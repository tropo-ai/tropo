#!/usr/bin/env python3
"""Smoke test: O_EXCL race-lock enforcement (Phase A acceptance test #6).

Per engine extension spec [51d171f3] §How to Validate Test 6:
  Simulate two simultaneous trigger-step fires on same triggered-spec-uid.
  Engine acquires O_EXCL lock atomically; second invocation refused with ContractError.

Two cases tested:
  Case A: same dev-cycle collision (file pre-exists with matching triggered_by_dev_cycle
           but no triggered_activation_uid) — ContractError "partial failure" message
  Case B: cross-cycle collision (file pre-exists with DIFFERENT triggered_by_dev_cycle)
           — ContractError "collision" message

Both refuse cleanly. Neither silently creates a duplicate activation.

Exit 0: PASS. Exit 1: FAIL.
"""
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent
VAULT_ROOT = SCRIPTS.parents[1]   # argo-os/
VAULT_FILES = VAULT_ROOT / "vault" / "files"
TODAY = time.strftime("%Y-%m-%d")

TEST_PIPELINE_UID = "da3f50dc"   # test-pipeline v1.0 (triggered pipeline target)
EXIT_CONTRACT = 4


def mint_test_uid() -> str:
    while True:
        uid = secrets.token_hex(4)
        if not (VAULT_FILES / f"{uid}.md").exists():
            return uid


def cleanup(*paths: Path) -> None:
    for p in paths:
        if isinstance(p, Path):
            p.unlink(missing_ok=True)


def write_minimal_activation(uid: str, dev_spec_uid: str) -> Path:
    content = (
        f"---\nuid: {uid}\ntype: activation\nactivation_class: pipeline\n"
        f"pipeline_uid: {TEST_PIPELINE_UID}\nstatus: active\nstate: active\n"
        f"activation_root_project: {uid}\nmember_of:\n  - {uid}\n"
        f"dev_spec_uid: {dev_spec_uid}\n---\n\n# Test activation {uid}\n"
    )
    path = VAULT_FILES / f"{uid}.md"
    path.write_text(content)
    return path


def write_minimal_dev_spec(uid: str) -> Path:
    fm = {"uid": uid, "type": "dev-spec", "status": "locked", "stage": "active"}
    fm_yaml = yaml.safe_dump(fm, default_flow_style=False, sort_keys=False)
    path = VAULT_FILES / f"{uid}.md"
    path.write_text(f"---\n{fm_yaml}---\n\n# Test dev-spec {uid}\n")
    return path


def pre_create_triggered_spec(uid: str, triggering_dev_cycle: str,
                               include_activation_uid: bool = False) -> Path:
    """Pre-create a triggered-spec file as if a prior trigger-step partially completed."""
    activation_line = "triggered_activation_uid: PENDING\n" if include_activation_uid else ""
    content = (
        f"---\nuid: {uid}\ntype: test-spec\nstatus: draft\n"
        f"triggered_by_dev_cycle: {triggering_dev_cycle}\n"
        f"{activation_line}---\n\n# Pre-created triggered spec {uid}\n"
    )
    path = VAULT_FILES / f"{uid}.md"
    path.write_text(content)
    return path


