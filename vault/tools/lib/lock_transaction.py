"""One atomic lock transaction, used by both ignitions of the two-pipeline split.

0a0a6777 §2: "Dev-spec lock is the only dev ignition and writes the complete
snapshot transaction. Release-plan lock is the symmetric release ignition."

The two locks are a symmetric PAIR in the locked spec, so they get one mechanism
rather than two that drift. AC2 asks the dev lock for "one activation/root plus
one pipeline-run/run-folder containing immutable hashes"; AC4 asks the release
lock to "atomically reserve every member and open one immutable release run".
Different payloads, identical transactional shape:

    plan  -> a complete, PURE description of every byte to be written
    apply -> journal the whole plan, then write it, then verify

WHY THE PLAN IS PURE, AND WHY THAT IS THE WHOLE DESIGN
------------------------------------------------------
Both ACs require that malformed, duplicate, and partial-write cases "leave zero
partial state". Those are three different failures and only the third is a
crash:

  malformed / duplicate — a precondition is false. The plan phase touches no
      disk, so refusing here cannot leave partial state. This is structural,
      not diligent: there is no write to forget to undo, because the code that
      could write has not run.

  partial write — the disk failed mid-apply. This is the only case that needs
      recovery, and it is the only case that gets a journal.

A design that validated as-it-wrote would need every refusal path to remember to
unwind, and "leaves zero partial state" would be a property of the author's
attention rather than of the program. Two phases make it a property of the
shape.

WHY PATCHES CARRY THE PRE-STATE HASH
------------------------------------
An in-place edit is planned against bytes read at plan time and applied later.
If anything changed in between, applying the patch would silently overwrite a
write this transaction never saw. Each patch therefore records the SHA-256 of
the bytes it was planned against and re-checks it at apply time. Same lesson as
the index-surface memo (talos-t40, 2026-08-08): a key that IS the content cannot
be stale, while a key that merely stands for it can.

WARN-SAFE AUDIT (deb77758, requested by argus-a147)
---------------------------------------------------
Each refusal here priced against Mike's rule — name the irreversible harm or
demote to a warning:

  lock contention      duplicate reservation; two live releases claiming one
                       piece of work, unrecoverable once either publishes
  target exists        would overwrite a governed entry — deletion of governed
                       substrate, which deb77758 lists explicitly
  patch pre-state moved  would destroy a concurrent write the transaction never
                       saw, and the lost bytes are not recoverable
  path escape/symlink  damages substrate outside the workspace, which the
                       rollback has no knowledge of and cannot restore
  duplicate target     the transaction has no single outcome, so what landed is
                       unknowable afterwards
  applied outside lock the reservation decision and the commit could straddle
                       another ignition; same harm as contention
  unreadable pre-state a patch whose previous bytes cannot be journaled cannot
                       be rolled back, so the transaction stops being atomic

Deliberately NOT refusals: a rollback that cannot recycle leaves the entry and
reports (Principle 13 — escalating to unlink is the harm, not the cure), and a
divergent file during replay stops and reports rather than guessing.

ROLLBACK AND PRINCIPLE 13
-------------------------
Governed `vault/files/*.md` entries are NEVER hard-deleted, including by a
rollback (Principle 13 / 0aefe71d; the A82 and 2774e472 silent-deletion defects
came from exactly that shortcut). Undoing a created governed entry means
recycling it. Everything else this transaction creates — run folders, manifests
— is machine-written scaffolding and is removed outright. A rollback that cannot
recycle leaves the entry in place and says so, rather than escalating to unlink.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

VAULT_ROOT = Path(__file__).resolve().parents[3]
VAULT_FILES = VAULT_ROOT / "vault" / "files"

#: Local, gitignored journal boundary. Machine-local recovery state, never
#: substrate — shipping one studio's in-flight transaction to another is the
#: defect class the package state-exclusion rule exists for.
LOCK_JOURNAL_DIR = VAULT_ROOT / ".tropo-studio" / "lock-transactions"

#: One exclusive lock for the whole ignition critical section. Ignitions are
#: rare and short, so a single workspace-wide lock costs nothing and removes the
#: entire class of interleaving between the reservation re-scan and the commit.
WORKSPACE_LOCK_PATH = LOCK_JOURNAL_DIR / "ignition.lock"


class LockRefusal(Exception):
    """A precondition is false. Raised only from the plan phase, so no write
    has happened and none needs undoing."""


class LockContention(LockRefusal):
    """Another ignition holds the workspace lock. Exactly one winner."""


#: Set while the workspace lock is held, so `apply_plan` can refuse to commit
#: outside the span rather than trusting every caller to remember.
_LOCK_DEPTH = 0

#: Identity of the CURRENT acquisition, not merely of the lock. Regenerated on
#: every acquire so that two spans in the same process are distinguishable.
#:
#: WHY A TOKEN AND NOT JUST A DEPTH COUNTER (argus-a147, NO-GO item 1). A plan is
#: built from reads taken under one acquisition and applied later. If the lock is
#: released and retaken in between — a retry, an exception handler, a caller that
#: helpfully wraps a second span — the depth counter is positive again and the
#: stale plan applies against a world it never observed. The token makes "the
#: span I was planned under" a fact the plan carries rather than an assumption
#: about control flow.
_LOCK_TOKEN: "str | None" = None


def _holding_workspace_lock() -> bool:
    return _LOCK_DEPTH > 0


def current_lock_token() -> "str | None":
    return _LOCK_TOKEN


@contextmanager
def exclusive_workspace_lock(timeout_s: float = 0.0, path: Optional[Path] = None):
    """Hold one exclusive lock across re-scan, plan, journal, and commit.

    WHY THE WHOLE SPAN AND NOT JUST THE WRITE (argus-a147 NO-GO item 1). The
    reservation gate reads every release-plan, decides no rival holds a member,
    and only then writes. Two processes interleaved between that read and that
    write both see an unclaimed member and both claim it — the check passes
    twice and the invariant it exists to keep is broken. A lock around only the
    write would not help: both would still have decided on stale reads.

    Non-blocking by default so contention is an immediate, legible refusal
    rather than a hang. Fail-closed, harm named (deb77758): a duplicate
    reservation means two live releases each attesting to the same work, which
    is not reversible once either publishes.
    """
    lock_path = path or WORKSPACE_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    deadline = _monotonic() + max(0.0, timeout_s)
    try:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if _monotonic() >= deadline:
                    raise LockContention(
                        f"another ignition holds {lock_path}. Exactly one lock "
                        "transaction may run at a time: two would each re-scan "
                        "reservations before the other committed, and both would "
                        "see the same member as unclaimed. Retry when it finishes."
                    ) from exc
                _sleep(0.05)
        global _LOCK_DEPTH, _LOCK_TOKEN
        outermost = _LOCK_DEPTH == 0
        previous_token = _LOCK_TOKEN
        if outermost:
            _LOCK_TOKEN = f"{os.getpid()}-{_monotonic():.6f}-{os.urandom(6).hex()}"
            os.ftruncate(handle, 0)
            os.lseek(handle, 0, os.SEEK_SET)
            os.write(handle, _LOCK_TOKEN.encode("utf-8"))
        _LOCK_DEPTH += 1
        try:
            yield lock_path
        finally:
            _LOCK_DEPTH -= 1
            if outermost:
                _LOCK_TOKEN = previous_token
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            os.close(handle)


def _monotonic() -> float:
    import time

    return time.monotonic()


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


class LockApplyFailure(Exception):
    """A write failed after the journal was committed. Carries what was undone
    and what could not be, because an operator's next move depends on both."""

    def __init__(self, message: str, undone: list[str], stranded: list[str]):
        super().__init__(message)
        self.undone = undone
        self.stranded = stranded


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


