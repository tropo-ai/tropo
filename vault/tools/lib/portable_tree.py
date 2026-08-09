"""Pure Contract-C0 structural portability: paths, trees, and safe ZIP.

This module owns the *structural* half of the C0 portability profile
(dev-spec ``372ffdda`` §Portability profile, §Safe ZIP, and the human-tree
hash in §Canonical bytes and hashes):

- canonical payload-path validation to the locked limits and path algebra;
- the ``lstat``/descriptor-relative payload tree scan that refuses symlinks,
  hardlinks, devices, sockets, FIFOs, mount escapes, and unknown kinds;
- the exact raw-path-byte-sorted human-tree SHA-256;
- a deterministic canonical STORED ZIP packer; and
- a complete central-directory + local-header ZIP unpack preflight that stages
  to an absent sibling directory and refuses hostile archives without ever
  leaving a partial destination.

CRITICAL — the Unicode collision key is DEPENDENCY-INJECTED, never implemented
here.  The dev-spec pins the portability key of a segment to
``NFKC(segment).casefold().rstrip(" .")`` computed against a *hash-pinned
Unicode 15.1 table* — a table this development environment does not carry
(system ``unicodedata`` is 15.0 and ``unicodedata2`` is 17.0).  Fabricating a
"15.1" table from either ambient database would ship mislabeled data, so this
module takes a :class:`NormalizationTable` (an injected ``(segment) -> key``
callable) as a REQUIRED parameter everywhere a portability key is derived.  It
never imports ``unicodedata``/``unicodedata2`` and bakes in no normalization
data of its own.

The house refusal vocabulary is reused verbatim from :mod:`folder_sidecar`
(``C0Refusal``/``C0ValidationError``/``C0Finding`` and the shared ``C0_*``
codes).  Only the ZIP-specific and structural codes named in the dev-spec's
refusal vocabulary that :mod:`folder_sidecar` does not already define are added
here; no parallel vocabulary is invented.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import stat as stat_module
import struct
import tempfile
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol, runtime_checkable

try:  # package-relative first, then flat sys.path (mirrors folder_sidecar)
    from . import folder_sidecar as _fs
except ImportError:  # pragma: no cover - exercised via flat sys.path in tests
    import folder_sidecar as _fs  # type: ignore

# Reuse — never redefine — the house exception hierarchy and shared codes.
C0Refusal = _fs.C0Refusal
C0ValidationError = _fs.C0ValidationError
C0Finding = _fs.C0Finding
PayloadEntry = _fs.PayloadEntry
payload_sha256 = _fs.payload_sha256

C0_SCHEMA_INVALID: Final = _fs.C0_SCHEMA_INVALID
C0_PATH_INVALID: Final = _fs.C0_PATH_INVALID
C0_PORTABILITY_COLLISION: Final = _fs.C0_PORTABILITY_COLLISION
C0_SPECIAL_FILE: Final = _fs.C0_SPECIAL_FILE
C0_HARDLINK: Final = _fs.C0_HARDLINK
C0_DIRECTORY_MISSING: Final = _fs.C0_DIRECTORY_MISSING
C0_HASH_MISMATCH: Final = _fs.C0_HASH_MISMATCH
C0_DUPLICATE_PATH: Final = _fs.C0_DUPLICATE_PATH

# Structural / ZIP codes from the dev-spec §Stable refusal vocabulary that the
# codec module does not define.  Added here, not invented — every name below is
# quoted verbatim from 372ffdda.
C0_PATH_TOO_LONG: Final = "C0_PATH_TOO_LONG"
C0_RESERVED_NAMESPACE: Final = "C0_RESERVED_NAMESPACE"
C0_DESTINATION_NOT_EMPTY: Final = "C0_DESTINATION_NOT_EMPTY"
C0_ZIP_TRAVERSAL: Final = "C0_ZIP_TRAVERSAL"
C0_ZIP_ABSOLUTE: Final = "C0_ZIP_ABSOLUTE"
C0_ZIP_DRIVE_PREFIX: Final = "C0_ZIP_DRIVE_PREFIX"
C0_ZIP_DUPLICATE: Final = "C0_ZIP_DUPLICATE"
C0_ZIP_ENCRYPTED: Final = "C0_ZIP_ENCRYPTED"
C0_ZIP_UNSUPPORTED: Final = "C0_ZIP_UNSUPPORTED"
C0_ZIP_SPECIAL_FILE: Final = "C0_ZIP_SPECIAL_FILE"
C0_ZIP_LIMIT_COUNT: Final = "C0_ZIP_LIMIT_COUNT"
C0_ZIP_LIMIT_SIZE: Final = "C0_ZIP_LIMIT_SIZE"
C0_ZIP_LIMIT_RATIO: Final = "C0_ZIP_LIMIT_RATIO"


# ---------------------------------------------------------------------------
# Locked limits (dev-spec §Portability profile → Limits, §Safe ZIP).
# ---------------------------------------------------------------------------
MAX_COMPONENT_BYTES: Final = 255
MAX_PATH_BYTES: Final = 1024
MAX_COMPONENTS: Final = 64
MAX_PAYLOAD_FILES: Final = 10_000
MAX_PAYLOAD_DIRECTORIES: Final = 10_000
MAX_ZIP_ENTRIES: Final = 40_032
MAX_TOTAL_EXPANDED_BYTES: Final = 2 * 1024 * 1024 * 1024  # 2 GiB
MAX_ENTRY_EXPANDED_BYTES: Final = 512 * 1024 * 1024  # 512 MiB
MAX_COMPRESSION_RATIO: Final = 100  # 100:1, per entry and per archive

# Reserved payload components and Windows hazards (dev-spec path rule 6).
RESERVED_PATH_COMPONENTS: Final[frozenset[str]] = frozenset(
    {".git", ".tropo", ".tropo-studio"}
)
WINDOWS_FORBIDDEN_CHARS: Final[frozenset[str]] = frozenset('<>:"|?*')
_WINDOWS_DEVICE_STEMS: Final[frozenset[str]] = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_DRIVE_PREFIX_RE: Final = re.compile(r"^[A-Za-z]:")

# Canonical STORED-pack fixed metadata (dev-spec §Safe ZIP → Canonical pack).
_DOS_DATE_1980_01_01: Final = 0x0021  # ((1980-1980) << 9) | (1 << 5) | 1
_DOS_TIME_MIDNIGHT: Final = 0x0000
_FILE_MODE: Final = 0o100644
_DIR_MODE: Final = 0o040755
_UNIX_MADE_BY: Final = (3 << 8) | 20  # host=Unix, spec version 2.0
_VERSION_NEEDED: Final = 20
_GPF_UTF8: Final = 0x0800  # general-purpose bit 11 (UTF-8 name)
_GPF_ENCRYPTED: Final = 0x0001  # bit 0 (traditional encryption)
_GPF_STRONG_ENCRYPTION: Final = 0x0040  # bit 6 (strong encryption)
_GPF_DATA_DESCRIPTOR: Final = 0x0008  # bit 3 (sizes deferred to descriptor)
_METHOD_STORED: Final = 0
_METHOD_DEFLATE: Final = 8

STAGING_PREFIX: Final = ".c0-unpack-staging-"

_SIG_LOCAL: Final = b"PK\x03\x04"
_SIG_CENTRAL: Final = b"PK\x01\x02"
_SIG_EOCD: Final = b"PK\x05\x06"
_SIG_ZIP64_EOCD: Final = b"PK\x06\x06"
_SIG_ZIP64_LOCATOR: Final = b"PK\x06\x07"
_ZIP64_SENTINEL_16: Final = 0xFFFF
_ZIP64_SENTINEL_32: Final = 0xFFFFFFFF


@runtime_checkable
class NormalizationTable(Protocol):
    """Injected Unicode-version-pinned single-segment normalizer.

    An implementation maps one raw path segment to its portability key,
    exactly ``NFKC(segment).casefold().rstrip(" .")`` under the pinned Unicode
    15.1 tables.  It is the ONLY place Unicode normalization/casefold data
    enters C0; this module supplies none.  Callers pass either an object
    implementing this protocol or a bare ``(str) -> str`` callable.
    """

    def normalize_segment(self, segment: str, /) -> str:
        ...


def _apply_normalizer(normalizer: object, segment: str) -> str:
    """Call an injected normalizer (protocol object or bare callable)."""

    if normalizer is None:
        raise C0ValidationError(
            C0_SCHEMA_INVALID,
            "a pinned Unicode 15.1 NormalizationTable must be injected; this "
            "module fabricates no normalization data",
        )
    method = getattr(normalizer, "normalize_segment", None)
    try:
        if callable(method):
            result = method(segment)
        elif callable(normalizer):
            result = normalizer(segment)
        else:
            raise TypeError("normalizer is neither a NormalizationTable nor callable")
    except C0Refusal:
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed on any table error
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"injected normalizer failed on segment {segment!r}: {exc}",
            path=segment,
        ) from exc
    if not isinstance(result, str):
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"injected normalizer returned {type(result).__name__} for {segment!r}",
            path=segment,
        )
    return result


def _contains_control(value: str) -> bool:
    return any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in value)


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8", errors="strict"))


def _device_stem(segment: str) -> str:
    return segment.split(".", 1)[0].upper()


# ---------------------------------------------------------------------------
# Canonical payload-path validation and portability-key derivation.
# ---------------------------------------------------------------------------
def _validate_normalized_segment(raw: str, key: str) -> str:
    """Apply dev-spec path rule 5 to a normalizer's output for one segment."""

    if key == "":
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"normalization of segment {raw!r} produced an empty component",
            path=raw,
        )
    if "/" in key or "\\" in key:
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"normalization of segment {raw!r} introduced a separator",
            path=raw,
        )
    if key in (".", ".."):
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"normalization of segment {raw!r} produced a dot component",
            path=raw,
        )
    if _contains_control(key):
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"normalization of segment {raw!r} produced a control character",
            path=raw,
        )
    if key in RESERVED_PATH_COMPONENTS:
        raise C0ValidationError(
            C0_RESERVED_NAMESPACE,
            f"normalization of segment {raw!r} produced reserved component {key!r}",
            path=raw,
        )
    return key


