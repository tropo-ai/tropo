#!/usr/bin/env python3
"""3d8d4351 AC1/AC2/AC4 — the sequence as data, walked as preconditions.

The MACRO_SEQUENCE declaration, the stage-named refusals, the d9025a97
unbootstrapped-stamp fixture at BOTH ends, and the declaration's divergence
facts asserted against the runner's own constants.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

sys.path.insert(0, str(TOOLS / "lib"))
import release_bindings as rb  # noqa: E402
from lib.release_gates import PREFLIGHT_EVIDENCE_FILENAME  # noqa: E402

_tr = importlib.util.spec_from_file_location("tr", TOOLS / "tropo-release.py")
tr = importlib.util.module_from_spec(_tr)
sys.modules["tr"] = tr
_tr.loader.exec_module(tr)

_rr = importlib.util.spec_from_file_location("rr", TOOLS / "tropo-release-run.py")
rr = importlib.util.module_from_spec(_rr)
sys.modules["rr"] = rr
_rr.loader.exec_module(rr)

IDENT = {"saga_id": "release:aaaaaaaa", "pipeline_run_uid": "aaaaaaaa",
         "activation_uid": "aabbccdd"}


def _lock_row():
    return {"event": "tropo.release.scope_locked", "ts": "2026-08-31T05:00:00Z",
            "actor": "7b921d17", "data": {"saga_id": IDENT["saga_id"],
            "pipeline_run_uid": IDENT["pipeline_run_uid"]},
            "schema_version": 2, "trace_id": IDENT["pipeline_run_uid"],
            "span_id": "lock"}


def _freeze_row():
    return {"event": "tropo.release.package_frozen", "ts": "2026-08-31T05:30:00Z",
            "actor": "4e8d1c60",
            "data": {"saga_id": IDENT["saga_id"],
                     "release_run_uid": IDENT["pipeline_run_uid"],
                     "package_sha256": "a" * 64},
            "schema_version": 2, "trace_id": IDENT["pipeline_run_uid"],
            "span_id": "frz"}


class SequenceDeclarationTests(unittest.TestCase):
    """AC1: the sequence is data; the divergence facts agree with the runner."""

    def test_the_eight_stages_in_order(self) -> None:
        self.assertEqual([s["stage"] for s in rb.MACRO_SEQUENCE],
                         ["LOCK", "BOOTSTRAP", "STEPS", "BUILD", "STAGE",
                          "PREFLIGHT", "ORCHESTRATOR", "FIRE"])

    def test_every_stage_names_its_store_and_declared_reader(self) -> None:
        for s in rb.MACRO_SEQUENCE:
            with self.subTest(stage=s["stage"]):
                self.assertTrue(s.get("evidence_store"))
                target = TOOLS / s["reader_module"] if not s["reader_module"].startswith("lib") \
                    else TOOLS / "lib" / s["reader_module"]
                if s["reader_module"] == "release_package.py":
                    target = TOOLS / "lib" / "release_package.py"
                self.assertTrue(target.is_file(), target)
                src = target.read_text()
                self.assertTrue((f"def {s['reader']}(" in src)
                                or (f"{s['reader']} =" in src)
                                or (f"{s['reader']}:" in src),
                                "%s not in %s" % (s["reader"], s["reader_module"]))

    def test_fire_never_invoked_uid_matches_the_runner(self) -> None:
        fire = rb.MACRO_SEQUENCE[-1]
        self.assertEqual(fire["never_invoked_uid"], "3dd817cb")
        runner_src = (TOOLS / "tropo-release-run.py").read_text()
        self.assertIn('NEVER_INVOKED = frozenset({"3dd817cb"})', runner_src,
                      "one fact, two homes — they cannot drift")


class WalkRefusalTests(unittest.TestCase):
    """AC2: the walk refuses stage-by-stage, naming stage + producing command."""

    def _gate(self, rows=(), state=None, pf=False):
        with tempfile.TemporaryDirectory() as tmp:
            rd = Path(tmp) / "run"
            rd.mkdir()
            if rows:
                (rd / "run.jsonl").write_text(
                    "\n".join(json.dumps(r) for r in rows) + "\n")
            if state is not None:
                (rd / "run.state.json").write_text(json.dumps(state))
            if pf:
                # The fixture writes the name the WRITER writes, imported from
                # its module — not a literal typed to match the gate. Until
                # 2026-08-31 this hand-wrote "preflight-journal.jsonl", the
                # same wrong name the gate read, so the pair agreed with each
                # other and with nothing that actually runs. A fixture built in
                # the reader's own shape is why this gate looked tested.
                (rd / PREFLIGHT_EVIDENCE_FILENAME).write_text("{}\n")
            wired = tr._load_wired_publisher()
            with patch.object(tr, "_load_wired_publisher", return_value=wired), \
                 patch.object(wired.tropo_roots, "RELEASES_DIR", Path(tmp) / "releases"), \
                 patch.object(wired, "_run_publish_state", side_effect=AssertionError("no staged fixture to probe")):
                return tr._fire_sequence_gate(rd, Path(tmp), IDENT, "9.9.9")

    def test_empty_run_refuses_at_lock_naming_the_command(self) -> None:
        r = self._gate()
        self.assertIsNotNone(r)
        self.assertIn("LOCK", r[1])
        self.assertIn("lock", r[1].lower(),
                      "the refusal names what produces the evidence")

    def test_lock_then_refuses_at_bootstrap(self) -> None:
        r = self._gate(rows=[_lock_row()])
        self.assertIn("BOOTSTRAP", r[1])

    def test_bootstrapped_refuses_at_build(self) -> None:
        r = self._gate(rows=[_lock_row()],
                       state={"activation_uid": "aabbccdd", "run_status": "active",
                              "step_status": {"s1": "verified"}})
        self.assertIn("BUILD", r[1])

    def test_frozen_advances_past_build(self) -> None:
        r = self._gate(rows=[_lock_row(), _freeze_row()],
                       state={"activation_uid": "aabbccdd", "run_status": "active",
                              "step_status": {"s1": "verified"}})
        self.assertIsNotNone(r)
        self.assertIn("STAGE", r[1])
        self.assertIn("nothing is staged", r[1],
                      "BUILD passed and the explicitly named fixture has no stage")

    def test_no_refusal_names_an_outward_act_as_remedy(self) -> None:
        """The A159 stale-cure-string rule: refusals never say 're-fire'."""
        for r in (self._gate(), self._gate(rows=[_lock_row()]),
                  self._gate(rows=[_lock_row(), _freeze_row()],
                             state={"activation_uid": "a", "run_status": "active",
                                    "step_status": {"s": "verified"}})):
            if r:
                self.assertNotIn("re-fire", r[1].lower())
                self.assertNotIn("re-run the fire", r[1].lower())


class D9025a97BothEndsTests(unittest.TestCase):
    """AC4's fixture: the unbootstrapped-stamp wedge cured at BOTH ends."""

    def _run_with_stamp(self, bootstrapped):
        # The TemporaryDirectory object must OUTLIVE the return — a `with`
        # block here deleted the run before the test read it (the MISUSE was
        # a missing journal, not the mechanism). Held on the instance until
        # the next call replaces it.
        self._keepalive = tempfile.TemporaryDirectory()
        tmp = self._keepalive.name
        if True:
            # folder name == pipeline_run_uid: _identity ties a journal to its
            # run by that match (a mismatch is a different run's journal)
            rd = Path(tmp) / IDENT["pipeline_run_uid"]
            rd.mkdir()
            stamp = {"event": "tropo.release.orchestrator_invoked",
                     "ts": "2026-08-31T05:10:00Z", "actor": "4e8d1c60",
                     "actor_label_resolved": "tropo-release engine stamp",
                     "data": {"saga_id": IDENT["saga_id"],
                              "pipeline_run_uid": IDENT["pipeline_run_uid"],
                              "invocation_uid": "x",
                              "invoked_via": "bare"},
                     "schema_version": 2,
                     "trace_id": IDENT["pipeline_run_uid"], "span_id": "o"}
            (rd / "run.jsonl").write_text(json.dumps(stamp) + "\n")
            if bootstrapped:
                (rd / "run.state.json").write_text(json.dumps(
                    {"activation_uid": "aabbccdd", "run_status": "active"}))
            return rd

    def test_writer_end_refuses_the_unbootstrapped_stamp(self) -> None:
        import contextlib, io
        rd = self._run_with_stamp(bootstrapped=False)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ok = tr._record_orchestrator_invoked(rd, IDENT)
        self.assertFalse(ok)
        journal = rd / "run.jsonl"
        if journal.is_file():
            self.assertFalse(journal.read_text().count("\n") > 1,
                             "the journal gained nothing")

    def test_reader_end_discounts_the_pre_bootstrap_stamp(self) -> None:
        rd = self._run_with_stamp(bootstrapped=False)
        ctx = rr.RunContext(vault_root=ROOT, release_plan_uid="plan",
                            run_dir=rd, activation_uid="act")
        refusal = rr._requires_orchestrator_invoked(ctx)
        self.assertIsNotNone(refusal)
        self.assertIn("never bootstrapped", refusal)
        self.assertIn("d9025a97", refusal)

    def test_bootstrapped_stamp_is_honored_at_both_ends(self) -> None:
        rd = self._run_with_stamp(bootstrapped=True)
        ctx = rr.RunContext(vault_root=ROOT, release_plan_uid="plan",
                            run_dir=rd, activation_uid="act")
        self.assertIsNone(rr._requires_orchestrator_invoked(ctx))


