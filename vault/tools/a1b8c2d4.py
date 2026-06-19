#!/usr/bin/env python3
"""
---
uid: a1b8c2d4
title: build-release — Tool
name: build-release
type: tool
status: active
owner: argus
domain: Build a Tropo-OS release from the Argo vault — versioned folder, manifest, index, ship artifacts.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/a1b8c2d4.py --bump <patch|feature|release> [--dry-run] [--force]
script_path: vault/tools/a1b8c2d4.py
input:
  type: object
  required:
  - bump
  properties:
    bump:
      type: string
      enum:
      - patch
      - feature
      - release
    dry-run:
      type: boolean
    force:
      type: boolean
      description: Bypass overwrite guard
output:
  type: object
  properties:
    verdict:
      type: string
      enum:
      - pass
      - version-conflict
      - validator-failed
      - fail
    version:
      type: string
    output_dir:
      type: string
destructive: true
audit_required: false
writes_scope:
- releases/**
- .tropo/version.md
governance_category: lifecycle
description: 'The MECHANICAL layer of the build-release playbook. Reads vault index for extraction_scope: ship entries + .tropo/ kernel directory, produces a versioned release folder with file copying, version bumping, manifest generation, index building. Does NOT handle release notes, cold-boot testing, or verification (those are the REASONING layer). Step 0 + Step 0b pre-flight gates run validators before any extract work begins. Overwrite guard refuses to overwrite a stale output directory; --force bypasses (for retries). Composes-with the dev-pipeline activation flow.'
domain_tags:
- build
- release
- ship-pipeline
- version-bump
- manifest
- mechanical-layer
trigger_description: Reach for this when executing Stream I (build + ship) of any dev-pipeline cycle. Run with --bump patch (e.g., v1.13.x → v1.14.0 isn't patch — that's feature; v1.14.0 → v1.14.1 IS patch), --bump feature (v1.14.0 → v1.15.0), or --bump release (v1.14.0 → v2.0.0). Step 0 + Step 0b pre-flight gates run validators automatically and refuse to build on validator failures. Use --dry-run to preview the build without writing. Use --force only on retries after fixing the conflict that triggered the overwrite guard.
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
- build
- release
- ship-pipeline
- mechanical-layer
- v1.15-stream-b
subsystem_hub:
- 8dd772a0
---
"""

"""
Build a Tropo-OS release from the Argo vault.

Reads the vault index for scope:ship entries and the .tropo/ kernel directory.
Produces a versioned release folder with the complete tropo-os product.

This is the MECHANICAL layer of the build-release playbook.
It handles: file copying, version bumping, manifest generation, index building.
It does NOT handle: release notes, cold-boot testing, verification (those are the REASONING layer).

Usage:
    python3 .tropo/scripts/build-release.py --bump <patch|feature|release> [--dry-run] [--force]

Example:
    python3 .tropo/scripts/build-release.py --bump patch
    python3 .tropo/scripts/build-release.py --bump feature --dry-run
    python3 .tropo/scripts/build-release.py --bump patch --force   # bypass overwrite guard

Overwrite guard (added 2026-05-01 by vela-v37 per Stream 2 task `87e3b4d6`):
    Before creating the build + testing output directories, the script checks if
    they already exist. If they do AND their internal version.md disagrees with
    the build target version, the script REFUSES to overwrite (exit 2) and
    prints a recovery hint. Catches the V36 2026-04-30 retrospective scenario:
    `--bump patch` from stale source version.md, output directory already
    exists with prior real content, blind overwrite. Use `--force` to bypass
    the guard for legitimate overwrite cases (re-build after intentional source
    change). DRY_RUN bypasses the guard (no actual overwrite occurs).
"""

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ─── lib/ship_extract/ engine (v1.43.0 Stream C — substrate UID c47b9d82) ───
# Adds the scripts directory to sys.path so `from lib.ship_extract import ...` resolves
# regardless of how build-release.py is invoked (cwd-independent).
# v1.56 Lane S: script relocated to vault/tools/; lib/ imports from .tropo/scripts/
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2] / '.tropo' / 'scripts')
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from lib.ship_extract import (
    read_manifest_root_uid as _engine_read_manifest_root_uid,
    load_manifest_entries as _engine_load_manifest_entries,
    resolve_source_path as _engine_resolve_source_path,
    should_exclude_kernel as _engine_should_exclude_kernel,
    validate_manifest_basic as _engine_validate_manifest_basic,
    sha256_file as _engine_sha256_file,
    copy_file as _engine_copy_file,
)
# Pipeline Activation Key gate (dev-spec 2ffdd9d6, brief f8cda3dd) — build + ship
# refuse without a runtime-minted, unforgeable fingerprint of a legitimate pipeline-run.
from lib.release_authorization import require_release_authorization, ReleaseAuthorizationError

# ─── Configuration ───────────────────────────────────────────────────────────

VAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLATFORM_ROOT = os.path.dirname(VAULT_ROOT)   # one level above the Studio
INDEX_PATH = os.path.join(VAULT_ROOT, 'vault', '00-index.jsonl')
VERSION_PATH = os.path.join(VAULT_ROOT, '.tropo', 'version.md')
# RELEASES_DIR sits OUTSIDE the platform repo entirely — releases are product artifacts,
# not source-repo content. Convention: sibling to the platform repo at <dev-root>/tropo-releases/.
# Path migration history: argo-os/releases/ → tropo-ai/releases/ (2026-05-11 partial move) →
# /tropo-releases/ (2026-05-18 outside-repo final per Mike-V47 directive — eliminates copy step
# for release-cold-boot-walk + clean separation of source vs product artifact).
RELEASES_DIR = os.path.join(os.path.dirname(PLATFORM_ROOT), 'tropo-releases')

# Directories and files copied by convention (not through the Vault)
KERNEL_DIR = os.path.join(VAULT_ROOT, '.tropo')

# Manifest-driven build (v1.12.1 MVP Phase E) — replaces legacy parallel-mirror handling
# (ROOT_FILES list + SKELETON_DIRS constant + load-vault-ship-files function +
# step_5/5b/6's parallel-mirror fallbacks) with a graph walk over ship-artifact
# entries rooted at the Tropo Release Structure project.
#
# Architecture: ship-artifact.capsule v1.1.4 (UID eeb59ddf) defines the contract;
# Build-Release Pipeline arch-spec v1.0 (UID 747c33c9) defines the pipeline.
# v1.12.1 implements MVP Phase E (Phases 0/1-basic/3/6); full spec compliance
# (Phase 2 orphan-zombie scanner, Phase 4 cleanup engine, Phase 5 link checker,
# 23-check validator, deterministic zip mode, build lock) deferred to v1.12.2/v1.13.

SHIP_ARTIFACT_CAPSULE_PATH = os.path.join(VAULT_ROOT, '.tropo', 'capsules', 'ship-artifact.capsule.md')

# Files to EXCLUDE from the kernel copy (argo-private scripts, migration
# playbooks specific to pre-v1.1 internal transitions, etc.)
# The `migrations/` folder itself stays — the concept is preserved for future
# version transitions — but specific pre-release migration playbooks are not
# shipped to external users. These exclusions are mirrored as ship-artifact
# entries with `source_mode: skip` (UIDs: 0a3aba36, e2ab6063, 5bf88693, 6a559168,
# 72fdd2e3, daf0d9f9, 98528ee9). Kept here as a defensive belt-and-suspenders
# check during the v1.12.1 transition; v1.12.2 evaluates removing this constant
# once manifest-driven exclusions are validated as fully equivalent.
KERNEL_EXCLUDE_PATTERNS = [
    'register-kernel.py',                    # migration-specific, not product
    'build-release.py',                      # v1.5: Argo-only release builder; users don't build Tropo releases from their own vault
    'migrate-file-status.playbook.md',       # pre-v1.1 internal migration
    'migrate-index-format.playbook.md',      # pre-v1.1 internal migration
    'v030-founding-citizens.playbook.md',    # v0.2 → v0.3 — no v0.x users
    'v030-generate-capsule.playbook.md',     # v0.2 → v0.3 — no v0.x users
    'v030-replace-agents.playbook.md',       # v0.2 → v0.3 — no v0.x users
]

DRY_RUN = '--dry-run' in sys.argv
FORCE = '--force' in sys.argv   # added 2026-05-01 (vela-v37, Stream 2 task 87e3b4d6) — bypasses overwrite guard


# ─── Version Management ─────────────────────────────────────────────────────

def read_current_version(version_path):
    """Read the current version from .tropo/version.md frontmatter."""
    with open(version_path, 'r') as f:
        content = f.read()
    match = re.search(r'version:\s*["\']?(\d+\.\d+\.\d+)', content)
    if match:
        return match.group(1)
    # Fallback: look for a version pattern anywhere
    match = re.search(r'(\d+\.\d+\.\d+)', content)
    if match:
        return match.group(1)
    return '0.0.0'


def bump_version(current, bump_type):
    """Apply semver bump."""
    parts = current.split('.')
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if bump_type == 'release':
        return f'{major + 1}.0.0'
    elif bump_type == 'feature':
        return f'{major}.{minor + 1}.0'
    elif bump_type == 'patch':
        return f'{major}.{minor}.{patch + 1}'
    else:
        raise ValueError(f'Unknown bump type: {bump_type}')


# ─── Index Reading ───────────────────────────────────────────────────────────

