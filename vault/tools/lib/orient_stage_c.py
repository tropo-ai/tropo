#!/usr/bin/env python3
"""Stage C of ``orient()`` — brief, then judge, then guard (dev-spec 2672f9d0).

WHY THIS MODULE EXISTS
----------------------
Stage A+B draw a circle around a task and rank what is inside it. That much is
deterministic. Stage C is where a model finally sees the corpus, and the only
question this module answers is how to let the model CHOOSE without letting it
SPEAK: it picks which sentences answer the task, and the source picks what
those sentences say.

Three moves, in a fixed order, with the order itself load-bearing:

  C1 brief  — one paragraph of task intent, written from the task's own title,
              body and links BEFORE any survivor body is read (Lock 3). A brief
              written after reading the corpus is a summary of the corpus; only
              a brief written in ignorance of it is a neutral yardstick to
              judge candidate spans against.
  C2 select — ONE batched call over the top-K survivor bodies. Each body is
              read exactly ONCE and that single read is what C2, C3 and the
              locator all see, so no two of them can disagree about what the
              source says (AC7).
  C3 guard  — deterministic and model-free, in :mod:`lib.span_guard`. Every
              proposal is located in the source and re-emitted as SOURCE bytes,
              or refused by name. The model's typography never reaches a block.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It builds no spend machinery. Every model call goes through
:func:`lib.metered_model.call`, which already reserves before it calls,
verifies the response model identity, enforces the tier/geo and consent gates
and reconciles to the provider's actuals. Stage C's whole spend duty is to
translate that edge's typed refusals into typed Stage C refusals rather than
letting one leak out looking like a result. It reads no model name of its own:
the policy route table is the single identity authority, reached by task class.

It derives no rot verdict — Lock 1 gives body-grain rot to the gardener lane,
and Stage C consumes verdicts it must never produce (AC10).

It writes NOTHING (I5/AC11). The block is a value: returned, read, forgotten.
The only bytes this module causes to be written anywhere are the metered edge's
own spend-ledger entries. That is also why :class:`StageCBlock` has no
``stamp``/``commit``/``sync`` method — not as a convention, but because the
module holds no writable handle for one to use.

THE COST ENVELOPE, AND THE UNIT THAT ONCE LIED
----------------------------------------------
C2 is ONE batched call against ONE $0.25 reservation, and AC2 lets the provider
choose the inference geo — Sonnet costs 10% more when it reports ``us``.

The number that governs is NOT the reconciled cost. Admission cannot price
reconciled tokens, because reconciliation happens after the call it is deciding
whether to make; ``metered_model`` admits on
``loop_metering.worst_case_request_cost_nano_usd``, which charges one input
token per UTF-8 REQUEST BYTE at the US rate plus a 4,096-byte overhead. An
earlier build of this module was tuned against the reconciled path — the one
that gates nothing — and certified an envelope the edge refuses. K and the cap
are now ruled against admission (2672f9d0 §3): K=6 bodies at 8,000 bytes with
2,048 output tokens is 52,000 request bytes and $0.2189, admitting with 12%
headroom. K=7 admits by only ~1,400 bytes, which is too fine when the framing
figure is itself an estimate. The $0.25 ceiling was NOT raised — it is
Mike-ruled at 7a4e9df1, and routing around a ruled value to make a first run
fit is the wrong precedent.

``C2_MAX_OUTPUT_TOKENS`` sits at 2,048, half again above AC3's floor of
``RESPONSE_MAX_BYTES // 3`` rather than on it. That floor assumes 3 bytes per
output token, and a Stage C span list is the one place the assumption is least
safe: the spans it quotes are the typography the guard exists for — curly
quotes and em dashes, multi-byte UTF-8 inside escaped JSON — which tokenizes
nearer two bytes per token. The spend edge is exact arithmetic and the floor is
an estimate, so the margin belongs on the estimate's side.

The per-body cap is 8,000 BYTES, and the unit is the whole point. It was
written as ~8K TOKENS and applied in bytes, so the constant said one thing and
the code did another — a genuinely 8,000-token body is ~32 KB and misses the
ceiling by roughly 4x, which is exactly the miss that shipped. The number did
not move when the unit was fixed; only the name did. Measured across all 4,284
governed bodies, 8,000 bytes fits 78.3% whole (median 2,604 B, p75 7,025 B,
p90 15,070 B) and is the knee of that curve.

K stays replay-tunable on recall@K. Do NOT re-derive it from cost.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Optional

from lib import metered_model, span_guard
from lib.distiller_model_policy import MODEL_ROUTES, SEGMENT_CLASSES
from lib.viewer_projection import OS_SEGMENT

__all__ = [
    "K_SURVIVORS",
    "PER_BODY_INPUT_BYTE_CAP",
    "C1_TASK_CLASS",
    "C2_TASK_CLASS",
    "C1_MAX_OUTPUT_TOKENS",
    "C2_MAX_OUTPUT_TOKENS",
    "REPAIR_RETRY_BUDGET",
    "MODEL_CALL_FLOOR",
    "MODEL_CALL_CEILING",
    "BODY_ROT_SCREENED",
    "FIRST_SCALE_REHEARSAL_REQUIRED",
    "RESPONSE_MAX_BYTES",
    "FENCE_PROHIBITION",
    "C1_SYSTEM_PROMPT",
    "C2_SYSTEM_PROMPT",
    "StageCRefusal",
    "REASON_MODEL_SUBSTITUTION",
    "REASON_RESPONSE_CONTRACT",
    "REASON_SPEND_CEILING",
    "REASON_SEGMENT_EGRESS",
    "REASON_VIEWER_MISMATCH",
    "REASON_AS_OF_MISMATCH",
    "REASON_SPAN_GUARD",
    "REASON_UNREHEARSED_CORPUS_SCALE",
    "REASON_MODEL_EDGE",
    "REASON_CALL_CEILING",
    "REASON_INPUT_CONTRACT",
    "ParsedResponse",
    "ReplayArtifact",
    "ReplayMetric",
    "CaptureLog",
    "StageCBlock",
    "parse_model_json",
    "most_restricted_segment",
    "run_stage_c",
]


# --------------------------------------------------------------------------- #
# The decided build parameters (dev-spec 2672f9d0 §3)                           #
# --------------------------------------------------------------------------- #

#: Survivor bodies C2 reads in its one batched call. Ruled at 2672f9d0 §3
#: against the ADMISSION path, not the reconciled one: six bodies at the cap
#: below is 52,000 request bytes and $0.2189, inside the $0.25 distill
#: reservation with 12% headroom. Seven admits by only ~1,400 bytes, too fine
#: when the framing figure is an estimate. Retune on recall@K, never on cost.
K_SURVIVORS = 6

#: Per-body input budget for C2, in BYTES — and the unit is load-bearing. This
#: was written as "~8K tokens" and applied in bytes, so the constant said one
#: thing and the code did another; an 8,000-TOKEN body is ~32 KB and overruns
#: the ceiling by roughly 4x. Fixing the unit did not move the number, only the
#: name. 8,000 bytes fits 78.3% of the vault's 4,284 governed bodies whole
#: (median 2,604 B, p75 7,025 B, p90 15,070 B) and is the knee of that curve.
PER_BODY_INPUT_BYTE_CAP = 8_000

#: The two policy route keys. Stage C names the CLASS and never the model: the
#: route table resolves identity, so §3's open parameter 3 — moving C1 from the
#: parse class to the distill class — stays this one line.
C1_TASK_CLASS = "parse-query"
C2_TASK_CLASS = "distill"

#: C1 writes one paragraph. The parse class carries a $0.01 per-call ceiling
#: and the shipped preflight spends most of it on the 4,096-byte request
#: overhead, so the brief's output budget has to stay small for the call to be
#: admissible at all.
C1_MAX_OUTPUT_TOKENS = 512

#: Inside the window the module docstring derives: at or above
#: ``RESPONSE_MAX_BYTES // 3`` so a full-size AC3-legal response can be
#: expressed, and far enough under the US-geo edge (2,351) that the envelope
#: does not depend on which geography the provider happens to pick.
C2_MAX_OUTPUT_TOKENS = 2_048

#: Shared with the guard rather than restated. Lock 2 fixes it at one, and two
#: copies of a ceiling are two ceilings waiting to disagree.
REPAIR_RETRY_BUDGET = span_guard.REPAIR_RETRY_BUDGET

#: §2's call shape: C1 + C2 always, plus at most the one repair the guard's
#: budget allows.
MODEL_CALL_FLOOR = 2
MODEL_CALL_CEILING = MODEL_CALL_FLOOR + REPAIR_RETRY_BUDGET

#: AC10's named interim mode. Body-grain rot verdicts ship from the gardener
#: lane; until they do, the block states plainly that no body was screened
#: rather than leaving the reader to assume one way or the other.
BODY_ROT_SCREENED = False

#: AC13: the first corpus-scale run is a capped rehearsal with receipts per the
#: Canary Lane doctrine, not a rollout.
FIRST_SCALE_REHEARSAL_REQUIRED = True

#: AC3's response bound, in UTF-8 bytes, applied to the ORIGINAL response text.
RESPONSE_MAX_BYTES = 4096


# --------------------------------------------------------------------------- #
# Typed refusals                                                                #
# --------------------------------------------------------------------------- #

REASON_MODEL_SUBSTITUTION = "STAGE_C_MODEL_SUBSTITUTION"
REASON_RESPONSE_CONTRACT = "STAGE_C_RESPONSE_CONTRACT"
REASON_SPEND_CEILING = "STAGE_C_SPEND_CEILING"
REASON_SEGMENT_EGRESS = "STAGE_C_SEGMENT_EGRESS"
REASON_VIEWER_MISMATCH = "STAGE_C_VIEWER_MISMATCH"
REASON_AS_OF_MISMATCH = "STAGE_C_AS_OF_MISMATCH"
REASON_SPAN_GUARD = "STAGE_C_SPAN_GUARD"
REASON_UNREHEARSED_CORPUS_SCALE = "STAGE_C_UNREHEARSED_CORPUS_SCALE"
#: A typed edge refusal Stage C cannot classify more precisely. It still
#: refuses by name: an unmapped code must never be rounded to the nearest
#: familiar one, because the nearest familiar one is usually reassuring.
REASON_MODEL_EDGE = "STAGE_C_MODEL_EDGE"
REASON_CALL_CEILING = "STAGE_C_CALL_CEILING"
REASON_INPUT_CONTRACT = "STAGE_C_INPUT_CONTRACT"


class StageCRefusal(Exception):
    """A Stage C run that will not produce a block, and why.

    Named reasons rather than one opaque failure: "the provider swapped the
    model" and "the guard could not place any span" are different signals about
    different parts of the system, and a run that reports only "Stage C failed"
    throws away the distinction the replay metrics exist to track.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def _refuse(reason: str, message: str) -> StageCRefusal:
    return StageCRefusal(reason, message)