@dataclass(frozen=True)
class CreateFile:
    """Write a file that does not exist yet."""

    path: Path
    content: str
    governed: bool = False  # a vault/files entry: recycle on undo, never unlink

    def describe(self, *, reconstructable: bool = False) -> dict:
        """`reconstructable` carries the bytes, for the journal only.

        The plan DIGEST is computed from the hash-only form so that an
        idempotence comparison stays cheap and stable; the JOURNAL needs the
        actual content, because a journal of hashes can tell you that something
        went wrong and not one thing about how to put it back (argus-a147 NO-GO
        item 2).
        """
        body = {
            "op": "create",
            "path": str(self.path),
            "sha256": sha256_text(self.content),
            "governed": self.governed,
        }
        if reconstructable:
            body["post_content"] = self.content
            body["pre_existed"] = False
        return body


@dataclass(frozen=True)
class PatchFile:
    """Replace a file's whole contents, guarded by the bytes it was planned against."""

    path: Path
    expected_sha256: str
    content: str

    def describe(self, *, reconstructable: bool = False) -> dict:
        body = {
            "op": "patch",
            "path": str(self.path),
            "expected_sha256": self.expected_sha256,
            "sha256": sha256_text(self.content),
        }
        if reconstructable:
            # Read at journal time, immediately after the pre-patch recheck, so
            # the bytes recorded are the bytes that will be replaced.
            try:
                body["pre_content"] = self.path.read_text(encoding="utf-8")
            except OSError as exc:
                raise LockRefusal(
                    f"cannot read {self.path} to journal its pre-state ({exc}); "
                    "a patch whose previous content cannot be recorded is a patch "
                    "that cannot be rolled back"
                ) from exc
            body["post_content"] = self.content
            body["pre_existed"] = True
        return body


