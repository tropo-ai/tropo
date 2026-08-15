"""Canonical verify-live public release receipts.

The receipt is a governance-authorized, hash-consistent publisher assertion
given trusted main checkout. It is tamper-evident within that repository's
write-access trust boundary; it is not cryptographic authentication and
deliberately carries no signature.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlsplit


SCHEMA_VERSION = "1.0.0"
RECEIPT_KIND = "verify-live-public-release"
PUBLISHER_TOOL_UID = "15cae798"
PUBLISHER_TOOL_SOURCE = "/tools/publish-release"
REPOSITORY = "tropo-ai/tropo"
RECEIPTS_RELATIVE_DIR = Path("vault") / "events" / "release-receipts"

RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_kind",
        "publisher_tool_uid",
        "publisher_tool_source",
        "repository",
        "version",
        "tag",
        "public_url",
        "published_at",
        "remote_main_sha",
        "remote_tag_sha",
        "release_object_tag",
        "release_object_url",
        "release_object_published_at",
        "release_object_is_draft",
        "verify_live_at",
    }
)

#: What a v2 receipt binds on top of v1 (Stage-6 preflight §5).
#:
#: A v1 receipt proves a release happened and says where. It cannot say WHICH
#: artefact, which release run authorised it, or which membership it shipped —
#: so it cannot be checked against anything after the fact. These fields make
#: the receipt self-verifying: the bytes are named by digest, the identity
#: chain is named by uid, and the public asset observations record what was
#: actually downloaded and hashed rather than what was uploaded.
V2_ADDED_FIELDS = frozenset(
    {
        "release_plan_uid",
        "release_entry_uid",
        "release_activation_uid",
        "release_pipeline_run_uid",
        "activation_root_uid",
        "fan_in_digest",
        "package_sha256",
        "public_asset_observations",
        "transaction_id",
    }
)
V2_RECEIPT_FIELDS = RECEIPT_FIELDS | V2_ADDED_FIELDS

#: v1 receipts stay readable forever; nothing new is written at v1.
SCHEMA_VERSION_V1 = "1.0.0"
SCHEMA_VERSION_V2 = "2.0.0"

_SEMVER_CORE = r"(?:0|[1-9][0-9]*)"
_SEMVER_IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER_RE = re.compile(
    rf"^{_SEMVER_CORE}\.{_SEMVER_CORE}\.{_SEMVER_CORE}"
    rf"(?:-{_SEMVER_IDENTIFIER}(?:\.{_SEMVER_IDENTIFIER})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)


class ReleaseReceiptError(ValueError):
    """A receipt or receipt directory violates the governed contract."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical UTF-8 JSON with one trailing LF."""
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ReleaseReceiptError(f"receipt is not canonical JSON data: {exc}") from exc
    return encoded.encode("utf-8") + b"\n"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_json_loads(payload: bytes, *, name: str) -> Any:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseReceiptError(f"{name} is not UTF-8") from exc

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseReceiptError(f"{name} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=no_duplicates,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ReleaseReceiptError(f"{name} contains non-finite number {constant}")
            ),
        )
    except ReleaseReceiptError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ReleaseReceiptError(f"{name} is not valid JSON") from exc
    if canonical_json_bytes(value) != payload:
        raise ReleaseReceiptError(f"{name} is not canonical JSON+LF")
    return value


