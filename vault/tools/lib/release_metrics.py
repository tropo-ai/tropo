"""The scorecard: three gestures, four timestamps, and honest refusal counts.

Dev-spec 2fae6312 (locked), implementation step 8.

WHAT IS BEING MEASURED AND WHY IT IS EASY TO FAKE. The headline claim of this
package is that a release takes three principal gestures — lock, invoke,
authorize fire. That claim is trivially satisfiable by not counting the fourth
one. So the counting rule is written down rather than left to the writer:
machine continuation is NOT a gesture, and every manual resume or
re-invocation IS a principal input. A run that needed a human to nudge it back
to life took four gestures, and the scorecard has to say so.

The same shape governs the rest. Elapsed lock-to-all-targets-live includes
human waits, retries, provider latency and process loss, because that is the
number the operator actually lived through; active machine time is reported
beside it rather than instead of it. Refusals are counted as occurrences AND
distinct classes, because five refusals of one class and five of five are
different releases. And a refusal class absent from the versioned baseline is
NEW — never folded in, because a baseline that absorbs surprises measures
nothing.

Missing or invalid metrics make the scorecard non-passing. A scorecard with a
hole is not a partial measurement; it is a release nobody measured.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from lib.journal_event import run_journal_event_type  # noqa: E402

__all__ = [
    "PRINCIPAL_GESTURES",
    "EXTRA_INPUTS",
    "GESTURE_TARGET",
    "GESTURE_TARGETS_V2",
    "resolve_principal_uids",
    "derive_real_fire_verdict",
    "REHEARSAL",
    "REAL_FIRE",
    "ReleaseMetricsError",
    "load_refusal_baseline",
    "classify_refusals",
    "count_gestures",
    "scorecard_path",
    "build_scorecard",
    "validate_scorecard",
]


class ReleaseMetricsError(RuntimeError):
    """Misuse of this module. Never a release verdict."""


#: The three canonical principal inputs, in order.
PRINCIPAL_GESTURES: Tuple[str, ...] = (
    "release_scope_locked",
    "release_orchestrator_invoked",
    "release_fire_authorized",
)

#: Inputs that are ALSO principal gestures but are not part of the target.
#: Naming them explicitly is the point: they are counted, not excused.
EXTRA_INPUTS: Tuple[str, ...] = ("manual_resume", "manual_reinvocation")

GESTURE_TARGET = 3

REHEARSAL = "rehearsal"
REAL_FIRE = "real-fire"

SCORECARD_FILENAMES = {
    REHEARSAL: "one-prompt-rehearsal-scorecard.json",
    REAL_FIRE: "one-prompt-real-fire-scorecard.json",
}

BASELINE_PATH = Path(".tropo/release-refusal-baseline.json")


def load_refusal_baseline(vault: Path) -> Dict[str, Any]:
    """The versioned refusal baseline, with its digest re-verified.

    A baseline whose digest is not checked is a list of strings. Re-computing
    it here means an edited baseline announces itself instead of quietly
    reclassifying a new refusal as known.
    """
    path = Path(vault) / BASELINE_PATH
    if not path.is_file():
        # refusal: misuse — no refusal baseline file at the expected path
        raise ReleaseMetricsError("no refusal baseline at %s" % path)
    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        # refusal: misuse — the refusal baseline does not parse as JSON
        raise ReleaseMetricsError("refusal baseline does not parse: %s" % exc)

    recorded = baseline.get("composite_sha256")
    payload = json.dumps(
        {k: v for k, v in baseline.items() if k != "composite_sha256"},
        sort_keys=True,
        separators=(",", ":"),
    )
    computed = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if recorded != computed:
        # refusal: priced/false-success — an in-place edited baseline reclassifies genuinely new refusal classes as known, so the written scorecard records a passing verdict for a release whose refusal profile nobody measured
        raise ReleaseMetricsError(
            "refusal baseline digest does not match its contents (recorded %s, "
            "computed %s). Edits require a separately reviewed baseline version, "
            "not an in-place amendment" % (str(recorded)[:12], computed[:12])
        )
    return baseline


def classify_refusals(
    observed: Optional[Sequence[str]], baseline: Mapping[str, Any],
    coverage: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Split observed refusal IDs into known and new, and count both ways.

    `observed` is None when refusals were NOT RECORDED for this run. That is a
    different fact from an empty list, which asserts that none occurred, and
    conflating them is how a scorecard reports a clean night that nobody
    measured. v1.91 is the worked example: roughly twenty refusals, recorded
    only as prose in a retrospective, and a scorecard built with
    `observed_refusals=[]` would have said zero.

    `coverage` names the surfaces the count actually saw. Refusal telemetry is
    emitted by five tools in this Studio, not by every refusing surface — the
    validator, the lock and the freeze refuse without recording. A count that
    does not say what it covered invites being read as a total. (Stream 1 AC4;
    substrate amendment Mike-approved 2026-08-24.)
    """
    base = {
        "baseline_version": baseline.get("baseline_version", ""),
        "baseline_composite_sha256": baseline.get("composite_sha256", ""),
        "classifier_version": baseline.get("classifier_version", ""),
        "coverage": sorted(coverage) if coverage else [],
    }
    if observed is None:
        return dict(
            base,
            recorded=False,
            occurrences=None,
            distinct_classes=None,
            known=[],
            unknown=[],
        )
    known_ids = {row["id"] for row in baseline.get("classes", [])}
    known = [r for r in observed if r in known_ids]
    unknown = [r for r in observed if r not in known_ids]
    return dict(
        base,
        recorded=True,
        occurrences=len(observed),
        distinct_classes=len(set(observed)),
        known=sorted(set(known)),
        unknown=sorted(set(unknown)),
    )


