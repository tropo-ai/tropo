"""The composite live verifier: what is true, checked against what we believe.

Dev-spec 2fae6312 (locked), implementation step 6.

WHY A SECOND VERIFIER AT ALL. The publication receipt is written by the thing
that published, and closure consumes that receipt. Left there, the loop closes
on itself: the run is complete because the run says so. This module is the
independent leg — it re-observes every prior fact and writes a SEPARATE
completion receipt binding the publication receipt, both event surfaces, the
closed record set, and the scorecard. That is what removes the circularity the
spec names.

THE ASYMMETRY THAT MAKES IT SAFE. Post-publication reconciliation can refuse
COMPLETION. It can never undo an outward fact. Once a tag is pushed and an
asset is public, the honest move on a discrepancy is to stay open with a named
partial state and let replay finish the job — not to delete anything, not to
rewrite public history, and above all not to call the release complete because
a retry would be inconvenient.

NAMED PARTIAL STATES, NOT FAILURE. "The release broke" tells an operator
nothing. "site-ref-pending" tells them exactly which edge is unfinished and
that replay will push it. Every incomplete outcome here resolves to one of the
closed names below.

OBSERVERS ARE INJECTED. This module performs no HTTP, no git, no provider
calls. The caller supplies one observer per fact, exactly as `release_saga`
takes observers per checkpoint, so the reconciliation logic is testable without
a network and the production adapters live at the edge where they belong.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "REQUIRED_FACTS",
    "PARTIAL_STATE_BY_FACT",
    "FactObservation",
    "CompletionVerdict",
    "ReleaseCompletionError",
    "verify_completion",
    "completion_receipt_sha256",
]


class ReleaseCompletionError(RuntimeError):
    """Misuse of this module. Never a completion verdict."""


#: Every fact the completion receipt binds, in observation order. Closed: a
#: fact outside this tuple cannot be bound, and one inside it cannot be
#: skipped, so the receipt's coverage is not a matter of who called what.
REQUIRED_FACTS: Tuple[str, ...] = (
    "publication_receipt",
    "bus_published_event",
    "run_published_event",
    "closed_records",
    "scorecard",
)

#: The named incomplete state each absent fact reports. From the spec's
#: outward checkpoint table, so an operator reading a partial state here and a
#: partial state in the journal is reading the same vocabulary.
PARTIAL_STATE_BY_FACT: Dict[str, str] = {
    "publication_receipt": "publication-receipt-pending",
    "bus_published_event": "event-mirror-pending",
    "run_published_event": "event-mirror-pending",
    "closed_records": "closure-pending",
    "scorecard": "scorecard-pending",
}

COMPLETION_EVENT = "tropo.release.completion_verified"

#: Facts that must all bind the SAME publication receipt. Observing four
#: present facts proves four things happened; it does not prove they happened
#: to the same release. A bus event mirroring one receipt while closure
#: consumed another is exactly the incoherence a per-fact check cannot see, so
#: the agreement is checked here rather than assumed by each observer.
CO_BOUND_FACTS: Tuple[str, ...] = (
    "publication_receipt",
    "bus_published_event",
    "run_published_event",
    "closed_records",
)

#: Verification itself could not complete. Distinct from any single edge being
#: pending: every edge is present, and they disagree.
INCOHERENT_STATE = "completion-verification-pending"


@dataclass(frozen=True)
class FactObservation:
    """One independently observed fact.

    `present` is the observation, not a claim read out of the journal. An
    observer that cannot reach its subject reports `present=False` with a
    detail saying so — it does not guess, and it does not raise past the
    verifier, because an unreachable provider is an incomplete release rather
    than a crashed tool.
    """

    fact: str
    present: bool
    evidence_sha256: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        if self.fact not in REQUIRED_FACTS:
            raise ReleaseCompletionError(
                "%r is not one of the bound facts: %s"
                % (self.fact, ", ".join(REQUIRED_FACTS))
            )
        if self.present and not self.evidence_sha256:
            raise ReleaseCompletionError(
                "observation of %r says present but carries no evidence hash. A "
                "fact asserted without evidence is the circularity this module "
                "exists to remove" % (self.fact,)
            )


@dataclass(frozen=True)
class CompletionVerdict:
    complete: bool
    partial_state: Optional[str]
    observations: Tuple[FactObservation, ...]
    receipt: Optional[Dict[str, Any]] = None
    detail: str = ""

    @property
    def missing(self) -> List[str]:
        return [o.fact for o in self.observations if not o.present]

    @property
    def exit_code(self) -> int:
        """0 complete, 1 incomplete. Never raises, never partial-credit."""
        return 0 if self.complete else 1


def completion_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    """Deterministic hash over the receipt body, sorted and separator-fixed."""
    payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_completion(
    observers: Mapping[str, Callable[[], FactObservation]],
    *,
    saga_id: str,
    pipeline_run_uid: str,
) -> CompletionVerdict:
    """Observe every bound fact, then decide.

    Every observer runs even after the first absence. Stopping early would
    report one pending edge when three are pending, and an operator who fixes
    the named one only to meet the next is being drip-fed a truth the verifier
    already had.
    """
    if not saga_id or not pipeline_run_uid:
        raise ReleaseCompletionError(
            "completion verification needs the run it is verifying"
        )

    missing_observers = [f for f in REQUIRED_FACTS if f not in observers]
    if missing_observers:
        raise ReleaseCompletionError(
            "no observer supplied for %s. A fact with no observer would be "
            "counted as verified by omission" % ", ".join(missing_observers)
        )

    observations: List[FactObservation] = []
    for fact in REQUIRED_FACTS:
        try:
            observation = observers[fact]()
        except Exception as exc:  # noqa: BLE001 — an unreachable edge is incomplete
            observation = FactObservation(
                fact=fact,
                present=False,
                detail="observer failed: %s: %s" % (type(exc).__name__, exc),
            )
        if not isinstance(observation, FactObservation):
            raise ReleaseCompletionError(
                "observer for %r returned %r, not a FactObservation"
                % (fact, type(observation).__name__)
            )
        if observation.fact != fact:
            raise ReleaseCompletionError(
                "observer for %r reported on %r" % (fact, observation.fact)
            )
        observations.append(observation)

    absent = [o for o in observations if not o.present]
    if absent:
        # The FIRST absent fact in dependency order names the state, because
        # that is the edge replay will attempt next.
        partial = PARTIAL_STATE_BY_FACT[absent[0].fact]
        return CompletionVerdict(
            complete=False,
            partial_state=partial,
            observations=tuple(observations),
            receipt=None,
            detail="%d of %d bound fact(s) not observed: %s"
            % (
                len(absent),
                len(REQUIRED_FACTS),
                ", ".join(
                    "%s (%s)" % (o.fact, o.detail or "absent") for o in absent
                ),
            ),
        )

    by_fact = {o.fact: o.evidence_sha256 for o in observations}
    bound = {by_fact[f] for f in CO_BOUND_FACTS}
    if len(bound) != 1:
        return CompletionVerdict(
            complete=False,
            partial_state=INCOHERENT_STATE,
            observations=tuple(observations),
            receipt=None,
            detail=(
                "every fact is present but they do not describe one release: "
                + ", ".join(
                    "%s=%s" % (f, by_fact[f]) for f in CO_BOUND_FACTS
                )
            ),
        )

    receipt = {
        "receipt_kind": "release-completion-receipt",
        "saga_id": saga_id,
        "pipeline_run_uid": pipeline_run_uid,
        "verified_facts": {
            o.fact: o.evidence_sha256 for o in observations
        },
    }
    receipt["completion_receipt_sha256"] = completion_receipt_sha256(receipt)

    return CompletionVerdict(
        complete=True,
        partial_state=None,
        observations=tuple(observations),
        receipt=receipt,
        detail="all %d bound facts independently observed" % len(REQUIRED_FACTS),
    )
