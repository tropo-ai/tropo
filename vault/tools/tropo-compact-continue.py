#!/usr/bin/env python3
"""
---
uid: 4d5ff95d
title: compact-continue — Tool
name: compact-continue
type: tool
status: active
owner: talos
domain: "Same-session re-anchor after context compaction: validate live identity, fetch, drain, report debts and work state, broadcast once. Never births, retires, or writes lineage."
spawnable_by:
  - all-executives
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-compact-continue.py --agent <slug> [--json] [--studio PATH] [--attest]"
script_path: vault/tools/tropo-compact-continue.py
belt: true
belt_invocation: "python3 vault/tools/tropo-compact-continue.py --agent <slug>"
belt_example: "python3 vault/tools/tropo-compact-continue.py --agent talos"
input:
  type: object
  properties:
    agent:
      type: string
      description: "Agent slug whose live generation is continuing (required)."
    json:
      type: boolean
      description: "Emit the re-anchor packet as JSON instead of the human report."
destructive: false
audit_required: false
writes_scope:
  - .tropo-studio/compact-continue/**
  - vault/events/**
governance_category: lifecycle
description: "One-command same-generation recovery after a context compaction. Reads the live generation from tropo-lineage.py who, corroborates it against the exact completed activation run, fetches before draining events, and prints the identity card (party uid, root uid, unified entry, sleeve, clone, remote, branch, git discipline, the correlationid emit shape) plus the machine-derived ordered read list with the not-to-read rollback files named beside it (f015fcaf29b9 items 2+4). The re-anchor broadcast is HELD until --attest: the continuation run reports NOT re-anchored with N reads outstanding, and only the attest gesture — after the reads, with real per-source fingerprints written to the activation file refresh_state() reads — emits it (item 3). It has no path to born and writes no lineage."
domain_tags:
  - compact-continue
  - re-anchor
  - lifecycle
  - same-session
trigger_description: "Reach for this the moment a session was compacted or an agent cannot remember completing boot. Run it BEFORE any other work and never run born: born mints a phantom successor for a session that is still alive. Also correct when an imminent auto-compact warning appears — context pressure routes here, not to retirement."
created: 2026-08-12
created_by: talos-t41
modified: 2026-09-07
modified_by: vela-v79
governed_by: d5e1b4a3
member_of:
  - 8dd772a0
schema_version: 2
extraction_scope: ship
refs:
  - d5f8fe55
  - 408c158c
tags:
  - tool
  - cli
  - compact-continue
  - lifecycle
subsystem_hub:
  - 8dd772a0
---
"""

from __future__ import annotations

