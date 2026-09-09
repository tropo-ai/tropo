#!/usr/bin/env python3
"""
---
uid: f0157a0d3671
title: precompact-snapshot — Tool
name: precompact-snapshot
type: tool
status: active
owner: talos
domain: "Write the machine-knowable half of a transfer the moment compaction is imminent, not after. Fired from the PreCompact hook wired in .claude/settings.json (talos, 2026-09-07, at Mike's direct word); this file is the standalone CLI the hook calls, resolving its own agent slug from .tropo/flags/resident.json since the hook command is written once and cannot know that ahead of time. Never births, retires, writes lineage, or touches the network."
spawnable_by:
  - all-executives
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-precompact-snapshot.py [--agent <slug>] [--trigger manual|auto] [--studio PATH] [--json]"
script_path: vault/tools/tropo-precompact-snapshot.py
belt: true
belt_invocation: "python3 vault/tools/tropo-precompact-snapshot.py"
belt_example: "python3 vault/tools/tropo-precompact-snapshot.py --agent talos --trigger auto"
input:
  type: object
  properties:
    agent:
      type: string
      description: "Agent slug to snapshot. Optional — defaults to .tropo/flags/resident.json. The real hook invocation never passes this: the command is written once in settings.json with no way to know ahead of time which agent is resident."
    trigger:
      type: string
      description: "manual | auto | unknown — read from the PreCompact hook's own stdin JSON (session_id/transcript_path/cwd/hook_event_name/trigger/custom_instructions), recorded not interpreted. --trigger overrides this for manual testing; the real hook invocation pipes stdin and never passes the flag."
    json:
      type: boolean
      description: "Also print the snapshot to stdout as JSON."
destructive: false
audit_required: false
writes_scope:
  - agents/*/.tropo-capsule/workspace/precompact-snapshot.json
governance_category: lifecycle
description: "f015fcaf29b9 item 5. Writes agents/<slug>/.tropo-capsule/workspace/precompact-snapshot.json: identity card, git state (local reads only — no fetch), recent self-attributed commits, every open reply_required id (local event union, no fetch), any pipeline-run this agent is the most recent actor on with its current step, and origin-watch state (honestly recorded as unknowable — watches are ephemeral background processes with no persistent record; see WAKE-DISCIPLINE.md). tropo-compact-continue.py reads this back and prints it FIRST, before re-deriving fresh truth, so the next boot can see the delta between what this session knew at compaction and what changed since. Deliberately network-free and best-effort: a hook that can time out or whose exit code besides 2 never blocks compaction must not gate on git fetch or a heavy drain, and a partial snapshot beats none — every section degrades to a recorded reason rather than raising."
domain_tags:
  - compact-continue
  - precompact
  - re-anchor
  - lifecycle
  - same-session
trigger_description: "Called by the PreCompact hook wired in .claude/settings.json, once per compaction, for both manual (/compact, /clear) and automatic (context-limit) triggers — verified against the Claude Code hooks docs directly (both before this tool was built and again before the hook was wired): PreCompact fires reliably in both cases, receives {session_id, transcript_path, cwd, hook_event_name, trigger: manual|auto, custom_instructions} on stdin (this tool reads it, bounded by select() so a manual run missing stdin can never hang), and its output cannot steer the compaction summary or reach the model at all, block or no block (a hard architectural boundary, not a gap in this tool) — hence writing beside the summary rather than attempting to ride into it. Also runnable by hand for a rehearsal or a manual pre-compact checkpoint, with --agent/--trigger overriding resident.json/stdin."
created: 2026-09-07
created_by: talos-t64
governed_by: d5e1b4a3
member_of:
  - 8dd772a0
schema_version: 2
extraction_scope: ship
refs:
  - d5f8fe55
  - f015fcaf29b9
  - 4d5ff95d
tags:
  - tool
  - cli
  - precompact
  - lifecycle
subsystem_hub:
  - 8dd772a0
---
"""

from __future__ import annotations

