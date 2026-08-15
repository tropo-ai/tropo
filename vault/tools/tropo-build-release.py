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
cli_command: python3 vault/tools/tropo-build-release.py --bump <patch|feature|release> [--dry-run] [--force]
script_path: vault/tools/tropo-build-release.py
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
- 8dd772a0
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
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import yaml  # vendor-ref manifest generation (S1, v1.80 re-build) — AST-walk frontmatter


def _load_tropo_roots():
    """Load the production-owned roots module outside either ``lib`` package."""
    roots_path = Path(__file__).resolve().with_name("lib") / "tropo_roots.py"
    spec = importlib.util.spec_from_file_location("_tropo_tools_roots", roots_path)
    if spec is None or spec.loader is None:
        raise ImportError("tropo_roots helper could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tropo_roots = _load_tropo_roots()

# ─── lib/ship_extract/ engine (v1.43.0 Stream C — substrate UID c47b9d82) ───
# Adds the scripts directory to sys.path so `from lib.ship_extract import ...` resolves
# regardless of how build-release.py is invoked (cwd-independent).
# v1.56 Lane S: script relocated to vault/tools/; lib/ imports from .tropo/scripts/
_SCRIPTS_DIR = str(tropo_roots.STUDIO_ROOT / '.tropo' / 'scripts')
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from lib.ship_extract import (
    read_manifest_root_uid as _engine_read_manifest_root_uid,
    load_manifest_entries as _engine_load_manifest_entries,
    resolve_source_path as _engine_resolve_source_path,
    should_exclude_kernel as _engine_should_exclude_kernel,
    is_generated_bytecode,
    prune_bytecode,
    validate_manifest_basic as _engine_validate_manifest_basic,
    sha256_file as _engine_sha256_file,
    copy_file as _engine_copy_file,
)
# Pipeline Activation Key gate (dev-spec 2ffdd9d6, brief f8cda3dd) — build + ship
# refuse without a runtime-minted, unforgeable fingerprint of a legitimate pipeline-run.
from lib.release_authorization import require_release_authorization, ReleaseAuthorizationError, attested_build_authorization

# Per-studio state exclusion (velocity item 8). Loaded by path from
# vault/tools/lib/ rather than the .tropo/scripts/lib namespace imported above,
# because those are two different `lib` packages and this rule belongs with the
# vault tooling that also consumes it.
import importlib.util as _psx_util
_psx_spec = _psx_util.spec_from_file_location(
    "tropo_package_state_exclusions",
    Path(__file__).resolve().with_name("lib") / "package_state_exclusions.py",
)
if _psx_spec is None or _psx_spec.loader is None:
    raise ImportError("package_state_exclusions helper could not be loaded")
package_state_exclusions = _psx_util.module_from_spec(_psx_spec)
_psx_spec.loader.exec_module(package_state_exclusions)


def _load_vault_lib(module_name, file_name):
    """Load a vault/tools/lib module by path.

    Same reason package_state_exclusions is loaded this way: `lib` above is
    `.tropo/scripts/lib`, a different package. Importing `lib.release_package`
    would silently resolve to the wrong namespace or fail, depending on path
    order, which is worse than being explicit.
    """
    spec = _psx_util.spec_from_file_location(
        module_name, Path(__file__).resolve().with_name("lib") / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"{file_name} could not be loaded")
    module = _psx_util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Stage-6 AC6-final: package-entry authority and the release-leg wait. Both are
# consulted before the zip exists.
#: This script's own registered identity. package_frozen is authored by the
#: TOOL, not by whichever executive invoked it (A148 blocker 2).
BUILD_TOOL_UID = "a1b8c2d4"
BUILD_TOOL_SOURCE = "/tools/build-release"

release_package = _load_vault_lib("tropo_release_package", "release_package.py")
release_legs = _load_vault_lib("tropo_release_legs", "release_legs.py")

# ─── Configuration ───────────────────────────────────────────────────────────

INDEX_PATH = os.path.join(tropo_roots.VAULT_DIR, '00-index.jsonl')
VERSION_PATH = os.path.join(tropo_roots.STUDIO_ROOT, '.tropo', 'version.md')
# RELEASES_DIR sits OUTSIDE the platform repo entirely — releases are product artifacts,
# not source-repo content. Convention: sibling to the platform repo at <dev-root>/tropo-releases/.
# Path migration history: argo-os/releases/ → tropo-ai/releases/ (2026-05-11 partial move) →
# /tropo-releases/ (2026-05-18 outside-repo final per Mike-V47 directive — eliminates copy step
# for release-cold-boot-walk + clean separation of source vs product artifact).

# Directories and files copied by convention (not through the Vault)
KERNEL_DIR = os.path.join(tropo_roots.STUDIO_ROOT, '.tropo')

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

SHIP_ARTIFACT_CAPSULE_PATH = os.path.join(tropo_roots.VAULT_DIR, 'capsules', 'tropo-ship-artifact.capsule.md')  # ADR-045: moved from .tropo/capsules/ (v1.21.0)

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
    'boot-digest.md',                        # v1.74: excluded from ship, per-studio derivation only
    'boot-fast-path.md',                     # v1.74: excluded from ship, per-studio derivation only
    'event-streams-v2.enabled',              # v1.86 punch-list item 6 (51dc85ef), talos-t40 2026-08-08.
                                              # Argo's v2-cutover marker, and shipping it BLOCKS the box.
                                              # load_cutover_marker treats presence as an authenticated
                                              # local contract: it demands three evidence UIDs that are
                                              # hardcoded to Argo entries (f15a9b85, 5a195c76, de9ac53c),
                                              # none of which ship, so verification fails and EVERY v2
                                              # emit refuses crew-wide. It also leaks Argo's baseline
                                              # commit and a 6,678-row ledger count into the customer box.
                                              # Absence is the designed state, not a gap: the loader
                                              # returns None ("legacy mode") and the validator prints
                                              # "pre-cutover studio". Shipping nothing lets the box emit;
                                              # shipping the marker, or a disabled one, does not —
                                              # `enabled` must be exactly True or the loader raises, so
                                              # there is no such thing as a ship-disabled marker.
                                              # A future release ships a properly box-derived cutover.
                                              # Same shape as the two entries below.
    'studio-identity.md',                    # Release Coupling (fbe50871), routed via Metis F-2
                                              # (event 00006331): the moment argo-os mints its own
                                              # identity (mint-id.py --kind studio), a box shipping
                                              # this file ships OUR identity — customer genesis
                                              # becomes a silent no-op (mint is idempotent by design).
                                              # A trap, not yet a live defect (argo-os has not run
                                              # --kind studio as of this fix).
]

DRY_RUN = '--dry-run' in sys.argv
FORCE = '--force' in sys.argv   # added 2026-05-01 (vela-v37, Stream 2 task 87e3b4d6) — bypasses overwrite guard
OFFLINE = '--offline' in sys.argv   # Release Coupling (fbe50871): pre-flight carve-out — an
                                    # internal build must never be hostage to a GitHub outage.


# ─── Publish-State Pre-Flight (Release Coupling, fbe50871, Step 0.5) ────────

def step_0_5_publish_state_preflight():
    """Step 0.5 — publish-state pre-flight (Release Coupling, fbe50871).

    Discriminates, offline-safe:
      - internal-ahead (the normal case — we're about to build the next version):
        INFO, proceed.
      - remote-ahead anomaly (something is published that this studio doesn't know
        about): refuse, naming it — this is not a normal state to build over.
      - unreachable: refuse UNLESS --offline, in which case proceed with
        publish_state recorded UNKNOWN in build provenance (never silently
        'assume in sync' — the honesty is in the recorded value, not the refusal).
      - broken/missing version.md: exit 2, never treated as 'drift' (a version we
        can't even read is not comparable to anything).
      - in-sync: INFO, proceed (this build is re-producing an already-published
        version — legitimate for --target retries).

    Returns a dict {"publish_state": ..., ...} recorded into build provenance;
    never raises — either returns normally (proceed) or calls sys.exit itself.
    """
    print('Step 0.5 — Publish-state pre-flight:')
    checker = os.path.join(tropo_roots.VAULT_DIR, 'tools', 'tropo-check-publish-state.py')
    if not os.path.exists(checker):
        print(f'  ⚠ {checker} not found — pre-flight skipped (non-blocking; tool missing).')
        return {"publish_state": "UNKNOWN", "reason": "checker tool not found"}
    try:
        result = subprocess.run(['python3', checker, '--json'],
                                 capture_output=True, text=True, timeout=30)
        state = json.loads(result.stdout)
    except Exception as e:
        print(f'  ⚠ Could not run/parse check-publish-state: {e}')
        if not OFFLINE:
            print('  ✗ Build REFUSED — publish-state pre-flight failed and --offline not passed.',
                  file=sys.stderr)
            print('    Pass --offline to proceed anyway (recorded honestly as UNKNOWN).',
                  file=sys.stderr)
            sys.exit(2)
        print('  --offline: proceeding, publish_state recorded UNKNOWN.')
        return {"publish_state": "UNKNOWN", "reason": str(e)}

    status = state.get("status")
    if status == "unknown_version":
        print('  ✗ Build REFUSED — .tropo/version.md is missing or unparseable.', file=sys.stderr)
        print('    This is never treated as drift — fix version.md, then re-run.', file=sys.stderr)
        sys.exit(2)
    if status == "unreachable":
        if not OFFLINE:
            print(f'  ✗ Build REFUSED — could not reach the publish-state remote: '
                  f'{state.get("error", "")[:200]}', file=sys.stderr)
            print('    Pass --offline to proceed anyway (recorded honestly as UNKNOWN).',
                  file=sys.stderr)
            sys.exit(2)
        print(f'  --offline: remote unreachable ({state.get("error", "")[:150]}), '
              f'proceeding with publish_state recorded UNKNOWN.')
        return {"publish_state": "UNKNOWN", "reason": state.get("error")}
    if status == "remote_ahead_anomaly":
        print(f'  ✗ Build REFUSED — ANOMALY: published v{state.get("latest_published")} is AHEAD of '
              f'internal v{state.get("internal_version")}. Investigate before building over this.',
              file=sys.stderr)
        sys.exit(1)
    if status == "internal_ahead":
        print(f'  ✓ internal v{state.get("internal_version")} ahead of published '
              f'v{state.get("latest_published") or "(none)"} — normal pre-publish state, proceeding.')
        return {
            "publish_state": "STAGED_OR_UNPUBLISHED",
            "internal_version": state.get("internal_version"),
            "latest_published": state.get("latest_published"),
        }
    if status == "in_sync":
        print(f'  ✓ internal v{state.get("internal_version")} already published — '
              f'proceeding (re-produce/retry build).')
        return {
            "publish_state": "LIVE",
            "internal_version": state.get("internal_version"),
            "latest_published": state.get("latest_published"),
        }
    print(f'  ⚠ Unrecognized publish-state status {status!r} — treating as UNKNOWN, proceeding.')
    return {"publish_state": "UNKNOWN", "reason": f"unrecognized status {status!r}"}


def target_publish_state_provenance(preflight: dict, target_version: str) -> dict:
    """Classify the target artifact, not merely the current studio version.

    The publish-state checker compares the current internal version to the
    remote. With ``--target`` the artifact may be newer than both even when
    that comparison reports ``in_sync``. Recording that inherited LIVE result
    against the new target would falsely claim a private build is published.
    """
    result = dict(preflight)
    latest = result.get("latest_published")
    if not latest or result.get("publish_state") == "UNKNOWN":
        return result
    target_key = tuple(int(part) for part in target_version.split("."))
    latest_key = tuple(int(part) for part in str(latest).split("."))
    result["preflight_publish_state"] = result.get("publish_state")
    if target_key > latest_key:
        result["publish_state"] = "STAGED_OR_UNPUBLISHED"
    elif target_key == latest_key:
        result["publish_state"] = "LIVE"
    else:
        result["publish_state"] = "HISTORICAL"
    return result


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
            if scope == 'ship':
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
    build_dir = os.path.join(tropo_roots.RELEASES_DIR, f'v{new_version}', 'builds', product_name)
    testing_dir = os.path.join(tropo_roots.RELEASES_DIR, f'v{new_version}', 'testing', product_name)
    dist_dir = os.path.join(tropo_roots.RELEASES_DIR, f'v{new_version}', 'dist')

    if not DRY_RUN:
        # Pre-write guard — added 2026-05-01 (vela-v37, Stream 2 task 87e3b4d6).
        # Catches V36's 2026-04-30 retrospective scenario (--bump patch from
        # stale source clobbering existing different-version output dir).
        guard_overwrite(new_version, build_dir, testing_dir)
        # Every build is a clean-room projection. Reusing a partial prior tree
        # makes --force/retry output depend on stale files and can silently
        # inflate the manifest. The version-level provenance/verdict files stay
        # outside these regenerated directories.
        for generated_dir in (build_dir, testing_dir):
            if os.path.isdir(generated_dir):
                shutil.rmtree(generated_dir)
        stale_zip = os.path.join(dist_dir, f'{product_name}.zip')
        if os.path.exists(stale_zip):
            os.remove(stale_zip)
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
    """Backward-compat wrapper — calls engine with the Studio root + release target."""
    return _engine_load_manifest_entries(
        index_path, tropo_roots.STUDIO_ROOT, manifest_root_uid, target='release'
    )


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
    # FOLDER-LEVEL SKIPS. `_build_override_index` only indexes `kind: file`, so a
    # `kind: folder` + `source_mode: skip` entry declared real intent that the
    # walker silently ignored. Fresh-Box needs it: the template corpus ships
    # recursively, but root-docs and the two skeletons inside it RELOCATE
    # elsewhere (recipient root, agents/, .tropo-studio/), so without this a box
    # carries two copies of those bytes at different paths — and a recipient
    # edits the copy nobody reads (e52826c5 AC1).
    skip_dirs = tuple(
        os.path.join(_resolve_argo_path(e.get('canonical_source', '')), '')
        for e in entries
        if e.get('kind') == 'folder'
        and e.get('source_mode') == 'skip'
        and e.get('canonical_source')
    )
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

        src_abs = os.path.join(tropo_roots.STUDIO_ROOT, _resolve_argo_path(cs)) if cs else None
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
                    prune_bytecode(dirs, files)
                    rel = os.path.relpath(root, src_abs)
                    rel = '' if rel == '.' else rel
                    if skip_dirs and os.path.join(
                        os.path.relpath(root, tropo_roots.STUDIO_ROOT), ''
                    ).startswith(skip_dirs):
                        dirs[:] = []
                        continue
                    for fname in files:
                        src_file = os.path.join(root, fname)
                        src_file_rel = os.path.relpath(src_file, tropo_roots.STUDIO_ROOT)
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


PER_STUDIO_BOOT_DERIVATIONS = (
    '.tropo/boot-digest.md',
    '.tropo/boot-fast-path.md',
)
PER_STUDIO_BOOT_DERIVATION_UIDS = frozenset({
    '266b0b56',
    'a993f079',
})


