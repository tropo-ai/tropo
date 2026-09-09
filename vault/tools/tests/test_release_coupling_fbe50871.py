"""Plant suite for Release Coupling (dev-spec fbe50871, Mike-locked 2026-07-13).

Committed test seams throughout: a scratch bare repo standing in for the GitHub
remote (--remote/--clone), a scratch build directory standing in for
tropo-build-release.py's output, and a scratch --clone-dir for the staged clone.
Never touches the real vault/events, vault/files, .tropo/version.md, or any real
GitHub remote. The real `gh` leg (AC-12) is stated honestly as untestable here —
only v1.85.0 production proves it (per the spec's own "Honest Limits" section).

Self-running (python3 test_release_coupling_fbe50871.py) and pytest-compatible.
"""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_VAULT_TOOLS = Path(__file__).resolve().parent.parent
_TROPO_SCRIPTS = Path(__file__).resolve().parents[3] / ".tropo" / "scripts"
sys.path.insert(0, str(_TROPO_SCRIPTS))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


relauth = _load("relauth_fbe50871", _TROPO_SCRIPTS / "lib" / "release_authorization.py")
cps = _load("cps_fbe50871", _VAULT_TOOLS / "tropo-check-publish-state.py")
pub = _load("pub_fbe50871", _VAULT_TOOLS / "tropo-publish-release.py")
build = _load("build_fbe50871", _VAULT_TOOLS / "tropo-build-release.py")
verlive = _load("verlive_fbe50871", _VAULT_TOOLS / "tropo-verify-release-live.py")


def _named_release_fixture(publisher, root, activation_uid="deadbeef"):
    """Real named resolver inputs, shared by caller fixtures (never the live index)."""
    files = root / "vault/files"
    files.mkdir(parents=True, exist_ok=True)
    run = root / "vault/pipeline-runs/b0000001"
    run.mkdir(parents=True, exist_ok=True)
    entries = {
        activation_uid: {"type": "activation", "pipeline_run_uid": "b0000001",
                         "activation_root_uid": "d0000001"},
        "b0000001": {"activation": activation_uid,
                      "pipeline": publisher.release_package.RELEASE_PIPELINE_UID,
                      "release_plan_uid": "c0000001",
                      "run_folder": "vault/pipeline-runs/b0000001"},
        "c0000001": {"release_activation_uid": activation_uid,
                      "fan_in_digest": "d" * 64},
    }
    for uid, fields in entries.items():
        (files / (uid + ".md")).write_text(
            "---\n" + "\n".join(f"{key}: {value}" for key, value in fields.items()) + "\n---\n")
    (run / "declaration-snapshot.json").write_text("{}\n")
    identity = publisher.release_package.resolve_release_run(
        activation_uid, files, root / "vault/pipeline-runs")
    return run, identity


class TestPrivateBuildRetryHonesty(unittest.TestCase):
    def test_target_newer_than_in_sync_studio_is_not_labeled_live(self):
        provenance = build.target_publish_state_provenance(
            {
                "publish_state": "LIVE",
                "internal_version": "1.84.1",
                "latest_published": "1.84.1",
            },
            "1.85.0",
        )
        self.assertEqual(provenance["publish_state"], "STAGED_OR_UNPUBLISHED")
        self.assertEqual(provenance["preflight_publish_state"], "LIVE")

    def test_retry_starts_from_clean_generated_trees_and_zip(self):
        with tempfile.TemporaryDirectory() as td:
            release_root = Path(td)
            product = "tropo-os-v1.85.0"
            build_dir = release_root / "v1.85.0" / "builds" / product
            testing_dir = release_root / "v1.85.0" / "testing" / product
            dist_dir = release_root / "v1.85.0" / "dist"
            for directory in (build_dir, testing_dir, dist_dir):
                directory.mkdir(parents=True)
            (build_dir / "stale-from-partial-build.txt").write_text("stale")
            (testing_dir / "stale-from-prior-walk.txt").write_text("stale")
            (dist_dir / f"{product}.zip").write_bytes(b"stale zip")

            with (
                patch.object(build.tropo_roots, "RELEASES_DIR", release_root),
                patch.object(build, "DRY_RUN", False),
                patch.object(build, "guard_overwrite"),
            ):
                actual = build.step_2_create_output("1.85.0")

            self.assertEqual(tuple(map(Path, actual)), (build_dir, testing_dir, dist_dir))
            self.assertTrue(build_dir.is_dir())
            self.assertTrue(testing_dir.is_dir())
            self.assertFalse((build_dir / "stale-from-partial-build.txt").exists())
            self.assertFalse((testing_dir / "stale-from-prior-walk.txt").exists())
            self.assertFalse((dist_dir / f"{product}.zip").exists())


# ─── T-1: the BREAKS fix — widened post-mint allowlist ────────────────────────

class TestAllowlistWidening(unittest.TestCase):
    """The gauntlet's own empirical repro (Argus A130, event 00006328): the
    ORIGINAL 2-shape allowlist refused the engine's own real ceremony. These
    are the exact event shapes from vault/pipeline-runs/dev-pipeline-896e6c9b-
    2026-07-02 (events 73-91) — real run-declared downstream steps that must
    now be allowed, plus forged shapes that must still refuse."""

    def test_real_ceremony_events_allowed(self):
        real_events = [
            {"event": "step_completed", "step": "8654900a", "data": {"natural_verdict": "pass"}},
            {"event": "pause_started", "step": None, "data": {"step": "bc6b17ec"}},
            {"event": "human_signoff", "step": "bc6b17ec", "data": {"verdict": "accepted"}},
            {"event": "pause_resumed", "step": "bc6b17ec", "data": {}},
            {"event": "step_started", "step": "bc6b17ec", "data": {}},
            {"event": "step_completed", "step": "bc6b17ec", "data": {}},
            {"event": "verification_receipt", "step": "bc6b17ec", "data": {"verdict": "pass"}},
            {"event": "step_started", "step": "c6b61fb9", "data": {}},
            {"event": "step_completed", "step": "c6b61fb9", "data": {}},
            {"event": "verification_receipt", "step": "c6b61fb9", "data": {"verdict": "fail"}},
            {"event": "step_started", "step": "3e0bb81e", "data": {}},
            {"event": "step_completed", "step": "3e0bb81e", "data": {}},
            {"event": "workflow_complete", "step": None, "data": {}},
        ]
        for ev in real_events:
            with self.subTest(event=ev["event"], step=ev.get("step")):
                self.assertTrue(relauth._post_mint_event_allowed(ev),
                                 f"real ceremony event wrongly refused: {ev}")

    def test_forged_events_still_refuse(self):
        forged = [
            {"event": "step_completed", "step": "deadbeef", "data": {}},   # non-existent step uid
            {"event": "verification_receipt", "step": "notreal1", "data": {}},  # not 8-hex
            {"event": "totally_made_up_event", "step": "bc6b17ec", "data": {}},  # not engine vocab
            {"event": "run_created", "step": None, "data": {}},   # bootstrap-only
            {"event": "step_declared", "step": "bc6b17ec", "data": {}},  # declaration-only
        ]
        for ev in forged:
            with self.subTest(event=ev["event"], step=ev.get("step")):
                self.assertFalse(relauth._post_mint_event_allowed(ev),
                                  f"forged event wrongly allowed: {ev}")

    def test_real_ceremony_step_uids_resolve_to_real_pipeline_entries(self):
        """The whitelist's actual security property: a step_uid must resolve to
        a real type:pipeline vault entry, not just look like one."""
        for step_uid in ("bc6b17ec", "c6b61fb9", "3e0bb81e", "8654900a"):
            fm = relauth._load_fm(relauth.VAULT_FILES / f"{step_uid}.md")
            self.assertIsNotNone(fm, f"{step_uid} should resolve to a real vault entry")
            self.assertEqual(fm.get("type"), "pipeline")


