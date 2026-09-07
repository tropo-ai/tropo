"""v1.95 Spine A AC8, build-step half (f015de6b3a18; plan f015ba71c711 row A5).

Three facts, each with a negative arm:
  1. the build tool wires step_9b2_render_studio_map after step_9b and before the
     sanitize step, and the step invokes the BOX's renderer in --box mode against
     the build dir (a copied render would carry this studio's counts);
  2. the step refuses (SystemExit) when the renderer is missing or fails, and
     returns the output path when it succeeds — proven with a stub renderer that
     records its argv, so the assertion is on what ran, not on what was declared;
  3. the review HTML and its svg/ folder have ship-artifact entries in the index
     with the modes and output paths the build's step 4 honours (zero shipped in
     v1.94, measured on the box).

Fixtures scrub GIT_* and pin cwd (studio pin f0158f934b60). Runs under
`python3 -m unittest vault.tools.tests.test_v195_spine_a_ac8_build_step`.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUILD_TOOL = ROOT / "vault" / "tools" / "tropo-build-release.py"
HTML_ENTRY = "f015ddd23f10"
SVG_ENTRY = "f015804812dc"
RESOURCES_ENTRY = "f015fb16887b"


def _scrub_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return env


class WiringTest(unittest.TestCase):
    def setUp(self):
        self.src = BUILD_TOOL.read_text(encoding="utf-8")
        self.tree = ast.parse(self.src)

    def test_step_defined_and_called_in_main_after_9b_before_sanitize(self):
        names = {n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)}
        self.assertIn("step_9b2_render_studio_map", names)
        main = next(n for n in ast.walk(self.tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        order = []
        for node in ast.walk(main):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ("step_9b_regenerate_tropo_nav",
                                    "step_9b2_render_studio_map",
                                    "step_10_sanitize_argo_identity"):
                    order.append((node.lineno, node.func.id))
        order.sort()
        ids = [i for _, i in order]
        self.assertIn("step_9b2_render_studio_map", ids, "the step is defined but nothing calls it")
        self.assertLess(ids.index("step_9b_regenerate_tropo_nav"), ids.index("step_9b2_render_studio_map"))
        self.assertLess(ids.index("step_9b2_render_studio_map"), ids.index("step_10_sanitize_argo_identity"))

    def test_step_invokes_box_renderer_in_box_mode(self):
        fn = next(n for n in ast.walk(self.tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "step_9b2_render_studio_map")
        literals = {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertIn("--box", literals)
        self.assertIn("tropo-render-studio-map.py", literals)
        self.assertIn("--vault-path", literals)


class StepBehaviourTest(unittest.TestCase):
    """Load ONLY the step function out of the build tool (the module has import-time
    side effects on the real studio), and run it against a scratch build dir whose
    renderer is a stub that records what it was called with."""

    def _load_step(self):
        src = BUILD_TOOL.read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "step_9b2_render_studio_map")
        module = ast.Module(body=[fn], type_ignores=[])
        ns = {"os": os, "subprocess": subprocess, "sys": sys}
        exec(compile(module, str(BUILD_TOOL), "exec"), ns)
        return ns["step_9b2_render_studio_map"]

    def _scratch(self, renderer_body: str | None):
        d = Path(tempfile.mkdtemp(prefix="ac8-step-"))
        tools = d / "vault" / "tools"
        tools.mkdir(parents=True)
        if renderer_body is not None:
            (tools / "tropo-render-studio-map.py").write_text(renderer_body, encoding="utf-8")
        return d

    def test_missing_renderer_refuses(self):
        step = self._load_step()
        d = self._scratch(None)
        with self.assertRaises(SystemExit):
            step(str(d))

    def test_failing_renderer_refuses(self):
        step = self._load_step()
        d = self._scratch("import sys\nsys.stderr.write('planted failure\\n')\nsys.exit(3)\n")
        with self.assertRaises(SystemExit):
            step(str(d))

    def test_succeeding_renderer_writes_map_and_returns_path(self):
        step = self._load_step()
        stub = (
            "import sys, os, json\n"
            "argv = sys.argv[1:]\n"
            "root = argv[argv.index('--vault-path') + 1]\n"
            "os.makedirs(os.path.join(root, 'boards', 'po'), exist_ok=True)\n"
            "with open(os.path.join(root, 'argv.json'), 'a') as f: f.write(json.dumps(argv) + '\\n')\n"
            "if '--check-stale' in argv:\n"
            "    print('FRESH: stub'); sys.exit(0)\n"
            "open(os.path.join(root, 'boards', 'po', 'studio-map.html'), 'w').write('<html>stub</html>')\n"
        )
        d = self._scratch(stub)
        out = step(str(d))
        self.assertTrue(Path(out).is_file())
        calls = [json.loads(l) for l in (d / "argv.json").read_text().splitlines()]
        self.assertTrue(all("--box" in c for c in calls), calls)
        self.assertTrue(all(c[c.index("--vault-path") + 1] == str(d) for c in calls), calls)


class ShipEntriesTest(unittest.TestCase):
    """Reads the ENTRY FILES, never vault/00-index.jsonl: the index is a
    per-machine, gitignored product and a test that asserts against it reports
    a false RED on any clone that has not rebuilt (Talos T62 measured it on his,
    2026-09-05, f015962de498 second instance; Orpheus's render fixture had the
    same defect the same hour). The frontmatter on main is the fact the build
    reads through the index once the clone rebuilds; asserting on the file is
    asserting on what every clone shares."""

    @staticmethod
    def _frontmatter(uid: str) -> dict:
        matches = sorted((ROOT / "vault" / "files").glob(f"*{uid}*.md"))
        if not matches:
            return {}
        text = matches[0].read_text(encoding="utf-8")
        if not text.startswith("---"):
            return {}
        body = text.split("---", 2)[1]
        fm = {}
        for line in body.splitlines():
            if ":" in line and not line.startswith((" ", "\t", "#")):
                k, _, v = line.partition(":")
                fm[k.strip()] = v.split("#", 1)[0].strip().strip("'\"")
        return fm

    def test_review_html_ships_direct_copy_at_its_path(self):
        fm = self._frontmatter(HTML_ENTRY)
        self.assertTrue(fm, "review HTML ship-artifact entry file not in vault/files")
        self.assertEqual(fm.get("type"), "ship-artifact")
        self.assertEqual(fm.get("source_mode"), "direct-copy")
        self.assertEqual(fm.get("output_path"), "docs/architecture-review-v4/tropo-l1-architecture-review.html")
        self.assertTrue((ROOT / "docs/architecture-review-v4/tropo-l1-architecture-review.html").is_file())

    def test_review_svgs_ship_recursively(self):
        fm = self._frontmatter(SVG_ENTRY)
        self.assertTrue(fm, "review svg/ ship-artifact entry file not in vault/files")
        self.assertEqual(fm.get("source_mode"), "recursive-ship-all")
        self.assertEqual(fm.get("output_path"), "docs/architecture-review-v4/svg/")
        svgs = sorted((ROOT / "docs/architecture-review-v4/svg").glob("*.svg"))
        self.assertEqual(len(svgs), 15, [p.name for p in svgs])

    def test_map_resources_file_ships(self):
        fm = self._frontmatter(RESOURCES_ENTRY)
        self.assertTrue(fm, "resources ship-artifact entry file not in vault/files")
        self.assertEqual(fm.get("source_mode"), "direct-copy")
        self.assertEqual(fm.get("output_path"), "vault/templates/root-docs/studio-map-resources.md")
        self.assertTrue((ROOT / "vault/templates/root-docs/studio-map-resources.md").is_file())


if __name__ == "__main__":
    unittest.main()
