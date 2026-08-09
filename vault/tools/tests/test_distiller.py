#!/usr/bin/env python3
"""Executable contract for the distiller's deterministic COMPOSITION.

Pairs dev-spec ``5b532f4b`` (activation ``e08ed396``) and test-spec ``120d5b3a``
(cycle brief ``6da0d037``; composes the landed walk ``5043b274`` / circle
``e12ff178`` / ranker ``1230fa5d``). One test class per dev-spec acceptance
criterion (1-based), driving ``orient_deterministic`` END-TO-END against ONE
sandboxed, segment-tagged, typed, state/decay-tagged fixture graph — the SAME
planted graph yields a matched ``(projection, circle_index, rank_index)`` triple,
so visibility (projection), circle structure (circle_index), and rank lifecycle
fields (rank_index) all agree on one graph — plus a live fail-closed smoke against
the real ``00-index.sqlite`` (cutover inactive here).

Coverage -> acceptance-criterion map (test-spec §Coverage):

* AC1 COMPOSITION / SEAM FIT — orders EXACTLY the circle's members (no data-losing adapter)
* AC2 VIEWER-SAFETY END-TO-END (the gate) — peer excludes owner-private, byte-identical
      across 0/1/N hidden neighbours; owner sees them — against the COMPOSED output
* AC3 PROVENANCE SURVIVES THE CHAIN — each item carries circle reason AND rank breakdown+score
* AC4 DETERMINISTIC + BUDGET END-TO-END — identical canonical across runs; budget flows through
* AC5 FAIL-CLOSED PROPAGATION — typed error on unresolved visibility + live sqlite smoke
* AC6 DETERMINISTIC-ONLY — delegates to draw_circle + rank_circle; no re-impl; no model/distill

The fixture reuses ``test_task_circle.py`` / ``test_distiller_ranker.py`` verbatim:
temp vault-roots whose manifest UID == segment UID so ``derive_segment`` yields the
segment (segment is NEVER a hand field), and a pinned B4a resolver synthesised from
an injected group corpus. The end-to-end viewer-safety plant seeds REAL owner-private
(alice) neighbours a naive seam would re-leak to a peer (bob); the raw graph neighbour
count is asserted to grow with the hidden count while the peer's composed result stays
byte-identical.
"""
from __future__ import annotations

import dataclasses
import inspect
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


DI_PATH = TOOLS / "lib" / "distiller.py"

# Reference the REAL landed modules the composition itself imports, so class
# identity is consistent end-to-end (the distiller builds lib.task_circle /
# lib.distiller_ranker values; the tests assert against the SAME classes).
import lib.viewer_projection as vp  # noqa: E402
import lib.task_circle as tc  # noqa: E402
import lib.distiller_ranker as dr  # noqa: E402
import lib.distiller as di  # noqa: E402
import lib.distiller_query as dq  # noqa: E402

from lib.group_contract import (  # noqa: E402
    GroupContractError,
    GroupErrorCode,
    build_group_corpus,
    semantic_hash,
)
from lib.group_registry import (  # noqa: E402
    AuthorityRevisionContext,
    GroupResolver,
    project_registry,
)

Viewer = vp.Viewer
ViewerProjection = vp.ViewerProjection
InMemoryGraphSource = vp.InMemoryGraphSource
GraphError = vp.GraphError
GraphErrorCode = vp.GraphErrorCode

Circle = tc.Circle
CircleMember = tc.CircleMember
InMemoryStructuralIndex = tc.InMemoryStructuralIndex
SqliteStructuralIndex = tc.SqliteStructuralIndex
draw_circle = tc.draw_circle

rank_circle = dr.rank_circle
InMemoryRankIndex = dr.InMemoryRankIndex
SqliteRankIndex = dr.SqliteRankIndex
DEFAULT_WEIGHTS = dr.DEFAULT_WEIGHTS
FEATURE_NAMES = dr.FEATURE_NAMES

orient_deterministic = di.orient_deterministic
DeterministicOrientation = di.DeterministicOrientation
OrientedItem = di.OrientedItem


# --------------------------------------------------------------------------- #
# Principals + segment UIDs (all 8-hex; segment UIDs double as manifest UIDs).  #
# --------------------------------------------------------------------------- #
ALICE = "a1a1a1a1"
BOB = "b2b2b2b2"

