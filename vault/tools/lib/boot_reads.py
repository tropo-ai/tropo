"""Warn-safe, content-free Claude Read observations for one activation window."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
try:
    import fcntl
except ImportError:  # Windows: honest degradation until a locking backend is supplied.
    fcntl = None
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import sys
from .boot_identity import find_activation_file, parse_frontmatter, extract_section

SCHEMA = 1
MARKER = re.compile(r'<!--\s*tropo-boot-read\s+(\{.*?\})\s*-->')

# Two independent claims, deliberately not collapsed. A read is OBSERVED when a
# successful in-window Read row carries the file's current content version; line
# COVERAGE is the weaker, separate claim about which lines that row proved. Native
# harnesses that return no line block leave coverage unknown, and unknown coverage
# of an observed read is not a missing read. Counted by identity, never by prose.
STATUS_FULL = 'done (full Read observed)'
STATUS_PARTIAL = 'observed (partial line coverage)'
STATUS_UNKNOWN = 'observed (line coverage unknown)'
STATUS_CHANGED = 'changed since observed'
STATUS_SKIPPED = 'skipped (no successful Read observed)'
STATUS_NOT_APPLICABLE = 'not applicable'
OBSERVED_STATUSES = (STATUS_FULL, STATUS_PARTIAL, STATUS_UNKNOWN)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(root, path):
    p = Path(path)
    p = (root / p).resolve() if not p.is_absolute() else p.resolve()
    return p.relative_to(root).as_posix()


def receipt_path(root, session):
    return root / '.tropo/flags' / ('boot-read-receipt-' + digest(session.encode()) + '.jsonl')


@contextmanager
def journal(root, session, receipt=None):
    if fcntl is None:
        raise ValueError('read observation unavailable: no supported serialization backend')
    path = receipt_path(root, session)
    path.resolve().relative_to(root)
    if receipt and Path(receipt).resolve() != path.resolve():
        raise ValueError('receipt does not match session/root')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+', encoding='utf-8') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        rows = [json.loads(line) for line in f if line.strip()]
        if any(not isinstance(r, dict) or r.get('schema') != SCHEMA or
               r.get('session_id') != session or r.get('root') != str(root) for r in rows):
            raise ValueError('malformed or mismatched receipt')
        def append(kind, **fields):
            row = dict(schema=SCHEMA, kind=kind, session_id=session, root=str(root),
                       at=datetime.now(timezone.utc).isoformat(), **fields)
            f.seek(0, 2)
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            rows.append(row)
        yield rows, append


def active_window(rows):
    active = None
    for row in rows:
        if row['kind'] == 'begin':
            active = row
        elif row['kind'] == 'reported' and active and row.get('window_id') == active.get('window_id'):
            active = None
    return active


def manifest_for(root, manifest=None, agent=None):
    if manifest:
        path = root / relative(root, manifest)
    else:
        if not agent or not re.fullmatch(r'[a-zA-Z0-9_-]+', agent):
            raise ValueError('missing or invalid agent resolution')
        activation = find_activation_file(root, agent)
        if not activation:
            raise ValueError('no activation file for ' + agent)
        fm = parse_frontmatter(activation.read_text())
        candidates = []
        if fm.get('agent_uid'):
            candidates.append(root / 'vault/agents' / (fm['agent_uid'] + '.md'))
        if fm.get('charter_file'):
            candidates.append(root / relative(root, fm['charter_file']))
        if fm.get('charter_uid'):
            candidates.append(root / 'vault/files' / (fm['charter_uid'] + '.md'))
        candidates.append(root / 'agents' / agent / 'agent-boot.extension.md')
        path = next((p for p in candidates if p.is_file() and
                     extract_section(p.read_text(), ('boot-extension',))), None)
        if not path:
            raise ValueError('no Boot-Extension resolved for ' + agent)
    text = path.read_text(encoding='utf-8')
    section = extract_section(text, ('boot-extension', 'boot protocol'))
    if not section:
        raise ValueError('manifest has no Boot Protocol or Boot-Extension')
    items = [json.loads(m.group(1)) for m in MARKER.finditer(section[1])]
    if not items:
        raise ValueError('manifest has no declared reads')
    seen = set()
    for item in items:
        if not isinstance(item, dict) or not item.get('id') or item['id'] in seen:
            raise ValueError('invalid or duplicate declaration')
        seen.add(item['id'])
        if item.get('applicability') not in ('required', 'if-present'):
            raise ValueError('unknown declaration applicability')
        item['path'] = relative(root, item['path'])
    # Birth synchronizes lifecycle frontmatter after begin. Bind the authored
    # boot instructions, not unrelated mutable metadata or other entry sections.
    # A changed declaration/instruction within this section still invalidates it.
    section_version = digest(('\n'.join(section)).encode('utf-8'))
    return dict(manifest=relative(root, path), manifest_digest=section_version, agent=agent), items


def coverage(path, response):
    """Accept only Claude's text-file envelope and byte-equivalent line ranges.

    Request offset/limit alone never contributes evidence. Unknown native shapes
    deliberately remain unknown until a real-harness acceptance walk validates them.
    """
    raw = path.read_bytes()
    version = digest(raw)
    result = dict(version=version, coverage='unknown', ranges=[])
    if not isinstance(response, dict) or response.get('type') != 'text':
        return result
    file = response.get('file')
    if not isinstance(file, dict) or not isinstance(file.get('content'), str):
        return result
    if any(response.get(k) or file.get(k) for k in ('truncated', 'is_truncated', 'error', 'is_error')):
        return result
    text = raw.decode('utf-8')
    lines = text.splitlines(keepends=True)
    start, count, total = (file.get(k) for k in ('startLine', 'numLines', 'totalLines'))
    if any(type(n) is not int for n in (start, count, total)):
        return result
    if total != len(lines) or start < 1 or count < 0 or start - 1 + count > total:
        return result
    expected = ''.join(lines[start - 1:start - 1 + count])
    # Native readers may omit the final newline from the returned range.
    if file['content'] not in (expected, expected.removesuffix('\n')):
        return result
    result.update(coverage='verified', ranges=[[start, start + count - 1]], total_lines=total)
    return result


def observe(verb, payload, root):
    if not isinstance(payload, dict) or payload.get('agent_id') or payload.get('subagent_id'):
        raise ValueError('execution context not independently observable')
    session = payload.get('session_id')
    if not isinstance(session, str) or not session.strip():
        raise ValueError('no harness session identity')
    if not isinstance(payload.get('cwd'), str) or not payload['cwd'].strip():
        raise ValueError('no explicit harness working directory')
    cwd = Path(payload['cwd']).resolve()
    cwd.relative_to(root)
    expected = 'SessionStart' if verb == 'session-start' else 'PostToolUse'
    if payload.get('hook_event_name') != expected:
        raise ValueError('unexpected native hook event')
    with journal(root, session) as (rows, append):
        if verb == 'session-start':
            append('session_start', source=payload.get('source'))
            env = os.environ.get('CLAUDE_ENV_FILE')
            if env:
                with open(env, 'a', encoding='utf-8') as f:
                    for key, value in [('TROPO_BOOT_READ_SESSION_ID', session),
                                       ('TROPO_BOOT_READ_ROOT', str(root)), ('TROPO_BOOT_READ_HARNESS', 'claude')]:
                        f.write('export ' + key + '=' + shlex.quote(value) + '\n')
            return 'Claude read observer session bound'
        if not any(r['kind'] == 'session_start' for r in rows):
            raise ValueError('missing SessionStart marker')
        if payload.get('tool_name') != 'Read' or payload.get('is_error') or payload.get('error'):
            raise ValueError('not a successful Read')
        response = payload.get('tool_response')
        if isinstance(response, dict) and (response.get('is_error') or response.get('error')):
            raise ValueError('failed Read response')
        inp = payload.get('tool_input', {})
        path = inp.get('file_path')
        if not isinstance(path, str):
            raise ValueError('missing Read file_path')
        rel = relative(root, cwd / path)
        active = active_window(rows)
        append('read', path=rel, window_id=active['window_id'] if active else None,
               tool_use_id=payload.get('tool_use_id'), offset=inp.get('offset'), limit=inp.get('limit'),
               **coverage(root / rel, response))
    return 'Read observation recorded'


def report(args):
    root = Path(args.vault_root).resolve()
    harness = args.harness or os.environ.get('TROPO_BOOT_READ_HARNESS')
    if harness != 'claude':
        raise ValueError('not observable in this harness')
    session = args.session_id or os.environ.get('TROPO_BOOT_READ_SESSION_ID')
    if not session:
        raise ValueError('no harness session identity')
    env_session = os.environ.get('TROPO_BOOT_READ_SESSION_ID')
    env_root = os.environ.get('TROPO_BOOT_READ_ROOT')
    if env_session and session != env_session:
        raise ValueError('session differs from hook environment')
    if env_root and Path(env_root).resolve() != root:
        raise ValueError('root differs from hook environment')
    binding, items = manifest_for(root, args.manifest, args.agent)
    with journal(root, session, args.receipt) as (rows, append):
        if not any(r['kind'] == 'session_start' for r in rows):
            raise ValueError('missing SessionStart marker')
        if args.begin:
            token = secrets.token_hex(24)
            append('begin', window_id=token, **binding)
            return dict(status='begun', window_id=token, summary=token)
        token = args.window_id
        if not token:
            raise ValueError('this boot not observable: no begin token')
        if args.audit:
            snapshots = [r for r in rows if r['kind'] == 'reported' and r.get('window_id') == token
                         and all(r.get(k) == v for k, v in binding.items())]
            if not snapshots:
                raise ValueError('no matching historical report')
            result = dict(snapshots[-1]['result'])
            result['summary'] = 'Historical audit (not a current greeting): ' + result['summary']
            return result
        active = active_window(rows)
        if not active or active.get('window_id') != token or any(active.get(k) != v for k, v in binding.items()):
            raise ValueError('absent, closed, superseded or mismatched activation window')
        window_reads = [r for r in rows[rows.index(active) + 1:] if r['kind'] == 'read' and r.get('window_id') == token]
        results = []
        for item in items:
            path = root / item['path']
            status = STATUS_SKIPPED
            if item['applicability'] == 'if-present' and not path.exists():
                status = STATUS_NOT_APPLICABLE
            elif path.is_file():
                raw = path.read_bytes()
                reads = [r for r in window_reads if r.get('path') == item['path']]
                same = [r for r in reads if r.get('version') == digest(raw)]
                covered = set()
                total = len(raw.decode('utf-8').splitlines(keepends=True))
                verified = False
                for row in same:
                    if row.get('coverage') == 'verified' and row.get('total_lines') == total:
                        ranges = row.get('ranges')
                        if not isinstance(ranges, list):
                            raise ValueError('malformed coverage ranges')
                        for first, last in ranges:
                            if type(first) is not int or type(last) is not int or not (1 <= first <= total + 1) or not (first - 1 <= last <= total):
                                raise ValueError('malformed coverage range')
                            covered.update(range(first, last + 1))
                            verified = True
                if verified and len(covered) == total:
                    status = STATUS_FULL
                elif same:
                    status = STATUS_PARTIAL if covered else STATUS_UNKNOWN
                elif reads:
                    status = STATUS_CHANGED
            results.append(dict(item, status=status))
        observed = sum(r['status'] in OBSERVED_STATUSES for r in results)
        done = sum(r['status'] == STATUS_FULL for r in results)
        partial = sum(r['status'] == STATUS_PARTIAL for r in results)
        unknown = sum(r['status'] == STATUS_UNKNOWN for r in results)
        due = sum(r['status'] != STATUS_NOT_APPLICABLE for r in results)
        # The headline counts observed reads; line coverage is reported beside it,
        # unknown where it is unknown, never silently folded into either number.
        lines = '; '.join(f'{label} for {n}' for n, label in
                          ((done, 'full line coverage verified'), (partial, 'partial line coverage'),
                           (unknown, 'line coverage unknown')) if n)
        result = dict(status='observed', observed=observed, done=done, partial=partial,
                      coverage_unknown=unknown, due=due, items=results,
                      summary=f'{observed}/{due} declared file reads observed in this Claude session '
                              'and activation window' + ('; ' + lines if lines else ''))
        append('reported', window_id=token, result=result, **binding)
        return result


def report_main(default_root):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vault-root', default=str(default_root))
    select = p.add_mutually_exclusive_group(required=True)
    select.add_argument('--manifest')
    select.add_argument('--agent')
    for name in ('session-id', 'receipt', 'harness', 'window-id'):
        p.add_argument('--' + name)
    p.add_argument('--begin', action='store_true')
    p.add_argument('--audit', action='store_true')
    p.add_argument('--json', action='store_true')
    args = p.parse_args()
    try:
        if args.begin and (args.audit or args.window_id):
            raise ValueError('begin cannot consume an existing window')
        result = report(args)
    except Exception as exc:
        result = dict(status='unobservable', summary=str(exc))
    if args.json:
        print(json.dumps(result))
    else:
        for row in result.get('items', []):
            print(row['id'] + ': ' + row['status'])
        print(result['summary'])
    return 0


def observer_main(default_root):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('verb', choices=('session-start', 'post-read'))
    p.add_argument('--vault-root', default=str(default_root))
    args = p.parse_args()
    try:
        print(observe(args.verb, json.load(sys.stdin), Path(args.vault_root).resolve()))
    except Exception as exc:
        print('Read observer unavailable: ' + str(exc))
    return 0
