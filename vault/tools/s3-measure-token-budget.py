#!/usr/bin/env python3
"""
---
uid: s3-measure-token-budget
name: s3-measure-token-budget
type: tool
title: "S3 Measure Token Budget — hot-path file class census + budget table"
description: "Scripted census of boot-hot-path and write-time file classes per v1.69 dev-spec 0c61a52b §S3 MEASURE. Produces token-budget-table.yaml consumed by check_token_budget_per_class in d2b9c8e6.py."
status: active
state: active
owner: talos
domain: "v1.69 S3 — token-performance"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/s3-measure-token-budget.py [--output <path>] [--apply]"
script_path: vault/tools/s3-measure-token-budget.py
created: 2026-06-12
created_by: talos-t15
governed_by: 8dd772a0
member_of:
  - "b7649a1c"   # v1.69 root
refs:
  - "0c61a52b"   # v1.69 dev-spec §S3
  - "7dab32b1"   # token-performance brief (claimed)
schema_version: 2
extraction_scope: argo-reference
---

S3 hot-path token-budget census.

File classes measured:
  unified_agent_entry  — vault/agents/*.md (boot-hot for Shape-A agents)
  boot_contract_pair   — vault/playbooks/99341618.md + e2c7d185.md
  tier1_canonical      — vault/files/8f6ea459.md (Tier 1 substrate)
  tier2_canonical      — vault/files/cf8c3be9.md (Tier 2 substrate)
  operating_principles — .tropo-studio/operating-principles.md
  self_healing         — .tropo/SELF-HEALING.md
  mission_brief        — context/mission-brief.md
  write_time_capsule   — .tropo/capsules/*.md (consulted at every vault write)
  vault_playbook       — vault/playbooks/*.md (all playbooks)
  activation_playbook  — vault/playbooks/99341618.md only
  retire_playbook      — vault/playbooks/e2c7d185.md only

Budget targets (initial; A110 adjudicates SPLIT candidates):
  unified_agent_entry  : 75 KB  (max current 67 KB — Argus A109; bounded by §Status-Notes rule)
  boot_contract_pair   : 70 KB each  (activation 61 KB / retire 55 KB — headroom preserved)
  tier1/tier2          : 40 KB each  (tier1 8 KB / tier2 28 KB — well within)
  operating_principles : 35 KB  (current 33 KB — borderline; watch closely)
  self_healing         : 20 KB  (current 16 KB — ok)
  mission_brief        : 8 KB   (current 4 KB — ok)
  write_time_capsule   : 50 KB each  (WARN fires: events.capsule 77 KB / ship-artifact 65 KB — SPLIT candidates)
  vault_playbook       : 80 KB each  (non-boot-contract playbooks need more headroom)
  activation_playbook  : 70 KB  (61 KB — ok)
  retire_playbook      : 70 KB  (55 KB — ok)
"""

import argparse
import glob as _glob
import json
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = VAULT_ROOT / "agents/dev-pipeline/activations/b7649a1c/token-budget-table.yaml"

# ── File class definitions ────────────────────────────────────────────────────
# Each class: (display_name, glob_pattern_relative_to_vault_root, budget_bytes, notes)
# budget_bytes = the per-file limit; WARN fires when any single file exceeds it.

CLASSES = [
    (
        "unified_agent_entry",
        "vault/agents/*.md",
        76800,   # 75 KB — bounded by agent.capsule §Status-Notes structural cap + soul verbatim
        "Boot-hot Shape-A: every agent activation reads their unified entry. "
        "§Status-Notes capped at current+predecessor; §Soul is verbatim (can't compress). "
        "SPLIT if §Boot-Extension grows unbounded (history companion pattern).",
    ),
    (
        "activation_playbook",
        "vault/playbooks/99341618.md",
        71680,   # 70 KB — measured 61 KB with 15% headroom
        "Boot-critical path for every activation. Boot-contract pair: thin-pointer + canonical. "
        "LEAN if amendment-note history exceeds current+prior; history_companion already exists.",
    ),
    (
        "retire_playbook",
        "vault/playbooks/e2c7d185.md",
        71680,   # 70 KB — measured 55 KB
        "Boot-critical path for every retirement. Same two-file pattern as activation.",
    ),
    (
        "tier1_canonical",
        "vault/files/8f6ea459.md",
        40960,   # 40 KB — measured 8 KB; cap preserves headroom as the OS substrate grows
        "Tier 1 OS config substrate. Read at every agent boot. Keep lean by construction.",
    ),
    (
        "tier2_canonical",
        "vault/files/cf8c3be9.md",
        40960,   # 40 KB — measured 28 KB
        "Tier 2 Studio boot extension substrate. Read at every agent boot.",
    ),
    (
        "operating_principles",
        ".tropo-studio/operating-principles.md",
        35840,   # 35 KB — measured 33 KB; borderline; flag for Vela to watch
        "Required at every boot for every agent. WARN if it crosses 35 KB — "
        "each principle is a lean rule, not a narrative; accumulation is drift.",
    ),
    (
        "self_healing",
        ".tropo/SELF-HEALING.md",
        20480,   # 20 KB — measured 16 KB
        "OS-tier primitive. Read at every boot. Must stay minimal.",
    ),
    (
        "mission_brief",
        "context/mission-brief.md",
        8192,    # 8 KB — measured 4 KB
        "Required boot read. Compressed mission; should never grow large.",
    ),
    (
        "write_time_capsule",
        ".tropo/capsules/*.md",
        51200,   # 50 KB — events.capsule 77 KB + ship-artifact 65 KB WARN immediately
        "Consulted at every governed write. SPLIT candidates: events.capsule (77 KB), "
        "ship-artifact.capsule (65 KB), publish.pipeline.capsule (60 KB). "
        "Each capsule should fit in one read; history → companion (proven 3×).",
    ),
    (
        "vault_playbook",
        "vault/playbooks/*.md",
        81920,   # 80 KB — non-boot-contract playbooks invoked on demand; more headroom ok
        "Invocation path: query index → UID → path → execute. "
        "Only the active playbook is loaded; fleet size < boot-path cost. "
        "Flag if any single playbook exceeds 80 KB (suggests history bloat).",
    ),
]


