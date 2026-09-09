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
  description: "JSON: per-step verdict (complete/open/not applicable + evidence), overall verdict (complete only if no step is open), never invents a pass. 'not applicable' is reported, never folded into a pass: it means the furniture that step observes is absent from this Studio (no library/captains-log.md, no 00-crew-brief.md, not a git repository) so there was nothing to do and nothing was missed."
created: '2026-08-24'
created_by: talos-t50
modified: '2026-09-09'
modified_by: metis-g128
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
bus. A missing ARTIFACT is reported open, never as pass. Missing FURNITURE —
the surface a step writes to not existing in this Studio at all — is reported
`not applicable`, which is its own third state and is also never a pass: it
emits evidence naming what is absent (see STATUS_* below). Two of the eight
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
import os
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
CAPTAINS_LOG_RELATIVE_PATH = "library/captains-log.md"

#: THREE STATES, NOT TWO. An observer returns `True` (the step landed),
#: `False` (a real gap — the furniture exists and the artifact is missing,
#: wrong, or split), or `None` — NOT APPLICABLE: the furniture this step
#: observes is absent from this Studio, so there was nothing to do and nothing
#: was missed.
#:
#: `None` is NEVER a silent pass. Every not-applicable branch emits evidence
#: that NAMES the absent furniture, so "nothing to do" can never be mistaken
#: for "not checked", and the report prints it as its own marker.
#:
#: The pattern arrived with `perform_crew_brief_rerender` (f01503e540a2,
#: vela-v80): measured on a built box, no shipped Studio carries
#: `00-crew-brief.md`, so that leg returned False and a stranger's first
#: retirement read `Crew surfaces: OPEN` with no action available to them that
#: could ever clear it. v1.96 first-minute item 5 measured the same shape on
#: two more steps — 2 of 8 steps completed on a real box — and this file now
#: carries the pattern at step level, not just inside one leg:
#:   * Captain's Log — no shipped box carries `library/captains-log.md`.
#:   * One commit    — a shipped Studio is not a git repository.
#: A required step that cannot pass in the shipped product is a defect in the
#: step, not a finding about the agent.
STATUS_COMPLETE = "complete"
STATUS_OPEN = "open"
STATUS_NOT_APPLICABLE = "not applicable"


def _step_status(ok: Optional[bool]) -> str:
    """Map an observer's tri-state verdict to the reported step status.

    One place, so a new observer cannot invent a fourth spelling and so `None`
    can never be quietly coerced to `open` by a `if ok else` at a call site —
    which is exactly how the crew-brief leg's fix would have been lost had the
    step composed it with `rerendered and status_ok`.
    """
    if ok is None:
        return STATUS_NOT_APPLICABLE
    return STATUS_COMPLETE if ok else STATUS_OPEN

#: The eight bold step labels, in order, as e2c7d185 §Required Practice
#: declares them TODAY. This IS a second copy of the list — the contract
#: makes that copy safe by refusing loudly the instant the playbook and this
#: registry disagree, rather than silently checking a subset (see module
#: docstring). A playbook amendment breaks this tool loudly, not an observer
#: quietly going dark.
REQUIRED_STEP_LABELS = (
    "Append session memories",
    "Write the letter",
    "Reflection",
    "Captain's Log",
    "Drain events",
    "Crew surfaces",
    "Retirement broadcast",
    "One commit",
)

#: Re-pinned 2026-09-05 (talos-t62, task f0150b2a4678) to the labels the
#: playbook has carried since Mike ruled memory curation out of the retiring
#: agent's job on 2026-09-04: "Memory fold." is gone, "One commit." arrived, and
#: the rest were reworded. The registry was not re-pinned with the ruling, so
#: this driver refused every invocation from 09-04 onward and A169, A170 and
#: A171 all retired without it — the instrument that exists so a retirement is
#: verified on the world instead of on the agent's word was itself unverifiable.
#:
#: Comparison is on the label HEAD, not the rendered string: the playbook writes
#: "Reflection — optional; research-grade short form." and "Captain's Log", and
#: pinning punctuation would make a copy-edit look like a missing step. A
#: rename, an addition, a removal or a reorder of the head still refuses, which
#: is the drift this contract exists to catch.


