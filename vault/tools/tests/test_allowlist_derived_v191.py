#!/usr/bin/env python3
"""v1.91 S2 AC5 (3fb41c99) — the post-mint allowlist is DERIVED, not hand-kept.

A legitimate recovery act must never read as tampering, and a successful build's
own event must never block the next build. Measured against the real defect:
v1.90 hit this three times -- package_superseded read as tampering, and
package_frozen from a successful build blocked the following build's key --
because _post_mint_event_allowed's type check only recognized
_ENGINE_EVENT_TYPES, a hand-kept frozenset that never named any tropo.release.*
event at all.

The fix: the same type check also accepts anything declared in
release_events.RELEASE_EVENTS -- the one finite table AC1/AC2 already hold
every release writer to. Adding a new declared event (as S2's own AC1 just
did, four times, in prior commits this cycle) makes it allowed with zero
edits to this function.

Self-running (python3 test_allowlist_derived_v191.py) and pytest-compatible,
matching test_release_authorization.py's own gauntlet style -- this exercises
the same module and belongs beside it.
"""
import sys
import json
import tempfile
import shutil
from pathlib import Path

_TROPO_SCRIPTS = Path(__file__).resolve().parents[3] / ".tropo" / "scripts"
sys.path.insert(0, str(_TROPO_SCRIPTS))
from lib import release_authorization as ra  # noqa: E402

FREEZE_STEP = "7de2c49f"  # release-freeze-verified-package (real WorkflowNode)


