#!/usr/bin/env python3
"""tropo-studio-status — the deterministic orientation package (studio-ops v2.0).

Design brief: vault/files/756a70a9.md (Mike-ruled 2026-08-29/30; Metis review folded).
v0.2 — Argus A163 peer-review cures F1-F10 (evt_b51c083be28ac6fe_00000300), all ten.
v0.3 — metis-g119 2026-09-04, Mike-directed: the board section prints counts by
       default (--board full for the item list); the broadcast fires only when a
       NEW identity enters the attention set (an item leaving is not attention);
       the board line names its population so its number is the boot number.

One argument-free call at every agent boot. Files-only deterministic core: same
files, same answer, any machine, any harness — ordering is CONTENT-based
everywhere (no mtimes, no file order; union-merged files have no order).
Reads vault/studio-ops/roster.json + log.jsonl. Report and fail loudly; NEVER
act. On a changed attention-set the tool itself emits the warning broadcast
(deduped by identities+bucket — never durations) and appends its own
status_check line. The stale_key advances ONLY when the emit actually reached
the bus. Empty substrate is FATAL — silence is never all-clear.

Exit 0 = report delivered. Exit 1 = the tool could not compute (loud failure).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OPS = os.path.join(ROOT, 'vault', 'studio-ops')
ROSTER = os.path.join(OPS, 'roster.json')
LOG = os.path.join(OPS, 'log.jsonl')
TOOL_UID = 'c1a4f2e0'

NOW = dt.datetime.now(dt.timezone.utc)
# F10: deterministic tie-break — completion outranks failure outranks holds;
# alphabetic within a tie is arbitrary but STABLE, which is the contract
EVENT_PRIORITY = {'run_complete': 0, 'run_failed': 1, 'held': 2, 'dispatched': 3}


def read_jsonl(path):
    rows, bad = [], 0
    if os.path.exists(path):
        with open(path) as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rows.append(json.loads(ln))
                except json.JSONDecodeError:
                    bad += 1
    return rows, bad


def parse_at(s):
    """F3: normalize EVERYTHING to tz-aware UTC; never raise; None if hopeless.
    Date-only stamps get +24h (conservative: the event could be any time that
    day) — ruled a design convention, not a defect (peer-review F10 ruling);
    a future-effective stamp (today, date-precision) is clamped by callers."""
    s = str(s or '')
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        d = dt.datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc)
        return d + dt.timedelta(hours=24), 'date'
    try:
        t = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None, 'bad'
    if t.tzinfo is None:  # the obvious idiom (datetime.now().isoformat()) must not kill boots
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.astimezone(dt.timezone.utc), 'ts'


def last_event_per_runner(rows):
    """F10: resolve by (timestamp, event-priority) — never file order, never
    first-seen-wins on ties."""
    last = {}
    for ev in rows:
        r = ev.get('runner')
        if not r:
            continue
        t, prec = parse_at(ev.get('at'))
        if t is None:
            continue
        rank = (t, -EVENT_PRIORITY.get(ev.get('event'), 9))
        if r not in last or rank > last[r][0]:
            last[r] = (rank, t, ev, prec)
    return last


def since(t, now):
    d = (now - t).total_seconds() / 3600
    if d < 0:
        return 'today (date precision)'
    return ('%dh ago' % round(d)) if d < 48 else ('%.0fd ago' % (d / 24))


def last_monday(now):
    m = now - dt.timedelta(days=now.weekday())
    return m.replace(hour=0, minute=0, second=0, microsecond=0)


def bucket_for(item, last, now):
    """F2/F6/F8: completion is run_complete ONLY. run_failed = failing (attention).
    dispatched-without-completion = in-flight. held and never-run enter the
    attention set — the two quietest states are the ones Mike most needs to see."""
    runner = item['runner']
    if runner not in last:
        return 'never-run', 'no run event in the studio log'
    _, t, ev, prec = last[runner]
    kind = ev.get('event')
    if kind == 'held':
        return 'held', 'held: %s (%s)' % (ev.get('reason', 'no reason recorded), ').rstrip(', )'), since(t, now))
    if kind == 'run_failed':
        return 'failing', 'last run FAILED %s: %s' % (since(t, now), str(ev.get('result', ''))[:60])
    if kind == 'dispatched':
        age_h = (now - t).total_seconds() / 3600
        return ('in-flight', 'dispatched %.0fh ago, no completion recorded' % age_h) if age_h < 24 \
            else ('failing', 'dispatched %.0fh ago and never completed' % age_h)
    if kind != 'run_complete':
        return 'never-run', 'unrecognized last event %r' % kind
    cad = item.get('cadence', 'daily')
    age_h = (now - t).total_seconds() / 3600
    if cad == 'weekly-monday':  # F8: real Monday semantics, not a weekly alias
        mon = last_monday(now)
        if t >= mon:
            return 'fresh', since(t, now)
        return 'overdue', 'due since Monday 00:00Z (last run %s)' % since(t, now)
    window_h = 24 if cad == 'daily' else 168
    if age_h > window_h:
        # F5: the OVERDUE AMOUNT, not the age
        return 'overdue', '%.1fh overdue' % (age_h - window_h)
    return 'fresh', since(t, now)


def section_ops(roster, rows, bad_lines):
    last = last_event_per_runner(rows)
    lines, attention = [], []
    marks = {'fresh': 'ok     ', 'overdue': 'STALE  ', 'held': 'HELD   ',
             'failing': 'FAILING', 'never-run': 'NEW    ', 'in-flight': 'FLIGHT '}
    for item in roster['items']:
        bucket, detail = bucket_for(item, last, NOW)
        lines.append('  [%s] %-24s %-14s %s' % (marks[bucket], item['runner'], item.get('cadence', ''), detail))
        if bucket in ('overdue', 'failing', 'held', 'never-run'):
            attention.append((item['runner'], bucket))
    if bad_lines:
        lines.append('  [WARN  ] %d unparseable log line(s) skipped (stated, not guessed)' % bad_lines)
    checks = [e for e in rows if e.get('runner') == 'tropo-studio-status' and e.get('event') == 'status_check']
    hdr = 'never (first run)'
    if checks:
        t, _ = parse_at(checks[-1].get('at'))
        if t is not None:
            hdr = since(t, NOW)
    return ('last status check: %s' % hdr), lines, attention, last


def frontmatter(path):
    try:
        text = open(path).read()
    except OSError:
        return {}
    m = re.match(r'^---\n(.*?)\n---', text, re.S)
    out = {}
    if m:
        for ln in m.group(1).split('\n'):
            mm = re.match(r'^([a-z_0-9]+):\s*(.*)$', ln)
            if mm:
                out[mm.group(1)] = mm.group(2).strip().strip("'\"")
    return out


def section_crew():
    lines = []
    home = os.path.join(ROOT, 'agents')
    for name in sorted(os.listdir(home)):
        lj = os.path.join(home, name, 'lineage.jsonl')
        if not os.path.exists(lj):
            continue
        born = retired = None  # (sort_key, idx, event)
        with open(lj) as f:
            for idx, ln in enumerate(f):
                try:
                    e = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if e.get('t') not in ('born', 'retired'):
                    continue
                t, _ = parse_at(e.get('at'))
                key = (t or dt.datetime.min.replace(tzinfo=dt.timezone.utc), idx)  # timestamp first, file order as fallback
                if e.get('t') == 'born':
                    if born is None or key > born[0]:
                        born = (key, e)
                else:
                    if retired is None or key > retired[0]:
                        retired = (key, e)
        # timestamps decide; on a tie the retirement wins (backfilled lineage
        # stamps born and retired with the same date); file order is the
        # fallback only when timestamps are absent
        EPOCH = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        r_key, b_key = retired[0] if retired else None, born[0] if born else None
        retired_wins = retired and (
            born is None
            or r_key >= b_key  # tuple compare: timestamp, then idx (born precedes retired in normal files)
            or (r_key[0] == EPOCH and b_key[0] == EPOCH and r_key[1] > b_key[1])
        )
        if retired_wins:
            lines.append('  %-10s %-8s RETIRED  %s' % (name, '', ''))
        elif born:
            lines.append('  %-10s %-8s ACTIVE   %s' % (name, born[1].get('gen', ''), str(born[1].get('model', ''))[:20]))
    return 'crew on deck (lineage truth, timestamp-resolved)', lines


def section_git():
    def g(*a):
        return subprocess.run(['git', '-C', ROOT] + list(a), capture_output=True, text=True).stdout.strip()
    head = g('rev-parse', '--short', 'HEAD') or '?'
    origin = g('rev-parse', '--short', 'origin/main') or '?'
    behind = g('rev-list', '--count', 'HEAD..origin/main') or '0'
    ahead = g('rev-list', '--count', 'origin/main..HEAD') or '0'
    subj = g('log', '-1', '--format=%s')[:80]
    lines = [
        '  HEAD %s | origin/main %s | ahead %s / behind %s (as of last fetch — core makes no network calls)' % (head, origin, ahead, behind),
        '  last commit: %s' % subj,
    ]
    return 'git state (local vs origin at last fetch)', lines


# Work-shaped types an agent actually drives. Deliberately excludes 'pipeline'
# (that type is pipeline-class STEP/STAGE DEFINITIONS — structural template
# entries, not live work; 89 of them read as "89 active pipelines" when the
# live-instance type is 'pipeline-run') and 'loop' (schedule infrastructure,
# reported separately in the studio-ops schedule-state section above).
WORK_TYPES = ('task', 'design-brief', 'dev-spec', 'decision', 'design-spec',
              'test-spec', 'pipeline-run', 'release-plan', 'arch-spec')

# Terminal statuses, observed across every WORK_TYPES vocabulary in the live
# index (2026-09-02 survey). An item in one of these is closed/archived/done
# by definition, regardless of which type-specific word it uses.
CLOSED_STATUSES = {'done', 'closed', 'archived', 'cancelled', 'complete'}


def _owner_slug(raw):
    """Normalize an owner/assigned_to value to a bare agent slug for matching.
    'argus-a123' -> 'argus', 'mike-maziarz' -> 'mike', 'vela' -> 'vela'.
    A bare UID (no letters before the first '-', or no '-' at all and not a
    known word) simply won't match any agent and that's correct — it's
    genuinely unattributed, not a false negative to paper over."""
    if not raw:
        return None
    return str(raw).strip().lower().split('-')[0]


def section_work(as_agent=None, board='counts'):
    idx = os.path.join(ROOT, 'vault', '00-index.jsonl')
    if not os.path.exists(idx):
        return 'work management — ABSENT', ['  vault/00-index.jsonl not built on this machine (derived projection; run rebuild) — stated, not guessed']

    if as_agent:
        who = as_agent.strip().lower()
        counts = {}
        open_items = []
        with open(idx) as fh:
            idx_lines = fh.readlines()
        for ln in idx_lines:
            try:
                e = json.loads(ln)
            except json.JSONDecodeError:
                continue
            t = e.get('type')
            if t not in WORK_TYPES:
                continue
            mine = _owner_slug(e.get('owner')) == who or _owner_slug(e.get('assigned_to')) == who
            if not mine:
                continue
            st = e.get('status') or e.get('state') or '?'
            if st in CLOSED_STATUSES:
                continue
            k = '%s/%s' % (t, st)
            counts[k] = counts.get(k, 0) + 1
            open_items.append((t, st, e.get('uid'), (e.get('title') or '')[:60]))
        # v0.3: the first line is THE boot number and names its population, so
        # no second instrument with a different denominator competes with it.
        lines = ['  %d open work item(s) — the boot number (work types: %s; documents, notes and pipeline definitions are not work items and are not counted)'
                 % (len(open_items), ', '.join(WORK_TYPES))]
        lines += ['  %s: %d' % (k, v) for k, v in sorted(counts.items())]
        if not open_items:
            lines.append('  (nothing open owned by or assigned to %s)' % who)
        elif board == 'full':
            lines.append('  --- open items ---')
            for t, st, uid, title in sorted(open_items):
                lines.append('  [%s/%s] %s — %s' % (t, st, uid, title))
        else:
            lines.append('  (item list withheld at boot; --board full prints it; the rendered board lives at boards/%s/)' % who)
        lines.append('  (owner/assigned_to == %s, open statuses only, excludes %s; derived per-machine index — state assertions read source)'
                      % (who, '/'.join(sorted(CLOSED_STATUSES))))
        return 'your work board (%s)' % who, lines

    # No --as given: studio-wide fallback, unchanged legacy shape (kept for
    # any caller that hasn't been updated to pass --as yet).
    counts = {}
    with open(idx) as fh:
        idx_lines = fh.readlines()
    for ln in idx_lines:
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        t = e.get('type')
        if t in ('task', 'design-brief', 'pipeline', 'loop'):
            k = '%s/%s' % (t, e.get('status', e.get('state', '?')))
            counts[k] = counts.get(k, 0) + 1
    lines = ['  %s: %d' % (k, v) for k, v in sorted(counts.items())]
    lines.append('  (studio-wide, no --as given; pass --as <agent> for your own open-items board — derived per-machine index; FIND-grade for discovery)')
    return 'work management (counts by type/status, studio-wide)', lines


GENESIS_CURE = 'python3 vault/tools/tropo-rebuild-index.py --apply --vault-path .'


def section_identity(root=None):
    """v1.95 Spine A AC2(b) (f015de6b3a18): ONE [WARN] line naming the cure when
    the studio-identity manifest is absent or malformed; nothing when present.
    Mike's premise at the walk was that every boot already ran this script and
    would see the identity; neither boot path invoked it (activate.md: zero
    hits; the playbook: one prose mention). Both paths now carry a numbered
    step that runs it (activate.md 0d; 99341618 Step 0.0d). The reader is the
    mint tool's own — one definition of "well-formed manifest"."""
    root = root or ROOT
    lines = []
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            '_tropo_mint_id_for_status', os.path.join(root, 'vault', 'tools', 'tropo-mint-id.py'))
        _mint = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mint)
    except Exception as exc:  # noqa: BLE001 — the reader itself could not load
        lines.append('  [WARN] studio identity: could not load the manifest reader (%s: %s)'
                     % (type(exc).__name__, exc))
        return ('studio identity', lines)
    try:
        _mint.read_studio_identity(__import__('pathlib').Path(root))
    except _mint.StudioIdentityError as exc:
        lines.append('  [WARN] studio identity: %s' % exc)
        lines.append('         cure: %s  (first-boot genesis mints .tropo/studio-identity.md and the '
                     'starter vault-entity; Po runs it at her first greeting — ask her by name)'
                     % GENESIS_CURE)
    except Exception as exc:  # noqa: BLE001
        lines.append('  [WARN] studio identity: reader failed (%s: %s)' % (type(exc).__name__, exc))
    return ('studio identity', lines)


