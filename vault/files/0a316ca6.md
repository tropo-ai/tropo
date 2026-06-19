#!/usr/bin/env python3
"""
---
uid: 0a316ca6
type: tool
name: scan-import-state.py
title: scan-import-state.py — Boot-Time Import State Scanner
description: Boot-time shallow scanner per Import Primitive Arch Spec §A.6 anomaly-driven trigger path. Walks Studio root one level deep, categorizes top-level entries as governed / orphan-source / orphan-sidecar / unindexed; writes JSON output to workspace; cost ~50ms. Triggers sa.reconciler when anomaly_detected is true.
version: 1.0.0
status: active
state: active
stage: build
schema_version: 2
extraction_scope: ship
author: argus
owner: argus
language: python
path: .tropo/scripts/scan-import-state.py
script_path: vault/tools/0a316ca6.py
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/0a316ca6.py [--output-dir <dir>]
spawnable_by:
- all-executives
destructive: 'false'
audit_required: 'false'
writes_scope:
- agents/<agent>/.tropo-capsule/workspace/import-state.md
reads_scope:
- ./*
governance_category: diagnostic
domain: Boot-time anomaly detection for the import primitive — sub-50ms shallow scan that categorizes Studio-root entries + flags whether sa.reconciler should be commissioned this session.
domain_tags:
- scan-import-state
- boot-time
- anomaly-detection
- shallow-scan
- import-primitive
- sa-reconciler-trigger
- v1.25.0-stream-b
trigger_description: "Boot-time shallow scanner for orphan/anomaly detection."
governed_by: d5e1b4a3
capsule_version: '2.5'
created: 2026-05-13
modified: 2026-05-14
created_by: argus-a60
modified_by: argus-a62
aligned_with:
- 2b49ba79
member_of:
- f1d7fe66
tags:
- tool
- python
- scan-import-state
- boot-time-scanner
- anomaly-detection
- v1.25.0-stream-b
subsystem_hub:
- 76bab75f
belt: true
belt_invocation: "python3 vault/tools/0a316ca6.py --output-dir <dir>"
belt_example: "python3 vault/tools/0a316ca6.py --output-dir agents/talos/..."
---
"""

"""scan-import-state.py — Boot-time shallow scanner for the Tropo import primitive.

Walks the Studio root one level deep and categorizes top-level entries as
governed / orphan-source / unindexed. Writes a markdown+JSON output to the
executive agent's workspace. Cost: ~50ms; no substrate writes.

Invoked at Group 3 Step 3.4.5 of agent-activation.playbook (v2.10+).
If `anomaly_detected: true` in the output, the executive commissions sa.reconciler
for the session per the anomaly-driven triggering path (Import Primitive
Architecture Specification v1.0 [vault/files/2b49ba79.md] §A.6).

Usage:
    python3 .tropo/scripts/scan-import-state.py
    python3 .tropo/scripts/scan-import-state.py --output-dir agents/argus/.tropo-capsule/workspace/
    python3 .tropo/scripts/scan-import-state.py --studio-root /path/to/argo-os/
    python3 .tropo/scripts/scan-import-state.py --json   # JSON to stdout

No third-party dependencies. Targets Python 3.8+.

Author: argus-a60
Owner: argus
Tool UID: 0a316ca6
Spec: vault/files/2b49ba79.md (Import Primitive Architecture Specification v1.0 LOCKED)
"""

import argparse
import fnmatch
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# Kernel-known directories that import-walker NEVER ingests.
# Baked into the tool in addition to .tropoignore for safety.
KERNEL_INGEST_NEVER = {
    '.tropo', '.tropo-studio', 'vault', 'agents', 'channels', 'playbooks',
    '00-tropo-nav', '01-exchange', '01-studio-inbox', 'playbook-runs',
    'recycle', 'archive', 'updates', 'shared', 'templates', 'context',
    'boards', '.git', '.svn', '.hg', '.obsidian',
}


def resolve_studio_root(arg_path=None):
    """Find Studio root: explicit arg, or walk up from cwd looking for .tropo/."""
    if arg_path:
        p = Path(arg_path).resolve()
        if (p / '.tropo').exists():
            return p
        raise SystemExit(f"--studio-root {arg_path} does not contain .tropo/ — not a Studio root")
    cwd = Path.cwd()
    for candidate in [cwd] + list(cwd.parents):
        if (candidate / '.tropo').exists():
            return candidate
    raise SystemExit("Could not find Studio root — no .tropo/ in cwd or ancestors. Use --studio-root.")


def parse_tropoignore(studio_root):
    """Read .tropoignore at Studio root; return list of patterns. Empty if file missing."""
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
    """Match an entry against .tropoignore patterns + the kernel never-ingest list."""
    if entry_name in KERNEL_INGEST_NEVER:
        return True
    for pattern in patterns:
        dir_only = pattern.endswith('/')
        stripped = pattern.rstrip('/')
        if dir_only and not is_dir:
            continue
        # Match by basename (most common case for top-level scan)
        if fnmatch.fnmatch(entry_name, stripped):
            return True
        # Pattern with path separator: match against the last segment as a fallback
        if '/' in stripped:
            base = stripped.split('/')[-1]
            if base and fnmatch.fnmatch(entry_name, base):
                return True
    return False


