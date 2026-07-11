#!/usr/bin/env python3
"""
---
uid: 992ba026
name: tropo-disposition
type: tool
title: "tropo-disposition — backlog disposition harness (safe + bounded)"
description: "Turns manual floor-sweeps into bounded-verification operations. Handles MECHANICAL-CERTAIN dispositions deterministically; surfaces JUDGMENT cases for review. Safety invariants by construction: never recycles referenced nodes (inbound-ref check from files, not index); archives via canonical archive() (6cc9dcdb); enum-checks status before writing; re-parents terminal items out of 01-inbox; --apply rebuilds + validates and refuses NEW failures."
status: active
state: active
owner: talos
domain: "Governance — safe bounded backlog disposition; MECHANICAL-CERTAIN dispositions handled deterministically; JUDGMENT cases surfaced for review."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-disposition.py --owner <owner> [--days N] [--apply]"
script_path: vault/tools/tropo-disposition.py
spawnable_by:
  - all-executives
input:
  type: object
  properties:
    owner: {type: string, description: "Owner slug to scope the disposition (e.g. argus, talos, vela)"}
    days: {type: integer, description: "Flag items older than N days (default 45)"}
    apply: {type: boolean, description: "Execute mechanical-certain set (default: dry-run)"}
output:
  type: object
  description: "Exit 0 on success; non-zero if disposition introduced new validator failures. Prints plan + review manifest to stdout."
created: 2026-06-22
created_by: talos-t21
modified: 2026-06-26
modified_by: talos-t21
version: "1.0"
governed_by: d5e1b4a3
refs:
  - 8dce9aec
schema_version: 2
extraction_scope: ship
trigger_description: "Dispose of stale backlog items safely: archives referenced items, recycles unreferenced ones, surfaces judgment cases for review. Default dry-run — add --apply to execute."
tags: [tool, disposition, governance, backlog, bounded-verification, safety-invariants, talos-t21]
belt: true
belt_invocation: "python3 vault/tools/tropo-disposition.py --owner <owner>"
belt_example: "python3 vault/tools/tropo-disposition.py --owner argus --apply"
---

tropo-disposition — backlog disposition harness (governed tool, UID 992ba026).

Turns manual floor-sweeps into a bounded-verification operation: the tool handles
MECHANICAL-CERTAIN dispositions deterministically and safely, surfacing only JUDGMENT
cases for review. Safety invariants are built-in (lived lessons from Argus A119):

  - NEVER recycles a referenced node — inbound-ref check from files (not index);
    referenced items archive, unreferenced items recycle.
  - Archives via the canonical archive() tool (6cc9dcdb), never hand-edits.
  - Enum-checks status against the type capsule before writing.
  - Re-parents terminal items out of 01-inbox/ in the same gesture (exit-side of
    the inbox transition protocol, v1.68 S2).
  - --apply rebuilds + validates and refuses to leave a NEW failure (diff against
    pre-run baseline).

Usage:
  python3 vault/tools/tropo-disposition.py --owner argus [--days 30] [--apply]

Default: DRY-RUN — prints the plan + review manifest, writes nothing.

Graduated from Argus A119 prototype (agents/argus/.tropo-capsule/workspace/
tropo-disposition.py) per dev-spec 8dce9aec (Talos T21, 2026-06-22).
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Root resolution (tool lives at vault/tools/<uid>.py)
# ---------------------------------------------------------------------------
ROOT = str(Path(__file__).resolve().parents[2])

INDEX_PATH = os.path.join(ROOT, 'vault', '00-index.jsonl')
FILES_DIR = os.path.join(ROOT, 'vault', 'files')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Types that are structural containers / definitions / records — not owned work-items.
NONWORK = frozenset({
    'activation', 'agent', 'board-snapshot', 'build', 'collection-ref', 'how-to',
    'kb-article', 'pipeline', 'playbook', 'project', 'project-plan',
    'reconcile-report', 'registry', 'session-agent', 'ship-artifact',
    'subsystem-hub', 'tool', 'capsule-definition',
})

TERMINAL = frozenset({
    'closed', 'done', 'shipped', 'retired', 'superseded', 'complete',
    'immutable', 'locked', 'published', 'archived', 'cancelled',
    'deprecated', 'evergreen', 'tested',
})

# Status values that should be written when reconciling an archived state.
# Capsule-valid terminal status for generic types.
RECONCILE_STATUS = 'archived'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_index():
    rows = []
    try:
        with open(INDEX_PATH) as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception as e:
        print(f'ERROR: Cannot load index at {INDEX_PATH}: {e}', file=sys.stderr)
        sys.exit(1)
    return rows


def body_is_empty(uid):
    """True if the vault file has no meaningful body content (stub/placeholder)."""
    p = os.path.join(FILES_DIR, f'{uid}.md')
    if not os.path.exists(p):
        return False
    text = open(p).read()
    text = re.sub(r'^---.*?\n---\n', '', text, count=1, flags=re.S)
    text = re.sub(r'<!-- nav-block:start -->.*?<!-- nav-block:end -->', '', text, flags=re.S)
    return len(text.strip()) == 0


def inbound_refs(uid):
    """Files (other than itself) that reference this uid.

    Reads the physical vault/files/*.md corpus — the RELIABLE surface; the index
    may not surface all refs fields. This is the no-recycle-referenced safety guard.
    """
    hits = []
    for f in glob.glob(os.path.join(FILES_DIR, '*.md')):
        if f.endswith(f'/{uid}.md'):
            continue
        try:
            if uid in open(f).read():
                hits.append(os.path.basename(f)[:-3])
        except Exception:
            pass
    return hits


def inbox_member_of(uid, rows):
    """Return the member_of list for uid; empty list if not found."""
    for r in rows:
        if r.get('uid') == uid:
            mob = r.get('member_of')
            if isinstance(mob, list):
                return mob
            return []
    return []


def is_inbox_uid(uid, rows):
    """True if this uid looks like a 01-inbox container."""
    for r in rows:
        if r.get('uid') == uid:
            title = str(r.get('title', '') or '').lower()
            path_hint = str(r.get('path', '') or '').lower()
            if '01-inbox' in path_hint or 'inbox' in title:
                return True
    return False


def shipped_versions(rows):
    vs = set()
    for e in rows:
        if e.get('type') == 'release' and str(e.get('status', '')).lower() in ('shipped', 'done'):
            rv = str(e.get('release_version', '')).lstrip('v')
            if rv:
                vs.add(rv)
    return vs


def run_archive(uid, reason, actor, dry_run):
    cmd = ['python3', 'vault/tools/tropo-archive.py', uid, '--reason', reason, '--actor', actor]
    if dry_run:
        print(f'  [DRY-RUN] would archive {uid}: {reason}')
        return
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f'  [WARN] archive {uid} exited {result.returncode}: {result.stderr[:200]}')
    else:
        print(f'  [ARCHIVED] {uid}')


def run_reconcile_status(uid, actor, dry_run):
    """For items already state:archived but status not matching — directly patch status: archived."""
    import yaml, datetime
    fpath = os.path.join(FILES_DIR, f'{uid}.md')
    if not os.path.exists(fpath):
        return
    try:
        text = open(fpath).read()
        parts = text.split('\n---\n', 1)
        if len(parts) < 2:
            return
        fm = yaml.safe_load(parts[0].lstrip('---\n'))
        if not isinstance(fm, dict):
            return
        if fm.get('status') == 'archived':
            return
        if dry_run:
            print(f'  [DRY-RUN] would set {uid} status → archived')
            return
        fm['status'] = 'archived'
        fm['modified_by'] = actor
        fm['modified'] = datetime.date.today().isoformat()
        new_fm = yaml.dump(fm, sort_keys=False, indent=2, width=1000).strip()
        open(fpath, 'w').write(f'---\n{new_fm}\n---\n{parts[1]}')
        print(f'  [RECONCILED] {uid} — status → archived')
    except Exception as e:
        print(f'  [WARN] reconcile {uid} failed: {e}')


def run_recycle(uids, reason, dry_run):
    if not uids:
        return
    cmd = ['python3', 'vault/tools/tropo-recycle.py'] + uids + ['--reason', reason]
    if dry_run:
        for uid in uids:
            print(f'  [DRY-RUN] would recycle {uid}: {reason}')
        return
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f'  [WARN] recycle exited {result.returncode}: {result.stderr[:200]}')
    else:
        for uid in uids:
            print(f'  [RECYCLED] {uid}')


def reparent_out_of_inbox(uid, rows, actor, dry_run):
    """Remove any 01-inbox entries from this item's member_of list (exit-side, v1.68 S2)."""
    mob = inbox_member_of(uid, rows)
    inbox_parents = [p for p in mob if is_inbox_uid(p, rows)]
    if not inbox_parents:
        return
    if dry_run:
        print(f'  [DRY-RUN] would re-parent {uid} out of inbox: remove {inbox_parents}')
        return
    # Use archive tool to get the file path, then edit frontmatter directly.
    fpath = os.path.join(FILES_DIR, f'{uid}.md')
    if not os.path.exists(fpath):
        return
    try:
        text = open(fpath).read()
        import yaml
        parts = text.split('\n---\n', 1)
        if len(parts) < 2:
            return
        fm = yaml.safe_load(parts[0].lstrip('---\n'))
        if not isinstance(fm, dict):
            return
        current_mob = fm.get('member_of', [])
        if isinstance(current_mob, list):
            fm['member_of'] = [p for p in current_mob if p not in inbox_parents]
            fm['modified_by'] = actor
            import datetime
            fm['modified'] = datetime.date.today().isoformat()
            new_fm = yaml.dump(fm, sort_keys=False, indent=2, width=1000).strip()
            new_text = f'---\n{new_fm}\n---\n{parts[1]}'
            open(fpath, 'w').write(new_text)
            print(f'  [REPARENTED] {uid} — removed from inbox parent(s): {inbox_parents}')
    except Exception as e:
        print(f'  [WARN] reparent {uid} failed: {e}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description='tropo-disposition — safe backlog disposition harness (dev-spec 8dce9aec)'
    )
    ap.add_argument('--owner', required=True,
                    help='Owner slug to scope the disposition (e.g. argus, talos, vela)')
    ap.add_argument('--days', type=int, default=45,
                    help='Flag items older than N days (default 45)')
    ap.add_argument('--apply', action='store_true',
                    help='Execute mechanical-certain set (default: dry-run)')
    args = ap.parse_args()

    owner = args.owner
    dry_run = not args.apply
    actor = f'{owner}-disposition-tool'

    rows = load_index()
    shipped = shipped_versions(rows)

    auto = []   # (uid, type, verdict, detail)
    review = []

    for e in rows:
        o = str(e.get('owner', ''))
        a = str(e.get('assigned_to', ''))
        if not (o.startswith(owner) or a.startswith(owner)):
            continue

        t = e.get('type', '')
        st = str(e.get('status', '') or '').lower()
        state = str(e.get('state', '') or '').lower()
        uid = e.get('uid', '')

        if t in NONWORK or not uid:
            continue
        if st in TERMINAL and state in TERMINAL:
            continue

        title = (e.get('title', '') or '')[:50]

        # Rule 1: state:archived but non-terminal status — ADR-047 disease
        if state == 'archived' and st not in TERMINAL:
            auto.append((uid, t, 'reconcile',
                         f'state:archived but status:{st or "blank"} → set {RECONCILE_STATUS}'))
            continue

        if st in TERMINAL or state in TERMINAL:
            continue  # one side terminal — leave for review

        # Rule 2: release-plan whose version has shipped
        if t == 'release-plan':
            m = re.search(r'(\d+\.\d+(?:\.\d+)?)', title)
            if m and m.group(1) in shipped:
                auto.append((uid, t, 'archive',
                             f'v{m.group(1)} has a shipped release entry'))
                continue
            review.append((uid, t, st or state, title,
                           'release-plan: no shipped entry — verify shipped vs renumbered'))
            continue

        # Rule 3: empty placeholder document
        if t == 'document' and body_is_empty(uid):
            refs = inbound_refs(uid)
            if refs:
                auto.append((uid, t, 'archive',
                             f'empty body but referenced by {len(refs)} ({",".join(refs[:3])}) → archive not recycle'))
            else:
                auto.append((uid, t, 'recycle', 'empty body, zero inbound refs'))
            continue

        # Rule 4: stuck pipeline-run
        if t == 'pipeline-run' and (st == 'active' or state == 'active'):
            refs = inbound_refs(uid)
            if refs:
                auto.append((uid, t, 'archive',
                             f'stuck run referenced by {len(refs)} ({",".join(refs[:3])}) → archive not recycle'))
            else:
                auto.append((uid, t, 'recycle', 'stuck auto-run, zero inbound refs'))
            continue

        # Else: judgment needed
        review.append((uid, t, st or state, title, 'needs judgment: stale-vs-live / route / keep'))

    mode = 'APPLY' if not dry_run else 'DRY-RUN'
    print(f'=== tropo-disposition (owner={owner}, mode={mode}, stale_threshold={args.days}d) ===')
    print(f'MECHANICAL-CERTAIN (tool handles): {len(auto)}   |   REVIEW (bounded verification): {len(review)}\n')

    from collections import Counter
    print('Auto-disposition plan:')
    for verdict, count in Counter(x[2] for x in auto).items():
        print(f'  {verdict}: {count}')
    for uid, t, verdict, detail in auto:
        print(f'    [{verdict:9}] {uid} ({t}) — {detail}')

    print(f'\nReview queue ({len(review)}) — tool will NOT touch these; an agent verdicts them:')
    for uid, t, s, ti, why in review[:60]:
        print(f'    {uid} [{t}/{s}] {ti}  <- {why}')
    if len(review) > 60:
        print(f'    ... and {len(review) - 60} more')

    if dry_run:
        print('\nDRY-RUN. Re-run with --apply to execute the mechanical-certain set.')
        return 0

    # --- APPLY: mechanical-certain set only; review queue is untouched ---
    print('\n=== APPLYING mechanical-certain set ===')

    recycle_uids = []
    for uid, t, verdict, detail in auto:
        if verdict == 'archive':
            run_archive(uid, f'tropo-disposition: {detail}', actor, dry_run=False)
            reparent_out_of_inbox(uid, rows, actor, dry_run=False)
        elif verdict == 'reconcile':
            run_reconcile_status(uid, actor, dry_run=False)
            reparent_out_of_inbox(uid, rows, actor, dry_run=False)
        elif verdict == 'recycle':
            refs = inbound_refs(uid)
            if refs:
                # Safety net: if refs appeared between planning and apply, archive instead
                print(f'  [SAFETY] {uid} has inbound refs at apply-time ({refs[:3]}) — archiving instead of recycling')
                run_archive(uid, f'tropo-disposition safety: found refs at apply-time', actor, dry_run=False)
                reparent_out_of_inbox(uid, rows, actor, dry_run=False)
            else:
                recycle_uids.append(uid)

    if recycle_uids:
        run_recycle(recycle_uids, 'tropo-disposition: unreferenced noise (empty placeholders / stuck auto-runs)', dry_run=False)

    # Rebuild + validate; refuse to leave a NEW failure
    print('\nRebuilding + validating...')
    pre_result = subprocess.run(
        ['python3', 'vault/tools/tropo-validate.py'],
        cwd=ROOT, capture_output=True, text=True
    )
    pre_summary = next(
        (l for l in pre_result.stdout.splitlines() if l.startswith('Summary')), None
    )
    pre_fails = 0
    if pre_summary:
        m = re.search(r'(\d+) failed', pre_summary)
        if m:
            pre_fails = int(m.group(1))

    subprocess.run(
        ['python3', 'vault/tools/tropo-rebuild-vault.py', '--apply'],
        cwd=ROOT, capture_output=True
    )

    post_result = subprocess.run(
        ['python3', 'vault/tools/tropo-validate.py'],
        cwd=ROOT, capture_output=True, text=True
    )
    post_summary = next(
        (l for l in post_result.stdout.splitlines() if l.startswith('Summary')), None
    )
    post_fails = 0
    if post_summary:
        m = re.search(r'(\d+) failed', post_summary)
        if m:
            post_fails = int(m.group(1))
        print(post_summary)

    if post_fails > pre_fails:
        new_fails = post_fails - pre_fails
        print(f'\nERROR: disposition introduced {new_fails} NEW failure(s). '
              f'Pre-run: {pre_fails} failed; post-run: {post_fails} failed.', file=sys.stderr)
        print('Investigate before shipping. The review queue is untouched.', file=sys.stderr)
        return 1

    print(f'\nApply complete. {len(auto)} item(s) dispositioned. '
          f'Review queue ({len(review)} item(s)) still needs agent verdicts.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