#: Where the box tells itself which manifest to ask for updates.
UPDATE_SOURCE_REL = os.path.join('.tropo', 'update-source.json')


def step_3g_write_update_source(build_dir):
    """Give the box a concrete update address, or refuse to build it.

    ae5e743c finding 4, found live on the FIRST customer discovery (2026-08-09):
    the box shipped no update-source address at all. The concierge's
    remote-discovery step names "the stable manifest URL" and no such URL existed
    anywhere in the shipped tree, so the check was never testable — and because
    the surrounding contract is "offline = skip, no error state", an address that
    was MISSING looked exactly like a network that was down. That swallowed the
    gap forever.

    THE FIX IS A REFUSAL, NOT A WARNING, and the placement is the point. A box
    with no update address is a box that can never learn about its own updates,
    and the only people who can supply the address are us, at build time. Making
    the customer surface a configuration gap they cannot fix would move the
    report away from the person who can act. So the build stops.

    The URL is DERIVED, never typed: the same public Supabase releases path the
    manifest generator publishes to, so the address the box asks for and the
    address we upload to cannot drift. The previous default,
    `https://api.tropo-ai.com/updates`, was fictional infrastructure whose host
    never resolved — discovered on a real customer's first apply. Nothing here
    invents a host.
    """
    manifest_url = _resolve_update_manifest_url()
    if not manifest_url:
        raise SystemExit(
            'REFUSED: cannot resolve the update manifest URL, so this box would '
            'ship with no update address — the exact defect found on the first '
            'customer discovery (ae5e743c finding 4).\n'
            '  Cure: set NEXT_PUBLIC_SUPABASE_URL, or provide tropo-app/.env.local, '
            'so the address is DERIVED from where releases actually publish.\n'
            '  Do not hand-write a URL here: the previous hand-written default '
            'pointed at a host that never existed.'
        )

    payload = {
        'schema_id': 'tropo.update-source/v1',
        'manifest_url': manifest_url,
        'note': (
            'Where this studio asks about updates. Absence of this file is a '
            'CONFIGURATION GAP, not an offline condition: report it, do not '
            'silently skip. Generated at build from the publish target so the '
            'address asked for and the address published to cannot drift.'
        ),
    }
    dst = os.path.join(build_dir, UPDATE_SOURCE_REL)
    if not DRY_RUN:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2)
            handle.write('\n')
    print(f'  Update source: {manifest_url}')
    return manifest_url


UPDATE_PUBLIC_SHAPE = '/storage/v1/object/public/releases/updates'
TRACKED_UPDATES_MANIFEST_REL = os.path.join('vault', 'updates', 'updates-manifest.json')


def _resolve_update_base_from_tracked_manifest():
    """Derive the public base from PUBLICATION EVIDENCE already in the repo.

    `vault/updates/updates-manifest.json` records the real URLs previous
    releases were published to. That is evidence, not a guess: if a package was
    fetched from an address, that address exists. Deriving from it means a
    machine with no publish credentials can still build a walkable candidate,
    which is what blocked the AC8 walk (verdict 62a22664).

    Nothing here invents a host — the previous hand-written default
    (`api.tropo-ai.com`) pointed at infrastructure that never existed and broke
    a real customer's first update. A URL that does not carry the expected
    public shape is rejected rather than patched into shape.
    """
    manifest_path = os.path.join(tropo_roots.STUDIO_ROOT, TRACKED_UPDATES_MANIFEST_REL)
    try:
        with open(manifest_path, encoding='utf-8') as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    for url in sorted(set(re.findall(r'https://[^"\'\s]+', json.dumps(payload)))):
        marker = UPDATE_PUBLIC_SHAPE + '/'
        if url.startswith('https://') and marker in url:
            return url.split(marker)[0] + UPDATE_PUBLIC_SHAPE
    return None


def _reconcile_update_origins(env_base, tracked_base):
    """Two sources of the same address must agree, or the build refuses.

    Silently preferring one would publish a box pointed at a bucket nobody
    uploads to — the same class of failure as the fictional host, arrived at by
    a different route.
    """
    if env_base and tracked_base and env_base.rstrip('/') != tracked_base.rstrip('/'):
        raise SystemExit(
            'REFUSED: update-source drift — the publish environment resolves '
            f'{env_base!r} but tracked publication evidence in '
            f'{TRACKED_UPDATES_MANIFEST_REL} resolves {tracked_base!r}. '
            'One of them is wrong, and shipping either would point the box at a '
            'bucket that may receive nothing. Reconcile them, then rebuild.'
        )
    return (env_base or tracked_base or '').rstrip('/') or None


def _resolve_update_manifest_url():
    """The published manifest address: publish environment, then evidence.

    Order: the real publish env (NEXT_PUBLIC_SUPABASE_URL / tropo-app/.env.local)
    first, because that is the live target; then the stable public base derived
    from tracked publication evidence. When both resolve they must agree —
    `_reconcile_update_origins` refuses drift rather than choosing.

    Reads the generator's own resolver rather than restating its path, so there
    is one definition of where the manifest lives (velocity item 4's rule
    applied across tools rather than across a tool and its test).
    """
    # The publish environment is consulted through the generator's own resolver,
    # but a failure to LOAD it must not skip the evidence path — that early
    # return is why a machine without publish credentials produced an
    # unwalkable candidate (AC8 verdict 62a22664).
    env_base = None
    spec = importlib.util.spec_from_file_location(
        'tropo_generate_update_manifest_for_source',
        os.path.join(tropo_roots.VAULT_DIR, 'tools', 'tropo-generate-update-manifest.py'),
    )
    if spec is not None and spec.loader is not None:
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            pass
        except Exception:
            module = None
        if module is not None:
            try:
                env_base = getattr(module, '_resolve_package_url_base', lambda: None)()
            except Exception:
                env_base = None
    if env_base:
        env_base = env_base.rstrip('/')
    tracked_base = _resolve_update_base_from_tracked_manifest()
    base = _reconcile_update_origins(env_base, tracked_base)
    if not base:
        return None
    return f"{base.rsplit('/', 1)[0]}/updates-manifest.json"


