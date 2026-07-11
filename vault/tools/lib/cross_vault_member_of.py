"""Cross-vault member_of primitive (dev-spec 4275b01c, ADR-051).

Implements the per-vault D7 grounding generalization + the up-lattice-only
cross-vault member_of edge legality rule, reconciled with the signed
boundary law (I3, dd16c90c / c2b1b612 §3 v2.1) and the audience lattice
(5d3ab142 §3).

SHARED MODULE — this is the single classification authority. Both
tropo-validate.py's check_cross_vault_member_of() (validator ERRORs) and
tropo-rebuild-index.py's composed-index edge layer (adjacency/
inbound_live_edges exclusion, via lib/gardener.py) import and call the
SAME functions here — the dev-spec explicitly requires this ("reuse the
SAME classification function/logic, do not reimplement it a second time
with different rules that could drift").

## Primary vs. additional member_of — the classification rule this module
adopts (judgment call; no field name is given by the dev-spec or by
f2e8a7b1's schema)

f2e8a7b1 §3.1 / §8.1 only requires "member_of: non-empty; at least one
entry is vault-entity-owned". There is no `primary_member_of:` field and
no ordering contract stated anywhere in the schema. This module adopts the
principled rule stated in the dev-spec's own framing of the "likely" shape:

    The PRIMARY grounding edge is the FIRST entry in a record's member_of
    list (in declared frontmatter order) that resolves — directly, or
    transitively through a chain of `type: project` records' own
    member_of/owner edges — to a project owned by a vault-entity homed in
    the SAME vault-node as the record itself (same-vault, exactly, per
    §2a — not merely equal-or-wider).

    Every OTHER entry in member_of is an ADDITIONAL edge, classified
    against the audience lattice (§2b): legal iff its target's segment is
    equal-or-wider than the record's own segment.

Why first-in-list, not "any that qualifies": member_of is declared in
frontmatter as an ordered YAML list; the record's author put something
first. Treating the first same-vault-resolving entry as canonical gives a
deterministic, mechanically-checkable rule (no ambiguity about which of N
qualifying entries is "the" anchor) while still tolerating the common
real-world shape where a record's true grounding project isn't literally
member_of[0] (e.g. a tag comes before the project). If NO entry resolves
same-vault, the record has no primary grounding at all — the D7-per-vault
violation (this is different from "zero entries", the already-existing
bare-orphan case f2e8a7b1 covers; this module's job is the NEW case: entries
exist, but none of them ground in this vault-node).

## Segment/audience source (grounding finding, disclosed)

There is no live per-vault-root manifest infrastructure yet (943bb220 §1,
409ef1cc's own grounding): "zero live type:vault instances" today. This
module's `classify_member_of_edges()` takes `segments: dict[uid -> str]`
and `group_lattice: GroupLattice` as PARAMETERS — it does not itself
discover per-vault-node segment tags or a live group registry, because
neither exists as real substrate in this studio today. Callers wire real
data when it exists (the composed index's `segment` field, once vault
manifests are real) or fixture data (tests). See GroupLattice below for
the audience-lattice fixture contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# The audience lattice (5d3ab142 §3) — group-subset checks
# ---------------------------------------------------------------------------

OS_SEGMENT = 'os'  # universally visible (5d3ab142 §3: "OS is universally visible")


@dataclass
class GroupLattice:
    """Fixture/real audience-lattice: declared group-subset edges.

    `wider[g]` = the set of groups that are equal-or-wider than `g` (i.e. `g`
    may legally reference something homed in any group in `wider[g]`),
    INCLUDING `g` itself (same-segment is always legal — §2b "Same-segment
    (equal) is legal"). `OS_SEGMENT` is implicitly wider than every group —
    a caller need not enumerate it in every entry.

    This is a FIXTURE-CONSTRUCTABLE contract, not a live-registry reader:
    5d3ab142 §3 names "the group registry" as the intended real mechanism
    but no `type: group` entries or group-registry file exist in this
    studio yet (grounding finding). Real integration is future work; this
    dataclass is the shape a live reader would populate.
    """
    wider: dict[str, set[str]] = field(default_factory=dict)

    def is_legal_target(self, source_segment: str, target_segment: str) -> bool:
        """True iff target_segment is equal-or-wider than source_segment."""
        if source_segment == target_segment:
            return True
        if target_segment == OS_SEGMENT:
            return True
        allowed = self.wider.get(source_segment, set())
        return target_segment in allowed or target_segment == source_segment

    def relation(self, source_segment: str, target_segment: str) -> str:
        """Classify the pair: 'equal' | 'up' | 'down' | 'incomparable'."""
        if source_segment == target_segment:
            return 'equal'
        if self.is_legal_target(source_segment, target_segment):
            # Wider-but-not-equal. Check if the reverse direction also holds
            # (both wider than each other only happens if segments alias —
            # treat as 'up' since forward direction is what's being asked).
            return 'up'
        # Not legal source->target. Is target actually NARROWER (down), or
        # simply unrelated (incomparable)? target is narrower than source
        # iff source is in target's wider-set.
        if source_segment in self.wider.get(target_segment, set()) or source_segment == OS_SEGMENT:
            return 'down'
        return 'incomparable'


def default_two_segment_lattice() -> GroupLattice:
    """The real live studio's current lattice: exactly {os, private}.

    os is universally wider; private has no declared wider-peers besides
    itself and os. This matches the ONLY segments that exist in the real
    00-index.jsonl today (grounding finding: Counter({'private': 3601,
    'os': 548}), zero 'team:<uid>' segments live).
    """
    return GroupLattice(wider={'private': set()})


# ---------------------------------------------------------------------------
# member_of list parsing
# ---------------------------------------------------------------------------

def _norm_list(val) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        return [val.strip()] if val.strip() else []
    if isinstance(val, list):
        return [str(v).strip() for v in val if v]
    return []


# ---------------------------------------------------------------------------
# Vault-node grounding root resolution
# ---------------------------------------------------------------------------

def resolve_project_vault_node(
    project_uid: str,
    by_uid: dict[str, dict],
    vault_entity_home_node: dict[str, str],
    segments: Optional[dict[str, str]] = None,
    seen: Optional[set[str]] = None,
) -> Optional[str]:
    """Resolve the vault-node UID a `type: project` record grounds in.

    CORRECTNESS FIX (Talos T26, 2026-07-08, found by running this check
    against the real vault before reporting BUILT): PRIMARY resolution
    trusts the project's OWN `segments` tag directly (the dev-spec's own
    §3 rule — "each record's home vault-node is its nearest-enclosing
    manifest," applied uniformly to every record, not just work-items).
    Live proof of the bug this fixes: a private-segment task's ONLY
    member_of entry was a private-segment project (01-inbox, 61049010) —
    itself same-vault by its OWN segment tag — but the OLD owner/member_of
    chain-walk kept recursing through 61049010's OTHER member_of siblings
    (also private) until it happened to reach one sibling's OWN sibling
    that carried an unrelated os-segment member_of edge, and returned
    'os' from THAT distant branch — a false foreign-primary flag on a
    genuinely same-vault record. Segment tags are already the
    authoritative, gardener-assigned home-node source (used directly for
    work-items elsewhere in this module); there is no principled reason
    to re-derive a project's home via a chain walk that can wander into
    unrelated sibling branches when the project's own tag already answers
    the question directly and correctly.

    Resolution order:
    1. If `segments[project_uid]` is a tag some real vault-entity anchors
       (i.e. present in `vault_entity_home_node.values()`), return it
       directly — no walk needed. This is the common, correct case for
       any record the gardener has already tagged (which is every real
       record today; `segments` defaults every UID to 'private').
    2. FALLBACK (defensive; for a record with no segment tag, or a
       segment no live vault-entity anchors yet — e.g. a future 'team:*'
       segment before its own vault-entity exists): walk
       project.owner -> vault-entity UID -> vault_entity_home_node
       lookup, then member_of parents, exactly as before. This path is
       structurally unreachable on today's real substrate (every record
       has a segment tag), kept for the future multi-vault case the
       dev-spec names, not exercised by real data today.

    Returns None if no chain reaches a known vault-entity (bare orphan —
    a DIFFERENT, pre-existing failure class this module does not re-flag).
    """
    if seen is None:
        seen = set()
    if project_uid in seen:
        return None  # cycle guard
    seen.add(project_uid)

    rec = by_uid.get(project_uid)
    if not rec:
        return None

    if segments is not None:
        own_segment = segments.get(project_uid)
        if own_segment is not None and own_segment in vault_entity_home_node.values():
            return own_segment

    owner = rec.get('owner')
    if isinstance(owner, str) and owner in vault_entity_home_node:
        return vault_entity_home_node[owner]

    # owner didn't resolve directly to a vault-entity — try walking owner
    # as a further project/entity chain, then member_of parents.
    if isinstance(owner, str) and owner in by_uid:
        via_owner = resolve_project_vault_node(owner, by_uid, vault_entity_home_node, segments, seen)
        if via_owner:
            return via_owner

    for parent in _norm_list(rec.get('member_of')):
        via_parent = resolve_project_vault_node(parent, by_uid, vault_entity_home_node, segments, seen)
        if via_parent:
            return via_parent

    return None


@dataclass
class GroundingResult:
    grounded: bool
    primary_uid: Optional[str]           # the member_of entry treated as primary
    primary_home_node: Optional[str]      # vault-node UID the primary traces to
    record_home_node: Optional[str]       # the record's OWN home vault-node (its segment)
    foreign_primary: bool                 # primary resolves to a DIFFERENT node's vault-entity
    additional_uids: list[str]            # every other member_of entry


def classify_grounding(
    rec: dict,
    by_uid: dict[str, dict],
    vault_entity_home_node: dict[str, str],
    segments: dict[str, str],
) -> GroundingResult:
    """Per-vault-node D7 primary-grounding classification (dev-spec §3).

    `segments[uid]` gives each record's own home vault-node (today: the
    composed index's `segment` field — see module docstring on why this is
    injected, not discovered here).
    """
    uid = rec.get('uid', '')
    record_home = segments.get(uid)
    member_of_list = _norm_list(rec.get('member_of'))

    primary_uid: Optional[str] = None
    primary_home: Optional[str] = None

    for candidate in member_of_list:
        home = resolve_project_vault_node(candidate, by_uid, vault_entity_home_node, segments)
        if home is not None and home == record_home:
            primary_uid = candidate
            primary_home = home
            break

    if primary_uid is None:
        # No same-vault-resolving entry. Check whether ANY entry resolves
        # to a DIFFERENT node's vault-entity (foreign-primary, D7-per-vault
        # violation) vs. none resolving anywhere at all (bare orphan, an
        # existing/different failure class this module does not re-flag).
        for candidate in member_of_list:
            home = resolve_project_vault_node(candidate, by_uid, vault_entity_home_node, segments)
            if home is not None:
                additional = [u for u in member_of_list if u != candidate]
                return GroundingResult(
                    grounded=False,
                    primary_uid=candidate,
                    primary_home_node=home,
                    record_home_node=record_home,
                    foreign_primary=True,
                    additional_uids=additional,
                )
        # Nothing resolved anywhere — bare orphan, not this module's class.
        return GroundingResult(
            grounded=False,
            primary_uid=None,
            primary_home_node=None,
            record_home_node=record_home,
            foreign_primary=False,
            additional_uids=list(member_of_list),
        )

    additional = [u for u in member_of_list if u != primary_uid]
    return GroundingResult(
        grounded=True,
        primary_uid=primary_uid,
        primary_home_node=primary_home,
        record_home_node=record_home,
        foreign_primary=False,
        additional_uids=additional,
    )


# ---------------------------------------------------------------------------
# Additional-edge legality classification (§2b, §2c)
# ---------------------------------------------------------------------------

@dataclass
class EdgeClassification:
    source_uid: str
    target_uid: str
    source_segment: str
    target_segment: str
    relation: str        # 'equal' | 'up' | 'down' | 'incomparable'
    legal: bool


def classify_additional_edge(
    source_uid: str,
    target_uid: str,
    segments: dict[str, str],
    lattice: GroupLattice,
) -> EdgeClassification:
    """Classify one ADDITIONAL member_of edge against the audience lattice.

    Same-segment (equal) and up-lattice (strictly wider target) are LEGAL.
    Down-lattice (narrower target) and incomparable are ILLEGAL-BUT-PRESENT
    (I3 semantics — excluded from adjacency/authority, raised as lint
    ERROR; never dropped from the record, never silently walked).
    """
    src_seg = segments.get(source_uid, 'private')
    dst_seg = segments.get(target_uid, 'private')
    relation = lattice.relation(src_seg, dst_seg)
    legal = relation in ('equal', 'up')
    return EdgeClassification(
        source_uid=source_uid,
        target_uid=target_uid,
        source_segment=src_seg,
        target_segment=dst_seg,
        relation=relation,
        legal=legal,
    )


def classify_member_of_edges(
    rec: dict,
    by_uid: dict[str, dict],
    vault_entity_home_node: dict[str, str],
    segments: dict[str, str],
    lattice: GroupLattice,
) -> tuple[GroundingResult, list[EdgeClassification]]:
    """Full per-record classification: grounding + every additional edge.

    This is the SINGLE entry point both tropo-validate.py and the
    composed-index edge layer (gardener.py) call — the one classification
    authority the dev-spec requires not be duplicated.
    """
    grounding = classify_grounding(rec, by_uid, vault_entity_home_node, segments)
    edges = [
        classify_additional_edge(rec.get('uid', ''), target, segments, lattice)
        for target in grounding.additional_uids
    ]
    return grounding, edges
