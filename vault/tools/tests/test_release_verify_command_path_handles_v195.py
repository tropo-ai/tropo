#!/usr/bin/env python3
"""The runner substitutes {run_folder} and {candidate_path} in a verification_command.

The freeze step 7de2c49f has declared
    python3 vault/tools/tropo-freeze-release-candidate.py --run-dir {run_folder} --candidate {candidate_path}
since v1.89, and build_run_context_uids never carried either handle, so the
braces reached subprocess intact and every receipt read exit=4. v1.90, v1.93
and v1.94 each amended the step to a hand-written shell script. This suite is
RED without the two handles (talos-t63, 2026-09-06; driver-ruled post-lock
inclusion on v1.95).

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_release_verify_command_path_handles_v195
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("eng_path_handles", TOOLS / "9e7003b1.py")
eng = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eng)

RUN_UID = "f015af4a6a0a"
ACT_UID = "f015637f34b1"


class PathHandles(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="path-handles-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.files.mkdir(parents=True)
        self.run_folder_rel = f"vault/pipeline-runs/release-pipeline-{RUN_UID}-2026-09-05"
        self.run_folder = self.tmp / self.run_folder_rel
        self.run_folder.mkdir(parents=True)
        self._orig = (eng.VAULT_ROOT, eng.VAULT_FILES)
        eng.VAULT_ROOT = self.tmp
        eng.VAULT_FILES = self.files
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        eng.VAULT_ROOT, eng.VAULT_FILES = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_entry(self, with_folder: bool = True) -> dict:
        fm = {"uid": RUN_UID, "type": "pipeline-run", "pipeline": "634913c2",
              "activation": ACT_UID, "members": ["8a4f802b"]}
        if with_folder:
            fm["run_folder"] = self.run_folder_rel
        return {"frontmatter": fm}

    def _journal(self, rows: list) -> None:
        (self.run_folder / "run.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def _built(self, sha: str, path: str) -> dict:
        return {"event": "tropo.release.candidate_built",
                "data": {"release_run_uid": RUN_UID, "pipeline_run_uid": RUN_UID,
                         "candidate_sha256": sha, "package_path": path}}

    def test_run_folder_and_candidate_path_resolve_from_the_run(self) -> None:
        zip_path = "/releases/v9.9.9/dist/tropo-os-v9.9.9.zip"
        sha = hashlib.sha256(b"bytes").hexdigest()
        self._journal([self._built(sha, zip_path)])
        ctx = eng.build_run_context_uids(self._run_entry(), ACT_UID)
        self.assertEqual(ctx.get("run_folder"), self.run_folder_rel)
        self.assertEqual(ctx.get("candidate_path"), zip_path)

    def test_the_declared_freeze_command_substitutes_completely(self) -> None:
        """The exact template locked on the v1.95 run, through the runner's own loop."""
        zip_path = "/releases/v9.9.9/dist/tropo-os-v9.9.9.zip"
        self._journal([self._built(hashlib.sha256(b"x").hexdigest(), zip_path)])
        ctx = eng.build_run_context_uids(self._run_entry(), ACT_UID)
        cmd = ("python3 vault/tools/tropo-freeze-release-candidate.py "
               "--run-dir {run_folder} --candidate {candidate_path}")
        for h, v in ctx.items():
            if v:
                cmd = cmd.replace("{" + h + "}", str(v))
        self.assertNotIn("{", cmd, f"a placeholder survived: {cmd}")
        self.assertIn(f"--run-dir {self.run_folder_rel}", cmd)
        self.assertIn(f"--candidate {zip_path}", cmd)

    def test_an_invalidated_candidate_leaves_the_handle_unresolved(self) -> None:
        """No live candidate -> no candidate_path: the placeholder stays visible
        and the receipt says so, rather than the runner guessing a file."""
        sha = hashlib.sha256(b"old").hexdigest()
        self._journal([self._built(sha, "/x.zip"),
                       {"event": "tropo.release.candidate_invalidated",
                        "data": {"release_run_uid": RUN_UID, "candidate_sha256": sha,
                                 "reason": "rebuilt"}}])
        ctx = eng.build_run_context_uids(self._run_entry(), ACT_UID)
        self.assertEqual(ctx.get("run_folder"), self.run_folder_rel)
        self.assertNotIn("candidate_path", ctx)

    def test_a_rebuilt_candidate_resolves_to_the_live_one(self) -> None:
        old = hashlib.sha256(b"old").hexdigest()
        new = hashlib.sha256(b"new").hexdigest()
        self._journal([self._built(old, "/old.zip"),
                       {"event": "tropo.release.candidate_invalidated",
                        "data": {"release_run_uid": RUN_UID, "candidate_sha256": old,
                                 "reason": "rebuilt"}},
                       self._built(new, "/new.zip")])
        ctx = eng.build_run_context_uids(self._run_entry(), ACT_UID)
        self.assertEqual(ctx.get("candidate_path"), "/new.zip")

    def test_a_run_without_a_folder_declares_neither_handle(self) -> None:
        ctx = eng.build_run_context_uids(self._run_entry(with_folder=False), ACT_UID)
        self.assertNotIn("run_folder", ctx)
        self.assertNotIn("candidate_path", ctx)

    def test_the_uid_handles_are_untouched(self) -> None:
        self._journal([])
        ctx = eng.build_run_context_uids(self._run_entry(), ACT_UID)
        self.assertEqual(ctx["activation"], ACT_UID)
        self.assertEqual(ctx["pipeline"], "634913c2")
        self.assertEqual(ctx["activation_root"], "8a4f802b")


if __name__ == "__main__":
    unittest.main()
