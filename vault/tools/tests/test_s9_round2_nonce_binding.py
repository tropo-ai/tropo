#!/usr/bin/env python3
"""S9 round-2 gauntlet — run_nonce binding (dev-spec f417a577).

Reproduces Argus's round-2 adversarial re-verify exactly, inverted: the forge that
CURRENTLY (round-1) authorizes must now REFUSE. Four acceptance checks, per f417a577:

  1. Copy a key minted for scratch run B into scratch run C (identical work-shape).
     Edit C's run.state.json pipeline_run_uid to B's uid AND forge a run_nonce onto C
     (the attacker does not possess B's real nonce — it never traveled in the key —
     so the best they can do is fabricate a value). Verify must REFUSE.
  2. Run B's own verify must still PASS (no regression on the legitimate case).
  3. Two independently-built same-shape runs must produce DIFFERENT fingerprints.
  4. Round-1 win survives: a verbatim key copy into a differently-identified folder
     (different run_uid, no forgery attempt at all) is still refused.

Self-running (python3 test_s9_round2_nonce_binding.py) and pytest-compatible.
"""
import sys, json, tempfile, shutil
from pathlib import Path

_TROPO_SCRIPTS = Path(__file__).resolve().parents[3] / ".tropo" / "scripts"
sys.path.insert(0, str(_TROPO_SCRIPTS))
from lib import release_authorization as ra  # noqa: E402


def _make_run(root: Path, activation_uid: str, run_uid: str, *, cascade=True) -> Path:
    """Same real-runtime-shaped run.jsonl as test_release_authorization.py, PLUS an
    explicit run.state.json carrying pipeline_run_uid (so identity is controllable for
    the forgery step, matching how the real pipeline runtime records it)."""
    folder = root / f"dev-pipeline-{run_uid}-2026-07-04"
    folder.mkdir(parents=True, exist_ok=True)
    events = [{"event": "run_created", "trace_id": activation_uid, "data": {"pipeline": "cd1fcd25"}}]
    events.append({"event": "step_completed", "step": "71a7d016", "trace_id": activation_uid, "data": {}})
    if cascade:
        events.append({"event": "step_completed", "step": ra.TEST_TRIGGER_STEP, "trace_id": activation_uid, "data": {}})
        events.append({"event": "verification_receipt", "step": ra.TEST_TRIGGER_STEP, "trace_id": activation_uid, "data": {"verdict": "pass"}})
        events.append({"event": "step_completed", "step": ra.DOC_TRIGGER_STEP, "trace_id": activation_uid, "data": {}})
        events.append({"event": "verification_receipt", "step": ra.DOC_TRIGGER_STEP, "trace_id": activation_uid, "data": {"verdict": "pass"}})
    (folder / "run.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    (folder / "run.state.json").write_text(json.dumps({"pipeline_run_uid": run_uid}, indent=2))
    return folder


def main():
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    tmp = Path(tempfile.mkdtemp(prefix="s9-round2-"))
    try:
        ra.PIPELINE_RUNS = tmp

        # --- Setup: run B (legit), run C (identical work-shape, independent nonce) ---
        b_folder = _make_run(tmp, "act-b", "b0000001")
        c_folder = _make_run(tmp, "act-c", "c0000002")  # byte-identical work-shape to B

        b_key = ra.mint_key("act-b")
        ra._get_or_create_run_nonce(c_folder)  # simulate C's OWN independent bootstrap
        b_nonce = json.loads((b_folder / "run.state.json").read_text())["run_nonce"]
        c_nonce_before_forge = json.loads((c_folder / "run.state.json").read_text())["run_nonce"]

        # Sanity: bootstrap nonces are independently generated, not equal by chance.
        check("setup sanity — B and C bootstrap nonces differ", b_nonce != c_nonce_before_forge)

        # --- Check 1: the round-2 forge — copy B's key into C, forge identity AND nonce ---
        # The attacker has B's key (fingerprint + run_uid + minted_at) but NOT B's run
        # folder, so NOT B's real nonce (it never travels in the key). They edit C's
        # run.state.json pipeline_run_uid to B's, and fabricate a run_nonce value (the
        # best a real attacker without B's folder could do — a guess, not B's real value).
        (c_folder / ra.KEY_FILENAME).write_text(json.dumps(b_key, indent=2))
        c_state = json.loads((c_folder / "run.state.json").read_text())
        c_state["pipeline_run_uid"] = "b0000001"          # round-1 forge: identity edit
        c_state["run_nonce"] = "deadbeef" * 4              # round-2 forge attempt: fabricated nonce
        (c_folder / "run.state.json").write_text(json.dumps(c_state, indent=2))
        try:
            ra.require_release_authorization("act-c")
            check("round-2 forge (copied key + forged identity + forged nonce) → REFUSED", False)
        except ra.ReleaseAuthorizationError as e:
            check("round-2 forge (copied key + forged identity + forged nonce) → REFUSED", True)
            print(f"    (refused as: {e})")

        # --- Check 2: run B's own verify still PASSES (no regression) ---
        try:
            ra.require_release_authorization("act-b")
            check("run B's own verify → still AUTHORIZED (no regression)", True)
        except ra.ReleaseAuthorizationError:
            check("run B's own verify → still AUTHORIZED (no regression)", False)

        # --- Check 3: two independently-built same-shape runs → DIFFERENT fingerprints ---
        d_folder = _make_run(tmp, "act-d", "d0000003")  # also byte-identical work-shape
        d_key = ra.mint_key("act-d")
        check("independently-built same-shape runs (B vs D) → DIFFERENT fingerprints",
              b_key["fingerprint"] != d_key["fingerprint"])

        # --- Check 4: round-1 win survives — verbatim key copy, no forgery attempt at all ---
        e_folder = _make_run(tmp, "act-e", "e0000004")
        (e_folder / ra.KEY_FILENAME).write_text(json.dumps(b_key, indent=2))  # verbatim copy, untouched
        try:
            ra.require_release_authorization("act-e")
            check("round-1 win — verbatim key copy, untouched foreign folder → REFUSED", False)
        except ra.ReleaseAuthorizationError as e:
            check("round-1 win — verbatim key copy, untouched foreign folder → REFUSED", True)
            print(f"    (refused as: {e})")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  {'✓' if ok else '✗ FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


# pytest entry point
def test_s9_round2_nonce_binding_gauntlet():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
