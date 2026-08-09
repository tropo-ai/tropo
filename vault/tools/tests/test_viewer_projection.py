#!/usr/bin/env python3
"""Executable contract for the viewer-relative distiller substrate.

Pairs dev-spec ``5043b274`` (activation ``057de5ce``) and test-spec
``30e4447e``. One test class per dev-spec acceptance criterion (1-based),
exercising the four ``viewer_projection`` primitives against a SANDBOXED fixture
graph (synthesised segment-tagged nodes/edges + a fixture B4a authority) so the
visibility boundary is provable WITHOUT the live corpus and independent of the
live Studio's cutover state.

Coverage -> acceptance-criterion map (test-spec §Coverage):

* AC1 VISIBLE-SEGMENTS RESOLUTION + FAIL-CLOSED
* AC2 ADJACENCY BOUNDARY LAW (invariant 1)
* AC3 NO EXISTENCE / CARDINALITY LEAK (invariant 4) — the property gate
* AC4 SEGMENT-LOCAL AUTHORITY (invariant 2)
* AC5 ONE STORAGE, PROJECTED AT READ (invariant 3)
* AC6 TRANSITIVE-SAFE BOUNDED WALK
* AC7 B4a IS THE SOLE VISIBILITY AUTHORITY

The module under test is loaded by file path with ``importlib`` (per
``test_b4a_audience_context.py``); the sibling ``lib`` libraries it composes are
imported normally so every ``GroupResolver`` / ``Result`` / ``GroupContractError``
shares one class identity with the module under test.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MODULE_PATH = TOOLS / "lib" / "viewer_projection.py"
vp = _load("viewer_projection_under_test", MODULE_PATH)

from lib.group_contract import (  # noqa: E402
    GroupContractError,
    GroupErrorCode,
    build_group_corpus,
    semantic_hash,
)
from lib.group_registry import (  # noqa: E402
    AuthorityRevisionContext,
    GroupResolver,
    Result,
    parse_registry_jsonl,
    project_registry,
)

Viewer = vp.Viewer
ViewerProjection = vp.ViewerProjection
InMemoryGraphSource = vp.InMemoryGraphSource
SqliteGraphSource = vp.SqliteGraphSource
Subgraph = vp.Subgraph
GraphError = vp.GraphError
GraphErrorCode = vp.GraphErrorCode


# --------------------------------------------------------------------------- #
# Principals + segment UIDs (all 8-hex; segment UIDs double as manifest UIDs).  #
# --------------------------------------------------------------------------- #
ALICE = "a1a1a1a1"
BOB = "b2b2b2b2"
CAROL = "c3c3c3c3"  # a second ROLE of the same human as ALICE; member of nothing

TEAM = "7ea70001"        # the shared team/vault segment
NARROW = "4a4a0001"      # a narrower group that TEAM (wider) includes
PRIV_ALICE = "b1a70001"  # alice's own private segment (a private vault-node)
PRIV_BOB = "b1a70002"    # bob's own private segment
OS = vp.OS_SEGMENT       # "os" — the reserved always-readable top constant

REVISION = "sha256:" + ("a" * 64)


def _principal(uid: str) -> dict:
    return {
        "principal_uid": uid,
        "principal_class": "human",
        "status": "active",
        "source_authority_uid": "a1b2c3d4",
        "source_revision": "1",
        "source_hash": "0" * 64,
    }


def _group(uid: str, slug: str, *, members, includes=None, owner=None) -> dict:
    group = {
        "uid": uid,
        "type": "group",
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "description": f"Purpose of {slug}.",
        "owner": owner or members[0],
        "members": list(members),
        "includes_groups": list(includes or []),
        "status": "active",
        "version": 1,
    }
    group["semantic_hash"] = semantic_hash(group)
    return group


def build_resolver(groups: list, principals: list) -> GroupResolver:
    """Synthesise a pinned B4a resolver from an injected group corpus — no signed
    authority and no live Studio state required."""

    corpus = build_group_corpus(
        {g["uid"]: g for g in groups},
        {p["principal_uid"]: p for p in principals},
    )
    projection = project_registry(
        corpus,
        AuthorityRevisionContext(
            source_authority_uid="a1b2c3d4",
            source_revision=REVISION,
            principal_directory_revision="1",
            source_paths={g["uid"]: f"vault/groups/{g['uid']}.md" for g in groups},
        ),
    )
    return GroupResolver.from_projection(projection), projection


def base_resolver() -> GroupResolver:
    """TEAM with alice + bob as DIRECT members (both peers of each other)."""

    resolver, _ = build_resolver(
        [_group(TEAM, "team", members=[ALICE, BOB])],
        [_principal(ALICE), _principal(BOB)],
    )
    return resolver


# --------------------------------------------------------------------------- #
# Sandbox segment-tagging: temp vault-roots whose manifest UID == segment UID.  #
# --------------------------------------------------------------------------- #
class _RootFactory:
    """Creates temp vault-roots so ``derive_segment`` yields the segment we want.

    A manifest-bearing root resolves every record under it to that manifest's UID
    (a team/private segment); a plain root + ``extraction_scope: ship`` resolves
    to the reserved ``os`` segment. Segment is therefore always the derived value
    — never a hand field on the record.
    """

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self._roots: dict = {}

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def manifest_root(self, segment_uid: str) -> Path:
        root = self._roots.get(segment_uid)
        if root is None:
            root = self.base / segment_uid
            (root / ".tropo").mkdir(parents=True, exist_ok=True)
            (root / ".tropo" / "vault-manifest.md").write_text(
                f"---\nuid: {segment_uid}\n---\n", encoding="utf-8"
            )
            self._roots[segment_uid] = root
        return root

    def os_root(self) -> Path:
        root = self._roots.get("__os__")
        if root is None:
            root = self.base / "os_root"
            root.mkdir(parents=True, exist_ok=True)
            self._roots["__os__"] = root
        return root


class _GraphBuilder:
    """Collects (uid -> segment) nodes and undirected/directed edges, then emits
    an :class:`InMemoryGraphSource` whose per-node root drives ``derive_segment``."""

    def __init__(self, roots: _RootFactory) -> None:
        self._roots = roots
        self._records: dict = {}
        self._node_root: dict = {}
        self._edges: list = []

    def node(self, uid: str, segment_uid: str, **metadata) -> str:
        if segment_uid == OS:
            self._records[uid] = {
                "uid": uid,
                "extraction_scope": "ship",
                "path": f"os_root/{uid}.md",
                **metadata,
            }
            self._node_root[uid] = self._roots.os_root()
        else:
            self._records[uid] = {
                "uid": uid,
                "path": f"vault/files/{uid}.md",
                **metadata,
            }
            self._node_root[uid] = self._roots.manifest_root(segment_uid)
        return uid

    def edge_only(self, uid: str, segment_uid: str) -> str:
        """Register a segment root without an indexed record."""

        self._node_root[uid] = self._roots.manifest_root(segment_uid)
        return uid

    def edge(self, src: str, dst: str) -> None:
        self._edges.append((src, dst))

    def biedge(self, a: str, b: str) -> None:
        self._edges.append((a, b))
        self._edges.append((b, a))

    def build(self) -> InMemoryGraphSource:
        return InMemoryGraphSource(self._edges, self._records, self._node_root)


def alice(viewer_private: str = PRIV_ALICE) -> Viewer:
    return Viewer(principal_uid=ALICE, private_segment_uid=viewer_private)


def bob(viewer_private: str = PRIV_BOB) -> Viewer:
    return Viewer(principal_uid=BOB, private_segment_uid=viewer_private)


class _ProjectionCase(unittest.TestCase):
    def setUp(self) -> None:
        self.roots = _RootFactory()
        self.addCleanup(self.roots.cleanup)

    def assert_err(self, result, code) -> None:
        self.assertIsInstance(result, Result)
        self.assertFalse(result.ok)
        self.assertIsNone(result.value)  # never a permissive/empty value
        self.assertIsNotNone(result.error)
        actual = getattr(result.error, "code", None)
        self.assertEqual(actual, code, msg=f"expected {code}, got {actual}: {result.error}")


# =========================================================================== #
# AC1 — VISIBLE-SEGMENTS RESOLUTION + FAIL-CLOSED                              #
# =========================================================================== #
class AC1VisibleSegmentsResolutionAndFailClosed(_ProjectionCase):
    def test_visible_set_is_os_union_team_union_own_private(self) -> None:
        proj = ViewerProjection.from_resolver(_GraphBuilder(self.roots).build(), base_resolver())
        result = proj.visible_segments(alice())
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(result.value, frozenset({OS, TEAM, PRIV_ALICE}))
        # bob resolves his OWN private segment, never alice's.
        self.assertEqual(
            proj.visible_segments(bob()).value, frozenset({OS, TEAM, PRIV_BOB})
        )

    def test_equal_or_wider_membership(self) -> None:
        # NARROW.members=[ALICE]; TEAM (wider) includes NARROW, members=[BOB].
        resolver, _ = build_resolver(
            [
                _group(NARROW, "narrow", members=[ALICE]),
                _group(TEAM, "team", members=[BOB], includes=[NARROW]),
            ],
            [_principal(ALICE), _principal(BOB)],
        )
        proj = ViewerProjection.from_resolver(_GraphBuilder(self.roots).build(), resolver)
        # A NARROW member reads NARROW *and* the wider TEAM (equal-or-wider).
        self.assertEqual(
            proj.visible_segments(alice()).value,
            frozenset({OS, NARROW, TEAM, PRIV_ALICE}),
        )
        # A TEAM member does NOT read the narrower NARROW.
        self.assertEqual(
            proj.visible_segments(bob()).value, frozenset({OS, TEAM, PRIV_BOB})
        )

    def test_two_role_human_resolves_distinct_visibility_per_role(self) -> None:
        # One human, two roles: ALICE (a TEAM member) and CAROL (member of none).
        proj = ViewerProjection.from_resolver(_GraphBuilder(self.roots).build(), base_resolver())
        role_a = Viewer(principal_uid=ALICE, private_segment_uid=PRIV_ALICE)
        role_b = Viewer(principal_uid=CAROL, private_segment_uid="c0000001")
        va = proj.visible_segments(role_a).value
        vb = proj.visible_segments(role_b).value
        self.assertEqual(va, frozenset({OS, TEAM, PRIV_ALICE}))
        self.assertEqual(vb, frozenset({OS, "c0000001"}))  # no TEAM, no PRIV_ALICE
        self.assertNotEqual(va, vb)  # the roles never leak into each other

    def test_fail_closed_on_stale_authority(self) -> None:
        _, projection = build_resolver(
            [_group(TEAM, "team", members=[ALICE, BOB])],
            [_principal(ALICE), _principal(BOB)],
        )
        # A resolver pinned to a different revision than the JSONL is stale.
        with self.assertRaises(GroupContractError) as raised:
            GroupResolver.from_jsonl(
                projection.jsonl_bytes, expected_revision="sha256:" + ("f" * 64)
            )
        stale = raised.exception
        self.assertEqual(stale.code, GroupErrorCode.GROUP_CORPUS_STALE)
        proj = ViewerProjection(
            _GraphBuilder(self.roots).build(), resolver=None, resolver_error=stale
        )
        self.assert_err(proj.visible_segments(alice()), GroupErrorCode.GROUP_CORPUS_STALE)

    def test_fail_closed_on_tampered_or_unavailable_authority(self) -> None:
        # A malformed/tampered registry surface is unresolvable — the exact class
        # B4a exists to refuse. visible_segments must carry the typed error, never
        # a permissive set.
        with self.assertRaises(GroupContractError) as raised:
            parse_registry_jsonl(b"{not valid json}\n")
        unavailable = raised.exception
        self.assertEqual(unavailable.code, GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE)
        proj = ViewerProjection(
            _GraphBuilder(self.roots).build(), resolver=None, resolver_error=unavailable
        )
        self.assert_err(
            proj.visible_segments(alice()), GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE
        )

    def test_fail_closed_when_cutover_inactive(self) -> None:
        # A Studio with no installed group authority (empty temp root) must not
        # fall open: from_repo_root produces a fail-closed projection.
        with tempfile.TemporaryDirectory() as tmp:
            proj = ViewerProjection.from_repo_root(tmp)
            self.assert_err(
                proj.visible_segments(alice()),
                GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
            )

    def test_reachability_fails_closed_group_not_found(self) -> None:
        # The reachability path visible_segments relies on refuses an absent group
        # with a typed GROUP_NOT_FOUND — never a permissive True.
        proj = ViewerProjection.from_resolver(_GraphBuilder(self.roots).build(), base_resolver())
        reach = proj._reach(TEAM, "dead0001")  # dead0001 is not in the corpus
        self.assert_err(reach, GroupErrorCode.GROUP_NOT_FOUND)

    def test_missing_role_principal_refuses(self) -> None:
        proj = ViewerProjection.from_resolver(_GraphBuilder(self.roots).build(), base_resolver())
        self.assert_err(
            proj.visible_segments(Viewer(principal_uid="")),
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
        )


# =========================================================================== #
# AC2 — ADJACENCY BOUNDARY LAW (invariant 1)                                  #
# =========================================================================== #
class AC2AdjacencyBoundaryLaw(_ProjectionCase):
    def _graph(self):
        g = _GraphBuilder(self.roots)
        g.node("t_node", TEAM)
        g.node("t_peer", TEAM)      # a team neighbour (visible to everyone on TEAM)
        g.node("t_other", TEAM)     # a second team neighbour
        g.node("p_a1", PRIV_ALICE)  # alice-private neighbours (hidden from bob)
        g.node("p_a2", PRIV_ALICE)
        g.biedge("t_node", "t_peer")
        g.biedge("t_node", "t_other")
        g.biedge("t_node", "p_a1")
        g.biedge("t_node", "p_a2")
        return ViewerProjection.from_resolver(g.build(), base_resolver())

    def test_peer_sees_team_only_and_deterministically_ordered(self) -> None:
        proj = self._graph()
        result = proj.adjacency("t_node", bob())
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(result.value, ("t_other", "t_peer"))  # sorted, team-only
        self.assertEqual(tuple(sorted(result.value)), result.value)

    def test_owner_sees_team_plus_own_private(self) -> None:
        proj = self._graph()
        result = proj.adjacency("t_node", alice())
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(result.value, ("p_a1", "p_a2", "t_other", "t_peer"))

    def test_no_edge_traversed_into_invisible_segment(self) -> None:
        proj = self._graph()
        # Not one private neighbour crosses to the peer.
        self.assertNotIn("p_a1", proj.adjacency("t_node", bob()).value)
        self.assertNotIn("p_a2", proj.adjacency("t_node", bob()).value)

    def test_unknown_node_refuses(self) -> None:
        proj = self._graph()
        result = proj.adjacency("nope0000", bob())
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, GraphErrorCode.NODE_NOT_FOUND)


# =========================================================================== #
# AC3 — NO EXISTENCE / CARDINALITY LEAK (invariant 4) — THE PROPERTY GATE      #
# =========================================================================== #
class AC3NoExistenceOrCardinalityLeak(_ProjectionCase):
    def _graph_with_hidden(self, hidden_count: int):
        """A team node with two fixed visible team neighbours and a VARYING number
        of hidden alice-private neighbours (both out- and back-edges)."""

        g = _GraphBuilder(self.roots)
        g.node("t_node", TEAM)
        g.node("t_vis1", TEAM)
        g.node("t_vis2", TEAM)
        g.biedge("t_node", "t_vis1")
        g.biedge("t_node", "t_vis2")
        hidden = []
        for i in range(hidden_count):
            uid = f"hp{i:04x}"
            g.node(uid, PRIV_ALICE)
            g.biedge("t_node", uid)  # both directions: out-edge AND private->team back-edge
            hidden.append(uid)
        return ViewerProjection.from_resolver(g.build(), base_resolver()), g, hidden

    def test_peer_output_byte_identical_across_0_1_and_N_hidden(self) -> None:
        peer = bob()
        baselines_adj = None
        baselines_walk = None
        for hidden_count in (0, 1, 7):
            proj, builder, hidden = self._graph_with_hidden(hidden_count)

            # Sanity: the fixture GENUINELY contains the hidden neighbours a naive
            # implementation would leak — the raw graph neighbour count grows.
            raw = builder.build().neighbors("t_node")
            self.assertEqual(len(raw), 2 + hidden_count)
            for uid in hidden:
                self.assertIn(uid, raw)

            adj = proj.adjacency("t_node", peer)
            walk = proj.walk("t_node", peer, budget=64)
            self.assertTrue(adj.ok and walk.ok)

            # The peer's projected output must not betray the hidden structure:
            # no count, no gap, no order tell.
            self.assertEqual(adj.value, ("t_vis1", "t_vis2"))
            adj_bytes = repr(adj.value).encode("utf-8")
            walk_bytes = walk.value.canonical().encode("utf-8")
            if baselines_adj is None:
                baselines_adj = adj_bytes
                baselines_walk = walk_bytes
            else:
                self.assertEqual(adj_bytes, baselines_adj)
                self.assertEqual(walk_bytes, baselines_walk)

    def test_owner_actually_sees_the_hidden_neighbours(self) -> None:
        # Confirms the plants are real: the SAME hidden nodes that are invisible to
        # the peer are visible to their owner (so the peer's identical output is
        # true filtering, not universally-dropped edges).
        proj, _builder, hidden = self._graph_with_hidden(7)
        owner_adj = proj.adjacency("t_node", alice()).value
        for uid in hidden:
            self.assertIn(uid, owner_adj)
        self.assertEqual(len(owner_adj), 2 + 7)


class Cut4ATotalUidFiltering(_ProjectionCase):
    def _projection(self, hidden_count: int):
        g = _GraphBuilder(self.roots)
        for uid in ("visible2", "visible1"):
            g.node(uid, TEAM)
        hidden = []
        for index in range(hidden_count):
            uid = f"hidden{index:02d}"
            g.node(uid, PRIV_ALICE)
            hidden.append(uid)
        g.edge_only("edgeonly", TEAM)
        return ViewerProjection.from_resolver(g.build(), base_resolver()), hidden

    def test_unknown_invisible_and_edge_only_candidates_vanish_before_observables(self):
        baseline = None
        for hidden_count in (0, 1, 7):
            projection, hidden = self._projection(hidden_count)
            candidates = [
                *reversed(hidden),
                "unknown1",
                "visible2",
                "edgeonly",
                "visible1",
                "visible2",
            ]
            result = projection.filter_visible_uids(candidates, bob())
            self.assertTrue(result.ok, msg=result.error)
            self.assertEqual(result.value, ("visible1", "visible2"))
            canonical = repr(result.value).encode("utf-8")
            if baseline is None:
                baseline = canonical
            else:
                self.assertEqual(canonical, baseline)

    def test_same_hidden_candidates_are_visible_only_to_their_owner(self):
        projection, hidden = self._projection(3)
        peer = projection.filter_visible_uids(hidden, bob())
        owner = projection.filter_visible_uids(hidden, alice())
        self.assertEqual(peer.value, ())
        self.assertEqual(owner.value, tuple(sorted(hidden)))

    def test_total_filter_preserves_typed_fail_closed_authority(self):
        g = _GraphBuilder(self.roots)
        g.node("visible1", TEAM)
        stale = GroupContractError(GroupErrorCode.GROUP_CORPUS_STALE, "stale")
        projection = ViewerProjection(g.build(), resolver=None, resolver_error=stale)
        result = projection.filter_visible_uids(("visible1",), bob())
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, GraphErrorCode.VISIBILITY_UNRESOLVED)
        self.assertEqual(
            result.error.audience_error.code, GroupErrorCode.GROUP_CORPUS_STALE
        )


# =========================================================================== #
# AC4 — SEGMENT-LOCAL AUTHORITY (invariant 2)                                 #
# =========================================================================== #
class AC4SegmentLocalAuthority(_ProjectionCase):
    def _graph(self, with_private_back_edges: bool):
        g = _GraphBuilder(self.roots)
        g.node("t_node", TEAM)
        g.node("t_src1", TEAM)
        g.node("t_src2", TEAM)
        g.edge("t_src1", "t_node")  # same-segment inbound -> counts
        g.edge("t_src2", "t_node")
        # A private node with its own inbound (owner-local authority).
        g.node("p_node", PRIV_ALICE)
        g.node("p_src", PRIV_ALICE)
        g.edge("p_src", "p_node")
        if with_private_back_edges:
            g.node("p_back1", PRIV_ALICE)
            g.node("p_back2", PRIV_ALICE)
            g.edge("p_back1", "t_node")  # private->team back-edges: must NOT count
            g.edge("p_back2", "t_node")
        return ViewerProjection.from_resolver(g.build(), base_resolver())

    def test_team_rank_excludes_private_to_team_back_edges(self) -> None:
        without = self._graph(with_private_back_edges=False)
        with_back = self._graph(with_private_back_edges=True)
        self.assertEqual(without.authority("t_node").value, 2)
        # Adding private->team back-edges leaves the team rank unchanged.
        self.assertEqual(with_back.authority("t_node").value, 2)

    def test_private_authority_is_a_separate_owner_local_computation(self) -> None:
        proj = self._graph(with_private_back_edges=True)
        self.assertEqual(proj.authority("p_node").value, 1)  # only its private inbound

    def test_authority_is_not_viewer_parameterised(self) -> None:
        # authority() takes no viewer; two independent projections agree.
        a = self._graph(with_private_back_edges=True).authority("t_node").value
        b = self._graph(with_private_back_edges=False).authority("t_node").value
        self.assertEqual(a, b)

    def test_authority_counts_only_existing_same_segment_live_sources(self) -> None:
        g = _GraphBuilder(self.roots)
        g.node("target00", TEAM)
        g.node(
            "highstal",
            TEAM,
            decay={"stale": True, "confidence": 0.9},
        )
        g.node("termstat", TEAM, status=" Shipped ")
        g.node("termstte", TEAM, state="ARCHIVED")
        g.node(
            "lowstale",
            TEAM,
            decay={"stale": True, "confidence": 0.79},
        )
        g.node(
            "clean000",
            TEAM,
            decay={"stale": False, "confidence": 1.0},
        )
        g.node("absent00", TEAM)
        g.node("crossseg", PRIV_ALICE, decay={"stale": False, "confidence": 0.0})
        g.edge_only("edgeonly", TEAM)

        sources = (
            "highstal",
            "termstat",
            "termstte",
            "lowstale",
            "clean000",
            "absent00",
            "crossseg",
            "edgeonly",
        )
        for source in sources:
            g.edge(source, "target00")

        graph = g.build()
        self.assertEqual(len(graph.inbound_sources("target00")), 8)
        self.assertIsNone(graph.record("edgeonly"))

        result = ViewerProjection.from_resolver(graph, base_resolver()).authority("target00")
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(result.value, 3)

    def test_unknown_node_refuses(self) -> None:
        proj = self._graph(with_private_back_edges=False)
        result = proj.authority("nope0000")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, GraphErrorCode.NODE_NOT_FOUND)


# =========================================================================== #
# AC5 — ONE STORAGE, PROJECTED AT READ (invariant 3)                          #
# =========================================================================== #
class AC5OneStorageProjectedAtRead(_ProjectionCase):
    def _snapshot(self, base: Path):
        return {
            str(p.relative_to(base)): p.stat().st_size
            for p in sorted(base.rglob("*"))
            if p.is_file()
        }

    def test_no_per_viewer_graph_artifact_is_written(self) -> None:
        g = _GraphBuilder(self.roots)
        g.node("t_node", TEAM)
        g.node("t_peer", TEAM)
        g.node("p_a1", PRIV_ALICE)
        g.biedge("t_node", "t_peer")
        g.biedge("t_node", "p_a1")
        proj = ViewerProjection.from_resolver(g.build(), base_resolver())

        before = self._snapshot(self.roots.base)
        # Exercise every primitive, for two distinct viewers.
        for viewer in (alice(), bob()):
            self.assertTrue(proj.visible_segments(viewer).ok)
            self.assertTrue(proj.adjacency("t_node", viewer).ok)
            self.assertTrue(proj.walk("t_node", viewer, budget=32).ok)
        self.assertTrue(proj.authority("t_node").ok)
        after = self._snapshot(self.roots.base)

        # The single storage (temp roots) is unchanged: nothing per-viewer was
        # projected to disk.
        self.assertEqual(before, after)

    def test_projection_exposes_no_persistence_surface(self) -> None:
        # Structural: the projection offers read primitives only — no store /
        # materialise / persist / write surface that would create a second truth.
        public = {name for name in dir(ViewerProjection) if not name.startswith("_")}
        forbidden = {"store", "materialize", "materialise", "persist", "save", "write", "flush"}
        self.assertEqual(public & forbidden, set())


# =========================================================================== #
# R5 — SQLITE RECORD CONTRACT                                                 #
# =========================================================================== #
class R5SqliteRecordContract(unittest.TestCase):
    def source(self, rows=(), edges=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        index_path = Path(tmp.name) / "index.sqlite"
        conn = sqlite3.connect(index_path)
        conn.execute(
            "CREATE TABLE entries ("
            "uid TEXT PRIMARY KEY, extraction_scope TEXT, status TEXT, "
            "state TEXT, fm_json TEXT)"
        )
        conn.execute(
            "CREATE TABLE edges (src_uid TEXT, rel TEXT, dst_uid TEXT)"
        )
        conn.executemany(
            "INSERT INTO entries(uid, extraction_scope, status, state, fm_json) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.executemany(
            "INSERT INTO edges(src_uid, rel, dst_uid) VALUES (?, ?, ?)",
            edges,
        )
        conn.commit()
        conn.close()
        return SqliteGraphSource(index_path, ROOT)

    def test_record_exposes_lifecycle_and_parsed_decay(self) -> None:
        decay = {"stale": True, "confidence": 0.9}
        source = self.source(
            rows=[
                (
                    "live0001",
                    "argo-reference",
                    "active",
                    "active",
                    json.dumps({"decay": decay, "other": "preserved-in-fm-only"}),
                )
            ]
        )
        self.assertEqual(
            source.record("live0001"),
            {
                "uid": "live0001",
                "extraction_scope": "argo-reference",
                "status": "active",
                "state": "active",
                "decay": decay,
                "path": "vault/files/live0001.md",
            },
        )

    def test_absent_metadata_is_neutral_and_edge_only_is_missing(self) -> None:
        source = self.source(
            rows=[
                ("null0001", None, None, None, None),
                ("empty001", "ship", None, None, ""),
                ("absent01", "ship", "locked", "active", "{}"),
            ],
            edges=[("edgeonly", "refs", "null0001")],
        )
        for uid in ("null0001", "empty001", "absent01"):
            record = source.record(uid)
            self.assertIsNotNone(record)
            self.assertIsNone(record["decay"])
        self.assertTrue(source.has_node("edgeonly"))
        self.assertIsNone(source.record("edgeonly"))

    def test_malformed_and_non_object_fm_json_fail_typed(self) -> None:
        source = self.source(
            rows=[
                ("badjson1", "ship", "active", "active", "{not-json"),
                ("array001", "ship", "active", "active", "[]"),
            ]
        )
        for uid in ("badjson1", "array001"):
            with self.subTest(uid=uid), self.assertRaises(GraphError) as raised:
                source.record(uid)
            self.assertEqual(raised.exception.code, GraphErrorCode.GRAPH_UNAVAILABLE)
            self.assertEqual(raised.exception.node_uid, uid)


# =========================================================================== #
# AC6 — TRANSITIVE-SAFE BOUNDED WALK                                          #
# =========================================================================== #
class AC6TransitiveSafeBoundedWalk(_ProjectionCase):
    def _graph(self):
        """A cyclic team subgraph with graded authority + one hidden private
        branch off the start node."""

        g = _GraphBuilder(self.roots)
        for uid in ("w_s", "w_x", "w_y", "w_z"):
            g.node(uid, TEAM)
        # start connects to x, y, z
        g.biedge("w_s", "w_x")
        g.biedge("w_s", "w_y")
        g.biedge("w_s", "w_z")
        # a cycle among x, y, z (visited-set must handle it)
        g.biedge("w_x", "w_y")
        g.biedge("w_y", "w_z")
        g.biedge("w_z", "w_x")
        # graded segment-local authority via same-segment inbound "voters".
        # x gets 3, y gets 2, z gets 1.
        voters = {"w_x": 3, "w_y": 2, "w_z": 1}
        for target, count in voters.items():
            for i in range(count):
                v = f"vote_{target[-1]}_{i}"
                g.node(v, TEAM)
                g.edge(v, target)
        # a hidden private branch off the start (invisible to bob).
        g.node("w_hidden", PRIV_ALICE)
        g.biedge("w_s", "w_hidden")
        return ViewerProjection.from_resolver(g.build(), base_resolver())

    def test_walk_uses_adjacency_per_hop_never_crossing_the_boundary(self) -> None:
        proj = self._graph()
        walk = proj.walk("w_s", bob(), budget=64)
        self.assertTrue(walk.ok, msg=walk.error)
        # The hidden private node is never reached (adjacency filtered every hop).
        self.assertNotIn("w_hidden", walk.value.nodes)
        for node in walk.value.nodes:
            self.assertNotEqual(node, "w_hidden")
        # The OWNER's walk (private visible) DOES reach it — viewer-relative.
        owner_walk = proj.walk("w_s", alice(), budget=64)
        self.assertIn("w_hidden", owner_walk.value.nodes)

    def test_cycle_visits_each_node_once(self) -> None:
        proj = self._graph()
        nodes = proj.walk("w_s", bob(), budget=64).value.nodes
        self.assertEqual(len(nodes), len(set(nodes)))  # no repeats despite the cycle

    def test_budget_truncates_highest_relevance_first_within_visible_segments(self) -> None:
        proj = self._graph()
        # Segment-local authority is graded x > y > z (more same-segment inbound
        # voters), so after the start the highest-authority neighbour is admitted
        # first under the budget.
        rank_x = proj.authority("w_x").value
        rank_y = proj.authority("w_y").value
        rank_z = proj.authority("w_z").value
        self.assertGreater(rank_x, rank_y)
        self.assertGreater(rank_y, rank_z)
        truncated = proj.walk("w_s", bob(), budget=2).value
        self.assertEqual(len(truncated.nodes), 2)
        self.assertEqual(truncated.nodes[0], "w_s")
        self.assertEqual(truncated.nodes[1], "w_x")  # highest-relevance-first
        # The truncated prefix is consistent with the fuller best-first order.
        fuller = proj.walk("w_s", bob(), budget=3).value
        self.assertEqual(fuller.nodes[:2], truncated.nodes)

    def test_zero_and_invalid_budget(self) -> None:
        proj = self._graph()
        self.assertEqual(proj.walk("w_s", bob(), budget=0).value, Subgraph((), ()))
        for bad in (-1, "3", 3.0, True):
            result = proj.walk("w_s", bob(), budget=bad)
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, GraphErrorCode.BUDGET_INVALID)

    def test_walk_fails_closed_on_unresolved_authority(self) -> None:
        g = _GraphBuilder(self.roots)
        g.node("w_s", TEAM)
        stale = GroupContractError(GroupErrorCode.GROUP_CORPUS_STALE, "stale")
        proj = ViewerProjection(g.build(), resolver=None, resolver_error=stale)
        result = proj.walk("w_s", bob(), budget=8)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, GraphErrorCode.VISIBILITY_UNRESOLVED)
        self.assertEqual(result.error.audience_error.code, GroupErrorCode.GROUP_CORPUS_STALE)


# =========================================================================== #
# AC7 — B4a IS THE SOLE VISIBILITY AUTHORITY                                  #
# =========================================================================== #
class AC7B4aIsSoleVisibilityAuthority(_ProjectionCase):
    def setUp(self) -> None:
        super().setUp()
        self.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_reuses_audience_gate_and_segment_derive_segment(self) -> None:
        self.assertIn("from lib.audience_gate import", self.source)
        for name in ("load_resolver", "B4aLattice", "cutover_active"):
            self.assertIn(name, self.source, msg=f"missing reuse of {name}")
        self.assertIn("from lib.segment import", self.source)
        self.assertIn("derive_segment", self.source)

    def test_no_second_policy_lattice_is_defined(self) -> None:
        # It may IMPORT B4aLattice, but must not DEFINE its own lattice class or
        # synthesize a fallback lattice.
        self.assertIsNone(re.search(r"^class\s+\w*[Ll]attice", self.source, re.M))
        self.assertNotIn("default_two_segment_lattice", self.source)

    def test_segment_is_never_read_from_a_hand_field(self) -> None:
        # No record-level 'segment' field is ever read; segment comes only from
        # derive_segment.
        for pattern in ('get("segment"', "get('segment'", '["segment"]', "['segment']"):
            self.assertNotIn(pattern, self.source, msg=f"hand segment read: {pattern}")

    def test_composes_with_the_verified_b4a_adapter_via_b4alattice(self) -> None:
        # The mount/validator integration path: a VERIFIED AudiencePolicy wrapped
        # in B4aLattice drives equal-or-wider reachability. Proves B4aLattice is
        # genuinely wired, not a dead import.
        policy, resolver, mike_group, mike_principal = _build_verified_policy()
        g = _GraphBuilder(self.roots)
        proj = ViewerProjection.from_policy(g.build(), policy, resolver)
        viewer = Viewer(principal_uid=mike_principal, private_segment_uid="d0000001")
        visible = proj.visible_segments(viewer)
        self.assertTrue(visible.ok, msg=visible.error)
        self.assertIn(OS, visible.value)
        self.assertIn(mike_group, visible.value)      # resolved via the B4a lattice
        self.assertIn("d0000001", visible.value)

    def test_from_policy_refuses_a_non_policy(self) -> None:
        _, resolver, _, _ = _build_verified_policy()
        with self.assertRaises(GroupContractError):
            ViewerProjection.from_policy(_GraphBuilder(self.roots).build(), "not-a-policy", resolver)


def _build_verified_policy():
    """Build a VERIFIED B4a AudiencePolicy + matching resolver in a sandbox,
    reusing the sibling authority/verify APIs (never re-implementing them),
    grounded on the RFC 8032 test seed (TEST-only signing input)."""

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    import lib.group_authority as ga
    import lib.audience_context as ac

    seed = bytes.fromhex(
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
    )
    authority_uid = "a1b2c3d4"
    signing_key_uid = "e5f6a7b8"
    mike_group = "11111111"
    mike_principal = "7b921d17"

    priv = Ed25519PrivateKey.from_private_bytes(seed)
    pub_b64 = ga.public_key_base64(priv.public_key())
    fingerprint = ga.fingerprint(pub_b64)

    group_dicts = [_group(mike_group, "mike", members=[mike_principal])]
    claims = [
        {
            "principal_uid": mike_principal,
            "principal_class": "human",
            "status": "active",
            "source_authority_uid": authority_uid,
            "source_revision": "1",
        }
    ]

    groups = ga.build_groups_jsonl(group_dicts)
    principals = ga.build_principals_jsonl(claims)
    policy_json = ga.build_audience_policy(private_group_uid=mike_group)
    manifest = ga.build_artifact_manifest(
        {
            "groups.jsonl": groups,
            "principals.jsonl": principals,
            "audience-policy.json": policy_json,
        }
    )
    tuple_fields = ga.build_authority_tuple(
        authority_uid=authority_uid,
        groups_jsonl=groups,
        principals_jsonl=principals,
        audience_policy_json=policy_json,
        artifact_manifest_json=manifest,
        authority_generation=1,
        signing_key_uid=signing_key_uid,
        previous_envelope_sha256=None,
    )
    signature = ga.sign_authority_tuple(tuple_fields, seed)
    envelope = ga.build_signed_envelope(tuple_fields, signature)
    envelope_bytes = ga.canonical_envelope_bytes(envelope)
    trust = {
        "accepted_keys": [
            ga.accept_authority_key(
                authority_uid=authority_uid,
                key_uid=signing_key_uid,
                public_key_b64=pub_b64,
                expected_fingerprint=fingerprint,
                accepted_by=mike_principal,
                accepted_at="2026-07-18T00:00:00Z",
            )
        ],
        "high_water": {},
    }
    verified = ga.verify_authority(
        signed_envelope=envelope_bytes,
        artifacts={
            "groups.jsonl": groups,
            "principals.jsonl": principals,
            "audience-policy.json": policy_json,
            "artifact-manifest.json": manifest,
        },
        trust_record=trust,
        expected_fingerprint=fingerprint,
    )
    context = ac.AudienceContext.build(
        group_authority=envelope,
        verified=verified,
        private_alias_group_uid=mike_group,
        reserved_os_always_readable=True,
    )
    # ONE resolver, pinned to the verified corpus revision, used both for
    # membership (in ViewerProjection) and inside the policy adapter.
    corpus = build_group_corpus(
        {g["uid"]: g for g in group_dicts}, {mike_principal: _principal(mike_principal)}
    )
    projection = project_registry(
        corpus,
        AuthorityRevisionContext(
            source_authority_uid=authority_uid,
            source_revision=verified.corpus_revision,
            principal_directory_revision=verified.principal_directory_revision,
            source_paths={g["uid"]: f"vault/groups/{g['uid']}.md" for g in group_dicts},
        ),
    )
    resolver = GroupResolver.from_projection(projection)
    policy = context.adapter(resolver)
    return policy, resolver, mike_group, mike_principal


if __name__ == "__main__":
    unittest.main()
