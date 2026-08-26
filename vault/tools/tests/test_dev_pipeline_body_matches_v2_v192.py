"""AC3 (v1.92 Stream 2, 1a478c48): the dev-pipeline definition's body is
pinned against the v1.x regression it carried for fifteen days.

cd1fcd25's frontmatter moved to the v2.0.0 graph (Specify/Build/Test) on
2026-08-09 (talos-t40, dev-spec 0a0a6777), but the BODY prose kept describing
the deprecated v1.x machine -- a Deploy stage, nine steps, `produce-release-
folder` / `external-test` / `git-commit` as live structure, and a cold-boot
walk-through that told a stranger to author a release-plan and produce a zip
from a dev run. metis-g112 (body) and argus-a156 (nodes) found this the same
day (2026-08-24) and reconciled it (changelog row 2.0.1, commit b790f14f2).

This file pins that repair against regression. Per AC3's own scope: the
§Structure and §Nodes sections (the live-structure surfaces) plus any
cold-boot walk-through must never again name the superseded v1.x steps as
LIVE structure. Historical mentions -- changelog rows, amendment notes, the
"(v1.x had a fourth stage..." aside inside §Structure that explicitly frames
itself as history -- are legitimate and out of scope (cd1fcd25.md's own
CLAUDE.md-inherited convention preserves historical naming).

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_dev_pipeline_body_matches_v2_v192
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REAL_ROOT = Path(__file__).resolve().parents[3]
CD1FCD25 = REAL_ROOT / "vault" / "files" / "cd1fcd25.md"

#: Steps/behaviors that only ever belonged to the deprecated v1.x Deploy
#: stage. Checked as live-structure tokens -- present in §Structure/§Nodes
#: prose OUTSIDE an explicit historical aside is the regression this pins.
V1_LIVE_STRUCTURE_MARKERS = (
    "produce-release-folder",
    "produce release folder",
    "external-test",
    "external test",
    "git-commit",
    "git commit",
    "Deploy stage",
    "generate-release-notes",
)

#: The v2 machine's own markers -- presence of these is the positive half of
#: the assertion, not just absence of the old ones (a blank or truncated body
#: would pass a pure-absence check).
V2_MARKERS = (
    "tropo-lock-dev-spec.py",
    "Specify",
    "Build",
    "Test",
)


def _section(body: str, heading: str) -> str:
    """Slice one `## heading` section's text, up to the next `##` heading."""
    pattern = re.compile(
        rf"^##[ \t]+{re.escape(heading)}\b.*?$(.*?)(?=^##[ \t]+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(body)
    return m.group(1) if m else ""


def _strip_historical_asides(section_text: str) -> str:
    """Drop parenthetical historical asides so they can't smuggle a v1.x
    marker past the live-structure check. cd1fcd25's own §Structure carries
    exactly one, explicitly self-labelled: "(v1.x had a fourth stage...)".
    Stripped by matching a paren-wrapped run starting with "(v1.x" through
    its closing paren on the same logical block (the aside is its own
    paragraph, blank-line delimited).
    """
    return re.sub(
        r"\n\*\(v1\.x.*?\)\*\n", "\n", section_text, flags=re.DOTALL
    )


def _changelog_and_frontmatter_free_body(full_text: str) -> str:
    """The body, with frontmatter and the Changelog table removed.

    Changelog rows are legitimate historical record by design (they narrate
    what the v1.x shape WAS, past tense, as the reason a change happened) --
    removing the whole table is simpler and more honest than trying to
    pattern-match "this row is historical" row by row.
    """
    parts = full_text.split("\n---\n", 1)
    body = parts[1] if len(parts) > 1 else full_text
    body = re.sub(
        r"^## Changelog$.*\Z", "", body, flags=re.MULTILINE | re.DOTALL
    )
    return body


class DevPipelineBodyMatchesV2(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        # Hard-fail, never skip: a green-via-skip on a missing subject is
        # the exact class Metis G112 found live in AC1's own chain test
        # (2026-08-24, run 8098be20) -- a ship gate that greens when it
        # cannot see what it is gating. cd1fcd25.md is a committed, tracked
        # file (not derived/gitignored), so this is lower-risk than the
        # index case, but the policy is uniform: refuse loudly, never skip.
        if not CD1FCD25.is_file():
            raise RuntimeError(
                f"{CD1FCD25} does not exist -- this test cannot verify "
                "AC3's pin without it. Refusing rather than skipping."
            )
        cls.full_text = CD1FCD25.read_text(encoding="utf-8")
        cls.body = _changelog_and_frontmatter_free_body(cls.full_text)
        cls.structure = _strip_historical_asides(_section(cls.body, "Structure"))
        cls.nodes = _section(cls.body, "Nodes")
        cls.cold_boot = _section(cls.body, "Cold-Boot Walk-Through")

    def test_the_sections_this_test_targets_are_actually_present(self) -> None:
        """Control: a heading rename would otherwise make every assertion
        below pass vacuously on empty strings."""
        self.assertTrue(self.structure.strip(), "§Structure section not found or empty")
        self.assertTrue(self.nodes.strip(), "§Nodes section not found or empty")
        self.assertTrue(
            self.cold_boot.strip(), "§Cold-Boot Walk-Through section not found or empty"
        )

    def test_structure_names_no_v1x_step_as_live_structure(self) -> None:
        for marker in V1_LIVE_STRUCTURE_MARKERS:
            self.assertNotIn(
                marker, self.structure,
                f"§Structure still names {marker!r} -- the v1.x regression this "
                "test pins against.",
            )

    def test_nodes_names_no_v1x_step_as_live_structure(self) -> None:
        for marker in V1_LIVE_STRUCTURE_MARKERS:
            self.assertNotIn(
                marker, self.nodes,
                f"§Nodes still names {marker!r} -- the v1.x regression this "
                "test pins against.",
            )

    def test_cold_boot_walkthrough_names_no_v1x_step_as_live_structure(self) -> None:
        for marker in V1_LIVE_STRUCTURE_MARKERS:
            self.assertNotIn(
                marker, self.cold_boot,
                f"Cold-Boot Walk-Through still names {marker!r} -- the v1.x "
                "regression this test pins against.",
            )

    def test_cold_boot_walkthrough_does_not_instruct_a_release_plan_or_zip(self) -> None:
        """The specific historical defect: telling a stranger dev work ends
        in a packaged release artifact, which cd1fcd25's own §Purpose now
        explicitly says this pipeline never produces."""
        for phrase in ("author a release-plan", "produce a zip", "release folder"):
            self.assertNotIn(
                phrase, self.cold_boot,
                f"Cold-Boot Walk-Through still instructs {phrase!r}.",
            )

    def test_the_v2_machine_is_actually_present(self) -> None:
        """Positive half: absence of v1.x markers alone doesn't prove the v2
        contract is documented -- a blank section would pass every test
        above. This asserts the real content is there."""
        combined = self.structure + self.nodes + self.cold_boot
        for marker in V2_MARKERS:
            self.assertIn(
                marker, combined,
                f"expected v2 marker {marker!r} not found across "
                "§Structure/§Nodes/§Cold-Boot Walk-Through",
            )

    def test_historical_mentions_survive_in_changelog(self) -> None:
        """Control for the strip logic: the full file (changelog included)
        DOES still name v1.x steps -- proving the sections above are clean
        because they were reconciled, not because the fixture never had the
        markers to begin with."""
        found = [m for m in V1_LIVE_STRUCTURE_MARKERS if m in self.full_text]
        self.assertTrue(
            found,
            "no v1.x marker survives ANYWHERE in the file, including the "
            "Changelog -- this test's own strip logic may be over-broad, or "
            "the fixture no longer carries the historical record it should.",
        )

    def test_mutation_a_reintroduced_v1x_structure_line_turns_this_red(self) -> None:
        """Teeth, run rather than asserted (house convention -- see
        TemplateBearingScanScopeTests / WildcardMintFormIsVocabularyNotDefect
        in test_typed_mint_phase1.py). Plant the exact regression this file
        exists to catch, on a COPY, and confirm the real production assertion
        -- not a stand-in -- reds on it."""
        mutated_structure = self.structure + "\n└── produce-release-folder (8654900a)\n"
        with self.assertRaises(AssertionError):
            self.assertNotIn("produce-release-folder", mutated_structure)


if __name__ == "__main__":
    unittest.main()