#: How the metered edge's closed refusal vocabulary maps onto Stage C's. The
#: edge is the authority on WHY a call did not happen; Stage C's job is to
#: carry that verdict outward under its own names rather than returning a
#: ``ModelRefusal`` where a block is expected.
_EDGE_REASONS = {
    "MODEL_SUBSTITUTION": REASON_MODEL_SUBSTITUTION,
    "CONSENT_DENIED": REASON_SEGMENT_EGRESS,
    "GEO_SCOPE_REFUSED": REASON_SEGMENT_EGRESS,
    "INVALID_SEGMENT": REASON_SEGMENT_EGRESS,
    "PER_CALL_LIMIT": REASON_SPEND_CEILING,
    "RESERVATION_REFUSED": REASON_SPEND_CEILING,
    "RECONCILIATION_REFUSED": REASON_SPEND_CEILING,
}


# --------------------------------------------------------------------------- #
# The wire contract (AC3)                                                       #
# --------------------------------------------------------------------------- #

#: The exact prohibition both system prompts carry, in the shipped Distiller
#: wording so the two edges ask for the same thing in the same words.
FENCE_PROHIBITION = (
    "Raw JSON only. Do not use Markdown fences. The first character must be { "
    "and the final character must be }. Do not include prose."
)

C1_SYSTEM_PROMPT = (
    "You write one task-intent brief of a single short paragraph. You are given "
    "only a task's title, body and existing links; you have not been shown any "
    "source document, so describe what the task is asking for and never guess "
    'at what the corpus contains. Return exactly one JSON object {"brief":'
    '"<one paragraph>"}. ' + FENCE_PROHIBITION
)

