"""lib/task_circle.py — the distiller's deterministic scope-drawing (draw_circle)
(dev-spec e12ff178; paired test-spec ee37d652; cycle brief 6da0d037 §5/§9).

The distiller's three moves are **draw a circle -> walk -> distill**
(``6da0d037`` §5 Face B). The viewer-relative *walk* landed in ``5043b274`` as
:mod:`lib.viewer_projection`. This module draws the **circle** that seeds it: the
deterministic scope of the relevant knowledge domain for a piece of work, drawn
from the work's OWN structure, expanded through the viewer-relative walk (so it
is private-safe by construction), with the gardener's rot rejected, every member
citing why it was included.

Design (``e12ff178`` §The design), in four moves:

1. **Seeds from structure (deterministic, NO model).** The task already encodes
   intent in structure (``6da0d037`` §9 decision 2), so seed derivation is a
   graph/index read, never a model router. Seeds are the task's DIRECT
   structural edges — ``governed_by``, ``refs``, ``member_of`` parents, and the
   task's direct neighbours — plus ONE structural hop for ``member_of``
   ancestors (grandparents) and same-project ``type``-siblings. No unbounded
   transitive closure.
2. **Expand through the walk (viewer-safe by construction).** EVERY neighbour
   lookup — both admitting a structural seed and every expansion hop beyond it —
   routes through :meth:`ViewerProjection.adjacency`. The circle therefore
   inherits the four co-signed invariants of ``5043b274`` and can never contain
   a node outside ``visible_segments(viewer)``, nor betray a hidden one. This
   module NEVER reads a raw graph edge for a *visibility* decision and NEVER
   derives a segment itself — that would re-open the leak class ``5043b274``
   closed.
3. **Decay-gate (reject rot).** A node the gardener flagged
   (``decay.stale`` is true AND ``decay.confidence >= DECAY_GATE_CONFIDENCE``) is
   excluded from the circle, and expansion never traverses THROUGH it (dead
   edges are not walked — only live edges count). A flagged-but-below-threshold
   node is KEPT.
4. **Auditable circle out.** :func:`draw_circle` returns a :class:`Circle`: an
   ordered, deterministic set of :class:`CircleMember` values, each carrying its
   inclusion provenance (the structural relation or seed path that admitted it,
   citing UIDs) and a :meth:`Circle.canonical` byte-stable surface.

Explicit exclusions (``e12ff178`` §Explicit exclusions): NO relevance
ranking/scoring (there is no score field; ordering is structural — by
seed-distance then UID), NO distillation to chunks, NO model/network calls, and
NO independently re-implemented visibility/neighbour filtering.

The types are REUSED, never re-invented: :class:`~lib.group_registry.Result`
(the ``ok/value/error`` convention) and :class:`~lib.viewer_projection.GraphError`
/ :class:`~lib.viewer_projection.GraphErrorCode` are the same objects the walk
raises, so a refusal propagates transitively and typed.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

# The typed Result convention + the walk's typed errors — REUSED, not parallel. #
from lib.group_registry import Result  # noqa: E402
from lib.decay_gate import DECAY_GATE_CONFIDENCE, is_decayed  # noqa: E402
from lib.distiller_query import (  # noqa: E402
    PrevalidatedQuerySeeds,
    QueryError,
    QueryErrorCode,
)
from lib.viewer_projection import (  # noqa: E402
    GraphError,
    GraphErrorCode,
    Viewer,
    ViewerProjection,
)


# --------------------------------------------------------------------------- #
# Provenance vocabulary. Each admitted node carries exactly one reason; when a #
# node qualifies via several relations the lowest structural distance wins,    #
# ties broken by this fixed relation priority, so the label is deterministic.  #
# --------------------------------------------------------------------------- #
REL_GOVERNED_BY = "governed_by-of-task"
REL_REF = "ref-of-task"
REL_MEMBER_PARENT = "member_of-parent"
REL_MEMBER_ANCESTOR = "member_of-ancestor"
REL_TYPE_SIBLING = "type-sibling"
REL_NEIGHBOR = "neighbor-of-task"
REL_WALK_HOP = "walk-hop-from"
REL_QUERY_SEED = "query-seed"

REFERENCE_MISSING_INDEX_ENTRY = "missing-index-entry"
REFERENCE_NON_UID_OR_INVALID = "non-uid-external-or-invalid-shape"

# Relation priority (lower == preferred when two relations tie on distance).
_REL_PRIORITY = {
    REL_GOVERNED_BY: 0,
    REL_REF: 1,
    REL_MEMBER_PARENT: 2,
    REL_MEMBER_ANCESTOR: 3,
    REL_TYPE_SIBLING: 4,
    REL_NEIGHBOR: 5,
    REL_WALK_HOP: 6,
    REL_QUERY_SEED: 7,
}


@dataclass(frozen=True)
class CircleMember:
    """One member of the drawn circle.

    ``uid`` is the member. ``distance`` is the number of structural/walk hops
    from the task (direct structural seeds are 1, the single ancestor/sibling
    hop is 2, walk expansion is seed-distance + hop-count). ``relation`` is the
    inclusion-provenance kind (one of the ``REL_*`` constants) and ``via`` is the
    UID the relation is anchored on (the task for a direct seed, the parent for
    an ancestor/sibling, the popped seed for a walk hop) — so provenance always
    cites a UID and a human can audit why the node was admitted.

    There is deliberately NO score / rank / weight field: this cut is membership
    + provenance only (``e12ff178`` §Explicit exclusions).
    """

    uid: str
    distance: int
    relation: str
    via: str

    @property
    def provenance(self) -> str:
        """A human-auditable, UID-citing inclusion reason, e.g.
        ``"ref-of-task:<task_uid>"`` or ``"walk-hop-from:<seed_uid>"``."""

        return f"{self.relation}:{self.via}"

    def _sort_key(self) -> tuple:
        return (self.distance, self.uid, _REL_PRIORITY.get(self.relation, 99), self.via)


@dataclass(frozen=True)
class ReferenceObservation:
    """A visible graph reference that is not an indexed, body-bearing entry.

    Observations are diagnostics, never circle members. ``raw_target`` preserves
    the target exactly as the graph exposed it; ``via`` / ``relation`` /
    ``distance`` preserve where the circle encountered it. Visibility filtering
    happens before this value is created, so diagnostics cannot reveal a target
    the viewer was not already allowed to observe.
    """

    raw_target: str
    via: str
    relation: str
    distance: int
    classification: str

    @property
    def provenance(self) -> str:
        return f"{self.relation}:{self.via}"

    def _sort_key(self) -> tuple:
        return (
            self.distance,
            self.raw_target,
            _REL_PRIORITY.get(self.relation, 99),
            self.via,
            self.classification,
        )


def _reference_classification(raw_target: object) -> str:
    if (
        isinstance(raw_target, str)
        and len(raw_target) == 8
        and all(char in "0123456789abcdefABCDEF" for char in raw_target)
    ):
        return REFERENCE_MISSING_INDEX_ENTRY
    return REFERENCE_NON_UID_OR_INVALID


class _ReferenceObservationCollector:
    """Deterministic de-duplicating collector internal to one circle draw."""

    def __init__(self) -> None:
        self._observations: dict[tuple, ReferenceObservation] = {}

    def offer(self, raw_target: object, distance: int, relation: str, via: str) -> None:
        raw_value = raw_target if isinstance(raw_target, str) else repr(raw_target)
        observation = ReferenceObservation(
            raw_target=raw_value,
            via=via,
            relation=relation,
            distance=distance,
            classification=_reference_classification(raw_target),
        )
        key = (observation.raw_target, observation.via, observation.relation)
        current = self._observations.get(key)
        if current is None or observation._sort_key() < current._sort_key():
            self._observations[key] = observation

    def add(self, observation: ReferenceObservation) -> None:
        self.offer(
            observation.raw_target,
            observation.distance,
            observation.relation,
            observation.via,
        )

    def values(self) -> tuple:
        return tuple(sorted(self._observations.values(), key=lambda item: item._sort_key()))


@dataclass(frozen=True)
class Circle:
    """An auditable, deterministic circle: the relevant-domain membership drawn
    for ``task_uid`` for a specific ``viewer``.

    ``members`` is an immutable tuple in deterministic stable order (by
    seed-distance, then UID) — a STRUCTURAL ordering, explicitly NOT a relevance
    rank. ``reference_observations`` is an additive diagnostic tuple for visible
    edge targets that have no indexed entry; those targets are never members.
    :meth:`canonical` is a byte-stable surface for the invariant-4 leak property
    test (mirrors :meth:`lib.viewer_projection.Subgraph.canonical`).
    """

    task_uid: str
    members: tuple
    reference_observations: tuple = ()

    def uids(self) -> tuple:
        """The member UIDs in the circle's deterministic order."""

        return tuple(m.uid for m in self.members)

    def reason(self, uid: str) -> Optional[str]:
        """The inclusion provenance string for ``uid``, or ``None`` if ``uid`` is
        not in the circle."""

        for member in self.members:
            if member.uid == uid:
                return member.provenance
        return None

    def canonical(self) -> str:
        import json

        payload = {
            "task": self.task_uid,
            "members": [
                {
                    "uid": m.uid,
                    "distance": m.distance,
                    "relation": m.relation,
                    "via": m.via,
                }
                for m in self.members
            ],
        }
        if self.reference_observations:
            payload["reference_observations"] = [
                {
                    "raw_target": observation.raw_target,
                    "classification": observation.classification,
                    "distance": observation.distance,
                    "relation": observation.relation,
                    "via": observation.via,
                }
                for observation in self.reference_observations
            ]
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )


