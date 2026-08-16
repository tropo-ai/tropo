#!/usr/bin/env python3
"""Provenance before close — locked dev-spec 0caad12b, paired contract f7a3c518.

Activation a88a1ca7, run 8ae708b9, P0 task 2175f969.

The defect this locks down was found by dogfooding the v1.87 fan-in weld on its
own cycle. complete-workflow reached full terminal state — run complete,
activation retired, root archived, dev-spec done with its governed report and
typed evidence — and production `gather_row` still refused, because the
canonical `dev_closed` receipt that binds those claims to a tested tree is
written by terminal-verify, which had never run. That instance was repairable.
The ORDER was not enforced, so any later cycle could go terminal unfannable and
only discover it at release-lock time, when the cycle is closed and the repair
is archaeology.

  AC1  ReceiptPreconditionTests .. refusal before every terminal write, naming
                                   the terminal-verify cure.
  AC2  CorrectSequenceTests ...... terminal-verify then complete-workflow closes
                                   once and feeds production gather_row with no
                                   repair command afterwards.
  AC3  ZeroStepTests ............. a run with no step events obeys the same rule;
                                   it is the shape that hit this in production.
  AC4  BindingMismatchTests ...... a receipt mismatching spec, activation, run,
                                   root or tested tree refuses, each with zero
                                   terminal mutations.
  AC5  RetryAndIsolationTests .... retry is explicit and idempotent, and fixture
                                   closure events exist only in the sandbox.

The fixture is imported from the accepted fan-in suite rather than copied: these
cases drive the same real runtime against the same real studio shape, and a
second copy of that setup would drift from the one Argus accepted.
"""
from __future__ import annotations

import unittest

