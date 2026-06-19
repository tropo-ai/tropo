#!/usr/bin/env python3
"""
---
uid: bf886f30
type: tool
name: import-walker.py
title: import-walker.py — Substrate-Internal Walker
description: 'The substrate-internal Python walker for the import primitive. Subcommands: ingest (ONE GESTURE — recursively sidecar every NEW file under 04-external-work/, zero args; v1.70 hardening), scan (enumerate + categorize), create-sidecar (author sidecar + folder marker + folder mirror + vault projection), reconcile (drift detection), apply (substrate write), promote-folder (Tier 1 → Tier 2). Library-mode invokable from other scripts. v1.0.3 (v1.28.0) added folder-marker mirror co-write + original_styles population + ordered-write protocol + retro-fill semantics + Members rebuild. v1.0.4 (v1.70) added the ingest one-gesture import + ~$ lock-file filter + --dry-run.'
version: 1.0.3
status: active
state: active
stage: build
schema_version: 2
extraction_scope: ship
author: argus
owner: argus
language: python
path: .tropo/scripts/import-walker.py
script_path: vault/tools/bf886f30.py
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/bf886f30.py {scan|create-sidecar|reconcile|apply|promote-folder|extract} [...]
spawnable_by:
- all-executives
- user
- sa.reconciler
destructive: 'true'
audit_required: 'true'
writes_scope:
- '**/.tropo-studio/**'
- vault/files/**
- vault/00-index.jsonl
- .tropo-studio/reconciler/journal.jsonl
reads_scope:
- '**'
governance_category: lifecycle
domain: Substrate-internal walker for the import primitive (v1.25.0 + v1.26.0 + v1.28.0). Authors sidecars + folder markers + folder mirrors + vault projections; computes hashes via the stable-id → content-aware → sha256 fallback chain; appends to the reconciler journal.
domain_tags:
- import-walker
- substrate-internal
- sidecar
- folder-marker
- folder-mirror
- vault-projection
- hash-chain
- journal
- v1.25.0-stream-b
- v1.28.0-stream-b
trigger_description: 'Reach for this when the import primitive needs substrate-internal operations — scanning a Studio for governable folders/files, authoring a sidecar + folder mirror + projection for one source file, running drift detection, applying a reconciler-event payload, or promoting a folder Tier 1 → Tier 2. Most users do NOT invoke this directly; sa.reconciler spawns it for reconciliation, and the v1.25.0 + v1.28.0 onboarding flows trigger create-sidecar implicitly. Direct invocation is for substrate-repair and CI-style scripted import. v1.28.0 v1.0.3 amendments: create-sidecar now co-writes folder-marker MIRROR at vault/files/<folder-uid>.md alongside the on-disk marker (ordered-write protocol with atomic-rename + inline index sync); populates `original_styles:` on .docx projections via shared office_styles library; supports retro-fill for pre-v1.28.0 imports; rebuilds folder mirror Members section from registry walk on every invocation.'
governed_by: d5e1b4a3
capsule_version: '2.5'
created: 2026-05-13
modified: 2026-05-14
created_by: argus-a60
modified_by: argus-a62
aligned_with:
- 2b49ba79
- 5a89297a
member_of:
- f1d7fe66
- e3cde3f4
tags:
- tool
- python
- import-walker
- substrate-internal
- v1.25.0-stream-b
- v1.28.0-stream-b
subsystem_hub:
- 76bab75f
---
"""