def step_3f_remove_per_studio_boot_derivations(build_dir):
    """Remove source-Studio derivation files and their index rows together."""
    excluded_paths = set(PER_STUDIO_BOOT_DERIVATIONS)
    removed_rows = 0
    if not DRY_RUN:
        for surface_name in ('00-index.jsonl', '00-archive-index.jsonl'):
            surface = Path(build_dir) / 'vault' / surface_name
            if not surface.is_file():
                continue
            kept = []
            for line_number, line in enumerate(
                surface.read_text(encoding='utf-8').splitlines(), start=1
            ):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SystemExit(
                        f'Cannot prune boot derivation row; invalid JSON at '
                        f'{surface}:{line_number}: {exc}'
                    ) from exc
                if (
                    str(row.get('uid') or '') in PER_STUDIO_BOOT_DERIVATION_UIDS
                    or str(row.get('path') or '') in excluded_paths
                ):
                    removed_rows += 1
                    continue
                kept.append(row)
            staged = surface.with_name(f'.{surface.name}.boot-prune.tmp')
            staged.write_text(
                ''.join(
                    json.dumps(row, ensure_ascii=False) + '\n'
                    for row in kept
                ),
                encoding='utf-8',
            )
            os.replace(staged, surface)

    removed = 0
    for relative in PER_STUDIO_BOOT_DERIVATIONS:
        target = os.path.join(build_dir, relative)
        if DRY_RUN:
            print(f'  [DRY-RUN] Would exclude {relative}')
            continue
        if os.path.lexists(target):
            if os.path.isdir(target) and not os.path.islink(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
            removed += 1
        if os.path.lexists(target):
            raise SystemExit(
                f'Per-Studio boot derivation exclusion failed: {relative} remains in build'
            )
    print(
        f'  Per-Studio boot derivations: {removed} files + {removed_rows} index rows '
        'removed; package uses canonical fallback'
    )
    return removed


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
        prune_bytecode(dirs, files)
        # Skip concierge subtree — copied separately below with its own governance
        if root == concierge_dir or root.startswith(concierge_dir + os.sep):
            continue

        for fname in files:
            src = os.path.join(root, fname)
            if should_exclude_kernel(src):
                skipped += 1
                continue

            rel = os.path.relpath(src, src_kernel)

            # Per-studio STATE, excluded by PATH — the basename list above cannot
            # express "everything under .tropo/flags/". v1.86.0 shipped 24 of our
            # flags into every customer box, including the attendant-mode offer
            # gate whose documented meaning is "the offer was made, do not repeat
            # it", so a brand-new studio was told its owner had already been
            # through onboarding (talos-t40, velocity item 8, 2026-08-09).
            if package_state_exclusions.is_studio_state(
                (Path('.tropo') / rel).as_posix()
            ):
                skipped += 1
                continue
            dst = os.path.join(dst_kernel, rel)
            copy_file(src, dst, DRY_RUN)
            copied += 1

    # Also copy the concierge (it ships — it's the first-boot experience)
    concierge_src = os.path.join(src_kernel, 'concierge')
    if os.path.exists(concierge_src):
        for root, dirs, files in os.walk(concierge_src):
            prune_bytecode(dirs, files)
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

        src = resolve_source_path(entry, tropo_roots.STUDIO_ROOT)
        if not os.path.exists(src):
            print(f'    MISSING: {entry["uid"]} — {src}')
            missing += 1
            continue

        # Preserve each entry's real path verbatim in the build (One-Home,
        # ADR-045). GENERALIZED per Argus A122 sign-off (event 00004975/00005008,
        # board-item 71472692): mirror src_rel exactly — not just the vault/
        # subdir, the FULL relative path — so any current or future governed
        # location ships correctly by construction, including trees outside
        # vault/ entirely (e.g. the starter-agent templates at bare
        # agents/sa/<name>/<name>.md — readable-named, not vault/agents/,
        # so a vault/-only regex misses them and a 'files' fallback wrongly
        # dumps their readable names into vault/files/, which only tolerates
        # <uid>.md — this was the bug in the first cut of this fix, caught by
        # the UID Consistency check on the first real build). Fallback to
        # vault/files/<uid>.md ONLY when path: is absent from the entry.
        src_rel = entry.get('path', '')
        if src_rel:
            dst = os.path.join(build_dir, src_rel)
            dst_dir = os.path.dirname(dst)
        else:
            dst_dir = os.path.join(build_dir, 'vault', 'files')
            dst = os.path.join(dst_dir, f'{entry["uid"]}.md')
        if not DRY_RUN:
            os.makedirs(dst_dir, exist_ok=True)
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
        # Also strip agent_root_uid when it references a non-shipping UID.
        # Shipped vault/agents/ entries (e.g. the concierge 566770f7) carry
        # agent_root_uid pointing to studio-internal projects that don't ship.
        # Argus A118 2026-06-21 — extend dangling-ref filter to agent scalar refs.
        if row.get('agent_root_uid') and row['agent_root_uid'] not in shipped_uids:
            del row['agent_root_uid']
            pruned_total += 1
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
    .tropo/scripts/generate-capability-catalogs.py → vault/tools/tropo-generate-capability-catalogs.py at v1.76
    but build-release.py had no regen step, causing catalogs to freeze at 2026-05-14.
    This step ensures .tropo/{tool,skill,sa-agent}-catalog.md is current-as-of-build
    so a new Studio agent can discover all ship-scoped tools.

    Must run BEFORE step_3_copy_kernel (which copies .tropo/ into the build).
    """
    catalog_gen = os.path.join(tropo_roots.VAULT_DIR, 'tools', 'tropo-generate-capability-catalogs.py')
    if not os.path.exists(catalog_gen):
        print(f'  ⚠ catalog generator not found at vault/tools/tropo-generate-capability-catalogs.py — catalogs NOT regenerated')
        return
    if DRY_RUN:
        print(f'  [DRY-RUN] Would run: python3 vault/tools/tropo-generate-capability-catalogs.py --apply')
        return
    import subprocess as _sp
    result = _sp.run(
        [sys.executable, catalog_gen, '--apply'],
        capture_output=True, text=True, cwd=str(tropo_roots.STUDIO_ROOT),
        stdin=_sp.DEVNULL, timeout=60,
    )
    if result.returncode != 0:
        print(f'  ⚠ catalog regen failed (exit {result.returncode}): {result.stderr[:200]}')
    else:
        lines = [l for l in (result.stdout or '').splitlines() if l.strip()]
        for l in lines[-3:]:
            print(f'  {l}')
        print(f'  ✓ capability catalogs regenerated (current-as-of-build)')



# Directories under vault/tools/ never worth shipping — build-time caches only,
# never the target of any .tropo/scripts/ shim. Excluded from the recursive walk.
VAULT_TOOLS_EXCLUDE_DIRS = {'__pycache__', '.pytest_cache'}


def step_3b_copy_vault_tools(build_dir):
    """Step 4c.2: Copy vault/tools/ wholesale alongside the kernel — RECURSIVELY.

    vault/tools/ holds the canonical tool implementations that .tropo/scripts/
    shims forward to. The shims ship as part of .tropo/ (step_3_copy_kernel);
    their targets must also ship or the scripting layer is dead in a stranger's
    download. Ships wholesale — not per-tool extraction_scope — per Argus A92
    ruling fdef56ea: the scripting layer is atomic infrastructure; per-tool
    tagging re-opens the exact omission bug.

    Ship-gap fix (G1, Argus A123 v1.78 artifact verification, 2026-07-02): this
    function did a SHALLOW os.listdir() copy — any subdirectory under
    vault/tools/ (lib/, tests/) was silently skipped (os.path.isfile() on a
    directory is False, no recursion). vault/tools/lib/tropo_update_namespace.py
    (the Gate-2 covenant predicate itself) and all 25+ files under
    vault/tools/tests/ (pre-existing regression gates: test_no_two_homes_gate.py,
    test_one_open_activation_gate.py, etc. — this predates Gate 2 entirely) had
    NEVER shipped to any customer studio. Fixed to walk recursively via os.walk,
    excluding known build-cache directories (VAULT_TOOLS_EXCLUDE_DIRS).

    Added: v1.63 P0 fix (Talos T12) per ruling fdef56ea + directive 03b17aaa.
    Fixed to recurse: v1.78 (Talos T23) per Argus A123 finding G1.
    """
    src_tools = os.path.join(tropo_roots.VAULT_DIR, 'tools')
    dst_tools = os.path.join(build_dir, 'vault', 'tools')

    if not os.path.isdir(src_tools):
        print(f'  ✗ vault/tools/ not found at {src_tools} — scripting layer targets cannot ship',
              file=sys.stderr)
        sys.exit(1)

    if not DRY_RUN:
        os.makedirs(dst_tools, exist_ok=True)

    copied = 0
    for root, dirs, files in os.walk(src_tools):
        prune_bytecode(dirs, files)
        dirs[:] = sorted(d for d in dirs if d not in VAULT_TOOLS_EXCLUDE_DIRS)
        for fname in sorted(files):
            src_file = os.path.join(root, fname)
            rel = os.path.relpath(src_file, src_tools)
            dst_file = os.path.join(dst_tools, rel)
            copy_file(src_file, dst_file, DRY_RUN)
            copied += 1

    print(f'  vault/tools/: {copied} files copied recursively (scripting layer targets, incl. lib/ + tests/)')
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
    src_playbooks = os.path.join(tropo_roots.VAULT_DIR, 'playbooks')
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


def step_3e_copy_vault_updates(build_dir):
    """Step 4c.4: Copy vault/updates/ wholesale alongside the kernel — RECURSIVELY.

    Ship-gap fix (G2, Argus A123 v1.78 artifact verification, 2026-07-02): the
    update apply state machine (re-homed from the dissolved system/updates/ at
    Gate 2, dev-spec fc4874f4) was not shipping at all — a fresh v1.78 studio
    would have neither the old system/updates/ tree (retired — 2 stale
    ship-artifact entries sourcing from vault/templates/root-docs/system/updates/
    were still manufacturing it every build; see assert_no_stale_system_dir())
    nor the new vault/updates/ one, while the
    concierge (v1.5.0) and the apply-update playbook (v2.2) both point at
    vault/updates/ unconditionally. Ships wholesale mirroring the
    vault/tools/ / vault/playbooks/ pattern (ruling fdef56ea: infrastructure
    the runtime unconditionally depends on ships atomically, not per-file
    extraction_scope). Recursive from the start (walks pending/applied/failed/
    receipts/ and their keeper files) — G1 proved a shallow copy silently drops
    subdirectories.

    Added: v1.78 (Talos T23) per Argus A123 finding G2.
    """
    src_updates = os.path.join(tropo_roots.VAULT_DIR, 'updates')
    dst_updates = os.path.join(build_dir, 'vault', 'updates')

    if not os.path.isdir(src_updates):
        print(f'  ✗ vault/updates/ not found at {src_updates} — update apply state machine cannot ship',
              file=sys.stderr)
        sys.exit(1)

    if not DRY_RUN:
        os.makedirs(dst_updates, exist_ok=True)

    copied = 0
    for root, dirs, files in os.walk(src_updates):
        prune_bytecode(dirs, files)
        dirs[:] = sorted(dirs)
        for fname in sorted(files):
            src_file = os.path.join(root, fname)
            rel = os.path.relpath(src_file, src_updates)
            dst_file = os.path.join(dst_updates, rel)
            copy_file(src_file, dst_file, DRY_RUN)
            copied += 1

    print(f'  vault/updates/: {copied} files copied recursively (update apply state machine)')
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
        scripts_dir = os.path.join(tropo_roots.STUDIO_ROOT, '.tropo', 'scripts')
        tools_dir = os.path.join(tropo_roots.VAULT_DIR, 'tools')
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
    skeleton_src = os.path.join(tropo_roots.VAULT_DIR, 'templates', '.tropo-studio-skeleton')  # ADR-045: moved from .tropo/templates/ (v1.21.0)
    vault_dst = os.path.join(build_dir, '.tropo-studio')

    if not os.path.exists(skeleton_src):
        raise SystemExit(
            f'.tropo-studio/ skeleton template not found at {skeleton_src}.\n'
            f'Expected location per Tropo-OS convention (vault/templates/.tropo-studio-skeleton/).\n'
            f'If this vault predates Tropo-OS v1.2, install or update.\n'
            f'Path-base / tier-reachability failure — halting rather than silent-skipping, '
            f'per ADR-032 amendment 2026-04-19.'
        )

    if not DRY_RUN:
        # Remove any pre-existing destination to ensure clean copy
        if os.path.exists(vault_dst):
            shutil.rmtree(vault_dst)
        shutil.copytree(skeleton_src, vault_dst,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))

    # Count what got copied for the log line
    file_count = 0
    for root, _, files in os.walk(skeleton_src):
        file_count += len(files)

    print(f'  .tropo-studio/: skeleton copied from template ({file_count} files)')


def step_8_write_version(build_dir, new_version):
    """Step 4h: Write the canonical bare one-line version contract."""
    dst = os.path.join(build_dir, '.tropo', 'version.md')
    if not DRY_RUN:
        with open(dst, 'w') as f:
            f.write(f'v{new_version}\n')
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

    rebuild_path = os.path.join(build_dir, 'vault', 'tools', 'tropo-rebuild-vault.py')  # rebuild-vault (v1.56 migrated)
    rehydrate_path = os.path.join(build_dir, 'vault', 'tools', 'tropo-rehydrate.py')  # rehydrate (v1.56 migrated). RT1 fix argus-a118 2026-06-21: was .tropo/scripts/rehydrate.py — moved at v1.56, so nav regen silently skipped + a fresh download shipped with no 00-tropo-nav. Mirrors L998 (rebuild-vault at vault/tools/).

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

    # Step 4 writes a provisional current index for the manifest walker. It is
    # not a complete index generation: no archive/SQLite/meta companions exist,
    # so the transactional index writer correctly refuses to adopt it. The
    # build directory is scratch output, not user state; clear that provisional
    # generation before asking the shipped rebuilder to derive the authoritative
    # current+archive pair and navigation from shipped source files.
    for rel in (
        'vault/00-index.jsonl',
        'vault/00-archive-index.jsonl',
        'vault/00-index.sqlite',
        'vault/00-project-tree.jsonl',
        '.tropo-studio/locks/index-surfaces.meta.json',
        '.tropo-studio/locks/index-surfaces.ratchet.json',
    ):
        candidate = os.path.join(build_dir, rel)
        if os.path.isfile(candidate):
            os.unlink(candidate)

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


# ─── Vendor-ref manifest (S1, v1.80 re-build) ───────────────────────────────
# The v1.80 customer-mode health surface (tropo-validate.py --customer) needs to
# classify a not-in-index UID reference as an "expected vendor outward-ref" vs a
# "real defect" using DATA, not guesswork. Prior to this fix, no such data existed
# — customer-mode just reused the pre-build release_mode's blanket "not in subset
# index -> safe by construction" downgrade, which swallowed a planted genuinely-
# broken ref (refs:[ffffffff]) as INFO. This step builds the manifest: the set of
# UID references from shipped files that point at real, legitimately-existing
# source-studio UIDs that simply didn't ship (studio-internal, not customer-facing).
# A ref that resolves to nothing anywhere in the source studio is NOT a vendor ref
# — it's excluded from the manifest, so customer-mode will still [FAIL] it.

_VENDOR_MANIFEST_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_VENDOR_MANIFEST_UID_RE = re.compile(r'^[0-9a-f]{8}$')
_VENDOR_MANIFEST_IDENTITY_FIELDS = frozenset({'tropo_agent_id', 'registry_uid'})
_VENDOR_MANIFEST_EXCLUDE_TOP = {'node_modules', '.git', 'archive', 'recycle', 'releases'}


def _vendor_manifest_split_frontmatter(text):
    m = _VENDOR_MANIFEST_FRONTMATTER_RE.match(text)
    return m.group(1) if m else None


def _vendor_manifest_governed_files(root_path):
    """Yield Markdown entries and Python-hosted tool entries."""
    for path in root_path.rglob('*'):
        if not path.is_file() or path.suffix not in {'.md', '.py'}:
            continue
        try:
            rel = path.relative_to(root_path)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in _VENDOR_MANIFEST_EXCLUDE_TOP:
            continue
        yield path


def _vendor_manifest_file_frontmatter(path):
    try:
        text = path.read_text(errors='replace')
    except OSError:
        return None
    if path.suffix == '.py':
        marker = text.find('---\n')
        if marker < 0:
            return None
        text = text[marker:]
    return _vendor_manifest_split_frontmatter(text)


def _vendor_manifest_uid_value(node):
    if isinstance(node, str):
        candidate = node
    elif isinstance(node, int) and not isinstance(node, bool):
        candidate = str(node)
    else:
        return None
    return candidate if _VENDOR_MANIFEST_UID_RE.match(candidate) else None


def _vendor_manifest_walk_for_uids(node, hits, at_root=False):
    """Recursively collect UID-shaped strings, mirroring tropo-validate.py's
    check_uid_cross_references._walk_for_uids exclusions (root uid: + identity
    fields skipped — those are self-identity, not graph references)."""
    if isinstance(node, dict):
        for key, value in node.items():
            key_str = str(key) if key is not None else ''
            if key_str in _VENDOR_MANIFEST_IDENTITY_FIELDS:
                continue
            if key_str == 'uid' and at_root:
                continue
            _vendor_manifest_walk_for_uids(value, hits, at_root=False)
    elif isinstance(node, list):
        for item in node:
            _vendor_manifest_walk_for_uids(item, hits, at_root=False)
    else:
        uid = _vendor_manifest_uid_value(node)
        if uid:
            hits.append(uid)


def _vendor_manifest_collect_all_uids(root):
    """All uid: frontmatter values in Markdown/Python surfaces under `root`, same exclusions as
    tropo-validate.py main()'s full-studio UID sweep (node_modules/.git/archive/
    recycle/releases skipped; non-governed)."""
    uids = set()
    root_path = Path(root)
    if not root_path.is_dir():
        return uids
    for governed_file in _vendor_manifest_governed_files(root_path):
        fm_text = _vendor_manifest_file_frontmatter(governed_file)
        if not fm_text:
            continue
        try:
            fm = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        uid = _vendor_manifest_uid_value(fm.get('uid'))
        if uid:
            uids.add(uid)
    return uids


def _vendor_manifest_collect_referenced_uids(root):
    """All UID-shaped reference values (any field, any nesting) across every
    shipped .md/.py file under `root`, excluding self-identity per the walker."""
    refs = set()
    root_path = Path(root)
    if not root_path.is_dir():
        return refs
    for governed_file in _vendor_manifest_governed_files(root_path):
        fm_text = _vendor_manifest_file_frontmatter(governed_file)
        if not fm_text:
            continue
        try:
            fm = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        hits = []
        _vendor_manifest_walk_for_uids(fm, hits, at_root=True)
        refs.update(hits)
    return refs


def step_9c_generate_vendor_ref_manifest(build_dir, new_version):
    """S1 (v1.80 re-build): generate the vendor-ref manifest that ships in the box.

    Runs AFTER step_9b (so it reads the freshly-rebuilt, shipped-ledger-only
    00-index.jsonl / vault/files set) — the manifest is data about what actually
    shipped, not the pre-regen snapshot.

    vendor_refs = (every UID-shaped reference in a shipped file)
                  MINUS (UIDs that shipped — those resolve normally)
                  INTERSECTED WITH (UIDs that exist anywhere in the SOURCE studio)

    That last intersection is what makes this safe: a reference to a UID that
    exists nowhere in the source studio (e.g. a planted `refs: [ffffffff]`) is
    NOT a legitimate vendor ref and is deliberately excluded from the manifest —
    customer-mode will still [FAIL] it.
    """
    print('Step 9c — Generate vendor-ref manifest (S1, v1.80):')
    if DRY_RUN:
        print('  [DRY-RUN] Would generate vault/vendor-refs-manifest.json')
        return 0

    shipped_uids = _vendor_manifest_collect_all_uids(build_dir)
    source_uids = _vendor_manifest_collect_all_uids(tropo_roots.STUDIO_ROOT)
    referenced_uids = _vendor_manifest_collect_referenced_uids(build_dir)

    outward_refs = referenced_uids - shipped_uids
    vendor_refs = outward_refs & source_uids
    unresolvable = outward_refs - vendor_refs

    if unresolvable:
        print(f'  ⚠ {len(unresolvable)} shipped reference(s) resolve to NEITHER the shipped box '
              f'NOR the source studio — excluded from the vendor-ref manifest (will [FAIL] in '
              f'customer-mode, as they should). This should already be impossible per the '
              f'pre-build full-studio 0-FAILED gate; investigate if seen:')
        for u in sorted(unresolvable)[:10]:
            print(f'    - {u}')

    manifest = {
        'schema_version': 1,
        'generated': datetime.now().isoformat(timespec='seconds'),
        'generated_by': 'tropo-build-release.py step_9c (S1, v1.80)',
        'release_version': new_version,
        'count': len(vendor_refs),
        'vendor_refs': sorted(vendor_refs),
    }

    out_dir = os.path.join(build_dir, 'vault')
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, 'vendor-refs-manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2, sort_keys=False)
        f.write('\n')

    print(f'  vendor-refs-manifest.json: {len(vendor_refs)} vendor outward-ref(s) '
          f'({len(unresolvable)} excluded as unresolvable)')
    return len(vendor_refs)


def _load_release_index_surfaces(build_dir):
    module_path = (
        Path(build_dir) / 'vault' / 'tools' / 'lib' / 'index_surfaces.py'
    )
    if not module_path.is_file():
        raise SystemExit(
            f'Shipped index surface library is missing: {module_path}'
        )
    module_name = (
        '_tropo_release_index_surfaces_'
        + hashlib.sha256(str(module_path).encode('utf-8')).hexdigest()[:12]
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f'Could not load shipped index surface library: {module_path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _read_release_index_rows(path):
    if not path.is_file():
        return []
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding='utf-8').splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f'Invalid release index JSON at {path}:{line_number}: {exc}'
            ) from exc
        if not isinstance(row, dict):
            raise SystemExit(
                f'Invalid release index row at {path}:{line_number}: expected object'
            )
        rows.append(row)
    return rows


def _release_index_source_inventory(build_dir, rows):
    inventory = []
    seen = set()
    for row in rows:
        uid = str(row.get('uid') or '')
        relative = str(row.get('path') or (
            f'vault/files/{uid}.md' if uid else ''
        ))
        if not relative or relative in seen:
            raise SystemExit(
                f'Release index row has no unique source path: uid={uid!r}, path={relative!r}'
            )
        source = Path(build_dir) / relative
        if not source.is_file():
            raise SystemExit(
                f'Release index row {uid!r} has no shipped source file at {relative}'
            )
        if source.is_symlink():
            mode = '120000'
            raw = os.readlink(source).encode('utf-8')
        else:
            mode = '100755' if os.access(source, os.X_OK) else '100644'
            raw = source.read_bytes()
        inventory.append((relative, mode, hashlib.sha256(raw).hexdigest()))
        seen.add(relative)
    return inventory


_GENESIS_SQLITE_SCRIPT = r"""
import importlib.util
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
tools = root / "vault" / "tools"
sys.path.insert(0, str(tools))
module_path = tools / "tropo-rebuild-index.py"
spec = importlib.util.spec_from_file_location(
    "_tropo_release_genesis_rebuild", module_path
)
if spec is None or spec.loader is None:
    raise RuntimeError(f"could not load {module_path}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

rows = []
for name in ("00-index.jsonl", "00-archive-index.jsonl"):
    path = root / "vault" / name
    if not path.is_file():
        continue
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
raw = module.build_sqlite_index(
    root, rows, True, defer_replace=True
)
if not raw:
    raise RuntimeError("genesis SQLite builder returned no bytes")
output.write_bytes(raw)
"""


def _build_release_genesis_sqlite_image(build_dir):
    """Build the customer box's canonical SQLite union in a clean interpreter."""
    fd, output_name = tempfile.mkstemp(
        prefix='.tropo-release-genesis-', suffix='.sqlite'
    )
    os.close(fd)
    output = Path(output_name)
    try:
        result = subprocess.run(
            [
                sys.executable,
                '-c',
                _GENESIS_SQLITE_SCRIPT,
                str(Path(build_dir).resolve()),
                str(output),
            ],
            capture_output=True,
            text=True,
            cwd=build_dir,
            timeout=300,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or '').strip()
            raise RuntimeError(
                f'genesis SQLite builder failed (exit {result.returncode}): '
                f'{detail[-1000:]}'
            )
        raw = output.read_bytes()
        if not raw:
            raise RuntimeError('genesis SQLite builder produced an empty image')
        return raw
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f'genesis SQLite builder could not run: {exc}') from exc
    finally:
        output.unlink(missing_ok=True)