def _load_fan_in_suite():
    """The accepted fan-in suite, loaded by PATH and kept as a module.

    By path, because the locked verify commands run this as
    `vault.tools.tests.test_provenance_before_close_0caad12b` from the repo
    root while a direct run imports it as a bare sibling, and a plain import
    statement can only satisfy one of those.

    Kept as a module rather than importing its TestCase by name, because a
    TestCase bound into this namespace is collected here too — the accepted
    cases would then run a second time inside the focused module, which is the
    duplication a focused module exists to avoid.
    """
    import importlib.util  # noqa: PLC0415
    import sys  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    name = "test_release_capsule_fan_in_a54b9889"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, str(Path(__file__).resolve().parent / f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fan_in_suite = _load_fan_in_suite()
eng = fan_in_suite.eng


class _ProvenanceCase(fan_in_suite.DevClosureFanInWeldTests):
    """Shared fixture, with the inherited AC1-bundle cases left behind.

    Subclassing gives the real runtime, the sandboxed studio, the git-backed
    tested tree and the production `gather_row`. The parent's own tests are
    dropped here so each locked class runs exactly the behaviour it names —
    inheriting them would report the parent's coverage five more times and
    make a focused module a duplicate one.
    """

    @classmethod
    def _drop_inherited_cases(cls) -> None:
        for name in dir(fan_in_suite.DevClosureFanInWeldTests):
            if name.startswith("test_") and name not in cls.__dict__:
                setattr(cls, name, None)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._drop_inherited_cases()

    # Applied to this class too, immediately below its definition: the loader
    # collects intermediate classes as well, and `__init_subclass__` never fires
    # for the class that defines it. Without this the parent's ten cases ran a
    # second time here, which is the duplicate module the focused-module ruling
    # exists to avoid.

    def vault_snapshot(self) -> dict:
        return {path.name: path.read_bytes() for path in self.files.rglob("*.md")}

    def assert_refused_without_mutating(self, snapshot: dict) -> None:
        """Zero terminal mutations, measured as a DIFFERENCE.

        Asserting absolute states (run active, root not archived) reads the
        wrong thing once terminal-verify has run: its weld legitimately
        archives the activation root, so an absolute check calls the previous
        step's correct work a mutation by this one. What the ruling requires is
        that the refused CLOSE changed nothing.
        """
        self.assertEqual(snapshot, self.vault_snapshot(),
                         "a refused close mutated the vault")
        self.assertNotEqual(self.fm(self.SPEC).get("status"), "done",
                            "a refused close flipped the dev-spec to done")
        self.assertIsNone(self.fm(self.SPEC).get("completion_report_uid"),
                          "a refused close minted a completion report")
        self.assertNotEqual(self.fm(self.RUN).get("status"), "complete",
                            "a refused close completed the run")

    def commit_post_test_evidence(self, *, tested_commit: str | None = None,
                                  mutate_spec=None) -> str:
        """Commit the exact two-layer shape used by a real independent report."""
        import subprocess
        import yaml

        report_uid = "e1de0001"
        claimed = tested_commit or self.tested_sha
        self.write(report_uid, fan_in_suite.entry(
            report_uid, type="verification-report", title="independent report",
            status="accepted", verdict="pass", tested_commit=claimed,
            triggering_dev_spec=self.SPEC,
            triggered_by_dev_cycle=self.ACT))

        spec_path = self.files / f"{self.SPEC}.md"
        raw = spec_path.read_text(encoding="utf-8")
        _empty, frontmatter, body = raw.split("---", 2)
        spec_fm = yaml.safe_load(frontmatter) or {}
        spec_fm["acceptance_evidence"] = [report_uid]
        if mutate_spec is not None:
            mutate_spec(spec_fm)
        spec_path.write_text(
            "---\n" + yaml.safe_dump(spec_fm, sort_keys=False) + "---" + body,
            encoding="utf-8")

        run = lambda *args: subprocess.run(  # noqa: E731
            ["git", *args], cwd=str(self.tmp), capture_output=True, text=True,
            check=True)
        run("add", str(spec_path.relative_to(self.tmp)),
            str((self.files / f"{report_uid}.md").relative_to(self.tmp)))
        run("commit", "-qm", "bind independent post-test evidence")
        return run("rev-parse", "HEAD").stdout.strip()


_ProvenanceCase._drop_inherited_cases()


# ─── AC1 — the precondition ──────────────────────────────────────────────────
class ReceiptPreconditionTests(_ProvenanceCase):
    """No canonical receipt, no close — and nothing moves on the way out."""

    def test_close_without_a_receipt_refuses_before_every_terminal_write(self) -> None:
        before = self.vault_snapshot()

        with self.assertRaises(SystemExit) as raised:
            self.close(verify=False)
        self.assertNotEqual(raised.exception.code, 0)

        self.assert_refused_without_mutating(before)

    def test_the_refusal_names_the_terminal_verify_cure(self) -> None:
        """A refusal that does not say what to run is a puzzle, not a gate."""
        printed = self.captured_refusal()
        self.assertIn("terminal-verify", printed)
        self.assertIn(self.ACT, printed)
        self.assertIn("--tested-sha", printed)

    def test_dry_run_refuses_where_the_real_close_would(self) -> None:
        """A preview that skips a gate the execution enforces is a rehearsal of
        a different play."""
        before = self.vault_snapshot()
        with self.assertRaises(SystemExit):
            self.close(dry_run=True)
        self.assert_refused_without_mutating(before)

    def captured_refusal(self) -> str:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer), contextlib.redirect_stdout(buffer):
            with contextlib.suppress(SystemExit):
                self.close(verify=False)
        return buffer.getvalue()


# ─── AC2 — the correct sequence ──────────────────────────────────────────────
class CorrectSequenceTests(_ProvenanceCase):
    """terminal-verify then complete-workflow, and the row resolves at once."""

    def test_the_closed_cycle_is_immediately_fannable(self) -> None:
        self.close()

        spec = self.fm(self.SPEC)
        self.assertEqual(spec.get("status"), "done")
        self.assertTrue(spec.get("completion_report_uid"))
        self.assertTrue(spec.get("acceptance_evidence"))

        row = self._fannable_row()
        self.assertEqual(row["tested_final_commit"], self.tested_sha,
                         "the row binds a tree other than the verified one")
        for field in ("dev_spec_uid", "activation_uid", "pipeline_run_uid",
                      "completion_receipt_sha256", "acceptance_evidence_sha256"):
            self.assertTrue(row.get(field), f"row missing {field}")

    def test_no_repair_command_is_needed_after_closure(self) -> None:
        """The whole point: the cycle is releasable when the close returns.

        The dogfood needed a terminal-verify AFTER the close to become
        fannable. If that is still true, this correction did nothing.
        """
        self.close()
        events_before = (self.run_folder / "run.jsonl").read_text(encoding="utf-8")
        self.assertTrue(self._fannable_row())
        self.assertEqual(
            events_before, (self.run_folder / "run.jsonl").read_text(encoding="utf-8"),
            "reading the row changed the run log, so something is repairing on read")