"""precompact-snapshot — f015fcaf29b9 item 5.

WHY THIS EXISTS. Two independent compactions on 2026-09-06 lost context at
exactly the moment nothing was watching: the agent's own working memory of
what it was mid-doing (an open reply_required thread, a pipeline step it had
started) evaporated with the context window, and nothing on disk had
captured it. compact-continue (4d5ff95d) re-derives FRESH truth on the next
boot, and does it well — but "fresh" is not "what this session knew right
before it lost its memory". A hard crash, a long gap before the next boot, or
simply wanting to see the delta all need that earlier snapshot to exist.

WHY NETWORK-FREE, DELIBERATELY, UNLIKE compact-continue. This tool is called
from a hook that fires synchronously before compaction proceeds. Per the
Claude Code hooks contract (verified before building this, not assumed):
exit code 2 blocks compaction, anything else does not, and hook output
cannot influence the summary regardless of exit code. A slow or hanging
`git fetch` inside a hook risks eating the hook's timeout budget for zero
benefit -- remote truth is safely recoverable at the NEXT boot regardless,
which is exactly when compact-continue already fetches. What this tool
captures is precisely the LOCAL, in-session state that boot cannot
reconstruct any other way. Every section is best-effort: a failure in one
degrades that section with a recorded reason and never raises past main().

WHAT THIS DOES NOT DO. It does not decide the hook is CORRECT to fire, does
not touch the network, does not write lineage, does not birth or retire, and
does not attempt to influence the compaction summary -- verified as
architecturally impossible before this was designed, so the snapshot sits
BESIDE the summary as a file compact-continue reads back, not inside it.
"""

import argparse
import importlib.util
import json
import re
import select
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

TOOL_UID = "f0157a0d3671"
TOOLS_DIR = Path(__file__).resolve().parent

# Pipeline-run scan bound: this is a best-effort "which run were you touching"
# lookup, not an index. Capped so a studio with thousands of historical runs
# cannot turn a hook-fired tool into a slow directory walk.
PIPELINE_RUN_SCAN_LIMIT = 60
RECENT_COMMIT_LIMIT = 8


def resolve_studio_root(explicit: Optional[str] = None) -> Path:
    if explicit:
        root = Path(explicit).resolve()
        if not (root / "agents").is_dir():
            raise SystemExit(f"REFUSED: {root} has no agents/ — not a Studio root")
        return root
    here = Path(__file__).resolve()
    for candidate in [here.parent.parent.parent] + list(here.parents):
        if (candidate / "agents").is_dir() and (candidate / "vault").is_dir():
            return candidate
    raise SystemExit("REFUSED: could not resolve Studio root from this file's location")


def _load_sibling(root: Path, filename: str, module_name: str):
    """Dynamically load a hyphenated sibling tool for its pure functions.
    One implementation of each fact (identity resolution, git state shape,
    the unanswered-reply scan) rather than a second copy that can drift from
    the one compact-continue and check-events already got right."""
    path = root / "vault" / "tools" / filename
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _run(args: list, cwd: Path, timeout: int = 15) -> subprocess.CompletedProcess:
    """Same no-shell discipline as compact-continue: argument arrays only,
    short timeouts (this tool must return fast from inside a hook)."""
    try:
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Git state — LOCAL READS ONLY, no fetch (see module docstring for why)         #
# --------------------------------------------------------------------------- #

