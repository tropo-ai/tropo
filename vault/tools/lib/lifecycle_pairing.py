"""Strict parser and verdict engine for capsule lifecycle-pairing declarations.

`enforced_enums` validates `status` and `state` as independent vocabularies.
Neither check can see the *relation* between them, so a project at
`status: evergreen, state: archived` passes both while the project capsule says
evergreen never terminates.  This module reads the declaration that closes that
gap, and is the single verdict engine for every consumer of it.

Capsule frontmatter is canonical and is never modified here.  Declared statuses
resolve through the same capsule's `enforced_enums` canon and aliases, so no
consumer maintains a second status list.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import lifecycle_machine as lm

ARCHIVED_WILDCARD = "any"
ARCHIVED_STATE = "archived"

TERMINAL_KEY = "terminal_statuses"
ARCHIVED_KEY = "archived_state_allowed_statuses"
_DECLARED_KEYS = frozenset({TERMINAL_KEY, ARCHIVED_KEY})

RULE_ARCHIVED_NOT_ALLOWED = "archived-state-status-not-allowed"
RULE_UNKNOWN_STATUS = "unknown-source-status"


class LifecyclePairingError(ValueError):
    """A capsule lifecycle-pairing declaration is malformed or inconsistent."""


@dataclass(frozen=True)
class PairingViolation:
    """One source record that its own type's law does not permit."""

    uid: str
    path: str
    type_name: str
    raw_status: str
    canonical_status: Optional[str]
    state: str
    rule_id: str
    contract_sha256: str

    def as_row(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "path": self.path,
            "type": self.type_name,
            "raw_status": self.raw_status,
            "canonical_status": self.canonical_status,
            "state": self.state,
            "rule_id": self.rule_id,
            "contract_sha256": self.contract_sha256,
        }