def step_10_1_seal_release_index_pair(build_dir, floor_evidence_uid):
    """Seal current + legitimately-empty archive surfaces as one trusted pair."""
    if DRY_RUN:
        print('Step 10.1 — [DRY-RUN] Would seal release index surface pair')
        return
    print('Step 10.1 — Seal release index surface pair:')
    index_surfaces = _load_release_index_surfaces(build_dir)
    vault_dir = Path(build_dir) / 'vault'
    current_path = vault_dir / index_surfaces.CURRENT_INDEX_NAME
    archive_path = vault_dir / index_surfaces.ARCHIVE_INDEX_NAME
    current_rows = _read_release_index_rows(current_path)
    archive_rows = _read_release_index_rows(archive_path)
    if (
        not isinstance(floor_evidence_uid, str)
        or not re.fullmatch(r'[0-9a-f]{8}', floor_evidence_uid)
    ):
        print(
            '  ✗ Build REFUSED — release index floor initialization requires '
            'an 8-hex activation/evidence UID.'
        )
        raise SystemExit(1)
    try:
        inventory = _release_index_source_inventory(
            build_dir, current_rows + archive_rows
        )
        proof = index_surfaces.prove_full_source_derivation(
            current_rows,
            archive_rows,
            source_complete=True,
            source_inventory=inventory,
        )
        sqlite_path = vault_dir / '00-index.sqlite'
        sqlite_raw = _build_release_genesis_sqlite_image(build_dir)
        index_surfaces.write_jsonl_pair_atomic(
            (
                (current_path, current_rows),
                (archive_path, archive_rows),
            ),
            full_source_derivation_proof=proof,
            surface_metadata_recovery_reason=(
                'release-box full-source derivation after sanitization'
            ),
            governed_floor_recovery=index_surfaces.GovernedFloorRecovery(
                current_protected_record_count=len(current_rows),
                archive_protected_record_count=len(archive_rows),
                evidence_uid=floor_evidence_uid,
            ),
            companion_replacements=((sqlite_path, sqlite_raw),),
        )
        # Prove both reads through the exact strict path customer-mode uses.
        index_surfaces.read_jsonl_strict(current_path)
        index_surfaces.read_jsonl_strict(archive_path)
    except (index_surfaces.IndexSurfaceRefusal, RuntimeError) as exc:
        print(f'  ✗ Build REFUSED — release index pair seal failed: {exc}')
        raise SystemExit(1) from None
    print(
        f'  ✓ current={len(current_rows)} rows, archive={len(archive_rows)} rows; '
        f'trusted floors initialized by {floor_evidence_uid}'
    )


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
        # Full SHA-256 (not truncated) — Gate 2 LOCK-AMENDMENT 2 (fc4874f4, finding 4496553c):
        # the namespace predicate's category (d) reads THIS file on a customer's disk to decide
        # replace-vs-preserve-vs-user-modified-shipped. A shipped studio has no source tree to
        # recompute hashes against; the 12-char display-truncated prefix this used to carry was
        # fine for a human skimming the table but not a real per-file integrity comparison.
        f.write('| Path | Size | SHA-256 |\n')
        f.write('|------|-----:|--------|\n')
        for rel, size, checksum in entries:
            f.write(f'| {rel} | {size:,} | `{checksum}` |\n')

    print(f'  Manifest: {len(entries)} files, {total_size:,} bytes total')
    return len(entries)



#: THE INDEX GENERATION LEAVES THE PACKAGE AS ONE SET (Argus, evt 114).
#:
#: A package cannot carry PART of an index generation. Shipping the pair with a
#: seal but no database gave the recipient two of the three evidence copies the
#: writer requires, and its first rebuild refused as incomplete evidence;
#: shipping the database made the package machine-dependent, because SQLite
#: bytes vary by library version. Both failures are the same mistake in
#: different clothes — a partial generation is evidence that contradicts itself.
#:
#: So the box carries none of it, and the recipient's first documented rebuild
#: bootstraps the whole generation locally: current, archive, project tree,
#: metadata, ratchet and its own database. That is the only shape the writer
#: both accepts and can recover from without machine-bound bytes.
PORTABLE_PURGE_NAMES = ('index-write.lock',)
PORTABLE_PURGE_SUFFIXES = ('.pyc', '.pyo', '-shm', '-wal', '.tmp-shm', '.tmp-wal')
PORTABLE_PURGE_EXACT_RELATIVE = (
    'vault/00-index.jsonl',
    'vault/00-archive-index.jsonl',
    'vault/00-project-tree.jsonl',
    'vault/00-index.sqlite',
    '.tropo-studio/locks/index-surfaces.meta.json',
    '.tropo-studio/locks/index-surfaces.ratchet.json',
)


def step_10_2_purge_run_local_artifacts(build_dir):
    """Remove what BUILDING the box created inside it, before the digest.

    Excluding bytecode during the copy traversals is necessary but not
    sufficient: later steps EXECUTE code inside the build directory — sealing
    the index pair imports the box's own `lib` — and the interpreter writes
    fresh `__pycache__` there afterwards, along with a machine-local index write
    lock. Two builds of one commit then differ in files that no source produced,
    which is the defect from evt 102 arriving by a second route.

    Purging after the last step that can create them is the only placement that
    holds regardless of which future step runs code in the box.
    """
    removed = 0
    for root, dirs, files in os.walk(build_dir, topdown=False):
        for name in list(dirs):
            if name in ('__pycache__',):
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
                removed += 1
                dirs.remove(name)
        for name in files:
            # `-shm`/`-wal` (and their `.tmp-` variants) are SQLite's journal
            # files. They are an artifact of the process that just wrote the
            # database, not content: Metis's Mac left `.tmp-shm`/`.tmp-wal`
            # where this machine leaves `-shm`/`-wal`, so the file COUNT itself
            # varied by platform before either byte was compared.
            rel = os.path.relpath(os.path.join(root, name), build_dir).replace(os.sep, '/')
            claims_absent_generation = (
                rel.startswith('vault/00-index') or rel.startswith('vault/00-archive-index')
                or rel.startswith('.tropo-studio/locks/index-'))
            if (name.endswith(PORTABLE_PURGE_SUFFIXES)
                    or name in PORTABLE_PURGE_NAMES
                    or rel in PORTABLE_PURGE_EXACT_RELATIVE
                    or claims_absent_generation):
                try:
                    os.remove(os.path.join(root, name))
                    removed += 1
                except OSError:
                    pass
    if removed:
        print(f'Step 10.2 — Purged {removed} non-portable artifact(s) '
              f'(bytecode, write locks, SQLite + its journals)')
    return removed


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
        # Metis's cold walk (verdict 62a22664): a recipient has no `argo-os/`
        # directory, so prose naming it as THIS FOLDER points a newcomer at a
        # path that does not exist in the artifact they are holding. Scoped to
        # that reader-addressing phrase deliberately — `argo-os/vault/...` in a
        # capsule's canonical_source examples describes a SOURCE address the
        # manifest really uses, and rewriting it would corrupt documentation to
        # fix a greeting.
        (re.compile(r'\(this folder, `argo-os/`\)', re.I), '(this folder)'),
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

    stripped_scope = 0
    for root, _, files in os.walk(build_dir):
        for f in files:
            if not f.endswith('.md'):
                continue
            path = Path(root) / f
            try:
                content = path.read_text(encoding='utf-8')
            except Exception:
                continue
            if not content.startswith('---\n'):
                continue
            end = content.find('\n---', 4)
            if end == -1:
                continue
            head, rest = content[:end], content[end:]
            # The trailing newline is optional: the LAST frontmatter line ends
            # at the fence, not at a newline, and requiring one silently missed
            # every single-field frontmatter (START-TROPO.md, GEMINI.md).
            cleaned = re.sub(r'^extraction_scope:[ \t]*argo-reference[ \t]*(?:\n|$)', '',
                             head, flags=re.M)
            if cleaned != head:
                path.write_text(cleaned + rest, encoding='utf-8')
                stripped_scope += 1
    if stripped_scope:
        print(f'  Build-metadata frontmatter stripped from {stripped_scope} file(s)')

    argo_isms = ['the Studio', 'the development dogfood', 'this folder, `argo-os/`']
    findings = []
    for root, _, files in os.walk(build_dir):
        for f in files:
            if f.endswith(_skip):
                continue
            path = os.path.join(root, f)
            rel_path = os.path.relpath(path, build_dir)
            # The sanitizer's own rule table necessarily spells the strings it
            # removes, so scanning it finds the definition rather than a leak.
            if f == os.path.basename(__file__):
                continue
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


WALK_ANSWER_ENV = 'TROPO_WALK_ANSWER'


def _normalize_walk_answer(raw):
    value = str(raw or '').strip().lower()
    if value in ('', 'y', 'yes'):
        return '', 'yes'
    if value in ('n', 'no'):
        return 'n', 'no'
    raise ValueError(
        f"invalid cold-walk answer {raw!r}; expected y/yes/n/no"
    )


def _resolve_walk_answer(explicit_answer=None, stdin=None):
    """Resolve flag → env → immediate non-TTY default → interactive TTY."""
    stdin = stdin or sys.stdin
    interactive = False
    if explicit_answer is not None:
        raw, source = explicit_answer, '--walk-answer'
    elif WALK_ANSWER_ENV in os.environ:
        raw, source = os.environ[WALK_ANSWER_ENV], WALK_ANSWER_ENV
    elif not stdin.isatty():
        raw, source = '', 'immediate non-TTY default (stdin not read)'
    else:
        raw = input(
            '  Run the cold-boot stranger walk? [Y/n, default Y]: '
        )
        source = 'interactive TTY'
        interactive = True
    normalized, label = _normalize_walk_answer(raw)
    print(f'  Cold-walk prompt answer: {label} (source: {source})')
    return normalized, interactive


def step_10_6_cold_walk_gate(new_version, dist_dir, verdict_path, last_cw_path,
                             walk_answer=None, stdin=None):
    """Step 10.6 — Stranger-walk gate (dev-spec 554624e5; v1.74).

    Always-ask: 'Run the cold-boot stranger walk?' Default YES. Override-to-skip recorded.

    Returns cold_walk_ok (bool):
      True  — upload may proceed (skip or PASS verdict)
      False — upload blocked (elected but verdict pending); zip is created for Po to walk

    Hard exit (sys.exit 5) on FAIL verdict — broken walk must be fixed before ship.
    """
    import json as _json
    from datetime import datetime as _dt

    print('Step 10.6 — Stranger-walk gate (dev-spec 554624e5):')

    # Always-ask (D3: always-ask, default YES — dev-spec 554624e5)
    try:
        answer, interactive_answer = _resolve_walk_answer(
            walk_answer, stdin
        )
    except (EOFError, KeyboardInterrupt):
        answer, interactive_answer = '', True
        print('  Cold-walk prompt answer: yes (source: EOF/interrupt default)')
    except ValueError as exc:
        print(f'  ✗ Build REFUSED — {exc}', file=sys.stderr)
        raise SystemExit(2) from None
    elected = (answer in ('', 'y', 'yes'))

    if not elected and not interactive_answer:
        print(
            '  ✗ Build REFUSED — a non-interactive `no` cannot create '
            '`skipped-by-mike`; answer yes/default headlessly or use a real TTY.',
            file=sys.stderr,
        )
        raise SystemExit(2)

    now = _dt.now().strftime('%Y-%m-%dT%H:%M:%S')
    os.makedirs(os.path.dirname(verdict_path), exist_ok=True)

    if not elected:
        # Skip path — record provenance, allow upload
        skip_rec = {
            'schema_version': '1',
            'release_version': new_version,
            'cold_walk': 'skipped-by-mike',
            'skipped_at': now,
        }
        with open(verdict_path, 'w') as f:
            _json.dump(skip_rec, f, indent=2)
        print(f'  Cold-walk: skipped-by-mike — provenance recorded.')
        print(f'    ({verdict_path})')
        return True

    # Elected — check for a Po-recorded verdict
    print('  Cold-walk: elected (default YES)')
    if not os.path.isfile(verdict_path):
        _pending_zip = os.path.join(dist_dir, f'tropo-os-v{new_version}.zip')
        print('  ⚠ No verdict on disk — zip will be created; upload blocked pending walk.')
        print('    After this build, conduct the walk and re-ship:')
        print(f'      1. python3 .tropo/scripts/test-harness-l2.py --release-zip {_pending_zip}')
        print(f'      2. Ask Po to walk (conductor: .tropo/playbooks/test-harness.playbook.md)')
        print(f'         Po writes verdict → {verdict_path}')
        print(f'      3. Re-run build-release.py --target {new_version} --force to upload.')
        pending_rec = {
            'schema_version': '1',
            'release_version': new_version,
            'cold_walk': 'elected-pending',
            'elected_at': now,
        }
        with open(verdict_path, 'w') as f:
            _json.dump(pending_rec, f, indent=2)
        return False  # upload blocked; zip proceeds

    with open(verdict_path) as f:
        verdict_data = _json.load(f)

    overall = verdict_data.get('overall')

    if overall == 'PASS':
        # Green — stamp provenance, update last-cold-walk pointer, allow upload
        verdict_data['cold_walk'] = 'ran'
        verdict_data['shipped_at'] = now
        with open(verdict_path, 'w') as f:
            _json.dump(verdict_data, f, indent=2)
        last_rec = {
            'last_cold_walk_release': new_version,
            'walk_date': verdict_data.get('walk_date', 'unknown'),
        }
        with open(last_cw_path, 'w') as f:
            _json.dump(last_rec, f, indent=2)
        print(f'  ✓ Cold-walk PASS (walk_date: {verdict_data.get("walk_date", "unknown")}) — ship cleared.')
        return True

    if overall == 'FAIL':
        print(f'\n  ✗ Ship BLOCKED — cold-walk verdict is FAIL.', file=sys.stderr)
        print(f'    Verdict file: {verdict_path}', file=sys.stderr)
        print('    Fix the failures the walk surfaced, re-run the walk via Po, then re-ship.', file=sys.stderr)
        sys.exit(5)

    # overall is None or unknown (e.g. prior elected-pending or skipped-by-mike overridden)
    _pending_zip = os.path.join(dist_dir, f'tropo-os-v{new_version}.zip')
    print('  ⚠ Verdict on disk has no overall verdict — walk not yet conducted (or prior skip).')
    print('    Zip will be created; upload blocked pending a conducted walk.')
    print(f'      1. python3 .tropo/scripts/test-harness-l2.py --release-zip {_pending_zip}')
    print(f'      2. Ask Po to walk → Po writes verdict to {verdict_path}')
    print(f'      3. Re-run build-release.py --target {new_version} --force to upload.')
    pending_rec = {
        'schema_version': '1',
        'release_version': new_version,
        'cold_walk': 'elected-pending',
        'elected_at': now,
        'prior_state': overall,
    }
    with open(verdict_path, 'w') as f:
        _json.dump(pending_rec, f, indent=2)
    return False


