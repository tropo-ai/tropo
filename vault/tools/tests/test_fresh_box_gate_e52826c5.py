#!/usr/bin/env python3
"""Fresh-Box Gate Closure — the written newcomer path (e52826c5 / 6eb50a61).

The claim this gate defends: *a stranger's first hour does not lie.* v1.86's cold
walk found the written path pointing at things the box does not contain, and a
documented first command that told a brand-new owner their studio was broken.

**These cases assert the BUILT BOX and real runtimes, not source prose.**
Argus's NO-GO (evt_a9360f18f56fe472_00000082) was correct about the first draft:
a red that only reads `extraction_scope:` can turn green while the package still
ships nothing. So:

* AC1/AC6/AC7 run the real manifest loader and the real package builder into a
  TempStudio and assert paths in the emitted box. Removing the packaging weld
  turns them red.
* AC2 runs `tropo-rebuild-vault.py` as a subprocess in two Studio-shaped
  fixtures and reads the argv the validator actually received.
* AC3 writes three governed files by the written steps and runs the real index
  rebuild — the stale same-UID plant must fail, the corrected one must pass.
* AC4/AC5 stay with their production suite; this file adds no duplicate case and
  the final matrix runs them alongside.
* AC8 is the independent cold walk. The builder cannot certify it.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
import unittest

import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
TEMPLATES = ROOT / "vault" / "templates"
SKILL = ROOT / "vault" / "skills" / "tropo-create-executive-agent.md"
REBUILD_VAULT = TOOLS / "tropo-rebuild-vault.py"
REBUILD_INDEX = TOOLS / "tropo-rebuild-index.py"
SMOKE = TOOLS / "tropo-smoke.py"
ORIENTATION_SOURCE = TEMPLATES / "root-docs" / "AGENT-ORIENTATION.md"

TEMPLATE_CORPUS_ARTIFACT = "f51f268c"
ORIENTATION_ARTIFACT = "bfc99da4"
LIB_ARTIFACT = "b281edeb"
GITATTRIBUTES_ARTIFACT = "86ffe86f"
UPDATE_SOURCE_SCHEMA = "tropo.update-source/v1"


def load_build_release():
    spec = importlib.util.spec_from_file_location(
        "tropo_build_release_for_fresh_box", TOOLS / "tropo-build-release.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_candidate_builder():
    spec = importlib.util.spec_from_file_location(
        "tropo_build_candidate_box_for_fresh_box", TOOLS / "tropo-build-candidate-box.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_source_mode_dispatch():
    """The shared packaging predicate, loaded from its real home."""
    spec = importlib.util.spec_from_file_location(
        "ship_extract_dispatch_for_fresh_box",
        ROOT / ".tropo" / "scripts" / "lib" / "ship_extract" / "source_mode_dispatch.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def strip_strings_and_comments(source: str) -> str:
    """Executable code only — a guard must read what a module does, not says."""
    kept = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            kept.append(token.string)
    except tokenize.TokenError:
        return source
    return " ".join(kept)


class BuiltBoxCase(unittest.TestCase):
    """Emits one real package from a package input this fixture builds itself.

    CHECKOUT-PORTABLE BY CONSTRUCTION. The first version read the live
    `vault/00-index.jsonl`, so it passed on the author's machine and failed on a
    fresh clone: index surfaces are gitignored, so a reviewer's checkout has no
    row for a newly authored ship artifact and the box came out empty
    (argus-a148, evt_a9360f18f56fe472_00000091 — 5 failures before a rebuild,
    18/18 after).

    So the fixture starts from TRACKED SOURCES ONLY — `git archive HEAD`, which
    carries no derived state at all — proves the derived surfaces are absent,
    then runs the real index rebuild inside its own TempStudio. That is both the
    setup and the stale-surface regression: there is no state to be stale,
    because the fixture builds its own. Production indexes are never touched.
    """

    build_dir: Path
    tmp: Path
    studio: Path
    builder = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="fresh-box-built-"))
        cls.studio = cls.tmp / "studio"
        cls.studio.mkdir()
        cls.materialize_tracked_sources(cls.studio)
        cls.assert_derived_surfaces_absent(cls.studio)
        cls.freshen_index(cls.studio)
        cls.builder = cls.load_builder_for(cls.studio)
        cls.build_dir = cls.tmp / "box"
        cls.build_dir.mkdir()
        cls.entries = cls.load_entries()
        cls.emit(cls.entries, cls.build_dir)

    @staticmethod
    def materialize_tracked_sources(studio: Path) -> None:
        """Tracked files only — the governed sources, none of the derived state."""
        archive = subprocess.run(
            ["git", "archive", "HEAD"], cwd=str(ROOT), capture_output=True, timeout=600
        )
        if archive.returncode != 0:
            raise unittest.SkipTest("git archive unavailable in this environment")
        extract = subprocess.run(
            ["tar", "-x", "-C", str(studio)],
            input=archive.stdout,
            capture_output=True,
            timeout=600,
        )
        assert extract.returncode == 0, extract.stderr[:400]

    @staticmethod
    def assert_derived_surfaces_absent(studio: Path) -> None:
        """The regression half: setup must start from nothing derived."""
        for rel in (
            "vault/00-index.jsonl",
            "vault/00-archive-index.jsonl",
            "vault/00-project-tree.jsonl",
            "vault/00-index.sqlite",
        ):
            assert not (studio / rel).exists(), (
                f"{rel} arrived from tracked sources; this fixture must prove it "
                f"can discover artifacts without inherited derived state"
            )

    @staticmethod
    def freshen_index(studio: Path) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(studio / "vault" / "tools" / "tropo-rebuild-index.py"),
                "--apply",
                "--skip-rehydrate",
                "--vault-path",
                str(studio),
            ],
            cwd=str(studio),
            capture_output=True,
            text=True,
            timeout=1800,
        )
        assert proc.returncode == 0, (
            "the fixture could not build its own package input: "
            f"{(proc.stderr or proc.stdout)[-500:]}"
        )

    @staticmethod
    def load_builder_for(studio: Path):
        """Load build-release with its roots pointed at the fixture Studio."""
        builder = load_build_release()
        builder.tropo_roots.STUDIO_ROOT = studio
        builder.tropo_roots.VAULT_DIR = studio / "vault"
        builder.INDEX_PATH = str(studio / "vault" / "00-index.jsonl")
        builder.SHIP_ARTIFACT_CAPSULE_PATH = str(
            studio / "vault" / "capsules" / "tropo-ship-artifact.capsule.md"
        )
        return builder

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @property
    def source_root(self) -> Path:
        return type(self).studio

    @staticmethod
    def file_digest_map(box: Path) -> dict:
        return {
            str(path.relative_to(box)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(box.rglob("*"))
            if path.is_file()
        }

    @classmethod
    def tree_digest(cls, box: Path) -> str:
        """One digest over path+content, so a rename is a difference too."""
        rolling = hashlib.sha256()
        for name, digest in sorted(cls.file_digest_map(box).items()):
            rolling.update(name.encode("utf-8"))
            rolling.update(digest.encode("ascii"))
        return rolling.hexdigest()

    @classmethod
    def load_entries(cls) -> list:
        root_uid = cls.builder.read_manifest_root_uid(
            cls.builder.SHIP_ARTIFACT_CAPSULE_PATH
        )
        return cls.builder.load_manifest_entries(cls.builder.INDEX_PATH, root_uid)

    @classmethod
    def emit(cls, entries: list, build_dir: Path, *, ship_entries: bool = True) -> None:
        """Run BOTH production emitters, the way a real build does.

        `build_from_manifest` walks the ship-artifact graph (templates, root
        docs, skeletons). Ship-scoped governed entries — including tools like
        `tropo-smoke.py`, which ship at their real path — come through
        `step_4_copy_ship_entries`, index-driven. Asserting the box from only
        one of the two would call a tool missing when the other step ships it.
        """
        cls.builder.DRY_RUN = False
        cls.builder.build_from_manifest(str(build_dir), entries)
        if ship_entries:
            cls.builder.step_4_copy_ship_entries(
                str(build_dir), cls.builder.load_ship_entries(cls.builder.INDEX_PATH)
            )

    def box(self, rel: str) -> Path:
        return self.build_dir / rel


class TemplateCorpusShipsTests(BuiltBoxCase):
    """AC1 — the templates the written path tells a newcomer to copy."""

    def test_every_top_level_template_is_present_in_the_built_box(self):
        expected = sorted(p.name for p in TEMPLATES.glob("tropo-*.template.md"))
        self.assertTrue(expected, "fixture is meaningless with no templates on disk")

        emitted = sorted(
            p.name for p in (self.box("vault/templates")).glob("tropo-*.template.md")
        )

        missing = [name for name in expected if name not in emitted]
        self.assertEqual(
            missing,
            [],
            f"{len(missing)} of {len(expected)} templates never reached the built "
            f"box, so 'copy from vault/templates/…' dead-ends: {missing[:5]}",
        )

    def test_relocating_subtrees_are_not_shipped_twice(self):
        """Skips are real: root-docs and the skeletons relocate elsewhere."""
        for skipped in (
            "vault/templates/root-docs",
            "vault/templates/agents-skeleton",
            "vault/templates/.tropo-studio-skeleton",
        ):
            self.assertFalse(
                self.box(skipped).exists(),
                f"{skipped} shipped under templates AND relocates elsewhere — two "
                f"copies of the same bytes at different paths",
            )

    def test_removing_the_corpus_artifact_empties_the_templates_in_the_box(self):
        """Mutation: the packaging weld, not the prose, is what ships them."""
        mutated = [
            e for e in self.entries if e.get("uid") != TEMPLATE_CORPUS_ARTIFACT
        ]
        self.assertEqual(
            len(mutated),
            len(self.entries) - 1,
            "the corpus artifact was not present in the manifest entries",
        )
        scratch = self.tmp / "mutated-box"
        scratch.mkdir(exist_ok=True)

        self.emit(mutated, scratch)

        emitted = list((scratch / "vault" / "templates").glob("tropo-*.template.md"))
        self.assertEqual(
            emitted,
            [],
            "templates still shipped without their artifact — the test is not "
            "measuring the packaging weld",
        )


class SmokeToolShipsTests(BuiltBoxCase):
    """AC6 — invoked from the BUILT BOX, not from Argo source."""

    def test_smoke_tool_is_present_in_the_built_box(self):
        self.assertTrue(
            self.box("vault/tools/tropo-smoke.py").is_file(),
            "tropo-smoke.py did not reach the box, while the toolbelt advertises it",
        )

    def test_the_belt_and_the_box_agree_about_this_tool(self):
        """The advertised command and the shipped tool must be the same thing.

        The kernel copy emits `.tropo/toolbelt.md` in a later build step than the
        manifest walker, so this box may not carry it. Skipping would leave the
        original defect — belt advertises, box lacks — unguarded, so assert the
        pairing across the two surfaces that do exist here.
        """
        belt_source = ROOT / ".tropo" / "toolbelt.md"
        self.assertTrue(belt_source.is_file(), "no toolbelt to check")
        advertised = "tropo-smoke.py" in belt_source.read_text(errors="replace")
        shipped = self.box("vault/tools/tropo-smoke.py").is_file()
        self.assertEqual(
            (advertised, shipped),
            (True, True),
            f"belt advertises smoke={advertised} but the box ships it={shipped}; "
            f"the two must not disagree",
        )
        emitted_belt = self.box(".tropo/toolbelt.md")
        if emitted_belt.is_file():
            self.assertIn("tropo-smoke.py", emitted_belt.read_text(errors="replace"))

    def test_documented_command_runs_from_the_box(self):
        tool = self.box("vault/tools/tropo-smoke.py")
        self.assertTrue(tool.is_file(), "no smoke tool in the box to run")
        proc = subprocess.run(
            [sys.executable, str(tool), "--only", "index", "--json"],
            cwd=str(self.build_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertTrue(
            proc.stdout.strip() or proc.stderr.strip(),
            "the documented smoke command produced no output inside the box",
        )
        self.assertNotIn(
            "Traceback",
            proc.stderr,
            f"smoke crashed inside the box: {proc.stderr[-400:]}",
        )


class OrientationDocumentTests(BuiltBoxCase):
    """AC7 — canonical source AND the built output, per the dev-spec's paths."""

    def test_canonical_source_lives_where_the_spec_declares(self):
        self.assertTrue(
            ORIENTATION_SOURCE.is_file(),
            "dev-spec e52826c5 declares the source at "
            "vault/templates/root-docs/AGENT-ORIENTATION.md",
        )

    def test_built_box_carries_orientation_at_its_root(self):
        emitted = self.box("AGENT-ORIENTATION.md")
        self.assertTrue(
            emitted.is_file(),
            "the box has no root AGENT-ORIENTATION.md, so it states no boundaries "
            "before capability",
        )
        self.assertEqual(
            emitted.read_text(errors="replace"),
            ORIENTATION_SOURCE.read_text(errors="replace"),
            "the direct-copy weld altered the document between source and box",
        )

    def test_orientation_states_all_four_boundaries(self):
        emitted = self.box("AGENT-ORIENTATION.md")
        self.assertTrue(emitted.is_file(), "no orientation document in the box")
        text = emitted.read_text(errors="replace").lower()
        for boundary in ("read", "search", "propos", "write"):
            self.assertIn(boundary, text, f"missing the {boundary} boundary")

    def test_removing_the_orientation_artifact_empties_it_from_the_box(self):
        mutated = [e for e in self.entries if e.get("uid") != ORIENTATION_ARTIFACT]
        self.assertEqual(len(mutated), len(self.entries) - 1)
        scratch = self.tmp / "mutated-orientation-box"
        scratch.mkdir(exist_ok=True)

        self.emit(mutated, scratch)

        self.assertFalse(
            (scratch / "AGENT-ORIENTATION.md").is_file(),
            "orientation reached the box without its artifact — the assertion is "
            "not measuring the direct-copy weld",
        )


