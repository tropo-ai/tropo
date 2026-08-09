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
import importlib.util
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
                patch.object(build, "RELEASES_DIR", str(release_root)),
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
        self.build_dir = self.tmp / "releases" / "v9.9.9"
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
        (self.build_dir / "dist").mkdir()
        (self.build_dir / "dist" / "tropo-os-v9.9.9.zip").write_bytes(b"PK\x03\x04fake")
        (self.build_dir / "cold-walk-verdict.json").write_text(
            json.dumps({"release_version": "9.9.9", "overall": "PASS"})
        )

        self.studio_root.mkdir(parents=True)
        (self.studio_root / "CHANGELOG.md").write_text(
            "## [Unreleased]\n\n## [9.9.9]\n- new stuff\n\n## [9.9.8]\n- old\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patches(self):
        return (
            patch.object(pub, "VAULT_ROOT", self.studio_root),
            patch.object(pub, "RELEASES_DIR", self.tmp / "releases"),
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

        build2 = self.tmp / "releases" / "v9.9.10"
        build2.mkdir(parents=True)
        (build2 / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [9.9.10]\n- x\n")
        (build2 / "cold-walk-verdict.json").write_text(
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
        self.build_dir = self.tmp / "releases" / "v9.9.9"
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
        (self.build_dir / "cold-walk-verdict.json").write_text(
            json.dumps({"release_version": "9.9.9", "overall": "PASS"})
        )
        self.studio_root.mkdir(parents=True)
        (self.studio_root / "CHANGELOG.md").write_text(
            "## [Unreleased]\n\n## [9.9.9]\n- new stuff\n\n## [9.9.8]\n- old\n")

        with patch.object(pub, "VAULT_ROOT", self.studio_root), \
             patch.object(pub, "RELEASES_DIR", self.tmp / "releases"), \
             patch.object(pub, "DEFAULT_REMOTE", str(self.bare)), \
             patch.object(pub, "require_release_authorization", lambda *a, **k: {"fingerprint": "fake"}):
            pub.cmd_stage(types.SimpleNamespace(
                activation_uid="deadbeef", version="9.9.9", remote=str(self.bare),
                clone=None, clone_dir=str(self.clone_dir), allow_delete=False))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fire_refuses_without_tty(self):
        with patch.object(pub, "VAULT_ROOT", self.studio_root), \
             patch.object(pub, "RELEASES_DIR", self.tmp / "releases"), \
             patch.object(pub, "DEFAULT_REMOTE", str(self.bare)), \
             patch.object(pub, "require_release_authorization", lambda *a, **k: {"fingerprint": "fake"}), \
             patch.object(sys.stdin, "isatty", lambda: False):
            rc = pub.cmd_fire(types.SimpleNamespace(version="9.9.9"))
        self.assertNotEqual(rc, 0)

    def test_fire_refuses_on_stale_stage(self):
        (self.clone_dir / "extra.txt").write_text("drift\n")
        subprocess.run(["git", "-C", str(self.clone_dir), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.clone_dir), "-c", "user.email=t@t.com",
                         "-c", "user.name=T", "commit", "-q", "-m", "drift"], check=True)
        with patch.object(pub, "VAULT_ROOT", self.studio_root), \
             patch.object(pub, "RELEASES_DIR", self.tmp / "releases"), \
             patch.object(pub, "DEFAULT_REMOTE", str(self.bare)), \
             patch.object(pub, "require_release_authorization", lambda *a, **k: {"fingerprint": "fake"}), \
             patch.object(pub, "_confirm_tty", lambda prompt: True):
            rc = pub.cmd_fire(types.SimpleNamespace(version="9.9.9"))
        self.assertNotEqual(rc, 0)

    def test_defer_requires_reason(self):
        rc = pub.cmd_defer(types.SimpleNamespace(version="9.9.9", reason=None))
        self.assertNotEqual(rc, 0)

    def test_defer_refuses_without_tty(self):
        with patch.object(sys.stdin, "isatty", lambda: False):
            rc = pub.cmd_defer(types.SimpleNamespace(version="9.9.9", reason="testing"))
        self.assertNotEqual(rc, 0)


class TestColdWalkPublishGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pub-cold-walk-")).resolve()
        self.release_dir = self.tmp / "releases" / "v9.9.9"
        self.release_dir.mkdir(parents=True)

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
            with self.subTest(payload=payload), patch.object(pub, "RELEASES_DIR", self.tmp / "releases"):
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
            with self.subTest(payload=payload), patch.object(pub, "RELEASES_DIR", self.tmp / "releases"):
                self._write(payload)
                self.assertEqual(pub._require_cold_walk_clearance("9.9.9"), payload)

    def test_stage_refuses_before_authorization_when_walk_is_pending(self):
        self._write({"release_version": "9.9.9", "cold_walk": "elected-pending"})
        args = types.SimpleNamespace(
            activation_uid="deadbeef",
            version="9.9.9",
            remote="https://github.com/tropo-ai/tropo.git",
            clone=None,
            clone_dir=None,
            allow_delete=False,
        )
        with patch.object(pub, "RELEASES_DIR", self.tmp / "releases"), \
             patch.object(pub, "require_release_authorization") as authorize:
            self.assertEqual(pub.cmd_stage(args), 6)
        authorize.assert_not_called()


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
            with patch.object(pub, "VAULT_ROOT", root), \
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
            with patch.object(pub, "VAULT_ROOT", root), \
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
            with patch.object(pub, "VAULT_ROOT", root), \
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