def _normalise_label(label: str) -> str:
    """The step's identity: the head before any em-dash qualifier, no trailing dot."""
    return label.split("\u2014")[0].strip().rstrip(".").strip()

_BOLD_STEP_RE = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*", re.MULTILINE)
# 59682505 cure (parse side, one authority): the playbook's real heading is
# "## The checklist — required practice, in order"; the driver defers to any
# H2 whose title contains "required practice", so a title tweak in the ONE
# authority (the playbook) never silently darkens this driver again.
_SECTION_RE = re.compile(
    r"^##[^\n]*required practice[^\n]*$(.*?)(?=^##\s+|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
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
            f"{path} — no H2 titled with 'required practice' found"
        )
    found = tuple(_BOLD_STEP_RE.findall(section_match.group(1)))
    normalised = tuple(_normalise_label(label) for label in found)
    if normalised != REQUIRED_STEP_LABELS:
        raise PlaybookDriftError(
            "e2c7d185 §Required Practice no longer matches this driver's step "
            f"registry. Registry: {list(REQUIRED_STEP_LABELS)!r}. "
            f"Playbook: {list(normalised)!r}. A step was added, renamed, "
            "removed, or reordered — the driver refuses rather than silently "
            "checking a subset.\n"
            "CURE: the playbook is the authority and it moved. Re-pin "
            "REQUIRED_STEP_LABELS in vault/tools/tropo-retire-driver.py to the "
            "playbook's labels above, add or drop the matching observer in "
            "run_driver, and update test_retire_driver_v192's fixture — the "
            "registry-matches-live-playbook test is what should have caught "
            "this before a retirement did."
        )
    return list(normalised)


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


