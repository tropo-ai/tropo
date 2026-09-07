#!/usr/bin/env python3
"""v1.95 Spine A — Identity and arrival (dev-spec f015de6b3a18).

AC1 ONLY in this file so far: THE BUILD STOPS MINTING INSIDE THE BOX.

The measurement this cures: two independent extractions of v1.94 boxes both
carried studio_id b4e250caf19a. Cause, traced through the tools: build-release
Step 9b runs the SHIPPED tropo-rebuild-vault.py inside the assembled box (it
exists to regenerate 00-tropo-nav/ from the shipped ledger), which reaches
tropo-rebuild-index.py, whose two genesis gates are presence-only — no
.tropo/studio-identity.md → mint one; no vault-entity record → mint the starter
pair. Every box therefore left the build carrying one identical Studio identity.

Mike ruled 2026-09-05 (f015e5ee0ede §RULED): genesis is unchanged, only WHEN it
runs changed. --no-genesis suppresses both legs for the in-box rebuild, and
assert_no_studio_identity() proves the OUTCOME before the zip rather than
trusting the flag.

Classes:
  RebuildIndex — the flag itself: it skips both gates, and rebuild-vault
                 forwards it on both of the argv builds it constructs.
  BuiltBox     — the guard and the box contents.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

REBUILD_INDEX_PATH = TOOLS / "tropo-rebuild-index.py"
REBUILD_VAULT_PATH = TOOLS / "tropo-rebuild-vault.py"
BUILD_RELEASE_PATH = TOOLS / "tropo-build-release.py"

# rebuild-index exits 8 on this kind of bare fixture: "index written; substrate
# has known FAIL findings" (B8, v1.62 — here, the fixture has no vault/capsules).
# The WRITE succeeded, which is the only thing these tests read. build-release's
# own Step 9b treats 0 and 8 identically for exactly this reason.
_INDEX_WROTE = (0, 8)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _minimal_studio(root: Path) -> None:
    """Just enough scaffolding for the rebuild to run: a .tropo/ dir, a
    STUDIO.md, one ordinary governed source. No manifest, no vault-entity —
    the virgin shape both genesis gates fire on. Same fixture shape as
    test_studio_genesis_first_boot.py's _minimal_studio."""
    (root / ".tropo").mkdir(parents=True, exist_ok=True)
    (root / "STUDIO.md").write_text(
        "---\n"
        "uid: 5747d1a0\n"
        "tier: vault\n"
        "vault_name: v1.95 Spine A Fixture Studio\n"
        "---\n"
        "# v1.95 Spine A Fixture Studio\n",
        encoding="utf-8",
    )
    files = root / "vault" / "files"
    files.mkdir(parents=True, exist_ok=True)
    (files / "11111111.md").write_text(
        "---\n"
        'uid: "11111111"\n'
        "type: note\n"
        'title: "fixture source"\n'
        "state: active\n"
        "status: active\n"
        "created: '2026-09-01'\n"
        "modified: '2026-09-01'\n"
        "schema_version: 2\n"
        "---\n"
        "# fixture source\n",
        encoding="utf-8",
    )


def _index_records(root: Path) -> list[dict]:
    index_path = root / "vault" / "00-index.jsonl"
    if not index_path.is_file():
        return []
    out = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


def _has_vault_entity(root: Path) -> bool:
    return any(
        r.get("type") == "entity" and r.get("subtype") == "vault-entity"
        for r in _index_records(root)
    )


def _has_inbox_project(root: Path) -> bool:
    return any(
        r.get("type") == "project" and r.get("title") == "01-studio-inbox"
        for r in _index_records(root)
    )