@dataclass
class LockPlan:
    """Every byte this transaction will write, decided before any of it is written."""

    kind: str  # "dev-spec-lock" | "release-plan-lock"
    subject_uid: str  # the dev-spec or release-plan being locked
    actor: str
    operations: list = field(default_factory=list)
    notes: dict = field(default_factory=dict)
    #: The acquisition this plan's reads were taken under. Captured at
    #: construction, checked at apply. A plan built under a different span is
    #: refused rather than applied against a world it never observed.
    #:
    #: PRIVATE AND READ-ONLY (argus-a147 residual 2). Removing the named
    #: `bind_to_current_acquisition()` helper was not enough: while the field was
    #: a public writable attribute, `plan.lock_token = current_lock_token()`
    #: under a later acquisition laundered a stale plan just as effectively, and
    #: with less to notice in review. The witness is now written once at
    #: construction and refuses reassignment.
    _lock_token: "str | None" = field(default_factory=current_lock_token, repr=False)

    @property
    def lock_token(self) -> "str | None":
        return self._lock_token

    def __setattr__(self, name, value):
        if name == "lock_token":
            raise LockRefusal(
                "LockPlan.lock_token is read-only. It witnesses the acquisition "
                "this plan's reads were taken under, and reassigning it would "
                "launder a stale plan into a later span without re-reading "
                "anything. Build the plan inside the span instead."
            )
        if name == "_lock_token" and getattr(self, "_sealed", False):
            raise LockRefusal(
                "the acquisition witness is sealed. It is written once, at "
                "construction, from the span that was open then. Assigning it "
                "afterwards — through the public name or the private one — is "
                "laundering a plan into an acquisition whose world it never read."
            )
        object.__setattr__(self, name, value)

    def __post_init__(self) -> None:
        # Seal AFTER the dataclass has finished assigning fields, so the witness
        # captured at construction is the only one this plan will ever carry.
        object.__setattr__(self, "_sealed", True)

    def create(self, path: Path, content: str, governed: bool = False) -> None:
        self.operations.append(CreateFile(path, content, governed))

    def patch(self, path: Path, original: str, content: str) -> None:
        self.operations.append(PatchFile(path, sha256_text(original), content))

    def describe(self, *, reconstructable: bool = False) -> dict:
        return {
            "kind": self.kind,
            "subject_uid": self.subject_uid,
            "actor": self.actor,
            "planned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "operations": [op.describe(reconstructable=reconstructable)
                           for op in self.operations],
            "notes": self.notes,
        }

    def digest(self) -> str:
        """A stable digest of the plan's effects, excluding the wall clock.

        Timestamps would make two identical plans hash differently, and the
        question this answers is "is this the same transaction", not "was it
        prepared at the same instant".
        """
        payload = {
            "kind": self.kind,
            "subject_uid": self.subject_uid,
            "operations": [op.describe() for op in self.operations],
        }
        return sha256_text(json.dumps(payload, sort_keys=True))