TEAM = "7ea70001"        # the shared team/vault segment (alice + bob)
PRIV_ALICE = "b1a70001"  # alice's own private segment
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


def _group(uid: str, slug: str, *, members) -> dict:
    group = {
        "uid": uid,
        "type": "group",
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "description": f"Purpose of {slug}.",
        "owner": members[0],
        "members": list(members),
        "includes_groups": [],
        "status": "active",
        "version": 1,
    }
    group["semantic_hash"] = semantic_hash(group)
    return group


def base_resolver() -> GroupResolver:
    """TEAM with alice + bob as DIRECT members (peers of each other)."""

    corpus = build_group_corpus(
        {TEAM: _group(TEAM, "team", members=[ALICE, BOB])},
        {ALICE: _principal(ALICE), BOB: _principal(BOB)},
    )
    projection = project_registry(
        corpus,
        AuthorityRevisionContext(
            source_authority_uid="a1b2c3d4",
            source_revision=REVISION,
            principal_directory_revision="1",
            source_paths={TEAM: f"vault/groups/{TEAM}.md"},
        ),
    )
    return GroupResolver.from_projection(projection)


# --------------------------------------------------------------------------- #
# Sandbox segment-tagging: temp vault-roots whose manifest UID == segment UID.  #
# (Copied from test_task_circle.py / test_distiller_ranker.py so segment is     #
# always the DERIVED value — never a hand field on the record.)                 #
# --------------------------------------------------------------------------- #
class _RootFactory:
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


class _OrientFixture:
    """Plants ONE segment-tagged graph with TYPED structural edges + per-node
    lifecycle (status/state) + decay signals, then emits a MATCHED triple over
    that single graph: a :class:`ViewerProjection` (visibility floor + authority),
    an :class:`InMemoryStructuralIndex` (the circle's seed structure + decay), and
    an :class:`InMemoryRankIndex` (the ranker's type/status/state/decay). All
    three read the SAME planted nodes/edges, so the composed pipeline is driven
    over one honest graph.

    ``node`` registers a segment-tagged node in the graph + BOTH indexes.
    ``rel`` plants a typed structural edge (member_of / refs / governed_by) —
    recorded in the structural index AND as a directed graph edge (so the
    projection sees it as a neighbour in either direction). ``neighbor`` plants an
    UNTYPED adjacency edge only.
    """

    def __init__(self, roots: _RootFactory) -> None:
        self._roots = roots
        self._records: dict = {}      # graph records (for derive_segment)
        self._node_root: dict = {}
        self._edges: list = []
        self._structures: dict = {}   # circle structural index
        self._rankrecs: dict = {}     # ranker lifecycle index

    def node(
        self,
        uid: str,
        segment_uid: str,
        *,
        type_: str = "task",
        status=None,
        state=None,
        decay=None,
    ) -> str:
        if segment_uid == OS:
            self._records[uid] = {
                "uid": uid,
                "extraction_scope": "ship",
                "path": f"os_root/{uid}.md",
            }
            self._node_root[uid] = self._roots.os_root()
        else:
            self._records[uid] = {"uid": uid, "path": f"vault/files/{uid}.md"}
            self._node_root[uid] = self._roots.manifest_root(segment_uid)
        self._structures[uid] = {
            "type": type_,
            "member_of": [],
            "refs": [],
            "governed_by": [],
            "decay": decay,
        }
        self._rankrecs[uid] = {
            "type": type_,
            "status": status,
            "state": state,
            "decay": decay,
        }
        return uid

    def rel(self, src: str, dst: str, kind: str) -> None:
        assert kind in ("member_of", "refs", "governed_by")
        self._structures[src][kind].append(dst)
        self._edges.append((src, dst))  # directed; adjacency reads both directions

    def neighbor(self, a: str, b: str) -> None:
        """An untyped direct edge (e.g. a `mentions`-class neighbour)."""

        self._edges.append((a, b))

    def projection(self) -> ViewerProjection:
        graph = InMemoryGraphSource(self._edges, self._records, self._node_root)
        return ViewerProjection.from_resolver(graph, base_resolver())

    def circle_index(self) -> InMemoryStructuralIndex:
        return InMemoryStructuralIndex(self._structures)

    def rank_index(self) -> InMemoryRankIndex:
        return InMemoryRankIndex(self._rankrecs)


