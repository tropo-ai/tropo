"""Shared parser and validator for the core v1.7 pruning contract.

The writer, full validator, and targeted check-one adapter use this module as
the single source of truth for block shape, evidence, policy, override, and
currency semantics. Validation is read-only; the pure evaluator accepts a
snapshot plus current index rows and returns typed findings.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

import yaml

try:
    from .normalized_body_hash import normalized_body_sha256, raw_body_sha256
except ImportError:  # direct path-load used by tropo-validate.py
    _hash_path = Path(__file__).resolve().with_name("normalized_body_hash.py")
    _hash_spec = importlib.util.spec_from_file_location(
        "_pruning_contract_normalized_body_hash",
        _hash_path,
    )
    if _hash_spec is None or _hash_spec.loader is None:
        raise ImportError(f"cannot load canonical body hashes from {_hash_path}")
    _hash_module = importlib.util.module_from_spec(_hash_spec)
    sys.modules[_hash_spec.name] = _hash_module
    _hash_spec.loader.exec_module(_hash_module)
    normalized_body_sha256 = _hash_module.normalized_body_sha256
    raw_body_sha256 = _hash_module.raw_body_sha256


UID_RE = re.compile(r"^[0-9a-f]{8}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
TOP_LEVEL_PRUNING_RE = re.compile(
    rb"""(?mx)
    ^
    (?:
        pruning
        |
        "pruning"
        |
        'pruning'
    )
    [\t ]*:
    """
)
NAV_BLOCK_RE = re.compile(
    rb"<!-- nav-block:start -->.*?<!-- nav-block:end -->",
    re.DOTALL,
)
VERDICTS = frozenset({"finished", "superseded", "abandoned"})
POLICY_RUNNER = "gardener-body-judge"
EVIDENCE_DOCTRINE = (
    "core pruning contract v1.7 evidence rule: "
    "a pruning verdict requires verbatim source evidence"
)

PRUNING_REQUIRED_KEYS = frozenset(
    {
        "verdict",
        "evidence_span",
        "evidence_locator",
        "judge_policy_uid",
        "judge_version",
        "judge_prompt_sha256",
        "origin_studio",
        "judged_at",
        "confidence",
        "normalized_body_hash_judged",
    }
)
PRUNING_ALLOWED_KEYS = PRUNING_REQUIRED_KEYS | {"override"}
LOCATOR_KEYS = frozenset({"body_sha256", "start_byte", "end_byte"})
OVERRIDE_KEYS = frozenset({"action", "by", "at", "reason"})


class PruningContractError(RuntimeError):
    """A pruning block or source snapshot violates the shared contract."""


class PruningIndexError(PruningContractError):
    """The current index cannot support fail-closed pruning validation."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _safe_repr(value: object) -> str:
    try:
        return repr(value)
    except Exception:
        return f"<{type(value).__name__}>"


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except (TypeError, ValueError) as exc:
            raise PruningContractError(
                f"unhashable YAML mapping key {_safe_repr(key)} is ambiguous"
            ) from exc
        if duplicate:
            raise PruningContractError(
                f"duplicate YAML key {_safe_repr(key)} is ambiguous"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class MarkdownSnapshot:
    raw: bytes
    frontmatter_text: str
    frontmatter: dict
    body: bytes


@dataclass(frozen=True)
class ContractFinding:
    severity: str
    code: str
    message: str
    cure: str

    def format(self, uid: str, path: str) -> str:
        def printable(value: object) -> str:
            return str(value).encode("utf-8", errors="backslashreplace").decode("utf-8")

        return (
            f"[{self.severity}] {printable(uid)} {printable(path)} — "
            f"{self.code}: {printable(self.message)}; cure: {printable(self.cure)}"
        )


@dataclass(frozen=True)
class PruningCheckResult:
    uid: str
    path: str
    applicable: bool
    has_pruning: bool
    findings: tuple[ContractFinding, ...] = ()
    declared_verdict: Optional[str] = None
    effective_verdict: Optional[str] = None
    t1_current: Optional[bool] = None
    t2_current: Optional[bool] = None
    policy_current: Optional[bool] = None
    override_current: bool = False

    @property
    def severity(self) -> str:
        if any(finding.severity == "FAIL" for finding in self.findings):
            return "FAIL"
        if any(finding.severity == "WARN" for finding in self.findings):
            return "WARN"
        return "PASS"

    @property
    def defects(self) -> int:
        return sum(finding.severity == "FAIL" for finding in self.findings)

    @property
    def warnings(self) -> int:
        return sum(finding.severity == "WARN" for finding in self.findings)

    def formatted_findings(self) -> list[str]:
        return [finding.format(self.uid, self.path) for finding in self.findings]


def parse_frontmatter_mapping(frontmatter_text: str) -> dict:
    try:
        parsed = yaml.load(frontmatter_text, Loader=_UniqueKeyLoader)
    except PruningContractError:
        raise
    except Exception as exc:
        raise PruningContractError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PruningContractError("frontmatter must be a mapping")
    return parsed


def has_top_level_pruning(raw: bytes) -> bool:
    if not raw.startswith(b"---\n"):
        return False
    boundary = raw.find(b"\n---\n", 3)
    frontmatter_bytes = raw[4:boundary] if boundary >= 0 else raw[4:]
    try:
        frontmatter_text = frontmatter_bytes.decode("utf-8", errors="strict")
        parsed = parse_frontmatter_mapping(frontmatter_text)
    except PruningContractError:
        return bool(TOP_LEVEL_PRUNING_RE.search(frontmatter_bytes))
    try:
        return "pruning" in parsed
    except (TypeError, ValueError):
        return bool(TOP_LEVEL_PRUNING_RE.search(frontmatter_bytes))


def parse_markdown_bytes(raw: bytes, path_label: object = "<source>") -> MarkdownSnapshot:
    if not raw.startswith(b"---\n"):
        raise PruningContractError(
            f"{path_label}: pruning-eligible Markdown must begin with exact '---\\n'"
        )
    boundary = raw.find(b"\n---\n", 3)
    if boundary < 0:
        raise PruningContractError(
            f"{path_label}: frontmatter must end with exact '\\n---\\n'"
        )
    try:
        frontmatter_text = raw[4:boundary].decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PruningContractError(
            f"{path_label}: frontmatter is not strict UTF-8"
        ) from exc
    frontmatter = parse_frontmatter_mapping(frontmatter_text)
    return MarkdownSnapshot(
        raw=raw,
        frontmatter_text=frontmatter_text,
        frontmatter=frontmatter,
        body=raw[boundary + len(b"\n---\n"):],
    )


def read_markdown_snapshot(path: Path) -> MarkdownSnapshot:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise PruningContractError(f"{path}: cannot read source: {exc}") from exc
    return parse_markdown_bytes(raw, path)


def source_scalar(frontmatter_text: str, key: str) -> Optional[str]:
    matches = re.findall(
        rf"(?m)^{re.escape(key)}:\s*(.*?)\s*$",
        frontmatter_text,
    )
    if len(matches) != 1:
        return None
    value = matches[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


def _trimmed_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PruningContractError(f"{field} must be a trimmed non-empty string")
    return value


def validate_trimmed_string(value: object, field: str) -> str:
    return _trimmed_string(value, field)


def _validate_utf8_string(value: object, field: str) -> str:
    text = _trimmed_string(value, field)
    try:
        text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise PruningContractError(f"{field} must be valid strict UTF-8 text") from exc
    return text


def _validate_hash(value: object, field: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise PruningContractError(f"{field} must be exactly 64 lowercase hex")
    return value


def validate_hash(value: object, field: str) -> str:
    return _validate_hash(value, field)


def _validate_timezone_datetime(value: object, field: str) -> str:
    text = _validate_utf8_string(value, f"pruning.{field}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (OverflowError, ValueError) as exc:
        raise PruningContractError(
            f"pruning.{field} must be an ISO 8601 datetime"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PruningContractError(f"pruning.{field} must be timezone-aware")
    return text


def validate_confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PruningContractError("confidence must be a non-boolean number")
    if isinstance(value, int):
        if not 0 <= value <= 1:
            raise PruningContractError(
                "confidence must be finite and within 0.0..1.0"
            )
        return float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise PruningContractError("confidence must be finite and within 0.0..1.0")
    return value


def _closed_string_keys(
    mapping: object,
    *,
    field: str,
    allowed: frozenset[str],
    required: frozenset[str],
) -> dict:
    if not isinstance(mapping, dict):
        raise PruningContractError(f"{field} must be a mapping")
    non_string = [key for key in mapping if not isinstance(key, str)]
    if non_string:
        rendered = ", ".join(_safe_repr(key) for key in non_string)
        raise PruningContractError(
            f"{field} keys must be strings; invalid keys: {rendered}"
        )
    keys = frozenset(mapping)
    missing = sorted(required - keys)
    unknown = sorted(keys - allowed)
    if missing or unknown:
        raise PruningContractError(
            f"malformed {field} block: missing={missing}, unknown={unknown}"
        )
    return mapping


def validate_pruning_block(block: object) -> dict:
    if not isinstance(block, dict):
        raise PruningContractError("existing pruning block must be a mapping")
    block = _closed_string_keys(
        block,
        field="pruning",
        allowed=PRUNING_ALLOWED_KEYS,
        required=PRUNING_REQUIRED_KEYS,
    )

    verdict = block.get("verdict")
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        raise PruningContractError(
            f"pruning.verdict must be one of {sorted(VERDICTS)}"
        )
    _validate_utf8_string(block.get("evidence_span"), "pruning.evidence_span")

    locator = block.get("evidence_locator")
    locator = _closed_string_keys(
        locator,
        field="pruning.evidence_locator",
        allowed=LOCATOR_KEYS,
        required=LOCATOR_KEYS,
    )
    _validate_hash(locator.get("body_sha256"), "pruning.evidence_locator.body_sha256")
    start = locator.get("start_byte")
    end = locator.get("end_byte")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end <= start
    ):
        raise PruningContractError(
            "pruning evidence byte range must be non-boolean integers with "
            "0 <= start_byte < end_byte"
        )

    policy_uid = block.get("judge_policy_uid")
    if not isinstance(policy_uid, str) or not UID_RE.fullmatch(policy_uid):
        raise PruningContractError("pruning.judge_policy_uid must be 8 lowercase hex")
    _validate_utf8_string(block.get("judge_version"), "pruning.judge_version")

    # Federation portability (Metis G93, 2026-07-25): a verdict crossing a mount
    # boundary must be evaluable WITHOUT resolving back into the origin studio,
    # because the origin's policy file may not be readable from the receiving
    # side. So the judge's exact identity and the producing studio travel ON the
    # stamp rather than only in the run directory.
    origin_studio = block.get("origin_studio")
    if not isinstance(origin_studio, str) or not UID_RE.fullmatch(origin_studio):
        raise PruningContractError("pruning.origin_studio must be 8 lowercase hex")
    prompt_sha = block.get("judge_prompt_sha256")
    if prompt_sha is not None:
        _validate_hash(prompt_sha, "pruning.judge_prompt_sha256")
    _validate_timezone_datetime(block.get("judged_at"), "judged_at")
    validate_confidence(block.get("confidence"))
    _validate_hash(
        block.get("normalized_body_hash_judged"),
        "pruning.normalized_body_hash_judged",
    )

    if "override" in block:
        override = block["override"]
        override = _closed_string_keys(
            override,
            field="pruning.override",
            allowed=OVERRIDE_KEYS,
            required=OVERRIDE_KEYS,
        )
        if override.get("action") != "keep":
            raise PruningContractError("pruning.override.action must be 'keep'")
        by = override.get("by")
        if not isinstance(by, str) or not UID_RE.fullmatch(by):
            raise PruningContractError("pruning.override.by must be 8 lowercase hex")
        _validate_timezone_datetime(override.get("at"), "override.at")
        _validate_utf8_string(override.get("reason"), "pruning.override.reason")
    return block


def validate_write_evidence(
    body: bytes,
    evidence_span: object,
    start_byte: object,
    end_byte: object,
) -> None:
    try:
        span = _trimmed_string(evidence_span, "evidence_span")
    except PruningContractError as exc:
        raise PruningContractError(f"{EVIDENCE_DOCTRINE}; {exc}") from exc
    if (
        isinstance(start_byte, bool)
        or isinstance(end_byte, bool)
        or not isinstance(start_byte, int)
        or not isinstance(end_byte, int)
        or start_byte < 0
        or end_byte <= start_byte
        or end_byte > len(body)
    ):
        raise PruningContractError(
            f"{EVIDENCE_DOCTRINE}; byte range must satisfy "
            "0 <= start_byte < end_byte <= raw body length"
        )
    for match in NAV_BLOCK_RE.finditer(body):
        if start_byte < match.end() and end_byte > match.start():
            raise PruningContractError(
                f"{EVIDENCE_DOCTRINE}; generated nav-block bytes are ineligible"
            )
    addressed = body[start_byte:end_byte]
    try:
        decoded = addressed.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PruningContractError(
            f"{EVIDENCE_DOCTRINE}; invalid UTF-8 bytes cannot be cited"
        ) from exc
    if decoded != span:
        raise PruningContractError(
            f"{EVIDENCE_DOCTRINE}; byte range does not decode to evidence_span"
        )


def active_policy_candidates(current_records: Sequence[dict]) -> list[dict]:
    return [
        row
        for row in current_records
        if isinstance(row, dict)
        and row.get("type") == "loop"
        and row.get("status") == "active"
        and row.get("state") == "active"
        and row.get("runner") == POLICY_RUNNER
    ]


def resolve_active_policy(
    policy_uid: str,
    judge_version: str,
    current_records: Sequence[dict],
) -> dict:
    if not UID_RE.fullmatch(policy_uid):
        raise PruningContractError("judge_policy_uid must be 8 lowercase hex")
    _validate_utf8_string(judge_version, "judge_version")
    candidates = active_policy_candidates(current_records)
    if len(candidates) != 1:
        raise PruningContractError(
            "judge policy fails closed: expected exactly one current "
            "status/state active type:loop with runner gardener-body-judge; "
            f"found {len(candidates)}"
        )
    policy = candidates[0]
    if policy.get("uid") != policy_uid:
        raise PruningContractError(
            f"judge policy fails closed: supplied {policy_uid}, active policy is "
            f"{policy.get('uid')!r}"
        )
    if policy.get("version") != judge_version:
        raise PruningContractError(
            f"judge policy version mismatch: supplied {judge_version!r}, active "
            f"policy {policy_uid} declares {policy.get('version')!r}"
        )
    return policy


def resolve_human_principal(uid: str, current_records: Sequence[dict]) -> dict:
    if not UID_RE.fullmatch(uid):
        raise PruningContractError("override principal UID must be 8 lowercase hex")
    matches = [
        row
        for row in current_records
        if isinstance(row, dict) and row.get("uid") == uid
    ]
    if len(matches) != 1:
        raise PruningContractError(
            f"override principal {uid} must resolve in the current index"
        )
    principal = matches[0]
    if (
        principal.get("type") != "principal"
        or principal.get("principal_class") != "human"
    ):
        raise PruningContractError(
            f"override principal {uid} must resolve to type:principal with "
            "principal_class:human"
        )
    return principal


def is_declared_pruning_home(relative_path: Path) -> bool:
    parts = Path(relative_path).parts
    if Path(relative_path).suffix.lower() != ".md":
        return False
    if len(parts) == 3 and parts[:2] in (
        ("vault", "files"),
        ("vault", "agents"),
        ("vault", "capsules"),
    ):
        return True
    return len(parts) >= 2 and parts[0] == "agents"


def resolve_declared_source_path(
    path_value: object,
    vault_root: Path,
    uid: str,
    *,
    indexed: bool,
    require_file: bool = True,
) -> tuple[Path, Path]:
    """Resolve one pruning path with the writer's fail-closed identity rules."""
    if not isinstance(path_value, (str, Path)) or not str(path_value).strip():
        raise PruningContractError(f"UID {uid} index row has no governed source path")
    supplied = Path(path_value)
    root = Path(vault_root).resolve()
    if indexed and supplied.is_absolute():
        raise PruningContractError(f"UID {uid} index path must be Studio-relative")
    if supplied.is_absolute():
        try:
            relative = supplied.relative_to(root)
        except ValueError as exc:
            raise PruningContractError(
                f"UID {uid} source path escapes the Studio root"
            ) from exc
    else:
        relative = supplied
    if ".." in relative.parts:
        raise PruningContractError(
            f"UID {uid} index path may not contain a '..' component"
        )
    if not is_declared_pruning_home(relative):
        raise PruningContractError(
            f"UID {uid} source is outside the four declared pruning Markdown homes"
        )

    candidate = root
    for component in relative.parts:
        candidate = candidate / component
        if candidate.is_symlink():
            raise PruningContractError(
                f"UID {uid} index path contains symlink component {component!r}"
            )
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise PruningContractError(
            f"UID {uid} source path escapes the Studio root"
        ) from exc
    if resolved != candidate:
        raise PruningContractError(
            f"UID {uid} source path is a non-canonical alias"
        )
    if require_file and (not candidate.is_file() or candidate.suffix.lower() != ".md"):
        raise PruningContractError(
            f"UID {uid} indexed source is missing or not eligible Markdown at "
            f"{relative.as_posix()}"
        )
    return candidate, relative


def resolve_origin_studio(vault_root: Path | str) -> str:
    """Return this studio's canonical identity UID, read from ``STUDIO.md``.

    Deliberately NOT caller-supplied. ``origin_studio`` is a provenance claim —
    "this studio produced this verdict" — and a provenance field a caller can
    hand in is a gate defended with a caller-controlled value. The writer
    derives it from the studio it is actually running in.

    Fail-closed: a missing, unreadable, or non-8-hex ``uid:`` in ``STUDIO.md``
    raises rather than falling back to a placeholder. A verdict with a guessed
    origin is worse at a federation boundary than a verdict that refused to be
    written.

    (When per-vault-node ``vault-entity`` instances land under ADR-051, this
    resolution tightens to that entity's UID; the studio config UID is today's
    single unambiguous source, and this is the one place to change it.)
    """
    path = Path(vault_root) / "STUDIO.md"
    if path.is_symlink() or not path.is_file():
        raise PruningContractError(
            "origin studio identity is unresolvable: STUDIO.md is missing or symlinked"
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PruningContractError(
            f"origin studio identity is unreadable: {exc}"
        ) from exc
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise PruningContractError(
            "origin studio identity is unresolvable: STUDIO.md has no frontmatter"
        )
    try:
        frontmatter = yaml.load(parts[1], Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise PruningContractError(
            f"origin studio identity is unresolvable: STUDIO.md YAML is invalid: {exc}"
        ) from exc
    if not isinstance(frontmatter, dict):
        raise PruningContractError(
            "origin studio identity is unresolvable: STUDIO.md frontmatter is not a mapping"
        )
    uid = frontmatter.get("uid")
    if not isinstance(uid, str) or not UID_RE.fullmatch(uid):
        raise PruningContractError(
            "origin studio identity is unresolvable: STUDIO.md uid must be 8 lowercase hex"
        )
    return uid


def resolve_indexed_pruning_source(
    uid: str,
    row: dict,
    vault_root: Path,
) -> Path:
    path, _relative = resolve_declared_source_path(
        row.get("path"),
        vault_root,
        uid,
        indexed=True,
    )
    snapshot = read_markdown_snapshot(path)
    source_uid = source_scalar(snapshot.frontmatter_text, "uid")
    if source_uid != uid:
        raise PruningContractError(
            f"UID/path/frontmatter disagreement: requested {uid}, "
            f"frontmatter has {source_uid!r}"
        )
    return path


def validate_locked_snapshot_identity(
    uid: str,
    path: Path,
    row: dict,
    snapshot: MarkdownSnapshot,
    vault_root: Path,
) -> None:
    expected_path, _relative = resolve_declared_source_path(
        row.get("path"),
        vault_root,
        uid,
        indexed=True,
    )
    if path != expected_path:
        raise PruningContractError(
            "locked target path no longer agrees with its index row"
        )
    source_uid = source_scalar(snapshot.frontmatter_text, "uid")
    if source_uid != uid:
        raise PruningContractError(
            f"UID/path/frontmatter disagreement in locked snapshot: "
            f"requested {uid}, frontmatter has {source_uid!r}"
        )


def iter_eligible_markdown(vault_root: Path) -> list[Path]:
    roots = (
        (vault_root / "vault" / "files", False),
        (vault_root / "vault" / "agents", False),
        (vault_root / "agents", True),
        (vault_root / "vault" / "capsules", False),
    )
    paths: set[Path] = set()
    for directory, recursive in roots:
        if not directory.is_dir():
            continue
        iterator = directory.rglob("*.md") if recursive else directory.glob("*.md")
        paths.update(path for path in iterator if path.is_file())
    return sorted(paths)


def _has_symlink_component(path: Path, vault_root: Path) -> bool:
    try:
        relative = path.relative_to(vault_root)
    except ValueError:
        return False
    candidate = vault_root
    for component in relative.parts:
        candidate = candidate / component
        if candidate.is_symlink():
            return True
    return False


def _load_index_strict(
    vault_root: Path,
    filename: str,
    label: str,
    *,
    required: bool,
) -> list[dict]:
    index_path = Path(vault_root) / "vault" / filename
    if not index_path.is_file():
        if not required:
            return []
        raise PruningIndexError(f"{label} index is missing at vault/{filename}")
    records: list[dict] = []
    try:
        with index_path.open(encoding="utf-8", errors="strict") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    record = json.loads(raw)
                except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
                    raise PruningIndexError(
                        f"{label} index has corrupt JSON at line {line_number}: {exc}"
                    ) from exc
                if not isinstance(record, dict):
                    raise PruningIndexError(
                        f"{label} index line {line_number} is not a JSON object"
                    )
                records.append(record)
    except PruningIndexError:
        raise
    except (OSError, UnicodeError) as exc:
        raise PruningIndexError(f"{label} index cannot be read: {exc}") from exc
    return records


def load_current_index_strict(vault_root: Path) -> list[dict]:
    """Read the current JSONL index without permissive row skipping."""
    return _load_index_strict(
        vault_root,
        "00-index.jsonl",
        "current",
        required=True,
    )


def load_archive_index_strict(vault_root: Path) -> list[dict]:
    """Read the optional archive projection without permissive row skipping."""
    return _load_index_strict(
        vault_root,
        "00-archive-index.jsonl",
        "archive",
        required=False,
    )


def load_target_index_union_strict(
    vault_root: Path,
) -> tuple[list[dict], list[dict]]:
    """Return current authority rows and current-first target union rows."""
    current = load_current_index_strict(vault_root)
    archive = load_archive_index_strict(vault_root)
    union = list(current)
    seen = {
        row.get("uid")
        for row in current
        if isinstance(row.get("uid"), str)
    }
    for row in archive:
        uid = row.get("uid")
        if isinstance(uid, str) and uid in seen:
            continue
        union.append(row)
        if isinstance(uid, str):
            seen.add(uid)
    return current, union


def _finding(severity: str, code: str, message: str, cure: str) -> ContractFinding:
    return ContractFinding(severity, code, message, cure)


def _failure_result(
    uid: str,
    path: str,
    code: str,
    message: str,
    cure: str,
) -> PruningCheckResult:
    return PruningCheckResult(
        uid=uid,
        path=path,
        applicable=True,
        has_pruning=True,
        findings=(_finding("FAIL", code, message, cure),),
    )


def _index_repair_result(
    uid: str,
    path: str,
    message: str,
) -> PruningCheckResult:
    return _failure_result(
        uid,
        path,
        "PRUNING_INDEX",
        message,
        "run `python3 vault/tools/tropo-rebuild-index.py`, then verify with "
        f"`python3 vault/tools/tropo-check-one.py {uid}`",
    )


def _global_index_repair_result(message: str) -> PruningCheckResult:
    return _failure_result(
        "<global>",
        "vault/00-index.jsonl",
        "PRUNING_INDEX",
        message,
        "run `python3 vault/tools/tropo-rebuild-index.py`, then rerun validation",
    )


def _strict_index_failure_message(exc: PruningIndexError) -> str:
    prefix = (
        "current index validation failed"
        if str(exc).startswith("current index")
        else "target index validation failed"
    )
    return f"{prefix}: {exc}"


def _outside_nav_occurrences(body: bytes, evidence: bytes) -> list[tuple[int, int]]:
    if not evidence:
        return []
    nav_ranges = [(match.start(), match.end()) for match in NAV_BLOCK_RE.finditer(body)]
    occurrences: list[tuple[int, int]] = []
    start = 0
    while True:
        index = body.find(evidence, start)
        if index < 0:
            break
        end = index + len(evidence)
        if not any(index < nav_end and end > nav_start for nav_start, nav_end in nav_ranges):
            occurrences.append((index, end))
        start = index + 1
    return occurrences


def evaluate_pruning_contract(
    *,
    uid: str,
    path: str,
    block: object,
    body: bytes,
    current_t1: str,
    current_t2: str,
    current_records: Sequence[dict],
) -> PruningCheckResult:
    findings: list[ContractFinding] = []
    verify_command = f"`python3 vault/tools/tropo-check-one.py {uid}`"
    try:
        valid = validate_pruning_block(block)
    except Exception as exc:
        findings.append(
            _finding(
                "FAIL",
                "PRUNING_SHAPE",
                str(exc) or type(exc).__name__,
                f"repair or remove the malformed pruning block, then run {verify_command}",
            )
        )
        return PruningCheckResult(
            uid=uid,
            path=path,
            applicable=True,
            has_pruning=True,
            findings=tuple(findings),
        )

    override = valid.get("override")
    override_authorized = False
    if override is not None:
        try:
            resolve_human_principal(override["by"], current_records)
            override_authorized = True
        except PruningContractError as exc:
            findings.append(
                _finding(
                    "FAIL",
                    "PRUNING_OVERRIDE_AUTHORITY",
                    str(exc),
                    f"remove the invalid override or rewrite it through the interactive "
                    f"canonical writer, then run {verify_command}",
                )
            )

    policies = active_policy_candidates(current_records)
    policy_current = (
        len(policies) == 1
        and policies[0].get("uid") == valid["judge_policy_uid"]
        and policies[0].get("version") == valid["judge_version"]
    )
    if not policy_current:
        if len(policies) == 0:
            detail = "no active gardener-body-judge loop resolves in the current index"
        elif len(policies) > 1:
            detail = (
                f"{len(policies)} active gardener-body-judge loops are ambiguous"
            )
        else:
            detail = (
                f"block policy/version ({valid['judge_policy_uid']!r}, "
                f"{valid['judge_version']!r}) does not match active "
                f"({policies[0].get('uid')!r}, {policies[0].get('version')!r})"
            )
        findings.append(
            _finding(
                "WARN",
                "PRUNING_POLICY_STALE",
                detail,
                f"re-queue {uid} under the active judge policy and verify with "
                f"{verify_command}",
            )
        )

    t2_current = valid["normalized_body_hash_judged"] == current_t2
    t1_current = valid["evidence_locator"]["body_sha256"] == current_t1
    if not t2_current:
        findings.append(
            _finding(
                "WARN",
                "PRUNING_T2_STALE",
                "normalized_body_hash_judged does not match the current body",
                f"re-queue {uid} for fresh judgment and verify with {verify_command}",
            )
        )
        return PruningCheckResult(
            uid=uid,
            path=path,
            applicable=True,
            has_pruning=True,
            findings=tuple(findings),
            declared_verdict=valid["verdict"],
            effective_verdict=None,
            t1_current=t1_current,
            t2_current=False,
            policy_current=policy_current,
            override_current=False,
        )

    evidence_valid = False
    locator = valid["evidence_locator"]
    if t1_current:
        try:
            validate_write_evidence(
                body,
                valid["evidence_span"],
                locator["start_byte"],
                locator["end_byte"],
            )
            evidence_valid = True
        except PruningContractError as exc:
            findings.append(
                _finding(
                    "FAIL",
                    "PRUNING_EVIDENCE",
                    str(exc),
                    f"re-stamp byte-exact non-nav evidence through the canonical writer, "
                    f"then run {verify_command}",
                )
            )
    else:
        evidence_bytes = valid["evidence_span"].encode("utf-8")
        occurrences = _outside_nav_occurrences(body, evidence_bytes)
        if len(occurrences) == 1:
            evidence_valid = True
            findings.append(
                _finding(
                    "WARN",
                    "PRUNING_T1_STALE",
                    "raw-body locator is stale but evidence resolves exactly once "
                    "outside generated nav blocks",
                    f"re-stamp the locator through the canonical writer, then run "
                    f"{verify_command}",
                )
            )
        else:
            findings.append(
                _finding(
                    "FAIL",
                    "PRUNING_STALE_EVIDENCE",
                    f"raw-body locator is stale and evidence resolves {len(occurrences)} "
                    "times outside generated nav blocks",
                    f"re-judge and re-stamp byte-exact evidence, then run "
                    f"{verify_command}",
                )
            )

    has_fail = any(finding.severity == "FAIL" for finding in findings)
    override_current = bool(
        override is not None
        and override_authorized
        and t2_current
        and evidence_valid
        and not has_fail
    )
    if has_fail:
        effective = None
    elif override_current:
        effective = "keep"
    elif policy_current and evidence_valid:
        effective = valid["verdict"]
    else:
        effective = None

    return PruningCheckResult(
        uid=uid,
        path=path,
        applicable=True,
        has_pruning=True,
        findings=tuple(findings),
        declared_verdict=valid["verdict"],
        effective_verdict=effective,
        t1_current=t1_current,
        t2_current=True,
        policy_current=policy_current,
        override_current=override_current,
    )


def check_pruning_path(
    path: Path,
    vault_root: Path,
    current_records: Sequence[dict],
    *,
    expected_uid: Optional[str] = None,
) -> PruningCheckResult:
    # Resolve BOTH sides before computing the relative path. `vault_root`
    # was already `.resolve()`d here; `path` was not, so a symlinked
    # ancestor (e.g. a TMPDIR alias, or any studio checked out through a
    # symlink) made `path.relative_to(vault_root)` raise ValueError even
    # for a path genuinely inside the vault. The except branch then fell
    # back to the raw, unresolved absolute path, which never matches
    # `is_declared_pruning_home`'s vault-relative patterns — so the
    # function returned an early not-applicable result (severity PASS,
    # zero findings) for real, in-scope pruning-governed files. That is a
    # fail-open on a governance gate, not a fail-closed skip. Resolving
    # both sides here fixes the false negative; a ValueError that still
    # occurs after full resolution is a genuine escape and fails closed
    # via `_failure_result`, never a silent skip.
    path = Path(path).resolve()
    vault_root = Path(vault_root).resolve()
    uid = expected_uid or path.stem
    try:
        relative = path.relative_to(vault_root)
    except ValueError as exc:
        return _failure_result(
            uid,
            path.as_posix(),
            "PRUNING_PATH_IDENTITY",
            f"resolved path {path} does not resolve inside vault root "
            f"{vault_root}: {exc}",
            "repair the index/source path identity with "
            "`python3 vault/tools/tropo-rebuild-index.py`, then verify with "
            f"`python3 vault/tools/tropo-check-one.py {uid}`",
        )
    path_label = relative.as_posix()
    if not is_declared_pruning_home(relative):
        return PruningCheckResult(uid, path_label, False, False)
    try:
        path, relative = resolve_declared_source_path(
            path,
            vault_root,
            uid,
            indexed=False,
        )
        path_label = relative.as_posix()
    except PruningContractError as exc:
        return _failure_result(
            uid,
            path_label,
            "PRUNING_PATH_IDENTITY",
            str(exc),
            "repair the index/source path identity with "
            "`python3 vault/tools/tropo-rebuild-index.py`, then verify with "
            f"`python3 vault/tools/tropo-check-one.py {uid}`",
        )

    try:
        raw = path.read_bytes()
    except OSError as exc:
        finding = _finding(
            "FAIL",
            "PRUNING_SOURCE_READ",
            str(exc),
            f"restore the governed source, then run "
            f"`python3 vault/tools/tropo-check-one.py {uid}`",
        )
        return PruningCheckResult(
            uid, path_label, True, True, (finding,)
        )
    if not has_top_level_pruning(raw):
        return PruningCheckResult(uid, path_label, True, False)

    try:
        snapshot = parse_markdown_bytes(raw, path_label)
        source_uid = source_scalar(snapshot.frontmatter_text, "uid")
        if source_uid is None or not UID_RE.fullmatch(source_uid):
            raise PruningContractError("source uid must be exactly 8 lowercase hex")
        if expected_uid is not None and source_uid != expected_uid:
            raise PruningContractError(
                f"requested UID {expected_uid} does not match source UID {source_uid}"
            )
        uid = source_uid
        current_t1 = raw_body_sha256(path)
        current_t2 = normalized_body_sha256(path)
    except Exception as exc:
        finding = _finding(
            "FAIL",
            "PRUNING_SOURCE_SHAPE",
            str(exc) or type(exc).__name__,
            f"repair the governed Markdown boundary/frontmatter, then run "
            f"`python3 vault/tools/tropo-check-one.py {uid}`",
        )
        return PruningCheckResult(
            uid, path_label, True, True, (finding,)
        )

    return evaluate_pruning_contract(
        uid=uid,
        path=path_label,
        block=snapshot.frontmatter.get("pruning"),
        body=snapshot.body,
        current_t1=current_t1,
        current_t2=current_t2,
        current_records=current_records,
    )


def _path_label(path: Path, vault_root: Path) -> str:
    try:
        return path.relative_to(vault_root).as_posix()
    except ValueError:
        return path.as_posix()


def _source_uid(path: Path) -> str:
    try:
        snapshot = read_markdown_snapshot(path)
        uid = source_scalar(snapshot.frontmatter_text, "uid")
        if uid is not None and UID_RE.fullmatch(uid):
            return uid
    except Exception:
        pass
    return path.stem


def _path_carries_pruning(path: Path) -> bool:
    try:
        return has_top_level_pruning(path.read_bytes())
    except OSError:
        return False


def _direct_uid_candidates(uid: str, vault_root: Path) -> list[Path]:
    return [
        vault_root / "vault" / "files" / f"{uid}.md",
        vault_root / "vault" / "agents" / f"{uid}.md",
        vault_root / "vault" / "capsules" / f"{uid}.md",
        vault_root / "agents" / f"{uid}.md",
    ]


def _indexed_row_check(
    uid: str,
    row: dict,
    vault_root: Path,
    current_records: Sequence[dict],
    *,
    expected_path: Optional[Path] = None,
) -> PruningCheckResult:
    relative = row.get("path")
    path_label = (
        relative if isinstance(relative, str) and relative else f"<index:{uid}>"
    )
    supplied_path = Path(relative) if isinstance(relative, str) else None
    if (
        supplied_path is not None
        and not supplied_path.is_absolute()
        and ".." not in supplied_path.parts
        and not is_declared_pruning_home(supplied_path)
    ):
        # Pruning is deliberately closed to four Markdown homes. Targeted
        # check-one must preserve the full-vault scanner's silent
        # non-applicability for indexed tools, actions, playbooks, and other
        # source classes outside that boundary; this checker is not a global
        # index-path validator.
        return PruningCheckResult(uid, path_label, False, False)
    try:
        path, _relative = resolve_declared_source_path(
            relative,
            vault_root,
            uid,
            indexed=True,
        )
    except Exception as exc:
        return _index_repair_result(
            uid,
            path_label,
            f"indexed pruning source identity failed: "
            f"{str(exc) or type(exc).__name__}",
        )
    if expected_path is not None and path != expected_path:
        return _index_repair_result(
            uid,
            path_label,
            "indexed pruning source path does not match the discovered governed source",
        )

    carries_pruning = _path_carries_pruning(path)
    row_carries_pruning = "pruning" in row
    if not carries_pruning:
        if row_carries_pruning:
            return _index_repair_result(
                uid,
                path_label,
                "target index carries pruning but the indexed source does not",
            )
        return PruningCheckResult(uid, path_label, True, False)
    if not row_carries_pruning:
        return _index_repair_result(
            uid,
            path_label,
            "pruning-bearing source is missing its target-index pruning projection",
        )
    return check_pruning_path(
        path,
        vault_root,
        current_records,
        expected_uid=uid,
    )


def check_pruning_uid(
    uid: str,
    vault_root: Path,
) -> Optional[PruningCheckResult]:
    """Strict targeted pruning validation for one indexed UID."""
    vault_root = Path(vault_root).resolve()
    try:
        current_records, target_records = load_target_index_union_strict(vault_root)
    except PruningIndexError as exc:
        candidate = next(
            (
                path
                for path in _direct_uid_candidates(uid, vault_root)
                if path.is_file()
                and not _has_symlink_component(path, vault_root)
                and _path_carries_pruning(path)
            ),
            None,
        )
        if candidate is None:
            return _global_index_repair_result(
                _strict_index_failure_message(exc)
            )
        return _index_repair_result(
            uid,
            _path_label(candidate, vault_root),
            _strict_index_failure_message(exc),
        )

    matches = [row for row in target_records if row.get("uid") == uid]
    if len(matches) != 1:
        candidate = next(
            (
                path
                for path in _direct_uid_candidates(uid, vault_root)
                if path.is_file()
                and not _has_symlink_component(path, vault_root)
                and _path_carries_pruning(path)
            ),
            None,
        )
        if candidate is None:
            return None
        return _index_repair_result(
            uid,
            _path_label(candidate, vault_root),
            f"pruning-bearing UID must resolve to exactly one current/archive "
            f"target row; "
            f"found {len(matches)}",
        )
    return _indexed_row_check(uid, matches[0], vault_root, current_records)


def check_pruning_vault(
    vault_root: Path,
    current_records: Optional[Sequence[dict]] = None,
) -> list[PruningCheckResult]:
    """Strict full scan with index/source reconciliation and path deduplication."""
    vault_root = Path(vault_root).resolve()
    source_paths = [
        path
        for path in iter_eligible_markdown(vault_root)
        if not _has_symlink_component(path, vault_root)
        and _path_carries_pruning(path)
    ]

    if current_records is None:
        try:
            authority_records, records = load_target_index_union_strict(vault_root)
        except PruningIndexError as exc:
            results: list[PruningCheckResult] = []
            seen: set[Path] = set()
            for path in source_paths:
                try:
                    identity = path.resolve(strict=False)
                except (OSError, RuntimeError):
                    identity = path
                if identity in seen:
                    continue
                seen.add(identity)
                uid = _source_uid(path)
                results.append(
                    _index_repair_result(
                        uid,
                        _path_label(path, vault_root),
                        _strict_index_failure_message(exc),
                    )
                )
            if not results:
                results.append(
                    _global_index_repair_result(
                        _strict_index_failure_message(exc)
                    )
                )
            return results
    else:
        authority_records = list(current_records)
        records = authority_records

    rows_by_uid: dict[str, list[dict]] = {}
    rows_by_path: dict[str, list[dict]] = {}
    for row in records:
        if not isinstance(row, dict):
            continue
        uid = row.get("uid")
        if isinstance(uid, str):
            rows_by_uid.setdefault(uid, []).append(row)
        relative = row.get("path")
        if isinstance(relative, str):
            rows_by_path.setdefault(relative, []).append(row)

    results = []
    handled_uids: set[str] = set()
    seen_paths: set[Path] = set()
    for path in source_paths:
        try:
            identity = path.resolve(strict=False)
        except (OSError, RuntimeError):
            identity = path
        if identity in seen_paths:
            continue
        seen_paths.add(identity)
        uid = _source_uid(path)
        if not UID_RE.fullmatch(uid):
            path_matches = rows_by_path.get(_path_label(path, vault_root), [])
            if (
                len(path_matches) == 1
                and isinstance(path_matches[0].get("uid"), str)
                and UID_RE.fullmatch(path_matches[0]["uid"])
            ):
                uid = path_matches[0]["uid"]
                handled_uids.add(uid)
                result = _indexed_row_check(
                    uid,
                    path_matches[0],
                    vault_root,
                    authority_records,
                    expected_path=path,
                )
            else:
                result = check_pruning_path(
                    path,
                    vault_root,
                    authority_records,
                )
            if result.has_pruning:
                results.append(result)
            continue
        matches = rows_by_uid.get(uid, [])
        handled_uids.add(uid)
        if len(matches) != 1:
            results.append(
                _index_repair_result(
                    uid,
                    _path_label(path, vault_root),
                    "pruning-bearing UID must resolve to exactly one current/archive "
                    f"target row; found {len(matches)}",
                )
            )
            continue
        try:
            expected_path, _relative = resolve_declared_source_path(
                path,
                vault_root,
                uid,
                indexed=False,
            )
        except PruningContractError:
            expected_path = path
        results.append(
            _indexed_row_check(
                uid,
                matches[0],
                vault_root,
                authority_records,
                expected_path=expected_path,
            )
        )

    for row in records:
        if not isinstance(row, dict):
            continue
        if "pruning" not in row:
            continue
        uid = row.get("uid")
        if not isinstance(uid, str) or not UID_RE.fullmatch(uid):
            results.append(
                _index_repair_result(
                    "<invalid-uid>",
                    str(row.get("path") or "<index>"),
                    "target-index pruning row has no valid 8-hex UID",
                )
            )
            continue
        if uid in handled_uids:
            continue
        handled_uids.add(uid)
        results.append(
            _indexed_row_check(
                uid,
                row,
                vault_root,
                authority_records,
            )
        )
    return results


__all__ = [
    "ContractFinding",
    "EVIDENCE_DOCTRINE",
    "HASH_RE",
    "MarkdownSnapshot",
    "NAV_BLOCK_RE",
    "POLICY_RUNNER",
    "PruningCheckResult",
    "PruningContractError",
    "PruningIndexError",
    "UID_RE",
    "VERDICTS",
    "active_policy_candidates",
    "check_pruning_path",
    "check_pruning_uid",
    "check_pruning_vault",
    "evaluate_pruning_contract",
    "has_top_level_pruning",
    "is_declared_pruning_home",
    "iter_eligible_markdown",
    "load_archive_index_strict",
    "load_current_index_strict",
    "load_target_index_union_strict",
    "parse_frontmatter_mapping",
    "parse_markdown_bytes",
    "read_markdown_snapshot",
    "resolve_active_policy",
    "resolve_declared_source_path",
    "resolve_human_principal",
    "resolve_indexed_pruning_source",
    "source_scalar",
    "validate_confidence",
    "validate_hash",
    "validate_pruning_block",
    "validate_locked_snapshot_identity",
    "validate_trimmed_string",
    "validate_write_evidence",
]
