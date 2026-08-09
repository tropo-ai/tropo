"""Public release receipt projection — ``tropo.public-release-projection.v1``.

Destination-agnostic projection + canonicalization layer for the G1.2 public
receipt system (design brief ``459a3070``). It reconstructs the exact six-field
public projection from one accepted Public Snapshot v1 release fact, produces the
canonical projection bytes and ``projection_sha256``, and builds/validates the
``receipt-index.json`` map. This is the L1-governed cross-implementation
reference: the website consumer must reproduce byte-identical projections and
identical hashes from the same shared vectors.

Boundaries (Argus A134 G1.2 disposition, 2026-07-18 — PARTIAL GO):
- This module is destination-agnostic. It performs no network operation, opens no
  transport, and reads no Argo substrate. It consumes only already-validated
  release-fact fields passed to it.
- The dedicated-repo transport publisher is HELD pending Mike infra gates (repo
  creation + repo-scoped principal + hostile permission test) and Mike-locked
  dev/test specs. Do not add transport here.
- The projection is a narrow PUBLIC subset. It excludes every private proof field
  carried by the internal release receipt (remote SHAs, verify-live timestamps,
  publisher identity, source hashes, repository/kind labels, event/release UIDs,
  operational state). Widening requires the Mike-approved schema-amendment path.

Canonicalization is reused verbatim from the sibling ``release_receipt`` module so
publisher and consumer share one canonicalization implementation.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


def _load_release_receipt():
    """Load the sibling canonicalization module as the single source of truth."""
    module_name = "tropo_public_receipt_release_receipt"
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).resolve().with_name("release_receipt.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load canonical release_receipt module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_rr = _load_release_receipt()

# --- reused canonicalization primitives (single source: release_receipt) -------
canonical_json_bytes = _rr.canonical_json_bytes
sha256_bytes = _rr.sha256_bytes
validate_timestamp = _rr.validate_timestamp
REPOSITORY = _rr.REPOSITORY
SHA256_RE = _rr.SHA256_RE

# --- projection contract (design brief 459a3070) -------------------------------
PROJECTION_SCHEMA = "tropo.public-release-projection.v1"
RELEASE_TYPE = "tropo.release.published"
INDEX_SCHEMA_VERSION = "1.0.0"

PROJECTION_FIELDS = frozenset(
    {"public_fact_id", "type", "occurred_at", "version", "tag", "public_url"}
)
INDEX_TOP_FIELDS = frozenset({"schema_version", "facts"})
INDEX_ENTRY_FIELDS = frozenset({"path", "projection_sha256", "projection_schema"})

PUBLIC_FACT_ID_RE = re.compile(r"^rf_[0-9a-f]{64}$")

# Argus P1-1: the public projection version is an EXACT canonical rule so publisher
# and consumer never disagree. It is SemVer core plus an optional pre-release, with
# NO leading ``v`` and NO build metadata. Build metadata (``+...``) is excluded
# deliberately: it carries no release-precedence meaning (SemVer 2.0.0 ignores it
# for ordering), and it would create tag/URL encoding ambiguity because
# ``tag == v<version>`` and ``public_url`` embeds the tag. A release that genuinely
# needs build metadata is a Mike-approved schema amendment, never a silent widening.
_SEMVER_CORE = r"(?:0|[1-9][0-9]*)"
_SEMVER_IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
PROJECTION_SEMVER_RE = re.compile(
    rf"^{_SEMVER_CORE}\.{_SEMVER_CORE}\.{_SEMVER_CORE}"
    rf"(?:-{_SEMVER_IDENTIFIER}(?:\.{_SEMVER_IDENTIFIER})*)?$"
)


class ProjectionError(ValueError):
    """A projection, index, or version violates the v1 public contract."""


# --- version / tag / url helpers ----------------------------------------------
def normalize_version(raw: Any) -> str:
    """Strip exactly one optional leading ``v`` and validate the canonical rule.

    Returns the normalized version string (no leading ``v``, no build metadata).
    """
    if not isinstance(raw, str) or not raw:
        raise ProjectionError("version must be a non-empty string")
    candidate = raw[1:] if raw.startswith("v") else raw
    if not PROJECTION_SEMVER_RE.fullmatch(candidate):
        raise ProjectionError(
            "version must be canonical SemVer MAJOR.MINOR.PATCH[-prerelease] "
            "with no leading v and no build metadata"
        )
    return candidate


def expected_tag(version: str) -> str:
    return f"v{version}"


def expected_public_url(tag: str) -> str:
    return f"https://github.com/{REPOSITORY}/releases/tag/{tag}"


# --- projection validation + canonical bytes ----------------------------------
def validate_projection(value: Any) -> dict[str, Any]:
    """Validate one projection object against the exact six-field v1 contract.

    Fail-closed on a non-object, missing/unknown fields, null/non-string values,
    or any field whose exact rule is not met. Returns a shallow copy.
    """
    if not isinstance(value, dict):
        raise ProjectionError("projection must be a JSON object")
    actual = set(value)
    if actual != PROJECTION_FIELDS:
        raise ProjectionError(
            "projection fields differ from contract "
            f"(missing={sorted(PROJECTION_FIELDS - actual)}, "
            f"unknown={sorted(actual - PROJECTION_FIELDS)})"
        )
    for field in PROJECTION_FIELDS:
        if not isinstance(value[field], str):
            raise ProjectionError(f"{field} must be a string (no null, number, or nesting)")

    public_fact_id = value["public_fact_id"]
    if not PUBLIC_FACT_ID_RE.fullmatch(public_fact_id):
        raise ProjectionError("public_fact_id must match ^rf_[0-9a-f]{64}$")

    if value["type"] != RELEASE_TYPE:
        raise ProjectionError(f"type must be exactly {RELEASE_TYPE!r}")

    validate_timestamp(value["occurred_at"], field="occurred_at")

    version = value["version"]
    if not PROJECTION_SEMVER_RE.fullmatch(version):
        raise ProjectionError(
            "version must be canonical SemVer without a leading v or build metadata"
        )
    tag = value["tag"]
    if tag != expected_tag(version):
        raise ProjectionError("tag must be exactly v<version>")
    # Single-source URL rule: reuse release_receipt's exact validator so the
    # publisher and this projection never diverge on the accepted release URL.
    # Re-raise its error as ProjectionError so this lib presents one error type.
    try:
        _rr._validate_public_url(value["public_url"], tag=tag)
    except _rr.ReleaseReceiptError as exc:
        raise ProjectionError(str(exc)) from exc
    if value["public_url"] != expected_public_url(tag):
        raise ProjectionError("public_url must be exactly the tag's GitHub release URL")

    return dict(value)


def canonical_projection_bytes(value: Any) -> bytes:
    """Return the exact canonical projection bytes (validated first)."""
    return canonical_json_bytes(validate_projection(value))


def projection_sha256(value: Any) -> str:
    """Return the lowercase-hex SHA-256 of the exact canonical projection bytes."""
    return sha256_bytes(canonical_projection_bytes(value))


def parse_projection_bytes(payload: bytes) -> dict[str, Any]:
    """Parse fetched projection bytes fail-closed, as a consumer would.

    Rejects non-UTF-8, non-finite numbers, duplicate keys, and any non-canonical
    encoding (whitespace, key order, CRLF, BOM, zero or multiple trailing LF),
    then validates the six-field schema. Returns the validated projection.
    """
    value = _rr._strict_json_loads(payload, name="projection")
    return validate_projection(value)


def project_release_fact(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct the six-field projection from one accepted release fact.

    Every non-projection field on the source fact is dropped; the source fact must
    carry the six projection fields (a fact lacking ``tag`` or ``public_url`` is
    ineligible for this transport even if those were optional in an earlier local
    bundle contract).
    """
    if not isinstance(fact, Mapping):
        raise ProjectionError("release fact must be a mapping")
    missing = [field for field in PROJECTION_FIELDS if field not in fact]
    if missing:
        raise ProjectionError(
            f"release fact is not projection-eligible (missing {sorted(missing)})"
        )
    return validate_projection({field: fact[field] for field in PROJECTION_FIELDS})


