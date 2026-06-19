#!/usr/bin/env python3
"""
---
uid: e3f5a8c1
title: validate-canonical-l0 — Tool
name: validate-canonical-l0
type: tool
status: active
owner: argus
domain: Verifies the rendered project-tree's L0 set matches the canonical L0 declaration; fails on drift.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/e3f5a8c1.py [--vault-path PATH] [--json]
script_path: vault/tools/e3f5a8c1.py
input:
  type: object
  properties:
    vault-path:
      type: string
      description: Optional explicit vault root (must contain vault/ + .tropo/).
    json:
      type: boolean
      description: When set, emits machine-readable JSON output.
output:
  type: object
  properties:
    verdict:
      type: string
      enum:
      - pass
      - mismatch
      - registry-or-tree-missing
    canonical_l0_count:
      type: integer
    rendered_l0_count:
      type: integer
    drift_details:
      type: array
      items:
        type: object
destructive: false
audit_required: false
writes_scope: []
governance_category: query
description: 'Reads .tropo-studio/registries/canonical-l0-projects.yaml and vault/00-project-tree.jsonl; compares the canonical L0 set against the rendered L0 set; fails on missing/extra/title-mismatch + on declared-non-L0 projects bubbling to L0. Integrated into build-release.py Step 0b pre-flight gate. Closes the v1.13.x defect class (substrate-membership backfill conflated ''missing parent'' with ''true L0 root''). Exit codes: 0 PASS / 1 mismatch / 2 file missing.'
domain_tags:
- validation
- structural-shape
- canonical-l0
- build-pipeline-pre-flight
- l0-mutation-protection
trigger_description: 'Reach for this when about to make any architectural call that could change the project-tree''s L0 set (reparenting projects, mutating member_of: arrays, modifying canonical-l0-projects.yaml, running v1.12-style substrate backfill scripts). Run before AND after the change. Pass = canonical L0 unchanged; non-zero exit = STOP and verify against canon. Honors Operating Principle 11 ''Verify Against Canonical Reference Before Architectural Calls''.'
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
- canonical-l0
- structural-shape
- build-pipeline-pre-flight
- v1.15-stream-b-worked-example
subsystem_hub:
- 8dd772a0
---
"""

