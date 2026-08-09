"""Plants for Engine Phase-1 memory schema forward migration."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


migration = _load(
    "tropo_memory_migration_test",
    ROOT / "vault" / "tools" / "tropo-migrate-memory-schema.py",
)
validator = _load(
    "tropo_memory_validator_test",
    ROOT / "vault" / "tools" / "tropo-validate.py",
)


def _body(path: Path) -> bytes:
    raw = path.read_bytes()
    parts = raw.split(b"\n---\n", 1)
    return parts[1] if len(parts) == 2 else raw


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


class MemoryMigrationTests(unittest.TestCase):
    def test_dry_run_noops_and_apply_preserves_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent_dir = root / "agents" / "talos" / ".tropo-capsule" / "memory" / "entries"
            studio_dir = root / ".tropo-studio" / "memory" / "entries"
            legacy_dir = root / "agents" / "argus" / ".tropo-capsule" / "memory" / "entries"
            (root / "vault" / "files").mkdir(parents=True)
            agent_dir.mkdir(parents=True)
            studio_dir.mkdir(parents=True)
            legacy_dir.mkdir(parents=True)

            agent = agent_dir / "deadbeef.md"
            agent.write_text(
                "---\nuid: deadbeef\nsubtype: architectural\nscore: 0.9\ndate: 2026-07-14\n---\n\n"
                "**A durable architectural lesson.** Body bytes must survive.\n",
                encoding="utf-8",
            )
            studio = studio_dir / "aaaaaaaa.md"
            studio.write_text(
                "---\nuid: aaaaaaaa\ntype: memory\nsubtype: semantic\nscope: vault\n"
                'context: "This context is deliberately much longer than one hundred and twenty characters so the migration must compact it without losing the original value from provenance."\n'
                "created: 2026-07-03\nstate: active\n---\n\nStudio body.\n",
                encoding="utf-8",
            )
            legacy = legacy_dir / "release_step_author_vela_test_plan.md"
            legacy.write_text(
                "---\nname: release test plan\ndescription: independent release testing\n"
                "type: feedback\ncreated: 2026-05-15\n---\n\nLegacy feedback body.\n",
                encoding="utf-8",
            )

            paths = [agent, studio, legacy]
            before_files = {path: path.read_bytes() for path in paths}
            before_bodies = {path: hashlib.sha256(_body(path)).hexdigest() for path in paths}

            dry = migration.migrate(root, apply=False)
            self.assertFalse(dry["errors"])
            self.assertEqual(dry["entries_changed"], 3)
            self.assertEqual({path: path.read_bytes() for path in paths}, before_files)

            applied = migration.migrate(root, apply=True)
            self.assertFalse(applied["errors"])
            self.assertEqual(applied["entries_changed"], 3)
            self.assertEqual(
                {path: hashlib.sha256(_body(path)).hexdigest() for path in paths},
                before_bodies,
            )

            agent_fm = _frontmatter(agent)
            self.assertEqual(agent_fm["scope"], "agent")
            self.assertEqual(agent_fm["subtype"], "semantic")
            self.assertTrue(agent_fm["context"])

            studio_fm = _frontmatter(studio)
            self.assertEqual(studio_fm["scope"], "studio")
            self.assertLessEqual(len(studio_fm["context"]), 120)
            self.assertIn("migration_original_context", studio_fm)

            legacy_fm = _frontmatter(legacy)
            self.assertEqual(legacy_fm["uid"], "d6dcd993")
            self.assertEqual(legacy_fm["type"], "memory")
            self.assertEqual(legacy_fm["subtype"], "feedback")

            findings, checked, defects = validator.check_memory_typing(root)
            self.assertEqual(checked, 3)
            self.assertEqual(defects, 0, findings)


if __name__ == "__main__":
    unittest.main()
