"""Gardener (Graph-GC Face A) — v1.82 federation-hardened decay stamping.

Implements dev-spec 8e551957 streams S0–S3 inside the rebuild-index pass.
Derived-index only (I5): never writes back to source .md frontmatter.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

MANIFEST_ROOT_UID = 'b2e7d4a9'
CONFIG_UID = 'be2296f9'
PRIVATE_SIDECAR = '.tropo-studio/gardener-wall-clock.json'

# ── Shared predicate constants (aligned with 7d08f2fb / 8dce9aec) ─────────────

LINEAGE_TYPES = frozenset({'activation', 'reflection'})
PRESERVE_TAGS = frozenset({
    'founding-lore', 'reflection', 'crew-genesis', 'preserve-class',
    'decision-of-record', 'tombstone',
})
OPEN_STATUSES = frozenset({
    'draft', 'active', 'proposed', 'design', 'in-progress', 'open',
    'pending', 'ready', 'review', 'blocked',
})
# Terminal for signal-1; published/locked/evergreen intentionally excluded.
TERMINAL_STATUSES = frozenset({
    'closed', 'done', 'shipped', 'retired', 'superseded', 'complete',
    'archived', 'cancelled', 'deprecated', 'tested', 'failed',
})
DEAD_PARENT_STATES = frozenset({'archived', 'deprecated', 'cancelled', 'retired'})
INBOUND_EDGE_FIELDS = frozenset({
    'refs', 'governed_by', 'composes_with', 'supersedes', 'aligned_with',
    'calls', 'mentions', 'implements', 'informs', 'related_to', 'derived_from',
    'bound_to',
})
DEFAULT_THRESHOLDS = {
    'decay_threshold_unshared_draft_days': 90,
    'decay_threshold_general_days': 180,
}
L2_BACKLOG_THRESHOLD_DAYS = 30  # Metis c27c741b §3D — NOT gardener config


def _parse_date(raw: Any) -> Optional[date]:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _norm_list(val: Any) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        return [val.strip()] if val.strip() else []
    if isinstance(val, list):
        return [str(v).strip() for v in val if v]
    return []


def _norm_tags(rec: dict) -> set[str]:
    tags = rec.get('tags') or []
    if isinstance(tags, str):
        tags = [tags]
    return {str(t).lower() for t in tags}




def _path_has_tropo_segment(path: str) -> bool:
    """True when `.tropo` appears as a path segment (not only at repo root)."""
    return any(part == '.tropo' for part in path.replace('\\', '/').split('/'))

def backfill_extraction_scope_by_path(path: str) -> Optional[str]:
    """S0 path-based extraction_scope backfill (derived index only)."""
    p = path.replace('\\', '/')
    if _path_has_tropo_segment(p):
        return 'ship'  # conservative: any .tropo/ segment → ship (os-layer)
    if p.startswith('agents/'):
        return 'argo-private'
    if p.startswith('vault/files/'):
        return 'argo-reference'
    if p.startswith('.tropo-studio/'):
        return 'argo-reference'
    if p.startswith('vault/tools/') or p.startswith('vault/capsules/'):
        return 'ship'
    if p.startswith('vault/actions/'):
        return 'ship'
    if p.startswith('vault/agents/') or p.startswith('vault/playbooks/'):
        return 'ship'
    return None  # unlisted — safety net handles


def safety_net_segment(path: str) -> str:
    """Conservative bucket for residual unscoped paths — never tag by silence."""
    p = path.replace('\\', '/')
    if _path_has_tropo_segment(p):
        return 'os'
    return 'private'


def compute_ship_manifest_uids(records: list[dict]) -> set[str]:
    """All UIDs transitively in the b2e7d4a9 ship-manifest graph."""
    by_uid = {r['uid']: r for r in records if r.get('uid')}
    manifest: set[str] = set()

    def reaches_manifest(uid: str, seen: set[str]) -> bool:
        if uid in seen:
            return False
        seen.add(uid)
        if uid == MANIFEST_ROOT_UID:
            return True
        rec = by_uid.get(uid)
        if not rec:
            return False
        for parent in _norm_list(rec.get('member_of')):
            if parent == MANIFEST_ROOT_UID or reaches_manifest(parent, seen):
                return True
        return False

    for rec in records:
        uid = rec.get('uid')
        if not uid:
            continue
        if uid == MANIFEST_ROOT_UID:
            manifest.add(uid)
            continue
        if MANIFEST_ROOT_UID in _norm_list(rec.get('member_of')):
            manifest.add(uid)
            continue
        if reaches_manifest(uid, set()):
            manifest.add(uid)
    return manifest


def discriminate_segment(
    rec: dict,
    effective_scope: Optional[str],
    ship_manifest_uids: set[str],
) -> str:
    """os iff extraction_scope:ship OR in ship-manifest; else private."""
    uid = rec.get('uid', '')
    if effective_scope == 'ship' or uid in ship_manifest_uids:
        return 'os'
    return 'private'


def resolve_effective_scope(rec: dict) -> tuple[str, bool]:
    """Return (effective extraction_scope, was_backfilled)."""
    scope = rec.get('extraction_scope')
    if scope:
        return str(scope), False
    path = rec.get('path', '')
    backfilled = backfill_extraction_scope_by_path(path)
    if backfilled:
        return backfilled, True
    # Unlisted path — safety net scope tag for segment only; scope stays absent
    return '', True


def load_gardener_config(vault_root: Path) -> dict[str, int]:
    """Load decay thresholds from be2296f9 or defaults."""
    cfg = dict(DEFAULT_THRESHOLDS)
    config_path = vault_root / 'vault' / 'files' / f'{CONFIG_UID}.md'
    if not config_path.exists():
        return cfg
    try:
        text = config_path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return cfg
    if not text.startswith('---'):
        return cfg
    end = text.find('\n---', 3)
    if end < 0:
        return cfg
    fm = text[3:end]
    for key in ('decay_threshold_unshared_draft_days', 'decay_threshold_general_days'):
        m = re.search(rf'^{re.escape(key)}:\s*["\']?(\d+)["\']?', fm, re.MULTILINE)
        if m:
            cfg[key] = int(m.group(1))
    return cfg


def repo_clock_date(vault_root: Path, records: list[dict]) -> date:
    """Repo-derived clock for byte-identical shared stamps (D-3)."""
    try:
        r = subprocess.run(
            ['git', 'log', '-1', '--format=%ci'],
            cwd=str(vault_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return date.fromisoformat(r.stdout.strip()[:10])
    except Exception:
        pass
    latest: Optional[date] = None
    for rec in records:
        for field in ('modified', 'created'):
            d = _parse_date(rec.get(field))
            if d and (latest is None or d > latest):
                latest = d
    return latest or date.today()


def is_preserve_class(rec: dict) -> bool:
    etype = str(rec.get('type') or '').lower()
    if etype in ('founding-lore', 'reflection', 'decision', 'adr'):
        return True
    tags = _norm_tags(rec)
    if tags & PRESERVE_TAGS:
        return True
    if rec.get('superseded_by') and str(rec.get('status') or '').lower() in ('done', 'superseded', 'active'):
        return True
    return False


def signal_lifecycle_contradiction(rec: dict) -> Optional[str]:
    if str(rec.get('type') or '') in LINEAGE_TYPES:
        return None
    state = str(rec.get('state') or '').lower()
    status = str(rec.get('status') or '').lower()
    if status in ('published', 'locked', 'evergreen'):
        return None
    if state == 'archived' and status in OPEN_STATUSES:
        return f'status:{status} on state:archived'
    if state == 'active' and status in TERMINAL_STATUSES:
        return f'status:{status} on state:active'
    return None


def signal_supersession(rec: dict, body: str = '') -> Optional[str]:
    if rec.get('superseded_by'):
        return f'superseded_by:{rec["superseded_by"]}'
    if re.search(r'(?:/SUPERSEDED|DO NOT BOOT)', body, re.I):
        return 'body-superseded-banner'
    return None


def _parent_dead(
    uid: str,
    by_uid: dict[str, dict],
    cache: dict[str, bool],
    visiting: Optional[set[str]] = None,
) -> bool:
    if visiting is None:
        visiting = set()
    if uid in cache:
        return cache[uid]
    if uid in visiting:
        cache[uid] = False
        return False
    visiting.add(uid)
    rec = by_uid.get(uid)
    if not rec:
        cache[uid] = False
        visiting.discard(uid)
        return False
    state = str(rec.get('state') or '').lower()
    status = str(rec.get('status') or '').lower()
    if state in DEAD_PARENT_STATES or status in ('deprecated', 'cancelled', 'archived'):
        cache[uid] = True
        visiting.discard(uid)
        return True
    parents = _norm_list(rec.get('member_of'))
    if not parents:
        cache[uid] = False
        visiting.discard(uid)
        return False
    dead = all(_parent_dead(p, by_uid, cache, visiting) for p in parents)
    cache[uid] = dead
    visiting.discard(uid)
    return dead


def signal_orphaned(rec: dict, by_uid: dict[str, dict]) -> Optional[str]:
    if str(rec.get('state') or '').lower() != 'active':
        return None
    if is_preserve_class(rec):
        return None
    homes = _norm_list(rec.get('member_of'))
    if not homes:
        return None
    cache: dict[str, bool] = {}
    if all(_parent_dead(h, by_uid, cache) for h in homes):
        return f'all member_of homes dead ({",".join(homes[:3])})'
    return None


def signal_machine_aged(
    rec: dict,
    as_of: date,
    machine_age_days: int = 14,
) -> Optional[str]:
    created_by = str(rec.get('created_by') or '')
    if not created_by.endswith('.py'):
        return None
    status = str(rec.get('status') or '').lower()
    if status not in OPEN_STATUSES:
        return None
    created = _parse_date(rec.get('created'))
    promoted = _parse_date(rec.get('promoted_at'))
    anchor = created
    if promoted and (not anchor or promoted > anchor):
        anchor = promoted
    if not anchor:
        return None
    age = (as_of - anchor).days
    if age > machine_age_days:
        return f'machine-authored {age}d open'
    return None


def false_positive_class(rec: dict) -> bool:
    """Metis G85 FP exclusions — adjudicated clean set (~6%, not raw ~55%)."""
    etype = str(rec.get('type') or '')
    if etype in LINEAGE_TYPES:
        return True
    state = str(rec.get('state') or '').lower()
    if state != 'active':
        return True
    status = str(rec.get('status') or '').lower()
    if status in ('published', 'locked', 'evergreen'):
        return True
    if state == 'archived' and status in TERMINAL_STATUSES:
        return True
    if is_preserve_class(rec):
        return True
    return False


def wall_clock_age_days(rec: dict, as_of: date) -> int:
    """D-3 raw owner-local wall-clock age (days idle) — one axis, two consumers."""
    modified = _parse_date(rec.get('modified'))
    created = _parse_date(rec.get('created'))
    promoted = _parse_date(rec.get('promoted_at'))
    anchor = modified or created
    if promoted and (not anchor or promoted > anchor):
        anchor = promoted
    if not anchor:
        return 0
    return max(0, (as_of - anchor).days)


def gardener_flags_stale(rec: dict, age_days: int, cfg: dict[str, int]) -> bool:
    """Apply configurable gardener thresholds (NOT L2's 30d)."""
    status = str(rec.get('status') or '').lower()
    if status == 'draft' and not _norm_list(rec.get('member_of')):
        return age_days >= cfg['decay_threshold_unshared_draft_days']
    return age_days >= cfg['decay_threshold_general_days']


def l2_backlog_counts(rec: dict, age_days: int) -> bool:
    """Metis L2 publish-backlog — independent 30d threshold on same raw age."""
    status = str(rec.get('status') or '').lower()
    if status != 'draft':
        return False
    if _norm_list(rec.get('member_of')):
        return False
    return age_days >= L2_BACKLOG_THRESHOLD_DAYS


def build_inbound_index(records: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """dst_uid -> [(src_uid, rel)] inbound edges."""
    inbound: dict[str, list[tuple[str, str]]] = {}
    for rec in records:
        src = rec.get('uid')
        if not src:
            continue
        for field in INBOUND_EDGE_FIELDS:
            vals = rec.get(field)
            if not vals:
                continue
            if isinstance(vals, str):
                vals = [vals]
            for dst in vals:
                if isinstance(dst, str) and dst.strip():
                    inbound.setdefault(dst.strip(), []).append((src, field))
    return inbound


def edge_crosses_segment(src_seg: str, dst_seg: str) -> bool:
    """I3 — private→os inbound breaks shared-field studio determinism (9219bd5a)."""
    return dst_seg == 'os' and src_seg == 'private'


def os_inbound_excluded_from_count(src_seg: str, dst_seg: str) -> bool:
    """OS nodes count inbound edges from os nodes only."""
    return dst_seg == 'os' and src_seg == 'private'


def build_illegal_member_of_edge_set(
    records: list[dict],
    by_uid: dict[str, dict],
    segments: dict[str, str],
) -> set[tuple[str, str]]:
    """4275b01c (ADR-051) — the set of (source_uid, target_uid) member_of
    pairs classified as ILLEGAL-BUT-PRESENT by the shared cross-vault
    member_of classifier (lib/cross_vault_member_of.py).

    member_of is NOT in INBOUND_EDGE_FIELDS (it never has been — ordinary
    project-hierarchy member_of edges are not treated as inbound-authority
    edges at all today). This function does not change that; it computes a
    SEPARATE exclusion set scoped to work-item member_of edges specifically,
    reusing the exact same classification logic
    check_cross_vault_member_of() (tropo-validate.py) uses, so the two
    surfaces cannot drift on what counts as illegal (dev-spec 4275b01c
    explicit requirement).

    Only work-item records' ADDITIONAL member_of edges are considered here
    (the primary grounding edge is same-vault by construction when valid,
    and is never a candidate for the audience-lattice legality check — see
    lib/cross_vault_member_of.classify_grounding docstring). Returns an
    empty set when there is no live vault-entity to ground against
    (matches check_cross_vault_member_of's own "nothing to validate"
    convention) — this function is a no-op on studios/fixtures with no
    vault-entity, never a source of new adjacency behavior in that case.
    """
    from lib.cross_vault_member_of import (
        classify_member_of_edges,
        default_two_segment_lattice,
    )

    vault_entity_home_node: dict[str, str] = {}
    for uid, rec in by_uid.items():
        if rec.get('type') == 'entity' and rec.get('subtype') == 'vault-entity':
            vault_entity_home_node[uid] = uid

    illegal: set[tuple[str, str]] = set()
    if not vault_entity_home_node:
        return illegal

    lattice = default_two_segment_lattice()
    work_item_types = {'task', 'work-item', 'workitem'}

    for rec in records:
        uid = rec.get('uid')
        if not uid or str(rec.get('type') or '') not in work_item_types:
            continue
        member_of_list = rec.get('member_of') or []
        if isinstance(member_of_list, str):
            member_of_list = [member_of_list]
        if not member_of_list:
            continue
        _grounding, edges = classify_member_of_edges(
            rec, by_uid, vault_entity_home_node, segments, lattice,
        )
        for edge in edges:
            if not edge.legal:
                illegal.add((edge.source_uid, edge.target_uid))
    return illegal


def compute_inbound_live_edges(
    uid: str,
    segment: str,
    stale_set: set[str],
    inbound: dict[str, list[tuple[str, str]]],
    segments: dict[str, str],
    by_uid: dict[str, dict],
    lint: list[str],
    illegal_member_of_edges: Optional[set[tuple[str, str]]] = None,
) -> int:
    illegal_member_of_edges = illegal_member_of_edges or set()
    count = 0
    for src, rel in inbound.get(uid, []):
        if src in stale_set:
            continue
        if not by_uid.get(src):
            continue
        if rel == 'member_of' and (src, uid) in illegal_member_of_edges:
            # 4275b01c: illegal-but-present cross-vault member_of edge —
            # excluded from adjacency + authority for ALL viewers (I3);
            # NOT dropped from the record, NOT silently walked. The
            # ERROR is raised by check_cross_vault_member_of()
            # (tropo-validate.py), which shares this exact classification.
            lint.append(
                f'I3-lint (4275b01c): {src}--member_of-->{uid} illegal-but-present '
                f'cross-vault edge — excluded from inbound_live_edges/adjacency'
            )
            continue
        src_seg = segments.get(src, 'private')
        if edge_crosses_segment(src_seg, segment):
            lint.append(f'I3-lint: {src}--{rel}-->{uid} cross-segment ({src_seg}->{segment})')
        if os_inbound_excluded_from_count(src_seg, segment):
            continue
        count += 1
    return count


def superseded_os_projection(rec: dict, segment: str) -> bool:
    """S3 — walked-but-flagged superseded OS nodes."""
    if segment != 'os':
        return False
    if not rec.get('superseded_by'):
        return False
    state = str(rec.get('state') or '').lower()
    status = str(rec.get('status') or '').lower()
    return state in ('archived', 'deprecated', 'cancelled', 'retired') or status in (
        'superseded', 'archived', 'done', 'deprecated', 'cancelled', 'retired',
    )


def cross_segment_supersession(rec: dict, by_uid: dict[str, dict], segments: dict[str, str]) -> bool:
    """Private artifact must not supersede-claim a team/os node."""
    target = rec.get('supersedes')
    if not target:
        return False
    targets = [target] if isinstance(target, str) else list(target)
    my_seg = segments.get(rec.get('uid', ''), 'private')
    for t in targets:
        if segments.get(t, 'private') != my_seg and my_seg == 'private':
            return True
    return False


def apply_gardener_pass(
    vault_root: Path,
    records: list[dict],
    apply_writes: bool,
) -> dict[str, Any]:
    """Run S0→S3 gardener pass; mutate records in place (derived index only)."""
    ship_manifest = compute_ship_manifest_uids(records)
    cfg = load_gardener_config(vault_root)
    repo_clock = repo_clock_date(vault_root, records)
    wall_clock = date.today()  # private overlay uses wall-clock

    by_uid = {r['uid']: r for r in records if r.get('uid')}
    effective_scopes: dict[str, str] = {}
    segments: dict[str, str] = {}
    backfill_count = 0

    # ── S0: extraction_scope backfill + segment discriminator ──
    for rec in records:
        uid = rec.get('uid')
        if not uid:
            continue
        scope, was_bf = resolve_effective_scope(rec)
        if was_bf and scope:
            rec['extraction_scope'] = scope
            backfill_count += 1
        elif was_bf and not scope:
            backfill_count += 1
        effective_scopes[uid] = scope or rec.get('extraction_scope') or ''
        seg = discriminate_segment(rec, effective_scopes[uid] or None, ship_manifest)
        if not effective_scopes[uid] and seg != 'os':
            seg = safety_net_segment(rec.get('path', ''))
        segments[uid] = seg
        rec['segment'] = seg

    unscoped_after = sum(
        1 for r in records
        if r.get('uid') and not r.get('extraction_scope')
    )

    # ── Per-segment signal pass (S1) ──
    raw_signals: dict[str, list[str]] = {}
    reasons: dict[str, str] = {}
    stale_raw: set[str] = set()
    stale_clean: set[str] = set()
    superseded_os: set[str] = set()
    lint: list[str] = []
    bodies: dict[str, str] = {}

    for rec in records:
        uid = rec.get('uid')
        if not uid:
            continue
        seg = segments[uid]
        as_of = repo_clock if seg == 'os' else wall_clock
        sigs: list[str] = []

        s1 = signal_lifecycle_contradiction(rec)
        if s1:
            sigs.append('lifecycle-contradiction')
            reasons.setdefault(uid, s1)
        s2 = signal_supersession(rec)
        if s2:
            sigs.append('superseded')
            reasons.setdefault(uid, s2)
        s3 = signal_orphaned(rec, by_uid)
        if s3:
            sigs.append('orphaned-by-dead-parent')
            reasons.setdefault(uid, s3)
        s4 = signal_machine_aged(rec, as_of)
        if s4:
            sigs.append('machine-aged')
            reasons.setdefault(uid, s4)

        if cross_segment_supersession(rec, by_uid, segments):
            lint.append(f'cross-segment-supersession-blocked:{uid}')

        if superseded_os_projection(rec, seg):
            superseded_os.add(uid)
            rec['superseded_os'] = True
            rec['superseded_by_projection'] = rec.get('superseded_by')

        raw_signals[uid] = sigs
        if sigs:
            stale_raw.add(uid)
        if sigs and not false_positive_class(rec):
            stale_clean.add(uid)

    # ── S2: wall-clock overlay (private segment) ──
    private_ages: dict[str, int] = {}
    for rec in records:
        uid = rec.get('uid')
        if not uid or segments.get(uid) != 'private':
            continue
        age = wall_clock_age_days(rec, wall_clock)
        private_ages[uid] = age
        rec['wall_clock_age_days'] = age
        if gardener_flags_stale(rec, age, cfg) and not false_positive_class(rec):
            stale_raw.add(uid)
            stale_clean.add(uid)
            if 'wall-clock-stale' not in raw_signals.get(uid, []):
                raw_signals.setdefault(uid, []).append('wall-clock-stale')
                reasons.setdefault(uid, f'wall-clock idle {age}d')

    # Stamp decay block (adjudicated clean set)
    for rec in records:
        uid = rec.get('uid')
        if not uid:
            continue
        seg = segments[uid]
        swept = repo_clock.isoformat() if seg == 'os' else wall_clock.isoformat()
        is_stale = uid in stale_clean
        rec['decay'] = {
            'stale': is_stale,
            'signals': raw_signals.get(uid, []),
            'reason': reasons.get(uid, ''),
            'confidence': 0.9 if is_stale else 0.0,
            'swept': swept,
        }

    stale_set = stale_clean
    inbound = build_inbound_index(records)

    # 4275b01c (ADR-051) — illegal-but-present cross-vault member_of edges
    # are excluded from adjacency/authority for ALL viewers (I3). Computed
    # via the SAME shared classifier check_cross_vault_member_of()
    # (tropo-validate.py) uses, so the two surfaces cannot drift.
    illegal_member_of_edges = build_illegal_member_of_edge_set(records, by_uid, segments)

    for rec in records:
        uid = rec.get('uid')
        if not uid:
            continue
        seg = segments[uid]
        rec['inbound_live_edges'] = compute_inbound_live_edges(
            uid, seg, stale_set, inbound, segments, by_uid, lint,
            illegal_member_of_edges=illegal_member_of_edges,
        )

    # Private sidecar (I5 — never synced to shared repo fields on source)
    sidecar_path = vault_root / PRIVATE_SIDECAR
    sidecar = {
        'wall_clock_as_of': wall_clock.isoformat(),
        'private_ages': private_ages,
        'thresholds': cfg,
        'l2_backlog_threshold_days': L2_BACKLOG_THRESHOLD_DAYS,
    }
    if apply_writes:
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(json.dumps(sidecar, indent=2) + '\n', encoding='utf-8')

    stats = {
        'backfill_count': backfill_count,
        'unscoped_after': unscoped_after,
        'raw_stale_count': len(stale_raw),
        'clean_stale_count': len(stale_clean),
        'superseded_os_count': len(superseded_os),
        'lint_count': len(lint),
        'repo_clock': repo_clock.isoformat(),
    }
    return stats
