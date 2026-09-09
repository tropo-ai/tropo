#!/usr/bin/env python3
"""---
uid: 9b3ce4d1
type: tool
name: tropo-verify-release-live
title: tropo-verify-release-live.py — independently verify a release is live and closed
status: active
owner: talos
extraction_scope: ship
schema_version: 2
created: '2026-08-16'
created_by: talos-t44
built_under: '2fae6312'
---

tropo-verify-release-live.py — is the release actually live?

Dev-spec 2fae6312 (locked), implementation step 6. The thin CLI over
`lib/release_completion.py`, and the production home of the observers that
module deliberately does not contain.

    python3 vault/tools/tropo-verify-release-live.py --run-dir <release run> \\
        [--json] [--write-receipt]

WHAT MAKES IT A SECOND OPINION. The publication receipt is written by the thing
that published. If closure consumed only that, the run would be complete
because the run said so. This command re-observes each fact and writes a
separate completion receipt binding all of them, which is the leg that removes
the circularity.

The observers here read the run's own artifacts and the two event surfaces.
They are honest about their reach: an observer that cannot see its subject
reports absent with the reason, and absent means the release stays open. That
is deliberately not the same thing as "verified" — a verifier that treats
unreachable as fine is the shape of gate that passes while blind.

EXIT CODES

    0  every bound fact observed; completion receipt written
    1  incomplete — the named partial state says which edge replay attempts next
    4  misuse (no run directory, unreadable journal)

Nonzero is never "probably fine". The spec's rule is that fire never returns
complete while release records are open, and this is the command that decides.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.release_completion import (  # noqa: E402
    COMPLETION_EVENT,
    REQUIRED_FACTS,
    FactObservation,
    ReleaseCompletionError,
    verify_completion,
)

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_MISUSE = 4

BUS_EVENT = "tropo.release.published"
RUN_EVENT = "tropo.release.published"
CLOSED_EVENT = "tropo.release.closed"


def _read_journal(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _event_type(row) -> str:
    """lib/release_closure.event_type — the one declared rule for reading an
    event's name out of a row. Run JSONL spells it `event`; the publisher
    mirrors the bus CloudEvent in verbatim, so `type` is equally real. This
    file used to carry an `event:`-only copy, which meant three of its five
    bound facts could never be observed on a real release: the publisher has
    always written the mirrored row as `type:`.
    """
    try:
        from lib.release_closure import event_type  # noqa: WPS433 — optional lib
        return event_type(row)
    except Exception:  # noqa: BLE001 — a missing lib narrows the read, never widens it
        if not isinstance(row, dict):
            return ""
        return str(row.get("event") or row.get("type") or "")


def _receipt_sha(data: Dict[str, Any]) -> str:
    """The publication receipt hash, under either name the producers write.

    `tropo-publish-release._published_event_data()` emits `receipt_sha256`.
    Nothing in this Studio has ever written `publication_receipt_sha256` —
    it appears only in this file's own reads and in its test fixtures. The
    publication_receipt observer already accepted both; the other three did
    not, which is sibling drift inside one file.
    """
    if not isinstance(data, dict):
        return ""
    return str(data.get("publication_receipt_sha256") or data.get("receipt_sha256") or "")


def _first(rows, event: str) -> Optional[Dict[str, Any]]:
    for row in rows:
        if _event_type(row) == event:
            return row
    return None


def _real_fire_scorecard_path(run_dir: Path) -> Path:
    """The producer's own filename, from the producer's own module.

    Never a literal here: a second copy of a filename is how this fact came to
    read `scorecard.json` while the writer wrote something else.
    """
    try:
        from lib import release_metrics  # noqa: WPS433 — optional lib
        return Path(release_metrics.scorecard_path(run_dir, release_metrics.REAL_FIRE))
    except Exception:  # noqa: BLE001 — a missing lib narrows the read, never widens it
        return run_dir / "one-prompt-real-fire-scorecard.json"


def resolve_publication_receipt(
    studio_root: Path, receipt_sha256: str
) -> "tuple[bool, str]":
    """THE one read path for the publication receipt. (Stream 1 AC4 / F10.)

    The receipt is CONTENT-ADDRESSED: release_receipt.write_release_receipt()
    names the file by the sha256 of its own canonical bytes, under
    vault/events/release-receipts/. Resolving it by the sha the published event
    already carries is strictly stronger than "a file exists in the run folder"
    — it binds the artifact to the event rather than to a location.

    Two traps, both named in the locked spec because both are easy to fall into:
    resolve by `receipt_sha256` from the PUBLISHED EVENT, never the transaction
    id (which carries the package sha); and verify by HASHING THE FILE BYTES,
    because a content-addressed receipt cannot contain its own hash.

    Returns (present, detail). Any other reader of this fact calls THIS.
    """
    if not receipt_sha256:
        return False, "the run's published event names no receipt sha"
    path = (Path(studio_root) / "vault" / "events" / "release-receipts"
            / ("%s.json" % receipt_sha256))
    if not path.is_file():
        return False, "no receipt at %s" % path
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != receipt_sha256:
        return False, (
            "receipt at %s hashes to %s, not the %s its own name claims"
            % (path, actual[:12], receipt_sha256[:12])
        )
    return True, ""


#: The records a closure event names, when it does not carry `closed_uids`.
#: The writer emits these five; the reader wanted a sixth name it never wrote.
#: One declared source both sides consult, rather than a second key. (AC4.)
CLOSED_RECORD_KEYS = (
    "release_plan_uid",
    "release_entry_uid",
    "activation_root_uid",
    "release_activation_uid",
    "release_pipeline_run_uid",
)


def closed_record_uids(data: Mapping[str, Any]) -> List[str]:
    """What a closure actually closed. `closed_uids` wins when present."""
    if not isinstance(data, Mapping):
        return []
    declared = data.get("closed_uids")
    if isinstance(declared, list) and declared:
        return [str(u) for u in declared if u]
    return [str(data[k]) for k in CLOSED_RECORD_KEYS if data.get(k)]


#: Runs whose scorecard fact is exempt BY NAME, and the journal that records
#: why. Metis G112 as release owner and spec locker, 2026-08-24T20:15:02Z
#: (`scorecard_decision_recorded`), clarified 2026-08-25T12:23:22Z
#: (`scorecard_decision_clarified`).
#:
#: THIS IS NOT A REMOVAL AND MUST NEVER BECOME ONE. `scorecard` stays in
#: REQUIRED_FACTS. From v1.92 forward every run fired through REAL_FIRE must
#: produce a card: v1.92 scores itself, and its card is part of the
#: release-vs-release measurement. A global removal was explicitly refused.
#:
#: WHY 7ee91e0b IS EXEMPT RATHER THAN RECONSTRUCTED. Rebuilding v1.91's card
#: needs `ORCHESTRATOR_STARTED_AT`, which was never recorded anywhere, and the
#: ~20 refusals bound to class IDs, which exist only as prose in the retro.
#: Passing `observed_refusals=[]` would assert zero refusals, which is false.
#: Fabricating either input to obtain a green is the exact disease this cycle
#: cures, so the release is honestly exempt instead of dishonestly complete.
#: KEYED BY THE RUN'S MINTED ACTIVATION UID. Not the saga, and not the name.
#:
#: Mike, 2026-08-25: "should the gates always check UID not name? Once a UID is
#: minted, it does not change." Yes — and the first fix here got it wrong twice
#: over. Keying on the SAGA leaked to every re-run of it. Keying on the FOLDER
#: NAME then traded one mutable claim for another: rename the directory and the
#: exemption silently vanishes, and nothing stops a directory being created that
#: wears the exempt name. `activation_uid` is minted, immutable, and distinct
#: from the saga — which delivers the run-scoping the ruling required for free,
#: because a re-run mints a new activation and cannot inherit this one.
#:
#: `run_folder_at_ruling` and `saga_at_ruling` are recorded as provenance only.
#: They are never matched on. A field kept for reading and a field matched on
#: are different things, and conflating them is how the name became the key.
#:
#: The first version keyed on the first 8-hex token scraped out of the folder
#: NAME and never stat'd the directory, which made it SAGA-scoped when the
#: ruling said RUN-scoped. Measured after an independent adversarial pass:
#: `release-pipeline-7ee91e0b-2026-12-31`, `dev-pipeline-7ee91e0b-2026-08-24`
#: and even `totally-unrelated-7ee91e0b-thing` all came back EXEMPT. Any re-run,
#: resume or later run of saga 7ee91e0b — the saga the spec says is still open —
#: would have inherited a permanent scorecard pass.
#:
#: Three negative controls were written for that exemption and all three passed.
#: The one testing scope used `deadbeef`, a uid absent from the table entirely,
#: so it could only ever prove the lookup works and never that the scope is
#: narrow. A control that varies the wrong dimension is a control in name only.
SCORECARD_EXEMPT_RUNS: Dict[str, Dict[str, str]] = {
    "08121161": {
        "run_folder_at_ruling": "release-pipeline-7ee91e0b-2026-08-23",
        "saga_at_ruling": "release:7ee91e0b",
        "journal": "vault/pipeline-runs/dev-pipeline-9ff56eec-2026-08-24/run.jsonl",
        "decision_event": "scorecard_decision_recorded",
        "reason": (
            "v1.91 predates the REAL_FIRE wiring; its card cannot be "
            "reconstructed without fabricating ORCHESTRATOR_STARTED_AT and the "
            "refusal class IDs. Measurement preserved as prose in the retro."
        ),
    },
}


def scorecard_exemption(run_dir: Path) -> Optional[Dict[str, str]]:
    """Is THIS run's scorecard exempt, and can the exemption prove its reason?

    Fails closed on its own evidence. An exemption whose recorded decision
    cannot be read is not an exemption — it is an assertion, and an assertion
    that a fact may be skipped is precisely what this verifier exists to refuse.
    So the journal is read and the decision event located before the exemption
    is honoured, and the evidence sha is the hash of that decision row: the
    exemption carries real evidence of a real decision, not a placeholder.
    """
    # Identity comes from the run's own journal, never from its path. A name is
    # a claim; a minted uid is identity, and this exemption exists precisely
    # because a claim was accepted where a measurement was required.
    if not run_dir.is_dir() or not (run_dir / "run.jsonl").is_file():
        return None
    activation = ""
    for row in _read_journal(run_dir / "run.jsonl"):
        candidate = str((row.get("data") or {}).get("activation_uid") or "")
        if candidate:
            activation = candidate
            break
    entry = SCORECARD_EXEMPT_RUNS.get(activation)
    if entry is None:
        return None

    root = _studio_root_for(str(run_dir))
    journal = Path(root) / entry["journal"]
    if not journal.is_file():
        return None
    for line in journal.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("event") != entry["decision_event"]:
            continue
        if row.get("acceptance_criterion") != "AC4":
            continue
        return {
            "evidence_sha256": hashlib.sha256(
                json.dumps(row, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest(),
            "detail": "scorecard EXEMPT (not measured) for run %s by recorded "
                      "decision (%s, %s): %s"
            % (run_dir.name, entry["decision_event"], row.get("ts", ""),
               entry["reason"]),
        }
    return None


def load_bus_rows(vault_root, bus_events=None, no_bus: bool = False):
    """THE bus, loaded one way, for every caller.

    The default IS vault/events/streams/ -- the bus is not an unknown location in
    this Studio. Conflating "you did not tell me where the bus is" with "the bus
    is unobserved" was the 2026-08-25 defect cured in main() below.

    It was cured there and ONLY there. The release facade
    (tropo-release.py::_completion_observers) called build_observers() directly
    and handed it `run_dir / "bus-events.jsonl"` -- a literal that occurs exactly
    once in the whole tree, at that read, and that nothing has ever written. So
    `tropo-release.py status` observed an empty bus for every release ever
    published, and since bus_published_event is a REQUIRED bound fact, status
    could never return anything but REFUSED. There is no flag to override it.

    The same fix, twice, in two files, is how that happened. This function exists
    so there is one loader to fix. (argus-a165, 2026-09-01.)
    """
    rows = []
    if no_bus:
        return rows
    if bus_events:
        return _read_journal(Path(bus_events))
    streams = Path(vault_root).resolve() / "vault" / "events" / "streams"
    if streams.is_dir():
        for stream in sorted(streams.glob("*.jsonl")):
            rows.extend(_read_journal(stream))
    return rows


def build_observers(
    run_dir: Path,
    bus_rows: List[Dict[str, Any]],
    version: str = "",
    studio_root: Optional[Path] = None,
) -> Dict[str, Callable]:
    """One observer per bound fact, reading world state rather than belief.

    The run journal is read here, but note WHAT is taken from it: the presence
    of a mirrored event row and the hashes it carries. The journal's own
    opinion about whether the release is finished is never consulted, because
    that opinion is the thing being checked.
    """
    rows = _read_journal(run_dir / "run.jsonl")

    def publication_receipt() -> FactObservation:
        # Resolved by the sha the run's own published event names, against the
        # content-addressed store — NOT by a file in the run folder, which no
        # producer has ever written. One read path: resolve_publication_receipt.
        row = _first(rows, RUN_EVENT)
        sha = _receipt_sha(row.get("data") or {}) if row else ""
        root = studio_root or _studio_root_for(str(run_dir))
        ok, detail = resolve_publication_receipt(root, sha)
        if not ok:
            return FactObservation("publication_receipt", False, detail=detail)
        return FactObservation("publication_receipt", True, evidence_sha256=str(sha))

    def bus_published_event() -> FactObservation:
        matches = [r for r in bus_rows if _event_type(r) == BUS_EVENT]
        # The bus is append-only forever, so "exactly one published event" can
        # only ever have meant "exactly one for THIS release". Unbound, the
        # gate gets more wrong with every release shipped: v1.91 read `found 2`
        # because v1.90's event was still on the same stream. Rows that declare
        # a version are attributable and must match; rows that declare none
        # cannot be assigned either way and are counted as before, because
        # inventing an assignment would be the gate asserting what it did not
        # observe. Real producer output always declares a version
        # (tropo-publish-release._published_event_data), so this tightens the
        # live path and leaves the version-less fixtures in the S3 AC5/AC6
        # locked suites reading exactly as they did.
        # (argus-a156, 2026-08-24 — retro 25c70440 §Actions 6: compare like
        # with like.)
        scoped = version or ""
        if scoped:
            matches = [
                r for r in matches
                if _normalise_version((r.get("data") or {}).get("version")) in ("", scoped)
            ]
        if len(matches) != 1:
            return FactObservation(
                "bus_published_event", False,
                detail="expected exactly one %s on the bus%s, found %d"
                % (BUS_EVENT, (" for v%s" % scoped) if scoped else "", len(matches)),
            )
        data = matches[0].get("data") or {}
        sha = _receipt_sha(data)
        if not sha:
            return FactObservation(
                "bus_published_event", False,
                detail="bus event does not bind a publication receipt",
            )
        return FactObservation("bus_published_event", True, evidence_sha256=str(sha))

    def run_published_event() -> FactObservation:
        row = _first(rows, RUN_EVENT)
        if row is None:
            return FactObservation(
                "run_published_event", False,
                detail="no %s row in the run journal" % RUN_EVENT,
            )
        sha = _receipt_sha(row.get("data") or {})
        if not sha:
            return FactObservation(
                "run_published_event", False,
                detail="run event does not bind a publication receipt",
            )
        return FactObservation("run_published_event", True, evidence_sha256=str(sha))

    def closed_records() -> FactObservation:
        row = _first(rows, CLOSED_EVENT)
        if row is None:
            return FactObservation(
                "closed_records", False, detail="no %s row in the run journal" % CLOSED_EVENT
            )
        data = row.get("data") or {}
        closed = closed_record_uids(data)
        if not closed:
            return FactObservation(
                "closed_records", False,
                detail="closure names no records; an empty closure closes nothing",
            )
        sha = _receipt_sha(data)
        if not sha:
            return FactObservation(
                "closed_records", False,
                detail="closure does not bind the publication receipt it consumed",
            )
        return FactObservation("closed_records", True, evidence_sha256=str(sha))

    def scorecard() -> FactObservation:
        # The producer writes MODE-SPECIFIC names via lib/release_metrics
        # (one-prompt-real-fire-scorecard.json). This reader wanted a third
        # name, `scorecard.json`, that neither mode has ever written.
        path = _real_fire_scorecard_path(run_dir)
        if not path.is_file():
            exempt = scorecard_exemption(run_dir)
            if exempt is not None:
                return FactObservation(
                    "scorecard", True,
                    evidence_sha256=exempt["evidence_sha256"],
                    detail=exempt["detail"],
                )
            return FactObservation(
                "scorecard", False,
                detail="no real-fire scorecard at %s" % path.name,
            )
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            return FactObservation(
                "scorecard", False, detail="scorecard does not parse: %s" % exc
            )
        # Hash the FILE BYTES. The old reader wanted a `scorecard_sha256` field
        # INSIDE the card — a field no producer has ever written, and one a card
        # cannot honestly contain, for the same reason the publication receipt
        # cannot contain its own hash. Same trap, same cure.
        if not card.get("mode") or not card.get("verdict"):
            return FactObservation(
                "scorecard", False,
                detail="scorecard at %s declares no mode/verdict" % path.name,
            )
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return FactObservation("scorecard", True, evidence_sha256=sha)

    return {
        "publication_receipt": publication_receipt,
        "bus_published_event": bus_published_event,
        "run_published_event": run_published_event,
        "closed_records": closed_records,
        "scorecard": scorecard,
    }


def _identity(run_dir: Path) -> Dict[str, str]:
    for row in _read_journal(run_dir / "run.jsonl"):
        data = row.get("data") or {}
        if data.get("saga_id") and data.get("pipeline_run_uid"):
            return {
                "saga_id": str(data["saga_id"]),
                "pipeline_run_uid": str(data["pipeline_run_uid"]),
            }
    return {}


def _emit_completion_verified(
    run_dir: Path, identity: Dict[str, str], receipt: Mapping[str, Any],
) -> bool:
    """Write the terminal `tropo.release.completion_verified` fact, once.

    v1.91 S2 AC1/AC5 (3fb41c99): this event was declared, read (by nothing —
    zero readers branch on it today) and asserted in the vocabulary table
    (2fae6312), and this tool computed the fact and only ever printed it.
    G111's ruling (2026-08-23): WRITE it, from the one place the fact becomes
    true — here, the composite verifier that independently proved it.

    `dedup=("pipeline_run_uid",)` per the declared cardinality ("once;
    terminal journal fact"): a rerun of an already-complete run is an
    idempotent no-op, matching the retry shape every other terminal release
    event in this vocabulary already uses.
    """
    journal = run_dir / "run.jsonl"
    for row in _read_journal(journal):
        if _event_type(row) != COMPLETION_EVENT:
            continue
        if str((row.get("data") or {}).get("pipeline_run_uid") or "") == identity["pipeline_run_uid"]:
            return False

    facts = receipt.get("verified_facts") or {}

    # AN EXEMPTED FACT IS NOT A MEASURED ONE, AND MUST NOT BE PUBLISHED AS ONE.
    # `scorecard_sha256` means "the hash of the scorecard". For an exempted run
    # the scorecard observation carries the hash of the GOVERNANCE DECISION ROW,
    # and publishing that under this key tells every downstream consumer — the
    # release-vs-release measurement included — that a card exists. It does not.
    # That is the "assert a measurement it never took" defect the second
    # post-lock amendment of 5b608d28 was made to cure, reappearing one level
    # up. So the key goes null and the exemption is stated in its own field.
    exempt = scorecard_exemption(run_dir)
    data = {
        "saga_id": identity["saga_id"],
        "pipeline_run_uid": identity["pipeline_run_uid"],
        "publication_receipt_sha256": facts.get("publication_receipt", ""),
        "closure_receipt_sha256": facts.get("closed_records", ""),
        "scorecard_sha256": None if exempt else facts.get("scorecard", ""),
        "scorecard_exempt": bool(exempt),
        "scorecard_exemption_detail": exempt["detail"] if exempt else "",
        "composite_verifier_receipt_sha256": receipt.get("completion_receipt_sha256", ""),
    }
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "event": COMPLETION_EVENT,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actor": "/tools/verify-release-live",
            "actor_label_resolved": None,
            "step": None, "stage": None, "data": data,
            "schema_version": 2,
            "trace_id": identity["pipeline_run_uid"],
            "span_id": uuid.uuid4().hex[:16], "parent_span_id": None,
        }, ensure_ascii=False) + "\n")
    return True


# S3 AC6 (176a8995): the built-but-unpublished marker. tropo-build-release.py
# writes it at the zip (publish_state "not-staged"); boot step 5.1.8 nags on it
# until publish_state is live or deferred-by-mike (fbe50871 owns the contract).
# verify-live is the command that decides COMPLETE, so it is the command that
# flips the marker to "live" — the file is kept rather than deleted so the
# record of which run turned it live survives.
PUBLISH_PENDING_REL = Path(".tropo") / "publish-pending.json"
PUBLISH_PENDING_SILENT_STATES = frozenset({"live", "deferred-by-mike"})


def _normalise_version(value: Any) -> str:
    text = str(value or "").strip()
    return text[1:] if text.startswith("v") else text


def _release_version_for(run_dir: Path, studio_root: Path) -> str:
    """Which version this run published — read from the run, never guessed.

    Looked for, in order: the content-addressed publication receipt the run's
    published event names; any journal row naming release_version/version; the
    release entry the run_created row binds (its frontmatter release_version).
    Empty when none of them say, and empty means "do not touch the marker" —
    silencing a nag for a version this run cannot prove it verified is Argus
    F-07 with extra steps.

    Stream 1 AC4 / F10: this used to read `run_dir/publication-receipt.json`
    directly — a SECOND read path for the same fact, and a path no producer
    writes. It now resolves the same way the observer does, so there is one
    implementation of "where the publication receipt lives".
    """
    rows = _read_journal(run_dir / "run.jsonl")
    row = _first(rows, RUN_EVENT)
    sha = _receipt_sha(row.get("data") or {}) if row else ""
    ok, _detail = resolve_publication_receipt(studio_root, sha)
    if ok:
        receipt = (Path(studio_root) / "vault" / "events" / "release-receipts"
                   / ("%s.json" % sha))
        try:
            version = _normalise_version(
                (json.loads(receipt.read_text(encoding="utf-8")) or {}).get("version"))
            if version:
                return version
        except (OSError, ValueError):
            pass
    release_entry_uid = ""
    for row in _read_journal(run_dir / "run.jsonl"):
        data = row.get("data") or {}
        version = _normalise_version(data.get("release_version") or data.get("version"))
        if version:
            return version
        release_entry_uid = release_entry_uid or str(data.get("release_entry_uid") or "")
    if release_entry_uid:
        entry = studio_root / "vault" / "files" / f"{release_entry_uid}.md"
        if entry.is_file():
            import re as _re
            match = _re.search(r"^release_version:\s*['\"]?([^'\"\n]+)",
                               entry.read_text(encoding="utf-8", errors="replace"), _re.M)
            if match:
                return _normalise_version(match.group(1))
    return ""


def clear_publish_pending(studio_root: Path, run_dir: Path,
                          verified_version: str = "") -> str:
    """S3 AC6 (176a8995): verify-live green flips .tropo/publish-pending.json to live.

    Returns a one-line account of what happened, for the operator. Only the
    marker for the version THIS run verified is flipped; a marker for another
    version (a later build awaiting its own publish) is left loud, and a run
    that cannot name its version leaves the marker alone and says so.

    3d8d4351 §6: `verified_version` is the VERIFY-ONLY case's teacher — that
    path verified a named version against the remote without walking this
    run's publication events, so the run-shaped resolver honestly finds
    nothing. The explicit version is not a guess: it is what the tag/object
    verification just proved live. Still one writer; the walk path keeps
    resolving from the run and never passes the override.
    """
    marker = studio_root / PUBLISH_PENDING_REL
    if not marker.is_file():
        return "publish-pending: no marker at %s (nothing to clear)" % marker
    try:
        body = json.loads(marker.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        return "publish-pending: marker %s unreadable (%s) — left as is" % (marker, exc)
    marker_version = _normalise_version(body.get("version"))
    run_version = (_normalise_version(verified_version)
                   if verified_version
                   else _release_version_for(run_dir, studio_root))
    # A silent state silences only ITS OWN version (f015ebc247ce, argus-a173
    # diagnosis 2026-09-07). Unscoped, this guard fired before run_version was
    # ever compared, so a marker silenced for v1.94 (Mike's own defer) stayed
    # silent forever after -- v1.95, v1.96, every release after it, because
    # the version-compare branch two lines down existed for exactly this case
    # and could never be reached. Third recurrence of one predicate error:
    # "a silent state exists" is not "a silent state FOR THIS VERSION exists".
    if (str(body.get("publish_state")) in PUBLISH_PENDING_SILENT_STATES
            and (not run_version or marker_version == run_version)):
        return "publish-pending: already %s for v%s" % (body.get("publish_state"), marker_version)
    if not run_version:
        return ("publish-pending: run %s names no release version, so the marker for "
                "v%s is left at %s — flip it by hand once you know they are the same "
                "release" % (run_dir.name, marker_version, body.get("publish_state")))
    if marker_version and marker_version != run_version:
        return ("publish-pending: marker is for v%s, this run verified v%s — left loud"
                % (marker_version, run_version))
    body.update({
        "version": marker_version or run_version,
        "publish_state": "live",
        "live_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verified_by": "tropo-verify-release-live.py",
        "verified_run": run_dir.name,
        # 3d8d4351: the completion VERDICT beside the flip's own facts, so the
        # marker answers "what did verification conclude" not just "when".
        # One writer still — this is THE marker's flip path (fbe50871), never
        # forked; the verify-only case reaches this same writer.
        "completion_verdict": str(body.get("completion_verdict") or "verified-live"),
    })
    staged = marker.with_name("." + marker.name + ".tmp")
    staged.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    staged.replace(marker)
    return "publish-pending: v%s -> live (%s)" % (body["version"], marker)


def defer_publish_pending(studio_root: Path, version: str,
                          defer_record: Optional[Mapping[str, Any]] = None,
                          written_by: str = "tropo-publish-release.py cmd_defer") -> str:
    """The marker's OTHER silent state, through the same module that owns the file.

    fbe50871 names two states that silence boot step 5.1.8: live and
    deferred-by-mike. clear_publish_pending above writes the first; nothing
    wrote the second. cmd_defer stamped the release entry deferred-by-mike and
    left the marker at not-staged, so the founder's defer produced two readers
    of one fact with one updated — every boot after the v1.94 defer
    (2026-09-05T12:58:49Z) printed a "built but not published" line for a
    release he had already deferred, and §30 of the Architecture Review had
    recorded the identical marker defect on v1.92 two weeks earlier. Found by
    metis-g120, wired by argus-a171, 2026-09-05.

    Same shape as the live flip: only the marker for THIS version is touched,
    a marker for another version is left loud, an already-silent marker is
    reported and left alone. Returns a one-line account for the operator.
    """
    marker = Path(studio_root) / PUBLISH_PENDING_REL
    if not marker.is_file():
        return "publish-pending: no marker at %s (nothing to defer)" % marker
    try:
        body = json.loads(marker.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        return "publish-pending: marker %s unreadable (%s) — left as is" % (marker, exc)
    marker_version = _normalise_version(body.get("version"))
    want = _normalise_version(version)
    # Same scoping fix as clear_publish_pending above -- see its comment.
    if (str(body.get("publish_state")) in PUBLISH_PENDING_SILENT_STATES
            and (not want or marker_version == want)):
        return "publish-pending: already %s for v%s" % (body.get("publish_state"), marker_version)
    if not want:
        return ("publish-pending: defer names no release version, so the marker for "
                "v%s is left at %s" % (marker_version, body.get("publish_state")))
    if marker_version and marker_version != want:
        return ("publish-pending: marker is for v%s, this defer is v%s — left loud"
                % (marker_version, want))
    body.update({
        "version": marker_version or want,
        "publish_state": "deferred-by-mike",
        "deferred_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "written_by": written_by,
        "defer_record": dict(defer_record or {}),
    })
    body.pop("cure", None)
    staged = marker.with_name("." + marker.name + ".tmp")
    staged.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    staged.replace(marker)
    return "publish-pending: v%s -> deferred-by-mike (%s)" % (body["version"], marker)


# S3 AC5 (176a8995): site_endpoint is OBSERVED — downloaded and hashed — or
# named as not observed. For at least three releases the saga withheld
# completion on this fact and nobody was blocked, because the incompleteness
# read as noise; the fire's own site_endpoint checkpoint tolerates absence.
# This is the second opinion: it fetches the public badge a visitor would get.
#
# WHY IT IS NOT (YET) IN lib/release_completion.REQUIRED_FACTS. That tuple is
# closed and FactObservation refuses a fact outside it, so binding site_endpoint
# is an amendment to the completion contract, not a flag. Today BOTH public
# URLs 404 (https://tropo-ai.com/os-release.json and /api/os-release — the
# site source carries the route, the deployed site does not), so binding it
# now would hold every verify-live INCOMPLETE until the site ships the
# endpoint, and would turn the locked AC6 fixture red. So: the observation
# runs on every verify-live, prints SEEN with its sha256 or the named refusal
# "site_endpoint not observed: <url> -> <status>", and --require-site-endpoint
# makes it binding (INCOMPLETE, site-endpoint-pending) on demand — the strict
# reading the spec wants, available the day the endpoint is live. Either the
# endpoint ships and this moves into REQUIRED_FACTS, or the observation is
# retired out loud; neither happens silently here.
#: The publisher's default for the served badge (tropo-publish-release.py
#: _site_endpoint_url): the file the AC4 adapter writes, at the site root.
DEFAULT_SITE_ENDPOINT_URL = "https://tropo-ai.com/os-release.json"
SITE_ENDPOINT_TIMEOUT_S = 15
SITE_ENDPOINT_PARTIAL_STATE = "site-endpoint-pending"


def _site_route_fallback() -> str:
    """lib/release_site.SITE_ENDPOINT — the /api route the site source serves
    the badge from. Probed after the default so the refusal names both."""
    try:
        from lib.release_site import SITE_ENDPOINT  # noqa: WPS433 — optional
        return str(SITE_ENDPOINT)
    except Exception:  # noqa: BLE001 — a missing lib only narrows the probe
        return ""


def _publish_state_for(version: str) -> Optional[Dict[str, Any]]:
    """The fire's staged record for this version, when this Studio has one.
    Its presence is what says 'a real fire declared an endpoint here'."""
    if not version:
        return None
    try:
        from lib import tropo_roots  # noqa: WPS433 — resolves from this copy's location
        path = Path(tropo_roots.RELEASES_DIR) / ("v%s" % version) / "publish-state.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — no roots, no state; reported as undeclared
        return None
    return None


def site_endpoint_candidates(explicit_url: str, run_dir: Path, studio_root: Path) -> Dict[str, Any]:
    """Which URL(s) to observe and why. Explicit (--site-endpoint-url / env)
    wins; else the fire's own declaration — the publish-state for the run's
    version (its site_endpoint_url, or the publisher's default); else nothing
    is declared and nothing is fetched (fixtures and pre-v1.90 runs)."""
    explicit = explicit_url or os.environ.get("TROPO_SITE_ENDPOINT_URL") or ""
    if explicit:
        return {"urls": [explicit], "source": "declared by --site-endpoint-url / TROPO_SITE_ENDPOINT_URL"}
    version = _release_version_for(run_dir, studio_root)
    state = _publish_state_for(version)
    if state is None:
        return {
            "urls": [],
            "source": (
                "undeclared: no publish-state for v%s in this Studio and no "
                "--site-endpoint-url / TROPO_SITE_ENDPOINT_URL" % (version or "?")
            ),
        }
    url = str(state.get("site_endpoint_url") or DEFAULT_SITE_ENDPOINT_URL)
    urls = [url]
    fallback = _site_route_fallback()
    if url == DEFAULT_SITE_ENDPOINT_URL and fallback and fallback not in urls:
        urls.append(fallback)
    return {"urls": urls, "source": "declared by the fire (publish-state v%s)" % version}


def observe_site_endpoint(urls: List[str], timeout: int = SITE_ENDPOINT_TIMEOUT_S) -> Dict[str, Any]:
    """GET each candidate, cache-busted; the first 200 is hashed and SEEN. Any
    other outcome is the named refusal, listing every URL and what it said."""
    tried: List[str] = []
    for url in urls:
        busted = url + ("&" if "?" in url else "?") + "tropo-verify=%d" % int(time.time())
        request = urllib.request.Request(
            busted, headers={"Cache-Control": "no-cache", "Pragma": "no-cache",
                             "User-Agent": "tropo-verify-release-live"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                body = response.read()
            if status == 200:
                digest = hashlib.sha256(body).hexdigest()
                version = ""
                try:
                    version = str((json.loads(body.decode("utf-8")) or {}).get("version") or "")
                except Exception:  # noqa: BLE001 — a non-JSON 200 is still an observation
                    version = ""
                return {"present": True, "url": url, "sha256": digest, "status": 200,
                        "version": version, "tried": tried + ["%s -> 200" % url],
                        "detail": "%s -> 200 sha256 %s%s" % (
                            url, digest[:12], (" version %s" % version) if version else "")}
            tried.append("%s -> %s" % (url, status))
        except urllib.error.HTTPError as exc:
            tried.append("%s -> %s" % (url, exc.code))
        except Exception as exc:  # noqa: BLE001 — unreachable is not observed
            tried.append("%s -> %s: %s" % (url, type(exc).__name__, str(exc)[:80]))
    return {"present": False, "url": urls[0] if urls else "", "sha256": "", "status": None,
            "version": "", "tried": tried,
            "detail": "site_endpoint not observed: " + "; ".join(tried)}


def _studio_root_for(vault_arg: str) -> Path:
    """The Studio the marker lives under: --vault when it is a Studio, else
    the Studio this script is installed in (the temp-studio copy re-roots it)."""
    candidate = Path(vault_arg).resolve()
    if (candidate / ".tropo").is_dir():
        return candidate
    return TOOLS.parents[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Independently verify that a release is live and closed."
    )
    # Either address: the run folder directly, or the release PLAN, which is
    # the identity an operator has in hand and the one AC9's command uses.
    parser.add_argument("--run-dir")
    parser.add_argument("--release-plan-uid")
    parser.add_argument("--vault", default=".")
    parser.add_argument(
        "--bus-events",
        help="JSONL of the global bus stream. Omitted, the bus is read from its "
             "canonical home (vault/events/streams/*.jsonl). Use --no-bus to "
             "deliberately leave it unobserved.",
    )
    parser.add_argument(
        "--no-bus",
        action="store_true",
        help="do not observe the bus at all; it then reads as absent rather "
             "than as fine",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--write-receipt",
        action="store_true",
        help="write completion-receipt.json into the run folder on success",
    )
    # S3 AC5 (176a8995)
    parser.add_argument(
        "--site-endpoint-url", default=None,
        help="the public badge URL to observe (default: the fire's declaration via "
             "publish-state, else the publisher's default https://tropo-ai.com/os-release.json; "
             "env TROPO_SITE_ENDPOINT_URL also honoured)",
    )
    parser.add_argument(
        "--require-site-endpoint", action="store_true",
        help="bind the site_endpoint observation: not observed -> INCOMPLETE "
             "(site-endpoint-pending), the strict reading of S3 AC5",
    )
    args = parser.parse_args(argv)

    if not args.run_dir and not args.release_plan_uid:
        parser.error("one of --run-dir or --release-plan-uid is required")
    if args.release_plan_uid and not args.run_dir:
        facade = importlib.util.spec_from_file_location(
            "tropo_release_for_resolution", TOOLS / "tropo-release.py"
        )
        module = importlib.util.module_from_spec(facade)
        sys.modules[facade.name] = module
        facade.loader.exec_module(module)
        args.run_dir = str(module.resolve_run_dir(Path(args.vault), args.release_plan_uid))

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print("[MISUSE] no such run directory: %s" % run_dir, file=sys.stderr)
        return EXIT_MISUSE

    # THE OPERATOR PATH. Until 2026-08-25 an omitted --bus-events meant "the bus
    # is unobserved", so the spec's own reference command —
    #     tropo-verify-release-live.py --run-dir <the v1.91 run>
    # — reported INCOMPLETE / event-mirror-pending and exited 1. Reaching exit 0
    # required naming one specific file out of 266 streams, which the operator
    # had to find by grepping. AC4's committed test bypassed that entirely by
    # concatenating every stream in a helper of its own, so the test's "bus" was
    # a shape neither a producer nor an operator ever supplies. Found by an
    # independent adversarial pass.
    #
    # The bus is not an unknown location in this Studio; it lives at
    # vault/events/streams/. Conflating "you did not tell me where the bus is"
    # with "the bus is unobserved" was the defect. Not-observing stays
    # available, but it is now something you ASK for.
    bus_rows: List[Dict[str, Any]] = load_bus_rows(
        args.vault, bus_events=args.bus_events, no_bus=args.no_bus)

    identity = _identity(run_dir)
    if not identity:
        print(
            "[MISUSE] run journal names no saga_id/pipeline_run_uid; there is no "
            "run here to verify",
            file=sys.stderr,
        )
        return EXIT_MISUSE

    studio_root = _studio_root_for(args.vault)

    try:
        verdict = verify_completion(
            build_observers(
                run_dir, bus_rows,
                _release_version_for(run_dir, studio_root),
                studio_root,
            ),
            saga_id=identity["saga_id"],
            pipeline_run_uid=identity["pipeline_run_uid"],
        )
    except ReleaseCompletionError as exc:
        print("[MISUSE] %s" % exc, file=sys.stderr)
        return EXIT_MISUSE

    # S3 AC5 (176a8995): observe the public badge — or name why not.
    candidates = site_endpoint_candidates(args.site_endpoint_url or "", run_dir, studio_root)
    if candidates["urls"]:
        site = observe_site_endpoint(candidates["urls"])
    else:
        site = {"present": False, "url": "", "sha256": "", "status": None, "version": "",
                "tried": [], "detail": "site_endpoint not observed: " + candidates["source"]}
    site["source"] = candidates["source"]
    site_binds = bool(args.require_site_endpoint)
    complete = verdict.complete and (site["present"] or not site_binds)
    partial_state = verdict.partial_state
    if verdict.complete and not complete:
        partial_state = SITE_ENDPOINT_PARTIAL_STATE

    # S3 AC6 (176a8995): COMPLETE is the green that clears the marker. Decided
    # here so --json carries the account instead of trailing it as prose.
    marker_note = clear_publish_pending(studio_root, run_dir) if complete else None

    # v1.91 S2 AC1/AC5 (3fb41c99): gated on the five REQUIRED_FACTS
    # (verdict.complete), not the site-inclusive `complete` -- the public
    # badge is advisory (S3 AC5) and is not one of the facts this event
    # binds. verdict.receipt is only non-None when verdict.complete is True.
    completion_emitted = False
    if verdict.complete and verdict.receipt:
        completion_emitted = _emit_completion_verified(run_dir, identity, verdict.receipt)

    if args.json:
        print(json.dumps(
            {
                "complete": complete,
                "partial_state": partial_state,
                "missing": verdict.missing + ([] if site["present"] or not site_binds
                                              else ["site_endpoint"]),
                "detail": verdict.detail,
                "site_endpoint": site,
                "publish_pending": marker_note,
                "observations": [
                    {
                        "fact": o.fact,
                        "present": o.present,
                        "evidence_sha256": o.evidence_sha256,
                        "detail": o.detail,
                    }
                    for o in verdict.observations
                ],
                "receipt": verdict.receipt,
                "completion_verified_emitted": completion_emitted,
            },
            indent=2,
            sort_keys=True,
        ))
    else:
        print("--- release completion: %s ---" % identity["pipeline_run_uid"])
        for observation in verdict.observations:
            print(
                "  [%s] %-22s %s"
                % (
                    "SEEN" if observation.present else "ABSENT",
                    observation.fact,
                    observation.evidence_sha256 or observation.detail,
                )
            )
        # S3 AC5: the site_endpoint line sits with the facts, marked as bound
        # or advisory so nobody reads its absence as noise.
        print(
            "  [%s] %-22s %s  (%s%s)"
            % (
                "SEEN" if site["present"] else "ABSENT",
                "site_endpoint",
                site["sha256"] or site["detail"],
                (site["source"] + "; ") if site["tried"] else "",
                "BOUND by --require-site-endpoint" if site_binds
                else "advisory until REQUIRED_FACTS binds it — S3 AC5",
            )
        )
        if complete:
            print("COMPLETE — %s" % COMPLETION_EVENT)
            print("  %s" % (
                "emitted %s" % COMPLETION_EVENT if completion_emitted
                else "%s already on record for this run (idempotent)" % COMPLETION_EVENT
            ))
        else:
            print("INCOMPLETE — %s" % partial_state)
            print("  %s" % (verdict.detail if not verdict.complete else site["detail"]))
        if complete and not site["present"]:
            print("  ! site_endpoint not observed (%s) — the release is published and closed, "
                  "but the public badge is not serving; ship the endpoint or retire the "
                  "observation, out loud (S3 AC5)." % site["detail"])

    if complete and args.write_receipt:
        target = run_dir / "completion-receipt.json"
        # The receipt body is hashed by lib/release_completion over exactly the
        # bound facts; the site observation is reported beside it, not folded in.
        target.write_text(
            json.dumps(verdict.receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print("receipt: %s" % target)

    if marker_note and not args.json:
        print(marker_note)

    return EXIT_OK if complete else EXIT_INCOMPLETE


if __name__ == "__main__":
    sys.exit(main())
