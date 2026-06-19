#!/usr/bin/env python3
"""B2 regression test — bootstrap-replay-on-def-amendment (Lane B v1.54).

Tests that _auto_heal_stale_def() in pipeline-runtime.py detects when a pipeline
def is amended post-bootstrap and transparently emits step_declared events for the
new steps at next engine tick (load_run call), without manual operator intervention.

Design against the v1.53 concrete case: b67c75e2 bootstrapped from dev-pipeline def
cd1fcd25 at v1.51 shape; v1.52 added notify-step 37996741; b67c75e2 never picked it up.
Under B1 auto-heal, load_run would have detected the version delta and declared it.

Structural acceptance: after amending def from version A to A+1 (adding 1 new step),
the next load_run call returns state with the new step in declared status.

Exit: 0 = PASS, 1 = FAIL
"""

import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = VAULT_ROOT / ".tropo" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import importlib.util as _ilu

def _load_module(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_pr = _load_module("pipeline_runtime", SCRIPTS_DIR / "pipeline-runtime.py")
load_run = _pr.load_run
action_bootstrap = _pr.action_bootstrap
read_vault_entry = _pr.read_vault_entry
write_vault_entry = _pr.write_vault_entry
derive_state = _pr.derive_state
load_existing_uids = _pr.load_existing_uids
mint_uid = _pr.mint_uid
VAULT_FILES = _pr.VAULT_FILES
TODAY = _pr.TODAY

CLEANUP: list[Path] = []


def _write_vault(uid: str, fm: dict, body: str = "") -> Path:
    path = VAULT_FILES / f"{uid}.md"
    import yaml
    fm_yaml = yaml.safe_dump(fm, default_flow_style=False, sort_keys=False,
                             allow_unicode=True, width=200)
    path.write_text(f"---\n{fm_yaml}---\n{body}\n", encoding="utf-8")
    CLEANUP.append(path)
    return path


def _remove(path: Path):
    try:
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            import shutil
            shutil.rmtree(path)
    except OSError:
        pass


def structural_check(label: str, condition: bool, detail: str = ""):
    marker = "PASS" if condition else "FAIL"
    msg = f"  [{marker}] {label}"
    if detail:
        msg += f": {detail}"
    print(msg)
    return condition


def main() -> int:
    print("[TEST] B1 bootstrap-replay-on-def-amendment v1.54")
    existing = load_existing_uids()

    # ── Mint UIDs ─────────────────────────────────────────────────────────────
    step_a_uid = mint_uid(existing)   # original step (in def v1.0)
    step_b_uid = mint_uid(existing)   # new step added in def v1.1
    pipeline_uid = mint_uid(existing)
    activation_uid = mint_uid(existing)
    root_uid = mint_uid(existing)

    run_folder_path: Path | None = None

    try:
        # ── Def v1.0 — one step ───────────────────────────────────────────────
        step_a = {
            "uid": step_a_uid, "type": "WorkflowNode", "name": "Step A",
            "step_owner_role": "talos", "verification_class": False,
        }
        _write_vault(step_a_uid, step_a)

        pipeline_fm_v1 = {
            "uid": pipeline_uid, "type": "pipeline", "name": "b1-test-pipeline",
            "version": "1.0", "modified": TODAY, "status": "active",
            "children": [step_a_uid],
        }
        _write_vault(pipeline_uid, pipeline_fm_v1, "# b1-test-pipeline\n")

        # ── Activation + activation-root project ──────────────────────────────
        root_fm = {
            "uid": root_uid, "type": "project", "title": "B1 test root",
            "status": "active", "state": "active",
        }
        _write_vault(root_uid, root_fm)

        activation_fm = {
            "uid": activation_uid, "type": "activation", "activation_class": "pipeline",
            "pipeline_uid": pipeline_uid, "activated_by": "test",
            "activation_root_project": root_uid, "status": "active",
            "cycle_context": "b1-regression-test",
        }
        _write_vault(activation_uid, activation_fm)

        # ── Bootstrap against def v1.0 ────────────────────────────────────────
        print("  [1] bootstrapping activation against def v1.0 (1 step)...")
        contract_path = Path(tempfile.mktemp(suffix=".json"))
        CLEANUP.append(contract_path)
        contract_data = {
            "skips_authorized_upfront": [],
            "additional_steps_added": [],
            "trust_overrides": [],
            "human_instructions": "b1 regression test",
            "supersession_reason": None,
            "supersedes_activation": None,
        }
        contract_path.write_text(json.dumps(contract_data))

        run_uid = action_bootstrap(activation_uid, str(contract_path), dry_run=False)
        print(f"      pipeline-run UID: {run_uid}")

        # Record run folder for cleanup
        pr_entry = read_vault_entry(run_uid)
        if pr_entry:
            run_folder_path = VAULT_ROOT / pr_entry["frontmatter"]["run_folder"]
            CLEANUP.append(run_folder_path)
            CLEANUP.append(VAULT_FILES / f"{run_uid}.md")

        # Verify step A is declared
        _, _, _, events_v1, state_v1 = load_run(activation_uid)
        ok1 = structural_check(
            "step A declared after bootstrap",
            step_a_uid in state_v1["step_status"],
            f"step_status keys: {list(state_v1['step_status'].keys())}"
        )
        ok2 = structural_check(
            "step B NOT declared (not in def v1.0 yet)",
            step_b_uid not in state_v1["step_status"],
        )

        # ── Amend def to v1.1 — add step B ───────────────────────────────────
        print("  [2] amending pipeline def v1.0 → v1.1 (adding step B)...")
        step_b = {
            "uid": step_b_uid, "type": "WorkflowNode", "name": "Step B (new)",
            "step_owner_role": "talos", "verification_class": False,
        }
        _write_vault(step_b_uid, step_b)

        pipeline_fm_v2 = dict(pipeline_fm_v1)
        pipeline_fm_v2["version"] = "1.1"
        pipeline_fm_v2["children"] = [step_a_uid, step_b_uid]
        _write_vault(pipeline_uid, pipeline_fm_v2, "# b1-test-pipeline v1.1\n")

        # ── Next load_run — B1 auto-heal should pick up step B ───────────────
        print("  [3] calling load_run — B1 auto-heal should emit step_declared for step B...")
        _, _, _, events_v2, state_v2 = load_run(activation_uid)

        ok3 = structural_check(
            "step A still declared after auto-heal",
            step_a_uid in state_v2["step_status"],
        )
        ok4 = structural_check(
            "step B NOW declared (auto-healed from def v1.1)",
            step_b_uid in state_v2["step_status"],
            f"step_status keys: {list(state_v2['step_status'].keys())}"
        )

        # Verify pipeline-run version was updated
        pr_reloaded = read_vault_entry(run_uid)
        ok5 = structural_check(
            "pipeline-run pipeline_version updated to 1.1",
            pr_reloaded is not None and
            pr_reloaded["frontmatter"].get("pipeline_version") == "1.1",
            f"got: {pr_reloaded['frontmatter'].get('pipeline_version') if pr_reloaded else 'None'}"
        )

        # ── Second load_run — no-op (already reconciled) ─────────────────────
        print("  [4] second load_run — should be no-op (already at v1.1)...")
        events_before = len(events_v2)
        _, _, _, events_v3, state_v3 = load_run(activation_uid)
        ok6 = structural_check(
            "no new events emitted on second load_run (idempotent)",
            len(events_v3) == events_before,
            f"before: {events_before}, after: {len(events_v3)}"
        )

        all_pass = all([ok1, ok2, ok3, ok4, ok5, ok6])
        verdict = "PASS" if all_pass else "FAIL"
        print(f"\n[{verdict}] B1 bootstrap-replay-on-def-amendment: "
              f"{'all structural checks passed' if all_pass else 'one or more checks FAILED'}")
        return 0 if all_pass else 1

    finally:
        # Restore pipeline def to v1.0 shape (so vault stays clean)
        try:
            _write_vault(pipeline_uid, pipeline_fm_v1, "# b1-test-pipeline\n")
        except Exception:
            pass
        # Cleanup test artifacts
        print("  [cleanup] removing test vault entries...")
        for path in CLEANUP:
            _remove(path)
        print(f"  [cleanup] removed {len(CLEANUP)} created paths")


if __name__ == "__main__":
    sys.exit(main())
