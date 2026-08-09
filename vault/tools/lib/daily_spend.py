"""Checksum-verified, flock-serialized UTC daily model-spend ledger."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from lib.loop_metering import MAX_NANO_USD


SCHEMA_VERSION = 1
_UID_RE = re.compile(r"^[0-9a-f]{8}$")
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
)
_VERSIONED_LEDGER_RE = re.compile(
    r"^(?P<day>\d{4}-\d{2}-\d{2})@"
    r"(?P<version>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))\.json$"
)
_CHECKSUM_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSIONED_LEDGER_FLOOR = (1, 2, 0)
_LEDGER_FIELDS = {
    "schema_version",
    "utc_date",
    "policy_uid",
    "policy_version",
    "daily_ceiling_nano_usd",
    "actual_total_nano_usd",
    "poisoned",
    "poison_reason",
    "reservations",
    "checksum",
}
_RESERVATION_FIELDS = {
    "run_uid",
    "task",
    "model",
    "segment_classes",
    "worst_case_nano_usd",
    "status",
    "actual_nano_usd",
    "gateway_request_id",
}
_STATUSES = {"reserved", "claimed", "reconciled"}


class DailySpendError(RuntimeError):
    """Daily spend state is absent, malformed, stale, or unsafe."""


class DailySpendLimitError(DailySpendError):
    """A valid reservation would cross the locked UTC-day ceiling."""


class MonthlySpendLimitError(DailySpendError):
    """A valid reservation would cross the locked UTC-month aggregate belt."""


def utc_day(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        raise DailySpendError("clock must return a datetime")
    if value.tzinfo is None:
        raise DailySpendError("clock datetime must be timezone-aware")
    return value.astimezone(timezone.utc).date().isoformat()


def utc_month(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        raise DailySpendError("clock must return a datetime")
    if value.tzinfo is None:
        raise DailySpendError("clock datetime must be timezone-aware")
    return value.astimezone(timezone.utc).strftime("%Y-%m")


def _validate_day(value: object) -> str:
    if not isinstance(value, str) or not _DAY_RE.fullmatch(value):
        raise DailySpendError("UTC day must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DailySpendError("UTC day is not a calendar date") from exc
    if parsed.isoformat() != value:
        raise DailySpendError("UTC day is not canonical")
    return value


def _validate_month(value: object) -> str:
    if not isinstance(value, str) or not _MONTH_RE.fullmatch(value):
        raise DailySpendError("UTC month must be YYYY-MM")
    year_str, month_str = value.split("-")
    if not (1 <= int(month_str) <= 12):
        raise DailySpendError("UTC month is not a calendar month")
    if int(year_str) < 1:
        raise DailySpendError("UTC month year is invalid")
    return value


def _month_of_day(day: str) -> str:
    return _validate_day(day)[:7]


def _semver(value: object, field: str = "policy_version") -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise DailySpendError(f"{field} must be strict semantic version")
    match = _SEMVER_RE.fullmatch(value)
    if match is None:
        raise DailySpendError(f"{field} must be strict semantic version")
    return tuple(int(part) for part in match.groups())


def _ledger_path(root: Path | str, day: str, policy_version: str) -> Path:
    """Return the sole ledger path for one strict policy version."""
    selected_day = _validate_day(day)
    version = _semver(policy_version)
    name = (
        f"{selected_day}@{policy_version}.json"
        if version >= _VERSIONED_LEDGER_FLOOR
        else f"{selected_day}.json"
    )
    return Path(root) / name


def _day_ledger_paths(root: Path | str, day: str) -> tuple[Path, ...]:
    """Enumerate every strictly named same-day ledger; reject ambiguous peers."""
    selected_day = _validate_day(day)
    candidate_root = Path(root)
    try:
        entries = tuple(candidate_root.iterdir())
    except OSError as exc:
        raise DailySpendError(f"daily ledger peers are unreadable: {exc}") from exc

    paths = []
    inodes: set[tuple[int, int]] = set()
    for path in entries:
        name = path.name
        if name == f"{selected_day}.lock":
            continue
        is_legacy = name == f"{selected_day}.json"
        match = _VERSIONED_LEDGER_RE.fullmatch(name)
        is_versioned = match is not None and match.group("day") == selected_day
        if not is_legacy and not is_versioned:
            if name.startswith(selected_day) or name.startswith(f".{selected_day}"):
                raise DailySpendError(
                    f"unknown same-day ledger naming: {name}"
                )
            continue
        if path.is_symlink():
            raise DailySpendError(f"same-day ledger is symlinked: {name}")
        try:
            info = path.stat()
        except OSError as exc:
            raise DailySpendError(
                f"same-day ledger is unreadable: {name}: {exc}"
            ) from exc
        if not stat.S_ISREG(info.st_mode):
            raise DailySpendError(f"same-day ledger is not regular: {name}")
        inode = (info.st_dev, info.st_ino)
        if inode in inodes:
            raise DailySpendError("duplicate same-day ledger inode")
        inodes.add(inode)
        paths.append(path)
    return tuple(sorted(paths, key=lambda path: path.name))


def _exact_amount(value: object, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DailySpendError(f"{field} must be exact integer nano-USD")
    minimum = 1 if positive else 0
    if value < minimum or value > MAX_NANO_USD:
        raise DailySpendError(f"{field} is outside the nano-USD domain")
    return value


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailySpendError(f"ledger is not canonical JSON: {exc}") from exc


def _checksum(value: dict) -> str:
    payload = dict(value)
    payload.pop("checksum", None)
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DailySpendError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value):
    raise DailySpendError(f"non-finite JSON constant {value!r}")


def _strict_json(raw: bytes) -> dict:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except DailySpendError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise DailySpendError(f"ledger JSON is malformed: {exc}") from exc
    if type(value) is not dict:
        raise DailySpendError("ledger must be a JSON object")
    return value


def _validate_binding(
    record: dict,
    *,
    run_uid: str,
    task: str,
    model: str,
    segment_classes: tuple[str, ...],
) -> None:
    expected = {
        "run_uid": run_uid,
        "task": task,
        "model": model,
        "segment_classes": list(segment_classes),
    }
    for field, value in expected.items():
        if record.get(field) != value:
            raise DailySpendError(f"reservation {field} binding mismatch")


def _validate_ledger(
    value: dict,
    *,
    expected_day: str,
    policy_uid: str | None = None,
    policy_version: str | None = None,
    daily_ceiling_nano_usd: int | None = None,
) -> dict:
    if set(value) != _LEDGER_FIELDS:
        raise DailySpendError(
            f"ledger fields must equal {sorted(_LEDGER_FIELDS)}"
        )
    if value.get("schema_version") != SCHEMA_VERSION:
        raise DailySpendError("ledger schema_version mismatch")
    if value.get("utc_date") != _validate_day(expected_day):
        raise DailySpendError("ledger UTC date is stale or mismatched")
    uid = value.get("policy_uid")
    if not isinstance(uid, str) or not _UID_RE.fullmatch(uid):
        raise DailySpendError("ledger policy_uid must be 8 lowercase hex")
    version = value.get("policy_version")
    _semver(version, "ledger policy_version")
    ceiling = _exact_amount(
        value.get("daily_ceiling_nano_usd"),
        "daily_ceiling_nano_usd",
        positive=True,
    )
    actual_total = _exact_amount(
        value.get("actual_total_nano_usd"),
        "actual_total_nano_usd",
    )
    if policy_uid is not None and uid != policy_uid:
        raise DailySpendError("ledger policy_uid mismatch")
    if policy_version is not None and version != policy_version:
        raise DailySpendError("ledger policy_version mismatch")
    if (
        daily_ceiling_nano_usd is not None
        and ceiling != daily_ceiling_nano_usd
    ):
        raise DailySpendError("ledger daily ceiling mismatch")
    if type(value.get("poisoned")) is not bool:
        raise DailySpendError("ledger poisoned must be boolean")
    poison_reason = value.get("poison_reason")
    if value["poisoned"]:
        if not isinstance(poison_reason, str) or not poison_reason:
            raise DailySpendError("poisoned ledger requires a reason")
    elif poison_reason is not None:
        raise DailySpendError("clean ledger poison_reason must be null")
    reservations = value.get("reservations")
    if type(reservations) is not dict:
        raise DailySpendError("ledger reservations must be an object")

    reconciled_total = 0
    for reservation_id, record in reservations.items():
        if not isinstance(reservation_id, str) or not _UID_RE.fullmatch(
            reservation_id
        ):
            raise DailySpendError("reservation IDs must be 8 lowercase hex")
        if type(record) is not dict or set(record) != _RESERVATION_FIELDS:
            raise DailySpendError(
                f"reservation {reservation_id} has a non-closed schema"
            )
        run_uid = record.get("run_uid")
        if not isinstance(run_uid, str) or not _UID_RE.fullmatch(run_uid):
            raise DailySpendError("reservation run_uid must be 8 lowercase hex")
        if not isinstance(record.get("task"), str) or not record["task"]:
            raise DailySpendError("reservation task must be non-empty")
        if not isinstance(record.get("model"), str) or not record["model"]:
            raise DailySpendError("reservation model must be non-empty")
        segments = record.get("segment_classes")
        if (
            not isinstance(segments, list)
            or not segments
            or segments != sorted(set(segments))
            or any(value not in {"os", "team", "private"} for value in segments)
        ):
            raise DailySpendError("reservation segment_classes are invalid")
        worst = _exact_amount(
            record.get("worst_case_nano_usd"),
            "reservation.worst_case_nano_usd",
            positive=True,
        )
        status_value = record.get("status")
        if status_value not in _STATUSES:
            raise DailySpendError("reservation status is invalid")
        actual = record.get("actual_nano_usd")
        request_id = record.get("gateway_request_id")
        if status_value == "reserved":
            if actual is not None or request_id is not None:
                raise DailySpendError("reserved record has consumed fields")
        elif status_value == "claimed":
            if actual is not None or not isinstance(request_id, str) or not request_id:
                raise DailySpendError("claimed record has invalid gateway binding")
        else:
            actual_value = _exact_amount(actual, "reservation.actual_nano_usd")
            if actual_value > worst:
                raise DailySpendError("reconciled actual exceeds reservation")
            if request_id is not None and (
                not isinstance(request_id, str) or not request_id
            ):
                raise DailySpendError("gateway_request_id must be null or non-empty")
            reconciled_total += actual_value
    if reconciled_total != actual_total:
        raise DailySpendError("ledger actual total does not match reservations")
    checksum = value.get("checksum")
    if not isinstance(checksum, str) or not _CHECKSUM_RE.fullmatch(checksum):
        raise DailySpendError("ledger checksum must be lowercase SHA-256")
    if checksum != _checksum(value):
        raise DailySpendError("ledger checksum mismatch")
    if effective_committed_nano_usd(value) > ceiling:
        raise DailySpendError("ledger committed spend exceeds its ceiling")
    return value


def effective_committed_nano_usd(ledger: dict) -> int:
    total = 0
    for record in ledger["reservations"].values():
        if record["status"] == "reconciled":
            total += record["actual_nano_usd"]
        else:
            total += record["worst_case_nano_usd"]
    if total > MAX_NANO_USD:
        raise DailySpendError("effective committed spend overflow")
    return total


def _require_root(root: Path, *, create: bool) -> Path:
    candidate = Path(root)
    if create:
        candidate.mkdir(parents=True, exist_ok=True)
    if candidate.is_symlink() or not candidate.is_dir():
        raise DailySpendError("daily spend root is missing or symlinked")
    return candidate


@contextmanager
def _locked(root: Path, day: str, *, initialize: bool = False) -> Iterator[Path]:
    root = _require_root(root, create=initialize)
    day = _validate_day(day)
    lock_path = root / f"{day}.lock"
    flags = os.O_RDWR | os.O_NOFOLLOW
    if initialize:
        flags |= os.O_CREAT
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise DailySpendError(f"stable lock is unavailable: {exc}") from exc
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            raise DailySpendError("stable lock is not a regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield root
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _read_locked(path: Path, day: str, **identity) -> dict:
    if path.is_symlink() or not path.is_file():
        raise DailySpendError("daily ledger is missing or symlinked")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            raw = os.read(descriptor, os.fstat(descriptor).st_size + 1)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise DailySpendError(f"daily ledger is unreadable: {exc}") from exc
    return _validate_ledger(_strict_json(raw), expected_day=day, **identity)


def _combined_committed_locked(
    root: Path,
    day: str,
    *,
    policy_uid: str,
    daily_ceiling_nano_usd: int,
) -> int:
    """Sum every same-day policy ledger while the caller holds the day lock."""
    total = 0
    versions: set[str] = set()
    reservation_ids: set[str] = set()
    for path in _day_ledger_paths(root, day):
        if path.name == f"{day}.json":
            ledger = _read_locked(
                path,
                day,
                policy_uid=policy_uid,
                daily_ceiling_nano_usd=daily_ceiling_nano_usd,
            )
            version = ledger["policy_version"]
            if _semver(version, "ledger policy_version") >= _VERSIONED_LEDGER_FLOOR:
                raise DailySpendError(
                    "legacy ledger embeds a policy version requiring a versioned path"
                )
        else:
            match = _VERSIONED_LEDGER_RE.fullmatch(path.name)
            if match is None or match.group("day") != day:
                raise DailySpendError("versioned ledger filename is invalid")
            version = match.group("version")
            if _semver(version) < _VERSIONED_LEDGER_FLOOR:
                raise DailySpendError(
                    "versioned ledger embeds a legacy policy version"
                )
            ledger = _read_locked(
                path,
                day,
                policy_uid=policy_uid,
                policy_version=version,
                daily_ceiling_nano_usd=daily_ceiling_nano_usd,
            )
        if _ledger_path(root, day, version) != path:
            raise DailySpendError("ledger filename/version binding mismatch")
        if version in versions:
            raise DailySpendError("duplicate same-day policy version ledger")
        versions.add(version)
        if ledger["poisoned"]:
            raise DailySpendError(f"same-day ledger is poisoned: {path.name}")
        overlap = reservation_ids.intersection(ledger["reservations"])
        if overlap:
            raise DailySpendError(
                "duplicate reservation ID across same-day ledgers"
            )
        reservation_ids.update(ledger["reservations"])
        committed = effective_committed_nano_usd(ledger)
        if total > MAX_NANO_USD - committed:
            raise DailySpendError("combined effective committed spend overflow")
        total += committed
    return total


def monthly_committed_nano_usd(
    root: Path | str,
    month: str,
    *,
    policy_uid: str,
    daily_ceiling_nano_usd: int,
) -> int:
    """Sum effective committed spend across every daily ledger dated in `month`.

    This is the UTC-month aggregate belt (D2's $50/month leak-detection
    ceiling) — a read-only aggregate over the already-hardened daily ledgers,
    not a second reservation/claim/reconcile lifecycle. It reuses the exact
    same checksum/schema/poison validation every daily ledger already passes
    (`_read_locked` / `_validate_ledger`); no new trust surface is introduced.

    Deliberate scope: only the *current* UTC day is read under its own flock
    (by the caller of `reserve`, which holds that lock for the duration of
    this call). Prior days in the same month are read without acquiring their
    locks — they are settled history, not concurrently mutated, and this
    belt exists to catch a slow leak across many quiet days, not to be a
    second atomic gate racing the daily ceiling. A day-boundary race here
    self-corrects on the very next reservation.
    """
    selected_month = _validate_month(month)
    candidate_root = _require_root(Path(root), create=False)
    try:
        entries = tuple(candidate_root.iterdir())
    except OSError as exc:
        raise DailySpendError(f"monthly ledger peers are unreadable: {exc}") from exc

    days_in_month: set[str] = set()
    for path in entries:
        name = path.name
        day_candidate = name[:10]
        if not _DAY_RE.fullmatch(day_candidate):
            continue
        if not (name == f"{day_candidate}.json" or name == f"{day_candidate}.lock"
                or _VERSIONED_LEDGER_RE.fullmatch(name)):
            continue
        if _month_of_day(day_candidate) == selected_month:
            days_in_month.add(day_candidate)

    total = 0
    reservation_ids: set[str] = set()
    for day in sorted(days_in_month):
        for path in _day_ledger_paths(candidate_root, day):
            match = _VERSIONED_LEDGER_RE.fullmatch(path.name)
            policy_version = match.group("version") if match else None
            ledger = _read_locked(
                path,
                day,
                policy_uid=policy_uid,
                policy_version=policy_version,
                daily_ceiling_nano_usd=daily_ceiling_nano_usd,
            )
            overlap = reservation_ids.intersection(ledger["reservations"])
            if overlap:
                raise DailySpendError(
                    "duplicate reservation ID across monthly ledgers"
                )
            reservation_ids.update(ledger["reservations"])
            committed = effective_committed_nano_usd(ledger)
            if total > MAX_NANO_USD - committed:
                raise DailySpendError(
                    "combined monthly committed spend overflow"
                )
            total += committed
    return total


def _write_locked(path: Path, ledger: dict) -> None:
    ledger["checksum"] = _checksum(ledger)
    rendered = _canonical_bytes(ledger) + b"\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temp_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_new_locked(path: Path, ledger: dict) -> None:
    """Create one initialized ledger without replacing a racing path."""
    ledger["checksum"] = _checksum(ledger)
    rendered = _canonical_bytes(ledger) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise DailySpendError(f"daily ledger creation failed: {exc}") from exc
    try:
        remaining = memoryview(rendered)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("ledger write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.close(descriptor)


def initialize_ledger(
    root: Path | str,
    *,
    policy_uid: str,
    policy_version: str,
    daily_ceiling_nano_usd: int,
    day: str | None = None,
) -> dict:
    selected_day = _validate_day(day or utc_day())
    if not isinstance(policy_uid, str) or not _UID_RE.fullmatch(policy_uid):
        raise DailySpendError("policy_uid must be 8 lowercase hex")
    _semver(policy_version)
    ceiling = _exact_amount(
        daily_ceiling_nano_usd,
        "daily_ceiling_nano_usd",
        positive=True,
    )
    with _locked(Path(root), selected_day, initialize=True) as locked_root:
        path = _ledger_path(locked_root, selected_day, policy_version)
        if path.exists() or path.is_symlink():
            raise DailySpendError("daily ledger already exists")
        ledger = {
            "schema_version": SCHEMA_VERSION,
            "utc_date": selected_day,
            "policy_uid": policy_uid,
            "policy_version": policy_version,
            "daily_ceiling_nano_usd": ceiling,
            "actual_total_nano_usd": 0,
            "poisoned": False,
            "poison_reason": None,
            "reservations": {},
            "checksum": "",
        }
        _write_new_locked(path, ledger)
        return dict(ledger)


def read_ledger(
    root: Path | str,
    *,
    day: str,
    policy_uid: str | None = None,
    policy_version: str | None = None,
    daily_ceiling_nano_usd: int | None = None,
) -> dict:
    selected_day = _validate_day(day)
    if policy_version is None:
        raise DailySpendError("policy_version is required to select one ledger")
    with _locked(Path(root), selected_day) as locked_root:
        path = _ledger_path(locked_root, selected_day, policy_version)
        return _read_locked(
            path,
            selected_day,
            policy_uid=policy_uid,
            policy_version=policy_version,
            daily_ceiling_nano_usd=daily_ceiling_nano_usd,
        )


def reserve(
    root: Path | str,
    *,
    day: str,
    policy_uid: str,
    policy_version: str,
    daily_ceiling_nano_usd: int,
    reservation_id: str,
    run_uid: str,
    task: str,
    model: str,
    segment_classes: tuple[str, ...],
    worst_case_nano_usd: int,
    monthly_ceiling_nano_usd: int | None = None,
) -> dict:
    selected_day = _validate_day(day)
    if not isinstance(reservation_id, str) or not _UID_RE.fullmatch(reservation_id):
        raise DailySpendError("reservation_id must be 8 lowercase hex")
    if not isinstance(run_uid, str) or not _UID_RE.fullmatch(run_uid):
        raise DailySpendError("run_uid must be 8 lowercase hex")
    if not isinstance(task, str) or not task:
        raise DailySpendError("task must be non-empty")
    if not isinstance(model, str) or not model:
        raise DailySpendError("model must be non-empty")
    if (
        not isinstance(segment_classes, tuple)
        or not segment_classes
        or segment_classes != tuple(sorted(set(segment_classes)))
        or any(value not in {"os", "team", "private"} for value in segment_classes)
    ):
        raise DailySpendError("segment_classes must be canonical and non-empty")
    worst = _exact_amount(
        worst_case_nano_usd,
        "worst_case_nano_usd",
        positive=True,
    )
    with _locked(Path(root), selected_day) as locked_root:
        path = _ledger_path(locked_root, selected_day, policy_version)
        committed = _combined_committed_locked(
            locked_root,
            selected_day,
            policy_uid=policy_uid,
            daily_ceiling_nano_usd=daily_ceiling_nano_usd,
        )
        ledger = _read_locked(
            path,
            selected_day,
            policy_uid=policy_uid,
            policy_version=policy_version,
            daily_ceiling_nano_usd=daily_ceiling_nano_usd,
        )
        if ledger["poisoned"]:
            raise DailySpendError("daily ledger is poisoned")
        if reservation_id in ledger["reservations"]:
            raise DailySpendError("reservation_id already exists")
        if committed > MAX_NANO_USD - worst:
            raise DailySpendError("combined reservation spend overflow")
        if committed + worst > ledger["daily_ceiling_nano_usd"]:
            raise DailySpendLimitError("reservation exceeds remaining UTC-day spend")
        if monthly_ceiling_nano_usd is not None:
            ceiling = _exact_amount(
                monthly_ceiling_nano_usd,
                "monthly_ceiling_nano_usd",
                positive=True,
            )
            month = _month_of_day(selected_day)
            month_committed = monthly_committed_nano_usd(
                locked_root,
                month,
                policy_uid=policy_uid,
                daily_ceiling_nano_usd=daily_ceiling_nano_usd,
            )
            if month_committed > MAX_NANO_USD - worst:
                raise DailySpendError("combined monthly reservation spend overflow")
            if month_committed + worst > ceiling:
                raise MonthlySpendLimitError(
                    "reservation exceeds remaining UTC-month spend"
                )
        record = {
            "run_uid": run_uid,
            "task": task,
            "model": model,
            "segment_classes": list(segment_classes),
            "worst_case_nano_usd": worst,
            "status": "reserved",
            "actual_nano_usd": None,
            "gateway_request_id": None,
        }
        ledger["reservations"][reservation_id] = record
        _write_locked(path, ledger)
        return dict(record)


def claim_reservation(
    root: Path | str,
    *,
    day: str,
    policy_uid: str,
    policy_version: str,
    daily_ceiling_nano_usd: int,
    reservation_id: str,
    run_uid: str,
    task: str,
    model: str,
    segment_classes: tuple[str, ...],
    gateway_request_id: str,
    minimum_worst_case_nano_usd: int | None = None,
) -> dict:
    selected_day = _validate_day(day)
    if not isinstance(gateway_request_id, str) or not gateway_request_id:
        raise DailySpendError("gateway_request_id must be non-empty")
    with _locked(Path(root), selected_day) as locked_root:
        path = _ledger_path(locked_root, selected_day, policy_version)
        ledger = _read_locked(
            path,
            selected_day,
            policy_uid=policy_uid,
            policy_version=policy_version,
            daily_ceiling_nano_usd=daily_ceiling_nano_usd,
        )
        if ledger["poisoned"]:
            raise DailySpendError("daily ledger is poisoned")
        record = ledger["reservations"].get(reservation_id)
        if record is None:
            raise DailySpendError("reservation is unknown")
        _validate_binding(
            record,
            run_uid=run_uid,
            task=task,
            model=model,
            segment_classes=segment_classes,
        )
        if record["status"] != "reserved":
            raise DailySpendError("reservation is not live or was replayed")
        if minimum_worst_case_nano_usd is not None:
            minimum = _exact_amount(
                minimum_worst_case_nano_usd,
                "minimum_worst_case_nano_usd",
                positive=True,
            )
            if record["worst_case_nano_usd"] < minimum:
                raise DailySpendError(
                    "reservation does not cover the exact gateway request"
                )
        record["status"] = "claimed"
        record["gateway_request_id"] = gateway_request_id
        _write_locked(path, ledger)
        return dict(record)


def _poison(ledger: dict, reason: str) -> None:
    ledger["poisoned"] = True
    ledger["poison_reason"] = reason


def reconcile(
    root: Path | str,
    *,
    day: str,
    policy_uid: str,
    policy_version: str,
    daily_ceiling_nano_usd: int,
    reservation_id: str,
    run_uid: str,
    task: str,
    model: str,
    segment_classes: tuple[str, ...],
    actual_nano_usd: int,
) -> dict:
    selected_day = _validate_day(day)
    actual = _exact_amount(actual_nano_usd, "actual_nano_usd")
    with _locked(Path(root), selected_day) as locked_root:
        path = _ledger_path(locked_root, selected_day, policy_version)
        ledger = _read_locked(
            path,
            selected_day,
            policy_uid=policy_uid,
            policy_version=policy_version,
            daily_ceiling_nano_usd=daily_ceiling_nano_usd,
        )
        if ledger["poisoned"]:
            raise DailySpendError("daily ledger is poisoned")
        record = ledger["reservations"].get(reservation_id)
        poison_reason = None
        if record is None:
            poison_reason = "reconciliation named an unknown reservation"
        else:
            try:
                _validate_binding(
                    record,
                    run_uid=run_uid,
                    task=task,
                    model=model,
                    segment_classes=segment_classes,
                )
            except DailySpendError as exc:
                poison_reason = str(exc)
            if poison_reason is None and record["status"] == "reconciled":
                poison_reason = "reservation was reconciled more than once"
            if (
                poison_reason is None
                and actual > record["worst_case_nano_usd"]
            ):
                poison_reason = "actual spend exceeded its reservation"
        if poison_reason is not None:
            _poison(ledger, poison_reason)
            _write_locked(path, ledger)
            raise DailySpendError(poison_reason)

        record["status"] = "reconciled"
        record["actual_nano_usd"] = actual
        ledger["actual_total_nano_usd"] += actual
        if ledger["actual_total_nano_usd"] > MAX_NANO_USD:
            _poison(ledger, "actual spend total overflow")
            _write_locked(path, ledger)
            raise DailySpendError("actual spend total overflow")
        _write_locked(path, ledger)
        return dict(record)


__all__ = [
    "DailySpendError",
    "DailySpendLimitError",
    "MonthlySpendLimitError",
    "SCHEMA_VERSION",
    "claim_reservation",
    "effective_committed_nano_usd",
    "initialize_ledger",
    "monthly_committed_nano_usd",
    "read_ledger",
    "reconcile",
    "reserve",
    "utc_day",
    "utc_month",
]
