#!/usr/bin/env python3
"""tropo-orient.py — ask the studio where a piece of work stands, and read the answer.

WHY THIS EXISTS
---------------
`orient()` has worked since 2026-07-31 and nobody could use it. Two reasons,
both about the reader rather than the engine:

  1. Running it meant an agent writing Python and pasting the result back.
  2. It answers in UIDs. Mike, 2026-08-01: "when I am reading our studio's
     work it has UIDs all over the place and I don't know what the file is
     without clicking a hyperlink (if it even is linkable)."

So this is not new capability. It is the same deterministic core — draw the
circle, rank it — rendered for a person: every item named, every item
explained (why it is in the circle, how far away, how it scored), and every
item linkable.

WITHOUT --read, THIS STILL COSTS NOTHING
----------------------------------------
The default is unchanged and unchanged deliberately: no model is called, no
reservation is made, nothing is spent, and the answer is the same citation list
it has always been. That is the free path, and it stays the default.

WITH --read, IT READS THEM
--------------------------
``--read`` turns on Stage C, the layer that opens the documents and answers
WHAT THEY SAY. It costs real money — a few cents a run — so it is a flag a
person chooses, never a default and never something a policy can switch on. The
paragraph it produces goes at the top of this same output; everything below it
stays exactly as the citation list.

Three things about the read are worth knowing before you use it:

  * **Most runs are partial, and the tool says which parts.** A document has to
    be resolvable, have a governed body under ``vault/files/``, and be ours to
    send before it can be read. Measured over all 91 governed tasks, 42.9% of
    ranked survivors clear that bar. Every one that does not is named in the
    output with the reason — never quietly dropped and never rounded into a
    count the reader has to notice.
  * **A run that can read nothing says so.** It never returns an empty answer,
    and it never puts the citation list under a heading that makes it look like
    something was read. That failure is the dangerous one, because a list of
    documents under a confident heading is indistinguishable from an answer.
  * **Every sentence in quotation marks is the source's own bytes.** The model
    chooses which sentences answer the task; :mod:`lib.span_guard` then throws
    the model's text away and re-cuts the quote from the file. The model's
    typography never reaches this output.

USAGE
-----
    python3 vault/tools/tropo-orient.py --task af6c53df
    python3 vault/tools/tropo-orient.py --task af6c53df --k 12 --as argus
    python3 vault/tools/tropo-orient.py --task af6c53df --board
    python3 vault/tools/tropo-orient.py --task af6c53df --read   # spends money

Checkpoint 5e6652ac. Metis G98, 2026-08-01; reading landed 2026-08-01.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import secrets
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "vault" / "tools"))
sys.path.insert(0, str(ROOT / "vault" / "tools" / "lib"))

from lib import daily_spend  # noqa: E402
from lib import distiller  # noqa: E402
from lib import index_surfaces  # noqa: E402
from lib import llm  # noqa: E402
from lib import loop_metering  # noqa: E402
from lib import metered_model  # noqa: E402
from lib import orient_stage_c as stage_c  # noqa: E402
from lib import viewer_projection as vp  # noqa: E402
from lib.distiller_model_policy import MODEL_ROUTES  # noqa: E402
from lib.distiller_ranker import SqliteRankIndex  # noqa: E402
from lib.task_circle import SqliteStructuralIndex  # noqa: E402

INDEX_JSONL = ROOT / "vault" / "00-index.jsonl"
ARCHIVE_INDEX_JSONL = ROOT / "vault" / "00-archive-index.jsonl"
INDEX_SQLITE = ROOT / "vault" / "00-index.sqlite"
FILES = ROOT / "vault" / "files"

#: The snapshot token this tool ranks under. One name, because Stage B stamps
#: it at rank and Stage C verifies it at distill (R2) — two spellings of it
#: would be a mismatch nobody could see.
INDEX_AS_OF = "tropo-orient"

#: Party UIDs, so `--as vela` works instead of `--as e97ac0ae`. Resolved from
#: the agent entries at import rather than hard-coded, because a hard-coded
#: roster is a second place for the same fact to live and it will drift.
def _principals() -> dict[str, str]:
    out: dict[str, str] = {}
    agents_dir = ROOT / "vault" / "agents"
    if not agents_dir.is_dir():
        return out
    for path in sorted(agents_dir.glob("*.md")):
        name = key = None
        for line in path.read_text(errors="ignore").splitlines()[:40]:
            if line.startswith("agent:"):
                name = line.split(":", 1)[1].strip().strip("'\"")
            elif line.startswith("party_uid:"):
                key = line.split(":", 1)[1].strip().strip("'\"")
            if name and key:
                out[name] = key
                break
    return out


def _records() -> dict[str, dict]:
    """Load metadata from the composed current + archive resolution union."""

    out: dict[str, dict] = {}
    for index_path in (INDEX_JSONL, ARCHIVE_INDEX_JSONL):
        if not index_path.exists():
            continue
        with index_path.open() as handle:
            for line in handle:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                uid = rec.get("uid")
                if uid:
                    out[uid] = rec
    return out


def _all_records() -> dict[str, dict]:
    """Current AND archived index rows — the read path's view of the vault.

    :func:`_records` above reads the same union for the citation list. This
    loader uses the shipped ADR-047 union reader because the paid path already
    receives a Studio root as an injection point in its tests and at runtime.
    Both paths therefore resolve archived and superseded rows as ordinary
    indexed documents.

    So keying eligibility on the current projection would refuse to read most
    of what orient ranks, on the grounds of which projection file a row was
    written to. The governed file is on disk either way. That is the same
    mistake as deriving egress from a publishing label, and it is corrected in
    the same direction: read from the union, decide on the document.

    Routed through the shipped union reader rather than a second glob, because
    keeping that routing in one module is what ADR-047 is for.
    """

    out: dict[str, dict] = {}
    for rec in index_surfaces.load_index_records(ROOT, include_archive=True):
        uid = rec.get("uid")
        if uid:
            out.setdefault(uid, rec)
    return out


def _describe(member) -> str:
    """Why this item is in the circle, in words rather than field names.

    The relation vocabulary is small and closed, so this is a lookup rather
    than a guess. An unmapped relation falls through to its own name with the
    underscores softened — visible rather than silently blank, because a
    reason nobody can read is the defect this tool exists to fix.
    """

    relation = (getattr(member, "relation", "") or "").strip()
    distance = getattr(member, "distance", None)
    phrase = {
        "member_of-parent":     "sits directly under it",
        "member_of-ancestor":   "is a parent project above it",
        "member_of-child":      "sits inside it",
        "ref-of-task":          "this work references it",
        "ref-to-task":          "it references this work",
        "refs":                 "this work references it",
        "governed_by-of-task":  "governs how this work is done",
        "neighbor-of-task":     "sits beside it in the graph",
        "type-sibling":         "another document of the same kind",
        "walk-hop-from":        "reachable through the graph",
    }.get(relation)
    if phrase is None:
        phrase = relation.replace("_", " ").replace("-", " ") or "related"
    if distance in (None, 0):
        return phrase
    return f"{phrase} · {'1 hop' if distance == 1 else f'{distance} hops'} away"


# --------------------------------------------------------------------------- #
# READING — Stage C. The only part of this tool that can spend money.          #
# --------------------------------------------------------------------------- #

#: How many documents one read takes. Read off Stage C rather than restated:
#: two copies of a batch size are two batch sizes waiting to disagree. It is
#: also NOT tuned upward to compensate for a low eligibility rate — a bigger
#: circle at a low rate spends more to leave more out.
K_READ = stage_c.K_SURVIVORS

#: The closed vocabulary of reasons a ranked survivor was not read. These are
#: FIELDS, not prose: the renderers consume the list and print one line per
#: entry, so a dropped document cannot be lost in a sentence a reader skims.
#:
#: Four reasons and no fifth. There is deliberately no "ineligible" here —
#: every entry says which of four separate problems cost the reader this
#: document, because they have four different fixes and one bucket would hide
#: which one is actually biting.
DROP_UNGOVERNED = "no-governed-body"
DROP_IMPORTED = "imported"
DROP_BATCH = "outside-the-batch"
DROP_SPEND = "over-the-call-ceiling"

_DROP_SENTENCE = {
    DROP_UNGOVERNED: (
        "the reader only opens governed bodies under vault/files, and this is "
        "not one"
    ),
    DROP_IMPORTED: (
        "it came into the studio from outside, so its words are not ours to send"
    ),
    DROP_BATCH: f"the reader takes {K_READ} at a time and this one fell outside",
    DROP_SPEND: "adding it would push the one batched call past its spend ceiling",
}

#: Room left in the C2 estimate for the brief, which does not exist yet when
#: the batch is priced, and for the guard's one repair call, which carries the
#: rejected spans on top of the same bodies. Both are bounded — the brief by
#: Stage C's own response ceiling, a repair by the guard's span bound times a
#: batch — so this is an allowance, not a guess.
_C2_ALLOWANCE_BYTES = stage_c.RESPONSE_MAX_BYTES + 8 * 1024

#: The three marks of an outside origin, read off a governed file's own
#: frontmatter. ``source_hash`` is the import walker's provenance stamp: it
#: records the digest of the file the artifact was carried in FROM, so nothing
#: the studio wrote can have one. It is the structural mark of the three —
#: ``type`` and ``extraction_scope`` are labels and an edit can move them.
_IMPORTED_MARKS = (
    re.compile(r"^source_hash:", re.MULTILINE),
    re.compile(r"^type:\s*['\"]?external-artifact['\"]?\s*$", re.MULTILINE),
    re.compile(r"^extraction_scope:\s*['\"]?external['\"]?\s*$", re.MULTILINE),
)


@dataclass(frozen=True)
class MeteredEdge:
    """Where a read's money comes from, and who answers the call.

    Every default here is the real one: the real Studio's spend ledger, the
    real policy, the real provider. The fields exist because Stage C's metered
    edge takes each of them as an injection point, and a test that cannot
    substitute the provider is a test that spends money to run.
    """

    studio_root: Path = ROOT
    run_uid: Optional[str] = None
    provider_call: Any = None
    policy_resolver: Any = None
    clock: Any = None
    reservation_id_factory: Any = None
    environment: Optional[Mapping[str, str]] = None


@dataclass(frozen=True)
class _TaskSource:
    """The task's own words, for C1's brief. Duck-typed by Stage C.

    ``body`` is the task's on-disk body cut to whatever the brief's route can
    afford — see :func:`_fit`. ``body_bytes`` and ``body_bytes_total`` travel
    with it so the block can say when the brief was written from part of a task
    rather than all of it; a brief silently written from a third of its task is
    a yardstick nobody knows is short.
    """

    uid: str
    title: str
    body: str
    links: tuple
    body_bytes: int
    body_bytes_total: int


def _imported(uid: str, rec: dict) -> bool:
    """Did this entry's words come from outside the studio?

    THIS IS NOT ``extraction_scope``, and keeping the two apart is the point.
    ``extraction_scope`` answers "may this go on the website", which is a
    publishing question; it is load-bearing for the website and is not widened
    here. Whether a document may cross to a model provider is a different
    question with a different answer, and deriving one from the other is what
    made 2,400 agent-authored records ineligible for a reason that had nothing
    to do with models.

    So: agent-authored governed content defaults to eligible, because every
    word of it was written by a model in the first place and withholding it now
    protects nothing. What is carved out is content with a genuine outside
    origin — the imported decks, Word files and PDFs — and it is recognised by
    three independent marks, because any one of them can be edited away:

      * the capsule type the importer assigns (``type: external-artifact``),
      * the ``external`` publishing label, and
      * the importer's own ``source_hash`` provenance stamp, which records the
        digest of the file the artifact came in FROM and which nothing the
        studio authored can have.

    Any one mark is enough. They are read from the index row AND from the
    file's own frontmatter, because a governed file with no index row at all is
    still a document with an origin, and the safe answer to "I cannot tell" is
    the one that keeps the bytes at home.
    """

    if rec.get("type") == "external-artifact":
        return True
    if (rec.get("extraction_scope") or "").strip().casefold() == "external":
        return True
    path = FILES / f"{uid}.md"
    if not path.is_file():
        return False
    head = path.read_text(errors="ignore")[:8192]
    if not head.startswith("---"):
        return False
    fence = head.find("\n---", 3)
    front = head[3:fence if fence > 0 else None]
    return any(mark.search(front) for mark in _IMPORTED_MARKS)


def egress_class(uid: str, records: dict) -> str:
    """The policy segment class Stage C's egress gate reads for ``uid``.

    Returns the OS class for anything that may cross to a provider and the
    private class for anything that may not. Handed to Stage C as its
    ``segment_class_of``, so AC5's gate refuses by name on anything this call
    marks private — which is why the read set is filtered by the SAME function
    before Stage C sees it. Belt and braces on purpose: the filter decides what
    is offered, the gate decides what is allowed, and if they ever disagree the
    gate wins and says so rather than letting a byte through.

    The governed body is what is classified, so a document with no governed
    body is private by default. That is not an egress judgement about it; there
    is simply nothing to send, and the read set drops it under its own reason
    before this is ever consulted.
    """

    if not (FILES / f"{uid}.md").is_file():
        return "private"
    if _imported(uid, records.get(uid) or {}):
        return "private"
    return vp.OS_SEGMENT


def _read_set(items: list, records: dict) -> tuple[list, list]:
    """Split the ranked survivors into what can be read and what cannot.

    Returns ``(uids, dropped)``. Two gates here and two more downstream, each
    with its own reason, and the reasons stay separate because they are
    separate problems with separate fixes: no governed body on disk is a
    substrate-shape problem, an imported artifact is an egress decision, the
    batch bound is Stage C's K, and the spend trim is the call ceiling.

    Note what is NOT a gate. Whether the current index projection carries the
    entry decides nothing — over half the ranked survivors in this vault are
    archived rows, and an archived governed file is a file.
    """

    keep, dropped = [], []
    for item in items:
        uid = item["uid"]
        if not (FILES / f"{uid}.md").is_file():
            dropped.append({**_named(item, records), "reason": DROP_UNGOVERNED})
        elif egress_class(uid, records) != vp.OS_SEGMENT:
            dropped.append({**_named(item, records), "reason": DROP_IMPORTED})
        else:
            keep.append(item)
    for item in keep[K_READ:]:
        dropped.append({**_named(item, records), "reason": DROP_BATCH})
    return [item["uid"] for item in keep[:K_READ]], dropped


def _text(value) -> str:
    """One index field as a string, or empty if it is not one.

    Index rows are JSON, and a field that is a list or a null in one row is a
    string in the next. A name is only a name if it is text. Canonical titles
    arrive losslessly from the composed index; callers trim display whitespace
    at the point of use without rereading source files.
    """

    return value if isinstance(value, str) else ""


def _named(item: dict, records: dict) -> dict:
    """Name the thing, then cite it from the current + archive union.

    ``archived`` travels as a field rather than a suffix on the title, so the
    read renderers can state lifecycle without either renderer parsing a
    display string. The ranked list also reads the union, so archived members
    retain their real title, type, status and governed path there.

    ``where`` is the entry's real path, and it is EMPTY when there is no real
    path to give. The citation list below prints ``vault/files/<uid>.md`` for
    every row because that is the shape it has always had, but next to "this
    is not a governed body" the same string is a contradiction: it names a
    file to explain that the file is not there. An empty ``where`` is how the
    renderers know to say the reason and nothing else.
    """

    uid = item["uid"]
    rec = records.get(uid) or {}
    title = _text(rec.get("title")).strip()
    if not title:
        # Some governed types keep their name in another field. A memory
        # entry's is ``context`` — that is where the type puts its name, not a
        # workaround for a missing one. Printing "an entry no index carries"
        # over a record the index describes in a sentence is the UID habit
        # wearing a different hat, and it renders eight distinct documents as
        # eight copies of the same line.
        title = next(
            (value for value in
             (_text(rec.get("description")).strip(),
              _text(rec.get("context")).strip())
             if value),
            "",
        )
    if not title:
        supplied = _text(item.get("title")).strip()
        title = "" if supplied.endswith("— not in the index") else supplied
    if not title:
        title = ("an entry the index carries under no name" if rec
                 else "an entry no index carries")
    where = _text(rec.get("path")).strip()
    if not where and (FILES / f"{uid}.md").is_file():
        where = f"vault/files/{uid}.md"
    return {
        "uid": uid,
        "title": title,
        "where": where,
        "archived": bool(rec) and index_surfaces.is_archive_record(rec),
    }


def _admits(task: str, payload: dict, *, system: str, max_tokens: int,
            allowance: int = 0) -> bool:
    """Would the metered edge admit this request?

    Prices the request through the SHIPPED admission arithmetic — the same
    serializer and the same worst-case pricer :mod:`lib.metered_model` uses —
    against the same route ceiling. Nothing about the ceiling is restated here;
    a second copy of it is a second ceiling. If this reconstruction ever drifts
    from the payload Stage C actually sends, the only consequence is that the
    edge refuses the call by name, which is the safe direction to be wrong in.
    """

    model, ceiling = MODEL_ROUTES[task]
    request = llm.serialize_locked_request(
        task,
        [{"role": "user",
          "content": json.dumps(payload, sort_keys=True, ensure_ascii=False)}],
        max_tokens=max_tokens,
        system=system,
    )
    worst = loop_metering.worst_case_request_cost_nano_usd(
        model,
        request_bytes=len(request) + allowance,
        max_tokens=max_tokens,
        cache_mode="none",
    )
    return worst <= ceiling


def _fit(uid: str, title: str, body: str, links: tuple) -> Optional[_TaskSource]:
    """Cut the task's body down to what C1's route can afford, or give up.

    The brief runs on the cheap parse route, whose per-call ceiling is spent
    mostly on the edge's fixed request overhead: it admits roughly 2,400 bytes
    of task. Real task bodies run to a median of 1,788 bytes and a p75 of
    4,519, so more than a quarter of them would refuse outright — measured, not
    assumed, and the reason this function exists at all rather than the
    constant that would have shipped instead.

    Returns ``None`` when even an empty body will not admit, which means the
    title or the link list alone has overrun the ceiling. Refusing is right:
    there is no honest brief to write from nothing.
    """

    def fits(candidate: str) -> bool:
        return _admits(
            stage_c.C1_TASK_CLASS,
            {"task_uid": uid, "title": title, "body": candidate,
             "links": list(links)},
            system=stage_c.C1_SYSTEM_PROMPT,
            max_tokens=stage_c.C1_MAX_OUTPUT_TOKENS,
        )

    total = len(body.encode("utf-8"))
    if fits(body):
        return _TaskSource(uid, title, body, links, total, total)
    if not fits(""):
        return None
    low, high = 0, len(body)
    while low < high:
        middle = (low + high + 1) // 2
        if fits(body[:middle]):
            low = middle
        else:
            high = middle - 1
    kept = body[:low].rstrip()
    return _TaskSource(uid, title, kept, links,
                       len(kept.encode("utf-8")), total)


def _affordable(task_uid: str, uids: list, bodies: dict) -> tuple[list, list]:
    """Trim the batch from the tail until the one C2 call admits.

    Dropping the lowest-ranked first is the only ordering that does not throw
    away the ranking Stage B just computed. Every trim is named, because a
    batch quietly shortened to fit a budget is a partial answer wearing a whole
    one's clothes.
    """

    kept, cut = list(uids), []
    while kept:
        payload = {
            "brief": "",
            "task_uid": task_uid,
            "survivors": [
                {"uid": uid,
                 "body": bodies[uid][:stage_c.PER_BODY_INPUT_BYTE_CAP]
                 .decode("utf-8", errors="ignore")}
                for uid in kept
            ],
        }
        if _admits(stage_c.C2_TASK_CLASS, payload,
                   system=stage_c.C2_SYSTEM_PROMPT,
                   max_tokens=stage_c.C2_MAX_OUTPUT_TOKENS,
                   allowance=_C2_ALLOWANCE_BYTES):
            break
        cut.append(kept.pop())
    return kept, cut


def _spend(edge: MeteredEdge, policy, run_uid: str) -> dict:
    """What this run actually cost, read back off the spend ledger.

    The ledger and not the receipts, because a refused run has no receipts to
    return — Stage C raises, and C1's cost goes with it — while the ledger
    still holds every reservation the run made. Spend is the ledger's question
    to answer; this only asks it.
    """

    empty = {"spent_nano_usd": 0, "reserved_nano_usd": 0, "calls": []}
    root = Path(edge.studio_root) / metered_model.LEDGER_RELATIVE_PATH
    day = daily_spend.utc_day(edge.clock() if edge.clock else None)
    try:
        ledger = daily_spend.read_ledger(
            root,
            day=day,
            policy_uid=policy.uid,
            policy_version=policy.version,
            daily_ceiling_nano_usd=policy.daily_ceiling_nano_usd,
        )
    except Exception:
        return empty
    calls = []
    for record in ledger["reservations"].values():
        if record.get("run_uid") != run_uid:
            continue
        calls.append({
            "task": record.get("task"),
            "model": record.get("model"),
            "status": record.get("status"),
            "reserved_nano_usd": record.get("worst_case_nano_usd") or 0,
            "spent_nano_usd": record.get("actual_nano_usd") or 0,
        })
    calls.sort(key=lambda call: (call["task"] or "", call["model"] or ""))
    return {
        "spent_nano_usd": sum(call["spent_nano_usd"] for call in calls),
        "reserved_nano_usd": sum(call["reserved_nano_usd"] for call in calls),
        "calls": calls,
    }


def read_block(task_uid: str, task_title: str, items: list,
               viewer, deterministic, index_as_of: str,
               edge: MeteredEdge) -> dict:
    """Run Stage C over the readable survivors and return the block.

    Composes ``orient_deterministic``'s own output with
    :func:`lib.orient_stage_c.run_stage_c` directly rather than through
    ``distiller.orient``. Three reasons, all of them about not spending more or
    answering worse:

      * ``orient()`` hands Stage C the WHOLE ranked list, and Stage C refuses
        the entire run if any member of it may not cross. At today's rates that
        refuses almost every real task. The degraded read Metis ruled for —
        read what is eligible, name what is not — is not expressible there
        without changing ``lib/``, and changing ``lib/`` was not the job.
      * ``orient()`` also runs ``resolve_query`` and ``distill``, whose model
        edges this surface has no output for. Their spend is avoidable, and
        routing around a spend you do not need is not an optimisation.
      * ``distill`` runs AFTER Stage C, so a content-loader fault there discards
        a block that has already been paid for.

    Nothing about Stage C's guarantees is softened by the shorter path: R2's
    stamps, AC5's egress gate, AC7's one-read-per-body and Lock 2's guard are
    all enforced inside ``run_stage_c``, which is where they belong.
    """

    records = _all_records()
    # The heading above this block reads the current index and says "(unknown)"
    # for an archived task. The brief is written FROM the task's title, so a
    # placeholder there is not a cosmetic problem: it is the yardstick C1
    # judges every candidate span against.
    task_title = (records.get(task_uid) or {}).get("title") or task_title
    uids, dropped = _read_set(items, records)
    block = {
        "status": "nothing-eligible",
        "considered": len(items),
        "read": [],
        "dropped": dropped,
        "dropped_count": len(dropped),
        "brief": "",
        "spans": [],
        "spend": {"spent_nano_usd": 0, "reserved_nano_usd": 0, "calls": []},
        "refusal": None,
        "detail": None,
        "task_body_bytes": 0,
        "task_body_bytes_total": 0,
    }
    if not uids:
        return block

    # The task's own words cross the edge too. If the task itself came from
    # outside the studio, no amount of eligible survivors makes the brief
    # sendable — Stage C is handed no classifier for the task stub, so this is
    # the only place the question gets asked.
    if egress_class(task_uid, records) != vp.OS_SEGMENT:
        block["refusal"] = "TASK_NOT_OURS_TO_SEND"
        block["detail"] = (
            "the task itself came into the studio from outside, and the brief "
            "is written from the task's own words"
        )
        block["status"] = "refused"
        return block

    task_body = ""
    task_path = FILES / f"{task_uid}.md"
    if task_path.is_file():
        task_body = distiller.span_guard.match_domain_bytes(task_path).decode(
            "utf-8", errors="replace")
    links = tuple(
        str(link) for link in ((records.get(task_uid) or {}).get("member_of") or ())
    )
    source = _fit(task_uid, task_title, task_body, links)
    if source is None:
        block["refusal"] = "BRIEF_WILL_NOT_FIT"
        block["detail"] = (
            "the task's title and links alone overrun the brief route's "
            "per-call ceiling, so there is nothing to write a brief from"
        )
        block["status"] = "refused"
        return block
    block["task_body_bytes"] = source.body_bytes
    block["task_body_bytes_total"] = source.body_bytes_total

    reader = distiller.governed_body_reader(FILES)
    try:
        bodies = {uid: reader(uid) for uid in uids}
    except (OSError, ValueError) as error:
        block["refusal"] = "BODY_UNREADABLE"
        block["detail"] = str(error)
        block["status"] = "refused"
        return block
    uids, priced_out = _affordable(task_uid, uids, bodies)
    by_uid = {item["uid"]: item for item in items}
    dropped.extend(
        {**_named(by_uid[uid], records), "reason": DROP_SPEND}
        for uid in priced_out
    )
    block["dropped_count"] = len(dropped)
    if not uids:
        block["status"] = "nothing-eligible"
        return block

    resolve = edge.policy_resolver or metered_model.resolve_policy
    try:
        policy = resolve()
    except Exception as error:
        block["refusal"] = "POLICY_UNAVAILABLE"
        block["detail"] = str(error)
        block["status"] = "refused"
        return block

    run_uid = edge.run_uid or os.environ.get("TROPO_RUN_UID") or secrets.token_hex(4)
    binding = metered_model.RunBinding(
        run_uid=run_uid,
        gateway_url=metered_model.GATEWAY_URL,
        virtual_key=f"sk-virtual-tropo-{run_uid}",
        studio_root=Path(edge.studio_root),
    )
    ledger_root = Path(edge.studio_root) / metered_model.LEDGER_RELATIVE_PATH
    try:
        daily_spend.initialize_ledger(
            ledger_root,
            policy_uid=policy.uid,
            policy_version=policy.version,
            daily_ceiling_nano_usd=policy.daily_ceiling_nano_usd,
            day=daily_spend.utc_day(edge.clock() if edge.clock else None),
        )
    except Exception:
        # Today's ledger already exists, which is the ordinary case on every
        # run after the first of the day. Anything worse than that is not
        # swallowed, only deferred: the reservation two steps down hits the
        # same ledger, and the metered edge refuses it by name. Raising here
        # instead would replace a named refusal with a traceback.
        pass

    block["read"] = [_named(by_uid[uid], records) for uid in uids]
    try:
        stage = stage_c.run_stage_c(
            task_uid=task_uid,
            task_source=source,
            viewer=viewer,
            visible_segments=frozenset({vp.OS_SEGMENT}),
            index_as_of=index_as_of,
            ranking=distiller.StageBRanking(
                viewer=viewer,
                index_as_of=index_as_of,
                uids=tuple(uids),
                deterministic=deterministic,
            ),
            circle=tuple(
                member.uid for member in deterministic.circle.members
            ),
            body_reader=reader,
            segment_class_of=lambda uid: egress_class(uid, records),
            run_binding=binding,
            provider_call=edge.provider_call,
            policy_resolver=resolve,
            clock=edge.clock,
            reservation_id_factory=edge.reservation_id_factory,
            environment=edge.environment,
        )
    except stage_c.StageCRefusal as refusal:
        block["status"] = "refused"
        block["refusal"] = refusal.reason
        block["detail"] = refusal.message
        block["spend"] = _spend(edge, policy, run_uid)
        return block
    except Exception as error:
        # Past this line a reservation may already be held. A traceback here
        # would take the block down with it and the reader would never learn
        # what today's budget is now carrying, so the failure comes back as a
        # refusal like any other and the ledger is read either way.
        block["status"] = "refused"
        block["refusal"] = "READ_FAILED"
        block["detail"] = f"{type(error).__name__}: {error}"
        block["spend"] = _spend(edge, policy, run_uid)
        return block

    block["status"] = "read"
    block["brief"] = stage.c1_brief
    block["spans"] = [
        {
            **_named(by_uid[span.uid], records),
            # The source's own bytes. The guard threw the model's copy away.
            "text": span.span_text,
            "char_start": span.locator.char_start,
            "char_end": span.locator.char_end,
            "body_sha256": span.locator.body_sha256,
        }
        for span in stage.spans
    ]
    block["spend"] = _spend(edge, policy, run_uid)
    return block


# --------------------------------------------------------------------------- #
# Tier-0 deterministic recall (dev-spec 4883fa94 / cascade amendment cd946580). #
# Enumerate exhaustively where it's cheap; select only where it's expensive.    #
# Neither helper calls a model, reads a body, or consults a clock — both are    #
# pure functions of the index rows, so AC6 determinism holds by construction.  #
# --------------------------------------------------------------------------- #
def _when(rec: dict) -> str:
    """The record's modified (or created) date, normalised to YYYY-MM-DD."""

    return str(rec.get("modified") or rec.get("created") or "")[:10]