def _memory_surfaces():
    """Phase-2 name resolution (f0153a6df07f), imported the way this tool
    already imports event_identity."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lib import memory_surfaces  # noqa: E402

    return memory_surfaces


# --- Step 1: session memories -----------------------------------------------

def observe_session_memories(root: Path, agent: str, gen: str) -> tuple[bool, str]:
    p = _memory_surfaces().agent_log(root, agent)
    if not p.is_file():
        return False, f"{p} does not exist"
    if p.stat().st_size == 0:
        return False, f"{p} exists but is empty"
    return True, str(p)


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
        # The playbook: "Write it only if you have something a future researcher
        # could use; otherwise skip." An absent reflection is a skip the playbook
        # authorises, not a missed step — reporting it open would push agents to
        # write filler to satisfy an instrument.
        return True, "no reflection — optional per the playbook, skipped"
    text = p.read_text(encoding="utf-8", errors="replace")
    # A real heading, not a bare mention (found live authoring this
    # observer's own test: "no narrative section" in ordinary prose
    # case-insensitive-matched a substring search that never required a
    # heading — the exact weak-observer class this spec warns about for
    # Captain's Log and Status-Notes applies here too).
    # RE-PINNED 2026-09-05 (talos-t62, task f0150b2a4678). This required
    # "File Manifest" and "Narrative" until now. The playbook's Reflection step
    # was rewritten to the research-grade short form and it says, verbatim,
    # "No File Manifest, commit tables, UID inventories" — so this observer was
    # demanding the exact structure the ruling FORBIDS, and would have reported
    # a perfectly compliant reflection as open. Found by running the driver on
    # A169/A170/A171: all three "missing File Manifest, Narrative", which is the
    # shape of a stale probe, not three agents making the same mistake.
    #
    # The headings the playbook now requires, and the bold-lead form it renders
    # them in (`- **Mistake** — …`) as well as a heading, since it shows both.
    required = ("Mistake", "Surprise", "Studio change")
    present = {
        name: re.search(
            r"^(?:#+\s*§?|\s*[-*]\s*\*\*)%s\b" % re.escape(name),
            text, re.IGNORECASE | re.MULTILINE) is not None
        for name in required
    }
    if all(present.values()):
        return True, str(p)
    missing = [name for name, ok in present.items() if not ok]
    return False, f"{p} exists but missing section(s): {', '.join(missing)}"


# --- Step 5: Captain's Log (known-negative-aware) ----------------------------

def observe_captains_log(root: Path, agent: str, gen: str) -> tuple[Optional[bool], str]:
    """Three states (see STATUS_* above). Returns None when this Studio keeps
    no Captain's Log at all.

    `None` means NOT APPLICABLE and is distinct from False: no shipped box
    ships `library/captains-log.md`, so before this fix a stranger's first
    retirement reported `Captain's Log: OPEN` permanently — no action available
    to them could clear it, because appending to a log the product does not
    ship is not an action. Measured on a real box, v1.96 first-minute item 5.

    False is preserved for the case that actually matters: the log EXISTS and
    carries no real entry for this generation. That is a missed step and stays
    a missed step. A broken symlink is existence, not absence — it falls to
    False with its own reason, the same way the crew-brief leg treats one.
    """
    p = root / CAPTAINS_LOG_RELATIVE_PATH
    if not os.path.lexists(p):
        return None, (
            f"not applicable — this Studio keeps no {CAPTAINS_LOG_RELATIVE_PATH}; "
            "there is no log to append to (normal for a freshly unzipped Studio)"
        )
    if not p.is_file():
        return False, (
            f"{p} exists but is not a readable file (a broken link or a "
            "directory) — cannot observe; this is a broken log, not an absent one"
        )
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

#: The rendered surface itself. Its ABSENCE is the signal that this Studio keeps
#: no crew brief — a single-agent Studio has no crew to brief — and the renderer
#: at 6510afc7.py requires an existing file, exiting "ERROR: crew brief not found"
#: without one. Every shipped box is in exactly that state.
CREW_BRIEF_RELATIVE_PATH = "00-crew-brief.md"


def perform_crew_brief_rerender(root: Path) -> tuple[Optional[bool], str]:
    """Re-render the crew brief. Returns None when the Studio keeps none.

    Three states, not two. `None` means NOT APPLICABLE and is distinct from
    False: a Studio with no `00-crew-brief.md` has nothing to re-render and has
    not failed to do anything. Measured 2026-09-08 on a built box (vela-v80):
    the file is absent from every shipped box, so this leg returned False, the
    step read `open`, and a stranger's first retirement reported
    `Crew surfaces: OPEN` permanently — no action available to them could ever
    clear it. A required step that cannot pass in the shipped product is a
    defect in the step.

    The not-applicable case EMITS rather than passing quietly: it names the
    absent file, so "nothing to do" can never be confused with "not checked".
    """
    brief = root / CREW_BRIEF_RELATIVE_PATH
    if not os.path.lexists(brief):
        return None, (
            f"not applicable — this Studio keeps no {CREW_BRIEF_RELATIVE_PATH}; "
            "nothing to re-render (normal for a single-agent or freshly unzipped Studio)"
        )
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
    # `rerendered is None` is NOT APPLICABLE, not failure: this Studio keeps no
    # crew brief. The step then rests on §Status-Notes alone, which every Studio
    # has. `False` still fails — a renderer that exists and errored is a real gap.
    ok = status_ok if rerendered is None else (rerendered and status_ok)
    evidence = f"re-render: {rerender_evidence} | status-notes: {status_evidence}"
    return ok, evidence


# --- One commit: the checklist artifacts land together, read from git ---------

def _git(root: Path, *args: str) -> tuple[int, str]:
    """Read-only git against THIS tree, with GIT_* scrubbed.

    The scrub is not decoration. An inherited GIT_DIR beats cwd, so a caller
    with one set would have this observer read a different repository and
    report confidently about the wrong history (the 2026-09-02 class).
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                           text=True, timeout=30, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return r.returncode, (r.stdout or "").strip()