def _validate_raw_segment(segment: str, path: str) -> None:
    """Enforce the raw (pre-normalization) component grammar (rules 1 and 6)."""

    if segment == "":
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload path has an empty or repeated separator",
            path=path,
        )
    if segment in (".", ".."):
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"payload path contains a {segment!r} segment",
            path=path,
        )
    if _utf8_len(segment) > MAX_COMPONENT_BYTES:
        raise C0ValidationError(
            C0_PATH_TOO_LONG,
            f"component {segment!r} exceeds {MAX_COMPONENT_BYTES} UTF-8 bytes",
            path=path,
        )
    if segment in RESERVED_PATH_COMPONENTS:
        raise C0ValidationError(
            C0_RESERVED_NAMESPACE,
            f"payload path uses reserved component {segment!r}",
            path=path,
        )
    if "\\" in segment:
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload path component contains a backslash",
            path=path,
        )
    bad = sorted(WINDOWS_FORBIDDEN_CHARS.intersection(segment))
    if bad:
        raise C0ValidationError(
            C0_PATH_INVALID,
            f"component {segment!r} contains Windows-forbidden character(s) {bad}",
            path=path,
        )
    if _device_stem(segment) in _WINDOWS_DEVICE_STEMS:
        raise C0ValidationError(
            C0_RESERVED_NAMESPACE,
            f"component {segment!r} is a reserved Windows device name",
            path=path,
        )


def derive_portability_key(
    path: str,
    normalizer: object,
    *,
    is_root: bool = False,
) -> str:
    """Validate one payload path and return its ``payload_portability_key``.

    ``path`` is the raw, filesystem-spelled path relative to ``payload_root``
    using POSIX ``/`` separators.  The returned key is
    ``"/".join(normalizer(segment) for segment in path.split("/"))`` after the
    full path algebra and limits have been enforced.  Only the payload root may
    use ``is_root=True`` with an empty path.
    """

    if not isinstance(path, str):
        raise C0ValidationError(C0_PATH_INVALID, "payload path must be a string")
    if is_root:
        if path != "":
            raise C0ValidationError(
                C0_PATH_INVALID,
                "the payload root must use the empty payload path",
                path=path,
            )
        return ""
    if path == "":
        raise C0ValidationError(
            C0_PATH_INVALID,
            "only the payload root may use the empty payload path",
        )
    try:
        path.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload path is not strict UTF-8 (lone surrogate)",
            path=path,
        ) from exc
    if _utf8_len(path) > MAX_PATH_BYTES:
        raise C0ValidationError(
            C0_PATH_TOO_LONG,
            f"payload path exceeds {MAX_PATH_BYTES} UTF-8 bytes",
            path=path,
        )
    if _contains_control(path):
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload path contains a NUL or control character",
            path=path,
        )
    if path.startswith("/"):
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload path must be payload-root-relative (no leading slash)",
            path=path,
        )
    if "\\" in path:
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload path may not contain a backslash (no UNC/Windows separator)",
            path=path,
        )
    if _DRIVE_PREFIX_RE.match(path):
        raise C0ValidationError(
            C0_PATH_INVALID,
            "payload path may not carry a drive-letter prefix",
            path=path,
        )
    segments = path.split("/")
    if len(segments) > MAX_COMPONENTS:
        raise C0ValidationError(
            C0_PATH_TOO_LONG,
            f"payload path has {len(segments)} components (> {MAX_COMPONENTS})",
            path=path,
        )
    key_parts: list[str] = []
    for segment in segments:
        _validate_raw_segment(segment, path)
        normalized = _apply_normalizer(normalizer, segment)
        key_parts.append(_validate_normalized_segment(segment, normalized))
    return "/".join(key_parts)