"""import-walker.py — Deep recursive walker for the Tropo import primitive.

The primary substrate-mutation tool for the import primitive. Performs:
    - Enumeration of sidecars + source files + vault projections
    - Hash computation per the three-step fallback chain (stable-id → content-aware → sha256)
    - Sidecar + folder-marker + vault-projection authoring
    - Audit-log appends to .tropo-studio/reconciler/journal.jsonl
    - Concurrency-safe writes via .tropo-studio/reconciler/.lock

Commands (v1.0):
    scan              Enumerate substrate; output UID-to-state map (no writes)
    create-sidecar    Author a sidecar (+ folder marker + projection) for a single source file
    reconcile         Full reconciliation pass; categorize events; apply routine + pattern-matched
    apply             Apply a single categorized event (JSON via --event or stdin)

Phase 2 stubs (v1.26.0+; raise SystemExit):
    promote-folder    Tier 1 → Tier 2 upgrade
    extract           Three extraction modes (ungoverned / tier-1-sidecar / stay)

Usage:
    python3 .tropo/scripts/import-walker.py scan
    python3 .tropo/scripts/import-walker.py create-sidecar --source <path>
    python3 .tropo/scripts/import-walker.py reconcile --dry-run
    python3 .tropo/scripts/import-walker.py reconcile --apply --write-journal
    python3 .tropo/scripts/import-walker.py apply --event '{"action": "create_sidecar", ...}'

No third-party dependencies. Targets Python 3.8+. Per spec [vault/files/2b49ba79.md].

Author: argus-a60
Owner: argus
Tool UID: bf886f30
Spec: vault/files/2b49ba79.md (Import Primitive Architecture Specification v1.0 LOCKED)
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Shared office-style extraction module (v1.28.0 NEW per arch-spec 5a89297a §3.5.5 Amendment 2).
# v1.56 Lane S inline closure by metis-g62 2026-05-27: office_styles also migrated to
# vault/tools/<uid>.py (UID d1f2420d per registry). The original v1.56 partial-migration
# assumed office_styles stayed at .tropo/scripts/ — that assumption broke when office_styles
# moved too. Load via same-dir UID-based importlib per v1.56 single-file-truth doctrine;
# matches the pattern used in tropo-extract.py (561d3c75) for the import-walker dependency.
import importlib.util as _importlib_util  # noqa: E402
_OS_PATH = Path(__file__).parent / 'd1f2420d.py'
if not _OS_PATH.exists():
    raise SystemExit(
        f"FATAL: required substrate {_OS_PATH} not present "
        "(office_styles UID d1f2420d per v1.56 migration)"
    )
_OS_SPEC = _importlib_util.spec_from_file_location('office_styles', _OS_PATH)
office_styles = _importlib_util.module_from_spec(_OS_SPEC)
_OS_SPEC.loader.exec_module(office_styles)


def _url_quote_path(p):
    """URL-encode a path for the URL portion of a markdown link.

    Path separators are preserved; spaces and other unsafe chars are percent-
    encoded so renderers don't break on `[text](path with spaces.docx)`.
    Closes sa.reconciler-001 Finding 3 (LOW; argus-a61 2026-05-13).
    """
    return urllib.parse.quote(str(p), safe='/')


TOOL_NAME = 'import-walker'
TOOL_VERSION = '1.0.3'   # v1.0.3 = v1.28.0 Stream B amendments per arch-spec 5a89297a §3.5.5 v0.5
                          # Amendment 1 (folder-marker mirror co-write) + Amendment 2 (original_styles
                          # population). Bumped from v1.0.1 by argus-a62 2026-05-14.

# vault/00-index.jsonl path — inline-sync target per arch-spec §3.10 check 4 (v0.5 widened
# to include type:project folder-marker mirrors authored by create-sidecar)
VAULT_INDEX_RELPATH = 'vault/00-index.jsonl'

# Tropo-work hub UID — the work-substrate L0 root project. Used as member_of for
# root-level sidecars (which have no folder-project parent since Studio root is the
# install context, not a folder-project). Resolves to a real type:project entry.
# Per project.capsule v2.4 §Sub-patterns "L0 root project" — tropo-work is the
# canonical L0 root for work-substrate; user-imported file is a legitimate child.
TROPO_WORK_L0_UID = '2d083137'

# Substrate paths (relative to Studio root)
LOCK_RELPATH = '.tropo-studio/reconciler/.lock'
JOURNAL_RELPATH = '.tropo-studio/reconciler/journal.jsonl'
LOCK_STALE_SECONDS = 3600

# Kernel-known never-ingest directories
KERNEL_INGEST_NEVER = {
    '.tropo', '.tropo-studio', 'vault', 'agents', 'channels', 'playbooks',
    '00-tropo-nav', '01-exchange', 'playbook-runs',
    'recycle', 'archive', 'updates', 'shared', 'templates', 'context',
    'boards', '.git', '.svn', '.hg', '.obsidian',
    # NOTE: '01-studio-inbox' was previously in this set; removed 2026-05-24 by metis-g60
    # under Mike-G60 directive after stress-test b3e9c4a7 surfaced the gap. The inbox's
    # AGENTS.md doctrine explicitly expects items to be "Promoted to a governed
    # vault/files/<uid>.md artifact" — exactly what the import primitive does. Excluding
    # 01-studio-inbox contradicted the inbox's own purpose. The inbox is THE source-
    # content surface by design; the walker should treat it as walkable like any other
    # source folder.
}

OFFICE_EXTENSIONS = {'.docx', '.xlsx', '.pptx'}
PDF_EXTENSIONS = {'.pdf'}

# Confidence thresholds (strict inequalities per arch-spec §C.5 Rule 2)
THRESHOLD_ROUTINE = 0.95
THRESHOLD_PATTERN = 0.80
THRESHOLD_JUDGMENT = 0.50


# ==========================================================================
# Studio root + ignore parsing
# ==========================================================================

def resolve_studio_root(arg_path=None):
    """Find Studio root: explicit arg, or walk up from cwd looking for .tropo/."""
    if arg_path:
        p = Path(arg_path).resolve()
        if (p / '.tropo').exists():
            return p
        raise SystemExit(f"--studio-root {arg_path} does not contain .tropo/")
    cwd = Path.cwd()
    for candidate in [cwd] + list(cwd.parents):
        if (candidate / '.tropo').exists():
            return candidate
    raise SystemExit("Could not find Studio root — no .tropo/ in cwd or ancestors.")


def parse_tropoignore(studio_root):
    """Read .tropoignore; return list of patterns."""
    ignore_file = studio_root / '.tropoignore'
    if not ignore_file.exists():
        return []
    patterns = []
    with ignore_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            patterns.append(line)
    return patterns


def matches_ignore(entry_name, is_dir, patterns):
    """Match against .tropoignore + kernel never-ingest."""
    if entry_name in KERNEL_INGEST_NEVER:
        return True
    for pattern in patterns:
        dir_only = pattern.endswith('/')
        stripped = pattern.rstrip('/')
        if dir_only and not is_dir:
            continue
        if fnmatch.fnmatch(entry_name, stripped):
            return True
        if '/' in stripped:
            base = stripped.split('/')[-1]
            if base and fnmatch.fnmatch(entry_name, base):
                return True
    return False


# ==========================================================================
# Minimal YAML frontmatter parser (stdlib-only)
# ==========================================================================

def parse_frontmatter(file_path):
    """Parse YAML-like frontmatter from a markdown file. Returns dict (possibly empty)."""
    if not file_path.exists():
        return {}
    try:
        text = file_path.read_text()
    except (OSError, UnicodeDecodeError):
        return {}
    if not text.startswith('---'):
        return {}
    rest = text[3:].lstrip('\n')
    end_idx = rest.find('\n---')
    if end_idx == -1:
        return {}
    frontmatter = rest[:end_idx]
    return _parse_yaml(frontmatter)


def _parse_yaml(text):
    """Minimal parser. Handles: scalars, quoted strings, arrays (- prefix at +2 indent), simple maps."""
    result = {}
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            i += 1
            continue
        # Top-level key: value (must not be indented)
        if line.startswith(' ') or line.startswith('\t'):
            i += 1
            continue
        m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$', line)
        if not m:
            i += 1
            continue
        key = m.group(1)
        value = m.group(2).strip()
        if value:
            result[key] = _parse_scalar(value)
            i += 1
        else:
            # Multi-line: collect indented continuation
            items = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip() or nxt.lstrip().startswith('#'):
                    j += 1
                    continue
                if not (nxt.startswith('  ') or nxt.startswith('\t')):
                    break
                inner = nxt.strip()
                if inner.startswith('- '):
                    items.append(_parse_scalar(inner[2:].strip()))
                    j += 1
                else:
                    # Skip nested maps for v1.0 (sidecars don't use them)
                    j += 1
            result[key] = items if items else ''
            i = j
    return result


def _parse_scalar(value):
    """Parse a scalar YAML value."""
    if not value:
        return ''
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.lower() in ('true', 'yes'):
        return True
    if value.lower() in ('false', 'no'):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


# ==========================================================================
# Hash function: three-step fallback chain
# ==========================================================================

def compute_hash(file_path):
    """Returns (hash_hex, hash_function_name)."""
    ext = file_path.suffix.lower()

    # Step 1: stable-identifier for Office files
    if ext in OFFICE_EXTENSIONS:
        sid = _extract_office_stable_id(file_path)
        if sid:
            return _hash_string(f"{sid}:{file_path.name}"), 'stable-id'

    # Step 1b: stable-identifier for PDFs
    if ext in PDF_EXTENSIONS:
        pid = _extract_pdf_id(file_path)
        if pid:
            return _hash_string(f"{pid}:{file_path.name}"), 'stable-id'

    # Step 2: content-aware hash for Office files
    if ext in OFFICE_EXTENSIONS:
        cah = _content_aware_hash_office(file_path)
        if cah:
            return cah, 'content-aware'

    # Step 3: plain SHA-256
    return _plain_sha256(file_path), 'sha256'


def _hash_string(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def _extract_office_stable_id(file_path):
    """Extract dc:identifier from docProps/core.xml inside an Office ZIP."""
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            if 'docProps/core.xml' not in zf.namelist():
                return None
            with zf.open('docProps/core.xml') as f:
                tree = ET.parse(f)
                ns = {'dc': 'http://purl.org/dc/elements/1.1/'}
                el = tree.getroot().find('dc:identifier', ns)
                if el is not None and el.text:
                    return el.text.strip()
        return None
    except (zipfile.BadZipFile, ET.ParseError, OSError):
        return None


def _extract_office_description(file_path):
    """Extract a description string from docProps/core.xml inside an Office ZIP.

    Prefers dc:description (typically the richer user-authored summary); falls
    back to dc:subject (typically a shorter tag-line); returns None if neither
    is populated or the file isn't an Office ZIP.

    Added 2026-05-13 (argus-a61) per Mike-A61 directive — auto-populate the
    projection + sidecar `description:` field on import so vault queries can
    surface meaningful descriptors for stranger-user discoverability.
    """
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            if 'docProps/core.xml' not in zf.namelist():
                return None
            with zf.open('docProps/core.xml') as f:
                tree = ET.parse(f)
                ns = {'dc': 'http://purl.org/dc/elements/1.1/'}
                for tag in ('dc:description', 'dc:subject'):
                    el = tree.getroot().find(tag, ns)
                    if el is not None and el.text and el.text.strip():
                        text = el.text.strip()
                        # Collapse internal whitespace + cap length for safety.
                        text = re.sub(r'\s+', ' ', text)
                        if len(text) > 500:
                            text = text[:497].rstrip() + '...'
                        return text
        return None
    except (zipfile.BadZipFile, ET.ParseError, OSError):
        return None


def _extract_pdf_id(file_path):
    """Read the last 4KB of a PDF and parse the /ID array."""
    try:
        with file_path.open('rb') as f:
            f.seek(0, 2)
            size = f.tell()
            read_size = min(4096, size)
            f.seek(size - read_size)
            tail = f.read(read_size)
        m = re.search(rb'/ID\s*\[\s*<([0-9a-fA-F]+)>', tail)
        if m:
            return m.group(1).decode('ascii')
        return None
    except OSError:
        return None


def _content_aware_hash_office(file_path):
    """Hash the XML payload inside an Office ZIP (excludes volatile metadata)."""
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            ext = file_path.suffix.lower()
            if ext == '.docx':
                payload_files = [n for n in zf.namelist() if n == 'word/document.xml']
            elif ext == '.xlsx':
                payload_files = sorted([n for n in zf.namelist() if n.startswith('xl/worksheets/') and n.endswith('.xml')])
            elif ext == '.pptx':
                payload_files = sorted([n for n in zf.namelist() if n.startswith('ppt/slides/') and n.endswith('.xml')])
            else:
                payload_files = []
            if not payload_files:
                return None
            h = hashlib.sha256()
            for name in payload_files:
                with zf.open(name) as f:
                    h.update(f.read())
            return h.hexdigest()
    except (zipfile.BadZipFile, OSError):
        return None


def _plain_sha256(file_path):
    """SHA-256 of file bytes."""
    h = hashlib.sha256()
    try:
        with file_path.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError as e:
        raise SystemExit(f"Could not read {file_path}: {e}")


# ==========================================================================
# Lock management
# ==========================================================================

class ReconcilerLock:
    """Context manager for the exclusive lock at .tropo-studio/reconciler/.lock"""

    def __init__(self, studio_root):
        self.studio_root = studio_root
        self.lock_path = studio_root / LOCK_RELPATH
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.held = False

    def __enter__(self):
        if self.lock_path.exists():
            age = time.time() - self.lock_path.stat().st_mtime
            if age > LOCK_STALE_SECONDS:
                print(f"WARN: stale lock at {self.lock_path} (age {int(age)}s); overriding", file=sys.stderr)
                self.lock_path.unlink(missing_ok=True)
        try:
            with self.lock_path.open('x') as f:
                f.write(f"locked by pid {os.getpid()} at {datetime.now(timezone.utc).isoformat()}\n")
            self.held = True
            return self
        except FileExistsError:
            raise SystemExit(f"Lock held at {self.lock_path}. Another reconciler is running. Exit cleanly.")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.held:
            self.lock_path.unlink(missing_ok=True)
        return False


# ==========================================================================
# UID + timestamps
# ==========================================================================

def generate_uid():
    """8-hex UID; same shape as `openssl rand -hex 4`."""
    return secrets.token_hex(4)


def now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def now_date():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


# ==========================================================================
# Sidecar / folder-marker / vault-projection writers
# ==========================================================================

def _yaml_str(s):
    """YAML-safe string interpolation: use JSON-style escaping. JSON strings are a
    subset of YAML strings, so this is safe and handles quotes/backslashes/colons."""
    return json.dumps(s)


def write_sidecar(sidecar_path, uid, source_filename, source_path_rel, original_path,
                  size_bytes, mtime_iso, source_hash, hash_function, folder_uid,
                  governance='tier-1-sidecar', title=None, description=''):
    """Author a sidecar with full external-artifact frontmatter.
    String values are JSON-escaped for YAML safety (handles quotes, colons, backslashes)."""
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    title = title or source_filename
    # Body uses plain markdown-safe rendering (no special chars expected from internals)
    body_title = title.replace('\n', ' ').replace('`', "'")
    body_path = source_path_rel.replace('`', "'")
    content = f"""---
uid: {uid}
type: external-artifact
status: active
title: {_yaml_str(title)}
owner: {TOOL_NAME}-v{TOOL_VERSION}
source_filename: {_yaml_str(source_filename)}
source_path: {_yaml_str(source_path_rel)}
original_path: {_yaml_str(original_path)}
source_size_bytes: {size_bytes}
source_mtime: {mtime_iso}
source_hash: {source_hash}
hash_function: {hash_function}
member_of:
  - {_yaml_str(folder_uid)}
governance: {governance}
description: {_yaml_str(description)}
created: {now_date()}
created_by: {TOOL_NAME}-v{TOOL_VERSION}
modified: {now_date()}
modified_by: {TOOL_NAME}-v{TOOL_VERSION}
schema_version: 1
---

# {body_title} — Tropo Sidecar

Governs `{body_path}` in folder-project `{folder_uid}`.
Vault projection at `vault/files/{uid}.md` (Tier 1).
"""
    sidecar_path.write_text(content)
    return uid


def write_folder_marker(folder_path, uid, folder_name, original_path,
                        parent_member=TROPO_WORK_L0_UID, governance='tier-1-sidecar'):
    """Author a .tropo-folder.md (project.capsule v2.4 instance).
    String values are JSON-escaped for YAML safety."""
    marker_dir = folder_path / '.tropo-studio'
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker_path = marker_dir / '.tropo-folder.md'
    body_name = folder_name.replace('`', "'").replace('\n', ' ')
    content = f"""---
