#!/usr/bin/env python3
"""Ship-scoped Python must run on the oldest interpreter a Studio presents.

The field failure: `tropo-import-walker.py` gained `mount_uid: str | None` with
no postponed annotations, silently raising its floor to 3.10. Every machine in
this build runs 3.12, so the defect surfaced only when the tool ran on Mike's
Mac during the gate-1 manual walk — stock macOS python3 is 3.9.6 and the walk
stopped dead.

The mutation that matters is therefore the real one: remove the future import
that fixed the walker and require the gate to go red.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"

SPEC = importlib.util.spec_from_file_location(
    "tropo_validate_for_python_floor", TOOLS / "tropo-validate.py"
)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)

WALKER = Path("vault/tools/tropo-import-walker.py")

SHIP_FRONTMATTER = '''#!/usr/bin/env python3
"""
---
uid: {uid}
type: tool
status: active
extraction_scope: ship
{extra}---
"""
{future}
from pathlib import Path


def probe(value{annotation}):
    return value
'''


class ShipPythonFloorTests(unittest.TestCase):
    def scratch(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="ship-python-floor-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "vault" / "tools").mkdir(parents=True)
        return tmp

    def plant(self, root: Path, name: str, *, annotation: str, future: bool,
              extra: str = "") -> Path:
        path = root / "vault" / "tools" / name
        path.write_text(
            SHIP_FRONTMATTER.format(
                uid=name.replace("-", "")[:8].ljust(8, "0"),
                extra=extra,
                future="from __future__ import annotations\n" if future else "",
                annotation=annotation,
            ),
            encoding="utf-8",
        )
        return path

    def test_the_live_tree_is_clean(self):
        findings, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(ROOT)
        self.assertGreater(checked, 0, "no ship-scoped tools were checked")
        self.assertEqual(defects, 0, f"ship tools would fail on py3.9: {findings}")

    def test_pep604_annotation_without_postponement_is_a_defect(self):
        root = self.scratch()
        self.plant(root, "tropo-probe.py", annotation=": str | None = None", future=False)

        findings, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)

        self.assertEqual(checked, 1)
        self.assertEqual(defects, 1)
        self.assertIn("PEP-604", findings[0])
        self.assertIn("Python 3.9", findings[0])

    def test_postponed_annotations_clear_it(self):
        root = self.scratch()
        self.plant(root, "tropo-probe.py", annotation=": str | None = None", future=True)
        _, _, defects = VALIDATOR.check_ship_python_interpreter_floor(root)
        self.assertEqual(defects, 0)

    def test_an_explicitly_declared_higher_floor_clears_it(self):
        """A tool may require 3.10 — it just may not do so silently."""
        root = self.scratch()
        self.plant(
            root,
            "tropo-probe.py",
            annotation=": str | None = None",
            future=False,
            extra="python_floor: '3.11'\n",
        )
        _, _, defects = VALIDATOR.check_ship_python_interpreter_floor(root)
        self.assertEqual(defects, 0)

    def test_non_ship_tools_are_out_of_scope(self):
        root = self.scratch()
        path = self.plant(root, "tropo-probe.py", annotation=": str | None = None", future=False)
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "extraction_scope: ship", "extraction_scope: argo-private"
            ),
            encoding="utf-8",
        )
        _, checked, defects = VALIDATOR.check_ship_python_interpreter_floor(root)
        self.assertEqual((checked, defects), (0, 0))

    def test_removing_the_walker_future_import_turns_the_gate_red(self):
        """The real mutation: undo metis-g107's fix and require a defect.

        Runs against a copy. The live walker is never modified.
        """
        root = self.scratch()
        shutil.copy2(ROOT / WALKER, root / WALKER)

        _, _, before = VALIDATOR.check_ship_python_interpreter_floor(root)
        self.assertEqual(before, 0, "the copied walker did not start clean")

        target = root / WALKER
        text = target.read_text(encoding="utf-8")
        mutated = text.replace("from __future__ import annotations", "", 1)
        self.assertNotEqual(mutated, text, "the walker no longer carries the fix")
        target.write_text(mutated, encoding="utf-8")

        findings, _, after = VALIDATOR.check_ship_python_interpreter_floor(root)

        self.assertGreater(
            after,
            0,
            "removing the postponed-annotations fix did not fail the gate — the "
            "exact defect that broke the gate-1 walk would ship again",
        )
        self.assertTrue(any("tropo-import-walker.py" in f for f in findings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
