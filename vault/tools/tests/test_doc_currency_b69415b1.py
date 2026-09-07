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
            if doc_currency.is_generated_at_boot(ref, relative_to=rel):
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


class UidsAreReferencesToo(unittest.TestCase):
    """v1.95 Spine B (f015997f8d8e committed_substrate, AMENDED): the tool
    resolves uids as well as paths against --target, so Spine A's reachability
    row (a) can be a Gate verifier over the assembled box.

    The decidability problem this class exists around: a shipped document is
    full of hex that is NOT a uid — git short shas most of all — and flagging
    every unresolved 8-hex token would report the documentation working as the
    documentation failing, the exact error this tool's docstring says it was
    built to avoid. So a token is only checked when the SOURCE Studio's index
    can name it as a governed entry.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.box_dir = self.root / "box"
        (self.box_dir / "vault" / "files").mkdir(parents=True)
        # the box SHIPS one governed entry, under its locked slug name
        (self.box_dir / "vault" / "files"
         / "a-locked-spec-aaaaaaaa.md").write_text("shipped\n", encoding="utf-8")
        # the SOURCE studio knows three uids are governed
        (self.root / "vault").mkdir(parents=True, exist_ok=True)
        (self.root / "vault" / "00-index.jsonl").write_text(
            '{"uid": "aaaaaaaa", "type": "note"}\n'
            '{"uid": "bbbbbbbb", "type": "note"}\n'
            '{"uid": "f015aaaabbbb", "type": "note"}\n', encoding="utf-8")
        self.known = doc_currency.governed_uids(self.root)
        self.box = doc_currency.Box(self.box_dir)

    def _forms(self, body):
        out = []
        for lineno, uid, form in doc_currency.scan_uids(body, self.known):
            out.append((uid, form, self.box.has_uid(uid)))
        return out

    def test_the_source_index_is_what_makes_a_token_a_uid(self):
        self.assertEqual(len(self.known), 3)

    def test_a_uid_the_box_ships_resolves_even_under_a_slug_name(self):
        """The lock gesture re-slugs governed files to <slug>-<uid>.md, so
        vault/files/<uid>.md is not the only shape a shipped entry takes."""
        self.assertEqual(self._forms("Read `aaaaaaaa` before you start."),
                         [("aaaaaaaa", "prose", True)])

    def test_a_governed_uid_the_box_does_not_ship_is_found_and_unresolved(self):
        found = self._forms("1. Open [the record](bbbbbbbb) first.")
        self.assertEqual(found, [("bbbbbbbb", "instruction", False)])

    def test_a_git_sha_is_not_a_uid_and_is_never_reported(self):
        """The false-positive arm. Without the source-index gate this line
        alone would report a dead reference in every shipped document."""
        self.assertEqual(self._forms("Landed at 26d83d25 on main."), [])

    def test_a_composite_12_hex_uid_is_recognised(self):
        found = self._forms("1. See [the spec](f015aaaabbbb).")
        self.assertEqual(found, [("f015aaaabbbb", "instruction", False)])

    def test_a_retirement_notice_naming_a_uid_is_not_a_defect(self):
        found = self._forms("`bbbbbbbb` was retired at v1.61; do not use it.")
        self.assertEqual(found, [("bbbbbbbb", "retired", False)])

    def test_a_longer_hex_run_is_not_sliced_into_a_uid(self):
        self.assertEqual(self._forms("digest aaaaaaaabbbbbbbbccccccccdddddddd"), [])


class AVariableRootedReferenceIsAParameter(unittest.TestCase):
    """metis-g121 + argus-a172, 2026-09-05, from the v1.94 box run.

    `$GEN/audience-policy.json` and `$STUDIO_ROOT/vault/tools/tropo-mint-id.py`
    are runbook PARAMETERS: the gate cannot decide them and reporting them as
    dead paths is the false-positive class this tool's docstring exists to
    avoid. Skipped AND emitted, the same shape as the <...> placeholder skip on
    lock-verify-commands-runnable — a skip that does not announce itself turns a
    gate that evaluated nothing into a gate that passed.
    """

    def _forms(self, body):
        return [(ref, form) for _n, ref, form in doc_currency.scan_text(body)]

    def test_a_dollar_rooted_reference_is_parameterised(self):
        self.assertEqual(self._forms("1. Read `$GEN/audience-policy.json` first."),
                         [("GEN/audience-policy.json", doc_currency.PARAMETERISED)])

    def test_a_braced_variable_root_yields_no_reference_at_all(self):
        """`${STUDIO_ROOT}/x` needs no skip: PATH_RE's lookbehind already
        refuses a path preceded by "/", so nothing is reported. Pinned because I
        wrote a brace branch for it first and this test proved the branch dead —
        the code is gone and this records why it is not needed."""
        self.assertEqual(self._forms("1. Read `${STUDIO_ROOT}/vault/tools/x.py`."), [])

    def test_an_out_of_studio_staging_root_is_parameterised(self):
        self.assertEqual(self._forms("1. Copy `STAGING/box/vault/x.md` across."),
                         [("STAGING/box/vault/x.md", doc_currency.PARAMETERISED)])

    def test_an_ordinary_path_is_still_judged(self):
        """The false-negative arm: the skip must not swallow real references."""
        self.assertEqual(self._forms("1. Open `vault/tools/tropo-mint-id.py`."),
                         [("vault/tools/tropo-mint-id.py", doc_currency.INSTRUCTION)])

    def test_a_dollar_elsewhere_in_the_line_does_not_excuse_a_real_path(self):
        """Only the reference's own ROOT counts, not a $ anywhere on the line."""
        forms = self._forms("1. With $VERSION set, open `vault/tools/x.py`.")
        self.assertEqual(forms, [("vault/tools/x.py", doc_currency.INSTRUCTION)])


