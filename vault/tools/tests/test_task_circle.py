#!/usr/bin/env python3
"""Executable contract for the distiller's deterministic scope-drawing.

Pairs dev-spec ``e12ff178`` (activation ``4f168aac``) and test-spec ``ee37d652``
(cycle brief ``6da0d037`` §5/§9; builds on the viewer-relative walk ``5043b274``).
One test class per dev-spec acceptance criterion (1-based), exercising
``draw_circle`` against a SANDBOXED fixture graph (synthesised segment-tagged
nodes/typed structural edges + planted gardener decay signals + a fixture B4a
authority) so seed-derivation, viewer-safety, and rot-rejection are provable
WITHOUT the live corpus and independent of the live Studio's cutover state.

Coverage -> acceptance-criterion map (test-spec §Coverage):

* AC1 STRUCTURAL SEED DERIVATION (deterministic, no model)
* AC2 VIEWER-SAFE BY CONSTRUCTION (composes on the walk; the leak class stays closed)
* AC3 DECAY-GATED — REJECTS ROT (both sides of the threshold; live edges only)
* AC4 DETERMINISTIC + BUDGET-BOUNDED (stable order; budget bound; cycles)
* AC5 AUDITABLE PROVENANCE (each member cites why, citing UIDs)
* AC6 NO RANKING / NO DISTILL / NO MODEL (structural review; expansion via viewer_projection)

The fixture reuses ``test_viewer_projection.py``'s approach verbatim: temp
vault-roots whose manifest UID == segment UID so ``derive_segment`` yields the
right segment (segment is NEVER a hand field), and a pinned B4a resolver
synthesised from an injected group corpus. The circle's structural index is
plumbed from the SAME planted edges, so visibility (projection) and structure
(index) agree on one graph.
"""
from __future__ import annotations

import importlib.util
import re
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


VP_PATH = TOOLS / "lib" / "viewer_projection.py"
TC_PATH = TOOLS / "lib" / "task_circle.py"
DG_PATH = TOOLS / "lib" / "decay_gate.py"
GARDENER_PATH = TOOLS / "lib" / "gardener.py"
vp = _load("viewer_projection_under_test", VP_PATH)
tc = _load("task_circle_under_test", TC_PATH)

from lib import decay_gate, gardener  # noqa: E402
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
draw_circle = tc.draw_circle
derive_seeds = tc.derive_seeds


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
# (Copied from test_viewer_projection.py so segment is always the DERIVED       #
# value — never a hand field on the record.)                                    #
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


class _CircleFixture:
    """Plants a segment-tagged graph with TYPED structural edges + decay signals,
    then emits a matched (ViewerProjection, InMemoryStructuralIndex) pair over the
    SAME single graph.

    ``node`` registers a segment-tagged node with a type and optional decay
    object. ``rel`` plants a typed structural edge (member_of / refs /
    governed_by) — recorded both in the structural index AND as a directed graph
    edge (so the projection sees it as a neighbour, in either direction).
    ``neighbor`` plants an UNTYPED adjacency edge only (a plain "direct
    neighbour" with no typed relation).
    """

    def __init__(self, roots: _RootFactory) -> None:
        self._roots = roots
        self._records: dict = {}
        self._node_root: dict = {}
        self._edges: list = []
        self._structures: dict = {}

    def node(self, uid: str, segment_uid: str, *, type_: str = "task", decay=None) -> str:
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
        return uid

    def rel(self, src: str, dst: str, kind: str) -> None:
        assert kind in ("member_of", "refs", "governed_by")
        self._structures[src][kind].append(dst)
        self._edges.append((src, dst))  # directed; adjacency reads both directions

    def neighbor(self, a: str, b: str) -> None:
        """An untyped direct edge (e.g. a `mentions`-class neighbour)."""

        self._edges.append((a, b))

    def edge_only(self, raw_target: str, segment_uid: str) -> str:
        """Register a graph endpoint with no indexed record or structure."""

        self._node_root[raw_target] = self._roots.manifest_root(segment_uid)
        return raw_target

    def projection(self) -> ViewerProjection:
        graph = InMemoryGraphSource(self._edges, self._records, self._node_root)
        return ViewerProjection.from_resolver(graph, base_resolver())

    def index(self) -> InMemoryStructuralIndex:
        return InMemoryStructuralIndex(self._structures)


