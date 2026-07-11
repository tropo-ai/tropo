"""shard_index.py — shard-keyed incremental composed-index primitive
(dev-spec c6f6bea4, ADR-051 Fork 4; test-spec ea352a6b).

SHARED module imported by both tropo-rebuild-index.py (the writer: derives +
reuses shard caches, unions them into vault/00-index.jsonl) and
tropo-validate.py (the reader: check_shard_index_consistency, the staleness
guard). Mirrors the lib/cross_vault_member_of.py sibling pattern — one
classification/derivation module, two consumers, so writer and validator can
never silently drift apart on what "stale" or "unreachable" means.

THE MODEL (Argus A128 rulings, build against these, do not re-litigate):
  1. Shard key = (vault_uid, resolved_commit) from .tropo-studio/compose.lock.
     No independent hashing — the mount-gate pin (409ef1cc) IS the dirty-check key.
  2. Composed index location is UNCHANGED: vault/00-index.jsonl. Shard caches
     are an internal build artifact under .tropo-studio/shards/, not a new
     query surface.
  3. The LOCAL shard (this studio's own vault/ — its private + os segments)
     is NOT pinned; it keeps the existing full source-scan trigger and is
     always re-derived. Only MOUNTED shards (one per compose.lock vault_uid)
     are pin-keyed / incrementally reused.
  4. Fail closed over fast. A shard that cannot be composed (missing cache,
     stale .meta, unreachable mount_path) is excluded + flagged — never
     silently dropped from view, never silently served stale/partial.

CACHE LAYOUT: `.tropo-studio/shards/<vault_uid>.jsonl` (that vault's index
rows, one JSON object per line — same per-record shape process_file()/
_record_to_index_rows' source records already produce) + a sibling
`.tropo-studio/shards/<vault_uid>.meta` (a single-line JSON object
`{"vault_uid": ..., "resolved_commit": ..., "derived_at": ...}` recording the
exact resolved_commit the .jsonl was derived at — the pin-diff key).

DERIVATION OF A MOUNTED SHARD: mount-gate (409ef1cc) refuses to record a
compose.lock pin for a dirty or unpinned working tree, so `mount_path`'s
working tree IS the pinned commit's content by construction — this module
re-derives a mounted shard by scanning `mount_path/vault/files/*.md` (the
same canonical-bulk source vault/files/ scan tropo-rebuild-index.py already
performs for the LOCAL shard) using the caller-supplied `process_file`
function (dependency-injected, not imported here, to keep this module free
of a hard import cycle against tropo-rebuild-index.py). This is a read-only
scan of the mounted working tree — no scratch clone, no `git show` extraction
— documented as a judgment call (see c6f6bea4 build report §9): today there
are ZERO real mounted vaults, so this path is proven only against fixture
git-backed 'mounted vault' source trees (test-spec ea352a6b), not a real
second studio.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional

SHARDS_REL = Path('.tropo-studio') / 'shards'
COMPOSE_LOCK_REL = Path('.tropo-studio') / 'compose.lock'


class ShardStatus(NamedTuple):
    """Outcome of reconciling one compose.lock vault_uid against its cache."""
    vault_uid: str
    action: str          # 'reused' | 'derived' | 'cannot-compose'
    reason: Optional[str]  # populated when action == 'cannot-compose'
    resolved_commit: Optional[str]
    record_count: int


def load_compose_lock_vaults(vault_root: Path) -> dict[str, dict]:
    """Read .tropo-studio/compose.lock; return its `vaults` dict, or {} if
    absent/corrupt/malformed. Never raises — an absent or empty compose.lock
    is the (today universal) "no mounted shards, local-only" case, which
    must behave identically to the pre-shard-index rebuild."""
    lock_path = vault_root / COMPOSE_LOCK_REL
    if not lock_path.is_file():
        return {}
    try:
        data = json.loads(lock_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    vaults = data.get('vaults') if isinstance(data, dict) else None
    return vaults if isinstance(vaults, dict) else {}


def shard_jsonl_path(vault_root: Path, vault_uid: str) -> Path:
    return vault_root / SHARDS_REL / f'{vault_uid}.jsonl'


def shard_meta_path(vault_root: Path, vault_uid: str) -> Path:
    return vault_root / SHARDS_REL / f'{vault_uid}.meta'


def read_shard_meta(vault_root: Path, vault_uid: str) -> Optional[dict]:
    """Return the parsed .meta object, or None if absent/corrupt."""
    p = shard_meta_path(vault_root, vault_uid)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _hash_jsonl_bytes(raw: bytes) -> str:
    """sha256 of the shard .jsonl file's raw bytes — the writer computes this
    once at write time; readers (resolve_shards, staleness_findings) recompute
    it from the LIVE on-disk .jsonl and compare against .meta's recorded value
    before trusting a commit-string match alone.

    SECURITY-REVIEW FIX (Talos T26, 2026-07-08): write_shard() performs two
    INDEPENDENT os.replace calls (jsonl, then meta) — not one atomic
    transaction. A crash between the two can leave .jsonl holding content
    derived at a NEWER commit while .meta still records an OLDER commit. If
    compose.lock is later re-pinned back to that older commit (a legitimate
    remount/revert), the old resolved_commit==pin check alone would silently
    accept the desynchronized .jsonl as valid — a stale-cache-served-as-fresh
    hole in the exact fail-closed guarantee this primitive exists to
    enforce. Recording + re-verifying the .jsonl content hash inside .meta
    closes it: any partial/desynchronized write is detected as a hash
    mismatch, not silently trusted on commit-string agreement alone.
    """
    return hashlib.sha256(raw).hexdigest()


def read_shard_jsonl(vault_root: Path, vault_uid: str) -> Optional[list[dict]]:
    """Return the cached shard's records, or None if the cache file is
    absent/unreadable. An empty-but-present file returns []."""
    p = shard_jsonl_path(vault_root, vault_uid)
    if not p.is_file():
        return None
    records: list[dict] = []
    try:
        with p.open(encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    return records


def _read_shard_jsonl_hash(vault_root: Path, vault_uid: str) -> Optional[str]:
    """sha256 of the LIVE on-disk .jsonl file's raw bytes, or None if absent/
    unreadable. Used to cross-verify against .meta's recorded jsonl_sha256."""
    p = shard_jsonl_path(vault_root, vault_uid)
    if not p.is_file():
        return None
    try:
        return _hash_jsonl_bytes(p.read_bytes())
    except OSError:
        return None


