#!/usr/bin/env python3
"""
---
uid: a7c5e3f1
title: rehydrate — Tool
name: rehydrate
type: tool
status: active
owner: argus
domain: Rehydrate vault into navigable folder trees — symlinks under 00-tropo-nav/ for active/archived/all views.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/a7c5e3f1.py [--output-dir-name DIR] [--vault-path PATH]
script_path: vault/tools/a7c5e3f1.py
input:
  type: object
  properties:
    output-dir-name:
      type: string
      description: 'Default: 00-tropo-nav'
    vault-path:
      type: string
destructive: true
audit_required: false
writes_scope:
- 00-tropo-nav/**
governance_category: lifecycle
description: 'Reads the flat vault (vault/files/<uid>.md) and project tree, generates human-navigable folder hierarchy under <output-dir-name>/ using symlinks. Three companion trees: 00-tropo-all/ (active + archived), 00-tropo-active/ (state: active only), 00-tropo-archived/ (state: archived only). Single root entry in sidebar; click to choose view. Project anchors live INSIDE their own folder (parent shows child folders cleanly; project''s own folder shows anchor at top alongside children).'
domain_tags:
- rehydrate
- navigation
- symlinks
- project-tree
- three-views
- rendering
trigger_description: Reach for this when the navigable folder tree at 00-tropo-nav/ is stale or missing — typically after running rebuild-vault.py to update the index + project-tree. The symlink hierarchy is the human-navigable surface; rebuild-vault.py rebuilds the data; rehydrate.py rebuilds the navigation. Run rehydrate.py whenever you want the project hierarchy in your editor's file tree to reflect current vault state. The active/archived/all views let you collapse archived noise without losing it.
created: 2026-05-09
created_by: argus-a53
modified: 2026-05-09
modified_by: argus-a53
governed_by: d5e1b4a3
capsule_version: '2.5'
schema_version: 2
extraction_scope: ship
member_of:
- c7e4f9a2
tags:
- tool
- cli
- rehydrate
- navigation
- symlinks
- v1.15-stream-b
subsystem_hub:
- dbc1cbbf
---
"""

"""Rehydrate ledger into navigable folder trees with hardlinks.

Reads the flat ledger (`vault/files/<uid>.md`) and the project tree index,
and generates a human-navigable folder hierarchy under <output-dir-name>/

v1.51.0 amendment (vela-v51 2026-05-23): swapped symlinks → hardlinks per Mike-V51
UX report — VS Code resolved symlinks to canonical target, landing the user in
vault/files/<uid>.md instead of the nav-tree path they clicked. Hardlinks preserve
the path-the-user-opened-with in VS Code while keeping content canonical (same inode).
Variable name `symlinks_created` retained for diff minimality.
using symlinks. Every governed artifact appears under every project it is
`member_of`.

Three companion trees are generated under a single navigation root:

    <output-dir-name>/
    ├── 00-tropo-all/         all entries (active + archived)
    ├── 00-tropo-active/      state: active only
    └── 00-tropo-archived/    state: archived only

Single root entry in the sidebar; click to choose the view. Default output
directory name: `00-tropo-nav`.

Project-anchor placement (2026-04-25 amendment):
    Project anchors live INSIDE their own folder, not in their parent's
    folder. This keeps the parent showing child folders cleanly, and the
    project's own folder shows the anchor at the top alongside its
    children. Single navigation primitive.

Usage:
    python3 rehydrate.py <output-dir-name> [--vault-path <path>]

Vault root resolution (2026-05-03 amendment, Metis G50 — align with Tier 1 v1.1 / ADR-032):
    Anchors checked in order: `.tropo/boot-config.md` (current Tier 1 v1.1 standard),
    then `settings/env.md` (legacy, retained for older vaults).

    1. Explicit `--vault-path <path>` argument wins (must contain at least one anchor).
    2. Otherwise: walk up from this script's location for either anchor.
    3. Fallback: cwd contains either anchor, use that.
    4. Otherwise: raise with a clear error naming both anchors.

This script is part of the Tropo-OS kernel and ships with every release via
`build-release.py`. It is called by `.tropo/scripts/rebuild-vault.py` (engineering
repo) — see that file's `rehydrateScript` invocation.

Governed by: `.tropo/scripts/CAPSULE.md` (kernel-tier scripts).
"""

import argparse
import json
import os
import re
import shutil
from pathlib import Path


VAULT_ANCHORS = (
    Path(".tropo") / "boot-config.md",  # Tier 1 v1.1 (ADR-032) — current standard
    Path("settings") / "env.md",        # legacy — retained for older vaults
)


