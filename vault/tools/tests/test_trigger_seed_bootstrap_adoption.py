"""The owner's bootstrap adopts a trigger-step (E6) seed — argus-a169, 2026-09-04.

Known-positive: the exact seed the v1.94 doc leg carried (run f0151bfa63c7: one run_created with
pipeline_uid, pipeline_run_uid, auto_triggered: true) must be adoptable. Negative controls: a second event,
a run-uid mismatch, and a plain non-pending seed all stay refused — the "already has events" guard is
unchanged for every other history.
"""
import importlib.util, json, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("rt", ROOT / "vault/tools/9e7003b1.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

RUN_FM = {"uid": "f0151bfa63c7", "pipeline": "5a4337ff", "substrate_authored_by": "f0155ade45f5"}


def _folder(events):
    d = Path(tempfile.mkdtemp(prefix="trigger-seed-"))
    (d / "run.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return d


def _seed(**over):
    data = {"pipeline_uid": "5a4337ff", "pipeline_run_uid": "f0151bfa63c7", "auto_triggered": True}
    data.update(over)
    return {"event": "run_created", "ts": "2026-09-04T12:16:37Z", "actor": "argus-a169",
            "data": data, "schema_version": 2, "trace_id": "f0155ade45f5", "span_id": "edc9af6c3b5c1514"}


class TriggerSeedIsAdoptable(unittest.TestCase):
    def test_v194_doc_leg_seed_is_adopted(self):
        ev = rt._pending_lock_run_created(_folder([_seed()]), RUN_FM)
        self.assertIsNotNone(ev, "the E6 seed the v1.94 doc leg carried must be adoptable")
        self.assertEqual(ev["data"]["pipeline_run_uid"], "f0151bfa63c7")

    def test_new_self_describing_seed_is_adopted(self):
        ev = rt._pending_lock_run_created(_folder([_seed(bootstrap_pending=True, activation_uid="f0155ade45f5",
                                                         subject_kind="doc-pipeline", subject_uid="f01563e39d18")]), RUN_FM)
        self.assertIsNotNone(ev)

    def test_run_uid_mismatch_is_refused(self):
        self.assertIsNone(rt._pending_lock_run_created(_folder([_seed(pipeline_run_uid="deadbeefdead")]), RUN_FM))

    def test_second_event_is_refused(self):
        two = [_seed(), {"event": "activation_contract_locked", "ts": "x", "actor": "y", "data": {}}]
        self.assertIsNone(rt._pending_lock_run_created(_folder(two), RUN_FM))

    def test_plain_non_pending_seed_stays_refused(self):
        # NEGATIVE CONTROL for the adoption clause: without auto_triggered the old rule holds.
        plain = _seed(); plain["data"].pop("auto_triggered")
        self.assertIsNone(rt._pending_lock_run_created(_folder([plain]), RUN_FM))


if __name__ == "__main__":
    unittest.main()