def alice(private: str = PRIV_ALICE) -> Viewer:
    return Viewer(principal_uid=ALICE, private_segment_uid=private)


def bob(private: str = PRIV_BOB) -> Viewer:
    return Viewer(principal_uid=BOB, private_segment_uid=private)


class _CircleCase(unittest.TestCase):
    def setUp(self) -> None:
        self.roots = _RootFactory()
        self.addCleanup(self.roots.cleanup)

    def draw(self, fx: _CircleFixture, task, viewer, budget):
        return draw_circle(
            task, viewer, budget, projection=fx.projection(), index=fx.index()
        )

    def seeds(self, fx: _CircleFixture, task, viewer):
        return derive_seeds(task, viewer, projection=fx.projection(), index=fx.index())


# =========================================================================== #
# AC1 — STRUCTURAL SEED DERIVATION (deterministic, no model)                  #
# =========================================================================== #
class AC1StructuralSeedDerivation(_CircleCase):
    def _fixture(self) -> _CircleFixture:
        fx = _CircleFixture(self.roots)
        # The task and its structural lineage (all on TEAM, visible to a member).
        fx.node("task0001", TEAM, type_="task")
        fx.node("p1000000", TEAM, type_="project")   # direct parent
        fx.node("gp000000", TEAM, type_="project")   # grandparent (ONE hop up)
        fx.node("ggp00000", TEAM, type_="project")   # great-grandparent (must NOT seed)
        fx.node("ref00001", TEAM, type_="note")      # direct ref
        fx.node("ref00002", TEAM, type_="note")      # direct ref
        fx.node("refofref", TEAM, type_="note")      # ref-of-ref (must NOT seed)
        fx.node("gov00000", TEAM, type_="capsule")   # governing authority
        fx.node("sib00001", TEAM, type_="task")      # same-project SAME-type sibling
        fx.node("notsib00", TEAM, type_="note")      # same-project DIFFERENT-type (not a seed)
        fx.node("nbr00001", TEAM, type_="note")      # untyped direct neighbour

        fx.rel("task0001", "p1000000", "member_of")
        fx.rel("p1000000", "gp000000", "member_of")
        fx.rel("gp000000", "ggp00000", "member_of")
        fx.rel("task0001", "ref00001", "refs")
        fx.rel("task0001", "ref00002", "refs")
        fx.rel("ref00001", "refofref", "refs")
        fx.rel("task0001", "gov00000", "governed_by")
        fx.rel("sib00001", "p1000000", "member_of")
        fx.rel("notsib00", "p1000000", "member_of")
        fx.neighbor("task0001", "nbr00001")
        return fx

    def test_seed_set_is_exactly_the_direct_structural_closure(self) -> None:
        fx = self._fixture()
        result = self.seeds(fx, "task0001", alice())
        self.assertTrue(result.ok, msg=result.error)
        got = {(m.uid, m.relation, m.via, m.distance) for m in result.value}
        expected = {
            ("gov00000", tc.REL_GOVERNED_BY, "task0001", 1),
            ("ref00001", tc.REL_REF, "task0001", 1),
            ("ref00002", tc.REL_REF, "task0001", 1),
            ("p1000000", tc.REL_MEMBER_PARENT, "task0001", 1),
            ("nbr00001", tc.REL_NEIGHBOR, "task0001", 1),
            ("gp000000", tc.REL_MEMBER_ANCESTOR, "p1000000", 2),
            ("sib00001", tc.REL_TYPE_SIBLING, "p1000000", 2),
        }
        self.assertEqual(got, expected)

    def test_no_transitive_explosion(self) -> None:
        # The unbounded-closure hazards are absent from the SEED set: the
        # great-grandparent, the ref-of-ref, and the different-type "sibling".
        fx = self._fixture()
        seed_uids = {m.uid for m in self.seeds(fx, "task0001", alice()).value}
        for forbidden in ("ggp00000", "refofref", "notsib00"):
            self.assertNotIn(forbidden, seed_uids)

    def test_seed_derivation_is_deterministic_no_model(self) -> None:
        fx = self._fixture()
        a = self.seeds(fx, "task0001", alice()).value
        b = self.seeds(fx, "task0001", alice()).value
        self.assertEqual([m._sort_key() for m in a], [m._sort_key() for m in b])
        # Structural review: the module imports no model/network client.
        source = TC_PATH.read_text(encoding="utf-8")
        for banned in ("import requests", "import urllib", "import http", "openai", "anthropic"):
            self.assertNotIn(banned, source)

    def test_unknown_task_refuses(self) -> None:
        fx = self._fixture()
        result = self.seeds(fx, "nosuch00", alice())
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, GraphErrorCode.NODE_NOT_FOUND)


