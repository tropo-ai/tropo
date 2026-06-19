#!/usr/bin/env python3
"""
---
uid: f4b8a6e2
title: rebuild-index — Tool
name: rebuild-index
type: tool
status: active
owner: argus
domain: Fast index + project-tree rebuild — vault/00-index.jsonl + 00-project-tree.jsonl from frontmatter (v1.15.1).
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/f4b8a6e2.py [--apply] [--only UID] [--vault-path PATH]   # --only UID = incremental single-entry index freshen (Argus A106, brief d7b3f1a9 §4)
script_path: vault/tools/f4b8a6e2.py
input:
  type: object
  properties:
    apply:
      type: boolean
      description: Without --apply, dry-run preview only
    vault-path:
      type: string
destructive: false
audit_required: false
writes_scope:
- vault/00-index.jsonl
- vault/00-project-tree.jsonl
governance_category: lifecycle
description: 'v1.15.1 fast/frequent rebuild script. Reads YAML frontmatter from vault/files/<uid>.md (canonical bulk) AND Studio-root *.md files with uid: frontmatter (Stream G — STUDIO.md, TROPO-CAPABILITIES.md). Writes vault/00-index.jsonl + vault/00-project-tree.jsonl. Pure index work — no rehydrate, no relations rendering, no cascade cleanup (those live in rebuild-vault.py wrapper). Idempotent. Reflection-of-frontmatter: every top-level scalar/list field passes through into the index (with title/description truncation preserved + underscore-prefixed denylist). Closes the silent index-drift defect Mike-Metis surfaced 2026-05-09.'
domain_tags:
- index-rebuild
- project-tree
- fast-frequent
- reflection-of-frontmatter
- studio-root-scan
- idempotent
- v1.15.1-stream-a
trigger_description: Reach for this any time you've added/removed/amended a vault entry's frontmatter and need the index + project-tree to reflect it. Fast (~1-2s on 1460+ entries) and idempotent — safe to re-run frequently. Use this for the common-case edit-and-index cycle; for the comprehensive refresh (index + symlink rehydrate + cascade cleanup) use rebuild-vault.py instead. Run with --apply to write; without --apply for dry-run preview. Reflection-of-frontmatter means new conventions (era, voice_authority, category, audience, etc.) reach the index automatically without script updates.
created: 2026-05-09
created_by: argus-a53
modified: 2026-05-09
modified_by: argus-a53
governed_by: d5e1b4a3
capsule_version: '2.5'
schema_version: 2
extraction_scope: ship
member_of:
- c5a9d3b7
tags:
- tool
- cli
- rebuild-index
- fast-frequent
- reflection-of-frontmatter
- studio-root-scan
- v1.15.1-stream-a
subsystem_hub:
- dbc1cbbf
---
"""
from __future__ import annotations

"""rebuild-index.py — fast index + project-tree rebuild (v1.15.1 Stream A).

Rebuilds `vault/00-index.jsonl` + `vault/00-project-tree.jsonl` from the YAML
frontmatter of every governed file. Pure index work. No rehydrate, no relations
rendering, no cascade cleanup — those belong to the comprehensive cadence and
live in rebuild-vault.py (which calls this script + adds those passes).

Sources scanned:
    1. `vault/files/*.md` — canonical vault entries (the bulk).
    2. Studio-root `*.md` files with `uid:` frontmatter (STUDIO.md, TROPO-CAPABILITIES.md, etc.) —
       per v1.15.1 Stream G: previously unindexed; closes the C20 + R12 ERRORs that
       v1.15 bypassed via TROPO_SKIP_ENFORCEMENT_GATE=1.

v1.15.1 changes vs prior rebuild-vault.py behavior:
    - Stream A: rebuild-index is the fast/frequent script (~1-2s); rebuild-vault becomes
      the comprehensive wrapper that calls rebuild-index then rehydrate + cascade.
    - Stream C: reflection-of-frontmatter — process_file no longer hardcodes a ~16-field
      allowlist. Every top-level frontmatter scalar/list is passed through into the index
      (with title/description truncation preserved + underscore-prefixed denylist as
      escape hatch). Closes the silent index-drift defect class Mike-Metis surfaced
      2026-05-09 (era / voice_authority / category / audience etc. now indexed).
    - Stream G: Studio-root scan extension. STUDIO.md (f1a7b3c2) + TROPO-CAPABILITIES.md
      (7a1ca900) become indexed; v1.14 release-plan capabilities_touched resolves correctly.

Usage:
    python3 .tropo/scripts/rebuild-index.py            # dry-run preview
    python3 .tropo/scripts/rebuild-index.py --apply    # write
    python3 .tropo/scripts/rebuild-index.py --vault-path <path>

Vault path resolution:
    1. Explicit --vault-path wins.
    2. Otherwise: walks up from script location for vault/ + .tropo/.
    3. Fallback: cwd if it has those anchors.

No third-party dependencies. Targets Python 3.8+.

Author: argus-a53
Owner: argus
Domain: ledger-hygiene; v1.15.1 rebuild-script reform.
"""

"""rebuild-index.py — fast index + project-tree rebuild (v1.15.1 Stream A refactor; v1.30.0 Stream B auto-invoke rehydrate).

After v1.30.0 Stream B (Argus A63 + Mike pair-design 2026-05-15), `--apply` mode automatically
invokes rehydrate.py at end of successful index rebuild (single-gesture Studio-tier index
rebuild). Use `--skip-rehydrate` to opt out (e.g., when rebuild-vault.py is the caller and
handles rehydrate explicitly at its [3/5] step).

Exit codes:
    0   PASS — index rebuild + rehydrate (if invoked) clean
    1   index rebuild itself failed (existing)
    2   vault root could not be resolved (existing)
    6   rehydrate.py FAILED (v1.30.0 Stream B NEW; index rebuild succeeded but rehydrate did not)
    7   rehydrate.py timeout (v1.30.0 Stream B NEW; 120s ceiling)
"""

import argparse
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import yaml as _yaml
except ImportError:
    _yaml = None  # type: ignore


# v1.56 Lane S: script relocated to vault/tools/; siblings resolved by UID
_TOOLS = Path(__file__).resolve().parent
REHYDRATE = _TOOLS / "a7c5e3f1.py"   # rehydrate — v1.30.0 Stream B auto-invoke


# ---------------------------------------------------------------------------
# Mentions Parser (v1.71 Edge-Substrate; 55c33476)
# ---------------------------------------------------------------------------
_MENTIONS_RE = re.compile(
    r'\[.*?\]\((?:(?:\.\./files/)|(?:vault/files/))?([0-9a-fA-F]{8})\.md\)'
    r'|(?<![a-zA-Z0-9_-])([0-9a-fA-F]{8})\.md(?![a-zA-Z0-9_-])'
    r'|\[\[([0-9a-fA-F]{8})\]\]'
)

_B8E4F1A3_MOD = None

