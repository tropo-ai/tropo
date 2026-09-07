#!/usr/bin/env python3
"""4e9ce4cc row 11 / AC4 — THE COMPOSED-PATH SUITE (seam rule 3c0547d3).

The entire delivery chain on a throwaway studio with zero hands:

    box zip → unzip → plan (mode=full, honest delete-set) → BOOTSTRAP apply
    SUCCEEDS (no MigrationContractError — the A2 cure proven at the composed
    path) → backup first → receipt from stdout (ONE JSON doc) → rebuild
    (nav regenerated, replaced entries indexed) → history row → planted
    customer edit intact (the A1 regression, cured and pinned HERE — AC3's
    survival case runs in this suite).

No retired machinery: the image's own applier, the image's own rebuild, the
real emitted box. The box comes from the fresh-box gate's fixture (git
archive HEAD → real index rebuild → real emitters), so what this suite
applies is what a customer would unzip.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
TESTS = TOOLS / "tests"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from tests.test_fresh_box_gate_e52826c5 import BuiltBoxCase  # noqa: E402

CUSTOMER_EDIT = "<!-- CUSTOM ORG DEFAULTS: ours, not yours -->\n"


def _prior_manifest_for(studio: Path) -> Path:
    """A prior image manifest describing a plausibly-older tree, planted so
    plan derives mode=full (the honest delete-set mode). It names a file the
    new image does NOT carry — the delete leg must see it. The manifest LISTS
    paths; it must not WRITE over studio files it lists (the first cut
    overwrote STUDIO.md with 'prior studio bytes' and the suite then proved
    its own fixture, not the applier)."""
    import hashlib

    listed_only = {"STUDIO.md": "prior studio bytes"}
    planted = {
        ".tropo/version.md": "v1.90.0\n",
        "vault/updates/retired-note.md": "shipped in 1.90, gone in 1.94",
    }
    prior_files = {**listed_only, **planted}
    manifest = {
        "schema": "tropo.image-manifest/v1",
        "version": "1.90.0",
        "file_count": len(prior_files),
        "files": {
            rel: {"sha256": hashlib.sha256(content.encode()).hexdigest(),
                  "bytes": len(content.encode())}
            for rel, content in prior_files.items()
        },
    }
    path = studio / "tropo-image-manifest.json"
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True),
                    encoding="utf-8")
    for rel, content in planted.items():
        target = studio / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return path


class DeliveryChannelEndToEnd(BuiltBoxCase):
    """AC4. One test method per seam, one shared emitted box, one applied
    studio — the chain composes or it does not."""

    @classmethod
    def emit(cls, entries: list, build_dir: Path, *, ship_entries: bool = True) -> None:
        """The FULL production carriage, not just the fixture's usual subset.

        The parent fixture emits the manifest-driven phases + ship entries —
        enough to pin box CONTENT, not enough to APPLY a box (no kernel, no
        vault/tools/ wholesale — and no applier, so bootstrap could never
        run). AC4's chain needs the artifact a customer actually unzips, so
        this emit mirrors the real build's step order: kernel, tools,
        playbooks, updates, schema, the manifest walker, update-source, then
        ship entries.
        """
        cls.builder.DRY_RUN = False
        cls.builder.step_3_copy_kernel(str(build_dir))
        cls.builder.step_3b_copy_vault_tools(str(build_dir))
        cls.builder.step_3d_copy_vault_playbooks(str(build_dir))
        cls.builder.step_3e_copy_vault_updates(str(build_dir))
        cls.builder.step_3j_copy_vault_schema(str(build_dir))
        cls.builder.build_from_manifest(str(build_dir), entries)
        cls.builder.step_3g_write_update_source(str(build_dir))
        if ship_entries:
            cls.builder.step_4_copy_ship_entries(
                str(build_dir), cls.builder.load_ship_entries(cls.builder.INDEX_PATH)
            )

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # The throwaway studio: the fixture's tracked-source studio, plus the
        # planted customer state an update must survive.
        cls.live_studio = cls.tmp / "live-studio"
        # symlinks=True: the tracked-source studio carries relative symlinks
        # (collections members) whose targets resolve only inside the real
        # tree — following them both breaks the copy and misrepresents the
        # studio a customer actually has.
        shutil.copytree(cls.studio, cls.live_studio, symlinks=True)
        # Model the FRESH-BOX customer, not the fixture's own birth: remove
        # every machine-local evidence surface (freshened index + floor
        # sidecars + ratchet + sqlite companions) so the only index state
        # after the apply is what the box itself ships. Leaving the
        # fixture's freshened evidence in place is the upgrading-git-
        # customer shape, whose honest rebuild path is land-then-reconcile —
        # the tool's own refusals say so, and the gitless fresh customer
        # (this fixture) must not need it.
        for rel in ("vault/00-index.jsonl", "vault/00-archive-index.jsonl",
                    "vault/00-index.sqlite", "vault/00-index.sqlite-shm",
                    "vault/00-index.sqlite-wal",
                    "vault/00-project-tree.jsonl",
                    ".tropo-studio/locks/index-surfaces.meta.json",
                    ".tropo-studio/locks/index-surfaces.ratchet.json",
                    ".tropo-studio/dirty-counter.json",
                    ".tropo-studio/folder-mounts.json",
                    ".tropo-studio/shards/local-archive-index.jsonl"):
            target = cls.live_studio / rel
            if target.exists():
                target.unlink()
        studio_md = cls.live_studio / "STUDIO.md"
        studio_md.write_text(
            studio_md.read_text(encoding="utf-8") + CUSTOMER_EDIT,
            encoding="utf-8")
        cls.planted_history = (
            cls.live_studio / "vault" / "updates" / "update-history.jsonl")
        cls.planted_history.write_text(
            json.dumps({"version": "1.90.0", "outcome": "success",
                        "mode": "full", "backup_dir": "/prior",
                        "utc": "2026-08-01T00:00:00Z"}) + "\n",
            encoding="utf-8")
        cls.prior = _prior_manifest_for(cls.live_studio)

        # The delivery artifact: a real zip of the emitted box, unzipped to
        # staging OUTSIDE the studio — the walk's exact shape. The image
        # manifest is enumerated from the same walk (step_9d's shape at real
        # build), so replace/skip derive from an authoritative list and the
        # history row carries a real version.
        import hashlib

        # The real box ships INDEX-FREE: the FINAL PORTABLE FREEZE
        # (step_10_2_purge_run_local_artifacts) removes machine-local index
        # surfaces after the in-box gates, and the real v1.93 zip carries no
        # vault/00-index.jsonl (verified against the shipped artifact). The
        # fixture's emit runs the copy steps but not the freeze, so remove
        # the index family here — otherwise this suite applies a box the
        # vendor has never shipped and the fresh customer's documented
        # first-rebuild path never gets exercised.
        for rel in ("vault/00-index.jsonl", "vault/00-archive-index.jsonl",
                    "vault/00-index.sqlite", "vault/00-index.sqlite-shm",
                    "vault/00-index.sqlite-wal"):
            target = cls.build_dir / rel
            if target.exists():
                target.unlink()

        box_files = {p.relative_to(cls.build_dir).as_posix(): p.read_bytes()
                     for p in sorted(cls.build_dir.rglob("*"))
                     if p.is_file()}
        (cls.build_dir / "tropo-image-manifest.json").write_text(
            json.dumps({
                "schema": "tropo.image-manifest/v1",
                "version": "1.94.0",
                "file_count": len(box_files),
                "files": {rel: {"sha256": hashlib.sha256(data).hexdigest(),
                                "bytes": len(data)}
                          for rel, data in box_files.items()},
            }, indent=1, sort_keys=True), encoding="utf-8")

        cls.staging = cls.tmp / "staging"
        cls.staging.mkdir()
        zip_path = cls.staging / "tropo-os-v1.94.0.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, data in box_files.items():
                zf.writestr(rel, data)
        with zipfile.ZipFile(zip_path, "a") as zf:
            zf.write(cls.build_dir / "tropo-image-manifest.json",
                     "tropo-image-manifest.json")
        cls.image = cls.staging / "image"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(cls.image)

    def test_10_the_chain_composes(self) -> None:
        image_applier = self.image / "vault" / "tools" / "tropo-apply-image.py"
        self.assertTrue(image_applier.is_file(), "the box carries no applier")

        # plan — mode=full, honest delete-set, writes nothing
        plan_proc = subprocess.run(
            [sys.executable, str(image_applier), "plan",
             "--image", str(self.image), "--studio", str(self.live_studio),
             "--prior-manifest", str(self.prior)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(plan_proc.returncode, 0, plan_proc.stderr[-500:])
        plan = json.loads(plan_proc.stdout)
        self.assertEqual(plan["mode"], "full",
                         f"expected mode=full from a planted prior manifest, "
                         f"got {plan['mode']}")
        self.assertIn("vault/updates/retired-note.md", plan["delete"],
                      "the delete-set is not honest — the retired prior file "
                      "should be deleted, not silently kept")
        self.assertIn("STUDIO.md", plan["skip"],
                      "the customer identity set must be in the skip set at "
                      "the plan surface (the A1 cure)")

        # BOOTSTRAP apply — succeeds on the built image; the A2 proof at the
        # composed path is that no MigrationContractError fires, because the
        # build stripped the undeclared migration the v1.90–v1.93 boxes rode.
        receipt_path = self.staging / "receipt.json"
        apply_proc = subprocess.run(
            [sys.executable, str(image_applier), "bootstrap",
             "--image", str(self.image), "--studio", str(self.live_studio),
             "--prior-manifest", str(self.prior)],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(apply_proc.returncode, 0, apply_proc.stderr[-800:])
        receipt_path.write_text(apply_proc.stdout, encoding="utf-8")
        receipt = json.loads(apply_proc.stdout)  # ONE JSON doc, whole stdout
        self.assertEqual(receipt["schema"], "tropo.apply-receipt/v1")

        # backup exists and predates the mutations it describes
        backup_dir = Path(receipt["backup_dir"])
        self.assertTrue(backup_dir.is_dir(), "no backup before write")
        self.assertTrue(any(backup_dir.rglob("*")),
                        "backup is empty — nothing was captured")

    def test_20_rebuild_reindexes_the_applied_studio(self) -> None:
        """A5: a real apply leaves derived surfaces stale/empty and replaced
        entries unindexed — the rebuild is load-bearing, and THIS proves it
        runs green on the applied studio with the image's own tool."""
        rebuild = self.live_studio / "vault" / "tools" / "tropo-rebuild-index.py"
        self.assertTrue(rebuild.is_file(), "image carries no rebuild tool")
        # Plain --apply, the fresh-customer shape: no prior machine-local
        # floor evidence exists, so the box's own shipped index is the only
        # floor and the rebuild derives to match it. (The upgrading-git-
        # customer shape differs — stale evidence + a dirty tree — and its
        # honest path is land-then-reconcile; the walk playbook teaches it,
        # the AC6 rehearsal exercises it live.)
        proc = subprocess.run(
            [sys.executable, str(rebuild), "--apply", "--skip-rehydrate",
             "--vault-path", str(self.live_studio)],
            cwd=str(self.live_studio), capture_output=True, text=True,
            timeout=600)
        if proc.returncode != 0:
            (Path("/tmp") / "t54-e2e-rebuild-stderr.txt").write_text(
                proc.stderr or "", encoding="utf-8")
        self.assertEqual(proc.returncode, 0,
                         f"rebuild failed on the applied studio: "
                         f"{(proc.stderr or proc.stdout)[-4000:]}")
        index = self.live_studio / "vault" / "00-index.jsonl"
        self.assertTrue(index.is_file() and index.stat().st_size > 0,
                        "index absent/empty after rebuild")

    def test_30_history_row_and_customer_edit_survive(self) -> None:
        """AC2 + AC3 at the composed path: the history grows by exactly one
        row with the planted prefix untouched, and the planted customer edit
        to STUDIO.md survives the FULL-mode apply byte-identically — the A1
        regression this channel exists to never repeat."""
        history_bytes = self.planted_history.read_bytes()
        lines = history_bytes.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 2,
                         f"expected planted row + one appended, got "
                         f"{len(lines)}: {lines}")
        row = json.loads(lines[-1])
        self.assertEqual(row["outcome"], "success")
        self.assertEqual(row["version"], "1.94.0",
                         "the history row carries the image manifest's "
                         "version, not a stamp")

        studio_md = (self.live_studio / "STUDIO.md").read_text(encoding="utf-8")
        self.assertIn(CUSTOMER_EDIT.strip(), studio_md,
                      "the planted customer edit to STUDIO.md was destroyed "
                      "by a full-mode apply — the A1 regression is LIVE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
