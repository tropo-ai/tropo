"""lib/publish_journal.py — the R1 publish-job STORE for the L1v3 Data Contract.

Dev-spec 3c13977e (L1v3 Data Contract), Binding Decision R1; cycle brief
cc437616 §7 (job lifecycle + the meaning of "landed") and §9 (closed error
enum). Test-spec c56b9cc0 assertions A4 (durability) + A5 (closed error enum),
and the substrate the A2 draftStatus merge overlays.

THE MOVE THIS IMPLEMENTS (dev-spec §Scope boundary):
  The cockpit reads ONE surface — a frontmatter-reconciled, read-only derived
  index whose only authoritative writer is `vault:rebuild`. Transient publish
  state (publishing / blocked) therefore CANNOT live in that index — a rebuild
  would erase it. This store is the durable write/job surface that lives
  OUTSIDE the index; the API layer merges (index scope) ⊔ (this store) to
  produce draftStatus. See lib/draft_status.py for the merge.

R1 DURABILITY DISCIPLINE (reuses the C0 journal discipline 372ffdda + the
Event Ledger per-writer stream primitives f15a9b85 — same append-under-flock,
fsync, and no-legacy-fallback posture as lib/event_identity.py):
  - append-only         — records are never edited or deleted in place;
  - hash-chained        — each record binds the previous record's hash, so any
                          tamper of an earlier record breaks the chain;
  - fsync'd             — every append flushes + fsyncs before returning;
  - CAS-guarded         — an append may pin the expected tip hash; a losing
                          writer refuses (compare-and-swap) rather than
                          clobbering a concurrent append;
  - torn-tail-tolerant  — a crash mid-append can leave a partial trailing line;
                          the reader drops ONLY that trailing torn record and
                          resumes from the last intact record. Corruption
                          anywhere but the tail is a hard failure (the chain is
                          broken, not merely truncated).

R1 also requires: a full `vault:rebuild` cannot erase or downgrade a live job
state (structurally true — this file is not the index and is never rebuilt from
frontmatter), and process loss at any transition resumes from evidence
(idempotent append — re-applying the transition already on the tip is a no-op).

WHAT THIS MODULE DOES NOT DO (D5 boundary — 304badf7, still `designed`):
  It is the STORE, not the publish SERVICE. It records typed job/error state
  and resolves the current overlay; it does NOT drive git push / remote CAS /
  local reconcile. The write-path service (§Write Contract) SEQUENCES BEHIND D5
  and is out of scope until D5 lands. This store is buildable + testable now.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional

SCHEMA_ID = "tropo.publish-journal/v1"

# Journal location: one append-only file per vault, OUTSIDE the derived index.
# dev-spec R1: `.tropo/publish-journal/<vault_uid>.jsonl`.
JOURNAL_DIR_REL = Path(".tropo") / "publish-journal"

GENESIS_HASH = "0" * 64
_UID_RE = re.compile(r"^[0-9a-f]{8}$")

# ---------------------------------------------------------------------------
# The closed job state machine (cc437616 §7 / dev-spec §Write Contract). Two
# machines — SOURCE and DESTINATION — plus the recoverable `blocked` overlay.
# `landed` is ALWAYS per named destination (R2): one clone's pull cannot certify
# another. These are a CODE CONSTANT, not config, for the same reason the public
# scope allowlist in segment.py is frozen: widening the state space is a
# reviewable code change, never an edit-without-review.
# ---------------------------------------------------------------------------
SOURCE_STATES = frozenset({
    "planned", "validated", "awaiting-assent", "ready", "pushed",
    "remote-integrated", "awaiting-receipt", "landed", "landed-then-superseded",
})
DESTINATION_STATES = frozenset({
    "pending", "reconciling", "receipt-emitted", "landed-local",
    "superseded-before-reconcile",
})
BLOCKED = "blocked"
ALL_STATES = SOURCE_STATES | DESTINATION_STATES | {BLOCKED}

# Terminal states — no transition may leave them (except a landed job being
# superseded, which is itself a distinct terminal state recorded as a new row).
TERMINAL_STATES = frozenset({
    "landed", "landed-then-superseded", "landed-local",
    "superseded-before-reconcile",
})

# ---------------------------------------------------------------------------
# The CLOSED error enum (dev-spec §Write Contract / cc437616 §9). A `blocked`
# record MUST carry an `error` drawn from EXACTLY this set plus a typed
# `resumable_from`; an unknown code is a HARD FAILURE (A5), never coerced.
# ---------------------------------------------------------------------------
CLOSED_ERROR_ENUM = frozenset({
    "STALE_PLAN",
    "OVERLAPPING_CHANGESET",
    "POLICY_REFUSED",
    "PRIVACY_REFUSED",
    "CONFLICT",
    "REMOTE_CHECK_FAILED",
    "REMOTE_CAS_FAILED",
    "RECONCILE_FAILED",
    "RECEIPT_REF_FAILED",
    "RECEIPT_INVALID",
    "SUPERSEDED_BEFORE_RECONCILE",
    "GROUP_RESOLUTION_UNAVAILABLE",
})


class PublishJournalError(Exception):
    """Base class for all publish-journal refusals (typed, never silent)."""


class PublishJournalValidationError(PublishJournalError):
    """A record failed the closed state/enum contract before it was written."""


class PublishJournalCASError(PublishJournalError):
    """compare-and-swap lost: the tip moved under a concurrent writer."""


class PublishJournalCorruption(PublishJournalError):
    """The hash chain broke somewhere other than a tolerable torn tail."""


# ---------------------------------------------------------------------------
# Hashing + canonical serialization
# ---------------------------------------------------------------------------

def _canonical_payload(record: dict) -> str:
    """Deterministic serialization of everything EXCEPT record_hash. The chain
    binds this canonical form, so key order / whitespace can never change the
    hash for logically identical content."""
    payload = {k: v for k, v in record.items() if k != "record_hash"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_record_hash(record: dict) -> str:
    """record_hash = sha256(prev_hash || canonical(payload)). prev_hash lives
    inside the payload too, so recomputation both re-derives this record's hash
    AND proves its linkage to the prior record."""
    material = record["prev_hash"] + "\n" + _canonical_payload(record)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def path_set_hash(uid_or_path_set) -> str:
    """Stable identity for a job's (uid/path set) — the third component of the
    row key (vault_uid, destination, uid/path set) the overlay resolves on
    (dev-spec §Read Contract item 3). Order-independent: a set published as
    {a,b} is the same row as {b,a}."""
    items = sorted(str(x) for x in uid_or_path_set)
    blob = json.dumps(items, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def journal_path(vault_root: Path, vault_uid: str) -> Path:
    if not _UID_RE.match(str(vault_uid)):
        raise PublishJournalValidationError(
            f"vault_uid must be 8-hex; got {vault_uid!r}"
        )
    return vault_root / JOURNAL_DIR_REL / f"{vault_uid}.jsonl"


# ---------------------------------------------------------------------------
# Read (torn-tail-tolerant + chain-verifying)
# ---------------------------------------------------------------------------

def read_records(vault_root: Path, vault_uid: str) -> list[dict]:
    """Return the verified record list for a vault, dropping ONLY a trailing
    torn record. Any chain break that is NOT the final record raises
    PublishJournalCorruption — truncation is tolerable, tampering is not."""
    path = journal_path(vault_root, vault_uid)
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8")
    if raw == "":
        return []
    # A crash mid-append can leave a final line with no trailing newline. Split
    # so the incomplete tail is isolated as its own (droppable) element: a
    # trailing "" (file ended with "\n") is stripped; a trailing non-empty
    # fragment is kept as the last line so the torn-tail path below drops it.
    parts = raw.split("\n")
    lines = parts[:-1] if parts[-1] == "" else parts

    records: list[dict] = []
    prev_hash = GENESIS_HASH
    prev_seq = 0
    for idx, line in enumerate(lines):
        is_last = idx == len(lines) - 1
        try:
            rec = json.loads(line)
            if not isinstance(rec, dict):
                raise ValueError("record is not a JSON object")
            _shape_check(rec)
            if rec["prev_hash"] != prev_hash:
                raise ValueError("prev_hash does not chain to prior record")
            if compute_record_hash(rec) != rec["record_hash"]:
                raise ValueError("record_hash does not match content")
            if rec["seq"] != prev_seq + 1:
                raise ValueError("seq is not strictly monotonic +1")
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            if is_last:
                # Tolerate a broken FINAL record as a torn tail: a partial write
                # from a crash mid-append. Everything before it verified, so the
                # store resumes cleanly from the last intact record (R1). A break
                # anywhere but the tail is tampering, not truncation → hard fail.
                break
            raise PublishJournalCorruption(
                f"publish journal {path} corrupt at record {idx + 1}: {exc}"
            ) from exc
        records.append(rec)
        prev_hash = rec["record_hash"]
        prev_seq = rec["seq"]
    return records


def _shape_check(rec: dict) -> None:
    required = {"schema_id", "seq", "job_uid", "vault_uid", "destination",
                "path_set_hash", "state", "asOf", "prev_hash", "record_hash"}
    missing = required - rec.keys()
    if missing:
        raise ValueError(f"record missing fields {sorted(missing)}")
    if rec["schema_id"] != SCHEMA_ID:
        raise ValueError(f"unexpected schema_id {rec['schema_id']!r}")
    if rec["state"] not in ALL_STATES:
        raise ValueError(f"state {rec['state']!r} outside the closed state set")
    if rec["state"] == BLOCKED and rec.get("error") not in CLOSED_ERROR_ENUM:
        raise ValueError(f"blocked record error {rec.get('error')!r} outside closed enum")


def current_tip_hash(records: list[dict]) -> str:
    return records[-1]["record_hash"] if records else GENESIS_HASH


# ---------------------------------------------------------------------------
# Append (append-only + hash-chained + fsync + CAS + idempotent)
# ---------------------------------------------------------------------------

def append_transition(
    vault_root: Path,
    vault_uid: str,
    *,
    job_uid: str,
    changeset_uid: str,
    destination: Optional[str],
    path_set,
    state: str,
    actor: str,
    asof: str,
    error: Optional[str] = None,
    reason: Optional[str] = None,
    resumable_from: Optional[str] = None,
    expected_tip: Optional[str] = None,
) -> dict:
    """Append one transition. Validates the closed contract BEFORE any write,
    then appends under an exclusive flock with fsync. Idempotent: re-applying
    the transition already on the tip for this (job_uid, destination, path set)
    is a no-op that returns the existing record (process-loss resume, R1).

    `expected_tip`, when supplied, is the compare-and-swap guard: if the live
    tip hash differs (a concurrent writer advanced the journal), the append
    refuses with PublishJournalCASError rather than forking the chain.
    """
    # ---- closed-contract validation (A5: unknown code is a HARD FAILURE) ----
    if state not in ALL_STATES:
        raise PublishJournalValidationError(
            f"state {state!r} is outside the closed state set {sorted(ALL_STATES)}"
        )
    if state == BLOCKED:
        if error not in CLOSED_ERROR_ENUM:
            raise PublishJournalValidationError(
                f"blocked transition requires an error in the closed enum; "
                f"got {error!r} (unknown codes are a hard failure — A5/§9)"
            )
        if resumable_from is not None and resumable_from not in ALL_STATES:
            raise PublishJournalValidationError(
                f"resumable_from {resumable_from!r} must be a valid state or None"
            )
    else:
        if error is not None:
            raise PublishJournalValidationError(
                f"non-blocked transition to {state!r} must not carry an error "
                f"(errors only attach to blocked); got {error!r}"
            )
    if not _UID_RE.match(str(job_uid)):
        raise PublishJournalValidationError(f"job_uid must be 8-hex; got {job_uid!r}")

    key_path_hash = path_set_hash(path_set)
    path = journal_path(vault_root, vault_uid)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            records = read_records(vault_root, vault_uid)
            tip = current_tip_hash(records)

            # CAS: refuse a losing writer instead of forking the chain.
            if expected_tip is not None and expected_tip != tip:
                raise PublishJournalCASError(
                    f"CAS failed for vault {vault_uid}: expected tip "
                    f"{expected_tip[:12]}…, live tip {tip[:12]}… — re-read and retry"
                )

            # Idempotent resume: if the latest record for THIS row key already
            # records this exact transition, re-applying is a no-op (R1: process
            # loss at a transition resumes from evidence, never duplicates).
            latest = _latest_for_job(records, job_uid, destination, key_path_hash)
            if (latest is not None
                    and latest["state"] == state
                    and latest.get("error") == error
                    and latest.get("resumable_from") == resumable_from):
                return latest

            record = {
                "schema_id": SCHEMA_ID,
                "seq": (records[-1]["seq"] + 1) if records else 1,
                "job_uid": job_uid,
                "changeset_uid": changeset_uid,
                "vault_uid": vault_uid,
                "destination": destination,
                "path_set_hash": key_path_hash,
                "state": state,
                "error": error,
                "reason": reason,
                "resumable_from": resumable_from,
                "actor": actor,
                "asOf": asof,
                "prev_hash": tip,
            }
            record["record_hash"] = compute_record_hash(record)
            line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)

            # If a prior crash left a torn tail (or any trailing bytes past the
            # last intact record), compact the file to exactly the valid prefix
            # BEFORE appending — otherwise the new line would concatenate onto a
            # partial fragment and corrupt the fresh record. Re-serializing the
            # parsed records is byte-identical to what was written (fixed key
            # order + separators), so a CLEAN file needs no rewrite and the
            # common path stays a pure append.
            clean = "".join(
                json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n"
                for r in records
            ).encode("utf-8")
            handle.seek(0, os.SEEK_END)
            if handle.tell() != len(clean):
                handle.seek(0)
                handle.truncate(0)
                handle.write(clean.decode("utf-8"))
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            return record
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _latest_for_job(records, job_uid, destination, key_path_hash) -> Optional[dict]:
    for rec in reversed(records):
        if (rec["job_uid"] == job_uid
                and rec["destination"] == destination
                and rec["path_set_hash"] == key_path_hash):
            return rec
    return None


# ---------------------------------------------------------------------------
# Overlay resolution (the read side the API layer consumes)
# ---------------------------------------------------------------------------

def records_for_row(records, destination, path_set) -> list[dict]:
    """All records for a row key (destination, uid/path set), oldest→newest.
    History stays queryable; the overlay reads only the current one."""
    key_path_hash = path_set_hash(path_set)
    return [r for r in records
            if r["destination"] == destination and r["path_set_hash"] == key_path_hash]


def current_row_record(records, destination, path_set) -> Optional[dict]:
    """The CURRENT non-superseded overlay record for a row (dev-spec §Read
    Contract item 3): the latest transition by seq. Append-only ordering means
    a later `landed` naturally supersedes an older `blocked` — history remains
    queryable but an old blocked row cannot permanently dominate."""
    rows = records_for_row(records, destination, path_set)
    if not rows:
        return None
    return max(rows, key=lambda r: r["seq"])


def blocked_jobs(records) -> list[dict]:
    """Every row whose CURRENT overlay record is blocked — the durable
    blocked-job input to the studio-health surface (A8). Deduped by row key."""
    seen = {}
    for rec in records:
        key = (rec["destination"], rec["path_set_hash"])
        if key not in seen or rec["seq"] > seen[key]["seq"]:
            seen[key] = rec
    return [rec for rec in seen.values() if rec["state"] == BLOCKED]


__all__ = [
    "SCHEMA_ID", "JOURNAL_DIR_REL", "GENESIS_HASH",
    "SOURCE_STATES", "DESTINATION_STATES", "BLOCKED", "ALL_STATES",
    "TERMINAL_STATES", "CLOSED_ERROR_ENUM",
    "PublishJournalError", "PublishJournalValidationError",
    "PublishJournalCASError", "PublishJournalCorruption",
    "journal_path", "read_records", "current_tip_hash", "append_transition",
    "path_set_hash", "compute_record_hash",
    "records_for_row", "current_row_record", "blocked_jobs",
]