class RebuildIndex(unittest.TestCase):
    """The flag: rebuild-index skips both genesis gates under --no-genesis,
    and rebuild-vault forwards it on BOTH argv builds it constructs."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="v195-ac1-rebuild-")
        self.tmp = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_rebuild_index(self, root: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(REBUILD_INDEX_PATH),
                "--apply",
                "--skip-rehydrate",
                "--vault-path",
                str(root),
                *extra,
            ],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=300,
        )

    def test_no_genesis_flag_skips_both_gates(self) -> None:
        """THE FLAG CONTROL, both arms in one test: with --no-genesis neither
        artifact appears; without it, on an identical fresh fixture, both do.
        The second arm is what makes the first mean anything — it proves the
        gates were live and the flag is what suppressed them."""
        suppressed = self.tmp / "suppressed"
        suppressed.mkdir()
        _minimal_studio(suppressed)
        result = self._run_rebuild_index(suppressed, "--no-genesis")
        self.assertIn(
            result.returncode, _INDEX_WROTE,
            f"rebuild-index --no-genesis exited {result.returncode}\n{result.stderr[-2000:]}",
        )
        self.assertTrue(
            (suppressed / "vault" / "00-index.jsonl").is_file(),
            "the index must still be written — --no-genesis suppresses genesis, not the rebuild",
        )
        self.assertFalse(
            (suppressed / ".tropo" / "studio-identity.md").exists(),
            "--no-genesis must not mint the Studio manifest",
        )
        self.assertFalse(
            _has_vault_entity(suppressed),
            "--no-genesis must not mint the starter vault-entity",
        )
        self.assertFalse(
            _has_inbox_project(suppressed),
            "--no-genesis must not mint the 01-studio-inbox project",
        )

        genesised = self.tmp / "genesised"
        genesised.mkdir()
        _minimal_studio(genesised)
        control = self._run_rebuild_index(genesised)
        self.assertIn(
            control.returncode, _INDEX_WROTE,
            f"rebuild-index (no flag) exited {control.returncode}\n{control.stderr[-2000:]}",
        )
        self.assertTrue(
            (genesised / ".tropo" / "studio-identity.md").is_file(),
            "without the flag the manifest gate must still mint (genesis is unchanged)",
        )
        self.assertTrue(
            _has_vault_entity(genesised),
            "without the flag the pair gate must still mint the vault-entity",
        )
        self.assertTrue(
            _has_inbox_project(genesised),
            "without the flag the pair gate must still mint the inbox project",
        )

    def test_rebuild_vault_forwards_flag_on_both_branches(self) -> None:
        """rebuild-vault builds argv for rebuild-index in TWO places — the
        --only early-return passthrough and the full pipeline. The flag must
        reach both; missing one leaves a live minting path into the box.

        Seam: rebuild-vault calls subprocess.run for the validator pre-step and
        then for rebuild-index. We replace that name in the loaded module,
        capture the argv, and raise a sentinel the moment the rebuild-index
        command is constructed — the pipeline past that point is not under test."""
        root = self.tmp / "forwarding"
        root.mkdir()
        _minimal_studio(root)

        class _Captured(Exception):
            def __init__(self, cmd):
                super().__init__("captured")
                self.cmd = cmd

        class _FakeResult:
            returncode = 0
            stdout = "Summary: fixture\n"
            stderr = ""

        def _argv_for(*cli_args: str) -> list[str]:
            module = _load(f"v195_rebuild_vault_{abs(hash(cli_args))}", REBUILD_VAULT_PATH)
            captured: list[list[str]] = []

            def fake_run(cmd, *args, **kwargs):
                captured.append(list(cmd))
                if str(module.REBUILD_INDEX) in [str(part) for part in cmd]:
                    raise _Captured(list(cmd))
                return _FakeResult()

            # `module.subprocess` IS the shared subprocess module, so assigning
            # .run here replaced it PROCESS-WIDE and nothing put it back: every
            # later test in this file that shelled out silently received
            # returncode 0 / "Summary: fixture" instead of running anything.
            # Found 2026-09-05 (talos-t62) when the Founder tests passed alone
            # and failed in suite order — the loud direction. The quiet one is
            # worse: a later test that only asserts returncode == 0 passes by
            # stub. Restored in the same finally that restores sys.argv.
            run_backup = module.subprocess.run
            module.subprocess.run = fake_run
            argv_backup = sys.argv[:]
            sys.argv = ["tropo-rebuild-vault.py", *cli_args]
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    module.main()
            except _Captured as exc:
                return exc.cmd
            finally:
                sys.argv = argv_backup
                module.subprocess.run = run_backup
            self.fail(f"rebuild-vault never invoked rebuild-index for {cli_args!r}; saw {captured!r}")

        only_with = _argv_for("--only", "11111111", "--vault-path", str(root), "--no-genesis")
        self.assertIn("--only", only_with)
        self.assertIn("--no-genesis", only_with, "the --only branch dropped the flag")

        full_with = _argv_for("--apply", "--vault-path", str(root), "--no-genesis")
        self.assertNotIn("--only", full_with)
        self.assertIn("--no-genesis", full_with, "the full pipeline dropped the flag")

        # Absent when not passed — the flag is opt-in on both branches, so an
        # ordinary customer or working-Studio rebuild still genesises.
        only_without = _argv_for("--only", "11111111", "--vault-path", str(root))
        self.assertNotIn("--no-genesis", only_without)
        full_without = _argv_for("--apply", "--vault-path", str(root))
        self.assertNotIn("--no-genesis", full_without)


class BuiltBox(unittest.TestCase):
    """The guard and the box contents.

    FIXTURE, DECLARED AS SUCH: a full tropo-build-release.py run is far too
    heavy for a unit test (it walks the whole ship scope, composes an index,
    and zips). These tests exercise assert_no_studio_identity() and Step 9b's
    argv directly against a fixture build_dir shaped like the post-Step-9b box:
    00-tropo-nav/ present, a small vault/00-index.jsonl, no manifest, no pair.
    One real build is run separately by the dispatcher, where the entry-count
    floor (>1,000 zip entries) is the assertion this fixture cannot make."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = _load("v195_build_release", BUILD_RELEASE_PATH)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="v195-ac1-box-")
        self.build_dir = Path(self._tmp.name).resolve()
        nav = self.build_dir / "00-tropo-nav" / "by-type" / "note"
        nav.mkdir(parents=True)
        (nav / "11111111.md").write_text("# nav entry\n", encoding="utf-8")
        (self.build_dir / ".tropo").mkdir()
        vault = self.build_dir / "vault"
        vault.mkdir()
        (vault / "00-index.jsonl").write_text(
            json.dumps({"uid": "11111111", "type": "note", "title": "fixture source",
                        "path": "vault/files/11111111.md"}) + "\n"
            + json.dumps({"uid": "5747d1a0", "type": "document", "title": "STUDIO",
                          "path": "STUDIO.md"}) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _plant_manifest(self) -> Path:
        path = self.build_dir / ".tropo" / "studio-identity.md"
        path.write_text(
            "---\nstudio_id: b4e250caf19a\nmint_prefix: b4e2\n"
            "entity_name: argo-os\n---\n# Studio identity\n",
            encoding="utf-8",
        )
        return path

    def _plant_vault_entity_record(self) -> None:
        index_path = self.build_dir / "vault" / "00-index.jsonl"
        with index_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "uid": "b4e2b7f272e8", "type": "entity", "subtype": "vault-entity",
                "title": "Your Tropo Vault", "path": "vault/files/b4e2b7f272e8.md",
            }) + "\n")

    def _guard(self) -> tuple[int, str]:
        """Run the guard; return (exit code, stderr). 0 means it passed."""
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            try:
                self.build.assert_no_studio_identity(str(self.build_dir))
            except SystemExit as exc:
                return int(exc.code or 0), err.getvalue()
        return 0, err.getvalue()

    def test_zip_is_nontrivial_carries_nav_and_no_manifest_no_pair(self) -> None:
        """PRESENCE FIRST. 00-tropo-nav/ — the whole reason Step 9b exists — is
        present and non-empty; the index is present; ONLY THEN the absences.
        An empty box must not be able to pass this by having nothing in it."""
        nav = self.build_dir / "00-tropo-nav"
        self.assertTrue(nav.is_dir(), "00-tropo-nav/ absent — Step 9b's own output")
        self.assertTrue(
            any(nav.rglob("*.md")),
            "00-tropo-nav/ carries no entries; presence is not satisfied by an empty dir",
        )
        records = _index_records(self.build_dir)
        self.assertGreater(len(records), 0, "the box index is empty; the absences below would be vacuous")

        self.assertFalse((self.build_dir / ".tropo" / "studio-identity.md").exists())
        self.assertFalse(_has_vault_entity(self.build_dir))
        self.assertFalse(_has_inbox_project(self.build_dir))

        # And Step 9b's argv is the reason: the shipped rebuilder is invoked with
        # --no-genesis. Read from the source, since running the real Step 9b here
        # would mean running a build.
        source = BUILD_RELEASE_PATH.read_text(encoding="utf-8")
        step_9b = source.split("def step_9b_regenerate_tropo_nav(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("'--no-genesis'", step_9b,
                      "Step 9b does not pass --no-genesis to the in-box rebuild")

        code, _ = self._guard()
        self.assertEqual(code, 0, "the clean fixture box must pass the guard")

    def test_guard_refuses_planted_manifest(self) -> None:
        planted = self._plant_manifest()
        self.assertTrue(planted.is_file())
        code, err = self._guard()
        self.assertNotEqual(code, 0, "the guard accepted a box carrying a Studio manifest")
        self.assertIn("studio-identity.md", err, "the refusal does not name the offending artifact")

    def test_guard_refuses_planted_vault_entity_record(self) -> None:
        self._plant_vault_entity_record()
        code, err = self._guard()
        self.assertNotEqual(code, 0, "the guard accepted a box carrying a vault-entity record")
        self.assertIn("vault-entity", err, "the refusal does not name the offending record")
        self.assertIn("b4e2b7f272e8", err, "the refusal does not identify WHICH record")

    def test_guard_accepts_both_plants_when_removed(self) -> None:
        """THE NEGATIVE CONTROL. Plant both, prove the refusal, remove both,
        prove the pass — so the two refusals above are the guard doing its job
        and not the fixture failing for some unrelated reason."""
        self._plant_manifest()
        self._plant_vault_entity_record()
        code, err = self._guard()
        self.assertNotEqual(code, 0)
        self.assertIn("studio-identity.md", err)
        self.assertIn("vault-entity", err)

        (self.build_dir / ".tropo" / "studio-identity.md").unlink()
        index_path = self.build_dir / "vault" / "00-index.jsonl"
        kept = [
            line for line in index_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and '"subtype": "vault-entity"' not in line
        ]
        index_path.write_text("\n".join(kept) + "\n", encoding="utf-8")

        code, err = self._guard()
        self.assertEqual(code, 0, f"the guard refused a clean box: {err}")


