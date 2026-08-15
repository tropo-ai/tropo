#!/usr/bin/env python3
"""
---
uid: 5a91c3f0
title: generate-update-manifest — Tool
name: generate-update-manifest
type: tool
status: active
owner: talos
domain: Generate the Update API's static manifest JSON (transport lean per fc4874f4 A122 walk) from governed type:release vault entries, and optionally upload it to the Supabase releases bucket at a stable, non-expiring URL.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/tropo-generate-update-manifest.py [--upload] [--out <path>]
script_path: vault/tools/tropo-generate-update-manifest.py
input:
  type: object
  properties:
    upload:
      type: boolean
      description: Upload the generated manifest to the Supabase releases bucket at a stable path.
    out:
      type: string
      description: Local path to write the manifest JSON (default vault/updates/updates-manifest.json).
output:
  type: object
  properties:
    manifest:
      type: object
destructive: false
audit_required: false
writes_scope:
- vault/updates/updates-manifest.json
governance_category: lifecycle
description: 'Implements the Update API (task f1d4b9e6) as a static-manifest transport (A122 walk lean confirmed at fc4874f4 lock): no live server, a JSON manifest generated + uploaded by tropo-build-release.py at ship time to the existing Supabase releases bucket at a STABLE (non-expiring, non-version-namespaced) path. User-agents GET the manifest, then do the version comparison CLIENT-SIDE against their local .tropo/version.md — offline simply means the fetch is skipped, no error state. Source of truth: type:release, status:shipped entries in vault/00-index.jsonl, each carrying release_version + description (+ optional min_compatible / update_type overrides). Chain order is ascending semver; min_compatible for each release defaults to the immediately-prior release'"'"'s version unless the release entry declares its own.'
domain_tags:
- update-api
- static-manifest
- transport-lean
- gate-2
- clean-self-update
created: 2026-07-02
created_by: talos-t23
modified: 2026-07-02
modified_by: talos-t23
governed_by: d5e1b4a3
capsule_version: '2.5'
schema_version: 2
extraction_scope: ship
member_of:
- 8dd772a0
tags:
- tool
- cli
- update-api
- manifest
- gate-2
subsystem_hub:
- 8dd772a0
---
"""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path


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
INDEX_PATH = str(tropo_roots.VAULT_DIR / '00-index.jsonl')
DEFAULT_OUT = str(tropo_roots.VAULT_DIR / 'updates' / 'updates-manifest.json')

# Stable (non-expiring) path in the Supabase releases bucket — NOT version-namespaced,
# so the client always fetches the same URL and always gets the latest catalog.
# Mirrors the bucket build-release.py already uploads zips to (storage/v1/object/releases/...).
MANIFEST_BUCKET_PATH = 'releases/updates-manifest.json'


def _semver_key(v):
    """Sort key for 'X.Y.Z' strings; malformed versions sort first (defensive, never crashes)."""
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)$', v.lstrip('v'))
    if not m:
        return (-1, -1, -1)
    return tuple(int(g) for g in m.groups())


def load_release_catalog(index_path):
    """Load shipped releases from the ADR-047 current+archive index union.

    Historical shipped releases are expected to live on the archive surface;
    update-chain generation is an explicitly history-aware consumer.
    Load actual
    Tropo-OS product releases — ascending by semver, deduped by version (last wins).

    Two discriminators exclude non-product release records that share the same
    capsule type: (1) extraction_scope must not be 'argo-private' (excludes Mike's
    day-job/MindBridge content releases, e.g. 'kb-marketing-v14.0', which are real
    test cargo for the studio but not Tropo-OS versions); (2) release_version must
    be strict semver X.Y.Z (excludes non-OS version tags like 'mos-v13.0').
    """
    by_version = {}
    index_path = Path(index_path)
    archive_path = index_path.parent / '00-archive-index.jsonl'
    if not index_path.exists() and not archive_path.exists():
        return []
    for surface in (index_path, archive_path):
        if not surface.exists():
            continue
        with surface.open('r') as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get('type') != 'release':
                    continue
                if row.get('status') != 'shipped':
                    continue
                if row.get('extraction_scope') == 'argo-private':
                    continue
                version = (row.get('release_version') or '').lstrip('v')
                if _semver_key(version) == (-1, -1, -1):
                    continue
                by_version[version] = row  # last one wins on duplicate version records
    releases = list(by_version.values())
    releases.sort(key=lambda r: _semver_key(r.get('release_version', '').lstrip('v')))
    return releases