def _validate_timestamp(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
        raise ReleaseReceiptError(
            f"{field} must be canonical UTC YYYY-MM-DDTHH:MM:SSZ"
        )
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise ReleaseReceiptError(f"{field} is not a real UTC timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ReleaseReceiptError(f"{field} is not canonical UTC")
    return value


def validate_timestamp(value: Any, *, field: str = "timestamp") -> str:
    """Validate one canonical UTC receipt timestamp."""
    return _validate_timestamp(value, field=field)


def _validate_public_url(value: Any, *, tag: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseReceiptError("public_url must be a non-empty HTTPS URL")
    if (
        value != value.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        or any(character.isspace() for character in value)
    ):
        raise ReleaseReceiptError("public_url contains whitespace or control characters")
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError as exc:
        raise ReleaseReceiptError("public_url is malformed") from exc
    expected_path = f"/{REPOSITORY}/releases/tag/{tag}"
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed_port is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != expected_path
        or "//" in parsed.path
        or "%" in parsed.path
        or any(part in {".", ".."} for part in PurePosixPath(parsed.path).parts)
        or value != f"https://github.com{expected_path}"
    ):
        raise ReleaseReceiptError(
            "public_url must exactly identify the receipt's tropo-ai/tropo tag"
        )
    return value


def validate_release_receipt(value: Any) -> dict[str, Any]:
    """Validate and return one exact-schema receipt without adding fields."""
    if not isinstance(value, dict):
        raise ReleaseReceiptError("release receipt must be a JSON object")
    actual_fields = set(value)
    if actual_fields != RECEIPT_FIELDS:
        raise ReleaseReceiptError(
            "release receipt fields differ from contract "
            f"(missing={sorted(RECEIPT_FIELDS - actual_fields)}, "
            f"unknown={sorted(actual_fields - RECEIPT_FIELDS)})"
        )
    constants = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": RECEIPT_KIND,
        "publisher_tool_uid": PUBLISHER_TOOL_UID,
        "publisher_tool_source": PUBLISHER_TOOL_SOURCE,
        "repository": REPOSITORY,
    }
    for field, expected in constants.items():
        if value[field] != expected or not isinstance(value[field], str):
            raise ReleaseReceiptError(f"{field} must equal {expected!r}")

    version = value["version"]
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        raise ReleaseReceiptError("version must be normalized SemVer without a v prefix")
    tag = value["tag"]
    if not isinstance(tag, str) or tag != f"v{version}":
        raise ReleaseReceiptError("tag must be exactly v<version>")
    _validate_public_url(value["public_url"], tag=tag)

    remote_main_sha = value["remote_main_sha"]
    remote_tag_sha = value["remote_tag_sha"]
    for field, sha in (
        ("remote_main_sha", remote_main_sha),
        ("remote_tag_sha", remote_tag_sha),
    ):
        if not isinstance(sha, str) or not SHA1_RE.fullmatch(sha):
            raise ReleaseReceiptError(f"{field} must be exact lowercase 40-hex")
    if remote_tag_sha != remote_main_sha:
        raise ReleaseReceiptError(
            "remote_tag_sha must equal remote_main_sha"
        )

    if value["release_object_tag"] != tag:
        raise ReleaseReceiptError("release_object_tag must equal tag")
    release_object_url = _validate_public_url(
        value["release_object_url"], tag=tag
    )
    if release_object_url != value["public_url"]:
        raise ReleaseReceiptError("release_object_url must equal public_url")
    if value["release_object_is_draft"] is not False:
        raise ReleaseReceiptError(
            "release_object_is_draft must be the JSON boolean false"
        )
    published_at = _validate_timestamp(value["published_at"], field="published_at")
    release_published_at = _validate_timestamp(
        value["release_object_published_at"],
        field="release_object_published_at",
    )
    if release_published_at != published_at:
        raise ReleaseReceiptError(
            "release_object_published_at must equal published_at"
        )
    verify_live_at = _validate_timestamp(value["verify_live_at"], field="verify_live_at")
    if verify_live_at < published_at:
        raise ReleaseReceiptError("verify_live_at cannot precede published_at")
    return dict(value)


def make_release_receipt(
    *,
    version: str,
    tag: str,
    public_url: str,
    remote_main_sha: str,
    remote_tag_sha: str,
    release_object_tag: str,
    release_object_url: str,
    release_object_published_at: str,
    release_object_is_draft: bool,
    published_at: str,
    verify_live_at: str,
) -> dict[str, Any]:
    """Construct and validate the one governed receipt shape."""
    return validate_release_receipt(
        {
            "schema_version": SCHEMA_VERSION,
            "receipt_kind": RECEIPT_KIND,
            "publisher_tool_uid": PUBLISHER_TOOL_UID,
            "publisher_tool_source": PUBLISHER_TOOL_SOURCE,
            "repository": REPOSITORY,
            "version": version,
            "tag": tag,
            "public_url": public_url,
            "published_at": published_at,
            "remote_main_sha": remote_main_sha,
            "remote_tag_sha": remote_tag_sha,
            "release_object_tag": release_object_tag,
            "release_object_url": release_object_url,
            "release_object_published_at": release_object_published_at,
            "release_object_is_draft": release_object_is_draft,
            "verify_live_at": verify_live_at,
        }
    )


def receipt_sha256(receipt: Mapping[str, Any]) -> str:
    validated = validate_release_receipt(dict(receipt))
    return sha256_bytes(canonical_json_bytes(validated))


def _receipt_directory(vault_root: Path, *, create: bool) -> Path:
    root = Path(
        os.path.abspath(os.path.expanduser(str(Path(vault_root))))
    )
    try:
        resolved_root = root.resolve(strict=True)
        root_metadata = root.lstat()
    except OSError as exc:
        raise ReleaseReceiptError("vault root must be a real directory") from exc
    if (
        resolved_root != root
        or root.is_symlink()
        or not stat.S_ISDIR(root_metadata.st_mode)
    ):
        raise ReleaseReceiptError(
            "vault root and receipt directory cannot use filesystem aliases"
        )
    current = root
    for part in RECEIPTS_RELATIVE_DIR.parts:
        current = current / part
        if not current.exists() and not current.is_symlink():
            if not create:
                return root / RECEIPTS_RELATIVE_DIR
            try:
                current.mkdir(mode=0o755)
            except FileExistsError:
                pass
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise ReleaseReceiptError("release receipt directory is unreadable") from exc
        if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise ReleaseReceiptError(
                "release receipt directory and parents must be real directories"
            )
    return current


def load_release_receipts(vault_root: Path) -> dict[str, dict[str, Any]]:
    """Load all receipts once as ``sha256 -> validated receipt``.

    Any malformed committed entry, wrong content-addressed filename, or
    duplicate version with differing hashes invalidates the complete set.
    """
    directory = _receipt_directory(Path(vault_root), create=False)
    if not directory.exists() and not directory.is_symlink():
        return {}
    if directory.is_symlink() or not directory.is_dir():
        raise ReleaseReceiptError("release receipt path must be a real directory")

    by_sha: dict[str, dict[str, Any]] = {}
    by_version: dict[str, str] = {}
    try:
        entries = sorted(directory.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise ReleaseReceiptError("release receipt directory is unreadable") from exc
    for path in entries:
        match = re.fullmatch(r"([0-9a-f]{64})\.json", path.name)
        if match is None:
            raise ReleaseReceiptError(
                f"release receipt has a non-content-addressed filename: {path.name}"
            )
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise ReleaseReceiptError(f"could not inspect receipt {path.name}") from exc
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            raise ReleaseReceiptError(
                f"receipt {path.name} must be one unlinked regular file"
            )
        try:
            descriptor = os.open(
                path,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
            )
            with os.fdopen(descriptor, "rb") as handle:
                opened = os.fstat(handle.fileno())
                if (
                    (opened.st_dev, opened.st_ino)
                    != (metadata.st_dev, metadata.st_ino)
                    or not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                ):
                    raise ReleaseReceiptError(
                        f"receipt changed before read: {path.name}"
                    )
                payload = handle.read()
                after_open = os.fstat(handle.fileno())
            after_path = path.lstat()
        except ReleaseReceiptError:
            raise
        except OSError as exc:
            raise ReleaseReceiptError(
                f"could not safely read receipt {path.name}"
            ) from exc
        metadata_tuple = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )
        if (
            metadata_tuple
            != (
                after_open.st_dev,
                after_open.st_ino,
                after_open.st_size,
                after_open.st_mtime_ns,
                after_open.st_ctime_ns,
            )
            or metadata_tuple
            != (
                after_path.st_dev,
                after_path.st_ino,
                after_path.st_size,
                after_path.st_mtime_ns,
                after_path.st_ctime_ns,
            )
            or after_open.st_nlink != 1
            or after_path.st_nlink != 1
            or not stat.S_ISREG(after_path.st_mode)
            or len(payload) != after_open.st_size
        ):
            raise ReleaseReceiptError(
                f"receipt changed or became linked while being read: {path.name}"
            )
        expected_sha = match.group(1)
        actual_sha = sha256_bytes(payload)
        if actual_sha != expected_sha:
            raise ReleaseReceiptError(
                f"receipt filename hash does not match exact bytes: {path.name}"
            )
        value = _strict_json_loads(payload, name=path.name)
        receipt = validate_any_release_receipt(value)
        prior_sha = by_version.get(receipt["version"])
        if prior_sha is not None and prior_sha != expected_sha:
            raise ReleaseReceiptError(
                f"release receipt version conflict for {receipt['version']}"
            )
        by_version[receipt["version"]] = expected_sha
        by_sha[expected_sha] = receipt
    return by_sha


def validate_receipt_mapping(
    receipts: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Defensively validate an already-loaded receipt map without filesystem I/O."""
    if not isinstance(receipts, Mapping):
        raise ReleaseReceiptError("release receipts must be a SHA-to-receipt mapping")
    normalized: dict[str, dict[str, Any]] = {}
    versions: dict[str, str] = {}
    for digest, value in receipts.items():
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ReleaseReceiptError("release receipt mapping key must be lowercase sha256")
        if not isinstance(value, Mapping):
            raise ReleaseReceiptError("release receipt mapping value must be an object")
        receipt = validate_release_receipt(dict(value))
        actual = sha256_bytes(canonical_json_bytes(receipt))
        if actual != digest:
            raise ReleaseReceiptError("release receipt mapping hash does not re-derive")
        prior = versions.get(receipt["version"])
        if prior is not None and prior != digest:
            raise ReleaseReceiptError(
                f"release receipt version conflict for {receipt['version']}"
            )
        versions[receipt["version"]] = digest
        normalized[digest] = receipt
    return normalized


def _recover_writer_temporaries(directory: Path) -> None:
    """Recover only this writer's strict crash-temporary namespace."""
    temporary_re = re.compile(
        r"\.([0-9a-f]{64})\.([0-9]+)\.([0-9a-f]{16})\.tmp"
    )
    changed = False
    for temporary in sorted(directory.glob(".*.tmp")):
        match = temporary_re.fullmatch(temporary.name)
        if match is None:
            continue
        try:
            metadata = temporary.lstat()
        except OSError as exc:
            raise ReleaseReceiptError(
                "could not inspect a crashed receipt temporary"
            ) from exc
        if (
            temporary.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink not in {1, 2}
        ):
            raise ReleaseReceiptError(
                "crashed receipt temporary is not safely recoverable"
            )
        if metadata.st_nlink == 2:
            target = directory / f"{match.group(1)}.json"
            try:
                target_metadata = target.lstat()
            except OSError as exc:
                raise ReleaseReceiptError(
                    "linked receipt temporary has no committed target"
                ) from exc
            if (
                target.is_symlink()
                or not stat.S_ISREG(target_metadata.st_mode)
                or (target_metadata.st_dev, target_metadata.st_ino)
                != (metadata.st_dev, metadata.st_ino)
            ):
                raise ReleaseReceiptError(
                    "linked receipt temporary target is ambiguous"
                )
        try:
            temporary.unlink()
        except OSError as exc:
            raise ReleaseReceiptError(
                "could not recover a crashed receipt temporary"
            ) from exc
        changed = True
    if changed:
        directory_fd = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def write_release_receipt(
    vault_root: Path, receipt: Mapping[str, Any]
) -> str:
    """Atomically and idempotently commit one content-addressed receipt.

    Identical bytes are a harmless no-op.  Existing invalid receipts or a
    different receipt for the same release version refuse without replacement.
    """
    validated = validate_any_release_receipt(dict(receipt))
    payload = canonical_json_bytes(validated)
    digest = sha256_bytes(payload)
    directory = _receipt_directory(Path(vault_root), create=True)
    directory_fd = os.open(
        directory,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary_name = f".{digest}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    temporary_path = directory / temporary_name
    target_path = directory / f"{digest}.json"
    try:
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        _recover_writer_temporaries(directory)
        existing = load_release_receipts(Path(vault_root))
        if digest in existing:
            return digest
        for existing_sha, existing_receipt in existing.items():
            if (
                existing_receipt["version"] == validated["version"]
                and existing_sha != digest
            ):
                raise ReleaseReceiptError(
                    f"release receipt version conflict for {validated['version']}"
                )

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary_path, flags, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, target_path, follow_symlinks=False)
        except FileExistsError:
            try:
                existing_payload = target_path.read_bytes()
            except OSError as exc:
                raise ReleaseReceiptError(
                    "existing receipt could not be checked for idempotency"
                ) from exc
            if existing_payload != payload:
                raise ReleaseReceiptError(
                    "content-addressed receipt path contains conflicting bytes"
                )
        os.unlink(temporary_path)
        os.fsync(directory_fd)

        committed = load_release_receipts(Path(vault_root))
        if committed.get(digest) != validated:
            raise ReleaseReceiptError("committed receipt did not re-load exactly")
        return digest
    except OSError as exc:
        raise ReleaseReceiptError(f"could not atomically write release receipt: {exc}") from exc
    finally:
        try:
            if temporary_path.exists() or temporary_path.is_symlink():
                temporary_path.unlink()
        except OSError:
            pass
        try:
            fcntl.flock(directory_fd, fcntl.LOCK_UN)
        finally:
            os.close(directory_fd)


def _validate_asset_url(value: Any) -> str:
    """A downloadable asset location: HTTPS, clean, no embedded credentials.

    Deliberately looser than `_validate_public_url` about WHERE, because the
    canonical GitHub asset and the Supabase mirror live on different hosts,
    and deliberately just as strict about SHAPE, because a URL carrying
    credentials or whitespace in a governed receipt is a different problem
    than a wrong host.
    """
    if not isinstance(value, str) or not value:
        raise ReleaseReceiptError("asset url must be a non-empty HTTPS URL")
    if (
        value != value.strip()
        or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value)
        or any(c.isspace() for c in value)
    ):
        raise ReleaseReceiptError("asset url contains whitespace or control characters")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ReleaseReceiptError("asset url is malformed") from exc
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
    ):
        raise ReleaseReceiptError(f"asset url {value!r} is not a clean HTTPS location")
    return value


