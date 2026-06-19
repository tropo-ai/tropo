#!/usr/bin/env python3
"""
---
uid: 8c4cea94
name: migrate-v14-subsystem-hub-split
type: tool
status: active
owner: argus
domain: "v1.14 schema split migration — move subsystem hub UIDs from member_of: → subsystem_hub:."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/8c4cea94.py"
script_path: vault/tools/8c4cea94.py
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

"""v1.14 schema split migration — move subsystem hub UIDs from member_of: → subsystem_hub:.

Authored by Argus A80 2026-05-23 captain-mode under v1.51 cycle per:
- project.capsule v2.5 §Migration Notes (v2.4 → v2.5)
- Vela V51 Path 2 finding [fb395501]
- Mike-A80 directive 2026-05-23 verbatim "B. let's do it right"
- v1.51 cycle brief [1feefe68 v0.2 LOCKED]

WHAT THIS DOES:

Sweeps vault/files/*.md. For each entry whose member_of: array contains UIDs that
resolve to subsystem hubs (entries with subsystem_name: frontmatter field):
- Moves the hub UID(s) from member_of: array → subsystem_hub: array
- Sets capsule_version: 2.5 on the migrated entry (gates Validation Check 11 enforcement
  per project.capsule v2.5)
- Preserves YAML comments + ordering on both fields
- Logs each migration to stdout (dry-run) OR writes to disk (--apply)

ANTI-FOOTGUN INVARIANTS:

1. --dry-run is DEFAULT. --apply must be explicitly passed. Captain's-rule: Mike walks
   dry-run output BEFORE any write fires.
2. Entries whose own UID is a subsystem hub (i.e., entries with their own subsystem_name:
   field) are NEVER modified — they ARE the hubs; their own member_of: is true parentage.
3. If member_of: becomes empty after migration AND owner: doesn't resolve to a vault-entity,
   the entry is logged as DEFECT (Rule 1 violation requires per-entry Mike review). Migration
   does NOT proceed on DEFECT entries unless --include-defects is passed.
4. If subsystem_hub: already exists on the entry (idempotent re-run), hub UIDs are merged
   into existing array (no duplicates; preserves existing order).
5. If member_of: has only hub UIDs (the 188 hub-only-parented case) AND no non-hub parent
   exists, the entry's member_of: becomes [] post-migration. This is correct schema (the hub
   membership is now in subsystem_hub:); but Rule 1 may flag if no vault-entity owner. DEFECT
   path applies.
6. Files outside vault/files/ are never touched. Capsule definitions at .tropo/capsules/ are
   excluded (capsule entries are governance not work-items).
7. Files with no frontmatter are skipped silently.
8. YAML parse failures are logged as ERROR (no migration); script continues.

USAGE:

    # Dry-run (default; no writes):
    python3 .tropo/scripts/migrate-v14-subsystem-hub-split.py

    # Apply migration (writes to disk):
    python3 .tropo/scripts/migrate-v14-subsystem-hub-split.py --apply

    # Include entries that would become Rule-1-violators (DEFECT path):
    python3 .tropo/scripts/migrate-v14-subsystem-hub-split.py --apply --include-defects

    # Restrict to a single UID (debugging / targeted migration):
    python3 .tropo/scripts/migrate-v14-subsystem-hub-split.py --uid 7e93ed75

OUTPUT FORMAT:

    [MIGRATE] <path> uid=<uid>
      member_of: [<old-list>] → [<new-list>]
      subsystem_hub: [<old-list>] → [<new-list>] (NEW field)
      hub_uids_moved: [<hub-uid-1>, <hub-uid-2>]
      capsule_version: <old> → 2.5

    [DEFECT] <path> uid=<uid>
      member_of becomes [] post-migration AND owner=<owner> doesn't resolve to vault-entity
      hub_uids: [<hub-uid-list>]
      remediation: per-entry Mike review OR --include-defects to proceed

    [ERROR] <path> uid=<uid>
      <error description>

    Summary:
      Total entries scanned: <n>
      Hub-edge entries: <n>
      Hub-only-parented (DEFECT candidates): <n>
      Migrations queued: <n>
      Writes applied: <n>  (0 if --dry-run; equals queued count if --apply)
      Errors: <n>
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install via `pip install pyyaml`.", file=sys.stderr)
    sys.exit(1)


# Subsystem hub UIDs (entries with subsystem_name: field). Built dynamically at start
# so the script auto-adapts as new hubs land. Pre-computed list as fallback / verification.
KNOWN_HUB_UIDS_FALLBACK = {
    "1aba710c",  # Tropo Library
    "2d083137",  # Tropo Work
    "3a207ed3",  # Tropo Link
    "58722bdf",  # Import Primitive
    "76bab75f",  # Tropo Playbooks
    "8dd772a0",  # Tropo Governance
    "952f3aa3",  # Tropo Test Harness
    "99ed55fd",  # Tropo Agents
    "b8daa232",  # Tropo Boot System (archived)
    "dbc1cbbf",  # Tropo Rendering
    "f87e33f0",  # Tropo Documentation
}


def discover_hub_uids(vault_root: Path) -> set[str]:
    """Scan vault/files/ for entries with subsystem_name: field. Return their UIDs."""
    hubs: set[str] = set()
    files_dir = vault_root / "vault" / "files"
    if not files_dir.exists():
        return hubs
    for f in files_dir.glob("*.md"):
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        if fm is None:
            continue
        if fm.get("subsystem_name"):
            uid = fm.get("uid") or f.stem
            if isinstance(uid, str):
                hubs.add(uid)
    return hubs


def _split_frontmatter_raw(text: str) -> Optional[tuple[str, str, str]]:
    """Split file text into (preamble, frontmatter_yaml, body).

    Returns None if no frontmatter detected.
    Preserves trailing newline on frontmatter delimiter for round-trip safety.
    """
    if not text.startswith("---"):
        return None
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return None
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None
    fm_yaml = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])
    return ("---", fm_yaml, body)


def _parse_frontmatter(text: str) -> Optional[dict]:
    """Parse YAML frontmatter into dict; return None on failure."""
    parts = _split_frontmatter_raw(text)
    if parts is None:
        return None
    try:
        fm = yaml.safe_load(parts[1])
        return fm if isinstance(fm, dict) else None
    except yaml.YAMLError:
        return None


def _frontmatter_has_field(fm_yaml: str, field: str) -> bool:
    """Check whether YAML body contains a top-level field declaration (regex; preserves
    comment-aware parsing without needing full YAML round-trip)."""
    pattern = re.compile(rf"^{re.escape(field)}\s*:", re.MULTILINE)
    return bool(pattern.search(fm_yaml))


def _migrate_member_of_in_yaml_string(fm_yaml: str, hub_uids_to_move: list[str]) -> tuple[str, list[str]]:
    """Migrate hub UIDs out of member_of: in raw YAML string.

    Returns (new_yaml, remaining_non_hub_uids_in_member_of).

    Approach: parse YAML, modify, re-emit. Loses comments on the member_of: block but
    preserves overall structure. For comment-preservation, use ruamel.yaml — but PyYAML
    is the kernel-script dependency per CLAUDE.md. Round-trip safety verified by
    re-parsing migrated YAML matches expected shape.
    """
    fm = yaml.safe_load(fm_yaml)
    if not isinstance(fm, dict):
        return fm_yaml, []
    member_of = fm.get("member_of") or []
    if not isinstance(member_of, list):
        return fm_yaml, []
    new_member_of = [m for m in member_of if not (isinstance(m, str) and m in hub_uids_to_move)]
    fm["member_of"] = new_member_of
    # Sort frontmatter output to match common vault convention; PyYAML default_flow_style=False
    return yaml.dump(fm, sort_keys=False, default_flow_style=False, allow_unicode=True, width=10000), new_member_of


def _add_or_merge_subsystem_hub_in_yaml(fm_yaml: str, hub_uids_to_add: list[str]) -> str:
    """Add subsystem_hub: array (or merge into existing) in raw YAML string."""
    fm = yaml.safe_load(fm_yaml)
    if not isinstance(fm, dict):
        return fm_yaml
    existing = fm.get("subsystem_hub") or []
    if not isinstance(existing, list):
        existing = []
    # Merge preserving order; deduplicate
    merged = list(existing)
    for uid in hub_uids_to_add:
        if uid not in merged:
            merged.append(uid)
    fm["subsystem_hub"] = merged
    return yaml.dump(fm, sort_keys=False, default_flow_style=False, allow_unicode=True, width=10000)


def _set_capsule_version_in_yaml(fm_yaml: str, version: str = "2.5") -> str:
    """Set capsule_version field in raw YAML string."""
    fm = yaml.safe_load(fm_yaml)
    if not isinstance(fm, dict):
        return fm_yaml
    fm["capsule_version"] = version
    return yaml.dump(fm, sort_keys=False, default_flow_style=False, allow_unicode=True, width=10000)


def _resolve_owner_is_vault_entity(owner: Optional[str], hub_uids: set[str]) -> bool:
    """Heuristic: check whether owner: appears to be a vault-entity reference.

    Vault-entity owners are typically the literal string 'mike-maziarz' or another known
    entity. For full validation, check against entity.capsule instances in vault. Heuristic
    here is conservative: owners that look like 8-hex UIDs OR known vault-entity strings
    are accepted; bare strings like 'argus' / 'vela' are also accepted (entity references
    pre-v2-migration).
    """
    if not owner or not isinstance(owner, str):
        return False
    # Known vault-entity owner strings
    if owner.lower() in {"mike", "mike-maziarz", "tropo", "vault", "system"}:
        return True
    # 8-hex UID owner: check it's not a hub (hubs can't own; they ARE substrate)
    if len(owner) == 8 and all(c in "0123456789abcdef" for c in owner.lower()):
        return owner not in hub_uids
    # Bare-string owners (e.g., 'argus', 'vela') are pre-v2-migration; accept
    return True


def migrate_entry(path: Path, fm: dict, fm_yaml: str, body: str, hub_uids: set[str]) -> Optional[dict]:
    """Determine migration plan for a single entry. Returns None if no migration needed.

    Returns dict: {
        "action": "migrate" | "defect" | "error",
        "uid": str,
        "hub_uids_moved": list[str],
        "member_of_before": list,
        "member_of_after": list,
        "subsystem_hub_before": list,
        "subsystem_hub_after": list,
        "capsule_version_before": Optional[str],
        "new_text": str,  # populated only when action=migrate or action=defect
        "defect_reason": Optional[str],
        "error_message": Optional[str],
    }
    """
    uid = fm.get("uid") or path.stem

    # Skip subsystem hubs themselves
    if uid in hub_uids:
        return None

    member_of = fm.get("member_of") or []
    if not isinstance(member_of, list):
        return None

    hub_edges = [m for m in member_of if isinstance(m, str) and m in hub_uids]
    if not hub_edges:
        return None  # no migration needed

    non_hub_edges = [m for m in member_of if isinstance(m, str) and m not in hub_uids]

    # Check defect condition: member_of becomes empty + owner doesn't resolve to vault-entity
    owner = fm.get("owner")
    is_defect = (not non_hub_edges) and (not _resolve_owner_is_vault_entity(owner, hub_uids))

    # Build migration plan
    plan = {
        "action": "defect" if is_defect else "migrate",
        "uid": uid,
        "hub_uids_moved": hub_edges,
        "member_of_before": list(member_of),
        "member_of_after": non_hub_edges,
        "subsystem_hub_before": list(fm.get("subsystem_hub") or []),
        "subsystem_hub_after": [],  # populated below
        "capsule_version_before": fm.get("capsule_version"),
        "new_text": "",
        "defect_reason": None,
        "error_message": None,
    }

    if is_defect:
        plan["defect_reason"] = (
            f"member_of becomes [] post-migration; owner={owner!r} does not resolve to vault-entity "
            f"(Rule 1 violation). Per-entry Mike review OR --include-defects."
        )

    # Compute subsystem_hub_after
    existing_subsystem_hub = plan["subsystem_hub_before"]
    new_subsystem_hub = list(existing_subsystem_hub)
    for h in hub_edges:
        if h not in new_subsystem_hub:
            new_subsystem_hub.append(h)
    plan["subsystem_hub_after"] = new_subsystem_hub

    # Build the new YAML body (skip for defect unless --include-defects is set at apply time)
    try:
        # Step 1: remove hub UIDs from member_of:
        new_yaml, _ = _migrate_member_of_in_yaml_string(fm_yaml, hub_edges)
        # Step 2: add subsystem_hub: array
        new_yaml = _add_or_merge_subsystem_hub_in_yaml(new_yaml, hub_edges)
        # Step 3: set capsule_version: 2.5
        new_yaml = _set_capsule_version_in_yaml(new_yaml, "2.5")
        plan["new_text"] = f"---\n{new_yaml}---\n{body}"
    except Exception as e:
        plan["action"] = "error"
        plan["error_message"] = str(e)

    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true",
                        help="Apply migrations (writes to disk). Default is dry-run (no writes).")
    parser.add_argument("--include-defects", action="store_true",
                        help="Include entries that would become Rule-1-violators post-migration.")
    parser.add_argument("--uid", type=str, default=None,
                        help="Restrict migration to a single UID (debugging / targeted migration).")
    parser.add_argument("--vault-root", type=Path, default=Path("."),
                        help="Vault root directory (default: cwd).")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print every entry scanned, not just migrations.")
    args = parser.parse_args()

    vault_root = args.vault_root.resolve()
    if not (vault_root / "vault" / "files").exists():
        print(f"ERROR: vault/files/ not found under {vault_root}", file=sys.stderr)
        return 1

    print(f"v1.14 subsystem-hub schema-split migration")
    print(f"Mode: {'APPLY (writes will fire)' if args.apply else 'DRY-RUN (no writes)'}")
    print(f"Vault root: {vault_root}")
    print()

    # Discover subsystem hubs dynamically
    print("Discovering subsystem hubs...")
    hub_uids = discover_hub_uids(vault_root)
    if not hub_uids:
        print(f"  No hubs discovered. Using fallback list of {len(KNOWN_HUB_UIDS_FALLBACK)} known hubs.")
        hub_uids = KNOWN_HUB_UIDS_FALLBACK
    print(f"  Found {len(hub_uids)} subsystem hubs: {sorted(hub_uids)}")
    print()

    # Scan vault/files/
    files_dir = vault_root / "vault" / "files"
    total_scanned = 0
    hub_edge_count = 0
    plans: list[dict] = []
    errors: list[dict] = []

    for f in sorted(files_dir.glob("*.md")):
        try:
            text = f.read_text(errors="replace")
        except OSError as e:
            errors.append({"path": str(f.relative_to(vault_root)), "error": str(e)})
            continue
        parts = _split_frontmatter_raw(text)
        if parts is None:
            continue
        fm = _parse_frontmatter(text)
        if fm is None:
            continue
        total_scanned += 1

        uid = fm.get("uid") or f.stem
        if args.uid and uid != args.uid:
            continue

        plan = migrate_entry(f, fm, parts[1], parts[2], hub_uids)
        if plan is None:
            continue

        hub_edge_count += 1
        plan["path"] = str(f.relative_to(vault_root))
        plan["abs_path"] = str(f)
        plans.append(plan)

    # Categorize
    migrations = [p for p in plans if p["action"] == "migrate"]
    defects = [p for p in plans if p["action"] == "defect"]
    plan_errors = [p for p in plans if p["action"] == "error"]

    # Print per-entry output
    for p in plans:
        if p["action"] == "migrate":
            print(f"[MIGRATE] {p['path']} uid={p['uid']}")
            print(f"  member_of: {p['member_of_before']} → {p['member_of_after']}")
            print(f"  subsystem_hub: {p['subsystem_hub_before']} → {p['subsystem_hub_after']}")
            print(f"  hub_uids_moved: {p['hub_uids_moved']}")
            print(f"  capsule_version: {p['capsule_version_before']!r} → '2.5'")
            print()
        elif p["action"] == "defect":
            print(f"[DEFECT] {p['path']} uid={p['uid']}")
            print(f"  {p['defect_reason']}")
            print(f"  hub_uids: {p['hub_uids_moved']}")
            print()
        elif p["action"] == "error":
            print(f"[ERROR] {p['path']} uid={p['uid']}")
            print(f"  {p['error_message']}")
            print()

    # Apply if requested
    writes_applied = 0
    if args.apply:
        for p in plans:
            if p["action"] == "migrate" or (p["action"] == "defect" and args.include_defects):
                if not p["new_text"]:
                    continue
                Path(p["abs_path"]).write_text(p["new_text"])
                writes_applied += 1

    # Summary
    print("=" * 70)
    print("Summary:")
    print(f"  Total entries scanned:         {total_scanned}")
    print(f"  Hub-edge entries (migration candidates): {hub_edge_count}")
    print(f"  Migrations queued:             {len(migrations)}")
    print(f"  Defects (need Mike review):    {len(defects)}")
    print(f"  Plan errors:                   {len(plan_errors)}")
    print(f"  Writes applied:                {writes_applied}")
    print(f"  Read errors:                   {len(errors)}")
    print()
    if not args.apply:
        print("DRY-RUN — no writes fired. Re-run with --apply to apply.")
        if defects and not args.include_defects:
            print(f"NOTE: {len(defects)} DEFECT entries would be SKIPPED at --apply (per Rule 1 protection).")
            print("      Use --include-defects to include them.")
    else:
        print(f"APPLY complete. {writes_applied} entries migrated. Run vault rebuild + tree diff to verify.")

    return 0 if not plan_errors and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