def load_ship_entries(index_path):
    """Load all entries tagged for release: extraction_scope: ship.

    v1.12.1 amendment: dropped backward-compat fallback for the deprecated
    extraction_scope value (V35 deprecated the legacy value 2026-04-28; v1.10
    enforcement at STRICT mode 2026-05-07 catches stale values; 13-day grace
    period elapsed). Vaults using the deprecated value will not have entries
    extracted; surface via validator.

    Original fix: 2026-04-28 by vela-v36 — surfaced during v1.4 ship-zip
    pre-flight when this function returned 0 entries because all 157 ship-tagged
    vault entries carried the canonical extraction_scope value.

    v1.25.0 note: this function is a positive-filter (opt-in to 'ship'); the
    new `extraction_scope: external` value introduced for vault projections of
    imported user content (per Import Primitive Architecture Specification
    [vault/files/2b49ba79.md] §C.7) is automatically excluded from ship builds
    by virtue of not matching 'ship'. No code change needed; documented for
    clarity.
    """
    entries = []
    with open(index_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            scope = row.get('extraction_scope')
            if row.get('scope') == 'ship' or scope == 'ship':
                entries.append(row)
    return entries


# v1.43.0 Stream C refactor: function definitions moved to lib/ship_extract/.
# Thin wrappers preserve existing call signatures while delegating to the shared engine.

resolve_source_path = _engine_resolve_source_path  # signature unchanged
sha256_file = _engine_sha256_file  # signature unchanged
copy_file = _engine_copy_file  # signature unchanged


def should_exclude_kernel(filepath):
    """Backward-compat wrapper — passes module-level KERNEL_EXCLUDE_PATTERNS to engine."""
    return _engine_should_exclude_kernel(filepath, KERNEL_EXCLUDE_PATTERNS)


# ─── Build Steps ─────────────────────────────────────────────────────────────

def step_1_compute_version(bump_type):
    """Step 4a: Read current version and compute new version."""
    current = read_current_version(VERSION_PATH)
    new_version = bump_version(current, bump_type)
    print(f'  Version: {current} → {new_version} ({bump_type})')
    return current, new_version


def guard_overwrite(new_version, build_dir, testing_dir):
    """Pre-write guard against the V36 2026-04-30 retrospective scenario.

    The scenario: source `.tropo/version.md` is stale (still showing an older
    version while the actual source content is newer). `--bump patch` from
    stale source computes a wrong new_version. The output directory already
    exists at that path with prior real working content. The script blindly
    overwrites. Pure luck saved the v1.3.1 dist zip last time.

    The guard: before any file creation, check if `build_dir` or `testing_dir`
    already exist. If they do, look for an internal version.md stamp. If the
    stamp's version disagrees with `new_version`, REFUSE to overwrite (exit 2)
    with a recovery hint.

    Bypasses:
    - `--force` flag — deliberate overwrite case (re-run after source change).
    - DRY_RUN — never writes; guard not needed.

    Raises:
        SystemExit(2): if existing dir's version.md disagrees with new_version
                       OR if existing dir has no version.md (cannot verify),
                       AND --force not specified.
    """
    if DRY_RUN:
        return

    for label, target_dir in [('build', build_dir), ('testing', testing_dir)]:
        if not os.path.exists(target_dir):
            continue   # nothing to overwrite — clean

        # Look for version.md in the existing directory
        candidate_paths = [
            os.path.join(target_dir, '.tropo', 'version.md'),
            os.path.join(target_dir, 'version.md'),
        ]
        existing_version = None
        for p in candidate_paths:
            if os.path.exists(p):
                existing_version = read_current_version(p)
                break

        if existing_version is None:
            if FORCE:
                print(f'  ⚠ {label} dir exists but has no version.md — proceeding (--force)')
                continue
            print(f'\n=== BUILD GUARD: REFUSING OVERWRITE ({label} dir) ===', file=sys.stderr)
            print(f'  Target: {target_dir}', file=sys.stderr)
            print(f'  Issue:  directory exists but contains no version.md stamp.', file=sys.stderr)
            print(f'          Cannot verify content-version agreement; refusing overwrite.', file=sys.stderr)
            print(f'  Recovery:', file=sys.stderr)
            print(f'    - If this is intended: re-run with --force flag', file=sys.stderr)
            print(f'    - If this is unexpected: inspect {target_dir} contents.', file=sys.stderr)
            print(f'      Move/archive before retrying.', file=sys.stderr)
            sys.exit(2)

        if existing_version != new_version:
            if FORCE:
                print(f'  ⚠ {label} dir version.md = {existing_version} ≠ build target '
                      f'{new_version} — proceeding (--force)')
                continue
            print(f'\n=== BUILD GUARD: REFUSING OVERWRITE ({label} dir) ===', file=sys.stderr)
            print(f'  Target: {target_dir}', file=sys.stderr)
            print(f'  Issue:  existing directory has version.md = {existing_version}', file=sys.stderr)
            print(f'          but build target version is {new_version}.', file=sys.stderr)
            print(f'          Overwriting would clobber {existing_version} working content', file=sys.stderr)
            print(f'          (the V36 2026-04-30 scenario — caught by luck last time).', file=sys.stderr)
            print(f'  Recovery:', file=sys.stderr)
            print(f'    - If source .tropo/version.md is stale: update source first, then re-run.', file=sys.stderr)
            print(f'    - If you intentionally want to overwrite the existing {existing_version}', file=sys.stderr)
            print(f'      content with a {new_version} build: run with --force flag.', file=sys.stderr)
            print(f'    - If unsure: archive {target_dir} to a safe location before proceeding.', file=sys.stderr)
            sys.exit(2)
        # version matches — content-mismatch check is too expensive for v0.1; deferred to v0.2.
        # The version-stamp match is sufficient defense for the V36 retrospective scenario.


def step_2_create_output(new_version):
    """Step 4b: Create the output directory."""
    product_name = f'tropo-os-v{new_version}'
    build_dir = os.path.join(RELEASES_DIR, f'v{new_version}', 'builds', product_name)
    testing_dir = os.path.join(RELEASES_DIR, f'v{new_version}', 'testing', product_name)
    dist_dir = os.path.join(RELEASES_DIR, f'v{new_version}', 'dist')

    if not DRY_RUN:
        # Pre-write guard — added 2026-05-01 (vela-v37, Stream 2 task 87e3b4d6).
        # Catches V36's 2026-04-30 retrospective scenario (--bump patch from
        # stale source clobbering existing different-version output dir).
        guard_overwrite(new_version, build_dir, testing_dir)
        os.makedirs(build_dir, exist_ok=True)
        os.makedirs(testing_dir, exist_ok=True)
        os.makedirs(dist_dir, exist_ok=True)

    print(f'  Output: {build_dir}')
    return build_dir, testing_dir, dist_dir


# ─── MVP Phase E (v1.12.1) — Manifest-driven build ──────────────────────────
# Phases 0/1-basic/3/6 of the locked Build-Release Pipeline arch-spec (UID 747c33c9).
# Replaces the legacy parallel-mirror handling. Full spec compliance (Phase 2
# orphan/zombie scanner, Phase 4 cleanup engine, Phase 5 link checker, 23-check
# validator, deterministic zip mode, build lock) deferred to v1.12.2 / v1.13.

# v1.43.0 Stream C refactor: read_manifest_root_uid + load_manifest_entries +
# validate_manifest_basic moved to lib/ship_extract/. Thin wrappers below preserve
# the build-release.py call signatures (which take just index_path + manifest_root_uid,
# implicitly target='release').

read_manifest_root_uid = _engine_read_manifest_root_uid  # signature unchanged (capsule_path, target='release')


def load_manifest_entries(index_path, manifest_root_uid):
    """Backward-compat wrapper — calls engine with VAULT_ROOT + target='release'."""
    return _engine_load_manifest_entries(index_path, VAULT_ROOT, manifest_root_uid, target='release')


def validate_manifest_basic(entries, vault_root):
    """Backward-compat wrapper — calls engine with target='release' (release-only validation rules).

    Engine's validate_manifest_basic does sys.exit on failure (matches pre-Stream-C behavior).
    If we reach the success-path print, validation passed.
    """
    _engine_validate_manifest_basic(entries, vault_root, target='release')
    print(f'  ✓ Phase 1 (basic) PASS — {len(entries)} entries resolved')


def _resolve_argo_path(canonical_source):
    """Strip argo-os/ prefix to get vault-relative path."""
    if canonical_source.startswith('argo-os/'):
        return canonical_source[len('argo-os/'):]
    return canonical_source


def _build_override_index(entries):
    """Build a map from canonical_source path → entry, for files that have
    explicit ship-artifact entries (skip or direct-copy override) under a
    recursive-ship-all parent. Used to honor override-child precedence."""
    overrides = {}
    for e in entries:
        if e.get('kind') != 'file':
            continue
        if e.get('source_mode') not in ('skip', 'direct-copy'):
            continue
        cs = e.get('canonical_source', '')
        if cs:
            overrides[_resolve_argo_path(cs)] = e
    return overrides


# Ship-artifact entries handled by dedicated legacy steps (kept during MVP transition).
# v1.12.2 evaluates folding these into the manifest walker fully.
MANIFEST_SKIP_HANDLED_ELSEWHERE = {
    '0dc0a350',   # .tropo recursive-ship-all → step_3_copy_kernel (has special concierge handling)
    '482c6918',   # .tropo-studio recursive-ship-all → step_7_create_vault_skeleton (wholesale template copy)
    '3d21dbd1',   # vault recursive-ship-tagged → step_4_copy_ship_entries (index-driven; builds shipped index too)
    '79cca015',   # argo-os/ root structure-only → build_dir already created by step_2_create_output
}


def build_from_manifest(build_dir, entries):
    """Phase 3 (Build Output) — walk graph, apply source_mode per entry, emit recipient tree.

    MVP Phase E: handles all six source_modes per arch-spec §2.4 table.
    Skips entries handled by dedicated legacy steps (set above).
    Does NOT include Phase 4 cleanup (marker stripping, link rewriting) —
    deferred to v1.12.2.
    """
    overrides = _build_override_index(entries)
    counts = {
        'recursive-ship-all': 0,
        'recursive-ship-tagged': 0,
        'explicit-children': 0,
        'structure-only': 0,
        'direct-copy': 0,
        'skip': 0,
    }
    files_emitted = 0
    files_skipped_by_override = 0

    # Topological-walk sort key per arch-spec Required Behavior #15:
    # (parent-UID, canonical_source) lexicographic for determinism.
    sorted_entries = sorted(
        entries,
        key=lambda e: (e.get('parent') or '', e.get('canonical_source', ''))
    )

    for entry in sorted_entries:
        # Skip entries handled by dedicated legacy steps during MVP transition
        if entry.get('uid') in MANIFEST_SKIP_HANDLED_ELSEWHERE:
            continue

        mode = entry.get('source_mode', '')
        kind = entry.get('kind', '')
        cs = entry.get('canonical_source', '')
        op = entry.get('output_path', '')

        # Default output_path: mirror canonical_source minus argo-os/ prefix
        if not op:
            op = _resolve_argo_path(cs)
        op = op.rstrip('/')

        src_abs = os.path.join(VAULT_ROOT, _resolve_argo_path(cs)) if cs else None
        dst_abs = os.path.join(build_dir, op) if op else None

        counts[mode] = counts.get(mode, 0) + 1

        if mode == 'skip':
            continue

        if kind == 'folder':
            if mode == 'structure-only':
                if not DRY_RUN and dst_abs:
                    os.makedirs(dst_abs, exist_ok=True)
            elif mode == 'recursive-ship-all':
                if not src_abs or not os.path.isdir(src_abs):
                    continue
                if not DRY_RUN and dst_abs:
                    os.makedirs(dst_abs, exist_ok=True)
                for root, dirs, files in os.walk(src_abs):
                    rel = os.path.relpath(root, src_abs)
                    rel = '' if rel == '.' else rel
                    for fname in files:
                        src_file = os.path.join(root, fname)
                        src_file_rel = os.path.relpath(src_file, VAULT_ROOT)
                        # Honor per-file override (skip or direct-copy under recursive parent)
                        if src_file_rel in overrides:
                            files_skipped_by_override += 1
                            continue
                        # Belt-and-suspenders: respect KERNEL_EXCLUDE_PATTERNS for argo-private files
                        if should_exclude_kernel(src_file):
                            continue
                        dst_file = os.path.join(dst_abs, rel, fname) if rel else os.path.join(dst_abs, fname)
                        copy_file(src_file, dst_file, DRY_RUN)
                        files_emitted += 1
            elif mode == 'recursive-ship-tagged':
                # MVP: vault/ folder ships via step_4_copy_ship_entries (index-driven).
                # Manifest entry 3d21dbd1 declares the intent; step_4 implements.
                # Skip here — handled separately in main().
                continue
            elif mode == 'explicit-children':
                # MVP: not used in current 31-entry manifest; defer full implementation to v1.12.2.
                if not DRY_RUN and dst_abs:
                    os.makedirs(dst_abs, exist_ok=True)
        elif kind == 'file' and mode == 'direct-copy':
            if src_abs and os.path.exists(src_abs):
                copy_file(src_abs, dst_abs, DRY_RUN)
                files_emitted += 1
            else:
                # Phase 1 should have caught this; defensive
                print(f'    ⚠ direct-copy source missing: {cs}', file=sys.stderr)

    print(f'  Manifest build: {files_emitted} files emitted; {files_skipped_by_override} skipped by override')
    print(f'    Source-mode breakdown:')
    for mode, n in counts.items():
        print(f'      {mode}: {n} entries')
    return files_emitted


def step_phase0_bootstrap():
    """Phase 0 — Bootstrap: resolve manifest_root_uid, load graph, verify integrity."""
    print('Phase 0 — Bootstrap (resolve manifest_root_uid + load ship-artifact graph):')
    manifest_root = read_manifest_root_uid(SHIP_ARTIFACT_CAPSULE_PATH)
    print(f'  manifest_root_uid: {manifest_root}')
    entries = load_manifest_entries(INDEX_PATH, manifest_root)
    print(f'  Ship-artifact entries: {len(entries)}')
    # Basic integrity: at least one entry, at least one root (parent: null or empty)
    if not entries:
        print(f'  ✗ BOOTSTRAP HALT: no ship-artifact entries with member_of: [{manifest_root}]', file=sys.stderr)
        sys.exit(64)
    return entries


# ─── Legacy build steps (preserved for kernel + vault entries) ───────────────

def step_3_copy_kernel(build_dir):
    """Step 4c: Copy the .tropo/ kernel directory.

    NOTE (v1.12.1 MVP Phase E): This kernel copy is ALSO covered by ship-artifact
    entry 0dc0a350 (.tropo recursive-ship-all). For MVP we keep this function as
    the canonical kernel copy because it has special concierge handling that the
    manifest walker doesn't yet replicate. v1.12.2 evaluates collapsing into the
    manifest walker fully.
    """
    src_kernel = KERNEL_DIR
    dst_kernel = os.path.join(build_dir, '.tropo')
    copied = 0
    skipped = 0

    # Precise match for the concierge directory only — NOT concierge-paths
    # (prior substring match `'concierge' in root` also caught
    # `.tropo/playbooks/concierge-paths/` and dropped the v1.2.0 outcome
    # playbooks from the ship. Bug surfaced by Gate 4 cold-boot on v1.3.0
    # build, 2026-04-22.)
    concierge_dir = os.path.join(src_kernel, 'concierge')
    for root, dirs, files in os.walk(src_kernel):
        # Skip concierge subtree — copied separately below with its own governance
        if root == concierge_dir or root.startswith(concierge_dir + os.sep):
            continue

        for fname in files:
            src = os.path.join(root, fname)
            if should_exclude_kernel(src):
                skipped += 1
                continue

            rel = os.path.relpath(src, src_kernel)
            dst = os.path.join(dst_kernel, rel)
            copy_file(src, dst, DRY_RUN)
            copied += 1

    # Also copy the concierge (it ships — it's the first-boot experience)
    concierge_src = os.path.join(src_kernel, 'concierge')
    if os.path.exists(concierge_src):
        for root, dirs, files in os.walk(concierge_src):
            for fname in files:
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, src_kernel)
                dst = os.path.join(dst_kernel, rel)
                copy_file(src, dst, DRY_RUN)
                copied += 1

    print(f'  Kernel: {copied} files copied, {skipped} excluded')
    return copied


