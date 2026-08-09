#!/usr/bin/env python3
"""
---
uid: 29931da1
title: "smoke — can this studio still do its own six operations?"
name: smoke
type: tool
status: active
owner: talos
domain: "Studio liveness — six real operations (BOOT, MINT, INDEX, COMMIT, BUILD, ORIENT) driven against the REAL studio the tool is invoked in. Answers the one question a validator cannot: not 'is the substrate well-formed' but 'can this studio still do its own work right now'. Stdlib-only, non-destructive, seconds."
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-smoke.py [--only OP] [--json] [--studio PATH]"
script_path: vault/tools/tropo-smoke.py
belt: true
belt_invocation: "python3 vault/tools/tropo-smoke.py"
belt_example: "python3 vault/tools/tropo-smoke.py --only index --json"
trigger_description: "Run after any retirement, after any commit that touches vault/tools/, and any time the studio feels wrong but the validator says it is fine. Six liveness probes in under thirty seconds."
author: talos-t37
created: '2026-07-31'
created_by: talos-t37
modified: '2026-07-31'
modified_by: talos-t37
schema_version: 2
governed_by: d5e1b4a3
member_of:
- 8dd772a0
refs:
- af6c53df
- d78cc16a
- 1f29bcfb
---

tropo-smoke — can this studio still do its own six operations?

WHY THIS EXISTS (dev-spec af6c53df, Metis G97/G98, 2026-07-30/31)
-----------------------------------------------------------------
On a single day, governance machinery blocked legitimate work NINE times.  Zero
of those firings caught a real attack or a real corruption; every one was a
false positive against legitimate work.  The validator reported the studio
healthy while agents could not be born, files could not be minted, and the
index could not be rebuilt.

A validator asks "is the substrate well-formed."  That question kept answering
yes.  This tool asks a different one, the only one that was actually failing:

    can this studio still DO its own six operations?

    1. BOOT   — can an agent still be born?
    2. MINT   — can a governed file be created AND indexed?
    3. INDEX  — can an existing entry be freshened?
    4. COMMIT — does a governed file survive the clean-filter round trip?
    5. BUILD  — does the cockpit still compile?
    6. ORIENT — can this studio answer a question about itself?

Each probe drives the real gesture against the real studio.  Nothing here is
simulated, and no probe constructs a world of its own to then find in order —
an instrument that builds its own world will always find that world healthy.
Where isolation is genuinely required (the COMMIT scratch path, the MINT
throwaway) the material is DERIVED FROM REAL SUBSTRATE and the derivation is
named at the point of use (spec R2).

THREE REQUIREMENTS THAT SHAPE THE CODE (af6c53df, added 2026-07-31)
-------------------------------------------------------------------
R1  INDEX must assert it SAW something, not merely that it exited zero.
    Break 8 was a rebuild that succeeded while examining nothing, because a
    stale per-machine digest under the gitignored .tropo-studio/locks/ made
    three validator gates report "0 rows checked" and PASS.  So probe_index
    reads the receipt the rebuild writes for its own run and fails when
    rows_checked is 0 — including when the operation exits 0 but leaves no
    receipt at all.  Absence of evidence is not evidence of a pass.

R2  The probes run against a studio that HAS state, never a pristine fixture.

R3  BOOT exercises the SUCCESSOR's birth, not the retiring agent's checklist.
    An agent's last act is the one act no gate can watch, because the agent is
    the thing that stops.  probe_boot is a dry-run successor birth against the
    substrate as it stands, reporting what the NEXT generation would hit.

OPERATION 6 — ORIENT, AND WHY IT IS THE SHARPEST CASE IN THE FILE
------------------------------------------------------------------
The first five operations ask whether this studio can still WORK.  The sixth
asks whether it can still THINK: given a task, can it draw a circle of relevant
substrate around it and rank that circle?  That is `orient_deterministic`
(lib/distiller.py) — the crew's flagship capability, and the deterministic core
underneath it: no model, no network, no spend.

It is here because of one measurement.  Metis G98 wired the shipped `orient()`
to this studio's real surfaces and found it COULD NOT RUN AT ALL: it failed
closed at the visibility floor with GROUP_RESOLUTION_UNAVAILABLE before a circle
was drawn, before anything was ranked, before a model was reached.  Her finding
is the mandate:

    "We had NO instrument that would ever have reported this.  The unit tests
     pass — they inject their own projection.  The validator passes — it does
     not call orient().  tropo-smoke passes BOOT and COMMIT — it does not
     exercise the crown.  A capability can be fully built, fully tested, fully
     green, and structurally unable to run on the machine it was built for, and
     nothing we own says a word."

THREE THINGS THIS PROBE WILL NOT DO, and each one is load-bearing:

  * It will NEVER install, bypass, or degrade past the group authority to
    produce a green.  A studio with no installed authority reports UNKNOWN with
    the one-time install named, because "no group authority installed for this
    Studio" is not a broken studio — it is an UNPERFORMED SETUP STEP.  An
    instrument that routes around the gate it reports on is worth less than no
    instrument.
  * It will NEVER confuse "the caller supplied nothing" with "the studio cannot
    resolve".  `visible_segments` refuses a viewer with no principal, and that
    refusal is the CALLER being wrong, not the studio.  So the viewer is built
    from a real principal the installed authority itself resolves, and if no
    such principal exists the answer is UNKNOWN — never a fabricated one.
  * It claims NO visibility the authority did not grant.  The viewer carries a
    principal and nothing else: no private-store claim, no widened audience.
    Everything this probe sees, the installed authority handed it.

It makes no claim about anything being secure.  What an installed authority
buys this studio is ATTRIBUTION, CONTINUITY, and knowing who is who — that is
the bar, and this probe reports against that bar and no higher one.

THREE STATES, NOT TWO, BECAUSE THEY HAVE DIFFERENT OWNERS (2026-08-01)
-----------------------------------------------------------------------
Argus A143's sharpening, endorsed by Metis:

    "The ORIENT probe: three states not two.  no-corpus,
     corpus-but-no-authority, and authority-installed-but-still-refusing have
     different OWNERS, so collapsing them into one UNKNOWN reproduces the
     failure the probe exists to catch."

The last clause is the whole of it.  This probe exists because a capability
could be fully built, fully tested, fully green and structurally unable to
run, and nothing said so.  An UNKNOWN that does not say WHOSE PROBLEM IT IS
leaves the reader exactly where they started — the same silence, one level up.
So the three are named, each carries its own owner and its own next action, no
two of them print the same cure, and the one that is a real defect is a FAIL.
The ladder that keeps them exclusive lives at `orient_state`.

IDENTITY IS RESIDENT IN THE STUDIO, NOT IN THE HARDWARE (ADR-065, 0a5d562d)
----------------------------------------------------------------------------
This probe used to call the installed group authority a MACHINE-LOCAL pin and
its cure a per-machine ceremony.  Mike ruled that wrong:

    "I want identity and authority to be resident in our studio ... The studio
     is portable across hardware.  What does the hardware have to do with
     authority?"

So: the authority record lives under `.tropo-studio/`, is tracked, and TRAVELS
WITH THE VAULT — a clone arrives already knowing who everyone is, and is never
told to perform a ritual on the box it landed on.  The
corpus-but-no-authority cure therefore names a ONE-TIME act for the Studio
that then travels, and names restoring the tracked record FIRST, because a
Studio that already has one and arrives without it has a deleted file rather
than an unperformed step.

The same ruling closed the question of making the read path fail closed
without a local trust record: answered NO.  A boundary needs two sides, and
between Mike and his own agents there is one.  Nothing in this probe adds one;
its refusal to install an authority is instrument integrity — do not report on
a gate you just opened — and not a defence of anything.

NON-DESTRUCTIVE, INCLUDING ON FAILURE (AC2)
--------------------------------------------
Every probe cleans up in `finally`, never on the happy path only — a probe that
fails is exactly the probe most likely to leave residue.  The MINT throwaway is
removed with the canonical soft-delete gesture (tropo-recycle.py); this module
never `rm`s a governed path.  The derived runtime state a real gesture
legitimately advances (index surfaces, surface seal, dirty counter, run
receipt, recycle bin, event stream) is snapshotted before and restored
byte-for-byte after, so running this twice leaves the tree byte-identical.

STDLIB ONLY (AC3)
-----------------
Like tropo-preflight (d78cc16a), this must run when the studio is PARTLY
BROKEN.  A third-party import defeats the purpose: the first thing that breaks
on a stranded machine is the thing that needs installing.  Every probe drives
the studio's own tools as SUBPROCESSES rather than importing them, so a tool
that cannot even import is reported as a finding instead of crashing the
instrument.

ORIENT is where that rule earns its keep rather than merely obeying it.
`orient_deterministic` lives in vault/tools/lib/, and importing it in-process
pulls PyYAML and cryptography into THIS interpreter (measured: lib.distiller ->
lib.viewer_projection -> lib.segment -> yaml, and lib.audience_gate ->
lib.group_authority -> cryptography).  A studio missing those is break 7
exactly — "Python deps declared 07-21 but not shipped to the fork that needs
them" — and an instrument that dies on the import cannot report the other five
operations, which have nothing to do with orient.  So ORIENT drives the library
out-of-process, the way probe_index drives lib/index_surfaces.py, and a missing
third-party dependency comes back as an UNKNOWN about one operation instead of
a traceback about all six.

THE BUDGET IS 120 SECONDS, AND 30 IS `--fast` (AC7, AMENDED 2026-07-31)
------------------------------------------------------------------------
The first live run measured the collision.  A real index rebuild on this studio
costs 20-40s, so a 30s TOTAL budget forces sub-budgets of about 2s onto MINT,
INDEX and BUILD, and all three then time out.  Three of the five operations
were being reported as unfinished by the clock rather than by the studio.

So the DEFAULT budget is 120s and the 30s promise is preserved as `--fast`,
"because the instrument's job is truth and an instrument that cannot afford to
look is the failure mode this whole spec exists to kill" (Metis G98).  Every
per-probe ceiling is a FRACTION of the active budget rather than a constant
measured against 30, so the two budgets are one behaviour at two scales and
there is no second set of numbers to drift.

THREE OUTCOMES, BECAUSE TIMEOUT IS NOT FAILURE (AC7a)
------------------------------------------------------
A probe that did not finish reports UNKNOWN, never FAIL, and says what it did
and did not check.  "Reporting red-when-blind erodes trust in an instrument
exactly as fast as reporting green-when-blind, and it is the same defect
wearing the opposite sign."

The line this module draws, stated once so every probe can be read against it:

    FAIL     the studio was observed to be unable to do the operation.
             A determined answer, in the negative.
    UNKNOWN  this instrument could not determine whether the studio can do the
             operation — it ran out of budget, could not read, or was never
             provisioned to look.  Not an answer at all, and reported as one.
    PASS     the operation was driven end to end and it worked.

Two refinements that fall out of that line and are worth naming, because both
are places a careless reading goes wrong:

  * A confirmed blocker found BEFORE the clock ran out is still FAIL.  The scan
    being partial cannot un-see a defect, and reporting UNKNOWN there would
    hide a real finding behind the budget.  The partiality is recorded in
    evidence (`scan_complete`) rather than in the verdict.
  * A machine that has never provisioned the thing under test is UNKNOWN, not
    FAIL.  `node_modules/.bin/tsc` missing says nothing about whether the
    cockpit compiles; it says this machine has not run `npm install`.  Failing
    it would be one more gate refusing legitimate work, which is the disease.

`ProbeResult.status` is the primary field and `ok` is DERIVED from it
(`status == "pass"`), so every existing truthiness check keeps meaning exactly
"passed" and can never quietly acquire an UNKNOWN.  Nothing in this module
counts failures by negating `ok`; failure counting goes through `failures()`,
which tests `status == "fail"` and nothing else.  There is a structural test
in the suite that holds that line.

USAGE
    python3 vault/tools/tropo-smoke.py                 # all six, 120s budget
    python3 vault/tools/tropo-smoke.py --fast          # the 30s budget (AC7)
    python3 vault/tools/tropo-smoke.py --only index    # one operation
    python3 vault/tools/tropo-smoke.py --json          # machine-readable
    python3 vault/tools/tropo-smoke.py --studio PATH   # another studio root

EXIT CODES
    0  every probe ran and passed
    1  at least one probe FAILED — a problem was found
    3  nothing failed, but at least one probe could not determine an answer
    2  usage error

Three outcomes get three codes for the same reason `status` has three values:
folding them loses the distinction the amendment exists to preserve.  Exit 0 is
the positive claim "every operation was exercised and every one worked",
and a run that could not look has not earned it — that is green-when-blind at
the process boundary.  Exit 1 is the positive claim "this studio has a
problem", and a run that could not look has not earned that either.  Neither is
true, so UNKNOWN gets its own code.  FAIL dominates UNKNOWN: a found problem is
the strongest fact in a run, so any failure makes the whole run 1.

Exit 0 is also why ORIENT's missing-authority answer is UNKNOWN and not PASS.
A Studio that has never had a group authority installed has not been shown
able to orient; saying so costs the run its 0, and that is the correct price.

This is NOT a landing gate.  It prints loudly; whether it blocks is Argus's
call (af6c53df §Lanes).  When it does become one, the gate condition is
`rc == 1`, not `rc != 0`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

# ORIENT is LAST, and the position is an argument rather than an accident. It
# reads the composed index, so it must run after the operation that freshens
# one; and it is the only probe that asks whether the studio can still think
# rather than whether it can still work, which is the question worth leaving
# the reader on.
OPERATIONS: tuple[str, ...] = (
    "boot", "mint", "index", "commit", "build", "orient",
)

# The three outcomes. `unknown` is not a shade of `fail`; it is the absence of
# an answer, and every consumer in this module is required to say which of the
# three it means rather than negating another one (AC7a).
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_UNKNOWN = "unknown"
STATUSES: tuple[str, ...] = (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN)

# AC7 as amended 2026-07-31 by Metis G98 after the first live run measured the
# collision: a real index rebuild on this studio is 20-40s, so a 30s TOTAL
# budget forced ~2s sub-budgets onto MINT, INDEX and BUILD and timed all three
# out. 30s is preserved as `--fast`; the default is the one that can afford to
# look.
FAST_BUDGET_SECONDS = 30
TIME_BUDGET_SECONDS = 120

# Ceilings for ONE hung probe, not expected cost. Without them a single wedged
# subprocess eats the whole budget and the remaining operations never run —
# which is the same silence this tool exists to break.
#
# Expressed as a FRACTION of the ACTIVE budget, never as seconds. That is the
# amendment's real content: the first build hardcoded 10/25/20/10/25 against a
# 30s budget, so raising the budget would have left every ceiling behind and
# the collision would have survived the fix. The fractions below ARE those five
# numbers over 30, so `--fast` reproduces the original behaviour exactly and
# the default is the same instrument with four times the room.
#
# ORIENT's share is BOOT's, and it is a measurement rather than a guess: the
# whole deterministic orient — interpreter start, the PyYAML/cryptography
# import chain, resolver load, anchor selection, draw and rank — costs about
# half a second on this studio's 4,832-entry index. Ten seconds of a 30s budget
# is twenty times that, which is a ceiling for a HUNG library rather than a
# guess at the cost.
PROBE_BUDGET_SHARES: dict[str, float] = {
    "boot": 10.0 / 30.0,
    "mint": 25.0 / 30.0,
    "index": 20.0 / 30.0,
    "commit": 10.0 / 30.0,
    "build": 25.0 / 30.0,
    "orient": 10.0 / 30.0,
}
DEFAULT_PROBE_SHARE = 15.0 / 30.0

# The floor under a ceiling that the elapsed budget has already eaten. Also a
# fraction, for the same reason. See _timeout_for.
TIMEOUT_FLOOR_SHARE = 2.0 / 30.0

# The shell convention for "killed by a timeout". `_Ran` carries an explicit
# `timed_out` flag; `_git_bytes` keeps the payload as bytes and has only a
# return code to speak with, so it says it here. Named rather than spelled 124
# at each site, because a caller that mistakes this for a real exit status
# reports a broken clean filter over a slow one (AC7a).
_RC_TIMEOUT = 124

# Slug stamped into the MINT throwaway so cleanup can attribute the file to
# this tool and never to a concurrent agent's fresh mint.
SMOKE_AUTHOR = "tropo-smoke-probe"

# The type MINT throws away. `note` is the lightest governed type with a
# capsule §Template leg; picking a heavier one would test the capsule, not the
# mint path.
SMOKE_MINT_TYPE = "note"

_HEX8 = re.compile(r"^[0-9a-f]{8}$")
_FM_SCALAR = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*?)[ \t]*$")
_GENERATION_TAIL = re.compile(r"^(.*?)(\d+)$")
_NAV_START = "<!-- nav-block:start -->"
_NAV_END = "<!-- nav-block:end -->"

# The rendered nav region, LINE-ANCHORED, mirroring the pinned _NAV_BLOCK_RE in
# tropo-generate-relations-header.py (the single source of truth the clean
# filter imports). Anchoring is not a detail: an unanchored match already
# corrupted authored text once, when a walk-brief that quotes both sentinels
# mid-prose was treated as carrying a block (vault/files/69ea3f38.md, self-heal
# note at _NAV_BLOCK_RE). A liveness probe that fails a studio because one of
# its documents TALKS about nav blocks is manufacturing exactly the
# false-positive class this tool exists to end. Kept in bytes because the whole
# COMMIT comparison is a byte comparison; `^` after \n and the ASCII sentinels
# make the byte and text forms agree, since \n cannot occur inside a UTF-8
# multi-byte sequence.
_NAV_REGION_RE = re.compile(
    rb"^<!-- nav-block:start -->\n.*?^<!-- nav-block:end -->\n*",
    re.DOTALL | re.MULTILINE,
)

# An activation entry in one of these states has stopped. Mirrors the terminal
# set the fleet-boot-health check uses in tropo-validate.py; `failed` and
# `superseded` are included because a successor derives past those too.
_TERMINAL_ACTIVATION_STATES = frozenset(
    {"retired", "retiring", "stale", "closed", "failed", "superseded"}
)

# Fields a retirement stamps on the way out. None of them appears on an entry
# that has not been closed, so any of them next to `status: active` means the
# retirement completed everywhere except the one field the gate reads.
_RETIREMENT_EVIDENCE_FIELDS: tuple[str, ...] = (
    "retired_at", "closure_reason", "closed_at", "retirement_reason",
)

ACTIVATION_TOOL_REL = "vault/tools/40b2f455.py"

# Derived runtime state a real index gesture legitimately advances. None of it
# is a governed change this instrument is entitled to leave behind (AC2).
# Order matters: the SQLite database goes back before its write-ahead log and
# shared-memory sidecar, so the trio is never briefly inconsistent on disk.
# The sidecars are listed at all because a clean close checkpoints and removes
# them, and a probe that silently deletes two files is not non-destructive.
_INDEX_DERIVED_FILES: tuple[str, ...] = (
    "vault/00-index.jsonl",
    "vault/00-archive-index.jsonl",
    "vault/00-index.sqlite",
    "vault/00-index.sqlite-wal",
    "vault/00-index.sqlite-shm",
    "vault/00-project-tree.jsonl",
    ".tropo-studio/dirty-counter.json",
)

# Guarded whole, not file by file. The seal, the ratchet, the transaction
# journal, the run receipt and the write lock all live here, the rebuild
# invents new ones as it goes, and the write lock in particular is left behind
# carrying the PID of whoever last held it — so a run that named the files
# individually would still leave a different byte in the tree every time.
_INDEX_DERIVED_DIRS: tuple[str, ...] = (
    ".tropo-studio/locks",
    ".tropo-studio/shards",
)

# recycle emits tropo.substrate.recycled, which appends to the tracked event
# ledger. Real record of a real gesture — but the gesture was a liveness probe,
# not studio work, so the append is this tool's residue and is rolled back.
_MINT_DERIVED_FILES: tuple[str, ...] = _INDEX_DERIVED_FILES + (
    "vault/events/00-events.jsonl",
    ".tropo-studio/event-writer-instance.json",
)

INDEX_RUN_RECEIPT_REL = ".tropo-studio/shards/index-rebuild-run.json"

REBUILD_TOOL_REL = "vault/tools/tropo-rebuild-index.py"

# ADR-063 owed an instrument reporting how many metas still need the
# superseded-format digest door, so the door can be closed on evidence rather
# than on a guess. It cannot be a central count: the seal lives under the
# gitignored .tropo-studio/locks/, is written per machine, and is never pushed
# — the same invisibility that made break 8 possible. So the count is the union
# of per-machine readings, and this probe is where a reading gets taken,
# because INDEX is the operation an agent already runs on any machine at any
# time. Driven as a subprocess like every other tool here (AC3): recomputing
# the digest inside this file would fork the one function that defines what a
# valid seal is, and a second copy of that function is how the formats drifted
# apart in the first place.
LEGACY_DIGEST_DOOR_TOOL_REL = "vault/tools/lib/index_surfaces.py"

# ── ORIENT (operation 6) ─────────────────────────────────────────────────────

# The deterministic core the probe exercises, and the composed index every one
# of its adapters reads. Named as paths rather than imported: see the AC3 note
# in the module docstring.
ORIENT_LIBRARY_REL = "vault/tools/lib/distiller.py"
COMPOSED_INDEX_REL = "vault/00-index.sqlite"

# The rebuild that composes that index. Defined here, with the ORIENT
# constants, rather than beside the other tool commands, because it IS the
# no-corpus state's next action and a state whose cure is declared three
# screens away from the state is a cure that drifts away from it.
FULL_REBUILD_CURE = "python3 vault/tools/tropo-rebuild-index.py --apply"

# The Studio-resident record that says a group authority has been installed,
# and the directory it lives in.
#
# RESIDENT IN THE STUDIO, and that word replaced a hardware-scoped one here on
# 2026-08-01 (ADR-065, 0a5d562d). Scoping it to the box made a portable Studio
# owe a one-time act to every machine it was ever cloned to, and it does not:
# the record is tracked, it travels with the vault, and a clone arrives already
# knowing who everyone is. Hardware is not a participant.
#
# This probe READS it and never writes it (constraint: an instrument may not
# route around the gate it reports on).
GROUP_AUTHORITY_PIN_REL = ".tropo-studio/authorities/group-authority/installed.json"
GROUP_AUTHORITY_DIR_REL = ".tropo-studio/authorities/"
GROUP_AUTHORITY_TOOL_REL = "vault/tools/tropo-group-authority.py"

# The install, named in full, because the whole point of reporting UNKNOWN here
# is that a human can go and do it. Four steps, in order, performed ONCE FOR
# THE STUDIO — not once per machine — and none of them is a step this tool is
# entitled to take on their behalf.
#
# The restore line comes FIRST, and that ordering is the ADR-065 consequence
# rather than a stylistic choice. Because the record travels with the vault, a
# Studio that has one and arrives without it is looking at a deleted tracked
# file, and printing only the four-step install would send that reader off to
# redo something they already own.
GROUP_AUTHORITY_INSTALL_CURE = (
    f"git checkout -- {GROUP_AUTHORITY_DIR_REL}"
    "  # first, if this vault should already carry one: the record is tracked "
    "and travels with the Studio\n"
    f"python3 {GROUP_AUTHORITY_TOOL_REL} build"
    f"  ->  accept-fingerprint  ->  verify  ->  install"
    "  # otherwise install one ONCE for the Studio, by a human; it then "
    "travels with the vault and no clone repeats it. This probe will not "
    "perform it"
)
GROUP_REGISTRY_CURE = "python3 vault/tools/tropo-rebuild-group-registry.py"
GROUP_AUTHORITY_VERIFY_CURE = f"python3 {GROUP_AUTHORITY_TOOL_REL} verify"

# The next action when the authority IS installed and orient still will not
# answer: make the authority verify itself, then re-project the resolver
# surface visibility reads. Held apart from the other two states' cures on
# purpose — a reader who cannot tell the three states apart by the command they
# are handed has been given the collapsed UNKNOWN back in a different costume.
ORIENT_RETRIEVAL_CURE = f"{GROUP_AUTHORITY_VERIFY_CURE} && {GROUP_REGISTRY_CURE}"

# How many members the circle is asked for. Big enough that "ranked" is
# visible (a one-member circle is trivially in order and would make the
# ordering check decoration), small enough that the draw stays cheap on a
# 1,850-degree hub.
ORIENT_CIRCLE_BUDGET = 25

# How far down the connectivity ranking the anchor search is allowed to walk
# before it gives up and reports UNKNOWN. Bounded so the probe cannot spend its
# ceiling searching, and so "nothing in this studio is inside this viewer's
# audience" is reached rather than approached.
ORIENT_ANCHOR_SHORTLIST = 8


# ── the three ORIENT states, because they have different OWNERS ──────────────
#
# Argus A143, endorsed by Metis: "no-corpus, corpus-but-no-authority, and
# authority-installed-but-still-refusing have different OWNERS, so collapsing
# them into one UNKNOWN reproduces the failure the probe exists to catch."
#
# An UNKNOWN that does not name an owner tells the reader that somebody should
# do something. Every one of the three below tells them WHO, and hands them a
# different command, so the three can be told apart at a glance in a report
# that scrolls past.


@dataclass(frozen=True)
class OrientState:
    """One rung of the orientation ladder: what is missing, and whose it is.

    `status` is carried on the state rather than decided at each branch so the
    two UNKNOWNs and the one FAIL cannot drift apart from the names. The
    difference is the substance: two of these are nobody having done a thing
    yet, and the third is a defect in something that was done.
    """

    name: str
    owner: str
    next_action: str
    status: str

    def opening(self) -> str:
        """The first thing in the detail line, so the owner reads at a glance."""
        return f"{self.name} (owner: {self.owner})"

    def stamp(self, evidence: dict) -> "OrientState":
        """Put the state where a machine can route on it, not only in prose."""
        evidence["orient_state"] = self.name
        evidence["orient_state_owner"] = self.owner
        return self


# Nobody can orient over nothing. The composed index is absent, unreadable, or
# empty, and until it is rebuilt no question about retrieval can be asked at
# all — so this is UNKNOWN and it belongs to whoever rebuilds the index.
ORIENT_NO_CORPUS = OrientState(
    name="no-corpus",
    owner="whoever rebuilds the composed index",
    next_action=FULL_REBUILD_CURE,
    status=STATUS_UNKNOWN,
)

# The corpus is there and no group authority has ever been installed for the
# Studio, so visibility cannot resolve. NOT A BROKEN STUDIO — an unperformed
# setup step, and the reason it is UNKNOWN rather than FAIL. One human act,
# once, for the Studio; the record then travels with the vault (ADR-065).
ORIENT_NO_AUTHORITY = OrientState(
    name="corpus-but-no-authority",
    owner="a human, once for the Studio; the record then travels with the vault",
    next_action=GROUP_AUTHORITY_INSTALL_CURE,
    status=STATUS_UNKNOWN,
)

# Corpus present, authority installed, and orient still cannot answer. This is
# the one that is a REAL DEFECT — Metis G98's finding, and the reason ORIENT is
# in this tool at all — so it is FAIL, and it has to be distinguishable from
# the two above without reading past the first phrase.
ORIENT_STILL_REFUSING = OrientState(
    name="authority-installed-but-still-refusing",
    owner="whoever owns the retrieval path",
    next_action=ORIENT_RETRIEVAL_CURE,
    status=STATUS_FAIL,
)

ORIENT_STATES: tuple[OrientState, ...] = (
    ORIENT_NO_CORPUS, ORIENT_NO_AUTHORITY, ORIENT_STILL_REFUSING,
)


def orient_state(corpus_readable: bool, authority_installed: bool = False,
                 orient_answered: bool = False) -> Optional[OrientState]:
    """Which of the three states this studio is in, or None when it can orient.

    A LADDER, and the ORDER is the argument. Each rung is only a meaningful
    question once the rung beneath it holds: debugging retrieval over an index
    nobody can read is wasted, and installing an authority over an absent
    corpus buys nothing. Reading them in order is also what makes the three
    MUTUALLY EXCLUSIVE and EXHAUSTIVE rather than three labels that can be true
    at once — which is the collapse Argus warned about, wearing a different
    hat. Over the whole (corpus, authority, answered) cube exactly one of the
    four outcomes holds at every point, and there is a case in the suite that
    enumerates all eight and says so.

    THE DEFAULTS MEAN "NOT ESTABLISHED", and that is safe for exactly one
    structural reason: the ladder returns at the first rung that fails, so a
    caller who fell off rung 1 never reaches the value it never had. A caller
    that HAS established a rung is required to say so.

    WHAT IS DELIBERATELY NOT A STATE. Being unable to LOOK is not one of the
    three, and giving it a fourth name would re-collapse the distinction the
    three exist to make. A clock that ran out, a machine with no PyYAML, a
    driver of this instrument's own that crashed, an authority that names no
    principal to view as, a studio where nothing at all is inside the viewer's
    audience — none of those is a fact about the Studio with an owner in it.
    They stay UNKNOWN, they say what they did and did not check, and they carry
    no `orient_state`, because inventing an owner for them is precisely the
    false-positive class this tool exists to end.
    """
    if not corpus_readable:
        return ORIENT_NO_CORPUS
    if not authority_installed:
        return ORIENT_NO_AUTHORITY
    if not orient_answered:
        return ORIENT_STILL_REFUSING
    return None


MINT_TOOL_REL = "vault/tools/tropo-mint-id.py"
RECYCLE_TOOL_REL = "vault/tools/tropo-recycle.py"
NAVBLOCK_TOOL_REL = "vault/tools/tropo-navblock-strip.py"
NAVBLOCK_INSTALL_CURE = f"python3 {NAVBLOCK_TOOL_REL} --install"
NAVBLOCK_VERIFY_CURE = f"python3 {NAVBLOCK_TOOL_REL} --verify-install"

# The escape hatch for a SEALED-METADATA deadlock, which --apply alone cannot
# open: metadata recovery is authorized only by a full source re-derivation
# (`reconcile and full_source_derivation_proof is not None`, tropo-rebuild-
# index.py). Naming --apply for that failure would be naming a command that
# refuses again, which is worse than naming none — a cure that does not cure
# is how an operator learns to stop reading the cure line.
METADATA_RECOVERY_CURE = (
    "python3 vault/tools/tropo-rebuild-index.py --apply --reconcile"
)

# Refusal fingerprints. Matched against the rebuilder's own message rather
# than guessed from the exit code. The first entry is the important one: when
# the studio names its own recovery in prose, take it at its word instead of
# pattern-matching the failure — every later line here is a fallback for a
# refusal that did not say.
_REFUSAL_CURES: tuple[tuple[str, str], ...] = (
    ("source-complete reconcile", METADATA_RECOVERY_CURE),
    ("pair digest mismatch", METADATA_RECOVERY_CURE),
    ("index-surface metadata", METADATA_RECOVERY_CURE),
    ("surface metadata", METADATA_RECOVERY_CURE),
    ("invalid source inventory identity", METADATA_RECOVERY_CURE),
    ("shrink-floor evidence", METADATA_RECOVERY_CURE),
    ("invalid shrink ratchet", METADATA_RECOVERY_CURE),
)

# run_all publishes the wall-clock deadline here so a later probe can shrink its
# own ceiling to what is left of the budget. A probe called directly (the test
# surface, `--only`) sees None and uses its own ceiling.
_DEADLINE: Optional[float] = None

# The budget this run is actually working to. run_all sets it and restores the
# default in `finally`, so a `--fast` run can never leave a 30s ceiling behind
# for the next caller in the same process.
_BUDGET_SECONDS: float = float(TIME_BUDGET_SECONDS)


@dataclass(frozen=True)
class ProbeResult:
    """One operation's verdict, in three values rather than two.

    `cure` is AC4's whole point: "MINT: FAIL" is not acceptable output. A
    failing probe names the operation, the exact error, and a command a human
    can paste. `evidence` carries measured facts, never adjectives — R1 lives
    there (`rows_checked`).

    `status` is the primary field and `ok` is derived from it. The obvious
    alternative — leaving `ok` as the primary field and widening it to
    Optional[bool] — is a trap, because `if not result.ok` is true for both
    False and None, so every careless caller would silently count UNKNOWN as
    FAIL: the exact defect AC7a exists to prevent, arriving through the
    representation instead of through the logic. Deriving `ok` from `status`
    inverts that: the cheap check keeps its old meaning ("passed"), it can
    never widen, and anything that wants to count problems has to name
    `STATUS_FAIL` out loud.
    """

    operation: str
    status: str
    detail: str
    cure: str
    elapsed_s: float
    evidence: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Passed. Only ever passed — never 'did not fail'."""
        return self.status == STATUS_PASS

    @property
    def failed(self) -> bool:
        """A problem was FOUND. An UNKNOWN is not one of these."""
        return self.status == STATUS_FAIL

    @property
    def unknown(self) -> bool:
        """No answer was reached: out of budget, unreadable, or unprovisioned."""
        return self.status == STATUS_UNKNOWN

    def as_dict(self) -> dict:
        return {
            "operation": self.operation,
            "status": self.status,
            # Kept, and kept meaning exactly "passed", so a machine reader
            # written against the two-outcome shape cannot silently start
            # treating UNKNOWN as a green.
            "ok": self.ok,
            "detail": self.detail,
            "cure": self.cure,
            "elapsed_s": round(self.elapsed_s, 3),
            "evidence": self.evidence,
        }


