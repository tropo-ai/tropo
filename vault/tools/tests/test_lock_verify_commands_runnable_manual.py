"""lock-verify-commands-runnable: a MANUAL criterion's prose is not a shell line.

RED on the pre-2026-09-03 gate: it tokenised every criterion's `verify.command`
and refused on any slash-bearing token that was not a path -- 5854773a AC6
("Mike's one-word keep/suppress recorded here") refused the v1.94 plan lock.
GREEN now: manual criteria are skipped AND the skip is emitted on the outcome.
The automated case still refuses, so removing the path check turns test 2 red.
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[3]
TOOLS = STUDIO / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load():
    spec = importlib.util.spec_from_file_location(
        "tropo_release_preflight_manual_test", TOOLS / "tropo-release-preflight.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ManualCriteriaAreNotShellLines(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.corpus = Path(tempfile.mkdtemp())

    def _ctx(self, criteria):
        return {
            "fan_in_manifest": ["fixture01"],
            "governed_index": {"fixture01": {"type": "dev-spec", "acceptance_criteria": criteria}},
            "shipped_tool_corpus": str(self.corpus),
        }

    def test_manual_prose_with_a_slash_does_not_refuse_and_the_skip_is_emitted(self):
        out = self.mod._lock_verify_commands_runnable(self._ctx([
            {"id": "AC6", "verify": {"method": "manual",
                                      "command": "at lock: Mike's one-word keep/suppress recorded here"}},
        ]))
        self.assertEqual(out.verdict, self.mod.VERDICT_PASS, out.detail)
        self.assertIn("fixture01 AC6", out.evidence.get("skipped_manual", []))
        self.assertIn("manual by declaration", out.detail)

    def test_automated_command_naming_a_missing_path_still_refuses(self):
        out = self.mod._lock_verify_commands_runnable(self._ctx([
            {"id": "AC1", "verify": {"method": "automated",
                                      "command": "python3 vault/tools/tests/does_not_exist.py"}},
        ]))
        self.assertEqual(out.verdict, self.mod.VERDICT_REFUSED)
        self.assertIn("does_not_exist.py", out.detail)

    def test_mixed_refusal_still_carries_the_skip_list(self):
        out = self.mod._lock_verify_commands_runnable(self._ctx([
            {"id": "AC1", "verify": {"method": "automated", "command": "python3 nope/missing.py"}},
            {"id": "AC6", "verify": {"method": "manual", "command": "walk keep/suppress"}},
        ]))
        self.assertEqual(out.verdict, self.mod.VERDICT_REFUSED)
        self.assertEqual(out.evidence.get("skipped_manual"), ["fixture01 AC6"])


if __name__ == "__main__":
    unittest.main()


class ACommandIsAShellLineNotAPathList(unittest.TestCase):
    """The v1.95 ignition refusal (argus-a172 + metis-g121, 2026-09-05).

    Two TRUE rows were refused: AC6's token is the literal
    `open('vault/00-index.jsonl')` — a valid `python -c`, and the file exists —
    and AC5's is `vault/pipeline-runs/<v195-run>`, a placeholder for a folder
    that cannot exist before the run is created, so it refused Mike's ignition
    every time.

    Both known-negatives below exist so the cure cannot be a blanket skip: a
    real path inside a call must still be CHECKED, and a genuinely absent path
    must still REFUSE.
    """

    def setUp(self):
        self.mod = _load()
        self.corpus = Path(tempfile.mkdtemp())
        (self.corpus / "vault").mkdir()
        (self.corpus / "vault" / "00-index.jsonl").write_text("{}\n", encoding="utf-8")

    def _ctx(self, criteria):
        return {
            "fan_in_manifest": ["fixture01"],
            "governed_index": {"fixture01": {"type": "dev-spec", "acceptance_criteria": criteria}},
            "shipped_tool_corpus": str(self.corpus),
        }

    def _run(self, command):
        return self.mod._lock_verify_commands_runnable(self._ctx([
            {"id": "AC1", "verify": {"method": "automated", "command": command}}]))

    def test_a_real_path_inside_a_call_expression_passes(self):
        out = self._run("""python3 -c "rows=[l for l in open('vault/00-index.jsonl')]" """)
        self.assertEqual(out.verdict, self.mod.VERDICT_PASS, out.detail)

    def test_an_absent_path_inside_a_call_expression_still_refuses(self):
        """The cure extracts quoted paths — so it must still JUDGE them."""
        out = self._run("""python3 -c "rows=open('vault/00-nope.jsonl')" """)
        self.assertEqual(out.verdict, self.mod.VERDICT_REFUSED, out.detail)
        self.assertIn("vault/00-nope.jsonl", out.detail)

    def test_a_placeholder_token_is_skipped_and_the_skip_is_emitted(self):
        out = self._run("python3 tool.py --run-dir vault/pipeline-runs/<v195-run>")
        self.assertEqual(out.verdict, self.mod.VERDICT_PASS, out.detail)
        self.assertIn("placeholder", out.detail)
        self.assertTrue(any("<v195-run>" in row
                            for row in out.evidence.get("skipped_placeholders", [])),
                        "the skip was not emitted: a gate that evaluated nothing "
                        "must not read as a gate that passed")

    def test_a_placeholder_does_not_excuse_the_rest_of_the_command(self):
        """A blanket skip would pass this. The absent sibling path must refuse."""
        out = self._run("python3 vault/tools/does_not_exist.py --run-dir runs/<v195-run>")
        self.assertEqual(out.verdict, self.mod.VERDICT_REFUSED, out.detail)
        self.assertIn("does_not_exist.py", out.detail)


class ADeclaredTestIdMustResolve(unittest.TestCase):
    """Plan-owner ruling, metis-g121 2026-09-05, verbatim "REFUSE".

    An unresolvable `python3 -m unittest` id is the same defect as a missing
    path in another notation, and whether an id resolves is mechanically
    decidable — which is where Mike's 09-01 rule allows a refusal. Her harm, in
    her words: a spec whose declared verification surface does not exist can be
    closed and locked carrying a criterion nobody can ever run, and the plan's
    Definition of Done becomes a false claim at fire.

    Measured before landing: 37 declared ids across every locked dev-spec, 5
    unresolvable — all of them Spine A AC4's, an AC that was simply unbuilt. The
    gate reported PASS the whole time.
    """

    def setUp(self):
        self.mod = _load()
        self.corpus = Path(tempfile.mkdtemp())
        pkg = self.corpus / "vault" / "tools" / "tests"
        pkg.mkdir(parents=True)
        (pkg / "test_fixture_suite.py").write_text(
            "import unittest\n\n\n"
            "class Real(unittest.TestCase):\n"
            "    def test_present(self):\n        pass\n\n\n"
            "class Standalone:\n"
            "    def test_here(self):\n        pass\n",
            encoding="utf-8")

    def _run(self, command):
        return self.mod._lock_verify_commands_runnable({
            "fan_in_manifest": ["fixture01"],
            "governed_index": {"fixture01": {"type": "dev-spec", "acceptance_criteria": [
                {"id": "AC1", "verify": {"method": "automated", "command": command}}]}},
            "shipped_tool_corpus": str(self.corpus),
        })

    _BASE = "python3 -m unittest vault.tools.tests.test_fixture_suite."

    def test_a_resolvable_id_passes(self):
        out = self._run(self._BASE + "Real.test_present")
        self.assertEqual(out.verdict, self.mod.VERDICT_PASS, out.detail)

    def test_a_missing_class_refuses(self):
        out = self._run(self._BASE + "Founder.test_present")
        self.assertEqual(out.verdict, self.mod.VERDICT_REFUSED, out.detail)
        self.assertIn("Founder", out.detail)

    def test_a_missing_method_on_a_baseless_class_refuses(self):
        out = self._run(self._BASE + "Standalone.test_absent")
        self.assertEqual(out.verdict, self.mod.VERDICT_REFUSED, out.detail)
        self.assertIn("test_absent", out.detail)

    def test_a_missing_module_refuses(self):
        out = self._run("python3 -m unittest vault.tools.tests.test_no_such_suite.Real.test_present")
        self.assertEqual(out.verdict, self.mod.VERDICT_REFUSED, out.detail)

    def test_an_inherited_member_is_not_a_refusal(self):
        """A TestCase subclass may declare none of the methods it runs, so an
        unresolved name on a class WITH bases is not decidably absent — and this
        gate refuses only what it can decide."""
        out = self._run(self._BASE + "Real.test_inherited_from_somewhere")
        self.assertEqual(out.verdict, self.mod.VERDICT_PASS, out.detail)

    def test_prose_after_the_command_is_not_a_test_id(self):
        """Spine B AC5's real command ends "; then on the v1.95 run: ...".
        `v1.95` has a dot and no slash; reading it as an id refused a true row
        in my own first scan of the corpus."""
        out = self._run(self._BASE + "Real.test_present; then on the v1.95 run: see the fixture")
        self.assertEqual(out.verdict, self.mod.VERDICT_PASS, out.detail)
