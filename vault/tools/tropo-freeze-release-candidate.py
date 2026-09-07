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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import release_package  # noqa: E402
from lib import release_verify  # noqa: E402

#: The four instruments the Verify stage declares, by step UID. v1.91 S2
#: (3fb41c99), Argus A155's ruling part 5: derived from
#: release_verify.NODE_INSTRUMENTS, not hand-duplicated -- this dict and
#: release_verify.INSTRUMENT_NODES were a sibling-drift pair with DIFFERENT
#: NAMES for the same four instruments (e.g. "full-release-validation" here,
#: "full-validator" there), so the receipt writer's instrument names never
#: matched what this reader looked for.
INSTRUMENTS: Dict[str, str] = dict(release_verify.NODE_INSTRUMENTS)

FREEZE_STEP = "7de2c49f"

#: The release-pipeline leaf this tool executes (v1.92 Stream 1, AC2).
#: 7de2c49f already declares this exact command in its `verification_command`,
#: and its §Gaps records the wiring closed on 2026-08-16. The binding makes the
#: same fact readable from the runtime side, so a runner asking "what performs
#: the freeze" gets an answer without parsing a vault entry.
PIPELINE_BINDINGS = (
    {
        "step_uid": FREEZE_STEP,
        "kind": "tool",
        # Amended 2026-08-27 with profile 6bf18510, Mike-authorized ("1. approved").
        # THREE shapes have stood here. `:decide` named the PURE half, which
        # computes and writes nothing — the v1.90.0 failure this tool's own
        # comment describes. The bare command string that replaced it could not
        # execute at all: no interpreter, not on PATH, and a static string
        # cannot carry --run-dir/--candidate, which do not exist until a release
        # is running. It failed with exit 127 one step before the fire.
        #
        # The placeholder language ({run_folder}/{candidate_path}) is NOT the
        # cure: nothing substitutes it. 9e7003b1.py:2349 records that family
        # reaching subprocess as a literal and breaking release run bd86ef44.
        #
        # So the declaration names the half that RECORDS, and the runner's
        # adapter supplies the runtime arguments. Neither compensates for the
        # other: a declaration cannot know a run folder, and an adapter must not
        # be where we hide a wrong callable.
        "entry": "tropo-freeze-release-candidate.py:main",
        "description": "freeze the candidate on evidence bound to its exact bytes",
    },
)

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

    # v1.91 S2 AC3 (3fb41c99): "is this run frozen" and "which candidate is
    # live" are answered by lib/release_package's shared resolvers, not by a
    # second loop here. This loop is now identity + reporting-only bookkeeping
    # (who is this run, which shas were EVER invalidated, was a candidate ever
    # built at all) -- none of which the shared resolvers exist to answer.
    # The prior version tracked `already_frozen` itself, and its own comment
    # admitted the defect: two readers of one journal disagreeing --
    # release_package.active_frozen_payload() returned NONE for a run this
    # loop called "already frozen". Found live on v1.90.0 with all four
    # instrument receipts bound and nothing left to do but freeze.
    # metis-g110, 2026-08-22 (found it); argus-a154, 2026-08-23 (ruled the
    # fix is delegation, not a second patch).
    identity: Dict[str, str] = {}
    invalidated = set()
    any_candidate_built = False
    last_built_sha: Optional[str] = None
    for row in rows:
        data = row.get("data") or {}
        for key in ("saga_id", "pipeline_run_uid"):
            if data.get(key) and key not in identity:
                identity[key] = str(data[key])
        event = row.get("event")
        if event == "tropo.release.candidate_built":
            any_candidate_built = True
            last_built_sha = data.get("candidate_sha256")
        elif event == "tropo.release.candidate_invalidated":
            invalidated.add(data.get("candidate_sha256"))

    run_uid = identity.get("pipeline_run_uid", "")
    payload: Dict[str, Any] = {
        "verdict": "fail",
        "verifier_role_resolved": "talos",
        "run_uid": run_uid,
        "candidate_sha256": "",
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

    try:
        active_candidate = release_package.active_candidate(rows, run_uid)
    except release_package.PackageRefusal as exc:
        return payload, str(exc)

    if active_candidate is None:
        if any_candidate_built:
            return payload, (
                "candidate %s carries a live invalidation; it must be rebuilt and "
                "re-verified" % str(last_built_sha)[:16]
            )
        return payload, "no candidate_built event; there is no recorded hash to compare against"

    recorded_sha = active_candidate.get("candidate_sha256")
    payload["candidate_sha256"] = recorded_sha or ""

    # 1 — the bytes are the same bytes.
    rehashed = sha256_file(candidate)
    payload["rehashed_sha256"] = rehashed
    if rehashed != recorded_sha:
        return payload, (
            "the candidate on disk hashes to %s but build recorded %s; every "
            "instrument receipt describes the recorded bytes, not these"
            % (rehashed[:16], str(recorded_sha)[:16])
        )

    # 2 — exactly four passing receipts, bound to these bytes. v1.91 S2
    # (3fb41c99), Argus A155's ruling parts 1/2/5: resolved through
    # release_verify.assert_ready_to_freeze -- the SAME shared resolver the
    # writer (9e7003b1.py's emit_release_verification_receipt) and the
    # publisher (assert_ready_to_publish) use, reading release_kind
    # `release-verification-receipt` rows (NOT the generic dev-pipeline
    # `verification_receipt` name those collided with -- 389 unrelated rows
    # in production under that name, per A155's measurement), keyed by
    # INSTRUMENT NAME (not step uid) and bound on candidate_sha256 (not
    # package_sha256, which no longer exists on the receipt at all: a
    # candidate has no package identity before it is frozen).
    # Bind to THESE bytes before resolving. resolve_receipt_set REFUSES on any
    # receipt whose digest differs rather than ignoring it — correct when a run
    # has one candidate, fatal once a candidate is invalidated and rebuilt: the
    # retired candidate's receipts stay in the append-only journal forever, so
    # the freeze could never pass again. Found live on run 7ee91e0b (argus-a155,
    # 2026-08-24) after Mike ordered a rebuild to fix F1 (33d5bca1): the freeze
    # refused with "the full-validator receipt tested 149e2e98d06e but the bytes
    # about to ship are 3cfb4fe4d537" — naming a candidate this same function had
    # already listed under live_invalidations a few lines earlier.
    #
    # Filtering here does not weaken the check: the resolver still requires all
    # four instruments present and passing FOR THIS DIGEST, so a missing one
    # still refuses. What it stops doing is refusing on evidence about bytes that
    # were deliberately retired and will never ship.
    raw_receipts = [
        row.get("data") or {} for row in rows
        if row.get("event") == release_verify.RECEIPT_KIND
        and (row.get("data") or {}).get("release_run_uid") == run_uid
        and (row.get("data") or {}).get("candidate_sha256") == recorded_sha
    ]
    try:
        by_instrument = release_verify.assert_ready_to_freeze(
            raw_receipts, run_uid, recorded_sha)
    except release_verify.VerifyRefusal as exc:
        payload["instrument_receipts"] = {}
        return payload, str(exc)

    receipts: Dict[str, Dict[str, Any]] = {
        release_verify.INSTRUMENT_NODES[name]: {
            "instrument": name,
            "verdict": receipt.verdict,
            "bound_sha256": receipt.candidate_sha256,
        }
        for name, receipt in by_instrument.items()
    }
    payload["instrument_receipts"] = receipts

    # 3 — no live invalidation. Already guaranteed: active_candidate() above
    # returns None (handled earlier) for exactly this case, so reaching here
    # means the resolver already confirmed recorded_sha is not invalidated.

    # 4 — the freeze is singular.
    try:
        active_frozen = release_package.active_frozen_payload(rows, run_uid)
    except release_package.PackageRefusal as exc:
        return payload, str(exc)
    if active_frozen:
        # The verdict is idempotent on its own act (talos-t63, 2026-09-06;
        # driver-ruled post-lock inclusion on v1.95). This command is BOTH the
        # step's act (--emit) and its declared verification_command, and the
        # runner re-runs the verification after the act: so "already frozen"
        # as a flat refusal meant the step could never pass its own check once
        # it had done its job, and v1.90, v1.93 and v1.94 each amended the
        # criteria to a hand-written script to get past it. Criterion 4 reads
        # "exactly one active package_frozen exists for this run AFTER the
        # step": a freeze that binds THESE bytes is that criterion satisfied.
        # A freeze on DIFFERENT bytes is still the dangerous case and refuses
        # — the same rule release_package.reconcile_existing_freeze applies to
        # the build tool.
        frozen_sha = str(active_frozen.get("package_sha256") or "").strip()
        if not frozen_sha:
            return payload, (
                "this run already has an active package_frozen that records no "
                "digest; refusing to guess whether it binds these bytes"
            )
        if frozen_sha != rehashed:
            return payload, (
                "this run already has an active package_frozen at %s and the "
                "candidate on disk is %s; a second freeze is a supersession and "
                "needs package_superseded, not another freeze"
                % (frozen_sha[:12], rehashed[:12])
            )
        payload["verdict"] = "pass"
        payload["frozen_event_uid"] = "existing"
        payload["rationale"] = (
            "candidate re-hashes to the recorded bytes, all four instrument "
            "receipts bind them, and the run's one active package_frozen binds "
            "these same bytes (criterion 4 holds as the post-state)"
        )
        return payload, None

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
    parser.add_argument("--emit", action="store_true",
                        help="on a PASS verdict, append the tropo.release.package_frozen "
                             "this node declares it emits. Ignored on any other verdict.")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print("[MISUSE] no such run directory: %s" % run_dir, file=sys.stderr)
        return EXIT_MISUSE

    payload, refusal = decide(run_dir, Path(args.candidate))
    if refusal:
        payload["rationale"] = refusal

    # THE MISSING WRITE HALF. This node's own Event Vocabulary declares
    # "tropo.release.package_frozen | this step, on all four criteria | exactly one
    # active per run" -- and nothing implemented it. The studio's only emitter was
    # tropo-build-release.py's stage6, which cannot run while a prior freeze is
    # active. So a run that legitimately superseded a freeze can satisfy every
    # criterion here, verify pass, and still leave the publisher with no digest to
    # bind to: v1.90.0 reached `fire` and was refused with "no package_frozen event".
    # Third instance of one shape in a single release -- package_superseded and
    # candidate_invalidated were the others. The reader, the refusal message and the
    # spec all existed; the writer did not.
    # Emits ONLY on a pass. A refusal can never write a freeze.
    # metis-g110, 2026-08-22.
    if args.emit and refusal is None and payload.get("frozen_event_uid") == "existing":
        print("[NOTE] --emit: the run's active package_frozen already binds these bytes; "
              "nothing written (a second identical freeze would be a duplicate)", file=sys.stderr)
    elif args.emit and refusal is None:
        import uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz
        journal = run_dir / "run.jsonl"
        identity = {}
        for row in read_journal(journal):
            data = row.get("data") or {}
            for key in ("release_activation_uid", "release_pipeline_run_uid",
                        "activation_root_uid", "release_plan_uid", "package_path",
                        "version"):
                if data.get(key) and key not in identity:
                    identity[key] = data[key]
        identity["package_sha256"] = payload["rehashed_sha256"]
        identity["frozen_by_step"] = FREEZE_STEP
        identity["note"] = ("emitted by the freeze step itself on a pass verdict, with "
                            "all four instrument receipts bound to these bytes")
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "event": "tropo.release.package_frozen",
                "ts": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "actor": "/tools/freeze-release-candidate",
                "actor_label_resolved": None,
                "step": FREEZE_STEP, "stage": None, "data": identity,
                "schema_version": 2,
                "trace_id": identity.get("release_pipeline_run_uid", ""),
                "span_id": _uuid.uuid4().hex[:16], "parent_span_id": None,
            }, ensure_ascii=False) + "\n")
        payload["frozen_event_uid"] = "emitted"
    elif args.emit and refusal is not None:
        print("[REFUSED] --emit ignored: the verdict is not pass", file=sys.stderr)

    print(json.dumps(payload, indent=2, sort_keys=True))
    if refusal and not args.quiet:
        print("REFUSED (%s): %s" % (FREEZE_STEP, refusal), file=sys.stderr)
    return EXIT_FROZEN if refusal is None else EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
