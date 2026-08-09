#!/usr/bin/env python3
"""
---
uid: dd3ac1c3
title: navblock-strip — Tool
name: navblock-strip
type: tool
status: active
owner: talos
domain: "I5 (dd16c90c) enforcement — sentinel-bounded strip of the <!-- nav-block:start -->...<!-- nav-block:end --> region at the git boundary (dev-spec 6ec30708, Option A)."
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-navblock-strip.py [--process | --clean | --install | --verify-install | --check [PATH...] | --migrate PATH...]"
script_path: vault/tools/tropo-navblock-strip.py
input:
  type: object
  properties:
    clean:
      type: boolean
      description: "SUPERSEDED spawn-per-file filter entry point (stdin -> stdout). No longer registered: it cost ~53ms of interpreter startup PER FILE, ~3.1 min per git add/status after a rebuild. Kept as the byte-level strip primitive and for --migrate. The wired driver is --process."
    install:
      type: boolean
      description: "Bootstrap: register this script as filter.navblockstrip.process in the LOCAL repo's git config, and remove any superseded .clean wiring. .git/config is never committed, so every fresh clone/studio must re-run this once — same class of gap as the D2 merge driver (vault/tools/federation/README.md)."
    verify-install:
      type: boolean
      description: "Diagnostic: confirm BOTH .gitattributes declares the filter over vault/files/*.md AND the local git config has the clean command wired. Exit 0 if fully wired, 1 otherwise. No-argument default."
    check:
      type: array
      items:
        type: string
      description: "Report nav-block presence. With no PATHs: git grep HEAD across vault/files/*.md (the object-store/shared-bytes boundary — never the working tree, which keeps the block by design). With explicit PATHs: check those working-tree files directly."
    migrate:
      type: array
      items:
        type: string
      description: "Option-B/Phase-F direct body rewrite (deferred; NOT invoked by this Option-A build, which performs no destructive body edit at all). Kept because this tool is spec'd to serve both callers with one mechanism."
output:
  type: object
  properties:
    verdict:
      type: string
      enum:
      - pass
      - fail
destructive: false
audit_required: false
writes_scope:
- .git/config (local only, via --install; git config is never a tracked/committed file)
governance_category: lifecycle
description: 'Sentinel-bounded, idempotent, byte-safe strip of the machine-derived <!-- nav-block:start -->...<!-- nav-block:end --> region built for dev-spec 6ec30708, closing a signed I5 (dd16c90c, derived-never-syncs) violation: an index-derived, viewer-relative Navigation render was being committed inside governed vault/files/*.md bodies. Reuses (never reinvents) vault/tools/tropo-generate-relations-header.py''s strip_nav_block()/_NAV_BLOCK_RE — the same sentinel-strip the renderer, the export tool, and the FTS indexer already use. Serves two callers: the git clean filter (Option A, live now) and the deferred Option-B/Phase-F migration (a direct body rewrite, not used by this build).'
domain_tags:
- i5-enforcement
- git-clean-filter
- nav-blocks
- derived-content
- federation
- 6ec30708
trigger_description: "Reach for this when installing/verifying the nav-block git clean filter on a fresh clone or studio (--install then --verify-install), or when auditing whether any committed vault/files/*.md blob still carries a nav-block (--check)."
created: 2026-07-07
created_by: talos-t25
modified: 2026-07-07
modified_by: talos-t25
governed_by: d5e1b4a3
capsule_version: '2.5'
schema_version: 2
extraction_scope: ship
member_of:
- 8dd772a0
refs:
- 6ec30708
- dd16c90c
tags:
- tool
- cli
- i5-enforcement
- git-clean-filter
- nav-blocks
- 6ec30708
subsystem_hub:
- dbc1cbbf
belt: false
belt_note: "Occasional bootstrap/audit tool (install once per clone; check/verify on demand), not a reach-for-this-constantly primitive — same belt:false class as tropo-restore.py's precedent (ADR-050 belt cap)."
---
"""
from __future__ import annotations