def alice(private: str = PRIV_ALICE) -> Viewer:
    return Viewer(principal_uid=ALICE, private_segment_uid=private)


def bob(private: str = PRIV_BOB) -> Viewer:
    return Viewer(principal_uid=BOB, private_segment_uid=private)


class _OrientCase(unittest.TestCase):
    def setUp(self) -> None:
        self.roots = _RootFactory()
        self.addCleanup(self.roots.cleanup)

    def orient(self, fx: _OrientFixture, task, viewer, budget):
        return orient_deterministic(
            task,
            viewer,
            budget,
            projection=fx.projection(),
            circle_index=fx.circle_index(),
            rank_index=fx.rank_index(),
        )

    def manual_circle(self, fx: _OrientFixture, task, viewer, budget):
        return draw_circle(task, viewer, budget, projection=fx.projection(), index=fx.circle_index())

    def manual_ranked(self, fx: _OrientFixture, circle, task, viewer):
        return rank_circle(circle, task, viewer, projection=fx.projection(), index=fx.rank_index())


# =========================================================================== #
# AC1 — COMPOSITION (one call, seam fit): orders EXACTLY the circle's members  #
# =========================================================================== #
class AC1CompositionSeamFit(_OrientCase):
    def _fixture(self) -> _OrientFixture:
        # A task with a governing capsule, two refs, a parent + same-type sibling,
        # and a hop node — so the drawn circle is non-trivial and the ranked order
        # (capsule outranks work) differs from the circle's structural order.
        fx = _OrientFixture(self.roots)
        fx.node("task0001", TEAM, type_="task", status="active")
        fx.node("gov00000", TEAM, type_="capsule", status="active")
        fx.node("ref00001", TEAM, type_="note", status="active")
        fx.node("ref00002", TEAM, type_="note", status="draft")
        fx.node("p1000000", TEAM, type_="project", status="active")
        fx.node("sib00001", TEAM, type_="task", status="active")
        fx.node("hopnode0", TEAM, type_="note", status="active")
        fx.rel("task0001", "gov00000", "governed_by")
        fx.rel("task0001", "ref00001", "refs")
        fx.rel("task0001", "ref00002", "refs")
        fx.rel("task0001", "p1000000", "member_of")
        fx.rel("sib00001", "p1000000", "member_of")
        fx.neighbor("ref00001", "hopnode0")
        return fx

    def test_returns_deterministic_orientation_wrapping_ranked_circle(self) -> None:
        fx = self._fixture()
        result = self.orient(fx, "task0001", bob(), 64)
        self.assertTrue(result.ok, msg=result.error)
        orientation = result.value
        self.assertIsInstance(orientation, DeterministicOrientation)
        # It wraps the RankedCircle produced by rank_circle.
        self.assertIs(type(orientation.ranked), dr.RankedCircle)
        self.assertEqual(orientation.task_uid, "task0001")

    def test_orders_exactly_the_circles_members(self) -> None:
        fx = self._fixture()
        circle = self.manual_circle(fx, "task0001", bob(), 64).value
        orientation = self.orient(fx, "task0001", bob(), 64).value
        # Same membership (exactly), no more, no fewer — no data-losing adapter.
        self.assertEqual(set(orientation.uids()), set(circle.uids()))
        self.assertEqual(len(orientation.items), len(circle.members))

    def test_composed_order_equals_manual_draw_then_rank(self) -> None:
        # The seam fits: composing == draw_circle THEN rank_circle, run by hand.
        fx = self._fixture()
        circle = self.manual_circle(fx, "task0001", bob(), 64).value
        ranked = self.manual_ranked(fx, circle, "task0001", bob()).value
        orientation = self.orient(fx, "task0001", bob(), 64).value
        self.assertEqual(orientation.uids(), ranked.uids())
        self.assertEqual(orientation.ranked.canonical(), ranked.canonical())

    def test_ranked_order_is_not_merely_the_circle_structural_order(self) -> None:
        # Proof the ranker actually ran across the seam: the ranked order is
        # score-descending and differs from the circle's structural order.
        #
        # The top member changed from `gov00000` to `ref00001` when relation
        # specificity landed (a0c648f3 / Argus A144 ruling 2026-08-03), and that
        # IS the fix rather than a regression: `gov00000` is admitted by an
        # automatic `governed_by` edge, `ref00001` by a reference the work's
        # author wrote. The governing capsule still outranks the structurally-
        # closer members, so the property this case was written to prove is
        # intact — only the deliberate reference now sits above it.
        fx = self._fixture()
        circle = self.manual_circle(fx, "task0001", bob(), 64).value
        orientation = self.orient(fx, "task0001", bob(), 64).value
        uids = orientation.uids()
        self.assertIn("gov00000", uids)
        self.assertEqual(uids[0], "ref00001")  # deliberate reference leads
        # The governing capsule is now BELOW the structural parent, which is the
        # correction rather than a regression: `governed_by` is attached
        # automatically and `member_of` is not, so the capsule's top layer tier
        # no longer carries it past a node the graph actually placed here.
        self.assertLess(uids.index("p1000000"), uids.index("gov00000"))
        # And the boost is NOT an override: ref00002 is admitted by the same
        # deliberate `refs` edge as ref00001 but is a DRAFT, and it lands below
        # both the parent and the governing capsule. Lifecycle still wins.
        self.assertEqual(orientation.item("ref00002").relation, "ref-of-task")
        self.assertLess(uids.index("gov00000"), uids.index("ref00002"))
        self.assertNotEqual(uids, circle.uids())


