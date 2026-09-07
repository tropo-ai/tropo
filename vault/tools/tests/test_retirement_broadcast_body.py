#!/usr/bin/env python3
"""Retirement broadcast body carries the letter (playbook e2c7d185 step 7).

Step 7 specifies a body of 2-4 sentences with pointers to the letter and, if
written, the reflection. `tropo-lineage.py` hard-coded a body naming only the
lineage file. Measured at metis-g116's boot: of 101 retirement broadcasts ever
emitted, 37 carried a pointer to the letter.

The controls below are the point. Each one must change verdict when the
mechanism it names is removed, or it proves nothing.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[1] / "tropo-lineage.py"
_spec = importlib.util.spec_from_file_location("tropo_lineage_under_test", _TOOL)
lin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lin)


class RetirementBodyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "agents" / "zeta" / "transfers").mkdir(parents=True)
        (self.root / "agents" / "zeta" / "reflections").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _body(self, record, agent="zeta"):
        gen = record.get("gen", "Z9")
        return lin._retirement_body(
            self.root, agent, record, f"{agent} {gen} retired")

    def test_letter_named_when_recorded_by_flag(self):
        """--letter path: the recorded destination is named."""
        rec = {"gen": "Z9", "t": "retired",
               "letter": "agents/zeta/transfers/Z9.md"}
        self.assertIn("Letter: agents/zeta/transfers/Z9.md", self._body(rec))

    def test_letter_found_at_canonical_home_without_the_flag(self):
        """The documented close-without---letter path still names the letter.

        An agent who authors the letter in place closes WITHOUT --letter,
        because the tool refuses to place over an existing slot. metis-g115
        closed exactly this way. A missing `letter` key is not evidence of a
        missing letter.
        """
        (self.root / "agents/zeta/transfers/Z9.md").write_text("letter body")
        rec = {"gen": "Z9", "t": "retired"}
        self.assertIn("Letter: agents/zeta/transfers/Z9.md", self._body(rec))

    def test_no_letter_claimed_when_none_exists(self):
        """NEGATIVE CONTROL: never announce a letter that is not on disk.

        Goes red if the fallback stops checking existence and derives the
        path unconditionally.
        """
        rec = {"gen": "Z9", "t": "retired"}
        body = self._body(rec)
        self.assertNotIn("Letter:", body)
        self.assertIn("Lineage: agents/zeta/lineage.jsonl", body)

    def test_reflection_named_only_when_written(self):
        """Reflection is optional; name it if and only if it exists."""
        rec = {"gen": "Z9", "t": "retired"}
        self.assertNotIn("Reflection:", self._body(rec))
        (self.root / "agents/zeta/reflections/z9-reflection.md").write_text("x")
        self.assertIn("Reflection: agents/zeta/reflections/z9-reflection.md",
                      self._body(rec))

    def test_agents_own_closing_note_survives_into_the_body(self):
        """The retiring agent's summary is on the record; do not throw it away."""
        rec = {"gen": "Z9", "t": "retired", "note": "closed the vacuous class"}
        self.assertIn("closed the vacuous class", self._body(rec))

    def test_body_is_not_the_old_boilerplate(self):
        """The regression this file exists for.

        The old body was exactly headline + lineage. With a letter on disk the
        body must say strictly more than that.
        """
        (self.root / "agents/zeta/transfers/Z9.md").write_text("letter body")
        rec = {"gen": "Z9", "t": "retired"}
        old = "zeta Z9 retired. Lineage: agents/zeta/lineage.jsonl"
        self.assertNotEqual(self._body(rec), old)

    def test_birth_records_are_not_this_functions_business(self):
        """Birth keeps crew-state and its own body; the playbook mandates none."""
        rec = {"gen": "Z9", "t": "born"}
        self.assertNotIn("Letter:", self._body(rec))


class AnnounceWiringTests(unittest.TestCase):
    """The wiring leg. Added by argus-a167 at non-author verification, 2026-09-02.

    The seven tests above all call `_retirement_body` directly, so every one of
    them stays green when `announce()` stops calling it. Measured, not argued:
    deleting the two-line call site in `announce()` — which reverts the crew's
    retirement notice to the old boilerplate in production — left 7/7 passing.

    The commit message claimed a leg like this already existed ("stands up a
    temp studio with a stub emit-event and asserts the body reaches the real
    emit argv"). It did not; the helper was proven correct and never proven
    wired. That is the same declared-but-not-wired family the patch itself was
    written to cure, one level up, which is why it earned its own test rather
    than a note.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "agents" / "zeta" / "transfers").mkdir(parents=True)
        (self.root / "agents" / "zeta" / "transfers" / "Z9.md").write_text("letter")
        tools = self.root / "vault" / "tools"
        tools.mkdir(parents=True)
        self.argv_sink = self.root / "emit-argv.json"
        # Stub emitter: records the argv it was handed, exits 0. announce()
        # shells out to this exact path, so what lands here is what production
        # would have sent to the real emitter.
        (tools / "tropo-emit-event.py").write_text(
            "import json, sys\n"
            f"open({str(self.argv_sink)!r}, 'w').write(json.dumps(sys.argv))\n"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _announced_payload(self):
        import json as _json
        rec = {"gen": "Z9", "t": "retired", "note": "closed the vacuous class",
               "letter": "agents/zeta/transfers/Z9.md"}
        lin.announce(self.root, "zeta", rec)
        self.assertTrue(self.argv_sink.is_file(),
                        "stub emitter never ran; announce() did not shell out")
        argv = _json.loads(self.argv_sink.read_text())
        self.assertIn("--data", argv, "emit argv carried no --data")
        return _json.loads(argv[argv.index("--data") + 1])

    def test_letter_reaches_the_real_emit_argv(self):
        """Goes red if announce() stops calling _retirement_body."""
        body = self._announced_payload()["body"]
        self.assertIn("Letter: agents/zeta/transfers/Z9.md", body)

    def test_closing_note_reaches_the_real_emit_argv(self):
        """The agent's own summary must survive the trip to the emitter."""
        self.assertIn("closed the vacuous class",
                      self._announced_payload()["body"])

    def test_announced_body_is_not_the_old_boilerplate(self):
        """The production regression, asserted at the emitter and not in isolation."""
        payload = self._announced_payload()
        self.assertNotEqual(
            payload["body"], "zeta Z9 retired. Lineage: agents/zeta/lineage.jsonl")
        self.assertEqual(payload["category"], "retirement")


if __name__ == "__main__":
    unittest.main()
