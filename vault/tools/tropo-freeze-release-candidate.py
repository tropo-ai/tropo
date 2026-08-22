#!/usr/bin/env python3
"""---
uid: 2d7b6ef4
type: tool
name: tropo-freeze-release-candidate
title: tropo-freeze-release-candidate.py — decide the freeze on the bytes and the receipts
status: active
owner: talos
extraction_scope: ship
schema_version: 2
created: '2026-08-16'
created_by: talos-t44
built_under: '2fae6312'
---

tropo-freeze-release-candidate.py — the verdict producer for step 7de2c49f.

Dev-spec 2fae6312 (locked), step 4's executor. The WorkflowNode
`release-freeze-verified-package` declares `verification_class: true`, and a
vc:true step with no runnable verdict source is a self-attestation hole — the
step reports whatever the operator says it reports. This is the command that
makes its verdict a measurement.

    python3 vault/tools/tropo-freeze-release-candidate.py \\
        --run-dir <release run> --candidate <path to the zip>

WHAT IT DECIDES, in the order the node declares:

  1. the candidate on disk re-hashes to the candidate_sha256 recorded at build;
  2. exactly four passing instrument receipts exist for
     (run_uid, candidate_sha256, instrument), one per declared instrument;
  3. no candidate_invalidated is live for that candidate; and
  4. no active package_frozen exists yet for the run.

All four, or it refuses. Three receipts and one absent is a fail, not a
rounding error — the whole point of the node is that the freeze follows its
evidence rather than preceding it.

Exit 0 with the verification payload on stdout when the freeze is earned,
1 with the failing criterion named when it is not. The payload is the shape
`9e7003b1.py verify-step 7de2c49f --verification-data-stdin` consumes, so the
verdict this command computes is the verdict the pipeline records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: The four instruments the Verify stage declares, by step UID.
INSTRUMENTS: Dict[str, str] = {
    "4262d5fa": "full-release-validation",
    "a0f2bea8": "release-harness-gate",
    "bc6b17ec": "external-test",
    "c6b61fb9": "cold-boot-walk",
}

FREEZE_STEP = "7de2c49f"

EXIT_FROZEN = 0
EXIT_REFUSED = 1
EXIT_MISUSE = 4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def decide(run_dir: Path, candidate: Path) -> Tuple[Dict[str, Any], Optional[str]]:
    """Return (payload, refusal). `refusal` is None when the freeze is earned."""
    rows = read_journal(run_dir / "run.jsonl")

    identity: Dict[str, str] = {}
    recorded_sha: Optional[str] = None
    invalidated = set()
    already_frozen = False
    for row in rows:
        data = row.get("data") or {}
        for key in ("saga_id", "pipeline_run_uid"):
            if data.get(key) and key not in identity:
                identity[key] = str(data[key])
        event = row.get("event")
        if event == "tropo.release.candidate_built":
            recorded_sha = data.get("candidate_sha256")
        elif event == "tropo.release.candidate_invalidated":
            invalidated.add(data.get("candidate_sha256"))
        elif event == "tropo.release.package_frozen":
            already_frozen = True

    run_uid = identity.get("pipeline_run_uid", "")
    payload: Dict[str, Any] = {
        "verdict": "fail",
        "verifier_role_resolved": "talos",
        "run_uid": run_uid,
        "candidate_sha256": recorded_sha or "",
        "rehashed_sha256": "",
        "instrument_receipts": {},
        "live_invalidations": sorted(x for x in invalidated if x),
        "frozen_event_uid": None,
        "rationale": "",
    }

    if not run_uid:
        return payload, "the run journal names no pipeline_run_uid"
    if not candidate.is_file():
        return payload, "no candidate at %s" % candidate
    if recorded_sha is None:
        return payload, "no candidate_built event; there is no recorded hash to compare against"

    # 1 — the bytes are the same bytes.
    rehashed = sha256_file(candidate)
    payload["rehashed_sha256"] = rehashed
    if rehashed != recorded_sha:
        return payload, (
            "the candidate on disk hashes to %s but build recorded %s; every "
            "instrument receipt describes the recorded bytes, not these"
            % (rehashed[:16], str(recorded_sha)[:16])
        )

    # 2 — exactly four passing receipts, bound to these bytes.
    receipts: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("event") != "verification_receipt":
            continue
        data = row.get("data") or {}
        step = data.get("instrument_step_uid") or row.get("step")
        if step not in INSTRUMENTS:
            continue
        if str(data.get("pipeline_run_uid") or run_uid) != run_uid:
            continue
        if data.get("candidate_sha256") != recorded_sha:
            continue
        if str(data.get("verdict")) != "pass":
            continue
        receipts[step] = {
            "receipt_uid": data.get("receipt_uid") or row.get("span_id") or "",
            "verdict": "pass",
            "bound_sha256": recorded_sha,
        }
    payload["instrument_receipts"] = receipts

    missing = [
        "%s (%s)" % (uid, name)
        for uid, name in INSTRUMENTS.items()
        if uid not in receipts
    ]
    if missing:
        return payload, (
            "%d of 4 instrument receipt(s) absent for this candidate: %s"
            % (len(missing), ", ".join(sorted(missing)))
        )

    # 3 — no live invalidation.
    if recorded_sha in invalidated:
        return payload, (
            "candidate %s carries a live invalidation; it must be rebuilt and "
            "re-verified" % str(recorded_sha)[:16]
        )

    # 4 — the freeze is singular.
    if already_frozen:
        return payload, (
            "this run already has an active package_frozen; a second freeze is a "
            "supersession and needs package_superseded, not another freeze"
        )

    payload["verdict"] = "pass"
    payload["rationale"] = (
        "candidate re-hashes to the recorded bytes and all four instrument "
        "receipts bind them"
    )
    return payload, None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Decide whether a release candidate has earned its freeze."
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print("[MISUSE] no such run directory: %s" % run_dir, file=sys.stderr)
        return EXIT_MISUSE

    payload, refusal = decide(run_dir, Path(args.candidate))
    if refusal:
        payload["rationale"] = refusal

    print(json.dumps(payload, indent=2, sort_keys=True))
    if refusal and not args.quiet:
        print("REFUSED (%s): %s" % (FREEZE_STEP, refusal), file=sys.stderr)
    return EXIT_FROZEN if refusal is None else EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
