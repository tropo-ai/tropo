#!/usr/bin/env python3
"""Contract-first plants for ``vault/tools/tropo-smoke.py``, cut from af6c53df.

WHY THIS FILE IS RED TODAY
--------------------------
``vault/tools/tropo-smoke.py`` does not exist. That is the point. This crew has
repeatedly lost days to a suite written *against* an implementation: the tests
pass, the behaviour is wrong, and the green suite is what stops anyone looking.
Every case below was cut from af6c53df's AC1-AC7 and R1-R3 and from the frozen
surface in ``vault/tools/SMOKE-SURFACE.md`` **before** the build, in a lane that
never sees the implementation. The module load directly beneath this docstring
fails loudly and exactly once; nothing here is stubbed, mocked or weakened to
manufacture green.

THE CONTRACT SURFACE THESE PLANTS PIN (SMOKE-SURFACE.md, Talos T37, frozen)
--------------------------------------------------------------------------
::

    OPERATIONS: tuple[str, ...] = ("boot", "mint", "index", "commit", "build",
                                   "orient")
    TIME_BUDGET_SECONDS = 120                      # AC7 as amended
    FAST_BUDGET_SECONDS = 30                       # AC7's original promise
    STATUS_PASS / STATUS_FAIL / STATUS_UNKNOWN     # AC7a
    ProbeResult(operation, status, detail, cure, elapsed_s, evidence) # frozen
        .ok       -> status == "pass"   (derived, read-only)
        .failed   -> status == "fail"
        .unknown  -> status == "unknown"
    failures(results) / unknowns(results) / passes(results)
    exit_code_for(results) -> int
    probe_boot / probe_mint / probe_index / probe_commit / probe_build /
        probe_orient (studio: Path) -> ProbeResult
    PROBES: dict[str, Callable[[Path], ProbeResult]]   # keyed by OPERATIONS
    run_all(studio, only=None, budget=None) -> list[ProbeResult]
    format_report(results, budget=None) -> str
    main(argv=None) -> int  # CLI: [--only OP] [--fast] [--json] [--studio PATH]

THE SIXTH OPERATION (2026-07-31, ORIENTTests)
---------------------------------------------
``orient`` was added to OPERATIONS after Metis G98 wired the shipped
``orient()`` to this Studio's real surfaces and found it could not run at all:
it failed closed at the visibility floor with ``GROUP_RESOLUTION_UNAVAILABLE``
before a circle was drawn, before anything was ranked. Her note is the mandate:
"A capability can be fully built, fully tested, fully green, and structurally
unable to run on the machine it was built for, and nothing we own says a word."
Its cases live in ``ORIENTTests`` and every one of them is a state a studio can
genuinely be in, applied to a copy.

THE MATCHED EMPTY-CIRCLE PAIR, AND WHY BOTH PLANTS WERE REWRITTEN (2026-08-01)
------------------------------------------------------------------------------
``test_orient_fails_on_an_empty_circle_over_readable_substrate`` and
``test_orient_reports_unknown_when_nothing_is_inside_the_audience`` are one
branch read from both sides, and each was passing over a studio its plant had
not actually broken. The probe was right both times; the plants were wrong, in
two different ways, and both are recorded at the plant rather than paved over:

* **The rot plant wrote where the reader reads and still missed a node.**
  ``SqliteStructuralIndex.structure`` does read ``decay`` out of
  ``entries.fm_json``, and 174 of the fixture's 175 rows were gated correctly.
  The survivor had no row: this fixture is twelve governed files whose
  frontmatter cites hundreds of UIDs, so 136 of its 311 graph nodes are
  edge-only, ``structure`` returns ``None`` for them, and ``draw_circle`` reads
  ``decay`` off that ``None``. The plant now materialises the row the LIVE
  index already carries for those UIDs before writing the verdict, and reports
  what it failed to reach so the case can refuse to run over a partial plant.
* **The audience plant's premise about `private` was false.** The installed
  authority declares ``legacy_aliases: {"private": "b2e8d914"}``, and
  ``b2e8d914`` is one of the four segments the widest principal reads - so
  scoping every entry ``private`` moved nodes between two readable segments and
  changed nothing. The plant now empties the audience through
  ``derive_segment``'s vault-node branch instead.

Neither assertion was relaxed. Both cases gained a control that fails loudly if
the plant no-ops, because a plant that silently reaches nothing is precisely
what made them green.

THREE ORIENT STATES, NOT TWO, BECAUSE THEY HAVE DIFFERENT OWNERS (2026-08-01)
------------------------------------------------------------------------------
Argus A143, endorsed by Metis: "``no-corpus``, ``corpus-but-no-authority`` and
``authority-installed-but-still-refusing`` have different OWNERS, so collapsing
them into one UNKNOWN reproduces the failure the probe exists to catch." One
case per state
(``test_orient_state_no_corpus_belongs_to_the_index_rebuilder``,
``..._corpus_but_no_authority_belongs_to_one_human_once``,
``..._still_refusing_belongs_to_the_retrieval_path``), plus two that hold the
line between them: the cube of
(corpus, authority, answered) is required to be partitioned by the three, and
every stage the driver can emit is required to land on exactly one state or on
no state deliberately.

Each of the three carries a control that fails loudly if its plant no-ops, and
they are written as the OTHER states' negations rather than as a check that
something changed: the no-authority case asserts the CORPUS still reads, and
the still-refusing case asserts both the corpus and the authority survived.
That is what makes them cases about one state rather than three cases that
would all pass over the same broken studio.

Being unable to LOOK is deliberately none of the three, and
``assertNoOrientState`` pins that: a clock that ran out, an authority naming no
principal, an audience covering nothing. Those have no owner in the Studio, and
a fourth label for them would re-collapse the distinction.

ADR-065 (``0a5d562d``) landed the same day and superseded the probe's framing:
identity and authority are resident in the STUDIO, which is portable, and the
record travels with the vault. ``test_orient_never_says_the_authority_is_a_
property_of_the_hardware`` bars the machine-local vocabulary from the ORIENT
source and from what the probe prints. Machine language about PROVISIONING
survives on purpose - "this machine has not installed PyYAML" is true.

TWO RATIFIED AMENDMENTS, AND WHAT THEY CHANGED IN THIS FILE (2026-07-31)
------------------------------------------------------------------------
This suite was cut contract-first, before the implementation existed, against
AC7 as originally written. Metis G98 then ran the first build live and amended
the spec twice. Both amendments invalidate cases here, and the cases were
updated rather than argued with, because the spec moved under them:

* **AC7 amended.** The budget default is 120s and 30s survives as ``--fast``.
  ``test_ac7_the_budget_is_thirty_seconds`` asserted the old number and is
  replaced by ``test_ac7_the_default_budget_is_120_and_thirty_is_fast``. The
  whole-run timing case now measures against the FAST budget, because relaxing
  it to 120 against a 15-entry fixture would have removed its teeth: a fixture
  this small must still clear the strict promise.
* **AC7a: TIMEOUT IS NOT FAILURE.** Every case here was written when a probe
  had two outcomes, and several assert "not ok" where they mean "found a
  problem". ``assertProbeFails`` is now strict — it requires
  ``status == "fail"`` — and a sibling ``assertProbeUnknown`` carries the third
  outcome. The one generic case that legitimately accepts either
  (``test_ac4_a_failing_probe_prints_...``, which iterates whatever failed)
  uses the shared ``assertNotPassing`` instead. Making the plants strict is a
  STRENGTHENING: a probe that laundered a determined break into UNKNOWN to
  keep the run green would now redden ten cases.

Nothing here was relaxed to fit the implementation. ``AC7aThirdOutcomeTests``
and ``AC7BudgetAmendmentTests`` were added for the new behaviour, and each of
their cases was mutation-proven against a mutant that breaks the specific thing
it claims to cover.

WHAT THE FIVE BREAKS LOOK LIKE ON DISK, AND WHERE EACH ONE IS REPLAYED
----------------------------------------------------------------------
AC5 is the bar. Each replay below constructs the broken condition out of real
substrate and asserts the probe reports failure *with a useful cure*.

* **Break 1 - the G2 identity gate** (19 agents unbootable for three days).
  ``AC5PlantTests.test_ac5a_g2_identity_gate_blocked_nineteen_agents_from_birth``
  strips ``agent_public_key`` from the terminal generation of a lineage that has
  been keyed since G2, which is the exact condition
  ``authority_chain.derive_new_activation_predecessor`` refuses on.
* **Break 2 - fresh-clone index refusal.**
  ``AC5PlantTests.test_ac5b_fresh_clone_index_creation_refuses_on_a_dirty_file``
  gives ``probe_index`` a checkout with no index, no seal and a dirty governed
  file - the state every new machine starts in.
* **Break 3 - 059f2c68's raw-vs-filtered byte comparison** (minting broken
  studio-wide). ``AC5PlantTests.test_ac5c_*`` runs the commit and mint probes
  against a studio whose governed bodies carry nav blocks **rendered by the
  studio's own renderer**, with the clean filter installed. Worktree bytes and
  the staged blob genuinely differ there; a probe that compares raw bytes to the
  blob refuses legitimate work, which is what 059f2c68 did to every used studio
  while passing CI on a fresh checkout.
* **Break 8 - the gitignored per-machine digest** (three validator gates
  reporting ``0 rows checked`` and PASS). ``R1IndexSawSomethingTests`` drifts the
  index surfaces away from the seal in ``.tropo-studio/locks/`` and requires
  ``probe_index`` to fail rather than report success over an empty world.
* **Break 9 - 2dcadf62's digest tag rename** (index authority deadlocked
  studio-wide for 2h17m). ``AC5PlantTests.test_ac5_break9_*`` forges the pair
  digest, which reproduces the measured deadlock exactly - both
  ``tropo-rebuild-index.py --apply`` and ``--only`` exit 1 - and then *runs the
  cure the probe printed* and requires the studio to recover. A repair path
  gated behind the check it broke is the whole of break 9.

R3 (the successor's birth, not the retiring agent's checklist) is replayed in
``R3SuccessorBirthTests`` from the incident of 2026-07-31: Argus A142 finished
retiring while his activation entry ``b8a9f6fe`` still said ``status: active``
- which would have HALTED A143 at the ADR-016 hard gate - and his transfer stub
``6132a8bb`` was invisible to the index, so the successor's first act read
through an unindexed pointer.

THE FIXTURE IS A USED STUDIO, AND IT IS BUILT BY USING ONE (R2, AC6-adjacent)
-----------------------------------------------------------------------------
*An instrument that constructs its own world will always find that world in
order.* So no fixture here is authored: each one is a copy of real substrate
from the studio this file lives in - real governed entries, a real keyed
activation lineage, the real capsules, the real toolchain - and it is then
**used**: committed, rendered through ``tropo-generate-relations-header.py``
(which is what puts nav blocks on disk), indexed through
``tropo-rebuild-index.py --apply`` (which is what stamps the per-machine seal),
with the nav-block clean filter installed. Only then is it broken.

Measured while writing this suite, and worth recording: **this checkout has zero
rendered nav blocks.** Every `nav-block:start` in ``vault/files/`` today is prose
quoting the sentinel. A fixture copied from it raw is precisely the studio nobody
has ever used that let 059f2c68 through, which is why the render step is not
optional here.

AC6 - the used-studio fixture as a committed, shared artifact under
``vault/tools/tests/fixtures/used-studio/`` - is **Argus's lane** per af6c53df
§Lanes, and is deliberately not half-built here. What this file carries is the
minimum a contract test needs: a studio with a yesterday in it, built at runtime,
never committed.

DISCIPLINE
----------
Hermetic and non-destructive. Nothing in this file writes to the live studio; a
guard in ``SmokeCase.tearDown`` and in ``tearDownModule`` re-checks that after
every test, because the one way a probe could damage this studio is by resolving
the *live* toolchain while pointed at a fixture. No network (process-wide socket
guard, the sibling-suite idiom). Scratch lives in ``tempfile`` and is removed.

A SIXTH BREAK, MEASURED WHILE WRITING THIS SUITE AND NOT IN THE SPEC
--------------------------------------------------------------------
``tropo-recycle.py`` rewrites the index seal and the manifest it leaves behind
has dropped the ``@repo-clock`` and ``@wall-clock-date`` virtual inputs. Every
incremental ``tropo-rebuild-index.py --only`` afterwards refuses - *"semantic
derivation inputs changed outside the owned target"* - until somebody runs a
full ``--apply``. Reproduced on a clean fixture in four commands; the full
``--apply`` restores the virtuals and unblocks ``--only``.

That is break 9's exact shape (a write path leaving a seal the read path
refuses) sitting directly across operations 2 and 3, because MINT must recycle
its throwaway and INDEX runs next.
``AC1FiveProbesTests.test_ac1_all_five_go_green_on_a_studio_that_is_actually_working``
is where it lands. The contract does not say how to handle it; it does say all
five pass on a working studio.

THREE THINGS THE SPEC ASKS FOR THAT NO IMPLEMENTATION CAN GIVE, RECORDED NOT HIDDEN
-----------------------------------------------------------------------------------
1. **AC2's "run it twice and diff the tree - byte-identical" cannot hold for a
   probe that really mints.** The sanctioned soft-delete gesture moves the
   throwaway to ``recycle/agent-deletions/<date>/<uid>.md`` and appends a log
   line; a second run mints a second uid and leaves a second file. The only way
   to a byte-identical tree is to skip the recycle gesture (forbidden) or to skip
   the mint (the probe's whole job). So ``AC2NonDestructiveTests`` asserts the
   invariant that is actually load-bearing - every governed plane byte-identical,
   the index row set unchanged, git state unchanged, no stray path outside a
   sanctioned plane - and asserts the recycle bin grew, because that growth is
   the *evidence* the probe did the work. The planes are whitelisted in
   ``GOVERNED_PLANES`` rather than blacklisted, because a blacklist forgives
   every derived surface somebody adds next quarter.
2. **AC2's "never rm over a governed path" cannot be settled by an AST scan.**
   A probe legitimately removes its own scratch file, and that scratch file
   legitimately lives under ``vault/files/`` so the clean filter and the parser
   see it the way they see everything else. ``rmtree(tmpdir)`` and
   ``rmtree(studio / 'vault' / 'files' / uid)`` are the same call. The scan here
   is scoped to deletes that visibly reach for the studio, and the weight is
   carried by
   ``AC2NonDestructiveTests.test_ac2_a_governed_entry_that_looks_like_a_throwaway_still_survives``
   - a decoy entry, mint-shaped and stamped with the probe's own author, planted
   before the run and required to survive it. A probe that tidies up by sweeping
   rather than by recycling the uid it minted eats the decoy; nothing structural
   can see that.
3. **AC7's 30 seconds is asserted against the fixture, not against this studio.**
   A contract test cannot time a 4,293-entry vault it is forbidden to touch.

One spec claim is deliberately NOT encoded: the story that a K/cap ruling sat
unread on main for 3.5 hours. It was a timezone misreading - the ruling landed 26
minutes *after* the question (commit e92f158f). It is not a break and nothing
here replays it.
"""
from __future__ import annotations

import ast
import atexit
import contextlib
import dataclasses
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import typing
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
TOOLS_DIR = TESTS_DIR.parent
LIVE_STUDIO = TOOLS_DIR.parent.parent

# The build under contract. Absent today: this is the one loud failure the whole
# suite is designed to produce, and it is the correct end state.
#
# TROPO_SMOKE_PATH is the mutation-testing seam, and it exists for one reason:
# Talos's own practice of mutation-testing a green suite and reporting which
# cases have teeth needs somewhere to point. CI sets nothing and gets
# vault/tools/tropo-smoke.py.
SMOKE_PATH = Path(
    os.environ.get("TROPO_SMOKE_PATH") or (TOOLS_DIR / "tropo-smoke.py")
).resolve()