# =========================================================================== #
# AC2 — VIEWER-SAFETY END-TO-END (the gate): the WHOLE pipeline preserves it  #
# =========================================================================== #
class AC2ViewerSafetyEndToEnd(_OrientCase):
    def _fixture(self, hidden_count: int):
        """A task with one VISIBLE team ref and a VARYING number of owner-private
        (alice) refs a naive seam would re-leak to a peer (bob)."""

        fx = _OrientFixture(self.roots)
        fx.node("task0001", TEAM, type_="task", status="active")
        fx.node("teamref0", TEAM, type_="note", status="active")
        fx.rel("task0001", "teamref0", "refs")
        hidden = []
        for i in range(hidden_count):
            uid = f"prv{i:05x}"
            fx.node(uid, PRIV_ALICE, type_="note", status="active")
            fx.rel("task0001", uid, "refs")  # a private ref: hidden from a peer
            hidden.append(uid)
        return fx, hidden

    def test_peer_composed_result_excludes_owner_private_nodes(self) -> None:
        fx, hidden = self._fixture(3)
        orientation = self.orient(fx, "task0001", bob(), 64).value
        peer_uids = set(orientation.uids())
        self.assertIn("teamref0", peer_uids)
        for uid in hidden:
            self.assertNotIn(uid, peer_uids)
            # nor anywhere in the auditable composed surface (canonical)
            self.assertNotIn(uid, orientation.canonical())

    def test_owner_composed_result_includes_them_proving_true_filtering(self) -> None:
        # The SAME private nodes invisible to the peer ARE in the owner's composed
        # result — so the peer's exclusion is true filtering, not dropped edges.
        fx, hidden = self._fixture(3)
        owner_uids = set(self.orient(fx, "task0001", alice(), 64).value.uids())
        self.assertIn("teamref0", owner_uids)
        for uid in hidden:
            self.assertIn(uid, owner_uids)

    def test_peer_composed_canonical_byte_identical_across_0_1_and_N_hidden(self) -> None:
        baseline = None
        for hidden_count in (0, 1, 5):
            fx, hidden = self._fixture(hidden_count)

            # HONESTY GATE: the fixture GENUINELY contains hidden owner-private
            # neighbours a seam bug could re-leak (raw graph neighbour count grows).
            raw = fx.projection()._graph.neighbors("task0001")
            self.assertEqual(len(raw), 1 + hidden_count)
            for uid in hidden:
                self.assertIn(uid, raw)

            # The property runs against the COMPOSED output, not per-module output.
            canonical = self.orient(fx, "task0001", bob(), 64).value.canonical()
            if baseline is None:
                baseline = canonical
            else:
                self.assertEqual(canonical, baseline)

    def test_boundary_holds_across_both_stages_not_just_one(self) -> None:
        # Belt-and-braces: the composed peer result equals the per-module chain
        # (draw then rank) run by hand — the boundary is not re-crossed at the
        # seam, and the composition adds no leak the modules did not already close.
        fx, hidden = self._fixture(4)
        circle = self.manual_circle(fx, "task0001", bob(), 64).value
        ranked = self.manual_ranked(fx, circle, "task0001", bob()).value
        orientation = self.orient(fx, "task0001", bob(), 64).value
        self.assertEqual(orientation.uids(), ranked.uids())
        for uid in hidden:
            self.assertNotIn(uid, circle.uids())
            self.assertNotIn(uid, orientation.uids())


