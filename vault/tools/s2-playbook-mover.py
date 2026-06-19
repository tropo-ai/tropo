#!/usr/bin/env python3
"""
---
uid: s2-playbook-mover
name: s2-playbook-mover
type: tool
title: "S2 Playbook Mover — v1.69 copy-to-vault-first migration"
description: "Migrates playbooks from .tropo/playbooks/ to vault/playbooks/<uid>.md (single-file truth). Boot-contract pair (agent-activation + agent-retire) migrated LAST with gauntlet. Per dev-spec 0c61a52b §S2 + playbook.capsule v2.6."
status: active
state: active
owner: talos
domain: "v1.69 migration — S2 playbook unification"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/s2-playbook-mover.py --uid <uid> [--dry-run] [--apply]"
script_path: vault/tools/s2-playbook-mover.py
created: 2026-06-11
created_by: talos-t15
governed_by: 8dd772a0
member_of:
  - "b7649a1c"   # v1.69 root
refs:
  - "0c61a52b"   # v1.69 dev-spec §S2
  - "76bab75f"   # tropo-playbooks hub
schema_version: 2
extraction_scope: argo-reference
---
"""

import argparse
import subprocess
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
TODAY = "2026-06-11"

# S2 disposition list — each row maps uid → source path + optional frontmatter additions.
# Boot-contract pair is EXCLUDED here (handled separately with gauntlet + cold-boot test).
DISPOSITION = {
    # uid → (source_path_relative_to_vault_root, extra_frontmatter_fields)
    "71f186cf": (".tropo/playbooks/apply-update.playbook.md",              {}),
    "cd2b6d03": (".tropo/playbooks/cold-boot-action-test.playbook.md",     {}),
    "cb007e57": (".tropo/playbooks/cold-boot-test.playbook.md",            {}),
    "a5fb24a6": (".tropo/playbooks/dispatch-cold-boot.playbook.md",        {}),
    "7579f894": (".tropo/playbooks/dispatch-walker.playbook.md",           {}),
    "40ff3db1": (".tropo/playbooks/first-playbook.playbook.md",            {}),   # MINT row
    "7f2efd7c": (".tropo/playbooks/first-vault-setup.playbook.md",        {}),   # MINT row
    "91d8f2c5": (".tropo/playbooks/grooming.playbook.md",                  {}),
    "b84309f1": (".tropo/playbooks/new-hire-onboarding.playbook.md",       {}),
    "4a2f6dbd": (".tropo/playbooks/reconcile-imports.playbook.md",         {}),
    "6f3d2a18": (".tropo/playbooks/release-cold-boot-walk.playbook.md",    {}),
    "af8fc98a": (".tropo/playbooks/run-release-test-plan.playbook.md",     {"refs": ["harness-regime-ref-needs-sweep"]}),
    "45d21cd8": (".tropo/playbooks/setup-new-pipeline.playbook.md",        {}),
    "6b1fb41d": (".tropo/playbooks/team-onboarding-day2.playbook.md",      {}),
    "57a87001": (".tropo/playbooks/concierge-paths/start-a-project.playbook.md",    {"concierge_path": True}),
    "57a87002": (".tropo/playbooks/concierge-paths/create-an-agent.playbook.md",    {"concierge_path": True}),
    "57a87003": (".tropo/playbooks/concierge-paths/set-up-my-team.playbook.md",     {"concierge_path": True}),
    "57a87004": (".tropo/playbooks/concierge-paths/evaluate-tropo.playbook.md",     {"concierge_path": True}),
    "7c5a2b8f": (".tropo/playbooks/pipelines/tropo-work-pipeline.pipeline.md",      {}),
    "768c610e": ("playbooks/fleet-ops.playbook.md",                        {}),   # studio-root
    # f4a81b29: live references found → migrate + already marked status:superseded/superseded_by:99341618
    "f4a81b29": (".tropo/playbooks/agent-boot.playbook.md",               {}),
}

# Boot-contract pair — EXCLUDED, handled separately.
BOOT_CONTRACT = {"99341618", "e2c7d185"}