# (the module entry point is main() at the end of this file: unittest by default,
#  --arrival-walk for AC9's composed walk)


# ---------------------------------------------------------------------------
# AC2 / AC3 / AC7(b) — genesis in Po's greeting, the identity check as a step in
# both boot paths, the studio named after the greeting, links not shell commands.
# argus-a171, 2026-09-05.
# ---------------------------------------------------------------------------

STUDIO_ROOT = TOOLS.parents[1]
ACTIVATE = STUDIO_ROOT / ".tropo" / "concierge" / "activate.md"
PLAYBOOK = STUDIO_ROOT / "vault" / "playbooks" / "99341618.md"
FAST_PATH = STUDIO_ROOT / ".tropo" / "boot-fast-path.md"
START_TROPO = STUDIO_ROOT / "vault" / "templates" / "root-docs" / "START-TROPO.md"
README = STUDIO_ROOT / "vault" / "templates" / "root-docs" / "README.md"
STATUS_PATH = TOOLS / "tropo-studio-status.py"


class IdentityCheck(unittest.TestCase):
    """AC2(b): tropo-studio-status.py gains section_identity() — one [WARN] naming
    the cure when the manifest is absent or malformed; nothing when present."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.status = _load("v195_status", STATUS_PATH)

    def _scratch(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="v195-identity-")).resolve()
        self.addCleanup(shutil.rmtree, root, True)
        (root / ".tropo").mkdir()
        (root / "vault" / "tools").mkdir(parents=True)
        shutil.copy(TOOLS / "tropo-mint-id.py", root / "vault" / "tools" / "tropo-mint-id.py")
        return root

    def test_silent_when_this_studio_has_its_identity(self) -> None:
        title, lines = self.status.section_identity()
        self.assertEqual(title, "studio identity")
        self.assertEqual(lines, [])

    def test_warns_and_names_the_cure_when_the_manifest_is_absent(self) -> None:
        _title, lines = self.status.section_identity(str(self._scratch()))
        self.assertTrue(lines and lines[0].startswith("  [WARN] studio identity:"))
        self.assertIn("tropo-rebuild-index.py --apply --vault-path .", " ".join(lines))
        self.assertIn("Po", " ".join(lines))

    def test_warns_when_the_manifest_is_malformed(self) -> None:
        root = self._scratch()
        (root / ".tropo" / "studio-identity.md").write_text("---\nstudio_id: nope\n---\n")
        _title, lines = self.status.section_identity(str(root))
        self.assertTrue(lines and "[WARN]" in lines[0])

    def test_main_reports_the_section(self) -> None:
        src = STATUS_PATH.read_text(encoding="utf-8")
        self.assertIn("section_identity(),", src)   # wired into sections, not merely defined


class BothBootPathsRunTheCheck(unittest.TestCase):
    """AC2(b): a NEW numbered step in both boot paths; neither ran it before."""

    def test_concierge_step_0d_runs_it_and_routes_to_the_rebuild(self) -> None:
        text = ACTIVATE.read_text(encoding="utf-8")
        self.assertIn("**0d. Studio identity check", text)
        self.assertIn("tropo-studio-status.py --as po --no-emit", text)

    def test_playbook_step_0_0d_halts_and_routes_to_po(self) -> None:
        text = PLAYBOOK.read_text(encoding="utf-8")
        self.assertIn("#### Step 0.0d — Studio Identity Check", text)
        self.assertIn("route to Po by name", text)

    def test_fast_path_carries_the_step_and_is_fresh(self) -> None:
        self.assertIn("STUDIO IDENTITY CHECK", FAST_PATH.read_text(encoding="utf-8"))


class PoRunsGenesisAndNamesTheStudio(unittest.TestCase):
    """AC2(a)+(c), AC3: Po runs the rebuild herself; the templates stop telling
    the user to; §1.5 sets the entity name after vault_name."""

    def test_activate_no_longer_tells_the_user_to_run_and_restart(self) -> None:
        text = ACTIVATE.read_text(encoding="utf-8")
        self.assertNotIn("then restart this session", text)
        self.assertIn("YOU run genesis, not the user", text)

    def test_section_1_5_sets_the_entity_name_after_vault_name(self) -> None:
        text = ACTIVATE.read_text(encoding="utf-8")
        i = text.index("### 1.5 STUDIO.md Bootstrap")
        j = text.index("### 1.5b")
        self.assertIn('tropo-mint-id.py --set-entity-name "<vault_name>"', text[i:j])

    def test_templates_carry_no_manual_rebuild_step(self) -> None:
        for path in (START_TROPO, README):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("```bash\npython3 vault/tools/tropo-rebuild-index.py", text)
                self.assertIn("Po", text)


class LinksNotShellCommands(unittest.TestCase):
    """AC7(b), Mike-ruled 2026-09-05: Po renders a clickable link, else an absolute
    path, never a shell command — activate.md :108 and :319 reversed."""

    def test_both_deliver_the_render_rules_are_reversed(self) -> None:
        full = ACTIVATE.read_text(encoding="utf-8")
        text = full[:full.index("## Changelog")]   # history rows keep the old wording on purpose
        self.assertEqual(text.count("clickable link"), 2)
        self.assertNotIn("hand them the one command that opens it", text)
        self.assertNotIn("hand the user the one command that opens it", text)
        self.assertNotIn("`open <path>`", text)


# ---------------------------------------------------------------------------
# AC5 (tool half), AC6, AC7 — argus-a171, 2026-09-05.
# ---------------------------------------------------------------------------

BASELINE = STUDIO_ROOT / "vault" / "templates" / ".tropo-studio-skeleton" / "operating-principles.md"
CLAUDE_TEMPLATE = STUDIO_ROOT / "vault" / "templates" / "root-docs" / "CLAUDE.md"
PREFLIGHT_PATH = TOOLS / "tropo-release-preflight.py"
COMPANIONS_PATH = TOOLS / "tropo-genesis-companions.py"


class PrinciplesShipWhole(unittest.TestCase):
    """AC6, Mike-ruled at the walk: the baseline ships the principles WHOLE —
    the Founding Principle and 1–15 — with §Adapting telling a new studio it may remove."""

    def test_baseline_carries_the_founding_principle_and_all_fifteen(self) -> None:
        text = BASELINE.read_text(encoding="utf-8")
        self.assertIn("## The Founding Principle: Extreme Portability", text)
        for n in range(1, 16):
            self.assertTrue(__import__("re").search(r"^## %d\. " % n, text, __import__("re").M),
                            "principle %d missing from the baseline" % n)
        self.assertIn("## 14. Memory Writes Use Tropo Memory, Not Harness Memory", text)
        self.assertIn("## 15. Ask Before You Assume You Cannot Dispatch", text)
        self.assertIn("## Adapting these principles to your vault", text)
        self.assertIn("Remove", text[text.index("## Adapting"):])

    def test_baseline_tracks_the_studio_file_section_for_section(self) -> None:
        real = (STUDIO_ROOT / ".tropo-studio" / "operating-principles.md").read_text(encoding="utf-8")
        real_heads = [l for l in real.splitlines() if l.startswith("## ")]
        base_heads = [l for l in BASELINE.read_text(encoding="utf-8").splitlines() if l.startswith("## ")]
        self.assertEqual(base_heads[:len(real_heads)], real_heads)


class Position1ReachesBothBootPaths(unittest.TestCase):
    """AC6: Position 1 stated INLINE in 99341618 Step 2.5 and in activate.md; the
    CLAUDE.md template ships §Memory Writes (the second surface the capsule names)."""

    def test_playbook_step_2_5_states_it(self) -> None:
        text = PLAYBOOK.read_text(encoding="utf-8")
        i = text.index("#### Step 2.5"); j = text.index("#### Step 2.6") if "#### Step 2.6" in text else i + 6000
        self.assertIn("Position 1", text[i:j])
        self.assertIn("tropo-memory-write", text[i:j])

    def test_concierge_governance_states_it(self) -> None:
        text = ACTIVATE.read_text(encoding="utf-8")
        i = text.index("### Governance"); j = text.index("### File creation protocol")
        self.assertIn("never a harness-private store", text[i:j])
        self.assertIn("tropo-memory-write", text[i:j])

    def test_claude_template_ships_memory_writes(self) -> None:
        self.assertIn("## Memory Writes Go to Tropo Memory", CLAUDE_TEMPLATE.read_text(encoding="utf-8"))


class ReachabilityRows(unittest.TestCase):
    """AC7: at least five rows registered (floor), and none can pass on an empty box."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.preflight = _load("v195_preflight_ac7", PREFLIGHT_PATH)
        cls.registry = cls.preflight.build_registry()

    ROWS = ("build-doc-currency", "build-no-shell-instructions", "build-changelog-names-version",
            "build-memory-surfaces", "build-no-studio-identity")

    def _box(self) -> Path:
        box = Path(tempfile.mkdtemp(prefix="v195-ac7-box-")).resolve()
        self.addCleanup(shutil.rmtree, box, True)
        return box

    def _run(self, box, version="9.9.9"):
        return {o.gate_id: o for o in self.registry.run_phase(
            "candidate", {"source_tree": str(STUDIO_ROOT), "extracted_tree": str(box),
                          "version_string": version})}

    def test_at_least_five_rows_are_registered_at_candidate(self) -> None:
        ids = {g.gate_id for g in self.registry.gates_for_phase("candidate")}
        for row in self.ROWS:
            self.assertIn(row, ids)
        self.assertGreaterEqual(len(set(self.ROWS) & ids), 5)

    def test_no_row_passes_on_an_empty_box(self) -> None:
        out = self._run(self._box())
        for row in ("build-doc-currency", "build-no-shell-instructions",
                    "build-changelog-names-version", "build-memory-surfaces"):
            with self.subTest(row=row):
                self.assertEqual(out[row].verdict, "refused", out[row].detail)

    def test_memory_surfaces_and_changelog_pass_when_shipped(self) -> None:
        box = self._box()
        (box / ".tropo-studio").mkdir()
        shutil.copy(BASELINE, box / ".tropo-studio" / "operating-principles.md")
        shutil.copy(CLAUDE_TEMPLATE, box / "CLAUDE.md")
        (box / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [9.9.9] - 2026-09-05\n- x\n")
        out = self._run(box)
        self.assertEqual(out["build-memory-surfaces"].verdict, "pass", out["build-memory-surfaces"].detail)
        self.assertEqual(out["build-changelog-names-version"].verdict, "pass")
        (box / "CLAUDE.md").write_text("# no memory section\n")
        self.assertEqual(self._run(box)["build-memory-surfaces"].verdict, "refused")

    def test_shell_instruction_row_refuses_a_planted_open_command(self) -> None:
        box = self._box()
        (box / ".tropo" / "concierge").mkdir(parents=True)
        (box / ".tropo" / "concierge" / "activate.md").write_text(
            "# Po\n\n- Deliver the render: hand them a clickable link.\n")
        self.assertEqual(self._run(box)["build-no-shell-instructions"].verdict, "pass")
        (box / ".tropo" / "concierge" / "activate.md").write_text(
            "# Po\n\n- Deliver the render: on macOS, `open <path>` pops it into their browser.\n")
        out = self._run(box)["build-no-shell-instructions"]
        self.assertEqual(out.verdict, "refused")
        self.assertIn("activate.md:3", out.detail)

    def test_doc_currency_row_refuses_a_dead_instruction_link(self) -> None:
        box = self._box()
        (box / "vault" / "playbooks").mkdir(parents=True)
        (box / "vault" / "playbooks" / "x.md").write_text("Read [this](vault/files/missing-thing.md) first.\n")
        out = self._run(box)["build-doc-currency"]
        self.assertEqual(out.verdict, "refused")
        self.assertIn("missing-thing.md", out.detail)
        (box / "vault" / "files").mkdir(parents=True)
        (box / "vault" / "files" / "missing-thing.md").write_text("here\n")
        self.assertEqual(self._run(box)["build-doc-currency"].verdict, "pass")


class CompanionsRefuseWithoutGenesis(unittest.TestCase):
    """AC5 (tool half): the interim identity mint is gone; a Studio with no manifest
    is refused with the cure named, never minted for as a side effect."""

    def test_refuses_and_names_the_cure(self) -> None:
        companions = _load("v195_companions", COMPANIONS_PATH)
        root = Path(tempfile.mkdtemp(prefix="v195-ac5-")).resolve()
        self.addCleanup(shutil.rmtree, root, True)
        (root / ".tropo").mkdir(); (root / "vault" / "tools").mkdir(parents=True)
        shutil.copytree(STUDIO_ROOT / "vault" / "templates" / "companions", root / "vault" / "templates" / "companions")
        (root / "vault" / "tools" / "lib").mkdir()
        shutil.copy(TOOLS / "tropo-mint-id.py", root / "vault" / "tools" / "tropo-mint-id.py")
        shutil.copy(TOOLS / "lib" / "governed_path.py", root / "vault" / "tools" / "lib" / "governed_path.py")
        with self.assertRaises(companions.CompanionGenesisError) as cm:
            companions.genesis(root)
        self.assertIn("has not run genesis", str(cm.exception))
        self.assertIn("tropo-rebuild-index.py --apply", str(cm.exception))
        self.assertFalse((root / ".tropo" / "studio-identity.md").exists())
        src = COMPANIONS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("companion-genesis-interim", src)


class CompanionOfferEventsAreRegistered(unittest.TestCase):
    """AC5, Mike-ruled 2026-09-05 ("Q1 of 1, go with option 1."): the two
    concierge events are registered on BOTH REGISTERED_TYPES surfaces and named
    in the events capsule, so Po's offer and its decline can be emitted in
    strict mode. Mutation: drop either row and the emitter refuses again."""

    TYPES = ("tropo.concierge.companion_offer_made", "tropo.concierge.companion_offer_declined")

    def test_both_surfaces_and_the_capsule_carry_both_types(self) -> None:
        emit = _load("v195_emit", TOOLS / "tropo-emit-event.py")
        sys.path.insert(0, str(STUDIO_ROOT / ".tropo" / "scripts"))
        from lib import event_validators
        capsule = (STUDIO_ROOT / "vault" / "capsules" / "tropo-events.capsule.md").read_text(encoding="utf-8")
        for t in self.TYPES:
            with self.subTest(type=t):
                self.assertIn(t, emit.REGISTERED_TYPES)
                self.assertIn(t, event_validators.REGISTERED_TYPES)
                self.assertIn("type: %s" % t, capsule)
        self.assertIn("v1_14_amendment_note", capsule)
        self.assertIn("Q1 of 1, go with option 1.", capsule)


class CompanionOfferIsInPosScript(unittest.TestCase):
    """AC5 (prose half): §1.5c introduces Cal and Darin by name and purpose, asks
    one question, and writes the offer and the decline as the registered events."""

    def test_section_1_5c_carries_names_events_and_one_question(self) -> None:
        text = ACTIVATE.read_text(encoding="utf-8")
        i = text.index("### 1.5c Offer a first agent"); j = text.index("### 1.5b")
        sec = text[i:j]
        for needle in ("**Cal — Architect and Builder.**", "**Darin — Strategist and COO.**",
                       "tropo.concierge.companion_offer_made", "tropo.concierge.companion_offer_declined",
                       "tropo-genesis-companions.py --studio .", "--as po"):
            self.assertIn(needle, sec, needle)
        quoted = [l for l in sec.splitlines() if l.startswith("> ")]
        self.assertEqual(len(quoted), 1)                       # exactly one question line
        self.assertEqual(sum(l.count("?") for l in quoted), 1)  # and one question mark in it: one input decides


# ---------------------------------------------------------------------------
# THE SPEC-NAMED IDS (f015de6b3a18 acceptance_criteria[].verify.command). The
# locked spec names unittest ids; a non-author runs them VERBATIM, so the ids
# must exist. Each below delegates to the real assertion above (a delegating
# call, never a copy) or is the one test the named id promised that had no
# home yet. argus-a171, 2026-09-05, at Metis G121's measurement.
# ---------------------------------------------------------------------------

def _genesis_rebuild(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REBUILD_INDEX_PATH), "--apply", "--skip-rehydrate", "--vault-path", str(root)],
        capture_output=True, text=True, timeout=300, cwd=str(root), stdin=subprocess.DEVNULL,
    )


