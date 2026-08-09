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
cli_command: python3 vault/tools/tropo-validate.py [--vault-path PATH]
script_path: vault/tools/tropo-validate.py
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
description: 'Read-only structural validator for a Tropo vault. Six check classes: (1) Registry integrity — every file in agent-registry.yaml exists on disk; every agent file on disk is registered. (2) UID consistency — uid: frontmatter matches filename. (3) Orphan detection — files in governed scan-dirs without uid: (excludes README/CURATOR/AGENTS skip-list). (4) AGENTS.md coverage — every directory under requiredDirs has AGENTS.md. (5) Cross-reference resolution — every UID referenced in frontmatter resolves to a registry entry. (6) v1.5, re-pointed 2026-07-14 (66b6f3e8): blocked-task parity check, now cross-checking live vault/00-index.jsonl against vault/00-index.sqlite (retired 00-integrity.json had no writer since 2026-06-04; Argus A130 ruling, event 00006330).'
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
modified: 2026-07-26
modified_by: argus-a142
governed_by: d5e1b4a3
capsule_version: '2.5'
schema_version: 2
extraction_scope: ship
member_of:
- 8dd772a0
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
belt_invocation: "python3 vault/tools/tropo-validate.py"
belt_example: "python3 vault/tools/tropo-validate.py --vault-path ."
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
    6. v1.5 (inbox 656c26d0), re-pointed 2026-07-14 (vault/files/66b6f3e8.md;
       Argus A130 ruling, event 00006330): blocked-task parity check. Formerly
       compared 00-integrity.json's self-reported blocked_tasks count against
       its own uids array (written by a now-dead TS rebuilder with no writer
       since 2026-06-04). Now independently derives the set of
       type:task status:blocked UIDs from each of the two live truth
       surfaces — vault/00-index.jsonl and vault/00-index.sqlite — and
       flags any mismatch between them.

Usage:
    python3 vault/tools/tropo-validate.py            # against current vault
    python3 vault/tools/tropo-validate.py --vault-path <path>

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
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

# v1.56 Lane S: script relocated to vault/tools/; lib/ is under .tropo/scripts/
_TROPO_SCRIPTS = Path(__file__).resolve().parents[2] / '.tropo' / 'scripts'
if str(_TROPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TROPO_SCRIPTS))

import yaml  # v1.33.0 Stream H §3.1 PyYAML AST walk (R3 sa.skeptic-078 + sa.cold-boot-181 absorption)

# d996b941 L0c: shared identity resolver — must hard-fail on import (AC-L0c-fail)
from lib._identity import _resolve_principal_uid, _get_principal_class  # noqa: E402

# ADR-047 helper lives under vault/tools/lib/.  Load by path instead of
# ``from lib`` because several regression harnesses pre-import the separate
# namespace package at .tropo/scripts/lib before importing this module.
import importlib.util as _importlib_util
_mounted_projection_trust_spec = _importlib_util.spec_from_file_location(
    "tropo_mounted_projection_trust",
    Path(__file__).resolve().parent / "lib" / "mounted_projection_trust.py",
)
if (
    _mounted_projection_trust_spec is None
    or _mounted_projection_trust_spec.loader is None
):
    raise ImportError("mounted projection trust helper could not be loaded")
mounted_projection_trust = _importlib_util.module_from_spec(
    _mounted_projection_trust_spec
)
_mounted_projection_trust_spec.loader.exec_module(mounted_projection_trust)

_index_surfaces_spec = _importlib_util.spec_from_file_location(
    "tropo_index_surfaces",
    Path(__file__).resolve().parent / "lib" / "index_surfaces.py",
)
if _index_surfaces_spec is None or _index_surfaces_spec.loader is None:
    raise ImportError("ADR-047 index_surfaces helper could not be loaded")
index_surfaces = _importlib_util.module_from_spec(_index_surfaces_spec)
_index_surfaces_spec.loader.exec_module(index_surfaces)

_EVENT_IDENTITY_MODULE_NAME = "tropo_event_identity"
if _EVENT_IDENTITY_MODULE_NAME in sys.modules:
    event_identity = sys.modules[_EVENT_IDENTITY_MODULE_NAME]
else:
    _event_identity_spec = _importlib_util.spec_from_file_location(
        _EVENT_IDENTITY_MODULE_NAME,
        Path(__file__).resolve().parent / "lib" / "event_identity.py",
    )
    if _event_identity_spec is None or _event_identity_spec.loader is None:
        raise ImportError("shared event_identity helper could not be loaded")
    event_identity = _importlib_util.module_from_spec(_event_identity_spec)
    sys.modules[_EVENT_IDENTITY_MODULE_NAME] = event_identity
    _event_identity_spec.loader.exec_module(event_identity)

_PRUNING_CONTRACT_MODULE_NAME = "tropo_pruning_contract"
if _PRUNING_CONTRACT_MODULE_NAME in sys.modules:
    pruning_contract = sys.modules[_PRUNING_CONTRACT_MODULE_NAME]
else:
    _pruning_contract_spec = _importlib_util.spec_from_file_location(
        _PRUNING_CONTRACT_MODULE_NAME,
        Path(__file__).resolve().parent / "lib" / "pruning_contract.py",
    )
    if _pruning_contract_spec is None or _pruning_contract_spec.loader is None:
        raise ImportError("shared pruning contract helper could not be loaded")
    pruning_contract = _importlib_util.module_from_spec(_pruning_contract_spec)
    sys.modules[_PRUNING_CONTRACT_MODULE_NAME] = pruning_contract
    _pruning_contract_spec.loader.exec_module(pruning_contract)

_FINDINGS_MODULE_NAME = "tropo_engine_findings"
if _FINDINGS_MODULE_NAME in sys.modules:
    typed_findings = sys.modules[_FINDINGS_MODULE_NAME]
else:
    _findings_spec = _importlib_util.spec_from_file_location(
        _FINDINGS_MODULE_NAME,
        Path(__file__).resolve().parent / "lib" / "findings.py",
    )
    if _findings_spec is None or _findings_spec.loader is None:
        raise ImportError("typed findings primitive could not be loaded")
    typed_findings = _importlib_util.module_from_spec(_findings_spec)
    sys.modules[_FINDINGS_MODULE_NAME] = typed_findings
    _findings_spec.loader.exec_module(typed_findings)

Finding = typed_findings.Finding
FindingTally = typed_findings.FindingTally
Severity = typed_findings.Severity