# =========================================================================== #
# AC3 — PROVENANCE SURVIVES THE CHAIN (both layers on every composed item)    #
# =========================================================================== #
class AC3ProvenanceSurvives(_OrientCase):
    def _fixture(self) -> _OrientFixture:
        fx = _OrientFixture(self.roots)
        fx.node("task0001", TEAM, type_="task", status="active")
        fx.node("ref00001", TEAM, type_="note", status="active")
        fx.node("gov00000", TEAM, type_="capsule", status="locked")
        fx.node("hopnode0", TEAM, type_="note", status="draft")  # reached by expansion
        fx.rel("task0001", "ref00001", "refs")
        fx.rel("task0001", "gov00000", "governed_by")
        fx.neighbor("ref00001", "hopnode0")
        return fx

    def test_every_item_carries_both_provenance_layers(self) -> None:
        fx = self._fixture()
        orientation = self.orient(fx, "task0001", bob(), 64).value
        self.assertTrue(orientation.items)
        for item in orientation.items:
            # Layer 1 — circle-inclusion provenance (from the CircleMember).
            self.assertIsInstance(item.circle_member, tc.CircleMember)
            self.assertTrue(item.circle_provenance)
            self.assertIn(":", item.circle_provenance)
            self.assertIn(item.relation, tc._REL_PRIORITY)
            # Layer 2 — rank feature-breakdown + score (from the RankedMember).
            self.assertIsInstance(item.ranked_member, dr.RankedMember)
            self.assertIsInstance(item.breakdown, dr.FeatureBreakdown)
            self.assertEqual(set(item.contributions), set(FEATURE_NAMES))
            self.assertIsInstance(item.score, float)

    def test_circle_reason_reconstructable_from_composed_result(self) -> None:
        # The circle-inclusion reason survives verbatim through the seam.
        fx = self._fixture()
        circle = self.manual_circle(fx, "task0001", bob(), 64).value
        orientation = self.orient(fx, "task0001", bob(), 64).value
        self.assertEqual(
            orientation.item("ref00001").circle_provenance, f"{tc.REL_REF}:task0001"
        )
        self.assertEqual(
            orientation.item("gov00000").circle_provenance,
            f"{tc.REL_GOVERNED_BY}:task0001",
        )
        self.assertEqual(
            orientation.item("hopnode0").circle_provenance,
            f"{tc.REL_WALK_HOP}:ref00001",
        )
        # And it matches exactly what the drawn circle recorded (nothing mutated).
        for uid in circle.uids():
            self.assertEqual(
                orientation.item(uid).circle_provenance, circle.reason(uid)
            )

    def test_rank_breakdown_and_score_reconstructable_from_composed_result(self) -> None:
        # breakdown · effective-weights == score, reconstructed from the composed
        # item alone (the rank audit surface survives the seam intact).
        fx = self._fixture()
        orientation = self.orient(fx, "task0001", bob(), 64).value
        weights = orientation.weights
        for item in orientation.items:
            reconstructed = sum(
                getattr(weights, name) * getattr(item.breakdown, name)
                for name in FEATURE_NAMES
            )
            self.assertAlmostEqual(reconstructed, item.score, places=12)
            self.assertAlmostEqual(
                sum(item.contributions.values()), item.score, places=12
            )

    def test_composed_item_matches_underlying_landed_values(self) -> None:
        # Both layers are the EXACT landed values — no re-wrapping that drops data.
        fx = self._fixture()
        circle = self.manual_circle(fx, "task0001", bob(), 64).value
        ranked = self.manual_ranked(fx, circle, "task0001", bob()).value
        orientation = self.orient(fx, "task0001", bob(), 64).value
        circle_by_uid = {m.uid: m for m in circle.members}
        for uid in orientation.uids():
            item = orientation.item(uid)
            self.assertEqual(item.circle_member, circle_by_uid[uid])
            self.assertEqual(item.ranked_member, ranked.member(uid))

    def test_canonical_embeds_both_layers(self) -> None:
        import json

        fx = self._fixture()
        orientation = self.orient(fx, "task0001", bob(), 64).value
        parsed = json.loads(orientation.canonical())
        self.assertEqual(parsed["task"], "task0001")
        self.assertEqual(len(parsed["items"]), len(orientation.items))
        for entry in parsed["items"]:
            self.assertIn("provenance", entry["circle"])   # circle layer present
            self.assertIn("relation", entry["circle"])
            self.assertIn("score", entry["rank"])           # rank layer present
            self.assertEqual(set(entry["rank"]["breakdown"]), set(FEATURE_NAMES))