def _index_clock(records: Mapping) -> str:
    """The newest modified date across the index — the deterministic clock.

    Ages are measured against the substrate's own newest row, never against
    wall-clock now(), so identical commands stay byte-identical (AC6) while a
    stale rendered artifact still reads as exactly how far it lags the index.
    """

    newest = ""
    for rec in records.values():
        when = _when(rec)
        # Only real dates advance the clock — template rows carry literal
        # "[YYYY-MM-DD]" placeholders, and "[" out-sorts every digit.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", when) and when > newest:
            newest = when
    return newest


def _is_rendered_catalog(rec: dict) -> bool:
    """A rendered-catalog record: derived prose that does not re-render itself
    (the Writing Library TOC class — a73cef23 F6)."""

    if str(rec.get("subtype") or "").strip().lower() == "catalog":
        return True
    tags = {str(t).strip().lower() for t in (rec.get("tags") or ())}
    return bool(tags & {"catalog", "rendered", "front-desk"})


def _catalog_age_days(rec: dict, clock: str) -> Optional[int]:
    """Exact age of a rendered catalog vs the index clock, in days; None when
    the record is not a rendered catalog or either date is unparseable."""

    if not _is_rendered_catalog(rec):
        return None
    import datetime

    try:
        rendered = datetime.date.fromisoformat(_when(rec))
        newest = datetime.date.fromisoformat(clock)
    except ValueError:
        return None
    return (newest - rendered).days