C2_SYSTEM_PROMPT = (
    "You select verbatim spans from the survivor bodies in the payload, judged "
    "against the task-intent brief in that same payload and against nothing "
    "else. Copy the source characters exactly; never retype its punctuation. "
    "Each span must begin and end at a sentence boundary in its body, cover at "
    f"most {span_guard.MAX_SPAN_SENTENCES} sentences and "
    f"{span_guard.MAX_SPAN_BYTES} bytes, and name the uid it was taken from. "
    "Never merge text across bodies, restate a body in your own words, or "
    'return a uid that is not in the payload. Return exactly one JSON object '
    '{"spans":[{"uid":"<8-hex>","span_text":"<verbatim>"}]}. '
    + FENCE_PROHIBITION
)

#: The response contract each parse is held to: one closed object carrying
#: exactly this key. ``field`` names the contract, so a refusal says which of
#: the two edges broke it.
_RESPONSE_FIELDS = {"c1": "brief", "c2": "spans"}
_C1_FIELD = "c1"
_C2_FIELD = "c2"

_UID_RE = re.compile(r"^[0-9a-f]{8}$")
_FENCE = "```"
_JSON_FENCE_OPEN = "```json\n"
_TRAILING_PARTIAL_WORD = re.compile(r"\S*\Z")


# --------------------------------------------------------------------------- #
# Value types — every one of them frozen, because the block is a value          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ParsedResponse:
    """One parsed model response, with the ORIGINAL text preserved beside it.

    ``original_text`` is what the provider actually sent — fence and all, not
    the unwrapped body — because a replay that re-parses a cleaned-up copy
    cannot reproduce the parse that happened, and the hash is what makes that
    claim checkable rather than asserted.
    """

    value: dict
    original_text: str
    sha256: str


@dataclass(frozen=True)
class ReplayArtifact:
    """A first-class replay artifact: some text and the hash that pins it."""

    kind: str
    text: str
    sha256: str


@dataclass(frozen=True)
class ReplayMetric:
    """A counted replay metric.

    Deliberately has no ``verdict`` field and no way to grow one. A metric
    counts; adjudicating is someone else's lane (AC10). ``value`` is ``None``
    when the run's configuration cannot score the metric at all — which is not
    the same fact as a score of zero, and must not be recorded as one.
    """

    kind: str
    population: int
    value: Optional[int] = None