# ─── T-2: check-publish-state.py amendments ───────────────────────────────────

class TestCheckPublishState(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cps-fbe50871-")).resolve()
        self.bare = self.tmp / "bare.git"
        work = self.tmp / "work"
        self.work = work
        subprocess.run(["git", "init", "--bare", "-q", str(self.bare)], check=True)
        # Fixture fix (surfaced when rsync became available in CI — this bare repo's HEAD
        # defaults to refs/heads/master on environments without init.defaultBranch=main
        # configured; every seed/work commit below pushes to "main" instead, so an
        # unpatched HEAD would leave a later `git clone` with an empty working tree
        # (git warns "remote HEAD refers to nonexistent ref, unable to checkout").
        subprocess.run(["git", "-C", str(self.bare), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.email", "t@t.com"], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.name", "T"], check=True)
        subprocess.run(["git", "-C", str(work), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        subprocess.run(["git", "-C", str(work), "branch", "-M", "main"], check=True)
        subprocess.run(["git", "-C", str(work), "tag", "v1.0.0"], check=True)
        subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(self.bare)], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "main", "--tags"], check=True)
        self.main_sha = subprocess.run(["git", "-C", str(work), "rev-parse", "main"],
                                        capture_output=True, text=True).stdout.strip()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _args(self, **overrides):
        base = dict(json=True, remote=str(self.bare), clone=None, expect=None, sha=None)
        base.update(overrides)
        return types.SimpleNamespace(**base)

    def test_expect_verifies_tag_present(self):
        rc = cps.cmd_expect(self._args(expect="1.0.0"), str(self.bare))
        self.assertEqual(rc, 0)

    def test_expect_with_correct_sha_verifies(self):
        rc = cps.cmd_expect(self._args(expect="1.0.0", sha=self.main_sha), str(self.bare))
        self.assertEqual(rc, 0)

    def test_expect_with_wrong_sha_fails(self):
        rc = cps.cmd_expect(self._args(expect="1.0.0", sha="f" * 40), str(self.bare))
        self.assertEqual(rc, 1)

    def test_expect_rejects_tag_target_that_differs_from_main(self):
        subprocess.run(
            ["git", "-C", str(self.work), "commit", "-q", "--allow-empty", "-m", "main moved"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.work), "push", "-q", "origin", "main"],
            check=True,
        )
        rc = cps.cmd_expect(self._args(expect="1.0.0"), str(self.bare))
        self.assertEqual(rc, 1)

    def test_expect_peels_annotated_tag_to_commit(self):
        subprocess.run(
            [
                "git",
                "-C",
                str(self.work),
                "tag",
                "-a",
                "v1.0.1",
                "-m",
                "annotated",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.work), "push", "-q", "origin", "v1.0.1"],
            check=True,
        )
        rc = cps.cmd_expect(
            self._args(expect="1.0.1", sha=self.main_sha),
            str(self.bare),
        )
        self.assertEqual(rc, 0)

    def test_expect_missing_tag_fails(self):
        rc = cps.cmd_expect(self._args(expect="9.9.9"), str(self.bare))
        self.assertEqual(rc, 1)

    def test_unreachable_remote_exits_2(self):
        rc = cps.cmd_expect(self._args(expect="1.0.0"), str(self.tmp / "nonexistent"))
        self.assertEqual(rc, 2)

    def test_unknown_version_md_exits_2(self):
        empty_root = self.tmp / "empty-studio"
        empty_root.mkdir()
        rc = cps.cmd_status(self._args(), str(self.bare), root=empty_root)
        self.assertEqual(rc, 2)

    def test_dual_format_version_parsing(self):
        bare_fmt = self.tmp / "bare-fmt.md"
        bare_fmt.write_text("v2.5.0\n")
        self.assertEqual(cps.internal_version(self.tmp, bare_fmt), "2.5.0")
        fm_fmt = self.tmp / "fm-fmt.md"
        fm_fmt.write_text('---\nversion: "3.1.4"\n---\n\n# Tropo-OS v3.1.4\n')
        self.assertEqual(cps.internal_version(self.tmp, fm_fmt), "3.1.4")
        garbage = self.tmp / "garbage.md"
        garbage.write_text("not a version")
        self.assertEqual(cps.internal_version(self.tmp, garbage), "UNKNOWN")


# ─── T-3: tropo-publish-release.py safety-critical properties ─────────────────