"""tropo-navblock-strip.py — the Option-A git clean filter + shared strip primitive.

Dev-spec 6ec30708 (Argus A127, Option A RESOLVED 2026-07-06): the machine-derived
Navigation block (<!-- nav-block:start -->...<!-- nav-block:end -->, rendered by
tropo-generate-relations-header.py per OP-12) must never enter the git object store —
it is index-derived and viewer-relative (Siblings/Cited-by differ per composed graph),
so a copy baked into a shared/committed body is a standing I5 (dd16c90c,
derived-never-syncs) violation and, once shared, a cross-studio merge-storm engine.

Option A keeps the region on disk (working tree) for human/agent navigation and strips
it ONLY at the git boundary via a `clean` filter: `git add`/`git stage` runs this script
with the file's content on stdin and stages whatever it writes to stdout. The working
tree is never touched by the filter — `insert_or_update_block()` in the renderer keeps
regenerating the region locally on every render pass, exactly as before this spec.

Five entry points:
  --process          THE FILTER: git long-running filter process (packet-line, one
                     process per git command instead of one per file)
  --clean            superseded spawn-per-file mode; strip primitive + --migrate only
  --install           bootstrap: `git config filter.navblockstrip.process "..."` locally
                     (also removes any superseded .clean wiring)
  --verify-install     confirm .gitattributes + git config are BOTH wired (default action)
  --check [PATH...]   audit: any nav-block still in HEAD's object store? (or given paths)
  --migrate PATH...   direct body rewrite for the deferred Option-B/Phase-F cutover
"""

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

TOOLS_DIR = Path(__file__).resolve().parent
VAULT_ROOT = TOOLS_DIR.parent.parent
HEADER_SCRIPT = TOOLS_DIR / 'tropo-generate-relations-header.py'

FILTER_NAME = 'navblockstrip'
GITATTRIBUTES_PATH_PATTERN = 'vault/files/*.md'
CLEAN_COMMAND = 'python3 vault/tools/tropo-navblock-strip.py --clean'
PROCESS_COMMAND = 'python3 vault/tools/tropo-navblock-strip.py --process'

#: git's long-running filter protocol. Payload ceiling is git's
#: LARGE_PACKET_DATA_MAX (65520 - 4 bytes of length header).
_PKT_FLUSH = b'0000'
_PKT_MAX_PAYLOAD = 65516


class _Flush:
    """Sentinel for a `0000` flush packet, distinct from both EOF and an empty
    payload. Collapsing those three into `b''` is how a filter process hangs
    forever on a stream git has already closed."""


FLUSH = _Flush()

_HEADER_MODULE = None


