#!/usr/bin/env python3
"""
---
uid: b8e4f1a3
title: generate-relations-header — Tool
name: generate-relations-header
type: tool
status: active
owner: argus
domain: Render the single Vault-Path breadcrumb line (File Anatomy v2, 4506b6d4) — and strip the retired nav-block + Relations/Members renders from governed bodies.
spawnable_by:
- all-executives
transport: cli
cli_command: python3 vault/tools/tropo-generate-relations-header.py [--write] [--vault-root PATH] <target>...
script_path: vault/tools/tropo-generate-relations-header.py
implementation_kind: python-script
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
governance_category: lifecycle
description: 'File Anatomy v2 renderer (design note 4506b6d4, Mike-ruled 2026-07-23): a governed file carries frontmatter truth + ONE breadcrumb line + content. This tool renders the sentinel-wrapped Vault-Path breadcrumb (bottoms-up member_of/subsystem_hub walk, one hub-anchored chain, relative uid links) and STRIPS the retired surfaces its predecessor rendered: the multi-section nav-block (Tropo-Nav paths, This-file, Children, Siblings, Cited-by) and the body Relations/Members tables that triple-stated frontmatter edges. Predecessor pattern history: Relations table Argus A34 + Mike 2026-04-25; Members A53 v1.15.2; five-section nav-block Vela V45/V50. Retired per 4506b6d4 §Removal plan #1. Still Step 4/5 of rebuild-vault.py. Exports preserved for external callers: strip_nav_block()/_NAV_BLOCK_RE (git clean filter tropo-navblock-strip.py + tests), find_relations_block() (tropo-rebuild-index.py mention-stripping).'
domain_tags:
- breadcrumb-rendering
- file-anatomy-v2
- nav-block-retired
- navigation-surface
- body-frontmatter-sync
trigger_description: Reach for this to refresh a vault entry's Vault-Path breadcrumb line after changing its member_of, or run rebuild-vault.py to refresh breadcrumbs across the whole vault. Also the sweep tool that removes retired nav-blocks + Relations/Members tables from file bodies (File Anatomy v2, 4506b6d4). Run --write to modify in place; without --write for dry-run preview.
created: 2026-05-09
created_by: argus-a53
modified: 2026-07-23
modified_by: metis-g92
governed_by: d5e1b4a3
capsule_version: '2.5'
schema_version: 2
extraction_scope: ship
member_of:
- c2e8b4f6
tags:
- tool
- cli
- breadcrumb-rendering
- file-anatomy-v2
- kernel-tier
subsystem_hub:
- dbc1cbbf
---
"""