# --------------------------------------------------------------------------- #
# Structural index — the task's OWN structure + the gardener decay signal.     #
#                                                                              #
# This is READ-ONLY structural metadata for SEED DERIVATION and the DECAY      #
# GATE only: typed relations (member_of / refs / governed_by), the node type,  #
# reverse member_of (children, for type-sibling candidates), and the decay     #
# object. It NEVER makes a visibility decision and NEVER derives a segment —    #
# all visibility is decided by ViewerProjection.adjacency. Candidates surfaced #
# here are admitted ONLY if the projection also returns them as visible         #
# neighbours, so a hidden structural edge can never leak into the circle.      #
# --------------------------------------------------------------------------- #
class StructuralIndex:
    """Read-only structural + decay metadata over the composed union index."""

    index_as_of: Optional[str] = None

    def structure(self, uid: str) -> Optional[dict]:  # pragma: no cover - interface
        """``{"type": str, "member_of": [uid], "refs": [uid],
        "governed_by": [uid], "decay": {...}|None}`` for ``uid``, or ``None`` if
        the entry is not indexed."""

        raise NotImplementedError

    def children_of(self, parent_uid: str) -> list:  # pragma: no cover - interface
        """UIDs whose ``member_of`` contains ``parent_uid`` (reverse member_of) —
        the type-sibling *candidate* pool. Visibility is still decided by the
        projection; this only enumerates structural candidates."""

        raise NotImplementedError


