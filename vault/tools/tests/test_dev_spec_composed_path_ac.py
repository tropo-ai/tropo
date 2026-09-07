#!/usr/bin/env python3
"""test_dev_spec_composed_path_ac.py — adversarial gauntlet for The Seam Rule
(dev-spec f5790777 / dev-spec.capsule Governance Rule 10): validates
`check_dev_spec_composed_path_ac` in `tropo-validate.py`.

This file IS f5790777's AC5 — the composed-path acceptance criterion the rule
it tests demands of every spec that touches a shared lifecycle surface. It
runs the whole chain end-to-end (capsule enumeration -> parser -> matcher ->
ratchet -> finding text) on a THROWAWAY studio minted into a tempdir, not on
the unit under change, and it mutates no governed substrate.

The three legs, and why each exists (f5790777 §Risks and Failure Modes):

  Leg 1 — KNOWN-POSITIVE MUST FIRE. "A check that never fires on the
    substrate that motivated it passes every naive test and protects
    nothing." A scratch dev-spec targeting a declared shared surface with no
    composed_path AC must be reported. If this leg cannot fail, the check is
    blind.

  Leg 2 — KNOWN-NEGATIVE MUST PASS. The same spec carrying
    `composed_path: true` on one AC must not be reported, or the rule is a
    blanket ban rather than a gate.

  Leg 3 — THE RATCHET MUST CHANGE VERDICT. Severity is derived from
    `len(DEV_SPEC_COMPOSED_PATH_ALLOWLIST) == 0`. Emptying the allowlist must
    genuinely flip the SAME violation from WARN to ERROR. That verdict change
    when the mechanism is removed is this leg's whole purpose — a leg that
    stays green either way proves nothing about the ratchet.

Plus the refusal legs: the check must report [ERROR] rather than green when
it cannot read its own subject (capsule missing / markers absent /
enumeration empty). A gate that silently passes when blind is exactly the
failure mode f5790777 exists to prevent.

NOTE ON THE FIXTURE CAPSULE (talos, build time 2026-08-29): the marker block
is being written into the real `vault/capsules/tropo-dev-spec.capsule.md` by
argus-a163 concurrently with this build. These tests therefore mint their own
FIXTURE capsule in the tempdir and never read, and never require, the live
one — which is the correct shape regardless: the legs must be deterministic
against a planted enumeration, not against whatever the live capsule happens
to say on a given day. `test_live_capsule_enumeration_is_readable` is the one
deliberate exception; it is skipped (not failed) while the markers are absent.
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALIDATE_PATH = ROOT / "vault" / "tools" / "tropo-validate.py"
if str(ROOT / "vault" / "tools") not in sys.path:
    # exec_module below loads tropo-validate.py in-process; it inherits THIS
    # sys.path and does `from lib.work_item_types import ...` at top level
    # since 2026-08-31. (suite-health 2026-09-03; same class as five siblings)
    sys.path.insert(0, str(ROOT / "vault" / "tools"))

_spec = importlib.util.spec_from_file_location(
    "tropo_validate_under_test_f5790777", str(VALIDATE_PATH))
tropo_validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tropo_validate)

check_fn = tropo_validate.check_dev_spec_composed_path_ac
BEGIN = tropo_validate._COMPOSED_PATH_SURFACES_BEGIN
END = tropo_validate._COMPOSED_PATH_SURFACES_END

# A small, representative slice of the real enumeration. The check reads the
# set from the capsule at runtime, so the fixture only has to be a valid
# enumeration — not a copy of the live one. (Copying the live one here would
# recreate the two-lists-drifting defect the rule forbids.)
FIXTURE_SURFACES = [
    "vault/tools/lib/release_package.py",
    "vault/tools/9e7003b1.py",
    "vault/tools/tropo-release.py",
]
UNDECLARED_SURFACE = "vault/tools/some-ordinary-unshared-tool.py"


def _capsule_body(surfaces: list[str], *, with_markers: bool = True) -> str:
    block = ""
    if with_markers:
        lines = "\n".join(
            ["# comment lines and blanks are stripped by the parser", ""] + surfaces)
        block = f"{BEGIN}\n{lines}\n{END}\n"
    return (
        "---\n"
        "uid: c3f68cb5\n"
        "type: capsule\n"
        "version: '1.10'\n"
        "---\n\n"
        "# Fixture dev-spec capsule\n\n"
        "## Shared lifecycle surfaces\n\n"
        f"{block}"
        "\n## Governance Rules\n\nRule 10 fixture text.\n"
    )


def _dev_spec(uid: str, *, target: str, status: str = "locked",
              composed_path: bool = False, legacy_ac: bool = False) -> str:
    if legacy_ac:
        ac_block = "acceptance_criteria:\n  - 'a legacy pre-v1.8 string criterion'\n"
    else:
        cp_line = "    composed_path: true\n" if composed_path else ""
        ac_block = (
            "acceptance_criteria:\n"
            "  - id: AC1\n"
            f"{cp_line}"
            "    behavior: 'fixture behavior'\n"
            "    verify:\n"
            "      method: automated\n"
            "      command: 'true'\n"
            "      evidence: 'exits 0'\n"
        )
    return (
        "---\n"
        f"uid: {uid}\n"
        "type: dev-spec\n"
        f"status: {status}\n"
        "title: 'scratch fixture dev-spec'\n"
        "description: 'scratch fixture'\n"
        "committed_substrate:\n"
        f"  - target: \"{target}\"\n"
        "    change_class: AMENDED\n"
        "    description: 'scratch fixture target'\n"
        f"{ac_block}"
        "---\n\n# scratch fixture\n"
    )


class _ScratchStudio(unittest.TestCase):
    """Mints a throwaway studio (vault/capsules + vault/files) per test and
    deletes it in tearDown. No governed substrate is read or written."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="dscp_fixture_"))
        (self.tmp / "vault" / "files").mkdir(parents=True)
        (self.tmp / "vault" / "capsules").mkdir(parents=True)
        self.write_capsule(FIXTURE_SURFACES)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertFalse(self.tmp.exists(), "throwaway studio was not cleaned up")

    def write_capsule(self, surfaces: list[str], *, with_markers: bool = True) -> None:
        (self.tmp / "vault" / "capsules" / "tropo-dev-spec.capsule.md").write_text(
            _capsule_body(surfaces, with_markers=with_markers), encoding="utf-8")

    def write_spec(self, uid: str, **kw) -> None:
        (self.tmp / "vault" / "files" / f"{uid}.md").write_text(
            _dev_spec(uid, **kw), encoding="utf-8")


