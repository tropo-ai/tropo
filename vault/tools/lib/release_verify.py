"""AC7: four instruments, one package digest, each run exactly once.

Verify's claim is narrow and total: the full validator, the release harness,
the external test and the cold stranger walk each ran once, against the bytes
that are about to ship, and each said pass. This module owns the vocabulary
that claim is made in. It contains no network, no agent dispatch, and no
knowledge of how any instrument actually executes.

A148's Q3 answer shapes the whole file: ONE canonical receipt for all four
instruments, machine or human, distinguished by an `execution_mode` field
rather than by having two receipt types. The alternative -- reusing the AC6
`leg-attestation` type for the human instruments -- would have given the
Studio two vocabularies for "this happened", and every later reader would have
had to know which one to consult. `execution_mode` keeps the difference where
it belongs: in a field, not in a schema.

The engine never synthesizes these. It runs machine instruments and consumes
evidence for human and agent ones; Mike activates agents and human walks stay
human. What the run records is that the instrument happened and which package
it tested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from lib.governed_path import is_governed_uid_shape

#: The fixed four. Not configurable: AC7 counts instruments, and a vocabulary
#: a caller can extend is a vocabulary that cannot be counted against.
INSTRUMENTS = ("full-validator", "release-harness", "external-test", "cold-walk")

#: Which WorkflowNode declares each instrument, so a receipt can be tied back
#: to the graph position that was supposed to produce it.
INSTRUMENT_NODES = {
    "full-validator": "4262d5fa",
    "release-harness": "a0f2bea8",
    "external-test": "bc6b17ec",
    "cold-walk": "c6b61fb9",
}

#: v1.91 S2 (3fb41c99), Argus A155's ruling part 5: ONE instrument
#: vocabulary. tropo-freeze-release-candidate.py kept its own step-uid-keyed
#: dict with DIFFERENT NAMES for the same four instruments (e.g.
#: "full-release-validation" here spelled "full-validator") -- a
#: sibling-drift pair, not two designs. Derived, not hand-duplicated, so the
#: two can never drift again.
NODE_INSTRUMENTS = {node_uid: name for name, node_uid in INSTRUMENT_NODES.items()}

RECEIPT_KIND = "release-verification-receipt"

#: Every receipt binds all of these. A receipt missing any one of them cannot
#: answer the question Publish asks -- "did THIS instrument pass against THESE
#: bytes on THIS run" -- and a receipt that cannot answer that is not evidence.
#:
#: v1.91 S2 (3fb41c99), Argus A155's ruling: `candidate_sha256`, not
#: `package_sha256`. A receipt is written at VERIFY time, before a freeze can
#: exist -- binding it to a package identity that does not exist yet is the
#: ordering defect this spec removes. No guarantee is lost: the freeze gate
#: re-hashes the candidate on disk and requires every receipt to bind THAT
#: hash before it will freeze, so the evidence-to-freeze weld is enforced at
#: freeze, where it can be true, and package_sha256 == candidate_sha256 the
#: instant a freeze happens (freezing does not change the bytes).
RECEIPT_FIELDS = (
    "receipt_kind",
    "instrument",
    "release_run_uid",
    "candidate_sha256",
    "verdict",
    "executor_or_attester",
    "execution_mode",
    "evidence_ref",
    "started_at",
    "completed_at",
)

EXECUTION_MODES = ("machine", "human", "agent")
#: "skipped" is the founder's recorded excusal, never an instrument's verdict.
#: It is legal only when the receipt names `authorized_by`; it satisfies AC7's
#: count; and every reader that resolves a receipt set prints it loudly (see
#: `excusal_lines`). Before 2026-09-09 the runtime had an authorized-skip path
#: and this resolver had no notion of it, so a skip the founder authorized was
#: refused at the freeze and again at the fire — one fact, three readers, one
#: of them updated. Mike, 2026-09-09: "We need that flexibility. I like the
#: warn loudly and document as part of the process. I should be warned."
VERDICTS = ("pass", "fail", "skipped")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class VerifyRefusal(Exception):
    """The receipt set does not prove what AC7 claims, so Publish must not run.

    Fail-closed with the harm named (deb77758): publication is the one act
    this system cannot take back. A missing, failing, duplicated or
    wrong-digest receipt means some instrument's verdict on the shipping bytes
    is unknown, and an unproved yes is a no when the consequence leaves the
    building.
    """


@dataclass(frozen=True)
class Receipt:
    instrument: str
    release_run_uid: str
    candidate_sha256: str
    verdict: str
    executor_or_attester: str
    execution_mode: str
    evidence_ref: str
    started_at: str
    completed_at: str
    #: Only ever set on a `skipped` receipt: who excused the instrument.
    authorized_by: str = ""

    def as_dict(self) -> dict:
        out = {
            "receipt_kind": RECEIPT_KIND,
            "instrument": self.instrument,
            "release_run_uid": self.release_run_uid,
            "candidate_sha256": self.candidate_sha256,
            "verdict": self.verdict,
            "executor_or_attester": self.executor_or_attester,
            "execution_mode": self.execution_mode,
            "evidence_ref": self.evidence_ref,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
        if self.authorized_by:
            out["authorized_by"] = self.authorized_by
        return out


def validate_receipt(raw: dict) -> Receipt:
    """Parse one receipt or refuse, naming what is wrong with it.

    Deliberately strict about shape before it is strict about content: a
    receipt with a missing field is refused rather than defaulted, because a
    default here would invent a verdict nobody gave.
    """
    if not isinstance(raw, dict):
        raise VerifyRefusal(f"a verification receipt must be a mapping, got {type(raw).__name__}")

    missing = [f for f in RECEIPT_FIELDS if not str(raw.get(f) or "").strip()]
    if missing:
        raise VerifyRefusal(
            f"verification receipt is missing {', '.join(missing)}; a receipt "
            f"that cannot say which instrument tested which bytes on which run "
            f"is not evidence of anything"
        )

    if str(raw["receipt_kind"]) != RECEIPT_KIND:
        raise VerifyRefusal(
            f"receipt_kind is {raw['receipt_kind']!r}, not {RECEIPT_KIND!r}"
        )

    instrument = str(raw["instrument"])
    if instrument not in INSTRUMENTS:
        raise VerifyRefusal(
            f"{instrument!r} is not one of AC7's four instruments "
            f"({', '.join(INSTRUMENTS)}). The set is fixed because AC7 counts "
            f"it; an extensible vocabulary cannot be counted against."
        )

    mode = str(raw["execution_mode"])
    if mode not in EXECUTION_MODES:
        raise VerifyRefusal(
            f"execution_mode {mode!r} is not one of {', '.join(EXECUTION_MODES)}"
        )

    verdict = str(raw["verdict"])
    if verdict not in VERDICTS:
        raise VerifyRefusal(
            f"verdict {verdict!r} is not one of {', '.join(VERDICTS)}; an "
            f"unrecognised verdict is not a pass"
        )

    run_uid = str(raw["release_run_uid"])
    # accepts-both (UID_SHAPES): legacy 8-hex uids stay first-class forever;
    # every new governed mint is 12-hex composite since the Stage B flip
    # (2026-08-31). The literal 8-only regex this replaced refused a
    # freshly-minted composite release_run_uid as "not a governed uid".
    if not is_governed_uid_shape(run_uid):
        raise VerifyRefusal(f"release_run_uid {run_uid!r} is not a governed uid")

    digest = str(raw["candidate_sha256"])
    if not _SHA256.match(digest):
        raise VerifyRefusal(
            f"candidate_sha256 {digest[:16]!r} is not a sha-256 hex digest"
        )
    authorized_by = str(raw.get("authorized_by") or "").strip()
    if verdict == "skipped" and not authorized_by:
        raise VerifyRefusal(
            f"the {instrument} receipt says skipped but names no authorized_by; "
            f"an excusal nobody signed is a missing receipt, not a skip"
        )

    return Receipt(
        instrument=instrument,
        release_run_uid=run_uid,
        candidate_sha256=digest,
        verdict=verdict,
        executor_or_attester=str(raw["executor_or_attester"]),
        execution_mode=mode,
        evidence_ref=str(raw["evidence_ref"]),
        started_at=str(raw["started_at"]),
        completed_at=str(raw["completed_at"]),
        authorized_by=authorized_by,
    )


def resolve_receipt_set(
    raw_receipts: Iterable[dict],
    release_run_uid: str,
    expected_sha256: str,
) -> dict:
    """The one-digest bundle: four receipts, each passing or excused, or refuse.

    An excused instrument (verdict `skipped`, with `authorized_by`) counts
    toward the four and is returned in the set so the caller can print it
    loudly via `excusal_lines`; an absent instrument still refuses.

    Every refusal here is a different way of not knowing whether the shipping
    bytes were tested, and they are kept distinct because the operator's next
    move differs: a missing receipt means run the instrument, a wrong-digest
    receipt means the artefact changed under the verification, and a duplicate
    means something ran twice and one of those runs is unaccounted for.

    `expected_sha256` names two different facts depending on the caller:
    `assert_ready_to_freeze` passes the CANDIDATE digest (the only one that
    exists before a freeze); `assert_ready_to_publish` passes the FROZEN
    PACKAGE digest. Both compare against `receipt.candidate_sha256` --
    freezing does not change the bytes, so the two digests are the same
    value by the time a publish is possible.
    """
    by_instrument_history: dict = {}
    for raw in raw_receipts or []:
        receipt = validate_receipt(raw)

        if receipt.release_run_uid != release_run_uid:
            raise VerifyRefusal(
                f"a {receipt.instrument} receipt belongs to run "
                f"{receipt.release_run_uid}, not {release_run_uid}. Evidence "
                f"from another release does not transfer."
            )
        if receipt.candidate_sha256 != expected_sha256:
            raise VerifyRefusal(
                f"the {receipt.instrument} receipt tested "
                f"{receipt.candidate_sha256[:12]} but the bytes about to ship "
                f"are {expected_sha256[:12]}. Whatever that instrument "
                f"approved, it is not this artefact."
            )
        by_instrument_history.setdefault(receipt.instrument, []).append((receipt, raw))

    # LATEST RECEIPT PER INSTRUMENT GOVERNS; AGREEING PASS DUPLICATES ANYWHERE
    # IN THE HISTORY STILL REFUSE, UNLESS THE FINAL WINNER SELF-CERTIFIES.
    # First live release (v1.90, 2026-08-22, Metis G109): the original rule
    # refused ANY second receipt, which made every instrument that ever
    # reported a FAIL fatal to its run forever — re-running an instrument
    # after a cure is the only way a failed instrument ever passes, and the
    # journal is append-only, so the earlier FAIL can never leave. That is not
    # the harm the rule named. The harm it named — two PASSING executions with
    # one record of why — is still refused below.
    #
    # v1.92 addendum (vela-v74, 2026-08-26, Mike-directed "most lightweight
    # fix"): resolved once over the FULL history per instrument, not pairwise
    # against only the immediately-preceding receipt — a pairwise walk raises
    # (and the whole function aborts) the moment two consecutive receipts
    # disagree, even when a LATER receipt in the same history is the one that
    # actually explains the duplicate; that shape cannot ever reach its own
    # fix. "One record of why" can now be the final, chronologically-latest
    # receipt's OWN word: it may declare `supersedes_duplicate_receipt: true`
    # + a non-empty `duplicate_reason` naming what the earlier pass(es) were
    # (e.g. "written in error before the real dispatch's evidence existed") —
    # additive, optional, outside RECEIPT_FIELDS' closed schema, same shape as
    # candidate_invalidated_payload's already-solved pattern for the candidate
    # axis. This does not let a bad receipt silently win: the winner still has
    # to independently satisfy every other check (real instrument, correct
    # digest, resolvable evidence), and the declaration must sit on the
    # winner itself, not on whichever receipt happens to be adjacent to the
    # duplicate. A proper explicit retraction event mirroring
    # candidate_invalidated is the permanent fix and stays deferred to v1.93.
    by_instrument: dict = {}
    for instrument, history in by_instrument_history.items():
        history.sort(key=lambda pair: str(pair[0].completed_at or ""))
        winner, winner_raw = history[-1]
        other_passes = any(r.verdict == "pass" for r, _ in history[:-1])
        if winner.verdict == "skipped" and other_passes:
            raise VerifyRefusal(
                f"{instrument} passed against {expected_sha256[:12]} and was "
                f"excused afterwards by {winner.authorized_by}. Excusing an "
                f"instrument that already passed has no meaning; retire one "
                f"record or the other."
            )
        if winner.verdict == "pass" and other_passes:
            declared_reason = str(winner_raw.get("duplicate_reason") or "").strip()
            if not (winner_raw.get("supersedes_duplicate_receipt") and declared_reason):
                raise VerifyRefusal(
                    f"{instrument} has more than one PASSING receipt for "
                    f"run {release_run_uid}. Exactly one passing execution is "
                    f"legal, and agreeing duplicates refuse — two executions "
                    f"with one record of why is not a thing this can certify. "
                    f"(The final receipt may declare "
                    f"supersedes_duplicate_receipt:true + duplicate_reason to "
                    f"self-certify why two exist.)"
                )
        by_instrument[instrument] = winner

    missing = [name for name in INSTRUMENTS if name not in by_instrument]
    if missing:
        raise VerifyRefusal(
            f"no receipt for {', '.join(missing)} on run {release_run_uid}. "
            f"AC7 requires all four instruments against digest "
            f"{expected_sha256[:12]}; an instrument that did not report is not "
            f"an instrument that passed."
        )

    failed = [r.instrument for r in by_instrument.values()
              if r.verdict not in ("pass", "skipped")]
    if failed:
        raise VerifyRefusal(
            f"{', '.join(sorted(failed))} reported a failing verdict against "
            f"{expected_sha256[:12]}. A present receipt is not a passing one."
        )

    return by_instrument


def excused(by_instrument: dict) -> list:
    """The instruments in a resolved set that the founder excused, not verified."""
    return [r for r in by_instrument.values() if r.verdict == "skipped"]


def excusal_lines(by_instrument: dict) -> list:
    """The loud warning EVERY reader of a resolved receipt set prints.

    One home for the wording so the freeze, the fire and any later reader say
    the same thing about the same fact. An excused instrument is disclosed,
    never hidden inside a green summary (Mike-ruled 2026-09-09).
    """
    return [
        (f"⚠ EXCUSED, NOT VERIFIED: {r.instrument} did not run against "
         f"{r.candidate_sha256[:12]}. Skipped with authorization by "
         f"{r.authorized_by} ({r.evidence_ref}). Its verdict on these bytes is "
         f"unknown; the release proceeds on the founder's word.")
        for r in excused(by_instrument)
    ]


def assert_ready_to_freeze(
    raw_receipts: Iterable[dict],
    release_run_uid: str,
    candidate_sha256: str,
) -> dict:
    """The gate the freeze node calls before emitting `package_frozen`.

    dev-spec 2fae6312 moves the four-instrument proof from publish-time to
    freeze-time. The check itself is unchanged — same four instruments, same
    one-receipt-each rule, same digest binding — but it now runs against the
    CANDIDATE digest, which is the only digest that exists before a freeze.

    Named apart from `assert_ready_to_publish` because the two answer different
    questions at different boundaries: this one asks whether these bytes have
    earned a freeze, the other whether a frozen package may go outward. Sharing
    one name would make a later reader think one call site covers both.
    """
    return resolve_receipt_set(raw_receipts, release_run_uid, candidate_sha256)


def assert_ready_to_publish(
    raw_receipts: Iterable[dict],
    release_run_uid: str,
    package_sha256: str,
) -> dict:
    """The gate Publish calls before any network write.

    Named separately from `resolve_receipt_set` so the production call site
    reads as the decision it is making, and so removing it from `cmd_fire` is
    a visible deletion rather than a quiet change of argument.
    """
    return resolve_receipt_set(raw_receipts, release_run_uid, package_sha256)


def instrument_for_node(node_uid: str) -> Optional[str]:
    """Which instrument a Verify WorkflowNode is supposed to produce."""
    for instrument, uid in INSTRUMENT_NODES.items():
        if uid == node_uid:
            return instrument
    return None
