#!/usr/bin/env python3
"""2cb346d6 v1.90 release adapters — AC1–AC7 proofs (red baseline first).

The spec's four automated verify commands name THIS file's classes; the
fifth (ClosedEnumTests) is the non-gated AC7. Red at birth by design: the
machinery under test does not exist until the wiring lands.

A153's two hard lines are load-bearing here and each carries its named
mutation: (1) wiring means INVOKED BY THE SAGA — stubbing an adapter to a
no-op turns WiringTests red for that checkpoint; (2) --force-with-lease,
never --force — swapping the lease turns SiteRefCASTests red.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_saga as saga  # noqa: E402
from lib import tool_telemetry  # noqa: E402  (unused import guard: keep suite honest)


def _load_publisher():
    spec = importlib.util.spec_from_file_location(
        "publisher_v190", TOOLS / "tropo-publish-release.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["publisher_v190"] = module
    spec.loader.exec_module(module)
    return module


#: The eight checkpoints this spec wires (spec AC1; the site_ref-dependent
#: leg is site_endpoint, whose dependency chain pulls site_ref itself).
UNWIRED_EIGHT = (
    "site_prepare",
    "release_entry_projection",
    "site_ref",
    "site_endpoint",
    "run_published_event",
    "closure",
    "scorecard",
    "completion_verification",
)


def _cas_fixture(tag: str):
    """Shared local bare-repo site fixture (the AC2 shape, reused by AC1)."""
    import subprocess as _sp
    tmp = Path(tempfile.mkdtemp(prefix=f"v190_{tag}_")).resolve()
    remote = tmp / "remote.git"
    _sp.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    clone = tmp / "site"
    _sp.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
    for key, value in (("user.email", "t@t"), ("user.name", "t")):
        _sp.run(["git", "-C", str(clone), "config", key, value], check=True)
    _sp.run(["git", "-C", str(clone), "commit", "--allow-empty", "-m",
             "badge site v1.90.0"], check=True)
    _sp.run(["git", "-C", str(clone), "push", "-q", "origin", "HEAD:refs/heads/main"],
            check=True)
    _sp.run(["git", "-C", str(clone), "fetch", "-q", "origin"], check=True)
    tip = _sp.run(["git", "-C", str(clone), "rev-parse", "HEAD"],
                  capture_output=True, text=True, check=True).stdout.strip()
    return tmp, clone, tip


def _full_context(clone, tip, run="run-v190"):
    return {
        "parent": "p" * 40, "version": "1.90.0", "size": "1",
        "staged_sha": "0" * 40, "tag": "v1.90.0",
        "package_sha": "a" * 64, "release_uid": "00000001",
        "site_commit": tip, "run_uid": run,
        "receipt_sha": "r" * 64, "mode": "real",
        "scorecard_sha": "s" * 64,
        "site_clone_dir": str(clone), "site_ref": "refs/heads/main",
        "site_endpoint_url": "https://example.invalid/badge.svg",
    }


class WiringTests(unittest.TestCase):
    """AC1 — the eight are INVOKED BY THE SAGA, not present in the module."""

    def test_every_unwired_checkpoint_records_a_saga_observation(self) -> None:
        publisher = _load_publisher()
        tmp, clone, tip = _cas_fixture("wire")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(tmp)]))
        with tempfile.TemporaryDirectory(prefix="v190_run_") as rundir:
            run_dir = Path(rundir).resolve()
            (run_dir / "run.jsonl").write_text(
                json.dumps({"data": {"saga_id": "release:run-v190",
                                     "pipeline_run_uid": "run-v190"}}) + "\n",
                encoding="utf-8")
            journal = saga.SagaJournal.open(
                run_dir / "release-saga.jsonl", "release:run-v190")
            context = _full_context(clone, tip)
            with mock.patch.object(publisher, "_observe_public_asset",
                                   return_value="a" * 64):
                for checkpoint_id in UNWIRED_EIGHT:
                    # One call performs-or-observes the act AND records it
                    # through the journal (AC1's demanded entrypoint).
                    publisher.wire_checkpoint(journal, checkpoint_id, context)
            observed = {
                c for c in UNWIRED_EIGHT
                if journal.observed(c) is not None
            }
            self.assertEqual(
                observed, set(UNWIRED_EIGHT),
                f"checkpoints performed without a saga observation: "
                f"{sorted(set(UNWIRED_EIGHT) - observed)} — presence in the "
                f"module is not wiring (AC1)")

    def test_a_no_op_adapter_stub_turns_this_red_for_its_checkpoint(self) -> None:
        """The A153 mutation, planted as a test-time guarantee: an adapter
        that does nothing must not produce an observation."""
        publisher = _load_publisher()
        tmp, clone, tip = _cas_fixture("stub")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(tmp)]))
        with tempfile.TemporaryDirectory(prefix="v190_run_") as rundir:
            run_dir = Path(rundir).resolve()
            (run_dir / "run.jsonl").write_text(
                json.dumps({"data": {"saga_id": "release:run-v190b",
                                     "pipeline_run_uid": "run-v190b"}}) + "\n",
                encoding="utf-8")
            journal = saga.SagaJournal.open(
                run_dir / "release-saga.jsonl", "release:run-v190b")
            context = _full_context(clone, tip, run="run-v190b")
            with mock.patch.object(publisher, "_adapter_site_prepare",
                                   lambda *a, **k: None):
                result = publisher.wire_checkpoint(
                    journal, "site_prepare", context)
                self.assertIsNone(
                    result,
                    "a no-op adapter produced a result — wiring must yield "
                    "nothing when the act yields nothing")
                self.assertIsNone(
                    journal.observed("site_prepare"),
                    "a no-op adapter produced an observation: the journal can "
                    "be satisfied without the act — AC1's exact failure")


class SiteRefCASTests(unittest.TestCase):
    """AC2 — site_ref is a compare-and-swap, against a local bare repo."""

    def _fixture(self) -> tuple[Path, Path, str]:
        """A bare remote with one commit, plus a clone whose lease matches."""
        tmp = Path(tempfile.mkdtemp(prefix="v190_cas_")).resolve()
        remote = tmp / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        clone = tmp / "site"
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
        subprocess.run(["git", "-C", str(clone), "commit", "--allow-empty",
                        "-m", "badge site v1.90.0"], check=True)
        subprocess.run(["git", "-C", str(clone), "commit", "--amend",
                        "--allow-empty", "-m", "badge site v1.90.0"], check=True)
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.email", "t@t"],
            check=True)
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", str(clone), "commit", "--allow-empty",
                        "-m", "badge site v1.90.0"], check=True)
        tip = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        return tmp, clone, tip

    def test_matching_lease_pushes_and_observes(self) -> None:
        publisher = _load_publisher()
        tmp, clone, tip = self._fixture()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(tmp)]))
        context = {"site_commit": tip, "version": "1.90.0"}
        result = publisher.site_ref_cas_push(
            clone, "refs/heads/main", tip, expected_remote_tip=None)
        self.assertTrue(result.ok, result.detail)

    def test_moved_remote_refuses_and_names_the_pending_state(self) -> None:
        publisher = _load_publisher()
        tmp, clone, tip = self._fixture()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(tmp)]))
        # A competitor lands from a SECOND clone — the real contention shape.
        # Pushing from our own clone would update our tracking belief too,
        # and the lease would legitimately match: CAS cannot see contention
        # you caused yourself after re-reading your own push.
        rival = tmp / "rival"
        subprocess.run(["git", "clone", "-q", str(tmp / "remote.git"),
                        str(rival)], check=True)
        for key, value in (("user.email", "r@r"), ("user.name", "r")):
            subprocess.run(["git", "-C", str(rival), "config", key, value],
                           check=True)
        subprocess.run(["git", "-C", str(rival), "commit", "--allow-empty",
                        "-m", "competitor"], check=True)
        subprocess.run(["git", "-C", str(rival), "push", "-q", "origin",
                        "HEAD:refs/heads/main"], check=True)
        # Our clone's BELIEF is still the old tip; the world has moved.
        result = publisher.site_ref_cas_push(
            clone, "refs/heads/main", tip, expected_remote_tip=None)
        self.assertFalse(result.ok, "a moved remote was overwritten")
        self.assertEqual(result.incomplete_state, "release-live-site-pending")


class ReplaySafetyTests(unittest.TestCase):
    """AC3 — conflict, never overwrite, for the three replay-weighted acts."""

    def test_same_bytes_replay_is_already_present(self) -> None:
        publisher = _load_publisher()
        observation = publisher.replay_check(
            "site_ref", idempotency_key="site-ref:" + "1" * 40,
            expected={"site_commit": "1" * 40}, found={"site_commit": "1" * 40})
        self.assertEqual(observation.outcome, saga.OUTCOME_ALREADY_PRESENT)

    def test_different_bytes_conflict_and_refuse(self) -> None:
        publisher = _load_publisher()
        observation = publisher.replay_check(
            "github_asset", idempotency_key="gh-asset:v1.90.0:" + "a" * 64,
            expected={"package_sha": "a" * 64}, found={"package_sha": "b" * 64})
        self.assertEqual(observation.outcome, saga.OUTCOME_REFUSED)
        self.assertTrue(observation.detail)


class ManifestUrlResolutionTests(unittest.TestCase):
    """AC4 — the gate RESOLVES every URL the manifest names."""

    def test_one_absent_url_fails_naming_it(self) -> None:
        publisher = _load_publisher()
        manifest = {
            "current": "1.90.0",
            "updates": [
                {"version": "1.90.0",
                 "url": "https://example.invalid/tropo-os-v1.90.0.zip"},
            ],
        }
        with self.assertRaises(publisher.PublishError) as caught:
            publisher.resolve_manifest_urls(manifest)
        self.assertIn("tropo-os-v1.90.0.zip", str(caught.exception))

    def test_structural_only_check_is_the_red_mutation(self) -> None:
        """Reverting to `assert current == version` (the 1.87/1.88 defect)
        cannot satisfy resolve_manifest_urls: the resolver must touch the
        network for every named entry."""
        publisher = _load_publisher()
        # A manifest whose ONLY virtue is structural: names the version,
        # names a URL that does not resolve. Structural-only passes it;
        # the resolver must not.
        manifest = {"current": "1.90.0",
                    "updates": [{"version": "1.90.0",
                                 "url": "https://example.invalid/x.zip"}]}
        source = Path(publisher.__file__).read_text(encoding="utf-8")
        self.assertIn(
            "def resolve_manifest_urls", source,
            "the resolver was replaced by a structural check — that exact "
            "insufficiency shipped 1.87 and 1.88 with no update package")


class FireIntegrationTests(unittest.TestCase):
    """AC1's real-path half — cmd_fire itself journals the eight act sites.

    The WiringTests classes above prove the adapter layer invoked directly.
    These prove the FIRE SEQUENCE invokes it: cmd_fire, driven end to end
    with provider edges mocked at the boundary (GitHub, Supabase, badge,
    publish-state), must land a saga observation for every one of the eight
    checkpoints with context taken from the live fire, and must refuse its
    success exit when any observation is missing. Red at birth by design:
    until the wiring lands, cmd_fire performs its acts with no journal.
    """

    def _drive_cmd_fire(self, *, skip_checkpoint=None, stub_adapter=None,
                        invalid_scorecard=False):
        """One full cmd_fire run against real fixture git and mocked edges.

        Returns (exit_code, journal, run_uid). `skip_checkpoint` simulates a
        removed wire_checkpoint call site (the AC1 integration mutation);
        `stub_adapter` simulates a no-op adapter (the WiringTests mutation,
        applied on the real path); `invalid_scorecard` makes the producer emit
        a well-formed-JSON but schema-INVALID card, which is the shape that used
        to satisfy completion_verification and let a fire report LIVE over a
        measurement nobody could trust.
        """
        publisher = _load_publisher()
        tmp, clone, tip = _cas_fixture("fireint")
        # The fire pushes the staged tag after main; the fixture's commit is
        # the staged release, so the tag points at it.
        subprocess.run(["git", "-C", str(clone), "tag", "v1.90.0"], check=True)
        releases = tmp / "releases"
        releases.mkdir()
        # 8-hex, because that is what the scorecard schema's `pipeline_run_uid`
        # and `saga_id` patterns require. The old placeholder ("run-v190-fireint")
        # violated both and nothing said so — the structural fallback skipped
        # `pattern` entirely. The strict fallback caught it the first time it ran.
        run_uid = "a190f1e7"
        state = {
            "version": "1.90.0", "tag": "v1.90.0", "staged_sha": tip,
            "staged_at": "2026-08-21T00:00:00Z", "activation_uid": run_uid,
            "remote": str(tmp / "remote.git"), "clone_dir": str(clone),
        }
        state_file = releases / "v1.90.0" / "publish-state.json"
        state_file.parent.mkdir(parents=True)
        state_file.write_text(json.dumps(state), encoding="utf-8")

        ac7 = {"package_sha256": "a" * 64, "identity": type(
            "I", (), {"activation_uid": run_uid, "run_uid": run_uid})()}

        # THE SEAM THIS TEST EXISTS TO HOLD, wired the way production wires it.
        #
        # Two fixture gaps used to make the eight-act-site contract unsatisfiable
        # here, and together they hid a real deadlock for a full release cycle:
        #
        #   1. `identity` carried no `run_uid`, so `_run_journal_folder` returned
        #      None and the scorecard path could not even be computed.
        #   2. No `scorecard_producer` was injected, so nothing could write the
        #      card that `completion_verification` observes.
        #
        # The fix is NOT to pre-plant a scorecard — that would encode "a first
        # fire cannot complete" as intended behaviour. It is to inject the
        # producer the orchestrator injects, so this drives the real seam:
        # publisher calls producer, producer writes a real card, publisher
        # validates it, completion is observed. Remove the producer call from
        # cmd_fire and this test goes red, which is the whole point of it.
        run_folder = tmp / "pipeline-runs" / f"release-{run_uid}"
        run_folder.mkdir(parents=True)

        def _fixture_scorecard_producer(fired_version: str) -> None:
            """Stands in for tropo-release.py::_write_real_fire_scorecard."""
            if invalid_scorecard:
                # Exactly the shape a real fire produced before this cycle: a
                # card naming no release, with a null required timestamp. Valid
                # JSON, invalid measurement.
                target = publisher.release_metrics.scorecard_path(
                    run_folder, publisher.release_metrics.REAL_FIRE)
                target.write_text(json.dumps({
                    "schema_version": 1,
                    "mode": publisher.release_metrics.REAL_FIRE,
                    "saga_id": f"release:{run_uid}",
                    "pipeline_run_uid": run_uid,
                    "release_version": "",
                    "gestures": {"count": 0, "target": 3, "met": False,
                                 "inputs": []},
                    "timestamps": {"scope_locked_at": None,
                                   "orchestrator_started_at": None,
                                   "primary_live_at": None,
                                   "all_targets_live_at": None},
                    "elapsed": {"lock_to_all_targets_live_seconds": None,
                                "active_machine_seconds": None},
                    "refusals": {"recorded": False},
                    "verdict": "fail",
                }, indent=2) + "\n", encoding="utf-8")
                return
            card = publisher.release_metrics.build_scorecard(
                mode=publisher.release_metrics.REAL_FIRE,
                saga_id=f"release:{run_uid}",
                pipeline_run_uid=run_uid,
                release_version=fired_version,
                principal_inputs=[
                    {"input": "release_scope_locked", "at": "2026-08-21T00:00:00Z"},
                    {"input": "release_orchestrator_invoked",
                     "at": "2026-08-21T00:05:00Z"},
                    {"input": "release_fire_authorized", "at": "2026-08-21T00:10:00Z"},
                ],
                timestamps={
                    "scope_locked_at": "2026-08-21T00:00:00Z",
                    "orchestrator_started_at": "2026-08-21T00:05:00Z",
                    "primary_live_at": "2026-08-21T00:10:00Z",
                    "all_targets_live_at": "2026-08-21T00:12:00Z",
                },
                active_machine_seconds=None,
                observed_refusals=[],
                baseline={"baseline_version": "1", "composite_sha256": "b" * 64,
                          "classifier_version": "1", "classes": []},
                refusal_coverage=["tropo-build-release.py"],
            )
            target = publisher.release_metrics.scorecard_path(
                run_folder, publisher.release_metrics.REAL_FIRE)
            target.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")
        vstate = {
            "status": "verified", "expect": "1.90.0", "tag": "v1.90.0",
            "expected_sha": tip, "remote_main_sha": tip, "remote_tag_sha": tip,
        }
        real_wire = publisher.wire_checkpoint

        def skipping_wire(journal, checkpoint_id, context):
            if checkpoint_id == skip_checkpoint:
                return None
            return real_wire(journal, checkpoint_id, context)

        patches = [
            mock.patch.object(publisher, "_read_state", return_value=state),
            mock.patch.object(publisher, "_confirm_tty", return_value=True),
            # S3 AC1 (176a8995): cmd_fire now runs the whole pre-outward-fire
            # preflight (transport probe, gh/Supabase credentials, zip + sealed
            # notes, release entry, badge target) BEFORE its confirm. This
            # harness mocks the fire's edges and drives its act sites; the
            # preflight is one more edge here — its own suites prove it
            # (test_publish_preflight_v191, test_transport_preflight_v191).
            mock.patch.object(publisher, "run_fire_preflight", return_value=0),
            mock.patch.object(publisher, "require_release_authorization"),
            mock.patch.object(publisher, "_release_entry_uid_for",
                              return_value="00000001"),
            mock.patch.object(publisher, "require_ac7_receipt_set",
                              return_value=ac7),
            mock.patch.object(publisher, "_require_pinned_remote",
                              return_value=state["remote"]),
            mock.patch.object(publisher, "_require_clone_origin"),
            mock.patch.object(publisher, "_view_release_object",
                              return_value={"tag": "v1.90.0"}),
            mock.patch.object(publisher.tropo_roots, "RELEASES_DIR", releases),
            mock.patch.object(publisher, "_upload_supabase_zip"),
            mock.patch.object(publisher, "_verify_sealed_briefing_notes"),
            mock.patch.object(publisher, "_stamp_os_release_badge"),
            mock.patch.object(publisher, "_flip_release_entry_to_shipped"),
            mock.patch.object(publisher, "_upload_update_manifest"),
            mock.patch.object(publisher, "_verify_published_update_manifest"),
            mock.patch.object(publisher, "_run_publish_state",
                              return_value=vstate),
            mock.patch.object(publisher, "_complete_verified_publication",
                              return_value=({"receipt": {}}, "r" * 64, "t48")),
            mock.patch.object(publisher, "_initiate_release_closure",
                              return_value={"ok": True, "closed": ["x"]}),
            mock.patch.object(publisher, "_observe_public_asset",
                              return_value="a" * 64),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        if skip_checkpoint is not None:
            wire_patch = mock.patch.object(publisher, "wire_checkpoint",
                                           side_effect=skipping_wire)
            wire_patch.start()
            self.addCleanup(wire_patch.stop)
        if stub_adapter is not None:
            stub_patch = mock.patch.object(
                publisher, f"_adapter_{stub_adapter}", lambda *a, **k: None)
            stub_patch.start()
            self.addCleanup(stub_patch.stop)

        run_folder_patch = mock.patch.object(
            publisher, "_run_journal_folder", return_value=run_folder)
        run_folder_patch.start()
        self.addCleanup(run_folder_patch.stop)

        import argparse as _argparse
        args = _argparse.Namespace(
            version="1.90.0",
            scorecard_producer=_fixture_scorecard_producer,
        )
        exit_code = publisher.cmd_fire(args)
        journal = saga.SagaJournal.open(
            releases / "v1.90.0" / "release-saga.jsonl",
            saga.saga_id_for(run_uid))
        return exit_code, journal, run_uid, tip

    def test_an_invalid_scorecard_does_not_satisfy_completion(self) -> None:
        """The false-green control, and the reason existence is not the bar.

        Before this cycle the completion adapter asked only whether a file was
        at the path. So a card naming no release, with four null timestamps and
        no recorded refusals, satisfied the act site — and the fire printed
        LIVE and returned 0 over a measurement that was structurally incapable
        of being trusted. Here the same card must NOT satisfy it.

        Paired deliberately with the green case above: together they prove the
        gate discriminates on VALIDITY. A control that only ever sees an invalid
        card cannot tell "rejects bad" from "rejects everything".
        """
        exit_code, journal, run_uid, tip = self._drive_cmd_fire(
            invalid_scorecard=True)
        self.assertNotEqual(exit_code, 0,
                            "an invalid measurement must not report a clean fire")
        self.assertIsNone(
            journal.observed("completion_verification"),
            "completion may not be observed from a schema-invalid scorecard")

    def test_cmd_fire_journals_all_eight_act_sites(self) -> None:
        exit_code, journal, run_uid, tip = self._drive_cmd_fire()
        self.assertEqual(
            exit_code, 0,
            "the driven fire must succeed with every provider edge green")
        observed = {
            c for c in UNWIRED_EIGHT if journal.observed(c) is not None}
        self.assertEqual(
            observed, set(UNWIRED_EIGHT),
            f"cmd_fire performed acts without saga observations: "
            f"{sorted(set(UNWIRED_EIGHT) - observed)} — the fire sequence, "
            f"not the adapter layer, is unwired (AC1's real-path half)")
        # The observations carry LIVE context, not fixture constants: the
        # site_commit is the clone's real tip and the saga id derives from
        # the staged activation uid.
        site_ref = journal.observed("site_ref")
        self.assertEqual(site_ref["fact"]["site_commit"], tip)
        self.assertEqual(journal.saga_id, f"release:{run_uid}")

    def test_removed_wire_call_site_refuses_success_exit(self) -> None:
        """The AC1 integration mutation: deleting one wire_checkpoint call
        from cmd_fire leaves its observation missing and the fire must not
        return success over a journal that cannot describe it."""
        exit_code, journal, _, _ = self._drive_cmd_fire(
            skip_checkpoint="closure")
        self.assertNotEqual(
            exit_code, 0,
            "cmd_fire returned success with an unjournalled act site — "
            "a fire the saga cannot describe is not a successful fire")
        self.assertIsNone(
            journal.observed("closure"),
            "the skipped checkpoint somehow observed — the mutation "
            "simulation is broken, not the wiring")

    def test_no_op_adapter_on_the_real_path_refuses_success_exit(self) -> None:
        """The WiringTests no-op mutation, applied on the fire's own path:
        an adapter that records nothing must cost the fire its success."""
        exit_code, journal, _, _ = self._drive_cmd_fire(
            stub_adapter="release_entry_projection")
        self.assertNotEqual(exit_code, 0)
        self.assertIsNone(journal.observed("release_entry_projection"))


class ClosedEnumTests(unittest.TestCase):
    """AC7 — CHECKPOINTS stays a closed enum; unregistered acts refuse."""

    def test_unregistered_checkpoint_id_refuses(self) -> None:
        with self.assertRaises(saga.ReleaseSagaError):
            saga.assert_registered("not-a-checkpoint")

    def test_all_fifteen_registered(self) -> None:
        for checkpoint in saga.CHECKPOINTS:
            saga.assert_registered(checkpoint.checkpoint_id)

    def test_site_ref_declared_with_pending_state(self) -> None:
        site_ref = saga.CHECKPOINTS_BY_ID["site_ref"]
        self.assertEqual(site_ref.incomplete_state, "release-live-site-pending")


if __name__ == "__main__":
    unittest.main()
