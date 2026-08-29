"""AC5 (5b608d28, v1.92 Stream 1): the release machine reads its
product-specific step set from a TYPED release profile, never from a
literal baked into the machine.

Three assertions, matching the locked criterion's evidence exactly:
  1. No product literal ('tropo', a version string, a product path)
     appears in the machine modules (`lib/release_profile.py`,
     `tropo-release-run.py`).
  2. The shipped profile (`vault/files/6bf18510.md`) and a fixture profile
     declaring a DIFFERENT step set both load through `release_profile.py`
     and drive the runner to a terminal verdict.
  3. A judgment (`playbook`) slot with no named executor is refused at
     load.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_release_profile_seam_v192
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TOOLS = REPO / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.release_bindings import BindingError  # noqa: E402
from lib.release_gates import PHASES  # noqa: E402
from lib.release_profile import (  # noqa: E402
    ReleaseProfileError,
    load_profile,
    load_profile_from_frontmatter,
)

# The real 12 declared leaves of 634913c2, measured 2026-08-24 by both
# talos-t51 and argus-a156 independently (7 tool / 5 playbook).
# DERIVED, never pinned. This was a hard-coded twelve-uid literal — the second
# copy of the pipeline that release_bindings.declared_leaves() exists to
# prevent, and that AC2's own test scrupulously avoids. Proof it mattered: an
# adversarial pass deleted leaf 8654900a from the governing pipeline entry;
# AC2's suite went 11-failed and AC5+AC6 stayed at 22 passed, because this
# literal still said the leaf was there.
from lib import release_bindings as _rb  # noqa: E402

REAL_LEAVES = _rb.declared_leaves(REPO)

RELEASE_PROFILE_MODULE = TOOLS / "lib" / "release_profile.py"
RELEASE_RUN_SCRIPT = TOOLS / "tropo-release-run.py"

#: A version string shaped like a real shipped release ("1.92.0"), never a
#: two-part cycle label ("v1.92", which is documentation, not a release).
_VERSION_LITERAL_RE = re.compile(r"\b\d+\.\d+\.\d+\b")


def _load_release_run_module():
    name = "release_run_ac5_seam_test"
    spec = importlib.util.spec_from_file_location(name, RELEASE_RUN_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Argus A156's own warning: registering in sys.modules before
    # exec_module avoids an AttributeError from dataclasses on Python 3.9
    # when the module is loaded by path rather than by normal import.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class NoProductLiteralInMachineModules(unittest.TestCase):
    """The static assertion: the machine does not know what it is shipping."""

    def _assert_no_product_literal(self, path: Path) -> None:
        source = path.read_text(encoding="utf-8")
        self.assertNotIn(
            "tropo", source.lower(),
            f"{path.name} names the product literally — the machine must not "
            "know what it is shipping",
        )
        match = _VERSION_LITERAL_RE.search(source)
        self.assertIsNone(
            match,
            f"{path.name} contains a version-shaped literal {match.group(0) if match else ''!r} "
            "— a specific release version is a product concern",
        )
        self.assertNotIn(
            "vault/files/6bf18510", source,
            f"{path.name} hardcodes the shipped profile's own path — "
            "the machine must discover it by uid+type, not by literal path",
        )

    def test_release_profile_module_carries_no_product_literal(self) -> None:
        self._assert_no_product_literal(RELEASE_PROFILE_MODULE)

    def test_release_run_module_carries_no_product_literal(self) -> None:
        self._assert_no_product_literal(RELEASE_RUN_SCRIPT)


class SameLoaderDrivesToTerminalVerdict(unittest.TestCase):
    """The shipped profile and a fixture profile with a different step set
    both load through the same loader and reach a terminal verdict."""

    def setUp(self) -> None:
        self.release_run = _load_release_run_module()

    def _fixture_frontmatter(self):
        # Deliberately a DIFFERENT step set from the shipped profile: two
        # steps total, one slot populated, both deterministic — so this
        # fixture's walk reaches "complete", proving the runner is driven
        # by the profile's own data rather than a built-in list.
        return {
            "uid": "aaaa0001",
            "type": "release-profile",
            "product": "fixture-product",
            "pipeline_uid": "bbbb0002",
            "slots": [
                {
                    "slot": "build-the-artifact",
                    "gate_contract": "candidate",
                    "steps": [
                        {
                            "step_uid": "cccc0003",
                            "kind": "tool",
                            "entry": "fixture-build.py",
                            "description": "build the fixture artifact",
                        },
                    ],
                },
                {
                    "slot": "verify-the-artifact",
                    "gate_contract": "pre-freeze",
                    "steps": [
                        {
                            "step_uid": "dddd0004",
                            "kind": "tool",
                            "entry": "fixture-verify.py",
                            "description": "verify the fixture artifact",
                        },
                    ],
                },
                {
                    "slot": "publish-the-artifact",
                    "gate_contract": "pre-outward-fire",
                    "steps": [
                        {
                            "step_uid": "eeee0005",
                            "kind": "tool",
                            "entry": "fixture-publish.py",
                            "description": "publish the fixture artifact",
                        },
                    ],
                },
            ],
        }

    def test_shipped_profile_loads_and_drives_to_a_terminal_verdict(self) -> None:
        profile = load_profile(REPO, "6bf18510", declared_leaves=REAL_LEAVES)
        outcome = self.release_run.walk(profile)
        self.assertIn(outcome.status, ("complete", "halted"))
        self.assertEqual(len(outcome.actions), 2, "the shipped profile halts at its "
                          "second declared step (the doc-leg judgment leaf) — step order "
                          "amended 2026-08-27, Mike-authorized: legs before build, because "
                          "the build refuses until the legs settle (found on run d445af8b, "
                          "the first runner-driven walk); the pin moves with the fact")
        self.assertEqual(outcome.status, "halted")

    def test_fixture_profile_with_a_different_step_set_loads_and_drives_to_a_terminal_verdict(
        self,
    ) -> None:
        profile = load_profile_from_frontmatter(
            self._fixture_frontmatter(),
            declared_leaves=("cccc0003", "dddd0004", "eeee0005"),
        )
        outcome = self.release_run.walk(profile)
        self.assertEqual(outcome.status, "complete")
        self.assertEqual(len(outcome.actions), 3)

    def test_shipped_and_fixture_verdicts_differ_proving_the_profile_is_read(self) -> None:
        """Control: if the runner ignored the profile and always produced
        the same verdict, this would fail. Two different profiles must be
        able to produce two different terminal verdicts."""
        shipped = load_profile(REPO, "6bf18510", declared_leaves=REAL_LEAVES)
        fixture = load_profile_from_frontmatter(
            self._fixture_frontmatter(),
            declared_leaves=("cccc0003", "dddd0004", "eeee0005"),
        )
        shipped_outcome = self.release_run.walk(shipped)
        fixture_outcome = self.release_run.walk(fixture)
        self.assertNotEqual(shipped_outcome.status, fixture_outcome.status)


class JudgmentSlotWithNoExecutorIsRefused(unittest.TestCase):
    """AC5's one hard validation requirement, named explicitly in the spec."""

    def _frontmatter_with(self, step):
        return {
            "uid": "ffff0006",
            "type": "release-profile",
            "product": "refusal-fixture",
            "pipeline_uid": "bbbb0002",
            "slots": [
                {"slot": "build-the-artifact", "gate_contract": "candidate", "steps": [step]},
                {"slot": "verify-the-artifact", "gate_contract": "pre-freeze", "steps": []},
                {"slot": "publish-the-artifact", "gate_contract": "pre-outward-fire", "steps": []},
            ],
        }

    def test_playbook_step_with_no_executor_is_refused(self) -> None:
        fm = self._frontmatter_with({
            "step_uid": "11110007",
            "kind": "playbook",
            "entry": "some-procedure-uid",
            "description": "a judgment step naming no one",
        })
        with self.assertRaises(ReleaseProfileError):
            load_profile_from_frontmatter(fm)

    def test_mutation_adding_the_missing_executor_makes_it_load(self) -> None:
        """Teeth: the SAME step, differing only by the presence of
        `executor`, must load cleanly — proving the refusal above is about
        the missing field, not something else in the fixture."""
        fm = self._frontmatter_with({
            "step_uid": "11110007",
            "kind": "playbook",
            "entry": "some-procedure-uid",
            "executor": "human",
            "description": "a judgment step naming someone",
        })
        profile = load_profile_from_frontmatter(fm)
        self.assertEqual(profile.product, "refusal-fixture")

    def test_tool_step_naming_an_executor_is_also_refused(self) -> None:
        """Rule 3's inverse, named by Argus alongside rule 2: a
        deterministic step naming a human executor is a judgment step
        wearing the wrong label."""
        fm = self._frontmatter_with({
            "step_uid": "11110007",
            "kind": "tool",
            "entry": "some-script.py",
            "executor": "human",
            "description": "a deterministic step that should not name anyone",
        })
        with self.assertRaises(ReleaseProfileError):
            load_profile_from_frontmatter(fm)