def step_4_copy_ship_entries(build_dir, entries):
    """Step 4d-e: Copy scope:ship vault entries and build the output index."""
    dst_files = os.path.join(build_dir, 'vault', 'files')
    dst_index = os.path.join(build_dir, 'vault', '00-index.jsonl')

    if not DRY_RUN:
        os.makedirs(dst_files, exist_ok=True)

    copied = 0
    missing = 0
    index_rows = []

    for entry in entries:
        # Skip kernel entries — they're already copied via the kernel directory
        if entry.get('type') == 'kernel':
            continue

        src = resolve_source_path(entry, VAULT_ROOT)
        if not os.path.exists(src):
            print(f'    MISSING: {entry["uid"]} — {src}')
            missing += 1
            continue

        dst = os.path.join(dst_files, f'{entry["uid"]}.md')
        copy_file(src, dst, DRY_RUN)
        copied += 1

        # Build the output index row (strip argo-private fields)
        out_row = {k: v for k, v in entry.items()
                   if k not in ('extraction_scope',)}
        index_rows.append(out_row)

    # v1.9.0 Round 3: filter member_of arrays so user vault has no dangling
    # references. Source vault keeps full historical refs; build extract only
    # carries refs to UIDs whose files are also shipping. Closes concierge B4
    # finding §3.2 (6 dangling parent references in shipped vault content).
    shipped_uids = {row['uid'] for row in index_rows if row.get('uid')}
    pruned_total = 0
    for row in index_rows:
        if isinstance(row.get('member_of'), list):
            original = row['member_of']
            filtered = [u for u in original if u in shipped_uids]
            n_pruned = len(original) - len(filtered)
            if n_pruned > 0:
                row['member_of'] = filtered
                pruned_total += n_pruned
    if pruned_total > 0:
        print(f'  member_of dangling-ref filter: pruned {pruned_total} parent refs to non-shipping UIDs')

    if not DRY_RUN:
        os.makedirs(os.path.dirname(dst_index), exist_ok=True)
        with open(dst_index, 'w') as f:
            for row in index_rows:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')

    print(f'  Vault entries: {copied} copied, {missing} missing, {len(index_rows)} index rows')
    return copied, missing, index_rows


# step_5_copy_root_files: REMOVED v1.12.1 — replaced by manifest-driven Phase 3
# (build_from_manifest). Root-doc ship-artifact entries (UIDs 0132f318 AGENTS.md,
# 6cf8e659 README.md, 7f746921 CAPSULE.md, 93a75e93 STUDIO.md, ca667939 CLAUDE.md,
# 45233d71 START-TROPO.md, 5013db2a operating-agreement.md, 4a7e1c9b LICENSE
# [v1.12.1 NEW], 5b8f2d0c .cursorrules [v1.12.1 NEW], 6c9a3e1d .github/ [v1.12.1 NEW],
# f3473526 TROPO-CAPABILITIES.md) declare canonical_source under
# .tropo/templates/root-docs/ + .tropo/templates/ide-configs/ with output_path
# overrides relocating to recipient root. The manifest walker emits each file.
#
# RELEASE-NOTES.md remains a generated artifact (NOT a ship-artifact); per
# arch-spec 747c33c9 §1 Thesis the build-equivalence test confirms no functional
# regression. Generation logic moves to a v1.12.2 dedicated step
# (Talos-lane / future implementation); v1.12.1 ships without RELEASE-NOTES.md
# auto-generation — agent authors it before ship per existing v1.10/v1.11/v1.12
# practice.


