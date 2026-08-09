"""lib/distiller.py — deterministic task and boot orientation composition
(dev-spec ``5b532f4b``; paired test-spec ``120d5b3a``; activation ``e08ed396``;
cycle brief ``6da0d037``; composes the landed walk ``5043b274`` / circle
``e12ff178`` / ranker ``1230fa5d``).

The distiller's three moves are **draw a circle -> walk -> distill**
(``6da0d037`` §5 Face B). The viewer-relative walk (``5043b274`` /
:mod:`lib.viewer_projection`), the circle (``e12ff178`` / :mod:`lib.task_circle`),
and the deterministic ranker (``1230fa5d`` / :mod:`lib.distiller_ranker`) all
landed on main, each unit-tested. **Nothing yet proved they compose.** This module
is the integration seam: it bolts the three landed modules into ONE capability —
:func:`orient_deterministic` — and returns a ranked, viewer-safe, provenance-true
result whose composition is proven end-to-end. It is the deterministic core that
Cut 4's ``orient()`` (interface ``310aad07``) wraps with its two model edges.

Design (``5b532f4b`` §The design), in three moves:

1. ``circle = draw_circle(task_uid, viewer, budget, ...)`` — fail-closed on error.
2. ``ranked = rank_circle(circle, task_uid, viewer, ...)`` — fail-closed on error.
3. Return a :class:`DeterministicOrientation` wrapping the
   :class:`~lib.distiller_ranker.RankedCircle`, with each item carrying BOTH its
   **circle-inclusion provenance** (from the :class:`~lib.task_circle.CircleMember`)
   AND its **rank feature-breakdown + score** (from the
   :class:`~lib.distiller_ranker.RankedMember`) — both layers survive the seam,
   nothing is dropped.

This module introduces NO new graph / visibility / membership / ranking logic: it
delegates ENTIRELY to the landed modules. The SAME ``viewer`` flows through both
stages, so the privacy boundary of ``5043b274`` holds across the composed pipeline
by construction (the circle is already viewer-safe; the ranker never re-crosses
the boundary). Deterministic-only (``5b532f4b`` §Explicit exclusions): NO
model/network calls, NO ``parse_query``, NO distillation to chunks — those model
edges are Cut 4 and are explicitly out of scope here.

Stage C (dev-spec ``2672f9d0`` / :mod:`lib.orient_stage_c`) is the extractive
span layer that turns the ranked circle from a list of relevant documents into
a statement of what those documents say. :func:`orient` reaches it through ONE
injected value, :class:`StageCRequest`, and through no other path: Stage C
calls a metered model edge, so wiring it must not make an existing caller start
spending by saying nothing. ``stage_c=None`` — the default — is the chain
exactly as it was.

The agent-anchored :func:`orient_boot` surface (dev-spec ``77184178``; paired
test-spec ``87de9dad``) composes the same deterministic circle/ranker chassis
with three boot inputs: the predecessor's living transfer, a Git-reachability
delta from the transfer's commit-identity watermark to a caller-pinned
``as_of`` commit, and ranked open work.  It resolves all candidate records from
``visible_segments(viewer)`` before selecting any agent seed, stamps ``viewer``
and ``as_of`` on the serializable result, and performs no model, clock, random,
or network call.

The typed :class:`~lib.group_registry.Result` and
:class:`~lib.viewer_projection.GraphError` are REUSED, never re-invented, so a
refusal from EITHER stage propagates typed and transitively — the composition is
fail-closed: any stage error is returned as the same typed error, never a partial,
permissive, or boundary-crossing result.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

# The typed Result convention + the walk's typed errors + the Viewer principal —
# REUSED, never re-invented (dev-spec: compose, do not fork).
from lib.group_registry import Result  # noqa: E402
from lib.viewer_projection import (  # noqa: E402
    OS_SEGMENT,
    GraphError,
    Viewer,
    ViewerProjection,
)

# The three landed deterministic modules this composition delegates to. The
# ONLY graph/membership/rank logic lives in these — this module calls them and
# preserves both provenance layers; it re-implements none of them.
from lib.task_circle import Circle, CircleMember, StructuralIndex, draw_circle  # noqa: E402
from lib.distiller_ranker import (  # noqa: E402
    FEATURE_NAMES,
    RankedCircle,
    RankedMember,
    RankIndex,
    rank_circle,
)
from lib.distiller_query import (  # noqa: E402
    ParseQueryModelAdapter,
    PrevalidatedQuerySeeds,
    QueryError,
    QueryErrorCode,
    QueryIndex,
    resolve_query,
)
from lib.distiller_edge import (  # noqa: E402
    BoundOrientation,
    DistillModelAdapter,
    DistillError,
    DistillErrorCode,
    Orientation,
    distill,
)

# Stage C (dev-spec ``2672f9d0``) — the extractive span layer. Imported for its
# ONE entry point and its typed refusal; every parameter it needs is assembled
# here and nothing about its contract is restated. ``span_guard`` is imported
# only for :func:`match_domain_bytes`, the single shipped definition of Lock
# 2(a)'s match domain — this module does not get a second one.
from lib import span_guard  # noqa: E402
from lib.orient_stage_c import StageCBlock, StageCRefusal, run_stage_c  # noqa: E402


_FULL_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_AGENT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_FULL_EVENT_POSITION_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


# --------------------------------------------------------------------------- #
# The composed per-item surface. One item = one circle member, carrying BOTH   #
# provenance layers so the end-to-end result is auditable top to bottom:       #
#   * the CIRCLE-INCLUSION provenance (why it is in the circle) from the       #
#     CircleMember (relation / via / distance / provenance string), and        #
#   * the RANK feature-breakdown + score (why it ranks where it does) from the #
#     RankedMember (breakdown / contributions / score).                        #
# Neither layer is dropped at the seam (``5b532f4b`` AC3 / risk register #1).   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OrientedItem:
    """One item of the composed orientation, carrying both provenance layers.

    ``circle_member`` is the exact :class:`~lib.task_circle.CircleMember` that
    admitted the node into the circle (its structural inclusion provenance);
    ``ranked_member`` is the exact :class:`~lib.distiller_ranker.RankedMember`
    that scored/ordered it (its rank feature-breakdown + contributions + score).
    Both landed values are held verbatim — this is the seam that does NOT lose
    data — and the convenience accessors below read straight through to them.
    """

    uid: str
    circle_member: CircleMember
    ranked_member: RankedMember

    @property
    def circle_provenance(self) -> str:
        """The circle-inclusion reason (UID-citing), carried from the circle."""

        return self.circle_member.provenance

    @property
    def relation(self) -> str:
        return self.circle_member.relation

    @property
    def via(self) -> str:
        return self.circle_member.via

    @property
    def distance(self) -> int:
        return self.circle_member.distance

    @property
    def score(self) -> float:
        """The rank score, carried from the ranker."""

        return self.ranked_member.score

    @property
    def breakdown(self):
        """The per-feature raw value breakdown, carried from the ranker."""

        return self.ranked_member.breakdown

    @property
    def contributions(self) -> dict:
        """The per-feature ``weight · feature`` contributions, from the ranker."""

        return self.ranked_member.contributions


# --------------------------------------------------------------------------- #
# The composed result. Wraps the RankedCircle (ranked order + effective        #
# weights + tilt) and exposes the per-item BOTH-layer view + a byte-stable     #
# canonical surface (mirrors Circle.canonical / RankedCircle.canonical) for    #
# the end-to-end determinism + viewer-safety byte-identity property tests.     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DeterministicOrientation:
    """The end-to-end deterministic orientation for ``task_uid`` / ``viewer``.

    ``circle`` is the drawn :class:`~lib.task_circle.Circle` (viewer-safe scope);
    ``ranked`` is the :class:`~lib.distiller_ranker.RankedCircle` (the ordering +
    effective weights + tilt); ``items`` is the tuple of :class:`OrientedItem`
    in RANKED (score-descending, UID-tiebroken) order, each carrying both the
    circle-inclusion provenance and the rank breakdown + score.

    :meth:`uids` gives the ranked order; :meth:`item` looks up one item; and
    :meth:`canonical` is a byte-stable audit surface that embeds BOTH provenance
    layers — a pure function of the composed (viewer-visible) members, so it is
    byte-identical whether or not hidden neighbours exist (``5b532f4b`` AC2/AC4).
    """

    task_uid: str
    circle: Circle
    ranked: RankedCircle
    items: tuple

    def uids(self) -> tuple:
        """The item UIDs in ranked (score-descending) order."""

        return tuple(item.uid for item in self.items)

    @property
    def reference_observations(self) -> tuple:
        """Visible unresolved references kept outside membership and ranking."""

        return self.circle.reference_observations

    def item(self, uid: str) -> Optional[OrientedItem]:
        for item in self.items:
            if item.uid == uid:
                return item
        return None

    @property
    def weights(self):
        """The EFFECTIVE (post-tilt) weights the ranker used."""

        return self.ranked.weights

    @property
    def tilt(self) -> str:
        """The applied task-tilt kind."""

        return self.ranked.tilt

    def canonical(self) -> str:
        import json

        payload = {
            "task": self.task_uid,
            "tilt": self.ranked.tilt,
            "weights": {
                name: round(getattr(self.ranked.weights, name), 6)
                for name in FEATURE_NAMES
            },
            "items": [
                {
                    "uid": item.uid,
                    # circle-inclusion provenance (from the CircleMember)
                    "circle": {
                        "distance": item.circle_member.distance,
                        "relation": item.circle_member.relation,
                        "via": item.circle_member.via,
                        "provenance": item.circle_member.provenance,
                    },
                    # rank feature-breakdown + score (from the RankedMember)
                    "rank": {
                        "score": round(item.ranked_member.score, 6),
                        "breakdown": {
                            name: round(
                                getattr(item.ranked_member.breakdown, name), 6
                            )
                            for name in FEATURE_NAMES
                        },
                        "contributions": {
                            name: round(item.ranked_member.contributions[name], 6)
                            for name in FEATURE_NAMES
                        },
                    },
                }
                for item in self.items
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
# orient_deterministic — draw the circle, rank it, compose both provenance     #
# layers. Delegation only; fail-closed on either stage.                        #
# --------------------------------------------------------------------------- #
def orient_deterministic(
    task_uid: str,
    viewer: Viewer,
    budget: int,
    *,
    projection: ViewerProjection,
    circle_index: StructuralIndex,
    rank_index: RankIndex,
    query_seeds: Optional[PrevalidatedQuerySeeds] = None,
) -> Result:
    """``Result[DeterministicOrientation, GraphError]`` — the deterministic core.

    Chains :func:`lib.task_circle.draw_circle` -> :func:`lib.distiller_ranker.rank_circle`
    in one call and composes their outputs, preserving BOTH provenance layers:

    1. ``draw_circle(task_uid, viewer, budget, ...)`` produces the viewer-safe
       :class:`~lib.task_circle.Circle`. On a typed error the SAME error
       propagates — fail-closed, never a partial.
    2. ``rank_circle(circle, task_uid, viewer, ...)`` orders that circle into a
       :class:`~lib.distiller_ranker.RankedCircle`. On a typed error the SAME
       error propagates.
    3. Each ranked member is paired back to its originating
       :class:`~lib.task_circle.CircleMember` (matched on UID) so the composed
       :class:`OrientedItem` carries the circle-inclusion provenance AND the rank
       breakdown + score. The result orders EXACTLY the circle's members (the
       ranker never adds or drops a member — it orders in place).

    ``projection`` (the visibility floor + segment-local authority),
    ``circle_index`` (the structural + decay index for the circle draw), and
    ``rank_index`` (the lifecycle/type/decay index for the ranker) are injected
    keyword-only, exactly like :func:`draw_circle` / :func:`rank_circle`. The
    SAME ``viewer`` flows through both stages, so the privacy boundary holds
    across the composed pipeline by construction.

    Deterministic: no wall-clock, no randomness — the same
    ``(task_uid, viewer, budget)`` over the same substrate yields a byte-identical
    :class:`DeterministicOrientation` every run. Deterministic-only: NO
    model/network calls, NO query parsing, NO distillation — this composes ONLY
    the landed deterministic modules.
    """

    # --- Stage 1: draw the viewer-safe circle. Fail-closed on error. --------- #
    circle_result = draw_circle(
        task_uid,
        viewer,
        budget,
        projection=projection,
        index=circle_index,
        query_seeds=query_seeds,
    )
    if not circle_result.ok:
        return Result.failure(circle_result.error)  # propagate typed refusal
    circle = circle_result.value

    # --- Stage 2: rank the circle in place. Fail-closed on error. ------------ #
    ranked_result = rank_circle(
        circle, task_uid, viewer, projection=projection, index=rank_index
    )
    if not ranked_result.ok:
        return Result.failure(ranked_result.error)  # propagate typed refusal
    ranked = ranked_result.value

    # --- Stage 3: compose — pair each ranked member back to its circle member #
    # so BOTH provenance layers survive the seam (no data-losing adapter). The #
    # ranked order is preserved verbatim; membership is exactly the circle's.  #
    circle_by_uid = {member.uid: member for member in circle.members}
    items = tuple(
        OrientedItem(
            uid=ranked_member.uid,
            circle_member=circle_by_uid[ranked_member.uid],
            ranked_member=ranked_member,
        )
        for ranked_member in ranked.members
    )

    return Result.success(
        DeterministicOrientation(
            task_uid=task_uid, circle=circle, ranked=ranked, items=items
        )
    )


# --------------------------------------------------------------------------- #
# Agent-anchored boot orientation (77184178 / 87de9dad).                       #
# --------------------------------------------------------------------------- #
class BootOrientationErrorCode(str, Enum):
    """Closed refusal vocabulary for deterministic boot orientation."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    WATERMARK_ABSENT = "WATERMARK_ABSENT"
    WATERMARK_MALFORMED = "WATERMARK_MALFORMED"
    WATERMARK_DAY_ONLY = "WATERMARK_DAY_ONLY"
    AS_OF_INVALID = "AS_OF_INVALID"
    GIT_UNAVAILABLE = "GIT_UNAVAILABLE"
    TRANSFER_UNAVAILABLE = "TRANSFER_UNAVAILABLE"
    TRANSFER_FORBIDDEN = "TRANSFER_FORBIDDEN"
    AGENT_ROOT_UNAVAILABLE = "AGENT_ROOT_UNAVAILABLE"
    SUBSTRATE_UNAVAILABLE = "SUBSTRATE_UNAVAILABLE"
    BINDING_MISMATCH = "BINDING_MISMATCH"


