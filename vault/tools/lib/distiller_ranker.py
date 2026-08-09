"""lib/distiller_ranker.py — the distiller's deterministic relevance ordering
(dev-spec ``1230fa5d``; paired test-spec ``e380cfb0``; cycle brief ``6da0d037``
§9 decision 3, Mike-locked 2026-06-21).

The distiller's three moves are **draw a circle -> walk -> distill**
(``6da0d037`` §5 Face B). The circle (``e12ff178`` / :mod:`lib.task_circle`) and
the viewer-relative walk (``5043b274`` / :mod:`lib.viewer_projection`) are on
main. This module is the THIRD move's deterministic half: given the already-
drawn, already-viewer-safe :class:`~lib.task_circle.Circle`, order its members by
**why they matter** — a transparent, tunable weighted sum of four DETERMINISTIC
structural features — and show the math for every member.

It is the *deterministic* half of ``6da0d037`` §9 decision 3's "tunable weighted
ranker": ``prior-model > state > signal`` with task-tilt on top, weights kept
inspectable so the ranker stays governed, not a black box. The fuzzy relevance
edge (a freeform "ask your vault" query + a relevance model) and distillation to
chunks are Cut 4 (``6da0d037`` §8/§10) and are explicitly NOT built here.

The four features per circle member (``1230fa5d`` §The design):

1. **Layer (type-tier).** A named :data:`LAYER_TIERS` map — a documented
   prior-model, never a magic literal: governance/decision/capsule/arch-spec/
   playbook ("capsules have the truth") > work entries > events/memories.
2. **State (lifecycle).** :data:`STATE_SCORES` from ``status``/``state``:
   ``active``/``locked``/``current``/``shipped``/``published`` up-weighted;
   ``superseded``/``archived``/``rejected``/``cancelled``/``deprecated`` down.
3. **Connectivity.** :meth:`ViewerProjection.authority` — the segment-local,
   DECAY-GATED live-edge inbound count (``5043b274`` invariant 2). REUSED, never
   re-implemented: this module NEVER computes its own inbound count, so a dead /
   cross-segment incumbent cannot win on dead edges (the ``legacy-work-pipeline``
   574-inbound-edge failure, ``6da0d037`` §9 decision 3). Normalised WITHIN the
   circle (divided by the circle's max authority) so it is a comparable [0, 1]
   signal without any cross-segment or viewer-relative computation.
4. **Decay penalty.** A down-weight on the residual gardener decay signal read
   from the index ``decay`` object (circle members already cleared the circle's
   high-confidence decay GATE; this penalises what remains).

``score = Σ wᵢ·featureᵢ`` with weights from the inspectable :data:`DEFAULT_WEIGHTS`
named constant (``decay`` carries a NEGATIVE weight — it is a penalty). **Task-tilt**
(:func:`apply_task_tilt`) is a deterministic function of the TASK's ``type`` that
adjusts the profile: a lifecycle/status task (e.g. ``type: task``) up-weights
``state``; a design task (e.g. ``type: design-brief`` / ``design-spec`` /
``arch-spec``) up-weights ``layer``. The *effective* (post-tilt) weights are
emitted in the output.

:func:`rank_circle` returns a :class:`RankedCircle`: members ordered
score-DESCENDING with a stable UID tiebreak, each a :class:`RankedMember`
carrying its per-feature value breakdown + per-feature contribution + final score,
alongside the effective weights — so ``breakdown · weights == score`` is
reconstructable and a human can see WHY a member ranked where it did and tune the
weights (``6da0d037`` §9 decision 3: inspectable, governed).

Explicit exclusions (``1230fa5d`` §Explicit exclusions): NO model/network calls,
NO learned/dynamic weights (static tunable module constants only), NO freeform-
query parsing, NO distillation to chunks, and NO re-deriving circle membership /
re-crossing the visibility boundary — the given circle is ranked in place. The
typed :class:`~lib.group_registry.Result` and
:class:`~lib.viewer_projection.GraphError` are REUSED, so a refusal (e.g. an
authority read that cannot resolve) propagates typed, never a permissive default.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

# The typed Result convention + the walk's typed errors + the connectivity
# authority — all REUSED, never re-invented (dev-spec: compose, do not fork).
from lib.group_registry import Result  # noqa: E402
from lib.viewer_projection import (  # noqa: E402
    GraphError,
    GraphErrorCode,
    Viewer,
    ViewerProjection,
)


# --------------------------------------------------------------------------- #
# Feature 1 — LAYER (the prior model). A named, documented tier map, NOT a     #
# magic literal (``6da0d037`` §9 decision 3: "capsules have the truth").       #
#                                                                              #
# Three tiers, highest to lowest:                                              #
#   * GOVERNANCE — capsules / ADRs (decisions) / arch-specs / playbooks and    #
#     their governance kin. The prior model: authored, load-bearing truth.     #
#   * WORK       — the crew's produced work artifacts (tasks, briefs, specs,   #
#     notes, documents, projects, releases, ...).                             #
#   * EVENT      — the graph's own exhaust (events, memories, run instances,   #
#     snapshots). Lowest: high-volume, low-authority (``6da0d037`` §4: the      #
#     system is its own biggest polluter).                                     #
# Values are on an inspectable [0, 1] scale so a reviewer can read the prior   #
# directly and re-tune it as a code change. An unrecognised type falls to      #
# :data:`LAYER_TIER_DEFAULT` (the lowest tier — an unknown type is never       #
# inflated above known work).                                                  #
# --------------------------------------------------------------------------- #
LAYER_TIER_GOVERNANCE = 1.0
LAYER_TIER_WORK = 0.55
LAYER_TIER_EVENT = 0.15
LAYER_TIER_DEFAULT = LAYER_TIER_EVENT

LAYER_TIERS: Mapping[str, float] = {
    # --- Governance / prior-model tier ("capsules have the truth") ---------- #
    "capsule": LAYER_TIER_GOVERNANCE,
    "capsule-definition": LAYER_TIER_GOVERNANCE,
    "decision": LAYER_TIER_GOVERNANCE,          # ADRs
    "arch-spec": LAYER_TIER_GOVERNANCE,
    "playbook": LAYER_TIER_GOVERNANCE,
    "playbook-run": LAYER_TIER_GOVERNANCE,
    "project-plan": LAYER_TIER_GOVERNANCE,
    "release-plan": LAYER_TIER_GOVERNANCE,
    "subsystem-hub": LAYER_TIER_GOVERNANCE,
    "how-to": LAYER_TIER_GOVERNANCE,
    "tool": LAYER_TIER_GOVERNANCE,
    "action": LAYER_TIER_GOVERNANCE,
    "board-definition": LAYER_TIER_GOVERNANCE,
    "entity": LAYER_TIER_GOVERNANCE,
    "team": LAYER_TIER_GOVERNANCE,
    "vault": LAYER_TIER_GOVERNANCE,
    "vault-entity": LAYER_TIER_GOVERNANCE,
    # --- Work-entry tier (the crew's produced work) ------------------------- #
    "task": LAYER_TIER_WORK,
    "design-brief": LAYER_TIER_WORK,
    "design-spec": LAYER_TIER_WORK,
    "dev-spec": LAYER_TIER_WORK,
    "test-spec": LAYER_TIER_WORK,
    "doc-spec": LAYER_TIER_WORK,
    "build": LAYER_TIER_WORK,
    "release": LAYER_TIER_WORK,
    "note": LAYER_TIER_WORK,
    "document": LAYER_TIER_WORK,
    "kb-article": LAYER_TIER_WORK,
    "project": LAYER_TIER_WORK,
    "collection": LAYER_TIER_WORK,
    "collection-ref": LAYER_TIER_WORK,
    "pipeline": LAYER_TIER_WORK,
    "ship-artifact": LAYER_TIER_WORK,
    "external-artifact": LAYER_TIER_WORK,
    "agent": LAYER_TIER_WORK,
    # --- Event / memory tier (the graph's exhaust — lowest) ----------------- #
    "memory": LAYER_TIER_EVENT,
    "memory-entry": LAYER_TIER_EVENT,
    "event": LAYER_TIER_EVENT,
    "chat-session": LAYER_TIER_EVENT,
    "session-agent": LAYER_TIER_EVENT,
    "loop": LAYER_TIER_EVENT,
    "test-run": LAYER_TIER_EVENT,
    "pipeline-run": LAYER_TIER_EVENT,
    "board-snapshot": LAYER_TIER_EVENT,
    "reconcile-report": LAYER_TIER_EVENT,
    "working-copy": LAYER_TIER_EVENT,
    "capsule-history": LAYER_TIER_EVENT,
    "activation": LAYER_TIER_EVENT,
}


# --------------------------------------------------------------------------- #
# Feature 2 — STATE (lifecycle). A named, documented map from the lifecycle    #
# ``status`` / ``state`` fields to an inspectable [0, 1] health score.         #
# Up-weighted: live / authoritative / shipped. Down-weighted: superseded /     #
# archived / rejected / cancelled / deprecated (``1230fa5d`` AC2). An unknown  #
# value falls to :data:`STATE_SCORE_DEFAULT` (a neutral mid). A record's       #
# status and state are BOTH consulted and the MORE CONSERVATIVE (minimum) is   #
# taken, because ``6da0d037`` §4 measured that ~24% of entries carry a         #
# lifecycle CONTRADICTION (state vs status disagree, "the status field lies")  #
# — so a node claiming ``active`` while its state says ``archived`` is scored   #
# on the down-weighted archived value, not the flattering one.                 #
# --------------------------------------------------------------------------- #
STATE_SCORE_DEFAULT = 0.5

STATE_SCORES: Mapping[str, float] = {
    # --- up-weighted: live / authoritative / shipped ------------------------ #
    "active": 1.0,
    "locked": 1.0,
    "current": 1.0,
    "evergreen": 1.0,
    "standing": 1.0,
    "shipped": 1.0,
    "published": 1.0,
    "final": 0.95,
    "accepted": 0.85,
    "done": 0.8,
    "complete": 0.8,
    "verify": 0.75,
    "closed": 0.7,
    # --- neutral / in-flight ------------------------------------------------ #
    "build": 0.65,
    "design": 0.6,
    "specify": 0.6,
    "open": 0.6,
    "requested": 0.55,
    "draft": 0.5,
    "new": 0.5,
    "pre-ship": 0.5,
    "sent": 0.5,
    # --- down-weighted: blocked / terminal / rotten ------------------------- #
    "blocked": 0.3,
    "dormant": 0.2,
    "retired": 0.15,
    "superseded": 0.1,
    "archived": 0.1,
    "rejected": 0.1,
    "cancelled": 0.1,
    "deprecated": 0.1,
    "failed": 0.1,
    "stale": 0.1,
}


# --------------------------------------------------------------------------- #
# Relation specificity — how DELIBERATE the link that admitted this member is.  #
#                                                                               #
# A link a human authored says more about a piece of work than one the system   #
# attached to everything. Without this feature an automatic ``governed_by`` edge #
# and a hand-written ``refs`` edge weigh identically, and ``connectivity`` then  #
# rewards hub degree — so the most-connected node wins every circle it appears   #
# in. Measured by Metis G99 (``a0c648f3``): "Tropo Governance", ``governed_by``  #
# on 1,747 entries, ranked #1 in five of six real tasks while the two documents  #
# the work explicitly cited ranked last.                                        #
#                                                                               #
# Tiers are Argus A144's ruling (2026-08-03). The values are a STRONG BOOST and  #
# deliberately NOT an absolute override: at the default weight a deliberate      #
# reference to retired or rotten work still loses to a live structural neighbour,#
# because ``state`` and ``decay`` keep their full say. A tier table that could   #
# not be overturned by lifecycle would trade one inversion for its mirror image. #
# --------------------------------------------------------------------------- #
RELATION_DELIBERATE = 1.0   # a human authored this link
RELATION_STRUCTURAL = 0.5   # the graph's shape put it here
RELATION_BOILERPLATE = 0.15  # attached automatically, to nearly everything
RELATION_SCORE_DEFAULT = RELATION_STRUCTURAL

RELATION_SCORES = {
    # --- deliberate: someone chose to point at this ------------------------- #
    "ref-of-task": RELATION_DELIBERATE,
    "ref-to-task": RELATION_DELIBERATE,
    "refs": RELATION_DELIBERATE,
    # A query seed is the most deliberate signal available — a human typed it.
    # NOT named in the ruling; tiered here by the ruling's own principle and
    # flagged to Argus rather than left to fall through to the default.
    "query-seed": RELATION_DELIBERATE,
    # --- structural: real graph shape, but nobody chose it for THIS work ----- #
    "member_of-parent": RELATION_STRUCTURAL,
    "member_of-child": RELATION_STRUCTURAL,
    "neighbor-of-task": RELATION_STRUCTURAL,
    "walk-hop-from": RELATION_STRUCTURAL,
    # --- boilerplate: attached by the system, near-universal ----------------- #
    "governed_by-of-task": RELATION_BOILERPLATE,
    "member_of-ancestor": RELATION_BOILERPLATE,
    "type-sibling": RELATION_BOILERPLATE,
}


def relation_score(relation: Optional[str]) -> float:
    """Map a circle-inclusion relation to its specificity tier.

    An unknown relation scores :data:`RELATION_SCORE_DEFAULT` (structural) — the
    middle tier, never the top one. A new relation kind must not be able to
    promote itself to "deliberate" by being unrecognised.
    """

    if not relation:
        return RELATION_SCORE_DEFAULT
    return RELATION_SCORES.get(str(relation).strip(), RELATION_SCORE_DEFAULT)


# --------------------------------------------------------------------------- #
# The default weight profile — an inspectable, tunable named constant          #
# (``6da0d037`` §9 decision 3: "weights stay inspectable, keeping the ranker    #
# governed, not a black box"). Priority ``prior-model > state > signal``:       #
# layer > state > connectivity. ``decay`` is a PENALTY, hence a NEGATIVE        #
# weight. Weights are coefficients, not a probability simplex — they need not   #
# sum to 1, which keeps task-tilt a simple, readable additive delta.           #
# --------------------------------------------------------------------------- #
FEATURE_NAMES = ("layer", "state", "connectivity", "decay", "relation")


@dataclass(frozen=True)
class Weights:
    """An inspectable, tunable weight profile over the five features.

    ``decay`` is a penalty and is conventionally negative. Frozen so a profile
    is a stable, hashable value; :meth:`as_dict` / :meth:`canonical` give a
    byte-stable inspection surface (mirrors the circle's own ``canonical``).

    ``relation`` has NO default on purpose. A profile that silently omitted it
    would score every relation at zero and quietly restore the inversion this
    feature exists to fix — a caller that has not thought about relation should
    fail loudly, not rank plausibly.
    """

    layer: float
    state: float
    connectivity: float
    decay: float
    relation: float

    def as_dict(self) -> dict:
        return {
            "layer": self.layer,
            "state": self.state,
            "connectivity": self.connectivity,
            "decay": self.decay,
            "relation": self.relation,
        }

    def canonical(self) -> str:
        import json

        return json.dumps(
            {name: round(getattr(self, name), 6) for name in FEATURE_NAMES},
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )


# ``relation`` at 0.35 is sized from the live re-baseline, not guessed: on the
# incremental-validation brief the two deliberate references sat at 0.517/0.514
# against structural containers at 0.650/0.649. A deliberate member gains
# ``0.35 · 1.0`` where a structural one gains ``0.35 · 0.5``, a net 0.175 swing —
# enough to clear a 0.136 deficit with margin, and NOT enough to outrank a live
# node whose lifecycle is healthy when the reference itself is retired or rotten.
# That second property is the "strong boost, not absolute override" half of the
# ruling, and it is pinned by test rather than left as an intention.
DEFAULT_WEIGHTS = Weights(
    layer=0.45, state=0.30, connectivity=0.20, decay=-0.15, relation=0.35
)


# --------------------------------------------------------------------------- #
# Task-tilt — a DETERMINISTIC function of the TASK's type (``1230fa5d`` AC3 /   #
# ``6da0d037`` §9 decision 3). Not a fixed order and not a hidden bias: the     #
# tilt is a documented additive delta on ONE feature weight, and the resulting  #
# effective profile is emitted in the output so the reordering is auditable.    #
#   * A lifecycle / status task (its progress is about STATE) up-weights the    #
#     ``state`` feature.                                                        #
#   * A design task (its progress is about the prior model / LAYER) up-weights  #
#     the ``layer`` feature.                                                    #
#   * Any other task type leaves :data:`DEFAULT_WEIGHTS` unchanged.             #
# --------------------------------------------------------------------------- #
TILT_DELTA = 0.15

STATE_TILT_TASK_TYPES = frozenset({"task", "build", "release", "action"})
LAYER_TILT_TASK_TYPES = frozenset(
    {"design-brief", "design-spec", "arch-spec", "dev-spec", "doc-spec"}
)

TILT_STATE = "state"
TILT_LAYER = "layer"
TILT_NONE = "none"


def _norm(value: Optional[str]) -> str:
    """Lower/trim a raw enum-ish field; ``None``/non-str -> ``""``."""

    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def task_tilt_kind(task_type: Optional[str]) -> str:
    """The tilt label for a task ``type`` — one of :data:`TILT_STATE`,
    :data:`TILT_LAYER`, or :data:`TILT_NONE`. Pure, deterministic, no model."""

    normalized = _norm(task_type)
    if normalized in STATE_TILT_TASK_TYPES:
        return TILT_STATE
    if normalized in LAYER_TILT_TASK_TYPES:
        return TILT_LAYER
    return TILT_NONE


def apply_task_tilt(weights: Weights, task_type: Optional[str]) -> tuple:
    """Return ``(effective_weights, tilt_kind)``: ``weights`` with the tilt's
    additive :data:`TILT_DELTA` applied to the up-weighted feature. The delta is
    added (never a multiply, never learned) so the effect is a readable, bounded
    shift a reviewer can reproduce by hand."""

    kind = task_tilt_kind(task_type)
    if kind == TILT_STATE:
        return (
            Weights(
                layer=weights.layer,
                state=weights.state + TILT_DELTA,
                connectivity=weights.connectivity,
                decay=weights.decay,
                relation=weights.relation,
            ),
            kind,
        )
    if kind == TILT_LAYER:
        return (
            Weights(
                layer=weights.layer + TILT_DELTA,
                state=weights.state,
                connectivity=weights.connectivity,
                decay=weights.decay,
                relation=weights.relation,
            ),
            kind,
        )
    return (weights, kind)


# --------------------------------------------------------------------------- #
# The rank index — read-only per-member type/status/state/decay metadata.      #
#                                                                              #
# Distinct from ``task_circle``'s StructuralIndex (which surfaces the typed    #
# relations + decay used for SEED derivation): the ranker reads the LIFECYCLE  #
# fields (``status``/``state``) the layer / state / decay features need. Same  #
# single composed union index (``vault/00-index.sqlite``) underneath; injected #
# keyword-only exactly like ``draw_circle`` so the ranker composes on the      #
# landed substrate and is testable against a sandbox fixture. Read-only.       #
# --------------------------------------------------------------------------- #
class RankIndex:
    """Read-only source of the lifecycle/type/decay fields the ranker reads."""

    def record(self, uid: str) -> Optional[dict]:  # pragma: no cover - interface
        """``{"type": str, "status": str|None, "state": str|None,
        "decay": {...}|None}`` for ``uid``, or ``None`` if not indexed."""

        raise NotImplementedError


class InMemoryRankIndex(RankIndex):
    """In-memory rank index (sandbox fixture parity with
    :class:`lib.viewer_projection.InMemoryGraphSource`)."""

    def __init__(self, records: Mapping[str, dict]) -> None:
        self._records = {uid: dict(rec) for uid, rec in records.items()}

    def record(self, uid: str) -> Optional[dict]:
        rec = self._records.get(uid)
        if rec is None:
            return None
        return {
            "type": rec.get("type") or "",
            "status": rec.get("status"),
            "state": rec.get("state"),
            "decay": rec.get("decay"),
        }


class SqliteRankIndex(RankIndex):
    """Production rank index over the composed union index
    (``vault/00-index.sqlite``). Read-only; never a writer.

    ``type`` / ``status`` / ``state`` come from the ``entries`` table columns;
    the gardener ``decay`` object comes from ``fm_json``. Same single composed
    source the walk projects over and the circle's structural index reads.
    """

    def __init__(self, index_path: "os.PathLike | str") -> None:  # noqa: F821
        self._index_path = Path(index_path)
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

    def record(self, uid: str) -> Optional[dict]:
        import json

        cur = self._connection().cursor()
        row = cur.execute(
            "SELECT type, status, state, fm_json FROM entries WHERE uid=?", (uid,)
        ).fetchone()
        if row is None:
            return None
        decay = None
        if row[3]:
            try:
                decay = json.loads(row[3]).get("decay")
            except (ValueError, TypeError):
                decay = None
        return {
            "type": (row[0] or ""),
            "status": row[1],
            "state": row[2],
            "decay": decay,
        }


# --------------------------------------------------------------------------- #
# The four deterministic feature functions (each pure; no wall-clock, no I/O    #
# beyond the injected read-only index / segment-local authority).              #
# --------------------------------------------------------------------------- #
def layer_score(node_type: Optional[str]) -> float:
    """Feature 1 — the prior-model tier score for a ``type`` via
    :data:`LAYER_TIERS`; unknown types fall to :data:`LAYER_TIER_DEFAULT`."""

    return LAYER_TIERS.get(_norm(node_type), LAYER_TIER_DEFAULT)


def state_score(status: Optional[str], state: Optional[str]) -> float:
    """Feature 2 — the lifecycle health score. Both ``status`` and ``state`` are
    scored via :data:`STATE_SCORES`; the MINIMUM present score wins (conservative
    on a lifecycle contradiction, ``6da0d037`` §4). If neither is a recognised
    value, :data:`STATE_SCORE_DEFAULT`."""

    scores = []
    for raw in (status, state):
        normalized = _norm(raw)
        if normalized in STATE_SCORES:
            scores.append(STATE_SCORES[normalized])
    if not scores:
        return STATE_SCORE_DEFAULT
    return min(scores)


def decay_penalty(decay: Optional[dict]) -> float:
    """Feature 4 — the residual decay magnitude in [0, 1]. A stale node's
    penalty is its gardener confidence; a non-stale / absent / malformed decay
    object contributes no penalty. This value is combined with the NEGATIVE
    ``decay`` weight, so a higher residual decay lowers the score."""

    if not isinstance(decay, dict) or not decay.get("stale"):
        return 0.0
    try:
        confidence = float(decay.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0
    if confidence < 0.0:
        return 0.0
    if confidence > 1.0:
        return 1.0
    return confidence


# --------------------------------------------------------------------------- #
# The ranked output — inspectable, byte-stable, reconstructable.               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FeatureBreakdown:
    """The four raw feature VALUES for one member (before weighting). Dotting
    this with the circle's effective :class:`Weights` reconstructs the member's
    score (``1230fa5d`` AC5), so it is the audit surface for "why this score"."""

    layer: float
    state: float
    connectivity: float
    decay: float
    relation: float

    def as_dict(self) -> dict:
        return {
            "layer": self.layer,
            "state": self.state,
            "connectivity": self.connectivity,
            "decay": self.decay,
            "relation": self.relation,
        }


@dataclass(frozen=True)
class RankedMember:
    """One ranked circle member: its UID, final ``score``, the raw feature
    ``breakdown``, and the per-feature ``contributions`` (``weight · feature``).
    ``sum(contributions.values()) == score`` and
    ``breakdown · effective_weights == score`` both hold (AC5)."""

    uid: str
    score: float
    breakdown: FeatureBreakdown
    contributions: dict

    def _sort_key(self) -> tuple:
        # Score-DESCENDING (negated) with a stable ascending-UID tiebreak, so a
        # tie is broken deterministically and reproducibly (AC4).
        return (-self.score, self.uid)


@dataclass(frozen=True)
class RankedCircle:
    """The ranking result: the members score-descending (stable UID tiebreak),
    the EFFECTIVE (post-tilt) :class:`Weights` used, and the applied ``tilt``
    kind. ``task_uid`` is the task the circle was ranked for. :meth:`canonical`
    is a byte-stable audit surface (mirrors
    :meth:`lib.task_circle.Circle.canonical`)."""

    task_uid: str
    weights: Weights
    tilt: str
    members: tuple

    def uids(self) -> tuple:
        """The member UIDs in ranked (score-descending) order."""

        return tuple(m.uid for m in self.members)

    def member(self, uid: str) -> Optional[RankedMember]:
        for ranked in self.members:
            if ranked.uid == uid:
                return ranked
        return None

    def score(self, uid: str) -> Optional[float]:
        ranked = self.member(uid)
        return ranked.score if ranked is not None else None

    def canonical(self) -> str:
        import json

        return json.dumps(
            {
                "task": self.task_uid,
                "tilt": self.tilt,
                "weights": {
                    name: round(getattr(self.weights, name), 6)
                    for name in FEATURE_NAMES
                },
                "members": [
                    {
                        "uid": m.uid,
                        "score": round(m.score, 6),
                        "breakdown": {
                            name: round(getattr(m.breakdown, name), 6)
                            for name in FEATURE_NAMES
                        },
                        "contributions": {
                            name: round(m.contributions[name], 6)
                            for name in FEATURE_NAMES
                        },
                    }
                    for m in self.members
                ],
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )


# --------------------------------------------------------------------------- #
# rank_circle — the deterministic weighted ordering.                           #
# --------------------------------------------------------------------------- #
def rank_circle(
    circle,
    task_uid: str,
    viewer: Viewer,
    weights: Weights = DEFAULT_WEIGHTS,
    *,
    projection: ViewerProjection,
    index: RankIndex,
) -> Result:
    """``Result[RankedCircle, GraphError]`` — order the circle's members by the
    weighted structural relevance sum.

    ``circle`` is an already-drawn, already-viewer-safe
    :class:`~lib.task_circle.Circle` (only its ``members``' UIDs are read — this
    function NEVER re-derives membership and NEVER re-crosses the visibility
    boundary; the circle is ranked in place). ``task_uid`` selects the task-tilt.
    ``viewer`` is accepted for interface parity with the circle/walk substrate,
    but connectivity uses the segment-local, viewer-INDEPENDENT
    :meth:`~lib.viewer_projection.ViewerProjection.authority`, so no
    viewer-relative re-computation of visibility happens here (the circle already
    encodes it). ``weights`` is the tunable profile (default
    :data:`DEFAULT_WEIGHTS`). ``projection`` and ``index`` are injected
    keyword-only exactly like :func:`lib.task_circle.draw_circle`.

    Deterministic: the score is a pure weighted sum of the four features; ties
    break on ascending UID; the same ``(circle, task, viewer, weights)`` yields a
    byte-identical :class:`RankedCircle` every run (no wall-clock, no model).

    Fails closed with the walk's typed :class:`~lib.viewer_projection.GraphError`
    if a member's segment-local authority cannot be resolved — never a permissive
    default rank.
    """

    members = tuple(getattr(circle, "members", ()) or ())

    # Task-tilt: a deterministic function of the TASK's type. A missing task
    # record simply yields no tilt (the default profile) — ranking a circle does
    # not require the task itself to still be indexed.
    task_record = index.record(task_uid)
    task_type = (task_record or {}).get("type") if task_record else None
    effective, tilt = apply_task_tilt(weights, task_type)

    # Pass 1 — segment-local authority per member (REUSED, decay-gated, viewer-
    # independent). Fail closed on any unresolved authority. The circle's max is
    # the normalisation denominator so connectivity is a comparable [0, 1] signal
    # computed WITHIN the circle (no cross-segment / raw-count computation here).
    authorities: dict = {}
    max_authority = 0
    for member in members:
        result = projection.authority(member.uid)
        if not result.ok:
            return Result.failure(result.error)  # typed refusal propagates
        authorities[member.uid] = result.value
        if result.value > max_authority:
            max_authority = result.value

    # Pass 2 — features -> contributions -> score, per member.
    ranked: list = []
    for member in members:
        record = index.record(member.uid) or {}
        raw_authority = authorities[member.uid]
        connectivity = (raw_authority / max_authority) if max_authority > 0 else 0.0

        breakdown = FeatureBreakdown(
            layer=layer_score(record.get("type")),
            state=state_score(record.get("status"), record.get("state")),
            connectivity=connectivity,
            decay=decay_penalty(record.get("decay")),
            # The circle already carries WHY this member was admitted; the
            # ranker reads that provenance rather than re-deriving any edge.
            relation=relation_score(getattr(member, "relation", None)),
        )
        contributions = {
            name: getattr(effective, name) * getattr(breakdown, name)
            for name in FEATURE_NAMES
        }
        score = sum(contributions.values())
        ranked.append(
            RankedMember(
                uid=member.uid,
                score=score,
                breakdown=breakdown,
                contributions=contributions,
            )
        )

    ranked.sort(key=lambda r: r._sort_key())
    return Result.success(
        RankedCircle(
            task_uid=task_uid, weights=effective, tilt=tilt, members=tuple(ranked)
        )
    )


__all__ = [
    "LAYER_TIER_GOVERNANCE",
    "LAYER_TIER_WORK",
    "LAYER_TIER_EVENT",
    "LAYER_TIER_DEFAULT",
    "LAYER_TIERS",
    "STATE_SCORE_DEFAULT",
    "STATE_SCORES",
    "RELATION_DELIBERATE",
    "RELATION_STRUCTURAL",
    "RELATION_BOILERPLATE",
    "RELATION_SCORE_DEFAULT",
    "RELATION_SCORES",
    "relation_score",
    "FEATURE_NAMES",
    "Weights",
    "DEFAULT_WEIGHTS",
    "TILT_DELTA",
    "STATE_TILT_TASK_TYPES",
    "LAYER_TILT_TASK_TYPES",
    "TILT_STATE",
    "TILT_LAYER",
    "TILT_NONE",
    "task_tilt_kind",
    "apply_task_tilt",
    "RankIndex",
    "InMemoryRankIndex",
    "SqliteRankIndex",
    "layer_score",
    "state_score",
    "decay_penalty",
    "FeatureBreakdown",
    "RankedMember",
    "RankedCircle",
    "rank_circle",
]