def categorize_entry(entry, studio_root, patterns):
    """Categorize a top-level entry. Returns one of:
        'kernel-or-ignored', 'governed-folder', 'governed-file',
        'orphan-folder', 'orphan-file'
    """
    name = entry.name
    is_dir = entry.is_dir()
    if matches_ignore(name, is_dir, patterns):
        return 'kernel-or-ignored'
    if is_dir:
        marker = entry / '.tropo-studio' / '.tropo-folder.md'
        return 'governed-folder' if marker.exists() else 'orphan-folder'
    # Top-level file
    sidecar = studio_root / '.tropo-studio' / f'{name}.tropo.md'
    return 'governed-file' if sidecar.exists() else 'orphan-file'


def scan(studio_root):
    """Perform the shallow scan. Returns a result dict per arch-spec §C.6."""
    started_at = time.time()
    patterns = parse_tropoignore(studio_root)

    counts = {
        'governed_folders': 0,
        'governed_files_at_root': 0,
        'orphan_folders': 0,
        'orphan_files': 0,
        'kernel_or_ignored': 0,
    }
    orphan_paths = []

    for entry in sorted(studio_root.iterdir()):
        cat = categorize_entry(entry, studio_root, patterns)
        if cat == 'governed-folder':
            counts['governed_folders'] += 1
        elif cat == 'governed-file':
            counts['governed_files_at_root'] += 1
        elif cat == 'orphan-folder':
            counts['orphan_folders'] += 1
            orphan_paths.append(str(entry.relative_to(studio_root)) + '/')
        elif cat == 'orphan-file':
            counts['orphan_files'] += 1
            orphan_paths.append(str(entry.relative_to(studio_root)))
        else:
            counts['kernel_or_ignored'] += 1

    duration_ms = int((time.time() - started_at) * 1000)
    orphan_total = counts['orphan_folders'] + counts['orphan_files']
    anomaly_detected = orphan_total > 0

    if anomaly_detected:
        summary = f"{orphan_total} orphan-source entries at Studio root ({counts['orphan_folders']} folders + {counts['orphan_files']} files) require reconciliation."
        recommendation = 'commission-sa-reconciler'
    else:
        summary = "No anomalies; substrate is consistent at top level."
        recommendation = 'no-action'

    return {
        'scanned_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'scope': 'studio-root-one-level',
        'duration_ms': duration_ms,
        'studio_root': str(studio_root),
        'categories': counts,
        'orphan_paths': orphan_paths,
        'anomaly_detected': anomaly_detected,
        'anomaly_summary': summary,
        'trigger_recommendation': recommendation,
    }


def write_output(result, output_dir):
    """Write the scan result as a markdown file with frontmatter + JSON body."""
    output_path = Path(output_dir) / 'import-state.md'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""---
generated_by: scan-import-state.py-v1.0
generated_at: {result['scanned_at']}
schema_version: 1
anomaly_detected: {str(result['anomaly_detected']).lower()}
---

# Import-State Scan Result

*Generated by `.tropo/scripts/scan-import-state.py` (UID `0a316ca6`) per agent-activation.playbook v2.10 Step 3.4.5. Boot-time shallow scan of the Studio root for import-primitive anomalies.*

## Result

```json
{json.dumps(result, indent=2)}
```

## What to do with this

- **`anomaly_detected: true`** — commission [sa.reconciler (e4af1001)](../../../../agents/sa/sa.reconciler/sa.reconciler.md) for this session with `trigger_path: anomaly` and `scope: full-studio`. The reconciler produces a structured report with categorized findings; the executive triages.
- **`anomaly_detected: false`** — no action at boot. Routine daily reconciliation runs via fleet-ops's time-driven path separately.

---

*Schema: Import Primitive Architecture Specification v1.0 §C.6.*
"""
    output_path.write_text(content)
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Boot-time shallow scanner for the Tropo import primitive.'
    )
    parser.add_argument(
        '--output-dir',
        default=None,
        help='Directory to write import-state.md output. Default: no file write; stdout only.'
    )
    parser.add_argument(
        '--studio-root',
        default=None,
        help='Studio root path. Default: auto-detect by walking up from cwd looking for .tropo/.'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Print result JSON to stdout (instead of human-readable summary).'
    )
    args = parser.parse_args()

    studio_root = resolve_studio_root(args.studio_root)
    result = scan(studio_root)

    if args.output_dir:
        output_path = write_output(result, args.output_dir)
        print(f"Scan complete in {result['duration_ms']}ms — anomaly_detected: {result['anomaly_detected']}", file=sys.stderr)
        print(f"Output: {output_path}", file=sys.stderr)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Human-readable summary
        print(f"Studio root: {studio_root}")
        print(f"Scanned in: {result['duration_ms']}ms")
        print(f"Anomaly detected: {result['anomaly_detected']}")
        print(f"\nCategories:")
        for cat, count in result['categories'].items():
            print(f"  {cat:35s} {count}")
        if result['orphan_paths']:
            print(f"\nOrphan paths ({len(result['orphan_paths'])}):")
            for p in result['orphan_paths'][:15]:
                print(f"  - {p}")
            if len(result['orphan_paths']) > 15:
                print(f"  ... and {len(result['orphan_paths']) - 15} more")

    # Always exit 0. The JSON output is the signal; non-zero would interfere with playbook flow.
    sys.exit(0)


if __name__ == '__main__':
    main()
