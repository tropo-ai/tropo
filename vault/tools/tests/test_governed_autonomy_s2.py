"""Governed Autonomy S2 plants: governed birth + exact incremental/full rows."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rebuild = _load("s2_rebuild_index", TOOLS / "tropo-rebuild-index.py")
mint = _load("s2_mint_id", TOOLS / "tropo-mint-id.py")
check_one = _load("s2_check_one", TOOLS / "tropo-check-one.py")
from lib import index_surfaces, template_leg  # noqa: E402


class GovernedAutonomyS2Tests(unittest.TestCase):
    def test_note_companion_binding_and_one_home_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".tropo").mkdir()
            (root / "vault" / "files").mkdir(parents=True)
            capsules = root / "vault" / "capsules"
            capsules.mkdir()
            shutil.copy2(
                ROOT / "vault" / "capsules" / "tropo-note.capsule.md",
                capsules / "tropo-note.capsule.md",
            )
            (capsules / "templates").mkdir()
            shutil.copy2(
                ROOT / "vault" / "capsules" / "templates" / "note.template.md",
                capsules / "templates" / "note.template.md",
            )
            (capsules / "mint-registry.json").write_bytes(
                template_leg.build_mint_registry_bytes(root)
            )
            tools = root / "vault" / "tools"
            tools.mkdir()
            for name in (
                "tropo-rebuild-index.py",
                "tropo-generate-relations-header.py",
                "tropo-navblock-strip.py",
            ):
                shutil.copy2(TOOLS / name, tools / name)
            shutil.copytree(TOOLS / "lib", tools / "lib")
            initialized = subprocess.run(
                [
                    sys.executable,
                    str(tools / "tropo-rebuild-index.py"),
                    "--apply",
                    "--skip-rehydrate",
                    "--vault-path",
                    str(root),
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                initialized.returncode,
                0,
                initialized.stdout + initialized.stderr,
            )
            leg = template_leg.load_mint_template(root, "note")
            self.assertEqual(leg.capsule_version, "3.6")

            uid, path = mint.mint_file(
                "note",
                author="argus-a132",
                studio_root=root,
            )
            self.assertEqual(path, root / "vault" / "files" / f"{uid}.md")
            text = path.read_text(encoding="utf-8")
            self.assertIn("type: note", text)
            self.assertNotIn("status:", text)
            self.assertIn("state: active", text)
            self.assertIn("capsule_version: '3.6'", text)
            self.assertNotIn("<!-- REQUIRED:", text)
            findings = check_one.run_generic_mint_checks(uid, "note", root)
            self.assertEqual(findings, [])

    def test_new_tool_freshen_matches_full_rebuild_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".tropo").mkdir()
            (root / "vault" / "files").mkdir(parents=True)
            tools = root / "vault" / "tools"
            tools.mkdir()
            self.assertEqual(rebuild.rebuild_index(root, True), 0)

            uid = "deadbeef"
            path = tools / f"{uid}.md"
            path.write_text(
                "---\n"
                f"uid: {uid}\n"
                "name: scratch-library\n"
                "type: tool\n"
                "title: Scratch Library\n"
                "status: draft\n"
                "owner: argus-a132\n"
                'domain: "S2 exact-row plant."\n'
                "spawnable_by: []\n"
                "transport: library\n"
                "implementation_kind: library\n"
                "input:\n  type: object\n"
                "created: '2026-07-15'\n"
                "created_by: argus-a132\n"
                "schema_version: 2\n"
                "capsule_version: '1.8'\n"
                "governed_by: d5e1b4a3\n"
                "---\n\n# Scratch Library\n\n## Intent\n\nExact-row plant.\n",
                encoding="utf-8",
            )

            self.assertEqual(rebuild.freshen_one(uid, root), 0)
            current_path = root / "vault" / index_surfaces.CURRENT_INDEX_NAME
            incremental = next(
                row for row in index_surfaces.iter_jsonl(current_path)
                if row.get("uid") == uid
            )
            self.assertEqual(incremental["path"], f"vault/tools/{uid}.md")
            for field in (
                "extraction_scope", "segment", "decay", "inbound_live_edges",
            ):
                self.assertIn(field, incremental)
            with sqlite3.connect(root / "vault" / "00-index.sqlite") as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT json_extract(fm_json, '$.path') FROM entries WHERE uid=?",
                        (uid,),
                    ).fetchone()[0],
                    f"vault/tools/{uid}.md",
                )

            self.assertEqual(rebuild.rebuild_index(root, True), 0)
            full = next(
                row for row in index_surfaces.iter_jsonl(current_path)
                if row.get("uid") == uid
            )
            self.assertEqual(incremental, full)
            counter = json.loads(
                (root / ".tropo-studio" / "dirty-counter.json").read_text()
            )
            self.assertEqual(counter["writes_since_full_rebuild"], 0)

    def test_parallel_birth_archive_recycle_are_lossless(self) -> None:
        """Metis G89 P0 plant: every successful concurrent gesture survives."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".tropo").mkdir()
            (root / "vault" / "files").mkdir(parents=True)
            (root / "vault" / "capsules").mkdir()
            tools = root / "vault" / "tools"
            tools.mkdir()
            for name in (
                "tropo-mint-id.py",
                "tropo-rebuild-index.py",
                "tropo-archive.py",
                "tropo-recycle.py",
                "tropo-generate-relations-header.py",
                "tropo-navblock-strip.py",
            ):
                shutil.copy2(TOOLS / name, tools / name)
            shutil.copytree(TOOLS / "lib", tools / "lib")
            for name in ("tropo-note.capsule.md", "tropo-task.capsule.md"):
                shutil.copy2(
                    ROOT / "vault" / "capsules" / name,
                    root / "vault" / "capsules" / name,
                )
            templates = root / "vault" / "capsules" / "templates"
            templates.mkdir()
            for name in ("note.template.md", "task.template.md"):
                shutil.copy2(
                    ROOT / "vault" / "capsules" / "templates" / name,
                    templates / name,
                )
            (root / "vault" / "capsules" / "mint-registry.json").write_bytes(
                template_leg.build_mint_registry_bytes(root)
            )

            subprocess = __import__("subprocess")
            python = sys.executable
            rebuild_cmd = [
                python, str(tools / "tropo-rebuild-index.py"),
                "--apply", "--skip-rehydrate", "--vault-path", str(root),
            ]
            self.assertEqual(
                subprocess.run(rebuild_cmd, cwd=root, capture_output=True).returncode,
                0,
            )

            def counter() -> int:
                return json.loads(
                    (root / ".tropo-studio" / "dirty-counter.json").read_text()
                )["writes_since_full_rebuild"]

            def run_pair(commands: list[list[str]]) -> list:
                processes = [
                    subprocess.Popen(
                        command,
                        cwd=root,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    for command in commands
                ]
                results = []
                for process in processes:
                    stdout, stderr = process.communicate(timeout=90)
                    self.assertEqual(process.returncode, 0, stderr or stdout)
                    self.assertNotIn(
                        "index freshen failed",
                        stderr.lower(),
                        f"gesture reported process success but freshen failed: {stderr}",
                    )
                    results.append((stdout, stderr))
                return results

            note_cmd = [
                python, str(tools / "tropo-mint-id.py"),
                "--type", "note", "--author", "parallel-test",
            ]
            before = counter()
            note_results = run_pair([note_cmd, note_cmd])
            note_uids = [result[0].strip().splitlines()[0] for result in note_results]
            self.assertEqual(counter() - before, 2)

            indexed = {
                row["uid"]
                for row in index_surfaces.load_index_records(root, include_archive=True)
                if row.get("uid")
            }
            self.assertTrue(set(note_uids) <= indexed)

            task_cmd = [
                python, str(tools / "tropo-mint-id.py"),
                "--type", "task", "--author", "parallel-test",
            ]
            before = counter()
            task_results = run_pair([task_cmd, task_cmd])
            task_uids = [result[0].strip().splitlines()[0] for result in task_results]
            self.assertEqual(counter() - before, 2)
            for uid in task_uids:
                self.assertTrue((root / "vault" / "files" / f"{uid}.md").is_file())
            indexed = {
                row["uid"]
                for row in index_surfaces.load_index_records(root, include_archive=True)
                if row.get("uid")
            }
            self.assertTrue(set(task_uids) <= indexed)

            # Cross-gesture contention uses the same lock: archive one note
            # while minting another, then recycle the second while minting.
            archive_cmd = [
                python, str(tools / "tropo-archive.py"), note_uids[0],
                "--reason", "parallel archive plant", "--actor", "parallel-test",
            ]
            before = counter()
            archive_results = run_pair([archive_cmd, note_cmd])
            archive_mint_uid = archive_results[1][0].strip().splitlines()[0]
            self.assertEqual(counter() - before, 2)

            current_uids = {
                row["uid"] for row in index_surfaces.load_index_records(root)
                if row.get("uid")
            }
            archive_uids = {
                row["uid"]
                for row in index_surfaces.load_index_records(root, include_archive=True)
                if index_surfaces.is_archive_record(row)
            }
            self.assertIn(note_uids[0], archive_uids)
            self.assertIn(archive_mint_uid, current_uids)

            recycle_cmd = [
                python, str(tools / "tropo-recycle.py"), note_uids[1],
                "--reason", "parallel recycle plant",
            ]
            before = counter()
            recycle_results = run_pair([recycle_cmd, note_cmd])
            recycle_mint_uid = recycle_results[1][0].strip().splitlines()[0]
            self.assertEqual(counter() - before, 2)
            union_uids = {
                row["uid"]
                for row in index_surfaces.load_index_records(root, include_archive=True)
                if row.get("uid")
            }
            self.assertNotIn(note_uids[1], union_uids)
            self.assertIn(recycle_mint_uid, union_uids)


if __name__ == "__main__":
    unittest.main()
