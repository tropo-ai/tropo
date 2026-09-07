"""v1.95 AC7 content cure, ruling 1 (Metis G121, 2026-09-05 23:51Z; landed argus-a172):
SUPERSEDED PLAYBOOKS DO NOT SHIP. The release build's wholesale playbook channel
(step_3d_copy_vault_playbooks) excludes a playbook by its OWN `status: superseded`
declaration -- never by a skip list. Remove the exclusion and the first test goes red."""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def _load_builder(vault_dir: Path):
    spec = importlib.util.spec_from_file_location("br_superseded_%d" % id(vault_dir), TOOLS / "tropo-build-release.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    mod.tropo_roots.VAULT_DIR = str(vault_dir)
    mod.DRY_RUN = False
    return mod


class SupersededPlaybooksDoNotShip(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="superseded-pb-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.vault = self.tmp / "vault"
        pb = self.vault / "playbooks"
        pb.mkdir(parents=True)
        (pb / "live.md").write_text("---\nuid: aaaa1111\ntype: playbook\nstatus: active\n---\n# live\n", encoding="utf-8")
        (pb / "old.md").write_text("---\nuid: bbbb2222\ntype: playbook\nstatus: superseded\nsuperseded_by: aaaa1111\n---\n# old\n", encoding="utf-8")
        (pb / "quoted.md").write_text("---\nuid: cccc3333\nstatus: 'superseded'\n---\n# quoted\n", encoding="utf-8")
        (pb / "bare.md").write_text("# no frontmatter at all\n", encoding="utf-8")
        self.box = self.tmp / "box"
        self.box.mkdir()
        self.builder = _load_builder(self.vault)

    def test_superseded_by_declaration_is_excluded_and_the_rest_ships(self):
        copied = self.builder.step_3d_copy_vault_playbooks(str(self.box))
        shipped = sorted(p.name for p in (self.box / "vault" / "playbooks").iterdir())
        self.assertEqual(shipped, ["bare.md", "live.md"], shipped)
        self.assertEqual(copied, 2)

    def test_status_is_read_from_the_file_not_a_list(self):
        s = self.builder._playbook_status
        self.assertEqual(s(str(self.vault / "playbooks" / "old.md")), "superseded")
        self.assertEqual(s(str(self.vault / "playbooks" / "quoted.md")), "superseded")
        self.assertEqual(s(str(self.vault / "playbooks" / "live.md")), "active")
        self.assertEqual(s(str(self.vault / "playbooks" / "bare.md")), "")

    def test_the_three_real_superseded_playbooks_are_declared_not_listed(self):
        """The cure is the declaration in the real files: each of the three carries
        status: superseded in its own frontmatter, and the builder holds no list."""
        real = TOOLS.parent / "playbooks"
        for uid in ("7f2efd7c", "f4a81b29", "71f186cf"):
            self.assertEqual(self.builder._playbook_status(str(real / f"{uid}.md")), "superseded", uid)
        src = (TOOLS / "tropo-build-release.py").read_text(encoding="utf-8")
        self.assertNotIn("SUPERSEDED_PLAYBOOKS", src, "a skip list crept in; the ruling is exclusion by declaration")


if __name__ == "__main__":
    unittest.main()
