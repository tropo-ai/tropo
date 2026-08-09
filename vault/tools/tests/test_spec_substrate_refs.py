#!/usr/bin/env python3
"""Focused isolated plants for spec-family substrate refs and test-spec v1.2."""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".tropo" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib import dev_spec_validators, spec_substrate_refs, test_spec_validators


VALIDATE_PATH = ROOT / "vault" / "tools" / "tropo-validate.py"
_validate_spec = importlib.util.spec_from_file_location(
    "tropo_validate_spec_ref_tests", VALIDATE_PATH
)
tropo_validate = importlib.util.module_from_spec(_validate_spec)
assert _validate_spec.loader is not None
_validate_spec.loader.exec_module(tropo_validate)


DEV_UID = "dddd0001"
ACTIVATION_UID = "aaaa0001"
TEST_UID = "bbbb0001"
TARGET_UID = "cccc0001"


class Fixture:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="spec_refs_"))
        (self.root / "vault" / "files").mkdir(parents=True)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def write_entry(
        self,
        uid: str,
        frontmatter: dict,
        relative: str | None = None,
    ) -> Path:
        rel = relative or f"vault/files/{uid}.md"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "---\n"
            + yaml.safe_dump(frontmatter, sort_keys=False)
            + "---\n\n# fixture\n"
        )
        path.write_text(content, encoding="utf-8")
        return path

    def write_plain(self, relative: str, content: str = "fixture\n") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_index(self, rows: list[dict], *, archive: bool = False) -> None:
        name = "00-archive-index.jsonl" if archive else "00-index.jsonl"
        path = self.root / "vault" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )


def dev_frontmatter(
    targets: list[tuple[object, str]],
    acceptance_count: int = 1,
) -> dict:
    return {
        "uid": DEV_UID,
        "type": "dev-spec",
        "target_release": "1.86.0",
        "target_stream": "fixture",
        "committed_substrate": [
            {
                "target": target,
                "change_class": change_class,
                "description": "fixture target",
            }
            for target, change_class in targets
        ],
        "acceptance_criteria": [
            f"Acceptance criterion {number}"
            for number in range(1, acceptance_count + 1)
        ],
    }


def v18_dev_frontmatter(
    targets: list[tuple[object, str]],
    acceptance_count: int = 1,
) -> dict:
    frontmatter = dev_frontmatter(targets, acceptance_count)
    frontmatter["capsule_version"] = "1.8"
    del frontmatter["target_release"]
    del frontmatter["target_stream"]
    frontmatter["acceptance_criteria"] = [
        {
            "id": f"AC{number}",
            "behavior": f"Acceptance behavior {number}",
            "verify": {
                "method": "automated",
                "command": f"python3 -m unittest fixture_{number}",
                "evidence": f"Fixture {number} exits zero",
            },
        }
        for number in range(1, acceptance_count + 1)
    ]
    return frontmatter


def activation_frontmatter() -> dict:
    return {
        "uid": ACTIVATION_UID,
        "type": "activation",
        "dev_spec_uid": DEV_UID,
    }


def behavior(refs: list[object], ac: object = 1, method: str = "structural_check") -> dict:
    item = {
        "behavior_description": "A deterministic fixture behavior",
        "test_substrate_path": "new-file:vault/tools/tests/fixture.py",
        "verification_method": method,
        "target_substrate_refs": refs,
    }
    if ac is not None:
        item["verifies_acceptance_criterion"] = ac
    return item


def test_frontmatter(
    behaviors: list[dict],
    *,
    triggered_by: object = ACTIVATION_UID,
    created: object = "2026-07-17",
    capsule_version: object = "1.2",
    target_substrate: object = None,
    coverage_class: object = None,
    cycle_class: object = "engine-runtime",
) -> dict:
    fm = {
        "uid": TEST_UID,
        "type": "test-spec",
        "created": created,
        "capsule_version": capsule_version,
        "target_substrate": (
            [TARGET_UID] if target_substrate is None else target_substrate
        ),
        "target_subsystem": None,
        "triggered_by_dev_cycle": triggered_by,
        "triggering_dev_spec": DEV_UID,
        "behaviors_covered": behaviors,
        "coverage_class": (
            ["smoke", "property"]
            if coverage_class is None
            else coverage_class
        ),
        "cycle_class": cycle_class,
        "acceptance_criteria": "Fixture coverage is complete.",
    }
    if capsule_version is None:
        del fm["capsule_version"]
    if created is None:
        del fm["created"]
    return fm