def run_trigger_step(activation_uid: str, triggered_spec_uid: str,
                     spec_body: str) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
        tmp.write(spec_body)
        tmp_path = Path(tmp.name)
    try:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "pipeline-runtime.py"),
             "--activation-uid", activation_uid,
             "trigger-step", "dummy-step-uid",
             "--triggered-spec-uid", triggered_spec_uid,
             "--triggered-pipeline-uid", TEST_PIPELINE_UID,
             "--pipeline-class", "test-pipeline",
             "--triggered-spec-body-file", str(tmp_path)],
            capture_output=True, text=True,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_same_cycle_partial_failure_collision() -> bool:
    """Case A: spec exists, same dev-cycle, no triggered_activation_uid → partial failure ContractError."""
    print("  [case A] same-cycle partial failure: spec exists but triggered_activation_uid missing")

    act_uid = mint_test_uid()
    ds_uid = mint_test_uid()
    triggered_spec_uid = mint_test_uid()
    triggered_spec_path = VAULT_FILES / f"{triggered_spec_uid}.md"
    created = []

    try:
        created.append(write_minimal_dev_spec(ds_uid))
        created.append(write_minimal_activation(act_uid, ds_uid))

        # Pre-create spec with same dev-cycle but NO triggered_activation_uid
        created.append(pre_create_triggered_spec(triggered_spec_uid, act_uid,
                                                  include_activation_uid=False))

        spec_body = (
            f"---\nuid: {triggered_spec_uid}\ntype: test-spec\n"
            f"triggered_by_dev_cycle: {act_uid}\n---\n\n# Spec body\n"
        )
        r = run_trigger_step(act_uid, triggered_spec_uid, spec_body)

        if r.returncode != EXIT_CONTRACT:
            print(f"    FAIL: expected exit {EXIT_CONTRACT}, got {r.returncode}")
            print(f"    stderr: {r.stderr.strip()[:300]}")
            return False

        if "partial failure" not in r.stderr:
            print(f"    FAIL: expected 'partial failure' in stderr; got: {r.stderr.strip()[:300]!r}")
            return False

        print(f"    PASS: ContractError raised with 'partial failure' message (exit {EXIT_CONTRACT})")
        return True

    finally:
        cleanup(*created)


def test_cross_cycle_collision() -> bool:
    """Case B: spec exists, DIFFERENT dev-cycle → cross-cycle collision ContractError."""
    print("  [case B] cross-cycle collision: spec owned by different dev-cycle")

    act_uid = mint_test_uid()
    ds_uid = mint_test_uid()
    triggered_spec_uid = mint_test_uid()
    other_cycle_uid = mint_test_uid()   # a different dev-cycle that "owns" the spec
    triggered_spec_path = VAULT_FILES / f"{triggered_spec_uid}.md"
    created = []

    try:
        created.append(write_minimal_dev_spec(ds_uid))
        created.append(write_minimal_activation(act_uid, ds_uid))

        # Pre-create spec owned by a DIFFERENT dev-cycle
        created.append(pre_create_triggered_spec(triggered_spec_uid, other_cycle_uid,
                                                  include_activation_uid=True))

        spec_body = (
            f"---\nuid: {triggered_spec_uid}\ntype: test-spec\n"
            f"triggered_by_dev_cycle: {act_uid}\n---\n\n# Spec body\n"
        )
        r = run_trigger_step(act_uid, triggered_spec_uid, spec_body)

        if r.returncode != EXIT_CONTRACT:
            print(f"    FAIL: expected exit {EXIT_CONTRACT}, got {r.returncode}")
            print(f"    stderr: {r.stderr.strip()[:300]}")
            return False

        if "collision" not in r.stderr:
            print(f"    FAIL: expected 'collision' in stderr; got: {r.stderr.strip()[:300]!r}")
            return False

        if other_cycle_uid not in r.stderr:
            print(f"    FAIL: expected owning dev-cycle UID {other_cycle_uid!r} in collision error")
            return False

        print(f"    PASS: ContractError raised identifying owning dev-cycle {other_cycle_uid} (exit {EXIT_CONTRACT})")
        return True

    finally:
        cleanup(*created)


def main() -> int:
    print("[TEST] O_EXCL race-lock enforcement — two collision scenarios")
    failures = []

    if not test_same_cycle_partial_failure_collision():
        failures.append("Case A: same-cycle partial failure")

    if not test_cross_cycle_collision():
        failures.append("Case B: cross-cycle collision")

    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        return 1

    print("[PASS] O_EXCL race-lock enforcement: both collision cases raise ContractError cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
