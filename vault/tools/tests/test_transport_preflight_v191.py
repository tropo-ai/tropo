#!/usr/bin/env python3
"""v1.91 S3 AC2 (176a8995) — git transport is PROVEN before the confirm.

v1.90 (retrospective 62deeec1): the fire restored the push URL, git prompted
"Username for https://github.com" and timed out after 120 seconds — AFTER Mike
typed y. Grounding in tropo-publish-release.py cmd_fire: _confirm_tty fires
before anything touches the remote; the push URL is restored and the first
`git push` runs only after it. Nothing between stage and the confirm asks the
remote whether it will talk to us.

CONTRACT (red at birth, 2026-08-23):
  * `tropo-publish-release.py preflight --version V` exists as
    `cmd_preflight(args)` (args.version), same shape as cmd_fire. It NEVER
    prompts (no _confirm_tty, no input()).
  * It runs a read-only `git ls-remote <pinned remote>`; when that fails it
    REFUSES (nonzero) naming `ls-remote`, the remote and the cure (an HTTPS
    credential / `gh auth setup-git` / an ssh remote). With the remote
    reachable it never blames transport. AC1: every precondition is reported,
    so a preflight that stops before naming transport is red on purpose.
Fixtures: a local bare repo is the pinned remote (good transport); a loopback
HTTP server answering 401 reproduces the v1.90 shape (git asks for a username;
GIT_TERMINAL_PROMPT=0 keeps the suite from hanging — production preflight should
set the same). Roots are patched into a temp tree as the fbe50871 suite does.
Mutation clause: remove the ls-remote probe and the 401 case goes RED.
"""
from __future__ import annotations

import contextlib
import http.server
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "publisher_transport_v191", TOOLS / "tropo-publish-release.py")
pub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pub)

GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/usr/bin/false",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
_CURE = re.compile(r"credential|gh auth|askpass|ssh", re.I)


class _Prompted(Exception):
    """Raised by the sentinel if preflight asks a human anything."""


class _Deny401(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="GitHub"')
        self.end_headers()

    def log_message(self, *_):
        pass


def _git(args, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   cwd=str(cwd), check=True, capture_output=True,
                   env=dict(os.environ, **GIT_ENV))


class TransportPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="s3-transport-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bare = self.tmp / "remote.git"
        _git(["init", "--bare", "-q", str(self.bare)], self.tmp)
        _git(["symbolic-ref", "HEAD", "refs/heads/main"], self.bare)
        seed = self.tmp / "seed"
        _git(["init", "-q", "-b", "main", str(seed)], self.tmp)
        (seed / "README.md").write_text("seed\n")
        _git(["add", "-A"], seed)
        _git(["commit", "-q", "-m", "seed"], seed)
        _git(["remote", "add", "origin", str(self.bare)], seed)
        _git(["push", "-q", "origin", "main"], seed)
        self.clone = self.tmp / "staged-clone"
        _git(["clone", "-q", str(self.bare), str(self.clone)], self.tmp)
        self.sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.clone),
                                  capture_output=True, text=True).stdout.strip()
        self.studio = self.tmp / "studio"
        for sub in (".tropo", "vault/files"):
            (self.studio / sub).mkdir(parents=True)
        self.releases = self.tmp / "releases"

    def _stage_state(self, remote: str) -> None:
        # The state `stage` leaves behind, with the remote under test pinned.
        _git(["remote", "set-url", "origin", remote], self.clone)
        _git(["remote", "set-url", "--push", "origin", "DISABLED"], self.clone)
        (self.releases / "v9.9.9").mkdir(parents=True, exist_ok=True)
        (self.releases / "v9.9.9" / "publish-state.json").write_text(json.dumps(
            {"version": "9.9.9", "tag": "v9.9.9", "staged_sha": self.sha, "remote": remote,
             "activation_uid": "deadbeef", "clone_dir": str(self.clone)}))

    def _preflight(self, remote: str) -> tuple[int, str, float]:
        if not hasattr(pub, "cmd_preflight"):
            self.fail("NOT IMPLEMENTED: tropo-publish-release.py has no preflight "
                      "subcommand (cmd_preflight) — no transport probe can run "
                      "before the TTY confirm (S3 AC1/AC2)")
        self._stage_state(remote)
        ac7 = {"identity": types.SimpleNamespace(activation_uid="deadbeef", run_uid="r1"),
               "package_sha256": "a" * 64, "receipts": []}
        out = io.StringIO()
        started = time.monotonic()
        with patch.object(pub.tropo_roots, "STUDIO_ROOT", self.studio), \
             patch.object(pub.tropo_roots, "VAULT_DIR", self.studio / "vault"), \
             patch.object(pub.tropo_roots, "RELEASES_DIR", self.releases), \
             patch.object(pub.tropo_roots, "STAGED_CLONE_DIR", self.clone), \
             patch.object(pub.tropo_roots, "DEV_HOME", self.tmp), \
             patch.object(pub, "DEFAULT_REMOTE", remote), \
             patch.object(pub, "require_release_authorization", lambda *a, **k: {}), \
             patch.object(pub, "require_ac7_receipt_set", lambda *a, **k: ac7), \
             patch.object(pub, "_release_entry_uid_for", lambda *a, **k: "00000001"), \
             patch.object(pub, "_confirm_tty", side_effect=_Prompted), \
             patch("builtins.input", side_effect=_Prompted), \
             patch.dict(os.environ, GIT_ENV), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                rc = pub.cmd_preflight(types.SimpleNamespace(version="9.9.9"))
            except _Prompted:
                self.fail("preflight asked a human something — it must refuse or "
                          "pass without any prompt (S3 AC1)")
        return rc, out.getvalue(), time.monotonic() - started

    def test_no_https_credential_refuses_and_names_the_cure(self) -> None:
        server = http.server.HTTPServer(("127.0.0.1", 0), _Deny401)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        remote = f"http://127.0.0.1:{server.server_port}/tropo-ai/tropo.git"
        rc, out, elapsed = self._preflight(remote)
        self.assertLess(elapsed, 60, f"preflight hung {elapsed:.0f}s on the credential "
                        f"prompt — v1.90's 120s timeout, before the confirm this time")
        self.assertNotEqual(rc, 0, f"preflight passed with no HTTPS credential:\n{out}")
        self.assertIn("ls-remote", out,
                      f"preflight refused without naming the transport probe "
                      f"(git ls-remote {remote}) — every precondition must be "
                      f"reported, not just the first:\n{out}")
        self.assertTrue(_CURE.search(out),
                        f"refusal names no cure (credential / gh auth setup-git / "
                        f"ssh remote):\n{out}")

    def test_reachable_remote_is_not_blamed_for_transport(self) -> None:
        rc, out, _ = self._preflight(str(self.bare))
        self.assertIn("ls-remote", out,
                      f"preflight did not prove transport (no ls-remote line):\n{out}")
        self.assertFalse(re.search(r"could not read Username|terminal prompts disabled|"
                                   r"unable to access|ls-remote.*(fail|refus)", out, re.I),
                         f"a reachable remote was blamed for transport:\n{out}")


if __name__ == "__main__":
    unittest.main()
