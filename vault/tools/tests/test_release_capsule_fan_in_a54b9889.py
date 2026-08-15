#!/usr/bin/env python3
"""v1.87 fan-in correction — the AC1-AC4 contract for locked dev-spec a54b9889.

Paired locked test-spec: aa1f275f. Activation 3866d17b, run 1d242d00.

The gap this locks down: the runtime is ahead of its constitution. A real dev
cycle closes its run, retires its activation and archives its root, but leaves
the dev-spec at `status: locked` with no governed completion report and no typed
acceptance evidence — exactly the three bindings `gather_row` requires. Fan-in
therefore refuses finished work, and the capsules still describe a singular
`basis_spec` and a retired release-test gauntlet.

  AC1  DevClosureFanInWeldTests ... a real complete-workflow leaves a done
                                    dev-spec, a governed completion report and
                                    separate typed passing evidence, ATOMICALLY
                                    with run/activation/root; the product feeds
                                    production `gather_row` with no hand edits;
                                    refusal and crash leave no partial claim.
  AC2  ReleasePlanContractTests ... a v1.87 plan locks from ordered
                                    receipt-bound fan-in without `basis_spec`;
                                    legacy plans carrying it stay valid.
  AC3  BuildDerivationTests ....... a release-engineering build derives from its
                                    locked plan's verified fan-in; unlocked,
                                    unrelated, mismatched and empty plans refuse;
                                    legacy basis_spec derivation is grandfathered.
  AC4  LiveRule10Tests ............ for v1.87+, four live Verify receipts over ONE
                                    package_sha256 gate the release record;
                                    pre-release-pipeline releases keep f4a8c2d6.

Every positive fixture has a mutation plant on the new authority, because a
green suite that stays green when the weld is removed is measuring nothing.
Capsule tests execute validator predicates; string presence is a secondary guard
only, since prose alone cannot refuse anything (spec: prose-only correction is
FAIL).
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
VAULT_TOOLS = ROOT / "vault" / "tools"
CAPSULES = ROOT / "vault" / "capsules"
RUNTIME = VAULT_TOOLS / "9e7003b1.py"
LOCK_PLAN = VAULT_TOOLS / "tropo-lock-release-plan.py"

if str(VAULT_TOOLS) not in sys.path:
    sys.path.insert(0, str(VAULT_TOOLS))
if str(ROOT / ".tropo" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / ".tropo" / "scripts"))

PACKAGE_SHA = "f" * 64


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


eng = _load("eng_fan_in_a54b9889", RUNTIME)
rl = _load("lock_plan_a54b9889", LOCK_PLAN)


def contract():
    """The predicate module this correction introduces.

    Imported through a helper so a missing module reads as one legible failure
    per test rather than a collection error that hides the whole suite.
    """
    from lib import release_capsule_contract  # noqa: PLC0415

    return release_capsule_contract


def entry(uid: str, **fields) -> str:
    lines = [f"uid: {uid}"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    return "---\n" + "\n".join(lines) + f"\n---\n\n# {uid}\n"


# ═══════════════════════════════════════════════════════════════════════════
# AC1 — releasable dev closure
# ═══════════════════════════════════════════════════════════════════════════
class DevClosureFanInWeldTests(unittest.TestCase):
    """The terminal transaction must produce a FANNABLE cycle, or refuse.

    These drive the real `action_terminal_verify` / `action_complete_workflow`
    in a sandboxed studio and then hand the result to the real `gather_row`.
    Asserting the frontmatter fields alone would pass while fan-in still
    refused, which is the exact failure being corrected.
    """

    ACT = "ac710001"
    RUN = "0bb10001"
    SPEC = "5ec10001"
    ROOT_PROJECT = "a0010001"
    TEST_SPEC = "7e510001"
    TEST_ACT = "ac7e0001"
    DOC_ACT = "ac7d0001"

    #: Production event substrate this suite must not touch. Rebinding
    #: `eng.VAULT_ROOT` does NOT sandbox the auto-emitter: it emits through
    #: `_emit_pipeline_event`, which reads an environment variable and has its
    #: own fail-loud floor. That floor only rejects payload UIDs which are not
    #: 8-hex, and these fixture UIDs are well-formed — so nine synthetic
    #: `tropo.pipeline.closed` events for ac710001 reached a production stream
    #: before Argus caught it (evt 104). Well-formed test data is exactly the
    #: case a shape check cannot see.
    PRODUCTION_EVENTS = ROOT / "vault" / "events"

    @classmethod
    def setUpClass(cls) -> None:
        cls._production_canary = cls.snapshot_production_events()

    @classmethod
    def tearDownClass(cls) -> None:
        after = cls.snapshot_production_events()
        assert after == cls._production_canary, (
            "this suite mutated production event substrate: "
            f"{sorted(set(after) ^ set(cls._production_canary))[:5] or 'content changed'}"
        )

    @classmethod
    def snapshot_production_events(cls) -> dict:
        return {
            str(path.relative_to(cls.PRODUCTION_EVENTS)):
                hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(cls.PRODUCTION_EVENTS.rglob("*.jsonl"))
            if path.is_file()
        }

    def setUp(self) -> None:
        self._orig = (eng.VAULT_ROOT, eng.VAULT_FILES)
        self._orig_sandbox = os.environ.get("TROPO_PIPELINE_RUNTIME_SANDBOX")
        self._make_studio()
        self.sandbox_events = self.tmp / "sandbox-events.jsonl"
        os.environ["TROPO_PIPELINE_RUNTIME_SANDBOX"] = str(self.sandbox_events)

    def _make_studio(self, *, with_evidence: bool = True) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="fan-in-ac1-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.runs = self.tmp / "vault" / "pipeline-runs"
        self.files.mkdir(parents=True)
        self.runs.mkdir(parents=True)
        eng.VAULT_ROOT, eng.VAULT_FILES = self.tmp, self.files
        self._seed(with_evidence=with_evidence)
        # The run log is deliberately untracked: terminal-verify counts an
        # uncommitted TRACKED change as a stale tree, and appending run events
        # is exactly what a live run does between commits.
        (self.tmp / ".gitignore").write_text("vault/pipeline-runs/\n", encoding="utf-8")
        self.tested_sha = self._commit_studio()
        self._seed_run_events(self.tested_sha)

    def _commit_studio(self) -> str:
        """A real committed tree, because the weld binds evidence to one SHA.

        Terminal-verify refuses a tested SHA that is not the tree that exists
        now, so a fixture that stubbed git would be testing a different closure
        than the one that runs in production.
        """
        run = lambda *args: subprocess.run(  # noqa: E731
            ["git", *args], cwd=str(self.tmp), capture_output=True, text=True, check=True)
        run("init", "-q")
        run("config", "user.email", "fixture@tropo.test")
        run("config", "user.name", "fixture")
        run("add", "-A")
        run("commit", "-qm", "fixture tree")
        return run("rev-parse", "HEAD").stdout.strip()

    def tearDown(self) -> None:
        eng.VAULT_ROOT, eng.VAULT_FILES = self._orig
        if self._orig_sandbox is None:
            os.environ.pop("TROPO_PIPELINE_RUNTIME_SANDBOX", None)
        else:
            os.environ["TROPO_PIPELINE_RUNTIME_SANDBOX"] = self._orig_sandbox
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sandboxed_events(self) -> list:
        if not self.sandbox_events.is_file():
            return []
        return [json.loads(line) for line
                in self.sandbox_events.read_text(encoding="utf-8").splitlines() if line]

    # ---------------------------------------------------------------- fixture
    def write(self, uid: str, text: str) -> None:
        (self.files / f"{uid}.md").write_text(text, encoding="utf-8")

    def fm(self, uid: str) -> dict:
        text = (self.files / f"{uid}.md").read_text(encoding="utf-8")
        return yaml.safe_load(text.split("---")[1]) or {}

    def _seed(self, *, with_evidence: bool = True) -> None:
        self.write(self.ROOT_PROJECT, entry(
            self.ROOT_PROJECT, type="project", title="activation root",
            status="active", state="active"))
        # The test leg is a real triggered test-pipeline activation that
        # finished, which is the coupling shape a genuine cycle carries; the
        # attested route would need a principal registry this sandbox has no
        # business inventing.
        self.write(self.TEST_ACT, entry(
            self.TEST_ACT, type="activation", title="paired test cycle",
            status="retired", activation_class="pipeline"))
        self.write(self.DOC_ACT, entry(
            self.DOC_ACT, type="activation", title="paired doc cycle",
            status="retired", activation_class="pipeline"))
        self.write(self.SPEC, entry(
            self.SPEC, type="dev-spec", title="the cycle under test",
            status="locked", target_release="'1.87.0'",
            dev_spec_activation_uid=f"'{self.ACT}'",
            triggered_test_activation_uids=[self.TEST_ACT],
            triggered_doc_activation_uids=[self.DOC_ACT]))
        self.write(self.ACT, entry(
            self.ACT, type="activation", title="activation", status="active",
            activation_class="pipeline", dev_spec_uid=f"'{self.SPEC}'",
            activation_root_project=f"'{self.ROOT_PROJECT}'"))
        self.write(self.RUN, entry(
            self.RUN, type="pipeline-run", title="run", status="active",
            pipeline="da3f50dc", activation=f"'{self.ACT}'",
            substrate_authored_by=f"'{self.ACT}'",
            run_folder=f"'vault/pipeline-runs/dev-run-{self.RUN}'"))
        if with_evidence:
            # Typed passing evidence bound to THIS activation: a done paired
            # test-spec, which is the shape the spec names in C0.
            self.write(self.TEST_SPEC, entry(
                self.TEST_SPEC, type="test-spec", title="paired contract",
                status="done", verdict="pass",
                triggered_by_dev_cycle=f"'{self.ACT}'",
                triggering_dev_spec=f"'{self.SPEC}'"))

    def _seed_run_events(self, tested_sha: str) -> None:
        self.run_folder = self.runs / f"dev-run-{self.RUN}"
        self.run_folder.mkdir(parents=True, exist_ok=True)
        for event in (
            eng.make_event("run_created", "talos", trace_id=self.ACT, data={}),
            eng.make_event("step_declared", "talos", step="s1", trace_id=self.ACT, data={
                "step_id": "s1", "step_owner_role": "talos",
                "step_verifier_role": "same-as-executor",
                "verification_class": False, "depends_on_steps": [],
                "trust_level": "auto", "exit_criteria": ["file_exists: vault"],
                "retry_policy": {"max_retries": 0, "backoff": "linear"},
                "timeout_hours": 24, "compensation_step_id": None,
                "instructions_ref": None,
            }),
            eng.make_event("step_completed", "talos", step="s1", trace_id=self.ACT,
                           data={"natural_verdict": "pass"}),
            eng.make_event("verification_receipt", "talos", step="s1", trace_id=self.ACT,
                           data={"verifier_role_resolved": "talos", "verdict": "pass",
                                 "tested_commit_sha": tested_sha,
                                 "per_criterion": [{"criterion": "file_exists: vault",
                                                    "verdict": "pass"}],
                                 "rubric_scores": {"exit_criteria_coverage": 1.0},
                                 "overall_rationale": "fixture"}),
        ):
            eng.append_event(self.run_folder, event)

    def close(self, verify: bool = True, **kwargs):
        """Drive the REAL terminal contract, then the real closure.

        Terminal-verify is where the canonical dev-close receipt is welded, and
        `gather_row` reads that receipt rather than any frontmatter field. A
        fixture that skipped it would be hand-feeding fan-in the very provenance
        this correction exists to make real.
        """
        if verify and not kwargs.get("dry_run"):
            eng.action_terminal_verify(self.ACT, "talos", tested_sha=self.tested_sha)
        return eng.action_complete_workflow(self.ACT, "talos", **kwargs)

    def _fannable_row(self):
        """Feed the real production fan-in reader, with no hand edits."""
        return rl.gather_row(self.SPEC, self.files)

    # ------------------------------------------------------------ the weld
    def test_closure_produces_a_fannable_cycle(self) -> None:
        self.close()

        spec = self.fm(self.SPEC)
        self.assertEqual(spec.get("status"), "done",
                         "closure left the dev-spec locked, so fan-in refuses "
                         "finished work")
        report_uid = spec.get("completion_report_uid")
        self.assertTrue(report_uid, "no governed completion report was minted")
        report = self.fm(str(report_uid))
        self.assertEqual(report.get("type"), "completion-report",
                         "completion_report_uid does not name a governed "
                         "completion-report entry")
        evidence = spec.get("acceptance_evidence") or []
        self.assertTrue(evidence, "no typed acceptance evidence was bound")
        self.assertNotIn(str(report_uid), [str(u) for u in evidence],
                         "the completion report is impersonating acceptance "
                         "evidence; the spec requires two separate artifacts")

    def test_closure_events_land_in_the_sandbox_not_production(self) -> None:
        """The isolation itself, asserted rather than assumed.

        A canary alone proves nothing was written; it cannot distinguish an
        isolated emitter from one that never fired. This requires the events to
        exist somewhere, and that somewhere to be the sandbox.
        """
        self.close()
        emitted = self.sandboxed_events()
        self.assertTrue(emitted, "closure emitted no pipeline events at all, so "
                                 "the canary would pass on a dead emitter")
        self.assertTrue(all(e.get("sandboxed") for e in emitted))
        self.assertIn("tropo.pipeline.closed", [e.get("type") for e in emitted])

    def test_the_closed_cycle_feeds_production_gather_row(self) -> None:
        self.close()
        row = self._fannable_row()
        for field in ("dev_spec_uid", "activation_uid", "pipeline_run_uid",
                      "tested_final_commit", "completion_receipt_sha256",
                      "acceptance_evidence_sha256"):
            self.assertTrue(row.get(field), f"fan-in row missing {field}")

    def test_removing_the_weld_makes_fan_in_refuse(self) -> None:
        """Mutation: the three bindings ARE the fannability, one at a time."""
        self.close()
        self.assertTrue(self._fannable_row())

        spec_path = self.files / f"{self.SPEC}.md"
        original = spec_path.read_text(encoding="utf-8")
        head, front, body = original.split("---", 2)
        loaded = yaml.safe_load(front)

        def rewrite(mutate) -> None:
            """Round-trip the YAML rather than editing lines.

            Line surgery on a frontmatter block produced an unparseable file,
            and `gather_row` then refused for the wrong reason — a mutation that
            breaks the fixture proves nothing about the weld.
            """
            fm = copy.deepcopy(loaded)
            mutate(fm)
            spec_path.write_text(
                "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---" + body,
                encoding="utf-8")

        for label, mutate, expect in (
            ("report", lambda fm: fm.pop("completion_report_uid"), "completion report"),
            ("evidence", lambda fm: fm.pop("acceptance_evidence"), "acceptance"),
        ):
            with self.subTest(removed=label):
                rewrite(mutate)
                with self.assertRaises(Exception) as raised:
                    self._fannable_row()
                self.assertIn(expect, str(raised.exception).lower())
                spec_path.write_text(original, encoding="utf-8")

        # `done` is gated by assert_member_is_fannable, not gather_row: the row
        # builder binds provenance, the membership gate decides whether finished
        # work may be admitted. Asserting it through the wrong function would
        # have quietly passed while the status weld did nothing.
        from lib import fan_in  # noqa: PLC0415

        rewrite(lambda fm: fm.__setitem__("status", "locked"))
        with self.assertRaises(fan_in.FanInRefusal) as refused:
            fan_in.assert_member_is_fannable(
                yaml.safe_load(spec_path.read_text(encoding="utf-8").split("---")[1]),
                [], "c447e001")
        self.assertIn("done", str(refused.exception).lower())
        spec_path.write_text(original, encoding="utf-8")

        self.assertTrue(self._fannable_row(), "the matrix did not restore green")

    # ------------------------------------------------------------- refusals
    def test_closure_refuses_when_no_passing_evidence_exists(self) -> None:
        """No evidence means refuse, not close-and-lie."""
        shutil.rmtree(self.tmp, ignore_errors=True)
        self._make_studio(with_evidence=False)

        with self.assertRaises(SystemExit) as raised:
            self.close()
        self.assertNotEqual(raised.exception.code, 0)

        spec = self.fm(self.SPEC)
        self.assertEqual(spec.get("status"), "locked",
                         "a refused closure still flipped the dev-spec to done")
        self.assertIsNone(spec.get("completion_report_uid"))
        self.assertEqual(self.fm(self.RUN).get("status"), "active",
                         "a refused closure completed the run anyway")

    def test_dry_run_names_every_write_and_performs_none(self) -> None:
        # Provenance first: a dry run predicts the REAL outcome, and the real
        # close now refuses without a canonical receipt (2175f969). Letting the
        # preview skip a gate the execution enforces is how a dry run becomes a
        # reassurance rather than a rehearsal.
        eng.action_terminal_verify(self.ACT, "talos", tested_sha=self.tested_sha)
        before = {p: p.read_bytes() for p in self.files.rglob("*.md")}
        report = self.close(dry_run=True)
        for expected in ("dev-spec", "completion report", "acceptance"):
            self.assertIn(expected, str(report).lower(),
                          f"dry-run does not name the {expected} write")
        after = {p: p.read_bytes() for p in self.files.rglob("*.md")}
        self.assertEqual(before, after, "dry-run wrote to the vault")

    def test_retry_is_idempotent(self) -> None:
        self.close()
        first = self.fm(self.SPEC)
        reports = sorted(p.name for p in self.files.glob("*.md"))
        # Re-close only: terminal-verify legitimately refuses a second run
        # because the first close changed the tracked tree, and retry here
        # means "run the terminal transaction again", not "re-verify".
        #
        # Swallowing SystemExit here would let a refusing retry pass as an
        # idempotent one (Argus, evt 103): "did not duplicate" is also true of
        # a transaction that did nothing and gave up. Retry must return an
        # explicit converged result.
        result = self.close(verify=False)
        self.assertIn("converged", str(result).lower(),
                      f"retry returned {result!r}; an idempotent retry must say "
                      "it converged rather than refuse")
        second = self.fm(self.SPEC)
        self.assertEqual(first.get("completion_report_uid"),
                         second.get("completion_report_uid"),
                         "retry minted a second completion report")
        self.assertEqual(reports, sorted(p.name for p in self.files.glob("*.md")),
                         "retry created additional entries")

    def test_a_crash_mid_transaction_leaves_no_partial_fannable_claim(self) -> None:
        """Fail after the dev-spec flip: the cycle must not look fannable."""
        original = eng.write_vault_entry
        state = {"calls": 0}

        def exploding(uid, fm, body, *args, **kwargs):
            state["calls"] += 1
            if str(fm.get("type")) == "completion-report":
                raise RuntimeError("simulated crash before the report lands")
            return original(uid, fm, body, *args, **kwargs)

        eng.write_vault_entry = exploding
        try:
            with self.assertRaises((RuntimeError, SystemExit)):
                self.close()
        finally:
            eng.write_vault_entry = original

        with self.assertRaises(Exception):
            self._fannable_row()

        # RECOVERY IS THE PROMISE, not just refusal (Argus, evt 103). A journal
        # that only guarantees "the partial state is rejected" leaves the cycle
        # permanently unfannable, which is a different failure from the one it
        # was built to prevent. The retry must reach a coherent terminal bundle.
        recovered = self.close(verify=False)
        self.assertTrue(recovered)
        spec = self.fm(self.SPEC)
        self.assertEqual(spec.get("status"), "done")
        self.assertTrue(spec.get("completion_report_uid"))
        self.assertTrue(spec.get("acceptance_evidence"))
        self.assertTrue(self._fannable_row(),
                        "recovery did not produce a fannable cycle")

    # ----------------------------------------------------------- convergence
    def test_a_previously_complete_cycle_can_converge_without_inventing_history(self) -> None:
        """Compact-Continue's real closed cycle is the case this must serve.

        Existing completed cycles closed before this correction: run complete,
        activation retired, root archived, dev-spec still locked. They must
        become fannable from the evidence that already exists, and must NOT be
        made fannable when that evidence does not.
        """
        self.close()
        spec_path = self.files / f"{self.SPEC}.md"
        stale = spec_path.read_text(encoding="utf-8")
        stale = stale.replace("status: done", "status: locked")
        stale = "\n".join(line for line in stale.splitlines()
                          if not line.startswith("completion_report_uid")
                          and not line.startswith("acceptance_evidence")
                          and not line.startswith("  - 7e51")) + "\n"
        spec_path.write_text(stale, encoding="utf-8")

        converged = eng.action_converge_dev_closure(self.ACT, "talos")
        self.assertTrue(converged)
        self.assertEqual(self.fm(self.SPEC).get("status"), "done")
        self.assertTrue(self._fannable_row(),
                        "convergence did not make the already-complete cycle "
                        "fannable")

    def test_convergence_refuses_a_cycle_that_never_passed(self) -> None:
        self.close()
        (self.files / f"{self.TEST_SPEC}.md").unlink()
        spec_path = self.files / f"{self.SPEC}.md"
        spec_path.write_text(spec_path.read_text(encoding="utf-8")
                             .replace("status: done", "status: locked"),
                             encoding="utf-8")
        with self.assertRaises((SystemExit, RuntimeError, ValueError, eng.ValidationError)):
            eng.action_converge_dev_closure(self.ACT, "talos")


# ═══════════════════════════════════════════════════════════════════════════
# AC2 — release-plan authority
# ═══════════════════════════════════════════════════════════════════════════
class ReleasePlanContractTests(unittest.TestCase):
    """`basis_spec` becomes optional legacy; fan-in becomes the authority."""

    def plan(self, **over) -> dict:
        base = {
            "uid": "c447e001", "type": "release-plan", "status": "locked",
            "release_version": "1.87.0", "state": "active",
            "dev_spec_uids": ["5ec10001", "5ec10002"],
            "fan_in_manifest_ref": "vault/fan-in/c447e001.json",
            "fan_in_digest": "d" * 64,
            "release_activation_uid": "ac7c4471",
            "release_pipeline_run_uid": "0bbc4471",
        }
        base.update(over)
        return base

    def test_a_v187_plan_validates_without_basis_spec(self) -> None:
        problems = contract().check_release_plan(self.plan())
        self.assertEqual(problems, [],
                         "a v1.87 plan whose authority is its locked fan-in was "
                         f"rejected: {problems}")

    def test_removing_the_fan_in_requirements_turns_red(self) -> None:
        for field in ("dev_spec_uids", "fan_in_manifest_ref", "fan_in_digest",
                      "release_activation_uid", "release_pipeline_run_uid"):
            with self.subTest(missing=field):
                plan = self.plan()
                plan.pop(field)
                self.assertTrue(
                    contract().check_release_plan(plan),
                    f"a locked v1.87 plan missing {field} still validated, so "
                    "the fan-in is not actually the authority")

    def test_legacy_plans_carrying_basis_spec_remain_valid(self) -> None:
        legacy = {
            "uid": "b1a00099", "type": "release-plan", "status": "locked",
            "release_version": "1.53.0", "state": "active",
            "basis_spec": "826ee57b",
        }
        self.assertEqual(
            contract().check_release_plan(legacy, resolve=lambda uid: {
                "type": "design-spec", "status": "locked"}),
            [],
            "a pre-v1.87 plan lost validity when basis_spec became optional")

    def test_a_legacy_plan_with_an_unlocked_basis_spec_still_fails(self) -> None:
        legacy = {
            "uid": "b1a00098", "type": "release-plan", "status": "locked",
            "release_version": "1.53.0", "state": "active",
            "basis_spec": "826ee57b",
        }
        self.assertTrue(contract().check_release_plan(legacy, resolve=lambda uid: {
            "type": "design-spec", "status": "draft"}),
            "the grandfathered branch stopped enforcing its own rule")

    def test_the_capsule_declares_basis_spec_optional(self) -> None:
        text = (CAPSULES / "tropo-release-plan.capsule.md").read_text(encoding="utf-8")
        required, optional = text.split("## Optional Frontmatter", 1)
        self.assertNotIn("`basis_spec`", required.split("## Required Frontmatter", 1)[-1],
                         "basis_spec is still declared required")
        self.assertIn("`basis_spec`", optional,
                      "basis_spec is not declared as optional legacy")


# ═══════════════════════════════════════════════════════════════════════════
# AC3 — build derivation
# ═══════════════════════════════════════════════════════════════════════════
#: Provenance-before-close moved to its own focused module under locked
#: dev-spec 0caad12b / contract f7a3c518:
#: `vault/tools/tests/test_provenance_before_close_0caad12b.py`. It shares this
#: suite's fixture by import rather than by copy, so the runtime, the studio
#: shape and the production gather_row are the same ones accepted here.

class ProductionEnforcementTests(unittest.TestCase):
    """The predicates must be REACHABLE from production, not only from here.

    Argus's NO-GO (evt 110): `release_capsule_contract` was referenced by this
    test file and nothing else, and `tropo-check-one.py c447eb6a` printed "no
    check-family registered — SKIP (exit 0)". A green helper test says the
    function works; it says nothing about whether anything calls it. These cases
    drive the real CLI over fixture studios so the answer comes from the
    production entry point.
    """

    CHECK_ONE = VAULT_TOOLS / "tropo-check-one.py"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="fan-in-enforce-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.files.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, uid: str, text: str) -> None:
        (self.files / f"{uid}.md").write_text(text, encoding="utf-8")

    def index(self, rows: list) -> None:
        # Real index rows carry their governed source path, and the generic
        # pruning check reads it. A row without one fails for a reason that has
        # nothing to do with the family under test.
        (self.tmp / "vault" / "00-index.jsonl").write_text(
            "".join(json.dumps(dict(row, path=f"vault/files/{row['uid']}.md")) + "\n"
                    for row in rows),
            encoding="utf-8")

    def check_one(self, uid: str):
        return subprocess.run(
            [sys.executable, str(self.CHECK_ONE), uid, "--vault-path", str(self.tmp)],
            capture_output=True, text=True, timeout=600,
        )

    def seed_plan(self, uid: str, **fields) -> None:
        base = {"type": "release-plan", "status": "locked",
                "release_version": "1.87.0", "state": "active"}
        base.update(fields)
        self.write(uid, entry(uid, **base))
        self.index([{"uid": uid, "type": "release-plan"}])

    # -------------------------------------------------------------- C1 reach
    def test_check_one_refuses_a_locked_v187_plan_with_no_fan_in(self) -> None:
        self.seed_plan("c4470001")
        proc = self.check_one("c4470001")
        self.assertIn("dev_spec_uids", proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 1,
                         "the production entry point accepted a locked v1.87 "
                         "plan with no fan-in")

    def test_check_one_passes_a_valid_v187_plan(self) -> None:
        self.seed_plan(
            "c4470002",
            dev_spec_uids=["5ec10001"],
            fan_in_manifest_ref="vault/fan-in/c4470002.json",
            fan_in_digest="d" * 64,
            release_activation_uid="ac7c4472",
            release_pipeline_run_uid="0bbc4472",
        )
        proc = self.check_one("c4470002")
        self.assertEqual(proc.returncode, 0, (proc.stdout + proc.stderr)[-500:])
        self.assertNotIn("no check-family registered", proc.stdout)

    def test_check_one_passes_a_legacy_plan(self) -> None:
        self.write("826ee57b", entry("826ee57b", type="design-spec", status="locked",
                                     title="legacy basis"))
        self.write("b1a00099", entry("b1a00099", type="release-plan", status="locked",
                                     release_version="1.53.0", state="active",
                                     basis_spec="826ee57b"))
        self.index([{"uid": "b1a00099", "type": "release-plan"},
                    {"uid": "826ee57b", "type": "design-spec"}])
        proc = self.check_one("b1a00099")
        self.assertEqual(proc.returncode, 0, (proc.stdout + proc.stderr)[-500:])

    # -------------------------------------------------------------- C2 reach
    def test_check_one_refuses_a_build_derived_from_an_unlocked_plan(self) -> None:
        self.write("c4470003", entry(
            "c4470003", type="release-plan", status="specify",
            release_version="1.87.0", state="active", streams=["57e00001"],
            dev_spec_uids=["5ec10001"], fan_in_digest="d" * 64,
            fan_in_manifest_ref="vault/fan-in/c4470003.json"))
        self.write("b1d10001", entry(
            "b1d10001", type="build", build_version="1.87.0",
            derived_from=["c4470003"], member_of=["57e00001"]))
        self.index([{"uid": "c4470003", "type": "release-plan"},
                    {"uid": "b1d10001", "type": "build"}])
        proc = self.check_one("b1d10001")
        self.assertEqual(proc.returncode, 1,
                         "a build derived from an unlocked plan passed the "
                         "production entry point")
        self.assertIn("not locked", " ".join((proc.stdout + proc.stderr).split()))

    def test_check_one_passes_a_valid_v187_build(self) -> None:
        self.write("c4470004", entry(
            "c4470004", type="release-plan", status="locked",
            release_version="1.87.0", state="active", streams=["57e00001"],
            dev_spec_uids=["5ec10001"], fan_in_digest="d" * 64,
            fan_in_manifest_ref="vault/fan-in/c4470004.json",
            release_activation_uid="ac7c4474", release_pipeline_run_uid="0bbc4474"))
        self.write("b1d10002", entry(
            "b1d10002", type="build", build_version="1.87.0",
            derived_from=["c4470004"], member_of=["57e00001"]))
        self.index([{"uid": "c4470004", "type": "release-plan"},
                    {"uid": "b1d10002", "type": "build"}])
        proc = self.check_one("b1d10002")
        self.assertEqual(proc.returncode, 0, (proc.stdout + proc.stderr)[-500:])

    # ------------------------------------------------- reachability of exports
    def test_every_exported_predicate_has_a_production_caller(self) -> None:
        """A rule nothing calls is a rule the next cycle discovers by shipping."""
        module = ROOT / "vault" / "tools" / "lib" / "release_capsule_contract.py"
        tree = ast.parse(module.read_text(encoding="utf-8"))
        exported = [
            node.name for node in tree.body
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
        ]
        self.assertTrue(exported)

        internal = module.read_text(encoding="utf-8")
        production_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in sorted((ROOT / "vault" / "tools").rglob("*.py"))
            if "tests" not in path.parts and path != module
        )
        # Rule 10's enforcement is the publish gate, not this module: the
        # helper exists so the capsule contract can be asked the same question
        # offline. Exempting it silently would be the very thing this guard is
        # for, so the exemption names where the real refusal happens and the
        # next case proves that path is live.
        enforced_elsewhere = {"check_rule_10"}

        orphans = []
        for name in exported:
            if name in enforced_elsewhere:
                continue
            # Registration in a dispatcher table is a STRING, not a call. That
            # is still production reachability — it is how every other
            # check-family is reached.
            reachable = (
                f"{name}(" in production_text
                or f'"{name}"' in production_text
                or f"'{name}'" in production_text
                or internal.count(f"{name}(") > 1
            )
            if not reachable:
                orphans.append(name)
        self.assertEqual(
            orphans, [],
            f"exported but unreachable from production: {orphans}. A predicate "
            "only its own tests call cannot refuse anything.")

    def test_rule_10_enforcement_lives_on_the_publish_path(self) -> None:
        """The exemption above is only honest if that path really refuses."""
        publish = (VAULT_TOOLS / "tropo-publish-release.py").read_text(encoding="utf-8")
        self.assertIn("release_verify.assert_ready_to_publish(", publish)
        self.assertIn("release_verify.VerifyRefusal", publish,
                      "the publish path does not handle the refusal it invites")

    def test_the_dispatcher_registers_both_families(self) -> None:
        text = (VAULT_TOOLS / "tropo-check-one.py").read_text(encoding="utf-8")
        for entry_type, fn in (("release-plan", "run_all_release_plan_checks"),
                               ("build", "run_all_build_checks")):
            self.assertIn(fn, text, f"{entry_type} family not registered")


class BuildDerivationTests(unittest.TestCase):
    """A v1.87+ build derives from its locked plan; legacy stays grandfathered."""

    PLAN = {
        "uid": "c447e001", "type": "release-plan", "status": "locked",
        "release_version": "1.87.0", "state": "active",
        "streams": ["57e00001"], "dev_spec_uids": ["5ec10001"],
        "fan_in_manifest_ref": "vault/fan-in/c447e001.json",
        "fan_in_digest": "d" * 64,
    }

    def build(self, **over) -> dict:
        base = {
            "uid": "b1d10001", "type": "build", "build_version": "1.87.0",
            "derived_from": ["c447e001"], "member_of": ["57e00001"],
        }
        base.update(over)
        return base

    def test_a_build_derives_from_its_locked_plan(self) -> None:
        self.assertEqual(
            contract().check_build_derivation(self.build(), self.PLAN), [])

    def test_unqualified_plans_refuse(self) -> None:
        cases = {
            "unlocked plan": dict(self.PLAN, status="specify"),
            "version mismatch": dict(self.PLAN, release_version="1.86.0"),
            "empty fan-in": dict(self.PLAN, dev_spec_uids=[]),
            "no digest": {k: v for k, v in self.PLAN.items() if k != "fan_in_digest"},
            "no project overlap": dict(self.PLAN, streams=["99999999"]),
        }
        for name, plan in cases.items():
            with self.subTest(case=name):
                self.assertTrue(
                    contract().check_build_derivation(self.build(), plan),
                    f"{name} still qualified")

    def test_a_build_pointed_at_an_unrelated_plan_refuses(self) -> None:
        self.assertTrue(contract().check_build_derivation(
            self.build(derived_from=["deadbeef"]), self.PLAN),
            "a build not naming its plan in derived_from still qualified")

    def test_legacy_basis_spec_derivation_is_grandfathered(self) -> None:
        legacy_plan = {
            "uid": "b1a00099", "type": "release-plan", "status": "locked",
            "release_version": "1.53.0", "streams": ["57e00009"],
            "basis_spec": "826ee57b",
        }
        legacy_build = {
            "uid": "b1d10099", "type": "build", "build_version": "1.53.0",
            "derived_from": ["826ee57b"], "member_of": ["57e00009"],
        }
        self.assertEqual(
            contract().check_build_derivation(
                legacy_build, legacy_plan,
                resolve=lambda uid: {"type": "design-spec", "status": "locked"}),
            [],
            "a pre-v1.87 build lost its grandfathered derivation")

    def test_a_new_plan_may_not_fall_back_to_the_legacy_branch(self) -> None:
        """Compatibility is a branch for old plans, not an escape hatch."""
        plan = dict(self.PLAN, basis_spec="826ee57b", dev_spec_uids=[])
        self.assertTrue(
            contract().check_build_derivation(
                self.build(derived_from=["826ee57b"]), plan,
                resolve=lambda uid: {"type": "design-spec", "status": "locked"}),
            "a v1.87 plan with no fan-in qualified through the legacy branch")


# ═══════════════════════════════════════════════════════════════════════════
# AC4 — live Rule 10
# ═══════════════════════════════════════════════════════════════════════════
class LiveRule10Tests(unittest.TestCase):
    """Four live Verify receipts over one frozen package, not f4a8c2d6."""

    RUN = "0bbc4471"

    def receipts(self) -> list:
        from lib import release_verify  # noqa: PLC0415

        return [{
            "receipt_kind": "release-verification-receipt",
            "instrument": instrument,
            "release_run_uid": self.RUN,
            "package_sha256": PACKAGE_SHA,
            "verdict": "pass",
            "executor_or_attester": "talos-t41",
            "execution_mode": "machine",
            "evidence_ref": f"vault/receipts/{instrument}.json",
            "started_at": "2026-08-13T10:00:00Z",
            "completed_at": "2026-08-13T10:05:00Z",
        } for instrument in release_verify.INSTRUMENTS]

    def release(self, **over) -> dict:
        base = {
            "uid": "5e1c4471", "type": "release", "release_version": "1.87.0",
            "release_date": "2026-08-20", "package_sha256": PACKAGE_SHA,
            "release_pipeline_run_uid": self.RUN,
        }
        base.update(over)
        return base

    def test_four_receipts_over_one_package_satisfy_rule_10(self) -> None:
        self.assertEqual(
            contract().check_rule_10(self.release(), self.receipts()), [])

    def test_a_missing_receipt_fails(self) -> None:
        for index in range(4):
            with self.subTest(dropped=index):
                short = [r for i, r in enumerate(self.receipts()) if i != index]
                self.assertTrue(contract().check_rule_10(self.release(), short))

    def test_a_duplicate_receipt_fails(self) -> None:
        doubled = self.receipts()
        doubled.append(copy.deepcopy(doubled[0]))
        self.assertTrue(contract().check_rule_10(self.release(), doubled),
                        "two executions with one record still certified")

    def test_a_receipt_over_a_different_package_fails(self) -> None:
        drifted = self.receipts()
        drifted[2]["package_sha256"] = "e" * 64
        self.assertTrue(contract().check_rule_10(self.release(), drifted),
                        "an instrument that approved other bytes counted")

    def test_a_failing_verdict_fails(self) -> None:
        failed = self.receipts()
        failed[1]["verdict"] = "fail"
        self.assertTrue(contract().check_rule_10(self.release(), failed))

    def test_pre_release_pipeline_releases_keep_historical_semantics(self) -> None:
        historical = self.release(uid="5e1c0153", release_version="1.53.0",
                                  release_date="2026-05-25")
        historical.pop("package_sha256")
        historical.pop("release_pipeline_run_uid")
        self.assertEqual(
            contract().check_rule_10(historical, []), [],
            "a historical release was retroactively judged by the live gate")

    def test_the_capsule_no_longer_names_f4a8c2d6_as_the_live_gate(self) -> None:
        text = (CAPSULES / "tropo-release.capsule.md").read_text(encoding="utf-8")
        rule = text.split("Rule 10", 1)[-1][:4000]
        self.assertIn("package_sha256", rule,
                      "Rule 10 does not bind receipts to one frozen package")
        for node in ("4262d5fa", "a0f2bea8", "bc6b17ec", "c6b61fb9"):
            self.assertIn(node, text,
                          f"Rule 10 does not name live Verify instrument {node}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
