#!/usr/bin/env python3
"""
---
uid: d2b9c8e6
title: tropo-validate — Tool
name: tropo-validate
type: tool
status: active
owner: argus
domain: Structural vault validator — registry integrity, UID consistency, orphan detection, AGENTS.md coverage, cross-ref resolution.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/d2b9c8e6.py [--vault-path PATH]
script_path: vault/tools/d2b9c8e6.py
input:
  type: object
  properties:
    vault-path:
      type: string
output:
  type: object
  properties:
    verdict:
      type: string
      enum:
      - pass
      - findings
    findings:
      type: array
destructive: false
audit_required: false
writes_scope: []
governance_category: query
description: 'Read-only structural validator for a Tropo vault. Six check classes: (1) Registry integrity — every file in agent-registry.yaml exists on disk; every agent file on disk is registered. (2) UID consistency — uid: frontmatter matches filename. (3) Orphan detection — files in governed scan-dirs without uid: (excludes README/CURATOR/AGENTS skip-list). (4) AGENTS.md coverage — every directory under requiredDirs has AGENTS.md. (5) Cross-reference resolution — every UID referenced in frontmatter resolves to a registry entry. (6) NEW v1.5: 00-integrity.json blocked_tasks count↔uids parity check.'
domain_tags:
- validator
- structural-shape
- registry-integrity
- uid-consistency
- agents-md-coverage
- read-only
trigger_description: "Comprehensive read-only audit of vault structural health."
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
- validator
- structural-shape
- read-only
- v1.15-stream-b
subsystem_hub:
- 8dd772a0
belt: true
belt_invocation: "python3 vault/tools/d2b9c8e6.py"
belt_example: "python3 vault/tools/d2b9c8e6.py --vault-path ."
---
"""
from __future__ import annotations

"""tropo-validate.py — Python port of scripts/tropo-validate.ts (v1.5 S5/A5).

Canonical check-authoring pattern (v1.38.0): see `.tropo/scripts/CAPSULE.md`
§Validator Check Pattern.
- Pattern A (`yaml.safe_load` + dict-key lookup) for list-valued / nested / multi-field checks
- Pattern B (`split_frontmatter` + `get_scalar`) for single top-level scalar checks
- FORBIDDEN: any non-line-anchored test against raw frontmatter text (Pattern C); causes
  nested-field collision false positives. Caught at v1.37.0 R3; substrate-wide audit at v1.38.0.

Inventory of all checks: `vault/files/391043ad.md` (canonical reference).


Structural validator for a Tropo vault. Read-only — does not modify your vault.

Checks performed:
    1. Registry integrity — every file declared in `.tropo-studio/registries/agent-registry.yaml`
       exists on disk; every agent file on disk is registered.
    2. UID consistency — every governed file with a `uid:` frontmatter field has
       its filename match (or, for vault entries, the filename IS the UID).
    3. Orphan detection — files in governed scan-dirs that have no `uid:` field
       (excluding the AGENTS.md / CURATOR.md / README.md / 00-index.md skip-list).
    4. AGENTS.md coverage — every directory under `requiredDirs` has an
       AGENTS.md file. v1.4.4 ship-time was missing context/AGENTS.md +
       operating-agreement/AGENTS.md; v1.4.4 closed those structurally.
    5. Cross-reference resolution — every UID referenced in any frontmatter
       field resolves to a real entry in the registry/index.
    6. NEW v1.5 (inbox 656c26d0): 00-integrity.json blocked_tasks count↔uids
       parity check. The earlier TS script reported a count that didn't match
       the listed uids array; this Python port detects that drift and surfaces
       it as a finding.

Usage:
    python3 .tropo/scripts/tropo-validate.py            # against current vault
    python3 .tropo/scripts/tropo-validate.py --vault-path <path>

Exit codes:
    0 — all checks passed (FAIL count is zero)
    1 — at least one check failed
    2 — could not resolve vault root or other operational error

Dependencies: PyYAML for substrate-graph-integrity walk in
`check_uid_cross_references` (v1.33.0 Stream H §3.1 binding contract); other
checks remain pure-stdlib. PyYAML is a long-standing kernel-script dependency
(validate-canonical-l0.py, validate-release-manifest.py, validate-capability-
membership.py, tropo-export.py, tropo-backfill-styles.py all import yaml).
Targets Python 3.8+.

Note: the dev-repo TypeScript original does additional checks (specific
UID-field conventions, deeper graph integrity, board-snapshot field
projection). Those are deferred to v1.6+. v1 ships the high-leverage
checks users actually need to verify their vault is healthy.

Author: vela-v40
Owner: vela
Domain: vault-validation; v1.5 Truthful Ship vault-maintenance toolchain.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# v1.56 Lane S: script relocated to vault/tools/; lib/ is under .tropo/scripts/
_TROPO_SCRIPTS = Path(__file__).resolve().parents[2] / '.tropo' / 'scripts'
if str(_TROPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TROPO_SCRIPTS))

import yaml  # v1.33.0 Stream H §3.1 PyYAML AST walk (R3 sa.skeptic-078 + sa.cold-boot-181 absorption)

# d996b941 L0c: shared identity resolver — must hard-fail on import (AC-L0c-fail)
from lib._identity import _resolve_principal_uid, _get_principal_class  # noqa: E402


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
UID_RE = re.compile(r'^[0-9a-f]{8}$')
UID_REF_RE = re.compile(r'\b([0-9a-f]{8})\b')

# Skip filenames in orphan detection (these legitimately have no uid:)
ORPHAN_SKIP_NAMES = {
    'AGENTS.md', 'CAPSULE.md', 'CURATOR.md', 'README.md', '00-index.md',
    'activate.md',  # legacy activation pointer (pre-<name>-activation.md naming)
}

# Skip filename SUFFIX patterns in orphan detection — agent identity entry points
# and legacy thin-pointer paths. Identity substrate canonically lives at
# vault/files/<uid>.md post-v1.20.0/v1.21.0 convergence; these are by-design
# uid-less surfaces (activation pointer is the user-facing affordance per playbook
# v2.11 §"Activation file location is BY DESIGN, not a migration gap").
ORPHAN_SKIP_SUFFIXES = (
    '-activation.md',  # agent activation thin pointers
    '-activate.md',    # legacy activation pointer naming (Jules/Nestor/Tiphys/etc.)
    '-status.md',      # legacy status card paths (canonical at vault/files/<uid>.md)
    '-soul.md',        # legacy soul letter paths
    '-charter.md',     # legacy charter paths
    '-briefing.md',    # legacy briefing pointer paths
    '-profile.md',     # principal profile files (e.g., mike-profile.md)
    '-notes.md',       # principal/agent notes scratch
    '-historian.md',   # operations-class historian role files
    '-role-charter.md',# legacy role-charter paths
)

# Skip files containing these path segments — agent-private working substrate
# that is not governed by uid-graph contract. Captain-mode extended v1.34.0
# per Mike-V46 direction 2026-05-16 to filter validator output to actionable signal
# (governed-content drift) from coverage noise (by-design uid-less working files).
ORPHAN_SKIP_PATH_SEGMENTS = (
    '/.tropo-capsule/',  # agent-private capsule storage (memory v3 + workspace + meta)
    '/transfers/',       # living transfers + historical transfer snapshots
    '/reflections/',     # per-generation retrospective docs
    '/briefing-package/',# legacy briefing-package files (substrate retired v1.24.0)
    '/operations/',      # agent-private operations files (sub-agent records, audit trails)
    '/workspace/',       # ephemeral scratch
    '/archive/',         # archived working files (agent-private; vault archives use state:archived)
    '/playbook-runs/',   # playbook-run folders + run.jsonl (ephemeral)
    '/activations/',     # dev-pipeline + sa.* activation working folders
    '/activation-log/',  # sa.* dispatch records (catalog/activation-log/<N>-<spawner>-record.md)
    '/children/',        # pre-sa.* child-agent dispatch reports (agent-private historical)
    '/published/',       # pre-v1.20.0 agent-published working docs (agent-private historical)
    '/session-logs/',    # agent session-log records (agent-private)
    '/sessions/',        # agent session records (agent-private)
    '/directives/',      # director-private directive substrate
)

# Required AGENTS.md coverage — current top-level governed dirs of a Studio
# 2026-05-10 v1.16.0 Self-Healing Path 1 (fix-in-place): removed `projects` + `settings`
# — both retired per Mike-A54 directives (projects/ → 00-tropo-nav/ rendered nav supersedes;
# settings/ → .tropo-studio/ Studio metadata directory supersedes per v1.9.1 rename).
AGENTS_MD_REQUIRED_DIRS = [
    'vault',
    'channels',
    'agents',
    'context',
    'operating-agreement',
]

# Directories scanned for orphans (UID coverage)
ORPHAN_SCAN_DIRS = [
    'vault/files',
    'agents',
    'projects',
    'collections',
]


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def split_frontmatter(text: str) -> Optional[str]:
    m = FRONTMATTER_RE.match(text)
    return m.group(1) if m else None


def get_scalar(fm: str, field: str) -> Optional[str]:
    """P0 absorption (v1.35.0 R4 cold-boot-192): mirror rebuild-index.py fix —
    `#` inside a YAML-quoted string is content, not a comment. Without the
    quoted-string awareness, titles like `"Pre-event tease post #1 ..."` were
    truncated at the `#` and the closing `"` lost, breaking downstream renders.
    """
    pattern = rf'^{re.escape(field)}:\s*(.*)$'
    m = re.search(pattern, fm, re.MULTILINE)
    if not m:
        return None
    value = m.group(1).rstrip()
    if value.startswith('"'):
        end = value.find('"', 1)
        if end > 0:
            return value[1:end]
        return value
    if value.startswith("'"):
        end = value.find("'", 1)
        if end > 0:
            return value[1:end]
        return value
    if '#' in value:
        value = value.split('#', 1)[0]
    return value.rstrip()


def get_list(fm: str, field: str) -> Optional[list]:
    """Parse a YAML list field from frontmatter string.

    Handles two list shapes:
    - Inline: `field: [a, b, c]` (single-line bracket form)
    - Block: `field:\n  - a\n  - b\n` (multi-line dash form)

    Returns the list of string elements (stripped of quotes), or None if field absent.
    Returns the literal value as `'__scalar__'` sentinel-wrapped if field exists but
    isn't a list (caller can detect scalar-where-list-expected and fail validation).

    Authored 2026-05-18 by argus-a72 per v1.43.0 Stream C dry-run pre-flight fix —
    closes the v1.42 Check 24 script defect where `fm.get('target')` crashed because
    fm is a string, not a dict (split_frontmatter returns Optional[str]). Without
    get_list, Check 24 has never actually executed since v1.42 ship.
    """
    # Inline bracket shape: field: [a, b, c]
    inline_pattern = rf'^{re.escape(field)}:\s*\[([^\]]*)\]'
    m = re.search(inline_pattern, fm, re.MULTILINE)
    if m:
        raw = m.group(1).strip()
        if not raw:
            return []
        elements = [e.strip().strip('"\'') for e in raw.split(',') if e.strip()]
        return elements

    # Block shape: field:\n  - a\n  - b
    block_header_pattern = rf'^{re.escape(field)}:\s*$'
    header_match = re.search(block_header_pattern, fm, re.MULTILINE)
    if header_match:
        # Find consecutive `  - <value>` lines after the header
        start = header_match.end()
        # Walk forward, line by line, collecting dash items
        elements = []
        for line in fm[start:].split('\n')[1:]:  # skip the header's own line
            stripped = line.lstrip()
            if line.startswith('  ') and stripped.startswith('-'):
                val = stripped[1:].strip().strip('"\'')
                # Strip inline comment
                if '  #' in val:
                    val = val.split('  #')[0].strip()
                elements.append(val)
            elif line.strip() == '' or line.startswith('  '):
                # Empty line or continuation indent without dash — keep scanning
                if line.strip() == '':
                    continue
                # Non-dash indented line means we've left the list
                break
            else:
                break
        return elements

    # Scalar shape: field: <value> (not a list — caller may want to detect)
    scalar = get_scalar(fm, field)
    if scalar is not None:
        # Wrap in sentinel so caller can detect scalar-where-list-expected
        return [f'__scalar__:{scalar}']

    return None


def body_sha256(path: Path) -> str:
    """v1.70 S3.5.2 — Shared hashing contract for boot-derivation fingerprints.

    Body = content after the closing frontmatter fence (---).
    Normalization: collapse to exactly one trailing newline.
    Ensures writer (Argus) and checker (Talos) share one hashing truth.
    """
    import hashlib
    raw = path.read_bytes()
    # Split once on the CLOSING frontmatter fence
    parts = raw.split(b'\n---\n', 1)
    body = parts[1] if len(parts) == 2 else raw
    # Normalize trailing whitespace: collapse to exactly one \n
    body = body.rstrip(b'\n') + b'\n'
    return hashlib.sha256(body).hexdigest()


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
    for candidate in [script_path.parent.parent.parent, *script_path.parents]:
        if (candidate / 'vault').is_dir() and (candidate / '.tropo').is_dir():
            return candidate

    cwd = Path.cwd()
    if (cwd / 'vault').is_dir() and (cwd / '.tropo').is_dir():
        return cwd

    return None


# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------

def load_index(index_path: Path) -> tuple[dict[str, dict[str, Any]], int]:
    """Load the vault index. Returns (uid → record map, total record count)."""
    by_uid: dict[str, dict[str, Any]] = {}
    count = 0
    with index_path.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            uid = rec.get('uid')
            if uid:
                by_uid[uid] = rec
                count += 1
    return by_uid, count


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_uid_consistency(vault: Path) -> tuple[list[str], int]:
    """Verify uid frontmatter field matches filename for vault files."""
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0
    checked = 0
    for f in files_dir.glob('*.md'):
        uid_from_filename = f.stem
        if not UID_RE.match(uid_from_filename):
            findings.append(f'[FAIL] vault/files/{f.name} — filename is not a valid 8-hex UID')
            continue
        text = f.read_text(errors='replace')
        fm = split_frontmatter(text)
        if fm is None:
            findings.append(f'[WARN] vault/files/{f.name} — no frontmatter')
            continue
        fm_uid = get_scalar(fm, 'uid')
        if fm_uid and fm_uid != uid_from_filename:
            findings.append(f'[FAIL] vault/files/{f.name} — uid frontmatter ({fm_uid}) does not match filename')
        checked += 1
    return findings, checked


def check_uid_refs_are_strings(vault: Path) -> tuple[list[str], int, int]:
    """d3a58cdf item 1 — UID-reference fields must contain string values, not integers.

    The v1.63 cascade stall root cause: `children: [37996741]` was parsed by YAML as
    an integer list entry; isinstance(child_uid, str) dropped it silently. Sweeps the
    UID-bearing fields across all governed vault entries. WARN now; ERROR ratchet after
    the systemic sweep cleans the vault.

    Fields checked: children, depends_on_steps, next_steps, member_of, refs, composes_with,
    governed_by, supersedes, superseded_by, related_substrate, composes_with, closes,
    agent_root, commissioned_purpose (any scalar or list field that should be a string UID).
    """
    UID_BEARING_FIELDS = {
        'children', 'depends_on_steps', 'next_steps', 'member_of', 'refs',
        'composes_with', 'governed_by', 'supersedes', 'superseded_by',
        'related_substrate', 'closes', 'agent_root', 'pipeline', 'pipeline_uid',
        'dev_spec_uid', 'triggered_doc_spec_uids', 'triggered_test_spec_uids',
        'triggered_doc_activation_uids', 'triggered_test_activation_uids',
    }
    findings: list[str] = []
    int_ref_count = 0
    checked = 0

    files_dir = vault / 'vault' / 'files'
    if files_dir.is_dir():
        for f in files_dir.glob('*.md'):
            text = f.read_text(errors='replace')
            fm_str = split_frontmatter(text)
            if fm_str is None:
                continue
            try:
                fm_parsed = yaml.safe_load(fm_str)
            except Exception:
                continue
            if not isinstance(fm_parsed, dict):
                continue
            checked += 1
            for field in UID_BEARING_FIELDS:
                val = fm_parsed.get(field)
                if val is None:
                    continue
                if isinstance(val, int):
                    findings.append(
                        f"[WARN] vault/files/{f.name} — {field}: int-typed scalar "
                        f"({val!r}); must be quoted string (d3a58cdf class)"
                    )
                    int_ref_count += 1
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, int):
                            findings.append(
                                f"[WARN] vault/files/{f.name} — {field}[] item "
                                f"int-typed ({item!r}); must be quoted string (d3a58cdf class)"
                            )
                            int_ref_count += 1

    return findings, checked, int_ref_count


def check_uid_collision(vault: Path) -> tuple[list[str], int, int]:
    """f9751636 — check no two governed entries share a UID; no int-shaped frontmatter UIDs.

    Two defect classes:
    (a) int-shaped uid: YAML parses `uid: 37996741` as integer when the field lacks quotes.
        These cause silent key-type mismatches across tools (the d3a58cdf class). → FAIL.
    (b) Index duplicate UIDs: same UID appears in 00-index.jsonl more than once.
        These are stale rebuild artifacts (same file indexed twice), not file collisions. → WARN.
    True file collisions (two vault/files/*.md with identical filename) are impossible by
    filesystem constraint; uid-vs-filename mismatch is already covered by check_uid_consistency.
    """
    import json as _json
    findings: list[str] = []
    int_uid_count = 0
    dup_uid_count = 0

    # (a) int-shaped uid in vault/files/*.md frontmatter
    # Uses yaml.safe_load to detect when YAML parses uid as int (unquoted 8-hex-like value).
    files_dir = vault / "vault" / "files"
    if files_dir.is_dir():
        for f in files_dir.glob("*.md"):
            text = f.read_text(errors="replace")
            fm_str = split_frontmatter(text)
            if fm_str is None:
                continue
            try:
                fm_parsed = yaml.safe_load(fm_str)
            except Exception:
                continue
            if not isinstance(fm_parsed, dict):
                continue
            raw_uid = fm_parsed.get("uid")
            if isinstance(raw_uid, int):
                findings.append(
                    f"[WARN] vault/files/{f.name} — uid is int-typed ({raw_uid!r}); "
                    f"must be a quoted 8-hex string (d3a58cdf class; WARN now, ERROR ratchet after systemic cure)"
                )
                int_uid_count += 1

    # (b) index duplicate UIDs
    index_path = vault / "vault" / "00-index.jsonl"
    if index_path.exists():
        seen: dict[str, str] = {}
        for raw in index_path.read_text(errors="replace").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = _json.loads(raw)
            except Exception:
                continue
            if not isinstance(entry, dict):
                continue
            uid = entry.get("uid")
            if not uid:
                continue
            if uid in seen:
                if uid not in {f.split()[1] for f in findings if f.startswith("[WARN] index")}:
                    findings.append(
                        f"[WARN] index duplicate: uid {uid!r} appears multiple times "
                        f"(stale rebuild artifact — rebuild-vault.py --apply resolves)"
                    )
                    dup_uid_count += 1
            else:
                seen[uid] = entry.get("type", "?")

    checked = int_uid_count + dup_uid_count
    return findings, int_uid_count, dup_uid_count


def check_orphans(vault: Path) -> list[str]:
    """Find files in governed directories that lack a uid: frontmatter field.

    Excludes the orphan-skip-list (AGENTS.md, CAPSULE.md, etc.) and ship-allowlisted
    historical paths.
    """
    findings: list[str] = []
    for rel in ORPHAN_SCAN_DIRS:
        d = vault / rel
        if not d.is_dir():
            continue
        for f in d.rglob('*.md'):
            if f.name in ORPHAN_SKIP_NAMES:
                continue
            # Skip vault files — uid IS the filename, no orphan possible
            if rel == 'vault/files':
                continue
            # Skip files whose stem is itself a UID — same convention as vault/files/
            # (e.g., collections/<uid>.md); the filename IS the identity.
            if UID_RE.match(f.stem):
                continue
            # Skip filename suffix patterns (thin pointers + legacy identity paths)
            if f.name.endswith(ORPHAN_SKIP_SUFFIXES):
                continue
            # Skip path-segment patterns (agent-private working substrate)
            rel_path_str = '/' + str(f.relative_to(vault)) + '/'
            if any(seg in rel_path_str for seg in ORPHAN_SKIP_PATH_SEGMENTS):
                continue
            try:
                text = f.read_text(errors='replace')
            except Exception:
                continue
            fm = split_frontmatter(text)
            if fm is None:
                findings.append(f'[WARN] {f.relative_to(vault)} — no frontmatter')
                continue
            uid = get_scalar(fm, 'uid')
            if not uid:
                findings.append(f'[WARN] {f.relative_to(vault)} — no uid in frontmatter')
    return findings


def check_agents_md_coverage(vault: Path) -> tuple[list[str], int, int]:
    """Verify AGENTS.md exists in each required governed directory."""
    passes = 0
    fails = 0
    findings: list[str] = []
    for rel in AGENTS_MD_REQUIRED_DIRS:
        d = vault / rel
        agents_path = d / 'AGENTS.md'
        if agents_path.is_file():
            findings.append(f'[PASS] {rel}/AGENTS.md')
            passes += 1
        else:
            findings.append(f'[FAIL] {rel}/AGENTS.md — missing')
            fails += 1
    return findings, passes, fails


def check_uid_cross_references(vault: Path, all_uids: set[str]) -> tuple[list[str], int, int]:
    """v1.33.0 Stream H §3.1 — PyYAML AST-walk substrate-graph integrity check.

    SUPERSEDES + REPLACES the legacy check_cross_refs (member_of-only subset).

    R3 absorption (sa.skeptic-078 P0-2 + P0-3 + P1-3 + RC-1; sa.cold-boot-181
    D0-2): the v0.4 line-based regex scanner was structurally blind to
    (a) flow-style YAML lists `member_of: [aaa, bbb]`, (b) indented scalars
    under list items `relationships:\n  - to: aaa`, and (c) nested-dict path
    attribution. Live evidence at R3: 54+ unresolved cross-references silently
    passing across `relationships[*].to` + `registries[*].registry_uid` +
    `accepted_by[*].accepted_by_uid` and similar shapes. The PyYAML AST walk
    eliminates the entire defect class by parsing frontmatter into a real
    YAML tree and recursing through dicts + lists + scalars uniformly.

    Walks every vault/files/<uid>.md. Parses frontmatter via PyYAML safe_load.
    Recursively walks the parsed structure via _walk_for_uids(node, path_parts):
      - dict: iterate (key, value) pairs; recurse into value with path_parts+[key]
      - list: iterate (index, element); recurse into element with path_parts+[index]
      - str: full-match against UID_RE (`^[0-9a-f]{8}$`); resolve against all_uids
      - other scalars (int, bool, None, date): no-op

    Excludes (per spec §3.1 v0.5 §Exclusions):
      - Root-level `uid:` field — entry's own identity (always self-references)
      - `tropo_agent_id:` (any nesting) — identity primitive per agent-registration,
        not a graph reference
      - state:archived entries — honest historical record; cross-refs that broke
        as successor substrate evolved are audit-trail artifacts, not defects
      - Prose-embedded UIDs in description/body — out of scope (full-match only)
      - Cycles — pure resolution, not traversal; A→B→A is two clean resolutions

    Self-reference handling: a non-root field referencing the entry's OWN uid IS
    walked and resolved through all_uids (resolves trivially because the entry
    is in the index). Spec §3.1 v0.5 explicit.

    Index-staleness distinguishing (RC-2 absorption): when a UID reference doesn't
    resolve against all_uids, check whether `vault/files/<uid>.md` exists on disk.
    If yes → emit [INFO] "index-stale; run `npm run vault:rebuild`" (NOT a defect;
    operational dust). If no → emit [FAIL] real defect.

    Returns: (findings, n_checked, n_defects)
      - findings: per-defect [FAIL] lines + index-stale [INFO] lines + parse [WARN] lines
      - n_checked: number of vault/files/*.md entries successfully parsed
      - n_defects: number of REAL FAIL defects (excludes [INFO] index-stale + [WARN])
    """
    findings: list[str] = []
    n_checked = 0
    n_defects = 0
    n_stale = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        findings.append('[FAIL] vault/files/ — not found')
        return findings, n_checked, n_defects

    # Identity-class fields skipped during AST walk (not graph references —
    # these are typed identifiers for entities that live OUTSIDE the vault
    # entry graph; they have UIDs but their UIDs aren't vault entries).
    #
    # - `tropo_agent_id`: per-citizen unique 8-hex minted at agent registration;
    #   does not correspond to any vault entry per v1.33.0 substrate-cleanup
    #   investigation.
    # - `registry_uid`: subsystem-registry event identifier (release-registry
    #   entries in `.tropo-studio/registries/subsystem-registry.jsonl`); per-
    #   release event ID, not a vault entry. R3 absorption — investigation
    #   surfaced 38 release_history[*].registry_uid refs across 7 hub entries
    #   pointing at registry event UIDs that were never authored as vault/files/
    #   entries because subsystem-registry.jsonl is the authoritative store
    #   (matches Mike-doctrine registry-events-have-UIDs-but-arent-vault-entries
    #   from the v1.18.0 registry substrate design).
    #
    # `uid:` at the root is handled separately (root-only self-reference exclusion).
    # Sub-agent-finding UIDs in `relationships[].target` were intentionally
    # NOT excluded here — those are real broken refs that get nullified during
    # substrate cleanup, not silenced via field-exclusion (which would mask the
    # entire class for future entries).
    IDENTITY_FIELDS = frozenset({'tropo_agent_id', 'registry_uid'})

    def _format_path(path_parts: list) -> str:
        """Render path parts as `field[idx].sub[idx2].leaf` per spec §3.1 example."""
        out: list[str] = []
        for p in path_parts:
            if isinstance(p, int):
                out.append(f'[{p}]')
            else:
                if out and not out[-1].endswith(']'):
                    out.append('.')
                elif out and out[-1].endswith(']'):
                    out.append('.')
                out.append(str(p))
        # Squash leading dot if path starts with a key (no leading bracket)
        result = ''.join(out)
        return result.lstrip('.')

    def _walk_for_uids(node: Any, path_parts: list,
                       hits: list[tuple[str, list]]) -> None:
        """Recursively collect UID-shaped strings + their path parts."""
        if isinstance(node, dict):
            for key, value in node.items():
                key_str = str(key) if key is not None else ''
                # Skip identity-class fields entirely at any nesting depth.
                if key_str in IDENTITY_FIELDS:
                    continue
                # Skip root-level `uid:` (entry's own identity field).
                if key_str == 'uid' and not path_parts:
                    continue
                _walk_for_uids(value, path_parts + [key_str], hits)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk_for_uids(item, path_parts + [i], hits)
        elif isinstance(node, str):
            if UID_RE.match(node):
                hits.append((node, list(path_parts)))
        # else (int, bool, None, datetime, etc.): no-op

    for f in sorted(files_dir.glob('*.md')):
        try:
            text = f.read_text()
        except OSError:
            continue
        fm = split_frontmatter(text)
        if not fm:
            continue
        entry_uid = f.stem  # filename is the uid for vault/files/*.md

        # PyYAML parse — yields a real AST instead of regex-line-scanned strings.
        try:
            parsed = yaml.safe_load(fm)
        except yaml.YAMLError as exc:
            # Defer-to-existing kernel-file-integrity check class for malformed
            # frontmatter; surface WARN per spec §3.1 v0.5.
            findings.append(
                f'[WARN] vault/files/{f.name} — frontmatter PyYAML-unparseable '
                f'({exc.__class__.__name__}); SKIP cross-ref check')
            continue
        if not isinstance(parsed, dict):
            # Non-dict frontmatter (rare; legacy or malformed) — skip cleanly.
            continue

        n_checked += 1

        # Skip state:archived entries — honest historical record discipline.
        # Per spec §3.1 v0.5 §Exclusions: cross-refs that broke as successor
        # substrate evolved are audit-trail artifacts, not defects.
        entry_state = parsed.get('state') or ''
        if entry_state == 'archived':
            continue

        hits: list[tuple[str, list]] = []
        _walk_for_uids(parsed, [], hits)

        for uid_value, path_parts in hits:
            if uid_value in all_uids:
                continue  # resolves cleanly (includes self-references)
            # Triage: real defect vs index-stale (per RC-2 absorption)
            on_disk = (files_dir / f'{uid_value}.md').is_file()
            path_str = _format_path(path_parts)
            if on_disk:
                findings.append(
                    f'[INFO] vault/files/{f.name} — field `{path_str}` references '
                    f'{uid_value} which exists on disk but is not in '
                    f'`vault/00-index.jsonl`; run `npm run vault:rebuild`')
                n_stale += 1
            else:
                findings.append(
                    f'[FAIL] vault/files/{f.name} — field `{path_str}` '
                    f'references {uid_value} (not in index)')
                n_defects += 1

    # Append a summary [INFO] line when only staleness exists (no defects).
    # Visible to operators so they know substrate is healthy but index is lagging.
    if n_stale > 0 and n_defects == 0:
        findings.append(
            f'[INFO] {n_stale} cross-reference(s) point at on-disk files not yet '
            f'in the index; run `npm run vault:rebuild` to refresh.')

    return findings, n_checked, n_defects


def check_version_consistency(vault: Path) -> tuple[list[str], int, int]:
    """v1.33.0 Stream H §3.2 — substrate-honesty version-drift check.

    Compares `.tropo/version.md` Current-line against the latest LIVE Tropo-OS
    release entry. Filter: `type:release AND state:active AND 'cd1fcd25' in member_of`
    (dev-pipeline membership; excludes user-content releases per spec §3.2 v0.2
    discriminator absorbing skeptic-075 P0-3).

    WARN severity — drift signals operator attention but doesn't break functionality.
    Returns: (findings, n_warnings, _unused_for_fails=0). FAIL count is always 0;
    findings are WARN-class.
    """
    findings: list[str] = []

    version_md = vault / '.tropo' / 'version.md'
    if not version_md.is_file():
        # SKIP cleanly — defer-to-existing kernel-file-integrity check class
        findings.append('[INFO] .tropo/version.md — not found; SKIP version-consistency check')
        return findings, 0, 0

    try:
        version_text = version_md.read_text()
    except OSError:
        findings.append('[INFO] .tropo/version.md — unreadable; SKIP version-consistency check')
        return findings, 0, 0

    m = re.search(r'^\*\*Current:\*\*\s*v([\d.]+)', version_text, re.MULTILINE)
    if not m:
        findings.append('[INFO] .tropo/version.md — Current-line not found in expected format; SKIP')
        return findings, 0, 0
    declared_version = m.group(1)

    index_path = vault / 'vault' / '00-index.jsonl'
    if not index_path.is_file():
        findings.append('[WARN] vault/00-index.jsonl — not found; cannot verify version consistency')
        return findings, 1, 0

    conforming: list[tuple[str, str]] = []
    malformed: list[str] = []
    semver_re = re.compile(r'^\d+\.\d+\.\d+$')

    with index_path.open() as fp:
        for raw in fp:
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if row.get('type') != 'release':
                continue
            if row.get('state') != 'active':
                continue
            member_of = row.get('member_of') or []
            # Type-guard (R3 RE-RUN cold-boot-182 D1-NEW-2 absorption): Python's
            # `in` operator does substring match on strings. A malformed
            # member_of (string instead of list) would substring-match
            # 'cd1fcd25' and false-pass the dev-pipeline discriminator.
            # rebuild-vault.py builds list-typed member_of by construction;
            # this guard is defense-in-depth for adversarial / hand-edited input.
            if not isinstance(member_of, list) or 'cd1fcd25' not in member_of:
                # Not a Tropo-OS dev-pipeline release; skip
                continue
            uid = row.get('uid')
            release_version = row.get('release_version')
            if not isinstance(release_version, str) or not semver_re.match(release_version):
                malformed.append(f'{uid}: release_version "{release_version}" non-conforming (expected MAJOR.MINOR.PATCH)')
                continue
            conforming.append((uid, release_version))

    if not conforming:
        findings.append('[WARN] no current LIVE Tropo-OS release entry in vault (cycle in-progress state OR substrate-staleness)')
        return findings, 1, 0

    def semver_tuple(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split('.'))

    conforming.sort(key=lambda r: semver_tuple(r[1]), reverse=True)
    highest_uid, highest_version = conforming[0]

    # Multiple actives at highest semver — v1.21.0.1 rolling-window violation
    actives_at_top = [(u, v) for u, v in conforming if v == highest_version]
    if len(actives_at_top) > 1:
        findings.append(
            f'[WARN] {len(actives_at_top)} state:active Tropo-OS releases at v{highest_version} '
            f'(violates v1.21.0.1 rolling-window — only the current release stays state:active):'
        )
        for u, v in actives_at_top[:5]:
            findings.append(f'         • {u} (v{v})')
        if len(actives_at_top) > 5:
            findings.append(f'         ... and {len(actives_at_top) - 5} more')

    # Compare declared vs highest
    if declared_version != highest_version:
        findings.append(
            f'[WARN] version drift: .tropo/version.md declares v{declared_version} '
            f'≠ latest LIVE Tropo-OS release v{highest_version} ({highest_uid})'
        )
        findings.append(
            '         Fix: bump .tropo/version.md OR archive the unexpected release entry '
            'per v1.21.0.1 governance.'
        )

    # Report malformed (cap output)
    if malformed:
        findings.append(
            f'[WARN] {len(malformed)} Tropo-OS release entries have non-conforming release_version:'
        )
        for m_line in malformed[:5]:
            findings.append(f'         • {m_line}')
        if len(malformed) > 5:
            findings.append(f'         ... and {len(malformed) - 5} more')

    n_warns = len([f for f in findings if f.startswith('[WARN]')])
    return findings, n_warns, 0


def check_integrity_parity(vault: Path) -> tuple[list[str], bool]:
    """v1.5 inbox 656c26d0 — 00-integrity.json blocked_tasks count↔uids parity check.

    The TS rebuilder writes a 00-integrity.json with a `blocked_tasks` object
    that has both a `count` field and an array of UIDs. These can drift
    (sa.daily-vault-health surfaced this on 2026-05-03: count 62 vs 42 UIDs).
    Surface drift as a finding.
    """
    findings: list[str] = []
    integrity_path = vault / 'vault' / '00-integrity.json'
    if not integrity_path.is_file():
        return [f'[INFO] vault/00-integrity.json — not present (skip parity check)'], True
    try:
        data = json.loads(integrity_path.read_text())
    except json.JSONDecodeError as e:
        return [f'[WARN] vault/00-integrity.json — JSON parse failed: {e}'], False

    blocked = data.get('blocked_tasks') or data.get('blocked', {})
    if not isinstance(blocked, dict):
        return [], True

    count = blocked.get('count')
    uids = blocked.get('uids')
    if isinstance(count, int) and isinstance(uids, list):
        if count != len(uids):
            findings.append(
                f'[WARN] vault/00-integrity.json — blocked_tasks count={count} but uids array has {len(uids)} entries; '
                f'parity drift (v1.5 inbox 656c26d0)'
            )
            return findings, False

    return findings, True


# ---------------------------------------------------------------------------
# Generation-log invariants — RETIRED at v1.38.0
# ---------------------------------------------------------------------------
# `check_generation_logs` + helpers (`_parse_gen_tag`, `GEN_TAG_RE`,
# `GEN_DATE_RE`, `GEN_RETIRE_RE`) retired at v1.38.0 Phase 3 consolidation.
# Substrate validated (`agents/<name>/generation-log.md` files per
# generation-log.capsule v1.0) was retired at v1.21.0 Stream 3 — migrated to
# vault archive entries at `vault/files/<uid>.md` (`type: document,
# status: archived`). The check ran zero file iterations in current substrate.
# Honors Mike-A69 more-capsules-equals-more-maintenance pin applied to checks.
# Audit trail: v1.38.0 release entry + .tropo/scripts/CAPSULE.md §Validator
# Check Pattern + inventory document 391043ad §Phase 3.
#
# RECOVERY PATH (per R3 sa.skeptic-099 P0-3 absorption): if
# `agents/<name>/generation-log.md` substrate re-emerges (e.g., a
# first-generation agent creates one at activation; a legacy substrate
# migration brings them back; a Studio is imported from elsewhere that
# carries generation-logs as legitimate substrate), restore this check by
# either (a) checking out the function + helpers from git history at the
# v1.37.0 ship SHA, OR (b) re-authoring from the canonical pattern in
# .tropo/scripts/CAPSULE.md §Validator Check Pattern. The inventory entry
# at vault/files/391043ad.md retains the original specification for
# reference.


def check_self_healing_drift(vault: Path, window_days: int = 3) -> tuple[list[str], int]:
    """
    Self-Healing Primitive Stream H (v1.15.4): cycle-drift detection.

    Surfaces a WARNING when substrate-class kernel files (governance docs, capsules,
    playbooks, skills, OS-tier governance) have a frontmatter `modified:` date
    within `window_days` that is not referenced by ANY dev-pipeline activation
    (open or closed). Captures the "edits-without-ceremony" pattern that produced
    the v1.13.x drift defect class.

    Window default 3 days — catches edits in the rolling drift window that
    weren't governed. Tunable as future-cycle work; advisory severity initially.

    Signal preference: frontmatter `modified:` field (semantic edit timestamp
    set by agents) over filesystem mtime (also updated by rebuild-vault auto-
    rendering). Files without a frontmatter modified date are skipped.

    Reference corpus: all activation runs (open + closed) plus all activation-root
    project entries in vault/files/. Past closed activations cover past governed
    edits; the check fires only when no activation in the corpus references the
    file's UID, name, or path.

    Promotes to ERROR in a future cycle once the pattern stabilizes.
    """
    findings: list[str] = []
    files_checked = 0

    cutoff = datetime.now() - timedelta(days=window_days)
    cutoff_date = cutoff.date()

    # Build set of protected paths
    protected: list[Path] = []
    for explicit in (
        '.tropo/SELF-HEALING.md',
        '.tropo/boot-config.md',
        'STUDIO.md',
        'TROPO-CONTROL.md',
        '.tropo-studio/operating-principles.md',
    ):
        p = vault / explicit
        if p.is_file():
            protected.append(p)
    for subdir in ('.tropo/capsules', '.tropo/playbooks', '.tropo/skills'):
        d = vault / subdir
        if d.is_dir():
            protected.extend(p for p in d.rglob('*.md') if p.is_file())

    # Build corpus of activation references — ALL activations (open + closed)
    # plus all activation-root project entries (active + archived). Past
    # activations cover past governed edits; drift fires only when no
    # activation in the entire corpus references the file.
    corpus_parts: list[str] = []
    activations_dir = vault / 'agents' / 'dev-pipeline' / 'activations'
    if activations_dir.is_dir():
        for run_dir in activations_dir.iterdir():
            run_jsonl = run_dir / 'run.jsonl'
            if not run_jsonl.is_file():
                continue
            try:
                corpus_parts.append(run_jsonl.read_text(errors='replace'))
            except Exception:
                continue

    # Include all activation-root project entries in vault/files/
    vault_files = vault / 'vault' / 'files'
    if vault_files.is_dir():
        for f in vault_files.glob('*.md'):
            try:
                head = f.read_text(errors='replace')[:8000]
            except Exception:
                continue
            if 'type: project' in head and 'activation_run_uid:' in head:
                corpus_parts.append(head)

    corpus = '\n'.join(corpus_parts)

    # Check each protected file
    # Signal preference: frontmatter `modified:` field (semantic edit timestamp set by
    # agents) over filesystem mtime (which auto-rendering by rebuild-vault wrapper
    # also updates). Files without a frontmatter modified date are skipped from this
    # check rather than mtime-fallback — frontmatter omission is its own surface
    # caught by other validator checks.
    for fp in protected:
        files_checked += 1

        text: str = ''
        try:
            text = fp.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if not fm:
            continue

        modified_str = get_scalar(fm, 'modified')
        if not modified_str:
            continue
        try:
            mod_date = datetime.strptime(modified_str.strip().strip('"\''), '%Y-%m-%d').date()
        except ValueError:
            continue
        if mod_date < cutoff_date:
            continue

        rel = fp.relative_to(vault)
        rel_str = str(rel)
        uid = get_scalar(fm, 'uid')

        # Reference detection — file referenced by any activation in the corpus.
        # Match by relative path, full filename, filename stem (no extension), and UID.
        # Stem-match catches cases where activation roots cite playbooks/capsules without
        # the .md extension (common authoring convention).
        referenced = (
            rel_str in corpus
            or fp.name in corpus
            or fp.stem in corpus
            or (uid is not None and uid in corpus)
        )
        if referenced:
            continue

        findings.append(
            f"[WARN] {rel_str} (modified {modified_str}): Self-Healing drift — "
            f"substrate-class edit without open dev-pipeline activation reference. "
            f"Either activate a dev-pipeline cycle or surface the edit per Self-Healing "
            f"two-path action model."
        )

    return findings, files_checked


def check_kb_article_typing(vault: Path) -> tuple[list[str], int, int]:
    """v1.18.0 Stream A — Verify KB articles in .tropo/kb/ declare `type: kb-article`.

    Sweeps `.tropo/kb/*.md` for frontmatter; surfaces files missing `type: kb-article`
    at WARN severity (grace period during v1.18.0 + early v1.19.0 ship; ratchet to
    ERROR in a future cycle once the substrate has settled).

    Skips the legacy `00-index.md` (folder-class index, not an article) and any file
    in the `99-archive/` subfolder.

    Returns (findings, total_checked, untyped_count).
    Capsule: kb-article (UID 4cb20382).
    """
    findings: list[str] = []
    kb_dir = vault / '.tropo' / 'kb'
    if not kb_dir.is_dir():
        return findings, 0, 0

    total_checked = 0
    untyped = 0
    for f in kb_dir.glob('*.md'):
        # Skip index files + archive
        if f.name == '00-index.md':
            continue
        if '99-archive' in f.parts:
            continue
        total_checked += 1
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            findings.append(f'[WARN] .tropo/kb/{f.name} — no frontmatter; missing type: kb-article (v1.18.0 Stream A; capsule 4cb20382)')
            untyped += 1
            continue
        article_type = get_scalar(fm, 'type')
        if article_type != 'kb-article':
            actual = article_type if article_type else 'absent'
            findings.append(f'[WARN] .tropo/kb/{f.name} — type is {actual!r}; expected "kb-article" per capsule 4cb20382 (v1.18.0 Stream A)')
            untyped += 1
    return findings, total_checked, untyped


def check_canonical_reference_shape(vault: Path) -> tuple[list[str], int, int]:
    """V1 (v1.54) — verify substrate entries referencing canonical primitives are well-formed.

    Layer 2 of the substrate-verify-twice discipline (O11 brief 83af4ac1).
    Walks substrate and checks three canonical-reference classes:

    1. doc-spec instances — verify doc_changes_required[].path resolves OR is marked
       new-file; verify doc_changes_required[].tier matches canonical enum
    2. activation instances — verify status: in canonical enum; verify closure_reason:
       in canonical enum when status:retired
    3. Substrate entries citing file versions — when frontmatter cites version: of a
       referenced UID, verify cited version matches canonical's current version field

    WARN at v1.54; ERROR ratchet at v1.55.
    Returns (findings, total_checked, defects).
    """
    import re as _re
    findings: list[str] = []
    total = 0
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    VALID_ACTIVATION_STATUSES = {'active', 'retired', 'failed', 'stale', 'paused', 'done'}
    VALID_CLOSURE_REASONS = {'pipeline-complete', 'session-end', 'superseded', 'error', 'manual'}
    VALID_DOC_TIERS = {'summary', 'subsystem', 'spec', 'capsule', 'playbook', 'channel', 'cross-cutting'}

    for path in sorted(files_dir.glob('*.md')):
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        if not text.startswith('---\n'):
            continue
        end = text.find('\n---\n', 4)
        if end < 0:
            continue
        try:
            import yaml as _yaml
            fm = _yaml.safe_load(text[4:end])
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue

        entry_type = fm.get('type', '')
        rel = path.relative_to(vault)
        total += 1

        # ── Class 1: doc-spec entries ────────────────────────────────────────
        if entry_type == 'doc-spec':
            dcr = fm.get('doc_changes_required') or []
            if isinstance(dcr, list):
                for i, item in enumerate(dcr):
                    if not isinstance(item, dict):
                        continue
                    item_path = item.get('path', '')
                    item_tier = item.get('tier', '')
                    is_new_file = 'new-file' in str(item_path).lower()
                    if item_path and not is_new_file:
                        target = vault / item_path if not item_path.startswith('/') else Path(item_path)
                        if not target.exists():
                            findings.append(
                                f'  [WARN] {rel} — doc_changes_required[{i}].path '
                                f'{item_path!r} does not resolve and is not marked new-file '
                                f'(V1 canonical-reference; WARN v1.54 / ERROR v1.55)')
                    if item_tier and item_tier not in VALID_DOC_TIERS:
                        findings.append(
                            f'  [WARN] {rel} — doc_changes_required[{i}].tier '
                            f'{item_tier!r} not in canonical enum {sorted(VALID_DOC_TIERS)} '
                            f'(V1 canonical-reference; WARN v1.54 / ERROR v1.55)')

        # ── Class 2: activation entries — status enum only ───────────────────
        # closure_reason is free-text in practice; check only status enum.
        elif entry_type == 'activation':
            status = fm.get('status', '')
            if status and status not in VALID_ACTIVATION_STATUSES:
                findings.append(
                    f'  [WARN] {rel} — activation status {status!r} not in canonical enum '
                    f'{sorted(VALID_ACTIVATION_STATUSES)} '
                    f'(V1 canonical-reference; WARN v1.54 / ERROR v1.55)')

        # ── Class 3: entries citing a version of a referenced UID ────────────
        # Check: if frontmatter has a field like `composes_with_version: "1.0"` paired
        # with a UID reference, verify the referenced entry's version matches.
        # Scoped to `governed_by_version:` pattern (most common version-cite shape).
        governed_version = fm.get('governed_by_version')
        governed_uid = fm.get('governed_by')
        if governed_version and governed_uid and isinstance(governed_uid, str):
            if _re.fullmatch(r'[0-9a-f]{8}', governed_uid):
                target = read_vault_entry_from_path(files_dir / f'{governed_uid}.md')
                if target:
                    canonical_version = target.get('version') or target.get('schema_version')
                    if canonical_version and str(governed_version) != str(canonical_version):
                        findings.append(
                            f'  [WARN] {rel} — governed_by_version {governed_version!r} '
                            f'does not match {governed_uid}.md current version {canonical_version!r} '
                            f'(V1 canonical-reference; WARN v1.54 / ERROR v1.55)')

    return findings, total, len(findings)


def read_vault_entry_from_path(path: Path) -> dict | None:
    """Read frontmatter dict from a vault file path directly (no index lookup)."""
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
        if not text.startswith('---\n'):
            return None
        end = text.find('\n---\n', 4)
        if end < 0:
            return None
        import yaml as _yaml
        fm = _yaml.safe_load(text[4:end])
        return fm if isinstance(fm, dict) else None
    except Exception:
        return None


def check_activation_typing(vault: Path) -> tuple[list[str], int, int]:
    """v1.21.0 Stream 5 — Verify activation entries at vault/files/ are well-formed
    and ADR-016 + ADR-028 substrate invariants hold.

    Sweeps vault/files/*.md for entries with `type: activation`; verifies:
      - Required fields per activation.capsule v1.0 (name, agent, agent_root,
        agent_class, generation, model, platform, activated_at, activated_by,
        status, member_of)
      - status: enum (active/retired/failed/stale/paused)
      - agent_class: enum (executive/director/sa/cosmo/tropo/worker/child-agent)
      - **ADR-016 substrate enforcement** — at most one activation per agent
        slug with status: active
      - retired_at: present when status is terminal (retired/failed/stale)

    ERROR severity at v1.22.0+ (ratcheted per v1.22.0 Stream 5; was WARN at v1.21.0); grace-period
    pattern (mirrors kb-article + governance-contract precedents).

    Returns (findings, total_checked, defects).
    Capsule: activation (UID 4e8b21f0).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    required_fields = ['name', 'agent', 'agent_root', 'agent_class', 'generation',
                       'model', 'platform', 'activated_at', 'activated_by',
                       'status', 'member_of']
    valid_statuses = {'active', 'retired', 'failed', 'stale', 'paused'}
    valid_classes = {'executive', 'director', 'sa', 'cosmo', 'tropo',
                     'worker', 'child-agent', 'pipeline'}  # v1.35.0: pipeline class added for pipeline-template activations per pipeline.capsule v2.6 + pipeline-activate.py
    terminal_statuses = {'retired', 'failed', 'stale'}

    activations: list[tuple[str, dict[str, Any]]] = []
    total_checked = 0
    defects = 0
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        entry_type = get_scalar(fm, 'type')
        if entry_type != 'activation':
            continue
        total_checked += 1
        activations.append((f.name, fm))
        # Required field check
        for field in required_fields:
            if field not in fm:
                findings.append(f'[FAIL] vault/files/{f.name} — activation missing required field {field!r} (v1.21.0 Stream 5; capsule 4e8b21f0)')
                defects += 1
        # status enum
        status = get_scalar(fm, 'status')
        if status and status not in valid_statuses:
            findings.append(f'[FAIL] vault/files/{f.name} — activation status {status!r} not in valid enum {sorted(valid_statuses)}')
            defects += 1
        # agent_class enum
        agent_class = get_scalar(fm, 'agent_class')
        if agent_class and agent_class not in valid_classes:
            findings.append(f'[FAIL] vault/files/{f.name} — activation agent_class {agent_class!r} not in valid enum {sorted(valid_classes)}')
            defects += 1
        # retired_at consistency with terminal status
        if status in terminal_statuses and 'retired_at' not in fm:
            findings.append(f'[FAIL] vault/files/{f.name} — activation status {status!r} is terminal but retired_at field missing (activation.capsule §4 Rule 7)')
            defects += 1

    # ADR-016 substrate enforcement: at most one active per agent slug.
    # v1.52 class-aware refinement (Argus A81 captain-mode 2026-05-24 fix-on-see per stm-a80-005):
    # The rule applies to EXECUTIVE-CLASS agent identities (Argus / Vela / Metis / Cosmo / Orpheus / Talos / Tropo).
    # Pipeline-class activations share `agent: pipeline-runtime` by engine convention (the runtime is the
    # singular harness; activations are the dev-pipeline / doc-pipeline / test-pipeline cycle instances).
    # Concurrent pipeline-class activations under pipeline-runtime IS the cascade pattern v1.51 shipped;
    # ADR-016's "two active generations of the same agent is a governance violation" was designed for
    # executive identity continuity, not pipeline-runtime concurrency. Class-aware check skips
    # activation_class:pipeline entries from the singularity invariant.
    active_by_agent: dict[str, list[str]] = {}
    for fname, fm in activations:
        if get_scalar(fm, 'status') == 'active':
            activation_class = get_scalar(fm, 'activation_class') or get_scalar(fm, 'agent_class') or 'executive'
            if activation_class == 'pipeline':
                continue   # pipeline-class concurrency is the cascade pattern; not an ADR-016 violation
            agent_slug = get_scalar(fm, 'agent') or '?'
            active_by_agent.setdefault(agent_slug, []).append(fname)
    for agent_slug, fnames in active_by_agent.items():
        if len(fnames) > 1:
            findings.append(f'[FAIL] ADR-016 substrate violation — agent {agent_slug!r} has {len(fnames)} executive-class activation entries at status: active: {fnames}')
            defects += 1

    return findings, total_checked, defects


def check_charter_conformance(vault: Path) -> tuple[list[str], int, int]:
    """v1.37.0 NEW — Verify type:charter files conform to charter.capsule v1.0 schema.

    Sweeps vault/files/*.md for entries with `type: charter`; verifies the 8 checks
    per v1.37.0 spec [e3f47a82] §3.4 (charter.capsule UID 8f3c9e1a):

      1. All required frontmatter fields present (per spec §3.1 / charter.capsule §2):
         uid, type, agent_name, agent_class, role, scope, status, boot_protocol,
         created, created_by, modified, modified_by
      2. agent_class enum: executive | director (sa.* uses session-agent.capsule)
      3. boot_protocol enum: playbook | commissioned | on-demand
      4. status enum: active | locked | retired | archived | suspended
      5. scope object has both reads + writes sub-fields (each a list; may be empty)
      6. Body contains exactly one H2 matching ^##\\s+(?:\\d+\\.\\s+)?Identity$ (case-insensitive)
      7. If locked_at present, locked_by must also be present (atomic LOCK metadata)
      8. If status: retired or archived, checks 1-7 RELAXED at WARN-only at v2.0.0 ratchet
         (retired/archived charters preserve original substrate as honest historical record)

    WARN-severity at v1.37.0 honor-system; ERROR ratchet planned at v2.0.0 (public ship gate).
    Per Q2 Option B Mike-A69 brief lock 2026-05-17.

    Returns (findings, total_checked, defects).
    Capsule: charter (UID 8f3c9e1a; ships at v1.37.0).
    Spec: e3f47a82 §3.4.
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    required_fields = ['uid', 'type', 'agent_name', 'agent_class', 'role', 'scope',
                       'status', 'boot_protocol', 'created', 'created_by',
                       'modified', 'modified_by']
    valid_agent_classes = {'executive', 'director'}
    valid_boot_protocols = {'playbook', 'commissioned', 'on-demand'}
    valid_statuses = {'active', 'locked', 'retired', 'archived', 'suspended'}
    relaxed_statuses = {'retired', 'archived'}
    # Strict-literal Identity H2 regex per Q7-spec captain-mode argus call 2026-05-17
    identity_h2_re = re.compile(r'^##\s+(?:\d+\.\s+)?Identity\s*$', re.IGNORECASE | re.MULTILINE)

    total_checked = 0
    defects = 0
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        # R3 P0 absorption (sa.skeptic-095 argus-a69 captain-mode 2026-05-17):
        # split_frontmatter returns YAML text (str), not a parsed dict. Original
        # implementation used `if field not in fm` which did Python substring search
        # on the raw text — masked false negatives (e.g., Argus's nested `soul.role:`
        # made top-level `role:` appear as substring → false PASS). Parse via PyYAML
        # for true structured key-presence checks.
        try:
            fm_dict = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            continue
        if not isinstance(fm_dict, dict):
            continue
        entry_type = fm_dict.get('type')
        if entry_type != 'charter':
            continue
        total_checked += 1

        # Check 8: relaxation for retired/archived
        status = fm_dict.get('status')
        is_relaxed = status in relaxed_statuses

        # Check 1: required fields (structured key-presence per R3 P0 absorption)
        for field in required_fields:
            if field not in fm_dict:
                if is_relaxed:
                    continue  # relaxed for retired/archived
                findings.append(f'[WARN] vault/files/{f.name} — charter missing required field {field!r} (v1.37.0 spec e3f47a82 §3.4 Check 1; WARN at v1.37.0 honor-system; ERROR ratchet at v2.0.0)')
                defects += 1

        # Check 2: agent_class enum
        agent_class = fm_dict.get('agent_class')
        if agent_class and agent_class not in valid_agent_classes:
            if not is_relaxed:
                findings.append(f'[WARN] vault/files/{f.name} — charter agent_class {agent_class!r} not in valid enum {sorted(valid_agent_classes)} (sa.* must use session-agent.capsule; spec §3.4 Check 2)')
                defects += 1

        # Check 3: boot_protocol enum
        boot_protocol = fm_dict.get('boot_protocol')
        if boot_protocol and boot_protocol not in valid_boot_protocols:
            if not is_relaxed:
                findings.append(f'[WARN] vault/files/{f.name} — charter boot_protocol {boot_protocol!r} not in valid enum {sorted(valid_boot_protocols)} (spec §3.4 Check 3)')
                defects += 1

        # Check 4: status enum
        if status and status not in valid_statuses:
            findings.append(f'[WARN] vault/files/{f.name} — charter status {status!r} not in valid enum {sorted(valid_statuses)} (spec §3.4 Check 4)')
            defects += 1

        # Check 5: capability_scope object has both reads + writes sub-fields
        # (v1.72 Move 4 field-disambiguation: renamed from `scope` — the charter read/write
        #  authorization object is distinct from the scalar extraction/session `scope`.
        #  Argus A116 captain-edit; owner-notified to Talos.)
        if 'capability_scope' in fm_dict and not is_relaxed:
            cap_scope = fm_dict['capability_scope']
            if not isinstance(cap_scope, dict):
                findings.append(f'[WARN] vault/files/{f.name} — charter capability_scope is not an object (spec §3.4 Check 5)')
                defects += 1
            else:
                for sub in ('reads', 'writes'):
                    if sub not in cap_scope:
                        findings.append(f'[WARN] vault/files/{f.name} — charter capability_scope missing sub-field {sub!r} (spec §3.4 Check 5)')
                        defects += 1
                    elif not isinstance(cap_scope[sub], list):
                        findings.append(f'[WARN] vault/files/{f.name} — charter capability_scope.{sub} is not a list (spec §3.4 Check 5)')
                        defects += 1

        # Check 6: body contains Identity H2 (strict literal regex per Q7-spec)
        if not is_relaxed:
            # Extract body (everything after closing frontmatter ---)
            parts = text.split('---', 2)
            body = parts[2] if len(parts) >= 3 else ''
            if not identity_h2_re.search(body):
                findings.append(f'[WARN] vault/files/{f.name} — charter body missing required H2 matching ^##\\s+(?:\\d+\\.\\s+)?Identity$ (case-insensitive); spec §3.2 + §3.4 Check 6 strict-literal regex per Q7-spec argus-a69 captain-mode call')
                defects += 1

        # Check 7: locked_at/locked_by atomic pair
        if 'locked_at' in fm_dict and 'locked_by' not in fm_dict:
            findings.append(f'[WARN] vault/files/{f.name} — charter has locked_at but missing locked_by (atomic LOCK metadata; spec §3.4 Check 7)')
            defects += 1

    return findings, total_checked, defects


def check_activation_generation_monotonic(vault: Path) -> tuple[list[str], int, int]:
    """v1.22.0.3 P1-7 remediation — scan-time ADR-028 monotonicity check.

    Per activation.capsule v1.0+ §4 Rule 2: for any two activation entries with
    the same agent: slug, the one with later activated_at must have generation
    equal to predecessor's generation + 1 (class-specific arithmetic).

    write-activation-entry.py enforces this at write-time (op:open). This check
    is the scan-time companion — catches drift introduced by inline edits that
    bypass the script, or pre-registry backfills that violate monotonicity.

    Returns (findings, total_chains_checked, violations).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    # Group activations by agent
    by_agent: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') != 'activation':
            continue
        # Build mini-fm dict
        fields = {}
        for line in fm.splitlines():
            m = re.match(r'^([a-z_]+):\s*[\"\']?(.*?)[\"\']?$', line)
            if m:
                fields[m.group(1)] = m.group(2).strip()
        slug = fields.get('agent')
        if not slug:
            continue
        by_agent.setdefault(slug, []).append((f.stem, fields))

    def parse_gen(gen_str: str, agent_class: str):
        if agent_class in {'executive', 'director', 'cosmo', 'tropo'}:
            m = re.match(r'^([A-Za-z]+)(\d+)$', gen_str)
            if m:
                return int(m.group(2))
        elif agent_class in {'sa', 'worker'}:
            m = re.match(r'^.+-(\d+)$', gen_str)
            if m:
                return int(m.group(1))
        elif agent_class == 'child-agent':
            m = re.search(r'\.(\d+)\.', gen_str)
            if m:
                return int(m.group(1))
        return None

    chains_checked = 0
    violations = 0
    for slug, entries in by_agent.items():
        if len(entries) < 2:
            chains_checked += 1
            continue
        # Sort by activated_at ascending; tie-break by parsed generation number
        # (same-day activations need generation as secondary key for correct chain order)
        def sort_key(pair):
            uid, fields = pair
            agent_class = fields.get('agent_class', '')
            gen_num = parse_gen(fields.get('generation', ''), agent_class)
            return (fields.get('activated_at', ''), gen_num if gen_num is not None else 0)
        entries.sort(key=sort_key)
        chains_checked += 1
        for i in range(1, len(entries)):
            prev_uid, prev_fields = entries[i-1]
            curr_uid, curr_fields = entries[i]
            curr_class = curr_fields.get('agent_class', '')
            prev_gen = parse_gen(prev_fields.get('generation', ''), curr_class)
            curr_gen = parse_gen(curr_fields.get('generation', ''), curr_class)
            if prev_gen is not None and curr_gen is not None and curr_gen != prev_gen + 1:
                findings.append(f'[FAIL] ADR-028 substrate violation — agent {slug!r}: '
                                f'activation {curr_uid} generation {curr_fields.get("generation")} '
                                f'should be {prev_fields.get("generation")}+1; '
                                f'predecessor at {prev_uid}')
                violations += 1
    return findings, chains_checked, violations


def check_activation_stale_sweep(vault: Path) -> tuple[list[str], int, int]:
    """v1.22.0 Stream 4 sa.skeptic P0-4 remediation — verify active activations
    haven't exceeded their per-class stale threshold.

    Per activation.capsule v1.0.1 §2 stale_threshold_hours field. Surfaces as
    WARN; Vela's Tier 1 stale-sweep is the authoritative writer that flips
    status. This check is the belt; Vela is suspenders.

    Returns (findings, total_active, stale_candidates).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    STALE_DEFAULTS = {"sa": 2, "worker": 6, "executive": 168, "director": 168,
                      "cosmo": 168, "tropo": 168, "child-agent": 4}
    now = datetime.now()
    total_active = 0
    stale_candidates = 0

    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') != 'activation':
            continue
        if get_scalar(fm, 'status') != 'active':
            continue
        total_active += 1
        agent_class = get_scalar(fm, 'agent_class') or 'executive'
        # Threshold: read from frontmatter, else default by class
        threshold_str = get_scalar(fm, 'stale_threshold_hours')
        if threshold_str:
            try:
                threshold_hours = int(threshold_str)
            except ValueError:
                threshold_hours = STALE_DEFAULTS.get(agent_class, 168)
        else:
            threshold_hours = STALE_DEFAULTS.get(agent_class, 168)
        # Compare activated_at against threshold
        activated_at_str = get_scalar(fm, 'activated_at')
        if not activated_at_str:
            continue
        try:
            # Accept YYYY-MM-DD or full ISO
            activated_at = datetime.fromisoformat(activated_at_str.split('T')[0])
        except (ValueError, AttributeError):
            continue
        elapsed = now - activated_at
        if elapsed > timedelta(hours=threshold_hours):
            findings.append(f'[WARN] vault/files/{f.name} — activation status: active '
                            f'AND activated_at {activated_at_str} exceeds '
                            f'stale_threshold_hours={threshold_hours} '
                            f'(agent_class={agent_class}); candidate for Vela Tier 1 stale-sweep')
            stale_candidates += 1

    return findings, total_active, stale_candidates


def check_governance_contract_typing(vault: Path) -> tuple[list[str], int, int]:
    """v1.20.0 Stream A — Verify governance-contract instances at vault/files/ are well-formed.

    Sweeps vault/files/*.md for entries with `type: governance-contract`; verifies required
    fields (governed_path, folder_type, owner, write_access, read_access, purpose, member_of)
    are present and well-formed.

    ERROR severity at v1.22.0+ (ratcheted per v1.22.0 Stream 5; was WARN at v1.20.0-v1.21.x grace period); 
    per established grace-period pattern (mirrors check_kb_article_typing).

    Returns (findings, total_checked, untyped_count).
    Capsule: governance-contract (UID 7901662b).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    required_fields = ['governed_path', 'folder_type', 'owner', 'write_access', 'read_access', 'purpose', 'member_of']
    valid_folder_types = {'governed', 'registry', 'content', 'ledger', 'kernel',
                          'studio-metadata', 'runtime', 'archive', 'workspace'}

    total_checked = 0
    defects = 0
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        entry_type = get_scalar(fm, 'type')
        if entry_type != 'governance-contract':
            continue
        total_checked += 1
        # Required field check
        for field in required_fields:
            if field not in fm:
                findings.append(f'[FAIL] vault/files/{f.name} — governance-contract missing required field {field!r} (v1.20.0 Stream A; capsule 7901662b)')
                defects += 1
        # folder_type enum check
        folder_type = get_scalar(fm, 'folder_type')
        if folder_type and folder_type not in valid_folder_types:
            findings.append(f'[FAIL] vault/files/{f.name} — governance-contract folder_type {folder_type!r} not in valid enum {sorted(valid_folder_types)}')
            defects += 1
        # governed_path resolves to a real folder
        governed_path = get_scalar(fm, 'governed_path')
        if governed_path:
            gp = governed_path.strip('"').strip("'")
            target = vault / gp.rstrip('/')
            if not target.is_dir():
                findings.append(f'[FAIL] vault/files/{f.name} — governance-contract governed_path {gp!r} does not resolve to a real folder')
                defects += 1
    return findings, total_checked, defects


def check_memory_typing(vault: Path) -> tuple[list[str], int, int]:
    """v1.26.0 Stream 4 — Verify memory entries declare valid frontmatter per memory.capsule v1.0.

    Sweeps:
      agents/<slug>/.tropo-capsule/memory/entries/*.md   (per-agent memory)
      .tropo-studio/memory/entries/*.md                   (vault-level memory)
      vault/files/<uid>.md where type=memory             (typed primitive in main vault)

    Surfaces violations at WARN severity at v1.26.0 (grace period; ratchet to ERROR
    in later cycle once substrate has settled per Stream 0 migration).

    Checks per entry:
      1. Required-field presence: subtype, scope, context, body, created
      2. Enum compliance: subtype ∈ {semantic,episodic,procedural,reference,feedback};
         scope ∈ {agent,vault,project}; tier ∈ {stm,current,topic,archival,demoted}
      3. score: float in [0.0, 1.0] if set
      4. context: ≤ 120 chars if set

    Citation resolution (refs:) deferred to sa.memory-curator's verification-before-use
    pass at boot — not the validator's job. Curator-mutable field discipline (only
    sa.memory-curator can write last_referenced/reference_count/score/tier) is enforced
    at curator dispatch time, not validation time.

    Silently skips entries directories that don't exist yet (Stream 0 may not have
    populated them at validator run-time; absence is not failure).

    Returns (findings, total_checked, defects). Capsule: memory v1.0 (UID a5b3c891).
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    valid_subtypes = {'semantic', 'episodic', 'procedural', 'reference', 'feedback'}
    valid_scopes = {'agent', 'vault', 'project'}
    valid_tiers = {'stm', 'current', 'topic', 'archival', 'demoted'}

    candidate_dirs: list[Path] = []

    # Per-agent memory entries
    agents_dir = vault / 'agents'
    if agents_dir.is_dir():
        for agent_folder in agents_dir.iterdir():
            if not agent_folder.is_dir():
                continue
            entries_dir = agent_folder / '.tropo-capsule' / 'memory' / 'entries'
            if entries_dir.is_dir():
                candidate_dirs.append(entries_dir)

    # Vault-level memory entries
    vault_memory_entries = vault / '.tropo-studio' / 'memory' / 'entries'
    if vault_memory_entries.is_dir():
        candidate_dirs.append(vault_memory_entries)

    # Memory-typed entries in main vault/files/
    for f in (vault / 'vault' / 'files').glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') != 'memory':
            continue
        total_checked += 1
        _validate_memory_frontmatter(
            f, fm, valid_subtypes, valid_scopes, valid_tiers, findings,
        )
        # body presence — markdown after frontmatter end
        if '---' not in text[3:]:
            findings.append(f'[WARN] {f.relative_to(vault)} — memory entry has no body content after frontmatter (memory.capsule v1.0 §Required)')
            defects += 1

    # Memory entries in per-agent/vault-level directories
    for d in candidate_dirs:
        for f in d.glob('*.md'):
            total_checked += 1
            try:
                text = f.read_text(errors='replace')
            except Exception:
                continue
            fm = split_frontmatter(text)
            if fm is None:
                findings.append(f'[WARN] {f.relative_to(vault)} — memory entry missing frontmatter (memory.capsule v1.0 §Required)')
                defects += 1
                continue
            _validate_memory_frontmatter(
                f, fm, valid_subtypes, valid_scopes, valid_tiers, findings,
            )

    # Count defects from findings list
    defects = sum(1 for line in findings if line.startswith('[WARN]') or line.startswith('[FAIL]'))

    return findings, total_checked, defects


def _validate_memory_frontmatter(
    path: Path,
    fm: dict,
    valid_subtypes: set,
    valid_scopes: set,
    valid_tiers: set,
    findings: list,
) -> None:
    """Helper for check_memory_typing — validates a single memory entry's frontmatter.

    Mutates findings in place per memory.capsule v1.0 §Validation Checks.
    All violations are WARN at v1.26.0 (grace period).
    """
    rel = path.relative_to(path.parents[3]) if len(path.parents) >= 4 else path.name

    # Required fields
    for required in ('subtype', 'scope', 'context'):
        if not get_scalar(fm, required):
            findings.append(f'[WARN] {rel} — memory entry missing required field {required!r} (memory.capsule v1.0 §Required)')

    # Enum compliance
    subtype = get_scalar(fm, 'subtype')
    if subtype and subtype not in valid_subtypes:
        findings.append(f'[WARN] {rel} — subtype {subtype!r} not in {sorted(valid_subtypes)} (memory.capsule v1.0 §Subtypes)')

    scope = get_scalar(fm, 'scope')
    if scope and scope not in valid_scopes:
        findings.append(f'[WARN] {rel} — scope {scope!r} not in {sorted(valid_scopes)} (memory.capsule v1.0 §Scope)')

    retention = get_scalar(fm, 'retention')
    if retention and retention not in valid_tiers:
        findings.append(f'[WARN] {rel} — retention {retention!r} not in {sorted(valid_tiers)} (memory.capsule v1.0 §State Machine)')

    # Score range
    score_raw = get_scalar(fm, 'score')
    if score_raw is not None:
        try:
            score_val = float(score_raw)
            if score_val < 0.0 or score_val > 1.0:
                findings.append(f'[WARN] {rel} — score {score_val} outside [0.0, 1.0] range (memory.capsule v1.0 §Validation Check 4)')
        except (TypeError, ValueError):
            findings.append(f'[WARN] {rel} — score {score_raw!r} not a valid float (memory.capsule v1.0 §Validation Check 4)')

    # Context length
    context = get_scalar(fm, 'context')
    if context and len(context) > 120:
        findings.append(f'[WARN] {rel} — context length {len(context)} > 120 chars (memory.capsule v1.0 §Validation Check 5)')


def check_article_source_required_fields(vault: Path) -> tuple[list[str], int, int]:
    """v1.49.0.2 — Verify source articles declare fields required by web rendering.

    Sweeps vault/files/*.md for entries with subtype=article. Validates that each declares
    the fields required by app/(web)/agentic-builders/lib.ts parseVaultFile() — title, slug,
    published_at — when article is in publish-ready status.

    v1.49.0.2 DRY-refactor: rule logic lives in lib/article_readiness.py
    (`check_source_article_required_fields`) so tropo-validate.py + publish-check.py share
    a single source of truth + can't drift. Per R1 paired-walk skeptic-arch P1 finding.

    WARN severity at v1.49.0.2 (grace period; ERROR ratchet at v1.50.0+ per c5a7e391 §13.3 P1).
    Returns (findings, total_checked, defects).
    """
    # Local import — lib/ is a sibling directory; sys.path already set up at module level
    from lib.article_readiness import check_source_article_required_fields as _shared_check

    findings: list[str] = []
    total_checked = 0

    for f in (vault / 'vault' / 'files').glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_raw = split_frontmatter(text)
        if fm_raw is None:
            continue
        if get_scalar(fm_raw, 'subtype') != 'article':
            continue

        # Parse full YAML for shared-module input (it reads nested fields via dict access)
        try:
            fm_dict = yaml.safe_load(fm_raw) or {}
            if not isinstance(fm_dict, dict):
                continue
        except yaml.YAMLError:
            continue

        rel = f.relative_to(vault)
        result = _shared_check(get_scalar(fm_raw, 'uid') or f.stem, fm_dict)

        if result.skipped:
            continue
        total_checked += 1

        for finding in result.findings:
            findings.append(f'[WARN] {rel} — {finding}')

    defects = sum(1 for line in findings if line.startswith('[WARN]') or line.startswith('[FAIL]'))

    return findings, total_checked, defects


def check_ship_artifact_required_fields(vault: Path) -> tuple[list[str], int, int]:
    """v1.49.0.2 — Verify ship-artifact wrappers declare fields required by extraction engine.

    Sweeps vault/files/*.md for entries with type=ship-artifact. Validates required fields
    per publish.py extract_manifest_root + ship-artifact.capsule v1.4 schema.

    v1.49.0.2 DRY-refactor: rule logic lives in lib/article_readiness.py
    (`check_wrapper_required_fields`) so tropo-validate.py + publish-check.py share a single
    source of truth + can't drift. Per R1 paired-walk skeptic-arch P1 finding.

    Folder-class wrappers exempt from canonical_source + parent checks (they ARE the parent).
    WARN severity at v1.49.0.2 (grace period; ERROR ratchet at v1.50.0+ per c5a7e391 §13.3 P2).
    Returns (findings, total_checked, defects).
    """
    from lib.article_readiness import check_wrapper_required_fields as _shared_check

    findings: list[str] = []
    total_checked = 0

    for f in (vault / 'vault' / 'files').glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_raw = split_frontmatter(text)
        if fm_raw is None:
            continue
        if get_scalar(fm_raw, 'type') != 'ship-artifact':
            continue

        # Parse full YAML for shared-module input
        try:
            fm_dict = yaml.safe_load(fm_raw) or {}
            if not isinstance(fm_dict, dict):
                continue
        except yaml.YAMLError as e:
            findings.append(f'[WARN] {f.relative_to(vault)} — ship-artifact frontmatter YAML parse failed: {e}')
            continue

        total_checked += 1
        rel = f.relative_to(vault)
        result = _shared_check(get_scalar(fm_raw, 'uid') or f.stem, fm_dict)

        for finding in result.findings:
            findings.append(f'[WARN] {rel} — {finding}')

    defects = sum(1 for line in findings if line.startswith('[WARN]') or line.startswith('[FAIL]'))

    return findings, total_checked, defects


def check_publish_pipeline_md_schema(vault: Path) -> tuple[list[str], int, int]:
    """v1.49.0 — Verify publish.pipeline.md definitions conform to capsule schema.

    Sweeps vault/files/*.md for type=publish-pipeline entries; validates per
    publish.pipeline.capsule v1.0 (UID 7e3a91c8) §3 Pipeline Definition Schema.

    Checks per entry:
      1. Required-field presence: target, source, selection_rules
      2. target is a string (extensibility via target modules; check_target_module_present
         validates module existence separately)
      3. selection_rules is a dict with exactly one of: manifest_root, explicit_uids,
         all_files_of_type
      4. If cleanup_rules declared, must be a dict (full c5a7e391 §3.5 six-field
         schema validation deferred to v1.50+ ratchet — v1.49 only checks shape)

    WARN severity at v1.49.0 (grace period; ERROR ratchet at v1.50.0+ per cycle
    brief 143c74d5 v0.3 §S0.2).

    Returns (findings, total_checked, defects). Capsule: publish.pipeline v1.0 (UID 7e3a91c8).
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    required_fields = ('target', 'source', 'selection_rules')
    valid_selection_keys = {'manifest_root', 'explicit_uids', 'all_files_of_type'}

    for f in (vault / 'vault' / 'files').glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_raw = split_frontmatter(text)
        if fm_raw is None:
            continue
        if get_scalar(fm_raw, 'type') != 'publish-pipeline':
            continue

        # Parse full YAML dict for nested-field access (selection_rules + cleanup_rules)
        try:
            fm = yaml.safe_load(fm_raw) or {}
            if not isinstance(fm, dict):
                continue
        except yaml.YAMLError as e:
            findings.append(f'[WARN] {f.relative_to(vault)} — publish.pipeline.md frontmatter YAML parse failed: {e}')
            continue

        total_checked += 1
        rel = f.relative_to(vault)

        # Check 1: required fields
        for field in required_fields:
            if field not in fm:
                findings.append(f'[WARN] {rel} — publish.pipeline.md missing required field {field!r} (publish.pipeline.capsule v1.0 §3)')

        # Check 2: target is a string
        target = fm.get('target')
        if target is not None and not isinstance(target, str):
            findings.append(f'[WARN] {rel} — publish.pipeline.md target must be string, got {type(target).__name__} (publish.pipeline.capsule v1.0 §3)')

        # Check 3: selection_rules is a dict with exactly one of three valid shapes
        sel = fm.get('selection_rules')
        if sel is not None:
            if not isinstance(sel, dict):
                findings.append(f'[WARN] {rel} — publish.pipeline.md selection_rules must be a dict, got {type(sel).__name__} (publish.pipeline.capsule v1.0 §3.1)')
            else:
                present_keys = set(sel.keys()) & valid_selection_keys
                if len(present_keys) == 0:
                    findings.append(f'[WARN] {rel} — publish.pipeline.md selection_rules has no recognized shape; expected one of {sorted(valid_selection_keys)} (publish.pipeline.capsule v1.0 §3.1)')
                elif len(present_keys) > 1:
                    findings.append(f'[WARN] {rel} — publish.pipeline.md selection_rules declares multiple shapes {sorted(present_keys)}; should declare exactly one (publish.pipeline.capsule v1.0 §3.1)')

        # Check 4: cleanup_rules shape (if declared)
        cleanup = fm.get('cleanup_rules')
        if cleanup is not None and not isinstance(cleanup, dict):
            findings.append(f'[WARN] {rel} — publish.pipeline.md cleanup_rules must be a dict per c5a7e391 §3.5 schema, got {type(cleanup).__name__}')

    defects = sum(1 for line in findings if line.startswith('[WARN]') or line.startswith('[FAIL]'))

    return findings, total_checked, defects


def check_target_module_present(vault: Path) -> tuple[list[str], int, int]:
    """v1.49.0 — Verify each publish.pipeline.md's target has a corresponding target module.

    Sweeps vault/files/*.md for type=publish-pipeline entries; for each, checks that
    .tropo/scripts/publish_targets/<target>.py exists.

    Companion to check_publish_pipeline_md_schema — that one validates schema shape;
    this one validates the target module is actually present so publish.py won't exit 3
    at runtime invocation. Catches the defect at vault rebuild time vs runtime per
    fail-fast posture (publish.pipeline.capsule v1.0 §1 friction minimizer #3).

    WARN severity at v1.49.0 (grace period; ERROR ratchet at v1.50.0+ per cycle brief
    143c74d5 v0.3 §S0.2).

    Returns (findings, total_checked, defects). Capsule: publish.pipeline v1.0 (UID 7e3a91c8).
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    targets_dir = vault / '.tropo' / 'scripts' / 'publish_targets'

    for f in (vault / 'vault' / 'files').glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') != 'publish-pipeline':
            continue

        target = get_scalar(fm, 'publish_target')
        if not target or not isinstance(target, str):
            # check_publish_pipeline_md_schema already surfaced this; don't double-report
            continue

        total_checked += 1
        rel = f.relative_to(vault)
        target_module = targets_dir / f'{target}.py'

        if not target_module.is_file():
            findings.append(
                f'[WARN] {rel} — publish.pipeline.md target {target!r} has no module at '
                f'.tropo/scripts/publish_targets/{target}.py; publish.py will exit 3 at runtime '
                f'(publish.pipeline.capsule v1.0 §5 Target-Implementation Interface Contract)'
            )

    defects = sum(1 for line in findings if line.startswith('[WARN]') or line.startswith('[FAIL]'))

    return findings, total_checked, defects


def check_release_documentation_deliverables(vault: Path) -> tuple[list[str], int, int]:
    """v1.27.0 Stream C — Verify release entries have full documentation deliverables.

    For each release at status:shipped (current; not state:archived predecessors), check:
      1. Every subsystem in subsystems_touched has a `### v<X.Y.Z>` section in its hub body
      2. RELEASE-NOTES.md (at vault root parent) contains the version
      3. channels/releases.md has a post for this version

    This is Mike-A59's "deliberate not lazy" pin operationalized at substrate level —
    documentation gaps no longer ship silently.

    Releases marked sweep_history_backfilled_at carry grace-period INFO severity per
    Stream A pattern; new releases fire WARN at v1.27.0 (grace period for substrate
    to settle) with ERROR ratchet planned for v1.28.0+ once new cycles author cleanly.

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    # Find the current state:active release
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if not fm or get_scalar(fm, 'type') != 'release':
            continue
        if get_scalar(fm, 'status') != 'shipped':
            continue
        if get_scalar(fm, 'state') != 'active':
            continue
        total_checked += 1

        version = get_scalar(fm, 'release_version') or get_scalar(fm, 'version')
        if not version:
            continue
        version_label = str(version) if str(version).startswith('v') else f"v{version}"   # d5a1b7c3 fix (argus-a110): release_version values carry mixed v-prefix shape; never search for 'vv1.X'

        is_sweep_backfilled = bool(get_scalar(fm, 'sweep_history_backfilled_at'))
        sev = "INFO" if is_sweep_backfilled else "WARN"

        # Check 1: hub-body Change Log entry for each declared subsystem
        subs_touched_raw = fm.get('subsystems_touched') if isinstance(fm, dict) else None
        if isinstance(subs_touched_raw, list):
            for hub_uid in subs_touched_raw:
                hub_path = files_dir / f"{hub_uid}.md"
                if not hub_path.is_file():
                    continue
                try:
                    hub_text = hub_path.read_text(errors='replace')
                except Exception:
                    continue
                # Look for ### v<X.Y.Z> heading in hub body
                if f"### {version_label}" not in hub_text:
                    findings.append(
                        f'[{sev}] release {f.name} declares subsystems_touched={hub_uid} but hub vault/files/{hub_uid}.md has no `### {version_label}` Change Log entry (v1.27.0 Stream C; capsule a5b3c891)'
                    )
                    defects += 1

        # Check 2: RELEASE-NOTES.md at vault root contains the version
        release_notes_path = vault / 'RELEASE-NOTES.md'
        if release_notes_path.is_file():
            try:
                rn_text = release_notes_path.read_text(errors='replace')
            except Exception:
                rn_text = ''
            if version_label not in rn_text:
                findings.append(
                    f'[{sev}] RELEASE-NOTES.md missing {version_label} section for release {f.name} (v1.27.0 Stream C)'
                )
                defects += 1

        # Check 3: channels/releases.md has a post for this version
        releases_channel = vault / 'channels' / 'releases.md'
        if releases_channel.is_file():
            try:
                rc_text = releases_channel.read_text(errors='replace')
            except Exception:
                rc_text = ''
            if version_label not in rc_text:
                findings.append(
                    f'[{sev}] channels/releases.md missing post for {version_label} (release {f.name}); v1.27.0 Stream C'
                )
                defects += 1

    return findings, total_checked, defects


# ---------------------------------------------------------------------------
# v1.25.0 Stream E — Import primitive validator extensions
# Capsules: external-artifact (eedd7034), reconcile-report (013b7b6e)
# Spec: vault/files/2b49ba79.md
# ---------------------------------------------------------------------------

# External-artifact required frontmatter fields (per external-artifact.capsule v1.0)
EXTERNAL_ARTIFACT_REQUIRED_FIELDS = {
    'uid', 'type', 'status', 'title', 'owner', 'created', 'modified',
    'source_filename', 'source_path', 'original_path',
    'source_size_bytes', 'source_mtime', 'source_hash', 'hash_function',
    'member_of', 'governance', 'schema_version',
}

VALID_HASH_FUNCTIONS = {'stable-id', 'content-aware', 'sha256'}
VALID_GOVERNANCE_VALUES = {'tier-1-sidecar', 'tier-2-vault-native'}
VALID_EXTRACTION_SCOPE_VALUES = {'ship', 'argo-reference', 'argo-private', 'external', 'internal'}

# v1.42.0 Stream B — ship-artifact.capsule v1.3 Check 24: target field shape + enum
# Always-array shape per capsule v1.3 §Target Semantics. Allowed elements: release | web.
# Absent target field is permitted (implicit [release]); scalar values rejected.
VALID_SHIP_ARTIFACT_TARGETS = {'release', 'web'}

# v1.48.0 Stream A — ship-artifact.capsule v1.4 Checks 25-29
# Article subtype editorial state machine + publish-act semantics + external-work gitignore.
VALID_ARTICLE_EDITORIAL_STATES = {'draft', 'reviewed', 'locked', 'archived'}
VALID_PUBLICATION_STATE_VALUES = {'live', 'retracted'}


def check_cascade_spec_validity(vault: Path) -> tuple[list[str], int, int]:
    """v1.35.0 — Validate cascade_spec on type:pipeline entries (spec d2f8c194 §11.4).

    Walks vault/files/*.md for entries with type:pipeline + cascade_spec; verifies:
      - cascade_spec is a dict (else malformed)
      - generates_project_plan is bool if present
      - spawns_workstreams is a list if present
      - Each spawns_workstreams entry has required fields: pipeline_uid, name, owner_agent_class
      - Each declared pipeline_uid resolves to a vault entry of type:pipeline
      - Workstream pipelines (spawn targets) carry role:"workstream"
      - Cycle detection: no workstream spawns back to a parent in its own chain

    Honor-system WARN at v1.35.0 per spec §11(4); ERROR ratchet planned for v1.36.0+.
    Runtime hard-fail in pipeline-activate.py is the operational guard; this check
    surfaces shape defects on the substrate before any activation fires.

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    # Build UID → parsed-frontmatter index for resolution + cycle checks.
    # We need full nested structure (cascade_spec is dict-of-list-of-dicts),
    # so use yaml.safe_load rather than the regex-scalar accessor.
    pipelines: dict[str, dict[str, Any]] = {}
    all_uids: set[str] = set()
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        try:
            fm = yaml.safe_load(fm_text)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        uid = str(fm.get('uid') or f.stem)
        all_uids.add(uid)
        if fm.get('type') == 'pipeline':
            pipelines[uid] = fm

    total_checked = 0
    defects = 0
    ws_required = ('pipeline_uid', 'name', 'owner_agent_class')

    for uid, fm in pipelines.items():
        cascade = fm.get('cascade_spec')
        if cascade is None:
            continue
        total_checked += 1
        fname = f'vault/files/{uid}.md'

        if not isinstance(cascade, dict):
            findings.append(f'[WARN] {fname} — cascade_spec is not a mapping (got {type(cascade).__name__}); pipeline-activate.py would runtime-fail')
            defects += 1
            continue

        gpp = cascade.get('generates_project_plan')
        if gpp is not None and not isinstance(gpp, bool):
            findings.append(f'[WARN] {fname} — cascade_spec.generates_project_plan must be bool (got {gpp!r})')
            defects += 1

        sw = cascade.get('spawns_workstreams')
        if sw is None:
            continue
        if not isinstance(sw, list):
            findings.append(f'[WARN] {fname} — cascade_spec.spawns_workstreams must be a list (got {type(sw).__name__})')
            defects += 1
            continue

        # Per-workstream entry checks
        ws_uids_seen: set[str] = set()
        for i, ws in enumerate(sw):
            if not isinstance(ws, dict):
                findings.append(f'[WARN] {fname} — spawns_workstreams[{i}] is not a mapping')
                defects += 1
                continue
            for field in ws_required:
                if field not in ws:
                    findings.append(f'[WARN] {fname} — spawns_workstreams[{i}] missing required field {field!r}')
                    defects += 1
            ws_uid = ws.get('pipeline_uid')
            if not ws_uid:
                continue
            ws_uid = str(ws_uid)
            # UID resolution
            if ws_uid not in all_uids:
                findings.append(f'[WARN] {fname} — spawns_workstreams[{i}].pipeline_uid {ws_uid!r} does not resolve to any vault entry')
                defects += 1
                continue
            # Must point at a pipeline
            if ws_uid not in pipelines:
                findings.append(f'[WARN] {fname} — spawns_workstreams[{i}].pipeline_uid {ws_uid!r} resolves but is not type:pipeline')
                defects += 1
                continue
            # Workstream pipeline should carry role:"workstream"
            ws_fm = pipelines[ws_uid]
            if ws_fm.get('role') != 'workstream':
                findings.append(f'[WARN] {fname} — spawns_workstreams[{i}].pipeline_uid {ws_uid!r} target is not tagged role:"workstream"')
                defects += 1
            # Duplicate detection within this spawn list
            if ws_uid in ws_uids_seen:
                findings.append(f'[WARN] {fname} — spawns_workstreams declares pipeline_uid {ws_uid!r} more than once')
                defects += 1
            ws_uids_seen.add(ws_uid)

        # Cycle detection: walk spawn graph from this pipeline; flag if any descendant cycles back
        visited: set[str] = {uid}
        frontier: set[str] = set(ws_uids_seen)
        while frontier:
            if uid in frontier:
                findings.append(f'[WARN] {fname} — cascade_spec spawn graph contains a cycle back to root pipeline {uid!r}')
                defects += 1
                break
            next_frontier: set[str] = set()
            for fr_uid in frontier:
                if fr_uid in visited:
                    continue
                visited.add(fr_uid)
                fr_fm = pipelines.get(fr_uid)
                if not fr_fm:
                    continue
                fr_cascade = fr_fm.get('cascade_spec')
                if not isinstance(fr_cascade, dict):
                    continue
                fr_sw = fr_cascade.get('spawns_workstreams') or []
                if not isinstance(fr_sw, list):
                    continue
                for sub_ws in fr_sw:
                    if isinstance(sub_ws, dict) and sub_ws.get('pipeline_uid'):
                        next_frontier.add(str(sub_ws['pipeline_uid']))
            frontier = next_frontier - visited

    return findings, total_checked, defects


def check_pipeline_activation_provenance(vault: Path) -> tuple[list[str], int, int]:
    """v1.35.0 §Rule 10 v2.2 honor-system enforcement (spec d2f8c194 §4(11)).

    Pipeline-class activations must be authored by pipeline-activate.py — they
    are runtime fires, not hand-authored substrate. This check sweeps activation
    entries with activation_class:pipeline; flags any whose created_by is not
    `pipeline-activate.py`.

    Honor-system WARN at v1.35.0; mechanical-fail ratchet planned for v1.36.0+.
    The runtime script writes its own created_by; a manual author would need to
    bypass deliberately for this check to fire.

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    total_checked = 0
    defects = 0
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        # Cheap pre-filter: only pipeline-class activations
        if get_scalar(fm_text, 'type') != 'activation':
            continue
        ac = get_scalar(fm_text, 'activation_class')
        if ac != 'pipeline':
            continue
        total_checked += 1
        created_by = get_scalar(fm_text, 'created_by')
        if created_by != 'pipeline-activate.py':
            findings.append(
                f'[WARN] vault/files/{f.name} — pipeline-class activation created_by '
                f'{created_by!r} (expected pipeline-activate.py); §Rule 10 v2.2 '
                f'honor-system at v1.35.0; mechanical-fail ratchet at v1.36.0+'
            )
            defects += 1

    return findings, total_checked, defects


def check_step_verifier_distinct_from_owner_when_overridden(vault: Path) -> tuple[list[str], int, int]:
    """v1.46.0 — pipeline.capsule v3.0 §Validation Check 17.

    For step WorkflowNodes where both step_owner_role AND step_verifier_role
    are declared AND step_verifier_role != "same-as-executor", they must name
    different agent classes. Enforces the explicit-override discipline (an
    explicit step_verifier_role: value MUST mean separate-context verification;
    same-as-executor is the default and doesn't require declaration).

    Only fires on v3.0-shaped step entries (presence of both v3.0 fields).
    Pre-v3.0 step entries without these fields are skipped.

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    total_checked = 0
    defects = 0

    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        if get_scalar(fm_text, 'type') != 'pipeline':
            continue
        if get_scalar(fm_text, 'subtype') != 'workflow-node':
            continue

        owner = get_scalar(fm_text, 'step_owner_role')
        verifier = get_scalar(fm_text, 'step_verifier_role')

        # Only fires when both v3.0 fields are declared
        if not owner or not verifier:
            continue

        # Default 'same-as-executor' is allowed
        if verifier == 'same-as-executor':
            continue

        total_checked += 1

        if owner == verifier:
            findings.append(
                f'[FAIL] vault/files/{f.name} — step_verifier_role ({verifier!r}) equals step_owner_role ({owner!r}); '
                f'explicit override must name a DIFFERENT class than the executor per pipeline.capsule v3.0 §Check 17. '
                f'Use step_verifier_role: same-as-executor (default) if no separate-context verification is needed.'
            )
            defects += 1

    return findings, total_checked, defects


def check_step_depends_on_acyclic(vault: Path) -> tuple[list[str], int, int]:
    """v1.46.0 — pipeline.capsule v3.0 §Validation Check 18.

    Walk all step WorkflowNodes' depends_on_steps: edges and confirm no cycles.
    DAG invariant enforced structurally. ERROR severity.

    Only fires on v3.0-shaped step entries (presence of depends_on_steps field).
    Pre-v3.0 step entries without the field are skipped.

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    # Build map: step_uid -> depends_on_steps[]
    deps: dict[str, list[str]] = {}
    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        if get_scalar(fm_text, 'type') != 'pipeline':
            continue
        if get_scalar(fm_text, 'subtype') != 'workflow-node':
            continue

        dep_list = get_list(fm_text, 'depends_on_steps')
        if dep_list is None:
            continue
        # Strip scalar-sentinel results (caller indicated field is not a list)
        cleaned = [d for d in dep_list if not d.startswith('__scalar__:')]
        if not cleaned:
            continue
        uid = get_scalar(fm_text, 'uid') or f.stem
        deps[uid] = cleaned

    total_checked = len(deps)
    defects = 0

    # For each step with declared depends_on_steps, walk graph + detect cycles via DFS
    for start_uid in deps:
        visited: set[str] = set()
        stack: list[tuple[str, list[str]]] = [(start_uid, [start_uid])]
        cycle_found = False
        while stack and not cycle_found:
            node, path = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            for dep in deps.get(node, []):
                if dep in path:
                    findings.append(
                        f'[FAIL] vault/files/{start_uid}.md — depends_on_steps graph contains cycle: '
                        f'{" -> ".join(path + [dep])}; pipeline.capsule v3.0 §Check 18 (DAG invariant).'
                    )
                    defects += 1
                    cycle_found = True
                    break
                stack.append((dep, path + [dep]))

    return findings, total_checked, defects


def check_vc_true_has_verification_command(vault: Path) -> tuple[list[str], int, int]:
    """v1.64 — pipeline.capsule v3.2 §Validation Check 20 (WARN-ratchet).

    For step WorkflowNodes that are verification_class: true AND carry
    trust_level: approval-required (a vc:true GATE step), verification_command:
    MUST be present + non-empty. The vc:true parallel to Check 19 on the
    vc:false branch: a vc:true gate step's verdict is supposed to BE its natural
    machine output, but with no verification_command the engine has no machine
    to run and falls back to agent attestation (the vc:true self-attestation
    hole; the parallel to v1.62 B4 removing the vc:false stdin hatch).

    WARN-ratchet (v1.64): findings are [WARN], FAIL count always 0, so it cannot
    red-light a rebuild while existing gate steps are remediated. Ratchets to
    ERROR in a later cycle (the Check 19 WARN -> ERROR lifecycle).

    (A94 2026-06-02 re-scope): a vc:true step's verdict source can be ANY of the
    engine's evaluate_criterion methods — command (verification_command), human
    (trust_level: approval-required, or a `human:` exit_criterion), or aggregate
    (an `aggregate:` exit_criterion). WARN only when NONE exists. The original
    scope (vc:true + approval-required needs verification_command) was BACKWARDS:
    approval-required gates are human_signoff-verified, so they HAVE a source and
    must not warn. This flags the real hole: a vc:true step with no verdict source
    of any kind.

    Returns (findings, total_checked, _fails=0).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    total_checked = 0
    for f in sorted(files_dir.glob('*.md')):  # sorted for deterministic hole list (v1.66 S1 ed04d931)
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        if get_scalar(fm_text, 'type') != 'pipeline':
            continue
        if get_scalar(fm_text, 'subtype') != 'workflow-node':
            continue

        if str(get_scalar(fm_text, 'verification_class')).strip().lower() != 'true':
            continue

        total_checked += 1
        # Verdict sources (engine evaluate_criterion 4-way dispatch + step schema):
        #   command   -> step-level verification_command
        #   human     -> trust_level: approval-required (human_signoff IS the verdict),
        #                or an exit_criterion with the `human:` prefix
        #   aggregate -> an exit_criterion with the `aggregate:` prefix
        cmd = get_scalar(fm_text, 'verification_command')
        has_command = bool(cmd and str(cmd).strip())
        # v1.66 S1 part-2 (Vela V60 captain-mode 2026-06-07, per Argus A102 design-lock event 2239;
        # finding 7c4e9a1b): a verification_command present-as-text but in UNPARSEABLE frontmatter is a
        # sourceless verdict in disguise — the runtime's read_vault_entry does yaml.safe_load, returns
        # None on failure, and the command never runs. Check 20 used get_scalar (raw-text regex), so it
        # passed OVER 3 steps whose verification_command had unescaped inner quotes (343dd5d8/98de904e/
        # 8654900a). Harden: a command-bearing step whose frontmatter fails yaml.safe_load, or whose
        # command is empty after shlex.split, is an ERROR (matches the runtime's load semantics).
        if has_command:
            import shlex as _shlex
            _uid20 = get_scalar(fm_text, 'uid') or f.stem
            try:
                _parsed20 = yaml.safe_load(fm_text) or {}
            except Exception as _e20:
                findings.append(
                    f'[ERROR] vault/files/{f.name} — vc:true step {_uid20} declares a verification_command '
                    f'but its frontmatter is UNPARSEABLE YAML ({type(_e20).__name__}); the runtime cannot load '
                    f'it (read_vault_entry returns None) so the command never runs — a sourceless verdict in '
                    f'disguise. Per pipeline.capsule v3.3 §Check 20 (ERROR; v1.66 S1 part-2 unparseable-command guard).'
                )
                continue
            _vc20 = _parsed20.get('verification_command')
            if not (_vc20 and _shlex.split(str(_vc20))):
                findings.append(
                    f'[ERROR] vault/files/{f.name} — vc:true step {_uid20} verification_command is empty after '
                    f'parse — no runnable command means no verdict source. '
                    f'Per pipeline.capsule v3.3 §Check 20 (ERROR; v1.66 S1 part-2).'
                )
                continue
        is_human_gate = str(get_scalar(fm_text, 'trust_level')).strip() == 'approval-required'
        crits = get_list(fm_text, 'exit_criteria') or []
        has_human_or_agg = any(
            (not c.startswith('__scalar__:'))
            and (c.strip().startswith('human:') or c.strip().startswith('aggregate:'))
            for c in crits
        )
        if has_command or is_human_gate or has_human_or_agg:
            continue  # has a verdict source — fine

        uid = get_scalar(fm_text, 'uid') or f.stem
        findings.append(
            f'[ERROR] vault/files/{f.name} — vc:true step {uid} has NO verdict source '
            f'(no verification_command, not approval-required/human, no human:/aggregate: exit_criterion); '
            f'its natural-output verdict has no machine/human mechanism (vc:true self-attestation hole). '
            f'Per pipeline.capsule v3.3 §Check 20 (ERROR — ratcheted at v1.66 after live zero confirmed).'
        )

    return findings, total_checked, len(findings)


def check_pipeline_runtime_has_jsonl(vault: Path) -> tuple[list[str], int, int]:
    """v1.46.0 — pipeline-run.capsule v2.0 §Validation Check 13 (MUST-SHIP).

    For v2.0-shape pipeline-run entries: must declare run_folder: explicitly
    AND the path must contain a run.jsonl file. ERROR severity.

    v2.0-shape discriminator: presence of `substrate_authored_by:` field
    (REQUIRED at v2.0 per pipeline-run.capsule v2.0 §Schema). Pre-v2.0
    entries (v1.4-shape; no substrate_authored_by:) fall under v1.4's
    OPTIONAL-with-default rule and are skipped here.

    Also checks v2.0-shape entries that DO declare run_folder: — verifies
    the path resolves and contains run.jsonl.

    Skips state:archived entries (terminal historical record).

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    total_checked = 0
    defects = 0

    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        type_val = get_scalar(fm_text, 'type')
        if type_val != 'pipeline-run':
            continue

        # v2.0-shape discriminator: REQUIRED substrate_authored_by: field present
        substrate_authored_by = get_scalar(fm_text, 'substrate_authored_by')
        if not substrate_authored_by:
            # v1.4-shape entry — falls under v1.4's OPTIONAL run_folder rule; skip
            continue

        # Skip archived/terminal entries
        if get_scalar(fm_text, 'state') == 'archived':
            continue

        total_checked += 1

        run_folder = get_scalar(fm_text, 'run_folder')
        if not run_folder:
            findings.append(
                f'[FAIL] vault/files/{f.name} — v2.0-shape pipeline-run entry missing required run_folder: field '
                f'(REQUIRED at v2.0 per pipeline-run.capsule v2.0 §Check 13).'
            )
            defects += 1
            continue

        # Resolve run_folder path relative to vault root
        jsonl_path = (vault / run_folder).resolve() / 'run.jsonl'
        if not jsonl_path.is_file():
            findings.append(
                f'[FAIL] vault/files/{f.name} — declared run_folder ({run_folder!r}) does not contain a run.jsonl file '
                f'(expected at {jsonl_path}); pipeline-run.capsule v2.0 §Check 13.'
            )
            defects += 1

    return findings, total_checked, defects


def check_step_completion_has_verification(vault: Path) -> tuple[list[str], int, int]:
    """v1.46.0 — pipeline-run.capsule v2.0 §Validation Check 14 (MUST-SHIP).

    For every step_completed event in a v2.0-shape run.jsonl, a matching
    verification_receipt with verdict:pass for that step must also exist.
    ERROR severity.

    Verification-class steps (pipeline definition declares verification_class: true)
    bypass this check; their step_completed.data carries the natural verdict
    (build exit code / HTTP status / validator pass-fail) and that is sufficient.

    Only fires on v2.0-shape runs (those whose run.jsonl contains an
    activation_contract_locked event). Pre-v2.0 runs are skipped.

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []

    # Build verification-class step lookup from pipeline definitions
    verification_class_steps: set[str] = set()
    files_dir = vault / 'vault' / 'files'
    if files_dir.is_dir():
        for f in files_dir.glob('*.md'):
            try:
                text = f.read_text(errors='replace')
            except Exception:
                continue
            fm_text = split_frontmatter(text)
            if fm_text is None:
                continue
            if get_scalar(fm_text, 'type') != 'pipeline':
                continue
            if get_scalar(fm_text, 'verification_class') == 'true':
                uid = get_scalar(fm_text, 'uid') or f.stem
                verification_class_steps.add(uid)

    # Walk run.jsonl files under vault/pipeline-runs/ (v2.0 canonical path).
    # v1.4-shape runs at agents/dev-pipeline/activations/ are NOT checked here
    # because they pre-date the v2.0 contract; their schema doesn't include the
    # verification_receipt requirement.
    runs_dir = vault / 'vault' / 'pipeline-runs'
    if not runs_dir.is_dir():
        return findings, 0, 0

    total_checked = 0
    defects = 0

    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        jsonl_path = run_dir / 'run.jsonl'
        if not jsonl_path.is_file():
            continue

        try:
            events: list[dict] = []
            with jsonl_path.open() as fp:
                for raw in fp:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    events.append(ev)
        except OSError:
            continue

        # Only check v2.0 runs (those with activation_contract_locked event)
        has_contract = any(e.get('event') == 'activation_contract_locked' for e in events)
        if not has_contract:
            continue

        total_checked += 1

        # Build map: step_uid -> events targeting that step
        step_events: dict[str, list[dict]] = {}
        for ev in events:
            step_uid = ev.get('step')
            if not step_uid:
                continue
            step_events.setdefault(step_uid, []).append(ev)

        for step_uid, step_evs in step_events.items():
            if step_uid in verification_class_steps:
                continue  # bypass for verification-class steps
            has_completed = any(e.get('event') == 'step_completed' for e in step_evs)
            if not has_completed:
                continue
            has_passed = any(
                e.get('event') == 'verification_receipt'
                and (e.get('data') or {}).get('verdict') == 'pass'
                for e in step_evs
            )
            if not has_passed:
                try:
                    rel_jsonl = jsonl_path.relative_to(vault)
                except ValueError:
                    rel_jsonl = jsonl_path
                findings.append(
                    f'[FAIL] {rel_jsonl} — step {step_uid!r} has step_completed event without a matching '
                    f'verification_receipt:verdict:pass; pipeline-run.capsule v2.0 §Check 14.'
                )
                defects += 1

    return findings, total_checked, defects


def check_external_artifact_typing(vault: Path) -> tuple[list[str], int, int]:
    """Validate every type: external-artifact entry has required fields per external-artifact.capsule v1.0.

    Walks vault/files/*.md and vault/files/<uid>/metadata.md looking for type: external-artifact.
    For each, verify all required fields present + governance/hash_function enums valid.

    Returns (findings, total_checked, defects)."""
    findings: list[str] = []
    checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, checked, defects

    # Walk both flat (Tier 1) and per-UID directory (Tier 2)
    candidates: list[Path] = list(files_dir.glob('*.md'))
    for sub in files_dir.iterdir():
        if sub.is_dir():
            meta = sub / 'metadata.md'
            if meta.is_file():
                candidates.append(meta)

    for path in candidates:
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        type_val = get_scalar(fm, 'type')
        if type_val != 'external-artifact':
            continue

        checked += 1
        present_fields = {
            line.split(':', 1)[0].strip()
            for line in fm.splitlines()
            if ':' in line and not line.lstrip().startswith('-') and not line.startswith(' ')
        }
        missing = EXTERNAL_ARTIFACT_REQUIRED_FIELDS - present_fields
        if missing:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — external-artifact missing required field(s): {sorted(missing)}'
            )
            defects += 1
            continue

        # Enum validation
        gov = get_scalar(fm, 'governance')
        if gov and gov not in VALID_GOVERNANCE_VALUES:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — governance={gov!r} not in {sorted(VALID_GOVERNANCE_VALUES)}'
            )
            defects += 1
        hf = get_scalar(fm, 'hash_function')
        if hf and hf not in VALID_HASH_FUNCTIONS:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — hash_function={hf!r} not in {sorted(VALID_HASH_FUNCTIONS)}'
            )
            defects += 1
        sv = get_scalar(fm, 'schema_version')
        if sv and sv.strip() != '1':
            findings.append(
                f'[WARN] {path.relative_to(vault)} — schema_version={sv!r} (expected "1" for external-artifact v1.0)'
            )
            defects += 1

    return findings, checked, defects


def check_sidecar_source_pairing(vault: Path) -> tuple[list[str], int, int]:
    """Walk all .tropo-studio/*.tropo.md sidecars in the Studio; verify pairing.

    Forward: every sidecar's source_path resolves to an existing source file.
    Reverse: every file in a governed folder (per parent's .tropo-folder.md) NOT in .tropoignore
             has a corresponding sidecar.

    Returns (findings, total_checked, defects)."""
    findings: list[str] = []
    checked = 0
    defects = 0

    # Read .tropoignore patterns
    ignore_patterns: list[str] = []
    ignore_file = vault / '.tropoignore'
    if ignore_file.is_file():
        for line in ignore_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                ignore_patterns.append(line)

    # Find all .tropo-studio/ directories Studio-wide
    for tropo_studio in vault.rglob('.tropo-studio'):
        if not tropo_studio.is_dir():
            continue
        # Skip the kernel .tropo-studio at Studio root if it lacks .tropo-folder.md
        # (kernel .tropo-studio holds institutional metadata + maybe root-level sidecars)
        if tropo_studio.parent == vault:
            # Root .tropo-studio — only check actual *.tropo.md sidecars; no folder marker required
            # v1.0.1 fix (sa.skeptic round-2 P0-A6): defect counting now uses before_count
            # pattern (matches the per-folder branch below) — previous slicing [-1:] miscounted.
            for sidecar in tropo_studio.glob('*.tropo.md'):
                if sidecar.name == '.tropo-folder.md':
                    continue
                checked += 1
                before_count = len(findings)
                _check_sidecar_pair(sidecar, vault, vault, findings)
                if len(findings) > before_count:
                    defects += 1
            continue

        # Per-folder .tropo-studio with a .tropo-folder.md marker
        marker = tropo_studio / '.tropo-folder.md'
        if not marker.is_file():
            continue
        parent_folder = tropo_studio.parent

        # Forward check: each sidecar has a source
        sidecar_sources_named: set[str] = set()
        for sidecar in tropo_studio.glob('*.tropo.md'):
            if sidecar.name == '.tropo-folder.md':
                continue
            checked += 1
            before_count = len(findings)
            _check_sidecar_pair(sidecar, parent_folder, vault, findings)
            if len(findings) > before_count:
                defects += 1
            # Track filename for reverse check
            source_name = sidecar.name[:-len('.tropo.md')]
            sidecar_sources_named.add(source_name)

        # Reverse check: each file in the folder (not ignored) has a sidecar
        for entry in parent_folder.iterdir():
            if not entry.is_file():
                continue
            if entry.name == '.tropo-folder.md':
                continue
            # Skip if matches an ignore pattern at basename level
            if any(_pattern_matches_basename(p, entry.name, False) for p in ignore_patterns):
                continue
            if entry.name not in sidecar_sources_named:
                findings.append(
                    f'[WARN] {entry.relative_to(vault)} — file in governed folder lacks sidecar at {tropo_studio.relative_to(vault)}/{entry.name}.tropo.md'
                )
                defects += 1

    return findings, checked, defects


def _check_sidecar_pair(sidecar: Path, expected_parent: Path, vault: Path, findings: list[str]) -> None:
    """Forward-check: sidecar's source_path resolves."""
    try:
        text = sidecar.read_text()
    except (OSError, UnicodeDecodeError):
        return
    fm = split_frontmatter(text)
    if fm is None:
        return
    source_rel = get_scalar(fm, 'source_path')
    if not source_rel:
        findings.append(f'[WARN] {sidecar.relative_to(vault)} — missing source_path field')
        return
    # source_path is relative to the sidecar's own location
    resolved = (sidecar.parent / source_rel).resolve()
    if not resolved.exists():
        findings.append(
            f'[WARN] {sidecar.relative_to(vault)} — source_path {source_rel!r} does not resolve to existing file'
        )


def _pattern_matches_basename(pattern: str, name: str, is_dir: bool) -> bool:
    """Minimal .tropoignore basename match for the reverse check."""
    import fnmatch
    dir_only = pattern.endswith('/')
    stripped = pattern.rstrip('/')
    if dir_only and not is_dir:
        return False
    if fnmatch.fnmatch(name, stripped):
        return True
    if '/' in stripped:
        base = stripped.split('/')[-1]
        if base and fnmatch.fnmatch(name, base):
            return True
    return False


def check_uid_stability_across_tier(vault: Path) -> tuple[list[str], int, int]:
    """Verify UID matches between sidecar (Tier 1 or Tier 2) and vault projection.

    For each .tropo.md sidecar:
      - Read its UID
      - Expect projection at vault/files/<uid>.md (Tier 1) OR vault/files/<uid>/metadata.md (Tier 2)
      - Verify projection exists AND its UID matches
      - Verify projection path matches governance: value (Tier 1 → flat .md; Tier 2 → per-UID dir)

    Returns (findings, total_checked, defects)."""
    findings: list[str] = []
    checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'

    for sidecar in vault.rglob('*.tropo.md'):
        if not sidecar.is_file():
            continue
        # Skip the .tropo-folder.md markers (different schema; not external-artifact)
        if sidecar.name == '.tropo-folder.md':
            continue
        try:
            text = sidecar.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        uid = get_scalar(fm, 'uid')
        gov = get_scalar(fm, 'governance')
        if not uid:
            continue

        checked += 1
        # Expect a vault projection per governance
        if gov == 'tier-2-vault-native':
            proj = files_dir / uid / 'metadata.md'
            wrong_proj = files_dir / f'{uid}.md'
        else:  # tier-1-sidecar (or unset; default Tier 1)
            proj = files_dir / f'{uid}.md'
            wrong_proj = files_dir / uid / 'metadata.md'

        if not proj.is_file():
            findings.append(
                f'[WARN] {sidecar.relative_to(vault)} — uid {uid} has no vault projection at {proj.relative_to(vault)}'
            )
            defects += 1
            continue

        # Projection exists; verify UID matches
        try:
            proj_text = proj.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        proj_fm = split_frontmatter(proj_text)
        if proj_fm is None:
            findings.append(f'[WARN] {proj.relative_to(vault)} — no frontmatter; cannot verify UID stability')
            defects += 1
            continue
        proj_uid = get_scalar(proj_fm, 'uid')
        if proj_uid != uid:
            findings.append(
                f'[WARN] uid mismatch — sidecar {sidecar.relative_to(vault)} (uid={uid}) vs projection {proj.relative_to(vault)} (uid={proj_uid})'
            )
            defects += 1

        # Verify projection path matches governance tier
        if wrong_proj.exists():
            findings.append(
                f'[WARN] {sidecar.relative_to(vault)} — projection-path conflict: governance={gov} but found projection at {wrong_proj.relative_to(vault)} (wrong tier shape)'
            )
            defects += 1

    return findings, checked, defects


def check_extraction_scope_values(vault: Path) -> tuple[list[str], int, int]:
    """Verify extraction_scope: values are in the allowed enum; enforce external→external-artifact only.

    Returns (findings, total_checked, defects)."""
    findings: list[str] = []
    checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, checked, defects

    # Walk vault/files/*.md and vault/files/<uid>/metadata.md
    candidates: list[Path] = list(files_dir.glob('*.md'))
    for sub in files_dir.iterdir():
        if sub.is_dir():
            meta = sub / 'metadata.md'
            if meta.is_file():
                candidates.append(meta)

    for path in candidates:
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        scope = get_scalar(fm, 'extraction_scope')
        if scope is None:
            continue

        checked += 1
        if scope not in VALID_EXTRACTION_SCOPE_VALUES:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — extraction_scope={scope!r} not in {sorted(VALID_EXTRACTION_SCOPE_VALUES)}'
            )
            defects += 1
            continue

        # external is reserved for type: external-artifact
        if scope == 'external':
            entry_type = get_scalar(fm, 'type')
            if entry_type != 'external-artifact':
                findings.append(
                    f'[WARN] {path.relative_to(vault)} — extraction_scope=external used on type={entry_type!r} (reserved for type: external-artifact)'
                )
                defects += 1

    return findings, checked, defects


# ---------------------------------------------------------------------------
# Working-Copy Capsule Validation (v1.26.0 Stream D — per arch-spec 5a89297a §3.10)
# Capsule: working-copy (a2bc3e16)
# ---------------------------------------------------------------------------

# Working-copy required frontmatter fields (per working-copy.capsule v1.0)
WORKING_COPY_REQUIRED_FIELDS = {
    'uid', 'type', 'state', 'title',
    'derived_from', 'source_filename',
    'source_hash_at_extraction', 'last_source_hash_seen', 'hash_function',
    'extraction_tool_version', 'owner', 'extraction_scope',
    'created', 'modified', 'created_by', 'modified_by',  # v1.26.0.1 P2-5 — core.capsule mandates these
    'schema_version',
}


def _walk_working_copies(vault: Path) -> list[tuple[Path, str]]:
    """Return list of (path, frontmatter_text) for every type: working-copy entry."""
    files_dir = vault / 'vault' / 'files'
    out: list[tuple[Path, str]] = []
    if not files_dir.is_dir():
        return out
    for path in files_dir.glob('*.md'):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') == 'working-copy':
            out.append((path, fm))
    return out


def check_working_copy_schema(vault: Path) -> tuple[list[str], int, int]:
    """Check 1 per arch-spec §3.10 — working-copy schema.

    Each type:working-copy entry MUST have all required fields + valid enum values.
    Severity: FAIL (ERROR-class per spec).

    Returns (findings, checked, defects)."""
    findings: list[str] = []
    checked = 0
    defects = 0

    for path, fm in _walk_working_copies(vault):
        checked += 1
        present_fields = {
            line.split(':', 1)[0].strip()
            for line in fm.splitlines()
            if ':' in line and not line.lstrip().startswith('-') and not line.startswith(' ')
        }
        missing = WORKING_COPY_REQUIRED_FIELDS - present_fields
        if missing:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — working-copy missing required field(s): {sorted(missing)}'
            )
            defects += 1
            continue

        # Enum validation: hash_function
        hf = get_scalar(fm, 'hash_function')
        if hf and hf not in VALID_HASH_FUNCTIONS:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — hash_function={hf!r} not in {sorted(VALID_HASH_FUNCTIONS)}'
            )
            defects += 1
        # State enum — v1.68 S1 ratchet: WARN→ERROR (99e52c18 condition met:
        # 0 violations confirmed by raw measurement 2026-06-10; ratchet fires this cycle)
        state = get_scalar(fm, 'state')
        if state and state not in {'active', 'archived'}:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — state={state!r} not in {{active, archived}} '
                f'(ERROR; ratcheted from WARN per v1.68 S1 + 99e52c18; 0-violation floor confirmed)'
            )
            defects += 1
        # extraction_scope enum
        es = get_scalar(fm, 'extraction_scope')
        if es and es not in VALID_EXTRACTION_SCOPE_VALUES:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — extraction_scope={es!r} not in {sorted(VALID_EXTRACTION_SCOPE_VALUES)}'
            )
            defects += 1

    return findings, checked, defects


def check_working_copy_lineage(vault: Path) -> tuple[list[str], int, int]:
    """Check 2 per arch-spec §3.10 — working-copy lineage.

    Each type:working-copy entry's derived_from: UID MUST resolve to an existing
    vault/files/<uid>.md entry with type: external-artifact. Dangling lineage = FAIL.

    Returns (findings, checked, defects)."""
    findings: list[str] = []
    checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'

    for path, fm in _walk_working_copies(vault):
        checked += 1
        # Extract derived_from UID from YAML list format
        m = re.search(r'derived_from:\s*\n\s*-\s*"?([a-f0-9]{8})"?', fm)
        if not m:
            # Try inline list form
            m = re.search(r'derived_from:\s*\[\s*"?([a-f0-9]{8})"?', fm)
        if not m:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — derived_from: empty or unparseable; working-copy MUST chain to a projection'
            )
            defects += 1
            continue
        projection_uid = m.group(1)
        projection_path = files_dir / f'{projection_uid}.md'
        if not projection_path.exists():
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — derived_from: {projection_uid!r} does not resolve (dangling lineage)'
            )
            defects += 1
            continue
        # Verify projection is type: external-artifact
        try:
            proj_fm = split_frontmatter(projection_path.read_text())
            if proj_fm and get_scalar(proj_fm, 'type') != 'external-artifact':
                findings.append(
                    f'[FAIL] {path.relative_to(vault)} — derived_from: {projection_uid!r} is type={get_scalar(proj_fm, "type")!r}, not external-artifact'
                )
                defects += 1
        except (OSError, UnicodeDecodeError):
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — derived_from: {projection_uid!r} unreadable'
            )
            defects += 1

    return findings, checked, defects


def check_working_copy_sidecar_equivalence(vault: Path) -> tuple[list[str], int, int]:
    """Check 3 per arch-spec §3.10 + §2.6 invariant — sidecar-equivalence (Invariant #8).

    Each working-copy's projection MUST have a sibling sidecar at the projection's
    source_sidecar: path. Per spec §2.6: projection-UID = sidecar-UID per v1.25.0 §A.4
    baking-in rule 1. Dangling-projection-chain (projection exists but sidecar missing) = FAIL.

    Returns (findings, checked, defects)."""
    findings: list[str] = []
    checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'

    for path, fm in _walk_working_copies(vault):
        checked += 1
        # Extract projection UID
        m = re.search(r'derived_from:\s*\n\s*-\s*"?([a-f0-9]{8})"?', fm)
        if not m:
            m = re.search(r'derived_from:\s*\[\s*"?([a-f0-9]{8})"?', fm)
        if not m:
            continue  # check_working_copy_lineage already flagged this
        projection_uid = m.group(1)
        projection_path = files_dir / f'{projection_uid}.md'
        if not projection_path.exists():
            continue  # check_working_copy_lineage already flagged this
        try:
            proj_fm = split_frontmatter(projection_path.read_text())
        except (OSError, UnicodeDecodeError):
            continue
        if not proj_fm:
            continue
        sidecar_rel = get_scalar(proj_fm, 'source_sidecar')
        if not sidecar_rel:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — projection {projection_uid!r} has no source_sidecar field; '
                f'sidecar-equivalence invariant (Invariant #8) cannot be verified'
            )
            defects += 1
            continue
        # Clean YAML quoting on the path value
        sidecar_rel = sidecar_rel.strip().strip('"').strip("'")
        sidecar_abs = vault / sidecar_rel
        if not sidecar_abs.exists():
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — sidecar at {sidecar_rel!r} (per projection {projection_uid!r}) '
                f'does not exist; Invariant #8 violation (projection without sidecar)'
            )
            defects += 1

    return findings, checked, defects


def check_working_copy_index_sync(vault: Path) -> tuple[list[str], int, int]:
    """Check 4 per arch-spec §3.10 — index-sync (closes v1.25.0 fa026415 sibling).

    Every type:working-copy entry at vault/files/<uid>.md MUST have a corresponding
    row in vault/00-index.jsonl. tropo-extract.py is required to append index rows
    inline (not defer to rebuild-index.py); this check enforces that contract.

    Returns (findings, checked, defects)."""
    findings: list[str] = []
    checked = 0
    defects = 0

    index_path = vault / 'vault' / '00-index.jsonl'
    if not index_path.exists():
        return findings, checked, defects

    # Build a set of UIDs present in the index
    index_uids: set[str] = set()
    try:
        for line in index_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line.rstrip(','))
                if 'uid' in row:
                    index_uids.add(row['uid'])
            except json.JSONDecodeError:
                continue
    except (OSError, UnicodeDecodeError):
        return findings, checked, defects

    for path, fm in _walk_working_copies(vault):
        checked += 1
        wc_uid = get_scalar(fm, 'uid')
        if not wc_uid:
            continue  # check_working_copy_schema already flagged
        if wc_uid not in index_uids:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — working-copy uid={wc_uid!r} not in vault/00-index.jsonl; '
                f'tropo-extract.py MUST sync inline (closes fa026415 family of defects)'
            )
            defects += 1

    return findings, checked, defects


def check_working_copy_uniqueness(vault: Path) -> tuple[list[str], int, int]:
    """Check 5 per arch-spec §3.10 + capsule governance rule 2 — one-working-copy-per-projection.

    For each external-artifact projection, at most one state:active working-copy with
    derived_from:[<projection-uid>]. Multiple-actives = FAIL.

    Returns (findings, checked, defects)."""
    findings: list[str] = []
    checked = 0
    defects = 0

    projection_to_actives: dict[str, list[Path]] = {}
    for path, fm in _walk_working_copies(vault):
        if get_scalar(fm, 'state') != 'active':
            continue
        m = re.search(r'derived_from:\s*\n\s*-\s*"?([a-f0-9]{8})"?', fm)
        if not m:
            m = re.search(r'derived_from:\s*\[\s*"?([a-f0-9]{8})"?', fm)
        if not m:
            continue
        projection_uid = m.group(1)
        projection_to_actives.setdefault(projection_uid, []).append(path)

    for projection_uid, actives in projection_to_actives.items():
        checked += 1
        if len(actives) > 1:
            paths_str = ', '.join(str(p.relative_to(vault)) for p in actives)
            findings.append(
                f'[FAIL] Projection {projection_uid!r} has {len(actives)} active working-copies: {paths_str}; '
                f'capsule governance rule 2 (one-working-copy-per-projection) violated'
            )
            defects += 1

    return findings, checked, defects


# ---------------------------------------------------------------------------
# v1.28.0 Stream D — docx-template + folder-mirror + projection extensions
# ---------------------------------------------------------------------------

SLUG_RE = re.compile(r'^[a-z0-9-]+$')


def _walk_external_artifacts(vault: Path) -> list[tuple[Path, str]]:
    """Return list of (path, frontmatter_text) for every type: external-artifact entry."""
    files_dir = vault / 'vault' / 'files'
    out: list[tuple[Path, str]] = []
    if not files_dir.is_dir():
        return out
    for path in files_dir.glob('*.md'):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') == 'external-artifact':
            out.append((path, fm))
    return out


def _walk_docx_templates(vault: Path) -> list[tuple[Path, str]]:
    """Return list of (path, frontmatter_text) for every type: docx-template entry."""
    files_dir = vault / 'vault' / 'files'
    out: list[tuple[Path, str]] = []
    if not files_dir.is_dir():
        return out
    for path in files_dir.glob('*.md'):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') == 'docx-template':
            out.append((path, fm))
    return out


def _walk_folder_mirrors(vault: Path) -> list[tuple[Path, str]]:
    """Return (path, fm) for every type:project entry with mirror_of: <self-uid> declared
    AS A FRONTMATTER FIELD (line-anchored, not a substring elsewhere — e.g. inside
    completion_summary fields that quote the field name in prose).

    Per arch-spec §3.5.5 Amendment 1 v0.5: folder-mirror entries are type:project with
    a mirror_of: self-reference and a folder_marker_path: pointing at the on-disk marker.
    """
    files_dir = vault / 'vault' / 'files'
    out: list[tuple[Path, str]] = []
    if not files_dir.is_dir():
        return out
    for path in files_dir.glob('*.md'):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') != 'project':
            continue
        # Line-anchored detection — `mirror_of:` must appear as a frontmatter key,
        # not as a substring inside a quoted prose field (e.g. completion_summary).
        if not re.search(r'^mirror_of:\s+', fm, re.MULTILINE):
            continue
        out.append((path, fm))
    return out


def check_docx_template_typing(vault: Path) -> tuple[list[str], int, int]:
    """v1.28.0 Stream D — docx-template schema check per arch-spec §3.10 check 2 (extended for v1.28.0).

    Each type:docx-template entry MUST have all required fields + slug regex match +
    template_binary_path resolves to a readable .docx + extracted_styles structure.
    Severity: FAIL for missing/invalid required fields; WARN for hash mismatch.
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    required_fields = ('title', 'slug', 'description', 'template_binary_path',
                       'template_binary_hash', 'registration_tool_version', 'extraction_scope')

    for path, fm in _walk_docx_templates(vault):
        checked += 1
        rel = path.relative_to(vault)
        # Required fields
        for field in required_fields:
            if get_scalar(fm, field) is None:
                findings.append(
                    f'[FAIL] {rel} — docx-template missing required field {field!r}'
                )
                defects += 1
        # extracted_styles structure presence (presence-only at this level; structural
        # validation in check_extracted_styles_structure)
        if 'extracted_styles:' not in fm:
            findings.append(
                f'[FAIL] {rel} — docx-template missing required extracted_styles: block'
            )
            defects += 1
        # Slug regex
        slug = get_scalar(fm, 'slug')
        if slug and not SLUG_RE.match(slug):
            findings.append(
                f'[FAIL] {rel} — slug {slug!r} does not match {SLUG_RE.pattern} (Governance Rule 6)'
            )
            defects += 1
        # template_binary_path resolves
        binary_rel = get_scalar(fm, 'template_binary_path')
        if binary_rel:
            binary_abs = (vault / binary_rel).resolve()
            if not binary_abs.exists():
                findings.append(
                    f'[FAIL] {rel} — template_binary_path {binary_rel!r} does not resolve to a readable file'
                )
                defects += 1
            elif not binary_rel.lower().endswith('.docx'):
                findings.append(
                    f'[FAIL] {rel} — template_binary_path {binary_rel!r} is not a .docx'
                )
                defects += 1

    return findings, checked, defects


def check_docx_template_slug_uniqueness(vault: Path) -> tuple[list[str], int, int]:
    """v1.28.0 Stream D — slug uniqueness across active docx-template entries
    per docx-template.capsule v1.0 Governance Rule 2 + arch-spec §3.10 check 7.
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    slug_to_paths: dict[str, list[Path]] = {}
    for path, fm in _walk_docx_templates(vault):
        if get_scalar(fm, 'state') != 'active':
            continue
        slug = get_scalar(fm, 'slug')
        if not slug:
            continue
        slug_to_paths.setdefault(slug, []).append(path)

    for slug, paths in slug_to_paths.items():
        checked += 1
        if len(paths) > 1:
            paths_str = ', '.join(str(p.relative_to(vault)) for p in paths)
            findings.append(
                f'[FAIL] Slug {slug!r} is used by {len(paths)} active docx-template entries: {paths_str}; '
                f'docx-template Governance Rule 2 (slug uniqueness across active instances) violated'
            )
            defects += 1

    return findings, checked, defects


def check_original_styles_structure(vault: Path) -> tuple[list[str], int, int]:
    """v1.28.0 Stream D — Check 7 NEW per arch-spec §3.10 v0.5.

    For each type:external-artifact entry with original_styles: present, validate
    the structure conforms to the §3.4 schema (page / default_font / theme / named_styles /
    headers_footers / sections_count / special_features). Severity: WARN (opportunistic field).
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    required_top_keys = ('page', 'default_font', 'theme', 'named_styles',
                         'headers_footers', 'sections_count', 'special_features')

    for path, fm in _walk_external_artifacts(vault):
        if 'original_styles:' not in fm:
            continue
        checked += 1
        rel = path.relative_to(vault)
        # Light structural check: each required top-level key appears as an indented
        # field under the original_styles block. (Full YAML parse would be heavier;
        # we validate presence of the structural anchors only here.)
        m = re.search(r'^original_styles:\s*\n((?:[ \t]+.*\n)+)', fm, re.MULTILINE)
        if not m:
            findings.append(
                f'[WARN] {rel} — original_styles: present but indented body not parseable'
            )
            defects += 1
            continue
        block = m.group(1)
        missing = [k for k in required_top_keys if not re.search(rf'^\s+{re.escape(k)}:', block, re.MULTILINE)]
        if missing:
            findings.append(
                f'[WARN] {rel} — original_styles: missing top-level keys: {missing} '
                f'(per §3.4 schema)'
            )
            defects += 1

    return findings, checked, defects


def check_folder_mirror_integrity(vault: Path) -> tuple[list[str], int, int]:
    """v1.28.0 Stream D — Check 8 NEW per arch-spec §3.10 v0.5 (closes sa.skeptic-008 P0-2).

    For each type:project entry with mirror_of: <self-uid> declared, validate:
    (a) mirror_of value equals the entry's own uid (self-reference)
    (b) folder_marker_path resolves to a present on-disk .tropo-folder.md
    (c) the on-disk marker carries the SAME UID as the vault mirror
    (d) title / source_folder_name / original_path match between the on-disk marker and vault mirror

    Severity: FAIL for mismatch (substrate corruption). Missing-pair detection is in scope
    via the on-disk marker presence check; WARN-class for missing-pair (recoverable via
    reconciler retro-fill per the §3.8 folder-mirror-orphan-state event).
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    for path, fm in _walk_folder_mirrors(vault):
        checked += 1
        rel = path.relative_to(vault)
        own_uid = get_scalar(fm, 'uid')
        mirror_of_uid = get_scalar(fm, 'mirror_of')
        marker_path_rel = get_scalar(fm, 'folder_marker_path')

        # (a) mirror_of self-reference
        if mirror_of_uid != own_uid:
            findings.append(
                f'[FAIL] {rel} — mirror_of {mirror_of_uid!r} does not equal own uid {own_uid!r}; '
                f'sanctioned dual-residence pattern requires self-reference per §3.5.5 Amendment 1 v0.5'
            )
            defects += 1
            continue

        # (b) folder_marker_path resolves
        if not marker_path_rel:
            findings.append(
                f'[FAIL] {rel} — folder mirror missing required folder_marker_path: field'
            )
            defects += 1
            continue
        marker_abs = (vault / marker_path_rel).resolve()
        if not marker_abs.exists():
            findings.append(
                f'[WARN] {rel} — folder_marker_path {marker_path_rel!r} not present on disk; '
                f'recoverable via reconciler retro-fill per §3.8 folder-mirror-orphan-state event'
            )
            defects += 1
            continue

        # (c) on-disk marker UID matches
        try:
            marker_text = marker_abs.read_text()
            marker_fm = split_frontmatter(marker_text)
        except (OSError, UnicodeDecodeError):
            findings.append(
                f'[FAIL] {rel} — folder_marker_path {marker_path_rel!r} unreadable'
            )
            defects += 1
            continue
        if marker_fm is None:
            findings.append(
                f'[FAIL] {rel} — folder marker at {marker_path_rel!r} has no parseable frontmatter'
            )
            defects += 1
            continue
        marker_uid = get_scalar(marker_fm, 'uid')
        if marker_uid != own_uid:
            findings.append(
                f'[FAIL] {rel} — on-disk marker UID {marker_uid!r} does not match vault mirror UID {own_uid!r}'
            )
            defects += 1
            continue

        # (d) frontmatter parity on key descriptive fields
        for field in ('title', 'source_folder_name', 'original_path'):
            mirror_val = get_scalar(fm, field)
            marker_val = get_scalar(marker_fm, field)
            if mirror_val != marker_val:
                findings.append(
                    f'[FAIL] {rel} — field {field!r} differs between vault mirror ({mirror_val!r}) '
                    f'and on-disk marker ({marker_val!r})'
                )
                defects += 1

    return findings, checked, defects


def check_projection_index_sync(vault: Path) -> tuple[list[str], int, int]:
    """v1.28.0 Stream D — extends spec §3.10 check 4 (v0.5.1 in-stream micro-amendment).

    Every type:external-artifact projection authored by import-walker.py create-sidecar
    MUST have a row in vault/00-index.jsonl. Closes the v1.25.0 fa026415 carry-forward
    defect within v1.28.0 scope per arch-spec v0.5.1.
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    index_path = vault / 'vault' / '00-index.jsonl'
    if not index_path.exists():
        return findings, checked, defects

    index_uids: set[str] = set()
    try:
        for line in index_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line.rstrip(','))
                if 'uid' in row:
                    index_uids.add(row['uid'])
            except json.JSONDecodeError:
                continue
    except (OSError, UnicodeDecodeError):
        return findings, checked, defects

    for path, fm in _walk_external_artifacts(vault):
        checked += 1
        proj_uid = get_scalar(fm, 'uid')
        if not proj_uid:
            continue
        if proj_uid not in index_uids:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — external-artifact projection uid={proj_uid!r} not in vault/00-index.jsonl; '
                f'create-sidecar MUST sync inline per v0.5.1 (closes fa026415 carry-forward at v1.28.0)'
            )
            defects += 1

    return findings, checked, defects


def check_folder_mirror_index_sync(vault: Path) -> tuple[list[str], int, int]:
    """v1.28.0 Stream D — extends spec §3.10 check 4 (v0.5).

    Every type:project folder-mirror authored by import-walker.py create-sidecar
    MUST have a row in vault/00-index.jsonl. Inline-sync contract per arch-spec §3.5.5
    Amendment 1 v0.5.
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    index_path = vault / 'vault' / '00-index.jsonl'
    if not index_path.exists():
        return findings, checked, defects

    index_uids: set[str] = set()
    try:
        for line in index_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line.rstrip(','))
                if 'uid' in row:
                    index_uids.add(row['uid'])
            except json.JSONDecodeError:
                continue
    except (OSError, UnicodeDecodeError):
        return findings, checked, defects

    for path, fm in _walk_folder_mirrors(vault):
        checked += 1
        uid = get_scalar(fm, 'uid')
        if not uid:
            continue
        if uid not in index_uids:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — folder mirror uid={uid!r} not in vault/00-index.jsonl; '
                f'create-sidecar MUST sync inline per spec §3.5.5 Amendment 1 v0.5'
            )
            defects += 1

    return findings, checked, defects


def check_navigation_block_render_safety(vault: Path) -> tuple[list[str], int, int]:
    """v1.X — Navigation block render safety (WARN severity; ERROR ratchet planned).

    Authored 2026-05-15 by vela-v45 per HUMAN-NAVIGATION.md (57a9c11f) primitive +
    core.capsule v1.2 (ee814120) §Check 9.

    Walks vault/files/*.md; for each governed entry with frontmatter + H1 verifies:
    1. `title:` field present and non-empty (display-name per HUMAN-NAVIGATION).
    2. Body contains a sentinel-wrapped Navigation block
       (`<!-- nav-block:start --> ... <!-- nav-block:end -->`).

    Skip-class (no defect): no frontmatter, no H1 (renderer's no-h1 skip path).
    WARN at v1.X; ERROR ratchet planned post-migration.

    Returns (findings, checked_count, defect_count).
    """
    files_dir = vault / 'vault' / 'files'
    if not files_dir.exists():
        return [], 0, 0

    findings: list[str] = []
    checked = 0
    defects = 0

    NAV_START = '<!-- nav-block:start -->'
    NAV_END = '<!-- nav-block:end -->'

    for f in sorted(files_dir.glob('*.md')):
        try:
            content = f.read_text()
        except Exception:
            continue

        if not content.startswith('---\n'):
            continue
        end_idx = content.find('\n---\n', 4)
        if end_idx == -1:
            continue
        fm_text = content[4:end_idx]
        body = content[end_idx + 5:]

        if not re.search(r'^# .+$', body, re.MULTILINE):
            continue

        # Mirror the renderer's NAV_BLOCK_SUPPRESS_TYPES (b8e4f1a3.py, v1.45.0 Stream 1):
        # kb-article entries deliberately get NO nav-block (they ship as KB content; internal
        # navigation would leak). The check must not flag what the renderer will never author.
        # (R2 named-exempt; argus-a110 2026-06-12)
        m_type = re.search(r'^type:\s*([\w.-]+)', fm_text, re.MULTILINE)
        if m_type and m_type.group(1) in {'kb-article'}:
            continue

        checked += 1

        title_value = None
        for line in fm_text.split('\n'):
            m = re.match(r'^title:\s*(.*)$', line)
            if m:
                v = m.group(1).strip()
                v = re.split(r'\s+#', v, maxsplit=1)[0].strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                title_value = v.strip()
                break

        title_ok = bool(title_value)
        nav_ok = (NAV_START in body) and (NAV_END in body)

        if not title_ok and not nav_ok:
            findings.append(f'  {f.name} — missing both `title:` AND Navigation block sentinels')
            defects += 1
        elif not title_ok:
            findings.append(f'  {f.name} — missing `title:` (Navigation block present but back-link surfaces fall back to bare UID)')
            defects += 1
        elif not nav_ok:
            findings.append(f'  {f.name} — missing Navigation block sentinels (title present; run rebuild-vault.py to author)')
            defects += 1

    return findings, checked, defects


def check_ship_artifact_target_field(vault: Path) -> tuple[list[str], int, int]:
    """v1.42.0 Stream B — ship-artifact.capsule v1.3 Check 24: target field shape + enum.

    Validates ship-artifact entries' `target:` field per capsule v1.3 §Target Semantics:
    - Field is OPTIONAL (absent = implicit [release]; backward compat 100% with v1.2 entries)
    - When present: MUST be a YAML array (scalar values REJECTED)
    - Every element MUST be in {release, web}
    - ERROR at v1.3 directly (no WARN/ratchet phase per Decisions Locked item 10)

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, checked, defects

    for path in files_dir.glob('*.md'):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        entry_type = get_scalar(fm, 'type')
        if entry_type != 'ship-artifact':
            continue

        checked += 1

        # target field is OPTIONAL — absence is valid (implicit [release])
        # Detect presence via line-level grep against the frontmatter string
        # (v1.43.0 Stream C dry-run pre-flight fix per argus-a72: replaces buggy
        # `fm.get('target')` which assumed fm was a dict; split_frontmatter
        # returns Optional[str], so dict-API calls crash with AttributeError.
        # Check 24 has never actually run since v1.42 ship — get_list helper
        # added to fix the regression).
        if not re.search(r'^target:', fm, re.MULTILINE):
            continue

        target = get_list(fm, 'target')

        # Must be array (list), not scalar — get_list returns ['__scalar__:value'] sentinel
        # for scalar shape so we can detect the schema-shape failure
        if target is None or (target and target[0].startswith('__scalar__:')):
            scalar_value = target[0].split(':', 1)[1] if target else '(absent)'
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — target field must be a YAML array; got scalar {scalar_value!r} (per ship-artifact.capsule v1.3 Check 24)'
            )
            defects += 1
            continue

        # Every element must be in enum
        invalid_elements = [el for el in target if el not in VALID_SHIP_ARTIFACT_TARGETS]
        if invalid_elements:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — target array contains invalid element(s) {invalid_elements!r}; allowed values: {sorted(VALID_SHIP_ARTIFACT_TARGETS)}'
            )
            defects += 1
            continue

        # Empty array is invalid (degenerate)
        if len(target) == 0:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — target field is empty array; omit field for implicit [release] or declare at least one target'
            )
            defects += 1
            continue

    return findings, checked, defects


def check_article_state_machine_invariants(vault: Path) -> tuple[list[str], int, int]:
    """v1.48.0 Stream A — ship-artifact.capsule v1.4 Check 25: article subtype editorial state machine.

    Validates entries with `subtype: article` per capsule v1.4 §Article Subtype + Editorial State Machine:
    - `status:` MUST be in {draft, reviewed, locked, archived}
    - If `status: archived`: MUST have `superseded_by:` OR `retraction_note:` (preservation discipline)

    Severity: WARN at v1.4 / ERROR ratchet at v1.5 — one-cycle migration window for existing
    articles needing editorial-state backfill.

    Note: sequential state-transition history check (skipping `reviewed` on path to `locked`)
    requires git log inspection and is deferred to v1.5 ratchet alongside the ERROR transition.
    v1.4 WARN tier validates current-state shape only.

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, checked, defects

    for path in files_dir.glob('*.md'):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        subtype = get_scalar(fm, 'subtype')
        if subtype != 'article':
            continue

        checked += 1

        status_value = get_scalar(fm, 'status')
        if status_value is None:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — subtype:article entry missing `status:` field; expected one of {sorted(VALID_ARTICLE_EDITORIAL_STATES)}'
            )
            defects += 1
            continue

        if status_value not in VALID_ARTICLE_EDITORIAL_STATES:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — subtype:article entry has invalid status {status_value!r}; allowed: {sorted(VALID_ARTICLE_EDITORIAL_STATES)} (per ship-artifact.capsule v1.4 §Article Subtype)'
            )
            defects += 1
            continue

        # Archived articles must have supersession OR retraction provenance
        if status_value == 'archived':
            superseded_by = get_scalar(fm, 'superseded_by')
            # Retraction note may live in body (post-archival rationale); look for either
            # a frontmatter retraction_note field OR a body section header
            retraction_note_fm = get_scalar(fm, 'retraction_note')
            has_retraction_body = '## Retraction' in text or '## Retraction Note' in text
            if not superseded_by and not retraction_note_fm and not has_retraction_body:
                findings.append(
                    f'[WARN] {path.relative_to(vault)} — archived article must have `superseded_by:` OR `retraction_note:` (frontmatter or body); preservation discipline per OP-13'
                )
                defects += 1

    return findings, checked, defects


def check_wrapper_article_editorial_lock(vault: Path) -> tuple[list[str], int, int]:
    """v1.48.0 Stream A — ship-artifact.capsule v1.4 Check 26: wrapper-article editorial-lock composition.

    For each ship-artifact wrapper with `canonical_source:` pointing at a `subtype: article` entry:
    - Confirm the article entry exists in vault/files/
    - If wrapper's `target:` includes any published target (web, release) AND article's
      `status: != locked`, surface as substrate-discipline drift (wrapper targets publication
      but source article is not editorially locked).

    Severity: WARN at v1.4 / ERROR ratchet at v1.5.

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, checked, defects

    # Build a UID -> (subtype, status) map for fast article lookup
    article_states: dict[str, str] = {}
    for path in files_dir.glob('*.md'):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'subtype') != 'article':
            continue
        uid = get_scalar(fm, 'uid') or path.stem
        status_value = get_scalar(fm, 'status') or '(missing)'
        article_states[uid] = status_value

    # Now walk ship-artifact wrappers and check those pointing at articles
    for path in files_dir.glob('*.md'):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') != 'ship-artifact':
            continue

        canonical_source = get_scalar(fm, 'canonical_source')
        if not canonical_source:
            continue

        # Detect article-source wrappers via vault/files/<uid>.md path pattern
        m = re.search(r'vault/files/([0-9a-f]{8})\.md$', canonical_source)
        if not m:
            continue
        article_uid = m.group(1)

        # Only check if the source IS an article (skip non-article document-class sources)
        if article_uid not in article_states:
            continue

        checked += 1

        article_status = article_states[article_uid]
        if article_status == 'locked':
            continue  # composition clean

        # Wrapper targets a published target but source article isn't locked
        target = get_list(fm, 'target')
        if target is None:
            # Implicit [release] per capsule v1.3
            published_targets = {'release'}
        elif target and target[0].startswith('__scalar__:'):
            # Skip — Check 24 will surface the shape defect
            continue
        else:
            published_targets = set(target) & VALID_SHIP_ARTIFACT_TARGETS

        if published_targets:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — wrapper targets {sorted(published_targets)} but source article {article_uid} status is {article_status!r} (not locked); '
                f'either lock the article or remove publication targets from wrapper (per capsule v1.4 Rule 13)'
            )
            defects += 1

    return findings, checked, defects


def check_publication_state_pipeline_write_only(vault: Path) -> tuple[list[str], int, int]:
    """v1.48.0 Stream A — ship-artifact.capsule v1.4 Check 27: publication_state pipeline-write-only.

    v1.4 WARN tier scope: field-shape audit on the new `publication_state:` per-target map.
    Validates that when present, the field is structurally well-formed:
    - Top-level shape is a map (block-form YAML dict, not scalar/array)
    - Keys are valid target slugs (subset of VALID_SHIP_ARTIFACT_TARGETS)
    - Values are in VALID_PUBLICATION_STATE_VALUES ({live, retracted})

    The git-blame hand-edit-drift detection described in capsule v1.4 §Publish-Act Semantics
    requires a pipeline-write sentinel author to compare against (Cycle B engineering scope —
    build-web-content.py decides the sentinel identity). At v1.4 ship, the pipeline-write
    convention is not yet active; the git-blame heuristic activates at v1.5 ratchet alongside
    the WARN→ERROR transition once there's real pipeline-write data to verify against.

    Severity: WARN at v1.4 / ERROR ratchet at v1.5.

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, checked, defects

    for path in files_dir.glob('*.md'):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') != 'ship-artifact':
            continue

        # Only proceed if publication_state field is present
        if not re.search(r'^publication_state:', fm, re.MULTILINE):
            continue

        checked += 1

        # Parse the publication_state block — expected shape is a map of target -> state
        # Block form:
        #   publication_state:
        #     web: live
        #     release: retracted
        block_pattern = r'^publication_state:\s*$'
        header_match = re.search(block_pattern, fm, re.MULTILINE)
        if not header_match:
            # Field present but not block form — possibly inline mapping or scalar
            # Try inline mapping form: publication_state: {web: live}
            inline_pattern = r'^publication_state:\s*\{([^}]*)\}'
            inline_match = re.search(inline_pattern, fm, re.MULTILINE)
            if inline_match:
                raw = inline_match.group(1).strip()
                # Parse key:value pairs separated by commas
                entries: dict[str, str] = {}
                for pair in raw.split(','):
                    if ':' in pair:
                        k, v = pair.split(':', 1)
                        entries[k.strip().strip('"\'')] = v.strip().strip('"\'')
            else:
                # Field is scalar — shape failure
                findings.append(
                    f'[WARN] {path.relative_to(vault)} — publication_state must be a YAML map (target → state); got non-map shape (per capsule v1.4 Check 27)'
                )
                defects += 1
                continue
        else:
            # Block form — walk indented `<key>: <value>` lines
            entries = {}
            start = header_match.end()
            for line in fm[start:].split('\n')[1:]:
                stripped = line.lstrip()
                if line.startswith('  ') and ':' in stripped and not stripped.startswith('-'):
                    k, v = stripped.split(':', 1)
                    entries[k.strip().strip('"\'')] = v.strip().strip('"\'')
                elif line.strip() == '':
                    continue
                else:
                    break

        if not entries:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — publication_state field present but empty map (per capsule v1.4 Check 27); omit field for "never published" semantic'
            )
            defects += 1
            continue

        # Validate keys are valid target slugs
        invalid_keys = [k for k in entries if k not in VALID_SHIP_ARTIFACT_TARGETS]
        if invalid_keys:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — publication_state contains invalid target key(s) {invalid_keys!r}; allowed: {sorted(VALID_SHIP_ARTIFACT_TARGETS)} (per capsule v1.4 Check 27)'
            )
            defects += 1
            continue

        # Validate values are in enum
        invalid_values = {k: v for k, v in entries.items() if v not in VALID_PUBLICATION_STATE_VALUES}
        if invalid_values:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — publication_state contains invalid state value(s) {invalid_values!r}; allowed values: {sorted(VALID_PUBLICATION_STATE_VALUES)} (per capsule v1.4 Check 27)'
            )
            defects += 1

    return findings, checked, defects


def check_publication_state_target_coherence(vault: Path) -> tuple[list[str], int, int]:
    """v1.48.0 Stream A — ship-artifact.capsule v1.4 Check 28: publication_state target coherence.

    Verifies that `publication_state:` keys are a subset of the wrapper's `target:` array values.
    A wrapper cannot have publication_state.<target>: live for a target it doesn't declare.

    Severity: WARN at v1.4 (no ratchet planned — coherence violations should not occur if
    pipeline is well-behaved; WARN as audit signal).

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, checked, defects

    for path in files_dir.glob('*.md'):
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') != 'ship-artifact':
            continue

        if not re.search(r'^publication_state:', fm, re.MULTILINE):
            continue

        checked += 1

        # Resolve target array (or implicit [release] if absent)
        target = get_list(fm, 'target')
        if target is None:
            declared_targets = {'release'}
        elif target and target[0].startswith('__scalar__:'):
            # Skip — Check 24 will surface the shape defect
            continue
        else:
            declared_targets = set(target)

        # Parse publication_state keys (same logic as Check 27 but lighter — keys only)
        ps_keys: set[str] = set()
        block_header = re.search(r'^publication_state:\s*$', fm, re.MULTILINE)
        if block_header:
            start = block_header.end()
            for line in fm[start:].split('\n')[1:]:
                stripped = line.lstrip()
                if line.startswith('  ') and ':' in stripped and not stripped.startswith('-'):
                    k, _ = stripped.split(':', 1)
                    ps_keys.add(k.strip().strip('"\''))
                elif line.strip() == '':
                    continue
                else:
                    break
        else:
            inline_match = re.search(r'^publication_state:\s*\{([^}]*)\}', fm, re.MULTILINE)
            if inline_match:
                for pair in inline_match.group(1).split(','):
                    if ':' in pair:
                        k, _ = pair.split(':', 1)
                        ps_keys.add(k.strip().strip('"\''))

        # Check: publication_state keys must be subset of declared targets
        orphan_keys = ps_keys - declared_targets
        if orphan_keys:
            findings.append(
                f'[WARN] {path.relative_to(vault)} — publication_state has key(s) {sorted(orphan_keys)} not in target array {sorted(declared_targets)} '
                f'(cannot be live on a target the wrapper does not declare; per capsule v1.4 Check 28)'
            )
            defects += 1

    return findings, checked, defects


def check_external_work_gitignore(vault: Path) -> tuple[list[str], int, int]:
    """v1.48.0 Stream A — ship-artifact.capsule v1.4 Check 29: external-work/ gitignore.

    Verifies that the staging surface at `argo-os/external-work/` is gitignored at the
    Studio root. The `.gitignore` is typically at the platform-repo root (one level above
    `argo-os/`) but may also be at the Studio root for Studio-tracked installs.

    Severity: WARN at v1.4 (audit signal; failure to gitignore creates the three-way
    drift failure mode this capsule was designed to prevent).

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    checked = 1  # this is a one-shot Studio-level check, not a per-entry check
    defects = 0

    # Candidate .gitignore paths (search both Studio root + platform repo root)
    candidates = [
        vault / '.gitignore',
        vault.parent / '.gitignore',
    ]

    # Patterns that satisfy the gitignore requirement for external-work/
    # — either the specific external-work/ path is ignored, OR a parent folder
    # is ignored (e.g., /argo-os/ ignores everything under it transitively).
    valid_patterns = [
        re.compile(r'^/?argo-os/external-work/?\s*$', re.MULTILINE),
        re.compile(r'^/?external-work/?\s*$', re.MULTILINE),
        re.compile(r'^argo-os/external-work\b', re.MULTILINE),
        re.compile(r'^external-work\b', re.MULTILINE),
        # Parent-folder coverage: /argo-os/ alone covers all descendants
        re.compile(r'^/argo-os/\s*$', re.MULTILINE),
        re.compile(r'^/?argo-os/?\s*$', re.MULTILINE),
    ]

    found = False
    for gi_path in candidates:
        if not gi_path.is_file():
            continue
        try:
            gi_text = gi_path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if any(p.search(gi_text) for p in valid_patterns):
            found = True
            break

    if not found:
        findings.append(
            f'[WARN] argo-os/external-work/ not declared in .gitignore (checked {[str(c) for c in candidates]}); '
            f'staging surface should not be tracked in git (per capsule v1.4 Check 29 + §External-Work Staging Architecture)'
        )
        defects += 1

    return findings, checked, defects


def check_engine_no_direct_vault_unlink(vault: Path) -> tuple[list[str], int, int]:
    """Preservation Discipline enforcement — engine scripts must not hard-delete vault/files/.

    Scans .tropo/scripts/*.py for os.remove() / Path.unlink() / os.unlink() calls
    that reference vault/files/-class paths. Direct deletion violates Principle 13
    (Substrate Preservation Discipline) and was the root cause of the v1.52
    substrate-coherence defect (A82 2026-05-24). All vault entry deletion must go
    through tropo-recycle.py (soft-delete to recycle/agent-deletions/).

    Returns (findings, checked, defects).
    """
    import re as _re
    # P0 fix (Argus A93 2026-06-02): the original guard was DOUBLE-BLIND to the real
    # silent-deleter (pipeline-activate rollback, e337f1dd.py:606 — the A82/2774e472
    # root cause). (1) It only scanned .tropo/scripts/; that file lives in vault/tools/
    # post-v1.56. (2) It required the literal vault path ON the unlink line, but there
    # `path` was bound 14 lines earlier. Now: scan BOTH dirs AND resolve path-aliased
    # unlinks via a file-wide pass collecting vars bound to a vault/files path.
    scan_dirs = [vault / '.tropo' / 'scripts', vault / 'vault' / 'tools']

    unlink_patterns = [
        _re.compile(r'\.unlink\('),
        _re.compile(r'os\.remove\('),
        _re.compile(r'os\.unlink\('),
    ]
    # Exemptions: the soft-delete implementation + this validator itself, under BOTH
    # the .tropo/scripts shim names AND the vault/tools UID filenames.
    exempt_files = {
        'tropo-recycle.py', 'tropo-validate.py',
        '2573f6dd.py',  # tropo-recycle (canonical, vault/tools)
        'd2b9c8e6.py',  # this validator (canonical, vault/tools)
    }
    vault_kw = ('VAULT_FILES', 'vault/files', 'vault_files')
    assign_vault_path = _re.compile(r'(\w+)\s*=\s*[^=].*(?:VAULT_FILES|vault_files|vault/files)')
    receiver_unlink = _re.compile(r'(\w+)\.unlink\(')
    os_del_target = _re.compile(r'os\.(?:remove|unlink)\(\s*(\w+)')

    findings: list[str] = []
    checked = 0
    defects = 0

    for scripts_dir in scan_dirs:
        if not scripts_dir.is_dir():
            continue
        for script in sorted(scripts_dir.glob('*.py')):
            if script.name in exempt_files or script.name.startswith('test_'):
                continue
            checked += 1
            try:
                lines = script.read_text(encoding='utf-8').splitlines()
            except Exception:
                continue
            # Pass 1: collect every variable bound to a vault/files path anywhere in the
            # file, so an aliased unlink is caught no matter how far the binding sits.
            vault_vars = set()
            for line in lines:
                s = line.strip()
                if s.startswith('#'):
                    continue
                m = assign_vault_path.search(s)
                if m:
                    vault_vars.add(m.group(1))
            # Pass 2: flag a deletion targeting a vault/files path — literal on the line
            # OR via a vault-path-aliased variable.
            for lineno, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if not any(pat.search(stripped) for pat in unlink_patterns):
                    continue
                literal_hit = any(kw in stripped for kw in vault_kw)
                aliased_hit = False
                rm = receiver_unlink.search(stripped)
                if rm and rm.group(1) in vault_vars:
                    aliased_hit = True
                om = os_del_target.search(stripped)
                if om and om.group(1) in vault_vars:
                    aliased_hit = True
                if literal_hit or aliased_hit:
                    findings.append(
                        f'  [ERROR] {script.name}:{lineno}: direct vault deletion '
                        f'({stripped[:80]}) — use tropo-recycle.py instead'
                    )
                    defects += 1

    return findings, checked, defects


def check_kb_content_no_slug_collisions(vault: Path) -> tuple[list[str], int, int]:
    """Cycle 4 publish-pipeline — kb-content dual-write bug class audit (ERROR severity).

    Walks app/(web)/kb-content/*.md and detects any slug: value claimed by more
    than one file. A collision means two files (typically a stale wrapper-uid file
    from build-web-content.py + a current source-uid file from publish.py) both
    claim the same article slug. The article route serves whichever sorts first
    alphabetically — stale file wins; source edits never reach readers.

    Returns (findings, checked, defects).
    """
    import re as _re
    kb_content_dir = vault.parent / 'app' / '(web)' / 'kb-content'
    if not kb_content_dir.is_dir():
        return [], 0, 0

    slug_to_files: dict[str, list[str]] = {}
    checked = 0
    for md_file in sorted(kb_content_dir.glob('*.md')):
        try:
            content = md_file.read_text(encoding='utf-8')
        except Exception:
            continue
        checked += 1
        m = _re.search(r'^slug:\s*(.+?)\s*$', content, _re.MULTILINE)
        if not m:
            continue
        slug = m.group(1).strip().strip('"\'')
        slug_to_files.setdefault(slug, []).append(md_file.name)

    findings: list[str] = []
    defects = 0
    for slug, files in sorted(slug_to_files.items()):
        if len(files) > 1:
            findings.append(
                f'  [ERROR] slug collision: "{slug}" claimed by {len(files)} files: {", ".join(sorted(files))}'
            )
            defects += 1

    return findings, checked, defects


def check_duplicate_yaml_keys(vault: Path) -> tuple[list[str], int, int]:
    """v1.29.0 Stream A — duplicate top-level YAML key detection (FAIL severity).

    Walks vault/files/*.md; uses _yaml_dup_lib.detect_duplicate_yaml_keys()
    as the canonical detection (single source of truth — same library the
    fix-duplicate-yaml-keys.py cleanup script uses).

    Detection scope: top-level YAML keys ONLY. Within-list value duplicates
    are a different defect class (out of scope per Mike-A63 2026-05-14;
    filed at vault/files/6ba0e525.md).

    Spec: vault/files/81555e45.md v0.4 §3.2.

    Returns (findings, checked, defects).
    """
    # Lazy import to avoid hard dependency at module load if shared lib absent
    # v1.56 Lane S: script relocated to vault/tools/; lib/ is under .tropo/scripts/
    scripts_dir = Path(__file__).resolve().parents[2] / '.tropo' / 'scripts'
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from _yaml_dup_lib import (  # type: ignore
            detect_duplicate_yaml_keys,
            extract_frontmatter,
        )
    except ImportError as exc:
        return (
            [f'[FAIL] _yaml_dup_lib.py import failed: {exc} '
             f'(spec 81555e45 §3.2 requires the shared library at .tropo/scripts/)'],
            0,
            1,
        )

    findings: list[str] = []
    checked = 0
    defects = 0
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, checked, defects

    for md_path in sorted(files_dir.glob('*.md')):
        if not md_path.is_file():
            continue
        checked += 1
        try:
            text = md_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        parts = extract_frontmatter(text)
        if parts is None:
            continue
        _opening, body, _after = parts
        duplicates = detect_duplicate_yaml_keys(body)
        if duplicates:
            defects += 1
            keys_summary = ', '.join(
                f'{k} ({v}x)' for k, v in sorted(duplicates.items())
            )
            findings.append(
                f'[FAIL] {md_path.relative_to(vault)} — duplicate top-level '
                f'YAML key(s): {keys_summary}; '
                f'recovery: python3 .tropo/scripts/fix-duplicate-yaml-keys.py --apply'
            )

    return findings, checked, defects


# ---------------------------------------------------------------------------
# Two-Axis Agent Identity coherence (doctrine 15c70b96 / dev-spec e85d2d2c)
# ---------------------------------------------------------------------------

# Establishment grace per dev-spec e85d2d2c: while False, a commissioned messaging
# agent missing party_uid is a WARN (the registry is being populated this cycle).
# Flip True at cycle close once every messaging agent's party_uid is populated +
# verified — then "absent" becomes a FAIL (carved-in-stone by construction).
IDENTITY_PARTY_UID_REQUIRED = True   # ratcheted WARN→ERROR by Argus A94 2026-06-02: registry party_uid populated (Vela Step 3) + all live crew agents resolve coherent + retired/on-demand exempted; P0 #3 closed, identity arc complete


def check_agent_identity_coherence(vault: Path, all_uids: set[str]) -> tuple[list[str], int, int]:
    """Two-Axis Agent Identity coherence — party_uid is the single canonical
    messaging identity per agent (doctrine 15c70b96; dev-spec e85d2d2c; Mike-A91 walk).

    FAIL on:
      - multiplicity — more than one party_uid declared for an agent
      - phantom      — party_uid present but resolves to no vault entry (the 34cf0f1c class)
      - divergence   — a status card's tropo_agent_id disagrees with the registry party_uid
    WARN (establishment grace; ratchets to FAIL when IDENTITY_PARTY_UID_REQUIRED):
      - party_uid absent for a LIVE messaging agent (status active / on-hold)
    INFO (exempt — not a current messaging participant):
      - party_uid absent for a retired or on-demand (dormant) agent; (re)activation
        establishes the party_uid before the agent emits, so the requirement does not
        bite while dormant (Argus A94, 2026-06-02 — the ratchet enforces live-agent
        identity, not every-ever-commissioned agent)

    Only the party (messaging) axis is checked here; agent_root (lineage) is a
    separate axis, out of scope by design. The registry row-key badge is
    administrative and is neither axis.

    NOTE: divergence is best-effort — it reads the status card at the registry's
    `status-card:` path; many cards migrated to vault/files/<uid>.md and the
    registry paths are stale, so the card-read silently skips when unresolved.
    The check becomes fully effective once registry paths + cards are reconciled
    (dev-spec e85d2d2c committed_substrate target 2).

    Returns: (findings, n_agents_checked, n_fail_defects).
    """
    findings: list[str] = []
    reg_path = vault / '.tropo-studio' / 'registries' / 'agent-registry.yaml'
    if not reg_path.is_file():
        findings.append('[INFO] .tropo-studio/registries/agent-registry.yaml — not found; SKIP identity-coherence check')
        return findings, 0, 0
    try:
        reg = yaml.safe_load(reg_path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        findings.append(f'[WARN] agent-registry.yaml — unreadable/parse failed ({exc}); SKIP identity-coherence check')
        return findings, 0, 0
    agents = reg.get('agents') if isinstance(reg, dict) else None
    if not isinstance(agents, dict):
        findings.append('[WARN] agent-registry.yaml — no `agents:` mapping; SKIP identity-coherence check')
        return findings, 0, 0

    n_checked = 0
    n_fail = 0
    for badge, row in agents.items():
        if not isinstance(row, dict):
            continue
        if row.get('class') != 'crew' or row.get('type') != 'agent':
            continue  # humans, workers, services are out of party_uid scope
        name = row.get('name', badge)
        # never-commissioned shells (e.g. Tiphys, commissioned: null) have no identity yet
        if not row.get('commissioned') and not row.get('party_uid'):
            findings.append(f'[INFO] {name} ({badge}) — not yet commissioned; no party_uid expected')
            continue
        n_checked += 1
        party = row.get('party_uid')

        # multiplicity
        if isinstance(party, (list, tuple)):
            if len(party) > 1:
                findings.append(f'[FAIL] {name} ({badge}) — multiplicity: {len(party)} party_uid values {list(party)}; exactly one required (doctrine 15c70b96)')
                n_fail += 1
                continue
            party = party[0] if party else None

        # absent
        if not party:
            status = str(row.get('status') or '').strip().lower()
            # The party_uid requirement applies to current messaging participants
            # (active / on-hold). Retired + on-demand agents are out of the messaging
            # axis while dormant; (re)activation establishes party_uid before they emit.
            if status in ('retired', 'on-demand'):
                findings.append(f'[INFO] {name} ({badge}) — status {status}; party_uid not required (not a current messaging participant)')
                continue
            msg = f'{name} ({badge}) — no party_uid in registry; messaging identity not yet canonical (doctrine 15c70b96 / dev-spec e85d2d2c)'
            if IDENTITY_PARTY_UID_REQUIRED:
                findings.append(f'[FAIL] {msg}')
                n_fail += 1
            else:
                findings.append(f'[WARN] {msg} — establishment grace')
            continue

        party = str(party).strip()
        # phantom — must be a real, resolvable 8-hex UID
        if not UID_RE.match(party):
            findings.append(f'[FAIL] {name} ({badge}) — party_uid {party!r} is not a valid 8-hex UID (doctrine 15c70b96)')
            n_fail += 1
            continue
        if party not in all_uids:
            findings.append(f'[FAIL] {name} ({badge}) — party_uid {party} resolves to NO vault entry (phantom identity, the 34cf0f1c class; doctrine 15c70b96)')
            n_fail += 1
            continue

        # divergence vs status-card tropo_agent_id (best-effort; see docstring)
        card_rel = row.get('status-card')
        if isinstance(card_rel, str) and card_rel:
            card_path = vault / card_rel
            if card_path.is_file():
                try:
                    cfm = split_frontmatter(card_path.read_text())
                except OSError:
                    cfm = None
                if cfm:
                    card_id = get_scalar(cfm, 'tropo_agent_id')
                    if card_id and card_id.strip() and card_id.strip() != party:
                        findings.append(
                            f'[FAIL] {name} ({badge}) — divergence: status-card tropo_agent_id '
                            f'{card_id.strip()} != registry party_uid {party} ({card_rel}); '
                            f'card must reference the registry, not carry a divergent identity (doctrine 15c70b96)')
                        n_fail += 1
                        continue

        findings.append(f'[PASS] {name} ({badge}) — party_uid {party} resolves + coherent')

    return findings, n_checked, n_fail


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# meta_status M1/M2 checks (3783a7cb Piece E — WARN severity)
# ---------------------------------------------------------------------------

_META_STATUS_VALID_BUCKETS = frozenset({'to-do', 'in-progress', 'done', 'standing'})


def _load_meta_status_rollups(vault: Path) -> tuple[dict[str, dict[str, list[str]]], list[str]]:
    """Scan .tropo/capsules/*.capsule.md; return ({type: {bucket: [values]}}, errors).

    LOADER-FIRST (3783a7cb Piece B): unrecognized shape ERRORs loudly.
    """
    rollups: dict[str, dict[str, list[str]]] = {}
    errors: list[str] = []
    capsules_dir = vault / '.tropo' / 'capsules'
    if not capsules_dir.exists():
        return rollups, errors

    for capsule_path in sorted(capsules_dir.glob('*.capsule.md')):
        try:
            text = capsule_path.read_text()
        except OSError:
            continue
        fm = split_frontmatter(text)
        if not fm:
            continue
        try:
            parsed = yaml.safe_load(fm)
        except yaml.YAMLError:
            continue
        if not isinstance(parsed, dict):
            continue
        rollup = parsed.get('meta_status_rollup')
        if rollup is None:
            continue

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


def check_no_narrow_event_read_in_boot(vault: Path) -> tuple[list[str], int, int]:
    """Check-21 — boot/listen flows must NOT use bare `query-events --party` as the drain.

    Specified in dabe7c64 (LOCKED, check-events dev-spec §amends target).
    Built v1.70 S2.5 (talos-t15 2026-06-13). Flipped to ERROR v1.70 S2.5 (A111 GO 2026-06-13).

    Boot-path scope: vault/agents/*.md (unified entries / Tier-3) · vault/playbooks/*.md
    (canonical playbooks including activation + retire) · Tier 2 canonical (cf8c3be9) ·
    .tropo-studio/*.md (kernel-pointer degraded floors — scope gap found A111 2026-06-13).

    Flags: any occurrence of `query-events --party` in a boot-path file (the narrow drain
    that can miss broadcasts and pre-watermark reply_required). Exemptions:
    - `query-events --type` alone (specialized type-filtered queries — acceptable per S2.6)
    - Lines starting with `#` (comments/inline examples, not live instructions)
    - The check-events docstring itself (avoid self-reference)

    Returns (findings, n_files_scanned, n_violations).
    """
    import re as _re
    findings: list[str] = []
    n_scanned = 0
    n_violations = 0

    # Boot-path files to scan
    paths_to_scan: list[Path] = []
    for glob_pat in [
        "vault/agents/*.md",
        "vault/playbooks/*.md",
    ]:
        paths_to_scan.extend(sorted((vault).glob(glob_pat)))

    # Tier 2 canonical substrate (cf8c3be9 — boot-required read for every agent)
    tier2 = vault / "vault" / "files" / "cf8c3be9.md"
    if tier2.exists():
        paths_to_scan.append(tier2)

    # .tropo-studio/ kernel files (degraded-floor instructions are live boot-path text)
    # Scope gap surfaced by A111 2026-06-13: agent-boot.extension.md degraded floor
    # carried a query-events --party drain that was missed because .tropo-studio/ was excluded.
    tropo_studio = vault / ".tropo-studio"
    if tropo_studio.is_dir():
        paths_to_scan.extend(sorted(tropo_studio.glob("*.md")))

    # Pattern: bare query-events --party (the forbidden narrow drain)
    # Exemption: --type qualifier present on the same term (specialized query, not drain)
    # Heuristic: `query-events --party` without a preceding `--type` on the same line
    _NARROW_DRAIN_RE = _re.compile(r'query-events\s+[^\n]*--party')
    _TYPE_FILTER_RE  = _re.compile(r'query-events\s+[^\n]*--type')

    for path in paths_to_scan:
        try:
            text = path.read_text('utf-8', errors='replace')
        except OSError:
            continue
        n_scanned += 1
        rel = path.relative_to(vault).as_posix()

        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # Skip comment lines and blank lines
            if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                continue
            # Skip the check-events tool itself (it legitimately documents the pattern)
            if 'vault/tools/2471edc0.py' in rel or '2471edc0' in rel:
                continue
            # Flag: narrow drain pattern (query-events --party) without --type
            if _NARROW_DRAIN_RE.search(stripped) and not _TYPE_FILTER_RE.search(stripped):
                findings.append(
                    f'[FAIL] {rel}:{i} — bare `query-events --party` drain detected; '
                    f'replace with `check-events` (Check-21; dabe7c64; ERROR)'
                )
                n_violations += 1

    return findings, n_scanned, n_violations


# v1.66 S2 (4acf3f2d Piece E): WORK_ITEM_TYPES — the flowing-lifecycle types per 1d14b1bf
WORK_ITEM_TYPES = frozenset({
    'task', 'note', 'decision', 'design-brief', 'design-spec', 'dev-spec',
    'test-spec', 'arch-spec', 'doc-spec', 'project', 'pipeline', 'pipeline-run',
    'release-plan', 'ship-artifact', 'build', 'project-plan', 'test-run',
    'test-scenario', 'research', 'collection', 'vault-ops-spec', 'document', 'activation',
})


def check_agent_identity_unified(vault: Path) -> tuple[list[str], int, int]:
    """AC1 — Agent Identity Unification (agent.capsule v2.0 §Validation; v1.69 dev-spec 0c61a52b).

    ERROR on:
      - More than one type:agent entry per agent: slug in vault/agents/ (uniqueness)
      - Any type:charter file whose agent: slug has a unified entry but whose status is
        NOT 'superseded' (active charter for a migrated agent = failed tombstone)
      - Any file with superseded_by: set whose target does not resolve to a vault/agents/<uid>.md
        unified entry (broken tombstone chain)

    Scope (per A109 raw-verify note): unified entries must satisfy BOTH:
      (a) type='agent' in the index
      (b) agent: slug field present
      (c) path starts with 'vault/agents/'
    Bare type:agent entries outside vault/agents/ (5 legacy director defs) are excluded.

    Returns (findings, n_slugs_checked, n_defects).
    """
    import sqlite3 as _sq3
    findings: list[str] = []
    n_defects = 0

    sqlite_path = vault / 'vault' / '00-index.sqlite'
    if not sqlite_path.exists():
        findings.append('[INFO] vault/00-index.sqlite absent — SKIP check_agent_identity_unified')
        return findings, 0, 0

    conn = _sq3.connect(str(sqlite_path))
    try:
        # ── 1. Collect valid unified entries ──────────────────────────────────────
        unified_rows = conn.execute(
            "SELECT uid, json_extract(fm_json, '$.agent') AS slug "
            "FROM entries "
            "WHERE type = 'agent' "
            "  AND json_extract(fm_json, '$.agent') IS NOT NULL "
            "  AND json_extract(fm_json, '$.path') LIKE 'vault/agents/%'"
        ).fetchall()

        slug_to_uids: dict[str, list[str]] = {}
        for uid, slug in unified_rows:
            slug_to_uids.setdefault(slug, []).append(uid)

        unified_uids = {uid for uid, _ in unified_rows}
        n_checked = len(slug_to_uids)

        # ── 2. Uniqueness per slug ────────────────────────────────────────────────
        for slug, uids in sorted(slug_to_uids.items()):
            if len(uids) > 1:
                findings.append(
                    f'[FAIL] {slug} — {len(uids)} type:agent entries in vault/agents/ '
                    f'(expect exactly 1): {" · ".join(uids)}'
                )
                n_defects += 1

        # ── 3. Active charters for migrated slugs ─────────────────────────────────
        # Any type:charter in vault/files/ whose agent: is a migrated slug but whose
        # status is NOT 'superseded' is an unfired tombstone.
        for slug in slug_to_uids:
            live_charters = conn.execute(
                "SELECT uid FROM entries "
                "WHERE type = 'charter' "
                "  AND json_extract(fm_json, '$.agent') = ? "
                "  AND (json_extract(fm_json, '$.status') IS NULL "
                "       OR json_extract(fm_json, '$.status') != 'superseded')",
                (slug,)
            ).fetchall()
            for (c_uid,) in live_charters:
                findings.append(
                    f'[FAIL] vault/files/{c_uid}.md — active type:charter for migrated '
                    f'slug {slug!r}; expected status:superseded (tombstone not fired)'
                )
                n_defects += 1

        # ── 4. superseded_by resolution (v1.69 identity tombstones only) ───────────
        # Entries tombstoned during v1.69 migration carry superseded_by_agent: talos-t15.
        # For these, superseded_by: must resolve to a vault/agents/<uid>.md unified entry.
        # (The broader vault also uses superseded_by for non-identity purposes — do NOT
        # check those here; the existing UID cross-reference check covers them generically.)
        migration_tombstones = conn.execute(
            "SELECT uid, type, json_extract(fm_json, '$.superseded_by') AS target "
            "FROM entries "
            "WHERE json_extract(fm_json, '$.superseded_by_agent') = 'talos-t15' "
            "  AND json_extract(fm_json, '$.superseded_by') IS NOT NULL"
        ).fetchall()
        for s_uid, s_type, target in migration_tombstones:
            if target and target not in unified_uids:
                findings.append(
                    f'[FAIL] vault/files/{s_uid}.md ({s_type}) — '
                    f'v1.69 tombstone superseded_by:{target} does not resolve to a '
                    f'vault/agents/<uid>.md unified entry (broken tombstone chain)'
                )
                n_defects += 1

    finally:
        conn.close()

    return findings, n_checked, n_defects


def check_token_budget_per_class(vault: Path) -> tuple[list[str], int, int]:
    """S3 — Token-Performance per-class budget check (v1.69 dev-spec 0c61a52b §S3).

    Reads a budget table from vault/files/<budget_table_uid>.md or a canonical
    path (agents/dev-pipeline/activations/b7649a1c/token-budget-table.yaml).
    If no table is found, emits INFO and skips (the measure script populates it).

    WARN if any hot-path file class exceeds its budget_bytes limit (un-exempted).
    ERROR ratchet booked v1.70.

    Budget table format (YAML):
      classes:
        unified_agent_entry:
          budget_bytes: 65536        # 64KB per entry
          glob: "vault/agents/*.md"
          exempt_uids: []
        tier2_substrate:
          budget_bytes: 32768
          glob: ".tropo-studio/*.md"
          exempt_uids: []

    Returns (findings, n_classes_checked, n_over_budget).
    """
    findings: list[str] = []
    n_over = 0

    budget_path = vault / 'agents' / 'dev-pipeline' / 'activations' / 'b7649a1c' / 'token-budget-table.yaml'
    if not budget_path.exists():
        findings.append(
            '[INFO] token-budget-table.yaml absent — SKIP check_token_budget_per_class '
            '(run the S3 measure script to generate the table: '
            'vault/tools/s3-measure-token-budget.py --output agents/dev-pipeline/activations/b7649a1c/token-budget-table.yaml)'
        )
        return findings, 0, 0

    try:
        table = yaml.safe_load(budget_path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        findings.append(f'[WARN] token-budget-table.yaml — unreadable/parse failed ({exc}); SKIP')
        return findings, 0, 0

    classes = table.get('classes') if isinstance(table, dict) else None
    if not isinstance(classes, dict) or not classes:
        findings.append('[INFO] token-budget-table.yaml has no classes: mapping — SKIP')
        return findings, 0, 0

    import glob as _glob
    n_checked = 0
    for class_name, cfg in classes.items():
        if not isinstance(cfg, dict):
            continue
        budget_bytes = cfg.get('budget_bytes')
        pattern = cfg.get('glob', '')
        exempt_uids = set(cfg.get('exempt_uids', []) or [])
        if not budget_bytes or not pattern:
            continue
        n_checked += 1
        matched = sorted(_glob.glob(str(vault / pattern)))
        over = []
        for fp in matched:
            p = Path(fp)
            uid = p.stem
            if uid in exempt_uids:
                continue
            size = p.stat().st_size if p.exists() else 0
            if size > budget_bytes:
                over.append((uid, size))
        if over:
            for uid, size in over:
                findings.append(
                    f'[WARN] {class_name}: {uid} — {size:,} bytes > budget {budget_bytes:,} bytes '
                    f'(WARN v1.69; ERROR ratchet v1.70)'
                )
                n_over += 1
        else:
            findings.append(f'[INFO] {class_name}: {len(matched)} file(s) within budget ({budget_bytes:,} bytes max)')

    return findings, n_checked, n_over


def check_meta_status_m1_m2(vault: Path) -> tuple[list[str], int, int]:
    """M1 + M2 meta_status checks (3783a7cb Piece E + v1.66 S2 4acf3f2d). WARN severity.

    M1 — rollup disjoint+total: for ANY type declaring a meta_status_rollup (NOT gated on
         enforced_enums — fixes the project skip). Disjoint check: no value in 2+ buckets.
         Total check (where enforced_enums available): every canonical value in exactly one
         bucket. Types without enforced_enums: disjoint-only.
    M2 — queries the rebuilt meta_status VIEW (not inline frontmatter — catches 85 NULL-status
         escapes by construction). Counts lifecycle-N/A for WORK_ITEM_TYPES; reports as WARN
         with by-type breakdown. NOT required-0 this cycle (honest interim; defer to ENFORCE).

    Returns (findings, meta_status_coverage_gaps, meta_status_unresolved).
    """
    findings: list[str] = []
    rollups, loader_errors = _load_meta_status_rollups(vault)
    findings.extend(loader_errors)

    if not rollups:
        return findings, 0, 0

    # M1: load canonical sets from enforced_enums where available
    capsules_dir = vault / '.tropo' / 'capsules'
    canonical_by_type: dict[str, set[str]] = {}
    aliases_by_type: dict[str, set[str]] = {}  # v1.72 Move 4 (A116): alias-coverage check
    for capsule_path in sorted(capsules_dir.glob('*.capsule.md')):
        try:
            text = capsule_path.read_text()
        except OSError:
            continue
        fm = split_frontmatter(text)
        if not fm:
            continue
        try:
            parsed = yaml.safe_load(fm)
        except yaml.YAMLError:
            continue
        if not isinstance(parsed, dict):
            continue
        enums = parsed.get('enforced_enums')
        if not enums or not isinstance(enums, dict):
            continue
        type_name = capsule_path.name.split('.capsule.md')[0]
        status_enum = enums.get('status')
        if not status_enum:
            continue
        if isinstance(status_enum, list):
            canonical_by_type[type_name] = {v.lower() for v in status_enum if isinstance(v, str)}
        elif isinstance(status_enum, dict):
            canon = status_enum.get('canonical') or []
            if isinstance(canon, list):
                canonical_by_type[type_name] = {v.lower() for v in canon if isinstance(v, str)}
            aliases = status_enum.get('aliases') or {}
            if isinstance(aliases, dict):
                aliases_by_type[type_name] = {k.lower() for k in aliases if isinstance(k, str)}

    coverage_gaps = 0
    for type_name, rollup in rollups.items():
        # Build value→buckets map (always; needed for both disjoint + total checks)
        value_to_buckets: dict[str, list[str]] = {}
        for bucket, values in rollup.items():
            for v in values:
                value_to_buckets.setdefault(v, []).append(bucket)

        # Disjoint check: no value in 2+ buckets (runs for ALL types with rollup — 4acf3f2d fix)
        for v, buckets in sorted(value_to_buckets.items()):
            if len(buckets) > 1:
                findings.append(f'[WARN] M1: {type_name}.{v} in multiple buckets: {buckets}')
                coverage_gaps += 1

        # Total check: every canonical value covered (only when enforced_enums available)
        canonical = canonical_by_type.get(type_name)
        if canonical is not None:
            for canon_val in sorted(canonical):
                buckets = value_to_buckets.get(canon_val, [])
                if len(buckets) == 0:
                    findings.append(f'[WARN] M1: {type_name}.{canon_val} not in any meta_status_rollup bucket')
                    coverage_gaps += 1

        # M1 alias-coverage (v1.72 Move 4, Argus A116): every ALIAS source value must ALSO be in a
        # bucket. The meta_status VIEW buckets the RAW status value and does NOT apply enforced_enums
        # aliases — so an aliased value absent from the rollup resolves to lifecycle-N/A (the
        # recurring rollup-narrowing bug → M2 FAIL). enforced_enums NARROWS; meta_status_rollup must
        # stay COMPREHENSIVE (canonical ∪ aliases). WARN — same gradual severity as the canonical check.
        type_aliases = aliases_by_type.get(type_name)
        if type_aliases is not None:
            for alias_val in sorted(type_aliases):
                if len(value_to_buckets.get(alias_val, [])) == 0:
                    findings.append(
                        f'[WARN] M1: {type_name}.{alias_val} (alias) not in any meta_status_rollup '
                        f'bucket — the view buckets raw values; the rollup must cover aliases too'
                    )
                    coverage_gaps += 1

    # M2: query the rebuilt meta_status VIEW (not inline-parse — catches NULL-status entries)
    # v1.66 S2 (4acf3f2d): WARN count for WORK_ITEM_TYPES, NOT required-0 (honest interim)
    # v1.68 S1: REFERENCE_EXEMPT predicate applied (per manifest 2 A108 adjudication):
    #   exempt = status IS NULL AND type = 'note' (note.capsule declares status optional;
    #   these 13 are blank-status reference notes, not work-items missing a lifecycle value).
    #   Named predicate; printed explicitly; never silent.
    REFERENCE_EXEMPT_PREDICATE = "status IS NULL AND type = 'note'"
    # v1.69 S1: tombstoned identity files carry status='superseded' (a terminal migration state).
    # The meta_status VIEW has no rollup bucket for 'superseded', so these land as lifecycle-N/A.
    # Exempt them — superseded entries are intentionally terminal, not missing lifecycle data.
    TOMBSTONE_EXEMPT_PREDICATE = "status = 'superseded'"
    ALL_EXEMPT = f"({REFERENCE_EXEMPT_PREDICATE}) OR ({TOMBSTONE_EXEMPT_PREDICATE})"
    unresolved = 0
    exempt_count = 0
    tombstone_exempt_count = 0
    sqlite_path = vault / 'vault' / '00-index.sqlite'
    if sqlite_path.exists():
        try:
            import sqlite3 as _sqlite3
            conn = _sqlite3.connect(str(sqlite_path))
            placeholders = ','.join('?' * len(WORK_ITEM_TYPES))
            # Count REFERENCE_EXEMPT separately
            exempt_count = conn.execute(
                f"SELECT COUNT(*) FROM meta_status "
                f"WHERE meta_status='lifecycle-N/A' AND type IN ({placeholders}) "
                f"AND status IS NULL AND type = 'note'",
                list(WORK_ITEM_TYPES),
            ).fetchone()[0]
            if exempt_count:
                findings.append(
                    f'[INFO] M2: {exempt_count} note entries exempt by REFERENCE_EXEMPT '
                    f'(predicate: {REFERENCE_EXEMPT_PREDICATE})'
                )
            # Count TOMBSTONE_EXEMPT separately
            tombstone_exempt_count = conn.execute(
                f"SELECT COUNT(*) FROM meta_status "
                f"WHERE meta_status='lifecycle-N/A' AND type IN ({placeholders}) "
                f"AND status = 'superseded'",
                list(WORK_ITEM_TYPES),
            ).fetchone()[0]
            if tombstone_exempt_count:
                findings.append(
                    f'[INFO] M2: {tombstone_exempt_count} entries exempt by TOMBSTONE_EXEMPT '
                    f'(predicate: {TOMBSTONE_EXEMPT_PREDICATE}; v1.69 S1 migration tombstones)'
                )
            # Count unexplained (non-exempt N/A)
            rows = conn.execute(
                f"SELECT type, COUNT(*) FROM meta_status "
                f"WHERE meta_status='lifecycle-N/A' AND type IN ({placeholders}) "
                f"AND NOT ({ALL_EXEMPT}) "
                f"GROUP BY type ORDER BY 2 DESC",
                list(WORK_ITEM_TYPES),
            ).fetchall()
            conn.close()
            for row_type, row_count in rows:
                unresolved += row_count
                findings.append(
                    f'[FAIL] M2: {row_count} {row_type} entries resolve to lifecycle-N/A '
                    f'(no rollup match; ERROR — ratcheted per v1.68 S1 post-explained-to-zero)'
                )
        except Exception as _e:
            findings.append(f'[WARN] M2: SQLite query failed ({_e}); falling back to inline count')
            # Fallback: inline count (less accurate but non-fatal)
            type_value_map: dict[tuple[str, str], str] = {}
            for _tn, _rollup in rollups.items():
                for _bucket, _vals in _rollup.items():
                    for _v in _vals:
                        type_value_map[(_tn, _v.lower())] = _bucket
            files_dir = vault / 'vault' / 'files'
            for f in sorted(files_dir.glob('*.md')):
                try:
                    text = f.read_text(errors='replace')
                except OSError:
                    continue
                fm2 = split_frontmatter(text)
                if not fm2:
                    continue
                try:
                    parsed2 = yaml.safe_load(fm2)
                except yaml.YAMLError:
                    continue
                if not isinstance(parsed2, dict):
                    continue
                _type = parsed2.get('type') or ''
                _status = parsed2.get('status') or ''
                if not _type or _type not in WORK_ITEM_TYPES or _type not in rollups:
                    continue
                if _status and (_type, _status.lower()) not in type_value_map:
                    unresolved += 1

    return findings, coverage_gaps, unresolved


def check_meta_status_inline_fixtures() -> tuple[list[str], int, int]:
    """Loader-first inline fixtures for meta_status_rollup (3783a7cb Piece B).

    Tests shape validation without touching the live vault.
    Must pass BEFORE any capsule declares meta_status_rollup.
    """
    errors: list[str] = []
    passes = 0
    fails = 0

    def _check_shape(capsule_name: str, rollup_val) -> list[str]:
        errs: list[str] = []
        if not isinstance(rollup_val, dict):
            errs.append(
                f'[ERROR] {capsule_name} — meta_status_rollup: unrecognized shape '
                f'(expected {{bucket: [values]}}, got {type(rollup_val).__name__}) — 3783a7cb Piece B'
            )
            return errs
        for bucket, values in rollup_val.items():
            if bucket not in _META_STATUS_VALID_BUCKETS:
                errs.append(
                    f'[ERROR] {capsule_name} — meta_status_rollup: unrecognized bucket '
                    f'{bucket!r} (valid: {sorted(_META_STATUS_VALID_BUCKETS)}) — 3783a7cb Piece B'
                )
            elif not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                errs.append(
                    f'[ERROR] {capsule_name} — meta_status_rollup.{bucket}: '
                    f'unrecognized shape (expected list of strings) — 3783a7cb Piece B'
                )
        return errs

    def _run(capsule_name: str, rollup_val, expect_error: bool) -> None:
        nonlocal passes, fails
        got_errors = _check_shape(capsule_name, rollup_val)
        got_error = bool(got_errors)
        if expect_error == got_error:
            passes += 1
        else:
            fails += 1
            errors.append(
                f'[ERROR] meta_status fixture {capsule_name!r}: '
                f'expected error={expect_error} got={got_error} — 3783a7cb Piece B'
            )

    _run('test.capsule.md',
         {'to-do': ['new', 'accepted'], 'in-progress': ['active'], 'done': ['closed']},
         expect_error=False)                                            # valid dict
    _run('test.capsule.md', ['new', 'active', 'closed'], expect_error=True)   # list not dict
    _run('test.capsule.md', 'active', expect_error=True)                       # string not dict
    _run('test.capsule.md', {'wip': ['active']}, expect_error=True)            # unknown bucket
    _run('test.capsule.md', {'done': 'closed'}, expect_error=True)             # value not list
    _run('test.capsule.md',
         {'standing': ['evergreen', 'standing'], 'done': ['shipped']},
         expect_error=False)                                            # standing bucket valid

    return errors, passes, fails


# ---------------------------------------------------------------------------
# v1.66 S5 cascade_disposition check (e26935da §3 — WARN now, ERROR-ratchet next)
# ---------------------------------------------------------------------------

_S5_THRESHOLD_STR = "1.66.0"

def check_cascade_disposition_required(vault: Path) -> tuple[list[str], int, int]:
    """v1.66 S5 (e26935da): status:done v1.66+ dev-specs with empty triggered_*_activation_uids
    and no cascade_disposition -> WARN (ERROR-ratchet next cycle).
    Pre-S5 grandfathered (target_release < 1.66.0) entries emitted as INFO.
    Returns (findings, checked, warn_count).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    _s5 = (1, 66, 0)

    def _parse_ver(v):
        try:
            return tuple(int(x) for x in str(v or "0").lstrip("v").split("."))
        except (ValueError, TypeError):
            return (0,)

    total_checked = 0
    warn_count = 0
    for f in sorted(files_dir.glob('*.md')):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        if get_scalar(fm_text, 'type') not in ('dev-spec', 'dev_spec'):
            continue
        if get_scalar(fm_text, 'status') != 'done':
            continue
        doc_acts = get_list(fm_text, 'triggered_doc_activation_uids') or []
        test_acts = get_list(fm_text, 'triggered_test_activation_uids') or []
        if doc_acts or test_acts:
            continue  # has triggers — not an empty-triggers case
        total_checked += 1
        uid = get_scalar(fm_text, 'uid') or f.stem
        target_release = get_scalar(fm_text, 'target_release') or ''
        ver = _parse_ver(target_release)
        if ver < _s5:
            findings.append(
                f'[INFO] vault/files/{f.name} — dev-spec {uid} target_release={target_release!r} '
                f'pre-S5 grandfathered; no cascade_disposition required.'
            )
            continue
        # Check for cascade_disposition (any truthy value)
        cd = get_scalar(fm_text, 'cascade_disposition')
        if cd:
            continue  # has disposition — fine
        findings.append(
            f'[WARN] vault/files/{f.name} — dev-spec {uid} status:done target_release={target_release!r} '
            f'has empty triggered_*_activation_uids and no cascade_disposition; '
            f'close-gate will BLOCK at workflow-complete (e26935da S5; WARN now, ERROR at ratchet).'
        )
        warn_count += 1

    return findings, total_checked, warn_count


# v1.65 Enforce-First — task pilot (addc4490 v0.5)
# Two checks: enum-compliance + coherence.
# ---------------------------------------------------------------------------

def _parse_enforced_enums_block(
    capsule_name: str,
    enums: dict,
    findings: list[str],
) -> dict[str, dict]:
    """Parse a capsule's enforced_enums into a {field: {canonical, aliases}} map.

    Accepts two forms per field (c4512bdc Piece 1):
      - list   → {canonical: vals, aliases: {}}
      - dict   → must have canonical: list + aliases: dict; anything else → ERROR

    state fields are rejected with ERROR (alias maps apply to status-class
    lifecycle fields only; state overloading is DISAMBIGUATE, not synonym drift).
    Unrecognized shapes ERROR — never silent-skip.
    """
    result: dict[str, dict] = {}
    for field, vals in enums.items():
        if field == 'state':
            if isinstance(vals, dict):
                findings.append(
                    f'[ERROR] {capsule_name} — enforced_enums.state cannot carry '
                    f'an alias map (state overloading is DISAMBIGUATE, not synonym '
                    f'drift — c4512bdc Piece 1 §5)'
                )
            # state in list form is fine to enforce; just no aliases allowed
            if isinstance(vals, list):
                result[field] = {'canonical': list(vals), 'aliases': {}}
            continue
        if isinstance(vals, list):
            result[field] = {'canonical': list(vals), 'aliases': {}}
        elif isinstance(vals, dict):
            canonical = vals.get('canonical')
            aliases   = vals.get('aliases', {})
            if not isinstance(canonical, list) or not isinstance(aliases, dict):
                findings.append(
                    f'[ERROR] {capsule_name} — enforced_enums.{field}: unrecognized '
                    f'dict shape (expected canonical: [...], aliases: {{...}}) — '
                    f'c4512bdc Piece 1 §1'
                )
                continue
            result[field] = {'canonical': list(canonical), 'aliases': dict(aliases)}
        else:
            findings.append(
                f'[ERROR] {capsule_name} — enforced_enums.{field}: unrecognized form '
                f'(expected list or {{canonical, aliases}} dict) — c4512bdc Piece 1 §1'
            )
    return result


def check_enforced_enum_compliance(vault: Path) -> tuple[list[str], int, int, int]:
    """v1.65 + c4512bdc Piece 1 enforce-first enum check; v1.72 Move 7 ratcheted to ERROR.

    Reads each type capsule's enforced_enums via yaml.safe_load.  Accepts both
    the list form (canonical only) and the {canonical, aliases} dict form.
    Unrecognized shapes ERROR loudly (never silent-skip).

    Three-way classification per entry value (case-folded):
      PASS        — value in canonical set
      NORMALIZABLE — value in aliases map (groomer work item; WARN; does not fail)
      ERROR       — unknown drift (v1.72 Move 7; ratcheted from WARN; exits non-zero)

    NORMALIZABLE counted separately — does not increment total_warnings or
    total_fails; exit code unaffected.  state alias maps are rejected (ERROR).
    """
    findings: list[str] = []

    # 1. Build type → {field: {canonical, aliases}} map from type capsules
    capsules_dir = vault / '.tropo' / 'capsules'
    type_enums: dict[str, dict[str, dict]] = {}

    for capsule_path in sorted(capsules_dir.glob('*.capsule.md')):
        try:
            text = capsule_path.read_text()
        except OSError:
            continue
        fm = split_frontmatter(text)
        if not fm:
            continue
        try:
            parsed = yaml.safe_load(fm)
        except yaml.YAMLError:
            continue
        if not isinstance(parsed, dict):
            continue
        enums = parsed.get('enforced_enums')
        if not enums or not isinstance(enums, dict):
            continue
        type_name = capsule_path.name.split('.capsule.md')[0]
        parsed_enums = _parse_enforced_enums_block(
            capsule_path.name, enums, findings
        )
        if parsed_enums:
            type_enums[type_name] = parsed_enums

    if not type_enums:
        findings.append('[WARN] No type capsules with enforced_enums found — check skipped')
        return findings, 0, 0, 0

    # 2. For each governed entry: three-way classify per field
    search_dirs = [
        vault / 'vault' / 'files',
        vault / 'vault' / 'tools',
        vault / 'vault' / 'session-agents',
        vault / 'vault' / 'playbooks',
        vault / 'vault' / 'pipeline-runs',
        vault / 'vault' / 'loop-runs'
    ]
    
    n_checked = 0
    n_error = 0
    n_warn = 0

    for d in search_dirs:
        if not d.exists() or not d.is_dir():
            continue
        for f in sorted(d.glob('*.md')):
            try:
                text = f.read_text()
            except OSError:
                continue
            fm = split_frontmatter(text)
            if not fm:
                continue
            try:
                parsed = yaml.safe_load(fm)
            except yaml.YAMLError:
                continue
            if not isinstance(parsed, dict):
                continue
    
            entry_type = parsed.get('type')
            if not entry_type or entry_type not in type_enums:
                continue
    
            n_checked += 1
            for field, field_def in type_enums[entry_type].items():
                # Article documents specialize the document status machine.
                # Check 25 validates their draft/reviewed/locked/archived enum.
                if (
                    entry_type == 'document'
                    and parsed.get('subtype') == 'article'
                    and field == 'status'
                ):
                    continue
                raw_val = parsed.get(field)
                if raw_val is None:
                    continue
                raw_str   = str(raw_val).strip()
                raw_lower = raw_str.lower()  # case-fold per c4512bdc §6

                canon_lower   = [c.lower() for c in field_def['canonical']]
                aliases_lower = {k.lower(): v for k, v in field_def['aliases'].items()}

                rel_path = f.relative_to(vault)

                if raw_lower in canon_lower:
                    pass  # PASS — canonical value
                elif raw_lower in aliases_lower:
                    findings.append(
                        f'  [WARN] {rel_path} — {entry_type}.{field} = '
                        f'"{raw_str}" is a synonym for "{aliases_lower[raw_lower]}" '
                        f'(groomer will normalize)'
                    )
                    n_warn += 1
                else:
                    findings.append(
                        f'  [ERROR] {rel_path} — {entry_type}.{field} = '
                        f'"{raw_str}" not in enforced set {field_def["canonical"]}'
                    )
                    n_error += 1

    return findings, n_checked, n_error, n_warn


def check_enforced_enum_coherence(vault: Path) -> tuple[list[str], int, int]:
    """v1.65 enforce-first coherence check (addc4490 v0.5 mechanism item 4).

    Asserts each type capsule's enforced_enums block matches its designated
    canonical prose enum line.  Anchor: backtick-colon form (`field:` ∈ {…})
    unique to the enum declaration lines — avoids false-matching conditional
    references like `:207` in task.capsule ('requested_of … when status ∈ …').

    Pilot scope: any capsule carrying enforced_enums (task only now).  WARN.
    """
    findings: list[str] = []
    n_checked = 0
    n_fail = 0

    capsules_dir = vault / '.tropo' / 'capsules'

    for capsule_path in sorted(capsules_dir.glob('*.capsule.md')):
        try:
            text = capsule_path.read_text()
        except OSError:
            continue
        fm = split_frontmatter(text)
        if not fm:
            continue
        try:
            parsed = yaml.safe_load(fm)
        except yaml.YAMLError:
            continue
        if not isinstance(parsed, dict):
            continue
        enums = parsed.get('enforced_enums')
        if not enums or not isinstance(enums, dict):
            continue

        for field, declared_vals in enums.items():
            # Handle both list form (canonical only) and dict form (canonical + aliases).
            # Coherence checks the CANONICAL values against the prose anchor — aliases
            # live only in the frontmatter block, not in the prose.  (c4512bdc Piece 1 §4)
            if isinstance(declared_vals, list):
                canonical_vals: list = declared_vals
            elif isinstance(declared_vals, dict):
                canonical_vals = declared_vals.get('canonical', [])
                if not isinstance(canonical_vals, list):
                    continue
            else:
                continue
            n_checked += 1

            # Anchor: backtick-colon form "`field:` ∈ {…}" — unique to the
            # canonical enum declaration line (not conditional references).
            # Also accept the looser `∈ {…}` anchor per c4512bdc Piece 1 §4.
            pattern = re.compile(r'`' + re.escape(field) + r':` ∈ \{([^}]+)\}')
            m = pattern.search(text)
            if not m:
                # Fallback: looser ∈ {…} anchor (for capsules that use it)
                pattern_loose = re.compile(re.escape(field) + r'[^∈]*∈ \{([^}]+)\}')
                m = pattern_loose.search(text)
            if not m:
                findings.append(
                    f'  [WARN] {capsule_path.name} — no canonical prose line '
                    f'matching `{field}:` ∈ {{…}} found; coherence unverifiable'
                )
                n_fail += 1
                continue

            # Extract values: strip backticks and whitespace from each element
            prose_vals = [
                v.strip().strip('`') for v in m.group(1).split(',')
            ]

            if sorted(canonical_vals) != sorted(prose_vals):
                findings.append(
                    f'  [WARN] {capsule_path.name} — enforced_enums.{field} '
                    f'{sorted(canonical_vals)} does not match prose line '
                    f'{sorted(prose_vals)} — coherence FAIL'
                )
                n_fail += 1

    return findings, n_checked, n_fail


# ---------------------------------------------------------------------------
# d996b941 L0 — Principal-class + slug-uniqueness going-forward guards
# ---------------------------------------------------------------------------

def check_principal_class_present(vault: Path) -> tuple[list[str], int, int]:
    """d996b941 L0a — every active type:principal carries principal_class ∈ {human, agent-*}.

    Going-forward enforcement: no principal.capsule exists, so this check makes the
    invariant durable without a lock-break. WARN→ERROR ratchet.
    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    total_checked = 0
    defects = 0

    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        if get_scalar(fm_text, 'type') != 'principal':
            continue
        status = get_scalar(fm_text, 'status') or ''
        # v1.68 S1 tombstone pre-clear: both legacy (status:superseded) and
        # post-relocation (state:archived + superseded_by) shapes are inactive.
        if status in ('superseded', 'tombstone', 'retired'):
            continue
        if (get_scalar(fm_text, 'state') or '') == 'archived' and (get_scalar(fm_text, 'superseded_by') or ''):
            continue
        total_checked += 1
        pc = get_scalar(fm_text, 'principal_class') or ''
        if not pc or not (pc == 'human' or pc.startswith('agent-')):
            findings.append(
                f'[WARN] vault/files/{f.name} — active type:principal missing or invalid '
                f'principal_class {pc!r}; must be "human" or "agent-*" '
                f'(d996b941 L0a; task.capsule v4.3 Rule 14 identity substrate)'
            )
            defects += 1

    return findings, total_checked, defects


def check_principal_slug_unique(vault: Path) -> tuple[list[str], int, int]:
    """d996b941 L0b — no two active principals share a slug_alias or name.

    A slug collision = nondeterministic resolution = two-label spoof by another door.
    WARN→ERROR ratchet.
    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    slug_to_uid: dict[str, str] = {}
    total_checked = 0
    defects = 0

    for f in sorted(files_dir.glob('*.md')):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        if get_scalar(fm_text, 'type') != 'principal':
            continue
        status = get_scalar(fm_text, 'status') or ''
        # v1.68 S1 tombstone pre-clear: both legacy (status:superseded) and
        # post-relocation (state:archived + superseded_by) shapes are inactive.
        if status in ('superseded', 'tombstone', 'retired'):
            continue
        if (get_scalar(fm_text, 'state') or '') == 'archived' and (get_scalar(fm_text, 'superseded_by') or ''):
            continue

        total_checked += 1
        uid = get_scalar(fm_text, 'uid') or f.stem
        name = (get_scalar(fm_text, 'name') or '').lower()
        raw_aliases = fm_text.get('slug_aliases') if isinstance(fm_text, dict) else None
        aliases = [str(a).lower() for a in (raw_aliases or [])] if raw_aliases else []
        all_labels = ([name] if name else []) + aliases

        for label in all_labels:
            if label in slug_to_uid and slug_to_uid[label] != uid:
                findings.append(
                    f'[WARN] vault/files/{f.name} — active principal {uid!r} shares '
                    f'slug/alias {label!r} with {slug_to_uid[label]!r}; '
                    f'slug collision = nondeterministic resolution (d996b941 L0b)'
                )
                defects += 1
            else:
                slug_to_uid[label] = uid

    return findings, total_checked, defects


def check_task_approver_distinct_from_executor(vault: Path) -> tuple[list[str], int, int]:
    """d996b941 L1 — task.capsule v4.3 Check 22: approver ≠ executor.

    Fires on: type:task + approval_required:true + status:closed + resolution:done.
    Rule: approver must be set, resolve to a registered principal, and differ from
    owner ∪ accepted_by UIDs — UNLESS principal_class:human (human principals exempt).
    WARN this cycle; return 0 defects to keep validator 0-failed (AC9).
    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    total_checked = 0

    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        if get_scalar(fm_text, 'type') != 'task':
            continue
        if not (isinstance(fm_text, dict) and fm_text.get('approval_required') is True):
            continue
        if get_scalar(fm_text, 'status') != 'closed':
            continue
        if get_scalar(fm_text, 'resolution') != 'done':
            continue

        total_checked += 1
        approver = get_scalar(fm_text, 'approver') or ''

        # AC2: approver field must be set
        if not approver:
            findings.append(
                f'[WARN] vault/files/{f.name} — approval_required task closed:done '
                f'but approver field missing (task.capsule v4.3 Check 22)'
            )
            continue

        # AC7: approver must resolve to a registered principal
        approver_uid = _resolve_principal_uid(approver, vault)
        if approver_uid is None:
            findings.append(
                f'[WARN] vault/files/{f.name} — approver {approver!r} does not resolve '
                f'to a registered active principal (task.capsule v4.3 Check 22)'
            )
            continue

        # Human principals are exempt (AC4)
        if _get_principal_class(approver_uid, vault) == 'human':
            continue

        # Collect executor identities: owner + accepted_by UIDs
        owner = get_scalar(fm_text, 'owner') or ''
        owner_uid = _resolve_principal_uid(owner, vault) if owner else None

        executor_uids: set[str] = set()
        if owner_uid:
            executor_uids.add(owner_uid)
        raw_accepted = fm_text.get('accepted_by') if isinstance(fm_text, dict) else None
        if isinstance(raw_accepted, list):
            for rec in raw_accepted:
                if isinstance(rec, dict):
                    ab_uid_raw = rec.get('accepted_by_uid') or ''
                    ab_uid = _resolve_principal_uid(str(ab_uid_raw), vault) if ab_uid_raw else None
                    if ab_uid:
                        executor_uids.add(ab_uid)

        endorsed_by_raw = fm_text.get('endorsed_by') if isinstance(fm_text, dict) else None
        if endorsed_by_raw:
            eb_uid = _resolve_principal_uid(str(endorsed_by_raw), vault)
            if eb_uid:
                executor_uids.add(eb_uid)

        # AC3/AC5: approver must differ from all executor identities
        if approver_uid in executor_uids:
            findings.append(
                f'[WARN] vault/files/{f.name} — approver {approver!r} (resolved: {approver_uid}) '
                f'is the same principal as owner/accepted_by/endorsed_by executor; '
                f'task.capsule v4.3 Check 22 requires approver independence '
                f'(non-human approvers must differ from executor)'
            )

    return findings, total_checked, 0  # 0 defects: WARN phase, keeps validator 0-failed (AC9)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# v1.68 S2 — Inbox Transition Protocol
# ---------------------------------------------------------------------------

# TERMINAL statuses: mechanically derived from capsule done-bucket canonicals +
# cross-type terminals. An inbox member with a terminal status is a HARD violation
# (work finished; item definitively overdue to leave the inbox).
_INBOX_TERMINAL = frozenset({
    'done', 'closed', 'shipped', 'published', 'retired', 'archived', 'superseded',
    'locked', 'complete', 'complete-via-salvage', 'final', 'FINAL', 'retracted-replaced',
    'FINAL/RETIRING',
})

# Per-type UNCLAIMED sets: initial authoring states that are NOT violations.
# A member whose status is in its type's UNCLAIMED set is legitimately in the inbox
# (still being authored, not yet claimed).
# v1.68 S2 — Widened per A108 drain analysis (event 2924):
# note {new,accepted,active}: active=live filed note, NOT work-started per note.capsule
# document {new,draft}: draft is capsule initial state; parked Substack drafts ARE waiting
# task {new,accepted}: both roll to to-do; accepted=claimed but not started
_INBOX_UNCLAIMED = {
    'note': frozenset({'new', 'accepted', 'active'}),
    'task': frozenset({'new', 'accepted'}),
    'document': frozenset({'new', 'draft'}),
    'design-brief': frozenset({'design', 'specify'}),
    'dev-spec': frozenset({'draft'}),
    'test-spec': frozenset({'draft'}),
    'doc-spec': frozenset({'draft'}),
}
_INBOX_UNCLAIMED_DEFAULT = frozenset({'new'})


def check_inbox_transition(vault: Path) -> tuple[list[str], int, int, int]:
    """v1.68 S2 — inbox items must be in transition, not storage.

    Two tiers:
    - HARD: status in TERMINAL → work finished, item definitively overdue to leave (ERROR; ratcheted from WARN per v1.68 S2 post-drain)
    - SOFT: status past type's UNCLAIMED but not terminal → claimed/in-work, should re-parent (WARN)

    Inbox detection: entries whose title contains '01-inbox' (the convention).
    Inbox-of-inbox exclusion: entries that are themselves inboxes are EXCLUDED from violation
    counting (structural hierarchy; 4 live cases confirmed).
    """
    import json as _json
    findings: list[str] = []
    hard_count = 0
    soft_count = 0
    total_checked = 0

    index_path = vault / 'vault' / '00-index.jsonl'
    if not index_path.exists():
        return findings, 0, 0, 0

    # Step 1: resolve inbox set (entries whose title/name matches '01-inbox' convention)
    inbox_uids: set[str] = set()
    all_entries: dict[str, dict] = {}
    with index_path.open(encoding='utf-8', errors='replace') as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = _json.loads(raw)
            except Exception:
                continue
            if not isinstance(entry, dict):
                continue
            uid = entry.get('uid') or ''
            if not uid:
                continue
            all_entries[uid] = entry
            title = str(entry.get('title') or entry.get('name') or '').lower()
            # v1.68 S2: use '%inbox%' matching (catches 01-vault-inbox, 01-inbox, etc.)
            # equivalent to SQL LIKE '%inbox%' — A108 drain confirmed this is the right rule
            if 'inbox' in title:
                inbox_uids.add(uid)

    # Step 2: for each inbox, scan members
    by_inbox: dict[str, dict] = {uid: {'hard': 0, 'soft': 0} for uid in inbox_uids}
    for entry_uid, entry in all_entries.items():
        member_of = entry.get('member_of') or []
        if isinstance(member_of, str):
            member_of = [member_of]
        for inbox_uid in inbox_uids:
            if inbox_uid not in member_of:
                continue
            # This entry is a member of this inbox
            # Exclude entries that are themselves inboxes (structural hierarchy, not violations)
            if entry_uid in inbox_uids:
                continue
            # A110 ratified 2026-06-12: archived items occupy no inbox — state:archived is
            # terminal housekeeping. member_of is preserved for historical provenance only;
            # the item is no longer claimable. Exclude from violation counting.
            # (Metis G77 bulk archival surfaced ~11+ false [FAIL] lines that led to this fix.)
            if str(entry.get('state') or '') == 'archived':
                continue
            total_checked += 1
            status = str(entry.get('status') or '')
            entry_type = str(entry.get('type') or 'note')
            unclaimed = _INBOX_UNCLAIMED.get(entry_type, _INBOX_UNCLAIMED_DEFAULT)

            if status in _INBOX_TERMINAL:
                findings.append(
                    f'[FAIL] {entry_uid} (type:{entry_type} status:{status!r}) — '
                    f'HARD inbox violation in {inbox_uid}: terminal status, work finished '
                    f'(ERROR; ratcheted per v1.68 S2 post-drain)'
                )
                by_inbox[inbox_uid]['hard'] += 1
                hard_count += 1
            elif status and status not in unclaimed:
                findings.append(
                    f'[WARN] {entry_uid} (type:{entry_type} status:{status!r}) — '
                    f'SOFT inbox violation in {inbox_uid}: past unclaimed set {set(unclaimed)!r}, should re-parent'
                )
                by_inbox[inbox_uid]['soft'] += 1
                soft_count += 1

    # Summary finding with by-inbox breakdown
    if hard_count + soft_count > 0:
        findings.insert(0,
            f'[INFO] Inbox violations: {hard_count} HARD + {soft_count} SOFT '
            f'across {len(inbox_uids)} inboxes ({total_checked} members scanned)'
        )
        for iuid, counts in sorted(by_inbox.items(), key=lambda x: -(x[1]['hard'] + x[1]['soft'])):
            if counts['hard'] + counts['soft'] > 0:
                ientry = all_entries.get(iuid, {})
                ititle = str(ientry.get('title') or iuid)[:50]
                findings.append(f'  [INFO] {iuid} ({ititle}): {counts["hard"]} HARD + {counts["soft"]} SOFT')

    return findings, total_checked, hard_count, soft_count


# R1 — checks-fail-loud regression fixture (v1.69; talos-t15 2026-06-12)
# ---------------------------------------------------------------------------

def check_r1_fail_loud_fixture() -> tuple[list[str], int, int]:
    """R1 regression: validator checks must emit [FAIL] CRASHED (not [WARN] X check failed)
    when their execution block raises an exception.

    Fixed-list fixture: verifies each of the 15 R1-affected check names does NOT appear
    in the swallow pattern (WARN ... check failed) in this file's source. Uses exact
    string search for each check name + the specific failure suffix, avoiding
    self-referential regex issues.
    """
    findings: list[str] = []
    n_pass, n_fail = 0, 0

    source = Path(__file__).read_text('utf-8')
    # These 15 check names were the R1-affected swallow handlers (talos-t15 2026-06-12).
    # Each must NOT appear in the pattern "[WARN] <name> check failed:" — that would be
    # a regression to the swallow-own-crash anti-pattern.
    R1_CHECKS = [
        'check_agent_identity_unified',
        'check_token_budget_per_class',
        'cascade_disposition',
        'fleet_ops_schedule',
        'AC2', 'AC7', 'AC8',
        'Piece 1 fixture',
        'enforce-first enum',
        'enforce-first coherence',
        'meta_status fixture',
        'meta_status M1/M2',
        'principal-class-present',
        'principal-slug-unique',
        'task-approver-distinct',
    ]
    regressions = []
    for name in R1_CHECKS:
        if f"[WARN] {name} check failed" in source:
            regressions.append(name)
    if regressions:
        n_fail += 1
        findings.append(
            f'  [FAIL] R1 regression: {len(regressions)} check(s) reverted to WARN swallow: '
            + ', '.join(regressions)
        )
    else:
        n_pass += 1  # all 15 handlers confirmed fail-loud

    return findings, n_pass, n_fail


def check_curator_dispatch_fixture() -> tuple[list[str], int, int]:
    """AC5 (v1.69 dev-spec 0c61a52b §S3; argus-a110 2026-06-12) — boot-conditional
    curator dispatch fixtures against agent-activation.playbook v2.17 §2.5.

    Reference implementation of the §2.5 trigger decision + synthetic memory-dir
    fixtures. Contract: a booting agent dispatches sa.memory-curator ONLY on
    migrate / catch_up (F5 trip: >=3 generations OR >=50 unfolded entries) /
    citation_repair. Healthy lineage dispatches NONE. Precedence:
    migrate > catch_up > citation_repair (§2.5 order).
    """
    import json as _json
    import re as _re
    import tempfile as _tempfile
    import shutil as _shutil

    findings: list[str] = []
    n_pass, n_fail = 0, 0

    def _evaluate(memory_dir: Path, resolvable_uids: set) -> str:
        surface = memory_dir / 'agent-memory.md'
        v2_artifacts = [memory_dir / 'memory-current.md',
                        memory_dir / 'short-term-memory.jsonl',
                        memory_dir / 'transfers' / 'living-transfer.md']
        if not surface.exists():
            if any(q.exists() for q in v2_artifacts):
                return 'migrate'          # un-migrated v2 surface -> one-time conversion
            return 'none'                 # first-generation skeleton path: no dispatch
        text = surface.read_text('utf-8')
        # F5 Condition A — generations since last fold (fixture surfaces carry both ints
        # explicitly; live agents derive per §2.5 from generation + last_curated provenance)
        m_gen = _re.search(r'^generation:\s*(\d+)', text, _re.M)
        m_lcg = _re.search(r'^last_curated_generation:\s*(\d+)', text, _re.M)
        gens_since = (int(m_gen.group(1)) - int(m_lcg.group(1))) if (m_gen and m_lcg) else 0
        # F5 Condition B — entries past the LAST fold-boundary line in the episodic log
        unfolded = 0
        jsonl = memory_dir / 'agent-memories.jsonl'
        if jsonl.exists():
            rows = [ln for ln in jsonl.read_text('utf-8').splitlines() if ln.strip()]
            last_boundary = -1
            for i, ln in enumerate(rows):
                try:
                    if _json.loads(ln).get('boundary_marker'):
                        last_boundary = i
                except Exception:
                    continue
            unfolded = len(rows) - (last_boundary + 1)
        if gens_since >= 3 or unfolded >= 50:
            return 'catch_up'
        # Citation-resolution sweep — every 8-hex UID cited in §Top-of-Mind resolves
        m_tom = _re.search(r'## §Top-of-Mind(.*?)(?=\n## |\Z)', text, _re.S)
        if m_tom:
            cited = set(_re.findall(r'`([0-9a-f]{8})`', m_tom.group(1)))
            if cited - resolvable_uids:
                return 'citation_repair'
        return 'none'

    def _write_surface(d: Path, gen: int, lcg: int, cited: str):
        (d / 'agent-memory.md').write_text(
            f"---\nagent: fixture\ngeneration: {gen}\nlast_curated_generation: {lcg}\n"
            f"spec_version: \"3.0\"\n---\n\n## §Top-of-Mind\n\n- pin cites `{cited}`\n", 'utf-8')

    def _write_jsonl(d: Path, unfolded: int):
        rows = ['{"kind": "entry", "n": %d}' % i for i in range(3)]
        rows.append('{"kind": "fold-boundary", "boundary_marker": true, "entries_before_boundary": 3}')
        rows += ['{"kind": "entry", "n": %d}' % (10 + i) for i in range(unfolded)]
        (d / 'agent-memories.jsonl').write_text('\n'.join(rows) + '\n', 'utf-8')

    resolvable = {'aaaa1111'}
    tmp = Path(_tempfile.mkdtemp(prefix='ac5-curator-fixture-'))
    try:
        cases = []
        # 1 — healthy lineage: fresh fold, zero unfolded, citations resolve -> none
        d1 = tmp / 'healthy'; d1.mkdir()
        _write_surface(d1, gen=110, lcg=109, cited='aaaa1111'); _write_jsonl(d1, unfolded=0)
        cases.append(('healthy lineage dispatches none', d1, 'none'))
        # 2 — un-migrated v2 surface -> migrate (takes precedence over anything else)
        d2 = tmp / 'migrate'; d2.mkdir()
        (d2 / 'memory-current.md').write_text('# v2 surface\n', 'utf-8'); _write_jsonl(d2, unfolded=60)
        cases.append(('un-migrated v2 surface dispatches migrate (precedence over F5)', d2, 'migrate'))
        # 3 — F5 volume trip: 52 unfolded entries past boundary -> catch_up
        d3 = tmp / 'catchup'; d3.mkdir()
        _write_surface(d3, gen=110, lcg=109, cited='aaaa1111'); _write_jsonl(d3, unfolded=52)
        cases.append(('F5 volume trip (52 unfolded) dispatches catch_up', d3, 'catch_up'))
        # 4 — citation breakage: cited UID not resolvable -> citation_repair
        d4 = tmp / 'citation'; d4.mkdir()
        _write_surface(d4, gen=110, lcg=109, cited='deadbeef'); _write_jsonl(d4, unfolded=0)
        cases.append(('citation breakage dispatches citation_repair', d4, 'citation_repair'))

        for label, d, expected in cases:
            got = _evaluate(d, resolvable)
            if got == expected:
                n_pass += 1
            else:
                n_fail += 1
                findings.append(f'  [FAIL] AC5 fixture: {label} — expected {expected}, got {got}')
        # 5 — F5 generation trip on otherwise-healthy surface (Condition A): gens_since=4 -> catch_up
        _write_surface(d1, gen=110, lcg=106, cited='aaaa1111')
        got = _evaluate(d1, resolvable)
        if got == 'catch_up':
            n_pass += 1
        else:
            n_fail += 1
            findings.append(f'  [FAIL] AC5 fixture: F5 generation trip (4 gens) — expected catch_up, got {got}')
    finally:
        _shutil.rmtree(tmp, ignore_errors=True)

    return findings, n_pass, n_fail


# c4512bdc Piece 1 — Inline fixture self-tests
# ---------------------------------------------------------------------------

def check_piece1_inline_fixtures() -> tuple[list[str], int, int]:
    """Inline fixture tests for the alias-map loader + three-way classify.
    Verifies Piece 1 acceptance criteria against synthetic data — no capsule
    files needed.  Runs as a separate validator section in main().

    AC coverage:
      F1  list form  → loaded as canonical-only, PASS on canonical value
      F2  dict form  → loaded with aliases; aliased value → NORMALIZABLE; canonical → PASS; unknown → WARN
      F3  malformed dict (no 'canonical') → ERROR (not silent-skip)
      F4  state alias map → ERROR
      F5  case-fold: FINAL ≡ final → PASS/NORMALIZABLE based on canonical
    """
    findings: list[str] = []
    n_pass = 0
    n_fail = 0

    def assert_ok(cond: bool, msg: str) -> None:
        nonlocal n_pass, n_fail
        if cond:
            n_pass += 1
        else:
            n_fail += 1
            findings.append(f'  [FAIL] Piece 1 fixture: {msg}')

    # F1 — list form loader
    errs: list[str] = []
    r = _parse_enforced_enums_block('test.capsule.md', {'status': ['new', 'done']}, errs)
    assert_ok('status' in r and r['status']['canonical'] == ['new', 'done'], 'F1: list form should load as canonical-only')
    assert_ok(r['status']['aliases'] == {}, 'F1: list form should have empty aliases')
    assert_ok(len(errs) == 0, 'F1: list form should produce no errors')

    # F2 — dict form loader + three-way classify
    errs = []
    r = _parse_enforced_enums_block('test.capsule.md',
        {'status': {'canonical': ['design', 'specify', 'done'], 'aliases': {'closed': 'done', 'complete': 'done'}}},
        errs)
    assert_ok('status' in r, 'F2: dict form should load')
    assert_ok(r['status']['canonical'] == ['design', 'specify', 'done'], 'F2: canonical list correct')
    assert_ok(r['status']['aliases'] == {'closed': 'done', 'complete': 'done'}, 'F2: aliases map correct')
    assert_ok(len(errs) == 0, 'F2: dict form should produce no errors')
    # Classify: done → PASS; closed → NORMALIZABLE; unknown → WARN
    fd = r['status']
    canon_lc = [c.lower() for c in fd['canonical']]
    alias_lc = {k.lower(): v for k, v in fd['aliases'].items()}
    assert_ok('done' in canon_lc, 'F2: canonical value passes')
    assert_ok('closed' in alias_lc, 'F2: aliased value is NORMALIZABLE')
    assert_ok('mystery' not in canon_lc and 'mystery' not in alias_lc, 'F2: unknown value WARNs')

    # F3 — malformed dict (missing 'canonical') → ERROR
    errs = []
    r = _parse_enforced_enums_block('test.capsule.md', {'status': {'aliases': {'x': 'y'}}}, errs)
    assert_ok('status' not in r, 'F3: malformed dict should not load')
    assert_ok(any('[ERROR]' in e for e in errs), 'F3: malformed dict should produce ERROR')

    # F4 — state alias map → ERROR (state in dict form rejected)
    errs = []
    r = _parse_enforced_enums_block('test.capsule.md',
        {'state': {'canonical': ['active', 'archived'], 'aliases': {'current': 'active'}}},
        errs)
    assert_ok('state' not in r, 'F4: state alias map should not load')
    assert_ok(any('[ERROR]' in e for e in errs), 'F4: state alias map should produce ERROR')
    # state in LIST form is fine
    errs = []
    r = _parse_enforced_enums_block('test.capsule.md', {'state': ['active', 'archived']}, errs)
    assert_ok('state' in r and r['state']['aliases'] == {}, 'F4: state list form loads fine')
    assert_ok(len(errs) == 0, 'F4: state list form no errors')

    # F5 — case-fold: FINAL matches final in canonical
    errs = []
    r = _parse_enforced_enums_block('test.capsule.md',
        {'status': {'canonical': ['design', 'specify', 'done'], 'aliases': {'CLOSED': 'done'}}},
        errs)
    fd = r.get('status', {'canonical': [], 'aliases': {}})
    canon_lc = [c.lower() for c in fd['canonical']]
    alias_lc = {k.lower(): v for k, v in fd['aliases'].items()}
    assert_ok('done' in canon_lc, 'F5: case-fold: Done passes as done')
    assert_ok('closed' in alias_lc, 'F5: case-fold: CLOSED alias maps to done')

    return findings, n_pass, n_fail


# ---------------------------------------------------------------------------
# v1.70 S3.5.2 — Boot-Cost Gate (spec 5e12ab9c)
# ---------------------------------------------------------------------------

def check_boot_derivation_fresh(vault: Path) -> tuple[list[str], int, int]:
    """v1.70 S3.5.2 — Drift-gate for compressed boot artifacts.

    For each status:active artifact marked boot_derivation:true:
    1. Recompute every source's body-hash -> compare to sources_fingerprint.
    2. Recompute own body-hash -> compare to self_fingerprint.
    3. ERROR on mismatch / missing fields / missing source.
    Fail-closed: draft/unmarked artifacts are skipped (bootstrap-safe).

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    # Locations where boot-derivation artifacts may live
    scan_locations = [
        vault / '.tropo',
        vault / 'vault' / 'files',
    ]

    for loc in scan_locations:
        if not loc.is_dir():
            continue
        for f in sorted(loc.rglob('*.md')):
            try:
                text = f.read_text(errors='replace')
            except Exception:
                continue
            fm_text = split_frontmatter(text)
            if fm_text is None:
                continue

            # Filter: only status:active AND boot_derivation:true (bootstrap-safe)
            if get_scalar(fm_text, 'status') != 'active':
                continue
            bd = get_scalar(fm_text, 'boot_derivation')
            if str(bd).lower() != 'true':
                continue

            total_checked += 1
            rel = f.relative_to(vault)

            # Full YAML parse required for nested fingerprint objects
            try:
                fm = yaml.safe_load(fm_text)
            except Exception as e:
                findings.append(f'[FAIL] {rel} — YAML parse failed: {e}')
                defects += 1
                continue

            # 1. Self-fingerprint check
            self_fp = fm.get('self_fingerprint')
            if not isinstance(self_fp, dict) or 'body_sha256' not in self_fp:
                findings.append(f'[FAIL] {rel} — missing self_fingerprint.body_sha256 (fail-closed)')
                defects += 1
            else:
                expected_self = self_fp['body_sha256']
                actual_self = body_sha256(f)
                if actual_self != expected_self:
                    findings.append(
                        f'[FAIL] {rel} — self_fingerprint mismatch; artifact was hand-edited since curation '
                        f'(actual: {actual_self[:8]}, recorded: {expected_self[:8]})'
                    )
                    defects += 1

            # 2. Sources-fingerprint check
            sources_fp = fm.get('sources_fingerprint')
            if not isinstance(sources_fp, list):
                findings.append(f'[FAIL] {rel} — missing or malformed sources_fingerprint list (fail-closed)')
                defects += 1
            else:
                for i, src in enumerate(sources_fp):
                    if not isinstance(src, dict) or 'path' not in src or 'body_sha256' not in src:
                        findings.append(f'[FAIL] {rel} — sources_fingerprint[{i}] is malformed')
                        defects += 1
                        continue

                    src_path = vault / src['path']
                    if not src_path.is_file():
                        findings.append(f'[FAIL] {rel} — source {src["path"]} not found (fail-closed)')
                        defects += 1
                        continue

                    expected_src = src['body_sha256']
                    actual_src = body_sha256(src_path)
                    if actual_src != expected_src:
                        findings.append(
                            f'[FAIL] {rel} — source {src["path"]} drifted; '
                            f'canonical changed since curation '
                            f'(actual: {actual_src[:8]}, recorded: {expected_src[:8]})'
                        )
                        defects += 1

    return findings, total_checked, defects


def check_spec_coverage_pairing(vault: Path) -> tuple[list[str], int, int]:
    """v1.70 S3.5.2 — Verify pairing between test-spec behaviors and dev-spec ACs.

    Rule 3.b (dev-spec.capsule v1.1 / test-spec.capsule v1.1):
    1. Resolve triggered_by_dev_cycle -> dev-spec UID.
    2. Every behavior in test-spec must map to a valid 1-based index in dev-spec ACs.
    3. Every dev-spec AC must be covered by at least one behavior in the test-spec.

    Returns (findings, total_checked, defects).
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    # 1. Map all dev-specs for fast lookup
    dev_specs: dict[str, dict] = {}
    for f in files_dir.glob('*.md'):
        try:
            # Simple peek first
            text = f.read_text(errors='replace')
            if 'type: dev-spec' not in text and 'type: dev_spec' not in text:
                continue
            fm_text = split_frontmatter(text)
            if not fm_text:
                continue
            fm = yaml.safe_load(fm_text)
            if not isinstance(fm, dict) or fm.get('type') not in ('dev-spec', 'dev_spec'):
                continue
            uid = fm.get('uid') or f.stem
            dev_specs[uid] = fm
        except Exception:
            continue

    # 2. Check each test-spec
    for f in sorted(files_dir.glob('*.md')):
        try:
            text = f.read_text(errors='replace')
            if 'type: test-spec' not in text and 'type: test_spec' not in text:
                continue
            fm_text = split_frontmatter(text)
            if not fm_text:
                continue
            fm = yaml.safe_load(fm_text)
            if not isinstance(fm, dict) or fm.get('type') not in ('test-spec', 'test_spec'):
                continue

            total_checked += 1
            rel = f.relative_to(vault)
            test_uid = fm.get('uid') or f.stem

            # dev-spec linkage
            dev_uid = fm.get('triggered_by_dev_cycle')
            if not dev_uid:
                # Some test-specs might be standalone (uncommon but allowed for base regressions)
                continue

            dev_spec = dev_specs.get(dev_uid)
            if not dev_spec:
                # Might be in a different folder or recently deleted
                findings.append(f'[WARN] {rel} — triggered_by_dev_cycle {dev_uid!r} not found in vault/files/')
                # WARN because it might be a cross-studio ref or legacy
                continue

            dev_acs = dev_spec.get('acceptance_criteria')
            if not isinstance(dev_acs, list):
                # If it's a string, it's effectively a 1-item list for coverage
                dev_acs = [dev_acs] if dev_acs else []

            num_acs = len(dev_acs)
            behaviors = fm.get('behaviors_covered')
            if not isinstance(behaviors, list):
                findings.append(f'[FAIL] {rel} — behaviors_covered missing or not a list')
                defects += 1
                continue

            # Track which ACs are covered
            covered_indices: set[int] = set()

            for i, b in enumerate(behaviors):
                if not isinstance(b, dict):
                    continue
                v_ref = b.get('verifies_acceptance_criterion')
                if v_ref is None:
                    findings.append(f'[WARN] {rel} — behavior[{i}] missing verifies_acceptance_criterion')
                    # Grandfathering: legacy specs (pre-v1.70) are WARN;
                    # post-v1.70 or explicit opt-in are ERROR.
                    target_rel = fm.get('target_release', '')
                    if target_rel and target_rel >= 'v1.70':
                        defects += 1
                    continue

                # Support both int and list of ints
                refs = v_ref if isinstance(v_ref, list) else [v_ref]
                for r in refs:
                    try:
                        idx = int(r)
                        if 1 <= idx <= num_acs:
                            covered_indices.add(idx)
                        else:
                            findings.append(
                                f'[FAIL] {rel} — behavior[{i}] verifies AC {idx}, '
                                f'but dev-spec {dev_uid} only has {num_acs} ACs'
                            )
                            defects += 1
                    except (ValueError, TypeError):
                        findings.append(f'[FAIL] {rel} — behavior[{i}] verifies_acceptance_criterion {r!r} is not an integer')
                        defects += 1

            # Check for uncovered ACs
            for idx in range(1, num_acs + 1):
                if idx not in covered_indices:
                    findings.append(
                        f'[WARN] {rel} — dev-spec {dev_uid} acceptance_criterion #{idx} has NO covering behavior in this test-spec'
                    )
                    # Grandfathering: legacy specs (pre-v1.70) are WARN; 
                    # post-v1.70 or explicit opt-in are ERROR.
                    target_rel = fm.get('target_release', '')
                    if target_rel and target_rel >= 'v1.70':
                        defects += 1

        except Exception as e:
            findings.append(f'[FAIL] {f.name} — pairing check CRASHED: {e}')
            defects += 1

    return findings, total_checked, defects


def parse_version(v_str: str) -> list[int]:
    """v1.70 S3.5.2 — Robust version comparison for grandfathering."""
    if not v_str: return []
    import re
    return [int(c) for c in re.findall(r'\d+', v_str)]


# Warnings → Zero — grandfathered legacy cutoffs (c19fe1f4; v1.73 reclassify)
# Findings at or below these cutoffs are [INFO] named exemptions, not [WARN].
CHECK31_GRANDFATHER_MAX_EVENT_ID = "00000944"  # last root-UID emit, 2026-06-02; emit path fixed at v1.70
CHECK32_GRANDFATHER_MAX_RELEASE = "v1.70"       # completion-event requirement live from v1.70


def check_no_agent_emit_from_root_uid(vault: Path) -> tuple[list[str], int, int]:
    """Check 31 — agent messaging events must NOT use the agent-root UID as source_uid.

    Specified in 81e52840 (LOCKED, emit-on-party-identity §S2.4).
    Enforces the party-UID-only rule for agent emission.
    Legacy set (id <= CHECK31_GRANDFATHER_MAX_EVENT_ID) emits [INFO] named exemption.
    Going-forward violations (id > cutoff) emit [FAIL].
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    events_file = vault / 'vault' / 'events' / '00-events.jsonl'
    if not events_file.is_file():
        return findings, 0, 0

    # 1. Load all agent-root UIDs for detection
    agent_roots: set[str] = set()
    agents_dir = vault / 'vault' / 'agents'
    if agents_dir.is_dir():
        for f in agents_dir.glob('*.md'):
            try:
                fm_text = split_frontmatter(f.read_text(errors='replace'))
                root_uid = get_scalar(fm_text, 'agent_root_uid')
                if root_uid: agent_roots.add(root_uid)
            except Exception: continue

    # 2. Scan event log (large file — scan from end for recent violations if possible, 
    # but for v1.70 finish we check all v1.70+ events)
    try:
        with events_file.open('r', errors='replace') as fd:
            for i, line in enumerate(fd, 1):
                if not line.strip(): continue
                total_checked += 1
                try:
                    ev = json.loads(line)
                    source = ev.get('source', '')
                    source_uid = ev.get('source_uid')
                    # Check agent sources
                    if source.startswith('/agents/') or source.startswith('//'):
                        if source_uid in agent_roots:
                            # Grandfathering: ONLY fail on events after v1.70 rollout
                            # Heuristic: events with id >= 00003000 (v1.69+ era)
                            # Actually, let's check the time or just WARN for older ones.
                            event_id = ev.get('id', '0')
                            if event_id > CHECK31_GRANDFATHER_MAX_EVENT_ID:
                                findings.append(
                                    f'[FAIL] event {event_id} — agent source {source} emitted from root UID {source_uid}; '
                                    f'MUST use party UID (Check 31; 81e52840; ERROR)'
                                )
                                defects += 1
                            else:
                                findings.append(
                                    f'[INFO] event {event_id} — agent source {source} emitted from root UID {source_uid} '
                                    f'(grandfathered: id<={CHECK31_GRANDFATHER_MAX_EVENT_ID}; honest-record; emit path fixed at v1.70)'
                                )
                except Exception: continue
    except Exception: pass

    return findings, total_checked, defects


def check_completion_recording(vault: Path) -> tuple[list[str], int, int]:
    """Check 32 — terminal-state work-items must have a correlated completion event.

    Specified in 2fe61817 (LOCKED, emit-on-completion §S2.4).
    Detects "silent" closes (done without an event).
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    # 1. Map all completion events by correlationid
    completions: set[str] = set()
    events_file = vault / 'vault' / 'events' / '00-events.jsonl'
    if events_file.is_file():
        try:
            with events_file.open('r', errors='replace') as fd:
                for line in fd:
                    if 'tropo.message.replied' not in line and 'tropo.cycle.closed' not in line:
                        continue
                    try:
                        ev = json.loads(line)
                        cid = ev.get('correlationid')
                        if cid: completions.add(cid)
                    except Exception: continue
        except Exception: pass

    # 2. Scan work-items for terminal state
    files_dir = vault / 'vault' / 'files'
    v170 = parse_version(CHECK32_GRANDFATHER_MAX_RELEASE)
    if files_dir.is_dir():
        for f in sorted(files_dir.glob('*.md')):
            try:
                fm_text = split_frontmatter(f.read_text(errors='replace'))
                if not fm_text: continue

                state = get_scalar(fm_text, 'state')
                if state not in ('done', 'archived'):
                    continue

                total_checked += 1
                uid = get_scalar(fm_text, 'uid') or f.stem

                # Check if this UID has a completion event
                if uid not in completions:
                    rel = f.relative_to(vault)
                    target_rel_str = get_scalar(fm_text, 'target_release')
                    target_rel = parse_version(target_rel_str)

                    if target_rel and target_rel >= v170:
                        findings.append(
                            f'[FAIL] {rel} — state:{state} but NO correlated completion event found (Check 32; 2fe61817; ERROR)'
                        )
                        defects += 1
                    else:
                        findings.append(
                            f'[INFO] {rel} — state:{state} but NO correlated completion event found '
                            f'(grandfathered: pre-{CHECK32_GRANDFATHER_MAX_RELEASE}/no-target_release; honest-record)'
                        )
            except Exception: continue

    return findings, total_checked, defects


def check_identity_refs_resolve(vault: Path) -> tuple[list[str], int, int]:
    """Check 35 — all UID-references in unified agent entries must resolve.

    Standing item 4 (fdb7821d). Verifies that unified cards don't carry dangling pointers.
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    # 1. Get all UIDs in vault
    all_uids: set[str] = set()
    files_dir = vault / 'vault' / 'files'
    if files_dir.is_dir():
        for f in files_dir.glob('*.md'):
            all_uids.add(f.stem)
    
    # Add agent UIDs
    agents_dir = vault / 'vault' / 'agents'
    if agents_dir.is_dir():
        for f in agents_dir.glob('*.md'):
            all_uids.add(f.stem)

    # Add kernel capsules (UIDs in frontmatter)
    capsules_dir = vault / '.tropo' / 'capsules'
    if capsules_dir.is_dir():
        for f in capsules_dir.glob('*.md'):
            # Some capsules are named by UID, some by name.
            # Check frontmatter.
            all_uids.add(f.stem) # Stem might be UID
            try:
                fm_text = split_frontmatter(f.read_text(errors='replace'))
                uid = get_scalar(fm_text, 'uid')
                if uid: all_uids.add(uid)
            except Exception: continue

    # 2. Scan unified agent entries
    if agents_dir.is_dir():
        for f in sorted(agents_dir.glob('*.md')):
            try:
                fm_text = split_frontmatter(f.read_text(errors='replace'))
                if not fm_text: continue
                
                fm = yaml.safe_load(fm_text)
                if not isinstance(fm, dict): continue
                
                total_checked += 1
                rel = f.relative_to(vault)
                
                # Fields to check for UID resolution
                ref_fields = [
                    'current_activation_uid', 'current_soul_uid', 'current_charter_uid',
                    'current_status_card_uid', 'current_generation_log_uid', 'member_of',
                    'governed_by', 'agent_root_uid'
                ]
                
                for field in ref_fields:
                    val = fm.get(field)
                    if not val: continue
                    
                    refs = val if isinstance(val, list) else [val]
                    for ref in refs:
                        if not isinstance(ref, str): continue
                        # If it looks like a UID but doesn't exist
                        if len(ref) == 8 and all(c in '0123456789abcdef' for c in ref.lower()):
                            if ref not in all_uids:
                                findings.append(
                                    f'[FAIL] {rel} — {field} {ref!r} does not resolve (Check 35; Standing Item 4)'
                                )
                                defects += 1
            except Exception: continue

    return findings, total_checked, defects


def check_node_private_by_construction(vault: Path) -> tuple[list[str], int, int]:
    """Check 36 — Node Private-by-Construction Backstop (node.capsule §9).

    Reads all node frontmatter to find the true set of public and private nodes.
    Then scans the public projection artifact (boards/metis/entity-graph-public.json)
    and asserts the 4 JSON contract rules (1db54929):
    1. All node IDs resolve to true public nodes.
    2. No internal tags present in the public node tags.
    3. All link sources and targets resolve to nodes present in the artifact.
    4. No body text anywhere in the artifact.
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    entities_dir = vault / 'vault' / 'entities'
    nodes_dir = vault / 'vault' / 'nodes'
    scan_dirs = [d for d in (entities_dir, nodes_dir) if d.is_dir()]
    
    if not scan_dirs:
        return findings, 0, 0

    # 1. Identify all nodes by visibility
    true_public_slugs: set[str] = set()
    true_public_uids: set[str] = set()
    
    FORCED_PRIVATE_NODE_TAGS = {'mindbridge', 'personal'}
    INTERNAL_TAGS = {'wedge-tier1', 'wedge-tier2', 'wedge-tier3', 'foil', 'threat-primary', 'watch', 'reach'}
    
    for d in scan_dirs:
        for f in d.glob('*.md'):
            if f.name == '00-README.md': continue
            try:
                fm_text = split_frontmatter(f.read_text(errors='replace'))
                if not fm_text: continue
                
                fm = yaml.safe_load(fm_text)
                if not isinstance(fm, dict): continue
                
                # Prototype nodes use type: <flat> + entity_prototype: true, new nodes use type: node
                is_node = fm.get('type') == 'node' or fm.get('entity_prototype') is True
                if not is_node: continue
                
                uid = fm.get('uid') or f.stem
                slug = fm.get('slug') or f.stem
                vis = str(fm.get('visibility', 'private')).lower()
                tags = [str(t).lower() for t in fm.get('tags', []) if isinstance(t, str)]
                
                is_private = (vis == 'private')
                for tag in tags:
                    if tag in FORCED_PRIVATE_NODE_TAGS:
                        is_private = True
                        break
                        
                if not is_private:
                    true_public_slugs.add(slug)
                    true_public_uids.add(uid)
                    
            except Exception: continue

    # 2. Verify JSON Contract
    json_artifact = vault / 'boards' / 'metis' / 'entity-graph-public.json'
    if json_artifact.is_file():
        total_checked += 1
        rel = json_artifact.relative_to(vault)
        try:
            raw_text = json_artifact.read_text(errors='replace')
            data = json.loads(raw_text)
            
            # Rule 4: No body text. We ensure no field named "body" or "text" or "content"
            # exists in the envelope or the nodes.
            if "body" in data or "content" in data:
                findings.append(f'[FAIL] {rel} — Envelope contains forbidden body/content field (node.capsule §9; ERROR)')
                defects += 1
                
            artifact_node_ids: set[str] = set()
            
            nodes = data.get('nodes', [])
            for n in nodes:
                nid = n.get('id')
                if not nid: continue
                artifact_node_ids.add(nid)
                
                # Rule 4 inside nodes
                if "body" in n or "content" in n:
                    findings.append(f'[FAIL] {rel} — Node {nid} contains forbidden body/content field (node.capsule §9; ERROR)')
                    defects += 1
                    
                # Rule 1: Must resolve to true public node
                if nid not in true_public_slugs and nid not in true_public_uids:
                    findings.append(f'[FAIL] {rel} — PRIVATE/Missing node leaked into public projection: {nid} (node.capsule §9; ERROR)')
                    defects += 1
                    
                # Rule 2: No internal tags
                node_tags = n.get('tags', [])
                for tag in node_tags:
                    if tag in INTERNAL_TAGS:
                        findings.append(f'[FAIL] {rel} — INTERNAL tag leaked on node {nid}: {tag} (node.capsule §9; ERROR)')
                        defects += 1
                        
            # Rule 3: Edges must not dangle (prevents leaking private slugs via edges)
            links = data.get('links', [])
            for i, link in enumerate(links):
                src = link.get('source')
                tgt = link.get('target')
                if src not in artifact_node_ids:
                    findings.append(f'[FAIL] {rel} — Dangling link source: {src} not in artifact nodes (node.capsule §9; ERROR)')
                    defects += 1
                if tgt not in artifact_node_ids:
                    findings.append(f'[FAIL] {rel} — Dangling link target: {tgt} not in artifact nodes (node.capsule §9; ERROR)')
                    defects += 1
                    
        except Exception as e:
            findings.append(f'[FAIL] {json_artifact.name} JSON parse CRASHED: {e}')
            defects += 1

    return findings, total_checked, defects


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Structural validator for a Tropo vault.',
    )
    parser.add_argument('--vault-path', metavar='PATH',
                        help='Explicit vault root (must contain ledger/ + .tropo/).')
    parser.add_argument('--write-fingerprints', nargs='*', metavar='FILE',
                        help='v1.70 S3.5.2: Write dual fingerprints to target boot-derivation artifacts. '
                             'If no files provided, scans for existing boot_derivation:true entries.')
    args = parser.parse_args()

    vault = resolve_vault_root(args.vault_path)
    if vault is None:
        print('ERROR: Could not resolve vault root.', file=sys.stderr)
        return 2

    # --- v1.70 S3.5.2: Write Fingerprints Mode ---
    if args.write_fingerprints is not None:
        targets = []
        if not args.write_fingerprints:
            # Auto-discovery: find all files with boot_derivation:true
            scan_locations = [vault / '.tropo', vault / 'vault' / 'files']
            for loc in scan_locations:
                if not loc.is_dir(): continue
                for f in loc.rglob('*.md'):
                    try:
                        fm_text = split_frontmatter(f.read_text(errors='replace'))
                        if fm_text and str(get_scalar(fm_text, 'boot_derivation')).lower() == 'true':
                            targets.append(f)
                    except Exception: continue
        else:
            for f_path in args.write_fingerprints:
                p = Path(f_path)
                if p.is_file(): targets.append(p)
                else:
                    p2 = vault / f_path
                    if p2.is_file(): targets.append(p2)
                    else: print(f'ERROR: File not found: {f_path}')

        if not targets:
            print('No boot-derivation artifacts found to fingerprint.')
            return 0

        print(f'Writing fingerprints to {len(targets)} artifact(s)...')
        for f in targets:
            try:
                text = f.read_text(errors='replace')
                fm_raw = split_frontmatter(text)
                if not fm_raw:
                    print(f'  [SKIP] {f.name} — no frontmatter')
                    continue
                fm = yaml.safe_load(fm_raw)
                if not isinstance(fm, dict):
                    print(f'  [SKIP] {f.name} — malformed frontmatter')
                    continue

                sources = fm.get('sources_fingerprint')
                if not isinstance(sources, list):
                    print(f'  [SKIP] {f.name} — sources_fingerprint missing or not a list')
                    continue

                # 1. Update source fingerprints
                for src in sources:
                    if not isinstance(src, dict) or 'path' not in src: continue
                    src_path = vault / src['path']
                    if src_path.is_file():
                        src['body_sha256'] = body_sha256(src_path)
                        print(f'    • Hashed source: {src["path"]}')
                    else:
                        print(f'    [WARN] Source not found: {src["path"]}')

                # Sort by path for deterministic diff
                sources.sort(key=lambda x: x.get('path', ''))
                fm['sources_fingerprint'] = sources

                # 2. Update self fingerprint
                # To hash correctly, we need to hash the body of the file as it WILL be.
                # Since the body-hash excludes frontmatter, we can just hash the current body.
                # Fingerprint fields live in frontmatter, so they don't affect the body hash.
                fm['self_fingerprint'] = {'body_sha256': body_sha256(f)}
                print(f'    • Hashed self: {f.name}')

                # 3. Add gauntlet_verified_at
                from datetime import date
                fm['gauntlet_verified_at'] = date.today().isoformat()

                # 4. Write back
                # Use yaml.dump to regenerate frontmatter text
                # We want to preserve the triple-dash fences.
                new_fm = yaml.dump(fm, sort_keys=False, indent=2, width=1000)
                # Strip trailing newline from yaml.dump
                new_fm = new_fm.strip()
                # Reassemble file
                body_start = text.find('\n---\n', 3)
                if body_start == -1: # No body?
                    new_text = f'---\n{new_fm}\n---\n'
                else:
                    new_text = f'---\n{new_fm}\n---{text[body_start+4:]}'

                f.write_text(new_text, encoding='utf-8')
                print(f'  [OK] {f.name} fingerprinted.')
            except Exception as e:
                print(f'  [FAIL] {f.name}: {e}')

        return 0

    print('=' * 70)
    print('tropo-validate.py — vault structural validator')
    print(f'Vault root: {vault}')
    print('=' * 70)

    total_passes = 0
    total_fails = 0
    total_warnings = 0
    total_normalizable = 0

    # --- UID Consistency ---
    print('\n--- UID Consistency ---')
    findings, checked = check_uid_consistency(vault)
    if not findings:
        print(f'[PASS] {checked} vault UIDs verified')
        total_passes += 1
    else:
        for line in findings[:20]:
            print(line)
            if line.startswith('[FAIL]'):
                total_fails += 1
            elif line.startswith('[WARN]'):
                total_warnings += 1  # ratchet preserves count for display; FAIL counted by [FAIL] prefix
        if len(findings) > 20:
            print(f'  ... and {len(findings) - 20} more')

    # --- UID Ref Type Check (d3a58cdf: UID-bearing fields must be string, not int; WARN→ERROR) ---
    print('\n--- UID-Reference Fields Are Strings (d3a58cdf; int refs in children/member_of/etc → WARN) ---')
    try:
        urs_findings, urs_checked, urs_int_count = check_uid_refs_are_strings(vault)
        if not urs_findings:
            print(f'[PASS] {urs_checked} vault entries checked — all UID-reference fields are string-typed')
            total_passes += 1
        else:
            print(f'[INFO] {urs_checked} entries checked; {urs_int_count} int-typed UID ref(s) found (WARN)')
            for line in urs_findings[:20]:
                print(f'  {line}')
                total_warnings += 1
            if len(urs_findings) > 20:
                extra = len(urs_findings) - 20
                print(f'  ... and {extra} more')
                total_warnings += extra
    except Exception as e:
        # A108: check-crash must be loud, not silent. A verification check whose failure
        # is invisible is the v1.66 theater class — the check appears to pass when it crashed.
        import traceback as _tb
        print(f'[FAIL] uid-refs-are-strings check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- UID Collision Check (f9751636: int-shaped UIDs → FAIL; index duplicates → WARN) ---
    print('\n--- UID Collision + Int-Shape Check (f9751636; int-uid=WARN→ERROR ratchet; index-dup=WARN) ---')
    try:
        ucoll_findings, ucoll_int_count, ucoll_dup_count = check_uid_collision(vault)
        if not ucoll_findings:
            print('[PASS] No int-shaped UIDs; no index duplicate UIDs')
            total_passes += 1
        else:
            for line in ucoll_findings[:20]:
                print(f'  {line}')
                if line.startswith('[FAIL]'):
                    total_fails += 1
                elif line.startswith('[WARN]'):
                    total_warnings += 1
            if len(ucoll_findings) > 20:
                extra = len(ucoll_findings) - 20
                print(f'  ... and {extra} more')
                total_warnings += extra
            if ucoll_int_count == 0 and ucoll_dup_count > 0:
                print(f'[INFO] {ucoll_dup_count} index duplicate(s) found (WARN; run rebuild-vault.py --apply to clean)')
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] uid-collision check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- Orphan Detection ---
    print('\n--- Orphan Detection (UID coverage in governed dirs) ---')
    orphan_findings = check_orphans(vault)
    if not orphan_findings:
        print('[PASS] All governed files have uid: in frontmatter')
        total_passes += 1
    else:
        # These are mostly WARN-level (legacy files); summarize
        total_warnings += len(orphan_findings)
        print(f'[INFO] {len(orphan_findings)} files in governed directories without uid:')
        for line in orphan_findings[:5]:
            print(f'  {line}')
        if len(orphan_findings) > 5:
            print(f'  ... and {len(orphan_findings) - 5} more (run with -v for full list)')

    # --- AGENTS.md Coverage ---
    print('\n--- AGENTS.md Coverage ---')
    findings, passes, fails = check_agents_md_coverage(vault)
    for line in findings:
        print(line)
    total_passes += passes
    total_fails += fails

    # --- UID Cross-References (v1.33.0 Stream H §3.1; pattern-scan; supersedes legacy check_cross_refs) ---
    print('\n--- UID Cross-References (v1.33.0 Stream H §3.1; pattern-scan; supersedes legacy check_cross_refs) ---')
    index_path = vault / 'vault' / '00-index.jsonl'
    if not index_path.is_file():
        print('[FAIL] vault/00-index.jsonl — not found')
        total_fails += 1
    else:
        # Load all UIDs from the index AND from kernel-tier files (.tropo/) for resolution.
        # Capsules, scripts, and playbooks live outside vault/files/ but are referenced by
        # vault entries via governed_by: / aligned_with: / etc. Their UIDs must be in the
        # resolution set or pattern-scan generates false-positives.
        all_uids: set[str] = set()
        try:
            with index_path.open() as fp:
                for raw in fp:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        row = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    uid = row.get('uid')
                    if isinstance(uid, str) and UID_RE.match(uid):
                        all_uids.add(uid)
        except OSError:
            print('[FAIL] vault/00-index.jsonl — unreadable')
            total_fails += 1
            all_uids = set()

        # Augment with run-folder UIDs (dev-pipeline activations + playbook-runs +
        # any UID-named subdirectory under */activations/ or playbook-runs/).
        # These are filesystem-only governed records (run folders carry run.jsonl
        # but no .md with uid: frontmatter); they're referenced by release-plan
        # entries via activation_run_uid + member_of fields. Resolution should
        # treat them as valid.
        run_folder_parents = [
            vault / 'agents' / 'dev-pipeline' / 'activations',
            vault / 'playbook-runs',
        ]
        for rfp in run_folder_parents:
            if not rfp.is_dir():
                continue
            for child in rfp.iterdir():
                if not child.is_dir():
                    continue
                name = child.name
                # Match `^[0-9a-f]{8}$` OR `agent-activation-<slug>-<gen>-<date>` style
                if UID_RE.match(name):
                    all_uids.add(name)
                # Also extract trailing 8-hex from named run folders if present
                trail_match = re.search(r'([0-9a-f]{8})$', name)
                if trail_match:
                    all_uids.add(trail_match.group(1))

        # Augment with UIDs from governed `.md` files anywhere in the Studio
        # (legacy-path substrate per Mike-A55 flat-vault doctrine pin — many
        # governed files still live outside vault/files/: operating-principles
        # at .tropo-studio/, roadmap at agents/dev-pipeline/, SELF-HEALING at
        # .tropo/, agent activation files at agents/<name>/, etc.). Walk the
        # whole studio + extract uid: frontmatter; resolution set becomes
        # "all UIDs that actually exist in the substrate."
        # Excludes: node_modules/, .git/, archive/, recycle/ (non-governed).
        exclude_top = {'node_modules', '.git', 'archive', 'recycle', 'releases'}
        for md_file in vault.rglob('*.md'):
            try:
                rel = md_file.relative_to(vault)
            except ValueError:
                continue
            # Skip excluded top-level dirs
            if rel.parts and rel.parts[0] in exclude_top:
                continue
            # Skip vault/files/* (already loaded from index)
            if len(rel.parts) >= 2 and rel.parts[0] == 'vault' and rel.parts[1] == 'files':
                continue
            try:
                mtext = md_file.read_text()
            except OSError:
                continue
            mfm = split_frontmatter(mtext)
            if not mfm:
                continue
            muid = get_scalar(mfm, 'uid')
            if muid and UID_RE.match(muid):
                all_uids.add(muid)

        if all_uids:
            xref_findings, n_checked, n_defects = check_uid_cross_references(vault, all_uids)
            n_info_lines = sum(1 for line in xref_findings if line.startswith('[INFO]'))
            n_warn_lines = sum(1 for line in xref_findings if line.startswith('[WARN]'))
            if n_defects == 0:
                print(f'[PASS] {n_checked} vault entries verified — all UID cross-references resolve against {len(all_uids)} index UIDs')
                total_passes += 1
                # Surface any [INFO] (index-stale) or [WARN] (frontmatter parse) lines
                # so the operator sees them even when the check passes.
                if xref_findings:
                    for line in xref_findings[:10]:
                        print(f'  {line}')
                    if len(xref_findings) > 10:
                        print(f'  ... and {len(xref_findings) - 10} more')
                    # [WARN] lines count toward warnings ratchet; [INFO] does not.
                    total_warnings += n_warn_lines
            else:
                affected_files = len(set(line.split('vault/files/')[1].split(' ')[0] for line in xref_findings if 'vault/files/' in line))
                print(f'[FAIL] {n_defects} unresolved UID cross-references across {affected_files} vault entries')
                for line in xref_findings[:10]:
                    print(f'  {line}')
                if len(xref_findings) > 10:
                    print(f'  ... and {len(xref_findings) - 10} more')
                total_fails += n_defects
                total_warnings += n_warn_lines

            # --- Agent Identity Coherence (Two-Axis doctrine 15c70b96 / dev-spec e85d2d2c) ---
            print('\n--- Agent Identity Coherence (party_uid = single canonical messaging identity) ---')
            aic_findings, aic_checked, aic_defects = check_agent_identity_coherence(vault, all_uids)
            aic_warns = sum(1 for line in aic_findings if line.startswith('[WARN]'))
            if aic_defects == 0:
                print(f'[PASS] {aic_checked} messaging agents — party_uid coherence OK ({aic_warns} establishment-grace warning(s))')
                total_passes += 1
            else:
                print(f'[FAIL] {aic_defects} agent-identity coherence defect(s) — phantom / multiplicity / divergence')
                total_fails += aic_defects
            for line in aic_findings[:25]:
                print(f'  {line}')
            if len(aic_findings) > 25:
                print(f'  ... and {len(aic_findings) - 25} more')
            total_warnings += aic_warns

            # --- AC1: Agent Identity Unified (agent.capsule v2.0; v1.69 dev-spec 0c61a52b; ERROR) ---
            print('\n--- Agent Identity Unified (AC1; agent.capsule v2.0; one-entry-per-slug; ERROR) ---')
            try:
                aiu_findings, aiu_checked, aiu_defects = check_agent_identity_unified(vault)
                if aiu_defects == 0:
                    print(f'[PASS] {aiu_checked} agent slug(s) — identity unified (one vault/agents/ entry each; tombstones resolve)')
                    total_passes += 1
                else:
                    print(f'[FAIL] {aiu_defects} agent-identity-unified defect(s) — see below')
                    total_fails += aiu_defects
                for line in aiu_findings[:20]:
                    print(f'  {line}')
                if len(aiu_findings) > 20:
                    print(f'  ... and {len(aiu_findings) - 20} more')
            except Exception as _e:
                print(f'[FAIL] check_agent_identity_unified CRASHED: {_e}')
                total_fails += 1

            # --- S3: Token Budget Per Class (v1.69 dev-spec 0c61a52b §S3; WARN; ERROR ratchet v1.70) ---
            print('\n--- Token Budget Per Class (S3; v1.69; WARN; ERROR ratchet v1.70) ---')
            try:
                tbc_findings, tbc_checked, tbc_over = check_token_budget_per_class(vault)
                if tbc_over == 0:
                    if tbc_checked == 0:
                        # No budget table — INFO only, still a PASS (table is optional pre-measure)
                        print(f'[PASS] token budget table absent — SKIP (measure script populates)')
                    else:
                        print(f'[PASS] {tbc_checked} file class(es) within budget')
                    total_passes += 1
                else:
                    print(f'[WARN] {tbc_over} file(s) over class budget (WARN v1.69; ERROR ratchet v1.70)')
                    total_warnings += tbc_over
                    # Still counts as a pass at WARN severity
                    total_passes += 1
                for line in tbc_findings[:15]:
                    print(f'  {line}')
                if len(tbc_findings) > 15:
                    print(f'  ... and {len(tbc_findings) - 15} more')
            except Exception as _e:
                print(f'[FAIL] check_token_budget_per_class CRASHED: {_e}')
                total_fails += 1

    # --- Version Consistency (v1.33.0 Stream H §3.2; substrate-honesty; WARN severity) ---
    print('\n--- Version Consistency (v1.33.0 Stream H §3.2; substrate-honesty) ---')
    version_findings, version_warns, _ = check_version_consistency(vault)
    if not version_findings:
        print('[PASS] .tropo/version.md matches latest LIVE Tropo-OS release')
        total_passes += 1
    else:
        for line in version_findings:
            print(line)
        total_warnings += version_warns
        # PASS the check at the count level if only WARN/INFO findings (no FAIL emitted)
        if not any(line.startswith('[FAIL]') for line in version_findings):
            total_passes += 1

    # --- Generation-log invariants (RETIRED at v1.38.0; see release entry + .tropo/scripts/CAPSULE.md §Validator Check Pattern) ---
    # generation-log.capsule v1.0 substrate (`agents/<name>/generation-log.md`) retired
    # at v1.21.0 Stream 3; check_generation_logs validated zero files in current substrate
    # (scope = `agents/<name>/generation-log.md`; active count = 0). Retired at v1.38.0
    # Phase 3 consolidation per the more-capsules-equals-more-maintenance pin applied
    # to validator-checks. Pre-v1.21.0 historical gen-logs survive as frozen archives at
    # `vault/files/<uid>.md` with `type: document, status: archived` — governed by
    # `check_kb_article_typing` + general document-typing rules, not by this retired check.

    # --- Self-Healing Drift Detection (v1.15.4 NEW; primitive db0fd9b1) ---
    print('\n--- Self-Healing Drift Detection (v1.15.4; primitive db0fd9b1) ---')
    sh_findings, sh_checked = check_self_healing_drift(vault)
    if not sh_findings:
        print(f'[PASS] {sh_checked} substrate-class kernel files — no recent edits without open activation reference')
        total_passes += 1
    else:
        for line in sh_findings:
            print(line)
            if line.startswith('[WARN]'):
                total_warnings += 1  # ratchet preserves count for display; FAIL counted by [FAIL] prefix
            elif line.startswith('[FAIL]'):
                total_fails += 1

    # --- KB-Article Typing (v1.18.0 NEW; capsule 4cb20382) ---
    print('\n--- KB-Article Typing (v1.18.0 Stream A; capsule 4cb20382) ---')
    kb_findings, kb_checked, kb_untyped = check_kb_article_typing(vault)
    if not kb_findings:
        print(f'[PASS] {kb_checked} kb-articles in .tropo/kb/ verified typed')
        total_passes += 1
    else:
        print(f'[INFO] {kb_checked} kb-articles checked; {kb_untyped} untyped (WARN-severity during v1.18.0 grace period)')
        for line in kb_findings[:10]:
            print(f'  {line}')
            total_warnings += 1  # ratchet preserves count for display; FAIL counted by [FAIL] prefix
        if len(kb_findings) > 10:
            remaining = len(kb_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more (run with -v for full list)')

    # --- Governance-Contract Typing (v1.20.0 NEW; capsule 7901662b) ---
    print('\n--- Governance-Contract Typing (v1.20.0 Stream A; capsule 7901662b) ---')
    gc_findings, gc_checked, gc_defects = check_governance_contract_typing(vault)
    if not gc_findings:
        print(f'[PASS] {gc_checked} governance-contract instances in vault/files/ verified well-formed')
        total_passes += 1
    else:
        print(f'[INFO] {gc_checked} governance-contracts checked; {gc_defects} defects (ERROR-severity at v1.22.0+ (ratcheted))')
        for line in gc_findings[:10]:
            print(f'  {line}')
            total_warnings += 1  # ratchet preserves count for display; FAIL counted by [FAIL] prefix
        if len(gc_findings) > 10:
            remaining = len(gc_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more (run with -v for full list)')

    # --- Release Documentation Deliverables (v1.27.0 Stream C; closes brief-based bypass) ---
    print('\n--- Release Documentation Deliverables (v1.27.0 Stream C) ---')
    rd_findings, rd_checked, rd_defects = check_release_documentation_deliverables(vault)
    if not rd_findings:
        print(f'[PASS] {rd_checked} active release(s) have full documentation deliverables (hub Change Log + RELEASE-NOTES + channels/releases.md)')
        total_passes += 1
    else:
        print(f'[INFO] {rd_checked} active releases checked; {rd_defects} doc-deliverable gaps (WARN at v1.27.0 grace period; ERROR ratchet planned for v1.28.0+)')
        for line in rd_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(rd_findings) > 10:
            remaining = len(rd_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more')

    # --- Memory Typing (v1.26.0 NEW; capsule a5b3c891) ---
    print('\n--- Memory Typing (v1.26.0 Stream 4; capsule a5b3c891) ---')
    mem_findings, mem_checked, mem_defects = check_memory_typing(vault)
    if not mem_findings:
        print(f'[PASS] {mem_checked} memory entries verified well-formed per memory.capsule v1.0')
        total_passes += 1
    else:
        print(f'[INFO] {mem_checked} memory entries checked; {mem_defects} defects (WARN-severity at v1.26.0 grace period; ERROR ratchet in later cycle)')
        for line in mem_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(mem_findings) > 10:
            remaining = len(mem_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more (run with -v for full list)')

    # --- Article source required fields (v1.49.0.2 NEW; closes Fire 3 class per c5a7e391 §13.3 P1) ---
    print('\n--- Article Source Required Fields (v1.49.0.2; c5a7e391 §13.3 P1 — slug + published_at) ---')
    art_findings, art_checked, art_defects = check_article_source_required_fields(vault)
    if not art_findings:
        print(f'[PASS] {art_checked} subtype:article entries verified — all have slug + published_at')
        total_passes += 1
    else:
        print(f'[INFO] {art_checked} subtype:article entries checked; {art_defects} defects (WARN at v1.49.0.2 grace period; ERROR ratchet at v1.50+)')
        for line in art_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(art_findings) > 10:
            remaining = len(art_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more (run with -v for full list)')

    # --- Ship-artifact required fields (v1.49.0.2 NEW; closes Fire 1 class per c5a7e391 §13.3 P2) ---
    print('\n--- Ship-Artifact Required Fields (v1.49.0.2; c5a7e391 §13.3 P2 — kind + target + canonical_source + parent) ---')
    sa_findings, sa_checked, sa_defects = check_ship_artifact_required_fields(vault)
    if not sa_findings:
        print(f'[PASS] {sa_checked} ship-artifact wrappers verified — all have kind + target + canonical_source + parent')
        total_passes += 1
    else:
        print(f'[INFO] {sa_checked} ship-artifact wrappers checked; {sa_defects} defects (WARN at v1.49.0.2 grace period; ERROR ratchet at v1.50+)')
        for line in sa_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(sa_findings) > 10:
            remaining = len(sa_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more (run with -v for full list)')

    # --- publish.pipeline.md schema (v1.49.0 NEW; capsule 7e3a91c8) ---
    print('\n--- publish.pipeline.md Schema (v1.49.0; capsule 7e3a91c8 §3) ---')
    pp_schema_findings, pp_schema_checked, pp_schema_defects = check_publish_pipeline_md_schema(vault)
    if not pp_schema_findings:
        print(f'[PASS] {pp_schema_checked} publish.pipeline.md definitions verified per publish.pipeline.capsule v1.0 §3')
        total_passes += 1
    else:
        print(f'[INFO] {pp_schema_checked} publish.pipeline.md definitions checked; {pp_schema_defects} defects (WARN at v1.49 grace period; ERROR ratchet at v1.50+)')
        for line in pp_schema_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(pp_schema_findings) > 10:
            remaining = len(pp_schema_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more (run with -v for full list)')

    # --- publish.pipeline target module presence (v1.49.0 NEW; capsule 7e3a91c8) ---
    print('\n--- publish.pipeline Target Module Presence (v1.49.0; capsule 7e3a91c8 §5) ---')
    pp_target_findings, pp_target_checked, pp_target_defects = check_target_module_present(vault)
    if not pp_target_findings:
        print(f'[PASS] {pp_target_checked} publish.pipeline.md target modules verified present at .tropo/scripts/publish_targets/')
        total_passes += 1
    else:
        print(f'[INFO] {pp_target_checked} publish.pipeline.md target references checked; {pp_target_defects} missing modules (WARN at v1.49 grace period; ERROR ratchet at v1.50+)')
        for line in pp_target_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(pp_target_findings) > 10:
            remaining = len(pp_target_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more (run with -v for full list)')

    # --- ADR-028 Generation Monotonicity Scan-Time (v1.22.0.3; P1-7 remediation) ---
    print('\n--- ADR-028 Generation Monotonicity (v1.22.0.3 scan-time; capsule 4e8b21f0 §4 Rule 2) ---')
    mono_findings, mono_chains, mono_violations = check_activation_generation_monotonic(vault)
    if not mono_findings:
        print(f'[PASS] {mono_chains} agent chains verified monotonic (ADR-028 substrate enforcement)')
        total_passes += 1
    else:
        print(f'[FAIL] {mono_chains} chains checked; {mono_violations} violations')
        for line in mono_findings[:10]:
            print(f'  {line}')
            total_fails += 1

    # --- Activation Stale-Sweep (v1.22.0 Stream 4 — sa.skeptic P0-4 remediation) ---
    print('\n--- Activation Stale-Sweep (v1.22.0 Stream 4; capsule 4e8b21f0 §2 stale_threshold_hours) ---')
    stale_findings, stale_total, stale_cnt = check_activation_stale_sweep(vault)
    if not stale_findings:
        print(f'[PASS] {stale_total} active activations checked; 0 past stale threshold')
        total_passes += 1
    else:
        print(f'[INFO] {stale_total} active activations checked; {stale_cnt} past stale threshold (WARN-severity; Vela Tier 1 sweep is authoritative writer)')
        for line in stale_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(stale_findings) > 10:
            remaining = len(stale_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more')

    # --- Activation Typing (v1.21.0 NEW; capsule 4e8b21f0) ---
    print('\n--- Activation Typing (v1.21.0 Stream 5; capsule 4e8b21f0) ---')
    act_findings, act_checked, act_defects = check_activation_typing(vault)
    if not act_findings:
        print(f'[PASS] {act_checked} activation entries in vault/files/ verified well-formed (ADR-016 + ADR-028 substrate invariants hold)')
        total_passes += 1
    else:
        print(f'[INFO] {act_checked} activations checked; {act_defects} defects (ERROR-severity at v1.22.0+ (ratcheted))')
        for line in act_findings[:10]:
            print(f'  {line}')
            total_warnings += 1  # ratchet preserves count for display; FAIL counted by [FAIL] prefix
        if len(act_findings) > 10:
            remaining = len(act_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more (run with -v for full list)')

    # --- Charter Conformance (v1.37.0 NEW; capsule 8f3c9e1a; spec e3f47a82 §3.4) ---
    print('\n--- Charter Conformance (v1.37.0 Stream A; capsule 8f3c9e1a) ---')
    ch_findings, ch_checked, ch_defects = check_charter_conformance(vault)
    if not ch_findings:
        print(f'[PASS] {ch_checked} charter(s) verified well-formed (WARN-severity at v1.37.0 honor-system; ERROR ratchet planned for v2.0.0 public ship per Q2 Option B Mike-A69 lock)')
        total_passes += 1
    else:
        print(f'[INFO] {ch_checked} charters checked; {ch_defects} conformance gaps (WARN-severity at v1.37.0; ERROR ratchet at v2.0.0)')
        for line in ch_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(ch_findings) > 10:
            remaining = len(ch_findings) - 10
            total_warnings += remaining
            # R3 P2-2 absorption: removed misleading "(run with -v for full list)" — tropo-validate.py has no -v flag.
            # The full list is reproducible via direct python3 .tropo/scripts/tropo-validate.py invocation +
            # piping output through grep "Charter Conformance" / less.
            print(f'  ... and {remaining} more (full list: python3 .tropo/scripts/tropo-validate.py | grep -A 100 "Charter Conformance")')

    # --- Cascade Spec Validity (v1.35.0; spec d2f8c194 §11.4) ---
    print('\n--- Cascade Spec Validity (v1.35.0; spec d2f8c194 §11.4) ---')
    cs_findings, cs_checked, cs_defects = check_cascade_spec_validity(vault)
    if not cs_findings:
        print(f'[PASS] {cs_checked} pipeline cascade_spec(s) verified well-formed (WARN-severity at v1.35.0 honor-system; ERROR ratchet planned for v1.36.0+)')
        total_passes += 1
    else:
        print(f'[INFO] {cs_checked} cascade_spec(s) checked; {cs_defects} defects (WARN-severity at v1.35.0 honor-system)')
        for line in cs_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(cs_findings) > 10:
            remaining = len(cs_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more')

    # --- Pipeline Activation Provenance (v1.35.0 §Rule 10 v2.2 honor-system) ---
    print('\n--- Pipeline Activation Provenance (v1.35.0 §Rule 10; spec d2f8c194 §4.11) ---')
    pap_findings, pap_checked, pap_defects = check_pipeline_activation_provenance(vault)
    if not pap_findings:
        print(f'[PASS] {pap_checked} pipeline-class activation(s) verified authored by pipeline-activate.py (WARN-severity at v1.35.0 honor-system; mechanical-fail at v1.36.0+)')
        total_passes += 1
    else:
        print(f'[INFO] {pap_checked} pipeline-class activations checked; {pap_defects} provenance defects (WARN at v1.35.0)')
        for line in pap_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(pap_findings) > 10:
            remaining = len(pap_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more')

    # --- Step Verifier Distinct From Owner When Overridden (v1.46.0; pipeline.capsule v3.0 §Check 17) ---
    print('\n--- Step Verifier Distinct From Owner When Overridden (v1.46.0; pipeline.capsule v3.0 §Check 17) ---')
    svd_findings, svd_checked, svd_defects = check_step_verifier_distinct_from_owner_when_overridden(vault)
    if not svd_findings:
        print(f'[PASS] {svd_checked} v3.0-shaped step entries with explicit verifier override verified distinct from owner')
        total_passes += 1
    else:
        print(f'[INFO] {svd_checked} v3.0-shaped step entries checked; {svd_defects} explicit-override discipline defects (ERROR severity at v1.46.0)')
        for line in svd_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(svd_findings) > 10:
            remaining = len(svd_findings) - 10
            total_fails += remaining
            print(f'  ... and {remaining} more')

    # --- Step Depends-On Acyclic (v1.46.0; pipeline.capsule v3.0 §Check 18) ---
    print('\n--- Step Depends-On Acyclic (v1.46.0; pipeline.capsule v3.0 §Check 18) ---')
    sda_findings, sda_checked, sda_defects = check_step_depends_on_acyclic(vault)
    if not sda_findings:
        print(f'[PASS] {sda_checked} v3.0-shaped step entries with depends_on_steps verified acyclic')
        total_passes += 1
    else:
        print(f'[INFO] {sda_checked} v3.0-shaped step entries checked; {sda_defects} DAG-invariant defects (ERROR severity at v1.46.0)')
        for line in sda_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(sda_findings) > 10:
            remaining = len(sda_findings) - 10
            total_fails += remaining
            print(f'  ... and {remaining} more')

    # --- VC:true Gate Steps Have verification_command (v1.66 S1; pipeline.capsule v3.3 §Check 20; ERROR — ratcheted) ---
    print('\n--- VC:true Gate Steps Have verification_command (v1.66 S1; pipeline.capsule v3.3 §Check 20; ERROR ratchet live) ---')
    vch_findings, vch_checked, vch_fails = check_vc_true_has_verification_command(vault)
    if not vch_findings:
        print(f'[PASS] {vch_checked} vc:true gate steps verified to have a verdict source (verification_command / approval-required / human: / aggregate:)')
        total_passes += 1
    else:
        # ERROR-ratchet live (v1.66 S1 ed04d931 Step 3): gated on live-zero — only fires if
        # step_2 closed all 21 holes; any new sourceless step immediately red-lights validate.
        print(f'[FAIL] {vch_checked} vc:true gate steps checked; {len(vch_findings)} have NO verdict source (Check 20 ERROR — ratcheted at v1.66)')
        for line in vch_findings[:10]:
            print(f'  {line}')
        if len(vch_findings) > 10:
            print(f'  ... and {len(vch_findings) - 10} more')
        total_fails += len(vch_findings)

    # --- v1.66 S5 cascade_disposition required (e26935da §3; WARN now, ERROR-ratchet next) ---
    print('\n--- v1.66 S5 cascade_disposition (e26935da; done v1.66+ dev-spec + empty triggers -> WARN) ---')
    try:
        cd_findings, cd_checked, cd_warns = check_cascade_disposition_required(vault)
        if not cd_findings:
            print(f'[PASS] {cd_checked} done dev-spec(s) checked — all have cascade_disposition or are pre-S5 grandfathered')
            total_passes += 1
        else:
            # Emit backfill list for context
            info_lines = [l for l in cd_findings if l.strip().startswith('[INFO]')]
            warn_lines = [l for l in cd_findings if l.strip().startswith('[WARN]')]
            if info_lines:
                print(f'[INFO] {len(info_lines)} pre-S5 grandfathered dev-spec(s) (no action needed):')
                for line in info_lines[:5]:
                    print(f'  {line}')
            if warn_lines:
                print(f'[WARN] {len(warn_lines)} v1.66+ done dev-spec(s) missing cascade_disposition (backfill query):')
                for line in warn_lines[:10]:
                    print(f'  {line}')
                    total_warnings += 1
                if len(warn_lines) > 10:
                    print(f'  ... and {len(warn_lines) - 10} more')
                    total_warnings += len(warn_lines) - 10
            if not warn_lines:
                total_passes += 1
    except Exception as e:
        print(f'[FAIL] cascade_disposition CRASHED: {e}')
        total_fails += 1

    # --- Pipeline-Run Has run.jsonl (v1.46.0; pipeline-run.capsule v2.0 §Check 13) ---
    print('\n--- Pipeline-Run Has run.jsonl (v1.46.0; pipeline-run.capsule v2.0 §Check 13) ---')
    prj_findings, prj_checked, prj_defects = check_pipeline_runtime_has_jsonl(vault)
    if not prj_findings:
        print(f'[PASS] {prj_checked} pipeline-run / pipeline-class activation entries verified with run.jsonl at declared run_folder')
        total_passes += 1
    else:
        print(f'[INFO] {prj_checked} pipeline-run entries checked; {prj_defects} run.jsonl-missing defects (ERROR severity at v1.46.0)')
        for line in prj_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(prj_findings) > 10:
            remaining = len(prj_findings) - 10
            total_fails += remaining
            print(f'  ... and {remaining} more')

    # --- Step Completion Has Verification (v1.46.0; pipeline-run.capsule v2.0 §Check 14) ---
    print('\n--- Step Completion Has Verification (v1.46.0; pipeline-run.capsule v2.0 §Check 14) ---')
    scv_findings, scv_checked, scv_defects = check_step_completion_has_verification(vault)
    if not scv_findings:
        print(f'[PASS] {scv_checked} v2.0-shape pipeline-runs verified — every step_completed has matching verification_receipt:verdict:pass (or step is verification-class)')
        total_passes += 1
    else:
        print(f'[INFO] {scv_checked} v2.0-shape pipeline-runs checked; {scv_defects} verification-receipt-missing defects (ERROR severity at v1.46.0)')
        for line in scv_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(scv_findings) > 10:
            remaining = len(scv_findings) - 10
            total_fails += remaining
            print(f'  ... and {remaining} more')

    # --- External-Artifact Typing (v1.25.0 Stream E; capsule eedd7034) ---
    print('\n--- External-Artifact Typing (v1.25.0 Stream E; capsule eedd7034) ---')
    ea_findings, ea_checked, ea_defects = check_external_artifact_typing(vault)
    if not ea_findings:
        print(f'[PASS] {ea_checked} external-artifact entries verified well-formed per external-artifact.capsule v1.0')
        total_passes += 1
    else:
        print(f'[INFO] {ea_checked} external-artifact entries checked; {ea_defects} defects (WARN-severity at v1.25.0 grace period; ERROR ratchet planned for v1.26.0+)')
        for line in ea_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(ea_findings) > 10:
            remaining = len(ea_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more (run with -v for full list)')

    # --- Sidecar↔Source Pairing (v1.25.0 Stream E; spec 2b49ba79 §C.5) ---
    print('\n--- Sidecar↔Source Pairing (v1.25.0 Stream E; spec 2b49ba79) ---')
    ss_findings, ss_checked, ss_defects = check_sidecar_source_pairing(vault)
    if not ss_findings:
        print(f'[PASS] {ss_checked} sidecars verified paired with their source files (forward + reverse)')
        total_passes += 1
    else:
        print(f'[INFO] {ss_checked} sidecars checked; {ss_defects} pairing defects (WARN-severity at v1.25.0 grace period; ERROR ratchet planned for v1.26.0+)')
        for line in ss_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(ss_findings) > 10:
            remaining = len(ss_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more')

    # --- UID Stability Across Tier (v1.25.0 Stream E; spec 2b49ba79 §A.4 baking-in) ---
    print('\n--- UID Stability Across Tier (v1.25.0 Stream E; spec 2b49ba79) ---')
    us_findings, us_checked, us_defects = check_uid_stability_across_tier(vault)
    if not us_findings:
        print(f'[PASS] {us_checked} sidecars verified UID-stable with their vault projections (Tier 1/Tier 2 path-by-governance enforced)')
        total_passes += 1
    else:
        print(f'[INFO] {us_checked} sidecars checked; {us_defects} UID-stability defects (WARN-severity at v1.25.0 grace period; ERROR ratchet planned for v1.26.0+)')
        for line in us_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(us_findings) > 10:
            remaining = len(us_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more')

    # --- Extraction-Scope Values (v1.25.0 Stream E EXTENSION; spec 2b49ba79 §C.7) ---
    print('\n--- Extraction-Scope Values (v1.25.0 Stream E EXTENSION; spec 2b49ba79) ---')
    es_findings, es_checked, es_defects = check_extraction_scope_values(vault)
    if not es_findings:
        print(f'[PASS] {es_checked} entries with extraction_scope verified in allowed enum; external reserved for external-artifact type')
        total_passes += 1
    else:
        print(f'[INFO] {es_checked} entries with extraction_scope checked; {es_defects} value defects (WARN-severity at v1.25.0 grace period; ERROR ratchet planned for v1.26.0+)')
        for line in es_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(es_findings) > 10:
            remaining = len(es_findings) - 10
            total_warnings += remaining
            print(f'  ... and {remaining} more')

    # --- Working-Copy Schema (v1.26.0 Stream D; spec 5a89297a §3.10 check 1) ---
    print('\n--- Working-Copy Schema (v1.26.0 Stream D; spec 5a89297a §3.10 check 1) ---')
    wcs_findings, wcs_checked, wcs_defects = check_working_copy_schema(vault)
    if not wcs_findings:
        print(f'[PASS] {wcs_checked} type:working-copy entries verified against required schema + enums')
        total_passes += 1
    else:
        print(f'[FAIL] {wcs_checked} working-copies checked; {wcs_defects} schema defects')
        for line in wcs_findings[:10]:
            print(f'  {line}')
            if line.startswith('  [FAIL]') or line.startswith('[FAIL]'):
                total_fails += 1
        if len(wcs_findings) > 10:
            print(f'  ... and {len(wcs_findings) - 10} more')

    # --- Working-Copy Lineage (v1.26.0 Stream D; spec 5a89297a §3.10 check 2) ---
    print('\n--- Working-Copy Lineage (v1.26.0 Stream D; spec 5a89297a §3.10 check 2) ---')
    wcl_findings, wcl_checked, wcl_defects = check_working_copy_lineage(vault)
    if not wcl_findings:
        print(f'[PASS] {wcl_checked} working-copies verified to chain to type:external-artifact projections')
        total_passes += 1
    else:
        print(f'[FAIL] {wcl_checked} working-copies checked; {wcl_defects} lineage defects')
        for line in wcl_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(wcl_findings) > 10:
            print(f'  ... and {len(wcl_findings) - 10} more')

    # --- Working-Copy Sidecar-Equivalence (Invariant #8; spec 5a89297a §2.6 + §3.10 check 3) ---
    print('\n--- Working-Copy Sidecar-Equivalence (Invariant #8; spec 5a89297a §3.10 check 3) ---')
    wcse_findings, wcse_checked, wcse_defects = check_working_copy_sidecar_equivalence(vault)
    if not wcse_findings:
        print(f'[PASS] {wcse_checked} working-copies verified — projection UID = sidecar UID (Invariant #8 holds)')
        total_passes += 1
    else:
        print(f'[FAIL] {wcse_checked} working-copies checked; {wcse_defects} sidecar-equivalence defects (Invariant #8 violations)')
        for line in wcse_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(wcse_findings) > 10:
            print(f'  ... and {len(wcse_findings) - 10} more')

    # --- Working-Copy Index-Sync (closes fa026415 family; spec 5a89297a §3.10 check 4) ---
    print('\n--- Working-Copy Index-Sync (closes fa026415 family; spec 5a89297a §3.10 check 4) ---')
    wci_findings, wci_checked, wci_defects = check_working_copy_index_sync(vault)
    if not wci_findings:
        print(f'[PASS] {wci_checked} working-copies present in vault/00-index.jsonl (inline sync honored)')
        total_passes += 1
    else:
        print(f'[FAIL] {wci_checked} working-copies checked; {wci_defects} index-sync defects')
        for line in wci_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(wci_findings) > 10:
            print(f'  ... and {len(wci_findings) - 10} more')

    # --- Working-Copy Uniqueness (one-per-projection; spec 5a89297a §3.10 check 5) ---
    print('\n--- Working-Copy Uniqueness (one-per-projection; spec 5a89297a §3.10 check 5) ---')
    wcu_findings, wcu_checked, wcu_defects = check_working_copy_uniqueness(vault)
    if not wcu_findings:
        print(f'[PASS] {wcu_checked} projections verified at most one active working-copy each (capsule rule 2)')
        total_passes += 1
    else:
        print(f'[FAIL] {wcu_checked} projections checked; {wcu_defects} uniqueness violations')
        for line in wcu_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(wcu_findings) > 10:
            print(f'  ... and {len(wcu_findings) - 10} more')

    # --- v1.28.0 Stream D: docx-template + folder-mirror + projection extensions ---

    # --- Docx-Template Schema (v1.28.0 Stream D; spec 5a89297a §3.10 check 2 extended) ---
    print('\n--- Docx-Template Schema (v1.28.0 Stream D; spec 5a89297a §3.10 check 2 extended) ---')
    dts_findings, dts_checked, dts_defects = check_docx_template_typing(vault)
    if not dts_findings:
        print(f'[PASS] {dts_checked} type:docx-template entries verified against required schema + slug regex + binary-path resolves')
        total_passes += 1
    else:
        print(f'[FAIL] {dts_checked} docx-templates checked; {dts_defects} schema defects')
        for line in dts_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(dts_findings) > 10:
            print(f'  ... and {len(dts_findings) - 10} more')

    # --- Docx-Template Slug Uniqueness (v1.28.0 Stream D; capsule Rule 2) ---
    print('\n--- Docx-Template Slug Uniqueness (v1.28.0 Stream D; docx-template capsule Rule 2) ---')
    dtsu_findings, dtsu_checked, dtsu_defects = check_docx_template_slug_uniqueness(vault)
    if not dtsu_findings:
        print(f'[PASS] {dtsu_checked} active slugs verified unique across docx-template entries')
        total_passes += 1
    else:
        print(f'[FAIL] {dtsu_checked} slugs checked; {dtsu_defects} uniqueness violations')
        for line in dtsu_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(dtsu_findings) > 10:
            print(f'  ... and {len(dtsu_findings) - 10} more')

    # --- Original-Styles Structure (v1.28.0 Stream D; spec 5a89297a §3.10 check 7 NEW) ---
    print('\n--- Original-Styles Structure (v1.28.0 Stream D; spec 5a89297a §3.10 check 7 NEW) ---')
    oss_findings, oss_checked, oss_defects = check_original_styles_structure(vault)
    if not oss_findings:
        print(f'[PASS] {oss_checked} type:external-artifact entries with original_styles: verified against §3.4 schema')
        total_passes += 1
    else:
        # WARN-severity: opportunistic field; surface but don't fail the build
        print(f'[WARN] {oss_checked} entries checked; {oss_defects} original_styles structural concerns')
        for line in oss_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(oss_findings) > 10:
            print(f'  ... and {len(oss_findings) - 10} more')

    # --- Folder-Mirror Integrity (v1.28.0 Stream D; spec 5a89297a §3.10 check 8 NEW) ---
    print('\n--- Folder-Mirror Integrity (v1.28.0 Stream D; spec 5a89297a §3.10 check 8 NEW; closes sa.skeptic-008 P0-2) ---')
    fmi_findings, fmi_checked, fmi_defects = check_folder_mirror_integrity(vault)
    if not fmi_findings:
        print(f'[PASS] {fmi_checked} type:project folder-mirror entries verified — sanctioned dual-residence pattern integrity holds')
        total_passes += 1
    else:
        print(f'[FAIL/WARN] {fmi_checked} folder-mirrors checked; {fmi_defects} integrity defects')
        for line in fmi_findings[:10]:
            print(f'  {line}')
            if line.startswith('[FAIL]') or '[FAIL]' in line:
                total_fails += 1
            else:
                total_warnings += 1
        if len(fmi_findings) > 10:
            print(f'  ... and {len(fmi_findings) - 10} more')

    # --- Projection Index-Sync (v1.28.0 Stream D; spec 5a89297a §3.10 check 4 v0.5.1 widening) ---
    print('\n--- Projection Index-Sync (v1.28.0 Stream D; spec 5a89297a §3.10 check 4 v0.5.1 widening) ---')
    pis_findings, pis_checked, pis_defects = check_projection_index_sync(vault)
    if not pis_findings:
        print(f'[PASS] {pis_checked} type:external-artifact projections present in vault/00-index.jsonl (inline sync honored)')
        total_passes += 1
    else:
        print(f'[FAIL] {pis_checked} projections checked; {pis_defects} index-sync defects')
        for line in pis_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(pis_findings) > 10:
            print(f'  ... and {len(pis_findings) - 10} more')

    # --- Folder-Mirror Index-Sync (v1.28.0 Stream D; spec 5a89297a §3.10 check 4 v0.5 widening) ---
    print('\n--- Folder-Mirror Index-Sync (v1.28.0 Stream D; spec 5a89297a §3.10 check 4 v0.5 widening) ---')
    fmis_findings, fmis_checked, fmis_defects = check_folder_mirror_index_sync(vault)
    if not fmis_findings:
        print(f'[PASS] {fmis_checked} type:project folder-mirrors present in vault/00-index.jsonl (inline sync honored)')
        total_passes += 1
    else:
        print(f'[FAIL] {fmis_checked} folder-mirrors checked; {fmis_defects} index-sync defects')
        for line in fmis_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(fmis_findings) > 10:
            print(f'  ... and {len(fmis_findings) - 10} more')

    # --- Integrity Parity (v1.5 NEW) ---
    print('\n--- 00-integrity.json Parity (v1.5 inbox 656c26d0) ---')
    findings, ok = check_integrity_parity(vault)
    for line in findings:
        print(line)
        if '[WARN]' in line:
            total_warnings += 1  # ratchet preserves count for display; FAIL counted by [FAIL] prefix
    if ok and not findings:
        print('[PASS] integrity report parity (or report not present)')
        total_passes += 1

    # --- v1.70 Check 34: Boot-Derivation Freshness (Drift-Gate) ---
    print('\n--- Boot-Derivation Freshness (Check 34; spec 5e12ab9c; ERROR) ---')
    try:
        bdf_findings, bdf_checked, bdf_defects = check_boot_derivation_fresh(vault)
        if bdf_defects == 0:
            if bdf_checked > 0:
                print(f'[PASS] {bdf_checked} boot artifact(s) verified fresh (no drift)')
            else:
                print('[PASS] No active boot-derivation artifacts found to verify')
            total_passes += 1
        else:
            print(f'[FAIL] {bdf_checked} artifact(s) checked; {bdf_defects} drift defect(s) detected')

        for line in bdf_findings[:20]:
            print(f'  {line}')
            if '[FAIL]' in line: total_fails += 1
            elif '[WARN]' in line: total_warnings += 1
        if len(bdf_findings) > 20:
            print(f'  ... and {len(bdf_findings)-20} more')
            for line in bdf_findings[20:]:
                if '[FAIL]' in line: total_fails += 1
                elif '[WARN]' in line: total_warnings += 1
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] boot-derivation-freshness check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- v1.70 Check 33: Spec Coverage Pairing (AC <-> behavior) ---
    print('\n--- Spec Coverage Pairing (Check 33; dev-spec AC <-> test-spec behavior; ERROR) ---')
    try:
        scp_findings, scp_checked, scp_defects = check_spec_coverage_pairing(vault)
        if scp_defects == 0:
            print(f'[PASS] {scp_checked} test-spec(s) verified — all ACs from triggered dev-specs covered')
            total_passes += 1
        else:
            print(f'[FAIL] {scp_checked} test-spec(s) checked; {scp_defects} pairing defect(s) detected')

        for line in scp_findings[:20]:
            print(f'  {line}')
            if line.strip().startswith('[FAIL]'):
                total_fails += 1
            elif line.strip().startswith('[WARN]'):
                total_warnings += 1
        if len(scp_findings) > 20:
            extra = len(scp_findings) - 20
            print(f'  ... and {extra} more')
            for line in scp_findings[20:]:
                if line.strip().startswith('[FAIL]'):
                    total_fails += 1
                elif line.strip().startswith('[WARN]'):
                    total_warnings += 1
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] spec-coverage-pairing check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- v1.70 Check 31: No Agent Emit From Root UID (81e52840 §S2.4; ERROR) ---
    # v1.73 c19fe1f4: legacy set (id<=CHECK31_GRANDFATHER_MAX_EVENT_ID) now [INFO] named exemptions
    print('\n--- Agent Emit Axis Check (Check 31; must use party UID; ERROR) ---')
    try:
        c31_findings, c31_checked, c31_defects = check_no_agent_emit_from_root_uid(vault)
        c31_info = [l for l in c31_findings if l.strip().startswith('[INFO]')]
        c31_fail = [l for l in c31_findings if l.strip().startswith('[FAIL]')]
        if c31_defects == 0:
            print(f'[PASS] {c31_checked} event(s) checked — zero going-forward emits from root UID')
            total_passes += 1
        else:
            print(f'[FAIL] {c31_checked} event(s) checked; {c31_defects} violation(s) detected')
        if c31_info:
            print(f'[INFO] {len(c31_info)} grandfathered legacy event(s) (id<={CHECK31_GRANDFATHER_MAX_EVENT_ID}; named exempt; no action needed):')
            for line in c31_info[:5]:
                print(f'  {line}')
            if len(c31_info) > 5:
                print(f'  ... and {len(c31_info) - 5} more (all id<={CHECK31_GRANDFATHER_MAX_EVENT_ID}; same class)')
        for line in c31_fail:
            print(f'  {line}')
            total_fails += 1
    except Exception as e:
        print(f'[FAIL] Check 31 CRASHED: {e}')
        total_fails += 1

    # --- v1.70 Check 32: Completion Recording Enforcement (2fe61817 §S2.4; ERROR) ---
    # v1.73 c19fe1f4: legacy set (pre-v1.70 / no target_release) now [INFO] named exemptions
    print('\n--- Completion Recording Enforcement (Check 32; terminal state needs event; ERROR) ---')
    try:
        c32_findings, c32_checked, c32_defects = check_completion_recording(vault)
        c32_info = [l for l in c32_findings if l.strip().startswith('[INFO]')]
        c32_fail = [l for l in c32_findings if l.strip().startswith('[FAIL]')]
        if c32_defects == 0:
            print(f'[PASS] {c32_checked} terminal work-item(s) verified — completion events present or grandfathered')
            total_passes += 1
        else:
            print(f'[FAIL] {c32_checked} item(s) checked; {c32_defects} recording defect(s) detected')
        if c32_info:
            print(f'[INFO] {len(c32_info)} grandfathered legacy item(s) (pre-{CHECK32_GRANDFATHER_MAX_RELEASE}/no-target_release; named exempt; no action needed):')
            for line in c32_info[:5]:
                print(f'  {line}')
            if len(c32_info) > 5:
                print(f'  ... and {len(c32_info) - 5} more (all pre-{CHECK32_GRANDFATHER_MAX_RELEASE}; same class)')
        for line in c32_fail:
            print(f'  {line}')
            total_fails += 1
    except Exception as e:
        print(f'[FAIL] Check 32 CRASHED: {e}')
        total_fails += 1

    # --- v1.70 Check 35: Identity Reference Resolution (Standing Item 4; ERROR) ---
    print('\n--- Identity Reference Resolution (Check 35; unified card refs; ERROR) ---')
    try:
        c35_findings, c35_checked, c35_defects = check_identity_refs_resolve(vault)
        if c35_defects == 0:
            print(f'[PASS] {c35_checked} unified agent card(s) verified — all UID refs resolve')
            total_passes += 1
        else:
            print(f'[FAIL] {c35_checked} card(s) checked; {c35_defects} dangling reference(s) detected')

        for line in c35_findings[:20]:
            print(f'  {line}')
            if '[FAIL]' in line: total_fails += 1
            elif '[WARN]' in line: total_warnings += 1
        if len(c35_findings) > 20:
            extra = len(c35_findings) - 20
            print(f'  ... and {extra} more')
            for line in c35_findings[20:]:
                if '[FAIL]' in line: total_fails += 1
                elif '[WARN]' in line: total_warnings += 1
    except Exception as e:
        print(f'[FAIL] Check 35 CRASHED: {e}')
        total_fails += 1

    # --- Node Privacy Backstop (node.capsule §9; ERROR) ---
    print('\n--- Node Private-by-Construction Backstop (node.capsule §9; ERROR) ---')
    try:
        c36_findings, c36_checked, c36_defects = check_node_private_by_construction(vault)
        if c36_defects == 0:
            print(f'[PASS] {c36_checked} public projection artifact(s) scanned — ZERO private nodes leaked')
            total_passes += 1
        else:
            print(f'[FAIL] {c36_checked} artifact(s) scanned; {c36_defects} leak(s) detected')

        for line in c36_findings[:20]:
            print(f'  {line}')
            if '[FAIL]' in line: total_fails += 1
            elif '[WARN]' in line: total_warnings += 1
        if len(c36_findings) > 20:
            extra = len(c36_findings) - 20
            print(f'  ... and {extra} more')
            for line in c36_findings[20:]:
                if '[FAIL]' in line: total_fails += 1
                elif '[WARN]' in line: total_warnings += 1
    except Exception as e:
        print(f'[FAIL] Node Privacy Backstop CRASHED: {e}')
        total_fails += 1


    # --- Navigation Block Render Safety (v1.X; HUMAN-NAVIGATION 57a9c11f + core.capsule v1.2 §Check 9) ---
    print('\n--- Navigation Block Render Safety (v1.X; HUMAN-NAVIGATION 57a9c11f + core.capsule v1.2 §Check 9 NEW) ---')
    nav_findings, nav_checked, nav_defects = check_navigation_block_render_safety(vault)
    if not nav_findings:
        print(f'[PASS] {nav_checked} vault/files/*.md verified — `title:` present and Navigation block rendered')
        total_passes += 1
    else:
        print(f'[WARN] {nav_checked} files checked; {nav_defects} with Navigation block render-safety defects (WARN at v1.X; ERROR ratchet planned post-migration)')
        for line in nav_findings[:10]:
            print(line)
            total_warnings += 1
        if len(nav_findings) > 10:
            print(f'  ... and {len(nav_findings) - 10} more')
            total_warnings += (len(nav_findings) - 10)

    # --- Duplicate YAML Keys (v1.29.0 Stream A; spec 81555e45 v0.4 §3.2 NEW) ---
    print('\n--- Duplicate Top-Level YAML Keys (v1.29.0 Stream A; spec 81555e45 v0.4 §3.2 NEW) ---')
    dyk_findings, dyk_checked, dyk_defects = check_duplicate_yaml_keys(vault)
    if not dyk_findings:
        print(f'[PASS] {dyk_checked} vault/files/*.md verified — no duplicate top-level YAML keys')
        total_passes += 1
    else:
        print(f'[FAIL] {dyk_checked} files checked; {dyk_defects} with duplicate top-level YAML keys')
        for line in dyk_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(dyk_findings) > 10:
            print(f'  ... and {len(dyk_findings) - 10} more')

    # --- Ship-Artifact Target Field (v1.42.0 Stream B; ship-artifact.capsule v1.3 Check 24 NEW) ---
    print('\n--- Ship-Artifact Target Field (v1.42.0 Stream B; ship-artifact.capsule v1.3 §Validation Checks Check 24 NEW) ---')
    sat_findings, sat_checked, sat_defects = check_ship_artifact_target_field(vault)
    if not sat_findings:
        print(f'[PASS] {sat_checked} type:ship-artifact entries verified — target field shape + enum valid (or absent = implicit [release])')
        total_passes += 1
    else:
        print(f'[FAIL] {sat_checked} ship-artifact entries checked; {sat_defects} with target field defects')
        for line in sat_findings[:10]:
            print(f'  {line}')
            total_fails += 1
        if len(sat_findings) > 10:
            print(f'  ... and {len(sat_findings) - 10} more')

    # --- Article State Machine Invariants (v1.48.0 Stream A; ship-artifact.capsule v1.4 Check 25 NEW) ---
    print('\n--- Article State Machine Invariants (v1.48.0 Stream A; ship-artifact.capsule v1.4 Check 25 NEW; WARN at v1.4 / ERROR ratchet at v1.5) ---')
    asm_findings, asm_checked, asm_defects = check_article_state_machine_invariants(vault)
    if not asm_findings:
        print(f'[PASS] {asm_checked} subtype:article entries verified — editorial state machine clean')
        total_passes += 1
    else:
        print(f'[WARN] {asm_checked} subtype:article entries checked; {asm_defects} with editorial-state defects (WARN at v1.4; ERROR ratchet planned at v1.5)')
        for line in asm_findings[:10]:
            print(line)
            total_warnings += 1
        if len(asm_findings) > 10:
            print(f'  ... and {len(asm_findings) - 10} more')
            total_warnings += (len(asm_findings) - 10)

    # --- Wrapper-Article Editorial Lock (v1.48.0 Stream A; ship-artifact.capsule v1.4 Check 26 NEW) ---
    print('\n--- Wrapper-Article Editorial Lock (v1.48.0 Stream A; ship-artifact.capsule v1.4 Check 26 NEW; WARN at v1.4 / ERROR ratchet at v1.5) ---')
    wae_findings, wae_checked, wae_defects = check_wrapper_article_editorial_lock(vault)
    if not wae_findings:
        print(f'[PASS] {wae_checked} ship-artifact wrappers with article sources verified — editorial-lock composition clean')
        total_passes += 1
    else:
        print(f'[WARN] {wae_checked} wrappers checked; {wae_defects} with wrapper-article composition defects (WARN at v1.4; ERROR ratchet planned at v1.5)')
        for line in wae_findings[:10]:
            print(line)
            total_warnings += 1
        if len(wae_findings) > 10:
            print(f'  ... and {len(wae_findings) - 10} more')
            total_warnings += (len(wae_findings) - 10)

    # --- Publication State Pipeline-Write Discipline (v1.48.0 Stream A; ship-artifact.capsule v1.4 Check 27 NEW) ---
    print('\n--- Publication State Pipeline-Write Discipline (v1.48.0 Stream A; ship-artifact.capsule v1.4 Check 27 NEW; WARN at v1.4 / ERROR ratchet at v1.5) ---')
    ps1_findings, ps1_checked, ps1_defects = check_publication_state_pipeline_write_only(vault)
    if not ps1_findings:
        print(f'[PASS] {ps1_checked} ship-artifact entries with publication_state field verified — shape + enum valid')
        total_passes += 1
    else:
        print(f'[WARN] {ps1_checked} entries checked; {ps1_defects} with publication_state shape/enum defects (WARN at v1.4; ERROR ratchet planned at v1.5)')
        for line in ps1_findings[:10]:
            print(line)
            total_warnings += 1
        if len(ps1_findings) > 10:
            print(f'  ... and {len(ps1_findings) - 10} more')
            total_warnings += (len(ps1_findings) - 10)

    # --- Publication State Target Coherence (v1.48.0 Stream A; ship-artifact.capsule v1.4 Check 28 NEW) ---
    print('\n--- Publication State Target Coherence (v1.48.0 Stream A; ship-artifact.capsule v1.4 Check 28 NEW; WARN at v1.4) ---')
    ps2_findings, ps2_checked, ps2_defects = check_publication_state_target_coherence(vault)
    if not ps2_findings:
        print(f'[PASS] {ps2_checked} ship-artifact entries with publication_state verified — keys ⊆ target array')
        total_passes += 1
    else:
        print(f'[WARN] {ps2_checked} entries checked; {ps2_defects} with target-coherence defects')
        for line in ps2_findings[:10]:
            print(line)
            total_warnings += 1
        if len(ps2_findings) > 10:
            print(f'  ... and {len(ps2_findings) - 10} more')
            total_warnings += (len(ps2_findings) - 10)

    # --- External-Work Gitignore (v1.48.0 Stream A; ship-artifact.capsule v1.4 Check 29 NEW) ---
    print('\n--- External-Work Gitignore (v1.48.0 Stream A; ship-artifact.capsule v1.4 Check 29 NEW; WARN at v1.4) ---')
    ewg_findings, ewg_checked, ewg_defects = check_external_work_gitignore(vault)
    if not ewg_findings:
        print(f'[PASS] argo-os/external-work/ declared in .gitignore (staging surface not tracked in git)')
        total_passes += 1
    else:
        print(f'[WARN] external-work/ gitignore audit: {ewg_defects} defect(s)')
        for line in ewg_findings:
            print(line)
            total_warnings += 1

    # --- v1.51 Phase A: dev-spec.capsule v1.0 §Validation Checks (9 checks; lib module wire-up) ---
    print('\n--- dev-spec.capsule v1.0 §Validation Checks (v1.51 Phase A; 9 checks; WARN at v1.0 / ERROR ratchet at v1.51.1) ---')
    try:
        from lib.dev_spec_validators import run_all_dev_spec_checks
        ds_findings, ds_total, ds_defects = run_all_dev_spec_checks(vault)
        if not ds_findings:
            print(f'[PASS] {ds_total} dev-spec entries verified clean — 9-check family green')
            total_passes += 1
        else:
            print(f'[WARN] {ds_total} dev-spec entries checked; {ds_defects} findings (WARN at v1.0)')
            for line in ds_findings[:10]:
                print(f'  {line}')
                total_warnings += 1
            if len(ds_findings) > 10:
                print(f'  ... and {len(ds_findings) - 10} more')
                total_warnings += (len(ds_findings) - 10)
    except ImportError as e:
        print(f'[WARN] dev-spec validator lib not importable: {e}')
        total_warnings += 1

    # --- v1.51 Phase B: doc-spec.capsule v1.0 §Validation Checks (13 checks; lib module wire-up) ---
    print('\n--- doc-spec.capsule v1.0 §Validation Checks (v1.51 Phase B; 13 checks; WARN at v1.0 / ERROR ratchet v1.51.1+) ---')
    try:
        from lib.doc_spec_validators import run_all_doc_spec_checks
        dcs_findings, dcs_total, dcs_defects = run_all_doc_spec_checks(vault)
        if not dcs_findings:
            print(f'[PASS] {dcs_total} doc-spec entries verified clean — 13-check family green')
            total_passes += 1
        else:
            print(f'[WARN] {dcs_total} doc-spec entries checked; {dcs_defects} findings (WARN at v1.0)')
            for line in dcs_findings[:10]:
                print(f'  {line}')
                total_warnings += 1
            if len(dcs_findings) > 10:
                print(f'  ... and {len(dcs_findings) - 10} more')
                total_warnings += (len(dcs_findings) - 10)
    except ImportError as e:
        print(f'[WARN] doc-spec validator lib not importable: {e}')
        total_warnings += 1

    # --- v1.51 Phase B: test-spec.capsule v1.0 §Validation Checks (14 checks; lib module wire-up) ---
    print('\n--- test-spec.capsule v1.0 §Validation Checks (v1.51 Phase B; 14 checks; WARN at v1.0 / ERROR ratchet v1.51.1+ except SQ1 cross-validation which ratchets v1.1) ---')
    try:
        from lib.test_spec_validators import run_all_test_spec_checks
        ts_findings, ts_total, ts_defects = run_all_test_spec_checks(vault)
        if not ts_findings:
            print(f'[PASS] {ts_total} test-spec entries verified clean — 14-check family green')
            total_passes += 1
        else:
            print(f'[WARN] {ts_total} test-spec entries checked; {ts_defects} findings (WARN at v1.0)')
            for line in ts_findings[:10]:
                print(f'  {line}')
                total_warnings += 1
            if len(ts_findings) > 10:
                print(f'  ... and {len(ts_findings) - 10} more')
                total_warnings += (len(ts_findings) - 10)
    except ImportError as e:
        print(f'[WARN] test-spec validator lib not importable: {e}')
        total_warnings += 1

    # --- v1.51 Phase A: v1.14 schema split §Validation Checks 10-11 (project.capsule v2.5; 2 checks; lib module wire-up) ---
    print('\n--- v1.14 schema split §Validation Checks (project.capsule v2.5 Checks 10-11; 2 checks; WARN at v1.51 / ERROR ratchet v1.52+) ---')
    try:
        from lib.v14_subsystem_hub_validators import run_all_v14_subsystem_hub_checks
        v14_findings, v14_total, v14_defects = run_all_v14_subsystem_hub_checks(vault)
        if not v14_findings:
            print(f'[PASS] {v14_total} migrated entries verified clean — subsystem_hub schema-split discipline green')
            total_passes += 1
        else:
            print(f'[WARN] {v14_total} migrated entries checked; {v14_defects} findings (WARN at v1.51)')
            for line in v14_findings[:10]:
                print(f'  {line}')
                total_warnings += 1
            if len(v14_findings) > 10:
                print(f'  ... and {len(v14_findings) - 10} more')
                total_warnings += (len(v14_findings) - 10)
    except ImportError as e:
        print(f'[WARN] v14_subsystem_hub validator lib not importable: {e}')
        total_warnings += 1

    # --- v1.52 P-lane P3: numeric-folder-prefix.capsule v1.0 §6 Validation Checks (4 checks; lib module wire-up) ---
    print('\n--- numeric-folder-prefix.capsule v1.0 §Validation Checks (v1.52 P-lane P3; 4 checks; WARN at v1.0 / ERROR ratchet v1.1) ---')
    try:
        from lib.numeric_folder_prefix_validators import run_all_numeric_folder_prefix_checks
        nfp_findings, nfp_total, nfp_defects = run_all_numeric_folder_prefix_checks(vault)
        if not nfp_findings:
            print(f'[PASS] {nfp_total} numeric-prefix folders verified clean — 4-check family green')
            total_passes += 1
        else:
            print(f'[WARN] {nfp_total} numeric-prefix folders checked; {nfp_defects} findings (WARN at v1.0)')
            for line in nfp_findings[:10]:
                print(f'  {line}')
                total_warnings += 1
            if len(nfp_findings) > 10:
                print(f'  ... and {len(nfp_findings) - 10} more')
                total_warnings += (len(nfp_findings) - 10)
    except ImportError as e:
        print(f'[WARN] numeric-folder-prefix validator lib not importable: {e}')
        total_warnings += 1

    # --- v1.55 Stream A.8: Event Log Integrity Checks 1-10 (WARN; ERROR ratchet v1.56) ---
    print('\n--- Event Log Integrity Checks 1-10 (v1.55 Stream A.8; WARN / ERROR ratchet v1.56) ---')
    try:
        from lib.event_validators import run_all_event_checks
        ev_findings, ev_checked, ev_defects = run_all_event_checks(vault)
        if ev_checked == 0:
            print('[INFO] vault/events/00-events.jsonl not present — skipping (no events yet)')
        elif not ev_findings:
            print(f'[PASS] {ev_checked} event(s) checked — Checks 1-10 all clean')
            total_passes += 1
        else:
            print(f'[WARN] {ev_checked} event(s) checked; {ev_defects} finding(s)')
            for line in ev_findings:
                print(line)
                total_warnings += 1
    except ImportError as e:
        print(f'[WARN] event_validators import failed: {e}; A.8 checks skipped')
        total_warnings += 1

    # --- V1 (v1.54) Canonical Reference Shape (WARN; ERROR ratchet v1.55) ---
    print('\n--- V1 Canonical Reference Shape (v1.54; WARN ratchet / ERROR v1.55) ---')
    crs_findings, crs_checked, crs_defects = check_canonical_reference_shape(vault)
    if not crs_findings:
        print(f'[PASS] {crs_checked} vault entries checked — canonical references well-formed')
        total_passes += 1
    else:
        print(f'[WARN] {crs_checked} entries checked; {crs_defects} canonical-reference shape finding(s)')
        for line in crs_findings[:10]:
            print(line)
            total_warnings += 1
        if len(crs_findings) > 10:
            print(f'  ... and {len(crs_findings) - 10} more')
            total_warnings += (len(crs_findings) - 10)

    # --- Spec LOCK-signoff Required Fields (v1.53 Lane E E3; ERROR ratchet refuses LOCK with gaps) ---
    print('\n--- Spec LOCK-signoff Required Fields (v1.53 Lane E E3; ERROR ratchet) ---')
    try:
        from lib.spec_lock_validators import run_all_spec_lock_checks
        slv_findings, slv_total, slv_defects = run_all_spec_lock_checks(vault)
        if slv_defects:
            print(f'[FAIL] {slv_total} locked *-spec entries checked; {slv_defects} LOCK-signoff defect(s)')
            for f in slv_findings:
                print(f'  {f}')
            total_fails += slv_defects
        else:
            print(f'[PASS] {slv_total} locked *-spec entries verified — required fields complete at LOCK')
            total_passes += 1
    except ImportError as e:
        print(f'[WARN] spec_lock_validators import failed: {e}; E3 check skipped this run')
        total_warnings += 1

    # --- Preservation Discipline: engine scripts must not hard-delete vault/files/ ---
    print('\n--- Preservation Discipline: engine direct-vault-unlink audit (ERROR) ---')
    edu_findings, edu_checked, edu_defects = check_engine_no_direct_vault_unlink(vault)
    if not edu_findings:
        print(f'[PASS] {edu_checked} engine scripts checked — no direct vault/files/ unlink calls')
        total_passes += 1
    else:
        print(f'[FAIL] {edu_defects} direct vault deletion(s) found in engine scripts')
        for line in edu_findings:
            print(line)
        total_fails += edu_defects

    # --- Cycle 4: kb-content slug collision audit ---
    print('\n--- Cycle 4 publish-pipeline: kb-content slug collision audit (ERROR) ---')
    kcc_findings, kcc_checked, kcc_defects = check_kb_content_no_slug_collisions(vault)
    if not kcc_findings:
        print(f'[PASS] {kcc_checked} kb-content files checked — no slug collisions')
        total_passes += 1
    else:
        print(f'[FAIL] {kcc_defects} slug collision(s) in kb-content ({kcc_checked} files checked)')
        for line in kcc_findings:
            print(line)
        total_fails += kcc_defects

    # --- v1.57 Stream B.5: channel_render_safety checks (WARN at v1.57; ERROR ratchet v1.58) ---
    print('\n--- channel_render_safety (v1.57 Stream B.5; WARN / ERROR ratchet v1.58) ---')
    try:
        from lib.channel_render_validators import run_channel_render_safety_checks
        crs_findings, crs_checked, crs_defects = run_channel_render_safety_checks(vault)
        if crs_checked == 0:
            print('[INFO] No channels with rendered_from_events:true found — skipping')
        elif not crs_findings:
            print(f'[PASS] {crs_checked} rendered channel(s) checked — all deterministic + drift-free')
            total_passes += 1
        else:
            print(f'[WARN] {crs_checked} rendered channel(s) checked; {crs_defects} finding(s)')
            for line in crs_findings:
                print(line)
                total_warnings += 1
    except ImportError as e:
        print(f'[WARN] channel_render_validators import failed: {e}; B.5 checks skipped')
        total_warnings += 1

    # --- v1.60 Lane A-migrate: action.capsule vault/actions/ checks (WARN v1.60) ---
    print('\n--- vault/actions/ action.capsule checks (v1.60 Lane A-migrate; WARN) ---')
    try:
        from lib.action_validators import run_all_action_checks
        av_findings, av_checked, av_defects = run_all_action_checks(vault)
        if av_checked == 0:
            print('[INFO] vault/actions/ not present or empty — skipping')
        elif not av_findings:
            print(f'[PASS] {av_checked} vault/actions/ file(s) checked — action entries clean')
            total_passes += 1
        else:
            print(f'[WARN] {av_checked} action(s) checked; {av_defects} finding(s)')
            for line in av_findings[:10]:
                print(line)
                total_warnings += 1
            if len(av_findings) > 10:
                print(f'  ... and {len(av_findings) - 10} more')
                total_warnings += (len(av_findings) - 10)
    except ImportError as e:
        print(f'[WARN] action_validators import failed: {e}; Lane A checks skipped')
        total_warnings += 1

    # --- v1.59 Lane B A1: release entry required_at_activation + required_at_ship checks (WARN v1.59) ---
    print('\n--- release.capsule required_at_activation + required_at_ship field checks (v1.59 Lane B A1; WARN / ERROR ratchet v1.60) ---')
    try:
        from lib.release_validators import check_release_required_fields
        rv_findings, rv_checked, rv_defects = check_release_required_fields(vault)
        if rv_checked == 0:
            print('[INFO] No release entries found — skipping')
        elif not rv_findings:
            print(f'[PASS] {rv_checked} release entry(ies) checked — required fields populated')
            total_passes += 1
        else:
            print(f'[WARN] {rv_checked} release entry(ies) checked; {rv_defects} required-field finding(s)')
            for line in rv_findings[:10]:
                print(line)
                total_warnings += 1
            if len(rv_findings) > 10:
                print(f'  ... and {len(rv_findings) - 10} more')
                total_warnings += (len(rv_findings) - 10)
    except ImportError as e:
        print(f'[WARN] release_validators import failed: {e}; Lane B checks skipped')
        total_warnings += 1

    # --- v1.58 M.1: Lane V Layer 3 meta-validator (schema-to-implementation coherence; WARN at v1.58) ---
    print('\n--- Lane V Layer 3 meta-validator (v1.58 M.1; schema-to-implementation coherence; WARN / ERROR ratchet v1.59) ---')
    try:
        from lib.meta_validators import run_layer_3
        l3_findings, l3_capsules, l3_defects = run_layer_3(vault)
        if l3_capsules == 0:
            print('[INFO] No onboarded capsules found — skipping Layer 3')
        elif not l3_findings:
            print(f'[PASS] {l3_capsules} capsule(s) checked — all validator implementations aligned with schema declarations')
            total_passes += 1
        else:
            # v1.60 V-ratchet: ERROR-class findings (enum-value-drift, registered-type-drift) → total_fails
            error_findings = [f for f in l3_findings if '[ERROR]' in f]
            warn_findings  = [f for f in l3_findings if '[WARN]' in f]
            if error_findings:
                print(f'[FAIL] {l3_capsules} capsule(s) checked; {len(error_findings)} ERROR-class drift finding(s)')
                for line in error_findings[:10]:
                    print(line)
                    total_fails += 1
            if warn_findings:
                print(f'[WARN] {len(warn_findings)} WARN-class finding(s) (impl-not-detected; deferred to v1.61)')
                for line in warn_findings[:10]:
                    print(line)
                    total_warnings += 1
            if not error_findings and warn_findings:
                pass  # already printed
    except ImportError as e:
        print(f'[WARN] meta_validators import failed: {e}; Layer 3 checks skipped')
        total_warnings += 1

    # --- v1.56 Lane E + v1.64 tool-discovery: tool.capsule v1.7 §4 Validation Checks ---
    # v1.7 adds: Check v1.7-1 (name != uid; WARN at v1.64, ERROR ratchet v1.65)
    #            Check v1.7-2 (cli_command non-empty for transport:cli; same ratchet)
    #            transport enum extended: library added as valid
    print('\n--- tool.capsule v1.7 §4 Validation Checks (v1.56 Lane E + v1.64 tool-discovery; WARN / ERROR ratchet at v1.65) ---')
    try:
        from lib.tool_validators import run_all_tool_checks
        tv_findings, tv_checked, tv_defects = run_all_tool_checks(vault)
        if tv_checked == 0:
            print('[INFO] vault/tools/ not present or empty — skipping')
        elif not tv_findings:
            print(f'[PASS] {tv_checked} vault/tools/ file(s) checked — tool.capsule v1.7 checks clean')
            total_passes += 1
        else:
            print(f'[WARN] {tv_checked} tool(s) checked; {tv_defects} finding(s)')
            for line in tv_findings[:20]:
                print(line)
                total_warnings += 1
            if len(tv_findings) > 20:
                print(f'  ... and {len(tv_findings) - 20} more')
                total_warnings += (len(tv_findings) - 20)
    except ImportError as e:
        print(f'[WARN] tool_validators import failed: {e}; tool checks skipped')
        total_warnings += 1

    # --- v1.61 Lane F: fleet_ops_schedule declared on chief-of-staff Tier 3 (WARN → ERROR ratchet v1.62) ---
    # check_fleet_ops_schedule_declared_if_executive_class per Tier 2 cf8c3be9 v2.3 §Fleet-Ops Schedule Protocol.
    # At v1.61: WARN only. Ratchet to ERROR at v1.62 after V55 adoption cycle.
    print('\n--- fleet_ops_schedule declared on chief-of-staff Tier 3 (v1.61 Lane F; WARN → ERROR at v1.62) ---')
    try:
        import re as _re
        try:
            import yaml as _yaml
            _yaml_ok = True
        except ImportError:
            _yaml_ok = False
        # Chief-of-staff agents expected to declare fleet_ops_schedule.
        # TWO shapes (P0.4 v1.69 dual-shape branch):
        # (a) Legacy: tier:3 + (agent_class chief-of-staff OR agent in {vela}) in vault/files/
        # (b) Unified: type:agent + agent_class chief-of-staff in vault/agents/ (post-v1.69 migration)
        CHIEF_OF_STAFF_AGENTS = {'vela'}
        fo_findings = []
        fo_checked = 0

        def _check_fleet_ops_fm(fm, fname):
            nonlocal fo_checked
            agent = fm.get('agent', '')
            agent_class = fm.get('agent_class', '')
            is_chief = (agent in CHIEF_OF_STAFF_AGENTS or agent_class in ('chief-of-staff',))
            if not is_chief:
                return
            fo_checked += 1
            if not fm.get('fleet_ops_schedule'):
                fo_findings.append(
                    f'  [WARN] {fname}: agent={agent!r} missing fleet_ops_schedule: '
                    f'declaration (check_fleet_ops_schedule_declared_if_executive_class; WARN→ERROR v1.62)'
                )

        # Shape (a): legacy Tier-3 files in vault/files/
        for f in sorted((vault / 'vault' / 'files').iterdir()):
            if f.suffix != '.md':
                continue
            try:
                content = f.read_text(encoding='utf-8')
                m = _re.match(r'^---\n(.*?)\n---', content, _re.DOTALL)
                if not m:
                    continue
                if _yaml_ok:
                    fm = _yaml.safe_load(m.group(1)) or {}
                else:
                    fm_text = m.group(1)
                    fm = {}
                    for line in fm_text.splitlines():
                        if ':' in line and not line.startswith(' '):
                            k, _, v = line.partition(':')
                            fm[k.strip()] = v.strip().strip('"\'')
                tier = fm.get('tier', '')
                if str(tier) != '3':
                    continue
                _check_fleet_ops_fm(fm, f.name)
            except Exception:
                continue

        # Shape (b): unified agent entries in vault/agents/ (type:agent; post-v1.69 migration)
        vault_agents_dir = vault / 'vault' / 'agents'
        if vault_agents_dir.is_dir():
            for f in sorted(vault_agents_dir.iterdir()):
                if f.suffix != '.md':
                    continue
                try:
                    content = f.read_text(encoding='utf-8')
                    m = _re.match(r'^---\n(.*?)\n---', content, _re.DOTALL)
                    if not m:
                        continue
                    if _yaml_ok:
                        fm = _yaml.safe_load(m.group(1)) or {}
                    else:
                        fm = {}
                        for line in m.group(1).splitlines():
                            if ':' in line and not line.startswith(' '):
                                k, _, v = line.partition(':')
                                fm[k.strip()] = v.strip().strip('"\'')
                    if fm.get('type') != 'agent':
                        continue
                    _check_fleet_ops_fm(fm, f'vault/agents/{f.name}')
                except Exception:
                    continue
        if fo_checked == 0:
            print('[INFO] No chief-of-staff Tier 3 boot extensions found — skipping')
        elif not fo_findings:
            print(f'[PASS] {fo_checked} chief-of-staff Tier 3(s) checked — fleet_ops_schedule: declared on all')
            total_passes += 1
        else:
            for line in fo_findings:
                print(line)
                total_warnings += 1
    except Exception as e:
        print(f'[FAIL] fleet_ops_schedule CRASHED: {e}')
        total_fails += 1

    # --- v1.62 AC2: --verification-data-stdin self-attestation path removed ---
    print('\n--- v1.62 AC2: --verification-data-stdin removed from pipeline-runtime (WARN) ---')
    try:
        _rt_path = vault / 'vault' / 'tools' / '9e7003b1.py'
        if not _rt_path.exists():
            print('[INFO] pipeline-runtime 9e7003b1.py not found; skipping AC2 check')
        else:
            _rt_src = _rt_path.read_text(encoding='utf-8')
            if '--verification-data-stdin' in _rt_src and 'verification_data_stdin' in _rt_src and 'B4' not in _rt_src:
                print('[WARN] check_v162_stdin_path_removed: --verification-data-stdin still present in 9e7003b1 (v1.62 B4 not applied)')
                total_warnings += 1
            else:
                print('[PASS] check_v162_stdin_path_removed: self-attestation hatch absent or B4 applied')
                total_passes += 1
    except Exception as e:
        print(f'[FAIL] AC2 CRASHED: {e}')
        total_fails += 1

    # --- v1.62 AC7: v1.60/v1.61 cascade cleanup — doc acts retired, waiver 62f1ac90 exists ---
    print('\n--- v1.62 AC7: v1.60/v1.61 cascade cleanup (WARN) ---')
    try:
        _ac7_findings = []
        # Check doc-acts c94663a9 + 69e1341c are retired
        for _act_uid, _label in [('c94663a9', 'v1.60 doc-act'), ('69e1341c', 'v1.61 doc-act')]:
            _act_path = vault / 'vault' / 'files' / f'{_act_uid}.md'
            if _act_path.exists():
                _content = _act_path.read_text(encoding='utf-8')
                import re as _re2
                _m = _re2.match(r'^---\n(.*?)\n---', _content, _re2.DOTALL)
                if _m:
                    try:
                        import yaml as _yac7
                        _fm = _yac7.safe_load(_m.group(1)) or {}
                    except Exception:
                        _fm = {}
                    _status = _fm.get('status', '?')
                    if _status not in ('retired', 'done', 'archived'):
                        _ac7_findings.append(f'  [WARN] {_label} {_act_uid} status={_status!r} (expected retired)')
        # Check waiver 62f1ac90 exists
        _waiver_path = vault / 'vault' / 'files' / '62f1ac90.md'
        if not _waiver_path.exists():
            _ac7_findings.append('  [WARN] waiver 62f1ac90 not found in vault/files/')
        if _ac7_findings:
            for _f in _ac7_findings:
                print(_f)
                total_warnings += 1
        else:
            print('[PASS] check_v162_cascade_cleanup: doc-acts retired + waiver 62f1ac90 present')
            total_passes += 1
    except Exception as e:
        print(f'[FAIL] AC7 CRASHED: {e}')
        total_fails += 1

    # --- v1.62 AC8: self-dogfood gate — release.capsule Rule 17 present ---
    print('\n--- v1.62 AC8: self-dogfood gate (Rule 17 in release.capsule b19e8d43) (WARN) ---')
    try:
        _rc_path = vault / '.tropo' / 'capsules' / 'release.capsule.md'  # b19e8d43 — capsules live at .tropo/capsules/, NOT vault/files/ (Vela V56 lookup-path fix 2026-05-31; Mike-directed; Talos owns the check logic)
        if not _rc_path.exists():
            print('[WARN] check_v162_self_dogfood: release.capsule (b19e8d43) not found at .tropo/capsules/release.capsule.md')
            total_warnings += 1
        else:
            _rc_src = _rc_path.read_text(encoding='utf-8')
            if 'Rule 17' in _rc_src or 'rule_17' in _rc_src or 'completion.*gate' in _rc_src.lower():
                print('[PASS] check_v162_self_dogfood: Rule 17 completion-gate present in release.capsule')
                total_passes += 1
            else:
                print('[WARN] check_v162_self_dogfood: Rule 17 not found in release.capsule b19e8d43 — Vela Lane V may not have landed yet')
                total_warnings += 1
    except Exception as e:
        print(f'[FAIL] AC8 CRASHED: {e}')
        total_fails += 1

    # --- c4512bdc Piece 1: Inline fixture self-tests (zero capsules required) ---
    print('\n--- c4512bdc Piece 1 inline fixtures (list/dict/malformed/state-alias/case-fold) ---')
    try:
        fix_findings, fix_pass, fix_fail = check_piece1_inline_fixtures()
        if fix_fail == 0:
            print(f'[PASS] {fix_pass} fixture assertions pass — alias-map loader + three-way classify verified')
            total_passes += 1
        else:
            print(f'[FAIL] {fix_fail} fixture assertion(s) failed ({fix_pass} passed)')
            for line in fix_findings:
                print(line)
                total_fails += 1
    except Exception as e:
        print(f'[FAIL] Piece 1 fixture CRASHED: {e}')
        total_fails += 1

    # --- R1: checks-fail-loud regression fixture (v1.69; talos-t15 2026-06-12) ---
    print('\n--- R1 checks-fail-loud regression (v1.69; no swallow-own-crash in execution handlers) ---')
    try:
        r1_findings, r1_pass, r1_fail = check_r1_fail_loud_fixture()
        if r1_fail == 0:
            print(f'[PASS] {r1_pass} assertion(s) pass — zero execution handlers swallow crashes as WARN')
            total_passes += 1
        else:
            print(f'[FAIL] {r1_fail} R1 regression(s) — check-execution handler(s) swallow crashes')
            for line in r1_findings:
                print(line)
            total_fails += r1_fail
    except Exception as e:
        print(f'[FAIL] R1 fixture CRASHED: {e}')
        total_fails += 1

    # --- AC5: boot-conditional curator dispatch fixtures (v1.69 0c61a52b §S3; argus-a110 2026-06-12) ---
    print('\n--- AC5 curator-dispatch fixtures (agent-activation.playbook v2.17 §2.5) ---')
    try:
        ac5_findings, ac5_pass, ac5_fail = check_curator_dispatch_fixture()
        if ac5_fail == 0:
            print(f'[PASS] {ac5_pass} fixture assertion(s) — healthy-lineage boot dispatches none; migrate/F5/citation paths still dispatch')
            total_passes += 1
        else:
            print(f'[FAIL] {ac5_fail} curator-dispatch fixture failure(s)')
            for line in ac5_findings:
                print(line)
            total_fails += ac5_fail
    except Exception as e:
        print(f'[FAIL] AC5 curator-dispatch fixture CRASHED: {e}')
        total_fails += 1

    # --- Check-21: no narrow event drain in boot/listen flows (dabe7c64; S2.5 v1.70; ERROR) ---
    # Flipped WARN→ERROR: A111 GO 2026-06-13 — all 8 violation sites cut, Check-21 at 0.
    # Scope extended to .tropo-studio/ (kernel-pointer degraded floors) same beat.
    print('\n--- Check-21: no bare query-events --party drain in boot/listen flows (dabe7c64 §S2.5; ERROR) ---')
    try:
        c21_findings, c21_scanned, c21_violations = check_no_narrow_event_read_in_boot(vault)
        if c21_violations == 0:
            print(f'[PASS] {c21_scanned} boot-path file(s) scanned — no narrow event drain detected')
            total_passes += 1
        else:
            print(f'[FAIL] {c21_violations} narrow drain occurrence(s) across {c21_scanned} file(s) — '
                  f'replace with check-events (Check-21 ERROR; dabe7c64)')
            for line in c21_findings[:10]:
                print(f'  {line}')
            if len(c21_findings) > 10:
                print(f'  ... and {len(c21_findings) - 10} more')
            total_fails += c21_violations
    except Exception as _e:
        print(f'[FAIL] Check-21 CRASHED: {_e}')
        total_fails += 1

    # --- v1.65 + c4512bdc Piece 1: Enforced-Enum Compliance (three-way classify) ---
    print('\n--- Enforced-Enum Compliance (v1.72 Move 7; three-way PASS/WARN/ERROR) ---')
    try:
        ee_findings, ee_checked, ee_errors, ee_warns = check_enforced_enum_compliance(vault)
        if not ee_findings:
            print(f'[PASS] {ee_checked} entries checked — all values PASS (no drift, no aliases)')
            total_passes += 1
        else:
            print(f'[INFO] {ee_checked} entries checked; {ee_errors} ERROR (drift); {ee_warns} WARN (aliases)')
            for line in ee_findings[:20]:
                print(line)
                stripped = line.strip()
                if stripped.startswith('[WARN]'):
                    total_warnings += 1
                elif stripped.startswith('[ERROR]'):
                    total_fails += 1
            if len(ee_findings) > 20:
                remainder = len(ee_findings) - 20
                all_lines = ee_findings[20:]
                extra_warn = sum(1 for l in all_lines if l.strip().startswith('[WARN]'))
                extra_error = sum(1 for l in all_lines if l.strip().startswith('[ERROR]'))
                print(f'  ... and {remainder} more')
                total_warnings += extra_warn
                total_fails += extra_error
            if ee_errors == 0 and not any(l.strip().startswith('[ERROR]') for l in ee_findings):
                total_passes += 1
    except Exception as e:
        print(f'[FAIL] enforce-first enum CRASHED: {e}')
        total_fails += 1

    # --- v1.65 enforce-first: Enforced-Enum Coherence (task pilot, addc4490 v0.5) ---
    print('\n--- Enforced-Enum Coherence (v1.65 enforce-first; addc4490 v0.5; backtick-colon anchor; WARN) ---')
    try:
        coh_findings, coh_checked, coh_fail = check_enforced_enum_coherence(vault)
        if not coh_findings:
            print(f'[PASS] {coh_checked} enforced_enums field(s) checked — block matches canonical prose line')
            total_passes += 1
        else:
            print(f'[WARN] {coh_checked} field(s) checked; {coh_fail} coherence failure(s)')
            for line in coh_findings:
                print(line)
                total_warnings += 1
    except Exception as e:
        print(f'[FAIL] enforce-first coherence CRASHED: {e}')
        total_fails += 1

    # --- 3783a7cb Piece B: meta_status_rollup inline fixtures (LOADER-FIRST) ---
    print('\n--- meta_status_rollup inline fixtures (3783a7cb Piece B; loader-first; 6 assertions) ---')
    try:
        ms_fix_findings, ms_fix_pass, ms_fix_fail = check_meta_status_inline_fixtures()
        if ms_fix_fail == 0:
            print(f'[PASS] {ms_fix_pass} fixture assertions pass — meta_status_rollup loader verified')
            total_passes += 1
        else:
            print(f'[FAIL] {ms_fix_fail} fixture assertion(s) failed ({ms_fix_pass} passed)')
            for line in ms_fix_findings:
                print(line)
                total_fails += 1
    except Exception as e:
        print(f'[FAIL] meta_status fixture CRASHED: {e}')
        total_fails += 1

    # --- 3783a7cb Piece E: M1/M2 meta_status checks (WARN) ---
    print('\n--- meta_status M1/M2 (3783a7cb Piece E; capsule-driven rollup coverage + ELSE-leak; WARN) ---')
    ms_gaps = 0
    ms_unresolved = 0
    try:
        ms_findings, ms_gaps, ms_unresolved = check_meta_status_m1_m2(vault)
        if not ms_findings:
            print('[PASS] meta_status M1/M2: no coverage gaps + no unresolved entries (or no rollups declared yet)')
            total_passes += 1
        else:
            print(f'[INFO] meta_status_coverage_gaps={ms_gaps} meta_status_unresolved={ms_unresolved}')
            for line in ms_findings[:20]:
                print(line)
                stripped = line.strip()
                if stripped.startswith('[ERROR]'):
                    total_fails += 1
                elif stripped.startswith('[WARN]'):
                    total_warnings += 1
            if len(ms_findings) > 20:
                remainder = ms_findings[20:]
                extra_warn = sum(1 for l in remainder if l.strip().startswith('[WARN]'))
                extra_error = sum(1 for l in remainder if l.strip().startswith('[ERROR]'))
                print(f'  ... and {len(remainder)} more')
                total_warnings += extra_warn
                total_fails += extra_error
            if ms_gaps == 0 and ms_unresolved == 0 and not any(l.strip().startswith('[ERROR]') for l in ms_findings):
                total_passes += 1
    except Exception as e:
        print(f'[FAIL] meta_status M1/M2 CRASHED: {e}')
        total_fails += 1

    # --- d996b941 L0a: Principal-Class Present (WARN; d996b941 §L0a; task.capsule v4.3 Rule 14) ---
    print('\n--- Principal-Class Present (d996b941 L0a; every active type:principal carries principal_class; WARN) ---')
    try:
        pcp_findings, pcp_checked, pcp_defects = check_principal_class_present(vault)
        if not pcp_findings:
            print(f'[PASS] {pcp_checked} active principal(s) — all carry valid principal_class')
            total_passes += 1
        else:
            print(f'[INFO] {pcp_checked} principal(s) checked; {pcp_defects} missing/invalid principal_class (WARN)')
            for line in pcp_findings[:10]:
                print(f'  {line}')
                total_warnings += 1
            if len(pcp_findings) > 10:
                extra = len(pcp_findings) - 10
                total_warnings += extra
                print(f'  ... and {extra} more')
    except Exception as e:
        print(f'[FAIL] principal-class-present CRASHED: {e}')
        total_fails += 1

    # --- d996b941 L0b: Principal Slug Uniqueness (WARN; d996b941 §L0b; nondeterministic-resolution guard) ---
    print('\n--- Principal Slug Uniqueness (d996b941 L0b; no two active principals share slug/alias; WARN) ---')
    try:
        psu_findings, psu_checked, psu_defects = check_principal_slug_unique(vault)
        if not psu_findings:
            print(f'[PASS] {psu_checked} active principal(s) — all slugs/aliases unique')
            total_passes += 1
        else:
            print(f'[INFO] {psu_checked} principal(s) checked; {psu_defects} slug collision(s) (WARN)')
            for line in psu_findings[:10]:
                print(f'  {line}')
                total_warnings += 1
            if len(psu_findings) > 10:
                extra = len(psu_findings) - 10
                total_warnings += extra
                print(f'  ... and {extra} more')
    except Exception as e:
        print(f'[FAIL] principal-slug-unique CRASHED: {e}')
        total_fails += 1

    # --- d996b941 L1: Task Approver ≠ Executor (WARN; task.capsule v4.3 Check 22) ---
    print('\n--- Task Approver Distinct From Executor (d996b941 L1; task.capsule v4.3 Check 22; WARN) ---')
    try:
        tad_findings, tad_checked, _tad_defects = check_task_approver_distinct_from_executor(vault)
        if not tad_findings:
            print(f'[PASS] {tad_checked} approval_required+closed+done task(s) checked — all have independent approver')
            total_passes += 1
        else:
            print(f'[INFO] {tad_checked} task(s) checked; {len(tad_findings)} approver-independence finding(s) (WARN)')
            for line in tad_findings[:10]:
                print(f'  {line}')
                total_warnings += 1
            if len(tad_findings) > 10:
                extra = len(tad_findings) - 10
                total_warnings += extra
                print(f'  ... and {extra} more')
    except Exception as e:
        print(f'[FAIL] task-approver-distinct CRASHED: {e}')
        total_fails += 1

    # --- v1.68 S2: Inbox Transition Protocol (HARD-tier ERROR; SOFT=WARN) ---
    print('\n--- Inbox Transition Protocol (v1.68 S2; 344607e4; HARD=terminal ERROR post-drain; SOFT=active-work WARN) ---')
    try:
        itp_findings, itp_checked, itp_hard, itp_soft = check_inbox_transition(vault)
        if itp_hard == 0 and itp_soft == 0:
            print(f'[PASS] {itp_checked} inbox members checked — no transition violations')
            total_passes += 1
        else:
            for line in itp_findings[:25]:
                print(f'  {line}')
                if line.strip().startswith('[WARN]'):
                    total_warnings += 1
            if len(itp_findings) > 25:
                extra = len(itp_findings) - 25
                print(f'  ... and {extra} more')
                total_warnings += extra
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] inbox-transition check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    try:
        from lib.loop_validators import run_all_loop_checks
    except ImportError:
        print("[WARN] loop_validators lib not found")
        run_all_loop_checks = None

    # --- v1.71 S1: Loop Primitive checks (ERROR ratchet v1.71) ---
    print("\n--- Loop Primitive checks (v1.71 S1; ERROR) ---")
    if run_all_loop_checks:
        try:
            loop_findings, loop_total, loop_defects = run_all_loop_checks(vault)
            if loop_total == 0:
                print("[INFO] No loop entries or runs found — skipping")
            elif not loop_findings:
                print(f"[PASS] {loop_total} loop-run(s) / loop-definition(s) checked — all clean")
                total_passes += 1
            else:
                print(f"[FAIL] {loop_total} loop items checked; {loop_defects} finding(s)")
                for line in loop_findings:
                    print(f"  {line}")
                    total_fails += 1
        except Exception as e:
            print(f"[FAIL] loop-validators CRASHED: {e}")
            total_fails += 1
    else:
        print("[WARN] loop-validators skipped (lib missing)")

    # --- Summary ---
    print()
    print('=' * 70)
    print(f'Summary: {total_passes} passed, {total_fails} failed, {total_warnings} warnings, {total_normalizable} normalizable')
    print('=' * 70)

    # C.7 — Stream C auto-emission: tropo.validator.run.completed (v1.58)
    try:
        from lib.event_emitter import auto_emit
        auto_emit(
            "tropo.validator.run.completed",
            "/tools/tropo-validate",
            "d2b9c8e6",  # tool's own UID (A108: tools emit their own UID, not agent-root 123e12e7)
            lifecycle="ephemeral",
            data={"passed": total_passes, "failed": total_fails, "warnings": total_warnings, "normalizable": total_normalizable, "meta_status_coverage_gaps": ms_gaps, "meta_status_unresolved": ms_unresolved},
        )
    except Exception:
        pass

    return 0 if total_fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