def complete_fixture(
    targets: list[tuple[object, str]],
    behaviors: list[dict],
    *,
    test_fm: dict | None = None,
    dev_fm: dict | None = None,
    acceptance_count: int = 1,
) -> Fixture:
    fixture = Fixture()
    resolved_test_fm = test_fm or test_frontmatter(behaviors)
    resolved_test_uid = resolved_test_fm.get("uid", TEST_UID)
    fixture.write_entry(
        DEV_UID,
        dev_fm
        or dev_frontmatter(targets, acceptance_count=acceptance_count),
    )
    fixture.write_entry(ACTIVATION_UID, activation_frontmatter())
    fixture.write_entry(resolved_test_uid, resolved_test_fm)
    fixture.write_plain("vault/tools/target.py")
    fixture.write_index(
        [
            {"uid": DEV_UID, "type": "dev-spec", "path": f"vault/files/{DEV_UID}.md"},
            {
                "uid": ACTIVATION_UID,
                "type": "activation",
                "path": f"vault/files/{ACTIVATION_UID}.md",
            },
            {
                "uid": resolved_test_uid,
                "type": "test-spec",
                "path": f"vault/files/{resolved_test_uid}.md",
            },
            {"uid": TARGET_UID, "type": "tool", "path": "vault/tools/target.py"},
        ]
    )
    return fixture


class SpecSubstrateRefContractTests(unittest.TestCase):
    def test_uid_path_and_exact_literal_identity_only(self) -> None:
        fixture = Fixture()
        self.addCleanup(fixture.close)
        fixture.write_plain("vault/tools/target.py")
        fixture.write_index(
            [{"uid": TARGET_UID, "path": "vault/tools/target.py"}],
            archive=True,
        )
        identities = spec_substrate_refs.load_index_identities(fixture.root)
        uid = spec_substrate_refs.parse_substrate_ref(TARGET_UID, fixture.root)
        path = spec_substrate_refs.parse_substrate_ref(
            "vault/tools/target.py", fixture.root
        )
        same_path = spec_substrate_refs.parse_substrate_ref(
            "vault/tools/target.py", fixture.root
        )
        directory = spec_substrate_refs.parse_substrate_ref(
            "vault/tools/", fixture.root
        )
        basename = spec_substrate_refs.parse_substrate_ref(
            "target.py", fixture.root
        )
        case_variant = spec_substrate_refs.parse_substrate_ref(
            "vault/tools/Target.py", fixture.root
        )
        opaque = spec_substrate_refs.parse_substrate_ref(
            "gardener-body-judge", fixture.root
        )
        opaque_same = spec_substrate_refs.parse_substrate_ref(
            "gardener-body-judge", fixture.root
        )
        opaque_prefix = spec_substrate_refs.parse_substrate_ref(
            "gardener-body", fixture.root
        )

        self.assertTrue(spec_substrate_refs.refs_match(uid, path, identities))
        self.assertTrue(
            spec_substrate_refs.refs_match(path, same_path, identities)
        )
        self.assertTrue(
            spec_substrate_refs.refs_match(opaque, opaque_same, identities)
        )
        self.assertFalse(
            spec_substrate_refs.refs_match(path, directory, identities)
        )
        self.assertFalse(
            spec_substrate_refs.refs_match(path, basename, identities)
        )
        self.assertFalse(
            spec_substrate_refs.refs_match(path, case_variant, identities)
        )
        self.assertFalse(
            spec_substrate_refs.refs_match(opaque, opaque_prefix, identities)
        )

    def test_root_file_and_all_unsafe_path_classes(self) -> None:
        fixture = Fixture()
        self.addCleanup(fixture.close)
        fixture.write_plain("CLAUDE.md")
        root_file = spec_substrate_refs.parse_substrate_ref(
            "CLAUDE.md", fixture.root
        )
        self.assertEqual((root_file.kind, root_file.exists), ("path", True))

        fixture.write_plain("real/file.md")
        (fixture.root / "alias").symlink_to(fixture.root / "real")
        unsafe = [
            "/vault/file.md",
            "./vault/file.md",
            "vault/../file.md",
            "vault/./file.md",
            "vault//file.md",
            "vault\\file.md",
            "vault/\x00file.md",
            "vault/\ud800file.md",
            "real/file.md/",
            "alias/file.md",
        ]
        for value in unsafe:
            with self.subTest(value=value):
                with self.assertRaises(spec_substrate_refs.SubstrateRefError):
                    spec_substrate_refs.parse_substrate_ref(value, fixture.root)

    def test_dev_validation_unresolved_uid_and_missing_path_classes(self) -> None:
        fixture = Fixture()
        self.addCleanup(fixture.close)
        fixture.write_entry(
            DEV_UID,
            dev_frontmatter(
                [
                    ("eeee0001", "NEW"),
                    ("vault/tools/planned.py", "NEW"),
                    ("vault/tools/missing.py", "AMENDED"),
                    (["not", "a", "string"], "NEW"),
                ]
            ),
        )
        findings, checked, defects = (
            dev_spec_validators.check_dev_spec_committed_substrate_resolvable(
                fixture.root
            )
        )
        joined = "\n".join(findings)
        self.assertEqual(checked, 1)
        self.assertEqual(defects, 3)
        self.assertIn("UID eeee0001 does not resolve", joined)
        self.assertIn("[INFO]", joined)
        self.assertIn("NEW path 'vault/tools/planned.py'", joined)
        self.assertIn("AMENDED path 'vault/tools/missing.py' does not exist", joined)
        self.assertIn("must be a string", joined)


