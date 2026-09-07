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
import ast
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_gate_inputs as gate_inputs  # noqa: E402
from lib import build_guards  # noqa: E402
from lib import release_capsule_contract as contract  # noqa: E402
from lib.release_gates import (  # noqa: E402
    PHASES,
    VERDICT_ERROR,
    VERDICT_PASS,
    VERDICT_REFUSED,
    VERDICT_SKIPPED,
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
    vault = Path(_tree(context, "source_tree"))
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
    # The capsule's enum, ONE declared set (lib/release_capsule_contract.PLAN_STATUSES).
    # This gate carried its own hand list of three states (locked, active, design), which lacked
    # `specify` -- the plan's correct post-walk state -- and refused Mike's v1.95
    # ignition on it. Two readers of one fact, one of them wrong (talos-t63, 2026-09-06,
    # f015ef8ff398 step 2).
    status = str(fm.get("status") or "").strip().lower()
    if status not in contract.PLAN_STATUSES:
        failures.append("plan status is %r, not a plan state (%s)"
                        % (fm.get("status"), "/".join(sorted(contract.PLAN_STATUSES))))
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


#: v1.95 Spine B, plan-owner ruling 2026-09-05 (metis-g121, verbatim "REFUSE"):
#: an unresolvable `python3 -m unittest` id is the SAME defect as a missing path
#: in another notation, and whether an id resolves is mechanically decidable —
#: which is where Mike's 2026-09-01 rule allows a refusal rather than a warning.
#: Her harm, in her sentence: a spec whose declared verification surface does not
#: exist can be closed and locked carrying a criterion nobody can ever run, and
#: the plan's Definition of Done becomes a false claim at fire.
#:
#: Resolution is STATIC — ast.parse, never import. Importing a test module to
#: check a name would execute it, at lock, on the plan owner's tree.

def _unittest_ids(command: str) -> list:
    """The dotted ids a `python3 -m unittest ...` command names."""
    tokens = command.split()
    if "unittest" not in tokens:
        return []
    ident = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")
    found = []
    for token in tokens[tokens.index("unittest") + 1:]:
        if token.startswith("-"):
            continue
        if not ident.match(token):
            break   # the command ended; prose follows ("then on the v1.95 run:")
        found.append(token)
    return found


def _unresolvable_id(root: Path, dotted: str):
    """None if the id resolves in this tree, else a one-line reason."""
    parts = dotted.split(".")
    rest = None
    for cut in range(len(parts), 0, -1):
        candidate = root.joinpath(*parts[:cut]).with_suffix(".py")
        if candidate.is_file():
            rest = parts[cut:]
            break
    if rest is None:
        return "no module file for %s" % dotted
    if not rest:
        return None
    try:
        tree = ast.parse(candidate.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return "%s does not parse (%s)" % (candidate.name, exc.msg)
    node = tree
    for name in rest:
        found = None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and child.name == name:
                found = child
                break
        if found is None:
            # An inherited member is legitimate: a TestCase subclass may declare
            # none of the methods it runs. Only an unresolvable name on a class
            # with NO bases is decidably absent.
            if isinstance(node, ast.ClassDef) and node.bases:
                return None
            return "%s has no %s" % (candidate.name, name)
        node = found
    return None


def _lock_verify_commands_runnable(context: Dict[str, Any]) -> GateOutcome:
    members = context.get("fan_in_manifest") or []
    index = context.get("governed_index") or {}
    root = Path(str(context.get("shipped_tool_corpus") or "."))
    failures = []
    skipped_manual = []
    skipped_placeholders = []
    for uid in members:
        row = index.get(uid) or {}
        for crit in (row.get("acceptance_criteria") or []):
            if not isinstance(crit, dict):
                continue
            verify = crit.get("verify") or {}
            # A MANUAL criterion's `command` is prose by the capsule's own design
            # ("recorded at lock / walk"), not a shell line. Reading its slashes as
            # paths refused the v1.94 lock on 5854773a AC6 ("Mike's one-word
            # keep/suppress recorded here"). Skip it -- and EMIT the skip, so a
            # gate that evaluated nothing cannot read as a gate that passed
            # (2026-09-03, metis-g118; Talos owns this tool and was told).
            if str(verify.get("method") or "").strip().lower() == "manual":
                skipped_manual.append("%s %s" % (uid, crit.get("id") or "?"))
                continue
            command = str(verify.get("command") or "")
            # A verify command is a SHELL LINE, not a path list. Reading each
            # raw whitespace token as a path made this gate refuse two TRUE rows
            # at the v1.95 ignition: AC6's token is the literal
            # `open('vault/00-index.jsonl')` — a valid `python -c`, and the file
            # is on disk — and AC5's is `vault/pipeline-runs/<v195-run>`, a
            # declared placeholder for a folder that cannot exist before the run
            # is created. Mike 2026-09-01: a gate asserts only what is
            # mechanically decidable; everything else warns.
            # (argus-a172 + metis-g121, 2026-09-05.)
            for dotted in _unittest_ids(command):
                why = _unresolvable_id(root, dotted)
                if why:
                    failures.append(
                        "%s %s names test id %s, which does not resolve (%s)"
                        % (uid, crit.get("id") or "?", dotted, why))
            for raw in command.split():
                # A path inside a call expression is not at the token's ends,
                # so trimming leaves `open('vault/00-index.jsonl`. Decompose the
                # token on wrapper punctuation instead and judge each piece.
                #
                # NOT by pairing quotes: `"rows=open('p')"` nests them, and a
                # paired regex captured `rows=open(` and `)` while never seeing
                # the path — so the positive arm passed VACUOUSLY, with the path
                # unchecked. The absent-path known-negative is what exposed that;
                # a cure with only the happy arm would have shipped it.
                for token in re.split(r"""['"()`,;\[\]{}]""", raw):
                    token = token.strip()
                    if "<" in token and ">" in token:
                        # A parameter, by every spec convention. EMIT the skip:
                        # a gate that quietly evaluated nothing must not read as
                        # a gate that passed — the rule the manual-criteria skip
                        # above already follows.
                        skipped_placeholders.append(
                            "%s %s %s" % (uid, crit.get("id") or "?", token))
                        continue
                    if "/" not in token or token.startswith("-"):
                        continue
                    if not (root / token).exists():
                        failures.append(
                            "%s %s names %s, which does not exist"
                            % (uid, crit.get("id") or "?", token)
                        )
    outcome = _governance_outcome(
        "lock-verify-commands-runnable", failures, "verify commands")
    notes = []
    if skipped_manual:
        notes.append("%d manual criteria not evaluated (manual by declaration): %s"
                     % (len(skipped_manual), ", ".join(skipped_manual)))
    if skipped_placeholders:
        notes.append("%d placeholder token(s) not resolved (parameters, by declaration): %s"
                     % (len(skipped_placeholders), ", ".join(skipped_placeholders)))
    if notes and not failures:
        outcome = GateOutcome(
            gate_id="lock-verify-commands-runnable", verdict=VERDICT_PASS,
            detail="; ".join(notes),
            evidence={"skipped_manual": list(skipped_manual),
                      "skipped_placeholders": list(skipped_placeholders)},
        )
    elif notes:
        outcome.evidence["skipped_manual"] = list(skipped_manual)
        outcome.evidence["skipped_placeholders"] = list(skipped_placeholders)
    return outcome


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


# ---------------------------------------------------------------------------
# v1.95 Spine B (f015997f8d8e): the BUILD's own guards, registered.
#
# tropo-build-release.py called its guards directly, in sequence, so the box
# failed at the first one each attempt — v1.94 took eight — and this preflight
# could not see them. Each row here wraps a pure check from lib/build_guards
# (one definition, two readers). A guard reading the assembled box declares
# ("extracted_tree",) and the registry computes it to candidate; a guard
# reading only the source tree declares ("source_tree",) and lands at
# lock-static. No row names its phase. First guard registered 2026-09-05 by
# argus-a171 as the shape proof; the census in AC1 follows in this roster.
# ---------------------------------------------------------------------------

BUILD_GUARD_ROSTER = (
    # ── candidate: readers of the assembled box ──
    ("build-mission-brief-slot", "confidentiality-leak-in-boot-slot",
     ("extracted_tree",),
     "the shipped .tropo-studio/mission-brief.md is present and is the generic "
     "<FILL: …> template — Argo's real crew brief once shipped verbatim as every "
     "customer studio's own mission, and that publication cannot be recalled "
     "(task 2ffda37e defect #1)"),
    ("build-shipped-surfaces", "box-missing-declared-surface",
     ("extracted_tree",),
     "the box carries 00-tropo-nav (non-empty) and the five workspace folders — "
     "both shipped silently missing in the v1.74 release walk (RT1/RT2, 1ee11d09); "
     "a box without its declared surfaces is a quiet hole every stranger opens"),
    ("build-no-stale-system-dir", "one-home-layout-regression",
     ("extracted_tree",),
     "system/ is absent and vault/updates/ present — ADR-045 One Home moved them "
     "together; a box on neither layout cannot apply its own updates"),
    ("build-no-studio-identity", "shipped-studio-identity",
     ("extracted_tree",),
     "no .tropo/studio-identity.md and no vault-entity record in the box — every "
     "customer who unzips a box carrying one begins life as the SAME Studio and "
     "their uids collide at the first federation; not recallable once downloaded "
     "(v1.95 Spine A AC1, Mike-ruled 2026-09-05)"),
    ("build-shadow-substitutions", "shadow-pair-unfulfilled",
     ("source_tree", "extracted_tree"),
     "every SHADOW designation substituted: twin in the box, source out — a "
     "withheld source with no twin is a hole where a document was promised"),
    ("build-release-harness", "box-fails-own-regression",
     ("source_tree", "extracted_tree"),
     "the box passes .tropo/scripts/test-harness-check.py — a release that fails "
     "its own mechanical regression froze a package digest every receipt then "
     "attested (Step 10.5, brief f13cc214)"),
    ("build-box-self-test", "box-self-test-red",
     ("extracted_tree",),
     "the shipped tropo-test.py --quick runs GREEN or YELLOW inside the box; RED "
     "refuses — a box whose own test surface fails inside itself was frozen and "
     "green-lit (v1.80 S2, be1979b6)"),
    ("build-box-registry-rows", "box-registry-empty",
     ("extracted_tree",),
     "subsystem-registry.jsonl in the box carries rows — an empty registry means "
     "regeneration never landed and the box is incomplete (v1.80 S2)"),
    # ── candidate: Spine A's reachability rows (f015de6b3a18 AC7), declared there,
    # registered here; none can pass on an empty box ──
    ("build-doc-currency", "dead-shipped-instruction",
     ("source_tree", "extracted_tree"),
     "every path a shipped instruction document names resolves inside the box — "
     "a reader following a dead link in a playbook is stranded in a box that "
     "certified itself complete (Spine A AC7 row a)"),
    ("build-no-shell-instructions", "shell-command-as-instruction",
     ("extracted_tree",),
     "no shipped concierge instruction is a bare shell command presented as prose "
     "— Po renders a clickable link, else an absolute path, never `open <path>` "
     "(Mike-ruled 2026-09-05; Spine A AC7 row b)"),
    ("build-changelog-names-version", "changelog-drift",
     ("extracted_tree", "version_string"),
     "the shipped CHANGELOG.md carries a `## [version]` entry for the version being "
     "shipped — a plain header promise drifted twice before the G83 gate (AC7 row c)"),
    ("build-memory-surfaces", "memory-sovereignty-surface-missing",
     ("extracted_tree",),
     "every boot-routed memory-sovereignty surface tropo-memory.capsule names ships "
     "and carries the rule (OP-14 in the principles; CLAUDE.md §Memory Writes) — "
     "an agent this box creates must never learn to pin memory in a harness store "
     "(Spine A AC6/AC7 row i)"),
    # ── lock-static: readers of the source tree only — these now speak BEFORE a
    # build is attempted, which is the whole compiler-loop point ──
    ("build-covenant-floor", "update-covenant-violation",
     ("source_tree",),
     "THE FLOOR TEST (ADR-049 layer 2, fc4874f4): the gauntlet catches a planted "
     "violation and the real run shows zero user-file churn — an update built "
     "from this tree would otherwise overwrite files a customer authored"),
    ("build-overwrite-guard", "deletion-of-governed-substrate",
     ("version_string",),
     "no existing build/testing dir for this version disagrees with it or lacks a "
     "version.md stamp — the V36 2026-04-30 scenario handed prior working content "
     "to an unconditional rmtree; --force is the deliberate case, via context"),
    ("build-no-absolute-paths", "machine-path-leak",
     ("source_tree",),
     "no file in the shipped tool corpus (vault/tools, .tropo/scripts) outside the "
     "allowlist carries an absolute machine path — "
     "v1.90 came one paste from public with three maintainer scripts hard-coded "
     "to one machine while the box's test-report certified their absence"),
    ("build-activation-key", "unreconstructable-identity-or-lineage",
     ("pipeline_run", "version_string"),
     "the Pipeline Activation Key minted at produce-release-folder verifies for "
     "this activation (or the attested-build fallback for this version) — a box "
     "built standalone is believed to have passed gates that never ran"),
)


def _tree(context: Dict[str, Any], key: str) -> str:
    """A path input the verifier is about to judge. Talos T62 measured
    (2026-09-05, evt_32a4374c291f9a09_00000005): run_phase treats an EMPTY
    string as present, so Path('') is the current directory and five box gates
    PASSED while judging the live Studio. The registry's absence rule is by
    phase, not by type (a settled Gate contract), so the cure lives here, in
    the verifiers that read paths: a blank path is an operational error that
    names itself, never a tree to judge."""
    value = context.get(key)
    if value is None or not str(value).strip():
        raise _BlankTreeInput("%s is blank in the context — the gate would judge the "
                              "current directory, not the box" % key)
    return str(value)


class _BlankTreeInput(RuntimeError):
    pass


def _problems_outcome(gate_id: str, problems, detail_ok: str, evidence=None) -> GateOutcome:
    """One shape for every build guard: name every problem, never only the first."""
    if problems:
        return GateOutcome(
            gate_id=gate_id, verdict=VERDICT_REFUSED,
            detail="; ".join(problems),
            evidence={"problems": list(problems), "count": len(problems), **(evidence or {})},
        )
    return GateOutcome(gate_id=gate_id, verdict=VERDICT_PASS, detail=detail_ok,
                       evidence=dict(evidence or {}))


def _build_shipped_surfaces(context: Dict[str, Any]) -> GateOutcome:
    return _problems_outcome(
        "build-shipped-surfaces",
        build_guards.shipped_surfaces_problems(_tree(context, "extracted_tree")),
        "00-tropo-nav + %d workspace folders present" % (len(build_guards.SHIPPED_SURFACES) - 1))


def _build_no_stale_system_dir(context: Dict[str, Any]) -> GateOutcome:
    return _problems_outcome(
        "build-no-stale-system-dir",
        build_guards.stale_system_dir_problems(_tree(context, "extracted_tree")),
        "system/ absent; vault/updates/ present")


def _build_no_studio_identity(context: Dict[str, Any]) -> GateOutcome:
    return _problems_outcome(
        "build-no-studio-identity",
        build_guards.studio_identity_problems(_tree(context, "extracted_tree")),
        "no studio-identity manifest and no vault-entity record in the box")


def _build_shadow_substitutions(context: Dict[str, Any]) -> GateOutcome:
    from lib import ship_verdict
    resolver = ship_verdict.build_resolver(_tree(context, "source_tree"))
    pairs = resolver.shadow_pairs()
    if not pairs:
        return GateOutcome(gate_id="build-shadow-substitutions", verdict=VERDICT_PASS,
                           detail="no SHADOW designations in this manifest")
    problems, confirmed = build_guards.shadow_substitution_problems(
        _tree(context, "extracted_tree"), pairs)
    return _problems_outcome(
        "build-shadow-substitutions", problems,
        "%d SHADOW pair(s) substituted" % len(confirmed), {"confirmed": confirmed})


def _build_release_harness(context: Dict[str, Any]) -> GateOutcome:
    problems, out = build_guards.release_harness_problems(
        _tree(context, "source_tree"), _tree(context, "extracted_tree"))
    return _problems_outcome("build-release-harness", problems,
                             "test-harness regression PASS", {"output": out[-2000:]})


def _build_box_self_test(context: Dict[str, Any]) -> GateOutcome:
    problems, out = build_guards.box_self_test_problems(_tree(context, "extracted_tree"))
    return _problems_outcome("build-box-self-test", problems,
                             "shipped self-test in-box GREEN/YELLOW", {"output": out[-2000:]})


def _build_box_registry_rows(context: Dict[str, Any]) -> GateOutcome:
    problems, note = build_guards.box_registry_rows_problems(_tree(context, "extracted_tree"))
    return _problems_outcome("build-box-registry-rows", problems, note)


def _build_covenant_floor(context: Dict[str, Any]) -> GateOutcome:
    problems, out = build_guards.covenant_floor_problems(_tree(context, "source_tree"))
    return _problems_outcome("build-covenant-floor", problems,
                             "gauntlet caught the planted violation; real run shows zero churn",
                             {"output": out[-2000:]})


def _build_mission_brief_slot(context: Dict[str, Any]) -> GateOutcome:
    problems = build_guards.mission_brief_slot_problems(_tree(context, "extracted_tree"))
    if problems:
        return GateOutcome(
            gate_id="build-mission-brief-slot",
            verdict=VERDICT_REFUSED,
            detail="mission-brief slot: %s" % "; ".join(problems),
            evidence={"problems": list(problems), "count": len(problems)},
        )
    return GateOutcome(
        gate_id="build-mission-brief-slot", verdict=VERDICT_PASS,
        detail="%s is the generic <FILL: …> template" % build_guards.MISSION_BRIEF_SLOT_REL,
    )


def _build_overwrite_guard(context: Dict[str, Any]) -> GateOutcome:
    releases_root = context.get("releases_root")
    if not releases_root:
        return GateOutcome(gate_id="build-overwrite-guard", verdict=VERDICT_ERROR,
                           detail="releases_root is not in the context; the roots seam could not be read")
    return _problems_outcome(
        "build-overwrite-guard",
        build_guards.overwrite_problems(context["version_string"], releases_root,
                                        force=bool(context.get("force"))),
        "no conflicting build/testing dir for v%s under %s" % (context["version_string"], releases_root))


def _build_no_absolute_paths(context: Dict[str, Any]) -> GateOutcome:
    return _problems_outcome(
        "build-no-absolute-paths",
        build_guards.absolute_path_problems(_tree(context, "source_tree")),
        "no absolute machine paths in committed files outside the allowlist")


def _build_activation_key(context: Dict[str, Any]) -> GateOutcome:
    problems, detail = build_guards.activation_key_problems(
        _tree(context, "source_tree"), context["pipeline_run"], context["version_string"])
    return _problems_outcome("build-activation-key", problems, detail)


def _build_doc_currency(context: Dict[str, Any]) -> GateOutcome:
    return _problems_outcome("build-doc-currency",
                             build_guards.doc_currency_problems(_tree(context, "source_tree"), _tree(context, "extracted_tree")),
                             "every shipped instruction reference resolves inside the box")


def _build_no_shell_instructions(context: Dict[str, Any]) -> GateOutcome:
    return _problems_outcome("build-no-shell-instructions",
                             build_guards.shell_instruction_problems(_tree(context, "extracted_tree")),
                             "no shipped concierge instruction is a shell command presented as prose")


def _build_changelog_names_version(context: Dict[str, Any]) -> GateOutcome:
    return _problems_outcome("build-changelog-names-version",
                             build_guards.changelog_names_version_problems(_tree(context, "extracted_tree"), context["version_string"]),
                             "CHANGELOG.md names v%s" % context["version_string"])


def _build_memory_surfaces(context: Dict[str, Any]) -> GateOutcome:
    return _problems_outcome("build-memory-surfaces",
                             build_guards.memory_surfaces_problems(_tree(context, "extracted_tree")),
                             "both memory-sovereignty surfaces ship and carry the rule")


BUILD_GUARD_VERIFIERS = {
    "build-mission-brief-slot": _build_mission_brief_slot,
    "build-doc-currency": _build_doc_currency,
    "build-no-shell-instructions": _build_no_shell_instructions,
    "build-changelog-names-version": _build_changelog_names_version,
    "build-memory-surfaces": _build_memory_surfaces,
    "build-overwrite-guard": _build_overwrite_guard,
    "build-no-absolute-paths": _build_no_absolute_paths,
    "build-activation-key": _build_activation_key,
    "build-shipped-surfaces": _build_shipped_surfaces,
    "build-no-stale-system-dir": _build_no_stale_system_dir,
    "build-no-studio-identity": _build_no_studio_identity,
    "build-shadow-substitutions": _build_shadow_substitutions,
    "build-release-harness": _build_release_harness,
    "build-box-self-test": _build_box_self_test,
    "build-box-registry-rows": _build_box_registry_rows,
    "build-covenant-floor": _build_covenant_floor,
}


def register_build_gates(registry: GateRegistry) -> GateRegistry:
    """Bind the build-guard roster. Same one-list discipline as the other two."""
    stray = sorted(set(BUILD_GUARD_VERIFIERS) - {r[0] for r in BUILD_GUARD_ROSTER})
    if stray:
        raise ReleaseGateError(
            "verifier(s) for gate(s) not on BUILD_GUARD_ROSTER: %s" % ", ".join(stray)
        )
    for gate_id, refusal_class, inputs, description in BUILD_GUARD_ROSTER:
        verifier = BUILD_GUARD_VERIFIERS.get(gate_id)
        if verifier is None:
            raise ReleaseGateError("no verifier for build guard %r" % gate_id)
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
    # v1.95 Spine B: the build's guards, at the boundary the registry computes
    # for each (candidate for box readers, lock-static for tree readers).
    register_build_gates(registry)
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
    parser.add_argument(
        "--activation-uid", default=None,
        help="the release activation whose run minted the Pipeline Activation Key; "
             "omitted, build-activation-key reports skipped-inputs-absent (v1.95 Spine B)",
    )
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
            vault, args.plan_uid, version_string=args.version_string,
            activation_uid=args.activation_uid,
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
        path = write_evidence(Path(args.run_dir), args.phase, outcomes, registry,
                              tree_commit=context.get("tree_commit"))
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