"""Compact-Continue Phase 1 — same-session re-anchor (dev-spec d5f8fe55).

    Continue means this same agent session keeps going. Nothing is born,
    retired, or added to permanent lineage.

The tool does not detect compaction. A harness trigger or a human says the
session was compacted; this validates that request against lineage and the
exact completed activation run, then re-establishes repository and event truth.

Deliberate absences, each one a named risk in the spec:

* no import, subprocess, string, or fallback path to ``born`` — a phantom
  successor for a live session is the P0 this feature exists to prevent;
* no worktree mutation anywhere in the call graph: fetch is the only Git write,
  and it writes only to ``.git``;
* no shell. Every subprocess is an argument array, because commit subjects are
  attacker-shaped data (``99b17d16`` carries backticks) and must render as text;
* no boot replay, milestone, memory append, or agent-voice edit.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

TOOL_UID = "4d5ff95d"
DEV_SPEC_UID = "d5f8fe55"

# THE ONE CANONICAL TRIGGER. Copied byte-for-byte into every live and shipped
# harness surface; the validator compares against this constant, so a reworded
# copy is a build failure rather than a surface that quietly stops working.
TRIGGER_LINE = (
    "If this agent session was compacted, auto-compacted, or resumed, or you no "
    "longer remember completing boot, do not activate and never run `born`. Run "
    "`python3 vault/tools/tropo-compact-continue.py --agent <slug>` before any other work."
)

# Every surface that must carry TRIGGER_LINE, and what kind of copy it is.
#
# This list is the coverage contract the validator reads: a harness that gains a
# surface and does not appear here is invisible to the gate, so the list lives
# beside the trigger it distributes rather than in the validator.
#
#   markdown — the line appears as prose or a blockquote in the document;
#   json     — the line appears inside a hook command/instruction string.
TRIGGER_SURFACES: dict = {
    # Live Argo surfaces (dogfood).
    "CLAUDE.md": "markdown",
    "AGENTS.md": "markdown",
    "START-TROPO.md": "markdown",
    "GEMINI.md": "markdown",
    ".claude/settings.json": "json",
    ".gemini/settings.json": "json",
    # Shipped templates — the canonical sources recipients receive.
    "vault/templates/root-docs/CLAUDE.md": "markdown",
    "vault/templates/root-docs/AGENTS.md": "markdown",
    "vault/templates/root-docs/START-TROPO.md": "markdown",
    "vault/templates/root-docs/GEMINI.md": "markdown",
    "vault/templates/ide-configs/.cursorrules": "markdown",
    "vault/templates/harness-configs/.claude/settings.json": "json",
    "vault/templates/harness-configs/.gemini/settings.json": "json",
}

# Wording that would route a compacted session into a new generation. A surface
# carrying the trigger AND one of these is worse than one carrying neither: it
# reads as permission.
COMPACT_TO_BORN_PATTERNS: tuple = (
    r"compact\w*[^.\n]{0,80}\brun\s+`?born`?",
    r"compact\w*[^.\n]{0,80}\blineage\.py\s+born",
    r"after\s+compaction[^.\n]{0,80}\bactivate\b",
)

JOURNAL_REL = Path(".tropo-studio") / "compact-continue"
RETIREMENT_PLAYBOOK = "vault/playbooks/e2c7d185.md"
EVENT_MECHANICS_POINTER = (
    "python3 vault/tools/tropo-check-events.py --as <slug>; reply with "
    "tropo-emit-event.py --subject <recipient-party-uid> --correlationid "
    "<their-event-id> --final|--not-final — a reply without --correlationid "
    "never closes the thread and the asker is told they were not answered"
)
RECENT_COMMIT_DEFAULT = 5
GEN_RE = re.compile(r"^[A-Za-z]+\d+$")


class ContinueRefusal(Exception):
    """A request that must not be answered with a continuation packet."""


@dataclass
class Packet:
    status: str = "continued"
    agent: str = ""
    generation: str = ""
    same_session: bool = True
    same_generation: bool = True
    continuation_uid: str = ""
    identity: dict = field(default_factory=dict)
    activation_run: dict = field(default_factory=dict)
    git: dict = field(default_factory=dict)
    events: dict = field(default_factory=dict)
    recent_commits: list = field(default_factory=list)
    refresh: dict = field(default_factory=dict)
    broadcast: str = "pending"
    lineage_written: bool = False
    read_list: list = field(default_factory=list)
    not_to_read: list = field(default_factory=list)
    reads_outstanding: int = 0
    snapshot: dict = field(default_factory=dict)
    pointers: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "agent": self.agent,
            "generation": self.generation,
            "same_session": self.same_session,
            "same_generation": self.same_generation,
            "continuation_uid": self.continuation_uid,
            "identity": self.identity,
            "activation_run": self.activation_run,
            "git": self.git,
            "events": self.events,
            "recent_commits": self.recent_commits,
            "refresh": self.refresh,
            "broadcast": self.broadcast,
            "lineage_written": self.lineage_written,
            "read_list": self.read_list,
            "not_to_read": self.not_to_read,
            "reads_outstanding": self.reads_outstanding,
            "snapshot": self.snapshot,
            "pointers": self.pointers,
        }


# --------------------------------------------------------------------------- #
# Roots and processes                                                           #
# --------------------------------------------------------------------------- #

def resolve_studio_root(explicit: Optional[str] = None) -> Path:
    """Studio root from an explicit path, else the tree this tool lives in."""
    if explicit:
        root = Path(explicit).resolve()
    else:
        root = Path(__file__).resolve().parents[2]
    if not (root / "vault").is_dir():
        raise ContinueRefusal(f"not a Studio root (no vault/): {root}")
    return root


def run(args: list, cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    """Every subprocess in this tool. Argument array, shell=False, always."""
    return subprocess.run(
        [str(a) for a in args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        shell=False,
        timeout=timeout,
    )


def _tool(root: Path, name: str) -> Path:
    return root / "vault" / "tools" / name


# --------------------------------------------------------------------------- #
# Identity — the half that must never guess                                     #
# --------------------------------------------------------------------------- #

def read_live_generation(root: Path, slug: str) -> dict:
    """The live generation per lineage, or a refusal. Never births."""
    lineage = _tool(root, "tropo-lineage.py")
    if not lineage.is_file():
        raise ContinueRefusal(f"lineage tool not found at {lineage}")
    proc = run([sys.executable, lineage, "who", "--agent", slug], root)
    if proc.returncode != 0:
        raise ContinueRefusal(
            f"no live generation for {slug!r}: `tropo-lineage.py who` exited "
            f"{proc.returncode}. {(proc.stderr or proc.stdout).strip()[:400]}. "
            "Continue recovers a session that already exists; it never creates one."
        )
    try:
        record = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise ContinueRefusal(f"`who` output is not JSON: {exc}") from exc
    if not isinstance(record, dict) or not record.get("gen"):
        raise ContinueRefusal(
            f"`who --agent {slug}` reports no live generation. Continue refuses: "
            "an agent that was never born cannot be continued, and this tool "
            "will not birth one."
        )
    if record.get("retired"):
        raise ContinueRefusal(
            f"{slug} {record.get('gen')} is RETIRED. A retired generation is not "
            "a compacted session. Continue refuses rather than reanimating it."
        )
    return record


def find_activation_run(root: Path, slug: str, generation: str) -> dict:
    """The exact completed activation run corroborating this generation.

    Corroboration of the requested session, not proof compaction happened.
    Zero matches refuse. Multiple complete matches refuse as ambiguous unless
    they carry the same ``run_uid`` — mtime is never identity.
    """
    generation = str(generation).strip()
    if not GEN_RE.match(generation):
        raise ContinueRefusal(f"unusable generation {generation!r} from lineage")
    runs_dir = root / "playbook-runs"
    # metis-g111 2026-08-23 (self-heal after a machine reboot): run folders are named with the
    # lowercase generation (agent-activation-metis-g111-...), lineage returns "G111", and
    # pathlib.glob is case-sensitive here — so Continue refused a completed run it was
    # looking straight at. Match both casings.
    #
    # v1.93 CORRECTION (argus-a161): the comment above said "Match both casings" and the code
    # lowercased ONLY THE PATTERN, so it matched exactly one casing — the lowercase one. Any
    # agent whose run folder carries the generation as the boot playbook actually tells you to
    # write it (playbook 99341618 line 163 stamps the value `born` returned, e.g. "A161") was
    # invisible to this tool. PROVEN ON MY OWN LIVE SESSION: with
    # playbook-runs/agent-activation-argus-A161-2026-08-28/ complete on disk, this refused with
    # "no completed activation run for argus A161 on this machine".
    #
    # WHY IT WAS A SHIP BLOCKER RATHER THAN AN ANNOYANCE, per the v1.93 release harness: five
    # front-door documents (CLAUDE.md, START-TROPO.md, GEMINI.md, .tropo/boot-config.md and the
    # playbook) bind the agent to run THIS TOOL FIRST after a compaction and to never run `born`.
    # The refusal's only offered exit was "use normal activation", and normal activation IS
    # `born` — so the box contradicted itself and pushed the recovering agent toward writing a
    # phantom generation into permanent lineage. The diagnostic compounded it: the folder is
    # present and complete, and the tool called it "stale or missing".
    #
    # Now case-insensitive on BOTH sides, which is what the comment always claimed. Globbing a
    # slug-only pattern and filtering in Python keeps this independent of filesystem case
    # semantics, which differ across the platforms a portable Studio is meant to survive.
    wanted_prefix = f"agent-activation-{slug.lower()}-{generation.lower()}-"
    complete: list[dict] = []
    partial: list[str] = []
    candidates = [
        c for c in sorted(runs_dir.glob("agent-activation-*"))
        if c.name.lower().startswith(wanted_prefix)
    ] if runs_dir.is_dir() else []
    for candidate in candidates:
        run_path = candidate / "run.jsonl"
        if not run_path.is_file():
            continue
        saw_active = False
        saw_complete = False
        run_uid = ""
        for line in run_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            run_uid = str(row.get("run_uid") or run_uid)
            if "Active" in str(row.get("milestone") or ""):
                saw_active = True
            if str(row.get("run_status") or "") == "complete":
                saw_complete = True
        if saw_active and saw_complete:
            complete.append(
                {
                    "run_uid": run_uid or candidate.name,
                    "path": str(candidate.relative_to(root)),
                }
            )
        else:
            partial.append(candidate.name)
    if not complete:
        detail = (
            f" Incomplete run(s) present: {', '.join(partial)}." if partial else ""
        )
        raise ContinueRefusal(
            f"no completed activation run for {slug} {generation} on this "
            f"machine.{detail} A stale or missing run folder is not a current "
            "session: Continue refuses to claim compaction recovery. Use normal "
            "activation and human judgement."
        )
    distinct = {entry["run_uid"] for entry in complete}
    if len(distinct) > 1:
        raise ContinueRefusal(
            f"ambiguous activation runs for {slug} {generation}: "
            f"{', '.join(sorted(distinct))}. Continue refuses rather than "
            "choosing by modification time."
        )
    return complete[0]


# --------------------------------------------------------------------------- #
# Local continuation journal — operational crash state, never lineage           #
# --------------------------------------------------------------------------- #

def journal_path(root: Path, slug: str, generation: str) -> Path:
    return root / JOURNAL_REL / f"{slug}-{generation}.pending.json"


def acquire_lock(root: Path, slug: str, generation: str, *, timeout: float = 10.0):
    """Per-agent lock so two Continues cannot interleave their journals."""
    lock_dir = root / JOURNAL_REL / f"{slug}-{generation}.lock"
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout
    while True:
        try:
            lock_dir.mkdir()
            return lock_dir
        except FileExistsError:
            if time.time() >= deadline:
                raise ContinueRefusal(
                    f"another Continue holds {lock_dir}; refusing to interleave"
                )
            time.sleep(0.05)


def release_lock(lock_dir: Path) -> None:
    try:
        lock_dir.rmdir()
    except OSError:
        pass


def load_or_open_journal(root: Path, slug: str, generation: str, run_uid: str) -> dict:
    """Resume an incomplete continuation, or open a new one."""
    path = journal_path(root, slug, generation)
    if path.is_file():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            record = None
        if isinstance(record, dict) and record.get("continuation_uid"):
            record["resumed"] = True
            return record
    return {
        "continuation_uid": secrets.token_hex(16),
        "agent": slug,
        "generation": generation,
        "activation_run_uid": run_uid,
        "started": _now(),
        "phases": [],
        "resumed": False,
    }


def save_journal(root: Path, slug: str, generation: str, record: dict) -> None:
    path = journal_path(root, slug, generation)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def clear_journal(root: Path, slug: str, generation: str) -> None:
    path = journal_path(root, slug, generation)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Repository truth — read-only                                                  #
# --------------------------------------------------------------------------- #

def git_state(root: Path) -> dict:
    """Fetch, then describe. No pull, merge, rebase, checkout, reset, or clean."""
    state: dict[str, Any] = {
        "fetch_status": "fetched",
        "fetch_error": "",
        "branch": "",
        "remote": "",
        "local_sha": "",
        "remote_sha": "",
        "ahead": None,
        "behind": None,
        "dirty_tracked": [],
        "untracked": [],
    }
    fetch = run(["git", "fetch", "origin"], root, timeout=180)
    if fetch.returncode != 0:
        state["fetch_status"] = "failed-local-only"
        state["fetch_error"] = (fetch.stderr or fetch.stdout).strip()[:400]

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    remote_url = run(["git", "remote", "get-url", "origin"], root)
    if remote_url.returncode == 0:
        state["remote"] = remote_url.stdout.strip()
    if branch.returncode == 0:
        state["branch"] = branch.stdout.strip()
    local = run(["git", "rev-parse", "HEAD"], root)
    if local.returncode == 0:
        state["local_sha"] = local.stdout.strip()
    remote = run(["git", "rev-parse", "origin/main"], root)
    if remote.returncode == 0:
        state["remote_sha"] = remote.stdout.strip()
        counts = run(
            ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"], root
        )
        if counts.returncode == 0:
            parts = counts.stdout.split()
            if len(parts) == 2:
                state["behind"], state["ahead"] = int(parts[0]), int(parts[1])

    status = run(["git", "status", "--porcelain"], root)
    if status.returncode == 0:
        for line in status.stdout.splitlines():
            if not line.strip():
                continue
            code, _, path = line.partition(" ")
            if line.startswith("??"):
                state["untracked"].append(line[3:])
            else:
                state["dirty_tracked"].append(line[3:] or path.strip())
    return state


def recent_commits(root: Path, slug: str, generation: str, limit: int = RECENT_COMMIT_DEFAULT) -> list:
    """Self-attributed commits, rendered as data.

    Subjects are never interpolated into a shell. When no commit carries this
    generation's prefix, repository-recent commits are shown labelled
    ``ownership: unresolved`` rather than claimed.
    """
    prefix = f"{slug}-{generation.lower()}:"
    proc = run(
        ["git", "log", "-n", str(limit * 20), "--no-merges", "--format=%H%x00%s"],
        root,
    )
    if proc.returncode != 0:
        return []
    mine: list[dict] = []
    everything: list[dict] = []
    for line in proc.stdout.splitlines():
        sha, _, subject = line.partition("\x00")
        if not sha:
            continue
        entry = {"sha": sha[:8], "subject": subject, "ownership": "self"}
        if subject.startswith(prefix):
            mine.append(entry)
            if len(mine) >= limit:
                break
        elif len(everything) < limit:
            everything.append({**entry, "ownership": "unresolved"})
    return mine if mine else everything


# --------------------------------------------------------------------------- #
# Event truth — fetch first, spool before later phases                          #
# --------------------------------------------------------------------------- #

def drain_events(root: Path, slug: str, *, local_only: bool) -> tuple[dict, dict]:
    """Run the shipped drain once and return (summary, raw packet).

    Returned raw output is spooled by the caller BEFORE later phases run: a
    parent crash after draining must not be able to hide a message that the
    drain already marked seen.
    """
    tool = _tool(root, "tropo-check-events.py")
    summary: dict[str, Any] = {
        "state": "local-only" if local_only else "current",
        "drain_status": "ok",
        "new_events": 0,
        "unanswered_reply_required": 0,
        "debts": [],
        "error": "",
    }
    if not tool.is_file():
        summary["drain_status"] = "unavailable"
        summary["error"] = f"{tool} not found"
        return summary, {}
    proc = run([sys.executable, tool, "--as", slug, "--json"], root, timeout=180)
    if proc.returncode != 0 and not proc.stdout.strip():
        summary["drain_status"] = "failed"
        summary["error"] = (proc.stderr or "").strip()[:400]
        return summary, {}
    try:
        raw = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        summary["drain_status"] = "unparseable"
        summary["error"] = str(exc)[:200]
        return summary, {}
    unanswered = raw.get("unanswered_reply_required") or []
    summary["new_events"] = len(raw.get("new_events") or [])
    summary["unanswered_reply_required"] = len(unanswered)
    for event in unanswered[:20]:
        data = event.get("data") or {}
        summary["debts"].append(
            {
                "id": event.get("id", ""),
                "from": data.get("from", ""),
                "headline": str(data.get("headline") or "")[:120],
            }
        )
    return summary, raw


# --------------------------------------------------------------------------- #
# Precompact snapshot readback — item 5 seam (f015fcaf29b9): what the        #
# session knew at the moment compaction became imminent, printed FIRST,      #
# before any fresh truth is derived, so the delta is visible.                #
# --------------------------------------------------------------------------- #

def read_snapshot(root: Path, slug: str) -> dict:
    """The machine-knowable half of a transfer, captured pre-compaction.

    Written by tropo-precompact-snapshot.py under the agent's workspace.
    Absence is recorded honestly — a snapshot that never fired is signal,
    not noise. Malformed degrades to a reason, never a crash.
    """
    rel = Path("agents") / slug / ".tropo-capsule" / "workspace" / "precompact-snapshot.json"
    path = root / rel
    if not path.is_file():
        return {
            "present": False,
            "path": str(rel),
            "reason": "no snapshot — the PreCompact hook did not fire or is unwired",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return {"present": False, "path": str(rel), "reason": f"malformed: {exc}"}
    return {"present": True, "path": str(rel), "data": data}


def continuation_kind(snapshot: dict, continuation_uid: str) -> dict:
    """Did this continuation follow a COMPACTION, or only a resume?

    The tool cannot observe a compaction; its own docstring says so. But the
    PreCompact hook fires once per compaction and ONLY on a compaction, and the
    snapshot it writes stamps `written_at` and a `trigger` read from that hook's
    own stdin. So an unconsumed snapshot is evidence a compaction happened, and
    its absence is evidence one did not.

    This exists because the broadcast used to claim "compacted and re-anchored"
    on every run, including plain resumes. orpheus-o38 emitted exactly that
    false claim on 2026-09-07 and had to correct it on the bus; argus-a161 had
    to correct the same class on 2026-08-29. Derive the claim from evidence the
    compaction itself produced, never from the fact that this tool ran.

    Consumption matters: a snapshot from last week's compaction must not make
    today's resume look like one. The first continuation to read a snapshot
    stamps its own uid into it; later runs see it consumed and say `resume`.
    """
    if not snapshot.get("present"):
        return {
            "kind": "resume",
            "why": snapshot.get("reason") or "no precompact snapshot on disk",
            "evidence": None,
        }
    data = snapshot.get("data") or {}
    consumed_by = data.get("consumed_by")
    if consumed_by and consumed_by != continuation_uid:
        return {
            "kind": "resume",
            "why": f"snapshot already consumed by continuation {consumed_by[:12]}",
            "evidence": data.get("written_at"),
        }
    return {
        "kind": "compaction",
        "why": f"precompact snapshot written_at {data.get('written_at')} "
               f"(trigger={data.get('trigger')}), not yet consumed",
        "evidence": data.get("written_at"),
    }


def mark_snapshot_consumed(root: Path, slug: str, continuation_uid: str) -> None:
    """Stamp this continuation into the snapshot so it is claimed only once.

    Best-effort: a failure here must never break a continuation. The cost of
    missing the stamp is one extra `compaction` verdict, which is the safe
    direction — over-reporting a compaction wastes a read, under-reporting one
    skips it.
    """
    rel = Path("agents") / slug / ".tropo-capsule" / "workspace" / "precompact-snapshot.json"
    path = root / rel
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if data.get("consumed_by"):
            return
        data["consumed_by"] = continuation_uid
        data["consumed_at"] = _now()
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass


# --------------------------------------------------------------------------- #
# Identity card — item 4 (f015fcaf29b9): who/where you are, inline            #
# --------------------------------------------------------------------------- #

def _frontmatter(path: Path) -> dict:
    """First YAML frontmatter block of a governed file, as a dict. {} on none."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("\n---", 3)
        block = text[3:end]
    except ValueError:
        return {}
    fields: dict = {}
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip().strip("\"'")
    return fields