# =========================================================================== #
# AC2 — VIEWER-SAFE BY CONSTRUCTION (composes on the walk)                    #
# =========================================================================== #
class AC2ViewerSafeByConstruction(_CircleCase):
    def _fixture(self, hidden_count: int) -> _CircleFixture:
        """A task with one VISIBLE team ref and a VARYING number of owner-private
        (alice) refs a naive circle would leak to a peer."""

        fx = _CircleFixture(self.roots)
        fx.node("task0001", TEAM, type_="task")
        fx.node("teamref0", TEAM, type_="note")
        fx.rel("task0001", "teamref0", "refs")
        hidden = []
        for i in range(hidden_count):
            uid = f"prv{i:05x}"
            fx.node(uid, PRIV_ALICE, type_="note")
            fx.rel("task0001", uid, "refs")  # a private ref: hidden from a peer
            hidden.append(uid)
        return fx, hidden

    def test_peer_circle_excludes_owner_private_nodes(self) -> None:
        fx, hidden = self._fixture(3)
        peer_circle = self.draw(fx, "task0001", bob(), 64).value
        peer_uids = set(peer_circle.uids())
        self.assertIn("teamref0", peer_uids)
        for uid in hidden:
            self.assertNotIn(uid, peer_uids)

    def test_owner_circle_includes_them_proving_true_filtering(self) -> None:
        # The SAME private nodes invisible to the peer ARE in the owner's circle,
        # so the peer's exclusion is true filtering, not universally-dropped edges.
        fx, hidden = self._fixture(3)
        owner_uids = set(self.draw(fx, "task0001", alice(), 64).value.uids())
        for uid in hidden:
            self.assertIn(uid, owner_uids)

    def test_peer_circle_byte_identical_across_0_1_and_N_hidden(self) -> None:
        baseline = None
        for hidden_count in (0, 1, 5):
            fx, hidden = self._fixture(hidden_count)

            # Sanity: the fixture GENUINELY contains hidden neighbours a naive
            # implementation would leak (the raw graph neighbour count grows).
            raw = fx.projection()._graph.neighbors("task0001")
            self.assertEqual(len(raw), 1 + hidden_count)
            for uid in hidden:
                self.assertIn(uid, raw)

            canonical = self.draw(fx, "task0001", bob(), 64).value.canonical()
            if baseline is None:
                baseline = canonical
            else:
                self.assertEqual(canonical, baseline)

    def test_fail_closed_when_visibility_unresolved(self) -> None:
        fx, _ = self._fixture(2)
        graph = InMemoryGraphSource(fx._edges, fx._records, fx._node_root)
        stale = GroupContractError(GroupErrorCode.GROUP_CORPUS_STALE, "stale authority")
        proj = ViewerProjection(graph, resolver=None, resolver_error=stale)
        result = draw_circle("task0001", bob(), 64, projection=proj, index=fx.index())
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, GraphErrorCode.VISIBILITY_UNRESOLVED)
        self.assertEqual(
            result.error.audience_error.code, GroupErrorCode.GROUP_CORPUS_STALE
        )


# =========================================================================== #
# AC3 — DECAY-GATED — REJECTS ROT (both sides of the threshold)               #
# =========================================================================== #
def _decay(stale: bool, confidence: float, *signals) -> dict:
    return {
        "stale": stale,
        "signals": list(signals),
        "reason": "planted",
        "confidence": confidence,
        "swept": "2026-07-22",
    }


