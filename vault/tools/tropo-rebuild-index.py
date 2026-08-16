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
cli_command: python3 vault/tools/tropo-rebuild-index.py [--apply] [--reconcile] [--allow-index-shrink] [--only UID] [--vault-path PATH]   # --only UID = incremental single-entry index freshen (Argus A106, brief d7b3f1a9 §4)
script_path: vault/tools/tropo-rebuild-index.py
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
modified: 2026-07-26
modified_by: argus-a142
lifecycle_machine_projection_note: 'L2 Cockpit Cut 1A per locked dev-spec b06aa0fb + activation 1b3c6eaa: full rebuild validates capsule lifecycle_machine declarations and atomically emits constrained lifecycle_machines/lifecycle_transitions SQLite tables. Additive read projection only; capsule source remains canonical and unmodified.'
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
    python3 vault/tools/tropo-rebuild-index.py            # dry-run preview
    python3 vault/tools/tropo-rebuild-index.py --apply    # write
    python3 vault/tools/tropo-rebuild-index.py --vault-path <path>

Vault path resolution:
    1. Explicit --vault-path wins.
    2. Otherwise: walks up from script location for vault/ + .tropo/.
    3. Fallback: cwd if it has those anchors.

No third-party dependencies. Targets Python 3.8+.

Author: argus-a53
Owner: argus
Domain: vault-hygiene; v1.15.1 rebuild-script reform.
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
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:
    import yaml as _yaml
except ImportError:
    _yaml = None  # type: ignore

#: Safe-load through libyaml's C scanner where the machine has it. PyYAML's
#: pure-Python scanner was 88% of the sibling validator's runtime (measured
#: 2026-08-09, talos-t40) and this module parses the same frontmatter. Resolved
#: lazily and by hand rather than `from lib import`, because `_yaml` itself is
#: optional here and this module must keep importing on a box with no PyYAML.
_FAST_YAML = None
if _yaml is not None:
    try:
        import importlib.util as _fy_util

        _fy_spec = _fy_util.spec_from_file_location(
            "tropo_fast_yaml_rebuild",
            Path(__file__).resolve().parent / "lib" / "fast_yaml.py",
        )
        if _fy_spec is not None and _fy_spec.loader is not None:
            _FAST_YAML = _fy_util.module_from_spec(_fy_spec)
            _fy_spec.loader.exec_module(_FAST_YAML)
    except Exception:
        _FAST_YAML = None


def _yaml_safe_load(text: str) -> Any:
    """`yaml.safe_load` on the fastest available loader, with the old path intact.

    Falls back to plain PyYAML if the helper could not be loaded, and callers
    still guard on `_yaml is not None` for the no-PyYAML box, so this adds a
    speedup without adding a way to fail.
    """
    if _FAST_YAML is not None:
        return _FAST_YAML.safe_load(text)
    return _yaml.safe_load(text)


# v1.56 Lane S: script relocated to vault/tools/; siblings resolved by UID
_TOOLS = Path(__file__).resolve().parent
REHYDRATE = _TOOLS / "tropo-rehydrate.py"   # rehydrate — v1.30.0 Stream B auto-invoke
MINT_REGISTRY_GENERATOR = _TOOLS / "tropo-generate-mint-registry.py"

# v1.84 c6f6bea4 (ADR-051 Fork 4): shard-keyed incremental composed index.
# lib/shard_index.py is the SHARED module also imported by tropo-validate.py's
# check_shard_index_consistency — one derivation/reachability primitive, two
# consumers (writer + validator), so they cannot silently disagree on staleness.
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
from lib import (  # noqa: E402
    index_surfaces,
    lifecycle_machine,
    mounted_projection_trust,
    shard_index,
)

ARCHIVE_CACHE_KIND = 'local-archive-index'
ARCHIVE_CACHE_JSONL_REL = shard_index.SHARDS_REL / 'local-archive-index.jsonl'
ARCHIVE_CACHE_META_REL = shard_index.SHARDS_REL / 'local-archive-index.meta'
INDEX_RUN_ARTIFACT_REL = shard_index.SHARDS_REL / 'index-rebuild-run.json'


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _named_content_sha256(parts: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, raw in parts:
        digest.update(name.encode('utf-8'))
        digest.update(b'\0')
        digest.update(raw)
        digest.update(b'\0')
    return digest.hexdigest()


_NAVBLOCK_CLEAN_MODULE = None


_EXTRACT_TEXT_MODULE = None
_EXTRACT_TEXT_UNAVAILABLE = False


def _extract_text_module():
    """The text extractor (`tropo-extract-text.py`, cdadf603), loaded once.

    Imported rather than reimplemented, on the same principle the navblock
    cleaner follows above: one mechanism, two callers. The cache format, the
    staleness rule and the SF_DATALESS placeholder guard are the extractor's to
    define -- a second copy here would be a second thing to keep in step, which
    is the failure this studio pays for most often.

    Absence is a supported state, not an error: the index simply keeps today's
    behaviour and mounted binaries stay non-searchable.
    """
    global _EXTRACT_TEXT_MODULE, _EXTRACT_TEXT_UNAVAILABLE
    if _EXTRACT_TEXT_MODULE is not None or _EXTRACT_TEXT_UNAVAILABLE:
        return _EXTRACT_TEXT_MODULE
    path = _TOOLS / 'tropo-extract-text.py'
    try:
        spec = importlib.util.spec_from_file_location(
            'tropo_extract_text_index_reader', str(path)
        )
        if not spec or not spec.loader:
            raise ImportError(f'no loader for {path}')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in ('EXTRACTABLE', 'SF_DATALESS', 'cache_read', 'is_current',
                     'sha256_of'):
            if not hasattr(module, name):
                raise ImportError(f'{path} has no {name}')
    except Exception:
        _EXTRACT_TEXT_UNAVAILABLE = True
        return None
    _EXTRACT_TEXT_MODULE = module
    return module


def _is_extractable_suffix(relpath) -> bool:
    """Is this a source whose text would come from the extractor, not a read?"""
    extractor = _extract_text_module()
    if extractor is None:
        return False
    return Path(relpath).suffix.lower() in extractor.EXTRACTABLE


def _canonical_navblock_clean(raw: bytes) -> bytes:
    """Apply the exact canonical navblock clean primitive in this process."""
    global _NAVBLOCK_CLEAN_MODULE
    if _NAVBLOCK_CLEAN_MODULE is None:
        cleaner_path = _TOOLS / 'tropo-navblock-strip.py'
        spec = importlib.util.spec_from_file_location(
            'tropo_navblock_strip_index_identity',
            str(cleaner_path),
        )
        if not spec or not spec.loader:
            raise RuntimeError(f'cannot load canonical navblock cleaner {cleaner_path}')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not callable(getattr(module, 'run_clean', None)):
            raise RuntimeError(
                f'canonical navblock cleaner {cleaner_path} has no run_clean()'
            )
        _NAVBLOCK_CLEAN_MODULE = module
    return _NAVBLOCK_CLEAN_MODULE.run_clean(raw)


def _uses_parser_body_normalization(path: Path) -> bool:
    return (
        path.suffix.lower() == '.md'
        and path.parent.name == 'files'
        and path.parent.parent.name == 'vault'
    )


def _parser_canonical_derivation_bytes(path: Path, raw: bytes) -> bytes:
    """Return exactly the source bytes observable to index derivation."""
    if _uses_parser_body_normalization(path):
        return _canonical_navblock_clean(raw)
    return raw


def _git_blob_oid(raw: bytes, expected_oid: str) -> str:
    """Hash bytes exactly as Git hashes a blob, honoring SHA-1/SHA-256 repos."""
    if len(expected_oid) == 40:
        digest = hashlib.sha1()
    elif len(expected_oid) == 64:
        digest = hashlib.sha256()
    else:
        raise ValueError(f'unsupported Git object id length {len(expected_oid)}')
    digest.update(f'blob {len(raw)}\0'.encode('ascii'))
    digest.update(raw)
    return digest.hexdigest()


_DERIVATION_IMPLEMENTATION_PATHS = {
    '.gitattributes',
    'vault/tools/tropo-rebuild-index.py',
    'vault/tools/tropo-generate-relations-header.py',
    'vault/tools/tropo-navblock-strip.py',
    'vault/tools/lib/index_surfaces.py',
    'vault/tools/lib/shard_index.py',
    'vault/tools/lib/gardener.py',
    'vault/tools/lib/decay_gate.py',
    'vault/tools/lib/cross_vault_member_of.py',
    'vault/tools/lib/lifecycle_machine.py',
}


def _is_canonical_index_source(relative: Path) -> bool:
    """Whether the full rebuild can parse this path into a local index row."""
    parts = relative.parts
    if not parts:
        return False
    if len(parts) == 1:
        return relative.suffix.lower() == '.md'
    if len(parts) == 3 and parts[:2] == ('vault', 'files'):
        return relative.suffix.lower() == '.md'
    if len(parts) == 3 and parts[:2] == ('vault', 'capsules'):
        return (
            relative.name.endswith('.capsule.md')
            or relative.name.endswith('.history.md')
        )
    if len(parts) == 3 and parts[0] == 'vault' and parts[1] in {
        'tools',
        'actions',
    }:
        return relative.suffix.lower() in {'.py', '.md', '.json'}
    if len(parts) == 3 and parts[0] == 'vault' and parts[1] in {
        'agents',
        'playbooks',
        'skills',
    }:
        return relative.suffix.lower() == '.md'
    if len(parts) == 3 and parts[:2] == ('vault', 'session-agents'):
        return relative.suffix.lower() in {'.md', '.json'}
    if len(parts) == 4 and parts[:3] == (
        '.tropo-studio',
        'memory',
        'entries',
    ):
        return relative.suffix.lower() == '.md'
    if parts[0] == '.tropo' and relative.suffix.lower() == '.md':
        return relative.as_posix() in _tropo_kernel_admitted()
    if parts[0] == 'agents' and relative.suffix.lower() == '.md':
        if 'archive' in parts:
            return False
        if '.tropo-capsule' not in parts:
            return True
        return (
            len(parts) >= 6
            and parts[-4:-1] == ('.tropo-capsule', 'memory', 'entries')
        )
    return False


def _is_derivation_input(relative: Path) -> bool:
    return (
        _is_canonical_index_source(relative)
        or relative.as_posix() in _DERIVATION_IMPLEMENTATION_PATHS
    )


def _allowed_ignored_canonical_source(relative: Path) -> bool:
    parts = relative.parts
    return (
        parts[:3] == ('.tropo-studio', 'memory', 'entries')
        or (
            len(parts) >= 6
            and parts[0] == 'agents'
            and parts[-4:-1] == ('.tropo-capsule', 'memory', 'entries')
        )
    )


_KERNEL_UID_RE = re.compile(r"^uid:\s*[\"\']?([0-9a-f]{8})[\"\']?\s*$", re.M)
_KERNEL_ADMITTED_MEMO: dict = {}


def _tropo_kernel_sources(vault_root: Path) -> "tuple[list[Path], list[Path]]":
    root = Path(vault_root) / '.tropo'
    if not root.is_dir():
        return [], []
    admitted: "list[Path]" = []
    skipped: "list[Path]" = []
    for path in sorted(root.rglob('*.md')):
        if not path.is_file():
            continue
        # .tropo/seed/ is bootstrap payload for a DIFFERENT Studio -- copies of
        # vault entries shipped so a new Studio can be created. They carry the
        # same UIDs as the originals by design, so indexing them collides with
        # the live entry they were copied from. Same scoping rule as the
        # generated catalogs: the index holds THIS Studio's governed entries,
        # and a payload addressed to another one is not among them.
        if 'seed' in path.relative_to(root).parts:
            skipped.append(path)
            continue
        try:
            head = path.read_text(errors='replace')[:4096]
        except OSError:
            skipped.append(path); continue
        fm = head.split('---', 2)[1] if head.startswith('---') else ''
        (admitted if _KERNEL_UID_RE.search(fm) else skipped).append(path)
    return admitted, skipped


def _tropo_kernel_admitted(vault_root=None) -> frozenset:
    root = Path(vault_root) if vault_root else _TOOLS.parent.parent
    key = str(root.resolve())
    cached = _KERNEL_ADMITTED_MEMO.get(key)
    if cached is None:
        adm, _ = _tropo_kernel_sources(root)
        cached = frozenset(x.relative_to(root).as_posix() for x in adm)
        _KERNEL_ADMITTED_MEMO[key] = cached
    return cached


def _canonical_source_paths_on_disk(vault_root: Path) -> list[Path]:
    candidates: set[Path] = set()
    candidates.update(vault_root.glob('*.md'))
    candidates.update((vault_root / 'vault' / 'files').glob('*.md'))
    candidates.update((vault_root / 'vault' / 'capsules').glob('*.md'))
    for family in (
        'tools',
        'actions',
        'session-agents',
        'agents',
        'playbooks',
        'skills',
    ):
        candidates.update((vault_root / 'vault' / family).glob('*'))
    candidates.update(
        (vault_root / '.tropo-studio' / 'memory' / 'entries').glob('*.md')
    )
    agents_dir = vault_root / 'agents'
    if agents_dir.is_dir():
        candidates.update(agents_dir.rglob('*.md'))
    candidates.update(_tropo_kernel_sources(vault_root)[0])
    return sorted(
        path
        for path in candidates
        if path.is_file() or path.is_symlink()
        if _is_canonical_index_source(path.relative_to(vault_root))
    )


def _filesystem_source_inventory(
    vault_root: Path,
) -> tuple[Optional[dict[str, Any]], str]:
    """Compatibility proof for an intentionally unversioned fixture vault.

    Production Git studios use ``_derivation_worktree_clean`` and carry exact
    tracked blob identities. A standalone unversioned vault has no expected Git
    inventory; it may initialize absent surfaces from a stable complete scan,
    but remains ineligible for cache reuse.
    """
    source_inventory: list[tuple[str, str, str]] = []
    try:
        for source_path in _canonical_source_paths_on_disk(vault_root):
            relative = source_path.relative_to(vault_root)
            before = source_path.lstat()
            if stat.S_ISLNK(before.st_mode):
                mode = '120000'
                raw = os.readlink(os.fsencode(source_path))
            elif stat.S_ISREG(before.st_mode):
                mode = '100755' if before.st_mode & 0o111 else '100644'
                raw = source_path.read_bytes()
                if (
                    len(relative.parts) == 3
                    and relative.parts[:2] == ('vault', 'files')
                    and relative.suffix == '.md'
                ):
                    raw = _canonical_navblock_clean(raw)
            else:
                return None, (
                    f'unversioned canonical source has invalid mode: {relative}'
                )
            after = source_path.lstat()
            if (
                before.st_mode,
                before.st_size,
                before.st_mtime_ns,
                before.st_ino,
            ) != (
                after.st_mode,
                after.st_size,
                after.st_mtime_ns,
                after.st_ino,
            ):
                return None, (
                    f'unversioned canonical source changed during scan: {relative}'
                )
            source_inventory.append(
                (
                    relative.as_posix(),
                    mode,
                    _git_blob_oid(raw, '0' * 40),
                )
            )
    except (OSError, RuntimeError) as exc:
        return None, f'cannot inventory unversioned canonical sources: {exc}'
    normalized = tuple(sorted(source_inventory))
    return {
        'source_inventory': normalized,
        'source_inventory_sha256': _named_content_sha256([
            (path, f'{mode}\0{oid}'.encode('utf-8'))
            for path, mode, oid in normalized
        ]),
        'derivation_input_sha256': '',
        'tracked_derivation_input_count': 0,
    }, 'complete-unversioned-source-inventory'


def _parse_git_inventory(
    raw: bytes,
    *,
    index_format: bool,
) -> tuple[Optional[dict[str, tuple[str, str]]], str]:
    inventory: dict[str, tuple[str, str]] = {}
    for entry in raw.split(b'\0'):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b'\t', 1)
            fields = metadata.split(b' ')
            if index_format:
                raw_mode, raw_oid, raw_stage = fields
                index_stage = int(raw_stage)
            else:
                raw_mode, raw_type, raw_oid = fields
                if raw_type != b'blob':
                    continue
            path = os.fsdecode(raw_path)
            relative = Path(path)
            if relative.is_absolute() or '..' in relative.parts:
                return None, f'unsafe Git inventory path {path!r}'
            if not _is_derivation_input(relative):
                continue
            if index_format and index_stage != 0:
                return None, (
                    'derivation-relevant working tree has a conflicted '
                    f'index path {path}'
                )
            if path in inventory:
                return None, (
                    'derivation-relevant working tree has a conflicted '
                    f'index path {path}'
                )
            inventory[path] = (
                raw_mode.decode('ascii'),
                raw_oid.decode('ascii'),
            )
        except (UnicodeError, ValueError) as exc:
            return None, f'cannot parse Git inventory entry: {exc}'
    return inventory, 'complete'


