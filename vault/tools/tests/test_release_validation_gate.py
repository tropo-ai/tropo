"""Isolated tests for the activation-bound full-validator release gate."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import temp_studio


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
FILES = ROOT / "vault" / "files"
TOOL_PATH = TOOLS / "tropo-release-validation-gate.py"

SPEC = importlib.util.spec_from_file_location("release_validation_gate", TOOL_PATH)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gate)


BASELINE_OUTPUT = """\
--- Existing Alpha Debt ---
[FAIL] 12 entries checked; 1 defect found
  [FAIL] vault/files/aaaa0001.md — existing path-specific defect
--- Existing Beta Debt ---
[ERROR] vault/files/bbbb0002.md — existing error
Summary: 2 passed, 2 failed, 4 warnings, 0 normalizable
"""


class ReleaseValidationGateFixture(unittest.TestCase):
    activation_uid = "a1c00001"
    run_uid = "b1c00001"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="release-validator-gate-")
        self.root = Path(self.temporary.name).resolve()
        self.files = self.root / "vault" / "files"
        self.runs = self.root / "vault" / "pipeline-runs"
        self.run_relative = (
            f"vault/pipeline-runs/release-pipeline-{self.run_uid}-2026-08-14"
        )
        self.run_folder = self.root / self.run_relative
        self.files.mkdir(parents=True)
        self.run_folder.mkdir(parents=True)
        self._write_binding()

        self.validator_output = self.root / "validator-output.txt"
        self.validator_exit = self.root / "validator-exit.txt"
        self.validator_script = self.root / "fixture-validator.py"
        self.validator_script.write_text(
            "from pathlib import Path\n"
            "root = Path(__file__).resolve().parent\n"
            "print((root / 'validator-output.txt').read_text(), end='')\n"
            "raise SystemExit(int((root / 'validator-exit.txt').read_text()))\n",
            encoding="utf-8",
        )
        self.validator_command = (sys.executable, str(self.validator_script))
        self.ac5_command = (
            sys.executable,
            "-c",
            "print('AC5 fan-in verifier passed')",
        )
        self._set_validator(BASELINE_OUTPUT, 1)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_entry(self, uid: str, body: dict) -> None:
        frontmatter = {"uid": uid, **body}
        (self.files / f"{uid}.md").write_text(
            "---\n"
            + yaml.safe_dump(frontmatter, sort_keys=False)
            + "---\n\n"
            + f"# {uid}\n",
            encoding="utf-8",
        )

    def _write_binding(self, *, run_activation: str | None = None) -> None:
        self._write_entry(
            self.activation_uid,
            {
                "type": "activation",
                "status": "active",
                "pipeline": gate.RELEASE_PIPELINE_UID,
                "pipeline_run_uid": self.run_uid,
            },
        )
        backref = run_activation or self.activation_uid
        self._write_entry(
            self.run_uid,
            {
                "type": "pipeline-run",
                "status": "active",
                "pipeline": gate.RELEASE_PIPELINE_UID,
                "activation": backref,
                "substrate_authored_by": backref,
                "run_folder": self.run_relative,
            },
        )

    def _set_validator(self, output: str, exit_code: int) -> None:
        self.validator_output.write_text(output, encoding="utf-8")
        self.validator_exit.write_text(str(exit_code), encoding="utf-8")

    def _capture(self) -> dict:
        return gate.capture_baseline(
            self.activation_uid,
            studio_root=self.root,
            ac5_command=self.ac5_command,
            validator_command=self.validator_command,
            now=lambda: "2026-08-14T00:00:00Z",
            commit="a" * 40,
        )

    def _compare(self) -> dict:
        return gate.compare_current(
            self.activation_uid,
            studio_root=self.root,
            validator_command=self.validator_command,
            now=lambda: "2026-08-14T01:00:00Z",
            commit="b" * 40,
        )


class CaptureContract(ReleaseValidationGateFixture):
    def test_known_failures_exit_one_capture_successfully_with_full_evidence(self) -> None:
        report = self._capture()

        self.assertEqual(report["validator"]["exit_code"], 1)
        self.assertEqual(report["validator"]["evidence"]["summary"]["failed"], 2)
        self.assertEqual(report["ac5"]["exit_code"], 0)
        self.assertEqual(report["activation_uid"], self.activation_uid)
        self.assertEqual(report["run_uid"], self.run_uid)
        self.assertEqual(report["run_folder"], self.run_relative)
        self.assertEqual(report["captured_commit"], "a" * 40)
        self.assertTrue((self.run_folder / gate.AC5_LOG).is_file())
        self.assertTrue((self.run_folder / gate.BASELINE_LOG).is_file())
        self.assertTrue((self.run_folder / gate.BASELINE_REPORT).is_file())

        stored = json.loads(
            (self.run_folder / gate.BASELINE_REPORT).read_text(encoding="utf-8")
        )
        finding = stored["validator"]["evidence"]["sections"][
            "Existing Alpha Debt"
        ]["specific_findings"][0]
        self.assertEqual(
            finding,
            "  [FAIL] vault/files/aaaa0001.md — existing path-specific defect",
            "finding identity must retain its UID/path instead of normalizing it away",
        )
        with mock.patch.object(gate, "capture_baseline", return_value=report):
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = gate.main(
                    ["capture", "--activation-uid", self.activation_uid]
                )
        self.assertEqual(
            exit_code,
            0,
            "a completed validator result with known failures must pass capture",
        )

    def test_an_existing_valid_baseline_is_reused_not_rebased(self) -> None:
        first = self._capture()
        baseline_bytes = (self.run_folder / gate.BASELINE_REPORT).read_bytes()
        self._set_validator(
            BASELINE_OUTPUT.replace("1 defect found", "99 defects found"), 1
        )

        second = self._capture()

        self.assertEqual(second, first)
        self.assertEqual(
            (self.run_folder / gate.BASELINE_REPORT).read_bytes(), baseline_bytes
        )

    def test_ac5_failure_refuses_before_validator_baseline_exists(self) -> None:
        with self.assertRaises(gate.GateRefusal):
            gate.capture_baseline(
                self.activation_uid,
                studio_root=self.root,
                ac5_command=(sys.executable, "-c", "raise SystemExit(1)"),
                validator_command=self.validator_command,
                commit="a" * 40,
            )
        self.assertFalse((self.run_folder / gate.BASELINE_REPORT).exists())
        self.assertFalse((self.run_folder / gate.BASELINE_LOG).exists())


class ComparisonContract(ReleaseValidationGateFixture):
    def test_unchanged_findings_pass(self) -> None:
        self._capture()
        report = self._compare()
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["regressions"], [])

    def test_aggregate_checked_text_can_change_without_reidentifying_debt(self) -> None:
        self._capture()
        self._set_validator(
            BASELINE_OUTPUT.replace("12 entries checked", "99 entries checked"),
            1,
        )
        report = self._compare()
        self.assertEqual(report["verdict"], "pass")

    def test_ansi_is_removed_but_finding_identity_is_not(self) -> None:
        ansi_output = BASELINE_OUTPUT.replace(
            "  [FAIL] vault/files/aaaa0001.md",
            "  \x1b[31m[FAIL]\x1b[0m vault/files/aaaa0001.md",
        )
        self._set_validator(ansi_output, 1)
        self._capture()
        self._set_validator(BASELINE_OUTPUT, 1)
        report = self._compare()
        self.assertEqual(report["verdict"], "pass")

    def test_fewer_findings_pass(self) -> None:
        self._capture()
        self._set_validator(
            """\
