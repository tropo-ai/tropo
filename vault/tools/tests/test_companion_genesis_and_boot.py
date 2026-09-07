#!/usr/bin/env python3
"""v1.94 W6 — shipped companion content, local identity, and cold-box boot.

The package fixture invokes the production manifest walker and production copy
steps, emits the production image manifest, zips the result, and extracts it
outside this checkout. Genesis fixtures are isolated copies of that extraction;
no fixture principal or companion is ever written into the source Studio.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
TEMPLATES = ROOT / "vault" / "templates" / "companions"
GENESIS = TOOLS / "tropo-genesis-companions.py"
OLD_AGENT_PARTS = ("agents", "example")
OLD_AGENT_REL = "/".join(OLD_AGENT_PARTS)
FOUNDER_NAME = "Fixture Founder"
OFFER_MADE = "tropo.concierge.companion_offer_made"
OFFER_DECLINED = "tropo.concierge.companion_offer_declined"
ACTIVATED = "tropo.agent.activated"
CONSTITUTIONAL = {
    "constitutional-preservation",
    "constitutional-entity-reference",
    "constitutional-memory-sovereignty",
    "constitutional-verification",
}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"{path} lacks frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        raise AssertionError(f"{path} has no closing frontmatter fence")
    value = yaml.safe_load(text[4:end])
    if not isinstance(value, dict):
        raise AssertionError(f"{path} frontmatter is not a mapping")
    return value


def _hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


def _tree_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _complete_listing(root: Path) -> list[str]:
    return [path.relative_to(root).as_posix() for path in _tree_files(root)]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise AssertionError(f"{path}:{number} is not a JSON object")
        rows.append(value)
    return rows


def _events(studio: Path) -> list[dict[str, Any]]:
    """Every row on the Studio's bus: the legacy file plus any writer stream
    (the same union vault/tools/lib/event_identity.iter_raw_event_lines reads)."""
    paths: list[Path] = []
    legacy = studio / "vault" / "events" / "00-events.jsonl"
    if legacy.is_file():
        paths.append(legacy)
    streams = studio / "vault" / "events" / "streams"
    if streams.is_dir():
        paths.extend(sorted(streams.glob("*.jsonl")))
    rows: list[dict[str, Any]] = []
    for path in paths:
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if raw and not raw.startswith("#"):
                rows.append(json.loads(raw))
    return rows


def _agent_slugs(studio: Path) -> set[str]:
    home = studio / "vault" / "agents"
    if not home.is_dir():
        return set()
    return {str(_frontmatter(path).get("agent") or "") for path in home.glob("*.md")}


def _package_identity_violations(template_root: Path) -> list[str]:
    violations: list[str] = []
    token = re.compile(r"\b[0-9a-f]{8}(?:[0-9a-f]{4})?\b")
    concrete_field = re.compile(
        r"^(?:uid|party_uid|agent_root_uid):\s*[\"']?[0-9a-f]+[\"']?\s*$",
        re.MULTILINE,
    )
    for path in _tree_files(template_root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if token.search(text) or concrete_field.search(text):
            violations.append(path.relative_to(template_root).as_posix())
        if re.search(r"^lineage:\s*", text, re.MULTILINE):
            violations.append(path.relative_to(template_root).as_posix() + ":lineage")
    return sorted(set(violations))


def _assert_no_shipped_identity(test: unittest.TestCase, image: Path, slug: str) -> None:
    listing = _complete_listing(image)
    template = f"vault/templates/companions/{slug}.md"
    test.assertIn(template, listing, f"{slug} content template is absent from the package")
    test.assertFalse(
        any(path.startswith(f"agents/{slug}/") for path in listing),
        f"the package shipped a concrete agents/{slug}/ home",
    )
    for path in listing:
        if not path.startswith("vault/agents/") or not path.endswith(".md"):
            continue
        fm = _frontmatter(image / path)
        test.assertNotEqual(
            str(fm.get("agent") or "").casefold(),
            slug,
            f"the package shipped a concrete vault/agents entry for {slug}",
        )


def _crew_entries_resolve(
    crew_paths: list[Path], journal_rows: list[dict[str, Any]]
) -> list[str]:
    journal_by_time = {
        str(row.get("timestamp") or row.get("time") or ""): row
        for row in journal_rows
        if row.get("timestamp") or row.get("time")
    }
    defects: list[str] = []
    for path in crew_paths:
        for row in _read_jsonl(path):
            timestamp = str(row.get("timestamp") or "")
            if row.get("inherited_from") != "origin-studio":
                defects.append(f"{path.name}:{timestamp}:missing-attribution")
            if not timestamp or timestamp not in journal_by_time:
                defects.append(f"{path.name}:{timestamp or '<missing>'}:no-journal-event")
    return defects


class BuiltW6Package(unittest.TestCase):
    """One real package per invocation; every selected test shares its bytes."""

    tmp: Path
    source_studio: Path
    package_dir: Path
    image: Path
    package_listing: list[str]
    manifest_entries: list[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="w6-companion-package-"))
        if not (ROOT / ".git").exists():
            # The suite itself ships with vault/tools/. In an extracted box,
            # the current root already IS the real built image; rebuilding a
            # package would require source-only release machinery and git
            # history the box correctly does not carry.
            cls.source_studio = ROOT
            cls.package_dir = ROOT
            cls.image = ROOT
            cls.package_listing = _complete_listing(ROOT)
            cls.manifest_entries = []
            manifest = ROOT / "tropo-image-manifest.json"
            if not manifest.is_file():
                raise unittest.SkipTest(
                    "neither a source checkout nor a built image manifest is present"
                )
            return

        cls.source_studio = cls.tmp / "package-input"
        cls.source_studio.mkdir()
        archive = subprocess.run(
            [
                "git",
                "archive",
                "HEAD",
                "--",
                ".",
                ":(exclude).cursor",
                ":(exclude)**/.cursor",
                ":(exclude)tropo-app/.cursor",
            ],
            cwd=str(ROOT),
            capture_output=True,
            timeout=600,
        )
        if archive.returncode != 0:
            raise unittest.SkipTest("git archive is unavailable")
        extracted = subprocess.run(
            ["tar", "-x", "-C", str(cls.source_studio)],
            input=archive.stdout,
            capture_output=True,
            timeout=600,
        )
        if extracted.returncode != 0:
            raise AssertionError(extracted.stderr[:500])

        # Overlay exactly this work order's uncommitted sources. This keeps the
        # package input independent of live derived indexes and unrelated dirty
        # work while still testing the bytes under review before a commit exists.
        shutil.copytree(
            TEMPLATES,
            cls.source_studio / "vault" / "templates" / "companions",
            dirs_exist_ok=True,
        )
        for source in (
            GENESIS,
            Path(__file__),
            TOOLS / "tests" / "test_derived_row_title.py",
            ROOT / "vault" / "templates" / "tropo-agent-configurator.template.md",
        ):
            target = cls.source_studio / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        shutil.rmtree(
            cls.source_studio.joinpath(*OLD_AGENT_PARTS),
            ignore_errors=True,
        )

        rebuilt = subprocess.run(
            [
                sys.executable,
                str(
                    cls.source_studio
                    / "vault"
                    / "tools"
                    / "tropo-rebuild-index.py"
                ),
                "--apply",
                "--skip-rehydrate",
                "--vault-path",
                str(cls.source_studio),
            ],
            cwd=str(cls.source_studio),
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if rebuilt.returncode != 0:
            raise AssertionError(
                "isolated W6 package input could not build its own index: "
                + (rebuilt.stderr or rebuilt.stdout)[-2000:]
            )

        cls.package_dir = cls.tmp / "package"
        cls.package_dir.mkdir()
        builder = _load(TOOLS / "tropo-build-release.py", "w6_build_release")
        builder.tropo_roots.STUDIO_ROOT = cls.source_studio
        builder.tropo_roots.VAULT_DIR = cls.source_studio / "vault"
        builder.INDEX_PATH = str(cls.source_studio / "vault" / "00-index.jsonl")
        builder.KERNEL_DIR = str(cls.source_studio / ".tropo")
        builder.SHIP_ARTIFACT_CAPSULE_PATH = str(
            cls.source_studio
            / "vault"
            / "capsules"
            / "tropo-ship-artifact.capsule.md"
        )
        builder.DRY_RUN = False
        root_uid = builder.read_manifest_root_uid(builder.SHIP_ARTIFACT_CAPSULE_PATH)
        cls.manifest_entries = builder.load_manifest_entries(builder.INDEX_PATH, root_uid)

        # Production carriage. The same functions are called by main(); only
        # release authorization, publication, and outward writes are omitted.
        builder.step_3_copy_kernel(str(cls.package_dir))
        builder.step_3b_copy_vault_tools(str(cls.package_dir))
        builder.step_3d_copy_vault_playbooks(str(cls.package_dir))
        builder.step_3e_copy_vault_updates(str(cls.package_dir))
        builder.step_3j_copy_vault_schema(str(cls.package_dir))
        builder.step_4_copy_ship_entries(
            str(cls.package_dir), builder.load_ship_entries(builder.INDEX_PATH)
        )
        builder.build_from_manifest(str(cls.package_dir), cls.manifest_entries)
        builder.step_3f_remove_per_studio_boot_derivations(str(cls.package_dir))
        builder.step_3g_write_update_source(str(cls.package_dir))
        builder.step_7_create_vault_skeleton(str(cls.package_dir))

        # The root AGENTS pointer is the one D2 copy required by a real build.
        source_agents = (
            cls.source_studio
            / "vault"
            / "templates"
            / "agents-skeleton"
            / "AGENTS.md"
        )
        target_agents = cls.package_dir / "agents" / "AGENTS.md"
        target_agents.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_agents, target_agents)

        builder.step_10_2_purge_run_local_artifacts(str(cls.package_dir))
        builder.step_9d_emit_image_manifest(str(cls.package_dir), "1.94.0")
        image_manifest = cls.package_dir / "tropo-image-manifest.json"
        if not image_manifest.is_file():
            raise AssertionError("production image-manifest emitter wrote no manifest")

        zip_path = cls.tmp / "tropo-os-v1.94.0.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in _tree_files(cls.package_dir):
                archive.write(path, path.relative_to(cls.package_dir).as_posix())
        cls.image = cls.tmp / "outside-any-checkout" / "studio-image"
        cls.image.mkdir(parents=True)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(cls.image)
        cls.package_listing = _complete_listing(cls.image)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fixture_studio(self, name: str, *, po_fixture: bool = True) -> Path:
        studio = self.tmp / name
        if studio.exists():
            shutil.rmtree(studio)
        shutil.copytree(self.image, studio)
        if po_fixture:
            self.mint_po(studio)
        return studio

    # v1.95 Spine A AC5 (Mike: "cure and cut candidate #3"). No fixture may
    # supply what the box lacks: Po's identity used to be hand-written into
    # the registry here, which is exactly why the non-author cold walk found
    # `--as po` failing on a real fresh box. Every prerequisite below is the
    # box's own documented gesture, run on the extracted box.

    def first_boot(self, studio: Path) -> None:
        """Po's step 0b, the command activate.md names: derives the index and
        mints this Studio's identity. Idempotent on the manifest."""
        if (studio / ".tropo" / "studio-identity.md").exists():
            return
        proc = subprocess.run(
            [
                sys.executable,
                str(studio / "vault" / "tools" / "tropo-rebuild-index.py"),
                "--apply",
                "--skip-rehydrate",
                "--vault-path",
                ".",
            ],
            cwd=str(studio),
            capture_output=True,
            text=True,
            timeout=600,
            stdin=subprocess.DEVNULL,
        )
        self.assertTrue(
            (studio / ".tropo" / "studio-identity.md").is_file(),
            f"step 0b did not mint the Studio identity (exit {proc.returncode}): "
            + (proc.stderr or proc.stdout)[-1200:],
        )

    def genesis_command(self, studio: Path, *args: str) -> list[str]:
        return [
            sys.executable,
            str(studio / "vault" / "tools" / "tropo-genesis-companions.py"),
            "--studio",
            str(studio),
            *args,
        ]

    def mint_po(self, studio: Path) -> str:
        """Step 0b's second command (D2): Po's own party identity through the
        tool's --po. Returns her party uid."""
        self.first_boot(studio)
        proc = subprocess.run(
            self.genesis_command(studio, "--po"),
            cwd=str(studio), capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
        payload = json.loads(proc.stdout)
        if payload.get("po_already_present"):
            return str(payload["po_party_uid"])
        return str(payload["companions"]["po"]["party_uid"])

    def mint_founder(self, studio: Path) -> str:
        """§1.5's governed door (AC4): `tropo-mint-id.py --founder <name>`,
        idempotent on presence. Returns the founder principal's uid."""
        self.first_boot(studio)
        proc = subprocess.run(
            [
                sys.executable,
                str(studio / "vault" / "tools" / "tropo-mint-id.py"),
                "--founder",
                FOUNDER_NAME,
            ],
            cwd=str(studio), capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, (proc.stderr or proc.stdout)[-800:])
        match = re.search(
            r"founder principal (?:minted|already present): ([0-9a-f]+)", proc.stdout
        )
        self.assertIsNotNone(match, proc.stdout)
        assert match is not None
        return match.group(1)

    def emit_as_po(
        self, studio: Path, event_type: str, founder_uid: str, data: dict[str, Any]
    ) -> subprocess.CompletedProcess[str]:
        """The §1.5c emit exactly as activate.md documents it."""
        return subprocess.run(
            [
                sys.executable,
                str(studio / "vault" / "tools" / "tropo-emit-event.py"),
                "--type", event_type,
                "--source", "/agents/po",
                "--as", "po",
                "--lifecycle", "evergreen",
                "--subject", founder_uid,
                "--data", json.dumps(data),
            ],
            cwd=str(studio), capture_output=True, text=True, timeout=120,
        )

    def run_genesis(
        self,
        studio: Path,
        *,
        offline: bool = False,
        accept: str = "cal,darin",
        founder: bool = True,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any] | None]:
        env = dict(os.environ)
        if offline:
            blocker = self.tmp / "offline-python"
            blocker.mkdir(exist_ok=True)
            (blocker / "sitecustomize.py").write_text(
                "import socket\n"
                "def blocked(*args, **kwargs):\n"
                "    raise RuntimeError('network disabled by W6 offline fixture')\n"
                "socket.socket = blocked\n"
                "socket.create_connection = blocked\n",
                encoding="utf-8",
            )
            env["PYTHONPATH"] = str(blocker)
        # v1.95 Spine A AC5 (f015de6b3a18): companion genesis no longer mints the
        # Studio identity as an interim side effect — it REFUSES without a
        # manifest, and (D3) without a founder principal. In the arrival walk
        # Po's step 0b rebuild (AC2) and §1.5's founder door (AC4) have both
        # run before any companion is offered; here they are the same commands.
        self.first_boot(studio)
        if founder:
            self.mint_founder(studio)
        proc = subprocess.run(
            self.genesis_command(studio, "--accept", accept),
            cwd=str(studio),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        payload = json.loads(proc.stdout) if proc.returncode == 0 else None
        return proc, payload

    @staticmethod
    def generated_scope(studio: Path, payload: dict[str, Any]) -> list[Path]:
        paths: list[Path] = [
            studio / ".tropo" / "studio-identity.md",
            studio / ".tropo-studio" / "registries" / "agent-registry.yaml",
        ]
        for slug, identity in payload["companions"].items():
            paths.extend(
                [
                    studio / "vault" / "agents" / f"{identity['uid']}.md",
                    studio / "vault" / "files" / f"{identity['party_uid']}.md",
                    studio / "vault" / "files" / f"{identity['agent_root_uid']}.md",
                ]
            )
            paths.extend(_tree_files(studio / "agents" / slug))
        po = next(
            path
            for path in (studio / "vault" / "agents").glob("*.md")
            if str(_frontmatter(path).get("agent") or "") == "po"
        )
        paths.append(po)
        return sorted(set(paths))

    def test_applier_never_names_companions(self) -> None:
        studio = self.fixture_studio("applier-studio")
        proc, payload = self.run_genesis(studio)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
        assert payload is not None
        planted = (
            studio / "agents" / "cal" / ".tropo-capsule" / "memory"
            / "agent-memories.jsonl"
        )
        customer_memory = b'{"memory":"customer-authored; never vendor-owned"}\n'
        planted.write_bytes(customer_memory)

        applier = _load(
            self.image / "vault" / "tools" / "tropo-apply-image.py",
            "w6_image_applier",
        )
        prior = studio / "tropo-image-manifest.json"
        plan = applier.plan(self.image, studio, prior)
        companion_prefixes = ("agents/cal/", "agents/darin/")
        companion_entries = {
            f"vault/agents/{identity['uid']}.md"
            for identity in payload["companions"].values()
        }
        named = [
            path
            for operation in ("replace", "delete", "skip")
            for path in plan[operation]
            if path.startswith(companion_prefixes) or path in companion_entries
        ]
        self.assertEqual(named, [], f"the image applier named generated identity: {named}")

        # The feared mutation: derive deletes from an added Studio scan. The
        # same unreachability assertion must go red, proving the control has teeth.
        studio_scan = set(_complete_listing(studio))
        image_files = set(applier._image_files(self.image))
        unsafe = dict(plan)
        unsafe["delete"] = sorted(
            set(plan["delete"]) | (studio_scan - image_files - set(plan["skip"]))
        )
        with self.assertRaises(AssertionError):
            self.assertEqual(
                [
                    path
                    for path in unsafe["delete"]
                    if path.startswith(companion_prefixes) or path in companion_entries
                ],
                [],
                "unsafe Studio-scan delete derivation unexpectedly stayed green",
            )

        applier.apply(self.image, studio, prior_manifest=prior, version="1.94.0")
        self.assertEqual(planted.read_bytes(), customer_memory)

    def test_no_shipped_identity_cal(self) -> None:
        _assert_no_shipped_identity(self, self.image, "cal")
        self.assertIn(
            "vault/templates/companions/memory-edition/cal-method-pins.jsonl",
            self.package_listing,
        )

    def test_no_shipped_identity_darin(self) -> None:
        _assert_no_shipped_identity(self, self.image, "darin")
        self.assertIn(
            "vault/templates/companions/memory-edition/darin-method-pins.jsonl",
            self.package_listing,
        )

    def test_no_shipped_identity_po(self) -> None:
        _assert_no_shipped_identity(self, self.image, "po")
        self.assertIn(
            "vault/templates/companions/memory-edition/po-method-pins.jsonl",
            self.package_listing,
        )

    def test_shipped_companion_set_has_no_identity_coverage_gap(self) -> None:
        """AC2 (305bfe33) must cover every shipped companion, not a
        hand-named subset. Po joined the shipped set and the by-name
        assertions above were not extended to cover her until Argus A166's
        backstop review of 6b70aef8 caught the gap: a coverage assertion
        enumerated by name only ever covers the members alive when it was
        written. Derive the subject set from what the image actually ships
        — never from COMPANIONS (tropo-genesis-companions.py), which is
        mint-only and deliberately excludes class-not-crew members like Po
        — so the next companion is covered by construction, not by someone
        remembering to add a fourth `test_no_shipped_identity_*` method.

        The corpus-wide literal-uid scan and its known-positive plant used
        to live inside test_no_shipped_identity_darin, misnamed for what
        they check: Argus A166 mutation-proved that a real defect there
        would report as "darin identity failure," naming the wrong subject
        (evt_b51c083be28ac6fe_00000357). Moved here, which already derives
        the subject set, and Metis (evt_4dfea55c38b1c518_00000133) is why
        the plant loops every derived slug instead of one hardcoded name —
        `sorted(slugs)[0]` is 'cal' today and stays 'cal' regardless of what
        joins the set, so a single-slug plant would have reproduced the
        exact hardcode this test exists to remove, just wearing a derived
        costume. The packaging-channel resolution check moves here too —
        Argus: "it is not a darin fact either."
        """
        templates_dir = self.image / "vault" / "templates" / "companions"
        slugs: set[str] = set()
        for path in sorted(templates_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if not text.startswith("---\n"):
                continue
            end = text.find("\n---", 4)
            if end < 0:
                continue
            value = yaml.safe_load(text[4:end])
            if isinstance(value, dict) and value.get("type") == "agent":
                slugs.add(path.stem)
        self.assertGreaterEqual(
            len(slugs),
            3,
            f"expected at least cal/darin/po among the shipped companion "
            f"identity templates, found: {sorted(slugs)}",
        )
        for slug in sorted(slugs):
            with self.subTest(slug=slug):
                _assert_no_shipped_identity(self, self.image, slug)

        channels = [
            entry
            for entry in self.manifest_entries
            if entry.get("canonical_source") == "argo-os/vault/templates"
            and entry.get("source_mode") == "recursive-ship-all"
            and entry.get("output_path") == "vault/templates/"
        ]
        if self.manifest_entries:
            self.assertEqual(
                len(channels),
                1,
                "the companion bytes are present but their declared recursive "
                "template-corpus channel does not resolve exactly once",
            )
        else:
            image_manifest = json.loads(
                (self.image / "tropo-image-manifest.json").read_text(encoding="utf-8")
            )
            self.assertIn(
                "vault/templates/companions/darin.md",
                image_manifest.get("files", {}),
                "the built image manifest does not name the companion bytes",
            )

        self.assertEqual(
            _package_identity_violations(templates_dir),
            [],
        )
        for slug in sorted(slugs):
            with self.subTest(plant=slug):
                planted = self.tmp / f"identity-plant-{slug}"
                shutil.copytree(templates_dir, planted)
                target = planted / f"{slug}.md"
                text = target.read_text(encoding="utf-8")
                self.assertIn(
                    "{{uid}}", text, f"{slug}.md has no {{{{uid}}}} placeholder to plant into"
                )
                target.write_text(
                    text.replace("{{uid}}", "deadbeef", 1), encoding="utf-8"
                )
                self.assertIn(
                    f"{slug}.md",
                    _package_identity_violations(planted),
                    f"the known-positive hardcoded uid plant on {slug}.md did not trip the scan",
                )

    def test_genesis_distinct(self) -> None:
        first = self.fixture_studio("genesis-distinct-one")
        second = self.fixture_studio("genesis-distinct-two")
        one_proc, one = self.run_genesis(first)
        two_proc, two = self.run_genesis(second)
        self.assertEqual(one_proc.returncode, 0, one_proc.stderr[-1000:])
        self.assertEqual(two_proc.returncode, 0, two_proc.stderr[-1000:])
        assert one is not None and two is not None
        one_values = {
            value
            for identity in one["companions"].values()
            for value in identity.values()
        }
        two_values = {
            value
            for identity in two["companions"].values()
            for value in identity.values()
        }
        # accepts-both/derive-from-shipped class (Metis,
        # evt_4dfea55c38b1c518_00000133): both fixtures plant Po, so
        # genesis mints only cal+darin here (3 fields each = 6) — that is
        # the real, current shape, not a hardcode, and this asserts it by
        # deriving the count from what each run actually returned rather
        # than a literal that silently stops matching if the companion set
        # ever changes.
        expected_fields = 3 * len(one["companions"])
        self.assertEqual(
            len(one_values), expected_fields, "first Studio reused a companion identity"
        )
        self.assertEqual(
            len(two_values), expected_fields, "second Studio reused a companion identity"
        )
        self.assertTrue(
            one_values.isdisjoint(two_values),
            f"independent Studios share companion identity: {one_values & two_values}",
        )
        self.assertEqual(
            set(one["companions"]),
            set(two["companions"]),
            "the two fixture studios minted a different companion set",
        )
        for slug in sorted(one["companions"]):
            for field in ("uid", "party_uid", "agent_root_uid"):
                self.assertNotEqual(
                    one["companions"][slug][field],
                    two["companions"][slug][field],
                    f"two independent Studios share {slug}.{field}",
                )

        # The pairing above always plants Po (fixture_studio's default), so
        # it can never exercise the collision this test exists to prevent
        # for a companion that gets MINTED rather than planted. Pair two
        # cold boxes (no fixture Po) to close that: Metis's finding — "if
        # genesis ever produced a shared Po identity across two studios...
        # it would pass" — is about exactly this path.
        cold_one = self.fixture_studio("genesis-distinct-cold-one", po_fixture=False)
        cold_two = self.fixture_studio("genesis-distinct-cold-two", po_fixture=False)
        cold_one_proc, cold_one_payload = self.run_genesis(cold_one)
        cold_two_proc, cold_two_payload = self.run_genesis(cold_two)
        self.assertEqual(cold_one_proc.returncode, 0, cold_one_proc.stderr[-1000:])
        self.assertEqual(cold_two_proc.returncode, 0, cold_two_proc.stderr[-1000:])
        assert cold_one_payload is not None and cold_two_payload is not None
        self.assertIn("po", cold_one_payload["companions"])
        self.assertIn("po", cold_two_payload["companions"])
        for field in ("uid", "party_uid", "agent_root_uid"):
            self.assertNotEqual(
                cold_one_payload["companions"]["po"][field],
                cold_two_payload["companions"]["po"][field],
                f"two independently cold-minted Studios share po.{field}",
            )

    def test_genesis_offline(self) -> None:
        studio = self.fixture_studio("genesis-offline")
        proc, payload = self.run_genesis(studio, offline=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1400:])
        assert payload is not None
        gp = _load(
            studio / "vault" / "tools" / "lib" / "governed_path.py",
            "w6_offline_governed_path",
        )
        for slug, identity in payload["companions"].items():
            for field in ("uid", "party_uid", "agent_root_uid"):
                self.assertTrue(
                    gp.new_uid_is_valid_shape(identity[field]),
                    f"{slug}.{field} is not a complete current-shape identity",
                )
            pointer = _frontmatter(
                studio / "agents" / slug / f"{slug}-activation.md"
            )
            self.assertEqual(pointer["agent_uid"], identity["uid"])
            self.assertTrue(
                studio.joinpath("vault", "agents", f"{pointer['agent_uid']}.md").is_file()
            )
            self.assertTrue(
                studio.joinpath("vault", "files", f"{identity['party_uid']}.md").is_file()
            )
            self.assertTrue(
                studio.joinpath(
                    "vault", "files", f"{identity['agent_root_uid']}.md"
                ).is_file()
            )
            who = subprocess.run(
                [
                    sys.executable,
                    str(studio / "vault" / "tools" / "tropo-lineage.py"),
                    "--root",
                    str(studio),
                    "who",
                    "--agent",
                    slug,
                ],
                cwd=str(studio),
                env={
                    **os.environ,
                    "PYTHONPATH": str(self.tmp / "offline-python"),
                },
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(who.returncode, 0, who.stderr)
            self.assertEqual(
                json.loads(who.stdout)["gen"],
                "C1" if slug == "cal" else "D1",
            )
            drain = subprocess.run(
                [
                    sys.executable,
                    str(studio / "vault" / "tools" / "tropo-check-events.py"),
                    "--as",
                    slug,
                    "--json",
                ],
                cwd=str(studio),
                env={
                    **os.environ,
                    "PYTHONPATH": str(self.tmp / "offline-python"),
                },
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(drain.returncode, 0, drain.stderr[-600:])
        manifest = _frontmatter(studio / ".tropo" / "studio-identity.md")
        self.assertTrue(gp.is_composite_mint_prefix(str(manifest["mint_prefix"])))
        source = (studio / "vault" / "tools" / "tropo-genesis-companions.py").read_text(
            encoding="utf-8"
        )
        self.assertNotRegex(source, r"\b(?:requests|urllib|socket|httpx)\b")
        # v1.95 Spine A AC5: the tool READS the identity and never mints it — the
        # interim mint is gone; a Studio without a manifest is refused.
        self.assertNotIn("companion-genesis-interim", source)
        self.assertIn("has not run genesis", source)
        self.assertNotIn("token_hex", source)
        mint_source = (studio / "vault" / "tools" / "tropo-mint-id.py").read_text(
            encoding="utf-8"
        )
        callers = [
            node
            for node in ast.walk(ast.parse(mint_source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_generate_mint_prefix"
        ]
        self.assertEqual(
            len(callers),
            1,
            "interim prefix generation escaped the one studio-genesis writer",
        )

    def test_genesis_idempotent(self) -> None:
        studio = self.fixture_studio("genesis-idempotent")
        first_proc, first = self.run_genesis(studio)
        self.assertEqual(first_proc.returncode, 0, first_proc.stderr[-1000:])
        assert first is not None
        before = _hashes(studio, self.generated_scope(studio, first))
        second_proc, second = self.run_genesis(studio)
        self.assertEqual(second_proc.returncode, 0, second_proc.stderr[-1000:])
        assert second is not None
        after = _hashes(studio, self.generated_scope(studio, second))
        self.assertEqual(first["companions"], second["companions"])
        self.assertEqual(before, after)
        self.assertEqual(second["births"], [])
        self.assertEqual(second["created_paths"], [])
        self.assertEqual(second["pointer_updates"], [])

    def test_composed_cold_box(self) -> None:
        # No fixture Po is planted here. The package itself must carry every
        # prerequisite; otherwise this composed acceptance correctly fails.
        studio = self.fixture_studio("composed-cold-box", po_fixture=False)
        self.assertNotIn(".git", {path.name for path in studio.iterdir()})
        proc, payload = self.run_genesis(studio, offline=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1600:])
        assert payload is not None
        self.assertFalse((studio / ".tropo" / "boot-fast-path.md").exists())
        self.assertFalse((studio / ".tropo" / "boot-digest.md").exists())

        kernel_pointer = studio / ".tropo" / "playbooks" / "agent-activation.playbook.md"
        self.assertTrue(kernel_pointer.is_file())
        canonical_uid = str(_frontmatter(kernel_pointer)["canonical_substrate_uid"])
        canonical = studio / "vault" / "playbooks" / f"{canonical_uid}.md"
        self.assertTrue(canonical.is_file(), "kernel boot route has no canonical target")
        required = (
            "docs/tropo-studio-map.md",
            ".tropo/tool-catalog.md",
            ".tropo/skill-catalog.md",
            ".tropo/sa-agent-catalog.md",
            ".tropo/toolbelt.md",
            "vault/tools/tropo-studio-status.py",
        )
        for rel in required:
            self.assertIn(rel, self.package_listing, f"boot-resolved file absent: {rel}")
            self.assertTrue(studio.joinpath(rel).is_file(), rel)
        for slug, identity in payload["companions"].items():
            self.assertTrue(
                studio.joinpath("agents", slug, f"{slug}-activation.md").is_file()
            )
            entry = studio / "vault" / "agents" / f"{identity['uid']}.md"
            self.assertTrue(entry.is_file())
            body = entry.read_text(encoding="utf-8")
            for rel in required:
                self.assertIn(rel, body)

    def test_gauntlet_runs_in_built_package(self) -> None:
        shipped_suite = (
            self.image
            / "vault"
            / "tools"
            / "tests"
            / "test_companion_genesis_and_boot.py"
        )
        self.assertTrue(shipped_suite.is_file(), "the package carries no W6 gauntlet")
        proc = subprocess.run(
            [sys.executable, str(shipped_suite), "-v", "-k", "curated_edition"],
            cwd=str(self.image),
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
        self.assertIn("Ran 1 test", proc.stderr + proc.stdout)

    def test_boot_entry_point_updates(self) -> None:
        studio = self.fixture_studio("pointer-update")
        first_proc, payload = self.run_genesis(studio)
        self.assertEqual(first_proc.returncode, 0, first_proc.stderr[-1000:])
        assert payload is not None
        pointer = studio / "agents" / "cal" / "cal-activation.md"
        pointer_before = pointer.read_bytes()
        transfer = studio / "agents" / "cal" / "transfers" / "C0.md"
        transfer.write_text("customer-authored transfer\n", encoding="utf-8")
        identity = payload["companions"]["cal"]
        protected = [
            studio / "vault" / "agents" / f"{identity['uid']}.md",
            studio / "agents" / "cal" / "lineage.jsonl",
            transfer,
            *list((studio / "agents" / "cal" / ".tropo-capsule" / "memory").glob("*")),
        ]
        before = _hashes(studio, protected)
        pointer_template = (
            studio / "vault" / "templates" / "companions" / "activation-pointer.md"
        )
        pointer_template.write_text(
            pointer_template.read_text(encoding="utf-8")
            + "\nBoot contract edition: pointer-shape-two\n",
            encoding="utf-8",
        )
        second_proc, second = self.run_genesis(studio)
        self.assertEqual(second_proc.returncode, 0, second_proc.stderr[-1200:])
        assert second is not None
        self.assertNotEqual(pointer_before, pointer.read_bytes())
        self.assertIn("pointer-shape-two", pointer.read_text(encoding="utf-8"))
        self.assertEqual(before, _hashes(studio, protected))
        self.assertEqual(second["companions"], payload["companions"])

    def test_crew_memories_are_earned(self) -> None:
        crew_paths = [
            TEMPLATES / "memory-edition" / "cal-crew-memories.jsonl",
            TEMPLATES / "memory-edition" / "darin-crew-memories.jsonl",
        ]
        journal_path = os.environ.get("TROPO_COMPANION_REHEARSAL_JOURNAL")
        journal = _read_jsonl(Path(journal_path)) if journal_path else []
        defects = _crew_entries_resolve(crew_paths, journal)
        self.assertEqual(defects, [])

        planted = self.tmp / "unearned-memory.jsonl"
        planted.write_text(
            json.dumps(
                {
                    "timestamp": "2099-01-01T00:00:00Z",
                    "event_uid": "fixture-event",
                    "summary": "this event never happened",
                    "inherited_from": "origin-studio",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.assertTrue(
            _crew_entries_resolve([planted], journal),
            "an unmatched crew memory passed the earned-event gate",
        )

    def test_curated_edition(self) -> None:
        self.assertIn(
            "vault/templates/companions/COLD-WALK.md",
            self.package_listing,
            "manual cognition walk instructions did not reach the package",
        )
        # Derived, not hardcoded to ("cal", "darin") — the same class Argus
        # and Metis found across this file's coverage assertions (Po's own
        # pins existed and shipped, unchecked, until now).
        pin_slugs = sorted(
            path.stem.removesuffix("-method-pins")
            for path in (TEMPLATES / "memory-edition").glob("*-method-pins.jsonl")
        )
        self.assertGreaterEqual(len(pin_slugs), 3, pin_slugs)
        rows = {
            slug: _read_jsonl(
                TEMPLATES / "memory-edition" / f"{slug}-method-pins.jsonl"
            )
            for slug in pin_slugs
        }
        for slug, pins in rows.items():
            self.assertGreater(len(pins), 4)
            self.assertLessEqual(len(pins), 12)
            self.assertTrue(
                all(pin.get("inherited_from") == "origin-studio" for pin in pins)
            )
            constitutional = {
                str(pin.get("pin_id"))
                for pin in pins
                if pin.get("partition") == "constitutional"
            }
            self.assertEqual(constitutional, CONSTITUTIONAL)
        constitutional_by_slug = {
            slug: {
                pin["pin_id"]: pin
                for pin in pins
                if pin.get("partition") == "constitutional"
            }
            for slug, pins in rows.items()
        }
        baseline_slug, baseline = next(iter(constitutional_by_slug.items()))
        for slug, constitutional in constitutional_by_slug.items():
            self.assertEqual(
                constitutional,
                baseline,
                f"{slug}'s constitutional pins diverge from {baseline_slug}'s",
            )
        self.assertTrue({"build", "verify"} <= {p["partition"] for p in rows["cal"]})
        self.assertTrue({"walk", "decision"} <= {p["partition"] for p in rows["darin"]})
        self.assertTrue({"greet", "route"} <= {p["partition"] for p in rows["po"]})
        forbidden = re.compile(
            r"\b(?:argo|mike|metis|vela|argus|talos|orpheus|cosmo|v\d+\.\d+|release)\b",
            re.IGNORECASE,
        )
        for path in (TEMPLATES / "memory-edition").glob("*method-pins.jsonl"):
            self.assertIsNone(
                forbidden.search(path.read_text(encoding="utf-8")),
                f"{path.name} retains origin-specific context",
            )

    def test_crew_cross_resolution(self) -> None:
        for slug, peer_placeholder in (
            ("cal", "{{darin_party_uid}}"),
            ("darin", "{{cal_party_uid}}"),
        ):
            shipped = (TEMPLATES / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn(peer_placeholder, shipped)
            self.assertIn("{{po_party_uid}}", shipped)
            self.assertIn("tropo-companion-crew:start", shipped)
        studio = self.fixture_studio("crew-cross-resolution")
        proc, payload = self.run_genesis(studio)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
        assert payload is not None
        genesis_module = _load(
            studio / "vault" / "tools" / "tropo-genesis-companions.py",
            "w6_genesis_validation",
        )
        genesis_module.validate_crew_resolution(studio)

        negative = self.fixture_studio("crew-cross-resolution-negative")
        self.mint_founder(negative)
        with self.assertRaises(genesis_module.CompanionGenesisError):
            genesis_module.genesis(negative, write_po_crew=False)
        po = next(
            path
            for path in (negative / "vault" / "agents").glob("*.md")
            if str(_frontmatter(path).get("agent") or "") == "po"
        )
        # Po's block (rendered empty by --po) gained neither companion.
        for relationship in genesis_module.CREW_RELATIONSHIPS.values():
            self.assertNotIn(relationship, po.read_text(encoding="utf-8"))

    # v1.95 Spine A AC5 — the cold-walk defects Mike ruled "cure and cut
    # candidate #3" (D2/D3). Each of these is RED on the pre-cure tool: `--po`
    # and `--accept` were not flags, the born companions were owned by a
    # placeholder, and no birth landed on the bus.

    def test_po_flag_mints_po_alone_so_the_offer_can_be_written(self) -> None:
        """D2: on a fresh box Po has no party identity, so the documented
        offer emit (`--as po`) fails before the offer. `--po` mints her
        registry row and unified entry and nothing else; a second run is a
        no-op; the same emit then lands."""
        studio = self.fixture_studio("po-flag", po_fixture=False)
        self.first_boot(studio)
        founder = self.mint_founder(studio)
        offer = {"offered": ["cal", "darin"], "founder_principal_uid": founder}
        # Negative control: the box as shipped cannot resolve `--as po`.
        before = self.emit_as_po(studio, OFFER_MADE, founder, offer)
        self.assertNotEqual(before.returncode, 0, "the offer emit landed before Po had a party")
        self.assertIn(
            "ERROR: --as 'po' resolves to no unified entry in vault/agents/ or user agent "
            "in agent-registry.yaml (check spelling)",
            before.stderr,
        )
        self.assertEqual([e for e in _events(studio) if e["type"] == OFFER_MADE], [])

        proc = subprocess.run(
            self.genesis_command(studio, "--po"),
            cwd=str(studio), capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["births"], ["po"])
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(payload["activated"], {})
        self.assertEqual(set(payload["companions"]), {"po"})
        po_party = payload["companions"]["po"]["party_uid"]
        for slug in ("cal", "darin"):
            self.assertFalse((studio / "agents" / slug).exists(), f"--po birthed {slug}")
        self.assertEqual(_agent_slugs(studio) & {"cal", "darin", "po"}, {"po"})
        # Po's own birth keeps its crew broadcast; she is never "activated"
        # for the founder — that record is a companion's acceptance.
        self.assertNotIn(ACTIVATED, [e["type"] for e in _events(studio)])
        registry = yaml.safe_load(
            (studio / ".tropo-studio" / "registries" / "agent-registry.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn(po_party, registry["agents"])
        self.assertEqual(registry["agents"][po_party]["name"], "po")
        self.assertEqual(
            {str(row.get("name")) for row in registry["agents"].values()} & {"cal", "darin"},
            set(),
        )

        again = subprocess.run(
            self.genesis_command(studio, "--po"),
            cwd=str(studio), capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(again.returncode, 0, again.stderr[-800:])
        self.assertTrue(json.loads(again.stdout)["po_already_present"])
        self.assertIn("already present", again.stderr + again.stdout)
        self.assertEqual(_agent_slugs(studio) & {"cal", "darin", "po"}, {"po"})

        after = self.emit_as_po(studio, OFFER_MADE, founder, offer)
        self.assertEqual(after.returncode, 0, after.stderr[-800:])
        offers = [e for e in _events(studio) if e["type"] == OFFER_MADE]
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]["source_uid"], po_party)
        self.assertEqual(offers[0]["subject"], founder)

    def test_accept_cal_alone_is_owned_by_the_founder_and_born_on_the_bus(self) -> None:
        """D3: --accept cal materialises Cal only, owned by the founder
        principal, with exactly one tropo.agent.activated from Cal's own
        party addressed to the founder; Cal pairs with Po and Po with Cal;
        a second run adds nothing and Darin never appears."""
        studio = self.fixture_studio("accept-cal")
        founder = self.mint_founder(studio)
        proc, payload = self.run_genesis(studio, accept="cal")
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
        assert payload is not None
        self.assertEqual(payload["accepted"], ["cal"])
        self.assertEqual(payload["births"], ["cal"])
        self.assertEqual(payload["founder_principal_uid"], founder)
        self.assertEqual(set(payload["companions"]), {"cal"})
        self.assertTrue((studio / "agents" / "cal" / "cal-activation.md").is_file())
        self.assertFalse((studio / "agents" / "darin").exists())
        self.assertEqual(_agent_slugs(studio) & {"cal", "darin"}, {"cal"})

        # All THREE of a born companion's records name the founder as owner
        # (Vela's AC5 record f0157550b31b lines 304-334: the charter had no
        # owner, the agent-root owned itself, the principal said studio-owner).
        identity = payload["companions"]["cal"]
        records = {
            "unified charter": studio / "vault" / "agents" / f"{identity['uid']}.md",
            "companion principal": studio / "vault" / "files" / f"{identity['party_uid']}.md",
            "agent-root project": studio / "vault" / "files" / f"{identity['agent_root_uid']}.md",
        }
        for label, path in records.items():
            self.assertEqual(
                str(_frontmatter(path).get("owner")), founder,
                f"Cal's {label} ({path.name}) is not owned by the founder principal",
            )
        activated = [e for e in _events(studio) if e["type"] == ACTIVATED]
        self.assertEqual(len(activated), 1, activated)
        self.assertEqual(activated[0]["source"], "/agents/cal")
        self.assertEqual(activated[0]["source_uid"], identity["party_uid"])
        self.assertEqual(activated[0]["subject"], founder)
        self.assertEqual(activated[0]["data"]["agent"], "cal")
        self.assertEqual(set(payload["activated"]), {"cal"})

        genesis_module = _load(
            studio / "vault" / "tools" / "tropo-genesis-companions.py",
            "w6_accept_cal_validation",
        )
        gp = _load(
            studio / "vault" / "tools" / "lib" / "governed_path.py",
            "w6_accept_cal_governed_path",
        )
        genesis_module.validate_crew_resolution(studio)
        po_party = self.mint_po(studio)
        cal_entry = studio / "vault" / "agents" / f"{identity['uid']}.md"
        self.assertEqual(genesis_module._crew_values(cal_entry, gp, 1), [po_party])
        po_entry = next(
            path
            for path in (studio / "vault" / "agents").glob("*.md")
            if str(_frontmatter(path).get("agent") or "") == "po"
        )
        self.assertEqual(genesis_module._crew_values(po_entry, gp, 1), [identity["party_uid"]])

        again, second = self.run_genesis(studio, accept="cal")
        self.assertEqual(again.returncode, 0, again.stderr[-1200:])
        assert second is not None
        self.assertEqual(second["births"], [])
        self.assertEqual(second["activated"], {})
        self.assertEqual(second["companions"], payload["companions"])
        self.assertEqual(len([e for e in _events(studio) if e["type"] == ACTIVATED]), 1)
        self.assertFalse((studio / "agents" / "darin").exists())

    def test_accept_refuses_without_a_founder_and_writes_nothing(self) -> None:
        """D3: no founder principal means §1.5 has not run; --accept refuses,
        names the cure, and leaves the Studio byte-for-byte as it found it."""
        studio = self.fixture_studio("accept-no-founder")
        tree = [p for p in _tree_files(studio) if "__pycache__" not in p.parts]
        before = _hashes(studio, tree)
        proc, payload = self.run_genesis(studio, accept="cal", founder=False)
        self.assertNotEqual(proc.returncode, 0, "genesis accepted a companion with no founder")
        self.assertIsNone(payload)
        self.assertIn("no founder principal", proc.stderr)
        self.assertIn("--founder", proc.stderr)
        after_tree = [p for p in _tree_files(studio) if "__pycache__" not in p.parts]
        self.assertEqual(_hashes(studio, after_tree), before, "the refusal wrote something")
        self.assertFalse((studio / "agents" / "cal").exists())
        self.assertEqual(_agent_slugs(studio) & {"cal", "darin"}, set())
        self.assertEqual([e for e in _events(studio) if e["type"] == ACTIVATED], [])

    def test_decline_is_real_and_leaves_no_companion(self) -> None:
        """AC5's decline path as documented: --po, then the offer_made and
        offer_declined emits both land, and no companion exists anywhere."""
        studio = self.fixture_studio("decline")
        founder = self.mint_founder(studio)
        offer = {"offered": ["cal", "darin"], "founder_principal_uid": founder}
        made = self.emit_as_po(studio, OFFER_MADE, founder, offer)
        self.assertEqual(made.returncode, 0, made.stderr[-800:])
        declined = self.emit_as_po(studio, OFFER_DECLINED, founder, {**offer, "reason": None})
        self.assertEqual(declined.returncode, 0, declined.stderr[-800:])
        types = [e["type"] for e in _events(studio)]
        self.assertEqual(types.count(OFFER_MADE), 1)
        self.assertEqual(types.count(OFFER_DECLINED), 1)
        self.assertNotIn(ACTIVATED, types)
        for slug in ("cal", "darin"):
            self.assertFalse((studio / "agents" / slug).exists(), f"agents/{slug} exists after a decline")
        self.assertEqual(_agent_slugs(studio) & {"cal", "darin"}, set())
        registry = yaml.safe_load(
            (studio / ".tropo-studio" / "registries" / "agent-registry.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            {str(row.get("name")) for row in registry["agents"].values()} & {"cal", "darin"},
            set(),
        )

    def test_exemplar_retired(self) -> None:
        old_prefix = OLD_AGENT_REL + "/"
        self.assertFalse(
            any(path.startswith(old_prefix) for path in self.package_listing),
            "the retired exemplar is still present in the complete package listing",
        )
        receipt = (
            ROOT
            / "recycle"
            / "agent-deletions"
            / "2026-08-31"
            / "recycle.log"
        )
        if receipt.is_file():
            receipt_text = receipt.read_text(encoding="utf-8")
            self.assertIn("uid:example", receipt_text)
            self.assertIn(
                "replace the non-bootable exemplar with locally genesised Cal and Darin",
                receipt_text,
            )
            self.assertIn("moved_from:" + OLD_AGENT_REL, receipt_text)
        else:
            self.assertTrue(
                (ROOT / "tropo-image-manifest.json").is_file(),
                "origin recycle receipt is absent outside a built image",
            )

        known = (
            "vault/tools/tests/test_derived_row_title.py",
            "vault/templates/tropo-agent-configurator.template.md",
        )
        for rel in known:
            self.assertIn(rel, self.package_listing, f"known shipped reference site absent: {rel}")
            self.assertNotIn(
                OLD_AGENT_REL,
                (self.image / rel).read_text(encoding="utf-8"),
                f"{rel} still points at the retired exemplar",
            )
        shipped_hits = []
        for path in _tree_files(self.image):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if OLD_AGENT_REL in text:
                shipped_hits.append(path.relative_to(self.image).as_posix())
        self.assertEqual(shipped_hits, [], f"shipped old-path references remain: {shipped_hits}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