# load_starter_vault_files + step_5b_copy_starter_vault_files: REMOVED v1.12.1 —
# the parallel argo-os/starter/ mirror walker is replaced by the manifest-driven
# Phase 3 (build_from_manifest). The recursive-ship-tagged behavior for vault/
# entries is declared by ship-artifact 3d21dbd1 and implemented by
# step_4_copy_ship_entries (index-driven, kept during MVP transition).
# Files tagged extraction_scope:ship outside vault/ would need their own
# ship-artifact entries — gap surfaced for v1.12.2 if any exist.
#
# step_6_create_skeleton: REMOVED v1.12.1 — replaced by manifest-driven Phase 3.
# Top-level structure-only directories (boards/, channels/, collections/,
# decisions/, playbooks/, projects/, settings/, system/) are created by
# ship-artifact entries with source_mode: structure-only (8 entries; UIDs
# 50a7c8d3, 53f289af, 854d7fb6, ae9e70fb, b772b854, c343a672, cf27103e,
# db3477d1). agents/ user-facing directory ships from agents-skeleton template
# via 0c93cf7a recursive-ship-all (covers governance files + visitors/ +
# directors/ + sa/ subdirs; agent-subdir bulk copy is handled by manifest walk).
# Runtime subdirectories (system/updates/applied|failed|pending,
# system/vault-steward, agents/.tropo-capsule/memory) are created on first
# use by other code paths — not needed at install time.


def step_3a_regenerate_catalogs():
    """Step 4c.1: Regenerate capability catalogs before kernel copy.

    Orpheus O17 finding e4c2f9a1 (2026-06-12): the generator moved from
    .tropo/scripts/generate-capability-catalogs.py → vault/tools/d4e9a2c7.py at v1.56
    but build-release.py had no regen step, causing catalogs to freeze at 2026-05-14.
    This step ensures .tropo/{tool,skill,sa-agent}-catalog.md is current-as-of-build
    so a new Studio agent can discover all ship-scoped tools.

    Must run BEFORE step_3_copy_kernel (which copies .tropo/ into the build).
    """
    catalog_gen = os.path.join(VAULT_ROOT, 'vault', 'tools', 'd4e9a2c7.py')
    if not os.path.exists(catalog_gen):
        print(f'  ⚠ catalog generator not found at vault/tools/d4e9a2c7.py — catalogs NOT regenerated')
        return
    if DRY_RUN:
        print(f'  [DRY-RUN] Would run: python3 vault/tools/d4e9a2c7.py --apply')
        return
    import subprocess as _sp
    result = _sp.run(
        [sys.executable, catalog_gen, '--apply'],
        capture_output=True, text=True, cwd=str(VAULT_ROOT),
        stdin=_sp.DEVNULL, timeout=60,
    )
    if result.returncode != 0:
        print(f'  ⚠ catalog regen failed (exit {result.returncode}): {result.stderr[:200]}')
    else:
        lines = [l for l in (result.stdout or '').splitlines() if l.strip()]
        for l in lines[-3:]:
            print(f'  {l}')
        print(f'  ✓ capability catalogs regenerated (current-as-of-build)')


def step_3b_copy_vault_tools(build_dir):
    """Step 4c.2: Copy vault/tools/ wholesale alongside the kernel.

    vault/tools/ holds the canonical tool implementations that .tropo/scripts/
    shims forward to. The shims ship as part of .tropo/ (step_3_copy_kernel);
    their targets must also ship or the scripting layer is dead in a stranger's
    download. Ships wholesale — not per-tool extraction_scope — per Argus A92
    ruling fdef56ea: the scripting layer is atomic infrastructure; per-tool
    tagging re-opens the exact omission bug.

    Added: v1.63 P0 fix (Talos T12) per ruling fdef56ea + directive 03b17aaa.
    """
    src_tools = os.path.join(VAULT_ROOT, 'vault', 'tools')
    dst_tools = os.path.join(build_dir, 'vault', 'tools')

    if not os.path.isdir(src_tools):
        print(f'  ✗ vault/tools/ not found at {src_tools} — scripting layer targets cannot ship',
              file=sys.stderr)
        sys.exit(1)

    if not DRY_RUN:
        os.makedirs(dst_tools, exist_ok=True)

    copied = 0
    for fname in sorted(os.listdir(src_tools)):
        src_file = os.path.join(src_tools, fname)
        if not os.path.isfile(src_file):
            continue
        dst_file = os.path.join(dst_tools, fname)
        copy_file(src_file, dst_file, DRY_RUN)
        copied += 1

    print(f'  vault/tools/: {copied} files copied (scripting layer targets)')
    return copied


def step_3d_copy_vault_playbooks(build_dir):
    """Step 4c.3: Copy vault/playbooks/ wholesale alongside the kernel.

    vault/playbooks/ holds the canonical playbook implementations that
    .tropo/playbooks/ thin-pointers target (the two-file pattern).
    The thin-pointers ship as part of the kernel (step_3_copy_kernel);
    their targets MUST ship or the boot contract is dead in a stranger's
    download. Ships wholesale mirroring the vault/tools/ logic (fdef56ea).

    Added: v1.70 fix (Talos T18) per Orpheus finding b1f9c3d2.
    """
    src_playbooks = os.path.join(VAULT_ROOT, 'vault', 'playbooks')
    dst_playbooks = os.path.join(build_dir, 'vault', 'playbooks')

    if not os.path.isdir(src_playbooks):
        print(f'  ✗ vault/playbooks/ not found at {src_playbooks} — playbook targets cannot ship',
              file=sys.stderr)
        sys.exit(1)

    if not DRY_RUN:
        os.makedirs(dst_playbooks, exist_ok=True)

    copied = 0
    for fname in sorted(os.listdir(src_playbooks)):
        src_file = os.path.join(src_playbooks, fname)
        if not os.path.isfile(src_file):
            continue
        dst_file = os.path.join(dst_playbooks, fname)
        copy_file(src_file, dst_file, DRY_RUN)
        copied += 1

    print(f'  vault/playbooks/: {copied} files copied (playbook targets)')
    return copied


def step_3c_assert_forward_targets(build_dir):
    """Step 4c.3: Assert every .tropo/scripts/ shim's vault/tools/ target is present.

    Scans every .py file in the build's .tropo/scripts/. For each that references
    vault/tools/<uid>.py (in any comment or code), asserts that file exists in
    the build's vault/tools/. Fails the build if any forward-target is missing.

    This is the load-bearing half of ruling fdef56ea: even if ship-scoping ever
    changes, this guard makes 'shipped shim with dead target' structurally
    impossible at build time — caught here, never by a stranger.

    Added: v1.63 P0 fix (Talos T12) per ruling fdef56ea + directive 03b17aaa.
    """
    import re as _re
    _UID_PATTERN = _re.compile(r'vault/tools/([0-9a-f]{8})\.py')

    scripts_dir = os.path.join(build_dir, '.tropo', 'scripts')
    tools_dir = os.path.join(build_dir, 'vault', 'tools')

    if DRY_RUN:
        # In dry-run, scan the source dirs (build dirs don't exist yet).
        scripts_dir = os.path.join(VAULT_ROOT, '.tropo', 'scripts')
        tools_dir = os.path.join(VAULT_ROOT, 'vault', 'tools')
        print(f'  [DRY-RUN] Forward-target guard: scanning source dirs')

    if not os.path.isdir(scripts_dir):
        print(f'  ⚠ .tropo/scripts/ not found — forward-target guard skipped')
        return

    dead = []
    checked = 0
    for fname in sorted(os.listdir(scripts_dir)):
        if not fname.endswith('.py'):
            continue
        try:
            with open(os.path.join(scripts_dir, fname), 'r') as f:
                content = f.read()
        except Exception:
            continue
        for uid in _re.findall(_UID_PATTERN, content):
            checked += 1
            target = os.path.join(tools_dir, f'{uid}.py')
            if not os.path.exists(target):
                dead.append((fname, uid))

    if dead:
        print(f'\n  ✗ BUILD REFUSED — forward-target guard: {len(dead)} dead forwarder(s):',
              file=sys.stderr)
        for shim, uid in dead:
            print(f'    .tropo/scripts/{shim} → vault/tools/{uid}.py — MISSING', file=sys.stderr)
        print(f'    Ensure vault/tools/ ships every target referenced by .tropo/scripts/ shims.',
              file=sys.stderr)
        sys.exit(1)

    print(f'  Forward-target guard: {checked} shim→target pair(s) checked — all present')