class TestPublishReleaseStage(unittest.TestCase):
    """STAGE + the physical edge guard + idempotent re-entry + the deletion
    refusal. gh-dependent legs (release-object creation, verify-live's gh
    check) are out of scope here — see the spec's own Honest Limits (AC-12)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pub-fbe50871-")).resolve()
        self.bare = self.tmp / "bare.git"
        self.release_dir = self.tmp / "releases" / "v9.9.9"
        self.build_dir = (
            self.release_dir / "builds" / "tropo-os-v9.9.9"
        )
        self.clone_dir = self.tmp / "staged-clone"
        self.studio_root = self.tmp / "fake-studio"

        subprocess.run(["git", "init", "--bare", "-q", str(self.bare)], check=True)
        # See TestCheckPublishState.setUp for why this is required (empty-checkout fixture bug).
        subprocess.run(["git", "-C", str(self.bare), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
        seed = self.tmp / "seed"
        subprocess.run(["git", "init", "-q", str(seed)], check=True)
        subprocess.run(["git", "-C", str(seed), "config", "user.email", "t@t.com"], check=True)
        subprocess.run(["git", "-C", str(seed), "config", "user.name", "T"], check=True)
        (seed / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [9.9.8]\n- old\n")
        subprocess.run(["git", "-C", str(seed), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(seed), "commit", "-q", "-m", "seed"], check=True)
        subprocess.run(["git", "-C", str(seed), "branch", "-M", "main"], check=True)
        subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(self.bare)], check=True)
        subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "main"], check=True)

        self.build_dir.mkdir(parents=True)
        (self.build_dir / "CHANGELOG.md").write_text(
            "## [Unreleased]\n\n## [9.9.9]\n- new stuff\n\n## [9.9.8]\n- old\n")
        (self.build_dir / "README.md").write_text("# Tropo-OS v9.9.9\n")
        (self.release_dir / "dist").mkdir()
        (self.release_dir / "dist" / "tropo-os-v9.9.9.zip").write_bytes(b"PK\x03\x04fake")
        (self.release_dir / "cold-walk-verdict.json").write_text(
            json.dumps({"release_version": "9.9.9", "overall": "PASS"})
        )

        self.studio_root.mkdir(parents=True)
        (self.studio_root / "CHANGELOG.md").write_text(
            "## [Unreleased]\n\n## [9.9.9]\n- new stuff\n\n## [9.9.8]\n- old\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patches(self):
        return (
            patch.object(pub.tropo_roots, "STUDIO_ROOT", self.studio_root),
            patch.object(pub.tropo_roots, "RELEASES_DIR", self.tmp / "releases"),
            patch.object(pub, "require_release_authorization", lambda *a, **k: {"fingerprint": "fake"}),
            patch.object(pub, "DEFAULT_REMOTE", str(self.bare)),
        )

    def _stage_args(self, **overrides):
        base = dict(activation_uid="deadbeef", version="9.9.9", remote=str(self.bare),
                     clone=None, clone_dir=str(self.clone_dir), allow_delete=False)
        base.update(overrides)
        return types.SimpleNamespace(**base)

    def test_stage_happy_path_writes_state(self):
        p1, p2, p3, p4 = self._patches()
        with p1, p2, p3, p4:
            rc = pub.cmd_stage(self._stage_args())
        self.assertEqual(rc, 0)
        state = json.loads((self.tmp / "releases" / "v9.9.9" / "publish-state.json").read_text())
        self.assertEqual(state["tag"], "v9.9.9")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{40}", state["staged_sha"]))

    def test_push_url_physically_disabled_after_stage(self):
        p1, p2, p3, p4 = self._patches()
        with p1, p2, p3, p4:
            pub.cmd_stage(self._stage_args())
        push_url = subprocess.run(["git", "remote", "get-url", "--push", "origin"],
                                   cwd=str(self.clone_dir), capture_output=True, text=True).stdout.strip()
        self.assertEqual(push_url, "DISABLED")
        stray = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=str(self.clone_dir),
                                capture_output=True, text=True)
        self.assertNotEqual(stray.returncode, 0, "a stray push from the staged clone must fail")

    def test_stage_idempotent_on_clean_reentry(self):
        p1, p2, p3, p4 = self._patches()
        with p1, p2, p3, p4:
            pub.cmd_stage(self._stage_args())
            sha_before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.clone_dir),
                                         capture_output=True, text=True).stdout.strip()
            rc2 = pub.cmd_stage(self._stage_args())
            sha_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.clone_dir),
                                        capture_output=True, text=True).stdout.strip()
        self.assertEqual(rc2, 0)
        self.assertEqual(sha_before, sha_after, "idempotent re-entry must not create a new commit")

    def test_stage_refuses_non_allowlisted_deletion(self):
        bare2 = self.tmp / "bare2.git"
        seed2 = self.tmp / "seed2"
        subprocess.run(["git", "init", "--bare", "-q", str(bare2)], check=True)
        # See TestCheckPublishState.setUp for why this is required (empty-checkout fixture bug).
        subprocess.run(["git", "-C", str(bare2), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
        subprocess.run(["git", "init", "-q", str(seed2)], check=True)
        subprocess.run(["git", "-C", str(seed2), "config", "user.email", "t@t.com"], check=True)
        subprocess.run(["git", "-C", str(seed2), "config", "user.name", "T"], check=True)
        (seed2 / "CHANGELOG.md").write_text("old\n")
        (seed2 / "will-be-deleted.txt").write_text("should survive unless acknowledged\n")
        subprocess.run(["git", "-C", str(seed2), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(seed2), "commit", "-q", "-m", "seed2"], check=True)
        subprocess.run(["git", "-C", str(seed2), "branch", "-M", "main"], check=True)
        subprocess.run(["git", "-C", str(seed2), "remote", "add", "origin", str(bare2)], check=True)
        subprocess.run(["git", "-C", str(seed2), "push", "-q", "origin", "main"], check=True)

        release2 = self.tmp / "releases" / "v9.9.10"
        build2 = release2 / "builds" / "tropo-os-v9.9.10"
        build2.mkdir(parents=True)
        (build2 / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [9.9.10]\n- x\n")
        (release2 / "cold-walk-verdict.json").write_text(
            json.dumps({"release_version": "9.9.10", "overall": "PASS"})
        )
        (self.studio_root / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [9.9.10]\n- x\n")

        p1, p2, p3, p4 = self._patches()
        with p1, p2, p3, p4, patch.object(pub, "DEFAULT_REMOTE", str(bare2)):
            rc = pub.cmd_stage(self._stage_args(
                version="9.9.10", remote=str(bare2), clone_dir=str(self.tmp / "staged-clone-2")))
        self.assertNotEqual(rc, 0, "stage must refuse an unacknowledged non-allowlisted deletion")

    def test_changelog_divergence_refuses(self):
        (self.studio_root / "CHANGELOG.md").write_text(
            "## [Unreleased]\n\n## [9.9.9]\n- DIFFERENT stuff than the box\n\n## [9.9.8]\n- old\n")
        p1, p2, p3, p4 = self._patches()
        with p1, p2, p3, p4:
            with self.assertRaises(pub.PublishError):
                pub.cmd_stage(self._stage_args())


class TestPublishReleaseFireAndDeferGates(unittest.TestCase):
    """--fire / --defer's TTY-only default-NO discipline and STALE-STAGE
    detection -- the safety properties provable without a live `gh`/GitHub leg."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pub-firegates-")).resolve()
        self.bare = self.tmp / "bare.git"
        self.release_dir = self.tmp / "releases" / "v9.9.9"
        self.build_dir = (
            self.release_dir / "builds" / "tropo-os-v9.9.9"
        )
        self.clone_dir = self.tmp / "staged-clone"
        self.studio_root = self.tmp / "fake-studio"

        subprocess.run(["git", "init", "--bare", "-q", str(self.bare)], check=True)
        # See TestCheckPublishState.setUp for why this is required (empty-checkout fixture bug).
        subprocess.run(["git", "-C", str(self.bare), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
        seed = self.tmp / "seed"
        subprocess.run(["git", "init", "-q", str(seed)], check=True)
        subprocess.run(["git", "-C", str(seed), "config", "user.email", "t@t.com"], check=True)
        subprocess.run(["git", "-C", str(seed), "config", "user.name", "T"], check=True)
        (seed / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [9.9.8]\n- old\n")
        subprocess.run(["git", "-C", str(seed), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(seed), "commit", "-q", "-m", "seed"], check=True)
        subprocess.run(["git", "-C", str(seed), "branch", "-M", "main"], check=True)
        subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(self.bare)], check=True)
        subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "main"], check=True)

        self.build_dir.mkdir(parents=True)
        (self.build_dir / "CHANGELOG.md").write_text(
            "## [Unreleased]\n\n## [9.9.9]\n- new stuff\n\n## [9.9.8]\n- old\n")
        (self.release_dir / "cold-walk-verdict.json").write_text(
            json.dumps({"release_version": "9.9.9", "overall": "PASS"})
        )
        self.studio_root.mkdir(parents=True)
        (self.studio_root / "CHANGELOG.md").write_text(
            "## [Unreleased]\n\n## [9.9.9]\n- new stuff\n\n## [9.9.8]\n- old\n")

        with patch.object(pub.tropo_roots, "STUDIO_ROOT", self.studio_root), \
             patch.object(pub.tropo_roots, "RELEASES_DIR", self.tmp / "releases"), \
             patch.object(pub, "DEFAULT_REMOTE", str(self.bare)), \
             patch.object(pub, "require_release_authorization", lambda *a, **k: {"fingerprint": "fake"}):
            pub.cmd_stage(types.SimpleNamespace(
                activation_uid="deadbeef", version="9.9.9", remote=str(self.bare),
                clone=None, clone_dir=str(self.clone_dir), allow_delete=False))

        self.fixture_stack = contextlib.ExitStack()
        self.addCleanup(self.fixture_stack.close)
        self.fixture_stack.enter_context(patch.multiple(
            pub.tropo_roots, STUDIO_ROOT=self.studio_root,
            VAULT_DIR=self.studio_root / "vault", RELEASES_DIR=self.tmp / "releases"))
        self.run_dir, self.identity = _named_release_fixture(pub, self.studio_root)
        self.fixture_stack.enter_context(patch.object(
            pub, "_run_journal_folder", return_value=self.run_dir))
        zip_path = self.release_dir / "dist/tropo-os-v9.9.9.zip"
        zip_path.parent.mkdir()
        zip_path.write_bytes(b"verified fixture package")
        self.ac7 = {"identity": self.identity,
                    "package_sha256": pub.release_package.hash_final_zip(zip_path), "receipts": {}}
        self.fixture_stack.enter_context(patch.object(pub, "require_ac7_receipt_set", return_value=self.ac7))
        self.fixture_stack.enter_context(patch.object(pub, "_release_entry_uid_for", return_value="e0000001"))
        self.fixture_stack.enter_context(patch.object(pub, "_verify_live_module", return_value=verlive))
        # Keep the actual staged-state verifier: stale HEAD is this suite's
        # subject. Other gate legs belong to their own isolated adapter suites.
        real_verifiers = pub._pre_outward_fire_verifiers
        def fixture_verifiers(gates):
            checks = real_verifiers(gates)
            return {key: check if key == "fire-staged-state" else
                    (lambda ctx, key=key: gates.GateOutcome(key, gates.VERDICT_PASS, "fixture boundary"))
                    for key, check in checks.items()}
        self.fixture_stack.enter_context(patch.object(pub, "_pre_outward_fire_verifiers", side_effect=fixture_verifiers))
        self.fixture_stack.enter_context(patch.object(pub.urllib.request, "urlopen", side_effect=AssertionError("unexpected network")))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fire_refuses_without_tty(self):
        with patch.object(pub.tropo_roots, "STUDIO_ROOT", self.studio_root), \
             patch.object(pub.tropo_roots, "RELEASES_DIR", self.tmp / "releases"), \
             patch.object(pub, "DEFAULT_REMOTE", str(self.bare)), \
             patch.object(pub, "require_release_authorization", lambda *a, **k: {"fingerprint": "fake"}), \
             patch.object(sys.stdin, "isatty", lambda: False), \
             patch.object(pub, "_confirm_tty", wraps=pub._confirm_tty) as confirm:
            rc = pub.cmd_fire(types.SimpleNamespace(activation_uid="deadbeef", version="9.9.9"))
        self.assertEqual(rc, 6)
        confirm.assert_called_once()

    def test_fire_refuses_on_stale_stage(self):
        (self.clone_dir / "extra.txt").write_text("drift\n")
        subprocess.run(["git", "-C", str(self.clone_dir), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.clone_dir), "-c", "user.email=t@t.com",
                         "-c", "user.name=T", "commit", "-q", "-m", "drift"], check=True)
        with patch.object(pub.tropo_roots, "STUDIO_ROOT", self.studio_root), \
             patch.object(pub.tropo_roots, "RELEASES_DIR", self.tmp / "releases"), \
             patch.object(pub, "DEFAULT_REMOTE", str(self.bare)), \
             patch.object(pub, "require_release_authorization", lambda *a, **k: {"fingerprint": "fake"}), \
             patch.object(pub, "_confirm_tty", side_effect=AssertionError("stale stage reached confirm")), \
             contextlib.redirect_stdout(out := io.StringIO()):
            rc = pub.cmd_fire(types.SimpleNamespace(activation_uid="deadbeef", version="9.9.9"))
        self.assertNotEqual(rc, 0)
        self.assertIn("STALE-STAGE", out.getvalue())

    def test_defer_requires_reason(self):
        rc = pub.cmd_defer(types.SimpleNamespace(activation_uid="deadbeef", version="9.9.9", reason=None))
        self.assertNotEqual(rc, 0)

    def test_defer_refuses_without_tty(self):
        with patch.object(sys.stdin, "isatty", lambda: False):
            rc = pub.cmd_defer(types.SimpleNamespace(activation_uid="deadbeef", version="9.9.9", reason="testing"))
        self.assertNotEqual(rc, 0)

    def _marker(self, version, state="not-staged"):
        marker = self.studio_root / ".tropo" / "publish-pending.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"version": version, "publish_state": state,
                                      "written_by": "tropo-build-release.py step_11_zip_and_upload",
                                      "cure": "stage; then preflight + fire, or defer"}))
        return marker

    def _defer(self, version="9.9.9"):
        with patch.object(pub.tropo_roots, "STUDIO_ROOT", self.studio_root), \
             patch.object(pub, "_stamp_release_entry", lambda *a, **k: None), \
             patch.object(pub, "_confirm_tty", lambda prompt: True):
            return pub.cmd_defer(types.SimpleNamespace(activation_uid="deadbeef", version=version, reason="testing"))

    def test_defer_flips_the_marker_to_deferred_by_mike(self):
        # 2026-09-05: cmd_defer stamped the release entry and left the marker at
        # not-staged, so every boot nagged about a release Mike had deferred.
        # Mutation clause: drop the defer_publish_pending call from cmd_defer
        # and this fails on publish_state.
        marker = self._marker("9.9.9")
        self.assertEqual(self._defer(), 0)
        body = json.loads(marker.read_text())
        self.assertEqual(body["publish_state"], "deferred-by-mike")
        self.assertEqual(body["defer_record"]["reason"], "testing")
        self.assertNotIn("cure", body)
        self.assertIn("deferred_at", body)

    def test_defer_leaves_another_versions_marker_loud(self):
        """f015ebc247ce AC4: rewritten. The marker was `not-staged` here until
        2026-09-07 -- NOT a silent state -- so this could never exercise the
        version-scoping guard; it fell through to the version compare no
        matter how that guard was written, and could not fail if the guard's
        version scoping were removed. Now the marker starts SILENT
        (deferred-by-mike) for a version OTHER than the one being deferred --
        the shape a founder's real defer actually left behind for v1.94 while
        v1.95 shipped over it. Asserts the printed message, not just the
        marker file, because the file is a no-op either way (silently
        short-circuited or correctly left-loud both leave it untouched) --
        the message is the only observable that distinguishes the bug from
        the cure."""
        marker = self._marker("9.9.8", state="deferred-by-mike")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(self._defer("9.9.9"), 0)
        printed = buf.getvalue()
        self.assertNotIn(
            "already deferred-by-mike", printed,
            "the guard silently claimed v9.9.8's defer covers v9.9.9; got: %r" % (printed,))
        self.assertIn("left loud", printed)
        self.assertEqual(json.loads(marker.read_text())["publish_state"], "deferred-by-mike")

    def test_defer_leaves_a_live_marker_alone(self):
        marker = self._marker("9.9.9", state="live")
        self.assertEqual(self._defer(), 0)
        self.assertEqual(json.loads(marker.read_text())["publish_state"], "live")

    def test_defer_of_a_different_version_does_not_silently_claim_a_live_marker(self):
        """The `live` half of the same AC4 rewrite: a marker gone live for an
        OLDER version must not report itself as already covering a NEWER
        release being deferred now -- same message-not-just-file distinction
        as the deferred-by-mike case above."""
        marker = self._marker("9.9.8", state="live")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(self._defer("9.9.9"), 0)
        printed = buf.getvalue()
        self.assertNotIn("already live", printed)
        self.assertIn("left loud", printed)
        self.assertEqual(json.loads(marker.read_text())["publish_state"], "live")


