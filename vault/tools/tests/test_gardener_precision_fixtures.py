#!/usr/bin/env python3
"""Focused plants for frozen synthetic Gardener precision fixtures."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import gardener_precision_fixtures as fixtures  # noqa: E402
from lib import pruning_contract  # noqa: E402
from lib.normalized_body_hash import normalized_body_sha256  # noqa: E402


MANIFEST = (
    ROOT
    / "vault"
    / "tools"
    / "fixtures"
    / "gardener-pruning"
    / "manifest.json"
)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


class GardenerPrecisionFixtureTests(unittest.TestCase):
    def _load(self) -> fixtures.FixtureSet:
        return fixtures.load_fixture_set(
            MANIFEST,
            require_frozen=False,
        )

    def _scratch(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory(prefix="gardener_precision_")
        root = Path(temporary.name) / "gardener-pruning"
        shutil.copytree(MANIFEST.parent, root)
        return temporary, root / "manifest.json"

    @staticmethod
    def _read_manifest(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_manifest(path: Path, manifest: dict) -> None:
        path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=True) + "\n",
            encoding="utf-8",
        )

    def test_locked_case_balance_identity_and_gold_evidence(self) -> None:
        fixture_set = self._load()
        self.assertEqual(len(fixture_set.cases), 18)
        self.assertEqual(
            {
                class_name: sum(
                    case.record["class"] == class_name
                    for case in fixture_set.cases
                )
                for class_name in ("live", "spent", "adversarial")
            },
            {"live": 8, "spent": 6, "adversarial": 4},
        )
        ids = [case.case_id for case in fixture_set.cases]
        uids = [case.record["uid"] for case in fixture_set.cases]
        paths = [case.record["path"] for case in fixture_set.cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(uids), len(set(uids)))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all(uid.startswith("ff00") for uid in uids))
        self.assertTrue(all(path.startswith("bodies/") for path in paths))
        self.assertEqual(
            [
                case.record["expected"]["verdict"]
                for case in fixture_set.cases
                if case.record["class"] == "spent"
            ].count("superseded"),
            2,
        )
        self.assertEqual(
            [
                case.record["expected"]["verdict"]
                for case in fixture_set.cases
                if case.record["class"] == "spent"
            ].count("finished"),
            2,
        )
        self.assertEqual(
            [
                case.record["expected"]["verdict"]
                for case in fixture_set.cases
                if case.record["class"] == "spent"
            ].count("abandoned"),
            2,
        )

    def test_freeze_hashes_are_stable_and_body_corruption_is_detected(self) -> None:
        temporary, scratch_manifest = self._scratch()
        self.addCleanup(temporary.cleanup)
        loaded = fixtures.load_fixture_set(
            scratch_manifest,
            require_frozen=False,
        )
        if loaded.manifest["freeze"]["status"] == "unfrozen":
            first = fixtures.freeze_manifest(
                scratch_manifest,
                base_content_commit="a" * 40,
                frozen_at="2026-07-17",
            )
            loaded = fixtures.load_fixture_set(scratch_manifest)
        else:
            first = fixtures.verify_fixture_hashes(loaded)
        second = fixtures.verify_fixture_hashes(loaded)
        self.assertEqual(first, second)
        self.assertRegex(first["composite_sha256"], r"^[0-9a-f]{64}$")

        loaded.cases[0].path.write_text(
            loaded.cases[0].path.read_text(encoding="utf-8") + "\ncorruption\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            fixtures.FixtureContractError,
            "hash mismatch",
        ):
            fixtures.load_fixture_set(scratch_manifest)

    def test_duplicate_case_uid_and_path_refuse(self) -> None:
        for field in ("id", "uid", "path"):
            with self.subTest(field=field):
                temporary, scratch_manifest = self._scratch()
                self.addCleanup(temporary.cleanup)
                manifest = self._read_manifest(scratch_manifest)
                manifest["cases"][1][field] = manifest["cases"][0][field]
                self._write_manifest(scratch_manifest, manifest)
                with self.assertRaises(fixtures.FixtureContractError):
                    fixtures.load_fixture_set(
                        scratch_manifest,
                        require_frozen=False,
                        verify_hashes=False,
                    )

    def test_path_escape_absolute_and_symlink_refuse(self) -> None:
        for path_value in ("../escape.md", "/tmp/escape.md"):
            with self.subTest(path=path_value):
                temporary, scratch_manifest = self._scratch()
                self.addCleanup(temporary.cleanup)
                manifest = self._read_manifest(scratch_manifest)
                manifest["cases"][0]["path"] = path_value
                self._write_manifest(scratch_manifest, manifest)
                with self.assertRaisesRegex(
                    fixtures.FixtureContractError,
                    "canonical relative",
                ):
                    fixtures.load_fixture_set(
                        scratch_manifest,
                        require_frozen=False,
                        verify_hashes=False,
                    )

        temporary, scratch_manifest = self._scratch()
        self.addCleanup(temporary.cleanup)
        manifest = self._read_manifest(scratch_manifest)
        original = scratch_manifest.parent / manifest["cases"][0]["path"]
        alias = scratch_manifest.parent / "bodies" / "alias.md"
        alias.symlink_to(original.name)
        manifest["cases"][0]["path"] = "bodies/alias.md"
        self._write_manifest(scratch_manifest, manifest)
        with self.assertRaisesRegex(fixtures.FixtureContractError, "symlink"):
            fixtures.load_fixture_set(
                scratch_manifest,
                require_frozen=False,
                verify_hashes=False,
            )

    def test_gold_mock_scorecard_meets_all_locked_thresholds(self) -> None:
        fixture_set = self._load()
        score = fixtures.score_proposals(
            fixture_set,
            fixtures.gold_proposals(fixture_set),
        )
        self.assertTrue(score["passed"])
        self.assertEqual(score["counts"], {"live": 8, "spent": 6, "adversarial": 4})
        self.assertEqual(
            score["metrics"],
            {
                "live_false_prunes": 0,
                "live_precision": 1.0,
                "spent_correct": 6,
                "spent_recall": 1.0,
                "adversarial_illegal_stamps": 0,
                "adversarial_must_refuse_total": 2,
                "adversarial_refused": 2,
                "adversarial_refusal_rate": 1.0,
                "exact_action_matches": 18,
            },
        )

    def test_false_prune_missed_spent_and_adversarial_stamp_fail(self) -> None:
        fixture_set = self._load()
        base = fixtures.gold_proposals(fixture_set)
        cases = (
            ("live-01-published-active", "stamp"),
            ("spent-01-superseded", "no_verdict"),
            ("adv-02-cross-segment-bait", "stamp"),
        )
        for case_id, action in cases:
            with self.subTest(case_id=case_id):
                proposals = copy.deepcopy(base)
                proposal = next(p for p in proposals if p["case_id"] == case_id)
                case = next(c for c in fixture_set.cases if c.case_id == case_id)
                if action == "stamp":
                    evidence = case.body.decode("utf-8").splitlines()[-1]
                    encoded = evidence.encode("utf-8")
                    start = case.body.index(encoded)
                    proposal.update(
                        {
                            "action": "stamp",
                            "verdict": "superseded",
                            "evidence_span": evidence,
                            "start_byte": start,
                            "end_byte": start + len(encoded),
                        }
                    )
                else:
                    proposal.update(
                        {
                            "action": "no_verdict",
                            "verdict": None,
                            "evidence_span": None,
                            "start_byte": None,
                            "end_byte": None,
                        }
                    )
                score = fixtures.score_proposals(fixture_set, proposals)
                self.assertFalse(score["passed"])

    def test_nav_and_cross_body_evidence_never_count_as_legal(self) -> None:
        fixture_set = self._load()
        proposals = fixtures.gold_proposals(fixture_set)
        nav_case = next(
            case for case in fixture_set.cases if case.case_id == "adv-01-nav-evidence"
        )
        bait = "This synthetic page is superseded by a hidden replacement."
        start = nav_case.body.index(bait.encode("utf-8"))
        nav_proposal = next(
            p for p in proposals if p["case_id"] == nav_case.case_id
        )
        nav_proposal.update(
            {
                "action": "stamp",
                "verdict": "superseded",
                "evidence_span": bait,
                "start_byte": start,
                "end_byte": start + len(bait.encode("utf-8")),
            }
        )
        score = fixtures.score_proposals(fixture_set, proposals)
        nav_detail = next(
            detail for detail in score["cases"] if detail["case_id"] == nav_case.case_id
        )
        self.assertFalse(nav_detail["evidence_valid"])
        self.assertEqual(score["metrics"]["adversarial_illegal_stamps"], 1)
        self.assertFalse(score["passed"])

        proposals = fixtures.gold_proposals(fixture_set)
        spent = next(
            case for case in fixture_set.cases if case.case_id == "spent-01-superseded"
        )
        other = next(
            case for case in fixture_set.cases if case.case_id == "spent-03-finished"
        )
        foreign = other.record["expected"]["evidence"]
        proposal = next(p for p in proposals if p["case_id"] == spent.case_id)
        proposal.update(
            {
                "evidence_span": foreign,
                "start_byte": 0,
                "end_byte": len(foreign.encode("utf-8")),
            }
        )
        score = fixtures.score_proposals(fixture_set, proposals)
        detail = next(
            detail for detail in score["cases"] if detail["case_id"] == spent.case_id
        )
        self.assertFalse(detail["evidence_valid"])
        self.assertEqual(score["metrics"]["spent_recall"], 5 / 6)

    def test_proposal_parser_is_total_and_closed(self) -> None:
        fixture_set = self._load()
        gold = fixtures.gold_proposals(fixture_set)
        malformed: list[object] = []
        missing = copy.deepcopy(gold)
        missing[0].pop("confidence")
        malformed.append(missing)
        extra = copy.deepcopy(gold)
        extra[0]["surprise"] = True
        malformed.append(extra)
        for value in (
            True,
            float("nan"),
            float("inf"),
            -0.01,
            1.01,
            "certain",
        ):
            bad = copy.deepcopy(gold)
            bad[0]["confidence"] = value
            malformed.append(bad)
        bad_action = copy.deepcopy(gold)
        bad_action[0]["action"] = ["stamp"]
        malformed.append(bad_action)
        bad_null = copy.deepcopy(gold)
        bad_null[0]["evidence_span"] = "not-null"
        malformed.append(bad_null)
        malformed.extend((None, {}, "not-an-array", [None]))

        for index, value in enumerate(malformed):
            with self.subTest(index=index):
                with self.assertRaises(fixtures.FixtureContractError):
                    fixtures.score_proposals(fixture_set, value)

    def test_fixture_payload_is_disjoint_from_production_union_and_bodies(self) -> None:
        fixture_set = self._load()
        current, union = pruning_contract.load_target_index_union_strict(ROOT)
        production_uids = {
            row.get("uid") for row in union if isinstance(row.get("uid"), str)
        }
        production_paths = {
            row.get("path") for row in union if isinstance(row.get("path"), str)
        }
        self.assertTrue(
            all(case.record["uid"] not in production_uids for case in fixture_set.cases)
        )
        self.assertTrue(
            all(
                case.path.relative_to(ROOT).as_posix() not in production_paths
                for case in fixture_set.cases
            )
        )
        fixture_t2 = {normalized_body_sha256(case.path) for case in fixture_set.cases}
        production_t2: set[str] = set()
        for path in pruning_contract.iter_eligible_markdown(ROOT):
            try:
                production_t2.add(normalized_body_sha256(path))
            except Exception:
                continue
        self.assertTrue(fixture_t2.isdisjoint(production_t2))
        self.assertEqual(
            sum(
                isinstance(row.get("path"), str)
                and row["path"].startswith("vault/tools/fixtures/gardener-pruning/")
                for row in current
            ),
            0,
        )

    def test_loading_hashing_and_scoring_mutate_no_source_index_or_event(self) -> None:
        watched = (
            MANIFEST.parent,
            ROOT / "vault" / "00-index.jsonl",
            ROOT / "vault" / "00-archive-index.jsonl",
            ROOT / "vault" / "events" / "00-events.jsonl",
            ROOT / ".tropo-studio" / "dirty-counter.json",
        )
        before = {
            path.as_posix(): (
                _tree_hashes(path)
                if path.is_dir()
                else hashlib.sha256(path.read_bytes()).hexdigest()
            )
            for path in watched
        }
        fixture_set = self._load()
        fixtures.score_proposals(
            fixture_set,
            fixtures.gold_proposals(fixture_set),
        )
        after = {
            path.as_posix(): (
                _tree_hashes(path)
                if path.is_dir()
                else hashlib.sha256(path.read_bytes()).hexdigest()
            )
            for path in watched
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
