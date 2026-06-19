#!/usr/bin/env python3
"""
---
uid: e337f1dd
name: pipeline-activate
type: tool
status: active
owner: talos
domain: "pipeline-activate.py — pipeline-template activation runtime + cascade execution."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/e337f1dd.py"
script_path: vault/tools/e337f1dd.py
spawnable_by:
  - all-executives
input:
  type: object
  description: "See tool usage for argument details"
created: 2026-05-27
created_by: talos-t10
governed_by: d5e1b4a3
member_of:
  - c7e4f9a2
schema_version: 2
---
"""

"""pipeline-activate.py — pipeline-template activation runtime + cascade execution.

Authored 2026-05-16 by Argus A67 per v1.35.0 design spec d2f8c194 v0.4-LOCKED
(Mike-A67 stance-i + Q24α: NEW dedicated script, NOT extension of
write-activation-entry.py). §Rule 10 v2.2 runtime enforcement pulled in-scope
per stance-i lock.

Distinct concern from write-activation-entry.py (which handles AGENT-class
activations — sa.* + executive boots). This script handles PIPELINE-TEMPLATE
activations — opening a pipeline run, authoring its activation-root-project,
executing the cascade_spec (per pipeline.capsule v2.6) if declared, all
atomically with roll-back on failure.

Usage:
    python3 .tropo/scripts/pipeline-activate.py \\
        --pipeline-uid <8-hex> \\
        --activated-by <activator-entity-uid-or-"user"> \\
        [--cycle-context <description>] \\
        [--event-date <YYYY-MM-DD>]  # required if pipeline carries spawns_tasks
        [--member-of-project-plan <uid>]  # internal; set when recursively spawning a workstream
        [--rollback-manifest <path>]  # internal; set when recursively spawning

Exit codes:
    0   Success — full cascade executed cleanly; UIDs printed to stdout
    1   Validation failure (cascade_spec schema; pipeline_uid resolution; cycle)
    2   Runtime authoring failure (filesystem, YAML write, subprocess)
    3   Argument or environment error
    4   Roll-back triggered + completed; substrate clean; non-zero ship signal

Per pipeline.capsule v2.6 + project-plan.capsule v1.4. Composes with
write-activation-entry.py (subprocess for activation entry authoring) +
existing §Rule 10 v2.2 activation-root-project pattern.
"""
import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

import yaml  # PyYAML — already used by tropo-validate.py

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
WRITE_ACTIVATION_SCRIPT = Path(__file__).parent / "write-activation-entry.py"
TODAY = time.strftime("%Y-%m-%d")
NOW = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
SCRIPT_NAME = "pipeline-activate.py"

# Workstream cascade depth soft-cap per pipeline.capsule §Rule 5 (3 levels max)
MAX_CASCADE_DEPTH = 3


# ---------------------- helpers ----------------------------------------------

def yaml_quote(s: str) -> str:
    """Wrap a free-text value in YAML double-quotes with proper escaping."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# f9751636 chokepoint: delegate to the canonical collision-checked minter.
import importlib.util as _ilu_e337
_mint_spec_337 = _ilu_e337.spec_from_file_location(
    "_mint_uid_canonical_337", Path(__file__).resolve().parent / "5187be30.py"
)
_mint_mod_337 = _ilu_e337.module_from_spec(_mint_spec_337)
_mint_spec_337.loader.exec_module(_mint_mod_337)


def load_existing_uids():
    return _mint_mod_337.load_existing_uids()


def mint_uid(existing):
    """Mint a fresh 8-hex UID not colliding with existing or disk state."""
    existing_with_session = _mint_mod_337.load_existing_uids() | existing
    for _ in range(64):
        candidate = secrets.token_hex(4)
        if candidate not in existing_with_session:
            existing.add(candidate)
            return candidate
    raise RuntimeError("Could not mint unique UID in 64 attempts (vault saturated?)")


def parse_frontmatter(content: str) -> dict:
    """Extract + parse YAML frontmatter via PyYAML."""
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---\n", 4)
    if end < 0:
        return {}
    fm_text = content[4:end]
    try:
        result = yaml.safe_load(fm_text)
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError as e:
        raise ValueError(f"Frontmatter YAML parse error: {e}")


def resolve_pipeline(uid: str) -> dict:
    """Load a pipeline template's frontmatter. Returns dict or raises."""
    path = VAULT_FILES / f"{uid}.md"
    if not path.exists():
        raise ValueError(f"pipeline_uid {uid} does not resolve at {path}")
    fm = parse_frontmatter(path.read_text())
    if fm.get("type") != "pipeline":
        raise ValueError(f"UID {uid} is not type:pipeline (got type:{fm.get('type')})")
    return fm