class ProfileStructuralValidation(unittest.TestCase):
    """Validation rules 1, 5 and 6 from the capsule — adjacent to AC5's
    named requirement, cheap to prove, and load-bearing for the loader."""

    def _base_frontmatter(self):
        return {
            "uid": "22220008",
            "type": "release-profile",
            "product": "structural-fixture",
            "pipeline_uid": "bbbb0002",
            "slots": [
                {"slot": "build-the-artifact", "gate_contract": "candidate", "steps": []},
                {"slot": "verify-the-artifact", "gate_contract": "pre-freeze", "steps": []},
                {"slot": "publish-the-artifact", "gate_contract": "pre-outward-fire", "steps": []},
            ],
        }

    def test_missing_slot_is_refused(self) -> None:
        fm = self._base_frontmatter()
        fm["slots"].pop()  # drop publish-the-artifact
        with self.assertRaises(ReleaseProfileError):
            load_profile_from_frontmatter(fm)

    def test_duplicate_slot_is_refused(self) -> None:
        fm = self._base_frontmatter()
        fm["slots"].append(dict(fm["slots"][0]))  # a second build-the-artifact
        with self.assertRaises(ReleaseProfileError):
            load_profile_from_frontmatter(fm)

    def test_gate_contract_outside_the_five_phases_is_refused(self) -> None:
        fm = self._base_frontmatter()
        fm["slots"][0]["gate_contract"] = "whenever-is-convenient"
        self.assertNotIn(fm["slots"][0]["gate_contract"], PHASES)
        with self.assertRaises(ReleaseProfileError):
            load_profile_from_frontmatter(fm)

    def test_step_naming_a_non_live_leaf_is_refused_when_leaves_are_declared(self) -> None:
        fm = self._base_frontmatter()
        fm["slots"][0]["steps"] = [{
            "step_uid": "99990009",
            "kind": "tool",
            "entry": "somewhere.py",
            "description": "names a leaf that does not exist",
        }]
        with self.assertRaises(ReleaseProfileError):
            load_profile_from_frontmatter(fm, declared_leaves=("aaaa0001",))