def _load_public_snapshot_contract():
    """Load the co-located Phase 0.6 contract logic without ``lib`` ambiguity."""
    module_name = "tropo_public_snapshot_contract"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = _importlib_util.spec_from_file_location(
        module_name,
        Path(__file__).resolve().parent / "lib" / "public_snapshot.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError("public snapshot contract helper could not be loaded")
    module = _importlib_util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
UID_RE = re.compile(r'^[0-9a-f]{8}$')
UID_REF_RE = re.compile(r'\b([0-9a-f]{8})\b')


def _index_union(vault: Path) -> list[dict]:
    """Resolution/validation view across ADR-047 current + archive surfaces.

    The default index is intentionally current-only.  Validators preserve
    history and cross-reference resolution by opting into the archive surface.
    General diagnostics retain tolerant compatibility semantics; checks that
    prove union completeness or govern mutation call ``read_jsonl_strict``
    directly and fail closed when either surface is absent.
    """
    return index_surfaces.load_index_records(vault, include_archive=True)


def _index_union_uids(vault: Path) -> set[str]:
    return {
        str(record["uid"])
        for record in _index_union(vault)
        if record.get("uid")
    }


def _canonical_event_union(vault: Path) -> list[dict]:
    """Load canonical legacy-plus-stream history for event-backed checks."""
    studio_root = vault.parent if (vault / "files").is_dir() else vault
    return event_identity.load_event_union(studio_root)


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


def body_sha256(path: Path, strip_navblock: bool = False) -> str:
    """v1.70 S3.5.2 — Shared hashing contract for boot-derivation fingerprints.

    Body = content after the closing frontmatter fence (---).
    Normalization: collapse to exactly one trailing newline.
    strip_navblock: when True, remove <!-- nav-block:start --> ... <!-- nav-block:end -->
    before hashing. Use for source files (e.g. operating-principles.md) that have
    auto-generated nav-blocks which churn on every graph rebuild. (Talos T21, 2026-06-22;
    Argus A119 diagnosis: the gate drifted on every rebuild due to nav-block churn.)
    Ensures writer (--write-fingerprints) and checker share one hashing truth.
    """
    import hashlib, re as _re
    raw = path.read_bytes()
    # Split once on the CLOSING frontmatter fence
    parts = raw.split(b'\n---\n', 1)
    body = parts[1] if len(parts) == 2 else raw
    if strip_navblock:
        body = _re.sub(
            rb'<!-- nav-block:start -->.*?<!-- nav-block:end -->',
            b'',
            body,
            flags=_re.DOTALL,
        )
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
# Vendor-ref manifest loading (S1, v1.80 re-build)
# ---------------------------------------------------------------------------

VENDOR_REF_MANIFEST_REL_PATH = Path('vault') / 'vendor-refs-manifest.json'


def load_vendor_ref_manifest(vault: Path) -> Optional[set[str]]:
    """S1 (v1.80 re-build): load the shipped vendor-ref manifest, if present.

    Customer-mode classification must be data (the manifest the box carries),
    not guesswork (a blanket "not in subset index -> INFO" downgrade — the
    v1.80-original defect a refuter caught with n_defects=0 on a planted
    genuinely-broken ref). This loader is intentionally strict: any structural
    problem (missing file, bad JSON, wrong shape) returns None so the caller
    fails closed (treats every not-in-index ref as a real defect) rather than
    silently trusting malformed data.

    Returns the set of vendor-ref UIDs, or None if no usable manifest exists.
    """
    manifest_path = vault / VENDOR_REF_MANIFEST_REL_PATH
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    refs = data.get('vendor_refs')
    if not isinstance(refs, list):
        return None
    return {r for r in refs if isinstance(r, str) and UID_RE.match(r)}


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


def check_pruning_contract(vault: Path) -> tuple[list[str], int, int]:
    """Validate every present pruning block through the shared core-v1.7 checker.

    The scan is read-only and closed to the same four Markdown homes as the
    canonical writer. ``checked`` counts present pruning blocks; absent blocks
    are silent PASS. ``defects`` counts FAIL findings only, while WARN findings
    remain visible to the caller's warning tally.
    """
    results = pruning_contract.check_pruning_vault(vault)
    findings = [
        line
        for result in results
        for line in result.formatted_findings()
    ]
    defects = sum(result.defects for result in results)
    return findings, len(results), defects


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

    # (b) index duplicate UIDs — ADR-047 requires zero overlap both within
    # and ACROSS the current/archive surfaces.
    index_paths = (
        vault / "vault" / index_surfaces.CURRENT_INDEX_NAME,
        vault / "vault" / index_surfaces.ARCHIVE_INDEX_NAME,
    )
    for index_path in index_paths:
        if not index_path.is_file():
            raise index_surfaces.IndexSurfaceRefusal(
                f"REFUSAL: UID collision union requires {index_path}"
            )
        seen: dict[str, str] = {}
        for entry in index_surfaces.read_jsonl_strict(index_path):
            uid = entry.get("uid")
            if not uid:
                continue
            if uid in seen:
                if uid not in {f.split()[1] for f in findings if f.startswith("[WARN] index")}:
                    findings.append(
                        f"[WARN] index duplicate: uid {uid!r} appears multiple times in "
                        f"{index_path.name} "
                        f"(stale rebuild artifact — rebuild-vault.py --apply resolves)"
                    )
                    dup_uid_count += 1
            else:
                seen[uid] = entry.get("type", "?")

    current_uids = {
        rec.get("uid")
        for rec in index_surfaces.read_jsonl_strict(index_paths[0])
        if rec.get("uid")
    }
    archive_uids = {
        rec.get("uid")
        for rec in index_surfaces.read_jsonl_strict(index_paths[1])
        if rec.get("uid")
    }
    for uid in sorted(current_uids & archive_uids):
        findings.append(
            f"[WARN] index duplicate: uid {uid!r} appears in BOTH "
            f"{index_surfaces.CURRENT_INDEX_NAME} and {index_surfaces.ARCHIVE_INDEX_NAME} "
            f"(ADR-047 partition overlap — rebuild-vault.py --apply resolves)"
        )
        dup_uid_count += 1

    checked = int_uid_count + dup_uid_count
    return findings, int_uid_count, dup_uid_count


def _resolve_index_record_path(vault: Path, record: dict) -> Optional[Path]:
    """Resolve an index row to canonical local or mounted source."""
    relative = record.get('path')
    if isinstance(relative, str) and relative:
        if relative.startswith('mounted/'):
            parts = Path(relative).parts
            if len(parts) >= 4:
                vault_uid = parts[1]
                lock_path = vault / '.tropo-studio' / 'compose.lock'
                try:
                    lock = json.loads(lock_path.read_text(encoding='utf-8'))
                    mount_record = lock.get('vaults', {}).get(vault_uid, {})
                    mount_path = mount_record.get('mount_path')
                    if mount_path:
                        candidate = Path(mount_path).joinpath(*parts[2:])
                        if candidate.is_file():
                            return candidate
                except (OSError, json.JSONDecodeError, AttributeError):
                    return None
        else:
            candidate = vault / relative
            if candidate.is_file():
                return candidate

    uid = record.get('uid')
    if not isinstance(uid, str) or not uid:
        return None
    candidates = (
        vault / 'vault' / 'files' / f'{uid}.md',
        vault / 'vault' / 'agents' / f'{uid}.md',
        vault / 'vault' / 'playbooks' / f'{uid}.md',
        vault / 'vault' / 'skills' / f'{uid}.md',
        vault / 'vault' / 'session-agents' / f'{uid}.md',
        vault / 'vault' / 'actions' / f'{uid}.md',
        vault / 'vault' / 'tools' / f'{uid}.py',
        vault / 'vault' / 'tools' / f'{uid}.md',
        vault / 'vault' / 'tools' / f'{uid}.json',
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def check_index_union_integrity(vault: Path) -> tuple[list[str], int, int]:
    """ERROR invariant over the explicit current + archive union.

    Unlike ``load_index_records(..., include_archive=True)``, this check must
    preserve duplicate rows so it can prove uniqueness rather than hide an
    impossible overlap through consumer-side deduplication.
    """
    findings: list[str] = []
    rows: list[tuple[str, dict]] = []
    try:
        with index_surfaces.index_write_lock(vault, recover=False):
            for surface_name in (
                index_surfaces.CURRENT_INDEX_NAME,
                index_surfaces.ARCHIVE_INDEX_NAME,
            ):
                path = vault / 'vault' / surface_name
                if not path.is_file():
                    findings.append(
                        f'[ERROR] INDEX-UNION (current + archive): required '
                        f'surface {surface_name} is missing'
                    )
                    continue
                rows.extend(
                    (surface_name, record)
                    for record in index_surfaces.read_jsonl_strict(path)
                )
    except (
        index_surfaces.IndexSurfaceRefusal,
        index_surfaces.IndexLockTimeout,
    ) as exc:
        findings.append(
            f'[ERROR] INDEX-UNION (current + archive): {exc}'
        )

    seen: dict[str, str] = {}
    for surface_name, record in rows:
        uid = record.get('uid')
        if not isinstance(uid, str) or not uid:
            findings.append(
                f'[ERROR] INDEX-UNION (current + archive): row in '
                f'{surface_name} has no string uid'
            )
            continue
        if uid in seen:
            findings.append(
                f'[ERROR] INDEX-UNION UID uniqueness: {uid!r} appears in '
                f'{seen[uid]} and {surface_name}; full union requires one row '
                'per UID'
            )
        else:
            seen[uid] = surface_name
        if _resolve_index_record_path(vault, record) is None:
            findings.append(
                f'[ERROR] INDEX-UNION row resolution: {uid!r} from '
                f'{surface_name} has no backing canonical file '
                '(checked across current + archive union)'
            )

    return findings, len(rows), len(findings)


def _load_template_leg_module():
    module_name = 'tropo_live_template_leg'
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = _importlib_util.spec_from_file_location(
        module_name,
        Path(__file__).resolve().parent / 'lib' / 'template_leg.py',
    )
    if spec is None or spec.loader is None:
        raise ImportError('template-leg helper could not be loaded')
    module = _importlib_util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _folder_mount_registry(vault: Path) -> dict[str, dict]:
    registry_path = vault / '.tropo-studio' / 'folder-mounts.json'
    try:
        registry = json.loads(registry_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    mounts = registry.get('mounts') if isinstance(registry, dict) else None
    if not isinstance(mounts, dict):
        return {}
    return {
        str(uid): value
        for uid, value in mounts.items()
        if UID_RE.fullmatch(str(uid)) and isinstance(value, dict)
    }


def _template_projection_file_matches(vault: Path, record: dict) -> bool:
    uid = str(record.get('uid') or '')
    mount_uid = str(record.get('mount_uid') or '')
    availability = str(record.get('availability') or '')
    projection = vault / 'vault' / 'files' / f'{uid}.md'
    try:
        if projection.is_symlink():
            return False
        text = projection.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return False
    frontmatter = split_frontmatter(text)
    if frontmatter is None:
        return False
    if not (
        get_scalar(frontmatter, 'uid') == uid
        and get_scalar(frontmatter, 'type') == 'external-artifact'
        and get_scalar(frontmatter, 'mount_uid') == mount_uid
        and get_scalar(frontmatter, 'projection_authority') == 'derived-only'
        and get_scalar(frontmatter, 'availability') == availability
    ):
        return False
    if availability in {'unavailable', 'ambiguous'}:
        return not any(
            get_scalar(frontmatter, field)
            for field in (
                'source_path',
                'source_sidecar',
                'original_path',
                'mount_relpath',
            )
        ) and not any(
            get_list(frontmatter, field)
            for field in ('member_of', 'relations')
        )
    return True


def _available_projection_binding_decision(
    record: dict,
    mount: dict,
) -> dict:
    mount_uid = str(record.get('mount_uid') or '')
    if mount.get('availability') != 'available':
        return {
            'status': 'untrusted',
            'reason': 'mount-unavailable',
            'relpath': None,
            'sidecar_input': None,
        }
    raw_root = mount.get('path')
    if not isinstance(raw_root, str) or not raw_root.strip():
        return {
            'status': 'untrusted',
            'reason': 'mount-root-missing',
            'relpath': None,
            'sidecar_input': None,
        }
    root = Path(os.path.abspath(Path(raw_root).expanduser()))
    try:
        if root.is_symlink() or not root.is_dir():
            raise OSError('mount root is not a regular directory')
    except OSError:
        return {
            'status': 'untrusted',
            'reason': 'mount-root-unavailable',
            'relpath': None,
            'sidecar_input': None,
        }
    sidecars, sidecars_by_path = (
        mounted_projection_trust.load_sidecar_catalog(
            root,
            max_bytes=4 * 1024 * 1024,
        )
    )
    return mounted_projection_trust.verify_available_projection_binding(
        record,
        mount_uid=mount_uid,
        mount=mount,
        mount_root=root,
        sidecars=sidecars,
        sidecars_by_path=sidecars_by_path,
    )


def _template_body_shape_exemption_decision(
    record: dict,
    *,
    vault: Path,
    mounts: dict[str, dict],
) -> tuple[bool, Optional[str]]:
    """Whether this row is a source-shaped projection, not a minted body.

    The exemption is intentionally limited to this validator leg. UID,
    duplicate, provenance, capsule, index-union, and structural checks run in
    their own passes and continue to see the row.
    """
    uid = str(record.get('uid') or '')
    mount_uid = str(record.get('mount_uid') or '')
    availability = str(record.get('availability') or '')
    mount = mounts.get(mount_uid)
    if not bool(
        record.get('type') == 'external-artifact'
        and record.get('projection_authority') == 'derived-only'
        and UID_RE.fullmatch(uid)
        and UID_RE.fullmatch(mount_uid)
        and isinstance(mount, dict)
        and mount.get('state') == 'adopted'
        and record.get('path') == f'vault/files/{uid}.md'
        and availability in {'available', 'unavailable', 'ambiguous'}
    ):
        return False, 'projection-ownership-fields-invalid'
    if not _template_projection_file_matches(vault, record):
        return False, 'projection-stub-mismatch'
    if availability == 'available':
        binding = _available_projection_binding_decision(record, mount)
        return (
            binding.get('status') == 'verified',
            (
                None
                if binding.get('status') == 'verified'
                else str(binding.get('reason') or 'unknown')
            ),
        )
    projection_uids = mount.get('projection_uids')
    projection_hashes = mount.get('projection_hashes')
    expected_hash = (
        projection_hashes.get(uid)
        if isinstance(projection_hashes, dict)
        else None
    )
    try:
        actual_hash = hashlib.sha256(
            (vault / 'vault' / 'files' / f'{uid}.md').read_bytes()
        ).hexdigest()
    except OSError:
        return False
    exempt = (
        mount.get('availability') == availability
        and isinstance(projection_uids, list)
        and uid in {str(candidate) for candidate in projection_uids}
        and isinstance(expected_hash, str)
        and actual_hash == expected_hash
    )
    return (
        exempt,
        None if exempt else 'registry-tombstone-ownership-invalid',
    )


def _template_body_shape_exempt(
    record: dict,
    *,
    vault: Path,
    mounts: dict[str, dict],
) -> bool:
    exempt, _reason = _template_body_shape_exemption_decision(
        record,
        vault=vault,
        mounts=mounts,
    )
    return exempt


def check_live_template_body_shape(vault: Path) -> tuple[list[str], int, int]:
    """Validate template/body shape for CURRENT rows only.

    Archived/superseded entries remain available to union integrity and
    resolution checks, but they are frozen history rather than live authoring
    work.  This is deliberately index-scoped instead of a ``vault/files`` walk.

    Two scoping rules the §Template leg's own governing text already carries, and
    that this check originally dropped:

    * **The leg is a MINT-TIME contract.**  It describes what ``mint file``
      stamps, so it can only bind instances that were minted from it.  Every leg
      in this vault was authored 2026-07-12..07-18 while the corpus goes back
      months, and the Mike-walked program brief (b600698e §6) puts that corpus on
      the protect list -- "they gain template/verifier legs, nothing migrates" --
      with S2 (bba40cd7) naming historical migration explicitly OUT of scope.
      Each capsule declares ``template_enforced_from`` and may refine a revised
      body contract with ``template_enforced_from_version``; older instances are
      grandfathered for section presence. Judged against 1,089 findings across
      363 entries that were retroactive by construction.
    * **Severity is the capsule's to declare, not this function's.**  The grades
      come from the capsule-of-capsules §Generic Instance-Verifier Checks.  A
      hardcoded grade here would be the second source of truth that drifts.

    Grandfathering is deliberately narrow: it suppresses MISSING-SECTION only.
    A pre-leg entry stays subject to every other check in this function and in
    the rest of the validator.
    """
    current_path = vault / 'vault' / index_surfaces.CURRENT_INDEX_NAME
    if not current_path.exists():
        return [], 0, 0
    try:
        current_records = index_surfaces.read_jsonl_strict(current_path)
    except index_surfaces.IndexSurfaceRefusal as exc:
        return [f'[ERROR] LIVE-TEMPLATE current surface unreadable: {exc}'], 0, 1

    template_leg = _load_template_leg_module()
    severities = template_leg.load_instance_verifier_severities(vault)
    mounts = _folder_mount_registry(vault)
    findings: list[str] = []
    undeclared_grades: set[str] = set()

    def grade(check_name: str) -> Optional[str]:
        """The capsule-declared grade, or None when the capsule is silent.

        None is not "use a default" -- there is no default.  The caller drops the
        finding and the run reports the undeclared check as an ERROR, so an
        ungraded check fails loudly instead of silently picking a severity that
        nothing governs.
        """
        severity = severities.get(check_name)
        if severity is None:
            undeclared_grades.add(check_name)
        return severity

    checked = 0
    undeclared_enforcement: dict[str, str] = {}
    verifier_legs: dict[str, object] = {}
    unavailable_legs: set[str] = set()
    for record in current_records:
        uid = record.get('uid')
        entry_type = record.get('type')
        if not isinstance(uid, str) or not isinstance(entry_type, str):
            continue
        record_path = record.get('path')
        if (
            isinstance(record_path, str)
            and Path(record_path).suffix.lower() in {'.py', '.json'}
        ):
            # Template/body-shape is a Markdown contract. Tool source and JSON
            # metadata remain outside this leg even if their rows carry fields
            # that resemble a mounted projection.
            continue
        exempt, provenance_reason = _template_body_shape_exemption_decision(
            record,
            vault=vault,
            mounts=mounts,
        )
        if exempt:
            continue
        if (
            provenance_reason
            and entry_type == 'external-artifact'
            and record.get('mount_uid')
        ):
            findings.append(
                f'[WARN] {uid} ({entry_type}): '
                'MOUNTED-PROJECTION-PROVENANCE-INVALID — '
                f'{provenance_reason}; template/body-shape exemption denied'
            )
        if entry_type in unavailable_legs:
            continue
        leg = verifier_legs.get(entry_type)
        if leg is None:
            try:
                leg = template_leg.load_verifier_template(vault, entry_type)
            except template_leg.TemplateLegError:
                unavailable_legs.add(entry_type)
                continue
            verifier_legs[entry_type] = leg
        instance_path = _resolve_index_record_path(vault, record)
        if instance_path is None:
            # The union integrity check owns the ERROR to avoid double-counting.
            continue
        try:
            instance_text = instance_path.read_text(encoding='utf-8')
        except (OSError, UnicodeError) as exc:
            severity = grade('body-unreadable')
            if severity:
                findings.append(
                    f'[{severity}] {uid} ({entry_type}): LIVE-BODY unreadable — {exc}'
                )
            checked += 1
            continue
        checked += 1

        if leg.enforced_from is None:
            undeclared_enforcement[entry_type] = leg.capsule_path.name

        instance_fm = split_frontmatter(instance_text) or ''
        created = get_scalar(instance_fm, 'created') or record.get('created')
        capsule_version = (
            get_scalar(instance_fm, 'capsule_version')
            or record.get('capsule_version')
        )
        if not leg.grandfathers(
            created if isinstance(created, str) else None,
            capsule_version,
        ):
            severity = grade('sections-present')
            if severity:
                found_sections = template_leg.find_sections(instance_text)
                for title in leg.required_sections():
                    if title not in found_sections:
                        findings.append(
                            f'[{severity}] {uid} ({entry_type}): MISSING-SECTION — '
                            f"required section '{title}' not found (CURRENT surface "
                            f'only; template: {leg.capsule_path.name}, enforced from '
                            f'{leg.enforced_from}; entry created {created})'
                        )

        severity = grade('placeholder-survival')
        if severity:
            for placeholder_text in template_leg.find_required_placeholders(instance_text, entry_type):
                findings.append(
                    f'[{severity}] {uid} ({entry_type}): INCOMPLETE — required '
                    f'placeholder survived: "{placeholder_text}" '
                    '(CURRENT surface only)'
                )
        severity = grade('stray-mint-token')
        if severity:
            for stray in template_leg.find_stray_mint_tokens(instance_text, entry_type):
                findings.append(
                    f'[{severity}] {uid} ({entry_type}): MALFORMED-MINT — stray '
                    f'{stray} token survived (CURRENT surface only)'
                )

    for entry_type, capsule_name in sorted(undeclared_enforcement.items()):
        findings.append(
            f'[WARN] {capsule_name} ({entry_type}): TEMPLATE-ENFORCEMENT-UNDECLARED '
            '— capsule carries a §Template leg but no template_enforced_from; '
            'section-presence enforcement is inert for this type until the date '
            "the leg was authored is declared (core.capsule §Optional Frontmatter)"
        )
    if undeclared_grades:
        findings.append(
            '[ERROR] INSTANCE-VERIFIER-SEVERITY: no declared grade for '
            f'{", ".join(sorted(undeclared_grades))} in vault/capsules/'
            f'{template_leg.CAPSULE_DEFINITION_CAPSULE} §Generic Instance-Verifier '
            'Checks — those findings were withheld rather than graded against a '
            'severity nothing governs'
        )

    defects = sum(
        1 for finding in findings
        if finding.startswith('[FAIL]') or finding.startswith('[ERROR]')
    )
    return findings, checked, defects


def check_mint_id_chokepoint(vault: Path) -> tuple[list[str], int, int]:
    """796d9330 / ADR-050 — every governed 8-hex UID mint must route through
    tropo-mint-id.py's collision-checked mint(). A raw secrets.token_hex(4) CALL
    anywhere else in vault/tools/ is an unchecked bypass that can silently
    collide with an in-use UID (the exact defect class ADR-050 closes).

    Uses the `ast` module (not a text regex) so the check only fires on an actual
    function-call site — never on the pattern appearing in a docstring, comment,
    or string literal (the exact false-positive class a raw-text regex would hit
    on this function's own docstring).

    Legitimate exceptions:
    - tropo-mint-id.py itself (the canonical implementation) + tropo-archive.py's
      `archive-<hex>` event-id (monotonic-sequence kind, deferred — ADR-050
      Decision 4(d)) — both filename-allowlisted.
    - A specific call inline-marked `# noqa: mint-id-chokepoint-deferred` — for a
      knowingly out-of-scope advisory/print-only site named in a dev-spec's own
      triage (e.g. 796d9330's 4beff0d6.py suggested_uid scaffold hint). The marker
      is a deliberate, visible opt-out on the exact line, not a blanket file skip.

    WARN at v1.0 (796d9330 AC4); ERROR-ratchet after the first clean pass.
    Proven by an adversarial plant (AC5) — see test_capability_chain_smoke.py
    check_mint_id_chokepoint_gate.

    Returns (findings, total_scanned, violation_count).
    """
    import ast as _ast

    ALLOWLIST = frozenset({'tropo-mint-id.py', 'tropo-archive.py'})
    NOQA_MARKER = 'mint-id-chokepoint-deferred'

    tools_dir = vault / 'vault' / 'tools'
    findings: list[str] = []
    scanned = 0
    violations = 0
    if not tools_dir.is_dir():
        return findings, scanned, violations

    for f in sorted(tools_dir.glob('*.py')):
        scanned += 1
        if f.name in ALLOWLIST:
            continue
        try:
            text = f.read_text(errors='ignore')
        except Exception:
            continue
        try:
            tree = _ast.parse(text, filename=str(f))
        except SyntaxError:
            continue
        lines = text.splitlines()
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Call):
                continue
            func = node.func
            is_token_hex = (
                isinstance(func, _ast.Attribute) and func.attr == 'token_hex'
                and isinstance(func.value, _ast.Name) and func.value.id == 'secrets'
            )
            if not is_token_hex:
                continue
            if len(node.args) != 1 or not isinstance(node.args[0], _ast.Constant) or node.args[0].value != 4:
                continue
            lineno = getattr(node, 'lineno', 0)
            line_text = lines[lineno - 1] if 0 < lineno <= len(lines) else ''
            if NOQA_MARKER in line_text:
                continue
            violations += 1
            findings.append(
                f'[WARN] vault/tools/{f.name}:{lineno} — raw secrets.token_hex(4) '
                f'bypasses the tropo-mint-id.py chokepoint (796d9330/ADR-050); '
                f'route via mint()'
            )
    return findings, scanned, violations


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


def check_uid_cross_references(vault: Path, all_uids: set[str],
                               release_mode: bool = False,
                               customer_mode: bool = False,
                               vendor_manifest: Optional[set[str]] = None) -> tuple[list[str], int, int]:
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

    release_mode: when True, a UID reference not in the (subset) index resolves to
    [INFO] instead of [FAIL]. Safe by construction: the full-studio validation (pre-build,
    0 FAILED) guarantees no genuine broken refs exist, so any not-in-index ref in a release
    artifact is by definition an expected outward-ref to a non-shipped studio-internal file.
    (Dev-spec f8b51f4d D1, v1.74 Release-Self-Validates.)

    customer_mode: v1.80 re-build (S1). A shipped customer box has no source studio to fall
    back on, so it CANNOT use release_mode's blanket "not in subset index -> safe by
    construction" downgrade — that logic was v1.80's original defect: it swallowed a planted
    genuinely-broken ref (refs:[ffffffff], nonexistent anywhere) as INFO with n_defects=0.
    Customer-mode classification must be DATA, not guesswork: a not-in-index ref downgrades
    to [INFO] only if it appears in `vendor_manifest` (the vendor-ref manifest the box ships,
    built at release time by tropo-build-release.py from the real outward-ref graph). A ref
    absent from BOTH the index AND the manifest is a real defect and still [FAIL]s loudly.
    If vendor_manifest is None (no manifest shipped, or it failed to load), customer_mode
    fails closed: every not-in-index ref [FAIL]s, because there is no data to classify by.
    Takes precedence over release_mode when both are set.

    Returns: (findings, n_checked, n_defects)
      - findings: per-defect [FAIL] lines + index-stale [INFO] lines + parse [WARN] lines
      - n_checked: number of vault/files/*.md entries successfully parsed
      - n_defects: number of REAL FAIL defects (excludes [INFO] index-stale + [WARN]);
                   always 0 in release_mode (outward-refs downgraded to INFO)
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
            elif customer_mode:
                # S1 (v1.80 re-build): classify by the shipped vendor-ref manifest — data,
                # not guesswork. A missing/unusable manifest fails closed (no free pass).
                if vendor_manifest is not None and uid_value in vendor_manifest:
                    findings.append(
                        f'[INFO] vault/files/{f.name} — field `{path_str}` references '
                        f'{uid_value} (vendor outward-ref; in shipped manifest — expected)')
                    n_stale += 1
                else:
                    findings.append(
                        f'[FAIL] vault/files/{f.name} — field `{path_str}` references '
                        f'{uid_value} (not in index; not in vendor-ref manifest)')
                    n_defects += 1
            elif release_mode:
                # Release subset: a ref to a UID not in the (subset) index is an
                # expected outward-ref to a non-shipped studio-internal file (or a
                # kernel UID not vault-indexed). Safe by construction — the pre-build
                # full-studio pass (0 FAILED) guarantees no genuine broken refs exist.
                # (Dev-spec f8b51f4d D1.)
                findings.append(
                    f'[INFO] vault/files/{f.name} — field `{path_str}` references '
                    f'{uid_value} (outward-ref; not in release subset index — expected)')
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

    Compares `.tropo/version.md` declared version against the latest SHIPPED Tropo-OS
    release entry. Filter: `type:release AND status:shipped AND 'cd1fcd25' in member_of`
    (dev-pipeline membership; excludes user-content releases per spec §3.2 v0.2
    discriminator absorbing skeptic-075 P0-3).

    Argus A118 2026-06-21 — two coupled fixes:
    1. Parse bare `v?MAJOR.MINOR.PATCH` format (version.md is bare `v1.73.0`, not
       `**Current:** v1.73.0`); tolerate both forms.
    2. Compare against highest status:shipped release (not state:active — ALL releases
       have state:active, so the old filter picked the in-flight pre-ship entry as
       "highest active", making version.md = next-version a false pass pre-ship).
       The semantic: version.md = last shipped; advances to next only after ship.

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

    # Accept both `**Current:** v1.73.0` (legacy) and bare `v1.73.0` (current on-disk format).
    m = re.search(r'^\*\*Current:\*\*\s*v([\d.]+)', version_text, re.MULTILINE)
    if not m:
        m = re.search(r'^v?(\d+\.\d+\.\d+)', version_text.strip())
    if not m:
        findings.append('[INFO] .tropo/version.md — version not found in expected format; SKIP')
        return findings, 0, 0
    declared_version = m.group(1)

    index_path = vault / 'vault' / '00-index.jsonl'
    if not index_path.is_file():
        findings.append('[WARN] vault/00-index.jsonl — not found; cannot verify version consistency')
        return findings, 1, 0

    conforming: list[tuple[str, str]] = []
    malformed: list[str] = []
    # release_version allows optional leading 'v' (e.g. `v1.73.0` or `1.73.0`).
    semver_re = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)$')

    for row in _index_union(vault):
        if row.get('type') != 'release':
            continue
        # Filter to shipped releases only. state:active is set on ALL releases
        # (rolling-window not enforced in data), so using state:active as the
        # discriminator picks the in-flight pre-ship entry as "highest active"
        # and masks genuine drift. status:shipped = genuinely landed.
        if row.get('status') != 'shipped':
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
        if not isinstance(release_version, str):
            malformed.append(f'{uid}: release_version "{release_version}" non-conforming (expected MAJOR.MINOR.PATCH)')
            continue
        rv_m = semver_re.match(release_version)
        if not rv_m:
            malformed.append(f'{uid}: release_version "{release_version}" non-conforming (expected MAJOR.MINOR.PATCH)')
            continue
        # Normalise: strip leading 'v' so sort/compare work on plain semver strings.
        conforming.append((uid, f'{rv_m.group(1)}.{rv_m.group(2)}.{rv_m.group(3)}'))

    if not conforming:
        findings.append('[WARN] no shipped Tropo-OS release entry in vault (first cycle OR substrate-staleness)')
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

    # Compare declared vs highest shipped
    if declared_version != highest_version:
        findings.append(
            f'[WARN] version drift: .tropo/version.md declares v{declared_version} '
            f'≠ latest shipped Tropo-OS release v{highest_version} ({highest_uid})'
        )
        findings.append(
            '         Fix: set .tropo/version.md to the last shipped version OR '
            'mark the unexpected release entry as shipped per v1.21.0.1 governance.'
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
    """v1.5 inbox 656c26d0 — blocked-task parity check.

    Re-pointed 2026-07-14 (vault/files/66b6f3e8.md; Argus A130 ruling, event
    00006330). `vault/00-integrity.json` was retired: frozen since 2026-06-04
    with no writer anywhere in the repo. This check originally compared that
    file's self-reported `blocked_tasks.count` against the length of its own
    `blocked_tasks.uids` array — both fields written by the same dead TS
    rebuilder, so they could silently drift from each other
    (sa.daily-vault-health surfaced exactly that on 2026-05-03: count 62 vs
    42 UIDs).

    The live truth surfaces (per the same ruling) are `vault/00-index.jsonl`
    and `vault/00-index.sqlite` — both written in the same pass by
    tropo-rebuild-index.py (build_sqlite_index / freshen_one share one
    row-computation path), so they should never structurally disagree.
    Re-pointed check: independently derive the set of type:task
    status:blocked UIDs from each surface and flag any mismatch. Same
    drift-detection intent as the original (two representations of one fact
    falling out of sync), now checked against live data instead of an
    orphaned cached report — and a real defect (a rebuild that only
    half-completed) rather than a tautology, since jsonl and sqlite are
    independently queried here, not cross-derived from each other.
    """
    findings: list[str] = []
    index_path = vault / 'vault' / '00-index.jsonl'
    sqlite_path = vault / 'vault' / '00-index.sqlite'

    if not index_path.is_file():
        return [f'[INFO] vault/00-index.jsonl — not present (skip blocked-task parity check)'], True
    if not sqlite_path.is_file():
        return [f'[INFO] vault/00-index.sqlite — not present (skip blocked-task parity check)'], True

    jsonl_blocked: set[str] = {
        rec['uid']
        for rec in _index_union(vault)
        if rec.get('type') == 'task'
        and rec.get('status') == 'blocked'
        and rec.get('uid')
    }

    import sqlite3 as _sq3
    try:
        conn = _sq3.connect(str(sqlite_path))
        try:
            rows = conn.execute(
                "SELECT uid FROM entries WHERE type = 'task' AND status = 'blocked'"
            ).fetchall()
        finally:
            conn.close()
    except _sq3.Error as e:
        return [f'[WARN] vault/00-index.sqlite — query failed: {e}'], False
    sqlite_blocked = {row[0] for row in rows}

    if jsonl_blocked != sqlite_blocked:
        only_jsonl = sorted(jsonl_blocked - sqlite_blocked)
        only_sqlite = sorted(sqlite_blocked - jsonl_blocked)
        detail_bits = []
        if only_jsonl:
            preview = ', '.join(only_jsonl[:5]) + ('…' if len(only_jsonl) > 5 else '')
            detail_bits.append(f'{len(only_jsonl)} only in jsonl ({preview})')
        if only_sqlite:
            preview = ', '.join(only_sqlite[:5]) + ('…' if len(only_sqlite) > 5 else '')
            detail_bits.append(f'{len(only_sqlite)} only in sqlite ({preview})')
        findings.append(
            f'[WARN] blocked-task parity — current+archive JSONL union has {len(jsonl_blocked)} status:blocked '
            f'task(s), vault/00-index.sqlite has {len(sqlite_blocked)}; drift: {"; ".join(detail_bits)} '
            f'(run npm run vault:rebuild to resync; v1.5 inbox 656c26d0, re-pointed per 66b6f3e8)'
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
    for subdir in ('vault/capsules', '.tropo/playbooks', '.tropo/skills'):
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
        # Exempt template/example activations from the required-field check.
        # agent_name: "example" is the shipped starter template (d4e6f829);
        # it's intentionally incomplete — exempting avoids false FAIL on a
        # shipped educational resource. Argus A118 2026-06-21.
        if get_scalar(fm, 'agent_name') == 'example':
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


def check_pipeline_root_terminal_closure(vault: Path) -> tuple[list[str], int, int]:
    """v3.4 / v1.90 pipeline.capsule Rule 12 terminal-invariant check (dev-spec c392d833).

    The CLOSING mirror of Rule 10's step-0 authoring invariant: every pipeline
    activation root MUST reach state:archived + final_commit at ship/close. This
    check flags a SHIPPED/COMPLETED cycle whose activation root is still
    state:active — the exact defect metis-g91 diagnosed (task 1d689277: 93 roots
    stuck state:active studio-wide; dev 81% closed / test 17% / doc 9%).

    An activation root is a type:project entry whose title contains 'Activation
    Root' OR which carries activated_by_pipeline: (the pipeline-activate.py marker
    written by e337f1dd.py author_activation_root_project). A root is TERMINAL
    when status ∈ {done, retired, closed, complete, cancelled}. An in-flight root
    (status:active) is NOT flagged — parallel cycles stay legal (Mike-A94
    concurrency_model:independent); closing is per-root at its own ship, never a
    global gate.

    WARN-severity at v1.90 (ratchets to ERROR later, the Check 19/20 WARN→ERROR
    lifecycle): shipped WARN so it cannot red-light a concurrent cycle's validate
    while the weld (run_close_out_hook + build-release ship path) remediates the
    field forward. tropo-sweep-stale-roots.py (metis-g91) is the backstop.

    Returns (findings, total_roots, violations).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    TERMINAL = {"done", "retired", "closed", "complete", "cancelled"}
    total_roots = 0
    violations = 0

    for f in files_dir.glob('*.md'):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm = split_frontmatter(text)
        if fm is None:
            continue
        if get_scalar(fm, 'type') != 'project':
            continue
        title = get_scalar(fm, 'title') or ''
        is_root = ('Activation Root' in title) or (get_scalar(fm, 'activated_by_pipeline') is not None)
        if not is_root:
            continue
        total_roots += 1
        status = (get_scalar(fm, 'status') or '').lower()
        state = (get_scalar(fm, 'state') or '').lower()
        if status in TERMINAL and state == 'active':
            final_commit = get_scalar(fm, 'final_commit')
            missing = 'state:active' + ('' if final_commit else ' + no final_commit')
            findings.append(
                f'[WARN] vault/files/{f.name} — activation root status:{status} but {missing} '
                f'(pipeline.capsule Rule 12 terminal-closure: a shipped/completed cycle MUST reach '
                f'state:archived + final_commit). Primary writer: run_close_out_hook on the '
                f'tropo-build-release.py ship path; backstop: tropo-sweep-stale-roots.py.'
            )
            violations += 1

    return findings, total_roots, violations


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
    """Verify discrete v3 memory entries per memory.capsule v1.6.

    Sweeps:
      agents/<slug>/.tropo-capsule/memory/entries/*.md   (per-agent memory)
      .tropo-studio/memory/entries/*.md                   (vault-level memory)
      vault/files/<uid>.md where type=memory             (typed primitive in main vault)

    Surfaces violations at WARN severity at v1.26.0 (grace period; ratchet to ERROR
    in later cycle once substrate has settled per Stream 0 migration).

    Checks per entry:
      1. Required-field presence: subtype, scope, context + markdown body
      2. Enum compliance: subtype ∈ {semantic,episodic,procedural,reference,feedback};
         scope ∈ {agent,studio,doctrine}; tier ∈ {stm,current,topic,archival,demoted}
      3. score: float in [0.0, 1.0] if set
      4. context: ≤ 120 chars if set
      5. (v1.6, dev-spec 47c26a60) reinforcement_count is a non-negative integer if set;
         reinforced_by is a list of well-formed generation labels if set (Check 8)
      6. (v1.6) curator-mutable-field discipline: a memory entry carrying any of
         last_referenced/reference_count/score/tier/reinforcement_count/reinforced_by
         whose modified_by is a non-curator writer (not sa.memory-curator/argus) surfaces
         a WARN — the same finding class for all curator-mutable fields (Check 7)

    Citation resolution (refs:) deferred to sa.memory-curator's verification-before-use
    pass at boot — not the validator's job.

    Silently skips entries directories that don't exist yet (Stream 0 may not have
    populated them at validator run-time; absence is not failure).

    Returns (findings, total_checked, defects). Capsule UID a5b3c891.
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    valid_subtypes = {'semantic', 'episodic', 'procedural', 'reference', 'feedback'}
    valid_scopes = {'agent', 'studio', 'doctrine'}
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
            vault, f, fm, valid_subtypes, valid_scopes, valid_tiers, findings,
        )
        if not _memory_markdown_body(text):
            findings.append(f'[WARN] {f.relative_to(vault)} — memory entry has no markdown body content (memory.capsule v1.5 §Entry Shape)')
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
                findings.append(f'[WARN] {f.relative_to(vault)} — memory entry missing frontmatter (memory.capsule v1.5 §Entry Shape)')
                defects += 1
                continue
            _validate_memory_frontmatter(
                vault, f, fm, valid_subtypes, valid_scopes, valid_tiers, findings,
            )
            if not _memory_markdown_body(text):
                findings.append(f'[WARN] {f.relative_to(vault)} — memory entry has no markdown body content (memory.capsule v1.5 §Entry Shape)')

    # Count defects from findings list
    defects = sum(1 for line in findings if line.startswith('[WARN]') or line.startswith('[FAIL]'))

    return findings, total_checked, defects


def _memory_markdown_body(text: str) -> str:
    match = FRONTMATTER_RE.match(text)
    return text[match.end():].strip() if match else ""


def _validate_memory_frontmatter(
    vault: Path,
    path: Path,
    fm: dict,
    valid_subtypes: set,
    valid_scopes: set,
    valid_tiers: set,
    findings: list,
) -> None:
    """Validate one memory entry's v1.5 frontmatter.

    Mutates findings in place per memory.capsule v1.5 §Validation Checks.
    All violations are WARN at v1.26.0 (grace period).
    """
    rel = path.relative_to(vault)

    # Required fields
    for required in ('subtype', 'scope', 'context'):
        if not get_scalar(fm, required):
            findings.append(f'[WARN] {rel} — memory entry missing required field {required!r} (memory.capsule v1.5 §Entry Shape)')

    # Enum compliance
    subtype = get_scalar(fm, 'subtype')
    if subtype and subtype not in valid_subtypes:
        findings.append(f'[WARN] {rel} — subtype {subtype!r} not in {sorted(valid_subtypes)} (memory.capsule v1.5 §Subtypes)')

    scope = get_scalar(fm, 'scope')
    if scope and scope not in valid_scopes:
        findings.append(f'[WARN] {rel} — scope {scope!r} not in {sorted(valid_scopes)} (memory.capsule v1.5 §Scope)')

    retention = get_scalar(fm, 'retention')
    if retention and retention not in valid_tiers:
        findings.append(f'[WARN] {rel} — retention {retention!r} not in {sorted(valid_tiers)} (memory.capsule v1.5 §State Machine)')

    # Score range
    score_raw = get_scalar(fm, 'score')
    if score_raw is not None:
        try:
            score_val = float(score_raw)
            if score_val < 0.0 or score_val > 1.0:
                findings.append(f'[WARN] {rel} — score {score_val} outside [0.0, 1.0] range (memory.capsule v1.5 §Validation Check 4)')
        except (TypeError, ValueError):
            findings.append(f'[WARN] {rel} — score {score_raw!r} not a valid float (memory.capsule v1.5 §Validation Check 4)')

    # Context length
    context = get_scalar(fm, 'context')
    if context and len(context) > 120:
        findings.append(f'[WARN] {rel} — context length {len(context)} > 120 chars (memory.capsule v1.5 §Validation Check 5)')

    # Reinforcement fields well-formedness (memory.capsule v1.6 §Validation Check 8; dev-spec 47c26a60)
    rc_raw = get_scalar(fm, 'reinforcement_count')
    if rc_raw is not None and rc_raw.strip() != '':
        # Non-negative integer only: reject signs, decimals, and non-digits.
        if not re.fullmatch(r'\d+', rc_raw.strip()):
            findings.append(
                f'[WARN] {rel} — reinforcement_count {rc_raw!r} must be a non-negative integer '
                f'(memory.capsule v1.6 §Validation Check 8)'
            )

    reinforced_by = get_list(fm, 'reinforced_by')
    if reinforced_by is not None:
        if any(isinstance(e, str) and e.startswith('__scalar__:') for e in reinforced_by):
            findings.append(
                f'[WARN] {rel} — reinforced_by must be a list of generation labels, not a scalar '
                f'(memory.capsule v1.6 §Validation Check 8)'
            )
        else:
            malformed = [
                e for e in reinforced_by
                if (not isinstance(e, str))
                or (not e.strip())
                or (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', e.strip()))
            ]
            if malformed:
                findings.append(
                    f'[WARN] {rel} — reinforced_by contains malformed generation label(s) {malformed!r} '
                    f'(memory.capsule v1.6 §Validation Check 8 — expect non-empty tokens like A115)'
                )

    # Curator-mutable field discipline (memory.capsule v1.6 §Validation Check 7).
    # reinforcement_count + reinforced_by join score/tier/reference_count/last_referenced:
    # a non-curator write surfaces the same WARN finding class (dev-spec 47c26a60 §Design.4).
    curator_mutable_fields = (
        'last_referenced', 'reference_count', 'score', 'tier',
        'reinforcement_count', 'reinforced_by',
    )
    present_curator_fields = [
        name for name in curator_mutable_fields if get_scalar(fm, name) is not None
    ]
    modified_by = get_scalar(fm, 'modified_by')
    if (
        present_curator_fields
        and modified_by
        and not any(writer in modified_by for writer in ('sa.memory-curator', 'argus'))
    ):
        findings.append(
            f'[WARN] {rel} — curator-mutable field(s) {present_curator_fields} present but '
            f'modified_by={modified_by!r} is not sa.memory-curator/argus '
            f'(memory.capsule v1.6 §Validation Check 7 curator-mutable-field discipline)'
        )


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


def check_loop_registry_fields(vault: Path) -> tuple[list[str], int, int]:
    """loop.capsule v1.3 (1248583d) §7 Check 8 — ERROR-ratchet (Talos, v1.80 S11:
    the recording hook, `vault/tools/loop_run_cost_recorder.py`, has landed, so
    the capsule's WARN->ERROR ratchet condition is satisfied).

    For any `type: loop` entry with `cadence:` declared (registry-dispatched
    per boot-fast-path §5.1.7):
      - `consent_mode` and `runner` must be present.
      - `last_run` must parse as a date or a bare YAML null — the string
        `"null"` is a finding (the exact typing-contract bug this rider
        cures in the recorder).
      - `last_run_cost`, when present, must have `tokens`/`wall_min`/`usd_est`
        members that are each numeric or null; if any of those three carries
        a measured (non-null) figure, `recorded_by` must be present too — a
        cost figure with no provenance stamp looks fabricated.

    Returns (findings, total_checked, fails) — fails == len(findings) (all ERROR).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    total_checked = 0
    for f in sorted(files_dir.glob('*.md')):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        if get_scalar(fm_text, 'type') != 'loop':
            continue
        cadence = get_scalar(fm_text, 'cadence')
        if not cadence:
            continue  # not registry-dispatched at boot; these fields aren't required

        total_checked += 1
        uid = get_scalar(fm_text, 'uid') or f.stem
        consent_mode = get_scalar(fm_text, 'consent_mode')
        runner = get_scalar(fm_text, 'runner')
        if not consent_mode:
            findings.append(
                f'[ERROR] vault/files/{f.name} — loop {uid} declares cadence:{cadence} '
                f'but consent_mode is missing (loop.capsule v1.3 §7 Check 8).'
            )
        if not runner:
            findings.append(
                f'[ERROR] vault/files/{f.name} — loop {uid} declares cadence:{cadence} '
                f'but runner is missing (loop.capsule v1.3 §7 Check 8).'
            )

        # last_run typing: date-or-bare-null, never the string "null" (raw-text check —
        # a real quoted-string "null" is exactly what a naive stamp bug would write).
        m_lr = re.search(r'^last_run:\s*(.*)$', fm_text, re.MULTILINE)
        if m_lr is not None:
            raw_lr = m_lr.group(1).strip()
            if raw_lr in ('"null"', "'null'"):
                findings.append(
                    f'[ERROR] vault/files/{f.name} — loop {uid} last_run is the STRING "null" '
                    f'— the typing contract is date-or-bare-YAML-null, never the string \'null\' '
                    f'(loop.capsule v1.3 §7 Check 8).'
                )
            elif raw_lr in ('', 'null', '~'):
                pass  # honest bare null / absent
            else:
                unquoted = raw_lr.strip('"\'')
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', unquoted):
                    findings.append(
                        f'[ERROR] vault/files/{f.name} — loop {uid} last_run={raw_lr!r} does not '
                        f'parse as a date or bare YAML null (loop.capsule v1.3 §7 Check 8).'
                    )

        # last_run_cost: numeric-or-null members; a measured figure with no recorded_by
        # is a fabrication smell (loop.capsule v1.3 §2 last_run_cost + §7 Check 8).
        if 'last_run_cost:' in fm_text:
            try:
                parsed = yaml.safe_load(fm_text) or {}
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                lrc = parsed.get('last_run_cost')
                if isinstance(lrc, dict):
                    for numeric_field in ('tokens', 'wall_min', 'usd_est'):
                        v = lrc.get(numeric_field)
                        if v is not None and not isinstance(v, (int, float)):
                            findings.append(
                                f'[ERROR] vault/files/{f.name} — loop {uid} last_run_cost.{numeric_field}='
                                f'{v!r} is neither numeric nor null (loop.capsule v1.3 §7 Check 8).'
                            )
                    has_measured = any(
                        isinstance(lrc.get(k), (int, float)) for k in ('tokens', 'wall_min', 'usd_est')
                    )
                    if has_measured and not lrc.get('recorded_by'):
                        findings.append(
                            f'[ERROR] vault/files/{f.name} — loop {uid} last_run_cost has a measured '
                            f'figure but recorded_by is absent — fabricated-looking value '
                            f'(loop.capsule v1.3 §7 Check 8).'
                        )

    return findings, total_checked, len(findings)


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


def check_step_completion_has_verification(vault: Path, thorough: bool = False) -> tuple[list[str], int, int]:
    """v1.46.0 — pipeline-run.capsule v2.0 §Validation Check 14 (MUST-SHIP).

    For every step_completed event in a v2.0-shape run.jsonl, a matching
    verification_receipt with verdict:pass for that step must also exist.
    ERROR severity.

    Verification-class steps (pipeline definition declares verification_class: true)
    bypass this check; their step_completed.data carries the natural verdict
    (build exit code / HTTP status / validator pass-fail) and that is sufficient.

    Only fires on v2.0-shape runs (those whose run.jsonl contains an
    activation_contract_locked event). Pre-v2.0 runs are skipped.

    Governed Autonomy S1 (ef65fccd) rewrite — provenance + spot re-derivation:
    presence of a verification_receipt:verdict:pass event was ALWAYS the whole check;
    a receipt is just a JSONL line, and nothing here distinguished one the engine wrote
    from executing a real command from one hand-appended to the file by anything with
    write access. This is the exact class Argus A129 exploited on his own retirement
    close-gate (f67fe144) and the general shape the dev-spec names: "check
    check_step_completion_has_verification passes on an agent-authored verdict:pass
    receipt." Two additions, both fail-closed, neither weakens the baseline check above:

    1. PROVENANCE (always-on, no flag): a passing receipt that carries a `command` in
       its forensics (engine-written per 9e7003b1.py's _run_verification_command, S1)
       is a genuine engine-executed receipt. A receipt with NO forensics at all is only
       legitimate for the narrow set of steps that never had a command to run in the
       first place (verification_class:false auto-receipts, trigger-step's own
       substrate-write receipt) — those are distinguishable by verifier_role_resolved
       ('same-as-executor' with empty per_criterion, or a hardcoded trigger-step shape),
       not by absence alone. A receipt claiming verifier_role_resolved:
       'verification_command' WITHOUT forensics is flagged — that combination should be
       structurally impossible post-S1 and its presence means either a pre-S1 legacy
       receipt (INFO, grandfathered) or a forged one (FAIL).
    2. SPOT RE-DERIVATION (--thorough only, per S1 acceptance criterion 5): for a
       passing receipt that DOES carry forensics, re-run the recorded `command` in the
       recorded `cwd` and compare the resulting exit_code AND output_sha256 against
       what's recorded. A mismatch means either genuine drift (the underlying substrate
       changed since the receipt was minted — worth knowing) or a tampered receipt
       (worth knowing more urgently) — this check cannot tell the two apart and does not
       try to; it reports the mismatch and lets a human classify it, same posture as
       release_authorization.py's own re-run comparison for the pipeline-activation key.
       Off by default (real command re-execution is not something a routine validator
       pass should do silently) — pass thorough=True / --thorough explicitly.

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
            passing_receipts = [
                e for e in step_evs
                if e.get('event') == 'verification_receipt'
                and (e.get('data') or {}).get('verdict') == 'pass'
            ]
            if not passing_receipts:
                try:
                    rel_jsonl = jsonl_path.relative_to(vault)
                except ValueError:
                    rel_jsonl = jsonl_path
                findings.append(
                    f'[FAIL] {rel_jsonl} — step {step_uid!r} has step_completed event without a matching '
                    f'verification_receipt:verdict:pass; pipeline-run.capsule v2.0 §Check 14.'
                )
                defects += 1
                continue

            # S1 provenance + spot re-derivation (both operate on the LATEST passing
            # receipt — a step may accumulate several across re-verify cycles).
            try:
                rel_jsonl = jsonl_path.relative_to(vault)
            except ValueError:
                rel_jsonl = jsonl_path
            receipt_data = passing_receipts[-1].get('data') or {}
            forensics = receipt_data.get('forensics') or {}
            verifier_role = receipt_data.get('verifier_role_resolved')

            if not forensics:
                if verifier_role == 'verification_command':
                    findings.append(
                        f'[FAIL] {rel_jsonl} — step {step_uid!r} receipt claims '
                        f"verifier_role_resolved:'verification_command' but carries no forensics "
                        f'(command/exit_code/output_sha256) — structurally impossible post-S1; '
                        f'either a pre-S1 legacy receipt masquerading as command-verified, or a '
                        f'forged receipt (ef65fccd provenance check).'
                    )
                    defects += 1
                # else: no forensics + no verification_command claim — a legitimate
                # no-command receipt shape (verification_class:false auto-receipt,
                # trigger-step's substrate-write receipt). Nothing to flag.
                continue

            if thorough:
                command = forensics.get('command')
                cwd = forensics.get('cwd') or str(vault)
                recorded_exit = forensics.get('exit_code')
                recorded_hash = forensics.get('output_sha256')
                if command:
                    try:
                        import shlex as _shlex_tv
                        import hashlib as _hashlib_tv
                        _parts = _shlex_tv.split(str(command))
                        _argv = ([sys.executable] + _parts) if _parts and _parts[0].endswith('.py') else _parts
                        _result = subprocess.run(_argv, capture_output=True, text=True,
                                                 timeout=120, cwd=cwd)
                        _live_output = (_result.stdout or '') + (_result.stderr or '')
                        _live_hash = _hashlib_tv.sha256(_live_output.encode('utf-8', 'replace')).hexdigest()
                        _mismatch = []
                        if _result.returncode != recorded_exit:
                            _mismatch.append(f'exit_code recorded={recorded_exit!r} live={_result.returncode!r}')
                        if _live_hash != recorded_hash:
                            _mismatch.append('output_sha256 mismatch (output changed since receipt was minted)')
                        if _mismatch:
                            findings.append(
                                f'[FAIL] {rel_jsonl} — step {step_uid!r} SPOT RE-DERIVATION mismatch: '
                                f'{"; ".join(_mismatch)} — command {command!r} no longer reproduces its '
                                f'recorded receipt (drift or tamper; ef65fccd acceptance criterion 5).'
                            )
                            defects += 1
                    except Exception as _e:
                        findings.append(
                            f'[FAIL] {rel_jsonl} — step {step_uid!r} SPOT RE-DERIVATION could not re-run '
                            f'recorded command {command!r}: {_e} — a receipt whose command can no longer '
                            f'even execute is not re-derivable evidence.'
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

    # Inline-sync applies to the union: an archived working copy remains
    # indexed on the opt-in ADR-047 history surface.
    index_uids = _index_union_uids(vault)

    for path, fm in _walk_working_copies(vault):
        checked += 1
        wc_uid = get_scalar(fm, 'uid')
        if not wc_uid:
            continue  # check_working_copy_schema already flagged
        if wc_uid not in index_uids:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — working-copy uid={wc_uid!r} not in current/archive index union; '
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

    index_uids = _index_union_uids(vault)

    for path, fm in _walk_external_artifacts(vault):
        checked += 1
        proj_uid = get_scalar(fm, 'uid')
        if not proj_uid:
            continue
        if proj_uid not in index_uids:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — external-artifact projection uid={proj_uid!r} not in current/archive index union; '
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

    index_uids = _index_union_uids(vault)

    for path, fm in _walk_folder_mirrors(vault):
        checked += 1
        uid = get_scalar(fm, 'uid')
        if not uid:
            continue
        if uid not in index_uids:
            findings.append(
                f'[FAIL] {path.relative_to(vault)} — folder mirror uid={uid!r} not in current/archive index union; '
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


def check_navblock_git_filter_installed(vault: Path) -> tuple[list[str], int, int]:
    """Dev-spec 6ec30708 AC5 (I5 dd16c90c, Option A) — the nav-block git clean filter
    must be DETECTED as missing, not silently absent. Same failure class as a missing
    D2 field-aware merge driver (vault/tools/federation/README.md): `.gitattributes`
    alone never carries the actual filter COMMAND — the LOCAL, never-committed
    `.git/config` is a second, separate install step every fresh clone/studio needs.

    Two independent halves, BOTH required to pass:
      1. `.gitattributes` declares `vault/files/*.md filter=navblockstrip`.
      2. This clone's local `git config --get filter.navblockstrip.process` is set,
         and the superseded `.clean` spawn-per-file wiring is NOT.

    A vault with no `.git` at all (not yet on Git Beat 1, 98b9610a) is a skip-class,
    not a defect — there is nothing to install a filter INTO yet.

    Returns (findings, checked_count, defect_count). checked_count is always 1 (a
    single studio-wide mechanism, not a per-file check) so callers can report a
    stable "N checked" line consistent with the vault's other check functions.
    """
    if not (vault / '.git').exists():
        return [], 0, 0

    findings: list[str] = []
    checked = 1
    defects = 0

    ga_ok = False
    ga_path = vault / '.gitattributes'
    if ga_path.is_file():
        try:
            for line in ga_path.read_text(encoding='utf-8', errors='replace').splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[0] == 'vault/files/*.md' and 'filter=navblockstrip' in parts[1:]:
                    ga_ok = True
                    break
        except OSError:
            pass

    def _cfg(key: str) -> bool:
        try:
            r = subprocess.run(
                ['git', 'config', '--get', key],
                cwd=str(vault), capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0 and bool(r.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            return False

    cfg_ok = _cfg('filter.navblockstrip.process')
    stale_clean = _cfg('filter.navblockstrip.clean')

    if not ga_ok:
        findings.append(
            "  .gitattributes does not declare 'vault/files/*.md filter=navblockstrip' — "
            "the I5 (dd16c90c) nav-block clean-strip is not declared at all (6ec30708 AC5)."
        )
        defects += 1
    if not cfg_ok:
        findings.append(
            "  git config filter.navblockstrip.process is not set in this clone's LOCAL "
            ".git/config (never committed) — run `python3 vault/tools/tropo-navblock-strip.py "
            "--install`. A studio without this can silently commit nav-blocks into a shared "
            "segment and reintroduce the merge-storm (6ec30708 AC5)."
        )
        defects += 1
    if stale_clean:
        findings.append(
            "  git config filter.navblockstrip.clean is STILL wired in this clone — the "
            "superseded spawn-per-file shell-out (~53ms of interpreter startup per file; "
            "~3.1 min per git add/status after a full rebuild, vs 6.4s). git prefers "
            "`process` when both are set, so this changes nothing observable and will sit "
            "here looking correct — re-run `python3 vault/tools/tropo-navblock-strip.py "
            "--install`, which wires `process` and removes it (6ec30708 line 113)."
        )
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

    Walks vault/files/*.md, playbooks, tools, agents, and skills; uses
    _yaml_dup_lib.detect_duplicate_yaml_keys() as the canonical detection.

    Detection scope: top-level YAML keys ONLY.

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

    scan_targets = [
        ('vault/files', ['*.md']),
        ('vault/playbooks', ['*.md']),
        ('vault/tools', ['*.py', '*.md']),
        ('vault/agents', ['*.md']),
        ('vault/skills', ['*.md']),
    ]

    def get_yaml_body(filepath: Path, text: str) -> Optional[str]:
        ext = filepath.suffix.lower()
        if ext == '.py':
            lines = text.split('\n')
            i = 0
            while i < len(lines) and (lines[i].startswith('#') or not lines[i].strip()):
                i += 1
            rest = '\n'.join(lines[i:])
            m = re.match(r'^("""|\'\'\')(.*?)\1', rest, re.DOTALL)
            if not m:
                return None
            docstring_body = m.group(2)
            fm_match = re.search(r'---\n(.*?)\n---', docstring_body, re.DOTALL)
            if not fm_match:
                return None
            return fm_match.group(1)
        elif ext == '.md':
            parts = extract_frontmatter(text)
            if parts is None:
                return None
            return parts[1]
        return None

    for rel_dir, globs in scan_targets:
        target_dir = vault / rel_dir
        if not target_dir.is_dir():
            continue
        
        matched_files = []
        for glob_pat in globs:
            matched_files.extend(target_dir.glob(glob_pat))
            
        for filepath in sorted(matched_files):
            if not filepath.is_file():
                continue
            checked += 1
            try:
                text = filepath.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError):
                continue
            
            body = get_yaml_body(filepath, text)
            if body is None:
                continue
                
            duplicates = detect_duplicate_yaml_keys(body)
            if duplicates:
                defects += 1
                keys_summary = ', '.join(
                    f'{k} ({v}x)' for k, v in sorted(duplicates.items())
                )
                findings.append(
                    f'[FAIL] {filepath.relative_to(vault)} — duplicate top-level '
                    f'YAML key(s): {keys_summary}; '
                    f'recovery: python3 vault/tools/34fb726c.py --apply'
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
    """Scan vault/capsules/*.capsule.md; return ({type: {bucket: [values]}}, errors).

    LOADER-FIRST (3783a7cb Piece B): unrecognized shape ERRORs loudly.
    ADR-045 One Home (v1.76; e8d49d3a): canonical capsule home is vault/capsules/.
    """
    rollups: dict[str, dict[str, list[str]]] = {}
    errors: list[str] = []
    capsules_dir = vault / 'vault' / 'capsules'
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
        # ADR-045/048 One Home: shipped capsules carry the tropo- filename prefix
        # (tropo-document.capsule.md governs type 'document'). Strip the namespace
        # token or every rollup keys as 'tropo-<type>' and matches no entry type
        # (the 2026-07-01 M2-at-scale regression; argus-a122). Mirrors the same
        # fix in tropo-rebuild-index.py load_meta_status_rollups.
        if type_name.startswith('tropo-'):
            type_name = type_name[len('tropo-'):]

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
            if 'vault/tools/tropo-check-events.py' in rel or '2471edc0' in rel:
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
    capsules_dir = vault / 'vault' / 'capsules'
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
    capsules_dir = vault / 'vault' / 'capsules'
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

    capsules_dir = vault / 'vault' / 'capsules'

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

    # Step 1: resolve inbox set (entries whose title/name matches '01-inbox'
    # convention) across both ADR-047 surfaces.  Archived members are excluded
    # below exactly as before; loading the union preserves historical parent
    # resolution without polluting the default retrieval surface.
    inbox_uids: set[str] = set()
    all_entries: dict[str, dict] = {}
    for entry in _index_union(vault):
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
                    actual_src = body_sha256(src_path, strip_navblock=True)
                    if actual_src != expected_src:
                        findings.append(
                            f'[FAIL] {rel} — source {src["path"]} drifted; '
                            f'canonical changed since curation '
                            f'(actual: {actual_src[:8]}, recorded: {expected_src[:8]})'
                        )
                        defects += 1

    return findings, total_checked, defects


def check_spec_coverage_pairing(vault: Path) -> tuple[list[str], int, int]:
    """Use the test-spec family's single Rule 3.a/3.b implementation."""

    from lib.test_spec_validators import (  # local import preserves startup cost
        check_test_spec_cross_validation_against_dev_spec,
    )

    findings, total_checked, _ = (
        check_test_spec_cross_validation_against_dev_spec(vault)
    )
    defects = sum(
        finding.startswith(('[ERROR]', '[FAIL]')) for finding in findings
    )
    return findings, total_checked, defects


def check_test_spec_family(
    vault: Path,
    *,
    include_pairing: bool = True,
    include_behavior_floor: bool = True,
) -> tuple[list[str], int, int]:
    """Full-validator adapter for the same family check-one dispatches."""

    from lib.test_spec_validators import run_all_test_spec_checks

    return run_all_test_spec_checks(
        vault,
        include_pairing=include_pairing,
        include_behavior_floor=include_behavior_floor,
    )


def parse_version(v_str: str) -> list[int]:
    """v1.70 S3.5.2 — Robust version comparison for grandfathering."""
    if not v_str: return []
    import re
    return [int(c) for c in re.findall(r'\d+', v_str)]


# Warnings → Zero — grandfathered legacy cutoffs (c19fe1f4; v1.73 reclassify)
# Findings at or below these cutoffs are [INFO] named exemptions, not [WARN].
CHECK31_GRANDFATHER_MAX_EVENT_ID = "00000944"  # last root-UID emit, 2026-06-02; emit path fixed at v1.70
CHECK32_GRANDFATHER_MAX_RELEASE = "v1.70"       # completion-event requirement live from v1.70

# Gate 3 v2 floor — E4 reclassify (dev-spec 33be6147; b4f80d10 exempt-class E4)
# ADR-047 Layer-2 forward-pointer invariant introduced 2026-06-22 (dev-spec 8dce9aec, Argus A119).
# Items last substantively touched before this date are grandfathered [INFO]; post-cutoff → [WARN].
CHECK_AFP_LAYER2_GRANDFATHER_DATE = "2026-06-22"

# Gate 3 v1.75 — E5 reclassify (b4f80d10 exempt-class E5; Argus A121 00004857 Mike-approved).
# Undispositioned-backlog ratchet cut at v1.75 (2026-06-28). Items last touched before this date
# are grandfathered [INFO]; items modified on/after this date that go stale >45d → [WARN]/[ERROR].
CHECK_UDB_GRANDFATHER_DATE = "2026-06-28"


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

    # 2. Scan the canonical legacy-plus-stream union.
    for ev in _canonical_event_union(vault):
        total_checked += 1
        source = ev.get('source', '')
        source_uid = ev.get('source_uid')
        if source.startswith('/agents/') or source.startswith('//'):
            if source_uid in agent_roots:
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

    return findings, total_checked, defects


def check_completion_recording(vault: Path) -> tuple[list[str], int, int]:
    """Check 32 — terminal-state work-items must have a correlated completion event.

    Specified in 2fe61817 (LOCKED, emit-on-completion §S2.4).
    Detects "silent" closes (done without an event).

    Governed Autonomy S1 (ef65fccd) rewrite — world-state verification, not just
    correlation: the baseline check (below, unchanged) only proves an event with a
    matching correlationid EXISTS somewhere in the log — that is a claim, and the log
    is an appendable file anything with write access can append one more line to. Per
    Argus A130's design ("events verify against reality: terminal status, re-parent,
    correlation, fresh surfaces"):
      - terminal status: already the entry condition (state in done/archived) — unchanged.
      - correlation: already the baseline check — unchanged, kept as the FAIL case below.
      - re-parent: covered by the existing, separate check_inbox_transition (a terminal
        item still parented under an inbox is ITS finding, not duplicated here).
      - fresh surfaces (NEW): a correlated event is not enough on its own if the rest of
        the substrate never caught up — cross-check vault/00-index.jsonl has a row for
        this UID whose OWN state field agrees. A file claiming done, with a correlated
        event, whose index row is either MISSING or still shows a non-terminal state, is
        a real signal: either the index is stale (a "fresh surfaces" gap the write-path
        should have closed) or the completion event was manufactured without the write
        that should have accompanied genuine completion. Either way it is not silently
        trustworthy, so it downgrades from "verified complete" to a flagged INFO — it
        does not promote to FAIL on its own (index staleness has innocent causes, e.g. a
        rebuild that simply hasn't run yet), but it is no longer invisible.
    """
    findings: list[str] = []
    total_checked = 0
    defects = 0

    # 1. Map all completion events by correlationid
    completions: set[str] = set()
    for ev in _canonical_event_union(vault):
        if ev.get('type') not in ('tropo.message.replied', 'tropo.cycle.closed'):
            continue
        cid = ev.get('correlationid')
        if cid:
            completions.add(str(cid))

    # 1b. S1 fresh-surfaces: uid -> state as the INDEX currently sees it (may disagree
    # with the raw file if the index hasn't been refreshed since the file changed).
    index_state: dict[str, str] = {
        str(row['uid']): row.get('state')
        for row in _index_union(vault)
        if row.get('uid')
    }

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
                rel = f.relative_to(vault)

                # Check if this UID has a completion event
                if uid not in completions:
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
                    continue

                # S1 fresh-surfaces: the event correlates, but does the queryable index
                # row agree the item is genuinely terminal? A missing row or a
                # non-terminal index state means the completion isn't yet (or wasn't
                # ever) reflected outside this one file + one event line.
                idx_state = index_state.get(uid)
                if idx_state is None:
                    findings.append(
                        f'[INFO] {rel} — state:{state}, correlated event exists, but uid={uid!r} '
                        f'has NO row in the current/archive index union (fresh-surfaces gap; Check 32 S1 — '
                        f'the index has not caught up with this completion, or never will).'
                    )
                elif idx_state not in ('done', 'archived'):
                    findings.append(
                        f'[INFO] {rel} — state:{state}, correlated event exists, but the index row '
                        f'for uid={uid!r} shows state:{idx_state!r} (fresh-surfaces mismatch; Check 32 '
                        f'S1 — the index disagrees with the file about whether this is genuinely done).'
                    )
            except Exception: continue

    return findings, total_checked, defects


def check_identity_refs_resolve(vault: Path, release_mode: bool = False,
                                customer_mode: bool = False,
                                vendor_manifest: Optional[set[str]] = None) -> tuple[list[str], int, int]:
    """Check 35 — all UID-references in unified agent entries must resolve.

    Standing item 4 (fdb7821d). Verifies that unified cards don't carry dangling pointers.

    release_mode: when True, outward refs to UIDs not in the release subset are
    downgraded to [INFO] rather than [FAIL]. The pre-build full-studio pass (0 FAILED)
    guarantees no genuine broken refs exist; cross-boundary refs to non-shipped
    studio-internal UIDs (e.g. agent_root_uid → argo-reference project) are expected.
    Same pattern as check_uid_cross_references release_mode handling.

    customer_mode: v1.80 re-build (S1). Same manifest-based classification as
    check_uid_cross_references — a not-in-index ref downgrades to [INFO] only if it's
    in vendor_manifest; otherwise (including when vendor_manifest is None) it [FAIL]s.
    Takes precedence over release_mode when both are set.
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
    capsules_dir = vault / 'vault' / 'capsules'
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
                                if customer_mode:
                                    if vendor_manifest is not None and ref in vendor_manifest:
                                        findings.append(
                                            f'[INFO] {rel} — {field} {ref!r} vendor outward-ref; in shipped manifest — expected (Check 35 customer-mode)'
                                        )
                                    else:
                                        findings.append(
                                            f'[FAIL] {rel} — {field} {ref!r} does not resolve; not in vendor-ref manifest (Check 35; Standing Item 4)'
                                        )
                                        defects += 1
                                elif release_mode:
                                    findings.append(
                                        f'[INFO] {rel} — {field} {ref!r} outward-ref not in release subset (expected; Check 35 release-mode)'
                                    )
                                else:
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
# ADR-047 drift-prevention checks (dev-spec 8dce9aec; Argus A119 / Talos T21 2026-06-22)
# ---------------------------------------------------------------------------

# Types that are structural containers / definitions / records — not owned work-items.
# Matches the prototype's NONWORK set; governs undispositioned-backlog scope.
_NONWORK_TYPES = frozenset({
    'activation', 'agent', 'board-snapshot', 'build', 'collection-ref', 'how-to',
    'kb-article', 'pipeline', 'playbook', 'project', 'project-plan',
    'reconcile-report', 'registry', 'session-agent', 'ship-artifact',
    'subsystem-hub', 'tool', 'capsule-definition', 'document', 'release',
    'pipeline-run', 'release-plan',
})

_TERMINAL_STATUSES = frozenset({
    'closed', 'done', 'shipped', 'retired', 'superseded', 'complete',
    'immutable', 'locked', 'published', 'archived', 'cancelled',
    'deprecated', 'evergreen', 'tested',
})


def check_undispositioned_backlog(vault: Path, stale_days: int = 45) -> tuple[list[str], int, int]:
    """ADR-047 Component 2 — Undispositioned-stale backlog forcing function (dev-spec 8dce9aec).

    Flags owned work-items (non-NONWORK types) with non-terminal status AND modified
    older than stale_days. E5 grandfather (v1.75; 00004857 Mike-approved): items last
    touched before CHECK_UDB_GRANDFATHER_DATE are grandfathered [INFO]; post-cutoff stale
    items → [WARN] → ERROR (v1.75 ratchet).

    Returns (findings, total_checked, stale_count) — stale_count counts only post-cutoff items.
    """
    import datetime as _dt

    findings: list[str] = []
    info_findings: list[str] = []
    total_checked = 0
    stale_count = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    stale_cutoff = _dt.date.today() - _dt.timedelta(days=stale_days)
    grandfather_cutoff = _dt.date.fromisoformat(CHECK_UDB_GRANDFATHER_DATE)
    stale_by_owner: dict[str, list[str]] = {}

    for f in sorted(files_dir.glob('*.md')):
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

        entry_type = str(fm.get('type') or '')
        if entry_type in _NONWORK_TYPES:
            continue

        status = str(fm.get('status') or '').lower()
        state = str(fm.get('state') or '').lower()
        if status in _TERMINAL_STATUSES or state in ('archived', 'retired'):
            continue

        uid = str(fm.get('uid') or f.stem)
        modified_raw = fm.get('modified')
        if not modified_raw:
            continue
        try:
            if isinstance(modified_raw, _dt.date):
                modified_date = modified_raw
            else:
                modified_date = _dt.date.fromisoformat(str(modified_raw)[:10])
        except Exception:
            continue

        total_checked += 1
        if modified_date >= stale_cutoff:
            continue  # not stale yet

        owner = str(fm.get('owner') or fm.get('assigned_to') or 'unknown')
        title = str(fm.get('title') or '')[:60]
        age_days = (_dt.date.today() - modified_date).days

        # E5 grandfather: pre-cutoff items are named [INFO], not counted toward ERROR tally
        if modified_date < grandfather_cutoff:
            info_findings.append(
                f'{uid} [{entry_type}/{status or state}] "{title}" — {age_days}d stale '
                f'(owner: {owner}; modified {modified_date}; grandfathered E5 pre-{CHECK_UDB_GRANDFATHER_DATE})'
            )
        else:
            stale_by_owner.setdefault(owner, []).append(
                f'[WARN] {uid} [{entry_type}/{status or state}] "{title}" — {age_days}d stale (owner: {owner})'
            )
            stale_count += 1

    for owner_items in stale_by_owner.values():
        findings.extend(owner_items)

    # Prepend [INFO] block for grandfathered E5 entries (not counted toward ERROR tally)
    if info_findings:
        findings.insert(0,
            f'[INFO] {len(info_findings)} grandfathered pre-v1.75 undispositioned-stale item(s) '
            f'(modified < {CHECK_UDB_GRANDFATHER_DATE}; named exempt E5 per b4f80d10; '
            f'no action needed; going-forward ERROR branch active for post-cutoff):'
        )
        for item in info_findings[:10]:
            findings.insert(len([x for x in findings if x.startswith('[INFO]')]), f'  {item}')
        if len(info_findings) > 10:
            findings.append(f'  ... and {len(info_findings) - 10} more (all grandfathered E5)')

    return findings, total_checked, stale_count


def check_archived_forward_pointer(vault: Path) -> tuple[list[str], int, int]:
    """ADR-047 Component 3 — Layer-2 forward-pointer invariant (dev-spec 8dce9aec).

    Narrowed per Argus A121 (event 00004864; v1.75): only SUPERSESSIONS require a
    forward-pointer. A plain retirement (state:archived, no superseded_by, status!=superseded)
    legitimately has no successor and is excluded. Scope: status==superseded OR superseded_by
    field present (explicit supersession claim).

    E4 grandfather exemption (dev-spec 33be6147; b4f80d10 exempt-class list):
    Items last substantively touched before CHECK_AFP_LAYER2_GRANDFATHER_DATE (2026-06-22,
    when ADR-047 Layer-2 was introduced) are [INFO] named exemptions, not [ERROR].
    Post-cutoff superseded-without-pointer dead-ends → [ERROR] (v1.75 ratchet).

    Returns (findings, total_checked, defect_count).
    """
    findings: list[str] = []
    info_findings: list[str] = []
    total_checked = 0
    defect_count = 0

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, 0, 0

    # Load the index UID set once for index-aware forward-pointer resolution.
    # One-Home dirs (ADR-045) name files by convention (tropo-<name>.capsule.md,
    # <slug>-<uid>.py, etc.), NOT by UID — so filename-based resolution only
    # works for vault/files/. Capsules, tools, skills, etc. carry their UID in
    # frontmatter, indexed in 00-index.jsonl. Resolve via the index to catch
    # successors in any One-Home dir, not just vault/files/.
    known_uids = _index_union_uids(vault)

    for f in sorted(files_dir.glob('*.md')):
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

        state = str(fm.get('state') or '').lower()
        status = str(fm.get('status') or '').lower()
        has_superseded_by = bool(fm.get('superseded_by'))

        # Narrowed scope: only genuine supersessions require a forward-pointer.
        # Plain retirements (state:archived, no superseded_by, status!=superseded) are excluded —
        # they aged out legitimately and have no successor to point to.
        is_supersession = (status == 'superseded') or has_superseded_by
        if not is_supersession:
            continue

        total_checked += 1
        uid = str(fm.get('uid') or f.stem)
        title = str(fm.get('title') or '')[:50]

        # Forward-pointer candidates: superseded_by, current_truth
        fwd_uid = fm.get('superseded_by') or fm.get('current_truth')
        if not fwd_uid:
            # E4 grandfather check: was this item last touched before Layer-2 existed?
            modified = str(fm.get('modified') or fm.get('created') or '').strip()
            # Normalize: take the date portion only (handles "2026-05-01" and datetime forms)
            modified_date = modified[:10] if modified else ''
            if modified_date and modified_date < CHECK_AFP_LAYER2_GRANDFATHER_DATE:
                info_findings.append(
                    f'{uid} [{state or status}] "{title}" '
                    f'(modified {modified_date}; pre-Layer-2; grandfathered E4)'
                )
            else:
                findings.append(
                    f'[WARN] {uid} [{state or status}] "{title}" — no forward-pointer '
                    f'(superseded_by/current_truth absent; ADR-047 Layer-2; '
                    f'modified {modified_date or "unknown"})'
                )
                defect_count += 1
            continue

        # Verify it resolves — check all One-Home dirs (ADR-045; not just vault/files/).
        # Filename-based resolution works for vault/files/ (filename = UID), but capsules/
        # tools/skills/etc. name files by convention (tropo-<name>.capsule.md), carrying
        # the UID in frontmatter. Resolve via the index UID set (loaded above) as the
        # authoritative source, with filesystem fallback for robustness.
        _ONE_HOME_DIRS = ('files', 'agents', 'playbooks', 'tools', 'skills', 'templates',
                          'capsules', 'entities', 'actions', 'session-agents')
        resolved_in_index = str(fwd_uid) in known_uids
        resolved_on_disk = any(
            (vault / 'vault' / d / f'{fwd_uid}.md').is_file()
            for d in _ONE_HOME_DIRS
        )
        resolved = resolved_in_index or resolved_on_disk
        if not resolved:
            # Apply E4 grandfather to broken-resolver cases too (pre-cutoff cross-dir pointers
            # may predate the One-Home layout; they're honest, not defects).
            modified = str(fm.get('modified') or fm.get('created') or '').strip()
            modified_date = modified[:10] if modified else ''
            if modified_date and modified_date < CHECK_AFP_LAYER2_GRANDFATHER_DATE:
                info_findings.append(
                    f'{uid} [{state or status}] "{title}" — forward-pointer {fwd_uid!r} '
                    f'unresolved (pre-Layer-2 cross-dir; grandfathered E4; modified {modified_date})'
                )
            else:
                findings.append(
                    f'[WARN] {uid} [{state or status}] "{title}" — forward-pointer {fwd_uid!r} '
                    f'does not resolve in any One-Home dir (ADR-047 Layer-2; modified {modified_date or "unknown"})'
                )
                defect_count += 1

    # Prepend [INFO] block for grandfathered E4 entries (not counted toward warning tally)
    if info_findings:
        findings.insert(0,
            f'[INFO] {len(info_findings)} grandfathered pre-Layer-2 archived dead-end(s) '
            f'(modified < {CHECK_AFP_LAYER2_GRANDFATHER_DATE}; named exempt E4 per b4f80d10; '
            f'no action needed; going-forward FAIL branch active for post-cutoff):'
        )
        for item in info_findings[:5]:
            findings.insert(len([x for x in findings if x.startswith('[INFO]')]), f'  {item}')
        if len(info_findings) > 5:
            findings.append(
                f'  ... and {len(info_findings) - 5} more '
                f'(all modified < {CHECK_AFP_LAYER2_GRANDFATHER_DATE}; same E4 class)'
            )

    return findings, total_checked, defect_count


def check_no_two_homes(vault: Path) -> tuple[list[str], int, int]:
    """ADR-045 One Home enforcement — no governed file may exist in two homes.

    Scans vault/ content directories (files/, skills/, actions/, playbooks/,
    capsules/, templates/, tools/) and .tropo/ content directories (skills/,
    actions/, capsules/, templates/, playbooks/, and root .md files outside
    the bootstrap floor) for UID collisions. A UID appearing in both = violation.

    Also checks .py scripts: a UID-named .py in .tropo/scripts/ that also
    exists in vault/tools/ is a two-home script violation.

    Bootstrap floor files legitimately remaining in .tropo/ are excluded.
    ERROR ratchet since ADR-045 One Home (v1.76; e8d49d3a) — migration cycle closed.

    Returns (findings, total_checked, violation_count).
    """
    import re as _re

    UID_RE = _re.compile(r'^uid:\s*([0-9a-f]{8})\s*$', _re.MULTILINE)
    UID_STEM = _re.compile(r'^[0-9a-f]{8}$')

    BOOTSTRAP_FLOOR = frozenset({
        'boot-config.md', 'boot-digest.md', 'boot-fast-path.md', 'orientation.md',
        'SELF-HEALING.md', 'CAPSULE.md', 'TROPO-CONTROL.md', '00-index.md',
        'AGENTS.md', 'HUMAN-NAVIGATION.md', 'toolbelt.md', 'version.md',
        'tool-catalog.md', 'skill-catalog.md', 'sa-agent-catalog.md',
        'scheduled-agents.md', 'vocabulary', 'seed', 'system', 'definitions',
        'personas', 'concierge', 'schema', 'actions', 'boot-config',
    })

    findings: list[str] = []
    total_checked = 0
    violation_count = 0

    vault_root = vault.parent if (vault / 'files').is_dir() else vault
    vault_dir = vault_root / 'vault'
    tropo_dir = vault_root / '.tropo'

    # Collect vault/ UIDs
    vault_uids: dict[str, Path] = {}
    for subdir in ['files', 'skills', 'actions', 'playbooks', 'capsules', 'templates']:
        d = vault_dir / subdir
        if not d.is_dir():
            continue
        for f in sorted(d.glob('*.md')):
            try:
                text = f.read_text(errors='ignore')
            except Exception:
                continue
            m = UID_RE.search(text[:3000])
            if m:
                vault_uids[m.group(1)] = f

    # Collect vault/tools/ identities (.py) — UID from frontmatter + tropo- stem.
    # ADR-045/ADR-048: shipped tools renamed to tropo-<name>.py; UID_STEM.match(f.stem)
    # now matches zero shipped tools. Read uid from file content for all .py tools.
    vault_tool_uids: set[str] = set()   # canonical UIDs
    vault_tool_names: set[str] = set()  # tropo-<name> stems for name-based collision
    tools_dir = vault_dir / 'tools'
    if tools_dir.is_dir():
        for f in tools_dir.glob('*.py'):
            try:
                text = f.read_text(errors='ignore')
            except Exception:
                continue
            m = UID_RE.search(text[:3000])
            if m:
                vault_tool_uids.add(m.group(1))
            if f.stem.startswith('tropo-'):
                vault_tool_names.add(f.stem)

    # Scan .tropo/ content dirs for UIDs
    tropo_content_uids: dict[str, Path] = {}
    for subdir in ['skills', 'actions', 'capsules', 'templates', 'playbooks']:
        d = tropo_dir / subdir
        if not d.is_dir():
            continue
        for f in sorted(d.glob('*.md')):
            if f.name in BOOTSTRAP_FLOOR:
                continue
            try:
                text = f.read_text(errors='ignore')
            except Exception:
                continue
            m = UID_RE.search(text[:3000])
            if m:
                tropo_content_uids[m.group(1)] = f

    # .tropo/ root .md files outside bootstrap floor
    if tropo_dir.is_dir():
        for f in tropo_dir.glob('*.md'):
            if f.name in BOOTSTRAP_FLOOR:
                continue
            try:
                text = f.read_text(errors='ignore')
            except Exception:
                continue
            m = UID_RE.search(text[:3000])
            if m:
                tropo_content_uids[m.group(1)] = f

    # .tropo/scripts/ duplicates of vault/tools/ — matched by UID (from content) or tropo- name.
    # ADR-045: after rename, scripts are tropo-<name>.py; match on name collision or UID collision.
    tropo_scripts_dir = tropo_dir / 'scripts'
    script_violations: list[str] = []
    if tropo_scripts_dir.is_dir():
        for f in tropo_scripts_dir.glob('*.py'):
            identity = None
            # UID match: read uid from script content
            try:
                text = f.read_text(errors='ignore')
            except Exception:
                continue
            m = UID_RE.search(text[:3000])
            if m and m.group(1) in vault_tool_uids:
                identity = f'uid:{m.group(1)}'
            # Name match: tropo-<name>.py also exists in vault/tools/
            elif f.stem in vault_tool_names:
                identity = f'name:{f.stem}'
            # Legacy UID-stem match (pre-rename scripts)
            elif UID_STEM.match(f.stem) and f.stem in vault_tool_uids:
                identity = f'uid:{f.stem}'
            if identity:
                script_violations.append(f'{f.stem} ({identity})')

    total_checked = len(vault_uids) + len(tropo_content_uids) + len(vault_tool_uids) + len(vault_tool_names)

    for uid, tropo_path in sorted(tropo_content_uids.items()):
        if uid in vault_uids:
            vault_path = vault_uids[uid]
            findings.append(
                f'[ERROR] Two-home: uid {uid} exists in both '
                f'.tropo/ ({tropo_path.relative_to(vault_root)}) '
                f'and vault/ ({vault_path.relative_to(vault_root)}) — ADR-045'
            )
            violation_count += 1

    for ident in sorted(script_violations):
        findings.append(
            f'[ERROR] Two-home script: vault/tools/ entry ({ident}) also at .tropo/scripts/ — ADR-045'
        )
        violation_count += 1

    return findings, total_checked, violation_count


def check_entrypoint_pointer_resolution(vault: Path) -> tuple[list[str], int, int]:
    """S5(b) (v1.80): Extend PC-1 pointer class to package.json script entrypoints +
    skill/playbook step commands. ERROR on non-resolving entrypoints.

    Evidence: three live stale pointers from One Home renames in one session:
    package.json test + vault:rebuild, tropo-memory-write step 6 — the existing
    check_calls_pointer_resolution never looked at these surfaces.

    Returns (findings, checked, defects). DEFECTS count as ERRORs (not WARNs).
    """
    import shlex as _shlex
    findings: list[str] = []
    checked = 0
    defects = 0

    def _extract_py_path(cmd: str) -> Optional[str]:
        """Extract a script path from a shell command string like 'python3 vault/tools/foo.py'."""
        cmd = cmd.strip()
        if not cmd:
            return None
        try:
            parts = _shlex.split(cmd)
        except Exception:
            parts = cmd.split()
        if not parts:
            return None
        # Find python3/python/node/npm invocations followed by a file path
        py_prefixes = ('python3', 'python', 'python2', 'node', 'npx')
        for i, part in enumerate(parts):
            if part in py_prefixes and i + 1 < len(parts):
                candidate = parts[i + 1]
                if not candidate.startswith('-') and ('/' in candidate or candidate.endswith('.py') or candidate.endswith('.js')):
                    return candidate
        return None

    # 1. package.json script entrypoints
    pkg_json = vault / 'package.json'
    if pkg_json.is_file():
        try:
            import json as _json
            pkg = _json.loads(pkg_json.read_text(encoding='utf-8', errors='replace'))
            scripts = pkg.get('scripts', {})
            for script_name, cmd in scripts.items():
                if not isinstance(cmd, str):
                    continue
                path = _extract_py_path(cmd)
                if not path:
                    continue
                checked += 1
                candidate = vault / path if not Path(path).is_absolute() else Path(path)
                if not candidate.is_file():
                    findings.append(
                        f'[ERROR] package.json scripts.{script_name!r}: '
                        f'entrypoint {path!r} does not resolve on disk (PC-1 S5b)'
                    )
                    defects += 1
        except Exception as e:
            findings.append(f'[WARN] package.json entrypoint check failed: {e}')

    # 2. Skill/playbook step commands
    skill_dirs = [vault / 'vault' / 'skills', vault / 'vault' / 'playbooks']
    for skill_dir in skill_dirs:
        if not skill_dir.is_dir():
            continue
        for f in sorted(skill_dir.glob('*.md')):
            try:
                text = f.read_text(errors='replace')
            except Exception:
                continue
            rel = f.relative_to(vault)
            # Look for step commands: lines like "Run `python3 vault/tools/...`" or
            # inline code spans with python3/shell commands in step sections
            import re as _re_ep
            # Match patterns: `python3 path/to/script.py`, `python3 vault/tools/...`
            for m in _re_ep.finditer(r'`((?:python3?|node|npx)\s+[^`\s][^`]*)`', text):
                cmd = m.group(1)
                path = _extract_py_path(cmd)
                if not path:
                    continue
                # Skip web URLs, generated paths, etc.
                if path.startswith(('http', '{', '<', '$')):
                    continue
                checked += 1
                candidate = vault / path if not Path(path).is_absolute() else Path(path)
                if not candidate.is_file():
                    findings.append(
                        f'[ERROR] {rel}: step command {cmd!r} → {path!r} does not resolve on disk (PC-1 S5b)'
                    )
                    defects += 1

    return findings, checked, defects


def check_calls_pointer_resolution(vault: Path) -> tuple[list[str], int, int]:
    """Verify that calls: field targets in 00-index.jsonl resolve on disk.

    Catches regressions like c7ea9e01 where a skill migration leaves pointers
    at a dead path (Gate-4 finding class; 8b6f4c5d PC-1; Metis #2 2026-06-30).
    """
    findings: list[str] = []
    checked = 0
    defects = 0
    index_path = vault / 'vault' / '00-index.jsonl'
    if not index_path.exists():
        return findings, 0, 0

    for rec in _index_union(vault):
        calls = rec.get('calls')
        if not calls:
            continue

        uid = rec.get('uid', '?')

        # Normalise to list — handle YAML-bullet-as-string ("-path") and real lists
        if isinstance(calls, str):
            targets = [calls.lstrip('-').strip()]
        elif isinstance(calls, list):
            targets = [str(t).lstrip('-').strip() for t in calls if t]
        else:
            continue

        for target in targets:
            target = target.strip()
            if not target:
                continue
            checked += 1
            # Resolve relative to studio root (vault param is studio root, not vault/)
            candidate = vault / target
            if not candidate.is_file():
                findings.append(f'[WARN] {uid} calls: → {target!r} does not resolve on disk')
                defects += 1

    return findings, checked, defects


# ---------------------------------------------------------------------------
# v1.79 S1 — Agent-Memory Surface Bound Gate
# ---------------------------------------------------------------------------

def check_agent_memory_bound(vault: Path) -> tuple[list[str], int, int]:
    """v1.79 S1 — Memory-bound gate for v3 agent-memory surfaces.

    For every agents/*/.tropo-capsule/memory/agent-memory.md with spec_version 3.0:
    - ERROR when §Top-of-Mind exceeds 15 entries (capsule A1 bound)
    - WARN at >16 KB file size
    - ERROR at >32 KB file size

    Emission traced to the summary counter (the M2 lesson — the tally is the gate).
    References: dev-spec 5bd3d7f0 S1; tropo-memory.capsule A1; A123 groom precedent.

    v0.1 fix (Vela V63, 2026-07-05): the returned `defects` count is ERROR-class only.
    WARN-band findings (16-32KB) still print for visibility but must not fail the build —
    the caller's total_fails tally was incrementing on ANY defect regardless of the [WARN]/
    [ERROR] label printed inline, contradicting this function's own documented WARN/ERROR
    split (found while it blocked the v1.80.0 release cut on three surfaces sitting in the
    16-32KB warn band, none over the 32KB error ceiling).
    """
    import re as _re

    findings: list[str] = []
    checked = 0
    defects = 0  # ERROR-class only — see v0.1 fix note above

    agents_dir = vault / 'agents'
    if not agents_dir.is_dir():
        return findings, checked, defects

    TOP_OF_MIND_MAX = 15
    WARN_SIZE = 16 * 1024    # 16 KB
    ERROR_SIZE = 32 * 1024   # 32 KB

    # Matches numbered list entries at the start of a line inside §Top-of-Mind
    tom_entry_re = _re.compile(r'^\d+\.[ \t]', _re.MULTILINE)
    tom_section_re = _re.compile(r'## §Top-of-Mind(.*?)(?=\n## |\Z)', _re.DOTALL)

    for agent_folder in sorted(agents_dir.iterdir()):
        if not agent_folder.is_dir():
            continue
        memory_file = agent_folder / '.tropo-capsule' / 'memory' / 'agent-memory.md'
        if not memory_file.exists():
            continue

        try:
            text = memory_file.read_text(errors='replace')
        except Exception:
            continue

        # Only check v3 surfaces (spec_version: "3.0")
        fm_raw = split_frontmatter(text)
        if fm_raw is None:
            continue
        spec_version = get_scalar(fm_raw, 'spec_version')
        if str(spec_version) != '3.0':
            continue

        checked += 1
        rel = memory_file.relative_to(vault)
        file_size = memory_file.stat().st_size

        # File-size gate (checked before entry count — size is the cheaper signal)
        if file_size > ERROR_SIZE:
            findings.append(
                f'[ERROR] {rel} — agent-memory surface is {file_size:,} bytes '
                f'(>{ERROR_SIZE:,}B 32 KB ERROR bound; capsule A1 memory bound exceeded; '
                f'sa.memory-curator dispatch REQUIRED — v1.79 S1)'
            )
            defects += 1
        elif file_size > WARN_SIZE:
            findings.append(
                f'[WARN] {rel} — agent-memory surface is {file_size:,} bytes '
                f'(>{WARN_SIZE:,}B 16 KB warn threshold; capsule A1 approaching — v1.79 S1)'
            )
            # WARN-band, not ERROR-class — does not increment defects (see v0.1 fix note)

        # §Top-of-Mind entry count gate
        tom_match = tom_section_re.search(text)
        if tom_match:
            tom_section = tom_match.group(1)
            entries = tom_entry_re.findall(tom_section)
            entry_count = len(entries)
            if entry_count > TOP_OF_MIND_MAX:
                findings.append(
                    f'[ERROR] {rel} — §Top-of-Mind has {entry_count} entries '
                    f'(>{TOP_OF_MIND_MAX} capsule A1 bound; '
                    f'sa.memory-curator dispatch REQUIRED; tally is the gate — v1.79 S1)'
                )
                defects += 1

    return findings, checked, defects


# ---------------------------------------------------------------------------
# v1.79 S5 — Boot-Budget Tally Gate
# ---------------------------------------------------------------------------

def check_boot_budget_tally(vault: Path) -> tuple[list[str], int, int]:
    """v1.79 S5 — Boot-budget tally gate.

    Reads the most recent playbook-runs/agent-activation-*/run.jsonl.
    - WARN when the run never reached run_status:complete (boot was interrupted)
    - WARN when run_created→Agent-Active wall-time exceeds 10 minutes
      (requires ISO-8601 timestamps with time component; degrades to INFO on bare dates)
    - INFO when timestamps are bare dates (S4 ISO timestamps are authored by Argus
      in-parallel — degrades gracefully until S4 lands)

    The 10-minute warning fires against a 7–8-minute target boot bar (Mike-directed
    2026-07-02). References: dev-spec 5bd3d7f0 S5; cfdf0575 O26 boot audit.
    """
    import json as _json

    findings: list[str] = []
    checked = 0
    defects = 0

    runs_dir = vault / 'playbook-runs'
    if not runs_dir.is_dir():
        return findings, checked, defects

    activation_folders = [
        d for d in runs_dir.iterdir()
        if d.is_dir() and d.name.startswith('agent-activation-')
    ]
    if not activation_folders:
        return findings, checked, defects

    # Most recent by folder mtime
    latest_folder = max(activation_folders, key=lambda d: d.stat().st_mtime)
    run_jsonl = latest_folder / 'run.jsonl'
    if not run_jsonl.exists():
        return findings, checked, defects

    checked = 1
    rel = run_jsonl.relative_to(vault)

    try:
        events: list[dict] = []
        with run_jsonl.open(encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(_json.loads(line))
    except Exception as exc:
        findings.append(f'[WARN] {rel} — could not parse run.jsonl: {exc} (v1.79 S5)')
        defects += 1
        return findings, checked, defects

    # --- Completion check ---
    completed = any(ev.get('run_status') == 'complete' for ev in events)
    if not completed:
        findings.append(
            f'[WARN] {rel} — most recent activation run never reached run_status:complete '
            f'(boot was interrupted or timed out; v1.79 S5 boot-budget tally)'
        )
        defects += 1

    # --- Wall-time check (requires ISO-8601 timestamps with time component) ---
    run_created_ev = next((ev for ev in events if ev.get('event') == 'run_created'), None)
    agent_active_ev = next(
        (ev for ev in reversed(events) if ev.get('run_status') == 'complete'), None
    )

    if run_created_ev and agent_active_ev:
        ts_start = str(run_created_ev.get('timestamp', ''))
        ts_end = str(agent_active_ev.get('timestamp', ''))

        if 'T' not in ts_start or 'T' not in ts_end:
            # Bare date (e.g. "2026-07-02") — S4 will supply full ISO-8601 timestamps
            findings.append(
                f'[INFO] {rel} — boot-budget wall-time check skipped: timestamps are bare dates '
                f'(not full ISO-8601; S4 timestamps will enable this gate — v1.79 S5)'
            )
        else:
            try:
                from datetime import datetime as _dt
                # Strip trailing Z for fromisoformat compat (Python < 3.11)
                dt_start = _dt.fromisoformat(ts_start.rstrip('Z'))
                dt_end = _dt.fromisoformat(ts_end.rstrip('Z'))
                wall_minutes = (dt_end - dt_start).total_seconds() / 60.0
                if wall_minutes > 10.0:
                    findings.append(
                        f'[WARN] {rel} — boot wall-time {wall_minutes:.1f} min exceeds 10-minute bar '
                        f'(run_created→Agent-Active; target is 7–8 min; '
                        f'v1.79 S5 boot-budget tally)'
                    )
                    defects += 1
            except (ValueError, TypeError) as exc:
                findings.append(
                    f'[INFO] {rel} — boot-budget wall-time check skipped: could not parse '
                    f'timestamps as ISO-8601 ({exc}; S4 timestamps will enable this gate — v1.79 S5)'
                )

    return findings, checked, defects


# ---------------------------------------------------------------------------
# v1.79 S1 — Memory-Bound Gauntlet Fixture (inline self-test)
# ---------------------------------------------------------------------------

def check_memory_bound_fixture() -> tuple[list[str], int, int]:
    """v1.79 S1 gauntlet: inline fixture verifying that check_agent_memory_bound
    fires on over-bound surfaces and passes on compliant ones.

    Acceptance criteria (dev-spec 5bd3d7f0 S1):
    - 16 §Top-of-Mind entries → ERROR (entry count in message)
    - 14 §Top-of-Mind entries → PASS (no entry finding)
    - >32 KB body → ERROR (size gate)
    - >16 KB but ≤32 KB body → WARN (size gate)

    A passing message that never fired is a vacuous ratchet — this plant IS the acceptance.
    """
    import tempfile as _tempfile
    import shutil as _shutil

    findings: list[str] = []
    n_pass = 0
    n_fail = 0

    def _make_surface(vault_tmp: Path, tom_count: int, pad_bytes: int = 0) -> None:
        """Write a synthetic v3 agent-memory surface under a scratch agents/ tree."""
        mem_dir = vault_tmp / 'agents' / 'fixture-agent' / '.tropo-capsule' / 'memory'
        mem_dir.mkdir(parents=True, exist_ok=True)
        tom_lines = '\n'.join(
            f'{i + 1}. Synthetic pin entry {i + 1} — S1 gauntlet plant'
            for i in range(tom_count)
        )
        body = (
            '---\n'
            'spec_version: "3.0"\n'
            'agent: fixture\n'
            '---\n\n'
            '## §Top-of-Mind\n\n'
            f'{tom_lines}\n'
        )
        if pad_bytes > 0:
            body += '\n## §Padding\n\n' + ('x' * pad_bytes) + '\n'
        (mem_dir / 'agent-memory.md').write_text(body, 'utf-8')

    tmp = Path(_tempfile.mkdtemp(prefix='s1-memory-bound-fixture-'))
    try:
        # Case 1 — 16 entries (over bound) → ERROR with entry count
        v1 = tmp / 'v1'; _make_surface(v1, tom_count=16)
        f1, _c1, d1 = check_agent_memory_bound(v1)
        if d1 > 0 and any('[ERROR]' in ln and '16 entries' in ln for ln in f1):
            n_pass += 1
        else:
            n_fail += 1
            findings.append('  [FAIL] S1 gauntlet: 16-entry surface should produce [ERROR] with count — gate did not fire')

        # Case 2 — 14 entries (within bound) → PASS
        v2 = tmp / 'v2'; _make_surface(v2, tom_count=14)
        f2, _c2, d2 = check_agent_memory_bound(v2)
        entry_errors = [ln for ln in f2 if '[ERROR]' in ln and 'entries' in ln]
        if d2 == 0 and not entry_errors:
            n_pass += 1
        else:
            n_fail += 1
            findings.append(f'  [FAIL] S1 gauntlet: 14-entry surface should PASS — false positive: {entry_errors}')

        # Case 3 — >32 KB body → ERROR (size gate)
        v3 = tmp / 'v3'; _make_surface(v3, tom_count=5, pad_bytes=33 * 1024)
        f3, _c3, d3 = check_agent_memory_bound(v3)
        if d3 > 0 and any('[ERROR]' in ln and '32' in ln for ln in f3):
            n_pass += 1
        else:
            n_fail += 1
            findings.append('  [FAIL] S1 gauntlet: >32 KB surface should [ERROR] on size gate')

        # Case 4 — 17 KB body → WARN (size gate, not ERROR)
        v4 = tmp / 'v4'; _make_surface(v4, tom_count=5, pad_bytes=17 * 1024)
        f4, _c4, d4 = check_agent_memory_bound(v4)
        warn_size = [ln for ln in f4 if '[WARN]' in ln and '16' in ln]
        err_size = [ln for ln in f4 if '[ERROR]' in ln and '32' in ln]
        if warn_size and not err_size:
            n_pass += 1
        else:
            n_fail += 1
            findings.append('  [FAIL] S1 gauntlet: 17 KB surface should [WARN] (size), not [ERROR]')

    finally:
        _shutil.rmtree(tmp, ignore_errors=True)

    return findings, n_pass, n_fail


# ---------------------------------------------------------------------------
# v1.79 S5 — Boot-Budget Tally Gauntlet Fixture (inline self-test)
# ---------------------------------------------------------------------------

def check_boot_budget_tally_fixture() -> tuple[list[str], int, int]:
    """v1.79 S5 gauntlet: inline fixture verifying that check_boot_budget_tally
    fires on over-time and incomplete runs, and degrades gracefully on bare dates.

    Acceptance criteria (dev-spec 5bd3d7f0 S5):
    - Incomplete run (no run_status:complete) → WARN
    - >10-minute ISO run → WARN with wall-time in message
    - 7-minute complete ISO run → PASS (no defects)
    - Bare-date timestamps → INFO degrade (not ERROR or WARN)
    """
    import json as _json
    import tempfile as _tempfile
    import shutil as _shutil

    findings: list[str] = []
    n_pass = 0
    n_fail = 0

    def _write_run(vault_tmp: Path, start: str, end: str | None, complete: bool) -> None:
        run_dir = vault_tmp / 'playbook-runs' / 'agent-activation-fixture-F1-2026-07-03'
        run_dir.mkdir(parents=True)
        events: list[dict] = [
            {'event': 'run_created', 'run_uid': 'aaaabbbb', 'agent': 'fixture',
             'generation': 'F1', 'vault_root': '/tmp', 'timestamp': start, 'status': 'active'},
            {'event': 'milestone_fired', 'milestone': 'Boot Config Chain Complete',
             'group': 'Group 0', 'timestamp': start},
        ]
        if complete and end:
            events.append({
                'event': 'milestone_fired', 'milestone': 'Agent Active',
                'group': 'Group 5', 'timestamp': end, 'run_status': 'complete',
            })
        (run_dir / 'run.jsonl').write_text(
            '\n'.join(_json.dumps(e) for e in events) + '\n', 'utf-8'
        )

    tmp = Path(_tempfile.mkdtemp(prefix='s5-boot-budget-fixture-'))
    try:
        # Case 1 — incomplete (no run_status:complete) → WARN
        v1 = tmp / 'v1'
        _write_run(v1, '2026-07-03T10:00:00', None, complete=False)
        f1, _c1, d1 = check_boot_budget_tally(v1)
        if d1 > 0 and any('never reached run_status:complete' in ln for ln in f1):
            n_pass += 1
        else:
            n_fail += 1
            findings.append('  [FAIL] S5 gauntlet: incomplete run should WARN (run_status:complete missing)')

        # Case 2 — 15-minute ISO run (over 10-min bar) → WARN
        v2 = tmp / 'v2'
        _write_run(v2, '2026-07-03T09:00:00', '2026-07-03T09:15:00', complete=True)
        f2, _c2, d2 = check_boot_budget_tally(v2)
        if d2 > 0 and any('[WARN]' in ln and 'wall-time' in ln for ln in f2):
            n_pass += 1
        else:
            n_fail += 1
            findings.append('  [FAIL] S5 gauntlet: 15-minute run should WARN (over 10-minute bar)')

        # Case 3 — 7-minute ISO run (within bar) → PASS
        v3 = tmp / 'v3'
        _write_run(v3, '2026-07-03T08:00:00', '2026-07-03T08:07:00', complete=True)
        f3, _c3, d3 = check_boot_budget_tally(v3)
        if d3 == 0:
            n_pass += 1
        else:
            n_fail += 1
            findings.append(f'  [FAIL] S5 gauntlet: 7-minute complete run should PASS — got: {f3}')

        # Case 4 — bare-date timestamps → INFO degrade (not WARN/ERROR; graceful until S4 lands)
        v4 = tmp / 'v4'
        run4_dir = v4 / 'playbook-runs' / 'agent-activation-fixture-F4-2026-07-03'
        run4_dir.mkdir(parents=True)
        bare_events = [
            {'event': 'run_created', 'run_uid': 'bbbbcccc', 'timestamp': '2026-07-03', 'status': 'active'},
            {'event': 'milestone_fired', 'milestone': 'Agent Active', 'group': 'Group 5',
             'timestamp': '2026-07-03', 'run_status': 'complete'},
        ]
        (run4_dir / 'run.jsonl').write_text(
            '\n'.join(_json.dumps(e) for e in bare_events) + '\n', 'utf-8'
        )
        f4, _c4, d4 = check_boot_budget_tally(v4)
        has_info_skip = any('[INFO]' in ln and 'bare dates' in ln for ln in f4)
        has_defect = d4 > 0
        if has_info_skip and not has_defect:
            n_pass += 1
        else:
            n_fail += 1
            findings.append(
                f'  [FAIL] S5 gauntlet: bare-date run should INFO-degrade (no defect); '
                f'defects={d4}, findings={f4}'
            )

    finally:
        _shutil.rmtree(tmp, ignore_errors=True)

    return findings, n_pass, n_fail


# ---------------------------------------------------------------------------
# 943bb220 (ADR-051 Fork 1) — vault.capsule forge: type recognition + schema
# enforcement for the NEW `vault` manifest type and the RENAMED `vault-entity`
# type (UID 4d6e2f9a preserved). Two pure schema-check functions dispatched
# purely on `type:`/`subtype:` — by construction a `type: vault` entry is NEVER
# run through validate_vault_entity_fields and a `subtype: vault-entity` entry
# is NEVER run through validate_vault_manifest_fields (AC4's negative check).
# ---------------------------------------------------------------------------

_VAULT_MANIFEST_REQUIRED_FIELDS = (
    'kind', 'owner', 'audience', 'remote', 'prefix_policy', 'publish_policy',
    'curation_policy', 'curator', 'version', 'status', 'contract', 'regulated_acceptance',
)
_VAULT_MANIFEST_KIND_ENUM = frozenset({'os', 'personal', 'team', 'knowledgebase'})
_VAULT_MANIFEST_STATUS_ENUM = frozenset({'draft', 'active', 'deprecated', 'archived'})
_VAULT_ENTITY_SUBTYPE = 'vault-entity'
_STUDIO_IDENTITY_UID = '32067bea'


def validate_vault_manifest_fields(
    fm: dict,
    type_lookup: Optional[dict[str, str]] = None,
    strict_audience: bool = False,
) -> list[str]:
    """943bb220 §2 (ADR-051 Fork 1) — validate a `type: vault` MANIFEST instance's
    frontmatter (already YAML-parsed to a dict) against the new vault-node manifest
    schema. Pure function (dict in, error-string list out): directly unit-testable
    AND reused by the live-tree scan in check_vault_capsule_types() below.

    Implements Validation Checks 1-2, 4-8 from tropo-vault.capsule.md verbatim.
    Check 3's cross-version half (kind change after a manifest has EVER been active)
    requires git-log inspection across commits and is deferred to a later ratchet —
    same documented precedent as check_article_state_machine_invariants's
    sequential-transition-history note; v1.0 validates current-state shape only.
    Check 9 (contract-narrowing diff) is explicitly [target vNext] in the capsule.
    Check 10 (one manifest per vault-node at compose) is Fork 2's job (per-vault-root
    manifest discovery), not owned by this scan.

    ``strict_audience`` is the B4a cutover flag (dev-spec 0bfa771d §"Registry,
    resolver, and contextual audience"; brief 252534fe §5). When True — set by a
    caller once a group authority is installed (``lib.audience_gate.cutover_active``)
    — the audience MUST resolve to a live ``type: group`` UID: ``team``, ``team-def``,
    and any unknown / non-group 8-hex are refused. This removes the pre-B4a
    "known team or unknown UID" syntax-only acceptance. When False the pre-cutover
    lenient behaviour is preserved so a Studio that has not applied the authority
    update is unaffected.

    Returns a list of human-readable error strings (empty = valid).
    """
    errors: list[str] = []
    type_lookup = type_lookup or {}

    missing = [f for f in _VAULT_MANIFEST_REQUIRED_FIELDS if fm.get(f) in (None, '', [])]
    if missing:
        errors.append(f"missing required field(s): {', '.join(missing)}")

    kind = fm.get('kind')
    if kind is not None and kind not in _VAULT_MANIFEST_KIND_ENUM:
        errors.append(f"kind={kind!r} not in enum {sorted(_VAULT_MANIFEST_KIND_ENUM)}")

    status = fm.get('status')
    if status is not None and status not in _VAULT_MANIFEST_STATUS_ENUM:
        errors.append(f"status={status!r} not in enum {sorted(_VAULT_MANIFEST_STATUS_ENUM)}")
    if status == 'deprecated':
        successor = fm.get('successor')
        if not successor or not UID_RE.match(str(successor)):
            errors.append("status=deprecated requires a resolvable successor: (Rule 6)")

    prefix_policy = fm.get('prefix_policy')
    if prefix_policy is not None:
        if not isinstance(prefix_policy, dict):
            errors.append("prefix_policy must be an object")
        else:
            references = prefix_policy.get('references')
            refs_studio_identity = (
                references == _STUDIO_IDENTITY_UID
                or (isinstance(references, list) and _STUDIO_IDENTITY_UID in references)
            )
            inlines_prefix = any(
                prefix_policy.get(k) for k in ('mint_prefix', 'prefix', 'studio_prefix')
            )
            if inlines_prefix:
                errors.append(
                    "prefix_policy INLINES a studio prefix — must REFERENCE the studio "
                    "identity (32067bea) by reference, never carry one inline "
                    "(ADR-051 sibling boundary, Rule 2)"
                )
            elif not refs_studio_identity:
                errors.append(
                    "prefix_policy does not reference the studio identity (32067bea) "
                    "— Rule 2 requires an explicit reference"
                )

    audience = fm.get('audience')
    if audience is not None:
        if isinstance(audience, (list, tuple, set, dict)):
            errors.append(
                "audience is an inline member list — must be a single group-UID "
                "reference (Rule 4)"
            )
        elif not UID_RE.match(str(audience)):
            errors.append(f"audience={audience!r} is not an 8-hex group-UID reference")
        elif strict_audience:
            # B4a strict cutover: the audience must resolve to a live `type: group`.
            # `team`/`team-def`/entity and any unknown 8-hex UID are refused — the
            # "known team or unknown UID" fail-open is removed (252534fe §5).
            resolved_type = type_lookup.get(audience) if type_lookup else None
            if resolved_type is None:
                errors.append(
                    f"audience={audience!r} does not resolve to a known entity — a "
                    f"vault audience must be a live `type: group` UID (B4a strict; Rule 4)"
                )
            elif resolved_type != 'group':
                errors.append(
                    f"audience={audience!r} resolves to type={resolved_type!r}, not a "
                    f"`type: group` — team/team-def/entity audiences are refused (B4a strict; Rule 4)"
                )
        elif type_lookup and audience in type_lookup and type_lookup[audience] != 'team':
            errors.append(
                f"audience={audience!r} resolves to type={type_lookup[audience]!r}, "
                f"not a group/team entity (Rule 4)"
            )

    if not fm.get('curator'):
        errors.append("curator is missing — unowned curation is rejected (Rule 5)")

    regulated = fm.get('regulated_acceptance')
    if regulated is not None:
        if not isinstance(regulated, dict):
            errors.append("regulated_acceptance must be an object")
        elif regulated.get('accepted') is True and not regulated.get('accepted_by'):
            errors.append("regulated_acceptance.accepted=true but accepted_by is missing (A1)")

    return errors


def validate_vault_entity_fields(fm: dict, type_lookup: Optional[dict[str, str]] = None,
                                  subtype_lookup: Optional[dict[str, str]] = None) -> list[str]:
    """943bb220 §3 (ADR-051 Fork 1) — validate a RENAMED `vault-entity` instance's
    frontmatter (`type: entity`, `subtype: vault-entity`) against the renamed schema.
    Deliberately a SEPARATE function from validate_vault_manifest_fields() — the two
    never cross-apply (AC4's negative check is structural, not just tested).

    Returns a list of human-readable error strings (empty = valid).
    """
    errors: list[str] = []
    type_lookup = type_lookup or {}
    subtype_lookup = subtype_lookup or {}

    if fm.get('subtype') != _VAULT_ENTITY_SUBTYPE:
        errors.append(f"subtype={fm.get('subtype')!r}, expected {_VAULT_ENTITY_SUBTYPE!r}")

    principal = fm.get('principal')
    if not principal:
        errors.append("principal is missing (entity.capsule Rule 1)")
    elif not UID_RE.match(str(principal)):
        errors.append(f"principal={principal!r} is not an 8-hex UID")
    elif type_lookup and principal in type_lookup:
        p_type = type_lookup.get(principal)
        p_subtype = subtype_lookup.get(principal)
        if p_type == 'entity' and p_subtype not in ('person', 'agent', None):
            errors.append(
                f"principal {principal} resolves to subtype={p_subtype!r}, "
                f"expected person (or agent) — vault-entity.capsule Rule 2"
            )

    inbox_project = fm.get('inbox_project')
    if inbox_project:
        if not UID_RE.match(str(inbox_project)):
            errors.append(f"inbox_project={inbox_project!r} is not an 8-hex UID")
        elif type_lookup and inbox_project in type_lookup and type_lookup[inbox_project] != 'project':
            errors.append(f"inbox_project {inbox_project} does not resolve to a type:project entry")

    return errors


def _b4a_cutover_active(root: Path) -> bool:
    """True iff a B4a group authority is installed for this Studio.

    Defensive lazy import: any import/read failure yields False (pre-cutover
    behaviour), so this never fails open to a synthesized authority and never
    hard-crashes the validator on a Studio without the B4a runtime.
    """
    try:
        from lib.audience_gate import cutover_active
        return bool(cutover_active(root))
    except Exception:
        return False


def check_vault_capsule_types(vault: Path) -> tuple[list[str], int, int]:
    """943bb220 (ADR-051 Fork 1) — validator recognition for the vault.capsule forge.

    Scans vault/files/*.md for:
      (a) `type: vault` entries — validated against validate_vault_manifest_fields()
          (the NEW manifest schema). None exist yet in this studio (943bb220 §1's own
          grounded finding — "zero type: vault entries"); this check exists so a
          future manifest instance is caught the moment it's authored, and is proven
          live via the unit-test fixtures in test_vault_capsule_forge_943bb220.py.
          NOTE: the manifest's CANONICAL home is a per-vault-root path (Fork 2), not
          vault/files/<uid>.md (943bb220 §"Where instances live") — this scan covers
          vault/files/ as a defensive floor; Fork 2 owns extending discovery/gating
          to the per-vault-root path.
      (b) `type: entity, subtype: vault-entity` entries — validated against
          validate_vault_entity_fields() (the RENAMED schema) AND checked for the
          per-vault-node singleton (Rule 1).

    Singleton scoping judgment call (943bb220 build report): this studio has no
    per-vault-root manifest / multi-vault mount machinery yet (Fork 2, downstream),
    so there is no first-class "vault-node boundary" to scope the singleton by.
    `extraction_scope` is used as the best available proxy until Fork 2 lands: the
    2 live instances carry DIFFERENT extraction_scope values (7f5b1d83 =
    argo-reference, this studio's own live vault-node; 7c3a8e91 = ship, a template
    bundled FOR other studios' vault-nodes) — i.e. they are not really both "in"
    Argo's own vault-node. A 3rd instance sharing either group is the real P0 the
    capsule Rule 1 forbids.

    Returns (findings, total_checked, violation_count).
    """
    findings: list[str] = []
    checked = 0
    violations = 0

    index_path = vault / 'vault' / '00-index.jsonl'
    by_uid: dict[str, dict] = {
        str(record['uid']): record
        for record in _index_union(vault)
        if record.get('uid')
    }
    type_lookup = {u: r.get('type') for u, r in by_uid.items()}
    subtype_lookup = {u: r.get('subtype') for u, r in by_uid.items()}
    strict_audience = _b4a_cutover_active(vault)

    files_dir = vault / 'vault' / 'files'
    if not files_dir.is_dir():
        return findings, checked, violations

    vault_entity_groups: dict[str, list[str]] = {}

    for f in sorted(files_dir.glob('*.md')):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        try:
            fm = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue

        entry_type = fm.get('type')
        uid = fm.get('uid') or f.stem

        if entry_type == 'vault':
            checked += 1
            errors = validate_vault_manifest_fields(
                fm, type_lookup=type_lookup, strict_audience=strict_audience
            )
            if errors:
                violations += 1
                for e in errors:
                    findings.append(f'[ERROR] {f.relative_to(vault)} (type: vault, uid {uid}) — {e}')
        elif entry_type == 'entity' and fm.get('subtype') == _VAULT_ENTITY_SUBTYPE:
            checked += 1
            errors = validate_vault_entity_fields(fm, type_lookup=type_lookup, subtype_lookup=subtype_lookup)
            if errors:
                violations += 1
                for e in errors:
                    findings.append(f'[ERROR] {f.relative_to(vault)} (subtype: vault-entity, uid {uid}) — {e}')
            scope = str(fm.get('extraction_scope') or 'default')
            vault_entity_groups.setdefault(scope, []).append(str(uid))

    for scope, uids in sorted(vault_entity_groups.items()):
        if len(uids) > 1:
            violations += 1
            findings.append(
                f"[ERROR] {len(uids)} vault-entity instance(s) share extraction_scope="
                f"{scope!r} ({', '.join(sorted(uids))}) — Rule 1 singleton-per-vault-node "
                f"violation (vault-entity.capsule v1.1)"
            )

    return findings, checked, violations


# ---------------------------------------------------------------------------
# 409ef1cc (ADR-051 Fork 2) — per-vault-root manifest governed-write gate +
# compose.lock-graduated one-clone-per-vault-UID + diff-aware guarded
# transitions. Extends check_vault_capsule_types() (943bb220/Fork 1) to the
# per-vault-root manifest path Fork 2 was explicitly named as owning (see
# that function's own docstring: "Check 10 ... is Fork 2's job", and
# validate_vault_manifest_fields()'s docstring: "Check 9 ... is [target
# vNext] in the capsule").
# ---------------------------------------------------------------------------

VAULT_MANIFEST_REL = Path('.tropo') / 'vault-manifest.md'
DEFAULT_COMPOSE_LOCK_REL = Path('.tropo-studio') / 'compose.lock'


def _compose_lock_contract_hash(contract: dict) -> str:
    """Mirrors tropo-mount.py's contract_hash() exactly (sha256 of the
    canonical sorted-key JSON dump) — kept as a small local copy rather than
    a cross-file import so this validator's checks have no runtime
    dependency on tropo-mount.py (the gate depends on the validator's
    schema function; the reverse dependency is deliberately NOT created,
    to keep tropo-validate.py importable/runnable standalone as it always
    has been).
    """
    import hashlib as _hashlib
    canonical = json.dumps(contract, sort_keys=True, separators=(',', ':'))
    return _hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _contract_narrowing_reasons(old_contract: dict, new_contract: dict) -> list[str]:
    """Same narrowing rule as tropo-mount.py's contract_is_narrowed() —
    duplicated in small, self-contained form for the same standalone-
    validator reason as _compose_lock_contract_hash above. a1f7c750
    Guarded Transitions: contract NARROWING = drop a registered_type,
    downgrade a capsule_versions entry, or drop a capability.
    """
    reasons: list[str] = []
    old_types = set(old_contract.get('registered_types') or [])
    new_types = set(new_contract.get('registered_types') or [])
    dropped = old_types - new_types
    if dropped:
        reasons.append(f'registered_types dropped: {sorted(dropped)}')

    old_versions = old_contract.get('capsule_versions') or {}
    new_versions = new_contract.get('capsule_versions') or {}

    def _semver_tuple(v):
        try:
            return tuple(int(p) for p in str(v).split('.'))
        except (ValueError, AttributeError):
            return (0,)

    for capsule, old_v in old_versions.items():
        new_v = new_versions.get(capsule)
        if new_v is None:
            reasons.append(f'capsule_versions[{capsule!r}] removed (was {old_v!r})')
        elif _semver_tuple(new_v) < _semver_tuple(old_v):
            reasons.append(f'capsule_versions[{capsule!r}] downgraded {old_v!r} -> {new_v!r}')

    old_caps = set(old_contract.get('capabilities') or [])
    new_caps = set(new_contract.get('capabilities') or [])
    dropped_caps = old_caps - new_caps
    if dropped_caps:
        reasons.append(f'capabilities dropped: {sorted(dropped_caps)}')

    return reasons


def check_vault_manifest_governed_write_gate(
    vault: Path, compose_lock_path: Optional[Path] = None
) -> tuple[list[str], int, int]:
    """409ef1cc (ADR-051 Fork 2) — per-vault-root manifest governed-write gate.

    Discovers per-vault-root manifests (<vault-root>/.tropo/vault-manifest.md)
    the SAME way tropo-mount.py's compose.lock does: by walking the recorded
    vault_uid keys in .tropo-studio/compose.lock. This is the graduation off
    the extraction_scope proxy that check_vault_capsule_types() (943bb220)
    explicitly deferred to Fork 2 — compose.lock IS the real per-vault-node
    boundary/registry that check's own docstring said this studio lacked
    "until Fork 2 lands."

    NOTE: this check does NOT itself discover arbitrary manifests on disk by
    globbing for .tropo/vault-manifest.md paths outside compose.lock's
    knowledge — a manifest that was never mounted (never passed through
    tropo-mount.py even once) has no "before" state to diff against, so
    there is nothing to catch it being edited off-gate FROM. The off-gate
    catch (AC-1) fires for manifests that WERE mounted at least once
    (compose.lock has a recorded contract for them) and have since been
    edited directly on disk without going back through the gate — exactly
    the "governed write" failure mode a1f7c750 names: a manifest edit is
    only detectable as off-gate relative to a last-known-good gated state.
    A never-mounted stray manifest file is out of scope for THIS check (it
    would be caught by check_vault_capsule_types' vault/files/ scan only if
    it were ALSO placed there, which is not the per-vault-root convention).

    For each vault_uid in compose.lock:
      1. LIVE MANIFEST RE-READ (security-review fix, 2026-07-08): compose.lock
         records now persist `mount_path` (the local filesystem path the
         mount was run against — see .tropo/schema/compose-lockfile-schema.md
         for the durability caveat). When `mount_path` is present AND still
         resolves to a directory containing `.tropo/vault-manifest.md`, this
         check RE-READS THAT FILE FROM DISK, parses its frontmatter, and
         recomputes a contract hash from its live `contract` block —
         comparing that live hash against the PINNED `contract_hash`. A
         mismatch is a direct, un-bypassable catch of a hand-edit to the
         actual governed artifact (not merely to compose.lock's own copy of
         it) — this is the literal AC-1 scenario ("a per-vault-root
         type:vault manifest edited directly... FAILS"). If `mount_path` is
         absent (older compose.lock schema, or manually authored) or no
         longer resolves to a readable manifest, this step is SKIPPED for
         that vault_uid (recorded as a note, not a silent pass merged into
         the violation count) — it never blocks the record from receiving
         its other checks below.
      2. Absent a usable live manifest, or in addition to it, this check
         validates compose.lock's OWN recorded `contract` block against its
         OWN `contract_hash` in-place — catching a hand-edit of compose.lock
         itself (weaker than #1, but a real, independent catch: compose.lock
         is ALSO a governed artifact, per its own schema doc "do not
         hand-edit; run the gate").
      3. Diff-aware guarded transitions (a1f7c750 Checks 3/9, "[target
         vNext]" in the capsule / validate_vault_manifest_fields docstring):
         this function exposes the comparison primitives
         (_contract_narrowing_reasons) that tropo-mount.py's re-mount path
         already exercises live; here they are re-run in read-only/audit
         form against compose.lock's own recorded pin, so `tropo-validate.py`
         run standalone (no mount attempted) still surfaces "this recorded
         contract implies a narrowing was consented" bookkeeping errors
         (e.g. a hand-corrupted compose.lock record).
      4. One-clone-per-vault-UID (Check 10, graduated off extraction_scope):
         compose.lock is a dict keyed by vault_uid — by construction it
         cannot itself hold two records for one UID (last-write-wins on a
         hand-edit would SILENTLY lose one, which is itself an integrity
         concern) — so this check instead cross-validates compose.lock's
         vault_uids against `vault/files/*.md` `type: vault` manifests (the
         943bb220 defensive-floor scan) and flags any vault_uid appearing
         in BOTH places with a MISMATCHED contract_hash — i.e. a manifest
         instance and a compose.lock pin have drifted apart, which is
         exactly the off-gate-edit failure mode for a vault whose manifest
         happens to also be filed under vault/files/ (belt-and-suspenders
         placement, not the canonical per-vault-root location).
      5. `kind` immutable-after-active (Fork 3): now a REAL comparison
         (compose.lock's `manifest_kind` field, persisted starting with
         this fix) against both the live re-read manifest's `kind` (#1) and
         any belt-and-suspenders vault/files/ manifest's `kind` (#4) sharing
         the same UID — previously dead code because the record shape had
         no `kind` to compare against at all.

    Returns (findings, checked, violation_count). Zero live type:vault
    instances and an absent/empty compose.lock (this studio's real current
    state) mean checked==0, violations==0 today — the check exists so the
    FIRST manifest instance is caught the moment it drifts, per this
    dev-spec's own "lands on a clean, verified base with no migration
    surface" framing.
    """
    findings: list[str] = []
    checked = 0
    violations = 0

    lock_path = compose_lock_path or (vault / DEFAULT_COMPOSE_LOCK_REL)
    if not lock_path.is_file():
        return findings, checked, violations

    try:
        lock_data = json.loads(lock_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as e:
        return (
            [f'[ERROR] {lock_path} is corrupt / unreadable JSON: {e}'],
            1, 1,
        )
    if not isinstance(lock_data, dict) or not isinstance(lock_data.get('vaults'), dict):
        return (
            [f"[ERROR] {lock_path} does not match the compose-lockfile schema "
             f"(missing top-level 'vaults' object) — see .tropo/schema/compose-lockfile-schema.md"],
            1, 1,
        )

    vaults = lock_data['vaults']

    # Check 10 graduation: cross-validate compose.lock's vault_uids against
    # any type:vault manifest ALSO filed under vault/files/ (the 943bb220
    # defensive floor). A vault_uid present in both with a mismatched
    # contract_hash means the two records have drifted — an off-gate edit
    # of one without going through the other.
    files_dir = vault / 'vault' / 'files'
    files_manifest_by_uid: dict[str, dict] = {}
    if files_dir.is_dir():
        for f in sorted(files_dir.glob('*.md')):
            try:
                text = f.read_text(errors='replace')
            except Exception:
                continue
            fm_text = split_frontmatter(text)
            if fm_text is None:
                continue
            try:
                fm = yaml.safe_load(fm_text)
            except yaml.YAMLError:
                continue
            if not isinstance(fm, dict) or fm.get('type') != 'vault':
                continue
            uid = str(fm.get('uid') or f.stem)
            files_manifest_by_uid[uid] = fm

    for vault_uid, record in sorted(vaults.items()):
        checked += 1
        if not isinstance(record, dict):
            violations += 1
            findings.append(
                f'[ERROR] compose.lock vault_uid={vault_uid} record is not an object — '
                f'corrupt lockfile record (schema: .tropo/schema/compose-lockfile-schema.md)'
            )
            continue

        recorded_contract = record.get('contract')
        recorded_hash = record.get('contract_hash')
        if isinstance(recorded_contract, dict) and recorded_hash:
            live_hash = _compose_lock_contract_hash(recorded_contract)
            if live_hash != recorded_hash:
                violations += 1
                findings.append(
                    f'[ERROR] compose.lock vault_uid={vault_uid} — contract_hash '
                    f'{recorded_hash!r} does not match a recomputed hash of the recorded '
                    f'contract block ({live_hash!r}) — the lockfile record was hand-edited '
                    f'off-gate (governed-write violation, AC-1 class)'
                )

        # LIVE MANIFEST RE-READ (security-review fix, 2026-07-08): the
        # direct AC-1 catch — re-read the ACTUAL governed artifact
        # (<mount_path>/.tropo/vault-manifest.md) off disk, not just
        # compose.lock's own copy of it.
        mount_path_str = record.get('mount_path')
        recorded_kind = record.get('manifest_kind')
        if mount_path_str:
            live_manifest_path = Path(mount_path_str) / VAULT_MANIFEST_REL
            if live_manifest_path.is_file():
                try:
                    live_text = live_manifest_path.read_text(encoding='utf-8', errors='replace')
                except OSError as e:
                    findings.append(
                        f'[NOTE] compose.lock vault_uid={vault_uid} — mount_path manifest at '
                        f'{live_manifest_path} could not be read ({e}); live re-read skipped '
                        f'for this vault_uid (other checks still ran)'
                    )
                    live_text = None
                if live_text is not None:
                    live_fm_text = split_frontmatter(live_text)
                    live_fm = None
                    if live_fm_text is not None:
                        try:
                            parsed = yaml.safe_load(live_fm_text)
                            if isinstance(parsed, dict):
                                live_fm = parsed
                        except yaml.YAMLError:
                            live_fm = None
                    if live_fm is None:
                        violations += 1
                        findings.append(
                            f'[ERROR] compose.lock vault_uid={vault_uid} — live manifest at '
                            f'{live_manifest_path} has no parseable YAML frontmatter — cannot '
                            f'verify it still matches the pinned contract (governed-write '
                            f'violation, AC-1 class: the governed artifact is no longer in a '
                            f'state the gate could have admitted)'
                        )
                    else:
                        live_contract = live_fm.get('contract')
                        if isinstance(live_contract, dict) and recorded_hash:
                            live_manifest_hash = _compose_lock_contract_hash(live_contract)
                            if live_manifest_hash != recorded_hash:
                                violations += 1
                                findings.append(
                                    f'[ERROR] compose.lock vault_uid={vault_uid} — the LIVE '
                                    f'manifest on disk ({live_manifest_path}) has a contract '
                                    f'(hash {live_manifest_hash!r}) that no longer matches the '
                                    f'compose.lock-pinned contract (hash {recorded_hash!r}) — '
                                    f'the governed artifact was edited directly, off-gate, '
                                    f'without re-running tropo-mount.py (AC-1: direct hand-edit '
                                    f'of the per-vault-root manifest is caught)'
                                )
                        elif recorded_hash and not isinstance(live_contract, dict):
                            violations += 1
                            findings.append(
                                f'[ERROR] compose.lock vault_uid={vault_uid} — the live manifest '
                                f'at {live_manifest_path} no longer has a `contract` block at all '
                                f'(was pinned with contract_hash {recorded_hash!r}) — off-gate '
                                f'edit (AC-1 class)'
                            )
                        live_kind = live_fm.get('kind')
                        if recorded_kind and live_kind and live_kind != recorded_kind:
                            violations += 1
                            findings.append(
                                f"[ERROR] vault_uid={vault_uid} — kind changed from "
                                f"{recorded_kind!r} (pinned at mount) to {live_kind!r} (live "
                                f"manifest on disk) — kind is IMMUTABLE after active (a1f7c750 "
                                f"Fork 3); a conversion is a NEW vault + migration changeset, "
                                f"never an in-place flip"
                            )
            else:
                findings.append(
                    f'[NOTE] compose.lock vault_uid={vault_uid} — recorded mount_path '
                    f'{mount_path_str!r} no longer has a manifest at the expected path '
                    f'({live_manifest_path}); live re-read skipped (mount_path is advisory, '
                    f'local-machine state per its schema doc — this is not itself a violation)'
                )

        consent = record.get('consent')
        capabilities = (recorded_contract or {}).get('capabilities') or []
        if capabilities and not (isinstance(consent, dict) and consent.get('consented') is True):
            violations += 1
            findings.append(
                f'[ERROR] compose.lock vault_uid={vault_uid} declares executable '
                f'capabilities {capabilities} but consent.consented is not true — '
                f'executable-consent must be a recorded governed write (AC-3, bc25583d §6); '
                f'this record could only be produced by hand-editing compose.lock off-gate'
            )

        # Cross-validate against a belt-and-suspenders vault/files/ manifest,
        # if one happens to also exist for this UID (Check 10 graduation).
        files_fm = files_manifest_by_uid.get(vault_uid)
        if files_fm is not None:
            files_contract = files_fm.get('contract')
            if isinstance(files_contract, dict) and isinstance(recorded_contract, dict):
                files_hash = _compose_lock_contract_hash(files_contract)
                if files_hash != recorded_hash:
                    violations += 1
                    findings.append(
                        f'[ERROR] vault_uid={vault_uid} — vault/files/ manifest contract '
                        f'(hash {files_hash!r}) has drifted from the compose.lock-pinned '
                        f'contract (hash {recorded_hash!r}) — an off-gate edit to one '
                        f'without re-running tropo-mount.py to update the other'
                    )
            files_kind = files_fm.get('kind')
            record_kind = (record.get('manifest_kind'))
            if record_kind and files_kind and files_kind != record_kind:
                violations += 1
                findings.append(
                    f"[ERROR] vault_uid={vault_uid} — kind changed from "
                    f"{record_kind!r} (pinned) to {files_kind!r} (live vault/files/ manifest) "
                    f"— kind is IMMUTABLE after active (a1f7c750 Fork 3); a conversion is a "
                    f"NEW vault + migration changeset, never an in-place flip"
                )

    return findings, checked, violations


# ---------------------------------------------------------------------------
# Cross-vault member_of primitive (4275b01c, ADR-051) — per-vault D7
# grounding generalization + up-lattice-only cross-segment member_of edges.
# ---------------------------------------------------------------------------

def check_cross_vault_member_of(vault: Path) -> tuple[list[str], int, int]:
    """4275b01c (ADR-051) — per-vault-node D7 primary-grounding check +
    up-lattice boundary check on additional member_of edges.

    GENERALIZES the single-vault D7 grounding invariant (f2e8a7b1 §3.1/
    §8.1: WorkItem member_of non-empty, >=1 entry vault-entity-owned)
    per-vault-node, per Mike's ADR-051 ruling (18059aef) and the
    vault-entity singleton's v1.1 per-vault-node reframe (943bb220,
    4d6e2f9a Rule 1). This is a NEW check, not a rewrite of
    check_inbox_transition() — that function enforces a DIFFERENT
    invariant (items don't linger inside an '%inbox%'-titled container
    past their unclaimed window) and is explicitly NOT the D7-grounding
    walker per this dev-spec's own grounding (no existing function walks
    member_of up to a vault-entity). The two checks run independently and
    cannot disagree because they check different things; this generalizes
    the CONCEPT (per-vault D7 anchoring) that check_inbox_transition's
    docstring gestures at ("D7 enforcement") without actually walking the
    ownership chain.

    Two distinct failure classes (kept distinct per the dev-spec):
      - D7-per-vault violation (hard ERROR): a work-item's PRIMARY
        grounding member_of resolves to a DIFFERENT vault-node's
        vault-entity (foreign-primary) — the item is not grounded in its
        own vault. Severity class matches an orphan (no valid home
        anchor), but is a DISTINCT finding from the bare-orphan case
        (member_of entries exist; none of them ground HERE).
      - Illegal-but-present edge (ERROR, I3 semantics): an ADDITIONAL
        member_of edge (not the primary) points down-lattice or between
        incomparable segments. The record IS still validly grounded; the
        EDGE is excluded from adjacency/authority (see the composed-index
        exclusion this shares logic with, lib/gardener.py) and raised
        here as a lint ERROR — never silently dropped, never silently
        walked.

    Primary-vs-additional classification and the audience-lattice legality
    rule are NOT reimplemented here — both live in the single shared
    classification authority `lib.cross_vault_member_of` (imported below),
    which this check calls and which the composed-index edge-exclusion
    layer (tropo-rebuild-index.py -> lib/gardener.py) ALSO calls, so the
    two surfaces cannot drift apart on what counts as illegal.

    Real-substrate honesty (grounding finding, unchanged as of this
    build): zero live `type: vault` manifest instances exist in this
    studio, so there is exactly ONE implicit vault-node today (the whole
    studio) and at most one live `subtype: vault-entity` per the
    extraction_scope-proxied singleton (943bb220). This check is
    STRUCTURALLY per-vault-node (it groups work-items by their `segment`
    tag and validates each group's grounding against ITS OWN vault-entity
    set, ready for real multi-vault composition) — but against today's
    real index it only ever exercises that one implicit node, because no
    second node exists to disagree with it. A genuine live D7 violation
    surfaced by this check on real substrate is a real, disclosable
    finding, not a bug in the check.

    Segment/audience source: read from the composed index's own `segment`
    field (00-index.jsonl, written by the gardener pass) — this check is a
    READER of that tag, not a second discoverer (dev-spec §4).

    Returns (findings, checked, violation_count).
    """
    findings: list[str] = []
    checked = 0
    violations = 0

    index_path = vault / 'vault' / '00-index.jsonl'
    if not index_path.exists():
        return findings, checked, violations

    by_uid = {
        str(record['uid']): record
        for record in _index_union(vault)
        if record.get('uid')
    }
    if not by_uid:
        return findings, checked, violations

    # Local import — lib/ is a sibling directory; sys.path already set up at module level
    from lib.cross_vault_member_of import (
        classify_member_of_edges,
        default_two_segment_lattice,
    )

    # Build segment map from the composed index (gardener-assigned `segment`
    # field; falls back to 'private' — the safety-net default — for any
    # record missing it, matching gardener.py's own convention).
    segments: dict[str, str] = {
        uid: str(rec.get('segment') or 'private') for uid, rec in by_uid.items()
    }

    # Vault-entity home-node resolution: every live `subtype: vault-entity`
    # entity maps to the vault-node it anchors. CORRECTNESS FIX (Talos T26,
    # 2026-07-08, found by running this check against the real vault before
    # reporting BUILT — the original draft used the vault-entity's own 8-hex
    # UID as the node-identifier key, e.g. vault_entity_home_node['7f5b1d83']
    # = '7f5b1d83'. That is a DIFFERENT keyspace than `segments` above, which
    # holds the coarse tag ('private'/'os'/future 'team:<uid>') — so
    # `resolve_project_vault_node()` would return the vault-entity's raw UID
    # while `record_home = segments.get(record_uid)` returns 'private', and
    # `home == record_home` could NEVER be true for any real record. Live
    # proof: 259 false-positive D7-per-vault ERRORs on the real vault (every
    # record resolving to the one real vault-entity 7f5b1d83, which itself
    # is tagged segment:'private' in vault/00-index.jsonl) before this fix.
    # The correct home-node identifier is the vault-entity's OWN segment tag
    # — the same keyspace `segments` already uses for every other record.
    # This still generalizes cleanly: once real per-vault-root manifests
    # exist, a vault-entity's segment tag IS the manifest/vault-node UID
    # (the segment-assignment rule, bc25583d §7), so this is not a stopgap.
    vault_entity_home_node: dict[str, str] = {}
    for uid, rec in by_uid.items():
        if rec.get('type') == 'entity' and rec.get('subtype') == 'vault-entity':
            vault_entity_home_node[uid] = segments.get(uid, 'private')

    if not vault_entity_home_node:
        # No live vault-entity at all -> nothing for this check to ground
        # against. Distinct from "checked but clean" — genuinely nothing to
        # validate (matches the mount-gate's own "checked==0" convention
        # when there is no real substrate to exercise).
        return findings, checked, violations

    # B4a single-adapter cutover (dev-spec 0bfa771d; brief 252534fe §4/§5): once a
    # group authority is installed the audience-lattice legality is derived from the
    # ONE verified AudiencePolicy (via lib.audience_gate.B4aLattice), never a
    # synthesized default_two_segment_lattice(). The Gardener's composed-index
    # edge-exclusion layer consumes the SAME adapter, so the two surfaces cannot
    # drift. Pre-cutover (no installed authority) the prior default lattice is kept
    # so a Studio without the B4a runtime is unaffected; a load failure under
    # cutover falls back defensively rather than crashing the validator.
    lattice = default_two_segment_lattice()
    if _b4a_cutover_active(vault):
        try:
            from lib.audience_gate import B4aLattice, load_policy
            lattice = B4aLattice(load_policy(vault))
        except Exception:
            lattice = default_two_segment_lattice()

    work_item_types = {'task', 'work-item', 'workitem'}
    for uid, rec in by_uid.items():
        rtype = str(rec.get('type') or '')
        if rtype not in work_item_types:
            continue
        member_of_list = rec.get('member_of') or []
        if isinstance(member_of_list, str):
            member_of_list = [member_of_list]
        if not member_of_list:
            continue  # bare orphan — pre-existing, different failure class

        checked += 1
        grounding, edges = classify_member_of_edges(
            rec, by_uid, vault_entity_home_node, segments, lattice,
        )

        # Terminal-state carve-out (Argus A129, 2026-07-09, Mike-locked): a
        # D7-per-vault violation on a CLOSED/ARCHIVED record degrades from
        # ERROR to WARN. Rationale: (1) terminal records are immutable history
        # whose grounding reflects the taxonomy in force when they were live —
        # re-grounding them to satisfy a later-shipped rule is substrate
        # revisionism; (2) this does NOT weaken the leak-prevention covenant —
        # publication is gated by extraction_scope:ship (mount-gate / manifest /
        # sovereignty proof), NOT by this grounding-hygiene check, and the
        # foreign/illegal edge is ALREADY excluded from the composed authority
        # graph regardless of severity; (3) empirically only pre-rule archived
        # history trips this (8/8 findings at introduction were closed+archived,
        # zero live) — the signature of a rule that should bind LIVE work and
        # treat terminal records as a lint. LIVE records with the same shape
        # remain hard ERROR (locked by test_terminal_carveout_* in
        # tests/test_cross_vault_member_of_4275b01c.py).
        status = str(rec.get('status') or '')
        state = str(rec.get('state') or '')
        is_terminal = status in _TERMINAL_STATUSES or state in ('archived', 'retired')

        if grounding.foreign_primary:
            if is_terminal:
                findings.append(
                    f'[WARN] {uid} (type:{rtype}) — D7-per-vault grounding on a TERMINAL '
                    f'record (status={status!r}/state={state!r}): PRIMARY grounding '
                    f'member_of={grounding.primary_uid!r} traces to vault-node '
                    f'{grounding.primary_home_node!r}, record homed in vault-node '
                    f'{grounding.record_home_node!r}. Immutable history — hygiene, not a '
                    f'hard failure (foreign edge already excluded from the composed '
                    f'authority graph); live records with this shape remain ERROR '
                    f'(ADR-051 D7-per-vault, 4275b01c §2a; terminal carve-out A129 Mike-locked)'
                )
            else:
                violations += 1
                findings.append(
                    f'[ERROR] {uid} (type:{rtype}) — D7-per-vault violation: PRIMARY '
                    f'grounding member_of={grounding.primary_uid!r} traces to vault-node '
                    f'{grounding.primary_home_node!r}, but this record is homed in '
                    f'vault-node {grounding.record_home_node!r} — not grounded in its OWN '
                    f'vault (ADR-051 D7-per-vault, dev-spec 4275b01c §2a)'
                )
        elif not grounding.grounded:
            # member_of entries exist but none resolve to ANY vault-entity —
            # the pre-existing bare-orphan case (f2e8a7b1 D7); not this
            # check's new failure class, so not counted as a NEW violation
            # here (the inbox-transition / existing orphan machinery is the
            # authority for that case). No finding emitted to avoid double-
            # reporting the same record under two checks.
            pass

        for edge in edges:
            if not edge.legal:
                reason = (
                    f"target segment {edge.target_segment!r} is NARROWER than source "
                    f"segment {edge.source_segment!r}"
                    if edge.relation == 'down' else
                    f"segments {edge.source_segment!r} and {edge.target_segment!r} are "
                    f"INCOMPARABLE (neither is equal-or-wider)"
                )
                if is_terminal:
                    findings.append(
                        f'[WARN] {uid} (type:{rtype}) — illegal-but-present member_of edge '
                        f'to {edge.target_uid!r} on a TERMINAL record '
                        f'(status={status!r}/state={state!r}): {reason}. Already excluded '
                        f'from adjacency + authority for ALL viewers (I3, dd16c90c / '
                        f'c2b1b612 §3 v2.1); terminal history — hygiene, not a hard failure '
                        f'(live records with this shape remain ERROR; carve-out A129 Mike-locked).'
                    )
                else:
                    violations += 1
                    findings.append(
                        f'[ERROR] {uid} (type:{rtype}) — illegal-but-present member_of edge '
                        f'to {edge.target_uid!r}: {reason}. Excluded from adjacency + '
                        f'authority for ALL viewers (I3, dd16c90c / c2b1b612 §3 v2.1); never '
                        f'silently dropped, never silently walked.'
                    )

    return findings, checked, violations


# ---------------------------------------------------------------------------
# Pipeline-Activation Coupling Gate (8f15f08d) — ERROR-ratchet LIVE.
# The 9 pre-existing off-pipeline dev-specs this docstring's "VERIFY-BEFORE-
# DESIGNING FINDING" section named (5e12ab9c, 81e52840, dabe7c64, 98b9610a,
# 0c61a52b, 55c33476, c036dd4b, 2fe61817, bc730fe4) were cured by Talos T26
# 2026-07-08 per register 2b12e41d / work-order event 00005914 (Argus A127).
# All 22 checked dev-specs now correlate (0 violations, verified live before
# this edit) — ratcheting per 8f15f08d's own design: "no second hand-edit
# ... beyond removing the emptied allowlist."
# ---------------------------------------------------------------------------

# 8f15f08d §Grandfather: the two dev-specs Mike-ruled "feed-the-pipeline"
# (8e8a0962) for — cured retroactively by Talos T25 2026-07-07 (activations
# 413db7f5 / 019c765a). The 9-UID second wave (see header note above) was
# cured 2026-07-08 by Talos T26. Allowlist now EMPTY — every future
# off-pipeline lock is an ERROR, not a WARN.
DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST = frozenset()

# build_status values that count as "reached shippable state" for the
# escalation arm (AC-3). Sourced from dev-spec.capsule's observed enum
# (built_pending_verify is in-flight, NOT terminal).
_TERMINAL_BUILD_STATUS = frozenset({'mike-signed-accepted'})


def check_dev_spec_activation_coupling(vault: Path, customer_mode: bool = False) -> tuple[list[str], int, int]:
    """8f15f08d — Pipeline-Activation Coupling Gate.

    A dev-spec that has turned its ignition key (status: locked, and/or a
    terminal build_status e.g. mike-signed-accepted) must have a correlated
    pipeline activation: at least one type:activation entry anywhere in
    vault/files/ whose dev_spec_uid equals the dev-spec's uid, of ANY status
    (existence proves the pipeline was ever opened — a RETIRED activation
    still proves it did; see 8f15f08d's 2ffdd9d6/35c12763 precedent). If none
    exists, the dev-spec reached lock/shippable state off-pipeline.

    Ships WARN per Argus's explicit directive ("ship it as WARN now").
    8f15f08d's own text frames the ERROR-ratchet as auto-firing once the
    named 2-uid grandfather allowlist "empties" as each spec is cured.

    VERIFY-BEFORE-DESIGNING FINDING (Talos T25, 2026-07-07): a live scan of
    this vault at the moment both named UIDs were cured found 9 OTHER
    pre-existing, unrelated dev-specs already status:locked with NO
    correlated activation (5e12ab9c, 81e52840, dabe7c64, 98b9610a [ALSO
    carries a terminal build_status — same escalated class as v1.81/v1.82],
    0c61a52b, 55c33476, c036dd4b, 2fe61817, bc730fe4) — contradicting
    8f15f08d's own AC-6 premise that only the two named UIDs would be
    flagged on live substrate. A ratchet that auto-fires the instant the
    2-uid allowlist's members are individually cured would therefore go
    ERROR-live on 9 unrelated dev-specs the moment this check ships
    (v1.81/v1.82 having just been cured in the same session) — breaking
    tropo-validate.py studio-wide on entries this dev-spec never scoped or
    triaged.

    Talos judgment call (Rule 2 — flag, don't guess past a real conflict):
    the ERROR-ratchet is implemented as a STATIC severity gate keyed on the
    literal DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST constant being non-empty —
    i.e. exactly mirroring this file's OTHER ratchet-labeled check
    (check_mint_id_chokepoint, which always emits [WARN] in code today; its
    "ERROR-ratchet after the first clean pass" is a documented FUTURE manual
    amendment, not a value computed live from the current scan). Cured
    members already stop being reported at all (functionally "dropped");
    the named constant itself is the single, visible, auditable hand-edit
    that flips every future violation to ERROR — "no second hand-edit of
    the ratchet ... beyond removing the emptied allowlist" (8f15f08d,
    literally true here: emptying the constant is the ONLY edit needed).
    This is deliberately SAFE to ship today (both named UIDs cured, constant
    intentionally left non-empty pending Argus's judgment on the 9 other
    UIDs — separate cleanup item vs allowlist expansion vs accepting a wider
    ratchet bar) and remains auto-releasing in the sense 8f15f08d intends:
    the day Argus empties the constant, the check ratchets to ERROR with no
    other code change.

    Returns (findings, checked, violation_count).
    """
    findings: list[str] = []
    files_dir = vault / 'vault' / 'files'
    checked = 0
    violations = 0
    if not files_dir.is_dir():
        return findings, checked, violations

    correlated_dev_spec_uids: set[str] = set()
    dev_specs: list[tuple[str, dict]] = []

    for f in sorted(files_dir.glob('*.md')):
        try:
            text = f.read_text(errors='replace')
        except Exception:
            continue
        fm_text = split_frontmatter(text)
        if fm_text is None:
            continue
        try:
            fm = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        entry_type = fm.get('type')
        if entry_type == 'activation':
            dsu = fm.get('dev_spec_uid')
            if dsu:
                correlated_dev_spec_uids.add(str(dsu))
        elif entry_type == 'dev-spec':
            dev_specs.append((f.name, fm))

    # Pass 1: find every off-pipeline dev-spec + tally for the ratchet decision.
    off_pipeline: list[tuple[str, str, str, Optional[str], bool]] = []
    for fname, fm in dev_specs:
        uid = str(fm.get('uid') or Path(fname).stem)
        status = fm.get('status')
        build_status = fm.get('build_status')
        is_terminal_build = build_status in _TERMINAL_BUILD_STATUS
        triggers = (status == 'locked') or is_terminal_build
        if not triggers:
            continue
        checked += 1
        if uid in correlated_dev_spec_uids:
            continue  # cured — has a real activation on record, any status
        off_pipeline.append((fname, uid, status, build_status, is_terminal_build))

    violations = len(off_pipeline)
    # Ratchet: severity is a STATIC function of the named allowlist constant
    # (see docstring "Talos judgment call" above), NOT of this run's finding
    # count — a per-run "violations == 0" test is circular (a fresh
    # violation always makes the count >= 1, so it could never self-select
    # ERROR) and, worse, would auto-fire ERROR the instant the 2 named UIDs
    # were cured while 9 unrelated pre-existing violations remained. The
    # ONLY way this check reaches ERROR mode is a future hand-edit emptying
    # DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST — exactly the single-hand-edit
    # ratchet 8f15f08d names, mirroring check_mint_id_chokepoint's real
    # (always-WARN-until-a-future-code-change) behavior in this same file.
    ratchet_is_error = (len(DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST) == 0)
    severity = 'ERROR' if ratchet_is_error else 'WARN'

    # Shipped-subset guard (vela-v65, 2026-07-11; A132 release-mode repair,
    # 2026-07-16): a shipped box does not carry
    # the source studio's activation entries (activations are argo-internal;
    # only a generic template activation ships). So inside a customer extract,
    # every locked dev-spec whose correlated activation stayed home will fire
    # as off-pipeline — but that's an expected outward-ref, not a real defect.
    # Same principle as the UID outward-ref handling in Check 35: the shipped
    # box cannot verify source-studio pipeline correlations. Downgrade all
    # findings to INFO in customer mode so the shipped self-test (tropo-test.py
    # which passes --customer) doesn't fail its own S2 in-box gate on the
    # unavoidable absence of source-studio activation records. The caller
    # supplies this for both --customer and --release; those are the same
    # subset boundary for this source-governance-only coupling check.
    if customer_mode:
        severity = 'INFO'
        violations = 0  # don't count toward the fail tally in customer mode

    for fname, uid, status, build_status, is_terminal_build in off_pipeline:
        grandfathered = uid in DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST
        escalation = (
            f' [ESCALATED — build_status:{build_status} reached shippable state off-pipeline]'
            if is_terminal_build else ''
        )
        cure_note = (
            ' — grandfathered per 8e8a0962 feed-the-pipeline cure path; cure by opening a '
            'correlated type:activation (any status) with dev_spec_uid matching this uid'
            if grandfathered else
            ' — NOT on the named grandfather allowlist; open a correlated activation to cure '
            '(see 8f15f08d for the coupling rule)'
        )
        findings.append(
            f'[{severity}] vault/files/{fname} — dev-spec {uid} is status:{status!r}'
            + (f' with build_status:{build_status!r}' if build_status else '')
            + f' but has NO correlated type:activation (dev_spec_uid: {uid})'
            + escalation + cure_note
        )

    return findings, checked, violations


# ---------------------------------------------------------------------------
# Shard-index consistency (c6f6bea4, ADR-051 Fork 4) — the staleness guard.
# ---------------------------------------------------------------------------

def check_shard_index_consistency(vault: Path) -> tuple[list[str], int, int]:
    """c6f6bea4 (ADR-051 Fork 4) — shard-keyed incremental composed-index
    staleness guard.

    Read-only. For every vault_uid pinned in .tropo-studio/compose.lock,
    re-checks (via the SHARED lib/shard_index.py module — the same
    reachability/pin-match primitive tropo-rebuild-index.py's writer path
    uses, so validator and writer cannot silently disagree on what "stale"
    means) whether that vault's shard cache is:
      - REUSABLE: cache present, .meta resolved_commit == the compose.lock
        pin. No finding.
      - CANNOT-COMPOSE: cache missing entirely, OR .meta resolved_commit !=
        the pin (stale) AND mount_path is unreachable (so the next rebuild
        cannot self-heal it either), OR the compose.lock record itself is
        missing resolved_commit. This is the fail-closed case the dev-spec
        names explicitly: "a vault pinned in compose.lock whose shard cache
        is missing, whose .meta commit does not equal the pin, or whose
        mount_path is unreachable is surfaced as CANNOT-COMPOSE... NEVER
        served as a stale/partial shard passed off as complete."

    SEVERITY — [WARN], not [ERROR] — deliberate judgment call (disclosed in
    the c6f6bea4 build report, not a default this file's other checks use
    without reasoning): a stale/missing shard cache is a SELF-HEALING,
    LOCAL-ONLY build-artifact condition — the very next `--apply` rebuild
    re-derives it automatically as long as mount_path is still reachable
    (see resolve_shards(): a stale-but-reachable pin re-derives, it does
    not error). It only escalates to a genuinely un-self-healing condition
    when mount_path is ALSO unreachable — still [WARN] here, because "the
    shard is excluded, not corrupting the index" (fail-closed exclusion,
    the invariant this check exists to prove) is itself the safe outcome;
    an operator needs to know a mount has gone stale/unreachable, but
    nothing about the LOCAL studio's own governed content (vault/files/,
    the local shard) is at risk — contrast with check_vault_manifest_
    governed_write_gate's [ERROR], which fires on a hand-edited GOVERNED
    ARTIFACT (a trust-boundary breach), a categorically worse condition
    than "a derived cache hasn't caught up to a pin yet."

    Zero real type:vault mounts + an absent/empty compose.lock (this
    studio's real, current state) mean checked==0, violations==0 today —
    exactly the "lands on a clean, verified base with no migration surface"
    posture the mount-gate (409ef1cc) and member_of (4275b01c) checks
    already established for this same zero-mount reality.
    """
    findings: list[str] = []
    checked = 0
    violations = 0

    lock_path = vault / DEFAULT_COMPOSE_LOCK_REL
    if not lock_path.is_file():
        return findings, checked, violations

    # Local import — lib/ is a sibling directory; sys.path already set up at module level
    # (mirrors check_cross_vault_member_of's own local-import convention above).
    from lib.shard_index import staleness_findings

    statuses = staleness_findings(vault)
    for status in statuses:
        checked += 1
        if status.action == 'cannot-compose':
            violations += 1
            findings.append(
                f'[WARN] shard-index — vault_uid {status.vault_uid!r} CANNOT-COMPOSE: '
                f'{status.reason} (excluded from vault/00-index.jsonl this rebuild — '
                f'fail-closed, never served stale/partial; c6f6bea4 §4)'
            )

    return findings, checked, violations


# ---------------------------------------------------------------------------
# Publish boundary (44badb55, ADR-051 — the v1.84 two-machine sovereignty
# proof / Git Beat 2 federation transport). Independent re-check, never
# trusting tropo-publish.py's own receipt.
# ---------------------------------------------------------------------------

def check_publish_boundary(vault: Path) -> tuple[list[str], int, int]:
    """44badb55 (ADR-051) — client-side, fail-closed re-validation of every
    mounted vault's published team-branch tip. "B independently verifies —
    never trusts A's receipt" (Ruling 10): this re-derives everything from
    the actual committed git object graph, never from tropo-publish.py's
    JSON receipt.

    For each vault_uid pinned in .tropo-studio/compose.lock whose mount_path
    is reachable AND carries a local `lib.segment.TEAM_BRANCH_DEFAULT` ref
    (i.e. at least one publish has ever completed from that mount):

      1. Physical separation (§1): mount_path's .git must be DISTINCT from
         this studio's own .git (lib.segment.check_gitdir_distinct) — [ERROR]
         and skip the rest for that vault_uid if it is NOT (too dangerous to
         keep re-validating a "team vault" that is actually this repo).
      2. No submodules / single worktree (lib.segment.check_no_submodules /
         check_single_worktree) — [ERROR] each.
      3. Ancestry (lib.segment.verify_clean_ancestry): every commit reachable
         from the tip has at most one parent, and exactly one has zero —
         [ERROR] on any merge or non-single-root history (private-origin
         ancestry may have entered).
      4. No gitlinks (mode 160000 tree entries) reachable from the tip —
         [ERROR] each (submodule/gitlink objects are an ancestry/leak
         surface regardless of whether .gitmodules itself is present).
      5. No tags/notes present in the mount_path's own ref list that a push
         could have carried alongside the branch — [ERROR] each (44badb55
         requires pushing ONLY the single branch ref).
      6. No LFS pointer files / .gitattributes LFS filters in the committed
         tree — [ERROR] each (an LFS pointer is a content-addressed
         indirection this covenant's content-hash receipt does not cover).
      7. Re-reads the COMMITTED tree at the tip via `git show` (NEVER the
         working tree — this is what closes the TOCTOU between whatever
         tropo-publish.py's OWN filter saw and what is actually sitting in
         the object store) and independently re-derives BOTH gates
         (lib.segment.is_public_scope + lib.segment.derive_segment ==
         this vault's own manifest uid, per Ruling 3) for every vault/files/
         *.md blob. ANY file failing either gate is an [ERROR] — the
         covenant was violated and content that should never have crossed
         is sitting in a shared object store.
      8. Reflog (lib.segment.check_reflog_disabled) against the compose.lock
         record's own `remote` field, if present — [ERROR] if verifiably
         enabled; [WARN] (not ERROR) when the remote is a non-local URL and
         cannot be checked client-side — a named platform limit (Ruling 11),
         disclosed rather than silently treated as passing.

    Zero real published team-vaults exist in this studio today (no
    compose.lock entry has ever completed a publish), so checked==0,
    violations==0 currently — the same "lands on a clean, verified base"
    posture the other ADR-051 checks (mount-gate, member_of, shard-index)
    already established for this same zero-mount reality.
    """
    findings: list[str] = []
    checked = 0
    violations = 0

    lock_path = vault / DEFAULT_COMPOSE_LOCK_REL
    if not lock_path.is_file():
        return findings, checked, violations

    try:
        lock_data = json.loads(lock_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return findings, checked, violations
    vaults = lock_data.get('vaults') if isinstance(lock_data, dict) else None
    if not isinstance(vaults, dict):
        return findings, checked, violations

    # Local import — lib/ is a sibling directory; sys.path already set up at
    # module level (mirrors check_cross_vault_member_of's own convention).
    from lib.segment import (
        TEAM_BRANCH_DEFAULT, check_gitdir_distinct,
        check_no_submodules, check_single_worktree,
        check_reflog_disabled, verify_clean_ancestry,
        find_boundary_violations_in_committed_tree,
    )

    # NOTE: `vault` here is THIS FILE's convention for the studio root (see
    # resolve_vault_root — it returns the directory containing BOTH a
    # vault/ folder and a .tropo/ folder), not <studio>/vault/ itself.
    studio_root = vault

    for vault_uid, record in sorted(vaults.items()):
        mount_path_str = record.get('mount_path') if isinstance(record, dict) else None
        if not mount_path_str:
            continue
        mount_path = Path(mount_path_str)
        if not mount_path.is_dir() or not (mount_path / '.git').exists():
            continue  # unreachable mount is check_shard_index_consistency's finding, not this check's

        tip_result = subprocess.run(
            ['git', '-C', str(mount_path), 'rev-parse', '--verify', f'refs/heads/{TEAM_BRANCH_DEFAULT}'],
            capture_output=True, text=True, timeout=10,
        )
        if tip_result.returncode != 0:
            continue  # no publish has ever completed from this mount — nothing to re-validate yet
        tip = tip_result.stdout.strip()
        checked += 1

        gitdir_err = check_gitdir_distinct(studio_root, mount_path)
        if gitdir_err:
            violations += 1
            findings.append(f'[ERROR] publish-boundary — vault_uid {vault_uid!r}: {gitdir_err}')
            continue  # too dangerous to keep re-validating a "team vault" that IS this studio's own repo

        for check_fn in (check_no_submodules, check_single_worktree):
            err = check_fn(mount_path)
            if err:
                violations += 1
                findings.append(f'[ERROR] publish-boundary — vault_uid {vault_uid!r}: {err}')

        ancestry_holds, ancestry_detail = verify_clean_ancestry(mount_path, tip)
        if not ancestry_holds:
            violations += 1
            findings.append(f'[ERROR] publish-boundary — vault_uid {vault_uid!r}: ancestry check FAILED: {ancestry_detail}')

        remote_url = record.get('remote') if isinstance(record, dict) else None
        if remote_url:
            reflog_ok, reflog_detail = check_reflog_disabled(remote_url)
            if not reflog_ok:
                violations += 1
                findings.append(f'[ERROR] publish-boundary — vault_uid {vault_uid!r}: {reflog_detail}')
            elif 'named platform limit' in reflog_detail:
                findings.append(f'[WARN] publish-boundary — vault_uid {vault_uid!r}: {reflog_detail}')

        tags_result = subprocess.run(['git', '-C', str(mount_path), 'tag'], capture_output=True, text=True, timeout=10)
        if tags_result.returncode == 0 and tags_result.stdout.strip():
            violations += 1
            findings.append(
                f'[ERROR] publish-boundary — vault_uid {vault_uid!r}: tag(s) present '
                f'({tags_result.stdout.split()!r}) — 44badb55 requires pushing ONLY the single branch ref'
            )
        notes_result = subprocess.run(
            ['git', '-C', str(mount_path), 'for-each-ref', 'refs/notes/'],
            capture_output=True, text=True, timeout=10,
        )
        if notes_result.returncode == 0 and notes_result.stdout.strip():
            violations += 1
            findings.append(f'[ERROR] publish-boundary — vault_uid {vault_uid!r}: refs/notes/* present — refused')

        gitattributes_result = subprocess.run(
            ['git', '-C', str(mount_path), 'show', f'{tip}:.gitattributes'],
            capture_output=True, text=True, timeout=10,
        )
        if gitattributes_result.returncode == 0 and 'filter=lfs' in gitattributes_result.stdout:
            violations += 1
            findings.append(
                f'[ERROR] publish-boundary — vault_uid {vault_uid!r}: .gitattributes at tip {tip[:12]} '
                f'declares an LFS filter — refused (an LFS pointer is a content-addressed indirection '
                f'this covenant\'s content-hash receipt does not cover)'
            )

        # BOUNCE finding #1/#4 (Argus A128, 2026-07-09): use the compose.lock
        # -recorded vault_uid (established independently, at ORIGINAL
        # mount-gate time) as the authoritative comparator — NOT a fresh
        # read_vault_manifest_uid(mount_path) re-derived from the SAME
        # content being audited. The published team-main tree by
        # construction never carries .tropo/vault-manifest.md, so
        # re-deriving here would silently resolve None and either
        # over-block everything or (worse, pre-fix) quietly compare a
        # value against itself.
        tree_violations = find_boundary_violations_in_committed_tree(mount_path, vault_uid, tip)
        for v in tree_violations:
            violations += 1
            findings.append(f'[ERROR] publish-boundary — vault_uid {vault_uid!r}: {v}')

    return findings, checked, violations


def check_mint_provenance(vault: Path) -> tuple[list[str], int, int]:
    """Governed Autonomy S2 (bba40cd7) fail-loud floor: a governed file under
    vault/files/ whose type carries a §Template leg (mint-governed, closed
    registry) but has NO matching row in vault/00-index.jsonl is invisible to
    every index-driven surface -- exactly the defect class that motivated S2
    (029972a1: 8 tools invisible to the index from malformed hand-authored
    frontmatter). ERRORs loudly, naming the file + the cure. Hand-writes can't
    be physically prevented (an honest ceiling per the spec) -- they become
    immediately loud and invalid instead of silently orphaned.

    Scoped to types carrying a §Template leg only -- types with no leg yet are
    outside S2's closed-registry enforcement (nothing migrates in S2; the 90%
    of types without a leg are simply not checked here, not grandfathered-fail).

    Returns (findings, total_checked, defect_count).
    """
    import json as _json
    import re as _re

    vault_root = vault.parent if (vault / 'files').is_dir() else vault
    capsules_dir = vault_root / 'vault' / 'capsules'
    files_dir = vault_root / 'vault' / 'files'
    index_path = vault_root / 'vault' / '00-index.jsonl'

    if not files_dir.is_dir():
        return [], 0, 0

    # Which types carry a §Template leg? Cheap: ~80 capsule files, not per-instance.
    leg_types: set[str] = set()
    if capsules_dir.is_dir():
        heading_re = _re.compile(r'^##[ \t]+§Template\b', _re.MULTILINE)
        for cap in capsules_dir.glob('tropo-*.capsule.md'):
            try:
                text = cap.read_text(errors='ignore')
            except Exception:
                continue
            if heading_re.search(text):
                leg_types.add(cap.name[len('tropo-'):-len('.capsule.md')])

    if not leg_types:
        return [], 0, 0

    indexed_uids = _index_union_uids(vault)

    fm_re = _re.compile(r'^---\n(.*?)\n---', _re.DOTALL)
    uid_re = _re.compile(r'^uid:\s*([0-9a-f]{8})\s*$', _re.MULTILINE)
    type_re = _re.compile(r'^type:\s*"?([\w-]+)"?\s*$', _re.MULTILINE)

    findings: list[str] = []
    total_checked = 0
    defect_count = 0

    for f in sorted(files_dir.glob('*.md')):
        try:
            text = f.read_text(errors='ignore')
        except Exception:
            continue
        m = fm_re.match(text)
        if not m:
            continue
        type_m = type_re.search(m.group(1))
        if not type_m or type_m.group(1) not in leg_types:
            continue
        total_checked += 1
        uid_m = uid_re.search(m.group(1))
        uid = uid_m.group(1) if uid_m else f.stem
        if uid not in indexed_uids:
            defect_count += 1
            findings.append(
                f"[ERROR] {uid} ({type_m.group(1)}): mint-governed type has NO row in "
                f"the current/archive index union -- invisible to every index-driven surface. "
                f"Cure: python3 vault/tools/tropo-rebuild-index.py --only {uid} "
                f"(hand-authored bypass of `mint file` -- the fail-loud floor per bba40cd7)."
            )

    return findings, total_checked, defect_count


# S1 verification catch (Argus A130, 7627b589): T28's un-sandboxed test runs of
# pipeline-runtime.py wrote 43 fixture-shaped events (activation_uid/pipeline_run_uid
# like "act2"/"act3") into the production event log before the sandbox-mode fix
# (Talos T29, 9e7003b1.py _emit_pipeline_event) landed. Append-only log -- cannot be
# deleted, only documented. Exhaustive, explicit allowlist (not a date/id-threshold
# heuristic) so nothing new can silently ride in under a loose cutoff rule.
_KNOWN_PIPELINE_EVENT_POLLUTION_IDS = frozenset({
    '00006208', '00006209', '00006210', '00006211', '00006212', '00006213', '00006214',
    '00006215', '00006216', '00006217', '00006238', '00006239', '00006240', '00006244',
    '00006245', '00006246', '00006263', '00006264', '00006265', '00006267', '00006268',
    '00006269', '00006271', '00006272', '00006273', '00006274', '00006275', '00006276',
    '00006277', '00006278', '00006279', '00006280', '00006281', '00006282', '00006283',
    '00006284', '00006285', '00006289', '00006290', '00006291', '00006296', '00006297',
    '00006298',
})


def check_every_agent_can_still_boot(vault: Path) -> tuple[list[str], int, int]:
    """Can every agent in the fleet still be born?

    WHY THIS EXISTS (metis-g97, 2026-07-29): the G2 hardening made predecessor
    derivation require a keyed predecessor, but only two activation entries were
    ever retrofitted with keys. That left 19 agents unable to hand off to a
    successor -- argus, vela, orpheus, po, cosmo, stratus, pipeline-runtime,
    every sa.* and every coordinator. It shipped silently and sat for three days,
    because agent BIRTH is the only operation that trips it and only one agent
    had been born since.

    That is the expensive failure shape: a gate on the boot path fails at the one
    moment nobody is home, and the agent who could fix it is the agent who cannot
    start. Nothing in the studio asked this question, so nobody could see it.
    Now something asks it on every validate run.

    A live agent whose current generation is still active is NOT a defect -- that
    is ADR-016 holding correctly. Only a terminal predecessor that cannot produce
    a successor counts.

    Returns (findings, agents_checked, blocked_count).
    """
    import sys as _sys

    findings: list[str] = []
    tools = vault / 'vault' / 'tools'
    if str(tools) not in _sys.path:
        _sys.path.insert(0, str(tools))
    try:
        from lib import authority_chain as _ac
    except Exception as exc:  # pragma: no cover - import surface only
        return ([f'authority chain unavailable: {exc}'], 0, 0)

    try:
        records = _ac.load_canonical_activation_entries(vault)
    except Exception as exc:
        return ([f'activation entries unreadable: {exc}'], 0, 1)

    by_agent: dict[str, list] = {}
    for record in records:
        if record.agent and record.activation_type == 'activation':
            by_agent.setdefault(record.agent, []).append(record)

    # An ENDED lineage is not a broken one. Never ask about it again.
    #
    # An agent whose unified entry declares `superseded_by:` has been formally
    # retired with no successor to come. Asking "can this lineage produce a
    # successor?" of a lineage somebody deliberately ended produces a permanent
    # red line — and a health check that is permanently red teaches the crew to
    # ignore the one instrument that would have caught a real blocker.
    #
    # This is the tropo agent, and it is worth naming because the failure is not
    # the one it looks like. The tropo agent was renamed to Po and retired on
    # 2026-08-01 by argus-a143, carrying Mike's verbatim ruling and the explicit
    # sentence "no T2 is to be born". THE ANSWER HAS BEEN WRITTEN DOWN SINCE
    # THEN. The data was never wrong. This check simply never read it, and so
    # kept reporting a decided question as an open defect — which agent after
    # agent then dutifully raised with Mike as a loose end. Mike, 2026-08-03:
    # "I never want to hear about this issue again."
    #
    # The general lesson, which is the same one this whole session is about: an
    # instrument that cannot see a decision will keep re-litigating it, and the
    # cost lands on the human every single time.
    ended: dict[str, str] = {}
    agents_root = vault / 'vault' / 'agents'
    if agents_root.is_dir():
        for path in sorted(agents_root.glob('*.md')):
            try:
                fm = split_frontmatter(path.read_text(errors='replace'))
            except OSError:
                continue  # unreadable is UNCHECKED, never "ended" — never silently skip
            if not fm or (get_scalar(fm, 'type') or '') != 'agent':
                continue
            slug = (get_scalar(fm, 'agent') or '').strip()
            superseded = (get_scalar(fm, 'superseded_by') or '').strip()
            if slug and superseded:
                ended[slug] = superseded

    checked = 0
    blocked = 0
    for agent in sorted(by_agent):
        if agent in ended:
            continue  # deliberately ended; superseded_by names the successor role
        lineage = by_agent[agent]
        latest = max(
            lineage, key=lambda r: (r.activated_at, r.generation, r.uid)
        )
        # 163b3923 R3 — a still-active predecessor IS ADR-016 working, but
        # skipping those agents entirely made this check structurally unable to
        # see a whole class of birth blocker. It hid two on 2026-07-31 alone:
        # Po P2 (activation open 29 days after a session that ended without
        # ceremony) and Vela V72 (a live agent whose own activation frontmatter
        # was unparseable, poisoning her lineage for fifteen hours). Both were
        # found by hand, one by a control probe on an agent expected to pass.
        #
        # So probe them too, and separate the outcomes: a refusal that is ONLY
        # "predecessor must be terminal" is ADR-016 holding and is reported as
        # latent, not blocked. Any OTHER refusal is a real birth blocker that
        # will fire the moment that agent retires, and is reported now.
        predecessor_live = str(latest.status).strip().lower() not in {
            'retired', 'retiring', 'stale', 'closed'
        }
        if predecessor_live:
            try:
                _ac.derive_new_activation_predecessor(
                    records,
                    agent=agent,
                    agent_class=(
                        latest.canonical_agent_class
                        or latest.agent_class
                        or 'executive'
                    ),
                    generation=_next_probe_generation(latest.generation),
                )
            except Exception as exc:
                detail = str(exc)
                if 'must be terminal' not in detail:
                    # Something other than liveness blocks this birth. It is
                    # already true and will fire the moment they retire.
                    blocked += 1
                    findings.append(
                        f'{agent} ({latest.generation}+1) LATENT BIRTH BLOCKER '
                        f'(predecessor still {latest.status}; this fires when '
                        f'they retire): {detail}'
                    )
                elif (
                    _agent_class_has_a_birth_lifecycle(latest)
                    and _activation_is_past_stale_threshold(latest)
                ):
                    # "Predecessor must be terminal" is ADR-016 holding when the
                    # agent is genuinely working. Long past its own stale
                    # threshold it means the opposite: the session ended without
                    # ceremony and the activation was never closed, so the
                    # successor is blocked by an open record nobody will close
                    # on their own. This is exactly Po P2 — 29 days open, no
                    # events, no commits, no reflection — which sat unseen
                    # because this check skipped live predecessors entirely.
                    blocked += 1
                    findings.append(
                        f'{agent} ({latest.generation}+1) STALE OPEN ACTIVATION: '
                        f'predecessor {latest.uid} is status:{latest.status} but '
                        f'past its own stale threshold (activated '
                        f'{latest.activated_at}). Its session ended without '
                        f'closing. SELF-CLEARING: booting {agent} now sweeps this '
                        f'record automatically (metis-g100, 2026-08-03) — just '
                        f'activate them. To clear it without a boot: '
                        f'40b2f455.py close --activation-uid {latest.uid} '
                        f'--target-status retired --abandoned --authorized-by <you>.'
                    )
            continue
        checked += 1
        probe = f'{latest.generation}+1' if latest.generation else 'next'
        # Probe with the CANONICAL class, not the entry's declared one: a class
        # mismatch is a different defect and must not masquerade as a boot block.
        probe_class = (
            latest.canonical_agent_class or latest.agent_class or 'executive'
        )
        try:
            _ac.derive_new_activation_predecessor(
                records,
                agent=agent,
                agent_class=probe_class,
                generation=_next_probe_generation(latest.generation),
            )
        except Exception as exc:
            blocked += 1
            findings.append(
                f'{agent} ({probe}) LINEAGE DEFECT (birth is NOT blocked): {exc}'
            )
    return (findings, checked, blocked)


def _agent_class_has_a_birth_lifecycle(record) -> bool:
    """Whether this activation belongs to something that is BORN, not just run.

    Scoping matters more than coverage here. Without it the stale-predecessor
    branch reports every long-open `pipeline` run — including six recycled
    demo records from a single 2026-05-16 batch — as CANNOT BOOT, which buries
    the one real finding among seven false ones. A health check people learn to
    skip is the failure this whole line of work exists to fix. Pipeline runs are
    closed by Vela's Tier 1 stale-sweep; they do not produce successors.
    """
    agent_class = str(
        getattr(record, 'canonical_agent_class', '')
        or getattr(record, 'agent_class', '')
        or ''
    ).strip().lower()
    if agent_class in {'pipeline', 'worker', 'child-agent'}:
        return False
    # A record recovered from the recycle bin is deleted substrate; it must not
    # drive a live health verdict.
    source = str(getattr(record, 'source_path', '') or '')
    if '/recycle/' in source or '/99-recycle/' in source:
        return False
    return True


def _activation_is_past_stale_threshold(record) -> bool:
    """Whether a still-open activation has outlived its own declared threshold.

    Deliberately conservative: an unparseable date or a missing threshold
    returns False. A false positive here accuses a working agent of being dead,
    which is worse than missing one.
    """
    from datetime import date as _date

    raw = str(getattr(record, 'activated_at', '') or '').strip()
    if not raw:
        return False
    try:
        activated = _date.fromisoformat(raw[:10])
    except ValueError:
        return False
    try:
        threshold_hours = int(str(getattr(record, 'stale_threshold_hours', '') or 168))
    except (TypeError, ValueError):
        threshold_hours = 168
    return (_date.today() - activated).days > (threshold_hours / 24)


def _next_probe_generation(generation: str) -> str:
    """Synthesize the successor generation label for a boot probe.

    Handles both fleet shapes: executive prefixes (G96 -> G97) and slug-numbered
    session agents (sa.cold-boot-198 -> sa.cold-boot-199). Getting this wrong
    makes the probe itself the failure, which is worse than not probing.
    """
    import re as _re

    match = _re.fullmatch(r'(.*?)(\d+)', (generation or '').strip())
    if not match:
        return 'X1'
    return f'{match.group(1)}{int(match.group(2)) + 1}'


def check_pipeline_event_fixture_pollution(vault: Path) -> tuple[list[str], int, int]:
    """7627b589 fail-loud floor: a tropo.pipeline.* event in the production event
    log whose activation_uid/pipeline_run_uid isn't real 8-hex is a fixture-shaped
    event -- either a pre-fix historical leak (the exhaustive, documented allowlist
    above) or a NEW un-sandboxed test run that bypassed the sandbox-mode fix in
    9e7003b1.py's _emit_pipeline_event. The former is INFO (provenance-recorded,
    already accounted for); the latter is ERROR -- the plant is the proof.

    Returns (findings, total_checked, new_defect_count). Historical pollution is
    counted in total_checked but not in the defect count.
    """
    import re as _re

    uid_re = _re.compile(r'^[0-9a-f]{8}$')
    findings: list[str] = []
    total_checked = 0
    new_defects = 0
    historical_count = 0

    for rec in _canonical_event_union(vault):
        if not str(rec.get('type', '')).startswith('tropo.pipeline.'):
            continue
        data = rec.get('data') or {}
        polluted_key = None
        for key in ('activation_uid', 'pipeline_run_uid'):
            val = data.get(key)
            if val is not None and not uid_re.match(str(val)):
                polluted_key = key
                break
        if polluted_key is None:
            continue
        total_checked += 1
        event_id = rec.get('id', '')
        if event_id in _KNOWN_PIPELINE_EVENT_POLLUTION_IDS:
            historical_count += 1
            continue
        new_defects += 1
        findings.append(
            f"[ERROR] event {event_id}: {rec.get('type')} carries fixture-shaped "
            f"{polluted_key}={data.get(polluted_key)!r} -- not real 8-hex, not in the "
            f"documented pollution allowlist (7627b589). A test run bypassed the "
            f"sandbox mode (TROPO_PIPELINE_RUNTIME_SANDBOX) in 9e7003b1.py."
        )

    if historical_count:
        findings.insert(0,
            f"[INFO] {historical_count} historical fixture event(s) (7627b589, pre-sandbox-fix) "
            f"-- provenance-recorded, not re-litigated. See vault/files/7627b589.md."
        )

    return findings, total_checked, new_defects


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def check_typed_finding_tally_fixture() -> tuple[list[Finding], int, int]:
    """Law-12 plant: severity, never rendered prose, drives the tally.

    The ERROR carries a deliberately misleading ``[WARN]`` token in its
    message; the WARN carries ``[FAIL]``.  A prefix parser would invert them.
    The typed tally must still report exactly one of each severity.
    """
    planted = [
        Finding(
            Severity.ERROR,
            "typed-finding-plant",
            "mis-prefixed-error",
            "[WARN] this text must not downgrade an ERROR",
        ),
        Finding(
            Severity.WARN,
            "typed-finding-plant",
            "mis-prefixed-warn",
            "[FAIL] this text must not promote a WARN",
        ),
        Finding(
            Severity.INFO,
            "typed-finding-plant",
            "prefixless-info",
            "no control prefix at all",
        ),
    ]
    tally = FindingTally()
    tally.extend(planted, check_id="typed-finding-plant")
    defects: list[Finding] = []
    if (tally.errors, tally.warnings, tally.infos) != (1, 1, 1):
        defects.append(
            Finding(
                Severity.ERROR,
                "typed-finding-plant",
                "tally",
                f"expected (1,1,1), got "
                f"({tally.errors},{tally.warnings},{tally.infos})",
            )
        )
    if not str(planted[0]).lstrip().startswith("[ERROR]"):
        defects.append(
            Finding(
                Severity.ERROR,
                "typed-finding-plant",
                "render",
                "ERROR did not render from typed severity",
            )
        )
    if not str(planted[1]).lstrip().startswith("[WARN]"):
        defects.append(
            Finding(
                Severity.ERROR,
                "typed-finding-plant",
                "render",
                "WARN did not render from typed severity",
            )
        )

    def _crash_plant():
        raise RuntimeError("planted typed-family crash")

    crashed, _, _ = typed_findings.run_check_family(
        "typed-finding-crash-plant", _crash_plant
    )
    crash_tally = FindingTally()
    crash_tally.extend(crashed, check_id="typed-finding-crash-plant")
    if crash_tally.errors != 1:
        defects.append(
            Finding(
                Severity.ERROR,
                "typed-finding-crash-plant",
                "tally",
                f"expected one counted crash, got {crash_tally.errors}",
            )
        )
    return defects, len(planted) + 1, len(defects)


PUBLIC_SNAPSHOT_SAMPLE_REL = (
    Path("02-outbox") / "web-v4" / "public-snapshot-v1"
)

_PS_FILENAMES = frozenset(
    {"manifest.json", "release-facts.json", "privacy-receipt.json"}
)
_PS_ALLOWED_TYPES = frozenset(
    {"tropo.release.shipped", "tropo.release.published"}
)
_PS_FACT_REQUIRED = frozenset(
    {"public_fact_id", "type", "occurred_at", "version"}
)
_PS_FACT_OPTIONAL = frozenset(
    {"tag", "public_url", "agent_name", "agent_generation"}
)
_PS_HELD_POLICY = {
    "private-default": "input is private unless explicitly allowlisted",
    "unverified-release-emitter": "candidate emitter is not the governed verify-live publisher",
    "malformed-public-candidate": "candidate lacks valid required public fields",
    "unresolved-public-signer": "optional signer attribution could not be resolved safely",
    "unknown-input-fields": "candidate contains fields outside the public input allowlist",
}
_PS_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_PS_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_PS_FACT_ID_RE = re.compile(r"^rf_[0-9a-f]{64}$")
_PS_AGENT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 .'-]{0,79}$")
_PS_GENERATION_RE = re.compile(r"^[A-Z][0-9]+$")
_PS_SEMVER_CORE = r"(?:0|[1-9][0-9]*)"
_PS_SEMVER_IDENTIFIER = (
    r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
)
_PS_SEMVER_RE = re.compile(
    rf"^{_PS_SEMVER_CORE}\.{_PS_SEMVER_CORE}\.{_PS_SEMVER_CORE}"
    rf"(?:-{_PS_SEMVER_IDENTIFIER}(?:\.{_PS_SEMVER_IDENTIFIER})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_PS_PRIVATE_METADATA_KEYS = frozenset(
    {
        "policy_uid",
        "source_commit",
        "event_uid",
        "source_uid",
        "writer_instance_uid",
        "stream_uid",
        "local_seq",
        "display_seq",
        "subject",
        "correlationid",
        "causationid",
        "body",
        "data",
    }
)
_PS_FORBIDDEN_FACT_KEYS = frozenset(
    {
        "id",
        "event_uid",
        "source_uid",
        "writer_instance_uid",
        "stream_uid",
        "local_seq",
        "display_seq",
        "source",
        "subject",
        "correlationid",
        "causationid",
        "data",
        "body",
        "summary",
        "path",
        "uid",
    }
)


def _ps_reject_private_metadata(value: Any, subject: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _PS_PRIVATE_METADATA_KEYS:
                raise ValueError(f"{subject} contains forbidden private metadata")
            _ps_reject_private_metadata(child, subject)
    elif isinstance(value, list):
        for child in value:
            _ps_reject_private_metadata(child, subject)
    elif isinstance(value, str) and (
        value == "20495aaf" or _PS_COMMIT_RE.fullmatch(value)
    ):
        raise ValueError(f"{subject} contains a governed UID or private commit")


def _ps_payload(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"public snapshot contains non-canonical data: {exc}") from exc


def _ps_file_bytes(value: Any) -> bytes:
    return _ps_payload(value) + b"\n"


def _ps_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ps_exact(value: Any, expected: set[str], subject: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{subject} does not have its exact contract keys")
    return value


def _ps_read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    metadata = path.lstat()
    if path.is_symlink() or not path.is_file() or metadata.st_nlink != 1:
        raise ValueError(f"{path.name} must be an unlinked regular file")
    payload = path.read_bytes()

    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{path.name} has duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=no_duplicates,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"{path.name} has non-finite number {constant}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path.name} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} root must be an object")
    if _ps_file_bytes(value) != payload:
        raise ValueError(f"{path.name} is not canonical JSON")
    return value, payload


def _ps_timestamp(value: Any, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{subject} is not an ISO-8601 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{subject} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{subject} must carry a timezone")
    parsed = parsed.astimezone(timezone.utc)
    timespec = "microseconds" if parsed.microsecond else "seconds"
    normalized = parsed.isoformat(timespec=timespec).replace("+00:00", "Z")
    if normalized != value:
        raise ValueError(f"{subject} is not canonical UTC")
    return normalized


def _ps_semver(value: Any) -> str:
    if not isinstance(value, str) or not _PS_SEMVER_RE.fullmatch(value):
        raise ValueError("public snapshot version is not normalized SemVer")
    return value


def _ps_public_url(value: Any, version: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("public_url must be a non-empty string")
    if (
        value != value.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        or any(character.isspace() for character in value)
    ):
        raise ValueError("public_url contains whitespace or control characters")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("public_url is malformed") from exc
    prefix = "/tropo-ai/tropo/releases/tag/"
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(prefix)
        or parsed.path.endswith("/")
        or "//" in parsed.path
        or "%" in parsed.path
        or any(part in {".", ".."} for part in Path(parsed.path).parts)
        or value != f"https://github.com{parsed.path}"
    ):
        raise ValueError("public_url is outside the fixed GitHub release path")
    tag = parsed.path[len(prefix):]
    normalized = tag[1:] if tag.startswith("v") else tag
    if not _PS_SEMVER_RE.fullmatch(normalized) or normalized != version:
        raise ValueError("public_url release tag does not match version")


def _validate_public_snapshot_independent(bundle_path: Path) -> dict[str, Any]:
    """Minimal stdlib-only privacy/shape check independent of exporter code."""
    if bundle_path.is_symlink() or not bundle_path.is_dir():
        raise ValueError("public snapshot bundle must be a real directory")
    entries = list(bundle_path.iterdir())
    if {entry.name for entry in entries} != _PS_FILENAMES:
        raise ValueError("public snapshot layout must contain exactly three v1 files")

    release, release_payload = _ps_read_json(bundle_path / "release-facts.json")
    manifest, _ = _ps_read_json(bundle_path / "manifest.json")
    receipt, receipt_payload = _ps_read_json(
        bundle_path / "privacy-receipt.json"
    )
    _ps_reject_private_metadata(release, "release-facts")
    _ps_reject_private_metadata(manifest, "manifest")
    _ps_reject_private_metadata(receipt, "privacy receipt")

    release = _ps_exact(
        release, {"schema_version", "facts"}, "release-facts"
    )
    if release["schema_version"] != "1.0.0":
        raise ValueError("release-facts schema version is invalid")
    facts = release["facts"]
    if not isinstance(facts, list):
        raise ValueError("release-facts facts must be an array")
    previous = None
    seen_ids = set()
    for index, fact in enumerate(facts):
        if not isinstance(fact, dict):
            raise ValueError(f"release fact {index} is not an object")
        keys = set(fact)
        if keys & _PS_FORBIDDEN_FACT_KEYS:
            raise ValueError(f"release fact {index} contains a forbidden private key")
        if (
            not _PS_FACT_REQUIRED <= keys
            or not keys <= (_PS_FACT_REQUIRED | _PS_FACT_OPTIONAL)
        ):
            raise ValueError(f"release fact {index} violates the field allowlist")
        fact_id = fact["public_fact_id"]
        if not isinstance(fact_id, str) or not _PS_FACT_ID_RE.fullmatch(fact_id):
            raise ValueError(f"release fact {index} has malformed public_fact_id")
        if fact_id in seen_ids:
            raise ValueError("release facts contain duplicate public_fact_id")
        seen_ids.add(fact_id)
        if fact["type"] not in _PS_ALLOWED_TYPES:
            raise ValueError(f"release fact {index} has a non-public type")
        occurred_at = _ps_timestamp(fact["occurred_at"], "occurred_at")
        version = _ps_semver(fact["version"])
        has_name = "agent_name" in fact
        has_generation = "agent_generation" in fact
        if has_name != has_generation:
            raise ValueError("optional public attribution must appear as a pair")
        if has_name and (
            not isinstance(fact["agent_name"], str)
            or not _PS_AGENT_NAME_RE.fullmatch(fact["agent_name"])
            or not isinstance(fact["agent_generation"], str)
            or not _PS_GENERATION_RE.fullmatch(fact["agent_generation"])
        ):
            raise ValueError("public attribution is malformed")
        if "tag" in fact and fact["tag"] not in {version, f"v{version}"}:
            raise ValueError("public release tag does not match version")
        if "public_url" in fact:
            _ps_public_url(fact["public_url"], version)
        projected = dict(fact)
        del projected["public_fact_id"]
        expected_id = f"rf_{_ps_sha256(_ps_payload(projected))}"
        if fact_id != expected_id:
            raise ValueError("public_fact_id does not derive from public fields")
        order_key = (occurred_at, fact_id)
        if previous is not None and order_key <= previous:
            raise ValueError("release facts are not strictly sorted")
        previous = order_key

    manifest = _ps_exact(
        manifest,
        {
            "schema_version",
            "policy",
            "policy_version",
            "generated_at",
            "artifacts",
            "bundle_sha256",
        },
        "manifest",
    )
    if (
        manifest["schema_version"] != "1.0.0"
        or manifest["policy"] != "public-crew-snapshot"
        or manifest["policy_version"] != "1.0.0"
    ):
        raise ValueError("manifest public policy or schema is invalid")
    _ps_timestamp(manifest["generated_at"], "generated_at")
    release_hash = _ps_sha256(release_payload)
    release_descriptor = {
        "path": "release-facts.json",
        "sha256": release_hash,
        "bytes": len(release_payload),
        "records": len(facts),
    }
    receipt_descriptor = {
        "path": "privacy-receipt.json",
        "sha256": _ps_sha256(receipt_payload),
        "bytes": len(receipt_payload),
        "records": 1,
    }
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ValueError("manifest must describe data and privacy receipt artifacts")
    normalized_artifacts = [
        _ps_exact(
            artifact,
            {"path", "sha256", "bytes", "records"},
            "manifest artifact",
        )
        for artifact in artifacts
    ]
    if any(
        not isinstance(artifact["path"], str)
        or not isinstance(artifact["sha256"], str)
        or not _PS_HASH_RE.fullmatch(artifact["sha256"])
        or type(artifact["bytes"]) is not int
        or artifact["bytes"] < 0
        or type(artifact["records"]) is not int
        or artifact["records"] < 0
        for artifact in normalized_artifacts
    ):
        raise ValueError("manifest artifact descriptor fields are malformed")
    if normalized_artifacts != [release_descriptor, receipt_descriptor]:
        raise ValueError("manifest artifact descriptors do not match public bytes")
    expected_bundle_hash = _ps_sha256(_ps_payload(artifacts))
    if (
        not isinstance(manifest["bundle_sha256"], str)
        or not _PS_HASH_RE.fullmatch(manifest["bundle_sha256"])
        or manifest["bundle_sha256"] != expected_bundle_hash
    ):
        raise ValueError("manifest bundle hash does not re-derive")

    receipt = _ps_exact(
        receipt,
        {
            "schema_version",
            "policy",
            "policy_version",
            "exporter_version",
            "data_bundle_sha256",
            "crossed",
            "held_back",
            "overrides_consumed",
        },
        "privacy receipt",
    )
    if (
        receipt["schema_version"] != "1.0.0"
        or receipt["policy"] != "public-crew-snapshot"
        or receipt["policy_version"] != "1.0.0"
        or receipt["exporter_version"] != "1.1.0"
    ):
        raise ValueError("privacy receipt public policy or schema is invalid")
    expected_data_bundle_hash = _ps_sha256(_ps_payload([release_descriptor]))
    if receipt["data_bundle_sha256"] != expected_data_bundle_hash:
        raise ValueError("receipt data_bundle_sha256 does not re-derive")
    crossed = _ps_exact(receipt["crossed"], {"release_facts"}, "receipt crossed")
    crossed_release = _ps_exact(
        crossed["release_facts"], {"count", "sha256"}, "receipt release_facts"
    )
    if (
        type(crossed_release["count"]) is not int
        or crossed_release["count"] != len(facts)
        or crossed_release["sha256"] != release_hash
    ):
        raise ValueError("receipt crossed facts do not re-derive")
    held_back = receipt["held_back"]
    if not isinstance(held_back, list):
        raise ValueError("receipt held_back must be an array")
    previous_bucket = None
    for row_value in held_back:
        row = _ps_exact(row_value, {"bucket", "reason"}, "held-back row")
        bucket = row["bucket"]
        if (
            not isinstance(bucket, str)
            or bucket not in _PS_HELD_POLICY
            or row["reason"] != _PS_HELD_POLICY[bucket]
        ):
            raise ValueError("receipt has a non-policy held-back row")
        if previous_bucket is not None and bucket <= previous_bucket:
            raise ValueError("receipt held-back rows are not strictly sorted")
        previous_bucket = bucket
    if receipt["overrides_consumed"] != []:
        raise ValueError("v1 receipt cannot report consumed overrides")
    return {
        "bundle_sha256": manifest["bundle_sha256"],
        "policy": manifest["policy"],
        "records": len(facts),
        "release_facts_sha256": release_hash,
    }


def _ps_current_bound_commit(vault: Path) -> str:
    git_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    git_environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        head_result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=vault,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=git_environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("public snapshot source binding could not resolve HEAD") from exc
    commit = head_result.stdout.strip()
    if not _PS_COMMIT_RE.fullmatch(commit):
        raise ValueError("public snapshot source binding returned an invalid commit")
    return commit


def check_public_snapshot_contract(vault: Path) -> tuple[list[Finding], int, int]:
    """Independently check privacy/shape, then source-rederive with exporter code."""
    bundle_path = vault / PUBLIC_SNAPSHOT_SAMPLE_REL
    if not bundle_path.exists() and not bundle_path.is_symlink():
        return [], 0, 0
    if bundle_path.is_dir() and not any(bundle_path.iterdir()):
        return [], 0, 0
    try:
        _validate_public_snapshot_independent(bundle_path)
        contract = _load_public_snapshot_contract()
        bound_source_commit = _ps_current_bound_commit(vault)
        contract.validate_bundle_directory(
            bundle_path,
            source_root=vault,
            bound_source_commit=bound_source_commit,
        )
    except Exception as exc:
        return (
            [
                Finding(
                    Severity.ERROR,
                    "public-snapshot-contract",
                    PUBLIC_SNAPSHOT_SAMPLE_REL.as_posix(),
                    f"bundle validation/source re-derivation failed: "
                    f"{exc.__class__.__name__}: {exc}",
                )
            ],
            1,
            1,
        )
    return [], 1, 0


_VALIDATOR_PROVENANCE_SCHEMA_VERSION = 1


def validator_invocation_scope(
    *,
    customer: bool = False,
    release: bool = False,
    thorough: bool = False,
) -> dict[str, bool]:
    """Return the small, invocation-only scope label for a validator run."""
    return {
        "default": not customer and not release,
        "customer": bool(customer),
        "release": bool(release),
        "thorough": bool(thorough),
    }


def _empty_validator_provenance(scope: dict[str, bool]) -> dict[str, Any]:
    return {
        "schema_version": _VALIDATOR_PROVENANCE_SCHEMA_VERSION,
        "commit": None,
        "index_hash": None,
        "validator_version": None,
        "scope": dict(scope),
    }


def _validator_index_hash(vault: Path) -> str:
    """Hash named current/archive surfaces with unambiguous v1 framing."""
    combined = hashlib.sha256(b"tropo.validator.index-surfaces.v1\0")
    for name in ("00-index.jsonl", "00-archive-index.jsonl"):
        surface = hashlib.sha256()
        byte_length = 0
        with (vault / "vault" / name).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                byte_length += len(chunk)
                surface.update(chunk)
        encoded_name = name.encode("utf-8")
        combined.update(len(encoded_name).to_bytes(4, "big"))
        combined.update(encoded_name)
        combined.update(byte_length.to_bytes(8, "big"))
        combined.update(surface.digest())
    return combined.hexdigest()


def collect_validator_provenance(
    vault: Path,
    scope: dict[str, bool],
    *,
    validator_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Collect bounded run labels; unavailable facts remain null."""
    provenance = _empty_validator_provenance(scope)

    git_environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    git_environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=vault,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=git_environment,
        )
        commit = result.stdout.strip()
        if result.returncode == 0 and commit:
            provenance["commit"] = commit
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        provenance["index_hash"] = _validator_index_hash(vault)
    except OSError:
        pass

    implementation = Path(__file__) if validator_path is None else validator_path
    try:
        provenance["validator_version"] = hashlib.sha256(
            implementation.read_bytes()
        ).hexdigest()
    except OSError:
        pass

    return provenance


def collect_validator_provenance_nonblocking(
    vault: Path,
    scope: dict[str, bool],
) -> dict[str, Any]:
    """Keep unexpected label collection failures outside validator semantics."""
    try:
        return collect_validator_provenance(vault, scope)
    except Exception as exc:
        print(
            f"WARN: validator provenance collection failed (non-blocking): {exc}",
            file=sys.stderr,
        )
        return _empty_validator_provenance(scope)


def emit_validator_run_completed(
    *,
    passed: int,
    failed: int,
    warnings: int,
    normalizable: int,
    meta_status_coverage_gaps: int,
    meta_status_unresolved: int,
    provenance: dict[str, Any],
    exit_code: int,
) -> int:
    """Emit the compatible result payload without changing validator status."""
    data = {
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "normalizable": normalizable,
        "meta_status_coverage_gaps": meta_status_coverage_gaps,
        "meta_status_unresolved": meta_status_unresolved,
        "provenance": {
            "schema_version": provenance.get("schema_version"),
            "commit": provenance.get("commit"),
            "index_hash": provenance.get("index_hash"),
            "validator_version": provenance.get("validator_version"),
            "scope": provenance.get("scope"),
        },
    }
    try:
        from lib.event_emitter import auto_emit
        auto_emit(
            "tropo.validator.run.completed",
            "/tools/tropo-validate",
            "d2b9c8e6",
            lifecycle="ephemeral",
            data=data,
        )
    except Exception as exc:
        print(
            f"WARN: validator completion event emission failed (non-blocking): {exc}",
            file=sys.stderr,
        )
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Structural validator for a Tropo vault.',
    )
    parser.add_argument('--vault-path', metavar='PATH',
                        help='Explicit vault root (must contain ledger/ + .tropo/).')
    parser.add_argument('--write-fingerprints', nargs='*', metavar='FILE',
                        help='v1.70 S3.5.2: Write dual fingerprints to target boot-derivation artifacts. '
                             'If no files provided, scans for existing boot_derivation:true entries.')
    parser.add_argument('--release', action='store_true',
                        help='Release-mode validation (dev-spec f8b51f4d D1, v1.74): '
                             'downgrade outward-refs (UIDs not in the subset index) from [FAIL] to [INFO]. '
                             'Safe because the full-studio pre-build pass (0 FAILED) guarantees '
                             'no genuine broken refs — so in a release, every not-in-index ref '
                             'is by definition an expected outward-ref to a non-shipped studio file.')
    parser.add_argument('--customer', '--customer-mode', action='store_true',
                        help='S1 (v1.80): Customer-mode validation. An adopted studio running the health '
                             'surface against a shipped box sees ~207 vendor outward-refs (argo-internal '
                             'UIDs that did not ship) as [INFO] with count, never [FAIL]. Genuine broken '
                             'in-box refs still [FAIL] loudly. Pass --customer to a customer extract '
                             'health run; the shipped box carries an optional vendor-ref manifest. '
                             'Same mechanics as --release; separated for honest provenance.')
    parser.add_argument('--thorough', action='store_true',
                        help='Governed Autonomy S1 (ef65fccd): spot re-derivation for '
                             'check_step_completion_has_verification — re-runs each passing '
                             "receipt's recorded verification_command and compares exit_code + "
                             'output_sha256 against what was recorded, flagging drift/tamper. '
                             'Off by default (real command re-execution; not a routine-pass default).')
    parser.add_argument('--fleet-boot-health', action='store_true',
                        help='Run ONLY the fleet birth-health check and print one line. '
                             'For the Group 5 boot step: every agent asks, every boot, '
                             'whether any lineage in the fleet has stopped being able to '
                             'produce a successor. This check has existed since 2026-07-29 '
                             'and correctly reported metis, po and tropo as blocked — to '
                             'nobody, because it only ran inside a full validate that nobody '
                             'ran. An instrument that reports where no one is looking is the '
                             'same as no instrument (metis-g100, 2026-08-03).')
    args = parser.parse_args()

    vault = resolve_vault_root(args.vault_path)
    if vault is None:
        print('ERROR: Could not resolve vault root.', file=sys.stderr)
        return 2

    # --- Fleet birth health, standalone (metis-g100) ---
    if args.fleet_boot_health:
        try:
            findings, checked, blocked = check_every_agent_can_still_boot(vault)
        except Exception as exc:
            print(f'⚠️  Fleet birth health: check failed to run ({exc})')
            return 1
        if blocked == 0:
            print(f'✅ Fleet birth health: {checked} lineage(s) can produce a successor.')
            return 0
        # Severity language corrected metis-g101 2026-08-04. This said "CANNOT
        # produce a successor", which stopped being true when G100 converted
        # birth from refuse-on-failed-check to record-and-proceed.
        #
        # The first correction written here was ALSO wrong, and only a probe
        # caught it. It claimed the successor would be "born provisional" --
        # true for argus, but on a planted lineage whose predecessor carried an
        # unknown agent_class the mint issued a CLEAN entry, no findings at all.
        # The check and the mint do not share a rule set: this walk is stricter
        # than birth, and some of what it reports birth simply does not consult.
        #
        # So the only claim made here is the one that is verified in both
        # directions and pinned by test_fleet_health_language.py: the birth is
        # NOT BLOCKED. Whether it also comes out provisional is the mint's
        # business to report, not this check's to predict.
        #
        # It matters because of who reads this line. Boot step 5.1.9 puts it in
        # front of a human in every agent's startup signal, and Mike's standing
        # bar is "I NEVER EVER want to see my agents telling me they are failing
        # to boot." An alarm that overstates by a whole category is how a real
        # finding gets discounted -- and this instrument already spent thirty
        # days being right about Po while nobody acted.
        #
        # Findings are unchanged and still surface; only the claim about their
        # consequence is corrected. Exit code deliberately left non-zero: CI
        # should still see these, and changing that is a separate decision with
        # its own blast radius.
        print(
            f'🟡 Fleet birth health: {blocked} of {checked} lineage(s) carry a '
            'lineage defect. Birth is NOT blocked — the mint records what it '
            'cannot prove and proceeds. These are repairs, not emergencies.'
        )
        for line in findings:
            print(f'   • {line}')
        return 1

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
                        src['body_sha256'] = body_sha256(src_path, strip_navblock=True)
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

    run_scope = validator_invocation_scope(
        customer=getattr(args, "customer", False),
        release=getattr(args, "release", False),
        thorough=getattr(args, "thorough", False),
    )
    run_provenance = collect_validator_provenance_nonblocking(vault, run_scope)

    # S1 (v1.80 re-build): customer-mode classification is data (the shipped vendor-ref
    # manifest), not guesswork. Load once here; None means fail-closed downstream.
    vendor_manifest: Optional[set[str]] = None
    if getattr(args, 'customer', False):
        vendor_manifest = load_vendor_ref_manifest(vault)

    print('=' * 70)
    print('tropo-validate.py — vault structural validator')
    print(f'Vault root: {vault}')
    if getattr(args, 'customer', False):
        if vendor_manifest is not None:
            print(f'[INFO] CUSTOMER MODE active — vendor-ref manifest loaded '
                  f'({len(vendor_manifest)} known vendor refs); refs outside the manifest still [FAIL]')
        else:
            print('[WARN] CUSTOMER MODE active but no vendor-ref manifest found at '
                  f'{VENDOR_REF_MANIFEST_REL_PATH} — failing closed: every not-in-index ref [FAIL]s')
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

    # --- A142 index lifecycle: union integrity stays broad and ERROR-grade ---
    print(
        '\n--- Index Union Integrity '
        '(CURRENT + ARCHIVE; row resolution + UID uniqueness are ERROR invariants) ---'
    )
    try:
        iui_findings, iui_checked, iui_defects = check_index_union_integrity(vault)
        if iui_defects == 0:
            print(
                f'[PASS] {iui_checked} rows checked across current + archive '
                'union — every row resolves and every UID is unique'
            )
            total_passes += 1
        else:
            print(
                f'[ERROR] {iui_checked} rows checked across current + archive '
                f'union; {iui_defects} integrity violation(s)'
            )
            for line in iui_findings[:25]:
                print(f'  {line}')
            if len(iui_findings) > 25:
                print(f'  ... and {len(iui_findings) - 25} more')
            total_fails += iui_defects
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] index-union-integrity check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- A142 index lifecycle: live authoring checks are current-only ---
    print(
        '\n--- Live Template + Body Shape '
        '(CURRENT surface only; archived history explicitly excluded) ---'
    )
    try:
        ltb_findings, ltb_checked, ltb_defects = check_live_template_body_shape(vault)
        ltb_warnings = [f for f in ltb_findings if f.startswith('[WARN]')]
        if ltb_defects == 0:
            print(
                f'[PASS] {ltb_checked} current template-governed entries '
                'checked — archived/superseded entries excluded'
            )
            total_passes += 1
        else:
            print(
                f'[FAIL] {ltb_checked} current template-governed entries '
                f'checked; {ltb_defects} live body-shape defect(s) '
                '(archive excluded)'
            )
        # WARN-grade findings (section presence, per the capsule-declared grade)
        # print in both branches: they are advisory, so they must not gate the
        # exit code, but a warning nobody prints is a warning nobody fixes.
        for line in [f for f in ltb_findings if not f.startswith('[WARN]')][:25]:
            print(f'  {line}')
        if ltb_defects > 25:
            print(f'  ... and {ltb_defects - 25} more defect(s)')
        if ltb_warnings:
            print(f'  [WARN] {len(ltb_warnings)} advisory body-shape finding(s):')
            for line in ltb_warnings[:10]:
                print(f'  {line}')
            if len(ltb_warnings) > 10:
                print(f'  ... and {len(ltb_warnings) - 10} more warning(s)')
        total_fails += ltb_defects
        total_warnings += len(ltb_warnings)
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] live-template-body check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- Identity Minting Chokepoint (796d9330 / ADR-050; WARN now, ERROR ratchet after first clean pass) ---
    print('\n--- Identity Minting Chokepoint (796d9330/ADR-050; WARN now, ERROR ratchet after first clean pass) ---')
    try:
        mic_findings, mic_scanned, mic_violations = check_mint_id_chokepoint(vault)
        if mic_violations == 0:
            print(f'[PASS] {mic_scanned} vault/tools/*.py script(s) checked — no raw token_hex(4) bypass')
            total_passes += 1
        else:
            print(f'[WARN] {mic_scanned} script(s) checked; {mic_violations} raw-mint bypass(es) found')
            for line in mic_findings[:20]:
                print(f'  {line}')
                total_warnings += 1
            if len(mic_findings) > 20:
                extra = len(mic_findings) - 20
                print(f'  ... and {extra} more')
                total_warnings += extra
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] mint-id-chokepoint check CRASHED: {e}')
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
            for row in _index_union(vault):
                uid = row.get('uid')
                if isinstance(uid, str) and UID_RE.match(uid):
                    all_uids.add(uid)
        except OSError:
            print('[FAIL] current/archive index union — unreadable')
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
            xref_findings, n_checked, n_defects = check_uid_cross_references(
                vault, all_uids, release_mode=getattr(args, 'release', False),
                customer_mode=getattr(args, 'customer', False), vendor_manifest=vendor_manifest)
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

    # --- Memory Typing (capsule a5b3c891 v1.6) ---
    print('\n--- Memory Typing (Engine Phase 1 reconciliation + v1.6 reinforcement fields; capsule a5b3c891 v1.6) ---')
    mem_findings, mem_checked, mem_defects = check_memory_typing(vault)
    if not mem_findings:
        print(f'[PASS] {mem_checked} memory entries verified well-formed per memory.capsule v1.6')
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

    # --- Pipeline Root Terminal Closure (v3.4 / v1.90 Rule 12; dev-spec c392d833) ---
    print('\n--- Pipeline Root Terminal Closure (pipeline.capsule v3.4 Rule 12; dev-spec c392d833) ---')
    prtc_findings, prtc_roots, prtc_violations = check_pipeline_root_terminal_closure(vault)
    if not prtc_findings:
        print(f'[PASS] {prtc_roots} activation root(s) checked; 0 shipped/completed cycle left state:active '
              f'(Rule 12 terminal-closure holds; weld = run_close_out_hook on build-release ship path, backstop = tropo-sweep-stale-roots.py)')
        total_passes += 1
    else:
        print(f'[INFO] {prtc_roots} activation roots checked; {prtc_violations} shipped/completed but still state:active '
              f'(WARN-severity at v1.90; ratchets to ERROR later — the weld remediates forward, sweep is backstop)')
        for line in prtc_findings[:10]:
            print(f'  {line}')
            total_warnings += 1
        if len(prtc_findings) > 10:
            remaining = len(prtc_findings) - 10
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
            # The full list is reproducible via direct python3 vault/tools/tropo-validate.py invocation +
            # piping output through grep "Charter Conformance" / less.
            print(f'  ... and {remaining} more (full list: python3 vault/tools/tropo-validate.py | grep -A 100 "Charter Conformance")')

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

    # --- Loop Maintenance-Registry Fields (loop.capsule v1.3 §7 Check 8; ERROR ratchet — S11 hook landed, Talos v1.80) ---
    print('\n--- Loop Maintenance-Registry Fields (loop.capsule v1.3 §7 Check 8; ERROR ratchet — S11 hook landed) ---')
    try:
        lrf_findings, lrf_checked, lrf_fails = check_loop_registry_fields(vault)
        if not lrf_findings:
            print(f'[PASS] {lrf_checked} registry-dispatched loop(s) verified — consent_mode/runner present, '
                  f'last_run date-or-bare-null, last_run_cost null-honest')
            total_passes += 1
        else:
            print(f'[FAIL] {lrf_checked} registry-dispatched loop(s) checked; {len(lrf_findings)} registry-field defects (Check 8 ERROR)')
            for line in lrf_findings[:10]:
                print(f'  {line}')
            if len(lrf_findings) > 10:
                print(f'  ... and {len(lrf_findings) - 10} more')
            total_fails += len(lrf_findings)
    except Exception as e:
        print(f'[FAIL] loop registry-fields check CRASHED: {e}')
        total_fails += 1

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
    scv_findings, scv_checked, scv_defects = check_step_completion_has_verification(vault, thorough=args.thorough)
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

    # --- Blocked-Task Parity (v1.5, re-pointed 2026-07-14 per 66b6f3e8) ---
    print('\n--- Blocked-Task Parity (v1.5 inbox 656c26d0; re-pointed 66b6f3e8, was 00-integrity.json) ---')
    findings, ok = check_integrity_parity(vault)
    for line in findings:
        print(line)
        if '[WARN]' in line:
            total_warnings += 1  # ratchet preserves count for display; FAIL counted by [FAIL] prefix
    if ok and not findings:
        print('[PASS] blocked-task parity across vault/00-index.jsonl and vault/00-index.sqlite (or a surface not present)')
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
            if line.strip().startswith(('[FAIL]', '[ERROR]')):
                total_fails += 1
            elif line.strip().startswith('[WARN]'):
                total_warnings += 1
        if len(scp_findings) > 20:
            extra = len(scp_findings) - 20
            print(f'  ... and {extra} more')
            for line in scp_findings[20:]:
                if line.strip().startswith(('[FAIL]', '[ERROR]')):
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
        c35_findings, c35_checked, c35_defects = check_identity_refs_resolve(
            vault, release_mode=getattr(args, 'release', False),
            customer_mode=getattr(args, 'customer', False), vendor_manifest=vendor_manifest)
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

    # --- Nav-Block Git Filter Installed (dev-spec 6ec30708 AC5; I5 dd16c90c, Option A NEW) ---
    print('\n--- Nav-Block Git Filter Installed (dev-spec 6ec30708 AC5; I5 dd16c90c, Option A NEW) ---')
    navfilter_findings, navfilter_checked, navfilter_defects = check_navblock_git_filter_installed(vault)
    if navfilter_checked == 0:
        print('[SKIP] no .git/ at this vault root — nothing to install the filter into yet (pre-Git-Beat-1).')
    elif not navfilter_findings:
        print('[PASS] nav-block git clean filter fully wired (.gitattributes + local git config).')
        total_passes += 1
    else:
        print(f'[FAIL] nav-block git clean filter NOT fully wired ({navfilter_defects}/2 halves missing) — '
              f'a studio in this state can silently commit nav-blocks into a shared segment (I5 violation):')
        for line in navfilter_findings:
            print(line)
            total_fails += 1

    # --- Duplicate YAML Keys (v1.29.0 Stream A; spec 81555e45 v0.4 §3.2 NEW) ---
    print('\n--- Duplicate Top-Level YAML Keys (v1.29.0 Stream A; spec 81555e45 v0.4 §3.2 NEW) ---')
    dyk_findings, dyk_checked, dyk_defects = check_duplicate_yaml_keys(vault)
    if not dyk_findings:
        print(f'[PASS] {dyk_checked} files verified — no duplicate top-level YAML keys')
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

    # --- test-spec.capsule v1.2 §Validation Checks (14 checks; lib module wire-up) ---
    print('\n--- test-spec.capsule v1.2 §Validation Checks (bounded legacy WARN / v1.2+ ERROR) ---')
    try:
        # Check 33 above reports the same shared Rule 3 evaluator once; do not
        # duplicate those findings in the family roll-up.
        ts_findings, ts_total, ts_defects = check_test_spec_family(
            vault,
            include_pairing=False,
            include_behavior_floor=False,
        )
        if not ts_findings:
            print(f'[PASS] {ts_total} test-spec entries verified clean — 14-check family green')
            total_passes += 1
        else:
            strict_defects = sum(
                line.strip().startswith(('[FAIL]', '[ERROR]'))
                for line in ts_findings
            )
            warning_count = sum(
                line.strip().startswith('[WARN]') for line in ts_findings
            )
            rollup = '[FAIL]' if strict_defects else '[WARN]'
            print(
                f'{rollup} {ts_total} test-spec entries checked; '
                f'{strict_defects} strict defect(s), {warning_count} warning(s)'
            )
            for line in ts_findings[:10]:
                print(f'  {line}')
                if line.strip().startswith(('[FAIL]', '[ERROR]')):
                    total_fails += 1
                elif line.strip().startswith('[WARN]'):
                    total_warnings += 1
            if len(ts_findings) > 10:
                print(f'  ... and {len(ts_findings) - 10} more')
                for line in ts_findings[10:]:
                    if line.strip().startswith(('[FAIL]', '[ERROR]')):
                        total_fails += 1
                    elif line.strip().startswith('[WARN]'):
                        total_warnings += 1
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
        ev_findings, ev_checked, _legacy_ev_defects = typed_findings.run_check_family(
            "events", run_all_event_checks, vault
        )
        ev_tally = FindingTally()
        typed_event_findings = ev_tally.extend(ev_findings, check_id="events")
        if ev_checked == 0:
            print('[INFO] vault/events/00-events.jsonl not present — skipping (no events yet)')
        elif not ev_findings:
            print(f'[PASS] {ev_checked} event(s) checked — Checks 1-10 all clean')
            total_passes += 1
        else:
            verdict = 'FAIL' if ev_tally.errors else 'WARN'
            print(
                f'[{verdict}] {ev_checked} event(s) checked; '
                f'{ev_tally.errors} ERROR, {ev_tally.warnings} WARN, '
                f'{ev_tally.infos} INFO finding(s)'
            )
            for finding in typed_event_findings:
                print(finding)
            total_fails += ev_tally.errors
            total_warnings += ev_tally.warnings
    except ImportError as e:
        print(f'[WARN] event_validators import failed: {e}; A.8 checks skipped')
        total_warnings += 1

    # --- Tropo Engine Phase 1: Typed-Finding Tally Gauntlet (Law 12) ---
    print('\n--- Typed-Finding Tally Gauntlet (Engine Phase 1; severity drives tally) ---')
    tf_findings, tf_checked, tf_defects = check_typed_finding_tally_fixture()
    if tf_defects:
        print(f'[FAIL] {tf_checked} planted typed findings; {tf_defects} tally/render defect(s)')
        for finding in tf_findings:
            print(finding)
        total_fails += tf_defects
    else:
        print(
            f'[PASS] {tf_checked} planted findings — mis-prefixed ERROR/WARN + '
            'prefixless INFO tally and render from typed severity'
        )
        total_passes += 1

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

    # --- core v1.7: Gardener Pruning contract ---
    print('\n--- check_pruning_contract (core v1.7; shared writer/validator/check-one rules) ---')
    pruning_findings, pruning_checked, pruning_defects = check_pruning_contract(vault)
    pruning_warnings = [
        line for line in pruning_findings if line.startswith('[WARN]')
    ]
    pruning_failures = [
        line for line in pruning_findings if line.startswith('[FAIL]')
    ]
    if pruning_checked == 0:
        print('[INFO] No pruning blocks in eligible governed Markdown — silent PASS')
    elif not pruning_findings:
        print(f'[PASS] {pruning_checked} pruning block(s) checked — all current and valid')
        total_passes += 1
    else:
        if pruning_failures:
            print(
                f'[FAIL] {pruning_defects} pruning contract defect(s) across '
                f'{pruning_checked} block(s)'
            )
            for line in pruning_failures:
                print(line)
            total_fails += pruning_defects
        if pruning_warnings:
            print(
                f'[WARN] {len(pruning_warnings)} stale/re-queue pruning finding(s) '
                f'across {pruning_checked} block(s)'
            )
            for line in pruning_warnings:
                print(line)
            total_warnings += len(pruning_warnings)

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
        _rc_path = vault / 'vault' / 'capsules' / 'release.capsule.md'  # b19e8d43 — capsules live at .tropo/capsules/, NOT vault/files/ (Vela V56 lookup-path fix 2026-05-31; Mike-directed; Talos owns the check logic)
        if not _rc_path.exists():
            print('[WARN] check_v162_self_dogfood: release.capsule (b19e8d43) not found at vault/capsules/tropo-release.capsule.md')
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
                # [FAIL] counts as a fail — the v1.68 S1 ratchet flipped the M2
                # message prefix WARN->FAIL but this tally only knew [ERROR]/[WARN],
                # so ratcheted findings counted as NOTHING and the board stayed
                # green while M2 failed at scale (vacuous-ratchet class; fixed
                # 2026-07-01 argus-a122 after the O26 find).
                if stripped.startswith(('[ERROR]', '[FAIL]')):
                    total_fails += 1
                elif stripped.startswith('[WARN]'):
                    total_warnings += 1
            if len(ms_findings) > 20:
                remainder = ms_findings[20:]
                extra_warn = sum(1 for l in remainder if l.strip().startswith('[WARN]'))
                extra_error = sum(1 for l in remainder if l.strip().startswith(('[ERROR]', '[FAIL]')))
                print(f'  ... and {len(remainder)} more')
                total_warnings += extra_warn
                total_fails += extra_error
            if ms_gaps == 0 and ms_unresolved == 0 and not any(l.strip().startswith(('[ERROR]', '[FAIL]')) for l in ms_findings):
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
            if not loop_findings and loop_total == 0:
                print("[INFO] No loop entries or runs found — skipping")
            elif not loop_findings:
                print(f"[PASS] {loop_total} loop-run(s) / loop-definition(s) checked — all clean")
                total_passes += 1
            else:
                level = "FAIL" if loop_defects else "WARN"
                print(
                    f"[{level}] {loop_total} loop items checked; "
                    f"{len(loop_findings)} finding(s), {loop_defects} defect(s)"
                )
                for line in loop_findings:
                    print(f"  {line}")
                    if "[ERROR]" in line or "[FAIL]" in line:
                        total_fails += 1
                    elif "[WARN]" in line:
                        total_warnings += 1
        except Exception as e:
            print(f"[FAIL] loop-validators CRASHED: {e}")
            total_fails += 1
    else:
        print("[WARN] loop-validators skipped (lib missing)")

    # --- ADR-047 Component 2: Undispositioned Backlog (ERROR; v1.75 ratchet; E5 grandfather) ---
    print('\n--- Undispositioned-Stale Backlog (ADR-047 C2; dev-spec 8dce9aec; ERROR ratchet v1.75; E5 grandfather) ---')
    try:
        udb_findings, udb_checked, udb_stale = check_undispositioned_backlog(vault)
        if udb_stale == 0:
            print(f'[PASS] {udb_checked} owned work-item(s) checked — no post-{CHECK_UDB_GRANDFATHER_DATE} undispositioned-stale (>45 days)')
            total_passes += 1
        else:
            print(f'[ERROR] {udb_checked} owned work-item(s) checked; {udb_stale} post-{CHECK_UDB_GRANDFATHER_DATE} undispositioned-stale (>45 days)')
            total_fails += 1
        for line in udb_findings[:25]:
            print(f'  {line}')
        if len(udb_findings) > 25:
            print(f'  ... and {len(udb_findings) - 25} more')
    except Exception as e:
        print(f'[FAIL] undispositioned-backlog check CRASHED: {e}')
        total_fails += 1

    # --- ADR-047 Component 3: Archived Forward-Pointer Invariant (ERROR; v1.75 ratchet; E4 grandfather) ---
    print('\n--- Archived/Superseded Forward-Pointer Invariant (ADR-047 C3; dev-spec 8dce9aec; ERROR ratchet v1.75; E4 grandfather) ---')
    try:
        afp_findings, afp_checked, afp_defects = check_archived_forward_pointer(vault)
        if afp_defects == 0:
            print(f'[PASS] {afp_checked} archived/superseded entry(ies) checked — all have resolvable forward-pointer')
            total_passes += 1
        else:
            print(f'[ERROR] {afp_checked} archived/superseded entry(ies) checked; {afp_defects} missing/broken forward-pointer(s)')
            total_fails += 1
        for line in afp_findings[:25]:
            print(f'  {line}')
        if len(afp_findings) > 25:
            print(f'  ... and {len(afp_findings) - 25} more')
    except Exception as e:
        print(f'[FAIL] archived-forward-pointer check CRASHED: {e}')
        total_fails += 1

    # --- ADR-045 One Home: No Two-Homes Invariant (ERROR; ratcheted v1.76 (e8d49d3a) after migration) ---
    print('\n--- One Home — No Two-Homes Invariant (ADR-045; ERROR since v1.76 (e8d49d3a) migration complete) ---')
    try:
        nth_findings, nth_checked, nth_violations = check_no_two_homes(vault)
        if nth_violations == 0:
            print(f'[PASS] {nth_checked} entries checked — zero two-home duplicates (ADR-045 One Home)')
            total_passes += 1
        else:
            print(f'[ERROR] {nth_violations} two-home violation(s) found — same UID in both vault/ and .tropo/')
            total_fails += nth_violations
            for line in nth_findings[:20]:
                print(f'  {line}')
            if len(nth_findings) > 20:
                print(f'  ... and {len(nth_findings) - 20} more')
    except Exception as e:
        print(f'[FAIL] no-two-homes check CRASHED: {e}')
        total_fails += 1

    # --- Calls: Pointer Resolution (WARN; release smoke-test for skill/playbook chains; 8b6f4c5d PC-1) ---
    print('\n--- Calls: Pointer Resolution (release smoke-test; PC-1 class; WARN on dead targets) ---')
    try:
        cpr_findings, cpr_checked, cpr_defects = check_calls_pointer_resolution(vault)
        if cpr_checked == 0:
            print('[INFO] No calls: entries found in index — skipping')
        elif cpr_defects == 0:
            print(f'[PASS] {cpr_checked} calls: target(s) checked — all resolve on disk')
            total_passes += 1
        else:
            print(f'[WARN] {cpr_checked} calls: target(s) checked; {cpr_defects} unresolvable')
            total_warnings += 1
            for line in cpr_findings:
                print(f'  {line}')
    except Exception as e:
        print(f'[FAIL] calls-pointer-resolution check CRASHED: {e}')
        total_fails += 1

    # --- S5(b) (v1.80): Entrypoint Pointer Resolution (ERROR on non-resolving; PC-1 extended to package.json + skill/playbook steps) ---
    print('\n--- Entrypoint Pointer Resolution (v1.80 S5b; package.json scripts + skill/playbook steps; PC-1 extended; ERROR on dead) ---')
    try:
        epr_findings, epr_checked, epr_defects = check_entrypoint_pointer_resolution(vault)
        if epr_checked == 0:
            print('[INFO] No entrypoint script commands found — skipping')
        elif epr_defects == 0:
            print(f'[PASS] {epr_checked} entrypoint(s) checked — all resolve on disk')
            total_passes += 1
        else:
            print(f'[ERROR] {epr_checked} entrypoint(s) checked; {epr_defects} non-resolving (S5b PC-1 stale-pointer class)')
            total_fails += 1
            for line in epr_findings:
                print(f'  {line}')
    except Exception as e:
        print(f'[FAIL] entrypoint-pointer-resolution check CRASHED: {e}')
        total_fails += 1

    # --- v1.79 S1: Agent-Memory Surface Bound Gate (ERROR on >15 §Top-of-Mind; size gates) ---
    print('\n--- Agent-Memory Surface Bound Gate (v1.79 S1; >15 §Top-of-Mind = ERROR; >16KB WARN; >32KB ERROR) ---')
    try:
        amb_findings, amb_checked, amb_defects = check_agent_memory_bound(vault)
        if amb_checked == 0:
            print('[INFO] No v3 agent-memory surfaces found — skipping')
        elif amb_defects == 0:
            label = 'all within capsule A1 bounds' if not amb_findings else f'{len(amb_findings)} approaching-bound WARN(s), 0 ERROR'
            print(f'[PASS] {amb_checked} v3 agent-memory surface(s) checked — {label}')
            total_passes += 1
            for line in amb_findings:
                print(f'  {line}')
        else:
            print(f'[ERROR] {amb_checked} v3 agent-memory surface(s) checked; {amb_defects} bound violation(s)')
            total_fails += 1
            for line in amb_findings:
                print(f'  {line}')
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] agent-memory-bound check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- v1.79 S1 Gauntlet: memory-bound inline fixture (plant proves the gate fires) ---
    print('\n--- Agent-Memory Bound Gauntlet (v1.79 S1; inline plant — gate must fire on over-bound surface) ---')
    try:
        mbf_findings, mbf_pass, mbf_fail = check_memory_bound_fixture()
        if mbf_fail == 0:
            print(f'[PASS] {mbf_pass} fixture assertion(s) — memory-bound gate fires on 16-entry surface, passes on 14-entry; size gates fire correctly')
            total_passes += 1
        else:
            print(f'[FAIL] {mbf_fail} memory-bound gauntlet failure(s) — gate is vacuous (does not fire on planted surface)')
            for line in mbf_findings:
                print(line)
            total_fails += mbf_fail
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] memory-bound-gauntlet fixture CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- v1.79 S5: Boot-Budget Tally Gate (WARN on >10-min or incomplete most-recent activation) ---
    print('\n--- Boot-Budget Tally Gate (v1.79 S5; most-recent agent-activation run; WARN if >10min or incomplete) ---')
    try:
        bbt_findings, bbt_checked, bbt_defects = check_boot_budget_tally(vault)
        if bbt_checked == 0:
            print('[INFO] No agent-activation runs found — skipping')
        elif bbt_defects == 0:
            has_info = any(l.startswith('[INFO]') for l in bbt_findings)
            if bbt_findings and has_info:
                for line in bbt_findings:
                    print(f'  {line}')
            print(f'[PASS] Most-recent activation run checked — boot budget clean')
            total_passes += 1
        else:
            print(f'[WARN] Most-recent activation run: {bbt_defects} boot-budget finding(s)')
            total_warnings += bbt_defects
            for line in bbt_findings:
                print(f'  {line}')
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] boot-budget-tally check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- v1.79 S5 Gauntlet: boot-budget tally inline fixture (plant proves the gate fires) ---
    print('\n--- Boot-Budget Tally Gauntlet (v1.79 S5; inline plant — gate must fire on slow/incomplete run) ---')
    try:
        bbtf_findings, bbtf_pass, bbtf_fail = check_boot_budget_tally_fixture()
        if bbtf_fail == 0:
            print(f'[PASS] {bbtf_pass} fixture assertion(s) — boot-budget gate fires on >10min run and incomplete run; bare-date timestamps degrade gracefully')
            total_passes += 1
        else:
            print(f'[FAIL] {bbtf_fail} boot-budget gauntlet failure(s) — gate is vacuous or degrades incorrectly')
            for line in bbtf_findings:
                print(line)
            total_fails += bbtf_fail
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] boot-budget-tally-gauntlet fixture CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- 943bb220 (ADR-051 Fork 1): Vault Capsule Types — vault MANIFEST (new) + vault-entity (renamed) ---
    print('\n--- Vault Capsule Types (943bb220/ADR-051 Fork 1; vault manifest + vault-entity rename) ---')
    try:
        vct_findings, vct_checked, vct_violations = check_vault_capsule_types(vault)
        if vct_violations == 0:
            print(f'[PASS] {vct_checked} vault/vault-entity instance(s) checked — 0 violations')
            total_passes += 1
        else:
            print(f'[ERROR] {vct_checked} instance(s) checked; {vct_violations} violation(s)')
            total_fails += vct_violations
        for line in vct_findings[:25]:
            print(f'  {line}')
        if len(vct_findings) > 25:
            print(f'  ... and {len(vct_findings) - 25} more')
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] vault-capsule-types check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- 409ef1cc (ADR-051 Fork 2): Vault-Manifest Governed-Write Gate + compose.lock cross-validation ---
    print('\n--- Vault-Manifest Governed-Write Gate (409ef1cc/ADR-051 Fork 2; compose.lock cross-validation) ---')
    try:
        vmgw_findings, vmgw_checked, vmgw_violations = check_vault_manifest_governed_write_gate(vault)
        if vmgw_violations == 0:
            print(f'[PASS] {vmgw_checked} compose.lock vault-mount record(s) checked — 0 violations')
            total_passes += 1
        else:
            print(f'[ERROR] {vmgw_checked} record(s) checked; {vmgw_violations} violation(s)')
            total_fails += vmgw_violations
        for line in vmgw_findings[:25]:
            print(f'  {line}')
        if len(vmgw_findings) > 25:
            print(f'  ... and {len(vmgw_findings) - 25} more')
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] vault-manifest-governed-write-gate check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- 4275b01c (ADR-051): Cross-Vault member_of Primitive — per-vault D7 grounding + up-lattice edges ---
    print('\n--- Cross-Vault member_of Primitive (4275b01c/ADR-051; per-vault D7 + up-lattice boundary) ---')
    try:
        cvmo_findings, cvmo_checked, cvmo_violations = check_cross_vault_member_of(vault)
        if cvmo_violations == 0:
            print(f'[PASS] {cvmo_checked} work-item(s) checked — 0 D7-per-vault / illegal-edge violations')
            total_passes += 1
        else:
            print(f'[ERROR] {cvmo_checked} work-item(s) checked; {cvmo_violations} violation(s)')
            total_fails += cvmo_violations
        for line in cvmo_findings[:25]:
            print(f'  {line}')
        if len(cvmo_findings) > 25:
            print(f'  ... and {len(cvmo_findings) - 25} more')
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] cross-vault-member-of check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- c6f6bea4 (ADR-051 Fork 4): Shard-Index Consistency — staleness guard ---
    print('\n--- Shard-Index Consistency (c6f6bea4/ADR-051 Fork 4; incremental composed-index staleness guard) ---')
    try:
        sic_findings, sic_checked, sic_violations = check_shard_index_consistency(vault)
        if sic_violations == 0:
            print(f'[PASS] {sic_checked} compose.lock-pinned shard(s) checked — 0 cannot-compose findings')
            total_passes += 1
        else:
            print(f'[WARN] {sic_checked} shard(s) checked; {sic_violations} cannot-compose (fail-closed exclusion, not a data-corruption ERROR)')
            total_warnings += sic_violations
        for line in sic_findings[:25]:
            print(f'  {line}')
        if len(sic_findings) > 25:
            print(f'  ... and {len(sic_findings) - 25} more')
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] shard-index-consistency check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- 44badb55 (ADR-051, v1.84 DoD): Publish Boundary — two-machine sovereignty proof / Git Beat 2 ---
    print('\n--- Publish Boundary (44badb55/ADR-051; independent re-check of every published team-vault tip) ---')
    try:
        pb_findings, pb_checked, pb_violations = check_publish_boundary(vault)
        if pb_violations == 0:
            print(f'[PASS] {pb_checked} published team-vault tip(s) checked — 0 covenant violations')
            total_passes += 1
        else:
            severity_seen = 'ERROR' if any('[ERROR]' in l for l in pb_findings) else 'WARN'
            print(f'[{severity_seen}] {pb_checked} tip(s) checked; {pb_violations} violation(s)')
            for line in pb_findings[:25]:
                print(f'  {line}')
                if line.startswith('[ERROR]'):
                    total_fails += 1
                else:
                    total_warnings += 1
            if len(pb_findings) > 25:
                extra = len(pb_findings) - 25
                print(f'  ... and {extra} more')
                if severity_seen == 'ERROR':
                    total_fails += extra
                else:
                    total_warnings += extra
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] publish-boundary check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- 8f15f08d: Pipeline-Activation Coupling Gate (ERROR-ratchet live since 2026-07-08 — register 2b12e41d) ---
    print('\n--- Pipeline-Activation Coupling Gate (8f15f08d; ERROR-ratchet live — allowlist emptied 2026-07-08) ---')
    try:
        dsac_findings, dsac_checked, dsac_violations = check_dev_spec_activation_coupling(
            vault,
            customer_mode=(
                getattr(args, 'customer', False)
                or getattr(args, 'release', False)
            ),
        )
        if dsac_violations == 0:
            print(f'[PASS] {dsac_checked} locked/terminal-build-status dev-spec(s) checked — all have a correlated pipeline activation')
            total_passes += 1
        else:
            severity_seen = 'ERROR' if any('[ERROR]' in l for l in dsac_findings) else 'WARN'
            print(f'[{severity_seen}] {dsac_checked} locked/terminal-build-status dev-spec(s) checked; {dsac_violations} off-pipeline (no correlated activation)')
            for line in dsac_findings[:25]:
                print(f'  {line}')
                if line.startswith('[ERROR]'):
                    total_fails += 1
                else:
                    total_warnings += 1
            if len(dsac_findings) > 25:
                extra = len(dsac_findings) - 25
                print(f'  ... and {extra} more')
                if severity_seen == 'ERROR':
                    total_fails += extra
                else:
                    total_warnings += extra
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] dev-spec-activation-coupling check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- Fleet Boot Health (metis-g97): can every agent still be born? ---
    print('\n--- Fleet Boot Health (a gate on BIRTH fails when nobody is home) ---')
    try:
        fb_findings, fb_checked, fb_blocked = check_every_agent_can_still_boot(vault)
        if fb_checked == 0:
            print('[INFO] No agents with a terminal latest activation — skipping')
        elif fb_blocked == 0:
            print(f'[PASS] {fb_checked} agent(s) checked — every lineage can still produce a successor')
            total_passes += 1
        else:
            print(f'[ERROR] {fb_checked} agent(s) checked; {fb_blocked} CANNOT BOOT a successor')
            total_fails += fb_blocked
            for line in fb_findings[:25]:
                print(f'  {line}')
            if len(fb_findings) > 25:
                print(f'  ... and {len(fb_findings) - 25} more')
    except Exception as e:
        print(f'[FAIL] fleet-boot-health check CRASHED: {e}')
        total_fails += 1

    # --- Governed Autonomy S2 (bba40cd7): Mint Provenance Fail-Loud Floor (ERROR) ---
    print('\n--- Mint Provenance Fail-Loud Floor (bba40cd7; ERROR on index-invisible mint-governed files) ---')
    try:
        mp_findings, mp_checked, mp_violations = check_mint_provenance(vault)
        if mp_checked == 0:
            print('[INFO] No mint-governed (§Template-leg) types found — skipping')
        elif mp_violations == 0:
            print(f'[PASS] {mp_checked} mint-governed entry(ies) checked — all indexed')
            total_passes += 1
        else:
            print(f'[ERROR] {mp_checked} mint-governed entry(ies) checked; {mp_violations} invisible to the index')
            total_fails += mp_violations
            for line in mp_findings[:25]:
                print(f'  {line}')
            if len(mp_findings) > 25:
                print(f'  ... and {len(mp_findings) - 25} more')
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] mint-provenance check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- Event Ledger v2 Cutover Evidence Pins (P0 guardrail 2026-07-18; ERROR on drift) ---
    # A pinned-evidence file that drifts from the marker fail-closes EVERY v2 emit
    # crew-wide (load_cutover_marker raises). Before this check, that drift only
    # surfaced at the next agent's emit; now it fails loud here at validate/commit.
    # Reuses load_cutover_marker verbatim so this check is exactly the emit gate.
    print('\n--- Event Ledger v2 Cutover Evidence Pins (fail loud at validate, not at every emit) ---')
    try:
        marker_path = vault / '.tropo' / 'event-streams-v2.enabled'
        if not marker_path.is_file():
            print('[INFO] No cutover marker — pre-cutover studio; evidence-pin check skipped')
        else:
            from lib import event_identity as _cutover_ei
            try:
                _cutover_ei.load_cutover_marker(vault)
                print('[PASS] cutover marker verifies — pinned evidence + legacy epoch match (v2 emit unblocked)')
                total_passes += 1
            except Exception as _cutover_err:
                print('[ERROR] cutover marker verification FAILED — this blocks EVERY v2 emit crew-wide: '
                      f'{_cutover_err}')
                print('  Cure: restore the drifted pinned-evidence file to its marker-pinned bytes, or do a '
                      'governed marker re-pin if the change was intentional. The relations-header renderer now '
                      'skips pinned evidence; a manual edit to it must re-pin the marker in the same commit.')
                total_fails += 1
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] cutover-evidence-pin check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- 7627b589: Pipeline Event Fixture-Pollution Floor (ERROR on new leaks; INFO on grandfathered) ---
    print('\n--- Pipeline Event Fixture-Pollution Floor (7627b589; ERROR on new fixture-shaped pipeline events) ---')
    try:
        pep_findings, pep_checked, pep_new = check_pipeline_event_fixture_pollution(vault)
        if pep_checked == 0:
            print('[PASS] 0 fixture-shaped pipeline event(s) found in the production log')
            total_passes += 1
        elif pep_new == 0:
            print(f'[PASS] {pep_checked} fixture-shaped pipeline event(s) found, all in the documented '
                  f'historical allowlist (7627b589) — no new leaks')
            total_passes += 1
            for line in pep_findings:
                print(f'  {line}')
        else:
            print(f'[ERROR] {pep_checked} fixture-shaped pipeline event(s) found; {pep_new} NOT in the '
                  f'historical allowlist — a test run bypassed the sandbox mode')
            total_fails += pep_new
            for line in pep_findings:
                print(f'  {line}')
    except Exception as e:
        import traceback as _tb
        print(f'[FAIL] pipeline-event-fixture-pollution check CRASHED: {e}')
        _tb.print_exc()
        total_fails += 1

    # --- web-v4 Phase 0.6: local public snapshot contract (ERROR when sample exists) ---
    print('\n--- Public Snapshot Contract v1 (web-v4 Phase 0.6; fail-loud when sample exists) ---')
    ps_findings, ps_checked, ps_defects = typed_findings.run_check_family(
        "public-snapshot-contract", check_public_snapshot_contract, vault
    )
    if ps_checked == 0:
        print(f'[INFO] {PUBLIC_SNAPSHOT_SAMPLE_REL.as_posix()} absent — skipping')
    elif ps_defects == 0:
        print('[PASS] default public snapshot bundle is canonical and source-rederived')
        total_passes += 1
    else:
        print(f'[ERROR] default public snapshot bundle has {ps_defects} contract defect(s)')
        total_fails += ps_defects
        for finding in ps_findings:
            print(str(finding))

    # --- Summary ---
    print()
    print('=' * 70)
    print(f'Summary: {total_passes} passed, {total_fails} failed, {total_warnings} warnings, {total_normalizable} normalizable')
    print('=' * 70)

    validator_status = 0 if total_fails == 0 else 1
    return emit_validator_run_completed(
        passed=total_passes,
        failed=total_fails,
        warnings=total_warnings,
        normalizable=total_normalizable,
        meta_status_coverage_gaps=ms_gaps,
        meta_status_unresolved=ms_unresolved,
        provenance=run_provenance,
        exit_code=validator_status,
    )


if __name__ == '__main__':
    sys.exit(main())
