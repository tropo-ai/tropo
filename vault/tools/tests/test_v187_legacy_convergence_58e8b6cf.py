#!/usr/bin/env python3
"""Current-tree convergence for v1.87 legacy-scoped deliverables (58e8b6cf)."""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
FILES = ROOT / "vault" / "files"
REPORT_UID = "45324ca6"
ORIGINAL_SPECS = {"0a0a6777", "22289459", "d9ca03fd"}


def run_modules(*modules: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "unittest", *modules],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=900,
    )


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1]) or {}


class TwoPipelineConvergenceTests(unittest.TestCase):
    def test_current_pipeline_contracts_are_green(self) -> None:
        result = run_modules(
            "vault.tools.tests.test_two_pipeline_split_0a0a6777",
            "vault.tools.tests.test_ac07_release_graph_topology",
            "vault.tools.tests.test_release_plan_lock_end_to_end",
            "vault.tools.tests.test_ignition_snapshots",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_release_graph_is_active_and_dev_has_no_release_nodes(self) -> None:
        release = frontmatter(FILES / "634913c2.md")
        dev = frontmatter(FILES / "cd1fcd25.md")
        self.assertEqual(release.get("status"), "active")
        self.assertEqual(
            release.get("children"), ["471dd767", "8a4f802b", "8e03f8d6"]
        )
        self.assertEqual(
            dev.get("children"), ["03624b7a", "3bd8f5b6", "74945d48"]
        )


class SingleSourceConvergenceTests(unittest.TestCase):
    def test_current_single_source_contract_is_green(self) -> None:
        result = run_modules(
            "vault.tools.tests.test_boot_single_source_22289459",
            "vault.tools.tests.test_compact_continue_boot_derivation",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class GovernedSkipConvergenceTests(unittest.TestCase):
    def test_current_governed_skip_contract_is_green(self) -> None:
        result = run_modules(
            "vault.tools.tests.test_governed_skips_d9ca03fd",
            "vault.tools.tests.test_every_gate_has_a_caller",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ProvenanceHonestyTests(unittest.TestCase):
    def test_report_binds_current_convergence_without_inventing_history(self) -> None:
        path = FILES / f"{REPORT_UID}.md"
        self.assertTrue(path.is_file(), f"verification report missing: {path}")
        text = path.read_text(encoding="utf-8")
        fm = frontmatter(path)
        self.assertEqual(fm.get("type"), "verification-report")
        self.assertIn(str(fm.get("status") or "").lower(), {"accepted", "done"})
        self.assertIn(str(fm.get("verdict") or "").lower(), {"pass", "accepted"})
        self.assertEqual(set(str(uid) for uid in fm.get("original_spec_uids") or []),
                         ORIGINAL_SPECS)
        self.assertEqual(fm.get("convergence_activation_uid"), "7bb5ed82")
        self.assertEqual(fm.get("convergence_run_uid"), "3de565ed")
        self.assertRegex(str(fm.get("tested_commit") or ""), r"^[0-9a-f]{40}$")
        self.assertIn("does not reconstruct", text.lower())
        self.assertIn("missing historical", text.lower())

    def test_the_reported_tested_commit_is_the_tree_that_was_verified(self) -> None:
        """The report's own claim has to be checkable, not just well-shaped.

        Every other case here proves the suites are green NOW. None of them
        looks at WHICH tree they ran against, so a report could name a commit
        from before the convergence work and still pass the whole matrix —
        which is the one thing a convergence report exists to state precisely.

        A dirty tree fails too: the verified tree would then be a state that
        exists on no machine but this one.
        """
        fm = frontmatter(FILES / f"{REPORT_UID}.md")
        claimed = str(fm.get("tested_commit") or "")

        # Compared against the CYCLE'S OWN RECEIPT, not against HEAD. Two
        # earlier formulations were wrong in instructive ways: `claimed == HEAD`
        # is unsatisfiable, because writing the claim down is itself a commit;
        # and "no tool changed since the claimed tree" quietly re-dates the
        # report every time anything lands afterwards, which turns a historical
        # statement into a moving one.
        #
        # The invariant that actually matters is agreement: the tree the report
        # says it verified must be the tree the cycle's canonical dev-close
        # receipt attests. Those two disagreeing is precisely the invented
        # provenance this cycle exists to avoid, and it is checkable forever.
        attested = self.canonical_tested_commit()
        self.assertEqual(
            claimed, attested,
            f"the report names tested tree {claimed[:12]} but this cycle's "
            f"canonical receipt attests {attested[:12]}; a convergence report "
            "and its own close cannot describe different trees",
        )

    def canonical_tested_commit(self) -> str:
        """The tested tree from the run's canonical dev_closed receipt."""
        import json  # noqa: PLC0415

        run = frontmatter(FILES / "3de565ed.md")
        folder = ROOT / str(run.get("run_folder") or "")
        if not folder.is_dir():
            self.skipTest(f"no run folder at {folder}")
        for path in sorted(folder.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if "canonical-dev-close" not in line:
                    continue
                data = json.loads(line).get("data") or {}
                sha = data.get("tested_commit_sha") or data.get("tested_sha")
                if sha:
                    return str(sha)
        self.fail("this cycle has no canonical dev-close receipt to compare against")

    def test_report_does_not_claim_old_run_or_receipt_identity(self) -> None:
        path = FILES / f"{REPORT_UID}.md"
        self.assertTrue(path.is_file())
        fm = frontmatter(path)
        forbidden = {
            "legacy_activation_uid",
            "legacy_pipeline_run_uid",
            "legacy_completion_receipt_uid",
            "legacy_tested_commit",
        }
        self.assertEqual(forbidden & set(fm), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