# =========================================================================== #
# AC4 — DETERMINISTIC + BUDGET END-TO-END                                     #
# =========================================================================== #
class AC4DeterministicAndBudget(_OrientCase):
    def _fixture(self) -> _OrientFixture:
        fx = _OrientFixture(self.roots)
        fx.node("task0001", TEAM, type_="task", status="active")
        for uid, kind in (
            ("aaa00000", "note"),
            ("bbb00000", "capsule"),
            ("ccc00000", "decision"),
        ):
            fx.node(uid, TEAM, type_=kind, status="active")
        fx.rel("task0001", "aaa00000", "refs")
        # a cycle a -> b -> c -> a (visited-set must terminate it)
        fx.neighbor("aaa00000", "bbb00000")
        fx.neighbor("bbb00000", "ccc00000")
        fx.neighbor("ccc00000", "aaa00000")
        return fx

    def test_identical_composed_canonical_across_runs(self) -> None:
        fx = self._fixture()
        a = self.orient(fx, "task0001", bob(), 64).value
        b = self.orient(fx, "task0001", bob(), 64).value
        self.assertEqual(a.canonical(), b.canonical())
        self.assertEqual(a.uids(), b.uids())

    def test_composed_order_is_score_descending(self) -> None:
        fx = self._fixture()
        orientation = self.orient(fx, "task0001", bob(), 64).value
        scores = [item.score for item in orientation.items]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_budget_flows_through_to_the_circle_draw(self) -> None:
        fx = self._fixture()
        # budget 0 -> empty circle -> empty composed result.
        self.assertEqual(len(self.orient(fx, "task0001", bob(), 0).value.items), 0)
        # A bounded budget bounds the composed membership, and the composed
        # membership is EXACTLY the circle drawn at that same budget (budget flowed
        # through to draw_circle).
        for budget in (1, 2, 3):
            circle = self.manual_circle(fx, "task0001", bob(), budget).value
            orientation = self.orient(fx, "task0001", bob(), budget).value
            self.assertLessEqual(len(orientation.items), budget)
            self.assertEqual(set(orientation.uids()), set(circle.uids()))

    def test_invalid_budget_refuses_through_the_composition(self) -> None:
        fx = self._fixture()
        for bad in (-1, "3", 3.0, True):
            result = self.orient(fx, "task0001", bob(), bad)
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, GraphErrorCode.BUDGET_INVALID)

    def test_no_wallclock_or_nondeterminism_in_source(self) -> None:
        source = DI_PATH.read_text(encoding="utf-8")
        for banned in ("time.time", "datetime.now", "random.", "uuid", "monotonic"):
            self.assertNotIn(banned, source)


