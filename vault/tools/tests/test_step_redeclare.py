#!/usr/bin/env python3
"""Guardrail 3 of Metis G113's Option A ruling (2026-08-27T20:19Z) — the
contract test for `9e7003b1.py step-redeclare`, written from the CONTRACT
Argus A160 handed off (evt_b51c083be28ac6fe_00000220), not from his
implementation. Nothing touches the live wedged run d445af8b until this
suite and an independent verifier (guardrail 4) both clear.

THE GAP THIS ACTION CLOSES: a step whose executor fails AFTER step-start had
no way back — step-start refuses ('started' is not eligible), step-fail
yields 'failed' which is equally ineligible, and the only replay path to
'declared' was tropo.release.package_superseded, a mechanism built for a
superseded package. One argparse error permanently wedged run d445af8b.

TWO GUARDRAILS, each tested at both of its stated layers:

  GUARDRAIL 1 — structurally incapable of erasing a green.
    1a. The emitter refuses unless the step's CURRENT status is exactly
        'started'. Every other status (declared/verified/completed/failed)
        and a step_uid absent from the run are each tested by name, against
        the real wedged run wherever it already exhibits that status and a
        minimal fixture where it does not.
    1b. The emitter ALSO refuses if the step's raw event history carries any
        step_completed or verification_receipt SINCE THE STEP'S MOST RECENT
        RESET (a fresh step_declared or a tropo.release.package_superseded
        naming it), even if the derived current status reads 'started' — a
        defensive second check against a status that only LOOKS clean
        (constructed here via a step re-started after a genuine completion).
        The reset-scoping is itself tested both ways: a completion with NO
        reset since must still refuse on restart, and a completion BEFORE a
        genuine reset must be ALLOWED on restart — unscoped, that second case
        would reopen the exact wedge this action exists to close for any step
        that ever completed, which is the re-wedge two independent verifiers
        found in the 2026-08-28 correction.
    1c. THE REPLAY MUST ALSO REFUSE, independent of the emitter — Argus named
        this "the test I most want and least trust myself to have gotten
        right." A step_redeclared event is hand-authored directly into a
        journal for an already-verified step (the text-editor bypass no
        emitter-side check can prevent) and the replayed status must stay
        'verified'. Also covers the two-line forgery (step_started then
        step_redeclared, laid directly over a real green) that the original
        version of this replay guard honoured — reproduced by three of four
        independent verifiers against the unmutated engine before Argus's
        2026-08-28 correction closed it.

  GUARDRAIL 2 — the wedge stays on the record.
    2a. The journaled event's exact shape.
    2b. --reason / --failed-invocation are argparse-required — tested, along
        with the thing the contract calls for that the shipped action did NOT
        originally enforce: an EMPTY STRING is not the same as an absent
        flag, and the contract explicitly says "no empty-string escape."
        Found empty when this suite was first written (verifier 4 reproduced
        it independently) — reported as a live gap rather than silently
        patched around or the test loosened, matching the standard the
        runner-suite rewrite set. Argus's correction 3 closed it; these tests
        now assert the fixed behaviour directly, no expectedFailure needed.
    2c. --dry-run performs the identical guard checks and writes nothing,
        verified by md5 of run.jsonl and run.state.json before/after, for
        both an eligible and a refused case.

Every refusal test is proven by construction to change verdict when its
guard is removed: guardrail 1's per-status checks are pinned to their exact
refusal message (so a differently-broken guard cannot coincidentally satisfy
the assertion); guardrail 1b's reset-scoping is proven both by an ALLOWED
case that would wrongly refuse if the scoping were removed and by a REFUSED
case unaffected by it; and guardrail 1c is proven three times — once holding
against the shipped `derive_state`, once against a copy with the WHOLE
accepted-prior-states-and-not-blocked check patched to always succeed, and
once isolating just the completion/receipt re-scan half (the specific half
the 2026-08-28 correction added) — each watched going red.

MID-FLIGHT CORRECTION (2026-08-28): this suite failed in setUp on Argus's
machine (macOS resolves /var as a symlink to /private/var; the isolated-
engine safety assertion compared a resolved VAULT_ROOT against an
unresolved tempfile.mkdtemp() path and never matched) — fixed by resolving
every temp directory at creation. In parallel, guardrail 4's four
independent verifiers found five real corrections to the implementation
itself, three of which changed what this suite must assert: the reset-
scoping on guardrail 1b, the two-line forgery on guardrail 1c, and the
empty-string enforcement on guardrail 2b (this suite's own
EmptyStringIsNotAnEscape class predicted that last one before anyone
reported it). All three are reflected above and in their respective classes.

FIXTURE STRATEGY: real artifacts for the real question, isolated copies for
everything else. `9e7003b1.py` resolves its own vault root from its own
`__file__` two directories up — there is no injectable root parameter — so
an isolated test copies the whole vault/tools/ + .tropo/scripts/ tree (the
engine's own sibling-import surface) into a temp directory and loads the
COPIED script, which then resolves cleanly to that temp studio. The real
wedged run (activation 2e9f4dcd, run d445af8b) is copied in for every
scenario it already exhibits (started/verified/declared) exactly as Argus
instructed — real artifacts found every defect this cycle; not one came
from a fixture — and a minimal synthetic run supplies the two statuses it
does not currently hold (completed, failed) plus the constructed edge cases
guardrails 1b/1c require.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
REAL_ACTIVATION_UID = "2e9f4dcd"
REAL_RUN_FOLDER = "release-pipeline-d445af8b-2026-08-27"


def _load_isolated_engine(tmp: Path):
    """Copy the engine's own sibling-import surface into `tmp` and load the
    COPY — never the real vault/tools/9e7003b1.py — so VAULT_ROOT (computed
    from the loaded file's own __file__) resolves to the isolated studio."""
    shutil.copytree(STUDIO_ROOT / "vault" / "tools", tmp / "vault" / "tools",
                     ignore=shutil.ignore_patterns("__pycache__", "tests"))
    shutil.copytree(STUDIO_ROOT / ".tropo" / "scripts", tmp / ".tropo" / "scripts",
                     ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / "vault" / "files").mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "step_redeclare_engine_%s" % abs(hash(str(tmp))),
        tmp / "vault" / "tools" / "9e7003b1.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    # `tmp` is pre-resolved by every caller (Path(tempfile.mkdtemp()).resolve())
    # specifically so this comparison holds on macOS, where /var is a symlink
    # to /private/var: module.VAULT_ROOT is computed via .resolve() from the
    # loaded file's own __file__ and so follows the symlink, but the raw
    # tempfile.mkdtemp() string does not -- the two paths name the same
    # directory and never compare equal unmatched. Reported by argus-a160
    # (2026-08-28), all 31 tests failing in setUp on his machine.
    assert module.VAULT_ROOT == tmp, "engine did not resolve to the isolated copy"
    return module


def _copy_real_wedged_run(tmp: Path) -> Path:
    """The real wedged d445af8b corpus — frozen 2026-08-28 at the exact bytes
    that were on disk while the run was wedged (run.jsonl md5
    bc6abf90e7704d7f18883293ef5eedb4, the value argus-a160 recorded as
    untouched through the Guardrail-4 corrections).

    FROZEN, not live: the suite was built reading the live run — correct while
    the wedge existed and this suite was the gate against touching it. On
    2026-08-28 the guardrails cleared and the run progressed past the wedge,
    which flipped every live-coupled test red on a GREEN engine: the premise
    '2e9b1db7 is started' became false because the mechanism WORKED. The
    frozen fixture keeps testing the exact wedged shape that existed when the
    contract was written, decoupled from a run that is supposed to move. The
    freeze is a straight copy from git commit 5cadc7db3 — journal, state, both
    governed entries — nothing hand-edited."""
    fixture_dir = STUDIO_ROOT / "vault" / "tools" / "tests" / "fixtures" / "d445af8b_wedged"
    for uid in (REAL_ACTIVATION_UID, "d445af8b"):
        shutil.copy(fixture_dir / f"{uid}.md",
                    tmp / "vault" / "files" / f"{uid}.md")
    run_dir = tmp / "vault" / "pipeline-runs" / REAL_RUN_FOLDER
    run_dir.mkdir(parents=True)
    for name in ("run.jsonl", "run.state.json"):
        shutil.copy(fixture_dir / name, run_dir / name)
    return run_dir


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


class RealWedgedRunDryRun(unittest.TestCase):
    """Argus's own instruction: use the real wedged run, not only fixtures.
    His three claimed dry-run outcomes, reproduced independently rather than
    trusted — "that is me probing my own code and it certifies nothing."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)
        self.run_dir = _copy_real_wedged_run(self.tmp)

    def test_the_started_step_would_proceed(self):
        result = self.engine.action_step_redeclare(
            REAL_ACTIVATION_UID, "2e9b1db7", "verifier",
            reason="probe", failed_invocation="probe", dry_run=True)
        self.assertIn("would emit step_redeclared", result)
        self.assertIn("'started' -> 'declared'", result)

    def test_the_verified_step_is_refused(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "f9365ede", "verifier",
                reason="probe", failed_invocation="probe", dry_run=True)
        self.assertIn("'verified'", str(ctx.exception))

    def test_the_declared_step_is_refused(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "8654900a", "verifier",
                reason="probe", failed_invocation="probe", dry_run=True)
        self.assertIn("'declared'", str(ctx.exception))

    def test_every_other_verified_step_in_the_real_run_is_also_refused(self):
        """0cf86ea5, 4f64ec3c, 37996741 are also 'verified' on the real run —
        swept, not just the one Argus happened to quote."""
        for step_uid in ("0cf86ea5", "4f64ec3c", "37996741"):
            with self.assertRaises(self.engine.ContractError):
                self.engine.action_step_redeclare(
                    REAL_ACTIVATION_UID, step_uid, "verifier",
                    reason="probe", failed_invocation="probe", dry_run=True)

    def test_a_step_uid_not_in_the_run_is_refused(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "ffffffff", "verifier",
                reason="probe", failed_invocation="probe", dry_run=True)
        self.assertIn("not in this run", str(ctx.exception))

    def test_dry_run_against_the_real_run_writes_nothing_at_all(self):
        jsonl, state_json = self.run_dir / "run.jsonl", self.run_dir / "run.state.json"
        before = (_md5(jsonl), _md5(state_json))
        # One eligible + one refused call — both must be no-ops on disk.
        self.engine.action_step_redeclare(
            REAL_ACTIVATION_UID, "2e9b1db7", "verifier",
            reason="probe", failed_invocation="probe", dry_run=True)
        try:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "f9365ede", "verifier",
                reason="probe", failed_invocation="probe", dry_run=True)
        except self.engine.ContractError:
            pass
        after = (_md5(jsonl), _md5(state_json))
        self.assertEqual(before, after)


class Guardrail1RefusesEveryNonStartedStatus(unittest.TestCase):
    """1a, swept across every status the action must refuse, each pinned to
    its own named reason so a differently-broken guard cannot coincidentally
    satisfy a looser assertion. 'completed' and 'failed' are not present on
    the real run today, so a minimal synthetic run supplies them —
    everything else here is the real wedged run."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)
        self.run_dir = _copy_real_wedged_run(self.tmp)

    def _inject(self, step_uid: str, *rows) -> None:
        jsonl = self.run_dir / "run.jsonl"
        with jsonl.open("a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

    def test_started_is_the_only_accepted_status(self):
        result = self.engine.action_step_redeclare(
            REAL_ACTIVATION_UID, "2e9b1db7", "verifier",
            reason="x", failed_invocation="x", dry_run=True)
        self.assertIn("would emit", result)

    def test_verified_is_refused_naming_verified(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "f9365ede", "verifier",
                reason="x", failed_invocation="x", dry_run=True)
        self.assertIn("'verified', not 'started'", str(ctx.exception))

    def test_declared_is_refused_naming_declared(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "8654900a", "verifier",
                reason="x", failed_invocation="x", dry_run=True)
        self.assertIn("'declared', not 'started'", str(ctx.exception))

    def test_completed_is_refused_naming_completed(self):
        """A synthetic step, distinct from the wedged one, driven to
        'completed' (natural_verdict != pass path, per derive_state) so the
        real profile's declared-step set is untouched."""
        self._inject("cccccccc",
                     {"event": "step_declared", "data": {"step_id": "cccccccc"}},
                     {"event": "step_started", "step": "cccccccc"},
                     {"event": "step_completed", "step": "cccccccc",
                      "data": {"natural_verdict": "needs-review"}})
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "cccccccc", "verifier",
                reason="x", failed_invocation="x", dry_run=True)
        self.assertIn("'completed', not 'started'", str(ctx.exception))

    def test_failed_is_refused_naming_failed_the_converting_a_failure_case(self):
        """The specific case guardrail 1 forbids by name: a step that was
        honestly failed must stay failed, never quietly become a fresh
        start."""
        self._inject("dddddddd",
                     {"event": "step_declared", "data": {"step_id": "dddddddd"}},
                     {"event": "step_started", "step": "dddddddd"},
                     {"event": "step_failed", "step": "dddddddd"})
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "dddddddd", "verifier",
                reason="x", failed_invocation="x", dry_run=True)
        self.assertIn("'failed', not 'started'", str(ctx.exception))

    def test_the_status_guard_actually_changes_verdict_when_removed(self):
        """Mutation proof for 1a: reload a copy of the engine with the status
        check's comparison inverted, and watch a refused case start passing.

        Target is 8654900a ('declared'), not one of the 'verified' steps:
        the verified steps on this real run also carry a completion/receipt
        event, so guardrail 1b independently refuses them too and this
        mutation alone would not flip their verdict -- a correct example of
        defence in depth, but the wrong target for isolating 1a specifically.
        8654900a has never started, so it carries no such event."""
        source = (self.tmp / "vault" / "tools" / "9e7003b1.py").read_text(encoding="utf-8")
        needle = 'if status != "started":'
        self.assertIn(needle, source, "guard line moved; update this mutation probe")
        mutated = source.replace(needle, 'if False:', 1)
        mutant_path = self.tmp / "vault" / "tools" / "9e7003b1_mutant.py"
        mutant_path.write_text(mutated, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            "step_redeclare_mutant_%s" % abs(hash(str(self.tmp))), mutant_path)
        mutant = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mutant
        spec.loader.exec_module(mutant)
        result = mutant.action_step_redeclare(
            REAL_ACTIVATION_UID, "8654900a", "verifier",
            reason="x", failed_invocation="x", dry_run=True)
        self.assertIn("would emit", result,
                      "mutation did not flip the verdict -- the probe is not "
                      "actually exercising the status guard")