def write_shard(vault_root: Path, vault_uid: str, resolved_commit: str, records: list[dict], derived_at: str) -> None:
    """Temp+swap write of both <vault_uid>.jsonl and <vault_uid>.meta — same
    house pattern as index_path / compose.lock (os.replace). The two
    os.replace calls are NOT one atomic transaction (see jsonl_sha256 below
    for how the crash-consistency window this leaves open is closed)."""
    import os
    shards_dir = vault_root / SHARDS_REL
    shards_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = shard_jsonl_path(vault_root, vault_uid)
    tmp_jsonl = jsonl_path.with_suffix('.jsonl.tmp')
    jsonl_bytes = b''.join(
        (json.dumps(rec, separators=(',', ':')) + '\n').encode('utf-8') for rec in records
    )
    tmp_jsonl.write_bytes(jsonl_bytes)
    jsonl_hash = _hash_jsonl_bytes(jsonl_bytes)
    os.replace(tmp_jsonl, jsonl_path)

    # meta is written+swapped SECOND and carries jsonl_sha256 — a reader that
    # sees this meta but a live .jsonl hash that DISAGREES with jsonl_sha256
    # knows the pair desynchronized across a crash (§_hash_jsonl_bytes) and
    # must treat the shard as cannot-compose, not silently trust it.
    meta_path = shard_meta_path(vault_root, vault_uid)
    tmp_meta = meta_path.with_suffix('.meta.tmp')
    meta = {
        'vault_uid': vault_uid,
        'resolved_commit': resolved_commit,
        'derived_at': derived_at,
        'record_count': len(records),
        'jsonl_sha256': jsonl_hash,
    }
    tmp_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(tmp_meta, meta_path)


