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
)


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
    parser.add_argument("--phase", required=True, choices=list(PHASES))
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
    args = parser.parse_args(argv)

    vault = Path(args.vault).resolve()
    registry = build_registry()

    if args.list:
        for gate in registry.gates_for_phase(args.phase):
            print(
                "%-24s %-28s inputs=%s"
                % (gate.gate_id, gate.refusal_class, ",".join(gate.required_inputs))
            )
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

    context: Dict[str, Any] = {
        "source_tree": str(vault),
        "shipped_tool_corpus": str(vault / "vault" / "tools"),
    }

    try:
        outcomes = registry.run_phase(args.phase, context)
    except ReleaseGateError as exc:
        print("[MISUSE] %s" % exc, file=sys.stderr)
        return EXIT_MISUSE

    print("--- release preflight: %s (%d gate(s)) ---" % (args.phase, len(outcomes)))
    for outcome in outcomes:
        print("[%s] %s — %s" % (outcome.verdict.upper(), outcome.gate_id, outcome.detail))

    if args.run_dir:
        path = write_evidence(Path(args.run_dir), args.phase, outcomes, registry)
        print("evidence: %s" % path)

    unreached = registry.unreached_gates([args.phase])
    if unreached and args.phase == PHASES[-1]:
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