class FirstBoot(unittest.TestCase):
    """AC2 as declared."""

    def test_po_step0b_runs_rebuild_in_greeting(self) -> None:
        PoRunsGenesisAndNamesTheStudio("test_activate_no_longer_tells_the_user_to_run_and_restart").debug()

    def test_genesis_mints_identity_and_pair_once(self) -> None:
        """The rebuild WITHOUT --no-genesis mints the manifest and the pair; a
        second run mints nothing more (idempotent)."""
        root = Path(tempfile.mkdtemp(prefix="v195-firstboot-")).resolve()
        self.addCleanup(shutil.rmtree, root, True)
        _minimal_studio(root)
        first = _genesis_rebuild(root)
        self.assertIn(first.returncode, _INDEX_WROTE, first.stderr[-800:])
        manifest = root / ".tropo" / "studio-identity.md"
        self.assertTrue(manifest.is_file(), "genesis must mint the manifest")
        self.assertTrue(_has_vault_entity(root), "genesis must mint the starter pair")
        before = manifest.read_text(encoding="utf-8")
        pairs_before = sum(1 for r in _index_records(root)
                           if r.get("type") == "entity" and r.get("subtype") == "vault-entity")
        second = _genesis_rebuild(root)
        self.assertIn(second.returncode, _INDEX_WROTE, second.stderr[-800:])
        self.assertEqual(manifest.read_text(encoding="utf-8"), before, "second run must not re-mint identity")
        pairs_after = sum(1 for r in _index_records(root)
                          if r.get("type") == "entity" and r.get("subtype") == "vault-entity")
        self.assertEqual(pairs_after, pairs_before, "second run must not mint a second pair")

    def test_status_script_warns_on_missing_identity(self) -> None:
        IdentityCheck.setUpClass()
        IdentityCheck("test_warns_and_names_the_cure_when_the_manifest_is_absent").debug()

    def test_status_script_quiet_when_present(self) -> None:
        IdentityCheck.setUpClass()
        IdentityCheck("test_silent_when_this_studio_has_its_identity").debug()

    def test_both_boot_paths_carry_the_identity_step(self) -> None:
        BothBootPathsRunTheCheck("test_concierge_step_0d_runs_it_and_routes_to_the_rebuild").debug()
        BothBootPathsRunTheCheck("test_playbook_step_0_0d_halts_and_routes_to_po").debug()
        BothBootPathsRunTheCheck("test_fast_path_carries_the_step_and_is_fresh").debug()

    def test_root_templates_replaced_not_blanked(self) -> None:
        PoRunsGenesisAndNamesTheStudio("test_templates_carry_no_manual_rebuild_step").debug()
        for path in (START_TROPO, README):
            self.assertGreater(len(path.read_text(encoding="utf-8")), 500, "%s must not be blanked" % path.name)