def _is_archived(uid: str, rec: dict, current: Mapping) -> bool:
    """Archived by residence (archive index) OR by lifecycle (state field) —
    a row can sit in the current index with ``state: archived`` (the shells
    that outranked live series on 08-12 did exactly that)."""

    return uid not in current or str(rec.get("state") or "").strip().lower() == "archived"


def _one_hop_roster(task_uid: str, governed_ranks: Optional[Mapping] = None) -> dict:
    """Every node one structural hop from the task — complete, never truncated.

    The circle's membership budget cuts in (seed-distance, UID) order, so a
    high-UID live sibling can lose its seat to a low-UID archived shell before
    the ranker ever sees either (the 2026-08-12 miss, a73cef23 F1-corrected).
    This roster is the floor under that cut: names are ~80 bytes each, so the
    complete 1-hop truth is always affordable and always shown.
    """

    records = _all_records()
    current = _records()
    clock = _index_clock(records)
    ranks = governed_ranks or {}
    task = records.get(task_uid) or {}
    parents = [str(u) for u in (task.get("member_of") or ())]
    rows: dict = {}

    def add(uid: str, relation: str) -> None:
        rec = records.get(uid)
        if rec is None or uid == task_uid or uid in rows:
            return
        rows[uid] = {
            "uid": uid,
            "relation": relation,
            "type": rec.get("type") or "?",
            "status": rec.get("status") or "",
            "modified": _when(rec),
            "title": rec.get("title") or "(untitled)",
            "archived": _is_archived(uid, rec, current),
            # AC7 (lock-break form): the governed rank is DISCLOSED wherever
            # the complete evidence lists a node the ranked view may not show.
            "governed_rank": ranks.get(uid),
            "catalog_age_days": _catalog_age_days(rec, clock),
        }

    for parent in parents:
        add(parent, "parent")
    for uid, rec in records.items():
        member_of = [str(u) for u in (rec.get("member_of") or ())]
        if task_uid in member_of:
            add(uid, "child")
        elif parents and any(p in member_of for p in parents):
            add(uid, "sibling")
    ordered = sorted(
        rows.values(), key=lambda r: (r["modified"], r["uid"]), reverse=True
    )
    return {"nodes": ordered, "total": len(ordered)}