def section_meta():
    lines = []
    vpath = os.path.join(ROOT, '.tropo', 'version.md')
    v = open(vpath).read().strip() if os.path.exists(vpath) else '?'
    lines.append('  studio version: %s' % v)
    pend = os.path.join(ROOT, 'vault', 'updates', 'pending')
    real = [f for f in os.listdir(pend) if not f.startswith('.')] if os.path.isdir(pend) else []
    lines.append('  pending updates: %d' % len(real))
    pp = os.path.join(ROOT, '.tropo', 'publish-pending.json')
    if os.path.exists(pp):
        d = json.load(open(pp))
        lines.append('  publish marker: %s %s (%s)' % (d.get('version'), d.get('publish_state'), 'quiet' if d.get('publish_state') in ('live', 'deferred-by-mike') else 'ATTENTION'))
    # Boot-derivation freshness. argus-a167, 2026-09-02.
    #
    # The established-agent fast-path tells every booting agent to SKIP the full
    # Tier 1 + Tier 2 reads "when the gate is green -- the validator's last run
    # is the signal". Nothing at boot read that signal. Agents were deciding
    # whether to skip two reads on the strength of a check nobody ran; the only
    # way to see it was to hand-import the validator, which is what argus-a167
    # did at his own Group 0 rather than trust the instruction.
    #
    # A declared primitive with no caller, sitting inside the boot contract that
    # names it. Surfaced independently by talos-t60 at his own boot the same day,
    # who proposed exactly this row. One line, in the tool agents already run at
    # Group 3, so the signal the contract cites actually exists.
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            '_tv', os.path.join(ROOT, 'vault', 'tools', 'tropo-validate.py'))
        _tv = _ilu.module_from_spec(_spec)
        import sys as _sys
        _sys.path.insert(0, os.path.join(ROOT, 'vault', 'tools'))
        _spec.loader.exec_module(_tv)
        import pathlib as _pl
        _f, _checked, _defects = _tv.check_boot_derivation_fresh(_pl.Path(ROOT))
        if _defects:
            lines.append('  boot derivations: %d/%d DRIFTED -- fall back to the FULL Tier 1 + Tier 2 reads' % (_defects, _checked))
            for _line in _f[:3]:
                lines.append('    %s' % _line[:150])
        else:
            lines.append('  boot derivations: %d/%d fresh (fast-path skip of Tier 1+2 is legitimate)' % (_checked, _checked))
    except Exception as _e:
        # Never fail the status run on this. An unreadable gate is reported as
        # unknown, not as green -- silence here would recreate the defect.
        lines.append('  boot derivations: UNKNOWN (%s) -- treat as RED, do the full reads' % type(_e).__name__)

    return 'studio metadata', lines


