"""manifest_walker — Reads ship-artifact.capsule + walks ship-artifact graph + filters by target.

v1.43.0 Stream C extraction from build-release.py. Authored 2026-05-18 by argus-a72.

Per v1.42 capsule v1.3 amendment (substrate UID eeb59ddf), this module:

- Reads `manifest_root_uid:` from `.tropo/capsules/ship-artifact.capsule.md` frontmatter
- Resolves the correct root UID per target (release → b2e7d4a9; web → 4a99638d)
- Walks `vault/00-index.jsonl` filtering `type:ship-artifact + state:active + member_of contains <root_uid>`
- Hydrates ship-artifact-specific frontmatter fields (kind, source_mode, canonical_source, output_path, parent, target)
- Returns the target-filtered entry list ready for source_mode dispatch

Backward-compat: accepts scalar (v1.2) shape; treats as release target only.
"""

import json
import os
import re
import sys


def read_manifest_root_uid(capsule_path, target='release'):
    """Phase 0 step 1 — Read manifest_root_uid from ship-artifact.capsule frontmatter.

    Per arch-spec Required Behavior #3: NEVER hard-coded; always resolved dynamically.
    Halts with exit 64 (EX_USAGE) on TBD or absent.

    v1.42.0 Stream F atomic-commit migration: capsule v1.3 changed manifest_root_uid:
    from scalar to per-target map. This function accepts `target` parameter
    (default 'release' for build-release.py backward compat).

    Reader logic — map shape (v1.3+):
        manifest_root_uid:
          release: b2e7d4a9
          web: 4a99638d
        → returns the UID for the requested target key

    Backward-compat fallback — scalar shape (v1.2 and earlier):
        manifest_root_uid: b2e7d4a9
        → treated as release target's root; returned for target='release';
          ERROR for target='web' (web target requires v1.3+ capsule)

    Args:
        capsule_path: Absolute path to ship-artifact.capsule.md.
        target: Target key per v1.3 schema ('release' | 'web' | other future targets).

    Returns:
        8-hex manifest_root_uid string for the requested target.

    Raises:
        SystemExit(64): EX_USAGE — capsule not found, target absent in map, TBD value, or scalar+web.
    """
    if not os.path.exists(capsule_path):
        print(f'  ✗ BOOTSTRAP HALT: ship-artifact.capsule not found at {capsule_path}', file=sys.stderr)
        sys.exit(64)
    content = open(capsule_path).read()

    # Try v1.3 map shape first: look for `manifest_root_uid:` followed by indented `release: <uid>` etc.
    map_match = re.search(
        r'^manifest_root_uid:\s*\n((?:\s+\w+:\s*[a-f0-9]{8}.*\n)+)',
        content, re.MULTILINE
    )
    if map_match:
        # Parse the indented target → uid pairs
        target_map = {}
        for line in map_match.group(1).split('\n'):
            key_match = re.match(r'\s+(\w+):\s*([a-f0-9]{8})', line)
            if key_match:
                target_map[key_match.group(1)] = key_match.group(2)
        if target not in target_map:
            print(f'  ✗ BOOTSTRAP HALT: target {target!r} not declared in capsule manifest_root_uid map', file=sys.stderr)
            print(f'      Available targets: {list(target_map.keys())}', file=sys.stderr)
            sys.exit(64)
        return target_map[target]

    # Backward-compat: scalar shape (v1.2 and earlier)
    scalar_match = re.search(r'^manifest_root_uid:\s*([a-f0-9]{8})', content, re.MULTILINE)
    if scalar_match:
        if target != 'release':
            # P1-e absorption (sa.skeptic-108 R3 production-failure lens 2026-05-18):
            # provide migration path, not just rejection. Studios mid-migration need
            # guidance to recover.
            print(f'  ✗ BOOTSTRAP HALT: capsule manifest_root_uid is scalar (v1.2 shape); target {target!r} unsupported.', file=sys.stderr)
            print(f'      Web target requires v1.3+ capsule with manifest_root_uid map shape.', file=sys.stderr)
            print(f'      Migration path: amend `.tropo/capsules/ship-artifact.capsule.md` per v1.42 brief', file=sys.stderr)
            print(f'      `fdda7ceb` Stream A (capsule v1.3 schema amendment) — convert scalar manifest_root_uid', file=sys.stderr)
            print(f'      to per-target map shape:', file=sys.stderr)
            print(f'          manifest_root_uid:', file=sys.stderr)
            print(f'            release: <current-scalar-value>', file=sys.stderr)
            print(f'            web: <web-manifest-root-uid>   # e.g., 4a99638d in Argo', file=sys.stderr)
            print(f'      Then re-run this command. Capsule v1.3 spec: vault/files/eeb59ddf.md', file=sys.stderr)
            sys.exit(64)
        val = scalar_match.group(1)
        if val == 'TBD':
            print(f'  ✗ BOOTSTRAP HALT: manifest_root_uid is TBD in {capsule_path}', file=sys.stderr)
            print(f'      Phase D has not yet authored the Tropo Release Structure project.', file=sys.stderr)
            sys.exit(64)
        return val

    print(f'  ✗ BOOTSTRAP HALT: manifest_root_uid not found in {capsule_path}', file=sys.stderr)
    print(f'      Resolve per ship-artifact.capsule §Known Enforcement Gaps.', file=sys.stderr)
    sys.exit(64)