def validate_release_receipt_v2(value: Any) -> dict[str, Any]:
    """Validate a v2 receipt: the v1 contract plus the identity chain.

    The v1 shape is reused wholesale rather than restated, so the two cannot
    drift on the fields they share. What v2 adds is the ability to check a
    receipt against the world afterwards: a digest for the bytes, uids for the
    chain that authorised them, and observations of what was actually
    downloaded from each public location.
    """
    if not isinstance(value, dict):
        raise ReleaseReceiptError("release receipt must be a JSON object")
    actual = set(value)
    if actual != V2_RECEIPT_FIELDS:
        raise ReleaseReceiptError(
            "v2 release receipt fields differ from contract "
            f"(missing={sorted(V2_RECEIPT_FIELDS - actual)}, "
            f"unknown={sorted(actual - V2_RECEIPT_FIELDS)})"
        )
    if value.get("schema_version") != SCHEMA_VERSION_V2:
        raise ReleaseReceiptError(
            f"schema_version must equal {SCHEMA_VERSION_V2!r} for a v2 receipt"
        )

    core = {k: v for k, v in value.items() if k in RECEIPT_FIELDS}
    core["schema_version"] = SCHEMA_VERSION
    validate_release_receipt(core)

    for field in ("release_plan_uid", "release_entry_uid",
                  "release_activation_uid", "release_pipeline_run_uid",
                  "activation_root_uid"):
        uid = value[field]
        if not isinstance(uid, str) or not re.fullmatch(r"[0-9a-f]{8}", uid):
            raise ReleaseReceiptError(f"{field} must be a governed uid")

    for field in ("package_sha256", "fan_in_digest"):
        digest = value[field]
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ReleaseReceiptError(f"{field} must be a sha-256 hex digest")

    if not isinstance(value["transaction_id"], str) or not value["transaction_id"]:
        raise ReleaseReceiptError("transaction_id must be a non-empty string")

    observations = value["public_asset_observations"]
    if not isinstance(observations, list) or not observations:
        raise ReleaseReceiptError(
            "public_asset_observations must list at least one downloaded "
            "asset; a receipt that records no observation is recording an "
            "upload, not a verification"
        )
    for entry in observations:
        if not isinstance(entry, dict) or set(entry) != {"url", "observed_sha256"}:
            raise ReleaseReceiptError(
                "each public asset observation must be {url, observed_sha256}"
            )
        # NOT _validate_public_url: that one requires the GitHub tag PAGE for
        # this exact tag. An asset observation is a download URL, and the
        # Supabase mirror is not on github.com at all, so reusing it here
        # would refuse every valid mirror observation.
        _validate_asset_url(entry["url"])
        if not SHA256_RE.fullmatch(str(entry["observed_sha256"])):
            raise ReleaseReceiptError("observed_sha256 must be a sha-256 hex digest")
        if entry["observed_sha256"] != value["package_sha256"]:
            raise ReleaseReceiptError(
                f"public asset at {entry['url']} hashed to "
                f"{str(entry['observed_sha256'])[:12]} but the package is "
                f"{value['package_sha256'][:12]}. Silent divergence between "
                f"what shipped and what is downloadable is not allowed: the "
                f"canonical asset and every mirror must be the same bytes."
            )
    return dict(value)


