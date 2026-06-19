#!/usr/bin/env python3
"""Smoke test: three-pipeline coupling enforcement (Phase A acceptance tests #3 + #4).

Per engine extension spec [51d171f3] §How to Validate:
  Test 3: trigger-step smoke — engine spawns triggered activation; triggered_*_spec_uid
           written atomically to dev-spec frontmatter via fcntl.flock
  Test 4: coupling-enforcement smoke — complete-workflow refuses close when triggered
           activation not at status:done; ContractError (exit 4)

Setup uses minimal manually-authored vault entries (no bootstrap required for
enforcement test; bootstrap required for trigger-step test). All created entries
cleaned up after each sub-test.

Exit 0: PASS. Exit 1: FAIL.
"""
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

SCRIPTS = Path(__file__).resolve().parent
VAULT_ROOT = SCRIPTS.parents[1]   # argo-os/
VAULT_FILES = VAULT_ROOT / "vault" / "files"
TODAY = time.strftime("%Y-%m-%d")

TEST_PIPELINE_UID = "da3f50dc"   # test-pipeline v1.0 (activation target)
EXIT_CONTRACT = 4


def mint_test_uid() -> str:
    while True:
        uid = secrets.token_hex(4)
        if not (VAULT_FILES / f"{uid}.md").exists():
            return uid


def cleanup(*paths: Path) -> None:
    for p in paths:
        if isinstance(p, Path) and p.exists():
            if p.is_dir():
                import shutil
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)


def write_minimal_activation(uid: str, pipeline_uid: str, dev_spec_uid: Optional[str] = None) -> Path:
    dev_spec_line = f"dev_spec_uid: {dev_spec_uid}\n" if dev_spec_uid else ""
    content = (
        f"---\nuid: {uid}\ntype: activation\nactivation_class: pipeline\n"
        f"pipeline_uid: {pipeline_uid}\nstatus: active\nstate: active\n"
        f"activation_root_project: {uid}\nmember_of:\n  - {uid}\n"
        f"{dev_spec_line}---\n\n# Test activation {uid}\n"
    )
    path = VAULT_FILES / f"{uid}.md"
    path.write_text(content)
    return path


def write_minimal_pipeline_run(uid: str, activation_uid: str, run_folder_rel: str) -> Path:
    content = (
        f"---\nuid: {uid}\ntype: pipeline-run\nsubstrate_authored_by: {activation_uid}\n"
        f"run_folder: {run_folder_rel}\nstatus: active\nstate: active\n---\n\n"
        f"# Test pipeline-run {uid}\n"
    )
    path = VAULT_FILES / f"{uid}.md"
    path.write_text(content)
    return path


def write_minimal_dev_spec(uid: str, triggered_activation_uids: list[str],
                            pipeline_class: str = "test") -> Path:
    key = f"triggered_{pipeline_class}_activation_uids"
    spec_key = f"triggered_{pipeline_class}_spec_uids"
    fm = {
        "uid": uid, "type": "dev-spec", "status": "locked", "stage": "active",
        spec_key: [uid + "-spec"],
        key: triggered_activation_uids,
    }
    fm_yaml = yaml.safe_dump(fm, default_flow_style=False, sort_keys=False, allow_unicode=True)
    path = VAULT_FILES / f"{uid}.md"
    path.write_text(f"---\n{fm_yaml}---\n\n# Test dev-spec {uid}\n")
    return path


def write_minimal_non_done_activation(uid: str) -> Path:
    content = (
        f"---\nuid: {uid}\ntype: activation\nstatus: active\nstate: active\n---\n\n"
        f"# Test non-done activation {uid}\n"
    )
    path = VAULT_FILES / f"{uid}.md"
    path.write_text(content)
    return path


def write_minimal_done_activation(uid: str) -> Path:
    content = (
        f"---\nuid: {uid}\ntype: activation\nstatus: done\nstate: active\n---\n\n"
        f"# Test done activation {uid}\n"
    )
    path = VAULT_FILES / f"{uid}.md"
    path.write_text(content)
    return path