def _get_mentions(body: str, src_uid: str, declared_pairs: set[tuple[str, str]], all_uids: set[str]) -> list[str]:
    """Parse body for UID mentions, dropping code fences, relations blocks, and 4 drop cases."""
    global _B8E4F1A3_MOD
    if _B8E4F1A3_MOD is None:
        b8_path = _TOOLS / "b8e4f1a3.py"
        spec = importlib.util.spec_from_file_location("b8e4f1a3", str(b8_path))
        if not spec or not spec.loader:
            raise ImportError(f"FAIL-LOUD: Could not load {b8_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _B8E4F1A3_MOD = mod

    # 1. Strip fenced and inline code
    body_stripped = re.sub(r'```.*?```', '', body, flags=re.DOTALL)
    body_stripped = re.sub(r'`[^`\n]+`', '', body_stripped)
    
    # 2. Strip Relations/Members blocks
    try:
        rel_bounds = _B8E4F1A3_MOD.find_relations_block(body_stripped)
        if rel_bounds is not None:
            start, end = rel_bounds
            body_stripped = body_stripped[:start] + body_stripped[end:]
        body_stripped = _B8E4F1A3_MOD._STALE_MEMBERS_RE.sub('', body_stripped)
    except Exception as e:
        print(f"FAIL-LOUD: b8e4f1a3 parser failed: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Parse UIDs
    mentions: set[str] = set()
    for match in _MENTIONS_RE.finditer(body_stripped):
        uid = next(g for g in match.groups() if g is not None).lower()
        if uid == src_uid: continue # Drop self
        if uid not in all_uids:
            print(f"  [WARN] mentions parser: dead link to {uid} found in {src_uid}", file=sys.stderr)
            continue # Drop dead
        if (src_uid, uid) in declared_pairs: continue # Drop same-direction declared
        mentions.add(uid)
        
    return sorted(list(mentions))

# ---------------------------------------------------------------------------
# Frontmatter parsing (zero-dependency YAML subset)
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def split_frontmatter(text: str) -> Optional[str]:
    """Extract YAML frontmatter as raw string. Returns None if not present."""
    m = FRONTMATTER_RE.match(text)
    return m.group(1) if m else None


def get_scalar(fm: str, field: str) -> Optional[str]:
    """Get a top-level scalar field. Strips quotes; handles multi-line block scalars."""
    # 1. Block scalar detection (| or >)
    block_pattern = rf'^{re.escape(field)}:\s*([|>])\s*\n((?:\s+.*\n?)*)'
    m_block = re.search(block_pattern, fm, re.MULTILINE)
    if m_block:
        content = m_block.group(2)
        if not content.strip(): return ""
        lines = content.splitlines()
        # Use first non-empty line to detect indent
        first_line = next((l for l in lines if l.strip()), lines[0])
        indent = len(first_line) - len(first_line.lstrip())
        return "\n".join(line[indent:] for line in lines).strip()

    # 2. Quoted or simple scalar
    pattern = rf'^{re.escape(field)}:\s*(.*)$'
    m = re.search(pattern, fm, re.MULTILINE)
    if not m: return None
    value = m.group(1).rstrip()
    if value.startswith('"'):
        end = value.find('"', 1)
        if end > 0: return value[1:end]
    if value.startswith("'"):
        end = value.find("'", 1)
        if end > 0: return value[1:end]
    if '#' in value: value = value.split('#', 1)[0]
    return value.rstrip()


def get_list(fm: str, field: str) -> list[str]:
    """Get a top-level list field. Handles inline [a,b] and block - forms."""
    def clean_item(s: str) -> str:
        # v1.71 fix (argus-a114 2026-06-16): strip a trailing YAML inline comment +
        # surrounding quotes per item. `"uid"   # comment` -> `uid`. A '#' INSIDE the
        # quoted value is preserved, so free-text fields (acceptance_criteria) stay intact.
        # (The T20 rewrite dropped comment-stripping -> commented member_of items like
        #  `- "3cc28cc0"  # marker` parsed to a malformed UID -> no edge -> L0 bubbling.)
        s = s.strip()
        m = re.match(r'''^["']([^"']*)["']\s*(?:#.*)?$''', s)
        if m: return m.group(1).strip()
        return re.split(r'\s+#', s, 1)[0].strip().strip('"').strip("'")
    inline = re.search(rf'^{re.escape(field)}:\s*\[([^\]]*)\]\s*(?:#.*)?$', fm, re.MULTILINE)
    if inline:
        raw = inline.group(1)
        if not raw.strip(): return []
        return [clean_item(v) for v in raw.split(',') if v.strip()]

    # v1.14 fix: \s*-\s+ tolerates zero leading whitespace AND indented forms.
    # v1.70.x fix (Talos T20): handle multi-line items via indentation-aware scan.
    # v1.71 REGRESSION FIX (argus-a114 2026-06-16): the T20 capture `((?:\s+.*\n?)+)` required
    #   leading whitespace on EVERY line, silently dropping standard COLUMN-0 YAML block
    #   sequences (`member_of:\n- uid`) -> collapsed member_of for ~1.8k files studio-wide.
    #   New capture accepts a column-0 `- item` line AND indented continuations (so the T20
    #   multi-line acceptance_criteria scan is preserved). Verified vs a full battery pre-apply.
    block_pattern = rf'^{re.escape(field)}:\s*(?:[|>]-?)?\s*\n((?:[ \t]*-.*\n?|[ \t]+.*\n?)+)'
    block = re.search(block_pattern, fm, re.MULTILINE)
    if block:
        items: list[str] = []
        current = ""
        for line in block.group(1).splitlines():
            if not line.strip(): continue
            m = re.match(r'^\s*-\s+(.*)$', line)
            if m:
                if current: items.append(clean_item(current))
                current = m.group(1)
            elif current:
                current += " " + line.strip()
        if current: items.append(clean_item(current))
        return [i for i in items if i]
    return []


def get_int(fm: str, field: str, default: int = 1) -> int:
    """Get a top-level int field with default."""
    v = get_scalar(fm, field)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# v1.15.1 Stream C: reflection-of-frontmatter helpers
# ---------------------------------------------------------------------------

# Top-level key regex: identifier followed by `:` at column 0 (not indented).
TOP_LEVEL_KEY_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*):", re.MULTILINE)

# Fields handled by the structured "core" pass — don't re-extract via reflection.
CORE_FIELDS = {
    'uid', 'type', 'title', 'name', 'description', 'stage', 'state', 'status',
    'owner', 'member_of', 'created', 'modified', 'last_modified', 'tags',
    'file_ext', 'schema_version', 'role', 'extraction_scope', 'subsystem_name',
    'acceptance_criteria',
}


def get_all_top_level_keys(fm: str) -> list[str]:
    """Return all top-level (column-0, non-indented) frontmatter keys, in order."""
    keys: list[str] = []
    seen: set[str] = set()
    for line in fm.split("\n"):
        if not line or line.startswith((" ", "\t", "#")):
            continue
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):", line)
        if m:
            key = m.group(1)
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def detect_field_type(fm: str, field: str) -> str:
    """Return 'list', 'scalar', 'mapping', or 'absent' based on declaration shape."""
    if re.search(rf'^{re.escape(field)}:\s*\[', fm, re.MULTILINE): return 'list'
    if re.search(rf'^{re.escape(field)}:\s*(?:[|>]-?)?\s*\n\s*-\s+', fm, re.MULTILINE): return 'list'
    if re.search(rf'^{re.escape(field)}:\s*\n\s+[a-zA-Z_"]', fm, re.MULTILINE): return 'mapping'
    if re.search(rf'^{re.escape(field)}:\s*([|>])', fm, re.MULTILINE): return 'scalar'
    if re.search(rf'^{re.escape(field)}:\s*\S', fm, re.MULTILINE): return 'scalar'
    return 'absent'


def reflect_frontmatter(fm: str) -> dict[str, Any]:
    """v1.15.1 Stream C: pass-through reflection of frontmatter beyond CORE_FIELDS.

    Returns a dict of {field_name: value} for every top-level frontmatter key NOT
    in CORE_FIELDS, with type-appropriate value (scalar string / list / skipped for
    nested mappings). Underscore-prefixed keys are denylisted (escape hatch convention).
    Mappings are skipped at v1.15.1 (queryability adds limited value vs serialization
    complexity); future cycles may add structured mapping reflection.
    """
    out: dict[str, Any] = {}
    for key in get_all_top_level_keys(fm):
        if key in CORE_FIELDS:
            continue
        if key.startswith('_'):
            continue
        kind = detect_field_type(fm, key)
        if kind == 'scalar':
            v = get_scalar(fm, key)
            if v is not None:
                out[key] = v
        elif kind == 'list':
            v = get_list(fm, key)
            if v:
                out[key] = v
        # mapping / absent: skip
    return out


# ---------------------------------------------------------------------------
# Stage/state normalization (mirrors prior rebuild-vault.py)
# ---------------------------------------------------------------------------

V3_STATUS_TO_STAGE_STATE: dict[str, tuple[str, str]] = {
    'requested':  ('ideate',  'active'),
    'accepted':   ('ideate',  'active'),
    'active':     ('build',   'active'),
    'verify':     ('verify',  'active'),
    'done':       ('done',    'active'),
    'blocked':    ('build',   'active'),
    'rejected':   ('done',    'archived'),
    'cancelled':  ('done',    'archived'),
}
V3_STATUS_VOCAB = set(V3_STATUS_TO_STAGE_STATE.keys())

V4_STATUS_TO_STAGE_STATE: dict[str, tuple[str, str]] = {
    'new':       ('ideate', 'active'),
    'accepted':  ('ideate', 'active'),
    'active':    ('build',  'active'),
    'closed':    ('done',   'active'),
}
V4_STATUS_VOCAB = set(V4_STATUS_TO_STAGE_STATE.keys())

PRESERVE_STAGE_STATUSES = {'archived', 'superseded'}


def normalize_stage_state(fm: str) -> tuple[str, str]:
    stage_in = get_scalar(fm, 'stage')
    state_in = get_scalar(fm, 'state')
    status_in = get_scalar(fm, 'status')
    if stage_in and state_in:
        return stage_in, state_in
    if state_in in PRESERVE_STAGE_STATUSES:
        return stage_in or 'done', state_in
    if status_in in V4_STATUS_VOCAB:
        return V4_STATUS_TO_STAGE_STATE[status_in]
    if status_in in V3_STATUS_VOCAB:
        return V3_STATUS_TO_STAGE_STATE[status_in]
    return stage_in or 'ideate', state_in or 'active'


# ---------------------------------------------------------------------------
# File processing — reflection-augmented per Stream C
# ---------------------------------------------------------------------------

UID_RE = re.compile(r'^[0-9a-f]{8}$')


