"""Contextual authorization for release events.

Dev-spec 2fae6312 (locked), implementation step 5.

THE ONE RULE. An event is authorized against a context that is DERIVED FROM
SUBSTRATE — the immutable activation, the run journal, the run's declaration
snapshot, and observed package/receipt state. Caller-supplied identities never
populate that context. The caller's event says what it claims; the context says
what is true; authorization is the comparison.

This matters because the alternative is circular in a way that reads fine. If
an emitter passes both the event and the identities the event should match,
every event authorizes itself, and the check reports PASS for a run it never
looked at. The gate then costs real time and proves nothing — the same shape as
an enum checker examining zero entries.

So :class:`AuthorizationContext` has one honest constructor,
:meth:`AuthorizationContext.observe`, which reads substrate. Nothing in
:func:`authorize` accepts an identity override.

WHAT IS AND IS NOT CLAIMED. This guards event SHAPES and IDENTITIES inside a
trusted local-write boundary. It is not a security control against a process
with arbitrary repository write access — such a process can write the journal
directly. It stops honest emitters from writing dishonest rows.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from lib import release_package as _pkg  # noqa: E402
from lib import governed_path as gp  # noqa: E402
from lib.journal_event import run_journal_event_type  # noqa: E402

__all__ = [
    "RELEASE_EVENTS",
    "ENVELOPE_REQUIRED",
    "ENVELOPE_NULLABLE",
    "EventContract",
    "AuthorizationContext",
    "AuthorizationVerdict",
    "ReleaseEventError",
    "authorize",
]


class ReleaseEventError(RuntimeError):
    """Misuse of this module. Never an authorization verdict."""


# --------------------------------------------------------------------------- #
# Refusal classes — closed                                                     #
# --------------------------------------------------------------------------- #

REFUSAL_UNREGISTERED = "unregistered-event-type"
REFUSAL_ENVELOPE = "envelope-shape"
REFUSAL_DATA_MISSING = "missing-required-data"
REFUSAL_DATA_UNKNOWN = "unknown-data-key"
REFUSAL_IDENTITY = "identity-mismatch"
REFUSAL_STEP = "step-not-in-declaration-snapshot"
REFUSAL_CARDINALITY = "cardinality"

# --------------------------------------------------------------------------- #
# Envelope                                                                     #
# --------------------------------------------------------------------------- #

ENVELOPE_REQUIRED: Tuple[str, ...] = (
    "event",
    "ts",
    "actor",
    "data",
    "schema_version",
    "trace_id",
    "span_id",
)

ENVELOPE_NULLABLE: Tuple[str, ...] = (
    "actor_label_resolved",
    "step",
    "stage",
    "parent_span_id",
    # 3d8d4351 §4: HOW the row came to exist — "fire-authorize" on the
    # engine's own stamp path, "bare" on the diagnostic path. The verdict
    # tally's actor-awareness needs it: machine-authored rows carry it so a
    # principal gesture can never be forged by a machine writer claiming a
    # human actor. Nullable at the envelope layer; required in the data of
    # the classes the engine stamps.
    "invoked_via",
)


@dataclass(frozen=True)
class EventContract:
    """One row of the finite release-event table."""

    event: str
    required_data: Tuple[str, ...]
    #: Data keys that identify the run and must match observed substrate.
    dedup_keys: Tuple[str, ...] = ()
    #: True when the event names an instrument step; that step must belong to
    #: the run's IMMUTABLE declaration snapshot, not merely resolve in the
    #: live Vault — a node added after the run started is not this run's node.
    stepped: bool = False
    bus_type: Optional[str] = None
    #: A terminal fact may occur at most once per run.
    terminal: bool = False
    #: HOW MANY WRITERS THIS EVENT IS ALLOWED (S2 AC1, 3fb41c99).
    #: "one"          — exactly one emit site. The default, and the point of the AC:
    #:                  package_frozen had TWO writers asserting two different facts
    #:                  under one name, and that is what made the freeze step
    #:                  unreachable for six hours on release night.
    #: "engine-many"  — a library primitive emitted from many call sites.
    #:
    #: THE BOUND, ruled by argus-a154 2026-08-23 when accepting talos-t48's proposal:
    #: `engine-many` is legitimate ONLY when every writer emits through ONE SHARED
    #: PAYLOAD CONSTRUCTOR — many CALL SITES, one AUTHORSHIP. If two sites build the
    #: payload independently, that is not engine-many; that is package_frozen wearing
    #: a different label, and the declaration would re-open the exact defect this spec
    #: exists to close. A cardinality field without that bound is an escape hatch.
    writers_expected: str = "one"


def _c(event, required, dedup=(), stepped=False, bus=None, terminal=False,
       writers="one"):
    return EventContract(event, tuple(required), tuple(dedup), stepped, bus, terminal,
                         writers)


#: The finite table. An event outside it is refused, which is what makes the
#: vocabulary closed rather than merely documented.
RELEASE_EVENTS: Dict[str, EventContract] = {
    c.event: c
    for c in (
        _c(
            "tropo.release.scope_locked",
            ("saga_id", "release_plan_uid", "activation_uid", "activation_root_uid",
             "pipeline_run_uid", "release_entry_uid"),
            dedup=("pipeline_run_uid",),
            terminal=True,
        ),
        _c(
            "tropo.release.orchestrator_invoked",
            ("saga_id", "pipeline_run_uid", "invocation_uid", "invoked_via"),
            dedup=("invocation_uid",),
        ),
        _c(
            # 3d8d4351 §6: the verify-only path journals its invocation — no
            # run-resolving publish path escapes measurement. Reader: the
            # scorecard tally (AC5) counts it; cmd_verify_only writes it.
            "tropo.release.verify_only_invoked",
            ("saga_id", "pipeline_run_uid", "invocation_uid", "version", "reason",
             "invoked_via"),
            dedup=("invocation_uid",),
        ),
        _c(
            "tropo.release.fire_authorized",
            ("saga_id", "pipeline_run_uid", "package_sha256", "approval_uid"),
            dedup=("package_sha256",),
        ),
        _c(
            "tropo.release.candidate_built",
            ("saga_id", "pipeline_run_uid", "candidate_sha256", "candidate_path"),
            dedup=("candidate_sha256",),
        ),
        _c(
            "tropo.release.candidate_invalidated",
            ("saga_id", "pipeline_run_uid", "candidate_sha256", "reason"),
            dedup=("candidate_sha256",),
        ),
        _c(
            "verification_receipt",
            ("receipt_kind", "pipeline_run_uid", "candidate_sha256", "instrument",
             "instrument_step_uid", "verdict", "evidence_sha256"),
            dedup=("pipeline_run_uid", "candidate_sha256", "instrument"),
            stepped=True,
            # engine-many: 9 sites across 4 files, ALL through eng.make_event —
            # one authorship, many callers. Bound verified argus-a154 2026-08-23.
            writers="engine-many",
        ),
        _c(
            # v1.91 S2 (3fb41c99), Argus A155's ruling part 1: a name of its
            # own, split from the generic "verification_receipt" above —
            # that name is ALSO the dev-pipeline's per-step criterion
            # receipt (389 production rows carrying rubric_scores/
            # per_criterion/verifier_role_resolved, an unrelated shape), so
            # a reader keying on the name alone could not tell the two
            # apart. lib/release_verify.py's Receipt is the single writer
            # (9e7003b1.py's emit_release_verification_receipt, one call
            # site) and reader (the freeze gate, the publisher, the
            # release-harness-gate). release_run_uid not pipeline_run_uid,
            # and candidate_sha256 not package_sha256, matching the actual
            # dataclass field names rather than the vocabulary's usual
            # convention — the receipt is written before a freeze (and its
            # package identity) can exist.
            "release-verification-receipt",
            ("receipt_kind", "instrument", "release_run_uid", "candidate_sha256",
             "verdict", "executor_or_attester", "execution_mode", "evidence_ref",
             "started_at", "completed_at"),
            dedup=("release_run_uid", "candidate_sha256", "instrument"),
            stepped=True,
        ),
        _c(
            "tropo.release.package_frozen",
            ("saga_id", "pipeline_run_uid", "package_sha256", "receipt_set_sha256"),
            dedup=("pipeline_run_uid",),
            terminal=True,
        ),
        _c(
            "tropo.release.package_superseded",
            ("saga_id", "pipeline_run_uid", "old_package_sha256",
             "replacement_candidate_sha256", "reason"),
            dedup=("old_package_sha256",),
        ),
        _c(
            "tropo.release.saga_intent",
            ("saga_id", "pipeline_run_uid", "checkpoint_id", "idempotency_key",
             "input_fingerprint"),
            dedup=("checkpoint_id", "idempotency_key"),
            # engine-many: 2 sites, and the caller in tropo-publish-release.py:1831
            # emits via the library's OWN journal.append + INTENT_EVENT rather than
            # constructing a payload of its own. Bound verified argus-a154 2026-08-23.
            writers="engine-many",
        ),
        _c(
            "tropo.release.saga_observed",
            ("saga_id", "pipeline_run_uid", "checkpoint_id", "idempotency_key",
             "outcome", "observation_sha256"),
            dedup=("checkpoint_id", "idempotency_key"),
            # engine-many: 4 sites, same shared journal.append authorship as
            # saga_intent. Bound verified argus-a154 2026-08-23.
            writers="engine-many",
        ),
        _c(
            "tropo.release.published",
            ("saga_id", "pipeline_run_uid", "package_sha256", "release_entry_uid",
             "publication_receipt_sha256"),
            dedup=("publication_receipt_sha256",),
            bus="tropo.release.published",
            terminal=True,
        ),
        _c(
            "tropo.release.closed",
            ("saga_id", "pipeline_run_uid", "release_entry_uid",
             "publication_receipt_sha256", "closed_uids"),
            dedup=("publication_receipt_sha256",),
            bus="tropo.release.closed",
            terminal=True,
        ),
        _c(
            "tropo.release.completion_verified",
            ("saga_id", "pipeline_run_uid", "publication_receipt_sha256",
             "closure_receipt_sha256", "scorecard_sha256",
             "composite_verifier_receipt_sha256"),
            dedup=("pipeline_run_uid",),
            terminal=True,
        ),
    )
}

#: Human input IDs map exactly onto three of the events above.
HUMAN_INPUT_EVENTS: Dict[str, str] = {
    "release_scope_locked": "tropo.release.scope_locked",
    "release_orchestrator_invoked": "tropo.release.orchestrator_invoked",
    "release_fire_authorized": "tropo.release.fire_authorized",
}

#: Identity keys whose value, when present in `data`, must equal the observed
#: context. This is the list that makes an event about THIS run.
_IDENTITY_KEYS = (
    "saga_id",
    "pipeline_run_uid",
    "activation_uid",
    "activation_root_uid",
    "release_entry_uid",
    "release_plan_uid",
)


@dataclass(frozen=True)
class AuthorizationContext:
    """What is true about this run, read from substrate.

    Construct it with :meth:`observe`. The dataclass fields are the observed
    facts themselves, so a test may build one directly from substrate values —
    but nothing here ever takes them from the event being authorized.
    """

    activation_uid: str
    pipeline_run_uid: str
    saga_id: str
    release_entry_uid: str
    activation_root_uid: str = ""
    release_plan_uid: str = ""
    snapshot_step_uids: FrozenSet[str] = frozenset()
    active_candidate_sha256: Optional[str] = None
    frozen_package_sha256: Optional[str] = None
    publication_receipt_sha256: Optional[str] = None

    @classmethod
    def observe(cls, run_dir: Path) -> "AuthorizationContext":
        """Derive the context by reading the run's own substrate.

        Reads the immutable declaration snapshot for the step set and the run
        journal for identity and observed package state. Deliberately takes a
        directory and nothing else: there is no parameter through which a
        caller could supply an identity.
        """
        run_dir = Path(run_dir)
        snapshot_path = run_dir / "declaration-snapshot.json"
        journal_path = run_dir / "run.jsonl"

        step_uids = set()
        if snapshot_path.is_file():
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise ReleaseEventError(
                    "declaration snapshot at %s is unreadable: %s" % (snapshot_path, exc)
                )
            step_uids = _snapshot_step_uids(snapshot)

        identity: Dict[str, str] = {}
        receipt: Optional[str] = None

        rows = _read_journal(journal_path)
        for row in rows:
            data = row.get("data") or {}
            for key in _IDENTITY_KEYS:
                if key in data and key not in identity and data[key]:
                    identity[key] = str(data[key])
            if run_journal_event_type(row) == "tropo.release.published":
                receipt = data.get("publication_receipt_sha256") or data.get("receipt_sha256")

        # v1.91 S2 AC3 (3fb41c99): "which candidate is live" and "is this run
        # frozen" are answered by lib/release_package's shared resolvers, not
        # by a second loop here. The prior version tracked both itself and
        # never handled `package_superseded` at all -- a package_superseded
        # run read as still frozen, silently, in a reader nothing calls yet.
        # Ruled in scope by argus-a154 2026-08-23: an unwired reader that
        # DISAGREES with the shared resolver is a landmine, not a dead file --
        # the day something wires it, it inherits a wrong answer with no
        # warning, same shape as `package_frozen` acquiring two meanings.
        run_uid = identity.get("pipeline_run_uid", "")
        try:
            active = _pkg.active_candidate(rows, run_uid)
            frozen_payload = _pkg.active_frozen_payload(rows, run_uid)
        except _pkg.PackageRefusal as exc:
            # A genuinely ambiguous journal (two live candidates, a
            # supersession that names bytes that are not the active freeze)
            # is a substrate integrity problem, not an authorization verdict
            # this context can quietly resolve around -- "context comes from
            # the run, or it does not come at all" (module docstring).
            raise ReleaseEventError(
                f"cannot observe candidate/frozen state for run {run_uid!r}: {exc}"
            ) from exc
        candidate = active.get("candidate_sha256") if active else None
        frozen = frozen_payload.get("package_sha256") if frozen_payload else None

        return cls(
            activation_uid=identity.get("activation_uid", ""),
            pipeline_run_uid=identity.get("pipeline_run_uid", ""),
            saga_id=identity.get("saga_id", ""),
            release_entry_uid=identity.get("release_entry_uid", ""),
            activation_root_uid=identity.get("activation_root_uid", ""),
            release_plan_uid=identity.get("release_plan_uid", ""),
            snapshot_step_uids=frozenset(step_uids),
            active_candidate_sha256=candidate,
            frozen_package_sha256=frozen,
            publication_receipt_sha256=receipt,
        )

    def identity_value(self, key: str) -> Optional[str]:
        return {
            "saga_id": self.saga_id,
            "pipeline_run_uid": self.pipeline_run_uid,
            "activation_uid": self.activation_uid,
            "activation_root_uid": self.activation_root_uid,
            "release_entry_uid": self.release_entry_uid,
            "release_plan_uid": self.release_plan_uid,
        }.get(key)


#: The key the producer actually writes. `ignition.DeclarationSnapshot.as_dict()`
#: emits `declared_steps`, and `load_snapshot()` returns it under the same name;
#: the `steps` key appears ONLY inside the transient digest payload and never in
#: a snapshot a reader receives. This reader was written against six plausible
#: synonyms — uid / step_uid / node_uid / children / steps / nodes — and the one
#: real key was not among them, so it returned an empty set on every real
#: snapshot, silently, for dev and release runs alike. Named as a constant
#: rather than added to the guess list, because the guess list is the defect:
#: a reader should read what the writer declares, not enumerate what it might.
#: (Found by talos-t50 2026-08-24 building 1a478c48 AC2, who ran it against a
#: real snapshot rather than reading it, and asked before touching a file in
#: another lane. Verified and fixed by argus-a156 the same hour.)
SNAPSHOT_STEPS_KEY = "declared_steps"

#: Legacy tolerance only. Retained so a snapshot written before the key was
#: named still resolves; nothing in the current writer emits these.
_LEGACY_STEP_LIST_KEYS = ("children", "steps", "nodes")


def _snapshot_step_uids(snapshot: Any) -> set:
    """Every governed-shape step UID declared in the run's immutable snapshot."""
    found = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("uid", "step_uid", "node_uid") and isinstance(value, str):
                    found.add(value)
                elif key == SNAPSHOT_STEPS_KEY and isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            found.add(item)
                        else:
                            walk(item)
                elif key in _LEGACY_STEP_LIST_KEYS and isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            found.add(item)
                        else:
                            walk(item)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(snapshot)
    # accepts-both (UID_SHAPES): legacy 8-hex uids stay first-class forever;
    # every new governed mint is 12-hex composite since the Stage B flip
    # (2026-08-31). The literal `len(u) == 8` this replaced silently dropped
    # any composite step uid from the declared set.
    return {u for u in found if gp.is_governed_uid_shape(u)}