"""
generate-relations-header.py — File Anatomy v2 breadcrumb renderer + legacy-render sweep.

THE ANATOMY (design note 4506b6d4, Mike-ruled at the whiteboard 2026-07-23):
a governed file carries (1) frontmatter — the truth, all edges live there and only
there in written form; (2) ONE breadcrumb line — orientation for a human landing
cold in the raw file; (3) content. Nothing else derived. Navigation is a surface
(the L2 cockpit, the 00-tropo-nav tree, the index), not substrate embedded in files.

WHAT THIS RENDERS — the sentinel-wrapped breadcrumb, and nothing else:

    <!-- nav-block:start -->
    **📍 Vault Path:** [parent](uid.md) → [child](uid.md) → **This file's title**
    <!-- nav-block:end -->

  - Computed BOTTOMS-UP: walk member_of/subsystem_hub edges upward from the file
    (Mike's framing — a file can be member_of multiple nodes, so multiple upward
    chains exist); displayed top-down for reading.
  - Multi-parent policy: ONE chain shown, hub-preferring (subsystem-hub/project
    anchors first), per the Mike-V50 "show one; prefer active" precedent. The
    un-shown parents are not hidden — they are all in the frontmatter above.
  - Relative uid links only ([title](uid.md), same-folder). No absolute URLs, no
    server names — resolves identically in Chrome markdown viewers, VS Code,
    GitHub, and the L2 app. A static file cannot know where a server lives.
  - Sentinel-wrapped so the existing git clean filter (tropo-navblock-strip.py,
    dev-spec 6ec30708 / I5 dd16c90c) keeps committed bodies free of ALL derived
    content, breadcrumb included. Derived things stay strippable.

WHAT THIS STRIPS (the retired surfaces, removed on every --write pass):
  - The legacy five-section nav-block (Vault Path + Tropo-Nav paths + This-file +
    Children + Siblings + Cited-by) — replaced by the breadcrumb-only block.
  - The body **Relations** table + **Members** tables — retired outright; they
    triple-stated edges the frontmatter already carries (measured 2026-07-23:
    89% of work files, 431KB of duplication; nav-blocks 5.7MB / 14.9% of vault).
  Files whose new render is EMPTY (suppressed types, roots with no parent chain)
  still get their legacy blocks stripped — the strip is unconditional.

EXPORTS PRESERVED FOR EXTERNAL CALLERS (do not rename/remove):
  - strip_nav_block() / _NAV_BLOCK_RE — imported by the git clean filter
    (vault/tools/tropo-navblock-strip.py) + its test suite
    (vault/tools/tests/test_nav_blocks_out_6ec30708.py). The regex pattern text
    is pinned byte-identical by those tests.
  - find_relations_block() — imported by tropo-rebuild-index.py to drop legacy
    Relations/Members renders from mention-derivation. Still needed for archived
    bodies that predate the sweep.
  - Module import is side-effect-free (all execution behind __main__), verified
    by the strip tool's lazy-import contract.

Authors:
- argus-a34 2026-04-25 — initial Relations renderer (Stream 3 D3.2 of v1.4)
- vela-v42 2026-05-09 — v1.9.x rename drift patch + bulk apply across 1064 files
- argus-a53 2026-05-09 — v1.15.2 Members section; kernel-tier graduation
- vela-v45/v50 2026-05 — five-section nav-block + Tropo-Nav path lines
- talos-t25 2026-07-07 — line-anchored sentinel regex self-heal (6ec30708)
- metis-g92 2026-07-23 — File Anatomy v2 retool: breadcrumb-only render, legacy
  Relations/Members strip, per design note 4506b6d4 (Mike-ruled). Mike-directed
  lane-crossing: renderer retool taken by Metis with Argus/Talos queues full.

Usage
-----
Dry-run (emit block to stdout):
    python3 vault/tools/tropo-generate-relations-header.py path/to/file.md

In-place render + strip:
    python3 vault/tools/tropo-generate-relations-header.py --write path/to/file.md

Batch (process every .md file in a directory, non-recursive):
    python3 vault/tools/tropo-generate-relations-header.py --write vault/files/

Limitations
-----------
- Naive YAML parser (scalars, inline lists, multi-line `- item` lists). No nested
  objects/anchors/multiline strings.
- Single-H1 assumption — the breadcrumb inserts after the first `# ` line. Files
  with no H1 get strip-only treatment (legacy blocks removed, no breadcrumb).
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib import index_surfaces

# Navigation-block suppression — types where even the breadcrumb is more friction
# than help at first-encounter (operator-target user-facing content; V47 R3
# cold-boot "P0 — operator FAQ nav-block-at-head" finding). Per-file override via
# frontmatter `nav_block: suppress | render`.
NAV_BLOCK_SUPPRESS_TYPES: frozenset = frozenset({"kb-article"})

UID_RE = re.compile(r"^[0-9a-fA-F]{8}$")

# Hub-priority types — these become natural breadcrumb anchors
HUB_TYPES: Tuple[str, ...] = ("subsystem-hub", "project")


def is_uid(value: str) -> bool:
    """8-char hex string."""
    return bool(UID_RE.match(value))


def find_vault_root(start: Path) -> Path:
    """Walk up from `start` to find the studio root.

    Anchor priority (v1.9.0+ alignment with rehydrate.py + Tier 1 v1.1):
        1. `.tropo/boot-config.md` (current standard)
        2. `settings/env.md` (legacy; retained for older studios)
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
    """Load the ADR-047 current+archive union into a {uid: entry} map.

    Breadcrumb title resolution is history-aware even though default retrieval
    is current-only."""
    return {
        str(entry["uid"]): entry
        for entry in index_surfaces.load_index_records(vault_root, include_archive=True)
        if entry.get("uid")
    }