class APathTheFileCreatesIsNotDead(unittest.TestCase):
    """A runbook READS a path an earlier step of the same runbook created.

    `.tropo-studio/join-bundles/step5-principals.json` is written by the join
    ceremony at step 5 and read at 6 and 7; a fresh box carries none of them by
    construction. No verb heuristic decides this — most such lines are open()
    READS and the creator is usually a TOOL the playbook runs, not a literal
    write in its text — so the author declares it, once per path, visibly in the
    file, rather than the tool growing a skip list (metis-g121: never widen the
    skip list).
    """

    def _forms(self, body):
        return [(ref, form) for _n, ref, form in doc_currency.scan_text(body)]

    DECL = "<!-- doc-currency: creates .tropo-studio/join-bundles/step5.json -->\n"

    def test_a_declared_path_is_created_not_dead(self):
        body = self.DECL + '1. `json.load(open(".tropo-studio/join-bundles/step5.json"))`\n'
        self.assertEqual(self._forms(body),
                         [(".tropo-studio/join-bundles/step5.json", doc_currency.CREATED)])

    def test_the_declaration_covers_every_later_reference_in_that_file(self):
        body = self.DECL + ('1. write `.tropo-studio/join-bundles/step5.json`\n'
                            '2. read `.tropo-studio/join-bundles/step5.json`\n')
        self.assertEqual([f for _r, f in self._forms(body)],
                         [doc_currency.CREATED, doc_currency.CREATED])

    def test_an_undeclared_path_in_the_same_file_is_still_dead(self):
        """The declaration is per PATH, not a blanket amnesty for the file."""
        body = self.DECL + '1. Open `vault/tools/does-not-exist.py`\n'
        self.assertEqual(self._forms(body),
                         [("vault/tools/does-not-exist.py", doc_currency.INSTRUCTION)])

    def test_a_declaration_does_not_travel_to_another_file(self):
        """Scoped to the file that declares it: scan_text sees one file's text."""
        other = '1. Open `.tropo-studio/join-bundles/step5.json`\n'
        self.assertEqual(self._forms(other),
                         [(".tropo-studio/join-bundles/step5.json", doc_currency.INSTRUCTION)])
