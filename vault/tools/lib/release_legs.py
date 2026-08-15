"""Release legs, attestation, and the wait before package freeze (0a0a6777 AC6).

AC6: "Release Assemble opens doc/test branches from release-run provenance and
package freeze refuses until each leg is terminal or independently attested; dev
runs never trigger them."

Three claims, and they fail in different ways:

  PROVENANCE   the legs belong to the RELEASE run that opened them. A leg opened
               from a dev cycle is a leg nobody can trace to the thing being
               packaged.
  WAIT         package freeze happens after both legs settle, never before.
               Freezing early produces an artifact that claims completeness it
               does not have, and once published that claim cannot be withdrawn
               from whatever consumed it.
  ATTESTATION  "terminal" is not the only honest way for a leg to settle. Work
               can be legitimately out of scope, deferred, or verified by other
               means — and a gate with no path for that is a gate the crew
               learns to route around. So attestation is a FIRST-CLASS
               alternative, not a bypass, and it carries the same evidentiary
               weight as completion because it is the same evidence class.

WHY ATTESTATION IS A GOVERNED RECORD AND NOT A FLAG
---------------------------------------------------
Ruled by Mike through argus-a148: same evidence class as the AC5 fan-in receipt.
It names the attester, the leg, the release run, and the tested SHA, and it is
refused if it does not resolve or names a different run. A boolean field, or a
lighter human sign-off event, would have created a second evidence language for
"done enough to freeze" sitting next to the one just accepted — two vocabularies
for one claim is how the release-plan lifecycle drifted, and it is not worth
repeating one stage later.

A human may be the attester. The substrate is still a governed entry.

REFUSALS AND THE WARN-SAFE LINE (deb77758)
------------------------------------------
Every refusal here is priced against the rule, and they all name the same
irreversible harm: a package frozen without proof that its legs settled is a
false-completion artifact, and publication cannot be recalled.

  leg incomplete       the wait condition is FALSE — refuse
  leg unreadable       the wait condition is UNPROVED, which for packaging is
                       the same harm. "I cannot see" is normally a third answer
                       and must not become "you are wrong" — but here the
                       question is not "did it pass", it is "may I freeze", and
                       an unproved yes is a no. Refuse and flag, so the operator
                       sees a missing leg rather than a failing one.
  attestation missing  no evidence at all
  attestation stale    names a different run, so it attests to other work
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

#: The legs Assemble opens. Named rather than discovered so that "both legs"
#: is a fixed claim and cannot quietly become "whichever legs happened to open".
RELEASE_LEGS = ("doc", "test")

#: A leg has settled by COMPLETION when its activation reaches one of these.
TERMINAL_LEG_STATUSES = frozenset(
    {"done", "closed", "complete", "shipped", "retired"}
)

#: An attestation is this type, and only this type (argus-a148 ruling).
ATTESTATION_TYPE = "leg-attestation"

#: What an attestation must bind, mirroring the AC5 fan-in row.
ATTESTATION_FIELDS = ("attester", "leg", "release_pipeline_run_uid",
                      "tested_commit_sha", "rationale")

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
UID_RE = re.compile(r"^[0-9a-f]{8}$")


class LegRefusal(Exception):
    """A leg cannot be shown to have settled, so packaging must not proceed."""


class TriggerProvenanceRefusal(Exception):
    """A leg would be opened from something other than a release run."""


@dataclass(frozen=True)
class LegState:
    leg: str
    settled: bool
    basis: str          # "terminal" | "attested" | "incomplete" | "unreadable"
    detail: str
    activation_uid: Optional[str] = None
    attestation_uid: Optional[str] = None


@dataclass(frozen=True)
class ReleaseTriggerProvenance:
    """The one existing AC6 identity chain for a release-opened leg."""

    activation_uid: str
    release_plan_uid: str
    release_run_uid: str


def assert_release_run_provenance(run_frontmatter: Optional[dict],
                                  release_pipeline_uid: str) -> str:
    """A leg is opened from a RELEASE run or not at all.

    This is the topology claim expressed at runtime. AC1 already removes the
    doc/test triggers from the dev graph, but a graph edit only governs the
    paths that read the graph — a leftover call site, a hand-run CLI, or a
    frozen v1 run still holds the old shape. Both are needed: the graph tells
    the truth, and the engine refuses if something asks anyway.

    Fail-closed, harm named: a cascade opened from a dev run creates doc/test
    activations that no release can trace, and the spawned activations are real
    substrate that outlives the mistake.
    """
    if run_frontmatter is None:
        raise TriggerProvenanceRefusal(
            "no parent pipeline-run resolves for this trigger, so the leg would "
            "have no provenance at all. AC6 opens legs from release-run "
            "provenance; a leg nobody can trace to a release is a leg nobody can "
            "package."
        )
    pipeline_uid = str(run_frontmatter.get("pipeline") or "")
    if pipeline_uid != release_pipeline_uid:
        raise TriggerProvenanceRefusal(
            f"the parent pipeline-run belongs to pipeline {pipeline_uid!r}, not the "
            f"release pipeline {release_pipeline_uid!r}. Dev runs never open doc or "
            "test legs (0a0a6777 AC6): the cascade belongs to the release that will "
            "package it, and a dev-opened leg is substrate the release cannot cite."
        )
    run_uid = str(run_frontmatter.get("uid") or "")
    if not UID_RE.match(run_uid):
        raise TriggerProvenanceRefusal(
            f"parent pipeline-run has no resolvable uid ({run_uid!r}); the leg "
            "could not record which run opened it."
        )
    return run_uid


def resolve_release_trigger_provenance(
    activation_frontmatter: dict,
    run_frontmatter: Optional[dict],
    release_pipeline_uid: str,
    read_entry: Callable[[str], Optional[dict]],
) -> ReleaseTriggerProvenance:
    """Resolve and cross-check release activation → run → plan provenance.

    AC6 already locates release legs through their parent pipeline-run. This
    function completes that same chain instead of introducing a second trigger
    ownership record: the release activation and run must name the same plan,
    and the locked plan's own ignition backreferences must name both of them.
    """
    run_uid = assert_release_run_provenance(run_frontmatter, release_pipeline_uid)
    run_frontmatter = run_frontmatter or {}
    activation_uid = str(activation_frontmatter.get("uid") or "")
    if not UID_RE.fullmatch(activation_uid):
        raise TriggerProvenanceRefusal(
            f"release activation has no resolvable uid ({activation_uid!r}); the "
            "triggered leg could not bind back to the activation that opened it."
        )

    activation_pipeline = str(
        activation_frontmatter.get("pipeline_uid")
        or activation_frontmatter.get("pipeline")
        or ""
    )
    if activation_pipeline != release_pipeline_uid:
        raise TriggerProvenanceRefusal(
            f"activation {activation_uid} belongs to pipeline "
            f"{activation_pipeline!r}, not release pipeline "
            f"{release_pipeline_uid!r}."
        )

    activation_run_uid = str(
        activation_frontmatter.get("pipeline_run_uid") or ""
    )
    if activation_run_uid != run_uid:
        raise TriggerProvenanceRefusal(
            f"release activation {activation_uid} names pipeline run "
            f"{activation_run_uid!r}, but the resolved parent run is {run_uid!r}."
        )

    run_activation_uid = str(
        run_frontmatter.get("activation")
        or run_frontmatter.get("substrate_authored_by")
        or ""
    )
    if run_activation_uid != activation_uid:
        raise TriggerProvenanceRefusal(
            f"release run {run_uid} names activation "
            f"{run_activation_uid!r}, not {activation_uid!r}."
        )

    activation_plan_uid = str(
        activation_frontmatter.get("release_plan_uid") or ""
    )
    run_plan_uid = str(run_frontmatter.get("release_plan_uid") or "")
    if not UID_RE.fullmatch(activation_plan_uid) or activation_plan_uid != run_plan_uid:
        raise TriggerProvenanceRefusal(
            f"release activation/run plan provenance disagrees: activation "
            f"{activation_uid} names {activation_plan_uid!r}, run {run_uid} names "
            f"{run_plan_uid!r}. A leg cannot belong to two release plans."
        )

    plan = read_entry(activation_plan_uid)
    if plan is None:
        raise TriggerProvenanceRefusal(
            f"release plan {activation_plan_uid!r} does not resolve; the leg "
            "would bind to a plan that is not there."
        )
    plan_fm = plan.get("frontmatter", plan)
    if str(plan_fm.get("type") or "") != "release-plan":
        raise TriggerProvenanceRefusal(
            f"release provenance {activation_plan_uid!r} resolves to "
            f"type {plan_fm.get('type')!r}, not 'release-plan'."
        )
    if str(plan_fm.get("release_activation_uid") or "") != activation_uid:
        raise TriggerProvenanceRefusal(
            f"release plan {activation_plan_uid} names activation "
            f"{plan_fm.get('release_activation_uid')!r}, not {activation_uid!r}."
        )
    if str(plan_fm.get("release_pipeline_run_uid") or "") != run_uid:
        raise TriggerProvenanceRefusal(
            f"release plan {activation_plan_uid} names run "
            f"{plan_fm.get('release_pipeline_run_uid')!r}, not {run_uid!r}."
        )

    return ReleaseTriggerProvenance(
        activation_uid=activation_uid,
        release_plan_uid=activation_plan_uid,
        release_run_uid=run_uid,
    )


def validate_attestation(entry: Optional[dict], leg: str,
                         release_run_uid: str) -> str:
    """A typed governed attestation for THIS leg of THIS run, or a refusal.

    Same shape of check as the fan-in receipt: every binding present, and every
    binding agreeing with the thing in hand. An attestation that resolves but
    names another run is the dangerous case — it looks like evidence and belongs
    to different work.
    """
    if entry is None:
        raise LegRefusal(
            f"the {leg} leg cites an attestation that does not resolve. A release "
            "cannot freeze on evidence that is not there."
        )
    fm = entry.get("frontmatter", entry)

    if str(fm.get("type") or "") != ATTESTATION_TYPE:
        raise LegRefusal(
            f"the {leg} leg's attestation is type {fm.get('type')!r}, not "
            f"{ATTESTATION_TYPE!r}. Attestation is one evidence class, the same one "
            "the fan-in receipt uses; an arbitrary entry carries no verdict."
        )

    missing = [f for f in ATTESTATION_FIELDS if not fm.get(f)]
    if missing:
        raise LegRefusal(
            f"the {leg} leg's attestation is missing {', '.join(missing)}. It must "
            "name who attested, to which leg, for which release run, against which "
            "tested tree, and why — an attestation without a rationale records "
            "that someone decided, not what they decided."
        )

    if str(fm.get("leg")) != leg:
        raise LegRefusal(
            f"the attestation is for the {fm.get('leg')!r} leg, not {leg!r}."
        )
    if str(fm.get("release_pipeline_run_uid")) != release_run_uid:
        raise LegRefusal(
            f"the {leg} leg's attestation names release run "
            f"{fm.get('release_pipeline_run_uid')!r}, not {release_run_uid!r}. It "
            "attests to other work; a release cannot freeze on somebody else's "
            "evidence."
        )
    if not COMMIT_RE.match(str(fm.get("tested_commit_sha"))):
        raise LegRefusal(
            f"the {leg} leg's attestation records tested_commit_sha "
            f"{fm.get('tested_commit_sha')!r}, which is not a 40-hex commit. An "
            "attestation that cannot name the tree it was made against binds "
            "nothing."
        )
    return str(fm.get("uid") or "")


def resolve_leg(leg: str, release_run_uid: str, leg_record: Optional[dict],
                read_entry: Callable[[str], Optional[dict]]) -> LegState:
    """Has this leg settled, and on what basis?

    `leg_record` is what the release run knows about the leg: its activation and,
    optionally, an attestation. Absent entirely means the leg was never opened.
    """
    if leg_record is None:
        return LegState(leg, False, "unreadable",
                        f"the release run records no {leg} leg at all, so whether "
                        "it settled cannot be determined")

    attestation_uid = leg_record.get("attestation_uid")
    if attestation_uid:
        uid = validate_attestation(read_entry(str(attestation_uid)), leg,
                                   release_run_uid)
        return LegState(leg, True, "attested",
                        f"independently attested by governed record {uid}",
                        leg_record.get("activation_uid"), uid)

    activation_uid = leg_record.get("activation_uid")
    if not activation_uid:
        return LegState(leg, False, "unreadable",
                        f"the {leg} leg names neither an activation nor an "
                        "attestation")

    activation = read_entry(str(activation_uid))
    if activation is None:
        return LegState(leg, False, "unreadable",
                        f"the {leg} leg's activation {activation_uid} does not "
                        "resolve, so its state cannot be read",
                        str(activation_uid))

    status = str((activation.get("frontmatter", activation)).get("status") or "").lower()
    if status in TERMINAL_LEG_STATUSES:
        return LegState(leg, True, "terminal",
                        f"activation {activation_uid} is {status}",
                        str(activation_uid))
    return LegState(leg, False, "incomplete",
                    f"activation {activation_uid} is {status!r}, which is not "
                    "terminal, and no attestation is recorded",
                    str(activation_uid))


def leg_records_from_events(events) -> dict:
    """What a release run knows about its doc and test legs, from its events.

    ONE DEFINITION, TWO READERS. The engine consults this at the wait step and
    the package build consults it again before freezing, and those two answers
    have to be the same answer. A second derivation living next to the build
    would drift the moment either side learned something the other did not --
    and the failure would be a package frozen against legs the engine still
    considered open, which is precisely the state AC6 exists to make
    impossible.

    Read from the run's own events rather than dev-spec frontmatter: AC6 moved
    the legs onto the release graph, so the release run owns them. An
    attestation is recorded the same way, by the gesture that decides to
    attest.
    """
    records: dict = {}
    for ev in events or []:
        data = ev.get("data") or {}
        leg = data.get("pipeline_class")
        if leg in ("doc-pipeline", "test-pipeline"):
            key = "doc" if leg == "doc-pipeline" else "test"
            entry = records.setdefault(key, {})
            if data.get("triggered_activation_uid"):
                entry["activation_uid"] = data["triggered_activation_uid"]
        attested = data.get("attested_leg")
        if attested in ("doc", "test") and data.get("attestation_uid"):
            records.setdefault(attested, {})["attestation_uid"] = data["attestation_uid"]
    return records


def assert_ready_to_freeze(release_run_uid: str, leg_records: dict,
                           read_entry: Callable[[str], Optional[dict]]) -> list:
    """The wait. Every leg settled, by completion or attestation, or refuse.

    Returns the resolved states so a caller can record WHY it was allowed to
    proceed — "both legs terminal" and "one attested" are different facts and a
    release should say which.

    Fail-closed, harm named (deb77758): a package frozen before its legs settle
    claims a completeness it does not have, and once published that claim cannot
    be withdrawn from whatever consumed it. Both the incomplete case and the
    unreadable case land there — for packaging the question is not "did it
    pass?" but "may I freeze?", and an unproved yes is a no.
    """
    states = [resolve_leg(leg, release_run_uid, leg_records.get(leg), read_entry)
              for leg in RELEASE_LEGS]

    blocking = [s for s in states if not s.settled]
    if blocking:
        lines = [f"  - {s.leg}: {s.basis} — {s.detail}" for s in blocking]
        raise LegRefusal(
            f"package freeze refused: {len(blocking)} of {len(states)} release "
            "leg(s) have not settled:\n" + "\n".join(lines)
            + "\n\nA leg settles by reaching terminal OR by an independent typed "
              "attestation naming this run and a tested tree. Freezing now would "
              "produce an artifact claiming a completeness it does not have, and "
              "publication cannot be recalled."
        )
    return states