def walk_breadcrumb(
    uid: str,
    ledger: Dict[str, dict],
    max_depth: int = 5,
) -> List[Tuple[str, str]]:
    """Walk up parent edges to build a parent chain. Returns
    [(uid, title), ...] from root → immediate parent (root-first ordering for
    breadcrumb display).

    Computed BOTTOMS-UP from the file (a file can be member_of multiple nodes —
    multiple upward chains exist; this walk picks ONE per the policy below),
    displayed top-down. v1.14 schema split (Argus A80): parent edges come from
    BOTH `member_of:` (true parent projects) AND `subsystem_hub:` (subsystem hub
    catalog membership); subsystem_hub edges take priority for anchoring.

    Multi-parent policy (4506b6d4 §Anatomy, per the Mike-V50 "show one; prefer
    active" precedent): prefer parents whose own type is in HUB_TYPES
    (subsystem-hub / project) so the chain anchors at a recognizable structural
    hub; else first-listed wins. Stops at first ancestor with no parent edges,
    on cycle detection, or at max_depth. The parents not shown are all present
    in the file's own frontmatter — the breadcrumb is orientation, not the record.
    """
    chain: List[Tuple[str, str]] = []
    current = uid
    seen = {current}
    for _ in range(max_depth):
        entry = ledger.get(current)
        if not entry:
            break
        # Collect parent UIDs from BOTH subsystem_hub AND member_of (hub edges first).
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


def build_breadcrumb_block(
    fm: dict,
    filepath: Path,
    ledger: Dict[str, dict],
    breadcrumb_depth: int = 5,
) -> Optional[str]:
    """Build the File Anatomy v2 block: the sentinel-wrapped Vault-Path
    breadcrumb line, and nothing else.

    Returns None when there is nothing to render: no resolvable UID, a
    suppressed type (unless overridden), or an empty parent chain (an L0 root
    knows where it is). Callers still strip legacy blocks in that case — the
    strip is unconditional; only the render is conditional.
    """
    # UID resolution: prefer frontmatter `uid:`; fall back to filename stem
    # (vault/files/<uid>.md convention) for legacy entries lacking the field.
    own_uid = fm.get("uid")
    if not own_uid or not is_uid(own_uid):
        stem = filepath.stem
        if is_uid(stem):
            own_uid = stem
        else:
            return None

    own_title = fm.get("title") or fm.get("name") or own_uid
    own_type = fm.get("type") or "document"

    # Suppression: per-file override via `nav_block: suppress | render`.
    nav_block_override = fm.get("nav_block")
    if nav_block_override == "suppress":
        return None
    if nav_block_override != "render" and own_type in NAV_BLOCK_SUPPRESS_TYPES:
        return None

    chain = walk_breadcrumb(own_uid, ledger, max_depth=breadcrumb_depth)
    if not chain:
        return None

    crumbs: List[str] = []
    for puid, ptitle in chain:
        short = ptitle if len(ptitle) <= 40 else ptitle[:37] + "..."
        crumbs.append(f"[{short}]({puid}.md)")
    self_display = own_title if len(own_title) <= 60 else own_title[:57] + "..."
    crumbs.append(f"**{self_display}**")

    return "\n".join([
        "<!-- nav-block:start -->",
        "**📍 Vault Path:** " + " → ".join(crumbs),
        "<!-- nav-block:end -->",
    ])


# v1.X self-heal (Talos T25, 6ec30708 build, 2026-07-07): both sentinels are
# anchored to the START OF A LINE (`^` + re.MULTILINE), not bare substring matches
# — an unanchored pattern false-matched a walk-brief whose PROSE quotes both
# sentinel strings inline (vault/files/69ea3f38.md), corrupting authored text.
# Every REAL rendered block has each sentinel as a complete line by itself, so
# line-anchoring is a byte-for-byte no-op on genuine blocks and only closes the
# false-match gap. PINNED: the pattern text is verified byte-identical by
# tests/test_nav_blocks_out_6ec30708.py; the git clean filter imports this exact
# object. Do not fork or restyle it.
# The retired-render strip primitives now live in lib/governed_body.py so the
# receipt canonicalizer can import the SAME behaviour instead of carrying a
# second regex that drifts from this one (d220d43b D1). Re-exported here
# because nine call sites across the studio import them from this module.
from lib.governed_body import (  # noqa: E402,F401
    _NAV_BLOCK_RE,
    _STALE_MEMBERS_RE,
    _strip_stale_members,
    find_navigation_block,
    find_relations_block,
    strip_legacy_renders,
    strip_nav_block,
)



