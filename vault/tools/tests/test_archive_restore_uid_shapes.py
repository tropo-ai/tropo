#!/usr/bin/env python3
"""Focused regressions for archive/restore governed UID shape handling."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
ARCHIVE = TOOLS / "tropo-archive.py"
RESTORE = TOOLS / "tropo-restore.py"


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


class ToolStudio:
    """A throwaway Studio containing only the tools these tests exercise."""

    def __init__(self) -> None:
        self._test_root = ROOT / ".tmp-archive-restore-tests"
        self._test_root.mkdir(exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(
            prefix="studio-", dir=str(self._test_root)
        )
        self.root = Path(self._tmp.name).resolve()
        tools = self.root / "vault" / "tools"
        (self.root / "vault" / "files").mkdir(parents=True)
        (self.root / "vault" / "agents").mkdir()
        tools.mkdir(parents=True)
        shutil.copy2(ARCHIVE, tools / ARCHIVE.name)
        shutil.copy2(RESTORE, tools / RESTORE.name)
        (tools / "lib").mkdir()
        shutil.copy2(TOOLS / "lib" / "governed_path.py", tools / "lib")
        (tools / "tropo-rebuild-index.py").write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "from pathlib import Path\n"
            "root = Path(__file__).resolve().parents[2]\n"
            "with (root / 'rebuild-calls.txt').open('a') as out:\n"
            "    out.write(' '.join(sys.argv[1:]) + '\\n')\n",
            encoding="utf-8",
        )
        (tools / "tropo-emit-event.py").write_text(
            "#!/usr/bin/env python3\n",
            encoding="utf-8",
        )

    def close(self) -> None:
        self._tmp.cleanup()
        try:
            self._test_root.rmdir()
        except OSError:
            pass

    def entry(self, uid: str, *, slug: str | None = None, home: str = "files") -> Path:
        filename = f"{slug}-{uid}.md" if slug else f"{uid}.md"
        path = self.root / "vault" / home / filename
        path.write_text(
            "---\n"
            f"uid: {uid}\n"
            "type: note\n"
            "title: UID shape fixture\n"
            "state: active\n"
            "---\n\n"
            f"baseline body for {uid}\n",
            encoding="utf-8",
        )
        return path

    def tool(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return _run(
            self.root,
            sys.executable,
            str(self.root / "vault" / "tools" / name),
            *args,
        )


class ArchiveUidShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.studio = ToolStudio()
        self.addCleanup(self.studio.close)

    def test_legacy_and_composite_entries_and_superseders_archive(self) -> None:
        legacy = self.studio.entry("deadbeef")
        composite = self.studio.entry("1a2b3c4d5e6f", slug="readable-record")

        legacy_result = self.studio.tool(
            "tropo-archive.py",
            "deadbeef",
            "--reason",
            "legacy fixture",
            "--superseded-by",
            "1a2b3c4d5e6f",
        )
        self.assertEqual(
            legacy_result.returncode, 0, legacy_result.stderr or legacy_result.stdout
        )
        legacy_text = legacy.read_text(encoding="utf-8")
        self.assertIn("state: archived", legacy_text)
        self.assertIn("superseded_by: 1a2b3c4d5e6f", legacy_text)

        composite_result = self.studio.tool(
            "tropo-archive.py",
            "1a2b3c4d5e6f",
            "--reason",
            "composite fixture",
            "--superseded-by",
            "deadbeef",
        )
        self.assertEqual(
            composite_result.returncode,
            0,
            composite_result.stderr or composite_result.stdout,
        )
        composite_text = composite.read_text(encoding="utf-8")
        self.assertIn("state: archived", composite_text)
        self.assertIn("superseded_by: deadbeef", composite_text)

    def test_undeclared_and_non_hex_shapes_refuse_without_mutation(self) -> None:
        entry = self.studio.entry("feedface")
        before = entry.read_bytes()
        for bad in ("abcdef1234", "abcdefg1", "ABCDEF12"):
            with self.subTest(uid=bad):
                result = self.studio.tool(
                    "tropo-archive.py", bad, "--reason", "must refuse"
                )
                self.assertNotEqual(result.returncode, 0)

        for bad in ("abcdef1234", "abcdefg1", "ABCDEF12"):
            with self.subTest(superseded_by=bad):
                bad_superseder = self.studio.tool(
                    "tropo-archive.py",
                    "feedface",
                    "--reason",
                    "must refuse",
                    "--superseded-by",
                    bad,
                )
                self.assertNotEqual(bad_superseder.returncode, 0)
        self.assertEqual(entry.read_bytes(), before)

    def test_shared_predicate_control_has_mutation_teeth(self) -> None:
        """An 8-only predicate mutant must stop the composite archive."""
        path = self.studio.entry("1a2b3c4d5e6f", slug="mutation-control")
        copied_tool = self.studio.root / "vault" / "tools" / "tropo-archive.py"
        spec = importlib.util.spec_from_file_location("archive_mutation_control", copied_tool)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module._emit = lambda *args, **kwargs: None
        module._freshen_index = lambda uid: None

        argv = [
            str(copied_tool),
            "1a2b3c4d5e6f",
            "--reason",
            "mutation control",
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(
                module,
                "is_governed_uid_shape",
                side_effect=lambda uid: len(uid) == 8 and all(c in "0123456789abcdef" for c in uid),
            ),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(module.main(), 1)
        self.assertIn("state: active", path.read_text(encoding="utf-8"))


class RestoreUidShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.studio = ToolStudio()
        self.addCleanup(self.studio.close)

    def test_legacy_bare_and_composite_slugged_entries_resolve_for_restore(self) -> None:
        cases = (
            ("deadbeef", None),
            ("1a2b3c4d5e6f", "readable-record"),
            ("2b3c4d5e6f70", None),
        )
        for uid, slug in cases:
            with self.subTest(uid=uid):
                path = self.studio.entry(uid, slug=slug)
                result = self.studio.tool(
                    "tropo-restore.py",
                    uid,
                    "--to",
                    "abc1234",
                    "--reason",
                    "UID shape resolution",
                    "--dry-run",
                )
                self.assertEqual(
                    result.returncode, 0, result.stderr or result.stdout
                )
                self.assertIn(str(path.relative_to(self.studio.root)), result.stdout)

    def test_undeclared_and_non_hex_shapes_refuse(self) -> None:
        for bad in ("abcdef1234", "abcdefg1", "ABCDEF12"):
            with self.subTest(uid=bad):
                result = self.studio.tool(
                    "tropo-restore.py",
                    bad,
                    "--to",
                    "abc1234",
                    "--reason",
                    "must refuse",
                    "--dry-run",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid uid", result.stderr)

    def test_recycle_only_record_is_not_a_restore_source(self) -> None:
        uid = "1a2b3c4d5e6f"
        recycled = (
            self.studio.root
            / "recycle"
            / "agent-deletions"
            / "2026-08-31"
            / f"{uid}.md"
        )
        recycled.parent.mkdir(parents=True)
        recycled.write_text(f"---\nuid: {uid}\n---\n\nrecycled\n", encoding="utf-8")
        before = recycled.read_bytes()

        result = self.studio.tool(
            "tropo-restore.py",
            uid,
            "--to",
            "abc1234",
            "--reason",
            "recycle recovery uses the recycle doctrine",
            "--dry-run",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no governed file", result.stderr)
        self.assertEqual(recycled.read_bytes(), before)


class SharedAuthoritySourceTests(unittest.TestCase):
    def test_tools_import_shape_and_path_authority_without_local_uid_regex(self) -> None:
        for path in (ARCHIVE, RESTORE):
            with self.subTest(tool=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("is_governed_uid_shape", source)
                self.assertIn("resolve_governed_path", source)
                self.assertNotIn("UID_RE = re.compile", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