def _passed(operation: str, detail: str, elapsed_s: float,
            evidence: Optional[dict] = None) -> ProbeResult:
    evidence = evidence if evidence is not None else {}
    evidence["degraded"] = False
    return ProbeResult(operation, STATUS_PASS, detail, "", elapsed_s, evidence)


def _failed(operation: str, detail: str, cure: str, elapsed_s: float,
            evidence: Optional[dict] = None) -> ProbeResult:
    """A determined negative: the studio was OBSERVED unable to do this."""
    evidence = evidence if evidence is not None else {}
    evidence.setdefault("degraded", False)
    return ProbeResult(operation, STATUS_FAIL, detail, cure, elapsed_s, evidence)


def _unknown(operation: str, detail: str, cure: str, elapsed_s: float,
             evidence: Optional[dict] = None,
             checked: Iterable[str] = (),
             not_checked: Iterable[str] = ()) -> ProbeResult:
    """No answer. AC7a's third outcome, and it has to earn the word.

    A bare "UNKNOWN" is as useless as "MINT: FAIL" — it names the absence of a
    verdict without saying how much of the operation was actually driven. So
    the partial work is mandatory here rather than optional: `checked` and
    `not_checked` are stamped into evidence by the constructor, and the caller
    is expected to have put the same two lists into `detail` in prose. A cure
    is required too, because the thing a human does next after an UNKNOWN
    (usually: run this one operation by hand, without a clock on it) is exactly
    as actionable as the thing they do after a FAIL.
    """
    evidence = evidence if evidence is not None else {}
    evidence["degraded"] = True
    evidence["checked"] = list(checked)
    evidence["not_checked"] = list(not_checked)
    return ProbeResult(operation, STATUS_UNKNOWN, detail, cure, elapsed_s,
                       evidence)


def failures(results: Iterable[ProbeResult]) -> list[ProbeResult]:
    """Every probe that FOUND a problem.

    The one place in this module that decides what a failure is. It tests
    `status == STATUS_FAIL` and nothing else, so an UNKNOWN cannot be swept in
    by a `not result.ok` written in a hurry three months from now.
    """
    return [result for result in results if result.status == STATUS_FAIL]


def unknowns(results: Iterable[ProbeResult]) -> list[ProbeResult]:
    """Every probe that could not determine an answer."""
    return [result for result in results if result.status == STATUS_UNKNOWN]


def passes(results: Iterable[ProbeResult]) -> list[ProbeResult]:
    return [result for result in results if result.status == STATUS_PASS]


def exit_code_for(results: Iterable[ProbeResult]) -> int:
    """0 all passed / 1 something failed / 3 something could not be determined.

    See the module docstring for the argument. Kept as one named function so
    the mapping is testable and there is exactly one place it can drift.
    """
    results = list(results)
    if failures(results):
        return 1
    if unknowns(results):
        return 3
    return 0


# ── studio + small stdlib helpers ────────────────────────────────────────────


def studio_root() -> Path:
    """The studio root: this file lives at <root>/vault/tools/."""
    return Path(__file__).resolve().parents[2]


def active_budget() -> float:
    """The budget this run is working to: TIME_BUDGET_SECONDS, or 30 under
    `--fast`. Every ceiling in this module is a fraction of this number."""
    return _BUDGET_SECONDS


def _timeout_for(operation: str) -> float:
    """This probe's ceiling, derived from the ACTIVE budget and then shrunk to
    whatever is left of it.

    Derived, not looked up. AC7's amendment is only real if the ceilings move
    with the budget: the first build's `PROBE_TIMEOUTS = {"index": 20.0, ...}`
    was measured against 30 seconds, and raising the budget to 120 while
    leaving those constants in place would have kept INDEX capped at 20s
    against a rebuild that costs 20-40s — the amendment applied to the total
    and withheld from the operation it was written for.
    """
    budget = active_budget()
    ceiling = budget * PROBE_BUDGET_SHARES.get(operation, DEFAULT_PROBE_SHARE)
    # Never hand a subprocess a zero/negative timeout: a budget that has already
    # run out should still get one honest attempt with a small floor, so the
    # report says "did not finish" rather than "was never tried". The floor is
    # the one thing that can carry a run past the budget, and it is bounded at
    # a fixed share per remaining subprocess probe — a deliberate trade of a
    # few seconds of overrun for never reporting an operation as untried. It is
    # a smaller trade than it was, because an operation that gets only the
    # floor now reports UNKNOWN rather than FAIL (AC7a).
    floor = max(2.0, budget * TIMEOUT_FLOOR_SHARE)
    if _DEADLINE is None:
        return ceiling
    remaining = _DEADLINE - time.monotonic()
    return max(floor, min(ceiling, remaining))


def _step_timeout(operation: str, share: float = 0.5) -> float:
    """A ceiling for ONE step inside a probe, as a share of the probe's own.

    The commit probe alone runs ten git invocations. Giving each of them a
    hardcoded 20s meant one probe could spend a minute inside a ten-second
    ceiling, which is the same class of bug as the hardcoded probe ceilings:
    a number written against one budget and then never told the budget moved.
    """
    return max(2.0, _timeout_for(operation) * share)


def _cleanup_timeout() -> float:
    """Cleanup gets its own floor, and it deliberately outranks the budget.

    AC2 says a failed probe leaves no residue. A probe that abandons its
    soft-delete to save three seconds turns one broken studio into two, and
    the run most likely to need cleanup is the run that already ran out of
    time — so this floor does not shrink with the remaining budget the way a
    measurement ceiling does. Overrunning the clock is a reporting problem;
    leaving a governed orphan behind is a damage problem.
    """
    return max(15.0, active_budget() * 0.25)


class _Ran:
    """Result of one subprocess: returncode, output, and whether it timed out."""

    __slots__ = ("rc", "out", "err", "timed_out", "argv", "elapsed_s")

    def __init__(self, rc: int, out: str, err: str, timed_out: bool,
                 argv: list[str], elapsed_s: float) -> None:
        self.rc = rc
        self.out = out
        self.err = err
        self.timed_out = timed_out
        self.argv = argv
        self.elapsed_s = elapsed_s

    @property
    def diagnostic(self) -> str:
        text = (self.err or "").strip() or (self.out or "").strip()
        return _tail(text)


def _run(argv: list[str], cwd: Path, timeout: float,
         env: Optional[dict] = None, stdin: Optional[bytes] = None) -> _Ran:
    """Run a subprocess, never raise. A tool that cannot even start is a
    finding, not a stack trace — this instrument has to survive the studio
    being partly broken."""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=({**os.environ, **env} if env else None),
            input=(stdin.decode("utf-8", "surrogateescape")
                   if stdin is not None else None),
        )
    except subprocess.TimeoutExpired as exc:
        return _Ran(
            _RC_TIMEOUT,
            exc.stdout if isinstance(exc.stdout, str) else "",
            f"timed out after {timeout:.1f}s",
            True,
            argv,
            time.monotonic() - started,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _Ran(127, "", f"could not run {argv[0]}: {exc}", False, argv,
                    time.monotonic() - started)
    return _Ran(proc.returncode, proc.stdout or "", proc.stderr or "", False,
                argv, time.monotonic() - started)


def _git(studio: Path, *args: str, timeout: float = 20.0,
         env: Optional[dict] = None) -> _Ran:
    return _run(["git", *args], studio, timeout, env=env)


def _git_bytes(studio: Path, args: list[str], timeout: float = 20.0,
               env: Optional[dict] = None,
               stdin: Optional[bytes] = None) -> tuple[int, bytes, bytes]:
    """git, with the payload kept as bytes.

    The clean filter is a byte transformation and the whole COMMIT probe is a
    byte comparison; decoding to text here would hide exactly the kind of
    trailing-newline difference the filter is capable of introducing.
    """
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(studio), capture_output=True,
            timeout=timeout, input=stdin,
            env=({**os.environ, **env} if env else None),
        )
    except subprocess.TimeoutExpired:
        return _RC_TIMEOUT, b"", f"timed out after {timeout:.1f}s".encode()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, b"", f"could not run git: {exc}".encode()
    return proc.returncode, proc.stdout or b"", proc.stderr or b""