def identity_card(root: Path, slug: str, identity: dict) -> dict:
    """Party uid, root uid, unified entry, live sleeve, clone, remote, branch.

    Resolved from the activation pointer and the unified entry — the same
    files boot reads — never from memory. Absent fields degrade to None
    rather than refusing: a partial card beats reconstructing identity from
    four unnamed files by hand, which is the defect this closes.
    """
    card: dict = {
        "slug": slug,
        "generation": identity.get("gen"),
        "party_uid": None,
        "agent_root_uid": None,
        "unified_entry": None,
        "sleeve": identity.get("model"),
        "clone_path": str(root),
    }
    pointer = root / "agents" / slug / f"{slug}-activation.md"
    entry_rel: Optional[str] = None
    entry_uid: Optional[str] = None
    if pointer.is_file():
        entry_uid = _frontmatter(pointer).get("agent_uid")
    if not entry_uid:
        # Registry fallback: studios predating the thin-pointer shape carry
        # the agent_uid here. Resolution prefers the pointer, settles for
        # the registry, and degrades to a partial card over refusing.
        registry = (
            root / ".tropo-studio" / "registries" / "agent-registry.yaml"
        )
        if registry.is_file():
            m = re.search(
                rf"^\s*- name:\s*{re.escape(slug)}\s*$"
                r"(?:.*\n)*?^\s*agent_uid:\s*([0-9a-f]{8})\s*$",
                registry.read_text(encoding="utf-8", errors="replace"),
                re.M,
            )
            if m:
                entry_uid = m.group(1)
    if entry_uid:
        entry_rel = f"vault/agents/{entry_uid}.md"
        card["unified_entry"] = entry_rel
        entry_path = root / entry_rel
        if entry_path.is_file():
            efm = _frontmatter(entry_path)
            card["party_uid"] = efm.get("party_uid")
            card["agent_root_uid"] = efm.get("agent_root_uid")
            card["sleeve"] = efm.get("model") or card["sleeve"]
    if not card["sleeve"]:
        lineage_file = root / "agents" / slug / "lineage.jsonl"
        if lineage_file.is_file():
            for line in lineage_file.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("t") == "born" and str(row.get("gen")) == str(
                    card["generation"]
                ):
                    card["sleeve"] = row.get("model")
                    break
    card["emit_shape"] = (
        "tropo-emit-event.py --as <slug> --subject <party-uid> "
        "--correlationid <event-id> --final|--not-final"
    )
    card["git_discipline"] = (
        "fetch before you drain (git fetch origin), push after every emit; "
        "the local tree is a snapshot, origin/main is the bus"
    )
    return card