def make_portability_key(normalizer: object):
    """Adapt an injected normalizer into a ``folder_sidecar.PortabilityKey``.

    The returned ``(payload_path, is_root) -> key`` callable can be handed to
    :func:`folder_sidecar.scan_payload_inventory` and the codec's portability
    validator so a single normalization authority governs the whole stack.
    """

    def _key(payload_path: str, is_root: bool, /) -> str:
        return derive_portability_key(payload_path, normalizer, is_root=is_root)

    return _key


def portability_validator(normalizer: object):
    """Adapt an injected normalizer into a ``PortabilityValidator``.

    Returns a ``(path, declared_key, is_root) -> expected_key`` callable so the
    codec can confirm a record's stored key against the pinned tables.
    """

    def _validate(payload_path: str, declared_key: str, is_root: bool, /) -> str:
        return derive_portability_key(payload_path, normalizer, is_root=is_root)

    return _validate


# ---------------------------------------------------------------------------
# Exact human-tree hash (dev-spec §Canonical bytes and hashes).
# ---------------------------------------------------------------------------
def _tree_entry_fields(entry: object) -> tuple[str, bytes, str | None]:
    """Coerce a payload entry into ``(kind, raw_path_bytes, sha256|None)``."""

    if isinstance(entry, PayloadEntry):
        return entry.record_kind, bytes(entry.payload_path_bytes), entry.payload_sha256
    kind = getattr(entry, "record_kind", None)
    path_bytes = getattr(entry, "payload_path_bytes", None)
    sha = getattr(entry, "payload_sha256", None)
    if kind is not None and path_bytes is not None:
        return str(kind), bytes(path_bytes), sha
    if isinstance(entry, Sequence) and not isinstance(entry, (str, bytes, bytearray)):
        if len(entry) == 3:
            kind, raw, sha = entry
        elif len(entry) == 2:
            kind, raw = entry
            sha = None
        else:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                "tree entry tuple must be (kind, path, sha256?)",
            )
        raw_bytes = raw if isinstance(raw, (bytes, bytearray)) else str(raw).encode(
            "utf-8", errors="strict"
        )
        return str(kind), bytes(raw_bytes), sha
    raise C0ValidationError(
        C0_SCHEMA_INVALID,
        f"unsupported human-tree entry {type(entry).__name__}",
    )


def _first_component(raw_path_bytes: bytes) -> bytes:
    return raw_path_bytes.split(b"/", 1)[0]


_EXCLUDED_TOP_LEVEL: Final[frozenset[bytes]] = frozenset(
    name.encode("utf-8") for name in (".git", ".tropo", ".tropo-studio")
)


def human_tree_line(entry: object) -> bytes | None:
    """Return the exact human-tree line for one entry, or ``None`` if excluded."""

    kind, raw_path_bytes, sha = _tree_entry_fields(entry)
    if _first_component(raw_path_bytes) in _EXCLUDED_TOP_LEVEL:
        return None  # Tropo metadata and .git are excluded from the tree hash.
    encoded = base64.b64encode(raw_path_bytes)  # canonical padded RFC 4648
    if kind == "file":
        if not isinstance(sha, str) or _fs.HASH_RE.fullmatch(sha) is None:
            raise C0ValidationError(
                C0_HASH_MISMATCH,
                "file tree entry requires a lowercase SHA-256",
                path=raw_path_bytes.decode("utf-8", errors="backslashreplace"),
            )
        return b"F\x00" + encoded + b"\x00" + sha.encode("ascii") + b"\n"
    if kind == "directory":
        if sha is not None:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                "directory tree entry must not carry a SHA-256",
                path=raw_path_bytes.decode("utf-8", errors="backslashreplace"),
            )
        return b"D\x00" + encoded + b"\n"
    raise C0ValidationError(
        C0_SCHEMA_INVALID,
        f"tree entry kind must be file or directory, not {kind!r}",
    )


def human_tree_hash(entries: Iterable[object]) -> str:
    """SHA-256 over raw-path-byte-sorted human-tree lines.

    Files emit ``F NUL <payload_path_bytes_b64> NUL <payload_sha256> LF`` and
    directories emit ``D NUL <payload_path_bytes_b64> LF``.  Lines are ordered
    by raw payload-path bytes (the exact ``## Canonical bytes and hashes`` rule;
    the whole line is a deterministic tiebreaker only for degenerate duplicate
    paths, which never occur in a valid tree).  Empty directories keep their own
    ``D`` line, so directory identity survives transfer.
    """

    keyed: list[tuple[bytes, bytes]] = []
    for entry in entries:
        _, raw_path_bytes, _ = _tree_entry_fields(entry)
        line = human_tree_line(entry)
        if line is not None:
            keyed.append((raw_path_bytes, line))
    keyed.sort(key=lambda item: (item[0], item[1]))
    digest = hashlib.sha256()
    for _, line in keyed:
        digest.update(line)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Descriptor-relative, no-follow lstat payload tree scan.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScanResult:
    entries: tuple[PayloadEntry, ...]
    tree_sha256: str
    file_count: int
    directory_count: int