def _git_repository_state(root: Path) -> tuple[Optional[bool], str]:
    """Is there a repository at `root` whose history can be observed?

    Three states, the same three the step reports:

    * True  — git reports a work tree at `root`. Commits are observable.
    * None  — NOT APPLICABLE: git reports no work tree AND there is no `.git`
              at the root. This Studio is not a git repository, so there is no
              history in which artifacts could land together. Every shipped box
              is in exactly this state.
    * False — a `.git` EXISTS but git cannot read a repository through it.
              Broken furniture, not absent furniture, and a real gap.

    `rev-parse --is-inside-work-tree` is asked first because it is the only
    robust answer: it covers a linked worktree (whose `.git` is a file, not a
    directory) and a Studio nested inside a larger repository (whose root
    carries no `.git` of its own, yet whose commits are real and readable).
    The `.git` probe is only the tiebreak that separates "absent" from
    "present but unreadable" once git has already declined.
    """
    code, out = _git(root, "rev-parse", "--is-inside-work-tree")
    if code == 0 and out.strip() == "true":
        return True, ""
    if not os.path.lexists(root / ".git"):
        return None, (
            f"not applicable — this Studio is not a git repository (no .git at "
            f"{root}, and git reports no work tree); there is no commit history "
            "in which the artifacts could land together (normal for a freshly "
            "unzipped Studio)"
        )
    return False, (
        f"{root / '.git'} exists but git could not read a repository through it: "
        f"{out.strip()[:160] or 'no output from git rev-parse'}"
    )