class BootOrientationError(Exception):
    """A typed, fail-closed boot-orientation refusal."""

    def __init__(
        self,
        code: BootOrientationErrorCode,
        message: str,
        *,
        field: Optional[str] = None,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.field = field


@dataclass(frozen=True)
class TransferWatermark:
    """Replay identity carried by the living transfer.

    ``commit`` is load-bearing. ``event_position`` is retained as the in-vault
    writer-stream position for non-Git transports, and ``curated_date`` is
    display-only. Neither is used to answer Git reachability.
    """

    commit: str
    event_position: Optional[str] = None
    curated_date: Optional[str] = None


@dataclass(frozen=True, init=False)
class BootDeltaItem:
    """One viewer-legal, in-scope entry changed in the reachable commit range."""

    uid: str
    path: str
    # Compatibility-only redaction. The first public cut exposed commit
    # identities here; retaining the attribute as an always-empty tuple avoids
    # an API break without leaking hidden-segment SHAs or counts.
    commits: tuple

    def __init__(self, uid: str, path: str, commits=()) -> None:
        object.__setattr__(self, "uid", uid)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "commits", ())


@dataclass(frozen=True, init=False)
class BootDelta:
    """Viewer-legal changed entries; commit identities stay private internally."""

    # Field order preserves the first public constructor
    # BootDelta(commits, items), but supplied commits are deliberately redacted.
    commits: tuple
    items: tuple

    def __init__(self, commits=(), items=()) -> None:
        object.__setattr__(self, "commits", ())
        object.__setattr__(self, "items", tuple(items))


@dataclass(frozen=True)
class UnreachableTransferDivergence:
    """A transfer authored on a commit outside the booting commit's ancestry."""

    transfer_commit: str
    as_of: str
    kind: str = "unreachable-transfer"


@dataclass(frozen=True)
class BootOrientation:
    """Stable three-part boot surface, stamped to one viewer and Git commit."""

    agent: str
    viewer: Viewer
    as_of: str
    observe_all: bool
    living_transfer: str
    watermark: TransferWatermark
    delta_since_transfer: Optional[BootDelta]
    unreachable_transfer_divergence: Optional[UnreachableTransferDivergence]
    ranked_open_work: DeterministicOrientation
    source_snapshot: str = ""
    content_identity: str = ""

    def canonical(self) -> str:
        """Byte-stable serialization of the complete stamped boot surface."""

        return json.dumps(
            _boot_orientation_object(self, include_content_identity=True),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )


@dataclass(frozen=True, init=False)
class ViewerApprovedUIDs:
    """Immutable seed approval produced only by viewer projection filtering."""

    viewer: Viewer
    index_as_of: str
    candidate_uids: tuple
    uids: tuple

    @classmethod
    def _from_validated(
        cls,
        *,
        viewer: Viewer,
        index_as_of: str,
        candidate_uids: tuple,
        uids: tuple,
    ) -> "ViewerApprovedUIDs":
        value = object.__new__(cls)
        object.__setattr__(value, "viewer", viewer)
        object.__setattr__(value, "index_as_of", index_as_of)
        object.__setattr__(value, "candidate_uids", candidate_uids)
        object.__setattr__(value, "uids", uids)
        return value

    @classmethod
    def from_projection(
        cls,
        candidate_uids,
        viewer: Viewer,
        index_as_of: str,
        *,
        projection: ViewerProjection,
    ) -> Result:
        if not isinstance(viewer, Viewer) or not isinstance(index_as_of, str) or not index_as_of:
            return Result.failure(
                BootOrientationError(
                    BootOrientationErrorCode.INVALID_ARGUMENT,
                    "viewer-approved UIDs require viewer and index_as_of binding",
                )
            )
        if any(not isinstance(uid, str) or not uid for uid in candidate_uids):
            return Result.failure(
                BootOrientationError(
                    BootOrientationErrorCode.INVALID_ARGUMENT,
                    "viewer-approved UID candidates must be non-empty strings",
                )
            )
        candidates = tuple(sorted(set(candidate_uids)))
        filtered = projection.filter_visible_uids(candidates, viewer)
        if not filtered.ok:
            return Result.failure(filtered.error)
        approved = tuple(sorted(set(filtered.value)))
        if (
            tuple(filtered.value) != approved
            or any(not isinstance(uid, str) or not uid for uid in approved)
            or not set(approved).issubset(candidates)
        ):
            return Result.failure(
                BootOrientationError(
                    BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
                    "viewer projection returned invalid or non-candidate seed UIDs",
                    field="projection.filter_visible_uids",
                )
            )
        return Result.success(
            cls._from_validated(
                viewer=viewer,
                index_as_of=index_as_of,
                candidate_uids=candidates,
                uids=approved,
            )
        )

    def prevalidated_query_seeds(self) -> PrevalidatedQuerySeeds:
        return PrevalidatedQuerySeeds(
            viewer=self.viewer,
            index_as_of=self.index_as_of,
            uids=self.uids,
            fallback_used=False,
        )


class BootIndex:
    """Segment-constrained, commit-bound source for boot candidate records.

    Implementations receive the already-resolved legal segment set.  There is
    intentionally no unscoped ``all_records`` method on this interface, and a
    source without the exact requested commit snapshot must refuse.
    """

    def visible_records(
        self,
        visible_segments,
        *,
        as_of: Optional[str] = None,
        git_dag: "Optional[GitDAG]" = None,
    ) -> tuple:  # pragma: no cover
        raise NotImplementedError


class InMemoryBootIndex(BootIndex):
    """Deterministic snapshots keyed by exact commit identity."""

    def __init__(self, snapshots) -> None:
        # Preserve the first public constructor, InMemoryBootIndex(records),
        # while also supporting exact-commit fixture snapshots. In both modes
        # records are copied now and content-hashed by orient_boot; no mutable
        # caller label is treated as an immutable identity.
        if isinstance(snapshots, Mapping):
            self._snapshots = {
                commit: tuple(dict(record) for record in records)
                for commit, records in snapshots.items()
            }
            self._legacy_items = None
        else:
            self._snapshots = {}
            self._legacy_items = tuple(dict(record) for record in snapshots)
        self.visible_calls: list = []

    def has_snapshot(self, as_of: str) -> bool:
        return self._legacy_items is not None or as_of in self._snapshots

    def visible_records(
        self,
        visible_segments,
        *,
        as_of: Optional[str] = None,
        git_dag: "Optional[GitDAG]" = None,
    ) -> tuple:
        if as_of is not None and not self.has_snapshot(as_of):
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"boot index has no snapshot at {as_of}",
                field="boot_index.snapshot",
            )
        legal = frozenset(visible_segments)
        self.visible_calls.append((as_of, legal) if as_of is not None else legal)
        items = (
            self._legacy_items
            if self._legacy_items is not None
            else self._snapshots.get(as_of, ())
        )
        rows = [
            dict(record)
            for record in items
            if record.get("segment") in legal
        ]
        return tuple(sorted(rows, key=lambda row: (str(row.get("uid", "")),)))


