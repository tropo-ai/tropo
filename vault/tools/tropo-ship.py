#!/usr/bin/env python3
"""Can this package ship? Three facts, read from the run's own journal.

Mike, 2026-09-07, at maximum frustration after a two-day release:
"I get deny, deny, deny, deny, deny. millions of agent tokens to reason...
Our process is not reliable."

He was right, and here is the measurement that says so. The release machinery
is 21,051 lines. 1,598 of them read the WORLD -- the build guards and the
preflight -- and every real defect this release caught came from those, plus
the agent-executed walks. The other 19,453 lines move the run through its own
states and prove the process was followed. On the night of 2026-09-06 they
produced five refusals and zero findings about the product.

CORRECTION, 2026-09-07 ~02:30Z, before this file is a day old. The 19,453
figure above is INFLATED about sixfold and I am leaving the original sentence
standing with this correction beneath it rather than quietly editing it. Three
of the files I bucketed as ceremony do real work: tropo-build-release.py builds
the box, tropo-publish-release.py uploads, and 9e7003b1.py is the pipeline
runtime that drives 173 non-release runs against 15 release runs and cannot be
deleted for the release's sake. The genuinely release-specific permission
apparatus is about 3,310 lines: the saga orchestrator, the authorization key,
the leg state, and the freeze. Two of the five refusals that cost the night came
from that apparatus; three came from shared machinery that needed fixing, not
deleting. Full working: agents/metis/.tropo-capsule/workspace/
v196-machinery-measurement-CORRECTED.md.

THIS FILE IS A CANDIDATE ANSWER, TO BE SHADOWED AND NOT SWAPPED IN. It answers the only question the fire actually
needs answered, and it reads it from artifacts that already exist:

  1. The bytes are what we think they are.  The zip re-hashes to the digest
     the journal recorded at candidate_built.
  2. Four instruments passed ON THOSE BYTES.  The latest receipt per
     instrument says pass and names that digest. Latest governs: re-running an
     instrument after a cure is the only way a failed one ever passes.
  3. A human who did not drive the run said go, about those bytes.

Nothing else gates. Not step statuses, not the authorization key's fingerprint,
not the saga's 69 checkpoints, not the scorecard schema, not the ratchet. Those
are records. Records are worth keeping and worth reading; they are not worth
refusing on. That is Mike's own warn-safe ruling (deb77758) and his compiler
ruling (f015eb797361) applied to our own pipeline, which is the one place the
Metis line never applied them.

Exit 0 = GO, and the one line naming what may now happen.
Exit 1 = NO, and the one fact that is missing, in the words of the thing that
is missing it. No second refusal is printed: an operator fixes one thing.

This tool never publishes. It decides. The outward act stays where it is --
tropo-publish-release.py fire -- because uploading bytes to GitHub and a bucket
is real work, not ceremony. What this replaces is the permission apparatus in
front of it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

RECEIPT_KIND = "release-verification-receipt"
CANDIDATE_BUILT = "tropo.release.candidate_built"
CANDIDATE_INVALIDATED = "tropo.release.candidate_invalidated"
#: The four instruments AC7 binds. Named here, once, in the order a human reads.
INSTRUMENTS = ("full-validator", "release-harness", "external-test", "cold-walk")
PASSING = ("pass", "passed")


def read_journal(run_dir: Path) -> list:
    p = run_dir / "run.jsonl"
    if not p.is_file():
        raise SystemExit(f"NO: {p} does not exist, so there is no run to read.")
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def active_digest(rows: list) -> str:
    """The digest of the candidate that is live now, after invalidations."""
    live = None
    for r in rows:
        d = r.get("data") or {}
        kind = r.get("event") or r.get("type") or ""
        if kind == CANDIDATE_BUILT:
            live = str(d.get("candidate_sha256") or "")
        elif kind == CANDIDATE_INVALIDATED:
            if live == str(d.get("candidate_sha256") or ""):
                live = None
    return live or ""


def latest_receipts(rows: list, digest: str) -> dict:
    """Latest receipt per instrument. Later governs earlier, always."""
    out = {}
    for r in rows:
        d = r.get("data") or {}
        if str(d.get("receipt_kind") or "") != RECEIPT_KIND:
            continue
        if str(d.get("candidate_sha256") or "") != digest:
            continue
        out[str(d.get("instrument") or "")] = d
    return out


def human_go(rows: list) -> dict:
    """The last accepted signoff by someone who did not drive the run."""
    drivers = {str(r.get("actor") or "") for r in rows
               if r.get("event") in ("step_completed", "step_started")}
    best = None
    for r in rows:
        if r.get("event") != "human_signoff":
            continue
        d = r.get("data") or {}
        if str(d.get("verdict") or "") != "accepted":
            continue
        who = str(r.get("actor") or "")
        if who and who not in drivers:
            best = {"who": who, "at": r.get("ts"), "step": r.get("step")}
    return best or {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, help="the release run folder")
    ap.add_argument("--candidate", required=True, help="path to the .zip about to ship")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    run_dir, zip_path = Path(args.run_dir), Path(args.candidate)
    rows = read_journal(run_dir)

    digest = active_digest(rows)
    if not digest:
        return say(args, False, "no live candidate on this run: nothing was built, or every "
                                "candidate built was invalidated. Build one.")

    if not zip_path.is_file():
        return say(args, False, f"the candidate file {zip_path} does not exist.")
    h = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if h != digest:
        return say(args, False, f"the bytes are not the bytes: {zip_path.name} hashes to "
                                f"{h[:12]}, the run recorded {digest[:12]}. Something changed "
                                f"under the verification.")

    receipts = latest_receipts(rows, digest)
    for name in INSTRUMENTS:
        got = receipts.get(name)
        if not got:
            return say(args, False, f"{name} has no receipt naming {digest[:12]}. Run it.")
        if str(got.get("verdict") or "") not in PASSING:
            return say(args, False, f"{name} reported {got.get('verdict')!r} on {digest[:12]}. "
                                    f"Cure what it found, run it again; the later receipt governs.")

    go = human_go(rows)
    if not go:
        return say(args, False, "no accepted signoff from someone who did not drive this run. "
                                "A person who did not execute the steps has to say go.")

    return say(args, True,
               f"{zip_path.name} may ship. Digest {digest[:12]}; "
               f"{', '.join(INSTRUMENTS)} all pass on it; {go['who']} said go at {go['at']}.",
               digest=digest, signoff=go)


def say(args, ok: bool, msg: str, **extra) -> int:
    if args.json:
        print(json.dumps({"go": ok, "reason": msg, **extra}, indent=2, sort_keys=True))
    else:
        print(("GO — " if ok else "NO — ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