@dataclass(frozen=True)
class CaptureLog:
    """What the capture referenced, and the segment it therefore inherits.

    R4: a capture log is exactly as restricted as the most restricted chunk it
    touches, so a log that references one private chunk is private however many
    OS chunks sit beside it.
    """

    referenced_uids: tuple[str, ...]
    segment: str


@dataclass(frozen=True)
class StageCBlock:
    """The ephemeral Stage C block (I5).

    A frozen value with no persistence surface: no ``stamp``, no ``commit``, no
    ``sync``. Value equality is load-bearing rather than incidental — AC12's R1
    plant compares two whole blocks to prove that resolution through
    ``visible_segments`` leaves no trace of what it filtered, so anything that
    counted, totalled or gapped the invisible items would show up here as an
    inequality.
    """

    spans: tuple[span_guard.GuardedSpan, ...]
    circle: tuple[str, ...]
    ranking: Any
    c1_brief: str
    body_rot_screened: bool
    capture_log: CaptureLog
    replay_artifacts: tuple[Any, ...]
    model_calls: tuple[metered_model.ModelReceipt, ...]
    rehearsal_receipt: Optional[Mapping[str, Any]]


@dataclass(frozen=True)
class _SpanProposal:
    """One span the model proposed: a POINTER into a body, never content."""

    uid: str
    span_text: str


@dataclass(frozen=True)
class _SpanReject:
    """One proposal the guard would not emit, kept for the tally and repair."""

    uid: str
    span_text: str
    reason: str
    detail: str


# --------------------------------------------------------------------------- #
# Segment restriction (R4)                                                      #
# --------------------------------------------------------------------------- #

#: Least to most restricted. ``SEGMENT_CLASSES`` is alphabetical and carries no
#: ordering, so the order is stated here — and checked against the policy
#: vocabulary at import, so a fourth class cannot appear without someone
#: deciding where it sits.
_RESTRICTION_ORDER = (OS_SEGMENT, "team", "private")


def _verify_module_constants() -> None:
    """Fail at import rather than mid-run on a drifted policy vocabulary."""
    if set(_RESTRICTION_ORDER) != set(SEGMENT_CLASSES):
        raise AssertionError(
            "segment restriction order does not cover the policy's segment "
            "classes; decide where the new class ranks before Stage C runs"
        )
    missing = [
        task for task in (C1_TASK_CLASS, C2_TASK_CLASS) if task not in MODEL_ROUTES
    ]
    if missing:
        raise AssertionError(
            f"Stage C task classes {missing} are not policy routes; model "
            "identity is resolved by the route table and nowhere else"
        )


_verify_module_constants()


def most_restricted_segment(classes) -> str:
    """Return the most restricted of ``classes`` (R4's inheritance rule).

    A pure function on the segment vocabulary. Raises on an empty input: the
    most restricted member of nothing is not "os", and defaulting it to the
    most permissive value is exactly the direction a restriction rule must
    never fail in.
    """
    resolved = tuple(classes)
    if not resolved:
        raise ValueError("most_restricted_segment needs at least one segment class")
    unknown = sorted(set(resolved) - set(_RESTRICTION_ORDER))
    if unknown:
        raise ValueError(f"unknown segment class(es): {unknown}")
    return max(resolved, key=_RESTRICTION_ORDER.index)


# --------------------------------------------------------------------------- #
# AC3 — the parser                                                              #
# --------------------------------------------------------------------------- #


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError(f"non-finite JSON constant {value!r}")


