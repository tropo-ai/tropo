#!/usr/bin/env python3
"""
---
uid: b8e4f1a3
title: generate-relations-header — Tool
name: generate-relations-header
type: tool
status: active
owner: argus
domain: Render Relations + Members navigation blocks from a file's frontmatter — UID-graph navigation surface.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/b8e4f1a3.py [--write] [--vault-root PATH] <target>...
script_path: vault/tools/b8e4f1a3.py
input:
  type: object
  required:
  - target
  properties:
    target:
      type: array
      items:
        type: string
      description: File or directory paths. Directories scanned non-recursively for *.md.
    write:
      type: boolean
      description: 'Modify files in place (default: dry-run preview to stdout)'
    vault-root:
      type: string
output:
  type: object
  properties:
    verdict:
      type: string
      enum:
      - pass
      - partial
    files_processed:
      type: integer
    blocks_inserted:
      type: integer
    blocks_updated:
      type: integer
destructive: true
audit_required: false
writes_scope:
- vault/files/**
- .tropo/capsules/**
- agents/**
- '**/*.md'
governance_category: lifecycle
description: 'Renders two navigation blocks from a file''s frontmatter: (1) Relations — outbound UID-reference fields (governed_by, member_of, etc.) as clickable markdown links; (2) Members — inverse member_of (every governed entry that points AT this one) with typed-cap grouping (5 per type + ''N more'' overflow). Pattern established Argus A34 + Mike Maziarz 2026-04-25; Vela V42 patched + bulk-applied across 1064 files 2026-05-09; Argus A53 v1.15.2 added Members section + graduated to kernel tier 2026-05-09. Hooked into rebuild-vault.py wrapper as Step 4 — comprehensive-cadence rendering automation.'
domain_tags:
- relations-rendering
- members-rendering
- inverse-member-of
- typed-cap
- navigation-surface
- body-frontmatter-sync
- kernel-tier-graduated
- v1.15.2-stream-a-d
trigger_description: Reach for this when you need to refresh the Relations + Members navigation blocks in a vault entry's body — typically after editing the file's member_of frontmatter or any other UID-reference field. Run --write to modify in place; without --write for dry-run preview. Or run rebuild-vault.py wrapper to refresh Relations + Members across the whole vault as part of the comprehensive cadence (this script is Step 4 of that flow). The Members section uses typed-cap format (5 per type + overflow indicator) so hub entries with many children (tropo-governance has 41 decisions, 175 documents, 72 projects) stay scannable.
created: 2026-05-09
created_by: argus-a53
modified: 2026-05-09
modified_by: argus-a53
governed_by: d5e1b4a3
capsule_version: '2.5'
schema_version: 2
extraction_scope: ship
member_of:
- c2e8b4f6
tags:
- tool
- cli
- relations-rendering
- members-rendering
- kernel-tier
- v1.15.2-stream-a
- v1.15.2-stream-d-graduation
subsystem_hub:
- dbc1cbbf
---
"""