def process_file(filepath: Path, uid_override: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Parse one governed file → IndexRecord dict, or None on failure.

    uid_override: if provided, used as the canonical UID instead of filename stem.
    Useful for Studio-root files (Stream G) where the filename is not the UID.

    v1.15.1 Stream C: in addition to the structured core fields, every top-level
    frontmatter key not in CORE_FIELDS is passed through into the record via
    reflection-of-frontmatter (with `_`-prefixed denylist + mapping skip).
    Closes the silent index-drift defect class.
    """
    try:
        text = filepath.read_text(errors='replace')
    except Exception:
        return None

    fm = split_frontmatter(text)
    if fm is None:
        return None

    if uid_override:
        uid = uid_override
    else:
        uid = filepath.stem
    if not UID_RE.match(uid):
        return None

    fm_uid = get_scalar(fm, 'uid')
    if fm_uid and fm_uid != uid:
        # Mismatch — uid_override or filename is authoritative.
        pass

    stage, state = normalize_stage_state(fm)
    member_of = [u for u in get_list(fm, 'member_of') if UID_RE.match(u)]
    created = get_scalar(fm, 'created') or '2026-01-01'

    record: dict[str, Any] = {
        'uid':            uid,
        'type':           get_scalar(fm, 'type') or 'document',
        'title':          (get_scalar(fm, 'title') or get_scalar(fm, 'name') or '')[:100],
        'description':    (get_scalar(fm, 'description') or ''),  # 5d1ec9a9: removed 120-char cap
        'stage':          stage,
        'state':          state,
        'owner':          (get_scalar(fm, 'owner') or 'unknown')[:30],
        'member_of':      member_of,
        'created':        created,
        'modified':       get_scalar(fm, 'modified') or get_scalar(fm, 'last_modified') or created,
        'tags':           get_list(fm, 'tags'),
        'file_ext':       get_scalar(fm, 'file_ext') or 'md',
        'schema_version': get_int(fm, 'schema_version', 1),
    }

    status = get_scalar(fm, 'status')
    if status:
        record['status'] = status

    acceptance_criteria = get_list(fm, 'acceptance_criteria')
    if acceptance_criteria:
        record['acceptance_criteria'] = acceptance_criteria

    role = get_scalar(fm, 'role')
    if role:
        record['role'] = role

    extraction_scope = get_scalar(fm, 'extraction_scope')
    if extraction_scope:
        record['extraction_scope'] = extraction_scope

    subsystem_name = get_scalar(fm, 'subsystem_name')
    if subsystem_name:
        record['subsystem_name'] = subsystem_name

    # v1.15.1 Stream C: reflective pass for everything else.
    reflected = reflect_frontmatter(fm)
    for key, value in reflected.items():
        if key not in record:
            record[key] = value

    return record


# ---------------------------------------------------------------------------
# Project tree builder (unchanged from prior rebuild-vault.py)
# ---------------------------------------------------------------------------

def build_project_tree(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _is_navigable(r):
        t = r.get('type')
        if t == 'project':
            return True
        if t == 'pipeline':
            role = (r.get('role') or '').strip('"').strip("'")
            return role not in ('stage', 'step', 'leaf')
        # v1.14 schema split (Argus A80 2026-05-23): subsystem-hub type entries are
        # navigable parents — they are the canonical "where does this nest" anchors
        # entries declare via subsystem_hub: field. Previously hubs were excluded from
        # navigable set (the v1.13.1 hub-skip workaround era), which meant subsystem_hub:
        # edges pointing at hubs got filtered out. Post-v2.5 they MUST be navigable
        # so entries nest under their declared hub correctly.
        if t == 'subsystem-hub':
            return True
        return False
    projects = [r for r in records if _is_navigable(r)]
    by_uid = {p['uid']: p for p in projects}
    # NOTE v1.51 (Argus A80 2026-05-23, v1.14 schema split): hub_uids set retained for
    # informational use, but the v1.13.1 hub-skip workaround is REMOVED. Post-v2.5 capsule
    # amendment + migration (.tropo/scripts/migrate-v14-subsystem-hub-split.py applied
    # 2026-05-23 to 1059 entries), subsystem hub edges live in `subsystem_hub:` field;
    # `member_of:` contains only true parent project UIDs. Validation Check 11
    # (check_no_hub_uids_in_member_of) at project.capsule v2.5 enforces this post-migration.
    # Tree-building now reads BOTH member_of AND subsystem_hub as parent-edge sources;
    # no UIDs are skipped at render time.
    hub_uids = {p['uid'] for p in projects if p.get('subsystem_name')}

    def _all_parent_uids(p: dict) -> list[str]:
        """v1.14 schema split: parent edges come from BOTH member_of: AND subsystem_hub:.
        member_of: declares true parent projects. subsystem_hub: declares subsystem hub
        catalog membership. Both render as parent edges in the project tree."""
        edges: list[str] = []
        for pu in p.get('member_of', []) or []:
            if pu in by_uid and pu not in edges:
                edges.append(pu)
        for pu in p.get('subsystem_hub', []) or []:
            if pu in by_uid and pu not in edges:
                edges.append(pu)
        return edges

    children_of: dict[str, list[str]] = {p['uid']: [] for p in projects}
    for p in projects:
        for parent_uid in _all_parent_uids(p):
            children_of[parent_uid].append(p['uid'])

    roots = [p for p in projects if not _all_parent_uids(p)]
    roots.sort(key=lambda p: p.get('title', ''))

    visited_global: set[str] = set()
    cycles_found: list[list[str]] = []
    for p in projects:
        if p['uid'] in visited_global:
            continue
        path: list[str] = []
        current: Optional[str] = p['uid']
        while current and current in by_uid:
            if current in path:
                cycle_start = path.index(current)
                cycle = path[cycle_start:] + [current]
                cycles_found.append(cycle)
                visited_global.update(cycle)
                for cycle_uid in cycle:
                    cycle_p = by_uid[cycle_uid]
                    if cycle_p not in roots:
                        roots.append(cycle_p)
                break
            visited_global.add(current)
            path.append(current)
            # v1.14 schema split: read BOTH member_of AND subsystem_hub for cycle detection
            parents = _all_parent_uids(by_uid[current])
            current = parents[0] if parents else None
    if cycles_found:
        sys.stderr.write(f'WARNING: {len(cycles_found)} project-graph cycle(s) detected; cycle members promoted to roots:\n')
        for cycle in cycles_found:
            sys.stderr.write(f'  Cycle: {" -> ".join(uid[:8] for uid in cycle)}\n')

    result: list[dict[str, Any]] = []

    def traverse(uid: str, parent_uid: Optional[str], depth: int) -> None:
        p = by_uid.get(uid)
        if not p:
            return
        children = children_of.get(uid, [])
        result.append({
            'uid':      p['uid'],
            'title':    p.get('title', ''),
            'stage':    p.get('stage', 'ideate'),
            'state':    p.get('state', 'active'),
            'parent':   parent_uid,
            'children': children,
            'depth':    depth,
        })
        for child_uid in children:
            traverse(child_uid, uid, depth + 1)

    for root in roots:
        traverse(root['uid'], None, 0)

    return result


# ---------------------------------------------------------------------------
# vault/tools/ scan (v1.56 E.1 — Talos T10 2026-05-27)
# Handles three file kinds per tool.capsule v1.6 §2.5 canonical file layout:
#   .py  — python-script: frontmatter in leading docstring between --- markers
#   .md  — external-cli / action / http / platform / sa: standard frontmatter
#   .json — mcp-tool: frontmatter in top-level "tropo_metadata" object field
# ---------------------------------------------------------------------------

def split_py_docstring_frontmatter(text: str) -> Optional[str]:
    """Extract YAML frontmatter from a Python file's leading docstring.

    Handles both tight format (docstring starts immediately after shebang) and
    the v1.55-style loose format (newline between opening quotes and first ---):

      tight:  \"\"\"---\\nuid: abc\\n---\"\"\"
      loose:  \"\"\"\\n---\\nuid: abc\\n---\\n\"\"\"

    Returns the raw YAML string (between the --- markers) or None if not found.
    """
    # Skip shebang + any leading comment lines
    lines = text.split('\n')
    i = 0
    while i < len(lines) and (lines[i].startswith('#') or not lines[i].strip()):
        i += 1
    rest = '\n'.join(lines[i:])
    # Match leading triple-quoted docstring (either """ or ''')
    m = re.match(r'^("""|\'\'\')(.*?)\1', rest, re.DOTALL)
    if not m:
        return None
    docstring_body = m.group(2)
    # Extract --- ... --- block within the docstring
    fm_match = re.search(r'---\n(.*?)\n---', docstring_body, re.DOTALL)
    if not fm_match:
        return None
    return fm_match.group(1)


def split_json_tropo_metadata(text: str) -> Optional[str]:
    """Extract YAML-serializable frontmatter from a JSON tool file's tropo_metadata field.

    Per tool.capsule v1.6 §2.5: mcp-tool files are JSON with a top-level
    "tropo_metadata" object carrying capsule-required frontmatter fields.
    Returns the tropo_metadata dict serialized as YAML-style string, or None.
    """
    try:
        import json as _json
        obj = _json.loads(text)
        meta = obj.get('tropo_metadata')
        if not isinstance(meta, dict):
            return None
        # Serialize as minimal YAML (one field per line; scalars only at top level)
        lines: list[str] = []
        for k, v in meta.items():
            if isinstance(v, list):
                lines.append(f'{k}:')
                for item in v:
                    lines.append(f'  - {item}')
            elif isinstance(v, bool):
                lines.append(f'{k}: {"true" if v else "false"}')
            elif v is None:
                pass
            else:
                lines.append(f'{k}: {v}')
        return '\n'.join(lines) if lines else None
    except Exception:
        return None


def process_tool_file(filepath: Path) -> Optional[dict[str, Any]]:
    """Parse a vault/tools/ file — .py/.md/.json — into an IndexRecord dict."""
    try:
        text = filepath.read_text(errors='replace')
    except Exception:
        return None

    ext = filepath.suffix.lower()
    if ext == '.py':
        fm = split_py_docstring_frontmatter(text)
    elif ext == '.json':
        fm = split_json_tropo_metadata(text)
    else:  # .md or unknown
        fm = split_frontmatter(text)

    if fm is None:
        return None

    uid = get_scalar(fm, 'uid')
    if not uid:
        uid = filepath.stem
    if not UID_RE.match(uid):
        return None

    # Reuse process_file logic: temporarily synthesise a .md-style text so
    # we can call it without duplication. Instead, call the core parsing inline.
    stage, state = normalize_stage_state(fm)
    member_of = [u for u in get_list(fm, 'member_of') if UID_RE.match(u)]
    created = get_scalar(fm, 'created') or '2026-01-01'

    # Derive a file_ext that reflects the actual file kind
    file_ext_map = {'.py': 'py', '.json': 'json', '.md': 'md'}
    file_ext = file_ext_map.get(ext, 'md')

    record: dict[str, Any] = {
        'uid':            uid,
        'type':           get_scalar(fm, 'type') or 'tool',
        'title':          (get_scalar(fm, 'title') or get_scalar(fm, 'name') or '')[:100],
        'description':    (get_scalar(fm, 'description') or ''),  # 5d1ec9a9: removed 120-char cap
        'stage':          stage,
        'state':          state,
        'owner':          (get_scalar(fm, 'owner') or 'unknown')[:30],
        'member_of':      member_of,
        'created':        created,
        'modified':       get_scalar(fm, 'modified') or get_scalar(fm, 'last_modified') or created,
        'tags':           get_list(fm, 'tags'),
        'file_ext':       file_ext,
        'schema_version': get_int(fm, 'schema_version', 2),
    }

    status = get_scalar(fm, 'status')
    if status:
        record['status'] = status
    role = get_scalar(fm, 'role')
    if role:
        record['role'] = role
    extraction_scope = get_scalar(fm, 'extraction_scope')
    if extraction_scope:
        record['extraction_scope'] = extraction_scope
    subsystem_name = get_scalar(fm, 'subsystem_name')
    if subsystem_name:
        record['subsystem_name'] = subsystem_name

    # Reflective pass for remaining fields
    reflected = reflect_frontmatter(fm)
    for key, value in reflected.items():
        if key not in record:
            record[key] = value

    return record


def collect_vault_actions_records(vault_root: Path) -> list[dict[str, Any]]:
    """Scan vault/actions/ for .md/.json files; return index records.

    v1.60 Lane A-migrate (Talos T10 2026-05-29) — first-class vault/actions/ indexing
    per Pillar 1 single-file-truth pattern mirroring vault/tools/.
    """
    out: list[dict[str, Any]] = []
    actions_dir = vault_root / 'vault' / 'actions'
    if not actions_dir.is_dir():
        return out
    for f in sorted(actions_dir.iterdir()):
        if f.suffix.lower() not in ('.md', '.json'):
            continue
        if not UID_RE.match(f.stem):
            continue
        rec = process_tool_file(f)  # same parser as vault/tools/
        if rec is not None:
            if rec.get('type') == 'tool':
                rec['type'] = 'action'  # correct type if not declared in frontmatter
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


def collect_vault_session_agents_records(vault_root: Path) -> list[dict[str, Any]]:
    """Scan vault/session-agents/ for .md files; return index records.

    v1.61 Lane S-migrate (Talos T11 2026-05-29) — first-class vault/session-agents/ indexing
    per session-agent.capsule v1.6 §2.5 single-file-truth pattern mirroring vault/tools/.
    Session-agent class definitions migrated from agents/sa/sa.<name>/sa.<name>.md to
    vault/session-agents/<uid>.md canonical location.
    """
    out: list[dict[str, Any]] = []
    sa_dir = vault_root / 'vault' / 'session-agents'
    if not sa_dir.is_dir():
        return out
    for f in sorted(sa_dir.iterdir()):
        if f.suffix.lower() not in ('.md', '.json'):
            continue
        if not UID_RE.match(f.stem):
            continue
        rec = process_tool_file(f)  # same parser as vault/tools/
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


def collect_vault_agents_records(vault_root: Path) -> list[dict[str, Any]]:
    """Scan vault/agents/ for .md files; return index records.

    v1.69 P0.6 (Talos T14 2026-06-11) — first-class vault/agents/ indexing per
    agent.capsule v2.0 unified-entry shape. Unified agent entries live at
    vault/agents/<uid>.md (type:agent). Directory may be absent pre-migration — skip
    silently so this walker does not break pre-v1.69 rebuilds.
    """
    out: list[dict[str, Any]] = []
    agents_dir = vault_root / 'vault' / 'agents'
    if not agents_dir.is_dir():
        return out
    for f in sorted(agents_dir.iterdir()):
        if f.suffix.lower() != '.md':
            continue
        if not UID_RE.match(f.stem):
            continue
        rec = process_file(f)
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


def collect_vault_playbooks_records(vault_root: Path) -> list[dict[str, Any]]:
    """Scan vault/playbooks/ for .md files; return index records.

    v1.69 P0.6 (Talos T14 2026-06-11) — first-class vault/playbooks/ indexing per
    playbook.capsule unification (S2). Unified playbook entries live at
    vault/playbooks/<uid>.md (type:playbook). Directory may be absent pre-migration —
    skip silently so this walker does not break pre-v1.69 rebuilds.
    """
    out: list[dict[str, Any]] = []
    playbooks_dir = vault_root / 'vault' / 'playbooks'
    if not playbooks_dir.is_dir():
        return out
    for f in sorted(playbooks_dir.iterdir()):
        if f.suffix.lower() != '.md':
            continue
        if not UID_RE.match(f.stem):
            continue
        rec = process_file(f)
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


def collect_vault_tools_records(vault_root: Path) -> list[dict[str, Any]]:
    """Scan vault/tools/ for .py / .md / .json files; return index records.

    v1.56 E.1 (Talos T10 2026-05-27) — first-class vault/tools/ indexing per
    tool.capsule v1.6 §2.5 canonical file layout. Tools live as single-file-truth
    at vault/tools/<uid>.{py|md|json}; each carries YAML frontmatter in the format
    appropriate for its implementation_kind (python docstring / standard .md / JSON
    tropo_metadata field). rebuild-index now indexes them as first-class vault citizens
    alongside vault/files/, capsules, agents, etc.
    """
    out: list[dict[str, Any]] = []
    tools_dir = vault_root / 'vault' / 'tools'
    if not tools_dir.is_dir():
        return out
    for f in sorted(tools_dir.iterdir()):
        if f.suffix.lower() not in ('.py', '.md', '.json'):
            continue
        if not UID_RE.match(f.stem):
            continue
        rec = process_tool_file(f)
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Studio-root scan (v1.15.1 Stream G)
# ---------------------------------------------------------------------------

def collect_studio_root_records(vault_root: Path) -> list[dict[str, Any]]:
    """Scan Studio-root *.md files; return index records for any with uid: frontmatter.

    Closes the v1.14 substrate gap: STUDIO.md + TROPO-CAPABILITIES.md (and any future
    Studio-root entries with uid:) become indexed without being moved into vault/files/.
    Studio-root files keep their canonical home at the root by documented exception.
    """
    out: list[dict[str, Any]] = []
    for f in sorted(vault_root.glob('*.md')):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        uid = get_scalar(fm, 'uid')
        if not uid or not UID_RE.match(uid):
            continue
        rec = process_file(f, uid_override=uid)
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


def collect_agents_records(vault_root: Path) -> list[dict[str, Any]]:
    """Scan agents/** for *.md files with uid: frontmatter; return index records.

    v1.51 Argus A80 2026-05-23 — closes the substrate-coherence gap surfaced by the
    dev-spec validator after capsule indexing fix: agents/ substrate (roadmap.md,
    activation files, charter files, registries, templates, briefings) carries valid
    UIDs that other substrate cites via composes_with / refs / member_of etc. — but
    they weren't queryable through vault/00-index.jsonl. Same architectural class as
    capsule UIDs (fixed earlier this session). Per Mike-A80 "fix it right" doctrine
    + v1.14 schema split Option B precedent: first-class agents/ substrate indexing.

    Scope: agents/**/*.md recursively (covers agent root folders + subfolders);
    only entries with `uid:` frontmatter are indexed. Agent-private workspace files
    without uid: stay non-indexed (correct; they're ephemeral / not graph substrate).
    Excludes archive/ subdirectories per archived-substrate-not-active-index rule.
    """
    out: list[dict[str, Any]] = []
    agents_dir = vault_root / 'agents'
    if not agents_dir.is_dir():
        return out
    for f in sorted(agents_dir.rglob('*.md')):
        # Skip archive/ subdirectories
        if 'archive' in f.parts or '.tropo-capsule' in f.parts:
            continue
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        uid = get_scalar(fm, 'uid')
        if not uid or not UID_RE.match(uid):
            continue
        rec = process_file(f, uid_override=uid)
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


def collect_capsule_records(vault_root: Path) -> list[dict[str, Any]]:
    """Scan .tropo/capsules/*.capsule.md; return index records for any with uid: frontmatter.

    v1.51 Argus A80 2026-05-23 — closes the substrate-coherence gap surfaced by the
    dev-spec.capsule v1.0 validator wire-up: capsule UIDs (e.g., c3f68cb5 dev-spec.capsule;
    9a7d314a doc-spec.capsule; 621824df test-spec.capsule; 34e4cb0b project.capsule) are
    valid substrate targets that other entries cite via composes_with / governed_by /
    aligned_with / committed_substrate / etc. — but they weren't queryable through
    vault/00-index.jsonl because rebuild-index.py only scanned vault/files/ + Studio-root.
    Cross-reference validators (check_dev_spec_committed_substrate_resolvable; the OP-12
    nav-block renderer; UID cross-reference audits) over-flagged capsule UIDs as
    unresolvable. Per Mike-A80 "fix it right" doctrine 2026-05-23 + v1.14 schema split
    Option B precedent: extend the index to include capsule UIDs as first-class queryable
    substrate. Capsule .md files keep their canonical home at .tropo/capsules/ — same
    shape as Studio-root exception per collect_studio_root_records above.
    """
    out: list[dict[str, Any]] = []
    capsules_dir = vault_root / '.tropo' / 'capsules'
    if not capsules_dir.is_dir():
        return out
    for f in sorted(capsules_dir.glob('*.capsule.md')):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        uid = get_scalar(fm, 'uid')
        if not uid or not UID_RE.match(uid):
            continue
        rec = process_file(f, uid_override=uid)
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Vault root resolution
# ---------------------------------------------------------------------------

def resolve_vault_root(explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        p = Path(explicit).resolve()
        if (p / 'vault').is_dir() and (p / '.tropo').is_dir():
            return p
        return None

    script_path = Path(__file__).resolve()
    for candidate in [script_path.parent.parent.parent, script_path.parent.parent, *script_path.parents]:
        if (candidate / 'vault').is_dir() and (candidate / '.tropo').is_dir():
            return candidate

    cwd = Path.cwd()
    if (cwd / 'vault').is_dir() and (cwd / '.tropo').is_dir():
        return cwd

    return None


# ---------------------------------------------------------------------------
# SQLite index builder (fc114e57 — Studio Query Runtime)
# ---------------------------------------------------------------------------

# Edge relations extracted into the edges table for graph traversal.
_EDGE_FIELDS = [
    'member_of', 'refs', 'governed_by', 'composes_with',
    'superseded_by', 'aligned_with', 'calls', 'subsystem_hub',
]

# Core frontmatter columns stored as first-class columns in `entries`.
# Everything else is in fm_json for json_extract access.
_CORE_COLS = {
    'uid', 'type', 'title', 'status', 'state', 'stage',
    'created', 'modified', 'author', 'extraction_scope',
}

_FTS_BODY_CAP = None  # 8364626c fix: no cap — full body indexed (was 6000, truncated entries)

_NAV_BLOCK_RE = __import__('re').compile(
    r'<!--\s*nav-block:start\s*-->.*?<!--\s*nav-block:end\s*-->',
    __import__('re').DOTALL,
)


def _strip_nav_block(text: str) -> str:
    """Strip <!-- nav-block:start --> ... <!-- nav-block:end --> from FTS body (8364626c)."""
    return _NAV_BLOCK_RE.sub('', text).strip()


def _strip_frontmatter_body(raw: str) -> str:
    """Return the body section of a vault .md file (below the closing ---)."""
    if not raw.startswith('---'):
        return raw
    second = raw.find('\n---', 3)
    if second == -1:
        return raw
    return raw[second + 4:].strip()


# ── meta_status_rollup loader (3783a7cb Piece B — LOADER-FIRST) ──────────────

_META_STATUS_VALID_BUCKETS = frozenset({'to-do', 'in-progress', 'done', 'standing'})


def load_meta_status_rollups(
    vault_root: Path,
) -> tuple[dict[str, dict[str, list[str]]], list[str]]:
    """Scan .tropo/capsules/*.capsule.md; return ({type: {bucket: [values]}}, errors).

    LOADER-FIRST (3783a7cb Piece B): an unrecognized meta_status_rollup shape
    ERRORs loudly — never a silent skip. Capsules without the block are skipped
    silently (the block is opt-in during the rollout window).
    """
    rollups: dict[str, dict[str, list[str]]] = {}
    errors: list[str] = []
    capsules_dir = vault_root / '.tropo' / 'capsules'
    if not capsules_dir.exists():
        return rollups, errors

    for capsule_path in sorted(capsules_dir.glob('*.capsule.md')):
        try:
            text = capsule_path.read_text(encoding='utf-8')
        except OSError:
            continue
        if not text.startswith('---'):
            continue
        lines = text.split('\n')
        end_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == '---':
                end_idx = i
                break
        if end_idx is None:
            continue
        fm_text = '\n'.join(lines[1:end_idx])
        if _yaml is None:
            continue
        try:
            parsed = _yaml.safe_load(fm_text)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        rollup = parsed.get('meta_status_rollup')
        if rollup is None:
            continue  # no block declared — silent skip

        type_name = capsule_path.name.split('.capsule.md')[0]

        if not isinstance(rollup, dict):
            errors.append(
                f'[ERROR] {capsule_path.name} — meta_status_rollup: unrecognized shape '
                f'(expected {{bucket: [values]}}, got {type(rollup).__name__}) — 3783a7cb Piece B'
            )
            continue

        parsed_rollup: dict[str, list[str]] = {}
        shape_ok = True
        for bucket, values in rollup.items():
            if bucket not in _META_STATUS_VALID_BUCKETS:
                errors.append(
                    f'[ERROR] {capsule_path.name} — meta_status_rollup: unrecognized bucket '
                    f'{bucket!r} (valid: {sorted(_META_STATUS_VALID_BUCKETS)}) — 3783a7cb Piece B'
                )
                shape_ok = False
                continue
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                errors.append(
                    f'[ERROR] {capsule_path.name} — meta_status_rollup.{bucket}: '
                    f'unrecognized shape (expected list of strings) — 3783a7cb Piece B'
                )
                shape_ok = False
                continue
            parsed_rollup[bucket] = [v.lower() for v in values]

        if shape_ok:
            rollups[type_name] = parsed_rollup

    return rollups, errors


# ── Shared per-record → index-row transform (single source: full rebuild + rebuild --only) ──
# Extracted from build_sqlite_index so the incremental freshen (freshen_one / `--only <uid>`)
# and the full rebuild derive every entry's row IDENTICALLY — no second implementation to drift
# (brief d7b3f1a9 §4 design-property #3). Argus A106 2026-06-09.
_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)


def _raw_scalar(fm_text: str, field: str) -> Optional[str]:
    """Extract a raw scalar from YAML frontmatter text without laundering (store-raw)."""
    m = re.search(rf'^{re.escape(field)}:\s*(.*)$', fm_text, re.MULTILINE)
    if not m:
        return None
    val = m.group(1).strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    if not (m.group(1).strip().startswith('"') or m.group(1).strip().startswith("'")):
        if '#' in val:
            val = val.split('#', 1)[0].rstrip()
    return val or None


def _record_to_index_rows(rec: dict, files_dir: Path, declared_pairs: Optional[set[tuple[str, str]]] = None, all_uids: Optional[set[str]] = None) -> tuple:
    """One IndexRecord → (entry_row, edge_rows, fts_row) for vault/00-index.sqlite.
    SINGLE SOURCE shared by build_sqlite_index (full) and freshen_one (rebuild --only).
    Store-raw: core columns read raw frontmatter from vault/files/<uid>.md (never laundered)."""
    uid = rec.get('uid', '')
    raw_fm: Optional[str] = None
    body = ''
    fp = files_dir / f'{uid}.md'
    if fp.exists():
        try:
            file_text = fp.read_text(encoding='utf-8', errors='replace')
            fm_m = _FRONTMATTER_RE.match(file_text)
            if fm_m:
                raw_fm = fm_m.group(1)
                body = file_text[fm_m.end():].strip()
            else:
                body = file_text.strip()
            body = _strip_nav_block(body)
        except OSError:
            pass

    if raw_fm is not None:
        raw_type     = _raw_scalar(raw_fm, 'type')
        raw_title    = _raw_scalar(raw_fm, 'title')
        raw_status   = _raw_scalar(raw_fm, 'status')
        raw_state    = _raw_scalar(raw_fm, 'state')
        raw_stage    = _raw_scalar(raw_fm, 'stage')
        raw_created  = _raw_scalar(raw_fm, 'created')
        raw_modified = _raw_scalar(raw_fm, 'modified')
        raw_author   = _raw_scalar(raw_fm, 'author')
        raw_scope    = _raw_scalar(raw_fm, 'extraction_scope')
        raw_ac       = json.dumps(get_list(raw_fm, 'acceptance_criteria'), separators=(',', ':')) if 'acceptance_criteria:' in raw_fm else None
    else:
        raw_type     = rec.get('type')
        raw_title    = rec.get('title')
        raw_status   = rec.get('status')
        raw_state    = rec.get('state')
        raw_stage    = rec.get('stage')
        raw_created  = rec.get('created')
        raw_modified = rec.get('modified')
        raw_author   = rec.get('author')
        raw_scope    = rec.get('extraction_scope')
        raw_ac       = json.dumps(rec.get('acceptance_criteria'), separators=(',', ':')) if 'acceptance_criteria' in rec else None

    mo = rec.get('member_of')
    if isinstance(mo, list) and mo:
        mo_primary: Optional[str] = str(mo[0])
    elif isinstance(mo, str) and mo:
        mo_primary = mo
    else:
        mo_primary = None

    entry_row = (
        uid, raw_type, raw_title, raw_status, raw_state, raw_stage,
        raw_created, raw_modified, raw_author, raw_scope, mo_primary,
        raw_ac, json.dumps(rec, separators=(',', ':')),
    )

    edge_rows: list[tuple] = []
    for field in _EDGE_FIELDS:
        vals = rec.get(field)
        if not vals:
            continue
        if isinstance(vals, str):
            vals = [vals]
        if isinstance(vals, list):
            for v in vals:
                if isinstance(v, str) and v.strip():
                    edge_rows.append((uid, field, v.strip()))

    if declared_pairs is not None and all_uids is not None:
        mentions = _get_mentions(body, uid, declared_pairs, all_uids)
        for m in mentions:
            edge_rows.append((uid, 'mentions', m))

    fts_row = (uid, raw_title or '', body)
    return entry_row, edge_rows, fts_row


def freshen_one(uid: str, vault_root: Path) -> int:
    """rebuild --only <uid>: incrementally re-derive + upsert ONE entry's index rows
    (row + outbound edges + FTS) into the LIVE vault/00-index.sqlite, in a single
    transaction. Non-authoritative + self-healing per fc114e57 v1.6 (the next full
    rebuild reconciles from frontmatter). meta_status is a VIEW — updating the row
    re-buckets the card on the cockpit's next query; nothing imperative to recompute.
    Returns 0 on success; non-zero on a clean no-write failure. Argus A106 2026-06-09."""
    if not UID_RE.match(uid):
        print(f'[rebuild --only] {uid!r} is not an 8-hex UID', file=sys.stderr)
        return 2
    files_dir = vault_root / 'vault' / 'files'
    # v1.69 path-awareness: consult the live index for the true source path before
    # falling back to vault/files/<uid>.md — entries in vault/agents/ (unified
    # agent entries) would otherwise always miss (freshen_one A89 class fix).
    fp = None
    sqlite_path = vault_root / 'vault' / '00-index.sqlite'
    if sqlite_path.exists():
        try:
            import sqlite3 as _sq3, json as _json
            with _sq3.connect(str(sqlite_path)) as _conn:
                row = _conn.execute(
                    "SELECT json_extract(fm_json, '$.path') FROM entries WHERE uid=?", (uid,)
                ).fetchone()
                if row and row[0]:
                    candidate = vault_root / row[0]
                    if candidate.exists():
                        fp = candidate
        except Exception:
            pass
    if fp is None:
        fp = files_dir / f'{uid}.md'
    if not fp.exists():
        print(f'[rebuild --only] no governed file at {fp} — nothing to freshen '
              f'(a full rebuild reconciles deletions)', file=sys.stderr)
        return 1
    rec = process_file(fp)
    if rec:
        rec['path'] = str(fp.relative_to(vault_root))  # v1.69 path-provenance
    if not rec or not rec.get('uid'):
        print(f'[rebuild --only] {uid}: could not parse a record from {fp.name}', file=sys.stderr)
        return 1
    sqlite_path = vault_root / 'vault' / '00-index.sqlite'
    if not sqlite_path.exists():
        print(f'[rebuild --only] {sqlite_path} absent — run a full rebuild first', file=sys.stderr)
        return 1
    entry_row, edge_rows, fts_row = _record_to_index_rows(rec, files_dir)
    conn = sqlite3.connect(str(sqlite_path))
    try:
        conn.execute('BEGIN')
        conn.execute('INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', entry_row)
        conn.execute('DELETE FROM edges WHERE src_uid = ?', (uid,))
        if edge_rows:
            conn.executemany('INSERT INTO edges VALUES (?,?,?)', edge_rows)
        conn.execute('DELETE FROM entries_fts WHERE uid = ?', (uid,))
        conn.execute('INSERT INTO entries_fts VALUES (?,?,?)', fts_row)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f'[rebuild --only] {uid}: transaction rolled back — {e}', file=sys.stderr)
        return 1
    finally:
        conn.close()
    # A108 new finding: --only must also upsert vault/00-index.jsonl so callers
    # that read the JSONL (not SQLite) see the freshened entry. Without this,
    # new UIDs minted + immediately freshened are absent from 00-index.jsonl,
    # and the tool reported success anyway (silent partial success defect).
    jsonl_path = vault_root / 'vault' / '00-index.jsonl'
    if jsonl_path.exists():
        existing_lines = jsonl_path.read_text(encoding='utf-8').splitlines()
        new_line = json.dumps(rec, separators=(',', ':'))
        replaced = False
        out_lines = []
        for line in existing_lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row_uid = json.loads(stripped).get('uid') if stripped.startswith('{') else None
            except Exception:
                row_uid = None
            if row_uid == uid:
                out_lines.append(new_line)
                replaced = True
            else:
                out_lines.append(stripped)
        if not replaced:
            out_lines.append(new_line)  # new entry — append
        jsonl_path.write_text('\n'.join(out_lines) + '\n', encoding='utf-8')
        action = 'updated' if replaced else 'inserted (new)'
        print(f'[rebuild --only] {uid}: 00-index.jsonl {action}')
    else:
        print(f'[rebuild --only] {uid}: 00-index.jsonl absent — JSONL not updated '
              f'(run a full rebuild to create it)', file=sys.stderr)
    print(f'[rebuild --only] freshened {uid}: 1 entry row, {len(edge_rows)} edge(s), 1 FTS row '
          f'(meta_status view re-buckets on query)')
    return 0


def build_sqlite_index(
    vault_root: Path,
    records: list[dict[str, Any]],
    apply_writes: bool,
) -> None:
    """Build vault/00-index.sqlite from the collected index records.

    Schema (fc114e57):
      entries — core frontmatter as typed columns + fm_json TEXT for
                type-specific fields (query via json_extract).  RAW values
                stored — no laundering (the JSONL launders state/stage via
                rebuild-ledger.ts; the SQLite must NOT repeat that).
      edges   — (src_uid, rel, dst_uid) generic edge table, indexed both
                axes; recursive CTEs over this = graph traversal.
      entries_fts — FTS5 virtual table (uid, title, body) for ranked full-text.
      meta_status  — VIEW deriving a rollup lifecycle stage (not a stored column;
                    read from canon at query time per fc114e57 §4).

    Atomic rebuild: build to vault/00-index.sqlite.tmp then os.replace().
    """
    sqlite_path = vault_root / 'vault' / '00-index.sqlite'
    tmp_path = sqlite_path.with_suffix('.sqlite.tmp')
    files_dir = vault_root / 'vault' / 'files'

    if not apply_writes:
        print(f'  [DRY-RUN] would build {sqlite_path.name} ({len(records)} records)')
        return

    if tmp_path.exists():
        tmp_path.unlink()

    conn = sqlite3.connect(str(tmp_path))
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')

        # ── entries table ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                uid                 TEXT PRIMARY KEY,
                type                TEXT,
                title               TEXT,
                status              TEXT,
                state               TEXT,
                stage               TEXT,
                created             TEXT,
                modified            TEXT,
                author              TEXT,
                extraction_scope    TEXT,
                member_of_primary   TEXT,
                acceptance_criteria TEXT,
                fm_json             TEXT
            )
        """)
        for col in ('type', 'status', 'state', 'created', 'modified'):
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_entries_{col} ON entries({col})')

        # ── edges table ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                src_uid TEXT NOT NULL,
                rel     TEXT NOT NULL,
                dst_uid TEXT NOT NULL
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_uid, rel)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_uid, rel)')

        # ── meta_status_map bridge table (3783a7cb Piece C) ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_status_map (
                type   TEXT NOT NULL,
                value  TEXT NOT NULL,
                bucket TEXT NOT NULL,
                PRIMARY KEY (type, value)
            )
        """)

        # ── FTS5 entries_fts (uid, title, body) ──
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts
            USING fts5(uid UNINDEXED, title, body)
        """)

        # ── Populate ──
        # fc114e57 store-raw invariant: core columns must reflect RAW frontmatter values,
        # never derived/laundered values from the JSONL index (which may normalise
        # stage/status via rebuild-ledger.ts or similar).  For vault/files/<uid>.md
        # entries we read the file directly and parse the raw YAML — same file read as
        # the FTS body scan, so no extra I/O.  Non-vault/files entries (capsules, tools,
        # agents) fall back to the JSONL record values which are reflection-of-frontmatter.
        entry_rows: list[tuple] = []
        edge_rows:  list[tuple] = []
        fts_rows:   list[tuple] = []

        # Per-record derivation is the shared _record_to_index_rows helper (single source
        # with freshen_one / rebuild --only) — see the module-level def above.
        all_uids = {r.get('uid') for r in records if r.get('uid')}
        declared_pairs: set[tuple[str, str]] = set()
        for r in records:
            src_u = r.get('uid')
            if not src_u: continue
            for fld in _EDGE_FIELDS:
                vls = r.get(fld)
                if not vls: continue
                if isinstance(vls, str): vls = [vls]
                if isinstance(vls, list):
                    for v in vls:
                        if isinstance(v, str) and v.strip():
                            declared_pairs.add((src_u, v.strip()))

        for rec in records:
            uid = rec.get('uid', '')
            if not uid:
                continue
            entry_row, e_rows, fts_row = _record_to_index_rows(rec, files_dir, declared_pairs, all_uids)
            entry_rows.append(entry_row)
            edge_rows.extend(e_rows)
            fts_rows.append(fts_row)

        # v1.68 ghost-prune (76ec348e) — upgraded v1.69 path-provenance (talos.director):
        # DELETE entries + edges + FTS rows for UIDs NOT in the current rebuild pass.
        # v1.69 upgrade: ghost definition = "collected-with-path-this-pass" — every
        # record in the current pass has path: stamped, so absent-from-pass ≡ no-path.
        # INSERT OR REPLACE adds/updates; this DELETE removes rows whose backing file
        # was not reachable by any collector this pass.
        # Bounded: only deletes UIDs not present in the CURRENT records set.
        current_uids = {r[0] for r in entry_rows}  # uid is the first column
        existing_uids_in_db = {
            row[0] for row in conn.execute('SELECT uid FROM entries').fetchall()
        }
        ghost_uids = existing_uids_in_db - current_uids
        if ghost_uids:
            placeholders_g = ','.join('?' * len(ghost_uids))
            ghost_list = list(ghost_uids)
            conn.execute(f'DELETE FROM entries WHERE uid IN ({placeholders_g})', ghost_list)
            conn.execute(f'DELETE FROM edges WHERE src_uid IN ({placeholders_g})', ghost_list)
            conn.execute(f'DELETE FROM entries_fts WHERE uid IN ({placeholders_g})', ghost_list)
            print(f'  ghost-prune: removed {len(ghost_uids)} fileless entries from SQLite.')

        conn.executemany(
            'INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            entry_rows,
        )
        conn.executemany('INSERT INTO edges VALUES (?,?,?)', edge_rows)
        conn.executemany('INSERT INTO entries_fts VALUES (?,?,?)', fts_rows)

        # ── Populate meta_status_map from capsule rollup declarations ──
        rollups, rollup_errors = load_meta_status_rollups(vault_root)
        for err in rollup_errors:
            print(err)
        map_rows: list[tuple[str, str, str]] = []
        for type_name, buckets in rollups.items():
            for bucket, values in buckets.items():
                for value in values:
                    map_rows.append((type_name, value.lower(), bucket))
        # Gap-fill rows: missing rollup mappings not yet in locked capsule frontmatter.
        # Both pending proper lock-break + capsule amendment (A110 ratified 2026-06-12).
        # task:done → done (task.capsule v4.3 enforced_enums has [new,accepted,active,closed];
        #   status:done exists in the wild from pre-v4.3 era; should map to 'done' not N/A).
        # document:done → done (document.capsule v3.1 rollup has [published,archived,retired];
        #   status:done is valid terminal for documents; same gap class as task:done).
        GAP_FILL_ROWS = [
            ('task',     'done', 'done'),
            ('document', 'done', 'done'),
        ]
        map_rows.extend(GAP_FILL_ROWS)
        if map_rows:
            conn.executemany('INSERT OR REPLACE INTO meta_status_map VALUES (?,?,?)', map_rows)
        print(f'  meta_status_map: {len(map_rows)} rows from {len(rollups)} capsule rollup(s) '
              f'(+ {len(GAP_FILL_ROWS)} gap-fill rows pending capsule lock-break).')

        # ── meta_status VIEW — Piece D (v1.66 S2 4acf3f2d): COALESCE-of-JOINs ──
        # Precedence: lifecycle > status > stage > lifecycle-N/A.
        # NEVER raw COALESCE fallthrough — emits ONLY {to-do,in-progress,done,standing,lifecycle-N/A}.
        # No CASE literals (no raw leak); no state branch (DISAMBIGUATE stream owns state, 4bd03620).
        # v1.68 S1 — lifecycle JOIN now generic (A108 lean per M2 residual analysis):
        # standing/evergreen fire as 'standing' regardless of type — no per-capsule map rows
        # needed. COALESCE: generic-lifecycle-case → typed-status-map → typed-stage-map → N/A.
        # DROP+CREATE (not IF NOT EXISTS) so the fix applies on every rebuild.
        conn.execute("DROP VIEW IF EXISTS meta_status")
        conn.execute("""
            CREATE VIEW meta_status AS
            SELECT e.uid, e.type, e.title,
                   COALESCE(
                     CASE WHEN lower(json_extract(e.fm_json, '$.lifecycle'))
                               IN ('standing', 'evergreen')
                          THEN 'standing'
                     END,
                     ms.bucket,
                     st.bucket,
                     'lifecycle-N/A'
                   ) AS meta_status,
                   e.status, e.state, e.stage, e.created, e.modified
            FROM entries e
            LEFT JOIN meta_status_map ms
                   ON ms.type = e.type
                  AND lower(ms.value) = lower(e.status)
            LEFT JOIN meta_status_map st
                   ON st.type = e.type
                  AND lower(st.value) = lower(e.stage)
        """)

        # (B5 2026-06-09: transitional meta_stage compat view DROPPED — Metis's L2
        #  cutover verified complete; tropo-ai reads meta_status, 0 meta_stage refs.
        #  Vocabulary is now single: meta_status only. 8affeac0.)

        conn.commit()
        n_entries = len(entry_rows)
        n_edges   = len(edge_rows)
        print(f'Wrote {sqlite_path.name} ({n_entries} entries, {n_edges} edges, {len(fts_rows)} FTS rows).')

    except Exception as exc:
        conn.close()
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise exc

    conn.close()
    os.replace(tmp_path, sqlite_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def rebuild_index(vault_root: Path, apply_writes: bool) -> int:
    """Core rebuild logic — scans sources, writes index + project-tree.

    Returns 0 on success, non-zero on failure. Importable for rebuild-vault.py wrapper.
    """
    ledger_dir = vault_root / 'vault'
    files_dir = ledger_dir / 'files'
    index_path = ledger_dir / '00-index.jsonl'
    project_tree_path = ledger_dir / '00-project-tree.jsonl'

    if not files_dir.is_dir():
        print(f'ERROR: vault/files/ not found at {files_dir}', file=sys.stderr)
        return 2

    print('=' * 70)
    print('rebuild-index.py — fast index + project-tree rebuild (v1.15.1)')
    print('Mode:', 'APPLY (writes will happen)' if apply_writes else 'DRY-RUN (no writes)')
    print(f'Vault root: {vault_root}')
    print('=' * 70)

    records: list[dict[str, Any]] = []
    errors: list[str] = []

    # Source 1: vault/files/*.md (canonical bulk)
    files = sorted(files_dir.glob('*.md'))
    for f in files:
        rec = process_file(f)
        if rec is None:
            errors.append(f'  parse failed: vault/files/{f.name}')
        else:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            records.append(rec)

    # Source 2: Studio-root *.md with uid: frontmatter (v1.15.1 Stream G)
    studio_root_records = collect_studio_root_records(vault_root)
    records.extend(studio_root_records)

    # Source 3: .tropo/capsules/*.capsule.md with uid: frontmatter (v1.51 Argus A80 2026-05-23)
    # First-class capsule UID queryability per Mike-A80 "fix it right" doctrine.
    capsule_records = collect_capsule_records(vault_root)
    records.extend(capsule_records)

    # Source 4: agents/**/*.md with uid: frontmatter (v1.51 Argus A80 2026-05-23)
    # First-class agents/ substrate queryability — closes the b2c4f01e roadmap finding
    # the dev-spec validator surfaced after capsule indexing fix.
    agents_records = collect_agents_records(vault_root)
    records.extend(agents_records)

    # Source 5: vault/tools/ .py/.md/.json (v1.56 E.1 Talos T10 2026-05-27)
    # First-class vault/tools/ indexing per tool.capsule v1.6 §2.5 single-file-truth.
    vault_tools_records = collect_vault_tools_records(vault_root)
    records.extend(vault_tools_records)

    # Source 6: vault/actions/ .md/.json (v1.60 Lane A-migrate Talos T10 2026-05-29)
    # First-class vault/actions/ indexing per Pillar 1 single-file-truth pattern.
    vault_actions_records = collect_vault_actions_records(vault_root)
    records.extend(vault_actions_records)

    # Source 7: vault/session-agents/ .md (v1.61 Lane S-migrate Talos T11 2026-05-29)
    # First-class vault/session-agents/ indexing per session-agent.capsule v1.6 §2.5
    # single-file-truth pattern. Session-agent class definitions live at
    # vault/session-agents/<uid>.md; each carries YAML frontmatter.
    vault_session_agents_records = collect_vault_session_agents_records(vault_root)
    records.extend(vault_session_agents_records)

    # Source 8: vault/agents/ .md (v1.69 P0.6 Talos T14 2026-06-11)
    # First-class vault/agents/ indexing per agent.capsule v2.0 unified-entry shape.
    # Unified agent entries live at vault/agents/<uid>.md (type:agent); created by the
    # v1.69 per-agent migration. Directory may be absent pre-migration — skip silently.
    vault_agents_records = collect_vault_agents_records(vault_root)
    records.extend(vault_agents_records)

    # Source 9: vault/playbooks/ .md (v1.69 P0.6 Talos T14 2026-06-11)
    # First-class vault/playbooks/ indexing per playbook.capsule unification.
    # Unified playbook entries live at vault/playbooks/<uid>.md (type:playbook); created
    # by the v1.69 S2 move. Directory may be absent pre-migration — skip silently.
    vault_playbooks_records = collect_vault_playbooks_records(vault_root)
    records.extend(vault_playbooks_records)

    print(f'\nFiles scanned (vault/files/): {len(files)}')
    print(f'Studio-root records (Stream G): {len(studio_root_records)}')
    print(f'Capsule records (v1.51 first-class): {len(capsule_records)}')
    print(f'Agents records (v1.51 first-class): {len(agents_records)}')
    print(f'Vault/tools records (v1.56 E.1): {len(vault_tools_records)}')
    print(f'Vault/actions records (v1.60 A-migrate): {len(vault_actions_records)}')
    print(f'Vault/session-agents records (v1.61 Lane S-migrate): {len(vault_session_agents_records)}')
    print(f'Vault/agents records (v1.69 P0.6): {len(vault_agents_records)}')
    print(f'Vault/playbooks records (v1.69 P0.6): {len(vault_playbooks_records)}')
    print(f'Total records parsed: {len(records)}')
    print(f'Parse failures: {len(errors)}')
    if errors:
        for e in errors[:10]:
            print(e)

    # v1.69 path-provenance: compute purge list — UIDs in the LIVE DB not collected
    # by any collector this pass (true ghosts; no backing file reachable). These will
    # be ghost-pruned from SQLite on --apply but are listed here BEFORE deletion so
    # Argus can adjudicate (verify-before-destroy per T13/T14 precedent).
    sqlite_path_live = vault_root / 'vault' / '00-index.sqlite'
    purge_candidates: list[str] = []
    if sqlite_path_live.exists():
        try:
            _conn_live = sqlite3.connect(str(sqlite_path_live))
            existing_db_uids = {row[0] for row in _conn_live.execute('SELECT uid FROM entries').fetchall()}
            _conn_live.close()
            current_pass_uids = {rec.get('uid') for rec in records if rec.get('uid')}
            purge_candidates = sorted(existing_db_uids - current_pass_uids)
        except Exception as _exc:
            print(f'  WARN: could not compute purge candidates: {_exc}', file=sys.stderr)

    if purge_candidates:
        print(f'\n[PURGE-LIST] {len(purge_candidates)} UIDs in live DB not collected this pass '
              f'(will be ghost-pruned on --apply; DO NOT delete without adjudication):')
        for _uid in purge_candidates:
            print(f'  {_uid}')
    else:
        print('\n[PURGE-LIST] empty — live DB matches rebuilt records (no true ghosts).')

    existing_count = 0
    if index_path.exists():
        with index_path.open() as f:
            existing_count = sum(1 for line in f if line.strip())

    print(f'Existing index records: {existing_count}')
    print(f'New index records:      {len(records)}')

    project_tree = build_project_tree(records)
    print(f'Project tree records: {len(project_tree)}')

    if apply_writes:
        tmp_path = index_path.with_suffix('.jsonl.tmp')
        with tmp_path.open('w') as f:
            for rec in records:
                f.write(json.dumps(rec, separators=(',', ':')) + '\n')
        os.replace(tmp_path, index_path)
        print(f'\nWrote {index_path.relative_to(vault_root)} ({len(records)} records).')

        tmp_pt = project_tree_path.with_suffix('.jsonl.tmp')
        with tmp_pt.open('w') as f:
            for node in project_tree:
                f.write(json.dumps(node, separators=(',', ':')) + '\n')
        os.replace(tmp_pt, project_tree_path)
        print(f'Wrote {project_tree_path.relative_to(vault_root)} ({len(project_tree)} nodes).')
    else:
        print('\nDRY-RUN complete. Re-run with --apply to write the index + project tree.')

    # ── SQLite index (fc114e57 Studio Query Runtime) ──
    # Same pass as JSONL; atomic (temp+swap); raw values; JSONL kept as L1 floor.
    try:
        build_sqlite_index(vault_root, records, apply_writes)
    except Exception as exc:
        print(f'WARN: SQLite index build failed (JSONL canonical is intact): {exc}', file=sys.stderr)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Rebuild vault/00-index.jsonl + 00-project-tree.jsonl (fast; v1.15.1; v1.30.0 Stream B auto-invoke rehydrate).',
    )
    parser.add_argument('--apply', action='store_true',
                        help='Write changes (default is dry-run preview).')
    parser.add_argument('--vault-path', metavar='PATH',
                        help='Explicit vault root (must contain vault/ + .tropo/).')
    parser.add_argument('--skip-rehydrate', action='store_true',
                        help='Skip auto-invoke of rehydrate.py at end of --apply '
                             '(v1.30.0 Stream B opt-out; default behavior is auto-invoke). '
                             'Use when a downstream caller (rebuild-vault.py) handles rehydrate '
                             'separately, or for CI splitting.')
    parser.add_argument('--only', metavar='UID',
                        help='Incremental freshen: re-derive + upsert ONLY this entry into the '
                             'live vault/00-index.sqlite (row + outbound edges + FTS), no full '
                             'rebuild. Non-authoritative + self-healing per fc114e57 v1.6 '
                             '(brief d7b3f1a9 §4 — the L2 cockpit-reflect-on-edit gate).')
    args = parser.parse_args()

    vault = resolve_vault_root(args.vault_path)
    if vault is None:
        print('ERROR: Could not resolve vault root.', file=sys.stderr)
        print('Pass --vault-path <path> with an absolute path to a vault containing vault/ + .tropo/.',
              file=sys.stderr)
        return 2

    # rebuild --only <uid>: incremental single-entry freshen; bypasses the full rebuild path.
    if args.only:
        return freshen_one(args.only, vault)

    rebuild_rc = rebuild_index(vault, args.apply)
    if rebuild_rc != 0:
        return rebuild_rc   # index rebuild itself failed; existing exit code 1

    # v1.30.0 Stream B: auto-invoke rehydrate.py at end of --apply mode unless
    # --skip-rehydrate was set. Per spec afd811dd v0.3 §3.1.
    if args.apply and not args.skip_rehydrate:
        if not REHYDRATE.exists():
            print(f'\nWARNING: {REHYDRATE} not found; skipping auto-invoke of rehydrate.py.',
                  file=sys.stderr)
            return 0
        print('\n[Stream B auto-invoke] Running rehydrate.py...')
        rehydrate_cmd = [sys.executable, str(REHYDRATE), '00-tropo-nav',
                         '--vault-path', str(vault)]
        try:
            rehydrate_result = subprocess.run(
                rehydrate_cmd, cwd=str(vault), timeout=120
            )
        except subprocess.TimeoutExpired:
            print('  ✗ rehydrate.py timed out after 120s; substrate may be in inconsistent state.',
                  file=sys.stderr)
            return 7
        if rehydrate_result.returncode != 0:
            print(f'  ✗ rehydrate.py FAILED (exit code {rehydrate_result.returncode}) — '
                  f'index rebuild succeeded but rehydrate did not; substrate is in inconsistent state.',
                  file=sys.stderr)
            return 6
        print('  ✓ rehydrate.py succeeded')

    return 0


if __name__ == '__main__':
    sys.exit(main())

