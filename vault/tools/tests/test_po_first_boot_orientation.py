#!/usr/bin/env python3
"""v1.94 B-7 (f01564310146, LOCKED) — Po's first-boot orientation gauntlet.

Six locked criteria: the map renders fresh in a real built box and did not
ship pre-rendered (AC1); the escape costs one input and a flag silences the
automatic re-fire (AC2); the flag never blocks an on-demand re-run (AC3);
every artifact the walk cites resolves in a real box and all four concepts
are covered (AC4); the render is derived -- edits appear, hand-edits don't
survive, and staleness is detectable without anyone re-rendering (AC5); the
board kit's README names both authored-boards and derived-renders as
legitimate consumers of board.css (AC6).

AC1 and AC4 build a REAL box (git archive HEAD -> real index rebuild -> the
real production emitters) via the fresh-box gate's own shared fixture --
not a hand-made directory standing in for one. AC2/AC3/AC5 exercise real,
small, shared primitives (lib.po_first_boot, tropo-render-studio-map.py)
directly; AC6 reads real source text.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from tests.test_fresh_box_gate_e52826c5 import BuiltBoxCase  # noqa: E402

from lib import po_first_boot as pfb  # noqa: E402

import importlib.util as _ilu  # noqa: E402


def _load(name: str, path: Path):
    spec = _ilu.spec_from_file_location(name, path)
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render_map = _load(
    "po_first_boot_render_studio_map", TOOLS / "tropo-render-studio-map.py"
)

PLAYBOOK_PATH = ROOT / "vault" / "playbooks" / "po-first-boot-orientation-f015f6f98b9b.md"
PLAYBOOK_TEXT = PLAYBOOK_PATH.read_text(encoding="utf-8")

# The four concepts Mike named (AC4), each mapped to the artifact path the
# playbook actually cites for it -- kept here, once, so the coverage check
# and its negative control read the SAME declared set the playbook does.
CONCEPT_ARTIFACTS = {
    "the vault": "vault/files/eca73d77.md",
    "work management and capsules": "vault/files/2d4f8c91.md",
    "the agent lifecycle": "vault/playbooks/99341618.md",
    "the moment-index skim": "docs/tropo-studio-map.md",
}


def _steps_section(playbook_text: str) -> str:
    """The '## Steps' section only -- what Po actually SHOWS during the
    walk. Deliberately excludes Resources / Related Playbooks / frontmatter,
    which cite sibling dev-specs and this-repo governance for a maintainer
    reading raw source, never artifacts Po shows a customer (several of
    those, like sibling dev-specs at argo-reference scope, never ship in a
    customer box at all -- citing them there is normal cross-referencing,
    not a claim the walk displays them)."""
    match = re.search(r"## Steps\n(.*?)\n---\n\n## Outcomes", playbook_text, re.DOTALL)
    assert match, "playbook must have a ## Steps section ending before ## Outcomes"
    return match.group(1)


def cited_repo_paths(playbook_text: str) -> list[str]:
    """Every markdown-link target inside '## Steps' that names a real
    repo-relative file (never a bare directory, an anchor, or an external
    URL) -- resolved from the playbook's own location at
    vault/playbooks/<uid>.md, two directories below the repo root."""
    paths: list[str] = []
    for _label, href in re.findall(
        r"\[([^\]]+)\]\(([^)]+)\)", _steps_section(playbook_text)
    ):
        if href.startswith(("http://", "https://", "#")) or href.endswith("/"):
            continue
        path_part = href.split("#", 1)[0]
        resolved = render_map._rewrite_href(  # reuse the same lexical resolver
            path_part, source_dir="vault/playbooks", output_dir="."
        )
        paths.append(resolved)
    return paths


def missing_concepts(playbook_text: str, concepts: dict) -> list[str]:
    """Which of `concepts` has NO artifact path cited anywhere in the
    playbook text. Pure function so the negative control can call it
    against a deliberately mutilated copy of the text without touching
    the real file."""
    cited = set(cited_repo_paths(playbook_text))
    return [name for name, path in concepts.items() if path not in cited]


class ColdBoxFirstBoot(BuiltBoxCase):
    """AC1, as re-ruled by Mike at the v1.95 walk (Spine A AC8, 2026-09-05): the
    render SHIPS in the box, produced by Step 9b2 from the box's own index with
    the box's own renderer, and first boot VERIFIES it (--check-stale FRESH)
    rather than generating it blind. The rule this class pinned until v1.95 —
    nothing pre-rendered — is reversed; the fixture now runs Step 9b2 itself,
    as the build does, so the assertion is about the shipped shape and not
    about a fixture that never reached the step (metis-g121's measurement)."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # BuiltBoxCase's own emit() runs build_from_manifest + step_3e +
        # step_4 (governed, index-driven ship entries) but never
        # step_3b_copy_vault_tools -- vault/tools/*.py ships wholesale, not
        # as a governed entry, per a SEPARATE step (Argus A92/A123). This
        # test needs the generator itself present to run it, so it's the
        # one class in this file that also runs step_3b.
        cls.builder.step_3b_copy_vault_tools(str(cls.build_dir))
        # the build's own Step 9b2: render the map inside the box, box mode
        cls.builder.step_9b2_render_studio_map(str(cls.build_dir))

    def test_render_ships_and_first_boot_verifies_it_fresh(self) -> None:
        rendered = self.box("boards/po/studio-map.html")
        self.assertTrue(rendered.is_file(), "Step 9b2 must ship the render in the box (AC8)")

        tool = self.box("vault/tools/tropo-render-studio-map.py")
        self.assertTrue(tool.is_file(), "the renderer itself must ship in the box")
        source_map = self.box("docs/tropo-studio-map.md")
        self.assertTrue(source_map.is_file(), "the canonical Map must ship in the box")

        # first boot's gesture: --check-stale, and the shipped render is FRESH
        result = subprocess.run(
            [sys.executable, str(tool), "--check-stale", "--box", "--vault-path", str(self.build_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        html_text = rendered.read_text(encoding="utf-8")
        self.assertIn("<h1>", html_text)
        # Derived FROM THE BOX'S OWN MAP, not the dev machine's: the embedded
        # fingerprint must match a hash computed from the box's own source.
        expected_fp = render_map.body_sha256(source_map)
        match = render_map.FINGERPRINT_RE.search(html_text)
        self.assertIsNotNone(match, "render must carry a source fingerprint")
        self.assertEqual(match.group(1), expected_fp)


class OneGestureEscape(unittest.TestCase):
    """AC2 — the escape is one gesture, and the flag prevents re-fire."""

    def test_flag_absence_and_presence_gate_the_automatic_fire(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(
                pfb.should_fire_automatic_walk(root),
                "no flag yet -- the automatic walk must fire",
            )
            flag = pfb.mark_walk_offered(root)
            self.assertTrue(flag.is_file())
            self.assertFalse(
                pfb.should_fire_automatic_walk(root),
                "the flag was just written -- the automatic walk must not fire again",
            )
            # CONTROL: delete the flag and the walk must fire again --
            # proves the silence came from the flag, not from the
            # mechanism being broken.
            flag.unlink()
            self.assertTrue(
                pfb.should_fire_automatic_walk(root),
                "deleting the flag must restore the automatic fire",
            )

    def test_escape_is_a_single_input_with_no_confirming_follow_up(self) -> None:
        step_1 = re.search(
            r"1\. \*\*(?:Render|Verify) the (?:shipped )?map.*?(?=\n2\. \*\*)", PLAYBOOK_TEXT, re.DOTALL
        )
        self.assertIsNotNone(step_1, "Step 1 (the escape point) must exist")
        step_1_text = step_1.group(0)
        # Exactly one question posed to the user before either branch --
        # asserted by count, per the locked evidence. A second "?" inside
        # this step would mean a follow-up confirmation, which collapses
        # mandated-but-escapable into mandated.
        question_count = step_1_text.count("?")
        self.assertEqual(
            question_count,
            1,
            f"Step 1 must pose exactly one question (found {question_count}) "
            "-- a two-step escape fails this criterion",
        )
        self.assertNotIn("are you sure", step_1_text.lower())
        self.assertIn(
            "one-gesture escape point",
            step_1_text,
            "Step 1 must name itself as the escape point",
        )


class RerunOnDemand(unittest.TestCase):
    """AC3 — the walk re-runs on demand, forever. The flag gates the
    AUTOMATIC fire and nothing else."""

    def test_playbook_body_never_conditions_its_steps_on_the_flag(self) -> None:
        """The only flag reference in the whole playbook is Step 6 WRITING
        it -- nothing reads it as a precondition to running Steps 1-5.
        Structural proof that an on-demand run (which never consults the
        flag at all, per Rule 3) executes the identical steps regardless
        of the flag's state."""
        flag_mentions = [
            m.start() for m in re.finditer(r"flag", PLAYBOOK_TEXT, re.IGNORECASE)
        ]
        self.assertTrue(flag_mentions, "the playbook must document the flag somewhere")
        steps_1_to_5 = re.search(
            r"## Steps\n(.*?)6\. \*\*Write the flag", PLAYBOOK_TEXT, re.DOTALL
        )
        self.assertIsNotNone(steps_1_to_5)
        self.assertNotIn(
            "flag",
            steps_1_to_5.group(1).lower(),
            "Steps 1-5 must never mention the flag -- a read there would "
            "let it block an on-demand re-run, which Rule 3 forbids",
        )

    def test_should_fire_is_never_consulted_by_the_rules_governing_on_demand(
        self,
    ) -> None:
        rules_section = re.search(
            r"## Rules\n(.*?)\n---", PLAYBOOK_TEXT, re.DOTALL
        ).group(1)
        self.assertIn("on-demand", rules_section.lower())
        self.assertIn(
            "MUST NOT be checked before an on-demand request",
            rules_section,
        )


class CitedArtifactsAndConceptCoverage(BuiltBoxCase):
    """AC4 — every cited artifact resolves in a real built box, and all
    four concepts Mike named are covered."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # BuiltBoxCase's emit() skips step_3_copy_kernel (kernel/.tropo/) --
        # the walk's own Step 6 cites .tropo/concierge/activate.md, so this
        # class needs it present to check that citation for real.
        cls.builder.step_3_copy_kernel(str(cls.build_dir))

    def test_every_cited_path_resolves_in_the_built_box(self) -> None:
        paths = cited_repo_paths(PLAYBOOK_TEXT)
        self.assertTrue(paths, "fixture is meaningless if the playbook cites nothing")
        missing = [p for p in paths if not self.box(p).exists()]
        self.assertEqual(
            missing,
            [],
            f"{len(missing)} of {len(paths)} cited paths are absent from the "
            f"built box, never checked against the origin studio: {missing}",
        )

    def test_all_four_concepts_are_covered(self) -> None:
        self.assertEqual(
            missing_concepts(PLAYBOOK_TEXT, CONCEPT_ARTIFACTS),
            [],
            "every one of the four concepts Mike named must resolve to an "
            "artifact the walk actually shows",
        )
        for concept, path in CONCEPT_ARTIFACTS.items():
            with self.subTest(concept=concept):
                self.assertTrue(
                    self.box(path).is_file(),
                    f"{concept}'s cited artifact {path} must exist in the box",
                )

    def test_control_dropping_a_concept_is_caught(self) -> None:
        """Negative control: silently deleting one concept's step from the
        walk must turn the coverage check red -- without this, a walk that
        drops the agent lifecycle passes cleanly because every artifact it
        STILL names continues to exist."""
        mutilated = PLAYBOOK_TEXT.replace(
            "[`vault/playbooks/99341618.md`](../../vault/playbooks/99341618.md)",
            "",
        )
        self.assertEqual(
            missing_concepts(mutilated, CONCEPT_ARTIFACTS),
            ["the agent lifecycle"],
        )


class RenderIsDerived(unittest.TestCase):
    """AC5 — regeneration, and staleness is detectable without anyone
    re-rendering."""

    def _fixture(self, tmp: Path) -> tuple[Path, Path]:
        (tmp / "docs").mkdir()
        (tmp / "boards" / "po").mkdir(parents=True)
        source = tmp / "docs" / "tropo-studio-map.md"
        source.write_text(
            "---\ntitle: Test Map\n---\n\n# Test Map\n\nOriginal sentence.\n",
            encoding="utf-8",
        )
        output = tmp / "boards" / "po" / "studio-map.html"
        return source, output

    def test_an_edit_to_the_map_appears_after_re_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            source, output = self._fixture(tmp)
            output.write_text(render_map.render(source), encoding="utf-8")
            self.assertNotIn("A brand-new sentence", output.read_text(encoding="utf-8"))

            source.write_text(
                source.read_text(encoding="utf-8") + "\nA brand-new sentence.\n",
                encoding="utf-8",
            )
            output.write_text(render_map.render(source), encoding="utf-8")
            self.assertIn("A brand-new sentence", output.read_text(encoding="utf-8"))

    def test_a_hand_edit_to_the_render_does_not_survive_re_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            source, output = self._fixture(tmp)
            output.write_text(render_map.render(source), encoding="utf-8")
            output.write_text(
                output.read_text(encoding="utf-8").replace(
                    "Original sentence.", "A HAND EDIT THAT MUST NOT SURVIVE."
                ),
                encoding="utf-8",
            )
            self.assertIn(
                "A HAND EDIT THAT MUST NOT SURVIVE.",
                output.read_text(encoding="utf-8"),
            )

            output.write_text(render_map.render(source), encoding="utf-8")
            self.assertNotIn(
                "A HAND EDIT THAT MUST NOT SURVIVE.",
                output.read_text(encoding="utf-8"),
                "a derived surface that preserves hand edits is a second "
                "map wearing a render's name",
            )
            self.assertIn("Original sentence.", output.read_text(encoding="utf-8"))

    def test_moving_the_map_without_re_rendering_is_detected_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            source, output = self._fixture(tmp)
            output.write_text(render_map.render(source), encoding="utf-8")

            is_stale, rendered_fp, current_fp = render_map.check_staleness(
                output, source
            )
            self.assertFalse(is_stale)
            self.assertEqual(rendered_fp, current_fp)

            # Move the Map WITHOUT re-rendering -- the risk this spec cites.
            source.write_text(
                source.read_text(encoding="utf-8") + "\nMoved since the last render.\n",
                encoding="utf-8",
            )
            is_stale, rendered_fp, current_fp = render_map.check_staleness(
                output, source
            )
            self.assertTrue(is_stale, "a moved Map must be detected as stale")
            self.assertNotEqual(rendered_fp, current_fp)

            # CONTROL, the inverse direction: re-render and it must clear,
            # or the check is an alarm nobody can silence.
            output.write_text(render_map.render(source), encoding="utf-8")
            is_stale, rendered_fp, current_fp = render_map.check_staleness(
                output, source
            )
            self.assertFalse(is_stale)
            self.assertEqual(rendered_fp, current_fp)

    def test_relative_links_are_rewritten_from_source_relative_to_output_relative(
        self,
    ) -> None:
        """A link written relative to docs/ (where the source Map lives)
        must resolve correctly from boards/po/ (where the render lives) --
        carrying an href through unchanged silently breaks the moment
        source and output are in different directories, which they always
        are here. Caught once already by manually inspecting rendered
        output against this real repo; pinned here so it can't come back
        unnoticed."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            (tmp / ".tropo-studio").mkdir()
            target = tmp / ".tropo-studio" / "mission-brief.md"
            target.write_text("real target", encoding="utf-8")
            source, output = self._fixture(tmp)
            source.write_text(
                source.read_text(encoding="utf-8")
                + "\nSee [the mission brief](../.tropo-studio/mission-brief.md).\n",
                encoding="utf-8",
            )
            output.write_text(render_map.render(source), encoding="utf-8")

            html_text = output.read_text(encoding="utf-8")
            match = re.search(r'href="([^"]*mission-brief\.md)"', html_text)
            self.assertIsNotNone(match, "the rewritten link must still be present")
            resolved = (output.parent / match.group(1)).resolve()
            self.assertEqual(resolved, target.resolve())
            self.assertEqual(resolved.read_text(encoding="utf-8"), "real target")

    def test_the_runs_anyway_validate_check_catches_staleness_too(self) -> None:
        """AC5's own evidence names the shape this must take: 'detectable by
        something that runs anyway,' the same boot-derivation drift gate
        tropo-validate.py already runs routinely. check_po_map_render_fresh
        is that second reader of the fingerprint -- proven here directly,
        not assumed from RenderIsDerived's other tests exercising only the
        renderer's own check_staleness."""
        validate = _load("po_first_boot_tropo_validate", TOOLS / "tropo-validate.py")
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            source, output = self._fixture(tmp)
            output.write_text(render_map.render(source), encoding="utf-8")

            findings, checked, defects = validate.check_po_map_render_fresh(tmp)
            self.assertEqual(checked, 1)
            self.assertEqual(defects, 0, findings)

            source.write_text(
                source.read_text(encoding="utf-8") + "\nMoved.\n", encoding="utf-8"
            )
            findings, checked, defects = validate.check_po_map_render_fresh(tmp)
            self.assertEqual(defects, 1)
            self.assertTrue(any("stale" in f for f in findings), findings)


class KitReadmeNamesBothClasses(unittest.TestCase):
    """AC6 — the kit README carries the two-classes sentence, landing in
    this cycle: the stylesheet serves authored boards AND derived
    renders."""

    def test_readme_names_both_classes(self) -> None:
        readme = (ROOT / "boards" / "_formats" / "README.md").read_text(
            encoding="utf-8"
        )
        lowered = readme.lower()
        self.assertIn("authored board", lowered)
        self.assertIn("derived render", lowered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
