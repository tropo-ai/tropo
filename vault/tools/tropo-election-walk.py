#!/usr/bin/env python3
"""Shadow election walk — which twins have drifted from their sources, and by how much.

v1.94 Stream 5 (B-1, dev-spec 91d951f4), built by talos-t60 2026-09-02.

WHAT THIS IS. A SHADOW pair is a private source and the public twin that ships in its
place. Sources move. This walk says which twins are now editions of an older source, so
their owner can choose to re-elect. Mike ruled its posture at the lock walk, verbatim:

    "it's okay if they drift for a while, but there should always be a 'beacon home'
     between the two files and the opportunity to update. That was my original intent.
     I do not want blockers, I want awareness of drift"

So: this walk INFORMS. It never blocks a build, never fails a release, and never nags.
**Zero elections is a legal outcome and is stated out loud** rather than rendered as an
empty page, because an empty page and a page that did not run look identical.

THE FIELD IT TURNS ON is `edition_of_body_hash` on the twin: the source's body hash at
the moment that twin was last elected. Source hash == stored hash means no drift. A twin
with no stored hash has never been elected, so it is listed on the first run -- correct,
not an error.

USAGE
    tropo-election-walk.py                    # list drifted pairs
    tropo-election-walk.py --board <path>     # also render the board
    tropo-election-walk.py --apply <twin-uid> # elect: stamp the current source hash
    tropo-election-walk.py --apply-all        # elect every listed pair
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from lib.ship_verdict import build_resolver, normalize  # noqa: E402


def body_sha256(path):
    """Hash of the body after the closing frontmatter fence, one trailing newline.

    Same contract as the boot-derivation fingerprints (tropo-validate.body_sha256), so
    the two never disagree about what "the body" is. A file with no frontmatter hashes
    whole -- which is the op-agreement source's case, not an edge case.
    """
    raw = Path(path).read_bytes()
    parts = raw.split(b'\n---\n', 1)
    body = parts[1] if len(parts) == 2 else raw
    body = body.rstrip(b'\n') + b'\n'
    return hashlib.sha256(body).hexdigest()


def _read_frontmatter(path):
    text = Path(path).read_text(encoding='utf-8')
    if not text.startswith('---'):
        return {}, text
    end = text.find('\n---\n', 3)
    if end == -1:
        return {}, text
    import yaml
    try:
        return yaml.safe_load(text[4:end]) or {}, text
    except Exception:
        return {}, text


def _find_twin_file(vault_root, twin_uid):
    files_dir = Path(vault_root) / 'vault' / 'files'
    exact = files_dir / f'{twin_uid}.md'
    if exact.exists():
        return exact
    for candidate in sorted(files_dir.glob(f'*{twin_uid}*.md')):
        return candidate
    return None


class Pair:
    def __init__(self, source_path, twin_uid, twin_file, source_hash,
                 stored_hash, edition_date):
        self.source_path = source_path
        self.twin_uid = twin_uid
        self.twin_file = twin_file
        self.source_hash = source_hash
        self.stored_hash = stored_hash
        self.edition_date = edition_date

    @property
    def never_elected(self):
        return not self.stored_hash

    @property
    def drifted(self):
        """Listed when the source has moved since the last election, or never had one."""
        return self.never_elected or (self.source_hash != self.stored_hash)

    @property
    def state(self):
        if self.never_elected:
            return 'never elected'
        if self.drifted:
            return 'drifted'
        return 'current'


def collect_pairs(vault_root):
    """Every designated SHADOW pair, with both hashes resolved. Missing halves reported."""
    resolver = build_resolver(vault_root)
    pairs, problems = [], []

    for source_path, twin_uid in resolver.shadow_pairs():
        src_abs = Path(vault_root) / source_path
        if not src_abs.exists():
            problems.append(
                f'source missing on disk: {source_path} (designated to twin {twin_uid})')
            continue
        if not twin_uid:
            problems.append(
                f'{source_path} is ruled SHADOW but names no twin — a substitution with '
                f'nothing to substitute')
            continue
        twin_file = _find_twin_file(vault_root, twin_uid)
        if twin_file is None:
            problems.append(
                f'twin {twin_uid} not found for source {source_path} — the designation '
                f'points at nothing')
            continue

        fm, _ = _read_frontmatter(twin_file)
        pairs.append(Pair(
            source_path=source_path,
            twin_uid=twin_uid,
            twin_file=twin_file,
            source_hash=body_sha256(src_abs),
            stored_hash=(fm.get('edition_of_body_hash') or '').strip() or None,
            edition_date=fm.get('edition_date'),
        ))
    return pairs, problems


def apply_election(pair, dry_run=False):
    """Stamp the source's CURRENT body hash onto the twin. This is the election.

    Writes `edition_of_body_hash` and `edition_date` in place, creating them when
    absent. Only these two fields are touched -- an election is a statement that
    somebody looked at the two bodies, not a licence to edit the twin.
    """
    text = pair.twin_file.read_text(encoding='utf-8')
    if not text.startswith('---'):
        raise SystemExit(
            f'twin {pair.twin_uid} has no frontmatter to stamp — a twin must be a '
            f'governed record')
    end = text.find('\n---\n', 3)
    if end == -1:
        raise SystemExit(f'twin {pair.twin_uid} frontmatter is unterminated')

    fm_text, rest = text[4:end], text[end + 5:]
    today = date.today().isoformat()

    def _set(block, key, value):
        pattern = re.compile(rf'^{re.escape(key)}:.*$', re.MULTILINE)
        if pattern.search(block):
            return pattern.sub(f'{key}: {value}', block, count=1)
        return block.rstrip('\n') + f'\n{key}: {value}\n'

    fm_text = _set(fm_text, 'edition_of_body_hash', f'"{pair.source_hash}"')
    fm_text = _set(fm_text, 'edition_date', f"'{today}'")

    if dry_run:
        return False
    pair.twin_file.write_text(f'---\n{fm_text.rstrip()}\n---\n{rest}', encoding='utf-8')
    return True


BOARD_TEMPLATE = '''<!-- rendered by tropo-election-walk.py — a snapshot; regenerate when work moves -->
<link rel="stylesheet" href="../_shared/board.css">
<title>Shadow Election Walk</title>
<h1>Shadow Election Walk</h1>
<p class="lede">Which shipped public twins are editions of a source that has since moved.
This board informs; it never blocks a build. Zero elections is a legal outcome.</p>
{body}
<hr>
<p class="footer">Rendered by <code>tropo-election-walk.py</code> at {stamp} —
a snapshot; regenerate when work moves.</p>
'''


def render_board(pairs, problems, out_path):
    drifted = [p for p in pairs if p.drifted]
    rows = []
    if not pairs:
        body = ('<p class="empty"><strong>No SHADOW pairs are designated.</strong> '
                'Nothing to elect, and that is a legal state — not an empty render.</p>')
    elif not drifted:
        body = (f'<p class="empty"><strong>Zero elections.</strong> All {len(pairs)} '
                f'designated twin(s) are current editions of their sources. This is a '
                f'legal, stated outcome.</p>')
    else:
        for p in drifted:
            rows.append(
                f'<tr><td><code>{p.source_path}</code></td>'
                f'<td><code>{p.twin_uid}</code></td>'
                f'<td>{p.state}</td>'
                f'<td><code>{(p.stored_hash or "—")[:12]}</code></td>'
                f'<td><code>{p.source_hash[:12]}</code></td>'
                f'<td>{p.edition_date or "—"}</td></tr>')
        body = (
            f'<p><strong>{len(drifted)} of {len(pairs)}</strong> designated pair(s) '
            f'have drifted since their last election.</p>'
            '<table><thead><tr><th>Source</th><th>Twin</th><th>State</th>'
            '<th>Elected hash</th><th>Source hash now</th><th>Elected</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')

    if problems:
        items = ''.join(f'<li>{p}</li>' for p in problems)
        body += f'<h2>Designation problems</h2><ul class="warn">{items}</ul>'

    from datetime import datetime
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(BOARD_TEMPLATE.format(
        body=body,
        stamp=datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
    ), encoding='utf-8')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default=None, help='studio root (default: this tool\'s studio)')
    ap.add_argument('--board', default=None, help='render the board to this path')
    ap.add_argument('--apply', metavar='TWIN_UID', default=None,
                    help='elect one pair: stamp the current source hash onto that twin')
    ap.add_argument('--apply-all', action='store_true',
                    help='elect every drifted pair')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--json', action='store_true', help='machine-readable output')
    args = ap.parse_args()

    root = args.root or str(_HERE.parent.parent)
    pairs, problems = collect_pairs(root)
    drifted = [p for p in pairs if p.drifted]

    if args.json:
        print(json.dumps({
            'pairs': len(pairs),
            'drifted': [
                {'source': p.source_path, 'twin': p.twin_uid, 'state': p.state,
                 'source_hash': p.source_hash, 'elected_hash': p.stored_hash}
                for p in drifted],
            'problems': problems,
        }, indent=2))
    else:
        print('Shadow election walk')
        print(f'  designated pairs: {len(pairs)}')
        if not pairs:
            print('  No SHADOW pairs designated — nothing to elect. This is legal, not empty.')
        elif not drifted:
            print(f'  ZERO ELECTIONS — all {len(pairs)} twin(s) are current editions of '
                  f'their sources. Legal outcome, stated.')
        else:
            print(f'  {len(drifted)} pair(s) awaiting election:')
            for p in drifted:
                print(f'    · {p.source_path}')
                print(f'        twin {p.twin_uid} — {p.state}'
                      + (f' (elected {p.edition_date})' if p.edition_date else ''))
                print(f'        elected hash {(p.stored_hash or "none")[:16]} '
                      f'→ source now {p.source_hash[:16]}')
        for problem in problems:
            print(f'  ⚠ {problem}')

    applied = []
    if args.apply_all:
        targets = drifted
    elif args.apply:
        targets = [p for p in pairs if p.twin_uid == args.apply]
        if not targets:
            print(f'\n  No designated pair with twin {args.apply}', file=sys.stderr)
            return 2
    else:
        targets = []

    for p in targets:
        if apply_election(p, dry_run=args.dry_run):
            applied.append(p.twin_uid)
    if targets:
        verb = 'would elect' if args.dry_run else 'elected'
        print(f'\n  {verb}: {", ".join(t.twin_uid for t in targets)}')

    if args.board:
        # Re-collect so the board reflects any election just applied.
        pairs, problems = collect_pairs(root)
        out = render_board(pairs, problems, args.board)
        print(f'  board → {out}')

    # NEVER a failure exit for drift. Drift is information, per Mike's ruling.
    return 0


if __name__ == '__main__':
    sys.exit(main())
