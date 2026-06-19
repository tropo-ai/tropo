"""pipeline_test_helpers.py — Synthetic run scaffolding for v1.62 engine tests.

Wires directly to the real pipeline-runtime engine (vault/tools/9e7003b1.py) so
test assertions exercise the actual code paths, not vacuous mocks.

Used by:
  test_v162_ac1_empty_criteria_fails.py — B1 (empty criteria → FAIL) + B3 (all-steps-verified gate)
"""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path
from typing import Any

VAULT_ROOT = Path(__file__).resolve().parents[3]  # argo-os/


def _load_engine():
    """Load pipeline-runtime 9e7003b1 as a module."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_runtime",
        VAULT_ROOT / "vault" / "tools" / "9e7003b1.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = _load_engine()
    return _ENGINE


def make_synthetic_run(run_folder: Path, steps: list[dict]) -> list[dict]:
    """Create a minimal in-memory run.jsonl in run_folder for the given step list.

    Each step dict must have 'uid' and may have:
      exit_criteria: list[str]   (empty → B1 should FAIL)
      verification_class: bool   (False → auto-receipt; True → explicit verify needed)
    """
    run_folder.mkdir(parents=True, exist_ok=True)
    eng = _engine()

    now = "2026-01-01T00:00:00Z"
    events: list[dict] = []

    # run_created
    events.append({"event": "run_created", "ts": now, "actor": "test", "step": None,
                   "data": {"pipeline": "test_pipeline"}, "schema_version": 2,
                   "trace_id": "synthetic01", "span_id": "sp0001", "parent_span_id": None})

    # activation_contract_locked
    steps_locked = [
        {
            "step_id": s["uid"],
            "step_owner_role": s.get("step_owner_role", "talos"),
            "step_verifier_role": "same-as-executor",
            "verification_class": s.get("verification_class", False),
            "depends_on_steps": [],
            "exit_criteria": s.get("exit_criteria", []),
            "trust_level": "auto-with-verification",
            "retry_policy": {"max_retries": 0, "backoff": "linear"},
            "timeout_hours": 24,
            "compensation_step_id": None,
            "instructions_ref": None,
        }
        for s in steps
    ]
    events.append({"event": "activation_contract_locked", "ts": now, "actor": "test", "step": None,
                   "data": {"steps_locked": steps_locked, "human_instructions": "test run",
                            "supersession_reason": None, "supersedes_activation": None},
                   "schema_version": 2, "trace_id": "synthetic01",
                   "span_id": "sp0002", "parent_span_id": "sp0001"})

    # step_declared for each step
    for step_def in steps_locked:
        events.append({"event": "step_declared", "ts": now, "actor": "test",
                       "step": step_def["step_id"], "data": step_def,
                       "schema_version": 2, "trace_id": "synthetic01",
                       "span_id": f"sp_{step_def['step_id']}", "parent_span_id": "sp0002"})

    # Write to run.jsonl
    run_jsonl = run_folder / "run.jsonl"
    run_jsonl.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    # Derive and write run.state.json
    state = eng.derive_state(events)
    _write_state(run_folder, state)

    return events


def _write_state(run_folder: Path, state: dict) -> None:
    state_path = run_folder / "run.state.json"
    # pause_resumed_pending is a set in derive_state — convert to sorted list for JSON
    serializable = dict(state)
    if isinstance(serializable.get("pause_resumed_pending"), set):
        serializable["pause_resumed_pending"] = sorted(serializable["pause_resumed_pending"])
    state_path.write_text(json.dumps(serializable, indent=2))


def _read_events(run_folder: Path) -> list[dict]:
    run_jsonl = run_folder / "run.jsonl"
    return [json.loads(l) for l in run_jsonl.read_text().splitlines() if l.strip()]


def _append_event(run_folder: Path, event: dict) -> None:
    run_jsonl = run_folder / "run.jsonl"
    with run_jsonl.open("a") as f:
        f.write(json.dumps(event) + "\n")


def synthetic_step_start(run_folder: Path, events: list[dict], step_uid: str) -> str:
    """Append a step_started event and update state. Returns 'started' or error string."""
    eng = _engine()
    now = "2026-01-01T00:01:00Z"
    ev = eng.make_event("step_started", "test", step=step_uid,
                        trace_id="synthetic01", parent_span_id=None, data={})
    _append_event(run_folder, ev)
    events.append(ev)
    state = eng.derive_state(events)
    _write_state(run_folder, state)
    return "started"


def synthetic_step_complete(
    run_folder: Path,
    events: list[dict],
    step_uid: str,
    artifact_links: list[str] | None = None,
    natural_verdict: str | None = None,
) -> str:
    """Append step_completed + auto-verification_receipt for vc:false steps. Returns 'completed'."""
    eng = _engine()
    decls = eng.get_step_declarations(events)
    decl = decls.get(step_uid, {})
    parent = eng.find_event_span(events, "step_started", step_uid)

    data: dict = {"artifact_links": artifact_links or []}
    if decl.get("verification_class") and natural_verdict:
        data["natural_verdict"] = natural_verdict

    ev = eng.make_event("step_completed", "test", step=step_uid,
                        trace_id="synthetic01", parent_span_id=parent, data=data)
    _append_event(run_folder, ev)
    events.append(ev)

    # Auto-receipt for vc:false steps — always pass (vc-conditional, v1.63).
    # B1 (empty-criteria FAIL) gates vc:true steps only; vc:false have no verification gate.
    if not decl.get("verification_class", True):
        auto_criteria = decl.get("exit_criteria") or []
        auto_verdict = "pass"
        auto_rationale = (
            "verification_class:false — completed is terminal; auto-receipt pass."
            if not auto_criteria else
            "verification_class:false — completed is terminal; criteria declared, auto-receipt pass."
        )
        receipt = eng.make_event("verification_receipt", "test", step=step_uid,
                                 trace_id="synthetic01", parent_span_id=ev["span_id"],
                                 data={
                                     "verifier_role_resolved": "same-as-executor",
                                     "verdict": auto_verdict,
                                     "per_criterion": [],
                                     "rubric_scores": {"exit_criteria_coverage": 1.0 if auto_criteria else 0.0},
                                     "overall_rationale": auto_rationale,
                                 })
        _append_event(run_folder, receipt)
        events.append(receipt)

    state = eng.derive_state(events)
    _write_state(run_folder, state)
    return "completed"


def clean_synthetic_run(run_folder: Path) -> None:
    """Remove the synthetic run folder."""
    import shutil
    shutil.rmtree(run_folder, ignore_errors=True)
