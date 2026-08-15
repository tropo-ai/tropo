#!/usr/bin/env python3
"""
---
uid: a7c5e3f1
title: rehydrate — Tool
name: rehydrate
type: tool
status: active
owner: argus
domain: Rehydrate vault into navigable folder trees — hardlinks for governed entries under 00-tropo-nav/; source-file symlinks for available folder mounts (7b1e0ae5).
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/tropo-rehydrate.py [--output-dir-name DIR] [--vault-path PATH]
script_path: vault/tools/tropo-rehydrate.py
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
description: 'Reads the flat vault (vault/files/<uid>.md) and project tree, generates human-navigable folder hierarchy under <output-dir-name>/. Governed entries use hardlinks (v1.51). Available folder-mount leaves use symlinks to the real source file (7b1e0ae5 — cross-filesystem; opening reaches the native app). Three companion trees: 00-tropo-all/, 00-tropo-active/, 00-tropo-archived/. Project anchors live INSIDE their own folder.'
domain_tags:
- rehydrate
- navigation
- hardlinks
- source-symlinks
- project-tree
- three-views
- rendering
- mount-identity
trigger_description: Reach for this when the navigable folder tree at 00-tropo-nav/ is stale or missing — typically after running rebuild-vault.py to update the index + project-tree. The nav hierarchy is the human-navigable surface; rebuild-vault.py rebuilds the data; rehydrate.py rebuilds the navigation. Run rehydrate.py whenever you want the project hierarchy in your editor's file tree to reflect current vault state. The active/archived/all views let you collapse archived noise without losing it.
created: 2026-05-09
created_by: argus-a53
modified: 2026-05-09
modified_by: argus-a53
governed_by: d5e1b4a3
capsule_version: '2.5'
schema_version: 2
extraction_scope: ship
member_of:
- 8dd772a0
tags:
- tool
- cli
- rehydrate
- navigation
- hardlinks
- source-symlinks
- v1.15-stream-b
- mount-identity
subsystem_hub:
- dbc1cbbf
---
"""