class Naming(unittest.TestCase):
    """AC3 as declared."""

    def test_section_1_5_text_carries_set_entity_name_step(self) -> None:
        PoRunsGenesisAndNamesTheStudio("test_section_1_5_sets_the_entity_name_after_vault_name").debug()

    def test_driven_1_5_two_studios_same_folder_differ_in_id_and_name(self) -> None:
        """Two studios set up from identical trees in identically named folders
        end with different studio_ids (AC2's genesis) AND different
        entity_names (§1.5's set_entity_name)."""
        mint = _load("v195_mint_naming", TOOLS / "tropo-mint-id.py")
        roots = []
        for i in range(2):
            parent = Path(tempfile.mkdtemp(prefix="v195-naming-%d-" % i)).resolve()
            self.addCleanup(shutil.rmtree, parent, True)
            root = parent / "my-studio"          # identical folder name
            root.mkdir()
            _minimal_studio(root)
            proc = _genesis_rebuild(root)
            self.assertIn(proc.returncode, _INDEX_WROTE, proc.stderr[-800:])
            roots.append(root)
        ids = [mint.read_studio_identity(root=r)["studio_id"] for r in roots]
        self.assertNotEqual(ids[0], ids[1], "identical folders must not share a studio_id")
        mint.set_entity_name("Northwind Audit", root=roots[0])
        mint.set_entity_name("Harbor Lights", root=roots[1])
        names = [mint.read_studio_identity(root=r)["entity_name"] for r in roots]
        self.assertEqual(names, ["Northwind Audit", "Harbor Lights"])
        with self.assertRaises(ValueError):
            mint.set_entity_name("deadbeefcafe", root=roots[0])   # hex-shaped names refused

    def test_trigger_fires_on_placeholders_and_not_without(self) -> None:
        text = ACTIVATE.read_text(encoding="utf-8")
        self.assertIn("If placeholders are all filled, skip this entirely", text)
        self.assertIn("Only if Boot Protocol step 7 detected `<FILL: ...>` placeholders", text)