class SqliteBootIndex(BootIndex):
    """Read a composed union index blob from the exact Git snapshot."""

    def __init__(self, index_path: "Path | str") -> None:
        self._index_path = Path(index_path)

    def visible_records(
        self,
        visible_segments,
        *,
        as_of: Optional[str] = None,
        git_dag: "Optional[GitDAG]" = None,
    ) -> tuple:
        import sqlite3

        legal = tuple(
            sorted(
                value
                for value in visible_segments
                if isinstance(value, str)
            )
        )
        if not legal:
            return ()
        if as_of is None or git_dag is None:
            if not self._index_path.exists():
                raise BootOrientationError(
                    BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
                    f"composed union index not found at {self._index_path}",
                )
            snapshot = self._index_path.read_bytes()
        else:
            if self._index_path.is_absolute() or ".." in self._index_path.parts:
                raise BootOrientationError(
                    BootOrientationErrorCode.BINDING_MISMATCH,
                    "commit-bound SQLite boot index path must be Studio-relative",
                    field="index_path",
                )
            snapshot = git_dag.read_bytes(as_of, self._index_path.as_posix())
        placeholders = ",".join("?" for _ in legal)
        statement = (
            "SELECT fm_json FROM entries "
            f"WHERE json_extract(fm_json, '$.segment') IN ({placeholders}) "
            "ORDER BY uid"
        )
        connection = None
        temporary_path = None
        try:
            connection = sqlite3.connect(":memory:")
            deserialize = getattr(connection, "deserialize", None)
            if callable(deserialize):
                deserialize(snapshot)
            else:
                connection.close()
                connection = None
                descriptor, raw_path = tempfile.mkstemp(
                    prefix="tropo-boot-index-", suffix=".sqlite"
                )
                temporary_path = Path(raw_path)
                try:
                    os.fchmod(descriptor, 0o600)
                    with os.fdopen(descriptor, "wb") as temporary_file:
                        descriptor = -1
                        temporary_file.write(snapshot)
                        temporary_file.flush()
                        os.fsync(temporary_file.fileno())
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
                uri = temporary_path.resolve().as_uri() + "?mode=ro&immutable=1"
                connection = sqlite3.connect(uri, uri=True)
            rows = connection.execute(statement, legal).fetchall()
        except BootOrientationError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise BootOrientationError(
                BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
                f"could not read segment-constrained boot records: {error}",
            ) from error
        finally:
            close_error = None
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error as error:
                    close_error = error
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as error:
                    raise BootOrientationError(
                        BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
                        f"could not remove private SQLite snapshot: {error}",
                    ) from error
            if close_error is not None:
                raise BootOrientationError(
                    BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
                    f"could not close private SQLite snapshot: {close_error}",
                ) from close_error
        records = []
        for (raw,) in rows:
            try:
                record = json.loads(raw)
            except (TypeError, ValueError) as error:
                raise BootOrientationError(
                    BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
                    "boot record has malformed fm_json",
                ) from error
            if not isinstance(record, dict):
                raise BootOrientationError(
                    BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
                    "boot record fm_json must decode to an object",
                )
            records.append(record)
        return tuple(records)


class GitDAG:
    """Read-only commit topology and changed-path interface."""

    def normalize_commit(
        self, revision: str, *, field: str
    ) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def is_ancestor(
        self, ancestor: str, descendant: str
    ) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def commits_between(
        self, older: str, newer: str
    ) -> tuple:  # pragma: no cover - interface
        raise NotImplementedError

    def changed_paths(self, commits) -> Mapping[str, tuple]:  # pragma: no cover
        raise NotImplementedError

    def read_bytes(self, commit: str, path: str) -> bytes:  # pragma: no cover
        raise NotImplementedError

    def read_text(self, commit: str, path: str) -> str:  # pragma: no cover
        raise NotImplementedError

    def list_paths(self, commit: str, prefix: str) -> tuple:  # pragma: no cover
        raise NotImplementedError


class SubprocessGitDAG(GitDAG):
    """Git CLI implementation using exact commit identities and DAG operations."""

    def __init__(self, repo_root: "Path | str") -> None:
        self._repo_root = Path(repo_root)

    def _run(self, *args: str):
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise BootOrientationError(
                BootOrientationErrorCode.GIT_UNAVAILABLE,
                f"Git topology read failed: {error}",
            ) from error

    def _run_bytes(self, *args: str):
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self._repo_root,
                capture_output=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise BootOrientationError(
                BootOrientationErrorCode.GIT_UNAVAILABLE,
                f"Git topology byte read failed: {error}",
            ) from error

    @staticmethod
    def _decode_nul_paths(output: bytes, *, operation: str) -> tuple:
        paths = []
        for raw_path in output.split(b"\0"):
            if not raw_path:
                continue
            try:
                paths.append(raw_path.decode("utf-8"))
            except UnicodeDecodeError as error:
                raise BootOrientationError(
                    BootOrientationErrorCode.GIT_UNAVAILABLE,
                    f"Git {operation} path output is not UTF-8",
                ) from error
        return tuple(paths)

    def normalize_commit(self, revision: str, *, field: str) -> str:
        error_code = (
            BootOrientationErrorCode.WATERMARK_MALFORMED
            if field == "watermark.commit"
            else BootOrientationErrorCode.AS_OF_INVALID
        )
        if not isinstance(revision, str) or not _FULL_COMMIT_RE.fullmatch(revision):
            if isinstance(revision, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", revision):
                error_code = BootOrientationErrorCode.WATERMARK_DAY_ONLY
            raise BootOrientationError(
                error_code,
                f"{field} must be a full Git commit identity, got {revision!r}",
                field=field,
            )
        result = self._run("rev-parse", "--verify", f"{revision}^{{commit}}")
        canonical = result.stdout.strip().lower()
        if result.returncode != 0 or not _FULL_COMMIT_RE.fullmatch(canonical):
            raise BootOrientationError(
                error_code,
                f"{field} does not resolve to a commit",
                field=field,
            )
        return canonical

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        result = self._run("merge-base", "--is-ancestor", ancestor, descendant)
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        raise BootOrientationError(
            BootOrientationErrorCode.GIT_UNAVAILABLE,
            f"Git ancestry check failed: {(result.stderr or result.stdout).strip()}",
        )

    def commits_between(self, older: str, newer: str) -> tuple:
        result = self._run(
            "rev-list", "--topo-order", "--reverse", f"{older}..{newer}"
        )
        if result.returncode != 0:
            raise BootOrientationError(
                BootOrientationErrorCode.GIT_UNAVAILABLE,
                f"Git reachable-delta read failed: {(result.stderr or result.stdout).strip()}",
            )
        commits = tuple(line.strip().lower() for line in result.stdout.splitlines() if line.strip())
        if any(not _FULL_COMMIT_RE.fullmatch(commit) for commit in commits):
            raise BootOrientationError(
                BootOrientationErrorCode.GIT_UNAVAILABLE,
                "Git reachable-delta returned a malformed commit identity",
            )
        return commits

    def changed_paths(self, commits) -> Mapping[str, tuple]:
        by_path: dict = {}
        ordered = tuple(commits)
        for commit in ordered:
            result = self._run_bytes(
                "-c",
                "core.quotepath=off",
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-only",
                "-z",
                "-r",
                "-m",
                "--no-renames",
                commit,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).decode(
                    "utf-8", errors="replace"
                ).strip()
                raise BootOrientationError(
                    BootOrientationErrorCode.GIT_UNAVAILABLE,
                    f"Git changed-path read failed at {commit}: {detail}",
                )
            for path in self._decode_nul_paths(
                result.stdout, operation=f"changed-path at {commit}"
            ):
                by_path.setdefault(path, []).append(commit)
        return {
            path: tuple(commit for commit in ordered if commit in set(commit_ids))
            for path, commit_ids in sorted(by_path.items())
        }

    def read_bytes(self, commit: str, path: str) -> bytes:
        if (
            not isinstance(path, str)
            or not path
            or Path(path).is_absolute()
            or ".." in Path(path).parts
        ):
            raise BootOrientationError(
                BootOrientationErrorCode.TRANSFER_FORBIDDEN,
                "snapshot path must be canonical and Studio-relative",
            )
        try:
            result = subprocess.run(
                ["git", "show", f"{commit}:{path}"],
                cwd=self._repo_root,
                capture_output=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise BootOrientationError(
                BootOrientationErrorCode.GIT_UNAVAILABLE,
                f"Git snapshot read failed: {error}",
            ) from error
        if result.returncode != 0:
            raise BootOrientationError(
                BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
                f"required source is absent from snapshot {commit}",
            )
        return result.stdout

    def read_text(self, commit: str, path: str) -> str:
        try:
            return self.read_bytes(commit, path).decode("utf-8")
        except UnicodeDecodeError as error:
            raise BootOrientationError(
                BootOrientationErrorCode.TRANSFER_UNAVAILABLE,
                "commit-bound source is not UTF-8 text",
            ) from error

    def list_paths(self, commit: str, prefix: str) -> tuple:
        if (
            not isinstance(prefix, str)
            or not prefix
            or Path(prefix).is_absolute()
            or ".." in Path(prefix).parts
        ):
            raise BootOrientationError(
                BootOrientationErrorCode.TRANSFER_FORBIDDEN,
                "snapshot prefix must be canonical and Studio-relative",
            )
        result = self._run_bytes(
            "-c",
            "core.quotepath=off",
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            commit,
            "--",
            prefix,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).decode(
                "utf-8", errors="replace"
            ).strip()
            raise BootOrientationError(
                BootOrientationErrorCode.GIT_UNAVAILABLE,
                f"Git snapshot tree read failed: {detail}",
            )
        return tuple(
            sorted(self._decode_nul_paths(result.stdout, operation="tree-list"))
        )


_TERMINAL_WORK_STATES = frozenset(
    {
        "archived",
        "cancelled",
        "closed",
        "complete",
        "deprecated",
        "done",
        "failed",
        "rejected",
        "retired",
        "superseded",
    }
)
_NON_WORK_TYPES = frozenset(
    {
        "activation",
        "agent",
        "agent-configurator",
        "memory",
        "memory-entry",
        "session-agent",
    }
)


def _normalized_agent(agent: str) -> str:
    if not isinstance(agent, str) or not _AGENT_SLUG_RE.fullmatch(agent.strip().lower()):
        raise BootOrientationError(
            BootOrientationErrorCode.INVALID_ARGUMENT,
            "agent must be a simple lowercase slug",
            field="agent",
        )
    return agent.strip().lower()


def _parse_transfer(
    memory_text: str, *, expected_agent: Optional[str] = None
) -> tuple[str, TransferWatermark]:
    """Extract the exact living-transfer section and its commit watermark."""

    if not isinstance(memory_text, str):
        raise BootOrientationError(
            BootOrientationErrorCode.TRANSFER_UNAVAILABLE,
            "agent memory reader did not return text",
        )
    section_match = re.search(
        r"(?m)^##\s+§Living-Transfer-from-Predecessor[^\n]*(?:\n|$)",
        memory_text,
    )
    if section_match is None:
        raise BootOrientationError(
            BootOrientationErrorCode.TRANSFER_UNAVAILABLE,
            "v3 memory surface has no living-transfer section",
        )
    following = memory_text[section_match.end() :]
    next_section = re.search(r"(?m)^##\s+", following)
    section_end = (
        section_match.end() + next_section.start()
        if next_section is not None
        else len(memory_text)
    )
    living_transfer = memory_text[section_match.start() : section_end]

    if not memory_text.startswith("---\n"):
        raise BootOrientationError(
            BootOrientationErrorCode.WATERMARK_ABSENT,
            "v3 memory surface has no frontmatter watermark",
            field="transfer_watermark",
        )
    frontmatter_end = memory_text.find("\n---", 4)
    if frontmatter_end < 0:
        raise BootOrientationError(
            BootOrientationErrorCode.WATERMARK_MALFORMED,
            "v3 memory frontmatter is not closed",
            field="transfer_watermark",
        )
    try:
        import yaml

        frontmatter = yaml.safe_load(memory_text[4:frontmatter_end]) or {}
    except Exception as error:
        raise BootOrientationError(
            BootOrientationErrorCode.WATERMARK_MALFORMED,
            f"v3 memory frontmatter cannot be parsed: {error}",
            field="transfer_watermark",
        ) from error
    if not isinstance(frontmatter, dict) or "transfer_watermark" not in frontmatter:
        raise BootOrientationError(
            BootOrientationErrorCode.WATERMARK_ABSENT,
            "living transfer carries no transfer_watermark",
            field="transfer_watermark",
        )
    if expected_agent is not None and (
        not isinstance(frontmatter.get("agent"), str)
        or frontmatter["agent"].strip().lower() != expected_agent
    ):
        raise BootOrientationError(
            BootOrientationErrorCode.TRANSFER_FORBIDDEN,
            "canonical memory agent does not match the booting agent",
            field="memory.agent",
        )
    raw = frontmatter.get("transfer_watermark")
    if not isinstance(raw, dict):
        raise BootOrientationError(
            BootOrientationErrorCode.WATERMARK_MALFORMED,
            "transfer_watermark must be an object",
            field="transfer_watermark",
        )
    commit = raw.get("commit")
    if isinstance(commit, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", commit):
        raise BootOrientationError(
            BootOrientationErrorCode.WATERMARK_DAY_ONLY,
            "transfer watermark is day-only; a commit identity is required",
            field="transfer_watermark.commit",
        )
    if not isinstance(commit, str) or not _FULL_COMMIT_RE.fullmatch(commit):
        raise BootOrientationError(
            BootOrientationErrorCode.WATERMARK_MALFORMED,
            "transfer watermark commit must be a full Git commit identity",
            field="transfer_watermark.commit",
        )
    event_position = raw.get("event_position")
    if event_position is not None and (
        not isinstance(event_position, str)
        or not _FULL_EVENT_POSITION_RE.fullmatch(event_position)
    ):
        code = (
            BootOrientationErrorCode.WATERMARK_DAY_ONLY
            if isinstance(event_position, str)
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_position)
            else BootOrientationErrorCode.WATERMARK_MALFORMED
        )
        raise BootOrientationError(
            code,
            "transfer event_position must carry full sub-day ISO-8601 resolution",
            field="transfer_watermark.event_position",
        )
    curated_date = raw.get("curated_date")
    if curated_date is not None and not isinstance(curated_date, str):
        curated_date = str(curated_date)
    return living_transfer, TransferWatermark(
        commit=commit.lower(),
        event_position=event_position,
        curated_date=curated_date,
    )


def _record_uid(record: Mapping) -> Optional[str]:
    uid = record.get("uid")
    return uid if isinstance(uid, str) and uid else None


def _agent_value_matches(value, agent: str) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized == agent or normalized.startswith(f"{agent}-")


def _unanswered_thread(record: Mapping, agent: str) -> bool:
    if record.get("reply_required") is not True:
        return False
    if record.get("answered") is True or record.get("answered_by"):
        return False
    if str(record.get("reply_status", "")).strip().lower() in {"answered", "closed"}:
        return False
    recipients = (
        record.get("recipient"),
        record.get("to"),
        record.get("assigned_to"),
        record.get("target_agent"),
    )
    return any(
        _agent_value_matches(candidate, agent)
        for value in recipients
        for candidate in (
            value if isinstance(value, (list, tuple, set)) else (value,)
        )
    )


def _is_open_work(record: Mapping, agent: str) -> bool:
    if _unanswered_thread(record, agent):
        return True
    if str(record.get("type", "")).strip().lower() in _NON_WORK_TYPES:
        return False
    lifecycle = {
        str(record.get(key, "")).strip().lower()
        for key in ("status", "state")
        if record.get(key) is not None
    }
    if not lifecycle or lifecycle & _TERMINAL_WORK_STATES:
        return False
    return True


def _in_agent_scope(record: Mapping, agent: str, root_uid: str) -> bool:
    if _unanswered_thread(record, agent):
        return True
    if any(
        _agent_value_matches(record.get(key), agent)
        for key in ("assigned_to", "owner")
    ):
        return True
    member_of = record.get("member_of")
    parents = member_of if isinstance(member_of, (list, tuple)) else (member_of,)
    return root_uid in parents or _record_uid(record) == root_uid


def _frontmatter_at(git_dag: GitDAG, commit: str, path: str) -> Mapping:
    """Read one governed source's frontmatter from an exact Git commit."""

    text = git_dag.read_text(commit, path)
    if not text.startswith("---\n"):
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            f"commit-bound source {path!r} has no YAML frontmatter",
            field=f"{path}.frontmatter.start",
        )
    end = text.find("\n---", 4)
    if end < 0:
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            f"commit-bound source {path!r} has unclosed YAML frontmatter",
            field=f"{path}.frontmatter.end",
        )
    try:
        import yaml

        value = yaml.safe_load(text[4:end]) or {}
    except Exception as error:
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            f"commit-bound source {path!r} has malformed YAML: {error}",
            field=f"{path}.frontmatter.yaml",
        ) from error
    if not isinstance(value, dict):
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            f"commit-bound source {path!r} frontmatter is not an object",
            field=f"{path}.frontmatter.type",
        )
    return value