def _as_uid_list(value) -> list:
    """Normalise a frontmatter relation field (scalar, list, or None) to a list
    of UID strings, deterministically de-duplicated in first-seen order."""

    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list = []
    seen: set = set()
    for item in items:
        if isinstance(item, str) and item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


class InMemoryStructuralIndex(StructuralIndex):
    """In-memory structural index (sandbox fixture parity with
    :class:`lib.viewer_projection.InMemoryGraphSource`).

    ``structures`` maps a node UID to a partial record; missing relation fields
    default to empty and a missing ``type`` defaults to ``""``.
    """

    def __init__(
        self, structures: Mapping[str, dict], *, index_as_of: Optional[str] = None
    ) -> None:
        self._structures = {uid: dict(rec) for uid, rec in structures.items()}
        self.index_as_of = index_as_of
        # Precompute reverse member_of for deterministic children_of.
        self._children: dict = {}
        for uid in sorted(self._structures):
            for parent in _as_uid_list(self._structures[uid].get("member_of")):
                self._children.setdefault(parent, []).append(uid)

    def structure(self, uid: str) -> Optional[dict]:
        rec = self._structures.get(uid)
        if rec is None:
            return None
        return {
            "type": rec.get("type") or "",
            "member_of": _as_uid_list(rec.get("member_of")),
            "refs": _as_uid_list(rec.get("refs")),
            "governed_by": _as_uid_list(rec.get("governed_by")),
            "decay": rec.get("decay"),
        }

    def children_of(self, parent_uid: str) -> list:
        return list(self._children.get(parent_uid, []))