# ─── AC3 — zero-step cycles ──────────────────────────────────────────────────
class ZeroStepTests(_ProvenanceCase):
    """The shape that hit this in production gets no exemption.

    Run 1d242d00 carried a declaration snapshot and no step events, which is
    exactly why nothing forced provenance: there were no receipts to be missing.
    """

    def strip_to_zero_steps(self) -> None:
        for path in self.run_folder.glob("*.jsonl"):
            path.unlink()
        eng.append_event(self.run_folder, eng.make_event(
            "run_created", "talos", trace_id=self.ACT, data={}))

    def test_a_zero_step_cycle_refuses_then_closes_after_terminal_verify(self) -> None:
        self.strip_to_zero_steps()
        before = self.vault_snapshot()

        with self.assertRaises(SystemExit):
            self.close(verify=False)
        self.assert_refused_without_mutating(before)

        eng.action_terminal_verify(self.ACT, "talos", tested_sha=self.tested_sha)
        self.close(verify=False)

        self.assertEqual(self.fm(self.SPEC).get("status"), "done")
        self.assertTrue(self._fannable_row(),
                        "a zero-step cycle closed but is not fannable")


# ─── AC4 — one-link mismatches ───────────────────────────────────────────────
class BindingMismatchTests(_ProvenanceCase):
    """Every link the receipt names, corrupted one at a time.

    A receipt binds spec, activation, run, root and tree. Each of those is a
    different way of being somebody else's evidence, so each is corrupted
    alone: a matrix that only breaks two of five proves the gate reads two.
    """

    def receipt_log(self):
        eng.action_terminal_verify(self.ACT, "talos", tested_sha=self.tested_sha)
        log = self.run_folder / "run.jsonl"
        return log, log.read_text(encoding="utf-8")

    def test_each_mismatched_binding_refuses_with_zero_mutations(self) -> None:
        log, original = self.receipt_log()
        cases = {
            "dev-spec": (f'"{self.SPEC}"', '"5ec99999"'),
            "activation": (f'"dev_spec_uid": "{self.SPEC}", "activation_uid": "{self.ACT}"',
                           f'"dev_spec_uid": "{self.SPEC}", "activation_uid": "ac799999"'),
            "run": (f'"pipeline_run_uid": "{self.RUN}"', '"pipeline_run_uid": "0bb99999"'),
            "root": (f'"activation_root_uid": "{self.ROOT_PROJECT}"',
                     '"activation_root_uid": "a0099999"'),
            "tested tree": (self.tested_sha, "b" * 40),
        }
        for link, (needle, replacement) in cases.items():
            with self.subTest(link=link):
                corrupted = original.replace(needle, replacement)
                self.assertNotEqual(
                    corrupted, original,
                    f"the {link} corruption did not change the receipt, so this "
                    f"case would pass without testing anything")
                log.write_text(corrupted, encoding="utf-8")
                before = self.vault_snapshot()
                try:
                    with self.assertRaises(SystemExit):
                        self.close(verify=False)
                    self.assert_refused_without_mutating(before)
                finally:
                    # Restored in `finally` so one failing link cannot leave a
                    # corrupted receipt for the next case to trip over — the
                    # first version lost the restore to an early exit and the
                    # whole matrix reported the same wrong cause.
                    log.write_text(original, encoding="utf-8")

        self.close(verify=False)
        self.assertEqual(self.fm(self.SPEC).get("status"), "done",
                         "the matrix did not restore a closable cycle")

    def test_removing_the_precondition_recreates_the_unfannable_state(self) -> None:
        """Mutation: without the gate, the dogfood defect returns exactly."""
        original = eng.assert_canonical_provenance_exists
        eng.assert_canonical_provenance_exists = lambda *a, **k: None
        try:
            self.close(verify=False)
        finally:
            eng.assert_canonical_provenance_exists = original

        self.assertEqual(self.fm(self.SPEC).get("status"), "done",
                         "the mutation did not reach a terminal close")
        with self.assertRaises(Exception) as refused:
            self._fannable_row()
        self.assertIn("receipt", str(refused.exception).lower())


