"""lib/receipt_ref.py — the D5 append-only per-writer receipt-ref client.

Dev-spec 396d88a4 (receipts ride `refs/tropo/receipts/<writer_instance_uid>` on
the live `tropo-ai/tropo-receipts` repo); cycle brief cc437616 §6/§8 (the target
reconciliation receipt — destination, fetched/integrated commit, result-tree
hash, verifier, source-attestation hash). Test-spec 0f06a8b5 assertion P4.

THE RECEIPT STREAM CONTRACT (all fail-closed, each hostile plant refused):
  - per-writer ref     — `refs/tropo/receipts/<writer_instance_uid>`; one stream
                         per writer instance (no shared mutable ref).
  - append-only        — a receipt is a git commit whose parent is the current
                         stream tip; history is never rewritten.
  - single-parent CAS  — the append advances the ref with an old-value guard
                         (`git update-ref <ref> <new> <old>`); a concurrent
                         writer that advanced the tip loses → RECEIPT_REF_FAILED.
                         Exactly ONE linear parent per receipt (no merges).
  - content-addressed  — receipt_id = sha256(canonical payload minus the id);
                         a tampered stored receipt fails re-derivation →
                         RECEIPT_INVALID.
  - non-recursive      — a receipt may not be a receipt-OF-a-receipt (no
                         `subject.kind == "receipt"`, no receipt payload_type) →
                         RECEIPT_INVALID.
  - ACL                — only the REGISTERED writer/key may append (a forged
                         writer or wrong key → RECEIPT_REF_FAILED); authorized
                         members may fetch/read.
  - no replay          — a receipt_id already present in the stream cannot be
                         re-appended → RECEIPT_INVALID.

Works against the live receipts repo on github.com AND against a local bare repo
(the P4 proof) — the ref plumbing (`update-ref` old-value CAS, custom refs) is
identical. Uses only git plumbing (hash-object / mktree / commit-tree /
update-ref) so it never needs a working tree.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Optional

from lib.github_transport import run_git, GitError

RECEIPTS_REF_PREFIX = "refs/tropo/receipts/"
RECEIPT_BLOB_NAME = "receipt.json"
ZERO_OID = "0" * 40

# The only payload_type the stream accepts. Anything else — especially a receipt
# describing another receipt — is rejected as recursive.
RECONCILIATION_TYPE = "reconciliation-receipt"

ERR_RECEIPT_REF_FAILED = "RECEIPT_REF_FAILED"
ERR_RECEIPT_INVALID = "RECEIPT_INVALID"


class ReceiptError(Exception):
    """A modelled receipt-ref refusal carrying a closed D5 error code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")