def validate_cascade_spec(cascade: dict, parent_uid: str, depth: int, seen: set) -> None:
    """Validate cascade_spec at runtime. Raises on any violation."""
    if depth > MAX_CASCADE_DEPTH:
        raise ValueError(f"cascade depth {depth} exceeds soft-cap {MAX_CASCADE_DEPTH} (pipeline.capsule §Rule 5)")
    if not isinstance(cascade, dict):
        raise ValueError(f"cascade_spec must be a mapping; got {type(cascade).__name__}")
    if "spawns_workstreams" in cascade:
        ws_list = cascade["spawns_workstreams"]
        if not isinstance(ws_list, list):
            raise ValueError("cascade_spec.spawns_workstreams must be a list")
        for ws in ws_list:
            if not isinstance(ws, dict):
                raise ValueError(f"spawns_workstreams entry must be a mapping: {ws}")
            for required in ("pipeline_uid", "name", "owner_agent_class"):
                if required not in ws:
                    raise ValueError(f"spawns_workstreams entry missing required field: {required}")
            ws_uid = ws["pipeline_uid"]
            if ws_uid in seen:
                raise ValueError(f"cascade cycle detected: pipeline {ws_uid} transitively spawns itself")
            ws_fm = resolve_pipeline(ws_uid)  # raises on resolution failure
            if ws_fm.get("role") != "workstream":
                raise ValueError(f"workstream pipeline {ws_uid} missing role:\"workstream\" (got role:{ws_fm.get('role')})")
            if ws_fm.get("status") not in ("active", "locked"):
                raise ValueError(f"workstream pipeline {ws_uid} status must be active or locked (got {ws_fm.get('status')})")
            # Recursive cycle-check
            ws_cascade = ws_fm.get("cascade_spec")
            if isinstance(ws_cascade, dict):
                validate_cascade_spec(ws_cascade, ws_uid, depth + 1, seen | {ws_uid, parent_uid})


# ---------------------- substrate authoring ---------------------------------

def author_activation_root_project(
    pipeline_fm: dict, pipeline_uid: str, master_activation_uid: str,
    existing: set, cycle_context: str, manifest: list,
    activated_by: str = "user",
    proj_uid: str = None,
) -> str:
    """Author activation-root-project per §Rule 10 v2.2. Returns project UID.

    P1-5 absorption (v1.35.0 R3 skeptic-088): owner + author resolve to the
    activated_by entity per project-plan.capsule Rule 5; previously hardcoded
    to script name (owner) and argus-a67 (author).
    """
    if proj_uid is None:
        proj_uid = mint_uid(existing)
    pipeline_name = pipeline_fm.get("name", "pipeline")
    title = f"{pipeline_name} — Activation Root ({TODAY})"
    desc = f"Activation-root-project for pipeline {pipeline_uid} run on {TODAY}. Per pipeline.capsule §Rule 10 v2.2. All downstream substrate for this activation member_of: this project."
    content = (
        f"---\n"
        f"uid: {proj_uid}\n"
        f"type: project\n"
        f"title: {yaml_quote(title)}\n"
        f"description: {yaml_quote(desc)}\n"
        f"status: active\n"
        f"state: active\n"
        f"owner: {yaml_quote(activated_by)}\n"
        f"author: {yaml_quote(activated_by)}\n"
        f"created: {TODAY}\n"
        f"created_by: pipeline-activate.py\n"
        f"modified: {TODAY}\n"
        f"modified_by: pipeline-activate.py\n"
        f"schema_version: 2\n"
        f"member_of:\n"
        f"  - {pipeline_uid}\n"
        f"activated_by_pipeline: {pipeline_uid}\n"
        f"activation_entry: {master_activation_uid}\n"
        f"tags: [activation-root-project, pipeline-activation, v1-35-0]\n"
        f"file_ext: md\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"*Activation-root-project per pipeline.capsule §Rule 10 v2.2. "
        f"All downstream substrate from this activation `member_of:` this project.*\n\n"
        f"## Context\n\n"
        f"- **Pipeline template:** [{pipeline_uid}]({pipeline_uid}.md)\n"
        f"- **Activation entry:** [{master_activation_uid}]({master_activation_uid}.md)\n"
        f"- **Activated on:** {TODAY}\n"
        + (f"- **Cycle context:** {cycle_context}\n" if cycle_context else "")
        + f"\n*Authored by pipeline-activate.py on behalf of {activated_by} | {TODAY}*\n"
    )
    (VAULT_FILES / f"{proj_uid}.md").write_text(content)
    manifest.append({"uid": proj_uid, "type": "project", "role": "activation-root-project"})
    return proj_uid