def step_7_create_vault_skeleton(build_dir):
    """Step 4g: Copy the .tropo-studio/ skeleton template into the release.

    Per 2026-04-20 amendment (Vela V31 per Mike direction), the .tropo-studio/
    skeleton is a proper template that ships a structured vault-admin tier,
    not ad-hoc stubs. Template lives at .tropo/templates/.tropo-studio-skeleton/
    and is copied wholesale into the build.

    This closes the Tier Reachability ship gap — a new user unzipping the
    release now has every Tier 2 file the v2.2 activation playbook expects,
    so first-boot activation doesn't HALT.

    Fail-loud on template missing, per ADR-032 Tier Reachability amendment:
    declared-present-but-unreachable halts the build instead of silent-skip.
    """
    skeleton_src = os.path.join(VAULT_ROOT, '.tropo', 'templates', '.tropo-studio-skeleton')
    vault_dst = os.path.join(build_dir, '.tropo-studio')

    if not os.path.exists(skeleton_src):
        raise SystemExit(
            f'.tropo-studio/ skeleton template not found at {skeleton_src}.\n'
            f'Expected location per Tropo-OS convention (.tropo/templates/.tropo-studio-skeleton/).\n'
            f'If this vault predates Tropo-OS v1.2, install or update.\n'
            f'Path-base / tier-reachability failure — halting rather than silent-skipping, '
            f'per ADR-032 amendment 2026-04-19.'
        )

    if not DRY_RUN:
        # Remove any pre-existing destination to ensure clean copy
        if os.path.exists(vault_dst):
            shutil.rmtree(vault_dst)
        shutil.copytree(skeleton_src, vault_dst)

    # Count what got copied for the log line
    file_count = 0
    for root, _, files in os.walk(skeleton_src):
        file_count += len(files)

    print(f'  .tropo-studio/: skeleton copied from template ({file_count} files)')


def step_8_write_version(build_dir, new_version):
    """Step 4h: Write version.md in the output."""
    dst = os.path.join(build_dir, '.tropo', 'version.md')
    if not DRY_RUN:
        with open(dst, 'w') as f:
            f.write(f"""---
version: "{new_version}"
released: "{datetime.now().strftime('%Y-%m-%d')}"
---

# Tropo-OS v{new_version}

Released {datetime.now().strftime('%Y-%m-%d')}.

See RELEASE-NOTES.md for what changed in this version.
""")
    print(f'  Version file: v{new_version}')


# Version-stamping targets — stranger-facing files that must claim the same
# Tropo-OS version as .tropo/version.md at build time. Prevents the
# stranger-visible drift that v1.3.0 ship surfaced (7+ files declaring 3
# different versions on the same zip).
#
# Each entry: (relative_path_in_build, regex_pattern, replacement_template).
# {version} in the replacement is substituted with the new version at build.
# Patterns target ONLY stranger-facing version-claim sites — NOT historical
# changelog entries, NOT the concierge's own version declarations.
#
# Added 2026-04-22 by Vela V33 as v1.3.1 Stream 1 D1.1 deliverable.
VERSION_STAMP_SITES = [
    ('README.md', r'Tropo-OS v\d+\.\d+\.\d+', 'Tropo-OS v{version}'),
    ('START-TROPO.md', r'Tropo-OS v\d+\.\d+\.\d+', 'Tropo-OS v{version}'),
    ('AGENTS.md', r'tropo_version:\s*"\d+\.\d+\.\d+"', 'tropo_version: "{version}"'),
    ('boards/CAPSULE.md', r'Tropo-OS v\d+\.\d+\.\d+', 'Tropo-OS v{version}'),
    ('operating-agreement.md', r'Tropo-OS v\d+\.\d+\.\d+', 'Tropo-OS v{version}'),
    ('.tropo/TROPO-CONTROL.md', r'tropo_version:\s*"\d+\.\d+\.\d+"', 'tropo_version: "{version}"'),
    ('.tropo/TROPO-CONTROL.md', r'\| Tropo-OS version \| \d+\.\d+\.\d+ \|', '| Tropo-OS version | {version} |'),
    ('.tropo/concierge/activate.md', r'\*Tropo Concierge \| Tropo-OS v\d+\.\d+\.\d+\*', '*Tropo Concierge | Tropo-OS v{version}*'),
]


def step_8b_stamp_versions(build_dir, new_version):
    """Step 4h.5: stamp Tropo-OS version strings across stranger-facing files.

    Enforces version consistency between .tropo/version.md and all other
    version-claim sites. Prevents stranger-visible drift.
    """
    total = 0
    for rel_path, pattern, replacement_tmpl in VERSION_STAMP_SITES:
        path = os.path.join(build_dir, rel_path)
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r') as f:
                text = f.read()
        except Exception:
            continue
        replacement = replacement_tmpl.replace('{version}', new_version)
        new_text, n = re.subn(pattern, replacement, text)
        if n > 0:
            if not DRY_RUN:
                with open(path, 'w') as f:
                    f.write(new_text)
            total += n
            print(f'  Version stamp: {rel_path} — {n} sites -> v{new_version}')
    print(f'  Version stamping: {total} total stamps at v{new_version}')
    return total


def step_9b_regenerate_tropo_nav(build_dir):
    """v1.5 S2 (Truthful Ship): regenerate 00-tropo-nav/ from the SHIPPED ledger.

    Without this step, 00-tropo-nav/ ships as a stale snapshot from whatever
    source-vault state existed when the build started — symlinks point at content
    that may have been retagged out of ship-scope. Mike Maziarz cold-boot of
    v1.4.4 (2026-05-03) caught this directly. v1.5 closes it structurally.

    Two sub-steps:
      9b.1 — Run rebuild-vault.py against the build dir to regenerate
             00-index.jsonl + 00-project-tree.jsonl from the SHIPPED ledger
             (the build's vault/files/ — only entries that survived the scope walker).
      9b.2 — Run rehydrate.py against the freshly-rebuilt build ledger to produce
             00-tropo-nav/ with symlinks pointing at SHIPPED entries only.
    """
    build_nav = os.path.join(build_dir, '00-tropo-nav')
    if os.path.exists(build_nav):
        shutil.rmtree(build_nav)
        print('  Removed pre-existing 00-tropo-nav/ from build dir (will regenerate from shipped ledger)')

    rebuild_path = os.path.join(build_dir, 'vault', 'tools', 'e8d4c1b9.py')  # rebuild-vault (v1.56 migrated)
    rehydrate_path = os.path.join(build_dir, '.tropo', 'scripts', 'rehydrate.py')

    if not os.path.exists(rebuild_path):
        print(f'  ⚠ rebuild-vault.py not found at {rebuild_path} — 00-tropo-nav/ NOT regenerated')
        return
    if not os.path.exists(rehydrate_path):
        print(f'  ⚠ rehydrate.py not found at {rehydrate_path} — 00-tropo-nav/ NOT regenerated')
        return

    if DRY_RUN:
        print(f'  [DRY-RUN] Would regenerate 00-index.jsonl + 00-project-tree.jsonl + 00-tropo-nav/ via build dir tools')
        return

    import subprocess

    # 9b.1: rebuild-vault.py against build dir (writes 00-index.jsonl + 00-project-tree.jsonl
    # from the shipped vault files only — eats our own dogfood for v1.5 S5 ports)
    result = subprocess.run(
        ['python3', rebuild_path, '--apply', '--vault-path', build_dir],
        cwd=build_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f'  ⚠ rebuild-vault.py exited {result.returncode}')
        if result.stderr:
            print(f'    stderr: {result.stderr[:300]}')
        return
    else:
        # Echo a one-line summary
        for line in result.stdout.splitlines():
            if 'Wrote' in line or 'records' in line.lower():
                print(f'    {line.strip()}')

    # 9b.2: rehydrate.py against freshly-rebuilt build ledger
    result = subprocess.run(
        ['python3', rehydrate_path, '00-tropo-nav', '--vault-path', build_dir],
        cwd=build_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f'  ⚠ rehydrate.py exited {result.returncode}')
        if result.stderr:
            print(f'    stderr: {result.stderr[:300]}')
    else:
        # Count what was generated
        nav_root = os.path.join(build_dir, '00-tropo-nav')
        if os.path.exists(nav_root):
            counts = {}
            for sub in ('00-tropo-active', '00-tropo-all', '00-tropo-archived'):
                p = os.path.join(nav_root, sub)
                if os.path.isdir(p):
                    counts[sub] = len(os.listdir(p))
            count_str = ', '.join(f'{k}: {v}' for k, v in counts.items())
            print(f'  Regenerated 00-tropo-nav/ from shipped ledger ({count_str})')