def retire_shard(vault_root: Path, vault_uid: str) -> bool:
    """Remove a cached shard's .jsonl + .meta (vault_uid no longer pinned in
    compose.lock). Returns True if anything was actually removed."""
    removed = False
    for p in (shard_jsonl_path(vault_root, vault_uid), shard_meta_path(vault_root, vault_uid)):
        if p.exists():
            p.unlink()
            removed = True
    return removed


def list_cached_shard_uids(vault_root: Path) -> set[str]:
    shards_dir = vault_root / SHARDS_REL
    if not shards_dir.is_dir():
        return set()
    return {p.stem for p in shards_dir.glob('*.meta')}


def mount_path_reachable(mount_path_str: Optional[str]) -> Optional[Path]:
    """mount_path is advisory LOCAL-MACHINE state (409ef1cc schema doc) — a
    missing/unreachable mount_path is 'cannot verify', not a hard failure of
    THIS check. Returns the resolved Path if it exists and looks like a
    vault root (has vault/files/), else None."""
    if not mount_path_str:
        return None
    p = Path(mount_path_str)
    if not p.is_dir():
        return None
    if not (p / 'vault' / 'files').is_dir():
        return None
    return p


def pin_and_clean_violation(mount_path: Path, pin: str) -> Optional[str]:
    """Returns a human-readable reason, or None if mount_path's checked-out
    HEAD equals `pin` AND the working tree is clean (BOUNCE finding #8,
    2026-07-09). Re-deriving a shard from a working tree that has drifted
    from the pin it's supposed to represent — via a manual checkout, an
    uncommitted local edit, or a branch switch to the published team-main
    ref — would silently scan content the mount-gate never approved."""
    if not (mount_path / '.git').exists():
        return f'{mount_path} is not a git repository — cannot verify it matches pin {pin!r}'
    head_result = subprocess.run(
        ['git', '-C', str(mount_path), 'rev-parse', 'HEAD'],
        capture_output=True, text=True, timeout=10,
    )
    if head_result.returncode != 0:
        return f'could not resolve HEAD at {mount_path}: {head_result.stderr.strip()}'
    head = head_result.stdout.strip()
    if head != pin:
        return f'{mount_path} HEAD ({head[:12]}) != compose.lock pin ({pin[:12]}) — refusing to scan a working tree that has drifted from its pin'
    status_result = subprocess.run(
        ['git', '-C', str(mount_path), 'status', '--porcelain'],
        capture_output=True, text=True, timeout=10,
    )
    if status_result.returncode != 0:
        return f'could not check working-tree cleanliness at {mount_path}: {status_result.stderr.strip()}'
    if status_result.stdout.strip():
        dirty_lines = status_result.stdout.strip().splitlines()
        return f'{mount_path} has a DIRTY working tree ({len(dirty_lines)} uncommitted change(s)) at pin {pin[:12]} — refusing to scan uncommitted content'
    return None


