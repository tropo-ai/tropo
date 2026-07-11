#!/usr/bin/env python3
"""Ship-gate hole fix gauntlet (5864c0b6, assigned Talos, surfaced Argus S9 round-3).

Reproduces the exact round-3 forge — an executing agent appends a self-authored
{"event": "human_signoff", "data": {"verdict": "accepted"}} line to its own run.jsonl and
the public-ship gate (_has_human_signoff in .tropo/scripts/lib/release_authorization.py,
live at tropo-build-release.py:2196 require_release_authorization(require_human_signoff=True))
flips REFUSED -> AUTHORIZED with no check on who actually authored the signoff. The fix ports
the runtime's already-correct human: criterion checks (vault/tools/9e7003b1.py
evaluate_criterion, lines ~694-731) verbatim: trust only the engine-stamped ev.actor,
require it resolve to a REGISTERED principal, and require that principal differ from every
principal that executed a step in the run.

Three acceptance criteria (per 5864c0b6 + the assignment brief), each its own test:

  1. The exact round-3 forge must now REFUSE: a human_signoff event whose actor IS one of
     the run's own step-executor actors (self-authored while "executing" the run).
  2. A genuinely independent, Mike-authored signoff must still PASS: actor resolves to a
     registered principal that is NOT any run executor.
  3. An unregistered/bare actor must fail CLEANLY (a refusal, not a crash) — no accidental
     free pass just because the label doesn't resolve.

Uses REAL registered vault principals (not synthetic mocks that assume the fix's own
correctness) — "argus" and "talos" (registered agent-executive principals) and
"mike-maziarz" (a registered human principal) — resolved against the actual live vault via
_resolve_principal_uid, exactly as the shipped gate does at runtime. This is deliberately
NOT a self-consistent fixture: the realistic event-log shapes are lifted from a real
vault/pipeline-runs/ run (dev-pipeline-896e6c9b-2026-07-02/run.jsonl), and principal
resolution goes through the actual vault/files/ registry, not a stub.

Self-running (python3 test_shipgate_signoff_independence.py) and pytest-compatible.
"""
import sys
import json
import tempfile
import shutil
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
_TROPO_SCRIPTS = VAULT_ROOT / ".tropo" / "scripts"
sys.path.insert(0, str(_TROPO_SCRIPTS))
from lib import release_authorization as ra  # noqa: E402
from lib._identity import _resolve_principal_uid  # noqa: E402

# Real, currently-registered principals in THIS vault (checked at test collection time so a
# failure here means the fixture assumptions are stale, not that the security fix is broken).
_EXECUTOR_ACTOR = "argus"          # registered agent-executive principal
_INDEPENDENT_ACTOR = "mike-maziarz"  # registered human principal, distinct from _EXECUTOR_ACTOR
_UNREGISTERED_ACTOR = "totally-unregistered-actor-xyz-does-not-exist"


