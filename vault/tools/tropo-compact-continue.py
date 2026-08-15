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
cli_command: "python3 vault/tools/tropo-compact-continue.py --agent <slug> [--json] [--studio PATH]"
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
description: "One-command same-generation recovery after a context compaction. Reads the live generation from tropo-lineage.py who, corroborates it against the exact completed activation run, fetches before draining events, reports divergence/dirty state/reply_required debts/recent self-attributed commits/refresh state, and emits exactly one crew broadcast per continuation UID. It has no path to born and writes no lineage."
domain_tags:
  - compact-continue
  - re-anchor
  - lifecycle
  - same-session
trigger_description: "Reach for this the moment a session was compacted or an agent cannot remember completing boot. Run it BEFORE any other work and never run born: born mints a phantom successor for a session that is still alive. Also correct when an imminent auto-compact warning appears — context pressure routes here, not to retirement."
created: 2026-08-12
created_by: talos-t41
modified: 2026-08-12
modified_by: talos-t41
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
    "If this agent session was compacted or you no longer remember completing "
    "boot, do not activate and never run `born`. Run `python3 "
    "vault/tools/tropo-compact-continue.py --agent <slug>` before any other work."
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
    "python3 vault/tools/tropo-check-events.py --as <slug> "
    "(reply with tropo-emit-event.py --final/--not-final)"
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
    activation_run: dict = field(default_factory=dict)
    git: dict = field(default_factory=dict)
    events: dict = field(default_factory=dict)
    recent_commits: list = field(default_factory=list)
    refresh: dict = field(default_factory=dict)
    broadcast: str = "pending"
    lineage_written: bool = False
    pointers: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "agent": self.agent,
            "generation": self.generation,
            "same_session": self.same_session,
            "same_generation": self.same_generation,
            "continuation_uid": self.continuation_uid,
            "activation_run": self.activation_run,
            "git": self.git,
            "events": self.events,
            "recent_commits": self.recent_commits,
            "refresh": self.refresh,
            "broadcast": self.broadcast,
            "lineage_written": self.lineage_written,
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
    pattern = f"agent-activation-{slug.lower()}-{generation}-*"
    complete: list[dict] = []
    partial: list[str] = []
    for candidate in sorted(runs_dir.glob(pattern)) if runs_dir.is_dir() else []:
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
    """Emit the one crew event. Failure is warn-safe, never fatal."""
    if broadcast_exists(root, packet.continuation_uid):
        return "emitted", "already observed in the event union"
    tool = _tool(root, "tropo-emit-event.py")
    if not tool.is_file():
        return "pending", f"{tool} not found"
    payload = {
        "category": "crew-state",
        "t": "continued",
        "agent": slug,
        "gen": packet.generation,
        "continuation_uid": packet.continuation_uid,
        "debts": packet.events.get("unanswered_reply_required", 0),
        "fetch_status": packet.git.get("fetch_status", "fetched"),
        "refresh": packet.refresh.get("status", "absent"),
        "headline": f"{slug} {packet.generation} compacted and re-anchored",
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
        packet.refresh = refresh_state(root, slug)
        packet.pointers = {
            "retirement_playbook": RETIREMENT_PLAYBOOK,
            "event_mechanics": EVENT_MECHANICS_POINTER,
            "refresh_full_reads": (
                []
                if packet.refresh["status"] == "fresh"
                else [
                    f"vault/agents/<{slug}-unified-entry>.md",
                    f"agents/{slug}/.tropo-capsule/memory/",
                    ".tropo/boot-digest.md",
                    f"agents/{slug}/transfers/",
                ]
            ),
        }

        state, detail = emit_broadcast(root, slug, packet)
        packet.broadcast = state
        if state == "emitted":
            packet.status = "continued"
            clear_journal(root, slug, generation)
        else:
            packet.status = "continued-degraded"
            journal["broadcast_pending"] = detail
            journal["phases"].append("broadcast-pending")
            save_journal(root, slug, generation, journal)
        return packet
    finally:
        release_lock(lock)


def render_human(packet: Packet) -> str:
    git = packet.git
    lines = [
        "=" * 72,
        f"Compact-Continue — {packet.agent} {packet.generation} "
        f"({'same session, same generation' if packet.same_session else '?'})",
        "=" * 72,
        f"Status:        {packet.status}",
        f"Continuation:  {packet.continuation_uid}",
        f"Activation:    {packet.activation_run.get('run_uid', '')} "
        f"({packet.activation_run.get('path', '')})",
        f"Lineage:       unchanged (nothing born, nothing retired)",
        "",
        f"Git:           branch {git.get('branch', '?')} | fetch "
        f"{git.get('fetch_status', '?')}"
        + (f" — {git.get('fetch_error')}" if git.get("fetch_error") else ""),
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
    lines.append(f"Refresh:       {packet.refresh.get('status', 'absent')}")
    for full_read in packet.pointers.get("refresh_full_reads", []):
        lines.append(f"                 read in full: {full_read}")
    lines.append(f"Broadcast:     {packet.broadcast}")
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
    args = parser.parse_args(argv)

    if args.print_trigger:
        print(TRIGGER_LINE)
        return 0
    if not args.agent:
        parser.error("--agent is required (the tool never infers an agent slug)")

    try:
        root = resolve_studio_root(args.studio)
        packet = continue_session(root, args.agent)
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
