"""77ec1d61 — v1.94 Stream 5 gauntlet: derive_state must not promote a step to
verified without emitting its receipt (argus-a163 spec, talos-t53 build).

One grantor of 'verified': the verification_receipt fold. The exit-code
shortcut is grandfathered for PRE-cutover events (closed runs — v1.93's
attested freeze among them — must not re-grade); post-cutover, the WRITER
emits the receipt in the same transaction, so status and receipts agree in
every case. Grade-through-receipt shape chosen; cutover timestamp chosen for
historical compatibility (self-describing event timestamps, no run registry,
no retroactive re-grading).

AC1/AC2: pure-fold fixtures, ts-controlled around the cutover.
AC2(c): the manifestation deliberately left unpatched in v1.93 — revert the
derive_state change and the post-cutover-no-receipt fixtures fail (they would
read 'verified'); revert the writer change and the receipt-presence
assertions fail. Both halves are load-bearing.
AC4: the composed freeze-to-fire chain on a throwaway run — the decider finds
a complete four-instrument receipt set.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "d445af8b_verify"
REAL_ACTIVATION_UID = "2e9f4dcd"
REAL_RUN_FOLDER = "release-pipeline-d445af8b-2026-08-27"
CUTOVER = "2026-08-30T00:00:00Z"
PRE = "2026-08-28T00:00:00Z"
POST = "2026-08-30T01:00:00Z"
DISPOSABLE_SHA = "d" * 64
ACTOR = "talos-t53"

EVIDENCE_ENTRY = """---
uid: eext77ec
type: test-run
title: synthetic external-test evidence (77ec1d61 composed chain)
owner: sa.release-test-harness
executed_by: sa.release-test-harness
verdict: pass
release_pipeline_run_uid: "d445af8b"
package_sha256: %s
state: active
---

# Synthetic evidence entry

