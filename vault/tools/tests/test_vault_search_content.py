#!/usr/bin/env python3
"""search_content degradation contract (tropo-vault-search).

Two different "no results" states, only one of them silent:

  * index ABSENT         -> [] and silence (supported state, documented)
  * index PRESENT but
    unopenable read-only -> [] and ONE stderr line naming path + error

The second state was silent for a day while build_sqlite_index shipped a
WAL-mode 00-index.sqlite whose -wal/-shm sidecars kept their .tmp names past
os.replace(): every cold mode=ro open failed with CANTOPEN and read as
"nothing matches". The build side now ships a self-contained artifact
(journal_mode=DELETE, proven by test_mounted_content_phase2); this file pins
the consumer half so the announcement cannot be quietly removed.
"""
from __future__ import annotations
import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


search = _load("search_content_tests", TOOLS / "tropo-vault-search.py")


class SearchContentDegradationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="search-content-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self._old_path = search.SQLITE_PATH

    def _point_at(self, path: Path) -> None:
        search.SQLITE_PATH = path

    def tearDown(self) -> None:
        search.SQLITE_PATH = self._old_path

    def test_absent_index_is_silent_empty(self) -> None:
        self._point_at(self.root / "no-such-index.sqlite")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(search.search_content("anything"), [])
        self.assertEqual(err.getvalue(), "")

    def test_present_but_unopenable_index_is_announced_empty(self) -> None:
        garbage = self.root / "00-index.sqlite"
        garbage.write_bytes(b"this is not a sqlite database at all")
        self._point_at(garbage)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(search.search_content("anything"), [])
        message = err.getvalue()
        self.assertIn("[SEARCH]", message, "the degradation must be announced")
        self.assertIn(str(garbage), message, "it must name the index path")


if __name__ == "__main__":
    unittest.main()
