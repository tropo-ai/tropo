#!/usr/bin/env python3
"""Smoke test: activation-input validation (Phase A acceptance test #2).

Per engine extension spec [51d171f3] §Activation-Input Validation:
  - pipeline-activate.py --pipeline-uid <dev-pipeline-uid> WITHOUT --dev-spec-uid
    must emit WARN at v1.51 grace period (exit 0)
  - WITH invalid hex: exit 3 (arg error)
  - WITH non-existent UID: exit 1 (validation failure)
  - WITH valid locked dev-spec (54fdd9ce): exit 0 + dev_spec_uid written to activation

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

DEV_PIPELINE_UID = "cd1fcd25"   # dev-pipeline v1.2.0
DEV_SPEC_UID = "54fdd9ce"       # v1.51 recursive-bootstrap dev-spec, LOCKED


def cleanup(uids: list[str]) -> None:
    for uid in uids:
        p = VAULT_FILES / f"{uid}.md"
        if p.exists():
            p.unlink()


def run_activate(extra_args: list[str], manifest_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "pipeline-activate.py"),
         "--pipeline-uid", DEV_PIPELINE_UID,
         "--activated-by", "test-runner",
         "--cycle-context", "Phase A activation-input smoke test",
         "--rollback-manifest", str(manifest_path),
         *extra_args],
        capture_output=True, text=True,
    )


def collect_manifest_uids(manifest_path: Path) -> list[str]:
    uids = []
    if manifest_path.exists():
        for line in manifest_path.read_text().splitlines():
            if line.strip():
                try:
                    entry = json.loads(line)
                    if "uid" in entry:
                        uids.append(entry["uid"])
                except json.JSONDecodeError:
                    pass
    return uids


def main() -> int:
    print(f"[TEST] activation-input validation (dev-pipeline={DEV_PIPELINE_UID})")
    failures = []

    # Case 1: no --dev-spec-uid on dev-pipeline → WARN at v1.51 grace period (exit 0)
    with tempfile.TemporaryDirectory() as tmpdir:
        mp = Path(tmpdir) / "manifest.jsonl"
        r = run_activate([], mp)
        uids = collect_manifest_uids(mp)
        cleanup(uids)
        if r.returncode != 0:
            failures.append(f"Case 1: expected exit 0 for missing --dev-spec-uid (grace period), got {r.returncode}")
        elif "[WARN]" not in r.stderr and "dev-spec" not in r.stderr.lower():
            failures.append(f"Case 1: expected [WARN] about missing --dev-spec-uid in stderr, got: {r.stderr[:200]!r}")
        else:
            print(f"  Case 1 PASS: missing --dev-spec-uid → exit 0 + WARN (grace period)")

    # Case 2: invalid hex --dev-spec-uid → exit 3 (arg error)
    with tempfile.TemporaryDirectory() as tmpdir:
        mp = Path(tmpdir) / "manifest.jsonl"
        r = run_activate(["--dev-spec-uid", "not-hex!"], mp)
        cleanup(collect_manifest_uids(mp))
        if r.returncode != 3:
            failures.append(f"Case 2: expected exit 3 for invalid hex dev-spec-uid, got {r.returncode}")
        else:
            print(f"  Case 2 PASS: invalid hex --dev-spec-uid → exit 3 (arg error)")

    # Case 3: non-existent UID → exit 1 (validation failure)
    with tempfile.TemporaryDirectory() as tmpdir:
        mp = Path(tmpdir) / "manifest.jsonl"
        r = run_activate(["--dev-spec-uid", "00000000"], mp)
        cleanup(collect_manifest_uids(mp))
        if r.returncode != 1:
            failures.append(f"Case 3: expected exit 1 for non-existent dev-spec-uid, got {r.returncode}")
        else:
            print(f"  Case 3 PASS: non-existent --dev-spec-uid → exit 1 (validation failure)")

    # Case 4: valid locked dev-spec (54fdd9ce) → exit 0 + dev_spec_uid in activation frontmatter
    with tempfile.TemporaryDirectory() as tmpdir:
        mp = Path(tmpdir) / "manifest.jsonl"
        r = run_activate(["--dev-spec-uid", DEV_SPEC_UID], mp)
        uids = collect_manifest_uids(mp)
        activation_uid = r.stdout.strip() if r.returncode == 0 else None
        if r.returncode != 0:
            cleanup(uids)
            failures.append(f"Case 4: expected exit 0 with valid dev-spec-uid, got {r.returncode}: {r.stderr.strip()}")
        else:
            act_path = VAULT_FILES / f"{activation_uid}.md"
            if not act_path.is_file():
                failures.append(f"Case 4: activation file {activation_uid}.md not found")
            else:
                content = act_path.read_text()
                if f"dev_spec_uid: {DEV_SPEC_UID}" not in content:
                    failures.append(f"Case 4: dev_spec_uid:{DEV_SPEC_UID} not in activation frontmatter")
                else:
                    print(f"  Case 4 PASS: valid --dev-spec-uid → exit 0 + dev_spec_uid:{DEV_SPEC_UID} in activation")
            cleanup(uids)

    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        return 1

    print(f"[PASS] activation-input validation: all 4 cases correct")
    return 0


if __name__ == "__main__":
    sys.exit(main())