def step_9_generate_manifest(build_dir, new_version):
    """Step 4i: Generate MANIFEST.md with file listing and checksums."""
    manifest_path = os.path.join(build_dir, 'MANIFEST.md')
    if DRY_RUN:
        print(f'  Manifest: [dry run — would generate]')
        return 0

    entries = []
    total_size = 0
    for root, dirs, files in os.walk(build_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, build_dir)
            size = os.path.getsize(fpath)
            checksum = sha256_file(fpath)
            entries.append((rel, size, checksum))
            total_size += size

    entries.sort()

    with open(manifest_path, 'w') as f:
        f.write(f'# Tropo-OS v{new_version} — Build Manifest\n\n')
        f.write(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M")}\n')
        f.write(f'**Files:** {len(entries)}\n')
        f.write(f'**Total size:** {total_size:,} bytes ({total_size / 1024:.1f} KB)\n\n')
        f.write('| Path | Size | SHA-256 |\n')
        f.write('|------|-----:|--------|\n')
        for rel, size, checksum in entries:
            f.write(f'| {rel} | {size:,} | `{checksum[:12]}...` |\n')

    print(f'  Manifest: {len(entries)} files, {total_size:,} bytes total')
    return len(entries)


def step_10_sanitize_argo_identity(build_dir):
    print('Step 10 — Sanitize the Studio Identity')
    # v1.71 (argus-a114, Mike-authorized 2026-06-16): GENERICIZE the public artifact instead of
    # refusing. The Argo source legitimately references "the Studio" (it IS the Studio — the
    # governance hub, dev-pipeline, capsules correctly describe it); the public template must not.
    # So strip Argo identity from the COPIED build files (source untouched), then VERIFY none
    # remain (fail-closed). Prior behavior refused on legitimate source content that had already
    # shipped in v1.70 — this makes the build self-healing instead of a hard wall.
    _skip = ('.png', '.jpg', '.jpeg', '.gif', '.zip', '.sqlite', '.DS_Store')
    replacements = [
        (re.compile(r'the development dogfood', re.I), 'the development dogfood'),
        (re.compile(r'development dogfood', re.I), 'development dogfood'),
        (re.compile(r'the Studio', re.I), 'the Studio'),
        (re.compile(r'the Studio', re.I), 'the Studio'),
    ]
    sanitized = 0
    for root, _, files in os.walk(build_dir):
        for f in files:
            if f.endswith(_skip):
                continue
            path = os.path.join(root, f)
            try:
                content = Path(path).read_text(encoding='utf-8')
            except Exception:
                continue
            new = content
            for pat, repl in replacements:
                new = pat.sub(repl, new)
            if new != content:
                Path(path).write_text(new, encoding='utf-8')
                sanitized += 1

    argo_isms = ['the Studio', 'the development dogfood']
    findings = []
    for root, _, files in os.walk(build_dir):
        for f in files:
            if f.endswith(_skip):
                continue
            path = os.path.join(root, f)
            rel_path = os.path.relpath(path, build_dir)
            try:
                content = Path(path).read_text(encoding='utf-8').lower()
            except Exception:
                continue
            for ism in argo_isms:
                if ism in content:
                    findings.append(f"{rel_path}: still contains '{ism}'")

    if findings:
        print('  ✗ Build REFUSED — Argo-isms remain after genericization (fail-closed):')
        for f in findings:
            print(f'    - {f}')
        sys.exit(1)
    print(f'  ✓ Build sanitized — genericized {sanitized} artifact file(s); no Argo-isms remain.')


def step_11_zip_and_upload(build_dir, new_version, dist_dir, dry_run=False, allow_upload=True):
    print('Step 11 — Zip and Upload to Supabase')
    if dry_run:
        print('  --dry-run: skipping zip and upload')
        return

    import urllib.request
    zip_path_base = os.path.join(dist_dir, f"tropo-os-v{new_version}")
    shutil.make_archive(zip_path_base, 'zip', build_dir)
    zip_file = f"{zip_path_base}.zip"
    print(f'  ✓ Zipped to {zip_file}')

    # Public-ship gate (dev-spec 2ffdd9d6 AC-4): the upload is the one irreversible,
    # outward-facing act. It requires the human key (a human_signoff event in the run),
    # checked by the caller. Without it: local zip only, no public deploy.
    if not allow_upload:
        print('  ⚠ Public ship NOT authorized (no human signoff in the run) — '
              'local zip only, skipping upload.')
        return

    supabase_url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_SECRET_KEY')

    if not supabase_url or not supabase_key:
        # tropo-ai is a SIBLING of the Studio at the dev-root, so resolve via dirname(PLATFORM_ROOT)
        # — mirrors RELEASES_DIR's correct sibling-resolution. (Fixed argus-a115 2026-06-17,
        # Mike-A115 approved: the prior PLATFORM_ROOT/tropo-ai path was one level too shallow and
        # never resolved, silently skipping every upload.)
        env_file = os.path.join(os.path.dirname(PLATFORM_ROOT), 'tropo-ai', '.env.local')
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('NEXT_PUBLIC_SUPABASE_URL='):
                        supabase_url = line.strip().split('=', 1)[1]
                    elif line.startswith('SUPABASE_SECRET_KEY='):
                        supabase_key = line.strip().split('=', 1)[1]

    if not supabase_url or not supabase_key:
        print('  ⚠ Supabase credentials not found. Skipping upload.')
        return

    print('  Uploading to Supabase...')
    with open(zip_file, 'rb') as f:
        data = f.read()

    upload_url = f"{supabase_url}/storage/v1/object/releases/v{new_version}/tropo-os-v{new_version}.zip"
    
    req = urllib.request.Request(upload_url, data=data, method='POST')
    # New-format Supabase keys (sb_secret_…) are NOT JWTs — they authenticate via the `apikey`
    # header. Sending one as `Authorization: Bearer` makes the gateway JWT-parse it → "Invalid
    # Compact JWS". (Fixed argus-a115 2026-06-17, Mike-approved: publish env migrated to new keys.)
    req.add_header('apikey', supabase_key)
    req.add_header('Authorization', f'Bearer {supabase_key}')
    req.add_header('Content-Type', 'application/zip')
    req.add_header('x-upsert', 'true')  # allow overwrite (re-ship) — Supabase POST 400s on duplicate otherwise

    try:
        response = urllib.request.urlopen(req)
        if response.status in (200, 201):
            print(f'  ✓ Uploaded to Supabase releases/v{new_version}/')
        else:
            print(f'  ✗ Supabase upload failed: HTTP {response.status}')
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode('utf-8', 'replace')[:600]
        except Exception:
            pass
        print(f'  ✗ Supabase upload failed: HTTP {e.code} - {e.reason} :: {body}')
    except Exception as e:
        print(f'  ✗ Supabase upload failed: {e}')


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    # Parse args
    bump_type = None
    target_version = None
    activation_uid = None
    for i, arg in enumerate(sys.argv):
        if arg == '--bump' and i + 1 < len(sys.argv):
            bump_type = sys.argv[i + 1]
        elif arg == '--target' and i + 1 < len(sys.argv):
            target_version = sys.argv[i + 1]
        elif arg == '--activation-uid' and i + 1 < len(sys.argv):
            activation_uid = sys.argv[i + 1]

    if not bump_type and not target_version:
        print('Usage: python3 build-release.py (--bump <patch|feature|release> | --target <X.Y.Z>) [--dry-run] [--force]')
        print('')
        print('  --bump <type>      Compute target version from current .tropo/version.md + bump type.')
        print('  --target <X.Y.Z>   Build a specific version explicitly. Use when ship + on-disk-build')
        print('                     split across sessions and .tropo/version.md is already at the target')
        print('                     (vela-v46 2026-05-16 addition per Mike-V46 captain-mode authorization;')
        print('                     fixes the v1.34.0 packaging gap where Argus updates version.md at')
        print('                     substrate ship but --bump expects source to LAG one cycle behind build).')
        sys.exit(1)

    if bump_type and bump_type not in ('patch', 'feature', 'release'):
        print(f'Invalid bump type: {bump_type}. Must be patch, feature, or release.')
        sys.exit(1)

    if target_version and not re.match(r'^\d+\.\d+\.\d+$', target_version):
        print(f'Invalid --target version: {target_version}. Must match X.Y.Z (semver).')
        sys.exit(1)

    if bump_type and target_version:
        print(f'ERROR: --bump and --target are mutually exclusive. Pick one.')
        sys.exit(1)

    print(f'=== Tropo-OS Build {"[DRY RUN]" if DRY_RUN else ""} ===\n')

    # ── Pipeline Activation Key gate (dev-spec 2ffdd9d6) ──────────────────────
    # A real build refuses without a runtime-minted key proving this release went
    # through the pipeline (activation + doc/test cascade + gates). Fail-closed.
    # No break-glass: --force does NOT bypass this (it only overwrites a stale dir).
    # --dry-run is exempt (it produces no artifact).
    if not DRY_RUN:
        try:
            _key = require_release_authorization(activation_uid, 'produce-release-folder')
            print(f'  ✓ Pipeline Activation Key verified (activation {activation_uid}, '
                  f'fingerprint {_key.get("fingerprint","")[:12]}…)\n')
        except ReleaseAuthorizationError as e:
            print(f'  ✗ Build REFUSED — no valid Pipeline Activation Key: {e}', file=sys.stderr)
            print('    A release is produced through the pipeline runtime, which mints the key', file=sys.stderr)
            print('    at the produce-release-folder gate. Drive the cycle via pipeline-runtime.py —', file=sys.stderr)
            print('    do not invoke build-release standalone. (No key, no build.)', file=sys.stderr)
            sys.exit(3)

    # =====================================================================
    # Pre-flight: Vault rebuild — ALWAYS-RUN (hoisted from Step 0c at v1.41.0
    # Stream C; first authored captain-mode by Vela V47 2026-05-18 during
    # v1.40.0 build-incident response; formalized under v1.41.0 cycle ceremony
    # by Argus A71 2026-05-18 per brief 800c3352 Stream C)
    # =====================================================================
    # Per Mike-V47 directive 2026-05-18 after v1.40.0 build excluded the
    # canonical doctrine entry 0aefe71d because the index hadn't been rebuilt
    # after Argus authored it. Vault index currency is substrate-quality, not
    # enforcement — it MUST run unconditionally before the enforcement gate
    # so the build manifest sees the current vault state. The previous v1.30.0
    # design gated Step 0c inside TROPO_SKIP_ENFORCEMENT_GATE=1, which created
    # the silent-stale-index defect. Halt-mode failure locked per Mike-A71
    # 2026-05-18 R1 Locked Decision LD-3 (brief 800c3352).
    print('Step 0 — Vault rebuild (always-run; substrate currency pre-flight):')
    rebuild_path = os.path.join(VAULT_ROOT, 'vault', 'tools', 'e8d4c1b9.py')  # rebuild-vault (v1.56 migrated)
    try:
        rebuild_result = subprocess.run(
            ['python3', rebuild_path, '--vault-path', VAULT_ROOT, '--apply'],
            capture_output=True, text=True, cwd=VAULT_ROOT, timeout=300
        )
    except subprocess.TimeoutExpired:
        print('  ✗ Substrate rebuild timed out after 300s. Investigate vault size or rebuild regression.')
        sys.exit(2)
    except FileNotFoundError:
        print(f'  ✗ rebuild-vault.py not found at {rebuild_path}. v1.30.0 substrate missing.')
        sys.exit(2)

    if rebuild_result.returncode != 0:
        tail = '\n'.join(rebuild_result.stdout.splitlines()[-30:])
        print(tail)
        print('\n  ✗ Build REFUSED — rebuild-vault.py returned non-zero (validator FAIL or rebuild FAIL).')
        print('    Vault rebuild is always-run; this failure is NOT bypassable via')
        print('    TROPO_SKIP_ENFORCEMENT_GATE=1 (substrate quality is separate from')
        print('    capability-membership enforcement).')
        print('    Recovery paths depend on the failure class:')
        print('      - Validator FAIL on duplicate top-level YAML keys → run:')
        print('          python3 .tropo/scripts/fix-duplicate-yaml-keys.py --dry-run')
        print('          python3 .tropo/scripts/fix-duplicate-yaml-keys.py --apply [--allow-dirty]')
        print('      - Validator FAIL on other check classes → fix the violations surfaced above.')
        print('      - Rebuild FAIL → investigate substrate state; fix the rebuild-blocking defect.')
        sys.exit(1)

    summary = '\n'.join(rebuild_result.stdout.splitlines()[-10:])
    print('  ' + summary.replace('\n', '\n  '))
    print('  ✓ Vault rebuild PASS\n')

    # Step 1 (was Step 0 pre-v1.41.0 Stream C — v1.10 Pure Enforcement gate — Argus A50 + Mike pair-design 2026-05-07):
    # Run validate-capability-membership.py in STRICT mode before building.
    # Build refuses if any ERROR (Rule 11 + Rule 12 + structural-consistency +
    # Checks 19-23). Pre-v1.40 cycles grandfathered (v1.50.0 threshold extension
    # per Mike-A79 substrate-honesty walk 2026-05-22; rationale in validator
    # source). Cycle's own substrate gets exercised at this gate — v1.40 + later
    # cycles' release entries + release plans pass through hardened validator
    # before B6 atomic-triangle ship.
    #
    # TROPO_SKIP_ENFORCEMENT_GATE=1 — RETIRED FOR ROUTINE USE POST-v1.50.0.
    # Mike-V50 Path B directive 2026-05-22: v1.49 ships clean (no bypass) or v1.49
    # doesn't ship. Pattern-break locked at substrate level by Argus A79 v1.50.0
    # registry primitive establishment (registry.capsule + Registries hub + 5
    # wrapper entries + subsystem-registry.jsonl populated + rebuild-vault.py
    # auto-derives going-forward via derive-subsystem-registry.py).
    #
    # Bypass remains as TRUE EMERGENCY mechanism only — disaster recovery if
    # registry corrupts, vault index broken, validator regression discovered
    # mid-ship. Routine ship invoking the bypass is a substrate-discipline
    # violation; should be surfaced to Mike as substrate-coherence finding.
    # See v1.50.0 priority elevation brief [08e4a7c2] for full pattern history.
    if os.environ.get('TROPO_SKIP_ENFORCEMENT_GATE') != '1':
        print('Step 1 — v1.10 Pure Enforcement gate (validate-capability-membership.py STRICT mode):')
        # v1.56 Lane S captain-mode fix-on-see (Vela V54 2026-05-27):
        # validate-capability-membership.py migrated to vault/tools/f5e2d1c7.py;
        # legacy .tropo/scripts/ path no longer exists. Use canonical vault/tools/ path.
        validator_path = os.path.join(VAULT_ROOT, 'vault', 'tools',
                                      'f5e2d1c7.py')
        try:
            result = subprocess.run(
                ['python3', validator_path],
                capture_output=True, text=True, cwd=VAULT_ROOT, timeout=300
            )
        except subprocess.TimeoutExpired:
            print('  ✗ Validator timed out after 300s. Investigate vault size or validator regression.')
            sys.exit(2)
        except FileNotFoundError:
            print(f'  ✗ Validator not found at {validator_path}. v1.10 substrate missing.')
            sys.exit(2)

        if result.returncode != 0:
            # Print summary + last lines (full output likely large)
            tail = '\n'.join(result.stdout.splitlines()[-25:])
            print(tail)
            print('\n  ✗ Build REFUSED — validator returned ERROR(s) in STRICT mode.')
            print('    Fix the violations above (Rule 11 / Rule 12 / structural-consistency /')
            print('    Checks 19-23 / capability hub-membership) and re-run build.')
            print('    Bypass (emergency only): TROPO_SKIP_ENFORCEMENT_GATE=1 python3 ' + sys.argv[0] + ' ...')
            sys.exit(1)
        # Print just the summary tail on success
        summary = '\n'.join(result.stdout.splitlines()[-5:])
        print('  ' + summary.replace('\n', '\n  '))
        print('  ✓ Pre-build enforcement gate PASS (0 ERRORs)\n')

        # NOTE: original Step 0c (substrate-rebuild gate, v1.30.0) was hoisted
        # out of this conditional at v1.40.1 per Mike-V47 directive 2026-05-18
        # and is now Step 0 (always-run; see above). The hoisting fixes the
        # silent-stale-index defect that surfaced at v1.40.0 build when
        # TROPO_SKIP_ENFORCEMENT_GATE=1 also bypassed the rebuild — letting
        # the canonical doctrine entry 0aefe71d ship-fail because the index
        # hadn't been rebuilt after Argus authored it.
    else:
        print('Step 1 — v1.10 enforcement gate BYPASSED (TROPO_SKIP_ENFORCEMENT_GATE=1).')
        print('  ⚠ Emergency-only bypass; capability-membership Rule 11/12 enforcement skipped.')
        print('    Vault rebuild already ran at Step 0 (always-run pre-flight; not bypassable).')
        print('    Canonical L0 verification still runs at Step 1b (always-run; not bypassable since v1.46.0.1).\n')

    # Step 1b — v1.13.5 Canonical L0 verification (validate-canonical-l0.py)
    # v1.46.0.1 discipline patch (Argus A76 2026-05-20 per Vela V48 catch + Mike-A76 directive):
    # HOISTED OUT of the `if not bypass:` branch so canonical-L0 verification always
    # runs regardless of TROPO_SKIP_ENFORCEMENT_GATE. Validator-as-discipline pattern
    # ensures the bypass-as-standard pattern can never silence this class again.
    # Same hoist shape v1.40.1 applied to Step 0c (vault rebuild). Catches L0 drift
    # caused by speculative reparenting or backfill scripts that mutate member_of:
    # arrays without preserving true-L0 status. Validates against active state only;
    # archived L0 cleanup is a separate carry-forward. v1.14 schema split (v1.47.0
    # candidate) will eliminate the underlying ambiguity that makes this check necessary.
    print('Step 1b — v1.13.5 Canonical L0 verification (validate-canonical-l0.py; always-run since v1.46.0.1):')
    # v1.56 Lane S captain-mode fix-on-see (Vela V54 2026-05-27):
    # validate-canonical-l0.py migrated to vault/tools/e3f5a8c1.py.
    l0_validator_path = os.path.join(VAULT_ROOT, 'vault', 'tools',
                                     'e3f5a8c1.py')
    try:
        l0_result = subprocess.run(
            ['python3', l0_validator_path, '--state', 'active'],
            capture_output=True, text=True, cwd=VAULT_ROOT, timeout=30
        )
    except subprocess.TimeoutExpired:
        print('  ⚠ L0 validator timed out after 30s. Continuing build (non-blocking warning).')
        l0_result = None
    except FileNotFoundError:
        print(f'  ⚠ L0 validator not found at {l0_validator_path}. Continuing build (non-blocking warning).')
        l0_result = None

    if l0_result is not None:
        if l0_result.returncode == 0:
            print('  ✓ Canonical L0 verification PASS (rendered active L0 set matches canonical).\n')
        elif l0_result.returncode == 1:
            tail = '\n'.join(l0_result.stdout.splitlines()[-15:])
            print(tail)
            print('\n  ✗ Build REFUSED — rendered L0 set does not match canonical declaration.')
            print('    Either fix the project member_of: edges so the rendered L0 set matches')
            print('    .tropo-studio/registries/canonical-l0-projects.yaml, OR amend the registry')
            print('    with Mike approval if the canonical L0 set has legitimately changed.')
            print('    NOTE: this check is NOT bypassable since v1.46.0.1 (Argus + Vela catch 2026-05-20).')
            print('    Substrate-fix scope: v1.14 schema split (v1.47.0 candidate per Captain\'s Read v2.0).')
            sys.exit(1)
        else:
            print(f'  ⚠ L0 validator setup error (exit {l0_result.returncode}). Continuing build.')
            if l0_result.stderr:
                print('    ' + l0_result.stderr.strip().replace('\n', '\n    '))
            print()

    # Step 1c — v1.59 Lane B: cascade-pipelines-retired check (V3 pre-flip gate)
    # Refuses build if triggered doc/test pipeline activations are not status:retired.
    # Composes with v1.51 three-pipeline coupling enforcement; structural fix for
    # 3-cycle-recurring R11+R12 substrate-population-residue defect class.
    try:
        _scripts_lib = Path(VAULT_ROOT) / '.tropo' / 'scripts'
        import sys as _sys
        if str(_scripts_lib) not in _sys.path:
            _sys.path.insert(0, str(_scripts_lib))
        from lib.release_validators import check_cascade_pipelines_retired
        # Find the active dev-spec for this activation (from dev-spec index or env)
        _dev_spec_uid = os.environ.get('DEV_SPEC_UID', '')
        if _dev_spec_uid and re.match(r'^[0-9a-f]{8}$', _dev_spec_uid):
            print('Step 1c — v1.59 Lane B: cascade-pipelines-retired gate:')
            _casc_findings, _all_retired = check_cascade_pipelines_retired(
                Path(VAULT_ROOT), _dev_spec_uid
            )
            if _casc_findings:
                for _f in _casc_findings:
                    print(_f)
            if not _all_retired:
                print('\n  ✗ Build REFUSED — cascade pipelines not retired. '
                      'Close doc-pipeline + test-pipeline activations before ship-flip.')
                print('    Bypass: unset DEV_SPEC_UID (disables this check; emergency only).')
                sys.exit(1)
            else:
                if _casc_findings:
                    print('  ⚠ Cascade check complete with warnings (non-blocking).')
                else:
                    print('  ✓ All cascade pipelines retired — ship-flip gate PASS.')
        else:
            print('Step 1c — v1.59 Lane B: cascade-pipelines-retired gate: '
                  'SKIPPED (set DEV_SPEC_UID=<uid> to enable).')
    except Exception as _e:
        print(f'Step 1c — cascade gate skipped ({_e}; non-blocking).')

    # Step 1: Version
    if target_version:
        current = read_current_version(VERSION_PATH)
        new_version = target_version
        print(f'  Version: {current} → {new_version} (--target override; bump skipped)')
    else:
        current, new_version = step_1_compute_version(bump_type)

    # Step 2: Output directory
    build_dir, testing_dir, dist_dir = step_2_create_output(new_version)

    # Load ship entries from index
    entries = load_ship_entries(INDEX_PATH)
    print(f'  Scope:ship entries: {len(entries)}')
    print()

    # Step 3: Copy kernel
    print('Phase 2 — Mechanical Build:')

    # Step 3a: Regenerate capability catalogs (Orpheus finding e4c2f9a1; run BEFORE kernel copy)
    step_3a_regenerate_catalogs()

    kernel_count = step_3_copy_kernel(build_dir)

    # Step 3b: Copy vault/tools/ wholesale (scripting layer targets — ruling fdef56ea)
    step_3b_copy_vault_tools(build_dir)

    # Step 3d: Copy vault/playbooks/ wholesale (playbook targets — finding b1f9c3d2)
    step_3d_copy_vault_playbooks(build_dir)

    # Step 3c: Assert every shim's forward-target is present in build (ruling fdef56ea)
    step_3c_assert_forward_targets(build_dir)

    # Step 4: Copy ship entries
    entry_count, missing, index_rows = step_4_copy_ship_entries(build_dir, entries)

    # Phase 0 + 1 + 3 — MVP Phase E manifest-driven build (v1.12.1).
    # Replaces legacy step_5_copy_root_files + step_5b_copy_starter_vault_files +
    # step_6_create_skeleton. Per locked Build-Release Pipeline arch-spec
    # (UID 747c33c9) consuming ship-artifact.capsule v1.1.4 (UID eeb59ddf).
    print()
    manifest_entries = step_phase0_bootstrap()

    print()
    print('Phase 1 (basic) — Validate Manifest:')
    validate_manifest_basic(manifest_entries, VAULT_ROOT)

    print()
    print('Phase 3 — Build Output (manifest-driven):')
    build_from_manifest(build_dir, manifest_entries)

    # v1.12.1 transitional: RELEASE-NOTES.md is a generated artifact, not a
    # ship-artifact (per arch-spec 747c33c9 §1 Thesis "RELEASE-NOTES is generated
    # per release"). Lives at argo-os/RELEASE-NOTES.md (relocated from
    # argo-os/starter/RELEASE-NOTES.md at v1.12.1 ship). Copy to build root.
    # v1.12.2 implements proper RELEASE-NOTES.md generation step OR authors a
    # ship-artifact entry with explicit generated-artifact handling.
    rn_src = os.path.join(VAULT_ROOT, 'RELEASE-NOTES.md')
    if os.path.exists(rn_src):
        rn_dst = os.path.join(build_dir, 'RELEASE-NOTES.md')
        copy_file(rn_src, rn_dst, DRY_RUN)
        print(f'  RELEASE-NOTES.md: copied from argo-os/RELEASE-NOTES.md to build root')
    else:
        print(f'  ⚠ RELEASE-NOTES.md not found at {rn_src} — release ships without notes')

    # Step 7: .tropo-studio/ skeleton
    step_7_create_vault_skeleton(build_dir)

    # Step 8: Version file
    step_8_write_version(build_dir, new_version)

    # Step 8b: Version stamping across stranger-facing files (v1.3.1 D1.1)
    step_8b_stamp_versions(build_dir, new_version)

    # Step 9: Manifest
    file_count = step_9_generate_manifest(build_dir, new_version)

    # Step 9b: Regenerate 00-tropo-nav/ from the SHIPPED ledger (v1.5 S2)
    # Ensures shipped 00-tropo-nav reflects the SHIPPED ledger, not the source-vault state.
    # Closes Mike Maziarz cold-boot finding 2026-05-03 ("you did ship a 00-tropo-nav/ that was stale").
    step_9b_regenerate_tropo_nav(build_dir)

    # Step 10: Sanitize the Studio identity
    step_10_sanitize_argo_identity(build_dir)

    # Step 10.5: Release Test-Harness — mechanical regression GATE (new layer; brief f13cc214,
    # Mike-A115 2026-06-17). A release that fails its own regression does NOT ship. Runs the
    # self-contained harness against the produced+sanitized artifact; FAIL → refuse (no zip,
    # no upload). Composes with the Pipeline Activation Key: a release that can't pass its own
    # checks can't be shipped. (Mechanical layer only — the guided/stranger walk is dispatched
    # by the reasoning layer / run by a human; this is the deterministic gate.)
    if not DRY_RUN:
        print('Step 10.5 — Release Test-Harness (mechanical regression gate):')
        _harness = os.path.join(VAULT_ROOT, '.tropo', 'scripts', 'test-harness-check.py')
        if not os.path.exists(_harness):
            print(f'  ⚠ Test-harness not found at {_harness} — gate SKIPPED (surface this; do not treat as pass).')
        else:
            try:
                _hr = subprocess.run(['python3', _harness, '--release-dir', build_dir],
                                     capture_output=True, text=True, cwd=VAULT_ROOT, timeout=120)
                print('  ' + (_hr.stdout or '').strip().replace('\n', '\n  '))
                if _hr.returncode != 0:
                    print('\n  ✗ Build REFUSED — release failed its own test-harness regression.', file=sys.stderr)
                    print(f'    A release that cannot pass its own checks does not ship. See test-report.md in', file=sys.stderr)
                    print(f'    {build_dir} — fix the failures and re-run.', file=sys.stderr)
                    sys.exit(4)
                print('  ✓ Test-harness regression PASS\n')
            except subprocess.TimeoutExpired:
                print('  ✗ Test-harness timed out after 120s. Investigate.', file=sys.stderr)
                sys.exit(4)

    # Step 11: Zip and Upload — public ship requires the human key (dev-spec 2ffdd9d6 AC-4)
    _ship_ok = False
    if not DRY_RUN:
        try:
            require_release_authorization(activation_uid, 'produce-release-folder',
                                          require_human_signoff=True)
            _ship_ok = True
        except ReleaseAuthorizationError as e:
            print(f'  ⚠ Public ship gate: {e}')
    step_11_zip_and_upload(build_dir, new_version, dist_dir, DRY_RUN, allow_upload=_ship_ok)

    # Copy build to testing directory
    if not DRY_RUN:
        if os.path.exists(testing_dir):
            shutil.rmtree(testing_dir)
        shutil.copytree(build_dir, testing_dir, symlinks=True)

    # C.6 — Stream C auto-emission: tropo.release.shipped (v1.58)
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("ca90f098", str(Path(VAULT_ROOT) / "vault" / "tools" / "ca90f098.py"))
        _em = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_em)
        _em.emit("tropo.release.shipped", "/tools/build-release", "123e12e7",
                 lifecycle="evergreen",
                 data={"version": new_version, "build_dir": str(build_dir)})
    except Exception:
        pass

    print(f'\n=== Build Complete ===')
    print(f'  Version: {new_version}')
    print(f'  Build: {build_dir}')
    print(f'  Testing: {testing_dir}')
    if missing > 0:
        print(f'  ⚠ {missing} entries referenced in index but file not found')
    print(f'\nNext steps (reasoning layer — agent executes):')
    print(f'  1. Run cold-boot-test.playbook.md against {testing_dir}')
    print(f'     (artifact self-sufficiency testing — Argus-lane R1 verification primitive)')
    print(f'  2. Run release-cold-boot-walk.playbook.md (Vela release-step; Mike-conditional)')
    print(f'     Ask Mike first — he may skip for simple releases (manual test-Studio setup required).')
    print(f'     Three-persona stranger-walk against a test-Studio outside the repo (engineer / operator / enterprise).')
    print(f'     Ship-gate parallel to vela-test-plan; aggregate report lands at releases/v{new_version}/cold-boot-walk-report.md')
    print(f'  3. Generate RELEASE-NOTES.md')
    print(f'  4. Update source vault version to {new_version}')


if __name__ == '__main__':
    main()