def _read_journal(path: Path) -> List[Dict[str, Any]]:
    if not Path(path).is_file():
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


@dataclass(frozen=True)
class AuthorizationVerdict:
    authorized: bool
    refusal_class: Optional[str] = None
    detail: str = ""

    @property
    def refused(self) -> bool:
        return not self.authorized


_AUTHORIZED = AuthorizationVerdict(True)


def _refuse(refusal_class: str, detail: str) -> AuthorizationVerdict:
    return AuthorizationVerdict(False, refusal_class, detail)


def authorize(
    envelope: Dict[str, Any],
    context: AuthorizationContext,
    prior_events: Sequence[Dict[str, Any]] = (),
) -> AuthorizationVerdict:
    """Authorize one run-journal row against observed substrate.

    `prior_events` is the run journal as it stands. Note what is NOT a
    parameter: any identity the caller would like this event to be measured
    against. Those come from `context`, which came from substrate.
    """
    if not isinstance(envelope, dict):
        raise ReleaseEventError("envelope must be a dict")

    event = envelope.get("event")
    contract = RELEASE_EVENTS.get(event)
    if contract is None:
        return _refuse(
            REFUSAL_UNREGISTERED,
            "%r is not in the release event table; the vocabulary is closed" % (event,),
        )

    # --- envelope shape ---------------------------------------------------- #
    missing = [k for k in ENVELOPE_REQUIRED if k not in envelope]
    if missing:
        return _refuse(
            REFUSAL_ENVELOPE, "envelope missing %s" % ", ".join(sorted(missing))
        )
    unknown = [
        k for k in envelope if k not in ENVELOPE_REQUIRED and k not in ENVELOPE_NULLABLE
    ]
    if unknown:
        return _refuse(
            REFUSAL_ENVELOPE, "envelope has unknown key(s) %s" % ", ".join(sorted(unknown))
        )
    # 3d8d4351 §4: `actor` carries the PRINCIPAL UID, never a display name
    # (Mike-ruled 2026-08-30: "a UID should always be referenced"). Shape-
    # guarded here at the closed layer so no writer can forge a human-seeming
    # machine row again — the :206 "actor": "mike" class dies at authorization,
    # not just at the one cured writer. Flat 8/12-hex like every governed uid.
    import re as _re
    _actor = envelope.get("actor")
    if not isinstance(_actor, str) or not _re.fullmatch(r"[0-9a-f]{8}(?:[0-9a-f]{4})?", _actor):
        return _refuse(
            REFUSAL_ENVELOPE,
            "actor %r must be a flat-hex UID (principal UID for humans, "
            "engine UID for machine rows) — names are for humans, UIDs for "
            "records; actor_label_resolved carries the readable name" % (_actor,),
        )
    if envelope.get("schema_version") != 2:
        return _refuse(REFUSAL_ENVELOPE, "schema_version must be 2")
    if not envelope.get("span_id"):
        return _refuse(REFUSAL_ENVELOPE, "span_id must be present and unique")
    if any(
        row.get("span_id") == envelope.get("span_id") for row in prior_events
    ):
        return _refuse(REFUSAL_ENVELOPE, "span_id is not unique within the run")

    # trace_id is the activation UID — the run's spine, not a free label.
    if envelope.get("trace_id") != context.activation_uid:
        return _refuse(
            REFUSAL_IDENTITY,
            "trace_id %r is not this run's activation %r"
            % (envelope.get("trace_id"), context.activation_uid),
        )

    data = envelope.get("data")
    if not isinstance(data, dict):
        return _refuse(REFUSAL_ENVELOPE, "data must be an object")

    # --- data shape -------------------------------------------------------- #
    missing = [k for k in contract.required_data if k not in data]
    if missing:
        return _refuse(
            REFUSAL_DATA_MISSING,
            "%s missing required data %s" % (event, ", ".join(sorted(missing))),
        )
    extra = [k for k in data if k not in contract.required_data]
    if extra:
        return _refuse(
            REFUSAL_DATA_UNKNOWN,
            "%s carries unknown data key(s) %s; extra keys refuse so the row's "
            "shape cannot drift silently" % (event, ", ".join(sorted(extra))),
        )

    # --- identity ---------------------------------------------------------- #
    for key in _IDENTITY_KEYS:
        if key not in data:
            continue
        observed = context.identity_value(key)
        if observed and str(data[key]) != observed:
            return _refuse(
                REFUSAL_IDENTITY,
                "%s claims %s=%r; substrate observes %r"
                % (event, key, data[key], observed),
            )

    # --- stepped events must belong to the immutable snapshot -------------- #
    if contract.stepped:
        step_uid = data.get("instrument_step_uid")
        if envelope.get("step") not in (None, step_uid):
            return _refuse(
                REFUSAL_STEP,
                "envelope step %r disagrees with instrument_step_uid %r"
                % (envelope.get("step"), step_uid),
            )
        if context.snapshot_step_uids and step_uid not in context.snapshot_step_uids:
            return _refuse(
                REFUSAL_STEP,
                "step %r is not in this run's declaration snapshot. Resolving in "
                "the live Vault is not the same fact: a node added after the run "
                "started is not this run's node" % (step_uid,),
            )
    elif envelope.get("step") is not None:
        return _refuse(
            REFUSAL_STEP, "%s must set step:null; only receipts are stepped" % event
        )

    # --- cardinality ------------------------------------------------------- #
    same_event = [row for row in prior_events if run_journal_event_type(row) == event]
    if contract.terminal and same_event:
        return _refuse(
            REFUSAL_CARDINALITY,
            "%s is terminal and already present in this run" % event,
        )
    if contract.dedup_keys and not contract.terminal:
        signature = tuple(str(data.get(k)) for k in contract.dedup_keys)
        for row in same_event:
            prior = row.get("data") or {}
            if tuple(str(prior.get(k)) for k in contract.dedup_keys) == signature:
                return _refuse(
                    REFUSAL_CARDINALITY,
                    "%s already recorded for %s"
                    % (
                        event,
                        ", ".join(
                            "%s=%s" % (k, data.get(k)) for k in contract.dedup_keys
                        ),
                    ),
                )

    return _AUTHORIZED