#: Tokens too generic to carry a keyword query on their own.
_TERM_STOPWORDS = frozenset(
    "the a an and or of for to in on with is are this that from into over".split()
)

#: Keyword hits carried in --json. The COUNT is always honest (``total``); the
#: list is bounded so a generic term cannot balloon the answer. Loud, not silent.
_KEYWORD_JSON_CAP = 200

#: Keyword hits shown in the text rendering (AC3: capped at 40, loudly).
_KEYWORD_TEXT_CAP = 40


def _query_terms(task_rec: dict, extra: tuple) -> tuple:
    """Deterministic term extraction: task title tokens + tags + caller terms."""

    raw = []
    for tok in re.split(r"[^0-9A-Za-z]+", str(task_rec.get("title") or "").lower()):
        if len(tok) >= 4 and tok not in _TERM_STOPWORDS:
            raw.append(tok)
    for tag in (task_rec.get("tags") or ()):
        tag_norm = str(tag).lower().strip()
        if tag_norm:
            raw.append(tag_norm)
        for tok in re.split(r"[^0-9A-Za-z]+", tag_norm):
            if len(tok) >= 4 and tok not in _TERM_STOPWORDS:
                raw.append(tok)
    for term in extra:
        term_norm = str(term).lower().strip()
        if term_norm:
            raw.append(term_norm)
    return tuple(sorted(set(raw)))


