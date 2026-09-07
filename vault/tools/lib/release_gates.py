"""The release gate registry: one gate vocabulary, five truthful boundaries.

Dev-spec 2fae6312 (locked), implementation step 3.

THE RULE THIS ENCODES. The upstream brief asked for "every gate before
ignition", which cannot be met literally — package verification cannot run
before package bytes exist, and the release entry is born by the lock itself.
The enforceable rule is stronger and honest:

    every gate runs at the earliest boundary where all of its required inputs
    exist, and never first speaks after an irreversible act it could have
    preceded.

WHY THE PHASE IS COMPUTED AND NOT DECLARED. If a gate could name its own
boundary, the cheapest way to make a failing gate pass would be to move it
later — ideally to just after the push it was supposed to prevent. So a gate
declares only what it needs. :data:`INPUT_FIRST_AVAILABLE` — a table this
module owns, which no gate can extend or amend — says when each input first
exists in the world, and :func:`first_evaluable_phase` takes the latest of
them. A gate that names an input the table does not know is refused at
registration rather than granted a phase of its choosing.

That asymmetry is the whole design. Gates describe their inputs; the registry
decides when they run.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "PHASES",
    "PREFLIGHT_EVIDENCE_FILENAME",
    "INPUT_FIRST_AVAILABLE",
    "ReleaseGateError",
    "Gate",
    "GateOutcome",
    "GateRegistry",
    "first_evaluable_phase",
    "phase_index",
    "write_evidence",
]


# --------------------------------------------------------------------------- #
# Phases — ordered, closed                                                     #
# --------------------------------------------------------------------------- #

PHASES: Tuple[str, ...] = (
    "lock-static",
    "candidate",
    "pre-freeze",
    "pre-outward-fire",
    "post-publication-reconcile",
)

_PHASE_INDEX: Dict[str, int] = {name: i for i, name in enumerate(PHASES)}


def phase_index(phase: str) -> int:
    try:
        return _PHASE_INDEX[phase]
    except KeyError:
        raise ReleaseGateError(
            "unknown phase %r; the phase set is closed: %s"
            % (phase, ", ".join(PHASES))
        )


# --------------------------------------------------------------------------- #
# The input table — owned here, never by a gate                                #
# --------------------------------------------------------------------------- #

#: When each release input FIRST EXISTS. Keyed by input name, valued by phase.
#: This table is the independent half of the contract. Adding a row is a
#: deliberate amendment to the release model; a gate cannot do it by declaring
#: a dependency, because unknown inputs are refused at registration.
INPUT_FIRST_AVAILABLE: Dict[str, str] = {
    # Pure planning facts — true before anything is built.
    "release_plan": "lock-static",
    "fan_in_manifest": "lock-static",
    "member_states": "lock-static",
    "version_string": "lock-static",
    "changelog_prose": "lock-static",
    "briefing_prose": "lock-static",
    "source_tree": "lock-static",
    "shipped_tool_corpus": "lock-static",
    "governed_index": "lock-static",
    "capsule_law": "lock-static",
    "release_entry": "lock-static",
    "pipeline_run": "lock-static",
    "saga_id": "lock-static",
    # Candidate bytes exist.
    "candidate_bytes": "candidate",
    "package_sha256": "candidate",
    "package_manifest": "candidate",
    "extracted_tree": "candidate",
    # Evidence bound to those bytes, gathered before the freeze.
    "runtime_receipt": "pre-freeze",
    "instrument_evidence": "pre-freeze",
    "package_link_report": "pre-freeze",
    # The freeze has happened; nothing outward has.
    "frozen_package": "pre-outward-fire",
    "staged_release_commit": "pre-outward-fire",
    "staged_site_commit": "pre-outward-fire",
    "provider_credentials": "pre-outward-fire",
    "provider_reachability": "pre-outward-fire",
    "remote_identity": "pre-outward-fire",
    "fire_authorization": "pre-outward-fire",
    # Only true after an irreversible public act.
    "published_refs": "post-publication-reconcile",
    "github_release_object": "post-publication-reconcile",
    "public_asset_observations": "post-publication-reconcile",
    "published_manifest": "post-publication-reconcile",
    "site_endpoint_observation": "post-publication-reconcile",
    "publication_receipt": "post-publication-reconcile",
}


# --------------------------------------------------------------------------- #
# Failure taxonomy                                                             #
# --------------------------------------------------------------------------- #

#: A refusal is a determinate verdict about the release: the world says no, and
#: running again changes nothing. An operational error is the gate failing to
#: reach an answer — a provider timeout, an unreadable file. The two must never
#: be conflated: a refusal treated as operational invites a retry loop around a
#: real defect, and an operational error treated as a refusal fails a release
#: that was never actually judged.
#: THE preflight evidence filename. Declared here, beside the only writer, and
#: IMPORTED by every reader — never re-typed.
#:
#: Why a constant rather than two matching literals: it was two literals, and
#: they disagreed. `write_evidence` created "preflight.jsonl" while the PREFLIGHT
#: sequence gate in tropo-release.py checked for "preflight-journal.jsonl" — a
#: name nothing in the studio ever wrote. The gate refused every run that HAD
#: passed preflight, and its refusal told the operator to run preflight again,
#: which wrote the name the gate could not see. A permanent wedge on the release
#: fire, reachable only by following the refusal's own instructions.
#:
#: It survived because the test suite read the WRITER's name and was green: the
#: tests proved the writer agreed with itself. Two of three readers matching is
#: what a green suite looks like in this failure family.
#:
#: (argus-a165, 2026-08-31, found by a substrate sweep and reproduced from the
#: shipped source on both sides. Regression: tests/test_preflight_evidence_name_parity.py)
PREFLIGHT_EVIDENCE_FILENAME = "preflight.jsonl"

FAILURE_REFUSAL = "refusal"
FAILURE_OPERATIONAL = "operational-error"

VERDICT_PASS = "pass"
VERDICT_REFUSED = "refused"
VERDICT_ERROR = "operational-error"
VERDICT_SKIPPED = "skipped-inputs-absent"


class ReleaseGateError(RuntimeError):
    """Registry misuse. Never a release verdict."""


def first_evaluable_phase(required_inputs: Sequence[str]) -> str:
    """The earliest phase at which every required input exists.

    A gate with no inputs is evaluable immediately. Otherwise the answer is the
    LATEST first-availability among its inputs, because a gate cannot run until
    the last thing it reads exists.
    """
    if not required_inputs:
        return PHASES[0]
    latest = 0
    for name in required_inputs:
        if name not in INPUT_FIRST_AVAILABLE:
            raise ReleaseGateError(
                "unknown release input %r. A gate may not introduce inputs: the "
                "input-to-phase table is what stops a gate from choosing its own "
                "boundary. Add the input to INPUT_FIRST_AVAILABLE deliberately, "
                "with the phase at which it genuinely first exists." % (name,)
            )
        latest = max(latest, phase_index(INPUT_FIRST_AVAILABLE[name]))
    return PHASES[latest]


@dataclass(frozen=True)
class Gate:
    """One release gate.

    Note what is absent: there is no ``first_evaluable_phase`` field. The phase
    is derived from :attr:`required_inputs` through the registry's own table,
    so a gate cannot place itself after the act it exists to prevent.
    """

    gate_id: str
    refusal_class: str
    required_inputs: Tuple[str, ...]
    verifier: Callable[[Dict[str, Any]], "GateOutcome"]
    #: A phase at which this gate MUST run again even after passing, because
    #: its subject can change underneath it (remote identity, provider state).
    mandatory_revalidation_phase: Optional[str] = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.gate_id:
            raise ReleaseGateError("a gate needs a stable id")
        if not self.refusal_class:
            raise ReleaseGateError(
                "gate %r needs a refusal class; an unclassified failure is the "
                "unnamed nonzero exit this registry exists to remove" % self.gate_id
            )
        if not callable(self.verifier):
            raise ReleaseGateError("gate %r needs a callable verifier" % self.gate_id)
        # Raises on unknown inputs — the anti-gaming edge.
        computed = first_evaluable_phase(self.required_inputs)
        if self.mandatory_revalidation_phase is not None:
            revalidation = phase_index(self.mandatory_revalidation_phase)
            if revalidation < phase_index(computed):
                raise ReleaseGateError(
                    "gate %r would revalidate at %s, before its inputs exist at %s"
                    % (self.gate_id, self.mandatory_revalidation_phase, computed)
                )

    @property
    def first_evaluable_phase(self) -> str:
        return first_evaluable_phase(self.required_inputs)

    def inputs_fingerprint(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """What this gate actually read, and whether it was present."""
        return {
            name: {
                "present": name in context and context[name] is not None,
                "first_available": INPUT_FIRST_AVAILABLE[name],
            }
            for name in self.required_inputs
        }

    def runs_at(self, phase: str) -> bool:
        """True when this gate speaks at `phase`.

        A gate speaks at its earliest truthful boundary, and again at any
        declared revalidation phase. It does not re-run at every later phase:
        repeating a settled verdict is noise, and noise is what taught this
        crew to stop reading gate output.
        """
        if phase == self.first_evaluable_phase:
            return True
        return phase == self.mandatory_revalidation_phase


@dataclass(frozen=True)
class GateOutcome:
    """A gate's typed answer. Never an exception, never a bare exit code."""

    gate_id: str
    verdict: str
    detail: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.verdict in (VERDICT_PASS, VERDICT_SKIPPED)

    @property
    def failure_kind(self) -> Optional[str]:
        if self.verdict == VERDICT_REFUSED:
            return FAILURE_REFUSAL
        if self.verdict == VERDICT_ERROR:
            return FAILURE_OPERATIONAL
        return None