class TestSpecV12PairingTests(unittest.TestCase):
    def test_activation_traversal_and_optional_dev_uid_equality(self) -> None:
        fixture = complete_fixture(
            [(TARGET_UID, "NEW")], [behavior([TARGET_UID])]
        )
        self.addCleanup(fixture.close)
        findings, checked, _ = (
            test_spec_validators.check_test_spec_triggered_by_dev_cycle_resolvable(
                fixture.root
            )
        )
        self.assertEqual((checked, findings), (1, []))

        mismatch = test_frontmatter([behavior([TARGET_UID])])
        mismatch["triggering_dev_spec"] = "eeee0001"
        other = complete_fixture(
            [(TARGET_UID, "NEW")],
            [behavior([TARGET_UID])],
            test_fm=mismatch,
        )
        self.addCleanup(other.close)
        findings, _, _ = (
            test_spec_validators.check_test_spec_triggered_by_dev_cycle_resolvable(
                other.root
            )
        )
        self.assertTrue(
            any(
                finding.startswith("[ERROR]")
                and "does not equal resolved dev-spec UID" in finding
                for finding in findings
            ),
            findings,
        )

    def test_frozen_cohort_ignores_dates_and_generic_versions(self) -> None:
        fixture = Fixture()
        self.addCleanup(fixture.close)
        fixture.write_entry(DEV_UID, dev_frontmatter([(TARGET_UID, "NEW")]))
        specs = [
            (
                "1fee7e4b",
                test_frontmatter(
                    [behavior([TARGET_UID])],
                    triggered_by=DEV_UID,
                    created="2099-01-01",
                    capsule_version="2.5",
                ),
            ),
            (
                "ac6e3792",
                test_frontmatter(
                    [behavior([TARGET_UID])],
                    triggered_by=DEV_UID,
                    created=None,
                    capsule_version=None,
                ),
            ),
            (
                "bbbb0001",
                test_frontmatter(
                    [behavior([TARGET_UID])],
                    triggered_by=DEV_UID,
                    created="2000-01-01",
                    capsule_version="1.1",
                ),
            ),
            (
                "bbbb0002",
                test_frontmatter(
                    [behavior([TARGET_UID])],
                    triggered_by=DEV_UID,
                    created="2000-01-01",
                    capsule_version="1.2",
                ),
            ),
            (
                "bbbb0003",
                test_frontmatter(
                    [behavior([TARGET_UID])],
                    triggered_by=DEV_UID,
                    created="2000-01-01",
                    capsule_version=None,
                ),
            ),
            (
                "bbbb0004",
                test_frontmatter(
                    [behavior([TARGET_UID])],
                    triggered_by=DEV_UID,
                    created="2000-01-01",
                    capsule_version=1.2,
                ),
            ),
        ]
        for uid, fm in specs:
            fm["uid"] = uid
            fixture.write_entry(uid, fm)

        linkage, checked, _ = (
            test_spec_validators.check_test_spec_triggered_by_dev_cycle_resolvable(
                fixture.root
            )
        )
        required, _, _ = test_spec_validators.check_test_spec_required_fields(
            fixture.root
        )
        all_findings = "\n".join(linkage + required)
        self.assertEqual(checked, 6)
        self.assertNotIn("1fee7e4b.md — triggered_by_dev_cycle", all_findings)
        self.assertNotIn("ac6e3792.md — triggered_by_dev_cycle", all_findings)
        for uid in ("bbbb0001", "bbbb0002", "bbbb0003", "bbbb0004"):
            self.assertIn(f"[ERROR] vault/files/{uid}.md", all_findings)
        self.assertIn("outside the frozen v1.2 cohort", all_findings)
        self.assertIn("back-level", all_findings)
        self.assertIn("must be a semver string", all_findings)
        self.assertEqual(
            len(test_spec_validators.FROZEN_LEGACY_TEST_SPEC_UIDS), 46
        )

    def test_malformed_behaviors_are_empty_then_report_every_rule_3_gap(self) -> None:
        targets = [(TARGET_UID, "NEW"), ("planned-target", "NEW")]
        for malformed in ({"not": "a-list"}, [7]):
            with self.subTest(malformed=malformed):
                strict_fm = test_frontmatter([])
                strict_fm["behaviors_covered"] = malformed
                fixture = complete_fixture(
                    targets,
                    [],
                    test_fm=strict_fm,
                    acceptance_count=3,
                )
                self.addCleanup(fixture.close)
                findings, checked, _ = (
                    test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                        fixture.root
                    )
                )
                self.assertEqual(checked, 1)
                self.assertEqual(
                    len([item for item in findings if item.startswith("[ERROR]")]),
                    6,
                    findings,
                )
                self.assertEqual(
                    len([item for item in findings if "NEW target" in item]),
                    2,
                    findings,
                )
                self.assertEqual(
                    len([item for item in findings if "criterion #" in item]),
                    3,
                    findings,
                )

        legacy_fm = test_frontmatter(
            [], capsule_version="9.9", created="2099-01-01"
        )
        legacy_fm["uid"] = "1fee7e4b"
        legacy_fm["behaviors_covered"] = {"not": "a-list"}
        legacy_fixture = complete_fixture(
            targets,
            [],
            test_fm=legacy_fm,
            acceptance_count=3,
        )
        self.addCleanup(legacy_fixture.close)
        legacy_findings, _, _ = (
            test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                legacy_fixture.root
            )
        )
        self.assertEqual(len(legacy_findings), 6, legacy_findings)
        self.assertTrue(
            all(item.startswith("[WARN]") for item in legacy_findings),
            legacy_findings,
        )

    def test_uid_path_path_path_and_opaque_pairing(self) -> None:
        targets = [
            (TARGET_UID, "NEW"),
            ("vault/tools/exact.py", "NEW"),
            ("gardener-body-judge", "NEW"),
        ]
        behaviors = [
            behavior(["vault/tools/target.py"], 1),
            behavior(["vault/tools/exact.py"], 2),
            behavior(["gardener-body-judge"], 3),
        ]
        fixture = complete_fixture(
            targets, behaviors, acceptance_count=3
        )
        self.addCleanup(fixture.close)
        findings, checked, _ = (
            test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                fixture.root
            )
        )
        self.assertEqual((checked, findings), (1, []))

    def test_unresolved_test_side_uid_is_strict_error(self) -> None:
        fm = test_frontmatter(
            [behavior([TARGET_UID])],
            target_substrate=["eeee0001"],
        )
        fixture = complete_fixture(
            [(TARGET_UID, "NEW")],
            fm["behaviors_covered"],
            test_fm=fm,
        )
        self.addCleanup(fixture.close)
        findings, checked, _ = (
            test_spec_validators.check_test_spec_target_substrate_resolvable(
                fixture.root
            )
        )
        self.assertEqual(checked, 1)
        self.assertTrue(
            any(
                finding.startswith("[ERROR]")
                and "UID eeee0001 does not resolve" in finding
                for finding in findings
            ),
            findings,
        )

    def test_no_fuzzy_prefix_or_directory_containment_pairing(self) -> None:
        fixture = complete_fixture(
            [("vault/tools/alpha.py", "NEW")],
            [behavior(["vault/tools/"], 1)],
        )
        self.addCleanup(fixture.close)
        findings, _, _ = (
            test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                fixture.root
            )
        )
        self.assertTrue(
            any(
                finding.startswith("[ERROR]")
                and "NEW target 'vault/tools/alpha.py' has no exact" in finding
                for finding in findings
            ),
            findings,
        )

    def test_gardener_new_targets_each_have_indispensable_exact_ref(self) -> None:
        gardener_targets = [
            "vault/tools/lib/normalized_body_hash.py",
            "vault/tools/tropo-gardener-verdict.py",
            "gardener-body-judge",
            "first-sweep-plan",
            "vault/tools/tropo-validate.py",
            "validation-fixtures",
        ]
        behaviors = [
            behavior([target], index)
            for index, target in enumerate(gardener_targets, start=1)
        ]
        behaviors.extend(
            behavior([], index)
            for index in range(len(gardener_targets) + 1, 11)
        )
        targets = [(target, "NEW") for target in gardener_targets]

        fixture = complete_fixture(
            targets, behaviors, acceptance_count=10
        )
        self.addCleanup(fixture.close)
        findings, _, _ = (
            test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                fixture.root
            )
        )
        self.assertEqual(findings, [])

        for removed_index, removed_target in enumerate(gardener_targets):
            with self.subTest(removed_target=removed_target):
                changed = copy.deepcopy(behaviors)
                changed[removed_index]["target_substrate_refs"] = []
                plant = complete_fixture(
                    targets, changed, acceptance_count=10
                )
                self.addCleanup(plant.close)
                findings, _, _ = (
                    test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                        plant.root
                    )
                )
                gaps = [
                    finding
                    for finding in findings
                    if "has no exact behaviors_covered.target_substrate_refs" in finding
                ]
                self.assertEqual(len(gaps), 1, findings)
                self.assertIn(repr(removed_target), gaps[0])

    def test_all_ten_acs_missing_invalid_and_out_of_range_pointers(self) -> None:
        behaviors = [
            behavior([TARGET_UID], index) for index in range(1, 11)
        ]
        fixture = complete_fixture(
            [(TARGET_UID, "NEW")], behaviors, acceptance_count=10
        )
        self.addCleanup(fixture.close)
        findings, _, _ = (
            test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                fixture.root
            )
        )
        self.assertEqual(findings, [])

        for label, replacement, expected in (
            ("missing", None, "criterion #10 has no covering behavior"),
            ("out-of-range", 11, "verifies AC #11"),
            ("invalid", "10", "must be a 1-based integer"),
            ("strict-list", [10], "must be a 1-based integer"),
        ):
            with self.subTest(label=label):
                changed = copy.deepcopy(behaviors)
                if replacement is None:
                    changed[-1].pop("verifies_acceptance_criterion")
                else:
                    changed[-1]["verifies_acceptance_criterion"] = replacement
                plant = complete_fixture(
                    [(TARGET_UID, "NEW")],
                    changed,
                    acceptance_count=10,
                )
                self.addCleanup(plant.close)
                findings, _, _ = (
                    test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                        plant.root
                    )
                )
                self.assertTrue(
                    any(
                        finding.startswith("[ERROR]") and expected in finding
                        for finding in findings
                    ),
                    findings,
                )

    def test_legacy_list_pointer_remains_compatible(self) -> None:
        legacy = test_frontmatter(
            [behavior([TARGET_UID], [1])],
            triggered_by=DEV_UID,
            created="2026-07-16",
            capsule_version=None,
        )
        legacy["uid"] = "ac6e3792"
        fixture = complete_fixture(
            [(TARGET_UID, "NEW")],
            legacy["behaviors_covered"],
            test_fm=legacy,
        )
        self.addCleanup(fixture.close)
        findings, _, _ = (
            test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                fixture.root
            )
        )
        self.assertEqual(findings, [])

    def test_v18_stable_ac_ids_are_required_and_covered(self) -> None:
        behaviors = [
            behavior([TARGET_UID], "AC1"),
            behavior([], "AC2"),
        ]
        dev_fm = v18_dev_frontmatter(
            [(TARGET_UID, "NEW")],
            acceptance_count=2,
        )
        fixture = complete_fixture(
            [(TARGET_UID, "NEW")],
            behaviors,
            dev_fm=dev_fm,
        )
        self.addCleanup(fixture.close)
        findings, _, _ = (
            test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                fixture.root
            )
        )
        self.assertEqual(findings, [])

        for label, replacement, expected in (
            ("missing", None, "criterion AC2 has no covering behavior"),
            ("legacy-integer", 2, "must be a stable AC ID string"),
            ("unknown-id", "AC9", "does not declare that acceptance ID"),
        ):
            with self.subTest(label=label):
                changed = copy.deepcopy(behaviors)
                if replacement is None:
                    changed[-1].pop("verifies_acceptance_criterion")
                else:
                    changed[-1]["verifies_acceptance_criterion"] = replacement
                plant = complete_fixture(
                    [(TARGET_UID, "NEW")],
                    changed,
                    dev_fm=dev_fm,
                )
                self.addCleanup(plant.close)
                findings, _, _ = (
                    test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                        plant.root
                    )
                )
                self.assertTrue(
                    any(expected in finding for finding in findings),
                    findings,
                )


