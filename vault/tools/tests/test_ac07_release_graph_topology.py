"""AC7 topology: Verify declares four instruments and the graph resolves them.

The preflight's finding, verified before it was fixed: Verify named four
instruments in prose and had two children, the package step was pointed at by
its predecessor but claimed by nobody, and the harness jumped straight to
Publish. Graph resolution follows `children`, so a node that is pointed at but
unclaimed is simply never walked -- the pipeline described a process it did not
perform.

These assertions are about the resolved graph rather than about prose, because
prose is what was already right.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

FILES = Path(__file__).resolve().parents[2] / "files"
if not FILES.is_dir():  # running from a copied studio
    FILES = Path(__file__).resolve().parents[3] / "vault" / "files"

RELEASE_PIPELINE = "634913c2"
ASSEMBLE = "471dd767"
VERIFY = "8a4f802b"
PUBLISH = "8e03f8d6"
PACKAGE = "8654900a"
DEAD_DEPLOY = "3a7dbdda"

#: A148's preflight §3, in declaration order.
FOUR_INSTRUMENTS = ["4262d5fa", "a0f2bea8", "bc6b17ec", "c6b61fb9"]


def frontmatter(uid: str) -> dict:
    text = (FILES / f"{uid}.md").read_text(encoding="utf-8")
    return yaml.safe_load(text[3:text.find("\n---", 3)]) or {}


def member_of(uid: str) -> list:
    return [r.get("uid") for r in (frontmatter(uid).get("relationships") or [])
            if r.get("rel") == "member_of"]


def children(uid: str) -> list:
    return [str(c) for c in (frontmatter(uid).get("children") or [])]


class VerifyResolvesFourInstruments(unittest.TestCase):

    def test_verify_claims_all_four_in_declared_order(self):
        self.assertEqual(
            [c for c in children(VERIFY) if c in FOUR_INSTRUMENTS],
            FOUR_INSTRUMENTS,
            "Verify does not claim its four instruments in the declared "
            "order; resolution follows children, so an unclaimed instrument "
            "never runs no matter what the prose says",
        )

    def test_each_instrument_is_a_member_of_verify(self):
        for uid in FOUR_INSTRUMENTS:
            with self.subTest(instrument=uid):
                self.assertEqual(member_of(uid), [VERIFY])

    def test_the_verify_chain_is_linear_and_ends_at_publish(self):
        expected = FOUR_INSTRUMENTS + [PUBLISH]
        for current, following in zip(expected, expected[1:]):
            with self.subTest(step=current):
                self.assertEqual(
                    [str(n) for n in (frontmatter(current).get("next_steps") or [])],
                    [following],
                    f"{current} does not hand to {following}",
                )

    def test_the_harness_no_longer_bypasses_into_publish(self):
        """The specific bypass: a0f2bea8 jumped to Publish (3dd817cb).

        With it in place the last two instruments were unreachable even once
        they were filed under Verify, so re-homing alone would have looked
        correct and changed nothing.
        """
        self.assertNotIn(
            "3dd817cb",
            [str(n) for n in (frontmatter("a0f2bea8").get("next_steps") or [])],
        )

    def test_dependencies_agree_with_the_chain(self):
        expected = FOUR_INSTRUMENTS
        for previous, current in zip(expected, expected[1:]):
            with self.subTest(step=current):
                self.assertIn(
                    previous,
                    [str(d) for d in (frontmatter(current).get("depends_on_steps") or [])],
                    f"{current} does not depend on {previous}, so the order is "
                    f"advisory rather than enforced",
                )


class AssembleOwnsThePackageStep(unittest.TestCase):

    def test_assemble_claims_the_package_step(self):
        self.assertIn(
            PACKAGE, children(ASSEMBLE),
            "nothing claims the step that produces the package, so a release "
            "run never walks it",
        )

    def test_the_stage_boundary_is_the_declared_one(self):
        self.assertEqual(
            [str(n) for n in (frontmatter("2e9b1db7").get("next_steps") or [])],
            [PACKAGE])
        self.assertEqual(
            [str(n) for n in (frontmatter(PACKAGE).get("next_steps") or [])],
            [VERIFY])
        self.assertEqual(member_of(PACKAGE), [ASSEMBLE])


class TheDeadDeployStageClaimsNoReleaseNode(unittest.TestCase):

    def test_it_no_longer_claims_the_relocated_nodes(self):
        """A dead stage claiming live nodes is a contradiction, not a nit.

        3a7dbdda is unreachable — it declares member_of cd1fcd25 and the dev
        root does not list it — so nothing walks it. But leaving it claiming
        nodes that now live on the release graph is exactly the half-moved
        state that let these three sit in the wrong drawer for a whole stage.
        """
        stale = set(children(DEAD_DEPLOY)) & ({PACKAGE} | set(FOUR_INSTRUMENTS))
        self.assertEqual(stale, set(), f"still claimed by the dead stage: {sorted(stale)}")

    def test_it_is_genuinely_unreachable_from_the_dev_root(self):
        self.assertNotIn(
            DEAD_DEPLOY, children("cd1fcd25"),
            "the old Deploy stage is reachable again, which changes the "
            "severity of everything this class tolerates",
        )


class EveryAmendedNodeStillParses(unittest.TestCase):

    def test_the_amendment_notes_did_not_break_their_own_files(self):
        """Written after doing exactly that.

        The first version of my re-homing notes put an apostrophe inside a
        single-quoted YAML scalar and made two of these entries unparseable —
        the same defect I had fixed in the lock's renderer that morning, in a
        different surface, by hand. A fix in one writer does nothing for the
        next person hand-rolling YAML in a script.
        """
        for uid in [PACKAGE, ASSEMBLE, VERIFY, PUBLISH, DEAD_DEPLOY] + FOUR_INSTRUMENTS:
            with self.subTest(uid=uid):
                self.assertIsInstance(frontmatter(uid), dict)


if __name__ == "__main__":
    unittest.main()