class SqliteStructuralIndex(StructuralIndex):
    """Production structural index over the composed union index
    (``vault/00-index.sqlite``). Read-only; never a writer.

    Typed relations come from the ``edges`` table (``member_of`` / ``refs`` /
    ``governed_by`` rows); node ``type`` and the gardener ``decay`` object come
    from the ``entries`` table (``type`` column + ``fm_json``). This is the same
    single composed source the walk projects over.
    """

    def __init__(
        self,
        index_path: "os.PathLike | str",  # noqa: F821
        *,
        index_as_of: Optional[str] = None,
    ) -> None:
        self._index_path = Path(index_path)
        self.index_as_of = index_as_of
        self._conn = None

    def _connection(self):
        import sqlite3

        if self._conn is None:
            if not self._index_path.exists():
                raise GraphError(
                    GraphErrorCode.GRAPH_UNAVAILABLE,
                    f"composed union index not found at {self._index_path}",
                )
            self._conn = sqlite3.connect(f"file:{self._index_path}?mode=ro", uri=True)
        return self._conn

    def structure(self, uid: str) -> Optional[dict]:
        import json

        cur = self._connection().cursor()
        row = cur.execute(
            "SELECT type, fm_json FROM entries WHERE uid=?", (uid,)
        ).fetchone()
        # The entries table is the admission boundary. An edge endpoint without
        # a row is a reference observation, not an indexed circle member.
        if row is None:
            return None
        edge_rows = cur.execute(
            "SELECT rel, dst_uid FROM edges WHERE src_uid=? AND rel IN "
            "('member_of','refs','governed_by')",
            (uid,),
        ).fetchall()
        node_type = row[0] or ""
        decay = None
        if row[1]:
            try:
                decay = json.loads(row[1]).get("decay")
            except (ValueError, TypeError):
                decay = None
        buckets: dict = {"member_of": [], "refs": [], "governed_by": []}
        for rel, dst in edge_rows:
            if dst and dst not in buckets[rel]:
                buckets[rel].append(dst)
        return {
            "type": node_type,
            "member_of": buckets["member_of"],
            "refs": buckets["refs"],
            "governed_by": buckets["governed_by"],
            "decay": decay,
        }

    def children_of(self, parent_uid: str) -> list:
        cur = self._connection().cursor()
        rows = cur.execute(
            "SELECT DISTINCT src_uid FROM edges WHERE rel='member_of' AND dst_uid=? "
            "ORDER BY src_uid",
            (parent_uid,),
        ).fetchall()
        return [r[0] for r in rows]


# --------------------------------------------------------------------------- #
# Seed derivation (deterministic, structural, viewer-safe).                    #
# --------------------------------------------------------------------------- #
def _classify_direct(neighbor: str, struct: dict) -> tuple:
    """Return ``(relation, distance)`` for a visible DIRECT neighbour of the task
    given the task's own structure. Fixed precedence: governed_by > ref >
    member_of-parent > (untyped) neighbor."""

    if neighbor in struct["governed_by"]:
        return REL_GOVERNED_BY, 1
    if neighbor in struct["refs"]:
        return REL_REF, 1
    if neighbor in struct["member_of"]:
        return REL_MEMBER_PARENT, 1
    return REL_NEIGHBOR, 1


