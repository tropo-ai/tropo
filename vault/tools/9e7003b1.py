#!/usr/bin/env python3
"""
---
uid: 9e7003b1
name: pipeline-runtime
type: tool
status: active
owner: talos
domain: "pipeline-runtime.py — v1.46.0 sequential-execution companion to pipeline-activate.py."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/9e7003b1.py"
script_path: vault/tools/9e7003b1.py
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
from __future__ import annotations

"""pipeline-runtime.py — v1.46.0 sequential-execution companion to pipeline-activate.py.

Authored 2026-05-20 by Argus A76 per v1.46.0 cycle brief MUST-SHIP #4 + design-spec
[2b809e0f] v0.2 LOCKED (Mike-A75 'fire' + 'proceed' authority 2026-05-20).

Sequential-execution architecture (Mike-A75 lock 2026-05-20): pipeline-activate.py
runs first as substrate-authoring layer (preserved unchanged; A67 v1.35.0; 639 LOC).
pipeline-runtime.py reads the activation entry by UID + handles runtime concerns:
activation contract presentation, run.jsonl event writing, structured
verification_receipt enforcement, next-step-eligibility computation, OTel attribute
emission, skip/authorization flow, resumption protocol.

Two-entry vault substrate: pipeline-activate.py's activation entry persists for
substrate-authoring lineage (type:activation, activation_class:pipeline);
pipeline-runtime.py writes its own pipeline-run entry at v2.0-shape with
substrate_authored_by: linking field (type:pipeline-run).

Usage:
    python3 .tropo/scripts/pipeline-runtime.py \\
        --activation-uid <8-hex> \\
        [--action <verb>] \\
        [action-specific args]

Exit codes:
    0   Success — action completed cleanly; result printed to stdout
    1   Validation failure (activation_uid does not resolve / structural defect)
    2   Runtime authoring failure (filesystem, jsonl write, subprocess)
    3   Argument or environment error
    4   Contract integrity failure (immutable mutation OR ineligible step transition)
    5   Skip-authorization failure (apply-skip without prior auth, etc.)

Per pipeline.capsule v3.0 + pipeline-run.capsule v2.0. Composes with
pipeline-activate.py (sequential predecessor) + tropo-validate.py (validator checks).
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import yaml  # PyYAML

# d996b941 L0c: shared identity resolver — must hard-fail on import (AC-L0c-fail)
_TROPO_SCRIPTS = Path(__file__).resolve().parents[2] / '.tropo' / 'scripts'
if str(_TROPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TROPO_SCRIPTS))
from lib._identity import _resolve_principal_uid, _get_principal_class  # noqa: E402

# ---------------------- constants ----------------------

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
PIPELINE_RUNS_FOLDER = VAULT_ROOT / "vault" / "pipeline-runs"
VAULT_INDEX = VAULT_ROOT / "vault" / "00-index.jsonl"
# v1.56 Lane S: relocated to vault/tools/; siblings resolved by UID
_TOOLS = Path(__file__).resolve().parent
TODAY = date.today().isoformat()
SCRIPT_NAME = "pipeline-runtime.py"
SCHEMA_VERSION = 2
EVENT_SIZE_CAP = 10240  # per pipeline-run.capsule v1.4 §Size Limit
TRIGGER_LOCK_TIMEOUT_SECONDS = 5  # fcntl.flock wait budget for dev-spec atomic append

# Exit codes per spec §15
EXIT_SUCCESS = 0
EXIT_VALIDATION = 1
EXIT_RUNTIME = 2
EXIT_ARGS = 3
EXIT_CONTRACT = 4
EXIT_SKIP_AUTH = 5


# ---------------------- error types ----------------------

class ValidationError(Exception):
    pass

class ContractError(Exception):
    pass

class SkipAuthError(Exception):
    pass

class DSLParseError(Exception):
    pass


# ---------------------- time helpers ----------------------

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------- UID minting (f9751636 chokepoint) ----------------------
# Delegate to the canonical collision-checked minter at vault/tools/5187be30.py.
# importlib required because the module name starts with a digit.

import importlib.util as _ilu
_mint_spec = _ilu.spec_from_file_location(
    "_mint_uid_canonical",
    Path(__file__).resolve().parent / "5187be30.py"
)
_mint_mod = _ilu.module_from_spec(_mint_spec)
_mint_spec.loader.exec_module(_mint_mod)


def load_existing_uids() -> set:
    return _mint_mod.load_existing_uids()


def mint_uid(existing: set) -> str:
    # Delegates to the canonical minter's collision universe (disk) merged with the
    # caller's accumulated session set (UIDs minted but not yet written to disk).
    existing_with_session = _mint_mod.load_existing_uids() | existing
    for _ in range(64):
        candidate = secrets.token_hex(4)
        if candidate not in existing_with_session:
            existing.add(candidate)
            return candidate
    return secrets.token_hex(8)  # fallback (original behavior)


def mint_span_id() -> str:
    return secrets.token_hex(8)


def _compute_step_fingerprint(step_uids: set) -> str:
    """d3a58cdf item 2 — derive a step-set fingerprint from the sorted leaf-step UID set.

    A computed fact, not a hand-maintained version field. The fingerprint detects both
    additions AND removals — the version string only caught what authors remembered to bump.
    Format: sha256(NUL-joined sorted UIDs)[:16] (64 bits; collision risk negligible at
    pipeline scales of <1000 steps).
    """
    payload = "\x00".join(sorted(str(uid) for uid in step_uids))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------- vault entry I/O ----------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)


def read_vault_entry(uid: str) -> dict | None:
    """Returns dict with 'frontmatter' (parsed yaml) + 'body' (str). None if missing."""
    path = VAULT_FILES / f"{uid}.md"
    if not path.is_file():
        return None
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    return {"frontmatter": fm, "body": m.group(2), "path": path}


_UID_BEARING_KEYS = frozenset({
    "uid", "pipeline", "pipeline_uid", "agent_root", "dev_spec_uid", "parent",
    "governed_by", "member_of", "refs", "composes_with", "supersedes", "superseded_by",
    "children", "depends_on_steps", "next_steps", "closes", "related_substrate",
    "triggered_doc_spec_uids", "triggered_test_spec_uids",
    "triggered_doc_activation_uids", "triggered_test_activation_uids",
})


def _coerce_uid_fields_to_str(fm: dict) -> dict:
    """Ensure UID-bearing frontmatter fields are Python strings before YAML dump.

    yaml.safe_dump writes integer values as bare integers (uid: 37996741), which
    YAML parsers then read back as int — the d3a58cdf whack-a-mole class. This
    coercion makes every write_vault_entry call safe: integers in UID-bearing
    fields become strings, and yaml.safe_dump quotes them correctly.
    """
    out = {}
    for k, v in fm.items():
        if k in _UID_BEARING_KEYS:
            if isinstance(v, int):
                out[k] = str(v)
            elif isinstance(v, list):
                out[k] = [str(i) if isinstance(i, int) else i for i in v]
            else:
                out[k] = v
        else:
            out[k] = v
    return out


class _NoAliasSafeDumper(yaml.SafeDumper):
    """SafeDumper that never emits YAML anchors/aliases (&id001 / *id001).

    Root-cause fix (argus-a115 2026-06-17): when two frontmatter keys share one list object
    (e.g. a pipeline-run's `members` and `member_of`), yaml.safe_dump serializes the second as
    an alias `*id001`. The index regex parser can't resolve aliases, so those edges silently
    vanish from the graph (21 pipeline-run member_of edges were lost this way). Ignoring aliases
    expands every reference to its literal value, so the parser always sees real UIDs.
    """
    def ignore_aliases(self, data):
        return True


def write_vault_entry(uid: str, frontmatter: dict, body: str) -> Path:
    """Write a vault entry. Overwrites if exists."""
    path = VAULT_FILES / f"{uid}.md"
    fm_yaml = yaml.dump(_coerce_uid_fields_to_str(frontmatter),
                        Dumper=_NoAliasSafeDumper,
                        default_flow_style=False, sort_keys=False,
                        allow_unicode=True, width=200)
    path.write_text(f"---\n{fm_yaml}---\n{body}")
    return path


# ---------------------- pipeline definition resolution ----------------------

def resolve_workflow_node_tree(root_uid: str) -> dict:
    """Walks pipeline definition recursively. Returns dict mapping step_uid -> step frontmatter."""
    nodes: dict[str, dict] = {}
    queue = [root_uid]
    seen: set[str] = set()
    while queue:
        uid = queue.pop(0)
        if uid in seen:
            continue
        seen.add(uid)
        entry = read_vault_entry(uid)
        if entry is None:
            raise ValidationError(f"pipeline node UID {uid!r} does not resolve")
        nodes[uid] = entry["frontmatter"]
        children = entry["frontmatter"].get("children") or []
        if isinstance(children, list):
            for child_uid in children:
                # D2 (v1.63): coerce YAML-integer UIDs to str — YAML parses unquoted
                # 8-digit hex-looking ints (e.g. 37996741) as integers, silently
                # dropping them from the step set. Coerce before the isinstance check.
                if isinstance(child_uid, int):
                    child_uid = str(child_uid)
                if isinstance(child_uid, str) and re.fullmatch(r"[0-9a-f]{8}", child_uid):
                    queue.append(child_uid)
    return nodes


def collect_step_nodes(nodes: dict) -> list[str]:
    """Returns step UIDs (leaf nodes — children: empty)."""
    steps = []
    for uid, fm in nodes.items():
        children = fm.get("children")
        if not children:
            steps.append(uid)
    return steps


# ---------------------- run-folder + jsonl ----------------------

def run_folder_for(pipeline_run_entry: dict) -> Path:
    rf = pipeline_run_entry.get("run_folder")
    if not rf:
        raise ValidationError(f"pipeline-run entry missing required run_folder: field")
    return (VAULT_ROOT / rf).resolve()


def current_jsonl_path(run_folder: Path) -> Path:
    """Return current jsonl segment path (run.jsonl or latest run-NNN.jsonl)."""
    index_path = run_folder / "run-index.json"
    if index_path.is_file():
        idx = json.loads(index_path.read_text())
        segments = idx.get("segments", [])
        if segments:
            return run_folder / segments[-1]
    return run_folder / "run.jsonl"


def event_count(jsonl_path: Path) -> int:
    if not jsonl_path.is_file():
        return 0
    with jsonl_path.open() as f:
        return sum(1 for line in f if line.strip())


def append_event(run_folder: Path, event: dict) -> None:
    """Atomic append with fcntl.flock + rollover on size cap (§6 spec)."""
    current = current_jsonl_path(run_folder)
    if current.is_file() and event_count(current) >= EVENT_SIZE_CAP:
        # Rollover
        next_n = 2
        while (run_folder / f"run-{next_n:03d}.jsonl").exists():
            next_n += 1
        new_segment = f"run-{next_n:03d}.jsonl"
        idx_path = run_folder / "run-index.json"
        idx = json.loads(idx_path.read_text()) if idx_path.is_file() else {"segments": ["run.jsonl"]}
        idx["segments"].append(new_segment)
        idx_path.write_text(json.dumps(idx, indent=2))
        current = run_folder / new_segment
    current.touch(exist_ok=True)
    with current.open("a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(json.dumps(event) + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_events(run_folder: Path) -> list[dict]:
    """Read all events across all segments."""
    events: list[dict] = []
    idx_path = run_folder / "run-index.json"
    if idx_path.is_file():
        segments = json.loads(idx_path.read_text()).get("segments", ["run.jsonl"])
    else:
        segments = ["run.jsonl"]
    for seg in segments:
        seg_path = run_folder / seg
        if not seg_path.is_file():
            continue
        with seg_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def make_event(event_type: str, actor: str, *,
               actor_label: str | None = None,
               step: str | None = None,
               stage: str | None = None,
               data: dict | None = None,
               trace_id: str,
               parent_span_id: str | None = None) -> dict:
    return {
        "event": event_type,
        "ts": now_iso(),
        "actor": actor,
        "actor_label_resolved": actor_label,
        "step": step,
        "stage": stage,
        "data": data or {},
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "span_id": mint_span_id(),
        "parent_span_id": parent_span_id,
    }


# ---------------------- state derivation (§6) ----------------------

def derive_state(events: list[dict]) -> dict:
    """Fold events left-to-right into current state.

    v1.46.0.1 fix (V48 finding 2026-05-20): per-step `pause_resumed_pending` set
    tracks approval-required steps that have been pause_resumed since their last
    pause_started. action_step_start consults this set to fire step_started
    instead of looping pause_started. Cleared when step_started fires.
    """
    state = {
        "step_status": {},
        "skip_authorizations": {},
        "step_spans": {},  # step_uid -> {started: span_id, completed: span_id, ...}
        "last_step_event": {},
        "run_status": "active",
        "current_stage": None,
        "current_step": None,
        "last_event_ts": None,
        "pause_resumed_pending": set(),
    }
    for i, ev in enumerate(events):
        et = ev.get("event")
        step = ev.get("step")
        state["last_event_ts"] = ev.get("ts")
        if et == "step_declared":
            sid = ev["data"].get("step_id")
            if sid:
                state["step_status"][sid] = "declared"
        elif et == "step_started" and step:
            state["step_status"][step] = "started"
            state["step_spans"].setdefault(step, {})["started"] = ev.get("span_id")
            state["current_step"] = step
            # The step has fired for real; clear any pending approval token
            state["pause_resumed_pending"].discard(step)
        elif et == "step_completed" and step:
            natural = (ev.get("data") or {}).get("natural_verdict")
            ev_data = ev.get("data") or {}
            if natural == "pass":
                # v1.66 S1 fix (b): promote to 'verified' ONLY when the verdict
                # comes from a real engine-sourced mechanism — signaled by the
                # presence of 'verification_command_exit_code' in event data (set
                # by the engine's command runner). A bare natural_verdict=pass with
                # no engine evidence stays at 'completed'; it must earn 'verified'
                # via a subsequent verification_receipt (Argus A102 ed04d931 §b).
                if "verification_command_exit_code" in ev_data:
                    state["step_status"][step] = "verified"
                else:
                    state["step_status"][step] = "completed"
            else:
                state["step_status"][step] = "completed"
            state["step_spans"].setdefault(step, {})["completed"] = ev.get("span_id")
        elif et == "verification_receipt" and step:
            verdict = (ev.get("data") or {}).get("verdict")
            if verdict == "pass":
                state["step_status"][step] = "verified"
        elif et == "step_criteria_amended" and step:
            # Amending criteria invalidates the prior asserted verification — reset
            # to "completed" so verify-step can compute a real receipt on the new criteria.
            # (Vela V56 00000668 2026-06-01 — closes the asserted-natural_verdict status hole)
            if state["step_status"].get(step) == "verified":
                state["step_status"][step] = "completed"
        elif et == "step_failed" and step:
            state["step_status"][step] = "failed"
        elif et == "step_skipped" and step:
            state["step_status"][step] = "skipped"
        elif et == "skip_authorization":
            sid = (ev.get("data") or {}).get("step_id")
            if sid:
                state["skip_authorizations"][sid] = ev.get("span_id")
        elif et == "pause_started":
            state["run_status"] = "paused"
        elif et == "pause_resumed":
            state["run_status"] = "active"
            # Resolve which step this resume is approving. Prefer explicit
            # data.step (v1.46.0.1+ schema); fall back to walking backward to the
            # most recent pause_started to recover the step UID for legacy events.
            paused_step = ev.get("step") or (ev.get("data") or {}).get("step")
            if not paused_step:
                for prior in reversed(events[:i]):
                    if prior.get("event") == "pause_started":
                        paused_step = (prior.get("data") or {}).get("step")
                        break
            if paused_step:
                state["pause_resumed_pending"].add(paused_step)
        elif et == "workflow_complete":
            state["run_status"] = "complete"
        elif et == "status_changed":
            new_status = (ev.get("data") or {}).get("status")
            if new_status:
                state["run_status"] = new_status
        if step:
            state["last_step_event"][step] = ev
    return state


def write_run_state_json(run_folder: Path, pipeline_run_entry: dict, state: dict, activation_uid: str) -> None:
    """Overwrite run.state.json with current derived state (§6)."""
    fm = pipeline_run_entry
    obj = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_run_uid": fm.get("uid"),
        "activation_uid": activation_uid,
        "substrate_authored_by": fm.get("substrate_authored_by"),
        "pipeline_uid": fm.get("pipeline"),
        "pipeline_version": fm.get("pipeline_version"),
        "current_stage": state.get("current_stage"),
        "current_step": state.get("current_step"),
        "step_status": state.get("step_status", {}),
        "skip_authorizations": state.get("skip_authorizations", {}),
        "pause_resumed_pending": sorted(state.get("pause_resumed_pending", set())),
        "eligible_steps": compute_eligible_steps(state, get_step_declarations(read_events(run_folder))),
        "last_event_ts": state.get("last_event_ts"),
        "last_segment_path": str(current_jsonl_path(run_folder).relative_to(VAULT_ROOT)),
        "run_status": state.get("run_status"),
        "supersession_reason": fm.get("supersession_reason"),
        "supersedes_activation": fm.get("supersedes_activation"),
    }
    (run_folder / "run.state.json").write_text(json.dumps(obj, indent=2) + "\n")