class Guardrail1bBlockingEventsOverrideAnApparentStartedStatus(unittest.TestCase):
    """The defensive second check: even when the derived status reads
    'started', a step_completed/verification_receipt SINCE THE STEP'S MOST
    RECENT RESET in that step's raw history must still refuse. Constructed
    via the one real way this shape arises -- a step re-started after a
    genuine completion (a retried step-start, or a re-triggered leg) -- not
    an arbitrary invalid state. The reset-scoping itself (2026-08-28
    correction) is tested both ways below: no reset since the completion
    must still refuse, and a genuine reset (package_superseded naming the
    step) before the restart must be ALLOWED -- unscoped, that second case
    would reopen the exact wedge this action exists to close for any step
    that ever completed, which is the re-wedge two independent verifiers
    found."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)
        self.run_dir = _copy_real_wedged_run(self.tmp)

    def test_a_step_completed_then_restarted_still_refuses_despite_reading_started(self):
        jsonl = self.run_dir / "run.jsonl"
        with jsonl.open("a", encoding="utf-8") as f:
            for row in (
                {"event": "step_declared", "data": {"step_id": "eeeeeeee"}},
                {"event": "step_started", "step": "eeeeeeee"},
                {"event": "step_completed", "step": "eeeeeeee",
                 "data": {"natural_verdict": "pass", "verification_command_exit_code": 0}},
                {"event": "step_started", "step": "eeeeeeee"},  # re-fired
            ):
                f.write(json.dumps(row) + "\n")

        # Confirm the precondition: derived status genuinely reads 'started'.
        _, _, _, events, state = self.engine.load_run(REAL_ACTIVATION_UID, dry_run=True)
        self.assertEqual(state["step_status"]["eeeeeeee"], "started")

        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "eeeeeeee", "verifier",
                reason="x", failed_invocation="x", dry_run=True)
        self.assertIn("completion/receipt event", str(ctx.exception))

    def test_a_verification_receipt_then_restarted_also_still_refuses(self):
        jsonl = self.run_dir / "run.jsonl"
        with jsonl.open("a", encoding="utf-8") as f:
            for row in (
                {"event": "step_declared", "data": {"step_id": "ffffffaa"}},
                {"event": "step_started", "step": "ffffffaa"},
                {"event": "verification_receipt", "step": "ffffffaa", "data": {"verdict": "pass"}},
                {"event": "step_started", "step": "ffffffaa"},
            ):
                f.write(json.dumps(row) + "\n")
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "ffffffaa", "verifier",
                reason="x", failed_invocation="x", dry_run=True)
        self.assertIn("completion/receipt event", str(ctx.exception))

    def test_the_blocking_check_actually_changes_verdict_when_removed(self):
        source = (self.tmp / "vault" / "tools" / "9e7003b1.py").read_text(encoding="utf-8")
        needle = "if blocking:"
        self.assertIn(needle, source, "guard line moved; update this mutation probe")
        mutated = source.replace(needle, "if False:", 1)
        mutant_path = self.tmp / "vault" / "tools" / "9e7003b1_mutant_1b.py"
        mutant_path.write_text(mutated, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            "step_redeclare_mutant_1b_%s" % abs(hash(str(self.tmp))), mutant_path)
        mutant = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mutant
        spec.loader.exec_module(mutant)

        jsonl = self.run_dir / "run.jsonl"
        with jsonl.open("a", encoding="utf-8") as f:
            for row in (
                {"event": "step_declared", "data": {"step_id": "eeeeeeee"}},
                {"event": "step_started", "step": "eeeeeeee"},
                {"event": "step_completed", "step": "eeeeeeee",
                 "data": {"natural_verdict": "pass", "verification_command_exit_code": 0}},
                {"event": "step_started", "step": "eeeeeeee"},
            ):
                f.write(json.dumps(row) + "\n")
        result = mutant.action_step_redeclare(
            REAL_ACTIVATION_UID, "eeeeeeee", "verifier",
            reason="x", failed_invocation="x", dry_run=True)
        self.assertIn("would emit", result,
                      "mutation did not flip the verdict -- the probe is not "
                      "actually exercising the blocking-events guard")

    def test_a_step_completed_then_superseded_then_restarted_is_allowed_to_redeclare(self):
        """The positive twin the 2026-08-28 correction added: a completion
        BEFORE the step's most recent reset (tropo.release.package_superseded
        naming this step in invalidated_steps) must NOT count against a later
        restart -- unlike the un-reset case above, which must still refuse.
        Before this correction, the blocking scan covered a step's ENTIRE
        history with no reset awareness, so a legitimately superseded-and-
        restarted step could never be redeclared either -- reopening, for
        that step, the exact wedge this action exists to close. Two
        independent verifiers proved that re-wedge on real engine event
        shapes (per _redeclare_scan_active's own docstring)."""
        jsonl = self.run_dir / "run.jsonl"
        with jsonl.open("a", encoding="utf-8") as f:
            for row in (
                {"event": "step_declared", "data": {"step_id": "eeeeeeee"}},
                {"event": "step_started", "step": "eeeeeeee"},
                {"event": "step_completed", "step": "eeeeeeee",
                 "data": {"natural_verdict": "pass", "verification_command_exit_code": 0}},
                {"event": "tropo.release.package_superseded",
                 "data": {"invalidated_steps": ["eeeeeeee"]}},
                {"event": "step_started", "step": "eeeeeeee"},
            ):
                f.write(json.dumps(row) + "\n")

        _, _, _, events, state = self.engine.load_run(REAL_ACTIVATION_UID, dry_run=True)
        self.assertEqual(state["step_status"]["eeeeeeee"], "started")

        result = self.engine.action_step_redeclare(
            REAL_ACTIVATION_UID, "eeeeeeee", "verifier",
            reason="x", failed_invocation="x", dry_run=True)
        self.assertIn("would emit", result)

    def test_the_reset_scoping_actually_changes_verdict_when_removed(self):
        """Mutation proof for the reset-scoping half specifically: neutralise
        _redeclare_scan_active's reset tracking (every `reset_at = j`
        assignment) so it degrades to the old, unscoped whole-history scan,
        and confirm the superseded-and-restarted case above -- which must be
        ALLOWED -- gets wrongly refused under the mutant. That is the exact
        re-wedge two verifiers reported against the un-reset-aware version."""
        source = (self.tmp / "vault" / "tools" / "9e7003b1.py").read_text(encoding="utf-8")
        needle = "reset_at = j"
        # three reset points since v1.95 candidate #3 (argus-a172, 2026-09-06):
        # step_declared, the ruled re-opens (step_reverify_opened / step_reopened),
        # and package_superseded.invalidated_steps -- the mutant neutralises all.
        self.assertEqual(source.count(needle), 3,
                         "reset-tracking assignment count changed; update this mutation probe")
        mutated = source.replace(needle, "pass", 3)
        mutant_path = self.tmp / "vault" / "tools" / "9e7003b1_mutant_1b_scope.py"
        mutant_path.write_text(mutated, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            "step_redeclare_mutant_1b_scope_%s" % abs(hash(str(self.tmp))), mutant_path)
        mutant = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mutant
        spec.loader.exec_module(mutant)

        jsonl = self.run_dir / "run.jsonl"
        with jsonl.open("a", encoding="utf-8") as f:
            for row in (
                {"event": "step_declared", "data": {"step_id": "eeeeeeee"}},
                {"event": "step_started", "step": "eeeeeeee"},
                {"event": "step_completed", "step": "eeeeeeee",
                 "data": {"natural_verdict": "pass", "verification_command_exit_code": 0}},
                {"event": "tropo.release.package_superseded",
                 "data": {"invalidated_steps": ["eeeeeeee"]}},
                {"event": "step_started", "step": "eeeeeeee"},
            ):
                f.write(json.dumps(row) + "\n")
        with self.assertRaises(mutant.ContractError,
                               msg="mutation did not flip the verdict -- the probe is not "
                                   "actually exercising the reset-scoping"):
            mutant.action_step_redeclare(
                REAL_ACTIVATION_UID, "eeeeeeee", "verifier",
                reason="x", failed_invocation="x", dry_run=True)


class Guardrail1cReplayNeverHonoursAForgedRedeclare(unittest.TestCase):
    """"The test I most want and least trust myself to have gotten right."
    Pure derive_state calls -- no CLI, no run folder, no emitter -- because
    the whole point is that a text editor can write directly into run.jsonl
    and bypass the emitter entirely. Tested against derive_state itself, not
    through action_step_redeclare, so nothing here depends on guardrail 1a/1b
    also holding."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)

    def _forged_redeclare(self, step_uid: str, claimed_previous: str) -> dict:
        return {"event": "step_redeclared", "step": step_uid,
                "data": {"step_id": step_uid, "previous_status": claimed_previous,
                          "reason": "forged", "failed_invocation": "forged",
                          "redeclared_by": "attacker"}}

    def test_a_forged_redeclare_on_a_verified_step_does_not_move_it(self):
        events = [
            {"event": "step_declared", "data": {"step_id": "aaaaaaaa"}},
            {"event": "step_started", "step": "aaaaaaaa"},
            {"event": "step_completed", "step": "aaaaaaaa",
             "data": {"natural_verdict": "pass", "verification_command_exit_code": 0}},
            self._forged_redeclare("aaaaaaaa", "verified"),
        ]
        state = self.engine.derive_state(events)
        self.assertEqual(state["step_status"]["aaaaaaaa"], "verified")

    def test_a_forged_redeclare_on_a_completed_step_does_not_move_it(self):
        events = [
            {"event": "step_declared", "data": {"step_id": "bbbbbbbb"}},
            {"event": "step_started", "step": "bbbbbbbb"},
            {"event": "step_completed", "step": "bbbbbbbb", "data": {}},
            self._forged_redeclare("bbbbbbbb", "completed"),
        ]
        state = self.engine.derive_state(events)
        self.assertEqual(state["step_status"]["bbbbbbbb"], "completed")

    def test_a_forged_redeclare_via_verification_receipt_also_does_not_move_it(self):
        events = [
            {"event": "step_declared", "data": {"step_id": "cccccccc"}},
            {"event": "step_started", "step": "cccccccc"},
            {"event": "verification_receipt", "step": "cccccccc", "data": {"verdict": "pass"}},
            self._forged_redeclare("cccccccc", "verified"),
        ]
        state = self.engine.derive_state(events)
        self.assertEqual(state["step_status"]["cccccccc"], "verified")

    def test_a_genuine_redeclare_on_a_started_step_does_move_it(self):
        """The positive twin: the replay DOES honour the event for the one
        prior state it is meant to serve."""
        events = [
            {"event": "step_declared", "data": {"step_id": "dddddddd"}},
            {"event": "step_started", "step": "dddddddd"},
            self._forged_redeclare("dddddddd", "started"),
        ]
        state = self.engine.derive_state(events)
        self.assertEqual(state["step_status"]["dddddddd"], "declared")

    def test_a_two_line_forgery_started_then_redeclared_over_a_real_green_does_not_reach_declared(self):
        """The exact defect four independent verifiers reproduced against the
        UNMUTATED engine, corrected 2026-08-28. The OLD replay guard checked
        only the immediately-prior REPLAYED status, so two hand-authored
        lines -- step_started, then step_redeclared -- walked a REAL green (a
        step carrying a real verification_receipt) to 'declared': the forged
        step_started event unconditionally flips the derived status to
        'started' first (a single forged line the module's own docstring
        already discloses as out of scope for this guard -- there is no
        tamper-resistance against a text editor), and the old guard then saw
        a bare 'started' prior with no completion/receipt re-scan. Three of
        four verifiers reproduced it independently. The fix applies the same
        completion/receipt scan the emitter applies to this branch too. What
        must NOT happen, and is asserted here, is the forged step_redeclared
        additionally walking the step on to 'declared'."""
        events = [
            {"event": "step_declared", "data": {"step_id": "eeeeeeee"}},
            {"event": "step_started", "step": "eeeeeeee"},
            {"event": "verification_receipt", "step": "eeeeeeee", "data": {"verdict": "pass"}},
            {"event": "step_started", "step": "eeeeeeee"},  # forged line 1
            self._forged_redeclare("eeeeeeee", "started"),  # forged line 2
        ]
        state = self.engine.derive_state(events)
        self.assertNotEqual(state["step_status"]["eeeeeeee"], "declared")

    def test_the_replay_guard_actually_changes_verdict_when_removed(self):
        """Mutation proof for the base rule: a copy of derive_state with the
        WHOLE accepted-prior-states-and-not-blocked check widened to accept
        everything must let the forged verified-step redeclare through."""
        source = (self.tmp / "vault" / "tools" / "9e7003b1.py").read_text(encoding="utf-8")
        needle = 'if _prior in ("started", "declared") and not _blocked:'
        self.assertIn(needle, source, "guard line moved; update this mutation probe")
        mutated = source.replace(needle, "if True:", 1)
        mutant_path = self.tmp / "vault" / "tools" / "9e7003b1_mutant_1c.py"
        mutant_path.write_text(mutated, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            "step_redeclare_mutant_1c_%s" % abs(hash(str(self.tmp))), mutant_path)
        mutant = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mutant
        spec.loader.exec_module(mutant)

        events = [
            {"event": "step_declared", "data": {"step_id": "aaaaaaaa"}},
            {"event": "step_started", "step": "aaaaaaaa"},
            {"event": "step_completed", "step": "aaaaaaaa",
             "data": {"natural_verdict": "pass", "verification_command_exit_code": 0}},
            self._forged_redeclare("aaaaaaaa", "verified"),
        ]
        state = mutant.derive_state(events)
        self.assertEqual(state["step_status"]["aaaaaaaa"], "declared",
                         "mutation did not flip the verdict -- the probe is not "
                         "actually exercising the replay guard")

    def test_the_completion_receipt_scan_on_replay_actually_changes_verdict_when_removed(self):
        """Mutation proof isolating the 2026-08-28 correction specifically:
        revert the replay guard to the single-clause form four independent
        verifiers refuted (`_prior` checked alone, no completion/receipt
        re-scan) and confirm the two-line forgery above -- which must NOT
        reach 'declared' against the real engine -- is wrongly honoured by
        the reverted code. This isolates the `_blocked` half from the base
        `_prior` rule already proven above."""
        source = (self.tmp / "vault" / "tools" / "9e7003b1.py").read_text(encoding="utf-8")
        needle = 'if _prior in ("started", "declared") and not _blocked:'
        self.assertIn(needle, source, "guard line moved; update this mutation probe")
        mutated = source.replace(needle, 'if _prior in ("started", "declared"):', 1)
        mutant_path = self.tmp / "vault" / "tools" / "9e7003b1_mutant_1c_scan.py"
        mutant_path.write_text(mutated, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            "step_redeclare_mutant_1c_scan_%s" % abs(hash(str(self.tmp))), mutant_path)
        mutant = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mutant
        spec.loader.exec_module(mutant)

        events = [
            {"event": "step_declared", "data": {"step_id": "eeeeeeee"}},
            {"event": "step_started", "step": "eeeeeeee"},
            {"event": "verification_receipt", "step": "eeeeeeee", "data": {"verdict": "pass"}},
            {"event": "step_started", "step": "eeeeeeee"},
            self._forged_redeclare("eeeeeeee", "started"),
        ]
        state = mutant.derive_state(events)
        self.assertEqual(state["step_status"]["eeeeeeee"], "declared",
                         "mutation did not flip the verdict -- the probe is not "
                         "actually exercising the completion/receipt scan on replay")


class Guardrail2EventShapeAndRecording(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)
        self.run_dir = _copy_real_wedged_run(self.tmp)

    def test_the_journaled_event_carries_every_required_field(self):
        self.engine.action_step_redeclare(
            REAL_ACTIVATION_UID, "2e9b1db7", "the-verifier",
            reason="executor threw an argparse error",
            failed_invocation="tropo-check-harness-receipt.py exit 2",
            dry_run=False)
        _, _, run_folder, events, _ = self.engine.load_run(REAL_ACTIVATION_UID, dry_run=True)
        redeclares = [e for e in events if e.get("event") == "step_redeclared"]
        self.assertEqual(len(redeclares), 1)
        data = redeclares[0]["data"]
        self.assertEqual(data["step_id"], "2e9b1db7")
        self.assertEqual(data["previous_status"], "started")
        self.assertEqual(data["reason"], "executor threw an argparse error")
        self.assertEqual(data["failed_invocation"],
                         "tropo-check-harness-receipt.py exit 2")
        self.assertEqual(data["redeclared_by"], "the-verifier")

    def test_the_step_reads_declared_after_a_real_redeclare(self):
        self.engine.action_step_redeclare(
            REAL_ACTIVATION_UID, "2e9b1db7", "the-verifier",
            reason="x", failed_invocation="x", dry_run=False)
        _, _, _, _, state = self.engine.load_run(REAL_ACTIVATION_UID, dry_run=True)
        self.assertEqual(state["step_status"]["2e9b1db7"], "declared")
        self.assertIsNone(state["current_step"])

    def test_omitting_reason_is_refused_by_argparse(self):
        parser_ns = self.engine.build_parser()
        with self.assertRaises(SystemExit):
            parser_ns.parse_args([
                "--activation-uid", REAL_ACTIVATION_UID, "step-redeclare",
                "2e9b1db7", "--failed-invocation", "x"])

    def test_omitting_failed_invocation_is_refused_by_argparse(self):
        parser_ns = self.engine.build_parser()
        with self.assertRaises(SystemExit):
            parser_ns.parse_args([
                "--activation-uid", REAL_ACTIVATION_UID, "step-redeclare",
                "2e9b1db7", "--reason", "x"])

    def test_omitting_actor_is_refused_by_argparse(self):
        """Adopted 2026-08-28 (Argus A160's recommendation, T52's reasoning,
        landed by T53 in the same gesture as the code change): attribution is
        the point of a wedge record, so omission is refused rather than
        silently defaulted to the generic 'user'. This replaces
        test_actor_defaults_to_the_generic_user_when_not_supplied, which
        pinned that default as current behaviour without endorsing it."""
        parser_ns = self.engine.build_parser()
        with self.assertRaises(SystemExit):
            parser_ns.parse_args([
                "--activation-uid", REAL_ACTIVATION_UID, "step-redeclare",
                "2e9b1db7", "--reason", "x", "--failed-invocation", "x"])
        args = parser_ns.parse_args([
            "--activation-uid", REAL_ACTIVATION_UID, "step-redeclare",
            "2e9b1db7", "--reason", "x", "--failed-invocation", "x",
            "--actor", "talos-t53"])
        self.assertEqual(args.actor, "talos-t53")

    def test_an_empty_actor_is_refused_by_the_action(self):
        """The argparse requirement guards the CLI; direct API callers bypass
        argparse, so the action itself refuses an empty/whitespace actor --
        the same belt-and-braces shape the G2 empty-string enforcement uses."""
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "2e9b1db7", "   ",
                reason="a real reason", failed_invocation="a real cause",
                dry_run=True)
        self.assertIn("--actor", str(ctx.exception))


class EmptyStringIsNotAnEscape(unittest.TestCase):
    """Guardrail 2b's stated contract: '--reason and --failed-invocation are
    both REQUIRED by argparse (no defaults, no empty-string escape).' The
    argparse-required half held from the start (proven above). The
    empty-string half did NOT when this class was first written: verified
    live against the isolated copy of the shipped action, action_step_
    redeclare accepted reason="" and failed_invocation="" with no rejection,
    on both the dry-run and the real-write path. That gap was reported
    rather than silently patched or the test loosened to match -- and Argus's
    correction 3 (2026-08-28, verifier 4's own reproduction) closed it: both
    flags now refuse an empty or whitespace-only value with a ContractError,
    checked before the dry-run return. These tests now assert the CONTRACT's
    stated behaviour directly against the FIXED code, no expectedFailure
    needed -- the second time this instrument named a real defect before its
    author did."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)
        self.run_dir = _copy_real_wedged_run(self.tmp)

    def test_an_empty_reason_is_refused(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "2e9b1db7", "verifier",
                reason="", failed_invocation="a real cause", dry_run=True)
        self.assertIn("--reason", str(ctx.exception))

    def test_an_empty_failed_invocation_is_refused(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "2e9b1db7", "verifier",
                reason="a real reason", failed_invocation="", dry_run=True)
        self.assertIn("--failed-invocation", str(ctx.exception))

    def test_a_whitespace_only_reason_is_also_refused(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "2e9b1db7", "verifier",
                reason="   ", failed_invocation="a real cause", dry_run=True)
        self.assertIn("--reason", str(ctx.exception))

    def test_a_whitespace_only_failed_invocation_is_also_refused(self):
        with self.assertRaises(self.engine.ContractError) as ctx:
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "2e9b1db7", "verifier",
                reason="a real reason", failed_invocation="\t\n ", dry_run=True)
        self.assertIn("--failed-invocation", str(ctx.exception))

    def test_an_empty_reason_is_refused_before_any_real_write_too(self):
        """The contract's own claim ('checked BEFORE the dry-run return so a
        dry run fails the same way a real one does') proven on the
        non-dry-run path too, with a write-count check so this cannot pass
        by coincidence."""
        jsonl = self.run_dir / "run.jsonl"
        before = _md5(jsonl)
        with self.assertRaises(self.engine.ContractError):
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "2e9b1db7", "verifier",
                reason="", failed_invocation="a real cause", dry_run=False)
        self.assertEqual(_md5(jsonl), before)


