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
import importlib.util
import json
import sys
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

    if args.json:
        print(json.dumps(
            {
                "complete": verdict.complete,
                "partial_state": verdict.partial_state,
                "missing": verdict.missing,
                "detail": verdict.detail,
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
        if verdict.complete:
            print("COMPLETE — %s" % COMPLETION_EVENT)
        else:
            print("INCOMPLETE — %s" % verdict.partial_state)
            print("  %s" % verdict.detail)

    if verdict.complete and args.write_receipt:
        target = run_dir / "completion-receipt.json"
        target.write_text(
            json.dumps(verdict.receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print("receipt: %s" % target)

    return verdict.exit_code


if __name__ == "__main__":
    sys.exit(main())