def _tail(text: str, limit: int = 480) -> str:
    """Squeeze a tool's output to one readable line.

    Head AND tail, because these messages put the refusal reason first and the
    remediation last, and dropping either end is how a cure gets lost.
    """
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    return text[:head] + " … " + text[-(limit - head):]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> tuple[list[dict], int]:
    """Return (records, malformed_line_count). Malformed lines are counted, not
    swallowed: a corrupt index surface is itself a finding."""
    records: list[dict] = []
    malformed = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(record, dict):
                records.append(record)
            else:
                malformed += 1
    return records, malformed


def _frontmatter_or_reason(path: Path,
                           limit: int = 32768) -> tuple[Optional[dict], str]:
    """Scalar YAML frontmatter, plus WHY it is absent when it is.

    The two absences are different verdicts under AC7a and collapsing them is
    how a probe reports red while blind. A governed file that is NOT THERE is a
    determined block on the successor — the index row points at nothing. A
    governed file that IS there and could not be read is a lineage this
    instrument did not check, and saying "the successor would halt" about a
    lineage nobody looked at is a fabricated finding.

    Deliberately not a YAML parser: it reads flat `key: value` scalars out of
    the leading `---` block, which is all any probe here needs. A real parser
    would mean a third-party import, and AC3 forbids one.
    """
    if not path.exists():
        return None, "missing"
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(limit)
    except OSError as exc:
        return None, f"unreadable ({exc.__class__.__name__}: {exc})"
    if not head.startswith("---"):
        return None, "no frontmatter block"
    lines = head.splitlines()
    scalars: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = _FM_SCALAR.match(line)
        if not match:
            continue
        value = match.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        scalars[match.group(1)] = value
    return scalars, ""


def _frontmatter(path: Path, limit: int = 32768) -> Optional[dict]:
    """Scalars only, for callers that do not need to tell the absences apart."""
    scalars, _reason = _frontmatter_or_reason(path, limit)
    return scalars


def _next_generation(label: str) -> str:
    """The successor's generation label. Handles both fleet shapes: executive
    prefixes (A142 -> A143) and slug-numbered session agents (…-054 -> …-055).
    Empty when the label carries no number to advance — that is a real block on
    the successor's birth, not a probe defect, so it is reported rather than
    guessed around."""
    match = _GENERATION_TAIL.match((label or "").strip())
    if not match:
        return ""
    digits = match.group(2)
    return f"{match.group(1)}{str(int(digits) + 1).zfill(len(digits))}"


def _rebuild_cure(studio: Path, diagnostic: str) -> str:
    """Pick the command that actually reopens THIS refusal.

    The rebuilder refuses for several different reasons and only one of them
    is repaired by a plain `--apply`. A sealed-metadata mismatch deadlocks the
    Studio precisely because the sanctioned repair is gated behind the check
    that is refusing, and only a source-complete reconcile is authorized to
    re-stamp the seal. AC4 asks for the command a human runs next, which means
    the one that works — not the one that is usually right.
    """
    text = (diagnostic or "").lower()
    for fingerprint, cure in _REFUSAL_CURES:
        if fingerprint in text:
            if cure == METADATA_RECOVERY_CURE:
                return _metadata_recovery_cure(studio)
            return cure
    # The tool frequently names its own recovery inline; prefer the studio's
    # own instruction over anything inferred here.
    named = re.search(r"run `([^`]+)`", diagnostic or "")
    if named and "rebuild-index" in named.group(1):
        return named.group(1)
    return FULL_REBUILD_CURE


def _metadata_recovery_cure(studio: Path) -> str:
    """The reconcile that re-stamps a deadlocked seal — plus, when the tree
    needs it, the step without which that reconcile refuses too.

    Metadata recovery is authorized only by a source-complete derivation, and
    a worktree carrying uncommitted derivation inputs is not source-complete:
    the reconcile answers `REFUSAL: uncommitted derivation inputs are
    non-authoritative … Land, revert, or isolate the recorded paths first`.
    Naming the bare reconcile to an operator whose tree is dirty sends them
    into a second refusal, so the dirty case names the isolate/restore pair
    around it. Isolating is the reversible one of the studio's own three
    options, which is why it is the one named here.

    The isolate EXCLUDES .tropo-studio/, and that exclusion is load-bearing
    rather than tidy. dirty-counter.json under it is tracked, so a blanket
    `stash push -u` sweeps it in — and the reconcile then rewrites the very
    file it is holding, so the closing `stash pop` aborts with "local changes
    would be overwritten by merge" and strands the operator's work in a stash
    they now have to unpick by hand. Nothing under .tropo-studio/ is a
    derivation input, so holding it back costs the reconcile nothing and the
    three commands run clean end to end.

    The dirty/clean question is answered from the seal the rebuilder itself
    stamped, NOT from `git status`. On a studio whose stat cache is cold, a
    status runs the clean filter over every governed file — measured at 2m47s
    against 4,292 of them — and a liveness probe with a thirty-second budget
    cannot ask a question that expensive. `derived_from_uncommitted` is the
    exact predicate the rebuilder gates recovery on, and it is one JSON read.
    """
    meta = studio / ".tropo-studio" / "locks" / "index-surfaces.meta.json"
    uncommitted = False
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        inventory = data.get("source_inventory")
        uncommitted = bool(data.get("derived_from_uncommitted")) or bool(
            isinstance(inventory, dict)
            and inventory.get("uncommitted_inputs")
        )
    except (OSError, json.JSONDecodeError, AttributeError):
        uncommitted = False
    if not uncommitted:
        return METADATA_RECOVERY_CURE
    return (
        "git stash push -u -m tropo-smoke-isolate -- . ':(exclude).tropo-studio'"
        " && " + METADATA_RECOVERY_CURE
        + " ; git stash pop"
    )


def _cure_chain(commands: list[str], fallback: str, max_chained: int = 2) -> str:
    unique: list[str] = []
    for command in commands:
        if command and command not in unique:
            unique.append(command)
    if not unique:
        return fallback
    if len(unique) > max_chained:
        return fallback
    return " && ".join(unique)


# ── AC2: byte-exact rollback of derived runtime state ────────────────────────


class _DerivedStateGuard:
    """Snapshot, then restore byte-for-byte, the derived state a probe writes.

    A probe drives the real gesture against the real studio (AC1/R2), and the
    real gesture legitimately advances derived surfaces: the index pair, the
    surface seal, the SQLite union, the dirty counter, the rebuild receipt, the
    recycle bin, the event stream. None of that is a governed change a liveness
    probe is entitled to leave behind, and a studio that grows a new index row
    and a new recycle tombstone every time somebody checks whether it is alive
    is a studio nobody checks twice. So each probe wraps its writes in one of
    these and restores in `finally` — on success and on failure alike (AC2).

    Not a lock. If another process is writing the index at the same moment,
    restoring would undo their work; the studio's own tools hold the index
    write lock for their own critical sections, and a smoke run is a
    single-operator gesture. Named here rather than hidden.
    """

    def __init__(self, studio: Path, files: Iterable[str] = (),
                 dirs: Iterable[str] = ()) -> None:
        self.studio = studio
        self._files = tuple(files)
        self._dirs = tuple(dirs)
        self._tmp: Optional[str] = None
        # relative path -> (existed, sha256 or None, copy path or None)
        self._file_state: dict[str, tuple[bool, Optional[str], Optional[Path]]] = {}
        self._dir_state: dict[str, tuple[bool, dict[str, tuple[str, Path]]]] = {}
        self.restored: list[str] = []
        self.restore_errors: list[str] = []

    def __enter__(self) -> "_DerivedStateGuard":
        self._tmp = tempfile.mkdtemp(prefix="tropo-smoke-guard-")
        staging = Path(self._tmp)
        for index, rel in enumerate(self._files):
            target = self.studio / rel
            if target.is_file():
                copy = staging / f"f{index}"
                shutil.copy2(target, copy)
                self._file_state[rel] = (True, _sha256_file(target), copy)
            else:
                self._file_state[rel] = (False, None, None)
        for index, rel in enumerate(self._dirs):
            target = self.studio / rel
            existed = target.is_dir()
            contents: dict[str, tuple[str, Path]] = {}
            if existed:
                bucket = staging / f"d{index}"
                bucket.mkdir(parents=True, exist_ok=True)
                for member in sorted(target.rglob("*")):
                    if not member.is_file():
                        continue
                    rel_member = member.relative_to(target).as_posix()
                    copy = bucket / rel_member.replace("/", "__")
                    shutil.copy2(member, copy)
                    contents[rel_member] = (_sha256_file(member), copy)
            self._dir_state[rel] = (existed, contents)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.restore()
        return False

    def restore(self) -> None:
        for rel, (existed, digest, copy) in self._file_state.items():
            target = self.studio / rel
            try:
                if existed and copy is not None:
                    if not target.is_file() or _sha256_file(target) != digest:
                        self._replace(copy, target)
                        self.restored.append(rel)
                elif target.is_file():
                    target.unlink()
                    self.restored.append(f"-{rel}")
            except OSError as exc:
                self.restore_errors.append(f"{rel}: {exc}")
        for rel, (existed, contents) in self._dir_state.items():
            target = self.studio / rel
            try:
                if target.is_dir():
                    for member in sorted(target.rglob("*"), reverse=True):
                        if member.is_file():
                            rel_member = member.relative_to(target).as_posix()
                            prior = contents.get(rel_member)
                            if prior is None:
                                member.unlink()
                                self.restored.append(f"-{rel}/{rel_member}")
                            elif _sha256_file(member) != prior[0]:
                                self._replace(prior[1], member)
                                self.restored.append(f"{rel}/{rel_member}")
                        elif member.is_dir() and not any(member.iterdir()):
                            member.rmdir()
                # Put back anything the gesture consumed. A tool that clears a
                # lock or rotates a shard away is deleting derived state that
                # WAS there before this probe ran, and leaving the hole behind
                # is residue in the other direction.
                for rel_member, (_digest, copy) in contents.items():
                    member = target / rel_member
                    if not member.is_file():
                        self._replace(copy, member)
                        self.restored.append(f"+{rel}/{rel_member}")
                if not existed and target.is_dir() and not any(target.iterdir()):
                    target.rmdir()
                    self.restored.append(f"-{rel}/")
            except OSError as exc:
                self.restore_errors.append(f"{rel}: {exc}")
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    @staticmethod
    def _replace(source: Path, target: Path) -> None:
        """Atomic put-back: never leave a half-written index surface behind."""
        target.parent.mkdir(parents=True, exist_ok=True)
        staged = target.with_name(target.name + ".tropo-smoke-restore")
        shutil.copy2(source, staged)
        os.replace(staged, target)


# ── probe 1: BOOT ────────────────────────────────────────────────────────────


