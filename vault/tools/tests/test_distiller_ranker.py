#!/usr/bin/env python3
"""Executable contract for the distiller's deterministic weighted ranker.

Pairs dev-spec ``1230fa5d`` (activation ``9b0888c4``) and test-spec ``e380cfb0``
(cycle brief ``6da0d037`` §9 decision 3; ranks the circle ``e12ff178`` over the
viewer-relative walk ``5043b274``). One test class per dev-spec acceptance
criterion (1-based), exercising ``rank_circle`` against a SANDBOXED fixture
circle (segment-tagged, typed, state- and decay-tagged members + a fixture B4a
authority) so the layer / state / decay-gated-connectivity / task-tilt behaviours
are provable WITHOUT the live corpus and independent of the live Studio's cutover
state.

Coverage -> acceptance-criterion map (test-spec §Coverage):

* AC1 LAYER FEATURE — capsule/ADR > work entry > event/memory (all else equal)
* AC2 STATE + DECAY-GATED CONNECTIVITY — the dead-incumbent plant + lifecycle state
* AC3 TASK-TILT — status-task vs design-task reorder the SAME circle
* AC4 WEIGHTED SUM + DETERMINISTIC — identical across runs; stable UID tiebreak
* AC5 INSPECTABLE / GOVERNED — breakdown · effective-weights == score
* AC6 VIEWER-SAFE + NO MODEL / NO DISTILL / NO LEARNED WEIGHTS — structural review

The fixture reuses ``test_task_circle.py`` / ``test_viewer_projection.py``'s
approach verbatim: temp vault-roots whose manifest UID == segment UID so
``derive_segment`` yields the segment (segment is NEVER a hand field), and a
pinned B4a resolver synthesised from an injected group corpus. Authority (the
connectivity feature) is planted as real directed inbound edges so
``ViewerProjection.authority`` — the segment-local, decay-gated count the ranker
REUSES — is what actually decides connectivity, and the DEAD-INCUMBENT plant is
verifiably honest: the loser has strictly MORE raw inbound edges than the winner,
so a naive raw-count ranker would get it wrong and the decay-gated ranker gets it
right.
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
DR_PATH = TOOLS / "lib" / "distiller_ranker.py"
vp = _load("viewer_projection_under_test", VP_PATH)
tc = _load("task_circle_under_test", TC_PATH)
dr = _load("distiller_ranker_under_test", DR_PATH)

from lib.group_contract import (  # noqa: E402
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

Circle = tc.Circle
CircleMember = tc.CircleMember

rank_circle = dr.rank_circle
InMemoryRankIndex = dr.InMemoryRankIndex
DEFAULT_WEIGHTS = dr.DEFAULT_WEIGHTS
Weights = dr.Weights
FEATURE_NAMES = dr.FEATURE_NAMES


# --------------------------------------------------------------------------- #
# Principals + segment UIDs (all 8-hex; segment UIDs double as manifest UIDs).  #
# --------------------------------------------------------------------------- #
ALICE = "a1a1a1a1"
BOB = "b2b2b2b2"

TEAM = "7ea70001"        # the shared team/vault segment (alice + bob)
OTHER = "7ea70002"       # a DIFFERENT team segment (cross-segment dead edges)
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
# (Copied from test_viewer_projection.py / test_task_circle.py so segment is    #
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


class _RankFixture:
    """Plants a segment-tagged graph (members + inbound "voters" for authority)
    and a matched rank index (per-member type/status/state/decay), then emits a
    (ViewerProjection, InMemoryRankIndex) pair over ONE graph and constructs the
    Circle to be ranked.

    ``member`` registers a ranked circle member (graph node + index record).
    ``authority_from`` plants ``n`` distinct inbound voter edges into a target
    from sources in a given segment — so ``authority(target)`` (segment-local)
    counts only the voters whose segment matches the target's, while the raw
    inbound count includes them all. ``set_task`` registers the task's index
    record (its ``type`` drives the tilt; the task is not itself ranked).
    """

    def __init__(self, roots: _RootFactory) -> None:
        self._roots = roots
        self._records: dict = {}      # graph records (for derive_segment)
        self._node_root: dict = {}
        self._edges: list = []
        self._index: dict = {}        # rank-index records (type/status/state/decay)

    def _reg_graph(self, uid: str, segment_uid: str) -> None:
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

    def member(
        self,
        uid: str,
        segment_uid: str = TEAM,
        *,
        type_: str = "note",
        status=None,
        state=None,
        decay=None,
    ) -> str:
        self._reg_graph(uid, segment_uid)
        self._index[uid] = {
            "type": type_,
            "status": status,
            "state": state,
            "decay": decay,
        }
        return uid

    def authority_from(self, target: str, segment_uid: str, n: int) -> list:
        """Plant ``n`` distinct inbound edges into ``target`` from voter nodes in
        ``segment_uid``. Voters in the target's OWN segment count toward
        ``authority``; voters in any other segment are raw inbound edges that do
        NOT count (the segment-local / decay-gated law)."""

        voters = []
        for i in range(n):
            voter = f"v_{segment_uid}_{target}_{i}"
            self._reg_graph(voter, segment_uid)
            self._edges.append((voter, target))  # directed INTO target
            voters.append(voter)
        return voters

    def set_task(self, uid: str, type_: str) -> str:
        self._index[uid] = {"type": type_, "status": None, "state": None, "decay": None}
        return uid

    def projection(self) -> ViewerProjection:
        graph = InMemoryGraphSource(self._edges, self._records, self._node_root)
        return ViewerProjection.from_resolver(graph, base_resolver())

    def rank_index(self) -> InMemoryRankIndex:
        return InMemoryRankIndex(self._index)

    def circle(self, task_uid: str, *member_uids: str) -> Circle:
        members = tuple(
            CircleMember(uid=uid, distance=1, relation=tc.REL_NEIGHBOR, via=task_uid)
            for uid in member_uids
        )
        return Circle(task_uid=task_uid, members=members)

    def circle_by_relation(self, task_uid: str, *pairs) -> Circle:
        """A circle whose members carry SPECIFIED inclusion relations.

        ``pairs`` are ``(uid, relation)``. The plain :meth:`circle` helper pins
        every member to one relation, which cannot exercise the relation feature
        at all — a suite built only on it would score every member identically
        on relation and prove nothing about the tiers.
        """

        members = tuple(
            CircleMember(uid=uid, distance=1, relation=relation, via=task_uid)
            for uid, relation in pairs
        )
        return Circle(task_uid=task_uid, members=members)


def viewer() -> Viewer:
    return Viewer(principal_uid=BOB, private_segment_uid=PRIV_BOB)


def _decay(stale: bool, confidence: float, *signals) -> dict:
    return {
        "stale": stale,
        "signals": list(signals),
        "reason": "planted",
        "confidence": confidence,
        "swept": "2026-07-22",
    }


class _RankCase(unittest.TestCase):
    def setUp(self) -> None:
        self.roots = _RootFactory()
        self.addCleanup(self.roots.cleanup)

    def rank(self, fx: _RankFixture, circle, task_uid, weights=DEFAULT_WEIGHTS):
        return rank_circle(
            circle,
            task_uid,
            viewer(),
            weights,
            projection=fx.projection(),
            index=fx.rank_index(),
        )

    def ranked(self, fx: _RankFixture, circle, task_uid, weights=DEFAULT_WEIGHTS):
        """Rank and unwrap, asserting success first."""

        result = self.rank(fx, circle, task_uid, weights)
        self.assertTrue(result.ok, msg=result.error)
        return result.value


# =========================================================================== #
# AC1 — LAYER FEATURE (prior-model, type-tiered, deterministic; no model)     #
# =========================================================================== #
class AC1LayerFeature(_RankCase):
    def _fixture(self):
        fx = _RankFixture(self.roots)
        # All else equal: same status, same authority (1 live voter each -> the
        # connectivity feature is equal), no decay. Only TYPE differs.
        cap = fx.member("cap00000", type_="capsule", status="active")
        work = fx.member("wrk00000", type_="note", status="active")
        event = fx.member("evt00000", type_="memory", status="active")
        for uid in (cap, work, event):
            fx.authority_from(uid, TEAM, 1)
        task = fx.set_task("task0001", "note")  # neutral task type -> no tilt
        return fx, task, (cap, work, event)

    def test_capsule_outranks_work_outranks_event(self) -> None:
        fx, task, (cap, work, event) = self._fixture()
        ranked = self.ranked(fx, fx.circle(task, work, event, cap), task)
        self.assertEqual(ranked.uids(), (cap, work, event))
        self.assertGreater(ranked.score(cap), ranked.score(work))
        self.assertGreater(ranked.score(work), ranked.score(event))

    def test_layer_tier_map_is_a_named_documented_prior(self) -> None:
        # The tiers are a named constant, ordered governance > work > event.
        self.assertGreater(dr.LAYER_TIER_GOVERNANCE, dr.LAYER_TIER_WORK)
        self.assertGreater(dr.LAYER_TIER_WORK, dr.LAYER_TIER_EVENT)
        # ADRs (decisions), arch-specs, playbooks sit in the top tier with capsules.
        for gov in ("capsule", "decision", "arch-spec", "playbook"):
            self.assertEqual(dr.layer_score(gov), dr.LAYER_TIER_GOVERNANCE)
        for work in ("task", "design-brief", "note", "document", "project"):
            self.assertEqual(dr.layer_score(work), dr.LAYER_TIER_WORK)
        for event in ("memory", "event", "pipeline-run", "board-snapshot"):
            self.assertEqual(dr.layer_score(event), dr.LAYER_TIER_EVENT)

    def test_adr_outranks_work_entry_all_else_equal(self) -> None:
        fx = _RankFixture(self.roots)
        adr = fx.member("adr00000", type_="decision", status="active")
        brief = fx.member("brf00000", type_="design-brief", status="active")
        for uid in (adr, brief):
            fx.authority_from(uid, TEAM, 2)
        task = fx.set_task("task0001", "collection")  # neutral -> no tilt
        ranked = self.ranked(fx, fx.circle(task, brief, adr), task)
        self.assertEqual(ranked.uids()[0], adr)


# =========================================================================== #
# AC2 — STATE + DECAY-GATED CONNECTIVITY (the dead-incumbent plant)           #
# =========================================================================== #
class AC2StateAndDecayGatedConnectivity(_RankCase):
    def _dead_incumbent_fixture(self):
        """The DEAD-INCUMBENT plant. Both members are identical in type / state /
        decay; only their inbound edge topology differs.

        * ``incumbent`` — 1 LIVE (same-segment) inbound + 6 DEAD (cross-segment)
          inbound  => raw inbound 7, segment-local authority 1.
        * ``winner``    — 3 LIVE (same-segment) inbound                => raw
          inbound 3, segment-local authority 3.

        A naive raw-count ranker ranks the incumbent first (7 > 3) — WRONG. The
        decay-gated ranker ranks the winner first (authority 3 > 1) — RIGHT.
        """

        fx = _RankFixture(self.roots)
        incumbent = fx.member("incumb00", TEAM, type_="note", status="active")
        winner = fx.member("winner00", TEAM, type_="note", status="active")
        fx.authority_from(incumbent, TEAM, 1)     # 1 live edge
        fx.authority_from(incumbent, OTHER, 4)    # 4 cross-segment dead edges
        fx.authority_from(incumbent, OS, 2)       # 2 more cross-segment dead edges
        fx.authority_from(winner, TEAM, 3)        # 3 live edges
        task = fx.set_task("task0001", "note")    # neutral task -> no tilt
        return fx, task, incumbent, winner

    def test_fixture_is_honest_incumbent_has_more_raw_edges(self) -> None:
        # HONESTY GATE: the loser genuinely has MORE raw inbound edges than the
        # winner, and its segment-local authority is genuinely LOWER.
        fx, _task, incumbent, winner = self._dead_incumbent_fixture()
        graph = fx.projection()._graph
        raw_incumbent = len(graph.inbound_sources(incumbent))
        raw_winner = len(graph.inbound_sources(winner))
        self.assertEqual(raw_incumbent, 7)
        self.assertEqual(raw_winner, 3)
        self.assertGreater(raw_incumbent, raw_winner)  # naive raw-count -> incumbent
        auth_incumbent = fx.projection().authority(incumbent).value
        auth_winner = fx.projection().authority(winner).value
        self.assertEqual(auth_incumbent, 1)
        self.assertEqual(auth_winner, 3)
        self.assertLess(auth_incumbent, auth_winner)   # decay-gated -> winner

    def test_dead_incumbent_ranks_below_fewer_live_edge_node(self) -> None:
        fx, task, incumbent, winner = self._dead_incumbent_fixture()
        ranked = self.ranked(fx, fx.circle(task, incumbent, winner), task)
        self.assertEqual(ranked.uids(), (winner, incumbent))
        self.assertGreater(ranked.score(winner), ranked.score(incumbent))
        # It is the CONNECTIVITY feature that separates them (all else equal).
        w = ranked.member(winner).breakdown
        i = ranked.member(incumbent).breakdown
        self.assertEqual((w.layer, w.state, w.decay), (i.layer, i.state, i.decay))
        self.assertGreater(w.connectivity, i.connectivity)

    def test_lifecycle_state_weighting(self) -> None:
        # State feature: active up-weighted, archived down-weighted (all else
        # equal: same type, same authority, no decay).
        fx = _RankFixture(self.roots)
        live = fx.member("live0000", type_="note", status="active", state="active")
        dead = fx.member("dead0000", type_="note", status="archived", state="active")
        for uid in (live, dead):
            fx.authority_from(uid, TEAM, 2)
        task = fx.set_task("task0001", "note")
        ranked = self.ranked(fx, fx.circle(task, dead, live), task)
        self.assertEqual(ranked.uids(), (live, dead))
        self.assertGreater(ranked.score(live), ranked.score(dead))

    def test_state_score_map_direction(self) -> None:
        # Up-weighted lifecycle states outscore down-weighted ones.
        for up in ("active", "locked", "current", "shipped", "published"):
            for down in ("superseded", "archived", "rejected", "cancelled", "deprecated"):
                self.assertGreater(
                    dr.state_score(up, None), dr.state_score(down, None),
                    msg=f"{up} should outscore {down}",
                )

    def test_state_contradiction_takes_the_conservative_minimum(self) -> None:
        # status says active, state says archived -> scored on the down value.
        contradicted = dr.state_score("active", "archived")
        self.assertEqual(contradicted, dr.state_score("archived", "archived"))


# =========================================================================== #
# AC3 — TASK-TILT (tunable, not a fixed order)                                #
# =========================================================================== #
class AC3TaskTilt(_RankCase):
    def _fixture(self):
        """A high-layer/low-state member vs a low-layer/high-state member, with
        equal connectivity and no decay — so the WINNER depends purely on whether
        the tilt up-weights layer or state."""

        fx = _RankFixture(self.roots)
        # A: capsule (top layer) but archived (bottom state).
        a = fx.member("aaa00000", type_="capsule", status="archived", state="active")
        # B: memory (bottom layer) but active (top state).
        b = fx.member("bbb00000", type_="memory", status="active", state="active")
        for uid in (a, b):
            fx.authority_from(uid, TEAM, 1)  # equal connectivity
        return fx, a, b

    def test_design_task_up_weights_layer_A_wins(self) -> None:
        fx, a, b = self._fixture()
        task = fx.set_task("dsgn0001", "design-brief")
        ranked = self.ranked(fx, fx.circle(task, a, b), task)
        self.assertEqual(ranked.tilt, dr.TILT_LAYER)
        self.assertEqual(ranked.weights.layer, DEFAULT_WEIGHTS.layer + dr.TILT_DELTA)
        self.assertEqual(ranked.weights.state, DEFAULT_WEIGHTS.state)
        self.assertEqual(ranked.uids()[0], a)

    def test_status_task_up_weights_state_B_wins(self) -> None:
        fx, a, b = self._fixture()
        task = fx.set_task("task0001", "task")
        ranked = self.ranked(fx, fx.circle(task, a, b), task)
        self.assertEqual(ranked.tilt, dr.TILT_STATE)
        self.assertEqual(ranked.weights.state, DEFAULT_WEIGHTS.state + dr.TILT_DELTA)
        self.assertEqual(ranked.weights.layer, DEFAULT_WEIGHTS.layer)
        self.assertEqual(ranked.uids()[0], b)

    def test_same_circle_two_task_types_reorder(self) -> None:
        fx, a, b = self._fixture()
        design = self.ranked(fx, fx.circle("d", a, b), fx.set_task("d", "design-spec"))
        status = self.ranked(fx, fx.circle("s", a, b), fx.set_task("s", "task"))
        self.assertNotEqual(design.uids(), status.uids())
        self.assertEqual(design.uids(), (a, b))
        self.assertEqual(status.uids(), (b, a))

    def test_neutral_task_type_leaves_default_profile(self) -> None:
        fx, a, b = self._fixture()
        task = fx.set_task("proj0001", "project")  # neither tilt set
        ranked = self.ranked(fx, fx.circle(task, a, b), task)
        self.assertEqual(ranked.tilt, dr.TILT_NONE)
        self.assertEqual(ranked.weights, DEFAULT_WEIGHTS)


# =========================================================================== #
# AC4 — WEIGHTED SUM + DETERMINISTIC                                          #
# =========================================================================== #
class AC4WeightedSumDeterministic(_RankCase):
    def _mixed_fixture(self):
        fx = _RankFixture(self.roots)
        fx.member("mmm00001", type_="capsule", status="active")
        fx.member("mmm00002", type_="note", status="draft")
        fx.member("mmm00003", type_="memory", status="archived",
                  decay=_decay(True, 0.4, "machine-aged"))
        fx.authority_from("mmm00001", TEAM, 3)
        fx.authority_from("mmm00002", TEAM, 1)
        fx.authority_from("mmm00003", TEAM, 2)
        task = fx.set_task("task0001", "note")
        return fx, task, ("mmm00001", "mmm00002", "mmm00003")

    def test_identical_ranking_across_runs(self) -> None:
        fx, task, uids = self._mixed_fixture()
        a = self.rank(fx, fx.circle(task, *uids), task).value
        b = self.rank(fx, fx.circle(task, *uids), task).value
        self.assertEqual(a.canonical(), b.canonical())

    def test_order_is_score_descending(self) -> None:
        fx, task, uids = self._mixed_fixture()
        ranked = self.rank(fx, fx.circle(task, *uids), task).value
        scores = [m.score for m in ranked.members]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_stable_uid_tiebreak_on_exact_ties(self) -> None:
        # Two members IDENTICAL in every feature (type/state/authority/decay) tie
        # on score; the tiebreak is ascending UID, deterministically.
        fx = _RankFixture(self.roots)
        hi = fx.member("zzzz0001", type_="note", status="active")
        lo = fx.member("aaaa0001", type_="note", status="active")
        for uid in (hi, lo):
            fx.authority_from(uid, TEAM, 2)
        task = fx.set_task("task0001", "note")
        ranked = self.rank(fx, fx.circle(task, hi, lo), task).value
        self.assertEqual(ranked.score(hi), ranked.score(lo))     # a genuine tie
        self.assertEqual(ranked.uids(), ("aaaa0001", "zzzz0001"))  # UID-ascending

    def test_no_wallclock_or_nondeterminism_in_source(self) -> None:
        source = DR_PATH.read_text(encoding="utf-8")
        for banned in ("time.time", "datetime.now", "random.", "uuid", "monotonic"):
            self.assertNotIn(banned, source)

    def test_authority_failure_fails_closed(self) -> None:
        # A member absent from the graph cannot resolve authority -> typed refusal
        # propagates (never a permissive default rank).
        fx = _RankFixture(self.roots)
        fx.member("present0", type_="note", status="active")
        fx.authority_from("present0", TEAM, 1)
        task = fx.set_task("task0001", "note")
        circle = fx.circle(task, "present0", "absent00")  # absent00 has no node
        result = self.rank(fx, circle, task)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, vp.GraphErrorCode.NODE_NOT_FOUND)


# =========================================================================== #
# AC5 — INSPECTABLE / GOVERNED (not a black box)                              #
# =========================================================================== #
class AC5InspectableGoverned(_RankCase):
    def _fixture(self):
        fx = _RankFixture(self.roots)
        fx.member("iii00001", type_="capsule", status="locked")
        fx.member("iii00002", type_="task", status="active", state="active")
        fx.member("iii00003", type_="memory", status="retired",
                  decay=_decay(True, 0.55, "machine-aged"))
        fx.authority_from("iii00001", TEAM, 2)
        fx.authority_from("iii00001", OS, 3)   # cross-segment: raw only, not authority
        fx.authority_from("iii00002", TEAM, 4)
        fx.authority_from("iii00003", TEAM, 1)
        task = fx.set_task("dsgn0001", "design-brief")  # a real tilt is applied
        return fx, task, ("iii00001", "iii00002", "iii00003")

    def test_breakdown_dot_effective_weights_reconstructs_score(self) -> None:
        fx, task, uids = self._fixture()
        ranked = self.rank(fx, fx.circle(task, *uids), task).value
        weights = ranked.weights  # the EFFECTIVE (post-tilt) weights, emitted
        for member in ranked.members:
            reconstructed = sum(
                getattr(weights, name) * getattr(member.breakdown, name)
                for name in FEATURE_NAMES
            )
            self.assertAlmostEqual(reconstructed, member.score, places=12)

    def test_contributions_sum_to_score(self) -> None:
        fx, task, uids = self._fixture()
        ranked = self.rank(fx, fx.circle(task, *uids), task).value
        for member in ranked.members:
            self.assertAlmostEqual(
                sum(member.contributions.values()), member.score, places=12
            )
            # Each contribution is weight · feature — the "why it ranked" line.
            for name in FEATURE_NAMES:
                self.assertAlmostEqual(
                    member.contributions[name],
                    getattr(ranked.weights, name) * getattr(member.breakdown, name),
                    places=12,
                )

    def test_effective_weights_are_emitted_and_tunable(self) -> None:
        fx, task, uids = self._fixture()
        ranked = self.rank(fx, fx.circle(task, *uids), task).value
        self.assertIsInstance(ranked.weights, Weights)
        self.assertEqual(ranked.tilt, dr.TILT_LAYER)
        # A custom weight profile is honoured (weights are tunable, not baked in).
        # This fixture's task is a design task, so the LAYER tilt applies on top.
        # relation=0.0 is the deliberate "disable this feature" profile — proof
        # the fifth feature is tunable like the other four, not baked in.
        custom_base = Weights(
            layer=0.1, state=0.9, connectivity=0.0, decay=0.0, relation=0.0
        )
        custom = self.rank(fx, fx.circle(task, *uids), task, weights=custom_base).value
        self.assertEqual(custom.weights.layer, 0.1 + dr.TILT_DELTA)  # tilt still applies
        self.assertEqual(custom.weights.state, 0.9)                  # untilted feature intact
        self.assertEqual(custom.weights.relation, 0.0)               # carried through the tilt
        self.assertNotEqual(custom.canonical(), ranked.canonical())

    def test_connectivity_uses_segment_local_authority_not_raw_count(self) -> None:
        # iii00001 has 5 raw inbound (2 team + 3 os) but authority 2; iii00002 has
        # authority 4. Normalised WITHIN the circle: 00002 is the max (1.0).
        fx, task, uids = self._fixture()
        ranked = self.rank(fx, fx.circle(task, *uids), task).value
        self.assertEqual(ranked.member("iii00002").breakdown.connectivity, 1.0)
        self.assertAlmostEqual(
            ranked.member("iii00001").breakdown.connectivity, 2 / 4
        )

    def test_canonical_is_stable_and_reparseable(self) -> None:
        import json

        fx, task, uids = self._fixture()
        ranked = self.rank(fx, fx.circle(task, *uids), task).value
        parsed = json.loads(ranked.canonical())
        self.assertEqual(parsed["task"], task)
        self.assertEqual(len(parsed["members"]), len(uids))
        self.assertEqual(set(parsed["weights"]), set(FEATURE_NAMES))
        for m in parsed["members"]:
            self.assertEqual(set(m["breakdown"]), set(FEATURE_NAMES))
            self.assertEqual(set(m["contributions"]), set(FEATURE_NAMES))


# =========================================================================== #
# AC6 — VIEWER-SAFE + NO MODEL / NO DISTILL / NO LEARNED WEIGHTS              #
# =========================================================================== #
class AC6ViewerSafeNoModelNoDistillNoLearnedWeights(_RankCase):
    def setUp(self) -> None:
        super().setUp()
        self.source = DR_PATH.read_text(encoding="utf-8")

    def test_connectivity_via_projection_authority(self) -> None:
        self.assertIn("from lib.viewer_projection import", self.source)
        self.assertIn(".authority(", self.source)

    def test_does_not_compute_its_own_inbound_count_or_re_cross_boundary(self) -> None:
        # No raw graph read for connectivity/visibility, no membership derivation:
        # the ranker orders ONLY the given circle's members.
        for banned in (
            ".inbound_sources(",   # would be a self-computed inbound count
            ".neighbors(",
            ".adjacency(",
            "derive_segment",
            "draw_circle(",
            "derive_seeds(",
            "children_of",
        ):
            self.assertNotIn(banned, self.source, msg=f"unexpected {banned}")

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

    def test_no_learned_or_dynamic_weights(self) -> None:
        # Static tunable constants only — no ML/fitting machinery.
        for banned in ("sklearn", "torch", "tensorflow", ".fit(", "gradient", "backprop"):
            self.assertNotIn(banned, self.source)
        # DEFAULT_WEIGHTS is a static module-level named constant.
        self.assertIsInstance(DEFAULT_WEIGHTS, Weights)

    def test_no_distillation_to_chunks(self) -> None:
        # No distill function and no distilled-chunk field on the output types.
        self.assertIsNone(re.search(r"^\s*def\s+\w*distill", self.source, re.M))
        member_fields = {f.name for f in dr.RankedMember.__dataclass_fields__.values()}
        circle_fields = {f.name for f in dr.RankedCircle.__dataclass_fields__.values()}
        forbidden = {"chunk", "chunks", "distilled", "text", "body", "content"}
        self.assertEqual(member_fields & forbidden, set())
        self.assertEqual(circle_fields & forbidden, set())

    def test_output_carries_breakdown_score_and_effective_weights(self) -> None:
        # Inspectable/governed surface: breakdown + score per member; effective
        # weights on the circle.
        member_fields = {f.name for f in dr.RankedMember.__dataclass_fields__.values()}
        circle_fields = {f.name for f in dr.RankedCircle.__dataclass_fields__.values()}
        self.assertTrue({"uid", "score", "breakdown", "contributions"} <= member_fields)
        self.assertTrue({"task_uid", "weights", "tilt", "members"} <= circle_fields)

    def test_ranks_only_circle_members_no_membership_re_derivation(self) -> None:
        # The ranked output is exactly the circle's members — nothing added, none
        # re-derived across the visibility boundary.
        fx = _RankFixture(self.roots)
        given = ("m0000001", "m0000002", "m0000003")
        for uid in given:
            fx.member(uid, type_="note", status="active")
            fx.authority_from(uid, TEAM, 1)
        # A viewer-visible neighbour that is NOT in the circle must never appear.
        fx.member("notincir", type_="capsule", status="active")
        fx.authority_from("notincir", TEAM, 9)
        task = fx.set_task("task0001", "note")
        ranked = self.rank(fx, fx.circle(task, *given), task).value
        self.assertEqual(set(ranked.uids()), set(given))
        self.assertNotIn("notincir", ranked.uids())


# =========================================================================== #
# RELATION SPECIFICITY — the fifth feature (a0c648f3; Argus A144 ruling        #
# 2026-08-03). Metis G99 measured the inversion: "Tropo Governance",           #
# `governed_by` on 1,747 entries, ranked #1 in five of six real tasks while    #
# the two documents the work explicitly cited ranked LAST. Relation type was   #
# absent from the score, so an automatic edge and an authored one weighed the  #
# same and connectivity then rewarded hub degree.                              #
# =========================================================================== #
class RelationSpecificityFeature(_RankCase):
    def _equal_but_for_relation(self):
        """Three members identical in type, status, decay and authority. The
        ONLY thing that differs is the relation that admitted them, so any
        ordering here is attributable to the relation feature and nothing else."""

        fx = _RankFixture(self.roots)
        for uid in ("deliber0", "structur", "boilerpl"):
            fx.member(uid, type_="note", status="active")
            fx.authority_from(uid, TEAM, 1)
        task = fx.set_task("task0001", "note")  # neutral type -> no tilt
        circle = fx.circle_by_relation(
            task,
            ("deliber0", tc.REL_REF),
            ("structur", tc.REL_MEMBER_PARENT),
            ("boilerpl", tc.REL_GOVERNED_BY),
        )
        return fx, task, circle

    def test_deliberate_outranks_structural_outranks_boilerplate(self) -> None:
        fx, task, circle = self._equal_but_for_relation()
        ranked = self.ranked(fx, circle, task)
        self.assertEqual(ranked.uids(), ("deliber0", "structur", "boilerpl"))

    def test_relation_is_the_only_cause_of_that_order(self) -> None:
        # The control: zero the relation weight and the SAME circle collapses to
        # a tie broken on UID. Without this, the ordering above could be coming
        # from anything. A plant whose subject can be removed without reddening
        # it is measuring something else.
        fx, task, circle = self._equal_but_for_relation()
        off = Weights(layer=0.45, state=0.30, connectivity=0.20,
                      decay=-0.15, relation=0.0)
        ranked = self.ranked(fx, circle, task, weights=off)
        scores = {uid: ranked.score(uid) for uid in ranked.uids()}
        self.assertEqual(len(set(round(s, 9) for s in scores.values())), 1)
        self.assertEqual(ranked.uids(), tuple(sorted(scores)))  # pure UID tiebreak

    def test_boost_is_strong_but_lifecycle_can_still_overturn_it(self) -> None:
        # Argus's binding constraint: a STRONG BOOST, never an absolute override.
        # A deliberate reference to RETIRED work must lose to a live structural
        # neighbour — otherwise the fix trades one inversion for its mirror.
        fx = _RankFixture(self.roots)
        fx.member("deadref0", type_="note", status="retired")
        fx.member("livepart", type_="note", status="active")
        for uid in ("deadref0", "livepart"):
            fx.authority_from(uid, TEAM, 1)
        task = fx.set_task("task0001", "note")
        ranked = self.ranked(fx, fx.circle_by_relation(
            task, ("deadref0", tc.REL_REF), ("livepart", tc.REL_MEMBER_PARENT)), task)
        self.assertEqual(ranked.uids(), ("livepart", "deadref0"))

    def test_a_healthy_deliberate_reference_does_win(self) -> None:
        # The other half of the same claim: the boost is real, not merely
        # survivable. Same shape as above with the reference ALIVE flips it.
        fx = _RankFixture(self.roots)
        for uid in ("liveref0", "livepart"):
            fx.member(uid, type_="note", status="active")
            fx.authority_from(uid, TEAM, 1)
        task = fx.set_task("task0001", "note")
        ranked = self.ranked(fx, fx.circle_by_relation(
            task, ("liveref0", tc.REL_REF), ("livepart", tc.REL_MEMBER_PARENT)), task)
        self.assertEqual(ranked.uids(), ("liveref0", "livepart"))

    def test_hub_degree_no_longer_beats_a_deliberate_reference(self) -> None:
        # The measured symptom, reproduced in miniature: a governance node with
        # overwhelming inbound degree against a reference with almost none.
        fx = _RankFixture(self.roots)
        fx.member("hubgov00", type_="note", status="active")
        fx.member("citedref", type_="note", status="active")
        fx.authority_from("hubgov00", TEAM, 40)   # the 1,747-edge shape
        fx.authority_from("citedref", TEAM, 1)
        task = fx.set_task("task0001", "note")
        ranked = self.ranked(fx, fx.circle_by_relation(
            task, ("hubgov00", tc.REL_GOVERNED_BY), ("citedref", tc.REL_REF)), task)
        self.assertEqual(ranked.uids(), ("citedref", "hubgov00"))

    def test_unknown_relation_defaults_to_structural_never_deliberate(self) -> None:
        # A relation kind nobody has tiered yet must not be able to promote
        # itself into the top tier by being unrecognised.
        self.assertEqual(dr.relation_score("a-kind-invented-tomorrow"),
                         dr.RELATION_STRUCTURAL)
        self.assertEqual(dr.relation_score(None), dr.RELATION_STRUCTURAL)
        self.assertEqual(dr.relation_score(""), dr.RELATION_STRUCTURAL)
        self.assertLess(dr.relation_score("a-kind-invented-tomorrow"),
                        dr.relation_score(tc.REL_REF))

    def test_every_relation_the_circle_can_emit_is_tiered(self) -> None:
        # Guard against the circle growing a relation the ranker never tiered.
        # It would still score (the default is safe), but silently at the middle
        # tier — so this fails loudly at the moment the vocabulary changes.
        emitted = {
            tc.REL_GOVERNED_BY, tc.REL_REF, tc.REL_MEMBER_PARENT,
            tc.REL_MEMBER_ANCESTOR, tc.REL_TYPE_SIBLING, tc.REL_NEIGHBOR,
            tc.REL_WALK_HOP, tc.REL_QUERY_SEED,
        }
        self.assertEqual(emitted - set(dr.RELATION_SCORES), set())

    def test_relation_is_inspectable_and_reconstructs_the_score(self) -> None:
        # AC5 must still hold with five features: breakdown · weights == score.
        fx, task, circle = self._equal_but_for_relation()
        ranked = self.ranked(fx, circle, task)
        self.assertIn("relation", FEATURE_NAMES)
        for member in ranked.members:
            self.assertAlmostEqual(
                sum(getattr(ranked.weights, n) * getattr(member.breakdown, n)
                    for n in FEATURE_NAMES),
                member.score,
            )
            self.assertAlmostEqual(sum(member.contributions.values()), member.score)

    def test_relation_survives_the_task_tilt(self) -> None:
        # apply_task_tilt rebuilds the Weights object; a field dropped there
        # would silently zero the feature for tilted tasks only.
        for task_type in ("design-brief", "note", "task", "capsule"):
            with self.subTest(task_type=task_type):
                effective, _ = dr.apply_task_tilt(DEFAULT_WEIGHTS, task_type)
                self.assertEqual(effective.relation, DEFAULT_WEIGHTS.relation)


if __name__ == "__main__":
    unittest.main()