def author_project_plan(
    pipeline_fm: dict, pipeline_uid: str, activation_root_uid: str,
    cascade: dict, existing: set, manifest: list,
    activated_by: str = "user",
) -> str:
    """Author cascade-generated project-plan per project-plan.capsule v1.4. Returns plan UID.

    P1-5 absorption (v1.35.0 R3 skeptic-088): owner + author resolve to the
    activated_by entity per project-plan.capsule Rule 5.
    """
    plan_uid = mint_uid(existing)
    pipeline_name = pipeline_fm.get("name", "pipeline")
    title = f"{pipeline_name} — Project Plan"
    desc = f"Cascade-generated project plan for {pipeline_name} pipeline activation. Authored by pipeline-activate.py at activation-time per pipeline.capsule v2.6 cascade_spec.generates_project_plan."
    ws_list = cascade.get("spawns_workstreams", [])
    deliverables_text = "\n".join(
        f"### {i+1}. {ws.get('name', 'workstream')}\n\n"
        f"**Owner:** {ws.get('owner_agent_class', 'TBD')}\n"
        f"**Workstream pipeline:** [{ws.get('pipeline_uid', 'TBD')}]({ws.get('pipeline_uid', 'TBD')}.md)\n"
        f"**Acceptance criteria:** Workstream activation completes; all owned tasks reach terminal state; workstream wrap-up signed.\n"
        for i, ws in enumerate(ws_list)
    )
    content = (
        f"---\n"
        f"uid: {plan_uid}\n"
        f"type: project-plan\n"
        f"title: {yaml_quote(title)}\n"
        f"description: {yaml_quote(desc)}\n"
        f"owner: {yaml_quote(activated_by)}\n"
        f"status: draft\n"
        f"state: active\n"
        f"plan_for: {activation_root_uid}\n"
        f"derived_from:\n"
        f"  - {pipeline_uid}\n"
        f"member_of:\n"
        f"  - {activation_root_uid}\n"
        f"author: {yaml_quote(activated_by)}\n"
        f"created: {TODAY}\n"
        f"created_by: pipeline-activate.py\n"
        f"modified: {TODAY}\n"
        f"modified_by: pipeline-activate.py\n"
        f"schema_version: 2\n"
        f"tags: [project-plan, cascade-generated, v1-4-amendment]\n"
        f"file_ext: md\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"*Cascade-generated project plan. Authored by pipeline-activate.py per pipeline.capsule v2.6 + project-plan.capsule v1.4 (derived_from accepts pipeline-template UID).*\n\n"
        f"## Objectives\n\n"
        f"- Execute the {pipeline_name} pipeline end-to-end via the cascade-spawned workstreams.\n"
        f"- Each workstream-owning agent generates their own tasks against this plan and delivers per-workstream acceptance criteria.\n"
        f"- Plan composes against the master activation-root-project [{activation_root_uid}]({activation_root_uid}.md).\n\n"
        f"## Scope\n\n"
        f"**In-scope:** {len(ws_list)} workstreams declared by cascade_spec; each owned by named functional-class agent; all member_of this plan.\n\n"
        f"**Out-of-scope:** task-level execution detail (workstream-owning agents own tasks; not auto-cascaded by default).\n\n"
        f"## Deliverables\n\n{deliverables_text}\n"
        f"## Dependencies\n\n"
        f"- Pipeline template: [{pipeline_uid}]({pipeline_uid}.md) (v2.6+)\n"
        f"- pipeline.capsule v2.6\n"
        f"- project-plan.capsule v1.4\n"
        f"- pipeline-activate.py runtime\n\n"
        f"## Verification Plan\n\n"
        f"Each workstream's wrap-up signals completion. Master pipeline's wrap-up stage signals end-to-end success.\n\n"
        f"## Timeline\n\n"
        f"Phased per master pipeline's stage progression. No hard calendar dates per project-plan.capsule §Timeline rule.\n\n"
        f"## Open Decisions\n\n"
        f"- None at cascade generation. Workstream-owning agents may file decisions per their own work.\n\n"
        f"---\n\n"
        f"*Cascade-generated {TODAY} by pipeline-activate.py on behalf of {activated_by}*\n"
    )
    (VAULT_FILES / f"{plan_uid}.md").write_text(content)
    manifest.append({"uid": plan_uid, "type": "project-plan", "role": "cascade-generated"})
    return plan_uid