def _has_anchor(directory: Path) -> bool:
    return any((directory / anchor).exists() for anchor in VAULT_ANCHORS)


def resolve_vault_root(explicit_path):
    """Resolve vault root via explicit arg → walk-up-for-anchor → cwd fallback."""
    anchor_list = ", ".join(str(a) for a in VAULT_ANCHORS)

    if explicit_path:
        p = Path(explicit_path).resolve()
        if not _has_anchor(p):
            raise SystemExit(
                f"--vault-path {p} contains no Tropo-OS vault anchor "
                f"({anchor_list}). Not a Tropo-OS vault."
            )
        return p

    p = Path(__file__).resolve().parent
    while p != p.parent:
        if _has_anchor(p):
            return p
        p = p.parent

    cwd = Path.cwd()
    if _has_anchor(cwd):
        return cwd

    raise SystemExit(
        f"Could not resolve vault root. No anchor ({anchor_list}) found walking "
        f"up from script location ({Path(__file__).resolve().parent}) or in cwd "
        f"({cwd}). Pass --vault-path <absolute path> explicitly."
    )


def sanitize(name: str) -> str:
    name = name.replace("/", "-").replace(":", "-").replace("\\", "-")
    return re.sub(r'[<>"|?*]', "-", name).strip()


def build_project_paths(project_tree_path, index, project_states, state_filter):
    """Build {uid: [relative_path, ...]} for projects matching the state filter.

    Multi-parent rendering (v1.9.x amendment by vela-v42, 2026-05-07): every project
    appears under EVERY navigable parent in its `member_of` array — same composable-graph
    behavior as governed file-symlinks. Mirrors V40 §3 Thread 4 (composable backlog graph)
    at the folder level so entity-inboxes render under their parent-entity's inbox AND
    under the universal vault-inbox simultaneously.

    Reads the navigable-project SET from project_tree_path (rebuild-vault.py already
    filters type:project + type:pipeline-roots cleanly via _is_navigable()). Reads
    multi-parent EDGES from the full index `member_of` arrays (not the singular `parent`
    in project_tree_path).

    Cycles are broken by a per-traversal visited set. Cascade-filter behavior preserved:
    if ALL navigable parents are state-mismatched, the project does NOT render at root
    (closes the archived-cascade leak per v1.6 architectural discipline).

    state_filter: None (all), "active", or "archived".
    project_states: {uid: state} mapping from the index.
    index: full {uid: {title, state, type, member_of}} from load_index() — used for
        member_of edges (project_tree.jsonl only carries singular `parent`).

    Returns: {uid: [Path, ...]} — list of relative paths per project (one per parent).
    """
    # Set of navigable UIDs (already correctly filtered by rebuild-vault.py)
    navigable_uids = set()
    with open(project_tree_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            navigable_uids.add(json.loads(line)["uid"])

    # NOTE v1.51 (Argus A80 2026-05-23): v1.13.1 hub-edge-as-metadata workaround REMOVED.
    # Post-v2.5 capsule amendment + migration (.tropo/scripts/migrate-v14-subsystem-hub-split.py
    # applied 2026-05-23 to 1059 entries): subsystem hub edges live in `subsystem_hub:` field;
    # `member_of:` contains only true parent project UIDs. Validation Check 11 at
    # project.capsule v2.5 enforces no-hub-UIDs-in-member_of post-migration.
    # Tree-building now reads BOTH member_of AND subsystem_hub as parent-edge sources;
    # no UIDs are skipped at render time.
    hub_uids = {uid for uid, e in index.items() if e.get("subsystem_name")}  # retained for informational use only

    paths = {}  # uid -> list[Path]

    def get_paths(uid, visited):
        if uid in visited:
            return []  # cycle break
        if uid in paths:
            return paths[uid]
        if uid not in navigable_uids:
            return None
        if state_filter is not None and project_states.get(uid) != state_filter:
            return None  # this project is state-filtered

        entry = index.get(uid)
        if not entry:
            return None
        title = entry["title"]
        name = sanitize(title)

        # Walk every navigable parent. v1.14 schema split (v1.51 Argus A80 2026-05-23):
        # parent edges come from BOTH `member_of:` (true parent projects) AND `subsystem_hub:`
        # (subsystem hub catalog membership). Both render as parent edges in the project tree.
        # Hub-skip workaround removed; Validation Check 11 at project.capsule v2.5 enforces
        # no-hub-UIDs-in-member_of post-migration. Dedupe via dict-ordering preservation.
        seen_parents: set[str] = set()
        parent_uids: list[str] = []
        for pid in list(entry.get("member_of", []) or []) + list(entry.get("subsystem_hub", []) or []):
            if pid in navigable_uids and pid not in seen_parents:
                parent_uids.append(pid)
                seen_parents.add(pid)

        # Entity-inbox disambiguation (v1.9.x amendment by mike-vela 2026-05-07):
        # Projects whose title starts with "01-inbox" (entity-scoped inboxes per the
        # numerical-prefix convention) collide visually when the composable graph
        # nests them (e.g., dev-pipeline's 01-inbox inside tropo-work's 01-inbox
        # inside 01-studio-inbox renders as `01-inbox/01-inbox/01-inbox/`).
        # The fix: prefix entity-inbox folder names with the primary navigable parent's
        # title — so dev-pipeline's "01-inbox" renders as "dev-pipeline-01-inbox" at
        # every path. The universal "01-studio-inbox" is excluded because it IS the
        # root (no parent to pull from). Constant disambiguated name across all
        # render paths preserves identity; minor redundancy in the entity's own
        # primary path (e.g., `tropo-work/dev-pipeline/dev-pipeline-01-inbox/`) is
        # the trade-off against universal scan-clarity.
        if title.startswith("01-inbox") and not title.startswith("01-studio-inbox"):
            for parent_uid in parent_uids:
                parent_entry = index.get(parent_uid)
                if parent_entry and parent_entry.get("title"):
                    parent_name = sanitize(parent_entry["title"])
                    name = f"{parent_name}-{name}"
                    break  # only first navigable parent contributes

        new_visited = visited | {uid}

        results = []
        all_parents_state_filtered = bool(parent_uids)  # default true if there are parents; flipped when one resolves
        for parent_uid in parent_uids:
            # If parent is state-mismatched, that's a cascade-filter signal (preserve below)
            if state_filter is not None and project_states.get(parent_uid) != state_filter:
                continue
            parent_paths = get_paths(parent_uid, new_visited)
            if parent_paths is None:
                # parent filtered (not navigable or state-filtered upstream) — skip this edge
                continue
            if len(parent_paths) == 0:
                # cycle from this branch — skip
                continue
            all_parents_state_filtered = False
            for pp in parent_paths:
                results.append(pp / name)

        if not results:
            # No navigable parents OR all parents resolved to nothing.
            # Two cases preserved from v1.6 cascade-filter discipline:
            # (a) ALL parents state-mismatched → cascade-filter: do not surface at root
            # (b) No project-parents at all (orphan-by-typing) OR only cycles → root at top level
            if all_parents_state_filtered and parent_uids:
                return None  # cascade-filter; do not cache (preserves original semantics)
            results.append(Path(name))

        paths[uid] = results
        return results

    for uid in list(navigable_uids):
        get_paths(uid, set())

    return paths


def load_index(index_path):
    """Load uid -> {title, state, type, member_of, subsystem_hub, subsystem_name} from
    the pre-built index.

    v1.14 schema split (Argus A80 2026-05-23): subsystem_hub: is the canonical home for
    subsystem hub catalog membership; member_of: holds true parent project UIDs only.
    Tree-building in build_project_paths reads BOTH fields as parent-edge sources.
    subsystem_name retained for hub-identification (informational use).
    """
    entries = {}
    with open(index_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            entries[e["uid"]] = {
                "title": e.get("title", ""),
                "state": e.get("state", ""),
                "type": e.get("type", ""),
                "member_of": e.get("member_of", []),
                "subsystem_hub": e.get("subsystem_hub", []),
                "subsystem_name": e.get("subsystem_name", ""),
            }
    return entries


def build_one_tree(vault_root, output_dir, ledger_files, project_tree_path,
                   index, project_states, state_filter, label):
    """Build one filtered tree of project folders + symlinks.

    Multi-parent rendering (v1.9.x): project_paths is now {uid: [Path, ...]} —
    each project may render under multiple parent paths (composable graph).
    Files (non-project entries) symlink under EVERY path of EVERY navigable
    member_of parent, so entries appear at every applicable location in the tree.
    Symlink creation is idempotent (skip if link already exists at that path)."""
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    project_paths = build_project_paths(project_tree_path, index, project_states, state_filter)

    # Create directories for every path each project should appear at
    folder_count = 0
    for paths_list in project_paths.values():
        for rel_path in paths_list:
            (output_dir / rel_path).mkdir(parents=True, exist_ok=True)
            folder_count += 1

    symlinks_created = 0
    skipped_orphans = 0
    skipped_filter = 0

    for ledger_file in sorted(ledger_files.glob("*.md")):
        uid = ledger_file.stem
        entry = index.get(uid)
        if not entry or not entry["title"]:
            continue

        # Filter by entry state.
        if state_filter is not None and entry["state"] != state_filter:
            skipped_filter += 1
            continue

        link_name = f"{uid} — {sanitize(entry['title'])}.md"

        # Project anchors live inside their own folder(s) — one anchor per rendered path.
        if uid in project_paths:
            for project_path in project_paths[uid]:
                project_folder = output_dir / project_path
                link_path = project_folder / link_name
                if link_path.exists() or link_path.is_symlink():
                    continue  # idempotent (handles legacy symlinks during transition)
                # Hardlinks (v1.51.0 fix-on-see by vela-v51 2026-05-23 per Mike-V51 UX report):
                # symlinks resolved to canonical target in VS Code, collapsing nav-tree
                # walkability — opening a 00-tropo-nav link landed Mike in vault/files/<uid>.md
                # via symlink-follow, defeating OP-12 Tropo-Nav Path intent. Hardlinks point at
                # same inode but VS Code shows the path used to open. Same-filesystem requirement
                # holds (argo-os/ is one disk); editing one updates both (canonical content
                # preserved); rm one doesn't delete the other (idempotent rebuild safe).
                os.link(ledger_file, link_path)
                symlinks_created += 1
            continue

        # Non-project entries live in each parent project's folder
        # (only those parents whose state matches the filter).
        # Multi-parent: walk every path of every navigable parent.
        member_of = entry["member_of"]
        if not member_of:
            skipped_orphans += 1
            continue

        placed = False
        for project_uid in member_of:
            if project_uid not in project_paths:
                continue
            for project_path in project_paths[project_uid]:
                project_folder = output_dir / project_path
                link_path = project_folder / link_name
                if link_path.exists() or link_path.is_symlink():
                    continue  # idempotent — a file member_of two projects with overlapping paths (handles legacy symlinks during transition)
                # Hardlinks per v1.51.0 fix-on-see — see comment at first os.link() site above
                os.link(ledger_file, link_path)
                symlinks_created += 1
                placed = True

        if not placed:
            skipped_orphans += 1

    print(f"  {label}: {len(project_paths)} unique projects ({folder_count} rendered folder paths), "
          f"{symlinks_created} symlinks ({skipped_orphans} orphans, {skipped_filter} state-filtered)")


def main():
    parser = argparse.ArgumentParser(
        description="Rehydrate ledger into navigable folder trees with symlinks."
    )
    parser.add_argument(
        "output_dir_name",
        help="Output navigation root (relative to vault root). Default convention: 00-tropo-nav",
    )
    parser.add_argument(
        "--vault-path",
        default=None,
        help="Vault root path. Defaults to auto-detection.",
    )
    args = parser.parse_args()

    vault_root = resolve_vault_root(args.vault_path)
    ledger_files = vault_root / "vault" / "files"   # path renamed ledger/ → vault/ in v1.9.0; variable name retained for diff minimality (v1.10+ rename candidate)
    project_tree_path = vault_root / "vault" / "00-project-tree.jsonl"
    index_path = vault_root / "vault" / "00-index.jsonl"
    nav_root = vault_root / args.output_dir_name

    print(f"Vault root: {vault_root}")
    print(f"Loading index from {index_path.name}...")
    index = load_index(index_path)
    project_states = {uid: entry["state"] for uid, entry in index.items()}
    print(f"  {len(index)} entries indexed")

    print(f"Generating navigation trees under {nav_root}/...")

    if nav_root.exists():
        shutil.rmtree(nav_root)
    nav_root.mkdir(parents=True)

    # Three trees side-by-side. Single sidebar root.
    build_one_tree(vault_root, nav_root / "00-tropo-all",
                   ledger_files, project_tree_path, index,
                   project_states, None, "all")
    build_one_tree(vault_root, nav_root / "00-tropo-active",
                   ledger_files, project_tree_path, index,
                   project_states, "active", "active")
    build_one_tree(vault_root, nav_root / "00-tropo-archived",
                   ledger_files, project_tree_path, index,
                   project_states, "archived", "archived")

    # Best-effort cleanup of the legacy single-tree directory if it still exists.
    legacy = vault_root / "00-tropo-all-folders"
    if legacy.exists() and legacy.is_dir():
        shutil.rmtree(legacy)
        print(f"Removed legacy directory: {legacy.name}/")

    print(f"Done. Output: {nav_root}")


if __name__ == "__main__":
    main()