def _read_regular_file(dir_fd: int, name: str, rel: str) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise C0ValidationError(
            C0_SPECIAL_FILE,
            f"cannot open payload file {rel!r} no-follow: {exc}",
            path=rel,
        ) from exc
    try:
        opened = os.fstat(fd)
        if not stat_module.S_ISREG(opened.st_mode):
            raise C0ValidationError(
                C0_SPECIAL_FILE,
                f"payload {rel!r} is not a regular file after open",
                path=rel,
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise C0ValidationError(
            C0_HASH_MISMATCH,
            f"payload {rel!r} changed during read-only scan",
            path=rel,
        )
    return b"".join(chunks), opened


def scan_tree(
    payload_root: str | os.PathLike[str],
    *,
    normalizer: object,
) -> ScanResult:
    """Descriptor-relative, no-follow ``lstat`` scan of one payload root.

    Traversal opens each directory with ``O_NOFOLLOW`` and stats children with
    ``dir_fd`` + ``follow_symlinks=False``; a resolved-string prefix check is
    never used.  Symlinks, hardlinked files (``st_nlink > 1``), devices,
    sockets, FIFOs, unknown kinds, and mount escapes all refuse.  Every path is
    validated with the injected normalizer, and the exact human-tree hash is
    returned alongside the sorted inventory.
    """

    root = os.fspath(payload_root)
    try:
        root_stat = os.lstat(root)
    except OSError as exc:
        raise C0ValidationError(
            C0_DIRECTORY_MISSING,
            f"cannot lstat payload root {root!r}: {exc}",
        ) from exc
    if stat_module.S_ISLNK(root_stat.st_mode):
        raise C0ValidationError(
            C0_SPECIAL_FILE, f"payload root {root!r} is a symlink"
        )
    if not stat_module.S_ISDIR(root_stat.st_mode):
        raise C0ValidationError(
            C0_DIRECTORY_MISSING, f"payload root {root!r} is not a directory"
        )
    root_dev = root_stat.st_dev
    open_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_NOFOLLOW", 0
    ) | getattr(os, "O_CLOEXEC", 0)

    entries: list[PayloadEntry] = [PayloadEntry.directory("", "")]
    counts = {"file": 0, "directory": 0}

    # Mount escapes are detected at directory transitions: a filesystem is
    # mounted *onto a directory*, so a subdirectory whose device differs from
    # its parent has crossed a mount boundary.  Per-file device numbers are not
    # compared because some container overlays report a distinct device for
    # regular files versus their parent directory, which is not a real mount.
    def walk(dir_fd: int, rel: str, parent_dev: int) -> None:
        try:
            names = os.listdir(dir_fd)
        except OSError as exc:
            raise C0ValidationError(
                C0_DIRECTORY_MISSING,
                f"cannot list payload directory {rel or '.'!r}: {exc}",
                path=rel,
            ) from exc
        for name in sorted(names, key=lambda n: n.encode("utf-8", errors="surrogatepass")):
            try:
                name.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise C0ValidationError(
                    C0_PATH_INVALID,
                    f"payload name {name!r} is not strict UTF-8",
                    path=rel,
                ) from exc
            child_rel = f"{rel}/{name}" if rel else name
            try:
                child_stat = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            except OSError as exc:
                raise C0ValidationError(
                    C0_SPECIAL_FILE,
                    f"cannot lstat payload {child_rel!r}: {exc}",
                    path=child_rel,
                ) from exc
            if stat_module.S_ISLNK(child_stat.st_mode):
                raise C0ValidationError(
                    C0_SPECIAL_FILE, f"payload {child_rel!r} is a symlink", path=child_rel
                )
            key = derive_portability_key(child_rel, normalizer)
            path_bytes = child_rel.encode("utf-8", errors="strict")
            if stat_module.S_ISDIR(child_stat.st_mode):
                if child_stat.st_dev != parent_dev:
                    raise C0ValidationError(
                        C0_SPECIAL_FILE,
                        f"payload {child_rel!r} crosses a mount boundary",
                        path=child_rel,
                    )
                counts["directory"] += 1
                if counts["directory"] > MAX_PAYLOAD_DIRECTORIES:
                    raise C0ValidationError(
                        C0_PATH_TOO_LONG,
                        f"payload has more than {MAX_PAYLOAD_DIRECTORIES} directories",
                        path=child_rel,
                    )
                entries.append(
                    PayloadEntry.directory(child_rel, key, payload_path_bytes=path_bytes)
                )
                try:
                    child_fd = os.open(name, open_flags, dir_fd=dir_fd)
                except OSError as exc:
                    raise C0ValidationError(
                        C0_SPECIAL_FILE,
                        f"cannot open payload directory {child_rel!r} no-follow: {exc}",
                        path=child_rel,
                    ) from exc
                try:
                    walk(child_fd, child_rel, child_stat.st_dev)
                finally:
                    os.close(child_fd)
            elif stat_module.S_ISREG(child_stat.st_mode):
                if child_stat.st_nlink > 1:
                    raise C0ValidationError(
                        C0_HARDLINK,
                        f"payload file {child_rel!r} has {child_stat.st_nlink} hard links",
                        path=child_rel,
                    )
                counts["file"] += 1
                if counts["file"] > MAX_PAYLOAD_FILES:
                    raise C0ValidationError(
                        C0_PATH_TOO_LONG,
                        f"payload has more than {MAX_PAYLOAD_FILES} files",
                        path=child_rel,
                    )
                data, _ = _read_regular_file(dir_fd, name, child_rel)
                entries.append(
                    PayloadEntry.file(
                        child_rel, data, key, payload_path_bytes=path_bytes
                    )
                )
            else:
                raise C0ValidationError(
                    C0_SPECIAL_FILE,
                    f"payload {child_rel!r} is a device, socket, FIFO, or unknown kind",
                    path=child_rel,
                )

    try:
        root_fd = os.open(root, open_flags)
    except OSError as exc:
        raise C0ValidationError(
            C0_DIRECTORY_MISSING,
            f"cannot open payload root {root!r} no-follow: {exc}",
        ) from exc
    try:
        walk(root_fd, "", root_dev)
    finally:
        os.close(root_fd)

    ordered = tuple(sorted(entries, key=lambda e: e.payload_path_bytes))
    return ScanResult(
        entries=ordered,
        tree_sha256=human_tree_hash(ordered),
        file_count=counts["file"],
        directory_count=counts["directory"],
    )


# ---------------------------------------------------------------------------
# Deterministic canonical STORED ZIP packer.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PackMember:
    """One canonical archive member (a file with bytes, or a directory)."""

    name: str
    is_dir: bool = False
    data: bytes = b""


def _validate_arcname(name: str, *, allow_dir_slash: bool) -> tuple[list[str], bool]:
    """Validate a ZIP arc-name structurally; return ``(components, is_dir)``.

    Unlike the payload-path grammar this deliberately permits ``.tropo`` (a C0
    archive carries ``.tropo/vault-manifest.md`` and the record namespace) and
    Windows device stems, since the archive is not itself a payload subtree.
    It still refuses ``.git``, absolute/drive/traversal names, control bytes,
    over-depth, and over-length components.
    """

    if not isinstance(name, str) or name == "":
        raise C0ValidationError(C0_PATH_INVALID, "archive entry name is empty")
    if _contains_control(name):
        raise C0ValidationError(
            C0_PATH_INVALID, "archive entry name has a control character", path=name
        )
    if name.startswith("/"):
        raise C0ValidationError(C0_ZIP_ABSOLUTE, "archive entry name is absolute", path=name)
    if name.startswith("\\"):
        raise C0ValidationError(
            C0_ZIP_ABSOLUTE, "archive entry name is a UNC/absolute path", path=name
        )
    if _DRIVE_PREFIX_RE.match(name):
        raise C0ValidationError(
            C0_ZIP_DRIVE_PREFIX, "archive entry name has a drive prefix", path=name
        )
    is_dir = name.endswith("/")
    if is_dir and not allow_dir_slash:
        raise C0ValidationError(
            C0_PATH_INVALID, "archive entry name has an unexpected trailing slash", path=name
        )
    trimmed = name[:-1] if is_dir else name
    if _utf8_len(name) > MAX_PATH_BYTES:
        raise C0ValidationError(
            C0_PATH_TOO_LONG, f"archive name exceeds {MAX_PATH_BYTES} bytes", path=name
        )
    components = trimmed.split("/")
    if len(components) > MAX_COMPONENTS:
        raise C0ValidationError(
            C0_PATH_TOO_LONG,
            f"archive name has {len(components)} components (> {MAX_COMPONENTS})",
            path=name,
        )
    for comp in components:
        if comp == "":
            raise C0ValidationError(
                C0_PATH_INVALID, "archive name has an empty component", path=name
            )
        if comp == ".":
            raise C0ValidationError(
                C0_PATH_INVALID, "archive name has a '.' component", path=name
            )
        if comp == "..":
            raise C0ValidationError(
                C0_ZIP_TRAVERSAL, "archive name has a '..' component", path=name
            )
        if "\\" in comp:
            raise C0ValidationError(
                C0_PATH_INVALID, "archive name component has a backslash", path=name
            )
        if _utf8_len(comp) > MAX_COMPONENT_BYTES:
            raise C0ValidationError(
                C0_PATH_TOO_LONG,
                f"archive component {comp!r} exceeds {MAX_COMPONENT_BYTES} bytes",
                path=name,
            )
        if comp == ".git":
            raise C0ValidationError(
                C0_RESERVED_NAMESPACE, "archive name contains a .git component", path=name
            )
    return components, is_dir


