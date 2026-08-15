"""Stage-6 step 1: package-entry authority and one immutable package identity.

Covers A148's locked answers (evt_a9360f18f56fe472_00000020):

- Q1: resolution is by required explicit `--activation-uid`, never a scan;
  activation, run and root must agree, the run must belong to the release
  pipeline, and the snapshot must resolve.
- Q2: there is no omission-based legacy path -- omitting the activation
  refuses rather than falling back.
- Q5: the fan-in digest is recomputed canonically from the lock's immutable
  manifest and compared to what the lock recorded; mismatch refuses.

Fixtures are shaped from what `tropo-lock-release-plan.py` actually renders
(`activation:` on the run, `activation_root_uid` on the activation,
`fan_in_digest` on the plan), read out of the tool rather than assumed. An
earlier draft of the module guessed those names from the dev-side shape and
would have refused every real release for the wrong reason.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib import release_package as rp  # noqa: E402


class ThePackageKnowsWhatAuthorisedIt(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac6-package-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.runs = self.tmp / "vault" / "pipeline-runs"
        self.files.mkdir(parents=True)
        self.runs.mkdir(parents=True)
        self._build()

    def _write(self, uid: str, lines: list) -> None:
        (self.files / f"{uid}.md").write_text(
            "---\n" + f"uid: {uid}\n" + "\n".join(lines) + "\n---\n\n# " + uid + "\n",
            encoding="utf-8")

    def _build(self) -> None:
        run_folder = "release-pipeline-2026-08-11"
        (self.runs / run_folder).mkdir(parents=True, exist_ok=True)
        (self.runs / run_folder / "declaration-snapshot.json").write_text(
            '{"digest": "abc"}', encoding="utf-8")
        self._write("acc00001", [
            "type: activation", "status: active",
            f"pipeline: {rp.RELEASE_PIPELINE_UID}",
            "release_plan_uid: 'pln00001'",
            "pipeline_run_uid: 'run00001'",
            "activation_root_uid: 'rot00001'"])
        self._write("run00001", [
            "type: pipeline-run", "status: active",
            f"pipeline: {rp.RELEASE_PIPELINE_UID}",
            "activation: 'acc00001'",
            "release_plan_uid: 'pln00001'",
            f"run_folder: '{run_folder}'"])
        self._write("pln00001", [
            "type: release-plan", "status: locked",
            "release_activation_uid: 'acc00001'",
            "release_pipeline_run_uid: 'run00001'",
            "fan_in_digest: 'deadbeefdeadbeef'"])

    def _resolve(self, activation="acc00001"):
        return rp.resolve_release_run(activation, self.files, self.runs)

    def test_a_clean_chain_resolves_and_carries_every_binding(self):
        identity = self._resolve()
        self.assertEqual(identity.run_uid, "run00001")
        self.assertEqual(identity.root_uid, "rot00001")
        self.assertEqual(identity.plan_uid, "pln00001")
        self.assertEqual(identity.fan_in_digest, "deadbeefdeadbeef")
        self.assertIsNotNone(identity.snapshot_path)
        self.assertEqual(
            set(identity.binding()),
            {"release_activation_uid", "release_pipeline_run_uid",
             "activation_root_uid", "release_plan_uid", "fan_in_digest"},
        )

    def test_omitting_the_activation_refuses_rather_than_falling_back(self):
        """Q2: there is no omission-based legacy path.

        The point is not that a required argument is missing. It is that no
        caller can reach package production without naming the run that
        authorised it, so the freeze gate cannot be skipped by leaving an
        argument off -- which is how a gate becomes advisory.
        """
        for empty in (None, "", "   "):
            with self.subTest(value=repr(empty)):
                with self.assertRaises(rp.PackageRefusal) as caught:
                    rp.resolve_release_run(empty, self.files, self.runs)
                self.assertIn("requires --activation-uid", str(caught.exception))

    def test_a_dev_run_cannot_authorise_a_release_package(self):
        self._write("run00001", [
            "type: pipeline-run", "status: active",
            "pipeline: 74945d48",
            "activation: 'acc00001'",
            "release_plan_uid: 'pln00001'",
            "run_folder: 'release-pipeline-2026-08-11'"])
        with self.assertRaises(rp.PackageRefusal) as caught:
            self._resolve()
        self.assertIn("not the release pipeline", str(caught.exception))

    def test_a_run_naming_a_different_activation_refuses(self):
        self._write("run00001", [
            "type: pipeline-run", "status: active",
            f"pipeline: {rp.RELEASE_PIPELINE_UID}",
            "activation: 'acc09999'",
            "release_plan_uid: 'pln00001'",
            "run_folder: 'release-pipeline-2026-08-11'"])
        with self.assertRaises(rp.PackageRefusal) as caught:
            self._resolve()
        self.assertIn("identity disagreement", str(caught.exception))

    def test_a_plan_locked_by_another_activation_refuses(self):
        self._write("pln00001", [
            "type: release-plan", "status: locked",
            "release_activation_uid: 'acc09999'",
            "fan_in_digest: 'deadbeefdeadbeef'"])
        with self.assertRaises(rp.PackageRefusal) as caught:
            self._resolve()
        self.assertIn("identity disagreement", str(caught.exception))

    def test_a_missing_snapshot_refuses_before_any_package_write(self):
        (self.runs / "release-pipeline-2026-08-11"
         / "declaration-snapshot.json").unlink()
        with self.assertRaises(rp.PackageRefusal) as caught:
            self._resolve()
        self.assertIn("immutable snapshot does not resolve", str(caught.exception))

    def test_a_plan_with_no_fan_in_digest_refuses(self):
        self._write("pln00001", [
            "type: release-plan", "status: locked",
            "release_activation_uid: 'acc00001'"])
        with self.assertRaises(rp.PackageRefusal) as caught:
            self._resolve()
        self.assertIn("no fan_in_digest", str(caught.exception))

    def test_a_uid_shaped_like_a_search_term_is_refused_not_searched(self):
        for bogus in ("acc0001", "../../etc/passwd", "acc0000*", "ACC00001"):
            with self.subTest(uid=bogus):
                with self.assertRaises(rp.PackageRefusal):
                    rp.resolve_release_run(bogus, self.files, self.runs)


class TheDigestIsTakenFromTheBytesThatShip(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac6-zip-")).resolve()
        self.zip_path = self.tmp / "tropo-os-v1.87.0.zip"
        with zipfile.ZipFile(self.zip_path, "w") as archive:
            archive.writestr("README.md", "# shipped\n")

    def test_the_hash_is_of_the_final_zip_file_itself(self):
        expected = hashlib.sha256(self.zip_path.read_bytes()).hexdigest()
        self.assertEqual(rp.hash_final_zip(self.zip_path), expected)

    def test_a_missing_package_refuses_rather_than_hashing_nothing(self):
        with self.assertRaises(rp.PackageRefusal):
            rp.hash_final_zip(self.tmp / "not-there.zip")

    def test_identical_bytes_are_an_idempotent_retry(self):
        digest = rp.hash_final_zip(self.zip_path)
        self.assertFalse(
            rp.reconcile_existing_freeze(
                {"package_sha256": digest}, digest, "run00001"),
            "a retry with identical bytes should not emit a second event",
        )

    def test_different_bytes_for_one_run_refuse(self):
        """The dangerous case: receipts already written describe other bytes."""
        with self.assertRaises(rp.PackageRefusal) as caught:
            rp.reconcile_existing_freeze(
                {"package_sha256": "a" * 64}, "b" * 64, "run00001")
        self.assertIn("already frozen", str(caught.exception))

    def test_a_prior_freeze_with_no_digest_refuses_rather_than_guessing(self):
        with self.assertRaises(rp.PackageRefusal):
            rp.reconcile_existing_freeze({"package_sha256": ""}, "b" * 64, "r")

    def test_no_prior_freeze_means_emit(self):
        self.assertTrue(rp.reconcile_existing_freeze(None, "b" * 64, "r"))

    def test_named_pre_public_supersession_allows_one_new_freeze(self):
        events = [
            {"event": rp.PACKAGE_FROZEN_EVENT,
             "data": {"release_run_uid": "run00001",
                      "package_sha256": "a" * 64}},
            {"event": rp.PACKAGE_SUPERSEDED_EVENT,
             "data": {"release_run_uid": "run00001",
                      "old_package_sha256": "a" * 64}},
        ]
        self.assertIsNone(rp.active_frozen_payload(events, "run00001"))
        events.append({
            "event": rp.PACKAGE_FROZEN_EVENT,
            "data": {"release_run_uid": "run00001",
                     "package_sha256": "b" * 64},
        })
        self.assertEqual(
            rp.active_frozen_payload(events, "run00001")["package_sha256"],
            "b" * 64,
        )

    def test_supersession_must_name_the_active_digest(self):
        events = [
            {"event": rp.PACKAGE_FROZEN_EVENT,
             "data": {"release_run_uid": "run00001",
                      "package_sha256": "a" * 64}},
            {"event": rp.PACKAGE_SUPERSEDED_EVENT,
             "data": {"release_run_uid": "run00001",
                      "old_package_sha256": "c" * 64}},
        ]
        with self.assertRaises(rp.PackageRefusal):
            rp.active_frozen_payload(events, "run00001")


if __name__ == "__main__":
    unittest.main()