def _assert_inside_workspace(path: Path) -> None:
    """Refuse a target outside the studio, or reached through a symlink.

    Fail-closed, harm named (deb77758): a write that escapes the workspace, or
    that follows a symlink out of it, damages substrate the studio does not
    govern and cannot roll back — the rollback path only knows about paths
    inside the plan.

    Checked WITHOUT resolving the final component, so planting a symlink at the
    destination is caught rather than quietly followed to wherever it points.
    """
    parent = path.parent
    try:
        resolved_parent = parent.resolve(strict=False)
        root = VAULT_ROOT.resolve(strict=False)
    except OSError as exc:
        raise LockRefusal(f"cannot resolve {parent} to check containment: {exc}") from exc

    if root not in resolved_parent.parents and resolved_parent != root:
        raise LockRefusal(
            f"{path} resolves outside the studio ({resolved_parent}). A lock "
            "transaction writes only inside the workspace it can roll back."
        )
    if path.is_symlink():
        raise LockRefusal(
            f"{path} is a symlink. Writing through it would modify a target the "
            "plan never named and the rollback cannot restore."
        )


def _preflight(plan: LockPlan) -> None:
    """Every reason to refuse, checked while refusing is still free.

    Runs immediately before the journal, over the plan as a whole, so a
    conflict in the last operation stops the first one from being written.
    """
    seen: set[Path] = set()
    for op in plan.operations:
        _assert_inside_workspace(op.path)
        # Canonicalise the PARENT before duplicate detection, so two spellings
        # of one destination — `a/b.md` and `a/./b.md`, or a path reached through
        # a symlinked directory inside the workspace — are recognised as the same
        # target. Comparing raw Paths let an alias pair through as two distinct
        # writes, and the transaction would then have no single outcome for that
        # file (argus-a147 NO-GO item 6).
        canonical = op.path.parent.resolve(strict=False) / op.path.name
        if canonical in seen:
            raise LockRefusal(
                f"plan writes {op.path} twice (canonically {canonical}); a "
                "transaction that contradicts itself has no single outcome to apply"
            )
        seen.add(canonical)

        if isinstance(op, CreateFile):
            if op.path.exists():
                raise LockRefusal(
                    f"{op.path} already exists; a lock that would overwrite an "
                    "existing entry is a duplicate lock, not a new one"
                )
        else:
            if not op.path.is_file():
                raise LockRefusal(f"{op.path} was planned as a patch but does not exist")
            actual = sha256_bytes(op.path.read_bytes())
            if actual != op.expected_sha256:
                raise LockRefusal(
                    f"{op.path} changed after this lock was planned "
                    f"(planned against {op.expected_sha256[:12]}, found "
                    f"{actual[:12]}). Re-plan; applying would overwrite a write "
                    "this transaction never saw."
                )


def _write_journal(plan: LockPlan) -> Path:
    """Commit the intent before the first byte of the effect.

    A multi-file lock with no journal has no recovery, only an operator
    guessing which half happened.
    """
    path = LOCK_JOURNAL_DIR / f"{plan.kind}-{plan.subject_uid}.json"
    body = dict(plan.describe(reconstructable=True),
                plan_digest=plan.digest(), state="applying")
    # Deliberately the SAME writer the effects use. It had its own temp+rename
    # copy until 2026-08-10, which was not a bug but did mean the ordering
    # guarantee had two implementations and only one of them could be observed
    # at a single instrumentation point — the test that asserts "journal before
    # effect" could not actually see the journal.
    _atomic_write(path, json.dumps(body, indent=2, sort_keys=True) + "\n")
    return path


