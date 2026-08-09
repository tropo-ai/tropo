#!/usr/bin/env python3
"""Lock 2's deterministic verbatim guard for Stage C spans (dev-spec 2672f9d0).

WHAT THIS MODULE IS FOR
-----------------------
Stage C asks a model which parts of a governed body answer a task. The model is
useful for *choosing*; it is not trusted to *quote*. Language models rewrite
typography as a matter of course — a straight apostrophe becomes a curly one, a
hyphen becomes an em-dash — and a span that has been silently retyped is a
paraphrase wearing a quotation's clothes.

So this guard inverts the trust. The model's text is treated as a POINTER, never
as content: it is used only to locate a region of the source, and what gets
emitted is the source's own bytes, sliced at a boundary derived source-side. The
invariant the whole extractive claim rests on is one sentence long:

    THE MODEL'S TYPOGRAPHY CAN NEVER REACH THE BLOCK.

Lock 2's three clauses, in the order they execute:

  (a) MATCH DOMAIN — match against the raw on-disk post-frontmatter bytes, and
      nothing else. Not the composed-index body copy, which is stripped and can
      lag disk (AC7); not a re-read, because a second read is a second chance to
      disagree with itself.
  (b) CANONICALIZED MATCHING WITH SOURCE-AUTHORITATIVE REPAIR — fold typography
      to FIND the span, then discard the folded form and emit the source bytes.
      Canonicalization is a matching aid with no emission path.
  (c) COMPLETE-BOUNDARY SPANS — a span starts and ends where a sentence does, so
      a quote can never begin mid-clause and imply a claim the source did not
      make.

WHY IT REJECTS RATHER THAN TRUNCATES
------------------------------------
When a proposed span is too long, the tempting repair is to trim it to the
bound. That would silently break clause (c): a truncated span ends wherever the
byte count ran out, which is almost never a sentence boundary. Rejecting is the
only repair that cannot manufacture a boundary violation while fixing a length
one. The bounds are expressed in BOTH sentences and bytes for the same reason —
three short sentences and three long ones are different risks, and an unbounded
span is Lock 2's paraphrase loophole by another name.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It derives no rot verdict (Lock 1 — the gardener owns that), reads no network,
and knows nothing about models, spend or viewers. It is a pure function from
(uid, proposed text, source bytes) to a guarded span or a typed refusal, which
is what makes it testable without a provider and reusable outside Stage C.
"""
from __future__ import annotations

import bisect
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

from lib.normalized_body_hash import _post_fence_body_bytes

PathLike = Union[str, Path]

__all__ = [
    "MAX_SPAN_SENTENCES",
    "MAX_SPAN_BYTES",
    "REPAIR_RETRY_BUDGET",
    "REASON_NO_MATCH",
    "REASON_SPAN_SENTENCE_BOUND",
    "REASON_SPAN_BYTE_BOUND",
    "REASON_INCOMPLETE_BOUNDARY",
    "REASON_REPAIR_BUDGET_EXHAUSTED",
    "SpanGuardRefusal",
    "Locator",
    "ContextWindow",
    "GuardedSpan",
    "match_domain_bytes",
    "canonicalize",
    "guard_span",
    "guard_with_repair",
]


# --------------------------------------------------------------------------- #
# The decided bounds (dev-spec 2672f9d0 §3, open parameters 2 and 4)            #
# --------------------------------------------------------------------------- #

#: Upper bound on a span, in complete source sentences. Three is long enough to
#: carry a claim with its qualifier and short enough that the span is still a
#: quotation rather than an excerpt.
MAX_SPAN_SENTENCES = 3

#: Upper bound on a span, in UTF-8 bytes. Independent of the sentence bound
#: because three long sentences and three short ones are different risks; a
#: sentence count alone leaves the loophole open.
MAX_SPAN_BYTES = 600

#: Fixed at 1 by Lock 2. A ceiling, not a default: the guard's reject/repair
#: rate is a first-class metric, and a high rate is a model-choice signal that a
#: generous retry budget would hide.
REPAIR_RETRY_BUDGET = 1