def section_bus():
    """F1: content ordering only. Scan every stream file's tail for broadcast
    lines, rank by event time (content), take 5. No mtimes anywhere."""
    found = []
    sdir = os.path.join(ROOT, 'vault', 'events', 'streams')
    for fname in os.listdir(sdir):
        fp = os.path.join(sdir, fname)
        try:
            with open(fp) as f:
                tail = f.readlines()[-50:]
        except OSError:
            continue
        for ln in tail:
            if '"tropo.broadcast.crew"' in ln:
                try:
                    e = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                found.append((e.get('time', ''), e.get('data', {}).get('headline') or ''))
    found.sort(key=lambda x: x[0], reverse=True)
    lines = ['  %s %s' % (t[:16], h[:100]) for t, h in found[:5]]
    if not lines:
        lines = ['  (no crew broadcasts found in bounded scan)']
    return 'recent bus digest (last 5 broadcasts, content-ordered)', lines


def attention_ids(attention):
    return sorted('%s:%s' % (r, b) for r, b in attention)


def attention_key(attention):
    return hashlib.sha256('|'.join(attention_ids(attention)).encode()).hexdigest()[:16]


def decide_emit(attention, prev_ids, prev_key):
    """v0.3: emit only when a NEW identity (runner:bucket) enters the attention
    set. An item leaving — a loop turning green, a hold lifted — is not attention
    and must not wake every executive's drain. Returns (emit, reason, new_ids).
    prev_ids is the identity list the last status_check recorded; a legacy
    record carries only attention_key, so that one transition falls back to
    key inequality (the v0.2 rule) rather than guessing."""
    ids = attention_ids(attention)
    if not ids:
        return False, 'nothing needing attention', []
    if prev_ids is None:
        if prev_key is None:
            return True, 'first run', ids
        return (attention_key(attention) != prev_key), 'legacy record: key compare', ids
    new = sorted(set(ids) - set(prev_ids))
    if new:
        return True, 'new: %s' % ', '.join(new), new
    return False, 'deduped — no new identity entered the attention set (%d carried)' % len(ids), []


