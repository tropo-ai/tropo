"""v1.95 Spine A AC7 row (a): the build's doc-currency gate reaches the uid arm
(talos-t62 e7c716dd2) by passing the SOURCE Studio's governed set -- the one
argument the tool's own main() passes and the gate did not (argus-a172,
2026-09-06). Two arms: a governed uid a shipped playbook names as an instruction
and the box lacks is exactly one problem; an empty governed set is itself a
problem, never a silent pass. Remove the wiring and the first test goes red."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def _bg():
    spec = importlib.util.spec_from_file_location("bg_uid_arm", TOOLS / "lib" / "build_guards.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


class DocCurrencyGateReachesTheUidArm(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dc-uid-arm-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # SOURCE studio: the real tool (the gate imports it from source_tree) + an
        # index that governs one uid.
        self.src = self.tmp / "src"
        (self.src / "vault" / "tools").mkdir(parents=True)
        shutil.copy(TOOLS / "tropo-check-doc-currency.py", self.src / "vault" / "tools" / "tropo-check-doc-currency.py")
        (self.src / "vault" / "00-index.jsonl").write_text(
            json.dumps({"uid": "abcd1234", "type": "playbook", "path": "vault/playbooks/abcd1234.md", "title": "governed"}) + "\n",
            encoding="utf-8")
        # BOX: one shipped playbook that names the governed uid as an instruction,
        # and does not carry it.
        self.box = self.tmp / "box"
        (self.box / "vault" / "playbooks").mkdir(parents=True)
        (self.box / "vault" / "playbooks" / "11112222.md").write_text(
            "---\nuid: 11112222\ntype: playbook\n---\n# walk\n\n1. Run the playbook `abcd1234` next.\n", encoding="utf-8")

    def test_a_governed_uid_the_box_lacks_is_exactly_one_problem(self):
        probs = _bg().doc_currency_problems(str(self.src), self.box)
        uid_probs = [p for p in probs if "abcd1234" in p]
        self.assertEqual(len(uid_probs), 1, probs)
        self.assertIn("governed by the source, absent from the box", uid_probs[0])

    def test_a_governed_uid_the_box_carries_is_not_a_problem(self):
        (self.box / "vault" / "playbooks" / "abcd1234.md").write_text("---\nuid: abcd1234\n---\n# here\n", encoding="utf-8")
        probs = _bg().doc_currency_problems(str(self.src), self.box)
        self.assertEqual([p for p in probs if "abcd1234" in p], [], probs)

    def test_an_empty_governed_set_is_a_problem_not_a_pass(self):
        (self.src / "vault" / "00-index.jsonl").unlink()
        probs = _bg().doc_currency_problems(str(self.src), self.box)
        self.assertTrue(any("uid arm evaluated nothing" in p for p in probs), probs)


if __name__ == "__main__":
    unittest.main()