# ---------------------- eligibility ----------------------

def get_step_declarations(events: list[dict]) -> dict[str, dict]:
    """Return map step_uid -> step_declared event data.

    Prefers the latest step_criteria_amended event over step_declared for any
    step that has been amended (gap-3 fix per Vela V56 00000660 2026-06-01).
    This allows re-authored step criteria to reach an in-flight run without
    re-bootstrapping the whole pipeline-run.
    """
    decls = {}
    for ev in events:
        et = ev.get("event")
        data = ev.get("data") or {}
        if et == "step_declared":
            sid = data.get("step_id")
            if sid:
                decls[sid] = data
        elif et == "step_criteria_amended":
            # Override: latest amendment wins; merge criteria into existing decl
            sid = data.get("step_id")
            if sid and sid in decls:
                amended = dict(decls[sid])
                amended["exit_criteria"] = data.get("exit_criteria", amended.get("exit_criteria", []))
                if "verification_command" in data:
                    amended["verification_command"] = data["verification_command"]
                decls[sid] = amended
    return decls


def compute_eligible_steps(state: dict, step_declarations: dict[str, dict]) -> list[str]:
    """Compute set of step UIDs eligible to start (§7 spec)."""
    eligible = []
    for step_id, decl in step_declarations.items():
        status = state["step_status"].get(step_id, "declared")
        if status not in ("declared",):
            continue
        deps = decl.get("depends_on_steps") or []
        all_deps_satisfied = True
        for dep_uid in deps:
            # v1.63 P0 (Argus A93 2026-06-02): a locked run-contract may carry a UID ref
            # as a YAML int (e.g. 8654900a's dep [37996741]); the string-keyed step_status
            # + declarations won't resolve it. Coerce here so eligibility is robust to int
            # refs in any frozen contract. Part of the int-vs-string UID class (d3a58cdf).
            dep_uid = str(dep_uid)
            dep_status = state["step_status"].get(dep_uid)
            dep_decl = step_declarations.get(dep_uid, {})
            # Satisfied iff: verified, OR skipped (with auth),
            # OR vc:false + completed (completed is terminal for vc:false;
            # auto-receipt fires immediately but state query may race the write).
            # vc-conditional (v1.63 Argus A92 GO event 812).
            if dep_status == "verified":
                continue
            if dep_status == "completed" and not dep_decl.get("verification_class"):
                continue
            if dep_status == "skipped" and dep_uid in state["skip_authorizations"]:
                continue
            all_deps_satisfied = False
            break
        if all_deps_satisfied:
            eligible.append(step_id)
    return eligible


# ---------------------- parent_span_id resolution (§6) ----------------------

def find_event_span(events: list[dict], event_type: str, step: str | None = None) -> str | None:
    """Return span_id of most recent matching event."""
    for ev in reversed(events):
        if ev.get("event") != event_type:
            continue
        if step is not None and ev.get("step") != step:
            continue
        return ev.get("span_id")
    return None


# ---------------------- DSL parser (§10) ----------------------

def parse_exit_criterion(criterion_str: str) -> tuple[str, dict]:
    """Tokenize-then-dispatch parser per §10 v0.2 absorption."""
    s = criterion_str.strip()
    if s.startswith("file:"):
        if not s.endswith(".exists"):
            raise DSLParseError(f"file: criterion must end in .exists: {criterion_str!r}")
        path = s[5:-len(".exists")]
        return ("file_exists", {"path": path})
    if "." not in s:
        raise DSLParseError(f"missing '.' in criterion: {criterion_str!r}")
    uid_ref, rest = s.split(".", 1)
    for op in [" contains ", " matches ", " == "]:
        idx = rest.find(op)
        if idx >= 0:
            field = rest[:idx]
            value = rest[idx + len(op):]
            op_name = op.strip()
            if op_name == "==":
                return ("field_equals", {"uid_ref": uid_ref, "field": field, "value": value})
            if op_name == "contains":
                return ("field_contains", {"uid_ref": uid_ref, "field": field, "value": value})
            if op_name == "matches" and field == "body":
                return ("body_matches", {"uid_ref": uid_ref, "pattern": value})
            raise DSLParseError(f"unrecognized operator in criterion: {criterion_str!r}")
    if rest == "exists":
        return ("uid_exists", {"uid_ref": uid_ref})
    # populated op: uid_ref.field populated — passes if field is present and non-empty
    # (non-empty string, non-None, non-empty list). Argus A91 2026-06-01, pipeline.capsule v3.2.
    if rest.endswith(" populated") or rest == "populated":
        field = rest[: -len(" populated")].strip() if rest != "populated" else ""
        if not field:
            raise DSLParseError(f"populated op requires a field name: {criterion_str!r}")
        return ("field_populated", {"uid_ref": uid_ref, "field": field})
    raise DSLParseError(f"unrecognized criterion shape: {criterion_str!r}")


# ---------------------- substrate snapshot (§10) ----------------------

def build_snapshot(criteria: list[str], context_uids: dict) -> dict:
    """Read every UID referenced by any criterion exactly once; cache result."""
    snapshot: dict[str, dict | None] = {}
    for c in criteria:
        try:
            kind, args = parse_exit_criterion(c)
        except DSLParseError:
            continue
        target = None
        if kind in ("uid_exists", "field_equals", "field_contains", "body_matches", "field_populated"):
            ref = args["uid_ref"]
            # Resolve uid_ref via context
            target = resolve_uid_ref(ref, context_uids)
        elif kind == "file_exists":
            continue
        if target and target not in snapshot:
            snapshot[target] = read_vault_entry(target)
    return snapshot


def resolve_uid_ref(ref: str, context: dict) -> str | None:
    """Resolve a DSL uid-ref via context handles per §10."""
    if re.fullmatch(r"[0-9a-f]{8}", ref):
        return ref
    return context.get(ref)


def evaluate_criterion(
    criterion: str,
    context_uids: dict,
    snapshot: dict,
    run_events: list[dict] | None = None,  # for human_signoff + aggregate dispatch
) -> dict:
    """Returns {criterion, verdict, rationale, substrate_state_at_check}.

    4-way dispatch per criterion shape (Argus A91 6ec09070 2026-06-01):
      1. DSL  — uid_ref.exists / .field==V / .contains V / .body matches P / file:X.exists
      2. human: <event_id_or_step> — passes if a human_signoff event with verdict:accepted exists
      3. aggregate: <key>==<value> — passes if test_aggregate event carries that key=value
      4. (future) command: dispatched via verification_command on the step schema
    """
    # Dispatch 2: human: prefix — check for human_signoff event
    # v1.66 S1 verifier-independence fixes (Argus A102 ed04d931 §1):
    #   (i)  Step-scoped: signoff data.step must match subject (this step's UID)
    #   (ii) Independent: signed_by must differ from the step executor
    #        (no owner self-sign; the self-attestation route Metis 9a8c9adc closed)
    if criterion.strip().startswith("human:"):
        if run_events is None:
            return {"criterion": criterion, "verdict": "error",
                    "rationale": "human: criterion requires run_events context", "substrate_state_at_check": None}
        subject = criterion.strip()[len("human:"):].strip()
        # Find executor of this step (actor who fired step_completed for subject)
        step_executor = None
        for ev in run_events:
            if ev.get("event") == "step_completed" and ev.get("step") == subject:
                step_executor = ev.get("actor")
                break
        # Resolve executor to canonical principal UID for two-label spoof detection
        executor_principal_uid = _resolve_principal_uid(step_executor, VAULT_ROOT) if step_executor else None
        for ev in run_events:
            if ev.get("event") == "human_signoff":
                data = ev.get("data") or {}
                v = data.get("verdict", "")
                if v not in ("accepted", "pass", "approved"):
                    continue
                # (i) Step-scope: signoff must be for THIS step (B: scope-less rejected)
                ev_step = data.get("step") or ev.get("step")
                if not ev_step:
                    continue  # scope-less signoff rejected (v1.66 S1 fix B)
                if ev_step != subject:
                    continue  # signoff scoped to a different step
                # (ii) Independence: signer must be a REGISTERED principal (not None)
                # AND must differ from the executor — both enforced at this chokepoint
                # (v1.66 S1 consolidated fix; Argus A102 ed04d931 §1)
                # Trust ONLY ev.actor (engine-stamped author field); never data.signer_principal_uid
                # (agent-writable — forged stamp exploit, Vela V60 5th skeptic, 2026-06-07)
                signed_by = ev.get("actor") or data.get("signed_by") or ""
                signer_principal_uid = _resolve_principal_uid(signed_by, VAULT_ROOT)
                if signer_principal_uid is None:
                    continue  # unregistered signer — rejected (closes unregistered-label bypass)
                if executor_principal_uid and signer_principal_uid == executor_principal_uid:
                    continue  # same identity as executor — two-label spoof rejected
                return {"criterion": criterion, "verdict": "pass",
                        "rationale": f"human_signoff found: verdict={v!r} signed_by={signed_by!r} principal={signer_principal_uid!r} (independent of executor {step_executor!r}/{executor_principal_uid!r})",
                        "substrate_state_at_check": "run.jsonl:human_signoff"}
        return {"criterion": criterion, "verdict": "fail",
                "rationale": f"no accepted independent scoped human_signoff for step {subject!r} (must be step-scoped, signed by non-executor registered principal)",
                "substrate_state_at_check": None}

    # Dispatch 3: aggregate: prefix — check test_aggregate event
    if criterion.strip().startswith("aggregate:"):
        if run_events is None:
            return {"criterion": criterion, "verdict": "error",
                    "rationale": "aggregate: criterion requires run_events context", "substrate_state_at_check": None}
        expr = criterion.strip()[len("aggregate:"):].strip()
        # Shape: aggregate: <key> == <value>  OR  aggregate: <key> <= <value>
        import re as _re
        m = _re.match(r"^(.+?)\s*(==|<=|>=|<|>)\s*(.+)$", expr)
        for ev in run_events:
            if ev.get("event") == "test_aggregate":
                data = ev.get("data") or {}
                if m:
                    key, op, expected = m.group(1).strip(), m.group(2), m.group(3).strip()
                    actual = data.get(key)
                    try:
                        ok = eval(f"{repr(actual)} {op} {repr(type(actual)(expected))}")  # type-coerced compare
                    except Exception:
                        ok = str(actual) == expected
                    return {"criterion": criterion, "verdict": "pass" if ok else "fail",
                            "rationale": f"test_aggregate {key}={actual!r} {op} {expected!r} → {'pass' if ok else 'fail'}",
                            "substrate_state_at_check": "run.jsonl:test_aggregate"}
        return {"criterion": criterion, "verdict": "fail",
                "rationale": "no test_aggregate event found in run events",
                "substrate_state_at_check": None}

    # Dispatch 1: DSL (original path)
    try:
        kind, args = parse_exit_criterion(criterion)
    except DSLParseError as e:
        return {"criterion": criterion, "verdict": "error",
                "rationale": f"DSL parse failure: {e}", "substrate_state_at_check": None}
    if kind == "file_exists":
        path = args["path"]
        abs_path = (VAULT_ROOT / path) if not path.startswith("/") else Path(path)
        ok = abs_path.is_file()
        return {"criterion": criterion, "verdict": "pass" if ok else "fail",
                "rationale": f"file {abs_path} {'exists' if ok else 'missing'}",
                "substrate_state_at_check": str(abs_path)}
    ref = args["uid_ref"]
    target = resolve_uid_ref(ref, context_uids)
    if target is None:
        return {"criterion": criterion, "verdict": "error",
                "rationale": f"uid_ref {ref!r} failed to resolve via run context",
                "substrate_state_at_check": None}
    entry = snapshot.get(target)
    if entry is None:
        return {"criterion": criterion, "verdict": "fail",
                "rationale": f"vault entry {target} not present on disk",
                "substrate_state_at_check": target}
    if kind == "uid_exists":
        return {"criterion": criterion, "verdict": "pass",
                "rationale": f"vault entry {target} exists",
                "substrate_state_at_check": target}
    fm = entry["frontmatter"]
    if kind == "field_equals":
        actual = fm.get(args["field"])
        ok = str(actual) == args["value"] or actual == args["value"]
        return {"criterion": criterion, "verdict": "pass" if ok else "fail",
                "rationale": f"{args['field']}={actual!r} (expected {args['value']!r})",
                "substrate_state_at_check": f"{target}.{args['field']}"}
    if kind == "field_contains":
        actual = fm.get(args["field"])
        if not isinstance(actual, list):
            return {"criterion": criterion, "verdict": "fail",
                    "rationale": f"{args['field']} is not a list (got {type(actual).__name__})",
                    "substrate_state_at_check": f"{target}.{args['field']}"}
        ok = args["value"] in actual or any(str(x) == args["value"] for x in actual)
        return {"criterion": criterion, "verdict": "pass" if ok else "fail",
                "rationale": f"{args['field']} {'contains' if ok else 'does not contain'} {args['value']!r}",
                "substrate_state_at_check": f"{target}.{args['field']}"}
    if kind == "field_populated":
        actual = fm.get(args["field"])
        ok = actual is not None and actual != "" and actual != [] and actual != {}
        return {"criterion": criterion, "verdict": "pass" if ok else "fail",
                "rationale": f"{args['field']}={actual!r} ({'non-empty' if ok else 'absent or empty'})",
                "substrate_state_at_check": f"{target}.{args['field']}"}
    if kind == "body_matches":
        body = entry.get("body") or ""
        pattern = args["pattern"]
        # Try substring first; fall back to regex
        ok = pattern in body
        if not ok:
            try:
                ok = bool(re.search(pattern, body))
            except re.error:
                ok = False
        return {"criterion": criterion, "verdict": "pass" if ok else "fail",
                "rationale": f"body {'matches' if ok else 'does not match'} {pattern!r}",
                "substrate_state_at_check": f"{target}.body"}
    return {"criterion": criterion, "verdict": "error",
            "rationale": f"unknown criterion shape: {kind!r}",
            "substrate_state_at_check": None}


# ---------------------- pipeline-run discovery ----------------------

def find_pipeline_run_for(activation_uid: str) -> dict | None:
    """Reverse-lookup pipeline-run entry via substrate_authored_by. Scans vault/files/."""
    for f in VAULT_FILES.glob("*.md"):
        entry = read_vault_entry(f.stem)
        if entry is None:
            continue
        fm = entry["frontmatter"]
        if fm.get("type") == "pipeline-run" and fm.get("substrate_authored_by") == activation_uid:
            return entry
    return None


def build_run_context_uids(pipeline_run_entry: dict, activation_uid: str) -> dict:
    """Build context-uid map for DSL resolution (§10).

    Named handles available to exit_criteria DSL authors:
      activation          — the activation entry UID
      pipeline            — the pipeline definition UID
      activation_root     — the activation root project UID (first member of pipeline-run)
      dev_spec            — dev_spec_uid from activation frontmatter (dev-pipeline only)
      triggered_doc_spec  — first triggered doc-spec UID (from dev-spec frontmatter)
      triggered_test_spec — first triggered test-spec UID (from dev-spec frontmatter)
      triggered_doc_activation  — first triggered doc-pipeline activation UID
      triggered_test_activation — first triggered test-pipeline activation UID
    Plus any literal 8-hex UID resolves directly.
    """
    fm = pipeline_run_entry["frontmatter"] if "frontmatter" in pipeline_run_entry else pipeline_run_entry
    ctx: dict = {"activation": activation_uid, "pipeline": fm.get("pipeline")}
    members = fm.get("members") or []
    if isinstance(members, list) and members:
        ctx["activation_root"] = members[0]

    # Resolve activation entry for dev_spec_uid + triggered UIDs
    activation_entry = read_vault_entry(activation_uid)
    if activation_entry:
        afm = activation_entry["frontmatter"]
        dev_spec_uid = afm.get("dev_spec_uid")
        if dev_spec_uid:
            ctx["dev_spec"] = dev_spec_uid
            ds = read_vault_entry(dev_spec_uid)
            if ds:
                dsf = ds["frontmatter"]
                doc_specs = dsf.get("triggered_doc_spec_uids") or []
                test_specs = dsf.get("triggered_test_spec_uids") or []
                doc_acts = dsf.get("triggered_doc_activation_uids") or []
                test_acts = dsf.get("triggered_test_activation_uids") or []
                if doc_specs:
                    ctx["triggered_doc_spec"] = doc_specs[0]
                if test_specs:
                    ctx["triggered_test_spec"] = test_specs[0]
                if doc_acts:
                    ctx["triggered_doc_activation"] = doc_acts[0]
                if test_acts:
                    ctx["triggered_test_activation"] = test_acts[0]
    return ctx


