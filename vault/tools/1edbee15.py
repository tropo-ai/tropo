#!/usr/bin/env python3
"""
---
uid: 1edbee15
name: loop-brakes-watchdog
type: tool
status: active
owner: talos
domain: "The platform-enforced BRAKES circuit-breaker + human checkpoints for loop-runs (v1.71 S1)."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/1edbee15.py"
script_path: vault/tools/1edbee15.py
spawnable_by:
  - launchd
input:
  type: object
  description: "Scans active loop-runs and enforces hard brakes (spend, wall-clock) and human checkpoints."
created: 2026-06-14
created_by: argus-a112
modified: 2026-06-16
modified_by: talos-t20 (v1.71 build delta)
governed_by: d5e1b4a3
member_of:
  - c7e4f9a2
realizes_dev_spec: 9da979b2
schema_version: 2
belt: false
title: "loop-brakes-watchdog — ground-truth circuit-breaker + human checkpoints"
trigger_description: "Launchd-fired watchdog that kills runaway loop-runs and enforces human checkpoints."
---
"""

import json
import os
import sys
import time
from pathlib import Path

def check_loop_run_start_preconditions(run_dir: Path) -> bool:
    """LOOP-RUN ENGINE FAIL-CLOSE: Refuse to start if contract is missing or invalid."""
    run_jsonl = run_dir / 'run.jsonl'
    if not run_jsonl.exists():
        print(f"FAIL-CLOSE: {run_dir} has no run.jsonl")
        return False
        
    contract_locked = False
    try:
        with open(run_jsonl, 'r') as f:
            for line in f:
                ev = json.loads(line)
                if ev.get("event") == "loop_contract_locked":
                    contract_locked = True
                    brakes = ev.get("brakes")
                    goal = ev.get("goal")
                    verifier = ev.get("verifier")
                    policy = ev.get("policy", {})
                    
                    if not brakes or not goal or not verifier:
                        print(f"FAIL-CLOSE: {run_dir} contract missing brakes, goal, or verifier")
                        return False
                    
                    if goal.get("authored_by") == policy.get("ref"):
                        print(f"FAIL-CLOSE: {run_dir} goal authored_by == policy executor")
                        return False
                        
                    # P0(4): Check gateway route if spend brake is declared
                    if brakes.get("max_budget_usd"):
                        if os.environ.get("ANTHROPIC_BASE_URL", "") != "http://127.0.0.1:8080":
                            print(f"FAIL-CLOSE: {run_dir} max_budget_usd declared but gateway route not configured")
                            return False

                    return True
    except Exception as e:
        print(f"FAIL-CLOSE: {run_dir} failed to parse contract: {e}")
        return False
        
    print(f"FAIL-CLOSE: {run_dir} no loop_contract_locked event found")
    return False

def trip_brake(run_dir: Path, brake_name: str, gt_value: str, enforcer: str, source: str):
    """Transition run to killed and write brake_tripped event."""
    run_jsonl = run_dir / 'run.jsonl'
    
    # Write event
    trip_ev = {
        "event": "brake_tripped",
        "brake": brake_name,
        "ground_truth_value": gt_value,
        "enforcer": enforcer,
        "source": source
    }
    with open(run_jsonl, 'a') as f:
        f.write(json.dumps(trip_ev) + '\n')
        f.write(json.dumps({"event": "workflow_complete", "terminal_state": "killed"}) + '\n')
        
    # Write poison sentinel to kill the agent process
    poison_file = run_dir / '.poison_sentinel'
    poison_file.write_text("KILLED BY BRAKES WATCHDOG")
    
    # Update state file to reflect killed status
    state_file = run_dir / 'run.state.json'
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            state['status'] = 'killed'
            state_file.write_text(json.dumps(state))
        except Exception:
            pass

    print(f"KILLED {run_dir.name} - Brake Tripped: {brake_name} ({gt_value})")

def trigger_human_checkpoint(run_dir: Path, iters: int):
    """Transition run to paused for human check-in."""
    run_jsonl = run_dir / 'run.jsonl'
    
    trip_ev = {
        "event": "human_checkpoint_required",
        "iteration": iters,
        "message": "Human check-in required. Review progress and explicitly issue human_continue event."
    }
    with open(run_jsonl, 'a') as f:
        f.write(json.dumps(trip_ev) + '\n')
        f.write(json.dumps({"event": "status_changed", "from": "active", "to": "paused"}) + '\n')
        
    # Write sentinel to stop autonomous iterations until cleared
    pause_file = run_dir / '.paused_sentinel'
    pause_file.write_text("PAUSED FOR HUMAN CHECKPOINT")
    
    # Update state file
    state_file = run_dir / 'run.state.json'
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            state['status'] = 'paused'
            state_file.write_text(json.dumps(state))
        except Exception:
            pass

    print(f"PAUSED {run_dir.name} - Human Checkpoint at iteration {iters}")

