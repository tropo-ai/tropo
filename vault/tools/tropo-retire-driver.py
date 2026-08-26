#!/usr/bin/env python3
"""
---
uid: 4e128745
name: retire-driver
type: tool
title: "retire-driver — walks e2c7d185's eight required-practice steps, verifies each landed, never closes"
status: active
owner: talos
domain: "Reads the world (files, the event bus) and reports per-step + overall retirement-practice completeness for one agent generation. Refuses only on its own unreadable input (the playbook section it reads its step list from). Never blocks tropo-lineage.py retire, which stays the ungated close."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-retire-driver.py --agent <slug> --generation <GEN> --root <studio-root>"
script_path: vault/tools/tropo-retire-driver.py
spawnable_by:
  - all-executives
input:
  type: object
  properties:
    agent: {type: string, description: "agent slug (e.g. talos)"}
    root: {type: string, description: "studio root; default is the current studio (own tests run isolated via --root)"}
output:
  type: object
  description: "JSON: per-step verdict (open/complete + evidence), overall verdict (complete only if every step is complete), never invents a pass"
created: '2026-08-24'
created_by: talos-t50
modified: '2026-08-24'
modified_by: talos-t50
governed_by: 8dd772a0
member_of:
  - "8dd772a0"
schema_version: 2
extraction_scope: ship
trigger_description: "Run before (or instead of trusting memory for) a retirement: reports which of e2c7d185's eight required-practice steps actually landed, by observing the world, not by asking the retiring agent."
belt_invocation: "python3 vault/tools/tropo-retire-driver.py --agent <slug> --generation <GEN>"
belt_example: "python3 vault/tools/tropo-retire-driver.py --agent talos"
---
"""

from __future__ import annotations