class _PublishMarkerFixture(unittest.TestCase):
    """A scratch .tropo/publish-pending.json, isolated from the real one.

    Unlike TestPublishReleaseFireAndDeferGates above, these tests call
    verlive.clear_publish_pending / verlive.defer_publish_pending directly
    rather than through cmd_defer's CLI wrapper -- AC1/AC2 are claims about
    those two functions' own return values, and the CLI wrapper only exposes
    an exit code.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="publish-marker-scope-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.marker_path = self.tmp / ".tropo" / "publish-pending.json"
        self.marker_path.parent.mkdir(parents=True)

    def _write_marker(self, version: str, state: str) -> None:
        self.marker_path.write_text(
            json.dumps({"version": version, "publish_state": state}), encoding="utf-8")

    def _read_marker(self) -> dict:
        return json.loads(self.marker_path.read_text(encoding="utf-8"))


class ClearPublishPendingGuardIsVersionScoped(_PublishMarkerFixture):
    """f015ebc247ce AC1."""

    def test_deferred_marker_for_an_older_version_reaches_the_comparison(self) -> None:
        self._write_marker("1.94.0", "deferred-by-mike")
        result = verlive.clear_publish_pending(
            self.tmp, self.tmp / "run", verified_version="1.95.0")
        self.assertNotIn(
            "already", result,
            "the guard short-circuited before comparing versions: %r" % (result,))
        self.assertIn("left loud", result)
        self.assertIn("1.94.0", result)
        self.assertIn("1.95.0", result)
        # The bug's real-world consequence, named directly: the marker stays
        # wrong (this is "left loud", not "cured" -- Mike's advance-vs-stay
        # question in the task is deliberately not decided here).
        self.assertEqual(self._read_marker()["publish_state"], "deferred-by-mike")

    def test_live_marker_for_an_older_version_also_reaches_the_comparison(self) -> None:
        self._write_marker("1.90.0", "live")
        result = verlive.clear_publish_pending(
            self.tmp, self.tmp / "run", verified_version="1.95.0")
        self.assertNotIn("already", result)
        self.assertIn("left loud", result)


class DeferPublishPendingGuardIsVersionScoped(_PublishMarkerFixture):
    """f015ebc247ce AC2 -- identical defect, defer_publish_pending."""

    def test_deferred_marker_for_an_older_version_reaches_the_comparison(self) -> None:
        self._write_marker("1.94.0", "deferred-by-mike")
        result = verlive.defer_publish_pending(self.tmp, "1.95.0")
        self.assertNotIn("already", result)
        self.assertIn("left loud", result)
        self.assertEqual(self._read_marker()["publish_state"], "deferred-by-mike")


class ThePublishMarkerSameVersionInvariantStillHolds(_PublishMarkerFixture):
    """f015ebc247ce AC3: the arm that must NOT move. A silent marker for the
    SAME version still short-circuits, both functions -- this is what stops a
    re-verify or a second defer from silently overwriting a founder's own
    ruling on the record."""

    def test_clear_still_short_circuits_on_the_same_version(self) -> None:
        self._write_marker("1.95.0", "deferred-by-mike")
        result = verlive.clear_publish_pending(
            self.tmp, self.tmp / "run", verified_version="1.95.0")
        self.assertIn("already", result)
        self.assertEqual(
            self._read_marker()["publish_state"], "deferred-by-mike",
            "a same-version re-verify must never overwrite a founder's defer")

    def test_clear_still_short_circuits_when_no_run_version_is_known(self) -> None:
        # An empty run_version is the guard's OTHER legitimate reason to
        # short-circuit -- "cannot prove which version this run is about" --
        # unrelated to the version-scoping bug and must survive the fix.
        self._write_marker("1.95.0", "live")
        result = verlive.clear_publish_pending(
            self.tmp, self.tmp / "run", verified_version="")
        self.assertIn("already", result)

    def test_defer_still_short_circuits_on_the_same_version(self) -> None:
        self._write_marker("1.95.0", "live")
        result = verlive.defer_publish_pending(self.tmp, "1.95.0")
        self.assertIn("already", result)
        self.assertEqual(self._read_marker()["publish_state"], "live")


class ThePublishMarkerFixIsMutationProven(_PublishMarkerFixture):
    """AC1's own demand, taken literally: 'assert the test fails when the two
    added lines are removed'. Loads an ISOLATED copy of the real module with
    the cured predicate reverted to its exact pre-fix form, and proves the
    reverted copy reproduces the original defect -- not a claim in a
    docstring, an executed one."""

    _CURED_CLEAR = (
        '    if (str(body.get("publish_state")) in PUBLISH_PENDING_SILENT_STATES\n'
        '            and (not run_version or marker_version == run_version)):\n'
    )
    _UNSCOPED_CLEAR = (
        '    if str(body.get("publish_state")) in PUBLISH_PENDING_SILENT_STATES:\n'
    )
    _CURED_DEFER = (
        '    if (str(body.get("publish_state")) in PUBLISH_PENDING_SILENT_STATES\n'
        '            and (not want or marker_version == want)):\n'
    )
    _UNSCOPED_DEFER = (
        '    if str(body.get("publish_state")) in PUBLISH_PENDING_SILENT_STATES:\n'
    )

    def _load_mutated(self, cured: str, unscoped: str, label: str):
        source = (_VAULT_TOOLS / "tropo-verify-release-live.py").read_text(encoding="utf-8")
        self.assertIn(
            cured, source,
            "the cured %s predicate text moved; update this mutation probe" % label)
        self.assertEqual(
            source.count(cured), 1,
            "expected exactly one occurrence of the cured %s predicate" % label)
        mutated_source = source.replace(cured, unscoped)
        self.assertNotEqual(mutated_source, source, "mutation did not change the file")
        mutated_path = self.tmp / ("mutated_%s.py" % label)
        mutated_path.write_text(mutated_source, encoding="utf-8")
        return _load("verlive_mutated_%s_fbe50871" % label, mutated_path)

    def test_reverting_clear_publish_pendings_predicate_reproduces_the_defect(self) -> None:
        mutated = self._load_mutated(self._CURED_CLEAR, self._UNSCOPED_CLEAR, "clear")
        self._write_marker("1.94.0", "deferred-by-mike")
        result = mutated.clear_publish_pending(
            self.tmp, self.tmp / "run", verified_version="1.95.0")
        self.assertIn(
            "already deferred-by-mike for v1.94.0", result,
            "the mutated (pre-fix) predicate did not reproduce the original "
            "silent short-circuit -- the two added lines are not load-bearing "
            "for this test, or the mutation probe is stale: %r" % (result,))

    def test_reverting_defer_publish_pendings_predicate_reproduces_the_defect(self) -> None:
        mutated = self._load_mutated(self._CURED_DEFER, self._UNSCOPED_DEFER, "defer")
        self._write_marker("1.94.0", "deferred-by-mike")
        result = mutated.defer_publish_pending(self.tmp, "1.95.0")
        self.assertIn("already deferred-by-mike for v1.94.0", result)


class TestColdWalkPublishGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pub-cold-walk-")).resolve()
        self.release_dir = self.tmp / "releases" / "v9.9.9"
        self.release_dir.mkdir(parents=True)
        (
            self.release_dir / "builds" / "tropo-os-v9.9.9"
        ).mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, payload):
        (self.release_dir / "cold-walk-verdict.json").write_text(json.dumps(payload))

    def test_missing_pending_fail_and_wrong_version_refuse(self):
        cases = [
            None,
            {"release_version": "9.9.9", "cold_walk": "elected-pending"},
            {"release_version": "9.9.9", "overall": "FAIL"},
            {"release_version": "9.9.8", "overall": "PASS"},
        ]
        for payload in cases:
            with self.subTest(payload=payload), patch.object(
                pub.tropo_roots, "RELEASES_DIR", self.tmp / "releases"
            ):
                verdict_path = self.release_dir / "cold-walk-verdict.json"
                if payload is None:
                    verdict_path.unlink(missing_ok=True)
                else:
                    self._write(payload)
                with self.assertRaises(pub.PublishError):
                    pub._require_cold_walk_clearance("9.9.9")

    def test_pass_and_recorded_skip_clear(self):
        cases = [
            {"release_version": "9.9.9", "overall": "PASS"},
            {"release_version": "9.9.9", "cold_walk": "skipped-by-mike"},
        ]
        for payload in cases:
            with self.subTest(payload=payload), patch.object(
                pub.tropo_roots, "RELEASES_DIR", self.tmp / "releases"
            ):
                self._write(payload)
                self.assertEqual(pub._require_cold_walk_clearance("9.9.9"), payload)

    def test_stage_no_longer_gates_on_the_legacy_cold_walk_verdict(self):
        """Superseded contract, rewritten rather than deleted (Stage-6 V10).

        Until Stage 6 this asserted that Stage refuses while the cold walk is
        pending. That gate read a verdict file written by build Step 10.6
        BEFORE the zip existed, so it attested to a walk over an artefact that
        had not been produced, and it stood in for what AC7 now requires from
        four instruments against the frozen digest.

        Stage writes nothing public — it prepares a private clone — so the
        Verify question belongs at Fire, where it can be asked against a
        digest that exists. What this now pins is the absence: a pending walk
        no longer stops Stage, and the authorization call it used to short-
        circuit is reached.
        """
        self._write({"release_version": "9.9.9", "cold_walk": "elected-pending"})
        args = types.SimpleNamespace(
            activation_uid="deadbeef",
            version="9.9.9",
            remote="https://github.com/tropo-ai/tropo.git",
            clone=None,
            clone_dir=None,
            allow_delete=False,
        )
        with patch.object(pub.tropo_roots, "RELEASES_DIR", self.tmp / "releases"), \
             patch.object(pub, "require_release_authorization") as authorize:
            pub.cmd_stage(args)
        authorize.assert_called()


class _FakeResponse:
    """Minimal urlopen context manager: status + body, nothing else."""

    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = json.dumps(payload or {}).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class VerifyChannelTwoLegs(unittest.TestCase):
    """4e9ce4cc AC1 — the channel verifies itself, on EVERY publish path.

    NETWORK-FREE BY CONSTRUCTION. Every urlopen is mocked; nothing here touches the live
    bucket. AC1's two LIVE runs (the red birth-certificate run against today's stale
    manifest, and the green run after the v1.94 publish) are operational acts against
    the real channel, explicitly outside any suite, and are NOT what this class claims
    to cover. They belong to the release owner and get recorded on the AC when run.

    WHY THE GATE EXISTS, which is also why the wiring test below matters most: v1.93
    shipped through `cmd_verify_only` while every manifest gate lived only inside
    `cmd_fire`. A gate wired into one path is skipped by exactly the other path a
    deadlocked fire falls back to — so "has a caller" is not enough, and this asserts
    the specific callers.
    """

    VERSION = "1.94.0"

    def _manifest(self, current="1.94.0", rows=None):
        if rows is None:
            rows = [{"version": "1.94.0", "url": "https://example.invalid/u/1.94.0.zip"}]
        return {"current": current, "updates": rows}

    # -- leg 1: completeness ---------------------------------------------

    def _run_completeness(self, manifest):
        with patch.object(pub, "_load_supabase_credentials",
                          return_value=("https://fake.invalid", "key")), \
             patch("urllib.request.urlopen",
                   return_value=_FakeResponse(200, manifest)):
            return pub._verify_published_update_manifest(self.VERSION)

    def test_leg1_passes_when_current_matches_and_the_row_is_present(self):
        got = self._run_completeness(self._manifest())
        self.assertEqual(got["current"], self.VERSION)

    def test_leg1_reds_when_current_is_an_older_version(self):
        """The birth-certificate shape: current 1.92.0, no matching row."""
        with self.assertRaises(pub.PublishError) as ctx:
            self._run_completeness(self._manifest(
                current="1.92.0",
                rows=[{"version": "1.92.0", "url": "https://example.invalid/u/1.92.0.zip"}]))
        message = str(ctx.exception)
        self.assertIn(
            "mismatch", message.lower(),
            "the refusal must CITE the completeness mismatch — a red that does not say "
            "which leg fired cannot prove the completeness bucket was reached")
        self.assertIn("1.92.0", message,
                      "the refusal does not name the version actually observed")

    def test_leg1_reds_when_current_matches_but_the_row_is_missing(self):
        """The half nobody would think to break: `current` right, no matching entry.

        Asserted separately because a check that only compares `current` passes this
        case, and a manifest naming a version it has no package for is exactly the
        1.87/1.88 failure this gate was written after.
        """
        with self.assertRaises(pub.PublishError):
            self._run_completeness(self._manifest(
                current=self.VERSION,
                rows=[{"version": "1.93.0", "url": "https://example.invalid/u/x.zip"}]))

    # -- leg 2: resolution -----------------------------------------------

    def test_leg2_heads_every_url_bearing_row(self):
        manifest = self._manifest(rows=[
            {"version": "1.94.0", "url": "https://example.invalid/a.zip"},
            {"version": "1.93.0", "url": "https://example.invalid/b.zip"},
        ])
        seen = []

        def _fake(request, timeout=None):
            seen.append((request.full_url, request.get_method()))
            return _FakeResponse(200)

        with patch("urllib.request.urlopen", side_effect=_fake):
            pub.resolve_manifest_urls(manifest)

        self.assertEqual(len(seen), 2, f"expected both rows HEADed, saw {seen}")
        for _url, method in seen:
            self.assertEqual(method, "HEAD",
                             "the resolution leg must HEAD, not GET — it proves the "
                             "object exists without downloading a release")

    def test_leg2_skips_url_less_rows_so_a_dead_row_cannot_red_forever(self):
        """The design point stated in verify_channel's own docstring.

        Dead catalog rows carry no url. If leg 2 tried to resolve them the gate would be
        permanently red on history nobody can fix, and a gate that cannot go green is
        one people route around.
        """
        manifest = self._manifest(rows=[
            {"version": "1.10.0"},                                        # dead, url-less
            {"version": "1.94.0", "url": "https://example.invalid/a.zip"},
        ])
        seen = []
        with patch("urllib.request.urlopen",
                   side_effect=lambda request, timeout=None: (
                       seen.append(request.full_url) or _FakeResponse(200))):
            pub.resolve_manifest_urls(manifest)
        self.assertEqual(
            seen, ["https://example.invalid/a.zip"],
            "leg 2 reached a url-less row; a dead catalog row must be skipped, not "
            "resolved")

    def test_leg2_reds_on_an_http_error_status(self):
        manifest = self._manifest()
        with patch("urllib.request.urlopen",
                   return_value=_FakeResponse(404)):
            with self.assertRaises(pub.PublishError) as ctx:
                pub.resolve_manifest_urls(manifest)
        self.assertIn("unresolvable", str(ctx.exception).lower())

    def test_leg2_reds_when_the_url_cannot_be_reached_at_all(self):
        """A structural check proves the manifest NAMES the release; only this proves
        the named object exists. That insufficiency shipped 1.87 and 1.88 empty."""
        manifest = self._manifest()
        with patch("urllib.request.urlopen", side_effect=OSError("no route")):
            with self.assertRaises(pub.PublishError) as ctx:
                pub.resolve_manifest_urls(manifest)
        self.assertIn("unresolvable", str(ctx.exception).lower())

    # -- both legs, through the real entry point --------------------------

    def test_verify_channel_runs_both_legs_in_one_call(self):
        manifest = self._manifest()
        heads = []

        def _fake(request, timeout=None):
            method = request.get_method()
            if method == "HEAD":
                heads.append(request.full_url)
                return _FakeResponse(200)
            return _FakeResponse(200, manifest)

        with patch.object(pub, "_load_supabase_credentials",
                          return_value=("https://fake.invalid", "key")), \
             patch("urllib.request.urlopen", side_effect=_fake):
            got = pub.verify_channel(self.VERSION)

        self.assertEqual(got["current"], self.VERSION, "leg 1 did not run")
        self.assertEqual(
            heads, ["https://example.invalid/u/1.94.0.zip"],
            "leg 2 did not run inside verify_channel — the two legs must both fire from "
            "the one entry point, or a caller gets half a gate")

    # -- the wiring, which is the whole reason the gate is standalone -----

    def test_the_gate_is_wired_into_every_publish_path(self):
        """AC1's headline: EVERY publish path, not just the one that was audited.

        Source-level because running cmd_fire needs a world. The named callers are the
        assertion: cmd_fire (the main path), cmd_verify_only (the path v1.93 actually
        shipped through while the gates lived only in cmd_fire), and cmd_verify_channel
        (the standalone birth-certificate runner).
        """
        source = (_VAULT_TOOLS / "tropo-publish-release.py").read_text(encoding="utf-8")
        for fn in ("cmd_fire", "cmd_verify_only", "cmd_verify_channel"):
            start = source.find(f"def {fn}(")
            self.assertGreater(start, 0, f"{fn} is gone from the publish tool")
            nxt = source.find("\ndef ", start + 1)
            body = source[start: nxt if nxt > 0 else len(source)]
            self.assertIn(
                "verify_channel(", body,
                f"{fn} does not call verify_channel. A gate wired into one path is "
                f"skipped by exactly the other path a deadlocked fire falls back to — "
                f"that is how v1.93 shipped past every manifest gate.")

    def test_a_red_channel_exits_14_distinctly_from_an_invocation_error(self):
        """Exit 14 is a FINDING about the channel, not a tool failure. An operational
        run cannot act on 'nonzero'."""
        source = (_VAULT_TOOLS / "tropo-publish-release.py").read_text(encoding="utf-8")
        start = source.find("def cmd_verify_channel(")
        body = source[start: source.find("\ndef ", start + 1)]
        self.assertIn("return 14", body,
                      "cmd_verify_channel no longer carries its distinct red exit code")


class TestManifestPublishWeld(unittest.TestCase):
    class _Response:
        status = 200

        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def test_manifest_upload_requires_credentials_before_generator_runs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            generator = root / "vault" / "tools" / "tropo-generate-update-manifest.py"
            generator.parent.mkdir(parents=True)
            generator.write_text("# fixture\n")
            with patch.object(pub.tropo_roots, "STUDIO_ROOT", root), \
                 patch.object(pub.tropo_roots, "VAULT_DIR", root / "vault"), \
                 patch.object(
                     pub,
                     "_load_supabase_credentials",
                     side_effect=pub.PublishError("credentials absent"),
                 ), \
                 patch.object(pub.subprocess, "run") as run:
                with self.assertRaisesRegex(pub.PublishError, "credentials absent"):
                    pub._upload_update_manifest()
            run.assert_not_called()

    def test_manifest_upload_passes_verified_credentials_to_generator(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            generator = root / "vault" / "tools" / "tropo-generate-update-manifest.py"
            generator.parent.mkdir(parents=True)
            generator.write_text("# fixture\n")
            completed = types.SimpleNamespace(returncode=0, stdout="uploaded\n", stderr="")
            with patch.object(pub.tropo_roots, "STUDIO_ROOT", root), \
                 patch.object(pub.tropo_roots, "VAULT_DIR", root / "vault"), \
                 patch.object(
                     pub,
                     "_load_supabase_credentials",
                     return_value=("https://storage.example", "private-key"),
                 ), \
                 patch.object(pub.subprocess, "run", return_value=completed) as run:
                pub._upload_update_manifest()
            child_env = run.call_args.kwargs["env"]
            self.assertEqual(child_env["NEXT_PUBLIC_SUPABASE_URL"], "https://storage.example")
            self.assertEqual(child_env["SUPABASE_SECRET_KEY"], "private-key")
            self.assertEqual(run.call_args.args[0], ["python3", str(generator), "--upload"])

    def test_manifest_upload_process_failure_is_publish_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            generator = root / "vault" / "tools" / "tropo-generate-update-manifest.py"
            generator.parent.mkdir(parents=True)
            generator.write_text("# fixture\n")
            with patch.object(pub.tropo_roots, "STUDIO_ROOT", root), \
                 patch.object(pub.tropo_roots, "VAULT_DIR", root / "vault"), \
                 patch.object(
                     pub,
                     "_load_supabase_credentials",
                     return_value=("https://storage.example", "private-key"),
                 ), \
                 patch.object(
                     pub.subprocess,
                     "run",
                     side_effect=subprocess.TimeoutExpired("manifest generator", 30),
                 ):
                with self.assertRaisesRegex(pub.PublishError, "could not run"):
                    pub._upload_update_manifest()

    def test_public_manifest_verification_requires_current_and_version_entry(self):
        cases = [
            ({"current": "9.9.8", "updates": [{"version": "9.9.9"}]}, False),
            ({"current": "9.9.9", "updates": [{"version": "9.9.8"}]}, False),
            ({"current": "9.9.9", "updates": [{"version": "9.9.9"}]}, True),
        ]
        for payload, accepted in cases:
            with self.subTest(payload=payload), \
                 patch.object(
                     pub,
                     "_load_supabase_credentials",
                     return_value=("https://storage.example", "private-key"),
                 ), \
                 patch.object(
                     pub.urllib.request,
                     "urlopen",
                     return_value=self._Response(payload),
                 ) as fetch:
                if accepted:
                    observed = pub._verify_published_update_manifest("9.9.9")
                    self.assertEqual(observed, payload)
                else:
                    with self.assertRaisesRegex(pub.PublishError, "manifest mismatch"):
                        pub._verify_published_update_manifest("9.9.9")
                request = fetch.call_args.args[0]
                self.assertIn(
                    "/storage/v1/object/public/releases/updates-manifest.json?verify=",
                    request.full_url,
                )


if __name__ == "__main__":
    unittest.main()