def validate_any_release_receipt(value: Any) -> dict[str, Any]:
    """Validate a receipt at whichever schema it declares.

    The store validated v1 only, so a v2 receipt could be BUILT by the
    publisher and then neither written nor read back — the writer refused it
    and the loader refused it, and closure would never find the receipt it was
    closing against. Surfaced by driving the real happy path, which is the
    thing that catches an integration seam nobody wired.

    Dispatches rather than loosening: each schema is still validated in full.
    """
    if isinstance(value, dict) and value.get("schema_version") == SCHEMA_VERSION_V2:
        return validate_release_receipt_v2(value)
    return validate_release_receipt(value)


def assert_v2_authority(receipt: Any, *, purpose: str) -> dict[str, Any]:
    """A v1 receipt is history, never authority for a v2 release.

    A148's Q4 answer, implemented as the distinction it draws. Historical v1
    receipts remain readable and remain valid evidence that a v1 publication
    happened. They are never acceptable authority for a v2 release run, a
    package gate, or closure — and the refusal names the missing digest rather
    than treating its absence as satisfaction. This is read compatibility, not
    an operational fallback, so no new v1 publication is licensed by it.
    """
    if not isinstance(receipt, dict):
        raise ReleaseReceiptError("release receipt must be a JSON object")
    schema = receipt.get("schema_version")
    if schema == SCHEMA_VERSION_V2:
        return validate_release_receipt_v2(receipt)
    if schema == SCHEMA_VERSION_V1:
        raise ReleaseReceiptError(
            f"this is a v1 receipt and cannot authorise {purpose}: it carries "
            f"no package_sha256, so nothing binds it to the artefact that "
            f"shipped. It remains valid evidence of the v1 publication it "
            f"records."
        )
    raise ReleaseReceiptError(
        f"unrecognised receipt schema_version {schema!r}; refusing to treat an "
        f"unknown shape as authority for {purpose}"
    )


# Short aliases keep call sites readable without weakening the explicit API.
load_receipts = load_release_receipts
write_receipt = write_release_receipt