def open_master_activation_entry(
    pipeline_uid: str, activated_by: str, cycle_context: str,
    activation_root_uid: str, existing: set, manifest: list,
    activation_uid: str = None,
    dev_spec_uid: str = None,
) -> str:
    """Author activation entry per activation.capsule v1.0.

    Pipeline-class activations: agent-class fields filled with placeholder
    values that pin the pipeline runtime as the 'agent' for substrate-graph
    purposes. v1.35.5 amends activation.capsule to support activation_class
    discrimination properly; v1.35.0 ships with these placeholders.

    Accepts pre-minted activation_uid via kwargs for cross-reference coordination
    with author_activation_root_project (both files reference each other).
    dev_spec_uid: optional; written to frontmatter for three-pipeline coupling
    enforcement at close-time (v1.51 per engine-extension spec 51d171f3).
    """
    if activation_uid is None:
        activation_uid = mint_uid(existing)
    pipeline_path = VAULT_FILES / f"{pipeline_uid}.md"
    pipeline_fm = parse_frontmatter(pipeline_path.read_text())
    pipeline_name = pipeline_fm.get("name", "pipeline")
    desc = f"Pipeline activation for {pipeline_name} ({pipeline_uid}) opened by pipeline-activate.py on {TODAY}."
    cycle_ref = f"cycle_context: {yaml_quote(cycle_context)}\n" if cycle_context else ""
    dev_spec_ref = f"dev_spec_uid: {dev_spec_uid}\n" if dev_spec_uid else ""
    # v1.52 owner+assigned_to propagation (Mike-A82 board-surfacing amendment 2026-05-24):
    # Read pipeline def's owner: field; write owner + assigned_to on activation entry so
    # sa.board-agent's owner_prefix/assigned_to_prefix filters catch the activation as
    # owner's work on their next boot. Composes with dev-pipeline notify-step
    # (37996741) for immediate channel signal + persistent board surfacing.
    pipeline_owner = pipeline_fm.get("owner") or "unknown"
    owner_ref = f"owner: {yaml_quote(pipeline_owner)}\n"
    assigned_to_ref = f"assigned_to: {yaml_quote(pipeline_owner)}\n"
    # Generation: pipeline-uid suffix; could be enhanced to count prior runs.
    generation = f"{pipeline_uid}-{int(time.time())}"
    content = (
        f"---\n"
        f"uid: {activation_uid}\n"
        f"type: activation\n"
        f"name: {yaml_quote(f'pipeline-runtime-{pipeline_uid}')}\n"
        f"title: {yaml_quote(f'{pipeline_name} Activation — {TODAY}')}\n"
        f"description: {yaml_quote(desc)}\n"
        f"status: active\n"
        f"state: active\n"
        f"{owner_ref}"
        f"{assigned_to_ref}"
        f"activation_class: pipeline\n"
        f"agent: {yaml_quote('pipeline-runtime')}\n"
        f"agent_class: pipeline\n"
        f"agent_root: {pipeline_uid}\n"
        f"generation: {yaml_quote(generation)}\n"
        f"model: {yaml_quote('pipeline-activate.py-v1.0')}\n"
        f"platform: kernel\n"
        f"pipeline_uid: {pipeline_uid}\n"
        f"activated_by: {yaml_quote(activated_by)}\n"
        f"activated_at: {TODAY}\n"
        f"activation_root_project: {activation_root_uid}\n"
        f"member_of:\n"
        f"  - {activation_root_uid}\n"
        f"author: pipeline-activate.py\n"
        f"created: {TODAY}\n"
        f"created_by: pipeline-activate.py\n"
        f"modified: {TODAY}\n"
        f"modified_by: pipeline-activate.py\n"
        f"schema_version: 2\n"
        f"{cycle_ref}"
        f"{dev_spec_ref}"
        f"tags: [activation, pipeline-class, v1-35-0]\n"
        f"file_ext: md\n"
        f"---\n\n"
        f"# {pipeline_name} Activation — {TODAY}\n\n"
        f"*Pipeline activation entry opened by pipeline-activate.py per pipeline.capsule §Rule 10 v2.2 (runtime-enforced at v1.35.0 per stance-i). Agent-class fields carry placeholder values for activation.capsule v1.0 compliance; v1.35.5 amends activation.capsule to support `activation_class: pipeline` discrimination properly.*\n\n"
        f"## Activation context\n\n"
        f"- **Pipeline template:** [{pipeline_uid}]({pipeline_uid}.md)\n"
        f"- **Activation-root-project:** [{activation_root_uid}]({activation_root_uid}.md)\n"
        f"- **Activated by:** {activated_by}\n"
        f"- **Date:** {TODAY}\n"
        + (f"- **Cycle context:** {cycle_context}\n" if cycle_context else "")
        + (f"- **Dev-spec:** [{dev_spec_uid}]({dev_spec_uid}.md)\n" if dev_spec_uid else "")
        + f"\n*Authored by pipeline-activate.py | Argus A67 | 2026-05-16*\n"
    )
    (VAULT_FILES / f"{activation_uid}.md").write_text(content)
    manifest.append({"uid": activation_uid, "type": "activation", "role": "master"})
    return activation_uid


