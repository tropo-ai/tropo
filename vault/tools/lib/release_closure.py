"""AC8: the public receipt is the release-close commit point.

Publication is the one act this system cannot take back. Once a valid public
receipt exists, the release IS public, and the only honest question left is
whether our records have caught up. So closure is not a transaction that can
roll back -- it is a forward-only saga that must converge.

The shape follows from that (preflight §6):

    discover or write the one public receipt
    verify exactly one published event points at it
    journal the intent BEFORE the first closure mutation
    close plan, entry, activation, run, root
    release member reservations
    emit exactly one receipt-linked closure event
    mark the journal complete

The failure mode this is built around: a crash anywhere after the receipt must
leave the release **public but open**, never falsely closed. Public-but-open is
recoverable by rerunning; falsely-closed is a lie that no later step will
revisit, because nothing ever re-examines a closed release. Between an
incomplete record and a wrong one, the incomplete record is the one an operator
can act on.

Retry discovers the same receipt and the same transaction id and completes only
the steps that are missing. A conflicting receipt, or a post-state that
disagrees with the journal, refuses and preserves the evidence rather than
guessing which run was real.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

#: Machine-local recovery state, gitignored on purpose: one studio's in-flight
#: transaction is not another studio's substrate.
CLOSE_JOURNAL_DIR = Path(".tropo-studio") / "pipeline-close"

PUBLISHED_EVENT = "tropo.release.published"
CLOSED_EVENT = "tropo.release.closed"

#: The saga steps, in order. Named so the journal records progress in terms an
#: operator can read, rather than an index into a list that may be reordered.
STEPS = (
    "receipt_verified",
    "published_event_verified",
    "substrate_closed",
    "reservations_released",
    "closure_event_emitted",
)

_UID = re.compile(r"^[0-9a-f]{8}$")


class ClosureRefusal(Exception):
    """Closure cannot proceed and the evidence is preserved untouched.

    Distinct from a failure: a refusal means we found a contradiction and
    stopped on purpose. Nothing is cleaned up, because the contradiction is
    the most valuable thing on disk at that moment.
    """


@dataclass
class ClosureJournal:
    """What we intended, what we have done, and which release it belongs to."""

    release_run_uid: str
    receipt_sha256: str
    transaction_id: str
    completed: list = field(default_factory=list)
    state: str = "opened"

    def as_dict(self) -> dict:
        return {
            "release_run_uid": self.release_run_uid,
            "receipt_sha256": self.receipt_sha256,
            "transaction_id": self.transaction_id,
            "completed": list(self.completed),
            "state": self.state,
        }

    def remaining(self) -> list:
        return [step for step in STEPS if step not in self.completed]

    def is_complete(self) -> bool:
        return not self.remaining()


def _event_type(event) -> str:
    """Run JSONL spells it `event`; vault streams spell it `type`."""
    if not isinstance(event, dict):
        return ""
    return str(event.get("event") or event.get("type") or "")


def journal_path(vault_root: Path, release_run_uid: str) -> Path:
    return Path(vault_root) / CLOSE_JOURNAL_DIR / f"release-{release_run_uid}.json"


def read_journal(vault_root: Path, release_run_uid: str) -> Optional[ClosureJournal]:
    path = journal_path(vault_root, release_run_uid)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ClosureRefusal(
            f"closure journal at {path} is unreadable ({exc}). Refusing rather "
            f"than starting a fresh close over a release that may already be "
            f"half closed."
        ) from exc
    return ClosureJournal(
        release_run_uid=str(raw.get("release_run_uid") or ""),
        receipt_sha256=str(raw.get("receipt_sha256") or ""),
        transaction_id=str(raw.get("transaction_id") or ""),
        completed=list(raw.get("completed") or []),
        state=str(raw.get("state") or "opened"),
    )


def open_or_resume_journal(
    vault_root: Path,
    release_run_uid: str,
    receipt_sha256: str,
    transaction_id: str,
) -> ClosureJournal:
    """Write the intent before the first mutation, or resume the existing one.

    A close that writes several records is a transaction, and a transaction
    with no journal has no recovery -- it has an operator guessing which half
    happened.

    Resuming refuses on any disagreement. A journal for this run naming a
    different receipt means two publications are in play, and picking either
    one would be a guess dressed as a decision.
    """
    if not _UID.match(release_run_uid or ""):
        raise ClosureRefusal(f"{release_run_uid!r} is not a governed run uid")

    existing = read_journal(vault_root, release_run_uid)
    if existing is not None:
        if existing.receipt_sha256 != receipt_sha256:
            raise ClosureRefusal(
                f"run {release_run_uid} already has an open closure for "
                f"receipt {existing.receipt_sha256[:12]}, and this one is for "
                f"{receipt_sha256[:12]}. Two receipts for one release run is a "
                f"contradiction, not a retry; the journal is left untouched."
            )
        if existing.transaction_id != transaction_id:
            raise ClosureRefusal(
                f"run {release_run_uid} has an open closure under transaction "
                f"{existing.transaction_id!r}, not {transaction_id!r}. A retry "
                f"reuses its transaction id; a new one means a second closure "
                f"is being attempted while the first is unfinished."
            )
        return existing

    journal = ClosureJournal(
        release_run_uid=release_run_uid,
        receipt_sha256=receipt_sha256,
        transaction_id=transaction_id,
    )
    _write_journal(vault_root, journal)
    return journal


def _write_journal(vault_root: Path, journal: ClosureJournal) -> Path:
    path = journal_path(vault_root, journal.release_run_uid)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(journal.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise ClosureRefusal(
            f"cannot write the closure journal at {path} ({exc}). Without it a "
            f"crash midway leaves no way to tell which half happened, and the "
            f"release is already public."
        ) from exc
    return path


def record_step(vault_root: Path, journal: ClosureJournal, step: str,
                verify: Optional[Callable[[], bool]] = None) -> ClosureJournal:
    """Mark one saga step done — only if the world agrees it happened.

    `verify` is required and must read the world back. This is not a gate on
    anyone's work; it is a gate on MINE, and it exists because I wrote this
    same bug four times in two days: reservations recorded as released without
    releasing them, substrate recorded as closed over a hook that closed one
    record of five, a closure event journalled with no emitter behind it, and
    a mount marked ADOPTED over a file with no sidecar.

    Every instance had the identical shape — the code path completed, so the
    step got marked — and no amount of resolving to be careful caught it. What
    catches it is making the claim unrepresentable without the read-back: you
    cannot say a step is done without handing over the function that proves it.

    Persisted per step rather than at the end, because the point is surviving
    a crash between two steps.
    """
    if step not in STEPS:
        raise ClosureRefusal(f"{step!r} is not a closure step")
    if verify is None:
        raise ClosureRefusal(
            f"recording {step!r} requires a verifier that reads the world back. "
            f"Four separate times this saga has recorded a step because its "
            f"code path finished rather than because its effect landed."
        )
    if not verify():
        raise ClosureRefusal(
            f"{step!r} did not take effect: the verifier read the world back "
            f"and it is not in the state this step claims. The release is "
            f"public and the journal records how far this got, which is the "
            f"recoverable state."
        )
    if step not in journal.completed:
        journal.completed.append(step)
    if journal.is_complete():
        journal.state = "complete"
    _write_journal(vault_root, journal)
    return journal


def assert_one_published_event(events: Iterable[dict], receipt_sha256: str) -> dict:
    """P13: exactly one published event, and it points at this receipt.

    Zero means the outward act is unproven and closure would be recording a
    publication nobody can evidence. Two means the release was fired twice and
    we cannot say which artefact the second one carried.
    """
    matches = [
        event for event in (events or [])
        if _event_type(event) == PUBLISHED_EVENT
        and str((event.get("data") or {}).get("receipt_sha256") or "") == receipt_sha256
    ]
    if not matches:
        raise ClosureRefusal(
            f"no {PUBLISHED_EVENT} event points at receipt "
            f"{receipt_sha256[:12]}. Closure records that a publication "
            f"happened; without that event there is nothing to record."
        )
    if len(matches) > 1:
        raise ClosureRefusal(
            f"{len(matches)} {PUBLISHED_EVENT} events point at receipt "
            f"{receipt_sha256[:12]}. Exactly one publication per receipt: two "
            f"means the release fired twice and this cannot say which."
        )
    return matches[0]


def resume_point(journal: Optional[ClosureJournal]) -> list:
    """Which steps a retry still owes, in order.

    A retry completes only what is missing. Re-running a completed step is not
    harmless here: re-emitting the closure event or re-releasing reservations
    would each produce a second record of a thing that happened once.
    """
    if journal is None:
        return list(STEPS)
    return journal.remaining()