class Doctrine(unittest.TestCase):
    """AC6 as declared."""

    def test_position_one_inline_in_both_boot_paths(self) -> None:
        Position1ReachesBothBootPaths("test_playbook_step_2_5_states_it").debug()
        Position1ReachesBothBootPaths("test_concierge_governance_states_it").debug()

    def test_shipped_box_carries_both_surfaces_capsule_412_names(self) -> None:
        Position1ReachesBothBootPaths("test_claude_template_ships_memory_writes").debug()
        ReachabilityRows.setUpClass()
        ReachabilityRows("test_memory_surfaces_and_changelog_pass_when_shipped").debug()

    def test_shipped_baseline_carries_op14(self) -> None:
        PrinciplesShipWhole("test_baseline_carries_the_founding_principle_and_all_fifteen").debug()


class Reachability(ReachabilityRows):
    """AC7 as declared: the same five-row tests under the spec's class name."""


# ---------------------------------------------------------------------------
# AC9 — THE COMPOSED ARRIVAL WALK harness (f015de6b3a18 AC9; declared command:
#   python3 vault/tools/tests/test_v195_spine_a.py --arrival-walk --box <zip>
#       --scratch <dir> --walker <name>)
# One throwaway extraction, scripted with timestamps, judged against the 5-minute
# bound. The walker is designated by Metis and is never an author; an author's
# own run is recorded AS an author run. Steps a harness cannot perform (a real
# Po turn, Cal's startup signal) are recorded as the mechanical half Po runs
# plus a WAITING/NOT-REACHED row — the walk records the gap, it never fakes it.
# argus-a171, 2026-09-05.
# ---------------------------------------------------------------------------

ARRIVAL_BOUND_SECONDS = 300   # calibrated ONLY against Po's 58 s pre-conversation floor on v1.94 (f0152b12b2df §Timeline); stated so it can be wrong


def _ts():
    import datetime as _dt, time as _t
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", _t.monotonic()


