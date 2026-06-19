#!/usr/bin/env python3
"""
---
uid: e8d4c1b9
title: rebuild-vault — Tool
name: rebuild-vault
type: tool
status: active
owner: argus
domain: Comprehensive substrate refresh — wraps rebuild-index + rehydrate + stale-cascade cleanup (v1.15.1 wrapper).
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/e8d4c1b9.py [--dry-run] [--only UID] [--vault-path PATH]
script_path: vault/tools/e8d4c1b9.py
input:
  type: object
  properties:
    apply:
      type: boolean
      description: "(v1.62 default-flip) APPLY is now the default; this flag is a backward-compat alias. Pass --dry-run for preview-only."
    vault-path:
      type: string
destructive: false
audit_required: false
writes_scope:
- vault/00-index.jsonl
- vault/00-project-tree.jsonl
- vault/00-cascade-*.jsonl
governance_category: lifecycle
description: 'v1.15.1 comprehensive-cadence wrapper. Composes three passes: (1) rebuild-index.py (fast: index + project-tree only with reflection-of-frontmatter and Studio-root scan); (2) rehydrate.py (symlink tree under 00-tropo-nav/); (3) stale-cascade cleanup (removes vault/00-cascade-<uid>.jsonl files whose root UID no longer exists in the rebuilt index). Use at boot, ship-prep, and structural changes when nav rendering matters. For the common-case edit-and-index cycle, prefer rebuild-index.py directly (~1-2s vs ~12-15s).'
domain_tags:
- index-rebuild
- project-tree
- rehydrate
- cascade-cleanup
- comprehensive-wrapper
- ledger-hygiene
- idempotent
- v1.15.1-stream-b-refactor
trigger_description: "Comprehensive substrate refresh (index + nav + boards + brief)."
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
supersedes: f7e3d9a2
tags:
- tool
- cli
- index-rebuild
- project-tree
- ledger-hygiene
- v1.15-stream-b
subsystem_hub:
- dbc1cbbf
belt: true
belt_invocation: "python3 vault/tools/e8d4c1b9.py"
belt_example: "python3 vault/tools/e8d4c1b9.py --only 3031ffa3"
---
"""
from __future__ import annotations

