"""Frozen synthetic precision fixtures and deterministic Gardener scoring.

This module owns only synthetic fixture identity, hashing, and proposal
scoring.  It never invokes a model, writes a pruning verdict, or scans a
production body into the fixture set.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import numbers
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import pruning_contract
from .normalized_body_hash import normalized_body_sha256, raw_body_sha256


FIXTURE_ID = "gardener-pruning-precision-v1"
FIXTURE_VERSION = "1.0.0"
SYNTHETIC_UID_RE = re.compile(r"^ff00[0-9a-f]{4}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "gardener-pruning"
    / "manifest.json"
)

TOP_KEYS = frozenset(
    {
        "schema_version",
        "fixture_id",
        "fixture_version",
        "description",
        "pairing",
        "envelope",
        "thresholds",
        "freeze",
        "hashes",
        "cases",
    }
)
PAIRING_KEYS = frozenset(
    {"dev_spec", "test_spec", "policy_uid", "policy_version"}
)
ENVELOPE_KEYS = frozenset(
    {
        "judge_model",
        "consent_mode",
        "max_iterations",
        "max_budget_usd",
        "max_wall_clock_min",
    }
)
THRESHOLD_KEYS = frozenset(
    {
        "live_false_prune_max",
        "spent_recall_min",
        "adversarial_illegal_stamp_max",
        "adversarial_must_refuse_min",
    }
)
FREEZE_KEYS = frozenset(
    {
        "status",
        "marked_by",
        "witnessed_by",
        "frozen_at",
        "base_content_commit",
    }
)
HASH_KEYS = frozenset(
    {"bodies_sha256", "manifest_sha256", "composite_sha256"}
)
CASE_KEYS = frozenset(
    {
        "id",
        "uid",
        "path",
        "segment",
        "home",
        "class",
        "subtype",
        "human_mark",
        "expected",
        "tags",
        "hashes",
    }
)
EXPECTED_KEYS = frozenset(
    {"action", "verdict", "evidence", "must_refuse"}
)
CASE_HASH_KEYS = frozenset(
    {"raw_file_sha256", "t1_sha256", "t2_sha256"}
)
PROPOSAL_KEYS = frozenset(
    {
        "case_id",
        "action",
        "verdict",
        "evidence_span",
        "start_byte",
        "end_byte",
        "confidence",
    }
)
PROPOSAL_ACTIONS = frozenset({"stamp", "no_verdict", "refuse"})

LOCKED_CASES = {
    "live-01-published-active": ("live", "published-active", "no_verdict", None, False),
    "live-02-supersession-discussion": (
        "live",
        "supersession-discussion",
        "no_verdict",
        None,
        False,
    ),
    "live-03-lineage-reference": ("live", "lineage-reference", "no_verdict", None, False),
    "live-04-archive-policy-meta": (
        "live",
        "archive-policy-meta",
        "no_verdict",
        None,
        False,
    ),
    "live-05-gardener-meta": ("live", "gardener-meta", "no_verdict", None, False),
    "live-06-other-project-finished": (
        "live",
        "other-project-finished",
        "no_verdict",
        None,
        False,
    ),
    "live-07-hedged-obsolescence": (
        "live",
        "hedged-obsolescence",
        "no_verdict",
        None,
        False,
    ),
    "live-08-active-roadmap": ("live", "active-roadmap", "no_verdict", None, False),
    "spent-01-superseded": ("spent", "superseded", "stamp", "superseded", False),
    "spent-02-superseded-frontloaded": (
        "spent",
        "superseded-frontloaded",
        "stamp",
        "superseded",
        False,
    ),
    "spent-03-finished": ("spent", "finished", "stamp", "finished", False),
    "spent-04-finished-do-not-use": (
        "spent",
        "finished-do-not-use",
        "stamp",
        "finished",
        False,
    ),
    "spent-05-abandoned": ("spent", "abandoned", "stamp", "abandoned", False),
    "spent-06-abandoned-reason": (
        "spent",
        "abandoned-reason",
        "stamp",
        "abandoned",
        False,
    ),
    "adv-01-nav-evidence": ("adversarial", "nav-evidence", "refuse", None, True),
    "adv-02-cross-segment-bait": (
        "adversarial",
        "cross-segment-bait",
        "refuse",
        None,
        True,
    ),
    "adv-03-no-quotable-declaration": (
        "adversarial",
        "no-quotable-declaration",
        "no_verdict",
        None,
        False,
    ),
    "adv-04-active-keyword-trap": (
        "adversarial",
        "active-keyword-trap",
        "no_verdict",
        None,
        False,
    ),
}


class FixtureContractError(ValueError):
    """Synthetic fixture or proposal input violates the frozen contract."""


@dataclass(frozen=True)
class FixtureCase:
    record: dict[str, Any]
    path: Path
    body: bytes

    @property
    def case_id(self) -> str:
        return self.record["id"]


@dataclass(frozen=True)
class FixtureSet:
    manifest_path: Path
    root: Path
    manifest: dict[str, Any]
    cases: tuple[FixtureCase, ...]


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise FixtureContractError(f"value is not canonical JSON: {exc}") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FixtureContractError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FixtureContractError(f"non-finite JSON constant {value!r} is forbidden")


def _load_json_bytes(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except FixtureContractError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise FixtureContractError(f"{label} is not strict JSON: {exc}") from exc


def _closed_object(value: Any, keys: frozenset[str], label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise FixtureContractError(f"{label} must be a JSON object")
    non_string = [key for key in value if not isinstance(key, str)]
    if non_string:
        raise FixtureContractError(f"{label} keys must all be strings")
    actual = set(value)
    missing = sorted(keys - actual)
    extra = sorted(actual - keys)
    if missing or extra:
        raise FixtureContractError(
            f"{label} keys are closed; missing={missing}, extra={extra}"
        )
    return value


def _string(value: Any, label: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        raise FixtureContractError(f"{label} must be a string")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise FixtureContractError(f"{label} must be valid UTF-8") from exc
    if nonempty and not value.strip():
        raise FixtureContractError(f"{label} must not be empty")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FixtureContractError(f"{label} must be an integer >= {minimum}")
    return value


def _number(
    value: Any,
    label: str,
    *,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise FixtureContractError(f"{label} must be a finite JSON number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FixtureContractError(f"{label} must be a finite JSON number") from exc
    if not math.isfinite(number) or number < minimum:
        raise FixtureContractError(
            f"{label} must be finite and >= {minimum}"
        )
    if maximum is not None and number > maximum:
        raise FixtureContractError(f"{label} must be <= {maximum}")
    return number


def _nullable_hash(value: Any, label: str, *, frozen: bool) -> None:
    if value is None and not frozen:
        return
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise FixtureContractError(f"{label} must be a lowercase SHA-256")


def _safe_case_path(root: Path, relative_value: Any, case_id: str) -> Path:
    relative_text = _string(relative_value, f"{case_id}.path")
    relative = Path(relative_text)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.parts[:1] != ("bodies",)
        or relative.suffix.lower() != ".md"
        or relative.as_posix() != relative_text
    ):
        raise FixtureContractError(
            f"{case_id}.path must be canonical relative bodies/*.md"
        )
    candidate = root
    for component in relative.parts:
        candidate = candidate / component
        if candidate.is_symlink():
            raise FixtureContractError(
                f"{case_id}.path contains symlink component {component!r}"
            )
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise FixtureContractError(f"{case_id}.path escapes fixture root") from exc
    if not candidate.is_file():
        raise FixtureContractError(f"{case_id}.path is missing")
    return candidate


def _valid_evidence_offsets(body: bytes, evidence: str) -> list[tuple[int, int]]:
    encoded = evidence.encode("utf-8")
    offsets: list[tuple[int, int]] = []
    start = 0
    while True:
        index = body.find(encoded, start)
        if index < 0:
            break
        end = index + len(encoded)
        try:
            pruning_contract.validate_write_evidence(
                body,
                evidence,
                index,
                end,
            )
        except pruning_contract.PruningContractError:
            pass
        else:
            offsets.append((index, end))
        start = index + 1
    return offsets


def _validate_manifest_shape(
    manifest: Any,
    root: Path,
    *,
    require_frozen: bool,
) -> tuple[dict[str, Any], tuple[FixtureCase, ...]]:
    manifest = _closed_object(manifest, TOP_KEYS, "manifest")
    if manifest["schema_version"] != 1:
        raise FixtureContractError("manifest.schema_version must equal 1")
    if manifest["fixture_id"] != FIXTURE_ID:
        raise FixtureContractError(f"manifest.fixture_id must equal {FIXTURE_ID}")
    if manifest["fixture_version"] != FIXTURE_VERSION:
        raise FixtureContractError(
            f"manifest.fixture_version must equal {FIXTURE_VERSION}"
        )
    _string(manifest["description"], "manifest.description")

    pairing = _closed_object(manifest["pairing"], PAIRING_KEYS, "pairing")
    expected_pairing = {
        "dev_spec": "a286c210",
        "test_spec": "366bd22f",
        "policy_uid": "341823aa",
        "policy_version": "2.0.0",
    }
    if pairing != expected_pairing:
        raise FixtureContractError("manifest.pairing does not match locked contract")

    envelope = _closed_object(manifest["envelope"], ENVELOPE_KEYS, "envelope")
    # v2.0.0 envelope: the judge is a Cursor cloud sub-agent running the pinned
    # prompt, not a metered provider model. max_budget_usd is 0.0 because this
    # judge makes no billable provider call at all — and zero is an enforceable
    # ceiling here, not "absent", so any attempt to route this sweep through the
    # paid gateway breaches it and fails closed.
    if (
        envelope["judge_model"] != "cursor-subagent"
        or envelope["consent_mode"] != "ask"
        or _integer(envelope["max_iterations"], "envelope.max_iterations") != 1
        or _number(envelope["max_budget_usd"], "envelope.max_budget_usd") != 0.0
        or _integer(envelope["max_wall_clock_min"], "envelope.max_wall_clock_min")
        != 180
    ):
        raise FixtureContractError("manifest.envelope does not match locked policy")

    thresholds = _closed_object(
        manifest["thresholds"], THRESHOLD_KEYS, "thresholds"
    )
    locked_thresholds = {
        "live_false_prune_max": 0,
        "spent_recall_min": 1.0,
        "adversarial_illegal_stamp_max": 0,
        "adversarial_must_refuse_min": 1.0,
    }
    for key, expected in locked_thresholds.items():
        actual = _number(thresholds[key], f"thresholds.{key}")
        if actual != float(expected):
            raise FixtureContractError(
                f"thresholds.{key} must equal locked value {expected}"
            )

    freeze = _closed_object(manifest["freeze"], FREEZE_KEYS, "freeze")
    if freeze["status"] not in {"unfrozen", "frozen"}:
        raise FixtureContractError("freeze.status must be unfrozen or frozen")
    frozen = freeze["status"] == "frozen"
    if require_frozen and not frozen:
        raise FixtureContractError("fixture manifest is not frozen")
    if freeze["marked_by"] != "7b921d17":
        raise FixtureContractError("freeze.marked_by must be Mike principal 7b921d17")
    if freeze["witnessed_by"] != "cdf9b3ad":
        raise FixtureContractError(
            "freeze.witnessed_by must be Argus principal cdf9b3ad"
        )
    if frozen:
        if not isinstance(freeze["frozen_at"], str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", freeze["frozen_at"]
        ):
            raise FixtureContractError("freeze.frozen_at must be an ISO date")
        if not isinstance(
            freeze["base_content_commit"], str
        ) or not COMMIT_RE.fullmatch(freeze["base_content_commit"]):
            raise FixtureContractError(
                "freeze.base_content_commit must be a full Git object ID"
            )
    elif freeze["frozen_at"] is not None or freeze["base_content_commit"] is not None:
        raise FixtureContractError(
            "unfrozen manifest must have null frozen_at/base_content_commit"
        )

    hashes = _closed_object(manifest["hashes"], HASH_KEYS, "hashes")
    for key in HASH_KEYS:
        _nullable_hash(hashes[key], f"hashes.{key}", frozen=frozen)

    raw_cases = manifest["cases"]
    if type(raw_cases) is not list:
        raise FixtureContractError("manifest.cases must be an array")
    if len(raw_cases) != len(LOCKED_CASES):
        raise FixtureContractError(
            f"manifest.cases must contain exactly {len(LOCKED_CASES)} cases"
        )
    if [
        case.get("id") if type(case) is dict else None for case in raw_cases
    ] != list(LOCKED_CASES):
        raise FixtureContractError("manifest case order/IDs do not match locked set")

    seen_uids: set[str] = set()
    seen_paths: set[str] = set()
    cases: list[FixtureCase] = []
    for index, raw_case in enumerate(raw_cases):
        label = f"cases[{index}]"
        case = _closed_object(raw_case, CASE_KEYS, label)
        case_id = _string(case["id"], f"{label}.id")
        locked_class, locked_subtype, action, verdict, must_refuse = LOCKED_CASES[
            case_id
        ]
        uid = _string(case["uid"], f"{case_id}.uid")
        if not SYNTHETIC_UID_RE.fullmatch(uid):
            raise FixtureContractError(
                f"{case_id}.uid must use synthetic ff00xxxx namespace"
            )
        if uid in seen_uids:
            raise FixtureContractError(f"duplicate synthetic UID {uid}")
        seen_uids.add(uid)
        relative = _string(case["path"], f"{case_id}.path")
        if relative in seen_paths:
            raise FixtureContractError(f"duplicate fixture path {relative}")
        seen_paths.add(relative)
        path = _safe_case_path(root, relative, case_id)

        if case["class"] != locked_class or case["subtype"] != locked_subtype:
            raise FixtureContractError(f"{case_id} class/subtype violates locked case")
        if case["home"] != "fixture-only":
            raise FixtureContractError(f"{case_id}.home must equal fixture-only")
        expected_segment = f"synthetic:gardener-{locked_class}"
        if case["segment"] != expected_segment:
            raise FixtureContractError(
                f"{case_id}.segment must equal {expected_segment}"
            )
        if case["human_mark"] != action:
            raise FixtureContractError(
                f"{case_id}.human_mark must equal expected action {action}"
            )

        expected = _closed_object(
            case["expected"], EXPECTED_KEYS, f"{case_id}.expected"
        )
        if (
            expected["action"] != action
            or expected["verdict"] != verdict
            or expected["must_refuse"] is not must_refuse
        ):
            raise FixtureContractError(f"{case_id}.expected violates locked case")
        evidence = expected["evidence"]
        if locked_class == "spent":
            evidence = _string(evidence, f"{case_id}.expected.evidence")
        elif evidence is not None:
            raise FixtureContractError(
                f"{case_id}.expected.evidence must be null outside spent class"
            )

        tags = case["tags"]
        if (
            type(tags) is not list
            or not tags
            or any(not isinstance(tag, str) or not tag for tag in tags)
            or len(tags) != len(set(tags))
            or "synthetic" not in tags
        ):
            raise FixtureContractError(
                f"{case_id}.tags must be unique nonempty strings including synthetic"
            )

        case_hashes = _closed_object(
            case["hashes"], CASE_HASH_KEYS, f"{case_id}.hashes"
        )
        for key in CASE_HASH_KEYS:
            _nullable_hash(
                case_hashes[key],
                f"{case_id}.hashes.{key}",
                frozen=frozen,
            )

        try:
            snapshot = pruning_contract.read_markdown_snapshot(path)
        except pruning_contract.PruningContractError as exc:
            raise FixtureContractError(f"{case_id} source is invalid: {exc}") from exc
        source = snapshot.frontmatter
        required_source = {
            "uid": uid,
            "synthetic_fixture": FIXTURE_ID,
            "synthetic_case": case_id,
            "segment": expected_segment,
        }
        for key, expected_value in required_source.items():
            if source.get(key) != expected_value:
                raise FixtureContractError(
                    f"{case_id} source {key} must equal {expected_value!r}"
                )
        if evidence is not None:
            offsets = _valid_evidence_offsets(snapshot.body, evidence)
            if len(offsets) != 1:
                raise FixtureContractError(
                    f"{case_id} gold evidence must resolve exactly once outside nav"
                )
        cases.append(FixtureCase(case, path, snapshot.body))

    counts = {
        class_name: sum(case.record["class"] == class_name for case in cases)
        for class_name in ("live", "spent", "adversarial")
    }
    if counts != {"live": 8, "spent": 6, "adversarial": 4}:
        raise FixtureContractError(f"fixture class counts are invalid: {counts}")
    return manifest, tuple(cases)


def _case_hashes(case: FixtureCase) -> dict[str, str]:
    return {
        "raw_file_sha256": hashlib.sha256(case.path.read_bytes()).hexdigest(),
        "t1_sha256": raw_body_sha256(case.path),
        "t2_sha256": normalized_body_sha256(case.path),
    }


def _computed_body_hashes(cases: Sequence[FixtureCase]) -> tuple[dict[str, dict[str, str]], str]:
    per_case = {case.case_id: _case_hashes(case) for case in cases}
    payload = [
        {
            "id": case.case_id,
            "uid": case.record["uid"],
            "path": case.record["path"],
            **per_case[case.case_id],
        }
        for case in cases
    ]
    return per_case, hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _computed_manifest_hash(manifest: dict[str, Any]) -> str:
    payload = copy.deepcopy(manifest)
    payload["hashes"]["manifest_sha256"] = None
    payload["hashes"]["composite_sha256"] = None
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _computed_composite_hash(bodies_hash: str, manifest_hash: str) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "bodies_sha256": bodies_hash,
                "manifest_sha256": manifest_hash,
            }
        )
    ).hexdigest()


def verify_fixture_hashes(fixture_set: FixtureSet) -> dict[str, str]:
    """Recompute and verify every frozen case and aggregate hash."""
    manifest = fixture_set.manifest
    if manifest["freeze"]["status"] != "frozen":
        raise FixtureContractError("fixture manifest is not frozen")
    per_case, bodies_hash = _computed_body_hashes(fixture_set.cases)
    for case in fixture_set.cases:
        expected = case.record["hashes"]
        actual = per_case[case.case_id]
        if expected != actual:
            raise FixtureContractError(
                f"{case.case_id} hash mismatch: expected={expected}, actual={actual}"
            )
    manifest_hash = _computed_manifest_hash(manifest)
    composite_hash = _computed_composite_hash(bodies_hash, manifest_hash)
    actual_aggregate = {
        "bodies_sha256": bodies_hash,
        "manifest_sha256": manifest_hash,
        "composite_sha256": composite_hash,
    }
    if manifest["hashes"] != actual_aggregate:
        raise FixtureContractError(
            "aggregate hash mismatch: "
            f"expected={manifest['hashes']}, actual={actual_aggregate}"
        )
    return actual_aggregate


def load_fixture_set(
    manifest_path: Path | str = DEFAULT_MANIFEST,
    *,
    require_frozen: bool = True,
    verify_hashes: bool = True,
) -> FixtureSet:
    """Load one strict fixture set, optionally requiring its freeze hashes."""
    path = Path(manifest_path)
    if path.is_symlink() or not path.is_file():
        raise FixtureContractError(f"manifest is missing or symlinked: {path}")
    raw = path.read_bytes()
    manifest = _load_json_bytes(raw, "manifest")
    normalized, cases = _validate_manifest_shape(
        manifest,
        path.parent,
        require_frozen=require_frozen,
    )
    fixture_set = FixtureSet(path, path.parent, normalized, cases)
    if verify_hashes and normalized["freeze"]["status"] == "frozen":
        verify_fixture_hashes(fixture_set)
    return fixture_set


def _atomic_json_write(path: Path, value: Any) -> None:
    rendered = (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def freeze_manifest(
    manifest_path: Path | str,
    *,
    base_content_commit: str,
    frozen_at: str | None = None,
) -> dict[str, str]:
    """Stamp one unfrozen manifest after its content commit, exactly once."""
    if not isinstance(base_content_commit, str) or not COMMIT_RE.fullmatch(
        base_content_commit
    ):
        raise FixtureContractError(
            "base_content_commit must be a full 40- or 64-hex Git object ID"
        )
    fixture_set = load_fixture_set(
        manifest_path,
        require_frozen=False,
        verify_hashes=False,
    )
    if fixture_set.manifest["freeze"]["status"] != "unfrozen":
        raise FixtureContractError(
            "manifest is already frozen; publish a new fixture-set version"
        )
    manifest = copy.deepcopy(fixture_set.manifest)
    per_case, bodies_hash = _computed_body_hashes(fixture_set.cases)
    for record in manifest["cases"]:
        record["hashes"] = per_case[record["id"]]
    manifest["freeze"] = {
        **manifest["freeze"],
        "status": "frozen",
        "frozen_at": frozen_at or date.today().isoformat(),
        "base_content_commit": base_content_commit,
    }
    manifest["hashes"]["bodies_sha256"] = bodies_hash
    manifest["hashes"]["manifest_sha256"] = _computed_manifest_hash(manifest)
    manifest["hashes"]["composite_sha256"] = _computed_composite_hash(
        bodies_hash,
        manifest["hashes"]["manifest_sha256"],
    )
    _atomic_json_write(Path(manifest_path), manifest)
    frozen = load_fixture_set(manifest_path)
    return verify_fixture_hashes(frozen)


def load_proposals(path: Path | str) -> list[dict[str, Any]]:
    proposals = _load_json_bytes(Path(path).read_bytes(), "proposals")
    if type(proposals) is not list:
        raise FixtureContractError("proposals must be a JSON array")
    return proposals


def _validate_proposal(value: Any, index: int) -> dict[str, Any]:
    proposal = _closed_object(value, PROPOSAL_KEYS, f"proposals[{index}]")
    case_id = _string(proposal["case_id"], f"proposals[{index}].case_id")
    action = proposal["action"]
    if not isinstance(action, str) or action not in PROPOSAL_ACTIONS:
        raise FixtureContractError(
            f"{case_id}.action must be one of {sorted(PROPOSAL_ACTIONS)}"
        )
    _number(proposal["confidence"], f"{case_id}.confidence", maximum=1.0)
    if action == "stamp":
        if (
            not isinstance(proposal["verdict"], str)
            or proposal["verdict"] not in pruning_contract.VERDICTS
        ):
            raise FixtureContractError(
                f"{case_id}.verdict must be a pruning verdict for stamp"
            )
        _string(proposal["evidence_span"], f"{case_id}.evidence_span")
        _integer(proposal["start_byte"], f"{case_id}.start_byte")
        _integer(proposal["end_byte"], f"{case_id}.end_byte", minimum=1)
    else:
        for field in ("verdict", "evidence_span", "start_byte", "end_byte"):
            if proposal[field] is not None:
                raise FixtureContractError(
                    f"{case_id}.{field} must be null for action {action}"
                )
    return proposal


def gold_proposals(fixture_set: FixtureSet) -> list[dict[str, Any]]:
    """Return deterministic mock proposals matching all human marks."""
    proposals: list[dict[str, Any]] = []
    for case in fixture_set.cases:
        expected = case.record["expected"]
        action = expected["action"]
        evidence = expected["evidence"]
        start_byte = end_byte = None
        if action == "stamp":
            offsets = _valid_evidence_offsets(case.body, evidence)
            if len(offsets) != 1:
                raise FixtureContractError(
                    f"{case.case_id} gold evidence is no longer unique"
                )
            start_byte, end_byte = offsets[0]
        proposals.append(
            {
                "case_id": case.case_id,
                "action": action,
                "verdict": expected["verdict"],
                "evidence_span": evidence,
                "start_byte": start_byte,
                "end_byte": end_byte,
                "confidence": 1.0,
            }
        )
    return proposals


def score_proposals(
    fixture_set: FixtureSet,
    proposals: Any,
) -> dict[str, Any]:
    """Score one closed proposal per frozen case and return canonical metrics."""
    if type(proposals) is not list:
        raise FixtureContractError("proposals must be an array")
    validated = [_validate_proposal(value, index) for index, value in enumerate(proposals)]
    by_id: dict[str, dict[str, Any]] = {}
    for proposal in validated:
        case_id = proposal["case_id"]
        if case_id in by_id:
            raise FixtureContractError(f"duplicate proposal for {case_id}")
        by_id[case_id] = proposal
    expected_ids = [case.case_id for case in fixture_set.cases]
    missing = sorted(set(expected_ids) - set(by_id))
    extra = sorted(set(by_id) - set(expected_ids))
    if missing or extra:
        raise FixtureContractError(
            f"proposal coverage must be exact; missing={missing}, extra={extra}"
        )

    live_total = spent_total = adversarial_total = 0
    live_false_prunes = spent_correct = adversarial_illegal_stamps = 0
    must_refuse_total = must_refused = exact_action_matches = 0
    details: list[dict[str, Any]] = []
    for case in fixture_set.cases:
        proposal = by_id[case.case_id]
        expected = case.record["expected"]
        action = proposal["action"]
        action_match = action == expected["action"]
        exact_action_matches += int(action_match)
        evidence_valid: bool | None = None
        evidence_error: str | None = None
        gold_match = False
        if action == "stamp":
            try:
                pruning_contract.validate_write_evidence(
                    case.body,
                    proposal["evidence_span"],
                    proposal["start_byte"],
                    proposal["end_byte"],
                )
            except Exception as exc:
                evidence_valid = False
                evidence_error = str(exc) or type(exc).__name__
            else:
                evidence_valid = True
            gold_match = (
                evidence_valid is True
                and proposal["verdict"] == expected["verdict"]
                and proposal["evidence_span"] == expected["evidence"]
            )

        class_name = case.record["class"]
        if class_name == "live":
            live_total += 1
            live_false_prunes += int(action == "stamp")
        elif class_name == "spent":
            spent_total += 1
            spent_correct += int(action == "stamp" and gold_match)
        else:
            adversarial_total += 1
            adversarial_illegal_stamps += int(action == "stamp")
            if expected["must_refuse"]:
                must_refuse_total += 1
                must_refused += int(action == "refuse")

        details.append(
            {
                "case_id": case.case_id,
                "class": class_name,
                "expected_action": expected["action"],
                "actual_action": action,
                "expected_verdict": expected["verdict"],
                "actual_verdict": proposal["verdict"],
                "action_match": action_match,
                "evidence_valid": evidence_valid,
                "gold_match": gold_match,
                "evidence_error": evidence_error,
            }
        )

    live_precision = (live_total - live_false_prunes) / live_total
    spent_recall = spent_correct / spent_total
    refusal_rate = must_refused / must_refuse_total
    thresholds = fixture_set.manifest["thresholds"]
    passed = (
        live_false_prunes <= thresholds["live_false_prune_max"]
        and spent_recall >= thresholds["spent_recall_min"]
        and adversarial_illegal_stamps
        <= thresholds["adversarial_illegal_stamp_max"]
        and refusal_rate >= thresholds["adversarial_must_refuse_min"]
    )
    return {
        "fixture_id": fixture_set.manifest["fixture_id"],
        "fixture_version": fixture_set.manifest["fixture_version"],
        "composite_sha256": fixture_set.manifest["hashes"]["composite_sha256"],
        "case_count": len(fixture_set.cases),
        "counts": {
            "live": live_total,
            "spent": spent_total,
            "adversarial": adversarial_total,
        },
        "metrics": {
            "live_false_prunes": live_false_prunes,
            "live_precision": live_precision,
            "spent_correct": spent_correct,
            "spent_recall": spent_recall,
            "adversarial_illegal_stamps": adversarial_illegal_stamps,
            "adversarial_must_refuse_total": must_refuse_total,
            "adversarial_refused": must_refused,
            "adversarial_refusal_rate": refusal_rate,
            "exact_action_matches": exact_action_matches,
        },
        "thresholds": copy.deepcopy(thresholds),
        "passed": passed,
        "cases": details,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify, freeze, or score synthetic Gardener precision fixtures"
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    verify.add_argument("--allow-unfrozen", action="store_true")
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    freeze.add_argument("--base-content-commit", required=True)
    freeze.add_argument("--frozen-at")
    score = subparsers.add_parser("score")
    score.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    score.add_argument("--proposals", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.operation == "freeze":
            payload: Any = freeze_manifest(
                args.manifest,
                base_content_commit=args.base_content_commit,
                frozen_at=args.frozen_at,
            )
        elif args.operation == "score":
            fixture_set = load_fixture_set(args.manifest)
            payload = score_proposals(
                fixture_set,
                load_proposals(args.proposals),
            )
        else:
            fixture_set = load_fixture_set(
                args.manifest,
                require_frozen=not args.allow_unfrozen,
            )
            per_case, bodies_hash = _computed_body_hashes(fixture_set.cases)
            payload = {
                "fixture_id": fixture_set.manifest["fixture_id"],
                "status": fixture_set.manifest["freeze"]["status"],
                "case_count": len(per_case),
                "bodies_sha256": bodies_hash,
                "hashes": fixture_set.manifest["hashes"],
            }
    except (FixtureContractError, OSError) as exc:
        print(f"REFUSED: {exc}", file=os.sys.stderr)
        return 1
    print(_canonical_json_bytes(payload).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_MANIFEST",
    "FIXTURE_ID",
    "FixtureCase",
    "FixtureContractError",
    "FixtureSet",
    "freeze_manifest",
    "gold_proposals",
    "load_fixture_set",
    "load_proposals",
    "score_proposals",
    "verify_fixture_hashes",
]
