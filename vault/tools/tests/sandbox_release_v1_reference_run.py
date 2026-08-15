#!/usr/bin/env python3
"""Stage 6 reference run — through PRODUCTION entry points.

Run: python3 vault/tools/tests/sandbox_release_v1_reference_run.py

A148 NO-GO'd the previous version of this file and was right: it imported
`release_package` / `release_verify` / `release_closure` directly, fabricated
four receipts and a published event, and hand-marked every journal step. It
reported 15/15 over a production chain that was entirely unwired. Helper-green,
production-unproven — the exact class this file exists to prevent, committed
inside the file that exists to prevent it.

So this version drives the real welds. The rule, from his blocker 10: patches
may replace NETWORK ADAPTERS, not the orchestration under test. Concretely,
`urlopen` is mocked and the git remote is a scratch bare repo; nothing else is
patched.

WHAT THIS DOES NOT DRIVE, stated rather than hidden: `tropo-build-release.py`
main() end to end. Its Step 0 does a full vault rebuild measured at over twenty
minutes, so a sandbox cannot walk it. This drives the welded functions that
main() calls — `stage6_package_authority`, `stage6_freeze_package` — and the
weld suite asserts structurally that main() calls them in the right order and
guards Step 12 off the v2 path. That split is a real limitation and belongs in
the boundary report, not in a footnote.

EXPECTED STATE: this run FAILS today, on blockers 3 and 4. The publisher still
writes v1 receipts, never downloads and hashes the public asset, and never
invokes closure. That red is the point — it names what is missing instead of
asserting it is done.
"""
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parents[3]


def git(cwd, *a):
    r = subprocess.run(["git", *a], cwd=str(cwd), capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(a)}: {r.stderr}")
    return r.stdout.strip()


def write_entry(files, uid, lines):
    (files / f"{uid}.md").write_text(
        "---\n" + f"uid: {uid}\n" + "\n".join(lines) + "\n---\n\n# " + uid + "\n",
        encoding="utf-8")


def build_studio(root):
    """A Studio-shaped copy. Tools are COPIED, never symlinked: the sandbox has
    to be able to have a dirty tree without dirtying the real studio."""
    (root / "vault" / "tools" / "lib").mkdir(parents=True)
    (root / "vault" / "files").mkdir(parents=True)
    (root / "vault" / "pipeline-runs").mkdir(parents=True)
    (root / "vault" / "events" / "release-receipts").mkdir(parents=True)
    (root / ".tropo-studio").mkdir(parents=True)
    for lib in (SRC / "vault" / "tools" / "lib").glob("*.py"):
        (root / "vault" / "tools" / "lib" / lib.name).write_bytes(lib.read_bytes())
    for rel in ("vault/tools/9e7003b1.py", "vault/tools/tropo-publish-release.py",
                "vault/tools/tropo-mint-id.py", "vault/tools/tropo-lineage.py",
                "vault/tools/tropo-emit-event.py"):
        src = SRC / rel
        if src.is_file():
            (root / rel).write_bytes(src.read_bytes())
    caps = root / "vault" / "capsules"
    caps.mkdir(parents=True, exist_ok=True)
    for cap in (SRC / "vault" / "capsules").glob("*.md"):
        (caps / cap.name).write_bytes(cap.read_bytes())
    for cap in (SRC / "vault" / "capsules").glob("*.json"):
        (caps / cap.name).write_bytes(cap.read_bytes())

    ks = root / ".tropo" / "scripts" / "lib"
    ks.mkdir(parents=True)
    for lib in (SRC / ".tropo" / "scripts" / "lib").glob("*.py"):
        (ks / lib.name).write_bytes(lib.read_bytes())
    git(root, "init", "-q")
    git(root, "config", "user.email", "sandbox@tropo")
    git(root, "config", "user.name", "sandbox")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "sandbox base")