# =========================================================================== #
# AC5 — FAIL-CLOSED PROPAGATION (typed error; never a partial)                #
# =========================================================================== #
class AC5FailClosedPropagation(_OrientCase):
    def _fixture(self):
        fx = _OrientFixture(self.roots)
        fx.node("task0001", TEAM, type_="task", status="active")
        fx.node("teamref0", TEAM, type_="note", status="active")
        fx.rel("task0001", "teamref0", "refs")
        # plant private neighbours too, so a permissive fallback would leak them
        for i in range(2):
            uid = f"prv{i:05x}"
            fx.node(uid, PRIV_ALICE, type_="note", status="active")
            fx.rel("task0001", uid, "refs")
        return fx

    def test_unresolved_visibility_propagates_typed_error_not_a_partial(self) -> None:
        fx = self._fixture()
        graph = InMemoryGraphSource(fx._edges, fx._records, fx._node_root)
        stale = GroupContractError(GroupErrorCode.GROUP_CORPUS_STALE, "stale authority")
        proj = ViewerProjection(graph, resolver=None, resolver_error=stale)
        result = orient_deterministic(
            "task0001",
            bob(),
            64,
            projection=proj,
            circle_index=fx.circle_index(),
            rank_index=fx.rank_index(),
        )
        # A typed GraphError, fail-closed — and NO partial orientation returned.
        self.assertFalse(result.ok)
        self.assertIsInstance(result.error, GraphError)
        self.assertEqual(result.error.code, GraphErrorCode.VISIBILITY_UNRESOLVED)
        self.assertEqual(
            result.error.audience_error.code, GroupErrorCode.GROUP_CORPUS_STALE
        )
        self.assertIsNone(result.value)

    def test_unknown_task_propagates_typed_error(self) -> None:
        # A task absent from the index fails closed at the draw stage; the typed
        # NODE_NOT_FOUND propagates through the composition (never a partial).
        fx = self._fixture()
        result = self.orient(fx, "nosuch00", bob(), 64)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, GraphErrorCode.NODE_NOT_FOUND)
        self.assertIsNone(result.value)

    def test_live_smoke_against_real_index_fails_closed(self) -> None:
        # Live smoke: orient_deterministic over the real composed union index via
        # ViewerProjection.from_repo_root (cutover INACTIVE on this Studio) returns
        # the typed fail-closed error — never a partial/permissive orientation.
        repo_root = "/workspace"
        index_path = Path(repo_root) / "vault" / "00-index.sqlite"
        if not index_path.exists():  # pragma: no cover - environment guard
            self.skipTest("real 00-index.sqlite not present in this environment")
        projection = ViewerProjection.from_repo_root(repo_root)
        circle_index = SqliteStructuralIndex(index_path)
        rank_index = SqliteRankIndex(index_path)
        # '5b532f4b' is this very dev-spec — a real entry in the index, so the
        # draw reaches the visibility resolution and fails closed there (rather
        # than short-circuiting on NODE_NOT_FOUND).
        result = orient_deterministic(
            "5b532f4b",
            bob(),
            32,
            projection=projection,
            circle_index=circle_index,
            rank_index=rank_index,
        )
        self.assertFalse(result.ok)  # typed fail-closed error, not a partial
        self.assertIsInstance(result.error, GraphError)
        self.assertEqual(result.error.code, GraphErrorCode.VISIBILITY_UNRESOLVED)
        self.assertIsNone(result.value)


# =========================================================================== #
# AC6 — DETERMINISTIC-ONLY (delegates; no re-impl; no model/distill)          #
# =========================================================================== #
class AC6DeterministicOnly(_OrientCase):
    def setUp(self) -> None:
        super().setUp()
        self.source = DI_PATH.read_text(encoding="utf-8")

    def test_imports_and_calls_both_landed_stages(self) -> None:
        self.assertIn("from lib.task_circle import", self.source)
        self.assertIn("draw_circle(", self.source)
        self.assertIn("from lib.distiller_ranker import", self.source)
        self.assertIn("rank_circle(", self.source)

    def test_defines_no_independent_walk_rank_or_neighbor_logic(self) -> None:
        # The composition delegates: it never reads a raw graph edge, never
        # resolves visibility itself, never computes authority or membership, and
        # never re-derives seeds/segments — all of that belongs to the landed
        # modules it calls.
        for banned in (
            ".adjacency(",
            ".neighbors(",
            ".inbound_sources(",
            ".authority(",
            ".walk(",
            "derive_segment",
            "derive_seeds(",
            "children_of(",
        ):
            self.assertNotIn(banned, self.source, msg=f"unexpected {banned}")
        # And it defines no function of its own that re-implements a walk/rank.
        self.assertIsNone(re.search(r"^\s*def\s+\w*walk\w*", self.source, re.M))
        self.assertIsNone(re.search(r"^\s*def\s+\w*rank\w*", self.source, re.M))

    def test_no_model_or_network_calls(self) -> None:
        for banned in (
            "import requests",
            "import urllib",
            "import http",
            "import socket",
            "openai",
            "anthropic",
            "httpx",
        ):
            self.assertNotIn(banned, self.source)

    def test_deterministic_core_still_has_no_query_distill_or_chunking(self) -> None:
        # Cut 4A adds an outer orient() chassis, but the frozen deterministic
        # function itself remains only draw -> rank -> provenance composition.
        deterministic_source = inspect.getsource(di.orient_deterministic)
        self.assertNotIn("resolve_query(", deterministic_source)
        self.assertNotIn("distill(", deterministic_source)
        self.assertNotIn("chunk", deterministic_source)
        item_fields = {f.name for f in di.OrientedItem.__dataclass_fields__.values()}
        orient_fields = {
            f.name for f in di.DeterministicOrientation.__dataclass_fields__.values()
        }
        forbidden = {"chunk", "chunks", "distilled", "text", "body", "content"}
        self.assertEqual(item_fields & forbidden, set())
        self.assertEqual(orient_fields & forbidden, set())

    def test_composed_output_preserves_both_provenance_layers_structurally(self) -> None:
        # The seam surface itself carries both landed values — a structural
        # guarantee that neither provenance layer can be dropped.
        item_fields = {f.name for f in di.OrientedItem.__dataclass_fields__.values()}
        self.assertIn("circle_member", item_fields)   # circle provenance layer
        self.assertIn("ranked_member", item_fields)   # rank breakdown+score layer