def _header_module():
    """Lazily import tropo-generate-relations-header.py (hyphenated filename, so a
    normal `import` statement can't name it) exactly once per process. Side-effect-free:
    the header script's only top-level executable code is behind `if __name__ ==
    "__main__"`, verified against the live file this imports."""
    global _HEADER_MODULE
    if _HEADER_MODULE is None:
        spec = importlib.util.spec_from_file_location(
            'tropo_generate_relations_header_navstrip', str(HEADER_SCRIPT)
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _HEADER_MODULE = mod
    return _HEADER_MODULE


def strip_nav_block(text: str) -> str:
    """The one strip primitive, reused (not reinvented) from the renderer's own
    `_NAV_BLOCK_RE` / `strip_nav_block()` — byte-safe outside the sentinels, idempotent."""
    return _header_module().strip_nav_block(text)


def run_clean(stdin_bytes: bytes) -> bytes:
    """Pure byte-in/byte-out core of the `--clean` mode, factored out so tests can
    exercise it directly without a subprocess + real stdin/stdout."""
    text = stdin_bytes.decode('utf-8', errors='surrogateescape')
    return strip_nav_block(text).encode('utf-8', errors='surrogateescape')


def cmd_clean() -> int:
    data = sys.stdin.buffer.read()
    sys.stdout.buffer.write(run_clean(data))
    sys.stdout.buffer.flush()
    return 0


# --------------------------------------------------------------------------
# Long-running filter process (`filter.<driver>.process`)
#
# WHY THIS EXISTS AND WHY --clean IS NOT THE FILTER ANY MORE.
#
# `--clean` is a spawn-per-file shell-out: git starts a fresh python for every
# file it needs the clean form of. The interpreter start dominates completely
# -- ~53ms of process startup to run a regex over one small file. One full
# `rebuild-vault` re-renders the nav region into ~93% of the vault, so the next
# `git add`/`status`/`diff` pays that 53ms 3,561 times: ~3.1 MINUTES, against
# 6.4 SECONDS for the same command with the filter stubbed out to `cat`. About
# 29x the cost of the operation it wraps, on every git gesture, by every agent,
# on every machine.
#
# Dev-spec 6ec30708 line 113 called this exactly, in advance, verbatim: "Use
# git's long-running `filter.<driver>.process` protocol (not the spawn-per-file
# `clean` shell-out) to bound the cost of `git add`/`status`/`diff` at 2,410
# files." The spec named the failure and the remedy; the build shipped the
# shell-out anyway and nobody measured it. Measured by metis-g104 2026-08-07
# after git hung on her.
#
# This is the remedy as specified: ONE process handles every file over
# packet-line on stdin/stdout, so the interpreter starts once per git command
# instead of once per file.
# --------------------------------------------------------------------------


def _read_exactly(stream, count: int) -> bytes:
    buf = b''
    while len(buf) < count:
        chunk = stream.read(count - len(buf))
        if not chunk:
            return b''  # EOF mid-packet; caller treats as shutdown
        buf += chunk
    return buf


def _pkt_read(stream):
    """One packet. Returns bytes, FLUSH, or None at EOF."""
    header = _read_exactly(stream, 4)
    if len(header) < 4:
        return None
    if header == _PKT_FLUSH:
        return FLUSH
    try:
        length = int(header, 16)
    except ValueError:
        return None
    if length <= 4:
        return b''
    return _read_exactly(stream, length - 4)


def _pkt_read_until_flush(stream) -> Optional[List[bytes]]:
    """Packets up to the next flush. None at EOF -- git has closed us down."""
    items: List[bytes] = []
    while True:
        pkt = _pkt_read(stream)
        if pkt is None:
            return None
        if pkt is FLUSH:
            return items
        items.append(pkt)


def _pkt_write(stream, payload: bytes) -> None:
    stream.write(b'%04x' % (len(payload) + 4) + payload)


def _pkt_write_text(stream, text: str) -> None:
    _pkt_write(stream, text.encode('utf-8') + b'\n')


def _pkt_write_flush(stream) -> None:
    stream.write(_PKT_FLUSH)


def _pkt_write_content(stream, content: bytes) -> None:
    for start in range(0, len(content), _PKT_MAX_PAYLOAD):
        _pkt_write(stream, content[start:start + _PKT_MAX_PAYLOAD])
    _pkt_write_flush(stream)


def _parse_kv(items: List[bytes]) -> dict:
    out = {}
    for raw in items:
        line = raw.decode('utf-8', errors='replace').rstrip('\n')
        if '=' in line:
            key, _, value = line.partition('=')
            out[key] = value
    return out


def cmd_process(stdin=None, stdout=None) -> int:
    """git long-running filter, protocol version 2.

    Streams are injectable so the suite can drive a full conversation in-process
    without spawning git.
    """
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer

    handshake = _pkt_read_until_flush(stdin)
    if handshake is None:
        return 0
    intro = _parse_kv(handshake)
    welcome = [
        raw.decode('utf-8', errors='replace').strip() for raw in handshake
    ]
    if 'git-filter-client' not in welcome:
        print('[FAIL] not speaking git filter protocol on stdin', file=sys.stderr)
        return 1
    if intro.get('version') != '2':
        print(
            f"[FAIL] unsupported filter protocol version {intro.get('version')!r}; "
            f"this filter speaks version 2",
            file=sys.stderr,
        )
        return 1
    _pkt_write_text(stdout, 'git-filter-server')
    _pkt_write_text(stdout, 'version=2')
    _pkt_write_flush(stdout)
    stdout.flush()

    # Announce only what we do. `smudge` is deliberately absent: 6ec30708's
    # implementation note rules it out by name -- regeneration is the batch
    # Step-5 render on pull, never a per-file smudge on checkout.
    if _pkt_read_until_flush(stdin) is None:
        return 0
    _pkt_write_text(stdout, 'capability=clean')
    _pkt_write_flush(stdout)
    stdout.flush()

    while True:
        meta = _pkt_read_until_flush(stdin)
        if meta is None:
            return 0  # git closed the stream: normal shutdown
        request = _parse_kv(meta)
        command = request.get('command')
        payload = _pkt_read_until_flush(stdin)
        if payload is None:
            return 0
        content = b''.join(payload)

        if command != 'clean':
            _pkt_write_text(stdout, 'status=error')
            _pkt_write_flush(stdout)
            stdout.flush()
            continue

        try:
            cleaned = run_clean(content)
        except Exception as exc:  # a bad file must not take the whole run down
            print(
                f"[FAIL] nav-block strip failed for "
                f"{request.get('pathname', '<unknown>')}: {exc}",
                file=sys.stderr,
            )
            _pkt_write_text(stdout, 'status=error')
            _pkt_write_flush(stdout)
            stdout.flush()
            continue

        _pkt_write_text(stdout, 'status=success')
        _pkt_write_flush(stdout)
        _pkt_write_content(stdout, cleaned)
        _pkt_write_flush(stdout)  # empty list terminates the response
        stdout.flush()


def cmd_install(vault_root: Path) -> int:
    r = subprocess.run(
        ['git', 'config', f'filter.{FILTER_NAME}.process', PROCESS_COMMAND],
        cwd=str(vault_root), capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f'[FAIL] git config install failed: {r.stderr.strip()}', file=sys.stderr)
        return 1
    # Retire the slow wiring in the same gesture. git prefers `process` when
    # both are present, so a leftover `.clean` would not change behaviour --
    # but it would sit in every existing clone looking correct, and the next
    # reader would have no way to tell a migrated clone from a stale one.
    # Every clone that ran the old --install has this line right now.
    removed = subprocess.run(
        ['git', 'config', '--unset-all', f'filter.{FILTER_NAME}.clean'],
        cwd=str(vault_root), capture_output=True, text=True,
    )
    print(
        f'[OK] filter.{FILTER_NAME}.process installed in {vault_root}/.git/config '
        f'(LOCAL only; .git/config is never committed — re-run this on every fresh '
        f'clone/studio).'
    )
    if removed.returncode == 0:
        print(
            f'[OK] removed the superseded filter.{FILTER_NAME}.clean wiring '
            f'(spawn-per-file; ~53ms of interpreter startup per file).'
        )
    return 0


def _gitattributes_declares_filter(vault_root: Path) -> bool:
    ga = vault_root / '.gitattributes'
    if not ga.is_file():
        return False
    for line in ga.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] == GITATTRIBUTES_PATH_PATTERN and f'filter={FILTER_NAME}' in parts[1:]:
            return True
    return False