def derive_mounted_shard_records(
    mount_path: Path,
    process_file: Callable[[Path], Optional[dict[str, Any]]],
    vault_uid: str,
) -> list[dict]:
    """Re-derive a mounted shard's index rows by scanning
    `mount_path/vault/files/*.md` with the SAME per-file transform
    (`process_file`, dependency-injected by the caller — tropo-rebuild-
    index.py's own function) the local shard uses. Every record is tagged
    with `path` (relative to `mount_path`, mirroring the local shard's
    v1.69 path-provenance convention) so downstream Gardener segment
    discrimination and mentions-parsing behave identically regardless of
    which population a record came from.

    Deliberately narrow: only vault/files/*.md (the canonical-bulk source),
    not the other 11 local-studio-only collectors (agents/, capsules/,
    memory entries, etc.) — a mounted vault's OWN governed substrate is its
    vault/files/ tree; its studio-root/agents/tools sources describe ITS
    OWN studio operationally, not content this composed index should absorb
    wholesale. This mirrors the dev-spec's framing of a shard as "a
    segment = a vault-node" (I1), not "a whole foreign studio."

    SECURITY-REVIEW FIX (Talos T26, 2026-07-08): a mounted record's `path`
    is now provenance-prefixed (`mounted/<vault_uid>/vault/files/<file>`),
    NOT a bare `vault/files/<file>` string. A bare path was string-identical
    to a LOCAL record's own vault/files/ path shape, which let
    tropo-rebuild-index.py's pre-existing S7 source-precedence dedup
    (tier 0 = anything path-prefixed `vault/files/`) place a mounted record
    at the SAME precedence tier as a local one; if a mounted record's UID
    happened to collide with a local (or another mount's) record's UID AND
    they coincidentally shared type+title, S7's same-entity heuristic
    silently collapsed them into ONE record, discarding the other vault's
    genuinely distinct document with no warning — a live violation of the
    one-clone-per-vault-UID guarantee (I1) despite this shard-index build
    never itself minting a duplicate. The provenance prefix guarantees a
    mounted record's path can never string-collide with a local one, and
    the sibling `_shard_vault_uid` marker (stripped before the final index
    write — see tropo-rebuild-index.py's S7 dedup amendment) lets the dedup
    logic explicitly refuse to silently merge two records from DIFFERENT
    vault provenances even if type+title coincidentally match — that case
    now fails loud, exactly like the pre-existing cross-document-collision
    path already does for two genuinely different local documents.

    PULL-SIDE BOUNDARY FILTER (Talos T27, 2026-07-08, dev-spec 44badb55
    §4 — "B does NOT trust A"): when `mount_path` carries its own
    `.tropo/vault-manifest.md` (a REAL, mount-gate-approved vault-node —
    the only shape 409ef1cc's gate ever actually admits into compose.lock),
    every candidate record is re-checked against the SAME two-gate boundary
    tropo-publish.py enforces on the write side (lib.segment.is_public_scope
    + lib.segment.derive_segment == this mount's own manifest uid) before
    it is allowed into the returned list. A record that fails either gate
    is EXCLUDED outright — never unioned into the composed index, not
    merely excluded from some downstream edge/adjacency view. This is what
    "records excluded, not merely edges" means: a private-segment record
    that somehow reached this machine's clone (a bypass of tropo-publish.py,
    a compromised remote, a hand-edited frontmatter claim) still never
    becomes visible through this studio's own composed index, even before
    check_publish_boundary's next validator pass would catch it in an
    audit.

    FAIL-CLOSED ON MISSING/CORRUPT MANIFEST (Argus A128 HEAVY-verify BOUNCE
    finding #1, 2026-07-09 — this function's PRIOR shape failed OPEN here,
    a real covenant leak, proven end-to-end: `if manifest_uid is not None`
    made the entire two-gate filter conditional on re-reading mount_path's
    OWN `.tropo/vault-manifest.md` — but tropo-publish.py's published
    orphan tree by construction NEVER contains that file (it only ever
    scans `vault/files/*.md`), so a REAL machine-B mount reflecting
    published team-main content has no manifest to re-read, and the old
    code let every record — argo-private/argo-reference/unmarked included
    — through unfiltered. The old inline disclosure ("mount-gate never
    admits a manifest-less mount, so this can't happen for real") was
    WRONG: mount-gate validates the ORIGINAL team-vault-root at MOUNT
    time; it says nothing about what's checked out later when this
    function re-scans mount_path's CURRENT working tree.

    THE FIX (findings #1 + #4 + #10 together — Argus's own three findings
    interlock and must be resolved as one): the scope gate
    (`is_public_scope`) now runs UNCONDITIONALLY — it can never be skipped,
    closing #1's fail-open outright. The segment gate is resolved two ways
    depending on what `mount_path` actually has available, per finding
    #10's own two named options:

      - Manifest PRESENT at mount_path (a real standalone checkout of the
        vault, not just the published branch): derive_segment reads it and
        the result is an INDEPENDENT cross-check against `vault_uid` — if
        they disagree, that mount_path's manifest does not actually match
        what compose.lock recorded for it, which is exactly finding #5's
        foreign-vault-uid-claim shape; excluded.
      - Manifest ABSENT (the realistic Machine-B case: a clone reflecting
        ONLY the published team-main branch, which by construction never
        carries `.tropo/vault-manifest.md`): there is nothing left to
        independently re-derive against, so `vault_uid` — established once
        at ORIGINAL mount-gate time, never re-derived from this same scan
        — is trusted directly as this content's segment (finding #10's
        "key B's segment derivation off compose.lock"). This is NOT a
        re-introduction of #1's fail-open: the scope gate above still
        excludes anything not provably public regardless of this branch.

    A record's own frontmatter `segment:` field, if present, is ALSO
    cross-checked against `vault_uid` in both branches — AC3's
    "frontmatter segment vs derived MISMATCH => ERROR": a disagreement is
    loud (raises), never silently resolved either direction.
    """
    from lib.segment import is_public_scope, derive_segment, read_vault_manifest_uid

    manifest_present = read_vault_manifest_uid(mount_path) is not None

    files_dir = mount_path / 'vault' / 'files'
    records: list[dict] = []
    for f in sorted(files_dir.glob('*.md')):
        rec = process_file(f)
        if rec is None:
            continue
        try:
            rel = f.relative_to(mount_path)
        except ValueError:
            rel = f

        raw_scope = rec.get('extraction_scope')
        claimed_segment = rec.get('segment')
        if claimed_segment is not None and str(claimed_segment) != str(vault_uid):
            raise ValueError(
                f"{rel} at {mount_path} carries frontmatter segment={claimed_segment!r} "
                f"which DISAGREES with the compose.lock-recorded vault_uid {vault_uid!r} "
                f"(AC3 mismatch — refusing rather than silently picking a side)"
            )

        if manifest_present:
            boundary_rec = {'uid': rec.get('uid'), 'extraction_scope': raw_scope, 'path': str(rel)}
            segment = derive_segment(boundary_rec, mount_path)
        else:
            segment = vault_uid

        if not is_public_scope(raw_scope) or segment != vault_uid:
            continue  # excluded outright — never enters the returned records at all

        rec['path'] = f'mounted/{vault_uid}/{rel}'
        rec['_shard_vault_uid'] = vault_uid
        records.append(rec)
    return records