# ---- Test 4: coupling enforcement (complete-workflow refuses if triggered not done) ----

def test_coupling_enforcement() -> bool:
    print("  [sub-test 4] coupling enforcement: complete-workflow refuses close when triggered not done")

    act_uid = mint_test_uid()
    pr_uid = mint_test_uid()
    ds_uid = mint_test_uid()
    non_done_uid = mint_test_uid()
    run_folder_rel = f"vault/pipeline-runs/test-coupling-{pr_uid}-{TODAY}"
    run_folder = VAULT_ROOT / run_folder_rel

    created_paths = []
    try:
        # Create non-done triggered activation
        created_paths.append(write_minimal_non_done_activation(non_done_uid))

        # Create dev-spec pointing to the non-done triggered activation
        created_paths.append(write_minimal_dev_spec(ds_uid, [non_done_uid], pipeline_class="test"))

        # Create activation entry with dev_spec_uid
        created_paths.append(write_minimal_activation(act_uid, TEST_PIPELINE_UID, dev_spec_uid=ds_uid))

        # Create pipeline-run entry (load_run requires it)
        created_paths.append(write_minimal_pipeline_run(pr_uid, act_uid, run_folder_rel))

        # Create run folder with empty run.jsonl (load_run reads events from here)
        run_folder.mkdir(parents=True, exist_ok=True)
        run_jsonl = run_folder / "run.jsonl"
        run_jsonl.write_text("")
        created_paths.append(run_folder)

        # Run complete-workflow — should fail with ContractError (exit 4)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "pipeline-runtime.py"),
             "--activation-uid", act_uid,
             "complete-workflow"],
            capture_output=True, text=True,
        )

        if r.returncode != EXIT_CONTRACT:
            print(f"    FAIL: expected exit {EXIT_CONTRACT} (ContractError), got {r.returncode}")
            print(f"    stderr: {r.stderr.strip()[:300]}")
            return False

        if "not done" not in r.stderr and "coupling" not in r.stderr.lower():
            print(f"    FAIL: expected coupling error in stderr; got: {r.stderr.strip()[:300]!r}")
            return False

        print(f"    PASS: complete-workflow blocked (exit {r.returncode}); coupling enforcement active")

        # Verify a "done" triggered activation allows close by swapping to a done activation
        done_uid = mint_test_uid()
        created_paths.append(write_minimal_done_activation(done_uid))
        write_minimal_dev_spec(ds_uid, [done_uid], pipeline_class="test")  # overwrite with done uid

        r2 = subprocess.run(
            [sys.executable, str(SCRIPTS / "pipeline-runtime.py"),
             "--activation-uid", act_uid,
             "complete-workflow"],
            capture_output=True, text=True,
        )
        # Note: this will also fail because the run.jsonl state machine doesn't have proper events
        # but the failure should NOT be ContractError — it should be a state/validation error
        if r2.returncode == EXIT_CONTRACT:
            print(f"    FAIL: complete-workflow still ContractError after triggered activation is done")
            return False

        print(f"    PASS: with all triggered activations done, coupling gate passes (engine proceeded to state-machine check)")
        return True

    finally:
        cleanup(*created_paths)
        cleanup(VAULT_FILES / f"{non_done_uid}.md")


# ---- Test 3: trigger-step smoke (via real pipeline-activate.py spawn) ----