def _git_config_value(vault_root: Path, key: str) -> str:
    r = subprocess.run(
        ['git', 'config', '--get', key],
        cwd=str(vault_root), capture_output=True, text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else ''


def _git_config_has_clean(vault_root: Path) -> bool:
    return bool(_git_config_value(vault_root, f'filter.{FILTER_NAME}.clean'))


def _git_config_has_process(vault_root: Path) -> bool:
    return bool(_git_config_value(vault_root, f'filter.{FILTER_NAME}.process'))


def verify_install(vault_root: Path) -> Tuple[bool, List[str]]:
    """Two independent halves must BOTH be true, per 6ec30708 §6 / the D2 merge-driver
    precedent (vault/tools/federation/README.md): `.gitattributes` alone never carries
    the command — a fresh clone's LOCAL git config is a second, separate install step.
    Returns (fully_wired, findings)."""
    findings: List[str] = []
    ga_ok = _gitattributes_declares_filter(vault_root)
    process_ok = _git_config_has_process(vault_root)
    stale_clean = _git_config_has_clean(vault_root)
    if not ga_ok:
        findings.append(
            f"[FAIL] .gitattributes does not declare '{GITATTRIBUTES_PATH_PATTERN} filter={FILTER_NAME}' "
            f"— the I5 (dd16c90c) clean-strip is not declared at all in this vault root."
        )
    if not process_ok:
        findings.append(
            f"[FAIL] git config filter.{FILTER_NAME}.process is not set in this clone's LOCAL "
            f".git/config (never committed) — run `python3 vault/tools/tropo-navblock-strip.py "
            f"--install`. A studio without this cannot silently commit nav-blocks into a shared "
            f"segment (6ec30708 AC5) — same failure class as a missing D2 merge driver."
        )
    # A stale `.clean` FAILS rather than warns, and that is the point of this
    # half. git prefers `process` when both are set, so the slow wiring is
    # invisible from behaviour alone -- it just sits there being correct-looking
    # in every clone that ever ran the old installer. The tool half of this fix
    # is worthless on its own: .git/config is per-clone and never committed, so
    # nothing propagates it. The check has to be the thing that finds them.
    # (metis-g104 found 143 committed nav-blocks in the MindBridge studio from
    # exactly this gap in the ORIGINAL install, one layer down.)
    if stale_clean:
        findings.append(
            f"[FAIL] git config filter.{FILTER_NAME}.clean is still wired in this clone — "
            f"the superseded spawn-per-file shell-out (~53ms of interpreter startup per "
            f"file; ~3.1 min per git add/status after a full rebuild, vs 6.4s). Re-run "
            f"`python3 vault/tools/tropo-navblock-strip.py --install`, which installs the "
            f"long-running process protocol and removes this line (6ec30708 line 113)."
        )
    return (ga_ok and process_ok and not stale_clean), findings


def cmd_verify_install(vault_root: Path) -> int:
    ok, findings = verify_install(vault_root)
    if ok:
        print(f'[PASS] nav-block clean filter fully wired ({vault_root}).')
        return 0
    for f in findings:
        print(f, file=sys.stderr)
    return 1


def cmd_check(paths: Optional[List[str]], vault_root: Path) -> int:
    """No PATHS (the AC1 shared-segment claim): `git grep` HEAD for the sentinel across
    vault/files/*.md — the object-store boundary, never the working tree (which keeps
    the block by design under Option A). Explicit PATHS: direct working-tree spot-check
    (tests / manual use), NOT a stand-in for the HEAD claim."""
    if not paths:
        r = subprocess.run(
            ['git', 'grep', '-l', 'nav-block:start', 'HEAD', '--', GITATTRIBUTES_PATH_PATTERN],
            cwd=str(vault_root), capture_output=True, text=True,
        )
        if r.returncode not in (0, 1):
            print(f'[ERROR] git grep failed: {r.stderr.strip()}', file=sys.stderr)
            return 2
        # git grep finds the SENTINEL STRING; the filter strips a line-anchored
        # REGION. Those are different questions, and the audit was asking the
        # wrong one — it reported 11 "committed nav-blocks" in a vault that has
        # zero, because eleven governed files DISCUSS nav-blocks and one of them
        # is the nav-block dev-spec itself. An instrument aimed one gate off from
        # the mechanism it measures. Confirm each candidate against the canonical
        # regex, which is the same one the filter uses.
        # (Found via Metis G105's Stream A loose-ends list, 2026-08-08.)
        hits = []
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            ref = line.split(':', 1)[0] if ':' in line else line
            rel = line.split(':', 1)[1] if ':' in line else line
            blob = subprocess.run(
                ['git', 'show', f'{ref}:{rel}'],
                cwd=str(vault_root), capture_output=True, text=True,
            )
            if blob.returncode != 0:
                continue
            if strip_nav_block(blob.stdout) != blob.stdout:
                hits.append(line)
        if not hits:
            print(f'[PASS] 0 committed {GITATTRIBUTES_PATH_PATTERN} blobs carry a nav-block (HEAD).')
            return 0
        print(f'[FAIL] {len(hits)} committed {GITATTRIBUTES_PATH_PATTERN} blob(s) still carry a nav-block (HEAD):', file=sys.stderr)
        for h in hits[:20]:
            print(f'  {h}', file=sys.stderr)
        if len(hits) > 20:
            print(f'  ... and {len(hits) - 20} more', file=sys.stderr)
        return 1

    hits = []
    for p in paths:
        fp = Path(p)
        if not fp.is_file():
            continue
        text = fp.read_text(encoding='utf-8', errors='replace')
        if strip_nav_block(text) != text:  # the region, not the mention
            hits.append(p)
    if hits:
        print(f'[INFO] {len(hits)} of {len(paths)} given path(s) carry a nav-block (working-tree check).')
        for h in hits:
            print(f'  {h}')
        return 1
    print(f'[INFO] 0 of {len(paths)} given path(s) carry a nav-block (working-tree check).')
    return 0


def cmd_migrate(paths: List[str]) -> int:
    """Direct body rewrite — the Option-B/Phase-F mechanism. Deferred; NOT invoked by
    this build's rollout (Option-A-only, no body edit performed anywhere in this
    commit). Kept here because 6ec30708's committed_substrate text is explicit this
    ONE tool 'serves BOTH the git clean-filter (Option A) and the one-time Phase-M
    migration pass' — one mechanism, two callers, built once, not two half-tools."""
    changed = 0
    for p in paths:
        fp = Path(p)
        if not fp.is_file():
            print(f'[skip] {p}: not a file', file=sys.stderr)
            continue
        original = fp.read_text(encoding='utf-8')
        stripped = strip_nav_block(original)
        if stripped != original:
            fp.write_text(stripped, encoding='utf-8')
            changed += 1
            print(f'[migrated] {p}')
        else:
            print(f'[unchanged] {p}')
    print(f'{changed} of {len(paths)} file(s) changed.')
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Nav-block strip: git clean filter + migration primitive (dev-spec 6ec30708).'
    )
    parser.add_argument('--clean', action='store_true', help='SUPERSEDED spawn-per-file filter mode: stdin -> stdout (kept as the strip primitive and for --migrate; --install no longer wires it)')
    parser.add_argument('--process', action='store_true', help='git long-running filter process (packet-line); the wired filter')
    parser.add_argument('--install', action='store_true', help='register filter.navblockstrip.process in local git config and remove any superseded .clean wiring')
    parser.add_argument('--verify-install', action='store_true', help='confirm .gitattributes + git config are both wired')
    parser.add_argument('--check', nargs='*', default=None, metavar='PATH',
                         help='report nav-block presence (default with no PATH: HEAD object store via git grep)')
    parser.add_argument('--migrate', nargs='+', default=None, metavar='PATH',
                         help='Option-B/Phase-F direct body rewrite (deferred; not used by this Option-A rollout)')
    parser.add_argument('--vault-root', default=None, help='override vault root (default: repo containing this script)')
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    vault_root = Path(args.vault_root).resolve() if args.vault_root else VAULT_ROOT

    if args.process:
        return cmd_process()
    if args.clean:
        return cmd_clean()
    if args.install:
        return cmd_install(vault_root)
    if args.verify_install:
        return cmd_verify_install(vault_root)
    if args.migrate is not None:
        return cmd_migrate(args.migrate)
    if args.check is not None:
        return cmd_check(args.check, vault_root)
    # No flags at all: the single most useful default diagnostic — "is I5
    # enforcement actually live in this clone?"
    return cmd_verify_install(vault_root)


if __name__ == '__main__':
    sys.exit(main())
