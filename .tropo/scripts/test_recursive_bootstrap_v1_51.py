#!/usr/bin/env python3
"""Smoke test: recursive-bootstrap v1.51 (Phase A acceptance test #5).

Per engine extension spec [51d171f3] §How to Validate Test 5:
  Fire dev-pipeline (cd1fcd25) with dev-spec (54fdd9ce) via pipeline-activate.py.
  Bootstrap the activation. Fire trigger-step for doc-pipeline (5a4337ff) +
  test-pipeline (da3f50dc). Mark triggered activations done. Run complete-workflow.
  Assert structural state: dev-spec frontmatter has triggered UIDs; triggered
  activation entries exist; activation status retired.

verification_method: structural_check

Covered behaviors (c5ff0091 Behavior 9):
  - dev-pipeline activation with dev-spec input creates activation.dev_spec_uid
  - trigger-step for doc-pipeline populates triggered_doc_spec_uids + triggered_doc_activation_uids
  - trigger-step for test-pipeline populates triggered_test_spec_uids + triggered_test_activation_uids
  - complete-workflow exits 0 when all triggered activations at status:done
  - activation status = retired after complete-workflow

Exit 0: PASS. Exit 1: FAIL.
"""
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import yaml

SCRIPTS = Path(__file__).resolve().parent
VAULT_ROOT = SCRIPTS.parents[1]   # argo-os/
VAULT_FILES = VAULT_ROOT / "vault" / "files"
TODAY = time.strftime("%Y-%m-%d")

DEV_PIPELINE_UID = "cd1fcd25"   # dev-pipeline
DEV_SPEC_UID = "54fdd9ce"       # recursive-bootstrap dev-spec (real vault entry; restored after test)
DOC_PIPELINE_UID = "5a4337ff"   # doc-pipeline v1.0 (Orpheus O11 LOCKED)
TEST_PIPELINE_UID = "da3f50dc"  # test-pipeline v1.0 (Vela V51 LOCKED)

PIPELINE_RUNTIME = SCRIPTS / "pipeline-runtime.py"
PIPELINE_ACTIVATE = SCRIPTS / "pipeline-activate.py"


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


def collect_manifest_uids(pipeline_uid: str) -> list:
    """Return all UIDs from the pipeline-activate rollback manifest for today's run."""
    manifest_dir = VAULT_ROOT / "playbook-runs" / f"pipeline-activate-{pipeline_uid}-{TODAY}"
    manifest_path = manifest_dir / "cascade-rollback.jsonl"
    uids = []
    if manifest_path.exists():
        for line in manifest_path.read_text().splitlines():
            try:
                entry = json.loads(line)
                uid = entry.get("uid")
                if uid:
                    uids.append(uid)
            except (json.JSONDecodeError, AttributeError):
                pass
    return uids


def activate_pipeline(pipeline_uid: str, dev_spec_uid: Optional[str] = None) -> str:
    """Run pipeline-activate.py; return act_uid (stdout). Raises on failure."""
    cmd = [
        sys.executable, str(PIPELINE_ACTIVATE),
        "--pipeline-uid", pipeline_uid,
        "--activated-by", "test-recursive-bootstrap",
        "--cycle-context", "Phase A acceptance test 5 — recursive-bootstrap v1.51",
    ]
    if dev_spec_uid:
        cmd += ["--dev-spec-uid", dev_spec_uid]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"pipeline-activate.py ({pipeline_uid}) exited {r.returncode}: {r.stderr.strip()[:400]}")
    act_uid = r.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{8}", act_uid):
        raise RuntimeError(f"pipeline-activate.py returned invalid UID: {act_uid!r}")
    return act_uid


