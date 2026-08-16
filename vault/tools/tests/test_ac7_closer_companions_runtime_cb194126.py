"""AC7 runtime proof: a fresh close leaves zero unexplained archives.

A149's NO-GO (2026-08-15) on my first AC7 suite was correct: those six tests read
source slices and performed a string-removal plant. They never executed
action_close_release, never observed five terminal records, never read five
correlated events, and never ran Check 32 against the resulting world. The locked
AC asks for a fresh close and zero unexplained archives, which is a claim about a
world, not about a file's text.

This drives the real engine against the sandbox fixture the reference run already
uses, then asks Check 32 — the actual validator function that refused the v1.87
build — whether the world it produced is clean.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TOOLS = TESTS.parent
SRC = TOOLS.parents[0]

_spec = importlib.util.spec_from_file_location(
    "sandbox_ref_ac7", TESTS / "sandbox_release_v1_reference_run.py"
)
sandbox = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sandbox)

CLOSED_RECORDS = ("c0000002", "e0000002", "d0000002", "b0000002", "acc00002")


def _receipt(rr, package_sha256: str) -> dict:
    """A v2 receipt binding the happy-path chain, built explicitly.

    The reference run derives this through the publisher with network mocks. Here
    the receipt is an input to the close, not the subject, so it is constructed
    directly — fewer moving parts between the fixture and the behaviour under test.

    Contract-pinned values are read from the receipt module's own constants rather
    than retyped. Hardcoding them means this fixture drifts silently the day the
    contract changes, and a fixture that no longer matches production teaches
    nothing — which is the whole reason this file exists.
    """
    return {
        "schema_version": rr.SCHEMA_VERSION_V2,
        "receipt_kind": rr.RECEIPT_KIND,
        "version": "1.87.0",
        "tag": "v1.87.0",
        "repository": rr.REPOSITORY,
        "publisher_tool_source": rr.PUBLISHER_TOOL_SOURCE,
        "publisher_tool_uid": rr.PUBLISHER_TOOL_UID,
        "published_at": "2026-08-11T21:00:00Z",
        "public_url": "https://github.com/tropo-ai/tropo/releases/tag/v1.87.0",
        "verify_live_at": "2026-08-11T21:05:00Z",
        "remote_main_sha": "a" * 40,
        "remote_tag_sha": "a" * 40,
        "release_object_tag": "v1.87.0",
        "release_object_url": "https://github.com/tropo-ai/tropo/releases/tag/v1.87.0",
        "release_object_is_draft": False,
        "release_object_published_at": "2026-08-11T21:00:00Z",
        "package_sha256": package_sha256,
        "fan_in_digest": "d" * 64,
        "release_plan_uid": "c0000002",
        "release_entry_uid": "e0000002",
        "release_activation_uid": "acc00002",
        "release_pipeline_run_uid": "b0000002",
        "activation_root_uid": "d0000002",
        # The contract requires at least one downloaded-asset observation whose
        # digest equals package_sha256: "a receipt that records no observation is
        # recording an upload, not a verification."
        "public_asset_observations": [{
            "url": "https://github.com/tropo-ai/tropo/releases/download/"
                   "v1.87.0/tropo-os-v1.87.0.zip",
            "observed_sha256": package_sha256,
        }],
        "transaction_id": "tx-ac7",
    }


class CloserCompanionsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "studio"
        self.root.mkdir()
        sandbox.build_studio(self.root)
        # A149's correction: build_studio omits tropo-rebuild-events-sqlite.py, so
        # every close in the sandbox logged a projection-rebuild failure and the
        # fresh-projection leg was never exercised. Canonical JSONL still let Check
        # 32 pass, which is exactly the shape of a leg that looks covered and is not.
        # Its lib closure already ships via build_studio's lib/*.py copy.
        rebuild = SRC / "tools" / "tropo-rebuild-events-sqlite.py"
        if rebuild.is_file():
            (self.root / "vault" / "tools" / rebuild.name).write_bytes(rebuild.read_bytes())
        self._saved_path = list(sys.path)

        self.rp = sandbox.load(self.root, "ac7_rp", "vault/tools/lib/release_package.py")
        self.rr = sandbox.load(self.root, "ac7_rr", "vault/tools/lib/release_receipt.py")
        self.engine = sandbox.load(self.root, "ac7_engine", "vault/tools/9e7003b1.py")
        self.engine.VAULT_ROOT = self.root

        files = self.root / "vault" / "files"
        run_folder = "release-pipeline-happy"
        self.run_dir = self.root / "vault" / "pipeline-runs" / run_folder
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "declaration-snapshot.json").write_text('{"digest":"h"}')

        w = sandbox.write_entry
        pipeline = self.rp.RELEASE_PIPELINE_UID
        w(files, "acc00002", [
            "type: activation", "status: active", f"pipeline: {pipeline}",
            "release_plan_uid: 'c0000002'", "pipeline_run_uid: 'b0000002'",
            "activation_root_uid: 'd0000002'", "release_entry_uid: 'e0000002'"])
        w(files, "b0000002", [
            "type: pipeline-run", "status: active", f"pipeline: {pipeline}",
            "activation: 'acc00002'", "substrate_authored_by: 'acc00002'",
            "release_plan_uid: 'c0000002'",
            f"run_folder: 'vault/pipeline-runs/{run_folder}'"])
        w(files, "c0000002", [
            "type: release-plan", "status: locked",
            "release_activation_uid: 'acc00002'",
            "fan_in_digest: '" + "d" * 64 + "'", "dev_spec_uids:", "  - bbbbbbbb"])
        w(files, "bbbbbbbb", ["type: dev-spec", "status: done"])
        w(files, "d0000002", [
            "type: project", "status: active", "state: active",
            f"activated_by_pipeline: {pipeline}", "activation_uid: 'acc00002'",
            "release_plan_uid: 'c0000002'"])
        w(files, "e0000002", ["type: release", "status: active"])

        self.receipt_sha = self.rr.write_release_receipt(self.root, _receipt(self.rr, "f" * 64))
        self.engine.append_event(self.run_dir, self.engine.make_event(
            "tropo.release.published", "tropo-publish-release.py",
            data={"receipt_sha256": self.receipt_sha}, trace_id="b0000002"))

    def tearDown(self):
        sys.path[:] = self._saved_path
        self._tmp.cleanup()

    # ---- helpers -------------------------------------------------------

    def _close(self, transaction_id="tx-ac7"):
        return self.engine.action_close_release(
            "acc00002", "sandbox", receipt_sha256=self.receipt_sha,
            transaction_id=transaction_id)

    def _status(self, uid):
        entry = self.engine.read_vault_entry(uid) or {}
        return str((entry.get("frontmatter") or {}).get("status") or "").lower()

    def _correlated_closes(self):
        """uid -> count of tropo.cycle.closed events correlated to it.

        Read from the canonical event union the way Check 32 reads it, not from a
        return value the closer hands back about itself.
        """
        import json
        counts = {uid: 0 for uid in CLOSED_RECORDS}
        events_dir = self.root / "vault" / "events"
        for path in list(events_dir.rglob("*.jsonl")):
            if "receipts" in path.parts:
                continue
            for line in path.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("type") != "tropo.cycle.closed":
                    continue
                cid = str(ev.get("correlationid") or "")
                if cid in counts:
                    counts[cid] += 1
        return counts

    # ---- the AC --------------------------------------------------------

    def test_a_fresh_close_moves_all_five_records_terminal(self):
        self._close()
        terminal = {uid: self._status(uid) for uid in CLOSED_RECORDS}
        for uid, status in terminal.items():
            self.assertIn(
                status, ("done", "closed", "archived", "retired", "shipped"),
                f"{uid} did not reach a terminal status: {terminal}",
            )

    def test_every_closed_record_has_exactly_one_correlated_event(self):
        """The AC, executed: five records archived, five correlated events."""
        self._close()
        counts = self._correlated_closes()
        missing = [uid for uid, n in counts.items() if n == 0]
        self.assertEqual(
            missing, [],
            f"records archived with no correlated tropo.cycle.closed event: {missing} "
            f"(this is the fifteen-unexplained-archives class)",
        )
        duplicated = {uid: n for uid, n in counts.items() if n > 1}
        self.assertEqual(duplicated, {}, f"duplicate close events: {duplicated}")

    def test_a_rerun_produces_no_duplicate_events(self):
        """Idempotence, run rather than reasoned about."""
        self._close()
        first = self._correlated_closes()
        try:
            self._close(transaction_id="tx-ac7-again")
        except Exception:
            # A second close may legitimately refuse; what must not happen is a
            # second event for a record that already closed.
            pass
        second = self._correlated_closes()
        self.assertEqual(
            first, second,
            f"a rerun changed the event counts: {first} -> {second}",
        )

    def test_check32_finds_zero_unexplained_archives_for_these_records(self):
        """Ask the instrument that actually refused the v1.87 build."""
        self._close()
        spec = importlib.util.spec_from_file_location(
            "ac7_tropo_validate", SRC / "tools" / "tropo-validate.py"
        )
        tv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tv)

        findings, _checked, _defects = tv.check_completion_recording(self.root)
        offending = [f for f in findings
                     if any(uid in f for uid in CLOSED_RECORDS) and "[FAIL]" in f]
        self.assertEqual(
            offending, [],
            "Check 32 reports unexplained terminal records from a fresh close:\n  "
            + "\n  ".join(offending),
        )

    def _close_events(self):
        """Full event objects for the five correlated closes, not just counts."""
        import json
        found = []
        events_dir = self.root / "vault" / "events"
        for path in list(events_dir.rglob("*.jsonl")):
            if "receipts" in path.parts:
                continue
            for line in path.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("type") == "tropo.cycle.closed" and \
                        str(ev.get("correlationid") or "") in CLOSED_RECORDS:
                    found.append(ev)
        return found

    def test_every_close_event_declares_the_tools_own_provenance(self):
        """A correlated event whose provenance lies is not acceptable completion
        substrate (A149). 123e12e7 is "Talos — Agent Root Project"; this tool's
        declared uid is 9e7003b1."""
        self._close()
        events = self._close_events()
        self.assertEqual(len(events), len(CLOSED_RECORDS), "expected one close per record")
        for ev in events:
            self.assertEqual(ev.get("source"), "/tools/pipeline-runtime",
                             f"wrong source on {ev.get('correlationid')}")
            self.assertEqual(
                ev.get("source_uid"), "9e7003b1",
                f"{ev.get('correlationid')} claims source_uid {ev.get('source_uid')!r}; "
                f"123e12e7 is an agent-root project, not this tool",
            )

    def test_provenance_reds_when_the_agent_root_uid_is_restored(self):
        """Negative plant A149 specified."""
        self.engine.TOOL_UID = "123e12e7"
        try:
            self._close()
            events = self._close_events()
        finally:
            self.engine.TOOL_UID = "9e7003b1"
        self.assertTrue(events, "no close events emitted under the plant")
        self.assertTrue(
            any(ev.get("source_uid") == "123e12e7" for ev in events),
            "restoring the agent-root uid must reintroduce the false provenance; if "
            "it does not, the assertion above is not measuring provenance",
        )

    def test_a_fresh_close_logs_no_projection_rebuild_failure(self):
        """The sandbox now carries tropo-rebuild-events-sqlite.py, so the
        derived-projection leg actually runs instead of warning past itself."""
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self._close()
        self.assertNotIn("projection", err.getvalue().lower(),
                         f"projection warning during a fresh close: {err.getvalue()[:300]}")

    def test_the_derived_projection_carries_the_five_events(self):
        """Assert the projection content when the fixture exposes it (A149: 'if')."""
        import sqlite3
        self._close()
        db = self.root / "vault" / "events" / "00-events-index.sqlite"
        if not db.is_file():
            self.skipTest("fixture exposes no derived projection")
        con = sqlite3.connect(db)
        try:
            rows = con.execute(
                "SELECT correlationid FROM events WHERE type = 'tropo.cycle.closed'"
            ).fetchall()
        finally:
            con.close()
        got = {r[0] for r in rows}
        missing = [uid for uid in CLOSED_RECORDS if uid not in got]
        self.assertEqual(missing, [], f"projection missing closes for {missing}")

    def test_removing_the_per_record_emit_reopens_the_class(self):
        """Negative plant on the PRODUCTION path, not on source text.

        Neuter the emitter the close loop calls and re-run a real close: four
        companions go terminal with no correlated event, which is exactly the
        state the v1.87 build gate refused.
        """
        self.engine._emit_cycle_closed = lambda *a, **k: False
        self._close()
        counts = self._correlated_closes()
        missing = [uid for uid, n in counts.items() if n == 0]
        self.assertNotEqual(
            missing, [],
            "with the emitter neutered the silent-archive class must return; if it "
            "does not, this test is not measuring the weld",
        )


if __name__ == "__main__":
    unittest.main()