Fixture record for the composed chain.
""" % DISPOSABLE_SHA


def _decl(step_id, *, vc=True, command="/usr/bin/true", trust="auto"):
    data = {"step_id": step_id, "step_owner_role": "vela",
            "verification_class": vc, "depends_on_steps": [],
            "exit_criteria": ["the toy check passes"],
            "trust_level": trust, "retry_policy": {"max_retries": 0, "backoff": "linear"},
            "timeout_hours": 1, "compensation_step_id": None,
            "instructions_ref": None}
    if command is not None:
        data["verification_command"] = command
    return data


def _ev(kind, step=None, ts=POST, **data):
    row = {"event": kind, "ts": ts, "actor": ACTOR,
           "actor_label_resolved": None, "stage": None,
           "schema_version": 2, "trace_id": REAL_ACTIVATION_UID}
    if step:
        row["step"] = step
    row["data"] = data
    return row


class FoldParity(unittest.TestCase):
    """AC1 + AC2 as pure derive_state fixtures. Imports the REAL engine module
    (no isolation): derive_state is a pure fold with no filesystem reads."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "parity_engine_real", STUDIO_ROOT / "vault" / "tools" / "9e7003b1.py")
        cls.engine = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.engine
        spec.loader.exec_module(cls.engine)
        assert cls.engine.RECEIPT_PARITY_CUTOVER_TS == CUTOVER

    def grade(self, events, step="s1"):
        return self.engine.derive_state(events)["step_status"].get(step)

    # -- AC1 both directions ------------------------------------------------
    def test_post_cutover_exit_code_without_receipt_stays_completed(self):
        events = [_ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
                  _ev("step_started", step="s1", ts=POST),
                  _ev("step_completed", step="s1", ts=POST, natural_verdict="pass",
                      verification_command_exit_code=0)]
        self.assertEqual(self.grade(events), "completed")

    def test_post_cutover_exit_code_with_receipt_reaches_verified(self):
        events = [_ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
                  _ev("step_started", step="s1", ts=POST),
                  _ev("step_completed", step="s1", ts=POST, natural_verdict="pass",
                      verification_command_exit_code=0),
                  _ev("verification_receipt", step="s1", ts=POST, verdict="pass")]
        self.assertEqual(self.grade(events), "verified")

    def test_pre_cutover_exit_code_without_receipt_stays_verified_grandfathered(self):
        """The v1.93 runs are closed with attested freezes; history does not
        re-grade. This is the compatibility choice, tested as a contract."""
        events = [_ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
                  _ev("step_started", step="s1", ts=PRE),
                  _ev("step_completed", step="s1", ts=PRE, natural_verdict="pass",
                      verification_command_exit_code=0)]
        self.assertEqual(self.grade(events), "verified")

    # -- AC2 named manifestations ------------------------------------------
    def test_manifestation_a_vc_false_step_receipt_backed(self):
        """(a) was patched narrowly in v1.93 (the E2 auto-receipt). The root
        fix makes that patch redundant: any receipt-less completion, vc either
        way, reads non-terminal post-cutover."""
        events = [_ev("step_declared", step="s1", ts=PRE, **_decl("s1", vc=False, command=None)),
                  _ev("step_started", step="s1", ts=POST),
                  _ev("step_completed", step="s1", ts=POST, natural_verdict="pass"),
                  _ev("verification_receipt", step="s1", ts=POST, verdict="pass")]
        self.assertEqual(self.grade(events), "verified")
        events[-1]["data"]["verdict"] = "fail"
        self.assertEqual(self.grade(events), "completed")

    def test_manifestation_b_no_command_step_needs_verify_step(self):
        """(b): a vc:true step with no verification_command never had the
        shortcut; verify-step's receipt remains its only path."""
        events = [_ev("step_declared", step="s1", ts=PRE, **_decl("s1", command=None)),
                  _ev("step_started", step="s1", ts=POST),
                  _ev("step_completed", step="s1", ts=POST, natural_verdict="pass")]
        self.assertEqual(self.grade(events), "completed")
        events.append(_ev("verification_receipt", step="s1", ts=POST, verdict="pass"))
        self.assertEqual(self.grade(events), "verified")

    def test_manifestation_c_command_passed_step_requires_receipt(self):
        """THE one left unpatched in v1.93: engine-sourced exit code, genuine
        pass, no receipt. Old fold: verified (the lie the release chain
        believed). Post-fix: completed until the receipt exists. Reverting the
        derive_state cutover flips THIS test red."""
        events = [_ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
                  _ev("step_started", step="s1", ts=POST),
                  _ev("step_completed", step="s1", ts=POST, natural_verdict="pass",
                      verification_command_exit_code=0)]
        self.assertEqual(self.grade(events), "completed",
                         "an exit code alone must not confer verified post-cutover")

    def test_absent_timestamp_defaults_to_grandfathered(self):
        """A legacy row with no parseable ts keeps the old grade — conservative
        direction: preserve, never silently un-verify."""
        events = [_ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
                  _ev("step_started", step="s1", ts=PRE),
                  {"event": "step_completed", "actor": ACTOR, "step": "s1",
                   "schema_version": 2, "trace_id": REAL_ACTIVATION_UID,
                   "data": {"natural_verdict": "pass",
                            "verification_command_exit_code": 0}}]
        self.assertEqual(self.grade(events), "verified")


def _load_isolated_engine(tmp: Path):
    shutil.copytree(STUDIO_ROOT / "vault" / "tools", tmp / "vault" / "tools",
                     ignore=shutil.ignore_patterns("__pycache__", "tests"))
    shutil.copytree(STUDIO_ROOT / ".tropo" / "scripts", tmp / ".tropo" / "scripts",
                     ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / "vault" / "files").mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "parity_engine_%s" % abs(hash(str(tmp))),
        tmp / "vault" / "tools" / "9e7003b1.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module.VAULT_ROOT == tmp
    return module