def _keyword_hits(task_uid: str, extra_terms: tuple,
                  governed_ranks: Optional[Mapping] = None) -> dict:
    """Tier-0 keyword recall over the current + archive index rows.

    The 2026-08-12 control (a73cef23 F2): a plain grep over the index found the
    complete live series the circle missed, in sub-second time, for $0. This is
    that grep made structural — always run, never model-dependent. Hits are
    UNRANKED next to the circle: match provenance travels with each hit so the
    reader (or a later Tier-1 triage) judges relevance from evidence.
    """

    records = _all_records()
    current = _records()
    ranks = governed_ranks or {}
    terms = _query_terms(records.get(task_uid) or {}, extra_terms)
    if not terms:
        return {"terms": [], "hits": [], "total": 0}
    hits = []
    for uid, rec in records.items():
        if uid == task_uid:
            continue
        haystacks = (
            ("title", str(rec.get("title") or "").lower()),
            ("description", str(rec.get("description") or "").lower()),
            ("tags", " ".join(str(t).lower() for t in (rec.get("tags") or ()))),
        )
        matched = sorted(
            term for term in terms if any(term in hay for _, hay in haystacks)
        )
        if not matched:
            continue
        hits.append({
            "uid": uid,
            "title": rec.get("title") or "(untitled)",
            "type": rec.get("type") or "?",
            "status": rec.get("status") or "",
            "modified": _when(rec),
            "archived": _is_archived(uid, rec, current),
            "terms_matched": matched,
            "governed_rank": ranks.get(uid),
        })
    hits.sort(key=lambda h: (h["modified"], h["uid"]), reverse=True)
    hits.sort(key=lambda h: len(h["terms_matched"]), reverse=True)
    return {"terms": list(terms), "hits": hits[:_KEYWORD_JSON_CAP],
            "total": len(hits)}


def orient(task_uid: str, k: int, principal: str,
           edge: Optional[MeteredEdge] = None,
           draw_budget: Optional[int] = None,
           extra_terms: tuple = ()) -> dict:
    projection = vp.ViewerProjection.from_repo_root(ROOT)
    circle_index = SqliteStructuralIndex(INDEX_SQLITE, index_as_of=INDEX_AS_OF)
    rank_index = SqliteRankIndex(INDEX_SQLITE)
    viewer = vp.Viewer(principal_uid=principal)

    # AC1 (4883fa94): the circle's membership budget is DECOUPLED from the
    # display count. Display-k as the draw budget let (seed-distance, UID)
    # membership order decide the contest before the ranker ran — "best first"
    # was only true among the UID-lucky. Draw wide, rank everything, show k.
    draw = max(int(draw_budget), k) if draw_budget else max(8 * k, 256)

    result = distiller.orient_deterministic(
        task_uid, viewer, draw,
        projection=projection, circle_index=circle_index, rank_index=rank_index,
    )
    if not result.ok:
        return {"ok": False, "error": str(result.error)}

    records = _records()
    clock = _index_clock(records)
    ranked_items = []
    for item in getattr(result.value, "items", ()):
        uid = getattr(item, "uid", "?")
        rec = records.get(uid, {})
        ranked = getattr(item, "ranked_member", None)
        circle_member = getattr(item, "circle_member", None)
        distance = getattr(circle_member, "distance", None)
        ranked_items.append({
            "uid": uid,
            # Compatibility fallback for older deterministic producers. The
            # current circle admits entries-backed members only and reports
            # unresolved edge targets through reference_observations instead.
            "title": rec.get("title") or f"{uid} — not in the index",
            "type": rec.get("type") or "unindexed",
            "status": rec.get("status") or "",
            "modified": _when(rec),
            "why": _describe(circle_member),
            "score": round(float(getattr(ranked, "score", 0) or 0), 3),
            "distance": distance,
            "stale": bool((rec.get("decay") or {}).get("stale")),
            "catalog_age_days": _catalog_age_days(rec, clock),
            "indexed": bool(rec),
        })
    # Governed-ranker order, exactly (4883fa94 lock-break, AC1): orchestration
    # must not become a second ranker, so there is NO post-sort here — not by
    # distance, not by recency. What the ranker ordered is what displays; the
    # roster and keyword sections below carry the complete evidence with each
    # node's governed rank disclosed (AC7), which is where a far-ranked live
    # node stays visible.
    items = ranked_items[:k]
    governed_ranks = {it["uid"]: n for n, it in enumerate(ranked_items, 1)}
    observations = [
        {
            "raw_target": getattr(observation, "raw_target", ""),
            "via": getattr(observation, "via", ""),
            "relation": getattr(observation, "relation", ""),
            "provenance": getattr(observation, "provenance", ""),
            "distance": getattr(observation, "distance", None),
            "classification": getattr(observation, "classification", ""),
        }
        for observation in getattr(result.value, "reference_observations", ())
    ]
    answer = {"ok": True, "task": task_uid,
              "task_title": (records.get(task_uid) or {}).get("title") or "(unknown)",
              "items": items,
              "ranked_total": len(ranked_items),
              "k": k,
              "draw_budget": draw,
              "one_hop": _one_hop_roster(task_uid, governed_ranks),
              "keyword_recall": _keyword_hits(task_uid, extra_terms,
                                              governed_ranks),
              "reference_observations": observations}
    # The paid branch, and the only one. Without ``edge`` the answer above is
    # the same deterministic citation + observation answer and no metered edge
    # is constructed, let alone reached — "did this cost money?" is answerable
    # from whether the key below is present at all. Observations are never
    # passed to read_block: Stage C receives ranked members only.
    if edge is not None:
        answer["read"] = read_block(
            task_uid, answer["task_title"], items,
            viewer, result.value, INDEX_AS_OF, edge,
        )
    return answer


def _usd(nano: int) -> str:
    return f"${nano / 1_000_000_000:.4f}"


#: What each metered call was FOR, in the reader's words rather than the policy
#: route's. "parse-query" and "distill" are the spend policy's names for two
#: model routes; neither of them tells Mike which part of the answer he paid
#: for.
_CALL_PURPOSE = {
    stage_c.C1_TASK_CLASS: "reading the task and writing the brief",
    stage_c.C2_TASK_CLASS: "choosing which sentences answer it",
}


def _spend_lines(spend: dict) -> list:
    """What the read cost, always stated, including when it cost nothing."""

    spent, reserved = spend["spent_nano_usd"], spend["reserved_nano_usd"]
    if not spend["calls"]:
        return ["  Nothing was spent — no model was reached."]
    lines = []
    if spent:
        lines.append(
            f"  This read cost {_usd(spent)}. {_usd(reserved)} was held "
            f"against today's budget to cover it."
        )
    else:
        lines.append(
            f"  Nothing was spent. {_usd(reserved)} was held against today's "
            f"budget and stays held, because the call was made and did not "
            f"come back."
        )
    for call in spend["calls"]:
        purpose = _CALL_PURPOSE.get(call["task"], call["task"] or "a model call")
        lines.append(
            f"    · {purpose} — {call['model']} — {_usd(call['spent_nano_usd'])}"
        )
    return lines


#: Archived entries are ordinary resolvable members in both the ranked list and
#: the read block. Carry the lifecycle note without claiming the union-backed
#: list below lost their metadata.
_ARCHIVED_NOTE = "archived"


def _cite(entry: dict) -> str:
    """One entry's path line, with the archive note when it needs one."""

    return entry["where"] + (f" · {_ARCHIVED_NOTE}" if entry["archived"] else "")


