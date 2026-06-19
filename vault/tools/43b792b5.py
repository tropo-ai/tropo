#!/usr/bin/env python3
"""
---
uid: 43b792b5
name: cascade-stress-compare
type: tool
status: active
owner: talos
domain: "R3 cascade-runtime-stress: structural-shape comparison of two cascade runs."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/43b792b5.py"
script_path: vault/tools/43b792b5.py
spawnable_by:
  - all-executives
input:
  type: object
  description: "See tool usage for argument details"
created: 2026-05-27
created_by: talos-t10
governed_by: d5e1b4a3
member_of:
  - c7e4f9a2
schema_version: 2
---
"""
from __future__ import annotations

"""R3 cascade-runtime-stress: structural-shape comparison of two cascade runs.

Per v1.35.0 spec §2.3 AS-IF-EXECUTED match-predicate. Walks the member_of
graph from each activation-root-project UID, strips instance-variable fields
(uids, timestamps, generations, run-specific UID-references), and compares
the normalized structural shape.

PASS = same capsule type counts + same titles per type + same role distribution
+ same total. FAIL = any divergence; details printed.

Closes the fictional-cascade vulnerability R1B identified — by re-firing the
cascade against a fresh activation and comparing the result to the prior run,
we prove the cascade produces deterministic shape from the pipeline template.

Usage:
  python3 cascade-stress-compare.py --prior-root <uid> --new-root <uid>

Exit codes:
  0  PASS — structural shape matches
  1  FAIL — divergences detected (printed to stdout)
  2  Usage / IO error
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

VAULT_FILES = Path(__file__).resolve().parents[2] / "vault" / "files"

# Fields stripped per spec §2.3 — instance-variable, not structural-shape.
STRIPPED_FIELDS = {
    "uid", "activated_at", "created", "modified", "created_by", "modified_by",
    "activated_by", "generation", "author", "agent_root",
    "run_folder", "activation_root_project", "activation_entry",
    "run_uid", "activation_uid", "activated_by_pipeline",
    "modification_note", "v0_3_brainstorm_anchor", "v0_3_r2_absorption_anchor",
}


def load_frontmatter(path: Path) -> dict | None:
    try:
        text = path.read_text()
    except OSError:
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    try:
        return yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return None


CASCADE_AUTHOR = "pipeline-activate.py"


def walk_members(root_uid: str, cascade_only: bool = True) -> set[str]:
    """Return all UIDs transitively member_of root_uid (including root).

    When cascade_only=True (default), filters to entries whose created_by
    or author is the cascade runtime — matches spec §2.3's intent of
    comparing CASCADE OUTPUT, not all post-cascade additions to the tree
    (e.g., manually-authored demonstration tasks).

    RC (v1.35.0 R5 sa.skeptic-089 RC-1): the cascade_only filter is
    attribution-based; if a Path-1 self-heal rewrites author/created_by on a
    cascade-authored entry to a human entity, that entry silently drops from
    the comparison surface. Acceptable trade-off — Path-1 fixes are rare on
    cascade output, and the comparison's structural-shape predicate doesn't
    track owner/author divergence anyway. For exhaustive comparison including
    manually-fixed entries, pass --include-non-cascade explicitly.
    """
    visited: set[str] = set()
    frontier = {root_uid}
    while frontier:
        next_frontier: set[str] = set()
        for path in VAULT_FILES.glob("*.md"):
            uid = path.stem
            if uid in visited or uid in next_frontier:
                continue
            fm = load_frontmatter(path)
            if not fm:
                continue
            mo = fm.get("member_of", [])
            if not isinstance(mo, list):
                continue
            mo_strs = {str(m) for m in mo}
            if mo_strs & frontier:
                if cascade_only:
                    cb = str(fm.get("created_by", ""))
                    au = str(fm.get("author", ""))
                    if cb != CASCADE_AUTHOR and au != CASCADE_AUTHOR:
                        continue
                next_frontier.add(uid)
        visited |= frontier
        frontier = next_frontier - visited
    return visited


def normalize_title(t: str) -> str:
    """Strip date-class tokens from titles so 2026-05-16 → DATE."""
    import re
    return re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "DATE", t or "")


def shape_signature(uids: set[str]) -> dict:
    """Compute normalized shape signature for comparison."""
    type_counts: Counter = Counter()
    titles_by_type: dict[str, list[str]] = {}
    role_counts: Counter = Counter()
    status_by_type: dict[str, Counter] = {}
    state_by_type: dict[str, Counter] = {}
    for uid in uids:
        fm = load_frontmatter(VAULT_FILES / f"{uid}.md")
        if not fm:
            continue
        t = str(fm.get("type", "?"))
        type_counts[t] += 1
        title = normalize_title(str(fm.get("title", fm.get("name", "")) or ""))
        titles_by_type.setdefault(t, []).append(title)
        role = fm.get("role")
        if role:
            role_counts[str(role)] += 1
        st = fm.get("status")
        if st:
            status_by_type.setdefault(t, Counter())[str(st)] += 1
        sst = fm.get("state")
        if sst:
            state_by_type.setdefault(t, Counter())[str(sst)] += 1
    return {
        "total": len(uids),
        "type_counts": dict(type_counts),
        "titles_by_type": {t: sorted(ts) for t, ts in titles_by_type.items()},
        "role_counts": dict(role_counts),
        "status_by_type": {t: dict(c) for t, c in status_by_type.items()},
        "state_by_type": {t: dict(c) for t, c in state_by_type.items()},
    }


def compare(prior: dict, new: dict) -> list[str]:
    """Return list of divergence descriptions; empty list = PASS."""
    div = []
    if prior["total"] != new["total"]:
        div.append(f"total: prior={prior['total']} new={new['total']}")
    if prior["type_counts"] != new["type_counts"]:
        div.append(
            f"type_counts: prior={prior['type_counts']} new={new['type_counts']}"
        )
    if prior["role_counts"] != new["role_counts"]:
        div.append(
            f"role_counts: prior={prior['role_counts']} new={new['role_counts']}"
        )
    all_types = set(prior["titles_by_type"]) | set(new["titles_by_type"])
    for t in sorted(all_types):
        p_titles = prior["titles_by_type"].get(t, [])
        n_titles = new["titles_by_type"].get(t, [])
        if p_titles != n_titles:
            only_prior = sorted(set(p_titles) - set(n_titles))
            only_new = sorted(set(n_titles) - set(p_titles))
            div.append(
                f"titles[{t}]: only_prior={only_prior} only_new={only_new}"
            )
    for t in sorted(set(prior["status_by_type"]) | set(new["status_by_type"])):
        if prior["status_by_type"].get(t) != new["status_by_type"].get(t):
            div.append(
                f"status[{t}]: prior={prior['status_by_type'].get(t)} "
                f"new={new['status_by_type'].get(t)}"
            )
    for t in sorted(set(prior["state_by_type"]) | set(new["state_by_type"])):
        if prior["state_by_type"].get(t) != new["state_by_type"].get(t):
            div.append(
                f"state[{t}]: prior={prior['state_by_type'].get(t)} "
                f"new={new['state_by_type'].get(t)}"
            )
    return div


def main() -> int:
    p = argparse.ArgumentParser(
        description="R3 cascade-runtime-stress comparator (v1.35.0 spec §2.3)."
    )
    p.add_argument("--prior-root", required=True,
                   help="UID of prior cascade activation-root-project")
    p.add_argument("--new-root", required=True,
                   help="UID of fresh cascade activation-root-project")
    p.add_argument("--verbose", action="store_true",
                   help="Print full shape signatures even on PASS")
    p.add_argument("--include-non-cascade", action="store_true",
                   help="Include manually-authored entries in member_of tree "
                        "(default: filter to cascade-authored only per spec §2.3 intent)")
    args = p.parse_args()
    cascade_only = not args.include_non_cascade

    label = "cascade-authored" if cascade_only else "all"
    print(f"Walking prior {label} tree from {args.prior_root}...")
    prior_uids = walk_members(args.prior_root, cascade_only=cascade_only)
    print(f"  Found {len(prior_uids)} entries")

    print(f"Walking new {label} tree from {args.new_root}...")
    new_uids = walk_members(args.new_root, cascade_only=cascade_only)
    print(f"  Found {len(new_uids)} entries")

    prior_shape = shape_signature(prior_uids)
    new_shape = shape_signature(new_uids)

    if args.verbose:
        import json
        print("\n=== Prior shape ===")
        print(json.dumps(prior_shape, indent=2, sort_keys=True))
        print("\n=== New shape ===")
        print(json.dumps(new_shape, indent=2, sort_keys=True))

    divergences = compare(prior_shape, new_shape)
    print("\n=== Verdict ===")
    if not divergences:
        print(f"PASS — structural shape matches across {prior_shape['total']} entries.")
        return 0
    print(f"FAIL — {len(divergences)} divergence(s):")
    for d in divergences:
        print(f"  - {d}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