def _resolve_package_url_base():
    """Package URLs must point where packages actually live: the same Supabase
    releases bucket that serves this manifest (public path, no auth). The prior
    default 'https://api.tropo-ai.com/updates' was fictional infrastructure —
    the host never resolved, discovered live on the FIRST customer apply attempt
    (2026-08-09). Only the public project URL is needed (no secret)."""
    supabase_url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
    if not supabase_url:
        env_file = tropo_roots.STUDIO_ROOT / 'tropo-app' / '.env.local'
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('NEXT_PUBLIC_SUPABASE_URL='):
                        supabase_url = line.strip().split('=', 1)[1]
    if not supabase_url:
        return None
    return f"{supabase_url.rstrip('/')}/storage/v1/object/public/releases/updates"


def build_manifest(releases, package_url_base=None):
    """Build the Update API manifest per the three response shapes in task f1d4b9e6.

    The manifest itself carries the FULL catalog (static-transport lean); the client
    derives which shape applies to it by comparing its own .tropo/version.md against
    `current` / `minimum_supported` / each update's `min_compatible`. This function
    produces the catalog; it does not know any individual client's current version.
    """
    if not releases:
        return {
            'current': None,
            'minimum_supported': None,
            'updates': [],
            'note': 'No shipped releases recorded in the vault release catalog yet '
                    '(type:release, status:shipped in vault/00-index.jsonl).',
        }

    updates = []
    prior_version = None
    for r in releases:
        version = r.get('release_version', '').lstrip('v')
        # min_compatible: explicit override on the release entry wins; otherwise the
        # immediately-prior release in the chain (linear step-through by default).
        min_compatible = r.get('min_compatible') or prior_version or version
        update_type = r.get('update_type') or _infer_update_type(prior_version, version)
        updates.append({
            'version': version,
            'type': update_type,
            'description': (r.get('description') or r.get('title') or '')[:200],
            'url': f'{package_url_base}/tropo-update-v{version}.zip',  # base resolved, never fictional
            'min_compatible': min_compatible,
        })
        prior_version = version

    current = releases[-1].get('release_version', '').lstrip('v')
    minimum_supported = releases[0].get('release_version', '').lstrip('v')

    return {
        'current': current,
        'minimum_supported': minimum_supported,
        'updates': updates,
    }


def _infer_update_type(prior_version, version):
    """patch/feature/release inferred from semver delta when the release entry doesn't declare one."""
    if not prior_version:
        return 'release'
    p = _semver_key(prior_version)
    v = _semver_key(version)
    if p[0] != v[0]:
        return 'release'
    if p[1] != v[1]:
        return 'feature'
    return 'patch'


