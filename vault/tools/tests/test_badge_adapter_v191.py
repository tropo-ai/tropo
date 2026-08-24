#!/usr/bin/env python3
"""v1.91 S3 AC4 (176a8995) — the website badge is written BY AN ADAPTER to the
repository the website deploys from, resolved from configuration.

Today (tropo-publish-release.py _stamp_os_release_badge, called from cmd_fire
after the Supabase upload): the fire stamps STUDIO_ROOT/tropo-app/os-release.json
inside argo-os and prints "→ NEXT (manual): commit + push ...". The site builds
from tropo-ai/tropo-app, a separate private repo, badge at its root; G107 and
G108 mirrored by hand and G110 found the target from a Vercel screenshot
(62deeec1). A printed instruction is the knowledge living in heads, again.

CONTRACT THIS TEST DRIVES (red at birth, 2026-08-23):
  * The fire's badge act — `_stamp_os_release_badge(version, dist_dir,
    released_at)`, the entry point the fire calls and test_v188_weld_batch
    pins — leaves the stamped badge on the main branch of the DEPLOY
    repository, at its root (os-release.json), pushed.
  * The deploy repository is resolved from configuration, never assumed to
    be the studio: this fixture supplies it both ways the publisher already
    resolves site facts (_site_endpoint_url: staged state, then environment):
    publish-state `site_badge_remote` and env `TROPO_SITE_BADGE_REMOTE`. The
    committed default must name tropo-ai/tropo-app, not argo-os.
  * It prints no manual "commit + push" instruction — an adapter writes.
  * Any working clone it needs lives under the patched tropo_roots tree.
Mutation clause: point the target at argo-os (or leave today's stamp) -> RED,
because the deploy repository still serves the previous version.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "publisher_badge_v191", TOOLS / "tropo-publish-release.py")
pub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pub)

GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null"}
STALE = {"schema": "tropo.os-release/v1", "version": "v1.89.0",
         "fileSize": "5.0 MB", "sizeBytes": 1, "releasedAt": "2026-01-01"}
ZIP_BYTES = 3_000_000


def _git(args, cwd):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                          cwd=str(cwd), check=True, capture_output=True, text=True,
                          env=dict(os.environ, **GIT_ENV))


class BadgeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="s3-badge-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # The website's repository (stands for tropo-ai/tropo-app), badge at root.
        self.site = self.tmp / "tropo-app.git"
        _git(["init", "--bare", "-q", str(self.site)], self.tmp)
        _git(["symbolic-ref", "HEAD", "refs/heads/main"], self.site)
        seed = self.tmp / "seed"
        _git(["init", "-q", "-b", "main", str(seed)], self.tmp)
        (seed / "os-release.json").write_text(json.dumps(STALE, indent=2) + "\n")
        _git(["add", "-A"], seed)
        _git(["commit", "-q", "-m", "badge v1.89.0"], seed)
        _git(["remote", "add", "origin", str(self.site)], seed)
        _git(["push", "-q", "origin", "main"], seed)
        # The studio (argo-os) — today's target, present so today's code runs through.
        self.studio = self.tmp / "studio"
        (self.studio / "tropo-app").mkdir(parents=True)
        (self.studio / ".tropo").mkdir()
        (self.studio / "vault" / "files").mkdir(parents=True)
        self.studio_badge = self.studio / "tropo-app" / "os-release.json"
        self.studio_badge.write_text(json.dumps(STALE, indent=2) + "\n")
        self.dist = self.tmp / "releases" / "v9.9.9" / "dist"
        self.dist.mkdir(parents=True)
        (self.dist / "tropo-os-v9.9.9.zip").write_bytes(b"x" * ZIP_BYTES)
        (self.dist.parent / "publish-state.json").write_text(json.dumps({
            "version": "9.9.9", "tag": "v9.9.9", "staged_sha": "0" * 40,
            "activation_uid": "deadbeef", "remote": pub.DEFAULT_REMOTE,
            "clone_dir": str(self.tmp / "staged-clone"),
            "site_badge_remote": str(self.site)}))

    def _deployed_badge(self) -> dict:
        shown = _git(["--git-dir", str(self.site), "show", "main:os-release.json"], self.tmp)
        return json.loads(shown.stdout)

    def _stamp(self) -> str:
        out = io.StringIO()
        with patch.object(pub.tropo_roots, "STUDIO_ROOT", self.studio), \
             patch.object(pub.tropo_roots, "VAULT_DIR", self.studio / "vault"), \
             patch.object(pub.tropo_roots, "RELEASES_DIR", self.tmp / "releases"), \
             patch.object(pub.tropo_roots, "STAGED_CLONE_DIR", self.tmp / "staged-clone"), \
             patch.object(pub.tropo_roots, "DEV_HOME", self.tmp), \
             patch.object(pub.tropo_roots, "STUDIOS_HOME", self.tmp / "studios"), \
             patch.dict(os.environ, dict(GIT_ENV, TROPO_SITE_BADGE_REMOTE=str(self.site))), \
             contextlib.redirect_stdout(out):
            pub._stamp_os_release_badge("9.9.9", self.dist, "2026-08-23")
        return out.getvalue()

    def test_the_badge_lands_in_the_repository_the_site_deploys_from(self) -> None:
        self._stamp()
        deployed = self._deployed_badge()
        studio_side = json.loads(self.studio_badge.read_text())
        self.assertEqual(
            deployed.get("version"), "v9.9.9",
            f"the deploy repository {self.site} still serves {deployed.get('version')} "
            f"on main:os-release.json — the badge was written to the studio instead "
            f"({self.studio_badge} now says {studio_side.get('version')}) and left "
            f"for a human to commit + push (S3 AC4: an adapter writes to the "
            f"configured deploy target, not a printed instruction)")
        self.assertEqual(deployed.get("sizeBytes"), ZIP_BYTES, "sizeBytes must measure the real zip")
        self.assertEqual(deployed.get("releasedAt"), "2026-08-23")
        self.assertEqual(deployed.get("schema"), STALE["schema"], "unrelated fields must survive")

    def test_the_act_prints_no_manual_commit_and_push_instruction(self) -> None:
        out = self._stamp()
        self.assertNotIn(
            "NEXT (manual)", out,
            f"the badge act still hands the deploy to a human:\n{out}")


if __name__ == "__main__":
    unittest.main()
