#!/usr/bin/env python3
"""Gauntlet for the Pipeline Activation Key (dev-spec 2ffdd9d6 AC-6).

Proves: a legit run+key passes; a forged/absent/tampered key fails; ship without the
human key skips upload. Enforcement code gets an adversarial pass — a forged key MUST NOT
defeat the gate. Self-running (python3 test_release_authorization.py) and pytest-compatible.
"""
import sys, json, tempfile, shutil
from pathlib import Path

_TROPO_SCRIPTS = Path(__file__).resolve().parents[3] / ".tropo" / "scripts"
sys.path.insert(0, str(_TROPO_SCRIPTS))
from lib import release_authorization as ra  # noqa: E402


def _make_run(root: Path, activation_uid="act-legit", *, cascade=True, signoff=False, progressed=True,
              signoff_actor="mike-maziarz"):
    """Create a synthetic run folder with a run.jsonl in REAL runtime shapes (verified against
    vault/pipeline-runs/ output: trace_id links the run; verdicts live in data; the cascade is
    a step_completed for each trigger-step UID).

    5864c0b6 fix: human_signoff independence is keyed off the engine-stamped `actor` field
    (never a self-reported data field), so step_completed events now carry a real executor
    actor ("argus", a registered agent principal — matches vault/pipeline-runs/ shape) and the
    signoff defaults to "mike-maziarz" (a registered, independent human principal) so the
    legitimate-signoff fixture actually exercises a real registered-and-independent pass
    rather than accidentally relying on an unregistered-actor no-op."""
    folder = root / f"dev-pipeline-{activation_uid}-2026-06-17"
    folder.mkdir(parents=True, exist_ok=True)
    events = [{"event": "run_created", "trace_id": activation_uid, "data": {"pipeline": "cd1fcd25"}}]
    if progressed:
        events.append({"event": "step_completed", "actor": "argus", "step": "71a7d016", "trace_id": activation_uid, "data": {}})
    if cascade:
        # cascade fired = step_completed for both trigger-step UIDs (doc 0cf86ea5 / test 4f64ec3c)
        events.append({"event": "step_completed", "actor": "argus", "step": ra.TEST_TRIGGER_STEP, "trace_id": activation_uid, "data": {}})
        events.append({"event": "verification_receipt", "step": ra.TEST_TRIGGER_STEP, "trace_id": activation_uid, "data": {"verdict": "pass"}})
        events.append({"event": "step_completed", "actor": "argus", "step": ra.DOC_TRIGGER_STEP, "trace_id": activation_uid, "data": {}})
        events.append({"event": "verification_receipt", "step": ra.DOC_TRIGGER_STEP, "trace_id": activation_uid, "data": {"verdict": "pass"}})
    if signoff:
        events.append({"event": "human_signoff", "actor": signoff_actor, "trace_id": activation_uid, "data": {"verdict": "accepted"}})
    (folder / "run.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return folder


def _run(tmp, fn):
    ra.PIPELINE_RUNS = tmp  # redirect the gate at the test sandbox
    return fn()


def main():
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    tmp = Path(tempfile.mkdtemp(prefix="key-gauntlet-"))
    try:
        ra.PIPELINE_RUNS = tmp

        # 1. LEGIT: cascade present + minted key → require passes
        _make_run(tmp, "act-legit", cascade=True)
        key = ra.mint_key("act-legit")
        try:
            ra.require_release_authorization("act-legit")
            check("legit run + minted key → AUTHORIZED", True)
        except ra.ReleaseAuthorizationError:
            check("legit run + minted key → AUTHORIZED", False)

        # 2. FORGED: touch a garbage key → must REFUSE
        forged = tmp / "dev-pipeline-act-forge-2026-06-17"
        _make_run(tmp, "act-forge", cascade=True)
        (forged / ra.KEY_FILENAME).write_text(json.dumps(
            {"activation_uid": "act-forge", "fingerprint": "deadbeef" * 8, "minted_by": "attacker"}))
        try:
            ra.require_release_authorization("act-forge"); check("forged key (wrong fingerprint) → REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("forged key (wrong fingerprint) → REFUSED", True)

        # 3. ABSENT: no key file → must REFUSE
        _make_run(tmp, "act-nokey", cascade=True)
        try:
            ra.require_release_authorization("act-nokey"); check("no key file → REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("no key file → REFUSED", True)

        # 4. NO ACTIVATION → must REFUSE
        try:
            ra.require_release_authorization(None); check("no activation-uid → REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("no activation-uid → REFUSED", True)

        # 5. NO CASCADE: run without doc/test triggers → cannot mint (protocol not followed)
        _make_run(tmp, "act-nocascade", cascade=False)
        try:
            ra.mint_key("act-nocascade"); check("no doc/test cascade → mint REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("no doc/test cascade → mint REFUSED", True)

        # 6. TAMPERED: mint, then append work events (run state diverges) → fingerprint mismatch
        tfolder = _make_run(tmp, "act-tamper", cascade=True)
        ra.mint_key("act-tamper")
        with (tfolder / "run.jsonl").open("a") as f:
            f.write(json.dumps({"event": "step_completed", "step": "snuck-in", "verdict": "pass"}) + "\n")
        try:
            ra.require_release_authorization("act-tamper"); check("tampered run after mint → REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("tampered run after mint → REFUSED", True)

        # 7. PRODUCE STEP: a mint before its completion becomes stale; the
        # runtime's post-completion remint restores a valid durable key.
        pfolder = _make_run(tmp, "act-produce", cascade=True)
        ra.mint_key("act-produce")
        with (pfolder / "run.jsonl").open("a") as f:
            f.write(json.dumps({
                "event": "step_completed",
                "step": "8654900a",
                "trace_id": "act-produce",
                "data": {"natural_verdict": "pass"},
            }) + "\n")
        ra.mint_key("act-produce")
        try:
            ra.require_release_authorization("act-produce")
            check("post-produce remint → AUTHORIZED", True)
        except ra.ReleaseAuthorizationError:
            check("post-produce remint → AUTHORIZED", False)

        # 8. SHIP without human signoff → REFUSED; with signoff → AUTHORIZED
        _make_run(tmp, "act-nosign", cascade=True)
        ra.mint_key("act-nosign")
        try:
            ra.require_release_authorization("act-nosign", require_human_signoff=True)
            check("ship without human signoff → REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("ship without human signoff → REFUSED", True)

        _make_run(tmp, "act-signed", cascade=True, signoff=True)
        ra.mint_key("act-signed")
        try:
            ra.require_release_authorization("act-signed", require_human_signoff=True)
            check("ship WITH human signoff → AUTHORIZED", True)
        except ra.ReleaseAuthorizationError:
            check("ship WITH human signoff → AUTHORIZED", False)

        # 9. DOC-LESS DEV-SPEC: legitimately-authorized skip of the doc trigger (a test-only
        # dev-spec, e.g. mount-gate/409ef1cc's class) → mint MUST succeed. d2f8a91c fix.
        def _make_skip_run(root, activation_uid, *, linked=True, disposition="skip_with_authorization", authorized_by="mike-maziarz"):
            folder = root / f"dev-pipeline-{activation_uid}-2026-06-17"
            folder.mkdir(parents=True, exist_ok=True)
            events = [
                {"event": "run_created", "trace_id": activation_uid, "data": {"pipeline": "cd1fcd25"}},
                {"event": "step_completed", "actor": "argus", "step": "71a7d016", "trace_id": activation_uid, "data": {}},
                {"event": "step_completed", "actor": "argus", "step": ra.TEST_TRIGGER_STEP, "trace_id": activation_uid, "data": {}},
                {"event": "verification_receipt", "step": ra.TEST_TRIGGER_STEP, "trace_id": activation_uid, "data": {"verdict": "pass"}},
                {"event": "skip_request", "actor": "talos", "step": ra.DOC_TRIGGER_STEP, "trace_id": activation_uid, "data": {"reason": "no doc-class deliverable"}},
                {"event": "skip_authorization", "actor": "talos", "step": ra.DOC_TRIGGER_STEP, "trace_id": activation_uid, "span_id": "auth-span-1", "data": ({"authorized_by": authorized_by} if authorized_by else {})},
                {"event": "step_skipped", "actor": "talos", "step": ra.DOC_TRIGGER_STEP, "trace_id": activation_uid, "data": {"disposition": disposition, "skip_authorization_span_id": ("auth-span-1" if linked else "auth-span-NONEXISTENT")}},
            ]
            (folder / "run.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
            return folder

        _make_skip_run(tmp, "act-docskip-legit")
        try:
            ra.mint_key("act-docskip-legit")
            ra.require_release_authorization("act-docskip-legit")
            check("doc-less dev-spec, legit authorized skip → mint AUTHORIZED", True)
        except ra.ReleaseAuthorizationError:
            check("doc-less dev-spec, legit authorized skip → mint AUTHORIZED", False)

        # 10. ADVERSARIAL: step_skipped present but skip_authorization_span_id points nowhere
        # (forged/dangling skip claim) → mint MUST still REFUSE.
        _make_skip_run(tmp, "act-docskip-unlinked", linked=False)
        try:
            ra.mint_key("act-docskip-unlinked")
            check("forged/unlinked skip (dangling span_id) → mint REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("forged/unlinked skip (dangling span_id) → mint REFUSED", True)

        # 11. ADVERSARIAL: skip_authorization exists but authorized_by is empty (never actually
        # resolved to a principal) → mint MUST still REFUSE.
        _make_skip_run(tmp, "act-docskip-noauth", authorized_by=None)
        try:
            ra.mint_key("act-docskip-noauth")
            check("skip_authorization with empty authorized_by → mint REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("skip_authorization with empty authorized_by → mint REFUSED", True)

        # 12. ADVERSARIAL: step_skipped with a disposition other than skip_with_authorization
        # (e.g. an unauthorized/auto skip) → mint MUST still REFUSE.
        _make_skip_run(tmp, "act-docskip-baddisposition", disposition="skip_unauthorized")
        try:
            ra.mint_key("act-docskip-baddisposition")
            check("step_skipped with non-authorized disposition → mint REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("step_skipped with non-authorized disposition → mint REFUSED", True)

        # ── attested_build_authorization gauntlet (argus-a129-attested-build-gate spec) ──
        avault = tmp / "avault"
        vfiles = avault / "vault" / "files"
        vfiles.mkdir(parents=True, exist_ok=True)

        def _write_fm(uid, fm: dict):
            body = "---\n" + "\n".join(f"{k}: {json.dumps(v)}" for k, v in fm.items()) + "\n---\n\n# stub\n"
            (vfiles / f"{uid}.md").write_text(body)

        def _hex_uid(*parts):
            import hashlib
            return hashlib.sha256("|".join(parts).encode()).hexdigest()[:8]

        def _seed_attested_release(version, *, release_status="shipped", signed_by="mike-maziarz",
                                    released_by="vela-v64", close_method="attested-manual",
                                    decision_status="accepted", decision_signed_by="mike-maziarz",
                                    cite_decision=True):
            rel_uid = _hex_uid("rel", version)
            act_uid = _hex_uid("act", version)
            spec_uid = _hex_uid("spec", version)
            dec_uid = _hex_uid("dec", version)
            _write_fm(rel_uid, {
                "uid": rel_uid, "type": "release", "release_version": f"v{version}",
                "status": release_status, "signed_by": signed_by, "released_by": released_by,
                "derived_from": [spec_uid],
            })
            closure_reason = (f"attested per decision {dec_uid}" if cite_decision
                               else "attested, no decision cited")
            _write_fm(act_uid, {
                "uid": act_uid, "type": "activation", "dev_spec_uid": spec_uid,
                "close_method": close_method, "closure_reason": closure_reason,
            })
            _write_fm(dec_uid, {"uid": dec_uid, "type": "note", "status": decision_status,
                                 "signed_by": decision_signed_by})
            return rel_uid

        # 13a. LEGIT: shipped+signed release, attested-manual activation, accepted+signed
        # decision → produce AUTHORIZED.
        _seed_attested_release("9.1.0")
        try:
            r = ra.attested_build_authorization("9.1.0", vault_root=avault)
            check("attested-build: legit chain → AUTHORIZED", r["method"] == "attested-build")
        except ra.ReleaseAuthorizationError:
            check("attested-build: legit chain → AUTHORIZED", False)

        # 13b. NO RELEASE ENTRY for the version → REFUSED.
        try:
            ra.attested_build_authorization("9.2.0", vault_root=avault)
            check("attested-build: no release entry → REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("attested-build: no release entry → REFUSED", True)

        # 13c. status != shipped → REFUSED.
        _seed_attested_release("9.3.0", release_status="draft")
        try:
            ra.attested_build_authorization("9.3.0", vault_root=avault)
            check("attested-build: status!=shipped → REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("attested-build: status!=shipped → REFUSED", True)

        # 13d. signed_by missing/empty → REFUSED.
        _seed_attested_release("9.4.0", signed_by="")
        try:
            ra.attested_build_authorization("9.4.0", vault_root=avault)
            check("attested-build: signed_by empty → REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("attested-build: signed_by empty → REFUSED", True)

        # 13e. Activation NOT attested-manual (normal release that merely lost its key) →
        # REFUSED — this path must not become a generic bypass for any release.
        _seed_attested_release("9.5.0", close_method="engine-complete-workflow")
        try:
            ra.attested_build_authorization("9.5.0", vault_root=avault)
            check("attested-build: close_method!=attested-manual → REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("attested-build: close_method!=attested-manual → REFUSED", True)

        # 13e2. Decision cited is not accepted/signed → REFUSED.
        _seed_attested_release("9.6.0", decision_status="draft")
        try:
            ra.attested_build_authorization("9.6.0", vault_root=avault)
            check("attested-build: cited decision not accepted → REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("attested-build: cited decision not accepted → REFUSED", True)

        # 13f. attested-build authorization MUST NOT satisfy the outward ship/human-signoff
        # gate — require_release_authorization(require_human_signoff=True) is a completely
        # separate function this never touches. Prove it: a run with no human_signoff still
        # refuses the ship gate even though attested-build succeeded for the same version.
        _seed_attested_release("9.7.0")
        ra.attested_build_authorization("9.7.0", vault_root=avault)  # succeeds — produce gate only
        _make_run(tmp, "act-shipgate-noattest", cascade=True)  # no signoff
        try:
            ra.require_release_authorization("act-shipgate-noattest", require_human_signoff=True)
            check("attested-build does NOT satisfy outward ship gate → still REFUSED", False)
        except ra.ReleaseAuthorizationError:
            check("attested-build does NOT satisfy outward ship gate → still REFUSED", True)

        # 14. COMPOSITION: attested-build (produce-gate, version-keyed) and the pipeline-key
        # path with an authorized skip (produce-gate, activation-keyed) are independent — one
        # succeeding for a given version does not depend on or interfere with the other.
        _make_skip_run(tmp, "act-compose-pipeline")
        pipeline_ok = False
        try:
            ra.mint_key("act-compose-pipeline")
            ra.require_release_authorization("act-compose-pipeline")
            pipeline_ok = True
        except ra.ReleaseAuthorizationError:
            pipeline_ok = False
        attested_ok = False
        try:
            ra.attested_build_authorization("9.7.0", vault_root=avault)  # already-seeded above
            attested_ok = True
        except ra.ReleaseAuthorizationError:
            attested_ok = False
        check("composition: authorized-skip pipeline-key AND attested-build both hold independently",
              pipeline_ok and attested_ok)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  {'✓' if ok else '✗ FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


# pytest entry points
def test_pipeline_activation_key_gauntlet():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