def assert_shipped_surfaces(build_dir):
    """RT1/RT2 ship-surface guard (argus-a118, v1.74): a release MUST carry its
    declared human-navigation + workspace surfaces. Both shipped silently-missing
    in Mike's v1.74 release-walk — nav-regen pointed at a moved rehydrate path (RT1)
    and the workspace folders had no manifest entry (RT2). A release that cannot
    produce a declared surface must FAIL the build, not ship a quiet hole.
    Same silent-failure class as the F19/P0 transformation body-drop. (Finding 1ee11d09.)"""
    required = ['00-tropo-nav', '01-studio-inbox', '02-outbox', '03-design',
                '04-external-work', '99-recycle']
    missing = [d for d in required if not os.path.isdir(os.path.join(build_dir, d))]
    nav = os.path.join(build_dir, '00-tropo-nav')
    if os.path.isdir(nav) and not os.listdir(nav):
        missing.append('00-tropo-nav (present but EMPTY — nav regen produced nothing)')
    if missing:
        print('  ✗ SHIP-SURFACE GUARD FAILED — release is missing declared surface(s):', file=sys.stderr)
        for d in missing:
            print(f'      - {d}', file=sys.stderr)
        print('    A release that cannot produce its declared nav + workspace surfaces must NOT ship', file=sys.stderr)
        print('    (RT1/RT2, finding 1ee11d09). Fix the nav-regen step / ship-artifact manifest and re-build.', file=sys.stderr)
        sys.exit(6)
    print('  ✓ Ship-surface guard: 00-tropo-nav + 5 workspace folders present in build.')


def assert_no_stale_system_dir(build_dir):
    """One Home retirement guard — ALL of system/ must be absent from the shipped box.

    History:
    - Gate 2 (v1.78, Argus A123 2026-07-02): system/updates/ dissolved (re-homed to
      vault/updates/); retired c5f8a193 + e7c2a851 (source_mode -> skip).
    - v1.80 S3 (talos-t24 2026-07-04): system/vault-steward/ re-homed to
      vault/tropo-vault-steward/ per ADR-045 One Home. With that re-home, the whole
      system/ tree is now empty of shipping content — guard widened to ALL of system/.
      a3d7b248 + b94e3d72 now output_path: vault/tropo-vault-steward/.

    Inverse-checks vault/updates/ is present — the two must move together or a
    fresh box lands on neither the old layout nor the new one."""
    stale_dir = os.path.join(build_dir, 'system')
    updates_dir = os.path.join(build_dir, 'vault', 'updates')

    problems = []
    if os.path.isdir(stale_dir):
        contents = []
        for root, _, files in os.walk(stale_dir):
            for f in files:
                contents.append(os.path.relpath(os.path.join(root, f), build_dir))
        if contents:
            problems.append(f"system/ shipped ({len(contents)} file(s)) — dissolved by "
                             f"ADR-045 One Home (system/updates/ at Gate 2; system/vault-steward/ "
                             f"at v1.80 S3). Check c5f8a193 + e7c2a851 are source_mode:skip and "
                             f"a3d7b248 + b94e3d72 output_path is vault/tropo-vault-steward/. "
                             f"Sample: {contents[:5]}")
    if not os.path.isdir(updates_dir) or not os.listdir(updates_dir):
        problems.append("vault/updates/ missing or empty — the Gate-2 update apply state "
                         "machine did not ship (see step_3e_copy_vault_updates).")

    if problems:
        print('  ✗ ONE-HOME RETIREMENT GUARD FAILED (all system/ must be absent):', file=sys.stderr)
        for p in problems:
            print(f'      - {p}', file=sys.stderr)
        print('    Fix: confirm c5f8a193 + e7c2a851 are source_mode:skip; '
              'confirm a3d7b248 + b94e3d72 output_path is vault/tropo-vault-steward/; re-build.', file=sys.stderr)
        sys.exit(8)
    print('  ✓ One Home retirement guard: system/ absent from build; vault/updates/ present '
          '(system/ fully re-homed per ADR-045).')


# Argo-internal markers that must never appear in the shipped mission-brief boot slot.
# Drawn from the leak's own content (task 2ffda37e defect #1 §Verification) — the phrases
# a customer studio was reading as its OWN mission before the slot was repointed at the
# generic template.
_MISSION_BRIEF_LEAK_MARKERS = ('argo', 'metis', 'hollow economy', 'agentic builders',
                               'culture is the moat')

# Word-boundary matched, not substring: a bare `'argo' in body` also fires on "cargo",
# "embargo" and "Argonaut", which would fail a release build with a confidentiality
# message about a word the template is entitled to use.
_MISSION_BRIEF_LEAK_RE = re.compile(
    r'\b(?:' + '|'.join(re.escape(m) for m in _MISSION_BRIEF_LEAK_MARKERS) + r')\b',
    re.IGNORECASE)


def assert_mission_brief_slot(build_dir):
    """Mission-brief boot-slot guard (task 2ffda37e defect #1, P1 confidentiality leak).

    The slot .tropo-studio/mission-brief.md is BOTH a boot-contract requirement and a
    confidentiality surface, and the two pull in opposite directions:
      - absent  → every customer agent hits a missing required read at Step 2.3
                  (activation playbook 99341618) / Tier-2 read-at-every-boot (cf8c3be9);
      - populated with real prose → whatever is in it becomes the mission every agent in
                  that studio boots on, which is exactly how Argo's internal crew brief
                  shipped verbatim to customer studios.

    Only a `<FILL: …>` template satisfies both. This asserts that AFTER every step that
    writes into the box — Step 7's rmtree+recreate of .tropo-studio/ and Step 10's
    sanitize pass both run over this path — so a later step silently clobbering the slot
    cannot ship. Same posture as assert_shipped_surfaces: a declared surface the build
    cannot produce correctly must FAIL the build rather than ship a quiet hole."""
    slot = os.path.join(build_dir, '.tropo-studio', 'mission-brief.md')
    if not os.path.isfile(slot):
        print('  ✗ MISSION-BRIEF SLOT GUARD FAILED — .tropo-studio/mission-brief.md absent '
              'from the build.', file=sys.stderr)
        print('    It is a Required:Yes boot read (99341618 Step 2.3 + cf8c3be9 Tier 2); a box '
              'without it breaks first boot for every customer agent. Check Step 7.1 and that '
              'Step 7 did not clobber it.', file=sys.stderr)
        sys.exit(9)

    body = Path(slot).read_text(encoding='utf-8')
    problems = []
    if '<FILL:' not in body:
        problems.append('no <FILL: …> placeholders — the slot is not the generic template. '
                        'Whatever is in it becomes the mission every agent in a customer '
                        'studio boots on.')
    hits = sorted({m.group(0).lower() for m in _MISSION_BRIEF_LEAK_RE.finditer(body)})
    if hits:
        problems.append(f'Argo-internal marker(s) present: {hits}')

    if problems:
        print('  ✗ MISSION-BRIEF SLOT GUARD FAILED — .tropo-studio/mission-brief.md is not a '
              'generic template:', file=sys.stderr)
        for p in problems:
            print(f'      - {p}', file=sys.stderr)
        print('    Step 7.1 must source vault/templates/root-docs/mission-brief.template.md. '
              'Argo\'s real brief ships only as a labelled example, never in the boot slot '
              '(task 2ffda37e defect #1).', file=sys.stderr)
        sys.exit(9)
    print('  ✓ Mission-brief slot guard: .tropo-studio/mission-brief.md is the generic '
          '<FILL: …> template (no Argo-internal content).')


def stage6_package_authority(activation_uid):
    """Resolve who authorised this package and refuse unless the legs settled.

    THE AC6-FINAL WELD (0a0a6777; A148 evt_a9360f18f56fe472_00000010 and
    _00000020). AC6 claims the package freeze refuses until every release leg
    is terminal or independently attested. Until now that claim was true of a
    run walking the release graph and false of anyone invoking this script,
    which is the only way a package is actually produced. The gate lived in a
    library that only its own tests called.

    Everything here happens BEFORE a single zip byte exists, because a refusal
    after the artefact is a refusal that already cost something.

    Deliberately no fallback. There is no "if we cannot resolve a run, carry
    on" branch and no caller boolean that turns this off: an omission-based
    bypass would make the gate advisory, and a gate a caller can decline is
    not a gate. That is A148's Q2 answer and it is stricter than what I
    proposed.
    """
    runtime = _load_pipeline_runtime()
    identity = release_package.resolve_release_run(
        activation_uid,
        Path(tropo_roots.VAULT_DIR) / "files",
        Path(tropo_roots.VAULT_DIR) / "pipeline-runs",
    )

    # A148 Q5: recompute the fan-in digest canonically from the lock's
    # IMMUTABLE manifest and compare. One source plus an integrity check, not
    # two sources — the rows are never read from live dev-specs, so a spec
    # edited since the lock cannot change what this package claims to contain.
    _verify_fan_in_against_manifest(identity, runtime)

    run_entry = runtime.read_vault_entry(identity.run_uid) or {}
    run_folder = str((run_entry.get("frontmatter") or {}).get("run_folder") or "")
    if not run_folder:
        raise release_package.PackageRefusal(
            f"release run {identity.run_uid} declares no run_folder, so its "
            f"leg events cannot be read and the wait cannot be evaluated"
        )
    events = runtime.read_events(Path(tropo_roots.STUDIO_ROOT) / run_folder)

    # One definition, two readers: the same derivation the engine uses at the
    # wait step. A package must not be able to disagree with the engine about
    # whether the legs settled.
    leg_records = release_legs.leg_records_from_events(events)
    states = release_legs.assert_ready_to_freeze(
        identity.run_uid, leg_records, runtime.read_vault_entry
    )
    return identity, states