def _encode_arcname(name: str) -> tuple[bytes, int]:
    raw = name.encode("utf-8", errors="strict")
    flag = 0 if raw.decode("ascii", errors="ignore") == name and name.isascii() else _GPF_UTF8
    return raw, flag


def canonical_pack(members: Iterable[PackMember | tuple]) -> bytes:
    """Produce a byte-deterministic canonical STORED ZIP.

    Entries are STORED (never deflated), names are sorted by raw UTF-8 bytes,
    directories are explicit with a trailing ``/`` (so empty directories are
    preserved), every timestamp is 1980-01-01T00:00:00, files use mode 0644 and
    directories 0755, and there are no comments, extra fields, or ``.git``.
    Packing identical inputs twice yields identical bytes.
    """

    normalized: list[PackMember] = []
    for member in members:
        if isinstance(member, PackMember):
            normalized.append(member)
        elif isinstance(member, tuple) and len(member) in (2, 3):
            name = member[0]
            is_dir = bool(member[1])
            data = member[2] if len(member) == 3 else b""
            normalized.append(PackMember(name, is_dir, data or b""))
        else:
            raise C0ValidationError(
                C0_SCHEMA_INVALID, "pack member must be PackMember or tuple"
            )

    prepared: list[tuple[bytes, PackMember, bool]] = []
    seen: set[bytes] = set()
    for member in normalized:
        stored_name = member.name
        if member.is_dir and not stored_name.endswith("/"):
            stored_name = stored_name + "/"
        components, is_dir = _validate_arcname(stored_name, allow_dir_slash=True)
        if is_dir != member.is_dir:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"member {member.name!r} directory flag disagrees with its name",
                path=member.name,
            )
        if member.is_dir and member.data:
            raise C0ValidationError(
                C0_SCHEMA_INVALID,
                f"directory member {member.name!r} may not carry data",
                path=member.name,
            )
        raw = stored_name.encode("utf-8", errors="strict")
        if raw in seen:
            raise C0ValidationError(
                C0_ZIP_DUPLICATE, f"duplicate archive member {stored_name!r}", path=stored_name
            )
        seen.add(raw)
        prepared.append((raw, PackMember(stored_name, member.is_dir, member.data), is_dir))

    # File-vs-directory conflict on the same logical path.
    dir_paths = {raw[:-1] for raw, _m, is_dir in prepared if is_dir}
    file_paths = {raw for raw, _m, is_dir in prepared if not is_dir}
    clash = dir_paths & file_paths
    if clash:
        example = sorted(clash)[0].decode("utf-8", errors="backslashreplace")
        raise C0ValidationError(
            C0_ZIP_DUPLICATE, f"archive uses {example!r} as both file and directory"
        )

    prepared.sort(key=lambda item: item[0])

    local_chunks: list[bytes] = []
    central_chunks: list[bytes] = []
    offset = 0
    for raw, member, is_dir in prepared:
        data = b"" if is_dir else member.data
        crc = zlib.crc32(data) & 0xFFFFFFFF
        size = len(data)
        _raw, flag = _encode_arcname(member.name)
        mode = _DIR_MODE if is_dir else _FILE_MODE
        external_attr = (mode << 16) | (0x10 if is_dir else 0x00)
        local = struct.pack(
            "<4sHHHHHIIIHH",
            _SIG_LOCAL,
            _VERSION_NEEDED,
            flag,
            _METHOD_STORED,
            _DOS_TIME_MIDNIGHT,
            _DOS_DATE_1980_01_01,
            crc,
            size,
            size,
            len(raw),
            0,
        ) + raw + data
        central = struct.pack(
            "<4sHHHHHHIIIHHHHHII",
            _SIG_CENTRAL,
            _UNIX_MADE_BY,
            _VERSION_NEEDED,
            flag,
            _METHOD_STORED,
            _DOS_TIME_MIDNIGHT,
            _DOS_DATE_1980_01_01,
            crc,
            size,
            size,
            len(raw),
            0,
            0,
            0,
            0,
            external_attr,
            offset,
        ) + raw
        local_chunks.append(local)
        central_chunks.append(central)
        offset += len(local)

    central_bytes = b"".join(central_chunks)
    local_bytes = b"".join(local_chunks)
    count = len(prepared)
    eocd = struct.pack(
        "<4sHHHHIIH",
        _SIG_EOCD,
        0,
        0,
        count,
        count,
        len(central_bytes),
        len(local_bytes),
        0,
    )
    return local_bytes + central_bytes + eocd


# ---------------------------------------------------------------------------
# Safe ZIP unpack: complete preflight, then staged stream, then atomic rename.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _CentralEntry:
    index: int
    raw_name: bytes
    name: str
    components: tuple[str, ...]
    is_dir: bool
    flag: int
    method: int
    crc: int
    comp_size: int
    uncomp_size: int
    header_offset: int
    made_by: int
    external_attr: int


@dataclass(frozen=True)
class PreflightResult:
    entries: tuple[_CentralEntry, ...]
    total_uncompressed: int
    effective_entry_count: int
    directories: tuple[str, ...]
    files: tuple[str, ...]


@dataclass(frozen=True)
class UnpackResult:
    destination: str
    tree_sha256: str
    file_count: int
    directory_count: int
    preflight: PreflightResult = field(repr=False)


def _u16(buf: bytes, off: int) -> int:
    return struct.unpack_from("<H", buf, off)[0]