class TestLeg1KnownPositiveFires(_ScratchStudio):
    """LEG 1 — the known-positive MUST fire."""

    def test_leg1_shared_surface_without_composed_path_is_flagged(self) -> None:
        self.write_spec("aaaa1111", target="vault/tools/9e7003b1.py")
        findings, checked, violations = check_fn(self.tmp)
        self.assertEqual(checked, 1, findings)
        self.assertEqual(violations, 1, findings)
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("aaaa1111", findings[0])
        self.assertIn("vault/tools/9e7003b1.py", findings[0])
        self.assertIn("composed_path", findings[0])

    def test_leg1_fires_for_draft_status_too(self) -> None:
        self.write_spec("aaaa2222", target="vault/tools/tropo-release.py", status="draft")
        _findings, checked, violations = check_fn(self.tmp)
        self.assertEqual((checked, violations), (1, 1))

    def test_leg1_legacy_string_acs_cannot_declare_and_are_flagged(self) -> None:
        # Pre-v1.8 list-of-strings ACs carry no marker; absent means absent.
        self.write_spec("aaaa3333", target="vault/tools/9e7003b1.py", legacy_ac=True)
        _findings, checked, violations = check_fn(self.tmp)
        self.assertEqual((checked, violations), (1, 1))


class TestLeg2KnownNegativePasses(_ScratchStudio):
    """LEG 2 — the known-negative MUST pass."""

    def test_leg2_composed_path_true_clears_the_same_spec(self) -> None:
        # Identical spec to leg 1's, one field added. Prove it fires first, so
        # the pass is a cure and not an inert fixture.
        self.write_spec("bbbb1111", target="vault/tools/9e7003b1.py")
        _f0, _c0, violations_before = check_fn(self.tmp)
        self.assertEqual(violations_before, 1)

        self.write_spec("bbbb1111", target="vault/tools/9e7003b1.py", composed_path=True)
        findings, checked, violations = check_fn(self.tmp)
        self.assertEqual(checked, 1, findings)
        self.assertEqual(violations, 0, findings)
        self.assertEqual(findings, [])

    def test_leg2_undeclared_surface_is_out_of_scope(self) -> None:
        self.write_spec("bbbb2222", target=UNDECLARED_SURFACE)
        findings, checked, violations = check_fn(self.tmp)
        self.assertEqual((checked, violations), (0, 0), findings)

    def test_leg2_done_specs_are_grandfathered(self) -> None:
        # f5790777 §Scope Boundaries: existing done dev-specs are untouched.
        self.write_spec("bbbb3333", target="vault/tools/9e7003b1.py", status="done")
        findings, checked, violations = check_fn(self.tmp)
        self.assertEqual((checked, violations), (0, 0), findings)

    def test_leg2_matching_is_exact_not_prefix_or_containment(self) -> None:
        # dev-spec.capsule §Substrate Reference Syntax: prefix, containment,
        # basename, case-fold and fuzzy matches are FORBIDDEN.
        for uid, target in (
            ("bbbb4444", "vault/tools/9e7003b1.py (parse_exit_criterion:615)"),
            ("bbbb5555", "vault/tools"),
            ("bbbb6666", "9e7003b1.py"),
            ("bbbb7777", "VAULT/TOOLS/9E7003B1.PY"),
            ("bbbb8888", "argo/vault/tools/9e7003b1.py"),
        ):
            with self.subTest(target=target):
                self.write_spec(uid, target=target)
                findings, checked, violations = check_fn(self.tmp)
                self.assertEqual((checked, violations), (0, 0), findings)
                (self.tmp / "vault" / "files" / f"{uid}.md").unlink()