class R5SharedDecayLifecycleGate(unittest.TestCase):
    def test_decay_boundary_and_neutral_metadata(self) -> None:
        cases = (
            (None, False),
            ({}, False),
            ({"stale": False, "confidence": 1.0}, False),
            ({"stale": True, "confidence": 0.79}, False),
            ({"stale": True, "confidence": 0.8}, True),
            ({"stale": True, "confidence": "0.9"}, True),
            ({"stale": True, "confidence": "malformed"}, False),
        )
        for metadata, expected in cases:
            with self.subTest(metadata=metadata):
                self.assertEqual(decay_gate.is_decayed(metadata), expected)

    def test_exact_terminal_vocabulary_and_live_cases(self) -> None:
        self.assertEqual(
            decay_gate.TERMINAL_STATUSES,
            frozenset(
                {
                    "closed",
                    "done",
                    "shipped",
                    "retired",
                    "superseded",
                    "complete",
                    "archived",
                    "cancelled",
                    "deprecated",
                    "tested",
                    "failed",
                }
            ),
        )
        self.assertEqual(
            decay_gate.TERMINAL_STATES,
            frozenset({"archived", "deprecated", "cancelled", "retired"}),
        )
        for status in decay_gate.TERMINAL_STATUSES:
            with self.subTest(status=status):
                self.assertFalse(
                    decay_gate.is_live_authority_source(
                        {"status": f" {status.upper()} "}
                    )
                )
        for state in decay_gate.TERMINAL_STATES:
            with self.subTest(state=state):
                self.assertFalse(
                    decay_gate.is_live_authority_source({"state": state.swapcase()})
                )
        for status in ("locked", "published", "evergreen", None):
            with self.subTest(status=status):
                self.assertTrue(
                    decay_gate.is_live_authority_source(
                        {"status": status, "state": "active", "decay": None}
                    )
                )
        self.assertFalse(
            decay_gate.is_live_authority_source(
                {"decay": {"stale": True, "confidence": 0.8}}
            )
        )

    def test_consumers_reexport_the_shared_policy(self) -> None:
        self.assertEqual(tc.DECAY_GATE_CONFIDENCE, 0.8)
        self.assertIs(tc.is_decayed, decay_gate.is_decayed)
        self.assertIs(gardener.TERMINAL_STATUSES, decay_gate.TERMINAL_STATUSES)
        self.assertIs(gardener.TERMINAL_STATES, decay_gate.TERMINAL_STATES)
        self.assertIs(gardener.DEAD_PARENT_STATES, decay_gate.TERMINAL_STATES)

    def test_decay_gate_is_the_sole_policy_owner(self) -> None:
        gate_source = DG_PATH.read_text(encoding="utf-8")
        circle_source = TC_PATH.read_text(encoding="utf-8")
        gardener_source = GARDENER_PATH.read_text(encoding="utf-8")
        self.assertRegex(gate_source, r"(?m)^DECAY_GATE_CONFIDENCE\s*=\s*0\.8$")
        self.assertRegex(gate_source, r"(?m)^TERMINAL_STATUSES\s*=")
        self.assertRegex(gate_source, r"(?m)^TERMINAL_STATES\s*=")
        self.assertNotRegex(circle_source, r"(?m)^DECAY_GATE_CONFIDENCE\s*=")
        self.assertNotRegex(circle_source, r"(?m)^def\s+_?is_decayed\s*\(")
        self.assertNotRegex(gardener_source, r"(?m)^TERMINAL_STATUSES\s*=")
        self.assertNotRegex(gardener_source, r"(?m)^TERMINAL_STATES\s*=")