def _verify_fan_in_against_manifest(identity, runtime):
    """Prove the membership recorded at lock time has not moved since.

    The manifest is the lock's own immutable artefact. Reading the rows from
    there and recomputing gives one source and a proof of integrity; reading
    them from the current dev-specs would give two sources, and the newer one
    would silently win.
    """
    plan = runtime.read_vault_entry(identity.plan_uid) or {}
    ref = str((plan.get("frontmatter") or {}).get("fan_in_manifest_ref") or "")
    if not ref:
        raise release_package.PackageRefusal(
            f"release-plan {identity.plan_uid} names no fan_in_manifest_ref, "
            f"so the digest it recorded cannot be checked against anything"
        )
    path = Path(tropo_roots.STUDIO_ROOT) / ref
    if not path.is_file():
        raise release_package.PackageRefusal(
            f"fan-in manifest for {identity.plan_uid} does not resolve at "
            f"{path}; refusing rather than trusting a digest with no manifest"
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise release_package.PackageRefusal(
            f"fan-in manifest at {path} does not parse: {exc}"
        ) from exc
    release_package.verify_fan_in_digest(identity, manifest.get("rows") or [])


def _load_pipeline_runtime():
    """The engine, imported by path. Its event reader is the one we reuse."""
    path = os.path.join(tropo_roots.VAULT_DIR, 'tools', '9e7003b1.py')
    spec = importlib.util.spec_from_file_location('_pipeline_runtime', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules['_pipeline_runtime'] = module
    spec.loader.exec_module(module)
    return module


def stage6_freeze_package(identity, zip_file, new_version, actor='tropo-build-release.py'):
    """Hash the shipped bytes once and record the one package identity.

    The digest is taken from the final zip on disk — not the build directory,
    not a value a caller supplies. Every AC7 instrument afterwards names its
    subject by this number, so a digest sourced from anything else makes all
    four of them describe an artefact that never shipped.
    """
    package_sha256 = release_package.hash_final_zip(Path(zip_file))
    runtime = _load_pipeline_runtime()
    run_entry = runtime.read_vault_entry(identity.run_uid) or {}
    run_folder = str((run_entry.get("frontmatter") or {}).get("run_folder") or "")
    events = runtime.read_events(Path(tropo_roots.STUDIO_ROOT) / run_folder)

    existing = release_package.active_frozen_payload(events, identity.run_uid)
    if not release_package.reconcile_existing_freeze(
        existing, package_sha256, identity.run_uid
    ):
        print(f'  ✓ package already frozen at {package_sha256[:12]}… (idempotent retry)')
        return package_sha256

    payload = release_package.package_frozen_payload(
        identity, Path(zip_file), package_sha256, version=new_version
    )
    # A148 addendum item 1: package_frozen is a RUN-LOCAL event and belongs on
    # the runtime's own writer, not a subprocess to tropo-emit-event.py. The
    # subprocess call was wrong three ways at once — it passed --run-folder,
    # which is not a flag that exists; it omitted --lifecycle, which is
    # required; and it hardcoded --as talos, so identical bytes would carry
    # different provenance depending on who ran the build.
    #
    # It would have failed on every real invocation. It never did here because
    # nothing had yet driven this path end to end, which is precisely the
    # helper-green gap this whole NO-GO is about.
    #
    # The tool is the author: a1b8c2d4 is this script's registered uid, and it
    # is the same whoever is at the keyboard.
    try:
        event = runtime.make_event(
            release_package.PACKAGE_FROZEN_EVENT,
            BUILD_TOOL_UID,
            actor_label=BUILD_TOOL_SOURCE,
            data=payload,
            trace_id=identity.run_uid,
        )
        runtime.append_event(Path(tropo_roots.STUDIO_ROOT) / run_folder, event)
    except Exception as exc:  # noqa: BLE001 -- a package with no identity cannot ship
        raise release_package.PackageRefusal(
            f"package_frozen could not be recorded for run {identity.run_uid}: "
            f"{exc}. A package whose identity was never recorded cannot be "
            f"verified or published, so this refuses rather than leaving a zip "
            f"nobody can bind a receipt to."
        ) from exc
    print(f'  ✓ package_frozen recorded: {package_sha256[:12]}… '
          f'(run {identity.run_uid}, {len(states_summary(payload))} bindings)')
    return package_sha256


def states_summary(payload):
    """The identity fields carried on the freeze, for the operator line."""
    return [key for key in payload if key.endswith('_uid') or key == 'fan_in_digest']


def step_11_zip_and_upload(build_dir, new_version, dist_dir, dry_run=False):
    """Step 11 — Zip ONLY (Release Coupling, fbe50871). The upload (Supabase zip +
    update-manifest) that used to live here moved to tropo-publish-release.py --fire —
    the build now ends fully private, on every channel, by construction. Name kept
    (not renamed to step_11_zip) to minimize call-site churn; the docstring is the
    source of truth for what it actually does now."""
    print('Step 11 — Zip (private; upload moved to tropo-publish-release.py --fire)')
    if dry_run:
        print('  --dry-run: skipping zip')
        return

    zip_path_base = os.path.join(dist_dir, f"tropo-os-v{new_version}")
    shutil.make_archive(zip_path_base, 'zip', build_dir)
    zip_file = f"{zip_path_base}.zip"
    print(f'  ✓ Zipped to {zip_file}')
    print('  PUBLISH: not-staged — nothing left this machine. '
          'Run tropo-publish-release.py to stage, then --fire to publish.')


#: Wall-clock ceiling for the studio validator-debt ratchet subprocess. Named
#: because it has been bumped three times and its test asserted a copy of the
#: literal, so the third bump (420 -> 1080, metis-g105 07f13225) left the test
#: red on the release path it was bumped for. One definition, two readers.
STUDIO_DEBT_RATCHET_TIMEOUT_S = 1080

#: Wall-clock ceiling for the Step 0 full vault rebuild. The retrospective named
#: this one as "300s vs 25min" — a limit set when the rebuild was fast, left
#: alone while the vault grew, and finally discovered by a build that could never
#: pass its own first step. Bumped 300 -> 2400 by metis-g105 on the strength of a
#: 24m22s measurement.
#:
#: RE-MEASURED 2026-08-09 (talos-t40): 278.3s on this machine before velocity
#: item 1, and 204.4s after. That is 7x below the measurement this ceiling was
#: sized against, on the same command and the same vault, which is a machine
#: difference nobody has reconciled yet — see the open question with Metis.
#: The ceiling stays at 2400 deliberately: it costs nothing when the rebuild is
#: healthy, and the failure it guards against is a build hanging unattended.
#: Do not lower it on the strength of the faster machine alone.
STEP0_VAULT_REBUILD_TIMEOUT_S = 2400


_VALIDATOR_SNAPSHOT_EXCLUDES = frozenset({
    '.git', '__pycache__', '.pytest_cache', 'node_modules',
    'archive', 'recycle', 'tropo-releases',
})


def _validator_tree_snapshot(root):
    digest = hashlib.sha256()
    count = 0
    root_path = Path(root).resolve()
    for path in sorted(root_path.rglob('*'), key=lambda item: item.as_posix()):
        relative = path.relative_to(root_path)
        if any(part in _VALIDATOR_SNAPSHOT_EXCLUDES for part in relative.parts):
            continue
        if path.is_symlink():
            raw = os.readlink(path).encode('utf-8')
            kind = b'L'
        elif path.is_file():
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            kind = b'F'
        else:
            continue
        digest.update(kind)
        digest.update(relative.as_posix().encode('utf-8'))
        digest.update(b'\0')
        digest.update(hashlib.sha256(raw).digest())
        count += 1
    return digest.hexdigest(), count


def _write_validation_receipt(receipt):
    path = (
        tropo_roots.STUDIO_ROOT
        / '.tropo-studio'
        / 'locks'
        / 'build-validation-receipt.json'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f'.{path.name}.tmp')
    staged.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    os.replace(staged, path)
    return path


def _run_post_rebuild_validation(attempt_id):
    """Run the one authoritative validator after rebuild and seal its receipt."""
    ratchet = os.path.join(
        tropo_roots.VAULT_DIR,
        'tools',
        'tests',
        'test_post_migration_release_clean.py',
    )
    print(
        'Step 0a — Authoritative post-rebuild validation '
        f'(attempt={attempt_id}):'
    )
    started = datetime.now().astimezone().isoformat()
    try:
        result = subprocess.run(
            [sys.executable, ratchet],
            capture_output=True,
            text=True,
            cwd=tropo_roots.STUDIO_ROOT,
            timeout=STUDIO_DEBT_RATCHET_TIMEOUT_S,
        )
        output = (result.stdout or '') + (result.stderr or '')
        returncode = result.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        output = f'validator ratchet could not run: {exc}'
        returncode = 2
    if output:
        print('  ' + output.strip().replace('\n', '\n  '))
    match = re.search(
        r'Result:\s*(\d+) passed,\s*(\d+) failed',
        output,
    )
    tree_sha256, tree_file_count = _validator_tree_snapshot(
        tropo_roots.STUDIO_ROOT
    )
    receipt = {
        'schema_version': 1,
        'attempt_id': attempt_id,
        'phase': 'post-rebuild',
        'started_at': started,
        'finished_at': datetime.now().astimezone().isoformat(),
        'validator_returncode': returncode,
        'summary': (
            {
                'passed': int(match.group(1)),
                'failed': int(match.group(2)),
            }
            if match else None
        ),
        'tree_sha256': tree_sha256,
        'tree_file_count': tree_file_count,
        'output_sha256': hashlib.sha256(output.encode('utf-8')).hexdigest(),
        'output_tail': '\n'.join(output.splitlines()[-40:]),
        'clear': returncode == 0 and match is not None,
    }
    receipt_path = _write_validation_receipt(receipt)
    print(
        f'  Validation receipt: {receipt_path} '
        f'(tree={tree_sha256[:12]}…, files={tree_file_count}, '
        f'clear={receipt["clear"]})'
    )
    if not receipt['clear']:
        print(
            '  ✗ Build REFUSED — post-rebuild validator/ratchet did not '
            'produce a clear, parseable receipt.'
        )
    return receipt


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    # Parse args
    bump_type = None
    target_version = None
    activation_uid = None
    walk_answer = None
    for i, arg in enumerate(sys.argv):
        if arg == '--bump' and i + 1 < len(sys.argv):
            bump_type = sys.argv[i + 1]
        elif arg == '--target' and i + 1 < len(sys.argv):
            target_version = sys.argv[i + 1]
        elif arg == '--activation-uid' and i + 1 < len(sys.argv):
            activation_uid = sys.argv[i + 1]
        elif arg == '--walk-answer' and i + 1 < len(sys.argv):
            walk_answer = sys.argv[i + 1]

    if not bump_type and not target_version:
        print('Usage: python3 build-release.py (--bump <patch|feature|release> | --target <X.Y.Z>) '
              '[--dry-run] [--force] [--offline]')
        print('')
        print('  --bump <type>      Compute target version from current .tropo/version.md + bump type.')
        print('  --target <X.Y.Z>   Build a specific version explicitly. Use when ship + on-disk-build')
        print('                     split across sessions and .tropo/version.md is already at the target')
        print('                     (vela-v46 2026-05-16 addition per Mike-V46 captain-mode authorization;')
        print('                     fixes the v1.34.0 packaging gap where Argus updates version.md at')
        print('                     substrate ship but --bump expects source to LAG one cycle behind build).')
        print('  --offline          Skip the Step 0.5 publish-state pre-flight if the remote is')
        print('                     unreachable (Release Coupling, fbe50871) — proceeds with')
        print('                     publish_state recorded UNKNOWN in build provenance, never silently')
        print('                     assumed in-sync. Build ends fully private regardless; publish via')
        print('                     tropo-publish-release.py when ready to go live.')
        print('  --walk-answer y|n  Explicit cold-walk answer for headless builds; '
              f'env fallback: {WALK_ANSWER_ENV}. Non-interactive `no` refuses.')
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
    # ── AC6-final: package-entry authority + the release-leg wait ────────────
    # Before anything is built, not after. A refusal here costs nothing; the
    # same refusal after the zip is a refusal that already produced an
    # artefact somebody has to reason about (254a360b).
    _stage6_identity = None
    if not DRY_RUN:
        try:
            _stage6_identity, _stage6_states = stage6_package_authority(activation_uid)
            print(f'  ✓ release run {_stage6_identity.run_uid} resolved; legs settled '
                  f'({", ".join(s.leg + ":" + s.basis for s in _stage6_states)})\n')
        except release_package.PackageRefusal as exc:
            print(f'REFUSED: {exc}')
            print(f'  No package was produced. Re-run after correcting: '
                  f'python3 vault/tools/tropo-build-release.py '
                  f'--activation-uid {activation_uid or "<uid>"} '
                  f'{"--bump " + bump_type if bump_type else "--target " + str(target_version)}')
            sys.exit(1)
        except Exception as exc:  # noqa: BLE001 -- the wait refuses loudly, never warns
            print(f'REFUSED: release legs are not settled for this package: {exc}')
            print(f'  No package was produced. Settle or attest the open leg, '
                  f'then re-run: python3 vault/tools/tropo-build-release.py '
                  f'--activation-uid {activation_uid or "<uid>"} '
                  f'{"--bump " + bump_type if bump_type else "--target " + str(target_version)}')
            sys.exit(1)

    if not DRY_RUN:
        try:
            _key = require_release_authorization(activation_uid, 'produce-release-folder')
            print(f'  ✓ Pipeline Activation Key verified (activation {activation_uid}, '
                  f'fingerprint {_key.get("fingerprint","")[:12]}…)\n')
        except ReleaseAuthorizationError as e:
            # Attested-build fallback (argus-a129-attested-build-gate spec, Mike-approved
            # 2026-07-11): an attested-close release (8c8ca68c-class) has no pipeline-run to
            # key against — the pipeline-key path will ALWAYS refuse it, correctly. This is a
            # SEPARATE, narrower authorization source for THIS gate only; it never touches the
            # outward ship gate below (require_release_authorization + require_human_signoff
            # stays the sole path to a public push). Resolves by --target, not --activation-uid
            # — attested builds have no run.
            _attested = None
            if target_version:
                try:
                    _attested = attested_build_authorization(target_version)
                except ReleaseAuthorizationError:
                    _attested = None
            if _attested:
                print(f'  ✓ Attested-Build Authorization verified (release {_attested["release_uid"]}, '
                      f'version {_attested["version"]}, attestation {_attested["attestation_uid"]})\n')
            else:
                print(f'  ✗ Build REFUSED — no valid Pipeline Activation Key: {e}', file=sys.stderr)
                print('    A release is produced through the pipeline runtime, which mints the key', file=sys.stderr)
                print('    at the produce-release-folder gate. Drive the cycle via pipeline-runtime.py —', file=sys.stderr)
                print('    do not invoke build-release standalone. (No key, no build.)', file=sys.stderr)
                sys.exit(3)

    # ── Step 0.5 — Publish-state pre-flight (Release Coupling, fbe50871) ─────
    _publish_state_provenance = {"publish_state": "UNKNOWN"}
    if not DRY_RUN:
        _publish_state_provenance = step_0_5_publish_state_preflight()
        print()

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
    rebuild_path = os.path.join(tropo_roots.VAULT_DIR, 'tools', 'tropo-rebuild-vault.py')  # rebuild-vault (v1.56 migrated)
    validation_attempt_id = uuid.uuid4().hex
    try:
        rebuild_result = subprocess.run(
            [
                sys.executable,
                rebuild_path,
                '--vault-path',
                tropo_roots.STUDIO_ROOT,
                '--apply',
                '--skip-validator',
                '--validator-run-id',
                validation_attempt_id,
            ],
            capture_output=True, text=True, cwd=tropo_roots.STUDIO_ROOT,
            timeout=STEP0_VAULT_REBUILD_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        # 300s was set when the vault was a fraction of its current size; the full rebuild
        # MEASURED 24m22s on 2026-08-08 (4,900+ files, belt + three catalogs). 2400s gives
        # headroom without letting a genuine hang run unbounded. (metis-g105, v1.86 stage)
        print(f'  ✗ Substrate rebuild timed out after {STEP0_VAULT_REBUILD_TIMEOUT_S}s. Investigate vault size or rebuild regression.')
        sys.exit(2)
    except FileNotFoundError:
        print(f'  ✗ rebuild-vault.py not found at {rebuild_path}. v1.30.0 substrate missing.')
        sys.exit(2)

    if rebuild_result.returncode != 0:
        tail = '\n'.join(rebuild_result.stdout.splitlines()[-30:])
        print(tail)
        print('\n  ✗ Build REFUSED — rebuild-vault.py returned non-zero.')
        print('    Vault rebuild is always-run; this failure is NOT bypassable via')
        print('    TROPO_SKIP_ENFORCEMENT_GATE=1 (substrate quality is separate from')
        print('    capability-membership enforcement).')
        print('    The authoritative validator runs only after rebuild succeeds.')
        sys.exit(1)

    summary = '\n'.join(rebuild_result.stdout.splitlines()[-10:])
    print('  ' + summary.replace('\n', '\n  '))
    print('  ✓ Vault rebuild PASS\n')
    validation_receipt = _run_post_rebuild_validation(
        validation_attempt_id
    )
    if not validation_receipt['clear']:
        sys.exit(1)

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
        # validate-capability-membership.py migrated to vault/tools/tropo-validate-capability-membership.py;
        # legacy .tropo/scripts/ path no longer exists. Use canonical vault/tools/ path.
        validator_path = os.path.join(tropo_roots.VAULT_DIR, 'tools',
                                      'tropo-validate-capability-membership.py')
        try:
            result = subprocess.run(
                ['python3', validator_path],
                capture_output=True, text=True, cwd=tropo_roots.STUDIO_ROOT, timeout=600
            )
        except subprocess.TimeoutExpired:
            print('  ✗ Validator timed out after 600s. Investigate vault size or validator regression.')
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
    # validate-canonical-l0.py migrated to vault/tools/tropo-validate-canonical-l0.py.
    l0_validator_path = os.path.join(tropo_roots.VAULT_DIR, 'tools',
                                     'tropo-validate-canonical-l0.py')
    try:
        l0_result = subprocess.run(
            ['python3', l0_validator_path, '--state', 'active',
             '--extraction-scope', 'ship'],
            capture_output=True, text=True, cwd=tropo_roots.STUDIO_ROOT, timeout=30
        )
    except subprocess.TimeoutExpired:
        print('  ⚠ L0 validator timed out after 30s. Continuing build (non-blocking warning).')
        l0_result = None
    except FileNotFoundError:
        print(f'  ⚠ L0 validator not found at {l0_validator_path}. Continuing build (non-blocking warning).')
        l0_result = None

    if l0_result is not None:
        if l0_result.returncode == 0:
            print('  ✓ Canonical L0 verification PASS '
                  '(ship-scoped active L0 set matches canonical).\n')
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
        _scripts_lib = tropo_roots.STUDIO_ROOT / '.tropo' / 'scripts'
        import sys as _sys
        if str(_scripts_lib) not in _sys.path:
            _sys.path.insert(0, str(_scripts_lib))
        from lib.release_validators import check_cascade_pipelines_retired
        # Find the active dev-spec for this activation (from dev-spec index or env)
        _dev_spec_uid = os.environ.get('DEV_SPEC_UID', '')
        if _dev_spec_uid and re.match(r'^[0-9a-f]{8}$', _dev_spec_uid):
            print('Step 1c — v1.59 Lane B: cascade-pipelines-retired gate:')
            _casc_findings, _all_retired = check_cascade_pipelines_retired(
                tropo_roots.STUDIO_ROOT, _dev_spec_uid
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

    if not DRY_RUN:
        receipt_dir = tropo_roots.RELEASES_DIR / f'v{new_version}'
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / 'build-validation-receipt.json'
        receipt_path.write_text(
            json.dumps(validation_receipt, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        print(f'  Post-rebuild validation receipt copied to {receipt_path}')

    _pre_target_publish_state = _publish_state_provenance.get("publish_state")
    _publish_state_provenance = target_publish_state_provenance(
        _publish_state_provenance, new_version
    )
    if _publish_state_provenance.get("publish_state") != _pre_target_publish_state:
        print(
            f'  Target publish-state: {_publish_state_provenance["publish_state"]} '
            f'(latest published v{_publish_state_provenance.get("latest_published")})'
        )

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

    # Step 3e: Copy vault/updates/ wholesale (update apply state machine — finding G2, Gate 2)
    step_3e_copy_vault_updates(build_dir)

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
    validate_manifest_basic(manifest_entries, tropo_roots.STUDIO_ROOT)

    print()
    print('Phase 3 — Build Output (manifest-driven):')
    build_from_manifest(build_dir, manifest_entries)
    step_3f_remove_per_studio_boot_derivations(build_dir)
    step_3g_write_update_source(build_dir)

    # v1.12.1 transitional: RELEASE-NOTES.md is a generated artifact, not a
    # ship-artifact (per arch-spec 747c33c9 §1 Thesis "RELEASE-NOTES is generated
    # per release"). Lives at argo-os/RELEASE-NOTES.md (relocated from
    # argo-os/starter/RELEASE-NOTES.md at v1.12.1 ship). Copy to build root.
    # v1.12.2 implements proper RELEASE-NOTES.md generation step OR authors a
    # ship-artifact entry with explicit generated-artifact handling.
    rn_src = os.path.join(tropo_roots.STUDIO_ROOT, 'RELEASE-NOTES.md')
    if os.path.exists(rn_src):
        rn_dst = os.path.join(build_dir, 'RELEASE-NOTES.md')
        copy_file(rn_src, rn_dst, DRY_RUN)
        print(f'  RELEASE-NOTES.md: copied from argo-os/RELEASE-NOTES.md to build root')
    else:
        print(f'  ⚠ RELEASE-NOTES.md not found at {rn_src} — release ships without notes')
    # CHANGELOG.md (public user-facing changelog, Keep a Changelog format). Studio source-of-truth.
    # The ship gate (require_release_authorization with version) enforces this file is current
    # before upload is authorized (Metis G83 anti-drift gate, v1.74).
    cl_src = os.path.join(tropo_roots.STUDIO_ROOT, 'CHANGELOG.md')
    if os.path.exists(cl_src):
        cl_dst = os.path.join(build_dir, 'CHANGELOG.md')
        copy_file(cl_src, cl_dst, DRY_RUN)
        print(f'  CHANGELOG.md: copied from argo-os/CHANGELOG.md to build root')
    else:
        print(f'  ⚠ CHANGELOG.md not found at {cl_src} — ship gate will block until it exists')
    # D2 — folder-mirror AGENTS.md + package.json (dev-spec f8b51f4d D2, v1.74).
    # These files exist in the studio but the manifest-driven Phase 3 doesn't ship them.
    # channels/AGENTS.md, context/AGENTS.md, operating-agreement/AGENTS.md: required by the
    # AGENTS_MD_REQUIRED_DIRS check in the validator; their absence causes FAIL in release.
    # package.json: ships so a downloader's `npm test` (the studio health check) actually runs.
    # Each entry is (source_rel_path, dest_dir[, dest_name]). dest_name defaults to
    # the source basename; supply it explicitly when the SHIPPED filename must differ
    # from the source filename (source ≠ dest).
    _d2_files = [
        ('package.json', ''),                                    # root → root
        (os.path.join('vault', 'templates', 'agents-skeleton', 'AGENTS.md'),
         'agents'),
        (os.path.join('channels', 'AGENTS.md'), 'channels'),
        (os.path.join('context', 'AGENTS.md'), 'context'),
        (os.path.join('operating-agreement', 'AGENTS.md'), 'operating-agreement'),
        # NOTE: the mission-brief boot slot is seeded AFTER step_7_create_vault_skeleton
        # (see below), NOT here — its destination now lives inside .tropo-studio/, which
        # step_7 rmtree's + recreates, so a copy placed in this pre-skeleton loop would be
        # clobbered. Relocated from context/ per task 2ffda37e defect #4 (Mike-approved).
    ]
    for _entry in _d2_files:
        rel_path, dest_dir = _entry[0], _entry[1]
        dest_name = _entry[2] if len(_entry) > 2 else os.path.basename(rel_path)
        src = os.path.join(tropo_roots.STUDIO_ROOT, rel_path)
        if os.path.exists(src):
            dst_folder = os.path.join(build_dir, dest_dir) if dest_dir else build_dir
            if not DRY_RUN:
                os.makedirs(dst_folder, exist_ok=True)
            dst = os.path.join(dst_folder, dest_name)
            copy_file(src, dst, DRY_RUN)
            print(f'  D2: {rel_path} → build root/{os.path.join(dest_dir, dest_name) if dest_dir else dest_name}')
        else:
            print(f'  ⚠ D2: {rel_path} not found at {src} — skipped')

    # Step 7: .tropo-studio/ skeleton
    step_7_create_vault_skeleton(build_dir)

    # Step 7.1 — Seed the mission-brief boot slot (task 2ffda37e defects #1+#4).
    # Ship the GENERIC <FILL> TEMPLATE, not Argo's real internal mission brief, into the
    # authoritative boot slot .tropo-studio/mission-brief.md (activation playbook Step 2.3
    # + Tier 2 read at every boot; relocated from context/ per Mike's decision, defect #4).
    # MUST run AFTER step_7_create_vault_skeleton: that step rmtree's + recreates
    # .tropo-studio/ from the skeleton, so a copy placed in the pre-skeleton D2 loop would
    # be clobbered. Sourcing the single canonical template (no content duplication) keeps
    # the boot read resolvable while shipping only <FILL: …> placeholders. Argo's real
    # brief (.tropo-studio/mission-brief.md, extraction_scope: argo-reference) never ships;
    # it ships separately as the labeled example (vault/templates/examples/mission-brief.example.md)
    # — do not touch that.
    _mb_src = os.path.join(tropo_roots.VAULT_DIR, 'templates', 'root-docs', 'mission-brief.template.md')
    _mb_dst = os.path.join(build_dir, '.tropo-studio', 'mission-brief.md')
    if not os.path.exists(_mb_src):
        raise SystemExit(
            f'Mission-brief template not found at {_mb_src}.\n'
            f'The boot slot .tropo-studio/mission-brief.md is a Required:Yes read at Step 2.3 of the\n'
            f'activation playbook (99341618) and a Tier-2 read-at-every-boot (cf8c3be9) — shipping a box\n'
            f'without it makes every customer agent hit a missing required read on first boot.\n'
            f'Path-base / tier-reachability failure — halting rather than silent-skipping, '
            f'per ADR-032 amendment 2026-04-19.'
        )
    copy_file(_mb_src, _mb_dst, DRY_RUN)
    print(f'  Mission-brief slot: template → build root/.tropo-studio/mission-brief.md')

    # Step 8: Version file
    step_8_write_version(build_dir, new_version)

    # Step 8.1 — Record Step 0.5's publish-state pre-flight result into build provenance
    # (Release Coupling, fbe50871: "unreachable... recorded in build provenance as
    # publish_state UNKNOWN"). tropo-publish-release.py's STAGE step reads this.
    if not DRY_RUN:
        _prov_dir = os.path.join(tropo_roots.RELEASES_DIR, f'v{new_version}')
        os.makedirs(_prov_dir, exist_ok=True)
        _prov_path = os.path.join(_prov_dir, 'build-provenance.json')
        with open(_prov_path, 'w') as f:
            json.dump({
                "version": new_version,
                "built_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
                **_publish_state_provenance,
            }, f, indent=2)
        print(f'  Build provenance: {_prov_path} (publish_state={_publish_state_provenance.get("publish_state")})')

    # Step 8b: Version stamping across stranger-facing files (v1.3.1 D1.1)
    step_8b_stamp_versions(build_dir, new_version)

    # Step 9: Manifest
    file_count = step_9_generate_manifest(build_dir, new_version)

    # Step 9b: Regenerate 00-tropo-nav/ from the SHIPPED ledger (v1.5 S2)
    # Ensures shipped 00-tropo-nav reflects the SHIPPED ledger, not the source-vault state.
    # Closes Mike Maziarz cold-boot finding 2026-05-03 ("you did ship a 00-tropo-nav/ that was stale").
    step_9b_regenerate_tropo_nav(build_dir)

    # Step 9c: Generate the vendor-ref manifest (S1, v1.80) — the box now carries
    # data for customer-mode classification instead of relying on guesswork.
    step_9c_generate_vendor_ref_manifest(build_dir, new_version)

    # Step 10: Sanitize the Studio identity
    step_10_sanitize_argo_identity(build_dir)
    # The in-box gates below still need a working index, so the generation
    # survives until the final freeze before the zip. It is NOT sealed: a seal
    # is evidence about surfaces this package does not ship (evt 114), and the
    # recipient seals the generation its own first rebuild creates.

    # Step 10.5: Release Test-Harness — mechanical regression GATE (new layer; brief f13cc214,
    # Mike-A115 2026-06-17). A release that fails its own regression does NOT ship. Runs the
    # self-contained harness against the produced+sanitized artifact; FAIL → refuse (no zip,
    # no upload). Composes with the Pipeline Activation Key: a release that can't pass its own
    # checks can't be shipped. (Mechanical layer only — the guided/stranger walk is dispatched
    # by the reasoning layer / run by a human; this is the deterministic gate.)
    if not DRY_RUN:
        print('Step 10.5 — Release Test-Harness (mechanical regression gate):')
        _harness = os.path.join(tropo_roots.STUDIO_ROOT, '.tropo', 'scripts', 'test-harness-check.py')
        if not os.path.exists(_harness):
            print(f'  ⚠ Test-harness not found at {_harness} — gate SKIPPED (surface this; do not treat as pass).')
        else:
            try:
                _hr = subprocess.run(['python3', _harness, '--release-dir', build_dir],
                                     capture_output=True, text=True, cwd=tropo_roots.STUDIO_ROOT, timeout=120)
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

    # Step 10.5a — S2 (v1.80): Shipped self-test passes in the box.
    # S2 (cbe4f7bd R11 class, dev-spec be1979b6): the ship gate runs the shipped self-test surface
    # INSIDE the built box pre-ship and verifies registry-row regeneration actually landed by reading
    # the box, not just checking the call ran. A failing shipped test refuses the build.
    # Folds the un-archived R11 item (cbe4f7bd).
    if not DRY_RUN:
        print('Step 10.5a — S2: Shipped self-test in-box gate (v1.80 S2):')
        _box_test = os.path.join(build_dir, 'vault', 'tools', 'tropo-test.py')
        if not os.path.exists(_box_test):
            print(f'  ✗ Build REFUSED — tropo-test.py not found in built box at {_box_test}. '
                  f'The shipped test surface must be present in the box.', file=sys.stderr)
            sys.exit(4)
        else:
            try:
                _tr = subprocess.run(['python3', _box_test, '--quick'],
                                     capture_output=True, text=True, cwd=build_dir,
                                     timeout=300, env={**os.environ, 'VAULT_ROOT': build_dir})
                _tr_out = (_tr.stdout or '') + (_tr.stderr or '')
                print('  ' + _tr_out.strip()[:500].replace('\n', '\n  '))
                # v0.1 fix (vela-v63, 2026-07-05): tropo-test.py's own exit-code contract is
                # 0=GREEN, 1=YELLOW (passes, warnings present), 2=RED (real failures, ship-blocker).
                # This gate was refusing on ANY nonzero code, including YELLOW — meaning a release
                # with zero test failures but any warning could never pass. Only RED (>=2) blocks.
                if _tr.returncode >= 2:
                    print('\n  ✗ Build REFUSED — shipped self-test (tropo-test.py) FAILED (RED) in the built box.', file=sys.stderr)
                    print('    A release whose own test surface fails inside the box does not ship (S2).', file=sys.stderr)
                    sys.exit(4)
                elif _tr.returncode == 1:
                    print('  ⚠ Shipped self-test in-box YELLOW (warnings present, 0 failures) — proceeding\n')
                else:
                    print('  ✓ Shipped self-test in-box PASS (GREEN)\n')
            except subprocess.TimeoutExpired:
                print('  ✗ Shipped self-test timed out after 300s. Investigate.', file=sys.stderr)
                sys.exit(4)

        # Verify registry-row regeneration actually landed (read the box, not just check the call ran)
        _registry = os.path.join(build_dir, 'vault', '.tropo-studio', 'registries', 'subsystem-registry.jsonl')
        if not os.path.exists(_registry):
            _registry = os.path.join(build_dir, '.tropo-studio', 'registries', 'subsystem-registry.jsonl')
        if os.path.exists(_registry):
            import json as _json_s2
            _rows = [l for l in open(_registry).read().splitlines() if l.strip()]
            if len(_rows) == 0:
                print('\n  ✗ Build REFUSED — subsystem-registry.jsonl in built box has 0 rows. '
                      'Registry-row regeneration did not land; the box is incomplete (S2).', file=sys.stderr)
                sys.exit(4)
            print(f'  ✓ subsystem-registry.jsonl: {len(_rows)} row(s) in box — regeneration confirmed')
        else:
            print(f'  ⚠ subsystem-registry.jsonl not found in box at {_registry} — '
                  f'registry-row verification skipped (non-blocking at v1.80; surface for next build)')

    # Step 10.7 — Covenant Gate: THE FLOOR TEST as a BLOCKING build gate (ADR-049 layer 2;
    # dev-spec fc4874f4, Mike-approved lock-amendment 2026-07-01 "Let's build. Let's go!").
    # A release whose update path would violate zero-user-churn cannot be built, and
    # therefore cannot ship. Same posture as Step 10.5 (mechanical regression gate):
    # hard sys.exit on failure, unconditional — this blocks the BUILD itself, not any
    # downstream publish action. Governance wrapper: vault/playbooks/d2efcac9.md.
    if not DRY_RUN:
        print('Step 10.7 — Covenant Gate (THE FLOOR TEST, ADR-049 layer 2):')
        _floor_test = os.path.join(tropo_roots.VAULT_DIR, 'tools', 'tests', 'test_clean_update_floor.py')
        if not os.path.exists(_floor_test):
            print(f'  ✗ Build REFUSED — floor test not found at {_floor_test}. '
                  f'The covenant gate cannot be skipped by absence.', file=sys.stderr)
            sys.exit(7)

        # Sub-step 1: gauntlet — plant a covenant violation, assert the gate catches it.
        # If the gate can't catch a planted violation, it's not a real gate; refuse to
        # trust its PASS on the real run below.
        _gr = subprocess.run(['python3', _floor_test, '--gauntlet'],
                              capture_output=True, text=True, cwd=tropo_roots.STUDIO_ROOT, timeout=60)
        print('  ' + (_gr.stdout or '').strip().replace('\n', '\n  '))
        if _gr.returncode != 0:
            print('\n  ✗ Build REFUSED — the covenant gate failed its own gauntlet '
                  '(a planted violation was NOT detected). The gate is not trustworthy '
                  'as-is; fix vault/tools/tests/test_clean_update_floor.py before shipping.',
                  file=sys.stderr)
            sys.exit(7)

        # Sub-step 2: the real run — must show zero user-file churn against the current
        # update path (namespace predicate + apply-update playbook Rules).
        _fr = subprocess.run(['python3', _floor_test],
                              capture_output=True, text=True, cwd=tropo_roots.STUDIO_ROOT, timeout=60)
        print('  ' + (_fr.stdout or '').strip().replace('\n', '\n  '))
        if _fr.returncode != 0:
            print('\n  ✗ Build REFUSED — THE FLOOR TEST failed: the update path would '
                  'touch user files. Fix the namespace predicate or the apply-update '
                  'playbook before shipping (ADR-049 covenant).', file=sys.stderr)
            sys.exit(7)
        print('  ✓ Covenant gate PASS — gauntlet caught the planted violation, real run shows zero churn.\n')

    # Step 10.8 — Generate the Update API static manifest (task f1d4b9e6; transport-lean
    # per the A122 walk: no live server, a stable-URL JSON manifest). Release Coupling
    # (fbe50871): GENERATION ONLY here — the manifest UPLOAD moved to tropo-publish-release.py
    # --fire, alongside the zip's own upload (the build ends fully private; nothing public
    # happens until Mike's hand is on the trigger). Generate-only runs here unconditionally
    # so the manifest is always current-as-of-build for local inspection.
    if not DRY_RUN:
        print('Step 10.8 — Update API manifest (generate-only; upload moved to --fire):')
        _manifest_gen = os.path.join(tropo_roots.VAULT_DIR, 'tools', 'tropo-generate-update-manifest.py')
        if os.path.exists(_manifest_gen):
            _mr = subprocess.run(['python3', _manifest_gen],
                                  capture_output=True, text=True, cwd=tropo_roots.STUDIO_ROOT, timeout=30)
            print('  ' + (_mr.stdout or '').strip().replace('\n', '\n  '))
            if _mr.returncode != 0:
                print(f'  ⚠ Manifest generation failed (exit {_mr.returncode}) — non-blocking; '
                      f'fire will need a fresh manifest before it can upload.')
        else:
            print(f'  ⚠ Manifest generator not found at {_manifest_gen} — skipped (non-blocking).')

    # Step 10.9 — S10 (v1.80): Release-news delivery watermark refresh.
    # The Tropo briefing surface (f6a967fd, agents/tropo/briefing-package/current-release-notes.md)
    # carries `release_version` + `last_delivered_version`. Every release must advance
    # `release_version` to the shipped version and reset `last_delivered_version: null` so
    # the release-liaison delivers the new notes to the Studio user. Prior gap: the v1.17.0
    # notes have been stale since v1.17.0 (last_delivered_version was never set, meaning the
    # surface was never refreshed by the pipeline). This wires the mechanical refresh so
    # "the studio's own news tells the truth too" (S10, dev-spec be1979b6 §S10).
    if not DRY_RUN:
        import re as _re
        _rn_path = os.path.join(tropo_roots.STUDIO_ROOT, 'agents', 'tropo', 'briefing-package', 'current-release-notes.md')
        if os.path.exists(_rn_path):
            try:
                _rn_text = open(_rn_path).read()
                _rn_new = _re.sub(
                    r'^(release_version:\s*).*$', f'\\g<1>v{new_version}', _rn_text, flags=_re.MULTILINE)
                _rn_new = _re.sub(
                    r'^(last_delivered_version:\s*).*$', '\\g<1>null', _rn_new, flags=_re.MULTILINE)
                if _rn_new != _rn_text:
                    open(_rn_path, 'w').write(_rn_new)
                    print(f'Step 10.9 — Release-news watermark refreshed: '
                          f'release_version=v{new_version}, last_delivered_version reset to null')
                else:
                    print(f'Step 10.9 — Release-news watermark: already at v{new_version} (no-op)')
            except Exception as _e:
                print(f'Step 10.9 — Release-news watermark update failed (non-blocking): {_e}')
        else:
            print(f'Step 10.9 — Release-news surface not found at {_rn_path} — '
                  f'non-blocking; refresh manually before ship.')

    # Step 11: Zip ONLY (Release Coupling, fbe50871) — the build ends fully private here.
    # Upload (Supabase zip + update-manifest) moved to tropo-publish-release.py --fire;
    # the outward-ship human-key gate (require_release_authorization with
    # require_human_signoff=True) moved there too — composition law 1: "one outward gate,
    # consulted twice (stage and fire)", never here. Build's own produce-gate check (above,
    # no require_human_signoff) is unchanged — that one only proves the pipeline ran, it
    # was never the outward gate.
    _build_clean = True
    if not DRY_RUN:
        # Step 10.6 — Stranger-walk gate (dev-spec 554624e5; v1.74) stays as the build's
        # OWN inherited in-build human touch (composition law 4 / AC-2: "a third in-build
        # touch, named and inherited, not re-litigated"). Always-ask; default YES;
        # override-to-skip recorded as honest provenance. No longer gates any upload here
        # (nothing uploads from build) — it gates whether THIS build is clean enough to stage.
        # Step 10.6 is a v1 artefact on the v2 release path. AC7 moves the
        # stranger walk into Verify as one of four instruments bound to the
        # frozen digest; running it here too would create a second definition
        # of "walk passed", and the older one would be the one that ran
        # against bytes that did not exist yet.
        if _stage6_identity is None:
            _cw_verdict_path = os.path.join(tropo_roots.RELEASES_DIR, f'v{new_version}', 'cold-walk-verdict.json')
            _last_cw_path = os.path.join(tropo_roots.RELEASES_DIR, 'last-cold-walk-release.json')
            _build_clean = step_10_6_cold_walk_gate(
                new_version,
                dist_dir,
                _cw_verdict_path,
                _last_cw_path,
                walk_answer=walk_answer,
            )
        else:
            _build_clean = True
            print('Step 10.6 — skipped on the v2 release path: the stranger walk '
                  'is an AC7 Verify instrument bound to the frozen package digest '
                  '(0a0a6777).')

        # RT1/RT2 ship-surface guard (argus-a118, v1.74): FAIL before the zip if the
        # release is missing its declared nav + workspace surfaces (finding 1ee11d09).
        assert_shipped_surfaces(build_dir)

        # One Home retirement guard (G2, Gate 2): FAIL before the zip if the dissolved
        # system/ tree still shipped, or if vault/updates/ didn't.
        assert_no_stale_system_dir(build_dir)

        # Mission-brief boot-slot guard (task 2ffda37e defect #1): FAIL before the zip if
        # the slot is missing or carries anything other than the generic <FILL: …> template.
        assert_mission_brief_slot(build_dir)

    # FINAL PORTABLE FREEZE (Argus, evt 112/113). The in-box mechanical gates
    # above RUN the box — they import its tools and may compose its index — so
    # they put bytecode, journals and a machine-local SQLite back after the
    # earlier purge. Purging once more immediately before the zip is what makes
    # the shipped bytes portable, and the manifest is regenerated afterwards so
    # it cannot list files the freeze removed.
    if not DRY_RUN:
        if step_10_2_purge_run_local_artifacts(build_dir):
            step_9_generate_manifest(build_dir, new_version)

    step_11_zip_and_upload(build_dir, new_version, dist_dir, DRY_RUN)

    # The one immutable package identity, taken from the bytes that shipped.
    if _stage6_identity is not None and not DRY_RUN:
        _zip_file = os.path.join(dist_dir, f'tropo-os-v{new_version}.zip')
        stage6_freeze_package(_stage6_identity, _zip_file, new_version)

    # Copy build to testing directory
    if not DRY_RUN:
        if os.path.exists(testing_dir):
            shutil.rmtree(testing_dir)
        shutil.copytree(build_dir, testing_dir, symlinks=True)

    # Step 12 — Durable pipeline closure (dev-spec c392d833, activation 63988cfb;
    # metis-g91 diagnosis 1d689277). WELD close-to-ship — the symmetric mirror of
    # ADR-052's lock→open. Opening is welded atomically (spec-lock → pipeline-activate
    # authors the activation root at state:active); closing was coupled to nothing, so
    # 93 roots piled up state:active (dev 81% closed / test 17% / doc 9%) and final_commit
    # had effectively no writer (16/180 hand-typed). Now that the release artifact is
    # produced, this invokes pipeline-runtime.py's close-out hook as a GUARANTEED side
    # effect: the cycle's own activation root flips state:active → state:archived and
    # gets final_commit=<ship SHA> stamped. No honor-system step to forget; a ship can
    # no longer leave its own root state:active.
    #   - Idempotent: safe if complete-workflow already closed the root (no re-stamp).
    #   - Per-root, never a global lock: parallel cycles stay legal (Mike-A94
    #     concurrency_model: independent) — it closes exactly THIS root at THIS ship.
    #   - Non-blocking: the artifact already exists; a close-out hiccup must not fail the
    #     build. The tropo-sweep-stale-roots.py backstop + the Rule-10 terminal-invariant
    #     validator check catch any root left state:active.
    #   - Skipped on --dry-run (no artifact) and when no --activation-uid was supplied
    #     (e.g. attested builds with no pipeline-run — the sweep backstop covers those).
    # P10 / A148 blocker 1: NOT on the v2 release path. Legacy close-out here
    # fires immediately after packaging — before Verify, before Publish, before
    # any receipt exists — so a v2 release would close its own substrate while
    # the artefact it just built is still unverified and unpublished. The
    # release closes from its public receipt or it does not close.
    #
    # Guarded by the same `_stage6_identity` predicate as step 10.6, so the two
    # cannot disagree about which path this build is on.
    if not DRY_RUN and activation_uid and _stage6_identity is None:
        print('Step 12 — Durable pipeline closure (weld close-to-ship; dev-spec c392d833):')
        try:
            _ship_sha = subprocess.run(['git', 'rev-parse', 'HEAD'],
                                       capture_output=True, text=True,
                                       cwd=tropo_roots.STUDIO_ROOT, timeout=15).stdout.strip()
        except Exception:
            _ship_sha = ''
        _runtime = os.path.join(tropo_roots.VAULT_DIR, 'tools', '9e7003b1.py')  # pipeline-runtime.py
        _co_cmd = ['python3', _runtime, '--activation-uid', activation_uid,
                   '--actor', 'tropo-build-release.py', 'close-out']
        if _ship_sha:
            _co_cmd += ['--final-commit', _ship_sha]
        try:
            _co = subprocess.run(_co_cmd, capture_output=True, text=True,
                                 cwd=tropo_roots.STUDIO_ROOT, timeout=60)
            _co_out = (_co.stdout or '').strip()
            if _co_out:
                print('  ' + _co_out.replace('\n', '\n  '))
            if _co.returncode != 0:
                print(f'  ⚠ close-out returned exit {_co.returncode} (non-blocking); '
                      f'root may remain state:active — sweep backstop + Rule-10 check will surface it. '
                      f'stderr: {(_co.stderr or "").strip()[:200]}')
            else:
                print(f'  ✓ Activation root closed + archived '
                      f'(final_commit={(_ship_sha[:12] + "…") if _ship_sha else "n/a"})\n')
        except Exception as _e:
            print(f'  ⚠ close-out invocation failed (non-blocking): {_e}')

    # EXIT + EVENT HONESTY (Release Coupling, fbe50871, AC-8): tropo.release.shipped is
    # NO LONGER emitted from build. Build performs zero public distribution now (upload
    # moved to --fire) — emitting a "shipped" event here would claim something that did
    # not happen. The real, verified signal is tropo.release.published, emitted by
    # tropo-publish-release.py --fire ONLY on full green (tag + main sha + release object
    # all verified live). If _build_clean is False (cold-walk gate did not pass), that is
    # recorded in cold-walk-verdict.json for tropo-publish-release.py's STAGE step to read
    # and refuse on, rather than build itself exiting nonzero for a gate that was always
    # meant to be advisory-then-checked-downstream (the cold-walk gate's own prompt already
    # handles the interactive override case).

    print(f'\n=== Build Complete ===')
    print(f'  Version: {new_version}')
    print(f'  Build: {build_dir}')
    print(f'  Testing: {testing_dir}')
    if missing > 0:
        print(f'  ⚠ {missing} entries referenced in index but file not found')
    _cw_verdict_path_display = os.path.join(tropo_roots.RELEASES_DIR, f'v{new_version}', 'cold-walk-verdict.json')
    _expected_zip_display = os.path.join(tropo_roots.RELEASES_DIR, f'v{new_version}', 'dist', f'tropo-os-v{new_version}.zip')
    print(f'\nNext steps (reasoning layer — agent executes):')
    print(f'  1. Run cold-boot-test.playbook.md against {testing_dir}')
    print(f'     (artifact self-sufficiency testing — Argus-lane R1 verification primitive)')
    print(f'  2. Stranger-walk gate (dev-spec 554624e5; v1.74 — built-in at Step 10.6):')
    print(f'     The always-ask prompt ran above. If upload was blocked pending a walk:')
    print(f'       a. python3 .tropo/scripts/test-harness-l2.py --release-zip {_expected_zip_display}')
    print(f'       b. Ask Po to conduct the walk (conductor: .tropo/playbooks/test-harness.playbook.md)')
    print(f'          Po writes verdict → {_cw_verdict_path_display}')
    print(f'       c. Re-run: python3 vault/tools/tropo-build-release.py --target {new_version} --force --activation-uid <uid>')
    print(f'          (--target is idempotent: re-uses the existing build, does NOT re-bump to next version)')
    print(f'  3. Generate RELEASE-NOTES.md')
    print(f'  4. Update source vault version to {new_version} (manual: echo "v{new_version}" > .tropo/version.md)')
    print(f'  5. PUBLISH (Release Coupling, fbe50871) — nothing above made anything public:')
    print(f'       a. python3 vault/tools/tropo-publish-release.py stage --activation-uid <uid> --version {new_version}')
    print(f'          (automated, idempotent, PRIVATE — re-runs the outward gate, physically disables the')
    print(f'          staged clone\'s push URL, stops at STAGED)')
    print(f'       b. python3 vault/tools/tropo-publish-release.py --fire   (Mike\'s hand — the one public act)')
    print(f'          tropo.release.published is emitted only on full green verify-live.')
    print(f'       c. Or: python3 vault/tools/tropo-publish-release.py --defer --reason "..."   (Mike-gestured skip)')


if __name__ == '__main__':
    main()