class TestLeg3RatchetChangesVerdict(_ScratchStudio):
    """LEG 3 — the ratchet MUST change verdict when the mechanism is removed."""

    def test_leg3_emptying_the_allowlist_flips_warn_to_error(self) -> None:
        self.write_spec("cccc1111", target="vault/tools/lib/release_package.py")
        original = tropo_validate.DEV_SPEC_COMPOSED_PATH_ALLOWLIST

        # (a) Shipped state: the seed allowlist is non-empty -> WARN.
        self.assertTrue(
            len(original) > 0,
            "DEV_SPEC_COMPOSED_PATH_ALLOWLIST shipped EMPTY — this is f5790777's "
            "'ratchet trap (highest)': the check would go ERROR on day one against "
            "the whole in-flight population and break the validator for the crew.")
        findings_warn, _c_w, violations_w = check_fn(self.tmp)
        self.assertEqual(violations_w, 1, findings_warn)
        self.assertTrue(all(f.startswith("[WARN]") for f in findings_warn), findings_warn)

        # (b) Mechanism removed: allowlist emptied -> the SAME violation is ERROR.
        tropo_validate.DEV_SPEC_COMPOSED_PATH_ALLOWLIST = frozenset()
        try:
            findings_error, _c_e, violations_e = check_fn(self.tmp)
        finally:
            tropo_validate.DEV_SPEC_COMPOSED_PATH_ALLOWLIST = original
        self.assertEqual(violations_e, 1, findings_error)
        self.assertTrue(all(f.startswith("[ERROR]") for f in findings_error), findings_error)

        # The verdict genuinely CHANGED — the point of this leg.
        self.assertNotEqual(findings_warn[0].split(" ")[0], findings_error[0].split(" ")[0])
        # And the module is restored for every other test in this file.
        self.assertEqual(tropo_validate.DEV_SPEC_COMPOSED_PATH_ALLOWLIST, original)

    def test_leg3_seed_allowlist_membership_only_changes_wording(self) -> None:
        # Membership must NOT suppress the finding — it changes the cure note
        # only, exactly as the check_dev_spec_activation_coupling precedent does.
        seeded_uid = sorted(tropo_validate.DEV_SPEC_COMPOSED_PATH_ALLOWLIST)[0]
        self.write_spec(seeded_uid, target="vault/tools/tropo-release.py")
        findings, checked, violations = check_fn(self.tmp)
        self.assertEqual((checked, violations), (1, 1), findings)
        self.assertTrue(findings[0].startswith("[WARN]"), findings)
        self.assertIn("on the f5790777 seed allowlist", findings[0])

        self.write_spec("dddd9999", target="vault/tools/tropo-release.py")
        findings2, _c2, _v2 = check_fn(self.tmp)
        not_seeded = [f for f in findings2 if "dddd9999" in f]
        self.assertEqual(len(not_seeded), 1, findings2)
        self.assertIn("NOT on the f5790777 seed allowlist", not_seeded[0])