class AC3DecayGatedRejectsRot(_CircleCase):
    def _fixture(self) -> _CircleFixture:
        fx = _CircleFixture(self.roots)
        fx.node("task0001", TEAM, type_="task")
        fx.node("seedp000", TEAM, type_="note")           # a live seed (ref of task)
        fx.rel("task0001", "seedp000", "refs")

        # In the SEED's neighbourhood: a high-confidence rotten node (excluded),
        # a below-threshold flagged node (kept), and a clean node (kept).
        fx.node("rot00000", TEAM, type_="note", decay=_decay(True, 0.9, "orphaned-by-dead-parent"))
        fx.node("lowconf0", TEAM, type_="note", decay=_decay(True, 0.5, "machine-aged"))
        fx.node("clean000", TEAM, type_="note", decay=_decay(False, 0.0))
        fx.neighbor("seedp000", "rot00000")
        fx.neighbor("seedp000", "lowconf0")
        fx.neighbor("seedp000", "clean000")

        # Boundary cases: exactly AT the threshold (excluded, >=) and just below.
        fx.node("atthresh", TEAM, type_="note", decay=_decay(True, tc.DECAY_GATE_CONFIDENCE))
        fx.node("justbelo", TEAM, type_="note", decay=_decay(True, tc.DECAY_GATE_CONFIDENCE - 0.01))
        fx.neighbor("seedp000", "atthresh")
        fx.neighbor("seedp000", "justbelo")

        # A node reachable ONLY THROUGH the rotten node (a dead edge): must NOT
        # appear — expansion counts only live edges.
        fx.node("beyond00", TEAM, type_="note")
        fx.neighbor("rot00000", "beyond00")
        return fx

    def test_high_confidence_rot_is_excluded(self) -> None:
        fx = self._fixture()
        uids = set(self.draw(fx, "task0001", bob(), 64).value.uids())
        self.assertIn("seedp000", uids)
        self.assertNotIn("rot00000", uids)
        self.assertNotIn("atthresh", uids)  # confidence == threshold -> gated (>=)

    def test_below_threshold_flagged_node_is_kept(self) -> None:
        fx = self._fixture()
        uids = set(self.draw(fx, "task0001", bob(), 64).value.uids())
        self.assertIn("lowconf0", uids)   # stale but low confidence -> kept
        self.assertIn("justbelo", uids)   # just below threshold -> kept
        self.assertIn("clean000", uids)   # not stale -> kept

    def test_expansion_counts_only_live_edges(self) -> None:
        # The node reachable only through the rotten node is not walked to.
        fx = self._fixture()
        uids = set(self.draw(fx, "task0001", bob(), 64).value.uids())
        self.assertNotIn("beyond00", uids)

    def test_rotten_seed_is_gated_at_the_seed_layer_too(self) -> None:
        # A directly-referenced rotten node (a SEED, not just a hop) is excluded;
        # a below-threshold direct ref is kept.
        fx = _CircleFixture(self.roots)
        fx.node("task0001", TEAM, type_="task")
        fx.node("rotref00", TEAM, type_="note", decay=_decay(True, 0.95))
        fx.node("liveref0", TEAM, type_="note", decay=_decay(True, 0.3))
        fx.rel("task0001", "rotref00", "refs")
        fx.rel("task0001", "liveref0", "refs")
        seed_uids = {m.uid for m in self.seeds(fx, "task0001", bob()).value}
        self.assertNotIn("rotref00", seed_uids)
        self.assertIn("liveref0", seed_uids)