class GateRegistry:
    """The roster, and the only thing that decides when a gate runs."""

    def __init__(self) -> None:
        self._gates: Dict[str, Gate] = {}

    def register(self, gate: Gate) -> Gate:
        if gate.gate_id in self._gates:
            raise ReleaseGateError(
                "gate %r is already registered; two implementations of one gate "
                "is how the wrong one stays wired" % gate.gate_id
            )
        self._gates[gate.gate_id] = gate
        return gate

    def __len__(self) -> int:
        return len(self._gates)

    def __contains__(self, gate_id: object) -> bool:
        return gate_id in self._gates

    def get(self, gate_id: str) -> Gate:
        try:
            return self._gates[gate_id]
        except KeyError:
            raise ReleaseGateError("no gate registered as %r" % gate_id)

    def all_gates(self) -> List[Gate]:
        return [self._gates[k] for k in sorted(self._gates)]

    def gates_for_phase(self, phase: str) -> List[Gate]:
        phase_index(phase)  # validate
        return [gate for gate in self.all_gates() if gate.runs_at(phase)]

    def unreached_gates(self, phases_run: Iterable[str]) -> List[Gate]:
        """Gates that no executed phase would have invoked.

        The coverage question, asked of the registry itself: a gate that is
        registered but never scheduled is indistinguishable from a gate that
        passed, unless something counts.
        """
        scheduled = set()
        for phase in phases_run:
            scheduled.update(gate.gate_id for gate in self.gates_for_phase(phase))
        return [gate for gate in self.all_gates() if gate.gate_id not in scheduled]

    def run_phase(
        self, phase: str, context: Dict[str, Any]
    ) -> List[GateOutcome]:
        """Run every gate that speaks at `phase`.

        A verifier that raises is converted into a typed operational error
        rather than being allowed to become an unclassified nonzero exit. A
        verifier that returns something other than a GateOutcome is a
        programming defect and raises.
        """
        outcomes: List[GateOutcome] = []
        for gate in self.gates_for_phase(phase):
            missing = [
                name
                for name in gate.required_inputs
                if context.get(name) is None
            ]
            if missing:
                outcomes.append(
                    GateOutcome(
                        gate_id=gate.gate_id,
                        verdict=VERDICT_SKIPPED,
                        detail=(
                            "inputs absent at %s: %s" % (phase, ", ".join(missing))
                        ),
                        evidence={"inputs": gate.inputs_fingerprint(context)},
                    )
                )
                continue
            try:
                outcome = gate.verifier(context)
            except Exception as exc:  # noqa: BLE001 — the classification point
                outcome = GateOutcome(
                    gate_id=gate.gate_id,
                    verdict=VERDICT_ERROR,
                    detail="%s: %s" % (type(exc).__name__, exc),
                )
            if not isinstance(outcome, GateOutcome):
                raise ReleaseGateError(
                    "gate %r returned %r, not a GateOutcome"
                    % (gate.gate_id, type(outcome).__name__)
                )
            if outcome.gate_id != gate.gate_id:
                raise ReleaseGateError(
                    "gate %r returned an outcome labelled %r"
                    % (gate.gate_id, outcome.gate_id)
                )
            outcomes.append(outcome)
        return outcomes


