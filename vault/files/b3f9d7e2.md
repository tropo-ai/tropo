#!/usr/bin/env python3
"""
---
uid: b3f9d7e2
title: register-kernel — Tool
name: register-kernel
type: tool
status: active
owner: argus
domain: 'Register .tropo/ kernel files in the vault index — type: kernel entries pointing at .tropo/ paths.'
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/b3f9d7e2.py [--dry-run]
script_path: vault/tools/b3f9d7e2.py
input:
  type: object
  properties:
    dry-run:
      type: boolean
destructive: false
audit_required: false
writes_scope:
- vault/00-index.jsonl
governance_category: lifecycle
description: 'Registers all .tropo/ kernel files in the vault index. For each .md file in .tropo/, creates a vault index entry with type: kernel + kernel_type (inferred from directory: capsules→capsule, actions→action, etc.) + path (vault-relative) + scope: ship + status (from frontmatter, default ''published'') + owner: tropo + title (from H1 or frontmatter). Does NOT copy files into vault/files/ — files stay in .tropo/, vault entry points at them via path: field. Companion to rebuild-vault.py.'
domain_tags:
- kernel-registration
- ship-scope
- vault-index
- type-kernel
trigger_description: Reach for this when kernel files have been added/removed/renamed under .tropo/ and the vault index needs to reflect that change. Companion to rebuild-vault.py — that one rebuilds entries authored at vault/files/<uid>.md; this one registers files that stay at their .tropo/ path. Run after kernel directory changes; not part of routine index rebuild. Future v1.16+ may merge these two into a single rebuild script per the Kernel Migration to Vault thesis (1fa26624).
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
- kernel-registration
- vault-index
- v1.15-stream-b
subsystem_hub:
- dbc1cbbf
---
"""

"""
Register all .tropo/ kernel files in the Vault.

For each .md file in .tropo/, creates a vault index entry with:
  - type: kernel
  - kernel_type: inferred from directory (capsules→capsule, actions→action, etc.)
  - path: vault-relative path to the file
  - scope: ship (kernel always ships)
  - status: read from the file's frontmatter, default 'published'
  - owner: tropo
  - title: read from H1 or frontmatter title
  - uid: read from frontmatter if present, generated if not

Does NOT copy files into vault/files/. The files stay in .tropo/.
The vault entry points at them via the path: field.

Usage:
    python3 .tropo/scripts/register-kernel.py [--dry-run]
"""

import json
import os
import re
import secrets
import sys

VAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_PATH = os.path.join(VAULT_ROOT, 'ledger', '00-index.jsonl')
TROPO_DIR = os.path.join(VAULT_ROOT, '.tropo')

DRY_RUN = '--dry-run' in sys.argv

# Map directory names to kernel_type values
DIR_TO_KERNEL_TYPE = {
    'capsules': 'capsule',
    'actions': 'action',
    'playbooks': 'playbook',
    'skills': 'skill',
    'templates': 'template',
    'schema': 'schema',
    'kb': 'kb',
    'scripts': 'script',
    'system': 'system',
    'platform-setup': 'system',
}


def generate_uid():
    return secrets.token_hex(4)


def parse_frontmatter(filepath):
    """Extract frontmatter fields from a markdown file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if not content.startswith('---'):
        return {}, content

    try:
        end = content.index('---', 3)
    except ValueError:
        return {}, content

    fm_text = content[3:end]
    fields = {}

    for line in fm_text.strip().split('\n'):
        if ':' not in line:
            continue
        key = line.split(':', 1)[0].strip()
        val = line.split(':', 1)[1].strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            val = val[1:-1]
        fields[key] = val

    return fields, content


def extract_title(fm, content):
    """Get title from frontmatter or first H1."""
    if 'title' in fm and fm['title']:
        return fm['title'][:100]
    if 'name' in fm and fm['name']:
        return fm['name'][:100]
    # Look for first H1
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()[:100]
    return None


def infer_kernel_type(rel_path):
    """Infer kernel_type from the directory path."""
    parts = rel_path.replace('.tropo/', '').split('/')
    if len(parts) >= 1:
        dir_name = parts[0]
        if dir_name in DIR_TO_KERNEL_TYPE:
            return DIR_TO_KERNEL_TYPE[dir_name]
    # Top-level .tropo/ files
    return 'system'


def load_existing_uids(index_path):
    """Load all existing UIDs from the index."""
    uids = set()
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    uids.add(row['uid'])
    return uids


def load_existing_paths(index_path):
    """Load all existing path values from the index."""
    paths = {}
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    if 'path' in row:
                        paths[row['path']] = row['uid']
    return paths


def main():
    existing_uids = load_existing_uids(INDEX_PATH)
    existing_paths = load_existing_paths(INDEX_PATH)

    new_entries = []
    skipped = 0
    already_registered = 0

    for root, dirs, files in os.walk(TROPO_DIR):
        # Skip migrations subdirectory (update payloads, not kernel)
        if 'migrations' in root:
            continue
        # Skip concierge (separate governance model, not a kernel primitive)
        if 'concierge' in root:
            continue

        for fname in sorted(files):
            if not fname.endswith('.md'):
                continue

            filepath = os.path.join(root, fname)
            rel_path = os.path.relpath(filepath, VAULT_ROOT)

            # Check if already registered by path
            if rel_path in existing_paths:
                already_registered += 1
                continue

            fm, content = parse_frontmatter(filepath)

            # Get or generate UID — must match ^[0-9a-f]{8}$ per core capsule validation
            uid = fm.get('uid', '')
            if not uid or len(uid) != 8 or not all(c in '0123456789abcdef' for c in uid):
                uid = generate_uid()
                while uid in existing_uids:
                    uid = generate_uid()

            if uid in existing_uids:
                # UID collision — this file might already be registered under a different path
                already_registered += 1
                continue

            title = extract_title(fm, content)
            if not title:
                title = fname.replace('.md', '').replace('-', ' ').replace('.', ' ').title()

            status = fm.get('status', 'published')
            kernel_type = infer_kernel_type(rel_path)
            created = fm.get('created', '2026-04-12')
            modified = fm.get('modified', fm.get('last_modified', '2026-04-12'))

            # Build description
            desc = fm.get('description', '')
            if not desc:
                desc = f"Kernel {kernel_type}: {title}"
            desc = desc[:120]

            entry = {
                'uid': uid,
                'type': 'kernel',
                'status': status,
                'title': title[:100],
                'description': desc,
                'owner': 'tropo',
                'created': created,
                'modified': modified,
                'tags': [f'kernel-{kernel_type}', 'os'],
                'file_ext': 'md',
                'schema_version': 1,
                'scope': 'ship',
                'path': rel_path,
                'created_by': fm.get('author', 'tropo'),
            }

            new_entries.append(entry)
            existing_uids.add(uid)

    print(f"Scanned .tropo/ directory")
    print(f"  Already registered: {already_registered}")
    print(f"  New entries to add: {len(new_entries)}")

    if DRY_RUN:
        print("\n[DRY RUN] Entries that would be added:\n")
        for e in new_entries:
            print(f"  {e['uid']}  |  {e['tags'][0]:20s}  |  {e['path']}")
        print(f"\n[DRY RUN] No changes written.")
        return

    # Append to index
    with open(INDEX_PATH, 'a', encoding='utf-8') as f:
        for entry in new_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"\n{len(new_entries)} kernel entries appended to {INDEX_PATH}")
    print(f"Total index rows now: {len(existing_uids)}")


if __name__ == '__main__':
    main()