# =========================================================================== #
# AC4 — DETERMINISTIC + BUDGET-BOUNDED                                        #
# =========================================================================== #
class AC4DeterministicAndBudgetBounded(_CircleCase):
    def _fixture(self) -> _CircleFixture:
        """A task seeding into a cyclic team subgraph."""

        fx = _CircleFixture(self.roots)
        fx.node("task0001", TEAM, type_="task")
        for uid in ("aaa00000", "bbb00000", "ccc00000"):
            fx.node(uid, TEAM, type_="note")
        fx.rel("task0001", "aaa00000", "refs")
        # a cycle a -> b -> c -> a (visited-set must terminate it)
        fx.neighbor("aaa00000", "bbb00000")
        fx.neighbor("bbb00000", "ccc00000")
        fx.neighbor("ccc00000", "aaa00000")
        return fx

    def test_identical_circle_across_runs(self) -> None:
        fx = self._fixture()
        a = self.draw(fx, "task0001", bob(), 64).value
        b = self.draw(fx, "task0001", bob(), 64).value
        self.assertEqual(a.canonical(), b.canonical())

    def test_stable_ordering_by_distance_then_uid(self) -> None:
        fx = self._fixture()
        members = self.draw(fx, "task0001", bob(), 64).value.members
        keys = [(m.distance, m.uid) for m in members]
        self.assertEqual(keys, sorted(keys))

    def test_budget_bounds_size(self) -> None:
        fx = self._fixture()
        self.assertEqual(len(self.draw(fx, "task0001", bob(), 0).value.members), 0)
        self.assertLessEqual(len(self.draw(fx, "task0001", bob(), 1).value.members), 1)
        self.assertLessEqual(len(self.draw(fx, "task0001", bob(), 2).value.members), 2)
        # With ample budget the whole reachable live domain is drawn.
        full = self.draw(fx, "task0001", bob(), 64).value
        self.assertEqual(set(full.uids()), {"aaa00000", "bbb00000", "ccc00000"})

    def test_cycle_visits_each_node_once(self) -> None:
        fx = self._fixture()
        uids = self.draw(fx, "task0001", bob(), 64).value.uids()
        self.assertEqual(len(uids), len(set(uids)))

    def test_budget_prefix_is_consistent_with_fuller_circle(self) -> None:
        # A smaller-budget circle is a prefix of a larger one (stable order).
        fx = self._fixture()
        small = self.draw(fx, "task0001", bob(), 1).value.uids()
        large = self.draw(fx, "task0001", bob(), 64).value.uids()
        self.assertEqual(large[: len(small)], small)

    def test_invalid_budget_refuses(self) -> None:
        fx = self._fixture()
        for bad in (-1, "3", 3.0, True):
            result = self.draw(fx, "task0001", bob(), bad)
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, GraphErrorCode.BUDGET_INVALID)


# =========================================================================== #
# AC5 — AUDITABLE PROVENANCE                                                   #
# =========================================================================== #
class AC5AuditableProvenance(_CircleCase):
    def _fixture(self) -> _CircleFixture:
        fx = _CircleFixture(self.roots)
        fx.node("task0001", TEAM, type_="task")
        fx.node("ref00001", TEAM, type_="note")
        fx.node("gov00000", TEAM, type_="capsule")
        fx.node("hopnode0", TEAM, type_="note")   # reached by expansion from the ref
        fx.rel("task0001", "ref00001", "refs")
        fx.rel("task0001", "gov00000", "governed_by")
        fx.neighbor("ref00001", "hopnode0")
        return fx

    def test_every_member_carries_a_uid_citing_reason(self) -> None:
        fx = self._fixture()
        circle = self.draw(fx, "task0001", bob(), 64).value
        self.assertTrue(circle.members)
        known = set(circle.uids()) | {"task0001"}
        for member in circle.members:
            self.assertTrue(member.provenance)
            self.assertIn(":", member.provenance)
            self.assertIn(member.via, known)  # provenance cites a real UID

    def test_specific_relations_are_correct(self) -> None:
        fx = self._fixture()
        circle = self.draw(fx, "task0001", bob(), 64).value
        self.assertEqual(circle.reason("ref00001"), f"{tc.REL_REF}:task0001")
        self.assertEqual(circle.reason("gov00000"), f"{tc.REL_GOVERNED_BY}:task0001")
        # hopnode0 was admitted by expansion FROM the ref seed — it cites it.
        self.assertEqual(circle.reason("hopnode0"), f"{tc.REL_WALK_HOP}:ref00001")

    def test_circle_is_inspectable(self) -> None:
        fx = self._fixture()
        circle = self.draw(fx, "task0001", bob(), 64).value
        self.assertIsInstance(circle, Circle)
        self.assertEqual(circle.task_uid, "task0001")
        self.assertIsNone(circle.reason("not-in-circle"))
        # canonical() is a stable, re-parseable audit surface.
        import json

        parsed = json.loads(circle.canonical())
        self.assertEqual(parsed["task"], "task0001")
        self.assertEqual(len(parsed["members"]), len(circle.members))


