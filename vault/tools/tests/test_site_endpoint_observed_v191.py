#!/usr/bin/env python3
"""v1.91 S3 AC5 (176a8995) — verify-live OBSERVES site_endpoint, or names why not.

The locked AC5 case (test_publish_preflight_v191.SiteEndpointAC5) is world-bound
and skips: it needs https://tropo-ai.com to serve the badge. This file pins the
MECHANICS with a loopback server so the observation cannot rot unnoticed:

  * a served badge is SEEN with its sha256 (downloaded and hashed, not trusted);
  * a 404 is the named refusal "site_endpoint not observed: <url> -> 404";
  * by default the observation is advisory (REQUIRED_FACTS is closed and both
    public URLs 404 today — see the design note in tropo-verify-release-live.py);
    --require-site-endpoint binds it: not observed -> INCOMPLETE, exit 1,
    partial state site-endpoint-pending, and the publish-pending marker is NOT
    flipped to live.
Mutation clause: drop the observation (or make absence silent) -> RED.
"""
from __future__ import annotations

import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import temp_studio  # noqa: E402
import release_fixture_v192 as fixture  # noqa: E402

SHA = "ab" * 32
BADGE = json.dumps({"version": "v9.9.9", "fileSize": "2.9 MB",
                    "sizeBytes": 3_000_000, "releasedAt": "2026-08-23"}).encode()


class _Site(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/os-release.json"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(BADGE)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass


class SiteEndpointObservedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), _Site)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="s3-site-endpoint-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.studio = temp_studio.TempStudio(tmp / "studios" / "argo-os").build()
        shutil.copy2(temp_studio.REAL_TOOLS / "tropo-verify-release-live.py",
                     self.studio.tools / "tropo-verify-release-live.py")
        self.run_dir = self.studio.runs / "release-pipeline-r1-2026-08-23"
        self.run_dir.mkdir(parents=True)
        self.receipt_sha = fixture.build_finished_release(
            self.run_dir,
            self.studio.root,
            extra_rows=[{"event": "run_created",
                         "data": {"saga_id": "release:r1",
                                  "pipeline_run_uid": "r1",
                                  "release_version": "9.9.9"}}],
        )
        self.bus = tmp / "bus.jsonl"
        self.bus.write_text(
            json.dumps(fixture.bus_published_row(self.receipt_sha)) + "\n")
        self.marker = self.studio.root / ".tropo" / "publish-pending.json"
        self.marker.write_text(json.dumps({"version": "9.9.9", "publish_state": "not-staged"}))

    def _verify(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.studio.tools / "tropo-verify-release-live.py"),
             "--run-dir", str(self.run_dir), "--vault", str(self.studio.root),
             "--bus-events", str(self.bus), *extra],
            cwd=str(self.studio.root), capture_output=True, text=True, timeout=120)

    def test_a_served_badge_is_seen_with_its_sha256(self) -> None:
        import hashlib
        proc = self._verify("--site-endpoint-url", self.base + "/os-release.json", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        body = json.loads(proc.stdout)
        site = body["site_endpoint"]
        self.assertTrue(site["present"], site)
        self.assertEqual(site["sha256"], hashlib.sha256(BADGE).hexdigest(),
                         "the badge must be downloaded and hashed, not trusted")
        self.assertEqual(site["version"], "v9.9.9")

    def test_a_404_is_the_named_refusal_and_advisory_by_default(self) -> None:
        proc = self._verify("--site-endpoint-url", self.base + "/missing.json")
        self.assertEqual(proc.returncode, 0, "advisory by default: COMPLETE stands")
        self.assertIn("site_endpoint not observed: %s/missing.json -> 404" % self.base,
                      proc.stdout, proc.stdout)
        self.assertIn("[ABSENT] site_endpoint", proc.stdout)

    def test_required_site_endpoint_binds_the_observation(self) -> None:
        proc = self._verify("--site-endpoint-url", self.base + "/missing.json",
                            "--require-site-endpoint")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("INCOMPLETE — site-endpoint-pending", proc.stdout)
        self.assertEqual(json.loads(self.marker.read_text())["publish_state"], "not-staged",
                         "not live -> the publish-pending marker must not be flipped")

    def test_an_undeclared_endpoint_fetches_nothing_and_says_so(self) -> None:
        proc = self._verify()
        self.assertEqual(proc.returncode, 0)
        self.assertIn("site_endpoint not observed: undeclared", proc.stdout)


if __name__ == "__main__":
    unittest.main()
