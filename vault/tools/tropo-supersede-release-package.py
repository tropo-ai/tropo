#!/usr/bin/env python3
"""---
uid: 5c7e91a4
type: tool
name: tropo-supersede-release-package
title: tropo-supersede-release-package.py — retire a frozen package, pre-public, on the record
status: active
owner: metis
extraction_scope: ship
schema_version: 2
created: '2026-08-22'
created_by: metis-g110
built_under: '2fae6312'
---

tropo-supersede-release-package.py — the missing write half of `package_superseded`.

The sibling of `tropo-freeze-release-candidate.py` (2d7b6ef4). That tool decides a
freeze; this one retires one. Until now only the READ half existed:
`PACKAGE_SUPERSEDED_EVENT` was declared in `lib/release_package.py`, consumed by
`active_frozen_payload()`, asserted by the 2fae6312 test suite, and named as the
cure in two separate refusal messages — with nothing anywhere able to emit it.

v1.90.0 walked into it. The CHANGELOG ship gate fires at stage, AFTER the freeze,
so promoting `[Unreleased]` to `[1.90.0]` forced a rebuild; the rebuild produced
different bytes; and the freeze reconciliation refused with

    "One release run has one package identity ... needs package_superseded,
     not another freeze"

pointing at a door with no handle on this side.

    python3 vault/tools/tropo-supersede-release-package.py \\
        --run-dir <release run> \\
        --old-sha <the frozen digest being retired> \\
        --reason "<why the bytes people verified are not the bytes that ship>" \\
        [--new-sha <the replacement digest>] [--actor <agent-gen>]

WHAT IT REFUSES, and none of these is negotiable:

  1. no active `package_frozen` for the run — there is nothing to supersede;
  2. `--old-sha` does not match the active freeze — superseding a digest that
     is not the live one is how a stale freeze survives a supersession;
  3. the package has already been published — supersession is a PRE-PUBLIC act.
     After the fire it is a new release, not a quieter edit of an old one.

Every superseded digest keeps its receipts in the journal. Nothing is deleted:
the record says these bytes were verified, and then says they were replaced and
why. That pairing is the whole value — a release that repackaged late should be
able to prove it repackaged late.

Exit 0 when the supersession is recorded, 1 when refused, 4 on misuse.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import release_package as pkg  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_MISUSE = 4

PUBLISHED_EVENTS = ("tropo.release.published",)


def read_journal(path: Path) -> List[Dict[str, Any]]:
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


def run_uid_from(rows: List[Dict[str, Any]]) -> str:
    for row in rows:
        data = row.get("data") or {}
        for key in ("release_pipeline_run_uid", "pipeline_run_uid"):
            if data.get(key):
                return str(data[key])
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--old-sha", default=None,
                    help="the frozen digest being retired; required unless --candidate-only")
    ap.add_argument("--candidate-only", action="store_true",
                    help="skip the package half and retire only a candidate. For the case "
                         "where the freeze was already superseded and the candidate axis "
                         "was missed — which is exactly how v1.90.0 found this gap.")
    ap.add_argument("--reason", required=True,
                    help="why the verified bytes are not the shipping bytes; goes in the record")
    ap.add_argument("--new-sha", default=None)
    ap.add_argument("--actor", default="metis-g110")
    ap.add_argument("--invalidate-candidate", default=None, metavar="SHA",
                    help="also retire the CANDIDATE of the same name. Distinct event on "
                         "purpose (lib/release_package.py says so): superseding a frozen "
                         "package does not retire the candidate that produced it, and a "
                         "run with two live candidates refuses because receipts bind to a "
                         "candidate digest. v1.90.0 hit both axes in the same gesture.")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    journal = run_dir / "run.jsonl"
    if not journal.is_file():
        print(f"MISUSE: no run.jsonl under {run_dir}", file=sys.stderr)
        return EXIT_MISUSE

    rows = read_journal(journal)
    run_uid = run_uid_from(rows)
    if not run_uid:
        print("REFUSED: the run journal names no pipeline run uid", file=sys.stderr)
        return EXIT_REFUSED

    # 3 — pre-public only.
    for row in rows:
        if pkg.event_type(row) in PUBLISHED_EVENTS:
            print("REFUSED: this run has already published. Supersession is a "
                  "pre-public act; after the fire the cure is a new release.",
                  file=sys.stderr)
            return EXIT_REFUSED

    if args.candidate_only:
        if not args.invalidate_candidate:
            print("MISUSE: --candidate-only needs --invalidate-candidate", file=sys.stderr)
            return EXIT_MISUSE
        try:
            still = pkg.active_frozen_payload(rows, run_uid)
        except pkg.PackageRefusal as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return EXIT_REFUSED
        if still:
            print(f"REFUSED: --candidate-only, but an active package_frozen "
                  f"({str(still.get('package_sha256'))[:12]}) is still live. Retire "
                  f"the package first; a candidate cannot be retired out from under "
                  f"a freeze that still points at it.", file=sys.stderr)
            return EXIT_REFUSED
        recorded = ""
    else:
        if not args.old_sha:
            print("MISUSE: --old-sha is required unless --candidate-only", file=sys.stderr)
            return EXIT_MISUSE
        # 1 + 2 — there is an active freeze and it is the one being named.
        try:
            active = pkg.active_frozen_payload(rows, run_uid)
        except pkg.PackageRefusal as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return EXIT_REFUSED
        if not active:
            print(f"REFUSED: run {run_uid} carries no active package_frozen; there "
                  f"is nothing to supersede.", file=sys.stderr)
            return EXIT_REFUSED

        recorded = str(active.get("package_sha256") or "")
        if recorded != args.old_sha:
            print(f"REFUSED: --old-sha {args.old_sha[:12]} is not the active freeze "
                  f"({recorded[:12]}). Superseding a digest that is not live is how "
                  f"a stale freeze survives its own supersession.", file=sys.stderr)
            return EXIT_REFUSED

    if not args.candidate_only:
        payload = pkg.package_superseded_payload(
            run_uid=run_uid,
            old_package_sha256=recorded,
            reason=args.reason,
            new_package_sha256=args.new_sha,
            superseded_by=args.actor,
        )
        for key in ("release_activation_uid", "activation_root_uid", "release_plan_uid", "version"):
            if active.get(key):
                payload.setdefault(key, active[key])

        event = {
            "event": pkg.PACKAGE_SUPERSEDED_EVENT,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "actor": args.actor,
            "actor_label_resolved": "/tools/supersede-release-package",
            "step": None,
            "stage": None,
            "data": payload,
            "schema_version": 2,
            "trace_id": run_uid,
            "span_id": uuid.uuid4().hex[:16],
            "parent_span_id": None,
        }
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

        # Prove the read side agrees: the freeze must now be gone.
        after = pkg.active_frozen_payload(read_journal(journal), run_uid)
        if after is not None:
            print("REFUSED (post-write): the supersession was appended but the active "
                  "freeze did not clear. Do not proceed; the record is inconsistent.",
                  file=sys.stderr)
            return EXIT_REFUSED

    # The candidate axis. Superseding the frozen package leaves the candidate that
    # produced it live, and a run with two live candidates refuses on the next read
    # because receipts bind to a candidate digest, not a package one. Checking one
    # invariant and not its sibling is the whole reason this needed a second pass.
    invalidated = None
    if args.invalidate_candidate:
        rows_now = read_journal(journal)
        if args.invalidate_candidate == (args.new_sha or ""):
            print("REFUSED: --invalidate-candidate names the replacement digest. "
                  "That would retire the candidate you are about to ship.",
                  file=sys.stderr)
            return EXIT_REFUSED
        seen = any(
            pkg.event_type(r) == pkg.CANDIDATE_BUILT_EVENT
            and str((r.get("data") or {}).get("candidate_sha256") or "") == args.invalidate_candidate
            for r in rows_now
        )
        if not seen:
            print(f"REFUSED: no candidate_built for {args.invalidate_candidate[:12]}; "
                  f"there is no candidate by that name to invalidate.", file=sys.stderr)
            return EXIT_REFUSED
        inv = pkg.candidate_invalidated_payload(
            run_uid, args.invalidate_candidate,
            f"superseded alongside package {recorded[:12]}: {args.reason}",
        )
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "event": pkg.CANDIDATE_INVALIDATED_EVENT,
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "actor": args.actor,
                "actor_label_resolved": "/tools/supersede-release-package",
                "step": None, "stage": None, "data": inv,
                "schema_version": 2, "trace_id": run_uid,
                "span_id": uuid.uuid4().hex[:16], "parent_span_id": None,
            }, ensure_ascii=False) + "\n")
        invalidated = args.invalidate_candidate
        # Prove this side too: exactly one live candidate, and it is the new one.
        try:
            live = pkg.active_candidate(read_journal(journal), run_uid)
        except pkg.PackageRefusal as exc:
            print(f"REFUSED (post-write): candidate axis still ambiguous: {exc}",
                  file=sys.stderr)
            return EXIT_REFUSED
        live_sha = str((live or {}).get("candidate_sha256") or "")
        if args.new_sha and live_sha != args.new_sha:
            print(f"REFUSED (post-write): expected {args.new_sha[:12]} live, got "
                  f"{live_sha[:12] or 'NONE'}.", file=sys.stderr)
            return EXIT_REFUSED

    print(json.dumps({
        "superseded_package": recorded,
        "invalidated_candidate": invalidated,
        "replacement": args.new_sha,
        "run_uid": run_uid,
        "reason": args.reason,
        "active_freeze_after": None,
        "verdict": "recorded",
    }, indent=1))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