class OrientReferenceObservationAdmissionTests(_CircleCase):
    def test_edge_only_target_never_consumes_budget_or_extends_traversal(self):
        fx = _CircleFixture(self.roots)
        fx.node("task0001", TEAM, type_="task")
        fx.node("ffff0001", TEAM, type_="note")
        fx.node("beyond01", TEAM, type_="note")
        fx.edge_only("00000001", TEAM)
        fx.rel("task0001", "00000001", "refs")
        fx.rel("task0001", "ffff0001", "refs")
        fx.neighbor("00000001", "beyond01")

        projection = fx.projection()
        direct = projection.adjacency("task0001", bob())
        self.assertTrue(direct.ok, msg=direct.error)
        # Negative control: an unpartitioned budget-1 implementation takes the
        # lexically first edge endpoint and loses the real indexed member.
        unpartitioned_mutant = tuple(sorted(direct.value)[:1])
        self.assertEqual(unpartitioned_mutant, ("00000001",))

        result = draw_circle(
            "task0001", bob(), 1, projection=projection, index=fx.index()
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(result.value.uids(), ("ffff0001",))
        self.assertNotIn("00000001", result.value.uids())
        self.assertNotIn("beyond01", result.value.uids())
        self.assertEqual(
            tuple(item.raw_target for item in result.value.reference_observations),
            ("00000001",),
        )

        edge_adjacency = projection.adjacency("00000001", bob())
        self.assertTrue(edge_adjacency.ok, msg=edge_adjacency.error)
        self.assertIn(
            "beyond01",
            edge_adjacency.value,
            msg="CONTROL: the edge-only endpoint must genuinely lead onward",
        )

    def test_observations_are_classified_and_created_only_after_visibility(self):
        fx = _CircleFixture(self.roots)
        fx.node("task0001", TEAM, type_="task")
        fx.edge_only("deadbeef", TEAM)
        fx.edge_only("<script>alert(1)</script>", TEAM)
        fx.edge_only("facefeed", PRIV_ALICE)
        for target in ("deadbeef", "<script>alert(1)</script>", "facefeed"):
            fx.rel("task0001", target, "refs")

        result = self.draw(fx, "task0001", bob(), 8)
        self.assertTrue(result.ok, msg=result.error)
        observations = {
            item.raw_target: item for item in result.value.reference_observations
        }
        self.assertEqual(set(observations), {"deadbeef", "<script>alert(1)</script>"})
        self.assertEqual(
            observations["deadbeef"].classification,
            tc.REFERENCE_MISSING_INDEX_ENTRY,
        )
        self.assertEqual(
            observations["<script>alert(1)</script>"].classification,
            tc.REFERENCE_NON_UID_OR_INVALID,
        )
        for observation in observations.values():
            self.assertEqual(observation.via, "task0001")
            self.assertEqual(observation.relation, tc.REL_REF)
            self.assertEqual(observation.distance, 1)
        self.assertNotIn("facefeed", repr(result.value.reference_observations))


class Cut4AOptionalQuerySeeds(_CircleCase):
    SNAPSHOT = "snapshot-circle-1"

    def bound_seeds(self, viewer, uids, *, as_of=SNAPSHOT):
        # This legacy suite loads viewer_projection under an alternate module
        # name. Build the frozen production seed value with that exact Viewer
        # instance so the test exercises equality at the real seam.
        seeds = object.__new__(tc.PrevalidatedQuerySeeds)
        object.__setattr__(seeds, "viewer", viewer)
        object.__setattr__(seeds, "index_as_of", as_of)
        object.__setattr__(seeds, "uids", tuple(sorted(set(uids))))
        object.__setattr__(seeds, "fallback_used", False)
        return seeds

    def fixture(self):
        fx = _CircleFixture(self.roots)
        fx.node("task0001", TEAM, type_="task")
        fx.node("struct01", TEAM, type_="note")
        fx.node("query001", TEAM, type_="note")
        fx.node("queryhop", TEAM, type_="note")
        fx.node("hidden01", PRIV_ALICE, type_="note")
        fx.rel("task0001", "struct01", "refs")
        fx.neighbor("query001", "queryhop")
        return fx

    def index(self, fx):
        return InMemoryStructuralIndex(
            fx._structures, index_as_of=self.SNAPSHOT
        )

    def test_visible_query_seed_enters_with_provenance_and_expands_via_projection(self):
        fx = self.fixture()
        viewer = bob()
        result = draw_circle(
            "task0001",
            viewer,
            16,
            projection=fx.projection(),
            index=self.index(fx),
            query_seeds=self.bound_seeds(viewer, ("query001",)),
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(
            result.value.reason("query001"), f"{tc.REL_QUERY_SEED}:task0001"
        )
        self.assertEqual(
            result.value.reason("queryhop"), f"{tc.REL_WALK_HOP}:query001"
        )

    def test_structural_reason_wins_and_hidden_query_seed_is_defensively_filtered(self):
        fx = self.fixture()
        viewer = bob()
        result = draw_circle(
            "task0001",
            viewer,
            16,
            projection=fx.projection(),
            index=self.index(fx),
            query_seeds=self.bound_seeds(
                viewer, ("struct01", "hidden01")
            ),
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(
            result.value.reason("struct01"), f"{tc.REL_REF}:task0001"
        )
        self.assertNotIn("hidden01", result.value.uids())

    def test_forged_viewer_and_snapshot_bindings_refuse(self):
        fx = self.fixture()
        for seeds in (
            self.bound_seeds(alice(), ("query001",)),
            self.bound_seeds(bob(), ("query001",), as_of="other"),
        ):
            with self.subTest(seeds=seeds):
                result = draw_circle(
                    "task0001",
                    bob(),
                    16,
                    projection=fx.projection(),
                    index=self.index(fx),
                    query_seeds=seeds,
                )
                self.assertFalse(result.ok)
                self.assertEqual(
                    result.error.code, tc.QueryErrorCode.BINDING_MISMATCH
                )

    def test_absent_query_seeds_retain_exact_no_seed_canonical(self):
        fx = self.fixture()
        kwargs = {
            "projection": fx.projection(),
            "index": self.index(fx),
        }
        implicit = draw_circle("task0001", bob(), 16, **kwargs)
        explicit = draw_circle(
            "task0001", bob(), 16, query_seeds=None, **kwargs
        )
        self.assertTrue(implicit.ok and explicit.ok)
        self.assertEqual(implicit.value.canonical(), explicit.value.canonical())


# =========================================================================== #
# AC6 — NO RANKING / NO DISTILL / NO MODEL (structural review)                #
# =========================================================================== #
class AC6NoRankingNoDistillNoModel(_CircleCase):
    def setUp(self) -> None:
        super().setUp()
        self.source = TC_PATH.read_text(encoding="utf-8")

    def test_expansion_routes_through_viewer_projection(self) -> None:
        self.assertIn("from lib.viewer_projection import", self.source)
        self.assertIn(".adjacency(", self.source)

    def test_no_independent_neighbor_or_visibility_filtering(self) -> None:
        # The module never reads a raw graph edge for a neighbour/visibility
        # decision (no .neighbors(), no .inbound_sources()) and never derives a
        # segment itself — those all belong to viewer_projection.
        self.assertNotIn(".neighbors(", self.source)
        self.assertNotIn(".inbound_sources(", self.source)
        self.assertNotIn("derive_segment", self.source)
        for pattern in ('get("segment"', "get('segment'", '["segment"]', "['segment']"):
            self.assertNotIn(pattern, self.source)

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

    def test_no_score_rank_or_chunk_fields(self) -> None:
        # Membership + provenance only: the auditable structures carry no
        # relevance score / rank / weight and no distilled-chunk field.
        member_fields = {f.name for f in CircleMember.__dataclass_fields__.values()}
        circle_fields = {f.name for f in Circle.__dataclass_fields__.values()}
        self.assertEqual(member_fields, {"uid", "distance", "relation", "via"})
        self.assertEqual(
            circle_fields, {"task_uid", "members", "reference_observations"}
        )
        forbidden = {"score", "rank", "weight", "relevance", "chunk", "chunks", "distilled"}
        self.assertEqual(member_fields & forbidden, set())
        self.assertEqual(circle_fields & forbidden, set())

    def test_no_distill_or_ranker_surface_is_defined(self) -> None:
        # No distillation function and no relevance-ranker are defined here —
        # those cuts are explicitly deferred (e12ff178 §Explicit exclusions).
        self.assertIsNone(re.search(r"^def\s+distill", self.source, re.M))
        self.assertIsNone(re.search(r"^def\s+\w*rank\w*", self.source, re.M))
        self.assertIsNone(re.search(r"^\s+def\s+distill", self.source, re.M))


if __name__ == "__main__":
    unittest.main()
