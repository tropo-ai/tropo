#!/usr/bin/env python3
"""The per-studio boot derivations have ONE home, and a link to them is not dead.

v1.95 candidate #1 (2026-09-06) was refused by build-doc-currency on
`vault/playbooks/99341618.md:58`, which links `.tropo/boot-fast-path.md` and
`.tropo/boot-digest.md`. The build excludes both by declaration
(PER_STUDIO_BOOT_DERIVATIONS); the doc-currency tool's own skip list never
learned them, and the shared guard carried a third raw copy of the skip. Every
rehearsal box read green because the rehearsal builder never excluded them.
Now: the tuple lives in lib/package_state_exclusions, the build re-exports it,
the tool matches on the normalised box path, and the guard calls the tool.

RED without each half (G122's ruling for candidate #2, optional in-window):
  - remove the lib import from the tool -> the derivation link reads dead;
  - match on the raw ref -> the `../../` form reads dead;
  - the build carrying its own literal tuple -> the identity test fails.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_doc_currency_boot_derivations_one_home
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
STUDIO = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))

from lib import package_state_exclusions as pse  # noqa: E402
from lib import build_guards  # noqa: E402


def _load(name, alias):
    spec = importlib.util.spec_from_file_location(alias, TOOLS / name)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


tool = _load("tropo-check-doc-currency.py", "doc_currency_one_home")


class OneHome(unittest.TestCase):

    def test_the_tool_reads_the_librarys_object(self) -> None:
        self.assertIs(tool.PER_STUDIO_BOOT_DERIVATIONS, pse.PER_STUDIO_BOOT_DERIVATIONS)
        self.assertEqual(set(pse.PER_STUDIO_BOOT_DERIVATIONS),
                         {".tropo/boot-digest.md", ".tropo/boot-fast-path.md"})

    def test_the_build_carries_no_private_copy(self) -> None:
        source = (TOOLS / "tropo-build-release.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"PER_STUDIO_BOOT_DERIVATIONS\s*=\s*\(\s*\n\s*['\"]\.tropo/boot",
                            "the build declares the tuple privately again")
        self.assertIn("PER_STUDIO_BOOT_DERIVATIONS = ", source)
        self.assertRegex(source, r"PER_STUDIO_BOOT_DERIVATIONS\s*=\s*\w+\.PER_STUDIO_BOOT_DERIVATIONS")


class NormalisedSkip(unittest.TestCase):

    def test_a_root_relative_derivation_is_generated(self) -> None:
        for rel in pse.PER_STUDIO_BOOT_DERIVATIONS:
            self.assertTrue(tool.is_generated_at_boot(rel, "vault/playbooks/x.md"), rel)

    def test_the_dotdot_form_from_a_playbook_is_generated(self) -> None:
        """The exact shape of 99341618.md:58."""
        self.assertTrue(tool.is_generated_at_boot("../../.tropo/boot-fast-path.md", "vault/playbooks/99341618.md"))
        self.assertTrue(tool.is_generated_at_boot("../../.tropo/boot-digest.md", "vault/playbooks/99341618.md"))
        self.assertEqual(tool.normalised_ref("../../.tropo/boot-fast-path.md", "vault/playbooks/99341618.md"),
                         ".tropo/boot-fast-path.md")

    def test_the_kernel_pointer_form_is_generated(self) -> None:
        """`.tropo/playbooks/agent-activation.playbook.md` links `../boot-fast-path.md`."""
        self.assertTrue(tool.is_generated_at_boot("../boot-fast-path.md", ".tropo/playbooks/agent-activation.playbook.md"))

    def test_the_index_family_still_skips(self) -> None:
        self.assertTrue(tool.is_generated_at_boot("vault/00-index.jsonl", "vault/playbooks/x.md"))

    def test_an_unlisted_absent_path_is_not_generated(self) -> None:
        """The control: the skip is a list, not a wildcard."""
        self.assertFalse(tool.is_generated_at_boot("../../.tropo/boot-nothing.md", "vault/playbooks/x.md"))
        self.assertFalse(tool.is_generated_at_boot(".tropo/boot-fast-path.history.md", "vault/playbooks/x.md"))


class TheGuardOverAScratchBox(unittest.TestCase):
    """build_guards.doc_currency_problems on a box that LACKS the derivations,
    as the release box does, must not call a link to them a problem, and must
    still call an unlisted absent path a problem."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.box = Path(self.tmp.name) / "box"
        (self.box / "vault" / "playbooks").mkdir(parents=True)
        (self.box / ".tropo" / "playbooks").mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)

    def _guard(self, body: str):
        (self.box / "vault" / "playbooks" / "99341618.md").write_text(body, encoding="utf-8")
        return build_guards.doc_currency_problems(str(STUDIO), self.box)

    def test_a_link_to_each_derivation_is_not_a_problem(self) -> None:
        problems = self._guard(
            "**Established-agent path:** read [`.tropo/boot-fast-path.md`](../../.tropo/boot-fast-path.md) "
            "plus [`.tropo/boot-digest.md`](../../.tropo/boot-digest.md) instead of this full body.\n")
        dead = [p for p in problems if "boot-fast-path" in p or "boot-digest" in p]
        self.assertEqual(dead, [], problems)

    def test_an_unlisted_absent_path_is_still_a_problem(self) -> None:
        problems = self._guard("1. Read `.tropo/playbooks/does-not-ship.playbook.md` before Group 0.\n")
        self.assertTrue(any("does-not-ship" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