class WriterParity(unittest.TestCase):
    """The writer half: a post-cutover command-verified completion emits the
    receipt in the same transaction (manifestation (c) closed at the root).
    Reverting the writer change fails the receipt-presence assertions."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)
        # Exercise the post-cutover world: every event this fixture writes is
        # after the (patched) cutover.
        self.engine.RECEIPT_PARITY_CUTOVER_TS = "2000-01-01T00:00:00Z"
        for name in (REAL_ACTIVATION_UID, "d445af8b"):
            shutil.copy(FIXTURES / f"{name}.md",
                        self.tmp / "vault" / "files" / f"{name}.md")
        run_dir = self.tmp / "vault" / "pipeline-runs" / REAL_RUN_FOLDER
        run_dir.mkdir(parents=True)
        (run_dir / "run.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"event": "step_declared", "ts": "2001-01-01T00:00:00Z", "actor": ACTOR,
             "step": "4262d5fa", "schema_version": 2, "trace_id": REAL_ACTIVATION_UID,
             "data": _decl("4262d5fa")},
            _ev("step_started", step="4262d5fa", ts="2001-01-01T00:00:01Z"),
            {"event": "tropo.release.candidate_built",
             "ts": "2001-01-01T00:00:02Z", "actor": ACTOR,
             "schema_version": 2, "trace_id": REAL_ACTIVATION_UID,
             "data": {"release_run_uid": "d445af8b",
                      "candidate_sha256": DISPOSABLE_SHA,
                      "version": "9.9.9-fixture"}},
        ]) + "\n")
        self.run_dir = run_dir

    def test_command_completion_emits_receipt_and_reaches_verified(self):
        result = self.engine.action_step_complete(
            REAL_ACTIVATION_UID, "4262d5fa", ["toy.md"], ACTOR)
        self.assertIn("completed", result)
        rows = self.engine.read_events(self.run_dir)
        receipts = [r for r in rows if r.get("event") == "verification_receipt"
                    and r.get("step") == "4262d5fa"]
        self.assertEqual(len(receipts), 1,
                         "the writer must emit the receipt in the same transaction")
        self.assertEqual(receipts[0]["data"]["verdict"], "pass")
        ac7 = [r for r in rows
               if r.get("event") == "release-verification-receipt"
               and r.get("step") == "4262d5fa"]
        self.assertEqual(len(ac7), 1,
                         "full-validator is an AC7 instrument: the machine-mode "
                         "command path must emit the instrument receipt too")
        state = self.engine.derive_state(rows)
        self.assertEqual(state["step_status"]["4262d5fa"], "verified",
                         "grade-through-receipt: status and receipts agree")


class ComposedFreezeChain(unittest.TestCase):
    """AC4: declare a throwaway run, complete all four instruments through
    their real paths, and the freeze decider finds a complete four-instrument
    receipt set. No governed substrate mutated; teardown removes the tmp dir.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = _load_isolated_engine(self.tmp)
        self.engine.RECEIPT_PARITY_CUTOVER_TS = "2000-01-01T00:00:00Z"
        for name in (REAL_ACTIVATION_UID, "d445af8b"):
            shutil.copy(FIXTURES / f"{name}.md",
                        self.tmp / "vault" / "files" / f"{name}.md")
        (self.tmp / "vault" / "files" / "eext77ec.md").write_text(
            EVIDENCE_ENTRY, encoding="utf-8")
        run_dir = self.tmp / "vault" / "pipeline-runs" / REAL_RUN_FOLDER
        run_dir.mkdir(parents=True)
        decls = [
            ("a0f2bea8", _decl("a0f2bea8", vc=True, command="/usr/bin/true")),   # harness
            ("4262d5fa", _decl("4262d5fa", vc=True, command="/usr/bin/true")),   # full-validator
            ("bc6b17ec", _decl("bc6b17ec", vc=False, command=None)),            # external-test
            ("c6b61fb9", _decl("c6b61fb9", vc=True, command="/usr/bin/true")),   # cold-walk
        ]
        rows = [{"event": "step_declared", "ts": "2001-01-01T00:00:00Z",
                 "actor": ACTOR, "step": sid, "schema_version": 2,
                 "trace_id": REAL_ACTIVATION_UID, "data": d} for sid, d in decls]
        rows.append({"event": "tropo.release.candidate_built",
                     "ts": "2001-01-01T00:00:02Z", "actor": ACTOR,
                     "schema_version": 2, "trace_id": REAL_ACTIVATION_UID,
                     "data": {"release_run_uid": "d445af8b",
                              "candidate_sha256": DISPOSABLE_SHA,
                              "version": "9.9.9-fixture"}})
        (run_dir / "run.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n")
        self.run_dir = run_dir

    def _start(self, sid):
        self.engine.action_step_start(REAL_ACTIVATION_UID, sid, ACTOR)

    def test_composed_chain_reaches_a_satisfiable_freeze(self):
        # harness: vc:true + command — manifestation (c), writer-emitted.
        self._start("a0f2bea8")
        self.engine.action_step_complete(
            REAL_ACTIVATION_UID, "a0f2bea8", ["h.txt"], ACTOR)
        # full-validator: same shape.
        self._start("4262d5fa")
        self.engine.action_step_complete(
            REAL_ACTIVATION_UID, "4262d5fa", ["v.txt"], ACTOR)
        # external-test: vc:false + human evidence — the Metis-ruled path.
        self._start("bc6b17ec")
        self.engine.action_step_complete(
            REAL_ACTIVATION_UID, "bc6b17ec", ["e.txt"], ACTOR,
            execution_mode="human", evidence_ref="eext77ec")
        # cold-walk: vc:true + command — writer-emitted again.
        self._start("c6b61fb9")
        self.engine.action_step_complete(
            REAL_ACTIVATION_UID, "c6b61fb9", ["c.txt"], ACTOR)

        rows = self.engine.read_events(self.run_dir)
        receipts = [r["data"] for r in rows
                    if r.get("event") == "release-verification-receipt"]
        self.assertEqual(len(receipts), 4,
                         f"expected four instrument receipts, got "
                         f"{sorted(r.get('instrument') for r in receipts)}")
        state = self.engine.derive_state(rows)
        for sid in ("a0f2bea8", "4262d5fa", "bc6b17ec", "c6b61fb9"):
            self.assertEqual(state["step_status"][sid], "verified",
                             f"{sid} must reach verified WITH its receipt")

        from lib import release_verify as _rv
        bundle = _rv.assert_ready_to_freeze(receipts, "d445af8b", DISPOSABLE_SHA)
        self.assertEqual(
            set(bundle), {"release-harness", "full-validator",
                          "external-test", "cold-walk"},
            "the freeze decider must find all four instruments satisfied")