def _dropped_lines(read: dict) -> list:
    """Every survivor that was not read, one line each, by name.

    Driven off the list rather than the count, so a document cannot go missing
    from the roster while the number still looks right — and so the roster
    cannot be skimmed past the way a sentence can.
    """

    dropped = read["dropped"]
    if not dropped:
        return []
    lines = [f"  {len(dropped)} of the {read['considered']} were not read:"]
    for entry in dropped:
        lines.append(f"    · {entry['title']}")
        reason = _DROP_SENTENCE[entry["reason"]]
        lines.append(
            f"      {entry['where']} — {reason}" if entry["where"]
            else f"      {reason}"
        )
    return lines


def _count(n: int) -> str:
    """"1 document" / "3 documents". A tool that says "The 1 documents" is
    reporting a template, and a reader hears the template rather than the
    number."""

    return f"{n} document" if n == 1 else f"{n} documents"


def _crossed(read: dict) -> bool:
    """Did the survivor bodies actually leave this machine?

    C1 sends the task's own words and nothing else; no survivor body crosses
    until C2. So a run that stopped at C1 opened its documents from disk and
    sent none of them, and the difference is the one fact in a refused block
    a reader might act on. Read off the spend calls, because a body crossing
    the edge and a reservation against that route are the same event.
    """

    return any(call["task"] == stage_c.C2_TASK_CLASS
               for call in read["spend"]["calls"])


def _roster_head(read: dict) -> str:
    """What happened to the documents the read opened, in one phrase."""

    documents = _count(len(read["read"]))
    if read["status"] == "read":
        return f"the {documents} this was read from:"
    if _crossed(read):
        return f"the {documents} this had sent when it stopped:"
    return f"the {documents} this had opened, and had not sent, when it stopped:"


def _roster_lines(read: dict) -> list:
    """The documents that were actually opened, named.

    Not the same list as the quotes. A batched read opens every document it
    can afford and the model quotes from whichever ones answer; the rest were
    still read and still paid for, and a reader judging the answer needs to
    know which documents were in front of it. Present on a refused run too,
    where it says what had crossed — or had not — when the run stopped.
    """

    if not read["read"]:
        return []
    head = _roster_head(read)
    lines = [f"  {head[0].upper()}{head[1:]}"]
    for entry in read["read"]:
        lines.append(f"    · {entry['title']}")
        lines.append(f"      {_cite(entry)}")
    return lines


def _read_lines(read: dict) -> list:
    """Stage C's answer, above the citation list.

    Three shapes, and the difference between them is the whole point. A run
    that read something leads with what it says. A run that could read nothing
    says exactly that, in those words, and never lets the citation list stand
    under a heading that implies an answer — a list of documents under a
    confident heading is indistinguishable from a distilled one. A run that was
    refused names the gate that refused it.
    """

    lines = [""]
    if read["status"] == "read":
        lines.append(f"  WHAT THEY SAY — read from {len(read['read'])} of "
                     f"{_count(read['considered'])}")
        lines.append("")
        lines.extend(
            textwrap.wrap(read["brief"], width=76,
                          initial_indent="  ", subsequent_indent="  ")
        )
        lines.append("")
        for span in read["spans"]:
            lines.extend(
                textwrap.wrap(f"“{span['text']}”", width=74,
                              initial_indent="    ", subsequent_indent="    ")
            )
            lines.append(
                f"        — {span['title']}"
            )
            lines.append(
                f"          {span['where']}, characters "
                f"{span['char_start']}–{span['char_end']}"
            )
            if span["archived"]:
                lines.append(f"          {_ARCHIVED_NOTE}")
            lines.append("")
        if not read["spans"]:
            lines.append("  The brief is above; no sentence in those documents "
                         "survived the guard,")
            lines.append("  so there is nothing here quoted from them.")
            lines.append("")
    elif read["status"] == "nothing-eligible":
        lines.append("  NOTHING HERE WAS READ")
        lines.append("")
        lines.append("  No survivor was eligible to be read. The picture below "
                     "is where to look;")
        lines.append("  it has not been read and it is not an answer.")
        lines.append("")
    else:
        lines.append("  THE READ DID NOT HAPPEN")
        lines.append("")
        lines.extend(
            textwrap.wrap(f"{read['refusal']} — {read['detail']}", width=76,
                          initial_indent="  ", subsequent_indent="  ")
        )
        lines.append("")
        lines.append("  Nothing below has been read. It is where to look, not "
                     "what they say.")
        lines.append("")
    lines.extend(_roster_lines(read))
    if read["read"]:
        lines.append("")
    lines.extend(_dropped_lines(read))
    if read["dropped"]:
        lines.append("")
    if read["task_body_bytes_total"] > read["task_body_bytes"] > 0:
        lines.append(
            f"  The brief was written from the first {read['task_body_bytes']} "
            f"of the task's {read['task_body_bytes_total']} bytes — the brief's"
        )
        lines.append("  route cannot afford the whole of it.")
        lines.append("")
    lines.extend(_spend_lines(read["spend"]))
    lines.append("")
    return lines


def render_librarian_feed(answer: dict, body_budget: int) -> str:
    """Librarian L1 (d317f532 AC1): one feedable artifact — the deterministic
    evidence exactly as rendered, then the bodies of the top-ranked governed
    documents up to ``body_budget`` characters. Content past the budget is
    NAMED, never silently dropped. Deterministic given the index snapshot:
    same inputs, byte-identical artifact."""

    parts = [
        "# LIBRARIAN FEED — orientation evidence + governed bodies\n",
        f"task: {answer['task']} · {answer.get('task_title', '')}\n",
        "contract: you are a session librarian. You never write. You answer\n"
        "only with citations by UID from THIS feed. If the answer is not in\n"
        "your context, say 'not in my context' — never guess. You inherit\n"
        "AGENT-ORIENTATION's boundaries: an index row is a pointer; absence\n"
        "of evidence here is not evidence of absence in the studio.\n",
        "\n## EVIDENCE (deterministic tiers — where to look and why)\n",
        render_text(answer),
        "\n## BODIES — top-ranked governed documents, in ranked order\n",
    ]
    spent = 0
    included, excluded = [], []
    # The task's own body ALWAYS leads — a task is not its own graph
    # neighbour, so ranking alone omits the one document every question
    # is about. Found by the librarian's first honest "not in my context"
    # (2026-08-15, first live exchange).
    task_uid = str(answer.get("task", ""))
    task_path = FILES / f"{task_uid}.md"
    if task_path.is_file():
        body = task_path.read_text(encoding="utf-8", errors="replace")
        if len(body) <= body_budget:
            spent += len(body)
            included.append(task_uid)
            parts.append(
                f"\n### {task_uid} · vault/files/{task_uid}.md · THE TASK "
                f"ITSELF — read first\n\n{body}\n"
            )
        else:
            excluded.append((task_uid, "task body alone exceeds the budget"))
    for item in answer.get("items", ()):
        uid = item.get("uid", "")
        path = FILES / f"{uid}.md"
        if not path.is_file():
            excluded.append((uid, "no governed body under vault/files"))
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        if spent + len(body) > body_budget:
            excluded.append((uid, f"body budget ({body_budget} chars) reached"))
            continue
        spent += len(body)
        included.append(uid)
        parts.append(
            f"\n### {uid} · vault/files/{uid}.md · {item.get('type','?')}"
            f" · {item.get('status','?')}\n\n{body}\n"
        )
    parts.append(
        f"\n## FEED LEDGER — honest accounting\n"
        f"bodies included: {len(included)} ({', '.join(included) or 'none'})\n"
        f"body characters: {spent} of budget {body_budget}\n"
    )
    if excluded:
        parts.append("excluded, by name — ask your executive to feed these "
                     "separately if needed:\n")
        for uid, why in excluded:
            parts.append(f"  - {uid}: {why}\n")
    else:
        parts.append("excluded: none\n")
    parts.append("\nThe evidence section's one-hop roster is COMPLETE; the "
                 "bodies above are a budgeted selection. Cite accordingly.\n")
    return "".join(parts)