uid: {uid}
type: project
status: active
title: {_yaml_str(folder_name)}
description: {_yaml_str("Imported folder governed by Tropo.")}
owner: {TOOL_NAME}-v{TOOL_VERSION}
stage: build
state: active
lifecycle: standing
source_folder_name: {_yaml_str(folder_name)}
original_path: {_yaml_str(original_path)}
governance: {governance}
member_of:
  - {_yaml_str(parent_member)}
created: {now_date()}
created_by: {TOOL_NAME}-v{TOOL_VERSION}
modified: {now_date()}
modified_by: {TOOL_NAME}-v{TOOL_VERSION}
schema_version: 1
---

# {body_name} — Tropo Folder Marker

This folder is governed by Tropo. Files inside are members of this folder-project.
Sidecars live in `.tropo-studio/` alongside this marker.
"""
    marker_path.write_text(content)
    return uid


# ==========================================================================
# Folder-marker MIRROR — v1.28.0 Stream B per arch-spec 5a89297a §3.5.5 Amendment 1 v0.5
# ==========================================================================

def _build_mirror_members_section(studio_root, folder_uid):
    """Rebuild the ## Members section by querying vault/00-index.jsonl for all entries
    whose member_of: contains <folder_uid> AND type in {external-artifact, working-copy}.

    Per arch-spec §3.5.5 Amendment 1 v0.5 (Members section mechanics — closes
    sa.cold-boot-007 B3): rebuild on every create-sidecar invocation that touches
    this folder. Idempotent. Survives deletions naturally.

    Order: by `created:` ascending (stable rendering across rebuilds).
    """
    index_path = studio_root / VAULT_INDEX_RELPATH
    if not index_path.exists():
        return "\n## Members\n\n(No members yet; index will populate as sidecars are authored.)\n"

    members = []
    try:
        with index_path.open('r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rtype = row.get('type')
                if rtype not in ('external-artifact', 'working-copy'):
                    continue
                member_of = row.get('member_of', []) or []
                if folder_uid not in member_of:
                    continue
                members.append({
                    'uid': row.get('uid', ''),
                    'title': row.get('title', '(untitled)'),
                    'type': rtype,
                    'created': row.get('created', ''),
                })
    except OSError:
        return "\n## Members\n\n(Index read failed; will rebuild on next create-sidecar.)\n"

    members.sort(key=lambda m: (m.get('created') or '', m.get('uid') or ''))

    if not members:
        return "\n## Members\n\n(No governed members yet.)\n"

    lines = ["\n## Members\n", "| UID | Title | Type |", "|---|---|---|"]
    for m in members:
        uid = m['uid']
        title = m['title'].replace('|', '\\|')
        lines.append(f"| [{uid}]({uid}.md) | {title} | {m['type']} |")
    return "\n".join(lines) + "\n"


def write_folder_mirror(studio_root, folder_uid, folder_name, original_path,
                        folder_marker_path_rel,
                        parent_member=TROPO_WORK_L0_UID, governance='tier-1-sidecar'):
    """Author a vault-resident folder-marker MIRROR at vault/files/<folder-uid>.md.

    Per arch-spec 5a89297a §3.5.5 Amendment 1 v0.5 (closes "I'm blind without it" gap):
    every folder governed by Tropo gets a vault mirror co-written with the on-disk
    marker; mirror appears in tropo-nav from the moment the first sidecar lands.

    Ordered-write protocol (v0.5 closes sa.skeptic-008 P1-1 + sa.cold-boot-007 B2):
    - Write to vault/files/<uid>.md.tmp first (NOT visible to readers)
    - Caller atomic-renames .tmp → .md after the on-disk marker write succeeds
    - On any failure, caller deletes the .tmp (best-effort cleanup)
    - Reconciler detects orphaned .tmp on next pass per §3.8 folder-mirror-orphan-state event

    Returns the path to the .tmp file (NOT the final mirror path).
    The caller is responsible for the atomic-rename step.
    """
    mirror_path = studio_root / 'vault' / 'files' / f'{folder_uid}.md'
    mirror_tmp = studio_root / 'vault' / 'files' / f'{folder_uid}.md.tmp'
    mirror_path.parent.mkdir(parents=True, exist_ok=True)

    body_name = folder_name.replace('`', "'").replace('\n', ' ')
    members_section = _build_mirror_members_section(studio_root, folder_uid)
    members_section_quoted = members_section  # already markdown

    content = f"""---
uid: {folder_uid}
type: project
status: active
title: {_yaml_str(folder_name)}
description: {_yaml_str("Imported folder governed by Tropo (vault-resident mirror of the on-disk .tropo-folder.md).")}
owner: {TOOL_NAME}-v{TOOL_VERSION}
stage: build
state: active
lifecycle: standing
source_folder_name: {_yaml_str(folder_name)}
original_path: {_yaml_str(original_path)}
governance: {governance}
mirror_of: {folder_uid}
folder_marker_path: {_yaml_str(folder_marker_path_rel)}
member_of:
  - {_yaml_str(parent_member)}
created: {now_date()}
created_by: {TOOL_NAME}-v{TOOL_VERSION}
modified: {now_date()}
modified_by: {TOOL_NAME}-v{TOOL_VERSION}
schema_version: 1
---

# {body_name} — Tropo Folder (vault mirror)

This entry is the vault-resident MIRROR of the on-disk folder-marker at
`{folder_marker_path_rel}`. The two files share the same UID and represent
a single governed entity with two on-disk representations:

- On-disk marker (portable; travels with the folder if moved)
- Vault mirror (this file; queryable via the vault index + tropo-nav)

Per arch-spec [5a89297a v0.5](5a89297a.md) §3.5.5 Amendment 1 + §3.8
folder-mirror UID-duplication sanctioned exception.