def count_gestures(inputs: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Count principal inputs against the three-gesture target.

    `inputs` is the recorded sequence of PRINCIPAL inputs only. Machine
    continuation never appears here — if it does, that is a caller defect and
    it raises rather than being silently dropped, because dropping it is
    precisely how a four-gesture run reports three.
    """
    recorded: List[Dict[str, str]] = []
    for index, item in enumerate(inputs):
        name = item.get("input")
        if name not in PRINCIPAL_GESTURES and name not in EXTRA_INPUTS:
            # refusal: misuse — a caller-supplied input name is not a principal input
            raise ReleaseMetricsError(
                "input[%d] %r is not a principal input. Machine continuation is "
                "not a gesture and must not be recorded as one; a manual resume "
                "is, and must be recorded as manual_resume" % (index, name)
            )
        if not item.get("at"):
            # refusal: misuse — a caller-supplied input row carries no timestamp
            raise ReleaseMetricsError("input[%d] %r has no timestamp" % (index, name))
        recorded.append({"input": str(name), "at": str(item["at"])})

    extras = [i for i in recorded if i["input"] in EXTRA_INPUTS]
    missing = [g for g in PRINCIPAL_GESTURES if g not in {i["input"] for i in recorded}]
    met = not extras and not missing and len(recorded) == GESTURE_TARGET

    if met:
        detail = "three principal gestures, no manual bridge"
    elif missing and not extras:
        detail = "incomplete: %s not recorded" % ", ".join(missing)
    else:
        detail = (
            "%d principal input(s) — the target is %d, and %d manual "
            "intervention(s) mean the machine did not continue on its own: %s"
            % (
                len(recorded),
                GESTURE_TARGET,
                len(extras),
                ", ".join(sorted({e["input"] for e in extras})) or "none",
            )
        )

    return {
        "principal_inputs": recorded,
        "target": GESTURE_TARGET,
        "met": met,
        "detail": detail,
    }




# ── 3d8d4351 §4: the v2 verdict contract ────────────────────────────────── #
#
# REAL_FIRE verdict is one of fired-one-gesture / refused-then-attested /
# failed, derived from journal rows ONLY, ACTOR-AWARE: a principal gesture is
# a journal row whose `actor` resolves to a human principal in the principal
# registry (names never appear in actor — the carrier's shape guard sees to
# that); machine-authored rows (the engine's stamp included, marked by
# invoked_via) never count. all_targets_live_at leaves the predicate —
# completion facts remain the completion verifier's.

#: Per-mode gesture targets (schema v2). REAL_FIRE's ratchet is <= 2 human
#: gestures (the lock and the go/no-go); REHEARSAL keeps the classic three.
GESTURE_TARGETS_V2: Dict[str, int] = {REAL_FIRE: 2, REHEARSAL: 3}

#: The journal event classes that evidence each REAL_FIRE verdict shape.
FIRE_AUTHORIZED_EVENT = "tropo.release.fire_authorized"
ATTESTED_PATH_EVENT = "tropo.release.verify_only_invoked"
PUBLISHED_EVENT = "tropo.release.published"

#: The gesture CLASSES (the ratchet's "the lock and the go/no-go" — plus the
#: legacy orchestrator invocation, which a principal may still run bare).
#: Completion facts (published) and measurements are NOT gestures: counting
#: them would charge the human for the machine's own success.
GESTURE_EVENT_CLASSES: Tuple[str, ...] = (
    "tropo.release.scope_locked",
    "tropo.release.orchestrator_invoked",
    FIRE_AUTHORIZED_EVENT,
)


def resolve_principal_uids(registry_path: Path) -> set:
    """Human principals from the agent registry (stdlib-only block parse).

    A row is a principal when its block carries `type: human`; its identity
    is the block's `party_uid`. Deliberately minimal: the registry is
    hand-maintained YAML with one nested agents map, and importing a YAML
    implementation to read eight blocks would make the metrics module depend
    on a parser it does not otherwise need. Unreadable registry -> empty set:
    the verdict then sees zero principal gestures and fails honestly rather
    than crashing mid-release.
    """
    try:
        text = registry_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    principals: set = set()
    current: Dict[str, str] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        if not raw.startswith(("    ", "	")) and stripped.endswith(":") and current:
            # a new top-level-ish block begins; flush
            if current.get("type") == "human" and current.get("party_uid"):
                principals.add(current["party_uid"])
            current = {}
        for key in ("type", "party_uid"):
            prefix = key + ":"
            if stripped.startswith(prefix):
                current[key] = stripped[len(prefix):].strip().split("#", 1)[0].strip()
    if current.get("type") == "human" and current.get("party_uid"):
        principals.add(current["party_uid"])
    return principals


def _is_machine_row(row: Mapping[str, Any]) -> bool:
    invoked_via = row.get("invoked_via")
    return bool(invoked_via) and invoked_via != ""


def derive_real_fire_verdict(
    journal_rows: Sequence[Mapping[str, Any]],
    principal_uids: set,
) -> Dict[str, Any]:
    """The triple, from rows. Never reads the world — rows only.

    Returns the verdict plus its DERIVATION (the span_ids that produced it),
    because a verdict a human cannot audit against its rows is exactly the
    opacity this schema exists to remove.
    """
    principal_rows = [
        r for r in journal_rows
        if run_journal_event_type(r) in GESTURE_EVENT_CLASSES
        and r.get("actor") in principal_uids and not _is_machine_row(r)
    ]
    fire_by_principal = any(
        run_journal_event_type(r) == FIRE_AUTHORIZED_EVENT for r in principal_rows)
    attested_path = any(
        run_journal_event_type(r) == ATTESTED_PATH_EVENT for r in journal_rows)
    published = any(run_journal_event_type(r) == PUBLISHED_EVENT for r in journal_rows)

    if fire_by_principal and published and len(principal_rows) <= GESTURE_TARGETS_V2[REAL_FIRE]:
        verdict = "fired-one-gesture"
    elif (not fire_by_principal) and attested_path and published:
        verdict = "refused-then-attested"
    else:
        verdict = "failed"

    return {
        "verdict": verdict,
        "principal_gesture_rows": [
            {"span_id": r.get("span_id"), "event": run_journal_event_type(r)} for r in principal_rows
        ],
        "derivation": {
            "fire_authorized_by_principal": fire_by_principal,
            "attested_path_row": attested_path,
            "published_row": published,
            "principal_gesture_count": len(principal_rows),
            "target": GESTURE_TARGETS_V2[REAL_FIRE],
        },
    }


def count_gestures_v2(
    journal_rows: Sequence[Mapping[str, Any]],
    principal_uids: set,
    mode: str,
) -> Dict[str, Any]:
    """Actor-aware gesture tally over journal rows (schema v2).

    v1's count_gestures trusted the caller to pre-filter principal inputs;
    v2 derives the same question from rows the journal actually holds.
    """
    target = GESTURE_TARGETS_V2[mode]
    principal_rows = [
        r for r in journal_rows
        if run_journal_event_type(r) in GESTURE_EVENT_CLASSES
        and r.get("actor") in principal_uids and not _is_machine_row(r)
    ]
    met = len(principal_rows) <= target if mode == REAL_FIRE else len(principal_rows) == target
    return {
        "principal_inputs": [
            {"event": run_journal_event_type(r), "at": r.get("ts")} for r in principal_rows
        ],
        "target": target,
        "met": met,
        "detail": "%d principal gesture(s) against a target of %d%s" % (
            len(principal_rows), target,
            " (machine rows never count)" if principal_rows else ""),
    }


def build_scorecard_v2(
    *,
    mode: str,
    saga_id: str,
    pipeline_run_uid: str,
    release_version: str,
    journal_rows: Sequence[Mapping[str, Any]],
    principal_registry_path: Path,
    timestamps: Mapping[str, Optional[str]],
    active_machine_seconds: Optional[float],
    observed_refusals: Optional[Sequence[str]],
    baseline: Mapping[str, Any],
    refusal_coverage: Optional[Sequence[str]] = None,
    checkpoints_performed: Optional[int] = None,
) -> Dict[str, Any]:
    """Schema v2: the verdict is derived, actor-aware, and auditable.

    REAL_FIRE verdict comes from derive_real_fire_verdict; REHEARSAL keeps
    the pass/fail domain and gains checkpoints_performed.
    all_targets_live_at is RECORDED when present and never verdict-bearing —
    completion facts belong to the completion verifier.
    """
    principal_uids = resolve_principal_uids(principal_registry_path)
    refusals = classify_refusals(
        observed_refusals, baseline, coverage=refusal_coverage)

    card: Dict[str, Any] = {
        "schema_version": 2,
        "mode": mode,
        "saga_id": saga_id,
        "pipeline_run_uid": pipeline_run_uid,
        "release_version": release_version,
        "gestures": count_gestures_v2(journal_rows, principal_uids, mode),
        "timestamps": {k: timestamps.get(k) for k in (
            "scope_locked_at", "orchestrator_started_at", "primary_live_at",
            "all_targets_live_at")},
        "elapsed": {
            "lock_to_primary_live_seconds": _elapsed_seconds(
                timestamps.get("scope_locked_at"),
                timestamps.get("primary_live_at")),
            "active_machine_seconds": active_machine_seconds,
        },
        "refusals": refusals,
    }

    if mode == REAL_FIRE:
        derived = derive_real_fire_verdict(journal_rows, principal_uids)
        card["verdict"] = derived["verdict"]
        card["verdict_derivation"] = derived["derivation"]
        card["principal_gesture_rows"] = derived["principal_gesture_rows"]
    else:
        gestures_met = card["gestures"]["met"]
        stamps_ok = all(timestamps.get(k) is not None for k in (
            "scope_locked_at", "orchestrator_started_at", "primary_live_at"))
        refusals_ok = refusals.get("recorded", True) and not refusals.get("unknown")
        card["verdict"] = "pass" if (gestures_met and stamps_ok and refusals_ok) else "fail"
        card["checkpoints_performed"] = checkpoints_performed

    return card

def scorecard_path(run_folder: Path, mode: str) -> Path:
    if mode not in SCORECARD_FILENAMES:
        # refusal: misuse — the scorecard mode argument is not one of the two
        raise ReleaseMetricsError(
            "mode must be %s" % " or ".join(sorted(SCORECARD_FILENAMES))
        )
    return Path(run_folder) / SCORECARD_FILENAMES[mode]


def _elapsed_seconds(start: Optional[str], end: Optional[str]) -> Optional[float]:
    if not start or not end:
        return None
    from datetime import datetime

    fmt = "%Y-%m-%dT%H:%M:%SZ"
    try:
        return (datetime.strptime(end, fmt) - datetime.strptime(start, fmt)).total_seconds()
    except ValueError as exc:
        # refusal: misuse — a timestamp is not in the required format
        raise ReleaseMetricsError("timestamps must be %s: %s" % (fmt, exc))


def build_scorecard(
    *,
    mode: str,
    saga_id: str,
    pipeline_run_uid: str,
    release_version: str,
    principal_inputs: Sequence[Mapping[str, Any]],
    timestamps: Mapping[str, Optional[str]],
    active_machine_seconds: Optional[float],
    observed_refusals: Optional[Sequence[str]],
    baseline: Mapping[str, Any],
    refusal_coverage: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Assemble one scorecard. Verdict is derived, never supplied."""
    if mode not in SCORECARD_FILENAMES:
        # refusal: misuse — the scorecard mode argument is unknown
        raise ReleaseMetricsError("unknown scorecard mode %r" % mode)

    required_stamps = (
        "scope_locked_at",
        "orchestrator_started_at",
        "primary_live_at",
        "all_targets_live_at",
    )
    missing_keys = [k for k in required_stamps if k not in timestamps]
    if missing_keys:
        # refusal: misuse — the caller's timestamps mapping is missing required keys
        raise ReleaseMetricsError(
            "timestamps missing %s; a scorecard with a hole is not a partial "
            "measurement" % ", ".join(missing_keys)
        )

    gestures = count_gestures(principal_inputs)
    refusals = classify_refusals(
        observed_refusals, baseline, coverage=refusal_coverage)
    elapsed = {
        "lock_to_all_targets_live_seconds": _elapsed_seconds(
            timestamps.get("scope_locked_at"), timestamps.get("all_targets_live_at")
        ),
        "active_machine_seconds": active_machine_seconds,
    }

    verdict = "pass"
    if not gestures["met"]:
        verdict = "fail"
    elif any(timestamps.get(k) is None for k in required_stamps):
        verdict = "fail"
    elif elapsed["lock_to_all_targets_live_seconds"] is None:
        verdict = "fail"
    elif not refusals.get("recorded", True):
        # A missing measurement cannot pass. The schema says so; this enforces
        # it for the refusal block the same way it already does for timestamps.
        verdict = "fail"
    elif refusals["unknown"]:
        verdict = "fail"

    return {
        "schema_version": 1,
        "mode": mode,
        "saga_id": saga_id,
        "pipeline_run_uid": pipeline_run_uid,
        "release_version": release_version,
        "gestures": gestures,
        "timestamps": {k: timestamps.get(k) for k in required_stamps},
        "elapsed": elapsed,
        "refusals": refusals,
        "verdict": verdict,
    }


def validate_scorecard(scorecard: Mapping[str, Any], schema_path: Path) -> List[str]:
    """Validate against the closed schema. Returns findings; empty is valid.

    Uses `jsonschema` when the machine has it and falls back to a structural
    check that enforces the same closed-object and required-key rules. The
    fallback is narrower, and says so, rather than passing everything and
    calling that validation.
    """
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    # 3d8d4351 §4: the v2 bindings a closed declarative schema cannot say —
    # verdict DOMAIN follows mode, gesture TARGET follows mode. Runs on both
    # validator paths (jsonschema and the structural fallback).
    findings_v2: List[str] = []
    if scorecard.get("schema_version") == 2:
        mode = scorecard.get("mode")
        verdict = scorecard.get("verdict")
        if mode == REAL_FIRE and verdict not in (
                "fired-one-gesture", "refused-then-attested", "failed"):
            findings_v2.append(
                "verdict: real-fire verdict must be the journal-derived triple, "
                "got %r" % (verdict,))
        if mode == REHEARSAL and verdict not in ("pass", "fail"):
            findings_v2.append(
                "verdict: rehearsal keeps the pass/fail domain, got %r" % (verdict,))
        elapsed = scorecard.get("elapsed") or {}
        anchors = [k for k in ("lock_to_primary_live_seconds",
                               "lock_to_all_targets_live_seconds")
                   if elapsed.get(k) is not None]
        if len(anchors) != 1:
            findings_v2.append(
                "elapsed: exactly one lock anchor expected (v2 = primary_live), "
                "found %s" % (anchors or "none"))
        target = (scorecard.get("gestures") or {}).get("target")
        expected_target = GESTURE_TARGETS_V2.get(mode)
        if expected_target is not None and target != expected_target:
            findings_v2.append(
                "gestures.target: expected %d for mode %r, got %r"
                % (expected_target, mode, target))
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return _structural_check(scorecard, schema) + findings_v2

    validator = jsonschema.Draft202012Validator(schema)
    return [
        "%s: %s" % ("/".join(str(p) for p in e.path) or "<root>", e.message)
        for e in sorted(validator.iter_errors(scorecard), key=lambda e: list(e.path))
    ] + findings_v2


_JSON_TYPES = {
    "string": str,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _type_findings(value: Any, schema: Mapping[str, Any], where: str) -> List[str]:
    """Enforce `type`, `minLength`, `pattern`, `minItems` — the scalar contract.

    THE FALLBACK USED TO SKIP ALL OF THIS, and that is how an invalid real-fire
    scorecard validated clean on every machine without `jsonschema` installed
    (which is every machine in this studio). `release_version: ""` passed
    minLength 1; `timestamps.scope_locked_at: null` passed type ["string"]. A
    validator that answers VALID for something it never examined is the
    false-success class the release doctrine names by name — worse than no
    validator, because it is quoted as evidence.

    Recursion into objects/arrays stays where it was; this only adds the leaf
    constraints the old code walked straight past.
    (argus-a158, 2026-08-25.)
    """
    findings: List[str] = []
    declared = schema.get("type")
    if declared is not None:
        allowed = declared if isinstance(declared, list) else [declared]
        ok = False
        for name in allowed:
            if name == "null":
                if value is None:
                    ok = True
            elif name in ("integer", "number"):
                if isinstance(value, bool):
                    continue
                if name == "integer" and isinstance(value, int):
                    ok = True
                elif name == "number" and isinstance(value, (int, float)):
                    ok = True
            else:
                expected = _JSON_TYPES.get(name)
                # bool is a subclass of int; guard the reverse direction too.
                if expected is not None and isinstance(value, expected):
                    if expected is not bool and isinstance(value, bool):
                        continue
                    ok = True
            if ok:
                break
        if not ok:
            findings.append(
                "%s: expected type %r, got %s" % (where, declared, type(value).__name__)
            )
            return findings
    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            findings.append(
                "%s: shorter than minLength %d (value %r)" % (where, min_length, value)
            )
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            try:
                if re.search(pattern, value) is None:
                    findings.append("%s: %r does not match %r" % (where, value, pattern))
            except re.error:
                pass
    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            findings.append("%s: fewer than minItems %d" % (where, min_items))
    return findings


def _structural_check(value: Any, schema: Mapping[str, Any], where: str = "<root>") -> List[str]:
    findings: List[str] = []
    if "const" in schema:
        if value != schema["const"]:
            findings.append("%s: expected %r" % (where, schema["const"]))
        return findings
    if "enum" in schema:
        if value not in schema["enum"]:
            findings.append("%s: %r not in %r" % (where, value, schema["enum"]))
        return findings
    findings.extend(_type_findings(value, schema, where))
    if findings:
        return findings
    if schema.get("type") == "object":
        if not isinstance(value, dict):
            findings.append("%s: expected an object" % where)
            return findings
        for key in schema.get("required", []):
            if key not in value:
                findings.append("%s: missing required %r" % (where, key))
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    findings.append("%s: unexpected key %r" % (where, key))
        for key, subschema in properties.items():
            if key in value:
                findings.extend(
                    _structural_check(value[key], subschema, "%s/%s" % (where, key))
                )
    elif schema.get("type") == "array" and isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                findings.extend(
                    _structural_check(item, item_schema, "%s[%d]" % (where, index))
                )
    return findings
