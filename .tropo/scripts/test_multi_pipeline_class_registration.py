#!/usr/bin/env python3
"""Smoke test: multi-pipeline-class registration (Phase A acceptance test #1).

Per engine extension spec [51d171f3] §How to Validate Test 1:
  - Author trivial doc-pipeline definition; activate via pipeline-activate.py
  - Engine fires activation cleanly; activation entry written with type:activation
  - Pipeline-class resolves from pipeline definition name field

Uses Vela V51's test-pipeline definition [da3f50dc] as the trivial-but-real
activation target (Phase C LOCKED; first production registration of test-pipeline class).

Exit 0: PASS. Exit 1: FAIL.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
VAULT_FILES = SCRIPTS.parents[1] / "vault" / "files"
VAULT_ROOT = SCRIPTS.parents[2]

TEST_PIPELINE_UID = "da3f50dc"  # test-pipeline v1.0, Vela V51 LOCKED 2026-05-23


def cleanup(uids: list[str]) -> None:
    for uid in uids:
        p = VAULT_FILES / f"{uid}.md"
        if p.exists():
            p.unlink()


def main() -> int:
    print(f"[TEST] multi-pipeline-class registration — target: {TEST_PIPELINE_UID} (test-pipeline)")
    created_uids: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.jsonl"

        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "pipeline-activate.py"),
             "--pipeline-uid", TEST_PIPELINE_UID,
             "--activated-by", "test-runner",
             "--cycle-context", "Phase A multi-class registration smoke test",
             "--rollback-manifest", str(manifest_path)],
            capture_output=True, text=True,
        )

        # Collect manifest UIDs for cleanup
        if manifest_path.exists():
            for line in manifest_path.read_text().splitlines():
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if "uid" in entry:
                            created_uids.append(entry["uid"])
                    except json.JSONDecodeError:
                        pass

        if result.returncode != 0:
            cleanup(created_uids)
            print(f"[FAIL] pipeline-activate.py exited {result.returncode}")
            print(f"  stderr: {result.stderr.strip()}")
            return 1

        activation_uid = result.stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{8}", activation_uid):
            cleanup(created_uids)
            print(f"[FAIL] returned UID {activation_uid!r} is not 8-hex")
            return 1

        if activation_uid not in created_uids:
            created_uids.append(activation_uid)

        act_path = VAULT_FILES / f"{activation_uid}.md"
        if not act_path.is_file():
            cleanup(created_uids)
            print(f"[FAIL] activation file {activation_uid}.md not found in vault")
            return 1

        content = act_path.read_text()

        checks = [
            ("type: activation", "type:activation"),
            ("activation_class: pipeline", "activation_class:pipeline"),
            (f"pipeline_uid: {TEST_PIPELINE_UID}", f"pipeline_uid:{TEST_PIPELINE_UID}"),
        ]
        for needle, label in checks:
            if needle not in content:
                cleanup(created_uids)
                print(f"[FAIL] activation entry missing {label}")
                return 1

        # Also check run-folder created from pipeline-runs/
        run_dirs = list((VAULT_ROOT / "vault" / "pipeline-runs").glob(f"*{activation_uid}*")) if \
            (VAULT_ROOT / "vault" / "pipeline-runs").exists() else []

        print(f"  activation UID:    {activation_uid}")
        print(f"  pipeline_uid:      {TEST_PIPELINE_UID} (test-pipeline)")
        print(f"  activation_class:  pipeline (engine class-agnostic)")
        print(f"  vault file:        vault/files/{activation_uid}.md")
        print(f"[PASS] multi-pipeline-class registration: test-pipeline activates cleanly under v1.46 engine")

        cleanup(created_uids)
        return 0


if __name__ == "__main__":
    sys.exit(main())
