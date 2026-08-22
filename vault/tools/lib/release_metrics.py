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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "PRINCIPAL_GESTURES",
    "EXTRA_INPUTS",
    "GESTURE_TARGET",
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
        raise ReleaseMetricsError("no refusal baseline at %s" % path)
    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ReleaseMetricsError("refusal baseline does not parse: %s" % exc)

    recorded = baseline.get("composite_sha256")
    payload = json.dumps(
        {k: v for k, v in baseline.items() if k != "composite_sha256"},
        sort_keys=True,
        separators=(",", ":"),
    )
    computed = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if recorded != computed:
        raise ReleaseMetricsError(
            "refusal baseline digest does not match its contents (recorded %s, "
            "computed %s). Edits require a separately reviewed baseline version, "
            "not an in-place amendment" % (str(recorded)[:12], computed[:12])
        )
    return baseline


def classify_refusals(
    observed: Sequence[str], baseline: Mapping[str, Any]
) -> Dict[str, Any]:
    """Split observed refusal IDs into known and new, and count both ways."""
    known_ids = {row["id"] for row in baseline.get("classes", [])}
    known = [r for r in observed if r in known_ids]
    unknown = [r for r in observed if r not in known_ids]
    return {
        "baseline_version": baseline.get("baseline_version", ""),
        "baseline_composite_sha256": baseline.get("composite_sha256", ""),
        "classifier_version": baseline.get("classifier_version", ""),
        "occurrences": len(observed),
        "distinct_classes": len(set(observed)),
        "known": sorted(set(known)),
        "unknown": sorted(set(unknown)),
    }


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
            raise ReleaseMetricsError(
                "input[%d] %r is not a principal input. Machine continuation is "
                "not a gesture and must not be recorded as one; a manual resume "
                "is, and must be recorded as manual_resume" % (index, name)
            )
        if not item.get("at"):
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


def scorecard_path(run_folder: Path, mode: str) -> Path:
    if mode not in SCORECARD_FILENAMES:
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
    observed_refusals: Sequence[str],
    baseline: Mapping[str, Any],
) -> Dict[str, Any]:
    """Assemble one scorecard. Verdict is derived, never supplied."""
    if mode not in SCORECARD_FILENAMES:
        raise ReleaseMetricsError("unknown scorecard mode %r" % mode)

    required_stamps = (
        "scope_locked_at",
        "orchestrator_started_at",
        "primary_live_at",
        "all_targets_live_at",
    )
    missing_keys = [k for k in required_stamps if k not in timestamps]
    if missing_keys:
        raise ReleaseMetricsError(
            "timestamps missing %s; a scorecard with a hole is not a partial "
            "measurement" % ", ".join(missing_keys)
        )

    gestures = count_gestures(principal_inputs)
    refusals = classify_refusals(observed_refusals, baseline)
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
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return _structural_check(scorecard, schema)

    validator = jsonschema.Draft202012Validator(schema)
    return [
        "%s: %s" % ("/".join(str(p) for p in e.path) or "<root>", e.message)
        for e in sorted(validator.iter_errors(scorecard), key=lambda e: list(e.path))
    ]


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