{members_section_quoted}
*Mirror authored by `{TOOL_NAME}` v{TOOL_VERSION}. Regenerable via
`tropo-backfill-styles.py --folder-markers` if lost.*
"""
    mirror_tmp.write_text(content)
    return mirror_tmp, mirror_path


def append_projection_index_row(studio_root, uid, title, member_of_uid,
                                source_filename, source_relpath, description=''):
    """Append a vault/00-index.jsonl row for an external-artifact projection.

    v1.0.3 in-stream micro-amendment (v0.5.1 — surfaced by Stream B smoke-test 2026-05-14):
    extends §3.10 check 4 inline-sync to type:external-artifact projections. Without this,
    the folder mirror's ## Members section is empty on first-touch (closes the load-bearing
    UX promise of v1.28.0 — "every folder navigable from the moment the first sidecar lands").

    Idempotent: skips if a row with this UID already exists.
    Schema matches rebuild-index.py output so re-runs don't replace inconsistent fields.
    """
    index_path = studio_root / VAULT_INDEX_RELPATH
    if not index_path.exists():
        return  # First-gen Studio; rebuild-index will catch

    # Idempotency: scan for existing UID row
    try:
        with index_path.open('r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get('uid') == uid:
                    return
    except OSError:
        return  # don't block create-sidecar on index read failure

    row = {
        'uid': uid,
        'type': 'external-artifact',
        'title': title,
        'description': description,
        'state': 'active',
        'status': 'active',
        'owner': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'governance': 'tier-1-sidecar',
        'source_filename': source_filename,
        'source_path': source_relpath,
        'original_path': source_relpath,
        'member_of': [member_of_uid],
        'created': now_date(),
        'modified': now_date(),
        'created_by': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'modified_by': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'schema_version': 2,
        'extraction_scope': 'external',
        'file_ext': 'md',
    }
    with index_path.open('a') as f:
        f.write(json.dumps(row, separators=(',', ':')) + '\n')
        f.flush()
        os.fsync(f.fileno())


def append_folder_mirror_index_row(studio_root, folder_uid, folder_name, original_path,
                                   folder_marker_path_rel,
                                   parent_member=TROPO_WORK_L0_UID,
                                   governance='tier-1-sidecar'):
    """Append a vault/00-index.jsonl row for a folder-marker mirror.

    Per arch-spec §3.10 check 4 (v0.5 widened to include type:project): every
    folder-marker mirror authored by create-sidecar MUST have an index row at
    end of execution. Closes the fa026415-class index-sync defect for folder-markers.

    Schema matches what rebuild-index.py emits so re-runs don't replace inconsistent fields.
    Skips silently if index doesn't exist (first-gen Studio; rebuild-index will catch).
    """
    index_path = studio_root / VAULT_INDEX_RELPATH
    if not index_path.exists():
        return

    # If the row already exists for this UID, skip (idempotent on retro-fill paths).
    # Reading the whole index is cheap relative to the index-corruption risk of dup rows.
    try:
        with index_path.open('r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get('uid') == folder_uid:
                    return  # already indexed
    except OSError:
        return  # don't block create-sidecar on index read failure

    row = {
        'uid': folder_uid,
        'type': 'project',
        'title': folder_name,
        'description': 'Imported folder governed by Tropo (vault-resident mirror of the on-disk .tropo-folder.md).',
        'state': 'active',
        'status': 'active',
        'stage': 'build',
        'owner': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'lifecycle': 'standing',
        'governance': governance,
        'source_folder_name': folder_name,
        'original_path': original_path,
        'mirror_of': folder_uid,
        'folder_marker_path': folder_marker_path_rel,
        'member_of': [parent_member],
        'created': now_date(),
        'modified': now_date(),
        'created_by': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'modified_by': f'{TOOL_NAME}-v{TOOL_VERSION}',
        'schema_version': 2,
        'extraction_scope': 'argo-private',
        'tags': ['folder-marker-mirror', 'tropo-work', 'import-walker-authored'],
        'file_ext': 'md',
    }
    with index_path.open('a') as f:
        f.write(json.dumps(row, separators=(',', ':')) + '\n')
        f.flush()
        os.fsync(f.fileno())


def rebuild_folder_mirror(studio_root, folder_uid, folder_name, original_path,
                          folder_marker_path_rel,
                          parent_member=TROPO_WORK_L0_UID, governance='tier-1-sidecar'):
    """Rebuild the ## Members section of an existing folder mirror.

    Called when create-sidecar adds a new sidecar to a folder that already has a
    vault mirror — the Members section is registry-rebuilt to include the new sidecar.

    Idempotent. Survives deletions naturally per arch-spec §3.5.5 Amendment 1 v0.5.

    The mirror's frontmatter is preserved; only the ## Members section is regenerated.
    """
    mirror_path = studio_root / 'vault' / 'files' / f'{folder_uid}.md'
    if not mirror_path.exists():
        # Retro-fill path: mirror doesn't exist; caller should invoke write_folder_mirror.
        return False

    text = mirror_path.read_text()
    new_members = _build_mirror_members_section(studio_root, folder_uid)

    # Replace existing ## Members section (between "## Members" header and the next "##" or EOF)
    # OR insert before the closing italics footer if no Members section yet.
    pattern_members = re.compile(r'\n## Members\n.*?(?=\n##|\n\*Mirror authored|\Z)', re.DOTALL)
    if pattern_members.search(text):
        text = pattern_members.sub('\n' + new_members.lstrip('\n').rstrip() + '\n', text)
    else:
        # Insert before the closing italics footer
        footer_anchor = '*Mirror authored by'
        if footer_anchor in text:
            text = text.replace(footer_anchor, new_members.rstrip() + '\n\n' + footer_anchor)
        else:
            text = text + '\n' + new_members

    # Update modified date
    text = re.sub(r'^modified: \S+', f'modified: {now_date()}', text, flags=re.MULTILINE)
    text = re.sub(r'^modified_by: \S+', f'modified_by: {TOOL_NAME}-v{TOOL_VERSION}', text, flags=re.MULTILINE)

    mirror_path.write_text(text)
    return True



def _serialize_original_styles_yaml(styles_dict):
    """Render the original_styles dict as a YAML block for projection frontmatter.

    Per arch-spec 5a89297a §3.4 schema. Output is indented to match the surrounding
    frontmatter at indent=2 (per Mike-A55 vault rebuild regex requirement memory pin).
    """
    lines = ['original_styles:']
    page = styles_dict.get('page', {})
    lines.append('  page:')
    lines.append(f'    width_dxa: {page.get("width_dxa", 12240)}')
    lines.append(f'    height_dxa: {page.get("height_dxa", 15840)}')
    lines.append(f'    orientation: {_yaml_str(page.get("orientation", "portrait"))}')
    lines.append('    margins_dxa:')
    margins = page.get('margins_dxa', {})
    for k in ('top', 'bottom', 'left', 'right'):
        lines.append(f'      {k}: {margins.get(k, 1440)}')
    df = styles_dict.get('default_font', {})
    lines.append('  default_font:')
    lines.append(f'    family: {_yaml_str(df.get("family", "Calibri"))}')
    lines.append(f'    size_half_pt: {df.get("size_half_pt", 22)}')
    lines.append(f'    color: {_yaml_str(df.get("color", "000000"))}')
    theme = styles_dict.get('theme', {})
    lines.append('  theme:')
    lines.append(f'    primary_color: {_yaml_str(theme.get("primary_color", "1F497D"))}')
    lines.append(f'    secondary_color: {_yaml_str(theme.get("secondary_color", "4F81BD"))}')
    named = styles_dict.get('named_styles') or []
    lines.append('  named_styles:')
    if not named:
        lines.append('    []')
    else:
        for s in named:
            lines.append(f'    - id: {_yaml_str(s.get("id", ""))}')
            if 'name' in s:
                lines.append(f'      name: {_yaml_str(s["name"])}')
            if 'font_family' in s:
                lines.append(f'      font_family: {_yaml_str(s["font_family"])}')
            if 'font_size_half_pt' in s:
                lines.append(f'      font_size_half_pt: {s["font_size_half_pt"]}')
            if 'bold' in s:
                lines.append(f'      bold: {"true" if s["bold"] else "false"}')
            if 'color' in s:
                lines.append(f'      color: {_yaml_str(s["color"])}')
            if 'spacing_before' in s:
                lines.append(f'      spacing_before: {s["spacing_before"]}')
            if 'spacing_after' in s:
                lines.append(f'      spacing_after: {s["spacing_after"]}')
    hf = styles_dict.get('headers_footers', {})
    lines.append('  headers_footers:')
    lines.append(f'    has_header: {"true" if hf.get("has_header") else "false"}')
    lines.append(f'    has_footer: {"true" if hf.get("has_footer") else "false"}')
    htp = hf.get('header_text_preview')
    ftp = hf.get('footer_text_preview')
    lines.append(f'    header_text_preview: {_yaml_str(htp) if htp else "null"}')
    lines.append(f'    footer_text_preview: {_yaml_str(ftp) if ftp else "null"}')
    lines.append(f'  sections_count: {styles_dict.get("sections_count", 1)}')
    sf = styles_dict.get('special_features', {})
    lines.append('  special_features:')
    lines.append(f'    has_macros: {"true" if sf.get("has_macros") else "false"}')
    lines.append(f'    has_embedded_fonts: {"true" if sf.get("has_embedded_fonts") else "false"}')
    lines.append(f'    has_custom_xml: {"true" if sf.get("has_custom_xml") else "false"}')
    lines.append(f'    has_watermark: {"true" if sf.get("has_watermark") else "false"}')
    return '\n'.join(lines)


def write_vault_projection(studio_root, uid, sidecar_relpath, source_relpath,
                          title, member_of_uid, source_filename, source_size_bytes,
                          source_mtime, source_hash, hash_function, original_path,
                          governance='tier-1-sidecar', description='',
                          original_styles=None):
    """Author a vault projection at vault/files/<uid>.md (Tier 1).

    v1.0.1 fix (sa.skeptic round-2 P0-A4): projection now carries all required
    external-artifact fields per the capsule's Required Frontmatter contract.
    Per arch-spec §C.3 the projection's source_path is relative to Studio root
    (vs sidecar's relative-to-sidecar).

    v1.0.3 (v1.28.0 per arch-spec §3.5.5 Amendment 2 v0.5): accepts optional
    `original_styles` dict (per arch-spec §3.4 schema). When provided, emitted
    as an indented YAML block in the projection frontmatter. The field is OPTIONAL
    on external-artifact.capsule v1.1; pre-v1.28.0 projections + non-Office binaries
    remain valid without it.
    """
    projection_path = studio_root / 'vault' / 'files' / f'{uid}.md'
    projection_path.parent.mkdir(parents=True, exist_ok=True)
    body_title = title.replace('`', "'").replace('\n', ' ')

    original_styles_block = ''
    if original_styles:
        original_styles_block = _serialize_original_styles_yaml(original_styles) + '\n'

    content = f"""---
uid: {uid}
type: external-artifact
status: active
title: {_yaml_str(title)}
owner: {TOOL_NAME}-v{TOOL_VERSION}
source_sidecar: {_yaml_str(sidecar_relpath)}
source_filename: {_yaml_str(source_filename)}
source_path: {_yaml_str(source_relpath)}
original_path: {_yaml_str(original_path)}
source_size_bytes: {source_size_bytes}
source_mtime: {source_mtime}
source_hash: {source_hash}
hash_function: {hash_function}
description: {_yaml_str(description)}
member_of:
  - {_yaml_str(member_of_uid)}
governance: {governance}
relations: []
extraction_scope: external
{original_styles_block}created: {now_date()}
created_by: {TOOL_NAME}-v{TOOL_VERSION}
modified: {now_date()}
modified_by: {TOOL_NAME}-v{TOOL_VERSION}
schema_version: 1
---

# {body_title} (vault projection)

**Relations**

(none yet)

**Source:** [{source_relpath}](../../{_url_quote_path(source_relpath)})
**Sidecar:** [{sidecar_relpath}](../../{_url_quote_path(sidecar_relpath)})

*Projection derived from sidecar; regenerable via `import-walker.py reconcile --apply` or `rebuild-vault.py`.*
"""
    projection_path.write_text(content)
    return projection_path


# ==========================================================================
# Audit log
# ==========================================================================

def append_journal(studio_root, event):
    """Append an event row to journal.jsonl."""
    journal_path = studio_root / JOURNAL_RELPATH
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with journal_path.open('a') as f:
        f.write(json.dumps(event) + '\n')


def make_event(action, target_uid, before=None, after=None, evidence='',
               category='routine', confidence=1.0, pattern_match=None,
               hash_function=None, applied=True, deferred_reason=None,
               run_uid='standalone', executive='standalone', trigger_path='user-invoked',
               reversible=True):
    """Compose an event row per arch-spec §C.8 schema."""
    return {
        'event_uid': generate_uid(),
        'timestamp': now_iso(),
        'run_uid': run_uid,
        'executive': executive,
        'trigger_path': trigger_path,
        'action': action,
        'reversible': reversible,
        'category': category,
        'confidence': confidence,
        'target_uid': target_uid,
        'pattern_match': pattern_match,
        'hash_function': hash_function,
        'before': before,
        'after': after,
        'evidence': evidence,
        'applied': applied,
        'applied_at': now_iso() if applied else None,
        'deferred_reason': deferred_reason,
    }


# ==========================================================================
# Categorization helpers
# ==========================================================================

def categorize_by_confidence(confidence):
    """Return category per the strict-inequality thresholds (arch-spec §C.5 Rule 2)."""
    if confidence >= THRESHOLD_ROUTINE:
        return 'routine'
    if confidence >= THRESHOLD_PATTERN:
        return 'pattern-matched'
    if confidence >= THRESHOLD_JUDGMENT:
        return 'judgment'
    return 'blocking'


# ==========================================================================
# Walk helpers
# ==========================================================================

def find_governed_folders(studio_root, patterns):
    """Yield (folder_path, marker_path) tuples for governed folders Studio-wide.

    v1.0.1 fix (sa.skeptic round-2 P0-A5): uses rglob over all .tropo-folder.md
    markers, independent of parent-chain governance. Previously this function only
    descended into folders whose ROOT-level parent was governed, missing orphan
    sub-folders authored beneath ungoverned parents. Now finds every governed
    folder regardless of parent chain. The orphan-sub-folder rule from §C.1
    (governed sub-folder requires governed parent OR vault-entity root) is
    enforced separately by check_external_artifact_typing / orphan-folder reporting,
    not by silent reconciler omission."""
    # Skip the Studio root's own .tropo-studio (institutional metadata, not folder-project)
    for marker in sorted(studio_root.rglob('.tropo-folder.md')):
        folder = marker.parent.parent  # marker is at <folder>/.tropo-studio/.tropo-folder.md
        # Skip if any ancestor path component matches an ignore pattern (kernel folders, etc.)
        skip = False
        try:
            rel_parts = folder.relative_to(studio_root).parts
        except ValueError:
            continue
        for part in rel_parts:
            if matches_ignore(part, True, patterns):
                skip = True
                break
        if skip:
            continue
        yield folder, marker


def _find_working_copies(studio_root):
    """Scan vault/files/ and return a map of projection_uid -> Path(working_copy).
    Only includes 'active' working-copies. Used by reconcile to detect if drift
    should trigger a re-versioning (re-extract)."""
    wc_map = {}
    vault_files = studio_root / 'vault' / 'files'
    if not vault_files.exists():
        return wc_map
    for p in vault_files.glob('*.md'):
        # Cheap check: working-copy files are usually small enough to parse fm
        try:
            fm = parse_frontmatter(p)
            if fm.get('type') == 'working-copy' and fm.get('state') == 'active':
                dfs = fm.get('derived_from')
                if dfs and isinstance(dfs, list) and len(dfs) > 0:
                    wc_map[dfs[0]] = p
                elif dfs and isinstance(dfs, str):
                    wc_map[dfs] = p
        except Exception:
            continue
    return wc_map


# ==========================================================================
# Commands
# ==========================================================================

def cmd_scan(args, studio_root):
    """Enumerate substrate; output UID-to-state map."""
    patterns = parse_tropoignore(studio_root)

    sidecars = []
    orphan_sources = []
    orphan_sidecars = []

    # Root-level files with sidecars in <root>/.tropo-studio/
    root_tropo_studio = studio_root / '.tropo-studio'
    root_sidecars = {}
    if root_tropo_studio.exists():
        for s in root_tropo_studio.glob('*.tropo.md'):
            source_name = s.name[:-len('.tropo.md')]
            root_sidecars[source_name] = s

    for entry in sorted(studio_root.iterdir()):
        if matches_ignore(entry.name, entry.is_dir(), patterns):
            continue
        if entry.is_file():
            if entry.name in root_sidecars:
                fm = parse_frontmatter(root_sidecars[entry.name])
                sidecars.append({
                    'sidecar_path': str(root_sidecars[entry.name].relative_to(studio_root)),
                    'source_path': str(entry.relative_to(studio_root)),
                    'uid': fm.get('uid', ''),
                    'recorded_hash': fm.get('source_hash', ''),
                    'hash_function': fm.get('hash_function', ''),
                    'governance': fm.get('governance', 'tier-1-sidecar'),
                })
            else:
                orphan_sources.append(str(entry.relative_to(studio_root)))
        elif entry.is_dir():
            marker = entry / '.tropo-studio' / '.tropo-folder.md'
            if marker.exists():
                _enumerate_governed_folder(entry, studio_root, patterns, sidecars, orphan_sources, orphan_sidecars)
            else:
                orphan_sources.append(str(entry.relative_to(studio_root)) + '/')

    result = {
        'studio_root': str(studio_root),
        'sidecars': sidecars,
        'orphan_sources': orphan_sources,
        'orphan_sidecars': orphan_sidecars,
        'counts': {
            'sidecars': len(sidecars),
            'orphan_sources': len(orphan_sources),
            'orphan_sidecars': len(orphan_sidecars),
        },
    }
    print(json.dumps(result, indent=2))


def _enumerate_governed_folder(folder_path, studio_root, patterns, sidecars, orphan_sources, orphan_sidecars):
    """Recursively enumerate sidecars + sources in a governed folder."""
    tropo_studio = folder_path / '.tropo-studio'
    existing_sidecars = {}
    if tropo_studio.exists():
        for s in tropo_studio.glob('*.tropo.md'):
            source_name = s.name[:-len('.tropo.md')]
            existing_sidecars[source_name] = s

    actual_files = {}
    for entry in folder_path.iterdir():
        if entry.name == '.tropo-studio':
            continue
        if entry.is_file() and not matches_ignore(entry.name, False, patterns):
            actual_files[entry.name] = entry
        elif entry.is_dir() and not matches_ignore(entry.name, True, patterns):
            sub_marker = entry / '.tropo-studio' / '.tropo-folder.md'
            if sub_marker.exists():
                _enumerate_governed_folder(entry, studio_root, patterns, sidecars, orphan_sources, orphan_sidecars)
            else:
                orphan_sources.append(str(entry.relative_to(studio_root)) + '/')

    # Match sidecars to sources
    for name, file_path in actual_files.items():
        if name in existing_sidecars:
            fm = parse_frontmatter(existing_sidecars[name])
            sidecars.append({
                'sidecar_path': str(existing_sidecars[name].relative_to(studio_root)),
                'source_path': str(file_path.relative_to(studio_root)),
                'uid': fm.get('uid', ''),
                'recorded_hash': fm.get('source_hash', ''),
                'hash_function': fm.get('hash_function', ''),
                'governance': fm.get('governance', 'tier-1-sidecar'),
            })
        else:
            orphan_sources.append(str(file_path.relative_to(studio_root)))

    # Sidecars with missing sources
    for name, sidecar_path in existing_sidecars.items():
        if name not in actual_files:
            fm = parse_frontmatter(sidecar_path)
            orphan_sidecars.append({
                'sidecar_path': str(sidecar_path.relative_to(studio_root)),
                'recorded_uid': fm.get('uid', ''),
                'recorded_source': fm.get('source_filename', name),
            })


def cmd_create_sidecar(args, studio_root):
    """Author sidecar + folder marker + vault mirror + vault projection for a single source file.

    v1.0.3 (v1.28.0 per arch-spec 5a89297a §3.5.5 v0.5):
    - Amendment 1: co-write folder-marker MIRROR at vault/files/<folder-uid>.md via
      ordered-write protocol (mirror.tmp → marker write → atomic-rename → index sync).
      Mirror appears in tropo-nav from the moment the first sidecar lands.
    - Amendment 2: populate `original_styles:` on projection for .docx files via the
      shared library function office_styles.extract_office_styles(). Failure modes:
      style extraction fails on .docx → log via journal + STDERR + omit field;
      do NOT fail create-sidecar.
    """
    source_path = Path(args.source).resolve()
    if not source_path.exists():
        raise SystemExit(f"Source file not found: {source_path}")
    if not source_path.is_file():
        raise SystemExit(f"Source is not a regular file: {source_path}")

    try:
        rel_to_root = source_path.relative_to(studio_root)
    except ValueError:
        raise SystemExit(f"Source file is not inside Studio root: {source_path}")

    parent_folder = source_path.parent
    tropo_studio = parent_folder / '.tropo-studio'
    sidecar_path = tropo_studio / f'{source_path.name}.tropo.md'

    if sidecar_path.exists():
        print(f"Sidecar already exists: {sidecar_path}", file=sys.stderr)
        sys.exit(0)

    tropo_studio.mkdir(parents=True, exist_ok=True)

    # Folder marker + vault mirror: only for non-root folders. Studio root is the
    # install context, not a folder-project; root-level sidecars use TROPO_WORK_L0_UID
    # as parent member (no on-disk marker, no mirror; the root project is implicit).
    folder_mirror_action = None  # one of: None / 'authored' / 'retro-filled' / 'rebuilt-members'
    if parent_folder == studio_root:
        folder_uid = TROPO_WORK_L0_UID
    else:
        marker_path = tropo_studio / '.tropo-folder.md'
        marker_rel = str(marker_path.relative_to(studio_root))
        folder_rel = str(parent_folder.relative_to(studio_root))

        if not marker_path.exists():
            # Fresh import: mint UID + author marker + mirror (ordered-write protocol)
            folder_uid = generate_uid()
            mirror_path = studio_root / 'vault' / 'files' / f'{folder_uid}.md'
            mirror_tmp = None
            try:
                # Step 1: write mirror to .tmp (NOT visible to readers)
                mirror_tmp, mirror_final = write_folder_mirror(
                    studio_root=studio_root,
                    folder_uid=folder_uid,
                    folder_name=parent_folder.name,
                    original_path=folder_rel,
                    folder_marker_path_rel=marker_rel,
                )
                # Step 2: write on-disk marker (atomic per single-write semantics)
                write_folder_marker(parent_folder, folder_uid, parent_folder.name, folder_rel)
                # Step 3: atomic-rename .tmp → .md (POSIX/NTFS atomic)
                os.replace(mirror_tmp, mirror_final)
                # Step 4: inline index append per §3.10 check 4 v0.5 widening
                append_folder_mirror_index_row(
                    studio_root=studio_root,
                    folder_uid=folder_uid,
                    folder_name=parent_folder.name,
                    original_path=folder_rel,
                    folder_marker_path_rel=marker_rel,
                )
                folder_mirror_action = 'authored'
                print(f"Authored folder marker: {marker_path} (uid: {folder_uid})", file=sys.stderr)
                print(f"Authored folder mirror: vault/files/{folder_uid}.md", file=sys.stderr)
            except Exception as e:
                # Ordered-write cleanup: delete the .tmp file if it exists
                if mirror_tmp and Path(mirror_tmp).exists():
                    try:
                        Path(mirror_tmp).unlink()
                    except OSError:
                        pass
                raise SystemExit(
                    f"Folder mirror co-write failed: {e}. "
                    f"Partial state may exist; reconciler will detect on next pass per "
                    f"arch-spec §3.8 folder-mirror-orphan-state event."
                )
        else:
            # Marker exists. Resolve UID + handle retro-fill or members-refresh.
            fm = parse_frontmatter(marker_path)
            folder_uid = fm.get('uid', generate_uid())
            mirror_path = studio_root / 'vault' / 'files' / f'{folder_uid}.md'

            if not mirror_path.exists():
                # Retro-fill: marker exists but no vault mirror (pre-v0.4 import OR
                # mid-write process-death recovery). Per arch-spec §3.5.5 Amendment 1 v0.5
                # retro-fill semantics: author mirror using existing UID.
                mirror_tmp = None
                try:
                    mirror_tmp, mirror_final = write_folder_mirror(
                        studio_root=studio_root,
                        folder_uid=folder_uid,
                        folder_name=parent_folder.name,
                        original_path=folder_rel,
                        folder_marker_path_rel=marker_rel,
                    )
                    os.replace(mirror_tmp, mirror_final)
                    append_folder_mirror_index_row(
                        studio_root=studio_root,
                        folder_uid=folder_uid,
                        folder_name=parent_folder.name,
                        original_path=folder_rel,
                        folder_marker_path_rel=marker_rel,
                    )
                    folder_mirror_action = 'retro-filled'
                    print(f"Retro-filled folder mirror: vault/files/{folder_uid}.md (existing marker UID)", file=sys.stderr)
                except Exception as e:
                    if mirror_tmp and Path(mirror_tmp).exists():
                        try:
                            Path(mirror_tmp).unlink()
                        except OSError:
                            pass
                    print(f"WARN: retro-fill of folder mirror failed: {e}", file=sys.stderr)
            else:
                # Marker + mirror both exist. ## Members section rebuild happens AFTER
                # the sidecar+projection are authored (so the new member is in the index).
                folder_mirror_action = 'rebuilt-members'

    # Compute hash + write sidecar
    source_hash, hash_function = compute_hash(source_path)
    stat = source_path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    uid = generate_uid()

    source_rel_to_sidecar = f"../{source_path.name}"
    source_rel_to_root = str(rel_to_root)

    # Auto-extract description from Office-binary core.xml (dc:description → dc:subject).
    description = _extract_office_description(source_path) or ''

    # Style extraction at import time per arch-spec §3.5.5 Amendment 2 v0.5.
    # Caller resolves to absolute Path before calling (closes sa.cold-boot-007 X3).
    # v1.28.0 scope: .docx only. Non-.docx or extraction-failure → None (field omitted).
    original_styles = None
    style_extraction_skipped_reason = None
    if source_path.suffix.lower() == '.docx':
        try:
            original_styles = office_styles.extract_office_styles(source_path)
            if original_styles is None:
                style_extraction_skipped_reason = 'recognized_docx_but_extraction_returned_none'
        except Exception as e:
            style_extraction_skipped_reason = f'extraction_exception: {type(e).__name__}: {e}'
            original_styles = None

    write_sidecar(
        sidecar_path=sidecar_path,
        uid=uid,
        source_filename=source_path.name,
        source_path_rel=source_rel_to_sidecar,
        original_path=source_rel_to_root,
        size_bytes=stat.st_size,
        mtime_iso=mtime_iso,
        source_hash=source_hash,
        hash_function=hash_function,
        folder_uid=folder_uid,
        description=description,
    )

    # Vault projection — pass full sidecar metadata per arch-spec §C.3 + capsule v1.0.1.
    # v1.0.3: pass original_styles dict if extracted (None otherwise; field is optional).
    sidecar_rel = str(sidecar_path.relative_to(studio_root))
    write_vault_projection(
        studio_root=studio_root,
        uid=uid,
        sidecar_relpath=sidecar_rel,
        source_relpath=source_rel_to_root,
        title=source_path.name,
        member_of_uid=folder_uid,
        source_filename=source_path.name,
        source_size_bytes=stat.st_size,
        source_mtime=mtime_iso,
        source_hash=source_hash,
        hash_function=hash_function,
        original_path=source_rel_to_root,
        description=description,
        original_styles=original_styles,
    )

    # Inline-sync the projection row into vault/00-index.jsonl per v0.5.1 in-stream
    # micro-amendment (Stream B smoke-test surfaced UX gap 2026-05-14): without inline
    # sync, the folder mirror's ## Members section is empty on first-touch.
    append_projection_index_row(
        studio_root=studio_root,
        uid=uid,
        title=source_path.name,
        member_of_uid=folder_uid,
        source_filename=source_path.name,
        source_relpath=source_rel_to_root,
        description=description,
    )

    # If folder has a mirror, rebuild its ## Members section to include this new sidecar.
    # Now that the projection is in the index, the registry walk picks it up.
    # (For 'authored' + 'retro-filled' paths: the mirror was written BEFORE the projection
    # landed in the index per ordered-write protocol; refresh now so first-touch Members is correct.)
    if folder_mirror_action in ('authored', 'retro-filled', 'rebuilt-members') and folder_uid != TROPO_WORK_L0_UID:
        folder_rel = str(parent_folder.relative_to(studio_root))
        marker_rel = str((parent_folder / '.tropo-studio' / '.tropo-folder.md').relative_to(studio_root))
        rebuild_folder_mirror(
            studio_root=studio_root,
            folder_uid=folder_uid,
            folder_name=parent_folder.name,
            original_path=folder_rel,
            folder_marker_path_rel=marker_rel,
        )

    # Style-extraction-skipped journal event (v0.5 per arch-spec §3.5.5 Amendment 2 +
    # closes sa.cold-boot-007 A1 "log" surface ambiguity — journal + STDERR; NOT ops.md).
    if style_extraction_skipped_reason:
        append_journal(studio_root, make_event(
            action='style_extraction_skipped',
            target_uid=uid,
            after={'projection_uid': uid, 'source_path': source_rel_to_root,
                   'failure_reason': style_extraction_skipped_reason},
            evidence=f'office_styles.extract_office_styles() failed for {source_rel_to_root}: {style_extraction_skipped_reason}',
            category='routine',
            confidence=1.0,
            hash_function=hash_function,
            run_uid=args.run_uid or 'cli-standalone',
            executive=args.executive or 'cli-user',
        ))
        print(f"WARN: style_extraction_skipped: {uid}: {style_extraction_skipped_reason}", file=sys.stderr)

    # Audit log (the standard create-sidecar event)
    append_journal(studio_root, make_event(
        action='create_sidecar',
        target_uid=uid,
        after={'path': source_rel_to_root, 'hash': source_hash,
               'folder_uid': folder_uid, 'folder_mirror_action': folder_mirror_action,
               'original_styles_populated': original_styles is not None},
        evidence=f'create-sidecar invoked via CLI for {source_rel_to_root}',
        category='routine',
        confidence=1.0,
        hash_function=hash_function,
        run_uid=args.run_uid or 'cli-standalone',
        executive=args.executive or 'cli-user',
    ))

    print(f"Sidecar created: {sidecar_path} (uid: {uid}, hash_function: {hash_function})")
    print(f"Projection:    vault/files/{uid}.md", file=sys.stderr)
    if original_styles is not None:
        ns_count = len(original_styles.get('named_styles', []) or [])
        print(f"Original styles: populated ({ns_count} named styles)", file=sys.stderr)


def cmd_reconcile(args, studio_root):
    """Full reconciliation pass."""
    apply_writes = args.apply
    write_journal = args.write_journal or args.apply

    if apply_writes:
        with ReconcilerLock(studio_root):
            _do_reconcile(studio_root, apply_writes=True, write_journal=write_journal,
                          run_uid=args.run_uid or generate_uid(),
                          executive=args.executive or 'cli-standalone')
    else:
        _do_reconcile(studio_root, apply_writes=False, write_journal=False,
                      run_uid='dry-run', executive='cli-standalone')


def _do_reconcile(studio_root, apply_writes, write_journal, run_uid, executive):
    """Core reconcile logic."""
    started_at = time.time()
    patterns = parse_tropoignore(studio_root)

    wc_map = _find_working_copies(studio_root)
    events = []

    # Pass 1: root-level files (Studio root isn't itself a folder-project;
    # sidecars for root-level files live at <root>/.tropo-studio/<filename>.tropo.md)
    _detect_deltas_at_root(studio_root, patterns, events, wc_map)

    # Pass 2: governed folders (recursive)
    for folder, marker in find_governed_folders(studio_root, patterns):
        _detect_deltas_in_folder(folder, studio_root, patterns, events, wc_map)

    # Categorize + assign confidence per arch-spec §C.5 Rule 6
    # Application happens for routine + pattern-matched events
    applied_count = 0
    deferred_count = 0

    for event in events:
        category = categorize_by_confidence(event['confidence'])
        event['category'] = category

        if apply_writes and category in ('routine', 'pattern-matched'):
            success, err = _apply_event(studio_root, event, run_uid, executive)
            event['applied'] = success
            event['applied_at'] = now_iso() if success else None
            event['deferred_reason'] = err
            if success:
                applied_count += 1
            else:
                deferred_count += 1
        else:
            event['applied'] = False
            event['applied_at'] = None
            event['deferred_reason'] = 'dry-run' if not apply_writes else 'category-deferred'
            deferred_count += 1

        if write_journal:
            append_journal(studio_root, _event_to_journal_row(event, run_uid, executive))

    duration_ms = int((time.time() - started_at) * 1000)
    summary = {
        'run_uid': run_uid,
        'executive': executive,
        'studio_root': str(studio_root),
        'apply_writes': apply_writes,
        'write_journal': write_journal,
        'duration_ms': duration_ms,
        'total_events_after_pattern_match': len(events),
        'events_applied': applied_count,
        'events_deferred': deferred_count,
        'events_by_category': {
            'routine': sum(1 for e in events if e['category'] == 'routine'),
            'pattern_matched': sum(1 for e in events if e['category'] == 'pattern-matched'),
            'judgment': sum(1 for e in events if e['category'] == 'judgment'),
            'blocking': sum(1 for e in events if e['category'] == 'blocking'),
        },
        'events': events,
    }
    print(json.dumps(summary, indent=2))


def _detect_deltas_at_root(studio_root, patterns, events, wc_map=None):
    """Detect deltas for root-level files. Root isn't a folder-project;
    sidecars live at <root>/.tropo-studio/<filename>.tropo.md."""
    wc_map = wc_map or {}
    tropo_studio = studio_root / '.tropo-studio'
    existing_sidecars = {}
    if tropo_studio.exists():
        for s in tropo_studio.glob('*.tropo.md'):
            source_name = s.name[:-len('.tropo.md')]
            existing_sidecars[source_name] = s

    # Root-level files (not directories, not ignored)
    actual_files = {}
    for entry in studio_root.iterdir():
        if entry.is_file() and not matches_ignore(entry.name, entry.is_dir(), patterns):
            actual_files[entry.name] = entry

    # New uncompanioned files at root
    for name, fp in actual_files.items():
        if name not in existing_sidecars:
            events.append({
                'type': 'new-uncompanioned-file',
                'path': str(fp.relative_to(studio_root)),
                'folder_path': '.',
                'source_filename': name,
                'confidence': 0.97,
                'action': 'create_sidecar',
                'evidence': f'Root-level file {name} lacks sidecar; auto-index.',
            })

    # Orphan sidecars at root
    for name, sidecar_path in existing_sidecars.items():
        if name not in actual_files:
            fm = parse_frontmatter(sidecar_path)
            events.append({
                'type': 'orphan-sidecar',
                'sidecar_path': str(sidecar_path.relative_to(studio_root)),
                'recorded_uid': fm.get('uid', ''),
                'recorded_source': fm.get('source_filename', name),
                'confidence': 0.40,
                'action': 'surface_to_user',
                'evidence': f'Root-level sidecar {sidecar_path.name} has no source file; user resolution.',
            })

    # Content-change for root-level files
    for name, fp in actual_files.items():
        if name in existing_sidecars:
            fm = parse_frontmatter(existing_sidecars[name])
            recorded_hash = fm.get('source_hash', '')
            recorded_fn = fm.get('hash_function', 'sha256')
            if not recorded_hash:
                continue
            current_hash, current_fn = compute_hash(fp)
            if current_hash != recorded_hash:
                uid = fm.get('uid', '')
                wc_path = wc_map.get(uid)
                action = 'update_sidecar_metadata'
                confidence = 0.96
                evidence = f'Hash drift on root-level {name}.'

                if wc_path and fp.suffix.lower() == '.docx':
                    wc_fm = parse_frontmatter(wc_path)
                    # Heuristic for agent edits: modified > created
                    if wc_fm.get('modified') != wc_fm.get('created'):
                        action = 'judgment'
                        confidence = 0.45  # requires human resolution
                        evidence = f'Conflict: Word edit drifted on {name} AND vault working-copy was edited by agent.'
                    else:
                        action = 'reversion'
                        confidence = 0.98  # highly routine: flow Word edit into vault
                        evidence = f'Word edit detected on {name}; auto-reversioning vault working-copy.'

                events.append({
                    'type': 'content-change',
                    'path': str(fp.relative_to(studio_root)),
                    'sidecar_path': str(existing_sidecars[name].relative_to(studio_root)),
                    'uid': uid,
                    'old_hash': recorded_hash,
                    'new_hash': current_hash,
                    'old_hash_function': recorded_fn,
                    'new_hash_function': current_fn,
                    'confidence': confidence,
                    'action': action,
                    'evidence': evidence,
                })


def _detect_deltas_in_folder(folder_path, studio_root, patterns, events, wc_map=None):
    """Detect substrate deltas in a governed folder."""
    wc_map = wc_map or {}
    tropo_studio = folder_path / '.tropo-studio'
    existing_sidecars = {}
    if tropo_studio.exists():
        for s in tropo_studio.glob('*.tropo.md'):
            source_name = s.name[:-len('.tropo.md')]
            existing_sidecars[source_name] = s

    actual_files = {}
    for entry in folder_path.iterdir():
        if entry.name == '.tropo-studio':
            continue
        if entry.is_file() and not matches_ignore(entry.name, entry.is_dir(), patterns):
            actual_files[entry.name] = entry

    # New uncompanioned files
    for name, fp in actual_files.items():
        if name not in existing_sidecars:
            events.append({
                'type': 'new-uncompanioned-file',
                'path': str(fp.relative_to(studio_root)),
                'folder_path': str(folder_path.relative_to(studio_root)) if folder_path != studio_root else '.',
                'source_filename': name,
                'confidence': 0.97,
                'action': 'create_sidecar',
                'evidence': f'File present in governed folder {folder_path.name}/ without sidecar; auto-index.',
            })

    # Orphan sidecars
    for name, sidecar_path in existing_sidecars.items():
        if name not in actual_files:
            fm = parse_frontmatter(sidecar_path)
            events.append({
                'type': 'orphan-sidecar',
                'sidecar_path': str(sidecar_path.relative_to(studio_root)),
                'recorded_uid': fm.get('uid', ''),
                'recorded_source': fm.get('source_filename', name),
                'confidence': 0.40,
                'action': 'surface_to_user',
                'evidence': f'Sidecar {sidecar_path.name} has no source file; could be deleted source, moved file, or stale sidecar.',
            })

    # Content-change detection
    for name, fp in actual_files.items():
        if name in existing_sidecars:
            fm = parse_frontmatter(existing_sidecars[name])
            recorded_hash = fm.get('source_hash', '')
            recorded_fn = fm.get('hash_function', 'sha256')
            if not recorded_hash:
                continue
            current_hash, current_fn = compute_hash(fp)
            if current_hash != recorded_hash:
                uid = fm.get('uid', '')
                wc_path = wc_map.get(uid)
                action = 'update_sidecar_metadata'
                confidence = 0.96
                evidence = f'Hash drift on {fp.name}: {recorded_fn}/{recorded_hash[:12]}... → {current_fn}/{current_hash[:12]}...'

                if wc_path and fp.suffix.lower() == '.docx':
                    wc_fm = parse_frontmatter(wc_path)
                    if wc_fm.get('modified') != wc_fm.get('created'):
                        action = 'judgment'
                        confidence = 0.45
                        evidence = f'Conflict: Word edit drifted on {fp.name} AND vault working-copy was edited by agent.'
                    else:
                        action = 'reversion'
                        confidence = 0.98
                        evidence = f'Word edit detected on {fp.name}; auto-reversioning vault working-copy.'

                events.append({
                    'type': 'content-change',
                    'path': str(fp.relative_to(studio_root)),
                    'sidecar_path': str(existing_sidecars[name].relative_to(studio_root)),
                    'uid': uid,
                    'old_hash': recorded_hash,
                    'new_hash': current_hash,
                    'old_hash_function': recorded_fn,
                    'new_hash_function': current_fn,
                    'confidence': confidence,
                    'action': action,
                    'evidence': evidence,
                })


def _apply_event(studio_root, event, run_uid, executive):
    """Apply a single event. Returns (success_bool, error_message_or_None)."""
    action = event.get('action')

    try:
        if action == 'create_sidecar':
            # Reuse cmd_create_sidecar logic via direct call
            source_relpath = event.get('path')
            source_path = studio_root / source_relpath
            if not source_path.exists():
                return False, f"Source not found: {source_path}"

            parent_folder = source_path.parent
            tropo_studio = parent_folder / '.tropo-studio'
            sidecar_path = tropo_studio / f'{source_path.name}.tropo.md'
            if sidecar_path.exists():
                return True, None  # Already exists; treat as no-op success

            tropo_studio.mkdir(parents=True, exist_ok=True)
            marker_path = tropo_studio / '.tropo-folder.md'
            if not marker_path.exists():
                folder_uid = generate_uid()
                folder_rel = str(parent_folder.relative_to(studio_root)) if parent_folder != studio_root else '.'
                write_folder_marker(parent_folder, folder_uid, parent_folder.name, folder_rel)
            else:
                fm = parse_frontmatter(marker_path)
                folder_uid = fm.get('uid', generate_uid())

            source_hash, hash_function = compute_hash(source_path)
            stat = source_path.stat()
            mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            uid = generate_uid()

            write_sidecar(
                sidecar_path=sidecar_path,
                uid=uid,
                source_filename=source_path.name,
                source_path_rel=f'../{source_path.name}',
                original_path=str(source_path.relative_to(studio_root)),
                size_bytes=stat.st_size,
                mtime_iso=mtime_iso,
                source_hash=source_hash,
                hash_function=hash_function,
                folder_uid=folder_uid,
            )
            sidecar_rel = str(sidecar_path.relative_to(studio_root))
            source_rel = str(source_path.relative_to(studio_root))
            write_vault_projection(
                studio_root=studio_root,
                uid=uid,
                sidecar_relpath=sidecar_rel,
                source_relpath=source_rel,
                title=source_path.name,
                member_of_uid=folder_uid,
                source_filename=source_path.name,
                source_size_bytes=stat.st_size,
                source_mtime=mtime_iso,
                source_hash=source_hash,
                hash_function=hash_function,
                original_path=source_rel,
            )
            event['target_uid'] = uid
            event['hash_function'] = hash_function
            event['after'] = {'path': str(source_path.relative_to(studio_root)), 'hash': source_hash}
            return True, None

        elif action == 'update_sidecar_metadata':
            # Hash drift; update sidecar's source_hash + mtime
            return _apply_update_sidecar_metadata(studio_root, event)

        elif action == 'reversion':
            # Re-extract a new working-copy version using tropo-extract.py
            projection_uid = event.get('uid')
            if not projection_uid:
                return False, "Missing projection uid for reversion"

            import subprocess
            # Invoke tropo-extract --force --skip-lock
            # 561d3c75.py is the UID for tropo-extract.py per registry.
            te_path = studio_root / 'vault' / 'tools' / '561d3c75.py'
            if not te_path.exists():
                return False, f"tropo-extract tool not found at {te_path}"

            cmd = [
                sys.executable, str(te_path),
                '--projection', projection_uid,
                '--force',
                '--skip-lock',
                '--studio-root', str(studio_root),
                '--executive', executive,
                '--run-uid', run_uid,
            ]
            try:
                # Use capture_output=True to keep stdout/stderr out of our JSON summary
                proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
                # If extraction succeeded, we MUST update the sidecar's source_hash
                # so the reconciler doesn't see drift again.
                success, err = _apply_update_sidecar_metadata(studio_root, event)
                return success, err
            except subprocess.CalledProcessError as e:
                return False, f"tropo-extract failed (exit {e.returncode}): {e.stderr}"

        elif action == 'surface_to_user' or action == 'judgment':
            # No substrate write; just defer
            return False, f'{action} is deferred to executive; no auto-application'

        else:
            return False, f"Action '{action}' not implemented in v1.0"

    except (OSError, ValueError, KeyError) as e:
        return False, f"Apply error: {e}"


def _apply_update_sidecar_metadata(studio_root, event):
    """Helper to update a sidecar's recorded hash + modified fields."""
    sidecar_relpath = event.get('sidecar_path')
    new_hash = event.get('new_hash')
    new_fn = event.get('new_hash_function', 'sha256')
    if not sidecar_relpath or not new_hash:
        return False, "Missing sidecar_path or new_hash"
    sidecar_path = studio_root / sidecar_relpath
    if not sidecar_path.exists():
        return False, f"Sidecar not found: {sidecar_path}"
    text = sidecar_path.read_text()
    # Replace source_hash, hash_function, source_mtime, modified, modified_by
    new_mtime = now_iso()
    new_modified = now_date()
    # v1.0.1 fix (sa.skeptic round-2 P0-A3): anchor to line-start + use \S+ safely.
    text = re.sub(r'^source_hash: \S+', f'source_hash: {new_hash}', text, flags=re.MULTILINE)
    text = re.sub(r'^hash_function: \S+', f'hash_function: {new_fn}', text, flags=re.MULTILINE)
    text = re.sub(r'^modified: \d{4}-\d{2}-\d{2}', f'modified: {new_modified}', text, flags=re.MULTILINE)
    text = re.sub(r'^modified_by: \S+', f'modified_by: {TOOL_NAME}-v{TOOL_VERSION}', text, flags=re.MULTILINE)
    sidecar_path.write_text(text)
    return True, None


def _event_to_journal_row(event, run_uid, executive):
    """Convert an internal event dict to the journal row schema."""
    return make_event(
        action=event.get('action', 'unknown'),
        target_uid=event.get('target_uid', event.get('uid', event.get('recorded_uid', 'unknown'))),
        before=event.get('before'),
        after=event.get('after'),
        evidence=event.get('evidence', ''),
        category=event.get('category', 'judgment'),
        confidence=event.get('confidence', 0.5),
        pattern_match=event.get('pattern_match'),
        hash_function=event.get('hash_function') or event.get('new_hash_function'),
        applied=event.get('applied', False),
        deferred_reason=event.get('deferred_reason'),
        run_uid=run_uid,
        executive=executive,
        trigger_path='scheduled',
        reversible=event.get('action') not in ('mint_new_uid', 'surface_to_user'),
    )


def cmd_apply(args, studio_root):
    """Apply a single categorized event from JSON (--event or stdin)."""
    if args.event:
        event = json.loads(args.event)
    else:
        event = json.load(sys.stdin)
    success, err = _apply_event(studio_root, event,
                                run_uid=args.run_uid or 'apply-single',
                                executive=args.executive or 'cli-user')
    if success:
        append_journal(studio_root, _event_to_journal_row({**event, 'applied': True}, args.run_uid or 'apply-single', args.executive or 'cli-user'))
        print(json.dumps({'applied': True, 'event': event}, indent=2))
    else:
        print(json.dumps({'applied': False, 'error': err, 'event': event}, indent=2))
        sys.exit(2)


def cmd_promote_folder(args, studio_root):
    raise SystemExit("promote-folder is Phase 2 (v1.26.0+) scope. Not implemented in v1.25.0.")


def cmd_extract(args, studio_root):
    raise SystemExit("extract is Phase 2 (v1.26.0+) scope. Not implemented in v1.25.0.")


# ==========================================================================
# CLI
# ==========================================================================

def cmd_ingest(args, studio_root):
    """One gesture: recursively scan a source root (default 04-external-work/) and
    create a sidecar + vault projection for every NEW file. The user names no
    files — this finds everything ungoverned. Idempotent: files already governed
    (sidecar present) or matching .tropoignore / kernel-never / hidden are skipped.

    v1.70 hardening (Mike-G77 one-gesture directive 2026-06-13): the import on-ramp
    was scan + per-file create-sidecar; this collapses it to a single zero-arg call.
    Reuses cmd_create_sidecar per new file (the battle-tested path) — no duplication.
    """
    import io as _io
    import contextlib as _ctx
    import types as _types

    patterns = parse_tropoignore(studio_root)
    root_rel = getattr(args, 'root', None) or '04-external-work'
    scan_root = (studio_root / root_rel).resolve()
    if not scan_root.exists():
        raise SystemExit(f"ingest root not found: {scan_root} (relative to studio root {studio_root})")

    created, already, ignored, failed = [], [], [], []

    for dirpath, dirnames, filenames in os.walk(scan_root):
        # Prune ignored / hidden / kernel dirs in place (don't descend into
        # .tropo-studio sidecar dirs, .obsidian, .git, etc.).
        dirnames[:] = [d for d in dirnames
                       if not d.startswith('.')
                       and d not in KERNEL_INGEST_NEVER
                       and not matches_ignore(d, True, patterns)]
        for fn in sorted(filenames):
            # Skip hidden, our own sidecars, and editor lock/temp files. Office
            # writes a `~$<name>` lock file while a doc is open; those vanish when
            # the app closes, so a sidecar pointing at one is a guaranteed broken
            # handle. (v1.70 hardening: caught on the first real ingest run.)
            if (fn.startswith('.') or fn.startswith('~$') or fn.startswith('~')
                    or fn.endswith('.tmp') or fn.endswith('.tropo.md')):
                ignored.append(fn); continue
            if matches_ignore(fn, False, patterns):
                ignored.append(fn); continue
            fpath = Path(dirpath) / fn
            rel = str(fpath.relative_to(studio_root))
            sidecar = fpath.parent / '.tropo-studio' / f'{fn}.tropo.md'
            if sidecar.exists():
                already.append(rel); continue
            if getattr(args, 'dry_run', False):
                created.append(rel); continue  # preview only — no write
            # New file → sidecar it via the existing per-file path, output captured.
            one = _types.SimpleNamespace(
                source=str(fpath),
                run_uid=getattr(args, 'run_uid', None),
                executive=getattr(args, 'executive', None) or 'ingest',
            )
            buf = _io.StringIO()
            try:
                with _ctx.redirect_stdout(buf), _ctx.redirect_stderr(buf):
                    cmd_create_sidecar(one, studio_root)
                created.append(rel)
            except SystemExit as e:
                code = str(e)
                if code in ('0', 'None', ''):  # pre-filtered, but defensive
                    already.append(rel)
                else:
                    failed.append((rel, code))
            except Exception as e:  # noqa: BLE001 — one bad file must not abort the sweep
                failed.append((rel, f'{type(e).__name__}: {e}'))

    if getattr(args, 'json', False):
        print(json.dumps({
            'root': root_rel,
            'created': len(created), 'already_governed': len(already),
            'ignored': len(ignored), 'failed': len(failed),
            'created_files': created, 'failed_files': failed,
        }))
        return

    verb = 'WOULD sidecar' if getattr(args, 'dry_run', False) else 'sidecarred + projected into the vault'
    print(f"Ingest scan of {root_rel}/ complete{' (DRY RUN — no writes)' if getattr(args, 'dry_run', False) else ''}:")
    print(f"  {len(created)} new file(s) {verb}")
    print(f"  {len(already)} already governed (skipped)")
    print(f"  {len(ignored)} ignored (.tropoignore / kernel / hidden)")
    if failed:
        print(f"  {len(failed)} FAILED:")
        for f, reason in failed:
            print(f"    ! {f}: {reason}")
    for c in created:
        print(f"  + {c}")


def main():
    parser = argparse.ArgumentParser(description='Tropo import primitive walker.')
    parser.add_argument('--studio-root', default=None)
    subs = parser.add_subparsers(dest='command', required=True)

    p_scan = subs.add_parser('scan', help='Enumerate substrate; output JSON')
    p_scan.add_argument('--scope', default='full-studio')

    p_create = subs.add_parser('create-sidecar', help='Create a sidecar for a single source file')
    p_create.add_argument('--source', required=True)
    p_create.add_argument('--run-uid', default=None)
    p_create.add_argument('--executive', default=None)

    p_reconcile = subs.add_parser('reconcile', help='Full reconciliation pass')
    p_reconcile.add_argument('--scope', default='full-studio')
    p_reconcile.add_argument('--apply', action='store_true', help='Apply routine + pattern-matched events')
    p_reconcile.add_argument('--dry-run', action='store_true', help='Detect + categorize but do not apply')
    p_reconcile.add_argument('--write-journal', action='store_true', help='Append events to journal.jsonl')
    p_reconcile.add_argument('--run-uid', default=None)
    p_reconcile.add_argument('--executive', default=None)

    p_apply = subs.add_parser('apply', help='Apply a single event from JSON')
    p_apply.add_argument('--event', default=None, help='JSON event string; if absent, reads from stdin')
    p_apply.add_argument('--run-uid', default=None)
    p_apply.add_argument('--executive', default=None)

    p_promote = subs.add_parser('promote-folder', help='Tier 1 → Tier 2 upgrade (Phase 2 stub)')
    p_promote.add_argument('--folder', required=True)

    p_extract = subs.add_parser('extract', help='Three extraction modes (Phase 2 stub)')
    p_extract.add_argument('--folder', required=True)
    p_extract.add_argument('--mode', choices=['ungoverned', 'tier-1-sidecar', 'stay'], required=True)
    p_extract.add_argument('--destination', required=True)

    p_ingest = subs.add_parser('ingest',
                               help='ONE GESTURE: recursively sidecar every NEW file under a root (default 04-external-work/). No file args needed.')
    p_ingest.add_argument('--root', default='04-external-work',
                          help='Root to scan recursively (default: 04-external-work)')
    p_ingest.add_argument('--dry-run', action='store_true', help='Preview what would be sidecarred; no writes')
    p_ingest.add_argument('--json', action='store_true')
    p_ingest.add_argument('--run-uid', default=None)
    p_ingest.add_argument('--executive', default=None)

    args = parser.parse_args()
    studio_root = resolve_studio_root(args.studio_root)

    handlers = {
        'scan': cmd_scan,
        'create-sidecar': cmd_create_sidecar,
        'reconcile': cmd_reconcile,
        'apply': cmd_apply,
        'promote-folder': cmd_promote_folder,
        'extract': cmd_extract,
        'ingest': cmd_ingest,
    }
    handlers[args.command](args, studio_root)


if __name__ == '__main__':
    main()