def render_for_client(manifest, client_version):
    """Client-side comparison logic (documented here for the apply-update playbook +
    concierge to call/port — the static-transport lean puts this on the CLIENT, not
    a server). Returns exactly one of the three response shapes from task f1d4b9e6,
    plus a graceful non-crashing fallback for malformed/unknown version strings
    (task f1d4b9e6 acceptance criterion: never a 500/stack trace)."""
    client_key = _semver_key(client_version)
    if client_key == (-1, -1, -1):
        # Malformed/unparseable local version — cannot compare. Graceful, not an error
        # state: behave like "no update info available" (same posture as offline=skip)
        # rather than falsely claiming migration_required for a version we can't read.
        return {
            'current': manifest.get('current'),
            'updates': [],
            'note': f"Local version '{client_version}' is not a parseable semver string — "
                    f"skipping comparison. Treat as no update info available.",
        }

    if not manifest.get('current'):
        return {'current': client_version, 'updates': []}

    min_key = _semver_key(manifest['minimum_supported'])

    if client_key < min_key:
        return {
            'migration_required': True,
            'message': (
                f"Your vault is at v{client_version} but this update requires "
                f"v{manifest['minimum_supported']} or higher. Install the intermediate "
                f"updates in order before this one can apply."
            ),
        }

    pending = [u for u in manifest['updates'] if _semver_key(u['version']) > client_key]
    if not pending:
        return {'current': manifest['current'], 'updates': []}

    return {
        'current': manifest['current'],
        'minimum_supported': manifest['minimum_supported'],
        'updates': pending,
    }


def upload_to_supabase(manifest_json):
    """Upload the manifest to the stable bucket path. Mirrors build-release.py's upload
    auth pattern (apikey + Bearer header, x-upsert for overwrite-on-reship)."""
    import urllib.request

    supabase_url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_SECRET_KEY')

    if not supabase_url or not supabase_key:
        # tropo-app lives INSIDE the studio (third instance of the one-level-off
        # class caught at the v1.86.0 fire, 2026-08-09; siblings fixed the same night
        # in tropo-publish-release.py).
        env_file = tropo_roots.STUDIO_ROOT / 'tropo-app' / '.env.local'
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('NEXT_PUBLIC_SUPABASE_URL='):
                        supabase_url = line.strip().split('=', 1)[1]
                    elif line.startswith('SUPABASE_SECRET_KEY='):
                        supabase_key = line.strip().split('=', 1)[1]

    if not supabase_url or not supabase_key:
        print('  ⚠ Supabase credentials not found. Manifest generated locally only; upload skipped.')
        return False

    upload_url = f'{supabase_url}/storage/v1/object/{MANIFEST_BUCKET_PATH}'
    req = urllib.request.Request(upload_url, data=manifest_json.encode('utf-8'), method='POST')
    req.add_header('apikey', supabase_key)
    req.add_header('Authorization', f'Bearer {supabase_key}')
    req.add_header('Content-Type', 'application/json')
    req.add_header('x-upsert', 'true')

    try:
        response = urllib.request.urlopen(req)
        if response.status in (200, 201):
            print(f'  ✓ Update manifest uploaded to {MANIFEST_BUCKET_PATH} (stable URL)')
            return True
        print(f'  ✗ Manifest upload failed: HTTP {response.status}')
        return False
    except Exception as e:
        print(f'  ✗ Manifest upload failed: {e}')
        return False


def main():
    do_upload = '--upload' in sys.argv
    out_path = DEFAULT_OUT
    if '--out' in sys.argv:
        out_path = sys.argv[sys.argv.index('--out') + 1]

    releases = load_release_catalog(INDEX_PATH)
    package_url_base = _resolve_package_url_base()
    if not package_url_base:
        print('  ⚠ NEXT_PUBLIC_SUPABASE_URL unresolvable — package URLs cannot be emitted '
              'truthfully; refusing to generate a manifest with fictional hosts.',
              file=sys.stderr)
        sys.exit(2)
    manifest = build_manifest(releases, package_url_base=package_url_base)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
    with open(out_path, 'w') as f:
        f.write(manifest_json + '\n')

    print(f'  Update manifest: {len(manifest.get("updates", []))} release(s) in catalog, '
          f'current={manifest.get("current")}, minimum_supported={manifest.get("minimum_supported")}')
    print(f'  Written to {out_path}')

    if do_upload:
        upload_to_supabase(manifest_json)

    return manifest


if __name__ == '__main__':
    main()