def observe_one_commit(
    root: Path, agent: str, gen: str, unified_entry_uid: Optional[str] = None,
) -> tuple[Optional[bool], str]:
    """The playbook's step 8: the retirement's artifacts land in ONE commit.

    Observed from `git log`, never from testimony. Reflection is OPTIONAL — an
    absent reflection is not an open step, because the playbook itself marks
    that step optional; a reflection that EXISTS but sits in a different commit
    is a real split and is reported.

    Three states (see STATUS_* above). Returns None when this Studio is not a
    git repository: "land the artifacts in one commit" is not an instruction a
    stranger on a shipped, non-git box can follow, and reporting it open told
    them to do something no action of theirs could satisfy (v1.96 first-minute
    item 5, measured on a real box). A repository that DOES exist and carries
    no commit for the letter, or carries the artifacts split across two, is
    still False — that is the split this step exists to catch.
    """
    repository, why = _git_repository_state(root)
    if repository is not True:
        return repository, why    # None = not applicable; False = broken .git

    letter_rel = f"agents/{agent}/transfers/{gen}.md"
    code, sha = _git(root, "log", "--format=%H", "-1", "--", letter_rel)
    if code != 0 or not sha:
        return False, f"no commit in this tree touches {letter_rel} — nothing to verify"
    code, listing = _git(root, "show", "--name-only", "--format=", sha)
    if code != 0:
        return False, f"could not read the file list of {sha[:12]}"
    touched = {line.strip() for line in listing.splitlines() if line.strip()}

    required = {
        "letter": letter_rel,
        "session memories": f"agents/{agent}/.tropo-capsule/memory/agent-memories.jsonl",
        "captain's log": "library/captains-log.md",
    }
    if unified_entry_uid:
        required["status-notes"] = f"vault/agents/{unified_entry_uid}.md"
    reflection_rel = f"agents/{agent}/reflections/{gen.lower()}-reflection.md"
    if (root / reflection_rel).is_file():
        required["reflection"] = reflection_rel

    missing = sorted(name for name, rel in required.items() if rel not in touched)

    # The commit must not come AFTER the lineage `retired` line was recorded.
    lineage_rel = f"agents/{agent}/lineage.jsonl"
    code, lineage_sha = _git(root, "log", "--format=%H", "-1", "-S", f'"gen": "{gen}"',
                             "--", lineage_rel)
    order = ""
    if code == 0 and lineage_sha and lineage_sha != sha:
        anc, _ = _git(root, "merge-base", "--is-ancestor", sha, lineage_sha)
        order = "" if anc == 0 else (
            f"; the artifact commit {sha[:12]} does NOT precede the lineage "
            f"commit {lineage_sha[:12]}")

    if missing or order:
        # Name WHERE each stray artifact actually landed. "not in this commit"
        # reads as "absent", and absent is a different and much worse finding
        # than "split across two commits" — which is what the step is for.
        elsewhere = []
        for name in missing:
            rel = required[name]
            # captains-log.md and agent-memories.jsonl are SHARED, append-only
            # files: "the last commit that touched this path" is whoever wrote
            # to them most recently, not where THIS generation's entry landed.
            # The pickaxe finds the commit that introduced the generation's own
            # text, which is the honest answer to "where did it go".
            code2, other = _git(root, "log", "--format=%H", "-1", "-S", gen, "--", rel)
            if code2 != 0 or not other:
                code2, other = _git(root, "log", "--format=%H", "-1", "--", rel)
            elsewhere.append(
                f"{name} in {other[:12]}" if code2 == 0 and other else f"{name} in no commit")
        return False, (
            f"split across commits — {sha[:12]} carries "
            f"{sorted(set(required) - set(missing))}; " + "; ".join(elsewhere) + order
            if missing else f"commit {sha[:12]} carries every artifact{order}")
    reflection_note = "" if "reflection" in required else " (no reflection — optional, n/a)"
    return True, f"one commit {sha[:12]}: {sorted(required)}{reflection_note}"


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
    steps["Append session memories"] = {"status": _step_status(ok), "evidence": ev}

    ok, ev = observe_letter(root, agent, gen, letter_source)
    steps["Write the letter"] = {"status": _step_status(ok), "evidence": ev}

    ok, ev = observe_reflection(root, agent, gen)
    steps["Reflection"] = {"status": _step_status(ok), "evidence": ev}

    ok, ev = observe_captains_log(root, agent, gen)
    steps["Captain's Log"] = {"status": _step_status(ok), "evidence": ev}

    ok, ev = observe_event_drain(root, agent, gen, party_uid, agent_root_uid, flagged_thread_ids)
    steps["Drain events"] = {"status": _step_status(ok), "evidence": ev}

    ok, ev = observe_crew_surfaces(root, agent, gen, unified_entry_uid, perform=perform_acts)
    steps["Crew surfaces"] = {"status": _step_status(ok), "evidence": ev}

    ok, ev = observe_retirement_notice(root, agent, gen)
    steps["Retirement broadcast"] = {"status": _step_status(ok), "evidence": ev}

    ok, ev = observe_one_commit(root, agent, gen, unified_entry_uid)
    steps["One commit"] = {"status": _step_status(ok), "evidence": ev}

    # A not-applicable step does not block completion — there was nothing to do
    # — and it is NOT counted as complete either. It is listed on its own key so
    # a reader of the JSON sees exactly which steps this Studio has no furniture
    # for, and cannot mistake the silence for a pass.
    open_steps = [label for label in REQUIRED_STEP_LABELS
                  if steps[label]["status"] == STATUS_OPEN]
    not_applicable = [label for label in REQUIRED_STEP_LABELS
                      if steps[label]["status"] == STATUS_NOT_APPLICABLE]
    overall = "complete" if not open_steps else "incomplete"
    return {
        "agent": agent,
        "generation": gen,
        "steps": steps,
        "open_steps": open_steps,
        "not_applicable_steps": not_applicable,
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
        markers = {
            STATUS_COMPLETE: "✓",
            STATUS_NOT_APPLICABLE: "· n/a",
            STATUS_OPEN: "✗ OPEN",
        }
        for label in REQUIRED_STEP_LABELS:
            step = report["steps"][label]
            # n/a prints as its own marker. It is neither a tick (nothing was
            # verified) nor an OPEN (nothing was missed); collapsing it into
            # either is the reporting half of the same defect.
            marker = markers[step["status"]]
            print(f"  {marker}  {label}  ({step['evidence']})")
    return 0 if report["overall"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