class Guardrail2cDryRunWritesNothing(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)
        self.run_dir = _copy_real_wedged_run(self.tmp)
        self.jsonl = self.run_dir / "run.jsonl"
        self.state_json = self.run_dir / "run.state.json"

    def test_an_eligible_dry_run_writes_nothing(self):
        before = (_md5(self.jsonl), _md5(self.state_json))
        self.engine.action_step_redeclare(
            REAL_ACTIVATION_UID, "2e9b1db7", "verifier",
            reason="x", failed_invocation="x", dry_run=True)
        after = (_md5(self.jsonl), _md5(self.state_json))
        self.assertEqual(before, after)

    def test_a_refused_dry_run_also_writes_nothing(self):
        before = (_md5(self.jsonl), _md5(self.state_json))
        with self.assertRaises(self.engine.ContractError):
            self.engine.action_step_redeclare(
                REAL_ACTIVATION_UID, "f9365ede", "verifier",
                reason="x", failed_invocation="x", dry_run=True)
        after = (_md5(self.jsonl), _md5(self.state_json))
        self.assertEqual(before, after)

    def test_a_real_non_dry_run_call_does_write(self):
        """The negative control for the two tests above: proves the md5
        comparison is actually sensitive to a write, not just always equal
        because nothing in this run folder ever changes."""
        before = (_md5(self.jsonl), _md5(self.state_json))
        self.engine.action_step_redeclare(
            REAL_ACTIVATION_UID, "2e9b1db7", "verifier",
            reason="x", failed_invocation="x", dry_run=False)
        after = (_md5(self.jsonl), _md5(self.state_json))
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