def _u32(buf: bytes, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def _find_eocd(data: bytes) -> int:
    if len(data) < 22:
        raise C0ValidationError(C0_ZIP_UNSUPPORTED, "archive is too small to be a ZIP")
    max_back = min(len(data), 22 + 0xFFFF)
    window_start = len(data) - max_back
    idx = data.rfind(_SIG_EOCD, window_start)
    if idx < 0:
        raise C0ValidationError(
            C0_ZIP_UNSUPPORTED, "end-of-central-directory record not found"
        )
    comment_len = _u16(data, idx + 20)
    if idx + 22 + comment_len != len(data):
        raise C0ValidationError(
            C0_ZIP_UNSUPPORTED, "trailing bytes after end-of-central-directory record"
        )
    return idx


def _classify_zip_kind(entry_name: str, made_by: int, external_attr: int) -> str:
    """Return 'file', 'directory', or raise C0_ZIP_SPECIAL_FILE."""

    is_unix = (made_by >> 8) == 3
    unix_mode = (external_attr >> 16) & 0xFFFF
    if is_unix and unix_mode:
        if stat_module.S_ISDIR(unix_mode):
            return "directory"
        if stat_module.S_ISREG(unix_mode):
            return "file"
        raise C0ValidationError(
            C0_ZIP_SPECIAL_FILE,
            f"archive entry {entry_name!r} has a special Unix mode {oct(unix_mode)}",
            path=entry_name,
        )
    return "directory" if entry_name.endswith("/") else "file"


def preflight_archive(archive: bytes, *, normalizer: object) -> PreflightResult:
    """Complete central-directory + local-header preflight (no writes).

    Every hostile-archive class named in dev-spec §Safe ZIP is refused here,
    before any destination is created: multi-disk/ZIP64, over-count, encrypted,
    unsupported method, special-mode, absolute/drive/traversal names,
    non-UTF-8 names, over-depth/over-length, raw and normalized duplicates,
    file/directory conflicts, over-size, over-ratio, and any local-header/central
    -directory disagreement.
    """

    if not isinstance(archive, (bytes, bytearray, memoryview)):
        raise C0ValidationError(C0_ZIP_UNSUPPORTED, "archive must be raw bytes")
    data = bytes(archive)

    eocd = _find_eocd(data)
    # Reject ZIP64 outright: the canonical profile never needs it and parsing a
    # second EOCD format would widen the attack surface for this floor.  The
    # ZIP64 locator, when present, sits in the 20 bytes immediately before the
    # standard EOCD, so we look only there rather than scanning payload bytes.
    if eocd >= 20 and data[eocd - 20 : eocd - 16] == _SIG_ZIP64_LOCATOR:
        raise C0ValidationError(C0_ZIP_UNSUPPORTED, "ZIP64 archives are not supported")
    disk_no = _u16(data, eocd + 4)
    cd_start_disk = _u16(data, eocd + 6)
    entries_this_disk = _u16(data, eocd + 8)
    total_entries = _u16(data, eocd + 10)
    cd_size = _u32(data, eocd + 12)
    cd_offset = _u32(data, eocd + 16)

    if disk_no != 0 or cd_start_disk != 0 or entries_this_disk != total_entries:
        raise C0ValidationError(C0_ZIP_UNSUPPORTED, "multi-disk (spanned) archive")
    if (
        total_entries == _ZIP64_SENTINEL_16
        or cd_size == _ZIP64_SENTINEL_32
        or cd_offset == _ZIP64_SENTINEL_32
    ):
        raise C0ValidationError(C0_ZIP_UNSUPPORTED, "ZIP64 sentinel in EOCD record")
    # Over-count is refused from the declared central-directory count first, so
    # a count bomb never forces us to materialize its records.
    if total_entries > MAX_ZIP_ENTRIES:
        raise C0ValidationError(
            C0_ZIP_LIMIT_COUNT,
            f"archive declares {total_entries} entries (> {MAX_ZIP_ENTRIES})",
        )
    if cd_offset + cd_size > len(data):
        raise C0ValidationError(C0_ZIP_UNSUPPORTED, "central directory runs past EOF")

    entries: list[_CentralEntry] = []
    pos = cd_offset
    for index in range(total_entries):
        header_start = pos
        if data[header_start : header_start + 4] != _SIG_CENTRAL:
            raise C0ValidationError(
                C0_ZIP_UNSUPPORTED, f"bad central-directory header at entry {index}"
            )
        made_by = _u16(data, header_start + 4)
        flag = _u16(data, header_start + 8)
        method = _u16(data, header_start + 10)
        crc = _u32(data, header_start + 16)
        comp_size = _u32(data, header_start + 20)
        uncomp_size = _u32(data, header_start + 24)
        name_len = _u16(data, header_start + 28)
        extra_len = _u16(data, header_start + 30)
        comment_len = _u16(data, header_start + 32)
        external_attr = _u32(data, header_start + 38)
        header_offset = _u32(data, header_start + 42)
        name_start = header_start + 46
        raw_name = data[name_start : name_start + name_len]
        pos = name_start + name_len + extra_len + comment_len
        if pos > cd_offset + cd_size:
            raise C0ValidationError(
                C0_ZIP_UNSUPPORTED, f"central-directory entry {index} overruns"
            )

        if flag & (_GPF_ENCRYPTED | _GPF_STRONG_ENCRYPTION):
            raise C0ValidationError(
                C0_ZIP_ENCRYPTED, f"archive entry {index} is encrypted"
            )
        if flag & _GPF_DATA_DESCRIPTOR:
            raise C0ValidationError(
                C0_ZIP_UNSUPPORTED,
                f"archive entry {index} defers sizes to a data descriptor",
            )
        if method not in (_METHOD_STORED, _METHOD_DEFLATE):
            raise C0ValidationError(
                C0_ZIP_UNSUPPORTED,
                f"archive entry {index} uses unsupported method {method}",
            )
        try:
            name = raw_name.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise C0ValidationError(
                C0_PATH_INVALID, f"archive entry {index} name is not strict UTF-8"
            ) from exc
        if not name.isascii() and not (flag & _GPF_UTF8):
            raise C0ValidationError(
                C0_PATH_INVALID,
                f"archive entry {index} has a non-ASCII name without the UTF-8 flag",
                path=name,
            )
        components, name_is_dir = _validate_arcname(name, allow_dir_slash=True)
        kind = _classify_zip_kind(name, made_by, external_attr)
        is_dir = name_is_dir or kind == "directory"
        entries.append(
            _CentralEntry(
                index=index,
                raw_name=raw_name,
                name=name,
                components=tuple(components),
                is_dir=is_dir,
                flag=flag,
                method=method,
                crc=crc,
                comp_size=comp_size,
                uncomp_size=uncomp_size,
                header_offset=header_offset,
                made_by=made_by,
                external_attr=external_attr,
            )
        )

    # Raw-duplicate names.
    raw_seen: set[bytes] = set()
    for entry in entries:
        if entry.raw_name in raw_seen:
            raise C0ValidationError(
                C0_ZIP_DUPLICATE, f"archive repeats raw name {entry.name!r}", path=entry.name
            )
        raw_seen.add(entry.raw_name)

    # Normalized (portability-key) duplicates via the injected table.
    key_owner: dict[str, str] = {}
    for entry in entries:
        norm_key = "/".join(_apply_normalizer(normalizer, c) for c in entry.components)
        norm_key = norm_key + ("/" if entry.is_dir else "")
        prior = key_owner.get(norm_key)
        if prior is not None and prior != entry.name:
            raise C0ValidationError(
                C0_PORTABILITY_COLLISION,
                f"archive names {prior!r} and {entry.name!r} share a portability key",
                path=entry.name,
            )
        key_owner[norm_key] = entry.name

    # File-vs-directory conflicts, including implicit parent directories.
    file_paths: set[tuple[str, ...]] = set()
    dir_paths: set[tuple[str, ...]] = set()
    for entry in entries:
        comps = entry.components
        if entry.is_dir:
            dir_paths.add(comps)
        else:
            file_paths.add(comps)
        for depth in range(1, len(comps)):
            dir_paths.add(comps[:depth])
    conflict = file_paths & dir_paths
    if conflict:
        example = "/".join(sorted(conflict)[0])
        raise C0ValidationError(
            C0_ZIP_DUPLICATE, f"archive uses {example!r} as both file and directory"
        )

    effective = len(file_paths | dir_paths)
    if effective > MAX_ZIP_ENTRIES:
        raise C0ValidationError(
            C0_ZIP_LIMIT_COUNT,
            f"archive expands to {effective} entries incl. implicit dirs "
            f"(> {MAX_ZIP_ENTRIES})",
        )

    # Declared-size and declared-ratio limits (preflight, before streaming).
    total_uncompressed = 0
    for entry in entries:
        if entry.is_dir:
            continue
        if entry.uncomp_size > MAX_ENTRY_EXPANDED_BYTES:
            raise C0ValidationError(
                C0_ZIP_LIMIT_SIZE,
                f"entry {entry.name!r} declares {entry.uncomp_size} bytes "
                f"(> {MAX_ENTRY_EXPANDED_BYTES})",
                path=entry.name,
            )
        if entry.uncomp_size > MAX_COMPRESSION_RATIO * entry.comp_size:
            raise C0ValidationError(
                C0_ZIP_LIMIT_RATIO,
                f"entry {entry.name!r} declares ratio "
                f"{entry.uncomp_size}:{entry.comp_size} (> {MAX_COMPRESSION_RATIO}:1)",
                path=entry.name,
            )
        total_uncompressed += entry.uncomp_size
    if total_uncompressed > MAX_TOTAL_EXPANDED_BYTES:
        raise C0ValidationError(
            C0_ZIP_LIMIT_SIZE,
            f"archive declares {total_uncompressed} expanded bytes "
            f"(> {MAX_TOTAL_EXPANDED_BYTES})",
        )
    total_compressed = sum(e.comp_size for e in entries if not e.is_dir)
    if total_uncompressed > MAX_COMPRESSION_RATIO * total_compressed:
        raise C0ValidationError(
            C0_ZIP_LIMIT_RATIO,
            f"archive declares ratio {total_uncompressed}:{total_compressed} "
            f"(> {MAX_COMPRESSION_RATIO}:1)",
        )

    # Local-header / central-directory agreement.
    for entry in entries:
        off = entry.header_offset
        if data[off : off + 4] != _SIG_LOCAL:
            raise C0ValidationError(
                C0_ZIP_UNSUPPORTED, f"entry {entry.name!r} has no local header", path=entry.name
            )
        l_flag = _u16(data, off + 6)
        l_method = _u16(data, off + 8)
        l_crc = _u32(data, off + 14)
        l_comp = _u32(data, off + 18)
        l_uncomp = _u32(data, off + 22)
        l_name_len = _u16(data, off + 26)
        l_extra_len = _u16(data, off + 28)
        l_name = data[off + 30 : off + 30 + l_name_len]
        if l_name != entry.raw_name:
            raise C0ValidationError(
                C0_ZIP_UNSUPPORTED,
                f"entry {entry.name!r} local name disagrees with central directory",
                path=entry.name,
            )
        if (l_method, l_crc, l_comp, l_uncomp) != (
            entry.method,
            entry.crc,
            entry.comp_size,
            entry.uncomp_size,
        ):
            raise C0ValidationError(
                C0_ZIP_UNSUPPORTED,
                f"entry {entry.name!r} local header disagrees with central directory",
                path=entry.name,
            )
        data_start = off + 30 + l_name_len + l_extra_len
        if data_start + entry.comp_size > len(data):
            raise C0ValidationError(
                C0_ZIP_UNSUPPORTED,
                f"entry {entry.name!r} data runs past end of archive",
                path=entry.name,
            )

    files = tuple(sorted("/".join(c) for c in file_paths))
    directories = tuple(sorted("/".join(c) for c in dir_paths))
    return PreflightResult(
        entries=tuple(entries),
        total_uncompressed=total_uncompressed,
        effective_entry_count=effective,
        directories=directories,
        files=files,
    )


def _entry_data_offset(data: bytes, entry: _CentralEntry) -> int:
    off = entry.header_offset
    l_name_len = _u16(data, off + 26)
    l_extra_len = _u16(data, off + 28)
    return off + 30 + l_name_len + l_extra_len


def _decompress_and_verify(data: bytes, entry: _CentralEntry, running_total: int) -> bytes:
    start = _entry_data_offset(data, entry)
    raw = data[start : start + entry.comp_size]
    if entry.method == _METHOD_STORED:
        out = raw
    else:
        decompressor = zlib.decompressobj(-15)
        chunks: list[bytes] = []
        produced = 0
        for i in range(0, len(raw), 1024 * 1024):
            chunk = decompressor.decompress(raw[i : i + 1024 * 1024], MAX_ENTRY_EXPANDED_BYTES)
            produced += len(chunk)
            if produced > MAX_ENTRY_EXPANDED_BYTES:
                raise C0ValidationError(
                    C0_ZIP_LIMIT_SIZE,
                    f"entry {entry.name!r} expands beyond {MAX_ENTRY_EXPANDED_BYTES} bytes",
                    path=entry.name,
                )
            chunks.append(chunk)
        chunks.append(decompressor.flush())
        out = b"".join(chunks)
    if len(out) != entry.uncomp_size:
        raise C0ValidationError(
            C0_HASH_MISMATCH,
            f"entry {entry.name!r} expanded size disagrees with its header",
            path=entry.name,
        )
    if len(out) > MAX_ENTRY_EXPANDED_BYTES:
        raise C0ValidationError(
            C0_ZIP_LIMIT_SIZE, f"entry {entry.name!r} exceeds per-entry size", path=entry.name
        )
    if running_total + len(out) > MAX_TOTAL_EXPANDED_BYTES:
        raise C0ValidationError(
            C0_ZIP_LIMIT_SIZE, "archive exceeds total expanded size while streaming"
        )
    if len(out) > MAX_COMPRESSION_RATIO * entry.comp_size:
        raise C0ValidationError(
            C0_ZIP_LIMIT_RATIO, f"entry {entry.name!r} exceeds ratio while streaming", path=entry.name
        )
    if (zlib.crc32(out) & 0xFFFFFFFF) != entry.crc:
        raise C0ValidationError(
            C0_HASH_MISMATCH, f"entry {entry.name!r} failed CRC verification", path=entry.name
        )
    return out


def _fsync_dir(path: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def safe_unpack(
    archive: bytes | str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    normalizer: object,
) -> UnpackResult:
    """Preflight, stage to an absent sibling, verify, then atomically rename.

    The complete preflight runs before the destination is created.  Bytes are
    streamed into an absent sibling staging directory with per-entry and archive
    size/ratio caps and CRC verification enforced on the *actual* stream; the
    staged tree's exact human-tree hash is computed; then staging is atomically
    renamed onto the (required-absent) destination.  Any refusal removes only
    staging, leaving the destination absent or byte-identical.
    """

    if isinstance(archive, (bytes, bytearray, memoryview)):
        data = bytes(archive)
    else:
        arc_path = os.fspath(archive)
        try:
            st = os.lstat(arc_path)
        except OSError as exc:
            raise C0ValidationError(
                C0_ZIP_UNSUPPORTED, f"cannot lstat archive {arc_path!r}: {exc}"
            ) from exc
        if not stat_module.S_ISREG(st.st_mode):
            raise C0ValidationError(
                C0_ZIP_UNSUPPORTED, f"archive {arc_path!r} is not a regular file"
            )
        with open(arc_path, "rb") as handle:
            data = handle.read()

    dest = os.fspath(destination)
    dest_abs = os.path.abspath(dest)
    parent = os.path.dirname(dest_abs) or os.getcwd()
    if os.path.lexists(dest_abs):
        raise C0ValidationError(
            C0_DESTINATION_NOT_EMPTY,
            f"unpack destination {dest!r} already exists",
        )
    if not os.path.isdir(parent):
        raise C0ValidationError(
            C0_DIRECTORY_MISSING, f"destination parent {parent!r} is not a directory"
        )

    preflight = preflight_archive(data, normalizer=normalizer)

    staging = tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=parent)
    try:
        os.chmod(staging, _DIR_MODE & 0o7777)
        made_dirs: set[str] = {""}
        # Tree-hash entries are collected from what we actually stage.  The
        # human-tree hash excludes .tropo/.git itself, so a real C0 archive's
        # metadata is carried into the destination but never re-validated as a
        # payload component here (that is the codec/manifest layer's job).
        tree_entries: list[tuple[str, bytes, str | None]] = [("directory", b"", None)]

        def ensure_dir(components: tuple[str, ...]) -> None:
            accumulated: list[str] = []
            for comp in components:
                accumulated.append(comp)
                rel = "/".join(accumulated)
                if rel in made_dirs:
                    continue
                target = os.path.join(staging, *accumulated)
                os.mkdir(target)
                os.chmod(target, _DIR_MODE & 0o7777)
                made_dirs.add(rel)
                tree_entries.append(("directory", rel.encode("utf-8"), None))

        running_total = 0
        file_count = 0
        # Deterministic write order by raw name bytes.
        for entry in sorted(preflight.entries, key=lambda e: e.raw_name):
            if entry.is_dir:
                ensure_dir(entry.components)
                continue
            ensure_dir(entry.components[:-1])
            payload = _decompress_and_verify(data, entry, running_total)
            running_total += len(payload)
            target = os.path.join(staging, *entry.components)
            fd = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
                _FILE_MODE & 0o7777,
            )
            try:
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.chmod(target, _FILE_MODE & 0o7777)
            tree_entries.append(
                ("file", "/".join(entry.components).encode("utf-8"), payload_sha256(payload))
            )
            file_count += 1

        tree_sha256 = human_tree_hash(tree_entries)
        directory_count = len(made_dirs) - 1  # exclude the payload-root itself
        _fsync_dir(staging)
        os.rename(staging, dest_abs)
        _fsync_dir(parent)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return UnpackResult(
        destination=dest_abs,
        tree_sha256=tree_sha256,
        file_count=file_count,
        directory_count=directory_count,
        preflight=preflight,
    )