def render_text(answer: dict) -> str:
    if not answer["ok"]:
        return f"orient could not answer: {answer['error']}"
    lines = [
        "",
        f"  WHERE THIS STANDS — {answer['task_title']}",
        f"  {answer['task']}",
    ]
    # AC1 + AC8 (4883fa94): both budgets and the tiers that ran, stated up top,
    # and the claim's scope stated with them — this is orientation evidence,
    # never an answer to the caller's substantive task.
    tier = ("deterministic tiers + read tier below"
            if "read" in answer else "deterministic tiers only — 0 model calls")
    if answer.get("draw_budget"):
        lines.append(
            f"  drew up to {answer['draw_budget']} candidates, ranked "
            f"{answer.get('ranked_total', len(answer['items']))}, showing top "
            f"{len(answer['items'])} — {tier}"
        )
        lines.append(
            "  orientation evidence only — selecting evidence does not answer"
            " the caller's task"
        )
    if answer.get("read_preflight_refusal"):
        lines.extend([
            "",
            "  THE READ DID NOT HAPPEN — " + answer["read_preflight_refusal"],
        ])
    if "read" in answer:
        lines.extend(_read_lines(answer["read"]))
    lines.extend([
        "",
        f"  {len(answer['items'])} documents make up the picture, best first.",
        "",
    ])
    for n, it in enumerate(answer["items"], 1):
        flag = "  ⚠ flagged stale" if it["stale"] else ""
        when = f"  ·  {it['modified']}" if it.get("modified") else ""
        lines.append(f"  {n:2}. {it['title']}")
        lines.append(f"      {it['type']}{'  ·  ' + it['status'] if it['status'] else ''}{when}  ·  {it['why']}{flag}")
        lines.append(f"      vault/files/{it['uid']}.md")
        lines.append("")
    one_hop = answer.get("one_hop") or {}
    if one_hop.get("nodes"):
        lines.append(
            f"  ONE HOP FROM THIS — all {one_hop['total']} nodes, complete and"
        )
        lines.append("  newest first, with governed rank disclosed when drawn.")
        lines.append("  The ranked picture above is a selection; this is the whole neighbourhood.")
        lines.append("")
        for row in one_hop["nodes"]:
            arch = "  [archived]" if row["archived"] else ""
            when = row["modified"] or "undated"
            rank = row.get("governed_rank")
            ranked = (f" · governed rank {rank}" if rank
                      else " · unranked (outside the draw)")
            age = row.get("catalog_age_days")
            catalog = (f" · rendered catalog, {age} days behind the newest index row"
                       if age is not None else "")
            lines.append(
                f"  - {row['uid']}  {row['relation']:7}  {row['type']}"
                f" · {row['status'] or '?'} · {when}{ranked}{catalog}{arch}"
            )
            lines.append(f"      {row['title']}")
        lines.append("")
    recall = answer.get("keyword_recall") or {}
    if recall.get("terms"):
        shown = recall["hits"][:_KEYWORD_TEXT_CAP]
        lines.append(
            f"  KEYWORD HITS — deterministic, unranked. {recall['total']} rows"
        )
        lines.append(
            f"  match the task's own words; showing {len(shown)}."
        )
        lines.append(f"  terms: {', '.join(recall['terms'])}")
        lines.append("")
        for hit in shown:
            arch = "  [archived]" if hit["archived"] else ""
            when = hit["modified"] or "undated"
            rank = hit.get("governed_rank")
            ranked = f" · governed rank {rank}" if rank else ""
            lines.append(
                f"  - {hit['uid']}  {hit['type']} · {hit['status'] or '?'}"
                f" · {when}{ranked}{arch}  ({', '.join(hit['terms_matched'])})"
            )
            lines.append(f"      {hit['title']}")
        if recall["total"] > len(shown):
            lines.append(
                f"  … and {recall['total'] - len(shown)} more not shown —"
                " tighten with --terms."
            )
        lines.append("")
    observations = answer.get("reference_observations", ())
    if observations:
        lines.append("  REFERENCE OBSERVATIONS — not indexed or ranked")
        lines.append("")
        for observation in observations:
            distance = observation.get("distance")
            hops = "" if distance is None else (
                "1 hop" if distance == 1 else f"{distance} hops"
            )
            details = " · ".join(
                value
                for value in (
                    observation.get("classification") or "unresolved-reference",
                    observation.get("provenance") or "",
                    hops,
                )
                if value
            )
            lines.append(f"  - {observation.get('raw_target', '')}")
            lines.append(f"      {details}")
        lines.append("")
    if "read" not in answer:
        lines.append("  This says where to look and why. It does not say what they say —")
        lines.append("  that is Stage C, and it runs on --read. Checkpoint 5e6652ac.")
    elif answer["read"]["status"] == "read":
        lines.append("  Every sentence in quotation marks above is the source's own bytes,")
        lines.append("  cut from the file by the guard — never the model's words. It chose")
        lines.append("  which sentences; the files said them. Checkpoint 5e6652ac.")
    else:
        lines.append("  Nothing above was read. This is where to look and why, which is not")
        lines.append("  the same thing as an answer. Checkpoint 5e6652ac.")
    lines.append("")
    return "\n".join(lines)


def _board_read(read: dict) -> str:
    """The same read, in the same three shapes, for the board.

    Renders from the same block the text renderer consumes, so the two surfaces
    cannot come to different conclusions about what was read or what was left
    out. New content is escaped; the citation rows below are left exactly as
    they were, because changing how an existing row is emitted would change the
    free path's output.
    """

    def esc(value) -> str:
        return html.escape(str(value), quote=False)

    # The read's own styles travel with the read, so a board rendered without
    # it is byte-for-byte the board that shipped.
    parts = ["""<style>
 .read{margin-bottom:38px}
 .read .eyebrow.warn{color:var(--fg2)}
 .brief{font-size:17px;color:var(--fg);margin:14px 0 22px}
 blockquote{border-left:2px solid var(--ember);padding:2px 0 2px 16px;margin:0 0 18px;
  font-size:16px;color:var(--fg)}
 blockquote cite{display:block;font-family:var(--mono);font-size:11.5px;
  color:var(--fg3);font-style:normal;margin-top:8px}
 blockquote cite a{color:var(--fg3)}
 .drop-head{font-family:var(--mono);font-size:11.5px;color:var(--fg3);
  margin:22px 0 8px;text-transform:uppercase;letter-spacing:.08em}
 ul.drops{list-style:none}
 ul.drops li{border-top:1px solid var(--line);padding:10px 0 10px 0}
 ul.drops li:before{content:none}
 ul.drops b{font-size:14px;color:var(--fg2);font-weight:500}
 .spend{font-family:var(--mono);font-size:11.5px;color:var(--fg3);margin-top:20px}
</style>
<section class="read">"""]
    if read["status"] == "read":
        parts.append(
            f'<div class="eyebrow">◑ &nbsp;what they say — read from '
            f'{len(read["read"])} of {_count(read["considered"])}</div>'
        )
        parts.append(f'<p class="brief">{esc(read["brief"])}</p>')
        for span in read["spans"]:
            parts.append(
                f'<blockquote>{esc(span["text"])}'
                f'<cite>{esc(span["title"])} &nbsp;·&nbsp; '
                f'<a href="../../{esc(span["where"])}">'
                f'{esc(span["where"])}</a> &nbsp;·&nbsp; '
                f'characters {span["char_start"]}–{span["char_end"]}'
                + (f' &nbsp;·&nbsp; {esc(_ARCHIVED_NOTE)}' if span["archived"] else "")
                + "</cite></blockquote>"
            )
        if not read["spans"]:
            parts.append(
                '<p class="brief">No sentence in those documents survived the '
                "guard, so nothing here is quoted from them.</p>"
            )
    elif read["status"] == "nothing-eligible":
        parts.append('<div class="eyebrow warn">◒ &nbsp;nothing here was read</div>')
        parts.append(
            '<p class="brief">No survivor was eligible to be read. What follows '
            "is where to look. It has not been read and it is not an answer.</p>"
        )
    else:
        parts.append('<div class="eyebrow warn">◒ &nbsp;the read did not happen</div>')
        parts.append(
            f'<p class="brief">{esc(read["refusal"])} — {esc(read["detail"])}. '
            "Nothing below has been read.</p>"
        )
    if read["read"]:
        parts.append(
            f'<p class="drop-head">{esc(_roster_head(read))}</p>'
            '<ul class="drops">'
        )
        for entry in read["read"]:
            parts.append(
                f'<li><b>{esc(entry["title"])}</b>'
                f'<span class="m">{esc(_cite(entry))}</span></li>'
            )
        parts.append("</ul>")
    if read["dropped"]:
        parts.append(
            f'<p class="drop-head">{len(read["dropped"])} of the '
            f'{read["considered"]} were not read:</p><ul class="drops">'
        )
        for entry in read["dropped"]:
            reason = esc(_DROP_SENTENCE[entry["reason"]])
            parts.append(
                f'<li><b>{esc(entry["title"])}</b><span class="m">'
                + (f'{esc(entry["where"])} — {reason}' if entry["where"]
                   else reason)
                + "</span></li>"
            )
        parts.append("</ul>")
    spend = read["spend"]
    parts.append(
        f'<p class="spend">{esc(" ".join(line.strip() for line in _spend_lines(spend)))}</p>'
    )
    parts.append("</section>\n")
    return "\n".join(parts)