# ---------------------- bootstrap (action) ----------------------

def action_bootstrap(activation_uid: str, contract_input_path: str | None, dry_run: bool) -> str:
    activation = read_vault_entry(activation_uid)
    if activation is None:
        raise ValidationError(f"activation_uid {activation_uid!r} does not resolve")
    afm = activation["frontmatter"]
    if afm.get("type") != "activation":
        raise ValidationError(f"UID {activation_uid!r} is not type:activation (got {afm.get('type')!r})")
    if afm.get("activation_class") != "pipeline":
        raise ValidationError(f"UID {activation_uid!r} is not activation_class:pipeline")

    # Reject if a pipeline-run already exists for this activation — unless the prior run
    # was superseded via contract-modification (E5 fix v1.53): an amended contract requires
    # a fresh bootstrap; the prior run entry is preserved with activation_superseded:true.
    existing = find_pipeline_run_for(activation_uid)
    if existing is not None:
        efm = existing["frontmatter"]
        if efm.get("activation_superseded") and efm.get("supersession_reason") == "contract-modification":
            print(f"[INFO] prior pipeline-run {efm.get('uid')!r} superseded via contract-modification; "
                  "allowing re-bootstrap", file=sys.stderr)
        else:
            raise ValidationError(
                f"pipeline-run entry {efm.get('uid')!r} already exists for "
                f"activation {activation_uid!r}; cannot bootstrap twice")

    pipeline_uid = afm.get("pipeline_uid")
    if not pipeline_uid:
        raise ValidationError(f"activation entry missing pipeline_uid field")
    pipeline_def = read_vault_entry(pipeline_uid)
    if pipeline_def is None:
        raise ValidationError(f"pipeline_uid {pipeline_uid!r} does not resolve")
    nodes = resolve_workflow_node_tree(pipeline_uid)
    step_uids = collect_step_nodes(nodes)
    if not step_uids:
        raise ValidationError(f"pipeline {pipeline_uid!r} has no leaf step WorkflowNodes")

    # Build proposed contract (v3.0 schema defaults applied for v2.6-shape steps)
    steps_locked = []
    for step_uid in step_uids:
        sfm = nodes[step_uid]
        steps_locked.append({
            "step_id": step_uid,
            "step_owner_role": sfm.get("step_owner_role") or "unspecified",
            "step_verifier_role": sfm.get("step_verifier_role") or "same-as-executor",
            "verification_class": bool(sfm.get("verification_class", False)),
            "depends_on_steps": sfm.get("depends_on_steps") or [],
            "exit_criteria": sfm.get("exit_criteria") or [],
            "trust_level": sfm.get("trust_level") or pipeline_def["frontmatter"].get("default_trust_gradient") or "auto-with-verification",
            "retry_policy": sfm.get("retry_policy") or {"max_retries": 0, "backoff": "linear"},
            "timeout_hours": sfm.get("timeout_hours") or 24,
            "compensation_step_id": sfm.get("compensation_step_id"),
            "instructions_ref": sfm.get("instructions_ref"),
            # v1.66 S1 fix (Vela V60 captain-mode 2026-06-07, per Argus A102 design-lock
            # event 2239 + finding 7c4e9a1b): carry verification_command + verdict_cwd from
            # the step frontmatter into the locked contract. Without this, get_step_declarations
            # never recovers them and BOTH command sites (action_step_complete ~L1227 +
            # action_verify_step ~L1353) read decl.get("verification_command")=None — so the
            # declared command NEVER runs on a normal activation and the vc:true verdict falls
            # back to same-as-executor self-attestation (the exact Gate-6 hole AC6 caught).
            # step_declared carries data=step (L963), so this propagates to events by construction.
            "verification_command": sfm.get("verification_command"),
            "verdict_cwd": sfm.get("verdict_cwd"),
        })

    # E2 (v1.63): assert every depends_on_steps entry resolves to a locked step.
    # A dangling dep (int UID, missing step, typo) can never be satisfied — catching
    # it here prevents a run that is born structurally blocked. Closes the class:
    # 37996741 was added as an int in substrate, silently dropped by the tree-walker,
    # then locked as a dep on 8654900a → run born with an unsatisfiable dep.
    _step_uid_set = set(s["step_id"] for s in steps_locked)
    for _s in steps_locked:
        for _dep in (_s.get("depends_on_steps") or []):
            _dep_str = str(_dep) if isinstance(_dep, int) else _dep
            if _dep_str not in _step_uid_set:
                raise ValidationError(
                    f"step {_s['step_id']!r} depends_on_steps contains {_dep!r} "
                    f"which is not a declared step in pipeline {pipeline_uid!r}. "
                    f"Fix the pipeline substrate before bootstrapping (E2 v1.63)."
                )

    # B2 (v1.62): refuse bootstrap if ship/close steps carry empty exit_criteria.
    # Ship/close steps are identified as: approval-required trust_level OR verification_class:true.
    # These are the gates that must be specified before a run can meaningfully start.
    hollow_gate_steps = [
        s["step_id"] for s in steps_locked
        if (s.get("trust_level") == "approval-required" or s.get("verification_class"))
        and not s.get("exit_criteria")
    ]
    if hollow_gate_steps:
        raise ValidationError(
            f"Bootstrap refused — ship/close steps have empty exit_criteria (v1.62 B2): "
            f"{hollow_gate_steps}. Populate exit_criteria DSL on these steps before bootstrapping. "
            f"A pipeline with unspecified close criteria cannot be verified — it will fail at "
            f"verify-step and cannot reach workflow_complete."
        )

    # Prompt user for the four contract questions
    responses = collect_contract_responses(contract_input_path, steps_locked)

    contract = {
        "pipeline_uid": pipeline_uid,
        "pipeline_version": pipeline_def["frontmatter"].get("version") or "0.0.0",
        "cycle_context": afm.get("cycle_context") or "",
        "steps_locked": steps_locked,
        "skips_authorized_upfront": responses.get("skips_authorized_upfront", []),
        "additional_steps_added": responses.get("additional_steps_added", []),
        "trust_overrides": responses.get("trust_overrides", []),
        "human_instructions": responses.get("human_instructions", ""),
        "supersession_reason": responses.get("supersession_reason"),
        "supersedes_activation": responses.get("supersedes_activation"),
    }

    if dry_run:
        print(json.dumps({"dry_run": True, "contract": contract}, indent=2), file=sys.stdout)
        return ""

    # v1.68 S2 — Inbox Transition Protocol activation wire.
    # When a dev-spec is inbox-resident at cycle activation, strip the inbox edge
    # and re-parent to the cycle's activation_root_project (the root UID from the
    # activation entry — SOURCE field is afm.activation_root_project).
    # Idempotent: no-op if the dev-spec is not inbox-resident.
    # Precedent: run_close_out_hook read-mutate-write pattern (9e7003b1.py ~L2256-2308).
    _dev_spec_uid = afm.get("dev_spec_uid")
    _root_uid = (
        afm.get("activation_root_project")
        or (activation_root_list[0] if activation_root_list else None)
    )
    if _dev_spec_uid and _root_uid:
        _ds_entry = read_vault_entry(_dev_spec_uid)
        if _ds_entry:
            _dsf = _ds_entry["frontmatter"]
            _ds_member_of = _dsf.get("member_of") or []
            if isinstance(_ds_member_of, str):
                _ds_member_of = [_ds_member_of]
            # Resolve inbox UIDs (entries with '01-inbox' in title) from the index
            _inbox_uids: set = set()
            try:
                _idx = VAULT_ROOT / "vault" / "00-index.jsonl"
                if _idx.exists():
                    for _raw in _idx.read_text(encoding="utf-8").splitlines():
                        if not _raw.strip():
                            continue
                        try:
                            _e = json.loads(_raw)
                            if isinstance(_e, dict):
                                _t = str(_e.get("title") or _e.get("name") or "").lower()
                                if "01-inbox" in _t or ("01-" in _t and "inbox" in _t):
                                    _inbox_uids.add(_e.get("uid", ""))
                        except Exception:
                            pass
            except Exception:
                pass
            _inbox_in_member_of = [u for u in _ds_member_of if u in _inbox_uids]
            if _inbox_in_member_of:
                _new_member_of = [u for u in _ds_member_of if u not in _inbox_uids]
                if _root_uid not in _new_member_of:
                    _new_member_of.append(_root_uid)
                _dsf["member_of"] = _new_member_of
                _dsf["modified"] = TODAY
                _dsf["modified_by"] = activated_by
                write_vault_entry(_dev_spec_uid, _dsf, _ds_entry.get("body", ""))
                _trans_ev = make_event(
                    "tropo.substrate.modified", activated_by,
                    trace_id=activation_uid, parent_span_id=None,
                    data={
                        "action": "inbox-transition",
                        "uid": _dev_spec_uid,
                        "from": _inbox_in_member_of,
                        "to": _root_uid,
                    }
                )
                # Emit to the vault event log rather than the run folder (not created yet)
                try:
                    _ev_path = VAULT_ROOT / "vault" / "events.jsonl"
                    if _ev_path.exists():
                        with _ev_path.open("a", encoding="utf-8") as _ef:
                            _ef.write(json.dumps(_trans_ev) + "\n")
                except Exception:
                    pass
                print(f"[INFO] inbox-transition: dev-spec {_dev_spec_uid!r} re-parented "
                      f"from inbox(es) {_inbox_in_member_of} to root {_root_uid!r}",
                      file=sys.stderr)

    # Mint pipeline-run UID + create run-folder
    existing_uids = load_existing_uids()
    pipeline_run_uid = mint_uid(existing_uids)
    pipeline_name = pipeline_def["frontmatter"].get("name", "pipeline").lower().replace(" ", "-").replace("/", "-")
    pipeline_name = re.sub(r"[^a-z0-9-]", "", pipeline_name) or "pipeline"
    run_folder_rel = f"vault/pipeline-runs/{pipeline_name}-{pipeline_run_uid}-{TODAY}"
    run_folder_abs = VAULT_ROOT / run_folder_rel
    run_folder_abs.mkdir(parents=True, exist_ok=False)
    (run_folder_abs / "artifacts").mkdir()

    activation_root = afm.get("activation_root_project") or afm.get("member_of") or []
    if isinstance(activation_root, str):
        activation_root_list = [activation_root]
    elif isinstance(activation_root, list):
        activation_root_list = activation_root
    else:
        activation_root_list = []

    activated_by = afm.get("activated_by") or "user"

    # Author pipeline-run vault entry (v2.0 shape)
    pr_frontmatter = {
        "uid": pipeline_run_uid,
        "type": "pipeline-run",
        "title": f"{pipeline_def['frontmatter'].get('name', 'pipeline')} — Run {TODAY}",  # R2 nav render-safety (argus-a110 2026-06-12)
        "name": f"{pipeline_def['frontmatter'].get('name', 'pipeline')} — Run {TODAY}",
        "pipeline": pipeline_uid,
        "pipeline_version": pipeline_def["frontmatter"].get("version") or "0.0.0",
        "pipeline_step_fingerprint": _compute_step_fingerprint(set(step_uids)),  # d3a58cdf item 2
        "substrate_authored_by": activation_uid,
        "status": "active",
        "state": "active",
        "current_stage": None,
        "current_step": None,
        "members": activation_root_list or [],
        "owner": activated_by,
        "principal": activated_by,
        "authorized_by": activated_by,
        "started_at": now_iso(),
        "current_step_entered_at": now_iso(),
        "run_folder": run_folder_rel,
        "member_snapshot_mode": "live",
        "restart_strategy": "manual",
        "schema_version": SCHEMA_VERSION,
        "created": TODAY,
        "created_by": SCRIPT_NAME,
        "modified": TODAY,
        "modified_by": SCRIPT_NAME,
        "member_of": activation_root_list,
        "tags": ["pipeline-run", "v2-0-shape", "v1-46-0"],
    }
    if responses.get("supersedes_activation"):
        pr_frontmatter["supersedes_activation"] = responses["supersedes_activation"]
        pr_frontmatter["supersession_reason"] = responses.get("supersession_reason")
    body = f"""# {pr_frontmatter['name']}

*v2.0-shape pipeline-run instance authored by pipeline-runtime.py 2026-05-20.*

**Activation:** [{activation_uid}](../files/{activation_uid}.md)
**Pipeline:** [{pipeline_uid}](../files/{pipeline_uid}.md) v{pr_frontmatter['pipeline_version']}
**Run folder:** `{run_folder_rel}/`

See `run.jsonl` in the run folder for the full event log; `run.state.json` for derived current state.
"""
    write_vault_entry(pipeline_run_uid, pr_frontmatter, body)

    # Seed run-folder files
    (run_folder_abs / "definition.md").write_text(
        f"# Pipeline-Run Definition\n\nSee vault entry [{pipeline_run_uid}](../../files/{pipeline_run_uid}.md).\n")
    (run_folder_abs / "context.md").write_text(
        f"# Run Context\n\n{afm.get('cycle_context', '')}\n")
    (run_folder_abs / "thread.md").write_text(
        "# LLM Working Memory\n\n*Append-only by convention.*\n")

    # Seed events: run_created + activation_contract_locked + N step_declared
    run_created = make_event(
        "run_created", activated_by,
        trace_id=activation_uid, parent_span_id=None,
        data={
            "pipeline": pipeline_uid,
            "pipeline_version": pr_frontmatter["pipeline_version"],
            "members": activation_root_list,
            "authorized_by": activated_by,
        },
    )
    append_event(run_folder_abs, run_created)

    contract_event = make_event(
        "activation_contract_locked", activated_by,
        trace_id=activation_uid, parent_span_id=run_created["span_id"],
        data=contract,
    )
    append_event(run_folder_abs, contract_event)

    for step in steps_locked:
        ev = make_event(
            "step_declared", activated_by,
            step=step["step_id"],
            trace_id=activation_uid, parent_span_id=contract_event["span_id"],
            data=step,
        )
        append_event(run_folder_abs, ev)

    # Write run.state.json
    events = read_events(run_folder_abs)
    state = derive_state(events)
    write_run_state_json(run_folder_abs, pr_frontmatter, state, activation_uid)

    # C.5 — Stream C auto-emission: tropo.pipeline.bootstrapped (v1.58)
    try:
        _sp = Path(__file__).resolve().parents[2] / ".tropo" / "scripts"
        import sys as _sys
        if str(_sp) not in _sys.path:
            _sys.path.insert(0, str(_sp))
        from lib.event_emitter import auto_emit
        auto_emit("tropo.pipeline.bootstrapped", "/tools/pipeline-runtime", "123e12e7",
                  lifecycle="evergreen",
                  data={"activation_uid": activation_uid, "pipeline_run_uid": pipeline_run_uid})
    except Exception:
        pass

    return pipeline_run_uid


def collect_contract_responses(contract_input_path: str | None, steps_locked: list[dict]) -> dict:
    """Collect responses to the four contract questions (§5)."""
    if contract_input_path:
        with open(contract_input_path) as f:
            text = f.read()
        return yaml.safe_load(text) or {}
    if not sys.stdin.isatty():
        print("ERROR: non-TTY invocation requires --contract-input <path>", file=sys.stderr)
        sys.exit(EXIT_ARGS)
    print("\n=== Activation Contract Proposed ===", file=sys.stderr)
    for s in steps_locked:
        print(f"  {s['step_id']}  owner={s['step_owner_role']}  verifier={s['step_verifier_role']}  "
              f"trust={s['trust_level']}  exit_criteria={len(s['exit_criteria'])}",
              file=sys.stderr)
    try:
        import readline  # noqa: F401
    except ImportError:
        pass
    skips_raw = input("Steps to skip upfront? (newline-separated step_uids; blank = none): ").strip()
    additions_raw = input("Additional steps to add? (y/n; y prompts for free-text JSON spec): ").strip().lower()
    overrides_raw = input("Trust-level overrides? (newline-separated `step_uid:trust_level`; blank = none): ").strip()
    instructions = input("Specific instructions for this activation? (free-text or blank): ").strip()

    skips = []
    if skips_raw:
        for sid in re.split(r"\s+", skips_raw):
            if sid:
                skips.append({"step_id": sid, "authorized_by": "user", "reason": "skip-upfront"})

    additional = []
    if additions_raw == "y":
        extra = input("Paste additional step specs as JSON array (or blank to skip): ").strip()
        if extra:
            try:
                parsed = json.loads(extra)
                if isinstance(parsed, list):
                    additional = parsed
            except json.JSONDecodeError:
                print("WARNING: could not parse additional steps JSON; ignored", file=sys.stderr)

    overrides = []
    if overrides_raw:
        for line in overrides_raw.splitlines():
            if ":" in line:
                sid, level = line.split(":", 1)
                overrides.append({"step_id": sid.strip(), "override_to": level.strip()})

    print("\n=== Locked Contract Echo ===", file=sys.stderr)
    print(f"  skips: {len(skips)}  additions: {len(additional)}  overrides: {len(overrides)}",
          file=sys.stderr)
    print(f"  instructions: {instructions[:80]!r}", file=sys.stderr)
    confirm = input("Confirm and write activation_contract_locked event? (y/n): ").strip().lower()
    if confirm != "y":
        print("ERROR: contract not confirmed", file=sys.stderr)
        sys.exit(EXIT_CONTRACT)

    return {
        "skips_authorized_upfront": skips,
        "additional_steps_added": additional,
        "trust_overrides": overrides,
        "human_instructions": instructions,
    }