def author_workstream_activation(
    parent_activation_uid: str, parent_root_uid: str, parent_plan_uid: str,
    ws_entry: dict, existing: set, manifest: list, event_date: str = None,
    depth: int = 1, activated_by: str = "user",
) -> str:
    """Recursively activate a workstream sub-pipeline via self-invocation.

    Sub-activation gets its own activation-root-project per §Rule 10 (recursive
    composition); spawned activation's member_of includes parent's project-plan
    (per cascade_spec.member_of_project_plan: true) + parent's activation-root.
    """
    ws_uid = ws_entry["pipeline_uid"]
    ws_name = ws_entry["name"]
    owner_class = ws_entry["owner_agent_class"]
    member_of_plan = ws_entry.get("member_of_project_plan", True)

    # Load workstream pipeline + its cascade_spec (if present; for spawns_tasks)
    ws_fm = resolve_pipeline(ws_uid)
    ws_cascade = ws_fm.get("cascade_spec")

    # Author sub-activation-root-project
    sub_root_uid = mint_uid(existing)
    sub_title = f"{ws_name} — Workstream Activation Root ({TODAY})"
    sub_desc = f"Workstream activation-root for {ws_name} sub-pipeline ({ws_uid}); spawned by parent activation {parent_activation_uid}."
    member_of_list = [parent_root_uid]
    if member_of_plan and parent_plan_uid:
        member_of_list.append(parent_plan_uid)

    sub_root_content = (
        f"---\n"
        f"uid: {sub_root_uid}\n"
        f"type: project\n"
        f"title: {yaml_quote(sub_title)}\n"
        f"description: {yaml_quote(sub_desc)}\n"
        f"status: active\n"
        f"state: active\n"
        f"owner: {yaml_quote(owner_class)}\n"
        f"author: {yaml_quote(activated_by)}\n"
        f"created: {TODAY}\n"
        f"created_by: pipeline-activate.py\n"
        f"modified: {TODAY}\n"
        f"modified_by: pipeline-activate.py\n"
        f"schema_version: 2\n"
        f"member_of:\n"
        + "".join(f"  - {m}\n" for m in member_of_list)
        + f"workstream_role: {ws_name}\n"
        f"parent_activation: {parent_activation_uid}\n"
        f"tags: [workstream-activation-root, cascade-spawned, v1-35-0]\n"
        f"file_ext: md\n"
        f"---\n\n"
        f"# {sub_title}\n\n"
        f"*Workstream activation-root spawned by pipeline-activate.py from parent {parent_activation_uid} per pipeline.capsule v2.6 cascade_spec.spawns_workstreams.*\n\n"
        f"## Workstream context\n\n"
        f"- **Workstream pipeline:** [{ws_uid}]({ws_uid}.md)\n"
        f"- **Owner agent class:** `{owner_class}`\n"
        f"- **Parent activation:** [{parent_activation_uid}]({parent_activation_uid}.md)\n"
        f"- **Parent activation-root:** [{parent_root_uid}]({parent_root_uid}.md)\n"
        f"- **Parent project plan:** [{parent_plan_uid}]({parent_plan_uid}.md)\n\n"
        f"## Tasks\n\n"
        f"Workstream-owning agent (`{owner_class}`) generates tasks against the parent project plan. "
        f"Cascade does NOT auto-spawn tasks by default per v1.35.0 design (one workstream may opt-in via its own `spawns_tasks:`).\n\n"
        f"*Authored by pipeline-activate.py | Argus A67 | 2026-05-16*\n"
    )
    (VAULT_FILES / f"{sub_root_uid}.md").write_text(sub_root_content)
    manifest.append({"uid": sub_root_uid, "type": "project", "role": "workstream-activation-root"})

    # Author sub-activation entry
    sub_activation_uid = mint_uid(existing)
    sub_act_desc = f"Workstream activation for {ws_name} ({ws_uid}); spawned by master activation {parent_activation_uid}."
    sub_generation = f"{ws_uid}-{int(time.time())}"
    sub_act_content = (
        f"---\n"
        f"uid: {sub_activation_uid}\n"
        f"type: activation\n"
        f"name: {yaml_quote(f'workstream-runtime-{ws_uid}')}\n"
        f"title: {yaml_quote(f'{ws_name} Workstream Activation — {TODAY}')}\n"
        f"description: {yaml_quote(sub_act_desc)}\n"
        f"status: active\n"
        f"state: active\n"
        f"activation_class: pipeline\n"
        f"activation_role: workstream\n"
        f"agent: {yaml_quote(owner_class)}\n"
        f"agent_class: pipeline\n"
        f"agent_root: {ws_uid}\n"
        f"generation: {yaml_quote(sub_generation)}\n"
        f"model: {yaml_quote('pipeline-activate.py-v1.0')}\n"
        f"platform: kernel\n"
        f"pipeline_uid: {ws_uid}\n"
        f"activated_by: {parent_activation_uid}\n"
        f"activated_at: {TODAY}\n"
        f"activation_root_project: {sub_root_uid}\n"
        f"member_of:\n"
        + "".join(f"  - {m}\n" for m in member_of_list)
        + f"author: pipeline-activate.py\n"
        f"created: {TODAY}\n"
        f"created_by: pipeline-activate.py\n"
        f"modified: {TODAY}\n"
        f"modified_by: pipeline-activate.py\n"
        f"schema_version: 2\n"
        f"tags: [activation, workstream, cascade-spawned, v1-35-0]\n"
        f"file_ext: md\n"
        f"---\n\n"
        f"# {ws_name} Workstream Activation — {TODAY}\n\n"
        f"*Workstream activation spawned by pipeline-activate.py from master activation {parent_activation_uid}.*\n\n"
        f"## Cascade lineage\n\n"
        f"- **Workstream pipeline:** [{ws_uid}]({ws_uid}.md)\n"
        f"- **Workstream activation-root:** [{sub_root_uid}]({sub_root_uid}.md)\n"
        f"- **Parent activation:** [{parent_activation_uid}]({parent_activation_uid}.md)\n"
        f"- **Owner agent class:** `{owner_class}`\n\n"
        f"*Authored by pipeline-activate.py | Argus A67 | 2026-05-16*\n"
    )
    (VAULT_FILES / f"{sub_activation_uid}.md").write_text(sub_act_content)
    manifest.append({"uid": sub_activation_uid, "type": "activation", "role": "workstream"})

    # If workstream has spawns_tasks (teach-by-example pattern), author them
    if isinstance(ws_cascade, dict) and ws_cascade.get("spawns_tasks"):
        if not event_date:
            print(f"WARN: workstream {ws_uid} has spawns_tasks but no --event-date provided; skipping task spawn", file=sys.stderr)
        else:
            author_workstream_tasks(
                ws_cascade["spawns_tasks"], sub_root_uid, owner_class, event_date, existing, manifest
            )

    return sub_activation_uid