def recover_incomplete(journal_dir: Optional[Path] = None,
                       recycle: "Callable[[Path, str], bool] | None | str" = "default",
                       ) -> list[dict]:
    """Roll back any transaction that was applying when the process died.

    NO-GO item 2: a journal you cannot replay is a diagnostic, not a recovery.
    Because the journal carries pre- and post-content for every operation, a
    crash at ANY point is recoverable by comparing what is on disk to what the
    journal says was intended:

      file matches post_content  -> that write landed; undo it
      file matches pre_content   -> it never landed; leave it
      file matches neither       -> somebody else has touched it since; STOP and
                                    report, because guessing here is how a
                                    recovery becomes the corruption

    Returns one report per journal handled.
    """
    # Resolved here rather than as a default argument: _default_recycle is
    # defined further down, and a def-time default would fail at import.
    if recycle == "default":
        recycle = _default_recycle
    directory = journal_dir or LOCK_JOURNAL_DIR
    reports: list[dict] = []
    if not directory.is_dir():
        return reports

    for path in sorted(directory.glob("*.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            reports.append({"journal": str(path), "outcome": "unreadable", "error": str(exc)})
            continue
        if body.get("state") != "applying":
            continue

        # CLASSIFY EVERYTHING BEFORE MUTATING ANYTHING (argus-a147 NO-GO item 2).
        # The first version decided and acted per operation as it walked. So a
        # divergence discovered at operation five happened AFTER four had already
        # been rolled back — a partial recovery, which is a third state nobody
        # asked for and which the report then described as "needs-operator"
        # without saying that half the undo had already run.
        plan_ok, classified, problems = _classify_journal(body)
        if not plan_ok:
            _finish_journal(path, "needs-operator", {"refused": problems})
            reports.append({"journal": str(path), "outcome": "needs-operator",
                            "recovered": [], "untouched": [], "diverged": problems})
            continue

        undone, left = [], []
        for action, target, payload, governed in classified:
            if action == "restore":
                _atomic_write(target, payload)
                undone.append(str(target))
            elif action == "remove":
                if governed:
                    # Principle 13 holds in recovery too. A governed entry is
                    # recycled; if that fails it STAYS and is reported, because a
                    # recovery that hard-deletes governed substrate is worse than
                    # the crash it is cleaning up after.
                    if recycle is not None and recycle(target, "lock transaction recovery"):
                        undone.append(str(target))
                    else:
                        left.append(f"{target} (governed; recycle unavailable — left in place)")
                else:
                    target.unlink()
                    _remove_if_empty(target.parent)
                    undone.append(str(target))
            else:
                left.append(str(target))

        _finish_journal(path, "rolled-back", {"recovered": undone, "untouched": left})
        reports.append({"journal": str(path), "outcome": "rolled-back",
                        "recovered": undone, "untouched": left, "diverged": []})
    return reports


def journal_plan_digest(body: dict) -> str:
    """Recompute a journal's plan digest from its own immutable fields.

    Must produce the same value as `LockPlan.digest()` for the plan that wrote
    it, so recovery can compare rather than assume. Computed over the fields
    that identify the transaction and its EFFECTS — kind, subject, and each
    operation's op/path/hashes — and deliberately NOT over the recorded content
    bodies or timestamps: content is validated separately against those hashes,
    and folding the clock in would make the digest unreproducible.
    """
    operations = []
    for op in body.get("operations", []):
        if not isinstance(op, dict):
            continue
        entry = {"op": op.get("op"), "path": op.get("path"),
                 "sha256": op.get("sha256")}
        if op.get("op") == "create":
            entry["governed"] = bool(op.get("governed"))
        else:
            entry["expected_sha256"] = op.get("expected_sha256")
        operations.append(entry)
    payload = {
        "kind": body.get("kind"),
        "subject_uid": body.get("subject_uid"),
        "operations": operations,
    }
    return sha256_text(json.dumps(payload, sort_keys=True))


def _classify_journal(body: dict) -> "tuple[bool, list, list]":
    """Decide every operation's disposition before any of them is acted on.

    Returns (safe_to_proceed, actions, problems). Any single problem means the
    whole journal is refused with ZERO mutation: a recovery that fixes the
    operations it understood and stops at the one it did not has invented a new
    partial state on top of the one it was called to resolve.

    Validates identity as well as content — the journal's own subject, and that
    every path is inside the workspace and is not a symlink — because a journal
    is a file on disk and a malicious or corrupted one would otherwise be a
    write primitive pointed wherever it likes.
    """
    problems: list = []
    actions: list = []

    if not isinstance(body.get("subject_uid"), str) or not body.get("kind"):
        problems.append("journal has no subject_uid/kind; it cannot be trusted to "
                        "describe a transaction")

    # STRICT SCHEMA AND DIGEST VALIDATION (blocker 2). Replay previously trusted
    # `pre_content` and the recorded hashes as given. A journal is a file on
    # disk: if its recorded content does not hash to its recorded digest, the
    # journal itself is corrupt, and restoring from it would write bytes nobody
    # ever committed while reporting a successful recovery.
    recorded_digest = body.get("plan_digest")
    if not isinstance(recorded_digest, str) or len(recorded_digest) != 64:
        problems.append("journal has no 64-hex plan_digest; it cannot be shown to "
                        "describe the transaction it claims to")
    else:
        # RECOMPUTE, do not merely shape-check (argus-a147). Accepting any
        # 64-character string checks that a digest is PRESENT, which is a
        # statement about formatting. An attacker or a corruption that rewrites
        # an operation and leaves the digest alone passes a shape check
        # trivially — the digest exists precisely so that the journal's contents
        # can be compared against it, and not doing the comparison makes it
        # decoration.
        actual = journal_plan_digest(body)
        if actual != recorded_digest:
            problems.append(
                f"journal plan_digest {recorded_digest[:12]}... does not match the "
                f"digest recomputed from its own operations ({actual[:12]}...). "
                "The journal has been altered since it was written, so nothing in "
                "it can be trusted to describe what happened.")
    for index, op in enumerate(body.get("operations", [])):
        if not isinstance(op, dict) or op.get("op") not in {"create", "patch"}:
            problems.append(f"operation {index} has an unknown shape: {op!r}")
            continue
        recorded = op.get("sha256")
        post = op.get("post_content")
        if post is not None and isinstance(recorded, str):
            if sha256_text(post) != recorded:
                problems.append(
                    f"operation {index} ({op.get('path')}): journalled post_content "
                    "does not hash to its recorded sha256; the journal is corrupt")
        expected_pre = op.get("expected_sha256")
        pre = op.get("pre_content")
        if pre is not None and isinstance(expected_pre, str):
            if sha256_text(pre) != expected_pre:
                problems.append(
                    f"operation {index} ({op.get('path')}): journalled pre_content "
                    "does not hash to its recorded expected_sha256; restoring it "
                    "would write bytes nobody committed")

    for op in reversed(body.get("operations", [])):
        raw_path = op.get("path")
        if not isinstance(raw_path, str):
            problems.append(f"operation has a non-string path: {raw_path!r}")
            continue
        target = Path(raw_path)

        try:
            _assert_inside_workspace(target)
        except LockRefusal as exc:
            problems.append(f"{target}: {exc}")
            continue

        if "post_content" not in op:
            problems.append(f"{target}: journal predates reconstructable effects; "
                            "it records hashes only and cannot be replayed")
            continue

        current = target.read_text(encoding="utf-8") if target.is_file() else None
        post, pre = op.get("post_content"), op.get("pre_content")

        if current is None:
            actions.append(("leave", target, None, op.get("governed", False)))
        elif current == post and op.get("pre_existed"):
            actions.append(("restore", target, pre, op.get("governed", False)))
        elif current == post:
            actions.append(("remove", target, None, op.get("governed", False)))
        elif current == pre:
            actions.append(("leave", target, None, op.get("governed", False)))
        else:
            problems.append(
                f"{target} matches neither the journalled pre- nor post-state; "
                "something has touched it since the crash and guessing here is "
                "how a recovery becomes the corruption")

    return (not problems), actions, problems


def _assert_not_symlink_now(path: Path) -> None:
    """Re-check at WRITE time, not only in preflight (argus-a147 NO-GO item 6).

    Preflight runs once over the whole plan; the writes happen afterwards. That
    gap is a TOCTOU window: a symlink planted at a target after preflight and
    before its write would be followed, and the transaction would modify a file
    it never named and cannot roll back. Checking again immediately before each
    write does not close the window to zero — nothing short of an atomic
    open-with-O_NOFOLLOW does — which is why the rename below also uses
    O_NOFOLLOW on the destination directory handle.
    """
    if path.is_symlink():
        raise LockRefusal(
            f"{path} became a symlink between preflight and write. Following it "
            "would modify a target the plan never named and the rollback cannot "
            "restore."
        )


class PossiblyApplied(Exception):
    """The rename may or may not have reached the disk.

    argus-a147, blocker 2: a post-rename directory fsync failure was being
    swallowed into the ordinary failure path, which then reported the
    transaction ROLLED BACK. That is the one report an operator will act on and
    the one we cannot substantiate — the rename very likely landed. "I do not
    know" is a third outcome and must be said out loud.
    """

    def __init__(self, path: Path, cause: BaseException):
        super().__init__(
            f"{path} was renamed into place but its directory fsync failed "
            f"({cause}). The write is POSSIBLY APPLIED: it may or may not have "
            "reached the disk, and reporting either 'applied' or 'rolled back' "
            "would state something unverified. Recover from the journal."
        )
        self.path = path
        self.cause = cause


def _open_dir_nofollow(directory: Path) -> int:
    """A directory handle opened without following a final symlink.

    Root-anchored, no-follow (blocker 2). Checking `is_symlink()` before writing
    leaves a window; opening the PARENT with O_NOFOLLOW and writing relative to
    that descriptor closes it, because the handle refers to the directory that
    existed at open time no matter what is swapped in afterwards.
    """
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(str(directory), flags)
    except OSError as exc:
        raise LockRefusal(
            f"cannot open {directory} as a real directory without following a "
            f"symlink ({exc}). A parent swapped for a link would redirect this "
            "write outside the plan."
        ) from exc


def _atomic_write(path: Path, content: str) -> None:
    """Write via temp-file + rename, anchored to a no-follow parent handle.

    The parent is opened once with O_NOFOLLOW and every subsequent step — create,
    write, fsync, rename — happens relative to that descriptor. A symlink swapped
    into the parent path after the open cannot redirect anything, because the
    descriptor already names the directory.
    """
    _assert_not_symlink_now(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dir_fd = _open_dir_nofollow(path.parent)
    tmp_name = f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp"
    try:
        fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644,
                     dir_fd=dir_fd)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            os.unlink(tmp_name, dir_fd=dir_fd)
            raise

        os.rename(tmp_name, path.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)

        # After this point the effect may be on disk. A failure here is NOT a
        # clean failure and must never be reported as a rollback.
        try:
            os.fsync(dir_fd)
        except OSError as exc:
            raise PossiblyApplied(path, exc) from exc
    finally:
        os.close(dir_fd)


def _remove_if_empty(directory: Path) -> None:
    """Drop a directory the transaction created and then emptied.

    Blocker 2: rollback removed files and left their run folders behind, so an
    "undone" transaction still showed a run folder on disk — enough to make a
    later reader believe a run existed. Only removes directories that are
    genuinely empty and inside the workspace, and never climbs past the root.
    """
    try:
        _assert_inside_workspace(directory / "_")
    except LockRefusal:
        return
    current = directory
    while current != VAULT_ROOT and current.is_dir():
        try:
            next(current.iterdir())
            return  # not empty; stop
        except StopIteration:
            pass
        except OSError:
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _undo(applied: list[tuple], recycle: Optional[Callable[[Path, str], bool]]) -> tuple[list[str], list[str]]:
    """Reverse what was applied, newest first. Returns (undone, stranded)."""
    undone: list[str] = []
    stranded: list[str] = []
    for op, previous in reversed(applied):
        try:
            if isinstance(op, PatchFile):
                _atomic_write(op.path, previous)
                undone.append(str(op.path))
            elif op.governed:
                # Principle 13: recycle, never unlink. If recycling fails the
                # entry STAYS — a rollback must not become the deletion the
                # discipline exists to prevent.
                if recycle is not None and recycle(op.path, "lock transaction rollback"):
                    undone.append(str(op.path))
                else:
                    stranded.append(str(op.path))
            else:
                if op.path.is_dir():
                    shutil.rmtree(op.path)
                else:
                    op.path.unlink(missing_ok=True)
                    _remove_if_empty(op.path.parent)
                undone.append(str(op.path))
        except OSError as exc:
            stranded.append(f"{op.path}: {exc}")
    return undone, stranded


def _default_recycle(path: Path, reason: str) -> bool:
    # vault/tools, NOT .tropo/scripts. It was the latter until 2026-08-10, which
    # meant `is_file()` was always False and rollback NEVER recycled — every
    # governed entry silently took the "stranded" branch. The Principle 13
    # behaviour was correct (nothing was hard-deleted) and the recovery was
    # dead, which is the worst kind of passing test: the safety property held
    # for the wrong reason. Caught by argus-a147's independent review, not by my
    # tests, because my tests injected a fake recycle and never exercised this.
    script = VAULT_ROOT / "vault" / "tools" / "tropo-recycle.py"
    if not script.is_file():
        return False
    result = subprocess.run(
        [sys.executable, str(script), path.stem, "--reason", reason],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def apply_plan(
    plan: LockPlan,
    recycle: Optional[Callable[[Path, str], bool]] = _default_recycle,
) -> Path:
    """Journal the plan, then write it. Returns the journal path.

    Refusals (LockRefusal) happen before the journal and write nothing. A write
    failure after the journal unwinds what landed and raises LockApplyFailure
    naming anything it could not unwind, because "partially rolled back" is a
    third outcome and must not be reported as either success or clean failure.
    """
    if not _holding_workspace_lock():
        raise LockRefusal(
            "apply_plan called without the workspace lock held. The reservation "
            "re-scan and this commit must sit inside one exclusive span, or two "
            "ignitions can each decide a member is unclaimed. Wrap the whole "
            "gather-plan-apply sequence in exclusive_workspace_lock()."
        )
    if plan.lock_token != _LOCK_TOKEN:
        raise LockRefusal(
            f"this plan was built under lock acquisition {plan.lock_token!r} but "
            f"the current acquisition is {_LOCK_TOKEN!r}. The lock was released "
            "and retaken between planning and applying, so the reservation scan "
            "behind this plan describes a world that may have moved. Re-plan "
            "inside the current span."
        )
    _preflight(plan)
    journal = _write_journal(plan)

    applied: list[tuple] = []
    try:
        for op in plan.operations:
            previous = op.path.read_text(encoding="utf-8") if isinstance(op, PatchFile) else None
            _atomic_write(op.path, op.content)
            applied.append((op, previous))
    except PossiblyApplied as exc:
        # Do NOT unwind and do NOT claim a rollback. The rename may have landed;
        # undoing on that assumption could destroy a write that survived, and
        # reporting "rolled back" tells an operator something we cannot show.
        _finish_journal(journal, "possibly-applied",
                        {"uncertain_path": str(exc.path), "error": repr(exc)})
        raise LockApplyFailure(
            f"{plan.kind} for {plan.subject_uid} is POSSIBLY APPLIED: {exc}. "
            f"Journal: {journal}. Run recovery, which compares disk against "
            "intent rather than guessing.",
            [], [str(exc.path)],
        ) from exc
    except BaseException as exc:
        undone, stranded = _undo(applied, recycle)
        # A rollback that could not recycle a governed entry has NOT rolled back.
        # Saying so would leave the entry on disk while the record claims the
        # transaction never happened (argus-a147, blocker 2).
        state = "rolled-back" if not stranded else "needs-operator"
        _finish_journal(journal, state, {"undone": undone, "stranded": stranded,
                                         "error": repr(exc)})
        raise LockApplyFailure(
            f"{plan.kind} for {plan.subject_uid} failed mid-apply ({exc}); "
            f"{len(undone)} write(s) undone, {len(stranded)} stranded"
            + (" — NEEDS OPERATOR: stranded substrate remains on disk"
               if stranded else "")
            + f". Journal: {journal}",
            undone, stranded,
        ) from exc

    _finish_journal(journal, "applied", {})
    return journal


def _finish_journal(path: Path, state: str, extra: dict) -> None:
    """Write the TERMINAL state atomically, and let failure propagate.

    This used a bare `write_text` and swallowed read errors (blocker 2). Both
    were wrong in the same direction: the terminal state is the one fact
    recovery reads to decide whether to act, so a torn write leaves an
    uninterpretable journal, and a silently skipped update leaves a completed
    transaction looking like an in-flight one forever.
    """
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LockApplyFailure(
            f"cannot read the journal at {path} to record its terminal state "
            f"({exc}). The transaction's outcome is now unrecorded, which is the "
            "one thing the journal exists to prevent.",
            [], [str(path)],
        ) from exc
    body["state"] = state
    body["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body.update(extra)
    _atomic_write(path, json.dumps(body, indent=2, sort_keys=True) + "\n")


def already_applied(kind: str, subject_uid: str, plan: LockPlan) -> bool:
    """Is this exact transaction already on disk, applied?

    AC2 requires the lock to be idempotent on retry. Idempotence compares the
    PLAN DIGEST, not just the subject: a second lock of the same subject that
    would write different bytes is a conflicting lock and must not be waved
    through as a retry.
    """
    path = LOCK_JOURNAL_DIR / f"{kind}-{subject_uid}.json"
    if not path.is_file():
        return False
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return body.get("state") == "applied" and body.get("plan_digest") == plan.digest()