def derive_seeds(
    task_uid: str,
    viewer: Viewer,
    *,
    projection: ViewerProjection,
    index: StructuralIndex,
    observation_sink: Optional[Callable[[ReferenceObservation], None]] = None,
) -> Result:
    """``Result[tuple[CircleMember, ...], GraphError]`` — the deterministic,
    viewer-safe structural seed set for the task (NO walk expansion).

    Seeds = the task's DIRECT visible neighbours classified by the task's own
    typed structure (governed_by / refs / member_of parents / other neighbours),
    PLUS one structural hop: ``member_of`` ancestors (grandparents) and
    same-project ``type``-siblings, reached through each visible parent. Every
    candidate is admitted ONLY if the projection returns it as a visible
    neighbour (``adjacency``), so the seed set can never contain a node the
    viewer cannot see. Rotten seeds are decay-gated out. Fails closed (typed
    error) if visibility cannot be resolved.
    """

    struct = index.structure(task_uid)
    if struct is None:
        return Result.failure(
            GraphError(
                GraphErrorCode.NODE_NOT_FOUND,
                f"task {task_uid!r} is not in the composed index",
                node_uid=task_uid if isinstance(task_uid, str) else None,
            )
        )

    # The task's DIRECT neighbours, already visibility-filtered by the projection.
    task_adj = projection.adjacency(task_uid, viewer)
    if not task_adj.ok:
        return Result.failure(task_adj.error)  # fail closed (typed)
    visible_direct = set(task_adj.value)

    # best[uid] -> (distance, relation, via); keep the lowest (distance, priority).
    best: dict = {}

    def offer(uid: str, distance: int, relation: str, via: str) -> None:
        if uid == task_uid:
            return
        key = (distance, _REL_PRIORITY[relation])
        current = best.get(uid)
        if current is None or key < (current[0], _REL_PRIORITY[current[1]]):
            best[uid] = (distance, relation, via)

    def observe(raw_target: object, distance: int, relation: str, via: str) -> None:
        if observation_sink is not None:
            observation_sink(
                ReferenceObservation(
                    raw_target=(
                        raw_target if isinstance(raw_target, str) else repr(raw_target)
                    ),
                    via=via,
                    relation=relation,
                    distance=distance,
                    classification=_reference_classification(raw_target),
                )
            )

    # --- direct structural seeds (distance 1) ---
    for neighbor in sorted(visible_direct):
        relation, distance = _classify_direct(neighbor, struct)
        if index.structure(neighbor) is None:
            observe(neighbor, distance, relation, task_uid)
            continue
        offer(neighbor, distance, relation, task_uid)

    # --- one structural hop: ancestors (grandparents) + type-siblings ---
    task_type = struct["type"]
    for parent in sorted(struct["member_of"]):
        if parent not in visible_direct:
            continue  # only expand through a VISIBLE parent (viewer-safe)
        parent_struct = index.structure(parent)
        if parent_struct is None:
            # Already observed by the direct-neighbour partition above.
            continue
        parent_adj = projection.adjacency(parent, viewer)
        if not parent_adj.ok:
            return Result.failure(parent_adj.error)  # fail closed (typed)
        parent_visible = set(parent_adj.value)

        grandparents = parent_struct["member_of"]
        for grandparent in sorted(grandparents):
            if grandparent in parent_visible:
                if index.structure(grandparent) is None:
                    observe(grandparent, 2, REL_MEMBER_ANCESTOR, parent)
                    continue
                offer(grandparent, 2, REL_MEMBER_ANCESTOR, parent)

        for sibling in sorted(index.children_of(parent)):
            if sibling == task_uid or sibling not in parent_visible:
                continue
            sibling_struct = index.structure(sibling)
            if sibling_struct is None:
                observe(sibling, 2, REL_WALK_HOP, parent)
                continue
            sibling_type = sibling_struct["type"]
            if sibling_type == task_type:
                offer(sibling, 2, REL_TYPE_SIBLING, parent)

    seeds: list = []
    for uid, (distance, relation, via) in best.items():
        node_struct = index.structure(uid)
        decay = node_struct["decay"] if node_struct else None
        if is_decayed(decay):
            continue  # reject rot even at the seed layer
        seeds.append(CircleMember(uid=uid, distance=distance, relation=relation, via=via))

    seeds.sort(key=lambda m: m._sort_key())
    return Result.success(tuple(seeds))


