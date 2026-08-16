"""Causal suite for the v1.88 weld batch (dev-spec cb194126).

Every weld here exists because a v1.87 receipt recorded it going wrong, so every
test carries a mutation control: restore the pre-weld behaviour and assert the
original defect returns. A regression test that stays green against the bug it
describes is measuring something else — that lesson cost this studio five
superseded packages, and it is the reason each class below has a
`*_when_*_restored` twin.

Plants are on the real doors named in the spec's committed_substrate, not on
helpers: the RELEASE-NOTES copy block in tropo-build-release.py, the briefing
stamp/verify pair, the entry flip, and the journal mirror.

AC1 ShipManifestTests    — neither doc surface reaches the built box
AC2 BriefingStampTests   — stamped at build, verified against sealed bytes at fire
AC4 EntryFlipTests       — flipped to shipped, and re-indexed, before manifest gen
AC5 JournalWeldTests     — one publication, two records, idempotent
"""
from __future__ import annotations

import importlib.util
import io
import re
import unittest
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]

BUILD_TOOL = TOOLS / "tropo-build-release.py"
PUBLISH_TOOL = TOOLS / "tropo-publish-release.py"
BRIEFING_REL = "agents/tropo/briefing-package/current-release-notes.md"

# The v1.86 package MANIFEST.md is the receipt-grade fixture for "what ships".
# NOTE: updates/tropo-update-v1.86.0/files/ is an update DELTA, not a full box —
# reading it as a box was a near-miss during this build. The manifest is the
# artifact that actually enumerates the shipped tree.
SHIPPED_MANIFEST = ROOT / "updates" / "tropo-update-v1.86.0" / "files" / "MANIFEST.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class ShipManifestTests(unittest.TestCase):
    """AC1 — RELEASE-NOTES.md and TROPO-CAPABILITIES.md leave the box."""

    def test_the_defect_is_real_and_this_fixture_can_see_it(self):
        """Control: the shipped v1.86 manifest carries both surfaces.

        Without this, a later 'the box lacks them' assertion could pass because
        the fixture cannot see box contents at all.
        """
        manifest = _source(SHIPPED_MANIFEST)
        for surface in ("RELEASE-NOTES.md", "TROPO-CAPABILITIES.md"):
            self.assertRegex(
                manifest, rf"(?m)^\| {re.escape(surface)} \|",
                msg=f"fixture cannot see shipped {surface}",
            )

    def test_no_build_path_copies_release_notes_into_the_box(self):
        """The signature of 'copies into the box' is a build_dir destination.

        An earlier version of this detector looked for a single line containing
        both the filename and `copy_file`. The original block never had one — the
        destination and the copy are separate lines — so it was blind to the very
        code it was written to forbid, and only the mutation control below found
        that out.
        """
        build = _source(BUILD_TOOL)
        offenders = re.findall(
            r"os\.path\.join\(\s*build_dir\s*,\s*'RELEASE-NOTES\.md'\s*\)", build
        )
        self.assertEqual(
            offenders, [],
            "a build path still targets RELEASE-NOTES.md into the box",
        )

    def test_the_removal_is_explained_where_the_copy_used_to_be(self):
        """The next reader must find the ruling, not an unexplained absence."""
        build = _source(BUILD_TOOL)
        self.assertIn("RELEASE-NOTES.md deliberately does NOT ship", build)

    def test_unaffected_root_docs_still_ship(self):
        """The weld removes two surfaces; it must not thin the box further."""
        build = _source(BUILD_TOOL)
        for keeper in ("CHANGELOG.md",):
            self.assertIn(keeper, build, f"{keeper} lost its build path")

    def test_release_notes_returns_to_the_box_when_the_copy_block_is_restored(self):
        """Mutation control for AC1's first door — the verbatim pre-weld block.

        This is not decorative. Its first version proved the detector above was
        blind, because the deleted block spreads the filename and the copy call
        across separate lines. The detector was rewritten because this failed.
        """
        restored = (
            "    rn_src = os.path.join(tropo_roots.STUDIO_ROOT, 'RELEASE-NOTES.md')\n"
            "    if os.path.exists(rn_src):\n"
            "        rn_dst = os.path.join(build_dir, 'RELEASE-NOTES.md')\n"
            "        copy_file(rn_src, rn_dst, DRY_RUN)\n"
        )
        offenders = re.findall(
            r"os\.path\.join\(\s*build_dir\s*,\s*'RELEASE-NOTES\.md'\s*\)", restored
        )
        self.assertNotEqual(
            offenders, [],
            "the detector cannot see the pre-weld copy block, so its green means nothing",
        )