class TestSpecV12CoverageAndAdapterTests(unittest.TestCase):
    def _coverage_findings(
        self,
        coverage: object,
        cycle: object = "engine-runtime",
        method: str = "structural_check",
    ) -> list[str]:
        fixture = complete_fixture(
            [(TARGET_UID, "NEW")],
            [behavior([TARGET_UID], method=method)],
            test_fm=test_frontmatter(
                [behavior([TARGET_UID], method=method)],
                coverage_class=coverage,
                cycle_class=cycle,
            ),
        )
        self.addCleanup(fixture.close)
        return test_spec_validators.check_test_spec_coverage_class_completeness(
            fixture.root
        )[0]

    def _conditional_findings(
        self,
        targets: list[tuple[object, str]],
        coverage: list[str],
        cycle: str,
        *,
        test_uid: str = TEST_UID,
        metadata: dict | None = None,
    ) -> list[str]:
        fm = test_frontmatter(
            [behavior([TARGET_UID])],
            coverage_class=coverage,
            cycle_class=cycle,
        )
        fm["uid"] = test_uid
        fixture = complete_fixture(
            targets,
            fm["behaviors_covered"],
            test_fm=fm,
        )
        self.addCleanup(fixture.close)
        if metadata is not None:
            fixture.write_entry("eeee0001", metadata)
        return test_spec_validators.check_test_spec_coverage_class_completeness(
            fixture.root
        )[0]

    def test_scalar_and_list_coverage_normalization_and_invalid_sets(self) -> None:
        self.assertEqual(
            self._coverage_findings(["smoke", "property"]), []
        )
        scalar = self._coverage_findings("smoke")
        self.assertTrue(any("missing: ['property']" in item for item in scalar))

        cases = [
            ([], "must be non-empty"),
            (["smoke", "smoke", "property"], "duplicate 'smoke'"),
            (["smoke", 7, "property"], "must be a string"),
            (["smoke", "unknown", "property"], "value 'unknown'"),
        ]
        for declaration, expected in cases:
            with self.subTest(declaration=declaration):
                findings = self._coverage_findings(declaration)
                self.assertTrue(
                    any(
                        finding.startswith("[ERROR]") and expected in finding
                        for finding in findings
                    ),
                    findings,
                )

    def test_engine_and_substrate_class_minima(self) -> None:
        engine = self._coverage_findings(["smoke"])
        self.assertTrue(any("missing: ['property']" in item for item in engine))

        substrate = self._coverage_findings(
            ["smoke"], cycle="substrate", method="machine_executable_script"
        )
        self.assertTrue(
            any("requires at least one structural_check behavior" in item for item in substrate)
        )
        self.assertEqual(
            self._coverage_findings(
                ["smoke"], cycle="substrate", method="structural_check"
            ),
            [],
        )

    def test_conditional_regression_and_gauntlet_minima(self) -> None:
        substrate_targets = [
            ("vault/tools/existing.py", "AMENDED"),
            ("vault/capsules/tropo-new.capsule.md", "NEW"),
        ]
        substrate = self._conditional_findings(
            substrate_targets, ["smoke"], "substrate"
        )
        self.assertTrue(
            any(
                finding.startswith("[ERROR]")
                and "missing: ['gauntlet', 'regression']" in finding
                for finding in substrate
            ),
            substrate,
        )
        self.assertEqual(
            self._conditional_findings(
                substrate_targets,
                ["smoke", "regression", "gauntlet"],
                "substrate",
            ),
            [],
        )
        os_type = self._conditional_findings(
            [("eeee0001", "NEW")],
            ["smoke"],
            "substrate",
            metadata={"uid": "eeee0001", "type": "os-primitive"},
        )
        self.assertTrue(
            any("missing: ['gauntlet']" in finding for finding in os_type),
            os_type,
        )

        engine_metadata = {
            "uid": "eeee0001",
            "type": "design-spec",
            "tags": ["engine-extension"],
        }
        engine_targets = [
            ("vault/tools/existing.py", "REFACTORED"),
            ("eeee0001", "NEW"),
        ]
        engine = self._conditional_findings(
            engine_targets,
            ["smoke", "property"],
            "engine-runtime",
            metadata=engine_metadata,
        )
        self.assertTrue(
            any(
                finding.startswith("[ERROR]")
                and "missing: ['gauntlet', 'regression']" in finding
                for finding in engine
            ),
            engine,
        )
        self.assertEqual(
            self._conditional_findings(
                engine_targets,
                ["smoke", "property", "regression", "gauntlet"],
                "engine-runtime",
                metadata=engine_metadata,
            ),
            [],
        )

        ux = self._conditional_findings(
            [("vault/pages/existing.md", "AMENDED")],
            ["smoke", "cold-boot"],
            "ux",
        )
        self.assertTrue(
            any("missing: ['regression']" in finding for finding in ux),
            ux,
        )

    def test_conditional_minima_are_exact_and_legacy_warn_grade(self) -> None:
        near_miss_metadata = {
            "uid": "eeee0001",
            "type": "design-spec",
            "tags": ["engine-extension-like"],
        }
        self.assertEqual(
            self._conditional_findings(
                [
                    ("vault/capsules-extra/not-a-capsule.md", "NEW"),
                    ("eeee0001", "NEW"),
                ],
                ["smoke", "property"],
                "engine-runtime",
                metadata=near_miss_metadata,
            ),
            [],
        )

        legacy = self._conditional_findings(
            [
                ("vault/tools/existing.py", "AMENDED"),
                ("vault/capsules/tropo-new.capsule.md", "NEW"),
            ],
            ["smoke"],
            "substrate",
            test_uid="1fee7e4b",
        )
        self.assertTrue(legacy, legacy)
        self.assertTrue(
            all(finding.startswith("[WARN]") for finding in legacy),
            legacy,
        )

    def test_conditional_minima_full_family_and_check_one_parity(self) -> None:
        fm = test_frontmatter(
            [behavior(["eeee0001"])],
            coverage_class=["smoke", "property"],
            cycle_class="engine-runtime",
        )
        fixture = complete_fixture(
            [
                ("vault/tools/existing.py", "REFACTORED"),
                ("eeee0001", "NEW"),
            ],
            fm["behaviors_covered"],
            test_fm=fm,
        )
        self.addCleanup(fixture.close)
        fixture.write_entry(
            "eeee0001",
            {
                "uid": "eeee0001",
                "type": "design-spec",
                "tags": ["engine-extension"],
            },
        )

        direct = (
            test_spec_validators.check_test_spec_coverage_class_completeness(
                fixture.root
            )[0]
        )
        shared_family = test_spec_validators.run_all_test_spec_checks(
            fixture.root
        )
        full_family = tropo_validate.check_test_spec_family(fixture.root)
        self.assertEqual(full_family, shared_family)
        self.assertTrue(
            any("missing: ['gauntlet', 'regression']" in item for item in direct),
            direct,
        )
        for finding in direct:
            self.assertIn(finding, full_family[0])

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "vault" / "tools" / "tropo-check-one.py"),
                TEST_UID,
                "--capsule",
                "test-spec",
                "--vault-path",
                str(fixture.root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "missing: ['gauntlet', 'regression']",
            result.stdout + result.stderr,
        )

    def test_malformed_amended_target_cannot_suppress_regression_floor(self) -> None:
        fm = test_frontmatter(
            [behavior([TARGET_UID])],
            coverage_class=["smoke", "property"],
            cycle_class="engine-runtime",
        )
        fixture = complete_fixture(
            [(["malformed", "target"], "AMENDED"), (TARGET_UID, "NEW")],
            fm["behaviors_covered"],
            test_fm=fm,
        )
        self.addCleanup(fixture.close)

        direct = test_spec_validators.run_all_test_spec_checks(fixture.root)
        full = tropo_validate.check_test_spec_family(fixture.root)
        self.assertEqual(full, direct)
        joined = "\n".join(direct[0])
        self.assertIn(
            "AMENDED target at committed_substrate[0] "
            "['malformed', 'target'] is an invalid substrate-ref",
            joined,
        )
        self.assertIn("missing: ['regression']", joined)

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "vault" / "tools" / "tropo-check-one.py"),
                TEST_UID,
                "--capsule",
                "test-spec",
                "--vault-path",
                str(fixture.root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        output = result.stdout + result.stderr
        self.assertIn("is an invalid substrate-ref", output)
        self.assertIn("missing: ['regression']", output)

    def test_full_and_targeted_adapters_share_pairing_substance(self) -> None:
        fm = test_frontmatter([])
        fm["behaviors_covered"] = {"malformed": True}
        fixture = complete_fixture(
            [(TARGET_UID, "NEW"), ("planned-target", "NEW")],
            [],
            test_fm=fm,
            acceptance_count=3,
        )
        self.addCleanup(fixture.close)
        shared_findings, shared_checked, _ = (
            test_spec_validators.check_test_spec_cross_validation_against_dev_spec(
                fixture.root
            )
        )
        full_findings, full_checked, full_defects = (
            tropo_validate.check_spec_coverage_pairing(fixture.root)
        )
        self.assertEqual((full_findings, full_checked), (shared_findings, shared_checked))
        self.assertGreater(full_defects, 0)
        self.assertEqual(len(shared_findings), 6, shared_findings)
        shared_family = test_spec_validators.run_all_test_spec_checks(
            fixture.root
        )
        full_family = tropo_validate.check_test_spec_family(fixture.root)
        self.assertEqual(full_family, shared_family)

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "vault" / "tools" / "tropo-check-one.py"),
                TEST_UID,
                "--capsule",
                "test-spec",
                "--vault-path",
                str(fixture.root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "NEW target 'cccc0001' has no exact",
            result.stdout + result.stderr,
        )
        self.assertIn(
            "NEW target 'planned-target' has no exact",
            result.stdout + result.stderr,
        )
        self.assertIn(
            "acceptance criterion #3 has no covering behavior",
            result.stdout + result.stderr,
        )
        self.assertIn(
            "malformed value is evaluated as empty",
            result.stdout + result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
