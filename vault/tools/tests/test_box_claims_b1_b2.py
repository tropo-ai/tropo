"""v1.95 candidate #3, two false claims in what ships (Vela's harness record
f015570b8fd9, sorted by G123 under the freeze rule, 2026-09-06):

  B1 -- the box's package.json read "version": "1.33.0" in a v1.95.0 box.
        package.json ships (D2: `npm test` runs in the box), so it is a
        version-claim site and joins VERSION_STAMP_SITES. Red on 1.33.0
        before the cure: the stamp step never touched the file.
  B2 -- MANIFEST.md listed ITSELF with the size and hash of its previous
        generation (146,401 / 2f52f265... while on disk 193,373 / 227b314e...)
        because the regen after sanitize walked the box and found the earlier
        slip. The shipped README says the slip cannot list itself. The
        generator now omits its own row; tropo-image-manifest.json (Step 9d)
        still fingerprints MANIFEST.md.

Both run the REAL build-tool functions on a temp box.
"""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def _build():
    spec = importlib.util.spec_from_file_location("_b1b2_build_tool", TOOLS / "tropo-build-release.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class PackageJsonIsAVersionClaimSite(unittest.TestCase):
    def setUp(self):
        self.build = _build()
        self._tmp = tempfile.TemporaryDirectory()
        self.box = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.box / "package.json").write_text(
            '{\n  "name": "tropo-os",\n  "version": "1.33.0",\n  "private": true\n}\n', encoding="utf-8")

    def test_package_json_is_configured_as_a_site(self):
        self.assertIn("package.json", [rel for rel, _, _ in self.build.VERSION_STAMP_SITES])

    def test_the_stamp_rewrites_package_json_to_the_version_being_cut(self):
        self.build.step_8b_stamp_versions(str(self.box), "1.95.0")
        data = json.loads((self.box / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "1.95.0")
        self.assertEqual(data["name"], "tropo-os", "the stamp touched more than the version")


class TheSlipCannotListItself(unittest.TestCase):
    def setUp(self):
        self.build = _build()
        self._tmp = tempfile.TemporaryDirectory()
        self.box = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.box / "README.md").write_text("# box\n", encoding="utf-8")
        (self.box / "vault").mkdir()
        (self.box / "vault" / "a.md").write_text("a\n", encoding="utf-8")
        # a previous generation of the slip, as regen-after-sanitize finds it
        (self.box / "MANIFEST.md").write_text("# stale slip\n| MANIFEST.md | 1 | `x` |\n", encoding="utf-8")

    def test_regenerated_manifest_carries_no_self_row_and_lists_the_files(self):
        count = self.build.step_9_generate_manifest(str(self.box), "1.95.0")
        text = (self.box / "MANIFEST.md").read_text(encoding="utf-8")
        self.assertNotIn("| MANIFEST.md |", text)
        self.assertIn("| README.md |", text)
        self.assertIn("| vault/a.md |", text)
        self.assertEqual(count, 2)
        self.assertIn("**Files:** 2", text)

    def test_the_image_manifest_still_fingerprints_the_slip(self):
        self.build.step_9_generate_manifest(str(self.box), "1.95.0")
        self.build.step_9d_emit_image_manifest(str(self.box), "1.95.0")
        image = json.loads((self.box / "tropo-image-manifest.json").read_text(encoding="utf-8"))
        files = image.get("files") or image
        self.assertIn("MANIFEST.md", files)
        digest = hashlib.sha256((self.box / "MANIFEST.md").read_bytes()).hexdigest()
        row = files["MANIFEST.md"]
        self.assertIn(digest, json.dumps(row), "the image manifest's fingerprint of the slip is stale")


if __name__ == "__main__":
    unittest.main()