# --------------------------------------------------------------------------- #
# Derived read list — item 2: the specific current files, not folder pointers #
# --------------------------------------------------------------------------- #

# The retired v1/v2 memory surfaces. ONE list, used by the read-list builder
# below — there were two hand-maintained copies of this until 2026-09-07, which
# is the same "second source of truth" defect this tool exists to warn about.
#
# Where they live changed with the 2026-09-07 restructure: MEMORY.md is deleted
# outright (a stub whose only job was to say which surface is current, and which
# said the wrong one for four months), while memory-current.md and
# short-term-memory.jsonl move into history/. Agents not yet restructured
# (directors, and any capsule never cut over to v3) still have them at the top
# level, so both locations are probed and only what EXISTS is reported.
def _memory_surfaces():
    """The Phase-2 name resolver (f0153a6df07f), imported the way this tool
    already imports event_identity: lazily, so a partial toolchain degrades to
    an ImportError at the call rather than at module load."""
    lib_parent = Path(__file__).resolve().parent
    if str(lib_parent) not in sys.path:
        sys.path.insert(0, str(lib_parent))
    from lib import memory_surfaces  # type: ignore

    return memory_surfaces


# NOT part of the Phase-2 rename, and the annex's `silent-behaviour-change`
# reading of this tuple is wrong (talos-t65, 2026-09-08). These are AGENT-scope
# names, probed per agent folder; `memory-current.md` in an agent folder is the
# retired v2 file, which is what this list is for. The rename targets the
# STUDIO-scope `.tropo-studio/memory/memory-current.md`, a different file that
# this loop never looks at. The live trap is the opposite one: never add
# `memory.md` or `memories.jsonl` here, or the surface an agent must boot-read
# gets labelled "legacy — never boot-read" the moment step 2 lands.
ROLLBACK_SURFACES: tuple = (
    "memory-current.md",
    "short-term-memory.jsonl",
    "MEMORY.md",
    "living-transfer",
)


