#!/usr/bin/env python3
"""v1.91 S3 AC6 (176a8995) — something WRITES .tropo/publish-pending.json.

Boot step 5.1.8 (vault/playbooks/99341618.md; .tropo/boot-fast-path.md) reads
`.tropo/publish-pending.json`: present with publish_state not in {live,
deferred-by-mike} -> one "built but not published" line; absent or live/
deferred -> silent. "Written by build/stage, cleared by verify-live green."
Nothing writes it (Argus F-07; d1194f22 l.359), so the gate has never once
spoken — every executive booted silent the morning after v1.90 was built
and unpublished. Grounding: tropo-build-release.py writes build-provenance.json
(Step 8.1) and zips at step_11_zip_and_upload ("PUBLISH: not-staged — nothing
left this machine"), then prints "=== Build Complete ===" — no marker anywhere;
tropo-verify-release-live.py decides COMPLETE from lib/release_completion and
touches no studio state.

CONTRACT THIS TEST DRIVES (red at birth, 2026-08-23):
  (a) The step that turns a build into a completed build — step_11_zip_and_upload,
      the zip — leaves STUDIO_ROOT/.tropo/publish-pending.json behind with
      {"version": <v>, "publish_state": <not live / not deferred-by-mike>}.
      Written by the zip step so it is provable without a 25-minute build and
      survives a death after the zip; dry_run=True writes nothing.
  (b) tropo-verify-release-live.py exiting 0 (COMPLETE) for a run clears the
      marker under the studio it is pointed at (--vault): removed, or flipped
      to publish_state live. Run as a COPY in a Studio-shaped temp tree so no
      root resolution can reach the real .tropo/.
Mutation clause: remove either write and the boot line can never fire/stop.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import temp_studio  # noqa: E402
import release_fixture_v192 as fixture  # noqa: E402

TOOLS = Path(__file__).resolve().parents[1]
MARKER = Path(".tropo") / "publish-pending.json"
SILENT_STATES = {"live", "deferred-by-mike"}
SHA = "ab" * 32


def _load_build():
    spec = importlib.util.spec_from_file_location(
        "build_release_marker_v191", TOOLS / "tropo-build-release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildWritesTheMarker(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="s3-marker-build-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.studio = self.tmp / "studio"
        (self.studio / ".tropo").mkdir(parents=True)
        (self.studio / "vault").mkdir()
        self.build_dir = self.tmp / "releases" / "v9.9.9" / "builds" / "tropo-os-v9.9.9"
        self.build_dir.mkdir(parents=True)
        (self.build_dir / "README.md").write_text("# Tropo-OS v9.9.9\n")
        self.dist = self.tmp / "releases" / "v9.9.9" / "dist"
        self.dist.mkdir()

    def _zip(self, dry_run: bool) -> None:
        build = _load_build()
        with patch.object(build.tropo_roots, "STUDIO_ROOT", self.studio), \
             patch.object(build.tropo_roots, "VAULT_DIR", self.studio / "vault"), \
             patch.object(build.tropo_roots, "RELEASES_DIR", self.tmp / "releases"):
            build.step_11_zip_and_upload(str(self.build_dir), "9.9.9", str(self.dist),
                                         dry_run=dry_run)

    def test_a_completed_build_writes_the_marker(self) -> None:
        self._zip(dry_run=False)
        self.assertTrue((self.dist / "tropo-os-v9.9.9.zip").is_file(), "fixture: no zip")
        marker = self.studio / MARKER
        self.assertTrue(
            marker.is_file(),
            f"the build zipped v9.9.9 and wrote no {MARKER} — boot 5.1.8 reads a "
            f"file nothing creates (Argus F-07); the built-but-unpublished line "
            f"can never fire")
        body = json.loads(marker.read_text())
        self.assertEqual(str(body.get("version")), "9.9.9", body)
        self.assertNotIn(str(body.get("publish_state")), SILENT_STATES | {"None", ""},
                         f"marker must carry a loud publish_state: {body}")

    def test_a_dry_run_writes_nothing(self) -> None:
        self._zip(dry_run=True)
        self.assertFalse((self.studio / MARKER).exists(), "dry-run must not claim a build")


class VerifyLiveGreenClearsTheMarker(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="s3-marker-verify-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.studio = temp_studio.TempStudio(tmp / "studios" / "argo-os").build()
        shutil.copy2(temp_studio.REAL_TOOLS / "tropo-verify-release-live.py",
                     self.studio.tools / "tropo-verify-release-live.py")
        self.run_dir = self.studio.runs / "release-pipeline-r1-2026-08-23"
        self.run_dir.mkdir(parents=True)
        rows = [
            {"event": "run_created", "data": {"saga_id": "release:r1",
                                              "pipeline_run_uid": "r1",
                                              "release_version": "9.9.9"}},
        ]
        # AMENDED 2026-08-24 by argus-a156 (Stream 1 AC4; Mike verbatim "1 yes,
        # 2 yes, 3 yes"; routed by metis-g112). This built a finished release
        # from two filenames no producer has ever written. It now builds what
        # the producers build. See release_fixture_v192 for the full reason.
        self.receipt_sha = fixture.build_finished_release(
            self.run_dir, self.studio.root, extra_rows=rows)
        self.bus = tmp / "bus.jsonl"
        self.bus.write_text(
            json.dumps(fixture.bus_published_row(self.receipt_sha)) + "\n")
        self.marker = self.studio.root / MARKER
        self.marker.write_text(json.dumps({"version": "9.9.9", "publish_state": "not-staged"}))

    def test_verify_live_green_clears_the_marker(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(self.studio.tools / "tropo-verify-release-live.py"),
             "--run-dir", str(self.run_dir), "--vault", str(self.studio.root),
             "--bus-events", str(self.bus)],
            cwd=str(self.studio.root), capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0,
                         f"fixture: verify-live is not green:\n{proc.stdout}{proc.stderr}")
        if self.marker.exists():
            state = json.loads(self.marker.read_text()).get("publish_state")
            self.assertIn(
                state, SILENT_STATES,
                f"verify-live reported COMPLETE and left {MARKER} at "
                f"publish_state={state!r} — boot 5.1.8 keeps nagging after the "
                f"release is live (S3 AC6: verify-live green clears it)")


if __name__ == "__main__":
    unittest.main()