class BriefingStampTests(unittest.TestCase):
    """AC2 — stamped at BUILD (it ships), verified against the SEALED copy at fire."""

    def setUp(self):
        self.build = _load("build_under_test_ac2", BUILD_TOOL)
        self.publish = _load("publish_under_test_ac2", PUBLISH_TOOL)

    def test_the_briefing_surface_actually_ships(self):
        """The premise of the whole ruling: a fire-time write would be too late."""
        self.assertIn(BRIEFING_REL, _source(SHIPPED_MANIFEST),
                      "if this surface does not ship, AC2's mechanism ruling is moot")

    def test_the_stamp_runs_before_the_box_is_assembled(self):
        """Ordering IS the weld — after build_from_manifest the bytes are copied."""
        build = _source(BUILD_TOOL)
        stamp_at = build.index("step_3h_stamp_briefing_notes(new_version)")
        assemble_at = build.index("build_from_manifest(build_dir, manifest_entries)")
        self.assertLess(
            stamp_at, assemble_at,
            "the stamp must precede assembly or it cannot reach the shipped copy",
        )

    def test_release_version_has_exactly_one_writer(self):
        """Step 10.9 used to write it too — after the box snapshot, non-blocking.

        Two writers agreeing on a value while only one reaches the artifact reads
        as belt-and-braces to the next person and is how v1.87 shipped stale.
        """
        build = _source(BUILD_TOOL)
        writers = re.findall(r"^\s*_rn_new = _re\.sub\(\s*$", build, re.MULTILINE)
        self.assertNotIn(
            "release_version:\\s*).*$', f'\\\\g<1>v{new_version}", build,
            "Step 10.9 is writing release_version again — the too-late writer is back",
        )
        self.assertEqual(
            build.count("_set(fm, 'release_version', label)"), 1,
            "release_version should have exactly one writer (step_3h)",
        )

    def test_fire_verifies_the_sealed_bytes_and_accepts_a_matching_box(self):
        with self._sealed_box("v1.88.0") as (dist, version):
            self.publish._verify_sealed_briefing_notes(version, dist)

    def test_fire_refuses_a_box_whose_sealed_copy_names_the_previous_version(self):
        """The exact v1.87 defect, reproduced end to end."""
        with self._sealed_box("v1.87.0") as (dist, _):
            with self.assertRaises(self.publish.PublishError) as caught:
                self.publish._verify_sealed_briefing_notes("1.88.0", dist)
        message = str(caught.exception)
        self.assertIn("v1.87.0", message, "the refusal must name what it found")
        self.assertIn("Rebuild", message, "the refusal must name the cure")

    def test_fire_refuses_a_box_missing_the_surface_entirely(self):
        with self._sealed_box(None) as (dist, _):
            with self.assertRaises(self.publish.PublishError) as caught:
                self.publish._verify_sealed_briefing_notes("1.88.0", dist)
        self.assertIn("contains no", str(caught.exception))

    def test_fire_refuses_when_there_is_no_package_at_all(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(self.publish.PublishError) as caught:
                self.publish._verify_sealed_briefing_notes("1.88.0", Path(tmp))
        self.assertIn("no package", str(caught.exception))

    from contextlib import contextmanager

    @contextmanager
    def _sealed_box(self, sealed_version: str | None):
        """A real zip shaped like the package, sealed at a chosen version."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            with zipfile.ZipFile(dist / "tropo-os-v1.88.0.zip", "w") as box:
                box.writestr("README.md", "# box\n")
                if sealed_version is not None:
                    box.writestr(
                        f"tropo-os-v1.88.0/{BRIEFING_REL}",
                        f"---\nuid: f6a967fd\nrelease_version: {sealed_version}\n---\nnotes\n",
                    )
            yield dist, "1.88.0"


class ShipManifestCapabilitiesDoorTests(unittest.TestCase):
    """AC1's SECOND door, plant included — directed by A149 2026-08-15.

    My first suite proved the RELEASE-NOTES door and only *mentioned*
    TROPO-CAPABILITIES in a control, which is the vacuous-green class this file
    exists to prevent. This runs the production loader against an isolated index
    and plants a reactivated f3473526 row, so the assertion is causal rather than
    a helper-only predicate.

    The plant also documents a live defect it caught: retiring the entry edits the
    FILE, but load_manifest_entries reads the INDEX. Until the row is re-derived
    the door is still open, and the manifest still returns the surface.
    """

    def setUp(self):
        self.build = _load("build_under_test_ac1b", BUILD_TOOL)
        self.root_uid = self.build.read_manifest_root_uid(
            self.build.SHIP_ARTIFACT_CAPSULE_PATH
        )
        self.assertTrue(self.root_uid, "manifest root uid must resolve")

    def _entries(self, index_path):
        return self.build.load_manifest_entries(str(index_path), self.root_uid)

    @staticmethod
    def _capabilities(entries):
        return [e for e in entries
                if "TROPO-CAPABILITIES" in str(e.get("canonical_source", ""))]

    def test_production_index_no_longer_ships_the_capabilities_surface(self):
        entries = self._entries(self.build.INDEX_PATH)
        self.assertEqual(
            self._capabilities(entries), [],
            "TROPO-CAPABILITIES.md still resolves through the production manifest "
            "loader; the ship-artifact row is still active in the index",
        )

    def test_reactivating_the_ship_artifact_reopens_the_door(self):
        """THE PLANT. Restore an active f3473526 row in an isolated index and the
        production loader returns the surface again; remove it and it does not."""
        import json as _json
        import tempfile

        plant = {
            "uid": "f3473526", "type": "ship-artifact",
            "title": "Ship: TROPO-CAPABILITIES.md",
            "state": "active", "status": "locked",
            "kind": "file", "target": ["release"],
            "canonical_source": "argo-os/TROPO-CAPABILITIES.md",
            "source_mode": "direct-copy",
            "member_of": [self.root_uid], "parent": None,
            "schema_version": 2, "file_ext": "md",
            "path": "vault/files/f3473526.md",
        }
        live = Path(self.build.INDEX_PATH).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            planted = Path(tmp) / "planted-index.jsonl"
            planted.write_text(live + _json.dumps(plant) + "\n", encoding="utf-8")
            with_plant = self._capabilities(self._entries(planted))

            clean = Path(tmp) / "clean-index.jsonl"
            clean.write_text(live, encoding="utf-8")
            without_plant = self._capabilities(self._entries(clean))

        self.assertEqual(
            len(with_plant), 1,
            "the plant did not reopen the door, so this test proves nothing about "
            "the door being shut",
        )
        self.assertEqual(
            without_plant, [],
            "removing the plant must close the door again",
        )


class BadgeStampTests(unittest.TestCase):
    """AC3 — the website badge, stamped from the artifact that actually shipped."""

    def setUp(self):
        self.publish = _load("publish_under_test_ac3", PUBLISH_TOOL)

    def test_human_size_reproduces_the_hand_maintained_convention(self):
        """6552432 bytes was hand-written as '6.2 MB' for v1.87.

        Deriving a display string that disagrees with the established convention
        would replace a stale badge with a wrong-looking one.
        """
        self.assertEqual(self.publish._human_size(6552432), "6.2 MB")

    def test_the_badge_is_stamped_from_the_real_zip_not_a_receipt_field(self):
        import json as _json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tropo-app").mkdir(parents=True)
            badge = root / "tropo-app" / "os-release.json"
            badge.write_text(_json.dumps({
                "schema": "tropo.os-release/v1", "version": "v1.80.0",
                "fileSize": "5.0 MB", "sizeBytes": 1, "releasedAt": "2026-01-01",
            }))
            dist = root / "dist"
            dist.mkdir()
            payload = b"x" * 3_000_000
            (dist / "tropo-os-v1.88.0.zip").write_bytes(payload)

            original_root = self.publish.tropo_roots.STUDIO_ROOT
            self.publish.tropo_roots.STUDIO_ROOT = root
            try:
                self.publish._stamp_os_release_badge("1.88.0", dist, "2026-08-15")
            finally:
                self.publish.tropo_roots.STUDIO_ROOT = original_root

            stamped = _json.loads(badge.read_text())
        self.assertEqual(stamped["version"], "v1.88.0")
        self.assertEqual(stamped["sizeBytes"], len(payload),
                         "sizeBytes must measure the real zip")
        self.assertEqual(stamped["releasedAt"], "2026-08-15")
        self.assertEqual(stamped["schema"], "tropo.os-release/v1",
                         "unrelated fields must survive the stamp")

    def test_refuses_when_there_is_no_package_to_measure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(self.publish.PublishError) as caught:
                self.publish._stamp_os_release_badge("1.88.0", Path(tmp), "2026-08-15")
        self.assertIn("no package", str(caught.exception))

    def test_refuses_when_the_badge_file_is_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            dist.mkdir(parents=True)
            (dist / "tropo-os-v1.88.0.zip").write_bytes(b"z")
            original_root = self.publish.tropo_roots.STUDIO_ROOT
            self.publish.tropo_roots.STUDIO_ROOT = root
            try:
                with self.assertRaises(self.publish.PublishError) as caught:
                    self.publish._stamp_os_release_badge("1.88.0", dist, "2026-08-15")
            finally:
                self.publish.tropo_roots.STUDIO_ROOT = original_root
        self.assertIn("not found", str(caught.exception))

    def test_the_manual_site_split_step_is_named_not_implied(self):
        """A stamped studio badge with an unpublished site is the same
        correct-here-wrong-there shape the briefing notes had."""
        source = _source(PUBLISH_TOOL)
        self.assertIn("NEXT (manual)", source)
        self.assertIn("npm run deploy", source)

    def test_the_stamp_runs_at_fire(self):
        source = _source(PUBLISH_TOOL)
        self.assertIn("_stamp_os_release_badge(", source[source.index("Uploading Supabase zip"):])


class EntryFlipTests(unittest.TestCase):
    """AC4 — flipped to shipped AND re-indexed, before manifest generation."""

    def setUp(self):
        self.publish = _load("publish_under_test_ac4", PUBLISH_TOOL)

    def test_the_flip_precedes_manifest_generation(self):
        """Compare CALL sites. Matching the bare name also finds the `def`, which
        sits hundreds of lines above every caller and inverts the comparison."""
        source = _source(PUBLISH_TOOL)
        flip_at = source.index("        _flip_release_entry_to_shipped(version)")
        manifest_at = source.index("        _upload_update_manifest()")
        self.assertLess(
            flip_at, manifest_at,
            "flipping after generation yields a correct entry and a wrong manifest",
        )

    def test_the_generator_reads_shipped_rows_from_the_index(self):
        """Why the flip must be paired with a re-index, stated by the consumer."""
        generator = _source(TOOLS / "tropo-generate-update-manifest.py")
        self.assertIn("'shipped'", generator)

    def test_the_flip_is_paired_with_an_index_freshen(self):
        source = _source(PUBLISH_TOOL)
        body_start = source.index("def _flip_release_entry_to_shipped")
        body_end = source.index("def _confirm_tty")
        body = source[body_start:body_end]
        self.assertIn(
            "_freshen_index_row", body,
            "stamping the file without freshening leaves file and index disagreeing, "
            "which is the half that keeps the manifest wrong",
        )

    def test_a_missing_release_entry_refuses_rather_than_skipping_quietly(self):
        original = self.publish._find_release_entry
        self.publish._find_release_entry = lambda version: (None, None)
        try:
            with self.assertRaises(self.publish.PublishError) as caught:
                self.publish._flip_release_entry_to_shipped("1.88.0")
        finally:
            self.publish._find_release_entry = original
        self.assertIn("manifest", str(caught.exception))

    def test_an_already_shipped_entry_is_left_alone(self):
        """Idempotence: a retried fire must not rewrite provenance."""
        calls = []
        original_find = self.publish._find_release_entry
        original_stamp = self.publish._stamp_release_entry
        self.publish._find_release_entry = lambda v: (Path("/x"), {"status": "shipped", "uid": "aaaaaaaa"})
        self.publish._stamp_release_entry = lambda *a, **k: calls.append(a) or True
        try:
            self.publish._flip_release_entry_to_shipped("1.88.0")
        finally:
            self.publish._find_release_entry = original_find
            self.publish._stamp_release_entry = original_stamp
        self.assertEqual(calls, [], "an already-shipped entry must not be re-stamped")


class HandBackTests(unittest.TestCase):
    """AC6 — the 403-night improvisation, productized.

    v1.87 was built on a host whose principal could not push to the public repo,
    and the transfer was invented at 3am: a branch, a zip, a SHA256SUMS, and
    `sha256sum -c` on the far side. It worked and then lived only in one agent's
    memory. These tests are what turns it into a path.
    """

    def setUp(self):
        self.publish = _load("publish_under_test_ac6", PUBLISH_TOOL)

    def _package(self, root: Path, version: str = "1.88.0", body: bytes = b"box-bytes") -> Path:
        dist = root / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        zip_path = dist / f"tropo-os-v{version}.zip"
        zip_path.write_bytes(body)
        return zip_path

    def test_the_bundle_carries_zip_sums_and_provenance(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = self._package(root)
            payload = root / "handback" / "v1.88.0"
            record = self.publish.write_transfer_bundle("1.88.0", zip_path, payload)

            self.assertTrue((payload / "tropo-os-v1.88.0.zip").is_file())
            self.assertTrue((payload / "SHA256SUMS").is_file())
            self.assertTrue((payload / "build-provenance.json").is_file())
            self.assertEqual(record["size_bytes"], zip_path.stat().st_size)

    def test_the_digest_comes_from_the_same_function_the_freeze_uses(self):
        """A second hashing path can disagree with the receipt while both look right."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = self._package(root)
            payload = root / "handback" / "v1.88.0"
            record = self.publish.write_transfer_bundle("1.88.0", zip_path, payload)
            self.assertEqual(
                record["package_sha256"],
                self.publish.release_package.hash_final_zip(zip_path),
            )

    def test_sha256sums_is_coreutils_verifiable_verbatim(self):
        """`sha256sum -c SHA256SUMS` is the documented far-side gesture. An
        absolute path or a stray format change breaks it silently."""
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = self._package(root)
            payload = root / "handback" / "v1.88.0"
            self.publish.write_transfer_bundle("1.88.0", zip_path, payload)
            checked = subprocess.run(
                ["sha256sum", "-c", "SHA256SUMS"],
                cwd=str(payload), capture_output=True, text=True,
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_a_matching_bundle_verifies(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = self._package(root)
            payload = root / "handback" / "v1.88.0"
            record = self.publish.write_transfer_bundle("1.88.0", zip_path, payload)
            returned = self.publish.verify_transfer_bundle(
                "1.88.0", payload, record["package_sha256"]
            )
            self.assertEqual(returned, record["package_sha256"])

    def test_a_mismatch_refuses_and_prints_BOTH_values(self):
        """The AC's explicit requirement. A refusal naming one digest cannot be
        told apart from corruption; naming both turns it into a diagnosis."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = self._package(root)
            payload = root / "handback" / "v1.88.0"
            record = self.publish.write_transfer_bundle("1.88.0", zip_path, payload)
            wrong = "0" * 64
            with self.assertRaises(self.publish.PublishError) as caught:
                self.publish.verify_transfer_bundle("1.88.0", payload, wrong)
        message = str(caught.exception)
        self.assertIn(wrong, message, "the expected digest must be printed")
        self.assertIn(record["package_sha256"], message, "the actual digest must be printed")

    def test_a_truncated_transfer_is_caught(self):
        """The realistic failure, not the dramatic one: bytes lost in transit."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = self._package(root, body=b"complete-box-bytes")
            payload = root / "handback" / "v1.88.0"
            record = self.publish.write_transfer_bundle("1.88.0", zip_path, payload)
            (payload / "tropo-os-v1.88.0.zip").write_bytes(b"complete-box")
            with self.assertRaises(self.publish.PublishError):
                self.publish.verify_transfer_bundle(
                    "1.88.0", payload, record["package_sha256"]
                )

    def test_a_missing_receipt_digest_refuses_rather_than_passing_vacuously(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = self._package(root)
            payload = root / "handback" / "v1.88.0"
            self.publish.write_transfer_bundle("1.88.0", zip_path, payload)
            with self.assertRaises(self.publish.PublishError) as caught:
                self.publish.verify_transfer_bundle("1.88.0", payload, "")
        self.assertIn("nothing to compare", str(caught.exception))

    def test_nothing_to_hand_back_refuses(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(self.publish.PublishError) as caught:
                self.publish.write_transfer_bundle(
                    "1.88.0", root / "dist" / "absent.zip", root / "handback"
                )
        self.assertIn("nothing to hand back", str(caught.exception))

    def test_round_trip_through_a_real_git_branch(self):
        """The whole point is a bundle that survives a branch hop.

        Runs the real cmd_handback against a real git repo — the improvisation
        performed, not modelled. Push is expected to fail (no remote), and the
        exit code must say 'committed but not pushed' rather than pretend success.
        """
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
            (root / "seed").write_text("seed\n")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)

            releases = root / "releases"
            (releases / "v1.88.0" / "dist").mkdir(parents=True)
            payload_bytes = b"the-real-box"
            (releases / "v1.88.0" / "dist" / "tropo-os-v1.88.0.zip").write_bytes(payload_bytes)

            saved_root = self.publish.tropo_roots.STUDIO_ROOT
            saved_releases = self.publish.tropo_roots.RELEASES_DIR
            self.publish.tropo_roots.STUDIO_ROOT = root
            self.publish.tropo_roots.RELEASES_DIR = releases
            try:
                class _Args:
                    version = "1.88.0"
                    no_branch = False
                rc = self.publish.cmd_handback(_Args())
            finally:
                self.publish.tropo_roots.STUDIO_ROOT = saved_root
                self.publish.tropo_roots.RELEASES_DIR = saved_releases

            self.assertEqual(rc, 6, "no remote configured, so push must fail honestly")
            branch = subprocess.run(
                ["git", "branch", "--list", "transfer/v1.88.0-dist"],
                cwd=root, capture_output=True, text=True,
            ).stdout
            self.assertIn("transfer/v1.88.0-dist", branch,
                          "the transfer branch must exist locally")
            back_on = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=root, capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(back_on, "main",
                             "the producing host must be left on its original branch")
            listed = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", "transfer/v1.88.0-dist"],
                cwd=root, capture_output=True, text=True,
            ).stdout
            for expected in ("SHA256SUMS", "build-provenance.json", "tropo-os-v1.88.0.zip"):
                self.assertIn(expected, listed, f"{expected} missing from the branch")


class HandBackReceiveRuntimeTests(unittest.TestCase):
    """AC6 receive→stage, executed rather than described (A149 NO-GO 2026-08-15).

    My first AC6 suite proved produce, digest equality, mismatch, truncation and
    coreutils verification — and never once called cmd_receive. A149 ran it and
    found receive verifies the zip, copies it to dist/, and then cmd_stage exits 3
    because the unpacked box it actually consumes was never reconstructed. A
    verified hand-back that cannot stage has moved the artefact, not the release.
    These tests drive the production command.
    """

    def setUp(self):
        self.publish = _load("publish_under_test_ac6rt", PUBLISH_TOOL)

    def _studio(self, tmp: Path, version="1.88.0", members=None):
        """A real hand-back: a zip shaped like the box, beside its SHA256SUMS."""
        releases = tmp / "releases"
        payload = tmp / "handback" / f"v{version}"
        payload.mkdir(parents=True)
        zip_path = payload / f"tropo-os-v{version}.zip"
        members = members or [
            (f"tropo-os-v{version}/README.md", b"# box\n"),
            (f"tropo-os-v{version}/vault/00-index.jsonl", b"{}\n"),
        ]
        with zipfile.ZipFile(zip_path, "w") as box:
            for name, body in members:
                box.writestr(name, body)
        digest = self.publish.release_package.hash_final_zip(zip_path)
        (payload / "SHA256SUMS").write_text(f"{digest}  {zip_path.name}\n")
        return releases, payload, digest

    class _Args:
        version = "1.88.0"
        activation_uid = "aaaaaaaa"
        payload_dir = None
        verify_only = False
        remote = None
        clone = None
        clone_dir = None
        allow_delete = False

    def _run_receive(self, tmp, releases, payload, digest, *, verify_only=False,
                     stage_recorder=None):
        saved = (self.publish.tropo_roots.STUDIO_ROOT,
                 self.publish.tropo_roots.RELEASES_DIR,
                 self.publish._frozen_package_sha256,
                 self.publish.cmd_stage)
        self.publish.tropo_roots.STUDIO_ROOT = tmp
        self.publish.tropo_roots.RELEASES_DIR = releases
        # The receipt lookup is not the subject under test; everything downstream is real.
        self.publish._frozen_package_sha256 = lambda v, a: digest
        if stage_recorder is not None:
            self.publish.cmd_stage = stage_recorder
        args = self._Args()
        args.payload_dir = str(payload)
        args.verify_only = verify_only
        try:
            return self.publish.cmd_receive(args)
        finally:
            (self.publish.tropo_roots.STUDIO_ROOT,
             self.publish.tropo_roots.RELEASES_DIR,
             self.publish._frozen_package_sha256,
             self.publish.cmd_stage) = saved

    def test_receive_reconstructs_the_box_and_enters_the_stage_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            releases, payload, digest = self._studio(tmp)
            entered = []
            rc = self._run_receive(
                tmp, releases, payload, digest,
                stage_recorder=lambda a: entered.append(a.version) or 0,
            )
            build_dir = releases / "v1.88.0" / "builds" / "tropo-os-v1.88.0"
            self.assertTrue(build_dir.is_dir(),
                            "the canonical box directory stage consumes was not rebuilt")
            self.assertTrue((build_dir / "README.md").is_file())
            self.assertTrue((build_dir / "vault" / "00-index.jsonl").is_file())
            self.assertEqual(entered, ["1.88.0"], "the production stage path was not entered")
            self.assertEqual(rc, 0)

    def test_the_exact_no_go_returns_when_extraction_is_removed(self):
        """Negative plant A149 asked for: without the unpack, stage exits 3.

        This reproduces his runtime evidence — cmd_receive_exit=3,
        dist_zip_exists=True, build_dir_exists=False.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            releases, payload, digest = self._studio(tmp)
            saved_reconstruct = self.publish.reconstruct_build_dir
            self.publish.reconstruct_build_dir = lambda *a, **k: None  # the pre-fix behaviour
            try:
                rc = self._run_receive(tmp, releases, payload, digest)
            finally:
                self.publish.reconstruct_build_dir = saved_reconstruct
            build_dir = releases / "v1.88.0" / "builds" / "tropo-os-v1.88.0"
            self.assertEqual(rc, 3, "without the unpack, real cmd_stage must exit 3")
            self.assertTrue((releases / "v1.88.0" / "dist" / "tropo-os-v1.88.0.zip").is_file(),
                            "dist zip present — the artefact moved but the release did not")
            self.assertFalse(build_dir.is_dir(), "build dir must be absent in the plant")

    def test_verify_only_reconstructs_but_does_not_stage(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            releases, payload, digest = self._studio(tmp)
            entered = []
            rc = self._run_receive(
                tmp, releases, payload, digest, verify_only=True,
                stage_recorder=lambda a: entered.append(a.version) or 0,
            )
            self.assertEqual(rc, 0)
            self.assertEqual(entered, [], "--verify-only must not stage")
            self.assertTrue(
                (releases / "v1.88.0" / "builds" / "tropo-os-v1.88.0").is_dir())

    def test_a_traversing_member_is_refused_before_anything_is_written(self):
        """The bytes came from another host; a crafted archive must not escape."""
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            releases, payload, digest = self._studio(
                tmp, members=[("tropo-os-v1.88.0/ok.md", b"ok"),
                              ("../escaped.md", b"nope")])
            rc = self._run_receive(tmp, releases, payload, digest)
            self.assertEqual(rc, 4)
            self.assertFalse((tmp / "escaped.md").exists(), "traversal was written")
            self.assertFalse((tmp.parent / "escaped.md").exists())

    def test_a_second_box_root_is_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            releases, payload, digest = self._studio(
                tmp, members=[("tropo-os-v1.88.0/ok.md", b"ok"),
                              ("some-other-tree/x.md", b"x")])
            rc = self._run_receive(tmp, releases, payload, digest)
            self.assertEqual(rc, 4)

    def test_a_digest_mismatch_still_refuses_before_unpacking(self):
        """Ordering: verification precedes extraction, so bad bytes never land."""
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            releases, payload, _digest = self._studio(tmp)
            rc = self._run_receive(tmp, releases, payload, "0" * 64)
            self.assertEqual(rc, 3)
            self.assertFalse((releases / "v1.88.0" / "builds").exists(),
                             "nothing may be unpacked from an unverified bundle")


class CloserCompanionTests(unittest.TestCase):
    """AC7 — a closed cycle leaves zero unexplained archives.

    Mike's ruling on the v1.87 build refusal: the close path emits a correlated
    close event for EVERY record it archives, companions included, "because a
    customer's studio would mint the same silent archives the first time they
    close a cycle." The gate found fifteen and the cure was hand-written events
    after the fact.
    """

    RUNTIME = TOOLS / "9e7003b1.py"

    def setUp(self):
        self.runtime_source = _source(self.RUNTIME)
        start = self.runtime_source.index("    def _close_substrate() -> None:")
        end = self.runtime_source.index("    def _substrate_is_closed() -> bool:")
        self.close_body = self.runtime_source[start:end]

    def test_the_closer_still_stamps_all_five_records(self):
        """Guard the premise: if the write set shrinks, the emission set must too."""
        for uid_var in ("plan_uid", "entry_uid", "root_uid", "run_uid", "activation_uid"):
            self.assertIn(uid_var, self.close_body,
                          f"{uid_var} left the terminal write set")

    def test_every_stamped_record_gets_a_correlated_close_event(self):
        """The weld: emission sits inside the same loop as the stamp, so a record
        cannot be moved terminal without its event."""
        self.assertIn("_emit_cycle_closed(VAULT_ROOT, uid", self.close_body)
        stamp_at = self.close_body.index("if _stamp_terminal_status(uid, terminal, actor):")
        emit_at = self.close_body.index("_emit_cycle_closed(VAULT_ROOT, uid")
        self.assertLess(
            stamp_at, emit_at,
            "the event must follow its stamp inside the loop, not precede it",
        )

    def test_the_emission_is_gated_on_a_successful_stamp(self):
        """A record that was already terminal must not mint a second event."""
        loop = self.close_body[self.close_body.index("for uid, terminal in"):]
        stamp_line = "if _stamp_terminal_status(uid, terminal, actor):"
        self.assertIn(stamp_line, loop)
        after_guard = loop[loop.index(stamp_line):]
        self.assertIn("_emit_cycle_closed", after_guard,
                      "emission must live under the stamp-succeeded branch")

    def _emitter_source(self) -> str:
        """The whole function, not a fixed-width window.

        This used to slice [:3000]. Adding a five-line provenance comment pushed
        the assertions past the window and turned two tests red on a magic number
        rather than on a regression — a test that fails when the code it inspects
        merely gets longer is measuring the wrong thing.
        """
        start = self.runtime_source.index("def _emit_cycle_closed")
        rest = self.runtime_source[start:]
        nxt = rest.index("\ndef ", 1)
        return rest[:nxt]

    def test_the_emitter_is_idempotent_and_non_blocking(self):
        """Both properties are what make per-record emission safe on a path that
        runs after the release is already public."""
        emitter = self._emitter_source()
        self.assertIn("_completion_event_exists", emitter,
                      "a retried close must not mint duplicate events")
        self.assertIn("return False", emitter)
        self.assertIn("WARN:", emitter,
                      "an emit failure must be logged, not raised, after the stamp")

    def test_check32_accepts_the_correlation_shape_this_emits(self):
        """Both halves must agree on the contract or the weld proves nothing:
        Check 32 keys on correlationid over cycle.closed events."""
        validator = _source(TOOLS / "tropo-validate.py")
        check = validator[validator.index("def check_completion_recording"):][:2600]
        self.assertIn("tropo.cycle.closed", check)
        self.assertIn("correlationid", check)
        emitter = self._emitter_source()
        self.assertIn('"tropo.cycle.closed"', emitter)
        self.assertIn("correlationid=root_uid", emitter)

    def test_the_emitter_declares_the_tools_own_uid_not_an_agent_root(self):
        """Provenance (A149, pre-AC8): the runtime emitted these events as
        123e12e7 — "Talos — Agent Root Project" — rather than as the tool that
        wrote them. The tool's own uid is 9e7003b1.

        Asserts the DECLARED CONSTANTS and that both emit sites reference them,
        rather than a literal call string. The first version of this test pinned
        the literal, so when production moved to one constant — the better shape,
        and the one A149 asked for — my own test went red and demanded the worse
        one back. A test that pins a spelling instead of a property will eventually
        argue against the fix.
        """
        source = self.runtime_source
        self.assertIn('TOOL_SOURCE = "/tools/pipeline-runtime"', source)
        self.assertIn('TOOL_UID = "9e7003b1"', source)
        self.assertEqual(
            source.count("TOOL_SOURCE, TOOL_UID"), 2,
            "both pipeline-runtime emit sites must reference the declared constants",
        )
        # The agent-root uid may survive only in the comment explaining why it is wrong.
        for line in source.splitlines():
            if "123e12e7" in line:
                self.assertTrue(
                    line.lstrip().startswith("#"),
                    f"agent-root uid used as a value, not just explained: {line.strip()}",
                )

    def test_silent_archives_return_when_the_emission_is_removed(self):
        """Mutation control: strip the per-record emit and the loop reverts to
        stamping four companions with no event — the fifteen-findings class."""
        reverted = self.close_body.replace(
            "                _emit_cycle_closed(VAULT_ROOT, uid, activation_uid=activation_uid)\n",
            "",
        )
        self.assertNotEqual(reverted, self.close_body, "the plant did not apply")
        self.assertNotIn("_emit_cycle_closed(VAULT_ROOT, uid", reverted,
                         "with the emit removed, stamped companions carry no event")


class JournalWeldTests(unittest.TestCase):
    """AC5 — one publication, two records, and never a third."""

    def setUp(self):
        self.publish = _load("publish_under_test_ac5", PUBLISH_TOOL)

    def test_the_finalizer_receives_the_run_identity(self):
        """The pre-lock finding: it took (version, state, candidate) and had no run."""
        source = _source(PUBLISH_TOOL)
        signature = source[source.index("def _finalize_verified_publication_locked"):][:260]
        self.assertIn("ac7_context", signature,
                      "without the run identity the finalizer cannot reach the journal")

    def test_the_mirror_runs_inside_finalization(self):
        source = _source(PUBLISH_TOOL)
        self.assertIn("_mirror_published_event_to_journal(ac7_context, event_data, receipt_sha256)",
                      source)

    def test_closure_reads_the_journal_the_mirror_writes(self):
        """Both halves must agree on the assertion, or the weld proves nothing."""
        closure = _source(TOOLS / "lib" / "release_closure.py")
        self.assertIn("def assert_one_published_event", closure)
        self.assertIn("release_closure.assert_one_published_event", _source(PUBLISH_TOOL))

    def test_no_run_identity_is_a_no_op_not_a_refusal(self):
        """Stage/verify paths legitimately have no run; they must not start failing."""
        self.assertIsNone(
            self.publish._mirror_published_event_to_journal(None, {"a": 1}, "sha")
        )
        self.assertIsNone(self.publish._run_journal_folder(None))
        self.assertIsNone(self.publish._run_journal_folder({}))

    def test_release_closure_is_actually_loaded_in_this_module(self):
        """It was not, and the NameError would have fired during a real publish."""
        self.assertTrue(hasattr(self.publish, "release_closure"))
        self.assertEqual(
            self.publish.release_closure.PUBLISHED_EVENT, "tropo.release.published"
        )


if __name__ == "__main__":
    unittest.main()
