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

RECEIPT_KIND = "release-verification-receipt"

#: Every receipt binds all of these. A receipt missing any one of them cannot
#: answer the question Publish asks -- "did THIS instrument pass against THESE
#: bytes on THIS run" -- and a receipt that cannot answer that is not evidence.
RECEIPT_FIELDS = (
    "receipt_kind",
    "instrument",
    "release_run_uid",
    "package_sha256",
    "verdict",
    "executor_or_attester",
    "execution_mode",
    "evidence_ref",
    "started_at",
    "completed_at",
)

EXECUTION_MODES = ("machine", "human", "agent")
VERDICTS = ("pass", "fail")

_UID = re.compile(r"^[0-9a-f]{8}$")
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
    package_sha256: str
    verdict: str
    executor_or_attester: str
    execution_mode: str
    evidence_ref: str
    started_at: str
    completed_at: str

    def as_dict(self) -> dict:
        return {
            "receipt_kind": RECEIPT_KIND,
            "instrument": self.instrument,
            "release_run_uid": self.release_run_uid,
            "package_sha256": self.package_sha256,
            "verdict": self.verdict,
            "executor_or_attester": self.executor_or_attester,
            "execution_mode": self.execution_mode,
            "evidence_ref": self.evidence_ref,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


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
    if not _UID.match(run_uid):
        raise VerifyRefusal(f"release_run_uid {run_uid!r} is not a governed uid")

    digest = str(raw["package_sha256"])
    if not _SHA256.match(digest):
        raise VerifyRefusal(
            f"package_sha256 {digest[:16]!r} is not a sha-256 hex digest"
        )

    return Receipt(
        instrument=instrument,
        release_run_uid=run_uid,
        package_sha256=digest,
        verdict=verdict,
        executor_or_attester=str(raw["executor_or_attester"]),
        execution_mode=mode,
        evidence_ref=str(raw["evidence_ref"]),
        started_at=str(raw["started_at"]),
        completed_at=str(raw["completed_at"]),
    )


def resolve_receipt_set(
    raw_receipts: Iterable[dict],
    release_run_uid: str,
    package_sha256: str,
) -> dict:
    """The one-digest bundle: exactly four passing receipts, or refuse.

    Every refusal here is a different way of not knowing whether the shipping
    bytes were tested, and they are kept distinct because the operator's next
    move differs: a missing receipt means run the instrument, a wrong-digest
    receipt means the artefact changed under the verification, and a duplicate
    means something ran twice and one of those runs is unaccounted for.
    """
    by_instrument: dict = {}
    for raw in raw_receipts or []:
        receipt = validate_receipt(raw)

        if receipt.release_run_uid != release_run_uid:
            raise VerifyRefusal(
                f"a {receipt.instrument} receipt belongs to run "
                f"{receipt.release_run_uid}, not {release_run_uid}. Evidence "
                f"from another release does not transfer."
            )
        if receipt.package_sha256 != package_sha256:
            raise VerifyRefusal(
                f"the {receipt.instrument} receipt tested "
                f"{receipt.package_sha256[:12]} but the package about to ship "
                f"is {package_sha256[:12]}. Whatever that instrument approved, "
                f"it is not this artefact."
            )

        # AGREEING DUPLICATES STILL REFUSE. "Ran exactly once" is part of the
        # claim, not a tidiness preference: two receipts mean two executions,
        # and if they agree we still cannot say which one the evidence_ref
        # describes or why the second was needed. Silently keeping one is how
        # a re-run that should have raised questions becomes invisible.
        if receipt.instrument in by_instrument:
            raise VerifyRefusal(
                f"{receipt.instrument} has more than one receipt for run "
                f"{release_run_uid}. Exactly one is legal, and duplicates "
                f"refuse even when they agree — two executions with one "
                f"record of why is not a thing this can certify."
            )
        by_instrument[receipt.instrument] = receipt

    missing = [name for name in INSTRUMENTS if name not in by_instrument]
    if missing:
        raise VerifyRefusal(
            f"no receipt for {', '.join(missing)} on run {release_run_uid}. "
            f"AC7 requires all four instruments against the frozen digest "
            f"{package_sha256[:12]}; an instrument that did not report is not "
            f"an instrument that passed."
        )

    failed = [r.instrument for r in by_instrument.values() if r.verdict != "pass"]
    if failed:
        raise VerifyRefusal(
            f"{', '.join(sorted(failed))} reported a failing verdict against "
            f"package {package_sha256[:12]}. A present receipt is not a "
            f"passing one."
        )

    return by_instrument


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