def insert_breadcrumb(body: str, block: str) -> Tuple[str, str]:
    """Insert the breadcrumb block after the H1 title.

    Returns (new_body, action) where action is "inserted" | "no-h1".
    Assumes legacy renders are already stripped from `body`.
    """
    h1_match = re.search(r"^# .+$", body, re.MULTILINE)
    if not h1_match:
        return body, "no-h1"
    insert_pos = h1_match.end()
    rest = body[insert_pos:].lstrip("\n")
    new_body = body[:insert_pos] + "\n\n" + block + "\n\n" + rest
    return new_body, "inserted"


def process_file(
    filepath: Path,
    vault_root: Path,
    ledger: Dict[str, dict],
    write: bool,
) -> str:
    """Process a single file: strip retired renders, insert the breadcrumb.

    The strip is UNCONDITIONAL (legacy blocks are removed even when nothing new
    renders — a suppressed type or a chainless root still gets cleaned); the
    render is conditional. Returns a status string for the report.
    """
    try:
        content = filepath.read_text()
    except Exception as e:
        return f"  [error] {filepath.name}: {e}"

    fm, fm_raw, body = parse_frontmatter(content)
    if not fm:
        return f"  [skip] {filepath.name}: no frontmatter"

    block = build_breadcrumb_block(fm, filepath, ledger)

    new_body = strip_legacy_renders(body)
    action = "stripped"
    if block is not None:
        new_body, insert_action = insert_breadcrumb(new_body, block)
        if insert_action == "inserted":
            action = "rendered"
        # no-h1 → strip-only result stands; breadcrumb needs an anchor.

    if write:
        new_content = fm_raw + new_body
        if new_content != content:
            filepath.write_text(new_content)
            return f"  [{action}] {filepath.name}"
        return f"  [unchanged] {filepath.name}"

    if block is not None:
        sys.stdout.write(f"\n--- {filepath.name} ---\n")
        sys.stdout.write(block + "\n")
    changed = (fm_raw + new_body) != content
    return f"  [dry-run] {filepath.name}: would be {action if changed else 'unchanged'}"


def cutover_pinned_evidence_paths(vault_root: Path) -> set:
    """Resolved paths of the Event Ledger v2 cutover-marker's pinned evidence files.

    These files are FROZEN: the marker (.tropo/event-streams-v2.enabled) binds their
    exact git-bound SHA-256, and load_cutover_marker() fail-closes every v2 emit if a
    pinned file drifts. Rendered navigation is index-derived and regenerable —
    rewriting pinned evidence changes the committed bytes and breaks the marker
    (the crew-wide emit outage of 2026-07-18). So this tool must NEVER rewrite
    pinned evidence. Fail-open: if the marker is absent/unreadable this returns an
    empty set (pre-cutover studios render normally).
    """
    marker = vault_root / ".tropo" / "event-streams-v2.enabled"
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    paths = set()
    for key in ("dev_spec_uid", "test_spec_uid", "audit_uid"):
        uid = data.get(key)
        if isinstance(uid, str) and uid:
            paths.add((vault_root / "vault" / "files" / f"{uid}.md").resolve())
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render the Vault-Path breadcrumb (File Anatomy v2) + strip retired nav renders."
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
        help="Override vault-root detection (default: walk up for .tropo/boot-config.md).",
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

    frozen = cutover_pinned_evidence_paths(vault_root)
    if frozen:
        skipped = [f for f in files if f.resolve() in frozen]
        if skipped:
            files = [f for f in files if f.resolve() not in frozen]
            for f in skipped:
                print(
                    f"SKIP (cutover-pinned evidence, frozen by .tropo/event-streams-v2.enabled): {f.name}",
                    file=sys.stderr,
                )

    print(f"\nProcessing {len(files)} files (write={args.write})...\n", file=sys.stderr)
    counts: Dict[str, int] = {}
    for f in files:
        result = process_file(f, vault_root, ledger, args.write)
        tag = result.strip().split("]")[0].lstrip("[").strip(" [")
        counts[tag] = counts.get(tag, 0) + 1
        print(result, file=sys.stderr)

    summary = " · ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    print(f"\nDone. {summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
