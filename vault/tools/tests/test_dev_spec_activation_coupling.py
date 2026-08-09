#!/usr/bin/env python3
"""test_dev_spec_activation_coupling.py — adversarial gauntlet for the
Pipeline-Activation Coupling Gate (dev-spec 8f15f08d): validates
`check_dev_spec_activation_coupling` in `tropo-validate.py`.

Runs against an ISOLATED fixture vault (a fresh tempdir with a minimal
`vault/files/` tree) rather than the real ~5,800-entry studio vault, so the
ratchet-toggle behavior (AC-4) is deterministic and does not depend on
whatever off-pipeline debt the real vault happens to carry on a given day.
One test (`test_real_substrate_...`) deliberately runs against the REAL
vault to prove item 3's cure actually landed, per Argus's explicit
instruction to verify that before shipping the check.

"Test-done" = the CHECK FUNCTION runs against real planted fixtures and its
findings are asserted, not merely that code compiles. Per this dev-spec's
own acceptance criteria: "Proven by running tropo-validate.py against the
plant, not asserted."
"""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALIDATE_PATH = ROOT / "vault" / "tools" / "tropo-validate.py"

_spec = importlib.util.spec_from_file_location("tropo_validate_under_test_8f15f08d", str(VALIDATE_PATH))
tropo_validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tropo_validate)

check_fn = tropo_validate.check_dev_spec_activation_coupling
ALLOWLIST = tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST


def _write(vault_root: Path, uid: str, body: str) -> None:
    files_dir = vault_root / "vault" / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    (files_dir / f"{uid}.md").write_text(body, encoding="utf-8")


def _dev_spec(uid: str, status: str = "locked", build_status: str | None = None) -> str:
    bs_line = f"build_status: {build_status}\n" if build_status else ""
    return (
        "---\n"
        f"uid: {uid}\n"
        "type: dev-spec\n"
        f"status: {status}\n"
        f"{bs_line}"
        "title: \"test fixture\"\n"
        "---\n\n# fixture\n"
    )


def _activation(uid: str, dev_spec_uid: str, status: str = "active") -> str:
    return (
        "---\n"
        f"uid: {uid}\n"
        "type: activation\n"
        f"status: {status}\n"
        f"dev_spec_uid: {dev_spec_uid}\n"
        "title: \"test fixture activation\"\n"
        "---\n\n# fixture\n"
    )