class SmokeLeg(unittest.TestCase):
    """4e5439c7 owed test 1: import-and-fold a minimal run, so a structural
    break (bad import, broken fold signature) fails BEFORE the behavioural
    assertions do."""

    def test_module_imports_and_folds_a_minimal_run(self):
        spec = importlib.util.spec_from_file_location(
            "parity_smoke_engine", STUDIO_ROOT / "vault" / "tools" / "9e7003b1.py")
        engine = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = engine
        spec.loader.exec_module(engine)
        state = engine.derive_state([
            _ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
            _ev("step_started", step="s1", ts=POST),
            _ev("step_completed", step="s1", ts=POST, natural_verdict="pass"),
        ])
        self.assertEqual(state["step_status"]["s1"], "completed")


class PropertyVerifiedImpliesReceipt(unittest.TestCase):
    """4e5439c7 owed test 2, the property invariant: over generated
    TIME-SORTED streams (the honest-journal shape; events.sort at the fold
    site), any step that reads 'verified' has a passing verification_receipt
    in the stream. Hand-picked fixtures prove the known cases; only this
    proves there is no unknown one.

    THE BOUND IS REAL AND DELIBERATE (A164 non-author verification,
    2026-08-30): production folds APPEND order, not time order, and an
    out-of-order stream carrying a pre-cutover stamp DOES reach verified
    without a receipt on the live engine -- reproduced by A164 against
    9e7003b1 with no scaffolding, and by this suite's own generator at
    sequence 15 when the sort is removed. That hole is the ts-inversion
    sibling, filed same-day in 38a0e0a5 (SCOPE EXTENDED: era must consult
    stream position beside the stamp). This property holds exactly over the
    streams it documents; the unsorted case is that filing's to cure."""

    def test_property_over_generated_sequences(self):
        import random
        spec = importlib.util.spec_from_file_location(
            "parity_property_engine", STUDIO_ROOT / "vault" / "tools" / "9e7003b1.py")
        engine = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = engine
        spec.loader.exec_module(engine)
        rng = random.Random(0x77EC1D61)
        for seq_no in range(300):
            events = [_ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
                      _ev("step_started", step="s1", ts=POST)]
            has_receipt = False
            for _ in range(rng.randint(0, 3)):
                choice = rng.random()
                ts = PRE if rng.random() < 0.5 else POST
                if choice < 0.4:
                    events.append(_ev(
                        "step_completed", step="s1", ts=ts,
                        natural_verdict="pass" if rng.random() < 0.8 else "fail",
                        **({"verification_command_exit_code": rng.choice([0, 0, 1])}
                           if rng.random() < 0.7 else {})))
                elif choice < 0.8:
                    has_receipt = True
                    events.append(_ev(
                        "verification_receipt", step="s1", ts=ts,
                        verdict=rng.choice(["pass", "pass", "fail"])))
                else:
                    events.append(_ev("step_failed", step="s1", ts=ts,
                                      data_extra=None) if False else
                                  _ev("step_reverify_opened", step="s1", ts=ts,
                                      step_uid="s1", instrument="harness",
                                      previous_status="verified",
                                      superseded_candidates=[],
                                      active_candidate_sha256="a" * 64,
                                      reason="gen", reopened_by="gen"))
            # Real journals are append-ordered in time; the generator sorts
            # by ts to model an HONEST stream. Out-of-order streams (a late
            # event carrying a pre-cutover stamp) DO reopen the grandfather
            # shortcut -- a ts-forgery hole sibling of 38a0e0a5's ts-less gap,
            # found by this property on its first run. Filed for the
            # follow-up; the invariant below holds for every honest journal.
            events.sort(key=lambda e: str(e.get('ts') or ''))
            state = engine.derive_state(events)
            status = state["step_status"]["s1"]
            passing_receipt = any(
                e.get("event") == "verification_receipt"
                and (e.get("data") or {}).get("verdict") == "pass"
                for e in events)
            self.assertFalse(
                status == "verified" and not passing_receipt,
                f"seq {seq_no}: verified without a passing receipt -- "
                f"events: {json.dumps(events)}")

        # 38a0e0a5 cure property: the SAME generated sequences, UNSORTED —
        # append order, the shape production folds. Every completion here
        # (whatever its stamp: PRE-forged, POST, or absent) folds AFTER the
        # seed's post-cutover started event, so the position bound alone must
        # close every hole the honest-sort used to mask. This is the exact
        # stream that broke sequence 15 before the cure.
        rng = random.Random(0x77EC1D61)  # same seed, same sequences
        for seq_no in range(300):
            events = [_ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
                      _ev("step_started", step="s1", ts=POST)]
            has_receipt = False
            for _ in range(rng.randint(0, 3)):
                choice = rng.random()
                ts = PRE if rng.random() < 0.5 else POST
                if choice < 0.4:
                    events.append(_ev(
                        "step_completed", step="s1", ts=ts,
                        natural_verdict="pass" if rng.random() < 0.8 else "fail",
                        **({"verification_command_exit_code": rng.choice([0, 0, 1])}
                           if rng.random() < 0.7 else {})))
                elif choice < 0.8:
                    has_receipt = True
                    events.append(_ev(
                        "verification_receipt", step="s1", ts=ts,
                        verdict=rng.choice(["pass", "pass", "fail"])))
                else:
                    events.append(_ev(
                        "step_failed", step="s1", ts=ts,
                                      data_extra=None) if False else
                                  _ev("step_reverify_opened", step="s1", ts=ts,
                                      step_uid="s1", instrument="harness",
                                      previous_status="verified",
                                      superseded_candidates=[],
                                      active_candidate_sha256="a" * 64,
                                      reason="gen", reopened_by="gen"))
            # NO sort: append order is the journal's truth (38a0e0a5 — era
            # consults stream position beside the stamp; the honest-sort mask
            # this property carried since A164's finding retires here).
            state = engine.derive_state(events)
            status = state["step_status"]["s1"]
            passing_receipt = any(
                e.get("event") == "verification_receipt"
                and (e.get("data") or {}).get("verdict") == "pass"
                for e in events)
            self.assertFalse(
                status == "verified" and not passing_receipt,
                f"UNSORTED seq {seq_no}: verified without a passing receipt -- "
                f"events: {json.dumps(events)}")