def watchdog_scan(vault_root: Path):
    """Scan active loop-runs and enforce hard brakes and human checkpoints."""
    loop_runs_dir = vault_root / 'vault' / 'loop-runs'
    if not loop_runs_dir.is_dir():
        return
        
    now = time.time()
    
    for run_dir in loop_runs_dir.glob('*'):
        if not run_dir.is_dir(): continue
        
        run_jsonl = run_dir / 'run.jsonl'
        if not run_jsonl.exists(): continue
        
        # Check if already killed
        poison_file = run_dir / '.poison_sentinel'
        if poison_file.exists(): continue
        
        # Parse contract to get brakes and track cooperative iterations
        brakes = {}
        status = "active"
        coop_iters = 0
        last_continue_iter = 0
        
        try:
            with open(run_jsonl, 'r') as f:
                for line in f:
                    ev = json.loads(line)
                    event_type = ev.get("event")
                    if event_type == "loop_contract_locked":
                        brakes = ev.get("brakes", {})
                    elif event_type == "workflow_complete":
                        status = ev.get("terminal_state", "complete")
                    elif event_type == "iteration_completed":
                        coop_iters = int(ev.get("iteration_n", coop_iters))
                    elif event_type == "human_continue":
                        last_continue_iter = coop_iters
                    elif event_type == "status_changed":
                        status = ev.get("to", status)
        except Exception:
            continue
            
        if status != "active" or not brakes:
            continue
            
        # 1. Wall-clock age (HARD BRAKE - ground truth)
        max_mins = brakes.get("max_wall_clock_min")
        if max_mins:
            # P0(2) fix: use the run-folder ctime, not the appended jsonl
            ctime = os.stat(run_dir).st_ctime
            age_mins = (now - ctime) / 60.0
            if age_mins >= max_mins:
                trip_brake(run_dir, "max_wall_clock_min", f"{age_mins:.1f}m", "watchdog", "ctime")
                continue
                
        # 2. Spend (HARD BRAKE - gateway ground-truth)
        max_spend = brakes.get("max_budget_usd")
        if max_spend:
            spend_file = run_dir / "gateway_spend.json"
            if spend_file.exists():
                try:
                    spend_data = json.loads(spend_file.read_text())
                    spent = spend_data.get("spent_usd", 0.0)
                    if spent >= max_spend:
                        trip_brake(run_dir, "max_budget_usd", f"${spent:.2f}", "watchdog", "gateway_spend.json")
                        continue
                except Exception as e:
                    trip_brake(run_dir, "max_budget_usd", f"UNREADABLE", "watchdog", f"gateway_spend.json_error:{e}")
                    continue
            else:
                trip_brake(run_dir, "max_budget_usd", f"MISSING", "watchdog", "gateway_spend.json_absent")
                continue
                    
        # 3. Terminal Iteration Stop (v1.71 S1; 00003838)
        max_iters = brakes.get("max_iterations")
        if max_iters and coop_iters >= max_iters:
            # Write workflow_complete with state: done (or limit-reached?)
            # Spec says "STOPS terminally and returns to the human"
            run_jsonl = run_dir / "run.jsonl"
            with open(run_jsonl, "a") as f:
                f.write(json.dumps({
                    "event": "brake_tripped",
                    "brake": "max_iterations",
                    "ground_truth_value": str(coop_iters),
                    "enforcer": "watchdog",
                    "source": "run.jsonl_cooperative"
                }) + "\n")
                f.write(json.dumps({"event": "workflow_complete", "terminal_state": "done", "reason": "max_iterations_reached"}) + "\n")
            
            # Write poison sentinel to kill the agent process
            poison_file = run_dir / ".poison_sentinel"
            poison_file.write_text("TERMINATED: MAX ITERATIONS REACHED")
            
            # Update state file
            state_file = run_dir / "run.state.json"
            if state_file.exists():
                try:
                    state = json.loads(state_file.read_text())
                    state["status"] = "done"
                    state_file.write_text(json.dumps(state))
                except Exception: pass
            print(f"DONE {run_dir.name} - Max Iterations Reached: {coop_iters}")
            continue

        # 4. Human Checkpoint (Mike-resolution 00003754)
        checkpoint_every = brakes.get("human_checkpoint_every")
        if checkpoint_every:
            checkpoint_every = int(checkpoint_every)
            # If we have reached a multiple of N iterations since the last check-in
            if coop_iters > last_continue_iter and (coop_iters - last_continue_iter) >= checkpoint_every:
                trigger_human_checkpoint(run_dir, coop_iters)
                continue

def main() -> int:
    vault_root = Path(__file__).resolve().parent.parent.parent
    
    if len(sys.argv) > 1 and sys.argv[1] == "--check-preconditions":
        if len(sys.argv) < 3:
            print("Usage: 1edbee15.py --check-preconditions <run_dir>")
            return 2
        run_dir = Path(sys.argv[2])
        if check_loop_run_start_preconditions(run_dir):
            print(f"Preconditions MET for {run_dir}")
            return 0
        return 1
        
    watchdog_scan(vault_root)
    return 0

if __name__ == "__main__":
    sys.exit(main())