class TestRefusesWhenBlind(_ScratchStudio):
    """The enumeration has ONE declared source. If the check cannot read it,
    it must refuse — never report green over a subject it cannot see."""

    def _assert_refusal(self, findings, checked, violations) -> None:
        self.assertEqual(violations, 1, findings)
        self.assertEqual(checked, 0, findings)
        self.assertEqual(len(findings), 1, findings)
        self.assertTrue(findings[0].startswith("[ERROR]"), findings)
        self.assertIn("CANNOT RUN", findings[0])

    def test_refuses_when_markers_absent(self) -> None:
        self.write_capsule(FIXTURE_SURFACES, with_markers=False)
        # Plant a violator too: a silent pass here would be indistinguishable
        # from a clean vault, which is the failure being guarded against.
        self.write_spec("eeee1111", target="vault/tools/9e7003b1.py")
        self._assert_refusal(*check_fn(self.tmp))

    def test_refuses_when_enumeration_is_empty(self) -> None:
        self.write_capsule([])
        self.write_spec("eeee2222", target="vault/tools/9e7003b1.py")
        self._assert_refusal(*check_fn(self.tmp))

    def test_refuses_when_capsule_missing(self) -> None:
        (self.tmp / "vault" / "capsules" / "tropo-dev-spec.capsule.md").unlink()
        self.write_spec("eeee3333", target="vault/tools/9e7003b1.py")
        self._assert_refusal(*check_fn(self.tmp))

    def test_refuses_when_end_marker_absent(self) -> None:
        path = self.tmp / "vault" / "capsules" / "tropo-dev-spec.capsule.md"
        path.write_text(_capsule_body(FIXTURE_SURFACES).replace(END, ""), encoding="utf-8")
        self._assert_refusal(*check_fn(self.tmp))

    def test_parser_strips_blanks_and_comment_lines(self) -> None:
        self.write_capsule(["# a comment", "", "vault/tools/9e7003b1.py", "   "])
        surfaces, err = tropo_validate._parse_shared_lifecycle_surfaces(self.tmp)
        self.assertIsNone(err)
        self.assertEqual(surfaces, frozenset({"vault/tools/9e7003b1.py"}))


class TestShippedSubsetMode(_ScratchStudio):
    """Customer/release mode is a subset boundary, handled as the
    activation-coupling precedent handles it: INFO, zero tally."""

    def test_customer_mode_downgrades_and_does_not_fail_the_box(self) -> None:
        self.write_spec("ffff1111", target="vault/tools/9e7003b1.py")
        findings, checked, violations = check_fn(self.tmp, customer_mode=True)
        self.assertEqual((checked, violations), (1, 0), findings)
        self.assertTrue(all(f.startswith("[INFO]") for f in findings), findings)


class TestLiveCapsule(unittest.TestCase):
    """Read-only sanity check against the real studio. Skipped, not failed,
    while argus-a163's marker block is still landing."""

    def test_live_capsule_enumeration_is_readable(self) -> None:
        surfaces, err = tropo_validate._parse_shared_lifecycle_surfaces(ROOT)
        if err is not None:
            self.skipTest(f"live capsule enumeration not landed yet: {err}")
        self.assertGreater(len(surfaces), 0)
        self.assertTrue(
            all(isinstance(s, str) and s and not s.startswith("#") for s in surfaces),
            sorted(surfaces))


if __name__ == "__main__":
    unittest.main()