def bootstrap_activation(act_uid: str) -> str:
    """Bootstrap activation with empty contract-input; return pipeline-run UID."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp.write("{}\n")
        contract_path = Path(tmp.name)
    try:
        r = subprocess.run(
            [sys.executable, str(PIPELINE_RUNTIME),
             "--activation-uid", act_uid,
             "bootstrap",
             "--contract-input", str(contract_path)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"bootstrap exited {r.returncode}: {r.stderr.strip()[:400]}")
    finally:
        contract_path.unlink(missing_ok=True)

    # Locate the pipeline-run entry created by bootstrap
    for f in VAULT_FILES.glob("*.md"):
        try:
            content = f.read_text()
            if f"substrate_authored_by: {act_uid}" in content and "type: pipeline-run" in content:
                return f.stem
        except OSError:
            pass
    raise RuntimeError(f"bootstrap did not create a pipeline-run entry for {act_uid!r}")


def trigger_pipeline(act_uid: str, triggered_pipeline_uid: str,
                     pipeline_class: str, spec_type: str) -> tuple:
    """Fire trigger-step; return (triggered_spec_uid, triggered_act_uid)."""
    triggered_spec_uid = mint_test_uid()
    spec_body = (
        f"---\nuid: {triggered_spec_uid}\ntype: {spec_type}\nstatus: draft\nstage: draft\n"
        f"triggered_by_dev_cycle: {act_uid}\ntriggered_activation_uid: PENDING\n---\n\n"
        f"# Test triggered spec {triggered_spec_uid}\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
        tmp.write(spec_body)
        spec_body_path = Path(tmp.name)
    try:
        r = subprocess.run(
            [sys.executable, str(PIPELINE_RUNTIME),
             "--activation-uid", act_uid,
             "trigger-step", "dummy-step-uid",
             "--triggered-spec-uid", triggered_spec_uid,
             "--triggered-pipeline-uid", triggered_pipeline_uid,
             "--pipeline-class", pipeline_class,
             "--triggered-spec-body-file", str(spec_body_path)],
            capture_output=True, text=True,
        )
    finally:
        spec_body_path.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"trigger-step ({pipeline_class}) exited {r.returncode}: {r.stderr.strip()[:400]}")
    try:
        result = json.loads(r.stdout.strip())
    except json.JSONDecodeError:
        raise RuntimeError(f"trigger-step stdout not valid JSON: {r.stdout.strip()!r}")
    triggered_act_uid = result.get("triggered_activation_uid")
    if not triggered_act_uid or not re.fullmatch(r"[0-9a-f]{8}", triggered_act_uid):
        raise RuntimeError(f"trigger-step ({pipeline_class}) returned invalid activation UID: {triggered_act_uid!r}")
    return triggered_spec_uid, triggered_act_uid


def mark_activation_done(uid: str) -> None:
    path = VAULT_FILES / f"{uid}.md"
    content = path.read_text()
    # Replace status field in frontmatter; state stays active
    content = re.sub(r"(?m)^status: active$", "status: done", content, count=1)
    path.write_text(content)


def get_pr_run_folder(pr_uid: str) -> Optional[Path]:
    path = VAULT_FILES / f"{pr_uid}.md"
    if not path.exists():
        return None
    content = path.read_text()
    m = re.search(r"run_folder:\s*(.+)", content)
    if not m:
        return None
    return VAULT_ROOT / m.group(1).strip()


def main() -> int:
    print("[TEST] recursive-bootstrap v1.51: dev-pipeline + dev-spec + trigger-step + complete-workflow")

    # Guard: dev-spec must exist
    dev_spec_path = VAULT_FILES / f"{DEV_SPEC_UID}.md"
    if not dev_spec_path.exists():
        print(f"  FAIL: dev-spec {DEV_SPEC_UID} not found in vault")
        return 1

    # Snapshot original dev-spec content for restoration after test (makes test repeatable)
    original_dev_spec = dev_spec_path.read_text()

    # Pre-check: dev-spec should not have pre-existing triggered UIDs (would block coupling gate)
    pre_fm = yaml.safe_load(original_dev_spec.split("\n---\n")[0].lstrip("---\n")) or {}
    for field in ("triggered_doc_activation_uids", "triggered_test_activation_uids"):
        existing = pre_fm.get(field, []) or []
        if existing:
            print(f"  FAIL pre-check: dev-spec {DEV_SPEC_UID} already has {field}={existing}")
            print(f"       Previous test run may not have cleaned up. Restore dev-spec manually.")
            return 1

    act_uid: Optional[str] = None
    pr_uid: Optional[str] = None
    doc_spec_uid: Optional[str] = None
    doc_act_uid: Optional[str] = None
    test_spec_uid: Optional[str] = None
    test_act_uid: Optional[str] = None

    try:
        # Step 1: Activate dev-pipeline with dev-spec
        print(f"  [1] activating dev-pipeline ({DEV_PIPELINE_UID}) with dev-spec ({DEV_SPEC_UID})")
        act_uid = activate_pipeline(DEV_PIPELINE_UID, dev_spec_uid=DEV_SPEC_UID)
        print(f"      activation UID: {act_uid}")

        act_content = (VAULT_FILES / f"{act_uid}.md").read_text()
        if "type: activation" not in act_content:
            print(f"  FAIL: activation entry missing 'type: activation'")
            return 1
        if f"dev_spec_uid: {DEV_SPEC_UID}" not in act_content:
            print(f"  FAIL: activation entry missing 'dev_spec_uid: {DEV_SPEC_UID}'")
            return 1
        print(f"      verified: type=activation, dev_spec_uid={DEV_SPEC_UID} present")

        # Step 2: Bootstrap
        print(f"  [2] bootstrapping activation {act_uid}")
        pr_uid = bootstrap_activation(act_uid)
        print(f"      pipeline-run UID: {pr_uid}")

        # Step 3: trigger-step for doc-pipeline
        print(f"  [3] trigger-step: doc-pipeline ({DOC_PIPELINE_UID})")
        doc_spec_uid, doc_act_uid = trigger_pipeline(
            act_uid, DOC_PIPELINE_UID, "doc-pipeline", "doc-spec")
        print(f"      doc-spec UID: {doc_spec_uid}")
        print(f"      doc-activation UID: {doc_act_uid}")

        # Step 4: trigger-step for test-pipeline
        print(f"  [4] trigger-step: test-pipeline ({TEST_PIPELINE_UID})")
        test_spec_uid, test_act_uid = trigger_pipeline(
            act_uid, TEST_PIPELINE_UID, "test-pipeline", "test-spec")
        print(f"      test-spec UID: {test_spec_uid}")
        print(f"      test-activation UID: {test_act_uid}")

        # Step 5: Structural assertion — dev-spec frontmatter updated with triggered UIDs
        print(f"  [5] structural check: dev-spec {DEV_SPEC_UID} frontmatter")
        updated_content = dev_spec_path.read_text()
        fm_raw = updated_content.split("\n---\n")[0].lstrip("---\n")
        ds_fm = yaml.safe_load(fm_raw) or {}

        failures = []
        for field, expected_uid, label in [
            ("triggered_doc_spec_uids", doc_spec_uid, "doc-spec UID"),
            ("triggered_doc_activation_uids", doc_act_uid, "doc-activation UID"),
            ("triggered_test_spec_uids", test_spec_uid, "test-spec UID"),
            ("triggered_test_activation_uids", test_act_uid, "test-activation UID"),
        ]:
            uid_list = ds_fm.get(field, []) or []
            if expected_uid not in uid_list:
                failures.append(f"  {field} missing {label} {expected_uid!r}; got {uid_list!r}")

        if failures:
            for f in failures:
                print(f"  FAIL: {f}")
            return 1
        print(f"      PASS: all four triggered UIDs present in dev-spec frontmatter")

        # Step 6: Triggered spec + activation vault files exist
        print(f"  [6] structural check: triggered vault files exist")
        for uid, label in [
            (doc_spec_uid, "doc-spec"), (doc_act_uid, "doc-activation"),
            (test_spec_uid, "test-spec"), (test_act_uid, "test-activation"),
        ]:
            if not (VAULT_FILES / f"{uid}.md").exists():
                print(f"  FAIL: {label} file {uid}.md not found")
                return 1
        print(f"      PASS: doc-spec, doc-activation, test-spec, test-activation files exist")

        # Step 7: Mark both triggered activations done
        print(f"  [7] marking triggered activations done: {doc_act_uid}, {test_act_uid}")
        mark_activation_done(doc_act_uid)
        mark_activation_done(test_act_uid)

        # Step 8: complete-workflow — coupling satisfied; expect exit 0
        print(f"  [8] complete-workflow with coupling satisfied")
        r = subprocess.run(
            [sys.executable, str(PIPELINE_RUNTIME),
             "--activation-uid", act_uid,
             "complete-workflow"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"  FAIL: complete-workflow exited {r.returncode} (expected 0)")
            print(f"        stderr: {r.stderr.strip()[:400]}")
            return 1
        print(f"      PASS: complete-workflow exited 0")

        # Step 9: Activation status = retired
        print(f"  [9] structural check: activation {act_uid} status after complete-workflow")
        act_post = (VAULT_FILES / f"{act_uid}.md").read_text()
        if "status: retired" not in act_post:
            print(f"  FAIL: activation status != 'retired' after complete-workflow")
            return 1
        print(f"      PASS: activation status = retired")

        print(f"\n[PASS] recursive-bootstrap v1.51: all structural checks passed")
        return 0

    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    finally:
        # Restore dev-spec to original content (test is repeatable)
        dev_spec_path.write_text(original_dev_spec)
        print(f"  [cleanup] dev-spec {DEV_SPEC_UID} restored to pre-test state")

        # Collect and remove all vault entries created during this test
        paths_to_remove: list = []

        # pipeline-run entry + run folder
        if pr_uid:
            paths_to_remove.append(VAULT_FILES / f"{pr_uid}.md")
            pr_folder = get_pr_run_folder(pr_uid)
            if pr_folder:
                paths_to_remove.append(pr_folder)

        # Triggered spec files
        for uid in filter(None, [doc_spec_uid, test_spec_uid]):
            paths_to_remove.append(VAULT_FILES / f"{uid}.md")

        # Triggered activation entries + their root projects (via pipeline-activate manifests)
        for pipeline_uid in [DOC_PIPELINE_UID, TEST_PIPELINE_UID]:
            for uid in collect_manifest_uids(pipeline_uid):
                paths_to_remove.append(VAULT_FILES / f"{uid}.md")
            mdir = VAULT_ROOT / "playbook-runs" / f"pipeline-activate-{pipeline_uid}-{TODAY}"
            paths_to_remove.append(mdir)

        # Dev-pipeline activation + root project (via its manifest)
        for uid in collect_manifest_uids(DEV_PIPELINE_UID):
            paths_to_remove.append(VAULT_FILES / f"{uid}.md")
        dev_mdir = VAULT_ROOT / "playbook-runs" / f"pipeline-activate-{DEV_PIPELINE_UID}-{TODAY}"
        paths_to_remove.append(dev_mdir)

        cleanup(*paths_to_remove)
        print(f"  [cleanup] removed {len(paths_to_remove)} created paths")


if __name__ == "__main__":
    sys.exit(main())