--- Existing Alpha Debt ---
[PASS] alpha clean
--- Existing Beta Debt ---
[ERROR] vault/files/bbbb0002.md — existing error
Summary: 3 passed, 1 failed, 4 warnings, 0 normalizable
""",
            1,
        )
        report = self._compare()
        self.assertEqual(report["verdict"], "pass")

    def test_added_specific_finding_fails(self) -> None:
        self._capture()
        self._set_validator(
            BASELINE_OUTPUT.replace(
                "[FAIL] 12 entries checked; 1 defect found",
                "[FAIL] 12 entries checked; 2 defects found",
            ).replace(
                "  [FAIL] vault/files/aaaa0001.md — existing path-specific defect",
                "  [FAIL] vault/files/aaaa0001.md — existing path-specific defect\n"
                "  [FAIL] vault/files/cccc0003.md — newly introduced defect",
            ).replace(
                "Summary: 2 passed, 2 failed",
                "Summary: 2 passed, 3 failed",
            ),
            1,
        )
        report = self._compare()
        self.assertEqual(report["verdict"], "fail")
        self.assertTrue(
            any(
                row["kind"] == "new-specific-finding"
                and "cccc0003" in row["signature"]
                for row in report["regressions"]
            )
        )
        with mock.patch.object(gate, "compare_current", return_value=report):
            with contextlib.redirect_stderr(io.StringIO()):
                exit_code = gate.main(
                    ["compare", "--activation-uid", self.activation_uid]
                )
        self.assertEqual(exit_code, 1)

    def test_increased_aggregate_count_and_new_section_fail(self) -> None:
        count_only = """\