# --------------------------------------------------------------------------- #
# Typed refusals — every rejection says which clause rejected it                #
# --------------------------------------------------------------------------- #

REASON_NO_MATCH = "SPAN_NO_MATCH"
REASON_SPAN_SENTENCE_BOUND = "SPAN_SENTENCE_BOUND"
REASON_SPAN_BYTE_BOUND = "SPAN_BYTE_BOUND"
REASON_INCOMPLETE_BOUNDARY = "SPAN_INCOMPLETE_BOUNDARY"
REASON_REPAIR_BUDGET_EXHAUSTED = "SPAN_REPAIR_BUDGET_EXHAUSTED"


class SpanGuardRefusal(Exception):
    """A span the guard will not emit, carrying the clause that refused it.

    Named reasons rather than one opaque failure because the reject/repair
    tally is a per-run metric: "the model quoted something that is not there"
    and "the model quoted four sentences" are different signals about the
    model, and collapsing them would throw away the distinction.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


# --------------------------------------------------------------------------- #
# Value types                                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Locator:
    """Where a span lives, derived source-side and independently checkable.

    ``body_sha256`` pins WHICH bytes the offsets index. Without it a char range
    is meaningless the moment the file changes, and a reader following a stale
    locator would quote whatever now sits at those offsets.
    """

    uid: str
    body_sha256: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class ContextWindow:
    """The sentence either side of a span, so a reader can see its setting.

    Empty strings at a body edge rather than ``None``: absent and empty are
    different facts, and a caller that has to test for both will eventually
    forget one.
    """

    preceding: str
    following: str


@dataclass(frozen=True)
class GuardedSpan:
    """A span whose text is source bytes, not model output."""

    uid: str
    span_text: str
    context_window: ContextWindow
    locator: Locator


# --------------------------------------------------------------------------- #
# Clause (a) — the match domain                                                 #
# --------------------------------------------------------------------------- #


def match_domain_bytes(path: PathLike) -> bytes:
    """The raw on-disk post-frontmatter bytes: the ONE legal match domain.

    Delegates to the shipped validator transform rather than re-implementing
    fence detection, so this module cannot drift into a second, private
    definition of "body". The sha256 of what this returns equals
    ``normalized_body_hash.raw_body_sha256(path)`` by construction — verified,
    not assumed.
    """
    return _post_fence_body_bytes(path)


# --------------------------------------------------------------------------- #
# Clause (b) — canonicalization, for MATCHING only                              #
# --------------------------------------------------------------------------- #

#: Typography a model substitutes without being asked. Folded to the ASCII form
#: the source is likely to hold so a match can be found; never folded on the way
#: out. Deliberately narrow: an aggressive fold makes genuinely different
#: sentences compare equal, which would let the guard "find" a span that is not
#: really there.
_TYPOGRAPHIC_FOLD = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2212": "-",
    "\u2026": "...",
    "\u00a0": " ", "\u2007": " ", "\u202f": " ", "\u2009": " ",
}
_FOLD_TABLE = str.maketrans(_TYPOGRAPHIC_FOLD)
_WHITESPACE_RUN = re.compile(r"\s+")


def canonicalize(text: str) -> str:
    """Fold typography and collapse whitespace, for comparison only.

    NFC first so that a composed and a decomposed apostrophe are the same
    character before the fold table sees either. Whitespace collapses because a
    model re-wraps lines it did not intend to change.
    """
    folded = unicodedata.normalize("NFC", text).translate(_FOLD_TABLE)
    return _WHITESPACE_RUN.sub(" ", folded).strip()


# --------------------------------------------------------------------------- #
# Clause (c) — sentence boundaries, computed source-side                        #
# --------------------------------------------------------------------------- #

#: A sentence ends at . ! or ? followed by whitespace or end-of-body. Blank
#: lines end a block and therefore also a sentence, so a heading or list item
#: that carries no terminator still bounds a span.
_SENTENCE_END = re.compile(r"(?<=[.!?])(?=\s)|\n\s*\n")


def _sentence_spans(body: str) -> list[tuple[int, int]]:
    """Character ranges of every sentence in the body, in order.

    Ranges exclude the whitespace between sentences: a span's boundary is the
    sentence's last character, not the space after it, so two spans that abut
    do not overlap on a space.
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in _SENTENCE_END.finditer(body):
        end = match.start() if match.group().strip() == "" and match.group() else match.start()
        chunk = body[cursor:end]
        if chunk.strip():
            start_offset = len(chunk) - len(chunk.lstrip())
            spans.append((cursor + start_offset, cursor + len(chunk.rstrip())))
        cursor = match.end()
    tail = body[cursor:]
    if tail.strip():
        start_offset = len(tail) - len(tail.lstrip())
        spans.append((cursor + start_offset, cursor + len(tail.rstrip())))
    return spans


