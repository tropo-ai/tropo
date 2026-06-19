#!/usr/bin/env python3
"""AC4 — completion report renders per-step verdict + per-criterion breakdown from run.jsonl.

Tests v1.62 B7: render_completion_report produces a non-empty markdown file at
run_folder/completion-report.md containing per-step sections and a summary.

Exits 0 on pass, non-zero on any assertion failure.
"""
import sys
import json
import tempfile
import shutil
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[4]  # argo-os/
sys.path.insert(0, str(VAULT_ROOT / "vault" / "tools"))

import importlib.util as _ilu
_rt_spec = _ilu.spec_from_file_location("pipeline_runtime", VAULT_ROOT / "vault" / "tools" / "9e7003b1.py")
_rt_mod = _ilu.module_from_spec(_rt_spec)
try:
    _rt_spec.loader.exec_module(_rt_mod)
except SystemExit:
    pass


def make_sample_run_events(activation_uid: str) -> list[dict]:
    return [
        {"event": "step_declared", "step": "step001", "data": {
            "step_id": "step001", "exit_criteria": ["step001.status == done"],
            "step_owner_role": "argus", "verification_class": False}},
        {"event": "step_declared", "step": "step002", "data": {
            "step_id": "step002", "exit_criteria": [],
            "step_owner_role": "talos", "verification_class": False}},
        {"event": "step_started", "step": "step001", "data": {}},
        {"event": "step_completed", "step": "step001", "data": {"artifact_links": ["spec001"]}},
        {"event": "verification_receipt", "step": "step001", "data": {
            "verdict": "pass",
            "per_criterion": [{"criterion": "step001.status == done", "verdict": "pass"}],
            "rubric_scores": {"exit_criteria_coverage": 1.0},
        }},
        {"event": "step_started", "step": "step002", "data": {}},
        {"event": "step_completed", "step": "step002", "data": {"artifact_links": []}},
        {"event": "verification_receipt", "step": "step002", "data": {
            "verdict": "fail",
            "per_criterion": [],
            "rubric_scores": {"exit_criteria_coverage": 0.0},
        }},
    ]


def test_completion_report_renders():
    """B7: render_completion_report writes completion-report.md with correct structure."""
    render_completion_report = _rt_mod.render_completion_report

    tmpdir = tempfile.mkdtemp(prefix="test_v162_ac4_")
    try:
        run_folder = Path(tmpdir)
        activation_uid = "testac401"
        events = make_sample_run_events(activation_uid)

        report = render_completion_report(activation_uid, run_folder, events)

        # Structural checks
        assert "# Completion Report" in report, "Missing report header"
        assert "## Per-Step Verdicts" in report, "Missing per-step section"
        assert "## Summary" in report, "Missing summary section"
        assert "step001" in report, "step001 missing from report"
        assert "step002" in report, "step002 missing from report"
        assert "✓" in report, "No passing step marker"
        assert "✗" in report, "No failing step marker"
        assert "FAIL" in report, "Summary should show FAIL (step002 has no criteria)"

        # File written
        report_path = run_folder / "completion-report.md"
        assert report_path.exists(), "completion-report.md not written to run folder"
        assert len(report_path.read_text()) > 100, "Report file is too short"

        print("  ✓ B7: completion report renders correctly with per-step verdict sections")
        print(f"  ✓ B7: completion-report.md written ({len(report)} chars)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_empty_run_report():
    """B7: render_completion_report handles empty event list without crashing."""
    render_completion_report = _rt_mod.render_completion_report

    tmpdir = tempfile.mkdtemp(prefix="test_v162_ac4_empty_")
    try:
        run_folder = Path(tmpdir)
        report = render_completion_report("emptyrun1", run_folder, [])
        assert "# Completion Report" in report
        assert "Steps total: 0" in report
        print("  ✓ B7: empty run renders without error")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    failures = []
    for test in [test_completion_report_renders, test_empty_run_report]:
        try:
            test()
        except (AssertionError, Exception) as e:
            failures.append(f"{test.__name__}: {e}")
            print(f"  ✗ {test.__name__}: {e}")

    if failures:
        print(f"\nFAIL: {len(failures)} test(s) failed")
        sys.exit(1)
    print("\nPASS: AC4 all assertions green")
    sys.exit(0)