def local_git_state(root: Path) -> dict:
    state: dict[str, Any] = {
        "fetched": False,
        "note": "no git fetch — precompact must return fast; origin/main here "
                "is whatever the last fetch (by any process) left on disk, "
                "not necessarily current. compact-continue fetches fresh.",
        "branch": None,
        "remote": None,
        "local_sha": None,
        "remote_sha_last_known": None,
        "ahead": None,
        "behind": None,
        "dirty_tracked": [],
        "untracked": [],
    }
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    if branch.returncode == 0:
        state["branch"] = branch.stdout.strip()
    remote_url = _run(["git", "remote", "get-url", "origin"], root)
    if remote_url.returncode == 0:
        state["remote"] = remote_url.stdout.strip()
    local = _run(["git", "rev-parse", "HEAD"], root)
    if local.returncode == 0:
        state["local_sha"] = local.stdout.strip()
    # origin/main as last recorded locally — a stale read is a KNOWN stale
    # read (the field name says so), not a silent wrong answer.
    remote = _run(["git", "rev-parse", "origin/main"], root)
    if remote.returncode == 0:
        state["remote_sha_last_known"] = remote.stdout.strip()
        counts = _run(
            ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"], root
        )
        if counts.returncode == 0:
            parts = counts.stdout.split()
            if len(parts) == 2:
                state["behind"], state["ahead"] = int(parts[0]), int(parts[1])
    status = _run(["git", "status", "--porcelain"], root)
    if status.returncode == 0:
        for line in status.stdout.splitlines():
            if not line.strip():
                continue
            if line.startswith("??"):
                state["untracked"].append(line[3:])
            else:
                state["dirty_tracked"].append(line[3:].strip() or line[2:].strip())
    return state


# --------------------------------------------------------------------------- #
# Open reply_required — local event union, no fetch                            #
# --------------------------------------------------------------------------- #

def open_reply_required(root: Path, slug: str, check_events_mod) -> dict:
    result: dict[str, Any] = {
        "resolved": False,
        "party_uid": None,
        "agent_root_uid": None,
        "count": 0,
        "ids": [],
        "note": "local event union only, no fetch — may miss anything another "
                "machine pushed since this session's own last drain",
    }
    if check_events_mod is None:
        result["note"] = "tropo-check-events.py not found; section skipped"
        return result
    try:
        party_uid, agent_root_uid = check_events_mod.resolve_identity(slug)
    except SystemExit:
        result["note"] = f"could not resolve identity for {slug!r}"
        return result
    result["resolved"] = True
    result["party_uid"] = party_uid
    result["agent_root_uid"] = agent_root_uid
    try:
        unanswered = check_events_mod.scan_unanswered_rr(party_uid, agent_root_uid)
    except Exception as exc:  # noqa: BLE001 — best-effort section, never raise past main()
        result["note"] = f"scan failed: {exc}"[:300]
        return result
    result["count"] = len(unanswered)
    for event in unanswered[:20]:
        data = event.get("data") or {}
        result["ids"].append({
            "id": event.get("id", ""),
            "from": data.get("from", ""),
            "headline": str(data.get("headline") or "")[:120],
        })
    return result


# --------------------------------------------------------------------------- #
# Pipeline work — best-effort: which run was this agent most recently touching #
# --------------------------------------------------------------------------- #

def current_pipeline_work(root: Path, slug: str, generation: Optional[str]) -> dict:
    result: dict[str, Any] = {
        "resolved": False,
        "run_folder": None,
        "run_status": None,
        "current_step": None,
        "eligible_steps": [],
        "last_actor_event_ts": None,
        "note": "best-effort: the most recently modified run.jsonl naming this "
                "agent's slug or slug-generation as actor in its own recent "
                "rows, scanned local-only and bounded — not an index",
    }
    runs_dir = root / "vault" / "pipeline-runs"
    if not runs_dir.is_dir():
        result["note"] = "no vault/pipeline-runs/ directory"
        return result
    candidates = sorted(
        (p for p in runs_dir.iterdir() if p.is_dir()),
        key=lambda p: (p / "run.jsonl").stat().st_mtime
        if (p / "run.jsonl").is_file() else 0,
        reverse=True,
    )[:PIPELINE_RUN_SCAN_LIMIT]
    slug_l = slug.lower()
    gen_actor = f"{slug_l}-{generation.lower()}" if generation else None
    for run_dir in candidates:
        journal = run_dir / "run.jsonl"
        if not journal.is_file():
            continue
        last_match_ts = None
        try:
            lines = journal.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines[-200:]:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            actor = str(row.get("actor") or "").lower()
            if actor == slug_l or (gen_actor and actor == gen_actor):
                last_match_ts = row.get("ts") or row.get("timestamp") or last_match_ts
        if last_match_ts is None:
            continue
        state_path = run_dir / "run.state.json"
        state: dict = {}
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8")) or {}
            except (OSError, ValueError):
                state = {}
        result.update({
            "resolved": True,
            "run_folder": str(run_dir.relative_to(root)),
            "run_status": state.get("run_status"),
            "current_step": state.get("current_step"),
            "eligible_steps": state.get("eligible_steps") or [],
            "last_actor_event_ts": last_match_ts,
        })
        return result
    result["note"] += "; no run in the scanned set names this agent as actor"
    return result