def _make_run(root: Path, activation_uid: str, *, cascade=True) -> Path:
    """Same shape as test_release_authorization.py's own fixture builder."""
    folder = root / f"dev-pipeline-{activation_uid}-2026-08-23"
    folder.mkdir(parents=True, exist_ok=True)
    events = [{"event": "run_created", "trace_id": activation_uid, "data": {"pipeline": "cd1fcd25"}}]
    if cascade:
        events.append({"event": "step_completed", "actor": "argus", "step": ra.TEST_TRIGGER_STEP,
                       "trace_id": activation_uid, "data": {}})
        events.append({"event": "verification_receipt", "step": ra.TEST_TRIGGER_STEP,
                       "trace_id": activation_uid, "data": {"verdict": "pass"}})
        events.append({"event": "step_completed", "actor": "argus", "step": ra.DOC_TRIGGER_STEP,
                       "trace_id": activation_uid, "data": {}})
        events.append({"event": "verification_receipt", "step": ra.DOC_TRIGGER_STEP,
                       "trace_id": activation_uid, "data": {"verdict": "pass"}})
    (folder / "run.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return folder


def main() -> int:
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    tmp = Path(tempfile.mkdtemp(prefix="allowlist-derived-"))
    try:
        ra.PIPELINE_RUNS = tmp

        # 1. THE v1.90 DEFECT, REPRODUCED THEN PROVEN FIXED: mint, then append
        # a real tropo.release.package_superseded row (no step -- run-level
        # principal fact) and confirm it does NOT read as tampering.
        folder = _make_run(tmp, "act-superseded")
        ra.mint_key("act-superseded")
        with (folder / "run.jsonl").open("a") as f:
            f.write(json.dumps({
                "event": "tropo.release.package_superseded", "step": None,
                "trace_id": "act-superseded",
                "data": {"release_run_uid": "act-superseded", "old_package_sha256": "a" * 64,
                         "reason": "changelog promoted after freeze"},
            }) + "\n")
        try:
            ra.require_release_authorization("act-superseded")
            check("package_superseded post-mint -> AUTHORIZED (was tampering in v1.90)", True)
        except ra.ReleaseAuthorizationError:
            check("package_superseded post-mint -> AUTHORIZED (was tampering in v1.90)", False)

        # 2. package_frozen FROM A SUCCESSFUL BUILD DOES NOT BLOCK THE KEY.
        # Carries a real step reference (the freeze WorkflowNode), so this also
        # proves Shape 3's step-resolution composes correctly with a declared
        # release event, not just the no-step principal-input ones.
        folder = _make_run(tmp, "act-frozen")
        ra.mint_key("act-frozen")
        with (folder / "run.jsonl").open("a") as f:
            f.write(json.dumps({
                "event": "tropo.release.package_frozen", "step": FREEZE_STEP,
                "trace_id": "act-frozen",
                "data": {"pipeline_run_uid": "act-frozen", "package_sha256": "b" * 64,
                         "receipt_set_sha256": "c" * 64},
            }) + "\n")
        try:
            ra.require_release_authorization("act-frozen")
            check("package_frozen (real step ref) post-mint -> AUTHORIZED", True)
        except ra.ReleaseAuthorizationError:
            check("package_frozen (real step ref) post-mint -> AUTHORIZED", False)

        # 2b. THE v1.93 DEFECT, REPRODUCED THEN PROVEN FIXED (argus-a162,
        # 2026-08-29): a legitimate reverify-step reopen of a VERIFIED/SKIPPED
        # instrument step must not read as tampering -- same class as
        # step_redeclared above, found on v1.93's own real stage attempt, the
        # first release run to ever reach this gate having used reverify-step.
        folder = _make_run(tmp, "act-reverified")
        ra.mint_key("act-reverified")
        with (folder / "run.jsonl").open("a") as f:
            f.write(json.dumps({
                "event": "step_reverify_opened", "step": FREEZE_STEP,
                "trace_id": "act-reverified",
                "data": {"step_uid": FREEZE_STEP, "instrument": "full-validator",
                         "previous_status": "verified", "superseded_candidates": [],
                         "active_candidate_sha256": "e" * 64},
            }) + "\n")
        try:
            ra.require_release_authorization("act-reverified")
            check("step_reverify_opened (real step ref) post-mint -> AUTHORIZED", True)
        except ra.ReleaseAuthorizationError:
            check("step_reverify_opened (real step ref) post-mint -> AUTHORIZED", False)

        # 3. DERIVED, NOT RE-ASSERTED: tropo.release.scope_locked was declared
        # in RELEASE_EVENTS by an EARLIER commit this cycle (3cddb767f) with NO
        # corresponding edit to this function. If it authorizes with zero
        # changes here, the derivation is real, not a second hand-kept copy.
        folder = _make_run(tmp, "act-scopelocked")
        ra.mint_key("act-scopelocked")
        with (folder / "run.jsonl").open("a") as f:
            f.write(json.dumps({
                "event": "tropo.release.scope_locked", "step": None,
                "trace_id": "act-scopelocked",
                "data": {"saga_id": "release:act-scopelocked", "release_plan_uid": "b1a00001",
                         "activation_uid": "act-scopelocked", "activation_root_uid": "11111111",
                         "pipeline_run_uid": "act-scopelocked", "release_entry_uid": "22222222"},
            }) + "\n")
        try:
            ra.require_release_authorization("act-scopelocked")
            check("scope_locked (declared 3cddb767f, no allowlist edit) -> AUTHORIZED", True)
        except ra.ReleaseAuthorizationError:
            check("scope_locked (declared 3cddb767f, no allowlist edit) -> AUTHORIZED", False)

        # 4. FAIL-CLOSED PRESERVED: an event in neither _ENGINE_EVENT_TYPES nor
        # RELEASE_EVENTS still refuses. Widening the allowlist to the declared
        # table must not widen it to "anything."
        folder = _make_run(tmp, "act-undeclared")
        ra.mint_key("act-undeclared")
        with (folder / "run.jsonl").open("a") as f:
            f.write(json.dumps({
                "event": "tropo.release.not_a_real_event", "step": None,
                "trace_id": "act-undeclared", "data": {},
            }) + "\n")
        try:
            ra.require_release_authorization("act-undeclared")
            check("undeclared event type post-mint -> still REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("undeclared event type post-mint -> still REFUSED", True)

        # 5. A DECLARED RELEASE EVENT WITH A FABRICATED STEP REFERENCE STILL
        # REFUSES: the widening accepts the TYPE, not an unresolvable step.
        folder = _make_run(tmp, "act-fakestep")
        ra.mint_key("act-fakestep")
        with (folder / "run.jsonl").open("a") as f:
            f.write(json.dumps({
                "event": "tropo.release.package_frozen", "step": "deadbeef",
                "trace_id": "act-fakestep",
                "data": {"pipeline_run_uid": "act-fakestep", "package_sha256": "d" * 64},
            }) + "\n")
        try:
            ra.require_release_authorization("act-fakestep")
            check("package_frozen with a fabricated step ref -> still REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("package_frozen with a fabricated step ref -> still REFUSED", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  {'✓' if ok else '✗ FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


# pytest entry point
def test_allowlist_derived_from_release_events():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
