"""The one release state machine: observe, intend, act, verify.

Dev-spec 2fae6312 (locked). Lock, build, publish and the operator facade all
drive release progression through this module, so there is exactly one place
that decides what has happened and what may happen next.

WHY A SAGA AND NOT A SCRIPT. Cross-repository publication cannot be atomic. A
release pushes git refs, creates a release object, uploads assets to two
providers, flips a governed entry, publishes a manifest, pushes a site commit,
and writes a receipt — across systems that fail independently and remember
different things. The honest model is therefore not "did the script finish" but
"what is true in the world right now", and every step here is written to be
resumable from world state rather than from a local belief about it.

THE FOUR STEPS, in this order, for every outward act:

  1. OBSERVE the exact world state for this checkpoint.
  2. RECORD INTENT in the run journal before touching anything outward.
  3. ACT only if the observation says the fact is absent.
  4. RECORD THE VERIFIED OBSERVATION, read back from the world.

Step 1 before step 2 is what makes replay safe: a run that died between intent
and act finds the fact absent and performs it; a run that died between act and
verification finds the fact present and records it without repeating the act.
An idempotency key makes "the same act" decidable rather than a judgement call.

WHAT THIS MODULE DELIBERATELY DOES NOT DO. It performs no release work itself.
It has no provider clients, no git calls, no knowledge of GitHub or Supabase.
Callers supply an observer and an actor per checkpoint; the machine owns
ordering, dependency, idempotency, conflict refusal, and the journal. A state
machine that also knows how to upload things becomes the second publisher the
spec forbids.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SAGA_ID_PREFIX = "release"

INTENT_EVENT = "tropo.release.saga_intent"
OBSERVED_EVENT = "tropo.release.saga_observed"

# Outcome kinds. A refusal is a truthful "no" about the world; an operational
# error is the machinery failing to find out. Collapsing the two is how a
# provider outage gets recorded as a governance decision.
OUTCOME_ALREADY_PRESENT = "already-present"
OUTCOME_ACTED = "acted"
OUTCOME_REFUSED = "refused"
OUTCOME_OPERATIONAL_ERROR = "operational-error"
OUTCOME_BLOCKED = "blocked-on-dependency"


class ReleaseSagaError(RuntimeError):
    """The saga cannot proceed and the reason is structural, not a refusal."""


@dataclass(frozen=True)
class Checkpoint:
    """One outward step's declared contract.

    `depends_on` is what must be verified first, `idempotency_key_template` is
    how two attempts are recognised as the same act, and `incomplete_state` is
    the exact name a partially-published release reports instead of a vague
    failure. That name is the difference between "the release broke" and
    "the site ref is pending and replay will push it".
    """

    checkpoint_id: str
    depends_on: Tuple[str, ...]
    idempotency_key_template: str
    incomplete_state: str
    description: str

    def idempotency_key(self, context: Dict[str, Any]) -> str:
        try:
            return self.idempotency_key_template.format(**context)
        except KeyError as exc:
            raise ReleaseSagaError(
                "checkpoint {} cannot build its idempotency key: context is "
                "missing {}".format(self.checkpoint_id, exc)
            )


# The closed checkpoint enum from the locked spec, in dependency order. Closed
# on purpose: an unregistered outward act is one the journal cannot describe,
# resume, or refuse, which is precisely the class this package exists to end.
CHECKPOINTS: Tuple[Checkpoint, ...] = (
    Checkpoint(
        "site_prepare", (),
        "site:{parent}:{version}:{size}", "site-prepare-pending",
        "Prepare the badge-only site commit with push disabled.",
    ),
    Checkpoint(
        "git_refs", ("site_prepare",),
        "refs:{staged_sha}", "primary-refs-pending",
        "Create main and tag refs atomically, or recover a bounded partial.",
    ),
    Checkpoint(
        "github_release", ("git_refs",),
        "gh-release:{tag}", "github-release-pending",
        "Create the release object if absent.",
    ),
    Checkpoint(
        "github_asset", ("github_release",),
        "gh-asset:{tag}:{package_sha}", "github-asset-pending",
        "Upload the package asset if absent; wrong bytes conflict.",
    ),
    Checkpoint(
        "supabase_asset", ("github_asset",),
        "supabase:{version}:{package_sha}", "supabase-asset-pending",
        "Upload the public asset if absent; wrong bytes conflict before upsert.",
    ),
    Checkpoint(
        "release_entry_projection", ("supabase_asset",),
        "entry:{release_uid}:{package_sha}", "release-entry-pending",
        "Flip the release entry, freshen the index, stamp the version.",
    ),
    Checkpoint(
        "update_manifest", ("release_entry_projection",),
        "manifest:{version}:{package_sha}", "manifest-pending",
        "Generate and upload the update manifest if absent or stale.",
    ),
    Checkpoint(
        "site_ref", ("update_manifest",),
        "site-ref:{site_commit}", "release-live-site-pending",
        "Fast-forward CAS push of the prepared site commit.",
    ),
    Checkpoint(
        "site_endpoint", ("site_ref",),
        "site-endpoint:{site_commit}:{version}", "release-live-site-pending",
        "Observe the served badge endpoint, cache-busted and bounded.",
    ),
    Checkpoint(
        "publication_receipt", (
            "git_refs", "github_release", "github_asset", "supabase_asset",
            "release_entry_projection", "update_manifest", "site_ref",
            "site_endpoint",
        ),
        "publication:{run_uid}:{package_sha}", "publication-receipt-pending",
        "Write the immutable publication receipt.",
    ),
    Checkpoint(
        "bus_published_event", ("publication_receipt",),
        "bus-published:{receipt_sha}", "event-mirror-pending",
        "Emit exactly one matching bus event.",
    ),
    Checkpoint(
        "run_published_event", ("publication_receipt",),
        "run-published:{receipt_sha}", "event-mirror-pending",
        "Append exactly one matching run event.",
    ),
    Checkpoint(
        "closure", ("bus_published_event", "run_published_event"),
        "closure:{receipt_sha}", "closure-pending",
        "Invoke the idempotent closer over every named record.",
    ),
    Checkpoint(
        "scorecard", ("closure",),
        "scorecard:{run_uid}:{mode}", "scorecard-pending",
        "Write the rehearsal or real-fire scorecard to its fixed path.",
    ),
    Checkpoint(
        "completion_verification", ("scorecard",),
        "completion:{scorecard_sha}", "completion-verification-pending",
        "Observe every prior fact independently, then write the completion "
        "receipt. Separate from publication_receipt on purpose: a receipt that "
        "attests to its own closure proves nothing, so the fact that closes the "
        "run is written by something that re-observed the world.",
    ),
)

CHECKPOINTS_BY_ID: Dict[str, Checkpoint] = {c.checkpoint_id: c for c in CHECKPOINTS}


def assert_registered(checkpoint_id: str) -> None:
    """AC7 (2cb346d6): an outward act not registered as a checkpoint is
    refused, not silently performed. The journal cannot describe, resume, or
    refuse an unregistered act — which is precisely the class this package
    exists to end."""
    if checkpoint_id not in CHECKPOINTS_BY_ID:
        raise ReleaseSagaError(
            "checkpoint {!r} is not in the closed enum; an unregistered "
            "outward act is one the journal cannot describe, resume, or "
            "refuse".format(checkpoint_id))


def saga_id_for(pipeline_run_uid: str) -> str:
    """The deterministic saga identity for one release run.

    Derived, never minted. Replay computes the same value from the same run, so
    a second attempt cannot open a second saga over one release — which is the
    failure that makes two partial publications look like two releases.
    """
    run_uid = (pipeline_run_uid or "").strip()
    if not run_uid:
        raise ReleaseSagaError("a saga id requires a pipeline run uid")
    return "{}:{}".format(SAGA_ID_PREFIX, run_uid)


@dataclass(frozen=True)
class Observation:
    """What the world says about one checkpoint, right now."""

    present: bool
    fact: Optional[Dict[str, Any]] = None
    conflict: Optional[str] = None

    @property
    def conflicting(self) -> bool:
        return self.conflict is not None


@dataclass(frozen=True)
class StepResult:
    checkpoint_id: str
    outcome: str
    saga_id: str
    idempotency_key: str
    fact: Optional[Dict[str, Any]] = None
    detail: str = ""
    incomplete_state: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.outcome in (OUTCOME_ALREADY_PRESENT, OUTCOME_ACTED)


@dataclass
class SagaJournal:
    """Append-only progression store for one release run.

    The journal records intent and verified observation; it is never the
    authority on whether an outward fact exists. A resumed run reads it to know
    what was attempted, then asks the world what is true.
    """

    path: Path
    saga_id: str
    _entries: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def open(cls, path: Path, saga_id: str) -> "SagaJournal":
        journal = cls(path=Path(path), saga_id=saga_id)
        journal.reload()
        return journal

    def reload(self) -> None:
        self._entries = []
        if not self.path.is_file():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                # A malformed line is history we cannot parse, not permission to
                # guess. Skip it for progression and let the validator report it.
                continue
            if isinstance(entry, dict):
                self._entries.append(entry)

    def append(self, event: str, checkpoint_id: str, **payload: Any) -> Dict[str, Any]:
        entry = {
            "event": event,
            "saga_id": self.saga_id,
            "checkpoint": checkpoint_id,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        entry.update(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        self._entries.append(entry)
        return entry

    def observed(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """The most recent verified observation for one checkpoint, if any."""
        for entry in reversed(self._entries):
            if (
                entry.get("event") == OBSERVED_EVENT
                and entry.get("checkpoint") == checkpoint_id
                and entry.get("saga_id") == self.saga_id
            ):
                return entry
        return None

    def intents(self, checkpoint_id: str) -> List[Dict[str, Any]]:
        return [
            entry for entry in self._entries
            if entry.get("event") == INTENT_EVENT
            and entry.get("checkpoint") == checkpoint_id
            and entry.get("saga_id") == self.saga_id
        ]

    def completed_checkpoints(self) -> List[str]:
        return [c.checkpoint_id for c in CHECKPOINTS if self.observed(c.checkpoint_id)]


def unmet_dependencies(checkpoint: Checkpoint, journal: SagaJournal) -> List[str]:
    return [dep for dep in checkpoint.depends_on if journal.observed(dep) is None]


def run_checkpoint(
    checkpoint_id: str,
    *,
    journal: SagaJournal,
    context: Dict[str, Any],
    observe: Callable[[], Observation],
    act: Callable[[], Dict[str, Any]],
) -> StepResult:
    """Drive one checkpoint through observe, intent, act, verify.

    `observe` answers what is true now; `act` performs the outward step and is
    only ever called when the observation says the fact is absent. Both are
    supplied by the caller because this module must not become a publisher.
    """
    checkpoint = CHECKPOINTS_BY_ID.get(checkpoint_id)
    if checkpoint is None:
        raise ReleaseSagaError(
            "unregistered checkpoint {!r}: the enum is closed so that no outward "
            "act exists which the journal cannot resume or refuse".format(checkpoint_id)
        )

    key = checkpoint.idempotency_key(context)
    blocked = unmet_dependencies(checkpoint, journal)
    if blocked:
        return StepResult(
            checkpoint_id, OUTCOME_BLOCKED, journal.saga_id, key,
            detail="unverified dependency: {}".format(", ".join(blocked)),
            incomplete_state=CHECKPOINTS_BY_ID[blocked[0]].incomplete_state,
        )

    # 1. OBSERVE — before intent, so replay can tell an unperformed act from an
    #    unrecorded one.
    try:
        observation = observe()
    except Exception as exc:
        return StepResult(
            checkpoint_id, OUTCOME_OPERATIONAL_ERROR, journal.saga_id, key,
            detail="observation failed: {}".format(exc),
            incomplete_state=checkpoint.incomplete_state,
        )

    if observation.conflicting:
        # A conflict is a truthful refusal: the world holds something that is
        # not what this run intended, and overwriting it is never this
        # machine's call.
        journal.append(
            OBSERVED_EVENT, checkpoint_id, idempotency_key=key,
            outcome=OUTCOME_REFUSED, conflict=observation.conflict,
        )
        return StepResult(
            checkpoint_id, OUTCOME_REFUSED, journal.saga_id, key,
            detail=observation.conflict, incomplete_state=checkpoint.incomplete_state,
        )

    if observation.present:
        journal.append(
            OBSERVED_EVENT, checkpoint_id, idempotency_key=key,
            outcome=OUTCOME_ALREADY_PRESENT, fact=observation.fact,
        )
        return StepResult(
            checkpoint_id, OUTCOME_ALREADY_PRESENT, journal.saga_id, key,
            fact=observation.fact, detail="already present; not repeated",
        )

    # 2. RECORD INTENT — before any outward act, so a crash mid-act leaves a
    #    trace pointing at exactly which checkpoint to re-observe.
    journal.append(INTENT_EVENT, checkpoint_id, idempotency_key=key)

    # 3. ACT.
    try:
        act()
    except Exception as exc:
        return StepResult(
            checkpoint_id, OUTCOME_OPERATIONAL_ERROR, journal.saga_id, key,
            detail="action failed: {}".format(exc),
            incomplete_state=checkpoint.incomplete_state,
        )

    # 4. VERIFY by reading the world back. The actor's return value is not
    #    evidence: a provider that accepted a request has not necessarily
    #    published a fact.
    try:
        confirmed = observe()
    except Exception as exc:
        return StepResult(
            checkpoint_id, OUTCOME_OPERATIONAL_ERROR, journal.saga_id, key,
            detail="post-act verification failed: {}".format(exc),
            incomplete_state=checkpoint.incomplete_state,
        )
    if confirmed.conflicting or not confirmed.present:
        return StepResult(
            checkpoint_id, OUTCOME_OPERATIONAL_ERROR, journal.saga_id, key,
            detail="acted but the world does not show the fact: {}".format(
                confirmed.conflict or "still absent"),
            incomplete_state=checkpoint.incomplete_state,
        )

    journal.append(
        OBSERVED_EVENT, checkpoint_id, idempotency_key=key,
        outcome=OUTCOME_ACTED, fact=confirmed.fact,
    )
    return StepResult(
        checkpoint_id, OUTCOME_ACTED, journal.saga_id, key, fact=confirmed.fact,
    )


def current_state(journal: SagaJournal) -> Dict[str, Any]:
    """What this release has actually completed, and what it is waiting on.

    `complete` means every checkpoint carries a verified observation. Anything
    else reports the exact named incomplete state of the first unfinished
    checkpoint, because "the release failed" is not a resumable instruction.
    """
    done = journal.completed_checkpoints()
    remaining = [c for c in CHECKPOINTS if c.checkpoint_id not in set(done)]
    return {
        "saga_id": journal.saga_id,
        "completed": done,
        "remaining": [c.checkpoint_id for c in remaining],
        "complete": not remaining,
        "state": "complete" if not remaining else remaining[0].incomplete_state,
    }


def next_checkpoint(journal: SagaJournal) -> Optional[Checkpoint]:
    """The first checkpoint whose dependencies are met and which is unverified."""
    for checkpoint in CHECKPOINTS:
        if journal.observed(checkpoint.checkpoint_id) is not None:
            continue
        if unmet_dependencies(checkpoint, journal):
            continue
        return checkpoint
    return None


__all__ = [
    "CHECKPOINTS",
    "CHECKPOINTS_BY_ID",
    "Checkpoint",
    "INTENT_EVENT",
    "OBSERVED_EVENT",
    "OUTCOME_ACTED",
    "OUTCOME_ALREADY_PRESENT",
    "OUTCOME_BLOCKED",
    "OUTCOME_OPERATIONAL_ERROR",
    "OUTCOME_REFUSED",
    "Observation",
    "ReleaseSagaError",
    "SagaJournal",
    "StepResult",
    "current_state",
    "next_checkpoint",
    "run_checkpoint",
    "saga_id_for",
]