# ---------------------- shared bootstrap state ----------------------

def _auto_heal_stale_def(
    pr: dict, run_folder: Path, events: list[dict], activation_uid: str
) -> tuple[list[dict], dict]:
    """B1 (v1.54) — auto-heal active pipeline-run whose def-snapshot is stale.

    When a pipeline def is amended (new steps added, versions bumped) after a run
    was bootstrapped, the run's step_declared set becomes stale. This function
    detects the delta and emits step_declared events for any steps the current def
    declares that the run has not yet seen — silently, without manual ceremony.

    Design against the v1.52 notify-step case: b67c75e2 missed trigger notify-step
    37996741 added to dev-pipeline def cd1fcd25 post-bootstrap. Auto-heal would have
    emitted step_declared for 37996741 transparently at next engine tick.

    Returns updated (events, state) tuple; no-ops if def is current or auto-heal fails.
    Self-Healing Path 1 posture: fix-on-see, no surfacing to owner.
    """
    pr_fm = pr["frontmatter"]
    pipeline_uid = pr_fm.get("pipeline")
    if not pipeline_uid:
        return events, derive_state(events)

    # Staleness detection: compare recorded pipeline_version vs current def version
    pipeline_def = read_vault_entry(pipeline_uid)
    if pipeline_def is None:
        return events, derive_state(events)

    recorded_version = pr_fm.get("pipeline_version") or ""
    current_version = pipeline_def["frontmatter"].get("version") or ""

    # d3a58cdf item 2 — fingerprint-first staleness check.
    # D1 (v1.63) removed the version-equality early-return (version string can lie when
    # an author adds a step without bumping the version). The fingerprint is a COMPUTED
    # fact from the sorted leaf-step UID set — it detects additions AND removals without
    # trusting any hand-maintained field. Fast O(log n) compare before the expensive
    # tree resolve; fall through to full set-diff only if fingerprints differ.
    declared_step_uids = set(get_step_declarations(events).keys())
    recorded_fingerprint = pr_fm.get("pipeline_step_fingerprint") or ""

    # Cheap fingerprint path: resolve tree once, check fingerprint first
    try:
        nodes = resolve_workflow_node_tree(pipeline_uid)
        current_step_uids = set(collect_step_nodes(nodes))
    except Exception as e:
        print(f"[WARN] B1 auto-heal: could not resolve current step list for {pipeline_uid!r}: {e}",
              file=sys.stderr)
        return events, derive_state(events)

    current_fingerprint = _compute_step_fingerprint(current_step_uids)
    if recorded_fingerprint and recorded_fingerprint == current_fingerprint:
        # Fingerprints match — def has not changed; no heal needed, skip even version update.
        return events, derive_state(events)

    new_steps = [uid for uid in collect_step_nodes(nodes) if uid not in declared_step_uids]

    if not new_steps:
        # Fingerprint changed (e.g. step removed) but no new steps to declare.
        # Update fingerprint + version record so future ticks don't re-evaluate.
        pr_fm["pipeline_version"] = current_version
        pr_fm["pipeline_step_fingerprint"] = current_fingerprint
        pr_fm["modified"] = TODAY
        pr_fm["modified_by"] = SCRIPT_NAME
        write_vault_entry(pr_fm["uid"], pr_fm, pr.get("body", ""))
        return events, derive_state(events)

    print(f"[INFO] B1 auto-heal: def {pipeline_uid!r} updated {recorded_version!r} → {current_version!r}; "
          f"declaring {len(new_steps)} new step(s): {new_steps}", file=sys.stderr)

    # Build step declarations from current def (v3.0 schema defaults)
    contract_parent = None
    for ev in events:
        if ev.get("event") == "activation_contract_locked":
            contract_parent = ev.get("span_id")
            break

    for step_uid in new_steps:
        sfm = nodes.get(step_uid, {})
        step_data = {
            "step_id": step_uid,
            "step_owner_role": sfm.get("step_owner_role") or "unspecified",
            "step_verifier_role": sfm.get("step_verifier_role") or "same-as-executor",
            "verification_class": bool(sfm.get("verification_class", False)),
            "depends_on_steps": sfm.get("depends_on_steps") or [],
            "exit_criteria": sfm.get("exit_criteria") or [],
            "trust_level": sfm.get("trust_level") or pipeline_def["frontmatter"].get("default_trust_gradient") or "auto-with-verification",
            "retry_policy": sfm.get("retry_policy") or {"max_retries": 0, "backoff": "linear"},
            "timeout_hours": sfm.get("timeout_hours") or 24,
            "compensation_step_id": sfm.get("compensation_step_id"),
            "instructions_ref": sfm.get("instructions_ref"),
            "auto_healed": True,  # provenance marker
        }
        ev = make_event("step_declared", SCRIPT_NAME,
                        step=step_uid,
                        trace_id=activation_uid,
                        parent_span_id=contract_parent,
                        data=step_data)
        append_event(run_folder, ev)

    # Update pipeline-run frontmatter to record new version + fingerprint
    pr_fm["pipeline_version"] = current_version
    pr_fm["pipeline_step_fingerprint"] = current_fingerprint
    pr_fm["modified"] = TODAY
    pr_fm["modified_by"] = SCRIPT_NAME
    write_vault_entry(pr_fm["uid"], pr_fm, pr.get("body", ""))

    # Re-read events after appending + re-derive state
    updated_events = read_events(run_folder)
    updated_state = derive_state(updated_events)

    # d3a58cdf item 3 — sync run.state.json immediately after the heal mutates
    # run.jsonl, so the derived cache is never stale relative to the event log.
    # Without this, a crash between load_run() and the enclosing action's final
    # write_run_state_json() leaves the cache showing eligible_steps:[] against
    # a run.jsonl that now has the new step_declared events.
    write_run_state_json(run_folder, pr_fm, updated_state, activation_uid)

    return updated_events, updated_state


def load_run(activation_uid: str) -> tuple[dict, dict, Path, list[dict], dict]:
    """Returns (activation_entry, pipeline_run_entry, run_folder, events, state).

    Includes B1 auto-heal: if pipeline def was amended since bootstrap, new steps
    are declared transparently before returning to the caller.
    """
    activation = read_vault_entry(activation_uid)
    if activation is None:
        raise ValidationError(f"activation_uid {activation_uid!r} does not resolve")
    pr = find_pipeline_run_for(activation_uid)
    if pr is None:
        raise ValidationError(f"no pipeline-run entry yet for activation {activation_uid!r}; run --action bootstrap first")
    run_folder = run_folder_for(pr["frontmatter"])
    events = read_events(run_folder)
    # B1 auto-heal: detect + reconcile stale def-snapshot silently
    events, state = _auto_heal_stale_def(pr, run_folder, events, activation_uid)
    return activation, pr, run_folder, events, state


def actor_uid_or_default(args, fallback: str) -> str:
    return getattr(args, "actor", None) or fallback


# ---------------------- per-action handlers ----------------------