class BoundedEraTests(unittest.TestCase):
    """38a0e0a5 — both timestamp gaps bounded in one helper.

    Fixtures name each era branch the property cannot generate honestly:
    the ts-less rows in pre-cutover runs (the 30 real v1.93-era rows whose
    grades the conservative default preserves), the same rows in
    post-cutover runs (the never-aging gap), and the forged-stamp sibling.
    """

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "parity_era_engine", STUDIO_ROOT / "vault" / "tools" / "9e7003b1.py")
        cls.engine = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.engine
        spec.loader.exec_module(cls.engine)

    def _completed(self, ts, exit_code=0):
        return _ev("step_completed", step="s1", ts=ts,
                   natural_verdict="pass",
                   verification_command_exit_code=exit_code)

    def test_a_forged_pre_cutover_stamp_after_a_post_cutover_event_earns_nothing(self):
        """The ts-inversion sibling, closed: stream position beats the stamp."""
        state = self.engine.derive_state([
            _ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
            _ev("step_started", step="s1", ts=POST),
            self._completed(ts=PRE),  # forged: appended after a post-cutover event
        ])
        self.assertEqual(state["step_status"]["s1"], "completed")

    def test_a_ts_less_completion_in_a_post_cutover_run_earns_nothing(self):
        """The never-aging gap, closed: absent ts inherits nothing when the
        run's own era (a post-cutover started event) is post-cutover."""
        row = self._completed(ts=None)
        row.pop("ts")
        state = self.engine.derive_state([
            _ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
            _ev("step_started", step="s1", ts=POST),
            row,
        ])
        self.assertEqual(state["step_status"]["s1"], "completed")

    def test_a_ts_less_completion_in_a_pre_cutover_run_keeps_its_legacy_grade(self):
        """The 30 real rows: a run whose era is pre-cutover keeps leniency for
        its ts-less completions — flipping this would re-grade v1.93 history."""
        row = self._completed(ts=None)
        row.pop("ts")
        state = self.engine.derive_state([
            _ev("step_declared", step="s1", ts=PRE, **_decl("s1")),
            _ev("step_started", step="s1", ts=PRE),
            row,
        ])
        self.assertEqual(state["step_status"]["s1"], "verified")

    def test_a_wholly_ts_less_stream_stays_conservative(self):
        """No era evidence anywhere: the deliberate conservative branch (the
        fold never un-grades what it cannot date; the validator's
        ts-less-after-cutover warning is the surface that names such a run,
        not the fold)."""
        row = self._completed(ts=None)
        row.pop("ts")
        state = self.engine.derive_state([row])
        self.assertEqual(state["step_status"]["s1"], "verified")


if __name__ == "__main__":
    unittest.main()