def author_workstream_tasks(
    tasks_spec: list, workstream_root_uid: str, default_owner: str,
    event_date: str, existing: set, manifest: list,
) -> list:
    """Author auto-cascade tasks for a workstream (teach-by-example pattern)."""
    import datetime
    task_uids = []
    try:
        event_dt = datetime.datetime.strptime(event_date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"--event-date must be YYYY-MM-DD; got: {event_date}")
    for task_spec in tasks_spec:
        task_uid = mint_uid(existing)
        title = task_spec["title"]
        owner = task_spec.get("owner_agent_class", default_owner)
        offset = task_spec.get("relative_offset_days", 0)
        task_date = event_dt + datetime.timedelta(days=int(offset))
        depends_on = task_spec.get("depends_on", []) or []
        content = (
            f"---\n"
            f"uid: {task_uid}\n"
            f"type: task\n"
            f"title: {yaml_quote(title)}\n"
            f"status: open\n"
            f"state: active\n"
            f"owner: {yaml_quote(owner)}\n"
            f"requested_of: {yaml_quote(owner)}\n"
            f"due_date: {task_date.isoformat()}\n"
            f"relative_offset_days: {offset}\n"
            f"depends_on: {json.dumps(depends_on)}\n"
            f"member_of:\n"
            f"  - {workstream_root_uid}\n"
            f"unit_of_work_purpose: {yaml_quote('Workstream contribution to event activation.')}\n"
            f"created: {TODAY}\n"
            f"created_by: pipeline-activate.py\n"
            f"modified: {TODAY}\n"
            f"modified_by: pipeline-activate.py\n"
            f"schema_version: 2\n"
            f"tags: [task, cascade-spawned, auto-task-spawn-teach-by-example]\n"
            f"file_ext: md\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"*Auto-spawned by pipeline-activate.py per workstream's cascade_spec.spawns_tasks (teach-by-example pattern). "
            f"Due {task_date.isoformat()} (event-date {offset:+d} days).*\n\n"
            f"**Owner:** `{owner}`\n"
            + (f"**Depends on:** {', '.join(depends_on)}\n" if depends_on else "")
            + f"\n*Cascade-spawned 2026-05-16 by pipeline-activate.py | Argus A67*\n"
        )
        (VAULT_FILES / f"{task_uid}.md").write_text(content)
        manifest.append({"uid": task_uid, "type": "task", "role": "cascade-spawned"})
        task_uids.append(task_uid)
    return task_uids


# ---------------------- roll-back -------------------------------------------