def _derivation_worktree_clean(
    vault_root: Path,
    head: str,
    *,
    allowed_dirty_paths: Optional[set[str]] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Prove only derivation inputs clean and return their exact inventory.

    Runtime state such as dirty counters, event streams/receipts, and cursors is
    deliberately outside this scope.  ``None`` means completeness could not be
    proven; callers then rederive and cannot mint an absent-surface proof.
    """
    allowed = {
        Path(path).as_posix()
        for path in (allowed_dirty_paths or set())
        if path and not Path(path).is_absolute() and '..' not in Path(path).parts
    }
    blockers: dict[str, str] = {}
    accepted_dirty_paths: set[str] = set()

    def block(
        path: str,
        detail: str,
        *,
        owned_permitted: bool = True,
    ) -> None:
        if path not in allowed or not owned_permitted:
            blockers.setdefault(path, detail)

    git = ['git', '-C', str(vault_root)]
    try:
        filemode_result = subprocess.run(
            [*git, 'config', '--bool', 'core.filemode'],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if filemode_result.returncode == 0:
            honor_filemode = filemode_result.stdout.strip().lower() == 'true'
        elif filemode_result.returncode == 1:
            honor_filemode = True
        else:
            return None, (
                'cannot read Git core.filemode: '
                f'{filemode_result.stderr.strip()}'
            )

        index_result = subprocess.run(
            [*git, 'ls-files', '--stage', '-z'],
            capture_output=True,
            timeout=20,
        )
        if index_result.returncode != 0:
            return None, (
                'cannot enumerate tracked derivation inputs: '
                f'{index_result.stderr.decode("utf-8", "replace").strip()}'
            )
        index_inventory, reason = _parse_git_inventory(
            index_result.stdout,
            index_format=True,
        )
        if index_inventory is None:
            return None, reason

        head_result = subprocess.run(
            [*git, 'ls-tree', '-r', '-z', '--full-tree', head],
            capture_output=True,
            timeout=20,
        )
        if head_result.returncode != 0:
            return None, (
                'cannot enumerate HEAD derivation inputs: '
                f'{head_result.stderr.decode("utf-8", "replace").strip()}'
            )
        head_inventory, reason = _parse_git_inventory(
            head_result.stdout,
            index_format=False,
        )
        if head_inventory is None:
            return None, reason
        if index_inventory != head_inventory:
            differing = sorted(
                path
                for path in set(index_inventory) | set(head_inventory)
                if index_inventory.get(path) != head_inventory.get(path)
            )
            for path in differing:
                index_entry = index_inventory.get(path)
                head_entry = head_inventory.get(path)
                staged_deletion = (
                    path in allowed
                    and head_entry is not None
                    and index_entry is None
                )
                staged_type_loss = (
                    path in allowed
                    and index_entry is not None
                    and head_entry is not None
                    and (
                        (index_entry[0] == '120000')
                        != (head_entry[0] == '120000')
                    )
                )
                block(
                    path,
                    (
                        'staged tracked source/input deletion'
                        if staged_deletion
                        else (
                            'staged source/input type change'
                            if staged_type_loss
                            else 'staged change'
                        )
                    ),
                    owned_permitted=not (
                        staged_deletion or staged_type_loss
                    ),
                )
                if (
                    path in allowed
                    and not staged_deletion
                    and not staged_type_loss
                ):
                    accepted_dirty_paths.add(path)

        untracked_result = subprocess.run(
            [*git, 'ls-files', '--others', '--exclude-standard', '-z'],
            capture_output=True,
            timeout=20,
        )
        if untracked_result.returncode != 0:
            return None, (
                'cannot enumerate untracked derivation inputs: '
                f'{untracked_result.stderr.decode("utf-8", "replace").strip()}'
            )
        untracked_relevant = sorted(
            os.fsdecode(raw_path)
            for raw_path in untracked_result.stdout.split(b'\0')
            if raw_path and _is_derivation_input(Path(os.fsdecode(raw_path)))
        )
        for path in untracked_relevant:
            block(path, 'untracked source/input')
            if path in allowed:
                accepted_dirty_paths.add(path)

        hash_oid = next(
            (oid for _mode, oid in index_inventory.values()),
            '0' * 40,
        )
        source_inventory: list[tuple[str, str, str]] = []
        for relative_path, (index_mode, index_oid) in sorted(
            index_inventory.items()
        ):
            relative = Path(relative_path)
            worktree_path = vault_root / relative
            is_navblock_path = (
                len(relative.parts) == 3
                and relative.parts[:2] == ('vault', 'files')
                and relative.suffix == '.md'
            )
            inventory_mode = index_mode
            inventory_oid = index_oid
            try:
                before = worktree_path.lstat()
                if index_mode in {'100644', '100755'}:
                    if not stat.S_ISREG(before.st_mode):
                        block(
                            relative_path,
                            'invalid worktree mode',
                            owned_permitted=False,
                        )
                        continue
                    executable_mode_changed = honor_filemode and (
                        bool(before.st_mode & 0o111) != (index_mode == '100755')
                    )
                    if executable_mode_changed:
                        block(relative_path, 'changed executable mode')
                        if relative_path in allowed:
                            accepted_dirty_paths.add(relative_path)
                    raw_worktree = worktree_path.read_bytes()
                    comparable = (
                        _canonical_navblock_clean(raw_worktree)
                        if is_navblock_path
                        else raw_worktree
                    )
                    if relative_path in allowed:
                        inventory_mode = (
                            '100755'
                            if before.st_mode & 0o111
                            else '100644'
                        )
                        inventory_oid = _git_blob_oid(comparable, index_oid)
                elif index_mode == '120000':
                    if not stat.S_ISLNK(before.st_mode):
                        block(
                            relative_path,
                            'changed symlink mode',
                            owned_permitted=False,
                        )
                        continue
                    comparable = os.readlink(os.fsencode(worktree_path))
                    if relative_path in allowed:
                        inventory_oid = _git_blob_oid(comparable, index_oid)
                else:
                    block(
                        relative_path,
                        f'unsupported index mode {index_mode}',
                        owned_permitted=False,
                    )
                    continue
                after = worktree_path.lstat()
            except FileNotFoundError:
                block(relative_path, 'deleted tracked source/input')
                continue
            except OSError as exc:
                block(
                    relative_path,
                    f'cannot read tracked input: {exc}',
                    owned_permitted=False,
                )
                continue
            if (
                before.st_mode,
                before.st_size,
                before.st_mtime_ns,
                before.st_ino,
            ) != (
                after.st_mode,
                after.st_size,
                after.st_mtime_ns,
                after.st_ino,
            ):
                block(
                    relative_path,
                    'changed during verification',
                    owned_permitted=False,
                )
            if (
                _git_blob_oid(comparable, index_oid) != index_oid
            ):
                if relative_path in allowed:
                    accepted_dirty_paths.add(relative_path)
                else:
                    path_kind = 'navblock' if is_navblock_path else 'ordinary'
                    block(
                        relative_path,
                        f'dirty {path_kind} source/input',
                    )
            if _is_canonical_index_source(relative):
                source_inventory.append(
                    (relative_path, inventory_mode, inventory_oid)
                )

        tracked_sources = {path for path, _mode, _oid in source_inventory}
        for source_path in _canonical_source_paths_on_disk(vault_root):
            relative = source_path.relative_to(vault_root)
            relative_path = relative.as_posix()
            if relative_path in tracked_sources:
                continue
            if (
                relative_path not in allowed
                and not _allowed_ignored_canonical_source(relative)
            ):
                block(relative_path, 'untracked canonical source')
            if relative_path in allowed:
                accepted_dirty_paths.add(relative_path)
            try:
                before = source_path.lstat()
                if stat.S_ISLNK(before.st_mode):
                    mode = '120000'
                    raw = os.readlink(os.fsencode(source_path))
                elif stat.S_ISREG(before.st_mode):
                    mode = (
                        '100755' if before.st_mode & 0o111 else '100644'
                    )
                    raw = source_path.read_bytes()
                    if (
                        len(relative.parts) == 3
                        and relative.parts[:2] == ('vault', 'files')
                        and relative.suffix == '.md'
                    ):
                        raw = _canonical_navblock_clean(raw)
                else:
                    block(
                        relative_path,
                        'invalid canonical source mode',
                        owned_permitted=False,
                    )
                    continue
            except OSError as exc:
                block(
                    relative_path,
                    f'cannot read canonical source: {exc}',
                    owned_permitted=False,
                )
                continue
            source_inventory.append(
                (relative_path, mode, _git_blob_oid(raw, hash_oid))
            )

        if blockers:
            rendered = ', '.join(
                f'{path} [{blockers[path]}]' for path in sorted(blockers)
            )
            return None, (
                'derivation-relevant source inventory is incomplete; '
                f'blocking paths (land/revert/isolate first): {rendered}'
            )
        normalized_sources = tuple(sorted(source_inventory))
        derivation_inventory = tuple(
            (path, mode, oid)
            for path, (mode, oid) in sorted(index_inventory.items())
        )
        return {
            'source_inventory': normalized_sources,
            'source_inventory_sha256': _named_content_sha256([
                (
                    path,
                    f'{mode}\0{oid}'.encode('utf-8'),
                )
                for path, mode, oid in normalized_sources
            ]),
            'derivation_input_sha256': _named_content_sha256([
                (
                    path,
                    f'{mode}\0{oid}'.encode('utf-8'),
                )
                for path, mode, oid in derivation_inventory
            ]),
            'tracked_derivation_input_count': len(derivation_inventory),
            'operation_owned_dirty_paths': tuple(sorted(allowed)),
            'accepted_dirty_paths': tuple(sorted(accepted_dirty_paths)),
        }, 'complete'
    except Exception as exc:
        return None, f'cannot verify derivation working tree: {exc}'


def _capture_source_inventory_proof(
    vault_root: Path,
    *,
    allowed_dirty_paths: Optional[set[str]] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Capture one stable expected source inventory for a full derivation."""
    try:
        head_result = subprocess.run(
            ['git', '-C', str(vault_root), 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f'cannot prove source inventory completeness: {exc}'
    if head_result.returncode == 0:
        return _derivation_worktree_clean(
            vault_root,
            head_result.stdout.strip(),
            allowed_dirty_paths=allowed_dirty_paths,
        )
    if not (vault_root / '.git').exists():
        return _filesystem_source_inventory(vault_root)
    return None, (
        'cannot resolve HEAD for source inventory proof: '
        f'{head_result.stderr.strip()}'
    )


def _capture_initial_worktree_source_proof(
    vault_root: Path,
) -> tuple[Optional[dict[str, Any]], str]:
    """Prove initial worktree sources while permitting only present source WIP.

    This exception is safe only before any derived index participant exists.
    Present canonical sources may differ from HEAD because the collector can
    account for them exactly; deleted sources, type changes, and dirty
    derivation code/configuration remain blockers.
    """
    allowed_sources = {
        path.relative_to(vault_root).as_posix()
        for path in _canonical_source_paths_on_disk(vault_root)
    }
    return _capture_source_inventory_proof(
        vault_root,
        allowed_dirty_paths=allowed_sources,
    )


def _parse_complete_git_inventory(
    raw: bytes,
    *,
    index_format: bool,
) -> tuple[Optional[dict[str, tuple[str, str]]], str]:
    """Parse every Git blob so symlink targets can be verified in-process."""
    inventory: dict[str, tuple[str, str]] = {}
    for entry in raw.split(b'\0'):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b'\t', 1)
            fields = metadata.split(b' ')
            if index_format:
                raw_mode, raw_oid, raw_stage = fields
                if int(raw_stage) != 0:
                    return None, (
                        'working tree has a conflicted index path '
                        f'{os.fsdecode(raw_path)}'
                    )
            else:
                raw_mode, raw_type, raw_oid = fields
                if raw_type != b'blob':
                    continue
            path = os.fsdecode(raw_path)
            relative = Path(path)
            if relative.is_absolute() or '..' in relative.parts:
                return None, f'unsafe Git inventory path {path!r}'
            if path in inventory:
                return None, f'working tree has duplicate Git path {path}'
            inventory[path] = (
                raw_mode.decode('ascii'),
                raw_oid.decode('ascii'),
            )
        except (UnicodeError, ValueError) as exc:
            return None, f'cannot parse Git inventory entry: {exc}'
    return inventory, 'complete'


def _read_git_blob_batch(
    vault_root: Path,
    object_ids: set[str],
) -> tuple[Optional[dict[str, bytes]], str]:
    """Read committed blob bytes in one Git process, bypassing clean filters."""
    if not object_ids:
        return {}, 'complete'
    requested = sorted(object_ids)
    try:
        result = subprocess.run(
            ['git', '-C', str(vault_root), 'cat-file', '--batch'],
            input=(''.join(f'{oid}\n' for oid in requested)).encode('ascii'),
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f'cannot read committed derivation blobs: {exc}'
    if result.returncode != 0:
        return None, (
            'cannot read committed derivation blobs: '
            f'{result.stderr.decode("utf-8", "replace").strip()}'
        )
    parsed: dict[str, bytes] = {}
    cursor = 0
    raw = result.stdout
    try:
        for requested_oid in requested:
            header_end = raw.index(b'\n', cursor)
            header = raw[cursor:header_end].decode('ascii')
            cursor = header_end + 1
            fields = header.split()
            if len(fields) != 3 or fields[1] != 'blob':
                return None, (
                    'committed derivation object is not a readable blob: '
                    f'{header}'
                )
            actual_oid, _kind, size_raw = fields
            size = int(size_raw)
            content = raw[cursor:cursor + size]
            cursor += size
            if raw[cursor:cursor + 1] != b'\n':
                return None, 'malformed git cat-file --batch response'
            cursor += 1
            if actual_oid != requested_oid or len(content) != size:
                return None, 'git cat-file returned a mismatched blob'
            parsed[requested_oid] = content
    except (UnicodeError, ValueError) as exc:
        return None, f'cannot parse committed derivation blobs: {exc}'
    return parsed, 'complete'


def _exact_derivation_input_paths(
    vault_root: Path,
    extra_input_paths: tuple[Path, ...],
) -> dict[str, tuple[Path, str, bool]]:
    """Return relative input paths as path, manifest-kind, Git-authority flag."""
    paths: dict[str, tuple[Path, str, bool]] = {}
    for path in _canonical_source_paths_on_disk(vault_root):
        relative = path.relative_to(vault_root).as_posix()
        paths[relative] = (path, 'source', True)
    for relative_raw in sorted(_DERIVATION_IMPLEMENTATION_PATHS):
        path = vault_root / relative_raw
        if path.exists() or path.is_symlink():
            kind = (
                'source'
                if _is_canonical_index_source(Path(relative_raw))
                else 'input'
            )
            paths[relative_raw] = (path, kind, True)
    compose_path = vault_root / shard_index.COMPOSE_LOCK_REL
    if compose_path.exists() or compose_path.is_symlink():
        relative = compose_path.relative_to(vault_root).as_posix()
        paths[relative] = (compose_path, 'input', False)
    folder_mounts_path = vault_root / '.tropo-studio/folder-mounts.json'
    if folder_mounts_path.exists() or folder_mounts_path.is_symlink():
        relative = folder_mounts_path.relative_to(vault_root).as_posix()
        paths[relative] = (folder_mounts_path, 'input', False)
    for path in extra_input_paths:
        if not (path.exists() or path.is_symlink()):
            continue
        relative = path.relative_to(vault_root).as_posix()
        paths[relative] = (path, 'cache', False)
    return paths


def _capture_exact_derivation_snapshot(
    vault_root: Path,
    *,
    extra_input_paths: tuple[Path, ...] = (),
    allowed_deleted_paths: Optional[set[str]] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Hash exact worktree bytes/modes/link targets without storing content."""
    allowed_deleted = {
        Path(path).as_posix()
        for path in (allowed_deleted_paths or set())
        if path and not Path(path).is_absolute() and '..' not in Path(path).parts
    }
    git = ['git', '-C', str(vault_root)]
    try:
        head_result = subprocess.run(
            [*git, 'ls-tree', '-r', '-z', '--full-tree', 'HEAD'],
            capture_output=True,
            timeout=20,
        )
        index_result = subprocess.run(
            [*git, 'ls-files', '--stage', '-z'],
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f'cannot inventory exact derivation bytes: {exc}'
    git_authority_available = head_result.returncode == 0
    if head_result.returncode != 0:
        if not (vault_root / '.git').exists():
            head_inventory: dict[str, tuple[str, str]] = {}
            index_inventory: dict[str, tuple[str, str]] = {}
        else:
            return None, (
                'cannot enumerate committed derivation inputs: '
                f'{head_result.stderr.decode("utf-8", "replace").strip()}'
            )
    elif index_result.returncode != 0:
        return None, (
            'cannot enumerate indexed derivation inputs: '
            f'{index_result.stderr.decode("utf-8", "replace").strip()}'
        )
    else:
        head_inventory, reason = _parse_complete_git_inventory(
            head_result.stdout,
            index_format=False,
        )
        if head_inventory is None:
            return None, reason
        index_inventory, reason = _parse_complete_git_inventory(
            index_result.stdout,
            index_format=True,
        )
        if index_inventory is None:
            return None, reason

    inputs = _exact_derivation_input_paths(vault_root, extra_input_paths)
    committed_blobs, committed_reason = _read_git_blob_batch(
        vault_root,
        {oid for _mode, oid in head_inventory.values()},
    )
    if committed_blobs is None:
        return None, committed_reason
    blockers: dict[str, str] = {}
    manifest: list[tuple[str, str, str, str]] = []
    uncommitted: dict[str, tuple[str, str, str, str]] = {}
    source_paths: set[str] = set()
    hash_oid = next(
        (oid for _mode, oid in head_inventory.values()),
        next(
            (oid for _mode, oid in index_inventory.values()),
            '0' * 40,
        ),
    )

    expected_paths = {
        path
        for path in set(head_inventory) | set(index_inventory)
        if _is_derivation_input(Path(path))
    }
    for relative in sorted(expected_paths - set(inputs)):
        if relative in allowed_deleted:
            absent_sha = hashlib.sha256(b'absent derivation input').hexdigest()
            manifest.append(
                ('source-absence', relative, 'absent', absent_sha)
            )
            source_paths.add(relative)
            uncommitted[relative] = (
                relative,
                'absent',
                absent_sha,
                '',
            )
        else:
            blockers[relative] = 'deleted tracked source/input'

    for relative, (path, kind, git_authority) in sorted(inputs.items()):
        try:
            before = path.lstat()
            symlink_target_sha256 = ''
            if stat.S_ISLNK(before.st_mode):
                mode = '120000'
                link_raw = os.readlink(os.fsencode(path))
                symlink_target_sha256 = hashlib.sha256(link_raw).hexdigest()
                raw = _parser_canonical_derivation_bytes(
                    path,
                    path.read_bytes(),
                )
                manifest.append(
                    (
                        'symlink-target',
                        relative,
                        mode,
                        symlink_target_sha256,
                    )
                )
                git_comparable = link_raw
            elif stat.S_ISREG(before.st_mode):
                mode = '100755' if before.st_mode & 0o111 else '100644'
                raw = _parser_canonical_derivation_bytes(
                    path,
                    path.read_bytes(),
                )
                git_comparable = raw
            else:
                blockers[relative] = 'invalid derivation input mode'
                continue
            after = path.lstat()
        except (OSError, RuntimeError) as exc:
            blockers[relative] = f'cannot read derivation input: {exc}'
            continue
        if (
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ino,
        ) != (
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ino,
        ):
            blockers[relative] = 'changed during exact-byte verification'
            continue

        content_sha256 = hashlib.sha256(raw).hexdigest()
        manifest.append((kind, relative, mode, content_sha256))
        if kind == 'source':
            source_paths.add(relative)
        if not git_authority:
            continue

        head_entry = head_inventory.get(relative)
        index_entry = index_inventory.get(relative)
        if (
            head_entry is not None
            and index_entry is None
        ):
            blockers[relative] = 'staged tracked source/input deletion'
            continue
        if (
            head_entry is not None
            and index_entry is not None
            and ((head_entry[0] == '120000') != (index_entry[0] == '120000'))
        ):
            blockers[relative] = 'staged source/input type change'
            continue
        if (
            head_entry is not None
            and ((head_entry[0] == '120000') != (mode == '120000'))
        ):
            blockers[relative] = (
                'invalid worktree mode (source/input type change)'
            )
            continue

        dirty = head_entry is None
        if head_entry is not None:
            head_mode, head_oid = head_entry
            committed_raw = committed_blobs.get(head_oid)
            if committed_raw is None:
                blockers[relative] = 'committed source/input blob is unavailable'
                continue
            committed_comparable = (
                committed_raw
                if mode == '120000'
                else _parser_canonical_derivation_bytes(
                    path,
                    committed_raw,
                )
            )
            dirty = (
                git_comparable != committed_comparable
                or (
                    head_mode in {'100644', '100755'}
                    and mode != head_mode
                )
            )
        if mode == '120000':
            try:
                resolved_target = path.resolve(strict=True)
                target_relative = resolved_target.relative_to(
                    vault_root.resolve()
                ).as_posix()
                target_head = head_inventory.get(target_relative)
                if target_head is None:
                    dirty = True
                elif _parser_canonical_derivation_bytes(
                    path,
                    committed_blobs[target_head[1]],
                ) != raw:
                    dirty = True
            except (OSError, ValueError):
                dirty = True
        if dirty:
            uncommitted[relative] = (
                relative,
                mode,
                content_sha256,
                symlink_target_sha256,
            )

    if blockers:
        rendered = ', '.join(
            f'{path} [{blockers[path]}]' for path in sorted(blockers)
        )
        return None, (
            'exact derivation manifest is incomplete; blocking paths '
            f'(land/revert/isolate first): {rendered}'
        )
    normalized_manifest = tuple(sorted(manifest))
    return {
        'manifest': normalized_manifest,
        'source_paths': tuple(sorted(source_paths)),
        'uncommitted_inputs': tuple(sorted(uncommitted.values())),
        'derived_from_uncommitted': bool(uncommitted),
        'git_authority_available': git_authority_available,
    }, 'complete'


def _finalize_derivation_manifest(
    snapshot: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    repo_clock: str,
    wall_clock_date: str,
) -> tuple[tuple[str, str, str, str], ...]:
    manifest = list(snapshot['manifest'])
    for record in records:
        path = str(record.get('path') or '')
        if not path.startswith('mounted/'):
            continue
        raw = json.dumps(
            record,
            separators=(',', ':'),
            sort_keys=True,
        ).encode('utf-8')
        manifest.append((
            'mounted-record',
            f'@{path}',
            'virtual',
            hashlib.sha256(raw).hexdigest(),
        ))
    virtual_inputs = {
        '@python-runtime': (
            f'python={sys.version};'
            f'pyyaml={getattr(_yaml, "__version__", "absent")}'
        ).encode('utf-8'),
    }
    if repo_clock:
        virtual_inputs['@repo-clock'] = repo_clock.encode('utf-8')
    if wall_clock_date:
        virtual_inputs['@wall-clock-date'] = wall_clock_date.encode('ascii')
    for path, raw in sorted(virtual_inputs.items()):
        manifest.append((
            'virtual',
            path,
            'virtual',
            hashlib.sha256(raw).hexdigest(),
        ))
    return tuple(sorted(manifest))


def _derivation_repo_clock(vault_root: Path) -> str:
    try:
        result = subprocess.run(
            ['git', '-C', str(vault_root), 'log', '-1', '--format=%ci'],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return 'unversioned'
    return result.stdout.strip() if result.returncode == 0 else 'unversioned'


def _uncommitted_input_receipt(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            'content_sha256': content_sha256,
            'mode': mode,
            'path': path,
            'symlink_target_sha256': symlink_target_sha256 or None,
        }
        for path, mode, content_sha256, symlink_target_sha256 in snapshot[
            'uncommitted_inputs'
        ]
    ]


def _inherited_derivation_snapshot(
    vault_root: Path,
    owned_paths: set[str],
) -> tuple[Optional[dict[str, Any]], str]:
    """A single-file write's snapshot: inherit the trusted manifest, re-hash ONE file.

    WHY THIS EXISTS. Writing one governed file used to cost 26.1 seconds and
    13,219 `posix.open` calls, because `_capture_exact_derivation_snapshot` was
    called twice and each call re-read every source file in the vault to rebuild
    a 6,248-entry manifest that was already sitting on disk. Measured 2026-08-06:
    85% of a single-entry write was that proof.

    Worse than slow, it REFUSED. Any file changed anywhere since the last full
    rebuild blocked every write. Reproduced live the same day: Orpheus booting
    updated her own agent card, and that alone refused an unrelated write —
    "semantic derivation inputs changed outside the owned target:
    vault/agents/8b81aecf.md". Two agents working at once was enough.

    THE RULING (Mike, 2026-08-06). Saving one file does not have to prove the
    whole vault is correct. That is what the full rebuild is for, and it is what
    `_freshen_one_locked` already declares in its own docstring: "Non-authoritative
    + self-healing ... the next full rebuild reconciles from frontmatter". The
    whole-vault proof was added on top of that contract on 2026-07-30 by
    059f2c68, which metis-g97 flagged as breaking minting the same day.

    Mike, on why the rule was wrong rather than merely expensive: detecting that
    a file drifted from its record is a READ question. The architecture review
    says hand-edits "always work and are caught DOWNSTREAM" (§9). This restores
    that: drift is caught by the next full rebuild, verified 2026-08-06 by
    tampering with a file's frontmatter and watching the rebuild re-derive it.

    WHAT IS PRESERVED. The seal stays COMPLETE — we inherit every entry a full
    rebuild proved, so nothing downstream sees a partial manifest. The
    before/after equality check still catches the TARGET changing mid-write,
    because both snapshots re-hash it. What is given up, deliberately, is
    noticing that an unrelated file moved during the write.

    Virtual entries are dropped because `_finalize_derivation_manifest` re-adds
    every one of them (mounts, clocks, runtime); carrying the stored copies
    through produces "derivation manifest contains duplicate entries".

    Measured after: 3.25s, and stable — three consecutive writes each inheriting
    the previous write's seal, all clean.
    """
    try:
        prior = index_surfaces.load_trusted_derivation_manifest(vault_root)
    except index_surfaces.IndexSurfaceRefusal as exc:
        return None, f'no trusted derivation manifest to inherit: {exc}'
    manifest = {
        (kind, path): (kind, path, mode, content_sha256)
        for kind, path, mode, content_sha256 in prior
        if kind != 'virtual'
    }
    source_paths = {
        path
        for kind, path, _mode, _sha in prior
        if kind in ('source', 'source-absence')
    }
    # DERIVATION CODE IS RE-HASHED FRESH, SOURCES ARE INHERITED.
    #
    # A data file changing elsewhere is none of this write's business -- that is
    # the whole ruling. But a change to the derivation CODE is a different class:
    # if the parser or the gardener changed, every row already in the index may
    # be stale, and that must still force a full rebuild.
    #
    # This costs nothing to keep. There are 8 'input' entries against 6,140
    # 'source' entries (measured 2026-08-06), so re-hashing the code is ~0.1% of
    # the proof we removed. Caught by
    # test_parser_canonical_navblock_proof_and_global_only_authority, which
    # asserts a gardener.py edit blocks an A-only write -- and it was right to.
    # Enumerated FROM DISK, not from the stored manifest. A first attempt only
    # re-hashed inputs already present in the manifest, which silently missed a
    # code file that was newly ADDED -- exactly the case that test constructs,
    # and it passed my review because I reasoned about the fix instead of
    # instrumenting it. This walks the implementation-path set (plus the compose
    # lock and mounts registry) and never calls _canonical_source_paths_on_disk,
    # which is the expensive 6,140-file walk being removed.
    code_inputs: list[tuple[str, Path]] = []
    for relative_raw in sorted(_DERIVATION_IMPLEMENTATION_PATHS):
        if _is_canonical_index_source(Path(relative_raw)):
            continue
        code_inputs.append((relative_raw, vault_root / relative_raw))
    for extra_rel in (
        str(shard_index.COMPOSE_LOCK_REL),
        '.tropo-studio/folder-mounts.json',
    ):
        code_inputs.append((extra_rel, vault_root / extra_rel))
    for relative, target in code_inputs:
        if not (target.exists() or target.is_symlink()):
            manifest.pop(('input', relative), None)
            continue
        if not target.is_file():
            continue
        fresh = hashlib.sha256(
            _parser_canonical_derivation_bytes(target, target.read_bytes())
        ).hexdigest()
        manifest[('input', relative)] = ('input', relative, '100644', fresh)

    uncommitted: dict[str, tuple[str, str, str, str]] = {}
    for relative in sorted(owned_paths):
        target = vault_root / relative
        if not target.is_file():
            continue
        canonical = _parser_canonical_derivation_bytes(
            target, target.read_bytes()
        )
        content_sha = hashlib.sha256(canonical).hexdigest()
        for replaced in ('input', 'source', 'source-absence', 'symlink-target'):
            manifest.pop((replaced, relative), None)
        manifest[('source', relative)] = (
            'source', relative, '100644', content_sha
        )
        uncommitted[relative] = (relative, '100644', content_sha, '')
        source_paths.add(relative)
    return (
        {
            'manifest': tuple(sorted(manifest.values())),
            'uncommitted_inputs': tuple(sorted(uncommitted.values())),
            'source_paths': tuple(sorted(source_paths)),
            'derived_from_uncommitted': bool(uncommitted),
        },
        'inherited trusted manifest; owned path(s) re-hashed',
    )


def _verify_incremental_source_scope(
    vault_root: Path,
    owned_paths: set[str],
    *,
    defer_semantic_scope_to_trusted_manifest: bool = False,
) -> tuple[Optional[dict[str, Any]], str]:
    """Permit only this operation's exact canonical source paths to be dirty."""
    requested = {Path(path).as_posix() for path in owned_paths if path}
    normalized = {
        path
        for path in requested
        if not Path(path).is_absolute()
        and '..' not in Path(path).parts
        and _is_derivation_input(Path(path))
    }
    if normalized != requested:
        return None, (
            'incremental operation did not resolve every owned path to a '
            'canonical derivation input'
        )
    if not defer_semantic_scope_to_trusted_manifest:
        proof, reason = _capture_source_inventory_proof(
            vault_root,
            allowed_dirty_paths=normalized,
        )
        if proof is None:
            return None, reason
    exact, exact_reason = _capture_exact_derivation_snapshot(
        vault_root,
        allowed_deleted_paths=normalized,
    )
    if exact is None:
        return None, exact_reason
    return exact, (
        'manifest comparison pending for operation-owned path(s): '
        + (', '.join(sorted(normalized)) if normalized else '(none)')
    )


def _snapshot_with_source_replacements(
    snapshot: dict[str, Any],
    vault_root: Path,
    replacements: dict[Path, bytes],
    *,
    input_paths: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Project staged governed bytes into an exact derivation snapshot."""
    overlaid = dict(snapshot)
    manifest = {
        (entry[0], entry[1]): entry
        for entry in snapshot["manifest"]
    }
    uncommitted = {
        entry[0]: entry
        for entry in snapshot["uncommitted_inputs"]
    }
    source_paths = set(snapshot["source_paths"])
    input_paths = {Path(path).as_posix() for path in (input_paths or set())}
    for path, raw in replacements.items():
        relative = path.relative_to(vault_root).as_posix()
        canonical = _parser_canonical_derivation_bytes(path, raw)
        content_sha = hashlib.sha256(canonical).hexdigest()
        kind = "input" if relative in input_paths else "source"
        # These kinds are mutually exclusive only for the replaced path. Key
        # the complete manifest by (kind, path), otherwise an unrelated
        # symlink's source and target receipts collapse because they
        # intentionally share one path.
        for replaced_kind in (
            "input",
            "source",
            "source-absence",
            "symlink-target",
        ):
            manifest.pop((replaced_kind, relative), None)
        manifest[(kind, relative)] = (kind, relative, "100644", content_sha)
        uncommitted[relative] = (relative, "100644", content_sha, "")
        if kind == "source":
            source_paths.add(relative)
    overlaid["manifest"] = tuple(sorted(manifest.values()))
    overlaid["uncommitted_inputs"] = tuple(sorted(uncommitted.values()))
    overlaid["source_paths"] = tuple(sorted(source_paths))
    overlaid["derived_from_uncommitted"] = bool(uncommitted)
    return overlaid


def _snapshot_with_mounted_catalog(
    snapshot: dict[str, Any],
    catalog: "_MountedSourceCatalog",
) -> dict[str, Any]:
    """Bind portable virtual digests for every mounted input actually consumed."""
    overlaid = dict(snapshot)
    manifest = {
        (entry[0], entry[1]): entry
        for entry in snapshot["manifest"]
    }
    for entry in catalog.manifest_entries():
        manifest[(entry[0], entry[1])] = entry
    overlaid["manifest"] = tuple(sorted(manifest.values()))
    return overlaid


# The passage of time is not a semantic input change. These two virtuals are
# RECORDED in the seal (so provenance still says which day a derivation ran) but
# never COMPARED as blockers, because a date advancing does not make previously
# derived rows wrong — it only means age-derived fields are due a refresh, which
# the next full pass handles.
#
# Compared, they froze every incremental write studio-wide at midnight with
# nothing edited by anyone. This fired on me live at 2026-08-02T00:20Z, four
# hours after I documented it and chose not to fix it — the refusal named
# `@wall-clock-date` while I was trying to mint an unrelated brief. A gate whose
# trigger is the clock cannot be reasoned about by the agent it stops.
#
# `@python-runtime` is deliberately NOT in this set: a different interpreter or
# PyYAML version genuinely can parse sources differently, so that one stays a
# blocker.
CLOCK_VIRTUAL_INPUTS = frozenset({'@repo-clock', '@wall-clock-date'})


def _derivation_clock_entries(vault_root: Path) -> dict[str, str]:
    """Clock values for a transaction that does not re-run the gardener.

    The full and freshen paths take these from `gardener_stats`. A removal never
    runs the gardener, but it still WRITES a seal, so it must record the same
    two virtual inputs the next incremental read will look for. Computed the
    same way the gardener computes them (ISO dates), not read back from the
    seal — the manifest stores sha256 of each value, so carrying the sealed
    entry forward would hash an already-hashed value and produce a fresh delta,
    which is the very failure being fixed.
    """
    entries = {'repo_clock': '', 'wall_clock_date': ''}
    try:
        from lib import gardener as _gardener
        entries['repo_clock'] = _gardener.repo_clock_date(vault_root, []).isoformat()
    except Exception:
        pass
    try:
        from datetime import date as _date
        entries['wall_clock_date'] = _date.today().isoformat()
    except Exception:
        pass
    return entries


def _incremental_manifest_blockers(
    vault_root: Path,
    current_manifest: tuple[tuple[str, str, str, str], ...],
    owned_paths: set[str],
    *,
    allowed_virtual_paths: Optional[set[str]] = None,
    allowed_virtual_prefixes: Optional[tuple[str, ...]] = None,
) -> list[str]:
    """Name semantic inputs changed since the trusted full/global snapshot."""
    prior_manifest = index_surfaces.load_trusted_derivation_manifest(
        vault_root
    )
    prior = {
        (kind, path): (mode, content_sha256)
        for kind, path, mode, content_sha256 in prior_manifest
    }
    current = {
        (kind, path): (mode, content_sha256)
        for kind, path, mode, content_sha256 in current_manifest
    }
    changed_keys = {
        key
        for key in set(prior) | set(current)
        if prior.get(key) != current.get(key)
    }
    allowed_kinds = {'input', 'source', 'source-absence', 'symlink-target'}
    owned = {Path(path).as_posix() for path in owned_paths}
    allowed_virtual_paths = set(allowed_virtual_paths or ())
    # Prefix authorization exists because a virtual entry can DISAPPEAR: an
    # offline mount drops its sidecar observation entirely, so it is absent from
    # the current manifest and cannot be named by enumerating it.
    prefixes = tuple(allowed_virtual_prefixes or ())

    def _virtual_allowed(path: str) -> bool:
        return path in allowed_virtual_paths or (
            bool(prefixes) and path.startswith(prefixes)
        )

    return sorted({
        path
        for kind, path in changed_keys
        if path not in CLOCK_VIRTUAL_INPUTS
        and not (kind == 'virtual' and _virtual_allowed(path))
        and (kind not in allowed_kinds or path not in owned)
    })


def _archive_derivation_fingerprints() -> dict[str, str]:
    """Fingerprint every implementation family that can change archive rows.

    Git source movement proves the canonical inputs are unchanged.  These
    hashes separately prove the parser, ADR-047 predicate, Gardener overlay,
    and verified-cache implementation that derived those inputs are unchanged.
    """
    parser_path = Path(__file__).resolve()
    lib_dir = _TOOLS / 'lib'
    parser_runtime = (
        f'python={sys.version};'
        f'pyyaml={getattr(_yaml, "__version__", "absent")}'
    ).encode('utf-8')
    return {
        'parser': _named_content_sha256([
            (parser_path.name, parser_path.read_bytes()),
            ('runtime', parser_runtime),
        ]),
        'archive_predicate': _file_sha256(
            Path(index_surfaces.__file__).resolve()
        ),
        'gardener': _named_content_sha256([
            (name, (lib_dir / name).read_bytes())
            for name in (
                'gardener.py',
                'decay_gate.py',
                'cross_vault_member_of.py',
            )
        ]),
        'implementation': _file_sha256(
            Path(shard_index.__file__).resolve()
        ),
    }


def _archive_derivation_identity(
    vault_root: Path,
) -> tuple[Optional[dict[str, Any]], str]:
    """Return a complete conservative cache identity or explain refusal.

    Exact content/mode inventories cover only canonical source families and
    implementation/config inputs that can affect derivation. Runtime state
    (dirty counters, event streams/receipts, cursors) is intentionally absent.
    Canonical navblock-only worktree renders are stripped in process; relevant
    drift or an incomplete inventory remains fail-closed. Code/runtime hashes,
    repository clock date, wall-clock date, and raw compose.lock cover the
    remaining inputs that can alter Gardener-derived fields.
    """
    try:
        head_result = subprocess.run(
            ['git', '-C', str(vault_root), 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f'cannot resolve Git HEAD: {exc}'
    if head_result.returncode != 0:
        return None, f'cannot resolve Git HEAD: {head_result.stderr.strip()}'
    head = head_result.stdout.strip()

    worktree_proof, cleanliness_reason = _derivation_worktree_clean(
        vault_root,
        head,
    )
    if worktree_proof is None:
        return None, cleanliness_reason

    try:
        repo_clock_result = subprocess.run(
            ['git', '-C', str(vault_root), 'log', '-1', '--format=%ci'],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f'cannot resolve derivation repository clock: {exc}'
    if repo_clock_result.returncode != 0 or not repo_clock_result.stdout.strip():
        return None, (
            'cannot resolve derivation repository clock: '
            f'{repo_clock_result.stderr.strip()}'
        )

    compose_path = vault_root / shard_index.COMPOSE_LOCK_REL
    try:
        compose_raw = compose_path.read_bytes() if compose_path.is_file() else b''
    except OSError as exc:
        return None, f'cannot read compose.lock derivation input: {exc}'
    mounted_pins = {
        vault_uid: str(record.get('resolved_commit') or '')
        for vault_uid, record in sorted(
            shard_index.load_compose_lock_vaults(vault_root).items()
        )
        if isinstance(record, dict)
    }
    mounted_cache_identities: dict[str, dict] = {}
    try:
        expected_shard_identity = shard_index.shard_derivation_identity(
            process_file
        )
        for vault_uid, pin in mounted_pins.items():
            cached = shard_index.read_verified_jsonl_cache(
                shard_index.shard_jsonl_path(vault_root, vault_uid),
                shard_index.shard_meta_path(vault_root, vault_uid),
                cache_kind='mounted-vault-shard',
            )
            if cached is None:
                return None, (
                    f'active mount {vault_uid} has no complete verified shard cache'
                )
            _records, meta = cached
            if (
                meta.get('vault_uid') != vault_uid
                or meta.get('resolved_commit') != pin
                or meta.get('derivation_identity') != expected_shard_identity
            ):
                return None, (
                    f'active mount {vault_uid} shard identity is stale or incomplete'
                )
            mounted_cache_identities[vault_uid] = {
                'resolved_commit': pin,
                'jsonl_sha256': meta.get('jsonl_sha256'),
                'record_count': meta.get('record_count'),
                'derivation_identity': expected_shard_identity,
            }
    except shard_index.VerifiedCacheRefusal as exc:
        return None, f'cannot prove mounted-shard derivation inputs: {exc}'
    return {
        'derivation_input_sha256': worktree_proof[
            'derivation_input_sha256'
        ],
        'source_inventory_sha256': worktree_proof[
            'source_inventory_sha256'
        ],
        'source_inventory_count': len(worktree_proof['source_inventory']),
        'repo_clock_date': repo_clock_result.stdout.strip()[:10],
        'wall_clock_date': _dt.date.today().isoformat(),
        'compose_lock_sha256': hashlib.sha256(compose_raw).hexdigest(),
        'mounted_pins': mounted_pins,
        'mounted_cache_identities': mounted_cache_identities,
        'derivation_fingerprints': _archive_derivation_fingerprints(),
    }, 'complete'


def _now_iso() -> str:
    """UTC ISO-8601 timestamp for shard .meta derived_at (no tz dependency)."""
    return _dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _relative_source_path(path: Path, vault_root: Path) -> str:
    try:
        return path.relative_to(vault_root).as_posix()
    except ValueError:
        return path.as_posix()


def _skip_cached_archive_source(
    path: Path,
    vault_root: Path,
    skip_paths: Optional[set[str]],
) -> bool:
    return bool(
        skip_paths
        and _relative_source_path(path, vault_root) in skip_paths
    )


# ---------------------------------------------------------------------------
# Mentions Parser (v1.71 Edge-Substrate; 55c33476)
# ---------------------------------------------------------------------------
_MENTIONS_RE = re.compile(
    r'\[.*?\]\((?:(?:\.\./files/)|(?:vault/files/))?([0-9a-fA-F]{8})\.md\)'
    r'|(?<![a-zA-Z0-9_-])([0-9a-fA-F]{8})\.md(?![a-zA-Z0-9_-])'
    r'|\[\[([0-9a-fA-F]{8})\]\]'
)
_MOUNTED_MARKDOWN_MENTIONS_RE = re.compile(
    r'\[.*?\]\((?:(?:\.\./files/)|(?:vault/files/))?([0-9a-fA-F]{8})\.md\)'
    r'|(?<![a-zA-Z0-9_-])([0-9a-fA-F]{8})\.md(?![a-zA-Z0-9_-])'
)

_B8E4F1A3_MOD = None

def _get_mentions(
    body: str,
    src_uid: str,
    declared_pairs: set[tuple[str, str]],
    all_uids: set[str],
    *,
    include_wikilink_uids: bool = True,
) -> list[str]:
    """Parse body for UID mentions, dropping code fences, relations blocks, and 4 drop cases."""
    global _B8E4F1A3_MOD
    if _B8E4F1A3_MOD is None:
        b8_path = _TOOLS / "tropo-generate-relations-header.py"
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
    mentions_re = (
        _MENTIONS_RE
        if include_wikilink_uids
        else _MOUNTED_MARKDOWN_MENTIONS_RE
    )
    for match in mentions_re.finditer(body_stripped):
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


def _decode_yaml_single_quoted_scalar(value: str) -> Optional[str]:
    """Decode one valid YAML single-quoted flow scalar.

    YAML represents an apostrophe inside a single-quoted scalar as two
    consecutive apostrophes.  The first apostrophe not paired this way closes
    the scalar; anything after it is outside the scalar (normally whitespace
    and an inline comment).
    """
    if not value.startswith("'"):
        return None
    decoded: list[str] = []
    index = 1
    while index < len(value):
        char = value[index]
        if char != "'":
            decoded.append(char)
            index += 1
            continue
        if index + 1 < len(value) and value[index + 1] == "'":
            decoded.append("'")
            index += 2
            continue
        return ''.join(decoded)
    return None


@lru_cache(maxsize=8192)
def _field_re(prefix: str, field: str, suffix: str) -> "re.Pattern[str]":
    """Compile `prefix + escape(field) + suffix` ONCE per distinct field name.

    MEASURED 2026-08-09 (talos-t40, velocity item 1). A dry-run full rebuild
    called `re._compile` 877,263 times and actually compiled 160,296 patterns —
    24.0s of a 69s profiled run, the single largest line item. The cause is that
    the frontmatter readers built their pattern STRING on every call
    (`rf'^{re.escape(field)}:...'`), five of them per `detect_field_type`, across
    ~137k `get_scalar` and ~60k `detect_field_type` calls.

    `re` does memoize by pattern string, but its cache holds 512 entries and is
    CLEARED WHOLESALE on overflow. Enough distinct field names blow it on every
    file, which is why even the constant patterns elsewhere in this module were
    being recompiled: the thrash is global, so the cost lands on code that never
    built a dynamic pattern at all.

    Keyed on the three parts rather than the finished string so the escaping
    stays here and no call site can drift from the pattern it means.
    """
    return re.compile(prefix + re.escape(field) + suffix, re.MULTILINE)


def get_scalar(fm: str, field: str) -> Optional[str]:
    """Get a top-level scalar field. Strips quotes; handles multi-line block scalars."""
    # 1. Block scalar detection (| or >)
    m_block = _field_re('^', field, r':\s*([|>])\s*\n((?:\s+.*\n?)*)').search(fm)
    if m_block:
        content = m_block.group(2)
        if not content.strip(): return ""
        lines = content.splitlines()
        # Use first non-empty line to detect indent
        first_line = next((l for l in lines if l.strip()), lines[0])
        indent = len(first_line) - len(first_line.lstrip())
        return "\n".join(line[indent:] for line in lines).strip()

    # 2. Quoted or simple scalar
    m = _field_re('^', field, r':\s*(.*)$').search(fm)
    if not m: return None
    value = m.group(1).rstrip()
    if value.startswith('"'):
        end = value.find('"', 1)
        if end > 0: return value[1:end]
    if value.startswith("'"):
        decoded = _decode_yaml_single_quoted_scalar(value)
        if decoded is not None:
            return decoded
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
    inline = _field_re('^', field, r':\s*\[([^\]]*)\]\s*(?:#.*)?$').search(fm)
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
    block = _field_re('^', field, r':\s*(?:[|>]-?)?\s*\n((?:[ \t]*-.*\n?|[ \t]+.*\n?)+)').search(fm)
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
    if _field_re('^', field, r':\s*\[').search(fm): return 'list'
    if _field_re('^', field, r':\s*(?:[|>]-?)?\s*\n\s*-\s+').search(fm): return 'list'
    if _field_re('^', field, r':\s*\n\s+[a-zA-Z_"]').search(fm): return 'mapping'
    if _field_re('^', field, r':\s*([|>])').search(fm): return 'scalar'
    if _field_re('^', field, r':\s*\S').search(fm): return 'scalar'
    return 'absent'


def reflect_frontmatter(
    fm: str,
    *,
    pruning_eligible_markdown: bool = False,
) -> dict[str, Any]:
    """v1.15.1 Stream C: pass-through reflection of frontmatter beyond CORE_FIELDS.

    Returns a dict of {field_name: value} for every top-level frontmatter key NOT
    in CORE_FIELDS, with type-appropriate value (scalar string / list / skipped for
    nested mappings). Underscore-prefixed keys are denylisted (escape hatch convention).
    Mappings are skipped at v1.15.1 (queryability adds limited value vs serialization
    complexity), with one governed exception: core.capsule v1.7 requires the complete
    nested ``pruning`` verdict from eligible Markdown to project into JSONL and SQLite.
    Python/JSON sources never project it. Keep that exception targeted; this is not a
    general nested-map reflection expansion.
    """
    out: dict[str, Any] = {}
    parsed_pruning: Any = None
    pruning_loaded = False
    for key in get_all_top_level_keys(fm):
        if key in CORE_FIELDS:
            continue
        if key.startswith('_'):
            continue
        if key == 'pruning':
            if pruning_eligible_markdown and _yaml is not None:
                if not pruning_loaded:
                    try:
                        parsed = _yaml_safe_load(fm)
                        parsed_pruning = parsed.get('pruning') if isinstance(parsed, dict) else None
                    except Exception:
                        parsed_pruning = None
                    pruning_loaded = True
                if isinstance(parsed_pruning, dict):
                    out[key] = parsed_pruning
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


def _derived_row_title(fm: str, filepath: Path) -> str:
    """The index row's DISPLAY title, derived — never written back to source.

    Governed files under `agents/` and `.tropo/` carry no `title:`; an agent
    activation names itself with `agent_name:`. They are indexed because they
    carry a uid and a type, so 28 rows projected an empty title and the cockpit
    showed blank entries for real records.

    The wrong fix is stamping `title:` into 28 identity files to satisfy a
    derived surface — that edits substrate to please a projection. So the title
    is DERIVED here, at projection time, and the source file is never touched.
    Precedence ruled by Argus A145 (2026-08-08): title, then agent_name, then
    name, then the filename stem, which always exists and is never empty.

    Derived through the module's CANONICAL YAML PARSER, not get_scalar. get_scalar
    is a line matcher: it strips the outer quotes of a double-quoted scalar but does
    not YAML-decode escaped inner quotes, so a valid title such as
    `"\\"Import your work\\" — Get-Started onboarding step"` projected as a single
    backslash, and process_file then wrote that corruption into JSONL and onward to
    SQLite and FTS. One file in 4,740 uses an escaped quote in a title, which is why
    it went unseen until the row-freshness check (6c538b6a AC2) asked whether rows
    still agree with their files.

    The parser is the one this module already trusts for pruning, structured
    frontmatter and record bodies — routing one more field through it rather than
    adding a decoder. get_scalar remains the fallback for a frontmatter block YAML
    cannot parse at all: a malformed file should still project a usable display
    title rather than collapse to its filename stem.
    """
    parsed: Any = None
    try:
        loaded = _yaml_safe_load(fm)
        if isinstance(loaded, dict):
            parsed = loaded
    except Exception:
        parsed = None  # unparseable frontmatter — fall back per key below
    for key in ('title', 'agent_name', 'name'):
        value = ''
        if parsed is not None:
            raw = parsed.get(key)
            if raw is not None and not isinstance(raw, (dict, list)):
                value = str(raw).strip()
        if not value:
            value = (get_scalar(fm, key) or '').strip()
        if value:
            return value
    return filepath.stem


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
        text = _parser_canonical_derivation_bytes(
            filepath,
            filepath.read_bytes(),
        ).decode('utf-8', errors='replace')
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
    if uid_override is not None and fm_uid != uid:
        return None

    stage, state = normalize_stage_state(fm)
    member_of = [u for u in get_list(fm, 'member_of') if UID_RE.match(u)]
    created = get_scalar(fm, 'created') or '2026-01-01'
    source_title = _derived_row_title(fm, filepath)

    record: dict[str, Any] = {
        'uid':            uid,
        'type':           get_scalar(fm, 'type') or 'document',
        'title':          source_title,
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
    reflected = reflect_frontmatter(
        fm,
        pruning_eligible_markdown=filepath.suffix.lower() == '.md',
    )
    for key, value in reflected.items():
        if key not in record:
            record[key] = value
    if _yaml is not None:
        try:
            structured_frontmatter = _yaml_safe_load(fm)
        except Exception:
            structured_frontmatter = None
        if isinstance(structured_frontmatter, dict):
            for field in ("relations", "relationships"):
                value = structured_frontmatter.get(field)
                if isinstance(value, (list, dict)):
                    record[field] = value

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
    source_title = _derived_row_title(fm, filepath)

    record: dict[str, Any] = {
        'uid':            uid,
        'type':           get_scalar(fm, 'type') or 'tool',
        'title':          source_title,
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
    reflected = reflect_frontmatter(
        fm,
        pruning_eligible_markdown=ext == '.md',
    )
    for key, value in reflected.items():
        if key not in record:
            record[key] = value

    return record


def collect_vault_actions_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
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
        if _skip_cached_archive_source(f, vault_root, skip_paths):
            continue
        # ADR-045/ADR-048: shipped actions renamed to tropo-<name>.md; UID read from frontmatter.
        rec = process_tool_file(f)  # same parser as vault/tools/
        if rec is not None:
            if rec.get('type') == 'tool':
                rec['type'] = 'action'  # correct type if not declared in frontmatter
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


def collect_vault_session_agents_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
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
        if _skip_cached_archive_source(f, vault_root, skip_paths):
            continue
        rec = process_tool_file(f)  # same parser as vault/tools/
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


def collect_vault_agents_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
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
        if _skip_cached_archive_source(f, vault_root, skip_paths):
            continue
        rec = process_file(f)
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


def collect_vault_playbooks_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
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
        if _skip_cached_archive_source(f, vault_root, skip_paths):
            continue
        rec = process_file(f)
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


def collect_vault_skills_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Scan vault/skills/ for .md files; return index records.

    v1.74 (Talos T20 2026-06-21) — first-class vault/skills/ indexing per
    how-to.capsule unification. Unified skill entries live at
    vault/skills/<uid>.md (type:how-to).
    """
    out: list[dict[str, Any]] = []
    skills_dir = vault_root / 'vault' / 'skills'
    if not skills_dir.is_dir():
        return out
    for f in sorted(skills_dir.iterdir()):
        if f.suffix.lower() != '.md':
            continue
        if _skip_cached_archive_source(f, vault_root, skip_paths):
            continue
        # ADR-045/ADR-048: shipped skills renamed to tropo-<name>.md; UID read from frontmatter.
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
            rec['path'] = str(f.relative_to(vault_root))
            out.append(rec)
    return out


def collect_studio_memory_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Scan .tropo-studio/memory/entries/*.md for studio-scope memory entries.

    v1.79 Memory Sovereignty (Talos T24 2026-07-03) — memory entries written via
    tropo-memory-write skill live at .tropo-studio/memory/entries/<uid>.md but were
    not picked up by any prior source scan. Closes the index-registration gap Metis G87
    surfaced at her boot (event 00005467): rebuild wiped manually-added rows, and the
    manual-fallback in the skill was therefore futile. Fix: first-class scan here so
    every rebuild correctly registers studio-scope memory entries.
    """
    out: list[dict[str, Any]] = []
    memory_dir = vault_root / '.tropo-studio' / 'memory' / 'entries'
    if not memory_dir.is_dir():
        return out
    for f in sorted(memory_dir.glob('*.md')):
        if not UID_RE.match(f.stem):
            continue
        if _skip_cached_archive_source(f, vault_root, skip_paths):
            continue
        rec = process_file(f)
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))
            out.append(rec)
    return out


def collect_agent_memory_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Scan agents/*/.tropo-capsule/memory/entries/*.md for agent-scope memory entries.

    v1.79 Memory Sovereignty (Talos T24 2026-07-03) — agent-scope memory entries live
    under agents/<slug>/.tropo-capsule/memory/entries/. The existing collect_agents_records()
    explicitly excludes .tropo-capsule/ directories (ephemeral workspace exclusion) so
    these entries were never indexed. This dedicated scanner closes the gap: it targets
    only the memory/entries/ leaf — not the full .tropo-capsule/ tree — so no unintended
    workspace content is swept in. Symmetric fix to collect_studio_memory_records above.
    """
    out: list[dict[str, Any]] = []
    agents_dir = vault_root / 'agents'
    if not agents_dir.is_dir():
        return out
    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        memory_dir = agent_dir / '.tropo-capsule' / 'memory' / 'entries'
        if not memory_dir.is_dir():
            continue
        for f in sorted(memory_dir.glob('*.md')):
            if not UID_RE.match(f.stem):
                continue
            if _skip_cached_archive_source(f, vault_root, skip_paths):
                continue
            rec = process_file(f)
            if rec is not None:
                rec['path'] = str(f.relative_to(vault_root))
                out.append(rec)
    return out


def collect_vault_tools_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
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
        # ADR-045/ADR-048: shipped tools renamed to tropo-<name>.py; UID read from frontmatter.
        # Non-shipped tools still have UID stems. process_tool_file handles both cases.
        # Skip only test sub-directories; accept any .py/.md/.json at this level.
        if f.is_dir():
            continue
        if _skip_cached_archive_source(f, vault_root, skip_paths):
            continue
        rec = process_tool_file(f)
        if rec is not None:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Studio-root scan (v1.15.1 Stream G)
# ---------------------------------------------------------------------------

def collect_studio_root_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Scan Studio-root *.md files; return index records for any with uid: frontmatter.

    Closes the v1.14 substrate gap: STUDIO.md + TROPO-CAPABILITIES.md (and any future
    Studio-root entries with uid:) become indexed without being moved into vault/files/.
    Studio-root files keep their canonical home at the root by documented exception.
    """
    out: list[dict[str, Any]] = []
    for f in sorted(vault_root.glob('*.md')):
        if _skip_cached_archive_source(f, vault_root, skip_paths):
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


def collect_agents_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
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
        if _skip_cached_archive_source(f, vault_root, skip_paths):
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


def collect_tropo_kernel_records(vault_root: Path, skip_paths=None) -> "list[dict[str, Any]]":
    out: "list[dict[str, Any]]" = []
    admitted, _skipped = _tropo_kernel_sources(vault_root)
    for f in admitted:
        if _skip_cached_archive_source(f, vault_root, skip_paths):
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
            rec['path'] = str(f.relative_to(vault_root))
            out.append(rec)
    return out


def collect_capsule_records(
    vault_root: Path,
    skip_paths: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
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
    substrate. Capsule .md files keep their canonical home at vault/capsules/ — same
    shape as Studio-root exception per collect_studio_root_records above.
    ADR-045 One Home (v1.76; e8d49d3a): canonical home is vault/capsules/.
    """
    out: list[dict[str, Any]] = []
    capsules_dir = vault_root / 'vault' / 'capsules'
    if not capsules_dir.is_dir():
        return out
    for f in sorted(capsules_dir.glob('*.md')):
        if not (f.name.endswith('.capsule.md') or f.name.endswith('.history.md')):
            continue
        if _skip_cached_archive_source(f, vault_root, skip_paths):
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
_STRUCTURED_EDGE_RELATION_KEYS = (
    "predicate", "rel", "relation", "type", "kind",
)
_STRUCTURED_EDGE_TARGET_KEYS = (
    "target_uid", "uid", "target", "to", "dst_uid",
)


def iter_record_edges(record: dict) -> Iterable[tuple[str, str]]:
    """Yield canonical scalar/list and typed structured graph relations."""
    seen: set[tuple[str, str]] = set()

    def emit(relation: Any, target: Any) -> Iterable[tuple[str, str]]:
        relation_text = str(relation or "").strip()
        target_text = str(target or "").strip()
        pair = (relation_text, target_text)
        if relation_text and target_text and pair not in seen:
            seen.add(pair)
            yield pair

    for field in _EDGE_FIELDS:
        values = record.get(field)
        if isinstance(values, str):
            values = [values]
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str):
                    yield from emit(field, value)

    for container_name in ("relations", "relationships"):
        container = record.get(container_name)
        if isinstance(container, dict):
            for relation, values in container.items():
                if isinstance(values, str):
                    values = [values]
                if isinstance(values, list):
                    for target in values:
                        if isinstance(target, str):
                            yield from emit(relation, target)
            continue
        if not isinstance(container, list):
            continue
        for item in container:
            if not isinstance(item, dict):
                continue
            relation = next(
                (
                    item.get(key)
                    for key in _STRUCTURED_EDGE_RELATION_KEYS
                    if item.get(key)
                ),
                None,
            )
            target = next(
                (
                    item.get(key)
                    for key in _STRUCTURED_EDGE_TARGET_KEYS
                    if item.get(key)
                ),
                None,
            )
            yield from emit(relation, target)


# Core frontmatter columns stored as first-class columns in `entries`.
# Everything else is in fm_json for json_extract access.
_CORE_COLS = {
    'uid', 'type', 'title', 'status', 'state', 'stage',
    'created', 'modified', 'author', 'extraction_scope',
}

_FTS_BODY_CAP = None  # 8364626c fix: no cap — full body indexed (was 6000, truncated entries)

#: Extensions whose bytes are text we can meaningfully full-text index. A
#: mounted .docx/.pptx/.png has its identity in a sidecar and its bytes are not
#: searchable text, so it is skipped rather than indexed as mojibake.
_MOUNTED_TEXT_SUFFIXES = frozenset({'.md', '.markdown', '.txt', '.rst', '.org'})

#: Hard ceiling on a single mounted file read into FTS. The vault's own bodies
#: are uncapped (8364626c) because we author them; a mount points at content we
#: do not control, so one pathological file must not blow up a rebuild.
_MOUNTED_FTS_MAX_BYTES = 4 * 1024 * 1024


def _fts_body_for_out_of_tree_entry(rec: dict, body: str, files_dir: Path) -> str:
    """Body for a governed file whose canonical home is NOT `vault/files/`.

    Bodies are read from `vault/files/<uid>.md`, so anything governed that lives
    elsewhere indexed with an EMPTY body and was invisible to content search.
    Measured 2026-08-02: capsules 83/83 empty, tools 66/66, studio memory 37/37,
    plus every agent-owned file. Roughly 350 entries with no searchable text.

    This is not only a search gap. `entries_fts.body` is the crown's content
    source (`distiller_content.SqliteContentLoader`), so the distiller could not
    read a single CAPSULE -- the surface our own doctrine names as holding the
    design truth ("CAPSULES HAVE THE TRUTH"). It was reading around them.

    Deliberately narrow: it only FILLS AN EMPTY body, so no existing indexed
    body changes. Frontmatter-derived columns are untouched and still resolve
    exactly as before; only the searchable text is added.
    """

    if body:
        return body
    rel = rec.get('path')
    if not isinstance(rel, str) or not rel.strip():
        return body
    try:
        root = files_dir.parent.parent
        target = (root / rel.strip()).resolve()
        if not str(target).startswith(str(root.resolve())):
            return body  # never read outside the studio via a crafted path
        # Executable/tool sources remain a separate policy decision. This fill
        # is limited to the already-approved human-readable text family.
        if target.suffix.lower() not in _MOUNTED_TEXT_SUFFIXES:
            return body
        if not target.is_file():
            return body
        if target.stat().st_size > _MOUNTED_FTS_MAX_BYTES:
            return body
        text = target.read_text(encoding='utf-8', errors='replace')
    except (OSError, ValueError):
        return body
    return _strip_frontmatter_body(text)


_FOLDER_MOUNTS_REL = Path('.tropo-studio/folder-mounts.json')
_WIKILINK_RE = re.compile(r'(?<!!)\[\[([^\[\]\n]+)\]\]')


def _safe_mount_relative(value: Any) -> Optional[Path]:
    """Return a normalized, containment-safe mount-relative path."""
    if not isinstance(value, str) or not value.strip():
        return None
    relative = Path(value.strip().replace('\\', '/'))
    if relative.is_absolute() or '..' in relative.parts:
        return None
    return relative


def _mounted_relative_text(value: Any) -> Optional[str]:
    relative = _safe_mount_relative(value)
    if relative is None or not relative.parts:
        return None
    return relative.as_posix()


def _read_mounted_regular_bytes(
    mount_root: Path,
    relpath: str,
    *,
    max_bytes: int,
) -> tuple[str, Optional[bytes], Optional[int]]:
    """Read one mount-relative regular file from stable no-follow descriptors.

    Every path component is opened relative to the already-opened parent.
    Descriptor and directory-entry identities must agree before and after the
    bounded read, so symlinks, special files, and rename/swap races fail closed.
    """
    relative = _safe_mount_relative(relpath)
    if relative is None or not relative.parts:
        return 'unavailable', None, None
    nofollow = getattr(os, 'O_NOFOLLOW', 0)
    cloexec = getattr(os, 'O_CLOEXEC', 0)
    directory = getattr(os, 'O_DIRECTORY', 0)
    nonblock = getattr(os, 'O_NONBLOCK', 0)
    opened: list[int] = []
    try:
        root_fd = os.open(
            os.fspath(mount_root),
            os.O_RDONLY | directory | nofollow | cloexec,
        )
        opened.append(root_fd)
        if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
            return 'unavailable', None, None
        parent_fd = root_fd
        for component in relative.parts[:-1]:
            child_fd = os.open(
                component,
                os.O_RDONLY | directory | nofollow | cloexec,
                dir_fd=parent_fd,
            )
            opened.append(child_fd)
            if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
                return 'unavailable', None, None
            parent_fd = child_fd

        leaf = relative.parts[-1]
        named_before = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        source_fd = os.open(
            leaf,
            os.O_RDONLY | nofollow | cloexec | nonblock,
            dir_fd=parent_fd,
        )
        opened.append(source_fd)
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(named_before.st_mode)
            or (before.st_dev, before.st_ino)
            != (named_before.st_dev, named_before.st_ino)
        ):
            return 'unavailable', None, None
        if before.st_size > max_bytes:
            return 'bounded', None, before.st_size

        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining > 0:
            chunk = os.read(source_fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b''.join(chunks)
        after = os.fstat(source_fd)
        named_after = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        identity_fields = (
            'st_dev',
            'st_ino',
            'st_mode',
            'st_size',
            'st_mtime_ns',
            'st_ctime_ns',
        )
        if (
            len(raw) != before.st_size
            or any(getattr(before, field) != getattr(after, field)
                   for field in identity_fields)
            or any(getattr(before, field) != getattr(named_after, field)
                   for field in ('st_dev', 'st_ino', 'st_mode', 'st_size'))
        ):
            return 'unavailable', None, None
        return 'ok', raw, before.st_size
    except (OSError, ValueError):
        return 'unavailable', None, None
    finally:
        for fd in reversed(opened):
            try:
                os.close(fd)
            except OSError:
                pass


def _wikilink_key(value: str) -> str:
    """Normalize an Obsidian link alias without inventing fuzzy matching."""
    normalized = unicodedata.normalize('NFKC', value).strip().replace('\\', '/')
    normalized = re.sub(r'/+', '/', normalized).strip('/')
    for suffix in _MOUNTED_TEXT_SUFFIXES:
        if normalized.casefold().endswith(suffix):
            normalized = normalized[:-len(suffix)]
            break
    return normalized.casefold()


class _MountedSourceCatalog:
    """Authoritative mounted-source resolver and mount-scoped alias index.

    The folder-mount registry owns the current root. ``mount_relpath`` (or an
    authoritative sidecar found under that root) owns the path within it.
    Projection ``source_path`` is deliberately never consulted: it is an
    advisory absolute handle and is precisely the value that goes stale after
    a cloud-folder move.
    """

    def __init__(
        self,
        vault_root: Path,
        records: Iterable[dict],
        *,
        registry_raw: Optional[bytes] = None,
    ) -> None:
        self.vault_root = Path(vault_root).resolve()
        self.records = [record for record in records if isinstance(record, dict)]
        self.mounts: dict[str, dict] = {}
        self._sources: dict[str, dict[str, Any]] = {}
        self._bindings: dict[str, dict[str, Any]] = {}
        self._sidecars: dict[
            str,
            dict[str, list[tuple[str, dict[str, Any], str]]],
        ] = {}
        self._sidecars_by_path: dict[
            str,
            dict[str, tuple[dict[str, Any], str]],
        ] = {}
        self._path_aliases: dict[str, dict[str, set[str]]] = {}
        self._stem_aliases: dict[str, dict[str, set[str]]] = {}
        self._title_aliases: dict[str, dict[str, set[str]]] = {}
        self._uid_aliases: dict[str, dict[str, set[str]]] = {}
        self.registry_schema_version = 0
        registry_path = self.vault_root / _FOLDER_MOUNTS_REL
        self.registry_raw = b''
        try:
            self.registry_raw = (
                bytes(registry_raw)
                if registry_raw is not None
                else registry_path.read_bytes()
            )
            registry_text = self.registry_raw.decode('utf-8')
            registry = json.loads(registry_text)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
            registry = {}
        if isinstance(registry, dict):
            try:
                self.registry_schema_version = int(
                    registry.get('schema_version') or 0
                )
            except (TypeError, ValueError):
                self.registry_schema_version = 0
        raw_mounts = registry.get('mounts') if isinstance(registry, dict) else {}
        if isinstance(raw_mounts, dict):
            self.mounts = {
                str(uid): raw
                for uid, raw in raw_mounts.items()
                if isinstance(raw, dict)
            }
        self._build_aliases()

    def _mount_root(self, mount_uid: str) -> Optional[Path]:
        mount = self.mounts.get(mount_uid)
        if not mount:
            return None
        if mount.get('state') != 'adopted':
            return None
        # A REMOTE MACHINE'S BLINDNESS IS NOT THIS MACHINE'S TRUTH.
        #
        # `availability` lives in `.tropo-studio/folder-mounts.json`, which is
        # git-tracked and therefore shared. But the fact it records -- can I open
        # this path? -- is PER-MACHINE. `reconcile` on a box that cannot see the
        # folder writes `unavailable`, that commit reaches every other machine,
        # and this gate then refused to resolve a mount whose folder was sitting
        # on local disk, readable.
        #
        # Measured 2026-08-06 (metis-g103, finding 728f4bf7): mount 1e6a0b5d
        # points at Mike's iCloud path, so any Linux box reconciling it marks it
        # unavailable and all 54 mounted bodies go dark on Mike's Mac -- proven
        # by running this resolver against the live registry with the flag
        # flipped, while `is_file()` on the target returned True throughout.
        #
        # So the flag no longer gates. The lstat() below already answers the
        # reachability question locally and correctly, and it is the answer that
        # matters: if the folder is here, we can read it; if it is not, the stat
        # fails and we return None regardless of what any registry says. The
        # persisted value stays as an operator-facing record of what some
        # machine last saw -- advisory, never authority.
        #
        # This does NOT weaken identity. A path that exists locally but holds
        # DIFFERENT content is caught per record by the sidecar/digest binding
        # in verify_available_projection_binding(), which is what that check is
        # for. Reachability and identity are separate questions; conflating them
        # is what made one machine able to blind all the others.
        raw = mount.get('path')
        if not isinstance(raw, str) or not raw.strip():
            return None
        try:
            root = Path(os.path.abspath(Path(raw).expanduser()))
            root_stat = root.lstat()
        except (OSError, ValueError):
            return None
        return root if stat.S_ISDIR(root_stat.st_mode) else None

    def _sidecars_for_mount(
        self,
        mount_uid: str,
        mount_root: Path,
    ) -> dict[str, list[tuple[str, dict[str, Any], str]]]:
        cached = self._sidecars.get(mount_uid)
        if cached is not None:
            return cached
        found, by_path = mounted_projection_trust.load_sidecar_catalog(
            mount_root,
            max_bytes=_MOUNTED_FTS_MAX_BYTES,
        )
        self._sidecars[mount_uid] = found
        self._sidecars_by_path[mount_uid] = by_path
        return found

    def _projection_binding(
        self,
        record: dict,
        mount_uid: str,
        mount_root: Path,
    ) -> dict[str, Any]:
        uid = str(record.get('uid') or '')
        cached = self._bindings.get(uid)
        if cached is not None:
            return cached
        sidecars = self._sidecars_for_mount(mount_uid, mount_root)
        by_path = self._sidecars_by_path.get(mount_uid, {})
        result = mounted_projection_trust.verify_available_projection_binding(
            record,
            mount_uid=mount_uid,
            mount=self.mounts.get(mount_uid),
            mount_root=mount_root,
            sidecars=sidecars,
            sidecars_by_path=by_path,
        )
        self._bindings[uid] = result
        return result

    def _cached_extracted_text(self, uid, mount_root, relpath):
        """Searchable text for a mounted binary, or None to keep it non-text.

        Reads the extractor's cache; it never extracts. Extraction costs ~340ms
        a document, so a 1,000-document corpus would add ~6 minutes to EVERY
        rebuild -- `sync` fills the cache, the index only reads it. Two gestures
        on purpose (metis-g104, cdadf603).

        Every failure returns None, which means today's `available-nontext`.
        Deliberately NOT `unavailable`: that status trips the
        MOUNTED-FTS-BODY-LOSS guard and freezes every index write in the studio,
        which is exactly the P0 (254a360b) we spent 2026-08-07 on. "I have no
        text for this" and "the disk is gone" are different facts.
        """
        extractor = _extract_text_module()
        if extractor is None:
            return None
        if Path(relpath).suffix.lower() not in extractor.EXTRACTABLE:
            return None

        # Cache first, on purpose. No cache entry means we touch the source
        # file zero times -- no stat, no hash, no download.
        record = extractor.cache_read(self.vault_root, str(uid))
        if not isinstance(record, dict):
            return None

        target = Path(mount_root) / relpath
        try:
            st = target.lstat()
        except OSError:
            return None
        # A cloud placeholder is not a file yet. Hashing one reads it, and
        # reading one DOWNLOADS it: 90.6% of Mike's SharePoint mount is
        # SF_DATALESS (2,319 of 2,560, 10.45 GB). The extractor already refuses
        # to touch these; an index that stats its way into a download would
        # undo that from the other side.
        if getattr(st, 'st_flags', 0) & extractor.SF_DATALESS:
            return None
        if not stat.S_ISREG(st.st_mode):
            return None

        if not extractor.is_current(record, extractor.sha256_of(target)):
            return None  # stale cache: never serve text for content that moved on

        status = record.get('status')
        if status == 'empty':
            # A real answer, not a gap. The document genuinely holds no text,
            # so it must not be re-extracted forever chasing one.
            return '', record.get('content_sha256')
        if status != 'ok':
            return None
        text = record.get('text')
        if not isinstance(text, str) or text == '':
            return None
        if len(text.encode('utf-8', 'surrogateescape')) > _MOUNTED_FTS_MAX_BYTES:
            return None  # same ceiling the byte path already enforces
        return text, record.get('content_sha256')

    def source(self, record: dict) -> dict[str, Any]:
        uid = str(record.get('uid') or '')
        cached = self._sources.get(uid)
        if cached is not None:
            return cached
        mount_uid = str(record.get('mount_uid') or '')
        unavailable = {
            'mount_uid': mount_uid,
            'status': 'unavailable',
            'path': None,
            'relpath': None,
            'text': None,
            'raw': None,
            'content_sha256': None,
            'sidecar_input': None,
            'trust_reason': None,
            # Where a body CAME FROM, which is a different question from
            # whether we have one. 'read' = decoded from the source bytes;
            # 'derived' = produced from them by a separate pass (today: the
            # text extractor, cdadf603).
            #
            # MOUNTED-FTS-BODY-LOSS refuses a populated body going empty
            # because for a READ body that is evidence of loss -- the case
            # metis-g99 built it for, and it stays hard. For a DERIVED body it
            # means only that we hold no current derivation: normal, curable,
            # and `tropo-extract-text.py sync` is the cure.
            #
            # This is a property rather than a third entry on the guard's
            # exemption list. An exemption list is a record of everything that
            # ever confused a guard; the next derived source (OCR over a
            # scanned PDF) would have been a fourth, and by then nobody would
            # remember why the list existed. Mike, 2026-08-08: sick of patching
            # layers of fixes over each other. Ruled by metis-g104 the same
            # night, ceiling raised deliberately to allow it.
            'origin': 'read',
        }
        # ABSENCE OF THE FIELD IS NOT EVIDENCE OF ABSENCE OF THE FILE.
        #
        # `availability` is stamped by the post-migration writer, so a LEGACY
        # projection has no such field. Reading "missing" as "unavailable"
        # silently blanked the body of every not-yet-migrated mounted file --
        # on the studio's first real folder mount that meant Mike's notes,
        # sitting readable on local disk, vanished from search AND from the
        # crown, with no signal at all.
        #
        # "Not yet migrated" and "the disk is gone" are different facts and only
        # the second should suppress content. An explicit non-available value is
        # still honoured, which is what makes the offline tombstone work; only
        # the SILENT case falls through, and it falls through to a real read
        # that fails closed on its own if the file is genuinely unreachable.
        # (metis-g99 2026-08-02, mirrors the mount-level legacy_available above.)
        # The fall-through is NOT gated on the registry schema version.
        #
        # It was, on `< 2`, and that expired. metis-g104's `adopt` rewrote
        # folder-mounts.json at schema_version 2 on 2026-08-07, which retired
        # the carve-out for every pre-existing mounted record in the same
        # instant: 42 projections whose files were readable on local disk all
        # resolved `unavailable`, MOUNTED-FTS-BODY-LOSS correctly refused to
        # blank them, and every index write in the studio froze (P0, 254a360b).
        # Nobody narrowed the carve-out -- a version number moved.
        #
        # A compatibility bridge with an expiry condition will expire, on a day
        # nobody chose. This one had already been removed one level up: the
        # mount-level gate above is resolved live per machine for the same
        # reason, because the read answers the question and the flag only
        # remembers someone else's answer. This is its surviving twin.
        #
        # The version added nothing it could not get from the read below, which
        # fails closed on its own when the file is genuinely unreachable.
        # test_mounted_content_phase2.LegacyRecordCarveOutMustNotExpireTests
        # goes red if it is ever re-gated, on any version number.
        declared_availability = record.get('availability')
        legacy_record = declared_availability is None
        if not mount_uid or (
            declared_availability != 'available' and not legacy_record
        ):
            self._sources[uid] = unavailable
            return unavailable
        mount = self.mounts.get(mount_uid)
        if not isinstance(mount, dict):
            result = {
                **unavailable,
                'status': 'untrusted',
                'trust_reason': 'mount-unregistered',
            }
            self._sources[uid] = result
            return result
        if mount.get('state') != 'adopted':
            result = {
                **unavailable,
                'status': 'untrusted',
                'trust_reason': 'mount-not-adopted',
            }
            self._sources[uid] = result
            return result
        # The same shared-flag gate as _mount_root() above, and removed for the
        # same reason: this refused a body because SOME machine could not see the
        # folder. `_mount_root()` is called a few lines down and stats the path
        # here, on this machine, which is the only place the question can be
        # answered. If the folder is genuinely gone, that stat fails and we
        # return `unavailable` anyway -- so the tombstone behaviour every
        # MountedAvailabilityTests case pins is preserved; what is gone is one
        # machine's ability to impose its blindness on the rest.
        # (metis-g103 2026-08-06, finding 728f4bf7. Fixing only _mount_root left
        # this one still refusing -- found by asserting on status rather than on
        # the body, which is the check that would have hidden it.)
        if record.get('type') == 'project':
            result = {
                **unavailable,
                'status': 'available-nontext',
            }
            self._sources[uid] = result
            return result
        mount_root = self._mount_root(mount_uid)
        if mount_root is None:
            self._sources[uid] = unavailable
            return unavailable
        binding = self._projection_binding(
            record, mount_uid, mount_root
        )
        if binding.get('status') != 'verified':
            result = {
                **unavailable,
                'status': 'untrusted',
                'relpath': binding.get('relpath'),
                'sidecar_input': binding.get('sidecar_input'),
                'trust_reason': binding.get('reason'),
            }
            self._sources[uid] = result
            return result
        relpath = str(binding['relpath'])
        sidecar_input = binding.get('sidecar_input')

        # Folder mirrors and opaque artifacts are available identities, but
        # never use their projection boilerplate as searchable body text.
        if Path(relpath).suffix.lower() not in _MOUNTED_TEXT_SUFFIXES:
            extracted = self._cached_extracted_text(uid, mount_root, relpath)
            if extracted is not None:
                text, content_hash = extracted
                result = {
                    **unavailable,
                    'status': 'available-text',
                    'relpath': relpath,
                    'text': text,
                    # An extraction has no authoritative source BYTES -- the
                    # docx on disk is a zip, not this text. b'' is reserved
                    # downstream for "verified zero-byte source", which an
                    # empty EXTRACTION genuinely is: the document really has no
                    # text, so an empty body is an answer and not a loss.
                    'raw': b'' if text == '' else None,
                    'content_sha256': content_hash,
                    'sidecar_input': sidecar_input,
                    'origin': 'derived',
                }
                self._sources[uid] = result
                return result
            # An extractable binary with no CURRENT extraction is still a
            # derived body -- we simply do not hold the derivation right now.
            # This is the flag the guard reads when a .docx that was searchable
            # yesterday goes empty because someone edited it: nothing was lost,
            # the cache went stale, and `sync` restores it. A non-extractable
            # source (.png, a folder mirror) stays 'read': it has no text
            # because there is no text, and its body was never populated, so
            # the guard never looks at it either way.
            result = {
                **unavailable,
                'status': 'available-nontext',
                'relpath': relpath,
                'sidecar_input': sidecar_input,
                'origin': (
                    'derived' if _is_extractable_suffix(relpath) else 'read'
                ),
            }
            self._sources[uid] = result
            return result
        read_status, raw, size = _read_mounted_regular_bytes(
            mount_root,
            relpath,
            max_bytes=_MOUNTED_FTS_MAX_BYTES,
        )
        if read_status == 'bounded':
            result = {
                **unavailable,
                'status': 'available-bounded',
                'relpath': relpath,
                'size': size,
                'sidecar_input': sidecar_input,
            }
            self._sources[uid] = result
            return result
        if read_status != 'ok' or raw is None:
            result = {
                **unavailable,
                'relpath': relpath,
                'sidecar_input': sidecar_input,
            }
            self._sources[uid] = result
            return result
        try:
            # Strict UTF-8 preserves every source byte round-trip. Invalid text
            # is unreadable for this text-only index and therefore fails closed.
            text = raw.decode('utf-8')
        except UnicodeError:
            result = {
                **unavailable,
                'relpath': relpath,
                'sidecar_input': sidecar_input,
            }
            self._sources[uid] = result
            return result
        result = {
            **unavailable,
            'status': 'available-text',
            'relpath': relpath,
            'text': text,
            'raw': raw,
            'content_sha256': hashlib.sha256(raw).hexdigest(),
            'sidecar_input': sidecar_input,
        }
        self._sources[uid] = result
        return result

    @staticmethod
    def _offer(
        aliases: dict[str, dict[str, set[str]]],
        mount_uid: str,
        alias: str,
        uid: str,
    ) -> None:
        key = _wikilink_key(alias)
        if key:
            aliases.setdefault(mount_uid, {}).setdefault(key, set()).add(uid)

    def _build_aliases(self) -> None:
        for record in self.records:
            uid = str(record.get('uid') or '')
            mount_uid = str(record.get('mount_uid') or '')
            if not UID_RE.fullmatch(uid) or mount_uid not in self.mounts:
                continue
            # Alias identity comes from authoritative metadata, not source
            # readability. A temporarily missing target remains a stable graph
            # destination; only an unavailable *source note* loses its outgoing
            # body-derived edges.
            mount_root = self._mount_root(mount_uid)
            if mount_root is None:
                continue
            binding = self._projection_binding(
                record,
                mount_uid,
                mount_root,
            )
            if binding.get('status') != 'verified':
                continue
            relpath = str(binding['relpath'])
            if relpath:
                relative = Path(relpath)
                self._offer(
                    self._path_aliases, mount_uid, relative.as_posix(), uid
                )
                self._offer(
                    self._stem_aliases, mount_uid, relative.stem, uid
                )
            title = record.get('title')
            if isinstance(title, str) and title.strip():
                self._offer(self._title_aliases, mount_uid, title, uid)
            self._offer(self._uid_aliases, mount_uid, uid, uid)

    def manifest_entries(self) -> tuple[tuple[str, str, str, str], ...]:
        entries: dict[tuple[str, str], tuple[str, str, str, str]] = {}
        for mount_uid, mount in self.mounts.items():
            if not UID_RE.fullmatch(mount_uid):
                continue
            registry_path = f'@mounted-registry/{mount_uid}'
            entries[('virtual', registry_path)] = (
                'virtual',
                registry_path,
                'virtual',
                hashlib.sha256(
                    json.dumps(
                        mount,
                        separators=(',', ':'),
                        sort_keys=True,
                    ).encode('utf-8')
                ).hexdigest(),
            )
        for record in self.records:
            uid = str(record.get('uid') or '')
            mount_uid = str(record.get('mount_uid') or '')
            if not UID_RE.fullmatch(uid) or not UID_RE.fullmatch(mount_uid):
                continue
            source = self.source(record)
            source_path = f'@mounted-source/{mount_uid}/{uid}'
            state = {
                'content_sha256': source.get('content_sha256'),
                'relpath': source.get('relpath'),
                'size': source.get('size'),
                'status': source.get('status'),
                'trust_reason': source.get('trust_reason'),
            }
            digest = hashlib.sha256(
                json.dumps(
                    state,
                    separators=(',', ':'),
                    sort_keys=True,
                ).encode('utf-8')
            ).hexdigest()
            entries[('virtual', source_path)] = (
                'virtual',
                source_path,
                'virtual',
                digest,
            )
            sidecar_input = source.get('sidecar_input')
            if (
                isinstance(sidecar_input, tuple)
                and len(sidecar_input) == 2
            ):
                sidecar_relpath, sidecar_sha256 = sidecar_input
                sidecar_path = f'@mounted-sidecar/{mount_uid}/{uid}'
                entries[('virtual', sidecar_path)] = (
                    'virtual',
                    sidecar_path,
                    'virtual',
                    hashlib.sha256(
                        f'{sidecar_relpath}\0{sidecar_sha256}'.encode('utf-8')
                    ).hexdigest(),
                )
        return tuple(sorted(entries.values()))

    def signature(self) -> tuple[str, tuple[tuple[str, str, str, str], ...]]:
        return hashlib.sha256(self.registry_raw).hexdigest(), self.manifest_entries()

    def virtual_paths_for_mounts(self, mount_uids: set[str]) -> set[str]:
        prefixes = tuple(
            f'@mounted-{kind}/{mount_uid}/'
            for mount_uid in sorted(mount_uids)
            for kind in ('source', 'sidecar')
        )
        paths = {
            path
            for _kind, path, _mode, _digest in self.manifest_entries()
            if path.startswith(prefixes)
        }
        paths.update(
            f'@mounted-registry/{mount_uid}'
            for mount_uid in mount_uids
        )
        # Offline transitions deliberately drop consumed sidecar bytes from the
        # current manifest. Keep both stable virtual identities authorized for
        # every record in the mount-wide dependency batch so the corresponding
        # prior sidecar entry may disappear without being misclassified as an
        # unrelated derivation input.
        for record in self.records:
            mount_uid = str(record.get('mount_uid') or '')
            uid = str(record.get('uid') or '')
            if mount_uid not in mount_uids or not UID_RE.fullmatch(uid):
                continue
            paths.add(f'@mounted-source/{mount_uid}/{uid}')
            paths.add(f'@mounted-sidecar/{mount_uid}/{uid}')
        return paths

    def resolve_wikilink(
        self,
        record: dict,
        raw_target: str,
    ) -> tuple[Optional[str], str, tuple[str, ...]]:
        mount_uid = str(record.get('mount_uid') or '')
        target = raw_target.split('|', 1)[0].strip()
        target = target.split('#', 1)[0].strip()
        key = _wikilink_key(target)
        if not key:
            return None, 'wikilink-alias-missing', ()

        # A slash is an explicit mount-relative path. Bare aliases retain and
        # union every UID/stem/title candidate; any collision is ambiguous.
        if '/' in target.replace('\\', '/'):
            candidates = set(
                self._path_aliases.get(mount_uid, {}).get(key, set())
            )
        else:
            candidates = set(
                self._uid_aliases.get(mount_uid, {}).get(key, set())
            )
            candidates.update(
                self._stem_aliases.get(mount_uid, {}).get(key, set())
            )
            candidates.update(
                self._title_aliases.get(mount_uid, {}).get(key, set())
            )
        if len(candidates) == 1:
            return next(iter(candidates)), '', tuple(sorted(candidates))
        if len(candidates) > 1:
            return (
                None,
                'wikilink-alias-ambiguous',
                tuple(sorted(candidates)),
            )
        return None, 'wikilink-alias-missing', ()

    def wikilink_rows(
        self,
        record: dict,
        text: str,
    ) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str, str, str]]]:
        uid = str(record.get('uid') or '')
        mount_uid = str(record.get('mount_uid') or '')
        scrubbed = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        scrubbed = re.sub(r'`[^`\n]*`', '', scrubbed)
        edges: set[tuple[str, str, str]] = set()
        observations: set[tuple[str, str, str, str, str]] = set()
        for match in _WIKILINK_RE.finditer(scrubbed):
            raw = match.group(1).strip()
            target_uid, kind, candidates = self.resolve_wikilink(record, raw)
            if target_uid and target_uid != uid:
                edges.add((uid, 'mentions', target_uid))
                continue
            if target_uid == uid:
                continue
            observations.add((
                uid,
                kind,
                raw,
                mount_uid,
                json.dumps(candidates, separators=(',', ':')),
            ))
        return sorted(edges), sorted(observations)


def _fts_body_with_mounted_source(
    rec: dict,
    body: str,
    *,
    vault_root: Optional[Path] = None,
    catalog: Optional[_MountedSourceCatalog] = None,
) -> str:
    """Use a MOUNTED file's own text as its indexed body for full-text search.

    A mounted file lives outside the studio; `vault/files/<uid>.md` is only a
    derived stub holding identity and a pointer, so indexing that stub alone
    makes the content unsearchable -- searching the studio for a word that
    appears in a mounted note returned nothing (metis-g99, first real folder
    mount, 2026-08-02). This reads the source and indexes THAT, so search
    covers the content while the file is never copied into the vault.

    It REPLACES the stub body rather than appending to it, for two reasons that
    both matter more than they look:

    1. `entries_fts.body` is not only a search corpus. It is the crown's
       content source -- `distiller_content.SqliteContentLoader` reads exact
       body bytes from this column and cuts the verbatim spans it cites, with
       character offsets. Appending would make every offset for a mounted file
       relative to a stub+source concatenation, so a citation would not line up
       with the real file, and the first span of every note would be projection
       boilerplate plus an absolute machine path instead of the author's words.
    2. Every stub carries the same boilerplate ("vault projection",
       "Relations", "regenerable"), so appending makes those words match every
       mounted entry. Measured before this fix: 200+ hits each, all noise.

    For a mounted file the content IS the source. Offset 0 is the first
    character the human wrote.

    Fails SOFT and closed by design. A mount is on removable, cloud-synced, or
    unplugged storage; it is unavailable often and that is NORMAL. The identity
    and title row remain, but a mounted row never falls back to projection
    boilerplate or stale cached content.
    """
    if not rec.get('mount_uid'):
        return body
    if catalog is None:
        if vault_root is None:
            return ''
        catalog = _MountedSourceCatalog(vault_root, [rec])
    source = catalog.source(rec)
    return source['text'] if source.get('status') == 'available-text' else ''

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
    capsules_dir = vault_root / 'vault' / 'capsules'
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
            parsed = _yaml_safe_load(fm_text)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        rollup = parsed.get('meta_status_rollup')
        if rollup is None:
            continue  # no block declared — silent skip

        type_name = capsule_path.name.split('.capsule.md')[0]
        # ADR-045/048 One Home: shipped capsules carry the tropo- filename prefix
        # (tropo-document.capsule.md governs type 'document'). The prefix is a
        # namespace token, not part of the governed type name — strip it, or every
        # rollup keys as 'tropo-<type>', matches no entry, and the whole studio
        # resolves lifecycle-N/A (the 2026-07-01 M2-at-scale regression; argus-a122).
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


# ── Shared per-record → index-row transform (single source: full rebuild + rebuild --only) ──
# Extracted from build_sqlite_index so the incremental freshen (freshen_one / `--only <uid>`)
# and the full rebuild derive every entry's row IDENTICALLY — no second implementation to drift
# (brief d7b3f1a9 §4 design-property #3). Argus A106 2026-06-09.
_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)


def _raw_scalar(fm_text: str, field: str) -> Optional[str]:
    """Extract a raw scalar from YAML frontmatter text without laundering (store-raw)."""
    m = _field_re('^', field, r':\s*(.*)$').search(fm_text)
    if not m:
        return None
    val = m.group(1).strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    if not (m.group(1).strip().startswith('"') or m.group(1).strip().startswith("'")):
        if '#' in val:
            val = val.split('#', 1)[0].rstrip()
    return val or None


def _record_to_index_rows(
    rec: dict,
    files_dir: Path,
    declared_pairs: Optional[set[tuple[str, str]]] = None,
    all_uids: Optional[set[str]] = None,
    source_raw: Optional[bytes] = None,
) -> tuple:
    """One IndexRecord → (entry_row, edge_rows, fts_row) for vault/00-index.sqlite.
    SINGLE SOURCE shared by build_sqlite_index (full) and freshen_one (rebuild --only).
    Core columns read raw frontmatter from vault/files/<uid>.md (never laundered)."""
    # NOTE: for a MOUNTED file the vault entry is a derived stub carrying no
    # body, so FTS alone would index the pointer and not the content. See
    # _fts_body_with_mounted_source() below, called at the fts_row build.
    uid = rec.get('uid', '')
    raw_fm: Optional[str] = None
    body = ''
    fp = files_dir / f'{uid}.md'
    if source_raw is not None or fp.exists():
        try:
            file_text = _parser_canonical_derivation_bytes(
                fp,
                source_raw if source_raw is not None else fp.read_bytes(),
            ).decode('utf-8', errors='replace')
            fm_m = _FRONTMATTER_RE.match(file_text)
            if fm_m:
                raw_fm = fm_m.group(1)
                body = file_text[fm_m.end():].strip()
            else:
                body = file_text.strip()
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

    # JSONL is the canonical parsed representation.  SQLite and FTS must use
    # that same title rather than independently projecting raw YAML syntax.
    projected_title = str(rec.get('title') or '')

    mo = rec.get('member_of')
    if isinstance(mo, list) and mo:
        mo_primary: Optional[str] = str(mo[0])
    elif isinstance(mo, str) and mo:
        mo_primary = mo
    else:
        mo_primary = None

    entry_row = (
        uid, raw_type, projected_title, raw_status, raw_state, raw_stage,
        raw_created, raw_modified, raw_author, raw_scope, mo_primary,
        raw_ac, json.dumps(rec, separators=(',', ':')),
    )

    edge_rows: list[tuple] = [
        (uid, relation, target)
        for relation, target in iter_record_edges(rec)
    ]

    if declared_pairs is not None and all_uids is not None:
        mentions = _get_mentions(body, uid, declared_pairs, all_uids)
        for m in mentions:
            edge_rows.append((uid, 'mentions', m))

    # Body precedence is intentional and strict:
    #   1. Preserve an existing vault/files body byte-for-byte.
    #   2. Fill an empty ordinary canonical row from its governed source path.
    #   3. For anything claiming mounted semantics, ignore both values here;
    #      _record_to_derived_rows replaces them with a verified source body or
    #      an empty body after the availability/provenance gate.
    canonical_body = _fts_body_for_out_of_tree_entry(rec, body, files_dir)
    fts_row = (
        uid,
        projected_title,
        _fts_body_with_mounted_source(rec, canonical_body),
    )
    return entry_row, edge_rows, fts_row


def _record_to_derived_rows(
    rec: dict,
    files_dir: Path,
    *,
    catalog: _MountedSourceCatalog,
    declared_pairs: Optional[set[tuple[str, str]]] = None,
    all_uids: Optional[set[str]] = None,
    source_raw: Optional[bytes] = None,
) -> tuple[tuple, list[tuple], tuple, list[tuple]]:
    """Derive SQLite rows, including availability-gated mounted observations."""
    entry_row, edge_rows, fts_row = _record_to_index_rows(
        rec,
        files_dir,
        source_raw=source_raw,
    )
    uid = str(rec.get('uid') or '')
    if not rec.get('mount_uid'):
        if declared_pairs is not None and all_uids is not None:
            body = fts_row[2]
            edge_rows.extend(
                (uid, 'mentions', target)
                for target in _get_mentions(
                    body, uid, declared_pairs, all_uids
                )
            )
        return entry_row, edge_rows, fts_row, []

    # Mounted projections take precedence over the ordinary canonical-source
    # fill above. Only a verified, available text source may contribute body
    # bytes; every unavailable, invalid, opaque, or bounded source stays empty.
    source = catalog.source(rec)
    status = source.get('status')
    if status == 'unavailable':
        # Availability is a hard derivation gate. Even if a stale projection
        # still carries relations, an unreadable/missing/orphaned source cannot
        # retain any outgoing edge derived from that source.
        return entry_row, [], (uid, fts_row[1], ''), []
    if status == 'untrusted':
        reason = str(source.get('trust_reason') or 'unknown')
        observation = (
            uid,
            'mounted-source-provenance-invalid',
            reason,
            str(rec.get('mount_uid') or ''),
            '[]',
        )
        # A row claiming mounted-source semantics without verified projection
        # provenance cannot contribute projection metadata, body text, or graph
        # edges. Keeping only identity plus a named observation makes the
        # failure inspectable without ever trusting the claimed source path.
        return entry_row, [], (uid, fts_row[1], ''), [observation]

    source_text = source.get('text')
    observations: list[tuple] = []
    if status == 'available-text' and isinstance(source_text, str):
        if declared_pairs is not None and all_uids is not None:
            edge_rows.extend(
                (uid, 'mentions', target)
                for target in _get_mentions(
                    source_text,
                    uid,
                    declared_pairs,
                    all_uids,
                    include_wikilink_uids=False,
                )
            )
        wikilink_edges, observations = catalog.wikilink_rows(rec, source_text)
        edge_rows.extend(wikilink_edges)
        fts_row = (uid, fts_row[1], source_text)
    else:
        # Opaque and over-bound sources keep metadata relations, but never index
        # projection boilerplate and cannot produce body-derived relations.
        fts_row = (uid, fts_row[1], '')

    edge_rows = sorted(set(edge_rows))
    return entry_row, edge_rows, fts_row, observations


def _assert_mounted_fts_body_transitions(
    records: Iterable[dict[str, Any]],
    fts_rows: Iterable[tuple[str, str, str]],
    prior_bodies: dict[str, str],
    catalog: _MountedSourceCatalog,
) -> None:
    """Refuse an unexplained populated-to-empty mounted crown transition."""
    records_by_uid = {
        str(record.get("uid")): record
        for record in records
        if record.get("uid") and record.get("mount_uid")
    }
    refusals: list[tuple[str, str]] = []
    went_dark: list[str] = []
    for uid, _title, proposed_body in fts_rows:
        prior_body = prior_bodies.get(uid)
        record = records_by_uid.get(uid)
        if record is None or not prior_body or proposed_body != "":
            continue

        source = catalog.source(record)
        # A verified zero-byte source is positive evidence that the user
        # cleared the file; preserve that authoritative empty body.
        if (
            source.get("status") == "available-text"
            and source.get("raw") == b""
        ):
            continue

        # Explicit tombstones intentionally remove stale searchable content
        # while retaining the stable mounted identity and link target.
        mount = catalog.mounts.get(str(record.get("mount_uid") or ""))
        record_availability = record.get("availability")
        mount_availability = (
            mount.get("availability") if isinstance(mount, dict) else None
        )
        if (
            record_availability in {"unavailable", "ambiguous"}
            or mount_availability in {"unavailable", "ambiguous"}
        ):
            continue

        # A DERIVED body going empty is not evidence of loss. We hold no
        # current derivation -- the source is right there, readable, and
        # `sync` reproduces the text. A READ body going empty IS evidence of
        # loss, and that is the case this guard was built for; it stays hard.
        #
        # Reported rather than silent, which is the whole point and not a
        # softening of it: a body disappearing without a word is exactly what
        # metis-g99 built this guard to prevent, and "curable" is not the same
        # as "invisible-worthy" (metis-g104's ruling, 2026-08-08).
        if source.get("origin") == "derived":
            went_dark.append(uid)
            continue

        refusals.append((uid, str(source.get("status") or "unknown")))

    if went_dark:
        print(
            f"[MOUNTED-TEXT] {len(went_dark)} derived body/bodies have no current "
            f"extraction and are no longer searchable: "
            f"{', '.join(sorted(went_dark)[:8])}"
            f"{' …' if len(went_dark) > 8 else ''}\n"
            f"  cure: python3 vault/tools/tropo-extract-text.py sync",
            file=sys.stderr,
        )

    if refusals:
        rendered = ", ".join(
            f"{uid} [{status}]" for uid, status in sorted(refusals)
        )
        raise index_surfaces.IndexSurfaceRefusal(
            "MOUNTED-FTS-BODY-LOSS: populated mounted body would become empty "
            f"without an explicit tombstone or verified zero-byte source: {rendered}"
        )


DIRTY_COUNTER_DEFAULT_THRESHOLD = 50


def _invalidate_archive_cache(vault_root: Path) -> None:
    """Drop only the derived local-archive cache after an incremental mutation."""
    for path in (
        vault_root / ARCHIVE_CACHE_JSONL_REL,
        vault_root / ARCHIVE_CACHE_META_REL,
    ):
        path.unlink(missing_ok=True)


def _dirty_counter_path(vault_root: Path) -> Path:
    return vault_root / ".tropo-studio" / "dirty-counter.json"


def _dirty_counter_replacement(
    vault_root: Path,
    *,
    reset: bool = False,
) -> tuple[Path, bytes, int]:
    """Prepare the next counter image without mutating its transaction."""
    path = _dirty_counter_path(vault_root)
    data: dict = {}
    if reset:
        data = {
            "writes_since_full_rebuild": 0,
            "last_full_rebuild": _dt.date.today().isoformat(),
        }
    else:
        if path.is_file():
            try:
                data = json.loads(path.read_text())
            except Exception:
                data = {}
        data["writes_since_full_rebuild"] = (
            int(data.get("writes_since_full_rebuild", 0)) + 1
        )
    data["last_updated"] = _dt.date.today().isoformat()
    raw = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return path, raw, data["writes_since_full_rebuild"]


def _incremental_maintenance_replacements(
    vault_root: Path,
) -> tuple[tuple[Path, bytes], ...]:
    """Prepare cache invalidation and one counter bump for the index journal."""
    replacements = [
        (path, b"")
        for path in (
            vault_root / ARCHIVE_CACHE_JSONL_REL,
            vault_root / ARCHIVE_CACHE_META_REL,
        )
        if path.is_file()
    ]
    counter_path, counter_raw, _count = _dirty_counter_replacement(vault_root)
    replacements.append((counter_path, counter_raw))
    return tuple(replacements)


def _bump_dirty_counter(vault_root: Path, *, reset: bool = False) -> int:
    """Governed Autonomy S2 (bba40cd7): writes-since-full-rebuild counter.
    freshen_one/remove_one each increment it (an incremental write the next
    full rebuild hasn't yet reconciled); a successful --apply full rebuild
    resets it to 0. The caller holds the cross-surface index lock; this write
    is atomic and fail-loud so a reportedly-successful governed birth cannot
    silently lose its maintenance increment."""
    path, raw, count = _dirty_counter_replacement(vault_root, reset=reset)
    index_surfaces._write_bytes_atomic(path, raw)
    return count


def dirty_counter_status(vault_root: Path, threshold: int = DIRTY_COUNTER_DEFAULT_THRESHOLD) -> dict:
    """Query helper for boot steps / maintenance loops (Governed Autonomy S2
    acceptance criterion: "drive the counter over threshold -> exactly one
    boot health line recommends the full pass"). Returns
    {count, threshold, over_threshold, last_full_rebuild}. Never raises --
    an unreadable/absent counter file reads as count=0 (nothing dirty yet)."""
    path = _dirty_counter_path(vault_root)
    count = 0
    last_full_rebuild = None
    if path.is_file():
        try:
            data = json.loads(path.read_text())
            count = int(data.get("writes_since_full_rebuild", 0))
            last_full_rebuild = data.get("last_full_rebuild")
        except Exception:
            pass
    return {"count": count, "threshold": threshold, "over_threshold": count > threshold,
            "last_full_rebuild": last_full_rebuild}


def _apply_gardener_to_fresh_record(
    rec: dict,
    vault_root: Path,
) -> tuple[dict, dict[str, Any]]:
    """Apply the full-rebuild Gardener transform to one incremental record.

    Governed Autonomy S2 AC-10 requires an incremental row to be byte-identical
    to the row a subsequent full rebuild derives.  ``process_file()`` alone
    cannot satisfy that contract: the full path also stamps extraction-scope
    backfill, segment, wall-clock age, decay, and inbound-live-edge fields.

    Reuse the SAME ``apply_gardener_pass`` over the current+archive union with
    this UID replaced by its freshly parsed source record.  This is O(index)
    in memory (no source-tree scan) and preserves Law 3: one transform, N
    consumers.  The private sidecar is not written on an incremental freshen;
    the row fields are still exactly the shared pass's result.
    """
    records, gardener_stats, _changed = _apply_gardener_to_fresh_records(
        [rec],
        vault_root,
    )
    return records[0], gardener_stats


def _apply_gardener_to_fresh_records(
    fresh_records: list[dict],
    vault_root: Path,
) -> tuple[list[dict], dict[str, Any], list[dict]]:
    """Run one coherent Gardener pass with the complete fresh batch installed."""
    from lib.gardener import apply_gardener_pass

    fresh_by_uid = {
        str(record.get("uid")): record
        for record in fresh_records
        if record.get("uid")
    }
    if len(fresh_by_uid) != len(fresh_records):
        raise RuntimeError("Gardener batch contains a missing or duplicate UID")
    candidate_union = index_surfaces.load_index_records(
        vault_root,
        include_archive=True,
        require_complete_union=True,
    )
    before_by_uid = {
        str(record.get("uid")): json.dumps(
            record,
            separators=(",", ":"),
            sort_keys=True,
        )
        for record in candidate_union
        if record.get("uid")
    }
    installed: set[str] = set()
    for index, existing in enumerate(candidate_union):
        uid = str(existing.get("uid") or "")
        if uid in fresh_by_uid:
            candidate_union[index] = fresh_by_uid[uid]
            installed.add(uid)
    for uid in sorted(set(fresh_by_uid) - installed):
        candidate_union.append(fresh_by_uid[uid])

    gardener_stats = apply_gardener_pass(
        vault_root,
        candidate_union,
        apply_writes=False,
    )
    transformed = {
        str(candidate.get("uid")): candidate
        for candidate in candidate_union
        if str(candidate.get("uid") or "") in fresh_by_uid
    }
    missing = set(fresh_by_uid) - set(transformed)
    if missing:
        raise RuntimeError(
            "Gardener pass lost fresh UID(s) " + ", ".join(sorted(missing))
        )
    changed = [
        record
        for record in candidate_union
        if before_by_uid.get(str(record.get("uid"))) != json.dumps(
            record,
            separators=(",", ":"),
            sort_keys=True,
        )
    ]
    return (
        [transformed[str(record["uid"])] for record in fresh_records],
        gardener_stats,
        changed,
    )


def _prepare_sqlite_image(
    sqlite_path: Path,
    mutator: Callable[[sqlite3.Connection], bool],
) -> tuple[bytes, bool]:
    """Mutate an isolated SQLite copy and return its durable byte image."""
    try:
        original = sqlite_path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f'cannot snapshot {sqlite_path}: {exc}') from exc
    fd, tmp_name = tempfile.mkstemp(
        prefix=f'.{sqlite_path.name}.',
        suffix='.transaction-copy',
        dir=str(sqlite_path.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    sidecars = [
        Path(str(tmp_path) + suffix) for suffix in ('-journal', '-wal', '-shm')
    ]
    conn: Optional[sqlite3.Connection] = None
    try:
        with tmp_path.open('wb') as handle:
            handle.write(original)
            handle.flush()
            os.fsync(handle.fileno())
        conn = sqlite3.connect(str(tmp_path))
        conn.execute('PRAGMA journal_mode=DELETE')
        conn.execute('BEGIN')
        changed = bool(mutator(conn))
        conn.commit()
        conn.close()
        conn = None
        with tmp_path.open('rb') as handle:
            os.fsync(handle.fileno())
        return tmp_path.read_bytes(), changed
    except Exception:
        if conn is not None:
            conn.rollback()
            conn.close()
        raise
    finally:
        tmp_path.unlink(missing_ok=True)
        for sidecar in sidecars:
            sidecar.unlink(missing_ok=True)


def _projection_record_from_bytes(
    uid: str,
    path: Path,
    raw: Optional[bytes],
) -> Optional[dict[str, Any]]:
    if raw is None:
        return process_file(path, uid_override=uid) if path.is_file() else None
    with tempfile.TemporaryDirectory(prefix='tropo-mounted-dependency-') as tmp:
        staged_path = Path(tmp) / f'{uid}.md'
        staged_path.write_bytes(raw)
        return process_file(staged_path, uid_override=uid)


def _mounted_batch_dependency_uids(
    uids: tuple[str, ...],
    vault_root: Path,
    staged: dict[Path, bytes],
) -> tuple[tuple[str, ...], set[str]]:
    """Expand alias-affecting writes to every record in the affected mount."""
    existing = index_surfaces.load_index_records(
        vault_root,
        include_archive=True,
        require_complete_union=True,
    )
    requested = set(uids)
    affected_mounts = {
        str(record.get('mount_uid'))
        for record in existing
        if str(record.get('uid') or '') in requested
        and record.get('mount_uid')
    }
    files_dir = vault_root / 'vault' / 'files'
    incoming: dict[str, dict[str, Any]] = {}
    for uid in uids:
        path = (files_dir / f'{uid}.md').resolve()
        record = _projection_record_from_bytes(uid, path, staged.get(path))
        if record is None:
            continue
        incoming[uid] = record
        if record.get('mount_uid'):
            affected_mounts.add(str(record['mount_uid']))
    if not affected_mounts:
        return tuple(sorted(requested)), set()
    expanded = requested | {
        str(record.get('uid'))
        for record in existing
        if record.get('uid')
        and str(record.get('mount_uid') or '') in affected_mounts
    }
    expanded.update(
        uid
        for uid, record in incoming.items()
        if str(record.get('mount_uid') or '') in affected_mounts
    )
    return tuple(sorted(expanded)), affected_mounts


def _registry_bytes_on_disk(vault_root: Path) -> Optional[bytes]:
    """The folder-mount registry as it currently is, or None when absent."""
    try:
        return (vault_root / _FOLDER_MOUNTS_REL).read_bytes()
    except OSError:
        return None


def freshen_many(
    uids: Iterable[str],
    vault_root: Path,
    *,
    source_replacements: Optional[dict[Path, bytes]] = None,
    companion_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
    require_absent_sources: Optional[Iterable[Path]] = None,
) -> int:
    """Serialize one multi-UID upsert across JSONL, SQLite, seals, and caches."""
    normalized = tuple(sorted(set(uids)))
    if not normalized:
        print('[rebuild --batch] no UIDs supplied', file=sys.stderr)
        return 2
    try:
        with index_surfaces.index_write_lock(vault_root):
            return _freshen_many_locked(
                normalized,
                vault_root,
                source_replacements=source_replacements,
                companion_replacements=companion_replacements,
                require_absent_sources=require_absent_sources,
            )
    except index_surfaces.IndexLockTimeout as exc:
        print(f'[rebuild --batch] {exc}', file=sys.stderr)
        return 1


def _freshen_many_locked(
    uids: tuple[str, ...],
    vault_root: Path,
    *,
    source_replacements: Optional[dict[Path, bytes]] = None,
    companion_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
    require_absent_sources: Optional[Iterable[Path]] = None,
) -> int:
    """Re-derive every owned UID and commit one recoverable index transaction."""
    companion_replacements = tuple(companion_replacements or ())
    invalid = [uid for uid in uids if not UID_RE.match(uid)]
    if invalid:
        print(
            f'[rebuild --batch] invalid 8-hex UID(s): {", ".join(invalid)}',
            file=sys.stderr,
        )
        return 2
    files_dir = vault_root / 'vault' / 'files'
    requested_paths = {uid: files_dir / f'{uid}.md' for uid in uids}
    staged = {
        Path(path).resolve(): raw
        for path, raw in (source_replacements or {}).items()
    }
    create_only = {
        Path(path).resolve()
        for path in (require_absent_sources or ())
    }
    if set(staged) - {path.resolve() for path in requested_paths.values()}:
        print(
            '[rebuild --batch] staged source set exceeds requested UIDs',
            file=sys.stderr,
        )
        return 2
    if create_only - set(staged):
        print(
            '[rebuild --batch] create-only source set must be a subset of staged '
            'source replacements',
            file=sys.stderr,
        )
        return 2
    collisions = []
    for path in sorted(create_only):
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            print(
                f'[rebuild --batch] cannot inspect create-only source {path}: {exc}; '
                'no source or derived rows written',
                file=sys.stderr,
            )
            return 1
        collisions.append(path)
    if collisions:
        print(
            '[rebuild --batch] mint collision inside index lock: '
            + ', '.join(str(path) for path in collisions)
            + '; refusing to overwrite existing source',
            file=sys.stderr,
        )
        return 1
    try:
        uids, affected_mounts = _mounted_batch_dependency_uids(
            uids,
            vault_root,
            staged,
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(f'[rebuild --batch] {exc}; no derived rows written', file=sys.stderr)
        return 1
    paths = {
        uid: (files_dir / f'{uid}.md').resolve()
        for uid in uids
    }
    missing = [
        str(path)
        for path in paths.values()
        if not path.is_file() and path not in staged
    ]
    if missing:
        print(
            '[rebuild --batch] governed source(s) absent: '
            + ', '.join(missing)
            + '; no derived rows written',
            file=sys.stderr,
        )
        return 1
    try:
        provenance_schema = index_surfaces.trusted_index_provenance_schema(
            vault_root
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(f'[rebuild --batch] {exc}; no derived rows written', file=sys.stderr)
        return 1
    if provenance_schema == 2 and staged:
        print(
            '[rebuild --batch] staged projection transaction requires current '
            'schema-3 surfaces; run one source-complete rebuild first',
            file=sys.stderr,
        )
        return 1
    if provenance_schema == 2:
        return rebuild_index(
            vault_root,
            True,
            _index_lock_held=True,
            _force_source_complete=True,
        )

    owned_paths = {
        path.relative_to(vault_root).as_posix() for path in paths.values()
    }
    # THE BATCH PATH IS THE ONE AGENTS ACTUALLY TAKE.
    #
    # I optimised _freshen_one_locked first and then measured the real gesture:
    # `tropo-mint-id.py --type note` took 7.16s while `rebuild --only` took
    # 1.39s. The mint routes through freshen_many, which still paid the full
    # whole-vault proof — 13,287 posix.open calls. Optimising the path nobody
    # takes is its own lesson: measure the PRODUCT, not the CLI you happened to
    # be holding. (metis-g103 2026-08-06)
    #
    # Same inheritance as the single path; see _inherited_derivation_snapshot
    # for the ruling, what is preserved (derivation code still blocks) and what
    # is deliberately given up.
    _inherited_batch_snapshot = True
    source_snapshot_before, source_scope_reason = _inherited_derivation_snapshot(
        vault_root,
        owned_paths,
    )
    if source_snapshot_before is None:
        # Bootstrap: nothing to inherit yet. Pay the full capture ONCE, which is
        # what mints the manifest every later batch inherits.
        _inherited_batch_snapshot = False
        source_snapshot_before, source_scope_reason = (
            _verify_incremental_source_scope(
                vault_root,
                owned_paths,
                defer_semantic_scope_to_trusted_manifest=True,
            )
        )
    if source_snapshot_before is None:
        print(
            '[rebuild --batch] REFUSAL: source inventory incomplete; '
            f'{source_scope_reason}. Run a full --apply; no derived rows written.',
            file=sys.stderr,
        )
        return 1

    records: list[dict[str, Any]] = []
    for uid in uids:
        if paths[uid] in staged:
            with tempfile.TemporaryDirectory(prefix='tropo-staged-projection-') as tmp:
                staged_path = Path(tmp) / f'{uid}.md'
                staged_path.write_bytes(staged[paths[uid]])
                record = process_file(staged_path, uid_override=uid)
        else:
            record = process_file(paths[uid], uid_override=uid)
        if record:
            record['path'] = paths[uid].relative_to(vault_root).as_posix()
        if not record or record.get('uid') != uid:
            print(
                f'[rebuild --batch] {uid}: could not parse its governed projection; '
                'no derived rows written',
                file=sys.stderr,
            )
            return 1
        records.append(record)
    try:
        records, gardener_stats, changed_records = _apply_gardener_to_fresh_records(
            records,
            vault_root,
        )
    except Exception as exc:
        print(
            f'[rebuild --batch] Gardener transform failed — {exc}; '
            'no derived rows written',
            file=sys.stderr,
        )
        return 1

    catalog_records = index_surfaces.load_index_records(
        vault_root,
        include_archive=True,
        require_complete_union=True,
    )
    fresh_by_uid = {str(record['uid']): record for record in records}
    catalog_records = [
        fresh_by_uid.get(str(record.get('uid')), record)
        for record in catalog_records
    ]
    present = {str(record.get('uid')) for record in catalog_records}
    catalog_records.extend(
        fresh_by_uid[uid] for uid in sorted(set(fresh_by_uid) - present)
    )
    registry_raw = next(
        (
            raw
            for path, raw in companion_replacements
            if Path(path).resolve()
            == (vault_root / _FOLDER_MOUNTS_REL).resolve()
        ),
        None,
    )
    catalog = _MountedSourceCatalog(
        vault_root,
        catalog_records,
        registry_raw=registry_raw,
    )
    mounted_signature_before = catalog.signature()
    all_uids = {
        str(record.get('uid'))
        for record in catalog_records
        if record.get('uid')
    }
    declared_pairs = {
        (str(record.get('uid')), target)
        for record in catalog_records
        if record.get('uid')
        for _relation, target in iter_record_edges(record)
    }

    row_sets: list[tuple[str, tuple, list[tuple], tuple, list[tuple]]] = []
    for record in records:
        uid = str(record["uid"])
        entry_row, edge_rows, fts_row, observation_rows = _record_to_derived_rows(
            record,
            files_dir,
            catalog=catalog,
            declared_pairs=declared_pairs,
            all_uids=all_uids,
            source_raw=staged.get(paths[uid]),
        )
        row_sets.append((
            uid,
            entry_row,
            edge_rows,
            fts_row,
            observation_rows,
        ))
    changed_by_uid = {
        str(record.get("uid")): record for record in changed_records
    }
    for record in records:
        changed_by_uid[str(record["uid"])] = record
    changed_records = [
        changed_by_uid[uid] for uid in sorted(changed_by_uid)
    ]

    sqlite_path = vault_root / 'vault' / '00-index.sqlite'
    if not sqlite_path.is_file():
        print(
            f'[rebuild --batch] {sqlite_path} absent — run a full rebuild first',
            file=sys.stderr,
        )
        return 1
    with sqlite3.connect(sqlite_path) as prior_connection:
        prior_mounted_fts_bodies = {
            row[0]: row[1]
            for row in prior_connection.execute(
                'SELECT uid, body FROM entries_fts WHERE uid IN ('
                + ','.join('?' for _ in row_sets)
                + ')',
                tuple(uid for uid, *_rest in row_sets),
            ).fetchall()
        }
    try:
        _assert_mounted_fts_body_transitions(
            records,
            (
                fts_row
                for _uid, _entry, _edges, fts_row, _observations in row_sets
            ),
            prior_mounted_fts_bodies,
            catalog,
        )
        route_plan = index_surfaces.plan_records_route(
            vault_root,
            changed_records,
        )
    except (ValueError, index_surfaces.IndexSurfaceRefusal) as exc:
        print(f'[rebuild --batch] {exc}; no derived rows written', file=sys.stderr)
        return 1
    route_before = {
        str(record.get('uid')): record
        for record in route_plan.current_before + route_plan.archive_before
        if record.get('uid')
    }
    route_after = {
        str(record.get('uid')): record
        for record in route_plan.current_after + route_plan.archive_after
        if record.get('uid')
    }
    route_changed_uids = {
        uid
        for uid in set(route_before) | set(route_after)
        if route_before.get(uid) != route_after.get(uid)
    }

    # Must match the shape of the "before" snapshot, and cover the SAME owned
    # set, or the equality check below compares two different things and refuses
    # every batch.
    if _inherited_batch_snapshot:
        source_snapshot_after, snapshot_reason = _inherited_derivation_snapshot(
            vault_root,
            owned_paths,
        )
    else:
        source_snapshot_after, snapshot_reason = (
            _capture_exact_derivation_snapshot(vault_root)
        )
    if source_snapshot_after is None:
        print(
            f'[rebuild --batch] REFUSAL: {snapshot_reason}; no derived rows written',
            file=sys.stderr,
        )
        return 1
    if source_snapshot_before != source_snapshot_after:
        print(
            '[rebuild --batch] REFUSAL: exact derivation inputs changed while '
            'the batch was parsed; no derived rows written',
            file=sys.stderr,
        )
        return 1
    mounted_catalog_after = _MountedSourceCatalog(
        vault_root,
        catalog_records,
        registry_raw=registry_raw,
    )
    if mounted_signature_before != mounted_catalog_after.signature():
        print(
            '[rebuild --batch] REFUSAL: mounted registry/source inputs changed '
            'while the batch was derived; no derived rows written',
            file=sys.stderr,
        )
        return 1

    effective_replacements = dict(staged)
    input_paths: set[str] = set()
    if registry_raw is not None:
        registry_path = (vault_root / _FOLDER_MOUNTS_REL).resolve()
        effective_replacements[registry_path] = registry_raw
        input_paths.add(_FOLDER_MOUNTS_REL.as_posix())
    effective_snapshot = _snapshot_with_source_replacements(
        source_snapshot_after,
        vault_root,
        effective_replacements,
        input_paths=input_paths,
    )
    effective_snapshot = _snapshot_with_mounted_catalog(
        effective_snapshot,
        catalog,
    )
    route_union = route_plan.current_after + route_plan.archive_after
    current_manifest = _finalize_derivation_manifest(
        effective_snapshot,
        route_union,
        repo_clock=str(gardener_stats.get('repo_clock') or ''),
        wall_clock_date=str(gardener_stats.get('wall_clock_as_of') or ''),
    )
    allowed_virtual_paths = catalog.virtual_paths_for_mounts(affected_mounts)
    # A BATCH THAT DERIVES NOTHING FROM MOUNTED CONTENT IS NOT INVALIDATED BY
    # MOUNTED CONTENT MOVING.
    #
    # `@mounted-source/...` and `@mounted-sidecar/...` are observations of
    # folders on other volumes; on a laptop with iCloud and OneDrive mounts they
    # change — and disappear, when a mount goes offline — constantly, for
    # reasons no batch caused. When no record in this batch carries a
    # `mount_uid`, none of its derived rows read those observations, so treating
    # their movement as tampering refuses correct work: mounting a NEW folder
    # died on an UNRELATED mount being offline (7b1e0ae5). Rows that do read
    # them stay fully guarded, because any batch touching mounted content has a
    # non-empty `affected_mounts` and takes the per-mount authorization above.
    allowed_virtual_prefixes = (
        ('@mounted-source/', '@mounted-sidecar/') if not affected_mounts else ()
    )
    if registry_raw is not None and registry_raw == _registry_bytes_on_disk(vault_root):
        # A COMPANION THAT DECLARES CURRENT STATE IS NOT A CHANGE.
        #
        # `@mounted-registry/<uid>` entries are a pure function of the
        # folder-mount registry bytes. A caller that passes the bytes ALREADY ON
        # DISK is stating what it derived against, so those entries belong to
        # this transaction; a caller passing DIFFERENT bytes is mutating the
        # registry and must still be held to per-mount authorization, which is
        # what stops a batch for one mount smuggling a rename of another.
        #
        # Without this, the SECOND `mount` in a studio refused (7b1e0ae5):
        # `affected_mounts` is derived from records carrying `mount_uid`, and a
        # governed mount PROJECT deliberately does not carry one — it is the
        # thing mounted content points at, not mounted content. So mount 1's
        # registry row, written after the transaction that created the index
        # surfaces, read as an unrelated semantic input changing under the
        # writer, and mount 2 died with "no index surface was reported current".
        allowed_virtual_paths.update(
            f'@mounted-registry/{mount_uid}'
            for mount_uid in mounted_catalog_after.mounts
        )
    try:
        blockers = _incremental_manifest_blockers(
            vault_root,
            current_manifest,
            owned_paths | input_paths,
            allowed_virtual_paths=allowed_virtual_paths,
            allowed_virtual_prefixes=allowed_virtual_prefixes,
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(
            f'[rebuild --batch] {exc}; run a full --apply; no derived rows written',
            file=sys.stderr,
        )
        return 1
    if blockers:
        print(
            '[rebuild --batch] REFUSAL: semantic derivation inputs changed '
            'outside the owned projections: '
            + ', '.join(blockers)
            + '; no derived rows written',
            file=sys.stderr,
        )
        return 1
    try:
        provenance = index_surfaces.prove_surface_derivation(
            route_plan.current_after,
            route_plan.archive_after,
            manifest=current_manifest,
            source_paths={
                str(record.get('path'))
                for record in route_union
                if record.get('path')
                and not str(record.get('path')).startswith('mounted/')
            },
            uncommitted_inputs=effective_snapshot['uncommitted_inputs'],
        )

        def mutate_sqlite(conn: sqlite3.Connection) -> bool:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS index_observations (
                    src_uid        TEXT NOT NULL,
                    kind           TEXT NOT NULL,
                    raw_target     TEXT NOT NULL,
                    mount_uid      TEXT NOT NULL,
                    candidate_uids TEXT NOT NULL,
                    PRIMARY KEY (src_uid, kind, raw_target)
                )
            """)
            for (
                uid,
                entry_row,
                edge_rows,
                fts_row,
                observation_rows,
            ) in row_sets:
                conn.execute(
                    'INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    entry_row,
                )
                conn.execute('DELETE FROM edges WHERE src_uid = ?', (uid,))
                if edge_rows:
                    conn.executemany('INSERT INTO edges VALUES (?,?,?)', edge_rows)
                conn.execute('DELETE FROM entries_fts WHERE uid = ?', (uid,))
                conn.execute('INSERT INTO entries_fts VALUES (?,?,?)', fts_row)
                conn.execute(
                    'DELETE FROM index_observations WHERE src_uid = ?',
                    (uid,),
                )
                if observation_rows:
                    conn.executemany(
                        'INSERT INTO index_observations VALUES (?,?,?,?,?)',
                        observation_rows,
                    )
            requested = set(uids)
            for record in changed_records:
                uid = str(record.get('uid') or '')
                if uid in requested:
                    continue
                conn.execute(
                    'UPDATE entries SET fm_json = ? WHERE uid = ?',
                    (json.dumps(record, separators=(',', ':')), uid),
                )
            return True

        sqlite_raw, _changed = _prepare_sqlite_image(sqlite_path, mutate_sqlite)
        maintenance_replacements = _incremental_maintenance_replacements(
            vault_root
        )
        destinations = index_surfaces.write_records_route(
            route_plan,
            companion_replacements=(
                (sqlite_path, sqlite_raw),
                *maintenance_replacements,
                *companion_replacements,
            ),
            source_replacements=staged.items(),
            derivation_provenance=provenance,
            incremental_owned_route_uids=route_changed_uids,
        )
    except (
        index_surfaces.IndexSurfaceRefusal,
        OSError,
        RuntimeError,
        sqlite3.Error,
    ) as exc:
        print(
            f'[rebuild --batch] REFUSAL: {exc}; no derived rows written',
            file=sys.stderr,
        )
        return 1

    try:
        _invalidate_archive_cache(vault_root)
    except OSError as exc:
        print(
            f'[rebuild --batch] WARN: stale cache bytes were invalidated '
            f'transactionally but cleanup failed ({exc}); verified cache reuse '
            'will refuse',
            file=sys.stderr,
        )
    for uid, surface, action in destinations:
        print(f'[rebuild --batch] {uid}: {surface} {action}')
    print(
        f'[rebuild --batch] freshened {len(uids)} entries in one transaction'
    )
    return 0


def freshen_one(uid: str, vault_root: Path) -> int:
    """Serialize one complete incremental upsert across every derived surface."""
    try:
        with index_surfaces.index_write_lock(vault_root):
            try:
                _expanded, affected_mounts = _mounted_batch_dependency_uids(
                    (uid,),
                    vault_root,
                    {},
                )
            except index_surfaces.IndexSurfaceRefusal:
                affected_mounts = set()
            if affected_mounts:
                return _freshen_many_locked((uid,), vault_root)
            return _freshen_one_locked(uid, vault_root)
    except index_surfaces.IndexLockTimeout as exc:
        print(f'[rebuild --only] {uid}: {exc}', file=sys.stderr)
        return 1


def _process_governed_path_for_uid(fp: Path, uid: str, vault_root: Path) -> Optional[dict[str, Any]]:
    """Dispatch one incremental source through its full-rebuild parser family.

    Existing SQLite path provenance resolves renamed One-Home Markdown such as
    ``agents/<slug>/roadmap.md`` and ``vault/capsules/*.capsule.md``.  Those files
    cannot derive their UID from ``Path.stem``; the full rebuild passes their
    frontmatter UID as ``uid_override``.  Incremental freshen must do the same.
    Tool-family Python/JSON/docstring layouts continue through process_tool_file.
    """
    tool_family_dirs = {
        vault_root / 'vault' / 'tools',
        vault_root / 'vault' / 'actions',
        vault_root / 'vault' / 'session-agents',
    }
    if fp.parent in tool_family_dirs or fp.suffix.lower() in ('.py', '.json'):
        record = process_tool_file(fp)
        return record if record and record.get('uid') == uid else None
    return process_file(fp, uid_override=uid)


def _freshen_one_locked(uid: str, vault_root: Path) -> int:
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
        # New One-Home entries do not have a live SQLite row yet, so path
        # provenance cannot resolve them. Probe the registered canonical homes
        # before the legacy vault/files fallback (S2 tool-class birth replay).
        # Locked friendly-path tools derive identity from embedded frontmatter,
        # so an exact UID filename is not sufficient for first registration.
        candidates = [
            files_dir / f'{uid}.md',
            vault_root / 'vault' / 'tools' / f'{uid}.py',
            vault_root / 'vault' / 'tools' / f'{uid}.md',
            vault_root / 'vault' / 'tools' / f'{uid}.json',
            vault_root / 'vault' / 'actions' / f'{uid}.md',
            vault_root / 'vault' / 'actions' / f'{uid}.json',
            vault_root / 'vault' / 'agents' / f'{uid}.md',
            vault_root / 'vault' / 'playbooks' / f'{uid}.md',
            vault_root / 'vault' / 'skills' / f'{uid}.md',
            vault_root / 'vault' / 'session-agents' / f'{uid}.md',
        ]
        fp = next((candidate for candidate in candidates if candidate.exists()), None)
        if fp is None:
            friendly_matches = []
            tools_dir = vault_root / 'vault' / 'tools'
            if tools_dir.is_dir():
                for candidate in sorted(tools_dir.iterdir()):
                    if candidate.suffix.lower() not in ('.py', '.md', '.json'):
                        continue
                    try:
                        record = process_tool_file(candidate)
                    except Exception:
                        continue
                    if record and record.get('uid') == uid:
                        friendly_matches.append(candidate)
            if len(friendly_matches) > 1:
                rendered = ', '.join(
                    str(path.relative_to(vault_root))
                    for path in friendly_matches
                )
                print(
                    f'[rebuild --only] {uid}: multiple friendly-path tool '
                    f'sources resolve this UID: {rendered}',
                    file=sys.stderr,
                )
                return 1
            fp = friendly_matches[0] if friendly_matches else candidates[0]
    if not fp.exists():
        print(f'[rebuild --only] no governed file at {fp} — nothing to freshen '
              f'(a full rebuild reconciles deletions)', file=sys.stderr)
        return 1
    try:
        provenance_schema = index_surfaces.trusted_index_provenance_schema(
            vault_root
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(
            f'[rebuild --only] {uid}: {exc}; no derived rows written',
            file=sys.stderr,
        )
        return 1
    if provenance_schema == 2:
        # Five-step compatibility path: verify the legacy pair above, retain
        # this lock, bypass every derivation cache, collect/prove every source,
        # then atomically replace all participants with schema3 provenance.
        print(
            f'[rebuild --only] {uid}: schema2 pair has no trusted global '
            'source manifest; escalating atomically to a full source-complete '
            'bootstrap.'
        )
        rc = rebuild_index(
            vault_root,
            True,
            _index_lock_held=True,
            _force_source_complete=True,
        )
        if rc != 0:
            print(
                f'[rebuild --only] {uid}: REFUSAL: schema2 full bootstrap '
                'could not prove and rederive every source; no incremental '
                'certification was issued.',
                file=sys.stderr,
            )
            return rc
        print(
            f'[rebuild --only] {uid}: schema2 full bootstrap completed; all '
            'rows now match the trusted schema3 manifest.'
        )
        return 0
    owned_relative = fp.relative_to(vault_root).as_posix()
    # Inherit the trusted manifest instead of re-proving the whole vault. See
    # _inherited_derivation_snapshot for the measurement, the ruling, and what
    # is deliberately given up. (metis-g103 2026-08-06: 26.1s -> 3.25s, and it
    # stops refusing writes because another agent touched an unrelated file.)
    source_snapshot_before, source_scope_reason = _inherited_derivation_snapshot(
        vault_root,
        {owned_relative},
    )
    if source_snapshot_before is None:
        # BOOTSTRAP, not steady state. There is nothing to inherit -- a fresh
        # clone, a studio whose seal was never minted, or damaged evidence. The
        # expensive whole-vault capture is exactly right here and costs its 26
        # seconds ONCE, because the write it certifies is what mints the
        # manifest every later write inherits.
        #
        # Found by test_two_deleted_floor_files_recover_from_sqlite_without_lowering,
        # which recovers a studio with no prior manifest. Without this fallback
        # my change made --only impossible on any studio that had never done a
        # full --apply. (metis-g103 2026-08-06)
        source_snapshot_before, source_scope_reason = (
            _verify_incremental_source_scope(
                vault_root,
                {owned_relative},
                defer_semantic_scope_to_trusted_manifest=True,
            )
        )
        _inherited_snapshot_used = False
    else:
        _inherited_snapshot_used = True
    if source_snapshot_before is None:
        print(
            f'[rebuild --only] {uid}: REFUSAL: source inventory incomplete; '
            f'{source_scope_reason}. Run a full --apply so every named '
            'derivation input and row advances together; '
            'no derived rows written.',
            file=sys.stderr,
        )
        return 1
    rec = _process_governed_path_for_uid(fp, uid, vault_root)
    if rec:
        rec['path'] = str(fp.relative_to(vault_root))  # v1.69 path-provenance
    if not rec or not rec.get('uid'):
        print(f'[rebuild --only] {uid}: could not parse a record from {fp.name}', file=sys.stderr)
        return 1
    try:
        rec, gardener_stats = _apply_gardener_to_fresh_record(
            rec,
            vault_root,
        )
    except Exception as exc:
        print(
            f'[rebuild --only] {uid}: Gardener coherence transform failed — {exc}; '
            f'no index rows written (run a full rebuild for the named cure)',
            file=sys.stderr,
        )
        return 1
    sqlite_path = vault_root / 'vault' / '00-index.sqlite'
    if not sqlite_path.exists():
        print(f'[rebuild --only] {sqlite_path} absent — run a full rebuild first', file=sys.stderr)
        return 1
    catalog_records = index_surfaces.load_index_records(
        vault_root,
        include_archive=True,
        require_complete_union=True,
    )
    catalog_records = [
        rec if str(record.get('uid')) == uid else record
        for record in catalog_records
    ]
    if not any(str(record.get('uid')) == uid for record in catalog_records):
        catalog_records.append(rec)
    catalog = _MountedSourceCatalog(vault_root, catalog_records)
    mounted_signature_before = catalog.signature()
    all_uids = {
        str(record.get('uid'))
        for record in catalog_records
        if record.get('uid')
    }
    declared_pairs = {
        (str(record.get('uid')), target)
        for record in catalog_records
        if record.get('uid')
        for _relation, target in iter_record_edges(record)
    }
    entry_row, edge_rows, fts_row, observation_rows = _record_to_derived_rows(
        rec,
        files_dir,
        catalog=catalog,
        declared_pairs=declared_pairs,
        all_uids=all_uids,
    )
    # Preflight BOTH JSONL surfaces before the first derived write.  In
    # particular, a damaged archive must refuse before SQLite/current can be
    # advanced to a state the archive side of the union did not accept.
    try:
        route_plan = index_surfaces.plan_record_route(vault_root, rec)
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(f'[rebuild --only] {uid}: {exc}; no derived rows written',
              file=sys.stderr)
        return 1
    # Same inherited shape as the "before" snapshot, and the SAME owned set --
    # both re-hash the target, so a target that changed mid-write still fails
    # the equality check below. Passing a different owned set here would make
    # the two snapshots differ by construction and refuse every write.
    if _inherited_snapshot_used:
        source_snapshot_after, snapshot_reason = _inherited_derivation_snapshot(
            vault_root,
            {owned_relative},
        )
    else:
        # Bootstrap path: the "before" snapshot was a full capture, so the
        # "after" must be one too or the equality check compares two different
        # shapes and refuses every bootstrap write.
        source_snapshot_after, snapshot_reason = (
            _capture_exact_derivation_snapshot(vault_root)
        )
    if source_snapshot_after is None:
        print(
            f'[rebuild --only] {uid}: REFUSAL: {snapshot_reason}; '
            'no derived rows written',
            file=sys.stderr,
        )
        return 1
    if source_snapshot_before != source_snapshot_after:
        print(
            f'[rebuild --only] {uid}: REFUSAL: exact derivation inputs '
            'changed while the target was parsed; no derived rows written',
            file=sys.stderr,
        )
        return 1
    mounted_catalog_after = _MountedSourceCatalog(vault_root, catalog_records)
    if mounted_signature_before != mounted_catalog_after.signature():
        print(
            f'[rebuild --only] {uid}: REFUSAL: mounted registry/source inputs '
            'changed while the target was derived; no derived rows written',
            file=sys.stderr,
        )
        return 1
    effective_snapshot = _snapshot_with_mounted_catalog(
        source_snapshot_after,
        catalog,
    )
    route_union = route_plan.current_after + route_plan.archive_after
    local_source_paths = {
        str(record.get('path'))
        for record in route_union
        if record.get('path')
        and not str(record.get('path')).startswith('mounted/')
    }
    current_manifest = _finalize_derivation_manifest(
        effective_snapshot,
        route_union,
        repo_clock=str(gardener_stats.get('repo_clock') or ''),
        wall_clock_date=str(
            gardener_stats.get('wall_clock_as_of') or ''
        ),
    )
    try:
        manifest_blockers = _incremental_manifest_blockers(
            vault_root,
            current_manifest,
            {owned_relative},
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        legacy_scope, legacy_reason = _capture_source_inventory_proof(
            vault_root,
            allowed_dirty_paths={owned_relative},
        )
        if legacy_scope is None:
            print(
                f'[rebuild --only] {uid}: {exc}; {legacy_reason}. Run a '
                'full --apply before --only. No derived rows written.',
                file=sys.stderr,
            )
            return 1
        # One-way compatibility for schema2/bootstrap or damaged-evidence
        # diagnosis. The pair writer still performs its ratchet/evidence gate;
        # successful writes immediately mint the schema3 trusted manifest.
        manifest_blockers = []
    if manifest_blockers:
        print(
            f'[rebuild --only] {uid}: REFUSAL: semantic derivation inputs '
            'changed outside the owned target: '
            + ', '.join(manifest_blockers)
            + '. Run a full --apply; no derived rows written.',
            file=sys.stderr,
        )
        return 1
    try:
        derivation_provenance = index_surfaces.prove_surface_derivation(
            route_plan.current_after,
            route_plan.archive_after,
            manifest=current_manifest,
            source_paths=local_source_paths,
            uncommitted_inputs=source_snapshot_after[
                'uncommitted_inputs'
            ],
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(
            f'[rebuild --only] {uid}: {exc}; no derived rows written',
            file=sys.stderr,
        )
        return 1
    try:
        def mutate_sqlite(conn: sqlite3.Connection) -> bool:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS index_observations (
                    src_uid        TEXT NOT NULL,
                    kind           TEXT NOT NULL,
                    raw_target     TEXT NOT NULL,
                    mount_uid      TEXT NOT NULL,
                    candidate_uids TEXT NOT NULL,
                    PRIMARY KEY (src_uid, kind, raw_target)
                )
            """)
            conn.execute(
                'INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                entry_row,
            )
            conn.execute('DELETE FROM edges WHERE src_uid = ?', (uid,))
            if edge_rows:
                conn.executemany('INSERT INTO edges VALUES (?,?,?)', edge_rows)
            conn.execute('DELETE FROM entries_fts WHERE uid = ?', (uid,))
            conn.execute('INSERT INTO entries_fts VALUES (?,?,?)', fts_row)
            conn.execute(
                'DELETE FROM index_observations WHERE src_uid = ?',
                (uid,),
            )
            if observation_rows:
                conn.executemany(
                    'INSERT INTO index_observations VALUES (?,?,?,?,?)',
                    observation_rows,
                )
            return True

        sqlite_raw, _changed = _prepare_sqlite_image(
            sqlite_path,
            mutate_sqlite,
        )
        surface, action = index_surfaces.write_record_route(
            route_plan,
            companion_replacements=((sqlite_path, sqlite_raw),),
            derivation_provenance=derivation_provenance,
        )
    except (index_surfaces.IndexSurfaceRefusal, OSError, RuntimeError, sqlite3.Error) as exc:
        print(f'[rebuild --only] {uid}: REFUSAL: {exc}; no derived rows written',
              file=sys.stderr)
        return 1
    # ADR-047 Layer 1: the pair route above uses the SAME archive predicate as
    # the full rebuild. Moving active→archived (or back) removes the UID from
    # the old surface in one journaled gesture with the SQLite union image.
    try:
        _invalidate_archive_cache(vault_root)
    except OSError as exc:
        print(
            f'[rebuild --only] {uid}: WARN: committed rows but could not '
            f'invalidate archive cache ({exc}); verified cache identity/hash '
            'will refuse stale reuse',
            file=sys.stderr,
        )
    print(f'[rebuild --only] {uid}: {surface} {action}')
    print(f'[rebuild --only] freshened {uid}: 1 entry row, {len(edge_rows)} edge(s), 1 FTS row '
          f'(meta_status view re-buckets on query)')
    try:
        _bump_dirty_counter(vault_root)
    except OSError as exc:
        print(f'[rebuild --only] {uid}: WARN: dirty counter update failed: {exc}',
              file=sys.stderr)
    try:
        _write_index_run_artifact(vault_root, {
            'schema_version': 2,
            'run_started_at': _now_iso(),
            'mode': 'incremental-only',
            'assembled_record_count': len(route_union),
            'current_record_count': len(route_plan.current_after),
            'archive_record_count': len(route_plan.archive_after),
            'derived_from_uncommitted': bool(
                derivation_provenance.uncommitted_inputs
            ),
            'uncommitted_inputs': _uncommitted_input_receipt(
                source_snapshot_after
            ),
            'source_inventory_sha256': (
                derivation_provenance.manifest_sha256
            ),
            'authoritative_for': {
                'federation': not bool(
                    derivation_provenance.uncommitted_inputs
                ),
                'local': True,
                'ratchet_baseline': not bool(
                    derivation_provenance.uncommitted_inputs
                ),
                'release': not bool(
                    derivation_provenance.uncommitted_inputs
                ),
            },
        })
    except OSError as exc:
        print(
            f'[rebuild --only] {uid}: WARN: run artifact update failed: {exc}',
            file=sys.stderr,
        )
    return 0


def remove_many(
    uids: Iterable[str],
    vault_root: Path,
    *,
    companion_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
) -> int:
    """Serialize one multi-UID removal across JSONL, SQLite, seals, and caches."""
    normalized = tuple(sorted(set(uids)))
    if not normalized:
        print('[rebuild --remove-batch] no UIDs supplied', file=sys.stderr)
        return 2
    try:
        with index_surfaces.index_write_lock(vault_root):
            return _remove_many_locked(
                normalized,
                vault_root,
                companion_replacements=companion_replacements,
            )
    except index_surfaces.IndexLockTimeout as exc:
        print(f'[rebuild --remove-batch] {exc}', file=sys.stderr)
        return 1


def _remove_many_locked(
    uids: tuple[str, ...],
    vault_root: Path,
    *,
    companion_replacements: Optional[Iterable[tuple[Path, bytes]]] = None,
) -> int:
    invalid = [uid for uid in uids if not UID_RE.match(uid)]
    if invalid:
        print(
            f'[rebuild --remove-batch] invalid UID(s): {", ".join(invalid)}',
            file=sys.stderr,
        )
        return 2
    try:
        plan = index_surfaces.plan_uids_removal(vault_root, uids)
    except (ValueError, index_surfaces.IndexSurfaceRefusal) as exc:
        print(
            f'[rebuild --remove-batch] {exc}; no derived rows written',
            file=sys.stderr,
        )
        return 1
    uid_set = set(uids)
    pre_removal_union = plan.current_before + plan.archive_before
    affected_mounts = {
        str(record.get('mount_uid'))
        for record in pre_removal_union
        if str(record.get('uid') or '') in uid_set
        and record.get('mount_uid')
    }
    owned_paths = {
        str(record.get('path'))
        for record in plan.current_before + plan.archive_before
        if record.get('uid') in uid_set and record.get('path')
    }
    source_snapshot_before, reason = _verify_incremental_source_scope(
        vault_root,
        owned_paths,
    )
    if source_snapshot_before is None:
        print(
            f'[rebuild --remove-batch] REFUSAL: {reason}; no derived rows written',
            file=sys.stderr,
        )
        return 1
    source_snapshot_after, reason = _capture_exact_derivation_snapshot(
        vault_root,
        allowed_deleted_paths=owned_paths,
    )
    if source_snapshot_after is None or source_snapshot_after != source_snapshot_before:
        detail = reason if source_snapshot_after is None else (
            'exact derivation inputs changed during removal preflight'
        )
        print(
            f'[rebuild --remove-batch] REFUSAL: {detail}; no derived rows written',
            file=sys.stderr,
        )
        return 1
    union = plan.current_after + plan.archive_after
    dependent_records = [
        record
        for record in union
        if str(record.get('mount_uid') or '') in affected_mounts
    ]
    registry_raw = next(
        (
            raw
            for path, raw in tuple(companion_replacements or ())
            if Path(path).resolve()
            == (vault_root / _FOLDER_MOUNTS_REL).resolve()
        ),
        None,
    )
    mounted_catalog_before = _MountedSourceCatalog(
        vault_root,
        union,
        registry_raw=registry_raw,
    )
    mounted_signature_before = mounted_catalog_before.signature()
    all_uids = {
        str(record.get('uid'))
        for record in union
        if record.get('uid')
    }
    declared_pairs = {
        (str(record.get('uid')), target)
        for record in union
        if record.get('uid')
        for _relation, target in iter_record_edges(record)
    }
    files_dir = vault_root / 'vault' / 'files'
    dependent_row_sets: list[
        tuple[str, tuple, list[tuple], tuple, list[tuple]]
    ] = []
    for record in dependent_records:
        dependent_uid = str(record.get('uid') or '')
        entry_row, edge_rows, fts_row, observations = _record_to_derived_rows(
            record,
            files_dir,
            catalog=mounted_catalog_before,
            declared_pairs=declared_pairs,
            all_uids=all_uids,
        )
        dependent_row_sets.append(
            (dependent_uid, entry_row, edge_rows, fts_row, observations)
        )
    effective_snapshot = source_snapshot_after
    if registry_raw is not None:
        effective_snapshot = _snapshot_with_source_replacements(
            effective_snapshot,
            vault_root,
            {(vault_root / _FOLDER_MOUNTS_REL).resolve(): registry_raw},
            input_paths={_FOLDER_MOUNTS_REL.as_posix()},
        )
    effective_snapshot = _snapshot_with_mounted_catalog(
        effective_snapshot,
        mounted_catalog_before,
    )
    current_manifest = _finalize_derivation_manifest(
        effective_snapshot,
        union,
        **_derivation_clock_entries(vault_root),
    )
    manifest_owned_paths = set(owned_paths)
    if registry_raw is not None:
        manifest_owned_paths.add(_FOLDER_MOUNTS_REL.as_posix())
    allowed_removal_virtual_paths = (
        mounted_catalog_before.virtual_paths_for_mounts(affected_mounts)
    )
    allowed_removal_virtual_paths.update(
        f'@mounted-{kind}/{record.get("mount_uid")}/{record.get("uid")}'
        for record in pre_removal_union
        if str(record.get('uid') or '') in uid_set
        and str(record.get('mount_uid') or '') in affected_mounts
        for kind in ('source', 'sidecar')
    )
    allowed_removal_virtual_paths.update(
        f'@mounted-registry/{mount_uid}'
        for mount_uid in affected_mounts
    )
    try:
        blockers = _incremental_manifest_blockers(
            vault_root,
            current_manifest,
            manifest_owned_paths,
            allowed_virtual_paths=allowed_removal_virtual_paths,
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(
            f'[rebuild --remove-batch] {exc}; run a full --apply; '
            'no derived rows written',
            file=sys.stderr,
        )
        return 1
    if blockers:
        print(
            '[rebuild --remove-batch] REFUSAL: semantic derivation inputs '
            'changed outside the removed projections and affected mounts: '
            + ', '.join(blockers)
            + '; run a full --apply; no derived rows written',
            file=sys.stderr,
        )
        return 1
    try:
        provenance = index_surfaces.prove_surface_derivation(
            plan.current_after,
            plan.archive_after,
            manifest=current_manifest,
            source_paths={
                str(record.get('path'))
                for record in union
                if record.get('path')
                and not str(record.get('path')).startswith('mounted/')
            },
            uncommitted_inputs=effective_snapshot['uncommitted_inputs'],
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(
            f'[rebuild --remove-batch] {exc}; no derived rows written',
            file=sys.stderr,
        )
        return 1

    sqlite_path = vault_root / 'vault' / '00-index.sqlite'
    companions: tuple[tuple[Path, bytes], ...] = ()
    sqlite_changed = False
    if sqlite_path.is_file():
        try:
            def mutate_sqlite(conn: sqlite3.Connection) -> bool:
                placeholders = ','.join('?' for _ in uids)
                entry_present = conn.execute(
                    f'SELECT 1 FROM entries WHERE uid IN ({placeholders}) LIMIT 1',
                    uids,
                ).fetchone() is not None
                edge_present = conn.execute(
                    f'SELECT 1 FROM edges WHERE src_uid IN ({placeholders}) '
                    f'OR dst_uid IN ({placeholders}) LIMIT 1',
                    (*uids, *uids),
                ).fetchone() is not None
                fts_present = conn.execute(
                    f'SELECT 1 FROM entries_fts WHERE uid IN ({placeholders}) LIMIT 1',
                    uids,
                ).fetchone() is not None
                conn.execute(
                    f'DELETE FROM entries WHERE uid IN ({placeholders})',
                    uids,
                )
                conn.execute(
                    f'DELETE FROM edges WHERE src_uid IN ({placeholders}) '
                    f'OR dst_uid IN ({placeholders})',
                    (*uids, *uids),
                )
                conn.execute(
                    f'DELETE FROM entries_fts WHERE uid IN ({placeholders})',
                    uids,
                )
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS index_observations (
                        src_uid TEXT NOT NULL, kind TEXT NOT NULL,
                        raw_target TEXT NOT NULL, mount_uid TEXT NOT NULL,
                        candidate_uids TEXT NOT NULL,
                        PRIMARY KEY (src_uid, kind, raw_target)
                    )
                """)
                conn.execute(
                    f'DELETE FROM index_observations '
                    f'WHERE src_uid IN ({placeholders})',
                    uids,
                )
                for (
                    dependent_uid,
                    entry_row,
                    edge_rows,
                    fts_row,
                    observation_rows,
                ) in dependent_row_sets:
                    conn.execute(
                        'INSERT OR REPLACE INTO entries '
                        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        entry_row,
                    )
                    conn.execute(
                        'DELETE FROM edges WHERE src_uid = ?',
                        (dependent_uid,),
                    )
                    if edge_rows:
                        conn.executemany(
                            'INSERT INTO edges VALUES (?,?,?)',
                            edge_rows,
                        )
                    conn.execute(
                        'DELETE FROM entries_fts WHERE uid = ?',
                        (dependent_uid,),
                    )
                    conn.execute(
                        'INSERT INTO entries_fts VALUES (?,?,?)',
                        fts_row,
                    )
                    conn.execute(
                        'DELETE FROM index_observations WHERE src_uid = ?',
                        (dependent_uid,),
                    )
                    if observation_rows:
                        conn.executemany(
                            'INSERT INTO index_observations VALUES (?,?,?,?,?)',
                            observation_rows,
                        )
                return (
                    entry_present
                    or edge_present
                    or fts_present
                    or bool(dependent_row_sets)
                )

            sqlite_raw, sqlite_changed = _prepare_sqlite_image(
                sqlite_path,
                mutate_sqlite,
            )
            companions = ((sqlite_path, sqlite_raw),)
        except (OSError, RuntimeError, sqlite3.Error) as exc:
            print(
                f'[rebuild --remove-batch] could not prepare SQLite image: {exc}',
                file=sys.stderr,
            )
            return 1
    mounted_catalog_after = _MountedSourceCatalog(
        vault_root,
        union,
        registry_raw=registry_raw,
    )
    if mounted_signature_before != mounted_catalog_after.signature():
        print(
            '[rebuild --remove-batch] REFUSAL: mounted registry/source inputs '
            'changed during removal; no derived rows written',
            file=sys.stderr,
        )
        return 1
    if not any(surfaces for _uid, surfaces in plan.removed_from) and not sqlite_changed:
        return 0
    try:
        maintenance_replacements = _incremental_maintenance_replacements(
            vault_root
        )
        index_surfaces.write_uids_removal(
            plan,
            companion_replacements=(
                *companions,
                *maintenance_replacements,
                *(tuple(companion_replacements or ())),
            ),
            derivation_provenance=provenance,
        )
    except (index_surfaces.IndexSurfaceRefusal, OSError) as exc:
        print(
            f'[rebuild --remove-batch] REFUSAL: {exc}; no derived rows written',
            file=sys.stderr,
        )
        return 1
    try:
        _invalidate_archive_cache(vault_root)
    except OSError as exc:
        print(
            f'[rebuild --remove-batch] WARN: stale cache bytes were invalidated '
            f'transactionally but cleanup failed ({exc}); verified cache reuse '
            'will refuse',
            file=sys.stderr,
        )
    print(
        f'[rebuild --remove-batch] removed {len(uids)} UIDs in one transaction'
    )
    return 0


def remove_one(uid: str, vault_root: Path) -> int:
    """Serialize one complete removal across JSONL, SQLite, and counter."""
    try:
        with index_surfaces.index_write_lock(vault_root):
            return _remove_one_locked(uid, vault_root)
    except index_surfaces.IndexLockTimeout as exc:
        print(f'[rebuild --remove] {uid}: {exc}', file=sys.stderr)
        return 1


def _remove_one_locked(uid: str, vault_root: Path) -> int:
    """rebuild --remove <uid>: the deletion-side counterpart to freshen_one
    (Governed Autonomy S2, bba40cd7 -- "recycle freshens/removes the entry's
    index rows in-gesture"). freshen_one requires the source file to still
    exist (it RE-DERIVES from frontmatter); recycle's whole point is that the
    file no longer lives at vault/files/<uid>.md, so there is nothing to
    re-derive -- the row must be REMOVED, not refreshed. Without this, a
    recycled entry lingers as a live, queryable row until the next full
    rebuild -- "soft-deleted entries never linger as live rows" is the S2
    acceptance criterion this closes.

    Idempotent: removing an already-absent uid is a no-op success, not an
    error (recycle may call this on a uid the index never had a row for).
    Returns 0 on success (including no-op); non-zero only on a genuine I/O
    failure.
    """
    if not UID_RE.match(uid):
        print(f'[rebuild --remove] {uid!r} is not an 8-hex UID', file=sys.stderr)
        return 2

    sqlite_path = vault_root / 'vault' / '00-index.sqlite'
    try:
        removal_plan = index_surfaces.plan_uid_removal(vault_root, uid)
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(
            f'[rebuild --remove] {uid}: {exc}; no derived rows written',
            file=sys.stderr,
        )
        return 1
    if any(
        record.get('mount_uid')
        for record in (
            removal_plan.current_before + removal_plan.archive_before
        )
        if str(record.get('uid') or '') == uid
    ):
        # Mounted aliases are mount-scoped dependencies. Reuse the batch path
        # even for one UID so every surviving same-mount source is re-derived
        # with the pre-removal mount identity in the same sealed transaction.
        return _remove_many_locked((uid,), vault_root)
    owned_paths = {
        str(record.get('path'))
        for record in (
            removal_plan.current_before + removal_plan.archive_before
        )
        if record.get('uid') == uid and record.get('path')
    }
    source_snapshot_before, source_scope_reason = _verify_incremental_source_scope(
        vault_root,
        owned_paths,
    )
    if source_snapshot_before is None:
        print(
            f'[rebuild --remove] {uid}: REFUSAL: source inventory incomplete; '
            f'{source_scope_reason}. Land, revert, or isolate unrelated paths '
            'first; '
            'no derived rows written.',
            file=sys.stderr,
        )
        return 1
    source_snapshot_after, snapshot_reason = _capture_exact_derivation_snapshot(
        vault_root,
        allowed_deleted_paths=owned_paths,
    )
    if source_snapshot_after is None:
        print(
            f'[rebuild --remove] {uid}: REFUSAL: {snapshot_reason}; '
            'no derived rows written',
            file=sys.stderr,
        )
        return 1
    if source_snapshot_before != source_snapshot_after:
        print(
            f'[rebuild --remove] {uid}: REFUSAL: exact derivation inputs '
            'changed during removal preflight; no derived rows written',
            file=sys.stderr,
        )
        return 1
    removal_union = removal_plan.current_after + removal_plan.archive_after
    mounted_catalog_before = _MountedSourceCatalog(vault_root, removal_union)
    mounted_signature_before = mounted_catalog_before.signature()
    effective_snapshot = _snapshot_with_mounted_catalog(
        source_snapshot_after,
        mounted_catalog_before,
    )
    current_manifest = _finalize_derivation_manifest(
        effective_snapshot,
        removal_union,
        **_derivation_clock_entries(vault_root),
    )
    try:
        blockers = _incremental_manifest_blockers(
            vault_root,
            current_manifest,
            owned_paths,
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(
            f'[rebuild --remove] {uid}: {exc}; run a full --apply; '
            'no derived rows written',
            file=sys.stderr,
        )
        return 1
    if blockers:
        print(
            f'[rebuild --remove] {uid}: REFUSAL: semantic derivation inputs '
            'changed outside the removed projection: '
            + ', '.join(blockers)
            + '; run a full --apply; no derived rows written',
            file=sys.stderr,
        )
        return 1
    try:
        derivation_provenance = index_surfaces.prove_surface_derivation(
            removal_plan.current_after,
            removal_plan.archive_after,
            manifest=current_manifest,
            source_paths={
                str(record.get('path'))
                for record in removal_union
                if record.get('path')
                and not str(record.get('path')).startswith('mounted/')
            },
            uncommitted_inputs=effective_snapshot[
                'uncommitted_inputs'
            ],
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(
            f'[rebuild --remove] {uid}: {exc}; no derived rows written',
            file=sys.stderr,
        )
        return 1

    sqlite_changed = False
    companions: tuple[tuple[Path, bytes], ...] = ()
    if sqlite_path.exists():
        try:
            def mutate_sqlite(conn: sqlite3.Connection) -> bool:
                entry_present = conn.execute(
                    'SELECT 1 FROM entries WHERE uid = ? LIMIT 1',
                    (uid,),
                ).fetchone() is not None
                edge_present = conn.execute(
                    'SELECT 1 FROM edges WHERE src_uid = ? OR dst_uid = ? LIMIT 1',
                    (uid, uid),
                ).fetchone() is not None
                fts_present = conn.execute(
                    'SELECT 1 FROM entries_fts WHERE uid = ? LIMIT 1',
                    (uid,),
                ).fetchone() is not None
                conn.execute('DELETE FROM entries WHERE uid = ?', (uid,))
                conn.execute(
                    'DELETE FROM edges WHERE src_uid = ? OR dst_uid = ?',
                    (uid, uid),
                )
                conn.execute('DELETE FROM entries_fts WHERE uid = ?', (uid,))
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS index_observations (
                        src_uid TEXT NOT NULL, kind TEXT NOT NULL,
                        raw_target TEXT NOT NULL, mount_uid TEXT NOT NULL,
                        candidate_uids TEXT NOT NULL,
                        PRIMARY KEY (src_uid, kind, raw_target)
                    )
                """)
                conn.execute(
                    'DELETE FROM index_observations WHERE src_uid = ?',
                    (uid,),
                )
                return entry_present or edge_present or fts_present

            sqlite_raw, sqlite_changed = _prepare_sqlite_image(
                sqlite_path,
                mutate_sqlite,
            )
            companions = ((sqlite_path, sqlite_raw),)
        except (OSError, RuntimeError, sqlite3.Error) as exc:
            print(
                f'[rebuild --remove] {uid}: REFUSAL: could not prepare '
                f'SQLite removal without touching live surfaces: {exc}',
                file=sys.stderr,
            )
            return 1
    else:
        print(
            f'[rebuild --remove] {sqlite_path} absent — nothing to remove there',
            file=sys.stderr,
        )

    mounted_catalog_after = _MountedSourceCatalog(vault_root, removal_union)
    if mounted_signature_before != mounted_catalog_after.signature():
        print(
            f'[rebuild --remove] {uid}: REFUSAL: mounted registry/source '
            'inputs changed during removal; no derived rows written',
            file=sys.stderr,
        )
        return 1
    if not removal_plan.removed_from and not sqlite_changed:
        print(f'[rebuild --remove] {uid}: no row in derived union (no-op)')
        return 0

    try:
        removed_surfaces = index_surfaces.write_uid_removal(
            removal_plan,
            companion_replacements=companions,
            derivation_provenance=derivation_provenance,
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(
            f'[rebuild --remove] {uid}: {exc}; current, archive, and SQLite '
            'remain byte-identical',
            file=sys.stderr,
        )
        return 1

    any_removed = sqlite_changed or bool(removed_surfaces)
    if removed_surfaces:
        for surface in removed_surfaces:
            print(f'[rebuild --remove] {uid}: removed from {surface}')
    else:
        print(f'[rebuild --remove] {uid}: no row in either JSONL surface (no-op)')

    if any_removed:
        try:
            _invalidate_archive_cache(vault_root)
        except OSError as exc:
            print(
                f'[rebuild --remove] {uid}: WARN: committed removal but could '
                f'not invalidate archive cache ({exc}); verified identity/hash '
                'will refuse stale reuse',
                file=sys.stderr,
            )
        try:
            _bump_dirty_counter(vault_root)
        except OSError as exc:
            print(f'[rebuild --remove] {uid}: WARN: dirty counter failed: {exc}',
                  file=sys.stderr)
        try:
            _write_index_run_artifact(vault_root, {
                'schema_version': 2,
                'run_started_at': _now_iso(),
                'mode': 'incremental-remove',
                'assembled_record_count': len(removal_union),
                'current_record_count': len(removal_plan.current_after),
                'archive_record_count': len(removal_plan.archive_after),
                'derived_from_uncommitted': bool(
                    derivation_provenance.uncommitted_inputs
                ),
                'uncommitted_inputs': _uncommitted_input_receipt(
                    source_snapshot_after
                ),
                'source_inventory_sha256': (
                    derivation_provenance.manifest_sha256
                ),
                'authoritative_for': {
                    'federation': not bool(
                        derivation_provenance.uncommitted_inputs
                    ),
                    'local': True,
                    'ratchet_baseline': not bool(
                        derivation_provenance.uncommitted_inputs
                    ),
                    'release': not bool(
                        derivation_provenance.uncommitted_inputs
                    ),
                },
            })
        except OSError as exc:
            print(
                f'[rebuild --remove] {uid}: WARN: run artifact update failed: '
                f'{exc}',
                file=sys.stderr,
            )

    return 0


def build_sqlite_index(
    vault_root: Path,
    records: list[dict[str, Any]],
    apply_writes: bool,
    machines: Optional[tuple[lifecycle_machine.LifecycleMachine, ...]] = None,
    *,
    defer_replace: bool = False,
    mounted_catalog: Optional[_MountedSourceCatalog] = None,
) -> Optional[bytes]:
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
      lifecycle_machines — ordered canonical machine states declared by capsules.
      lifecycle_transitions — ordered, move-ID-addressed legal transition edges.
      lifecycle_aliases — validated legacy lifecycle values mapped to canonical states.

    Atomic rebuild: build to vault/00-index.sqlite.tmp then either return its
    durable byte image to the caller's wider index transaction or os.replace().
    """
    sqlite_path = vault_root / 'vault' / '00-index.sqlite'
    tmp_path = sqlite_path.with_suffix('.sqlite.tmp')
    files_dir = vault_root / 'vault' / 'files'
    prior_mounted_fts_bodies: dict[str, str] = {}
    if sqlite_path.is_file():
        try:
            with sqlite3.connect(sqlite_path) as prior_connection:
                prior_mounted_fts_bodies = {
                    row[0]: row[1]
                    for row in prior_connection.execute(
                        'SELECT uid, body FROM entries_fts'
                    ).fetchall()
                }
        except sqlite3.Error:
            pass
    if machines is None:
        machines = lifecycle_machine.load_lifecycle_machines(vault_root)
    machine_rows, transition_rows, alias_rows = lifecycle_machine.normalized_rows(machines)

    if not apply_writes:
        print(f'  [DRY-RUN] would build {sqlite_path.name} ({len(records)} records, '
              f'{len(machine_rows)} lifecycle states, '
              f'{len(transition_rows)} lifecycle transitions, '
              f'{len(alias_rows)} lifecycle aliases)')
        return None

    if tmp_path.exists():
        tmp_path.unlink()

    conn = sqlite3.connect(str(tmp_path))
    try:
        conn.execute('PRAGMA foreign_keys=ON')
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

        # Deterministic, non-edge outcomes from body-derived resolution.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS index_observations (
                src_uid        TEXT NOT NULL,
                kind           TEXT NOT NULL,
                raw_target     TEXT NOT NULL,
                mount_uid      TEXT NOT NULL,
                candidate_uids TEXT NOT NULL,
                PRIMARY KEY (src_uid, kind, raw_target)
            )
        """)
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_index_observations_src '
            'ON index_observations(src_uid, kind)'
        )

        # ── meta_status_map bridge table (3783a7cb Piece C) ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_status_map (
                type   TEXT NOT NULL,
                value  TEXT NOT NULL,
                bucket TEXT NOT NULL,
                PRIMARY KEY (type, value)
            )
        """)

        # ── Capsule-declared lifecycle machines (b06aa0fb Cockpit Cut 1A) ──
        conn.execute("""
            CREATE TABLE lifecycle_machines (
                type        TEXT NOT NULL,
                field       TEXT NOT NULL CHECK (field = 'status'),
                optional    INTEGER NOT NULL CHECK (optional IN (0, 1)),
                state       TEXT NOT NULL,
                state_label TEXT NOT NULL,
                state_ord   INTEGER NOT NULL CHECK (state_ord >= 0),
                terminal    INTEGER NOT NULL CHECK (terminal IN (0, 1)),
                PRIMARY KEY (type, state),
                UNIQUE (type, state_ord)
            )
        """)
        conn.execute("""
            CREATE TABLE lifecycle_transitions (
                type           TEXT NOT NULL,
                move_id        TEXT NOT NULL,
                from_state     TEXT NOT NULL,
                to_state       TEXT NOT NULL,
                move_ord       INTEGER NOT NULL CHECK (move_ord >= 0),
                label          TEXT NOT NULL,
                direction      TEXT NOT NULL
                                   CHECK (direction IN ('forward', 'back')),
                confirm        INTEGER NOT NULL CHECK (confirm IN (0, 1)),
                resolution     TEXT,
                gate           TEXT,
                warning        TEXT,
                principal_only INTEGER NOT NULL CHECK (principal_only IN (0, 1)),
                legacy_default INTEGER NOT NULL CHECK (legacy_default IN (0, 1)),
                PRIMARY KEY (type, move_id),
                UNIQUE (type, move_ord),
                FOREIGN KEY (type, from_state)
                    REFERENCES lifecycle_machines(type, state),
                FOREIGN KEY (type, to_state)
                    REFERENCES lifecycle_machines(type, state)
            )
        """)
        conn.execute(
            'CREATE INDEX idx_lifecycle_transitions_from '
            'ON lifecycle_transitions(type, from_state, move_ord)'
        )
        conn.execute(
            'CREATE INDEX idx_lifecycle_transitions_to '
            'ON lifecycle_transitions(type, to_state, move_ord)'
        )
        conn.execute("""
            CREATE TABLE lifecycle_aliases (
                type            TEXT NOT NULL,
                alias           TEXT NOT NULL,
                canonical_state TEXT NOT NULL,
                PRIMARY KEY (type, alias),
                FOREIGN KEY (type, canonical_state)
                    REFERENCES lifecycle_machines(type, state)
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
        observation_rows: list[tuple] = []

        # Per-record derivation is the shared _record_to_index_rows helper (single source
        # with freshen_one / rebuild --only) — see the module-level def above.
        all_uids = {r.get('uid') for r in records if r.get('uid')}
        declared_pairs: set[tuple[str, str]] = set()
        for r in records:
            src_u = r.get('uid')
            if not src_u: continue
            for _relation, target in iter_record_edges(r):
                declared_pairs.add((src_u, target))

        catalog = mounted_catalog or _MountedSourceCatalog(vault_root, records)

        for rec in records:
            uid = rec.get('uid', '')
            if not uid:
                continue
            (
                entry_row,
                e_rows,
                fts_row,
                rec_observations,
            ) = _record_to_derived_rows(
                rec,
                files_dir,
                catalog=catalog,
                declared_pairs=declared_pairs,
                all_uids=all_uids,
            )
            entry_rows.append(entry_row)
            edge_rows.extend(e_rows)
            fts_rows.append(fts_row)
            observation_rows.extend(rec_observations)

        _assert_mounted_fts_body_transitions(
            records,
            fts_rows,
            prior_mounted_fts_bodies,
            catalog,
        )

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
            conn.execute(
                f'DELETE FROM index_observations '
                f'WHERE src_uid IN ({placeholders_g})',
                ghost_list,
            )
            print(f'  ghost-prune: removed {len(ghost_uids)} fileless entries from SQLite.')

        conn.executemany(
            'INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            entry_rows,
        )
        conn.executemany('INSERT INTO edges VALUES (?,?,?)', edge_rows)
        conn.executemany('INSERT INTO entries_fts VALUES (?,?,?)', fts_rows)
        conn.executemany(
            'INSERT INTO index_observations VALUES (?,?,?,?,?)',
            observation_rows,
        )

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

        # Strict parsing/normalization completed before the temp database was
        # opened. Plain INSERT plus PK/UNIQUE/FK constraints keeps malformed,
        # duplicate, or dangling machine metadata from ever reaching the swap.
        if machine_rows:
            conn.executemany(
                'INSERT INTO lifecycle_machines VALUES (?,?,?,?,?,?,?)',
                machine_rows,
            )
        if transition_rows:
            conn.executemany(
                'INSERT INTO lifecycle_transitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                transition_rows,
            )
        if alias_rows:
            conn.executemany(
                'INSERT INTO lifecycle_aliases VALUES (?,?,?)',
                alias_rows,
            )
        print(f'  lifecycle machines: {len(machines)} type(s), '
              f'{len(machine_rows)} state row(s), '
              f'{len(transition_rows)} transition row(s), '
              f'{len(alias_rows)} alias row(s).')

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
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        n_entries = len(entry_rows)
        n_edges   = len(edge_rows)
        verb = 'Prepared' if defer_replace else 'Wrote'
        print(f'{verb} {sqlite_path.name} ({n_entries} entries, {n_edges} edges, {len(fts_rows)} FTS rows).')

    except Exception as exc:
        conn.close()
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise exc

    conn.close()
    if defer_replace:
        try:
            raw = tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)
        return raw
    os.replace(tmp_path, sqlite_path)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _archive_cache_paths(vault_root: Path) -> tuple[Path, Path]:
    return (
        vault_root / ARCHIVE_CACHE_JSONL_REL,
        vault_root / ARCHIVE_CACHE_META_REL,
    )


def _load_reusable_archive_cache(
    vault_root: Path,
    archive_surface_path: Path,
    *,
    reconcile: bool,
) -> tuple[list[dict], set[str], str]:
    """Return verified cached rows + local source paths safe to skip."""
    if reconcile:
        return [], set(), 'reconcile-bypass'

    cache_jsonl, cache_meta = _archive_cache_paths(vault_root)
    cache_present = cache_jsonl.exists() or cache_meta.exists()
    current_surface_path = archive_surface_path.with_name(
        index_surfaces.CURRENT_INDEX_NAME
    )
    surface_metadata_mismatch = False
    for surface_path in (current_surface_path, archive_surface_path):
        if not surface_path.is_file():
            continue
        try:
            index_surfaces.read_jsonl_strict(surface_path)
        except index_surfaces.IndexSurfaceRefusal as exc:
            # A source-complete full rebuild is the named cure for stale pair
            # metadata on either surface. Preserve strict JSONL/newline/object
            # validation, reject cache reuse, and let the later proof authorize
            # one transaction that refreshes all participants together.
            try:
                index_surfaces.read_jsonl_strict(
                    surface_path,
                    verify_surface_metadata=False,
                )
            except index_surfaces.IndexSurfaceRefusal:
                raise shard_index.VerifiedCacheRefusal(str(exc)) from exc
            surface_metadata_mismatch = True
    if surface_metadata_mismatch:
        return [], set(), 'rejected-surface-metadata-mismatch'
    if not archive_surface_path.is_file() and cache_present:
        raise shard_index.VerifiedCacheRefusal(
            'REFUSAL: archive cache exists while its required archive surface '
            'is missing'
        )
    cached = shard_index.read_verified_jsonl_cache(
        cache_jsonl,
        cache_meta,
        cache_kind=ARCHIVE_CACHE_KIND,
    )
    if cached is None:
        return [], set(), 'miss'

    records, meta = cached
    if any(not index_surfaces.is_archive_record(record) for record in records):
        raise shard_index.VerifiedCacheRefusal(
            'REFUSAL: archive cache contains a record outside the ADR-047 '
            'archive predicate'
        )

    identity, identity_reason = _archive_derivation_identity(vault_root)
    if identity is None:
        return [], set(), f'rejected-identity-unproven: {identity_reason}'
    if (
        meta.get('derivation_identity') != identity
        or meta.get('derivation_fingerprints')
        != identity['derivation_fingerprints']
    ):
        return [], set(), 'rejected-derivation-input-changed'

    recorded_paths = meta.get('source_paths')
    if not isinstance(recorded_paths, list) or not all(
        isinstance(path, str) for path in recorded_paths
    ):
        raise shard_index.VerifiedCacheRefusal(
            'REFUSAL: archive cache metadata has invalid source_paths'
        )
    local_record_paths: set[str] = set()
    for record in records:
        path = record.get('path')
        if isinstance(path, str) and path.startswith('mounted/'):
            raise shard_index.VerifiedCacheRefusal(
                'REFUSAL: local archive cache contains a mounted-vault row'
            )
        if not isinstance(path, str) or not path:
            raise shard_index.VerifiedCacheRefusal(
                f'REFUSAL: cached local archive row {record.get("uid")!r} '
                'has no canonical source path'
            )
        local_record_paths.add(path)
    if set(recorded_paths) != local_record_paths:
        raise shard_index.VerifiedCacheRefusal(
            'REFUSAL: archive cache source-path metadata does not match its rows'
        )

    return records, local_record_paths, 'reused'


def _write_archive_cache(
    vault_root: Path,
    archive_surface_path: Path,
    archive_records: list[dict],
    *,
    reconcile: bool,
) -> str:
    """Create a complete-identity cache of local archive rows only."""
    local_archive_records = [
        record
        for record in archive_records
        if not str(record.get('path') or '').startswith('mounted/')
    ]
    source_paths = sorted({
        str(record['path'])
        for record in local_archive_records
        if isinstance(record.get('path'), str)
    })
    identity, identity_reason = _archive_derivation_identity(vault_root)
    if identity is None:
        _invalidate_archive_cache(vault_root)
        return f'not-written: incomplete derivation identity ({identity_reason})'
    try:
        head_result = subprocess.run(
            ['git', '-C', str(vault_root), 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _invalidate_archive_cache(vault_root)
        return f'not-written: cannot resolve Git HEAD ({exc})'
    if head_result.returncode != 0:
        _invalidate_archive_cache(vault_root)
        return (
            'not-written: cannot resolve Git HEAD '
            f'({head_result.stderr.strip()})'
        )
    head = head_result.stdout.strip()
    cache_jsonl, cache_meta = _archive_cache_paths(vault_root)
    if reconcile:
        # Reconcile explicitly discards the old derived pair before recreating
        # it from canonical source.  No canonical row/file is ever deleted.
        cache_jsonl.unlink(missing_ok=True)
        cache_meta.unlink(missing_ok=True)
    shard_index.write_verified_jsonl_cache(
        cache_jsonl,
        cache_meta,
        local_archive_records,
        cache_kind=ARCHIVE_CACHE_KIND,
        resolved_commit=head,
        derived_at=_now_iso(),
        source_paths=source_paths,
        extra_meta={
            'derivation_fingerprints': _archive_derivation_fingerprints(),
            'derivation_identity': identity,
        },
    )
    return 'recreated' if reconcile else 'derived'


def _write_index_run_artifact(vault_root: Path, stats: dict[str, Any]) -> None:
    """Write the latest local cost receipt (ignored derived runtime state)."""
    index_surfaces.write_json_atomic(
        vault_root / INDEX_RUN_ARTIFACT_REL,
        stats,
    )


def _replacement_drops_only_mounted_rows(
    vault_root: Path,
    surface_path: Path,
    replacement: list[dict],
    *,
    verify_surface_metadata: bool = True,
) -> bool:
    """Recognize only compose.lock-proven retirement, not unavailability.

    A mounted row is retired only when its vault UID is absent from the current
    compose.lock.  Cache corruption or an unreachable still-pinned mount is not
    retirement evidence and must never bypass the shrink floor.
    """
    if not surface_path.exists():
        return False
    existing = index_surfaces.read_jsonl_strict(
        surface_path,
        verify_surface_metadata=verify_surface_metadata,
    )
    replacement_uids = {
        str(record['uid']) for record in replacement if record.get('uid')
    }
    removed = [
        record
        for record in existing
        if record.get('uid') and str(record['uid']) not in replacement_uids
    ]
    if not removed:
        return False
    pinned_vault_uids = set(
        shard_index.load_compose_lock_vaults(vault_root)
    )
    for record in removed:
        parts = Path(str(record.get('path') or '')).parts
        if (
            len(parts) < 2
            or parts[0] != 'mounted'
            or parts[1] in pinned_vault_uids
        ):
            return False
    return True


def rebuild_index(
    vault_root: Path,
    apply_writes: bool,
    *,
    allow_index_shrink: bool = False,
    reconcile: bool = False,
    governed_floor_recovery: Optional[
        index_surfaces.GovernedFloorRecovery
    ] = None,
    governed_shrink_authorization: Optional[
        index_surfaces.GovernedShrinkAuthorization
    ] = None,
    _index_lock_held: bool = False,
    _force_source_complete: bool = False,
) -> int:
    """Core rebuild logic — scans sources, writes index + project-tree.

    Returns 0 on success, non-zero on failure. Importable for rebuild-vault.py wrapper.
    """
    run_started = time.perf_counter()
    run_started_at = _now_iso()
    if not _index_lock_held:
        try:
            with index_surfaces.index_write_lock(
                vault_root,
                recover=apply_writes,
            ):
                return rebuild_index(
                    vault_root,
                    apply_writes,
                    allow_index_shrink=allow_index_shrink,
                    reconcile=reconcile,
                    governed_floor_recovery=governed_floor_recovery,
                    governed_shrink_authorization=(
                        governed_shrink_authorization
                    ),
                    _index_lock_held=True,
                    _force_source_complete=_force_source_complete,
                )
        except (
            index_surfaces.IndexLockTimeout,
            index_surfaces.IndexSurfaceRefusal,
        ) as exc:
            print(f'ERROR: full rebuild could not acquire index transaction lock — {exc}',
                  file=sys.stderr)
            return 1

    vault_dir = vault_root / 'vault'
    files_dir = vault_dir / 'files'
    index_path = vault_dir / '00-index.jsonl'
    archive_index_path = vault_dir / '00-archive-index.jsonl'
    project_tree_path = vault_dir / '00-project-tree.jsonl'
    sqlite_path_live = vault_dir / '00-index.sqlite'
    initial_derived_state_absent = not any(
        path.exists()
        for path in (
            index_path,
            archive_index_path,
            sqlite_path_live,
            vault_root / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
            vault_root / index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
        )
    )
    if not files_dir.is_dir():
        print(f'ERROR: vault/files/ not found at {files_dir}', file=sys.stderr)
        return 2

    # Validate capsule law before any derived surface is written. A malformed
    # declaration is a hard rebuild failure, never a skipped machine or warning.
    try:
        lifecycle_machines = lifecycle_machine.load_lifecycle_machines(vault_root)
    except lifecycle_machine.LifecycleMachineError as exc:
        print(f'ERROR: lifecycle_machine validation failed — {exc}', file=sys.stderr)
        return 1

    try:
        cached_archive_records, cached_archive_paths, archive_cache_action = (
            _load_reusable_archive_cache(
                vault_root,
                archive_index_path,
                reconcile=(
                    reconcile
                    or allow_index_shrink
                    or initial_derived_state_absent
                    or _force_source_complete
                ),
            )
        )
    except shard_index.VerifiedCacheRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if (
        initial_derived_state_absent
        and archive_cache_action == 'reconcile-bypass'
    ):
        archive_cache_action = 'initial-surface-creation-bypass'
    # The trusted source manifest describes canonical parser inputs, not the
    # verified cache transport that happened to avoid reparsing them.
    archive_cache_inputs: tuple[Path, ...] = ()
    (
        derivation_snapshot_before,
        derivation_snapshot_before_reason,
    ) = _capture_exact_derivation_snapshot(
        vault_root,
        extra_input_paths=archive_cache_inputs,
    )

    print('=' * 70)
    print('rebuild-index.py — fast index + project-tree rebuild (v1.15.1)')
    print('Mode:', 'APPLY (writes will happen)' if apply_writes else 'DRY-RUN (no writes)')
    print('Reconcile:', 'YES (full source re-derivation)' if reconcile else 'no')
    print(f'Archive cache: {archive_cache_action}')
    print(f'Vault root: {vault_root}')
    print('=' * 70)

    records: list[dict[str, Any]] = []
    errors: list[str] = []
    skipped_local_archive_sources = 0

    # Source 1: vault/files/*.md (canonical bulk)
    files = sorted(files_dir.glob('*.md'))
    for f in files:
        if _skip_cached_archive_source(f, vault_root, cached_archive_paths):
            skipped_local_archive_sources += 1
            continue
        rec = process_file(f)
        if rec is None:
            errors.append(f'  parse failed: vault/files/{f.name}')
        else:
            rec['path'] = str(f.relative_to(vault_root))  # v1.69 path-provenance
            records.append(rec)

    # Source 2: Studio-root *.md with uid: frontmatter (v1.15.1 Stream G)
    studio_root_records = collect_studio_root_records(
        vault_root, cached_archive_paths,
    )
    records.extend(studio_root_records)

    # Source 3: vault/capsules/*.capsule.md with uid: frontmatter (v1.51 Argus A80 2026-05-23; ADR-045 One Home v1.76 e8d49d3a)
    # First-class capsule UID queryability per Mike-A80 "fix it right" doctrine.
    capsule_records = collect_capsule_records(vault_root, cached_archive_paths)
    records.extend(capsule_records)

    # Source 4: agents/**/*.md with uid: frontmatter (v1.51 Argus A80 2026-05-23)
    # First-class agents/ substrate queryability — closes the b2c4f01e roadmap finding
    # the dev-spec validator surfaced after capsule indexing fix.
    agents_records = collect_agents_records(vault_root, cached_archive_paths)
    records.extend(agents_records)
    tropo_kernel_records = collect_tropo_kernel_records(vault_root, cached_archive_paths)
    records.extend(tropo_kernel_records)

    # Source 5: vault/tools/ .py/.md/.json (v1.56 E.1 Talos T10 2026-05-27)
    # First-class vault/tools/ indexing per tool.capsule v1.6 §2.5 single-file-truth.
    vault_tools_records = collect_vault_tools_records(
        vault_root, cached_archive_paths,
    )
    records.extend(vault_tools_records)

    # Source 6: vault/actions/ .md/.json (v1.60 Lane A-migrate Talos T10 2026-05-29)
    # First-class vault/actions/ indexing per Pillar 1 single-file-truth pattern.
    vault_actions_records = collect_vault_actions_records(
        vault_root, cached_archive_paths,
    )
    records.extend(vault_actions_records)

    # Source 7: vault/session-agents/ .md (v1.61 Lane S-migrate Talos T11 2026-05-29)
    # First-class vault/session-agents/ indexing per session-agent.capsule v1.6 §2.5
    # single-file-truth pattern. Session-agent class definitions live at
    # vault/session-agents/<uid>.md; each carries YAML frontmatter.
    vault_session_agents_records = collect_vault_session_agents_records(
        vault_root, cached_archive_paths,
    )
    records.extend(vault_session_agents_records)

    # Source 8: vault/agents/ .md (v1.69 P0.6 Talos T14 2026-06-11)
    # First-class vault/agents/ indexing per agent.capsule v2.0 unified-entry shape.
    # Unified agent entries live at vault/agents/<uid>.md (type:agent); created by the
    # v1.69 per-agent migration. Directory may be absent pre-migration — skip silently.
    vault_agents_records = collect_vault_agents_records(
        vault_root, cached_archive_paths,
    )
    records.extend(vault_agents_records)

    # Source 9: vault/playbooks/ .md (v1.69 P0.6 Talos T14 2026-06-11)
    # First-class vault/playbooks/ indexing per playbook.capsule unification.
    # Unified playbook entries live at vault/playbooks/<uid>.md (type:playbook); created
    # by the v1.69 S2 move. Directory may be absent pre-migration — skip silently.
    vault_playbooks_records = collect_vault_playbooks_records(
        vault_root, cached_archive_paths,
    )
    records.extend(vault_playbooks_records)

    # Source 10: vault/skills/ .md (v1.74 Talos T20 2026-06-21)
    # First-class vault/skills/ indexing per how-to.capsule unification.
    # Unified skill entries live at vault/skills/<uid>.md (type:how-to).
    vault_skills_records = collect_vault_skills_records(
        vault_root, cached_archive_paths,
    )
    records.extend(vault_skills_records)

    # Source 11: .tropo-studio/memory/entries/*.md (v1.79 Memory Sovereignty Talos T24 2026-07-03)
    # Studio-scope memory entries written via tropo-memory-write skill. Previously unscanned;
    # rebuild wiped manually-added index rows making the skill's manual-fallback instruction
    # futile. Fix: first-class scan so every rebuild registers studio-scope pins. (event 00005467)
    studio_memory_records = collect_studio_memory_records(
        vault_root, cached_archive_paths,
    )
    records.extend(studio_memory_records)

    # Source 12: agents/*/.tropo-capsule/memory/entries/*.md (v1.79 Memory Sovereignty Talos T24 2026-07-03)
    # Agent-scope memory entries. Excluded from collect_agents_records() by design (.tropo-capsule
    # skip). This dedicated scanner targets only the memory/entries/ leaf — no workspace bleed.
    # Symmetric fix to Source 11. (event 00005467)
    agent_memory_records = collect_agent_memory_records(
        vault_root, cached_archive_paths,
    )
    records.extend(agent_memory_records)

    # A valid cache can only skip paths it already knows.  If a newly scanned
    # local source now routes to archive (new file or current→archive
    # transition), restart once in reconcile mode so canonical ordering and
    # cache equivalence come from one complete source pass.
    if cached_archive_records and any(
        index_surfaces.is_archive_record(record) for record in records
    ):
        print(
            '[ARCHIVE CACHE] new archive-relevant source detected; '
            'rejecting reuse and restarting with full source derivation.'
        )
        return rebuild_index(
            vault_root,
            apply_writes,
            allow_index_shrink=allow_index_shrink,
            reconcile=True,
            governed_floor_recovery=governed_floor_recovery,
            governed_shrink_authorization=governed_shrink_authorization,
            _index_lock_held=_index_lock_held,
            _force_source_complete=_force_source_complete,
        )

    parsed_record_count = len(records)
    cached_archive_snapshot = {
        str(record.get('uid')): record
        for record in cached_archive_records
        if record.get('uid')
    }
    # Mounted archive rows are independently supplied by their verified shard;
    # local rows are inserted here in their original archive-surface order.
    records.extend(
        json.loads(json.dumps(record))
        for record in cached_archive_records
        if not str(record.get('path') or '').startswith('mounted/')
    )

    # Source 13: mounted-vault shards (v1.84 c6f6bea4, ADR-051 Fork 4 — shard-keyed
    # incremental composed index). Each vault_uid pinned in .tropo-studio/compose.lock
    # contributes ONE shard, keyed by that record's resolved_commit (the mount-gate pin,
    # 409ef1cc — no independent hashing). A shard whose cached .meta commit already
    # equals the pin is REUSED verbatim (zero re-derivation); a changed/new pin is
    # re-derived from mount_path's vault/files/ tree using the SAME process_file
    # transform the local shard (Source 1) uses; a vault_uid no longer in compose.lock
    # has its cache retired. compose.lock absent/empty (today's real-studio universal
    # case) => zero mounted shards => this source contributes nothing and every other
    # code path is byte-identical to the pre-shard-index rebuild. STALENESS GUARD: a
    # pinned vault whose shard cannot be verified/re-derived (missing cache AND
    # unreachable mount_path) is EXCLUDED here — never silently unioned as stale/partial
    # — and separately flagged by check_shard_index_consistency (tropo-validate.py).
    # SECURITY-REVIEW FIX (Talos T26, 2026-07-08): apply_writes threaded
    # through so a dry-run (no --apply) performs ZERO shard-cache disk
    # writes, matching this tool's own "DRY-RUN (no writes)" banner —
    # previously resolve_shards() had no apply_writes parameter and always
    # wrote/retired shard cache files for real regardless of this flag.
    mounted_records, shard_statuses = shard_index.resolve_shards(
        vault_root,
        process_file,
        _now_iso(),
        apply_writes=apply_writes,
        force_rederive=(
            reconcile
            or allow_index_shrink
            or not index_path.is_file()
            or not archive_index_path.is_file()
            or _force_source_complete
        ),
    )
    records.extend(mounted_records)
    cannot_compose = [s for s in shard_statuses if s.action == 'cannot-compose']
    reused_count = sum(1 for s in shard_statuses if s.action == 'reused')
    derived_count = sum(1 for s in shard_statuses if s.action == 'derived')
    parsed_record_count += sum(
        status.record_count
        for status in shard_statuses
        if status.action == 'derived'
    )

    print(f'\nFiles discovered (vault/files/): {len(files)}')
    print(f'Archived files skipped by verified cache: {len(cached_archive_paths)}')
    print(f'Studio-root records (Stream G): {len(studio_root_records)}')
    print(f'Capsule records (v1.51 first-class): {len(capsule_records)}')
    print(f'Agents records (v1.51 first-class): {len(agents_records)}')
    _k_admitted, _k_skipped = _tropo_kernel_sources(vault_root)
    print(
        f'Kernel doctrine records (.tropo/, ADR-064): '
        f'{len(tropo_kernel_records)} ({len(_k_skipped)} skipped: no governed uid)'
    )
    print(f'Vault/tools records (v1.56 E.1): {len(vault_tools_records)}')
    print(f'Vault/actions records (v1.60 A-migrate): {len(vault_actions_records)}')
    print(f'Vault/session-agents records (v1.61 Lane S-migrate): {len(vault_session_agents_records)}')
    print(f'Vault/agents records (v1.69 P0.6): {len(vault_agents_records)}')
    print(f'Vault/playbooks records (v1.69 P0.6): {len(vault_playbooks_records)}')
    print(f'Vault/skills records (v1.74): {len(vault_skills_records)}')
    print(f'Studio memory records (v1.79): {len(studio_memory_records)}')
    print(f'Agent memory records (v1.79): {len(agent_memory_records)}')
    print(f'Mounted-vault shard records (v1.84 c6f6bea4): {len(mounted_records)} '
          f'({reused_count} shard(s) reused, {derived_count} re-derived, '
          f'{len(cannot_compose)} cannot-compose)')
    if cannot_compose:
        print(
            f'  [SHARD-INDEX STALENESS GUARD] {len(cannot_compose)} active '
            'compose.lock mount(s) cannot be verified:',
            file=sys.stderr,
        )
        for s in cannot_compose:
            print(
                f'REFUSAL: active mount {s.vault_uid} cannot compose: {s.reason}',
                file=sys.stderr,
            )
        return 1
    print(f'Total records parsed: {parsed_record_count}')
    print(f'Total records assembled: {len(records)}')
    print(f'Parse failures: {len(errors)}')
    if errors:
        for e in errors[:10]:
            print(e)

    # S7 (v1.80): source-precedence dedup — 18 dup-UID rows were surviving rebuild.
    # Root cause: multiple source collectors (vault/files/, session-agents, agents/*,
    # memory entries) can each produce a row for the same UID when files outside
    # vault/files/ accidentally mint the same UID as a canonical vault/files/ entry.
    # Precedence: vault/files/ > vault/session-agents/ > all others.
    # Duplicates within a tier: first-seen wins; collision is logged as a warning.
    #
    # S7 addendum hardening (v1.80 re-build, talos-t24 2026-07-04): the rule above is
    # only safe when the two rows genuinely describe the SAME real-world entity indexed
    # from more than one source (e.g. a migration-era duplicate). A refuter caught it
    # silently dropping TWO governed, DIFFERENT documents that happened to mis-mint the
    # same UID as an unrelated vault/files/ entry (agents/sa/sa.reconciler/sa.reconciler.md
    # collided with vault/files/e4af1001.md, a project; agents/talos/reflections/
    # T19-reflection.md collided with vault/files/a52a5982.md, a living-transfer stub) —
    # the dedup dropped the agent definition + the reflection from the index entirely,
    # making a live governed agent invisible. Same-entity duplicates (identical type +
    # title) still dedupe silently per the source-precedence rule; a DIFFERENT type or
    # title on the same UID is a real cross-document collision and now FAILS LOUD instead
    # of being masked — re-mint one side (python3 vault/tools/tropo-mint-id.py) and re-run.
    # SECURITY-REVIEW FIX (Talos T26, 2026-07-08, c6f6bea4 shard-index build):
    # the same_entity heuristic below (type+title match) is only safe to
    # silently dedupe when both records ALSO share the same vault
    # provenance. Two records from DIFFERENT vaults (a local record and a
    # mounted-shard record, or two different mounts) that happen to collide
    # on UID AND coincidentally share type+title are NOT the same real-world
    # entity — silently keeping one and dropping the other would violate
    # the one-clone-per-vault-UID guarantee (I1) with no warning. `_shard_
    # vault_uid` (set only on mounted-shard records by
    # lib/shard_index.derive_mounted_shard_records; absent/None on every
    # local-studio record) makes vault provenance explicit and checkable
    # here rather than inferred from path shape alone.
    _seen_uids: dict[str, dict] = {}  # uid → {path, type, title, vault_uid} of first-seen record
    _deduped: list[dict] = []
    _dup_log: list[str] = []
    def _source_tier(rec: dict) -> int:
        p = rec.get("path", "")
        if p.startswith("vault/files/"): return 0
        if p.startswith("vault/session-agents/"): return 1
        return 2
    # Sort by tier so vault/files/ records win on UID conflicts
    records.sort(key=_source_tier)
    for rec in records:
        uid = rec.get("uid")
        if not uid:
            _deduped.append(rec)
            continue
        if uid in _seen_uids:
            existing = _seen_uids[uid]
            existing_path = existing["path"]
            new_path = rec.get("path", "?")
            same_vault = existing.get("vault_uid") == rec.get("_shard_vault_uid")
            same_entity = (
                same_vault
                and rec.get("type") == existing.get("type")
                and rec.get("title") == existing.get("title")
            )
            if not same_entity:
                cross_vault_note = (
                    f" — CROSS-VAULT COLLISION (kept-so-far vault_uid={existing.get('vault_uid')!r}, "
                    f"colliding vault_uid={rec.get('_shard_vault_uid')!r}; even matching type+title "
                    f"is never treated as the same entity across different vaults, c6f6bea4)"
                    if not same_vault else ""
                )
                print(
                    f"FAIL-LOUD: cross-document UID collision on {uid!r} — this is NOT a "
                    f"same-entity multi-source duplicate, it is two DIFFERENT governed "
                    f"documents sharing one UID{cross_vault_note}:\n"
                    f"  kept-so-far: {existing_path!r} (type={existing.get('type')!r}, "
                    f"title={existing.get('title')!r})\n"
                    f"  colliding:   {new_path!r} (type={rec.get('type')!r}, "
                    f"title={rec.get('title')!r})\n"
                    f"Refusing to silently drop either side (v1.80 S7 hardening — a prior "
                    f"silent drop here made a governed agent definition invisible in the "
                    f"index). Re-mint one of the two source files to a fresh UID "
                    f"(python3 vault/tools/tropo-mint-id.py) and re-run.",
                    file=sys.stderr)
                sys.exit(1)
            _dup_log.append(
                f"  DUP {uid}: kept {existing_path!r}, dropped {new_path!r} "
                f"(source-precedence rule; same type+title+vault — same entity indexed from multiple sources)")
        else:
            _seen_uids[uid] = {
                "path": rec.get("path", "?"), "type": rec.get("type"), "title": rec.get("title"),
                "vault_uid": rec.get("_shard_vault_uid"),
            }
            _deduped.append(rec)
    if _dup_log:
        print(f'\n[DEDUP] {len(_dup_log)} dup-UID rows eliminated by source-precedence rule:')
        for line in _dup_log[:20]:
            print(line)
        if len(_dup_log) > 20:
            print(f'  ... and {len(_dup_log) - 20} more')
    # Strip the internal-only _shard_vault_uid marker before it proceeds any
    # further (Gardener, sqlite build, the final vault/00-index.jsonl write)
    # — it is a dedup-time-only signal, not part of the committed index schema.
    for _rec in _deduped:
        _rec.pop("_shard_vault_uid", None)
    records = _deduped

    # v1.82 Gardener (8e551957) — S0→S3 decay stamping pass (derived index only; I5 never-sync)
    gardener_completed = False
    try:
        if str(_TOOLS) not in sys.path:
            sys.path.insert(0, str(_TOOLS))
        from lib.gardener import apply_gardener_pass
        gardener_stats = apply_gardener_pass(vault_root, records, apply_writes)
        if cached_archive_snapshot:
            # Cache hits preserve the archive surface verbatim.  The Gardener
            # still sees the union when deriving live-record signals, but its
            # wall-clock/inbound overlays must not rewrite frozen history.
            for index, record in enumerate(records):
                cached_record = cached_archive_snapshot.get(str(record.get('uid')))
                if cached_record is not None:
                    records[index] = json.loads(json.dumps(cached_record))
        print(f'\n[GARDENER v1.82] backfill={gardener_stats["backfill_count"]} '
              f'unscoped_after={gardener_stats["unscoped_after"]} '
              f'clean_stale={gardener_stats["clean_stale_count"]}/{gardener_stats["raw_stale_count"]} raw '
              f'superseded_os={gardener_stats["superseded_os_count"]} '
              f'repo_clock={gardener_stats["repo_clock"]}')
        if gardener_stats.get('lint_count'):
            print(f'  [GARDENER] {gardener_stats["lint_count"]} cross-segment lint(s) surfaced')
        gardener_completed = True
    except Exception as exc:
        print(f'WARN: Gardener pass failed (index rebuild continues): {exc}', file=sys.stderr)

    # v1.69 path-provenance: compute purge list — UIDs in the LIVE DB not collected
    # by any collector this pass (true ghosts; no backing file reachable). These will
    # be ghost-pruned from SQLite on --apply but are listed here BEFORE deletion so
    # Argus can adjudicate (verify-before-destroy per T13/T14 precedent).
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

    mounted_catalog_before = _MountedSourceCatalog(vault_root, records)
    mounted_signature_before = mounted_catalog_before.signature()
    current_records, archive_records = index_surfaces.partition_records(records)

    # Lossless partition is a build-time invariant, not a post-hoc claim.
    if len(current_records) + len(archive_records) != len(records):
        print('ERROR: ADR-047 index partition lost records', file=sys.stderr)
        return 1
    current_uids = {rec.get('uid') for rec in current_records if rec.get('uid')}
    archive_uids = {rec.get('uid') for rec in archive_records if rec.get('uid')}
    overlap = sorted(current_uids & archive_uids)
    if overlap:
        print(f'ERROR: ADR-047 index partition overlap ({len(overlap)} UID(s)): '
              f'{", ".join(overlap[:10])}', file=sys.stderr)
        return 1

    # An absent canonical destination or stale pair sidecar can be repaired
    # only by a derivation that parsed every source instead of trusting any
    # local-archive or mounted-shard cache.  Bind that fact to the exact pair
    # bytes before preflight; partial/cache-backed runs receive no proof.
    source_shortcut_complete = (
        archive_cache_action != 'reused'
        and not cached_archive_paths
        and skipped_local_archive_sources == 0
        and reused_count == 0
        and not errors
        and gardener_completed
    )
    derivation_snapshot_after, source_inventory_reason = (
        _capture_exact_derivation_snapshot(
            vault_root,
            extra_input_paths=archive_cache_inputs,
        )
    )
    stable_derivation_snapshot = None
    if derivation_snapshot_before is None:
        source_inventory_reason = derivation_snapshot_before_reason
    elif derivation_snapshot_after is None:
        pass
    elif derivation_snapshot_before != derivation_snapshot_after:
        source_inventory_reason = (
            'exact derivation bytes/modes changed during the collection pass'
        )
    elif errors:
        source_inventory_reason = (
            'full source collection has parse failures; '
            + ', '.join(error.strip() for error in errors)
        )
    elif not gardener_completed:
        source_inventory_reason = 'Gardener derivation did not complete'
    else:
        stable_derivation_snapshot = derivation_snapshot_after
    if stable_derivation_snapshot is not None:
        stable_derivation_snapshot = _snapshot_with_mounted_catalog(
            stable_derivation_snapshot,
            mounted_catalog_before,
        )

    derivation_provenance = None
    local_collected_paths = {
        str(record['path'])
        for record in records
        if isinstance(record.get('path'), str)
        and not str(record['path']).startswith('mounted/')
    }
    if stable_derivation_snapshot is not None:
        try:
            derivation_provenance = index_surfaces.prove_surface_derivation(
                current_records,
                archive_records,
                manifest=_finalize_derivation_manifest(
                    stable_derivation_snapshot,
                    records,
                    repo_clock=str(gardener_stats.get('repo_clock') or ''),
                    wall_clock_date=str(
                        gardener_stats.get('wall_clock_as_of') or ''
                    ),
                ),
                source_paths=local_collected_paths,
                uncommitted_inputs=stable_derivation_snapshot[
                    'uncommitted_inputs'
                ],
            )
        except index_surfaces.IndexSurfaceRefusal as exc:
            source_inventory_reason = str(exc)

    source_complete = (
        source_shortcut_complete
        and derivation_provenance is not None
    )
    full_source_derivation_proof = None
    if source_complete:
        try:
            exact_source_inventory = tuple(
                (
                    path,
                    mode,
                    content_sha256,
                )
                for kind, path, mode, content_sha256 in (
                    stable_derivation_snapshot['manifest']
                )
                if kind == 'source'
            )
            full_source_derivation_proof = (
                index_surfaces.prove_full_source_derivation(
                    current_records,
                    archive_records,
                    source_complete=True,
                    source_inventory=exact_source_inventory,
                    derivation_provenance=derivation_provenance,
                )
            )
        except index_surfaces.IndexSurfaceRefusal as exc:
            print(str(exc), file=sys.stderr)
            return 1
    elif source_shortcut_complete:
        print(
            '[SOURCE COMPLETENESS] proof unavailable: '
            f'{source_inventory_reason}',
            file=sys.stderr,
        )

    complete_source_required = (
        initial_derived_state_absent
        or not index_path.exists()
        or not archive_index_path.exists()
        or reconcile
        or allow_index_shrink
        or governed_floor_recovery is not None
        or _force_source_complete
    )
    if complete_source_required and full_source_derivation_proof is None:
        print(
            'REFUSAL: full source-complete derivation proof is unavailable; '
            f'{source_inventory_reason}. Land, revert, or isolate the exact '
            'blocking paths first, then rerun the requested operation. '
            'No index participant was written.',
            file=sys.stderr,
        )
        return 1
    if apply_writes and derivation_provenance is None:
        print(
            'REFUSAL: exact derivation provenance is unavailable; '
            f'{source_inventory_reason}. No index participant was written.',
            file=sys.stderr,
        )
        return 1
    derived_from_uncommitted = bool(
        derivation_provenance
        and derivation_provenance.uncommitted_inputs
    )
    if derived_from_uncommitted and (
        reconcile
        or allow_index_shrink
        or governed_floor_recovery is not None
    ):
        uncommitted_paths = [
            path
            for path, _mode, _content_sha, _link_sha in (
                derivation_provenance.uncommitted_inputs
            )
        ]
        print(
            'REFUSAL: uncommitted derivation inputs are non-authoritative for '
            'reconcile, ratchet recovery, or shrink authority; Land, revert, '
            'or isolate the recorded paths first: '
            + ', '.join(uncommitted_paths)
            + '. No index participant was written.',
            file=sys.stderr,
        )
        return 1
    if derived_from_uncommitted:
        uncommitted_paths = [
            path
            for path, _mode, _content_sha, _link_sha in (
                derivation_provenance.uncommitted_inputs
            )
        ]
        print(
            '[SOURCE PROVENANCE] worktree-derived, non-authoritative input(s): '
            + ', '.join(uncommitted_paths)
        )
        if initial_derived_state_absent:
            print(
                '[SOURCE PROVENANCE] initial worktree-derived proof accepted '
                'for local, non-authoritative index creation.'
            )

    metadata_recovery_authorized = (
        reconcile
        and full_source_derivation_proof is not None
        and not derived_from_uncommitted
    )
    try:
        existing_current_count = (
            len(index_surfaces.read_jsonl_strict(
                index_path,
                verify_surface_metadata=full_source_derivation_proof is None,
            ))
            if index_path.exists()
            else 0
        )
        existing_archive_count = (
            len(index_surfaces.read_jsonl_strict(
                archive_index_path,
                verify_surface_metadata=full_source_derivation_proof is None,
            ))
            if archive_index_path.exists()
            else 0
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f'Existing current-index records: {existing_current_count}')
    print(f'Existing archive-index records: {existing_archive_count}')
    print(f'New current-index records:      {len(current_records)}')
    print(f'New archive-index records:      {len(archive_records)}')
    print(f'New union records:              {len(records)}')

    # Mike/A142 index-lifecycle floor: preflight BOTH surfaces before either
    # swap.  A current-only collection pass must not get as far as replacing
    # the archive with an empty projection.  Strict reads make a truncated or
    # corrupt existing surface a refusal rather than an implied zero baseline.
    try:
        current_mounted_retirement = (
            not allow_index_shrink
            and _replacement_drops_only_mounted_rows(
                vault_root,
                index_path,
                current_records,
                verify_surface_metadata=full_source_derivation_proof is None,
            )
        )
        archive_mounted_retirement = (
            not allow_index_shrink
            and _replacement_drops_only_mounted_rows(
                vault_root,
                archive_index_path,
                archive_records,
                verify_surface_metadata=full_source_derivation_proof is None,
            )
        )
        index_surfaces.preflight_jsonl_replacement(
            index_path,
            current_records,
            allow_shrink=(
                allow_index_shrink
                or current_mounted_retirement
            ),
            full_source_derivation_proof=full_source_derivation_proof,
            allow_surface_metadata_recovery=metadata_recovery_authorized,
        )
        index_surfaces.preflight_jsonl_replacement(
            archive_index_path,
            archive_records,
            allow_shrink=(
                allow_index_shrink
                or archive_mounted_retirement
            ),
            full_source_derivation_proof=full_source_derivation_proof,
            allow_surface_metadata_recovery=metadata_recovery_authorized,
        )
    except index_surfaces.IndexSurfaceRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 1
    mounted_retirement_paths = {
        path
        for path, allowed in (
            (index_path, current_mounted_retirement),
            (archive_index_path, archive_mounted_retirement),
        )
        if allowed
    }
    if mounted_retirement_paths:
        if current_mounted_retirement or archive_mounted_retirement:
            print(
                '[SHRINK FLOOR] composed mounted-row retirement recognized '
                'from explicit compose.lock removal; local-row shrink floor '
                'remains enforced.'
            )
    project_tree = build_project_tree(records)
    print(f'Project tree records: {len(project_tree)}')

    # Prepare SQLite before any destination swap. Full apply commits SQLite,
    # both JSONLs, and their trusted pair sidecar through one durable journal.
    sqlite_raw: Optional[bytes] = None
    try:
        sqlite_raw = build_sqlite_index(
            vault_root,
            records,
            apply_writes,
            machines=lifecycle_machines,
            defer_replace=apply_writes,
            mounted_catalog=mounted_catalog_before,
        )
    except Exception as exc:
        print(f'ERROR: SQLite index build failed before index transaction: {exc}',
              file=sys.stderr)
        return 1
    mounted_catalog_after = _MountedSourceCatalog(vault_root, records)
    if mounted_signature_before != mounted_catalog_after.signature():
        print(
            'REFUSAL: mounted registry/source inputs changed during SQLite '
            'derivation. No index participant was written.',
            file=sys.stderr,
        )
        return 1

    if apply_writes:
        if sqlite_raw is None:
            print('ERROR: SQLite index preparation returned no durable image',
                  file=sys.stderr)
            return 1
        try:
            current_count, archive_count = index_surfaces.write_jsonl_pair_atomic(
                (
                    (index_path, current_records),
                    (archive_index_path, archive_records),
                ),
                allow_shrink=allow_index_shrink,
                allow_shrink_paths=mounted_retirement_paths,
                shrink_baseline_advance_reason=(
                    'explicit-adjudicated-shrink-override'
                    if allow_index_shrink
                    else None
                ),
                companion_replacements=((sqlite_path_live, sqlite_raw),),
                full_source_derivation_proof=full_source_derivation_proof,
                derivation_provenance=derivation_provenance,
                surface_metadata_recovery_reason=(
                    'source-complete-reconcile'
                    if metadata_recovery_authorized
                    else None
                ),
                governed_floor_recovery=governed_floor_recovery,
                governed_shrink_authorization=(
                    governed_shrink_authorization
                ),
            )
        except index_surfaces.IndexSurfaceRefusal as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f'\nWrote {index_path.relative_to(vault_root)} ({current_count} current records).')
        print(f'Wrote {archive_index_path.relative_to(vault_root)} '
              f'({archive_count} archived/superseded records).')
        print(f'Wrote {sqlite_path_live.relative_to(vault_root)} '
              f'as the same recoverable index transaction.')

        tmp_pt = project_tree_path.with_suffix('.jsonl.tmp')
        with tmp_pt.open('w') as f:
            for node in project_tree:
                f.write(json.dumps(node, separators=(',', ':')) + '\n')
        os.replace(tmp_pt, project_tree_path)
        print(f'Wrote {project_tree_path.relative_to(vault_root)} ({len(project_tree)} nodes).')
    else:
        print('\nDRY-RUN complete. Re-run with --apply to write the index + project tree.')

    if apply_writes:
        _bump_dirty_counter(vault_root, reset=True)
        cache_write_action = archive_cache_action
        if derived_from_uncommitted:
            _invalidate_archive_cache(vault_root)
            cache_write_action = (
                'not-written: initial worktree-derived cache reuse disabled'
                if initial_derived_state_absent
                else 'not-written: uncommitted derivation cache reuse disabled'
            )
        elif archive_cache_action != 'reused':
            try:
                cache_write_action = _write_archive_cache(
                    vault_root,
                    archive_index_path,
                    archive_records,
                    reconcile=reconcile,
                )
            except (OSError, shard_index.VerifiedCacheRefusal) as exc:
                print(
                    f'ERROR: archive cache could not be written safely — {exc}',
                    file=sys.stderr,
                )
                return 1

        elapsed = time.perf_counter() - run_started
        run_artifact = {
            'schema_version': 2,
            'run_started_at': run_started_at,
            'mode': (
                'initial-worktree-derived'
                if initial_derived_state_absent
                and derived_from_uncommitted
                else (
                    'worktree-derived'
                    if derived_from_uncommitted
                    else (
                        'schema2-full-bootstrap'
                        if _force_source_complete
                        else ('reconcile' if reconcile else 'normal')
                    )
                )
            ),
            'wall_clock_seconds': elapsed,
            'parsed_record_count': parsed_record_count,
            'assembled_record_count': len(records),
            'current_record_count': len(current_records),
            'archive_record_count': len(archive_records),
            'archive_source_skip_count': len(cached_archive_paths),
            'archive_cache_action': cache_write_action,
            'worktree_derived': derived_from_uncommitted,
            'worktree_derived_paths': (
                [
                    path
                    for path, _mode, _content_sha, _link_sha in (
                        derivation_provenance.uncommitted_inputs
                    )
                ]
                if derivation_provenance is not None
                else []
            ),
            'derived_from_uncommitted': derived_from_uncommitted,
            'uncommitted_inputs': (
                _uncommitted_input_receipt(stable_derivation_snapshot)
                if stable_derivation_snapshot is not None
                else []
            ),
            'source_inventory_sha256': (
                derivation_provenance.manifest_sha256
                if derivation_provenance is not None
                else None
            ),
            'authoritative_for': {
                'federation': not derived_from_uncommitted,
                'local': True,
                'ratchet_baseline': not derived_from_uncommitted,
                'release': not derived_from_uncommitted,
            },
            'archive_cache_reuse_disabled': derived_from_uncommitted,
        }
        try:
            _write_index_run_artifact(vault_root, run_artifact)
        except OSError as exc:
            print(
                f'ERROR: index run artifact could not be written — {exc}',
                file=sys.stderr,
            )
            return 1
        print(
            f'[RUN ARTIFACT] {INDEX_RUN_ARTIFACT_REL} '
            f'(wall_clock_seconds={elapsed:.6f}, '
            f'parsed_record_count={parsed_record_count}).'
        )

    return 0


def _parse_recovery_floors(value: str) -> tuple[int, int]:
    try:
        current_raw, archive_raw = value.split(":", 1)
        current_floor = int(current_raw)
        archive_floor = int(archive_raw)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            "expected CURRENT:ARCHIVE nonnegative integer floors"
        ) from exc
    if current_floor < 0 or archive_floor < 0:
        raise argparse.ArgumentTypeError(
            "recovery floors must be nonnegative"
        )
    return current_floor, archive_floor


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Rebuild vault/00-index.jsonl + 00-project-tree.jsonl (fast; v1.15.1; v1.30.0 Stream B auto-invoke rehydrate).',
    )
    parser.add_argument('--apply', action='store_true',
                        help='Write changes (default is dry-run preview).')
    parser.add_argument(
        '--allow-index-shrink',
        action='store_true',
        help='Explicitly override the current/archive shrink floor after human '
             'adjudication. Requires --shrink-authorization-uid and '
             '--shrink-evidence-uid. Reconcile alone never grants this authority.',
    )
    parser.add_argument(
        '--shrink-authorization-uid',
        metavar='UID',
        help='8-hex UID identifying the authority that approved an explicit '
             '--allow-index-shrink operation.',
    )
    parser.add_argument(
        '--shrink-evidence-uid',
        metavar='UID',
        help='8-hex UID identifying the reviewed evidence supporting an '
             '--allow-index-shrink operation.',
    )
    parser.add_argument(
        '--reconcile',
        action='store_true',
        help='Force full source re-derivation, bypass/recreate the verified '
             'archive cache, and print purge candidates. Writes still require '
             '--apply; reconcile alone is a no-write preview.',
    )
    parser.add_argument(
        '--recover-index-floors',
        type=_parse_recovery_floors,
        metavar='CURRENT:ARCHIVE',
        help='Governed total-loss recovery only: caller-supplied protected '
             'current/archive floors. Requires --apply --reconcile and '
             '--floor-recovery-evidence-uid; the restored floor is the maximum '
             'of supplied, observed, and any independently valid history.',
    )
    parser.add_argument(
        '--floor-recovery-evidence-uid',
        metavar='UID',
        help='8-hex authorization/evidence UID governing '
             '--recover-index-floors.',
    )
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
                             '(brief d7b3f1a9 §4 — the L2 cockpit-reflect-on-edit gate). '
                             'Requires the source file to still exist (re-derives from it).')
    parser.add_argument('--remove', metavar='UID',
                        help='Governed Autonomy S2 (bba40cd7): remove ONLY this entry\'s index '
                             'rows (entries/edges/FTS + the 00-index.jsonl line) — the deletion '
                             'counterpart to --only, for callers (recycle) whose source file no '
                             'longer exists to re-derive from. Idempotent; no-op if already absent.')
    parser.add_argument('--dirty-status', action='store_true',
                        help='Governed Autonomy S2 (bba40cd7): print the writes-since-full-rebuild '
                             'counter and exit (0 under threshold, 1 over — for a boot/maintenance '
                             'health line; incremental freshens/removals increment it, a full '
                             '--apply rebuild resets it).')
    args = parser.parse_args()

    shrink_authority_requested = (
        args.allow_index_shrink
        or args.shrink_authorization_uid is not None
        or args.shrink_evidence_uid is not None
    )
    if shrink_authority_requested and (
        not args.allow_index_shrink
        or args.shrink_authorization_uid is None
        or args.shrink_evidence_uid is None
        or args.only
        or args.remove
        or args.dirty_status
    ):
        parser.error(
            "explicit shrink authority requires --allow-index-shrink, "
            "--shrink-authorization-uid UID, and --shrink-evidence-uid UID; "
            "it cannot be combined with --only, --remove, or --dirty-status"
        )
    governed_shrink_authorization = None
    if shrink_authority_requested:
        for flag, uid in (
            ("--shrink-authorization-uid", args.shrink_authorization_uid),
            ("--shrink-evidence-uid", args.shrink_evidence_uid),
        ):
            if (
                len(uid) != 8
                or any(char not in "0123456789abcdef" for char in uid)
            ):
                parser.error(f"{flag} must be 8 lowercase hex")
        governed_shrink_authorization = (
            index_surfaces.GovernedShrinkAuthorization(
                authorization_uid=args.shrink_authorization_uid,
                evidence_uid=args.shrink_evidence_uid,
            )
        )

    recovery_requested = (
        args.recover_index_floors is not None
        or args.floor_recovery_evidence_uid is not None
    )
    if recovery_requested and (
        args.recover_index_floors is None
        or args.floor_recovery_evidence_uid is None
        or not args.apply
        or not args.reconcile
        or args.only
        or args.remove
        or args.dirty_status
        or args.allow_index_shrink
    ):
        parser.error(
            "governed floor recovery requires both "
            "--recover-index-floors CURRENT:ARCHIVE and "
            "--floor-recovery-evidence-uid UID with --apply --reconcile; "
            "it cannot be combined with --only, --remove, --dirty-status, "
            "or --allow-index-shrink"
        )
    governed_floor_recovery = None
    if recovery_requested:
        evidence_uid = args.floor_recovery_evidence_uid
        if (
            len(evidence_uid) != 8
            or any(char not in "0123456789abcdef" for char in evidence_uid)
        ):
            parser.error("--floor-recovery-evidence-uid must be 8 lowercase hex")
        current_floor, archive_floor = args.recover_index_floors
        governed_floor_recovery = index_surfaces.GovernedFloorRecovery(
            current_protected_record_count=current_floor,
            archive_protected_record_count=archive_floor,
            evidence_uid=evidence_uid,
        )

    vault = resolve_vault_root(args.vault_path)
    if vault is None:
        print('ERROR: Could not resolve vault root.', file=sys.stderr)
        print('Pass --vault-path <path> with an absolute path to a vault containing vault/ + .tropo/.',
              file=sys.stderr)
        return 2

    # rebuild --dirty-status: query-only, no writes.
    if args.dirty_status:
        status = dirty_counter_status(vault)
        if status['over_threshold']:
            print(f"🔔 vault index: {status['count']} incremental writes since the last full "
                  f"rebuild (threshold {status['threshold']}) — a full rebuild is recommended "
                  f"(python3 vault/tools/tropo-rebuild-index.py --apply).")
            return 1
        print(f"vault index: {status['count']} incremental writes since the last full rebuild "
              f"(threshold {status['threshold']}) — under threshold.")
        return 0

    # rebuild --only <uid>: incremental single-entry freshen; bypasses the full rebuild path.
    if args.only:
        return freshen_one(args.only, vault)

    # rebuild --remove <uid>: incremental single-entry removal; bypasses the full rebuild path.
    if args.remove:
        return remove_one(args.remove, vault)

    rebuild_rc = rebuild_index(
        vault,
        args.apply,
        allow_index_shrink=args.allow_index_shrink,
        reconcile=args.reconcile,
        governed_floor_recovery=governed_floor_recovery,
        governed_shrink_authorization=governed_shrink_authorization,
    )
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

    if args.apply:
        if not MINT_REGISTRY_GENERATOR.exists():
            print(
                f'  ✗ {MINT_REGISTRY_GENERATOR.name} not found; a rebuilt Studio '
                'cannot mint governed files.',
                file=sys.stderr,
            )
            return 8
        mint_result = subprocess.run(
            [
                sys.executable,
                str(MINT_REGISTRY_GENERATOR),
                '--vault-path',
                str(vault),
            ],
            cwd=str(vault),
            timeout=120,
        )
        if mint_result.returncode != 0:
            print(
                f'  ✗ mint-registry generation FAILED (exit code '
                f'{mint_result.returncode})',
                file=sys.stderr,
            )
            return 8
        print('  ✓ mint registry generated')

    return 0


if __name__ == '__main__':
    sys.exit(main())