# ─── Recovery — the report cannot contain itself ────────────────────────────
class PostTestEvidenceDescendantTests(_ProvenanceCase):
    """A typed report may follow its tested tree; product changes may not."""

    def verify_then_commit_report(self, **kwargs) -> str:
        eng.action_terminal_verify(
            self.ACT, "talos", tested_sha=self.tested_sha)
        return self.commit_post_test_evidence(**kwargs)

    def test_matching_evidence_only_descendant_closes_and_fans_in_old_tree(self) -> None:
        evidence_head = self.verify_then_commit_report()
        self.assertNotEqual(evidence_head, self.tested_sha)

        result = self.close(verify=False)

        self.assertIn("workflow_complete", result)
        self.assertEqual(self.fm(self.SPEC).get("status"), "done")
        self.assertEqual(
            self._fannable_row()["tested_final_commit"], self.tested_sha,
            "post-test report commit replaced the tree that actually ran the tests")

    def test_product_change_above_tested_tree_still_refuses(self) -> None:
        self.verify_then_commit_report()
        import subprocess

        product = self.tmp / "vault" / "tools" / "untested.py"
        product.parent.mkdir(parents=True)
        product.write_text("raise RuntimeError('untested')\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", str(product.relative_to(self.tmp))], cwd=str(self.tmp),
            check=True)
        subprocess.run(
            ["git", "commit", "-qm", "unverified product change"], cwd=str(self.tmp),
            check=True)

        with self.assertRaises(SystemExit):
            self.close(verify=False)
        self.assertNotEqual(self.fm(self.SPEC).get("status"), "done")

    def test_report_naming_another_tested_tree_refuses(self) -> None:
        self.verify_then_commit_report(tested_commit="b" * 40)

        with self.assertRaises(SystemExit):
            self.close(verify=False)
        self.assertNotEqual(self.fm(self.SPEC).get("status"), "done")

    def test_non_evidence_dev_spec_edit_refuses(self) -> None:
        self.verify_then_commit_report(
            mutate_spec=lambda fm: fm.__setitem__("title", "scope changed after test"))

        with self.assertRaises(SystemExit):
            self.close(verify=False)
        self.assertNotEqual(self.fm(self.SPEC).get("status"), "done")


# ─── AC5 — retry and isolation ───────────────────────────────────────────────
class RetryAndIsolationTests(_ProvenanceCase):
    """Retry says what it did, and no fixture event reaches production."""

    def test_retry_is_explicit_and_idempotent(self) -> None:
        self.close()
        first = self.fm(self.SPEC)
        entries = sorted(p.name for p in self.files.glob("*.md"))

        result = self.close(verify=False)
        self.assertIn("converged", str(result).lower(),
                      f"retry returned {result!r}; an idempotent retry must say it "
                      "converged rather than refuse or repeat")

        second = self.fm(self.SPEC)
        self.assertEqual(first.get("completion_report_uid"),
                         second.get("completion_report_uid"),
                         "retry minted a second completion report")
        self.assertEqual(entries, sorted(p.name for p in self.files.glob("*.md")),
                         "retry created additional entries")
        self.assertTrue(self._fannable_row(), "retry left the cycle unfannable")

    def test_closure_events_land_in_the_sandbox_only(self) -> None:
        """Asserted positively, because a canary cannot tell an isolated
        emitter from a dead one."""
        self.close()
        emitted = self.sandboxed_events()
        self.assertTrue(emitted, "closure emitted no pipeline events at all")
        self.assertTrue(all(event.get("sandboxed") for event in emitted))
        self.assertIn("tropo.pipeline.closed", [event.get("type") for event in emitted])


if __name__ == "__main__":
    unittest.main(verbosity=2)