def arrival_walk(box: Path, scratch: Path, walker: str, *, studio_name: str, founder_name: str,
                 author_run: bool, bound: int = ARRIVAL_BOUND_SECONDS) -> int:
    import zipfile
    rows = []          # (step, iso, seconds_from_extraction_start, note)
    findings = []
    t_iso0, t0 = _ts()

    def mark(step, note=""):
        iso, t = _ts()
        rows.append((step, iso, round(t - t0, 1), note))
        print("  %-22s %s  +%6.1fs  %s" % (step, iso, t - t0, note))

    scratch.mkdir(parents=True, exist_ok=True)
    print("ARRIVAL WALK — box %s → %s (walker: %s%s)" % (box.name, scratch, walker,
                                                          ", AUTHOR RUN, not the walk" if author_run else ""))
    # 1. extraction
    with zipfile.ZipFile(box) as zf:
        names = zf.namelist()
        roots = {n.split("/", 1)[0] for n in names if "/" in n}
        zf.extractall(scratch)
    root = scratch / roots.pop() if len(roots) == 1 else scratch
    mark("extracted", "%d entries → %s" % (len(names), root.name))
    # AC1: no manifest, no pair in the zip
    manifest_in_zip = any(n.endswith(".tropo/studio-identity.md") for n in names)
    if manifest_in_zip:
        findings.append("AC1: the zip ships .tropo/studio-identity.md (a shipped Studio identity)")
    mark("ac1-no-identity", "manifest in zip: %s" % manifest_in_zip)

    def run(*cmd, timeout=600):
        return subprocess.run([sys.executable, *cmd], capture_output=True, text=True,
                              timeout=timeout, cwd=str(root), stdin=subprocess.DEVNULL)

    # 2. Po's step 0d: the identity check WARNS on a fresh box
    status = root / "vault" / "tools" / "tropo-studio-status.py"
    if status.is_file():
        r = run(str(status), "--as", "po", "--no-emit")
        warned = "[WARN] studio identity" in (r.stdout + r.stderr)
        mark("identity-warn", "WARN present: %s; exit %d" % (warned, r.returncode) + ("" if warned else "  (this box's status tool predates the AC2 step)"))
        # The exit code is the half this harness never read: Vela's AC5 cold walk of
        # the sealed candidate #2 (2026-09-06) found the tool FATAL-crashing (exit 1)
        # on every fresh box while this harness, checking only the WARN text, passed.
        if r.returncode != 0:
            findings.append("AC2b: Step 0d does not complete on a fresh box -- tropo-studio-status.py exited %d: %s"
                            % (r.returncode, (r.stdout + r.stderr).strip()[-240:]))
        if not warned:
            findings.append("AC2b: the shipped status tool printed no studio-identity WARN (box predates Step 0d, or the section is missing)")
    else:
        mark("identity-warn", "no tropo-studio-status.py in the box")
        findings.append("AC2b: tropo-studio-status.py absent from the box")

    # 3. Po's step 0b: genesis — the rebuild she runs herself
    rebuild = root / "vault" / "tools" / "tropo-rebuild-index.py"
    r = run(str(rebuild), "--apply", "--vault-path", ".")
    manifest = root / ".tropo" / "studio-identity.md"
    pair = _has_vault_entity(root)
    mark("genesis", "rebuild exit %d; manifest: %s; vault-entity: %s" % (r.returncode, manifest.is_file(), pair))
    if not manifest.is_file() or not pair:
        findings.append("AC2a: genesis did not mint both halves (manifest %s, pair %s)" % (manifest.is_file(), pair))
    # 3b. Po's step 0b, second command (AC5 D2, candidate #3): her own party
    #     identity, so `--as po` resolves when the offer is written.
    companions = root / "vault" / "tools" / "tropo-genesis-companions.py"
    if companions.is_file():
        r = run(str(companions), "--studio", ".", "--po")
        mark("po-identity", "genesis-companions --po exit %d" % r.returncode)
        if r.returncode != 0:
            findings.append("AC5 D2: --po refused: %s" % (r.stderr or r.stdout)[-300:])

    # 4. Po's first turn — a real LLM turn is not a harness step; the mechanical
    #    half she runs before speaking is: the identity check now silent, the map
    #    verified fresh.
    if status.is_file():
        r = run(str(status), "--as", "po", "--no-emit")
        silent = "[WARN] studio identity" not in (r.stdout + r.stderr)
        mark("po-first-turn", "identity check silent after genesis: %s; exit %d (the conversational turn itself is not a harness step)" % (silent, r.returncode))
        if r.returncode != 0:
            findings.append("AC2b: after genesis tropo-studio-status.py still does not complete (exit %d): %s"
                            % (r.returncode, (r.stdout + r.stderr).strip()[-240:]))
    else:
        mark("po-first-turn", "NOT REACHED in harness (no status tool)")

    # 5. §1.5: the studio named — set_entity_name
    mint_path = root / "vault" / "tools" / "tropo-mint-id.py"
    r = run(str(mint_path), "--set-entity-name", studio_name)
    named = manifest.is_file() and ("entity_name: %s" % studio_name in manifest.read_text(errors="replace")
                                    or ("entity_name: '%s'" % studio_name) in manifest.read_text(errors="replace")
                                    or ('entity_name: "%s"' % studio_name) in manifest.read_text(errors="replace"))
    mark("name-set", "%r → manifest carries it: %s (exit %d)" % (studio_name, named, r.returncode))
    if not named:
        findings.append("AC3: set_entity_name did not land %r on the manifest (exit %d): %s" % (studio_name, r.returncode, (r.stderr or r.stdout)[-300:]))

    # 6. §1.5: the founder minted — AC4's door.
    # AC4 landed as `tropo-mint-id.py --founder <name>` (talos-t62, d8d54af8c), not a
    # separate script; the harness calls the door the concierge text names.
    founder_tool = root / "vault" / "tools" / "tropo-mint-id.py"
    if founder_tool.is_file():
        r = run(str(founder_tool), "--founder", founder_name)
        mark("founder-minted", "exit %d: %s" % (r.returncode, (r.stdout or r.stderr).strip()[-160:]))
    else:
        mark("founder-minted", "tropo-mint-id.py absent from the box — not faked")
        findings.append("AC4: founder principal not minted — tropo-mint-id.py is not in the box")

    # 7. the companion offer → Cal's signal: genesis-companions materialises Cal;
    #    his STARTUP SIGNAL is an LLM turn and is recorded NOT REACHED by the harness.
    companions = root / "vault" / "tools" / "tropo-genesis-companions.py"
    if companions.is_file():
        r = run(str(companions), "--studio", ".", "--accept", "cal")
        cal = (root / "agents" / "cal").is_dir()
        mark("cal-signal", "companion genesis exit %d; agents/cal present: %s; Cal's startup signal NOT REACHED by harness (LLM turn)" % (r.returncode, cal))
        if r.returncode != 0:
            findings.append("AC5: companion genesis refused: %s" % (r.stderr or r.stdout)[-300:])
    else:
        mark("cal-signal", "NOT REACHED — no tropo-genesis-companions.py in the box")

    elapsed = rows[-1][2]
    verdict = "PASS" if elapsed <= bound else "FAIL"
    record = scratch / "arrival-walk-record.md"
    lines = ["# Arrival walk record — %s" % box.name, "",
             "*%s at %s. Walker: %s.%s Box: `%s`. Bound: %ds wall from extraction to Cal's signal.*" % (
                 "AUTHOR RUN (harness build; not the walk)" if author_run else "Walk",
                 t_iso0, walker, " The author drove it; Metis designates the walker for the record that counts." if author_run else "", box, bound),
             "", "| step | at (UTC) | +s | note |", "|---|---|---|---|"]
    lines += ["| %s | %s | %.1f | %s |" % r for r in rows]
    lines += ["", "**Elapsed (extraction → last reached step): %.1fs — %s the %ds bound.**" % (elapsed, "within" if verdict == "PASS" else "OVER", bound), ""]
    lines += ["## Steps not performable by a harness", "",
              "- Po's conversational first turn and Cal's startup signal are LLM turns; the harness runs the mechanical half of each and records the rest NOT REACHED.",
              "- The founder principal (AC4) is minted through `tropo-mint-id.py --founder`; a box without that door records the gap, never fakes it.", ""]
    lines += ["## Findings", ""] + (["- %s" % f for f in findings] or ["- none"]) + [""]
    lines += ["*Elapsed judged against the bound; the bound is calibrated only against Po's 58 s pre-conversation floor on v1.94 (f0152b12b2df) and is stated so it can be wrong.*"]
    record.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("record: %s" % record)
    print("VERDICT: %s (%.1fs of %ds)%s" % (verdict, elapsed, bound, "; %d finding(s)" % len(findings) if findings else ""))
    return 0 if verdict == "PASS" else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="v1.95 Spine A tests; --arrival-walk runs the AC9 composed arrival walk")
    ap.add_argument("--arrival-walk", action="store_true")
    ap.add_argument("--box", help="the release .zip")
    ap.add_argument("--scratch", help="throwaway extraction dir")
    ap.add_argument("--walker", default="unnamed", help="the walker's name (designated by Metis; never an author)")
    ap.add_argument("--studio-name", default="Walker Studio", help="the walker's answer to 'what should I call this Studio?'")
    ap.add_argument("--founder-name", default="Walker", help="the walker's answer to 'what should I call you?'")
    ap.add_argument("--author-run", action="store_true", help="record this as the author's own run, not the walk")
    ap.add_argument("--bound", type=int, default=ARRIVAL_BOUND_SECONDS)
    args, rest = ap.parse_known_args(argv)
    if args.arrival_walk:
        if not args.box or not args.scratch:
            ap.error("--arrival-walk needs --box <zip> and --scratch <dir>")
        return arrival_walk(Path(args.box).expanduser().resolve(), Path(args.scratch).expanduser().resolve(),
                            args.walker, studio_name=args.studio_name, founder_name=args.founder_name,
                            author_run=args.author_run, bound=args.bound)
    unittest.main(argv=[sys.argv[0], *rest])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


