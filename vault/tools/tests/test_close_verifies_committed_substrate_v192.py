"""AC5 (b1e78abb, v1.92): a dev-spec at `status: done` whose committed_
substrate names an unresolvable target is a validator finding naming EVERY
unresolved target, not the first.

29506520 shipped `status: done` with four of its twelve declared
committed_substrate targets absent from disk. Nothing verified this —
grepped every file in vault/tools/ and vault/tools/lib/ for a
committed_substrate read paired with an existence check: zero hits. This
file is fixture-only (per the spec's own §Acceptance: "AC5's pytest
evidence is fixture-only" — the live-vault run against 29506520 is release-
verification evidence, recorded on the run journal, not asserted here).

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_close_verifies_committed_substrate_v192
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import importlib.util

_spec = importlib.util.spec_from_file_location("validator_ac5", TOOLS / "tropo-validate.py")
validator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validator)


class CommittedSubstrateResolvesAtDone(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac5-substrate-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.files = self.tmp / "vault" / "files"
        self.files.mkdir(parents=True)
        self.index_path = self.tmp / "vault" / "00-index.jsonl"

    def _write_spec(self, uid: str, status: str, capsule_version, committed_substrate) -> None:
        import json as _json

        lines = [
            f"uid: {uid}",
            "type: dev-spec",
            f"status: {status}",
            f"capsule_version: {capsule_version!r}" if capsule_version is not None else "",
            "committed_substrate:",
        ]
        lines = [l for l in lines if l]
        for entry in committed_substrate:
            if isinstance(entry, dict):
                lines.append(f"  - target: {entry['target']}")
                lines.append(f"    change_class: {entry.get('change_class', 'NEW')}")
                lines.append(f"    description: {entry.get('description', 'x')}")
            else:
                lines.append(f"  - {entry}")
        (self.files / f"{uid}.md").write_text(
            "---\n" + "\n".join(lines) + "\n---\n\n# " + uid + "\n", encoding="utf-8"
        )

    def _write_real_path(self, relative: str, content: str = "x") -> None:
        p = self.tmp / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def _write_index(self, uids: list) -> None:
        import json as _json

        self.index_path.write_text(
            "\n".join(_json.dumps({"uid": u, "type": "tool"}) for u in uids) + "\n",
            encoding="utf-8",
        )

    def test_capsule_1_5_plus_done_with_two_absent_paths_yields_one_finding_naming_both(self) -> None:
        self._write_index([])
        self._write_spec(
            "aa000001", "done", "1.9",
            [
                "vault/tools/nonexistent_one.py",
                "vault/tools/nonexistent_two.py",
            ],
        )
        findings, checked, errors = validator.check_committed_substrate_resolves_at_done(self.tmp)
        self.assertEqual(checked, 1)
        self.assertEqual(errors, 1)
        matching = [f for f in findings if "aa000001" in f]
        self.assertEqual(len(matching), 1, "expected exactly one finding for this spec, not one per target")
        self.assertTrue(matching[0].startswith("[ERROR]"))
        self.assertIn("nonexistent_one.py", matching[0])
        self.assertIn("nonexistent_two.py", matching[0])

    def test_pre_1_5_spec_with_the_same_absence_yields_the_named_debt_class_not_an_error(self) -> None:
        self._write_index([])
        self._write_spec(
            "aa000002", "done", "1.2",
            ["vault/tools/nonexistent_three.py"],
        )
        findings, checked, errors = validator.check_committed_substrate_resolves_at_done(self.tmp)
        self.assertEqual(checked, 1)
        self.assertEqual(errors, 0, "pre-1.5 must not count toward the ERROR tally")
        matching = [f for f in findings if "aa000002" in f]
        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0].startswith("[WARN]"))
        self.assertIn("debt-baseline", matching[0])

    def test_locked_spec_with_absent_targets_yields_nothing(self) -> None:
        self._write_index([])
        self._write_spec(
            "aa000003", "locked", "1.9",
            ["vault/tools/nonexistent_four.py"],
        )
        findings, checked, errors = validator.check_committed_substrate_resolves_at_done(self.tmp)
        self.assertEqual(checked, 0, "a locked spec must not even be counted -- only done is in scope")
        self.assertEqual(errors, 0)
        self.assertEqual([f for f in findings if "aa000003" in f], [])

    def test_a_planted_identifier_target_at_done_yields_the_named_warn(self) -> None:
        self._write_index([])
        self._write_spec(
            "aa000004", "done", "1.9",
            ["gardener-body-judge"],  # the capsule's own worked example of class 3
        )
        findings, checked, errors = validator.check_committed_substrate_resolves_at_done(self.tmp)
        self.assertEqual(checked, 1)
        self.assertEqual(errors, 0, "a planned identifier is never an ERROR")
        matching = [f for f in findings if "aa000004" in f]
        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0].startswith("[WARN]"))
        self.assertIn("planned identifier", matching[0])
        self.assertIn("gardener-body-judge", matching[0])

    def test_a_resolvable_uid_target_and_a_resolvable_path_target_produce_no_finding(self) -> None:
        """Control: the check must not false-positive on legitimately
        resolvable substrate, or every test above proves nothing about
        selectivity."""
        self._write_index(["deadbeef"])
        self._write_real_path("vault/tools/real_file.py")
        self._write_spec(
            "aa000005", "done", "1.9",
            ["deadbeef", "vault/tools/real_file.py"],
        )
        findings, checked, errors = validator.check_committed_substrate_resolves_at_done(self.tmp)
        self.assertEqual(checked, 1)
        self.assertEqual(errors, 0)
        self.assertEqual([f for f in findings if "aa000005" in f], [])

    def test_legacy_bare_string_committed_substrate_shape_is_supported(self) -> None:
        """29506520's own shape (list of bare path strings, not objects with
        a target key) — the capsule's documented pre-v1.8 compatibility
        form. If this test fails, the known-positive scenario the spec
        names cannot be represented at all."""
        self._write_index([])
        self._write_spec(
            "aa000006", "done", "1.9",
            ["vault/tools/nonexistent_five.py"],  # bare string, not {target: ...}
        )
        findings, checked, errors = validator.check_committed_substrate_resolves_at_done(self.tmp)
        self.assertEqual(errors, 1)
        self.assertTrue(any("aa000006" in f and "nonexistent_five.py" in f for f in findings))

    def test_a_directory_target_with_trailing_slash_resolves_as_a_directory(self) -> None:
        (self.tmp / "vault" / "tools" / "lib").mkdir(parents=True)
        self._write_index([])
        self._write_spec("aa000007", "done", "1.9", ["vault/tools/lib/"])
        findings, checked, errors = validator.check_committed_substrate_resolves_at_done(self.tmp)
        self.assertEqual(errors, 0)
        self.assertEqual([f for f in findings if "aa000007" in f], [])

    def test_a_missing_vault_files_directory_hard_fails_not_silent_zero(self) -> None:
        """Metis G112's hardening finding on AC5's own non-author
        verification: a wrong --vault-path returned zero findings, same
        false-green-on-absent-subject class as the AC1 chain test's index
        fix. Refuses now instead."""
        with self.assertRaises(RuntimeError):
            validator.check_committed_substrate_resolves_at_done(self.tmp / "nowhere")

    def test_mutation_removing_a_real_file_turns_this_red(self) -> None:
        """Teeth, run rather than asserted: prove the check reacts to the
        filesystem, not to a cached assumption."""
        self._write_index([])
        self._write_real_path("vault/tools/will_be_removed.py")
        self._write_spec("aa000008", "done", "1.9", ["vault/tools/will_be_removed.py"])
        _findings, _checked, errors_before = validator.check_committed_substrate_resolves_at_done(self.tmp)
        self.assertEqual(errors_before, 0)

        (self.tmp / "vault" / "tools" / "will_be_removed.py").unlink()
        findings_after, _checked2, errors_after = validator.check_committed_substrate_resolves_at_done(self.tmp)
        self.assertEqual(errors_after, 1)
        self.assertTrue(any("aa000008" in f for f in findings_after))


class CommittedSubstrateDebtBaseline(unittest.TestCase):
    """b1e78abb AC5 follow-on, Metis G112's baseline ruling (2026-08-24):
    persist the measured ERROR-tier set into a curated
    committed-substrate-debt-baseline.json on the enum-debt pattern —
    known signatures WARN, a new or changed signature still ERRORs,
    shrink-only. Mirrors test_enum_debt_baseline's shape for the sibling
    baseline this one is modeled on."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac5-baseline-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.files = self.tmp / "vault" / "files"
        self.files.mkdir(parents=True)
        self.index_path = self.tmp / "vault" / "00-index.jsonl"
        self.index_path.write_text("", encoding="utf-8")

    def _write_spec(self, uid: str, status: str, capsule_version, committed_substrate) -> None:
        lines = [
            f"uid: {uid}",
            "type: dev-spec",
            f"status: {status}",
            f"capsule_version: {capsule_version!r}" if capsule_version is not None else "",
            "committed_substrate:",
        ]
        lines = [l for l in lines if l]
        for entry in committed_substrate:
            lines.append(f"  - {entry}")
        (self.files / f"{uid}.md").write_text(
            "---\n" + "\n".join(lines) + "\n---\n\n# " + uid + "\n", encoding="utf-8"
        )

    def test_load_absent_baseline_is_legal_and_excuses_nothing(self) -> None:
        baseline = validator.load_committed_substrate_debt_baseline(self.tmp)
        self.assertFalse(baseline["present"])
        self.assertEqual(baseline["signatures"], {})

    def test_load_malformed_baseline_raises_rather_than_silently_excusing(self) -> None:
        path = self.tmp / validator.COMMITTED_SUBSTRATE_DEBT_BASELINE_RELATIVE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"schema_version": 1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            validator.load_committed_substrate_debt_baseline(self.tmp)

    def test_a_known_signature_warns_instead_of_erroring(self) -> None:
        self._write_spec("bb000001", "done", "1.9", ["vault/tools/nonexistent_a.py"])
        baseline = {
            "present": True,
            "signatures": {
                validator._committed_substrate_debt_signature(
                    "bb000001", ["vault/tools/nonexistent_a.py"]
                ): {}
            },
            "header": {},
        }
        findings, checked, errors = validator.check_committed_substrate_resolves_at_done(
            self.tmp, baseline=baseline
        )
        self.assertEqual(checked, 1)
        self.assertEqual(errors, 0, "a baselined signature must not count toward the ERROR tally")
        matching = [f for f in findings if "bb000001" in f]
        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0].startswith("[WARN]"))
        self.assertIn("debt-baseline", matching[0])

    def test_an_unbaselined_spec_still_errors_with_a_baseline_present(self) -> None:
        """Control: a baseline excuses only the signatures it names, not
        every capsule_version >= 1.5 finding once any baseline exists."""
        self._write_spec("bb000002", "done", "1.9", ["vault/tools/nonexistent_b.py"])
        baseline = {
            "present": True,
            "signatures": {"some-other-uid|some-other-target": {}},
            "header": {},
        }
        findings, checked, errors = validator.check_committed_substrate_resolves_at_done(
            self.tmp, baseline=baseline
        )
        self.assertEqual(errors, 1)
        self.assertTrue(any(f.startswith("[ERROR]") and "bb000002" in f for f in findings))

    def test_a_partial_cure_of_a_baselined_spec_still_errors(self) -> None:
        """Metis's ruling: fixing any record shrinks the frozen list — it
        does not stay WARN over whatever remains broken. The signature is
        keyed on the FULL unresolved set, so removing one of two targets
        produces a signature the baseline (captured against the original
        two-target set) does not contain."""
        baseline = {
            "present": True,
            "signatures": {
                validator._committed_substrate_debt_signature(
                    "bb000003",
                    ["vault/tools/nonexistent_c1.py", "vault/tools/nonexistent_c2.py"],
                ): {}
            },
            "header": {},
        }
        # Only one of the two original targets is still unresolved.
        self._write_spec("bb000003", "done", "1.9", ["vault/tools/nonexistent_c1.py"])
        findings, _checked, errors = validator.check_committed_substrate_resolves_at_done(
            self.tmp, baseline=baseline
        )
        self.assertEqual(errors, 1, "a changed target set is a new signature, not a shrink")
        self.assertTrue(any(f.startswith("[ERROR]") and "bb000003" in f for f in findings))

    def test_write_first_capture_writes_the_current_error_tier_set(self) -> None:
        self._write_spec("bb000004", "done", "1.9", ["vault/tools/nonexistent_d.py"])
        messages, code = validator.write_committed_substrate_debt_baseline(self.tmp)
        self.assertEqual(code, 0)
        self.assertTrue(any(m.startswith("[PASS]") for m in messages))
        baseline = validator.load_committed_substrate_debt_baseline(self.tmp)
        self.assertTrue(baseline["present"])
        self.assertEqual(len(baseline["signatures"]), 1)

    def test_write_shrink_is_legal(self) -> None:
        self._write_spec("bb000005", "done", "1.9", ["vault/tools/nonexistent_e.py"])
        self._write_spec("bb000006", "done", "1.9", ["vault/tools/nonexistent_f.py"])
        messages, code = validator.write_committed_substrate_debt_baseline(self.tmp)
        self.assertEqual(code, 0)
        first = validator.load_committed_substrate_debt_baseline(self.tmp)
        self.assertEqual(len(first["signatures"]), 2)

        # bb000006 is cured (no longer done); only bb000005's signature
        # survives in the live census.
        (self.files / "bb000006.md").unlink()
        messages, code = validator.write_committed_substrate_debt_baseline(self.tmp)
        self.assertEqual(code, 0)
        second = validator.load_committed_substrate_debt_baseline(self.tmp)
        self.assertEqual(len(second["signatures"]), 1)

    def test_write_growth_refuses_and_leaves_the_file_unchanged(self) -> None:
        self._write_spec("bb000007", "done", "1.9", ["vault/tools/nonexistent_g.py"])
        validator.write_committed_substrate_debt_baseline(self.tmp)
        path = self.tmp / validator.COMMITTED_SUBSTRATE_DEBT_BASELINE_RELATIVE_PATH
        before = path.read_text(encoding="utf-8")

        # A genuinely new ERROR-tier finding appears — growth, not shrink.
        self._write_spec("bb000008", "done", "1.9", ["vault/tools/nonexistent_h.py"])
        messages, code = validator.write_committed_substrate_debt_baseline(self.tmp)
        self.assertEqual(code, 1)
        self.assertTrue(any(m.startswith("[FAIL]") for m in messages))
        after = path.read_text(encoding="utf-8")
        self.assertEqual(before, after, "a refused write must not touch the baseline file")


if __name__ == "__main__":
    unittest.main()
