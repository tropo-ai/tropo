#!/usr/bin/env python3
"""Memory-freshness gate tests (f015fcaf29b9 item 8).

The load-bearing case is the NEGATIVE CONTROL the coordination driver
required: an agent whose retirement ceremony never ran — no retired rows in
lineage at all — must still trip the gate. The instrument counts births,
not ceremonies, precisely so a skipped ceremony hides nothing.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tropo-check-memory-freshness.py"
SLUG = "vela"


def make_studio(tmp: Path, *, born_gens, folded_at, retired_gens=()):
    root = tmp / "studio"
    (root / "vault" / "tools").mkdir(parents=True)
    (root / "agents" / SLUG / ".tropo-capsule" / "memory").mkdir(parents=True)
    rows = []
    for i, gen in enumerate(born_gens):
        rows.append(
            {"t": "born", "gen": gen, "at": f"2026-09-0{i+1}T00:00:00Z", "by": "mike"}
        )
        if gen in retired_gens:
            rows.append(
                {"t": "retired", "gen": gen, "at": f"2026-09-0{i+1}T12:00:00Z"}
            )
    (root / "agents" / SLUG / "lineage.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    frontmatter = (
        "---\nagent: vela\ngeneration: %s\nlast_curated: '2026-09-01'\n---\n"
        % folded_at
        if folded_at
        else "---\nagent: vela\nlast_curated: '2026-09-01'\n---\n"
    )
    (root / "agents" / SLUG / ".tropo-capsule" / "memory" / "agent-memory.md").write_text(
        frontmatter + "\n# memory\n", encoding="utf-8"
    )
    return root


def run_tool(root: Path, *extra):
    return subprocess.run(
        [sys.executable, str(TOOL), "--agent", SLUG, "--studio", str(root), "--json", *extra],
        capture_output=True,
        text=True,
        check=False,
    )


class FreshnessGateTests(unittest.TestCase):
    def test_claimed_genesis_counts_as_one_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_studio(Path(tmp), born_gens=["D1", "D1", "D2", "D3"], folded_at="D1")
            before = (root / "agents" / SLUG / "lineage.jsonl").read_bytes()
            proc = run_tool(root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            row = json.loads(proc.stdout)["rows"][0]
            self.assertEqual(row["generations_since_fold"], 2)
            self.assertNotEqual(row["verdict"], "STALE")
            self.assertEqual((root / "agents" / SLUG / "lineage.jsonl").read_bytes(), before)

    def test_fresh_surface_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_studio(
                Path(tmp), born_gens=["V78", "V79"], folded_at="V79"
            )
            proc = run_tool(root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            row = json.loads(proc.stdout)["rows"][0]
            self.assertEqual(row["verdict"], "ok")
            self.assertEqual(row["generations_since_fold"], 0)

    def test_three_generations_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_studio(
                Path(tmp),
                born_gens=["V75", "V76", "V77", "V78"],
                folded_at="V75",
                retired_gens=["V75", "V76", "V77"],
            )
            proc = run_tool(root)
            self.assertEqual(proc.returncode, 1)
            row = json.loads(proc.stdout)["rows"][0]
            self.assertEqual(row["verdict"], "STALE")
            self.assertEqual(row["generations_since_fold"], 3)

    def test_negative_control_skipped_ceremony_still_trips(self):
        """THE required case: no retirement ceremony ever ran — zero retired
        rows in lineage — and the gate still fires. Folding was gated on
        clean retirements; this is the exact blind spot (V76 never formally
        retired; V77 retired with no fold; O36/O37 the same shape).
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = make_studio(
                Path(tmp),
                born_gens=["V75", "V76", "V77", "V78"],
                folded_at="V75",
                retired_gens=(),  # NO ceremony rows at all
            )
            proc = run_tool(root)
            self.assertEqual(proc.returncode, 1)
            row = json.loads(proc.stdout)["rows"][0]
            self.assertEqual(row["verdict"], "STALE")
            self.assertEqual(row["generations_since_fold"], 3)

    def test_never_folded_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_studio(Path(tmp), born_gens=["V78"], folded_at=None)
            proc = run_tool(root)
            self.assertEqual(proc.returncode, 1)
            row = json.loads(proc.stdout)["rows"][0]
            self.assertEqual(row["verdict"], "never-folded")

    def test_byte_tight_axis_flags_independently_of_generations(self):
        """O38's second axis: bytes-remaining under the capsule error ceiling
        flags a surface that cannot accept its next pin even when the
        generations axis is quiet (talos live: 2 gens, 1995 bytes)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_studio(Path(tmp), born_gens=["V78", "V79"], folded_at="V79")
            mem = root / "agents" / SLUG / ".tropo-capsule" / "memory" / "agent-memory.md"
            body = "\n".join("# padding line %d some extra width to cross the byte threshold" % i for i in range(680))
            mem.write_text(mem.read_text() + "\n" + body + "\n", encoding="utf-8")
            proc = run_tool(root)
            self.assertEqual(proc.returncode, 1)
            row = json.loads(proc.stdout)["rows"][0]
            self.assertEqual(row["verdict"], "BYTE-TIGHT")
            self.assertLess(row["bytes_remaining"], 2048)
            self.assertEqual(row["generations_since_fold"], 0)

    def test_fold_generation_missing_from_lineage_is_unresolvable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_studio(
                Path(tmp), born_gens=["V78", "V79"], folded_at="V60"
            )
            proc = run_tool(root)
            self.assertEqual(proc.returncode, 0)  # unresolvable warns, not gates
            row = json.loads(proc.stdout)["rows"][0]
            self.assertEqual(row["verdict"], "unresolvable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