def parse_model_json(text: str, *, field: str) -> ParsedResponse:
    """Parse one model response under AC3's output contract.

    Accepts raw JSON, or exactly one bounded lowercase ```json wrapper — the
    single deviation the prompts tolerate because it is the one models make
    while still meaning the right thing. Prose, nesting, an uppercase fence,
    two fences, an array, an empty body and anything over
    ``RESPONSE_MAX_BYTES`` are all refused: each is a response whose intent
    cannot be read off its bytes, and guessing at intent here is how a
    half-parsed answer gets treated as a whole one.

    ``field`` names the response contract (``"c1"`` / ``"c2"``); the parsed
    object must be closed around exactly that contract's key.
    """
    try:
        expected_key = _RESPONSE_FIELDS[field]
    except KeyError as exc:
        raise ValueError(f"unknown response contract: {field!r}") from exc
    if not isinstance(text, str):
        raise _refuse(REASON_RESPONSE_CONTRACT, f"{field}: response is not text")

    size = len(text.encode("utf-8"))
    if size > RESPONSE_MAX_BYTES:
        raise _refuse(
            REASON_RESPONSE_CONTRACT,
            f"{field}: response is {size} bytes, bound is {RESPONSE_MAX_BYTES}",
        )

    payload = _unwrap_one_fence(text, field)
    if not (payload.startswith("{") and payload.endswith("}")):
        raise _refuse(
            REASON_RESPONSE_CONTRACT,
            f"{field}: response is not one bare JSON object; the prompt "
            "requires an opening brace first and a closing brace last",
        )
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (ValueError, RecursionError) as exc:
        raise _refuse(
            REASON_RESPONSE_CONTRACT, f"{field}: response is not valid JSON: {exc}"
        ) from exc
    if type(value) is not dict:
        raise _refuse(
            REASON_RESPONSE_CONTRACT, f"{field}: response is not a JSON object"
        )
    if set(value) != {expected_key}:
        raise _refuse(
            REASON_RESPONSE_CONTRACT,
            f"{field}: response must carry exactly {{{expected_key!r}}}, got "
            f"{sorted(value)}",
        )
    return ParsedResponse(
        value=value,
        original_text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _unwrap_one_fence(text: str, field: str) -> str:
    """Return the JSON payload, tolerating at most one bounded lowercase fence.

    Counting every fence marker in the whole response is what makes "exactly
    one bounded wrapper" true: a nested ``` inside the object and a second
    fenced block after it are both invisible to a check that only looks at the
    two ends.
    """
    candidate = text.strip()
    if not candidate:
        raise _refuse(REASON_RESPONSE_CONTRACT, f"{field}: response is empty")
    markers = candidate.count(_FENCE)
    if markers == 0:
        return candidate
    if (
        markers == 2
        and candidate.startswith(_JSON_FENCE_OPEN)
        and candidate.endswith(_FENCE)
    ):
        return candidate[len(_JSON_FENCE_OPEN) : -len(_FENCE)].strip()
    raise _refuse(
        REASON_RESPONSE_CONTRACT,
        f"{field}: response is not raw JSON or exactly one bounded lowercase "
        f"```json wrapper ({markers} fence markers)",
    )


def _brief_from(parsed: ParsedResponse) -> str:
    brief = parsed.value["brief"]
    if not isinstance(brief, str) or not brief.strip():
        raise _refuse(
            REASON_RESPONSE_CONTRACT, "c1: brief must be a non-empty string"
        )
    return brief


def _proposals_from(parsed: ParsedResponse) -> tuple[_SpanProposal, ...]:
    spans = parsed.value["spans"]
    if not isinstance(spans, list):
        raise _refuse(REASON_RESPONSE_CONTRACT, "c2: spans must be a JSON array")
    proposals = []
    for item in spans:
        if type(item) is not dict or set(item) != {"uid", "span_text"}:
            raise _refuse(
                REASON_RESPONSE_CONTRACT,
                'c2: each span must be exactly {"uid", "span_text"}',
            )
        uid, span_text = item["uid"], item["span_text"]
        if not isinstance(uid, str) or not _UID_RE.fullmatch(uid):
            raise _refuse(
                REASON_RESPONSE_CONTRACT, "c2: span uid is not 8 lowercase hex"
            )
        if not isinstance(span_text, str) or not span_text:
            raise _refuse(
                REASON_RESPONSE_CONTRACT, f"c2: span text for {uid} is not a string"
            )
        proposals.append(_SpanProposal(uid=uid, span_text=span_text))
    return tuple(proposals)


# --------------------------------------------------------------------------- #
# The bound model edge                                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _ModelEdge:
    """This run's binding to :func:`lib.metered_model.call`.

    Holds no spend logic of its own. It exists so the run's binding, policy
    resolver, clock and reservation factory travel together, and so every
    receipt lands in one ordered list — the block's ``model_calls`` is that
    list, which is why the ledger and the block can never disagree about how
    many calls happened.
    """

    run_binding: Any
    provider_call: Any
    policy_resolver: Any
    clock: Any
    reservation_id_factory: Any
    environment: Any
    receipts: list

    def text(
        self,
        *,
        task: str,
        messages: list,
        system: str,
        max_tokens: int,
        segment_classes: tuple[str, ...],
    ) -> str:
        """One metered call; the response text, or a typed Stage C refusal."""
        if len(self.receipts) >= MODEL_CALL_CEILING:
            raise _refuse(
                REASON_CALL_CEILING,
                f"Stage C's per-run ceiling of {MODEL_CALL_CEILING} model calls "
                f"is spent; {task} would be call {len(self.receipts) + 1}",
            )
        result = metered_model.call(
            task,
            messages,
            segment_classes=segment_classes,
            run_binding=self.run_binding,
            max_tokens=max_tokens,
            system=system,
            provider_call=self.provider_call,
            policy_resolver=self.policy_resolver,
            clock=self.clock,
            reservation_id_factory=self.reservation_id_factory,
            environment=self.environment,
        )
        if isinstance(result, metered_model.ModelRefusal):
            raise _refuse(
                _EDGE_REASONS.get(result.code, REASON_MODEL_EDGE),
                f"{task}: the model edge refused with {result.code}: "
                f"{result.message}",
            )
        self.receipts.append(result.receipt)
        return result.text


# --------------------------------------------------------------------------- #
# Input handling                                                                #
# --------------------------------------------------------------------------- #


def _uid_sequence(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise _refuse(REASON_INPUT_CONTRACT, f"{label} must be a sequence of uids")
    try:
        items = list(value)
    except TypeError as exc:
        raise _refuse(
            REASON_INPUT_CONTRACT, f"{label} must be a sequence of uids"
        ) from exc
    for item in items:
        if not isinstance(item, str) or not _UID_RE.fullmatch(item):
            raise _refuse(
                REASON_INPUT_CONTRACT, f"{label} contains a non-uid entry: {item!r}"
            )
    return tuple(items)


def _stage_b_attr(ranking: Any, name: str) -> Any:
    if not hasattr(ranking, name):
        raise _refuse(
            REASON_INPUT_CONTRACT,
            f"ranking carries no {name}; Stage B stamps it at rank and Stage C "
            "verifies it at distill (R2)",
        )
    return getattr(ranking, name)


def _task_text(task_source: Any, name: str) -> str:
    value = getattr(task_source, name, None)
    if not isinstance(value, str):
        raise _refuse(
            REASON_INPUT_CONTRACT, f"task_source.{name} must be a string for C1"
        )
    return value


def _segment_class(segment_class_of: Callable[[str], str], uid: str) -> str:
    segment = segment_class_of(uid)
    if segment not in SEGMENT_CLASSES:
        raise _refuse(
            REASON_INPUT_CONTRACT,
            f"{uid}: segment_class_of returned {segment!r}, which is not a "
            "policy segment class",
        )
    return segment


def _read_body(body_reader: Callable[[str], bytes], uid: str) -> bytes:
    source = body_reader(uid)
    if not isinstance(source, (bytes, bytearray)):
        raise _refuse(
            REASON_INPUT_CONTRACT,
            f"{uid}: body_reader must return the raw post-frontmatter bytes",
        )
    return bytes(source)


def _capped_body(source_bytes: bytes) -> str:
    """One survivor body, capped at the per-body input budget.

    Cut back to a whitespace boundary when it truncates, so the model is never
    handed half a word and asked to quote it verbatim.
    """
    head = source_bytes[:PER_BODY_INPUT_BYTE_CAP].decode("utf-8", errors="ignore")
    if len(source_bytes) > PER_BODY_INPUT_BYTE_CAP:
        head = _TRAILING_PARTIAL_WORD.sub("", head)
    return head


def _message(payload: dict) -> list:
    return [
        {
            "role": "user",
            "content": json.dumps(payload, sort_keys=True, ensure_ascii=False),
        }
    ]


# --------------------------------------------------------------------------- #
# C3 — applying the guard to a batch of proposals                               #
# --------------------------------------------------------------------------- #


def _guard_batch(
    proposals: tuple[_SpanProposal, ...],
    bodies: dict,
) -> tuple[list, list]:
    """Guard every proposal against the ONE read of its body.

    A proposal naming a uid that was never sent is rejected in the same
    channel as a proposal the guard cannot place: both are the model pointing
    at something that is not there, both are counted, and neither can be
    emitted. Rejects are returned rather than raised so one repair call can
    address all of them at once.
    """
    guarded, rejected = [], []
    for proposal in proposals:
        source = bodies.get(proposal.uid)
        if source is None:
            rejected.append(
                _SpanReject(
                    uid=proposal.uid,
                    span_text=proposal.span_text,
                    reason=REASON_SPAN_GUARD,
                    detail=(
                        "uid was not among the survivor bodies in the payload"
                    ),
                )
            )
            continue
        try:
            guarded.append(
                span_guard.guard_span(
                    uid=proposal.uid,
                    model_span_text=proposal.span_text,
                    source_bytes=source,
                )
            )
        except span_guard.SpanGuardRefusal as refusal:
            rejected.append(
                _SpanReject(
                    uid=proposal.uid,
                    span_text=proposal.span_text,
                    reason=refusal.reason,
                    detail=refusal.message,
                )
            )
    return guarded, rejected


def _ordered_unique(guarded: list, survivors: tuple[str, ...]) -> tuple:
    """Rank order, then source order, with duplicates collapsed.

    A repair call re-proposes spans that were already accepted often enough
    that de-duplication is the rule, not the edge case; and ordering the block
    by rank rather than by the order the model happened to answer in keeps two
    identical runs byte-identical.
    """
    rank = {uid: index for index, uid in enumerate(survivors)}
    seen, unique = set(), []
    for span in guarded:
        key = (span.uid, span.locator.char_start, span.locator.char_end)
        if key in seen:
            continue
        seen.add(key)
        unique.append(span)
    return tuple(
        sorted(unique, key=lambda span: (rank[span.uid], span.locator.char_start))
    )


# --------------------------------------------------------------------------- #
# The stage                                                                     #
# --------------------------------------------------------------------------- #


def run_stage_c(
    *,
    task_uid: str,
    task_source: Any,
    viewer: Any,
    visible_segments: Any,
    index_as_of: str,
    ranking: Any,
    circle: Any,
    body_reader: Callable[[str], bytes],
    segment_class_of: Callable[[str], str],
    run_binding: Any,
    seed_candidates: Any = (),
    provider_call: Any = None,
    policy_resolver: Any = None,
    clock: Any = None,
    reservation_id_factory: Any = None,
    environment: Optional[Mapping[str, str]] = None,
    corpus_scale: bool = False,
    rehearsal_receipt: Optional[Mapping[str, Any]] = None,
) -> StageCBlock:
    """Run C1, C2 and C3 and return the ephemeral block.

    Keyword-only, and Stage B's outputs (``ranking``, ``circle``,
    ``task_source``) are duck-typed: Stage C consumes them, so it should not
    own their types, and the block's own types are the only ones it exports.

    The order of what follows is the contract, not an implementation detail.
    Every gate that can refuse without spending money runs first; C1 is called
    before a single survivor body is read; each body is read exactly once and
    that read is shared by C2, C3 and the locator; and nothing is written
    anywhere at any point.
    """
    # AC13 — a corpus-scale run is a capped rehearsal with receipts or it does
    # not run. Checked before anything is spent or read.
    if corpus_scale and FIRST_SCALE_REHEARSAL_REQUIRED:
        if not isinstance(rehearsal_receipt, Mapping) or not rehearsal_receipt:
            raise _refuse(
                REASON_UNREHEARSED_CORPUS_SCALE,
                "the first corpus-scale run is a capped rehearsal with receipts "
                "per the Canary Lane doctrine, not a rollout",
            )

    # AC12 R2 — viewer and as-of are stamped at rank and VERIFIED here. A
    # ranking computed for another viewer or another snapshot is not this
    # run's ranking, and distilling it would answer the wrong question with
    # someone else's visibility.
    if _stage_b_attr(ranking, "viewer") != viewer:
        raise _refuse(
            REASON_VIEWER_MISMATCH,
            "the viewer stamped at rank is not the viewer distilling",
        )
    if _stage_b_attr(ranking, "index_as_of") != index_as_of:
        raise _refuse(
            REASON_AS_OF_MISMATCH,
            "the as-of stamped at rank is not the as-of distilling",
        )

    # Every input check that can refuse belongs on the near side of the first
    # reservation, so a malformed call costs nothing — including the circle,
    # which is not needed until the block is assembled.
    ranked = _uid_sequence(_stage_b_attr(ranking, "uids"), "ranking.uids")
    seeds = _uid_sequence(seed_candidates, "seed_candidates")
    resolved_circle = _uid_sequence(circle, "circle")

    # AC12 R1 — seed and FTS-fallback candidates resolve THROUGH
    # visible_segments. Filtered silently and counted nowhere: a refusal, a
    # tally or a gap in the block would each answer "how much is hidden from
    # me?", which is the question the floor exists to leave unanswerable.
    visible_seeds = tuple(
        uid
        for uid in seeds
        if _segment_class(segment_class_of, uid) in visible_segments
    )

    survivors = []
    for uid in (*ranked, *visible_seeds):
        if uid not in survivors:
            survivors.append(uid)
    survivors = tuple(survivors[:K_SURVIVORS])
    if not survivors:
        raise _refuse(
            REASON_INPUT_CONTRACT,
            "Stage C was handed no visible survivor to distill",
        )

    # AC5 — egress is a SECOND gate, not the same one. Visibility decides what
    # this viewer may see; egress decides what may cross to a provider, and
    # today only the OS segment may. A ranked survivor that is team- or
    # private-segment refuses by name instead of being dropped: Stage B ranked
    # it, so its presence is an upstream projection failure and silently
    # discarding it would hide that.
    survivor_segments = {
        uid: _segment_class(segment_class_of, uid) for uid in survivors
    }
    denied = sorted(
        uid for uid, segment in survivor_segments.items() if segment != OS_SEGMENT
    )
    if denied:
        raise _refuse(
            REASON_SEGMENT_EGRESS,
            f"survivors {denied} are not OS-segment; a team- or private-segment "
            "chunk may not reach the model edge, and cost approval is not "
            "egress approval",
        )

    edge = _ModelEdge(
        run_binding=run_binding,
        provider_call=provider_call,
        policy_resolver=policy_resolver,
        clock=clock,
        reservation_id_factory=reservation_id_factory,
        environment=environment,
        receipts=[],
    )

    # AC9 / Lock 3 — C1 first, from the task's own title, body and links. The
    # payload deliberately cannot contain a survivor body: none has been read.
    #
    # C1 crosses the edge declared OS-segment. ``segment_class_of`` resolves
    # CANDIDATE uids, not the task stub the caller hands in — Stage C is given
    # no classifier for the stub — so if a task is ever itself team- or
    # private-segment, that classification has to arrive with the task. Flagged
    # rather than defaulted quietly.
    brief_text = edge.text(
        task=C1_TASK_CLASS,
        messages=_message(
            {
                "task_uid": task_uid,
                "title": _task_text(task_source, "title"),
                "body": _task_text(task_source, "body"),
                "links": list(getattr(task_source, "links", ())),
            }
        ),
        system=C1_SYSTEM_PROMPT,
        max_tokens=C1_MAX_OUTPUT_TOKENS,
        segment_classes=(OS_SEGMENT,),
    )
    c1_parsed = parse_model_json(brief_text, field=_C1_FIELD)
    c1_brief = _brief_from(c1_parsed)

    # AC7 — ONE read per body, here, after the brief and before C2. Everything
    # downstream (C2's payload, C3's match domain, the locator's hash) reads
    # this dict; a repair retry re-uses it rather than going back to disk,
    # because a second read is a second chance for the source to disagree with
    # the locator already derived from the first.
    bodies = {uid: _read_body(body_reader, uid) for uid in survivors}
    payload_bodies = [
        {"uid": uid, "body": _capped_body(bodies[uid])} for uid in survivors
    ]
    c2_segments = tuple(sorted({survivor_segments[uid] for uid in survivors}))

    artifacts: list = [
        ReplayArtifact(
            kind="c1_response",
            text=c1_parsed.original_text,
            sha256=c1_parsed.sha256,
        ),
        ReplayArtifact(
            kind="c1_brief",
            text=c1_brief,
            sha256=hashlib.sha256(c1_brief.encode("utf-8")).hexdigest(),
        ),
    ]

    def distill(rejected: list) -> tuple[_SpanProposal, ...]:
        """One C2 call — the first pass, or the one repair the budget allows."""
        payload = {
            "brief": c1_brief,
            "task_uid": task_uid,
            "survivors": payload_bodies,
        }
        if rejected:
            # The repair carries the bodies again: the model cannot re-quote a
            # source it can no longer see, and the guard's own message is the
            # most precise statement of what was wrong with each attempt.
            payload["rejected_spans"] = [
                {
                    "uid": reject.uid,
                    "span_text": reject.span_text,
                    "reason": reject.reason,
                    "detail": reject.detail,
                }
                for reject in rejected
            ]
        text = edge.text(
            task=C2_TASK_CLASS,
            messages=_message(payload),
            system=C2_SYSTEM_PROMPT,
            max_tokens=C2_MAX_OUTPUT_TOKENS,
            segment_classes=c2_segments,
        )
        parsed = parse_model_json(text, field=_C2_FIELD)
        artifacts.append(
            ReplayArtifact(
                kind="c2_response",
                text=parsed.original_text,
                sha256=parsed.sha256,
            )
        )
        return _proposals_from(parsed)

    proposals = distill([])
    guarded, rejected = _guard_batch(proposals, bodies)
    proposed_total, rejected_total, repairs = len(proposals), len(rejected), 0

    # Lock 2's budget, spent at the BATCH grain. The guard's own
    # ``guard_with_repair`` spends the budget per span, which is right for a
    # single span and wrong here: C2 is one batched call, so N unguardable
    # spans would cost N repair calls and blow §2's per-run ceiling of three.
    # One repair call fixes the whole batch.
    while rejected and repairs < REPAIR_RETRY_BUDGET:
        repairs += 1
        retry = distill(rejected)
        proposed_total += len(retry)
        repaired, rejected = _guard_batch(retry, bodies)
        rejected_total += len(rejected)
        guarded.extend(repaired)

    spans = _ordered_unique(guarded, survivors)
    if proposals and not spans:
        raise _refuse(
            REASON_SPAN_GUARD,
            f"none of the {proposed_total} proposed span(s) could be placed in "
            "the source after the repair budget was spent; an unguardable "
            "batch is a guard signal, not an empty answer",
        )

    artifacts.extend(
        (
            ReplayMetric(
                kind="span_guard_rejects",
                population=proposed_total,
                value=rejected_total,
            ),
            ReplayMetric(
                kind="span_guard_repairs",
                population=REPAIR_RETRY_BUDGET,
                value=repairs,
            ),
            # AC10: the intrusion population is recorded and the score is left
            # unset. Stage C consumes body-grain rot verdicts and never derives
            # them, and none exist yet — so there is nothing to score against,
            # and writing zero here would be a verdict wearing a metric's
            # clothes.
            ReplayMetric(kind="rot_span_intrusion", population=len(spans)),
        )
    )

    return StageCBlock(
        spans=spans,
        circle=resolved_circle,
        ranking=ranking,
        c1_brief=c1_brief,
        body_rot_screened=BODY_ROT_SCREENED,
        capture_log=CaptureLog(
            referenced_uids=tuple(span.uid for span in spans),
            # R4: the log inherits from every chunk the capture crossed the
            # edge with, not only from the ones that survived the guard — a
            # rejected span was still read and still sent. The spans' own
            # classes are a subset of these, so this is the same value or a
            # more restricted one, which is the only safe direction to err in.
            segment=most_restricted_segment(survivor_segments.values()),
        ),
        replay_artifacts=tuple(artifacts),
        model_calls=tuple(edge.receipts),
        rehearsal_receipt=rehearsal_receipt,
    )