def emit_broadcast(attention, key, new_ids=None):
    if not attention:
        return None, 'broadcast: none emitted (nothing needing attention)'
    new_txt = ('NEW %s; ' % ', '.join(new_ids)) if new_ids else ''
    body = {
        'category': 'ops', 'severity': 'flash',
        'headline': 'STUDIO-OPS ATTENTION REPORT (tropo-studio-status, key %s): %s%s' % (key, new_txt, ', '.join('%s (%s)' % a for a in attention)),
        'body': 'Deterministic boot check per design brief 756a70a9. Report and fail loudly; no action taken. Dispatch on Mike word only; decision-class items belong on the decision board.',
    }
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, 'vault', 'tools', 'tropo-emit-event.py'),
         '--source-uid', TOOL_UID, '--source', '/tools/tropo-studio-status',
         '--type', 'tropo.broadcast.crew', '--lifecycle', 'ephemeral',
         '--data', json.dumps(body)],
        capture_output=True, text=True)
    ok = r.returncode == 0
    msg = 'broadcast: EMITTED %s' % (json.loads(r.stdout).get('id', '?') if ok and r.stdout.strip().startswith('{') else '?') if ok \
        else 'broadcast: EMIT FAILED (warn-safe; will retry next boot — key NOT advanced) :: %s' % r.stderr.strip()[:100]
    return ok, msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-emit', action='store_true', help='dry run (no broadcast, no log write)')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--as', dest='as_agent', default=None,
                     help='agent slug (e.g. vela) — scopes the work-management section to open items owned by or assigned to this agent; omit for the studio-wide fallback')
    ap.add_argument('--board', choices=('counts', 'full'), default='counts',
                     help='counts (default, the boot shape) or full (every open item with its title)')
    args = ap.parse_args()

    # F7: empty substrate is FATAL — never a silent all-clear. But a FRESH BOX
    # has no studio-ops substrate by construction, and Po's Step 0d runs this
    # script on exactly that box to learn the Studio has no identity yet (v1.95
    # Spine A AC2b). Measured 2026-09-06 by argus-a172 on a HEAD candidate: the
    # floor fired first and the identity WARN never printed, so the arrival
    # walk's AC2b row failed on every honest box. The identity section runs
    # before the floor; the floor still returns 1.
    if not os.path.exists(ROSTER) or not os.path.exists(LOG):
        title, lines = section_identity()
        if lines:
            print(title)
            for line in lines:
                print(line)
        if not os.path.isdir(OPS):
            # The substrate folder does not exist at all: this Studio has never
            # initialised studio-ops. Every shipped box arrives this way and stays
            # this way through genesis (nothing at Step 0b creates it), and Po's
            # Step 0d runs this script on exactly that box. Vela's AC5 cold walk
            # of the sealed v1.95 candidate #2 (2026-09-06) measured the floor
            # returning 1 "regardless of identity state", so Step 0d never
            # completed. Not initialised is a WARN and a clean exit; the FATAL
            # floor below is for a substrate that EXISTS and was emptied or
            # truncated -- silence is never all-clear there.
            print('  [WARN] studio-ops substrate not initialised (%s absent) -- expected on a fresh '
                  'Studio; the ops loops create it' % OPS)
            return 0
        print('FATAL: studio-ops substrate missing (%s)' % OPS)
        return 1
    roster = json.load(open(ROSTER))
    rows, bad_lines = read_jsonl(LOG)
    if not roster.get('items'):
        print('FATAL: studio-ops roster has no items — emptied or corrupted; refusing to report all-clear')
        return 1
    if not rows:
        print('FATAL: studio-ops log is empty — truncated or corrupted; refusing to report all-clear')
        return 1

    sla, ops_lines, attention, _ = section_ops(roster, rows, bad_lines)
    sections = [
        ('studio-ops schedule state', ops_lines),
        section_crew(), section_git(), section_work(args.as_agent, args.board), section_meta(),
        section_identity(), section_bus(),
    ]

    # F9: signature over SUBSTANCE with all growing quantities (ages, ago-text)
    # stripped — buckets and content only; presentation never enters the hash
    sig_core = {
        'ops_buckets': sorted('%s:%s' % (i['runner'], bucket_for(i, last_event_per_runner(rows), NOW)[0]) for i in roster['items']),
        'sections': {t: ls for t, ls in sections if t != 'studio-ops schedule state'},
    }
    sig = hashlib.sha256(json.dumps(sig_core, sort_keys=True).encode()).hexdigest()[:16]
    checks = [e for e in rows if e.get('runner') == 'tropo-studio-status' and e.get('event') == 'status_check']
    prev_sig = checks[-1].get('signature') if checks else None
    prev_key = checks[-1].get('attention_key') if checks else None
    prev_ids = checks[-1].get('attention_ids') if checks else None

    key = attention_key(attention)
    ids = attention_ids(attention)
    do_emit, why, new_ids = decide_emit(attention, prev_ids, prev_key)
    if args.no_emit:
        emit_ok, bcast = None, 'broadcast: suppressed (--no-emit)'
    elif not do_emit:
        emit_ok, bcast = None, 'broadcast: none emitted (%s, key %s)' % (why, key)
    else:
        emit_ok, bcast = emit_broadcast(attention, key, new_ids)

    if args.json:
        print(json.dumps({'signature': sig, 'changed_since_last': sig != prev_sig,
                          'attention': attention, 'attention_key': key,
                          'unparseable_lines_skipped': bad_lines,
                          'sections': {t: ls for t, ls in sections}}, indent=1))
    else:
        print('=== tropo-studio-status (studio-ops v2.0, post-peer-review cures) === %s' % NOW.strftime('%Y-%m-%dT%H:%M:%SZ'))
        print(sla)
        print('state signature: %s%s' % (sig, '  (CHANGED since last look — substance)' if sig != prev_sig else ''))
        print(bcast)
        for title, lines in sections:
            if not lines:
                # a silent section is silent (AC2b: "nothing when present");
                # the title alone would read as a section that forgot to speak
                continue
            print('\n%s' % title)
            print('\n'.join(lines))
        if attention:
            print('\nSUGGESTION (relay to studio owner; do not act):')
            for r, b in attention:
                print('  - %s [%s]: run on Mike word, or route if owned elsewhere (roster note)' % (r, b))

    if not args.no_emit:
        # F4: the attention key advances ONLY when the emit reached the bus;
        # a failed emit retries next boot instead of suppressing forever
        with open(LOG, 'a') as f:
            f.write(json.dumps({'at': NOW.strftime('%Y-%m-%dT%H:%M:%SZ'), 'runner': 'tropo-studio-status',
                                'event': 'status_check', 'signature': sig,
                                'attention_key': key if emit_ok in (True, None) or not attention else prev_key,
                                # v0.3: identities persist so the next run can tell a
                                # new entrant from a leaver; a failed emit keeps the
                                # previous list so the entrant is retried next boot
                                'attention_ids': ids if emit_ok in (True, None) or not attention else (prev_ids or []),
                                'emit_ok': emit_ok,
                                'attention_count': len(attention),
                                'unparseable_skipped': bad_lines,
                                'by': {'actor': 'tool', 'id': 'tropo-studio-status'}}) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