def resolve_shards(
    vault_root: Path,
    process_file: Callable[[Path], Optional[dict[str, Any]]],
    now_iso: str,
    apply_writes: bool = True,
) -> tuple[list[dict], list[ShardStatus]]:
    """The incremental-reuse reconciliation pass (dev-spec c6f6bea4 §3
    steps 2-3, minus the local shard which the caller derives separately).

    For each vault_uid in compose.lock:
      - cache absent, OR cache .meta commit != pin, OR cache .meta's
        recorded jsonl_sha256 does not match the LIVE .jsonl file's actual
        hash (a crash-desynchronized pair — see write_shard/_hash_jsonl_bytes),
        OR mount_path unreachable AND cache absent/stale -> re-derive if
        mount_path IS reachable; otherwise CANNOT-COMPOSE (fail closed —
        never serve a stale/partial/desynchronized shard).
      - cache present AND .meta commit == pin AND jsonl_sha256 matches live
        content -> REUSE (no re-derivation, no write).
    Any cached shard whose vault_uid is no longer a compose.lock key is
    retired (removed from disk) — never unioned.

    SECURITY-REVIEW FIX (Talos T26, 2026-07-08): `apply_writes` gates every
    real disk write in this function (write_shard, retire_shard) — a
    dry-run (apply_writes=False) reconciles + reports statuses exactly as
    before but performs ZERO filesystem mutations under .tropo-studio/shards/,
    matching tropo-rebuild-index.py's own "DRY-RUN (no writes)" banner
    contract. Previously this function had no apply_writes parameter at all
    and always wrote/retired for real regardless of the caller's --apply
    flag — inert against today's real studio (no compose.lock exists yet)
    but a real violation of the dry-run contract once vaults are actually
    mounted. On a dry-run, a shard that WOULD be derived/retired is still
    correctly reflected in the returned statuses/mounted_records (so preview
    counts stay accurate) — only the disk write itself is skipped.

    Returns (mounted_records, statuses) — mounted_records is the flat union
    of every REUSED or newly-DERIVED shard's rows (cannot-compose shards
    contribute ZERO rows, by construction — the exclusion IS the fail-closed
    behavior, not a separate filter step downstream).
    """
    vaults = load_compose_lock_vaults(vault_root)
    pinned_uids = set(vaults.keys())
    cached_uids = list_cached_shard_uids(vault_root)

    statuses: list[ShardStatus] = []
    mounted_records: list[dict] = []

    for vault_uid, record in sorted(vaults.items()):
        pin = record.get('resolved_commit') if isinstance(record, dict) else None
        mount_path_str = record.get('mount_path') if isinstance(record, dict) else None

        if not pin:
            statuses.append(ShardStatus(vault_uid, 'cannot-compose', 'compose.lock record missing resolved_commit', None, 0))
            continue

        meta = read_shard_meta(vault_root, vault_uid)
        cached_records = read_shard_jsonl(vault_root, vault_uid)
        live_hash = _read_shard_jsonl_hash(vault_root, vault_uid) if meta is not None else None
        recorded_hash = meta.get('jsonl_sha256') if meta is not None else None
        cache_valid = (
            meta is not None
            and cached_records is not None
            and meta.get('resolved_commit') == pin
            and recorded_hash is not None
            and live_hash == recorded_hash
        )

        if cache_valid:
            statuses.append(ShardStatus(vault_uid, 'reused', None, pin, len(cached_records)))
            mounted_records.extend(cached_records)
            continue

        # Cache missing/stale/desynchronized — must re-derive from
        # mount_path. If mount_path is unreachable, this is CANNOT-COMPOSE
        # (fail closed), not a silent reuse of a stale/desynchronized cache
        # and not a silent skip.
        resolved_mount = mount_path_reachable(mount_path_str)
        if resolved_mount is None:
            desync_note = (
                ' (cache present but jsonl content hash does not match recorded '
                'jsonl_sha256 — a crash-desynchronized pair, treated as stale)'
                if meta is not None and recorded_hash is not None and live_hash != recorded_hash
                else ''
            )
            reason = (
                f'shard cache missing/stale (meta={meta!r}){desync_note} and mount_path '
                f'{mount_path_str!r} is unreachable — cannot re-derive'
            )
            statuses.append(ShardStatus(vault_uid, 'cannot-compose', reason, pin, 0))
            continue

        # SECURITY-REVIEW FIX (Argus A128 HEAVY-verify BOUNCE finding #8,
        # 2026-07-09): re-deriving from resolved_mount's LIVE working tree
        # with no check that HEAD actually equals the compose.lock pin, nor
        # that the tree is clean, meant a mutated/checked-out-elsewhere
        # working tree at a pinned mount would be silently scanned as if it
        # were the pinned, mount-gate-approved content. Assert both before
        # re-deriving; either failing is CANNOT-COMPOSE, not a best-effort
        # scan of whatever happens to be on disk.
        pin_mismatch_reason = pin_and_clean_violation(resolved_mount, pin)
        if pin_mismatch_reason:
            statuses.append(ShardStatus(vault_uid, 'cannot-compose', pin_mismatch_reason, pin, 0))
            continue

        derived = derive_mounted_shard_records(resolved_mount, process_file, vault_uid)
        if apply_writes:
            write_shard(vault_root, vault_uid, pin, derived, now_iso)
        statuses.append(ShardStatus(vault_uid, 'derived', None, pin, len(derived)))
        mounted_records.extend(derived)

    # Retire cached shards for vault_uids no longer in compose.lock.
    if apply_writes:
        for stale_uid in cached_uids - pinned_uids:
            retire_shard(vault_root, stale_uid)

    return mounted_records, statuses