class TestDevSpecActivationCoupling(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="dsac_fixture_"))
        (self.tmp / "vault" / "files").mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # AC-1: a planted dev-spec at status:locked with NO correlated activation is flagged;
    # a properly-activated one is not.
    def test_ac1_locked_no_activation_is_flagged(self) -> None:
        _write(self.tmp, "aaaa1111", _dev_spec("aaaa1111"))
        findings, checked, violations = check_fn(self.tmp)
        self.assertEqual(checked, 1)
        self.assertEqual(violations, 1)
        self.assertTrue(any("aaaa1111" in f for f in findings), findings)

    def test_ac1_activated_dev_spec_is_not_flagged(self) -> None:
        _write(self.tmp, "bbbb2222", _dev_spec("bbbb2222"))
        _write(self.tmp, "cccc3333", _activation("cccc3333", "bbbb2222", status="retired"))
        findings, checked, violations = check_fn(self.tmp)
        self.assertEqual(checked, 1)
        self.assertEqual(violations, 0)
        self.assertEqual(findings, [])

    # AC-2: authoring a correlated activation cures the SAME plant on the next run —
    # the gate is the presence of the correlation record, demonstrated by the run.
    def test_ac2_correlation_cures_on_next_run(self) -> None:
        _write(self.tmp, "dddd4444", _dev_spec("dddd4444"))
        _findings1, _checked1, violations1 = check_fn(self.tmp)
        self.assertEqual(violations1, 1)
        _write(self.tmp, "eeee5555", _activation("eeee5555", "dddd4444"))
        _findings2, _checked2, violations2 = check_fn(self.tmp)
        self.assertEqual(violations2, 0)

    # AC-3: the build_status arm escalates the finding's wording; correlation cures it too.
    def test_ac3_build_status_arm_is_escalated(self) -> None:
        _write(self.tmp, "ffff6666", _dev_spec("ffff6666", status="draft", build_status="mike-signed-accepted"))
        findings, checked, violations = check_fn(self.tmp)
        self.assertEqual(checked, 1)
        self.assertEqual(violations, 1)
        self.assertTrue(any("ESCALATED" in f and "mike-signed-accepted" in f for f in findings), findings)
        _write(self.tmp, "77778888", _activation("77778888", "ffff6666"))
        _findings2, _checked2, violations2 = check_fn(self.tmp)
        self.assertEqual(violations2, 0)

    def test_ac3_in_flight_build_status_does_not_escalate(self) -> None:
        # built_pending_verify is NOT in the terminal set — status:draft + this build_status
        # should not even trigger the rule (neither locked nor terminal).
        _write(self.tmp, "99990000", _dev_spec("99990000", status="draft", build_status="built_pending_verify"))
        findings, checked, violations = check_fn(self.tmp)
        self.assertEqual(checked, 0)
        self.assertEqual(violations, 0)
        self.assertEqual(findings, [])

    # AC-4: WARN when the allowlist is non-empty; ERROR once it's empty (the ratchet
    # condition). Both severities demonstrated against ONE plant by toggling the
    # module constant — per tropo-validate.py's check_dev_spec_activation_coupling
    # docstring, the ratchet is implemented as a STATIC gate on
    # DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST (deliberately NOT a live per-run
    # "is the vault clean" computation — that would be circular; see the docstring's
    # "Talos judgment call" for the full disclosure).
    #
    # UPDATED 2026-07-08 (Talos T26, register 2b12e41d / event 00005914): the
    # ALLOWLIST ratchet has now FIRED FOR REAL in the shipped module (both named
    # grandfather UIDs plus the 9-other-UID debt this docstring named are cured;
    # DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST == frozenset() in the live module).
    # This test no longer reads the real module's pre-cure/post-cure state as an
    # implicit fixture — it explicitly patches BOTH directions so it stays correct
    # regardless of the module's current shipped allowlist contents.
    def test_ac4_ratchet_toggles_warn_to_error(self) -> None:
        _write(self.tmp, "11112222", _dev_spec("11112222"))
        original_allowlist = tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST

        # Non-empty-allowlist state -> WARN.
        tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST = frozenset({"deadbeef"})
        try:
            findings_warn, _checked_w, violations_w = check_fn(self.tmp)
        finally:
            tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST = original_allowlist
        self.assertEqual(violations_w, 1)
        self.assertTrue(all(f.startswith("[WARN]") for f in findings_warn), findings_warn)

        # Empty-allowlist state (the ratchet-fired / now-shipped state) -> ERROR.
        tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST = frozenset()
        try:
            findings_error, _checked_e, violations_e = check_fn(self.tmp)
        finally:
            tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST = original_allowlist
        self.assertEqual(violations_e, 1)
        self.assertTrue(any(f.startswith("[ERROR]") for f in findings_error), findings_error)

        # Confirm the restore took — the module is back in its real shipped state
        # for every other test in this file.
        self.assertEqual(tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST, original_allowlist)

    # AC-5: a grandfathered UID (present in the allowlist) is flagged WARN, not
    # ERROR, and the wording discloses the grandfather cure path. UPDATED 2026-07-08
    # (Talos T26): the real shipped allowlist is now EMPTY (both named UIDs +
    # the 9-other-UID debt cured) — this test patches a non-empty allowlist
    # locally to exercise the grandfather-wording code path, which is otherwise
    # unreachable in the live (ratcheted) state. It no longer asserts the real
    # module's ALLOWLIST equals the old 2-UID set — that assertion belongs to
    # history, not to this behavioral test.
    def test_ac5_grandfathered_uid_is_warn_not_error(self) -> None:
        original_allowlist = tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST
        tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST = frozenset({"92093c81", "8e551957"})
        try:
            _write(self.tmp, "92093c81", _dev_spec("92093c81", build_status="mike-signed-accepted"))
            findings, _checked, violations = check_fn(self.tmp)
        finally:
            tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST = original_allowlist
        self.assertEqual(violations, 1)
        self.assertTrue(findings[0].startswith("[WARN]"), findings)
        self.assertIn("grandfathered per 8e8a0962", findings[0])

    def test_ac5_non_grandfathered_uid_wording_differs(self) -> None:
        _write(self.tmp, "abcdef01", _dev_spec("abcdef01"))
        findings, _checked, violations = check_fn(self.tmp)
        self.assertEqual(violations, 1)
        self.assertIn("NOT on the named grandfather allowlist", findings[0])

    def test_shipped_subset_downgrades_missing_source_activation(self) -> None:
        _write(self.tmp, "abcdef01", _dev_spec("abcdef01"))
        findings, checked, violations = check_fn(self.tmp, customer_mode=True)
        self.assertEqual(checked, 1)
        self.assertEqual(violations, 0)
        self.assertTrue(all(f.startswith("[INFO]") for f in findings), findings)

    # Integration sanity check against the REAL studio vault — confirms item 3's
    # feed-the-pipeline cure (activations 413db7f5 / 019c765a) actually correlates
    # against 92093c81 / 8e551957, per Argus's explicit instruction to verify this
    # BEFORE shipping/turning on the check.
    def test_real_substrate_92093c81_and_8e551957_are_cured(self) -> None:
        findings, _checked, _violations = check_fn(ROOT)
        flagged_uids = {
            uid for f in findings for uid in ("92093c81", "8e551957") if uid in f
        }
        self.assertNotIn("92093c81", flagged_uids, "v1.81 dev-spec still flagged off-pipeline after item-3 cure")
        self.assertNotIn("8e551957", flagged_uids, "v1.82 dev-spec still flagged off-pipeline after item-3 cure")


if __name__ == "__main__":
    unittest.main()