__all__ = [
    "C0Finding",
    "C0Refusal",
    "C0ValidationError",
    "C0_DESTINATION_NOT_EMPTY",
    "C0_DIRECTORY_MISSING",
    "C0_DUPLICATE_PATH",
    "C0_HARDLINK",
    "C0_HASH_MISMATCH",
    "C0_PATH_INVALID",
    "C0_PATH_TOO_LONG",
    "C0_PORTABILITY_COLLISION",
    "C0_RESERVED_NAMESPACE",
    "C0_SCHEMA_INVALID",
    "C0_SPECIAL_FILE",
    "C0_ZIP_ABSOLUTE",
    "C0_ZIP_DRIVE_PREFIX",
    "C0_ZIP_DUPLICATE",
    "C0_ZIP_ENCRYPTED",
    "C0_ZIP_LIMIT_COUNT",
    "C0_ZIP_LIMIT_RATIO",
    "C0_ZIP_LIMIT_SIZE",
    "C0_ZIP_SPECIAL_FILE",
    "C0_ZIP_TRAVERSAL",
    "C0_ZIP_UNSUPPORTED",
    "MAX_COMPONENTS",
    "MAX_COMPONENT_BYTES",
    "MAX_COMPRESSION_RATIO",
    "MAX_ENTRY_EXPANDED_BYTES",
    "MAX_PATH_BYTES",
    "MAX_PAYLOAD_DIRECTORIES",
    "MAX_PAYLOAD_FILES",
    "MAX_TOTAL_EXPANDED_BYTES",
    "MAX_ZIP_ENTRIES",
    "NormalizationTable",
    "PackMember",
    "PayloadEntry",
    "PreflightResult",
    "RESERVED_PATH_COMPONENTS",
    "STAGING_PREFIX",
    "ScanResult",
    "UnpackResult",
    "WINDOWS_FORBIDDEN_CHARS",
    "canonical_pack",
    "derive_portability_key",
    "human_tree_hash",
    "human_tree_line",
    "make_portability_key",
    "payload_sha256",
    "portability_validator",
    "preflight_archive",
    "safe_unpack",
    "scan_tree",
]
