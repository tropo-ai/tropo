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


def _first(rows, event: str) -> Optional[Dict[str, Any]]:
    for row in rows:
        if row.get("event") == event:
            return row
    return None


def build_observers(run_dir: Path, bus_rows: List[Dict[str, Any]]) -> Dict[str, Callable]:
    """One observer per bound fact, reading world state rather than belief.

    The run journal is read here, but note WHAT is taken from it: the presence
    of a mirrored event row and the hashes it carries. The journal's own
    opinion about whether the release is finished is never consulted, because
    that opinion is the thing being checked.
    """
    rows = _read_journal(run_dir / "run.jsonl")

    def publication_receipt() -> FactObservation:
        path = run_dir / "publication-receipt.json"
        if not path.is_file():
            return FactObservation(
                "publication_receipt", False,
                detail="no publication-receipt.json in the run folder",
            )
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            return FactObservation(
                "publication_receipt", False, detail="receipt does not parse: %s" % exc
            )
        sha = receipt.get("publication_receipt_sha256") or receipt.get("receipt_sha256")
        if not sha:
            return FactObservation(
                "publication_receipt", False,
                detail="receipt carries no hash of itself",
            )
        return FactObservation("publication_receipt", True, evidence_sha256=str(sha))

    def bus_published_event() -> FactObservation:
        matches = [r for r in bus_rows if r.get("type") == BUS_EVENT]
        if len(matches) != 1:
            return FactObservation(
                "bus_published_event", False,
                detail="expected exactly one %s on the bus, found %d"
                % (BUS_EVENT, len(matches)),
            )
        data = matches[0].get("data") or {}
        sha = data.get("publication_receipt_sha256")
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
        sha = (row.get("data") or {}).get("publication_receipt_sha256")
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
        closed = data.get("closed_uids")
        if not closed:
            return FactObservation(
                "closed_records", False,
                detail="closure names no records; an empty closure closes nothing",
            )
        sha = data.get("publication_receipt_sha256")
        if not sha:
            return FactObservation(
                "closed_records", False,
                detail="closure does not bind the publication receipt it consumed",
            )
        return FactObservation("closed_records", True, evidence_sha256=str(sha))

    def scorecard() -> FactObservation:
        path = run_dir / "scorecard.json"
        if not path.is_file():
            return FactObservation(
                "scorecard", False, detail="no scorecard.json in the run folder"
            )
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            return FactObservation(
                "scorecard", False, detail="scorecard does not parse: %s" % exc
            )
        sha = card.get("scorecard_sha256")
        if not sha:
            return FactObservation(
                "scorecard", False, detail="scorecard carries no hash of itself"
            )
        return FactObservation("scorecard", True, evidence_sha256=str(sha))

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
        if row.get("event") != COMPLETION_EVENT:
            continue
        if str((row.get("data") or {}).get("pipeline_run_uid") or "") == identity["pipeline_run_uid"]:
            return False

    facts = receipt.get("verified_facts") or {}
    data = {
        "saga_id": identity["saga_id"],
        "pipeline_run_uid": identity["pipeline_run_uid"],
        "publication_receipt_sha256": facts.get("publication_receipt", ""),
        "closure_receipt_sha256": facts.get("closed_records", ""),
        "scorecard_sha256": facts.get("scorecard", ""),
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

    Looked for, in order: the publication receipt in the run folder; any
    journal row naming release_version/version; the release entry the
    run_created row binds (its frontmatter release_version). Empty when none of
    them say, and empty means "do not touch the marker" — silencing a nag for a
    version this run cannot prove it verified is Argus F-07 with extra steps.
    """
    receipt = run_dir / "publication-receipt.json"
    if receipt.is_file():
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


def clear_publish_pending(studio_root: Path, run_dir: Path) -> str:
    """S3 AC6 (176a8995): verify-live green flips .tropo/publish-pending.json to live.

    Returns a one-line account of what happened, for the operator. Only the
    marker for the version THIS run verified is flipped; a marker for another
    version (a later build awaiting its own publish) is left loud, and a run
    that cannot name its version leaves the marker alone and says so.
    """
    marker = studio_root / PUBLISH_PENDING_REL
    if not marker.is_file():
        return "publish-pending: no marker at %s (nothing to clear)" % marker
    try:
        body = json.loads(marker.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        return "publish-pending: marker %s unreadable (%s) — left as is" % (marker, exc)
    marker_version = _normalise_version(body.get("version"))
    run_version = _release_version_for(run_dir, studio_root)
    if str(body.get("publish_state")) in PUBLISH_PENDING_SILENT_STATES:
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
    })
    staged = marker.with_name("." + marker.name + ".tmp")
    staged.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    staged.replace(marker)
    return "publish-pending: v%s -> live (%s)" % (body["version"], marker)


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
        help="JSONL of the global bus stream; omitted means the bus is unobserved, "
             "which reads as absent rather than as fine",
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

    bus_rows: List[Dict[str, Any]] = []
    if args.bus_events:
        bus_rows = _read_journal(Path(args.bus_events))

    identity = _identity(run_dir)
    if not identity:
        print(
            "[MISUSE] run journal names no saga_id/pipeline_run_uid; there is no "
            "run here to verify",
            file=sys.stderr,
        )
        return EXIT_MISUSE

    try:
        verdict = verify_completion(
            build_observers(run_dir, bus_rows),
            saga_id=identity["saga_id"],
            pipeline_run_uid=identity["pipeline_run_uid"],
        )
    except ReleaseCompletionError as exc:
        print("[MISUSE] %s" % exc, file=sys.stderr)
        return EXIT_MISUSE

    # S3 AC5 (176a8995): observe the public badge — or name why not.
    studio_root = _studio_root_for(args.vault)
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
