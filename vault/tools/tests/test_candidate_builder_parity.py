"""v1.95 candidate-builder parity (Mike, 2026-09-06, "cure and cut candidate #3"):
the rehearsal instrument must never carry a path the release build excludes or
omits. Vela's AC5 cold walk of the SEALED candidate #2 found `vault/studio-ops`
absent from the box while every author rehearsal had run on boxes and fixtures
that carried it; candidate #1's doc-currency instrument read 0 on a box that
carried the two per-studio boot derivations the release build removes.

This test builds a real candidate box from HEAD with tropo-build-candidate-box.py
(the same emitters as the release build) and asserts, path by path, that nothing
in it is denied by the release build's own exclusion rules -- read from the build
tool at HEAD, one definition -- and that the studio-only substrate the release
box never carries is absent. The negative control runs the same predicate over a
raw archive of HEAD, which MUST contain excluded paths: a predicate that finds
nothing there proves nothing here.

Slow (builds a box, ~1-2 minutes). Run it when the builder or the build's
exclusion rules change.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
STUDIO = TOOLS.parents[1]

# Studio-only substrate: created per studio at genesis or by daily operations,
# never shipped. vault/studio-ops first (Mike's word); the two boot derivations
# (the release build's Step 3f); the per-machine index surfaces.
STUDIO_ONLY = (
    "vault/studio-ops",
    ".tropo/boot-fast-path.md",
    ".tropo/boot-digest.md",
    ".tropo/boot-fast-path.history.md",
    ".tropo/boot-digest.history.md",
)


def _load_build_tool():
    spec = importlib.util.spec_from_file_location("_parity_build_tool", TOOLS / "tropo-build-release.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _walk(root: Path):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in (".git", "__pycache__")]
        for n in fns:
            yield Path(dp, n)


class CandidateBoxCarriesNothingTheBuildExcludes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="candidate-parity-"))
        out = cls.tmp / "cand"
        proc = subprocess.run(
            [sys.executable, str(TOOLS / "tropo-build-candidate-box.py"), "--out", str(out), "--commit", "HEAD"],
            cwd=str(STUDIO), capture_output=True, text=True)
        if proc.returncode != 0:
            raise AssertionError("candidate builder failed (rc %s):\n%s" % (proc.returncode, (proc.stderr or proc.stdout)[-1500:]))
        cls.box = out / "box"
        assert cls.box.is_dir(), "candidate builder wrote no box/ under %s" % out
        cls.build = _load_build_tool()
        # the raw source tree at HEAD: the negative control
        cls.raw = cls.tmp / "raw"
        cls.raw.mkdir()
        archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=str(STUDIO), capture_output=True)
        assert archive.returncode == 0, archive.stderr.decode()[:400]
        tar_path = cls.tmp / "head.tar"
        tar_path.write_bytes(archive.stdout)
        with tarfile.open(tar_path) as tf:
            tf.extractall(cls.raw)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _excluded(self, root: Path):
        """Every path under root the release build's own rules deny."""
        hits = []
        for p in _walk(root):
            rel = p.relative_to(root).as_posix()
            # The kernel rule governs the kernel channel (.tropo/) and the
            # manifest channel's per-file copies; the wholesale vault/tools/
            # channel ships every tool by the A92 ruling (fdef56ea), which is
            # why the sealed v1.95 box carries tropo-build-release.py and
            # tropo-register-kernel.py although KERNEL_EXCLUDE_PATTERNS still
            # names both (dead letters from v1.5, a 1.96 cleanup, not parity).
            if rel.startswith(".tropo/") and self.build.should_exclude_kernel(str(p)):
                hits.append(rel)
                continue
            if rel in self.build.PER_STUDIO_BOOT_DERIVATIONS:
                hits.append(rel)
                continue
            for studio_only in STUDIO_ONLY:
                if rel == studio_only or rel.startswith(studio_only + "/"):
                    hits.append(rel)
                    break
        return sorted(set(hits))

    def test_the_predicate_is_live_on_the_raw_tree(self):
        """Negative control: HEAD's raw tree carries studio-only substrate and
        kernel-excluded files. If this finds nothing, the parity assertion below
        proves nothing."""
        hits = self._excluded(self.raw)
        self.assertTrue(any(h.startswith("vault/studio-ops") for h in hits), hits[:20])
        self.assertTrue(any(h in (".tropo/boot-fast-path.md", ".tropo/boot-digest.md") for h in hits), hits[:20])

    def test_the_candidate_box_carries_no_excluded_path(self):
        hits = self._excluded(self.box)
        self.assertEqual(hits, [], "the candidate builder ships paths the release build excludes:\n  " + "\n  ".join(hits[:40]))

    def test_studio_ops_is_absent_from_the_candidate_box(self):
        """vault/studio-ops first (Mike). The status tool's Step 0d must be
        rehearsed on a box that lacks it, as every shipped box does."""
        self.assertFalse((self.box / "vault" / "studio-ops").exists())

    # ── The inclusion direction (task f0158df832b1, talos-t65 2026-09-08) ─────
    # Everything above asserts the candidate carries nothing the release build
    # EXCLUDES. Nothing asserted that it carries what the release build
    # INCLUDES, and that half was false for every candidate box ever built: the
    # seven tree-resident files below were placed by code inline in the release
    # build's main(), unreachable from the candidate builder, so they were simply
    # absent. A one-directional parity test is how that survived -- the gate was
    # green and blind on the side that was broken.

    def _tree_resident_destinations(self):
        """Box-relative paths the release build's tree-resident steps place.

        Derived from the build tool's OWN declaration, not restated here: a
        second hand-written list is the defect this task exists to close.
        """
        dests = ["CHANGELOG.md", ".tropo-studio/mission-brief.md"]
        for entry in self.build.D2_FOLDER_MIRROR_FILES:
            rel_path, dest_dir = entry[0], entry[1]
            dest_name = entry[2] if len(entry) > 2 else os.path.basename(rel_path)
            dests.append(os.path.join(dest_dir, dest_name) if dest_dir else dest_name)
        return sorted(set(dests))

    def test_the_expected_set_is_drawn_from_the_build_tool_and_is_not_empty(self):
        """Control on the list itself: if D2_FOLDER_MIRROR_FILES is emptied or
        renamed, the assertion below must not pass vacuously. Seven files, and
        each one names a real reader: the four AGENTS.md are the validator's
        AGENTS_MD_REQUIRED_DIRS check, package.json is `npm test` inside the box,
        CHANGELOG.md is build-changelog-names-version, and the mission-brief slot
        is a Required:Yes boot read (99341618 Step 2.3 + cf8c3be9 Tier 2)."""
        dests = self._tree_resident_destinations()
        self.assertEqual(len(dests), 7, dests)
        self.assertIn("package.json", dests)
        self.assertIn(".tropo-studio/mission-brief.md", dests)

    def test_the_candidate_box_carries_every_tree_resident_file_the_build_places(self):
        """Mutation-proven 2026-09-08: dropping either the step_5d call or the
        step_7_1 call from tropo-build-candidate-box.py turns this red, naming
        the exact files that went missing."""
        missing = [d for d in self._tree_resident_destinations()
                   if not (self.box / d).is_file()]
        self.assertEqual(
            missing, [],
            "the candidate builder omits tree-resident files the release build places "
            "(three of the twelve box gates then refuse on the builder, not the product):\n  "
            + "\n  ".join(missing))

    def test_the_mission_brief_slot_is_the_generic_template_not_argos_own(self):
        """The slot must exist AND be the <FILL> template. Argo's real brief is
        extraction_scope: argo-reference and must never ship; a candidate box
        carrying it would hand a walker content no customer receives."""
        slot = self.box / ".tropo-studio" / "mission-brief.md"
        self.assertTrue(slot.is_file(), "mission-brief boot slot absent from the candidate box")
        body = slot.read_text(encoding="utf-8")
        self.assertIn("<FILL", body, "the shipped mission-brief slot is not the generic template")


if __name__ == "__main__":
    unittest.main()