# ── Measurement ───────────────────────────────────────────────────────────────

def measure_class(class_name: str, pattern: str) -> dict:
    """Measure all files matching the glob pattern."""
    files = sorted(_glob.glob(str(VAULT_ROOT / pattern)))
    if not files:
        return {
            "class": class_name,
            "file_count": 0,
            "total_bytes": 0,
            "max_bytes": 0,
            "avg_bytes": 0,
            "files": [],
        }
    sizes = [(Path(f).relative_to(VAULT_ROOT).as_posix(), Path(f).stat().st_size) for f in files]
    total = sum(s for _, s in sizes)
    max_s = max(s for _, s in sizes)
    return {
        "class": class_name,
        "file_count": len(files),
        "total_bytes": total,
        "max_bytes": max_s,
        "avg_bytes": total // len(files) if files else 0,
        "files": sorted(sizes, key=lambda x: -x[1]),  # largest first
    }


def format_kb(n: int) -> str:
    return f"{n / 1024:.1f} KB"


def run_census() -> list[dict]:
    results = []
    for class_name, pattern, budget, notes in CLASSES:
        m = measure_class(class_name, pattern)
        m["budget_bytes"] = budget
        m["budget_kb"] = budget / 1024
        m["notes"] = notes
        m["over_budget"] = [
            (path, size) for path, size in m["files"] if size > budget
        ]
        results.append(m)
    return results


def print_report(results: list[dict]) -> None:
    sep = "=" * 72
    print(f"\n{sep}")
    print("S3 Token Budget Census — Hot-Path File Classes")
    print(f"{sep}\n")

    for r in results:
        status = "⚠ OVER BUDGET" if r["over_budget"] else "✓ within budget"
        print(f"[{status}] {r['class']}")
        print(f"  pattern   : {[c[1] for c in CLASSES if c[0] == r['class']][0]}")
        print(f"  budget    : {format_kb(r['budget_bytes'])} ({r['budget_bytes']:,} bytes)")
        print(f"  files     : {r['file_count']}")
        if r["file_count"] > 0:
            print(f"  max size  : {format_kb(r['max_bytes'])} ({r['max_bytes']:,} bytes)")
            print(f"  avg size  : {format_kb(r['avg_bytes'])}")
            print(f"  total     : {format_kb(r['total_bytes'])}")
        if r["over_budget"]:
            print(f"  OVER BUDGET ({len(r['over_budget'])} file(s)):")
            for path, size in r["over_budget"]:
                excess = size - r["budget_bytes"]
                print(f"    {path}: {format_kb(size)} (excess: {format_kb(excess)})")
        if r["file_count"] > 0 and r["file_count"] <= 5:
            for path, size in r["files"]:
                print(f"    {path}: {format_kb(size)}")
        print()

    total_over = sum(len(r["over_budget"]) for r in results)
    print(f"{sep}")
    print(f"SUMMARY: {total_over} file(s) over budget across {len(results)} class(es)")
    print(f"{sep}\n")


def build_budget_table(results: list[dict]) -> dict:
    """Build the YAML budget table consumed by check_token_budget_per_class."""
    classes: dict = {}
    for r in results:
        pattern = [c[1] for c in CLASSES if c[0] == r["class"]][0]
        notes = r["notes"]
        classes[r["class"]] = {
            "budget_bytes": r["budget_bytes"],
            "glob": pattern,
            "exempt_uids": [],
            "notes": notes,
            "measured_at": "2026-06-12",
            "measured_by": "talos-t15",
            "current_max_bytes": r["max_bytes"],
            "current_file_count": r["file_count"],
        }
    return {
        "schema_version": 1,
        "generated_at": "2026-06-12",
        "generated_by": "talos-t15",
        "spec": "0c61a52b §S3 MEASURE",
        "adjudicated_by": None,  # A110 fills this in after review
        "classes": classes,
    }


def write_budget_table(table: dict, output_path: Path) -> None:
    try:
        import yaml
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            yaml.dump(table, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"Budget table written: {output_path.relative_to(VAULT_ROOT)}")
    except ImportError:
        # Fallback to JSON if yaml not available
        output_path.with_suffix(".json").write_text(
            json.dumps(table, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Budget table written (JSON fallback): {output_path.with_suffix('.json').relative_to(VAULT_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="S3 Token Budget Census")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help=f"Output path for budget table YAML (default: {DEFAULT_OUTPUT.relative_to(VAULT_ROOT)})")
    parser.add_argument("--apply", action="store_true",
                        help="Write budget table to output path (default: print report only)")
    args = parser.parse_args()

    results = run_census()
    print_report(results)

    table = build_budget_table(results)

    if args.apply:
        write_budget_table(table, Path(args.output))
        print("\nRe-run validator to activate check_token_budget_per_class:\n"
              "  python3 vault/tools/d2b9c8e6.py | grep 'Token Budget'")
    else:
        print("Re-run with --apply to write the budget table and activate the WARN check.")

    total_over = sum(len(r["over_budget"]) for r in results)
    return 1 if total_over > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