# Archive-in-place dispositions (migrations/ folder)
ARCHIVES = {
    "3ca544f2": "migrations/migrate-file-status.playbook.md",
    "a033e3b5": "migrations/migrate-index-format.playbook.md",
    "a7c1d4e3": "migrations/v030-founding-citizens.playbook.md",
    "b4e2c8a1": "migrations/v030-generate-capsule.playbook.md",
    "d5f3a9b2": "migrations/v030-replace-agents.playbook.md",
}


def _extract_frontmatter_raw(content: str) -> str:
    parts = content.split('---', 2)
    return parts[1] if len(parts) >= 3 else ''


def _extract_body(content: str) -> str:
    parts = content.split('---', 2)
    return parts[2] if len(parts) >= 3 else content


def _parse_frontmatter(content: str) -> dict:
    try:
        import yaml
        return yaml.safe_load(_extract_frontmatter_raw(content)) or {}
    except Exception:
        return {}


def _ensure_uid_in_frontmatter(content: str, uid: str) -> str:
    """Ensure frontmatter has uid: <uid>. Adds it if missing."""
    import re
    fm_raw = _extract_frontmatter_raw(content)
    body = _extract_body(content)
    if re.search(r'^uid\s*:', fm_raw, re.MULTILINE):
        # Replace existing uid
        fm_raw = re.sub(r'^uid\s*:.*$', f'uid: {uid}', fm_raw, flags=re.MULTILINE)
    else:
        # Add uid at the top of frontmatter
        fm_raw = f'\nuid: {uid}\n' + fm_raw.lstrip('\n')
    return f'---{fm_raw}---{body}'


def _add_frontmatter_field(content: str, key: str, value) -> str:
    """Add a frontmatter field at the end of the frontmatter block."""
    import re, yaml
    fm_raw = _extract_frontmatter_raw(content)
    body = _extract_body(content)
    if re.search(r'^' + re.escape(key) + r'\s*:', fm_raw, re.MULTILINE):
        return content  # Already present
    if isinstance(value, bool):
        line = f'{key}: {"true" if value else "false"}\n'
    elif isinstance(value, str):
        line = f'{key}: {value}\n'
    else:
        line = f'{key}: {yaml.dump(value, default_flow_style=True).strip()}\n'
    fm_raw = fm_raw.rstrip('\n') + '\n' + line
    return f'---{fm_raw}---{body}'


def _build_thin_pointer(uid: str, title: str, source_rel: str) -> str:
    """Build the kernel thin-pointer content for a non-boot-contract playbook."""
    vault_path = f'vault/playbooks/{uid}.md'
    # Relative path from .tropo/playbooks/ to vault/playbooks/ is ../../vault/playbooks/
    return (
        f"---\ncanonical_substrate_uid: \"{uid}\"\n"
        f"migrated_from: \"{source_rel}\"\n"
        f"migrated_at: \"{TODAY}\"\n"
        f"migrated_by: talos-t15\n---\n\n"
        f"# {title} — Thin Pointer\n\n"
        f"*Canonical substrate: [`{vault_path}`](../../{vault_path}). "
        f"v1.69 S2 playbook unification (dev-spec 0c61a52b). "
        f"This file is a thin pointer; all content is at the canonical path.*\n"
    )


