#!/usr/bin/env python3
"""The currency check has to be able to say the box is wrong — and to stay quiet
when it is right.

Finding b69415b1. Every clean number this instrument produced before these tests
existed was wrong, in five different ways, and each one looked tidy:

  1. a keyword count called retirement NOTICES defects (the documentation
     working, scored as the documentation failing)
  2. `lstrip("./")` strips CHARACTERS, so every `.tropo/...` path read ABSENT
  3. a loose pattern matched `agents/sa/sa.cold` out of `sa.cold-boot`
  4. an extension-blind pattern reported `docProps/core.xml` from a prose example
  5. root-only resolution called four SHIPPED concierge paths missing

None of those failures were visible in the output. They were visible only by
checking a suspicious row against the filesystem. So the bar here is A143's:
a negative test must change verdict when the mechanism it names is removed.
Each red case below has a green twin differing in exactly one dimension.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOL = STUDIO_ROOT / "vault" / "tools" / "tropo-check-doc-currency.py"

_spec = importlib.util.spec_from_file_location("doc_currency", TOOL)
doc_currency = importlib.util.module_from_spec(_spec)
sys.modules["doc_currency"] = doc_currency
_spec.loader.exec_module(doc_currency)


class DocCurrencyBox(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "vault" / "playbooks").mkdir(parents=True)
        (self.root / ".tropo" / "playbooks" / "concierge-paths").mkdir(parents=True)
        (self.root / "channels").mkdir()
        # Substrate that DOES exist in this fixture box.
        (self.root / "channels" / "CAPSULE.md").write_text("live\n")
        (self.root / ".tropo" / "version.md").write_text("1.0.0\n")
        (self.root / ".tropo" / "playbooks" / "concierge-paths"
         / "start-a-project.playbook.md").write_text("live\n")
        self.addCleanup(self.tmp.cleanup)

    def run_check(self, body: str, name="vault/playbooks/fixture.md"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        box = doc_currency.Box(self.root)
        dead, prose, retired, generated = [], [], 0, 0
        rel = name
        for lineno, ref, form in doc_currency.scan_text(body):
            if box.exists(ref, relative_to=rel):
                continue
            if ref in doc_currency.GENERATED_AT_BOOT:
                generated += 1
            elif form == doc_currency.RETIRED:
                retired += 1
            elif form == doc_currency.INSTRUCTION:
                dead.append(ref)
            else:
                prose.append(ref)
        return {"dead": dead, "prose": prose,
                "retired": retired, "generated": generated}

    # --- the instrument must go RED ------------------------------------

    def test_dead_instruction_in_step_is_reported(self):
        r = self.run_check("1. Post a bulletin to `channels/ops.md` when done.\n")
        self.assertEqual(r["dead"], ["channels/ops.md"])

    def test_dead_instruction_in_fenced_block_is_reported(self):
        r = self.run_check("```\ncat channels/ops.md\n```\n")
        self.assertEqual(r["dead"], ["channels/ops.md"])

    def test_absent_path_not_on_the_generated_list_still_fails(self):
        """Fail-closed: the generated allowlist must not become a catch-all."""
        r = self.run_check("1. Read `vault/00-totally-made-up.jsonl` first.\n")
        self.assertEqual(r["dead"], ["vault/00-totally-made-up.jsonl"])

    # --- and the GREEN twins, each differing in one dimension -----------

    def test_live_instruction_is_silent(self):
        """Same sentence as the red case; only the path's existence differs."""
        r = self.run_check("1. Post a bulletin to `channels/CAPSULE.md` when done.\n")
        self.assertEqual(r["dead"], [])

    def test_retirement_notice_is_not_a_defect(self):
        """Documentation correctly saying a path is gone is the doc WORKING."""
        r = self.run_check(
            "1. *(v1.61: `channels/ops.md` is retired per Rule 13; "
            "use emit-event instead.)*\n")
        self.assertEqual(r["dead"], [])
        self.assertEqual(r["retired"], 1)

    def test_dotfile_path_that_exists_is_silent(self):
        """Guards defect 2: lstrip('./') made every dotfile path read absent."""
        r = self.run_check("1. Read `.tropo/version.md` for the version.\n")
        self.assertEqual(r["dead"], [])

    def test_sibling_relative_reference_resolves(self):
        """Guards defect 5: resolution relative to the referencing file."""
        r = self.run_check(
            "1. Route to `concierge-paths/start-a-project.playbook.md`.\n",
            name=".tropo/playbooks/agent-boot.playbook.md")
        self.assertEqual(r["dead"], [])

    def test_hyphenated_dotted_name_is_not_split(self):
        """Guards defect 3: 'agents/sa/sa.cold-boot' is not 'agents/sa/sa.cold'."""
        r = self.run_check("1. Commission `agents/sa/sa.cold-boot` for this.\n")
        self.assertEqual(r["dead"], [])

    def test_foreign_extension_example_is_not_a_finding(self):
        """Guards defect 4: prose naming a .docx internal path is not an instruction."""
        r = self.run_check("1. A .docx stores metadata in `docProps/core.xml`.\n")
        self.assertEqual(r["dead"], [])

    def test_generated_artifact_is_not_a_finding(self):
        r = self.run_check("1. Search `vault/00-index.jsonl` for the entry.\n")
        self.assertEqual(r["dead"], [])
        self.assertEqual(r["generated"], 1)


if __name__ == "__main__":
    unittest.main()