def origin_watch_state() -> dict:
    return {
        "resolved": False,
        "note": "not observable from disk by design — an origin watch (per "
                "WAKE-DISCIPLINE.md) is an ephemeral background process this "
                "session started; the doctrine keeps no persistent record of "
                "one being armed. Honest absence, not a missing feature.",
    }


def build_snapshot(root: Path, slug: str, trigger: str) -> dict:
    compact_mod = _load_sibling(
        root, "tropo-compact-continue.py", "compact_continue_for_snapshot")
    check_events_mod = _load_sibling(
        root, "tropo-check-events.py", "check_events_for_snapshot")

    generation = None
    identity: dict = {"note": "tropo-compact-continue.py not found; identity "
                               "card unavailable"}
    if compact_mod is not None:
        try:
            live = compact_mod.read_live_generation(root, slug)
            generation = str(live.get("gen") or "") or None
            identity = compact_mod.identity_card(root, slug, live)
        except Exception as exc:  # noqa: BLE001 — best-effort, never raise
            identity = {"note": f"identity resolution failed: {exc}"[:300]}

    recent_commits: list = []
    if compact_mod is not None and generation:
        try:
            recent_commits = compact_mod.recent_commits(
                root, slug, generation, limit=RECENT_COMMIT_LIMIT)
        except Exception as exc:  # noqa: BLE001
            recent_commits = [{"error": f"recent_commits failed: {exc}"[:300]}]

    snapshot = {
        "written_by": "tropo-precompact-snapshot.py",
        "tool_uid": TOOL_UID,
        "written_at": _now(),
        "agent": slug,
        "generation": generation,
        "trigger": trigger,
        "identity": identity,
        "git": local_git_state(root),
        "recent_commits": recent_commits,
        "open_reply_required": open_reply_required(root, slug, check_events_mod),
        "pipeline_work": current_pipeline_work(root, slug, generation),
        "origin_watch": origin_watch_state(),
    }
    return snapshot


def write_snapshot(root: Path, slug: str, snapshot: dict) -> Path:
    agent_dir = root / "agents" / slug
    if not agent_dir.is_dir():
        # Never mint a phantom agent folder from a mistyped --agent. An
        # unresolvable identity already degraded every other section above;
        # refusing the write is the one thing this function does that is not
        # "record a reason and continue" -- because continuing here means
        # creating governed-adjacent structure for an identity that does not
        # exist, which is worse than a missing snapshot.
        raise LookupError(f"no agents/{slug}/ on disk — refusing to create one")
    workspace = agent_dir / ".tropo-capsule" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "precompact-snapshot.json"
    # Atomic write: a hook that gets killed mid-write must never leave a
    # truncated snapshot that reads as valid JSON with half its fields gone.
    staged = target.with_name("." + target.name + ".tmp")
    staged.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    staged.replace(target)
    return target


def render_human(snapshot: dict, target: Path) -> str:
    git = snapshot.get("git") or {}
    rr = snapshot.get("open_reply_required") or {}
    pipe = snapshot.get("pipeline_work") or {}
    lines = [
        f"precompact-snapshot: {snapshot.get('agent')} "
        f"{snapshot.get('generation') or '?'} — written {snapshot.get('written_at')} "
        f"(trigger={snapshot.get('trigger')})",
        f"  -> {target}",
        f"  git: branch {git.get('branch')} | dirty {len(git.get('dirty_tracked', []))} "
        f"tracked, {len(git.get('untracked', []))} untracked | "
        f"ahead {git.get('ahead')} behind {git.get('behind')} (last-known origin)",
        f"  open reply_required: {rr.get('count', 0)}",
        f"  pipeline work: "
        + (f"{pipe.get('run_folder')} step={pipe.get('current_step')}"
           if pipe.get("resolved") else "none found"),
    ]
    return "\n".join(lines)