class RehearsalGateTests(unittest.TestCase):
    """§7: the gate reads the card; the card must be OF this candidate."""

    def _card(self, **over):
        card = {"mode": "rehearsal", "verdict": "pass",
                "release_version": "1.94.0",
                "checkpoints_performed": len(tr.saga.CHECKPOINTS)}
        card.update(over)
        return card

    def test_refusals_name_the_producing_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rd = Path(tmp)
            r = tr._rehearsal_gate(rd, "1.94.0")
            self.assertIn("rehearse --run-dir", r[1])

    def test_version_mismatch_and_checkpoint_gap_refuse(self) -> None:
        import sys as _sys
        _sys.path.insert(0, str(TOOLS / "lib"))
        import release_metrics as _rm
        with tempfile.TemporaryDirectory() as tmp:
            rd = Path(tmp)
            p = _rm.scorecard_path(rd, _rm.REHEARSAL)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._card(release_version="1.93.0")))
            self.assertIn("1.93.0", tr._rehearsal_gate(rd, "1.94.0")[1])
            p.write_text(json.dumps(self._card(checkpoints_performed=1)))
            self.assertIn("checkpoints", tr._rehearsal_gate(rd, "1.94.0")[1])
            p.write_text(json.dumps(self._card()))
            self.assertIsNone(tr._rehearsal_gate(rd, "1.94.0"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