def _canonical(payload: Mapping) -> str:
    body = {k: v for k, v in payload.items() if k != "receipt_id"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_receipt_id(payload: Mapping) -> str:
    """Content address: sha256 over the canonical payload EXCLUDING receipt_id
    (so the id is a pure function of content and cannot be forged to a value
    that does not match its bytes)."""
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _is_recursive(payload: Mapping) -> bool:
    """A receipt-OF-a-receipt plant: a payload that is itself typed as a receipt,
    or whose subject is a receipt. Non-recursive (no receipt-of-receipt)."""
    if payload.get("payload_type") != RECONCILIATION_TYPE:
        return True
    subject = payload.get("subject")
    if isinstance(subject, Mapping) and str(subject.get("kind", "")).lower() == "receipt":
        return True
    if payload.get("parent_receipt") or payload.get("receipt_ref"):
        return True
    return False


class ReceiptRefClient:
    """Append-only per-writer receipt-ref client over a git repo (`repo_dir` is a
    git directory — a bare receipts repo in the proof fixture)."""

    def __init__(self, repo_dir: Path, *, authorized_writers: Optional[Mapping[str, str]] = None):
        self.repo_dir = Path(repo_dir)
        # writer_instance_uid -> presented key (the least-privilege append key).
        # None means "no ACL configured" — a closed default: reject every append
        # (fail-closed; a stream with no registered writer accepts nothing).
        self.authorized_writers = dict(authorized_writers or {})

    def _ref(self, writer_uid: str) -> str:
        return f"{RECEIPTS_REF_PREFIX}{writer_uid}"

    def tip(self, writer_uid: str) -> Optional[str]:
        proc = run_git(
            ["rev-parse", "--verify", "--quiet", self._ref(writer_uid)],
            git_dir=self.repo_dir, check=False,
        )
        out = proc.stdout.strip()
        return out or None

    def read_receipts(self, writer_uid: str) -> list[dict]:
        """Every receipt in the stream, oldest → newest, each verified for
        content-address integrity + single-parent linearity. A break anywhere is
        a hard failure (RECEIPT_INVALID) — the stream is evidence, not a cache."""
        tip = self.tip(writer_uid)
        if tip is None:
            return []
        proc = run_git(
            ["rev-list", "--first-parent", "--reverse", tip],
            git_dir=self.repo_dir, check=True,
        )
        commits = [c for c in proc.stdout.split() if c]
        receipts: list[dict] = []
        prev: Optional[str] = None
        for commit in commits:
            # single-parent linearity: each commit has exactly one parent = prev.
            parents = run_git(
                ["rev-list", "--parents", "-n", "1", commit],
                git_dir=self.repo_dir,
            ).stdout.split()
            parent_ids = parents[1:]
            if len(parent_ids) > 1:
                raise ReceiptError(ERR_RECEIPT_INVALID,
                                   f"receipt {commit[:12]} has {len(parent_ids)} parents (not single-parent)")
            if (parent_ids[0] if parent_ids else None) != prev:
                raise ReceiptError(ERR_RECEIPT_INVALID,
                                   f"receipt {commit[:12]} does not chain single-parent to prior")
            blob = run_git(
                ["cat-file", "-p", f"{commit}:{RECEIPT_BLOB_NAME}"], git_dir=self.repo_dir,
            ).stdout
            payload = json.loads(blob)
            recomputed = compute_receipt_id(payload)
            if payload.get("receipt_id") != recomputed:
                raise ReceiptError(ERR_RECEIPT_INVALID,
                                   f"receipt {commit[:12]} content-address mismatch (tampered)")
            receipts.append(payload)
            prev = commit
        return receipts

    def append_receipt(
        self, writer_uid: str, payload: Mapping, *,
        presented_key: Optional[str] = None, expected_parent: str = "__auto__",
    ) -> dict:
        """Append a receipt to the writer's stream. Refuses (typed) a forged
        writer, a recursive receipt, a replay, or a CAS race.

        `expected_parent="__auto__"` reads the live tip (the normal path);
        passing an explicit (possibly stale) value drives the CAS-race gauntlet.
        """
        # -- ACL: only the registered writer/key may append --------------------
        if writer_uid not in self.authorized_writers:
            raise ReceiptError(ERR_RECEIPT_REF_FAILED,
                               f"writer {writer_uid!r} is not a registered receipt writer (forged writer)")
        if presented_key != self.authorized_writers[writer_uid]:
            raise ReceiptError(ERR_RECEIPT_REF_FAILED,
                               f"writer {writer_uid!r} presented the wrong append key (forged/unauthorized)")

        # -- non-recursive: no receipt-of-receipt ------------------------------
        if _is_recursive(payload):
            raise ReceiptError(ERR_RECEIPT_INVALID,
                               "receipt-of-receipt refused: a receipt may not describe another receipt")

        # -- content-address + replay -----------------------------------------
        payload = dict(payload)
        receipt_id = compute_receipt_id(payload)
        payload["receipt_id"] = receipt_id
        existing = {r["receipt_id"] for r in self.read_receipts(writer_uid)}
        if receipt_id in existing:
            raise ReceiptError(ERR_RECEIPT_INVALID,
                               f"replay refused: receipt {receipt_id[:12]} already recorded in the stream")

        # -- build the receipt object (blob → tree → single-parent commit) -----
        blob = run_git(
            ["hash-object", "-w", "--stdin"], git_dir=self.repo_dir,
            input_text=json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        ).stdout.strip()
        tree = run_git(
            ["mktree"], git_dir=self.repo_dir,
            input_text=f"100644 blob {blob}\t{RECEIPT_BLOB_NAME}\n",
        ).stdout.strip()

        # The CAS old-value the caller expects the ref to be at (ZERO_OID means
        # "must not yet exist"). The commit parent is that value ONLY when it is
        # a real commit — a ZERO_OID/absent expectation makes a root commit.
        if expected_parent == "__auto__":
            expected_old = self.tip(writer_uid) or ZERO_OID
        else:
            expected_old = expected_parent or ZERO_OID
        parent = expected_old if expected_old != ZERO_OID else None
        commit_args = ["commit-tree", tree, "-m", receipt_id]
        if parent:
            commit_args += ["-p", parent]
        commit = run_git(commit_args, git_dir=self.repo_dir).stdout.strip()

        # -- single-parent CAS: old-value guard IS the append-only arbiter -----
        upd = run_git(
            ["update-ref", self._ref(writer_uid), commit, expected_old],
            git_dir=self.repo_dir, check=False,
        )
        if upd.returncode != 0:
            raise ReceiptError(ERR_RECEIPT_REF_FAILED,
                               f"receipt-ref CAS failed for {self._ref(writer_uid)}: the stream "
                               f"tip moved under a concurrent append (re-read and retry)")
        return {"receipt_id": receipt_id, "commit": commit, "ref": self._ref(writer_uid)}


def init_bare_receipts_repo(path: Path) -> Path:
    """A bare repo standing in for `tropo-ai/tropo-receipts` in the P4 proof."""
    path.mkdir(parents=True, exist_ok=True)
    run_git(["init", "--bare", str(path)])
    return path


__all__ = [
    "RECEIPTS_REF_PREFIX", "RECONCILIATION_TYPE", "ZERO_OID",
    "ERR_RECEIPT_REF_FAILED", "ERR_RECEIPT_INVALID",
    "ReceiptError", "ReceiptRefClient",
    "compute_receipt_id", "init_bare_receipts_repo",
]
