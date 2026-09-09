"""lib/po_first_boot.py — B-7 (f01564310146): the one shared fact both Po's
first-boot trigger (.tropo/concierge/activate.md, kernel surface) and her
walk (vault/playbooks/po-first-boot-orientation-f015f6f98b9b.md) read, so "does the automatic walk
fire" has exactly one answer instead of two copies of the same prose
drifting apart -- the studio's own costliest defect family, applied here
before it has a chance to recur.

The flag is per-install, machine scope in the studio-ops taxonomy
(0be90697) -- it sits beside the existing dated `.tropo/flags/*.flag`
markers and follows their own shape: presence is the whole signal, byte
content is never read.

v1.96 amendment (f01579bf3aee, "make the first-boot orientation tour
reachable from any agent, not only from Po"): the trigger above was
correct and still is -- one fact, one reader, and the walk's own Step 6
writes the same constant. What it could not survive was Po skipping the
step that reads it. On the founder's own v1.95 external test she went
straight from the pre-boot checks to her greeting; her retrospective is
the only reason anyone knows. A fact only ever consulted by the agent
who skipped consulting it has no witness.

So a SECOND surface reads the same fact: Group 5 of the canonical
activation playbook, on any agent's boot. `should_fold_agent_offer()`
below is that surface's gate, and it fires AT MOST ONCE per install --
`AGENT_OFFER_FLAG_REL` is written the moment the line is handed to an
agent. Once, from one agent, in front of the founder, then quiet
forever. This studio's founder nearly ended the project over machinery
that asks him for things; a tour offer that repeats every boot in a
studio with seven agents would be exactly that, so it does not repeat.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

FLAG_REL = Path(".tropo") / "flags" / "po-first-boot-orientation-offered.flag"

# Written when ANY agent folds the one-line tour offer into its startup
# signal. Deliberately distinct from FLAG_REL: FLAG_REL means "a human was
# walked through the offer by the walk playbook", this means "an agent put
# the line in front of somebody". Collapsing the two would let a signal line
# nobody answered silence Po's real offer.
AGENT_OFFER_FLAG_REL = (
    Path(".tropo") / "flags" / "agent-orientation-offer-surfaced.flag"
)

# A hand-off is not a delivery. The tool knows it printed a line to stdout; it
# cannot know an agent folded that line into a greeting a human read. The first
# build burned the install's single offer on the print, so an agent that ran the
# command and dropped the line silenced the tour forever AND the audit then
# reported the offer "surfaced" -- a self-report of compliance inside the change
# written to end self-reports of compliance (found by the non-author verifier,
# finding F1, 2026-09-07). So the flag now RECORDS hand-offs, one ISO stamp per
# line, and the ceiling bounds them. Real delivery still silences this surface
# immediately and for good: the walk flag is checked first, by
# should_fire_automatic_walk.
#
# THE CEILING IS 1, DELIBERATELY, AND IT COSTS SOMETHING. Argus A173 first set
# it to 3 so a dropped line could not be permanent, and the existing nag-control
# test refused the change on the founder's own stated priority: "this studio's
# founder nearly ended the project over machinery that repeats itself at him.
# Declining is not required to silence it -- surfacing once is." That priority
# wins here, because the loss it accepts is small: burning the AUTOMATIC offer
# does not lose the tour. Any "show me around" intent routes to the same walk
# forever, flag or no flag. What was NOT acceptable was the record claiming the
# offer had been surfaced to a human when all this tool observed was its own
# stdout -- that half of F1 is cured above and is not a trade-off.
#
# Raise this only with the founder's word, and only if a dropped line is ever
# measured actually costing an install its tour.
AGENT_OFFER_HANDOFF_CEILING = 1


def agent_offer_handoffs(vault_root: Path) -> int:
    """How many times the one-line offer has been handed to an agent."""
    flag = Path(vault_root) / AGENT_OFFER_FLAG_REL
    if not flag.is_file():
        return 0
    try:
        lines = [x for x in flag.read_text(encoding="utf-8").splitlines() if x.strip()]
    except OSError:
        return 0
    # A pre-existing empty marker from the first build is one hand-off.
    return len(lines) or 1

# The offer text, declared once so the concierge surface and the agent
# surface cannot drift into two differently-worded tours.
AGENT_OFFER_LINE = (
    "🔔 You haven't had the Studio orientation tour yet — want a walkthrough? "
    "(ask any agent for the tour, or ask Po)"
)


def should_fire_automatic_walk(vault_root: Path) -> bool:
    """True until the flag exists. Gates the AUTOMATIC first-boot fire
    ONLY -- callers driving an on-demand request ("give me the tour")
    must never consult this; the walk playbook runs in full regardless."""
    return not (Path(vault_root) / FLAG_REL).is_file()


def mark_walk_offered(vault_root: Path) -> Path:
    """Write the flag (idempotent, empty-file marker). Call this whether
    the walk completed or was skipped -- the flag records that the offer
    was made, not that it was accepted."""
    flag = Path(vault_root) / FLAG_REL
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.touch(exist_ok=True)
    return flag


def should_fold_agent_offer(vault_root: Path) -> bool:
    """True iff the tour has never reached a human through the walk AND no
    agent has yet surfaced the one-line offer. Both must be true, so taking
    the walk silences this surface too, and surfacing it once silences it
    forever regardless of what the human answers.

    Never nags: at most one agent boot on any install ever returns True."""
    root = Path(vault_root)
    if agent_offer_handoffs(root) >= AGENT_OFFER_HANDOFF_CEILING:
        return False
    return should_fire_automatic_walk(root)


def mark_agent_offer_surfaced(vault_root: Path) -> Path:
    """Record that the one-line offer was handed to an agent for its startup
    signal. Idempotent, empty-file marker, same shape as every other flag."""
    from datetime import datetime, timezone
    flag = Path(vault_root) / AGENT_OFFER_FLAG_REL
    flag.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with flag.open("a", encoding="utf-8") as fh:
        fh.write(stamp + "\n")
    return flag


def orientation_state(vault_root: Path) -> Dict[str, Any]:
    """The whole orientation picture as facts on disk, for a reader who is
    NOT the agent whose boot is in question -- a test, the release harness,
    an architect asking "has this install's tour ever fired?".

    Reports, never accuses, and never returns a verdict a caller should
    treat as a stop. `walk_offered=False` with `agent_offer_surfaced=True`
    is the exact signature of Po skipping her Step 8 and a later agent
    catching it; naming that state is the whole point, and it is the state
    the founder's own install was in with nobody able to say so.
    """
    root = Path(vault_root)
    walk = (root / FLAG_REL).is_file()
    agent = (root / AGENT_OFFER_FLAG_REL).is_file()
    handoffs = agent_offer_handoffs(root)
    if walk:
        summary = "the orientation walk has been offered to a human through the walk playbook"
    elif agent:
        summary = (
            "the walk has NEVER been offered through the walk playbook; the one-line "
            "tour offer has been HANDED TO AN AGENT {} time(s). Handed is not seen: "
            "this records what the tool did, not what a human read".format(handoffs)
        )
    else:
        summary = "the orientation tour has never been offered on this install, by any surface"
    return {
        "walk_offered": walk,
        "walk_flag": str(FLAG_REL),
        "agent_offer_surfaced": agent,
        "agent_offer_handoffs": handoffs,
        "agent_offer_handoff_ceiling": AGENT_OFFER_HANDOFF_CEILING,
        "agent_offer_flag": str(AGENT_OFFER_FLAG_REL),
        "automatic_walk_armed": not walk,
        "agent_fold_armed": should_fold_agent_offer(root),
        "summary": summary,
    }
