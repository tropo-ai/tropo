#!/usr/bin/env python3
"""Currently buildable synthetic AC gauntlets for Gardener Pruning."""
from __future__ import annotations

import copy
import hashlib
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import gardener_precision_fixtures as precision  # noqa: E402
from lib import pruning_contract  # noqa: E402
from lib.normalized_body_hash import (  # noqa: E402
    normalized_body_sha256,
    raw_body_sha256,
)
from vault.tools.tests.test_gardener_verdict import IsolatedVault  # noqa: E402


MANIFEST = (
    ROOT
    / "vault"
    / "tools"
    / "fixtures"
    / "gardener-pruning"
    / "manifest.json"
)


class GardenerPruningSyntheticACGauntlet(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture_set = precision.load_fixture_set(
            MANIFEST,
            require_frozen=False,
        )

    def _case(self, case_id: str) -> precision.FixtureCase:
        return next(case for case in self.fixture_set.cases if case.case_id == case_id)

    def test_ac1_true_prune_scratch_writer_preserves_body_t1_t2(self) -> None:
        source = self._case("spent-01-superseded")
        scratch = IsolatedVault(body=source.body)
        self.addCleanup(scratch.close)
        evidence = source.record["expected"]["evidence"]
        before_body = scratch.body_bytes()
        before_t1 = raw_body_sha256(scratch.target)
        before_t2 = normalized_body_sha256(scratch.target)

        result = scratch.stamp(
            scratch.request(
                evidence=evidence,
                verdict=source.record["expected"]["verdict"],
            )
        )

        self.assertTrue(result.source_changed)
        self.assertEqual(scratch.body_bytes(), before_body)
        self.assertEqual(raw_body_sha256(scratch.target), before_t1)
        self.assertEqual(normalized_body_sha256(scratch.target), before_t2)
        pruning = scratch.pruning()
        self.assertEqual(pruning["verdict"], "superseded")
        self.assertEqual(pruning["evidence_span"], evidence)
        locator = pruning["evidence_locator"]
        self.assertEqual(
            before_body[locator["start_byte"] : locator["end_byte"]].decode("utf-8"),
            evidence,
        )

    def test_ac2_locked_mock_precision_floor(self) -> None:
        score = precision.score_proposals(
            self.fixture_set,
            precision.gold_proposals(self.fixture_set),
        )
        self.assertTrue(score["passed"])
        self.assertEqual(score["metrics"]["live_false_prunes"], 0)
        self.assertEqual(score["metrics"]["live_precision"], 1.0)
        self.assertEqual(score["metrics"]["spent_recall"], 1.0)

    def test_ac3_evidenceless_writer_and_validator_refuse(self) -> None:
        source = self._case("spent-03-finished")
        scratch = IsolatedVault(body=source.body)
        self.addCleanup(scratch.close)
        request = scratch.request(
            evidence=source.record["expected"]["evidence"],
            verdict="finished",
        )
        with self.assertRaisesRegex(
            pruning_contract.PruningContractError,
            "evidence",
        ):
            scratch.stamp(replace(request, evidence_span=""))

        scratch.stamp(request)
        block = copy.deepcopy(scratch.pruning())
        block.pop("evidence_span")
        evaluated = pruning_contract.evaluate_pruning_contract(
            uid=request.uid,
            path=f"vault/files/{request.uid}.md",
            block=block,
            body=scratch.body_bytes(),
            current_t1=raw_body_sha256(scratch.target),
            current_t2=normalized_body_sha256(scratch.target),
            current_records=[],
        )
        self.assertEqual(evaluated.severity, "FAIL")
        self.assertEqual(evaluated.findings[0].code, "PRUNING_SHAPE")

    def test_ac5_nav_maintenance_is_t2_neutral_and_prose_is_not(self) -> None:
        source = self._case("live-01-published-active")
        with tempfile.TemporaryDirectory(prefix="gardener_ac5_") as temporary:
            path = Path(temporary) / source.path.name
            shutil.copy2(source.path, path)
            baseline = normalized_body_sha256(path)
            snapshot = pruning_contract.read_markdown_snapshot(path)
            nav = (
                b"<!-- nav-block:start -->generated fixture nav"
                b"<!-- nav-block:end -->"
            )
            path.write_bytes(
                snapshot.raw[: -len(snapshot.body)]
                + snapshot.body[:-1]
                + nav
                + b"\n"
            )
            self.assertEqual(normalized_body_sha256(path), baseline)
            path.write_bytes(path.read_bytes() + b"Real synthetic prose edit.\n")
            self.assertNotEqual(normalized_body_sha256(path), baseline)

    def test_ac7_viewer_free_body_local_mock_boundaries(self) -> None:
        before = {
            case.case_id: hashlib.sha256(case.path.read_bytes()).hexdigest()
            for case in self.fixture_set.cases
        }
        proposals = precision.gold_proposals(self.fixture_set)
        nav_case = self._case("adv-01-nav-evidence")
        nav_bait = "This synthetic page is superseded by a hidden replacement."
        nav_start = nav_case.body.index(nav_bait.encode("utf-8"))
        nav = next(p for p in proposals if p["case_id"] == nav_case.case_id)
        nav.update(
            {
                "action": "stamp",
                "verdict": "superseded",
                "evidence_span": nav_bait,
                "start_byte": nav_start,
                "end_byte": nav_start + len(nav_bait.encode("utf-8")),
            }
        )
        score = precision.score_proposals(self.fixture_set, proposals)
        nav_detail = next(
            detail for detail in score["cases"] if detail["case_id"] == nav_case.case_id
        )
        self.assertFalse(nav_detail["evidence_valid"])
        self.assertFalse(score["passed"])

        gold = precision.score_proposals(
            self.fixture_set,
            precision.gold_proposals(self.fixture_set),
        )
        cross_segment = next(
            detail
            for detail in gold["cases"]
            if detail["case_id"] == "adv-02-cross-segment-bait"
        )
        self.assertEqual(cross_segment["actual_action"], "refuse")
        self.assertTrue(cross_segment["action_match"])
        self.assertTrue(
            all("decay" not in case.record for case in self.fixture_set.cases)
        )
        after = {
            case.case_id: hashlib.sha256(case.path.read_bytes()).hexdigest()
            for case in self.fixture_set.cases
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