def _predecessor_generation(root: Path, slug: str, current: str) -> Optional[str]:
    """Last retired gen before the current born, from the lineage append log."""
    lineage_file = root / "agents" / slug / "lineage.jsonl"
    if not lineage_file.is_file():
        return None
    predecessor: Optional[str] = None
    for line in lineage_file.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = row.get("t")
        gen = str(row.get("gen", ""))
        if t == "retired":
            predecessor = gen
        elif t == "born" and gen == str(current):
            return predecessor
    return predecessor


def derive_read_list(root: Path, slug: str, identity: dict, card: dict) -> tuple:
    """(read_list, not_to_read). What the unified entry names as CURRENT.

    Ordered: soul-bearing entry first, then memory, then the predecessor
    letter, then doctrine. Each entry is a specific file, present or named
    as absent-with-reason — never a folder pointer a reader must interpret.
    """
    gen = identity.get("gen")
    # Phase 2 (f0153a6df07f): resolve memory.md, fall back to agent-memory.md.
    # A continuation hands its agent a read LIST — naming a file that is not
    # there is the one thing this function must never do, and after step 2 a
    # hardcoded old name would do exactly that for every agent in the studio.
    memory_rel = _memory_surfaces().agent_index(root, slug).relative_to(root).as_posix()
    predecessor = _predecessor_generation(root, slug, str(gen))
    letter_rel = (
        f"agents/{slug}/transfers/{predecessor}.md" if predecessor else None
    )
    read_list: list = []
    if card.get("unified_entry"):
        read_list.append(
            {
                "path": card["unified_entry"],
                "why": "your unified entry — §Charter identity, §Status-Notes current state",
            }
        )
    read_list.append(
        {
            "path": memory_rel,
            "why": "§Top-of-Mind carries the binding memory doctrine",
        }
    )
    if letter_rel:
        present = (root / letter_rel).is_file()
        read_list.append(
            {
                "path": letter_rel,
                "why": (
                    "your predecessor's handover letter"
                    if present
                    else "absent — your predecessor retired before the 2026-08-04 "
                    "cutover; read §Living-Transfer-from-Predecessor in the memory "
                    "surface instead (absence is not evidence no letter existed)"
                ),
            }
        )
    read_list.append(
        {
            "path": ".tropo/boot-digest.md",
            "why": "the binding doctrine digest (fingerprint-gated)",
        }
    )
    mem_dir = f"agents/{slug}/.tropo-capsule/memory"
    # Derived from ROLLBACK_SURFACES and from what is actually on disk, so a
    # restructured capsule and an un-migrated one both report truthfully. Naming
    # a file that is not there teaches a reader the tool does not know the tree.
    not_to_read = []
    for name in ROLLBACK_SURFACES:
        if name == "living-transfer":
            continue  # lives under transfers/, handled by the read list itself
        for rel in (f"{mem_dir}/{name}", f"{mem_dir}/history/{name}"):
            if (root / rel).exists():
                not_to_read.append({
                    "path": rel,
                    "why": "v1/v2 legacy — retained rollback, never boot-read",
                })
    return read_list, not_to_read