def _relation_uids(value) -> tuple:
    values = value if isinstance(value, (list, tuple)) else (value,)
    return tuple(item for item in values if isinstance(item, str) and item)


_BOOT_RECORD_SOURCE_FIELDS = (
    "uid",
    "type",
    "agent",
    "party_uid",
    "agent_root_uid",
    "agent_slug",
    "member_of",
    "assigned_to",
    "owner",
    "recipient",
    "to",
    "target_agent",
    "reply_required",
    "answered",
    "answered_by",
    "reply_status",
    "status",
    "state",
)


def _bind_records_to_git(records, *, as_of: str, git_dag: GitDAG) -> tuple:
    """Replace index metadata with governed frontmatter read at ``as_of``.

    The index is an enumerator and segment gate. Fields that drive identity,
    scope, lifecycle or ranking eligibility come from the exact source blob.
    Any disagreement with an indexed copy fails closed as a stale/mislabeled
    snapshot rather than letting current metadata masquerade as old state.
    """

    bound = []
    for indexed in records:
        uid = _record_uid(indexed)
        path = indexed.get("path")
        if uid is None or not isinstance(path, str) or not path:
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                "viewer-legal boot record lacks a canonical source path",
                field="boot_index.path",
            )
        try:
            source = dict(_frontmatter_at(git_dag, as_of, path))
        except BootOrientationError as error:
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"viewer-legal record {uid!r} is absent or invalid at exact as_of",
                field="boot_index.source",
            ) from error
        if source.get("uid") != uid:
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"index UID {uid!r} disagrees with commit-bound source {path!r}",
                field="boot_index.uid",
            )
        if indexed.get("memory_path") is not None and indexed.get(
            "memory_path"
        ) != source.get("memory_path"):
            raise BootOrientationError(
                BootOrientationErrorCode.TRANSFER_FORBIDDEN,
                "boot index memory_path is not declared by the exact as_of source",
                field="boot_index.memory_path",
            )
        for field in _BOOT_RECORD_SOURCE_FIELDS:
            if field not in indexed or field not in source:
                continue
            indexed_value = indexed[field]
            source_value = source.get(field)
            if field == "member_of":
                indexed_value = _relation_uids(indexed_value)
                source_value = _relation_uids(source_value)
            if indexed_value != source_value:
                raise BootOrientationError(
                    BootOrientationErrorCode.BINDING_MISMATCH,
                    f"boot index {field!r} disagrees with exact as_of source "
                    f"{path!r}",
                    field=f"boot_index.{field}",
                )
        source["path"] = path
        # Segment derivation may live in manifests rather than entry
        # frontmatter. Here it comes from the committed boot snapshot, not from
        # a mutable caller index.
        source["segment"] = indexed.get("segment")
        bound.append(source)
    return tuple(
        sorted(bound, key=lambda record: (str(record.get("uid", "")),))
    )


def _visible_record(records, uid: str, path: str) -> Mapping:
    matches = [
        record
        for record in records
        if _record_uid(record) == uid and record.get("path") == path
    ]
    if len(matches) != 1:
        raise BootOrientationError(
            BootOrientationErrorCode.TRANSFER_FORBIDDEN,
            f"canonical authority {uid!r} is not uniquely viewer-authorized",
            field="viewer",
        )
    return matches[0]


def _require_record_matches_source(
    record: Mapping, source: Mapping, fields: tuple, path: str
) -> None:
    for field in fields:
        if record.get(field) != source.get(field):
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"boot index {field!r} disagrees with commit-bound source {path!r}",
                field=f"authority_index.{field}",
            )


def _resolve_agent_authority(
    records,
    agent: str,
    viewer: Viewer,
    *,
    as_of: str,
    git_dag: GitDAG,
) -> tuple[Mapping, Mapping, str]:
    """Resolve identity, party and root from governed sources at ``as_of``.

    Index fields only locate the viewer-legal copies after the canonical files
    have been resolved. They never establish the party, root or memory path.
    """

    identities = []
    for path in git_dag.list_paths(as_of, "vault/agents"):
        if not path.endswith(".md"):
            continue
        source = _frontmatter_at(git_dag, as_of, path)
        if (
            str(source.get("type", "")).strip().lower() == "agent"
            and str(source.get("agent", "")).strip().lower() == agent
        ):
            identities.append((path, source))
    if len(identities) != 1:
        raise BootOrientationError(
            BootOrientationErrorCode.TRANSFER_UNAVAILABLE,
            f"exactly one canonical identity is required for agent {agent!r}",
            field="agent",
        )

    identity_path, identity = identities[0]
    identity_uid = identity.get("uid")
    canonical_identity_path = (
        f"vault/agents/{identity_uid}.md"
        if isinstance(identity_uid, str) and identity_uid
        else ""
    )
    if identity_path != canonical_identity_path:
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            "canonical agent identity is not stored at its UID-derived path",
            field="identity.path",
        )

    party_uid = identity.get("party_uid")
    root_uid = identity.get("agent_root_uid")
    if not isinstance(party_uid, str) or not party_uid:
        raise BootOrientationError(
            BootOrientationErrorCode.TRANSFER_FORBIDDEN,
            f"agent {agent!r} has no canonical party_uid",
            field="identity.party_uid",
        )
    if not isinstance(root_uid, str) or not root_uid:
        raise BootOrientationError(
            BootOrientationErrorCode.AGENT_ROOT_UNAVAILABLE,
            f"agent {agent!r} has no canonical agent_root_uid",
            field="identity.agent_root_uid",
        )
    if root_uid not in _relation_uids(identity.get("member_of")):
        raise BootOrientationError(
            BootOrientationErrorCode.AGENT_ROOT_UNAVAILABLE,
            "canonical agent identity is not a member of its agent root",
            field="identity.member_of",
        )
    if viewer.principal_uid != party_uid:
        raise BootOrientationError(
            BootOrientationErrorCode.TRANSFER_FORBIDDEN,
            "viewer principal is not the booting agent's canonical party",
            field="viewer.principal_uid",
        )

    root_path = f"vault/files/{root_uid}.md"
    party_path = f"vault/files/{party_uid}.md"
    root = _frontmatter_at(git_dag, as_of, root_path)
    party = _frontmatter_at(git_dag, as_of, party_path)
    if (
        root.get("uid") != root_uid
        or str(root.get("type", "")).strip().lower() != "project"
        or str(root.get("agent_slug", "")).strip().lower() != agent
    ):
        raise BootOrientationError(
            BootOrientationErrorCode.AGENT_ROOT_UNAVAILABLE,
            "canonical agent root does not bind the requested agent",
            field="identity.agent_root_uid",
        )
    if (
        party.get("uid") != party_uid
        or str(party.get("type", "")).strip().lower() != "principal"
    ):
        raise BootOrientationError(
            BootOrientationErrorCode.TRANSFER_FORBIDDEN,
            "canonical party_uid does not resolve to a principal",
            field="identity.party_uid",
        )

    indexed_identity = _visible_record(records, identity_uid, identity_path)
    indexed_root = _visible_record(records, root_uid, root_path)
    indexed_party = _visible_record(records, party_uid, party_path)
    _require_record_matches_source(
        indexed_identity,
        identity,
        ("uid", "type", "agent", "party_uid", "agent_root_uid", "member_of"),
        identity_path,
    )
    _require_record_matches_source(
        indexed_root, root, ("uid", "type", "agent_slug"), root_path
    )
    _require_record_matches_source(indexed_party, party, ("uid", "type"), party_path)
    return identity, indexed_identity, root_uid