"""
generate-relations-header.py — Render Relations + Members navigation blocks from a
file's YAML frontmatter.

The Relations block surfaces frontmatter UID-reference fields (governed_by, member_of,
etc.) as clickable markdown links — the OUTBOUND edges of a governed graph node.
The Members section (v1.15.2 addition) surfaces the INVERSE member_of relation —
every governed entry that points AT this one — with typed-cap grouping per Vela
4c2456b4 §5 lock.

Pattern established 2026-04-25 by Argus A34 + Mike Maziarz at Stream 3 D3.2 of v1.4
(Tropo Work v3 release). Per Architectural Principle 2.6 ("Machines Compose, Humans
Experience"): frontmatter composes; the rendered block is the human surface.

Authors:
- argus-a34 2026-04-25 — initial Relations renderer (Stream 3 D3.2 of v1.4)
- vela-v42 2026-05-09 — v1.9.x rename drift patch + bulk apply across 1064 files
- argus-a53 2026-05-09 — v1.15.2 Stream A: Members section extension (typed-cap;
  inverse member_of index built once per run); v1.15.2 Stream D: graduated from
  .tropo-studio/scripts/ (Studio-admin tier) to .tropo/scripts/ (kernel tier) —
  pattern stabilized at 1064 files deployed; canonical home is now kernel.

Status: kernel-tier (graduated v1.15.2). Both locations are valid during transition;
.tropo-studio/scripts/ copy preserved as Vela-deployed snapshot for honest historical
record; the kernel copy is canonical going forward.

Usage
-----
Dry-run (emit block to stdout):
    python3 .tropo-studio/scripts/generate-relations-header.py path/to/file.md

In-place insert/update:
    python3 .tropo-studio/scripts/generate-relations-header.py --write path/to/file.md

Batch (process every .md file in a directory, non-recursive):
    python3 .tropo-studio/scripts/generate-relations-header.py --write .tropo/capsules/

Override vault root (rarely needed):
    python3 .tropo-studio/scripts/generate-relations-header.py --vault-root /path file.md

Insertion semantics
-------------------
- Block goes immediately after the H1 title (`# `), before the next non-blank line.
- If a "> **Relations**" block already exists, it is REPLACED (idempotent re-runs).
- Detection: lines starting with `> **Relations**` followed by adjacent `> ...` lines.

Frontmatter fields surfaced (navigation-relevant only)
------------------------------------------------------
governed_by | aligned_with | pattern_exemplar | pattern_family | extends |
composes_with | member_of | derived_from | composes_into | supersedes |
superseded_by | basis_spec | foundation | streams | gates

Skipped (not navigation): title, description, tags, dates, schema_version, file_ext,
extraction_scope, owner, author, created/modified provenance.

Title lookup
------------
1. `.tropo/capsules/*.capsule.md` — for capsule UIDs (parses frontmatter).
2. `vault/00-index.jsonl` — for vault entry UIDs (one JSON line per entry).
3. Fallback: render the bare UID with a "(title not found)" annotation.

Limitations
-----------
- Naive YAML parser. Handles capsule + ledger frontmatter shapes (scalars, inline
  lists, multi-line `- item` lists, comments). Does NOT handle nested objects,
  anchors, multiline strings, or other full-YAML features.
- Single-H1 assumption — block inserts after the first `# ` line in the body.
- Vault root resolution: walks up from the target file looking for
  `settings/env.md`. Fails loudly if not found (per the "no hardcoded paths" rule).
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Navigation-block suppression — types where the nav-block is more friction
# than help at first-encounter (operator-target user-facing content).
# v1.45.0 Stream 1: kb-article entries (operator FAQ + canonical KB articles) are
# read by stranger users in the first 10 minutes; the nav-block dump (path crumb +
# UID/type/state + siblings list + cited-by) front-loads governance metadata
# before content and was V47's R3 cold-boot FAIL "P0 — operator FAQ nav-block-at-head"
# finding. Suppress nav-block generation on these types; let the body content lead.
# Existing nav-blocks in suppressed-type files get stripped on next render pass via
# insert_or_update_block Step 1 (unconditional sentinel strip).
NAV_BLOCK_SUPPRESS_TYPES: frozenset = frozenset({"kb-article"})

# Field grouping — which frontmatter fields render on which line of the block.
# Ordering controls the visual order; labels match what readers expect.
FIELD_GROUPS: List[Tuple[str, List[str]]] = [
    ("Governed by", ["governed_by"]),
    ("Aligned with", ["aligned_with"]),
    ("Pattern exemplar", ["pattern_exemplar"]),
    ("Pattern family", ["pattern_family"]),
    ("Extends", ["extends"]),
    ("Composes with", ["composes_with"]),
    ("Member of", ["member_of"]),
    ("Derived from", ["derived_from"]),
    ("Composes into", ["composes_into"]),
    ("Supersedes", ["supersedes"]),
    ("Superseded by", ["superseded_by"]),
    ("Basis spec", ["basis_spec"]),
    ("Foundation", ["foundation"]),
    ("Streams", ["streams"]),
    ("Gates", ["gates"]),
]

NAVIGATION_FIELDS = {f for _, fs in FIELD_GROUPS for f in fs}

UID_RE = re.compile(r"^[0-9a-fA-F]{8}$")


def find_vault_root(start: Path) -> Path:
    """Walk up from `start` to find the studio root.

    Anchor priority (v1.9.0+ alignment with rehydrate.py + Tier 1 v1.1):
        1. `.tropo/boot-config.md` (current standard)
        2. `settings/env.md` (legacy; retained for older studios)

    Patched 2026-05-08 by vela-v42 for v1.9.x rename drift (was anchor-only on
    settings/env.md which no longer exists in the Studio).
    """
    cur = start.resolve()
    while cur != cur.parent:
        if (cur / ".tropo" / "boot-config.md").exists():
            return cur
        if (cur / "settings" / "env.md").exists():
            return cur
        cur = cur.parent
    raise RuntimeError(
        f"Could not find vault root walking up from {start}. "
        f"Pass --vault-root explicitly if running outside a studio."
    )


def parse_frontmatter(content: str) -> Tuple[Optional[dict], str, str]:
    """Returns (frontmatter_dict, frontmatter_raw_str, body_str).

    Returns (None, "", content) if no frontmatter is detected.
    """
    if not content.startswith("---\n"):
        return None, "", content
    end_match = re.search(r"\n---\n", content[4:])
    if not end_match:
        return None, "", content
    fm_text_end = end_match.start() + 4  # offset of `\n---\n` in `content`
    fm_raw_end = fm_text_end + len("\n---\n")
    fm_raw = content[:fm_raw_end]
    fm_text = content[4:fm_text_end]
    body = content[fm_raw_end:]
    fm_dict = parse_yaml_lite(fm_text)
    return fm_dict, fm_raw, body


def parse_yaml_lite(text: str) -> dict:
    """Tiny YAML parser handling the shapes that capsules + vault entries use:

    - `key: scalar` (with optional `# inline comment`)
    - `key: [a, b, c]` (inline list)
    - `key:` followed by multi-line `  - item` rows

    Does not handle nested objects (e.g., `author: {name, role}`).
    """
    result: Dict[str, Any] = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        # Strip inline comments — `# ` after whitespace
        val_no_comment = re.split(r"\s+#", val, maxsplit=1)[0].strip()
        if val_no_comment.startswith("[") and val_no_comment.endswith("]"):
            inner = val_no_comment[1:-1].strip()
            if inner:
                items = [s.strip().strip('"').strip("'") for s in inner.split(",")]
                result[key] = items
            else:
                result[key] = []
        elif not val_no_comment:
            # Multi-line list expected (or empty value)
            items: List[str] = []
            j = i + 1
            while j < len(lines):
                m2 = re.match(r"^\s*-\s+(.+?)(\s+#.*)?$", lines[j])
                if not m2:
                    break
                item_val = m2.group(1).strip().strip('"').strip("'")
                # Strip inline comment from item too
                item_val = re.split(r"\s+#", item_val, maxsplit=1)[0].strip()
                items.append(item_val)
                j += 1
            if items:
                result[key] = items
                i = j - 1
            else:
                result[key] = ""
        else:
            result[key] = val_no_comment.strip('"').strip("'")
        i += 1
    return result


def load_ledger_index(vault_root: Path) -> Dict[str, dict]:
    """Load `vault/00-index.jsonl` into a {uid: entry} map.

    Path patched 2026-05-08 by vela-v42 for v1.9.0 ledger/ → vault/ rename
    drift (was hardcoded ledger/ which no longer exists)."""
    index_path = vault_root / "vault" / "00-index.jsonl"
    result: Dict[str, dict] = {}
    if not index_path.exists():
        return result
    with index_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            uid = entry.get("uid")
            if uid:
                result[uid] = entry
    return result


def load_capsule_index(vault_root: Path) -> Dict[str, Tuple[str, Path]]:
    """Scan `.tropo/capsules/` for capsule files. Returns {uid: (title, path)}."""
    result: Dict[str, Tuple[str, Path]] = {}
    capsule_dir = vault_root / ".tropo" / "capsules"
    if not capsule_dir.exists():
        return result
    for f in capsule_dir.glob("*.capsule.md"):
        try:
            content = f.read_text()
            fm, _, _ = parse_frontmatter(content)
            if not fm:
                continue
            uid = fm.get("uid")
            if not uid:
                continue
            title = fm.get("name") or fm.get("title") or f.stem.replace(".capsule", "")
            # `name` is canonical for capsules; render as `<name>.capsule`
            if "name" in fm:
                title = f"{title}.capsule"
            result[uid] = (title, f)
        except Exception:
            continue
    return result


def lookup_uid(
    uid: str,
    ledger: Dict[str, dict],
    capsules: Dict[str, Tuple[str, Path]],
    source_file: Path,
    vault_root: Path,
) -> Optional[Tuple[str, str]]:
    """Returns (title, relative_path_from_source_file) or None."""
    # Graph-only navigation (Mike-vela 2026-05-09 reframe):
    # The Relations block is for HUMANS WALKING THE GRAPH. Only emit links to
    # other governed graph-nodes. Same-folder relative links (`<uid>.md`) —
    # source file lives at vault/files/<uid>.md, target lives at vault/files/<uid>.md,
    # so a same-folder filename reference is the canonical link. Works in any
    # markdown viewer when the file is opened directly from vault/files/.
    # Symlinks in 00-tropo-nav/ are for project browsing (different surface);
    # graph-walk happens by opening source files in vault/files/ directly.
    if uid in ledger:
        entry = ledger[uid]
        title = entry.get("title", uid)
        return (title, f"{uid}.md")
    # Capsule references (uid in capsules) intentionally NOT emitted as links —
    # they live outside vault/files/ and would clutter the graph-walk surface.
    return None


def render_link(uid: str, title: str, path: str, max_title_len: int = 70) -> str:
    """Render `[Title (uid)](path)` with title truncation for compactness."""
    if len(title) > max_title_len:
        title = title[: max_title_len - 3] + "..."
    return f"[{title} ({uid})]({path})"


def is_uid(value: str) -> bool:
    """8-char hex string."""
    return bool(UID_RE.match(value))


def build_inverse_member_of_index(ledger: Dict[str, dict]) -> Dict[str, List[str]]:
    """v1.15.2 Stream A: build {parent_uid: [child_uids]} from the ledger.

    Inverts every entry's member_of array so we can answer 'what points AT this'.
    Built once per script run; used by build_members_block.
    """
    inverse: Dict[str, List[str]] = {}
    for child_uid, entry in ledger.items():
        member_of = entry.get('member_of') or []
        if isinstance(member_of, str):
            member_of = [member_of]
        for parent_uid in member_of:
            if not isinstance(parent_uid, str):
                continue
            parent_uid = parent_uid.strip()
            if not is_uid(parent_uid):
                continue
            inverse.setdefault(parent_uid, []).append(child_uid)
    return inverse


def build_tropo_nav_index(vault_root: Path) -> Dict[str, str]:
    """v1.X (vela-v50 2026-05-23, captain-mode per Mike-V50):
    Build {uid: relative_path_within_00-tropo-nav} mapping by walking symlinks.

    00-tropo-nav/ is the human-navigable filesystem tree at Studio root with three
    top-level dirs (00-tropo-active/ + 00-tropo-all/ + 00-tropo-archived/) holding
    symlinks to vault/files/<uid>.md. Per Mike-V50 directive 2026-05-23: vault entries
    rendered in their body should surface their tropo-nav location alongside the
    governance-graph Vault Path so humans can navigate from the rendered surface to
    the filesystem location they actually browse.

    Preference order (first-wins): 00-tropo-active > 00-tropo-all > 00-tropo-archived
    per Mike-V50 Q1 lock 2026-05-23 ("show one; prefer active").

    Returns empty dict if 00-tropo-nav/ doesn't exist (graceful for Studios that
    don't use the human-navigable surface).
    """
    nav_root = vault_root / "00-tropo-nav"
    if not nav_root.is_dir():
        return {}

    index: Dict[str, str] = {}
    # Preference order — first-wins per Mike-V50 Q1 2026-05-23
    for top_dir in ("00-tropo-active", "00-tropo-all", "00-tropo-archived"):
        top_path = nav_root / top_dir
        if not top_path.is_dir():
            continue
        # Walk all files under this top-level dir
        # v1.51.0 amendment (vela-v51 2026-05-23): swapped from is_symlink() filter to
        # is_file() + filename-UID-parse. rehydrate.py swapped symlinks → hardlinks same
        # session per Mike-V51 UX report; hardlinks are regular files (not symlinks), so
        # the prior `if not entry.is_symlink(): continue` filter returned False for every
        # entry and the index came back empty (Tropo-Nav Path lines got omitted from every
        # nav-block — symmetric bug). UID comes from filename convention (<uid> — <title>.md)
        # not from resolve() of the symlink target. Discipline lesson: when changing a writer
        # (rehydrate.py), audit the readers (this function) in the same pass.
        for entry in top_path.rglob("*"):
            if not entry.is_file():
                continue  # skip directories
            # Extract UID from filename stem — convention: "<uid> — <title>.md" per rehydrate.py
            filename = entry.name
            if " — " not in filename:
                continue
            uid_part = filename.split(" — ", 1)[0]
            if not is_uid(uid_part):
                continue
            stem = uid_part
            if stem in index:
                continue  # first-wins per preference order
            # Record relative path from 00-tropo-nav/ (e.g., "00-tropo-active/hello-tropo/board.md")
            try:
                rel_path = entry.relative_to(nav_root)
            except ValueError:
                continue
            index[stem] = str(rel_path)
    return index


# --------------------------------------------------------------------------
# Navigation block (v1.X amendment 2026-05-14, vela-v45)
# --------------------------------------------------------------------------
# Mike-V45 2026-05-14: the substrate is for agents, but the rendered body is
# for HUMANS too. The Relations + Members blocks surface outbound + member-of
# inverse edges; they're load-bearing but they don't answer "what AM I and
# where do I live?" The Navigation block fills that gap with three lines at
# the top of every vault entry's body:
#   📍 Path     — breadcrumb walking up member_of edges to a subsystem hub
#   🔗 This file — own UID + type + state + status in copy-friendly form
#   📥 Cited by — inbound back-links across all UID-valued reference fields
# All readable-name-first, UIDs in code-fences for triple-click copy-paste.
# Sentinel-wrapped (HTML comments) for idempotent find-and-replace.
# --------------------------------------------------------------------------

# Frontmatter fields that carry UID-valued references (for the cited-by index)
CITED_BY_FIELDS: Tuple[str, ...] = (
    "member_of", "refs", "governed_by", "supersedes", "superseded_by",
    "aligned_with", "closes", "pattern_exemplar", "composes_into",
    "composes_with", "derived_from", "extends", "basis_spec", "foundation",
    "predecessor", "predecessor_release", "activation_root_uid",
    "input_brief_uid", "capabilities_touched", "subsystems_touched",
    "agent_root", "soul_uid", "boot_extension_uid", "status_card_uid",
    "charter_uid", "generation_log_archive_uid", "roadmap_alignment",
)

# Hub-priority types — these become natural breadcrumb roots
HUB_TYPES: Tuple[str, ...] = ("subsystem-hub", "project")


def build_cited_by_index(ledger: Dict[str, dict]) -> Dict[str, List[Tuple[str, str]]]:
    """Build {target_uid: [(citer_uid, field_name), ...]} across all UID-valued
    reference fields. Sister to build_inverse_member_of_index but broader.

    Used by build_navigation_block's 📥 Cited by section. One pass over the
    ledger; deduped at render-time (a citer pointing via multiple fields is
    surfaced once per field — Mike sees how each edge type is reached).
    """
    inverse: Dict[str, List[Tuple[str, str]]] = {}
    for citer_uid, entry in ledger.items():
        for field in CITED_BY_FIELDS:
            val = entry.get(field)
            if not val:
                continue
            if isinstance(val, str):
                val = [val]
            if not isinstance(val, list):
                continue
            for v in val:
                if not isinstance(v, str):
                    continue
                v = re.split(r"\s+#", v.strip(), maxsplit=1)[0].strip()
                if is_uid(v):
                    inverse.setdefault(v, []).append((citer_uid, field))
    return inverse


def walk_breadcrumb(
    uid: str,
    ledger: Dict[str, dict],
    max_depth: int = 5,
) -> List[Tuple[str, str]]:
    """Walk up parent edges to build a parent chain. Returns
    [(uid, title), ...] from root → immediate parent (root-first ordering for
    breadcrumb display).

    v1.14 schema split (Argus A80 2026-05-23): parent edges come from BOTH
    `member_of:` (true parent projects) AND `subsystem_hub:` (subsystem hub
    catalog membership). Both render in the breadcrumb; subsystem_hub: edges
    take priority for anchoring at a recognizable subsystem hub.

    Prefers parents whose own type is in HUB_TYPES (subsystem-hub / project) so
    the breadcrumb anchors at a recognizable structural hub when possible. Stops
    at first ancestor with no parent edges, on cycle detection, or at max_depth.
    """
    chain: List[Tuple[str, str]] = []
    current = uid
    seen = {current}
    for _ in range(max_depth):
        entry = ledger.get(current)
        if not entry:
            break
        # v1.14 schema split: collect parent UIDs from BOTH member_of AND subsystem_hub.
        # subsystem_hub edges listed first (hub-priority for breadcrumb anchoring).
        raw_parents = []
        for sh in (entry.get("subsystem_hub") or []):
            if sh not in raw_parents:
                raw_parents.append(sh)
        for m in (entry.get("member_of") or []):
            if m not in raw_parents:
                raw_parents.append(m)
        if isinstance(raw_parents, str):
            raw_parents = [raw_parents]
        valid_parents = []
        for p in raw_parents:
            if not isinstance(p, str):
                continue
            p = re.split(r"\s+#", p.strip(), maxsplit=1)[0].strip()
            if is_uid(p):
                valid_parents.append(p)
        if not valid_parents:
            break
        # Prefer hub-typed parents
        parent = None
        for p in valid_parents:
            ptype = ledger.get(p, {}).get("type", "")
            if ptype in HUB_TYPES:
                parent = p
                break
        if not parent:
            parent = valid_parents[0]
        if parent in seen:
            break  # cycle guard
        seen.add(parent)
        pe = ledger.get(parent, {})
        title = pe.get("title") or pe.get("name") or parent
        chain.append((parent, title))
        current = parent
    return list(reversed(chain))  # root-first for breadcrumb display


def _entry_display(uid: str, ledger: Dict[str, dict]) -> Tuple[str, str]:
    """Returns (display_title, type) for a UID, with readable-name fallback chain.

    Resolution: title → name → uid (final fallback). type defaults to '?' if
    not declared. Used by Children + Siblings + Cited-by rendering so all three
    surfaces use the same display logic (Mike-V45 readable-name-first).
    """
    e = ledger.get(uid, {}) or {}
    title = e.get("title") or e.get("name") or uid
    etype = e.get("type") or "?"
    return title, etype


def build_navigation_block(
    fm: dict,
    filepath: Path,
    ledger: Dict[str, dict],
    inverse_index: Dict[str, List[str]],
    cited_by_index: Dict[str, List[Tuple[str, str]]],
    vault_root: Path,
    tropo_nav_index: Optional[Dict[str, str]] = None,
    breadcrumb_depth: int = 5,
    children_cap: int = 8,
    siblings_cap_per_parent: int = 6,
    cited_by_cap: int = 5,
) -> Optional[str]:
    """Build the unified Navigation block emitted at top of body.

    v1.X.0 (vela-v45 2026-05-14, captain-mode per Mike-V45):
    Five-section human-navigation surface recreating filesystem-tree walkability
    on the composable graph. Per Mike-V45 directive: "every file has a parent
    (except L0) and most files have children. The way a human navigates their
    work is through a file system tree. We can see up, and down easily. I am
    trying HARD to recreate that with our graph, except we are way more powerful
    because we are composable."

    Sections (in order):
      📍 Path     — breadcrumb walking up member_of edges (filesystem `cd ..`)
      🔗 This file — own identity (UID + type + state + status) copy-friendly
      ↓ Children  — files that member_of THIS (filesystem `ls .`)
      ↔ Siblings  — peers sharing THIS file's parents, grouped per parent
                    (filesystem `ls ../` minus self — multi-parent → multi-group)
      📥 Cited by — non-member_of inbound references (graph-only bonus)

    All sections optional — rendered only when non-empty. Wrapped in HTML-comment
    sentinels for idempotent find-and-replace.

    Returns None if the file has no resolvable UID.
    """
    # UID resolution: prefer frontmatter `uid:` field; fall back to filename stem
    # (vault/files/<uid>.md convention) for legacy entries lacking the field.
    # v1.X.1 amendment 2026-05-15 (vela-v45): catches 14 status-card / pre-v1.21
    # entries that have the canonical filename pattern but missed the
    # uid-in-frontmatter convention. Renderer now produces Navigation block for
    # those entries instead of skipping them.
    own_uid = fm.get("uid")
    if not own_uid or not is_uid(own_uid):
        stem = filepath.stem
        if is_uid(stem):
            own_uid = stem
        else:
            return None

    own_title = fm.get("title") or fm.get("name") or own_uid
    own_type = fm.get("type") or "document"
    own_state = fm.get("state")
    own_status = fm.get("status")

    # v1.45.0 Stream 1: suppress nav-block on user-facing content types.
    # Per-file override via frontmatter `nav_block: suppress | render` (suppress
    # forces suppression on any type; render forces rendering on a normally-
    # suppressed type, useful for kb-article entries serving as canonical hub-docs).
    nav_block_override = fm.get("nav_block")
    if nav_block_override == "suppress":
        return None
    if nav_block_override != "render" and own_type in NAV_BLOCK_SUPPRESS_TYPES:
        return None

    lines: List[str] = ["<!-- nav-block:start -->"]

    # 📍 Vault Path — breadcrumb walking up member_of (governance graph)
    # Renamed from "Path" → "Vault Path" 2026-05-23 by vela-v50 per Mike-V50 feature request
    # to distinguish from new 🌳 Tropo-Nav Path (filesystem-mounted human-navigable surface).
    chain = walk_breadcrumb(own_uid, ledger, max_depth=breadcrumb_depth)
    if chain:
        crumbs: List[str] = []
        for puid, ptitle in chain:
            short = ptitle if len(ptitle) <= 40 else ptitle[:37] + "..."
            crumbs.append(f"[{short}]({puid}.md)")
        self_display = own_title if len(own_title) <= 60 else own_title[:57] + "..."
        crumbs.append(f"**{self_display}**")
        lines.append("**📍 Vault Path:** " + " → ".join(crumbs))

    # 🌳 Tropo-Nav Path — file's location in 00-tropo-nav/ filesystem tree
    # v1.X (vela-v50 2026-05-23, captain-mode per Mike-V50 feature request):
    # Surface the human-navigable filesystem location alongside the governance-graph
    # Vault Path. Preference order: active > all > archived (first-wins per
    # Mike-V50 Q1 lock). Omit line entirely when no 00-tropo-nav/ symlink exists
    # (per Mike-V50 Q2 lock: clean rendering for non-tropo-nav entries).
    # v1.X.1 refinement (vela-v50 2026-05-23 same-turn per Mike-V50 visual feedback):
    # (1) blank line between Vault Path + Tropo-Nav Path for visual separation;
    # (2) Tropo-Nav Path is a hyperlink (relative path from vault/files/<uid>.md)
    # so Mike can click + navigate to the file's filesystem location. Angle-bracket
    # link syntax handles paths-with-spaces cleanly across markdown renderers.
    if tropo_nav_index:
        nav_path = tropo_nav_index.get(own_uid)
        if nav_path:
            full_path = f"00-tropo-nav/{nav_path}"
            # v1.X.4 refinement (vela-v50 2026-05-23 same-turn per Mike-V50 visual test):
            # Two real bugs from v1.X.3 caught by Mike's screenshot test 2026-05-23:
            # (1) Paths with spaces broke CommonMark URL parser → entire markdown link
            #     rendered as raw text (display + brackets + href all visible literally)
            # (2) Two consecutive lines without blank line between rendered as one paragraph
            # Fix: URL-encode href (handles spaces + special chars + em-dashes cleanly)
            # while keeping display readable; add blank line between VS Code + chat lines.
            # Path-as-both pin spirit honored: display + href represent the same target
            # (encoded for href to satisfy CommonMark; readable for display to satisfy human).
            # Earlier rationale (v1.X.3):
            # - VS Code (primary; clicks from vault/files/<uid>.md) needs file-relative path
            # - Claude Code chat (Read-tool consumer) needs CWD-relative path per pin
            # - Both formats rendered as separate labeled lines; fallback = Vela `open <path>`
            vscode_link = f"../../{full_path}"   # file-relative from vault/files/<uid>.md
            chat_link = f"{vault_root.name}/{full_path}"   # CWD-relative; prefix = the OPERATED studio's dir name (L2-portable; consistent with how the tool resolves every file from vault_root — fixes relocation watch-list #1, Argus A97 self-heal 2026-06-05)
            # URL-encode href; keep slashes + dots + dashes + underscores readable
            vscode_href = urllib.parse.quote(vscode_link, safe='/.-_')
            chat_href = urllib.parse.quote(chat_link, safe='/.-_')
            if chain:
                lines.append("")  # blank line before Tropo-Nav for visual separation
            lines.append(f"**🌳 Tropo-Nav Path** (VS Code): [{vscode_link}]({vscode_href})")
            lines.append("")  # blank line between VS Code + chat lines (separate paragraphs)
            lines.append(f"**🌳 Tropo-Nav Path** (chat): [{chat_link}]({chat_href})")

    if chain or (tropo_nav_index and tropo_nav_index.get(own_uid)):
        lines.append("")

    # 🔗 This file — self identity
    parts: List[str] = [f"UID `{own_uid}`", f"type `{own_type}`"]
    if own_state:
        parts.append(f"state `{own_state}`")
    if own_status:
        parts.append(f"status `{own_status}`")
    lines.append("**🔗 This file** — " + " · ".join(parts))

    # ↓ Children — inverse member_of (filesystem ls .)
    # Group by type, cap per type for hub-style entries with hundreds of children
    children = inverse_index.get(own_uid) or []
    if children:
        # Group by type for typed-cap rendering (mirrors build_members_block §5 lock)
        by_type: Dict[str, List[Tuple[str, str]]] = {}
        for cuid in children:
            ctitle, ctype = _entry_display(cuid, ledger)
            by_type.setdefault(ctype, []).append((cuid, ctitle))
        total_children = sum(len(v) for v in by_type.values())
        lines.append("")
        lines.append(f"**↓ Children ({total_children}):**")
        for ctype in sorted(by_type.keys()):
            items = sorted(by_type[ctype], key=lambda x: x[1].lower())
            capped = items[:children_cap]
            overflow = len(items) - len(capped)
            label = f"{ctype} ({len(items)})" if len(items) > 1 else ctype
            link_parts: List[str] = []
            for cuid, ctitle in capped:
                short = ctitle if len(ctitle) <= 50 else ctitle[:47] + "..."
                link_parts.append(f"[{short}]({cuid}.md)")
            if overflow > 0:
                link_parts.append(f"+ {overflow} more")
            lines.append(f"  - **{label}:** " + " · ".join(link_parts))

    # ↔ Siblings — for each parent in member_of, list OTHER children of that
    # parent. Multi-parent → multiple sibling sets shown per parent.
    # (filesystem ls ../ minus self, scoped to each parent in the graph)
    raw_parents = fm.get("member_of") or []
    if isinstance(raw_parents, str):
        raw_parents = [raw_parents]
    valid_parents: List[str] = []
    seen_parents = set()
    for p in raw_parents:
        if not isinstance(p, str):
            continue
        p = re.split(r"\s+#", p.strip(), maxsplit=1)[0].strip()
        if is_uid(p) and p not in seen_parents:
            valid_parents.append(p)
            seen_parents.add(p)
    sibling_groups: List[Tuple[str, str, List[Tuple[str, str, str]]]] = []
    for puid in valid_parents:
        peers = inverse_index.get(puid) or []
        peers_filtered = [u for u in peers if u != own_uid]
        if not peers_filtered:
            continue
        ptitle, _ptype = _entry_display(puid, ledger)
        peer_displays: List[Tuple[str, str, str]] = []
        for u in peers_filtered:
            utitle, utype = _entry_display(u, ledger)
            peer_displays.append((u, utitle, utype))
        # Sort by title for stable display
        peer_displays.sort(key=lambda x: x[1].lower())
        sibling_groups.append((puid, ptitle, peer_displays))
    if sibling_groups:
        total_sibs = sum(len(g[2]) for g in sibling_groups)
        lines.append("")
        lines.append(f"**↔ Siblings ({total_sibs}):**")
        for puid, ptitle, peers in sibling_groups:
            pshort = ptitle if len(ptitle) <= 40 else ptitle[:37] + "..."
            capped = peers[:siblings_cap_per_parent]
            overflow = len(peers) - len(capped)
            link_parts = []
            for u, utitle, _utype in capped:
                short = utitle if len(utitle) <= 50 else utitle[:47] + "..."
                link_parts.append(f"[{short}]({u}.md)")
            if overflow > 0:
                link_parts.append(f"+ {overflow} more")
            lines.append(
                f"  - **under [{pshort}]({puid}.md):** " + " · ".join(link_parts)
            )

    # 📥 Cited by — non-member_of inbound references, collapsed by citer
    raw_citers = cited_by_index.get(own_uid) or []
    # Exclude pure-member_of-only citers (those are already shown as Children
    # above — surfacing them again as Cited by is duplicate noise). Keep citers
    # that reference via OTHER fields (refs, governed_by, supersedes, etc.) OR
    # via member_of plus another field.
    citer_fields: Dict[str, List[str]] = {}
    citer_order: List[str] = []
    for cuid, field in raw_citers:
        if cuid not in citer_fields:
            citer_fields[cuid] = []
            citer_order.append(cuid)
        if field not in citer_fields[cuid]:
            citer_fields[cuid].append(field)
    # Filter: drop citers whose only edge is member_of (already a Child above)
    cited_filtered: List[str] = []
    for cuid in citer_order:
        fields = citer_fields[cuid]
        if fields == ["member_of"]:
            continue  # already surfaced as Child
        cited_filtered.append(cuid)
    if cited_filtered:
        total = len(cited_filtered)
        capped = cited_filtered[:cited_by_cap]
        overflow = total - len(capped)
        lines.append("")
        lines.append(f"**📥 Cited by ({total}):**")
        for cuid in capped:
            ctitle, ctype = _entry_display(cuid, ledger)
            short = ctitle if len(ctitle) <= 65 else ctitle[:62] + "..."
            via = ", ".join(f"`{f}`" for f in citer_fields[cuid])
            lines.append(f"- [{short}]({cuid}.md) — `{cuid}` (type `{ctype}`, via {via})")
        if overflow > 0:
            lines.append(
                f"- *+ {overflow} more — full back-link sweep via "
                f"`grep -l \"{own_uid}\" vault/files/*.md`*"
            )

    lines.append("<!-- nav-block:end -->")
    return "\n".join(lines)


_NAV_BLOCK_RE = re.compile(
    r"<!-- nav-block:start -->.*?<!-- nav-block:end -->\n*",
    re.DOTALL,
)


def find_navigation_block(body: str) -> Optional[Tuple[int, int]]:
    """Detect existing sentinel-wrapped Navigation block. Returns (start, end)
    or None. Sentinels make this trivially idempotent."""
    m = _NAV_BLOCK_RE.search(body)
    if m:
        return m.start(), m.end()
    return None


def build_members_block(
    uid: str,
    inverse_index: Dict[str, List[str]],
    ledger: Dict[str, dict],
    cap_per_type: int = 5,
) -> Optional[str]:
    """v1.15.2 Stream A: render Members section with typed-cap format per Vela 4c2456b4 §5.

    Format: group by type, cap at `cap_per_type` per type, "+ N more" overflow indicator.
    Returns None if no children. Renders as a `**Members**` heading + markdown table.
    """
    children = inverse_index.get(uid) or []
    if not children:
        return None

    by_type: Dict[str, List[Tuple[str, str]]] = {}
    for child_uid in children:
        entry = ledger.get(child_uid)
        if not entry:
            continue
        ctype = entry.get('type') or 'document'
        title = entry.get('title') or child_uid
        by_type.setdefault(ctype, []).append((child_uid, title))

    if not by_type:
        return None

    type_order = sorted(by_type.keys())
    rows: List[Tuple[str, str]] = []
    for ctype in type_order:
        items = sorted(by_type[ctype], key=lambda x: x[1].lower())
        capped = items[:cap_per_type]
        overflow = len(items) - len(capped)
        label = f"{ctype} ({len(items)})" if len(items) > 1 else ctype
        link_parts: List[str] = []
        for cuid, ctitle in capped:
            display_title = ctitle if len(ctitle) <= 50 else ctitle[:47] + "..."
            link_parts.append(f"[{display_title}]({cuid}.md)")
        if overflow > 0:
            link_parts.append(f"+ {overflow} more")
        rows.append((label, " · ".join(link_parts)))

    lines: List[str] = ["**Members**", "", "| Type | Children |", "|---|---|"]
    for label, items in rows:
        lines.append(f"| {label} | {items} |")
    return "\n".join(lines)


def build_relations_block(
    fm: dict,
    source_file: Path,
    ledger: Dict[str, dict],
    capsules: Dict[str, Tuple[str, Path]],
    vault_root: Path,
) -> Optional[str]:
    """Build the **Relations** markdown table block from frontmatter.

    Returns None if no navigation-relevant fields are present.

    Format: a `**Relations**` heading line followed by a markdown table with
    Relation / Target columns. One row per item. Renders reliably in every
    markdown viewer including Substack, GitHub, VS Code, Obsidian.

    Pattern history:
    - 2026-04-25 attempt 1: `> **Relations**` blockquote, middle-dot inline
      separators — rendered cramped in Mike's viewer (mike-feedback-1).
    - 2026-04-25 attempt 2: blockquote, row-per-item with `\\n` line breaks —
      Mike's viewer collapsed the lines into a single flowing paragraph
      (line breaks not preserved within blockquote in his renderer)
      (mike-feedback-2).
    - 2026-04-25 attempt 3: markdown table — universal renderer support;
      this format.
    """
    rows: List[Tuple[str, str]] = []

    for label, fields in FIELD_GROUPS:
        for field in fields:
            if field not in fm:
                continue
            value = fm[field]
            if isinstance(value, str):
                value = [value]
            elif not isinstance(value, list):
                continue
            for v in value:
                if not isinstance(v, str):
                    continue
                v = v.strip()
                v = re.split(r"\s+#", v, maxsplit=1)[0].strip()
                if not v:
                    continue
                if is_uid(v):
                    look = lookup_uid(v, ledger, capsules, source_file, vault_root)
                    if look:
                        title, path = look
                        item = render_link(v, title, path)
                        rows.append((label, item))
                    # else: graph-only navigation (Mike-vela 2026-05-09 reframe) —
                    # drop the row entirely; non-vault-graph references don't render
                else:
                    # Non-UID values (e.g., schema_version, plain strings) — skip;
                    # the Relations block is for graph-node navigation only
                    pass

    if not rows:
        return None

    lines: List[str] = ["**Relations**", "", "| Relation | Target |", "|---|---|"]
    for label, item in rows:
        lines.append(f"| {label} | {item} |")

    return "\n".join(lines)


def find_relations_block(body: str) -> Optional[Tuple[int, int]]:
    """Detect existing Relations/Members navigation block. Returns (start, end) or None.

    Handles two legacy formats + the current format:
    - Current: `**Relations**` heading + blank line + markdown table
    - Legacy 2: `> **Relations**` blockquote with row-per-item `> · Label: ...` lines
    - Legacy 1: `> **Relations**` blockquote with middle-dot inline separators
    - Standalone: `**Members**` table with no preceding Relations block

    After finding the Relations anchor, also consumes any trailing `**Members**`
    blocks (including stacked duplicates). This makes the replacement idempotent —
    the entire Relations + Members unit is replaced as one, preventing the
    stacked-Members bug where each rebuild appended a new Members block without
    removing the previous one (Argus A58 / v1.22.0.3 fix).
    """
    start = None
    end = None

    # Current format: **Relations** heading + table
    table_pattern = re.compile(
        r"^\*\*Relations\*\*[^\n]*\n+\| Relation \| Target \|\n\|[-:|\s]+\|\n(?:\|[^\n]*\|\n)+",
        re.MULTILINE,
    )
    m = table_pattern.search(body)
    if m:
        start, end = m.start(), m.end()
    else:
        # Legacy blockquote format
        bq_pattern = re.compile(r"^> \*\*Relations\*\*[^\n]*\n(?:^>[^\n]*\n)*", re.MULTILINE)
        m = bq_pattern.search(body)
        if m:
            start, end = m.start(), m.end()

    if start is None:
        # No Relations block — check for standalone Members block (files with
        # children but no outbound navigation fields)
        members_only = re.compile(
            r"^\*\*Members\*\*[^\n]*\n+\| Type \| Children \|\n\|[-:|\s]+\|\n(?:\|[^\n]*\|\n)*",
            re.MULTILINE,
        )
        m = members_only.search(body)
        if m:
            start, end = m.start(), m.end()
        else:
            return None

    # Consume any trailing Members blocks (handles normal append + stacked duplicates)
    members_pattern = re.compile(
        r"^\*\*Members\*\*[^\n]*\n+\| Type \| Children \|\n\|[-:|\s]+\|\n(?:\|[^\n]*\|\n)*",
        re.MULTILINE,
    )
    while True:
        remaining = body[end:]
        blank_match = re.match(r"^\n+", remaining)
        offset = blank_match.end() if blank_match else 0
        mm = members_pattern.match(remaining[offset:])
        if mm:
            end = end + offset + mm.end()
        else:
            break

    return start, end


_STALE_MEMBERS_RE = re.compile(
    r"\n*\*\*Members\*\*[^\n]*\n+\| Type \| Children \|\n\|[-:|\s]+\|\n(?:\|[^\n]*\|\n)*",
    re.MULTILINE,
)


def _strip_stale_members(text: str) -> str:
    """Remove any stray **Members** tables from a text segment.

    Called on the document body AFTER the canonical block has been placed, so that
    Members blocks scattered by previous non-idempotent runs are cleaned up even
    when they are not immediately adjacent to the Relations block.
    """
    return _STALE_MEMBERS_RE.sub("", text)


def insert_or_update_block(body: str, block: str) -> Tuple[str, str]:
    """Insert the unit (Navigation + Relations + Members) after H1 or update.

    Returns (new_body, action) where action is "inserted" | "updated" | "no-h1".

    v1.X amendment (vela-v45 2026-05-14): also strips any existing Navigation
    block (sentinel-wrapped) before inserting/updating, so the unit is replaced
    as one regardless of which sub-block(s) the file currently has. Order of
    operations:
      1. Strip existing Navigation block (idempotent via sentinels)
      2. Find existing Relations block (handles legacy formats + trailing Members)
      3. If Relations found: replace at that position. If not: insert after H1.
      4. Cleanup stale Members tables that survived detection.
    """
    # Step 1 — strip existing Navigation block (sentinel-wrapped, anywhere in body)
    nav_existing = find_navigation_block(body)
    if nav_existing is not None:
        body = body[:nav_existing[0]] + body[nav_existing[1]:]
        # Collapse any extra blank lines left behind
        body = re.sub(r"\n{3,}", "\n\n", body)

    # Step 2 — find existing Relations/Members block (post-Navigation-strip)
    existing = find_relations_block(body)
    if existing is not None:
        start, end = existing
        rest_after = body[end:]
        rest_after = rest_after.lstrip("\n")
        rest_after = _strip_stale_members(rest_after)
        new_body = body[:start] + block + "\n\n" + rest_after
        return new_body, "updated"

    # Step 3 — no Relations block; insert after H1
    h1_match = re.search(r"^# .+$", body, re.MULTILINE)
    if not h1_match:
        return body, "no-h1"

    insert_pos = h1_match.end()
    rest = body[insert_pos:]
    rest = rest.lstrip("\n")
    rest = _strip_stale_members(rest)

    new_body = (
        body[:insert_pos]
        + "\n\n"
        + block
        + "\n\n"
        + rest
    )
    return new_body, "inserted"


def process_file(
    filepath: Path,
    vault_root: Path,
    ledger: Dict[str, dict],
    capsules: Dict[str, Tuple[str, Path]],
    inverse_index: Dict[str, List[str]],
    cited_by_index: Dict[str, List[Tuple[str, str]]],
    write: bool,
    tropo_nav_index: Optional[Dict[str, str]] = None,
) -> str:
    """Process a single file. Returns a status string for the report.

    v1.15.2 Stream A: also renders Members section (inverse member_of) when the file's
    own UID has children. Relations + Members blocks are concatenated into one unit.
    v1.X amendment (vela-v45 2026-05-14): Navigation block (breadcrumb + self + cited-by)
    prepended for human walkability — Mike-V45 directive.
    """
    try:
        content = filepath.read_text()
    except Exception as e:
        return f"  [error] {filepath.name}: {e}"

    fm, fm_raw, body = parse_frontmatter(content)
    if not fm:
        return f"  [skip] {filepath.name}: no frontmatter"

    nav_block = build_navigation_block(
        fm, filepath, ledger, inverse_index, cited_by_index, vault_root,
        tropo_nav_index=tropo_nav_index,
    )
    relations_block = build_relations_block(fm, filepath, ledger, capsules, vault_root)

    # v1.X (vela-v45 2026-05-14): Members table is collapsed into Navigation block's
    # Children section per Mike-V45 unified-surface directive. The separate Members
    # block stops rendering. Any pre-existing **Members** tables in file bodies get
    # stripped by _strip_stale_members during insert_or_update_block — automatic
    # migration on next sweep.
    members_block = None

    if nav_block is None and relations_block is None:
        return f"  [skip] {filepath.name}: no Navigation + no Relations"

    parts: List[str] = []
    if nav_block:
        parts.append(nav_block)
    if relations_block:
        parts.append(relations_block)
    block = "\n\n".join(parts)

    if write:
        new_body, action = insert_or_update_block(body, block)
        if action == "no-h1":
            return f"  [skip] {filepath.name}: no H1 title found in body"
        new_content = fm_raw + new_body
        if new_content != content:
            filepath.write_text(new_content)
            tags: List[str] = []
            if nav_block:
                tags.append("Navigation")
            if relations_block:
                tags.append(f"Relations ({len([f for f in NAVIGATION_FIELDS if f in fm])} fields)")
            if members_block:
                tags.append("Members")
            return f"  [{action}] {filepath.name}: {' + '.join(tags)}"
        return f"  [unchanged] {filepath.name}"

    sys.stdout.write(f"\n--- {filepath.name} ---\n")
    sys.stdout.write(block + "\n")
    tags = []
    if nav_block:
        tags.append("Navigation")
    if relations_block:
        tags.append("Relations")
    if members_block:
        tags.append("Members")
    return f"  [dry-run] {filepath.name}: would surface {' + '.join(tags)}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Relations Header block from a file's frontmatter."
    )
    parser.add_argument(
        "target",
        nargs="+",
        help="File or directory paths. Directories are non-recursively scanned for *.md.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Modify files in place (default: dry-run to stdout).",
    )
    parser.add_argument(
        "--vault-root",
        help="Override vault-root detection (default: walk up for settings/env.md).",
    )
    args = parser.parse_args()

    first = Path(args.target[0]).resolve()
    if args.vault_root:
        vault_root = Path(args.vault_root).resolve()
    else:
        vault_root = find_vault_root(first)
    print(f"Vault root: {vault_root}", file=sys.stderr)

    print("Loading vault index...", file=sys.stderr)
    ledger = load_ledger_index(vault_root)
    print(f"  {len(ledger)} vault entries", file=sys.stderr)

    print("Loading capsule index...", file=sys.stderr)
    capsules = load_capsule_index(vault_root)
    print(f"  {len(capsules)} capsules", file=sys.stderr)

    print("Building inverse member_of index (v1.15.2 Members section)...", file=sys.stderr)
    inverse_index = build_inverse_member_of_index(ledger)
    print(f"  {len(inverse_index)} parents have children", file=sys.stderr)

    print("Building cited-by index (v1.X Navigation block, vela-v45 2026-05-14)...", file=sys.stderr)
    cited_by_index = build_cited_by_index(ledger)
    print(f"  {len(cited_by_index)} entries have inbound back-links", file=sys.stderr)

    print("Building tropo-nav index (v1.X Navigation block enhancement, vela-v50 2026-05-23)...", file=sys.stderr)
    tropo_nav_index = build_tropo_nav_index(vault_root)
    print(f"  {len(tropo_nav_index)} entries have 00-tropo-nav/ locations", file=sys.stderr)

    files: List[Path] = []
    for target in args.target:
        p = Path(target).resolve()
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.glob("*.md")))
        else:
            print(f"Warning: {target} not found", file=sys.stderr)

    if not files:
        print("No files to process.", file=sys.stderr)
        return 1

    print(f"\nProcessing {len(files)} files (write={args.write})...\n", file=sys.stderr)
    for f in files:
        result = process_file(
            f, vault_root, ledger, capsules, inverse_index, cited_by_index, args.write,
            tropo_nav_index=tropo_nav_index,
        )
        print(result, file=sys.stderr)

    print("\nDone.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