def _refuse(reason: str, message: str) -> SpanGuardRefusal:
    return SpanGuardRefusal(reason, message)


# --------------------------------------------------------------------------- #
# Which runs of sentences are worth comparing                                   #
# --------------------------------------------------------------------------- #


def _canonical_sentences(
    body: str, sentences: list[tuple[int, int]]
) -> Optional[list[str]]:
    """Each sentence's canonical form, IF the body is exactly their join.

    The check is the licence for everything below it. Measuring a run of
    sentences by canonicalizing it is cubic in the sentence count, and the
    corpus is not small enough to absorb that: a 477-sentence governed body
    took 267 seconds to place ONE span, and the longest body in the vault is
    2,905 sentences. So the search needs a run's canonical LENGTH without
    building the run, and that is only sound if canonicalizing a run equals
    joining its sentences' canonical forms with the single space the
    whitespace between them collapses to.

    That identity is asserted over the whole body rather than assumed. It
    holds because ``_sentence_spans`` excludes the whitespace between
    sentences and every gap it leaves is therefore whitespace, which
    ``canonicalize`` collapses to one space — but "it holds because" is an
    argument, and this is a check. Returning ``None`` when it fails puts the
    guard back on the unaccelerated comparison rather than on a decomposition
    it cannot vouch for.
    """
    pieces = [canonicalize(body[start:end]) for start, end in sentences]
    if " ".join(pieces) != canonicalize(body):
        return None
    return pieces


def _candidate_runs(
    pieces: Optional[list[str]], sentence_count: int, target: int
):
    """Runs to compare, longest-first — the guard's fixed order, unchanged.

    This is a PRUNE and nothing else. Every run it yields is still compared by
    canonicalizing the source slice, so no span reaches emission on the
    strength of the arithmetic here; skipping a run can only ever turn a match
    into a refusal, and never a refusal into a match. That is the one
    direction a guard is allowed to be wrong in, and it is why the licence
    above can be a check rather than a proof obligation.

    With the decomposition licensed, a run's canonical length is a
    subtraction. ``widths`` accumulates each sentence's canonical length plus
    the one space that separates it from the next, so it rises strictly, so at
    most one run can begin at a given sentence and be ``target`` characters
    long — and bisect finds that one. Without the licence, every run is a
    candidate, which is the enumeration this replaces.
    """
    if pieces is None:
        for length in range(sentence_count, 0, -1):
            for first in range(0, sentence_count - length + 1):
                yield length, first
        return
    widths = [0]
    for piece in pieces:
        widths.append(widths[-1] + len(piece) + 1)
    runs = []
    for first in range(sentence_count):
        width = widths[first] + target + 1
        position = bisect.bisect_left(widths, width, first + 1)
        if position <= sentence_count and widths[position] == width:
            runs.append((position - first, first))
    runs.sort(key=lambda run: (-run[0], run[1]))
    yield from runs


# --------------------------------------------------------------------------- #
# The guard                                                                     #
# --------------------------------------------------------------------------- #


