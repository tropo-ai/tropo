#!/usr/bin/env python3
"""
---
uid: 2e5c81d3
name: loop-activate
type: tool
status: active
owner: talos
domain: "Activation gate for governed loops (v1.71 S1)."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/2e5c81d3.py"
script_path: vault/tools/2e5c81d3.py
input:
  type: object
  description: "Prompts for human ceilings and creates a new loop-run."
created: 2026-06-16
created_by: talos-t20
governed_by: d5e1b4a3
member_of:
  - c7e4f9a2
realizes_dev_spec: 9da979b2
schema_version: 2
belt: true
title: "loop-activate — the human launch-gate for governed loops"
---
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
import yaml

def resolve_loop(vault_root: Path, loop_uid: str):
    """Find the loop definition by UID."""
    loop_file = vault_root / 'vault' / 'files' / f'{loop_uid}.md'
    if not loop_file.exists():
        # Search all md files if not found
        for f in (vault_root / 'vault' / 'files').glob('*.md'):
            if f.name.startswith(loop_uid):
                loop_file = f
                break
    
    if not loop_file.exists():
        print(f"Error: Loop {loop_uid} not found.")
        sys.exit(1)
        
    content = loop_file.read_text()
    parts = content.split('---')
    if len(parts) < 3:
        print(f"Error: {loop_file} has no frontmatter.")
        sys.exit(1)
        
    fm = yaml.safe_load(parts[1])
    if fm.get('type') != 'loop':
        print(f"Error: {loop_uid} is type:{fm.get('type')}, not 'loop'.")
        sys.exit(1)
        
    return fm

def prompt_int(msg: str, default: int) -> int:
    val = input(f"{msg} [{default}]: ").strip()
    if not val: return default
    return int(val)

def prompt_float(msg: str, default: float) -> float:
    val = input(f"{msg} [{default:.2f}]: ").strip()
    if not val: return default
    return float(val)

def main():
    if len(sys.argv) < 2:
        print("Usage: loop-activate <loop-uid>")
        sys.exit(1)
        
    vault_root = Path(__file__).resolve().parent.parent.parent
    loop_uid = sys.argv[1]
    loop = resolve_loop(vault_root, loop_uid)
    
    print(f"\n--- LOOP ACTIVATION: {loop['name']} (v{loop['version']}) ---")
    print(f"Goal: {loop['goal']['authored_by']} signed.")
    print("Set your safety ceilings (brakes):")
    
    # 1. Activation Gate Prompt (Mike-A114 direction)
    max_iters = prompt_int("Stop after how many iterations?", 5)
    max_budget = prompt_float("Dollar ceiling for this run?", 0.50)
    max_mins = prompt_int("Maximum minutes?", 60)
    
    checkpoint_raw = input("Check in every N instead of stopping? (blank for none): ").strip()
    checkpoint_every = int(checkpoint_raw) if checkpoint_raw else None
    
    # Generate run metadata
    run_uid = str(uuid.uuid4())[:8]
    date_str = datetime.now().strftime('%Y-%m-%d')
    folder_name = f"{loop['name'].replace(' ', '-').lower()}-{run_uid}-{date_str}"
    run_dir = vault_root / 'vault' / 'loop-runs' / folder_name
    run_dir.mkdir(parents=True, exist_ok=True)
    
    now_iso = datetime.now().isoformat() + 'Z'
    
    # 2. Seed run.jsonl
    run_jsonl = run_dir / 'run.jsonl'
    with open(run_jsonl, 'w') as f:
        # Event 1: run_created
        f.write(json.dumps({
            "event": "run_created",
            "time": now_iso,
            "owner": "mike-maziarz", # Default for now
            "loop": loop['uid'],
            "loop_version": loop['version']
        }) + '\n')
        
        # Event 2: loop_contract_locked (The immutable contract at start)
        brakes = {
            "max_iterations": max_iters,
            "max_budget_usd": max_budget,
            "max_wall_clock_min": max_mins,
            "tool_timeout_sec": 300 # Baseline default
        }
        if checkpoint_every:
            brakes["human_checkpoint_every"] = checkpoint_every
            
        f.write(json.dumps({
            "event": "loop_contract_locked",
            "time": now_iso,
            "goal": loop['goal'],
            "verifier": loop['verifier'],
            "brakes": brakes,
            "policy": loop['policy'],
            "consequence": loop['consequence']
        }) + '\n')

    # 3. Create initial state
    run_state = run_dir / 'run.state.json'
    state_data = {
        "uid": run_uid,
        "type": "loop-run",
        "name": f"Run of {loop['name']}",
        "loop": loop['uid'],
        "status": "active",
        "started_at": now_iso,
        "iteration_count": 0,
        "budget_spent_usd_reported": 0.0
    }
    run_state.write_text(json.dumps(state_data, indent=2))
    
    # 4. Initialize gateway_spend.json for the hard kill
    (run_dir / "gateway_spend.json").write_text(json.dumps({"spent_usd": 0.0}))
    
    # Create definition.md as a pointer/snapshot
    (run_dir / "definition.md").write_text(f"""---
uid: {run_uid}
type: loop-run
name: "{state_data['name']}"
loop: {loop['uid']}
status: active
---

Snapshot of loop definition {loop['uid']} v{loop['version']} at run start.
""")

    print(f"\n✓ Loop-run ACTIVATED at: vault/loop-runs/{folder_name}/")
    print(f"Brakes: {max_iters} iters / ${max_budget:.2f} / {max_mins} mins")
    print(f"\nLaunch command:")
    print(f"  claude-code --run-dir vault/loop-runs/{folder_name}")

if __name__ == "__main__":
    main()
