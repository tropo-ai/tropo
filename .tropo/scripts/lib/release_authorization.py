#!/usr/bin/env python3
"""release_authorization.py — the Pipeline Activation Key gate (dev-spec 2ffdd9d6, brief f8cda3dd).

Fingerprint-as-key. The pipeline runtime mints a key when a run legitimately reaches the
produce-release-folder gate (all prior gates green + the doc/test cascade fired). The build and
ship tools REFUSE without it. The key is a fingerprint of the run's work record — you cannot
mint it without the run having done the work.

THREAT MODEL (honest, per the brief's "later, not now"):
  NOW (private studio, trusted agents): this defeats the ACCIDENTAL shortcut — running
  build/ship with no activation, no pipeline-run, or a run that never reached the gate. The
  fingerprint binds the key to the run's actual event record.
  LATER (marketplace, untrusted agents): true anti-forgery against a malicious agent who
  replays the hash needs cryptographic signing (HMAC/PKI). The fingerprint is chosen so a
  signature wraps the SAME primitive later — no redesign. Until then: plain SHA-256.

Importable (require_release_authorization / mint_key) and a CLI (mint / verify).
"""
import sys, json, hashlib, argparse
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_RUNS = VAULT_ROOT / "vault" / "pipeline-runs"
GATE_PRODUCE = "produce-release-folder"
KEY_FILENAME = "release-authorization.json"

# Events that constitute the "work record" the fingerprint is computed over.
# NOTE: human_signoff is DELIBERATELY excluded — the fingerprint attests the PIPELINE ran (and
# is minted at the produce gate, before any ship signoff). The human signoff is a SEPARATE ship
# gate (checked by _has_human_signoff), so recording it later does not invalidate the key.
_WORK_EVENTS = ("step_completed", "verification_receipt")
# dev-pipeline cascade trigger steps (4.5 doc / 4.6 test). The cascade "fired" = both of these
# trigger-step UIDs have a step_completed event in the run (verified against real run.jsonl,
# not assumed — the structural proof the protocol was followed).
DOC_TRIGGER_STEP = "0cf86ea5"
TEST_TRIGGER_STEP = "4f64ec3c"


def _verdict(e):
    return e.get("verdict") or (e.get("data") or {}).get("verdict") or ""


def _step(e):
    return e.get("step") or e.get("step_name") or ""


class ReleaseAuthorizationError(Exception):
    """Raised on any authorization failure. Callers treat as fail-closed (refuse)."""


def _read_run_events(run_folder: Path):
    """Read all run.jsonl segment events in order. Empty list if none."""
    events = []
    idx = run_folder / "run-index.json"
    segments = ["run.jsonl"]
    if idx.is_file():
        try:
            segments = json.loads(idx.read_text()).get("segments", ["run.jsonl"])
        except Exception:
            segments = ["run.jsonl"]
    for seg in segments:
        p = run_folder / seg
        if not p.is_file():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue  # a malformed line is not a valid work event; fail-closed downstream
    return events


def find_run_folder(activation_uid: str) -> Path:
    """Locate the pipeline-run folder whose run records this activation. Fail-closed (raise)."""
    if not PIPELINE_RUNS.is_dir():
        raise ReleaseAuthorizationError("no pipeline-runs directory")
    matches = []
    for folder in PIPELINE_RUNS.iterdir():
        if not folder.is_dir():
            continue
        for ev in _read_run_events(folder):
            # Real runtime links the run to its activation via the event trace_id; keep the
            # activation_uid/activation fields as fallback for other shapes.
            if (ev.get("trace_id") == activation_uid
                    or ev.get("activation_uid") == activation_uid
                    or ev.get("activation") == activation_uid):
                matches.append(folder)
                break
    if not matches:
        raise ReleaseAuthorizationError(
            f"no pipeline-run found for activation {activation_uid!r} — "
            f"the release did not go through the pipeline (no key can exist)")
    # newest by mtime if more than one (re-runs/supersession)
    return max(matches, key=lambda f: f.stat().st_mtime)