--- Count Only ---
[ERROR] 20 entries checked; 2 violations found
Summary: 1 passed, 2 failed, 0 warnings, 0 normalizable
"""
        self._set_validator(count_only, 1)
        self._capture()
        self._set_validator(
            """\
--- Count Only ---
[ERROR] 20 entries checked; 3 violations found
--- Newly Failing Section ---
[FAIL] new generic failure without a path
Summary: 1 passed, 4 failed, 0 warnings, 0 normalizable
""",
            1,
        )
        report = self._compare()
        kinds = {row["kind"] for row in report["regressions"]}
        self.assertEqual(report["verdict"], "fail")
        self.assertIn("section-reported-count-increased", kinds)
        self.assertIn("new-failing-section", kinds)

    def test_operational_validator_error_fails_and_preserves_evidence(self) -> None:
        self._capture()
        self._set_validator("validator could not start\n", 2)
        report = self._compare()
        self.assertEqual(report["verdict"], "operational-error")
        self.assertTrue((self.run_folder / gate.CURRENT_LOG).is_file())
        self.assertTrue((self.run_folder / gate.COMPARISON_REPORT).is_file())
        self.assertEqual(
            report["regressions"][0]["kind"], "validator-operational-error"
        )
        with mock.patch.object(gate, "compare_current", return_value=report):
            with contextlib.redirect_stderr(io.StringIO()):
                exit_code = gate.main(
                    ["compare", "--activation-uid", self.activation_uid]
                )
        self.assertEqual(exit_code, 2)


class BindingAndIsolation(ReleaseValidationGateFixture):
    def test_missing_or_wrong_activation_run_binding_refuses_without_writes(self) -> None:
        with self.assertRaises(gate.GateRefusal):
            gate.capture_baseline(
                "deadbeef",
                studio_root=self.root,
                ac5_command=self.ac5_command,
                validator_command=self.validator_command,
                commit="a" * 40,
            )
        self._write_binding(run_activation="bad00001")
        with self.assertRaises(gate.GateRefusal):
            self._capture()
        self.assertEqual(list(self.run_folder.iterdir()), [])

    def test_production_studio_fingerprint_is_unchanged(self) -> None:
        before = temp_studio.production_fingerprint()
        self._capture()
        self._compare()
        after = temp_studio.production_fingerprint()
        self.assertEqual(temp_studio.diff_fingerprints(before, after), {})


class ProductionDeclarations(unittest.TestCase):
    def test_release_steps_call_the_production_tool_with_activation_binding(self) -> None:
        expected = {
            "f9365ede": "capture",
            "4262d5fa": "compare",
        }
        for uid, mode in expected.items():
            with self.subTest(uid=uid):
                frontmatter = yaml.safe_load(
                    (FILES / f"{uid}.md").read_text(encoding="utf-8").split(
                        "---", 2
                    )[1]
                )
                command = frontmatter["verification_command"]
                self.assertIn(
                    "vault/tools/tropo-release-validation-gate.py", command
                )
                self.assertIn(f" {mode} ", command)
                self.assertIn("--activation-uid {activation}", command)
                self.assertNotIn("updates/", command)
                self.assertNotIn("releases/", command)

    def test_verify_dependency_on_assemble_terminal_is_preserved(self) -> None:
        frontmatter = yaml.safe_load(
            (FILES / "4262d5fa.md").read_text(encoding="utf-8").split("---", 2)[1]
        )
        self.assertEqual(frontmatter["depends_on_steps"], ["8654900a"])

    def test_capture_tool_executes_the_existing_ac5_verifier(self) -> None:
        self.assertEqual(
            gate.AC5_COMMAND,
            (
                "python3",
                "-m",
                "unittest",
                "vault.tools.tests.test_two_pipeline_split_0a0a6777."
                "RemainingAcceptanceCriteria."
                "test_ac05_fan_in_row_and_reservation_gate",
            ),
        )
        self.assertEqual(
            gate.VALIDATOR_COMMAND,
            ("python3", "vault/tools/tropo-validate.py", "--release"),
        )


if __name__ == "__main__":
    unittest.main()