class TheTwoSurfacesAgree(unittest.TestCase):
    """AC2's tool-declared bindings and AC5's shipped profile, compared.

    737b51a9 item 3: an independent verifier measured these two disagreeing on
    9 of 11 shared leaves — entry on seven, executor class on four — while
    release_bindings' own docstring promised "a profile and a tool cannot
    disagree about what deterministic means". NO TEST COMPARED THEM, which is
    why a promise in a docstring survived a whole cycle as a falsehood.

    They agree today (measured 2026-08-26: 0 of 12). This exists so that stays
    true without anyone remembering to check. It is the same class as the
    scorecard seams — one fact, two readers — and the cure is the same: compare
    them mechanically instead of asserting they match.
    (argus-a158, closing 737b51a9 item 3.)
    """

    def _surfaces(self):
        from lib import release_bindings as rb
        from lib import release_profile as rp
        bindings, _sources = rb.collect_from_tools(REPO)
        a2 = {b.step_uid: b for b in bindings}
        profile = rp.load_profile(REPO, "6bf18510")
        a5 = {b.step_uid: b for slot in profile.slots for b in slot.steps}
        return a2, a5

    @staticmethod
    def _divergences(a2, a5):
        return sorted(
            uid for uid in set(a2) & set(a5)
            if (a2[uid].entry, a2[uid].executor, a2[uid].kind)
            != (a5[uid].entry, a5[uid].executor, a5[uid].kind)
        )

    def test_they_share_the_same_leaves(self) -> None:
        a2, a5 = self._surfaces()
        self.assertTrue(a2, "no tool-declared bindings resolved")
        self.assertTrue(a5, "no profile steps resolved")
        self.assertEqual(
            set(a2), set(a5),
            "the tool declarations and the shipped profile must cover the same "
            "leaves; a leaf in one and not the other is the divergence starting",
        )

    def test_no_shared_leaf_disagrees_on_entry_or_executor(self) -> None:
        a2, a5 = self._surfaces()
        diverged = self._divergences(a2, a5)
        detail = "\n".join(
            f"  {uid}\n"
            f"      AC2: kind={a2[uid].kind} entry={a2[uid].entry} exec={a2[uid].executor}\n"
            f"      AC5: kind={a5[uid].kind} entry={a5[uid].entry} exec={a5[uid].executor}"
            for uid in diverged
        )
        self.assertEqual([], diverged, f"profile and tools disagree:\n{detail}")

    def test_the_comparison_can_actually_see_a_divergence(self) -> None:
        """The known-positive, and it is not optional.

        "0 disagreements" is the same shape as a comparison that silently
        skipped every leaf — which is exactly what an earlier version of this
        probe did, swallowing twelve exceptions and reporting a clean result.
        A green here means nothing unless a planted divergence goes red.
        """
        import dataclasses
        a2, a5 = self._surfaces()
        uid = sorted(set(a2) & set(a5))[0]
        planted = dict(a5)
        planted[uid] = dataclasses.replace(a5[uid], entry="PLANTED-DIVERGENCE")
        self.assertEqual(
            [uid], self._divergences(a2, planted),
            "the comparison must detect a planted divergence, or its clean "
            "result is meaningless",
        )


if __name__ == "__main__":
    unittest.main()
