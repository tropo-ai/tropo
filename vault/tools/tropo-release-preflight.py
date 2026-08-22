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
from typing import Any, Dict

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


def build_registry() -> GateRegistry:
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
