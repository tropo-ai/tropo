"""lib/viewer_projection.py — the viewer-relative distiller substrate
(dev-spec 5043b274; co-signed interface f1d760a9; test-spec 30e4447e).

ONE composed, segment-tagged storage — the union index (``vault/00-index.sqlite``
``edges``) — read through N visibility projections. A walk from any node never
sees, and never even *detects the existence of*, a neighbour in a segment the
viewer cannot read. This module implements the four co-signed primitives as
**read-time projections** over that single storage; it never materialises a
second, per-viewer graph (invariant 3).

The four binding invariants (f1d760a9 §The four binding invariants):

1. **Adjacency never leaks across the visibility boundary** — transitive through
   :meth:`ViewerProjection.walk`, hop by hop.
2. **Authority is segment-local and viewer-independent** — no cross-segment
   authority leakage; private->team back-edges are excluded from a team node's
   shared rank. Reproducible across studios IFF the team segment is
   sync-consistent (locally always correct; a stale/divergent segment yields a
   different-but-locally-correct rank reconciled at publish/graph-merge — see
   :meth:`ViewerProjection.authority`).
3. **One storage, projected at read** — the composed segment-tagged index is the
   single source; the four primitives project at read time. No viewer-specific
   graph is ever stored.
4. **No existence / cardinality leak** — the visibility filter is *total*: an
   invisible neighbour is removed before any count, order, or gap is observable,
   so adding/removing hidden neighbours leaves a peer's output byte-identical.

Composition (dev-spec committed_substrate; invariant "B4a is the sole visibility
authority"):

* **Segment** is derived by :func:`lib.segment.derive_segment` ONLY — never a
  hand-editable per-record ``segment:`` field (R3, already enforced). A
  neighbour's visibility is decided by its *derived* segment.
* **Visibility** is resolved through the B4a authority landed in
  :mod:`lib.audience_gate`: :func:`~lib.audience_gate.load_resolver` builds the
  :class:`~lib.group_registry.GroupResolver` from the pinned authority tuple;
  :func:`~lib.audience_gate.cutover_active` gates strict enforcement;
  equal-or-wider reachability uses the resolver's
  ``can_reference`` / ``is_equal_or_wider`` semantics (or, for a deployment that
  already holds the verified adapter, the
  :class:`~lib.audience_gate.B4aLattice` over an ``AudiencePolicy`` — the exact
  mount/validator integration path). **No second policy lattice is introduced.**

Every return is a :class:`~lib.group_registry.Result` (the codebase's existing
``Ok/Err`` convention, re-exported by :mod:`lib.audience_gate`). A refusal
carries a typed error and is never a permissive default: visibility failures
carry the B4a :class:`~lib.group_contract.GroupContractError` (aliased here as
:data:`AudienceError`); graph-structure failures carry a typed :class:`GraphError`.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Optional

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

# --- The B4a visibility authority — reused, never re-implemented. ----------- #
from lib.audience_gate import (  # noqa: E402
    AUDIENCE_POLICY_ARTIFACT,
    INSTALLED_RELATIVE,
    OS_AUDIENCE,
    B4aLattice,
    cutover_active,
    load_resolver,
)
from lib.group_contract import GroupContractError, GroupErrorCode  # noqa: E402
from lib.group_registry import GroupResolver, Result  # noqa: E402
from lib.decay_gate import is_live_authority_source  # noqa: E402

# --- The ONLY segment source (R3): never a hand field. ---------------------- #
from lib.segment import derive_segment  # noqa: E402


# The reserved, always-readable top constant. Reused from the B4a audience
# adapter so this module and the gate agree on the literal ("os").
OS_SEGMENT = OS_AUDIENCE

# A visibility-resolution refusal is the B4a typed error — the same closed
# vocabulary the mount/validator integration raises. Aliased for the contract's
# ``AudienceError`` name; NOT a second error taxonomy.
AudienceError = GroupContractError


class GraphErrorCode(str, Enum):
    """Closed graph-projection refusal vocabulary (distinct from, and never a
    substitute for, the B4a audience codes)."""

    NODE_NOT_FOUND = "NODE_NOT_FOUND"
    GRAPH_UNAVAILABLE = "GRAPH_UNAVAILABLE"
    BUDGET_INVALID = "BUDGET_INVALID"
    # A graph read whose visibility could not be resolved: fail closed, carrying
    # the underlying B4a AudienceError in ``audience_error`` so the typed cause
    # propagates transitively (invariant 1 through walk).
    VISIBILITY_UNRESOLVED = "VISIBILITY_UNRESOLVED"


class GraphError(Exception):
    """A deterministic, typed graph-projection refusal.

    Carries the optional originating :class:`AudienceError` when a graph read
    fails closed because visibility could not be resolved, so the B4a code is
    never swallowed into a permissive default.
    """

    def __init__(
        self,
        code: GraphErrorCode,
        message: str,
        *,
        node_uid: Optional[str] = None,
        audience_error: Optional[AudienceError] = None,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.node_uid = node_uid
        self.audience_error = audience_error


def _installed_legacy_segment_aliases(repo_root: Path) -> dict:
    """The authority's declared legacy-segment aliases, or empty.

    `derive_segment` emits the legacy literals the corpus is tagged with while
    visibility resolves group UIDs, so the two only meet through the alias table
    the authority signs into `audience-policy.json`. Read from the installed
    generation rather than assumed, and empty on any absence or malformation —
    an empty map leaves the comparison exactly as strict as it was.
    """

    try:
        pin = json.loads(
            (repo_root / INSTALLED_RELATIVE).read_text(encoding="utf-8")
        )
        policy = json.loads(
            (
                repo_root
                / str(pin["generation_dir"])
                / AUDIENCE_POLICY_ARTIFACT
            ).read_text(encoding="utf-8")
        )
    except (OSError, KeyError, TypeError, ValueError):
        return {}
    aliases = policy.get("legacy_aliases")
    if not isinstance(aliases, Mapping):
        return {}
    return {
        str(k): str(v)
        for k, v in aliases.items()
        if isinstance(k, str) and isinstance(v, str) and k and v
    }


@dataclass(frozen=True)
class Viewer:
    """A viewer principal.

    ``principal_uid`` is the ROLE / WRITER principal, **never the human**
    (f1d760a9 co-sign addition B): a two-role human (``human_count=1``,
    ``role_count=2``) is two distinct :class:`Viewer` values with distinct
    ``principal_uid`` and distinct ``private_segment_uid``, so the roles never
    leak into each other.

    ``private_segment_uid`` is this role's own private segment — the vault-node
    UID of its private store. Private segments are local (not published to the
    shared team registry), so the viewer's own private segment is supplied here
    rather than resolved through the shared authority. It is always readable by
    its owner and by no one else.
    """

    principal_uid: str
    private_segment_uid: Optional[str] = None


@dataclass(frozen=True)
class Subgraph:
    """A visibility-filtered walk result.

    ``nodes`` is in deterministic traversal order (best-first by segment-local
    authority, UID-tiebroken). ``edges`` are the visible edges among the visited
    nodes as sorted, de-duplicated undirected pairs. The dataclass is frozen so
    its ``__eq__`` and :meth:`canonical` are a stable byte-identity surface for
    the invariant-4 leak property test.
    """

    nodes: tuple
    edges: tuple

    def canonical(self) -> str:
        import json

        return json.dumps(
            {"nodes": list(self.nodes), "edges": [list(e) for e in self.edges]},
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )


# --------------------------------------------------------------------------- #
# Graph sources over the ONE composed storage. Read-only; never a writer.      #
# --------------------------------------------------------------------------- #
class GraphSource:
    """Read-only view of the composed, segment-tagged union graph.

    A source yields raw edges and the per-node ``(record, vault_root)`` pair that
    :func:`lib.segment.derive_segment` needs — the "segment tagging" is the
    node's originating vault-root association, NOT a precomputed segment string,
    so segment is still derived at read time from the one true source.
    """

    def has_node(self, node_uid: object) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def neighbors(self, node_uid: str) -> list:  # pragma: no cover - interface
        """Distinct neighbour UIDs connected by an edge in either direction."""
        raise NotImplementedError

    def inbound_sources(self, node_uid: str) -> list:  # pragma: no cover
        """Source UIDs of edges directed INTO ``node_uid`` (dst == node)."""
        raise NotImplementedError

    def record(self, node_uid: str) -> Optional[dict]:  # pragma: no cover
        raise NotImplementedError

    def vault_root(self, node_uid: str) -> Path:  # pragma: no cover
        raise NotImplementedError


class InMemoryGraphSource(GraphSource):
    """In-memory sandbox graph (synthesised segment-tagged nodes + edges).

    ``edges`` is an iterable of ``(src_uid, dst_uid)`` pairs; ``records`` maps a
    node UID to the ``rec`` dict :func:`derive_segment` consumes; ``roots`` maps
    a node UID to its vault-root (a manifest-bearing root resolves to that
    manifest's UID; a plain root falls back to os/private discrimination).
    """

    def __init__(
        self,
        edges: Iterable,
        records: Mapping[str, dict],
        roots: Mapping[str, Path],
    ) -> None:
        self._records = dict(records)
        self._roots = {uid: Path(root) for uid, root in roots.items()}
        self._out: dict[str, set] = {}
        self._in: dict[str, set] = {}
        self._nodes: set = set(self._records)
        for src, dst in edges:
            self._nodes.add(src)
            self._nodes.add(dst)
            self._out.setdefault(src, set()).add(dst)
            self._in.setdefault(dst, set()).add(src)

    def has_node(self, node_uid: object) -> bool:
        return isinstance(node_uid, str) and node_uid in self._nodes

    def neighbors(self, node_uid: str) -> list:
        return list(self._out.get(node_uid, set()) | self._in.get(node_uid, set()))

    def inbound_sources(self, node_uid: str) -> list:
        return list(self._in.get(node_uid, set()))

    def record(self, node_uid: str) -> Optional[dict]:
        return self._records.get(node_uid)

    def vault_root(self, node_uid: str) -> Path:
        return self._roots.get(node_uid, Path("."))


class SqliteGraphSource(GraphSource):
    """Production source over the composed union index (``vault/00-index.sqlite``).

    Reads the ``edges`` table (``src_uid``/``rel``/``dst_uid``) and the
    ``entries`` table (for ``extraction_scope``, lifecycle, and decay metadata).
    Opens the database read-only; it is never a writer (invariant 3). Every node
    derives its segment through :func:`derive_segment` against ``repo_root`` at
    read time.
    """

    def __init__(self, index_path: "os.PathLike | str", repo_root: "os.PathLike | str") -> None:
        self._index_path = Path(index_path)
        self._repo_root = Path(repo_root)
        self._conn: Optional[sqlite3.Connection] = None

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            if not self._index_path.exists():
                raise GraphError(
                    GraphErrorCode.GRAPH_UNAVAILABLE,
                    f"composed union index not found at {self._index_path}",
                )
            uri = f"file:{self._index_path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True)
        return self._conn

    def has_node(self, node_uid: object) -> bool:
        if not isinstance(node_uid, str):
            return False
        cur = self._connection().cursor()
        row = cur.execute(
            "SELECT 1 FROM entries WHERE uid=? "
            "UNION SELECT 1 FROM edges WHERE src_uid=? "
            "UNION SELECT 1 FROM edges WHERE dst_uid=? LIMIT 1",
            (node_uid, node_uid, node_uid),
        ).fetchone()
        return row is not None

    def neighbors(self, node_uid: str) -> list:
        cur = self._connection().cursor()
        rows = cur.execute(
            "SELECT dst_uid FROM edges WHERE src_uid=? "
            "UNION SELECT src_uid FROM edges WHERE dst_uid=?",
            (node_uid, node_uid),
        ).fetchall()
        return [r[0] for r in rows]

    def inbound_sources(self, node_uid: str) -> list:
        cur = self._connection().cursor()
        rows = cur.execute(
            "SELECT src_uid FROM edges WHERE dst_uid=?", (node_uid,)
        ).fetchall()
        return [r[0] for r in rows]

    def record(self, node_uid: str) -> Optional[dict]:
        cur = self._connection().cursor()
        row = cur.execute(
            "SELECT uid, extraction_scope, status, state, fm_json "
            "FROM entries WHERE uid=?",
            (node_uid,),
        ).fetchone()
        if row is None:
            return None

        decay = None
        fm_json = row[4]
        if fm_json:
            try:
                metadata = json.loads(fm_json)
            except (TypeError, ValueError) as error:
                raise GraphError(
                    GraphErrorCode.GRAPH_UNAVAILABLE,
                    f"entry {node_uid!r} has malformed fm_json",
                    node_uid=node_uid,
                ) from error
            if not isinstance(metadata, dict):
                raise GraphError(
                    GraphErrorCode.GRAPH_UNAVAILABLE,
                    f"entry {node_uid!r} fm_json must decode to an object",
                    node_uid=node_uid,
                )
            decay = metadata.get("decay")

        return {
            "uid": row[0],
            "extraction_scope": row[1],
            "status": row[2],
            "state": row[3],
            "decay": decay,
            "path": f"vault/files/{node_uid}.md",
        }

    def vault_root(self, node_uid: str) -> Path:
        return self._repo_root


# --------------------------------------------------------------------------- #
# The viewer-relative projection.                                              #
# --------------------------------------------------------------------------- #
class ViewerProjection:
    """The four co-signed primitives, bound to ONE storage + ONE authority.

    Construction binds the composed segment-tagged graph (``graph``) and the B4a
    visibility authority (``resolver`` — the GroupResolver under the pinned
    tuple — and/or a ``lattice`` :class:`B4aLattice` over the verified adapter).
    The four methods project at read time; nothing per-viewer is ever stored.
    """

    def __init__(
        self,
        graph: GraphSource,
        *,
        resolver: Optional[GroupResolver] = None,
        lattice: Optional[B4aLattice] = None,
        resolver_error: Optional[AudienceError] = None,
        os_segment: str = OS_SEGMENT,
        legacy_segment_aliases: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._graph = graph
        self._resolver = resolver
        self._lattice = lattice
        self._resolver_error = resolver_error
        self._os_segment = os_segment
        # `derive_segment` yields the legacy literals (`private`, `os`) while
        # visibility resolves group UIDs. `os` is the reserved constant and
        # matches directly; `private` is an ALIAS whose target lives in the
        # signed audience policy. Without the mapping the comparison silently
        # never matches and every `private` record is invisible to everyone,
        # owner included (finding 401d0702 — 2,538 of 3,040 records).
        self._legacy_segment_aliases: dict = dict(legacy_segment_aliases or {})
        # Read-time memo of derive_segment output, per projection instance. This
        # is a transient in-process cache of the ONE true segment source — never
        # a persisted per-viewer artifact and never a hand field.
        self._segment_cache: dict = {}
        self._rank_cache: dict = {}

    # ---- constructors ---------------------------------------------------- #
    @classmethod
    def from_resolver(
        cls,
        graph: GraphSource,
        resolver: GroupResolver,
        *,
        os_segment: str = OS_SEGMENT,
    ) -> "ViewerProjection":
        """Bind a synthesised/loaded :class:`GroupResolver` directly."""

        return cls(graph, resolver=resolver, os_segment=os_segment)

    @classmethod
    def from_policy(
        cls,
        graph: GraphSource,
        policy,
        resolver: GroupResolver,
        *,
        os_segment: str = OS_SEGMENT,
    ) -> "ViewerProjection":
        """Bind a verified ``AudiencePolicy`` (the mount/validator integration).

        Equal-or-wider reachability is decided by the :class:`B4aLattice` over
        the verified policy; principal membership is resolved by the same
        pinned ``resolver``. This is the exact B4a composition the mount and
        validator use — no second policy lattice is introduced.
        """

        return cls(
            graph, resolver=resolver, lattice=B4aLattice(policy), os_segment=os_segment
        )

    @classmethod
    def from_repo_root(
        cls,
        repo_root: "os.PathLike | str",
        *,
        index_path: "Optional[os.PathLike | str]" = None,
        expected_revision: Optional[str] = None,
    ) -> "ViewerProjection":
        """Load the production authority + composed index from disk, fail-closed.

        If the Studio has not installed a group authority (``cutover_active`` is
        False) or the resolver cannot be loaded, the projection is constructed in
        a fail-closed state: :meth:`visible_segments` returns the typed error and
        never a permissive default.
        """

        repo_root = Path(repo_root)
        graph = SqliteGraphSource(
            index_path or (repo_root / "vault" / "00-index.sqlite"), repo_root
        )
        if not cutover_active(repo_root):
            return cls(
                graph,
                resolver_error=GroupContractError(
                    GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                    "no group authority installed for this Studio (cutover inactive); "
                    "visibility resolution unavailable",
                ),
            )
        try:
            resolver = load_resolver(repo_root, expected_revision=expected_revision)
        except GroupContractError as error:
            return cls(graph, resolver_error=error)
        return cls(
            graph,
            resolver=resolver,
            legacy_segment_aliases=_installed_legacy_segment_aliases(repo_root),
        )

    # ---- internal reachability + segment derivation ---------------------- #
    def _reach(self, source_segment: str, target_segment: str) -> Result:
        """Return ``Result[bool]``: is ``target_segment`` equal-or-wider than
        ``source_segment`` (i.e. readable from it)? Fail-closed on any typed
        authority refusal — never a permissive True."""

        if self._lattice is not None:
            relation = self._lattice.try_relation(source_segment, target_segment)
            if not relation.ok:
                return relation
            return Result.success(relation.value in ("equal", "up"))
        assert self._resolver is not None
        # can_reference(A, B) is True exactly when B == A or B is wider than A.
        return self._resolver.can_reference(source_segment, target_segment)

    def _home_segments(self, principal_uid: str) -> list:
        """Active segments in which ``principal_uid`` is a DIRECT member.

        Raises the typed :class:`GroupContractError` on any resolver refusal, so
        the caller fails closed.
        """

        assert self._resolver is not None
        home: list = []
        for group_uid in self._resolver.active_uids:
            resolved = self._resolver.resolve_group(group_uid)
            if not resolved.ok:
                raise resolved.error  # fail closed
            if principal_uid in resolved.value["direct_member_uids"]:
                home.append(group_uid)
        return home

    def _segment_of(self, node_uid: str) -> str:
        """The node's derived segment — the ONE true source, memoised.

        Resolved through the authority's declared legacy aliases so a derived
        literal (`private`) is compared as the group it names. The alias map is
        authority-declared, never invented here; an unmapped literal is returned
        unchanged and therefore still fails to match, which keeps the boundary
        fail-closed rather than guessing.
        """

        cached = self._segment_cache.get(node_uid)
        if cached is not None:
            return cached
        rec = self._graph.record(node_uid) or {"uid": node_uid, "path": ""}
        segment = derive_segment(rec, self._graph.vault_root(node_uid))
        segment = self._legacy_segment_aliases.get(segment, segment)
        self._segment_cache[node_uid] = segment
        return segment

    def _rank(self, node_uid: str) -> int:
        cached = self._rank_cache.get(node_uid)
        if cached is not None:
            return cached
        result = self.authority(node_uid)
        rank = result.value if result.ok else 0
        self._rank_cache[node_uid] = rank
        return rank

    # ---- 1. visible_segments --------------------------------------------- #
    def visible_segments(self, viewer: Viewer) -> Result:
        """``Result[frozenset[segment_uid], AudienceError]``.

        Returns ``{os}`` (the reserved always-readable top constant) ∪ the
        audience-resolved team/vault segments the viewer is a member of
        (equal-or-wider, via the B4a resolver under the pinned authority tuple)
        ∪ the viewer's own private segment. Keyed on the ROLE/WRITER principal.

        FAILS CLOSED with a typed :class:`AudienceError` on any
        unresolved/stale/tampered authority — never a permissive default.
        """

        if (
            not isinstance(viewer, Viewer)
            or not isinstance(viewer.principal_uid, str)
            or not viewer.principal_uid
        ):
            return Result.failure(
                GroupContractError(
                    GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                    "viewer must carry a role/writer principal uid",
                )
            )

        # Fail closed: no usable authority => a typed error, never a permissive
        # (or empty-but-ok) segment set.
        if self._resolver is None:
            return Result.failure(
                self._resolver_error
                or GroupContractError(
                    GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
                    "visibility authority is unavailable",
                )
            )

        visible = {self._os_segment}
        if viewer.private_segment_uid:
            visible.add(viewer.private_segment_uid)

        try:
            home = self._home_segments(viewer.principal_uid)
        except GroupContractError as error:
            return Result.failure(error)  # fail closed

        for segment in self._resolver.active_uids:
            for home_segment in home:
                reach = self._reach(home_segment, segment)
                if not reach.ok:
                    return Result.failure(reach.error)  # fail closed
                if reach.value:
                    visible.add(segment)
                    break
        return Result.success(frozenset(visible))

    # ---- total arbitrary-UID filtering ---------------------------------- #
    def filter_visible_uids(self, candidates: Iterable, viewer: Viewer) -> Result:
        """Return sorted, de-duplicated indexed UIDs visible to ``viewer``.

        This is the projection's narrow arbitrary-candidate boundary. Visibility
        resolves once before candidate inspection; unknown, edge-only, malformed,
        and invisible candidates are dropped before ordering or cardinality can
        become observable. Authority failures remain typed and fail closed.
        """

        visible = self.visible_segments(viewer)
        if not visible.ok:
            return Result.failure(
                GraphError(
                    GraphErrorCode.VISIBILITY_UNRESOLVED,
                    f"visibility could not be resolved: {visible.error}",
                    audience_error=visible.error,
                )
            )

        kept: set[str] = set()
        try:
            for candidate in candidates:
                if not isinstance(candidate, str) or not candidate:
                    continue
                # Arbitrary query seeds must resolve to an indexed record. An
                # edge-only UID is not a body-bearing entry and is indistinguish-
                # able here from an unknown UID.
                if not self._graph.has_node(candidate):
                    continue
                if self._graph.record(candidate) is None:
                    continue
                if self._segment_of(candidate) in visible.value:
                    kept.add(candidate)
        except GraphError as error:
            return Result.failure(error)
        return Result.success(tuple(sorted(kept)))

    # ---- 2. adjacency ---------------------------------------------------- #
    def adjacency(self, node_uid: str, viewer: Viewer) -> Result:
        """``Result[sorted[neighbor_uid], GraphError]``.

        Returns ONLY neighbours whose *derived* segment is in
        ``visible_segments(viewer)``, in deterministic (sorted, de-duplicated)
        order. Invariant 1 (boundary law) + invariant 4 (no existence/cardinality
        leak): an invisible neighbour is dropped **before** it can influence any
        count, ordering, or index position (see :meth:`_visible_neighbors`).
        """

        if not self._graph.has_node(node_uid):
            return Result.failure(
                GraphError(
                    GraphErrorCode.NODE_NOT_FOUND,
                    f"node {node_uid!r} is not in the composed graph",
                    node_uid=node_uid if isinstance(node_uid, str) else None,
                )
            )
        visible = self.visible_segments(viewer)
        if not visible.ok:
            return Result.failure(
                GraphError(
                    GraphErrorCode.VISIBILITY_UNRESOLVED,
                    f"visibility could not be resolved: {visible.error}",
                    node_uid=node_uid,
                    audience_error=visible.error,
                )
            )
        return Result.success(self._visible_neighbors(node_uid, visible.value))

    def _visible_neighbors(self, node_uid: str, visible_segments) -> tuple:
        """The TOTAL visibility filter (invariant 4).

        A neighbour is appended to the working list ONLY when its derived segment
        is in ``visible_segments``. Invisible neighbours are never added, so they
        contribute no count, no ordering artifact, and no index gap. Sorting and
        de-duplication happen over the already-filtered list, so the output is a
        pure function of the *visible* neighbours alone: adding or removing hidden
        neighbours cannot change a single byte of it.
        """

        kept: set = set()
        for neighbor in self._graph.neighbors(node_uid):
            if self._segment_of(neighbor) in visible_segments:
                kept.add(neighbor)
        return tuple(sorted(kept))

    # ---- 3. walk --------------------------------------------------------- #
    def walk(self, start_uid: str, viewer: Viewer, budget: int) -> Result:
        """``Result[Subgraph, GraphError]``.

        The visibility-filtered orient()/distiller walk, viewer-parameterised.
        Uses :meth:`adjacency` for EVERY hop, so the boundary law (invariant 1)
        and the no-leak law (invariant 4) hold transitively by construction.
        Cycles are handled by a visited-set (each node visited once). Bounded by
        ``budget`` with deterministic highest-relevance-first truncation WITHIN
        ``visible_segments`` — relevance is the existing structural signal
        (segment-local :meth:`authority`, i.e. decay-gated inbound connectivity),
        never a new relevance model and never computed cross-segment.
        """

        if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
            return Result.failure(
                GraphError(
                    GraphErrorCode.BUDGET_INVALID,
                    f"budget must be a non-negative int, got {budget!r}",
                )
            )
        if not self._graph.has_node(start_uid):
            return Result.failure(
                GraphError(
                    GraphErrorCode.NODE_NOT_FOUND,
                    f"start node {start_uid!r} is not in the composed graph",
                    node_uid=start_uid if isinstance(start_uid, str) else None,
                )
            )
        # Resolve visibility once, up front, so any authority failure fails the
        # whole walk closed (rather than leaking a partial subgraph).
        visible = self.visible_segments(viewer)
        if not visible.ok:
            return Result.failure(
                GraphError(
                    GraphErrorCode.VISIBILITY_UNRESOLVED,
                    f"visibility could not be resolved: {visible.error}",
                    node_uid=start_uid,
                    audience_error=visible.error,
                )
            )
        if budget == 0:
            return Result.success(Subgraph(nodes=(), edges=()))

        import heapq

        visited: list = []
        visited_set: set = set()
        # Best-first frontier: (-authority, uid). Highest segment-local authority
        # first; UID tiebreak makes truncation deterministic.
        heap: list = [(-self._rank(start_uid), start_uid)]
        while heap and len(visited) < budget:
            _neg_rank, node = heapq.heappop(heap)
            if node in visited_set:
                continue
            visited_set.add(node)
            visited.append(node)
            adjacency = self.adjacency(node, viewer)
            if not adjacency.ok:
                return Result.failure(adjacency.error)  # fail closed, mid-walk
            for neighbor in adjacency.value:
                if neighbor not in visited_set:
                    heapq.heappush(heap, (-self._rank(neighbor), neighbor))

        # Visible edges among the visited nodes, as sorted undirected pairs.
        edges: set = set()
        for node in visited:
            adjacency = self.adjacency(node, viewer)
            if not adjacency.ok:
                return Result.failure(adjacency.error)
            for neighbor in adjacency.value:
                if neighbor in visited_set:
                    edges.add(tuple(sorted((node, neighbor))))
        return Result.success(
            Subgraph(nodes=tuple(visited), edges=tuple(sorted(edges)))
        )

    # ---- 4. authority ---------------------------------------------------- #
    def authority(self, node_uid: str) -> Result:
        """``Result[rank, GraphError]`` — NOT viewer-parameterised.

        SEGMENT-LOCAL + LIVE-SOURCE-GATED: the rank counts an inbound source only
        when its indexed record exists, its derived segment matches the node's,
        and the shared decay/lifecycle gate considers it live. Private->team
        back-edges are therefore EXCLUDED from a team node's shared authority,
        and stale or terminal records cannot confer authority through residual
        edges. A private node's authority remains a separate, owner-local
        computation over the private segment.

        REPRODUCIBILITY PRECONDITION (f1d760a9 co-sign addition C / invariant 2):
        the rank is computed over LOCAL segment state — always locally correct —
        and is reproducible across studios IFF the team segment is
        sync-consistent. A stale/divergent segment yields a
        different-but-locally-correct rank that publish/graph-merge reconciles;
        it is NOT over-claimed as "reproducible on every studio".
        """

        if not self._graph.has_node(node_uid):
            return Result.failure(
                GraphError(
                    GraphErrorCode.NODE_NOT_FOUND,
                    f"node {node_uid!r} is not in the composed graph",
                    node_uid=node_uid if isinstance(node_uid, str) else None,
                )
            )
        segment = self._segment_of(node_uid)
        rank = 0
        for source in self._graph.inbound_sources(node_uid):
            source_record = self._graph.record(source)
            if source_record is None:
                continue
            if self._segment_of(source) != segment:
                continue
            if not is_live_authority_source(source_record):
                continue
            rank += 1
        return Result.success(rank)


__all__ = [
    "OS_SEGMENT",
    "AudienceError",
    "GraphError",
    "GraphErrorCode",
    "Viewer",
    "Subgraph",
    "GraphSource",
    "InMemoryGraphSource",
    "SqliteGraphSource",
    "ViewerProjection",
]