"""rebuild-vault.py — comprehensive substrate refresh wrapper (v1.15.1 + v1.30.0 Stream C-a).

After v1.15.1, this script is the comprehensive-cadence wrapper. After v1.30.0 Stream C-a
(Argus A63 + Mike pair-design 2026-05-15), it ALSO invokes tropo-validate.py as a NEW pre-step
before the rebuild flow — making rebuild-vault.py the canonical "is this substrate clean +
rebuildable?" gesture. Validator FAIL → refuses rebuild against broken substrate.

Composes (in order):
    [1/5] tropo-validate.py — NEW pre-step (v1.30.0 Stream C-a); refuses rebuild on validator FAIL
    [2/5] rebuild-index.py  — fast index + project-tree rebuild (with --skip-rehydrate per
                              v1.30.0 Stream C-a composition fix; rehydrate is invoked
                              explicitly at [3/5] below)
    [3/5] rehydrate.py      — symlink tree refresh under 00-tropo-nav/
    [4/5] stale-cascade cleanup — removes vault/00-cascade-<uid>.jsonl files whose
                                  root UID no longer exists in the rebuilt index
    [5/5] Relations + Members rendering across vault/files/
    [5b/5] import-walker reconcile (regenerate sidecar projections; v1.25.0+ only)

Exit codes (v1.30.0 NEW):
    0   PASS — all steps clean
    1   existing rebuild-index.py failure (unchanged)
    2   vault root could not be resolved (unchanged)
    8   tropo-validate.py FAILED (validator surfaced FAIL findings; refuses rebuild)
    9   tropo-validate.py timeout (120s) OR setup error (exit ≥2)

Use this script:
    - At Vela's daily Operational Health pass
    - At dev-pipeline ship-prep (Stream I atomic-triangle)
    - On structural changes (new file / delete / archival flip / member_of edit)
      when nav rendering matters in the next few minutes

For the common-case "I edited a file; refresh the index for queryability," prefer the
faster `python3 .tropo/scripts/rebuild-index.py --apply` directly (~1-2s vs ~12-15s).

Usage (v1.62 default-flip — APPLY is now the default):
    python3 .tropo/scripts/rebuild-vault.py            # WRITE (apply is default)
    python3 .tropo/scripts/rebuild-vault.py --dry-run  # preview only, no writes
    python3 .tropo/scripts/rebuild-vault.py --apply    # WRITE (backward-compat alias; same as bare)
    python3 .tropo/scripts/rebuild-vault.py --vault-path <path>

Vault path resolution: same as rebuild-index.py.

Author: argus-a53
Owner: argus
Domain: ledger-hygiene; v1.15.1 rebuild-script reform.

History:
    Pre-v1.15.1: rebuild-vault.py handled index + project-tree directly + cascade cleanup.
    v1.15.1: forked into rebuild-index.py (fast/frequent) + this wrapper (comprehensive/less-frequent)
             per Vela 4c2456b4 architecture and Mike-Vela cadence-math conversation 2026-05-09.
    rebuild-index.py inherits all the parsing + processing logic; this wrapper composes the
    additional rehydrate + cascade-cleanup passes.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


# v1.56 Lane S: script relocated to vault/tools/; sibling scripts resolved by UID
_TOOLS = Path(__file__).resolve().parent
REBUILD_INDEX = _TOOLS / "f4b8a6e2.py"           # rebuild-index
REHYDRATE = _TOOLS / "a7c5e3f1.py"               # rehydrate
GENERATE_RELATIONS_HEADER = _TOOLS / "b8e4f1a3.py"   # generate-relations-header
TROPO_VALIDATE = _TOOLS / "d2b9c8e6.py"          # tropo-validate


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


def find_stale_cascades(ledger_dir: Path, valid_uids: set[str]) -> list[Path]:
    """Find `00-cascade-<uid>.jsonl` files whose root UID is no longer in the index."""
    stale: list[Path] = []
    for f in ledger_dir.glob('00-cascade-*.jsonl'):
        m = re.match(r'^00-cascade-([0-9a-f]{8})\.jsonl$', f.name)
        if not m:
            continue
        cascade_uid = m.group(1)
        if cascade_uid not in valid_uids:
            stale.append(f)
    return stale


def load_index_uids(index_path: Path) -> set[str]:
    """Read the rebuilt index and return the set of all valid UIDs."""
    uids: set[str] = set()
    if not index_path.exists():
        return uids
    import json
    with index_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                uid = rec.get('uid')
                if uid:
                    uids.add(uid)
            except json.JSONDecodeError:
                continue
    return uids


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Comprehensive substrate refresh — index + rehydrate + stale-cascade cleanup (v1.15.1).',
    )
    parser.add_argument('--apply', action='store_true',
                        help='(Default behavior; retained for backward-compat — build-release.py + muscle memory.) Write changes.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview only; do not write. NOTE: APPLY is now the default — pass --dry-run to preview.')
    parser.add_argument('--vault-path', metavar='PATH',
                        help='Explicit vault root (must contain vault/ + .tropo/).')
    parser.add_argument('--only', metavar='UID',
                        help='Incremental single-entry freshen (passthrough to rebuild-index --only): '
                             're-derive + upsert ONLY this entry into the live vault/00-index.sqlite, '
                             'skipping the full validate/rehydrate/relations orchestration. '
                             'Non-authoritative + self-healing per fc114e57 (brief d7b3f1a9 §4).')
    args = parser.parse_args()

    # v1.62 default-flip (Vela V55 2026-05-29): APPLY is now the default; --dry-run for preview.
    # Rationale: this tool is destructive:false (idempotent regeneration), the only programmatic
    # caller (build-release.py) passes --apply explicitly, and apply is the dominant ad-hoc use.
    # The prior dry-run-default produced a SILENT no-op that read as success (exit 0 + full output),
    # which bit three ad-hoc rebuilds in one session. --apply retained as a harmless alias so
    # existing callers + muscle memory keep working. Caller-audit 2026-05-29: build-release is the
    # sole programmatic caller and passes --apply, so the flip is backward-compatible.
    args.apply = not args.dry_run

    vault = resolve_vault_root(args.vault_path)
    if vault is None:
        print('ERROR: Could not resolve vault root.', file=sys.stderr)
        print('Pass --vault-path <path> with an absolute path to a vault containing vault/ + .tropo/.',
              file=sys.stderr)
        return 2

    # rebuild-vault --only <uid>: thin passthrough to rebuild-index --only — a single-entry
    # incremental freshen, skipping the full validate/rehydrate/relations orchestration (running
    # those would defeat the fast cockpit-reflect purpose). Argus A106 2026-06-09 (brief d7b3f1a9 §4).
    if args.only:
        only_cmd = [sys.executable, str(REBUILD_INDEX), '--vault-path', str(vault), '--only', args.only]
        return subprocess.run(only_cmd, stdin=subprocess.DEVNULL, timeout=60).returncode

    print('=' * 70)
    print('rebuild-vault.py — comprehensive substrate refresh (v1.15.1 wrapper; v1.30.0 Stream C-a)')
    print('Mode:', 'APPLY (writes will happen)' if args.apply else 'DRY-RUN (no writes)')
    print(f'Vault root: {vault}')
    print('Composes: tropo-validate.py (v1.30.0 pre-step) + rebuild-index.py + rehydrate.py + stale-cascade cleanup')
    print('=' * 70)

    # ---- Step 0: tropo-validate.py (v1.30.0 Stream C-a NEW pre-step) ----
    # B8 (v1.62): Validator runs BEFORE rebuild as a signal, NOT as a hard gate.
    # Prior behaviour: FAIL → exit 8, leaving the index stale (agents read old data).
    # Fixed behaviour: FAIL → surface prominently + continue rebuild so index is FRESH.
    # Rationale: an unrelated validation FAIL (e.g. party-UID registration gap) should not
    # freeze the index; booting agents are better served by a current index + a visible FAIL
    # than by a silent stale index. The FAIL is still surfaced as a non-zero exit at the end.
    print('\n[1/5] Running tropo-validate.py (v1.30.0 Stream C-a pre-step)...')
    _validator_failed = False
    if not TROPO_VALIDATE.exists():
        print(f'  WARNING: {TROPO_VALIDATE} not found; skipping validator pre-step.', file=sys.stderr)
    else:
        validate_cmd = [sys.executable, str(TROPO_VALIDATE), '--vault-path', str(vault)]
        try:
            validate_result = subprocess.run(
                validate_cmd, capture_output=True, text=True,
                stdin=subprocess.DEVNULL, cwd=str(vault), timeout=120
            )
        except subprocess.TimeoutExpired:
            print('  ✗ tropo-validate.py timed out after 120s; skipping validator (B8: continuing rebuild).',
                  file=sys.stderr)
            _validator_failed = True
        else:
            if validate_result.returncode == 0:
                summary_line = ''
                for line in validate_result.stdout.splitlines()[::-1]:
                    if line.startswith('Summary:'):
                        summary_line = line
                        break
                print(f'  ✓ tropo-validate.py PASSED ({summary_line or "all checks clean"})')
            elif validate_result.returncode == 1:
                # B8: surface FAIL but do NOT exit — proceed to rebuild so index stays fresh.
                tail = '\n'.join(validate_result.stdout.splitlines()[-30:])
                print(tail)
                print('\n  ⚠ tropo-validate.py FAILED — FAIL findings surfaced above.',
                      file=sys.stderr)
                print('  ⚠ B8 (v1.62): proceeding with rebuild to keep index current.',
                      file=sys.stderr)
                print('  ⚠ Resolve FAIL findings; do not ship against a broken substrate.',
                      file=sys.stderr)
                _validator_failed = True
            else:
                print(f'  ✗ tropo-validate.py exited {validate_result.returncode} (setup error); skipping.',
                      file=sys.stderr)
                if validate_result.stderr:
                    print('    ' + validate_result.stderr.strip().replace('\n', '\n    '), file=sys.stderr)
                _validator_failed = True

    # ---- Step 1: rebuild-index.py ----
    print('\n[2/5] Running rebuild-index.py...')
    # v1.30.0 Stream C-a composition fix per spec §3.2-a: pass --skip-rehydrate
    # because [3/5] below calls rehydrate.py explicitly. Without the flag, Stream B's
    # auto-invoke of rehydrate inside rebuild-index.py would cause double-rehydrate.
    rebuild_index_cmd = [sys.executable, str(REBUILD_INDEX),
                         '--vault-path', str(vault),
                         '--skip-rehydrate']
    if args.apply:
        rebuild_index_cmd.append('--apply')
    result = subprocess.run(rebuild_index_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)
    if result.stdout: print(result.stdout, end="")
    if result.returncode != 0:
        print(f'\nERROR: rebuild-index.py exited non-zero ({result.returncode}); aborting.', file=sys.stderr)
        if result.stderr: print(result.stderr, file=sys.stderr)
        return result.returncode

    # ---- Step 2: rehydrate.py ----
    print('\n[3/5] Running rehydrate.py...')
    if not REHYDRATE.exists():
        print(f'  WARNING: {REHYDRATE} not found; skipping rehydrate pass.', file=sys.stderr)
    else:
        rehydrate_cmd = [sys.executable, str(REHYDRATE), '00-tropo-nav']
        rehydrate_cmd.extend(['--vault-path', str(vault)])
        if args.apply:
            # rehydrate.py interface — pass-through; rehydrate may not support --apply,
            # in which case it always writes; that's OK for the comprehensive cadence.
            pass
        result = subprocess.run(rehydrate_cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=120)
        if result.returncode != 0:
            print(f'  WARNING: rehydrate.py exited non-zero ({result.returncode}); continuing.', file=sys.stderr)

    # ---- Step 3: stale-cascade cleanup ----
    print('\n[4/5] Stale-cascade cleanup...')
    ledger_dir = vault / 'vault'
    index_path = ledger_dir / '00-index.jsonl'
    valid_uids = load_index_uids(index_path)
    stale_cascades = find_stale_cascades(ledger_dir, valid_uids)
    print(f'Stale cascades (root UID gone from index): {len(stale_cascades)}')
    for c in stale_cascades[:10]:
        print(f'  would remove: {c.name}')
    if len(stale_cascades) > 10:
        print(f'  ... and {len(stale_cascades) - 10} more')

    if args.apply:
        for c in stale_cascades:
            c.unlink()
        if stale_cascades:
            print(f'Removed {len(stale_cascades)} stale cascade file(s).')

    # ---- Step 4: relations + members rendering (v1.15.2 Stream B) ----
    print('\n[5/5] Relations + Members rendering across vault/files/...')
    if not GENERATE_RELATIONS_HEADER.exists():
        print(f'  WARNING: {GENERATE_RELATIONS_HEADER} not found; skipping relations/members render.', file=sys.stderr)
    else:
        relations_cmd = [sys.executable, str(GENERATE_RELATIONS_HEADER),
                         str(vault / 'vault' / 'files'),
                         '--vault-root', str(vault)]
        if args.apply:
            relations_cmd.append('--write')
        # Suppress per-file stderr noise for batch run; keep summary
        result = subprocess.run(relations_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
        if result.returncode != 0:
            print(f'  WARNING: generate-relations-header.py exited non-zero ({result.returncode}); continuing.', file=sys.stderr)
            if result.stderr:
                # Print the last few lines so the failure is visible
                tail_lines = result.stderr.strip().split('\n')[-5:]
                for line in tail_lines:
                    print(f'    {line}', file=sys.stderr)
        else:
            # Summarize: count [updated] / [inserted] / [unchanged] / [skip] from stderr
            stderr_lines = result.stderr.split('\n')
            counts = {'updated': 0, 'inserted': 0, 'unchanged': 0, 'skip': 0, 'error': 0}
            for line in stderr_lines:
                for tag in counts:
                    if f'[{tag}]' in line:
                        counts[tag] += 1
                        break
            summary = ', '.join(f'{k}: {v}' for k, v in counts.items() if v > 0)
            print(f'  {summary}')

    # ─── Step 4 — Sidecar→Projection reconciliation (v1.25.0 Stream E addition) ───
    # If import-walker.py is present (v1.25.0+), invoke it to regenerate vault projections
    # from .tropo-studio/*.tropo.md sidecars. This composes the import-primitive substrate
    # into the comprehensive vault refresh: anyone deleting vault/files/<uid>.md projections
    # for imported user content gets them rebuilt byte-equivalent from the sidecars.
    # Per Import Primitive Architecture Specification v1.0 LOCKED [vault/files/2b49ba79.md] §A.10.
    import_walker_path = vault / '.tropo' / 'scripts' / 'import-walker.py'
    if import_walker_path.is_file():
        print('\n[5b/5] import-walker reconcile (regenerate sidecar projections)...')
        walker_cmd = ['python3', str(import_walker_path), 'reconcile']
        if args.apply:
            walker_cmd.extend(['--apply', '--write-journal'])
        else:
            walker_cmd.append('--dry-run')
        result = subprocess.run(walker_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
        if result.returncode != 0:
            print(f'  WARNING: import-walker.py exited non-zero ({result.returncode}); continuing.', file=sys.stderr)
            if result.stderr:
                tail_lines = result.stderr.strip().split('\n')[-5:]
                for line in tail_lines:
                    print(f'    {line}', file=sys.stderr)
        else:
            # Parse the JSON summary line for counts
            try:
                summary = json.loads(result.stdout)
                applied = summary.get('events_applied', 0)
                deferred = summary.get('events_deferred', 0)
                duration = summary.get('duration_ms', 0)
                print(f'  reconciler: {applied} applied, {deferred} deferred ({duration}ms)')
            except (ValueError, KeyError):
                print('  reconciler: completed (no summary parse)')
    # else: pre-v1.25.0 vault; skip silently — import primitive not installed.

    # ─── Step 5c — Board rendering (v1.35.0 addition per spec d2f8c194 Q26α) ───
    # Renders type:board-definition outputs from substrate to 00-tropo-nav/00-tropo-active/<slug>/board.md.
    # v1.35.0 minimal: renders projects with explicit status_board: c72f1a85 binding (kernel default).
    # v1.35.5 enrichment: full prose-query parser; multi-board rendering; custom board-definitions.
    # v1.56 tools-in-vault: render-boards migrated to vault/tools/81e168d6.py; legacy .tropo/scripts/ fallback. (Argus A96 2026-06-04 — stale path silently skipped this since v1.56.)
    boards_script_path = vault / 'vault' / 'tools' / '81e168d6.py'
    if not boards_script_path.is_file():
        boards_script_path = vault / '.tropo' / 'scripts' / 'render-boards.py'
    if boards_script_path.is_file():
        print('\n[5c/5] render-boards (v1.35.0 minimal board rendering)...')
        boards_cmd = ['python3', str(boards_script_path)]
        if args.apply:
            boards_cmd.append('--apply')
        result = subprocess.run(boards_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
        if result.returncode != 0:
            print(f'  WARNING: render-boards.py exited non-zero ({result.returncode}); continuing.', file=sys.stderr)
            if result.stderr:
                tail_lines = result.stderr.strip().split('\n')[-5:]
                for line in tail_lines:
                    print(f'    {line}', file=sys.stderr)
        else:
            # Surface output (small; usually 1-5 lines)
            for line in result.stdout.strip().split('\n')[:5]:
                print(f'  {line}')
    # else: pre-v1.35.0 vault; skip silently — board renderer not installed.

    # ─── Step 5d — subsystem-registry derivation (v1.50.0 addition; Argus A79) ───
    # Derives .tropo-studio/registries/subsystem-registry.jsonl from current shipped
    # release entries' capabilities_touched + member_of: 1-hop traversal. Closes the
    # 10-cycle TROPO_SKIP_ENFORCEMENT_GATE bypass pattern by making the substrate
    # self-derive every rebuild. Per registry.capsule v1.0 [55a57893] + subsystem-registry
    # wrapper [880a9e5a] + Mike-V50 Path B + Mike-A79 v1.50.0 cycle authorization.
    # v1.56 tools-in-vault: derive-subsystem-registry migrated to vault/tools/6342d0ca.py; legacy .tropo/scripts/ fallback. (Argus A96 2026-06-04 — the stale path silently skipped derivation since v1.56, leaving subsystem-registry.jsonl stale and refusing release builds at R11; surfaced by Vela V58's v1.64 build.)
    derive_subsys_path = vault / 'vault' / 'tools' / '6342d0ca.py'
    if not derive_subsys_path.is_file():
        derive_subsys_path = vault / '.tropo' / 'scripts' / 'derive-subsystem-registry.py'
    if derive_subsys_path.is_file():
        print('\n[5d/5] derive-subsystem-registry (v1.50.0 going-forward registry sync)...')
        derive_cmd = ['python3', str(derive_subsys_path), '--vault-root', str(vault)]
        if not args.apply:
            # No --dry-run shape on this deriver: it's idempotent regeneration.
            # Skip the write in dry-run mode by not invoking at all.
            print('  (skipped in dry-run mode; idempotent regeneration only runs with --apply)')
        else:
            result = subprocess.run(derive_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
            if result.returncode != 0:
                print(f'  WARNING: derive-subsystem-registry.py exited non-zero ({result.returncode}); continuing.', file=sys.stderr)
                if result.stderr:
                    tail_lines = result.stderr.strip().split('\n')[-5:]
                    for line in tail_lines:
                        print(f'    {line}', file=sys.stderr)
            else:
                for line in result.stdout.strip().split('\n')[-3:]:
                    print(f'  {line}')
    # else: pre-v1.50.0 vault; skip silently — registry primitive not installed.

    # ─── Step 5d — Crew brief rendering (v1.34.0+ addition per Mike-V46 directive 2026-05-16) ───
    # Renders Operating Crew + Dormant tables in 00-crew-brief.md from per-agent status cards.
    # Root-cause fix for crew-brief duplicate-source-of-truth drift: tables are derivable from
    # canonical status cards; hand-edits can't keep up with multi-roll-per-session generation
    # turnover. Same shape as render-boards.py (auto-render derivable content from substrate).
    # v1.56 tools-in-vault: render-crew-brief migrated to vault/tools/6510afc7.py; legacy .tropo/scripts/ fallback. (Argus A96 2026-06-04 — stale path silently skipped this since v1.56.)
    crew_brief_script_path = vault / 'vault' / 'tools' / '6510afc7.py'
    if not crew_brief_script_path.is_file():
        crew_brief_script_path = vault / '.tropo' / 'scripts' / 'render-crew-brief.py'
    if crew_brief_script_path.is_file():
        print('\n[5d/5] render-crew-brief (Operating Crew + Dormant tables from status cards)...')
        crew_brief_cmd = ['python3', str(crew_brief_script_path)]
        result = subprocess.run(crew_brief_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
        if result.returncode != 0:
            print(f'  WARNING: render-crew-brief.py exited non-zero ({result.returncode}); continuing.', file=sys.stderr)
            if result.stderr:
                tail_lines = result.stderr.strip().split('\n')[-5:]
                for line in tail_lines:
                    print(f'    {line}', file=sys.stderr)
        else:
            for line in result.stdout.strip().split('\n')[:5]:
                print(f'  {line}')
    # else: pre-v1.34.0 vault; skip silently — crew brief renderer not installed.

    # ─── Step 5f — Capability catalogs + toolbelt (v1.70.0 S3.4) ───
    generate_catalogs_path = vault / "vault" / "tools" / "d4e9a2c7.py"
    if generate_catalogs_path.is_file():
        print('\n[5f/5] generate-capability-catalogs (belt + 3 catalogs)...')
        catalogs_cmd = [sys.executable, str(generate_catalogs_path)]
        if args.apply:
            catalogs_cmd.append('--apply')
        result = subprocess.run(
            catalogs_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60
        )
        if result.returncode != 0:
            print(f'  ERROR: generate-capability-catalogs.py exited {result.returncode}; aborting.', file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return result.returncode
        else:
            for line in result.stdout.strip().split('\n')[-8:]:
                print(f'  {line}')

    if args.apply:
        print('\n=== Comprehensive refresh complete ===')
        print('Next: run `python3 .tropo/scripts/tropo-validate.py` to confirm structural invariants hold.')
        # C.1 — Stream C auto-emission: tropo.substrate.modified summary (v1.58)
        try:
            _vr = Path(__file__).resolve().parents[2]
            _sp = _vr / ".tropo" / "scripts"
            if str(_sp) not in sys.path:
                sys.path.insert(0, str(_sp))
            from lib.event_emitter import auto_emit
            auto_emit("tropo.substrate.modified", "/tools/rebuild-vault", "123e12e7",
                      lifecycle="ephemeral",
                      data={"op": "rebuild-vault", "vault_root": str(vault)})
        except Exception:
            pass
    else:
        print('\nDRY-RUN complete (--dry-run passed; no writes). Re-run WITHOUT --dry-run to write — APPLY is the default.')

    # B8 (v1.62): exit non-zero if validator failed so callers (CI, build-release) can detect it.
    # The rebuild itself completed — the index is fresh — but the substrate has known FAILs.
    if _validator_failed:
        print('\nWARN: rebuild completed but tropo-validate.py reported FAIL findings (see above).',
              file=sys.stderr)
        print('WARN: do not ship against a substrate with active FAIL findings.', file=sys.stderr)
        return 8

    return 0


if __name__ == '__main__':
    sys.exit(main())