def _make_run(root: Path, activation_uid: str, *, signoff_actor, signoff_via_data_field=False) -> Path:
    """Real-runtime-shaped run.jsonl (verified against vault/pipeline-runs/ output): the run's
    executor (whoever ran step_completed) is _EXECUTOR_ACTOR throughout, matching how a real
    dev-pipeline run looks (one agent executes the whole run). The doc/test cascade fires (so
    a key CAN legitimately mint), and a human_signoff event is appended with the actor under
    test.

    signoff_via_data_field: when True, the signoff carries NO top-level `actor` at all and
    instead tries to smuggle identity through data.signer_principal_uid/data.signed_by — the
    exact self-reported-field bypass the fix must NOT trust (property 1 of the port)."""
    folder = root / f"dev-pipeline-{activation_uid}-2026-07-04"
    folder.mkdir(parents=True, exist_ok=True)
    events = [{"event": "run_created", "trace_id": activation_uid, "data": {"pipeline": "cd1fcd25"}}]
    events.append({"event": "step_completed", "actor": _EXECUTOR_ACTOR, "step": "71a7d016",
                   "trace_id": activation_uid, "data": {}})
    events.append({"event": "step_completed", "actor": _EXECUTOR_ACTOR, "step": ra.TEST_TRIGGER_STEP,
                   "trace_id": activation_uid, "data": {}})
    events.append({"event": "verification_receipt", "step": ra.TEST_TRIGGER_STEP,
                   "trace_id": activation_uid, "data": {"verdict": "pass"}})
    events.append({"event": "step_completed", "actor": _EXECUTOR_ACTOR, "step": ra.DOC_TRIGGER_STEP,
                   "trace_id": activation_uid, "data": {}})
    events.append({"event": "verification_receipt", "step": ra.DOC_TRIGGER_STEP,
                   "trace_id": activation_uid, "data": {"verdict": "pass"}})
    if signoff_via_data_field:
        # The forge variant that smuggles identity through a self-reported data field instead
        # of the engine-stamped actor — must NOT be trusted (no top-level actor at all).
        events.append({"event": "human_signoff", "trace_id": activation_uid,
                       "data": {"verdict": "accepted", "signed_by": signoff_actor,
                                "signer_principal_uid": _resolve_principal_uid(signoff_actor, VAULT_ROOT)}})
    else:
        events.append({"event": "human_signoff", "actor": signoff_actor,
                       "trace_id": activation_uid, "data": {"verdict": "accepted"}})
    (folder / "run.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return folder


def main():
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    # Sanity-check the fixture assumptions against the REAL live vault before trusting any
    # pass/fail below — a stale assumption here must fail loudly, not silently validate nothing.
    executor_uid = _resolve_principal_uid(_EXECUTOR_ACTOR, VAULT_ROOT)
    independent_uid = _resolve_principal_uid(_INDEPENDENT_ACTOR, VAULT_ROOT)
    check(f"fixture sanity: {_EXECUTOR_ACTOR!r} resolves to a registered principal", executor_uid is not None)
    check(f"fixture sanity: {_INDEPENDENT_ACTOR!r} resolves to a registered principal", independent_uid is not None)
    check("fixture sanity: executor and independent signer are DIFFERENT principals",
          executor_uid is not None and independent_uid is not None and executor_uid != independent_uid)
    check(f"fixture sanity: {_UNREGISTERED_ACTOR!r} does NOT resolve",
          _resolve_principal_uid(_UNREGISTERED_ACTOR, VAULT_ROOT) is None)

    tmp = Path(tempfile.mkdtemp(prefix="shipgate-signoff-"))
    try:
        ra.PIPELINE_RUNS = tmp

        # AC-1: the exact round-3 forge — self-authored signoff (actor == run's own executor)
        # while "executing" the run. Ship gate must REFUSE, not authorize.
        f1 = _make_run(tmp, "act-selfsign", signoff_actor=_EXECUTOR_ACTOR)
        ra.mint_key("act-selfsign")
        try:
            ra.require_release_authorization("act-selfsign", require_human_signoff=True)
            check("AC-1: self-authored signoff (round-3 forge) -> REFUSED", False)
        except ra.ReleaseAuthorizationError as e:
            check("AC-1: self-authored signoff (round-3 forge) -> REFUSED",
                  "human" in str(e).lower() or "signoff" in str(e).lower())

        # AC-1b: the self-report-field variant of the same forge — no top-level actor at all,
        # identity smuggled through data.signer_principal_uid/data.signed_by == the executor.
        # Must ALSO refuse (this is what "trust ONLY ev.actor" is specifically closing).
        f1b = _make_run(tmp, "act-selfsign-datafield", signoff_actor=_EXECUTOR_ACTOR,
                        signoff_via_data_field=True)
        ra.mint_key("act-selfsign-datafield")
        try:
            ra.require_release_authorization("act-selfsign-datafield", require_human_signoff=True)
            check("AC-1b: self-report data-field forge (no actor) -> REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("AC-1b: self-report data-field forge (no actor) -> REFUSED", True)

        # AC-2: a genuinely independent, registered signer (Mike) -> gate authorizes normally.
        # Must NOT break the legitimate path.
        f2 = _make_run(tmp, "act-legitsign", signoff_actor=_INDEPENDENT_ACTOR)
        ra.mint_key("act-legitsign")
        try:
            ra.require_release_authorization("act-legitsign", require_human_signoff=True)
            check("AC-2: independent registered signer (Mike) -> AUTHORIZED", True)
        except ra.ReleaseAuthorizationError as e:
            check("AC-2: independent registered signer (Mike) -> AUTHORIZED", False)

        # AC-3: an unregistered/bare actor -> clean REFUSAL, not a crash.
        f3 = _make_run(tmp, "act-unregistered", signoff_actor=_UNREGISTERED_ACTOR)
        ra.mint_key("act-unregistered")
        crashed = False
        refused = False
        try:
            ra.require_release_authorization("act-unregistered", require_human_signoff=True)
        except ra.ReleaseAuthorizationError:
            refused = True
        except Exception:
            crashed = True
        check("AC-3: unregistered/bare actor -> clean REFUSAL (not a crash)", refused and not crashed)

        # AC-3b: a signoff with NO actor at all (empty string) -> clean REFUSAL, not a crash.
        f3b = _make_run(tmp, "act-blankactor", signoff_actor="")
        ra.mint_key("act-blankactor")
        crashed = False
        refused = False
        try:
            ra.require_release_authorization("act-blankactor", require_human_signoff=True)
        except ra.ReleaseAuthorizationError:
            refused = True
        except Exception:
            crashed = True
        check("AC-3b: blank/empty actor -> clean REFUSAL (not a crash)", refused and not crashed)

        # Regression guard: unsigned run still refuses exactly as before the fix (baseline
        # behavior for "no signoff at all" must not have been disturbed by the port).
        f4 = _make_run(tmp, "act-nosign-at-all", signoff_actor=_INDEPENDENT_ACTOR)
        # overwrite with a run that has no human_signoff event whatsoever
        events = [json.loads(l) for l in (f4 / "run.jsonl").read_text().splitlines() if l.strip()]
        events = [e for e in events if e.get("event") != "human_signoff"]
        (f4 / "run.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
        ra.mint_key("act-nosign-at-all")
        try:
            ra.require_release_authorization("act-nosign-at-all", require_human_signoff=True)
            check("regression: no signoff at all -> still REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("regression: no signoff at all -> still REFUSED", True)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  {'✓' if ok else '✗ FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


# pytest entry points
def test_shipgate_signoff_independence():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
