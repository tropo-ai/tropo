#!/usr/bin/env python3
"""Index rows get a DERIVED display title; source files are never touched.

Governed files under `agents/` and `.tropo/` carry no `title:` — an agent
activation names itself with `agent_name:`. They are indexed because they carry
a uid and a type, so 28 rows projected an empty title and the cockpit showed
blank entries for real records.

Stamping `title:` into 28 identity files would edit substrate to please a
projection. Argus A145 ruled the other way on 2026-08-08: derive the row title
at projection time, precedence title -> agent_name -> name -> filename stem,
never edit the source. These fixtures are the two halves he asked for —
nonblank projection AND byte-identical source.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load():
    spec = importlib.util.spec_from_file_location(
        "rebuild_index_title", TOOLS / "tropo-rebuild-index.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["rebuild_index_title"] = module
    spec.loader.exec_module(module)
    return module


rebuild = _load()


class DerivedRowTitleTests(unittest.TestCase):
    def test_precedence_is_title_then_agent_name_then_name_then_stem(self) -> None:
        path = Path("agents/kb-curator/kb-curator-activation.md")
        cases = [
            ("title: T\nagent_name: A\nname: N\n", "T", "title wins"),
            ("agent_name: A\nname: N\n", "A", "agent_name beats name"),
            ("name: N\n", "N", "name when the first two are absent"),
            ("type: activation\n", "kb-curator-activation", "filename stem is the floor"),
        ]
        for fm, expected, why in cases:
            with self.subTest(case=why):
                self.assertEqual(rebuild._derived_row_title(fm, path), expected, why)

    def test_blank_and_whitespace_values_fall_through(self) -> None:
        """An empty `title:` is the absence this exists to fix, not a title."""
        path = Path("agents/example/example-activation.md")
        for fm in ('title: ""\n', 'title: "   "\n', 'title: ""\nagent_name: A\n'):
            with self.subTest(fm=fm):
                got = rebuild._derived_row_title(fm, path)
                self.assertTrue(got.strip(), f"{fm} projected a blank title")

    def test_the_derived_title_is_never_empty(self) -> None:
        """The stem always exists, so the projection has no blank branch left."""
        self.assertEqual(
            rebuild._derived_row_title("type: note\n", Path("x/y/some-file.md")),
            "some-file")

    def test_no_non_memory_row_in_the_live_index_has_a_blank_title(self) -> None:
        """The measured defect, asserted against the real projection.

        28 rows before: 22 under agents/, 6 under .tropo/, zero under vault/.
        """
        import json
        index = TOOLS.parents[1] / "vault" / "00-index.jsonl"
        if not index.is_file():
            self.skipTest("no built index in this checkout")
        blank = [
            json.loads(line) for line in index.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        blank = [
            r for r in blank
            if not str(r.get("title") or "").strip() and r.get("type") != "memory"
        ]
        self.assertEqual(
            blank, [],
            f"{len(blank)} non-memory rows still project a blank title")

    def test_deriving_a_title_does_not_touch_the_source_file(self) -> None:
        """The half that matters more than the display.

        A projection that repairs itself by editing substrate is not a
        projection. Byte-identical, asserted on the hash rather than on mtime.
        """
        source = TOOLS.parents[1] / "agents" / "kb-curator" / "kb-curator-activation.md"
        if not source.is_file():
            self.skipTest("fixture source absent in this checkout")
        raw = source.read_bytes()
        before = hashlib.sha256(raw).hexdigest()

        head = raw.decode("utf-8", errors="replace")[:4096]
        derived = rebuild._derived_row_title(head, source)

        self.assertTrue(derived.strip(), "this fixture must project a real title")
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest(), before,
            "deriving a display title modified the source file")

    def test_the_source_file_still_has_no_title_field(self) -> None:
        """The control. If someone 'fixes' this by stamping titles into the
        identity files, the tests above keep passing and the ruling has been
        quietly reversed. This is what notices."""
        source = TOOLS.parents[1] / "agents" / "kb-curator" / "kb-curator-activation.md"
        if not source.is_file():
            self.skipTest("fixture source absent in this checkout")
        head = source.read_text(encoding="utf-8")[:4096]
        self.assertNotIn(
            "\ntitle:", head,
            "a title: was stamped into an identity file — the ruling was to "
            "derive the row, never edit the source")


if __name__ == "__main__":
    unittest.main(verbosity=1)