def move_one(uid: str, dry_run: bool = True) -> bool:
    """Execute one playbook move. Returns True on success."""
    if uid not in DISPOSITION:
        print(f"ERROR: {uid} not in disposition list")
        return False

    source_rel, extra_fields = DISPOSITION[uid]
    source_path = VAULT_ROOT / source_rel
    canonical_path = VAULT_ROOT / 'vault' / 'playbooks' / f'{uid}.md'

    if not source_path.exists():
        print(f"ERROR: source not found: {source_path}")
        return False

    content = source_path.read_text('utf-8')
    fm = _parse_frontmatter(content)
    title = fm.get('title', fm.get('name', source_path.stem))

    print(f"\n{'[DRY-RUN] ' if dry_run else '[APPLY] '}Move {uid}: {source_rel}")
    print(f"  title:  {title}")
    print(f"  target: vault/playbooks/{uid}.md")

    # Step 1 — ensure uid in frontmatter
    content = _ensure_uid_in_frontmatter(content, uid)

    # Step 2 — add extra frontmatter fields (concierge_path: true, etc.)
    for key, val in extra_fields.items():
        if key == "refs":
            continue  # skip memo-only notes
        content = _add_frontmatter_field(content, key, val)

    # Step 3 — build thin-pointer for kernel path
    thin_pointer = _build_thin_pointer(uid, title, source_rel)

    if dry_run:
        print(f"  [DIFF] vault/playbooks/{uid}.md — new file ({len(content)} bytes)")
        print(f"  [DIFF] {source_rel} — replaced with thin-pointer ({len(thin_pointer)} bytes)")
        return True

    # APPLY: copy-to-vault FIRST, then thin-pointer
    # Step A — create vault/playbooks/ if needed
    canonical_path.parent.mkdir(parents=True, exist_ok=True)

    # Step B — write canonical to vault/playbooks/<uid>.md
    canonical_path.write_text(content, encoding='utf-8')
    print(f"  [1/4] Wrote vault/playbooks/{uid}.md")

    # Step C — verify canonical exists on disk (full rebuild reconciles the index at end)
    # Note: --only cannot freshen vault/playbooks/ entries that aren't yet indexed;
    # filesystem existence is sufficient before writing the thin-pointer.
    print(f"  [2/4] Skipped per-file index (full rebuild at end indexes vault/playbooks/)")

    # Step D — verify canonical file exists
    if not canonical_path.exists():
        print(f"  ERROR: {uid}.md not found on disk after write — aborting")
        return False
    print(f"  [3/4] Verified: vault/playbooks/{uid}.md exists on disk")

    # Step E — overwrite kernel path with thin-pointer
    source_path.write_text(thin_pointer, encoding='utf-8')
    print(f"  [4/4] Kernel path {source_rel} → thin-pointer")

    return True


def archive_one(uid: str, dry_run: bool = True) -> bool:
    """Archive a migrations/ playbook in place by setting state: archived."""
    if uid not in ARCHIVES:
        print(f"ERROR: {uid} not in archives list")
        return False
    source_rel = ARCHIVES[uid]
    source_path = VAULT_ROOT / source_rel
    if not source_path.exists():
        print(f"  [SKIP] {source_rel} — not found (already moved or absent)")
        return True

    print(f"\n{'[DRY-RUN] ' if dry_run else '[APPLY] '}Archive {uid}: {source_rel}")

    if dry_run:
        print(f"  [DIFF] {source_rel} — add state: archived")
        return True

    content = source_path.read_text('utf-8')
    content = _add_frontmatter_field(content, 'state', 'archived')
    source_path.write_text(content, encoding='utf-8')
    print(f"  [1/1] Archived in-place: {source_rel}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="S2 Playbook Mover — v1.69 copy-to-vault-first migration")
    parser.add_argument("--uid", default=None,
                        help="Single UID to process (or 'all' for all non-boot-contract playbooks)")
    parser.add_argument("--archives", action="store_true",
                        help="Process archive-in-place (migrations/) dispositions")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Show diff without writing (default)")
    parser.add_argument("--apply", action="store_true",
                        help="Execute the move")
    args = parser.parse_args()

    dry_run = not args.apply
    success = True

    if args.archives:
        for uid in ARCHIVES:
            if not archive_one(uid, dry_run=dry_run):
                success = False
        return 0 if success else 1

    if args.uid == 'all':
        for uid in DISPOSITION:
            if not move_one(uid, dry_run=dry_run):
                success = False
    elif args.uid:
        if not move_one(args.uid, dry_run=dry_run):
            success = False
    else:
        print("Usage: --uid <uid|all> [--apply] OR --archives [--apply]")
        print(f"Available UIDs: {', '.join(DISPOSITION.keys())}")
        print(f"Boot-contract (excluded): {', '.join(BOOT_CONTRACT)}")
        return 1

    if not dry_run:
        print("\n[DONE] All specified moves complete. Run full rebuild to reconcile.")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