def _load_module_under_contract():
    """Load the hyphenated tool by path - the house idiom for vault/tools/*.py.

    Raises rather than skipping when the module is absent. A contract suite that
    skips itself into green is the failure mode this file exists to prevent.
    """
    import importlib.util

    if not SMOKE_PATH.is_file():
        raise ModuleNotFoundError(
            f"the module under contract does not exist yet: {SMOKE_PATH}. "
            "This suite was cut from af6c53df + SMOKE-SURFACE.md before the "
            "build, on purpose. Red here is the correct state until Talos "
            "lands tropo-smoke.py; do NOT stub the module to clear it."
        )
    spec = importlib.util.spec_from_file_location("tropo_smoke_under_contract", str(SMOKE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = _load_module_under_contract()


# --------------------------------------------------------------------------- #
# Process-wide network guard - the sibling-suite idiom (test_orient_stage_c).   #
# A liveness probe that needs the network is not a liveness probe. This binds   #
# the test process only; the probes' own subprocesses are audited by AC3's AST  #
# scan instead.                                                                 #
# --------------------------------------------------------------------------- #
_SOCKET_PATCHERS = (
    mock.patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket.socket,
        "connect",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket.socket,
        "connect_ex",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket,
        "socket",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
)


# --------------------------------------------------------------------------- #
# Real substrate the fixtures are cut from.                                     #
# --------------------------------------------------------------------------- #

# A real keyed lineage (keys began at G2, which is what break 1 was about) plus
# the two entries from the 2026-07-31 retirement incident R3 names.
LINEAGE_ENTRIES = (
    "f3b263b3",  # metis G96, retired, keyed
    "8aafbfbb",  # metis G97, retired, keyed
    "39457c1d",  # metis G98, keyed - flipped to retired by the fixture builder
    "b8a9f6fe",  # argus A142, retired, declares transfer_uid: 6132a8bb
    "6132a8bb",  # the auto-generated transfer stub that was invisible to the index
)

# Real governed entries, including the spec under contract and the finding that
# added R1-R3. A fixture that carries the spec that demands it is not a mock.
CONTENT_ENTRIES = (
    "af6c53df",  # the dev-spec these plants are cut from
    "1f29bcfb",  # "Instruments that report green while blind" - breaks 8 and 9
    "132fb547",
    "391043ad",
    "69ea3f38",
    "6ec30708",  # the nav-block clean-filter spec itself
    "76bab75f",
)

# Bulk, for R1's scaling differential: rows_checked must move with the studio.
BULK_ENTRIES = (
    "13360e43", "28a759d2", "2e4feb56", "319ddd57", "3e8f6f79", "62319989",
    "942c1178", "ed07f435", "f82f1ab0", "f8cb4cc9", "1496bdd0", "1714f658",
    "39db7ee4", "9c77725f", "ca2dd64f", "088a282f", "9597cc60", "9bdce037",
    "a6fe0bad", "b91d4f20", "3fbdedd8", "5c0c4751", "7f746921", "b651035b",
)

METIS_SUCCESSOR_ENTRY = "39457c1d"
ARGUS_ENTRY = "b8a9f6fe"
REAL_TRANSFER_STUB = "6132a8bb"
ORPHAN_TRANSFER_UID = "5eb00001"  # 8-hex, deliberately absent from every index

# AC2 is stated as "run it twice and diff the tree, byte-identical", and the
# tree is not all one thing. These are the planes that must not move: the Vault,
# the status cards, the type system minting reads, the toolchain every probe
# drives, the OS invariants, the cockpit manifest. Whitelisted rather than
# blacklisted on purpose - a blacklist silently forgives every derived surface
# somebody adds next quarter, and the first draft of this file did exactly that
# until `.tropo-studio/gardener-wall-clock.json` appeared mid-run.
GOVERNED_PLANES = (
    "vault/files",
    "vault/agents",
    "vault/capsules",
    "vault/tools",
    ".tropo",
    "tropo-app",
    "STUDIO.md",
    ".gitattributes",
    ".gitignore",
)

# `.tropo-studio/` mixes governed markdown (CAPSULE.md, the operating
# principles) with three per-machine derived surfaces. Only the markdown is
# governed content.
GOVERNED_GLOBS = ((".tropo-studio", "*.md"),)

# Everything a probe is allowed to write or churn. `recycle/` is here because
# the sanctioned soft-delete writes there and nowhere else, which makes its
# growth the *evidence* the mint probe did its job rather than damage; the rest
# are disposable projections of the governed planes above. Requiring
# `vault/00-index.jsonl` to be byte-stable would forbid the INDEX operation.
SANCTIONED_CHURN = (
    ".git/",
    "__pycache__/",
    "recycle/",
    "vault/00-",
    ".tropo-studio/locks/",
    ".tropo-studio/shards/",
    ".tropo-studio/dirty-counter.json",
    ".tropo-studio/gardener-wall-clock.json",
    "00-tropo-nav/",
)


def _is_derived(relative: str) -> bool:
    return any(
        relative.startswith(prefix) or f"/{prefix}" in f"/{relative}"
        for prefix in SANCTIONED_CHURN
    )


def census(root: Path) -> dict:
    """Content census of one directory: relative path -> sha256 of the bytes.

    Paths AND bytes, so a new file, a deleted file and an edited file are all
    caught by one equality assertion.
    """
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file() or "__pycache__" in path.parts:
            continue
        result[path.relative_to(root).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


def governed_census(studio: Path) -> dict:
    """Census of the planes AC2 forbids a probe to move."""
    result = {}

    def take(path: Path) -> None:
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts:
            result[path.relative_to(studio).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()

    for plane in GOVERNED_PLANES:
        target = studio / plane
        if target.is_file():
            take(target)
        elif target.is_dir():
            for path in sorted(target.rglob("*")):
                take(path)
    for folder, pattern in GOVERNED_GLOBS:
        for path in sorted((studio / folder).glob(pattern)):
            take(path)
    return result


def tree_paths(studio: Path) -> set:
    """Every path in the studio, so an unsanctioned NEW file cannot hide in a
    plane the governed census does not walk."""
    return {
        path.relative_to(studio).as_posix()
        for path in studio.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
    }


def index_rows(studio: Path) -> dict:
    """The index union as {uid: row}, read the way the Vault says to read it."""
    rows = {}
    for name in ("00-index.jsonl", "00-archive-index.jsonl"):
        path = studio / "vault" / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("uid"):
                rows[row["uid"]] = row
    return rows


# The rendered region, not the sentinel. Governed prose quotes
# `<!-- nav-block:start -->` all over this vault - 6ec30708 IS the clean-filter
# spec and mentions it five times - and a plant that counted sentinels would
# call a fresh checkout a used studio.
NAV_BLOCK_RE = re.compile(
    rb"^<!-- nav-block:start -->\n.*?^<!-- nav-block:end -->\n*",
    re.DOTALL | re.MULTILINE,
)


def nav_blocked(studio: Path) -> list:
    """Governed files carrying a nav block the studio's own renderer put there.

    A used studio has these; a fresh checkout does not. Which files get one is
    the renderer's business (it walks member_of/subsystem_hub through the
    index), so the plants ask the fixture rather than naming a uid and going
    stale.
    """
    return [
        path
        for path in sorted((studio / "vault" / "files").glob("*.md"))
        if NAV_BLOCK_RE.search(path.read_bytes())
    ]


def git(studio: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(studio), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def git_state(studio: Path) -> str:
    """Porcelain status with the derived planes dropped.

    The INDEX operation rewrites ``vault/00-*`` and the seal, and the sanctioned
    soft-delete writes ``recycle/``; requiring those to be byte-stable would
    forbid two of the five operations outright. Everything git can still see
    here is governed, and must not move.
    """
    lines = []
    for line in git(studio, "status", "--porcelain").stdout.splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        if not _is_derived(path):
            lines.append(line)
    return "\n".join(lines)


def frontmatter_set(path: Path, field: str, value: str) -> None:
    """Set one top-level frontmatter scalar, or append it, byte-surgically.

    Deliberately regex-thin rather than a YAML round-trip: a round-trip would
    rewrite the whole file and destroy the "real substrate, minimally bent"
    property the fixtures depend on.
    """
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(field)}:.*$", re.MULTILINE)
    if pattern.search(text):
        path.write_text(pattern.sub(f"{field}: {value}", text, count=1), encoding="utf-8")
        return
    end = text.index("\n---", 3)
    path.write_text(text[:end] + f"\n{field}: {value}" + text[end:], encoding="utf-8")


def frontmatter_drop(path: Path, field: str) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(
        re.sub(rf"^{re.escape(field)}:.*\n", "", text, count=1, flags=re.MULTILINE),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# The used-studio fixture. Copied from real substrate, then USED: committed,    #
# rendered, indexed, sealed, with the clean filter wired.                       #
# --------------------------------------------------------------------------- #

_TEMPLATES: dict = {}
_TEMP_ROOTS: list = []


def _scratch(prefix: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix=f"tropo-smoke-{prefix}-"))
    _TEMP_ROOTS.append(root)
    return root


@atexit.register
def _cleanup_scratch() -> None:
    for root in _TEMP_ROOTS:
        shutil.rmtree(root, ignore_errors=True)


class FixtureUnavailable(Exception):
    """The live studio could not lend the substrate a used studio needs."""


def _copy_substrate(dest: Path, entries) -> None:
    (dest / "vault" / "tools" / "lib").mkdir(parents=True)
    (dest / "vault" / "files").mkdir(parents=True)
    (dest / "vault" / "agents").mkdir(parents=True)
    (dest / ".tropo").mkdir()
    (dest / ".tropo-studio").mkdir()

    for script in sorted((LIVE_STUDIO / "vault" / "tools").glob("*.py")):
        shutil.copy2(script, dest / "vault" / "tools" / script.name)
    for module in sorted((LIVE_STUDIO / "vault" / "tools" / "lib").glob("*.py")):
        shutil.copy2(module, dest / "vault" / "tools" / "lib" / module.name)
    shutil.copytree(LIVE_STUDIO / "vault" / "capsules", dest / "vault" / "capsules")

    missing = []
    for uid in entries:
        source = LIVE_STUDIO / "vault" / "files" / f"{uid}.md"
        if not source.is_file():
            missing.append(uid)
            continue
        shutil.copy2(source, dest / "vault" / "files" / f"{uid}.md")
    if missing:
        raise FixtureUnavailable(
            f"real substrate absent from {LIVE_STUDIO}: {', '.join(missing)}"
        )

    for card in sorted((LIVE_STUDIO / "vault" / "agents").glob("*.md")):
        shutil.copy2(card, dest / "vault" / "agents" / card.name)
    for governance in sorted((LIVE_STUDIO / ".tropo").glob("*.md")):
        shutil.copy2(governance, dest / ".tropo" / governance.name)
    for studio_file in sorted((LIVE_STUDIO / ".tropo-studio").glob("*.md")):
        shutil.copy2(studio_file, dest / ".tropo-studio" / studio_file.name)
    for root_file in ("STUDIO.md", ".gitattributes", ".gitignore", "requirements.txt"):
        source = LIVE_STUDIO / root_file
        if source.is_file():
            shutil.copy2(source, dest / root_file)

    _lend_the_group_authority(dest)

    # The cockpit, reduced to the two things operation 5 can ask about: the
    # studio's own declared way to typecheck itself, and an installed
    # typechecker to run. A real Next.js tree is 1.6 GB and copying it would
    # make the suite unrunnable, so the compiler is a stub that exits 0 - but it
    # is INSTALLED, at the path the real cockpit installs it to, with the real
    # cockpit's script name and command. A fixture that declares `tsc --noEmit`
    # and ships no tsc is a checkout nobody has ever built, which is the same
    # mistake as a fixture with no nav blocks, one plane over.
    app = dest / "tropo-app"
    bin_dir = app / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (app / "package.json").write_text(
        json.dumps(
            {
                "name": "tropo-app-fixture",
                "private": True,
                "scripts": {"typecheck": "tsc --noEmit"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    typechecker = bin_dir / "tsc"
    typechecker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    typechecker.chmod(0o755)


# The installed group authority and the registry that resolves against it.
#
# Both are STUDIO-RESIDENT and both are corpus-root relative, so a copy of the
# directories IS an installed authority - which is the same reason a clone of
# this vault arrives already knowing who everyone is. That sentence used to
# read "machine-local artifacts written by the ceremony"; ADR-065 (0a5d562d)
# retired the claim: authority is resident in the Studio, the Studio is
# portable, and hardware is not a participant.
AUTHORITY_DIR = ".tropo-studio/authorities"
GROUP_REGISTRY_FILES = (
    "vault/00-group-registry.jsonl",
    "vault/00-group-registry-wrapper.json",
    "vault/00-group-registry.sqlite",
)


def _lend_the_group_authority(dest: Path) -> None:
    """Copy the live studio's installed group authority into the fixture.

    ORIENT is the first operation that cannot run without one, so a fixture
    with no authority is a Studio that never had one installed - and every
    ORIENT case against it would come back UNKNOWN for that reason alone,
    including the ones meant to prove it can PASS.

    Copied rather than installed, and that is the same call ``_copy_substrate``
    makes for capsules and tooling: R2 says the instrument may not construct
    the world it inspects, so the fixture borrows a real one. Copying is also
    the honest gesture under ADR-065, because copying is exactly how a real
    Studio acquires one - the record travels with the vault. Installing one
    here would need ``cryptography``, a signing key and four steps a human is
    supposed to take, and it would produce an authority nobody has ever
    installed. The counterpart - proving an ABSENT authority reports UNKNOWN -
    is ``break_missing_group_authority`` on a copy.

    Fails loudly rather than skipping the copy. A fixture that silently loses
    its authority would turn every ORIENT case green-adjacent (UNKNOWN is not
    a pass, but it is not the failure the case was written to catch either).
    """
    source = LIVE_STUDIO / AUTHORITY_DIR
    if not (source / "group-authority" / "installed.json").is_file():
        raise FixtureUnavailable(
            f"{LIVE_STUDIO} has no installed group authority to lend; ORIENT "
            "cannot be exercised past the authority gate from here"
        )
    shutil.copytree(source, dest / AUTHORITY_DIR, dirs_exist_ok=True)

    lent = False
    for relative in GROUP_REGISTRY_FILES:
        candidate = LIVE_STUDIO / relative
        if candidate.is_file():
            destination = dest / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, destination)
            lent = True
    if not lent:
        raise FixtureUnavailable(
            "the live studio publishes no group registry; visibility cannot "
            "resolve in a fixture cut from it"
        )


def _run_tool(studio: Path, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(studio),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _index(studio: Path, *args: str) -> None:
    built = _run_tool(studio, "vault/tools/tropo-rebuild-index.py", "--apply", *args)
    if built.returncode != 0:
        raise FixtureUnavailable(
            f"index build refused: {(built.stderr or built.stdout)[-800:]}"
        )


def _use_the_studio(studio: Path, *, render: bool, build_index: bool) -> None:
    """Turn a checkout into a studio somebody has used.

    Every step is load-bearing and two of them were learned the hard way.

    * The clean filter goes in before the render is committed, so the nav blocks
      stay on disk and out of the object store. That worktree/blob divergence is
      the exact thing 059f2c68 mistook for corruption, and a fixture without it
      cannot see break 3.
    * The index is built BEFORE the render, because the renderer resolves
      breadcrumb chains through the index: run against an unindexed tree it
      renders 5 of these files, run against an indexed one it renders 12 -
      including every activation entry. Rendering first produces a studio whose
      lineage entries carry no nav block, which is a fresh checkout wearing a
      used studio's clothes.
    * The index is then rebuilt, because the render commit moves the repo clock
      and the trusted derivation manifest pins it. Skip this and every
      incremental ``--only`` in the fixture refuses before a probe touches it.
    """
    git(studio, "init", "-q")
    git(studio, "config", "user.email", "smoke@fixture.invalid")
    git(studio, "config", "user.name", "smoke fixture")
    git(studio, "config", "commit.gpgsign", "false")
    git(studio, "add", "-A")
    git(studio, "commit", "-q", "-m", "fixture: substrate as checked out")

    installed = _run_tool(studio, "vault/tools/tropo-navblock-strip.py", "--install")
    if installed.returncode != 0:
        raise FixtureUnavailable(f"clean filter would not install: {installed.stderr}")

    if build_index:
        _index(studio)

    if render:
        rendered = _run_tool(
            studio, "vault/tools/tropo-generate-relations-header.py",
            "vault/files", "--write",
        )
        if rendered.returncode != 0:
            raise FixtureUnavailable(f"renderer failed: {rendered.stderr[-800:]}")
        git(studio, "add", "-A")
        commit = git(studio, "commit", "-q", "-m", "fixture: rendered nav surfaces", check=False)
        if commit.returncode not in (0, 1):
            raise FixtureUnavailable(f"render commit failed: {commit.stderr}")
        if build_index:
            _index(studio)


def _build_template(name: str) -> Path:
    root = _scratch(f"template-{name}")
    studio = root / "studio"
    studio.mkdir()

    entries = LINEAGE_ENTRIES + CONTENT_ENTRIES
    if name == "bigger":
        entries = entries + BULK_ENTRIES
    _copy_substrate(studio, entries)

    successor = studio / "vault" / "files" / f"{METIS_SUCCESSOR_ENTRY}.md"
    card = studio / "vault" / "agents" / "9fc001c3.md"

    if name != "fresh-clone":
        # The retirement, as the retiring agent's own checklist leaves it: the
        # status card closed, the transfer written, the entry stamped. Whether
        # the ENTRY reached a terminal status is the variable R3 is about.
        frontmatter_set(successor, "retired_at", "'2026-07-31'")
        frontmatter_set(successor, "closure_reason", '"clean-retirement"')
        frontmatter_set(successor, "transfer_uid", REAL_TRANSFER_STUB)
        if card.is_file():
            frontmatter_set(card, "status", "RETIRED")

    if name == "active-at-handoff":
        # The 2026-07-31 incident, exactly: everything else about the retirement
        # is done and the activation entry still says active.
        frontmatter_set(successor, "status", "active")
    elif name != "fresh-clone":
        frontmatter_set(successor, "status", "retired")

    if name == "unkeyed-successor":
        # Break 1. The lineage has been keyed since G2 (G96 and G97 both carry
        # agent_public_key); the terminal generation does not. Stripped BEFORE
        # the first commit so this is a lineage that was never keyed at the tip,
        # not an entry whose identity changed under git - a different defect.
        frontmatter_drop(successor, "agent_public_key")

    if name == "fresh-clone":
        # Break 2's world: a git checkout, nothing rendered, no index, no seal -
        # and one dirty governed file, which is all it took to refuse index
        # creation on every new machine since the ratchet landed.
        _use_the_studio(studio, render=False, build_index=False)
        dirty = studio / "vault" / "files" / f"{CONTENT_ENTRIES[0]}.md"
        dirty.write_text(
            dirty.read_text(encoding="utf-8") + "\n<!-- uncommitted local edit -->\n",
            encoding="utf-8",
        )
    else:
        _use_the_studio(studio, render=True, build_index=True)

    return studio


def template(name: str) -> Path:
    if name not in _TEMPLATES:
        _TEMPLATES[name] = _build_template(name)
    return _TEMPLATES[name]


def studio_copy(name: str = "used") -> Path:
    """An independent copy of a prebuilt used studio, cheap enough to break."""
    destination = _scratch(f"case-{name}") / "studio"
    shutil.copytree(template(name), destination, symlinks=True)
    return destination


# --------------------------------------------------------------------------- #
# The breaks, applied to a copy.                                                #
# --------------------------------------------------------------------------- #

def break_stale_seal(studio: Path) -> None:
    """Break 8. The per-machine seal in .tropo-studio/locks/ no longer describes
    what is on disk - the state an unknown number of machines were in
    simultaneously, because .gitignore:44 keeps that directory local."""
    surface = studio / "vault" / "00-index.jsonl"
    lines = surface.read_text(encoding="utf-8").splitlines(keepends=True)
    surface.write_text("".join(lines[:-1]), encoding="utf-8")


def break_forged_seal(studio: Path) -> None:
    """Break 9's terminal state: a pair digest that matches no format the writer
    has ever emitted. Readers refuse, and the rebuild that would re-stamp the
    seal is gated behind the same check - the deadlock 2dcadf62 shipped."""
    meta = studio / ".tropo-studio" / "locks" / "index-surfaces.meta.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    data["pair_sha256"] = "0" * 64
    meta.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def break_orphan_transfer(studio: Path) -> Path:
    """R3(b). A transfer stub on disk that the index cannot see, with the
    retiring agent's entry pointing straight at it. The successor's first act is
    to read the transfer; it resolves through the index or not at all."""
    source = studio / "vault" / "files" / f"{REAL_TRANSFER_STUB}.md"
    orphan = studio / "vault" / "files" / f"{ORPHAN_TRANSFER_UID}.md"
    orphan.write_text(
        source.read_text(encoding="utf-8").replace(
            f"uid: {REAL_TRANSFER_STUB}", f"uid: {ORPHAN_TRANSFER_UID}", 1
        ),
        encoding="utf-8",
    )
    frontmatter_set(
        studio / "vault" / "files" / f"{ARGUS_ENTRY}.md",
        "transfer_uid",
        ORPHAN_TRANSFER_UID,
    )
    frontmatter_set(
        studio / "vault" / "files" / f"{METIS_SUCCESSOR_ENTRY}.md",
        "transfer_uid",
        ORPHAN_TRANSFER_UID,
    )
    return orphan


def break_lossy_clean_filter(studio: Path) -> None:
    """A clean filter that eats governed content past the nav block.

    This is the fixture problem pointed at the instrument. A commit probe whose
    scratch content is fresh-checkout-shaped (no nav block) sees a lossless round
    trip here and reports green; only a probe that puts USED-studio content
    through the filter finds the loss. That asymmetry is exactly why 059f2c68
    passed CI.
    """
    program = studio / "vault" / "tools" / "lossy-clean-filter.py"
    program.write_text(
        "import re, sys\n"
        "data = sys.stdin.buffer.read()\n"
        "if b'nav-block:start' in data:\n"
        "    data = re.split(rb'^<!-- nav-block:start -->', data, maxsplit=1, flags=re.M)[0]\n"
        "sys.stdout.buffer.write(data)\n",
        encoding="utf-8",
    )
    git(
        studio,
        "config",
        "filter.navblockstrip.clean",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(program))}",
    )


def break_slow_typecheck(studio: Path) -> None:
    """The cockpit compiles, slowly. Operation 5's UNKNOWN condition.

    `exec` matters and is not cosmetic. Without it the shell stays alive
    holding the stdout pipe, `subprocess.run` kills only the shell, and the
    `communicate()` that follows blocks on the grandchild until it exits - so
    the probe's timeout would silently become a thirty-second wait and the case
    would be measuring the harness rather than the probe.
    """
    typechecker = studio / "tropo-app" / "node_modules" / ".bin" / "tsc"
    typechecker.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    typechecker.chmod(0o755)


def break_unreadable_tip(studio: Path) -> Path:
    """A lineage this instrument cannot READ, which is not a lineage it has
    checked.

    The governed file is replaced by a directory rather than chmod'ed, so the
    case behaves identically for root and for a normal user - a permission
    trick silently becomes a no-op in a container that runs as root, and a
    plant that quietly stops planting is the thing this crew keeps getting
    burned by.
    """
    tip = studio / "vault" / "files" / f"{METIS_SUCCESSOR_ENTRY}.md"
    tip.unlink()
    tip.mkdir()
    return tip


def break_typecheck(studio: Path) -> None:
    """The cockpit stops compiling. Operation 5 is the one that was caught by
    hand on 2026-07-30 and should not have needed a human.

    Broken at the compiler, not at the script, so it is broken for a probe that
    runs `npm run typecheck` and for one that invokes `node_modules/.bin/tsc`
    directly. Which of those a probe does is its business; that the cockpit does
    not compile is the fact it has to report either way.
    """
    typechecker = studio / "tropo-app" / "node_modules" / ".bin" / "tsc"
    typechecker.write_text(
        "#!/bin/sh\n"
        "echo 'app/page.tsx(41,7): error TS2307: cannot find module @/lib/vault' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    typechecker.chmod(0o755)


# --------------------------------------------------------------------------- #
# The ORIENT breaks. Each one is a state a studio can genuinely be in, and each #
# is applied to a copy - never to the live studio, whose authority the fixture  #
# borrowed.                                                                     #
# --------------------------------------------------------------------------- #

def break_missing_group_authority(studio: Path) -> None:
    """State 2: the corpus is here and no authority has been installed FOR THE
    STUDIO.

    Not a broken studio: a Studio nobody has run
    ``tropo-group-authority.py build -> accept-fingerprint -> verify ->
    install`` for yet. Every visibility resolution then fails closed and orient
    cannot start, which is precisely the condition AC7a's third outcome exists
    for.

    ONE act, for the Studio, not one per machine (ADR-065, 0a5d562d). The
    record is tracked and travels with the vault, so this plant is also the
    shape of a vault whose tracked authority went missing - which is why the
    probe's cure names restoring it before it names installing one.

    The corpus is deliberately left alone. "corpus-but-no-authority" is only
    that state if the corpus is still there, and the case that drives this
    plant asserts exactly that before it asserts anything else.
    """
    shutil.rmtree(studio / AUTHORITY_DIR / "group-authority")


def break_group_registry(studio: Path) -> None:
    """State 3: Metis G98's finding, reproduced. The authority IS installed and
    visibility still fails closed.

    The record, the signed generation and the principal directory all survive;
    the resolver's query surface does not. ``visible_segments`` then refuses
    ``GROUP_CORPUS_UNAVAILABLE`` before the first neighbour is looked at -
    orient cannot run at all, on a Studio that has an authority installed.

    The corpus and the authority are both deliberately left intact, because
    this state is only itself if the two rungs below it hold. The case that
    drives this plant reads both back before it reads the verdict.
    """
    removed = False
    for relative in GROUP_REGISTRY_FILES:
        path = studio / relative
        if path.exists():
            path.unlink()
            removed = True
    studio_local = studio / ".tropo-studio" / "registries" / "group-registry.jsonl"
    if studio_local.exists():
        studio_local.unlink()
        removed = True
    if not removed:
        raise FixtureUnavailable("no group registry present to remove")


def break_principal_directory(studio: Path) -> None:
    """The installed authority names nobody this probe could view as.

    The generation's ``principals.jsonl`` no longer has the directory shape, so
    the authority resolves no principal. A probe that invented a viewer to get
    past this would be measuring its own fiction; a probe that reported the
    studio red for it would be blaming the studio for the caller's problem.
    """
    pin = json.loads(
        (studio / smoke.GROUP_AUTHORITY_PIN_REL).read_text(encoding="utf-8")
    )
    generation = studio / str(pin["generation_dir"])
    (generation / "principals.jsonl").write_text(
        '{"not": "a principal directory row"}\n', encoding="utf-8"
    )


def break_orient_library(studio: Path) -> None:
    """The deterministic orient library on THIS studio will not import.

    Substrate damage rather than an unprovisioned machine: the file is here and
    it is wrong. Distinguishing the two is the whole of the import branch.
    """
    (studio / smoke.ORIENT_LIBRARY_REL).write_text(
        "def orient_deterministic(  # planted: unclosed signature\n",
        encoding="utf-8",
    )


def break_orient_into_a_typed_refusal(studio: Path) -> None:
    """The shipped ``orient_deterministic`` refuses with a typed error.

    Shadows the real function at the bottom of the studio's own
    ``lib/distiller.py``, so the probe must be importing and calling THAT
    function for this to change the verdict at all. A probe wired to anything
    else - its own reimplementation, a cached result, a different entry point -
    stays green here, which is what makes this the wiring test.
    """
    library = studio / smoke.ORIENT_LIBRARY_REL
    library.write_text(
        library.read_text(encoding="utf-8")
        + '''

# planted by the suite
from lib.viewer_projection import GraphError as _PlantedError
from lib.viewer_projection import GraphErrorCode as _PlantedCode


def orient_deterministic(task_uid, viewer, budget, **kwargs):
    return Result.failure(
        _PlantedError(_PlantedCode.VISIBILITY_UNRESOLVED,
                      "planted: the crown refuses on this studio")
    )
''',
        encoding="utf-8",
    )


def _index_connection(studio: Path):
    return sqlite3.connect(str(studio / smoke.COMPOSED_INDEX_REL))


# The gardener's verdict as it lands on a swept entry: stale, and confident
# enough to clear `lib/decay_gate.DECAY_GATE_CONFIDENCE` (0.8). The signal
# string is the plant's own marker, so the plant can audit its own reach.
PLANTED_ROT_SIGNAL = "suite-planted-rot"
PLANTED_ROT = {
    "stale": True,
    "confidence": 0.95,
    "signals": [PLANTED_ROT_SIGNAL],
    "reason": "planted by test_tropo_smoke",
}

# Every UID the composed graph exposes as a NODE. Deliberately not
# `SELECT uid FROM entries`: the walk reaches a node through `edges`, and the
# two sets are not the same in a fixture cut from a subset of the vault.
_GRAPH_NODES = (
    "SELECT DISTINCT uid FROM ("
    "  SELECT uid FROM entries"
    "  UNION SELECT src_uid AS uid FROM edges"
    "  UNION SELECT dst_uid AS uid FROM edges"
    ") WHERE uid IS NOT NULL AND uid != ''"
)


class RotPlant(typing.NamedTuple):
    """What the rot plant actually reached — the control the case asserts on.

    ``unflagged`` is the plant auditing its own reach: every node of the
    composed graph, minus the anchor, minus everything now carrying the
    verdict. A non-empty tuple means the plant no-opped on part of the graph
    and an empty circle over it would prove nothing about the decay gate.
    That tuple was 136 UIDs long before this plant was amended, and the case
    it feeds was green anyway — which is the exact failure mode the control
    exists to make loud.
    """

    flagged: int
    materialised: tuple
    unflagged: tuple


def break_everything_rotten_except(studio: Path, keep: str) -> RotPlant:
    """Every node but one carries a high-confidence gardener decay verdict.

    This is the empty-circle condition, produced by the mechanism that produces
    it in the wild rather than by deleting rows. ``filter_visible_uids`` does
    NOT decay-gate, so the probe's own pre-check still reports the anchor's
    neighbours as readable; ``derive_seeds`` and ``draw_circle`` DO, so every
    seed is dropped and the circle comes back empty. Visible substrate, empty
    result - the case the probe has to call a retrieval defect.

    WHY THIS PLANT ALSO MATERIALISES ROWS, which is the amendment and the only
    surprising line in it. The verdict lives in ``entries.fm_json`` and
    ``SqliteStructuralIndex.structure`` reads exactly that key off exactly that
    column, so the write lands where the reader looks - MEASURED: 174 of the
    fixture's 175 rows were gated correctly. The survivor was a node with no
    row at all. This fixture is cut from twelve governed files whose
    frontmatter cites hundreds of UIDs, so 136 of its 311 graph nodes are
    edge-only references; ``structure`` returns ``None`` for those,
    ``draw_circle`` reads ``decay`` off that ``None``, and they are
    structurally un-gateable. The one that survived is ``8dd772a0``, the
    anchor's own ``member_of`` parent - and on the LIVE studio that UID is an
    indexed ``type: project`` entry at ``vault/files/8dd772a0.md`` with a row
    in ``vault/00-index.sqlite``, i.e. a node the gardener sweeps like any
    other. So the row the live index already carries is materialised here
    first, and THEN the real verdict is written to every row through the real
    column. Nothing is deleted, and visibility does not move: a row with no
    ``extraction_scope`` derives the same ``private`` segment the edge-only UID
    already derived through ``safety_net_segment``.
    """
    connection = _index_connection(studio)
    try:
        materialised = tuple(sorted(
            str(row[0]) for row in connection.execute(
                "SELECT DISTINCT uid FROM ("
                "  SELECT src_uid AS uid FROM edges"
                "  UNION SELECT dst_uid AS uid FROM edges"
                ") WHERE uid IS NOT NULL AND uid != '' "
                "AND uid NOT IN (SELECT uid FROM entries)"
            ).fetchall()
        ))
        connection.executemany(
            "INSERT INTO entries (uid, fm_json) VALUES (?, ?)",
            [(uid, json.dumps({"uid": uid})) for uid in materialised],
        )

        rows = connection.execute(
            "SELECT uid, fm_json FROM entries WHERE uid != ?", (keep,)
        ).fetchall()
        for uid, raw in rows:
            try:
                record = json.loads(raw) if raw else {}
            except ValueError:
                record = {}
            if not isinstance(record, dict):
                record = {}
            record["decay"] = PLANTED_ROT
            connection.execute(
                "UPDATE entries SET fm_json=? WHERE uid=?",
                (json.dumps(record), uid),
            )
        connection.commit()

        unflagged = tuple(sorted(
            str(row[0]) for row in connection.execute(
                f"{_GRAPH_NODES} AND uid != ? AND uid NOT IN ("
                "  SELECT uid FROM entries WHERE fm_json LIKE ?"
                ")",
                (keep, f"%{PLANTED_ROT_SIGNAL}%"),
            ).fetchall()
        ))
        return RotPlant(len(rows), materialised, unflagged)
    finally:
        connection.close()


# The vault-node this fixture is made to declare itself as. Eight hex, and
# deliberately NOT a group the installed authority knows - the plant re-reads
# the registry and refuses if that ever stops being true, because a uid that
# quietly became a granted segment would turn the plant into a no-op.
UNGRANTED_VAULT_NODE_UID = "5eb00002"


class AudiencePlant(typing.NamedTuple):
    """What the audience plant moved: which vault-node the studio now declares
    itself to be, and how many graph nodes that segment now covers."""

    vault_node_uid: str
    nodes: int


def break_everything_out_of_the_audience(studio: Path) -> AudiencePlant:
    """Nothing in the studio is inside this viewer's audience.

    THE PREMISE THIS PLANT USED TO CARRY WAS WRONG, and it is worth stating
    because the case it feeds only means something if the mechanism is real.
    It used to set every row's ``extraction_scope`` to ``private`` on the
    theory that "``os`` iff ship, everything else private, and no viewer reads
    private". The second half does not hold on a studio with an installed
    authority. MEASURED on this fixture: the installed generation's
    ``audience-policy.json`` declares ``legacy_aliases: {"private":
    "b2e8d914"}``, ``ViewerProjection`` resolves the derived ``private``
    literal THROUGH that alias, and ``b2e8d914`` is one of the four segments
    the widest principal reads. Scoping everything private moved 136 nodes from
    ``os`` to ``b2e8d914`` and left every one of them readable - the plant was
    a no-op against visibility, and the case passed a full healthy circle.
    (Without that alias every private record is invisible to everyone, owner
    included; that is finding ``401d0702``, and the alias is the fix for it.)

    So the audience is emptied through the OTHER branch of the one true segment
    source. ``lib.segment.derive_segment`` case 1: when the vault root carries
    a ``.tropo/vault-manifest.md``, EVERY node under it derives that
    vault-node's uid as its segment, ahead of any ``extraction_scope``
    reasoning. A studio that declares itself a vault-node the installed group
    authority does not grant is a real state - a forked or newly-minted
    vault-node before the authority is regenerated to cover it - and in it not
    one node of the studio is inside any principal's audience. This is also the
    same lever the walk's own suites use to place a node in a segment
    (``test_viewer_projection._RootFactory.manifest_root``), so the plant and
    the code under test agree about what a segment is.

    An empty circle here is orient behaving CORRECTLY - so the probe must not
    call it a defect.
    """
    manifest = studio / ".tropo" / "vault-manifest.md"
    if manifest.exists():
        raise FixtureUnavailable(
            f"{manifest} already exists; this fixture is already a declared "
            "vault-node and the plant would be measuring the wrong thing"
        )

    granted = set()
    registry = studio / GROUP_REGISTRY_FILES[0]
    if registry.is_file():
        for line in registry.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("group_uid"):
                granted.add(str(row["group_uid"]))
    if UNGRANTED_VAULT_NODE_UID in granted:
        raise FixtureUnavailable(
            f"{UNGRANTED_VAULT_NODE_UID} is a group the installed authority "
            "grants; declaring it as this studio's vault-node would leave "
            "every node READABLE and the plant would be a no-op"
        )

    connection = sqlite3.connect(
        f"file:{studio / smoke.COMPOSED_INDEX_REL}?mode=ro", uri=True
    )
    try:
        nodes = connection.execute(
            f"SELECT COUNT(*) FROM ({_GRAPH_NODES})"
        ).fetchone()[0]
    finally:
        connection.close()

    manifest.write_text(
        "---\n"
        f"uid: {UNGRANTED_VAULT_NODE_UID}\n"
        "type: vault\n"
        "title: a vault-node this authority does not grant\n"
        "---\n\n"
        "Planted by test_tropo_smoke: the studio declares itself a vault-node "
        "whose uid is in no group the installed authority resolves.\n",
        encoding="utf-8",
    )
    return AudiencePlant(UNGRANTED_VAULT_NODE_UID, int(nodes))


def break_one_entry_unreadable(studio: Path, uid: str) -> None:
    """One row of the composed index no longer decodes.

    The graph source raises ``GRAPH_UNAVAILABLE`` on it, which surfaces through
    whichever call touches the row first. Whatever stage that is, the probe has
    not learned anything about whether the studio can orient - it could not
    read the substrate.
    """
    connection = _index_connection(studio)
    try:
        connection.execute(
            "UPDATE entries SET fm_json='{ this is not json' WHERE uid=?", (uid,)
        )
        connection.commit()
    finally:
        connection.close()


# --------------------------------------------------------------------------- #
# The three ORIENT states, planted one at a time - and the readings that prove  #
# each plant actually took. Every case below is required to assert the reading  #
# BEFORE it asserts the verdict: a plant that silently no-ops leaves the probe  #
# in a different state, and the case then passes while measuring the wrong      #
# branch. That has happened twice in this file already (the rot plant that      #
# missed a node, the audience plant whose premise about `private` was false).   #
# --------------------------------------------------------------------------- #

def corpus_entry_count(studio: Path) -> typing.Optional[int]:
    """How many entries the composed index yields A READER, or None if none.

    The control for every no-corpus reading, and the control that the OTHER
    two states' plants did not accidentally take the corpus with them. Read
    the way the probe's driver reads it - open read-only, count the entries -
    so this helper and the thing under test cannot disagree about what
    "readable" means.
    """
    index = studio / smoke.COMPOSED_INDEX_REL
    if not index.is_file():
        return None
    try:
        connection = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        return int(connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def authority_is_installed(studio: Path) -> bool:
    """Is a group authority installed FOR THIS STUDIO?

    Mirrors ``lib.audience_gate.cutover_active``: the record, decoded, with an
    ``authority_uid`` in it. Deliberately not "does the directory exist" - the
    probe asks the studio's own function, and a control that asks a weaker
    question would call a half-deleted authority installed.

    Nothing here consults the machine. ADR-065: the record is resident in the
    Studio and travels with the vault.
    """
    pin = studio / smoke.GROUP_AUTHORITY_PIN_REL
    if not pin.is_file():
        return False
    try:
        record = json.loads(pin.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(record, dict) and isinstance(record.get("authority_uid"), str)


def _drop_sqlite_sidecars(index: Path) -> None:
    """A -wal left beside a replaced database is a reader's problem, not the
    plant's finding. Removed so the case measures what it planted."""
    for suffix in ("-wal", "-shm"):
        stray = index.with_name(index.name + suffix)
        if stray.exists():
            stray.unlink()


def break_the_corpus_absent(studio: Path) -> Path:
    """State 1, reading 1: there is no composed index at all."""
    index = studio / smoke.COMPOSED_INDEX_REL
    index.unlink()
    _drop_sqlite_sidecars(index)
    return index


def break_the_corpus_unopenable(studio: Path) -> Path:
    """State 1, reading 2: the composed index is on disk and is not a database.

    A real state - a truncated copy, an interrupted rebuild, a file restored
    from the wrong place. Before the corpus rung existed this came back as
    "the orientation driver raised ... that is a fault in this instrument",
    which names no owner and prints a cure that re-runs the instrument.
    """
    index = studio / smoke.COMPOSED_INDEX_REL
    index.write_bytes(b"planted by test_tropo_smoke: not a sqlite database\n")
    _drop_sqlite_sidecars(index)
    return index


def break_the_corpus_empty(studio: Path) -> int:
    """State 1, reading 3: the composed index opens and holds nothing.

    Readable, and nothing. Before the corpus rung existed this walked all the
    way to "none of the 0 most connected entries ... has a single neighbour
    inside the audience", which tells the reader to widen an audience over a
    corpus that has no entries in it - the wrong owner and the wrong cure.

    Returns the row count left behind, so the case can refuse to run over a
    delete that did not delete.
    """
    connection = _index_connection(studio)
    try:
        connection.execute("DELETE FROM entries")
        connection.commit()
        remaining = connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    finally:
        connection.close()
    return int(remaining)


def _fm_json_of(studio: Path, uid: str) -> typing.Optional[str]:
    """The raw ``fm_json`` the composed index holds for one uid.

    The control for the undecodable-row reading of state 1: without it, a
    plant that wrote to the wrong row leaves the case asserting a verdict
    about a perfectly healthy index.
    """
    connection = sqlite3.connect(
        f"file:{studio / smoke.COMPOSED_INDEX_REL}?mode=ro", uri=True
    )
    try:
        row = connection.execute(
            "SELECT fm_json FROM entries WHERE uid=?", (uid,)
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else row[0]


# Every way the ORIENT driver can name a stage. Scraped rather than typed, so
# a stage added to the driver without a verdict to route it reddens the
# coverage case instead of falling through in silence.
_DRIVER_STAGE_PATTERNS = (
    re.compile(r"""stage=["']([a-z-]+)["']"""),
    re.compile(r"""["']stage["']\s*:\s*["']([a-z-]+)["']"""),
    re.compile(r"""report\[["']stage["']\]\s*=\s*["']([a-z-]+)["']"""),
)


def _driver_stages(source: str) -> set:
    found: set = set()
    for pattern in _DRIVER_STAGE_PATTERNS:
        found.update(pattern.findall(source))
    return found


def _orient_source_regions(source: str) -> tuple:
    """The stretches of ``tropo-smoke.py`` that ARE the ORIENT probe.

    TWO regions, not one, and the second was added on 2026-08-01 because the
    first scan had a hole in it: the cure strings, the state table and the
    owners live with the ORIENT CONSTANTS, several hundred lines above
    ``# probe 6``, and a scan that started at the probe never read a word of
    them. The machine-local sentence ADR-065 superseded was sitting in exactly
    that gap.

    ``index`` rather than a tolerant search on purpose: if a marker moves, this
    fails loudly instead of quietly scanning nothing.
    """
    spans = (
        ("# ── ORIENT (operation 6)", "MINT_TOOL_REL ="),
        ("# ── probe 6: ORIENT", "PROBES: dict[str, Callable"),
    )
    regions = []
    for start_marker, end_marker in spans:
        start = source.index(start_marker)
        regions.append(source[start:source.index(end_marker, start)])
    return tuple(regions)


def a_machine_without(module: str) -> Path:
    """A directory that shadows ``module`` with the absence of ``module``.

    Break 7's world - "Python deps declared but never shipped to the fork that
    needs them" - without uninstalling anything from the machine running the
    suite. Put first on ``PYTHONPATH`` it is found before site-packages, and it
    raises the exact exception CPython raises when the module is genuinely not
    installed, ``name`` attribute included, which is the attribute the probe
    routes on.
    """
    shadow = _scratch(f"no-{module}")
    (shadow / f"{module}.py").write_text(
        f"raise ModuleNotFoundError(\"No module named {module!r}\", "
        f"name={module!r})\n",
        encoding="utf-8",
    )
    return shadow


# --------------------------------------------------------------------------- #
# Live-studio guard. The realistic way a probe damages this studio is by         #
# resolving the LIVE toolchain (vault/tools/*.py compute their own root from     #
# __file__) while pointed at a fixture, so this is checked after every test.     #
# --------------------------------------------------------------------------- #

def live_fingerprint() -> tuple:
    def stamp(root: Path):
        if not root.exists():
            return ()
        return tuple(
            (p.relative_to(LIVE_STUDIO).as_posix(), p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*"))
            if p.is_file()
        )

    return (
        stamp(LIVE_STUDIO / "vault" / "files"),
        stamp(LIVE_STUDIO / "vault" / "agents"),
        stamp(LIVE_STUDIO / "recycle"),
        stamp(LIVE_STUDIO / ".tropo-studio" / "locks"),
    )


_LIVE_AT_START: tuple = ()
_LIVE_GIT_AT_START: str = ""


def setUpModule():
    global _LIVE_AT_START, _LIVE_GIT_AT_START
    for patcher in _SOCKET_PATCHERS:
        patcher.start()
    _LIVE_AT_START = live_fingerprint()
    _LIVE_GIT_AT_START = git(LIVE_STUDIO, "status", "--porcelain", check=False).stdout


def tearDownModule():
    for patcher in reversed(_SOCKET_PATCHERS):
        patcher.stop()
    after_git = git(LIVE_STUDIO, "status", "--porcelain", check=False).stdout
    if after_git != _LIVE_GIT_AT_START:
        raise AssertionError(
            "this suite changed the LIVE studio's git state; every probe must "
            "run against the fixture it was handed\n"
            f"before:\n{_LIVE_GIT_AT_START}\nafter:\n{after_git}"
        )


# --------------------------------------------------------------------------- #
# Shared harness                                                                #
# --------------------------------------------------------------------------- #

COMMAND_TOKENS = ("python3", "python", "git", "npm", "npx", "node", "make", "bash", "sh")


def command_lines(cure: str) -> list:
    """Every line of a cure that a human could paste into a shell."""
    found = []
    for raw in (cure or "").splitlines():
        line = raw.strip().lstrip("$").strip().strip("`")
        if line.split(" ")[0] in COMMAND_TOKENS:
            found.append(line)
    return found


class SmokeCase(unittest.TestCase):
    """One used studio per case, and a guard that the live one was left alone."""

    def setUp(self) -> None:
        self._live_before = live_fingerprint()

    def tearDown(self) -> None:
        self.assertEqual(
            self._live_before,
            live_fingerprint(),
            msg="a probe wrote to the LIVE studio. Probes must resolve every "
            "path from the studio argument, never from the tool's own location.",
        )

    # -- fixtures ---------------------------------------------------------- #
    def studio(self, name: str = "used") -> Path:
        try:
            return studio_copy(name)
        except FixtureUnavailable as exc:
            self.skipTest(f"used-studio fixture unavailable: {exc}")

    # -- probe helpers ------------------------------------------------------ #
    def probe(self, operation: str, studio: Path):
        result = smoke.PROBES[operation](studio)
        self.assertEqual(
            result.operation,
            operation,
            msg=f"{operation}'s probe reported operation={result.operation!r}",
        )
        self.assertIsInstance(result.evidence, dict)
        if result.ok:
            self.assertEqual(
                result.cure,
                "",
                msg="the frozen surface says cure is empty when ok (a passing "
                "probe that prints a cure teaches agents to ignore cures)",
            )
        return result

    def assertNotPassing(self, result, *needles: str) -> None:
        """Not a pass — either outcome — and it names the error and the command.

        AC4 in one assertion, because 'MINT: FAIL' was acceptable output right
        up until somebody had to act on it at 2am. An UNKNOWN owes the reader
        the same thing a FAIL does: what happened and what to run next.
        """
        self.assertIn(result.status, smoke.STATUSES)
        self.assertFalse(
            result.ok,
            msg=f"{result.operation} reported PASS on a studio that is broken; "
            f"detail={result.detail!r} evidence={result.evidence!r}",
        )
        self.assertTrue(result.detail.strip(), msg="a failing probe printed no error")
        self.assertTrue(
            result.cure.strip(),
            msg=f"{result.operation} failed with an empty cure; AC4 requires the "
            "command a human runs next",
        )
        self.assertNotEqual(
            result.cure.strip().lower(),
            result.detail.strip().lower(),
            msg="the cure restates the error; a cure is what to DO",
        )
        haystack = f"{result.detail}\n{result.cure}".lower()
        for needle in needles:
            self.assertIn(
                needle.lower(),
                haystack,
                msg=f"{result.operation}'s failure never names {needle!r}; a human "
                "cannot act on it. Got:\n"
                f"detail={result.detail!r}\ncure={result.cure!r}",
            )

    def assertProbeFails(self, result, *needles: str) -> None:
        """A DETERMINED failure: the studio was observed unable to do this.

        Strict about the status since AC7a. Every caller of this helper plants
        a real, reproducible break — a forged seal, an unkeyed tip, a lossy
        filter, a cockpit that does not compile — and each of those has an
        answer. Accepting UNKNOWN here would let an implementation keep the run
        quiet by declining to decide, which is the mirror image of the defect
        the amendment is about.
        """
        self.assertNotPassing(result, *needles)
        self.assertEqual(
            result.status,
            smoke.STATUS_FAIL,
            msg=f"{result.operation} reported {result.status!r} over a studio "
            "with a planted, determined break. UNKNOWN means 'this instrument "
            "could not tell'; here it could. detail=" + repr(result.detail),
        )
        self.assertIn(result, smoke.failures([result]))

    def assertProbeUnknown(self, result, *needles: str) -> None:
        """AC7a's third outcome, and it has to say what it did and did not check.

        A bare UNKNOWN is as useless as 'MINT: FAIL'. So this asserts the
        status, that `ok` is False and `failed` is False (the two-way readings
        both being wrong is the whole point), that the partial work reached
        both the evidence and the prose, and that a cure came with it.
        """
        self.assertNotPassing(result, *needles)
        self.assertEqual(
            result.status,
            smoke.STATUS_UNKNOWN,
            msg=f"{result.operation} reported {result.status!r} for an "
            "operation this instrument could not determine. Reporting "
            "red-when-blind erodes trust exactly as fast as green-when-blind "
            f"(AC7a). detail={result.detail!r}",
        )
        self.assertFalse(result.ok)
        self.assertFalse(
            result.failed,
            msg="an UNKNOWN must not read as a failure through any accessor",
        )
        self.assertTrue(result.unknown)
        self.assertEqual(
            smoke.failures([result]), [], msg="failures() swept up an UNKNOWN"
        )
        self.assertIs(result.evidence.get("degraded"), True)
        for key in ("checked", "not_checked"):
            value = result.evidence.get(key)
            self.assertIsInstance(
                value, list,
                msg=f"an UNKNOWN with no evidence[{key!r}] does not say what it "
                f"did and did not check (AC7a). evidence={result.evidence!r}",
            )
        self.assertTrue(
            result.evidence["not_checked"],
            msg="an UNKNOWN that names nothing it failed to check is a bare "
            "UNKNOWN, which the amendment calls as useless as 'MINT: FAIL'",
        )
        lowered = result.detail.lower()
        self.assertIn(
            "not checked",
            lowered,
            msg="the partial work never reached the prose a human reads; "
            f"detail={result.detail!r}",
        )
        self.assertIn("unknown", lowered)

    def assertOrientState(self, result, state, *needles,
                          cure: typing.Optional[str] = None) -> None:
        """One of the three ORIENT states, whole: verdict, owner, cure, place.

        The sharpening this asserts is Argus A143's, endorsed by Metis: three
        states, not two, "because they have different OWNERS, so collapsing
        them into one UNKNOWN reproduces the failure the probe exists to
        catch." So a state is not proven by its verdict alone. Every clause
        below is one of the things a reader needs and the collapsed UNKNOWN
        did not give them:

        * the verdict the state carries - two of these are nobody having done
          a thing yet (UNKNOWN) and the third is a defect (FAIL), and reading
          the wrong one is what the whole distinction is for;
        * the state and its owner FIRST in the line, because a report scrolls
          and "at a glance" means the first phrase, not the ninth clause;
        * exactly ONE of the three named in the prose - two at once is the
          collapse in a different costume;
        * a cure that is not one of the OTHER two states' cures, because a
          reader who cannot tell them apart by the command they were handed
          has been given the collapsed UNKNOWN back.
        """
        self.assertNotPassing(result, *needles)
        self.assertEqual(
            result.status, state.status,
            msg=f"{state.name} is specified as {state.status.upper()} and this "
            f"came back {result.status.upper()}. The two UNKNOWNs are things "
            "nobody has done yet and the FAIL is a defect; swapping them is "
            f"the whole error. detail={result.detail!r}",
        )
        self.assertEqual(
            result.evidence.get("orient_state"), state.name,
            msg="the state never reached the evidence, so nothing downstream "
            f"can route on it: evidence={result.evidence!r}",
        )
        self.assertEqual(
            result.evidence.get("orient_state_owner"), state.owner,
            msg="the state reached the evidence without its owner, which is "
            "the field the three states exist to carry",
        )
        self.assertTrue(
            result.detail.startswith(state.opening()),
            msg="the state and its owner are not the FIRST thing a reader "
            "sees. An UNKNOWN that makes you read to the end to find out "
            f"whose problem it is has not stopped being collapsed: "
            f"{result.detail!r}",
        )
        named = [
            other.name for other in smoke.ORIENT_STATES
            if other.name in result.detail
        ]
        self.assertEqual(
            named, [state.name],
            msg="exactly one of the three states may be claimed by one "
            f"verdict; this one claimed {named}. detail={result.detail!r}",
        )
        for other in smoke.ORIENT_STATES:
            if other is state:
                continue
            self.assertNotEqual(
                result.cure.strip(), other.next_action.strip(),
                msg=f"{state.name} printed {other.name}'s cure. Two states "
                "sharing a command is the collapse with the labels left on",
            )
        self.assertEqual(
            result.cure, state.next_action if cure is None else cure,
            msg=f"{state.name} did not print the next action it is specified "
            f"to print. got={result.cure!r}",
        )
        self.assertReportNamesTheCure(result)

    def assertNoOrientState(self, result) -> None:
        """This instrument could not look, and said so without inventing an owner.

        The counterweight to ``assertOrientState``. A clock that ran out, a
        machine with no PyYAML, an audience that covers nothing - none of
        those is a fact about the Studio, and naming a fourth state for them
        would re-collapse the three. So: no ``orient_state``, and no state
        name smuggled into the prose either.
        """
        self.assertNotIn(
            "orient_state", result.evidence,
            msg="this branch could not look and claimed a state anyway; the "
            "owner it named is a guess. "
            f"evidence={result.evidence!r} detail={result.detail!r}",
        )
        named = [
            state.name for state in smoke.ORIENT_STATES
            if state.name in result.detail
        ]
        self.assertEqual(
            named, [],
            msg=f"a stateless branch named {named} in its prose anyway",
        )

    def assertReportNamesTheCure(self, result) -> None:
        report = smoke.format_report([result])
        self.assertIsInstance(report, str)
        self.assertIn(result.operation.lower(), report.lower())
        self.assertIn(result.detail.strip(), report)
        self.assertIn(result.cure.strip(), report)
        bare = f"{result.operation.upper()}: FAIL"
        self.assertNotEqual(
            report.strip(),
            bare,
            msg=f"{bare!r} alone is not acceptable output (AC4)",
        )
        self.assertGreater(len(report.strip()), len(bare) + 20)


# =========================================================================== #
# AC1 - the probes, keyed by OPERATIONS, run against the invoked studio         #
# =========================================================================== #
class AC1TheProbeSurfaceTests(SmokeCase):
    def test_ac1_the_operations_are_the_ones_a_studio_must_be_able_to_do(self):
        """A studio that cannot boot, mint, index, commit and build is broken,
        whatever its validator says. The tuple is the contract.

        ORIENT joined it after Metis G98 wired the shipped ``orient()`` to this
        studio's real surfaces and found it could not run at all - failing
        closed at the visibility floor before a circle was drawn - while every
        instrument the crew owned stayed green. The five ask whether the studio
        can still WORK; the sixth asks whether it can still answer a question
        about itself, and it goes last because it reads the index operation 3
        freshens.
        """
        self.assertEqual(
            smoke.OPERATIONS,
            ("boot", "mint", "index", "commit", "build", "orient"),
        )

    def test_ac1_probes_is_keyed_by_operations_with_no_gaps_and_no_extras(self):
        self.assertEqual(set(smoke.PROBES), set(smoke.OPERATIONS))
        for operation in smoke.OPERATIONS:
            with self.subTest(operation=operation):
                self.assertTrue(callable(smoke.PROBES[operation]))
                self.assertIs(
                    smoke.PROBES[operation],
                    getattr(smoke, f"probe_{operation}"),
                    msg=f"PROBES[{operation!r}] is not probe_{operation}; two "
                    "entry points to one operation is two behaviours waiting to "
                    "diverge",
                )

    def test_ac1_run_all_runs_every_operation_in_order_and_only_narrows_it(self):
        studio = self.studio()
        results = smoke.run_all(studio)
        self.assertEqual(
            [result.operation for result in results], list(smoke.OPERATIONS)
        )
        for operation in smoke.OPERATIONS:
            with self.subTest(operation=operation):
                narrowed = smoke.run_all(studio, only=operation)
                self.assertEqual([r.operation for r in narrowed], [operation])

    def test_ac1_they_all_go_green_on_a_studio_that_is_actually_working(self):
        """The baseline every plant in this file is a differential against.

        An instrument that always says FAIL is as useless as one that always
        says PASS, and it is the failure mode a plant-heavy suite invites. This
        is also the only case that exercises them all in one pass, in
        OPERATIONS order, the way the CLI runs them - and that ordering carries
        a hazard measured while writing this suite:

            MINT recycles its throwaway (AC2). ``tropo-recycle.py`` rewrites the
            index seal, and the manifest it leaves behind has dropped the
            ``@repo-clock`` and ``@wall-clock-date`` virtual inputs. INDEX runs
            next. Every incremental ``tropo-rebuild-index.py --only`` then
            refuses with "semantic derivation inputs changed outside the owned
            target: @repo-clock, @wall-clock-date", until somebody runs a full
            ``--apply``.

        That is break 9's shape - a write path leaving a seal the read path
        refuses - sitting directly across operations 2 and 3 of the five. The
        contract does not say how to handle it (re-stamp after recycling, or
        have INDEX recognise the drift and reconcile). It does say all five pass
        on a working studio, so it has to be handled.
        """
        studio = self.studio()
        results = smoke.run_all(studio)
        failed = [result for result in results if not result.ok]
        self.assertFalse(
            failed,
            msg="a healthy used studio - real entries, real capsules, rendered, "
            "indexed, sealed, filter installed - was reported broken:\n"
            + "\n".join(f"  {r.operation}: {r.detail}\n    cure: {r.cure}" for r in failed),
        )

    def test_ac1_every_probe_returns_the_frozen_result_shape(self):
        studio = self.studio()
        for result in smoke.run_all(studio):
            with self.subTest(operation=result.operation):
                self.assertIn(result.operation, smoke.OPERATIONS)
                self.assertIn(
                    result.status,
                    smoke.STATUSES,
                    msg="status is the primary field since AC7a and it is one "
                    f"of {smoke.STATUSES}; got {result.status!r}",
                )
                self.assertIsInstance(result.ok, bool)
                self.assertIsInstance(result.detail, str)
                self.assertIsInstance(result.cure, str)
                self.assertIsInstance(result.elapsed_s, float)
                self.assertIsInstance(result.evidence, dict)
                # A probe that reports zero elapsed time measured nothing. Same
                # shape as rows_checked=0: a number that proves the instrument
                # never ran is worse than no number.
                self.assertGreater(
                    result.elapsed_s,
                    0.0,
                    msg=f"{result.operation} claims it took no time at all",
                )

    def test_ac1_probe_results_are_frozen_so_a_verdict_cannot_be_edited_later(self):
        studio = self.studio()
        result = self.probe("index", studio)
        with self.assertRaises(Exception):
            result.ok = True  # type: ignore[misc]
        with self.assertRaises(Exception):
            result.status = smoke.STATUS_PASS  # type: ignore[misc]


# =========================================================================== #
# R2 - the instrument may not construct the world it then inspects              #
# =========================================================================== #
class R2RealStudioTests(SmokeCase):
    def test_r2_no_probe_reports_green_against_a_studio_that_is_not_there(self):
        """*An instrument that constructs its own world will always find that
        world in order.* An empty directory is the cheapest proof: a probe that
        builds its own pristine studio passes here, and every one of them must
        fail instead."""
        empty = _scratch("empty-world") / "not-a-studio"
        empty.mkdir(parents=True)
        for operation in smoke.OPERATIONS:
            with self.subTest(operation=operation):
                result = self.probe(operation, empty)
                self.assertFalse(
                    result.ok,
                    msg=f"{operation} reported PASS against an empty directory; "
                    "it is testing a world it made, not the studio it was given",
                )
                self.assertTrue(result.cure.strip())
        self.assertEqual(
            sorted(path.name for path in empty.iterdir()),
            [],
            msg="a probe furnished the empty directory it was pointed at. "
            "Building the world you then inspect is how an instrument certifies "
            "a studio nobody has ever used.",
        )

    def test_r2_the_verdicts_track_the_studio_they_are_handed(self):
        """The differential form: one healthy studio, one broken, same process.
        A probe with a fixed answer cannot satisfy both halves."""
        healthy = self.studio()
        broken = self.studio()
        break_forged_seal(broken)
        self.assertTrue(
            self.probe("index", healthy).ok,
            msg="the healthy used studio must pass, or the plants below prove "
            "nothing but that the probe always fails",
        )
        self.assertFalse(self.probe("index", broken).ok)

    def test_r2_the_module_builds_no_studio_of_its_own(self):
        """A structural audit to go with the behavioural one. Cloning, init-ing
        or copying a tree into place is how a probe ends up certifying a world
        that has never been used - which is case 3 of 1f29bcfb, and the reason
        059f2c68 passed CI.

        Two false positives were cut from this case while writing it, and both
        are worth recording, because a gate that refuses legitimate work is the
        measured disease here - nine firings on 2026-07-30, zero attacks caught.

        * It banned the *string* ``git init``, and fired on a cure that reads
          "not a git worktree - run git init". Naming a repair in a cure is the
          behaviour AC4 demands.
        * It banned ``mkdtemp`` outright, and fired on a probe that stages a
          backup of the derived surfaces so it can put them back. Scratch space
          is not a studio. What R2 forbids is *reporting on* a world you built,
          and only behaviour can see that - which is the empty-directory case
          above, and it is what actually holds this line.

        What is left is unambiguous: initialising or cloning a repository, and
        duplicating the studio you were handed.
        """
        tree = ast.parse(SMOKE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
                if name == "copytree" and _mentions_the_studio(node):
                    self.fail(
                        f"copytree({ast.unparse(node.args[0]) if node.args else '?'})"
                        " duplicates the studio; a probe reports on the studio it "
                        "was handed, not on a copy it made of it"
                    )
            if isinstance(node, (ast.List, ast.Tuple)):
                words = [
                    element.value
                    for element in node.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                ]
                if words and words[0] == "git":
                    self.assertNotIn(
                        words[1] if len(words) > 1 else "",
                        {"init", "clone"},
                        msg=f"{words} constructs a repository to test instead of "
                        "testing the one it was given",
                    )


def _string_literals(tree) -> set:
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _mentions_the_studio(node) -> bool:
    """Does this call reach for the studio it was handed?

    The one distinction an AST scan can actually draw. ``rmtree(tmpdir)`` is a
    probe cleaning up after itself; ``rmtree(studio / 'vault' / 'files' / uid)``
    is a probe deleting the Vault. Anything laundered through a local variable
    first escapes this, which is why the behavioural plants carry the weight.
    """
    rendered = ast.unparse(node)
    return "studio" in rendered or "vault/files" in rendered


# =========================================================================== #
# AC2 - non-destructive                                                         #
# =========================================================================== #
class AC2NonDestructiveTests(SmokeCase):
    def test_ac2_two_consecutive_runs_leave_every_governed_plane_untouched(self):
        """The spec's double-run diff, at the grain where it is meaningful.

        Byte-identical over the WHOLE tree is unreachable for a probe that really
        mints - see the module docstring. What must hold is that no governed byte
        moved, the index says the same thing afterwards, and git has nothing new
        to report. Paired with the recycle-bin assertion below, a do-nothing
        implementation cannot satisfy both.
        """
        studio = self.studio()
        self.maxDiff = None
        before = governed_census(studio)
        before_paths = tree_paths(studio)
        before_rows = set(index_rows(studio))
        before_git = git_state(studio)

        first = smoke.run_all(studio)
        after_first = governed_census(studio)
        second = smoke.run_all(studio)
        after_second = governed_census(studio)

        self.assertTrue(
            all(result.ok for result in first),
            msg="the fixture must be healthy for this to mean anything: "
            + "; ".join(f"{r.operation}: {r.detail}" for r in first if not r.ok),
        )
        self.assertTrue(all(result.ok for result in second))
        self.assertEqual(before, after_first, msg="run 1 changed governed content")
        self.assertEqual(after_first, after_second, msg="run 2 changed governed content")
        self.assertEqual(before_rows, set(index_rows(studio)), msg="the index gained or lost entries")
        self.assertEqual(before_git, git_state(studio), msg="the run left git state changed")

        stray = sorted(
            path
            for path in tree_paths(studio) - before_paths
            if not _is_derived(path)
        )
        self.assertEqual(
            stray,
            [],
            msg="two runs left files behind outside every sanctioned plane. A "
            "smoke test that litters is a smoke test nobody runs twice.",
        )

    def test_ac2_the_mint_probe_recycles_its_throwaway_and_leaves_no_orphan(self):
        """The evidence that the probe did the work, and did it the sanctioned
        way. A throwaway that vanishes without reaching recycle/ was removed with
        rm, which is the gesture the v1.35.0 incident cost us.

        RULED 2026-07-31 (Talos T37). AC2 asks for two things that cannot both
        be true, and both lanes building this found the conflict independently
        and resolved it opposite ways. AC2 says "proven by running it twice in a
        row and diffing the tree — byte-identical", and it also says the removal
        must go through ``tropo-recycle.py``. But ``recycle/`` is TRACKED here —
        1,556 files, a ``merge=union`` rule on its log, no ignore entry — so a
        retained tombstone hands the operator two new tracked paths on EVERY
        liveness check. A tool that bills you a commit for asking whether the
        studio is alive is a tool nobody runs, which is AC7's stated failure
        mode arriving through the back door.

        So byte-identity wins, and the tombstone is rolled back. That is not a
        deletion-discipline breach: the throwaway was never work, it is the
        probe's own scratch, and the REMOVAL still goes through the sanctioned
        tool. What is rolled back is bin state, not the code path.

        Which means this test can no longer prove the gesture by looking for a
        grave. It proves it from the probe's own evidence instead, and that is
        strictly harder to fake — a probe that shells out to ``rm`` cannot name
        a tombstone path under ``recycle/agent-deletions/``.
        """
        studio = self.studio()
        files_before = census(studio / "vault" / "files")

        result = self.probe("mint", studio)
        self.assertTrue(result.ok, msg=f"mint failed on a healthy studio: {result.detail}")

        self.assertEqual(
            files_before,
            census(studio / "vault" / "files"),
            msg="the mint probe left its throwaway (or an edit) in vault/files/",
        )
        tombstones = result.evidence.get("recycle_tombstones") or []
        self.assertTrue(
            tombstones,
            msg="the probe recorded no recycle tombstone, so either it never "
            "minted anything or it removed the throwaway without going through "
            f"tropo-recycle.py. evidence={result.evidence!r}",
        )
        self.assertTrue(
            all(
                re.fullmatch(r"[0-9a-f]{8}\.md", Path(t).name)
                and "recycle" in Path(t).parts[0]
                for t in tombstones
            ),
            msg="a recorded tombstone does not look like a uid landing in the "
            f"sanctioned bin: {tombstones}",
        )
        self.assertNotIn(
            ORPHAN_TRANSFER_UID,
            index_rows(studio),
            msg="sanity: the fixture must not already contain the orphan uid",
        )

    def test_ac2_the_module_never_removes_a_governed_path(self):
        """AC2's other half, audited structurally: recycle, never rm.

        Deletion discipline is a process rule, and a probe is exactly the
        'obvious case' that trains the next agent to bypass it.

        Scoped to deletes that reach for the studio, not to the primitives.
        The first draft banned ``unlink`` and ``rmtree`` outright and fired on a
        probe removing its own staging directory - which is the shape of the
        problem this whole spec is about, a gate refusing legitimate work. The
        spec says "never rm over a *governed path*", and that qualifier is the
        test. The decoy plant below is what catches a delete laundered through a
        local variable, which no AST scan can see.
        """
        source = SMOKE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        deletes = {"rmtree", "unlink", "remove", "removedirs", "rmdir"}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
            if name in deletes and _mentions_the_studio(node):
                self.fail(
                    f"{ast.unparse(node)} deletes a path off the studio. The "
                    "mint probe recycles its throwaway via tropo-recycle.py, "
                    "and no probe rm's governed content (AC2)."
                )
            if isinstance(node, (ast.List, ast.Tuple)):
                words = [
                    element.value
                    for element in node.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                ]
                if words and words[0] == "git":
                    self.assertFalse(
                        "clean" in words or ("checkout" in words and "--" in words),
                        msg=f"{words} discards the worktree. A liveness probe "
                        "reports on what it found; it does not repair it by "
                        "throwing work away.",
                    )
        for literal in _string_literals(tree):
            # Scoped the same way, and for the same reason: a BUILD cure may
            # legitimately read `rm -rf node_modules`, and `git checkout --
            # vault/tools/<tool>.py` is a real repair a human runs. What is
            # never legitimate is this module reaching for the Vault with rm.
            if "vault/" in literal:
                self.assertNotIn("rm -rf", literal)
        self.assertIn(
            "tropo-recycle.py",
            source,
            msg="AC2 names the gesture: the throwaway uid goes back through "
            "tropo-recycle.py",
        )

    def test_ac2_a_governed_entry_that_looks_like_a_throwaway_still_survives(self):
        """The decoy, and the sharpest thing this suite says about AC2.

        The mint probe creates an 8-hex governed entry and then has to get rid
        of it. The cheap implementation of "get rid of it" is a sweep: anything
        under `vault/files/` that this run does not recognise, or that carries
        the probe's own author stamp, goes. That works perfectly until it meets
        an entry somebody else minted a minute earlier - and a smoke test that
        eats a colleague's unindexed draft is worse than no smoke test.

        So: a real governed entry, minted the way the studio mints, sitting in
        `vault/files/` before the run starts and carrying the probe's own
        plausible author stamp. It must be there afterwards, byte for byte, and
        it must not be in the recycle bin.
        """
        studio = self.studio()
        decoy = studio / "vault" / "files" / "5eb0dec0.md"
        source = studio / "vault" / "files" / f"{CONTENT_ENTRIES[0]}.md"
        decoy.write_text(
            source.read_text(encoding="utf-8").replace(
                f"uid: {CONTENT_ENTRIES[0]}", "uid: 5eb0dec0", 1
            ),
            encoding="utf-8",
        )
        frontmatter_set(decoy, "author", "tropo-smoke")
        frontmatter_set(decoy, "title", '"decoy - a colleague''s unindexed draft"')
        planted = decoy.read_bytes()

        smoke.run_all(studio)

        self.assertTrue(
            decoy.is_file(),
            msg="the run deleted a governed entry that merely looked like the "
            "probe's own throwaway. A mint probe must recycle the uid it minted "
            "and nothing else.",
        )
        self.assertEqual(planted, decoy.read_bytes(), msg="the decoy was edited")
        recycled = census(studio / "recycle") if (studio / "recycle").exists() else {}
        self.assertFalse(
            [path for path in recycled if Path(path).name == "5eb0dec0.md"],
            msg="the run recycled a governed entry it did not mint",
        )

    def test_ac2_a_failed_probe_leaves_no_residue_either(self):
        """The harder half. Cleanup on the happy path is easy; the 2026-07-30
        breaks were all failures, and a failing probe that leaves half a mint
        behind turns one broken studio into two."""
        studio = self.studio()
        self.maxDiff = None
        break_forged_seal(studio)
        before = governed_census(studio)
        results = smoke.run_all(studio)
        self.assertTrue(
            any(not result.ok for result in results),
            msg="the fixture is deadlocked; something must have failed",
        )
        self.assertEqual(
            before,
            governed_census(studio),
            msg="a failing run left governed residue behind - most likely a "
            "throwaway uid that was minted and then never recycled because the "
            "probe returned early on the error. One broken studio became two.",
        )


# =========================================================================== #
# AC3 - stdlib only, proven by an AST scan                                      #
# =========================================================================== #
class AC3StdlibOnlyTests(unittest.TestCase):
    def test_ac3_every_import_in_the_module_resolves_to_the_standard_library(self):
        """Like tropo-preflight (d78cc16a), this tool has to run when the studio
        is partly broken - break 7 was Python deps declared but never shipped to
        the fork that needed them. A grep would miss a conditional import inside
        a function; the AST does not."""
        tree = ast.parse(SMOKE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # a relative import is this module's own package
                imported.add((node.module or "").split(".")[0])
        imported.discard("")

        self.assertTrue(imported, "the module imports nothing at all; scan is vacuous")
        for name in sorted(imported):
            with self.subTest(module=name):
                self.assertTrue(
                    _is_stdlib(name),
                    msg=f"{name!r} is not in the standard library. A third-party "
                    "import defeats the point of the tool (AC3).",
                )

    def test_ac3_the_scan_can_actually_fail(self):
        """Guards the guard. A stdlib predicate that says yes to everything would
        make the case above decoration."""
        self.assertFalse(_is_stdlib("yaml"))
        self.assertFalse(_is_stdlib("anthropic"))
        self.assertTrue(_is_stdlib("json"))
        self.assertTrue(_is_stdlib("subprocess"))


def _is_stdlib(name: str) -> bool:
    if name in sys.builtin_module_names:
        return True
    known = getattr(sys, "stdlib_module_names", None)
    if known is not None:
        return name in known
    import importlib.util
    import sysconfig

    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return False
    if spec is None or not spec.origin:
        return False
    stdlib = sysconfig.get_paths().get("stdlib", "")
    return bool(stdlib) and spec.origin.startswith(stdlib) and "site-packages" not in spec.origin


# =========================================================================== #
# AC4 - names the cure, not just the failure                                    #
# =========================================================================== #
class AC4NamesTheCureTests(SmokeCase):
    def test_ac4_a_failing_probe_prints_the_operation_the_error_and_the_command(self):
        """AC4 over whatever did not pass, in either non-passing outcome.

        This is the one case that deliberately does NOT pin the status: it
        sweeps up every result that is not a clean pass and demands the AC4
        shape from each. An UNKNOWN owes the reader the same thing a FAIL does.
        The status-specific plants are elsewhere and they are strict.
        """
        studio = self.studio()
        break_forged_seal(studio)
        break_typecheck(studio)
        not_passing = [r for r in smoke.run_all(studio) if r.status != smoke.STATUS_PASS]
        self.assertTrue(
            not_passing, "nothing failed on a studio that is broken twice over"
        )
        self.assertTrue(
            [r for r in not_passing if r.status == smoke.STATUS_FAIL],
            msg="a studio with a forged seal and a broken typecheck has two "
            "determined breaks in it; reporting none of them as FAIL is the "
            "amendment being used to keep the run quiet",
        )
        for result in not_passing:
            with self.subTest(operation=result.operation):
                self.assertNotPassing(result)
                self.assertReportNamesTheCure(result)

    def test_ac4_the_cure_is_a_command_a_human_can_run(self):
        """'Check the index' is not a cure. The measured cost of break 9 was 2h17m
        of agents not knowing which command repairs the seal."""
        studio = self.studio()
        break_forged_seal(studio)
        result = self.probe("index", studio)
        self.assertProbeFails(result)
        self.assertTrue(
            command_lines(result.cure),
            msg="the cure contains no runnable command line, only prose: "
            f"{result.cure!r}",
        )

    def test_ac4_the_report_carries_every_probe_not_just_the_failures(self):
        """`MINT: FAIL` names the operation and nothing else, and a report made
        of five of those lines lists all five operations while telling the
        reader nothing they can act on. So the operation NAME is not the
        assertion: every probe's detail must reach the report, and every failing
        probe's cure with it."""
        studio = self.studio()
        break_typecheck(studio)
        results = smoke.run_all(studio)
        self.assertTrue(any(not r.ok for r in results), "nothing failed to report")
        report = smoke.format_report(results)
        for result in results:
            with self.subTest(operation=result.operation):
                self.assertIn(result.operation.lower(), report.lower())
                self.assertIn(
                    result.detail.strip(),
                    report,
                    msg=f"{result.operation}'s detail never reached the report; "
                    "a verdict with no finding behind it is the 2am output AC4 "
                    "was written against",
                )
                if not result.ok:
                    self.assertIn(result.cure.strip(), report)
                    self.assertTrue(result.cure.strip())

    def test_ac4_the_cli_exits_one_when_a_probe_fails_and_zero_when_none_do(self):
        healthy = self.studio()
        broken = self.studio()
        break_forged_seal(broken)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(smoke.main(["--studio", str(healthy)]), 0)
            self.assertEqual(smoke.main(["--studio", str(broken)]), 1)

    def test_ac4_json_output_carries_the_cure_a_machine_can_route(self):
        studio = self.studio()
        break_forged_seal(studio)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = smoke.main(["--studio", str(studio), "--only", "index", "--json"])
        self.assertEqual(exit_code, 1)
        payload = json.loads(buffer.getvalue())
        rows = payload if isinstance(payload, list) else payload.get("results", payload.get("probes"))
        self.assertTrue(rows, f"--json emitted nothing routable: {payload!r}")
        row = rows[0] if isinstance(rows, list) else rows
        self.assertEqual(row["operation"], "index")
        self.assertIs(row["ok"], False)
        self.assertEqual(
            row["status"],
            smoke.STATUS_FAIL,
            msg="--json must carry the three-way status, and a forged seal is "
            f"a determined break; got {row.get('status')!r}",
        )
        self.assertTrue(row["cure"].strip())
        self.assertIn("rows_checked", row["evidence"])


# =========================================================================== #
# AC7 - fast enough to be run without thinking                                  #
# =========================================================================== #
class AC7TimeBudgetTests(SmokeCase):
    def test_ac7_the_default_budget_is_120_and_thirty_is_fast(self):
        """AC7 as amended 2026-07-31, replacing the original 30s assertion.

        The first live run measured the collision the old number caused: a real
        index rebuild on the studio costs 20-40s, so a 30s TOTAL budget forced
        ~2s sub-budgets onto MINT, INDEX and BUILD and timed all three out.
        """
        self.assertEqual(smoke.TIME_BUDGET_SECONDS, 120)
        self.assertEqual(smoke.FAST_BUDGET_SECONDS, 30)

    def test_ac7_a_whole_run_fits_inside_the_FAST_budget(self):
        """Measured against the fixture, not against this studio - a contract
        test cannot time a vault it is forbidden to touch. If a 15-entry used
        studio cannot clear 30 seconds, the 4,293-entry one has no chance.

        Held against the FAST budget rather than the new 120s default on
        purpose. Raising the assertion with the amendment would have removed
        its teeth: the amendment exists because a REAL studio cannot clear 30s,
        and a 15-entry fixture is not that studio. The strict promise is the
        one worth pinning here.
        """
        studio = self.studio()
        started = time.monotonic()
        results = smoke.run_all(studio, budget=smoke.FAST_BUDGET_SECONDS)
        elapsed = time.monotonic() - started
        self.assertLess(
            elapsed,
            smoke.FAST_BUDGET_SECONDS,
            msg=f"run_all took {elapsed:.1f}s against a {len(index_rows(studio))}-row "
            "fixture; it will not be run",
        )
        self.assertLessEqual(
            sum(result.elapsed_s for result in results),
            smoke.FAST_BUDGET_SECONDS,
            msg="the probes' own reported timings already exceed the budget",
        )


# =========================================================================== #
# AC7 AMENDED - the ceilings move with the budget, or the amendment is a       #
# number change that fixes nothing                                             #
# =========================================================================== #

# Metis G98's live measurement, and the reason AC7 was amended: a real index
# rebuild on the studio costs this much. Any per-probe ceiling below it means
# the operation cannot finish, whatever the total budget says.
MEASURED_REBUILD_FLOOR_SECONDS = 20.0
MEASURED_REBUILD_CEILING_SECONDS = 40.0

# The whole deterministic orientation against the live studio's 4,832-entry
# composed index, measured with `--only orient`: 0.18s. Rounded up hard,
# because a number used to argue "this one does not starve the others" should
# be generous to the opposite case.
MEASURED_ORIENT_SECONDS = 0.5


@contextlib.contextmanager
def budget_spent(budget: float, spent: float):
    """Pretend a run on `budget` has already burned `spent` seconds.

    Exercises the real ``_timeout_for``: it reads the module-level budget and
    the module-level deadline that ``run_all`` publishes, which is exactly the
    arithmetic AC7's collision lives in.
    """
    previous_budget = smoke._BUDGET_SECONDS
    previous_deadline = smoke._DEADLINE
    smoke._BUDGET_SECONDS = float(budget)
    smoke._DEADLINE = time.monotonic() + (budget - spent)
    try:
        yield
    finally:
        smoke._BUDGET_SECONDS = previous_budget
        smoke._DEADLINE = previous_deadline


def simulate_run(budget: float, costs: dict) -> tuple:
    """Walk the five operations in order against the REAL ``_timeout_for``.

    Returns (ceiling per operation, "finished"/"timed out" per operation).
    `costs` is what each operation would take if nothing interrupted it; a
    probe handed less than its cost times out and burns its whole ceiling,
    which is what starves the ones behind it. Everything about the budget
    arithmetic is the module's own - only the subprocesses are replaced by a
    measured number, because a contract test cannot run a 4,293-entry rebuild.
    """
    ceilings, outcomes = {}, {}
    elapsed = 0.0
    previous_budget = smoke._BUDGET_SECONDS
    previous_deadline = smoke._DEADLINE
    smoke._BUDGET_SECONDS = float(budget)
    try:
        for operation in smoke.OPERATIONS:
            smoke._DEADLINE = time.monotonic() + (budget - elapsed)
            ceiling = smoke._timeout_for(operation)
            ceilings[operation] = ceiling
            cost = costs[operation]
            outcomes[operation] = "finished" if cost <= ceiling else "timed out"
            elapsed += min(cost, ceiling)
    finally:
        smoke._BUDGET_SECONDS = previous_budget
        smoke._DEADLINE = previous_deadline
    return ceilings, outcomes


class AC7BudgetAmendmentTests(SmokeCase):
    def test_ac7_every_per_probe_ceiling_is_derived_from_the_active_budget(self):
        """The amendment's actual content, and the trap it had to avoid.

        The first build hardcoded `PROBE_TIMEOUTS = {"index": 20.0, ...}`
        against a 30s budget. Raising TIME_BUDGET_SECONDS to 120 while leaving
        those constants alone would have produced a tool that reports a 120s
        budget and still caps the index freshen at 20s - the amendment applied
        to the total and withheld from the operation it was written for. So the
        ceilings have to MOVE, and quadrupling the budget has to quadruple
        every one of them.
        """
        fast, default = {}, {}
        for operation in smoke.OPERATIONS:
            with budget_spent(smoke.FAST_BUDGET_SECONDS, 0.0):
                fast[operation] = smoke._timeout_for(operation)
            with budget_spent(smoke.TIME_BUDGET_SECONDS, 0.0):
                default[operation] = smoke._timeout_for(operation)

        ratio = smoke.TIME_BUDGET_SECONDS / smoke.FAST_BUDGET_SECONDS
        for operation in smoke.OPERATIONS:
            with self.subTest(operation=operation):
                self.assertAlmostEqual(
                    default[operation],
                    fast[operation] * ratio,
                    places=6,
                    msg=f"{operation}'s ceiling did not move with the budget "
                    f"({fast[operation]}s at {smoke.FAST_BUDGET_SECONDS}s, "
                    f"{default[operation]}s at {smoke.TIME_BUDGET_SECONDS}s). A "
                    "ceiling that ignores the budget is the amendment applied "
                    "to the total and withheld from the operations.",
                )

    def test_ac7_the_fast_budget_reproduces_the_original_ceilings_exactly(self):
        """`--fast` is the 30s promise PRESERVED, not a new tuning.

        These five numbers are T37's original PROBE_TIMEOUTS. If `--fast` did
        not reproduce them, the amendment would have quietly changed the
        behaviour it claimed to keep.
        """
        original = {"boot": 10.0, "mint": 25.0, "index": 20.0,
                    "commit": 10.0, "build": 25.0}
        with budget_spent(smoke.FAST_BUDGET_SECONDS, 0.0):
            for operation, seconds in original.items():
                with self.subTest(operation=operation):
                    self.assertAlmostEqual(
                        smoke._timeout_for(operation), seconds, places=6
                    )

    def test_ac7_the_default_budget_is_what_stops_index_and_build_timing_out(self):
        """THE COLLISION, replayed as the run that produced it.

        Metis G98, from the first live run: "a real index rebuild on this
        studio is 20-40s, so a 30s TOTAL budget forces sub-budgets of ~2s onto
        MINT, INDEX and BUILD, and all three then time out."

        The mechanism is sequential drain, so isolated arithmetic cannot see
        it: each probe's ceiling is shrunk to what is LEFT, so an expensive
        MINT is what starves INDEX, and a starved INDEX is what pushes COMMIT
        and BUILD onto the floor. `simulate_run` walks the five operations in
        OPERATIONS order against the real ``_timeout_for`` with a real
        remaining-budget deadline, which is the same arithmetic ``run_all``
        performs - only the subprocesses are replaced by their measured cost.

        The assertion is Metis's sentence verbatim: on 30s, MINT, INDEX and
        BUILD time out. On 120s, none of them does.
        """
        # A studio where the three expensive operations really cost what they
        # were measured to cost. BOOT is pure I/O and COMMIT is one small file
        # through the filter; both are sub-second on the live studio.
        measured = {
            "boot": 0.1,
            "mint": MEASURED_REBUILD_FLOOR_SECONDS + 10.0,
            "index": MEASURED_REBUILD_FLOOR_SECONDS + 10.0,
            "commit": 0.5,
            "build": MEASURED_REBUILD_FLOOR_SECONDS + 10.0,
            # Measured on the live 4,832-entry index: interpreter start, the
            # PyYAML/cryptography import chain, resolver load, anchor
            # selection, draw and rank, end to end.
            "orient": MEASURED_ORIENT_SECONDS,
        }
        fast_ceilings, fast_outcome = simulate_run(
            smoke.FAST_BUDGET_SECONDS, measured
        )
        default_ceilings, default_outcome = simulate_run(
            smoke.TIME_BUDGET_SECONDS, measured
        )

        self.assertEqual(
            [op for op, outcome in fast_outcome.items() if outcome == "timed out"],
            ["mint", "index", "build"],
            msg="the collision AC7 was amended over is not reproduced, so this "
            "case proves nothing. Ceilings on the 30s budget: "
            + ", ".join(f"{op}={s:.1f}s" for op, s in fast_ceilings.items()),
        )
        self.assertEqual(
            [op for op, outcome in default_outcome.items() if outcome == "timed out"],
            [],
            msg="the amended budget still starves an operation that costs "
            f"{measured['index']:.0f}s. Ceilings on the "
            f"{smoke.TIME_BUDGET_SECONDS}s budget: "
            + ", ".join(f"{op}={s:.1f}s" for op, s in default_ceilings.items()),
        )
        for operation in ("index", "build"):
            with self.subTest(operation=operation):
                self.assertLess(
                    fast_ceilings[operation],
                    MEASURED_REBUILD_FLOOR_SECONDS,
                    msg=f"on 30s, {operation} must be squeezed below the "
                    "measured floor of a real rebuild",
                )
                self.assertGreaterEqual(
                    default_ceilings[operation],
                    MEASURED_REBUILD_CEILING_SECONDS,
                    msg=f"on {smoke.TIME_BUDGET_SECONDS}s, {operation} gets "
                    f"{default_ceilings[operation]:.1f}s and a real rebuild "
                    f"costs up to {MEASURED_REBUILD_CEILING_SECONDS:.0f}s — the "
                    "instrument still cannot afford to look",
                )

    def test_ac7_the_cli_fast_flag_selects_the_thirty_second_budget(self):
        studio = self.studio()
        for argv, expected in (
            ([], smoke.TIME_BUDGET_SECONDS),
            (["--fast"], smoke.FAST_BUDGET_SECONDS),
        ):
            with self.subTest(argv=argv):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    smoke.main(["--studio", str(studio), "--only", "boot",
                                "--json", *argv])
                payload = json.loads(buffer.getvalue())
                self.assertEqual(payload["time_budget_seconds"], expected)
                self.assertEqual(payload["fast"], bool(argv))

    def test_ac7_a_fast_run_does_not_leave_its_budget_behind(self):
        """Module-level state that outlives the run that set it would make the
        next probe silently work to 30s. The `finally` in run_all is the whole
        of this; the case exists because that kind of leak is invisible until
        somebody runs two studios in one process, which is what this suite does
        on every single case."""
        studio = self.studio()
        smoke.run_all(studio, only="boot", budget=smoke.FAST_BUDGET_SECONDS)
        self.assertEqual(smoke.active_budget(), float(smoke.TIME_BUDGET_SECONDS))
        self.assertIsNone(smoke._DEADLINE)


# =========================================================================== #
# AC7a - TIMEOUT IS NOT FAILURE. Three outcomes, and UNKNOWN is one of them.    #
# =========================================================================== #
def only_for(operation: str, seconds: float, otherwise: float = 10.0):
    """Squeeze ONE operation's ceiling and leave the rest workable.

    Patches the real ``_timeout_for``, so the probe launches the real
    subprocess against the real studio and the real ``subprocess.run`` timeout
    kills it. Nothing about the timeout branch is simulated - only the number
    of seconds it is given, which is precisely the variable AC7 amended.
    """
    return mock.patch.object(
        smoke,
        "_timeout_for",
        lambda op: seconds if op == operation else otherwise,
    )


# Every git invocation in probe_commit that stands between the probe and an
# answer, with the name the report must use when that one stalls. Squeezing the
# clock hits whichever of these happens to be slowest on the day; this list is
# how each guard gets exercised on purpose instead.
COMMIT_GIT_STEPS = (
    (("rev-parse", "--is-inside-work-tree"), "`git rev-parse`"),
    (("check-attr", "filter"), "`git check-attr`"),
    (("config", "--get"), "`git config --get`"),
    (("add", "--"), "`git add`"),
)


class AC7aThirdOutcomeTests(SmokeCase):
    # -- the representation ------------------------------------------------- #
    def test_ac7a_status_is_the_primary_field_and_ok_is_derived_from_it(self):
        """The representation decision, pinned so it cannot drift back.

        `ok: Optional[bool]` is the obvious widening and it is a trap: `if not
        result.ok` is true for both False and None, so every careless caller
        would silently count UNKNOWN as FAIL - the exact defect AC7a exists to
        prevent, arriving through the representation instead of the logic. So
        `ok` must not be a field at all. It is derived, read-only, always a
        bool, and it only ever means "passed".
        """
        names = {f.name for f in dataclasses.fields(smoke.ProbeResult)}
        self.assertIn("status", names)
        self.assertNotIn(
            "ok",
            names,
            msg="`ok` is still a stored field. A stored `ok` can be widened to "
            "Optional[bool] by the next person who needs a third outcome, and "
            "then `if not result.ok` counts UNKNOWN as FAIL everywhere at once.",
        )
        self.assertEqual(
            sorted(smoke.STATUSES), ["fail", "pass", "unknown"]
        )

        for status, expect_ok, expect_failed, expect_unknown in (
            (smoke.STATUS_PASS, True, False, False),
            (smoke.STATUS_FAIL, False, True, False),
            (smoke.STATUS_UNKNOWN, False, False, True),
        ):
            with self.subTest(status=status):
                result = smoke.ProbeResult("index", status, "d", "c", 0.1, {})
                self.assertIsInstance(
                    result.ok,
                    bool,
                    msg="`ok` must never be None; a tri-state `ok` is the trap",
                )
                self.assertIs(result.ok, expect_ok)
                self.assertIs(result.failed, expect_failed)
                self.assertIs(result.unknown, expect_unknown)
                self.assertEqual(result.as_dict()["status"], status)
                self.assertIs(result.as_dict()["ok"], expect_ok)
                with self.assertRaises(Exception):
                    result.ok = True  # type: ignore[misc]

    def test_ac7a_an_unknown_is_never_counted_as_a_failure(self):
        """One pass, one fail, one unknown. The count is 1, not 2.

        This is the whole amendment reduced to arithmetic: a run that could not
        look is not a run that found a problem.
        """
        results = [
            smoke.ProbeResult("boot", smoke.STATUS_PASS, "clear", "", 0.1, {}),
            smoke.ProbeResult("mint", smoke.STATUS_FAIL, "refused", "fix", 0.1, {}),
            smoke.ProbeResult("index", smoke.STATUS_UNKNOWN, "no answer", "run", 0.1, {}),
        ]
        self.assertEqual([r.operation for r in smoke.failures(results)], ["mint"])
        self.assertEqual([r.operation for r in smoke.unknowns(results)], ["index"])
        self.assertEqual([r.operation for r in smoke.passes(results)], ["boot"])
        self.assertEqual(smoke.exit_code_for(results), 1)
        self.assertEqual(smoke.exit_code_for(results[:1]), 0)
        self.assertEqual(
            smoke.exit_code_for([results[0], results[2]]),
            3,
            msg="a run that could not look is not a run that found a problem, "
            "and it has not earned exit 0 either",
        )

        report = smoke.format_report(results)
        self.assertIn("UNKNOWN", report)
        self.assertIn(
            "1 of 3 operation(s) FAILED",
            report,
            msg="the summary counted the UNKNOWN as a failure:\n" + report,
        )

    def test_ac7a_the_module_never_decides_by_negating_ok(self):
        """The structural half, and the reason `ok` stayed a bool.

        `not result.ok` reads as "failed" and means "did not pass". While there
        were two outcomes those were the same sentence; they are not any more,
        and the gap is silent. So the module is not allowed to write it: every
        decision has to name the status it means. `failures()` is the one place
        that defines what a failure is.
        """
        offenders = _ok_negations(ast.parse(SMOKE_PATH.read_text(encoding="utf-8")))
        self.assertEqual(
            offenders,
            [],
            msg="the module decides something by negating `.ok`: "
            + "; ".join(offenders)
            + ". After AC7a that idiom silently folds UNKNOWN into FAIL. Test "
            "`status == STATUS_FAIL` (or use failures()) and say which of the "
            "three you mean.",
        )
        self.assertIn(
            "failures",
            dir(smoke),
            msg="there must be one named place that decides what a failure is",
        )

    def test_ac7a_the_negation_scan_can_actually_fail(self):
        """Guards the guard. A scan that never fires is decoration - and this
        crew was burned this week by a negative case that survived deletion of
        the thing it targeted, because control never reached the branch."""
        for snippet in (
            "if not result.ok:\n    count += 1\n",
            "failed = [r for r in results if not r.ok]\n",
            "if result.ok == False:\n    pass\n",
            "if result.ok is False:\n    pass\n",
        ):
            with self.subTest(snippet=snippet.strip()):
                self.assertTrue(_ok_negations(ast.parse(snippet)))
        for clean in (
            "if result.status == STATUS_FAIL:\n    pass\n",
            "if result.ok:\n    pass\n",
            "if not result.evidence:\n    pass\n",
        ):
            with self.subTest(snippet=clean.strip()):
                self.assertEqual(_ok_negations(ast.parse(clean)), [])

    # -- the named regression ------------------------------------------------ #
    def test_ac7a_index_reports_unknown_not_fail_when_the_freshen_times_out(self):
        """THE REGRESSION AC7a NAMES BY HAND.

        "T37's first build got this right for BUILD and wrong for INDEX, which
        printed FAIL on a 2.0s timeout." The studio in that run could freshen an
        entry perfectly well; what it could not do was finish a 20-40s rebuild
        in the two seconds a 30s total budget had left. The instrument reported
        the studio broken because the instrument ran out of clock.

        The differential is the load-bearing part. The SAME fixture, unsqueezed,
        must pass - so the case proves the verdict tracks the timeout and not
        the studio, and cannot be satisfied by a probe that always says UNKNOWN.
        """
        healthy = self.studio()
        starved = self.studio()

        baseline = self.probe("index", healthy)
        self.assertTrue(
            baseline.ok,
            msg="the fixture must freshen cleanly for this differential to "
            f"mean anything: {baseline.detail}",
        )

        with only_for("index", 0.05):
            result = smoke.probe_index(starved)

        self.assertIs(
            result.evidence.get("freshen_timed_out"),
            True,
            msg="the case did not actually reach the timeout branch - it is "
            f"asserting about some other path. evidence={result.evidence!r}",
        )
        self.assertProbeUnknown(result, "index")
        self.assertEqual(
            result.evidence.get("rows_checked"),
            0,
            msg="R1 still requires rows_checked on every path, including this "
            "one - and a killed rebuild saw nothing",
        )
        self.assertTrue(
            any("rows_checked" in item for item in result.evidence["not_checked"]),
            msg="the UNKNOWN must name rows_checked among the things it did "
            f"not check: {result.evidence['not_checked']}",
        )
        self.assertTrue(
            any(result.evidence["target_uid"] in item
                for item in result.evidence["checked"]),
            msg="the UNKNOWN must say what it DID do - it picked a real target "
            f"and launched the freshen: {result.evidence['checked']}",
        )

    def test_ac7a_build_reports_unknown_when_the_typecheck_times_out(self):
        """The half T37 already had right, now with the word for it."""
        studio = self.studio()
        break_slow_typecheck(studio)
        with only_for("build", 0.5):
            result = smoke.probe_build(studio)
        self.assertIs(
            result.evidence.get("timed_out"),
            True,
            msg=f"the typecheck did not time out: {result.evidence!r}",
        )
        self.assertProbeUnknown(result, "tsc")
        self.assertIn("not a green build", result.detail)

    def test_ac7a_mint_reports_unknown_when_the_mint_gesture_times_out(self):
        studio = self.studio()
        with only_for("mint", 0.05):
            result = smoke.probe_mint(studio)
        self.assertIs(
            result.evidence.get("mint_timed_out"),
            True,
            msg=f"the mint gesture did not time out: {result.evidence!r}",
        )
        self.assertProbeUnknown(result)
        self.assertEqual(
            census(studio / "vault" / "files"),
            census(studio / "vault" / "files"),
        )

    def test_ac7a_commit_reports_unknown_at_every_git_step_that_can_stall(self):
        """One subtest per guard, and each stalls exactly one invocation.

        The first version of this case squeezed `_step_timeout` to 1ms and
        asserted a single UNKNOWN. It passed - and it passed with the
        `rev-parse` guard deleted, because at 1ms only `git add` was actually
        slow enough to trip and control never reached the branch the case was
        named for. A stall the probe survives by luck is not a stall.

        So the clock is not the instrument here. Each subtest replaces exactly
        one git invocation with a deterministic timeout, records that the
        replacement fired, and requires the report to name that step. Delete
        any one of these guards and the matching subtest reddens.
        """
        studio = self.studio()
        real_git = smoke._git
        for prefix, named in COMMIT_GIT_STEPS:
            with self.subTest(step=named):
                fired: list = []

                def stalling_git(studio_arg, *args, _prefix=prefix, **kwargs):
                    if tuple(args[:len(_prefix)]) == _prefix:
                        fired.append(list(args))
                        return smoke._Ran(
                            smoke._RC_TIMEOUT, "", "timed out", True,
                            ["git", *args], 0.0,
                        )
                    return real_git(studio_arg, *args, **kwargs)

                with mock.patch.object(smoke, "_git", stalling_git):
                    result = smoke.probe_commit(studio)
                self.assertTrue(
                    fired,
                    msg=f"{named} was never invoked, so this subtest is "
                    "asserting about a branch control never entered",
                )
                self.assertProbeUnknown(result)
                self.assertIn("could not be exercised", result.detail)
                self.assertIn(
                    named,
                    result.detail,
                    msg=f"the report blamed something other than {named}: "
                    f"{result.detail!r}",
                )
                self.assertEqual(
                    result.evidence.get("residue"),
                    None,
                    msg=f"a stall at {named} left residue behind: "
                    f"{result.evidence.get('residue')!r}",
                )

    def test_ac7a_a_stalled_existence_check_does_not_authorise_a_delete(self):
        """AC7a with an AC2 blast radius, and the one that actually bit.

        COMMIT removes the loose object its own staging wrote. It decides
        whether the object is its own by asking `git cat-file -e` whether the
        hash was there beforehand. Reading that check's 124 as "absent" makes a
        timeout authorise a delete - and because the scratch copy is a real
        governed body, the hash it stages to is the sample file's own committed
        blob. Measured against the unguarded build: `git fsck` came back
        `missing blob 658a81c9`. A timeout is not an answer, and it is least of
        all an answer that permits an unlink.
        """
        studio = self.studio()
        real_git = smoke._git
        asked: list = []

        def stalling_git(studio_arg, *args, **kwargs):
            if args[:2] == ("cat-file", "-e"):
                asked.append(list(args))
                return smoke._Ran(smoke._RC_TIMEOUT, "", "timed out", True,
                                  ["git", *args], 0.0)
            return real_git(studio_arg, *args, **kwargs)

        with mock.patch.object(smoke, "_git", stalling_git):
            result = smoke.probe_commit(studio)

        self.assertTrue(
            asked,
            msg="the existence check never ran, so this case never reached "
            "the branch it targets",
        )
        self.assertIs(
            result.evidence.get("probe_object_ownership_unknown"),
            True,
            msg="the probe did not record that it never established whether "
            f"the object was its own: {result.evidence!r}",
        )
        self.assertIsNone(
            result.evidence.get("removed_probe_object"),
            msg="the probe deleted a loose object it never proved it created",
        )
        oid = asked[0][2]
        self.assertEqual(
            subprocess.run(["git", "cat-file", "-e", oid], cwd=str(studio),
                           capture_output=True).returncode,
            0,
            msg=f"blob {oid[:12]} was unlinked on the strength of a timeout",
        )
        fsck = subprocess.run(["git", "fsck", "--no-progress"], cwd=str(studio),
                              capture_output=True, text=True)
        self.assertNotIn("missing blob", fsck.stdout + fsck.stderr)

    def test_ac7a_commit_does_not_call_the_filter_lossy_when_the_blob_read_stalls(self):
        """The second silent one, and the sharper of the pair.

        C3 compares the staged blob to an independently computed expectation.
        If `git cat-file blob` runs out of time the blob is b"", which is
        byte-for-byte what a filter that ate the entire file would produce - so
        a two-outcome probe prints "derived content is entering the object
        store" or "the filter is rewriting authored content" on the strength of
        its own clock.
        """
        studio = self.studio()
        real_git_bytes = smoke._git_bytes
        intercepted: list = []

        def stalling_git_bytes(studio_arg, args, timeout=20.0, env=None, stdin=None):
            if args[:2] == ["cat-file", "blob"]:
                intercepted.append(list(args))
                return smoke._RC_TIMEOUT, b"", b"timed out"
            return real_git_bytes(studio_arg, args, timeout=timeout, env=env,
                                  stdin=stdin)

        with mock.patch.object(smoke, "_git_bytes", stalling_git_bytes):
            result = smoke.probe_commit(studio)

        self.assertTrue(
            intercepted,
            msg="the blob was never read back, so this case never reached the "
            "branch it targets",
        )
        self.assertProbeUnknown(result)
        for accusation in ("entering the object store", "rewriting authored",
                           "not the sentinel-stripped form"):
            self.assertNotIn(
                accusation,
                result.detail,
                msg="the probe accused the studio's filter over bytes it never "
                f"read: {result.detail!r}",
            )

    def test_ac7a_commit_does_not_accuse_the_filter_when_the_fixed_point_times_out(self):
        """The sharpest one in this class, because it is silent.

        C4 used to read `idempotent = frc == 0 and lrc == 0 and ...`, so a
        `git hash-object` that ran out of time made the probe print "the clean
        filter is not a fixed point" - an accusation about the studio's filter,
        manufactured entirely by a slow clock, in a report a human is supposed
        to act on. Nothing in the old two-outcome shape could express what had
        actually happened.

        The stub is scoped to the ONE invocation under test and it records its
        calls, so the case proves control reached the branch rather than
        assuming it.
        """
        studio = self.studio()
        real_git_bytes = smoke._git_bytes
        intercepted: list = []

        def flaky_git_bytes(studio_arg, args, timeout=20.0, env=None, stdin=None):
            if args[:1] == ["hash-object"] and "--no-filters" in args:
                intercepted.append(list(args))
                return smoke._RC_TIMEOUT, b"", b"timed out"
            return real_git_bytes(studio_arg, args, timeout=timeout, env=env,
                                  stdin=stdin)

        with mock.patch.object(smoke, "_git_bytes", flaky_git_bytes):
            result = smoke.probe_commit(studio)

        self.assertTrue(
            intercepted,
            msg="the fixed-point check was never reached, so this case is "
            "asserting about a branch control never entered",
        )
        self.assertProbeUnknown(result)
        self.assertIsNone(
            result.evidence.get("filter_idempotent"),
            msg="a fixed-point verdict was recorded from a check that never "
            f"completed: {result.evidence.get('filter_idempotent')!r}",
        )
        self.assertNotIn(
            "not a fixed point",
            result.detail,
            msg="the probe accused the studio's clean filter on the strength "
            f"of its own timeout: {result.detail!r}",
        )

    def test_ac7a_boot_reports_unknown_when_a_lineage_cannot_be_read(self):
        """Not every UNKNOWN is a clock.

        An activation file this instrument cannot read is a lineage it did not
        check, and B4 is where that matters: an unreadable tip presents exactly
        as an unkeyed one, so a probe that does not tell them apart
        manufactures break 1 - nineteen agents unbootable - out of an I/O
        error. And a probe that says "birth clear across 21 lineages" having
        read nine of them is green-when-blind.
        """
        healthy = self.studio()
        self.assertTrue(
            self.probe("boot", healthy).ok,
            msg="the fixture must boot cleanly for this differential to mean "
            "anything",
        )

        studio = self.studio()
        break_unreadable_tip(studio)
        result = self.probe("boot", studio)

        self.assertProbeUnknown(result)
        self.assertTrue(
            result.evidence.get("unreadable_activations"),
            msg=f"the unreadable lineage was never recorded: {result.evidence!r}",
        )
        self.assertGreater(result.evidence["lineages_unchecked"], 0)
        self.assertFalse(
            result.evidence["blockers"],
            msg="an unreadable lineage was turned into a blocker on the "
            f"successor's birth: {result.evidence['blockers']}",
        )

    def test_ac7a_build_reports_unknown_when_this_machine_never_installed_tsc(self):
        """A machine that has not run `npm install` is not a studio that cannot
        compile. Failing it is one more gate refusing legitimate work, which is
        the measured disease this whole spec exists to treat."""
        studio = self.studio()
        (studio / "tropo-app" / "node_modules" / ".bin" / "tsc").unlink()
        result = self.probe("build", studio)
        self.assertProbeUnknown(result, "npm install")

    def test_ac7a_a_probe_that_crashes_is_unknown_not_fail(self):
        """A crash in THIS file is not evidence about the studio. It is the
        most direct red-when-blind available: the instrument fell over and
        blamed the thing it was pointed at."""
        studio = self.studio()

        def exploding(_studio):
            raise RuntimeError("the instrument fell over")

        with mock.patch.dict(smoke.PROBES, {"build": exploding}):
            results = smoke.run_all(studio, only="build")

        self.assertEqual(len(results), 1)
        self.assertProbeUnknown(results[0])
        self.assertIs(results[0].evidence.get("probe_crashed"), True)
        self.assertEqual(smoke.exit_code_for(results), 3)

    # -- reporting ----------------------------------------------------------- #
    def test_ac7a_the_report_marks_three_outcomes_and_never_calls_unknown_red(self):
        results = [
            smoke.ProbeResult("boot", smoke.STATUS_PASS, "clear", "", 0.1, {}),
            smoke.ProbeResult("index", smoke.STATUS_UNKNOWN, "no answer",
                              "run it by hand", 0.2, {"degraded": True}),
        ]
        report = smoke.format_report(results)
        self.assertIn("[ PASS  ]", report)
        self.assertIn("[UNKNOWN]", report)
        self.assertNotIn("FAIL", report)
        self.assertIn(
            "run it by hand",
            report,
            msg="an UNKNOWN's cure must reach the report; the next action "
            "after 'could not determine' is as concrete as after a failure",
        )
        self.assertNotIn(
            "all 2 operation(s) PASSED",
            report,
            msg="a run with an UNKNOWN in it has not earned a clean bill of "
            "health:\n" + report,
        )

    def test_ac7a_json_carries_the_status_the_counts_and_the_exit_code(self):
        studio = self.studio()
        (studio / "tropo-app" / "node_modules" / ".bin" / "tsc").unlink()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = smoke.main(["--studio", str(studio), "--only", "build",
                               "--json"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 3)
        self.assertEqual(payload["exit_code"], 3)
        self.assertEqual(payload["status"], smoke.STATUS_UNKNOWN)
        self.assertEqual(payload["unknown"], 1)
        self.assertEqual(payload["failed"], 0)
        self.assertIs(
            payload["ok"],
            False,
            msg="the top-level `ok` must keep meaning 'every probe passed', or "
            "a reader written against the two-outcome payload starts counting "
            "UNKNOWNs as green",
        )
        row = payload["results"][0]
        self.assertEqual(row["status"], smoke.STATUS_UNKNOWN)
        self.assertIs(row["ok"], False)
        self.assertTrue(row["evidence"]["not_checked"])

    def test_ac7a_the_cli_exit_code_separates_unknown_from_failure(self):
        """0 / 1 / 3, and the argument for 3 is in the module docstring.

        Exit 0 is the positive claim "all five were exercised and all five
        worked" and a blind run has not earned it. Exit 1 is the positive claim
        "this studio has a problem" and a blind run has not earned that either.
        Neither is true, so the third outcome gets a third code.
        """
        healthy = self.studio()
        blind = self.studio()
        (blind / "tropo-app" / "node_modules" / ".bin" / "tsc").unlink()
        broken = self.studio()
        break_forged_seal(broken)
        both = self.studio()
        break_forged_seal(both)
        (both / "tropo-app" / "node_modules" / ".bin" / "tsc").unlink()

        with redirect_stdout(io.StringIO()):
            self.assertEqual(smoke.main(["--studio", str(healthy)]), 0)
            self.assertEqual(smoke.main(["--studio", str(blind)]), 3)
            self.assertEqual(smoke.main(["--studio", str(broken)]), 1)
            self.assertEqual(
                smoke.main(["--studio", str(both)]),
                1,
                msg="a found problem is the strongest fact in a run; FAIL "
                "dominates UNKNOWN",
            )

    # -- the anti-laundering direction --------------------------------------- #
    def test_ac7a_a_determined_break_is_still_fail_and_not_softened(self):
        """The amendment read backwards is a way to keep every run quiet.

        A probe could satisfy "never report red while blind" by never reporting
        red at all. So the plants that carry a real, reproducible break must
        still come back FAIL, and `unknowns()` must be empty for them.
        """
        studio = self.studio()
        break_forged_seal(studio)
        break_typecheck(studio)
        results = {r.operation: r for r in smoke.run_all(studio)}
        for operation in ("index", "mint", "build"):
            with self.subTest(operation=operation):
                self.assertEqual(
                    results[operation].status,
                    smoke.STATUS_FAIL,
                    msg=f"{operation} answered "
                    f"{results[operation].status!r} over a determined, "
                    "reproducible break. UNKNOWN is for what this instrument "
                    "could not tell, not for what it would rather not say: "
                    + results[operation].detail,
                )
        self.assertEqual(smoke.exit_code_for(list(results.values())), 1)


def _ok_negations(tree) -> list:
    """Every place a decision is made by negating or false-comparing `.ok`."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            operand = node.operand
            if isinstance(operand, ast.Attribute) and operand.attr == "ok":
                found.append(ast.unparse(node))
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Attribute):
            if node.left.attr != "ok":
                continue
            for operator, comparator in zip(node.ops, node.comparators):
                if isinstance(operator, (ast.Eq, ast.Is, ast.NotEq, ast.IsNot)) \
                        and isinstance(comparator, ast.Constant) \
                        and comparator.value is False:
                    found.append(ast.unparse(node))
    return found


# =========================================================================== #
# R1 - operation 3 must assert it SAW something (break 8)                       #
# =========================================================================== #
class R1IndexSawSomethingTests(SmokeCase):
    def test_r1_probe_index_records_rows_checked_and_it_is_measured_not_declared(self):
        """The sharpest case in the suite.

        Break 8: a rebuild that succeeded while checking nothing, on an unknown
        number of machines at once, because `.tropo-studio/locks/` is gitignored
        (`.gitignore:44`) and the digest that blinds the gates is per-machine.
        Three validator checks printed `0 rows checked` and PASSED.

        So rows_checked must be a measurement, not a constant. Two used studios
        of different sizes are handed to the same probe: the number has to move
        with the studio, and it can never exceed the rows that exist to be
        checked. A hardcoded `{"rows_checked": 4821}` satisfies "greater than
        zero" and fails this.
        """
        small = self.studio()
        big = self.studio("bigger")

        small_result = self.probe("index", small)
        big_result = self.probe("index", big)
        self.assertTrue(small_result.ok, msg=small_result.detail)
        self.assertTrue(big_result.ok, msg=big_result.detail)

        small_rows = small_result.evidence.get("rows_checked")
        big_rows = big_result.evidence.get("rows_checked")
        for label, value in (("small", small_rows), ("big", big_rows)):
            with self.subTest(studio=label):
                self.assertIsInstance(
                    value, int, msg="probe_index must record rows_checked (R1)"
                )
                self.assertGreater(value, 0)

        available_small = len(index_rows(small))
        available_big = len(index_rows(big))
        self.assertGreater(
            available_big, available_small, "the fixtures must differ in size"
        )
        self.assertLessEqual(
            small_rows,
            available_small,
            msg=f"rows_checked={small_rows} exceeds the {available_small} rows that "
            "exist; the number is not coming from this studio",
        )
        self.assertLess(
            small_rows,
            big_rows,
            msg=f"rows_checked did not move with the studio ({small_rows} vs "
            f"{big_rows} over {available_small} vs {available_big} rows); a "
            "constant here is break 8 wearing the instrument's badge",
        )

    def test_r1_zero_rows_checked_is_a_failure_not_a_pass(self):
        """Break 8, replayed. The seal in `.tropo-studio/locks/` no longer
        describes what is on disk, which is the state a machine reaches simply by
        having a different history from its neighbour. The index operation cannot
        see the surfaces, and the one answer it must not give is PASS."""
        studio = self.studio()
        break_stale_seal(studio)
        result = self.probe("index", studio)
        self.assertProbeFails(result, "index")
        self.assertEqual(
            result.evidence.get("rows_checked", 0),
            0,
            msg="the probe could not read the surfaces, so rows_checked must be "
            f"0 and the verdict FAIL - got {result.evidence!r}",
        )

    def test_r1_the_pass_condition_includes_having_seen_something(self):
        """The invariant, stated once and checked over every studio this suite
        builds, in both directions.

        Downward: `ok` and `rows_checked == 0` may never be true together - a
        probe that exits zero while examining nothing is break 8 reproduced
        inside the instrument built to catch it.

        Upward: `rows_checked` may never exceed the rows that exist to be
        checked. Both halves are needed, because the cheapest way past the
        downward half is a fabricated constant, and a fabricated constant is the
        same lie in the other direction - `{"rows_checked": 4821}` in a studio
        holding 175 rows is not a measurement of anything.
        """
        studios = [self.studio(), self.studio(), self.studio()]
        break_stale_seal(studios[1])
        break_forged_seal(studios[2])
        for position, studio in enumerate(studios):
            with self.subTest(studio=position):
                available = len(index_rows(studio))
                result = self.probe("index", studio)
                counted = result.evidence.get("rows_checked")
                self.assertIsInstance(
                    counted,
                    int,
                    msg="probe_index must record rows_checked in evidence on "
                    "every path, including the failing ones (R1)",
                )
                if counted == 0:
                    self.assertFalse(
                        result.ok,
                        msg="rows_checked=0 with ok=True is the exact defect R1 "
                        "was written to forbid",
                    )
                self.assertLessEqual(
                    counted,
                    max(available, len(index_rows(studio))),
                    msg=f"rows_checked={counted} over a studio that holds "
                    f"{available} rows. The number did not come from this "
                    "studio, which makes it decoration on a verdict.",
                )


# =========================================================================== #
# ADR-063 - INDEX is where a legacy-digest-door reading gets taken              #
# =========================================================================== #
class LegacyDigestDoorReadingTests(SmokeCase):
    def test_the_door_reading_is_taken_before_the_probe_rebuilds_the_seal(self):
        """Ordering is the correctness of this reading, not a detail.

        ADR-063 owes an instrument reporting how many metas still need the
        superseded-format digest door. There is no bus to count them on -
        `.tropo-studio/locks/` is gitignored and the seal is per-machine - so
        the count is the union of per-machine readings, and INDEX is where one
        gets taken because it is the operation agents already run anywhere.

        The probe's own `--only` re-stamps the seal in the current format. A
        reading taken after it would report every machine as healed by the act
        of measuring it, and the derived-state guard then puts the old seal
        back - so the machine would still need the door, the reading would say
        it did not, and the crew would close the door on that. This is the same
        shape as break 8: an instrument reporting green because of where it was
        pointed rather than because of what is true.
        """
        studio = self.studio()
        order: list[str] = []
        real_run = smoke._run

        def recording_run(argv, cwd, timeout, env=None, stdin=None):
            order.append(" ".join(str(part) for part in argv))
            return real_run(argv, cwd, timeout, env=env, stdin=stdin)

        with mock.patch.object(smoke, "_run", recording_run):
            result = smoke.probe_index(studio)

        read_at = [
            position for position, command in enumerate(order)
            if smoke.LEGACY_DIGEST_DOOR_TOOL_REL in command
        ]
        rebuilt_at = [
            position for position, command in enumerate(order)
            if smoke.REBUILD_TOOL_REL in command
        ]
        self.assertTrue(read_at, msg=f"no door reading was taken: {order}")
        self.assertTrue(rebuilt_at, msg=f"the probe never rebuilt: {order}")
        self.assertLess(
            min(read_at),
            min(rebuilt_at),
            msg="the door reading was taken after the probe's own rebuild, so "
            "it describes the seal the probe just wrote and then rolled back, "
            f"not the seal this machine holds: {order}",
        )

        reading = result.evidence.get("legacy_digest_door_report")
        self.assertIsInstance(reading, dict)
        self.assertTrue(
            reading.get("available"),
            msg=f"the reading did not come back: {reading!r}",
        )
        self.assertIn(
            result.evidence.get("legacy_digest_door"),
            {
                "current-sealed", "legacy-sealed", "unrecognised-seal",
                "unreadable-meta", "no-meta",
            },
            msg=f"the probe recorded no usable verdict: {reading!r}",
        )
        self.assertIn(
            result.evidence.get("legacy_digest_door_needed"),
            (True, False, None),
        )


# =========================================================================== #
# R3 - operation 1 exercises the SUCCESSOR's birth                              #
# =========================================================================== #
class R3SuccessorBirthTests(SmokeCase):
    def test_r3_boot_passes_when_the_next_generation_could_actually_be_born(self):
        """The baseline the two plants below are differentials against. A real
        keyed lineage (G96 -> G97 -> G98, keys and predecessor links intact),
        terminal at the tip, with an indexed transfer: G99 can be born."""
        studio = self.studio()
        result = self.probe("boot", studio)
        self.assertTrue(
            result.ok,
            msg=f"a bootable lineage was reported unbootable: {result.detail}",
        )
        self.assertTrue(
            result.evidence,
            msg="probe_boot recorded no evidence; 'it passed' is not a measurement",
        )

    def test_r3_an_entry_still_active_at_handoff_would_halt_the_successor(self):
        """The incident of 2026-07-31, replayed.

        Argus A142 completed his retirement - reflection written, memory folded,
        lanes handed off, broadcast sent - and his activation entry `b8a9f6fe`
        still said `status: active`. That would have HALTED A143 at the ADR-016
        hard gate (`.tropo/boot-config.md:54`: two live generations of one agent
        is a governance violation).

        Note what this asks for that the existing fleet-boot-health check does
        not: that check SKIPS a non-terminal lineage, on the sound reasoning that
        an active predecessor is ADR-016 working. R3 says the smoke probe must
        look at the handoff itself - an entry carrying `retired_at`,
        `closure_reason` and a `transfer_uid` while still declaring itself active
        is a retirement that stopped one field short, and the successor is the
        one who pays.
        """
        studio = self.studio("active-at-handoff")
        result = self.probe("boot", studio)
        self.assertProbeFails(result, METIS_SUCCESSOR_ENTRY)
        self.assertReportNamesTheCure(result)

    def test_r3_a_transfer_stub_invisible_to_the_index_is_caught_before_birth(self):
        """The same hour, the same retirement, the other half.

        A142's auto-generated transfer stub `6132a8bb` never reached the index,
        so the successor's first act - read the transfer - ran through an
        unindexed pointer. The Vault's own rule: an entry absent from the index
        union does not exist in the Vault. The stub is on disk here and the
        pointer resolves to nothing, which is precisely how it shipped.
        """
        studio = self.studio()
        orphan = break_orphan_transfer(studio)
        self.assertTrue(orphan.is_file(), "the stub must exist on disk")
        self.assertNotIn(
            ORPHAN_TRANSFER_UID,
            index_rows(studio),
            "the stub must be invisible to the index",
        )
        result = self.probe("boot", studio)
        self.assertProbeFails(result, ORPHAN_TRANSFER_UID)
        self.assertReportNamesTheCure(result)

    def test_r3_boot_is_read_only_about_the_successor_it_reports_on(self):
        """A dry-run birth. If the probe actually opened a generation to find out
        whether one could be opened, running the smoke test would become the
        thing ADR-016 refuses."""
        studio = self.studio()
        before = governed_census(studio)
        before_rows = set(index_rows(studio))
        self.probe("boot", studio)
        self.assertEqual(
            before, governed_census(studio), msg="probe_boot wrote to the studio"
        )
        self.assertEqual(before_rows, set(index_rows(studio)))


# =========================================================================== #
# AC5 - THE PLANT. The breaks of 2026-07-30/31, replayed against the probe.     #
# =========================================================================== #
class AC5PlantTests(SmokeCase):
    def test_ac5a_an_unkeyed_tip_no_longer_blocks_a_birth_because_nothing_does(self):
        """Break 1, replayed — and the replay had to change when the world did.

        THE ORIGINAL INCIDENT STANDS AS HISTORY. The G2 hardening made
        predecessor derivation require a keyed predecessor, only two activation
        entries were ever retrofitted with keys, and nineteen agents could not
        hand off to a successor. It shipped silently and sat for three days,
        because agent BIRTH is the only operation that trips it and only one
        agent had been born since.

        THE MECHANISM THAT CAUSED IT IS GONE. Birth moved to
        `tropo-lineage.py born` on 2026-08-06: standard library only, no index,
        no mint, no key, enforced by a test. An unkeyed tip cannot block a
        birth because nothing can.

        So this fixture — a keyed lineage whose terminal generation is unkeyed —
        is no longer a blocker, and a probe that still called it one was
        producing exactly the false red this suite exists to prevent. It did:
        it reported metis and orpheus as unable to produce a successor while
        both could, and printed a cure naming a tool every boot contract
        forbids (filed 7c31d9a4).

        The probe now RUNS the birth instead of modelling the rule, so this
        asserts the condition is correctly NOT a blocker. The paired test below
        asserts it still fails when a birth genuinely cannot happen — together
        they are the discrimination the old single assertion had lost.
        """
        studio = self.studio("unkeyed-successor")
        keyed = (studio / "vault" / "files" / "8aafbfbb.md").read_text(encoding="utf-8")
        unkeyed = (studio / "vault" / "files" / f"{METIS_SUCCESSOR_ENTRY}.md").read_text(encoding="utf-8")
        self.assertIn("agent_public_key:", keyed, "the lineage must have been keyed")
        self.assertNotIn("agent_public_key:", unkeyed, "the tip must be unkeyed")

        result = self.probe("boot", studio)
        self.assertNotIn(
            "cannot derive from its predecessor", str(result),
            "an unkeyed tip was reported as blocking a birth. Nothing blocks a "
            "birth any more; a probe that says otherwise is the false red that "
            "cost this crew a P0 report (7c31d9a4)")

    def test_ac5a2_the_birth_probe_still_fails_when_a_birth_really_cannot_happen(self):
        """The control, without which the test above passes for free.

        Asserting "no blocker" proves nothing on a probe that can no longer
        produce one. A lineage file that cannot be parsed is the one condition
        `born` genuinely refuses — guessing a generation out of an unreadable
        file is the single destructive move on that path — so it is what the
        probe must still surface.
        """
        import importlib.util as _il
        spec = _il.spec_from_file_location("smoke_birth_probe", SMOKE_PATH)
        module = _il.module_from_spec(spec)
        sys.modules["smoke_birth_probe"] = module
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "agents" / "ghost").mkdir(parents=True)
            (root / "agents" / "ghost" / "lineage.jsonl").write_text(
                "{ not json at all\n", encoding="utf-8")
            (root / "vault" / "tools").mkdir(parents=True)
            shutil.copy2(SMOKE_PATH.parent / "tropo-lineage.py",
                         root / "vault" / "tools" / "tropo-lineage.py")
            reason = module._dry_run_birth(root, "ghost")

        self.assertIsNotNone(
            reason, "an unreadable lineage file must still be reported — the "
                    "probe has stopped discriminating")
        self.assertIn("cannot be born", reason)

    def test_ac5b_fresh_clone_index_creation_refuses_on_a_dirty_file(self):
        """Break 2, replayed.

        Fresh-clone index creation refused on any dirty governed file - live
        since the ratchet landed, which means every new machine and every fork.
        The fixture is what a new machine actually has: a checkout, no index, no
        per-machine seal, nothing rendered, and one governed file edited.
        """
        studio = self.studio("fresh-clone")
        self.assertFalse(
            (studio / "vault" / "00-index.jsonl").exists(),
            "a fresh clone has no index; that is the point",
        )
        self.assertTrue(git_state(studio).strip(), "the checkout must be dirty")

        result = self.probe("index", studio)
        self.assertProbeFails(result)
        self.assertTrue(command_lines(result.cure))

    def test_ac5c_a_used_studio_is_not_corrupt_just_because_disk_differs_from_the_blob(self):
        """Break 3, replayed - and this one is a PASS assertion on purpose.

        059f2c68 compared raw worktree bytes against the committed blob. On a
        fresh checkout those are equal, so it passed CI. On a used studio the
        nav block is rendered on disk and stripped by the clean filter at the git
        boundary, so they are NOT equal - and 059f2c68 called that corruption and
        broke minting studio-wide.

        This fixture is rendered by the studio's own renderer and its filter is
        installed, so the divergence below is real and legitimate. The commit and
        mint probes must both survive it. A probe built the way 059f2c68 was
        fails here, which is the only way to catch that break at all: it is a
        false positive, so only a green assertion can see it.
        """
        studio = self.studio()
        rendered = nav_blocked(studio)
        self.assertTrue(
            rendered,
            "no governed file carries a rendered nav block, so this fixture is a "
            "fresh checkout and the plant would be vacuous - which is precisely "
            "the blind spot that let 059f2c68 through CI",
        )
        target = rendered[0]
        relative = target.relative_to(studio).as_posix()
        raw = target.read_bytes()

        git(studio, "add", "--", relative)
        blob = subprocess.run(
            ["git", "-C", str(studio), "show", f":{relative}"], capture_output=True
        ).stdout
        git(studio, "reset", "-q", "--", relative)
        self.assertNotEqual(
            raw, blob, "the clean filter is not wired; the plant would be vacuous"
        )
        self.assertIsNone(
            NAV_BLOCK_RE.search(blob),
            "the rendered region must be gone from the blob; that divergence is "
            "the whole condition under test",
        )

        commit_result = self.probe("commit", studio)
        self.assertTrue(
            commit_result.ok,
            msg="the commit probe called a correctly-filtered round trip a "
            f"failure - that IS 059f2c68: {commit_result.detail}",
        )
        mint_result = self.probe("mint", studio)
        self.assertTrue(
            mint_result.ok,
            msg="minting refused on a studio with rendered nav blocks, which is "
            f"break 3 verbatim: {mint_result.detail}",
        )

    def test_ac5c_a_filter_that_eats_governed_content_is_caught(self):
        """Break 3's root cause, from the other side - operation 4's actual job.

        The clean filter here strips the nav block AND everything after it. A
        commit probe whose scratch content is fresh-checkout-shaped never sees
        the loss: no nav block, no divergence, green. Only a probe that puts
        used-studio content through the round trip finds it. That asymmetry is
        case 3 of 1f29bcfb - the author's environment is a kind of mock - aimed
        at the instrument itself.
        """
        studio = self.studio()
        break_lossy_clean_filter(studio)
        result = self.probe("commit", studio)
        self.assertProbeFails(result)
        self.assertReportNamesTheCure(result)

    def test_ac5_break8_a_gate_that_passes_while_checking_nothing(self):
        """Break 8, replayed at the run level.

        `0 rows checked` and PASS, on an unknown number of machines, for an
        unknown length of time, because the digest that blinds the gates lives in
        a gitignored directory and one agent's repair cannot reach another's
        machine. A gate that fails is a bug; a gate that passes while checking
        nothing is a bug nobody files.
        """
        studio = self.studio()
        break_stale_seal(studio)
        results = {result.operation: result for result in smoke.run_all(studio)}
        self.assertProbeFails(results["index"])
        self.assertFalse(
            all(result.ok for result in results.values()),
            msg="a blinded studio reported a clean bill of health",
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(smoke.main(["--studio", str(studio)]), 1)

    def test_ac5_break9_the_cure_the_probe_prints_must_actually_cure(self):
        """Break 9, replayed - and this is the assertion that carries it.

        `2dcadf62` renamed a digest tag with no migration and deadlocked index
        authority studio-wide for 2h17m. What made it a deadlock rather than a
        breakage: the rebuild that re-stamps the seal is gated behind the same
        check the rename broke, so the only sanctioned repair path could not run.
        Measured at the time: `tropo-rebuild-index.py --apply` exited 1 on every
        machine, and nothing said so.

        So it is not enough for the probe to fail with a cure. The cure has to
        work. This runs it and re-probes.
        """
        studio = self.studio()
        break_forged_seal(studio)

        deadlocked = _run_tool(studio, "vault/tools/tropo-rebuild-index.py", "--apply")
        self.assertEqual(
            deadlocked.returncode,
            1,
            msg="the fixture is not in the deadlocked state break 9 describes",
        )

        result = self.probe("index", studio)
        self.assertProbeFails(result)
        commands = command_lines(result.cure)
        self.assertTrue(commands, f"no runnable cure in {result.cure!r}")

        for command in commands:
            subprocess.run(
                shlex.split(command),
                cwd=str(studio),
                capture_output=True,
                text=True,
                timeout=300,
            )

        repaired = self.probe("index", studio)
        self.assertTrue(
            repaired.ok,
            msg="the studio is still broken after running the probe's own cure "
            f"({commands}); a repair path gated behind the check it broke is the "
            f"whole of break 9. detail={repaired.detail!r}",
        )
        self.assertGreater(repaired.evidence.get("rows_checked", 0), 0)

    def test_ac5_break9_mint_is_blocked_by_the_same_deadlock_and_says_so(self):
        """af6c53df's own table routes break 9 to operations 2 AND 3: minting
        freshens the index, so a studio that cannot index cannot mint. A mint
        probe that reports green here is not touching the index at all, which
        means it is not doing the operation break 3 broke."""
        studio = self.studio()
        break_forged_seal(studio)
        result = self.probe("mint", studio)
        self.assertProbeFails(result)
        self.assertReportNamesTheCure(result)

    def test_ac5_the_build_probe_never_reports_green_because_it_could_not_look(self):
        """Operation 5, and the same disease as break 8 in a different organ.

        The cockpit typecheck was caught by hand on 2026-07-30. A build probe
        that shells out and treats 'the command did not run' as success is the
        instrument reporting green over a world it never saw.
        """
        studio = self.studio()
        break_typecheck(studio)
        result = self.probe("build", studio)
        self.assertProbeFails(result)
        self.assertReportNamesTheCure(result)

        missing = self.studio()
        (missing / "tropo-app" / "package.json").unlink()
        self.assertFalse(
            self.probe("build", missing).ok,
            msg="no cockpit and no toolchain is not a passing build",
        )


# =========================================================================== #
# ORIENT - operation 6. Can this studio answer a question about itself?         #
#                                                                               #
# Metis G98, on why this probe exists at all: "We had NO instrument that would   #
# ever have reported this. The unit tests pass - they inject their own           #
# projection. The validator passes - it does not call orient(). tropo-smoke      #
# passes BOOT and COMMIT - it does not exercise the crown."                      #
#                                                                               #
# So every case below drives the REAL deterministic core out of the studio it    #
# is handed, over the real composed index, through a real viewer carrying a      #
# real principal the installed authority resolves. Nothing is injected and       #
# nothing is doubled. The breaks are on copies.                                  #
# =========================================================================== #

# Every stage the ORIENT driver can report, and the state its verdict is
# specified to claim - or None where it is specified to claim NONE.
#
# Module-level because two cases read it and they must read the SAME one: one
# asks whether every branch lands on exactly one state or deliberately on no
# state, the other asks whether the branches that DO claim a state hand the
# reader a command they can attribute. A second copy of this table would let
# the two drift and each stay green over a different set of branches.
#
# It is also the only way the two guard branches get exercised at all.
# ``adapters`` and ``NODE_NOT_FOUND`` cannot be reached from any on-disk state
# - both are documented in the probe as guards against library behaviour that
# does not exist today - so a payload through ``_orient_verdict`` is the only
# thing that will ever read their prose back.
ORIENT_BRANCH_TABLE = (
    ("start", {"stage": "start"}, None),
    ("corpus-unreadable",
     {"stage": "corpus", "corpus_readable": False,
      "error_kind": "DatabaseError", "error_message": "planted"},
     smoke.ORIENT_NO_CORPUS),
    ("corpus-empty",
     {"stage": "corpus", "corpus_readable": True, "corpus_entry_count": 0},
     smoke.ORIENT_NO_CORPUS),
    ("import-unprovisioned",
     {"stage": "import", "error_kind": "ModuleNotFoundError",
      "error_message": "planted", "missing_module": "yaml"},
     None),
    ("import-substrate",
     {"stage": "import", "error_kind": "SyntaxError",
      "error_message": "planted", "missing_module": "lib.distiller"},
     None),
    ("authority-absent",
     {"stage": "authority", "corpus_readable": True,
      "authority_installed": False},
     smoke.ORIENT_NO_AUTHORITY),
    ("authority-unevaluable",
     {"stage": "authority", "corpus_readable": True,
      "error_kind": "OSError", "error_message": "planted"},
     None),
    ("viewer",
     {"stage": "viewer", "corpus_readable": True,
      "authority_installed": True, "authority_principal_count": 0},
     None),
    ("driver-crashed",
     {"stage": "driver-crashed", "error_kind": "RuntimeError",
      "error_message": "planted"},
     None),
    ("graph-unavailable-anywhere",
     {"stage": "visibility", "corpus_readable": True,
      "authority_installed": True, "error_kind": "GraphError",
      "error_code": "GRAPH_UNAVAILABLE", "error_message": "planted"},
     smoke.ORIENT_NO_CORPUS),
    ("budget-invalid",
     {"stage": "orient", "corpus_readable": True,
      "authority_installed": True, "task_uid": "abcd1234",
      "error_kind": "GraphError", "error_code": "BUDGET_INVALID",
      "error_message": "planted"},
     None),
    ("adapters",
     {"stage": "adapters", "corpus_readable": True,
      "authority_installed": True, "error_kind": "GraphError",
      "error_code": "SOMETHING_ELSE", "error_message": "planted"},
     smoke.ORIENT_STILL_REFUSING),
    ("visibility",
     {"stage": "visibility", "corpus_readable": True,
      "authority_installed": True, "viewer_principal_uid": "7b921d17",
      "error_kind": "GraphError",
      "error_code": "VISIBILITY_UNRESOLVED", "error_message": "planted"},
     smoke.ORIENT_STILL_REFUSING),
    ("anchor",
     {"stage": "anchor", "corpus_readable": True,
      "authority_installed": True, "viewer_principal_uid": "7b921d17",
      "visible_segment_count": 4,
      "anchors_considered": [{"uid": "abcd1234", "structural": 3,
                              "visible": 0}]},
     None),
    ("orient-node-not-found",
     {"stage": "orient", "corpus_readable": True,
      "authority_installed": True, "task_uid": "abcd1234",
      "error_kind": "GraphError", "error_code": "NODE_NOT_FOUND",
      "error_message": "planted"},
     smoke.ORIENT_STILL_REFUSING),
    ("orient-typed-refusal",
     {"stage": "orient", "corpus_readable": True,
      "authority_installed": True, "task_uid": "abcd1234",
      "error_kind": "GraphError", "error_code": "QUERY_UNSUPPORTED",
      "error_message": "planted"},
     smoke.ORIENT_STILL_REFUSING),
    ("oriented-empty",
     {"stage": "oriented", "corpus_readable": True,
      "authority_installed": True, "task_uid": "abcd1234",
      "item_count": 0, "visible_neighbours": 3, "structural_neighbours": 5},
     smoke.ORIENT_STILL_REFUSING),
    ("oriented-unranked",
     {"stage": "oriented", "corpus_readable": True,
      "authority_installed": True, "task_uid": "abcd1234",
      "item_count": 4, "visible_neighbours": 3,
      "structural_neighbours": 5, "ranked_descending": False,
      "tilt": "none", "top": [{"uid": "z", "provenance": "ref"}]},
     smoke.ORIENT_STILL_REFUSING),
    ("oriented-green",
     {"stage": "oriented", "corpus_readable": True,
      "authority_installed": True, "task_uid": "abcd1234",
      "item_count": 4, "visible_neighbours": 3,
      "structural_neighbours": 5, "ranked_descending": True,
      "tilt": "none", "visible_segment_count": 4,
      "viewer_principal_uid": "7b921d17", "task_uid_rule": "planted",
      "top": [{"uid": "z", "provenance": "ref"}]},
     None),
)


class ORIENTTests(SmokeCase):
    # -- the pass ---------------------------------------------------------- #
    def test_orient_answers_a_question_about_this_studio(self):
        """The green, and what has to be true for it to mean anything.

        A ranked, NON-EMPTY circle for a real anchor, reported with the anchor
        it used - a probe that cannot say which uid it oriented on is a probe
        whose green cannot be reproduced by hand.
        """
        studio = self.studio()
        result = self.probe("orient", studio)
        self.assertEqual(
            result.status, smoke.STATUS_PASS,
            msg=f"orient did not pass on a healthy studio: {result.detail}",
        )
        evidence = result.evidence
        self.assertGreater(
            int(evidence.get("item_count") or 0), 0,
            msg="a pass over an EMPTY circle is the green-while-blind this "
            "probe was written to end",
        )
        self.assertIs(evidence.get("ranked_descending"), True)
        self.assertTrue(evidence.get("task_uid"), msg="which uid did it orient on?")
        # Named as the circle's SUBJECT, not merely present somewhere in the
        # sentence. The anchor's uid also turns up inside the top member's
        # provenance string ("governed_by-of-task:<anchor>"), so a bare
        # substring check stays green over a report that has stopped saying
        # what it oriented on - measured, by mutating exactly that away.
        self.assertIn(
            f"for {evidence['task_uid']}", result.detail,
            msg="the pass does not say which uid the circle is FOR, so nobody "
            f"can reproduce it by hand: {result.detail!r}",
        )
        self.assertTrue(
            evidence.get("viewer_principal_uid"),
            msg="a viewer with no principal is refused by visible_segments; a "
            "pass has to name the principal it was granted",
        )
        self.assertIs(evidence.get("authority_installed"), True)

    def test_orient_reports_the_same_anchor_and_the_same_circle_every_run(self):
        """Deterministic, or the green is a coin toss with good odds.

        ``orient_deterministic`` promises a byte-identical orientation for the
        same (task, viewer, budget) over the same substrate. This pins that the
        PROBE inherits it: same anchor, same membership, same canonical digest.
        A probe that picked its anchor at random would satisfy every other case
        here and fail this one.
        """
        studio = self.studio()
        first = self.probe("orient", studio)
        second = self.probe("orient", studio)
        for key in ("task_uid", "viewer_principal_uid", "item_count",
                    "canonical_sha256"):
            with self.subTest(key=key):
                self.assertEqual(
                    first.evidence.get(key), second.evidence.get(key),
                    msg=f"two runs disagreed about {key}",
                )
        self.assertRegex(
            str(first.evidence.get("canonical_sha256") or ""), r"^[0-9a-f]{64}$",
            msg="the digest of the orientation is the evidence a circle was "
            "actually composed rather than a count invented",
        )

    def test_orient_is_wired_to_the_studios_own_orient_deterministic(self):
        """The wiring test, and the one that would catch a probe that fakes it.

        The studio's own ``lib/distiller.py`` is made to refuse with a typed
        error. A probe that really calls ``orient_deterministic`` from the
        studio it was handed turns red; a probe that reimplemented the walk, or
        asserted something cheaper, or read a cached result, stays green. There
        is no way to pass this without the call.
        """
        studio = self.studio()
        self.assertEqual(self.probe("orient", studio).status, smoke.STATUS_PASS)

        broken = self.studio()
        break_orient_into_a_typed_refusal(broken)
        result = self.probe("orient", broken)
        self.assertProbeFails(result, "VISIBILITY_UNRESOLVED")
        self.assertIn("planted", result.detail)
        self.assertEqual(result.evidence.get("stage"), "orient")
        self.assertReportNamesTheCure(result)

    # -- the three states, one case each ------------------------------------ #
    def test_orient_state_no_corpus_belongs_to_the_index_rebuilder(self):
        """STATE 1 of 3. Nobody can orient over nothing, and somebody owns it.

        Four readings of one state, because a corpus can be missing four ways
        and all four are the same person's: absent, present and not a
        database, present and empty, and present with a row that will not
        decode. One owner, one cure - and explicitly NOT the authority's
        problem and NOT retrieval's, which is the entire reason the state is
        named out loud instead of folded into a bare UNKNOWN.

        Two of these four used to come back as something else, measured:

        * not-a-database produced "the orientation driver raised ... a fault
          in this instrument", whose cure re-runs the instrument;
        * an empty index walked to "none of the 0 most connected entries has a
          single neighbour inside the audience", which tells the reader to
          widen an audience over a corpus with nothing in it.

        Both named the wrong owner, which is the failure mode this state
        exists to end.

        THE CONTROL IS WHY THIS CASE IS TRUSTWORTHY. Each reading asserts what
        the corpus actually IS - through the same read-only count the driver
        takes - before it asserts what the probe said about it. A plant that
        left a readable corpus behind would send the probe down a different
        branch, and the case would go green while measuring something else.
        This file has been burned by exactly that twice.
        """
        control = self.studio()
        self.assertGreater(
            corpus_entry_count(control) or 0, 0,
            msg="the control for all four readings: the UNPLANTED fixture has "
            "a readable corpus, so an unreadable one below is the plant and "
            "not a barren fixture",
        )
        self.assertEqual(
            self.probe("orient", control).status, smoke.STATUS_PASS,
            msg="and the unplanted fixture oriented, so nothing below is "
            "measuring a studio that was already in some other state",
        )

        with self.subTest(reading="the composed index is not on disk"):
            studio = self.studio()
            index = break_the_corpus_absent(studio)
            self.assertFalse(index.exists(), msg="the plant left the index in place")
            self.assertIsNone(
                corpus_entry_count(studio),
                msg="no index on disk must read as no corpus at all",
            )
            result = self.probe("orient", studio)
            self.assertOrientState(
                result, smoke.ORIENT_NO_CORPUS, "composed index",
            )

        with self.subTest(reading="the composed index is not a database"):
            studio = self.studio()
            index = break_the_corpus_unopenable(studio)
            self.assertTrue(
                index.is_file(),
                msg="this reading is about a file that IS there and will not "
                "open; deleting it would be the reading above",
            )
            self.assertIsNone(
                corpus_entry_count(studio),
                msg="the plant left a database a reader can still count rows "
                "in, so it planted nothing",
            )
            result = self.probe("orient", studio)
            self.assertOrientState(result, smoke.ORIENT_NO_CORPUS, "could not be read")
            self.assertEqual(result.evidence.get("stage"), "corpus")
            self.assertIs(result.evidence.get("corpus_readable"), False)

        with self.subTest(reading="the composed index opens and holds nothing"):
            studio = self.studio()
            remaining = break_the_corpus_empty(studio)
            self.assertEqual(
                remaining, 0,
                msg="the delete did not delete; there is still a corpus here",
            )
            self.assertEqual(
                corpus_entry_count(studio), 0,
                msg="this reading needs a corpus that OPENS - a count of None "
                "would make it the reading above and prove nothing about the "
                "readable-but-empty branch",
            )
            result = self.probe("orient", studio)
            self.assertOrientState(result, smoke.ORIENT_NO_CORPUS, "no entries")
            self.assertEqual(result.evidence.get("stage"), "corpus")
            self.assertEqual(result.evidence.get("corpus_entry_count"), 0)

        with self.subTest(reading="one row of the composed index will not decode"):
            healthy = self.probe("orient", self.studio())
            victim = str((healthy.evidence.get("top") or [{}])[0].get("uid") or "")
            self.assertTrue(victim, msg="no member to corrupt")
            studio = self.studio()
            break_one_entry_unreadable(studio, victim)
            self.assertEqual(
                _fm_json_of(studio, victim), "{ this is not json",
                msg="the plant did not reach the row it claims to have "
                "corrupted, so whatever the probe says next is about a "
                "healthy index",
            )
            result = self.probe("orient", studio)
            self.assertOrientState(result, smoke.ORIENT_NO_CORPUS, "GRAPH_UNAVAILABLE")
            self.assertEqual(result.evidence.get("error_code"), "GRAPH_UNAVAILABLE")

    def test_orient_state_corpus_but_no_authority_belongs_to_one_human_once(self):
        """STATE 2 of 3. An unperformed setup step, not a broken studio.

        The corpus is there and no group authority has ever been installed for
        the Studio, so visibility cannot resolve. UNKNOWN, because nobody has
        done a thing yet - reporting it red is red-when-blind, "the same defect
        as green-when-blind wearing the opposite sign."

        THE OWNER IS THE POINT, and ADR-065 (0a5d562d) is what makes it
        sayable. Identity and authority are resident in the Studio; the Studio
        is portable; the record travels with the vault. So the owner is a
        human performing ONE act FOR THE STUDIO, and the cure says so - it
        names restoring the tracked record first, because a vault that already
        has one and arrives without it has a deleted file rather than an
        unperformed step. What it must never say is that the reader owes a
        ritual to the box they are sitting at.

        THE CONTROLS, in the order they would catch a silent no-op: the
        authority is really there before the plant, really gone after it, and
        the CORPUS IS STILL READABLE afterwards. That last one is the one that
        matters. "corpus-but-no-authority" is only that state if the corpus
        survived; a plant that took the index with it would put the probe in
        state 1, and every assertion below would be measuring the wrong branch
        while looking perfectly green.
        """
        studio = self.studio()
        self.assertTrue(
            authority_is_installed(studio),
            msg="the fixture has no authority to remove, so this case would "
            "assert the state without ever changing it",
        )
        break_missing_group_authority(studio)
        self.assertFalse(
            authority_is_installed(studio),
            msg="the plant left an installed authority behind",
        )
        self.assertGreater(
            corpus_entry_count(studio) or 0, 0,
            msg="the plant took the corpus with it, so this is state 1 and not "
            "state 2, and everything below is measuring the wrong branch",
        )

        result = self.probe("orient", studio)
        self.assertOrientState(result, smoke.ORIENT_NO_AUTHORITY, "group authority")
        self.assertIs(result.evidence.get("authority_installed"), False)
        self.assertIn(
            "not a broken studio", result.detail.lower(),
            msg="the reader has to be told this is a step nobody has taken, "
            "not a defect; the difference is the verdict",
        )

        self.assertIn(smoke.GROUP_AUTHORITY_TOOL_REL, result.cure)
        for step in ("build", "accept-fingerprint", "verify", "install"):
            with self.subTest(step=step):
                self.assertIn(
                    step, result.cure,
                    msg=f"the cure never names the {step!r} step of the "
                    f"one-time install; got {result.cure!r}",
                )
        self.assertIn(
            smoke.GROUP_AUTHORITY_DIR_REL, result.cure,
            msg="the cure never names the directory the record travels in, so "
            "a reader whose tracked authority was deleted is sent to install "
            "a second one instead of restoring the one they own (ADR-065)",
        )
        self.assertIn(
            "travels with the", result.cure.lower(),
            msg="the cure has to say the record TRAVELS. Without it this reads "
            "as a per-machine act again, which is the framing ADR-065 "
            f"superseded; got {result.cure!r}",
        )
        self.assertTrue(
            command_lines(result.cure),
            msg="the cure has to contain a line a human can paste",
        )

    def test_orient_state_still_refusing_belongs_to_the_retrieval_path(self):
        """STATE 3 of 3, and the only one of the three that is a DEFECT.

        Corpus present, authority installed, and orient still cannot answer.
        Metis G98 measured exactly this and it is why ORIENT is in this tool:
        "A capability can be fully built, fully tested, fully green, and
        structurally unable to run ... and nothing we own says a word."

        FAIL, not UNKNOWN, and distinguishable from the two above without
        reading past the first phrase - because the reader's next move is
        completely different. States 1 and 2 are things nobody has done. This
        one is a thing that was done and does not work, and it belongs to
        whoever owns the retrieval path.

        THE CONTROLS ARE BOTH RUNGS BENEATH IT. The corpus is asserted
        readable and the authority asserted installed AFTER the plant, because
        this state is defined by those two holding. A plant that quietly took
        either would land the probe in state 1 or state 2 - which are UNKNOWN,
        not FAIL - and the case would then be proving the opposite of what it
        claims while wearing a green tick.
        """
        studio = self.studio()
        break_group_registry(studio)
        self.assertTrue(
            authority_is_installed(studio),
            msg="the plant removed the authority, so this is state 2; state 3 "
            "is only itself with an authority installed",
        )
        self.assertGreater(
            corpus_entry_count(studio) or 0, 0,
            msg="the plant took the corpus, so this is state 1; state 3 is "
            "only itself over a corpus that reads",
        )

        result = self.probe("orient", studio)
        self.assertOrientState(
            result, smoke.ORIENT_STILL_REFUSING, "GROUP_CORPUS_UNAVAILABLE",
        )
        self.assertIs(result.evidence.get("authority_installed"), True)
        self.assertEqual(result.evidence.get("stage"), "visibility")
        self.assertTrue(
            result.evidence.get("viewer_principal_uid"),
            msg="the refusal has to name the principal that was actually "
            "supplied, or it cannot be told apart from 'the caller passed no "
            "viewer' - which is the confusion this probe must never make",
        )
        self.assertIn(
            result, smoke.failures([result]),
            msg="the one state that is a real defect has to count as one",
        )

    def test_orient_the_three_states_are_exclusive_exhaustive_and_distinct(self):
        """"Two states that can both be true at once is the collapse Argus
        warned about, wearing a different hat."

        So the ladder is checked as a partition rather than as three labels.
        The three defining conditions are written here from the PROSE - "the
        composed index is absent or unreadable"; "the corpus is there, but no
        group authority has ever been installed"; "corpus present, authority
        installed, and orient still cannot answer" - and every one of the
        eight points of the (corpus, authority, answered) cube is required to
        satisfy exactly one of those three or the green, with the
        implementation agreeing at every point.

        Then the three are required to be distinct in the three fields a
        reader routes on: the name, the OWNER, and the command. Two states
        that print the same cure have been collapsed whatever their labels
        say.
        """
        def defining(corpus, authority, answered):
            return {
                smoke.ORIENT_NO_CORPUS: not corpus,
                smoke.ORIENT_NO_AUTHORITY: corpus and not authority,
                smoke.ORIENT_STILL_REFUSING: (
                    corpus and authority and not answered
                ),
            }

        seen = set()
        for corpus in (False, True):
            for authority in (False, True):
                for answered in (False, True):
                    point = (corpus, authority, answered)
                    with self.subTest(point=point):
                        holds = [
                            state for state, ok
                            in defining(*point).items() if ok
                        ]
                        self.assertLessEqual(
                            len(holds), 1,
                            msg=f"{point} satisfies {[s.name for s in holds]} "
                            "at once, so the three are not exclusive",
                        )
                        green = corpus and authority and answered
                        self.assertEqual(
                            len(holds) == 0, green,
                            msg=f"{point} is covered by no state and is not "
                            "the green either, so the three are not "
                            "exhaustive",
                        )
                        expected = holds[0] if holds else None
                        self.assertIs(
                            smoke.orient_state(*point), expected,
                            msg=f"at {point} the ladder returned "
                            f"{smoke.orient_state(*point)} and the prose says "
                            f"{expected}",
                        )
                        seen.add(expected)

        self.assertEqual(
            seen, set(smoke.ORIENT_STATES) | {None},
            msg="a state the ladder can never reach is a state that does not "
            "exist; every one of the three has to be reachable over the cube",
        )

        for field in ("name", "owner", "next_action"):
            values = [getattr(state, field) for state in smoke.ORIENT_STATES]
            with self.subTest(field=field):
                self.assertEqual(
                    len(set(values)), len(smoke.ORIENT_STATES),
                    msg=f"two of the three states share a {field}: {values}. "
                    "They have different owners; that is the whole sharpening",
                )
        self.assertEqual(
            [state.status for state in smoke.ORIENT_STATES],
            [smoke.STATUS_UNKNOWN, smoke.STATUS_UNKNOWN, smoke.STATUS_FAIL],
            msg="two of these are things nobody has done yet and the third is "
            "a defect; the verdicts have to say so",
        )

    def test_orient_the_three_states_are_exclusive_on_real_studios_too(self):
        """The cube proves the ladder. This proves the WIRING to it.

        Three studios, each broken into one state, driven end to end: three
        different states reported, three different owners, three different
        cures, and no verdict claiming more than one. A probe whose ladder is
        perfect and whose branches all call it with the same arguments would
        pass the case above and fail this one.
        """
        studios = {}

        no_corpus = self.studio()
        break_the_corpus_absent(no_corpus)
        studios[smoke.ORIENT_NO_CORPUS] = no_corpus

        no_authority = self.studio()
        break_missing_group_authority(no_authority)
        studios[smoke.ORIENT_NO_AUTHORITY] = no_authority

        refusing = self.studio()
        break_group_registry(refusing)
        studios[smoke.ORIENT_STILL_REFUSING] = refusing

        reported = {}
        for state, studio in studios.items():
            with self.subTest(state=state.name):
                result = self.probe("orient", studio)
                self.assertEqual(result.evidence.get("orient_state"), state.name)
                self.assertEqual(result.status, state.status)
                reported[state.name] = (
                    result.evidence.get("orient_state_owner"), result.cure,
                )

        self.assertEqual(
            len(reported), 3, msg="three studios did not produce three states"
        )
        owners = [owner for owner, _ in reported.values()]
        cures = [cure for _, cure in reported.values()]
        self.assertEqual(
            len(set(owners)), 3,
            msg=f"two of the three states told the reader the same owner: "
            f"{owners}",
        )
        self.assertEqual(
            len(set(cures)), 3,
            msg=f"two of the three states handed the reader the same command: "
            f"{cures}",
        )

    def test_orient_every_verdict_branch_is_one_state_or_none_on_purpose(self):
        """Exhaustive the other way: over the BRANCHES, not over the cube.

        A state machine is only exclusive if nothing escapes it by accident.
        So every stage the driver can report is driven through
        ``_orient_verdict`` and required to land on exactly one state or on
        NO state deliberately - and the stage list is scraped out of the
        driver source rather than typed here, so a stage added later without a
        verdict reddens this case instead of falling through in silence.

        The stateless ones are not an oversight and the table says which they
        are. Being unable to LOOK - a clock, a machine with no PyYAML, an
        audience that covers nothing, this instrument's own driver crashing -
        is not a fact about the Studio, and giving it a fourth name would
        re-collapse the three the sharpening exists to separate.
        """
        for label, payload, expected in ORIENT_BRANCH_TABLE:
            with self.subTest(branch=label):
                result = smoke._orient_verdict(
                    dict(payload), {}, ["a check"], 0.01,
                )
                if expected is None:
                    self.assertNotIn(
                        "orient_state", result.evidence,
                        msg=f"{label} claimed a state it has no owner for: "
                        f"{result.evidence.get('orient_state')!r}",
                    )
                    continue
                self.assertEqual(
                    result.evidence.get("orient_state"), expected.name,
                    msg=f"{label} should be {expected.name}; got "
                    f"{result.evidence.get('orient_state')!r}",
                )
                self.assertEqual(
                    result.status, expected.status,
                    msg=f"{label} carries {expected.name}, whose verdict is "
                    f"{expected.status}, and reported {result.status}",
                )
                self.assertTrue(
                    result.detail.startswith(expected.opening()),
                    msg=f"{label} did not open with its state and owner: "
                    f"{result.detail!r}",
                )

        covered = {payload["stage"] for _, payload, _ in ORIENT_BRANCH_TABLE}
        declared = _driver_stages(smoke._ORIENT_DRIVER)
        self.assertTrue(
            declared,
            msg="the stage scan found nothing, so it is decoration and this "
            "case proves no coverage at all",
        )
        self.assertEqual(
            sorted(declared - covered), [],
            msg="the driver can report a stage this case never drives through "
            "the verdict, so nobody knows whether it names a state or "
            "deliberately does not",
        )

    def test_orient_never_borrows_another_states_command_without_saying_whose(self):
        """The cure a reader PASTES has to agree with the owner they were told.

        "Do not let two of them share a cure string" is satisfied by three
        different strings, and three different strings are not enough. What a
        reader acts on is the first pasteable line, and a state-3 verdict whose
        first line is state 1's whole cure has handed the retrieval path's
        defect to the index rebuilder no matter how the sentence ends.

        Some borrowing is honest, so this does not ban it. ``adapters`` and
        ``NODE_NOT_FOUND`` both implicate the index itself even though it read
        - an adapter will not construct over it; two reads of it disagree - so
        a recompose IS the cheap first move there, and both say in the same
        breath that the retrieval path still owns the result. The rule is
        therefore: borrow if it helps, but attribute it in the cure.

        This is what sent the empty-circle branch back for a second look. It
        led with the recompose and never said whose defect it was, and a
        recompose does not move a decay verdict - so it was spending the index
        owner's command on a gate in the draw. That is the collapse Argus
        warned about arriving through the cure line rather than the label.
        """
        def command_only(line: str) -> str:
            return line.split("  #")[0].strip()

        # What each state's own cure LEADS with - the line a reader pastes
        # first - keyed so a borrowing can be recognised at all.
        leads = {}
        for state in smoke.ORIENT_STATES:
            commands = command_lines(state.next_action)
            self.assertTrue(
                commands,
                msg=f"{state.name} has no pasteable command in its cure, so "
                "this case cannot tell a borrowing from anything else and "
                f"would pass vacuously: {state.next_action!r}",
            )
            leads[command_only(commands[0])] = state
        self.assertEqual(
            len(leads), len(smoke.ORIENT_STATES),
            msg="two of the three states LEAD with the same command, so the "
            f"reader cannot tell them apart by what they paste: {sorted(leads)}",
        )

        # The phrase that puts a borrowed command back with its real owner.
        # Written out rather than derived from `owner`, because what a cure has
        # to do is name the owner in words a reader recognises, and an
        # automatic slice of the owner string would drift into asserting
        # nothing.
        attribution = {
            smoke.ORIENT_NO_CORPUS.name: "composed index",
            smoke.ORIENT_NO_AUTHORITY.name: "Studio",
            smoke.ORIENT_STILL_REFUSING.name: "retrieval path",
        }

        borrowings = 0
        for label, payload, expected in ORIENT_BRANCH_TABLE:
            if expected is None:
                continue
            with self.subTest(branch=label):
                result = smoke._orient_verdict(
                    dict(payload), {}, ["a check"], 0.01,
                )
                commands = command_lines(result.cure)
                self.assertTrue(
                    commands,
                    msg=f"{label} claims {expected.name} and hands the reader "
                    f"nothing to paste: {result.cure!r}",
                )
                lent_by = leads.get(command_only(commands[0]))
                if lent_by is None or lent_by is expected:
                    continue
                borrowings += 1
                self.assertIn(
                    attribution[expected.name], result.cure,
                    msg=f"{label} reports {expected.name} - owner "
                    f"{expected.owner!r} - and the first thing it tells the "
                    f"reader to run is {lent_by.name}'s own cure, without "
                    "naming who still owns the defect. The reader pastes it, "
                    "it does not help, and they have been pointed at the "
                    f"wrong person. cure={result.cure!r}",
                )

        self.assertGreater(
            borrowings, 0,
            msg="no branch borrowed another state's command, so every "
            "assertion above was skipped and this case proved nothing. If a "
            "borrowing was deliberately removed, remove this guard with it",
        )

    # -- the authority ------------------------------------------------------ #
    def test_orient_reports_unknown_when_no_authority_is_installed(self):
        """AC7a's sharpest case. No group authority is not a broken studio.

        "Reporting that red is red-when-blind, the same defect as
        green-when-blind wearing the opposite sign." The cure has to name the
        one-time install a human performs, all four steps, because the entire
        value of the UNKNOWN is that somebody can go and do it.
        """
        studio = self.studio()
        break_missing_group_authority(studio)
        result = self.probe("orient", studio)
        self.assertProbeUnknown(result, "group authority")
        self.assertIs(result.evidence.get("authority_installed"), False)
        self.assertIn(smoke.GROUP_AUTHORITY_TOOL_REL, result.cure)
        for step in ("build", "accept-fingerprint", "verify", "install"):
            with self.subTest(step=step):
                self.assertIn(
                    step, result.cure,
                    msg=f"the cure never names the {step!r} step of the "
                    f"one-time install; got {result.cure!r}",
                )
        self.assertReportNamesTheCure(result)

    def test_orient_never_says_the_authority_is_a_property_of_the_hardware(self):
        """ADR-065 (0a5d562d), which superseded a framing this probe carried.

        The probe used to call the installed record a MACHINE-LOCAL pin and
        its cure a per-machine ceremony. Mike ruled that wrong: "The studio is
        portable across hardware. What does the hardware have to do with
        authority?" Identity and authority are resident in the Studio, the
        trust record travels with the vault, and a clone arrives already
        knowing who everyone is.

        So the vocabulary is barred - in the source and in what the probe
        actually prints. Machine language about PROVISIONING survives on
        purpose ("this machine has not installed PyYAML" is true and useful);
        what is barred is machine language about AUTHORITY.
        """
        superseded = (
            "machine-local", "machine local", "per-machine",
            "machine identity", "machine enrollment", "machine enrolment",
        )
        source = SMOKE_PATH.read_text(encoding="utf-8")
        for region in _orient_source_regions(source):
            for phrase in superseded:
                with self.subTest(phrase=phrase, where="source"):
                    self.assertNotIn(
                        phrase, region,
                        msg=f"the ORIENT probe still calls something {phrase!r}. "
                        "Authority is resident in the Studio and travels with "
                        "the vault (ADR-065); hardware is not a participant.",
                    )

        studio = self.studio()
        break_missing_group_authority(studio)
        spoken = self.probe("orient", studio)
        said = f"{spoken.detail}\n{spoken.cure}".lower()
        for phrase in superseded:
            with self.subTest(phrase=phrase, where="output"):
                self.assertNotIn(phrase, said)
        self.assertIn(
            "travels with the vault", said,
            msg="the missing-authority answer never tells the reader the "
            "record travels, so it still reads as something owed to this box",
        )

    def test_orient_will_not_install_an_authority_to_produce_a_green(self):
        """The ruled constraint, asserted rather than trusted.

        "An instrument that routes around the gate it reports on is worth less
        than no instrument." So: after a run against a studio with no
        authority, there is still no authority - no pin, no generation, no
        trust file - and the probe did not quietly claim visibility some other
        way either.
        """
        studio = self.studio()
        break_missing_group_authority(studio)
        before = sorted(
            path.relative_to(studio).as_posix()
            for path in studio.rglob("*") if path.is_file()
        )

        result = self.probe("orient", studio)
        self.assertEqual(result.status, smoke.STATUS_UNKNOWN)

        self.assertFalse(
            (studio / smoke.GROUP_AUTHORITY_PIN_REL).exists(),
            msg="the probe installed an authority pin to get past the gate it "
            "is supposed to report on",
        )
        self.assertFalse((studio / AUTHORITY_DIR / "group-authority").exists())
        after = sorted(
            path.relative_to(studio).as_posix()
            for path in studio.rglob("*") if path.is_file()
        )
        authored = [
            path for path in set(after) - set(before)
            if not path.startswith("vault/00-index.sqlite-")
        ]
        self.assertEqual(
            authored, [],
            msg="the probe authored files on a studio it could not orient on",
        )

    def test_orient_fails_when_the_floor_is_down_with_an_authority_installed(self):
        """Metis G98's finding, reproduced on disk, and the reason for the
        probe.

        The authority IS installed and visibility STILL fails closed, so orient
        cannot start - before a circle is drawn, before anything is ranked.
        This one is FAIL and not UNKNOWN, and the distinction is the whole
        design: an authority nobody has installed is a step nobody has taken,
        while an installed authority that still will not resolve is a
        determined finding about this studio. Collapsing the two would either
        hide her bug or cry wolf on every fresh clone.
        """
        studio = self.studio()
        break_group_registry(studio)
        result = self.probe("orient", studio)
        self.assertProbeFails(result, "GROUP_CORPUS_UNAVAILABLE")
        self.assertIs(result.evidence.get("authority_installed"), True)
        self.assertEqual(result.evidence.get("stage"), "visibility")
        self.assertTrue(
            result.evidence.get("viewer_principal_uid"),
            msg="the refusal has to name the principal that was actually "
            "supplied, or it cannot be told apart from 'the caller passed no "
            "viewer' - which is the confusion this probe must never make",
        )
        self.assertReportNamesTheCure(result)

    def test_orient_reports_unknown_when_the_authority_names_no_principal(self):
        """No principal to view as is not the studio failing to orient.

        ``visible_segments`` refuses a viewer carrying no principal uid, and
        that refusal is the CALLER being wrong. The probe must not invent a
        viewer to get past it, and must not report the studio red for its own
        inability to build one.
        """
        studio = self.studio()
        break_principal_directory(studio)
        result = self.probe("orient", studio)
        self.assertProbeUnknown(result, "principal")
        self.assertEqual(result.evidence.get("stage"), "viewer")
        # No state, and the reasoning is the same as the audience case: an
        # authority IS installed, so this is not state 2, and the probe never
        # posed a question, so it is not state 3.
        self.assertNoOrientState(result)
        self.assertReportNamesTheCure(result)

    # -- the empty circle, both readings ------------------------------------ #
    def test_orient_fails_on_an_empty_circle_over_readable_substrate(self):
        """The hard call, and the branch it is one half of.

        Every node but the anchor carries a high-confidence decay verdict.
        ``filter_visible_uids`` does not decay-gate, so the probe's own
        pre-check still sees readable neighbours; the draw does gate, so the
        circle comes back empty. Visibility resolved, the walk ran, nothing
        came back: the instrument was not blind, it was answered. FAIL.

        The same fixture, same anchor, no plant, is asserted to come back with
        a NON-EMPTY circle a line earlier, so the empty one is the verdict
        moving and not the fixture being barren. And ``plant.unflagged`` is
        required to be empty: a plant that leaves any reachable node without
        the gardener's verdict is not testing the decay gate, it is testing
        which nodes it happened to reach. That assertion is the one that would
        have caught this case's own silent no-op - the plant reached 174 of 175
        rows and the 175th node, an edge-only ``member_of`` parent with no row
        to carry a verdict, kept the circle non-empty and the case green.
        """
        studio = self.studio()
        healthy = self.probe("orient", studio)
        self.assertEqual(healthy.status, smoke.STATUS_PASS)
        anchor = str(healthy.evidence["task_uid"])
        self.assertGreater(
            int(healthy.evidence.get("item_count") or 0), 0,
            msg="the control: this anchor draws a real circle on this fixture "
            "when nothing is rotten, so an empty one after the plant is the "
            "decay gate and not an empty studio",
        )

        rotten = self.studio()
        plant = break_everything_rotten_except(rotten, anchor)
        self.assertGreater(plant.flagged, 0, msg="the plant flagged nothing")
        self.assertEqual(
            plant.unflagged, (),
            msg="the plant left node(s) of the composed graph without the "
            "gardener's verdict, so an empty circle here would not be the "
            "decay gate answering and a NON-empty one would prove nothing "
            f"about it: {plant.unflagged!r}",
        )

        result = self.probe("orient", rotten)
        self.assertProbeFails(result, anchor)
        visible = int(result.evidence.get("visible_neighbours") or 0)
        self.assertOrientState(
            result, smoke.ORIENT_STILL_REFUSING, anchor,
            cure="python3 vault/tools/tropo-smoke.py --only orient --json"
            f"  # {anchor} drew 0 of {visible} neighbour(s) the projection had "
            "just read, so the drop is in the draw and belongs to the "
            "retrieval path, not to the corpus",
        )
        self.assertEqual(result.evidence.get("item_count"), 0)
        self.assertEqual(result.evidence.get("stage"), "oriented")
        self.assertGreater(
            int(result.evidence.get("visible_neighbours") or 0), 0,
            msg="this case only means something if the projection had just "
            "confirmed the anchor's neighbours READABLE; with none visible the "
            "empty circle would be correct behaviour and the verdict UNKNOWN",
        )
        self.assertReportNamesTheCure(result)

    def test_orient_reports_unknown_when_nothing_is_inside_the_audience(self):
        """The other half, and the one that stops the case above crying wolf.

        The studio declares itself a vault-node the installed authority does
        not grant, so ``derive_segment`` puts every node in a segment no
        principal reads and no anchor has a single neighbour the viewer may
        see. An empty circle here is orient behaving EXACTLY as designed, and a
        probe that failed it would be manufacturing the false-positive class
        this whole tool exists to end. Nothing was learned about whether orient
        can rank: UNKNOWN.

        The control is a differential against the same fixture unplanted: the
        FIRST anchor the probe considers has to be the same UID with the same
        structural neighbour count and its visible count has to fall from
        non-zero to zero. That pins the plant to visibility alone - it did not
        remove structure, it did not change which anchor is chosen, and it did
        not silently no-op, which is exactly what the previous
        ``extraction_scope``-based plant did here (every node stayed readable
        through the authority's ``private -> b2e8d914`` legacy alias).
        """
        control = self.probe("orient", self.studio())
        self.assertEqual(control.status, smoke.STATUS_PASS)
        before = (control.evidence.get("anchors_considered") or [{}])[0]
        self.assertGreater(
            int(before.get("visible") or 0), 0,
            msg="the control run has to hold an anchor with READABLE "
            "neighbours or the plant has nothing to take away",
        )

        studio = self.studio()
        plant = break_everything_out_of_the_audience(studio)
        self.assertGreater(plant.nodes, 0)

        result = self.probe("orient", studio)
        self.assertProbeUnknown(result, "audience")
        # ...and it claims NO state. The shape here looks like state 3 - the
        # corpus reads, the authority is installed - and calling it that would
        # convict the retrieval path for a studio whose audience simply does
        # not cover its own substrate. Its matched pair one case up IS state 3.
        self.assertNoOrientState(result)
        self.assertEqual(result.evidence.get("stage"), "anchor")
        considered = result.evidence.get("anchors_considered") or []
        self.assertTrue(considered, msg="it gave up without considering an anchor")
        self.assertEqual(
            [entry for entry in considered if entry.get("visible")], [],
            msg="it reported 'nothing is visible' while holding an anchor with "
            "a visible neighbour",
        )
        self.assertTrue(
            any(entry.get("structural") for entry in considered),
            msg="the studio has to HAVE structure for this to be the "
            "audience-empty case rather than the index-empty one",
        )
        after = next(
            (entry for entry in considered
             if entry.get("uid") == before.get("uid")), None,
        )
        self.assertIsNotNone(
            after,
            msg=f"the plant changed which anchors are considered at all; "
            f"{before.get('uid')!r} is missing from {considered!r}",
        )
        self.assertEqual(
            after.get("structural"), before.get("structural"),
            msg="the plant moved the STRUCTURE, not just the audience; an "
            "empty circle over a studio that lost its edges is a different "
            "finding and this case would not be measuring visibility",
        )
        self.assertEqual(after.get("visible"), 0)
        self.assertReportNamesTheCure(result)

    # -- this instrument could not look ------------------------------------- #
    def test_orient_reports_unknown_when_the_library_is_not_on_the_studio(self):
        studio = self.studio()
        (studio / smoke.ORIENT_LIBRARY_REL).unlink()
        result = self.probe("orient", studio)
        self.assertProbeUnknown(result, smoke.ORIENT_LIBRARY_REL)
        self.assertReportNamesTheCure(result)

    def test_orient_reports_unknown_when_there_is_no_composed_index(self):
        """Nothing to draw a circle over is not a studio that cannot orient."""
        studio = self.studio()
        (studio / smoke.COMPOSED_INDEX_REL).unlink()
        result = self.probe("orient", studio)
        self.assertProbeUnknown(result, "composed index")
        self.assertReportNamesTheCure(result)

    def test_orient_reports_unknown_when_the_index_cannot_be_read(self):
        """An UNREADABLE index is the same blindness as an absent one.

        One row of the composed index no longer decodes, so the graph source
        raises ``GRAPH_UNAVAILABLE`` on whichever call reaches it first. That
        code means "this instrument could not read the substrate" at every
        stage it can surface at - routing it by stage instead of by code was a
        measured defect here: it produced "visibility resolution still fails
        closed", which names the wrong break and prints the wrong cure.
        """
        studio = self.studio()
        healthy = self.probe("orient", studio)
        self.assertEqual(healthy.status, smoke.STATUS_PASS)
        victim = str((healthy.evidence.get("top") or [{}])[0].get("uid") or "")
        self.assertTrue(victim, msg="no member to corrupt")

        damaged = self.studio()
        break_one_entry_unreadable(damaged, victim)
        result = self.probe("orient", damaged)
        self.assertProbeUnknown(result, "GRAPH_UNAVAILABLE")
        self.assertEqual(result.evidence.get("error_code"), "GRAPH_UNAVAILABLE")
        self.assertIn(
            "rebuild-index", result.cure,
            msg="an unreadable index is cured by rebuilding it, not by "
            "re-installing the group authority",
        )
        self.assertReportNamesTheCure(result)

    def test_orient_reports_unknown_when_this_machine_never_installed_pyyaml(self):
        """Break 7's world: deps declared but never shipped to this fork.

        The orient library needs PyYAML and cryptography (measured:
        lib.distiller -> lib.viewer_projection -> lib.segment -> yaml). A
        machine without them says nothing about whether the capability works,
        so it is UNKNOWN with an install cure - and this is also the case that
        justifies driving the library out-of-process at all, since an
        in-process import would have taken the other five operations down with
        it.
        """
        studio = self.studio()
        shadow = a_machine_without("yaml")
        with mock.patch.dict(os.environ, {"PYTHONPATH": str(shadow)}):
            result = self.probe("orient", studio)
        self.assertProbeUnknown(result, "yaml")
        self.assertEqual(result.evidence.get("missing_module"), "yaml")
        self.assertEqual(result.evidence.get("stage"), "import")
        self.assertIn("pip install", result.cure)

        # ...and the other five are unharmed by the same machine, which is the
        # claim the subprocess design is making.
        with mock.patch.dict(os.environ, {"PYTHONPATH": str(shadow)}):
            self.assertEqual(self.probe("boot", studio).status, smoke.STATUS_PASS)

    def test_orient_fails_when_the_library_on_this_studio_will_not_import(self):
        """The other side of the import branch, and the reason it is a branch.

        A missing third-party module is an unprovisioned machine; a lib/ module
        that is present and broken is substrate damage, and this studio really
        cannot orient. Same exception class, opposite verdict, told apart by
        whether the missing module is one of the studio's own.
        """
        studio = self.studio()
        break_orient_library(studio)
        result = self.probe("orient", studio)
        self.assertProbeFails(result, "import")
        self.assertEqual(result.evidence.get("stage"), "import")
        self.assertReportNamesTheCure(result)

    def test_orient_reports_unknown_when_it_runs_out_of_budget(self):
        """AC7a for the one subprocess this probe runs.

        The driver is replaced by a sleep so the ONLY thing that can be slow is
        the orientation itself - a timeout case where some other call happened
        to be the slow one would prove nothing, and this suite has been burned
        by exactly that. The evidence has to carry ``driver_timed_out``, so a
        pass here cannot come from a different branch reporting UNKNOWN for a
        different reason.
        """
        studio = self.studio()
        slow = "import time\ntime.sleep(30)\n"
        with mock.patch.object(smoke, "_ORIENT_DRIVER", slow):
            with only_for("orient", 1.0):
                result = self.probe("orient", studio)
        self.assertProbeUnknown(result, "orient")
        self.assertIs(
            result.evidence.get("driver_timed_out"), True,
            msg="something other than the orientation produced this UNKNOWN",
        )
        # ...and it is the CLOCK branch that produced it. Deleting the timeout
        # branch entirely still yields an UNKNOWN - the driver returns no
        # readable report when it is killed - so asserting the status alone
        # would pass over an implementation that no longer distinguishes "ran
        # out of time" from "said something unparseable", and the reader would
        # be told to re-run for a JSON payload instead of being told the
        # budget ran out.
        self.assertRegex(
            result.detail,
            r"did not finish within [\d.]+s of the [\d.]+s budget",
            msg=f"the UNKNOWN never names the clock: {result.detail!r}",
        )
        # A clock that ran out has no owner inside the Studio, so it claims
        # none of the three states.
        self.assertNoOrientState(result)
        self.assertLess(result.elapsed_s, 20.0)
        self.assertReportNamesTheCure(result)

    def test_orient_reports_unknown_when_its_own_driver_says_nothing(self):
        """A fault in this instrument is not a finding about the studio."""
        studio = self.studio()
        with mock.patch.object(smoke, "_ORIENT_DRIVER", "print('not json')"):
            result = self.probe("orient", studio)
        self.assertProbeUnknown(result, "driver")
        self.assertReportNamesTheCure(result)

    # -- AC2 ---------------------------------------------------------------- #
    def test_orient_reads_and_leaves_the_studio_where_it_found_it(self):
        """AC2 at this probe's own grain, which is stricter than the run's.

        ORIENT only reads, so the only paths it may add are the SQLite sidecars
        any reader of a WAL-mode database materialises. In particular no
        ``__pycache__``: the driver imports the studio's library, and without
        PYTHONDONTWRITEBYTECODE that import drops compiled modules into
        ``vault/tools/lib/`` - a write into a GOVERNED plane, however
        gitignored it happens to be.

        The case ends by running the SAME driver with that one variable removed
        and requiring that it DOES write bytecode. Without that control, "no
        new .pyc" is equally consistent with the import never happening and
        with this test looking in the wrong directory.
        """
        def compiled() -> set:
            return {
                path.relative_to(studio).as_posix()
                for path in (studio / "vault" / "tools").rglob("*.pyc")
            }

        studio = self.studio()
        before = census(studio)
        before_paths = tree_paths(studio)
        # The fixture is BUILT by running the studio's own tools, so it already
        # has bytecode from that. What must not grow is the set.
        before_compiled = compiled()

        result = self.probe("orient", studio)
        self.assertEqual(result.status, smoke.STATUS_PASS)

        after = census(studio)
        self.maxDiff = None
        self.assertEqual(
            {path: digest for path, digest in after.items() if path in before},
            before,
            msg="orient changed or removed a file it was only supposed to read",
        )
        added = sorted(tree_paths(studio) - before_paths)
        self.assertEqual(
            [path for path in added
             if not path.startswith("vault/00-index.sqlite-")],
            [],
            msg=f"orient left files behind: {added}",
        )
        self.assertEqual(
            sorted(compiled() - before_compiled), [],
            msg="the driver wrote bytecode into the studio's toolchain. The "
            "orient library is imported out-of-process; without "
            "PYTHONDONTWRITEBYTECODE that import compiles every module on the "
            "chain into vault/tools/lib/__pycache__, which is a write into a "
            "governed plane.",
        )

        # The clean assertion above is worth only as much as the proof that it
        # would have SEEN a write. So run the same driver again with the one
        # variable removed. An earlier form of this case asserted instead that
        # the fixture already carried bytecode, which made it pass or fail on
        # whether the AMBIENT environment happened to have bytecode enabled -
        # `PYTHONDONTWRITEBYTECODE=1 pytest` reddened it while the probe was
        # perfectly correct. This form depends on nothing outside the test.
        control = subprocess.run(
            [sys.executable, "-c", smoke._ORIENT_DRIVER, str(studio),
             smoke._own_uid(), str(smoke.ORIENT_CIRCLE_BUDGET),
             str(smoke.ORIENT_ANCHOR_SHORTLIST)],
            cwd=str(studio), capture_output=True, text=True, timeout=120,
            env={key: value for key, value in os.environ.items()
                 if key != "PYTHONDONTWRITEBYTECODE"},
        )
        self.assertEqual(control.returncode, 0, msg=control.stderr[-2000:])
        self.assertTrue(
            sorted(compiled() - before_compiled),
            msg="the same driver, run WITHOUT PYTHONDONTWRITEBYTECODE, still "
            "wrote no bytecode into vault/tools - so this case cannot tell "
            "'the probe suppressed the write' apart from 'the import never "
            "happened' or 'this observation looks in the wrong place'",
        )

    # -- the guards, driven at the seam they are reachable from -------------- #
    def test_orient_believes_a_typed_refusal_it_does_not_recognise(self):
        """The default for an unrecognised typed error is FAIL, and it should be.

        ``_orient_verdict`` is the boundary between "the studio cannot" and
        "this instrument could not tell", and it is a pure function so a
        payload can drive branches no on-disk state reaches. NODE_NOT_FOUND is
        one of those: the anchor is chosen by a query against the same
        ``entries`` table ``structure()`` reads, so the two cannot disagree
        today - but the code is real in the wild (``d2bb4dda`` returns exactly
        it on the live studio) and silence would be the worse failure.
        """
        for code, needle in (
            ("NODE_NOT_FOUND", "disagree"),
            ("QUERY_UNSUPPORTED", "typed"),
        ):
            with self.subTest(code=code):
                result = smoke._orient_verdict(
                    {"stage": "orient", "task_uid": "abcd1234",
                     "error_kind": "GraphError", "error_code": code,
                     "error_message": "planted"},
                    {}, ["a check"], 0.01,
                )
                self.assertProbeFails(result, needle)

    def test_orient_calls_a_budget_it_rejected_its_own_fault(self):
        """``BUDGET_INVALID`` means THIS file handed the library a bad budget.

        Reporting the studio red for the instrument's own argument error is the
        most direct red-when-blind available, so it is UNKNOWN. Driven at the
        verdict seam because ORIENT_CIRCLE_BUDGET is a valid constant and no
        studio state can make it invalid.
        """
        result = smoke._orient_verdict(
            {"stage": "orient", "task_uid": "abcd1234",
             "error_kind": "GraphError", "error_code": "BUDGET_INVALID",
             "error_message": "budget must be a non-negative int"},
            {}, ["a check"], 0.01,
        )
        self.assertProbeUnknown(result, "BUDGET_INVALID")

    def test_orient_fails_a_circle_that_came_back_out_of_rank_order(self):
        """A circle is not a RANKED circle, and the difference is the second
        half of the capability.

        Driven at the verdict seam: producing a genuinely mis-ordered ranking
        would mean breaking ``rank_circle``, which is another agent's lane.
        """
        result = smoke._orient_verdict(
            {"stage": "oriented", "task_uid": "abcd1234", "item_count": 4,
             "visible_neighbours": 3, "structural_neighbours": 5,
             "ranked_descending": False, "tilt": "none",
             "top": [{"uid": "z", "provenance": "ref-of-task:abcd1234"}]},
            {}, ["a check"], 0.01,
        )
        self.assertProbeFails(result, "not in score order")

    def test_orient_fails_when_its_adapters_refuse_to_construct(self):
        """A guard, and named as one.

        Every adapter opens the index lazily, so a constructor that refuses
        outright would be new behaviour in a library this probe does not own.
        If it ever happens over an index this probe has ALREADY confirmed
        present and readable, that is the studio answering.
        """
        result = smoke._orient_verdict(
            {"stage": "adapters", "authority_installed": True,
             "error_kind": "GraphError", "error_code": "SOMETHING_ELSE",
             "error_message": "planted adapter refusal"},
            {}, ["a check"], 0.01,
        )
        self.assertProbeFails(result, "adapters")

    def test_orient_never_says_anything_is_secure(self):
        """Mike's ruling, and Metis's binding gloss on it.

        "We are just raising the bar so that we have an identity management
        system and we can track who is who. I don't want to over rotate on
        penetration-tested and passed security." So this probe's output,
        docstrings and comments must not offer a security guarantee. The honest
        words are attribution, continuity, and who-is-who - and they are what
        the cure text for a missing authority has to be written in.

        The scan reads BOTH ORIENT regions. It used to read only the probe,
        which left the cure strings, the state names and the owners - all of
        them declared with the ORIENT constants - completely unscanned. A
        prohibition with a hole in it where the printed text lives is not a
        prohibition.
        """
        forbidden = ("secure", "security", "tamper", "attack", "threat",
                     "penetration", "hardened", "cryptographically")
        regions = _orient_source_regions(SMOKE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(regions), 2)
        for index, region in enumerate(regions):
            lowered = region.lower()
            for word in forbidden:
                with self.subTest(word=word, region=index):
                    self.assertNotIn(
                        word, lowered,
                        msg=f"the ORIENT probe says {word!r} somewhere in its "
                        "output, docstrings or comments. What an installed "
                        "authority buys is attribution, continuity and knowing "
                        "who is who; it is not a security guarantee and must "
                        "not read like one.",
                    )

        studio = self.studio()
        break_missing_group_authority(studio)
        spoken = self.probe("orient", studio)
        said = f"{spoken.detail}\n{spoken.cure}".lower()
        for word in forbidden:
            with self.subTest(word=word, where="output"):
                self.assertNotIn(word, said)


if __name__ == "__main__":
    unittest.main()
