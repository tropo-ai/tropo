#!/usr/bin/env python3
"""
---
uid: cdadf603
title: "tropo-extract-text — searchable text out of mounted binaries, cached by UID + content hash"
name: tropo-extract-text
type: tool
status: active
owner: metis
created: 2026-08-07
created_by: metis-g104
extraction_scope: ship
subsystem_hub:
- 99ed55fd
domain: "Mounted-content legibility. Extracts body text from .docx/.pptx/.xlsx/.pdf living in a folder mount so the studio can search what is INSIDE them, not only their filenames."
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-extract-text.py {sync|file|get|grep|stats} [...]"
script_path: vault/tools/tropo-extract-text.py
destructive: false
audit_required: false
writes_scope:
- ".tropo-studio/extract-cache/ (derived, regenerable, gitignored-by-intent)"
governance_category: derived-content
schema_version: 2
trigger_description: "Reach for this when a mounted .docx/.pptx/.xlsx/.pdf should be findable by its CONTENT and not just its name. `sync` walks a mount and fills the cache; the index reads the cache."
tags:
- mounting
- extraction
- search
- office
- pdf
---

Extract searchable text from mounted binary documents.

WHY A CACHE, AND WHY KEYED THIS WAY
-----------------------------------
Extraction costs ~200ms/file (measured: 79 real documents in 16.1s). Re-running it
on every index rebuild is 16s for one small folder and minutes for a real corpus,
so the result must be cached.

The cache key is ``uid + content_sha256`` — never the path. Obsidian's Text
Extractor plugin keys on ``MD5(file.path)`` and performs no staleness check on
read, which produces two bugs by construction: a rename loses the cache entirely,
and an edited file returns stale text *forever*. Keying on identity plus content
means a rename is free (same uid, same bytes) and an edit invalidates exactly
once.

WHAT IT WILL NOT DO
-------------------
* **It never hydrates a cloud placeholder.** On a OneDrive/SharePoint mount ~90% of
  files are ``SF_DATALESS`` stubs; reading one downloads it. Placeholders are
  reported ``dataless`` and skipped. That is a fact to surface, not an error.
* **It never invents text.** A document that yields nothing is recorded with
  ``chars: 0`` and ``status: empty`` — distinguishable from "not yet tried".
  Silence and emptiness are different facts.
* **No network, no service, no API key.** ``mdimport`` is Spotlight's own importer
  and ships with macOS; the OOXML fallback is stdlib ``zipfile``.

metis-g104, 2026-08-07.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

EXTRACTABLE = {'.docx', '.pptx', '.xlsx', '.pdf'}
SF_DATALESS = 0x40000000
CACHE_DIRNAME = Path('.tropo-studio') / 'extract-cache'
MAX_CHARS = 4 * 1024 * 1024  # mirrors _MOUNTED_FTS_MAX_BYTES in the index


# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------

def _mdimport(path: Path) -> str:
    """Spotlight's own importer. Handles docx/pptx/xlsx/pdf/iWork/RTF."""
    try:
        out = subprocess.run(
            ['mdimport', '-t', '-d3', str(path)],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except Exception:
        return ''
    m = re.search(r'kMDItemTextContent\s*=\s*"(.*?)"(?:;|\n\s*kMD)', out, re.S)
    return m.group(1) if m else ''


def _ooxml(path: Path) -> str:
    """stdlib fallback: OOXML files are zip archives of XML.

    Used when mdimport returns nothing — a fresh file Spotlight has not indexed,
    or a machine where the importer is unavailable. Deliberately dumb: pull the
    text runs, join them, let the caller decide if it is enough.
    """
    try:
        z = zipfile.ZipFile(path)
    except Exception:
        return ''
    suffix = path.suffix.lower()
    if suffix == '.docx':
        parts, pattern = ['word/document.xml'], r'<w:t[^>]*>([^<]*)</w:t>'
    elif suffix == '.pptx':
        parts = sorted(
            n for n in z.namelist()
            if re.match(r'ppt/slides/slide[0-9]+\.xml$', n)
        )
        pattern = r'<a:t>([^<]*)</a:t>'
    elif suffix == '.xlsx':
        parts, pattern = ['xl/sharedStrings.xml'], r'<t[^>]*>([^<]*)</t>'
    else:
        return ''
    chunks: list[str] = []
    for name in parts:
        try:
            xml = z.read(name).decode('utf8', 'replace')
        except Exception:
            continue
        chunks.extend(re.findall(pattern, xml))
    return ' '.join(c for c in chunks if c.strip())


def extract(path: Path) -> tuple[str, str]:
    """Return (status, text). Never raises on a bad document."""
    try:
        st = os.lstat(path)
    except OSError:
        return 'missing', ''
    # Never trigger a cloud download to index something.
    if getattr(st, 'st_flags', 0) & SF_DATALESS:
        return 'dataless', ''
    if path.suffix.lower() not in EXTRACTABLE:
        return 'unsupported', ''

    text = _mdimport(path)
    if len(text.strip()) < 40:
        fallback = _ooxml(path)
        if len(fallback.strip()) > len(text.strip()):
            text = fallback
    text = text.replace('\\n', '\n').strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
    return ('ok' if text else 'empty'), text


def sha256_of(path: Path) -> str | None:
    """Content hash — only ever called on a materialized file."""
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as fh:
            for block in iter(lambda: fh.read(1 << 20), b''):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------

def cache_path(root: Path, uid: str) -> Path:
    return root / CACHE_DIRNAME / f'{uid}.json'


def cache_read(root: Path, uid: str) -> dict | None:
    p = cache_path(root, uid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def cache_write(root: Path, uid: str, rec: dict) -> None:
    p = cache_path(root, uid)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(rec, indent=1))
    tmp.replace(p)  # atomic


def is_current(rec: dict | None, content_hash: str | None) -> bool:
    """The whole point of the cache key: identity + content, never path."""
    return bool(rec) and bool(content_hash) and rec.get('content_sha256') == content_hash


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def mounted_records(root: Path, mount_uid: str | None) -> list[dict]:
    """Mounted projections from the index, optionally scoped to one mount."""
    out = []
    idx = root / 'vault' / '00-index.jsonl'
    if not idx.exists():
        return out
    for line in idx.open():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get('type') != 'external-artifact':
            continue
        if mount_uid and str(rec.get('mount_uid') or '') != mount_uid:
            continue
        src = rec.get('source_path')
        if src and Path(str(src)).suffix.lower() in EXTRACTABLE:
            out.append(rec)
    return out


def cmd_sync(args, root: Path) -> int:
    records = mounted_records(root, args.mount)
    print(f'{len(records)} extractable mounted document(s)'
          + (f' in mount {args.mount}' if args.mount else ''))
    counts = {'ok': 0, 'cached': 0, 'empty': 0, 'dataless': 0, 'missing': 0,
              'unsupported': 0}
    t0 = time.time()
    for rec in records:
        uid = str(rec.get('uid'))
        path = Path(str(rec.get('source_path')))
        try:
            st = os.lstat(path)
        except OSError:
            counts['missing'] += 1
            if args.verbose:
                print(f'  missing  {uid}  {path.name}')
            continue
        if getattr(st, 'st_flags', 0) & SF_DATALESS:
            counts['dataless'] += 1
            if args.verbose:
                print(f'  dataless {uid}  {path.name}  (not downloading)')
            continue
        content_hash = sha256_of(path)
        existing = cache_read(root, uid)
        if is_current(existing, content_hash) and not args.force:
            counts['cached'] += 1
            continue
        status, text = extract(path)
        if args.dry_run:
            print(f'  would extract {uid}  {path.name}  -> {status} '
                  f'({len(text):,} chars)')
            counts[status] = counts.get(status, 0) + 1
            continue
        cache_write(root, uid, {
            'uid': uid,
            'content_sha256': content_hash,
            'source_filename': path.name,
            'status': status,
            'chars': len(text),
            'extracted_by': args.executive,
            'text': text,
        })
        counts[status] = counts.get(status, 0) + 1
        if args.verbose:
            print(f'  {status:9} {uid}  {path.name}  ({len(text):,} chars)')
    el = time.time() - t0
    print(f'\nextracted {counts["ok"]} · cached {counts["cached"]} · '
          f'empty {counts["empty"]} · dataless {counts["dataless"]} · '
          f'missing {counts["missing"]}')
    print(f'{el:.1f}s'
          + (f'  ({el/max(len(records),1)*1000:.0f} ms/doc)' if records else ''))
    # Dataless is a normal state on a cloud mount, not a failure. Say so rather
    # than letting a count look like an error.
    if counts['dataless']:
        print(f'note: {counts["dataless"]} file(s) are cloud placeholders and were '
              f'skipped without downloading. Make them available locally to index them.')
    return 0


def cmd_file(args, root: Path) -> int:
    path = Path(args.path).expanduser()
    status, text = extract(path)
    print(f'{status}  {len(text):,} chars')
    if text and args.show:
        print('---')
        print(text[:args.show])
    return 0 if status == 'ok' else 1


def cmd_get(args, root: Path) -> int:
    rec = cache_read(root, args.uid)
    if not rec:
        print(f'no cached extraction for {args.uid}', file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(rec, indent=1))
    else:
        print(rec.get('text', ''))
    return 0


def cmd_grep(args, root: Path) -> int:
    """DIAGNOSTIC ONLY — a substring probe over the cache. NOT a search surface.

    Deliberately named `grep`, not `search`, and deliberately dumb: no ranking,
    no stemming, no query syntax. THE STUDIO HAS ONE SEARCH SURFACE AND IT IS
    THE INDEX. This exists to answer "did extraction actually capture anything
    useful" before the indexer is touched, and to debug a specific document.

    Note 4af60d6e (metis-g99, 2026-08-02) filed two search engines over one
    corpus as a defect -- they disagree about what the body is, rank
    differently, and a fix to one silently leaves the other broken. Adding a
    third would be repeating a defect we have already written down. If you find
    yourself adding ranking or filters here, stop: the work belongs in the FTS
    index, which is what this cache exists to feed.
    """
    d = root / CACHE_DIRNAME
    if not d.exists():
        print('cache empty — run `sync` first', file=sys.stderr)
        return 1
    needle = args.query.lower()
    hits = []
    for p in sorted(d.glob('*.json')):
        try:
            rec = json.loads(p.read_text())
        except Exception:
            continue
        text = rec.get('text') or ''
        low = text.lower()
        n = low.count(needle)
        if n:
            i = low.find(needle)
            start, end = max(0, i - 90), min(len(text), i + len(needle) + 90)
            snippet = ' '.join(text[start:end].split())
            hits.append((n, rec.get('uid'), rec.get('source_filename'), snippet))
    hits.sort(reverse=True)
    print(f'\n{len(hits)} document(s) contain "{args.query}"\n')
    for n, uid, name, snippet in hits[:args.limit]:
        print(f'  [{n}x] {name}')
        print(f'        uid {uid}')
        print(f'        …{snippet}…\n')
    return 0 if hits else 1


def cmd_stats(args, root: Path) -> int:
    d = root / CACHE_DIRNAME
    if not d.exists():
        print('cache empty')
        return 0
    n = chars = 0
    by_status: dict[str, int] = {}
    for p in d.glob('*.json'):
        try:
            rec = json.loads(p.read_text())
        except Exception:
            continue
        n += 1
        chars += int(rec.get('chars') or 0)
        s = str(rec.get('status'))
        by_status[s] = by_status.get(s, 0) + 1
    print(f'cached documents : {n}')
    print(f'total characters : {chars:,}  (~{chars//5:,} words)')
    print(f'by status        : {by_status}')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Extract searchable text from mounted binary documents.')
    ap.add_argument('--root', default=None, help='studio root')
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('sync', help='fill the cache for mounted documents')
    s.add_argument('--mount', help='limit to one mount uid')
    s.add_argument('--force', action='store_true', help='re-extract even if current')
    s.add_argument('--dry-run', action='store_true')
    s.add_argument('--verbose', action='store_true')
    s.add_argument('--executive', default='unknown')
    s.set_defaults(fn=cmd_sync)

    f = sub.add_parser('file', help='extract one file, print nothing to cache')
    f.add_argument('path')
    f.add_argument('--show', type=int, default=0, help='print N chars of text')
    f.set_defaults(fn=cmd_file)

    g = sub.add_parser('get', help='read cached text for a uid')
    g.add_argument('uid')
    g.add_argument('--json', action='store_true')
    g.set_defaults(fn=cmd_get)

    q = sub.add_parser('grep', help='DIAGNOSTIC substring probe over the cache; NOT a search surface')
    q.add_argument('query')
    q.add_argument('--limit', type=int, default=8)
    q.set_defaults(fn=cmd_grep)

    t = sub.add_parser('stats', help='what is in the cache')
    t.set_defaults(fn=cmd_stats)

    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    return args.fn(args, root)


if __name__ == '__main__':
    raise SystemExit(main())