def _resolve_resident_agent(root: Path) -> str:
    """The real PreCompact hook command is written once in settings.json and
    fires unattended -- it cannot know ahead of time which agent slug is
    resident in this clone (that changes across births/retirements). Read
    the same marker the boot topology already maintains for exactly this
    (WAKE-DISCIPLINE v1.2.0 one-agent-one-clone) rather than hardcode a slug
    into the hook command, which would go silently wrong the day this clone's
    resident agent changes. Raises on any failure -- caught by main()'s
    existing degrade-and-exit-0 handling, same as every other setup failure.
    """
    flag_path = root / ".tropo" / "flags" / "resident.json"
    data = json.loads(flag_path.read_text(encoding="utf-8"))
    slug = data.get("agent")
    if not slug or not isinstance(slug, str):
        raise ValueError(f"{flag_path} names no usable 'agent' field")
    return slug


def _read_stdin_hook_payload() -> dict:
    """Best-effort read of the PreCompact hook's own stdin JSON contract:
    {session_id, transcript_path, cwd, hook_event_name, trigger,
    custom_instructions}. A real hook invocation always pipes this and
    closes stdin immediately; a manual/test invocation may leave stdin
    open with nothing arriving. select() bounds the wait so a bare manual
    run can never hang -- this must never be the reason a hook is slow.
    Degrades to {} on anything but a clean parse: not-ready, empty, bad
    JSON, or a non-object payload.
    """
    try:
        if sys.stdin.isatty():
            return {}
        ready, _, _ = select.select([sys.stdin], [], [], 0.2)
        if not ready:
            return {}
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Write the machine-knowable half of a transfer, the moment "
            "compaction is imminent. Never births, retires, or touches the "
            "network. Always exits 0 — this tool must never be the reason a "
            "PreCompact hook blocks compaction."
        )
    )
    parser.add_argument(
        "--agent", default=None,
        help="agent slug. Optional -- defaults to the resident agent named "
             "in .tropo/flags/resident.json. The real hook invocation never "
             "passes this: the command is written once in settings.json and "
             "has no way to know ahead of time which agent is resident.")
    parser.add_argument(
        "--trigger", default=None, choices=["manual", "auto", "unknown"],
        help="override the trigger instead of reading it from the hook's "
             "own stdin JSON (manual testing only -- a real hook invocation "
             "never passes this either, it pipes stdin)")
    parser.add_argument("--studio", default=None, help="studio root (default: auto)")
    parser.add_argument("--json", action="store_true",
                        help="also print the snapshot to stdout as JSON")
    args = parser.parse_args(argv)

    hook_payload = _read_stdin_hook_payload()

    try:
        root = resolve_studio_root(args.studio)
        agent_slug = args.agent or _resolve_resident_agent(root)
        trigger = args.trigger or hook_payload.get("trigger") or "unknown"
        if trigger not in ("manual", "auto", "unknown"):
            trigger = "unknown"
        agent_slug = agent_slug.strip().lower()
        snapshot = build_snapshot(root, agent_slug, trigger)
        target = write_snapshot(root, agent_slug, snapshot)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 — never block a hook, not even
        # on the SystemExit resolve_studio_root raises when a studio root
        # can't be found -- this tool's contract is stricter than that
        # shared helper's own callers, so it degrades here rather than
        # letting a bare SystemExit escape main() with a non-zero code.
        print(f"precompact-snapshot: degraded, wrote nothing ({exc})", file=sys.stderr)
        return 0

    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print(render_human(snapshot, target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