def staleness_findings(vault_root: Path) -> list[ShardStatus]:
    """Read-only variant of the reconciliation check used by the VALIDATOR
    (tropo-validate.py's check_shard_index_consistency) — same reachability
    / pin-match logic as resolve_shards(), but NEVER re-derives or writes
    anything (a validator run must be side-effect-free). Returns the full
    per-vault_uid status list (including 'reused'/'stale-on-disk'/
    'cannot-compose'); the caller filters for cannot-compose to raise
    findings.
    """
    vaults = load_compose_lock_vaults(vault_root)
    statuses: list[ShardStatus] = []

    for vault_uid, record in sorted(vaults.items()):
        pin = record.get('resolved_commit') if isinstance(record, dict) else None
        mount_path_str = record.get('mount_path') if isinstance(record, dict) else None

        if not pin:
            statuses.append(ShardStatus(vault_uid, 'cannot-compose', 'compose.lock record missing resolved_commit', None, 0))
            continue

        meta = read_shard_meta(vault_root, vault_uid)
        cached_records = read_shard_jsonl(vault_root, vault_uid)

        if meta is None or cached_records is None:
            resolved_mount = mount_path_reachable(mount_path_str)
            reason = 'shard cache missing entirely'
            if resolved_mount is None:
                reason += f'; mount_path {mount_path_str!r} also unreachable'
            statuses.append(ShardStatus(vault_uid, 'cannot-compose', reason, pin, 0))
            continue

        cached_commit = meta.get('resolved_commit')
        if cached_commit != pin:
            resolved_mount = mount_path_reachable(mount_path_str)
            reason = f'shard cache stale — cached commit {cached_commit!r} != compose.lock pin {pin!r}'
            if resolved_mount is None:
                reason += f'; mount_path {mount_path_str!r} also unreachable (cannot self-heal on next rebuild)'
            statuses.append(ShardStatus(vault_uid, 'cannot-compose', reason, pin, len(cached_records)))
            continue

        # SECURITY-REVIEW FIX (Talos T26, 2026-07-08): commit-string agreement
        # alone is not sufficient — write_shard()'s two os.replace calls are
        # not one atomic transaction, so a crash between them can leave a
        # .jsonl/.meta pair whose commit strings happen to match again after
        # a later re-pin, but whose .jsonl content does NOT correspond to
        # that commit. Cross-verify the live .jsonl's actual hash against
        # .meta's recorded jsonl_sha256 before trusting the cache.
        recorded_hash = meta.get('jsonl_sha256')
        live_hash = _read_shard_jsonl_hash(vault_root, vault_uid)
        if recorded_hash is None or live_hash != recorded_hash:
            resolved_mount = mount_path_reachable(mount_path_str)
            reason = (
                f'shard cache DESYNCHRONIZED — commit matches pin ({pin!r}) but the live '
                f'.jsonl content hash ({live_hash!r}) does not match .meta\'s recorded '
                f'jsonl_sha256 ({recorded_hash!r}); a partial/crashed write is the likely '
                f'cause — never trusted on commit-match alone'
            )
            if resolved_mount is None:
                reason += f'; mount_path {mount_path_str!r} also unreachable (cannot self-heal on next rebuild)'
            statuses.append(ShardStatus(vault_uid, 'cannot-compose', reason, pin, len(cached_records)))
            continue

        statuses.append(ShardStatus(vault_uid, 'reused', None, pin, len(cached_records)))

    return statuses
