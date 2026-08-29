#!/usr/bin/env python3
"""---
uid: 5cf1a2b7
type: tool
name: tropo-release-preflight
title: tropo-release-preflight.py — run the release gates for one boundary
status: active
owner: talos
extraction_scope: ship
schema_version: 2
created: '2026-08-16'
created_by: talos-t44
built_under: '2fae6312'
---

tropo-release-preflight.py — run the release gates for one boundary.

Dev-spec 2fae6312 (locked), implementation step 3. The thin CLI adapter over
`lib/release_gates.py`, in the same shape as the saga's CLI adapters: the
module owns the vocabulary and the scheduling, this file owns argument
handling, evidence placement, and the exit contract.

    python3 vault/tools/tropo-release-preflight.py --phase lock-static \\
        --run-dir playbook-runs/<release-run>/

WHAT THE EXIT CODE MEANS. The point of the registry is that a failure is
classified, so the exit code is too:

    0  every gate that spoke at this boundary passed
    2  at least one REFUSAL — a determinate verdict; running again changes
       nothing until the world changes
    3  at least one OPERATIONAL ERROR — the gate could not reach an answer;
       this is the retryable class, and it is deliberately not 2
    4  misuse (unknown phase, unreadable run directory)

A release orchestrator can therefore branch on the class without parsing
prose, which is what makes "resume from verified world state" implementable
rather than aspirational.

THE ROSTER IS SMALL ON PURPOSE. Only gates whose production verifier exists
today are registered. Candidate identity, the four instruments, contextual
event authorization and the outward checkpoints arrive with steps 4-8 of the
spec and register here as they land. A gate is added by naming the inputs it
reads — never by naming the phase it would like to run at.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, Optional

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_gate_inputs as gate_inputs  # noqa: E402
from lib.release_gates import (  # noqa: E402
    PHASES,
    VERDICT_ERROR,
    VERDICT_PASS,
    VERDICT_REFUSED,
    Gate,
    GateOutcome,
    GateRegistry,
    ReleaseGateError,
    write_evidence,
)

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_OPERATIONAL = 3
EXIT_MISUSE = 4


def _load_validator():
    """The validator is a script, not a module; load it by path."""
    spec = importlib.util.spec_from_file_location(
        "tropo_validate_for_preflight", TOOLS / "tropo-validate.py"
    )
    if spec is None or spec.loader is None:
        raise ReleaseGateError("could not load tropo-validate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ship_python_floor(context: Dict[str, Any]) -> GateOutcome:
    """Shipped Python must run on the oldest interpreter a Studio presents.

    A lock-static gate in the exact sense the spec means: it reads the source
    tree, which exists before anything is built, so there is no honest reason
    for it to first speak after the package is published.
    """
    vault = Path(context["source_tree"])
    try:
        validator = _load_validator()
        findings, checked, defects = validator.check_ship_python_interpreter_floor(vault)
    except Exception as exc:  # noqa: BLE001 — classified, not swallowed
        return GateOutcome(
            gate_id="ship-python-floor",
            verdict=VERDICT_ERROR,
            detail="could not evaluate: %s: %s" % (type(exc).__name__, exc),
        )
    evidence = {"tools_checked": checked, "defects": defects, "findings": findings[:20]}
    if defects:
        return GateOutcome(
            gate_id="ship-python-floor",
            verdict=VERDICT_REFUSED,
            detail="%d shipped tool(s) would not run on Python 3.9" % defects,
            evidence=evidence,
        )
    return GateOutcome(
        gate_id="ship-python-floor",
        verdict=VERDICT_PASS,
        detail="%d shipped tool(s) run on the oldest supported interpreter" % checked,
        evidence=evidence,
    )


# --------------------------------------------------------------------------- #
# pre-outward-fire — S3 AC1 (176a8995)                                         #
# --------------------------------------------------------------------------- #

#: S3 AC1 (176a8995): every precondition the fire enforces, declared HERE so
#: there is ONE roster — `tropo-publish-release.py preflight` and the fire's
#: own pre-confirm pass both run this phase through this registry. Each row is
#: (gate_id, refusal_class, required_inputs, description); the description
#: names the cmd_fire refusal the gate pre-empts, because v1.90 met each of
#: them AFTER Mike typed y (62deeec1). The verifiers are supplied by the
#: publisher: every gate reads the publisher's staged world (publish-state.json,
#: the staged clone, the AC7 receipt set, its credentials), which this CLI has
#: no honest way to reach on its own — so `build_registry()` without them
#: registers none of these, and `--list` says so rather than listing gates that
#: cannot speak here.
PRE_OUTWARD_FIRE_ROSTER = (
    ("fire-staged-state", "stale-stage",
     ("version_string", "staged_release_commit", "staged_site_commit"),
     "the staged clone exists and its HEAD is the staged_sha "
     "(cmd_fire: STALE-STAGE, exit 7)"),
    ("fire-remote-identity", "remote-not-pinned",
     ("remote_identity", "staged_site_commit"),
     "the release remote is the pinned one and the staged clone's origin "
     "names it (cmd_fire exits 3 / 7)"),
    ("fire-transport", "transport-unproven",
     ("remote_identity", "provider_reachability"),
     "read-only `git ls-remote` reaches the pinned remote without a prompt, "
     "and an http(s) remote has a non-interactive credential (v1.90: "
     "'Username for https://github.com', 120s, after the confirm — S3 AC2)"),
    ("fire-receipt-set", "ac7-receipt-set",
     ("frozen_package", "staged_release_commit"),
     "the four-instrument receipt set is bound to the frozen package and the "
     "activation names release_entry_uid (cmd_fire exit 6)"),
    ("fire-authorization", "fire-unauthorized",
     ("fire_authorization", "version_string"),
     "the release-authorization key verifies with human signoff and "
     "CHANGELOG.md carries [version] (cmd_fire exit 4)"),
    ("fire-package-asset", "package-asset-missing",
     ("frozen_package",),
     "the zip is at dist/ and its sealed briefing notes name this version "
     "(cmd_fire exits 9 / 11)"),
    ("fire-release-entry", "release-entry-missing",
     ("version_string", "staged_release_commit"),
     "a type:release entry for this version exists for the shipped flip and "
     "the update manifest (cmd_fire exit 11)"),
    ("fire-gh-auth", "provider-credentials",
     ("provider_credentials",),
     "`gh auth status` is green for the release host, so `gh release create` "
     "will not refuse (cmd_fire exit 10)"),
    ("fire-supabase-credentials", "provider-credentials",
     ("provider_credentials",),
     "the Supabase URL and secret resolve (env or tropo-app/.env.local), so "
     "the zip + update-manifest upload will not refuse (cmd_fire exit 11)"),
    ("fire-badge-target", "badge-target-unreachable",
     ("provider_reachability",),
     "the website badge's deploy remote (S3 AC4 adapter) answers a read-only "
     "`git ls-remote` without a prompt, so the badge push will not hang"),
    # The eleventh gate, added 2026-08-26 by argus-a159 (Mike-approved) after an
    # adversarial review of the v1.93 release runner. v1.92.0 is public with an
    # open journal because the orchestrator step was skipped: no
    # orchestrator_invoked event -> an invalid scorecard -> completion never
    # observed -> "the release is public; the journal is not". Every gate in the
    # chain behaved correctly and nothing noticed until AFTER the outward act,
    # when the only remedy left is re-firing a live release. Knowable before
    # anything runs, so it belongs here, where refusing is free.
    ("fire-scorecard-inputs", "scorecard-inputs-missing",
     ("fire_authorization",),
     "the run journal carries tropo.release.orchestrator_invoked, so the "
     "release scorecard can be valid and the saga can close after the fire"),
)


# ---------------------------------------------------------------------------
# Stream 1 AC1 (5b608d28): the governance preconditions, registered as gates.
#
# Every row below is a refusal v1.91 discovered ONE AT A TIME, from inside the
# build, after the run had started. Each one was knowable before anything ran:
# their inputs are all planning facts, so the registry computes every one of
# them to lock-static. That is the whole point — a gate does not choose its
# boundary, and these could not have chosen a later one.
#
# The retro's Action 1 in one table. The observations note (56158edc §C1) asked
# for exactly this and called it "a release-readiness check that runs before the
# technical preflight and asserts the GOVERNANCE preconditions".
# ---------------------------------------------------------------------------

LOCK_STATIC_GOVERNANCE_ROSTER = (
    ("lock-plan-record", "release-plan-absent",
     ("release_plan",),
     "a release-plan record exists and is locked — v1.91 had none, and nothing "
     "said so until stage and fire could not resolve an activation (56158edc C1)"),
    ("lock-ratchet-targets", "ratchet-targets-empty",
     ("release_plan",),
     "the plan declares its ratchet targets; an empty declaration refused the "
     "BUILD in v1.91 although the produced bytes would have been identical"),
    ("lock-members-terminal", "member-not-done",
     ("fan_in_manifest", "member_states"),
     "every fan-in member is at a terminal done state before the plan locks; "
     "unsettled legs refused the build rather than the publish decision"),
    ("lock-criteria-readable", "criteria-not-where-the-gesture-reads",
     ("fan_in_manifest", "governed_index"),
     "every fan-in dev-spec carries acceptance_criteria where the lock gesture "
     "reads them; all four v1.91 specs carried theirs in the BODY and the "
     "gesture reads frontmatter, which is 29506520 AC8's whole subject"),
    ("lock-verify-commands-runnable", "verify-command-unrunnable",
     ("fan_in_manifest", "shipped_tool_corpus"),
     "every acceptance verify command names a target that exists; three locked "
     "v1.91 commands were placeholders and were only discovered at verification"),
    ("lock-target-release-current", "target-release-already-shipped",
     ("fan_in_manifest", "governed_index", "version_string"),
     "no fan-in member targets a release that already shipped; six specs sat "
     "locked against shipped versions, oldest 47 days, and nothing reported it"),
)


def _plan_frontmatter(context: Dict[str, Any]) -> Dict[str, Any]:
    """The release plan as data, or {} when it cannot be read.

    Callers distinguish "cannot see" from "is wrong": an unreadable plan is an
    operational error, never a refusal. "I cannot see" is never "you are wrong".
    """
    plan = context.get("release_plan")
    if isinstance(plan, dict):
        return plan
    return {}


def _governance_outcome(gate_id: str, failures: List[str], subject: str) -> GateOutcome:
    """One shape for all six: name every failure, never only the first."""
    if failures:
        return GateOutcome(
            gate_id=gate_id,
            verdict=VERDICT_REFUSED,
            detail="%s: %s" % (subject, "; ".join(failures)),
            evidence={"failures": list(failures), "count": len(failures)},
        )
    return GateOutcome(gate_id=gate_id, verdict=VERDICT_PASS)


def _lock_plan_record(context: Dict[str, Any]) -> GateOutcome:
    fm = _plan_frontmatter(context)
    if not fm:
        return GateOutcome(
            gate_id="lock-plan-record", verdict=VERDICT_ERROR,
            detail="the release plan could not be read as a record",
        )
    failures = []
    if not fm.get("uid"):
        failures.append("the plan record names no uid")
    if str(fm.get("status") or "") not in ("locked", "active", "design"):
        failures.append("plan status is %r, not a plan state" % fm.get("status"))
    return _governance_outcome("lock-plan-record", failures, "release plan")


def _lock_ratchet_targets(context: Dict[str, Any]) -> GateOutcome:
    fm = _plan_frontmatter(context)
    if not fm:
        return GateOutcome(
            gate_id="lock-ratchet-targets", verdict=VERDICT_ERROR,
            detail="the release plan could not be read as a record",
        )
    targets = fm.get("ratchet_targets")
    failures = []
    if targets is None:
        failures.append("ratchet_targets is undeclared")
    elif isinstance(targets, (list, tuple)) and not targets:
        failures.append("ratchet_targets is declared but empty")
    return _governance_outcome("lock-ratchet-targets", failures, "ratchet targets")


def _lock_members_terminal(context: Dict[str, Any]) -> GateOutcome:
    members = context.get("fan_in_manifest") or []
    states = context.get("member_states") or {}
    if not isinstance(states, dict):
        return GateOutcome(
            gate_id="lock-members-terminal", verdict=VERDICT_ERROR,
            detail="member_states is not a mapping",
        )
    failures = [
        "%s is %r" % (uid, states.get(uid))
        for uid in members
        if str(states.get(uid) or "") != "done"
    ]
    return _governance_outcome("lock-members-terminal", failures, "fan-in members")


def _lock_criteria_readable(context: Dict[str, Any]) -> GateOutcome:
    members = context.get("fan_in_manifest") or []
    index = context.get("governed_index") or {}
    if not isinstance(index, dict):
        return GateOutcome(
            gate_id="lock-criteria-readable", verdict=VERDICT_ERROR,
            detail="governed_index is not a mapping",
        )
    failures = []
    for uid in members:
        row = index.get(uid) or {}
        if row.get("type") != "dev-spec":
            continue
        if not row.get("acceptance_criteria"):
            failures.append("%s carries no acceptance_criteria in frontmatter" % uid)
    return _governance_outcome("lock-criteria-readable", failures, "acceptance criteria")


def _lock_verify_commands_runnable(context: Dict[str, Any]) -> GateOutcome:
    members = context.get("fan_in_manifest") or []
    index = context.get("governed_index") or {}
    root = Path(str(context.get("shipped_tool_corpus") or "."))
    failures = []
    for uid in members:
        row = index.get(uid) or {}
        for crit in (row.get("acceptance_criteria") or []):
            if not isinstance(crit, dict):
                continue
            command = str((crit.get("verify") or {}).get("command") or "")
            for token in command.split():
                if "/" not in token or token.startswith("-"):
                    continue
                if not (root / token).exists():
                    failures.append(
                        "%s %s names %s, which does not exist"
                        % (uid, crit.get("id") or "?", token)
                    )
    return _governance_outcome(
        "lock-verify-commands-runnable", failures, "verify commands")


def _lock_target_release_current(context: Dict[str, Any]) -> GateOutcome:
    members = context.get("fan_in_manifest") or []
    index = context.get("governed_index") or {}
    current = str(context.get("version_string") or "")
    if not isinstance(index, dict) or not current:
        return GateOutcome(
            gate_id="lock-target-release-current", verdict=VERDICT_ERROR,
            detail="need a governed index and the version being cut to compare",
        )
    # Shipped versions are DERIVED from the index this gate already declares,
    # not read from a second context key. A gate that declares one input and
    # reads another is the defect this whole stream exists to remove, and I
    # wrote one here before catching it.
    shipped = {
        str(row.get("release_version") or "")
        for row in index.values()
        if isinstance(row, dict) and row.get("type") == "release"
        and str(row.get("status") or "") == "shipped"
    } - {""}
    failures = [
        "%s targets %s, already shipped" % (uid, (index.get(uid) or {}).get("target_release"))
        for uid in members
        if str((index.get(uid) or {}).get("target_release") or "") in shipped
    ]
    return _governance_outcome(
        "lock-target-release-current", failures, "target releases")


GOVERNANCE_VERIFIERS = {
    "lock-plan-record": _lock_plan_record,
    "lock-ratchet-targets": _lock_ratchet_targets,
    "lock-members-terminal": _lock_members_terminal,
    "lock-criteria-readable": _lock_criteria_readable,
    "lock-verify-commands-runnable": _lock_verify_commands_runnable,
    "lock-target-release-current": _lock_target_release_current,
}


def register_governance_gates(registry: GateRegistry) -> GateRegistry:
    """Bind the lock-static roster. Same one-list discipline as the fire roster."""
    stray = sorted(set(GOVERNANCE_VERIFIERS) - {r[0] for r in LOCK_STATIC_GOVERNANCE_ROSTER})
    if stray:
        raise ReleaseGateError(
            "verifier(s) for gate(s) not on LOCK_STATIC_GOVERNANCE_ROSTER: %s"
            % ", ".join(stray)
        )
    for gate_id, refusal_class, inputs, description in LOCK_STATIC_GOVERNANCE_ROSTER:
        verifier = GOVERNANCE_VERIFIERS.get(gate_id)
        if verifier is None:
            raise ReleaseGateError("no verifier for governance gate %r" % gate_id)
        registry.register(
            Gate(
                gate_id=gate_id,
                refusal_class=refusal_class,
                required_inputs=tuple(inputs),
                verifier=verifier,
                description=description,
            )
        )
    return registry


def register_pre_outward_fire_gates(
    registry: GateRegistry, verifiers: Dict[str, Any]
) -> GateRegistry:
    """Bind the roster to the publisher's verifiers, one per row.

    A roster row with no verifier is registry misuse, not a skip: a gate that
    silently drops out of the phase is how a precondition reaches the human
    unchecked. A verifier for a gate the roster does not name is the second
    gate list forming, and is refused for the same reason.
    """
    roster_ids = {row[0] for row in PRE_OUTWARD_FIRE_ROSTER}
    stray = sorted(set(verifiers) - roster_ids)
    if stray:
        raise ReleaseGateError(
            "verifier(s) supplied for gate(s) not on PRE_OUTWARD_FIRE_ROSTER: %s "
            "— add the row here; this roster is the only list" % ", ".join(stray)
        )
    for gate_id, refusal_class, inputs, description in PRE_OUTWARD_FIRE_ROSTER:
        verifier = verifiers.get(gate_id)
        if verifier is None:
            raise ReleaseGateError(
                "no verifier supplied for pre-outward-fire gate %r" % gate_id
            )
        registry.register(
            Gate(
                gate_id=gate_id,
                refusal_class=refusal_class,
                required_inputs=tuple(inputs),
                verifier=verifier,
                description=description,
            )
        )
    return registry


def build_registry(fire_verifiers: Optional[Dict[str, Any]] = None) -> GateRegistry:
    registry = GateRegistry()
    # Stream 1 AC1: the governance preconditions, at the boundary the registry
    # computes for them — which is lock-static, because their inputs are all
    # planning facts. v1.91 met these one at a time from inside the build.
    register_governance_gates(registry)
    registry.register(
        Gate(
            gate_id="ship-python-floor",
            refusal_class="ship-interpreter-floor",
            required_inputs=("source_tree", "shipped_tool_corpus"),
            verifier=_ship_python_floor,
            description=(
                "PEP-604 annotations in shipped tools without postponed "
                "annotations or a declared 3.10+ floor"
            ),
        )
    )
    # S3 AC1 (176a8995): the pre-outward-fire roster, when the publisher
    # hands in the verifiers that can read its staged world.
    if fire_verifiers is not None:
        register_pre_outward_fire_gates(registry, fire_verifiers)
    return registry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the release gates for one truthful boundary."
    )
    parser.add_argument("--phase", required=True,
                        choices=list(PHASES) + ["all"],
                        help="a boundary, or 'all' to report every boundary in "
                             "one pass")
    parser.add_argument(
        "--vault", default=".", help="vault root (default: current directory)"
    )
    parser.add_argument(
        "--run-dir",
        help="release run folder; gate evidence is appended to preflight.jsonl",
    )
    parser.add_argument(
        "--list", action="store_true", help="list the gates for this phase and exit"
    )
    parser.add_argument(
        "--plan-uid",
        help="the release plan to evaluate against. Omitted, only the gates "
             "needing no plan can fire.",
    )
    parser.add_argument("--version-string", default="")
    args = parser.parse_args(argv)

    vault = Path(args.vault).resolve()
    registry = build_registry()

    if args.list:
        listed = registry.gates_for_phase(args.phase)
        for gate in listed:
            print(
                "%-30s %-34s inputs=%s"
                % (gate.gate_id, gate.refusal_class, ",".join(gate.required_inputs))
            )
        if not listed and args.phase != "pre-outward-fire":
            # Stream 1 AC1: an empty boundary says so. Printing nothing is
            # ambiguous between "no gates here" and "the listing broke", and
            # three boundaries stood empty for months behind that blank.
            print("(0 gates registered at %s)" % args.phase)
        if args.phase == "pre-outward-fire":
            # S3 AC1 (176a8995): the roster is declared here but its verifiers
            # live with the publisher's staged world; list it, and say where it runs.
            for gate_id, refusal_class, inputs, _description in PRE_OUTWARD_FIRE_ROSTER:
                print(
                    "%-24s %-28s inputs=%s  (runs via: tropo-publish-release.py "
                    "preflight --version <v>)"
                    % (gate_id, refusal_class, ",".join(inputs))
                )
        return EXIT_OK

    # v1.92 Stream 3 AC1/AC2 (61f3153a). This built a context of exactly
    # source_tree and shipped_tool_corpus, so six of seven lock-static gates
    # reported SKIPPED-INPUTS-ABSENT and the command exited 0 having evaluated
    # one precondition. The gates declared what they needed and nothing read it.
    # `shipped_tool_corpus` is the STUDIO ROOT now: verify commands are
    # studio-relative, and rooting them at vault/tools made
    # lock-verify-commands-runnable refuse on files that exist.
    try:
        context = gate_inputs.build_context(
            vault, args.plan_uid, version_string=args.version_string
        )
    except gate_inputs.GateInputError as exc:
        # An input that cannot be read is operational, never a verdict.
        print("[OPERATIONAL] %s" % exc, file=sys.stderr)
        return EXIT_OPERATIONAL

    phases = list(PHASES) if args.phase == "all" else [args.phase]
    outcomes = []
    try:
        for phase in phases:
            phase_outcomes = registry.run_phase(phase, context)
            print("--- release preflight: %s (%d gate(s)) ---"
                  % (phase, len(phase_outcomes)))
            if not phase_outcomes and phase != "pre-outward-fire":
                print("(0 gates registered at %s)" % phase)
            for outcome in phase_outcomes:
                print("[%s] %s — %s"
                      % (outcome.verdict.upper(), outcome.gate_id, outcome.detail))
            outcomes.extend(phase_outcomes)
    except ReleaseGateError as exc:
        print("[MISUSE] %s" % exc, file=sys.stderr)
        return EXIT_MISUSE

    if args.run_dir:
        path = write_evidence(Path(args.run_dir), args.phase, outcomes, registry)
        print("evidence: %s" % path)

    unreached = registry.unreached_gates(phases)
    if unreached and (args.phase == "all" or args.phase == PHASES[-1]):
        print(
            "[WARN] %d registered gate(s) were never scheduled: %s"
            % (len(unreached), ", ".join(g.gate_id for g in unreached))
        )

    if any(o.verdict == VERDICT_REFUSED for o in outcomes):
        return EXIT_REFUSED
    if any(o.verdict == VERDICT_ERROR for o in outcomes):
        return EXIT_OPERATIONAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