def _file_sha(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def reads_outstanding(root: Path, slug: str, read_list: list) -> int:
    """Reads not yet attested: absent attestation, unattested files, or drift.

    The attestation file is the one refresh_state() already reads
    (agents/<slug>/<slug>-compact-continue-activation.md). A read counts
    outstanding when its file exists, is not recorded there, or its hash
    has changed since it was.
    """
    attest = root / "agents" / slug / f"{slug}-compact-continue-activation.md"
    attested: dict = {}
    if attest.is_file():
        text = attest.read_text(encoding="utf-8", errors="replace")
        # Paired lines: `source: <rel>` (what refresh_state parses) beside
        # `source_hash: <rel> <sha256>` (what the outstanding-check parses).
        # The bare form stays authoritative for presence; the hash line adds
        # drift detection without breaking the other reader.
        attested = dict(
            re.findall(
                r"^\s*-?\s*source_hash:\s*(\S+)\s+([0-9a-f]{64})\s*$", text, re.M
            )
        )
    outstanding = 0
    for item in read_list:
        rel = item["path"]
        digest = _file_sha(root / rel)
        if digest is None:
            continue  # absent-with-reason entries carry no attestation duty
        if attested.get(rel) != digest:
            outstanding += 1
    return outstanding


# --------------------------------------------------------------------------- #
# Refresh — Phase-2 seam, interface only                                        #
# --------------------------------------------------------------------------- #

def refresh_state(root: Path, slug: str) -> dict:
    """``absent | stale | fresh``. Phase 1 never creates or edits the file."""
    rel = Path("agents") / slug / f"{slug}-compact-continue-activation.md"
    path = root / rel
    if not path.is_file():
        return {"status": "absent", "path": None, "sources_checked": []}
    text = path.read_text(encoding="utf-8", errors="replace")
    fingerprints = re.findall(
        r"^\s*-?\s*sources_fingerprint:\s*([0-9a-f]{64})\s*$", text, re.M
    )
    checked: list[dict] = []
    stale = False
    for line in re.findall(r"^\s*-?\s*source:\s*(\S+)\s*$", text, re.M):
        source = root / line
        checked.append({"source": line, "present": source.is_file()})
        if not source.is_file():
            stale = True
    if not fingerprints:
        stale = True
    return {
        "status": "stale" if stale else "fresh",
        "path": str(rel),
        "sources_checked": checked,
    }


# --------------------------------------------------------------------------- #
# Broadcast — exactly one per continuation UID                                  #
# --------------------------------------------------------------------------- #

def broadcast_exists(root: Path, continuation_uid: str) -> bool:
    """Dedupe on ``data.continuation_uid`` in the canonical event union only.

    No headline substring or top-level lookalike field can satisfy this: a
    crash-after-emit retry has to find the real payload or emit nothing.
    """
    lib = root / "vault" / "tools" / "lib"
    events: list[dict] = []
    if str(lib.parent) not in sys.path:
        sys.path.insert(0, str(lib.parent))
    try:
        from lib import event_identity  # type: ignore

        events = event_identity.load_event_union(root)
    except Exception:
        events = []
        for path in sorted((root / "vault" / "events").rglob("*.jsonl")):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    for event in events:
        if not isinstance(event, dict):
            continue
        data = event.get("data")
        if isinstance(data, dict) and data.get("continuation_uid") == continuation_uid:
            return True
    return False


def emit_broadcast(root: Path, slug: str, packet: Packet) -> tuple[str, str]:
    """Emit the one crew event. Failure is warn-safe, never fatal.

    Only ever called from the attest gesture — a continuation run alone
    never claims re-anchoring. The headline asserts reads attested because
    that is the only state from which this is reachable (item 3,
    f015fcaf29b9: the crew was previously told "re-anchored" before any
    read happened — a false signal by design).

    It does NOT assert a compaction. Whether one happened is derived from the
    PreCompact snapshot (see continuation_kind), because this tool cannot
    observe a compaction and used to claim one on every run — including plain
    resumes, which produced two false crew broadcasts in ten days.
    """
    if broadcast_exists(root, packet.continuation_uid):
        return "emitted", "already observed in the event union"
    tool = _tool(root, "tropo-emit-event.py")
    if not tool.is_file():
        return "pending", f"{tool} not found"
    kind = continuation_kind(packet.snapshot or {}, packet.continuation_uid)
    payload = {
        "category": "crew-state",
        "t": "continued",
        "agent": slug,
        "gen": packet.generation,
        "continuation_uid": packet.continuation_uid,
        "debts": packet.events.get("unanswered_reply_required", 0),
        "fetch_status": packet.git.get("fetch_status", "fetched"),
        "refresh": packet.refresh.get("status", "absent"),
        "reads_attested": True,
        "continuation_kind": kind["kind"],
        "kind_evidence": kind["why"],
        "headline": (
            f"{slug} {packet.generation} compacted and re-anchored (reads attested)"
            if kind["kind"] == "compaction"
            else f"{slug} {packet.generation} re-anchored on resume — NO compaction "
                 f"detected (reads attested); {kind['why']}"
        ),
    }
    proc = run(
        [
            sys.executable,
            tool,
            "--type",
            "tropo.broadcast.crew",
            "--source",
            f"/agents/{slug}",
            "--as",
            slug,
            "--lifecycle",
            "ephemeral",
            "--data",
            json.dumps(payload),
        ],
        root,
        timeout=120,
    )
    if proc.returncode != 0:
        return "pending", (proc.stderr or proc.stdout).strip()[:400]
    return "emitted", ""


# --------------------------------------------------------------------------- #
# The attest gesture — item 3: broadcast only after the reads are attested     #
# --------------------------------------------------------------------------- #

_ATTEST_BEGIN = (
    "<!-- BEGIN tropo-compact-continue attestation "
    "(auto-managed by --attest; safe to remove, recreated on next attest) -->"
)
_ATTEST_END = "<!-- END tropo-compact-continue attestation -->"


def _governed_uid(text: str) -> Optional[str]:
    """The uid: value if this file's YAML frontmatter declares one -- the
    marker of a real governed vault artifact (CLAUDE.md: 'Add a uid: to
    YAML frontmatter; the index picks it up'). None for a plain prior
    --attest pointer (no frontmatter at all in the pre-uid shape) or a
    file that does not exist. Read as raw text, not parsed as YAML: this
    function only ever needs to ANSWER "is this governed", never to
    understand the frontmatter's shape -- a real YAML parse-and-reserialize
    is exactly the lossy step (2026-09-07 incident, f0153f5ac5a6) that must
    never happen to a file this function says yes to."""
    if not text.startswith("---\n"):
        return None
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return None
    match = re.search(r"^\s*uid:\s*[\"']?(\S+?)[\"']?\s*$", text[3:end], re.M)
    return match.group(1) if match else None


def _attestation_header_and_body(
    slug: str, identity: dict, root: Path, read_list: list
) -> tuple:
    """(header_lines, body_lines): computed once, shared verbatim by both
    write paths below so the fresh-write and preserve-and-append shapes can
    never drift apart into two sources of the same fact. header is
    attested_at/attested_by; body is the source/hash/fingerprint content --
    unchanged from before this fix."""
    header = [
        f"attested_at: {_now()}",
        f"attested_by: {slug}-{identity.get('gen')}",
    ]
    body: list = []
    fingerprint_material: list[str] = []
    for item in read_list:
        digest = _file_sha(root / item["path"])
        if digest is None:
            body.append(f"# absent (no attestation duty): {item['path']}")
            continue
        body.append(f"source: {item['path']}")
        body.append(f"source_hash: {item['path']} {digest}")
        fingerprint_material.append(digest)
    combined = (
        hashlib.sha256("\n".join(fingerprint_material).encode()).hexdigest()
        if fingerprint_material
        else hashlib.sha256(b"no-sources").hexdigest()
    )
    body.append("")
    body.append(f"sources_fingerprint: {combined}")
    return header, body


def write_attestation(root: Path, slug: str, identity: dict, read_list: list) -> Path:
    """Write the activation file refresh_state() already looks for.

    Real fingerprints: every existing read-list file hashed at attest time.
    The gesture is the agent's own claim that the reads happened; the file
    records WHAT was attested, at which bytes, so drift afterwards is
    detectable by the next run's outstanding-check.

    GOVERNANCE-PRESERVING (f0153f5ac5a6, 2026-09-07): this path can be
    occupied by a real governed vault artifact minted here before compact-
    continue ever existed (it was, for talos: uid 4d1c8a37, a how-to entry,
    destroyed in place by this function's old unconditional overwrite on
    2026-09-07 -- the incident this fix exists to close). When the existing
    file declares a uid, its content and frontmatter are read as raw text
    and never touched -- no parse-and-reserialize, which is exactly the
    lossy step that caused the incident. The attestation is instead
    appended after whatever is already there, inside its own delimiters
    (or, on a later re-attest, replaced in place between those same
    delimiters, so re-attesting a governed file never grows it unbounded).
    Only when nothing governed occupies this path is the file written
    fresh, in the original simple shape -- unchanged behavior for the
    common case this incident was never about.
    """
    rel = Path("agents") / slug / f"{slug}-compact-continue-activation.md"
    path = root / rel
    existing = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    header, body = _attestation_header_and_body(slug, identity, root, read_list)

    if _governed_uid(existing) is not None:
        section = "\n".join(
            [_ATTEST_BEGIN, "", "## Compact-continue read attestation", "",
             "Written by `--attest` after the derived read list was actually "
             "read. refresh_state() reads the source lines below; the paired "
             "source_hash lines give the outstanding-check its drift "
             "detection.", ""]
            + header + [""] + body
            + [_ATTEST_END]
        ) + "\n"
        begin_at = existing.find(_ATTEST_BEGIN)
        end_marker_at = existing.find(_ATTEST_END, begin_at) if begin_at != -1 else -1
        if begin_at != -1 and end_marker_at != -1:
            after = end_marker_at + len(_ATTEST_END)
            new_text = existing[:begin_at] + section + existing[after:].lstrip("\n")
        else:
            separator = "\n" if existing.endswith("\n") else "\n\n"
            new_text = existing + separator + section
        path.write_text(new_text, encoding="utf-8")
        return path

    lines = (
        ["---", f"agent: {slug}", f"generation: {identity.get('gen')}"]
        + header
        + ["---", "", "# Compact-continue read attestation", "",
           "Written by `--attest` after the derived read list was actually read.",
           "refresh_state() reads the source lines below; the paired source_hash",
           "lines give the outstanding-check its drift detection.", ""]
        + body
        + [""]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def attest_reads(root: Path, slug: str) -> Packet:
    """`--attest`: record the reads, then and only then emit the broadcast.

    Refuses when there is no continuation journal to attest against — an
    attestation with no continuation behind it is just a broadcast license.
    """
    slug = slug.strip().lower()
    identity = read_live_generation(root, slug)
    generation = str(identity["gen"]).strip()
    activation = find_activation_run(root, slug, generation)

    lock = acquire_lock(root, slug, generation)
    try:
        journal = load_or_open_journal(root, slug, generation, activation["run_uid"])
        packet = Packet(
            agent=slug,
            generation=generation,
            continuation_uid=journal["continuation_uid"],
            activation_run=activation,
        )
        packet.snapshot = read_snapshot(root, slug)
        packet.git = git_state(root)
        packet.identity = identity_card(root, slug, identity)
        packet.read_list, packet.not_to_read = derive_read_list(
            root, slug, identity, packet.identity
        )
        packet.refresh = refresh_state(root, slug)

        write_attestation(root, slug, identity, packet.read_list)
        packet.reads_outstanding = reads_outstanding(root, slug, packet.read_list)
        if packet.reads_outstanding:
            packet.status = "attest-refused-drift"
            packet.broadcast = "held"
            return packet

        summary, _raw = drain_events(
            root, slug, local_only=packet.git["fetch_status"] != "fetched"
        )
        packet.events = summary
        state, detail = emit_broadcast(root, slug, packet)
        packet.broadcast = state
        if state == "emitted":
            # Claim the snapshot so a later resume cannot inherit this
            # compaction's evidence and re-announce a compaction that already
            # happened. Stamped only after the broadcast actually lands.
            mark_snapshot_consumed(root, slug, packet.continuation_uid)
            packet.status = "attested"
            clear_journal(root, slug, generation)
        else:
            packet.status = "attested-degraded"
            journal["broadcast_pending"] = detail
            save_journal(root, slug, generation, journal)
        return packet
    finally:
        release_lock(lock)


# --------------------------------------------------------------------------- #
# The gesture                                                                   #
# --------------------------------------------------------------------------- #

def continue_session(root: Path, slug: str) -> Packet:
    slug = slug.strip().lower()
    identity = read_live_generation(root, slug)
    generation = str(identity["gen"]).strip()
    activation = find_activation_run(root, slug, generation)

    lock = acquire_lock(root, slug, generation)
    try:
        journal = load_or_open_journal(root, slug, generation, activation["run_uid"])
        save_journal(root, slug, generation, journal)

        packet = Packet(
            agent=slug,
            generation=generation,
            continuation_uid=journal["continuation_uid"],
            activation_run=activation,
        )
        packet.snapshot = read_snapshot(root, slug)
        packet.git = git_state(root)
        journal["phases"].append("git")
        save_journal(root, slug, generation, journal)

        summary, raw = drain_events(
            root, slug, local_only=packet.git["fetch_status"] != "fetched"
        )
        # Durable spool BEFORE any later phase can crash the process.
        journal["events_raw"] = raw
        journal["phases"].append("events")
        save_journal(root, slug, generation, journal)
        packet.events = summary

        packet.recent_commits = recent_commits(root, slug, generation)
        packet.identity = identity_card(root, slug, identity)
        packet.read_list, packet.not_to_read = derive_read_list(
            root, slug, identity, packet.identity
        )
        packet.reads_outstanding = reads_outstanding(root, slug, packet.read_list)
        packet.refresh = refresh_state(root, slug)
        packet.pointers = {
            "retirement_playbook": RETIREMENT_PLAYBOOK,
            "event_mechanics": EVENT_MECHANICS_POINTER,
            "attest_command": (
                f"python3 vault/tools/tropo-compact-continue.py "
                f"--agent {slug} --attest"
            ),
        }

        # Item 3 (f015fcaf29b9): the broadcast is HELD until --attest. A run
        # that only names pointers has not re-anchored anything; the crew is
        # not told otherwise. The journal survives so --attest can pick up
        # this exact continuation uid. Only a prior attestation whose
        # fingerprints still cover these bytes earns plain "continued" —
        # zero outstanding files is not attestation, it is nothing to read.
        packet.broadcast = "held"
        # Status reads the HASH-BASED drift detector, never refresh_state():
        # refresh_state is presence-only (files exist) and cannot see content
        # drift after attest — T64's second-read defect, reproduced live. Plain
        # "continued" requires an attestation on record AND zero outstanding
        # (hashes matching); drift or no attestation -> pending-attest.
        attested_current = (
            packet.refresh.get("status") != "absent"
            and packet.reads_outstanding == 0
        )
        packet.status = "continued" if attested_current else "continued-pending-attest"
        journal["broadcast_pending"] = "awaiting --attest (reads outstanding)"
        journal["phases"].append("broadcast-held")
        save_journal(root, slug, generation, journal)
        return packet
    finally:
        release_lock(lock)


def render_human(packet: Packet) -> str:
    git = packet.git
    ident = packet.identity or {}
    snap = packet.snapshot or {}
    lines = [
        "=" * 72,
        f"Compact-Continue — {packet.agent} {packet.generation} "
        f"({'same session, same generation' if packet.same_session else '?'})",
        "=" * 72,
        "",
        "PRECOMPACT SNAPSHOT (what this session knew when compaction hit):",
    ]
    if snap.get("present"):
        data = snap.get("data") or {}
        lines.append(f"  written:       {data.get('written_at', 'unknown')} (trigger: {data.get('trigger', '?')})")
        open_rr = data.get("open_reply_required")
        if open_rr:
            lines.append(f"  open rr:       {json.dumps(open_rr)[:100]}")
        pipeline = data.get("pipeline_work")
        if pipeline:
            lines.append(f"  pipeline:      {json.dumps(pipeline)[:100]}")
        lines.append(f"  full:          {snap.get('path')}")
        lines.append("  (the delta between this and the fresh state below is yours to read)")
    else:
        lines.append(f"  {snap.get('reason', 'absent')} — {snap.get('path', '')}")
    lines += [
        "",
        "IDENTITY CARD (who and where you are — read this first):",
        f"  agent:         {packet.agent} ({packet.generation})",
        f"  party uid:     {ident.get('party_uid') or 'UNRESOLVED — resolve before emitting'}",
        f"  root uid:      {ident.get('agent_root_uid') or 'unknown'}",
        f"  unified entry: {ident.get('unified_entry') or 'unknown'}",
        f"  sleeve:        {ident.get('sleeve') or 'unknown'}",
        f"  clone:         {ident.get('clone_path', '')}",
        f"  git:           branch {git.get('branch', '?')} | remote "
        f"{git.get('remote', '?')} | fetch {git.get('fetch_status', '?')}"
        + (f" — {git.get('fetch_error')}" if git.get("fetch_error") else ""),
        f"  discipline:    {ident.get('git_discipline', '')}",
        f"  emit shape:    {ident.get('emit_shape', '')}",
        "",
        f"Status:        {packet.status}",
        f"Continuation:  {packet.continuation_uid}",
        f"Activation:    {packet.activation_run.get('run_uid', '')} "
        f"({packet.activation_run.get('path', '')})",
        f"Lineage:       unchanged (nothing born, nothing retired)",
        "",
        f"               local {git.get('local_sha', '')[:8]} | "
        f"origin/main {git.get('remote_sha', '')[:8]} | "
        f"ahead {git.get('ahead')} behind {git.get('behind')}",
        f"               dirty {len(git.get('dirty_tracked', []))} tracked, "
        f"{len(git.get('untracked', []))} untracked",
        "",
        f"Events:        {packet.events.get('state', '?')} | "
        f"{packet.events.get('new_events', 0)} new | "
        f"{packet.events.get('unanswered_reply_required', 0)} unanswered reply_required",
    ]
    if packet.events.get("state") == "local-only":
        lines.append(
            "               fetch failed: remote debt is NOT known to be zero"
        )
    for debt in packet.events.get("debts", [])[:5]:
        lines.append(f"                 - {debt['id']} {debt['from']}: {debt['headline']}")
    lines.append("")
    lines.append("Recent work:")
    for commit in packet.recent_commits:
        lines.append(
            f"                 {commit['sha']} [{commit['ownership']}] {commit['subject']}"
        )
    lines.append("")
    lines.append("READ LIST — these specific files, in order (then attest):")
    for item in packet.read_list:
        lines.append(f"  read:    {item['path']}")
        lines.append(f"           ({item['why']})")
    for item in packet.not_to_read:
        lines.append(f"  NOT read: {item['path']} — {item['why']}")
    lines.append("")
    if packet.reads_outstanding:
        lines.append(
            f"NOT re-anchored: {packet.reads_outstanding} read(s) outstanding."
        )
        lines.append(
            "  The crew is NOT told you are re-anchored until they are done."
        )
    elif packet.refresh.get("status") != "absent":
        lines.append("Reads attested for these bytes (broadcast dedupe owns re-emits).")
    else:
        lines.append("No attestation on record — run --attest after the reads.")
    lines.append(f"Attest:        {packet.pointers.get('attest_command', '--attest')}")
    lines.append(f"Broadcast:     {packet.broadcast}")
    lines.append(f"Refresh:       {packet.refresh.get('status', 'absent')}")
    lines.append(f"Retirement:    {packet.pointers.get('retirement_playbook', '')}")
    lines.append(f"Events how-to: {packet.pointers.get('event_mechanics', '')}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Same-session re-anchor after context compaction. Never births, "
            "retires, or writes lineage."
        )
    )
    # Required for a continuation, but --print-trigger is a pure read that
    # harness authors and the trigger-copy validator call without an agent.
    parser.add_argument("--agent", default=None, help="agent slug (required)")
    parser.add_argument("--json", action="store_true", help="emit the packet as JSON")
    parser.add_argument("--studio", default=None, help="studio root (default: auto)")
    parser.add_argument(
        "--print-trigger",
        action="store_true",
        help="print the canonical trigger line and exit",
    )
    parser.add_argument(
        "--attest",
        action="store_true",
        help=(
            "after doing the read list: record the attestation (real "
            "fingerprints) and emit the held broadcast. Without this flag "
            "the run never claims re-anchored."
        ),
    )
    args = parser.parse_args(argv)

    if args.print_trigger:
        print(TRIGGER_LINE)
        return 0
    if not args.agent:
        parser.error("--agent is required (the tool never infers an agent slug)")

    try:
        root = resolve_studio_root(args.studio)
        packet = (
            attest_reads(root, args.agent)
            if args.attest
            else continue_session(root, args.agent)
        )
    except ContinueRefusal as exc:
        if args.json:
            print(json.dumps({"status": "refused", "reason": str(exc)}, indent=2))
        else:
            print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(packet.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_human(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