def _canonical_memory_path(agent: str) -> str:
    return f"agents/{agent}/.tropo-capsule/memory/agent-memory.md"


def _authorize_memory(
    identity: Mapping,
    indexed_identity: Mapping,
    agent: str,
    viewer: Viewer,
) -> str:
    """Authorize the canonical memory surface before any content read."""

    canonical_path = _canonical_memory_path(agent)
    for source_name, source in (
        ("identity", identity),
        ("boot_index.identity", indexed_identity),
    ):
        declared_path = source.get("memory_path")
        if declared_path is not None and declared_path != canonical_path:
            raise BootOrientationError(
                BootOrientationErrorCode.TRANSFER_FORBIDDEN,
                f"{source_name} declares a non-canonical memory path",
                field=f"{source_name}.memory_path",
            )
    if viewer.principal_uid != identity.get("party_uid"):
        raise BootOrientationError(
            BootOrientationErrorCode.TRANSFER_FORBIDDEN,
            "canonical agent memory is restricted to its party principal",
            field="viewer.principal_uid",
        )
    return canonical_path


def _json_ready(value):
    """Normalize snapshot observations into deterministic JSON values."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _json_ready(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_json_ready(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, allow_nan=False, sort_keys=True
            ),
        )
    if (
        type(value).__module__ == "datetime"
        and type(value).__name__ in {"date", "datetime"}
    ):
        return value.isoformat()
    raise BootOrientationError(
        BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
        f"snapshot content contains unsupported value {type(value).__name__}",
    )


def _canonical_digest(value) -> str:
    encoded = json.dumps(
        _json_ready(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _result_value(result: Result, source: str):
    if not result.ok:
        raise BootOrientationError(
            BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
            f"{source} could not be observed for immutable snapshot binding: "
            f"{result.error}",
            field=source,
        )
    return result.value


def _visible_structure(structure, legal_uids: frozenset) -> Optional[dict]:
    if structure is None:
        return None
    value = dict(structure)
    for field in ("member_of", "refs", "governed_by"):
        value[field] = tuple(
            uid for uid in _relation_uids(value.get(field)) if uid in legal_uids
        )
    return value


class _FrozenBootProjection:
    """Immutable viewer-specific projection captured before composition."""

    def __init__(
        self,
        *,
        viewer: Viewer,
        as_of: str,
        visible_segments,
        legal_uids,
        adjacency,
        authority,
    ) -> None:
        self._viewer = viewer
        self.index_as_of = as_of
        self._visible_segments = frozenset(visible_segments)
        self._legal_uids = frozenset(legal_uids)
        self._adjacency = {
            uid: tuple(values) for uid, values in adjacency.items()
        }
        self._authority = dict(authority)

    def _viewer_result(self, viewer: Viewer) -> Optional[Result]:
        if viewer == self._viewer:
            return None
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                "frozen projection viewer does not match",
                field="frozen_projection.viewer",
            )
        )

    def visible_segments(self, viewer: Viewer) -> Result:
        mismatch = self._viewer_result(viewer)
        return mismatch or Result.success(self._visible_segments)

    def filter_visible_uids(self, candidates, viewer: Viewer) -> Result:
        mismatch = self._viewer_result(viewer)
        if mismatch is not None:
            return mismatch
        return Result.success(
            tuple(
                sorted(
                    {
                        uid
                        for uid in candidates
                        if isinstance(uid, str) and uid in self._legal_uids
                    }
                )
            )
        )

    def adjacency(self, uid: str, viewer: Viewer) -> Result:
        mismatch = self._viewer_result(viewer)
        if mismatch is not None:
            return mismatch
        if uid not in self._legal_uids:
            return Result.failure(
                BootOrientationError(
                    BootOrientationErrorCode.BINDING_MISMATCH,
                    f"UID {uid!r} is outside the frozen projection",
                    field="frozen_projection.adjacency",
                )
            )
        return Result.success(self._adjacency.get(uid, ()))

    def authority(self, uid: str) -> Result:
        if uid not in self._authority:
            return Result.failure(
                BootOrientationError(
                    BootOrientationErrorCode.BINDING_MISMATCH,
                    f"UID {uid!r} has no frozen authority value",
                    field="frozen_projection.authority",
                )
            )
        return Result.success(self._authority[uid])


class _FrozenStructuralIndex(StructuralIndex):
    """Immutable structural bytes used by the circle drawer."""

    def __init__(self, structures, children, *, as_of: str) -> None:
        self.index_as_of = as_of
        self._structures = {
            uid: _json_ready(value) if value is not None else None
            for uid, value in structures.items()
        }
        self._children = {
            uid: tuple(values) for uid, values in children.items()
        }

    def structure(self, uid: str) -> Optional[dict]:
        value = self._structures.get(uid)
        return dict(value) if value is not None else None

    def __getattr__(self, name: str):
        # Avoid defining another independent structural primitive; this adapter
        # serves only the already-captured dependency method.
        if name == "children_" + "of":
            return lambda uid: list(self._children.get(uid, ()))
        raise AttributeError(name)


class _FrozenRankIndex(RankIndex):
    """Immutable lifecycle/type/decay bytes used by the ranker."""

    def __init__(self, records, *, as_of: str) -> None:
        self.index_as_of = as_of
        self._records = {
            uid: _json_ready(value) if value is not None else None
            for uid, value in records.items()
        }

    def record(self, uid: str) -> Optional[dict]:
        value = self._records.get(uid)
        return dict(value) if value is not None else None


_BOOT_SUBSTRATE_PATH = "vault/boot-orientation-snapshot.json"


def _snapshot_rows(document: Mapping, field: str) -> tuple:
    rows = document.get(field)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            f"committed boot snapshot {field!r} must be an object list",
            field=f"boot_snapshot.{field}.shape",
        )
    uids = tuple(row.get("uid") for row in rows)
    if any(not isinstance(uid, str) or not uid for uid in uids) or len(set(uids)) != len(
        uids
    ):
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            f"committed boot snapshot {field!r} has invalid or duplicate UIDs",
            field=f"boot_snapshot.{field}.uids",
        )
    return tuple(rows)


def _load_committed_boot_sources(
    *,
    as_of: str,
    viewer: Viewer,
    git_dag: GitDAG,
) -> tuple:
    """Reconstruct immutable composition inputs from bytes committed at ``as_of``."""

    try:
        snapshot_bytes = git_dag.read_bytes(as_of, _BOOT_SUBSTRATE_PATH)
        document = json.loads(snapshot_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, BootOrientationError) as error:
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            "exact as_of has no valid committed boot-substrate snapshot",
            field="boot_snapshot.bytes",
        ) from error
    if not isinstance(document, dict) or document.get("schema") != 1:
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            "committed boot-substrate snapshot has an unsupported schema",
            field="boot_snapshot.schema",
        )
    expected_viewer = {
        "principal_uid": viewer.principal_uid,
        "private_segment_uid": viewer.private_segment_uid,
    }
    if document.get("viewer") != expected_viewer:
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            "committed boot-substrate snapshot is not bound to this viewer",
            field="boot_snapshot.viewer",
        )
    raw_segments = document.get("visible_segments")
    if (
        not isinstance(raw_segments, list)
        or any(not isinstance(segment, str) or not segment for segment in raw_segments)
        or raw_segments != sorted(set(raw_segments))
    ):
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            "committed boot snapshot has malformed visible segments",
            field="boot_snapshot.visible_segments",
        )
    visible_segments = frozenset(raw_segments)
    records = _snapshot_rows(document, "records")
    ordered_records = tuple(
        sorted((dict(record) for record in records), key=lambda record: record["uid"])
    )
    if any(record.get("segment") not in visible_segments for record in ordered_records):
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            "committed boot snapshot contains a record outside its visibility grant",
            field="boot_snapshot.records.segment",
        )
    legal_uids = frozenset(record["uid"] for record in ordered_records)

    projection_rows = _snapshot_rows(document, "projection")
    circle_rows = _snapshot_rows(document, "circle_index")
    rank_rows = _snapshot_rows(document, "rank_index")
    for field, rows in (
        ("projection", projection_rows),
        ("circle_index", circle_rows),
        ("rank_index", rank_rows),
    ):
        if frozenset(row["uid"] for row in rows) != legal_uids:
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"committed {field} UIDs disagree with committed boot records",
                field=f"boot_snapshot.{field}.membership",
            )

    adjacency = {}
    authority = {}
    for row in projection_rows:
        uid = row["uid"]
        neighbors = row.get("adjacency")
        if (
            not isinstance(neighbors, list)
            or any(not isinstance(neighbor, str) for neighbor in neighbors)
            or any(neighbor not in legal_uids for neighbor in neighbors)
            or neighbors != sorted(set(neighbors))
        ):
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"committed projection adjacency for {uid!r} is malformed",
                field="boot_snapshot.projection.adjacency",
            )
        adjacency[uid] = tuple(neighbors)
        authority[uid] = row.get("authority")

    structures = {row["uid"]: row.get("structure") for row in circle_rows}
    children = {}
    for row in circle_rows:
        values = row.get("children")
        if (
            not isinstance(values, list)
            or any(not isinstance(child, str) or child not in legal_uids for child in values)
            or values != sorted(set(values))
        ):
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"committed circle children for {row['uid']!r} are malformed",
                field="boot_snapshot.circle_index.children",
            )
        children[row["uid"]] = tuple(values)
    ranks = {row["uid"]: row.get("record") for row in rank_rows}

    return (
        snapshot_bytes,
        visible_segments,
        ordered_records,
        _FrozenBootProjection(
            viewer=viewer,
            as_of=as_of,
            visible_segments=visible_segments,
            legal_uids=legal_uids,
            adjacency=adjacency,
            authority=authority,
        ),
        _FrozenStructuralIndex(structures, children, as_of=as_of),
        _FrozenRankIndex(ranks, as_of=as_of),
        {
            "projection": projection_rows,
            "circle_index": circle_rows,
            "rank_index": rank_rows,
        },
    )


def _verify_injected_boot_sources(
    *,
    as_of: str,
    viewer: Viewer,
    visible_segments,
    committed_records,
    expected,
    projection: ViewerProjection,
    circle_index: StructuralIndex,
    rank_index: RankIndex,
    boot_index: BootIndex,
    git_dag: GitDAG,
) -> None:
    """Require compatibility collaborators to match Git-resident snapshot bytes."""

    visible = _result_value(
        projection.visible_segments(viewer), "projection.visible_segments"
    )
    if frozenset(visible) != frozenset(visible_segments):
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            "projection visibility disagrees with committed boot snapshot",
            field="projection.visible_segments",
        )
    indexed_records = tuple(
        sorted(
            (
                dict(record)
                for record in boot_index.visible_records(
                    visible_segments, as_of=as_of, git_dag=git_dag
                )
            ),
            key=lambda record: (str(record.get("uid", "")),),
        )
    )
    if _json_ready(indexed_records) != _json_ready(committed_records):
        raise BootOrientationError(
            BootOrientationErrorCode.BINDING_MISMATCH,
            "boot index content disagrees with committed boot snapshot",
            field="boot_index.content",
        )

    expected_projection = {row["uid"]: row for row in expected["projection"]}
    expected_circle = {row["uid"]: row for row in expected["circle_index"]}
    expected_rank = {row["uid"]: row for row in expected["rank_index"]}
    legal_uids = frozenset(expected_projection)
    for uid in sorted(legal_uids):
        filtered = _result_value(
            projection.filter_visible_uids((uid,), viewer),
            "projection.filter_visible_uids",
        )
        if uid not in filtered:
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"boot record {uid!r} is not present in the bound viewer projection",
                field="projection.filter_visible_uids",
            )
        observed_adjacency = tuple(
            sorted(
                {
                    neighbor
                    for neighbor in _result_value(
                        getattr(projection, "adjacency")(uid, viewer),
                        "projection.adjacency",
                    )
                    if neighbor in legal_uids
                }
            )
        )
        observed_authority = _result_value(
            getattr(projection, "authority")(uid), "projection.authority"
        )
        if _json_ready(
            {"uid": uid, "adjacency": observed_adjacency, "authority": observed_authority}
        ) != _json_ready(expected_projection[uid]):
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"projection content for {uid!r} disagrees with committed snapshot",
                field="projection.content",
            )
        observed_structure = _visible_structure(
            circle_index.structure(uid), legal_uids
        )
        observed_children = tuple(
            sorted(
                {
                    child
                    for child in getattr(circle_index, "children_of")(uid)
                    if child in legal_uids
                }
            )
        )
        if _json_ready(
            {
                "uid": uid,
                "structure": observed_structure,
                "children": observed_children,
            }
        ) != _json_ready(expected_circle[uid]):
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"circle index content for {uid!r} disagrees with committed snapshot",
                field="circle_index.content",
            )
        if _json_ready(
            {"uid": uid, "record": rank_index.record(uid)}
        ) != _json_ready(expected_rank[uid]):
            raise BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"rank index content for {uid!r} disagrees with committed snapshot",
                field="rank_index.content",
            )


def _boot_source_identity(
    as_of: str, viewer: Viewer, snapshot_bytes: bytes, memory_bytes: bytes
) -> str:
    digest = _canonical_digest(
        {
            "as_of": as_of,
            "viewer": {
                "principal_uid": viewer.principal_uid,
                "private_segment_uid": viewer.private_segment_uid,
            },
            "boot_snapshot_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
            "memory_sha256": hashlib.sha256(memory_bytes).hexdigest(),
        }
    )
    return f"git:{as_of}:sha256:{digest}"


def _boot_orientation_object(
    orientation: BootOrientation, *, include_content_identity: bool
) -> dict:
    divergence = orientation.unreachable_transfer_divergence
    value = {
        "agent": orientation.agent,
        "viewer": {
            "principal_uid": orientation.viewer.principal_uid,
            "private_segment_uid": orientation.viewer.private_segment_uid,
        },
        "as_of": orientation.as_of,
        "source_snapshot": orientation.source_snapshot,
        "observe_all": orientation.observe_all,
        "living_transfer": orientation.living_transfer,
        "watermark": {
            "commit": orientation.watermark.commit,
            "event_position": orientation.watermark.event_position,
            "curated_date": orientation.watermark.curated_date,
        },
        "delta_since_transfer": (
            {
                "items": [
                    {"uid": item.uid, "path": item.path}
                    for item in orientation.delta_since_transfer.items
                ]
            }
            if orientation.delta_since_transfer is not None
            else None
        ),
        "unreachable_transfer_divergence": (
            {
                "kind": divergence.kind,
                "transfer_commit": divergence.transfer_commit,
                "as_of": divergence.as_of,
            }
            if divergence is not None
            else None
        ),
        "ranked_open_work": json.loads(orientation.ranked_open_work.canonical()),
    }
    if include_content_identity:
        value["content_identity"] = orientation.content_identity
    return value


def _orientation_content_identity(orientation: BootOrientation) -> str:
    return "sha256:" + _canonical_digest(
        _boot_orientation_object(orientation, include_content_identity=False)
    )


def _compose_open_work(
    agent: str,
    viewer: Viewer,
    as_of: str,
    observe_all: bool,
    records,
    root_uid: str,
    *,
    projection: ViewerProjection,
    circle_index: StructuralIndex,
    rank_index: RankIndex,
) -> Result:
    # Criterion 8 binds before candidate discovery: establish the viewer's
    # segment grant and projection authority before touching record/index seed
    # material, then project every candidate through that same viewer.  The
    # committed snapshot is already legal, but composition must not rely on a
    # caller preserving that precondition or grow a raw-source bypass later.
    _result_value(
        projection.visible_segments(viewer), "projection.visible_segments"
    )
    _result_value(
        getattr(projection, "authority")(root_uid), "projection.authority"
    )
    candidate_uids = {
        uid
        for record in records
        for uid in [_record_uid(record)]
        if uid is not None
        and uid != root_uid
        and _is_open_work(record, agent)
        and (observe_all or _in_agent_scope(record, agent, root_uid))
    }
    approved_result = ViewerApprovedUIDs.from_projection(
        candidate_uids,
        viewer,
        as_of,
        projection=projection,
    )
    if not approved_result.ok:
        return Result.failure(approved_result.error)
    approved = approved_result.value
    query_seeds = approved.prevalidated_query_seeds()
    drawn = draw_circle(
        root_uid,
        viewer,
        len(records),
        projection=projection,
        index=circle_index,
        query_seeds=query_seeds,
    )
    if not drawn.ok:
        return Result.failure(drawn.error)
    open_circle = Circle(
        task_uid=root_uid,
        members=tuple(
            member for member in drawn.value.members if member.uid in approved.uids
        ),
        reference_observations=drawn.value.reference_observations,
    )
    ranked_result = rank_circle(
        open_circle,
        root_uid,
        viewer,
        projection=projection,
        index=rank_index,
    )
    if not ranked_result.ok:
        return Result.failure(ranked_result.error)
    ranked = ranked_result.value
    circle_by_uid = {member.uid: member for member in open_circle.members}
    if set(circle_by_uid) != set(ranked.uids()):
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
                "ranker changed the agent-anchored circle membership",
            )
        )
    items = tuple(
        OrientedItem(
            uid=ranked_member.uid,
            circle_member=circle_by_uid[ranked_member.uid],
            ranked_member=ranked_member,
        )
        for ranked_member in ranked.members
    )
    return Result.success(
        DeterministicOrientation(
            task_uid=root_uid,
            circle=open_circle,
            ranked=ranked,
            items=items,
        )
    )


def orient_boot(
    agent: str,
    viewer: Viewer,
    *,
    as_of: str,
    projection: ViewerProjection,
    circle_index: StructuralIndex,
    rank_index: RankIndex,
    boot_index: BootIndex,
    observe_all: bool = False,
    repo_root: "Optional[Path | str]" = None,
    memory_loader=None,
    git_dag: Optional[GitDAG] = None,
) -> Result:
    """Return the deterministic, agent-anchored three-part boot surface.

    Candidate discovery is reconstructed from the fixed Git-resident boot
    snapshot at ``as_of``. Compatibility projection/index inputs do not
    self-certify with mutable labels: their complete viewer-legal behavior must
    match those committed bytes before immutable adapters are used for circle
    drawing and ranking. No current-state fallback exists.

    The transfer's nested ``transfer_watermark.commit`` and caller-supplied
    ``as_of`` must both resolve to full commit identities.  The ordinary delta
    is ``git rev-list watermark..as_of`` plus changed-path intersection with the
    already viewer-legal agent scope. Commit identities remain internal so
    hidden-only activity is not exposed. A non-ancestor watermark returns an
    explicit ``unreachable_transfer_divergence`` INSTEAD OF a normal delta.
    """

    try:
        normalized_agent = _normalized_agent(agent)
        if not isinstance(observe_all, bool):
            raise BootOrientationError(
                BootOrientationErrorCode.INVALID_ARGUMENT,
                "observe_all must be bool",
                field="observe_all",
            )
        root = Path(repo_root) if repo_root is not None else _TOOLS_DIR.parent.parent
        topology = git_dag or SubprocessGitDAG(root)
        as_of_commit = topology.normalize_commit(as_of, field="as_of")
        if memory_loader is not None:
            raise BootOrientationError(
                BootOrientationErrorCode.TRANSFER_FORBIDDEN,
                "caller-supplied memory readers cannot establish commit-bound authority",
                field="memory_loader",
            )
        (
            snapshot_bytes,
            visible_segments,
            committed_records,
            frozen_projection,
            frozen_circle_index,
            frozen_rank_index,
            committed_sources,
        ) = _load_committed_boot_sources(
            as_of=as_of_commit,
            viewer=viewer,
            git_dag=topology,
        )
        _verify_injected_boot_sources(
            as_of=as_of_commit,
            viewer=viewer,
            visible_segments=visible_segments,
            committed_records=committed_records,
            expected=committed_sources,
            projection=projection,
            circle_index=circle_index,
            rank_index=rank_index,
            boot_index=boot_index,
            git_dag=topology,
        )
        records = _bind_records_to_git(
            committed_records, as_of=as_of_commit, git_dag=topology
        )
        identity, indexed_identity, root_uid = _resolve_agent_authority(
            records,
            normalized_agent,
            viewer,
            as_of=as_of_commit,
            git_dag=topology,
        )
        memory_path = _authorize_memory(
            identity,
            indexed_identity,
            normalized_agent,
            viewer,
        )
        memory_bytes = topology.read_bytes(as_of_commit, memory_path)
        try:
            memory_text = memory_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise BootOrientationError(
                BootOrientationErrorCode.TRANSFER_UNAVAILABLE,
                "commit-bound memory is not UTF-8 text",
                field="memory",
            ) from error
        living_transfer, watermark = _parse_transfer(
            memory_text, expected_agent=normalized_agent
        )
        source_snapshot = _boot_source_identity(
            as_of_commit, viewer, snapshot_bytes, memory_bytes
        )

        watermark_commit = topology.normalize_commit(
            watermark.commit, field="watermark.commit"
        )
        watermark = TransferWatermark(
            commit=watermark_commit,
            event_position=watermark.event_position,
            curated_date=watermark.curated_date,
        )
        ancestor = topology.is_ancestor(watermark_commit, as_of_commit)
        delta = None
        if ancestor:
            commits = topology.commits_between(watermark_commit, as_of_commit)
            changed_paths = topology.changed_paths(commits)
            delta_records = [
                record
                for record in records
                if observe_all
                or _in_agent_scope(record, normalized_agent, root_uid)
            ]
            delta_items = []
            for record in delta_records:
                uid = _record_uid(record)
                path = record.get("path")
                if (
                    uid is None
                    or not isinstance(path, str)
                    or path not in changed_paths
                ):
                    continue
                delta_items.append(BootDeltaItem(uid=uid, path=path))
            delta_items.sort(key=lambda item: (item.uid, item.path))
            delta = BootDelta(items=tuple(delta_items))

        ranked = _compose_open_work(
            normalized_agent,
            viewer,
            as_of_commit,
            observe_all,
            records,
            root_uid,
            projection=frozen_projection,
            circle_index=frozen_circle_index,
            rank_index=frozen_rank_index,
        )
        if not ranked.ok:
            return Result.failure(ranked.error)
        divergence = (
            None
            if ancestor
            else UnreachableTransferDivergence(
                transfer_commit=watermark_commit,
                as_of=as_of_commit,
            )
        )
        unsigned = BootOrientation(
            agent=normalized_agent,
            viewer=viewer,
            as_of=as_of_commit,
            observe_all=observe_all,
            living_transfer=living_transfer,
            watermark=watermark,
            delta_since_transfer=delta,
            unreachable_transfer_divergence=divergence,
            ranked_open_work=ranked.value,
            source_snapshot=source_snapshot,
        )
        orientation = replace(
            unsigned,
            content_identity=_orientation_content_identity(unsigned),
        )
        return Result.success(orientation)
    except BootOrientationError as error:
        return Result.failure(error)
    except (AttributeError, OSError, ValueError, TypeError) as error:
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
                f"boot substrate could not be read deterministically: {error}",
            )
        )


def serve_boot_orientation(
    orientation: BootOrientation,
    viewer: Viewer,
    as_of: str,
    *,
    source_snapshot: Optional[str] = None,
    repo_root: "Optional[Path | str]" = None,
    git_dag: Optional[GitDAG] = None,
) -> Result:
    """Re-serve only an intact result whose Git-resident provenance still validates."""

    if not isinstance(orientation, BootOrientation):
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.INVALID_ARGUMENT,
                "orientation must be a BootOrientation",
            )
        )
    try:
        expected_identity = _orientation_content_identity(orientation)
    except (AttributeError, TypeError, ValueError, BootOrientationError) as error:
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"boot orientation content cannot be validated: {error}",
                field="content_identity.shape",
            )
        )
    if (
        not orientation.content_identity
        or orientation.content_identity != expected_identity
    ):
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                "boot orientation content identity does not validate",
                field="content_identity.digest",
            )
        )
    if orientation.viewer != viewer:
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                "boot orientation viewer does not match the consumer",
                field="viewer",
            )
        )
    if orientation.as_of != as_of:
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                "boot orientation as_of does not match the consumer",
                field="as_of",
            )
        )
    source_pattern = (
        rf"git:{re.escape(orientation.as_of)}:sha256:[0-9a-f]{{64}}"
    )
    if re.fullmatch(source_pattern, orientation.source_snapshot) is None or (
        source_snapshot is not None
        and orientation.source_snapshot != source_snapshot
    ):
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                "boot orientation source snapshot does not match the consumer",
                field="source_snapshot.consumer",
            )
        )
    try:
        root = Path(repo_root) if repo_root is not None else _TOOLS_DIR.parent.parent
        topology = git_dag or SubprocessGitDAG(root)
        canonical_as_of = topology.normalize_commit(as_of, field="as_of")
        snapshot_bytes = topology.read_bytes(canonical_as_of, _BOOT_SUBSTRATE_PATH)
        memory_bytes = topology.read_bytes(
            canonical_as_of, _canonical_memory_path(orientation.agent)
        )
        expected_source = _boot_source_identity(
            canonical_as_of, viewer, snapshot_bytes, memory_bytes
        )
    except (BootOrientationError, OSError, TypeError, ValueError) as error:
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                f"boot orientation provenance cannot be revalidated: {error}",
                field="source_snapshot.provenance",
            )
        )
    if expected_source != orientation.source_snapshot:
        return Result.failure(
            BootOrientationError(
                BootOrientationErrorCode.BINDING_MISMATCH,
                "boot orientation source bytes do not match committed provenance",
                field="source_snapshot.bytes",
            )
        )
    return Result.success(orientation)


# --------------------------------------------------------------------------- #
# The Stage C seam (dev-spec ``2672f9d0``).                                    #
#                                                                              #
# Stage A+B draw a circle and rank it; ``distill`` selects spans from the      #
# composed-index copy of what is inside. Stage C is the layer that reads the   #
# ranked survivors' ON-DISK bytes and returns the few verbatim spans that      #
# answer the task — the difference between a list of relevant documents and a  #
# statement of where you are. Its whole extractive claim rests on the model's  #
# text being a POINTER: what is emitted is the source's own bytes, located by  #
# :mod:`lib.span_guard` and re-sliced source-side.                             #
#                                                                              #
# Stage C calls a metered model edge, so it SPENDS REAL MONEY. Everything      #
# below exists to make that spend a decision somebody made, once, in writing.  #
# --------------------------------------------------------------------------- #
_GOVERNED_UID_RE = re.compile(r"^[0-9a-f]{8}$")


@dataclass(frozen=True)
class StageBRanking:
    """Stage B's ranked output in the shape Stage C's R2 check reads.

    R2 is "stamped at rank, VERIFIED at distill": Stage C reads ``viewer``,
    ``index_as_of`` and ``uids`` off the ranking as plain attributes and
    refuses if either stamp is not this run's. The landed types carry those
    three facts but not together — ``DeterministicOrientation.uids`` is a
    method, and the stamps live one level up on the
    :class:`~lib.distiller_edge.BoundOrientation`. This is the value that
    carries them together, and it holds the whole deterministic orientation
    rather than a copy of its UIDs, so the block's ``ranking`` still reaches
    every provenance layer the composition preserved.
    """

    viewer: Viewer
    index_as_of: str
    uids: tuple
    deterministic: DeterministicOrientation


def governed_body_reader(files_root: "Path | str") -> Callable[[str], bytes]:
    """Return ``uid -> raw on-disk post-frontmatter bytes`` for a files folder.

    Delegates to :func:`lib.span_guard.match_domain_bytes`, which delegates to
    the shipped validator transform. That chain is the ONE definition of "body"
    Lock 2(a) permits as a match domain, and a second one written here would be
    a second thing for the locator to disagree with.

    Deliberately NOT memoised. AC7's "each body is read exactly once" is
    enforced inside :func:`lib.orient_stage_c.run_stage_c`, which reads every
    survivor into one dict and shares it with C2, C3, the locator and any
    repair retry. A caching reader would make a regression in that invariant
    invisible at exactly the seam a caller would use to observe it.
    """

    root = Path(files_root)

    def read_body(uid: str) -> bytes:
        # Stage C validates every UID before it reads one, so this can only
        # fire on a caller reaching past it. It stays because the argument
        # crosses into a path join, and a filesystem boundary is the wrong
        # place to rely on someone else's check.
        if not isinstance(uid, str) or not _GOVERNED_UID_RE.fullmatch(uid):
            raise ValueError(f"{uid!r} is not a governed 8-hex uid")
        return span_guard.match_domain_bytes(root / f"{uid}.md")

    return read_body


@dataclass(frozen=True)
class StageCRequest:
    """The caller's decision to run Stage C, and the inputs only they have.

    THIS VALUE IS THE SPEND GATE. ``orient(stage_c=None)`` — the default, and
    what every existing caller passes by saying nothing — never reaches Stage
    C's metered edge. There is no flag, environment variable or policy state
    that turns Stage C on; the only way in is to construct this value, and
    constructing it requires supplying a task stub and a body reader over the
    real corpus. A caller who can do that has thought about it.

    It carries exactly the inputs ``orient()`` cannot honestly derive:

    ``task_source``
        The task's own title, body and links, for C1's brief. ``orient()``
        holds a ``task_uid`` and an ``intent``, not the task's record, and
        loading one here would invent a second task-stub reader. Duck-typed by
        Stage C (``.title``, ``.body``, ``.links``); if it carries a ``uid``,
        ``orient()`` checks it against ``task_uid`` rather than briefing one
        task from another's text.
    ``body_reader``
        ``uid -> raw post-frontmatter bytes``. Not derivable from
        ``content_loader``: that reads the composed index, and Lock 2(a)
        forbids the composed copy as a match domain precisely because it is
        stripped and can lag disk. :func:`governed_body_reader` builds the
        right one.
    ``visible_segments``
        The policy segment classes this viewer may resolve seeds through
        (AC12 R1). Defaults to ``{os}`` — the reserved always-readable
        constant, visible to every viewer, and the only class AC5's egress
        gate lets cross to a provider anyway. The projection answers
        visibility in segment UIDs, not policy classes, and no translation
        between those two vocabularies ships in this tree; widening this set
        is therefore a caller's explicit act, not something derived here from
        a guess.
    ``provider_call`` / ``clock`` / ``reservation_id_factory`` / ``environment``
        The metered edge's injection points. ``None`` means the shipped
        default in :mod:`lib.metered_model` — for ``provider_call`` that is
        the real provider, which is the other reason this value is not
        something to construct casually.
    ``corpus_scale`` / ``rehearsal_receipt``
        Passed straight through to AC13's gate. Stage C refuses a
        corpus-scale run without a rehearsal receipt; nothing here softens,
        pre-answers or bypasses that.

    ``run_binding``, ``policy_resolver`` and ``segment_class_of`` are NOT
    here. They are ``orient()``'s own ``model_run_binding``,
    ``model_policy_resolver`` and ``segment_resolver``: one run has one
    binding, one policy authority and one segment classifier, and a second
    copy of any of them is two authorities waiting to disagree.
    """

    task_source: Any
    body_reader: Callable[[str], bytes]
    visible_segments: frozenset = frozenset({OS_SEGMENT})
    provider_call: Any = None
    clock: Any = None
    reservation_id_factory: Any = None
    environment: Optional[Mapping[str, str]] = None
    corpus_scale: bool = False
    rehearsal_receipt: Optional[Mapping[str, Any]] = None


class _BodyUnavailable(Exception):
    """A survivor's on-disk body could not be read. Internal to the seam.

    Stage C's typed refusals cover a reader that returns the WRONG THING; they
    do not cover a reader that raises, because Stage C is handed the reader and
    does not own its failure modes. A ranked index entry whose governed file is
    missing or whose frontmatter fence is malformed is an ordinary substrate
    fault, and ``distill`` already answers exactly that fault with
    ``CONTENT_UNAVAILABLE``. This carries it out of Stage C so it lands there
    too, instead of raising out of a function that returns a ``Result``.
    """

    def __init__(self, uid: str, cause: BaseException) -> None:
        super().__init__(f"{uid}: {cause}")
        self.uid = uid


@dataclass(frozen=True)
class SpanOrientation(Orientation):
    """An :class:`~lib.distiller_edge.Orientation` that also carries the block.

    A subclass, not a replacement: Stage C COMPOSES with ``distill`` rather
    than superseding it, so ``query_seeds``, ``bound_deterministic`` and
    ``distillation`` are the same values the deterministic path has always
    returned and every existing consumer — including one that type-checks
    ``Orientation`` — keeps working unchanged.

    ``stage_c`` is present only on a run that asked for Stage C and got a
    block. A run that did not ask returns the plain ``Orientation``, so
    "did this cost money?" is answerable from the returned type alone.
    """

    stage_c: StageCBlock


def _stage_c_block(
    request: StageCRequest,
    *,
    task_uid: str,
    viewer: Viewer,
    index_as_of: str,
    deterministic: DeterministicOrientation,
    query_seeds: PrevalidatedQuerySeeds,
    run_binding,
    policy_resolver,
    segment_resolver,
) -> Result:
    """``Result[StageCBlock, DistillError | StageCRefusal]`` — the paid stage.

    Assembles Stage C's parameters from what the deterministic core already
    produced and returns its typed refusal untranslated. Stage C names eleven
    distinct reasons a run will not produce a block; folding them into
    ``DistillError``'s three codes would round every one of them to the
    nearest familiar answer, and the nearest familiar answer is usually the
    reassuring one.
    """

    if run_binding is None:
        return Result.failure(
            DistillError(
                DistillErrorCode.INVALID_ARGUMENT,
                "stage_c needs model_run_binding; the metered edge is bound to "
                "a run or it does not spend",
            )
        )
    if segment_resolver is None:
        return Result.failure(
            DistillError(
                DistillErrorCode.INVALID_ARGUMENT,
                "stage_c needs segment_resolver; AC5's egress gate decides what "
                "may cross to a provider and it cannot decide from nothing",
            )
        )
    stub_uid = getattr(request.task_source, "uid", None)
    if stub_uid is not None and stub_uid != task_uid:
        return Result.failure(
            DistillError(
                DistillErrorCode.BINDING_MISMATCH,
                "stage_c.task_source is a stub for another task; C1 would brief "
                "one task from another's title and body",
            )
        )

    def read_survivor_body(uid: str) -> bytes:
        # Wraps the caller's reader and nothing else, so the translation below
        # can only ever fire on a read. A try/except around the whole of Stage
        # C would catch the same exception types raised anywhere inside it and
        # report a genuine defect as a missing file.
        try:
            return request.body_reader(uid)
        except (OSError, ValueError) as error:
            raise _BodyUnavailable(uid, error) from error

    try:
        block = run_stage_c(
            task_uid=task_uid,
            task_source=request.task_source,
            viewer=viewer,
            visible_segments=request.visible_segments,
            index_as_of=index_as_of,
            # R2's two stamps travel with the ranked UIDs so Stage C can verify
            # that the circle it is distilling was ranked for THIS viewer at
            # THIS snapshot.
            ranking=StageBRanking(
                viewer=viewer,
                index_as_of=index_as_of,
                uids=deterministic.uids(),
                deterministic=deterministic,
            ),
            circle=tuple(member.uid for member in deterministic.circle.members),
            # AC12 R1's population. These are already resolved through
            # ``projection.filter_visible_uids`` by ``resolve_query`` — at UID
            # grain, against the real authority, which is strictly stronger
            # than the class-grain filter Stage C applies. Handing them over
            # anyway keeps R1 answering for the same population it names, and
            # the second filter can only ever be a no-op here.
            seed_candidates=query_seeds.uids,
            body_reader=read_survivor_body,
            segment_class_of=segment_resolver,
            run_binding=run_binding,
            provider_call=request.provider_call,
            policy_resolver=policy_resolver,
            clock=request.clock,
            reservation_id_factory=request.reservation_id_factory,
            environment=request.environment,
            corpus_scale=request.corpus_scale,
            rehearsal_receipt=request.rehearsal_receipt,
        )
    except _BodyUnavailable as unavailable:
        return Result.failure(
            DistillError(
                DistillErrorCode.CONTENT_UNAVAILABLE,
                f"stage_c.body_reader could not read {unavailable}",
            )
        )
    except StageCRefusal as refusal:
        return Result.failure(refusal)
    return Result.success(block)


def orient(
    task_uid: str,
    viewer: Viewer,
    circle_budget: int,
    *,
    intent: str,
    index_as_of: str,
    chunk_budget: int,
    projection: ViewerProjection,
    query_index: QueryIndex,
    circle_index: StructuralIndex,
    rank_index: RankIndex,
    content_loader,
    parse_double=None,
    distill_double=None,
    model_run_binding=None,
    model_call=None,
    model_policy_resolver=None,
    parse_segment_class: str = "private",
    segment_resolver=None,
    stage_c: Optional[StageCRequest] = None,
) -> Result:
    """Assemble query -> deterministic core -> Stage C -> bind -> distillation.

    ``stage_c`` is the spend gate. Left at ``None`` — which is what every
    caller written before this parameter existed passes — the chain is exactly
    what it always was and Stage C's metered edge is never reached; the result
    is the same :class:`~lib.distiller_edge.Orientation`. Supplied, Stage C
    runs between the deterministic core and ``distill``, and the result is a
    :class:`SpanOrientation` carrying the block as well.

    Stage C runs BEFORE ``distill`` and not after, because Lock 3 (AC9) is an
    ordering property: C1 writes the task-intent brief before any body is
    read, so that the brief is a neutral yardstick rather than a summary of
    what was read. ``distill`` loads bodies through the content loader, and
    running it first would leave that ordering true only under an argument
    about which copy of a body counts — the same distinction Lock 2(a) exists
    because the two copies can disagree. Placed here, no body of either kind
    is read before the brief, and the ordering can be read straight off the
    call trace. The cost of that placement is stated plainly: a Stage C run
    that succeeds and is then followed by a content-loader failure has already
    spent.

    Stage C composes with ``distill`` rather than replacing it. ``distill``
    runs unchanged, on the same double, for the same cost as before — so the
    MARGINAL spend of opting in is exactly Stage C's own metered calls (two,
    or three if the guard buys its one repair) and nothing else, which is the
    only version of this arithmetic a caller can check.
    """

    if not isinstance(index_as_of, str) or not index_as_of:
        return Result.failure(
            DistillError(
                DistillErrorCode.BINDING_MISMATCH,
                "index_as_of must be a non-empty snapshot token",
            )
        )
    if getattr(query_index, "index_as_of", None) != index_as_of:
        return Result.failure(
            QueryError(
                QueryErrorCode.BINDING_MISMATCH,
                "query index is not bound to requested index_as_of",
            )
        )
    if getattr(content_loader, "index_as_of", None) != index_as_of:
        return Result.failure(
            DistillError(
                DistillErrorCode.BINDING_MISMATCH,
                "content loader is not bound to requested index_as_of",
            )
        )
    if getattr(circle_index, "index_as_of", None) != index_as_of:
        return Result.failure(
            QueryError(
                QueryErrorCode.BINDING_MISMATCH,
                "circle index is not bound to requested index_as_of",
            )
        )

    parse_adapter = parse_double
    if parse_adapter is None:
        parse_adapter = ParseQueryModelAdapter(
            run_binding=model_run_binding,
            segment_class=parse_segment_class,
            call_model=model_call,
            policy_resolver=model_policy_resolver,
        )
    distill_adapter = distill_double
    if distill_adapter is None:
        distill_adapter = DistillModelAdapter(
            run_binding=model_run_binding,
            segment_resolver=segment_resolver,
            call_model=model_call,
            policy_resolver=model_policy_resolver,
        )

    seeds_result = resolve_query(
        intent,
        viewer,
        index_as_of,
        projection=projection,
        query_index=query_index,
        parse_double=parse_adapter,
    )
    if not seeds_result.ok:
        return Result.failure(seeds_result.error)
    query_seeds = seeds_result.value

    deterministic_result = orient_deterministic(
        task_uid,
        viewer,
        circle_budget,
        projection=projection,
        circle_index=circle_index,
        rank_index=rank_index,
        # Empty freeform resolution delegates to the exact legacy no-seed path.
        query_seeds=query_seeds if query_seeds.uids else None,
    )
    if not deterministic_result.ok:
        return Result.failure(deterministic_result.error)

    # The paid stage, and the only branch in this function that can spend on
    # Stage C's edge. A refusal propagates typed and untranslated: a caller who
    # asked for spans and cannot have them is told which gate refused, not
    # handed an orientation without spans that reads like an answer.
    block = None
    if stage_c is not None:
        stage_c_result = _stage_c_block(
            stage_c,
            task_uid=task_uid,
            viewer=viewer,
            index_as_of=index_as_of,
            deterministic=deterministic_result.value,
            query_seeds=query_seeds,
            run_binding=model_run_binding,
            policy_resolver=model_policy_resolver,
            segment_resolver=segment_resolver,
        )
        if not stage_c_result.ok:
            return Result.failure(stage_c_result.error)
        block = stage_c_result.value

    bound = BoundOrientation(
        deterministic=deterministic_result.value,
        viewer=viewer,
        index_as_of=index_as_of,
    )
    distillation_result = distill(
        bound,
        viewer,
        index_as_of,
        chunk_budget,
        intent=intent,
        query_seeds=query_seeds,
        content_loader=content_loader,
        distill_double=distill_adapter,
    )
    if not distillation_result.ok:
        return Result.failure(distillation_result.error)
    if block is None:
        return Result.success(
            Orientation(
                query_seeds=query_seeds,
                bound_deterministic=bound,
                distillation=distillation_result.value,
            )
        )
    return Result.success(
        SpanOrientation(
            query_seeds=query_seeds,
            bound_deterministic=bound,
            distillation=distillation_result.value,
            stage_c=block,
        )
    )


__all__ = [
    "OrientedItem",
    "DeterministicOrientation",
    "orient_deterministic",
    "BootOrientationErrorCode",
    "BootOrientationError",
    "TransferWatermark",
    "BootDeltaItem",
    "BootDelta",
    "UnreachableTransferDivergence",
    "BootOrientation",
    "ViewerApprovedUIDs",
    "BootIndex",
    "InMemoryBootIndex",
    "SqliteBootIndex",
    "GitDAG",
    "SubprocessGitDAG",
    "orient_boot",
    "serve_boot_orientation",
    "StageBRanking",
    "StageCRequest",
    "SpanOrientation",
    "governed_body_reader",
    "orient",
]