# --------------------------------------------------------------------------- #
# draw_circle — seeds -> viewer-safe walk expansion -> decay-gated circle.     #
# --------------------------------------------------------------------------- #
def draw_circle(
    task_uid: str,
    viewer: Viewer,
    budget: int,
    *,
    projection: ViewerProjection,
    index: StructuralIndex,
    query_seeds: Optional[PrevalidatedQuerySeeds] = None,
) -> Result:
    """``Result[Circle, GraphError]`` — draw the relevant-domain circle for a task.

    ``projection`` is the :class:`~lib.viewer_projection.ViewerProjection` bound
    to the composed segment-tagged graph + B4a authority (the ONLY route for any
    neighbour/visibility decision); ``index`` is the :class:`StructuralIndex`
    over the same composed union index (seed structure + gardener decay). Both
    are injected so the circle composes on the landed walk substrate and is
    testable against a sandbox fixture (the positional ``(task_uid, viewer,
    budget)`` contract of ``e12ff178`` is preserved; the substrate handles are
    keyword-only dependencies).

    Membership is bounded by ``budget`` (the max number of members). Ordering is
    STRUCTURAL — by seed-distance then UID — never a relevance rank. Expansion
    beyond the seeds routes exclusively through
    :meth:`~lib.viewer_projection.ViewerProjection.adjacency`, so the circle
    inherits the four co-signed invariants; rotten nodes are decay-gated and
    dead edges (edges through a rotten node) are never walked. Visible edge-only
    targets are partitioned into ``reference_observations`` before the frontier,
    so they consume no budget and cannot reach ranking or Stage C. Fails closed
    with the walk's typed :class:`~lib.viewer_projection.GraphError` if
    visibility cannot be resolved.
    """

    # Budget validation mirrors the walk (reject bool, non-int, negative).
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        return Result.failure(
            GraphError(
                GraphErrorCode.BUDGET_INVALID,
                f"budget must be a non-negative int, got {budget!r}",
            )
        )

    if query_seeds is not None:
        if not isinstance(query_seeds, PrevalidatedQuerySeeds):
            return Result.failure(
                QueryError(
                    QueryErrorCode.INVALID_ARGUMENT,
                    "query_seeds must be PrevalidatedQuerySeeds",
                )
            )
        if (
            query_seeds.viewer != viewer
            or query_seeds.index_as_of != getattr(index, "index_as_of", None)
        ):
            return Result.failure(
                QueryError(
                    QueryErrorCode.BINDING_MISMATCH,
                    "query seeds do not match the circle viewer/index_as_of",
                )
            )

    observations = _ReferenceObservationCollector()
    seeds_result = derive_seeds(
        task_uid,
        viewer,
        projection=projection,
        index=index,
        observation_sink=observations.add,
    )
    if not seeds_result.ok:
        return Result.failure(seeds_result.error)  # propagate typed refusal
    seeds = seeds_result.value

    if query_seeds is not None and query_seeds.uids:
        visible_query = projection.filter_visible_uids(query_seeds.uids, viewer)
        if not visible_query.ok:
            return Result.failure(visible_query.error)

        # Merge query seeds behind the existing structural provenance priority.
        # A UID that qualifies both ways keeps its structural reason.
        merged = {member.uid: member for member in seeds}
        for uid in visible_query.value:
            node_struct = index.structure(uid)
            if node_struct is None:
                # Defensive partition: the production projection already drops
                # edge-only query candidates, but an injected projection cannot
                # turn one into a member.
                observations.offer(uid, 1, REL_QUERY_SEED, task_uid)
                continue
            decay = node_struct["decay"]
            if is_decayed(decay):
                continue
            proposed = CircleMember(
                uid=uid,
                distance=1,
                relation=REL_QUERY_SEED,
                via=task_uid,
            )
            current = merged.get(uid)
            if current is None or (
                proposed.distance,
                _REL_PRIORITY[proposed.relation],
            ) < (
                current.distance,
                _REL_PRIORITY[current.relation],
            ):
                merged[uid] = proposed
        seeds = tuple(sorted(merged.values(), key=lambda member: member._sort_key()))

    if budget == 0:
        return Result.success(
            Circle(
                task_uid=task_uid,
                members=(),
                reference_observations=observations.values(),
            )
        )

    import heapq

    # Deterministic frontier keyed on (distance, relation-priority, uid, via) so
    # the first pop of any UID is its stable winning provenance. This is NOT a
    # relevance rank — it is a structural distance ordering (visited-set handles
    # cycles, identically to the walk).
    heap: list = []
    for seed in seeds:
        heapq.heappush(
            heap,
            (seed.distance, _REL_PRIORITY[seed.relation], seed.uid, seed.relation, seed.via),
        )

    chosen: dict = {}
    while heap and len(chosen) < budget:
        distance, _prio, uid, relation, via = heapq.heappop(heap)
        if uid in chosen:
            continue

        node_struct = index.structure(uid)
        if node_struct is None:
            # Admission is entries-backed. This guard is intentionally repeated
            # at pop time so a custom seed source cannot bypass the partition.
            observations.offer(uid, distance, relation, via)
            continue
        decay = node_struct["decay"]
        if is_decayed(decay):
            # Rotten: excluded from membership AND never expanded through — its
            # edges are dead, so only live edges are ever counted/walked.
            continue

        chosen[uid] = CircleMember(uid=uid, distance=distance, relation=relation, via=via)

        # Expansion hop — EVERY neighbour comes from the projection (viewer-safe).
        neighbors = projection.adjacency(uid, viewer)
        if not neighbors.ok:
            return Result.failure(neighbors.error)  # fail closed mid-expansion
        for neighbor in neighbors.value:
            if neighbor != task_uid and neighbor not in chosen:
                # Partition before enqueueing: an edge-only target never takes a
                # frontier slot, consumes budget, affects traversal, or reaches
                # the ranker / Stage C.
                if index.structure(neighbor) is None:
                    observations.offer(
                        neighbor, distance + 1, REL_WALK_HOP, uid
                    )
                    continue
                heapq.heappush(
                    heap,
                    (
                        distance + 1,
                        _REL_PRIORITY[REL_WALK_HOP],
                        neighbor,
                        REL_WALK_HOP,
                        uid,
                    ),
                )

    members = sorted(chosen.values(), key=lambda m: m._sort_key())
    return Result.success(
        Circle(
            task_uid=task_uid,
            members=tuple(members),
            reference_observations=observations.values(),
        )
    )


__all__ = [
    "DECAY_GATE_CONFIDENCE",
    "is_decayed",
    "REL_GOVERNED_BY",
    "REL_REF",
    "REL_MEMBER_PARENT",
    "REL_MEMBER_ANCESTOR",
    "REL_TYPE_SIBLING",
    "REL_NEIGHBOR",
    "REL_WALK_HOP",
    "REL_QUERY_SEED",
    "REFERENCE_MISSING_INDEX_ENTRY",
    "REFERENCE_NON_UID_OR_INVALID",
    "CircleMember",
    "ReferenceObservation",
    "Circle",
    "StructuralIndex",
    "InMemoryStructuralIndex",
    "SqliteStructuralIndex",
    "derive_seeds",
    "draw_circle",
]