def render_board(answer: dict) -> str:
    rows = "\n".join(
        f'<li><a href="../../vault/files/{html.escape(str(it["uid"]), quote=True)}.md">'
        f'<b>{html.escape(str(it["title"]))}</b></a>'
        f'<span class="m">{html.escape(str(it["type"]))}'
        f'{html.escape(" · " + str(it["status"])) if it["status"] else ""}'
        f' · {html.escape(str(it["why"]))}'
        f'{" · flagged stale" if it["stale"] else ""}</span></li>'
        for it in answer["items"]
    )
    observation_rows = "\n".join(
        "<li>"
        f'<b><code>{html.escape(str(observation.get("raw_target", "")))}</code></b>'
        f'<span class="m">{html.escape(str(observation.get("classification") or "unresolved-reference"))}'
        f' · {html.escape(str(observation.get("provenance") or ""))}'
        f' · {html.escape(str(observation.get("distance")))} hop'
        f'{"s" if observation.get("distance") != 1 else ""}</span>'
        "</li>"
        for observation in answer.get("reference_observations", ())
    )
    observations_section = ""
    if observation_rows:
        observations_section = f"""
<section class="observations">
<h2>Reference observations</h2>
<p>Visible references that are not indexed documents. They were not ranked.</p>
<ul>
{observation_rows}
</ul>
</section>"""
    task_title = html.escape(str(answer["task_title"]))
    task_uid = html.escape(str(answer["task"]))
    read = _board_read(answer["read"]) if "read" in answer else ""
    if "read" not in answer:
        footer = (
            "This says where to look and why, drawn from the studio's own graph.<br>\n"
            "It does not say what these documents say — that is Stage C, and it runs on --read.<br>\n"
            "Checkpoint 5e6652ac · no model was called · nothing was spent"
        )
    elif answer["read"]["status"] == "read":
        footer = (
            "Every quotation above is the source's own bytes, cut from the file by the guard.<br>\n"
            "The model chose which sentences; the files said them.<br>\n"
            "Checkpoint 5e6652ac · "
            + html.escape(_usd(answer["read"]["spend"]["spent_nano_usd"]), quote=False)
            + " spent"
        )
    else:
        footer = (
            "Nothing above was read. This is where to look and why, which is not an answer.<br>\n"
            "Checkpoint 5e6652ac · "
            + html.escape(_usd(answer["read"]["spend"]["spent_nano_usd"]), quote=False)
            + " spent"
        )
    return f"""<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Where this stands — {task_title}</title>
<style>
 :root{{--bg:#0A0D12;--surf:#161A21;--fg:#EDEFF2;--fg2:#B7BCC4;--fg3:#8C95A1;
  --line:#3A414C;--ember:#FF5E1A;
  --sans:"Inter Tight",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
  --disp:"Space Grotesk","Inter Tight",system-ui,sans-serif}}
 *{{box-sizing:border-box;margin:0;padding:0}}
 body{{background:var(--bg);color:var(--fg);font-family:var(--sans);line-height:1.55;
  max-width:860px;margin:0 auto;padding:52px 26px 96px}}
 .eyebrow{{font-family:var(--mono);font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--ember)}}
 h1{{font-family:var(--disp);font-size:clamp(28px,4.4vw,42px);font-weight:700;letter-spacing:-.03em;
  line-height:1.08;margin:14px 0 8px}}
 .sub{{font-family:var(--mono);font-size:12px;color:var(--fg3);margin-bottom:34px}}
 ol{{list-style:none;counter-reset:i}}
 li{{counter-increment:i;border-top:1px solid var(--line);padding:16px 0 16px 44px;position:relative}}
 li:before{{content:counter(i);position:absolute;left:0;top:16px;font-family:var(--mono);
  font-size:12px;color:var(--fg3)}}
 li a{{color:var(--fg);text-decoration:none;font-size:17px;border-bottom:1px solid transparent}}
 li a:hover{{border-bottom-color:var(--ember)}}
 .m{{display:block;font-family:var(--mono);font-size:11.5px;color:var(--fg3);margin-top:6px}}
 section.observations{{margin-top:38px}}
 section.observations h2{{font-family:var(--disp);font-size:20px;margin-bottom:6px}}
 section.observations p{{color:var(--fg2);font-size:14px;margin-bottom:12px}}
 section.observations code{{font-family:var(--mono);font-size:13px}}
 footer{{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);
  font-family:var(--mono);font-size:11.5px;color:var(--fg3);line-height:1.8}}
</style></head><body>
<div class="eyebrow">◐ &nbsp;orient</div>
<h1>Where this stands</h1>
<div class="sub">{task_title} &nbsp;·&nbsp; {task_uid} &nbsp;·&nbsp; {len(answer['items'])} documents, best first</div>
{read}<ol>
{rows}
</ol>
{observations_section}
<footer>
{footer}
</footer>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ask the studio where a piece of work stands.")
    parser.add_argument("--task", required=True, help="uid of the work to orient on")
    parser.add_argument("--k", type=int, default=8, help="how many documents (default 8)")
    parser.add_argument("--as", dest="as_agent", default="mike",
                        help="who is asking — an agent name, or 'mike' (default)")
    parser.add_argument("--board", action="store_true",
                        help="also write a readable board under boards/<agent>/")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--read", action="store_true",
        help="SPENDS MONEY — a few cents. Opens the documents with a model and "
             "puts what they say at the top. Off by default; there is no other "
             "way to turn it on.")
    parser.add_argument(
        "--draw-budget", type=int, default=None,
        help="how many candidates the circle may admit before ranking "
             "(default max(8*k, 256); clamped to at least k). The display "
             "count stays --k; this widens the contest, not the answer.")
    parser.add_argument(
        "--terms", default="",
        help="extra keyword-recall terms, comma-separated, alongside the "
             "task's own title and tags.")
    parser.add_argument(
        "--for-librarian", dest="for_librarian", default=None, metavar="PATH",
        help="Librarian L1 (d317f532): write the deterministic evidence plus "
             "top-ranked governed bodies to PATH as one feedable artifact. "
             "No model calls; implies the free path.")
    parser.add_argument(
        "--body-budget", type=int, default=400_000,
        help="--for-librarian only: total body characters included before the "
             "cap names what it excluded (default 400000).")
    args = parser.parse_args()

    people = _principals()
    people.setdefault("mike", "7b921d17")
    principal = people.get(args.as_agent, args.as_agent)
    extra_terms = tuple(t for t in (s.strip() for s in args.terms.split(",")) if t)

    # AC5 (4883fa94): the read tier is gateway-brokered. Preflight the local
    # metering gateway BEFORE constructing the edge, so a missing gateway is
    # named as itself — not surfaced later as PROVIDER_FAILED mid-run with a
    # budget hold already taken.
    read_preflight_refusal = None
    if args.read:
        import socket
        try:
            socket.create_connection(("127.0.0.1", 8080), timeout=1.0).close()
        except OSError:
            read_preflight_refusal = (
                "the local metering gateway is not accepting on 127.0.0.1:8080."
                " The read tier is gateway-brokered by design; start the"
                " gateway and re-run --read. No model was called, nothing was"
                " reserved, nothing was spent."
            )
            args.read = False

    # The whole spend gate, in one expression: no flag, no edge, no money. The
    # deterministic answer below is reached identically either way. (TROPO_RUN_UID
    # attribution resolves where run_uid is consumed, so the gate stays bare.)
    answer = orient(args.task, args.k, principal,
                    MeteredEdge() if args.read else None,
                    draw_budget=args.draw_budget,
                    extra_terms=extra_terms)
    if read_preflight_refusal and answer.get("ok"):
        answer["read_preflight_refusal"] = read_preflight_refusal
    if args.json:
        print(json.dumps(answer, indent=1))
        return 0 if answer["ok"] else 1
    print(render_text(answer))
    if args.for_librarian and answer["ok"]:
        feed_path = Path(args.for_librarian)
        feed_path.parent.mkdir(parents=True, exist_ok=True)
        feed_path.write_text(render_librarian_feed(answer, args.body_budget))
        print(f"  librarian feed: {feed_path}\n")
    if args.board and answer["ok"]:
        out = ROOT / "boards" / "metis" / f"orient-{args.task}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_board(answer))
        print(f"  board: {out.relative_to(ROOT)}\n")
    return 0 if answer["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