def load_manifest_entries(index_path, vault_root, manifest_root_uid, target='release'):
    """Phase 0 step 2 — Load ship-artifact entries belonging to manifest graph.

    Filters vault/00-index.jsonl to type:ship-artifact + state:active + member_of
    containing manifest_root_uid, then reads each entry's .md file frontmatter to
    extract ship-artifact-specific fields (kind, source_mode, canonical_source,
    output_path, parent, target) which are not all carried in the index.

    v1.42 capsule v1.3 amendment: entries declare `target:` as always-array.
    This function filters entries whose target array contains the requested target.
    Backward-compat: entries without explicit `target:` field are treated as
    `target: [release]` (the pre-v1.3 implicit default).

    Args:
        index_path: Absolute path to vault/00-index.jsonl.
        vault_root: Absolute path to the Studio root (parent of vault/, .tropo/, etc.).
        manifest_root_uid: 8-hex UID returned by read_manifest_root_uid().
        target: Target key for entry filtering ('release' | 'web' | etc.).

    Returns:
        List of hydrated ship-artifact entry dicts.
    """
    entries = []
    vault_files_dir = os.path.join(vault_root, 'vault', 'files')
    # P1-a absorption (sa.skeptic-108 R3 production-failure lens 2026-05-18):
    # silent-skip counters surface what was previously lost. Engine reports
    # malformed/orphan counts to stderr at end of walk — substrate-honesty over
    # silently-correct.
    malformed_index_rows = 0
    orphan_index_rows = 0  # member_of matches manifest but vault/files/<uid>.md missing
    scalar_target_skips = 0  # P1-d absorption: scalar target:<value> at-odds with v1.3 array shape
    with open(index_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                malformed_index_rows += 1
                continue
            if e.get('type') != 'ship-artifact':
                continue
            if e.get('state') != 'active':
                continue
            mo = e.get('member_of', [])
            if isinstance(mo, str):
                mo = [mo]
            if manifest_root_uid not in mo:
                continue
            # Hydrate ship-artifact-specific fields from the .md frontmatter
            md_path = os.path.join(vault_files_dir, e['uid'] + '.md')
            if not os.path.exists(md_path):
                orphan_index_rows += 1
                continue
            content = open(md_path).read()
            if not content.startswith('---'):
                continue
            end = content.find('\n---', 3)
            if end < 0:
                continue
            fm = content[3:end]
            for field in ('kind', 'source_mode', 'canonical_source', 'output_path', 'parent'):
                m = re.search(rf'^{field}:\s*(.+?)\s*$', fm, re.MULTILINE)
                if m:
                    val = m.group(1).strip()
                    # strip any inline comment
                    if '  #' in val:
                        val = val.split('  #')[0].strip()
                    e[field] = val
            # Parse `target:` array (v1.3 shape: flow-style `target: [release]` OR block-style
            # `target:\n  - release`). Both YAML shapes are valid + PyYAML-equivalent; previously
            # only flow-style was detected — block-style was false-matched by scalar fallback and
            # rejected as "scalar shape" (e9b3c421 substrate-fidelity bug, Metis-G55-filed
            # 2026-05-18, Argus-A74 fix 2026-05-19).
            target_list = None
            # Try flow-style: target: [release] or target: [release, web]
            flow_match = re.search(r'^target:\s*\[([^\]]*)\]', fm, re.MULTILINE)
            if flow_match:
                target_list = [t.strip().strip('"\'') for t in flow_match.group(1).split(',') if t.strip()]
            else:
                # Try block-style:
                #   target:
                #     - release
                #     - web
                # Capture one-or-more `  - <value>` lines immediately following `target:`.
                block_match = re.search(
                    r'^target:[ \t]*\n((?:[ \t]+-[ \t]+\S.*\n?)+)',
                    fm,
                    re.MULTILINE,
                )
                if block_match:
                    target_list = []
                    for line in block_match.group(1).strip().split('\n'):
                        line = line.strip()
                        if line.startswith('- '):
                            val = line[2:].strip()
                            # strip inline comment
                            if '  #' in val:
                                val = val.split('  #')[0].strip()
                            val = val.strip('"\'')
                            if val:
                                target_list.append(val)
            if target_list is not None:
                e['target'] = target_list
            else:
                # Detect scalar `target:` (mid-migration entry; should be array per v1.3)
                # P1-d absorption (sa.skeptic-108 R3): engine was implicitly defaulting scalar to ['release']
                # — substrate-honesty issue. Now: surface as warning + skip the entry rather than silently
                # treat as release-target (Check 24 validator catches at audit time, but engine implicit
                # behavior was at odds with that posture).
                # Tightened (e9b3c421 fix): [ \t]* on whitespace and [^\[\n] on first char ensure
                # we don't false-match block-style YAML by consuming a newline into the value.
                scalar_match = re.search(r'^target:[ \t]*([^\[\n].*)$', fm, re.MULTILINE)
                if scalar_match:
                    scalar_target_skips += 1
                    print(
                        f'  ⚠ load_manifest_entries: {e["uid"]} has scalar `target:` shape '
                        f'(v1.3 requires array); skipping. Fix entry frontmatter to '
                        f'`target: [release]` etc.',
                        file=sys.stderr,
                    )
                    continue
                # No `target:` field at all — backward-compat: pre-v1.3 entries implicit [release]
                e['target'] = ['release']
            # Parse cleanup_rules block (YAML block-style map)
            # Shape:
            #   cleanup_rules:
            #     strip_nav_blocks: true
            #     broken_link_policy: strip
            # Not in the scalar-field hydration loop above; requires block-style parser.
            cr_match = re.search(
                r'^cleanup_rules:[ \t]*\n((?:[ \t]+\w+:[ \t]*\S.*\n?)+)',
                fm,
                re.MULTILINE,
            )
            if cr_match:
                cleanup_rules = {}
                for line in cr_match.group(1).split('\n'):
                    kv = re.match(r'\s+(\w+):\s*(.+?)\s*$', line)
                    if kv:
                        key = kv.group(1)
                        val_str = kv.group(2).strip()
                        if '  #' in val_str:
                            val_str = val_str.split('  #')[0].strip()
                        if val_str.lower() == 'true':
                            val = True
                        elif val_str.lower() == 'false':
                            val = False
                        else:
                            val = val_str.strip('"\'')
                        cleanup_rules[key] = val
                e['cleanup_rules'] = cleanup_rules
            # Filter by requested target
            if target not in e['target']:
                continue
            entries.append(e)

    # Surface silent-skip counts (P1-a absorption)
    if malformed_index_rows or orphan_index_rows or scalar_target_skips:
        msg_parts = []
        if malformed_index_rows:
            msg_parts.append(f'{malformed_index_rows} malformed index rows')
        if orphan_index_rows:
            msg_parts.append(f'{orphan_index_rows} orphan rows (member_of matches but vault/files/<uid>.md missing)')
        if scalar_target_skips:
            msg_parts.append(f'{scalar_target_skips} scalar-target-shape entries')
        print(
            f'  ⚠ load_manifest_entries: skipped {", ".join(msg_parts)} during walk',
            file=sys.stderr,
        )
    return entries
