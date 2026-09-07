#!/usr/bin/env python3
"""The spec lock appends its uid to the release plan's dev_spec_uids.

f01592dca86d, found by metis-g118 counting the v1.94 fan-in. The plan 301dce9d
carried `dev_spec_uids: []   # fills at spec-lock` and FOURTEEN specs locked
against it while the list stayed empty, because tropo-lock-dev-spec.py contained
no reference to the field. tropo-lock-release-plan.py refuses an empty list by
design, so the plan could not have locked at any count of done rows — every
"thirteen" on the board came from letters, and the plan's own field never said
anything. The plan owner populated all fourteen by hand.

AC1 append, AC2 idempotent and order-preserving, AC3 the inline-empty shape.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("lock_dev_spec", TOOLS / "tropo-lock-dev-spec.py")
lock = importlib.util.module_from_spec(_spec)
sys.modules["lock_dev_spec"] = lock
_spec.loader.exec_module(lock)


def _plan(body: str) -> str:
    return "---\nuid: 'planaaaa'\ntype: release-plan\n%s\nstatus: specify\n---\n\n# Plan\n" % body


class TheAppendIsBlockAware(unittest.TestCase):
    """AC1 + AC3. The naive `^key:` match on a block value produced TWO
    dev_spec_uids keys and YAML silently kept the last — the plan-lock's own
    NO-GO item 5, and the reason this is line-level and block-aware."""

    def _keys(self, text):
        return [l for l in text.splitlines() if l.startswith("dev_spec_uids")]

    def test_inline_empty_with_a_comment_becomes_a_block_and_keeps_the_comment(self):
        """The literal shape v1.94 carried."""
        text, changed = lock.append_uid_to_plan_list(
            _plan("dev_spec_uids: []   # fills at spec-lock, per stream"), "aaaaaaaa")
        self.assertTrue(changed)
        self.assertEqual(len(self._keys(text)), 1, "a second key was written")
        self.assertIn("  - aaaaaaaa", text)
        self.assertIn("fills at spec-lock", text, "the owner's note was dropped silently")

    def test_inline_empty_without_a_comment(self):
        text, changed = lock.append_uid_to_plan_list(_plan("dev_spec_uids: []"), "aaaaaaaa")
        self.assertTrue(changed)
        self.assertEqual(len(self._keys(text)), 1)
        self.assertIn("  - aaaaaaaa", text)

    def test_a_bare_key_gains_its_first_entry(self):
        text, changed = lock.append_uid_to_plan_list(_plan("dev_spec_uids:"), "aaaaaaaa")
        self.assertTrue(changed)
        self.assertIn("  - aaaaaaaa", text)

    def test_exactly_one_key_and_one_entry_after_a_single_append(self):
        text, _ = lock.append_uid_to_plan_list(_plan("dev_spec_uids: []"), "aaaaaaaa")
        self.assertEqual(len(self._keys(text)), 1)
        self.assertEqual(text.count("  - aaaaaaaa"), 1)

    def test_two_keys_refuse_rather_than_guess(self):
        doubled = _plan("dev_spec_uids: []\ndev_spec_uids:\n  - bbbbbbbb")
        with self.assertRaisesRegex(ValueError, "two dev_spec_uids keys"):
            lock.append_uid_to_plan_list(doubled, "aaaaaaaa")

    def test_the_member_list_as_the_last_frontmatter_key_stays_inside_the_frontmatter(self):
        """The shape no fixture had: `dev_spec_uids: []` immediately before `---`.

        The entry pattern matched the closer `---` as an entry named "--", so
        the uid was inserted AFTER the closer, into the body. YAML then read the
        list as null and the plan lock still refused "lists no dev_spec_uids".
        Found by the AC4 test calling the plan lock instead of reading the text.
        """
        plan = "---\nuid: 'planaaaa'\ntype: release-plan\nstatus: specify\n" \
               "dev_spec_uids: []   # fills at spec-lock\n---\n\n# Plan\n"
        text, changed = lock.append_uid_to_plan_list(plan, "aaaaaaaa")
        self.assertTrue(changed)
        head, body = text.split("\n---\n", 1)[0], text.split("\n---\n", 1)[1]
        self.assertIn("  - aaaaaaaa", head, "the entry landed outside the frontmatter")
        self.assertNotIn("aaaaaaaa", body)
        self.assertEqual(lock.parse_frontmatter(text).get("dev_spec_uids"), ["aaaaaaaa"],
                         "YAML does not read the appended member")

    def test_a_plan_without_the_field_is_left_alone(self):
        text, changed = lock.append_uid_to_plan_list(_plan("owner: metis"), "aaaaaaaa")
        self.assertFalse(changed)
        self.assertNotIn("aaaaaaaa", text)


class TheAppendIsIdempotentAndOrdered(unittest.TestCase):
    """AC2."""

    def test_idempotent_against_an_entry_carrying_a_trailing_comment(self):
        """Idempotence has to see the uid THROUGH the comment, or a re-lock
        silently doubles a member of the fan-in."""
        plan = _plan("dev_spec_uids:\n  - aaaaaaaa   # Spine A, already locked")
        text, changed = lock.append_uid_to_plan_list(plan, "aaaaaaaa")
        self.assertFalse(changed, "a commented entry was invisible to idempotence")
        self.assertEqual(text, plan)

    def test_locking_the_same_spec_twice_leaves_one_entry(self):
        once, _ = lock.append_uid_to_plan_list(_plan("dev_spec_uids: []"), "aaaaaaaa")
        twice, changed = lock.append_uid_to_plan_list(once, "aaaaaaaa")
        self.assertFalse(changed, "the second lock appended again")
        self.assertEqual(twice, once)
        self.assertEqual(twice.count("  - aaaaaaaa"), 1)

    def test_a_second_spec_appends_after_the_first(self):
        one, _ = lock.append_uid_to_plan_list(_plan("dev_spec_uids: []"), "aaaaaaaa")
        two, _ = lock.append_uid_to_plan_list(one, "bbbbbbbb")
        entries = [l.strip() for l in two.splitlines() if l.strip().startswith("- ")]
        self.assertEqual(entries, ["- aaaaaaaa", "- bbbbbbbb"], "fan-in order lost")

    def test_the_existing_v195_shape_round_trips(self):
        """The plan on main: a commented key AND entries with trailing comments.

        The trailing comments are the point. My first entry pattern required the
        line to end at the uid, matched none of the real entries, and therefore
        appended a DUPLICATE of a uid already present and inserted the new one
        FIRST. The synthetic fixture agreed with itself; the live plan did not.
        """
        plan = _plan("dev_spec_uids:   # the ordered members the lock reads\n"
                     "  - f015de6b3a18   # Spine A, identity and arrival\n"
                     "  - f015997f8d8e   # Spine B, the compiler loop")
        text, changed = lock.append_uid_to_plan_list(plan, "af6c53df")
        self.assertTrue(changed)
        # compare UIDS, not raw lines: the real entries carry trailing comments
        uids = [l.strip().lstrip("- ").split()[0]
                for l in text.splitlines() if l.strip().startswith("- ")]
        self.assertEqual(uids, ["f015de6b3a18", "f015997f8d8e", "af6c53df"])
        self.assertEqual(len([l for l in text.splitlines()
                              if l.startswith("dev_spec_uids")]), 1)


class ThePlanBindingIsTargetRelease(unittest.TestCase):
    """Which binding is used, said out loud because the task asked.

    A dev-spec carries no pointer to its plan: `member_of` on both is the
    dev-pipeline template. What binds them is the spec's `target_release`
    against the plan's `release_version`.
    """

    def setUp(self):
        self.files = Path(tempfile.mkdtemp(prefix="plan-binding-"))

    def _write(self, name, fm):
        (self.files / name).write_text("---\n%s\n---\n\n# x\n" % fm, encoding="utf-8")

    def test_exactly_one_live_plan_resolves(self):
        self._write("p1.md", "uid: p1\ntype: release-plan\nrelease_version: '1.95.0'\nstatus: specify")
        path, why = lock.resolve_plan_for_spec({"target_release": "1.95.0"}, self.files)
        self.assertIsNotNone(path, why)
        self.assertEqual(path.name, "p1.md")

    def test_a_done_plan_is_not_a_candidate(self):
        self._write("p1.md", "uid: p1\ntype: release-plan\nrelease_version: '1.94.0'\nstatus: done")
        path, why = lock.resolve_plan_for_spec({"target_release": "1.94.0"}, self.files)
        self.assertIsNone(path)
        self.assertIn("no live release-plan", why)

    def test_two_live_plans_refuse_rather_than_guess(self):
        for n in ("p1.md", "p2.md"):
            self._write(n, "uid: %s\ntype: release-plan\nrelease_version: '1.95.0'\nstatus: specify" % n)
        path, why = lock.resolve_plan_for_spec({"target_release": "1.95.0"}, self.files)
        self.assertIsNone(path)
        self.assertIn("refusing to guess", why)

    def test_a_spec_with_no_target_release_is_not_an_error(self):
        path, why = lock.resolve_plan_for_spec({}, self.files)
        self.assertIsNone(path)
        self.assertIn("no target_release", why)


if __name__ == "__main__":
    unittest.main()