def write_evidence(
    run_dir: Path, phase: str, outcomes: Sequence[GateOutcome], registry: GateRegistry,
    tree_commit: Optional[str] = None,
) -> Path:
    """Append this phase's gate evidence to the release run.

    Written per phase rather than per release so a run that dies mid-flight
    still shows which boundaries were reached and what each one said.

    `tree_commit` (v1.95 Spine B, f015997f8d8e AC2): the HEAD of the tree the
    phase ran against, supplied by the caller from its context. The runner
    refuses to build unless a clean lock-static set names the commit it is
    about to build (AC3); a row that cannot say which tree it judged cannot
    be that evidence, so callers that know the tree pass it and callers that
    do not leave it null rather than guess.

    `ts` (v1.95 Spine B, f015997f8d8e AC5; talos-t62, ruled by argus-a171
    2026-09-05): the UTC instant the row was written. AC5's live half asserts
    that a clean lock-static set PRECEDES `candidate_built`, and prints both
    timestamps when it does not — with no `ts` on these rows there was exactly
    one timestamp between the two the AC asks for, and the sequencing could not
    be evaluated at all. Additive: every reader keys by name, so nothing that
    reads verdict/gate_id/tree_commit changes.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / PREFLIGHT_EVIDENCE_FILENAME
    with path.open("a", encoding="utf-8") as handle:
        for outcome in outcomes:
            gate = registry.get(outcome.gate_id)
            handle.write(
                json.dumps(
                    {
                        "phase": phase,
                        "gate_id": outcome.gate_id,
                        "verdict": outcome.verdict,
                        "refusal_class": gate.refusal_class,
                        "failure_kind": outcome.failure_kind,
                        "first_evaluable_phase": gate.first_evaluable_phase,
                        "mandatory_revalidation_phase": (
                            gate.mandatory_revalidation_phase
                        ),
                        "required_inputs": list(gate.required_inputs),
                        "detail": outcome.detail,
                        "evidence": outcome.evidence,
                        "tree_commit": tree_commit or None,
                        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    return path