def _dry_run_birth(studio: Path, agent: str) -> Optional[str]:
    """Actually perform this lineage's next birth, in a throwaway root.

    Returns None when a successor can be born, or the reason it cannot.

    Pure observation is preserved: the only bytes written live under a
    TemporaryDirectory that is removed before this returns. The studio's own
    lineage file is copied in, never opened for writing.
    """
    lineage = studio / "agents" / agent / "lineage.jsonl"
    if not lineage.is_file():
        return None  # not a lineage-managed agent; other checks cover it
    tool = studio / "vault" / "tools" / "tropo-lineage.py"
    if not tool.is_file():
        return None  # nothing to run; absence is not a birth failure
    try:
        with tempfile.TemporaryDirectory(prefix="smoke-birth-") as tmp:
            root = Path(tmp)
            target = root / "agents" / agent
            target.mkdir(parents=True)
            shutil.copy2(lineage, target / "lineage.jsonl")
            proc = subprocess.run(
                [sys.executable, str(tool), "--root", str(root),
                 "born", "--agent", agent, "--by", "tropo-smoke-probe"],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip().splitlines()
                return (
                    "a successor cannot be born — `tropo-lineage.py born` "
                    f"exited {proc.returncode}: "
                    + (detail[-1] if detail else "no output")
                )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"could not run the birth probe: {exc}"
    return None


def probe_boot(studio: Path) -> ProbeResult:
    """Can an agent still be born? — a dry-run SUCCESSOR birth (spec R3).

    Not the retiring agent's checklist. The checklist is the machine-guaranteed
    half; the successor's actual birth is the manual half nobody runs, and it
    is the one act no gate can watch because the agent is the thing that stops.

    Argus A142 completed his retirement properly and two things were still
    wrong the moment he stopped. His activation entry was still `status: active`
    in the surface the ADR-016 gate reads, which would have HALTED A143. And
    his auto-generated transfer stub was invisible to the index, so his
    successor's first act would have read through an unindexed pointer. Neither
    was caught by the retirement path.

    So this probe reads the substrate a successor actually reads — the index
    union, which is what the ADR-016 registry query resolves against — and
    checks it against the canonical governed files:

      B1  every entry the ADR-016 query would return as `active` really is
          active according to its own governed file. A row that says active
          over a file that says retired halts a successor on a predecessor
          that has already stopped.
      B2  for a lineage whose latest generation has gone terminal, no other
          entry is left `active` to trip the no-parallel-generation gate.
      B3  the predecessor's declared transfer pointer resolves in the index,
          so the successor's first act is not a read through a dangling UID.

    Nothing here is written. This is the one probe that is pure observation.

    AC7a lands here in two places, and neither of them is a subprocess:

      * A lineage whose governed file could not be READ is a lineage this
        probe did not check, so it is counted as unchecked and never turned
        into a blocker. The B4 key check is where that matters most — an
        unreadable tip looks exactly like an unkeyed tip if you squint, and
        break 1 is serious enough that manufacturing a false one would be a
        real cost.
      * The scan itself is bounded. Reading frontmatter for every activation
        entry in a 4,800-row index is I/O this probe can be starved of, and an
        instrument that quietly stops halfway through and reports the part it
        saw as the whole answer is green-when-blind. So the scan carries a
        deadline, and stopping early makes the verdict UNKNOWN — unless a
        blocker was already found, in which case it stays FAIL. Partial sight
        cannot un-see a defect, and burying a confirmed blocker under UNKNOWN
        because the clock ran out afterwards would be the amendment used to
        hide exactly the finding it was written to preserve.
    """
    started = time.monotonic()
    deadline = started + _timeout_for("boot")
    evidence: dict = {}
    current_path = studio / "vault" / "00-index.jsonl"
    archive_path = studio / "vault" / "00-archive-index.jsonl"

    if not current_path.is_file():
        # Determined, not blind: the surface the ADR-016 gate resolves against
        # is the operation. Its absence is an answer about the studio.
        return _failed(
            "boot",
            f"the current index surface is missing at {current_path} — a "
            "successor's ADR-016 check has nothing to resolve against",
            FULL_REBUILD_CURE, time.monotonic() - started,
            {"current_index_present": False},
        )

    current_rows, malformed = _read_jsonl(current_path)
    archive_rows: list[dict] = []
    if archive_path.is_file():
        archive_rows, archive_malformed = _read_jsonl(archive_path)
        malformed += archive_malformed

    indexed_uids = {
        str(row.get("uid")) for row in current_rows + archive_rows if row.get("uid")
    }
    activations = [
        row for row in current_rows + archive_rows
        if row.get("type") == "activation" and row.get("agent")
    ]
    lineages: dict[str, list[dict]] = {}
    for row in activations:
        lineages.setdefault(str(row["agent"]), []).append(row)

    blockers: list[str] = []
    cures: list[str] = []
    active_checked = 0
    transfers_checked = 0
    legacy_path_transfers = 0
    successors_derived = 0
    unreadable: list[str] = []
    lineages_checked: list[str] = []

    def source_of(row: dict) -> Path:
        uid = str(row.get("uid"))
        return studio / str(row.get("path") or f"vault/files/{uid}.md")

    # One read per activation entry, reused by every check below. The reason
    # travels with the scalars, because "not there" and "could not read it"
    # are a FAIL and an UNKNOWN respectively.
    front: dict[str, Optional[dict]] = {}
    reasons: dict[str, str] = {}
    for row in activations:
        uid = str(row.get("uid"))
        if uid not in front:
            front[uid], reasons[uid] = _frontmatter_or_reason(source_of(row))
        if time.monotonic() > deadline:
            break


    for agent in sorted(lineages):
        if time.monotonic() > deadline:
            break
        lineages_checked.append(agent)
        rows = lineages[agent]
        latest = max(
            rows,
            key=lambda row: (
                str(row.get("activated_at") or ""),
                str(row.get("generation") or ""),
                str(row.get("uid") or ""),
            ),
        )
        active_rows = [
            row for row in rows
            if str(row.get("status") or "").strip().lower() == "active"
        ]

        # B1 — does the surface the gate reads agree with canonical truth?
        for row in active_rows:
            active_checked += 1
            uid = str(row.get("uid"))
            source = source_of(row)
            frontmatter = front.get(uid)
            reason = reasons.get(uid, "not scanned")
            if frontmatter is None:
                if reason in ("missing", "no frontmatter block"):
                    blockers.append(
                        f"{agent}: activation {uid} is indexed `active` but its "
                        f"governed file at {source} is {reason} — the ADR-016 "
                        "gate would resolve against a row with no source"
                    )
                    cures.append(FULL_REBUILD_CURE)
                else:
                    # AC7a. The file is THERE and this instrument could not read
                    # it. "Would halt the successor" is a claim about substrate
                    # nobody looked at, and a fabricated blocker costs the same
                    # trust as a missed one.
                    active_checked -= 1
                    unreadable.append(f"{agent}/{uid} ({reason})")
                continue
            file_status = str(frontmatter.get("status") or "").strip().lower()
            if file_status in _TERMINAL_ACTIVATION_STATES:
                blockers.append(
                    f"{agent}: ADR-016 would HALT the successor — index row "
                    f"{uid} ({row.get('generation') or '?'}) says "
                    f"`status: active`, its governed file says "
                    f"`status: {file_status}`. The agent stopped; the surface "
                    "the gate reads did not"
                )
                cures.append(
                    f"python3 vault/tools/tropo-rebuild-index.py --only {uid}"
                )
            elif file_status == "active":
                # B1b — the retirement that stopped one field short. The fleet
                # boot-health check skips a non-terminal lineage, reasoning
                # that a live predecessor is ADR-016 working as designed. That
                # is right for an agent still running and wrong at a handoff:
                # an entry stamped `retired_at` and `closure_reason`, carrying
                # a transfer pointer, still declaring itself active, is not a
                # live predecessor — it is a finished one whose last field
                # never flipped. Nobody is left to flip it, and the successor
                # is who pays.
                stamped = [
                    field for field in _RETIREMENT_EVIDENCE_FIELDS
                    if str(frontmatter.get(field) or "").strip()
                ]
                if stamped:
                    blockers.append(
                        f"{agent}: ADR-016 would HALT the successor — "
                        f"activation {uid} ({row.get('generation') or '?'}) "
                        f"still says `status: active` while carrying "
                        f"{', '.join(stamped)}"
                        + (
                            f" and transfer_uid "
                            f"{str(frontmatter.get('transfer_uid') or '').strip()}"
                            if str(frontmatter.get("transfer_uid") or "").strip()
                            else ""
                        )
                        + ". The retirement finished everywhere except the one "
                        "field the gate reads"
                    )
                    cures.append(
                        f"python3 {ACTIVATION_TOOL_REL} close "
                        f"--activation-uid {uid} --target-status retired"
                    )

        # B2 — a terminal lineage with a stray active entry blocks the birth.
        latest_status = str(latest.get("status") or "").strip().lower()
        if latest_status in _TERMINAL_ACTIVATION_STATES:
            strays = [
                str(row.get("uid")) for row in active_rows
                if str(row.get("uid")) != str(latest.get("uid"))
            ]
            if strays:
                blockers.append(
                    f"{agent}: latest generation "
                    f"{latest.get('generation') or '?'} is {latest_status}, but "
                    f"{len(strays)} other entry(ies) are still `active` "
                    f"({', '.join(strays[:4])}) — the successor's open would "
                    "HALT as a parallel-generation violation"
                )
                cures.append(
                    "python3 vault/tools/tropo-rebuild-index.py --only "
                    + strays[0]
                )

        # B3/B4 both read the TIP's own governed file. A tip this instrument
        # could not read makes both of them unanswerable, and B4 in particular
        # would manufacture break 1 out of thin air: an unreadable tip presents
        # as `agent_public_key: ''`, which is indistinguishable from an unkeyed
        # one. So the lineage is recorded as unchecked and skipped (AC7a).
        latest_uid = str(latest.get("uid"))
        latest_fm = front.get(latest_uid)
        if latest_fm is None:
            lineages_checked.pop()
            unreadable.append(
                f"{agent}/{latest_uid} tip "
                f"({reasons.get(latest_uid, 'not scanned')})"
            )
            continue

        transfer = str(latest_fm.get("transfer_uid") or "").strip()
        if transfer:
            if _HEX8.match(transfer):
                transfers_checked += 1
                if transfer not in indexed_uids:
                    stub = studio / "vault" / "files" / f"{transfer}.md"
                    where = (
                        "it exists on disk but no index row resolves it"
                        if stub.is_file() else
                        "no file and no index row resolve it"
                    )
                    blockers.append(
                        f"{agent}: transfer pointer {transfer} declared by "
                        f"{latest.get('generation') or '?'} is invisible to the "
                        f"index — {where}. The successor's first act reads "
                        "through a dangling pointer"
                    )
                    cures.append(
                        "python3 vault/tools/tropo-rebuild-index.py --only "
                        + transfer
                        if stub.is_file() else FULL_REBUILD_CURE
                    )
            else:
                # Pre-UID convention: early generations wrote a PATH into
                # transfer_uid. Not an index pointer, so an index miss says
                # nothing about it. Counted, never failed on — flagging
                # legitimate history is exactly the false-positive class this
                # tool exists to stop producing.
                legacy_path_transfers += 1

        # B4 — RUN the birth, do not model it.
        #
        # This used to model the old mint's key ratchet: "this lineage has keys
        # and its tip does not, therefore a successor cannot derive." That was
        # true, and correct, right up until 2026-08-06, when birth moved to
        # `tropo-lineage.py born` — which imports nothing but the standard
        # library, touches no index, no mint and no key, and a test enforces
        # that. From that moment the check was measuring a requirement that no
        # longer sits on the birth path, and it said so loudly: it reported
        # metis and orpheus as unable to produce a successor while both could,
        # and its printed cure named a tool every boot contract now forbids.
        # Two false reds on the highest-severity line of the studio's own
        # liveness test, about the one operation that only ever happens when
        # nobody is watching (filed 7c31d9a4, talos-t39 2026-08-06).
        #
        # A model of the birth path goes stale the day the path moves. Running
        # it cannot. `born` takes --root, so the real command runs against a
        # throwaway copy of this lineage's file: nothing in the studio is
        # written, and there is nothing left to keep in step.
        birth = _dry_run_birth(studio, agent)
        if birth is not None:
            blockers.append(f"{agent}: {birth}")
            cures.append(
                "read the refusal above; birth is deliberately unrefusable, so "
                "a failure here is the world saying no (unreadable lineage "
                "file, or a disk that cannot be written)"
            )

        if _next_generation(str(latest.get("generation") or "")):
            successors_derived += 1
        elif latest_status in _TERMINAL_ACTIVATION_STATES:
            blockers.append(
                f"{agent}: cannot derive a successor generation from "
                f"{latest.get('generation')!r} — ADR-028's predecessor+1 chain "
                "has nothing to advance"
            )
            cures.append(f"python3 vault/tools/tropo-check-one.py {latest.get('uid')}")

    scan_complete = len(lineages_checked) + len(unreadable) >= len(lineages)
    evidence.update({
        "lineages_present": len(lineages),
        "lineages_checked": len(lineages_checked),
        "lineages_unchecked": len(lineages) - len(lineages_checked),
        "scan_complete": scan_complete,
        "activation_rows": len(activations),
        "active_rows_checked": active_checked,
        "transfer_pointers_checked": transfers_checked,
        "legacy_path_transfer_pointers": legacy_path_transfers,
        "successor_generations_derived": successors_derived,
        "indexed_uids": len(indexed_uids),
        "malformed_index_lines": malformed,
        "blockers": blockers,
        "unreadable_activations": unreadable,
    })

    elapsed = time.monotonic() - started
    if blockers:
        # A blocker found before the clock ran out is still a blocker. Partial
        # sight cannot un-see a defect, so this stays FAIL and the partiality
        # is recorded in the detail and in `scan_complete` rather than being
        # allowed to soften the verdict (AC7a, and see the docstring).
        detail = (
            f"{len(blockers)} blocker(s) a successor would hit right now: "
            + " | ".join(blockers[:4])
        )
        if len(blockers) > 4:
            detail += f" | … and {len(blockers) - 4} more"
        if not scan_complete or unreadable:
            detail += (
                f". NOTE: this scan was PARTIAL — "
                f"{len(lineages_checked)} of {len(lineages)} lineage(s) were "
                "checked, so there may be more; the blockers above were "
                "observed, not inferred"
            )
        detail += (
            f". If the incremental freshen refuses, the full repair is "
            f"`{FULL_REBUILD_CURE}`."
        )
        return _failed("boot", detail,
                       _cure_chain(cures, FULL_REBUILD_CURE), elapsed,
                       evidence)

    if not scan_complete or unreadable:
        # No blocker found AND the probe did not see all of the substrate. The
        # honest report is that the question is open, not that the birth is
        # clear — "clear across 21 lineages" over 9 lineages actually read is
        # green-when-blind, which is the same defect as break 8.
        checked = [
            f"{len(lineages_checked)} of {len(lineages)} lineage(s) fully read",
            f"{active_checked} indexed-`active` row(s) reconciled against "
            "their governed files",
            f"{transfers_checked} transfer pointer(s) resolved in the index",
        ]
        not_checked = [
            f"{len(lineages) - len(lineages_checked)} lineage(s) whose "
            "governed files were not read: "
            + (", ".join(unreadable[:4]) if unreadable
               else "the scan ran out of its share of the budget")
        ]
        detail = (
            f"the dry-run successor birth is UNKNOWN: no blocker was found in "
            f"the {len(lineages_checked)} lineage(s) this probe could read, "
            f"and {len(lineages) - len(lineages_checked)} lineage(s) were not "
            "read at all. Checked: " + "; ".join(checked)
            + ". NOT checked: " + "; ".join(not_checked)
            + ". This is a sight result reported as one, not a clean bill of "
            "health"
        )
        return _unknown(
            "boot", detail,
            "python3 vault/tools/tropo-smoke.py --only boot", elapsed,
            evidence, checked=checked, not_checked=not_checked,
        )

    return _passed(
        "boot",
        f"dry-run successor birth clear across {len(lineages)} lineage(s): "
        f"{active_checked} `active` row(s) agree with their governed files, no "
        f"parallel-generation stray blocks a terminal lineage, and "
        f"{transfers_checked} transfer pointer(s) resolve in the index",
        elapsed, evidence,
    )


# ── probe 2: MINT ────────────────────────────────────────────────────────────


def _recycle(studio: Path, uid: str) -> _Ran:
    return _run(
        [sys.executable, str(studio / RECYCLE_TOOL_REL), uid,
         "--reason", "tropo-smoke liveness probe throwaway (af6c53df AC2)"],
        studio, _cleanup_timeout(),
    )


def _smoke_authored(path: Path) -> bool:
    """Is this file this tool's own throwaway? Attribution is by the author
    slug the mint gesture stamped, so cleanup can never reach a concurrent
    agent's freshly minted file."""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return False
    return bool(
        re.search(
            r"^(?:captured_by|author|created_by|owner):[ \t]*['\"]?"
            + re.escape(SMOKE_AUTHOR) + r"['\"]?[ \t]*$",
            head, re.M,
        )
    )


def probe_mint(studio: Path) -> ProbeResult:
    """Can a governed file be created AND indexed?

    Break 3 lived here: 059f2c68 compared raw worktree bytes to the committed
    blob, which is true only in a fresh checkout, and broke minting in every
    studio anyone had actually used. The pass condition is therefore not "the
    tool exited zero" but "the row is really there" — the write is not done
    until its row is.

    Cleanup is the canonical soft-delete gesture (tropo-recycle.py), never
    `rm`, and it runs in `finally` because the run most likely to leave a
    source-first orphan behind is the run that FAILED.

    AC7a: a mint that runs out of its share of the budget is UNKNOWN, not FAIL.
    The chokepoint may be perfectly healthy and merely slower than the clock,
    and "MINT: FAIL" over a studio that mints fine is the false positive this
    whole spec was written against. Cleanup still runs — the throwaway is
    attributed by author slug, so a gesture killed halfway through is still
    recycled if it managed to write anything.
    """
    started = time.monotonic()
    files_dir = studio / "vault" / "files"
    mint_tool = studio / MINT_TOOL_REL
    evidence: dict = {"mint_type": SMOKE_MINT_TYPE, "author": SMOKE_AUTHOR}
    checked: list[str] = []

    if not mint_tool.is_file():
        return _failed(
            "mint",
            f"the mint chokepoint is missing at {mint_tool} — nothing in this "
            "studio can create a governed identifier",
            "git checkout -- vault/tools/tropo-mint-id.py",
            time.monotonic() - started, evidence,
        )
    checked.append(f"the mint chokepoint is present at {MINT_TOOL_REL}")

    before = {path.name for path in files_dir.glob("*.md")} if files_dir.is_dir() else set()
    minted_uid = ""
    result: Optional[ProbeResult] = None

    guard = _DerivedStateGuard(
        studio,
        files=_MINT_DERIVED_FILES,
        dirs=_INDEX_DERIVED_DIRS + (
            "vault/events/streams",
            f"recycle/agent-deletions/{time.strftime('%Y-%m-%d')}",
        ),
    )
    guard.__enter__()
    try:
        budget = _timeout_for("mint")
        evidence["timeout_s"] = round(budget, 1)
        ran = _run(
            [sys.executable, str(mint_tool), "--type", SMOKE_MINT_TYPE,
             "--author", SMOKE_AUTHOR],
            studio, budget,
        )
        evidence["mint_exit_code"] = ran.rc
        evidence["mint_timed_out"] = ran.timed_out
        checked.append("the mint gesture was launched")
        stdout_uid = ""
        for line in reversed((ran.out or "").splitlines()):
            token = line.strip()
            if _HEX8.match(token):
                stdout_uid = token
                break
        minted_uid = stdout_uid
        evidence["minted_uid"] = minted_uid or None

        if ran.timed_out:
            not_checked = [
                "whether an 8-hex identifier came back",
                "whether a governed file was written for it",
                "whether the current index resolves that file",
            ]
            result = _unknown(
                "mint",
                f"the mint gesture did not finish within {ran.elapsed_s:.1f}s "
                f"of its {budget:.1f}s share of the {active_budget():.0f}s "
                f"budget, so whether this studio can mint is UNKNOWN. "
                f"Checked: {'; '.join(checked)}. NOT checked: "
                f"{'; '.join(not_checked)}. This is a budget result reported "
                f"as one, not a broken mint ({ran.diagnostic})",
                f"python3 vault/tools/tropo-mint-id.py --type "
                f"{SMOKE_MINT_TYPE} --author you",
                0.0, evidence, checked=checked, not_checked=not_checked,
            )
        elif ran.rc != 0:
            diagnostic = ran.diagnostic
            result = _failed(
                "mint",
                f"mint exited {ran.rc}: {diagnostic}",
                _rebuild_cure(studio, diagnostic), 0.0, evidence,
            )
        elif not minted_uid:
            # Determined, not blind. The chokepoint's contract is that it
            # prints the identifier it minted; exiting 0 without one means the
            # operation did not deliver its product, which is an answer about
            # the studio rather than a gap in this instrument's sight.
            result = _failed(
                "mint",
                "mint exited 0 but printed no 8-hex identifier — the gesture "
                "delivered no usable product, so nothing downstream of it can "
                f"proceed. stdout: {_tail(ran.out, 200)!r}",
                f"python3 vault/tools/tropo-mint-id.py --type "
                f"{SMOKE_MINT_TYPE} --author you",
                0.0, evidence,
            )
        else:
            source = files_dir / f"{minted_uid}.md"
            evidence["minted_path"] = str(source.relative_to(studio))
            index_path = studio / "vault" / "00-index.jsonl"
            row: Optional[dict] = None
            if index_path.is_file():
                rows, _malformed = _read_jsonl(index_path)
                matches = [r for r in rows if r.get("uid") == minted_uid]
                evidence["index_rows_for_uid"] = len(matches)
                row = matches[0] if len(matches) == 1 else None
            if not source.is_file():
                result = _failed(
                    "mint",
                    f"mint exited 0 but wrote no file at {source}",
                    FULL_REBUILD_CURE, 0.0, evidence,
                )
            elif row is None:
                result = _failed(
                    "mint",
                    f"mint exited 0 and wrote {source.name}, but the current "
                    "index carries no single row for it — the file exists and "
                    "is invisible. The write is not done until its row is",
                    f"python3 vault/tools/tropo-rebuild-index.py --only "
                    f"{minted_uid}",
                    0.0, evidence,
                )
            else:
                evidence["indexed_path"] = row.get("path")
                evidence["indexed_type"] = row.get("type")
                expected = source.relative_to(studio).as_posix()
                if row.get("path") != expected or row.get("type") != SMOKE_MINT_TYPE:
                    result = _failed(
                        "mint",
                        f"the index row for {minted_uid} does not match what "
                        f"was written: row says path={row.get('path')!r} "
                        f"type={row.get('type')!r}, disk says path={expected!r} "
                        f"type={SMOKE_MINT_TYPE!r}",
                        f"python3 vault/tools/tropo-rebuild-index.py --only "
                        f"{minted_uid}",
                        0.0, evidence,
                    )
                else:
                    result = _passed(
                        "mint",
                        f"minted {minted_uid} as a governed {SMOKE_MINT_TYPE} "
                        f"at {expected} and the current index resolves it "
                        "(exactly one row, matching path and type)",
                        0.0, evidence,
                    )
    finally:
        # AC2. Soft-delete every file this probe is responsible for, whether
        # the probe passed, failed, or left a source-first orphan behind.
        residue: list[str] = []
        now = {path.name for path in files_dir.glob("*.md")} if files_dir.is_dir() else set()
        candidates = []
        for name in sorted(now - before):
            if _smoke_authored(files_dir / name):
                candidates.append(name[:-3])
        if minted_uid and minted_uid not in candidates and (files_dir / f"{minted_uid}.md").is_file():
            candidates.append(minted_uid)
        recycled: list[str] = []
        tombstones: list[str] = []
        for uid in candidates:
            recycle_ran = _recycle(studio, uid)
            if (files_dir / f"{uid}.md").is_file():
                residue.append(
                    f"{uid} could not be soft-deleted "
                    f"({recycle_ran.diagnostic or 'unknown'})"
                )
            else:
                recycled.append(uid)
                # Where the sanctioned gesture put it, recorded before the
                # guard rolls the bin back. The tombstone itself does not
                # survive this probe (see the note below), so this is the only
                # place the removal path stays visible — without it, a reader
                # cannot tell a recycle from an rm, and telling those apart is
                # the whole point of the rule.
                for bin_name in ("recycle", "99-recycle"):
                    bin_dir = studio / bin_name
                    if not bin_dir.is_dir():
                        continue
                    for grave in bin_dir.rglob(f"{uid}.md"):
                        tombstones.append(
                            grave.relative_to(studio).as_posix()
                        )
        evidence["recycled"] = recycled
        evidence["recycle_tombstones"] = tombstones
        # The tombstone and its log line are this probe's own residue, not
        # governed work: the throwaway was born and removed inside one liveness
        # check. recycle/ is TRACKED here (1,556 files, no .gitignore entry,
        # and recycle.log even carries a merge=union attribute), so a bin left
        # to grow would put two new tracked files into `git status` on every
        # single run and hand the operator a commit obligation for checking
        # whether the studio was alive. So the bin goes back to the bytes it
        # had — while the removal gesture above stays the sanctioned one, and
        # `recycle_tombstones` above keeps the receipt. Nothing under
        # vault/files/ is ever `rm`ed.
        guard.restore()
        evidence["derived_state_restored"] = len(guard.restored)
        if guard.restore_errors:
            evidence["restore_errors"] = guard.restore_errors
            residue.extend(guard.restore_errors)
        if residue:
            # Residue is a DETERMINED finding and it outranks an UNKNOWN
            # verdict on the gesture itself: AC2 says a failed probe leaves no
            # residue, and this probe just observed that it did. So the status
            # is FAIL even when the mint outcome was unknown — and the detail
            # keeps the two apart, so the report never claims minting is broken
            # when what is broken is the cleanup after a timeout.
            evidence["residue"] = residue
            result = _failed(
                "mint",
                ((result.detail + " — but ") if result else "")
                + "this probe could not clean up after itself: "
                + "; ".join(residue),
                "python3 vault/tools/tropo-recycle.py "
                + (candidates[0] if candidates else "<uid>")
                + " --reason 'tropo-smoke residue'",
                0.0, evidence,
            )

    elapsed = time.monotonic() - started
    assert result is not None
    return ProbeResult(result.operation, result.status, result.detail,
                       result.cure, elapsed, result.evidence)


# ── probe 3: INDEX ───────────────────────────────────────────────────────────


def _pick_index_target(studio: Path, rows: list[dict]) -> Optional[str]:
    """A real, existing entry to freshen — never a fabricated one (R2).

    Deterministic (lowest UID whose governed file is really on disk) so two
    runs exercise the same row and the AC2 double-run diff means something.
    """
    for row in sorted(rows, key=lambda r: str(r.get("uid") or "")):
        uid = str(row.get("uid") or "")
        if not _HEX8.match(uid):
            continue
        source = studio / str(row.get("path") or f"vault/files/{uid}.md")
        if source.is_file():
            return uid
    return None


def _legacy_digest_door_reading(studio: Path) -> dict:
    """Does THIS machine still need the superseded-format digest door?

    Taken BEFORE the probe's own rebuild runs, and that ordering is the whole
    correctness of it: `--only` re-stamps the seal in the current format, so a
    reading taken afterwards would report every machine healed by the act of
    measuring it — and the derived-state guard then puts the old seal back, so
    the machine would still need the door and nobody would know.

    Never a verdict. A machine running on the bootstrap is not broken, it is
    carrying a stale seal that its next full rebuild fixes; failing it here
    would be one more gate refusing legitimate work, which is the disease this
    tool was built against. It becomes a failure on its own once the door
    closes, through the ordinary refusal path, with the cure attached.
    """
    tool = studio / LEGACY_DIGEST_DOOR_TOOL_REL
    if not tool.is_file():
        return {
            "available": False,
            "error": f"{LEGACY_DIGEST_DOOR_TOOL_REL} is not on this studio",
        }
    ran = _run(
        [sys.executable, str(tool), "--json"],
        studio, _step_timeout("index", 5.0 / 20.0),
    )
    # Exit 1 is that tool's VERDICT (this machine needs the door, or cannot
    # answer), not a run failure, so the payload is read either way.
    try:
        payload = json.loads(ran.out or "")
    except (json.JSONDecodeError, ValueError):
        payload = None
    if not isinstance(payload, dict):
        return {
            "available": False,
            "error": f"no reading came back (rc={ran.rc}): {ran.diagnostic}",
        }
    payload["available"] = True
    return payload


def probe_index(studio: Path) -> ProbeResult:
    """Can an existing entry be freshened?

    R1 is the whole shape of this probe. Break 8 was a rebuild that succeeded
    while checking nothing: a stale per-machine digest under the gitignored
    .tropo-studio/locks/ made three validator gates report `0 rows checked` and
    PASS. A gate that fails is a bug; a gate that passes while examining
    nothing is a bug nobody files.

    So exit code zero is necessary and not sufficient. The pass condition also
    requires the operation to show what it saw: the rebuild writes a receipt
    for its own run, and `rows_checked` is read from THAT run's receipt — not
    from a count this probe takes for itself, which would prove only that the
    file on disk has lines in it. A run that exits 0 and leaves no fresh
    receipt reports rows_checked = 0 and fails, because absence of evidence is
    exactly what break 8 looked like from the outside.

    AC7a NAMES THIS PROBE. T37's first build got the third outcome right for
    BUILD and wrong here: `--only` that did not finish printed FAIL on a 2.0s
    timeout, over a studio whose only defect was that a 20-40s rebuild had been
    handed two seconds. The rebuild not finishing says nothing whatever about
    whether the index can be freshened, and saying FAIL about it is the same
    defect as break 8 wearing the opposite sign. It is UNKNOWN now, and it
    carries the partial work.

    Note the one place that stays FAIL and is worth reading twice: exit 0 with
    `rows_checked == 0` is NOT an unknown. There the operation FINISHED and
    claimed success while showing no evidence of having examined anything —
    that is a determined observation about the studio's own gate, and R1 exists
    to fail exactly it. The distinction is who ran out of sight: this
    instrument (UNKNOWN) or the operation it was watching (FAIL).
    """
    started = time.monotonic()
    evidence: dict = {}
    checked: list[str] = []
    rebuild_tool = studio / REBUILD_TOOL_REL
    current_path = studio / "vault" / "00-index.jsonl"
    receipt_path = studio / INDEX_RUN_RECEIPT_REL

    door = _legacy_digest_door_reading(studio)
    # The scalar pair is what reaches the human report line; the full reading
    # is carried for whoever is collecting readings across machines.
    evidence["legacy_digest_door"] = (
        door.get("verdict") if door.get("available") else "unavailable"
    )
    evidence["legacy_digest_door_needed"] = (
        door.get("needs_door") if door.get("available") else None
    )
    evidence["legacy_digest_door_report"] = door

    if door.get("available"):
        checked.append(
            f"the legacy-digest-door reading for this machine "
            f"({door.get('verdict')})"
        )

    if not rebuild_tool.is_file():
        return _failed(
            "index",
            f"the index rebuilder is missing at {rebuild_tool}",
            "git checkout -- vault/tools/tropo-rebuild-index.py",
            time.monotonic() - started, evidence,
        )
    checked.append(f"the index rebuilder is present at {REBUILD_TOOL_REL}")
    if not current_path.is_file():
        return _failed(
            "index",
            f"there is no current index surface at {current_path} to freshen "
            "an entry into",
            FULL_REBUILD_CURE, time.monotonic() - started, evidence,
        )
    checked.append("the current index surface is present and readable")

    current_rows, malformed = _read_jsonl(current_path)
    evidence["malformed_index_lines"] = malformed
    target = _pick_index_target(studio, current_rows)
    if target is None:
        return _failed(
            "index",
            "no index row resolves to a governed file on disk — there is no "
            "real entry to freshen (this probe refuses to invent one)",
            FULL_REBUILD_CURE, time.monotonic() - started, evidence,
        )
    evidence["target_uid"] = target
    checked.append(
        f"a real existing entry ({target}) was selected to freshen"
    )

    receipt_before = receipt_path.read_bytes() if receipt_path.is_file() else b""
    probe_clock = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result: Optional[ProbeResult] = None

    guard = _DerivedStateGuard(studio, files=_INDEX_DERIVED_FILES,
                               dirs=_INDEX_DERIVED_DIRS)
    guard.__enter__()
    try:
        budget = _timeout_for("index")
        evidence["timeout_s"] = round(budget, 1)
        ran = _run(
            [sys.executable, str(rebuild_tool), "--only", target],
            studio, budget,
        )
        evidence["freshen_exit_code"] = ran.rc
        evidence["freshen_timed_out"] = ran.timed_out
        checked.append(f"`--only {target}` was launched against this studio")

        rows_checked = 0
        receipt_fresh = False
        receipt: dict = {}
        if receipt_path.is_file():
            receipt_after = receipt_path.read_bytes()
            try:
                receipt = json.loads(receipt_after.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                receipt = {}
            wrote_new_bytes = receipt_after != receipt_before
            stamped_now = str(receipt.get("run_started_at") or "") >= probe_clock
            receipt_fresh = (
                isinstance(receipt, dict)
                and receipt.get("mode") == "incremental-only"
                and (wrote_new_bytes or stamped_now)
            )
            if receipt_fresh:
                rows_checked = int(receipt.get("assembled_record_count") or 0)
        evidence.update({
            "rows_checked": rows_checked,
            "receipt_fresh": receipt_fresh,
            "receipt_path": INDEX_RUN_RECEIPT_REL,
            "receipt_mode": receipt.get("mode"),
            "current_record_count": receipt.get("current_record_count"),
            "archive_record_count": receipt.get("archive_record_count"),
            "index_rows_present": len(current_rows),
        })

        still_indexed = False
        if current_path.is_file():
            after_rows, _ = _read_jsonl(current_path)
            still_indexed = any(row.get("uid") == target for row in after_rows)
        evidence["target_still_indexed"] = still_indexed

        if ran.timed_out:
            # AC7a, and the regression the amendment names by hand. The
            # freshen was killed by this instrument's clock, so nothing was
            # learned about whether the studio can freshen an entry. FAIL here
            # was the defect: it reported a broken index over a studio whose
            # index was fine and whose rebuild is simply a 20-40s operation.
            not_checked = [
                "whether `--only` exits 0",
                "rows_checked — R1's evidence that the operation SAW something",
                f"whether {target} is still resolvable in the current index "
                "(the freshen was killed mid-write, so the surface on disk "
                "answers for a half-finished run, not for the studio)",
            ]
            result = _unknown(
                "index",
                f"`--only {target}` did not finish within {ran.elapsed_s:.1f}s "
                f"of its {budget:.1f}s share of the {active_budget():.0f}s "
                "budget, so whether this studio can freshen an entry is "
                f"UNKNOWN. Checked: {'; '.join(checked)}. NOT checked: "
                f"{'; '.join(not_checked)}. A real rebuild on a large studio "
                "costs 20-40s; if that is what happened, re-run without "
                "`--fast` before treating this as a defect",
                f"python3 {REBUILD_TOOL_REL} --only {target}"
                "  # no clock on it — time the real cost first",
                0.0, evidence, checked=checked, not_checked=not_checked,
            )
        elif ran.rc != 0:
            result = _failed(
                "index",
                f"`--only {target}` exited {ran.rc}: {ran.diagnostic}",
                _rebuild_cure(studio, ran.diagnostic), 0.0, evidence,
            )
        elif rows_checked <= 0:
            # R1. Break 8 reproduced, and the only way to catch it is to
            # refuse to call an evidence-free zero exit a pass. The two shapes
            # are named apart because they have different cures: a receipt
            # that never landed is usually a write that failed under the
            # gitignored .tropo-studio/, and a receipt that landed claiming
            # zero rows is a real derivation that examined nothing.
            writable = os.access(receipt_path.parent, os.W_OK) and (
                not receipt_path.exists() or os.access(receipt_path, os.W_OK)
            )
            evidence["receipt_writable"] = writable
            if receipt_fresh:
                shape = (
                    f"it wrote a fresh {receipt.get('mode')!r} receipt at "
                    f"{INDEX_RUN_RECEIPT_REL} claiming it assembled 0 records"
                )
                cure = FULL_REBUILD_CURE
            elif not writable:
                shape = (
                    f"no fresh receipt landed at {INDEX_RUN_RECEIPT_REL} and "
                    "that path is NOT WRITABLE, so the operation's own record "
                    "of what it examined failed to write while the operation "
                    "still reported success"
                )
                cure = (
                    "chmod -R u+w .tropo-studio/shards && "
                    + FULL_REBUILD_CURE
                )
            else:
                shape = (
                    f"no fresh receipt landed at {INDEX_RUN_RECEIPT_REL} "
                    f"(last mode on disk: {receipt.get('mode')!r}), so nothing "
                    "records what the operation examined"
                )
                cure = FULL_REBUILD_CURE
            # Determined, and deliberately NOT an unknown. The operation
            # finished and reported success; what it did not do is show any
            # evidence of having examined anything. R1 exists to fail that.
            result = _failed(
                "index",
                f"`--only {target}` exited 0 but rows_checked is 0 — {shape}. "
                "A rebuild that succeeds while checking nothing is break 8, "
                "and it passes every gate that reads only the exit code",
                cure, 0.0, evidence,
            )
        elif not still_indexed:
            result = _failed(
                "index",
                f"`--only {target}` exited 0 and checked {rows_checked} row(s), "
                "but the entry is no longer resolvable in the current index",
                FULL_REBUILD_CURE, 0.0, evidence,
            )
        else:
            detail = (
                f"freshened real entry {target} through `--only`, and the run "
                f"reported {rows_checked} row(s) checked "
                f"({receipt.get('current_record_count')} current + "
                f"{receipt.get('archive_record_count')} archive) in its own "
                "receipt"
            )
            if door.get("needs_door") is True:
                detail += (
                    "; and this machine's index seal is still in the "
                    f"superseded {door.get('legacy_tag')} format, carried by "
                    "the bootstrap door that closes "
                    f"{door.get('sunset')} ({door.get('days_until_sunset')} "
                    f"day(s) left) — `{door.get('cure')}` re-stamps it forward"
                )
            elif not door.get("available"):
                detail += (
                    "; the legacy-digest-door reading could not be taken "
                    f"({door.get('error')}), so whether this machine still "
                    "needs the door is unknown"
                )
            result = _passed("index", detail, 0.0, evidence)
    finally:
        guard.restore()
        evidence["derived_state_restored"] = len(guard.restored)
        if guard.restore_errors:
            evidence["restore_errors"] = guard.restore_errors

    elapsed = time.monotonic() - started
    assert result is not None
    return ProbeResult(result.operation, result.status, result.detail,
                       result.cure, elapsed, result.evidence)


# ── probe 4: COMMIT ──────────────────────────────────────────────────────────


def _find_used_studio_body(studio: Path) -> tuple[Optional[Path], bool]:
    """A REAL governed body to push through the clean filter (R2 / AC6).

    A fresh `git checkout` has no rendered nav region at ALL — the filter is
    clean-side with no smudge, so the derived region is stripped on the way in
    and never rebuilt on the way out. That absence is precisely why 059f2c68
    passed every test built from a fresh checkout and broke every studio
    anyone had actually used. So this looks for a body carrying a rendered
    region, and never manufactures one.

    Preference order, and the order is the argument:
      1. a live vault/files/*.md REGULAR file carrying a rendered region —
         the used-studio shape, on the exact path the filter is declared over.
      2. a recycled governed entry carrying one. These are former vault/files
         entries preserved with their rendered regions intact: a used studio's
         real bytes, not a fixture somebody wrote to be found in order.
      3. a live vault/files/*.md SYMLINK carrying one. Demoted deliberately —
         git stages a symlink's TARGET STRING, so those bytes never cross the
         clean-filter boundary in real life, and a sample that never makes the
         crossing is a weak witness for a probe about the crossing.
      4. any live governed entry. Honest degradation: the round trip is still
         exercised end to end, and the report says the strip leg was not.
    """
    files_dir = studio / "vault" / "files"

    def carries_region(path: Path) -> bool:
        try:
            return _NAV_REGION_RE.search(path.read_bytes()) is not None
        except OSError:
            return False

    symlinked: Optional[Path] = None
    if files_dir.is_dir():
        for path in sorted(files_dir.glob("*.md")):
            if not _HEX8.match(path.stem) or not carries_region(path):
                continue
            if path.is_symlink():
                symlinked = symlinked or path
            else:
                return path, True
    for bin_name in ("99-recycle", "recycle"):
        bin_dir = studio / bin_name
        if not bin_dir.is_dir():
            continue
        for path in sorted(bin_dir.rglob("*.md")):
            if carries_region(path):
                return path, True
    if symlinked is not None:
        return symlinked, True
    if files_dir.is_dir():
        for path in sorted(files_dir.glob("*.md")):
            if _HEX8.match(path.stem):
                return path, False
    return None, False


def probe_commit(studio: Path) -> ProbeResult:
    """Does a governed file survive the clean-filter round trip?

    This is break 3's root cause. A fresh git worktree checks out through the
    clean filter with NO smudge, so vault/files/*.md arrive with their derived
    nav region stripped, while a studio anyone has actually used has it
    rendered. 059f2c68 compared raw worktree bytes to the committed blob,
    passed every test built from a fresh checkout, and broke every studio that
    had ever been used.

    So the law this probe asserts is filtered-vs-filtered, never
    raw-vs-committed:

      C1  BOTH halves of the filter are wired. `.gitattributes` is tracked and
          travels with every clone; the clean command itself lives in the
          local .git/config, which is never committed. A studio with only the
          first half stages derived content into the object store and does not
          know it.
      C2  staging does not touch the working tree. The filter runs at the git
          boundary; the rendered region stays on disk for humans and agents.
      C3  the staged blob is the FILTERED form: no sentinel survives, and
          every byte outside the sentinels does.
      C4  the filter is a fixed point — re-staging its own output is a no-op.

    The scratch path is a real governed body copied to a throwaway name under
    vault/files/ (the only path the filter is declared over) and unstaged and
    removed in `finally`. Staging runs against a throwaway GIT_INDEX_FILE:
    real git, real filter, real object store, but the operator's own staging
    area is never touched (R2 — isolation derived from the real repository,
    not from a fabricated one).

    AC7a lands on every git invocation here. This probe makes ten of them, and
    a `git` that does not answer inside its ceiling used to become a sentence
    about the studio: a `rev-parse` timeout printed "this studio is not a git
    work tree", and — worse, because it is silent — a `hash-object` timeout
    made C4 print "the clean filter is not a fixed point". Both are the
    instrument's blindness dressed up as a finding. Every one of them is an
    UNKNOWN now, and each says which check it got to before the clock did.
    """
    started = time.monotonic()
    evidence: dict = {}
    checked: list[str] = []
    scratch_rel = f"vault/files/.tropo-smoke-probe-{os.getpid()}.md"
    scratch = studio / scratch_rel
    unknown_cure = "python3 vault/tools/tropo-smoke.py --only commit"

    def _timed_out(step: str, ran_or_rc, *, not_checked: list[str]) -> ProbeResult:
        """One shape for 'git did not answer', so no step can invent its own."""
        return _unknown(
            "commit",
            f"the clean-filter round trip could not be exercised: {step} did "
            f"not answer within its share of the {active_budget():.0f}s "
            f"budget, so whether a governed file survives the boundary is "
            f"UNKNOWN. Checked: "
            f"{'; '.join(checked) if checked else 'nothing yet'}. NOT "
            f"checked: {'; '.join(not_checked)}",
            unknown_cure, time.monotonic() - started, evidence,
            checked=checked, not_checked=not_checked,
        )

    inside = _git(studio, "rev-parse", "--is-inside-work-tree",
                  timeout=_step_timeout("commit"))
    if inside.timed_out:
        return _timed_out(
            "`git rev-parse`",
            inside,
            not_checked=["everything — git itself did not answer"],
        )
    if inside.rc != 0:
        return _failed(
            "commit",
            f"this studio is not a git work tree ({inside.diagnostic}) — a "
            "governed file has no clean-filter boundary to survive",
            "git init  # or run the smoke test inside the studio's repo",
            time.monotonic() - started, evidence,
        )
    checked.append("this studio is a git work tree")

    # C1a — which filter does .gitattributes declare over governed files?
    attr = _git(studio, "check-attr", "filter", "--",
                "vault/files/00000000.md", timeout=_step_timeout("commit"))
    if attr.timed_out:
        return _timed_out(
            "`git check-attr`", attr,
            not_checked=[
                "which filter .gitattributes declares over vault/files/*.md",
                "whether this clone's .git/config wires the clean half",
                "whether a governed body survives the round trip",
            ],
        )
    filter_name = ""
    match = re.search(r"filter:\s*(\S+)\s*$", (attr.out or "").strip())
    if match and match.group(1) not in ("unspecified", "unset"):
        filter_name = match.group(1)
    evidence["gitattributes_filter"] = filter_name or None
    if not filter_name:
        return _failed(
            "commit",
            "`.gitattributes` declares no clean filter over vault/files/*.md — "
            "the I5 derived-never-syncs strip is not declared in this studio "
            "at all, so index-derived content commits straight into the object "
            "store",
            NAVBLOCK_VERIFY_CURE,
            time.monotonic() - started, evidence,
        )
    checked.append(f".gitattributes declares filter={filter_name}")

    # C1b — the second, per-clone half nobody remembers.
    #
    # The wired driver is `process` (git's long-running filter), not `clean`.
    # `clean` is a spawn-per-file shell-out: ~53ms of interpreter startup per
    # file, ~3.1 min per `git add`/`status` after a full rebuild dirties ~3,561
    # files, against 6.4s with the filter stubbed to `cat`. 6ec30708 line 113
    # specified `process` and the build shipped `clean`; corrected 2026-08-07.
    config = _git(studio, "config", "--get", f"filter.{filter_name}.process",
                  timeout=_step_timeout("commit"))
    if config.timed_out:
        return _timed_out(
            "`git config --get`", config,
            not_checked=[
                "whether this clone's .git/config wires the filter half",
                "whether a governed body survives the round trip",
            ],
        )
    wired = config.rc == 0 and bool((config.out or "").strip())
    evidence["git_config_process_wired"] = wired
    evidence["git_config_process"] = (config.out or "").strip() or None

    stale = _git(studio, "config", "--get", f"filter.{filter_name}.clean",
                 timeout=_step_timeout("commit"))
    stale_clean = stale.rc == 0 and bool((stale.out or "").strip())
    evidence["git_config_stale_clean_wired"] = stale_clean

    if not wired:
        return _failed(
            "commit",
            f"`.gitattributes` declares filter={filter_name} over "
            "vault/files/*.md but this clone's LOCAL .git/config has no "
            f"filter.{filter_name}.process command. .git/config is never "
            "committed, so every fresh clone starts with exactly one half of "
            "the filter installed and stages derived nav content into the "
            "object store without saying so",
            NAVBLOCK_INSTALL_CURE,
            time.monotonic() - started, evidence,
        )
    if stale_clean:
        return _failed(
            "commit",
            f"this clone still wires the superseded filter.{filter_name}.clean "
            "(spawn-per-file: ~53ms of interpreter startup per file, ~3.1 min "
            "per git add/status after a full rebuild). git prefers `process` "
            "when both are set, so the slow wiring changes nothing you can "
            "observe and will sit here looking correct until someone reads it",
            NAVBLOCK_INSTALL_CURE,
            time.monotonic() - started, evidence,
        )
    checked.append("both halves of the filter are wired in this clone")

    sample, has_nav = _find_used_studio_body(studio)
    if sample is None:
        return _failed(
            "commit",
            "no governed file was found to round-trip — vault/files/ has no "
            "entry this probe can read",
            FULL_REBUILD_CURE, time.monotonic() - started, evidence,
        )
    raw = sample.read_bytes()
    checked.append(
        f"a real governed body was selected ({sample.name}, "
        + ("carrying a rendered nav region" if has_nav
           else "no rendered nav region in this studio") + ")"
    )
    evidence.update({
        "sample_source": str(sample.relative_to(studio)),
        "sample_is_symlink": sample.is_symlink(),
        "nav_region_present": has_nav,
        "sample_bytes": len(raw),
        "scratch_path": scratch_rel,
    })

    # The staging happens against a THROWAWAY git index, not .git/index.
    # Real `git add` against the real repository, real filter, real object
    # write — but the operator's staging area is never read, refreshed, or
    # written, so a smoke run can never disturb work somebody has half-staged
    # and can never contend for .git/index.lock (AC2).
    result: Optional[ProbeResult] = None
    staged = False
    created_object = ""
    tmpdir = tempfile.mkdtemp(prefix="tropo-smoke-index-")
    index_env = {"GIT_INDEX_FILE": str(Path(tmpdir) / "index")}
    evidence["isolated_git_index"] = True
    try:
        scratch.write_bytes(raw)

        # Which object would this staging write? Computed WITHOUT -w, so
        # asking the question does not itself add anything to the store —
        # that is how cleanup later knows whether the loose object is ours.
        rc, hashed, _err = _git_bytes(
            studio, ["hash-object", "--stdin", "--path", scratch_rel],
            timeout=_step_timeout("commit", 15.0 / 20.0), stdin=raw,
        )
        expected_oid = hashed.decode("ascii", "replace").strip() if rc == 0 else ""
        # Cleanup may only remove a loose object this probe can PROVE it
        # created, and "proved" means git said the hash was absent beforehand.
        # A `cat-file -e` that ran out of time says nothing; reading its 124 as
        # "absent" hands cleanup a blob the studio already owned. That is
        # AC7a's defect — a timeout treated as an answer — arriving with an AC2
        # blast radius, because the answer it fakes is the one that authorises
        # a delete. Measured: it unlinks the sample file's own committed blob
        # and leaves `git fsck` reporting a missing object.
        existed = _git(
            studio, "cat-file", "-e", expected_oid,
            timeout=_step_timeout("commit"),
        ) if expected_oid else None
        object_absence_proven = (
            existed is not None and not existed.timed_out and existed.rc != 0
        )
        if existed is not None and existed.timed_out:
            evidence["probe_object_ownership_unknown"] = True

        added = _git(studio, "add", "--", scratch_rel,
                     timeout=_step_timeout("commit"), env=index_env)
        if added.timed_out:
            result = _timed_out(
                "`git add`", added,
                not_checked=[
                    "whether the staged blob is the filtered form",
                    "whether staging left the working tree alone",
                    "whether the filter is a fixed point",
                ],
            )
        elif added.rc != 0:
            result = _failed(
                "commit",
                f"`git add` refused the governed scratch path: "
                f"{added.diagnostic}",
                f"git add -- {scratch_rel}", 0.0, evidence,
            )
        else:
            staged = True
            checked.append("the governed scratch path staged through the filter")
            if object_absence_proven:
                created_object = expected_oid
            rc, blob, _err = _git_bytes(
                studio, ["cat-file", "blob", f":{scratch_rel}"],
                timeout=_step_timeout("commit"), env=index_env,
            )
            evidence["blob_bytes"] = len(blob)
            evidence["worktree_unchanged"] = scratch.read_bytes() == raw
            evidence["raw_equals_blob"] = blob == raw

            failures: list[str] = []
            blind: list[str] = []
            if rc == _RC_TIMEOUT:
                # The blob never came back, so every byte comparison below is
                # against b"" — which looks exactly like a filter that ate the
                # whole file. Reporting that as a broken filter is the purest
                # form of red-when-blind available in this module.
                blind.append(
                    "the staged blob could not be read back before the clock "
                    "ran out, so no byte comparison was made at all"
                )
            elif rc != 0:
                failures.append(
                    "the staged path could not be read back out of the index "
                    "at all"
                )
            # C2 — the filter is clean-side only; the working tree keeps the
            # rendered region. A smudge here is the fresh-checkout illusion.
            if not evidence["worktree_unchanged"]:
                failures.append(
                    "staging MODIFIED the working-tree file; the clean filter "
                    "must never write back to disk"
                )
            if blind:
                pass  # C3 needs the blob; it is not comparable. See below.
            elif has_nav:
                # C3 — filtered-vs-filtered, against an independently computed
                # expectation: the body with exactly the sentinel-bounded
                # region(s) removed and every other byte kept. Comparing to
                # `expected` rather than to `raw` is the whole lesson of
                # 059f2c68, which compared raw worktree bytes to the committed
                # blob and so could only ever pass in a studio that had never
                # rendered anything.
                expected = _NAV_REGION_RE.sub(b"", raw)
                evidence["stripped_bytes"] = len(raw) - len(blob)
                evidence["expected_stripped_bytes"] = len(raw) - len(expected)
                if _NAV_REGION_RE.search(blob):
                    failures.append(
                        "the staged blob still carries a rendered nav-block "
                        "region — derived content is entering the object store"
                    )
                elif blob != expected:
                    failures.append(
                        f"the staged blob is not the sentinel-stripped form of "
                        f"the body: staging removed {len(raw) - len(blob)} "
                        f"byte(s) where the rendered region accounts for "
                        f"{len(raw) - len(expected)}, so the filter is cutting "
                        "authored content or leaving derived content behind"
                    )
            elif blob != raw:
                failures.append(
                    "the staged blob differs from a body that carries no "
                    "derived region at all — the filter is rewriting authored "
                    "content"
                )

            # C4 — idempotence. Re-filtering the filter's own output must be a
            # no-op, or the same body stages to a different blob on every add
            # and every studio fights every other studio forever. Compared as
            # hashes and computed without -w, so the check writes nothing.
            frc, filtered_hash, _e = _git_bytes(
                studio, ["hash-object", "--stdin", "--path", scratch_rel],
                timeout=_step_timeout("commit", 15.0 / 20.0), stdin=blob,
            )
            lrc, literal_hash, _e = _git_bytes(
                studio, ["hash-object", "--stdin", "--no-filters"],
                timeout=_step_timeout("commit", 15.0 / 20.0), stdin=blob,
            )
            if _RC_TIMEOUT in (frc, lrc):
                # The old build folded this into `idempotent = frc == 0 and
                # ...`, so a hash-object that ran out of time printed "the
                # clean filter is not a fixed point" — an accusation, in the
                # studio's own report, produced by nothing but a slow clock.
                evidence["filter_idempotent"] = None
                blind.append(
                    "the fixed-point check did not finish: `git hash-object` "
                    "ran out of time, so whether re-filtering the filter's own "
                    "output changes it was never determined"
                )
            else:
                idempotent = (
                    frc == 0 and lrc == 0
                    and filtered_hash.strip() == literal_hash.strip()
                )
                evidence["filter_idempotent"] = idempotent
                if not idempotent:
                    failures.append(
                        "re-filtering the filter's own output changes it — the "
                        "clean filter is not a fixed point, so the same file "
                        "stages differently on every add"
                    )

            if failures:
                # A determined break wins over an incomplete check: the bytes
                # this probe DID compare came back wrong, and that is a
                # finding no amount of missing budget takes away.
                result = _failed(
                    "commit",
                    f"clean-filter round trip broke on "
                    f"{sample.relative_to(studio)}: " + "; ".join(failures)
                    + (
                        f". (Also not checked: {'; '.join(blind)})"
                        if blind else ""
                    ),
                    NAVBLOCK_VERIFY_CURE,
                    0.0, evidence,
                )
            elif blind:
                result = _unknown(
                    "commit",
                    f"the clean-filter round trip is UNKNOWN on "
                    f"{sample.relative_to(studio)}: nothing that was compared "
                    f"came back wrong, and part of the round trip was never "
                    f"compared. Checked: {'; '.join(checked)}. NOT checked: "
                    + "; ".join(blind),
                    unknown_cure, 0.0, evidence,
                    checked=checked, not_checked=blind,
                )
            else:
                shape = (
                    f"stripped {evidence.get('stripped_bytes', 0)} byte(s) of "
                    "rendered nav region at the git boundary while the working "
                    "tree kept it"
                    if has_nav else
                    "passed authored bytes through unchanged (no rendered nav "
                    "region exists in this studio to strip)"
                )
                result = _passed(
                    "commit",
                    f"a real governed body ({sample.relative_to(studio)}, "
                    f"{len(raw)} bytes) survived the stage/unstage round trip: "
                    f"both filter halves wired, {shape}, and the filter is a "
                    "fixed point",
                    0.0, evidence,
                )
    except OSError as exc:
        # "Could not be exercised" is the definition of UNKNOWN. The studio may
        # round-trip governed files perfectly; what happened is that this
        # instrument could not write its scratch copy or read it back.
        not_checked = [f"the round trip itself ({exc.__class__.__name__}: {exc})"]
        result = _unknown(
            "commit",
            f"the clean-filter round trip could not be exercised: {exc}. "
            f"Checked: {'; '.join(checked) if checked else 'nothing yet'}. "
            f"NOT checked: {'; '.join(not_checked)}",
            unknown_cure, 0.0, evidence,
            checked=checked, not_checked=not_checked,
        )
    finally:
        residue: list[str] = []
        # Unstage first, then remove the file: the order a human would use,
        # and the order that cannot leave a scratch path staged. Cleanup is on
        # the cleanup clock, not the measurement clock — see _cleanup_timeout.
        if staged:
            _git(studio, "reset", "-q", "--", scratch_rel,
                 timeout=_cleanup_timeout(), env=index_env)
            still = _git(studio, "ls-files", "--cached", "--", scratch_rel,
                         timeout=_cleanup_timeout(), env=index_env)
            evidence["unstaged"] = not (still.out or "").strip()
            if not evidence["unstaged"]:
                residue.append(f"{scratch_rel} is still staged after reset")
        try:
            if scratch.is_file():
                # Not governed substrate: a scratch copy this probe wrote
                # seconds ago under a dotted name no mint can produce. Nothing
                # the studio owns under vault/files/ is ever removed here.
                scratch.unlink()
        except OSError as exc:
            residue.append(f"{scratch_rel}: {exc}")
        if created_object:
            # The blob this probe's own staging wrote, and only that one: the
            # hash was absent from the store before the add. Loose objects are
            # not governed substrate and an unreferenced one would linger until
            # the next gc, so it goes back out.
            located = _git(studio, "rev-parse", "--git-path",
                           f"objects/{created_object[:2]}/{created_object[2:]}",
                           timeout=_cleanup_timeout())
            loose = Path((located.out or "").strip())
            if located.rc == 0 and str(loose):
                if not loose.is_absolute():
                    loose = studio / loose
                try:
                    if loose.is_file():
                        loose.unlink()
                        evidence["removed_probe_object"] = created_object[:12]
                except OSError as exc:
                    residue.append(f"loose object {created_object[:12]}: {exc}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        if residue:
            evidence["residue"] = residue

    elapsed = time.monotonic() - started
    assert result is not None
    if "residue" in result.evidence:
        # Determined, and it outranks an UNKNOWN round trip for the same
        # reason it does in MINT: the residue was observed, and AC2 says a
        # failed probe leaves none.
        return _failed(
            "commit",
            result.detail + " — and this probe could not clean up after "
            "itself: " + "; ".join(result.evidence["residue"]),
            f"git reset -q -- {scratch_rel} && rm -f {scratch_rel}"
            "  # scratch copy written by this probe",
            elapsed, result.evidence,
        )
    return ProbeResult(result.operation, result.status, result.detail,
                       result.cure, elapsed, result.evidence)


# ── probe 5: BUILD ───────────────────────────────────────────────────────────


def probe_build(studio: Path) -> ProbeResult:
    """Does the cockpit still compile?

    Caught by hand on 2026-07-30, which is the whole complaint: it should not
    need a human. Typechecking is the cheapest question that still answers
    "would this app build", and it is the one that fits the budget.

    When the budget cannot cover it, this DEGRADES HONESTLY — it reports what
    it did check and says the compile state is unknown. It never reports a
    green build it did not observe.

    T37's first build already got the timeout right here (it set
    `evidence["degraded"]` and said "this is a budget result reported as one,
    not a green build") and could only express it as a FAIL, because there were
    two outcomes and it refused to use the wrong one. AC7a gives it the word it
    was reaching for. Two neighbouring states join it, on the same line the
    module docstring draws:

      * no cockpit at all — nothing here says this studio is supposed to have
        one, and "the compile state is unknown" is the true sentence.
      * the typechecker is not installed — that is a MACHINE that has not run
        `npm install`, not a studio that cannot compile. Failing it makes the
        instrument report a defect that does not exist anywhere but here,
        which is gate number eight.

    A cockpit DIRECTORY with no `package.json` stays FAIL, and the difference
    is the point: the studio declares an app there and the app's manifest is
    gone. That is substrate damage, determined, with a one-line repair.
    """
    started = time.monotonic()
    app = studio / "tropo-app"
    evidence: dict = {"app_path": "tropo-app"}
    checked: list[str] = []

    if not app.is_dir():
        not_checked = ["whether the cockpit compiles — there is no cockpit here"]
        return _unknown(
            "build",
            f"no cockpit at {app}, so the compile state of this studio's app "
            "is UNKNOWN. Checked: the path where a cockpit would live. NOT "
            f"checked: {not_checked[0]}. This is an absent app reported as "
            "one, not a broken build",
            "ls tropo-app  # restore or clone the cockpit into this studio",
            time.monotonic() - started, evidence,
            checked=[f"the path {app} where a cockpit would live"],
            not_checked=not_checked,
        )
    checked.append("the cockpit directory is present")
    # An app directory with no manifest is not an app. Checked before the
    # typechecker because tsc will happily walk a tsconfig in a gutted tree and
    # exit 0 over nothing — a green answer to a question nobody asked.
    manifest = app / "package.json"
    evidence["manifest"] = "tropo-app/package.json"
    if not manifest.is_file():
        return _failed(
            "build",
            f"the cockpit has no manifest at {manifest} — there is no app here "
            "to compile, and a typechecker pointed at the remains of one "
            "reports success without having built anything",
            "git checkout -- tropo-app/package.json",
            time.monotonic() - started, evidence,
        )
    checked.append("the cockpit's manifest is present")
    tsc = app / "node_modules" / ".bin" / "tsc"
    evidence["typechecker"] = str(tsc.relative_to(studio))
    if not tsc.exists():
        not_checked = [
            "whether the cockpit compiles — nothing on this machine can ask"
        ]
        return _unknown(
            "build",
            f"the cockpit's typechecker is not installed ({tsc} is missing), "
            "so the compile state is UNKNOWN. Checked: the app and its "
            f"manifest are present. NOT checked: {not_checked[0]}. This is a "
            "machine that has not installed the cockpit, which says nothing "
            "about whether the cockpit compiles",
            "cd tropo-app && npm install",
            time.monotonic() - started, evidence,
            checked=checked, not_checked=not_checked,
        )
    checked.append("the typechecker is installed on this machine")

    budget = _timeout_for("build")
    evidence["timeout_s"] = round(budget, 1)
    ran = _run([str(tsc), "--noEmit"], app, budget)
    evidence["exit_code"] = ran.rc
    evidence["timed_out"] = ran.timed_out
    elapsed = time.monotonic() - started

    if ran.timed_out:
        checked.append("the typecheck was started")
        not_checked = ["whether the cockpit compiles"]
        return _unknown(
            "build",
            f"the typecheck did not finish within {budget:.1f}s of the "
            f"{active_budget():.0f}s budget, so the cockpit's compile state is "
            f"UNKNOWN. Checked: {'; '.join(checked)}. NOT checked: "
            f"{not_checked[0]} — this is a budget result reported as one, not "
            "a green build",
            "cd tropo-app && npx tsc --noEmit", elapsed, evidence,
            checked=checked, not_checked=not_checked,
        )
    if ran.rc != 0:
        first = [
            line for line in (ran.out or "").splitlines() if line.strip()
        ][:3]
        evidence["first_errors"] = first
        return _failed(
            "build",
            f"the cockpit does not typecheck (tsc exited {ran.rc}): "
            + _tail(" | ".join(first) or ran.diagnostic),
            "cd tropo-app && npx tsc --noEmit", elapsed, evidence,
        )
    return _passed(
        "build",
        f"the cockpit typechecks clean (tsc --noEmit over tropo-app in "
        f"{ran.elapsed_s:.1f}s)",
        elapsed, evidence,
    )


# ── probe 6: ORIENT ──────────────────────────────────────────────────────────


def _own_uid() -> str:
    """This tool's own governed uid, read from this file's own frontmatter.

    Derived rather than typed, and that is the whole of it. A literal `"29931da1"`
    in the body of a probe is a hardcoded uid that rots the day the tool is
    re-minted or recycled; the frontmatter above IS the tool's identity, so an
    anchor read from it cannot drift away from what the tool actually is.
    """
    inside = False
    for line in (__doc__ or "").splitlines():
        stripped = line.strip()
        if stripped == "---":
            if inside:
                break
            inside = True
            continue
        if not inside:
            continue
        match = _FM_SCALAR.match(stripped)
        if match and match.group(1) == "uid":
            return match.group(2).strip().strip("'\"")
    return ""


# The deterministic orientation, driven out-of-process.
#
# WHY A SOURCE STRING AND NOT A FILE. The two alternatives are worse. Importing
# lib.distiller here breaks AC3 (it pulls PyYAML and cryptography into this
# interpreter) and would take the whole run down on a machine that has not
# installed them. Writing a driver into the tree — even under tempfile — is a
# write, and AC2 for this probe is stricter than AC2 for the others: ORIENT
# only READS, so the honest implementation contributes no file of its own.
# `python3 -c` is the only shape with no filesystem footprint at all.
#
# WHAT IT DOES TOUCH, STATED RATHER THAN CLAIMED AWAY. The composed index is a
# WAL-mode SQLite database, and opening one — even `mode=ro`, as every adapter
# here does — is what materialises its `-wal`/`-shm` sidecars. Those two paths
# appear beside `vault/00-index.sqlite` on a studio that had none, and they are
# the probe's ENTIRE footprint: no governed byte moves, no `__pycache__` is
# dropped (see PYTHONDONTWRITEBYTECODE below), and the index itself is
# unchanged. Every reader of the composed index in this studio does the same,
# and `vault/00-` is sanctioned churn under AC2 already. Saying "leaves not one
# byte anywhere" would have been the easier sentence and it would have been
# false.
#
# WHAT IT MAY AND MAY NOT DO. It reports FACTS and renders no verdict; every
# pass/fail/unknown decision is made by probe_orient below, where it is
# readable and testable. It opens the composed index read-only, it never writes,
# and it never installs, synthesises, or works around the group authority — a
# studio without one comes back as `stage: authority` and stops there.
#
# THE TWO RUNGS IT CLIMBS IN ORDER, and the order is the state machine: the
# corpus is proved readable and non-empty (`stage: corpus` if not) before the
# authority is asked about (`stage: authority` if none is installed), so the
# probe can never report the second state over a studio that is in the first.
_ORIENT_DRIVER = r'''
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def describe(error):
    """Flatten a typed refusal into JSON without importing its class here."""
    code = getattr(error, "code", None)
    return {
        "error_kind": type(error).__name__,
        "error_code": str(getattr(code, "value", code) or ""),
        "error_message": str(getattr(error, "message", None) or error),
    }


def orient(root, preferred, budget, shortlist):
    report = {"stage": "start"}
    index_path = root / "vault" / "00-index.sqlite"

    # --- rung 1: is there a corpus, and can it be read?
    #
    # First, and before a single one of the studio's own modules is imported.
    # Whether the composed index opens and holds rows is a fact about the
    # VAULT; it does not depend on what this machine has installed, and asking
    # it first is what keeps "nobody can orient over nothing" from being
    # reported as one of the later, differently-owned states. An index that
    # opens and holds ZERO rows counts here too: it is readable and it is
    # nothing, and walking on would end at "nothing is inside this viewer's
    # audience", which names the wrong owner and prints the wrong cure.
    try:
        connection = sqlite3.connect("file:%s?mode=ro" % index_path, uri=True)
        entry_count = connection.execute(
            "SELECT COUNT(*) FROM entries"
        ).fetchone()[0]
    except BaseException as exc:
        report.update(stage="corpus", corpus_readable=False, **describe(exc))
        return report
    report["corpus_readable"] = True
    report["corpus_entry_count"] = int(entry_count or 0)
    if not entry_count:
        report["stage"] = "corpus"
        return report

    sys.path.insert(0, str(root / "vault" / "tools"))
    try:
        from lib.audience_gate import INSTALLED_RELATIVE, cutover_active
        from lib.group_authority import (
            PRINCIPAL_ARTIFACT, verify_principal_directory,
        )
        from lib.viewer_projection import Viewer, ViewerProjection
        from lib.task_circle import SqliteStructuralIndex
        from lib.distiller_ranker import SqliteRankIndex
        from lib.distiller import orient_deterministic
    except BaseException as exc:
        report.update(stage="import", error_kind=type(exc).__name__,
                      error_message=str(exc),
                      missing_module=getattr(exc, "name", None) or "")
        return report

    # --- rung 2: has a group authority been installed FOR THE STUDIO? Asked
    # through the studio's OWN function so this probe and the studio can never
    # disagree about what "installed" means. Nothing about this question is
    # scoped to the hardware (ADR-065): the record it reads travels with the
    # vault, so the answer is the same on every box the Studio is cloned to.
    try:
        installed = bool(cutover_active(root))
    except BaseException as exc:
        report.update(stage="authority", **describe(exc))
        return report
    report["authority_installed"] = installed
    if not installed:
        report["stage"] = "authority"
        return report

    # --- who this studio can be viewed AS, read from the installed authority's
    # own principal directory. Deliberately a DIFFERENT artifact from the one
    # visibility resolves through: "who is who" and "what can they see" are two
    # questions, and collapsing them would make a broken registry look like a
    # studio with no principals.
    try:
        pin = json.loads((root / INSTALLED_RELATIVE).read_bytes().decode("utf-8"))
        generation = root / str(pin.get("generation_dir") or "")
        directory = verify_principal_directory(
            (generation / PRINCIPAL_ARTIFACT).read_bytes()
        )
        principals = {
            uid for uid, claim in directory.items()
            if isinstance(uid, str) and uid and claim.get("status") == "active"
        }
    except BaseException as exc:
        report.update(stage="viewer", **describe(exc))
        return report
    report["authority_principal_count"] = len(principals)
    if not principals:
        report["stage"] = "viewer"
        return report

    try:
        projection = ViewerProjection.from_repo_root(root, index_path=index_path)
        circle_index = SqliteStructuralIndex(index_path)
        rank_index = SqliteRankIndex(index_path)
    except BaseException as exc:
        report.update(stage="adapters", **describe(exc))
        return report

    # The widest audience the authority grants anyone. A liveness probe asks
    # whether this studio can answer for ANYBODY; if the most-visible principal
    # cannot, nobody can. Deterministic: widest first, uid-tiebroken.
    widest = None
    for principal_uid in sorted(principals):
        candidate = Viewer(principal_uid=principal_uid)
        seen = projection.visible_segments(candidate)
        if not seen.ok:
            report.update(stage="visibility", viewer_principal_uid=principal_uid,
                          **describe(seen.error))
            return report
        if widest is None or len(seen.value) > widest[1]:
            widest = (principal_uid, len(seen.value), sorted(seen.value))
    viewer = Viewer(principal_uid=widest[0])
    report["viewer_principal_uid"] = widest[0]
    report["visible_segment_count"] = widest[1]
    report["visible_segments"] = widest[2]

    # --- the anchor: a real, connected entry, chosen from the index itself,
    # over the read-only connection rung 1 already opened and proved.

    def neighbours(uid):
        rows = connection.execute(
            "SELECT dst_uid FROM edges WHERE src_uid=? "
            "UNION SELECT src_uid FROM edges WHERE dst_uid=?", (uid, uid)
        ).fetchall()
        return sorted({r[0] for r in rows if isinstance(r[0], str) and r[0]})

    preferred_indexed = bool(preferred) and connection.execute(
        "SELECT 1 FROM entries WHERE uid=?", (preferred,)
    ).fetchone() is not None
    report["preferred_uid"] = preferred
    report["preferred_uid_indexed"] = preferred_indexed

    candidates = []
    if preferred_indexed:
        candidates.append((preferred, "the instrument's own governed entry"))
    for row in connection.execute(
        "SELECT e.uid FROM entries e JOIN edges g "
        "ON g.src_uid = e.uid OR g.dst_uid = e.uid "
        "GROUP BY e.uid ORDER BY COUNT(*) DESC, e.uid ASC LIMIT ?", (shortlist,)
    ).fetchall():
        if row[0] != preferred:
            candidates.append(
                (row[0], "the most connected entry in the composed index")
            )

    considered = []
    anchor = None
    for uid, rule in candidates:
        structural = neighbours(uid)
        visible = ()
        if structural:
            seen = projection.filter_visible_uids(structural, viewer)
            if not seen.ok:
                report.update(stage="visibility", **describe(seen.error))
                return report
            visible = seen.value
        considered.append({"uid": uid, "structural": len(structural),
                           "visible": len(visible)})
        if visible:
            anchor = (uid, rule, len(structural), len(visible))
            break
    report["anchors_considered"] = considered
    if anchor is None:
        report["stage"] = "anchor"
        return report

    report["task_uid"] = anchor[0]
    report["task_uid_rule"] = anchor[1]
    report["structural_neighbours"] = anchor[2]
    report["visible_neighbours"] = anchor[3]
    report["circle_budget"] = budget

    result = orient_deterministic(
        anchor[0], viewer, budget, projection=projection,
        circle_index=circle_index, rank_index=rank_index,
    )
    if not result.ok:
        report.update(stage="orient", **describe(result.error))
        audience = getattr(result.error, "audience_error", None)
        if audience is not None:
            report["audience_error_code"] = describe(audience)["error_code"]
        return report

    orientation = result.value
    scores = [round(float(item.score), 6) for item in orientation.items]
    report.update(
        stage="oriented",
        item_count=len(orientation.items),
        tilt=str(orientation.tilt),
        ranked_descending=all(a >= b for a, b in zip(scores, scores[1:])),
        canonical_sha256=hashlib.sha256(
            orientation.canonical().encode("utf-8")
        ).hexdigest(),
        top=[
            {"uid": item.uid, "score": round(float(item.score), 6),
             "distance": item.distance, "provenance": item.circle_provenance}
            for item in orientation.items[:5]
        ],
    )
    return report


try:
    payload = orient(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]),
                     int(sys.argv[4]))
except BaseException as exc:
    import traceback
    payload = {"stage": "driver-crashed", "error_kind": type(exc).__name__,
               "error_message": str(exc), "traceback": traceback.format_exc()[-1200:]}
sys.stdout.write(json.dumps(payload, sort_keys=True))
'''


# Refusal codes that are routed BY CODE and never by stage, because the same
# code means the same thing wherever it surfaces. Everything not named in
# either set below is a determined refusal: a typed error out of the orient
# stack is the studio saying "I cannot do this", and the default has to be to
# believe it.
#
# The split between the two sets is the split between "somebody owns this" and
# "nobody does".

# The composed index could not be READ. That is the no-corpus state reached
# late instead of early — the rung 1 check in the driver catches an index that
# will not open at all, and this catches the row that will not decode. Same
# state, same owner, same cure, so it is routed to the same place.
#
# Routing it by stage instead of by code was a measured red-when-blind: one
# entry with malformed fm_json surfaced GRAPH_UNAVAILABLE through
# `filter_visible_uids` and produced "visibility resolution still fails
# closed", which names the wrong defect, the wrong owner AND the wrong cure.
_ORIENT_NO_CORPUS_CODES: frozenset = frozenset({"GRAPH_UNAVAILABLE"})

# Refusal codes that mean THIS INSTRUMENT is at fault, rather than that the
# studio cannot orient. No owner inside the Studio, so no state: see the note
# in `orient_state`.
_ORIENT_BLIND_CODES: dict[str, str] = {
    # This instrument handed the library a budget it rejected. That is a defect
    # in THIS file, and reporting the studio red for it is the most direct
    # red-when-blind there is.
    "BUDGET_INVALID": "python3 vault/tools/tropo-smoke.py --only orient --json",
}


def probe_orient(studio: Path) -> ProbeResult:
    """Can this studio answer a question about itself?

    The deterministic core of the crew's flagship capability, driven against
    the real studio: pick a real anchor, build a real viewer, draw the circle,
    rank it. No model, no network, no spend — `orient_deterministic` is the
    zero-cost half of `orient()` and it is the half that was found unable to
    run at all.

    THE LINE THIS PROBE DRAWS, and every branch below is one of these:

      PASS     a ranked, non-empty circle came back for a real anchor.
      FAIL     the studio was asked and answered that it cannot: a typed
               refusal, or an empty circle over substrate the projection had
               just said was visible.
      UNKNOWN  this instrument could not determine an answer — there is no
               corpus to orient over, no group authority has been installed
               for the Studio, the library is not importable on this machine,
               the authority resolves no principal to view as, nothing in the
               studio is inside this viewer's audience, or the clock ran out.

    AND WHEN IT IS NOT A PASS, IT SAYS WHOSE PROBLEM IT IS. Three states, read
    as the ladder at `orient_state` and printed at the front of the detail line
    so a report that scrolls past is still legible:

      no-corpus                                UNKNOWN  the index rebuilder
      corpus-but-no-authority                  UNKNOWN  one human, once, for
                                                        the Studio
      authority-installed-but-still-refusing   FAIL     the retrieval path

    Two of those are nobody having done a thing yet. The third is a defect in
    something that was done, and it is the reason this probe exists. Branches
    that could not LOOK carry no state at all, on purpose — see `orient_state`.

    THE EMPTY CIRCLE IS THE HARD ONE, so it is worth reading the two branches
    together. An empty circle is NOT automatically a defect: if every neighbour
    of the anchor sits in a segment this viewer cannot read, returning nothing
    is orient behaving exactly as designed, and failing it would be the
    instrument manufacturing the false-positive class this whole tool exists to
    end. So the probe settles that question BEFORE it draws, by asking the
    projection itself which of the anchor's structural neighbours are visible:

      * no anchor on the shortlist has a visible neighbour -> UNKNOWN. The
        studio has structure and none of it is inside this audience; nothing
        was learned about whether orient can rank.
      * the anchor HAS visible neighbours and the circle comes back empty ->
        FAIL. The projection said the substrate is readable and orient returned
        none of it. That is a determined negative about retrieval, reached with
        every fact in hand — the instrument was not blind, it was answered.

    WHAT IT WILL NOT DO TO GET A GREEN. It never installs or works around the
    group authority; a Studio without one is an unperformed setup step,
    reported as UNKNOWN with the one-time install named. It never invents a
    viewer; `visible_segments` refuses a viewer carrying no principal, and that
    refusal is the CALLER being wrong rather than the studio being broken, so
    the principal is one the installed authority itself resolves or there is no
    run. It claims no visibility the authority did not grant.

    WHAT AN INSTALLED AUTHORITY BUYS, in the only words this probe uses for
    it: ATTRIBUTION, CONTINUITY, and knowing WHO IS WHO. That is the bar Mike
    ruled and the bar this reports against — no higher one is claimed here, in
    the output or anywhere else in this file.
    """
    started = time.monotonic()
    evidence: dict = {}
    checked: list[str] = []

    library = studio / ORIENT_LIBRARY_REL
    evidence["orient_library"] = ORIENT_LIBRARY_REL
    if not library.is_file():
        not_checked = [
            "whether this studio can orient — the capability is not here to ask"
        ]
        return _unknown(
            "orient",
            f"the deterministic orient library is not on this studio "
            f"({library} is missing), so whether it can answer a question "
            "about itself is UNKNOWN. Checked: the path where the library "
            f"would live. NOT checked: {not_checked[0]}",
            f"git checkout -- {ORIENT_LIBRARY_REL}",
            time.monotonic() - started, evidence,
            checked=[f"the path {ORIENT_LIBRARY_REL} where the library would live"],
            not_checked=not_checked,
        )
    checked.append(f"the orient library is present at {ORIENT_LIBRARY_REL}")

    index_path = studio / COMPOSED_INDEX_REL
    evidence["composed_index"] = COMPOSED_INDEX_REL
    if not index_path.is_file():
        # Rung 1 of the ladder, and the cheapest reading of it: the file is not
        # there, so nothing downstream is worth asking. Stated as the state
        # rather than as a bare UNKNOWN, because "there is no index" without an
        # owner is the answer that leaves the reader where they started.
        state = orient_state(corpus_readable=False).stamp(evidence)
        not_checked = [
            "whether this studio can orient — there is no composed index to "
            "draw a circle over",
            "whether a group authority is installed for this Studio — a "
            "question with no meaning until there is something to orient over",
        ]
        return _unknown(
            "orient",
            f"{state.opening()}: there is no composed index at {index_path}, "
            "so orient has nothing to read and nobody can orient over "
            "nothing. The capability's state is UNKNOWN. Checked: "
            f"{'; '.join(checked)}. NOT checked: {'; '.join(not_checked)}",
            state.next_action, time.monotonic() - started, evidence,
            checked=checked, not_checked=not_checked,
        )
    checked.append(f"the composed index is present at {COMPOSED_INDEX_REL}")

    budget = _timeout_for("orient")
    evidence["timeout_s"] = round(budget, 1)
    evidence["circle_budget"] = ORIENT_CIRCLE_BUDGET
    preferred = _own_uid()
    evidence["preferred_uid"] = preferred
    ran = _run(
        [sys.executable, "-c", _ORIENT_DRIVER, str(studio), preferred,
         str(ORIENT_CIRCLE_BUDGET), str(ORIENT_ANCHOR_SHORTLIST)],
        studio, budget,
        # AC2 is absolute for this probe: it reads and writes nothing. Importing
        # the orient library would otherwise drop .pyc files into
        # vault/tools/lib/__pycache__/, which is a write into the studio however
        # gitignored it happens to be.
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )
    elapsed = time.monotonic() - started
    evidence["driver_exit_code"] = ran.rc
    evidence["driver_timed_out"] = ran.timed_out

    if ran.timed_out:
        checked.append("the deterministic orientation was launched")
        not_checked = [
            "whether a circle can be drawn",
            "whether that circle can be ranked",
        ]
        return _unknown(
            "orient",
            f"the deterministic orientation did not finish within "
            f"{budget:.1f}s of the {active_budget():.0f}s budget, so whether "
            "this studio can answer a question about itself is UNKNOWN. "
            f"Checked: {'; '.join(checked)}. NOT checked: "
            f"{'; '.join(not_checked)} — this is a budget result reported as "
            "one, not a broken capability",
            f"python3 vault/tools/tropo-smoke.py --only orient  "
            f"# no `--fast` on it — time the real cost first",
            elapsed, evidence, checked=checked, not_checked=not_checked,
        )

    try:
        report = json.loads(ran.out or "")
    except (json.JSONDecodeError, ValueError):
        report = None
    if not isinstance(report, dict):
        # The driver is this file's own code. It failing to report is an
        # instrument fault, and calling the studio red for it is exactly the
        # red-when-blind AC7a names.
        not_checked = ["the entire ORIENT operation"]
        return _unknown(
            "orient",
            "the orientation driver returned no readable report "
            f"(rc={ran.rc}): {ran.diagnostic}. That is a fault in this "
            "instrument, not a finding about the studio, so ORIENT is "
            f"UNKNOWN. Checked: {'; '.join(checked)}. NOT checked: "
            f"{not_checked[0]}",
            "python3 vault/tools/tropo-smoke.py --only orient --json",
            elapsed, evidence, checked=checked, not_checked=not_checked,
        )

    return _orient_verdict(report, evidence, checked, elapsed)


def _orient_verdict(report: dict, evidence: dict, checked: list,
                    elapsed: float) -> ProbeResult:
    """Turn the driver's facts into one of the three outcomes, and say whose.

    Split out from probe_orient on purpose: the boundary between "the studio
    cannot" and "this instrument could not tell" is the substance of this
    probe, and it belongs somewhere a test can drive it directly with a
    payload rather than only through a subprocess against a real studio.

    Every branch here is one of exactly two kinds, and the kind is visible in
    the code as well as in the output:

      * IT NAMES A STATE. `orient_state(...)` is called, the state is stamped
        into evidence, and the detail opens with the state's name and owner.
        Three of these, and no two print the same command.
      * IT NAMES NO STATE. This instrument could not look, so there is nothing
        to own. UNKNOWN, with what was and was not checked, and deliberately no
        `orient_state` — a fourth label for blindness would re-collapse the
        three.

    The one exception is documented where it sits: an authority record the
    studio's own check cannot even evaluate is a determined FAIL and carries no
    state, because no rung of the ladder was established either way.
    """
    stage = str(report.get("stage") or "")
    evidence["stage"] = stage
    for key in (
        "corpus_readable", "corpus_entry_count",
        "authority_installed", "authority_principal_count",
        "viewer_principal_uid", "visible_segment_count", "preferred_uid_indexed",
        "task_uid", "task_uid_rule", "structural_neighbours",
        "visible_neighbours", "item_count", "tilt", "ranked_descending",
        "canonical_sha256", "error_kind", "error_code", "audience_error_code",
        "missing_module",
    ):
        if key in report:
            evidence[key] = report[key]
    for key in ("visible_segments", "anchors_considered", "top"):
        if key in report:
            evidence[key] = report[key]
    message = str(report.get("error_message") or "")

    def still_refusing() -> OrientState:
        """State 3, read off the ladder rather than asserted.

        Every caller of this sits BELOW the driver's own two gates — it returns
        at `stage: corpus` when the index cannot be read and at
        `stage: authority` when no authority is installed — so reaching one of
        them IS the first two rungs holding. The facts are still read from the
        report where the driver stated them, so the ladder does the deciding
        and this function never re-decides it.
        """
        state = orient_state(
            corpus_readable=report.get("corpus_readable") is not False,
            authority_installed=report.get("authority_installed") is not False,
            orient_answered=False,
        )
        return state.stamp(evidence)

    # ---- rung 1: there is nothing to orient over -------------------------- #
    # The driver's own first act, so this arrives before any question about
    # authority: an index that will not open, or one that opens and is empty.
    # Both are "nobody can orient over nothing", both belong to whoever
    # rebuilds the index, and neither says anything about the two rungs above.
    if stage == "corpus":
        state = orient_state(corpus_readable=False).stamp(evidence)
        empty = report.get("corpus_readable") is True
        because = (
            f"the composed index at {COMPOSED_INDEX_REL} opens and holds no "
            "entries at all"
            if empty else
            f"the composed index at {COMPOSED_INDEX_REL} could not be read "
            f"({report.get('error_kind')}: {_tail(message)})"
        )
        not_checked = [
            "whether a circle can be drawn — there is no substrate to draw one "
            "over",
            "whether a group authority is installed for this Studio — a "
            "question with no meaning until there is something to orient over",
            "whether that circle can be ranked",
        ]
        return _unknown(
            "orient",
            f"{state.opening()}: {because}, so orient has nothing to work "
            "from and nobody can orient over nothing. UNKNOWN, and it says "
            "nothing at all about the group authority or about retrieval — "
            f"those are the other two states. Checked: {'; '.join(checked)}; "
            "whether the composed index opens and holds entries. NOT checked: "
            f"{'; '.join(not_checked)}",
            state.next_action, elapsed, evidence,
            checked=checked + [
                "whether the composed index opens and holds entries"
            ],
            not_checked=not_checked,
        )

    # ---- rung 2: no group authority has been installed for this Studio ---- #
    if stage == "authority" and report.get("authority_installed") is False:
        state = orient_state(
            corpus_readable=True, authority_installed=False,
        ).stamp(evidence)
        not_checked = [
            "whether a circle can be drawn — visibility resolution refuses "
            "before the first neighbour is looked at",
            "whether that circle can be ranked",
            "whether retrieval works — that is the third state and it cannot "
            "be reached from here",
        ]
        return _unknown(
            "orient",
            f"{state.opening()}: the composed index is here and readable, and "
            "no group authority has ever been installed for this Studio "
            f"({GROUP_AUTHORITY_PIN_REL} is absent or unreadable), so every "
            "visibility resolution fails closed and orient cannot start. That "
            "is an UNPERFORMED SETUP STEP, not a broken studio, and it is "
            "UNKNOWN rather than FAIL. It is one act for the Studio, not one "
            "per machine: the record travels with the vault, so a clone that "
            "already carries one performs nothing. This probe will not "
            f"install it to produce a green. Checked: {'; '.join(checked)}; "
            "the installed-authority record, through the studio's own cutover "
            f"check. NOT checked: {'; '.join(not_checked)}",
            state.next_action, elapsed, evidence,
            checked=checked + [
                "the installed-authority record, through the studio's own "
                "cutover check"
            ],
            not_checked=not_checked,
        )
    if stage == "authority":
        # NO STATE, and the reason is the ladder rather than an oversight: the
        # studio's own check did not return "installed" OR "not installed", it
        # could not evaluate the question, so neither rung 2 nor rung 3 was
        # established. A determined FAIL about the record itself.
        return _failed(
            "orient",
            "this studio's own cutover check could not read the "
            f"installed-authority record at {GROUP_AUTHORITY_PIN_REL}: "
            f"{report.get('error_kind')}: {_tail(message)}. That is neither of "
            "the two authority states — the question could not be evaluated at "
            "all — so it is reported as damage to the record, which travels "
            "with the vault and can be restored from it",
            _cure_chain(
                [GROUP_AUTHORITY_VERIFY_CURE,
                 f"git checkout -- {GROUP_AUTHORITY_DIR_REL}"],
                GROUP_AUTHORITY_VERIFY_CURE,
            ),
            elapsed, evidence,
        )

    # ---- the library will not import on this machine ---------------------- #
    # NO STATE either way. Neither rung was reached past the corpus: the
    # unprovisioned machine is not a fact about the Studio at all, and a
    # damaged `lib/` module is damage to the capability rather than to the
    # corpus, the authority, or the retrieval path the three states divide.
    if stage == "import":
        missing = str(report.get("missing_module") or "")
        # A dependency this studio does not own is a MACHINE that has not been
        # provisioned — break 7, "deps declared but never shipped to the fork
        # that needs them". Failing it would report a defect that exists
        # nowhere but here. A missing `lib.*` is substrate damage and stays a
        # determined failure.
        if missing and not missing.startswith("lib"):
            not_checked = ["the entire ORIENT operation"]
            return _unknown(
                "orient",
                f"the orient library needs {missing!r}, which is not "
                "installed on this machine, so whether this studio can orient "
                "is UNKNOWN. Checked: "
                f"{'; '.join(checked)}. NOT checked: {not_checked[0]}. This "
                "is an unprovisioned machine, which says nothing about "
                "whether the capability works",
                "python3 -m pip install -r requirements.txt",
                elapsed, evidence, checked=checked, not_checked=not_checked,
            )
        return _failed(
            "orient",
            "the deterministic orient library on this studio cannot be "
            f"imported: {report.get('error_kind')}: {_tail(message)}",
            f"python3 -c 'import lib.distiller'  "
            f"# from vault/tools/; then git checkout -- {ORIENT_LIBRARY_REL}",
            elapsed, evidence,
        )

    # ---- the authority names nobody this probe could view as -------------- #
    # NO STATE. An authority IS installed, so this is not rung 2, and the probe
    # never got to ask the studio anything, so it is not rung 3 either: it
    # could not build a viewer to ask WITH. Naming an owner for that would be
    # this instrument blaming the studio for a question it could not pose.
    if stage == "viewer":
        not_checked = [
            "whether a circle can be drawn for any real principal",
            "whether that circle can be ranked",
        ]
        return _unknown(
            "orient",
            "the installed group authority names no active principal this "
            f"probe could view as ({report.get('authority_principal_count')} "
            "found"
            + (f"; {report.get('error_kind')}: {_tail(message)}"
               if message else "")
            + "), so ORIENT is UNKNOWN. A viewer carrying no principal is "
            "refused by visible_segments, and that refusal would be THIS "
            "CALLER being wrong rather than the studio being unable — so no "
            "viewer is invented here to get past it. Checked: "
            f"{'; '.join(checked)}; the installed authority's own principal "
            f"directory. NOT checked: {'; '.join(not_checked)}",
            _cure_chain(
                [f"python3 {GROUP_AUTHORITY_TOOL_REL} verify", GROUP_REGISTRY_CURE],
                GROUP_REGISTRY_CURE,
            ),
            elapsed, evidence,
            checked=checked + [
                "the installed authority's own principal directory"
            ],
            not_checked=not_checked,
        )

    # ---- the driver died on the way to an answer --------------------------- #
    # NO STATE: the driver is this file's own code.
    if stage == "driver-crashed":
        not_checked = ["the entire ORIENT operation"]
        return _unknown(
            "orient",
            "the orientation driver raised before it could report: "
            f"{report.get('error_kind')}: {_tail(message)}. The driver is this "
            "instrument's own code, so that is a fault HERE and not a finding "
            "about the studio; ORIENT is UNKNOWN. Checked: "
            f"{'; '.join(checked)}. NOT checked: {not_checked[0]}",
            "python3 vault/tools/tropo-smoke.py --only orient --json",
            elapsed, evidence, checked=checked, not_checked=not_checked,
        )

    # ---- rung 1 again, reached late: the corpus could not be READ --------- #
    # Routed by CODE and before any stage, because the code means the same
    # thing wherever it surfaces. The driver's rung-1 check catches an index
    # that will not open; a row that will not decode only shows up when
    # something reads it, and that can be at any stage above. Same state, same
    # owner, same cure either way. See _ORIENT_NO_CORPUS_CODES.
    code = str(report.get("error_code") or "")
    if code in _ORIENT_NO_CORPUS_CODES:
        state = orient_state(corpus_readable=False).stamp(evidence)
        not_checked = [
            "whether a circle can be drawn",
            "whether that circle can be ranked",
            "whether retrieval is at fault — an index this instrument cannot "
            "read cannot convict it",
        ]
        return _unknown(
            "orient",
            f"{state.opening()}: the orient stack refused with {code} at "
            f"stage {stage!r}: {_tail(message)}. The composed index could not "
            "be READ, which is the same state as no index at all however late "
            "it surfaces — not the studio answering that it cannot orient, "
            "and not the authority's problem. UNKNOWN. Checked: "
            f"{'; '.join(checked)}. NOT checked: {'; '.join(not_checked)}",
            state.next_action, elapsed, evidence,
            checked=checked, not_checked=not_checked,
        )

    # ---- this instrument's own fault, wherever it surfaced ----------------- #
    # NO STATE: a bad argument out of this file has no owner in the Studio.
    if code in _ORIENT_BLIND_CODES:
        not_checked = [
            "whether a circle can be drawn",
            "whether that circle can be ranked",
        ]
        return _unknown(
            "orient",
            f"the orient stack refused with {code} at stage {stage!r}: "
            f"{_tail(message)}. That is this instrument handing the library "
            "something it would not take, rather than the studio answering "
            "that it cannot orient, so ORIENT is UNKNOWN and no state is "
            f"claimed for it. Checked: {'; '.join(checked)}. NOT checked: "
            f"{'; '.join(not_checked)}",
            _ORIENT_BLIND_CODES[code], elapsed, evidence,
            checked=checked, not_checked=not_checked,
        )

    # ---- an adapter over the composed index refused to construct ---------- #
    # A guard rather than an observed state: every adapter here opens the index
    # lazily, so a constructor that refuses outright would be new behaviour in
    # the library. Kept, and kept a determined FAIL, because if the library
    # ever does refuse to construct over an index this probe has already
    # confirmed present and readable, that is the studio answering.
    if stage == "adapters":
        state = still_refusing()
        return _failed(
            "orient",
            f"{state.opening()}: a group authority IS installed and this "
            "studio's own orient adapters refuse to construct over a composed "
            "index this probe has already read: "
            f"{report.get('error_kind')}: {_tail(message)}",
            f"{FULL_REBUILD_CURE}  # then, if the adapters still refuse over a "
            "freshly composed index, the refusal is in the retrieval path and "
            f"not in the corpus: {state.next_action}",
            elapsed, evidence,
        )

    # ---- the visibility floor is down WITH an authority installed ---------- #
    # State 3's defining condition, and Metis G98's finding on disk.
    if stage == "visibility":
        state = still_refusing()
        return _failed(
            "orient",
            f"{state.opening()}: a group authority IS installed and "
            "visibility resolution still fails closed for principal "
            f"{report.get('viewer_principal_uid')!r}"
            f": {report.get('error_code') or report.get('error_kind')}: "
            f"{_tail(message)}. This is the failure that put ORIENT in this "
            "tool — orient cannot start, before a circle is drawn and before "
            "anything is ranked — and with the authority installed it is a "
            "determined defect rather than a setup step nobody has taken",
            state.next_action, elapsed, evidence,
        )

    # ---- nothing in the studio is inside this viewer's audience ------------ #
    # NO STATE, and this is the branch where that matters most. The corpus is
    # readable and the authority is installed, so the shape looks like state 3
    # — but orient was never asked a question it could answer, so calling it a
    # retrieval defect would cry wolf on every studio whose audience does not
    # happen to cover its own substrate. Its matched pair is the EMPTY CIRCLE
    # over READABLE substrate below, which is state 3 and is a FAIL.
    if stage == "anchor":
        considered = report.get("anchors_considered") or []
        not_checked = [
            "whether a circle can be drawn — there is no anchor whose "
            "substrate this viewer is permitted to see",
            "whether that circle can be ranked",
        ]
        return _unknown(
            "orient",
            "none of the "
            f"{len(considered)} most connected entries in the composed index "
            "has a single neighbour inside the audience the installed "
            f"authority grants {report.get('viewer_principal_uid')!r} "
            f"({report.get('visible_segment_count')} segment(s) visible), so "
            "an empty circle here would be orient behaving correctly and "
            "nothing can be concluded about whether it can rank. UNKNOWN. "
            f"Checked: {'; '.join(checked)}; the shortlist of anchors and "
            "which of their neighbours this viewer can read. NOT checked: "
            f"{'; '.join(not_checked)}",
            "python3 vault/tools/tropo-rebuild-index.py --apply  "
            "# then widen the viewer's audience, or orient by hand as a "
            "principal whose audience covers this substrate",
            elapsed, evidence,
            checked=checked + [
                "the shortlist of anchors and which of their neighbours this "
                "viewer can read"
            ],
            not_checked=not_checked,
        )

    # ---- a typed refusal out of the capability itself ---------------------- #
    if stage == "orient":
        # Anything that means "could not look" has already been routed to
        # UNKNOWN above, so everything reaching here is a determined refusal
        # with the corpus read and the authority installed: state 3.
        state = still_refusing()
        anchor = report.get("task_uid")
        if code == "NODE_NOT_FOUND":
            # A guard, and worth saying so: the anchor is chosen by a query
            # against the SAME `entries` table `SqliteStructuralIndex.structure`
            # reads, so the two cannot disagree today and no on-disk state
            # reaches this. It stays because the code is real in the wild —
            # `d2bb4dda` returns exactly this on the live studio — and if a
            # future index ever splits those two reads apart, silence here
            # would be the worse outcome.
            return _failed(
                "orient",
                f"{state.opening()}: the anchor {anchor!r} was selected FROM "
                "the composed index's own entries table and orient cannot see "
                "it — the index the capability reads and the index it is "
                f"indexed in disagree: {_tail(message)}",
                f"{FULL_REBUILD_CURE}  # a recompose is the cheap move here, "
                "but the two reads disagreeing over one index is the retrieval "
                "path's to own",
                elapsed, evidence,
            )
        return _failed(
            "orient",
            f"{state.opening()}: orient refused on anchor {anchor!r} with "
            f"{code or report.get('error_kind')}: {_tail(message)}. A typed "
            "refusal is this studio answering that it cannot orient",
            f"python3 vault/tools/tropo-smoke.py --only orient --json  "
            f"# the refusal is typed; route it by its code",
            elapsed, evidence,
        )

    if stage != "oriented":
        # NO STATE: an unrecognised stage is this file out of step with its own
        # driver, which is nobody in the Studio's problem.
        not_checked = ["the entire ORIENT operation"]
        return _unknown(
            "orient",
            f"the orientation driver stopped at an unrecognised stage "
            f"{stage!r}, which is a fault in this instrument rather than a "
            f"finding about the studio, so ORIENT is UNKNOWN. Checked: "
            f"{'; '.join(checked)}. NOT checked: {not_checked[0]}",
            "python3 vault/tools/tropo-smoke.py --only orient --json",
            elapsed, evidence, checked=checked, not_checked=not_checked,
        )

    # ---- a circle came back ------------------------------------------------ #
    anchor = report.get("task_uid")
    items = int(report.get("item_count") or 0)
    visible = int(report.get("visible_neighbours") or 0)
    structural = int(report.get("structural_neighbours") or 0)
    if items <= 0:
        state = still_refusing()
        return _failed(
            "orient",
            f"{state.opening()}: orient drew an EMPTY circle for {anchor!r}, "
            f"an entry with {structural} structural neighbour(s) of which this "
            f"viewer's own projection had just confirmed {visible} readable. "
            "Visibility resolved, the walk ran, and nothing came back — so "
            "this is a determined retrieval defect and not a blind probe. (An "
            "empty circle over substrate the viewer CANNOT read is reported "
            "UNKNOWN with no state at all; that is not this)",
            # Deliberately NOT the recompose that cures state 1, though the two
            # sibling state-3 branches above do lead with it. There the index
            # itself is implicated — an adapter will not construct over it, or
            # two reads of it disagree. Here it is not: the probe's own
            # projection had just read these neighbours out of that index, so
            # the corpus produced them and the DRAW dropped them. Handing this
            # reader state 1's command would spend a full recompose on a gate
            # no recompose touches, and would point at the corpus owner for a
            # defect that is not theirs.
            "python3 vault/tools/tropo-smoke.py --only orient --json"
            f"  # {anchor} drew 0 of {visible} neighbour(s) the projection had "
            "just read, so the drop is in the draw and belongs to the "
            "retrieval path, not to the corpus",
            elapsed, evidence,
        )
    if report.get("ranked_descending") is not True:
        state = still_refusing()
        return _failed(
            "orient",
            f"{state.opening()}: orient returned {items} member(s) for "
            f"{anchor!r} but they are not in score order, so what came back is "
            "a circle and not a RANKED circle — the second half of the "
            "capability did not run",
            "python3 -m pytest vault/tools/tests/test_distiller_ranker.py",
            elapsed, evidence,
        )
    return _passed(
        "orient",
        f"this studio answered a question about itself: a ranked circle of "
        f"{items} member(s) for {anchor} ({report.get('task_uid_rule')}), "
        f"drawn and ranked for principal {report.get('viewer_principal_uid')} "
        f"over the {report.get('visible_segment_count')} segment(s) the "
        f"installed group authority grants it, tilt "
        f"{report.get('tilt')!r}, top member "
        f"{(report.get('top') or [{}])[0].get('uid')} via "
        f"{(report.get('top') or [{}])[0].get('provenance')}",
        elapsed, evidence,
    )


PROBES: dict[str, Callable[[Path], ProbeResult]] = {
    "boot": probe_boot,
    "mint": probe_mint,
    "index": probe_index,
    "commit": probe_commit,
    "build": probe_build,
    "orient": probe_orient,
}


# ── driver ───────────────────────────────────────────────────────────────────


def run_all(studio: Path, only: Optional[str] = None,
            budget: Optional[float] = None) -> list[ProbeResult]:
    """Run the probes in operation order and return one result each.

    A probe that raises is a failure of the INSTRUMENT, and an instrument that
    dies mid-run tells you nothing about the four operations it never reached —
    so every exception becomes a result and the run continues. Under AC7a that
    result is UNKNOWN rather than FAIL: a crash in this file is not evidence
    that the studio cannot do the operation, and printing FAIL because our own
    code raised is the most direct red-when-blind there is.

    `budget` is the active time budget in seconds; None means
    TIME_BUDGET_SECONDS. It is published module-wide for the length of the run
    and restored afterwards, so a `--fast` run cannot leave a 30s ceiling
    behind for the next caller in the same process.
    """
    global _DEADLINE, _BUDGET_SECONDS
    if only is not None and only not in OPERATIONS:
        raise ValueError(
            f"unknown operation {only!r}; expected one of {', '.join(OPERATIONS)}"
        )
    operations = (only,) if only else OPERATIONS
    results: list[ProbeResult] = []
    _BUDGET_SECONDS = float(TIME_BUDGET_SECONDS if budget is None else budget)
    _DEADLINE = time.monotonic() + _BUDGET_SECONDS
    try:
        for operation in operations:
            probe = PROBES[operation]
            started = time.monotonic()
            try:
                results.append(probe(studio))
            except Exception as exc:  # the instrument must not take the run down
                results.append(_unknown(
                    operation,
                    f"the {operation.upper()} probe itself crashed, so this "
                    f"operation is UNKNOWN: {type(exc).__name__}: {exc}. "
                    "Checked: nothing this instrument can stand behind. NOT "
                    "checked: the whole operation. A crash in the instrument "
                    "is not a finding about the studio",
                    f"python3 vault/tools/tropo-smoke.py --only {operation}",
                    time.monotonic() - started,
                    {"probe_crashed": True,
                     "exception": f"{type(exc).__name__}: {exc}"},
                    checked=[],
                    not_checked=[f"the entire {operation.upper()} operation"],
                ))
    finally:
        _DEADLINE = None
        _BUDGET_SECONDS = float(TIME_BUDGET_SECONDS)
    return results


_MARKS: dict[str, str] = {
    STATUS_PASS: " PASS  ",
    STATUS_FAIL: " FAIL  ",
    STATUS_UNKNOWN: "UNKNOWN",
}


def format_report(results: list[ProbeResult],
                  budget: Optional[float] = None) -> str:
    """Loud, and it names the cure. AC4: 'MINT: FAIL' alone is not output.

    Three marks, not two. A run that reads `[UNKNOWN] INDEX` and `[ FAIL ]
    MINT` tells an operator two different things to do; a run that prints FAIL
    for both tells them the studio is twice as broken as it is, and the second
    time that happens they stop reading the tool.
    """
    budget = float(TIME_BUDGET_SECONDS if budget is None else budget)
    lines = [
        "tropo-smoke — can this studio still do its own six operations?",
        "",
    ]
    total = 0.0
    for result in results:
        total += result.elapsed_s
        mark = _MARKS.get(result.status, result.status.upper())
        lines.append(
            f"  [{mark}] {result.operation.upper():<7}{result.elapsed_s:6.1f}s  "
            f"{result.detail}"
        )
        # A cure belongs on anything that is not a clean pass: after an UNKNOWN
        # the next action ("run this one by hand, without a clock") is exactly
        # as concrete as after a FAIL.
        if result.status != STATUS_PASS and result.cure:
            lines.append(f"          cure: {result.cure}")
        if result.evidence:
            facts = ", ".join(
                f"{key}={value!r}" for key, value in result.evidence.items()
                if not isinstance(value, (list, dict))
            )
            if facts:
                lines.append(f"          evidence: {_tail(facts, 400)}")
        lines.append("")

    failed = failures(results)
    undetermined = unknowns(results)
    budget_note = (
        f"within the {budget:.0f}s budget"
        if total <= budget else
        f"OVER the {budget:.0f}s budget (AC7)"
    )
    if failed:
        lines.append(
            f"  {len(failed)} of {len(results)} operation(s) FAILED"
            + (f", {len(undetermined)} UNKNOWN" if undetermined else "")
            + f" — {total:.1f}s, {budget_note}."
        )
        lines.append(
            "  This studio cannot do all of its own work right now. Run the "
            "cures above."
        )
        if undetermined:
            lines.append(
                "  The UNKNOWN operation(s) above are NOT failures — this "
                "instrument could not determine an answer for them. Re-run "
                "them without `--fast` before treating them as defects."
            )
    elif undetermined:
        lines.append(
            f"  {len(passes(results))} of {len(results)} operation(s) PASSED "
            f"and {len(undetermined)} could not be determined — {total:.1f}s, "
            f"{budget_note}."
        )
        lines.append(
            "  Nothing here says this studio is broken, and nothing here says "
            "it is whole. An instrument that cannot afford to look reports "
            "that it did not look (AC7a)."
        )
    else:
        lines.append(
            f"  all {len(results)} operation(s) PASSED — {total:.1f}s, "
            f"{budget_note}."
        )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        add_help=True,
        description="Six liveness probes against the real studio "
                    "(dev-spec af6c53df).",
    )
    parser.add_argument("--only", metavar="OP", default=None,
                        help=f"run one operation: {', '.join(OPERATIONS)}")
    parser.add_argument("--fast", action="store_true",
                        help=f"the original AC7 promise: a "
                             f"{FAST_BUDGET_SECONDS}s total budget instead of "
                             f"{TIME_BUDGET_SECONDS}s. Expect UNKNOWN from the "
                             "operations a real studio cannot finish that fast")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output")
    parser.add_argument("--studio", metavar="PATH", default=None,
                        help="studio root (default: the studio containing "
                             "this script)")
    args = parser.parse_args(argv)

    studio = Path(args.studio).resolve() if args.studio else studio_root()
    if not studio.is_dir():
        print(f"ERROR: no studio at {studio}", file=sys.stderr)
        return 2

    budget = float(FAST_BUDGET_SECONDS if args.fast else TIME_BUDGET_SECONDS)
    started = time.monotonic()
    try:
        results = run_all(studio, args.only, budget=budget)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    wall = time.monotonic() - started
    code = exit_code_for(results)

    if args.json:
        print(json.dumps({
            "studio": str(studio),
            # `ok` keeps meaning "every probe passed", so a reader written
            # against the two-outcome payload cannot start counting UNKNOWNs
            # as green. `status` and the counts are where the third outcome
            # lives, and `exit_code` is carried so nothing has to infer it.
            "ok": not failures(results) and not unknowns(results),
            "status": (
                STATUS_FAIL if failures(results)
                else STATUS_UNKNOWN if unknowns(results)
                else STATUS_PASS
            ),
            "exit_code": code,
            "passed": len(passes(results)),
            "failed": len(failures(results)),
            "unknown": len(unknowns(results)),
            "wall_clock_seconds": round(wall, 3),
            "time_budget_seconds": budget,
            "fast": bool(args.fast),
            "within_budget": wall <= budget,
            "results": [result.as_dict() for result in results],
        }, indent=2))
        return code

    print(f"  studio: {studio}")
    print(format_report(results, budget=budget))
    print(f"  wall clock: {wall:.1f}s")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