def action_step_start(activation_uid: str, step_uid: str, actor: str) -> str:
    activation, pr, run_folder, events, state = load_run(activation_uid)
    decls = get_step_declarations(events)
    if step_uid not in decls:
        raise ValidationError(f"step {step_uid!r} not in activation contract")
    eligible = compute_eligible_steps(state, decls)
    if step_uid not in eligible:
        raise ContractError(
            f"step {step_uid!r} not eligible (status={state['step_status'].get(step_uid)!r}; "
            f"deps not satisfied or already started)")
    decl = decls[step_uid]
    # v1.46.0.1 fix (V48 finding 2026-05-20): approval-required steps gate on
    # pause_resumed_pending. First step-start invocation writes pause_started;
    # after pause_resumed clears the gate, the next step-start fires step_started.
    if decl.get("trust_level") == "approval-required" and step_uid not in state.get("pause_resumed_pending", set()):
        ev = make_event("pause_started", actor,
                        trace_id=activation_uid,
                        parent_span_id=find_event_span(events, "step_declared", step_uid),
                        data={"reason": "human-confirmation-required", "step": step_uid})
        append_event(run_folder, ev)
        write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
        return f"paused:{step_uid}"
    parent = find_event_span(events, "step_declared", step_uid)
    ev = make_event("step_started", actor, step=step_uid,
                    trace_id=activation_uid, parent_span_id=parent,
                    data={"step_owner_role": decl.get("step_owner_role")})
    append_event(run_folder, ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    return f"started:{step_uid}"


def action_step_complete(activation_uid: str, step_uid: str, artifact_links: list[str], actor: str,
                          natural_verdict: str | None = None) -> str:
    activation, pr, run_folder, events, state = load_run(activation_uid)
    if state["step_status"].get(step_uid) != "started":
        raise ContractError(f"step {step_uid!r} not in 'started' status (got {state['step_status'].get(step_uid)!r})")
    parent = find_event_span(events, "step_started", step_uid)
    data: dict = {"artifact_links": artifact_links}
    decls = get_step_declarations(events)
    decl = decls.get(step_uid, {})

    # v1.63 verification_command: for verification_class:true steps that declare a
    # verification_command, the engine RUNS the command and derives the verdict from
    # the exit code (0=pass, nonzero=fail). Agent-supplied --natural-verdict is
    # refused for these steps — the command output IS the verdict.
    # Closes the vc:true self-attestation hatch (Argus A91 2026-06-01, f0ae00bf).
    # Analogous to B4 closing the vc:false --verification-data-stdin hatch.
    verification_command = decl.get("verification_command")
    # v1.66 S1 fix (a): refuse --natural-verdict on ALL vc:true steps, not just
    # command-bearing ones. A vc:true step's verdict must come from a real source
    # (verification_command exit code, verification_receipt, or accepted human_signoff)
    # — never an agent-typed --natural-verdict. Generalizes the v1.63 command-only
    # refusal (Argus A102 ed04d931 §verdict-state-machine).
    if decl.get("verification_class") and natural_verdict is not None:
        raise ContractError(
            f"step {step_uid!r}: --natural-verdict refused for ALL vc:true steps. "
            f"Verdict must come from a real source: verification_command exit code, "
            f"verification_receipt, or accepted human_signoff. "
            f"(v1.66 S1 state-machine fix (a); ed04d931)"
        )
    if decl.get("verification_class") and verification_command:
        # Run the verification command; derive verdict from exit code
        # v1.66 S1 (ed04d931): named-handle substitution + per-step verdict_cwd
        import shlex as _shlex
        _vc_str = str(verification_command)
        if "{" in _vc_str:
            _pr = find_pipeline_run_for(activation_uid)
            _ctx = build_run_context_uids(_pr, activation_uid) if _pr else {"activation": activation_uid}
            for _h, _v in _ctx.items():
                if _v:
                    _vc_str = _vc_str.replace("{" + _h + "}", str(_v))
        cmd_parts = _shlex.split(_vc_str)
        _verdict_cwd = str(decl.get("verdict_cwd") or VAULT_ROOT)
        try:
            cmd_result = subprocess.run(
                [sys.executable] + cmd_parts if cmd_parts[0].endswith(".py") else cmd_parts,
                capture_output=True, text=True, timeout=120,
                cwd=_verdict_cwd,
            )
            cmd_verdict = "pass" if cmd_result.returncode == 0 else "fail"
        except subprocess.TimeoutExpired:
            cmd_verdict = "error"
            cmd_result = None
        except Exception as e:
            cmd_verdict = "error"
            cmd_result = None
        data["natural_verdict"] = cmd_verdict
        data["verification_command_exit_code"] = getattr(cmd_result, "returncode", None)
        data["verification_command_stdout_tail"] = (
            (cmd_result.stdout or "")[-300:] if cmd_result else ""
        )
        print(f"  [verification_command] {step_uid}: {cmd_verdict} "
              f"(exit={getattr(cmd_result, 'returncode', '?')})", file=sys.stderr)
        # d3a9c1f7 full fix: run behaviors_covered → per-behavior test_executed → real
        # test_aggregate with pass_count/fail_count. Replaces the degenerate total:1 emit
        # from the T13 partial fix. Two sources for behaviors_covered:
        #   (a) inline on step declaration (decl.get("behaviors_covered"))
        #   (b) triggered_test_spec document (test-pipeline path: 05d9ecc5 run-test-substrate)
        _behaviors = list(decl.get("behaviors_covered") or [])
        if not _behaviors:
            _pr2 = find_pipeline_run_for(activation_uid)
            if _pr2:
                _ctx2 = build_run_context_uids(_pr2, activation_uid)
                _ts_uid = _ctx2.get("triggered_test_spec")
                if _ts_uid:
                    _ts_entry = read_vault_entry(_ts_uid)
                    if _ts_entry:
                        _behaviors = list(_ts_entry["frontmatter"].get("behaviors_covered") or [])
        if _behaviors:
            _behavior_results = []
            for _bi, _b in enumerate(_behaviors):
                _vmethod = _b.get("verification_method", "unknown")
                _bdesc = _b.get("behavior_description", f"behavior_{_bi + 1}")
                _bpath = str(_b.get("test_substrate_path") or "")
                if _vmethod == "machine_executable_script" and _bpath:
                    _bpath_abs = Path(_bpath) if Path(_bpath).is_absolute() else VAULT_ROOT / _bpath
                    try:
                        _bres = subprocess.run(
                            [sys.executable, str(_bpath_abs)] if _bpath_abs.suffix == ".py"
                            else [str(_bpath_abs)],
                            capture_output=True, text=True, timeout=60,
                            cwd=str(VAULT_ROOT),
                        )
                        _bverdict = "pass" if _bres.returncode == 0 else "fail"
                        _bdata = {
                            "behavior_index": _bi + 1,
                            "behavior_description": _bdesc,
                            "verification_method": _vmethod,
                            "verdict": _bverdict,
                            "exit_code": _bres.returncode,
                            "stdout_tail": (_bres.stdout or "")[-300:],
                            "stderr_tail": (_bres.stderr or "")[-200:],
                            "test_substrate_path": _bpath,
                        }
                    except subprocess.TimeoutExpired:
                        _bverdict = "error"
                        _bdata = {"behavior_index": _bi + 1, "behavior_description": _bdesc,
                                  "verification_method": _vmethod, "verdict": "error",
                                  "rationale": "subprocess timeout (60s)", "test_substrate_path": _bpath}
                    except Exception as _be:
                        _bverdict = "error"
                        _bdata = {"behavior_index": _bi + 1, "behavior_description": _bdesc,
                                  "verification_method": _vmethod, "verdict": "error",
                                  "rationale": str(_be), "test_substrate_path": _bpath}
                else:
                    # Non-machine-executable: deterministic_assertion/structural_check/
                    # agentic_review/manual_walk require agent dispatch — emit skipped.
                    _bverdict = "skipped"
                    _bdata = {
                        "behavior_index": _bi + 1,
                        "behavior_description": _bdesc,
                        "verification_method": _vmethod,
                        "verdict": "skipped",
                        "rationale": f"{_vmethod} not auto-executed by engine; requires agent dispatch",
                        "test_substrate_path": _bpath,
                    }
                _behavior_results.append({"behavior_description": _bdesc, "verdict": _bverdict})
                _te_ev = make_event("test_executed", actor, step=step_uid,
                                    trace_id=activation_uid, data=_bdata)
                append_event(run_folder, _te_ev)
                print(f"  [behavior {_bi + 1}/{len(_behaviors)}] {_bverdict}: {_bdesc[:70]}",
                      file=sys.stderr)
            _pass_count = sum(1 for r in _behavior_results if r["verdict"] == "pass")
            _fail_count = sum(1 for r in _behavior_results if r["verdict"] == "fail")
            _agg_ev = make_event("test_aggregate", actor, step=step_uid,
                                 trace_id=activation_uid,
                                 data={"pass_count": _pass_count, "fail_count": _fail_count,
                                       "total": len(_behavior_results),
                                       "verdict": "pass" if _fail_count == 0 else "fail",
                                       "behaviors": _behavior_results})
            append_event(run_folder, _agg_ev)
        else:
            # No behaviors_covered: fall back to degenerate single-command aggregate for
            # vc:true steps that have a verification_command but no behavior list.
            _agg_passed = 1 if cmd_verdict == "pass" else 0
            _agg_ev = make_event("test_aggregate", actor, step=step_uid,
                                 trace_id=activation_uid,
                                 data={"passed": _agg_passed, "total": 1,
                                       "verdict": cmd_verdict,
                                       "cmd_exit_code": data["verification_command_exit_code"]})
            append_event(run_folder, _agg_ev)
    elif decl.get("verification_class") and natural_verdict:
        data["natural_verdict"] = natural_verdict
    ev = make_event("step_completed", actor, step=step_uid,
                    trace_id=activation_uid, parent_span_id=parent, data=data)
    append_event(run_folder, ev)

    # The produce-step verification command mints before this step_completed
    # event exists. Refresh the key from the durable post-completion record so
    # the runtime does not invalidate its own fingerprint immediately.
    if step_uid == "8654900a" and data.get("natural_verdict") == "pass":
        try:
            from lib.release_authorization import mint_key
            mint_key(activation_uid, "produce-release-folder")
        except Exception as exc:
            raise ContractError(
                f"produce-release-folder completed but post-completion key mint failed: {exc}"
            ) from exc

    # E2 fix (v1.53): verification_class:false steps are terminal at completed.
    # Auto-emit verification_receipt verdict:pass — no separate verify-step required.
    # Option b per V52 lean: completed IS the verified state when no verification gate exists.
    if not decl.get("verification_class", True):
        # vc-conditional (v1.63 Argus A92 GO event 812): B1 (empty-criteria FAIL) gates
        # vc:true steps only. vc:false steps auto-receipt pass regardless of criteria —
        # they have no verification gate, so criteria are not a ship-condition for them.
        auto_criteria = decl.get("exit_criteria") or []
        auto_verdict = "pass"
        auto_rationale = (
            "verification_class:false — completed is terminal; auto-receipt pass."
            if not auto_criteria else
            "verification_class:false — completed is terminal; criteria declared, auto-receipt pass."
        )
        ev_receipt = make_event("verification_receipt", actor, step=step_uid,
                                trace_id=activation_uid, parent_span_id=ev["span_id"],
                                data={
                                    "verifier_role_resolved": "same-as-executor",
                                    "verdict": auto_verdict,
                                    "per_criterion": [],
                                    "rubric_scores": {"exit_criteria_coverage": 1.0 if auto_criteria else 0.0},
                                    "overall_rationale": auto_rationale,
                                })
        append_event(run_folder, ev_receipt)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    # C.5 — Stream C auto-emission: tropo.pipeline.step_completed (v1.58)
    try:
        _sp = Path(__file__).resolve().parents[2] / ".tropo" / "scripts"
        import sys as _sys
        if str(_sp) not in _sys.path:
            _sys.path.insert(0, str(_sp))
        from lib.event_emitter import auto_emit
        auto_emit("tropo.pipeline.step_completed", "/tools/pipeline-runtime", "123e12e7",
                  lifecycle="ephemeral",
                  data={"activation_uid": activation_uid, "step_uid": step_uid})
    except Exception:
        pass
    return f"completed:{step_uid}"


def action_verify_step(activation_uid: str, step_uid: str, actor: str) -> str:
    # B4 (v1.62): --verification-data-stdin self-attestation hatch removed. Criteria are
    # always engine-computed against substrate — never accepted as agent-authored prose.
    activation, pr, run_folder, events, state = load_run(activation_uid)
    if state["step_status"].get(step_uid) not in ("completed",):
        raise ContractError(f"step {step_uid!r} not in 'completed' status (got {state['step_status'].get(step_uid)!r})")
    decls = get_step_declarations(events)
    decl = decls.get(step_uid, {})
    parent = find_event_span(events, "step_completed", step_uid)
    if True:  # always engine-computed (self-attestation hatch removed v1.62 B4)
        # vc-conditional (v1.63 Argus A93 event 865): vc:false steps are not
        # verification-gated — verify-step auto-PASSes them, same as step_complete.
        # B1 (empty-criteria FAIL) gates vc:true steps only.
        if not decl.get("verification_class"):
            data = {
                "verifier_role_resolved": "same-as-executor",
                "verdict": "pass",
                "per_criterion": [],
                "rubric_scores": {"exit_criteria_coverage": 1.0},
                "overall_rationale": "verification_class:false — step is not verification-gated; "
                                     "verify-step auto-passes (vc-conditional, v1.63).",
            }
        else:
            # Same-as-executor: compute per-criterion verdicts against substrate snapshot
            criteria = decl.get("exit_criteria") or []
            # B1 (v1.62): empty exit_criteria → FAIL. A step without declared criteria
            # cannot be verified — it was never specified. Hollow criteria are a pre-condition
            # violation, not a pass. Closes the declarative-not-verified failure class.
            if not criteria:
                data = {
                    "verifier_role_resolved": decl.get("step_verifier_role") or "same-as-executor",
                    "verdict": "fail",
                    "per_criterion": [],
                    "rubric_scores": {"exit_criteria_coverage": 0.0},
                    "overall_rationale": "FAIL — exit_criteria is empty; step was never specified. "
                                         "Populate exit_criteria DSL before verification (v1.62 B1).",
                }
            else:
                # Fix (1): pass run_events so human: and aggregate: criteria can dispatch
                # Fix (2): honor verification_command on vc:true steps in verify-step
                # (Vela V56 00000662 2026-06-01 — same dispatch as action_step_complete)
                verification_command = decl.get("verification_command")
                if verification_command:
                    # v1.66 S1 (ed04d931): named-handle substitution + per-step verdict_cwd
                    import shlex as _shlex
                    _vc_str = str(verification_command)
                    if "{" in _vc_str:
                        _ctx2 = build_run_context_uids(pr, activation_uid)
                        for _h, _v in _ctx2.items():
                            if _v:
                                _vc_str = _vc_str.replace("{" + _h + "}", str(_v))
                    cmd_parts = _shlex.split(_vc_str)
                    _verdict_cwd2 = str(decl.get("verdict_cwd") or VAULT_ROOT)
                    try:
                        cmd_result = subprocess.run(
                            [sys.executable] + cmd_parts if cmd_parts[0].endswith(".py") else cmd_parts,
                            capture_output=True, text=True, timeout=120, cwd=_verdict_cwd2,
                        )
                        cmd_verdict = "pass" if cmd_result.returncode == 0 else "fail"
                        per_criterion = [{
                            "criterion": f"verification_command: {verification_command}",
                            "verdict": cmd_verdict,
                            "rationale": f"exit={cmd_result.returncode}; stdout={cmd_result.stdout[-200:] if cmd_result.stdout else ''}",
                        }]
                    except Exception as e:
                        cmd_verdict = "error"
                        per_criterion = [{"criterion": f"verification_command: {verification_command}",
                                          "verdict": "error", "rationale": str(e)}]
                    total = 1
                    passes = 1 if cmd_verdict == "pass" else 0
                    data = {
                        "verifier_role_resolved": "verification_command",
                        "verdict": cmd_verdict,
                        "per_criterion": per_criterion,
                        "rubric_scores": {"exit_criteria_coverage": passes / total},
                        "overall_rationale": f"verification_command: {cmd_verdict}",
                    }
                else:
                    ctx = build_run_context_uids(pr, activation_uid)
                    snapshot = build_snapshot(criteria, ctx)
                    per_criterion = [evaluate_criterion(c, ctx, snapshot, run_events=events)
                                     for c in criteria]
                    verdict = "pass"
                    if any(p["verdict"] == "error" for p in per_criterion):
                        verdict = "error"
                    elif any(p["verdict"] == "fail" for p in per_criterion):
                        verdict = "fail"
                    total = len(per_criterion)
                    passes = sum(1 for p in per_criterion if p["verdict"] == "pass")
                    rubric = {"exit_criteria_coverage": passes / total}
                    data = {
                        "verifier_role_resolved": decl.get("step_verifier_role") or "same-as-executor",
                        "verdict": verdict,
                        "per_criterion": per_criterion,
                        "rubric_scores": rubric,
                        "overall_rationale": f"{passes}/{total} criteria pass",
                    }
    ev = make_event("verification_receipt", actor, step=step_uid,
                    trace_id=activation_uid, parent_span_id=parent, data=data)
    append_event(run_folder, ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    return data.get("verdict", "unknown")


def action_step_fail(activation_uid: str, step_uid: str, actor: str, failure_phase: str,
                     failure_class: str, disposition: str, error_detail: str,
                     retry_count: int = 0) -> str:
    activation, pr, run_folder, events, state = load_run(activation_uid)
    parent = find_event_span(events, "step_started", step_uid)
    data = {
        "failure_phase": failure_phase,
        "failure_class": failure_class,
        "disposition": disposition,
        "retry_count": retry_count,
        "error_detail": error_detail,
    }
    ev = make_event("step_failed", actor, step=step_uid,
                    trace_id=activation_uid, parent_span_id=parent, data=data)
    append_event(run_folder, ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    return f"failed:{step_uid}:{disposition}"


def action_skip_request(activation_uid: str, step_uid: str, actor: str, reason: str) -> str:
    activation, pr, run_folder, events, state = load_run(activation_uid)
    parent = (find_event_span(events, "step_started", step_uid)
              or find_event_span(events, "step_declared", step_uid))
    ev = make_event("skip_request", actor, step=step_uid,
                    trace_id=activation_uid, parent_span_id=parent,
                    data={"step_id": step_uid, "requested_by": actor, "reason": reason})
    append_event(run_folder, ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    return f"skip_requested:{step_uid}"


def action_authorize_skip(activation_uid: str, step_uid: str, authorized_by: str,
                          conditions: str, actor: str) -> str:
    activation, pr, run_folder, events, state = load_run(activation_uid)
    # Validate authorizer resolves to type:principal
    authorizer = read_vault_entry(authorized_by)
    if authorizer is not None:
        atype = authorizer["frontmatter"].get("type")
        if atype not in ("principal", "human"):
            raise SkipAuthError(f"authorized_by {authorized_by!r} resolves to type:{atype!r}, "
                                f"not type:principal (or type:human at v1.47.0+)")
    parent = find_event_span(events, "skip_request", step_uid)
    ev = make_event("skip_authorization", actor, step=step_uid,
                    trace_id=activation_uid, parent_span_id=parent,
                    data={"step_id": step_uid, "authorized_by": authorized_by, "conditions": conditions})
    append_event(run_folder, ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    return f"skip_authorized:{step_uid}"


def action_apply_skip(activation_uid: str, step_uid: str, actor: str) -> str:
    activation, pr, run_folder, events, state = load_run(activation_uid)
    auth_span = state["skip_authorizations"].get(step_uid)
    if auth_span is None:
        raise SkipAuthError(f"no prior skip_authorization event for step {step_uid!r}")
    ev = make_event("step_skipped", actor, step=step_uid,
                    trace_id=activation_uid, parent_span_id=auth_span,
                    data={"disposition": "skip_with_authorization",
                          "skip_authorization_span_id": auth_span})
    append_event(run_folder, ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    return f"skipped:{step_uid}"


def action_pause(activation_uid: str, reason: str, actor: str) -> str:
    activation, pr, run_folder, events, state = load_run(activation_uid)
    ev = make_event("pause_started", actor,
                    trace_id=activation_uid,
                    parent_span_id=events[-1]["span_id"] if events else None,
                    data={"reason": reason})
    append_event(run_folder, ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    return "paused"


def action_resume(activation_uid: str, confirmation_granted_by: str | None, actor: str) -> str:
    activation, pr, run_folder, events, state = load_run(activation_uid)
    if state["run_status"] != "paused":
        raise ContractError(f"run status is {state['run_status']!r}, not paused")
    # v1.46.0.1 fix (V48 finding 2026-05-20): walk back to the most recent
    # pause_started so the pause_resumed event explicitly carries the step UID
    # being approved. Both the event's top-level `step` field and `data.step`
    # populate, so the state-derivation walk can resolve the approval without
    # a separate event-index lookup.
    last_pause = None
    for ev_prior in reversed(events):
        if ev_prior.get("event") == "pause_started":
            last_pause = ev_prior
            break
    parent = last_pause["span_id"] if last_pause else None
    paused_step = (last_pause.get("data") or {}).get("step") if last_pause else None

    # v1.66 S1 fix (c): require a human_signoff event before resuming an
    # approval-required step. An agent cannot self-approve — the signing entity
    # must differ from the caller, and a human_signoff with verdict:accepted must
    # exist in the run events. Closes the paper-gate hole where any agent could
    # resume an approval-required step with 0 real signoffs (Argus A102 ed04d931 §c).
    if paused_step:
        decls = get_step_declarations(events)
        paused_decl = decls.get(paused_step, {})
        if paused_decl.get("trust_level") == "approval-required":
            if not confirmation_granted_by:
                raise ContractError(
                    f"step {paused_step!r} is trust_level:approval-required; "
                    f"--confirmation-granted-by <actor> is required to resume. "
                    f"(v1.66 S1 fix (c); ed04d931)"
                )
            # C: resolve to canonical principal UIDs — closes two-label spoof + unregistered bypass
            granter_uid = _resolve_principal_uid(confirmation_granted_by, VAULT_ROOT)
            caller_uid = _resolve_principal_uid(actor, VAULT_ROOT)
            if granter_uid is None:
                raise ContractError(
                    f"step {paused_step!r} is trust_level:approval-required; "
                    f"confirmation_granted_by {confirmation_granted_by!r} does not resolve "
                    f"to a registered type:principal vault entry — only registered principals may sign. "
                    f"(v1.66 S1 consolidated fix; ed04d931)"
                )
            if granter_uid is not None and granter_uid == caller_uid:
                raise ContractError(
                    f"step {paused_step!r} is trust_level:approval-required; "
                    f"self-approval refused: {confirmation_granted_by!r} and {actor!r} "
                    f"resolve to the same principal ({granter_uid}). "
                    f"(v1.66 S1 fix (c/C); ed04d931)"
                )
            elif confirmation_granted_by == actor:
                raise ContractError(
                    f"step {paused_step!r} is trust_level:approval-required; "
                    f"self-approval refused (confirmation_granted_by must differ from actor). "
                    f"(v1.66 S1 fix (c); ed04d931)"
                )
            # Emit human_signoff event BEFORE pause_resumed (the gate record)
            signoff_ev = make_event("human_signoff", confirmation_granted_by,
                                    step=paused_step,
                                    trace_id=activation_uid, parent_span_id=parent,
                                    data={"verdict": "accepted",
                                          "step": paused_step,
                                          "signed_by": confirmation_granted_by,
                                          "signer_principal_uid": granter_uid})
            append_event(run_folder, signoff_ev)
    data: dict = {}
    if confirmation_granted_by:
        data["confirmation_granted_by"] = confirmation_granted_by
    if paused_step:
        data["step"] = paused_step
    ev = make_event("pause_resumed", actor,
                    step=paused_step,
                    trace_id=activation_uid, parent_span_id=parent, data=data)
    append_event(run_folder, ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    return "resumed"


def action_terminal_verify(activation_uid: str, actor: str) -> str:
    """v1.46.0 minimum-viable: inline verifier walks log + emits verifier_findings.
    Full sa.pipeline-verify dispatch defers to terminal-state-verifier substrate."""
    activation, pr, run_folder, events, state = load_run(activation_uid)
    decls = get_step_declarations(events)
    gaps = []
    for step_id in decls:
        status = state["step_status"].get(step_id)
        if status not in ("verified", "skipped"):
            gaps.append({"step_id": step_id, "status": status})
    verdict = "complete" if not gaps else "incomplete_gaps"
    # If all gaps are skipped-with-auth, downgrade to incomplete_with_authorized_skips
    if all(state["step_status"].get(g["step_id"]) == "skipped"
           and g["step_id"] in state["skip_authorizations"] for g in gaps) and gaps:
        verdict = "incomplete_with_authorized_skips"
    data = {
        "verdict": verdict,
        "gaps": gaps,
        "rubric_scores": {
            "step_completion_coverage": (len(decls) - len(gaps)) / max(len(decls), 1),
        },
    }
    parent = events[-1]["span_id"] if events else None
    ev = make_event("verifier_findings", actor,
                    trace_id=activation_uid, parent_span_id=parent, data=data)
    append_event(run_folder, ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    return verdict


def action_human_signoff(activation_uid: str, verdict: str, notes: str, actor: str,
                          step_uid: str | None = None) -> str:
    """Record a human signoff on a pipeline run.

    v1.66 S1 full verifier-independence (Argus A102 ed04d931 §A/B/C/D):
    A. Read activated_by from ACTIVATION entry (not pipeline-run frontmatter).
    B. Require step_uid — scope-less signoffs rejected.
    C. Resolve actor + executor to canonical principal UIDs — closes two-label spoof.
    D. Any registered type:principal that is NOT the executor may sign.
    """
    if verdict not in ("accepted", "accepted_with_exceptions", "rejected"):
        raise ContractError(f"invalid signoff verdict {verdict!r}")
    # B: require step_uid
    if not step_uid:
        raise ContractError(
            "human_signoff requires --step <step_uid>; scope-less signoffs rejected. "
            "(v1.66 S1 fix B; ed04d931)"
        )
    activation, pr, run_folder, events, state = load_run(activation_uid)
    # A: read activated_by from the ACTIVATION entry, not the pipeline-run entry
    afm = activation["frontmatter"] if activation else {}
    activated_by = afm.get("activated_by") or pr["frontmatter"].get("activated_by") or ""
    # C: resolve both actor and executor to canonical principal UIDs
    signer_uid = _resolve_principal_uid(actor, VAULT_ROOT)
    executor_uid = _resolve_principal_uid(activated_by, VAULT_ROOT)
    # D: signer must be a registered principal
    if signer_uid is None:
        raise ContractError(
            f"human-signoff actor {actor!r} does not resolve to a registered type:principal "
            f"vault entry; only registered principals may sign. (v1.66 S1 fix D; ed04d931)"
        )
    # C+A: reject if same canonical identity as executor (self-sign via any label)
    if signer_uid == executor_uid:
        raise ContractError(
            f"human-signoff refused: {actor!r} (resolved: {signer_uid}) is the pipeline "
            f"executor ({activated_by}, resolved: {executor_uid}); signoff must be independent. "
            f"(v1.66 S1 fix A/C; ed04d931)"
        )
    parent = find_event_span(events, "verifier_findings")
    ev = make_event("human_signoff", actor,
                    step=step_uid,
                    trace_id=activation_uid, parent_span_id=parent,
                    data={"signed_by": actor, "signer_principal_uid": signer_uid,
                          "verdict": verdict, "notes": notes, "step": step_uid})
    append_event(run_folder, ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)
    return f"signoff:{verdict}"


def check_triggered_pipeline_completion(activation_entry: dict) -> tuple[bool, str]:
    """Returns (allowed, reason). Called before action_complete_workflow permits close.

    Per v1.51 three-pipeline coupling: dev-pipeline activation close is blocked until
    all triggered doc-pipeline + test-pipeline activations reach status:done.
    Legacy cycles without dev_spec_uid are grandfathered (WARN, allow close).
    """
    fm = activation_entry["frontmatter"]
    dev_spec_uid = fm.get("dev_spec_uid")
    if not dev_spec_uid:
        print("[WARN] complete-workflow: no dev_spec_uid on activation; "
              "legacy cycle grandfathered per dev-spec.capsule Rule 7", file=sys.stderr)
        return True, "no-dev-spec-grandfathered"

    dev_spec = read_vault_entry(dev_spec_uid)
    if dev_spec is None:
        print(f"[WARN] complete-workflow: dev_spec_uid {dev_spec_uid!r} does not resolve; "
              "skip coupling check", file=sys.stderr)
        return True, "dev-spec-unresolvable"

    dsf = dev_spec["frontmatter"]
    doc_acts = dsf.get("triggered_doc_activation_uids") or []
    test_acts = dsf.get("triggered_test_activation_uids") or []
    all_triggered = list(doc_acts) + list(test_acts)

    if not all_triggered:
        # v1.66 S5 (e26935da): replace blanket-allow with cascade_disposition enforcement.
        # A retroactively-anchored cycle (empty triggers) must prove docs+tests via a
        # structured cascade_disposition. Pre-S5 grandfather (target_release < 1.66.0)
        # exempts from independence requirement (executor-of-record attestation OK).
        _S5_THRESHOLD = (1, 66, 0)
        try:
            _tr = str(dsf.get("target_release") or "0.0.0").lstrip("v")
            _tr_parts = tuple(int(x) for x in _tr.split("."))
            _is_pre_s5 = _tr_parts < _S5_THRESHOLD
        except (ValueError, TypeError):
            _is_pre_s5 = True  # unparseable → be conservative, grandfather

        _cascade = dsf.get("cascade_disposition")
        if _cascade is None:
            _msg = (
                f"retroactive-anchor: dev-spec {dev_spec_uid!r} has empty "
                f"triggered_*_activation_uids and no cascade_disposition; "
                f"close is BLOCKED until cascade_disposition is declared "
                f"(15c085de; e26935da S5)"
            )
            print(f"[BLOCKED] {_msg}", file=sys.stderr)
            return False, _msg

        # Resolve executor identity for independence check
        _activation_fm = activation_entry["frontmatter"] if activation_entry else {}
        _executor_uid = _resolve_principal_uid(_activation_fm.get("activated_by") or "", VAULT_ROOT)

        def _check_leg(leg_name: str) -> tuple[bool, str]:
            """Validate one cascade_disposition leg (doc or test). Returns (ok, reason)."""
            leg = _cascade.get(leg_name) if isinstance(_cascade, dict) else None
            if leg is None:
                # Missing leg: if the other leg covers it, OK; otherwise block
                return False, (f"cascade_disposition.{leg_name} missing; "
                               f"every cascade leg (doc + test) must be declared")
            mode = leg.get("mode") if isinstance(leg, dict) else None
            if mode == "triggered":
                # triggered mode with empty activation list = contradiction
                leg_acts = dsf.get(f"triggered_{leg_name}_activation_uids") or []
                if not leg_acts:
                    return False, (f"cascade_disposition.{leg_name}.mode=triggered "
                                   f"but triggered_{leg_name}_activation_uids is empty — contradiction")
                return True, "triggered"
            elif mode == "attested":
                evidence_ref = leg.get("evidence_ref") if isinstance(leg, dict) else None
                attested_by = leg.get("attested_by") if isinstance(leg, dict) else None
                if not evidence_ref:
                    return False, (f"cascade_disposition.{leg_name}.mode=attested "
                                   f"but evidence_ref missing")
                if not attested_by:
                    return False, (f"cascade_disposition.{leg_name}.mode=attested "
                                   f"but attested_by missing")
                _attester_uid = _resolve_principal_uid(str(attested_by), VAULT_ROOT)
                if _attester_uid is None:
                    return False, (f"cascade_disposition.{leg_name}.attested_by "
                                   f"{attested_by!r} does not resolve to a registered principal")
                if not _is_pre_s5 and _executor_uid and _attester_uid == _executor_uid:
                    return False, (f"cascade_disposition.{leg_name}: self-attestation refused "
                                   f"— attested_by {attested_by!r} resolves to executor "
                                   f"({_executor_uid}); independence required for v1.66+")
                return True, f"attested:{attested_by}"
            else:
                return False, (f"cascade_disposition.{leg_name}.mode={mode!r} unrecognized; "
                               f"must be triggered or attested")

        _ok_doc, _reason_doc = _check_leg("doc")
        _ok_test, _reason_test = _check_leg("test")
        if not _ok_doc:
            print(f"[BLOCKED] cascade-close-gate doc: {_reason_doc}", file=sys.stderr)
            return False, f"cascade-close-gate doc: {_reason_doc}"
        if not _ok_test:
            print(f"[BLOCKED] cascade-close-gate test: {_reason_test}", file=sys.stderr)
            return False, f"cascade-close-gate test: {_reason_test}"
        return True, f"cascade-attested (doc:{_reason_doc} test:{_reason_test})"

    for act_uid in all_triggered:
        act_entry = read_vault_entry(act_uid)
        if act_entry is None:
            return False, f"triggered activation {act_uid!r} does not resolve"
        fmf = act_entry["frontmatter"]
        # 99e52c18 state-disambiguate fix (L1904 2026-06-09): accept status:retired
        # (the canonical activation terminal) AND the status-terminal set as complete.
        # After the state-disambiguate migration, state:done will be replaced by state:active
        # + status:done — so gating on state=="done" would block ALL completed activations.
        # Gate on STATUS-terminal: retired / done / archived cover all legitimate completions.
        # status:retired (249 activations) IS the canonical activation terminal — MUST accept it.
        _terminal_statuses = {"done", "retired", "archived", "shipped", "closed", "complete"}
        if (fmf.get("status") or "").lower() not in _terminal_statuses:
            return False, (f"triggered activation {act_uid!r} not complete "
                           f"(status: {fmf.get('status')!r}, state: {fmf.get('state')!r})")

    # E7 (v1.53): close-gate enforcement — doc-pipeline activations must have orpheus_disposition_signoff
    # on their linked doc-spec before dev-pipeline can complete.
    # WARN-only at v1.53 (grace cycle per doc-spec.capsule v1.0.1 Check 14); ERROR ratchet at v1.54.
    for act_uid in doc_acts:
        act_entry = read_vault_entry(act_uid)
        if act_entry is None:
            continue
        act_fm = act_entry["frontmatter"]
        # Find the linked doc-spec (triggered_doc_spec_uids on the dev-spec)
        if dev_spec_uid:
            ds_entry = read_vault_entry(dev_spec_uid)
            if ds_entry:
                for spec_uid in (ds_entry["frontmatter"].get("triggered_doc_spec_uids") or []):
                    spec_entry = read_vault_entry(spec_uid)
                    if spec_entry is None:
                        continue
                    sfm = spec_entry["frontmatter"]
                    if sfm.get("type") == "doc-spec" and sfm.get("stage") == "done":
                        if not sfm.get("orpheus_disposition_signoff"):
                            print(
                                f"[WARN] E7 close-gate: doc-spec {spec_uid!r} stage:done but "
                                f"orpheus_disposition_signoff missing "
                                f"(WARN at v1.53; ERROR ratchet v1.54+)",
                                file=sys.stderr,
                            )
                            # v1.53 grace: warn but don't block

    return True, "all-triggered-done"


def _auto_bootstrap_triggered_pipeline(
    triggered_activation_uid: str,
    triggered_pipeline_uid: str,
    actor: str,
) -> str:
    """E6 (v1.53) — auto-write pipeline-run.capsule instance for triggered doc/test pipelines.

    Dev-pipeline gets pipeline-run substrate via explicit operator bootstrap call.
    Triggered doc-pipeline + test-pipeline activations get it automatically at trigger-step
    fire time — no operator action required. Mirrors action_bootstrap without contract negotiation.

    Returns the minted pipeline-run UID, or "" on failure (non-fatal; logged to stderr).
    """
    try:
        act = read_vault_entry(triggered_activation_uid)
        if act is None:
            print(f"[WARN] E6 auto-bootstrap: triggered activation {triggered_activation_uid!r} not found",
                  file=sys.stderr)
            return ""
        pipeline_def = read_vault_entry(triggered_pipeline_uid)
        if pipeline_def is None:
            print(f"[WARN] E6 auto-bootstrap: triggered pipeline {triggered_pipeline_uid!r} not found",
                  file=sys.stderr)
            return ""

        afm = act["frontmatter"]
        pdf = pipeline_def["frontmatter"]
        pipeline_name = pdf.get("name", "pipeline").lower().replace(" ", "-").replace("/", "-")
        pipeline_name = re.sub(r"[^a-z0-9-]", "", pipeline_name) or "pipeline"

        existing_uids = load_existing_uids()
        pr_uid = mint_uid(existing_uids)
        run_folder_rel = f"vault/pipeline-runs/{pipeline_name}-{pr_uid}-{TODAY}"
        run_folder_abs = VAULT_ROOT / run_folder_rel
        run_folder_abs.mkdir(parents=True, exist_ok=True)
        (run_folder_abs / "artifacts").mkdir(exist_ok=True)

        pr_fm = {
            "uid": pr_uid,
            "type": "pipeline-run",
            "title": f"{pdf.get('name', pipeline_name)} — Run {TODAY} (auto-triggered)",  # R2 nav render-safety (argus-a110 2026-06-12)
            "name": f"{pdf.get('name', pipeline_name)} — Run {TODAY} (auto-triggered)",
            "pipeline": triggered_pipeline_uid,
            "pipeline_version": pdf.get("version") or "0.0.0",
            "substrate_authored_by": triggered_activation_uid,
            "triggered_by_dev_pipeline": True,
            "status": "active",
            "state": "active",
            "current_stage": None,
            "current_step": None,
            "members": [],
            "owner": actor,
            "principal": actor,
            "authorized_by": actor,
            "started_at": now_iso(),
            "current_step_entered_at": now_iso(),
            "run_folder": run_folder_rel,
            "member_snapshot_mode": "live",
            "restart_strategy": "manual",
            "schema_version": SCHEMA_VERSION,
            "created": TODAY,
            "created_by": SCRIPT_NAME,
            "modified": TODAY,
            "modified_by": SCRIPT_NAME,
            "tags": ["pipeline-run", "v2-0-shape", "auto-triggered", "e6-v1-53"],
        }
        body = f"""# {pr_fm['name']}

*Auto-bootstrapped by pipeline-runtime.py trigger-step (E6 v1.53). No operator bootstrap required.*

**Triggered activation:** [{triggered_activation_uid}](../files/{triggered_activation_uid}.md)
**Pipeline:** [{triggered_pipeline_uid}](../files/{triggered_pipeline_uid}.md) v{pr_fm['pipeline_version']}
**Run folder:** `{run_folder_rel}/`
"""
        write_vault_entry(pr_uid, pr_fm, body)

        (run_folder_abs / "definition.md").write_text(
            f"# Pipeline-Run Definition\n\nSee vault entry [{pr_uid}](../../files/{pr_uid}.md).\n")
        (run_folder_abs / "context.md").write_text(
            f"# Run Context\n\nAuto-triggered by dev-pipeline at trigger-step. Actor: {actor}.\n")
        (run_folder_abs / "thread.md").write_text(
            "# LLM Working Memory\n\n*Append-only by convention.*\n")

        # Seed run_created event
        run_ev = make_event("run_created", actor,
                            trace_id=triggered_activation_uid, parent_span_id=None,
                            data={"pipeline_uid": triggered_pipeline_uid,
                                  "pipeline_run_uid": pr_uid,
                                  "auto_triggered": True})
        append_event(run_folder_abs, run_ev)
        print(f"  [E6] auto-bootstrapped pipeline-run {pr_uid!r} for triggered {pipeline_name}",
              file=sys.stderr)
        return pr_uid
    except Exception as e:
        print(f"[WARN] E6 auto-bootstrap failed for {triggered_activation_uid!r}: {e}",
              file=sys.stderr)
        return ""


def action_trigger_step(
    activation_uid: str,
    step_uid: str,
    triggered_spec_uid: str,
    triggered_spec_body: str,
    triggered_pipeline_uid: str,
    pipeline_class: str,
    actor: str,
    dry_run: bool = False,
) -> dict:
    """Three-pipeline coupling trigger-step handler.

    Sequence (per Engine Extension spec 51d171f3 v0.2):
    1. O_EXCL atomic create of triggered-spec file (race surface 1)
    2. Spawn pipeline-activate.py to open doc/test pipeline activation
    3. fcntl.flock atomic append to dev-spec frontmatter (race surface 2)
    Returns: {"triggered_spec_uid": ..., "triggered_activation_uid": ...}
    """
    if not re.fullmatch(r"[0-9a-f]{8}", triggered_spec_uid):
        raise ValidationError(f"--triggered-spec-uid must be 8-hex; got {triggered_spec_uid!r}")
    if not re.fullmatch(r"[0-9a-f]{8}", triggered_pipeline_uid):
        raise ValidationError(f"--triggered-pipeline-uid must be 8-hex; got {triggered_pipeline_uid!r}")
    if pipeline_class not in ("doc-pipeline", "test-pipeline"):
        raise ValidationError(
            f"--pipeline-class must be doc-pipeline or test-pipeline; got {pipeline_class!r}")

    activation = read_vault_entry(activation_uid)
    if activation is None:
        raise ValidationError(f"activation_uid {activation_uid!r} does not resolve")
    dev_spec_uid = activation["frontmatter"].get("dev_spec_uid")
    if not dev_spec_uid:
        raise ValidationError(
            f"activation {activation_uid!r} missing dev_spec_uid; cannot fire trigger-step")

    # B5 (v1.62): single-cascade idempotency — refuse a second trigger-step for the same
    # pipeline-class on this dev-run. Exactly one doc activation + one test activation per run.
    # Closes the v1.61 phantom-duplicate class where re-fires created orphaned cascade activations.
    ds_entry = read_vault_entry(dev_spec_uid)
    if ds_entry:
        dsf = ds_entry["frontmatter"]
        if pipeline_class == "doc-pipeline":
            existing_acts = dsf.get("triggered_doc_activation_uids") or []
        else:
            existing_acts = dsf.get("triggered_test_activation_uids") or []
        if existing_acts:
            raise ContractError(
                f"B5 single-cascade refused: {pipeline_class} already triggered for this dev-run "
                f"(activation(s): {existing_acts}). Each dev-run fires exactly one doc + one test "
                f"cascade. To re-trigger, retire the existing cascade activation first."
            )

    triggered_spec_path = VAULT_FILES / f"{triggered_spec_uid}.md"

    # Race surface 1: O_EXCL atomic create — fail if another process beat us
    try:
        fd = os.open(str(triggered_spec_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w") as f:
            f.write(triggered_spec_body)
    except FileExistsError:
        existing = read_vault_entry(triggered_spec_uid)
        if existing and existing["frontmatter"].get("triggered_by_dev_cycle") == activation_uid:
            # Idempotent retry: same dev-pipeline activation already created this spec
            print(f"[INFO] trigger-step idempotent: {triggered_spec_uid!r} already created by this cycle",
                  file=sys.stderr)
            existing_act_uid = existing["frontmatter"].get("triggered_activation_uid")
            if existing_act_uid:
                return {"triggered_spec_uid": triggered_spec_uid,
                        "triggered_activation_uid": existing_act_uid}
            raise ContractError(
                f"trigger-step partial failure: {triggered_spec_uid!r} exists (same dev-cycle) but "
                f"triggered_activation_uid field missing — spec authored but activation not yet spawned; "
                f"manual recovery needed (delete {triggered_spec_uid}.md and retry)"
            )
        owner = (existing["frontmatter"].get("triggered_by_dev_cycle") if existing else None)
        if owner is None:
            # Orphaned spec (no dev-cycle owner) — claim it for this cycle.
            # Per Argus A95 ruling (event 1147): None/unset triggered_by_dev_cycle means
            # the spec was pre-authored standalone; the triggering cycle claims ownership.
            # Only error when owned by a DIFFERENT cycle (a real conflict).
            print(f"[INFO] trigger-step: {'(dry-run) would claim' if dry_run else 'claiming'} orphaned spec "
                  f"{triggered_spec_uid!r} for cycle {activation_uid!r} (was unowned)", file=sys.stderr)
            if not dry_run:
                fm = existing["frontmatter"].copy()
                fm["triggered_by_dev_cycle"] = activation_uid
                write_vault_entry(triggered_spec_uid, fm, existing.get("body", ""))
        else:
            raise ContractError(
                f"trigger-step collision: {triggered_spec_uid!r} owned by dev-cycle "
                f"{owner!r}, not {activation_uid!r}")

    # dry-run: skip all writes — return a preview of what would fire.
    if dry_run:
        print(f"[DRY-RUN] trigger-step would activate pipeline {triggered_pipeline_uid!r} "
              f"(class={pipeline_class!r}) and update dev-spec {dev_spec_uid!r}", file=sys.stderr)
        return {"dry_run": True, "triggered_spec_uid": triggered_spec_uid,
                "triggered_activation_uid": "dry-run"}

    # Spawn pipeline-activate.py for the triggered pipeline class.
    # Pass --rollback-manifest to a trigger-scoped path so pipeline-activate treats
    # itself as a non-root-invocation — bypasses the root-level idempotency guard
    # (which only fires on root calls to prevent operator re-fires, not engine-triggered ones).
    activate_script = _TOOLS / "e337f1dd.py"  # pipeline-activate
    trigger_manifest_dir = (VAULT_ROOT / "playbook-runs"
                            / f"trigger-step-{triggered_pipeline_uid}-{activation_uid[:6]}-{TODAY}")
    trigger_manifest_dir.mkdir(parents=True, exist_ok=True)
    trigger_manifest_path = trigger_manifest_dir / "cascade-rollback.jsonl"
    try:
        result = subprocess.run(
            [sys.executable, str(activate_script),
             "--pipeline-uid", triggered_pipeline_uid,
             "--activated-by", actor,
             "--cycle-context", f"triggered-by-dev-cycle:{activation_uid}",
             "--rollback-manifest", str(trigger_manifest_path)],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise ContractError("pipeline-activate.py timed out after 30s during trigger-step")
    if result.returncode != 0:
        raise ContractError(
            f"pipeline-activate.py failed (exit {result.returncode}): {result.stderr.strip()}")
    triggered_activation_uid = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{8}", triggered_activation_uid):
        raise ContractError(
            f"pipeline-activate.py returned invalid activation UID: {triggered_activation_uid!r}")

    # Race surface 2: fcntl.flock exclusive lock on dev-spec for atomic frontmatter append
    dev_spec_path = VAULT_FILES / f"{dev_spec_uid}.md"
    with open(str(dev_spec_path), "r+") as f:
        deadline = time.time() + TRIGGER_LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    raise ContractError(
                        f"timeout waiting for fcntl lock on dev-spec {dev_spec_uid!r} "
                        f"after {TRIGGER_LOCK_TIMEOUT_SECONDS}s")
                time.sleep(0.05)
        try:
            content = f.read()
            m = _FRONTMATTER_RE.match(content)
            if not m:
                raise ValidationError(f"dev-spec {dev_spec_uid!r} has no valid frontmatter")
            dsf = yaml.safe_load(m.group(1)) or {}
            body = m.group(2)

            # Append spec UID + activation UID with idempotency guard
            if pipeline_class == "doc-pipeline":
                spec_list = dsf.setdefault("triggered_doc_spec_uids", [])
                act_list = dsf.setdefault("triggered_doc_activation_uids", [])
            else:
                spec_list = dsf.setdefault("triggered_test_spec_uids", [])
                act_list = dsf.setdefault("triggered_test_activation_uids", [])

            if triggered_spec_uid not in spec_list:
                spec_list.append(triggered_spec_uid)
            if triggered_activation_uid not in act_list:
                act_list.append(triggered_activation_uid)

            dsf["modified"] = TODAY
            dsf["modified_by"] = SCRIPT_NAME

            fm_yaml = yaml.safe_dump(dsf, default_flow_style=False, sort_keys=False,
                                     allow_unicode=True, width=200)
            f.seek(0)
            f.write(f"---\n{fm_yaml}---\n{body}")
            f.truncate()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    # E6 (v1.53): auto-write pipeline-run.capsule instance for the triggered doc/test pipeline.
    # Dev-pipeline gets pipeline-run via explicit operator bootstrap; triggered pipelines get it here.
    _auto_bootstrap_triggered_pipeline(triggered_activation_uid, triggered_pipeline_uid, actor)

    # Emit step lifecycle events atomically (pipeline-run.capsule v2.0 §Check 14).
    # trigger-step is a single substrate-changing action; the full step lifecycle
    # (started → completed → verified) fires here because the substrate work is
    # already done above and there is no human-verify gate on a trigger-step.
    activation_entry, pr, run_folder, events, state = load_run(activation_uid)
    artifact_links = [
        f"triggered_spec:{triggered_spec_uid}",
        f"triggered_activation:{triggered_activation_uid}",
    ]
    # step_started
    ev_started = make_event("step_started", actor, step=step_uid,
                            trace_id=activation_uid, parent_span_id=None, data={})
    append_event(run_folder, ev_started)
    # step_completed (with artifact_links pointing to the two new vault entries)
    ev_completed = make_event("step_completed", actor, step=step_uid,
                              trace_id=activation_uid,
                              parent_span_id=ev_started["span_id"],
                              data={"artifact_links": artifact_links})
    append_event(run_folder, ev_completed)
    # verification_receipt — verdict:pass (trigger-step has no human verify gate;
    # substrate writes above are the verifiable exit criterion)
    ev_receipt = make_event("verification_receipt", actor, step=step_uid,
                            trace_id=activation_uid,
                            parent_span_id=ev_completed["span_id"],
                            data={
                                "verifier_role_resolved": "same-as-executor",
                                "verdict": "pass",
                                "per_criterion": [],
                                "rubric_scores": {"exit_criteria_coverage": 1.0},
                                "overall_rationale": "trigger-step substrate writes verified: "
                                                     f"spec {triggered_spec_uid} created + "
                                                     f"activation {triggered_activation_uid} spawned",
                            })
    append_event(run_folder, ev_receipt)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(read_events(run_folder)), activation_uid)

    return {"triggered_spec_uid": triggered_spec_uid,
            "triggered_activation_uid": triggered_activation_uid}


def run_close_out_hook(activation: dict, dev_spec_uid: str | None, actor: str) -> list[str]:
    """B6 (v1.62): Pipeline completion close-out hook.

    Auto-marks completed work items as done when workflow_complete fires:
    - activation_root_project → state:done (the project that commissioned this run)
    - triggered_doc/test activation entries → status:retired (cascade activations land here)

    Returns list of closed UIDs for the completion report.
    Per design-brief 81595822 (Mike-A88 directive 2026-05-29).
    """
    closed: list[str] = []
    afm = activation["frontmatter"]

    # Close the activation root project
    # 99e52c18 state-disambiguate fix (2026-06-09):
    # (L2268) Re-key idempotency guard from state→status so a completed root
    #         (status:done) is not re-closed on every subsequent run.
    # (L2270) STOP writing state:done — state is visibility (active/archived),
    #         not completion. Completion recorded in status; state stays active.
    root_uid = afm.get("activation_root_project")
    if root_uid:
        root = read_vault_entry(root_uid)
        if root and root["frontmatter"].get("status") not in ("done", "retired", "archived"):
            rfm = root["frontmatter"]
            rfm["status"] = "done"   # record completion in status, not state
            # state intentionally NOT set to done — leave state:active (Option A)
            rfm["modified"] = TODAY
            rfm["modified_by"] = SCRIPT_NAME
            write_vault_entry(root_uid, rfm, root["body"])
            closed.append(root_uid)

    # Retire triggered cascade activations
    if dev_spec_uid:
        ds = read_vault_entry(dev_spec_uid)
        if ds:
            dsf = ds["frontmatter"]
            all_triggered = (
                list(dsf.get("triggered_doc_activation_uids") or []) +
                list(dsf.get("triggered_test_activation_uids") or [])
            )
            for tuid in all_triggered:
                tact = read_vault_entry(tuid)
                if tact and tact["frontmatter"].get("status") not in ("retired", "done"):
                    tfm = tact["frontmatter"]
                    tfm["status"] = "retired"
                    tfm["closure_reason"] = "cascade-complete-closeout-hook"
                    tfm["retired_at"] = TODAY
                    tfm["modified"] = TODAY
                    tfm["modified_by"] = SCRIPT_NAME
                    write_vault_entry(tuid, tfm, tact["body"])
                    closed.append(tuid)

    return closed


def action_complete_workflow(activation_uid: str, actor: str) -> str:
    activation, pr, run_folder, events, state = load_run(activation_uid)

    # B3 (v1.62): assert every step carries a real verification_receipt before workflow_complete.
    # (A94 2026-06-02, 5th sibling-drift fix): a step is terminal if verified OR a skip that
    # carries an authorization — mirroring L1511's skipped-is-terminal logic, but TIGHTER:
    # an UNauthorized skip still blocks (the completion gate must not pass an un-sanctioned skip).
    # The skipped-is-terminal logic had landed at L1511 but not here at its sibling. Systematic
    # sibling-drift class (rebuild-ledger / action_verify_step / compute_eligible_steps / int-vs-string
    # / this) -> filed for Talos's shared-helper sweep at d3a58cdf.
    decls = get_step_declarations(events)
    skip_auths = state.get("skip_authorizations", {})
    unverified = [
        uid for uid, status in state.get("step_status", {}).items()
        if uid in decls
        and not (status == "verified" or (status == "skipped" and uid in skip_auths))
    ]
    if unverified:
        print(f"BLOCKED: assert_all_steps_verified — steps not yet verified: {unverified} (v1.62 B3)",
              file=sys.stderr)
        print(f"BLOCKED: assert_all_steps_verified — steps not yet verified: {unverified} (v1.62 B3)")
        sys.exit(5)

    # B3-extension (v1.62 Argus A91 2026-06-01): for verification_class:true steps that were
    # "verified" via an agent-written natural_verdict (not an explicit verification_receipt),
    # recompute criteria against substrate if trust_level is auto or deterministic.
    # This closes the soft-attestation hole where an agent types natural_verdict:pass on
    # criteria that the engine can compute — same shape as the removed --verification-data-stdin
    # hatch but inside the gate rather than the verify-step command.
    ctx = build_run_context_uids(pr, activation_uid)
    for step_uid, decl in decls.items():
        if not decl.get("verification_class"):
            continue  # only vc:true steps
        trust = decl.get("trust_level", "auto-with-verification")
        if trust not in ("auto-with-verification", "auto"):
            continue  # approval-required steps use human judgment; skip
        # Check if this step has only a natural_verdict "receipt" (no explicit verification_receipt)
        has_explicit_receipt = any(
            ev.get("event") == "verification_receipt" and ev.get("step") == step_uid
            for ev in events
        )
        has_natural_verdict = any(
            ev.get("event") == "step_completed" and ev.get("step") == step_uid
            and (ev.get("data") or {}).get("natural_verdict") in ("pass", "fail")
            for ev in events
        )
        if has_explicit_receipt or not has_natural_verdict:
            continue  # already has a real receipt, or no natural_verdict to recompute
        # Recompute: engine evaluates the criteria against current substrate
        criteria = decl.get("exit_criteria") or []
        if not criteria:
            continue  # empty criteria already handled by B1
        snapshot = build_snapshot(criteria, ctx)
        per_criterion = [evaluate_criterion(c, ctx, snapshot) for c in criteria]
        verdict = "pass"
        if any(p["verdict"] == "error" for p in per_criterion):
            verdict = "error"
        elif any(p["verdict"] == "fail" for p in per_criterion):
            verdict = "fail"
        total = len(per_criterion)
        passes = sum(1 for p in per_criterion if p["verdict"] == "pass")
        receipt_ev = make_event(
            "verification_receipt", actor, step=step_uid,
            trace_id=activation_uid, parent_span_id=None,
            data={
                "verifier_role_resolved": "engine-recomputed-at-close",
                "verdict": verdict,
                "per_criterion": per_criterion,
                "rubric_scores": {"exit_criteria_coverage": passes / total if total else 0.0},
                "overall_rationale": (
                    f"B3-extension: engine-recomputed at workflow_complete (replaced agent-written "
                    f"natural_verdict; {passes}/{total} criteria pass) (Argus A91 2026-06-01)"
                ),
            }
        )
        append_event(run_folder, receipt_ev)
        events.append(receipt_ev)
        print(f"  [B3-ext] engine-recomputed {step_uid}: {verdict} ({passes}/{total} criteria)",
              file=sys.stderr)
        if verdict != "pass":
            print(f"BLOCKED: B3-extension recompute — step {step_uid!r} fails criteria (v1.62 B3-ext)",
                  file=sys.stderr)
            sys.exit(5)

    # Three-pipeline coupling enforcement (v1.51): refuse close if triggered activations not done.
    # E1 fix (v1.53): emit parseable BLOCKED: line + sys.exit(5) instead of raising ContractError.
    # build-release.py greps for "BLOCKED:" prefix; ContractError was swallowed silently (exit 137).
    allowed, reason = check_triggered_pipeline_completion(activation)
    if not allowed:
        print(f"BLOCKED: complete-workflow coupling enforcement — {reason}", file=sys.stderr)
        print(f"BLOCKED: complete-workflow coupling enforcement — {reason}")
        sys.exit(5)

    parent = find_event_span(events, "human_signoff") or (events[-1]["span_id"] if events else None)
    ev = make_event("workflow_complete", actor,
                    trace_id=activation_uid, parent_span_id=parent,
                    data={"terminal_state": "complete",
                          "final_verifier_findings_ref": find_event_span(events, "verifier_findings")})
    append_event(run_folder, ev)
    status_ev = make_event("status_changed", actor,
                            trace_id=activation_uid, parent_span_id=ev["span_id"],
                            data={"status": "complete"})
    append_event(run_folder, status_ev)
    # Flip pipeline-run frontmatter status active -> complete
    fm = pr["frontmatter"]
    fm["status"] = "complete"
    fm["completed_at"] = now_iso()
    fm["modified"] = TODAY
    fm["modified_by"] = SCRIPT_NAME
    write_vault_entry(fm["uid"], fm, pr["body"])
    # v1.47.0.1 fix-on-see (argus-a76 2026-05-20 per inbox note c3b8a7e1):
    # Also close the v1.4-shape activation entry pipeline-activate.py wrote.
    # Pre-fix: pipeline-runtime activation entries accumulated as status:active
    # indefinitely (only mark_superseded closed them); workflow_complete didn't.
    # Resulted in ADR-016 substrate violations at build pre-flight when
    # validate-capability-membership.py found multiple status:active entries
    # for agent slug `pipeline-runtime` (Vela V47 catch 2026-05-18 — 3 stale
    # entries cleaned via fix-on-see).
    afm = activation["frontmatter"]
    afm["status"] = "retired"
    afm["closure_reason"] = "pipeline-complete"
    afm["retired_at"] = TODAY
    afm["modified"] = TODAY
    afm["modified_by"] = SCRIPT_NAME
    write_vault_entry(activation_uid, afm, activation["body"])
    write_run_state_json(run_folder, fm, derive_state(read_events(run_folder)), activation_uid)

    # B7 (v1.62): render completion report from run.jsonl
    _report = render_completion_report(activation_uid, run_folder, events)
    print(f"  [completion-report] written to {run_folder}/completion-report.md", file=sys.stderr)

    # B6 (v1.62): close-out hook — auto-mark completed work items done
    dev_spec_uid = afm.get("dev_spec_uid")
    _close_out_uids = run_close_out_hook(activation, dev_spec_uid, actor)
    if _close_out_uids:
        print(f"  [close-out] marked done: {_close_out_uids}", file=sys.stderr)

    # C.5 — Stream C auto-emission: tropo.pipeline.closed (v1.58)
    try:
        _sp = Path(__file__).resolve().parents[2] / ".tropo" / "scripts"
        import sys as _sys
        if str(_sp) not in _sys.path:
            _sys.path.insert(0, str(_sp))
        from lib.event_emitter import auto_emit
        auto_emit("tropo.pipeline.closed", "/tools/pipeline-runtime", "123e12e7",
                  lifecycle="evergreen",
                  data={"activation_uid": activation_uid,
                        "pipeline_run_uid": pr["frontmatter"].get("uid")})
    except Exception:
        pass
    return "workflow_complete"


def render_completion_report(activation_uid: str, run_folder: Path, events: list[dict]) -> str:
    """B7 (v1.62): Render a per-step completion report from run.jsonl.

    Produces a human-readable summary of:
    - Every step: status, verdict, per-criterion breakdown, artifact links
    - Overall pass/fail counts and rubric coverage
    - Close-out items

    Per completion-report.capsule schema (v1.62 Lane A).
    Called at workflow_complete and renderable on-demand.
    """
    decls: dict[str, dict] = {}
    step_status: dict[str, str] = {}
    step_artifacts: dict[str, list] = {}
    step_verdicts: dict[str, dict] = {}

    for ev in events:
        et = ev.get("event") or ev.get("type", "")
        step = ev.get("step")
        data = ev.get("data") or {}
        if et == "step_declared" and step:
            decls[step] = data
        elif et == "step_completed" and step:
            step_status[step] = "completed"
            step_artifacts[step] = data.get("artifact_links") or []
            # Per pipeline-run.capsule Rule 8: verification_class:true steps may be
            # verified via natural_verdict in step_completed (no explicit receipt needed).
            # The completion report must honor this path so it agrees with the close gate.
            # (Argus A91 2026-06-01 substrate analysis; Option A fix for run 1db53550 gap.)
            nat = data.get("natural_verdict")
            if nat in ("pass", "fail"):
                step_status[step] = "verified"
                step_verdicts[step] = {
                    "verifier_role_resolved": "natural-verdict",
                    "verdict": nat,
                    "per_criterion": [],
                    "rubric_scores": {"exit_criteria_coverage": 1.0 if nat == "pass" else 0.0},
                    "overall_rationale": f"natural_verdict:{nat} from step_completed (pipeline-run.capsule Rule 8)",
                }
        elif et == "verification_receipt" and step:
            step_status[step] = "verified"
            step_verdicts[step] = data
        elif et == "step_failed" and step:
            step_status[step] = "failed"

    lines = [
        f"# Completion Report — Activation {activation_uid}",
        f"Generated: {now_iso()}",
        "",
        "## Per-Step Verdicts",
        "",
    ]

    total_steps = len(decls)
    pass_count = 0
    fail_count = 0
    unverified_count = 0

    for step_uid, decl in decls.items():
        status = step_status.get(step_uid, "declared")
        verdict_data = step_verdicts.get(step_uid, {})
        verdict = verdict_data.get("verdict", "—")
        criteria = decl.get("exit_criteria") or []
        per_criterion = verdict_data.get("per_criterion") or []
        artifacts = step_artifacts.get(step_uid) or []
        rubric = verdict_data.get("rubric_scores", {})
        coverage = rubric.get("exit_criteria_coverage", 0.0)

        if verdict == "pass":
            pass_count += 1
            marker = "✓"
        elif verdict in ("fail", "error"):
            fail_count += 1
            marker = "✗"
        else:
            unverified_count += 1
            marker = "?"

        lines.append(f"### {marker} {step_uid} — {status} / {verdict}")
        lines.append(f"- Owner: {decl.get('step_owner_role', '—')}")
        lines.append(f"- Criteria declared: {len(criteria)}  Coverage: {coverage:.0%}")
        if artifacts:
            lines.append(f"- Artifacts: {', '.join(str(a) for a in artifacts)}")
        if per_criterion:
            for c in per_criterion:
                c_verdict = c.get("verdict", "?")
                c_expr = c.get("expression") or c.get("criterion", "?")
                c_marker = "✓" if c_verdict == "pass" else "✗"
                lines.append(f"  {c_marker} `{c_expr}` → {c_verdict}")
        elif not criteria:
            lines.append("  *(no exit_criteria declared — hollow step)*")
        lines.append("")

    lines += [
        "## Summary",
        "",
        f"- Steps total: {total_steps}",
        f"- Passed: {pass_count}",
        f"- Failed: {fail_count}",
        f"- Unverified: {unverified_count}",
        f"- Overall: {'PASS' if fail_count == 0 and unverified_count == 0 else 'FAIL'}",
    ]

    report = "\n".join(lines)

    # Write to run folder for persistence
    report_path = run_folder / "completion-report.md"
    report_path.write_text(report, encoding="utf-8")

    return report


def action_resume_from_log(activation_uid: str) -> dict:
    activation, pr, run_folder, events, state = load_run(activation_uid)
    decls = get_step_declarations(events)
    eligible = compute_eligible_steps(state, decls)
    return {
        "pipeline_run_uid": pr["frontmatter"].get("uid"),
        "current_stage": state.get("current_stage"),
        "current_step": state.get("current_step"),
        "eligible_steps": eligible,
        "run_status": state.get("run_status"),
        "last_event_ts": state.get("last_event_ts"),
    }


def action_amend_step_criteria(
    activation_uid: str,
    step_uid: str,
    new_criteria: list[str],
    actor: str,
    verification_command: str | None = None,
) -> str:
    """Gap-3 fix (Vela V56 00000660 2026-06-01): amend exit_criteria on a declared step.

    Writes a step_criteria_amended event to run.jsonl. get_step_declarations
    prefers the latest amendment over the original step_declared, so re-authored
    step definitions reach verify-step without re-bootstrapping the run.
    """
    activation, pr, run_folder, events, state = load_run(activation_uid)
    decls = get_step_declarations(events)
    if step_uid not in decls:
        raise ValidationError(f"step {step_uid!r} not in activation contract; cannot amend")
    data: dict = {"step_id": step_uid, "exit_criteria": new_criteria}
    if verification_command:
        data["verification_command"] = verification_command
    ev = make_event("step_criteria_amended", actor, step=step_uid,
                    trace_id=activation_uid, parent_span_id=None, data=data)
    append_event(run_folder, ev)
    events.append(ev)
    write_run_state_json(run_folder, pr["frontmatter"], derive_state(events), activation_uid)
    return f"amended:{step_uid} ({len(new_criteria)} criteria)"


def action_mark_superseded(activation_uid: str, superseded_by: str, supersession_reason: str,
                            actor: str) -> str:
    activation, pr, run_folder, events, state = load_run(activation_uid)
    fm = pr["frontmatter"]
    if actor not in (fm.get("owner"), fm.get("principal"), fm.get("authorized_by")):
        raise ContractError(f"mark-superseded invoker {actor!r} is not owner/principal/authorized_by")
    if supersession_reason not in ("self-bootstrap", "contract-modification", "restart-from-scratch", "other"):
        raise ContractError(f"invalid supersession_reason {supersession_reason!r}")
    parent = events[-1]["span_id"] if events else None
    ev = make_event("activation_superseded", actor,
                    trace_id=activation_uid, parent_span_id=parent,
                    data={"superseded_by": superseded_by,
                          "supersession_reason": supersession_reason,
                          "prior_status_at_supersession": state.get("run_status")})
    append_event(run_folder, ev)
    # Flip activation entry to closed
    afm = activation["frontmatter"]
    afm["status"] = "retired"
    afm["closure_reason"] = "self-validating-bootstrap-supersession"
    afm["retired_at"] = TODAY
    afm["superseded_by"] = superseded_by
    write_vault_entry(activation_uid, afm, activation["body"])
    write_run_state_json(run_folder, fm, derive_state(read_events(run_folder)), activation_uid)
    return f"superseded:{activation_uid}:by:{superseded_by}"


# ---------------------- main / argparse ----------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=SCRIPT_NAME, description="v1.46.0 pipeline-runtime engine")
    p.add_argument("--activation-uid", required=True,
                   help="8-hex UID of pipeline-activate.py's activation entry")
    p.add_argument("--json", action="store_true", help="emit structured JSON to stdout")
    p.add_argument("--dry-run", action="store_true", help="render intended events without writing")
    p.add_argument("--actor", default="user",
                   help="actor UID for events written by this invocation (defaults to 'user')")
    sub = p.add_subparsers(dest="action", required=False)

    sub.add_parser("bootstrap", help="initial pipeline-run authoring + contract lock").add_argument(
        "--contract-input", help="YAML/JSON file with skips_authorized_upfront / additional_steps_added / "
                                 "trust_overrides / human_instructions / supersedes_activation / supersession_reason")

    sub.add_parser("step-start").add_argument("step_uid")

    sc = sub.add_parser("step-complete")
    sc.add_argument("step_uid")
    sc.add_argument("--artifact-links", required=True,
                    help="comma-separated paths or UIDs")
    sc.add_argument("--natural-verdict",
                    help="for verification-class steps: 'pass' or 'fail' from natural output")

    vs = sub.add_parser("verify-step")
    vs.add_argument("step_uid")
    # B4 (v1.62): --verification-data-stdin removed — self-attestation hatch closed.

    sf = sub.add_parser("step-fail")
    sf.add_argument("step_uid")
    sf.add_argument("--failure-phase", required=True, choices=["RP", "E", "RP/E"])
    sf.add_argument("--failure-class", required=True)
    sf.add_argument("--disposition", required=True,
                    choices=["retry", "skip_with_authorization", "complete_with_exception",
                             "compensate", "abort"])
    sf.add_argument("--error-detail", required=True)
    sf.add_argument("--retry-count", type=int, default=0)

    sr = sub.add_parser("skip-request")
    sr.add_argument("step_uid")
    sr.add_argument("--reason", required=True)

    az = sub.add_parser("authorize-skip")
    az.add_argument("step_uid")
    az.add_argument("--authorized-by", required=True)
    az.add_argument("--conditions", default="")

    sub.add_parser("apply-skip").add_argument("step_uid")

    pa = sub.add_parser("pause")
    pa.add_argument("--reason", default="explicit-pause")

    rs = sub.add_parser("resume")
    rs.add_argument("--confirmation-granted-by", default=None)

    sub.add_parser("terminal-verify")

    # Gap-3 fix: amend exit_criteria on a declared step without re-bootstrapping
    asc = sub.add_parser("amend-step-criteria")
    asc.add_argument("step_uid")
    asc.add_argument("--criteria", nargs="+", required=True,
                     help="New exit_criteria list (space-separated; quote each criterion)")
    asc.add_argument("--verification-command", default=None,
                     help="Optional: set verification_command on the step")

    hs = sub.add_parser("human-signoff")
    hs.add_argument("--verdict", required=True,
                    choices=["accepted", "accepted_with_exceptions", "rejected"])
    hs.add_argument("--notes", default="")

    ts = sub.add_parser("trigger-step", help="fire a three-pipeline coupling trigger (doc-pipeline or test-pipeline)")
    ts.add_argument("step_uid")
    ts.add_argument("--triggered-spec-uid", required=True,
                    help="pre-generated 8-hex UID for the triggered doc/test spec file")
    ts.add_argument("--triggered-pipeline-uid", required=True,
                    help="8-hex UID of the pipeline definition to activate (doc-pipeline or test-pipeline)")
    ts.add_argument("--pipeline-class", required=True, choices=["doc-pipeline", "test-pipeline"],
                    help="class of the triggered pipeline")
    ts.add_argument("--triggered-spec-body-stdin", action="store_true",
                    help="read triggered-spec file body from stdin")
    ts.add_argument("--triggered-spec-body-file",
                    help="path to file containing triggered-spec body (alternative to --triggered-spec-body-stdin)")

    sub.add_parser("complete-workflow")
    sub.add_parser("resume-from-log")

    ms = sub.add_parser("mark-superseded")
    ms.add_argument("--superseded-by", required=True)
    ms.add_argument("--supersession-reason", required=True,
                    choices=["self-bootstrap", "contract-modification", "restart-from-scratch", "other"])

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    action = args.action or "bootstrap"
    actor = args.actor

    try:
        if action == "bootstrap":
            result = action_bootstrap(args.activation_uid,
                                       getattr(args, "contract_input", None),
                                       args.dry_run)
            print(result if not args.json else json.dumps({"pipeline_run_uid": result}))
        elif action == "step-start":
            result = action_step_start(args.activation_uid, args.step_uid, actor)
            print(result if not args.json else json.dumps({"result": result}))
        elif action == "step-complete":
            links = [s.strip() for s in args.artifact_links.split(",") if s.strip()]
            result = action_step_complete(args.activation_uid, args.step_uid, links, actor,
                                            args.natural_verdict)
            print(result if not args.json else json.dumps({"result": result}))
        elif action == "verify-step":
            result = action_verify_step(args.activation_uid, args.step_uid, actor)
            print(result if not args.json else json.dumps({"verdict": result}))
        elif action == "step-fail":
            result = action_step_fail(args.activation_uid, args.step_uid, actor,
                                       args.failure_phase, args.failure_class, args.disposition,
                                       args.error_detail, args.retry_count)
            print(result if not args.json else json.dumps({"result": result}))
        elif action == "skip-request":
            result = action_skip_request(args.activation_uid, args.step_uid, actor, args.reason)
            print(result if not args.json else json.dumps({"result": result}))
        elif action == "authorize-skip":
            result = action_authorize_skip(args.activation_uid, args.step_uid,
                                            args.authorized_by, args.conditions, actor)
            print(result if not args.json else json.dumps({"result": result}))
        elif action == "apply-skip":
            result = action_apply_skip(args.activation_uid, args.step_uid, actor)
            print(result if not args.json else json.dumps({"result": result}))
        elif action == "pause":
            result = action_pause(args.activation_uid, args.reason, actor)
            print(result if not args.json else json.dumps({"result": result}))
        elif action == "resume":
            result = action_resume(args.activation_uid, args.confirmation_granted_by, actor)
            print(result if not args.json else json.dumps({"result": result}))
        elif action == "terminal-verify":
            result = action_terminal_verify(args.activation_uid, actor)
            print(result if not args.json else json.dumps({"verdict": result}))
        elif action == "amend-step-criteria":
            result = action_amend_step_criteria(
                args.activation_uid, args.step_uid, args.criteria, actor,
                verification_command=args.verification_command,
            )
            print(result if not args.json else json.dumps({"result": result}))
        elif action == "human-signoff":
            # v1.66 S1: standalone human-signoff CLI retired — action_resume is the ONE
            # enforced signoff path (Argus A102 ed04d931 §3). Direct callers to resume.
            print(
                "ERROR: --action human-signoff is retired. "
                "Use: python3 9e7003b1.py --action resume --confirmation-granted-by <principal> "
                "(the approval gate is enforced there with full independence checks). "
                "(v1.66 S1 consolidated fix; ed04d931)",
                file=sys.stderr,
            )
            sys.exit(2)
        elif action == "trigger-step":
            if args.triggered_spec_body_stdin:
                triggered_spec_body = sys.stdin.read()
            elif args.triggered_spec_body_file:
                triggered_spec_body = Path(args.triggered_spec_body_file).read_text()
            else:
                print("ERROR: trigger-step requires --triggered-spec-body-stdin or --triggered-spec-body-file",
                      file=sys.stderr)
                return EXIT_ARGS
            result = action_trigger_step(
                args.activation_uid, args.step_uid,
                args.triggered_spec_uid, triggered_spec_body,
                args.triggered_pipeline_uid, args.pipeline_class, actor,
                dry_run=args.dry_run,
            )
            print(json.dumps(result) if not args.json else json.dumps(result))
        elif action == "complete-workflow":
            result = action_complete_workflow(args.activation_uid, actor)
            print(result if not args.json else json.dumps({"result": result}))
        elif action == "resume-from-log":
            result = action_resume_from_log(args.activation_uid)
            print(json.dumps(result, indent=2))
        elif action == "mark-superseded":
            result = action_mark_superseded(args.activation_uid, args.superseded_by,
                                              args.supersession_reason, actor)
            print(result if not args.json else json.dumps({"result": result}))
        else:
            print(f"ERROR: unknown action {action!r}", file=sys.stderr)
            return EXIT_ARGS
        return EXIT_SUCCESS
    except ValidationError as e:
        print(f"VALIDATION ERROR: {e}", file=sys.stderr)
        return EXIT_VALIDATION
    except ContractError as e:
        print(f"CONTRACT ERROR: {e}", file=sys.stderr)
        return EXIT_CONTRACT
    except SkipAuthError as e:
        print(f"SKIP-AUTHORIZATION ERROR: {e}", file=sys.stderr)
        return EXIT_SKIP_AUTH
    except OSError as e:
        print(f"RUNTIME ERROR: {e}", file=sys.stderr)
        return EXIT_RUNTIME
    except Exception as e:
        print(f"UNEXPECTED ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    sys.exit(main())