@dataclass(frozen=True)
class LifecyclePairing:
    """One type's declared pairing law, resolved against its own enum."""

    type_name: str
    terminal_statuses: frozenset
    terminal_source: str
    archived_allows_any: bool
    archived_allowed_statuses: frozenset
    raw_terminal_statuses: Tuple[str, ...]
    raw_archived_allowed: Tuple[str, ...]
    canonical_statuses: Tuple[str, ...]
    aliases: Dict[str, str]
    capsule_path: Path

    def canonicalize(self, raw_status: str) -> Optional[str]:
        """The canonical form of a source status, or None when unknown.

        None is a real answer, not a failure to compute: an unknown status is
        reported with `canonical_status: null` so a census stays complete and
        the row can never be mistaken for a legal one.
        """
        if not isinstance(raw_status, str):
            return None
        value = raw_status.strip().lower()
        if value in self.canonical_statuses:
            return value
        return self.aliases.get(value)

    def is_terminal(self, raw_status: str) -> bool:
        canonical = self.canonicalize(raw_status)
        return canonical is not None and canonical in self.terminal_statuses

    def permits_archived(self, raw_status: str) -> bool:
        if self.archived_allows_any:
            return self.canonicalize(raw_status) is not None
        canonical = self.canonicalize(raw_status)
        return canonical is not None and canonical in self.archived_allowed_statuses

    @property
    def contract_sha256(self) -> str:
        """A stable digest of this type's effective pairing law.

        Baseline rows carry it so an unrelated sweep commit does not invalidate
        every remaining row, while a genuine contract change invalidates exactly
        the rows it governs.
        """
        payload = json.dumps(
            {
                "type": self.type_name,
                "terminal_statuses": sorted(self.terminal_statuses),
                "terminal_source": self.terminal_source,
                "archived_state_allowed_statuses": (
                    ARCHIVED_WILDCARD
                    if self.archived_allows_any
                    else sorted(self.archived_allowed_statuses)
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fail(path: Path, message: str) -> LifecyclePairingError:
    return LifecyclePairingError("{}: {}".format(path.name, message))


def _delegated(call, *args, **kwargs):
    """Run a shared lifecycle_machine helper, surfacing one error type.

    The helpers are reused deliberately — a second frontmatter reader or status
    vocabulary is the drift this package exists to remove — but a caller that
    catches LifecyclePairingError must not have malformed YAML escape past it
    wearing LifecycleMachineError.
    """
    try:
        return call(*args, **kwargs)
    except lm.LifecycleMachineError as exc:
        raise LifecyclePairingError(str(exc)) from exc


def _resolve_declared(
    values: Any,
    *,
    path: Path,
    location: str,
    canonical: Tuple[str, ...],
    aliases: Dict[str, str],
) -> Tuple[Tuple[str, ...], frozenset]:
    """Validate one declared status list and resolve it to canonical values."""
    if not isinstance(values, list):
        raise _fail(path, "{} must be a list".format(location))
    if not values:
        raise _fail(
            path,
            "{} must be a non-empty list; an empty declaration answers nothing".format(
                location
            ),
        )

    raw: list = []
    resolved: list = []
    for index, value in enumerate(values):
        member = "{}[{}]".format(location, index)
        if not isinstance(value, str) or not value.strip():
            raise _fail(path, "{} must be a non-empty string".format(member))
        normalized = value.strip().lower()
        if normalized == ARCHIVED_WILDCARD:
            raise _fail(
                path,
                "{} may not contain {!r}; the wildcard is legal only as the "
                "scalar {} value".format(member, ARCHIVED_WILDCARD, ARCHIVED_KEY),
            )
        if normalized in canonical:
            canonical_value = normalized
        elif normalized in aliases:
            canonical_value = aliases[normalized]
        else:
            raise _fail(
                path,
                "{} declares {!r}, which is not a canonical status or alias for "
                "this type ({})".format(member, value, sorted(canonical)),
            )
        if canonical_value in resolved:
            raise _fail(
                path,
                "{} declares {!r}, a duplicate of already-declared status "
                "{!r}".format(member, value, canonical_value),
            )
        raw.append(value.strip())
        resolved.append(canonical_value)
    return tuple(raw), frozenset(resolved)


def parse_capsule_lifecycle_pairing(path: Path) -> Optional[LifecyclePairing]:
    """Parse one capsule's declaration, returning None when it opts out.

    Opting out means "not declared / not checked".  It never means "apply a
    global default": one shared terminal set would falsely reject done-and-
    current law and miss per-type archive rules.
    """
    frontmatter = _delegated(lm._frontmatter, path)
    block = _delegated(
        lm._top_level_block, frontmatter, "lifecycle_pairing", path, required=False
    )
    if block is None:
        return None

    declaration = _delegated(lm._parse_block, block, "lifecycle_pairing", path)
    if not isinstance(declaration, dict):
        raise _fail(path, "lifecycle_pairing must be a mapping")
    unknown = sorted(set(declaration) - _DECLARED_KEYS, key=str)
    if unknown:
        raise _fail(
            path,
            "lifecycle_pairing is a closed block; unknown key(s) {}".format(unknown),
        )

    canonical, aliases = _delegated(lm.canonical_enum_for_field, path, "status")
    machine = _delegated(lm.parse_capsule_lifecycle_machine, path)

    if machine is not None:
        if TERMINAL_KEY in declaration:
            raise _fail(
                path,
                "lifecycle_pairing.{} is forbidden when lifecycle_machine exists; "
                "terminality has one authority and two sources can "
                "disagree".format(TERMINAL_KEY),
            )
        terminal_source = "machine"
        raw_terminal = tuple(
            state.value for state in machine.states if state.terminal
        )
        terminal = frozenset(raw_terminal)
        if not terminal:
            raise _fail(
                path,
                "lifecycle_machine declares no terminal state, so lifecycle_pairing "
                "cannot resolve terminality",
            )
    else:
        if TERMINAL_KEY not in declaration:
            raise _fail(
                path,
                "lifecycle_pairing.{} is required when the capsule declares no "
                "lifecycle_machine".format(TERMINAL_KEY),
            )
        terminal_source = "fallback"
        raw_terminal, terminal = _resolve_declared(
            declaration[TERMINAL_KEY],
            path=path,
            location="lifecycle_pairing.{}".format(TERMINAL_KEY),
            canonical=canonical,
            aliases=aliases,
        )

    if ARCHIVED_KEY not in declaration:
        raise _fail(
            path,
            "lifecycle_pairing.{} is required; a declaration that says nothing "
            "about archival is not a pairing".format(ARCHIVED_KEY),
        )
    archived_raw_value = declaration[ARCHIVED_KEY]
    if isinstance(archived_raw_value, str):
        if archived_raw_value.strip().lower() != ARCHIVED_WILDCARD:
            raise _fail(
                path,
                "lifecycle_pairing.{} scalar form must be {!r}; got {!r}".format(
                    ARCHIVED_KEY, ARCHIVED_WILDCARD, archived_raw_value
                ),
            )
        archived_allows_any = True
        raw_archived: Tuple[str, ...] = (ARCHIVED_WILDCARD,)
        archived_allowed = frozenset()
    else:
        archived_allows_any = False
        raw_archived, archived_allowed = _resolve_declared(
            archived_raw_value,
            path=path,
            location="lifecycle_pairing.{}".format(ARCHIVED_KEY),
            canonical=canonical,
            aliases=aliases,
        )

    return LifecyclePairing(
        type_name=_delegated(lm.capsule_type_from_filename, path),
        terminal_statuses=terminal,
        terminal_source=terminal_source,
        archived_allows_any=archived_allows_any,
        archived_allowed_statuses=archived_allowed,
        raw_terminal_statuses=raw_terminal,
        raw_archived_allowed=raw_archived,
        canonical_statuses=canonical,
        aliases=dict(aliases),
        capsule_path=path,
    )


def load_lifecycle_pairings(vault_root: Path) -> Dict[str, LifecyclePairing]:
    """Every declared pairing in the studio, keyed by governed type name."""
    capsules_dir = Path(vault_root) / "vault" / "capsules"
    if not capsules_dir.is_dir():
        return {}
    pairings: Dict[str, LifecyclePairing] = {}
    for capsule_path in sorted(capsules_dir.glob("*.capsule.md")):
        pairing = parse_capsule_lifecycle_pairing(capsule_path)
        if pairing is None:
            continue
        if pairing.type_name in pairings:
            raise LifecyclePairingError(
                "duplicate lifecycle_pairing declaration for type {!r}".format(
                    pairing.type_name
                )
            )
        pairings[pairing.type_name] = pairing
    return pairings


def evaluate_record(
    pairing: LifecyclePairing,
    *,
    uid: str,
    path: str,
    raw_status: Any,
    state: Any,
) -> Optional[PairingViolation]:
    """Judge one source record against its type's declared law.

    Returns None when the record is permitted.  `state: active` is never a
    violation on terminal status alone — a done decision may legitimately remain
    the current reference, and calling that a contradiction is the folklore this
    engine replaces.
    """
    raw_status_text = raw_status.strip() if isinstance(raw_status, str) else ""
    state_text = state.strip().lower() if isinstance(state, str) else ""
    canonical_status = pairing.canonicalize(raw_status_text)

    if canonical_status is None:
        return PairingViolation(
            uid=uid,
            path=path,
            type_name=pairing.type_name,
            raw_status=raw_status_text,
            canonical_status=None,
            state=state_text,
            rule_id=RULE_UNKNOWN_STATUS,
            contract_sha256=pairing.contract_sha256,
        )

    if state_text != ARCHIVED_STATE:
        return None

    if pairing.permits_archived(raw_status_text):
        return None

    return PairingViolation(
        uid=uid,
        path=path,
        type_name=pairing.type_name,
        raw_status=raw_status_text,
        canonical_status=canonical_status,
        state=state_text,
        rule_id=RULE_ARCHIVED_NOT_ALLOWED,
        contract_sha256=pairing.contract_sha256,
    )


REQUIRED_TYPES = (
    "arch-spec",
    "design-brief",
    "dev-spec",
    "project",
    "task",
    "test-spec",
)

SCHEMA_VERSION = 1

ERR_MISSING_DECLARATION = "missing-declaration"
ERR_MALFORMED_DECLARATION = "malformed-declaration"
ERR_UNREADABLE_SOURCE = "unreadable-source"
ERR_DUPLICATE_UID = "duplicate-uid"


def _entry_frontmatter(path: Path) -> Optional[Dict[str, Any]]:
    """Parse one governed file's frontmatter, or None when it has none."""
    text = path.read_text(encoding="utf-8", errors="strict")
    match = lm._FRONTMATTER_RE.match(text)
    if match is None:
        return None
    parsed = lm.yaml.safe_load(match.group("frontmatter"))
    return parsed if isinstance(parsed, dict) else None


def scan_source_pairings(
    vault_root: Path,
    pairings: Optional[Dict[str, LifecyclePairing]] = None,
) -> Dict[str, Any]:
    """Census every governed source file against its type's declared law.

    The scan reads `vault/files/*.md` directly.  It does not consult an index
    row to validate the source that row is derived from — a false green from a
    stale projection is the failure this check exists to prevent.

    Severity lives with the caller.  This function reports what is true:
    which declarations loaded, how many instances of each declared type were
    discovered and checked, and the exact violating records.
    """
    vault_root = Path(vault_root)
    if pairings is None:
        try:
            pairings = load_lifecycle_pairings(vault_root)
        except LifecyclePairingError as exc:
            return {
                "loaded": {},
                "coverage": {},
                "violations": [],
                "errors": [{"code": ERR_MALFORMED_DECLARATION, "path": "", "detail": str(exc)}],
            }

    coverage = {name: {"discovered": 0, "checked": 0} for name in pairings}
    violations: list = []
    errors: list = []
    seen_uids: Dict[str, str] = {}

    files_dir = vault_root / "vault" / "files"
    for source in sorted(files_dir.glob("*.md")) if files_dir.is_dir() else []:
        rel = str(source.relative_to(vault_root))
        try:
            fm = _entry_frontmatter(source)
        except Exception as exc:
            errors.append(
                {"code": ERR_UNREADABLE_SOURCE, "path": rel, "detail": str(exc)}
            )
            continue
        if not fm:
            continue
        type_name = fm.get("type")
        if not isinstance(type_name, str) or type_name not in pairings:
            continue

        coverage[type_name]["discovered"] += 1
        uid = fm.get("uid")
        uid_text = uid.strip() if isinstance(uid, str) else ""
        if uid_text:
            if uid_text in seen_uids:
                errors.append(
                    {
                        "code": ERR_DUPLICATE_UID,
                        "path": rel,
                        "detail": "uid {} also declared by {}".format(
                            uid_text, seen_uids[uid_text]
                        ),
                    }
                )
            else:
                seen_uids[uid_text] = rel

        violation = evaluate_record(
            pairings[type_name],
            uid=uid_text,
            path=rel,
            raw_status=fm.get("status"),
            state=fm.get("state"),
        )
        coverage[type_name]["checked"] += 1
        if violation is not None:
            violations.append(violation)

    violations.sort(key=lambda v: (v.path, v.uid))
    return {
        "loaded": pairings,
        "coverage": coverage,
        "violations": violations,
        "errors": errors,
    }


PAIRING_BASELINE_RELATIVE_PATH = ".tropo/state-pairing-debt-baseline.json"


CLOSURE_REVIEW_KEY = "closure_review_candidate"


def CLOSURE_REVIEW_KEY_PRESENT(frontmatter: Dict[str, Any]) -> bool:
    """True when source frontmatter carries the derived-only closure key.

    Kept here so the validator, check-one and the Gardener all ask the same
    question the same way.
    """
    return isinstance(frontmatter, dict) and CLOSURE_REVIEW_KEY in frontmatter


def pairing_row_signature(violation) -> str:
    """One pairing row's identity per the locked contract.

    UID and path, raw and canonical status, state, rule id, and the type's
    pairing-contract hash. Scoped this way on purpose: an unrelated sweep commit
    must not invalidate every remaining row, while a genuine contract change
    invalidates exactly the rows that contract governs.
    """
    row = violation.as_row() if hasattr(violation, "as_row") else dict(violation)
    return "|".join([
        str(row.get("uid") or ""),
        str(row.get("path") or ""),
        str(row.get("raw_status") or ""),
        "" if row.get("canonical_status") is None else str(row.get("canonical_status")),
        str(row.get("state") or ""),
        str(row.get("rule_id") or ""),
        str(row.get("contract_sha256") or ""),
    ])


def load_pairing_baseline(vault_root: Path) -> Dict[str, Any]:
    """Read the measured pairing baseline, or an empty one when absent.

    Absent means no debt is excused; it never means the tree is clean.
    """
    path = Path(vault_root) / PAIRING_BASELINE_RELATIVE_PATH
    if not path.is_file():
        return {"present": False, "signatures": {}, "header": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise LifecyclePairingError(
            "{} is unreadable: {}".format(PAIRING_BASELINE_RELATIVE_PATH, exc)
        )
    rows = raw.get("rows")
    if not isinstance(rows, list):
        raise LifecyclePairingError(
            "{} has no rows list".format(PAIRING_BASELINE_RELATIVE_PATH)
        )
    signatures = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("signature"):
            raise LifecyclePairingError(
                "{} contains a malformed row".format(PAIRING_BASELINE_RELATIVE_PATH)
            )
        signatures[row["signature"]] = row
    return {
        "present": True,
        "signatures": signatures,
        "header": {k: v for k, v in raw.items() if k != "rows"},
    }


def write_pairing_baseline(vault_root: Path) -> Tuple[list, int]:
    """Capture or shrink the measured pairing baseline.

    Shrink-only after the first write: a subset is legal, growth refuses. An
    allowlist that grows on demand legalizes every regression it meets.
    """
    vault_root = Path(vault_root)
    messages: list = []
    scan = scan_source_pairings(vault_root)
    if scan["errors"]:
        messages.append(
            "[FAIL] refusing to capture a baseline from an incomplete census; "
            "{} error(s)".format(len(scan["errors"]))
        )
        return messages, 2

    rows = {}
    for violation in scan["violations"]:
        row = violation.as_row()
        row["signature"] = pairing_row_signature(violation)
        rows[row["signature"]] = row

    existing = load_pairing_baseline(vault_root)
    if existing["present"]:
        grown = set(rows) - set(existing["signatures"])
        if grown:
            messages.append(
                "[FAIL] refusing to grow the pairing baseline by {} signature(s); "
                "a baseline that grows is an amnesty".format(len(grown))
            )
            for signature in sorted(grown)[:10]:
                messages.append("  would add: {}".format(signature))
            return messages, 1

    contract_hashes = sorted({
        pairing.contract_sha256 for pairing in scan["loaded"].values()
    })
    payload = {
        "schema_version": 1,
        "captured_at": _utc_now(),
        "creation_commit": _git_head(vault_root),
        "census_sha256": _census_digest(scan),
        "contract_sha256": hashlib.sha256(
            "|".join(contract_hashes).encode("utf-8")
        ).hexdigest(),
        "authority": "dev-spec 271d28d7 (locked); dd570ea4 must empty this file",
        "row_count": len(rows),
        "rows": [rows[key] for key in sorted(rows)],
    }
    path = vault_root / PAIRING_BASELINE_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    messages.append("[PASS] wrote {} signature(s) to {}".format(
        len(rows), PAIRING_BASELINE_RELATIVE_PATH))
    return messages, 0


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head(vault_root: Path) -> str:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(vault_root),
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _census_digest(scan: Dict[str, Any]) -> str:
    """A digest of what the census SAW, so a baseline cannot outlive its census."""
    payload = json.dumps(
        {name: dict(counts) for name, counts in sorted(scan["coverage"].items())},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_report(
    vault_root: Path,
    *,
    mode: str = "report",
    baseline: Optional[Dict[str, Any]] = None,
    enum_summary: Optional[Dict[str, Any]] = None,
    required_types: Optional[tuple] = None,
) -> Dict[str, Any]:
    """The closed JSON document both machine modes emit (amended 2026-08-16).

    One shape, one schema version, so a consumer never branches on which mode
    produced it. Pairing and enum debt are counted separately and carry separate
    baselines: they are different contracts with different cures, and a single
    merged number would let one hide inside the other.

    `complete` is a census property and `gate_pass` a verdict. Keeping them
    apart is what lets a caller distinguish "clean" from "did not actually
    look", which a bounded scan reports backwards by default.
    """
    vault_root = Path(vault_root)
    required = REQUIRED_TYPES if required_types is None else tuple(required_types)
    scan = scan_source_pairings(vault_root)
    loaded = scan["loaded"]
    loaded_types = sorted(loaded)
    missing_types = [name for name in required if name not in loaded]

    coverage = {
        name: dict(scan["coverage"][name]) for name in sorted(scan["coverage"])
    }
    incomplete = [
        name for name, counts in coverage.items()
        if counts["discovered"] > 0 and counts["checked"] == 0
    ]
    errors = list(scan["errors"])
    for name in missing_types:
        errors.append({
            "code": ERR_MISSING_DECLARATION,
            "path": "vault/capsules/tropo-{}.capsule.md".format(name),
            "detail": "required type declares no lifecycle_pairing",
        })

    if baseline is None:
        try:
            baseline = load_pairing_baseline(vault_root)
        except LifecyclePairingError as exc:
            baseline = {"present": False, "signatures": {}, "header": {}}
            errors.append({
                "code": ERR_MALFORMED_DECLARATION,
                "path": PAIRING_BASELINE_RELATIVE_PATH,
                "detail": str(exc),
            })
    known = baseline.get("signatures") or {}
    header = baseline.get("header") or {}

    violations = []
    seen_signatures = set()
    for violation in scan["violations"]:
        row = violation.as_row()
        signature = pairing_row_signature(violation)
        seen_signatures.add(signature)
        row["baseline_disposition"] = "known" if signature in known else "new"
        violations.append(row)
    violations.sort(key=lambda row: (row["path"], row["uid"]))

    pairing_known = sum(1 for row in violations if row["baseline_disposition"] == "known")
    pairing_new = len(violations) - pairing_known
    # A baselined row that no longer occurs is stale: the sweep fixed it and the
    # baseline must shrink to match, or it starts excusing something that is gone.
    stale_pairing = sorted(set(known) - seen_signatures)

    enum = enum_summary or {}
    enum_violations = int(enum.get("violations", 0) or 0)
    enum_known = int(enum.get("known_debt", 0) or 0)
    enum_new = int(enum.get("new_failures", 0) or 0)
    stale_enum = list(enum.get("stale_rows") or [])
    enum_present = bool(enum.get("present", False))
    enum_rows = int(enum.get("row_count", 0) or 0)

    complete = not missing_types and not incomplete and not errors
    baselines_empty = not known and not enum_rows

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "complete": complete,
        # Both baselines empty is part of the gate: known debt means the cleanup
        # is not finished, however clean today's scan looks.
        "gate_pass": (
            complete and not violations and enum_violations == 0 and baselines_empty
        ),
        "declarations": {
            "required_types": list(required),
            "loaded_types": loaded_types,
            "missing_types": missing_types,
            "coverage": coverage,
        },
        "counts": {
            "pairing_violations": len(violations),
            "enum_violations": enum_violations,
            "pairing_known_debt": pairing_known,
            "enum_known_debt": enum_known,
            "new_pairing_failures": pairing_new,
            "new_enum_failures": enum_new,
            "stale_pairing_baseline_rows": len(stale_pairing),
            "stale_enum_baseline_rows": len(stale_enum),
            "errors": len(errors),
        },
        "violations": violations,
        "baselines": {
            "pairing": {
                "present": bool(baseline.get("present")),
                "contract_sha256": header.get("contract_sha256", ""),
                "row_count": len(known),
                "stale_rows": stale_pairing,
            },
            "enum": {
                "present": enum_present,
                "contract_sha256": enum.get("contract_sha256", ""),
                "row_count": enum_rows,
                "stale_rows": stale_enum,
            },
            "creation_commit": header.get("creation_commit", ""),
            "census_sha256": header.get("census_sha256", ""),
        },
        "errors": errors,
    }


__all__ = [
    "pairing_row_signature",
    "write_pairing_baseline",
    "load_pairing_baseline",
    "PAIRING_BASELINE_RELATIVE_PATH",
    "ARCHIVED_WILDCARD",
    "REQUIRED_TYPES",
    "SCHEMA_VERSION",
    "build_report",
    "scan_source_pairings",
    "LifecyclePairing",
    "LifecyclePairingError",
    "PairingViolation",
    "RULE_ARCHIVED_NOT_ALLOWED",
    "RULE_UNKNOWN_STATUS",
    "evaluate_record",
    "load_lifecycle_pairings",
    "parse_capsule_lifecycle_pairing",
]