# --- receipt index -------------------------------------------------------------
def index_path_for(sha: str) -> str:
    if not isinstance(sha, str) or not SHA256_RE.fullmatch(sha):
        raise ProjectionError("projection_sha256 must be lowercase 64-hex")
    return f"receipts/releases/{sha}.json"


def build_receipt_index(projections: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the v1 ``receipt-index.json`` map from semantic fact ID to projection.

    Each projection is validated; the index binds only public path/hash/schema.
    Duplicate ``public_fact_id`` fails closed.
    """
    facts: dict[str, Any] = {}
    for projection in projections:
        validated = validate_projection(projection)
        sha = sha256_bytes(canonical_json_bytes(validated))
        public_fact_id = validated["public_fact_id"]
        if public_fact_id in facts:
            raise ProjectionError(f"duplicate public_fact_id {public_fact_id!r} in index")
        facts[public_fact_id] = {
            "path": index_path_for(sha),
            "projection_sha256": sha,
            "projection_schema": PROJECTION_SCHEMA,
        }
    return {"schema_version": INDEX_SCHEMA_VERSION, "facts": facts}


def validate_receipt_index(value: Any) -> dict[str, Any]:
    """Validate the index structure fail-closed (schema only, no byte cross-check)."""
    if not isinstance(value, dict):
        raise ProjectionError("receipt index must be a JSON object")
    if set(value) != INDEX_TOP_FIELDS:
        raise ProjectionError("receipt index top-level fields differ from contract")
    if value["schema_version"] != INDEX_SCHEMA_VERSION:
        raise ProjectionError(f"index schema_version must be {INDEX_SCHEMA_VERSION!r}")
    facts = value["facts"]
    if not isinstance(facts, dict):
        raise ProjectionError("index facts must be a JSON object")
    for public_fact_id, entry in facts.items():
        if not PUBLIC_FACT_ID_RE.fullmatch(public_fact_id):
            raise ProjectionError("index key must match ^rf_[0-9a-f]{64}$")
        if not isinstance(entry, dict) or set(entry) != INDEX_ENTRY_FIELDS:
            raise ProjectionError("index entry fields differ from contract")
        if entry["projection_schema"] != PROJECTION_SCHEMA:
            raise ProjectionError(f"index entry schema must be {PROJECTION_SCHEMA!r}")
        sha = entry["projection_sha256"]
        if not isinstance(sha, str) or not SHA256_RE.fullmatch(sha):
            raise ProjectionError("index entry projection_sha256 must be lowercase 64-hex")
        if entry["path"] != index_path_for(sha):
            raise ProjectionError("index entry path must be receipts/releases/<sha>.json")
    return dict(value)


def verify_index_against_projections(
    index: Mapping[str, Any], projection_bytes_by_path: Mapping[str, bytes]
) -> None:
    """Prove index/tree consistency: rehash the exact bytes and cross-check IDs.

    ``projection_bytes_by_path`` maps ``receipts/releases/<sha>.json`` to the exact
    fetched bytes. For every fact: rehashing the bytes must equal the entry's
    ``projection_sha256`` and the path hash; and the parsed projection's
    ``public_fact_id`` must equal the index key. Detects single-byte tampering.
    """
    validated_index = validate_receipt_index(index)
    for public_fact_id, entry in validated_index["facts"].items():
        path = entry["path"]
        if path not in projection_bytes_by_path:
            raise ProjectionError(f"index references missing projection {path!r}")
        payload = projection_bytes_by_path[path]
        actual_sha = sha256_bytes(payload)
        if actual_sha != entry["projection_sha256"]:
            raise ProjectionError(
                f"projection bytes at {path!r} hash to {actual_sha}, "
                f"index records {entry['projection_sha256']}"
            )
        if path != index_path_for(actual_sha):
            raise ProjectionError("index path does not content-address the projection")
        projection = parse_projection_bytes(payload)
        if projection["public_fact_id"] != public_fact_id:
            raise ProjectionError(
                "index key does not equal the projection's public_fact_id"
            )