def write_manifest(manifest: list, manifest_path: Path):
    """Append manifest entries to roll-back file."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "a") as f:
        for entry in manifest:
            f.write(json.dumps({**entry, "authored_at": NOW}) + "\n")


def rollback(manifest: list):
    """Walk manifest in reverse + soft-delete each authored UID via tropo-recycle.py.

    Preservation Discipline (Principle 13 / 0aefe71d): vault/files/ entries are
    NEVER hard-deleted. tropo-recycle.py moves them to recycle/agent-deletions/
    with a dated trail. Recovery is a plain mv back. Hard-delete (path.unlink)
    is a Principle 13 violation and was the root cause of the v1.52 substrate-
    coherence defect (A82 2026-05-24).
    """
    recycle_script = VAULT_ROOT / ".tropo" / "scripts" / "tropo-recycle.py"
    print(f"ROLLBACK: walking {len(manifest)} manifest entries in reverse...", file=sys.stderr)
    recycle_failures: list[str] = []
    for entry in reversed(manifest):
        uid = entry["uid"]
        path = VAULT_FILES / f"{uid}.md"
        if not path.exists():
            continue
        result = subprocess.run(
            [sys.executable, str(recycle_script), uid,
             "--reason", "pipeline-activate rollback: activation failed mid-cascade"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"  recycled: {uid} → recycle/agent-deletions/", file=sys.stderr)
        else:
            # Preservation Discipline (Principle 13 / 0aefe71d): NEVER hard-delete a
            # governed vault/files/ entry. A rollback that cannot recycle LEAVES the
            # entry in place and fails loud for manual recovery — it must not unlink.
            # The prior `path.unlink()` fallback here was the silent-deletion root cause
            # of A82 (2026-05-24) + 2774e472 (2026-06-01); removed by Argus A93 2026-06-02.
            print(f"  [ERROR] tropo-recycle.py failed for {uid} (exit {result.returncode}): "
                  f"{result.stderr.strip()} — LEAVING {path} in place (no hard-delete; "
                  f"Principle 13).", file=sys.stderr)
            recycle_failures.append(uid)
    return recycle_failures


# ---------------------- main ------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pipeline-template activation runtime per v1.35.0 spec.")
    parser.add_argument("--pipeline-uid", required=True, help="8-hex UID of pipeline template to activate")
    parser.add_argument("--activated-by", required=True, help="Entity UID or 'user'")
    parser.add_argument("--cycle-context", default="", help="Optional human-readable cycle/run context")
    parser.add_argument("--event-date", default=None, help="YYYY-MM-DD; required if pipeline has spawns_tasks")
    parser.add_argument("--member-of-project-plan", default=None, help="(internal) parent project-plan UID for workstream spawns")
    parser.add_argument("--rollback-manifest", default=None, help="(internal) path to shared rollback manifest")
    parser.add_argument("--depth", type=int, default=0, help="(internal) cascade depth counter")
    parser.add_argument("--dev-spec-uid", default=None,
                        help="8-hex UID of locked dev-spec for three-pipeline coupling (required for dev-pipeline activations at v1.52+; WARN at v1.51 grace period)")
    args = parser.parse_args()

    pipeline_uid = args.pipeline_uid.strip()
    if not re.fullmatch(r"[0-9a-f]{8}", pipeline_uid):
        print(f"ERROR: --pipeline-uid must be 8-hex; got: {pipeline_uid}", file=sys.stderr)
        sys.exit(3)

    # Dev-spec validation (v1.51 grace period: WARN if absent; enforce at v1.52+)
    dev_spec_uid = None
    if args.dev_spec_uid:
        dev_spec_uid = args.dev_spec_uid.strip()
        if not re.fullmatch(r"[0-9a-f]{8}", dev_spec_uid):
            print(f"ERROR: --dev-spec-uid must be 8-hex; got: {dev_spec_uid}", file=sys.stderr)
            sys.exit(3)
        dev_spec_path = VAULT_FILES / f"{dev_spec_uid}.md"
        if not dev_spec_path.is_file():
            print(f"ERROR: --dev-spec-uid {dev_spec_uid!r} does not resolve in vault", file=sys.stderr)
            sys.exit(1)
        ds_fm = parse_frontmatter(dev_spec_path.read_text())
        if ds_fm.get("type") != "dev-spec":
            print(f"ERROR: {dev_spec_uid!r} is not type:dev-spec (got {ds_fm.get('type')!r})", file=sys.stderr)
            sys.exit(1)
        if ds_fm.get("stage") != "active" or ds_fm.get("status") != "locked":
            print(f"[WARN] dev-spec {dev_spec_uid!r} expected stage:active + status:locked; "
                  f"got stage:{ds_fm.get('stage')!r} status:{ds_fm.get('status')!r} "
                  f"(proceeding per v1.51 grace period)", file=sys.stderr)
    else:
        # No dev-spec provided — WARN at v1.51, will ERROR at v1.52
        pipeline_path = VAULT_FILES / f"{pipeline_uid}.md"
        if pipeline_path.is_file():
            pipeline_fm = parse_frontmatter(pipeline_path.read_text())
            if pipeline_fm.get("name") == "dev-pipeline":
                print("[WARN] dev-pipeline activation without --dev-spec-uid; "
                      "required at v1.52+ per dev-spec.capsule Rule 7 (grandfathered at v1.51)",
                      file=sys.stderr)

    # Setup roll-back manifest
    is_root_invocation = args.rollback_manifest is None
    if is_root_invocation:
        # Pre-mint activation UID to key the manifest folder per-activation (3a8c9e21 fix
        # 2026-06-07 Talos T13). Prior keying: spec-UID (A92 2026-06-01) or date (A82
        # 2026-05-24). Per-activation-UID is uniquely correct: every activation gets its
        # own manifest folder regardless of pipeline, spec, or date — zero collision risk.
        # Old per-day + per-spec folders preserve as historical record; new activations
        # always write per-activation folders.
        _existing_pre = load_existing_uids()
        pre_act_uid = mint_uid(_existing_pre)
        manifest_dir = VAULT_ROOT / "playbook-runs" / f"pipeline-activate-{pre_act_uid}"
        manifest_path = manifest_dir / "cascade-rollback.jsonl"
        if manifest_dir.exists() and manifest_path.exists() and manifest_path.stat().st_size > 0:
            print(
                f"ERROR: pipeline-activate manifest already exists at {manifest_path} — "
                f"activation {pre_act_uid!r} already ran; rollback collision risk. "
                f"Delete the manifest folder to force re-activation (check vault integrity first).",
                file=sys.stderr,
            )
            sys.exit(1)
        manifest_dir.mkdir(parents=True, exist_ok=True)
    else:
        pre_act_uid = None
        manifest_path = Path(args.rollback_manifest)
    manifest: list = []

    try:
        # 1. Load + validate pipeline template
        pipeline_fm = resolve_pipeline(pipeline_uid)
        existing = load_existing_uids()
        cascade = pipeline_fm.get("cascade_spec")
        if isinstance(cascade, dict):
            # P1-3 absorption (v1.35.0 R3 skeptic-088): seed seen with the root
            # pipeline_uid so a root self-spawn (root pipeline whose own
            # cascade_spec.spawns_workstreams names itself) is caught at the
            # top-level, not just at recursion-level.
            validate_cascade_spec(cascade, pipeline_uid, args.depth, {pipeline_uid})

        # 2. Mint UIDs for activation-root + master activation entry (cross-reference
        #    each other; pre-mint both so both authoring calls receive resolvable UIDs).
        #    Re-use the pre-minted activation UID (manifest folder is keyed on it).
        root_uid_actual = mint_uid(existing)
        act_uid_actual = pre_act_uid if pre_act_uid else mint_uid(existing)

        # 3. Author master activation entry (references root_uid_actual)
        open_master_activation_entry(
            pipeline_uid, args.activated_by, args.cycle_context, root_uid_actual,
            existing, manifest, activation_uid=act_uid_actual,
            dev_spec_uid=dev_spec_uid,
        )

        # 4. Author activation-root-project (references act_uid_actual)
        author_activation_root_project(
            pipeline_fm, pipeline_uid, act_uid_actual,
            existing, args.cycle_context, manifest,
            activated_by=args.activated_by, proj_uid=root_uid_actual,
        )

        # 5. Cascade execution (if cascade_spec present)
        plan_uid = args.member_of_project_plan
        if isinstance(cascade, dict):
            if cascade.get("generates_project_plan"):
                plan_uid = author_project_plan(
                    pipeline_fm, pipeline_uid, root_uid_actual, cascade,
                    load_existing_uids(), manifest,
                    activated_by=args.activated_by,
                )

            # Spawn workstream sub-activations
            ws_list = cascade.get("spawns_workstreams", []) or []
            for ws_entry in ws_list:
                author_workstream_activation(
                    act_uid_actual, root_uid_actual, plan_uid,
                    ws_entry, load_existing_uids(), manifest,
                    event_date=args.event_date, depth=args.depth + 1,
                    activated_by=args.activated_by,
                )

        # 6. Write manifest (success); print activation UID
        write_manifest(manifest, manifest_path)
        print(act_uid_actual)
        # C.4 — Stream C auto-emission: tropo.pipeline.activated (v1.58)
        try:
            _vr = Path(__file__).resolve().parents[2]
            _sp = _vr / ".tropo" / "scripts"
            if str(_sp) not in sys.path:
                sys.path.insert(0, str(_sp))
            from lib.event_emitter import auto_emit
            auto_emit("tropo.pipeline.activated", "/tools/pipeline-activate", "123e12e7",
                      lifecycle="evergreen",
                      data={"activation_uid": act_uid_actual, "pipeline_uid": args.pipeline_uid})
        except Exception:
            pass
        sys.exit(0)

    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        if manifest:
            left = rollback(manifest)
            if left:
                print(f"ROLLBACK INCOMPLETE: {len(left)} entr(y/ies) could not be recycled "
                      f"and were LEFT ON DISK for manual recovery (Preservation Discipline — "
                      f"never hard-deleted): {left}", file=sys.stderr)
        sys.exit(4 if manifest else 1)


if __name__ == "__main__":
    main()