"""Rehydrate vault into navigable folder trees.

Reads the flat vault (`vault/files/<uid>.md`) and the project tree index,
and generates a human-navigable folder hierarchy under <output-dir-name>/.

Linking policy (codified by 7b1e0ae5; both halves in writing):

- **Governed entries → hardlinks** (v1.51.0, vela-v51 2026-05-23 / Mike-V51):
  VS Code resolved symlinks to the canonical target, collapsing nav walkability
  onto ``vault/files/<uid>.md``. Hardlinks keep the path-the-user-opened-with.
- **Mounted source files → symlinks** (7b1e0ae5 / Mike 2026-08-11): hardlinks
  cannot cross filesystems and live mounts sit on other volumes. For a mounted
  source, resolving to the real file *is* the point (Finder/editor opens the
  native app). Only mounts whose registry ``availability`` is ``available``
  render source leaves; unavailable mounts keep record hardlinks only.
  The governed ``.md`` record does not render a duplicate leaf beside the source.

Variable name ``symlinks_created`` counts both hardlinks and source symlinks
(historical; retained for diff minimality). Every governed artifact appears
under every project it is ``member_of``.

Three companion trees are generated under a single navigation root:

    <output-dir-name>/
    ├── 00-tropo-all/         all entries (active + archived)
    ├── 00-tropo-active/      state: active only
    └── 00-tropo-archived/    state: archived only

Usage:
    python3 tropo-rehydrate.py <output-dir-name> [--vault-path <path>]

This script is part of the Tropo-OS kernel and ships with every release via
`build-release.py`. It is called by `vault/tools/tropo-rebuild-vault.py`.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from lib import index_surfaces

FOLDER_MOUNTS_REL = Path(".tropo-studio") / "folder-mounts.json"
AVAILABILITY_AVAILABLE = "available"


VAULT_ANCHORS = (
    Path(".tropo") / "boot-config.md",  # Tier 1 v1.1 (ADR-032) — current standard
    Path("settings") / "env.md",        # legacy — retained for older vaults
)
NAV_COMPONENT_MAX_BYTES = 240
NAV_COMPONENT_HASH_CHARS = 16


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


def navigation_component(stem: str, *, identity: str, suffix: str = "") -> str:
    """Fit one rendered navigation name within a deterministic byte budget.

    The canonical title remains untouched in source/index surfaces. Only the
    disposable navigation projection is shortened. A digest of the complete
    pre-shortening component prevents titles sharing a long prefix from
    colliding, while UTF-8-aware clipping keeps the readable title prefix.
    """
    candidate = f"{stem}{suffix}"
    candidate_bytes = candidate.encode("utf-8", errors="surrogatepass")
    if len(candidate_bytes) <= NAV_COMPONENT_MAX_BYTES:
        return candidate

    digest_source = f"{identity}\0{candidate}".encode("utf-8", errors="surrogatepass")
    digest = hashlib.sha256(digest_source).hexdigest()[:NAV_COMPONENT_HASH_CHARS]
    marker = f" …~{digest}"
    fixed_bytes = len(marker.encode("utf-8")) + len(suffix.encode("utf-8"))
    readable_budget = NAV_COMPONENT_MAX_BYTES - fixed_bytes
    if readable_budget < 0:
        raise ValueError("navigation component suffix exceeds the byte budget")

    readable = stem.encode("utf-8", errors="surrogatepass")[:readable_budget].decode(
        "utf-8", errors="ignore"
    ).rstrip()
    return f"{readable}{marker}{suffix}"


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

        name = navigation_component(name, identity=uid)
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


def load_mount_availability(vault_root):
    """Return ``(availability_by_uid, root_path_by_uid)`` from folder-mounts.json.

    7b1e0ae5 §3.5 reads registry availability only — never invents it.
    """
    path = Path(vault_root) / FOLDER_MOUNTS_REL
    if not path.is_file():
        return {}, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}, {}
    mounts = data.get("mounts") if isinstance(data, dict) else {}
    if not isinstance(mounts, dict):
        return {}, {}
    out = {}
    roots = {}
    for uid, raw in mounts.items():
        if not isinstance(raw, dict):
            continue
        out[str(uid)] = raw.get("availability")
        roots[str(uid)] = raw.get("path")
    return out, roots


def load_index(index_path, archive_index_path=None):
    """Load uid -> entry fields from the current + archive index union.

    Carries ``mount_uid`` / ``source_path`` / ``mount_relpath`` / ``availability``
    / ``source_filename`` for external-artifact rows (7b1e0ae5 §3.5).

    v1.14 schema split (Argus A80 2026-05-23): subsystem_hub: is the canonical home for
    subsystem hub catalog membership; member_of: holds true parent project UIDs only.
    Tree-building in build_project_paths reads BOTH fields as parent-edge sources.

    ADR-047 Layer 1: rehydrate is intentionally an archive-aware consumer
    because it renders BOTH ``00-tropo-active`` and ``00-tropo-archived``.
    """
    entries = {}
    paths = [Path(index_path)]
    if archive_index_path is not None:
        paths.append(Path(archive_index_path))
    for path in paths:
        if not path.is_file():
            continue
        for e in index_surfaces.iter_jsonl(path):
            entries[e["uid"]] = {
                "title": e.get("title", ""),
                "state": e.get("state", ""),
                "type": e.get("type", ""),
                "member_of": e.get("member_of", []),
                "subsystem_hub": e.get("subsystem_hub", []),
                "subsystem_name": e.get("subsystem_name", ""),
                "mount_uid": e.get("mount_uid"),
                "source_path": e.get("source_path") or e.get("original_path") or "",
                "mount_relpath": e.get("mount_relpath") or "",
                "availability": e.get("availability"),
                "source_filename": e.get("source_filename") or "",
            }
    return entries


def _safe_link(kind, target, link_path, *, skipped, leaf_name):
    """Create one hardlink or symlink; never abort the tree on a single failure.

    7b1e0ae5 §3.5 per-leaf guard: EXDEV / missing target / permission skips the
    leaf and reports it by name; the build continues.
    """
    try:
        if kind == "hardlink":
            os.link(target, link_path)
        elif kind == "symlink":
            os.symlink(target, link_path)
        else:
            raise ValueError(f"unknown link kind {kind!r}")
        return True
    except OSError as exc:
        skipped.append(f"{leaf_name} ({exc.strerror or exc.__class__.__name__})")
        return False


def _source_leaf_target(entry, mount_roots):
    """Resolve the real source path for a mounted leaf, or None.

    Authoritative: registry mount root + ``mount_relpath``. Never stats-deep
    (76126a26 §5b B1); placeholders get the symlink like any other file.
    """
    mount_uid = entry.get("mount_uid")
    if not mount_uid:
        return None
    root = mount_roots.get(mount_uid)
    if not root:
        return None
    rel = entry.get("mount_relpath") or ""
    if not rel:
        # Fall back to basename of advisory source_path only when relpath absent.
        source_path = entry.get("source_path") or ""
        if source_path:
            return Path(source_path)
        return None
    return Path(root) / rel


def _source_leaf_name(entry, uid):
    """Real filename for the source leaf (not the governed uid — title.md)."""
    name = entry.get("source_filename") or ""
    if not name:
        rel = entry.get("mount_relpath") or ""
        name = Path(rel).name if rel else ""
    if not name:
        source_path = entry.get("source_path") or ""
        name = Path(source_path).name if source_path else ""
    if not name:
        name = f"{uid}.bin"
    return navigation_component(sanitize(name), identity=uid, suffix="")


def build_one_tree(vault_root, output_dir, ledger_files, project_tree_path,
                   index, project_states, state_filter, label,
                   mount_availability=None, mount_roots=None):
    """Build one filtered tree of project folders + leaves.

    Multi-parent rendering (v1.9.x): project_paths is now {uid: [Path, ...]} —
    each project may render under multiple parent paths (composable graph).
    Files (non-project entries) link under EVERY path of EVERY navigable
    member_of parent. Link creation is per-leaf guarded (7b1e0ae5).
    """
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    mount_availability = mount_availability or {}
    mount_roots = mount_roots or {}

    project_paths = build_project_paths(project_tree_path, index, project_states, state_filter)

    folder_count = 0
    for paths_list in project_paths.values():
        for rel_path in paths_list:
            (output_dir / rel_path).mkdir(parents=True, exist_ok=True)
            folder_count += 1

    symlinks_created = 0
    source_leaves = 0
    skipped_orphans = 0
    skipped_filter = 0
    skipped_leaves = []

    for ledger_file in sorted(ledger_files.glob("*.md")):
        uid = ledger_file.stem
        entry = index.get(uid)
        if not entry or not entry["title"]:
            continue

        if state_filter is not None and entry["state"] != state_filter:
            skipped_filter += 1
            continue

        record_link_name = navigation_component(
            f"{uid} — {sanitize(entry['title'])}",
            identity=uid,
            suffix=".md",
        )

        # Project anchors: always the governed record (hardlink).
        if uid in project_paths:
            for project_path in project_paths[uid]:
                project_folder = output_dir / project_path
                link_path = project_folder / record_link_name
                if link_path.exists() or link_path.is_symlink():
                    continue
                if _safe_link(
                    "hardlink",
                    ledger_file,
                    link_path,
                    skipped=skipped_leaves,
                    leaf_name=record_link_name,
                ):
                    symlinks_created += 1
            continue

        member_of = entry["member_of"]
        if not member_of:
            skipped_orphans += 1
            continue

        mount_uid = entry.get("mount_uid")
        use_source_leaf = (
            bool(mount_uid)
            and mount_availability.get(mount_uid) == AVAILABILITY_AVAILABLE
        )
        source_target = _source_leaf_target(entry, mount_roots) if use_source_leaf else None
        if use_source_leaf and source_target is not None:
            leaf_name = _source_leaf_name(entry, uid)
            placed = False
            for project_uid in member_of:
                if project_uid not in project_paths:
                    continue
                for project_path in project_paths[project_uid]:
                    project_folder = output_dir / project_path
                    link_path = project_folder / leaf_name
                    if link_path.exists() or link_path.is_symlink():
                        placed = True
                        continue
                    if _safe_link(
                        "symlink",
                        source_target,
                        link_path,
                        skipped=skipped_leaves,
                        leaf_name=leaf_name,
                    ):
                        symlinks_created += 1
                        source_leaves += 1
                        placed = True
            if not placed:
                skipped_orphans += 1
            continue

        # Governed record hardlink (including mounted rows on unavailable mounts).
        placed = False
        for project_uid in member_of:
            if project_uid not in project_paths:
                continue
            for project_path in project_paths[project_uid]:
                project_folder = output_dir / project_path
                link_path = project_folder / record_link_name
                if link_path.exists() or link_path.is_symlink():
                    placed = True
                    continue
                if _safe_link(
                    "hardlink",
                    ledger_file,
                    link_path,
                    skipped=skipped_leaves,
                    leaf_name=record_link_name,
                ):
                    symlinks_created += 1
                    placed = True

        if not placed:
            skipped_orphans += 1

    print(
        f"  {label}: {len(project_paths)} unique projects "
        f"({folder_count} rendered folder paths), "
        f"{symlinks_created} links ({source_leaves} source leaves, "
        f"{skipped_orphans} orphans, {skipped_filter} state-filtered, "
        f"{len(skipped_leaves)} leaf-skips)"
    )
    return skipped_leaves


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Rehydrate vault into navigable folder trees "
            "(hardlinks for governed entries; source symlinks for available mounts)."
        )
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
    ledger_files = vault_root / "vault" / "files"
    project_tree_path = vault_root / "vault" / "00-project-tree.jsonl"
    index_path = vault_root / "vault" / "00-index.jsonl"
    archive_index_path = vault_root / "vault" / "00-archive-index.jsonl"
    nav_root = vault_root / args.output_dir_name

    print(f"Vault root: {vault_root}")
    print(f"Loading index union from {index_path.name} + {archive_index_path.name}...")
    index = load_index(index_path, archive_index_path)
    project_states = {uid: entry["state"] for uid, entry in index.items()}
    mount_availability, mount_roots = load_mount_availability(vault_root)
    print(f"  {len(index)} entries indexed")
    available_mounts = sum(
        1 for v in mount_availability.values() if v == AVAILABILITY_AVAILABLE
    )
    print(f"  {available_mounts} available folder mount(s) for source leaves")

    print(f"Generating navigation trees under {nav_root}/...")

    if nav_root.exists():
        shutil.rmtree(nav_root)
    nav_root.mkdir(parents=True)

    all_skipped = []
    for tree_name, state_filter, label in (
        ("00-tropo-all", None, "all"),
        ("00-tropo-active", "active", "active"),
        ("00-tropo-archived", "archived", "archived"),
    ):
        skipped = build_one_tree(
            vault_root,
            nav_root / tree_name,
            ledger_files,
            project_tree_path,
            index,
            project_states,
            state_filter,
            label,
            mount_availability=mount_availability,
            mount_roots=mount_roots,
        )
        all_skipped.extend(skipped or [])

    legacy = vault_root / "00-tropo-all-folders"
    if legacy.exists() and legacy.is_dir():
        shutil.rmtree(legacy)
        print(f"Removed legacy directory: {legacy.name}/")

    if all_skipped:
        # Dedup while preserving order for the end-of-build report.
        seen = set()
        unique = []
        for name in all_skipped:
            if name in seen:
                continue
            seen.add(name)
            unique.append(name)
        print(f"Skipped {len(unique)} leaf link(s) by name:")
        for name in unique:
            print(f"  - {name}")

    print(f"Done. Output: {nav_root}")


if __name__ == "__main__":
    main()