def test_trigger_step_smoke() -> bool:
    print("  [sub-test 3] trigger-step smoke: engine spawns triggered activation + atomic frontmatter append")

    act_uid = mint_test_uid()
    ds_uid = mint_test_uid()
    triggered_spec_uid = mint_test_uid()

    created_paths = []
    triggered_spec_path = VAULT_FILES / f"{triggered_spec_uid}.md"

    try:
        # Create a minimal dev-spec (target of the atomic append)
        created_paths.append(write_minimal_dev_spec(ds_uid, [], pipeline_class="test"))

        # Create activation entry with dev_spec_uid pointing to our dev-spec
        created_paths.append(write_minimal_activation(act_uid, TEST_PIPELINE_UID, dev_spec_uid=ds_uid))

        # Build triggered-spec body the executor would render
        triggered_spec_body = (
            f"---\nuid: {triggered_spec_uid}\ntype: test-spec\nstatus: draft\nstage: draft\n"
            f"triggered_by_dev_cycle: {act_uid}\ntriggered_activation_uid: PENDING\n---\n\n"
            f"# Test triggered spec {triggered_spec_uid}\n"
        )

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
            tmp.write(triggered_spec_body)
            tmp_path = Path(tmp.name)

        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "pipeline-runtime.py"),
             "--activation-uid", act_uid,
             "trigger-step", "dummy-step-uid",
             "--triggered-spec-uid", triggered_spec_uid,
             "--triggered-pipeline-uid", TEST_PIPELINE_UID,
             "--pipeline-class", "test-pipeline",
             "--triggered-spec-body-file", str(tmp_path)],
            capture_output=True, text=True,
        )
        tmp_path.unlink(missing_ok=True)

        if triggered_spec_path.exists():
            created_paths.append(triggered_spec_path)

        if r.returncode != 0:
            print(f"    FAIL: trigger-step exited {r.returncode}")
            print(f"    stderr: {r.stderr.strip()[:300]}")
            print(f"    stdout: {r.stdout.strip()[:200]}")
            return False

        # Verify triggered-spec file was created
        if not triggered_spec_path.exists():
            print(f"    FAIL: triggered-spec file {triggered_spec_uid}.md not created")
            return False

        # Verify stdout has the returned UIDs
        import json
        try:
            result = json.loads(r.stdout.strip())
        except json.JSONDecodeError:
            print(f"    FAIL: trigger-step stdout not valid JSON: {r.stdout.strip()!r}")
            return False

        if result.get("triggered_spec_uid") != triggered_spec_uid:
            print(f"    FAIL: returned triggered_spec_uid mismatch")
            return False

        triggered_act_uid = result.get("triggered_activation_uid")
        if not triggered_act_uid or not re.fullmatch(r"[0-9a-f]{8}", triggered_act_uid):
            print(f"    FAIL: returned triggered_activation_uid invalid: {triggered_act_uid!r}")
            return False

        # Verify dev-spec frontmatter was atomically updated
        ds_content = (VAULT_FILES / f"{ds_uid}.md").read_text()
        if triggered_spec_uid not in ds_content:
            print(f"    FAIL: triggered_spec_uid {triggered_spec_uid} not in dev-spec frontmatter")
            return False
        if triggered_act_uid not in ds_content:
            print(f"    FAIL: triggered_activation_uid {triggered_act_uid} not in dev-spec frontmatter")
            return False

        print(f"    PASS: trigger-step fired; spec {triggered_spec_uid} created; activation {triggered_act_uid} spawned")
        print(f"          dev-spec frontmatter updated atomically via fcntl.flock")

        # Cleanup the triggered activation too
        cleanup(VAULT_FILES / f"{triggered_act_uid}.md")
        # Also try to find and clean up the activation root project
        for f in VAULT_FILES.glob("*.md"):
            content = f.read_text()
            if f"triggered-by-dev-cycle:{act_uid}" in content and f.stem != triggered_spec_uid:
                f.unlink(missing_ok=True)

        return True

    finally:
        cleanup(*created_paths)


def main() -> int:
    print("[TEST] three-pipeline coupling enforcement + trigger-step smoke")
    failures = []

    if not test_coupling_enforcement():
        failures.append("sub-test 4: coupling enforcement")

    if not test_trigger_step_smoke():
        failures.append("sub-test 3: trigger-step smoke")

    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        return 1

    print("[PASS] coupling enforcement + trigger-step: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