def guard_span(
    *,
    uid: str,
    model_span_text: str,
    source_bytes: bytes,
) -> GuardedSpan:
    """Locate the model's proposed span in the source and emit the SOURCE bytes.

    The model's text is a pointer. What comes back is sliced from
    ``source_bytes`` at a sentence boundary the source defines, with a locator
    and context window derived on the source side. If the proposal cannot be
    located, or locates something that is not a whole run of sentences, or
    exceeds a bound, this refuses by name rather than emitting something
    approximate.
    """
    body = source_bytes.decode("utf-8")
    sentences = _sentence_spans(body)
    if not sentences:
        raise _refuse(REASON_NO_MATCH, f"{uid}: source body contains no sentences")

    wanted = canonicalize(model_span_text)
    if not wanted:
        raise _refuse(REASON_NO_MATCH, f"{uid}: proposed span is empty")

    # Clause (c) drives the search: only whole runs of source sentences are
    # candidates, so an incomplete boundary can never be *found* in the first
    # place. Runs are tried longest-first so a proposal spanning three
    # sentences is not satisfied by its own first sentence.
    for length, first in _candidate_runs(
        _canonical_sentences(body, sentences), len(sentences), len(wanted)
    ):
        start = sentences[first][0]
        end = sentences[first + length - 1][1]
        if canonicalize(body[start:end]) != wanted:
            continue

        span_text = body[start:end]
        if length > MAX_SPAN_SENTENCES:
            raise _refuse(
                REASON_SPAN_SENTENCE_BOUND,
                f"{uid}: span is {length} sentences, bound is "
                f"{MAX_SPAN_SENTENCES}; the guard rejects rather than "
                "truncating, because a trimmed span ends where the count "
                "ran out and not where the source did",
            )
        span_bytes = len(span_text.encode("utf-8"))
        if span_bytes > MAX_SPAN_BYTES:
            raise _refuse(
                REASON_SPAN_BYTE_BOUND,
                f"{uid}: span is {span_bytes} bytes, bound is "
                f"{MAX_SPAN_BYTES}; an unbounded span is a paraphrase "
                "loophole by another name",
            )

        return GuardedSpan(
            uid=uid,
            span_text=span_text,
            context_window=ContextWindow(
                preceding=body[sentences[first - 1][0]:sentences[first - 1][1]]
                if first > 0
                else "",
                following=body[
                    sentences[first + length][0]:sentences[first + length][1]
                ]
                if first + length < len(sentences)
                else "",
            ),
            locator=Locator(
                uid=uid,
                body_sha256=hashlib.sha256(source_bytes).hexdigest(),
                char_start=start,
                char_end=end,
            ),
        )

    # No whole-sentence run matched. Distinguish "quoted text that is not in the
    # source at all" from "quoted a fragment of a sentence" — different signals
    # about the model, and the reject tally is only useful if they are separate.
    if wanted in canonicalize(body):
        raise _refuse(
            REASON_INCOMPLETE_BOUNDARY,
            f"{uid}: proposed span is present in the source but does not start "
            "and end at sentence boundaries; a quote that begins mid-clause can "
            "imply a claim the source did not make",
        )
    raise _refuse(
        REASON_NO_MATCH,
        f"{uid}: proposed span does not appear in the source body even after "
        "canonicalization",
    )


def guard_with_repair(
    *,
    uid: str,
    source_bytes: bytes,
    propose: Callable[[Optional[SpanGuardRefusal]], str],
) -> GuardedSpan:
    """Run the guard, allowing exactly ``REPAIR_RETRY_BUDGET`` re-proposals.

    ``propose`` is called with ``None`` for the first attempt and with the
    refusal that just occurred for each repair, so the caller can tell the model
    what was wrong. The budget is a hard ceiling: when it is exhausted this
    raises ``REASON_REPAIR_BUDGET_EXHAUSTED`` rather than trying once more.
    """
    last: Optional[SpanGuardRefusal] = None
    for attempt in range(REPAIR_RETRY_BUDGET + 1):
        try:
            return guard_span(
                uid=uid,
                model_span_text=propose(last),
                source_bytes=source_bytes,
            )
        except SpanGuardRefusal as refusal:
            last = refusal
    raise _refuse(
        REASON_REPAIR_BUDGET_EXHAUSTED,
        f"{uid}: span still unguardable after {REPAIR_RETRY_BUDGET} repair "
        f"attempt(s); last refusal was {last.reason if last else 'unknown'}",
    )