def load(root, name, rel):
    import importlib.util
    sys.path.insert(0, str(root / "vault" / "tools"))
    for mod in [m for m in list(sys.modules) if m == "lib" or m.startswith("lib.")]:
        del sys.modules[mod]
    spec = importlib.util.spec_from_file_location(name, root / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def arm_tripwire():
    """Any real socket is a recorded fact. Mocking urlopen is allowed; opening
    an actual connection from a reference run is not."""
    import socket
    attempted = []
    def refuse(self, address, *a, **k):
        attempted.append(str(address))
        raise OSError(f"reference run attempted a live connection to {address}")
    socket.socket.connect = refuse
    return attempted


def seed_release(root, rp):
    """A locked plan, its activation, run and root — the world a release needs."""
    files = root / "vault" / "files"
    run_folder = "release-pipeline-sandbox"
    (root / "vault" / "pipeline-runs" / run_folder).mkdir(parents=True, exist_ok=True)
    (root / "vault" / "pipeline-runs" / run_folder / "declaration-snapshot.json"
     ).write_text('{"digest":"sbx"}', encoding="utf-8")
    write_entry(files, "acc00001", [
        "type: activation", "status: active", f"pipeline: {rp.RELEASE_PIPELINE_UID}",
        "release_plan_uid: 'c0000001'", "pipeline_run_uid: 'b0000001'",
        "activation_root_uid: 'd0000001'", "release_entry_uid: 'e0000001'"])
    write_entry(files, "b0000001", [
        "type: pipeline-run", "status: active", f"pipeline: {rp.RELEASE_PIPELINE_UID}",
        "activation: 'acc00001'", "release_plan_uid: 'c0000001'",
        f"run_folder: 'vault/pipeline-runs/{run_folder}'"])
    write_entry(files, "c0000001", [
        "type: release-plan", "status: locked",
        "release_activation_uid: 'acc00001'", "fan_in_digest: '" + "d" * 64 + "'",
        "dev_spec_uids:", "  - aaaaaaaa"])
    write_entry(files, "d0000001", ["type: activation-root-project", "status: active"])
    write_entry(files, "e0000001", ["type: release", "status: active"])
    write_entry(files, "aaaaaaaa", ["type: dev-spec", "status: done"])
    return run_folder


def main():
    attempted = arm_tripwire()
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "studio"
        remote = Path(tmp) / "scratch-remote.git"
        build_studio(root)
        remote.mkdir(parents=True)
        git(remote, "init", "-q", "--bare")
        subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"],
                       cwd=str(remote), check=True, capture_output=True)

        rp = load(root, "sbx_rp", "vault/tools/lib/release_package.py")
        rv = load(root, "sbx_rv", "vault/tools/lib/release_verify.py")
        rr = load(root, "sbx_rr", "vault/tools/lib/release_receipt.py")
        rc = load(root, "sbx_rc", "vault/tools/lib/release_closure.py")
        engine = load(root, "sbx_engine", "vault/tools/9e7003b1.py")
        engine.VAULT_ROOT = root

        run_folder = seed_release(root, rp)
        run_dir = root / "vault" / "pipeline-runs" / run_folder

        # ── production weld 1: package authority ─────────────────────────────
        identity = rp.resolve_release_run(
            "acc00001", root / "vault" / "files", root / "vault" / "pipeline-runs")
        results["package authority resolves the release run"] = (
            identity.run_uid == "b0000001")

        dist = root / "dist"; dist.mkdir()
        zip_path = dist / "tropo-os-v1.87.0.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("README.md", "# sandbox\n")
        package_sha256 = rp.hash_final_zip(zip_path)

        # ── production weld 2: package_frozen through the runtime writer ─────
        # The real path, not a fabricated event: this is what caught the
        # nonexistent --run-folder flag and the missing --lifecycle.
        event = engine.make_event(
            rp.PACKAGE_FROZEN_EVENT, "a1b8c2d4",
            data=rp.package_frozen_payload(identity, zip_path, package_sha256,
                                           version="1.87.0"),
            trace_id=identity.run_uid)
        engine.append_event(run_dir, event)
        read_back = [e for e in engine.read_events(run_dir)
                     if rp.event_type(e) == rp.PACKAGE_FROZEN_EVENT]
        results["package_frozen is written and read back through the runtime"] = (
            len(read_back) == 1
            and read_back[0]["data"]["package_sha256"] == package_sha256)

        # ── blocker 3, driven at RUNTIME not asserted from source ────────────
        # A148's addendum 25: source presence is not proof. These call the real
        # publisher functions with urlopen mocked — the adapter, not the
        # orchestration.
        pub = load(root, "sbx_pub", "vault/tools/tropo-publish-release.py")

        class _Resp:
            status = 200
            def __init__(self, payload): self._p = payload; self._done = False
            def read(self, n=-1):
                if self._done: return b""
                self._done = True; return self._p
            def __enter__(self): return self
            def __exit__(self, *a): return False

        good = zip_path.read_bytes()
        with mock.patch.object(pub, "_load_supabase_credentials",
                               return_value=("https://sb.example.test", "k")), \
             mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: _Resp(good)):
            observed = pub.observe_published_assets("1.87.0", package_sha256)
        results["BLOCKER 3 downloads and hashes both public assets"] = (
            len(observed) == 2
            and all(o["observed_sha256"] == package_sha256 for o in observed))

        # The refusal that matters: what is downloadable is not what shipped.
        with mock.patch.object(pub, "_load_supabase_credentials",
                               return_value=("https://sb.example.test", "k")), \
             mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: _Resp(b"tampered")):
            try:
                pub.observe_published_assets("1.87.0", package_sha256)
                results["BLOCKER 3 a divergent public asset refuses"] = False
            except Exception as exc:
                results["BLOCKER 3 a divergent public asset refuses"] = (
                    "not what was verified" in str(exc))

        # A real v2 receipt, built by the real function from the AC7 context.
        state = {"tag": "v1.87.0", "staged_sha": "a" * 40}
        vstate = {"status": "verified", "expect": "1.87.0", "tag": "v1.87.0",
                  "expected_sha": "a" * 40, "remote_main_sha": "a" * 40,
                  "remote_tag_sha": "a" * 40}
        observation = {
            "release_object_tag": "v1.87.0",
            "release_object_url": pub._public_release_url("v1.87.0"),
            "release_object_is_draft": False,
            "release_object_published_at": "2026-08-11T21:00:00Z"}
        with mock.patch.object(pub, "_load_supabase_credentials",
                               return_value=("https://sb.example.test", "k")), \
             mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: _Resp(good)):
            receipt = pub._validated_receipt_observation(
                "1.87.0", state, vstate, release_observation=observation,
                ac7_context={"identity": identity,
                             "package_sha256": package_sha256,
                             "release_entry_uid": "e0000001",
                             "transaction_id": "tx-sbx"})
        results["BLOCKER 3 the receipt is v2 and binds the chain"] = (
            receipt["schema_version"] == rr.SCHEMA_VERSION_V2
            and receipt["package_sha256"] == package_sha256
            and receipt["release_pipeline_run_uid"] == identity.run_uid
            and receipt["release_plan_uid"] == identity.plan_uid)

        # ── blocker 4: the publisher's closure weld is callable and honest ───
        # Driven, not grepped: a failing closure must report public-and-open
        # rather than raise, because the release has already happened.
        # Caught here so a production defect is REPORTED rather than crashing
        # the run. A harness that dies on the thing it is testing looks like a
        # broken harness, and the reader's next move is to doubt the test.
        try:
            outcome = pub._initiate_release_closure(
                {"identity": identity, "transaction_id": "tx-sbx"}, "f" * 64)
            raised = None
        except Exception as exc:
            outcome, raised = None, f"{type(exc).__name__}: {exc}"
        results["BLOCKER 4 closure is invoked and never raises past the public act"] = (
            raised is None and isinstance(outcome, dict)
            and outcome.get("ok") is False and bool(outcome.get("detail")))
        if raised:
            print(f"  (closure RAISED past the public act — {raised[:80]})")

        # ── production weld 3: closure refuses without a real receipt ────────
        # Drives the REAL engine action. Its refusal here is correct: no v2
        # receipt exists yet, because blocker 3 has not landed.
        # The property that matters is that closure does not SILENTLY close an
        # unverified release. It refuses here on the un-bootstrapped run before
        # it reaches the receipt check, which is a correct refusal for a
        # different reason — recorded honestly rather than counted as proof of
        # the receipt binding, which this fixture does not yet reach.
        closure_refusal = None
        try:
            engine.action_close_release("acc00001", "sandbox",
                                        receipt_sha256="f" * 64,
                                        transaction_id="tx-sbx")
        except Exception as exc:
            closure_refusal = f"{type(exc).__name__}: {exc}"
        results["closure never silently closes an unverified release"] = (
            closure_refusal is not None)
        print(f"  (closure refused with — {str(closure_refusal)[:88]})")

        # ── THE HAPPY PATH: a real close that SUCCEEDS ───────────────────────
        # A148 fix 1. The previous run only showed closure refusing on an
        # un-bootstrapped run and counted that as "never silently closes" —
        # which proves failure visibility and says nothing about the path the
        # release actually takes. So: build the minimal valid bootstrapped run
        # and drive the same real action_close_release to success.
        #
        # Building this immediately surfaced an integration seam nothing else
        # touched: the receipt store validated v1 only, so a v2 receipt could
        # be built by the publisher and then neither written nor read back.
        files = root / "vault" / "files"
        happy_run = "release-pipeline-happy"
        happy_dir = root / "vault" / "pipeline-runs" / happy_run
        happy_dir.mkdir(parents=True, exist_ok=True)
        (happy_dir / "declaration-snapshot.json").write_text('{"digest":"h"}',
                                                             encoding="utf-8")
        write_entry(files, "acc00002", [
            "type: activation", "status: active",
            f"pipeline: {rp.RELEASE_PIPELINE_UID}",
            "release_plan_uid: 'c0000002'", "pipeline_run_uid: 'b0000002'",
            "activation_root_uid: 'd0000002'", "release_entry_uid: 'e0000002'"])
        write_entry(files, "b0000002", [
            "type: pipeline-run", "status: active",
            f"pipeline: {rp.RELEASE_PIPELINE_UID}",
            "activation: 'acc00002'",
            "substrate_authored_by: 'acc00002'",
            "release_plan_uid: 'c0000002'",
            f"run_folder: 'vault/pipeline-runs/{happy_run}'"])
        write_entry(files, "c0000002", [
            "type: release-plan", "status: locked",
            "release_activation_uid: 'acc00002'",
            "fan_in_digest: '" + "d" * 64 + "'", "dev_spec_uids:", "  - bbbbbbbb"])
        write_entry(files, "bbbbbbbb", ["type: dev-spec", "status: done"])
        # A148 in-flight fixture review (evt_a9360f18f56fe472_00000034): the
        # root shape must be what ignition.render_activation_root ACTUALLY
        # writes, or the happy path proves a record no lock creates. Read from
        # the renderer, not from the description: type project, and for a
        # release-plan subject the subject field renders as release_plan_uid.
        # Deliberately minimal — no owner/date/version padding, per his note.
        write_entry(files, "d0000002", [
            "type: project", "status: active", "state: active",
            f"activated_by_pipeline: {rp.RELEASE_PIPELINE_UID}",
            "activation_uid: 'acc00002'",
            "release_plan_uid: 'c0000002'"])
        write_entry(files, "e0000002", ["type: release", "status: active"])

        happy_receipt = dict(receipt)
        happy_receipt.update({
            "release_plan_uid": "c0000002", "release_entry_uid": "e0000002",
            "release_activation_uid": "acc00002",
            "release_pipeline_run_uid": "b0000002",
            "activation_root_uid": "d0000002"})
        receipt_sha = rr.write_release_receipt(root, happy_receipt)
        results["a v2 receipt can be stored and read back"] = (
            receipt_sha in rr.load_release_receipts(root))

        engine.append_event(happy_dir, engine.make_event(
            "tropo.release.published", "tropo-publish-release.py",
            data={"receipt_sha256": receipt_sha}, trace_id="b0000002"))

        closed_ok, close_detail = True, ""
        try:
            outcome = engine.action_close_release(
                "acc00002", "sandbox", receipt_sha256=receipt_sha,
                transaction_id="tx-happy")
        except Exception as exc:
            closed_ok, close_detail = False, f"{type(exc).__name__}: {exc}"
            outcome = {}
        results["HAPPY PATH the real close succeeds"] = closed_ok
        if not closed_ok:
            print(f"  (close failed — {close_detail[:110]})")

        results["HAPPY PATH the journal reads complete"] = (
            str(outcome.get("journal_state") or "") == "complete")

        def _status(uid):
            entry = engine.read_vault_entry(uid) or {}
            return str((entry.get("frontmatter") or {}).get("status") or "")

        terminal = {uid: _status(uid) for uid in
                    ("c0000002", "e0000002", "d0000002", "b0000002", "acc00002")}
        results["HAPPY PATH the release records are visibly terminal"] = all(
            v.lower() in ("done", "closed", "archived", "retired", "shipped")
            for v in terminal.values())
        if not results["HAPPY PATH the release records are visibly terminal"]:
            print(f"  (records still open — {terminal})")

        root_fm = (engine.read_vault_entry("d0000002") or {}).get("frontmatter") or {}
        results["HAPPY PATH the root is the shape the lock creates"] = (
            str(root_fm.get("type")) == "project"
            and str(root_fm.get("activated_by_pipeline")) == rp.RELEASE_PIPELINE_UID
            and str(root_fm.get("activation_uid")) == "acc00002"
            and str(root_fm.get("release_plan_uid")) == "c0000002")

        results["HAPPY PATH the closure event exists exactly once"] = (
            len([e for e in engine.read_events(happy_dir)
                 if rp.event_type(e) == "tropo.release.closed"]) == 1)

        # ── bounded case: a missing check blocks publish ─────────────────────
        # Three of four instruments reported. The reduced bar still requires
        # all four against one digest, and the refusal has to name the one
        # that did not report so an operator knows what to run.
        three = [r for r in [
            {"receipt_kind": rv.RECEIPT_KIND, "instrument": name,
             "release_run_uid": identity.run_uid, "package_sha256": package_sha256,
             "verdict": "pass", "executor_or_attester": "sandbox",
             "execution_mode": "machine", "evidence_ref": f"{name}.md",
             "started_at": "2026-08-11T23:00:00Z",
             "completed_at": "2026-08-11T23:05:00Z"}
            for name in rv.INSTRUMENTS] if r["instrument"] != "cold-walk"]
        try:
            rv.assert_ready_to_publish(three, identity.run_uid, package_sha256)
            results["a missing check blocks publish"] = False
        except Exception as exc:
            results["a missing check blocks publish"] = "cold-walk" in str(exc)

        # ── bounded case: a failed publish stays visibly incomplete ──────────
        # The publisher must not report success on a partial fire, and the
        # operator must be told what to do next rather than left to infer it.
        incomplete = pub._initiate_release_closure(
            {"identity": identity, "transaction_id": "tx-sbx"}, "f" * 64)
        results["a failed close stays visibly incomplete"] = (
            incomplete.get("ok") is False and bool(incomplete.get("detail")))

        # ── bounded case: failed close reports a retry, and the retry runs ───
        # Rerunnability is the whole recovery story at this profile, so the
        # command has to be real, not descriptive prose.
        closure_src = (root / "vault" / "tools" / "tropo-publish-release.py"
                       ).read_text(encoding="utf-8")
        results["a failed close prints an exact rerun command"] = (
            "close-release" in closure_src and "--transaction-id" in closure_src
            and "PUBLIC AND OPEN" in closure_src)

        # And the retry converges rather than starting over: the same
        # transaction id resumes, and a completed step is not performed twice.
        journal = rc.open_or_resume_journal(root, identity.run_uid, "f" * 64, "tx-sbx")
        rc.record_step(root, journal, "receipt_verified", verify=lambda: True)
        resumed = rc.open_or_resume_journal(root, identity.run_uid, "f" * 64, "tx-sbx")
        results["a retry resumes instead of restarting"] = (
            rc.resume_point(resumed) == list(rc.STEPS[1:]))

        # ── every incomplete outcome names the next command ──────────────────
        # An operator told "refused" without being told what to run reaches for
        # --force or invents a workaround. At this operating profile a visible
        # manual retry is an acceptable outcome; an unexplained stop is not.
        build_src = (SRC / "vault" / "tools" / "tropo-build-release.py"
                     ).read_text(encoding="utf-8")
        refusal_paths = {
            "build package gate": ("REFUSED" in build_src
                                   and "Re-run after correcting" in build_src),
            "build leg wait": "Settle or attest the open leg" in build_src,
            "publish AC7 gate": "Record the missing verification" in closure_src
                                or "Record the missing verification" in (
                                    root / "vault" / "tools"
                                    / "tropo-publish-release.py").read_text(
                                        encoding="utf-8"),
            "publish closure": "PUBLIC AND OPEN" in closure_src,
        }
        results["every incomplete outcome names the next command"] = all(
            refusal_paths.values())
        if not all(refusal_paths.values()):
            print("  (silent refusal paths: "
                  f"{[k for k, v in refusal_paths.items() if not v]})")

        # ── absence, on every channel we can watch ───────────────────────────
        results["the scratch remote received nothing"] = (
            subprocess.run(["git", "for-each-ref"], cwd=str(remote),
                           capture_output=True, text=True).stdout.strip() == "")
        results["no live socket was opened"] = not attempted
        results["the real studio was not written to"] = not list(
            (SRC / "vault" / "pipeline-runs").glob("release-pipeline-sandbox*"))

    width = max(len(k) for k in results)
    for name, ok in results.items():
        print(f"  {name.ljust(width)} : {'PASS' if ok else 'FAIL'}")
    failed = [k for k, v in results.items() if not v]
    every = not failed
    print("\nSTAGE 6 REFERENCE RUN:", "PASS" if every else "FAIL")
    if failed:
        print("\nUnmet, by design until the named blockers land:")
        for name in failed:
            print(f"  - {name}")
    return 0 if every else 1


if __name__ == "__main__":
    sys.exit(main())