class Founder(unittest.TestCase):
    """AC4 (f015de6b3a18): the founder gets a principal through the governed door.

    Unblocked 2026-09-05 when Mike ruled the principal capsule amended to
    `mint_mode: human` (8c19ed59 v1.1, argus-a171) — until then the spec itself
    said this AC's command was not runnable. The tool is
    tropo-mint-id.mint_founder_principal, called from the concierge's §1.5
    arrival beat after the Studio is named.

    Every mint here passes `studio_root` so collision checks run against the
    FIXTURE and never the host Studio: a test that mints into the live vault is
    the class that put 103 sidecars in Mike's personal folder.
    """

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "mint_id_founder", TOOLS / "tropo-mint-id.py")
        cls.mint = importlib.util.module_from_spec(spec)
        sys.modules["mint_id_founder"] = cls.mint
        spec.loader.exec_module(cls.mint)

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="spine-a-founder-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        # a fixture Studio with its OWN identity, so the uid carries this
        # fixture's prefix and not a constant every box would share
        (self.root / ".tropo").mkdir(parents=True)
        (self.root / "vault" / "files").mkdir(parents=True)
        # MINT the manifest rather than hand-writing one: the tool refuses a
        # manifest missing any required field (fail-loud, v2.1 AC5), and a
        # hand-written fixture is a fixture that does not resemble a Studio.
        #
        # Through the PYTHON API with an explicit root, not the CLI: the CLI
        # resolves its Studio from `Path(__file__).parents[2]` and has no flag
        # to target another root, so `--kind studio` with cwd set to a fixture
        # writes nothing there and reads the LIVE manifest instead. It is
        # idempotent, so nothing was harmed proving that — but a fixture that
        # believed the CLI would have been silently testing this Studio.
        self.mint.mint_studio_identity(root=self.root, minted_by="spine-a-founder-fixture")
        manifest = (self.root / ".tropo" / "studio-identity.md").read_text(encoding="utf-8")
        # The manifest is YAML: a prefix that happens to be all digits (about one
        # fixture in six) is written quoted, `mint_prefix: '8433'`, and a raw regex
        # read keeps the quotes -- the flake A172 chased on 2026-09-05. Strip them;
        # the uid the tool mints never carries them.
        self.prefix = re.search(r"^mint_prefix:\s*(\S+)", manifest, re.MULTILINE).group(1).strip("'\"")
        # the tool's declared scratch root, not a directory of my choosing:
        # mint_file refuses any output_dir outside agents/<agent>/.tropo-capsule/workspace
        self.scratch = self.root / "agents" / "po" / ".tropo-capsule" / "workspace" / "founder"
        self.scratch.mkdir(parents=True)
        for rel in ("vault/capsules", "vault/capsules/templates"):
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        live = TOOLS.parents[1] / "vault" / "capsules"
        shutil.copy2(live / "tropo-principal.capsule.md",
                     self.root / "vault" / "capsules" / "tropo-principal.capsule.md")
        shutil.copy2(live / "templates" / "principal.template.md",
                     self.root / "vault" / "capsules" / "templates" / "principal.template.md")
        # The registry is DERIVED from this fixture's own capsule set — copying
        # the live one lands a registry whose hashes describe capsules the
        # fixture does not have, and the mint refuses it as stale (correctly).
        gen = subprocess.run(
            [sys.executable, str(TOOLS / "tropo-generate-mint-registry.py"),
             "--vault-path", str(self.root)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(gen.returncode, 0,
                         "fixture mint registry could not be derived: %s%s"
                         % (gen.stdout, gen.stderr))
        registry = self.root / "vault" / "capsules" / "mint-registry.json"
        self.assertTrue(registry.is_file(),
                        "generator exited 0 but wrote no registry to the fixture; "
                        "stdout=%r stderr=%r" % (gen.stdout, gen.stderr))

    def _mint(self, name="Ada Lovelace"):
        # scratch override, the MintFixture idiom: a fixture Studio carries no
        # toolchain, so the canonical freshen has no freshener to load. The
        # collision checks still run against THIS root, which is what the AC's
        # evidence line requires.
        return self.mint.mint_founder_principal(
            name, self.root, output_dir=self.scratch, freshen=False)

    def _frontmatter(self, path):
        return path.read_text(encoding="utf-8").split("---", 2)[1]

    def test_section_1_5_text_carries_founder_mint_step(self) -> None:
        """The §1.5 line that calls AC4's tool, after vault_owner and before
        1.5b -- the beat the arrival walk drives. Known-negative: strip the
        line and this goes red (argus-a172, 2026-09-05)."""
        text = ACTIVATE.read_text(encoding="utf-8")
        i = text.index("### 1.5 STUDIO.md Bootstrap")
        j = text.index("### 1.5b")
        section = text[i:j]
        self.assertIn('tropo-mint-id.py --founder "<vault_owner>"', section)
        self.assertLess(section.index('--set-entity-name "<vault_name>"'),
                        section.index('--founder "<vault_owner>"'),
                        "the founder is minted after the Studio is named")

    def test_principal_born_through_mint_file_with_title_and_slug(self):
        uid, path, minted = self._mint("Ada Lovelace")
        self.assertTrue(minted)
        fm = self._frontmatter(path)
        self.assertIn("type: principal", fm)
        self.assertIn("Ada Lovelace — Founder", fm)
        self.assertIn('slug: "ada-lovelace"', fm)
        self.assertNotIn("REQUIRED:", fm, "the slug placeholder survived the mint")

    def test_principal_uid_carries_studio_prefix(self):
        uid, _path, _minted = self._mint()
        self.assertTrue(uid.startswith(self.prefix),
                        "%r does not carry the fixture Studio's mint_prefix %r — the founder's "
                        "identity must be this Studio's, not a constant" % (uid, self.prefix))

    def test_get_principal_class_returns_human(self):
        """The AC's evidence names the FUNCTION, so call it — a regex over the
        frontmatter would pass even if the resolver could not read the record.
        `_get_principal_class` resolves from vault/files/<uid>.md, so the minted
        record is placed there first, which is where the canonical mint puts it
        in production anyway."""
        uid, path, _ = self._mint()
        canonical = self.root / "vault" / "files" / ("%s.md" % uid)
        canonical.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            "spine_a_identity", TOOLS.parents[1] / ".tropo" / "scripts" / "lib" / "_identity.py")
        identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity)
        self.assertEqual(identity._get_principal_class(uid, self.root), "human")

    def test_second_run_asks_nothing_mints_nothing(self):
        first_uid, _p, minted_first = self._mint("Ada Lovelace")
        before = sorted(q.name for q in self.scratch.glob("*.md"))
        second_uid, path, minted_second = self._mint("Someone Else Entirely")
        after = sorted(q.name for q in self.scratch.glob("*.md"))
        self.assertTrue(minted_first)
        self.assertFalse(minted_second, "a second run minted a second founder")
        self.assertEqual(first_uid, second_uid)
        self.assertIsNone(path, "the idempotent path returned a file to write")
        self.assertEqual(before, after, "the second run wrote a file")

    def test_placeholder_fixture_reaching_1_5_has_no_principal_until_asked(self):
        """The presence-first control: reaching §1.5 is not the same as answering.

        Without it the suite could pass by minting in setUp and never showing
        that the beat is what creates the principal.
        """
        self.assertIsNone(self.mint._human_principal_uid(self.root, self.scratch),
                          "a Studio that has not asked already has a founder")
        self._mint("Ada Lovelace")
        self.assertIsNotNone(self.mint._human_principal_uid(self.root, self.scratch))