"""
validate-canonical-l0.py — v1.13.6 Canonical L0 Verification

Compares the rendered project-tree's L0 set against the canonical L0 declaration
in .tropo-studio/registries/canonical-l0-projects.yaml. Fails on any mismatch:
  - Canonical L0 missing from rendered tree (project moved or member_of: corrupted)
  - Project from non_l0_with_hub_only_risk bubbled to L0 (lost non-hub rendering parent)
  - Extra L0 in rendered tree not declared anywhere (needs registry entry or non-hub parent)
  - Title mismatch (canonical project's title doesn't match rendered)

v1.13.6 (Argus A52 2026-05-08): extended to verify non_l0_with_hub_only_risk list — projects
explicitly declared "should not appear at L0." Same defect class as canonical-L0 drift; same
detection mechanism. Closes the L0-mutation-protection class for both directions (canonical
L0 missing AND declared-non-L0 bubbling).

Exit codes:
  0 — all canonical L0s present, no extras, all titles match
  1 — mismatch found (caller should NOT proceed with build)
  2 — registry or project-tree file missing/unreadable

Usage:
  python3 .tropo/scripts/validate-canonical-l0.py
  python3 .tropo/scripts/validate-canonical-l0.py --vault-path /path/to/argo-os
  python3 .tropo/scripts/validate-canonical-l0.py --json   # machine-readable output

This validator is integrated into build-release.py Step 0 pre-flight gate. It runs
alongside validate-capability-membership.py + validate-release-manifest.py to catch
L0 drift before any extract work begins.

Background: v1.12 substrate-membership backfill replaced empty member_of arrays with
hub-UIDs, conflating "missing parent" with "true L0 root" — collapsing the rendered
nav under Tropo Governance hub. v1.13.1 shipped a render-fix; v1.13.5 (this script)
locks the L0 set as explicit substrate so future cycles verify against canon rather
than inferring.

v1.14 schema split (separate subsystem_hub: field from member_of:) will eliminate
the underlying ambiguity. This validator remains as the structural-shape check.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional


def find_vault_root(explicit: Optional[str]) -> Optional[Path]:
    """Resolve vault root: explicit arg, or walk up from script location."""
    if explicit:
        p = Path(explicit).resolve()
        if (p / 'vault').is_dir() and (p / '.tropo').is_dir():
            return p
        return None

    script_path = Path(__file__).resolve()
    for candidate in [script_path.parent.parent.parent, script_path.parent.parent, *script_path.parents]:
        if (candidate / 'vault').is_dir() and (candidate / '.tropo').is_dir():
            return candidate
    return None


def load_canonical_registry(vault_root: Path) -> Optional[dict[str, Any]]:
    """Load the canonical L0 registry. Try yaml.safe_load; fall back to minimal parser."""
    registry_path = vault_root / '.tropo-studio' / 'registries' / 'canonical-l0-projects.yaml'
    if not registry_path.exists():
        return None
    text = registry_path.read_text()

    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        # Minimal fallback parser for the canonical_l0_projects list — enough for this validator.
        return _minimal_parse(text)


def _minimal_parse(text: str) -> dict[str, Any]:
    """Tiny YAML-subset parser. Only handles the structure this registry actually uses."""
    out: dict[str, Any] = {'canonical_l0_projects': []}
    in_list = False
    current: Optional[dict[str, str]] = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith('#'):
            continue
        if line.startswith('canonical_l0_projects:'):
            in_list = True
            continue
        if in_list:
            stripped = line.strip()
            if line.startswith('  - uid:'):
                if current:
                    out['canonical_l0_projects'].append(current)
                current = {'uid': stripped.split(':', 1)[1].strip()}
            elif line.startswith('    title:') and current is not None:
                v = stripped.split(':', 1)[1].strip()
                current['title'] = v.strip('"').strip("'")
            elif line.startswith('non_l0_with_hub_only_risk:') or (not line.startswith(' ') and line.endswith(':')):
                if current:
                    out['canonical_l0_projects'].append(current)
                    current = None
                in_list = False
    if current and in_list:
        out['canonical_l0_projects'].append(current)
    return out


def load_rendered_l0_set(vault_root: Path, state_filter: Optional[str] = 'active') -> Optional[list[dict[str, Any]]]:
    """Load the rendered L0 set from 00-project-tree.jsonl (parent: null entries).

    state_filter: 'active' (default — daily working view), 'archived', or None (all states).
    The canonical L0 declaration is for the active working view; archived L0s with hub-only
    member_of: are tracked as a separate carry-forward (Vela-lane reparenting work).
    """
    tree_path = vault_root / 'vault' / '00-project-tree.jsonl'
    if not tree_path.exists():
        return None
    roots = []
    seen_uids: set[str] = set()
    with open(tree_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n = json.loads(line)
            if n.get('parent') is None and n['uid'] not in seen_uids:
                # v1.46.0.1 substrate fix (argus-a76 2026-05-20): treat state:standing as part of
                # the "active" view. Standing-state entries (evergreen / never-complete containers
                # like the agents L0 anchor 5e9c1a82) ARE active for navigation purposes; only
                # complete/archived/cancelled fall outside "active." Without this, standing-state
                # canonical L0s false-FAIL the validator even though they render correctly at L0.
                # 99e52c18 state-disambiguate (2026-06-09): state:standing is migrated to
                # state:active + lifecycle:standing; the 'standing' branch here is dead.
                node_state = n.get('state', 'active')
                if state_filter == 'active':
                    if node_state != 'active':
                        continue
                elif state_filter is not None and node_state != state_filter:
                    continue
                roots.append({'uid': n['uid'], 'title': n.get('title', ''), 'state': node_state})
                seen_uids.add(n['uid'])
    return roots


def compare(canonical: list[dict[str, str]], rendered: list[dict[str, str]],
            non_l0_risk: Optional[list[dict[str, str]]] = None) -> dict[str, Any]:
    """Diff the two sets. Returns findings dict.

    non_l0_risk: list of projects from the registry's non_l0_with_hub_only_risk section.
    These projects MUST NOT appear at L0 — they should nest under their declared canonical_parent.
    If they appear at L0, it means their member_of: was reset to hub-only (or empty), losing
    the non-hub rendering parent. Same defect class as canonical L0 drift.
    """
    canonical_uids = {p['uid']: p for p in canonical}
    rendered_uids = {p['uid']: p for p in rendered}
    non_l0_uids = {p['uid']: p for p in (non_l0_risk or [])}

    missing = [c for uid, c in canonical_uids.items() if uid not in rendered_uids]
    title_mismatches = []
    for uid, c in canonical_uids.items():
        r = rendered_uids.get(uid)
        if r and c.get('title') and r.get('title') and c['title'] != r['title']:
            title_mismatches.append({'uid': uid, 'canonical_title': c['title'], 'rendered_title': r['title']})

    # Extras: projects rendering at L0 that are NOT canonical L0.
    # Split into two classes for clearer reporting:
    #   - non_l0_risk_at_l0: explicitly declared "should not be L0" (the Packs class) — these are
    #     definite mutation defects (their canonical_parent edge was lost).
    #   - extra_unknown: not in either canonical or non_l0_risk — could be a new project that
    #     should be added to canonical, OR a project missing a non-hub parent.
    extras_all = [r for uid, r in rendered_uids.items() if uid not in canonical_uids]
    non_l0_risk_at_l0 = []
    extra_unknown = []
    for r in extras_all:
        if r['uid'] in non_l0_uids:
            entry = dict(r)
            entry['canonical_parent'] = non_l0_uids[r['uid']].get('canonical_parent', 'unknown')
            non_l0_risk_at_l0.append(entry)
        else:
            extra_unknown.append(r)

    return {
        'canonical_count': len(canonical),
        'rendered_count': len(rendered),
        'non_l0_risk_count': len(non_l0_uids),
        'missing_from_rendered': missing,
        'non_l0_risk_at_l0': non_l0_risk_at_l0,
        'extra_unknown': extra_unknown,
        'title_mismatches': title_mismatches,
        'pass': not (missing or non_l0_risk_at_l0 or extra_unknown or title_mismatches),
    }


def report_human(findings: dict[str, Any]) -> None:
    print("=" * 72)
    print("validate-canonical-l0.py — v1.13.6 Canonical L0 Verification")
    print("=" * 72)
    print(f"Canonical L0 count:        {findings['canonical_count']}")
    print(f"non_l0_with_hub_only_risk: {findings.get('non_l0_risk_count', 0)} (must NOT appear at L0)")
    print(f"Rendered L0 count:         {findings['rendered_count']}")
    print()

    if findings['missing_from_rendered']:
        print(f"❌ MISSING from rendered tree ({len(findings['missing_from_rendered'])}):")
        for p in findings['missing_from_rendered']:
            print(f"   {p['uid']}  {p.get('title', '')}")
        print("   → A canonical L0 is not rendering as L0. Check member_of: edges; project may have")
        print("     been speculatively reparented or its L0 status corrupted by a backfill script.")
        print()

    if findings.get('non_l0_risk_at_l0'):
        print(f"❌ DECLARED-NON-L0 BUBBLED TO L0 ({len(findings['non_l0_risk_at_l0'])}):")
        for p in findings['non_l0_risk_at_l0']:
            print(f"   {p['uid']}  {p.get('title', '')}  (canonical_parent: {p.get('canonical_parent')})")
        print("   → A project explicitly declared in non_l0_with_hub_only_risk has lost its non-hub")
        print("     rendering parent. Most likely cause: a backfill script mutated its member_of:")
        print("     to hub-only (same defect class as v1.12). Restore the non-hub parent.")
        print()

    if findings.get('extra_unknown'):
        print(f"❌ EXTRA in rendered tree (not declared anywhere) ({len(findings['extra_unknown'])}):")
        for p in findings['extra_unknown']:
            print(f"   {p['uid']}  {p.get('title', '')}")
        print("   → A project bubbled to L0 that's not in canonical_l0_projects OR")
        print("     non_l0_with_hub_only_risk. Either: (a) give it a non-hub parent in member_of:")
        print("     so it nests properly, OR (b) add it to the appropriate registry section with")
        print("     Mike approval.")
        print()

    if findings['title_mismatches']:
        print(f"⚠ TITLE MISMATCHES ({len(findings['title_mismatches'])}):")
        for m in findings['title_mismatches']:
            print(f"   {m['uid']}: canonical={m['canonical_title']!r} rendered={m['rendered_title']!r}")
        print("   → Update canonical-l0-projects.yaml or the project's title to match.")
        print()

    if findings['pass']:
        print("✓ PASS — rendered L0 matches canonical exactly + no declared-non-L0 at L0.")
    else:
        print("✗ FAIL — rendered L0 set does not match canonical declaration.")
    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate rendered L0 against canonical declaration.")
    parser.add_argument('--vault-path', help="Vault root path. Default: walk up from script location.")
    parser.add_argument('--state', default='active', choices=['active', 'archived', 'all'],
                        help="Which L0 state set to validate against canonical (default: active — the daily working view).")
    parser.add_argument('--json', action='store_true', help="Emit findings as JSON (no human-readable report).")
    args = parser.parse_args()

    vault_root = find_vault_root(args.vault_path)
    if not vault_root:
        msg = "Could not resolve vault root. Pass --vault-path explicitly."
        if args.json:
            print(json.dumps({'error': msg, 'exit_code': 2}))
        else:
            sys.stderr.write(f"ERROR: {msg}\n")
        return 2

    registry = load_canonical_registry(vault_root)
    if not registry:
        msg = "canonical-l0-projects.yaml not found at .tropo-studio/registries/"
        if args.json:
            print(json.dumps({'error': msg, 'exit_code': 2}))
        else:
            sys.stderr.write(f"ERROR: {msg}\n")
        return 2

    canonical = registry.get('canonical_l0_projects', [])
    non_l0_risk = registry.get('non_l0_with_hub_only_risk', [])
    state_filter = None if args.state == 'all' else args.state
    rendered = load_rendered_l0_set(vault_root, state_filter)
    if rendered is None:
        msg = "vault/00-project-tree.jsonl not found. Run rebuild-vault.py first."
        if args.json:
            print(json.dumps({'error': msg, 'exit_code': 2}))
        else:
            sys.stderr.write(f"ERROR: {msg}\n")
        return 2

    findings = compare(canonical, rendered, non_l0_risk)

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        report_human(findings)

    return 0 if findings['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