class PackageDependencyClosureTests(BuiltBoxCase):
    """A shipped tool ships its imports (AC8 walk verdict 62a22664).

    Metis's cold walk: the box carried 70 tool scripts and ZERO
    `vault/tools/lib/` modules, so the documented first rebuild died on
    ModuleNotFoundError. The candidate builder had faithfully packaged a
    production gap — `lib/` is ungoverned substrate, so the governed-entry
    manifest structurally could not carry it.
    """

    def test_lib_modules_reach_the_box(self):
        expected = sorted(p.name for p in (ROOT / "vault" / "tools" / "lib").glob("*.py"))
        self.assertTrue(expected, "no lib modules on disk to ship")
        emitted = sorted(p.name for p in (self.box("vault/tools/lib")).glob("*.py"))
        missing = [name for name in expected if name not in emitted]
        self.assertEqual(
            missing,
            [],
            f"{len(missing)} of {len(expected)} lib modules missing from the box; "
            f"every tool that imports them dies on first use: {missing[:5]}",
        )

    def test_documented_rebuild_runs_inside_the_box(self):
        """The stranger's first command, executed in the artifact they receive.

        Run against a PORTABLE copy, because "the artifact they receive" is the
        box after the final purge. This class's raw build_dir still carries a
        partial index generation — index rows written by the ship-entry emitter,
        with no trust metadata — and a rebuild there refuses at "no trusted
        index-surface metadata" before it reaches anything this case is about.
        That refusal is the shape evt 114 removed from the product, so asserting
        against it would be measuring a box no recipient gets.
        """
        box = self.tmp / "documented-rebuild-box"
        shutil.rmtree(box, ignore_errors=True)
        shutil.copytree(self.build_dir, box)
        type(self).builder.step_10_2_purge_run_local_artifacts(str(box))

        rebuild = box / "vault" / "tools" / "tropo-rebuild-index.py"
        self.assertTrue(rebuild.is_file(), "no rebuild tool in the box")
        proc = subprocess.run(
            [sys.executable, str(rebuild), "--apply", "--vault-path", str(box)],
            cwd=str(box),
            capture_output=True,
            text=True,
            timeout=1800,
        )
        combined = (proc.stderr or "") + (proc.stdout or "")
        self.assertNotIn(
            "ModuleNotFoundError",
            combined,
            "the documented first rebuild cannot import its own dependencies "
            "inside the box",
        )
        # Both halves, deliberately. The source check proves the shipped tool
        # CONTAINS the derivation; the behavioural checks prove it actually
        # produced the registry in a box shaped like the one a recipient gets.
        # The first alone passes on a tool that mentions the generator and fails
        # to run it, which is the gap that let a missing registry ship.
        self.assertIn(
            "MINT_REGISTRY_GENERATOR",
            rebuild.read_text(errors="replace"),
            "the shipped first-setup command has no mint-registry derivation",
        )
        self.assertEqual(proc.returncode, 0, combined[-500:])
        self.assertTrue(
            (box / "vault" / "capsules" / "mint-registry.json").is_file(),
            "the documented first setup rebuilt indexes but left governed minting "
            "unavailable; one setup command must derive both surfaces",
        )

    def test_smoke_capability_paths_run_inside_the_box(self):
        smoke = self.box("vault/tools/tropo-smoke.py")
        self.assertTrue(smoke.is_file(), "no smoke tool in the box")
        for op in ("mint", "index", "orient"):
            with self.subTest(op=op):
                proc = subprocess.run(
                    [sys.executable, str(smoke), "--only", op, "--json"],
                    cwd=str(self.build_dir),
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                self.assertNotIn(
                    "ModuleNotFoundError",
                    (proc.stderr or "") + (proc.stdout or ""),
                    f"smoke {op} cannot import its dependencies inside the box",
                )

    def test_removing_the_lib_artifact_reproduces_the_walk_failure(self):
        """Mutation: without the lib surface, the box breaks the way it did."""
        mutated = [e for e in self.entries if e.get("uid") != LIB_ARTIFACT]
        self.assertEqual(
            len(mutated),
            len(self.entries) - 1,
            "the lib artifact is not in the manifest entries",
        )
        scratch = self.tmp / "mutated-lib-box"
        scratch.mkdir(exist_ok=True)

        self.emit(mutated, scratch)

        self.assertFalse(
            list((scratch / "vault" / "tools" / "lib").glob("*.py")),
            "lib modules shipped without their artifact",
        )
        rebuild = scratch / "vault" / "tools" / "tropo-rebuild-index.py"
        if rebuild.is_file():
            proc = subprocess.run(
                [sys.executable, str(rebuild), "--apply", "--vault-path", str(scratch)],
                cwd=str(scratch),
                capture_output=True,
                text=True,
                timeout=900,
            )
            self.assertIn(
                "ModuleNotFoundError",
                (proc.stderr or "") + (proc.stdout or ""),
                "removing the lib surface did not reproduce the walk failure, so "
                "this case is not measuring dependency closure",
            )


class PackageDeterminismTests(BuiltBoxCase):
    """Two builds of one commit must be the same bytes (Argus NO-GO, evt 102).

    Same-commit candidate builds differed in exactly 13
    `vault/tools/lib/__pycache__/*.pyc` files: the candidate's own index and
    import execution generates bytecode inside the materialized source, and the
    new recursive lib surface then packaged it. Bytecode embeds the compiling
    interpreter's magic number and the source mtime, so it is machine-and-moment
    specific by construction.
    """

    def test_no_bytecode_reaches_the_box(self):
        offenders = [
            str(p.relative_to(self.build_dir))
            for p in self.build_dir.rglob("*")
            if p.is_file() and (p.suffix in (".pyc", ".pyo")
                                or "__pycache__" in p.parts)
        ]
        self.assertEqual(
            offenders,
            [],
            f"{len(offenders)} interpreter-generated files shipped: {offenders[:5]}",
        )

    def test_restoring_bytecode_to_the_traversal_turns_red(self):
        """Mutation: disable the pruning and the defect must come back.

        Asserting only that the predicate classifies a `.pyc` would pass while
        the packager ignored it. This re-emits with pruning neutered and
        requires the bytecode to reappear in the box.
        """
        cached = list((self.source_root / "vault" / "tools" / "lib").rglob("*.pyc"))
        self.assertTrue(
            cached,
            "no bytecode existed in the materialized source, so this case could "
            "not tell an exclusion from an empty directory",
        )

        builder = type(self).builder
        original = builder.prune_bytecode
        scratch = self.tmp / "mutated-bytecode-box"
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir()
        builder.prune_bytecode = lambda dirs, files: files
        try:
            self.emit(self.entries, scratch, ship_entries=False)
        finally:
            builder.prune_bytecode = original

        leaked = [p for p in scratch.rglob("*.pyc")]
        self.assertTrue(
            leaked,
            "neutering the pruning did not reintroduce bytecode, so the "
            "exclusion is not what keeps it out of the box",
        )

    def test_two_builds_of_one_commit_are_byte_identical(self):
        """Bytecode generation stays ENABLED, so the exclusion is what is tested.

        Setting PYTHONDONTWRITEBYTECODE would make this pass with the defect
        still present — it would prove the environment was quiet, not that the
        packager excludes what the environment produces.
        """
        second = self.tmp / "determinism-second"
        second.mkdir(exist_ok=True)
        self.emit(self.entries, second)

        first_map = self.file_digest_map(self.build_dir)
        second_map = self.file_digest_map(second)

        self.assertEqual(
            sorted(first_map), sorted(second_map), "the two builds emitted different file sets"
        )
        differing = [name for name, digest in first_map.items()
                     if second_map.get(name) != digest]
        self.assertEqual(
            differing,
            [],
            f"{len(differing)} files differ between two builds of the same "
            f"commit: {differing[:5]}",
        )
        self.assertEqual(
            self.tree_digest(self.build_dir),
            self.tree_digest(second),
            "package SHA is not reproducible from one commit",
        )


class IndexGenerationShapeTests(BuiltBoxCase):
    """A package carries the whole index generation or none of it (evt 114).

    Two failures taught this the hard way, and they are the same mistake in
    different clothes. Shipping the JSONL pair with a seal but no database gave
    the recipient two of the three evidence copies the writer requires, and its
    first rebuild refused as incomplete. Shipping the database made the package
    machine-dependent, because SQLite bytes vary by library version — Metis's
    Mac and this machine disagree on identical content. A partial generation is
    evidence that contradicts itself.
    """

    GENERATION = (
        "vault/00-index.jsonl",
        "vault/00-archive-index.jsonl",
        "vault/00-project-tree.jsonl",
        "vault/00-index.sqlite",
        ".tropo-studio/locks/index-surfaces.meta.json",
        ".tropo-studio/locks/index-surfaces.ratchet.json",
    )

    def purged_box(self) -> Path:
        box = self.tmp / "no-index-box"
        if not box.exists():
            shutil.copytree(self.build_dir, box)
            builder = type(self).builder
            builder.step_10_sanitize_argo_identity(str(box))
            builder.step_10_2_purge_run_local_artifacts(str(box))
        return box

    def rebuild_in(self, box: Path):
        return subprocess.run(
            [sys.executable, str(box / "vault" / "tools" / "tropo-rebuild-vault.py"),
             "--apply"],
            cwd=str(box), capture_output=True, text=True, timeout=1800,
        )

    def test_the_package_carries_no_index_generation(self):
        box = self.purged_box()
        present = [rel for rel in self.GENERATION if (box / rel).exists()]
        # Matched by the generation's real filenames, not by prefix: `.tropo/00-index.md`
        # and the briefing package's own 00-index.md are content documents that
        # happen to share a name, and sweeping them out would delete governed
        # reading material to tidy up derived state.
        generated = re.compile(
            r"^(00-index|00-archive-index|00-project-tree)\.(jsonl|sqlite)(-\w+)?$"
            r"|^index-surfaces\.(meta|ratchet)\.json$"
            r"|^index-write\.lock$"
        )
        stragglers = [
            str(p.relative_to(box)) for p in box.rglob("*")
            if p.is_file() and generated.match(p.name)
        ]
        self.assertEqual(present, [], f"index generation shipped: {present}")
        self.assertEqual(stragglers, [], f"files claim an absent generation: {stragglers}")

    def test_the_empty_shape_bootstraps_and_completes(self):
        """The recipient's first documented command builds the whole generation."""
        box = self.tmp / "bootstrap-walk-box"
        shutil.rmtree(box, ignore_errors=True)
        shutil.copytree(self.purged_box(), box)

        proc = self.rebuild_in(box)
        combined = (proc.stdout or "") + (proc.stderr or "")
        self.assertNotIn("shrink-floor evidence is incomplete", combined)
        self.assertNotIn("no trusted index-surface metadata", combined)
        for rel in ("vault/00-index.jsonl", "vault/00-archive-index.jsonl",
                    ".tropo-studio/locks/index-surfaces.meta.json",
                    ".tropo-studio/locks/index-surfaces.ratchet.json"):
            self.assertTrue((box / rel).is_file(),
                            f"first rebuild did not bootstrap {rel}")

        second = self.rebuild_in(box)
        self.assertNotIn("REFUSAL", (second.stdout or "") + (second.stderr or ""),
                         "the second rebuild does not refresh normally")

    def test_partial_shapes_refuse(self):
        """Mutation: each way of shipping PART of a generation must be caught.

        Restoring only some of the generation is exactly what the two rejected
        packages did, so each partial shape has to fail here or this suite would
        have shipped both of them.
        """
        source = self.build_dir
        cases = {
            "jsonl without evidence": ("vault/00-index.jsonl",),
            "two-copy evidence without SQLite": (
                "vault/00-index.jsonl",
                "vault/00-archive-index.jsonl",
                ".tropo-studio/locks/index-surfaces.meta.json",
                ".tropo-studio/locks/index-surfaces.ratchet.json",
            ),
            "SQLite without pair": ("vault/00-index.sqlite",),
        }
        for name, restored in cases.items():
            with self.subTest(shape=name):
                box = self.tmp / f"partial-{abs(hash(name))}"
                shutil.rmtree(box, ignore_errors=True)
                shutil.copytree(self.purged_box(), box)
                planted = False
                for rel in restored:
                    # The emitted pre-purge box carries the canonical JSONL
                    # surfaces but SQLite is generated in the fixture Studio
                    # and is intentionally not copied by the governed-entry
                    # emitter. Use that real local database for the
                    # SQLite-without-pair mutation rather than skipping the
                    # exact partial shape this test promises to cover.
                    origin_root = (
                        self.source_root
                        if name == "SQLite without pair"
                        else source
                    )
                    origin = origin_root / rel
                    if not origin.exists():
                        continue
                    (box / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(origin, box / rel)
                    planted = True
                if not planted:
                    self.skipTest(f"fixture cannot build the {name} shape")

                proc = self.rebuild_in(box)
                combined = (proc.stdout or "") + (proc.stderr or "")
                self.assertTrue(
                    "REFUSAL" in combined or proc.returncode != 0,
                    f"the {name} shape was accepted; a partial generation must refuse",
                )


class PortablePackageTests(BuiltBoxCase):
    """What the box ships once the index generation is out of it.

    The seal-era cases retired with the shape they described: sealing writes
    evidence about surfaces this package no longer carries, and the
    documented-rebuild and partial-shape cases now live in
    IndexGenerationShapeTests, which owns that contract end to end.
    """

    def portable_box(self) -> Path:
        """The box as a recipient receives it: sanitized and portable."""
        box = self.tmp / "portable-box"
        if not box.exists():
            shutil.copytree(self.build_dir, box)
            builder = type(self).builder
            builder.step_10_sanitize_argo_identity(str(box))
            builder.step_10_2_purge_run_local_artifacts(str(box))
        return box

    def test_sanitation_removes_the_two_warts_the_walk_named(self):
        box = self.portable_box()
        offenders = {"path": [], "metadata": []}
        for path in box.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            argo_path_claim = "this folder, " + "`" + "argo-" + "os/`"
            if argo_path_claim in text.lower():
                offenders["path"].append(str(path.relative_to(box)))
            if text.startswith("---\n"):
                end = text.find("\n---", 4)
                # Ask YAML what the FIELD is, rather than matching text.
                # `8dd772a0` records the phrase inside a quoted history value
                # describing its own promotion — prose about the past, not a
                # marker — and a text match cannot tell those apart once the
                # copier reflows a long scalar.
                try:
                    parsed = yaml.safe_load(text[4:end]) if end != -1 else None
                except yaml.YAMLError:
                    parsed = None
                if isinstance(parsed, dict) and \
                        str(parsed.get("extraction_scope") or "") == "argo-reference":
                    offenders["metadata"].append(str(path.relative_to(box)))
        self.assertEqual(offenders["path"], [], "box still points a reader at argo-os/")
        self.assertEqual(offenders["metadata"], [],
                         "box still carries build metadata in frontmatter")

    def test_no_machine_dependent_bytes_ship(self):
        """The package carries nothing a different machine would write differently.

        Ruled by Argus (evt 113): a SHA that excludes a shipped file is not an
        identity for that package, so the composed index does not ship at all.
        The portable truth is the sealed JSONL pair plus its metadata, which is
        text; the recipient's first rebuild materializes its own database.
        """
        box = self.portable_box()
        offenders = [
            str(p.relative_to(box)) for p in box.rglob("*")
            if p.is_file() and (
                p.name.endswith((".sqlite", ".pyc", ".pyo", "-shm", "-wal",
                                 ".tmp-shm", ".tmp-wal"))
                or p.name == "index-write.lock")
        ]
        self.assertEqual(offenders, [], f"machine-dependent bytes shipped: {offenders}")

    def test_the_digest_covers_every_shipped_file(self):
        """No exclusions and no side manifest — mutation: shipping the database.

        Planting a SQLite file must move the package SHA. If it did not, the
        anchor would leave delivered bytes unbound, which is the reason option
        (a) was rejected.
        """
        candidate = load_candidate_builder()
        box = self.portable_box()
        files, before_sha = candidate.digest_tree(box)
        self.assertTrue(files, "the digest covers nothing")

        planted = box / "vault" / "00-index.sqlite"
        planted.write_bytes(b"SQLite format 3\x00pretend-a-machine-local-database")
        try:
            after_files, after_sha = candidate.digest_tree(box)
            self.assertIn("vault/00-index.sqlite", after_files,
                          "a shipped file is outside the digest")
            self.assertNotEqual(before_sha, after_sha,
                                "shipping a database did not move the package SHA, "
                                "so the anchor does not bind every delivered byte")
        finally:
            planted.unlink()

    def test_the_recipient_receives_the_clean_filter_declaration(self):
        """A recipient who runs `git init` must not commit derived content.

        Metis's walk found the box carried no `.gitattributes` at all, so the
        navigation blocks that `vault/files/*.md` bodies carry — index-derived
        and viewer-relative — would enter the object store on the recipient's
        first commit. That is the I5 violation the filter exists to prevent,
        happening before anyone has done anything wrong.
        """
        shipped = self.box(".gitattributes")
        self.assertTrue(shipped.is_file(), "no .gitattributes in the box")
        self.assertIn("filter=navblockstrip", shipped.read_text(encoding="utf-8"))

    def test_removing_the_artifact_leaves_the_box_without_the_filter(self):
        """Mutation: the artifact is what puts the declaration in the box."""
        mutated = [e for e in self.entries if e.get("uid") != GITATTRIBUTES_ARTIFACT]
        self.assertEqual(len(mutated), len(self.entries) - 1,
                         "the .gitattributes artifact is not in the manifest entries")
        scratch = self.tmp / "no-gitattributes-box"
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir()

        self.emit(mutated, scratch, ship_entries=False)

        self.assertFalse(
            (scratch / ".gitattributes").exists(),
            "the declaration shipped without its artifact, so this case is not "
            "measuring what puts it there",
        )

    def test_mint_templates_reach_the_box(self):
        expected = sorted(p.name for p in (ROOT / "vault" / "capsules" / "templates").glob("*.md"))
        self.assertTrue(expected)
        shipped = sorted(p.name for p in (self.box("vault/capsules/templates")).glob("*.md"))
        self.assertEqual(
            [n for n in expected if n not in shipped], [],
            "mint cannot create a governed file without its templates, and the "
            "cure smoke names fails too",
        )


class UpdateSourceResolutionTests(unittest.TestCase):
    """AC4 — one resolver, extended; no hand-written host (Argus ruling 2)."""

    EXPECTED_SHAPE = "/storage/v1/object/public/releases/updates"

    def builder(self):
        return load_build_release()

    def test_tracked_publication_evidence_yields_the_expected_shape(self):
        builder = self.builder()
        derived = builder._resolve_update_base_from_tracked_manifest()
        self.assertTrue(
            derived,
            "no publication evidence derived from tracked "
            "vault/updates/updates-manifest.json",
        )
        self.assertTrue(derived.startswith("https://"), derived)
        self.assertIn(self.EXPECTED_SHAPE, derived, derived)

    def test_resolution_prefers_environment_then_tracked_evidence(self):
        builder = self.builder()
        resolved = builder._resolve_update_manifest_url()
        self.assertTrue(
            resolved,
            "the resolver returns nothing even though tracked publication "
            "evidence exists — a candidate box cannot be walked without an address",
        )
        self.assertTrue(resolved.endswith("updates-manifest.json"), resolved)

    def test_disagreement_between_env_and_tracked_evidence_refuses(self):
        builder = self.builder()
        with self.assertRaises(SystemExit) as raised:
            builder._reconcile_update_origins(
                "https://one.example/storage/v1/object/public/releases/updates",
                "https://two.example/storage/v1/object/public/releases/updates",
            )
        self.assertIn("drift", str(raised.exception).lower())

    def test_matching_origins_do_not_refuse(self):
        builder = self.builder()
        same = "https://one.example/storage/v1/object/public/releases/updates"
        self.assertEqual(builder._reconcile_update_origins(same, same), same)


class CustomerModeRebuildTests(unittest.TestCase):
    """AC2 — the argv the validator actually receives, in two Studio shapes."""

    def studio(self, *, recipient: bool) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="fresh-box-rebuild-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "vault" / "tools").mkdir(parents=True)
        (tmp / "vault" / "files").mkdir(parents=True)
        (tmp / ".tropo").mkdir(parents=True)
        shutil.copy2(REBUILD_VAULT, tmp / "vault" / "tools" / REBUILD_VAULT.name)
        # A validator stub that records the argv it was handed. Real subprocess,
        # real argument construction, no Argo validation run.
        (tmp / "vault" / "tools" / "tropo-validate.py").write_text(
            "import json, sys, pathlib\n"
            "pathlib.Path(__file__).parent.parent.parent.joinpath('argv.json')"
            ".write_text(json.dumps(sys.argv[1:]))\n"
            "print('[PASS] stub validator')\n"
            "raise SystemExit(0)\n",
            encoding="utf-8",
        )
        (tmp / "vault" / "tools" / "tropo-rebuild-index.py").write_text(
            "print('stub rebuild-index')\nraise SystemExit(0)\n", encoding="utf-8"
        )
        if recipient:
            (tmp / ".tropo" / "update-source.json").write_text(
                json.dumps(
                    {
                        "schema_id": UPDATE_SOURCE_SCHEMA,
                        "manifest_url": "https://example.test/releases/updates",
                    }
                ),
                encoding="utf-8",
            )
        return tmp

    def argv_for(self, studio: Path) -> list:
        subprocess.run(
            [sys.executable, str(studio / "vault" / "tools" / REBUILD_VAULT.name)],
            cwd=str(studio),
            capture_output=True,
            text=True,
            timeout=300,
        )
        recorded = studio / "argv.json"
        self.assertTrue(
            recorded.is_file(),
            "the rebuild never invoked the validator, so no argv was recorded",
        )
        return json.loads(recorded.read_text(encoding="utf-8"))

    def test_recipient_box_gets_customer_mode(self):
        argv = self.argv_for(self.studio(recipient=True))
        self.assertIn(
            "--customer",
            argv,
            "a recipient box still runs Argo-strict validation — the v1.86 "
            "'284 failed / do not ship against a broken substrate' first hour",
        )

    def test_argo_source_stays_strict(self):
        argv = self.argv_for(self.studio(recipient=False))
        self.assertNotIn(
            "--customer",
            argv,
            "the source Studio silently downgraded to customer mode; unconditional "
            "customer mode would pass a token search while hiding real failures",
        )

    def test_detection_reads_package_data_not_a_guess(self):
        code = strip_strings_and_comments(REBUILD_VAULT.read_text(errors="replace"))
        banned = {
            ".git": re.compile(r"['\"]\.git['\"]"),
            "hostname": re.compile(r"hostname|gethostname|uname", re.I),
            "environment": re.compile(r"os\.environ|getenv", re.I),
        }
        found = [name for name, pattern in banned.items() if pattern.search(code)]
        self.assertEqual(
            found,
            [],
            f"customer-mode detection must not consult {found}; identity comes "
            f"from authoritative recipient package data",
        )
        ast.parse(REBUILD_VAULT.read_text(errors="replace"))


class SkillUidCollisionTests(unittest.TestCase):
    """AC3 — follow the written steps, then run the REAL index rebuild."""

    def studio(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="fresh-box-uid-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "vault" / "files").mkdir(parents=True)
        (tmp / "vault" / "tools").mkdir(parents=True)
        (tmp / ".tropo").mkdir(parents=True)
        (tmp / "STUDIO.md").write_text("# fixture studio\n", encoding="utf-8")
        (tmp / ".tropo" / "boot-config.md").write_text("# boot\n", encoding="utf-8")
        # The rebuild reads sibling tools as derivation inputs, so a studio with
        # only the rebuilder refuses before it ever reaches UID resolution.
        for name in (
            "tropo-rebuild-index.py",
            "tropo-navblock-strip.py",
            "tropo-generate-relations-header.py",
        ):
            source = TOOLS / name
            if source.is_file():
                shutil.copy2(source, tmp / "vault" / "tools" / name)
        if (TOOLS / "lib").is_dir():
            shutil.copytree(TOOLS / "lib", tmp / "vault" / "tools" / "lib")
        return tmp

    def write_agent_trio(self, studio: Path, uids: tuple, name: str = "scout") -> None:
        """The three files the written skill actually tells a founder to create.

        They live at `agents/<name>/<name>-{charter,briefing,activation}.md`, not
        in `vault/files/<uid>.md` — planting them in the wrong home produced a
        filename parse refusal instead of the UID collision this case is for.
        """
        charter, briefing, activation = uids
        folder = studio / "agents" / name
        folder.mkdir(parents=True, exist_ok=True)
        for uid, kind in (
            (charter, "charter"),
            (briefing, "briefing"),
            (activation, "activation"),
        ):
            folder.joinpath(f"{name}-{kind}.md").write_text(
                f"---\nuid: {uid}\ntype: note\nstatus: active\nstate: active\n"
                f"title: 'fixture agent {kind}'\nmember_of: []\n---\n\n# {kind}\n",
                encoding="utf-8",
            )

    def rebuild(self, studio: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(studio / "vault" / "tools" / "tropo-rebuild-index.py"),
                "--apply",
                "--vault-path",
                str(studio),
            ],
            cwd=str(studio),
            capture_output=True,
            text=True,
            timeout=600,
        )

    def test_distinct_uids_survive_the_first_rebuild(self):
        studio = self.studio()
        self.write_agent_trio(studio, ("aa11aa11", "bb22bb22", "cc33cc33"))

        proc = self.rebuild(studio)

        self.assertEqual(
            proc.returncode,
            0,
            f"a skill-following newcomer's first rebuild failed: "
            f"{(proc.stderr or proc.stdout)[-500:]}",
        )
        index = studio / "vault" / "00-index.jsonl"
        self.assertTrue(index.is_file())
        uids = {
            json.loads(line)["uid"]
            for line in index.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        self.assertTrue({"aa11aa11", "bb22bb22", "cc33cc33"} <= uids)

    def test_the_stale_shared_uid_plant_is_rejected(self):
        """The defect the old skill text produced, reproduced end to end."""
        studio = self.studio()
        self.write_agent_trio(studio, ("dd44dd44", "dd44dd44", "dd44dd44"))

        proc = self.rebuild(studio)
        combined = ((proc.stdout or "") + (proc.stderr or "")).lower()

        self.assertNotEqual(
            proc.returncode,
            0,
            "three files sharing one UID rebuilt cleanly; the collision this "
            "gate exists for would not be caught",
        )
        self.assertRegex(
            combined,
            r"collision|duplicate|same uid|dd44dd44",
            f"the refusal did not name the shared UID: {combined[-400:]}",
        )

    def test_the_shipped_skill_no_longer_instructs_a_shared_uid(self):
        """Structural backstop for the runtime cases above."""
        text = SKILL.read_text(errors="replace")
        offenders = [
            line.strip()
            for line in text.splitlines()
            if re.search(r"same UID as|identical UID|reuse the UID", line, re.I)
        ]
        self.assertEqual(offenders, [], " | ".join(offenders))
        uid_sentences = [
            s for s in re.split(r"(?<=[.\n])", text) if re.search(r"\buid\b", s, re.I)
        ]
        self.assertTrue(
            any(
                re.search(r"distinct|own UID|separate UID|mint (a|its)", s, re.I)
                for s in uid_sentences
            ),
            "the skill never states that the three files carry their own UIDs",
        )


class ProductionSuiteMatrixTests(unittest.TestCase):
    """AC4/AC5 — run the existing production suites, do not duplicate them."""

    def test_package_state_exclusion_suite_passes(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "vault.tools.tests.test_package_state_exclusions",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=900,
        )
        self.assertEqual(
            proc.returncode,
            0,
            "AC4/AC5 production welds are red; Fresh-Box must not be reported "
            f"green over them: {(proc.stderr or proc.stdout)[-400:]}",
        )


class ColdWalkHandoffTests(unittest.TestCase):
    """AC8 — asserted as a handoff, never as a builder self-certification."""

    def test_this_suite_does_not_claim_the_cold_walk(self):
        source = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("AC8", source)
        verdict_phrase = " ".join(("cold", "walk", "passed"))
        self.assertNotIn(
            verdict_phrase,
            source.lower(),
            "the builder's own suite must never record a cold-walk verdict",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