def compute_fingerprint(run_folder: Path, gate: str = GATE_PRODUCE) -> str:
    """SHA-256 over the run's ordered work record up to and including the gate's completion.

    Requires the gate step to have completed AND the doc/test cascade to have fired — else
    the run never legitimately reached the gate and NO fingerprint is mintable (raise)."""
    events = _read_run_events(run_folder)
    work = [e for e in events if e.get("event") in _WORK_EVENTS]

    # The run must have actually progressed (not an empty/bootstrap-only run). Minting
    # happens AT the produce gate, so we require progress + the cascade, not produce-already-
    # completed (which would be a chicken-and-egg at mint time).
    if not any(e.get("event") == "step_completed" for e in events):
        raise ReleaseAuthorizationError(
            "run has completed no steps — not eligible for a key (empty/bootstrap-only run)")

    # The doc/test pipeline cascade (dev-pipeline steps 4.5/4.6) MUST have fired — proven by a
    # step_completed for BOTH trigger-step UIDs. This is the structural proof the release
    # protocol was followed, not shortcut. (Verified against real run.jsonl event shapes.)
    completed_steps = {_step(e) for e in events if e.get("event") == "step_completed"}
    if DOC_TRIGGER_STEP not in completed_steps or TEST_TRIGGER_STEP not in completed_steps:
        raise ReleaseAuthorizationError(
            "doc/test pipeline cascade (steps 4.5/4.6) did not fire in the run — "
            "the protocol was not followed; no key")

    canonical = "\n".join(f"{e.get('event')}|{_step(e)}|{_verdict(e)}" for e in work)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mint_key(activation_uid: str, gate: str = GATE_PRODUCE) -> dict:
    """Mint the key for a run that legitimately reached the gate. Runtime-only caller."""
    run_folder = find_run_folder(activation_uid)
    fp = compute_fingerprint(run_folder, gate)  # raises if the run isn't eligible
    events = _read_run_events(run_folder)
    key = {
        "activation_uid": activation_uid,
        "gate": gate,
        "fingerprint": fp,
        "minted_at_event": len(events),
        "minted_by": "pipeline-runtime",
    }
    (run_folder / KEY_FILENAME).write_text(json.dumps(key, indent=2))
    return key


def _has_human_signoff(run_folder: Path) -> bool:
    for e in _read_run_events(run_folder):
        if e.get("event") == "human_signoff" and _verdict(e) in ("accepted", "accepted_with_exceptions"):
            return True
    return False


def require_release_authorization(activation_uid: str, gate: str = GATE_PRODUCE,
                                  *, require_human_signoff: bool = False) -> dict:
    """The gate. Returns the key dict on success; raises ReleaseAuthorizationError otherwise.

    Fail-closed: ANY failure (no activation, no run, no key, fingerprint mismatch, missing
    signoff, unexpected error) refuses. There is no override flag (dev-spec AC-5)."""
    try:
        if not activation_uid:
            raise ReleaseAuthorizationError("no --activation-uid supplied (no key, no run)")
        run_folder = find_run_folder(activation_uid)
        key_path = run_folder / KEY_FILENAME
        if not key_path.is_file():
            raise ReleaseAuthorizationError(
                f"no release-authorization key in {run_folder.name} — "
                f"the run never reached the produce-release-folder gate")
        try:
            key = json.loads(key_path.read_text())
        except Exception as e:
            raise ReleaseAuthorizationError(f"key file unreadable/malformed: {e}")
        stored = key.get("fingerprint")
        # Recompute from the live run record; a forged/stale key won't match an eligible run,
        # and an ineligible run can't recompute at all (compute_fingerprint raises).
        live = compute_fingerprint(run_folder, gate)
        if not stored or stored != live:
            raise ReleaseAuthorizationError(
                "key fingerprint does not match the run's work record "
                "(forged, stale, or tampered key)")
        if require_human_signoff and not _has_human_signoff(run_folder):
            raise ReleaseAuthorizationError(
                "public ship requires a human_signoff event in the run — none found "
                "(the human key was not turned)")
        return key
    except ReleaseAuthorizationError:
        raise
    except Exception as e:  # fail-closed on anything unexpected
        raise ReleaseAuthorizationError(f"authorization check failed (fail-closed): {e}")


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Pipeline Activation Key — mint/verify release authorization")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mint", help="mint the key (runtime use, at the produce-release-folder gate)")
    m.add_argument("--activation-uid", required=True)
    m.add_argument("--gate", default=GATE_PRODUCE)
    v = sub.add_parser("verify", help="check authorization (exit 0 = authorized, nonzero = refused)")
    v.add_argument("--activation-uid", required=True)
    v.add_argument("--gate", default=GATE_PRODUCE)
    v.add_argument("--require-human-signoff", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "mint":
            key = mint_key(args.activation_uid, args.gate)
            print(json.dumps(key, indent=2)); return 0
        else:
            require_release_authorization(args.activation_uid, args.gate,
                                          require_human_signoff=args.require_human_signoff)
            print("AUTHORIZED"); return 0
    except ReleaseAuthorizationError as e:
        print(f"REFUSED: {e}", file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(_main())