"""tropo-retire-driver.py — the driver that reads the world instead of trusting the record.

b1e78abb (v1.92), carrying 29506520 AC1/AC2/AC5/AC7 forward. Two failures with
one shape: a record that says a thing happened, and no instrument that reads
the world to check. Retirement is eight required steps of governed practice
(e2c7d185 §Required Practice); until this file, the only thing standing
behind them was an agent reading prose and remembering. A155 missed a step.
A153 missed two. A154 recovered A153's retirement from a summary and missed
§8 for the same reason.

WARN-SAFE (deb77758): this tool REPORTS. It never blocks `tropo-lineage.py
retire`, which stays the ungated close (0a0a6777 AC6 doctrine). Its only
refusal is on its own unreadable input: if e2c7d185 §Required Practice does
not parse to exactly the eight bold step labels this file's own registry
knows, in that order, it refuses and names the delta. A driver that silently
checked a subset of a changed playbook would be the exact defect it exists
to cure.

Each step is "observed on the world" — a file on disk, or an event on the
bus. Absence of evidence is reported open, never as pass. Two of the eight
steps are TOKEN-SHAPED and get known-negative-aware observers rather than a
bare substring search: Captain's Log (a huge append-only file; matching the
generation number anywhere in it is not an observer — it must appear in a
real `## <Agent> <GEN> —` entry heading) and Crew Surfaces' §Status-Notes
half (the generation string appearing anywhere doesn't prove the retirement
DECLARATION is there).

Step 7 (crew surfaces) has a genuine ACT, not just an observation: the
crew-brief re-render has no other writer, so the driver performs it. Step 8
(retirement notice) is READ, never emitted — `tropo-lineage.py retire`'s own
`announce()` already emits it with `category: retirement`; a driver that also
emitted would produce two broadcasts per retirement and rebuild the
one-writer defect this whole family of specs exists to cure.

Correction found live authoring this file: e2c7d185's own §Handoff text
(inherited into this build's spec) names the crew-brief renderer as living
at `.tropo/scripts/render-crew-brief.py` "outside vault/tools" — that path
does not exist in this checkout. The real, current renderer is
`vault/tools/6510afc7.py` (the same tool this driver's own boot chain used).
Called correctly here; the stale path claim is a separate, small finding.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None

PLAYBOOK_RELATIVE_PATH = "vault/playbooks/e2c7d185.md"
CREW_BRIEF_RENDERER_RELATIVE_PATH = "vault/tools/6510afc7.py"

#: The eight bold step labels, in order, as e2c7d185 §Required Practice
#: declares them TODAY. This IS a second copy of the list — the contract
#: makes that copy safe by refusing loudly the instant the playbook and this
#: registry disagree, rather than silently checking a subset (see module
#: docstring). A playbook amendment breaks this tool loudly, not an observer
#: quietly going dark.
REQUIRED_STEP_LABELS = (
    "Session memories.",
    "Memory fold.",
    "The letter.",
    "Reflection.",
    "Captain's Log.",
    "Event drain.",
    "Crew surfaces.",
    "Retirement notice.",
)

_BOLD_STEP_RE = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*", re.MULTILINE)
_SECTION_RE = re.compile(
    r"^##\s+Required Practice.*?$(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL
)


class PlaybookDriftError(Exception):
    """§Required Practice no longer parses to the known step registry."""


def parse_required_steps(root: Path) -> list[str]:
    """The refusal this whole tool is built around: read the playbook's own
    step list and confirm it matches the registry exactly, in order."""
    path = root / PLAYBOOK_RELATIVE_PATH
    if not path.is_file():
        raise PlaybookDriftError(f"{path} not found — cannot read §Required Practice")
    text = path.read_text(encoding="utf-8")
    section_match = _SECTION_RE.search(text)
    if not section_match:
        raise PlaybookDriftError(
            f"{path} — no '## Required Practice' section found"
        )
    found = tuple(_BOLD_STEP_RE.findall(section_match.group(1)))
    if found != REQUIRED_STEP_LABELS:
        raise PlaybookDriftError(
            "e2c7d185 §Required Practice no longer matches this driver's step "
            f"registry. Registry: {list(REQUIRED_STEP_LABELS)!r}. "
            f"Playbook: {list(found)!r}. A step was added, renamed, removed, "
            "or reordered — the driver refuses rather than silently checking "
            "a subset."
        )
    return list(found)


def _split_frontmatter(text: str) -> Optional[dict]:
    if yaml is None or not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def _memory_dir(root: Path, agent: str) -> Path:
    return root / "agents" / agent / ".tropo-capsule" / "memory"


# --- Step 1: session memories -----------------------------------------------

def observe_session_memories(root: Path, agent: str, gen: str) -> tuple[bool, str]:
    p = _memory_dir(root, agent) / "agent-memories.jsonl"
    if not p.is_file():
        return False, f"{p} does not exist"
    if p.stat().st_size == 0:
        return False, f"{p} exists but is empty"
    return True, str(p)


# --- Step 2: memory fold -----------------------------------------------------

def observe_memory_fold(root: Path, agent: str, gen: str) -> tuple[bool, str]:
    p = _memory_dir(root, agent) / "agent-memory.md"
    if not p.is_file():
        return False, f"{p} does not exist"
    fm = _split_frontmatter(p.read_text(encoding="utf-8", errors="replace")) or {}
    gen_token = f"{agent}-{gen}".lower()
    # Branch 1: in-line fold, curated_by names THIS generation.
    if str(fm.get("curated_by", "")).lower() == gen_token:
        return True, f"{p} curated_by={fm.get('curated_by')!r}"
    # Branch 2 (F6, lawful): sa.memory-curator dispatch for a generation
    # whose in-line fold would leave the surface over-bound. A dispatched
    # curator's own frozen snapshot names the generation in its filename.
    # ANCHORED, not a substring. This read `if gen.lower() in child.name.lower()`
    # and false-greened on every generation prefix. Measured against the real
    # argus tree 2026-08-25: gen 'A15' resolved COMPLETE against
    # a153-agent-memory-snapshot.md, and gen '1' resolved COMPLETE against both
    # a153-... and 1fee9220.md. No test in the corpus touched this branch, and
    # BOTH real driver runs (A155 and A153) resolved step 2 through it rather
    # than through curated_by — so the branch carrying the live verdict was a
    # bare substring match. Found by an independent adversarial pass.
    history_dir = _memory_dir(root, agent) / "history"
    if history_dir.is_dir():
        anchored = re.compile(
            rf"(?<![a-z0-9]){re.escape(gen.lower())}(?![a-z0-9])"
        )
        for child in sorted(history_dir.iterdir()):
            if anchored.search(child.name.lower()):
                return True, f"curator dispatch snapshot {child}"
    return False, (
        f"{p} curated_by={fm.get('curated_by')!r} does not name {gen_token!r}, "
        f"and no dispatched curator snapshot found under {history_dir}"
    )


# --- Step 3: the letter (AC4-conditioned) ------------------------------------

def observe_letter(
    root: Path, agent: str, gen: str, letter_source: Optional[str]
) -> tuple[bool, str]:
    dest = root / "agents" / agent / "transfers" / f"{gen}.md"
    if dest.is_file() and dest.read_text(encoding="utf-8", errors="replace").strip():
        return True, str(dest)
    if letter_source:
        src = Path(letter_source)
        if src.is_file() and src.read_text(encoding="utf-8", errors="replace").strip():
            return True, f"authored, unplaced: {src} (not yet at {dest})"
    return False, f"{dest} absent or empty, and no verified non-empty --letter-source given"


# --- Step 4: reflection ------------------------------------------------------

def observe_reflection(root: Path, agent: str, gen: str) -> tuple[bool, str]:
    p = root / "agents" / agent / "reflections" / f"{gen.lower()}-reflection.md"
    if not p.is_file():
        return False, f"{p} does not exist"
    text = p.read_text(encoding="utf-8", errors="replace")
    # A real heading, not a bare mention (found live authoring this
    # observer's own test: "no narrative section" in ordinary prose
    # case-insensitive-matched a substring search that never required a
    # heading — the exact weak-observer class this spec warns about for
    # Captain's Log and Status-Notes applies here too).
    has_manifest = re.search(r"^#+\s*§?File Manifest\b", text, re.IGNORECASE | re.MULTILINE) is not None
    has_narrative = re.search(r"^#+\s*§?Narrative\b", text, re.IGNORECASE | re.MULTILINE) is not None
    if has_manifest and has_narrative:
        return True, str(p)
    missing = [n for n, ok in (("File Manifest", has_manifest), ("Narrative", has_narrative)) if not ok]
    return False, f"{p} exists but missing section(s): {', '.join(missing)}"


# --- Step 5: Captain's Log (known-negative-aware) ----------------------------

def observe_captains_log(root: Path, agent: str, gen: str) -> tuple[bool, str]:
    p = root / "library" / "captains-log.md"
    if not p.is_file():
        return False, f"{p} does not exist"
    text = p.read_text(encoding="utf-8", errors="replace")
    # A real entry MARKER, not a bare token match anywhere in a huge file.
    # Two formats live in this file today (found live authoring this
    # observer — Metis's line uses one, Talos's line the other, e2c7d185
    # mandates neither specifically): an H2 heading ("## Metis G111 —
    # 2026-08-24, at retirement") or a bold entry-opener line ("**Talos T49,
    # 2026-08-23.**"). Both are legitimate per-generation entry starts; a
    # bare mention of the generation inside someone else's narrative
    # ("...T49 corrected...") is neither shape and correctly does not match.
    marker_re = re.compile(
        rf"^(?:##\s+\S+\s+{re.escape(gen)}\b|\*\*\S+\s+{re.escape(gen)},)",
        re.MULTILINE,
    )
    m = marker_re.search(text)
    if m:
        line_end = text.index("\n", m.start()) if "\n" in text[m.start():] else len(text)
        return True, f"{p}: {text[m.start():line_end][:80]!r}"
    return False, (
        f"{p} — generation {gen!r} not found as a real entry marker (an H2 "
        "heading or a bold entry-opener line naming this generation) — a "
        "bare token match elsewhere in the file is not an observer"
    )


# --- Step 6: event drain ------------------------------------------------------

def observe_event_drain(
    root: Path, agent: str, gen: str, party_uid: Optional[str], agent_root_uid: Optional[str],
    flagged_thread_ids: Optional[list[str]] = None,
) -> tuple[bool, str]:
    """`root` is the STUDIO BEING OBSERVED (its event bus is what gets
    scanned) — it is deliberately NOT where this driver's own helper code
    is loaded from. The driver always ships beside the real `lib/` and
    `tropo-check-events.py`, at its own on-disk location, regardless of
    which studio's --root it was pointed at; a test fixture --root
    legitimately carries no copy of either. Loading relative to
    Path(__file__) rather than `root` is what makes that isolation work
    (found live: the first version resolved both from `root` and every
    fixture-driven test failed with FileNotFoundError)."""
    if not party_uid:
        return False, "no party_uid supplied — cannot scan the bus for this agent"
    own_tools_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(own_tools_dir))
    from lib import event_identity  # noqa: E402
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "retire_driver_check_events", own_tools_dir / "tropo-check-events.py"
    )
    check_events = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_events)

    event_union = event_identity.load_event_union(root)
    unanswered = check_events.scan_unanswered_rr(party_uid, agent_root_uid, event_union=event_union)
    if not unanswered:
        return True, "zero unanswered reply_required on both axes"
    unanswered_ids = {ev.get("id") or ev.get("event_uid") for ev in unanswered}
    flagged = set(flagged_thread_ids or [])
    still_open = unanswered_ids - flagged
    if not still_open:
        return True, (
            f"{len(unanswered_ids)} unanswered thread(s), all explicitly "
            f"flag-and-proceed: {sorted(flagged)}"
        )
    return False, f"unanswered reply_required: {sorted(still_open)}"


# --- Step 7: crew surfaces (driver ACTS: re-render; observes: §Status-Notes) --

def perform_crew_brief_rerender(root: Path) -> tuple[bool, str]:
    renderer = root / CREW_BRIEF_RENDERER_RELATIVE_PATH
    if not renderer.is_file():
        return False, f"{renderer} not found — cannot re-render"
    try:
        result = subprocess.run(
            [sys.executable, str(renderer)],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        return False, f"crew-brief renderer failed to run: {exc}"
    if result.returncode != 0:
        return False, f"crew-brief renderer exited {result.returncode}: {result.stderr[:200]}"
    return True, (result.stdout or "").strip()[:200]


def observe_status_notes(root: Path, agent: str, gen: str, unified_entry_uid: Optional[str]) -> tuple[bool, str]:
    if not unified_entry_uid:
        return False, "no unified entry uid supplied — cannot check §Status-Notes"
    p = root / "vault" / "agents" / f"{unified_entry_uid}.md"
    if not p.is_file():
        return False, f"{p} does not exist"
    text = p.read_text(encoding="utf-8", errors="replace")
    # BOUNDED TO THE ACTUAL SECTION, and absent means absent.
    #
    # This was `section = m.group(1) if m else text` with a DOTALL `(.*)`, so a
    # card with no §Status-Notes at all had its ENTIRE body scanned, and a card
    # whose §Status-Notes said the agent was ACTIVE still passed if the word
    # RETIRED appeared near the generation anywhere later in the file. On the
    # real argus card the "section" was ~430 lines of operating doctrine plus
    # the real section. Measured by an independent adversarial pass; the one
    # known-negative in the suite covered only a minimal file authored in the
    # reader's own shape.
    m = re.search(r"^#+\s*§Status-Notes\s*$(.*?)(?=^#+\s|\Z)",
                  text, re.DOTALL | re.MULTILINE)
    if m is None:
        m = re.search(r"§Status-Notes(.*?)(?=^#+\s|\Z)",
                      text, re.DOTALL | re.MULTILINE)
    if m is None:
        return False, (
            f"{p} carries no §Status-Notes section, so there is nothing to "
            f"observe. Absent is not satisfied."
        )
    section = m.group(1)
    if re.search(rf"\b{re.escape(gen)}\b.*RETIRED", section) or re.search(
        rf"RETIRED.*\b{re.escape(gen)}\b", section
    ):
        return True, f"{p} §Status-Notes names {gen} RETIRED"
    return False, f"{p} §Status-Notes does not name {gen} as retired"


def observe_crew_surfaces(
    root: Path, agent: str, gen: str, unified_entry_uid: Optional[str], perform: bool = True,
) -> tuple[bool, str]:
    rerendered, rerender_evidence = (
        perform_crew_brief_rerender(root) if perform else (True, "skipped (--no-act)")
    )
    status_ok, status_evidence = observe_status_notes(root, agent, gen, unified_entry_uid)
    ok = rerendered and status_ok
    evidence = f"re-render: {rerender_evidence} | status-notes: {status_evidence}"
    return ok, evidence


# --- Step 8: retirement notice (READ ONLY — never emits) --------------------

def observe_retirement_notice(root: Path, agent: str, gen: str) -> tuple[bool, str]:
    # Same isolation reasoning as observe_event_drain: load lib/ from the
    # driver's own on-disk location, scan events on --root's bus.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lib import event_identity  # noqa: E402

    event_union = event_identity.load_event_union(root)
    matches = [
        ev for ev in event_union
        if ev.get("type") == "tropo.broadcast.crew"
        and (ev.get("data") or {}).get("category") == "retirement"
        and (ev.get("data") or {}).get("agent") == agent
        and (ev.get("data") or {}).get("gen") == gen
    ]
    if not matches:
        return False, (
            f"no tropo.broadcast.crew event with category:retirement for "
            f"{agent} {gen} found on the bus"
        )
    return True, f"{len(matches)} matching broadcast(s) on the bus"


STEP_OBSERVERS = (
    "Session memories.",
    "Memory fold.",
    "The letter.",
    "Reflection.",
    "Captain's Log.",
    "Event drain.",
    "Crew surfaces.",
    "Retirement notice.",
)


def run_driver(
    root: Path, agent: str, gen: str, *,
    party_uid: Optional[str] = None,
    agent_root_uid: Optional[str] = None,
    unified_entry_uid: Optional[str] = None,
    letter_source: Optional[str] = None,
    flagged_thread_ids: Optional[list[str]] = None,
    perform_acts: bool = True,
) -> dict:
    """Walk all eight steps, in order, and return the full report. Refuses
    (raises PlaybookDriftError) only on unreadable/drifted input — never on
    an open step, which is reported, not raised."""
    parsed = parse_required_steps(root)  # raises PlaybookDriftError on drift
    assert parsed == list(REQUIRED_STEP_LABELS)  # defensive; parse already enforced this

    steps: dict[str, dict] = {}

    ok, ev = observe_session_memories(root, agent, gen)
    steps["Session memories."] = {"status": "complete" if ok else "open", "evidence": ev}

    ok, ev = observe_memory_fold(root, agent, gen)
    steps["Memory fold."] = {"status": "complete" if ok else "open", "evidence": ev}

    ok, ev = observe_letter(root, agent, gen, letter_source)
    steps["The letter."] = {"status": "complete" if ok else "open", "evidence": ev}

    ok, ev = observe_reflection(root, agent, gen)
    steps["Reflection."] = {"status": "complete" if ok else "open", "evidence": ev}

    ok, ev = observe_captains_log(root, agent, gen)
    steps["Captain's Log."] = {"status": "complete" if ok else "open", "evidence": ev}

    ok, ev = observe_event_drain(root, agent, gen, party_uid, agent_root_uid, flagged_thread_ids)
    steps["Event drain."] = {"status": "complete" if ok else "open", "evidence": ev}

    ok, ev = observe_crew_surfaces(root, agent, gen, unified_entry_uid, perform=perform_acts)
    steps["Crew surfaces."] = {"status": "complete" if ok else "open", "evidence": ev}

    ok, ev = observe_retirement_notice(root, agent, gen)
    steps["Retirement notice."] = {"status": "complete" if ok else "open", "evidence": ev}

    open_steps = [label for label in REQUIRED_STEP_LABELS if steps[label]["status"] == "open"]
    overall = "complete" if not open_steps else "incomplete"
    return {
        "agent": agent,
        "generation": gen,
        "steps": steps,
        "open_steps": open_steps,
        "overall": overall,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="tropo-retire-driver.py",
        description="Walk e2c7d185's eight required-practice steps and report completeness. Never closes.",
    )
    parser.add_argument("--agent", required=True)
    parser.add_argument("--generation", required=True, help="e.g. T50 or G112")
    parser.add_argument("--root", default=".", help="studio root (default: current directory)")
    parser.add_argument("--party-uid", default=None)
    parser.add_argument("--agent-root-uid", default=None)
    parser.add_argument("--unified-entry-uid", default=None)
    parser.add_argument("--letter-source", default=None, help="path to a letter authored but not yet placed")
    parser.add_argument("--flag-thread", action="append", default=[], help="event id explicitly flagged-and-proceed (repeatable)")
    parser.add_argument("--no-act", action="store_true", help="skip the crew-brief re-render (observe only)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        report = run_driver(
            root, args.agent, args.generation,
            party_uid=args.party_uid,
            agent_root_uid=args.agent_root_uid,
            unified_entry_uid=args.unified_entry_uid,
            letter_source=args.letter_source,
            flagged_thread_ids=args.flag_thread,
            perform_acts=not args.no_act,
        )
    except PlaybookDriftError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{args.agent} {args.generation} — retirement practice: {report['overall'].upper()}")
        for label in REQUIRED_STEP_LABELS:
            step = report["steps"][label]
            marker = "✓" if step["status"] == "complete" else "✗ OPEN"
            print(f"  {marker}  {label}  ({step['evidence']})")
    return 0 if report["overall"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