class Cut4ADeterministicRegression(_OrientCase):
    # Re-frozen 2026-08-03 when relation specificity landed as the fifth feature
    # (a0c648f3 / Argus A144 ruling). Verified by HAND before re-freezing rather
    # than regenerated and blessed: this member is admitted by `ref-of-task`, so
    # relation = 1.0 and its contribution is 1.0 · 0.35 = 0.35, taking the score
    # from 0.8975 to 0.2 + (-0.0) + 0.2475 + 0.35 + 0.45 = 1.2475. A golden
    # nobody recomputed is not a regression test.
    FROZEN_CANONICAL = (
        '{"items":[{"circle":{"distance":1,"provenance":"ref-of-task:task0001",'
        '"relation":"ref-of-task","via":"task0001"},"rank":{"breakdown":'
        '{"connectivity":1.0,"decay":0.0,"layer":0.55,"relation":1.0,'
        '"state":1.0},"contributions":{"connectivity":0.2,"decay":-0.0,'
        '"layer":0.2475,"relation":0.35,"state":0.45},"score":1.2475},'
        '"uid":"ref00001"}],"task":"task0001","tilt":"state","weights":'
        '{"connectivity":0.2,"decay":-0.15,"layer":0.45,"relation":0.35,'
        '"state":0.45}}'
    )

    def fixture(self):
        fx = _OrientFixture(self.roots)
        fx.node("task0001", TEAM, type_="task", status="active")
        fx.node("ref00001", TEAM, type_="note", status="active")
        fx.node("query001", TEAM, type_="note", status="active")
        fx.rel("task0001", "ref00001", "refs")
        return fx

    def test_pre_cut_canonical_is_literal_frozen_and_default_none_is_identical(self):
        fx = self.fixture()
        kwargs = {
            "projection": fx.projection(),
            "circle_index": fx.circle_index(),
            "rank_index": fx.rank_index(),
        }
        implicit = orient_deterministic("task0001", bob(), 1, **kwargs)
        explicit = orient_deterministic(
            "task0001", bob(), 1, query_seeds=None, **kwargs
        )
        self.assertTrue(implicit.ok and explicit.ok)
        self.assertEqual(implicit.value.canonical(), self.FROZEN_CANONICAL)
        self.assertEqual(explicit.value.canonical(), self.FROZEN_CANONICAL)

    def test_optional_bound_query_seed_delegates_without_changing_output_shape(self):
        fx = self.fixture()
        snapshot = "snapshot-distiller-1"
        viewer = bob()
        seeds = dq.PrevalidatedQuerySeeds(
            viewer, snapshot, ("query001",), False
        )
        result = orient_deterministic(
            "task0001",
            viewer,
            8,
            projection=fx.projection(),
            circle_index=tc.InMemoryStructuralIndex(
                fx._structures, index_as_of=snapshot
            ),
            rank_index=fx.rank_index(),
            query_seeds=seeds,
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertIsInstance(result.value, DeterministicOrientation)
        self.assertEqual(
            result.value.circle.reason("query001"),
            f"{tc.REL_QUERY_SEED}:task0001",
        )
        self.assertEqual(
            {f.name for f in dataclasses.fields(result.value)},
            {"task_uid", "circle", "ranked", "items"},
        )


if __name__ == "__main__":
    unittest.main()
