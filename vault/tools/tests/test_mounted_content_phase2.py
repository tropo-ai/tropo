#!/usr/bin/env python3
"""Focused proofs for corrected brief 811cf6d2, mounted-content Phase 2."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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


rebuild = _load("phase2_rebuild", TOOLS / "tropo-rebuild-index.py")
search = _load("phase2_search", TOOLS / "tropo-vault-search.py")
validate = _load("phase2_validate", TOOLS / "tropo-validate.py")
from lib import distiller  # noqa: E402


def _projection_text(record: dict, *, stale_body: str = "PROJECTION BOILERPLATE") -> str:
    lines = ["---"]
    for key, value in record.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f'  - "{item}"' for item in value)
        else:
            lines.append(f"{key}: {json.dumps(value) if isinstance(value, str) else value}")
    lines.extend(["---", "", stale_body, ""])
    return "\n".join(lines)


class MountedFixture:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="mounted-phase2-")
        self.root = Path(self.temp.name).resolve()
        self.files = self.root / "vault/files"
        self.files.mkdir(parents=True)
        (self.root / ".tropo").mkdir()
        (self.root / ".tropo-studio").mkdir()
        self.mounts: dict[str, dict] = {}
        self.records: list[dict] = []

    def close(self) -> None:
        self.temp.cleanup()

    def add_mount(self, mount_uid: str, path: Path, *, availability: str = "available") -> None:
        self.mounts[mount_uid] = {
            "name": mount_uid,
            "path": str(path),
            "state": "adopted",
            "availability": availability,
        }
        self.write_registry()

    def write_registry(self, schema_version: int = 2) -> None:
        (self.root / ".tropo-studio/folder-mounts.json").write_text(
            json.dumps(
                {"schema_version": schema_version, "mounts": self.mounts},
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def add_record(
        self,
        uid: str,
        mount_uid: str,
        relpath: str,
        *,
        title: str,
        availability: str | None = "available",
        stale_source_path: str = "/definitely/stale/source.md",
        stale_body: str = "PROJECTION BOILERPLATE STALE-CACHE-LEAK",
        record_type: str = "external-artifact",
        projection_authority: str = "derived-only",
    ) -> dict:
        mount_root = Path(self.mounts[mount_uid]["path"])
        relative = Path(relpath)
        sidecar = (
            mount_root
            / relative.parent
            / ".tropo-studio"
            / f"{relative.name}.tropo.md"
        )
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(
            "---\n"
            f"uid: {uid}\n"
            "type: external-artifact\n"
            f"title: {json.dumps(title)}\n"
            f"source_path: ../{relative.name}\n"
            "---\n",
            encoding="utf-8",
        )
        record = {
            "uid": uid,
            "type": record_type,
            "title": title,
            "status": "active",
            "state": "active",
            "projection_authority": projection_authority,
            "mount_uid": mount_uid,
            "mount_relpath": relpath,
            "source_path": stale_source_path,
            "source_sidecar": str(sidecar),
            "created": "2026-08-02",
            "modified": "2026-08-02",
            "schema_version": 2,
            "path": f"vault/files/{uid}.md",
        }
        # availability=None omits the KEY, which is what a pre-migration
        # projection actually looks like. Writing an explicit null would be a
        # different fact and would not exercise the legacy path.
        if availability is not None:
            record["availability"] = availability
        self.records.append(record)
        (self.files / f"{uid}.md").write_text(
            _projection_text(record, stale_body=stale_body),
            encoding="utf-8",
        )
        return record

    def build(self) -> None:
        rebuild.build_sqlite_index(
            self.root,
            self.records,
            True,
            machines=(),
        )

    def seal_git(self, message: str = "fixture") -> None:
        if not (self.root / ".git").exists():
            subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "fixture@test.local"],
                cwd=self.root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "fixture"],
                cwd=self.root,
                check=True,
            )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-qm", message],
            cwd=self.root,
            check=True,
        )

    def full_build(self) -> None:
        self.assert_build_result(
            rebuild.rebuild_index(
                self.root,
                True,
                reconcile=True,
            )
        )

    @staticmethod
    def assert_build_result(code: int) -> None:
        if code != 0:
            raise AssertionError(f"full rebuild failed with code {code}")

    def sqlite_semantics(self) -> dict[str, list[tuple]]:
        with sqlite3.connect(self.root / "vault/00-index.sqlite") as connection:
            return {
                "entries": connection.execute(
                    "SELECT uid, title, fm_json FROM entries ORDER BY uid"
                ).fetchall(),
                "edges": connection.execute(
                    "SELECT src_uid, rel, dst_uid FROM edges "
                    "ORDER BY src_uid, rel, dst_uid"
                ).fetchall(),
                "fts": connection.execute(
                    "SELECT uid, title, body FROM entries_fts ORDER BY uid"
                ).fetchall(),
                "observations": connection.execute(
                    "SELECT src_uid, kind, raw_target, mount_uid, candidate_uids "
                    "FROM index_observations "
                    "ORDER BY src_uid, kind, raw_target"
                ).fetchall(),
            }

    def body(self, uid: str) -> str:
        with sqlite3.connect(self.root / "vault/00-index.sqlite") as connection:
            return connection.execute(
                "SELECT body FROM entries_fts WHERE uid=?", (uid,)
            ).fetchone()[0]

    def content_search(self, query: str) -> list[dict]:
        old_sqlite, old_files = search.SQLITE_PATH, search.FILES_DIR
        search.SQLITE_PATH = self.root / "vault/00-index.sqlite"
        search.FILES_DIR = self.files
        try:
            return search.search_content(query)
        finally:
            search.SQLITE_PATH, search.FILES_DIR = old_sqlite, old_files


class AvailabilityAndSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = MountedFixture()
        self.addCleanup(self.fx.close)
        self.mount = self.fx.root / "outside/notes"
        self.mount.mkdir(parents=True)
        self.uid = "a1000001"
        self.mount_uid = "f1000001"
        self.source = self.mount / "daily.md"
        self.source.write_text(
            "# Daily\n\nsourceonlynebulaterm\n",
            encoding="utf-8",
        )
        self.fx.add_mount(self.mount_uid, self.mount)
        self.record = self.fx.add_record(
            self.uid,
            self.mount_uid,
            "daily.md",
            title="Daily",
        )

    def test_available_offline_restore_search_same_uid_and_exact_stale_leak(self) -> None:
        self.fx.build()
        self.assertEqual(
            self.fx.body(self.uid),
            "# Daily\n\nsourceonlynebulaterm\n",
        )
        self.assertEqual(
            [row["uid"] for row in self.fx.content_search("sourceonlynebulaterm")],
            [self.uid],
        )

        self.record["availability"] = "unavailable"
        self.fx.mounts[self.mount_uid]["availability"] = "unavailable"
        self.fx.write_registry()
        # Plant the exact leak: both a prior FTS body and a projection body still
        # carry searchable terms when the authoritative source goes offline.
        projection = self.fx.files / f"{self.uid}.md"
        projection.write_text(
            _projection_text(
                self.record,
                stale_body=(
                    "PROJECTION BOILERPLATE sourceonlynebulaterm "
                    "STALE-CACHE-LEAK"
                ),
            ),
            encoding="utf-8",
        )
        self.fx.build()

        self.assertEqual(self.fx.body(self.uid), "")
        self.assertEqual(self.fx.content_search("sourceonlynebulaterm"), [])
        self.assertTrue(projection.is_file())
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT uid, title FROM entries WHERE uid=?", (self.uid,)
                ).fetchone(),
                (self.uid, "Daily"),
            )

        self.record["availability"] = "available"
        self.fx.mounts[self.mount_uid]["availability"] = "available"
        self.fx.write_registry()
        self.fx.build()
        self.assertEqual(
            [row["uid"] for row in self.fx.content_search("sourceonlynebulaterm")],
            [self.uid],
        )
        self.assertEqual(self.fx.body(self.uid), self.source.read_text())

    def test_populated_body_refuses_unexpected_empty_but_allows_verified_clear(
        self,
    ) -> None:
        self.fx.seal_git("mounted body transition baseline")
        self.fx.full_build()
        protected = (
            self.fx.root / "vault/00-index.jsonl",
            self.fx.root / "vault/00-archive-index.jsonl",
            self.fx.root / "vault/00-index.sqlite",
            self.fx.root
            / rebuild.index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
            self.fx.root / rebuild.index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
        )
        before = {path: path.read_bytes() for path in protected}
        self.assertTrue(self.fx.body(self.uid))

        self.source.write_bytes(b"\xffinvalid-utf8")
        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            stderr
        ):
            self.assertEqual(rebuild.rebuild_index(self.fx.root, True), 1)
        self.assertIn("MOUNTED-FTS-BODY-LOSS", stderr.getvalue())
        self.assertEqual(
            {path: path.read_bytes() for path in protected},
            before,
        )

        self.source.write_bytes(b"")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            self.assertEqual(rebuild.rebuild_index(self.fx.root, True), 0)
        self.assertEqual(self.fx.body(self.uid), "")

    def test_registry_root_plus_relpath_beats_stale_absolute_path_after_move(self) -> None:
        stale = self.fx.root / "old-location/daily.md"
        stale.parent.mkdir(parents=True)
        stale.write_text("staleabsoluteleak\n", encoding="utf-8")
        self.record["source_path"] = str(stale)
        moved = self.fx.root / "outside/notes-moved"
        shutil.move(str(self.mount), str(moved))
        self.fx.mounts[self.mount_uid]["path"] = str(moved)
        self.fx.write_registry()

        self.fx.build()

        self.assertIn("sourceonlynebulaterm", self.fx.body(self.uid))
        self.assertNotIn("staleabsoluteleak", self.fx.body(self.uid))

    def test_sidecar_relative_source_path_is_authoritative_fallback(self) -> None:
        self.record.pop("mount_relpath")
        sidecars = self.mount / ".tropo-studio"
        sidecars.mkdir(exist_ok=True)
        (sidecars / "daily.md.tropo.md").write_text(
            "---\n"
            f"uid: {self.uid}\n"
            "type: external-artifact\n"
            "source_path: ../daily.md\n"
            "---\n",
            encoding="utf-8",
        )

        self.fx.build()

        self.assertEqual(self.fx.body(self.uid), self.source.read_text())

    def test_missing_and_invalid_utf8_sources_clear_body_and_outgoing_edges(self) -> None:
        target = "a1000002"
        self.record["refs"] = [target]
        missing = self.fx.add_record(
            target,
            self.mount_uid,
            "missing.md",
            title="Missing",
        )
        self.source.write_bytes(b"\xffnot-utf8")
        self.fx.build()
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            for uid in (self.uid, missing["uid"]):
                self.assertEqual(
                    connection.execute(
                        "SELECT body FROM entries_fts WHERE uid=?", (uid,)
                    ).fetchone()[0],
                    "",
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT rel, dst_uid FROM edges WHERE src_uid=?", (uid,)
                    ).fetchall(),
                    [],
                )

    def test_stage_c_reader_stays_on_projection_not_external_fts_source(self) -> None:
        self.fx.build()
        reader = distiller.governed_body_reader(self.fx.files)
        projection_body = reader(self.uid).decode("utf-8")
        self.assertIn("PROJECTION BOILERPLATE", projection_body)
        self.assertNotIn("sourceonlynebulaterm", projection_body)

    def _assert_untrusted_source(self, uid: str, reason: str) -> None:
        self.fx.build()
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT body FROM entries_fts WHERE uid=?", (uid,)
                ).fetchone(),
                ("",),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT rel, dst_uid FROM edges WHERE src_uid=?", (uid,)
                ).fetchall(),
                [],
            )
            self.assertEqual(
                connection.execute(
                    "SELECT kind, raw_target FROM index_observations "
                    "WHERE src_uid=?",
                    (uid,),
                ).fetchall(),
                [("mounted-source-provenance-invalid", reason)],
            )

    def test_spoofed_note_and_authored_projection_cannot_read_mounted_source(self) -> None:
        self.record["refs"] = ["a1000002"]
        self.record["type"] = "note"
        (self.fx.files / f"{self.uid}.md").write_text(
            _projection_text(self.record),
            encoding="utf-8",
        )
        self._assert_untrusted_source(
            self.uid,
            "projection-type-not-external-artifact",
        )

        self.record["type"] = "external-artifact"
        self.record["projection_authority"] = "authored"
        (self.fx.files / f"{self.uid}.md").write_text(
            _projection_text(self.record),
            encoding="utf-8",
        )
        self._assert_untrusted_source(
            self.uid,
            "projection-authority-not-derived-only",
        )

    def test_wrong_sidecar_uid_cannot_read_mounted_source(self) -> None:
        sidecar = Path(self.record["source_sidecar"])
        sidecar.write_text(
            sidecar.read_text(encoding="utf-8").replace(
                f"uid: {self.uid}",
                "uid: deadbeef",
            ),
            encoding="utf-8",
        )
        self._assert_untrusted_source(self.uid, "sidecar-uid-mismatch")

    def test_unadopted_mount_cannot_read_mounted_source(self) -> None:
        self.fx.mounts[self.mount_uid]["state"] = "attached"
        self.fx.write_registry()
        self._assert_untrusted_source(self.uid, "mount-not-adopted")

    def test_over_4mb_symlink_and_symlink_swap_fail_closed(self) -> None:
        self.source.write_bytes(b"x" * (rebuild._MOUNTED_FTS_MAX_BYTES + 1))
        self.fx.build()
        self.assertEqual(self.fx.body(self.uid), "")

        real_source = self.mount / "real.md"
        real_source.write_text("symlink-only-secret\n", encoding="utf-8")
        self.source.unlink()
        self.source.symlink_to(real_source.name)
        self.fx.build()
        self.assertEqual(self.fx.body(self.uid), "")

        self.source.unlink()
        self.source.write_text("descriptor-stable-secret\n", encoding="utf-8")
        backup = self.mount / "swapped-away.md"
        real_read = rebuild.os.read
        swapped = False

        def swap_after_open(fd: int, size: int) -> bytes:
            nonlocal swapped
            if not swapped:
                swapped = True
                os.replace(self.source, backup)
                self.source.symlink_to(backup.name)
            return real_read(fd, size)

        with mock.patch.object(rebuild.os, "read", side_effect=swap_after_open):
            self.fx.build()
        self.assertTrue(swapped)
        self.assertEqual(self.fx.body(self.uid), "")


class RemoteAvailabilityIsNotLocalTruthTests(unittest.TestCase):
    """One machine's blindness must not hide a folder the others can read.

    `.tropo-studio/folder-mounts.json` is git-tracked, so `availability` travels
    to every machine -- but the fact it records ("can I open this path?") is
    per-machine. A `reconcile` on a box that cannot see the folder wrote
    `unavailable`, that commit reached every other machine, and the resolver
    refused a mount whose folder was on local disk, readable.

    Measured on the live studio 2026-08-06 (metis-g103, finding 728f4bf7): mount
    1e6a0b5d points at Mike's iCloud path, so any Linux box marking it
    unavailable took all 54 mounted bodies dark on Mike's Mac.

    Both halves are asserted here, because a fix that only suppressed less would
    be a regression in the other direction: a genuinely absent folder must still
    tombstone.
    """

    def setUp(self) -> None:
        self.fx = MountedFixture()
        self.addCleanup(self.fx.close)
        self.mount = self.fx.root / "outside/shared-notes"
        self.mount.mkdir(parents=True)
        self.uid = "b2000001"
        self.mount_uid = "e2000001"
        self.body = "# Shared\n\nremoteflagcanaryterm\n"
        (self.mount / "shared.md").write_text(self.body, encoding="utf-8")
        self.fx.add_mount(self.mount_uid, self.mount)
        self.record = self.fx.add_record(
            self.uid, self.mount_uid, "shared.md", title="Shared")

    def test_a_remote_unavailable_does_not_hide_a_locally_readable_folder(self) -> None:
        self.fx.build()
        self.assertEqual(self.fx.body(self.uid), self.body, "baseline: it reads")

        # Another machine could not find the folder and said so, in the file we
        # all share. The folder is still right here.
        for flag in ("unavailable", "ambiguous"):
            self.fx.mounts[self.mount_uid]["availability"] = flag
            self.fx.write_registry()
            self.fx.build()
            self.assertEqual(
                self.fx.body(self.uid), self.body,
                f"a remote '{flag}' hid a folder this machine can read -- this is "
                f"the exact defect 728f4bf7 measured on 54 live bodies")
            self.assertEqual(
                [row["uid"] for row in self.fx.content_search("remoteflagcanaryterm")],
                [self.uid],
                f"a remote '{flag}' removed locally readable content from search")

    def test_a_genuinely_absent_folder_refuses_rather_than_silently_emptying(self) -> None:
        """The other half, and the substrate corrected my first draft of it.

        I expected an absent folder to quietly produce an empty body. It does
        not, and the real behaviour is better: `_assert_mounted_fts_body_transitions`
        REFUSES with `MOUNTED-FTS-BODY-LOSS` -- a populated mounted body may not
        become empty without an EXPLICIT tombstone or a verified zero-byte
        source. That is the division of labour the two `availability` fields
        were always meant to have, and which the bug had collapsed:

          * mount-level  -- a cache of "can I reach it", now resolved live per
            machine, never shared authority.
          * record-level -- the DELIBERATE tombstone, set when someone decides
            this content is gone. Still honoured; still the only way a body is
            allowed to disappear.

        So suppressing less at the mount level did not weaken the guarantee. It
        moved the decision to the field that was always supposed to own it.
        """
        self.fx.build()
        self.assertEqual(self.fx.body(self.uid), self.body)

        shutil.rmtree(self.mount)
        self.fx.mounts[self.mount_uid]["availability"] = "available"
        self.fx.write_registry()
        with self.assertRaises(Exception) as caught:
            self.fx.build()
        self.assertIn(
            "MOUNTED-FTS-BODY-LOSS", str(caught.exception),
            "an absent folder must refuse loudly, not silently empty the body")

    def test_the_explicit_record_tombstone_is_still_honoured(self) -> None:
        """And with the tombstone declared, the body goes -- as designed."""
        self.fx.build()
        self.assertEqual(self.fx.body(self.uid), self.body)

        shutil.rmtree(self.mount)
        self.record["availability"] = "unavailable"
        (self.fx.files / f"{self.uid}.md").write_text(
            (self.fx.files / f"{self.uid}.md").read_text(encoding="utf-8")
            .replace("availability: available", "availability: unavailable"),
            encoding="utf-8",
        )
        self.fx.build()
        self.assertNotIn(
            "remoteflagcanaryterm", self.fx.body(self.uid) or "",
            "a declared tombstone must still take the body down")


class MountedBinaryTextComesFromTheCacheNeverTheIndexTests(unittest.TestCase):
    """Searchable text for mounted .docx/.pptx/.xlsx/.pdf (cdadf603 integration).

    The extractor is a separate gesture on purpose. Extraction costs ~340ms a
    document, so pulling it into the rebuild would add ~6 minutes per 1,000
    documents to EVERY rebuild. `sync` fills the cache; the index only reads it.

    Every negative path here must land on `available-nontext`, never
    `unavailable` -- `unavailable` trips the MOUNTED-FTS-BODY-LOSS guard and
    freezes every index write in the studio, which is the P0 (254a360b) this
    crew spent 2026-08-07 on. "I have no text for this" and "the disk is gone"
    are different facts.
    """

    CANARY = "quarterlyextractioncanaryterm"

    def setUp(self) -> None:
        self.fx = MountedFixture()
        self.addCleanup(self.fx.close)
        self.mount = self.fx.root / "outside/office-docs"
        self.mount.mkdir(parents=True)
        self.uid = "b4000001"
        self.mount_uid = "e4000001"
        self.docx = self.mount / "quarterly.docx"
        self.docx.write_bytes(b"PK\x03\x04 not really a zip, never parsed here")
        self.fx.add_mount(self.mount_uid, self.mount)
        self.record = self.fx.add_record(
            self.uid, self.mount_uid, "quarterly.docx", title="Quarterly")
        self.extractor = rebuild._extract_text_module()
        if self.extractor is None:
            self.skipTest("tropo-extract-text.py not loadable in this checkout")

    def _write_cache(self, *, status="ok", text=None, content_sha256=None):
        text = self.CANARY if text is None else text
        if content_sha256 is None:
            content_sha256 = self.extractor.sha256_of(self.docx)
        rec = {
            "uid": self.uid,
            "content_sha256": content_sha256,
            "source_filename": self.docx.name,
            "status": status,
            "chars": len(text),
            "text": text,
        }
        self.extractor.cache_write(self.fx.root, self.uid, rec)
        return rec

    def _status(self):
        catalog = rebuild._MountedSourceCatalog(self.fx.root, self.fx.records)
        return catalog.source(self.record)

    def test_a_current_cache_entry_makes_the_document_searchable(self) -> None:
        self._write_cache()
        self.fx.build()
        self.assertEqual(
            [row["uid"] for row in self.fx.content_search(self.CANARY)],
            [self.uid],
            "a .docx with a CURRENT cache entry must contribute its extracted "
            "text to FTS -- that is the entire point of the integration")
        self.assertEqual(self._status().get("status"), "available-text")

    def test_a_stale_cache_reverts_to_nontext_rather_than_serving_stale_text(
        self,
    ) -> None:
        """The Obsidian Text-Extractor bug, refused by construction.

        That plugin keys on MD5(path) with no staleness check and serves stale
        text forever. Ours keys on uid + content_sha256, so content moving on is
        detectable -- and the only safe answer is to stop answering.
        """
        self._write_cache()
        self.fx.build()
        self.assertTrue(self.fx.content_search(self.CANARY), "baseline: searchable")

        self.docx.write_bytes(b"PK\x03\x04 the document has been edited since")
        self.fx.build()
        self.assertEqual(
            self.fx.content_search(self.CANARY), [],
            "a stale cache served text for content that no longer exists")
        self.assertEqual(
            self._status().get("status"), "available-nontext",
            "a stale cache must degrade to available-nontext; `unavailable` "
            "trips MOUNTED-FTS-BODY-LOSS and freezes every index write (254a360b)")

    def test_no_cache_entry_touches_the_source_file_zero_times(self) -> None:
        """Cache first. An unextracted corpus must cost no source I/O at all."""
        reads = []
        real = self.extractor.sha256_of
        self.extractor.sha256_of = lambda p: (reads.append(p), real(p))[1]
        try:
            self.assertEqual(self._status().get("status"), "available-nontext")
        finally:
            self.extractor.sha256_of = real
        self.assertEqual(
            reads, [],
            "with no cache entry the index hashed the source anyway -- on a "
            "cloud mount that is a download per file per rebuild")

    def test_a_cloud_placeholder_is_never_hashed_and_never_downloaded(self) -> None:
        """90.6% of Mike's SharePoint mount is SF_DATALESS (2,319 of 2,560,
        10.45 GB). Hashing one reads it; reading one downloads it. Asserted on
        the syscall, not on the clock, because a timing assertion here would be
        flaky and would also pass for the wrong reason on a warm cache."""
        self._write_cache()
        reads = []
        real_hash = self.extractor.sha256_of
        self.extractor.sha256_of = lambda p: (reads.append(p), real_hash(p))[1]

        real_lstat = Path.lstat
        target = self.docx.resolve()
        dataless_flag = self.extractor.SF_DATALESS

        def fake_lstat(self_path, *a, **kw):
            st = real_lstat(self_path, *a, **kw)
            if Path(self_path).resolve() == target:
                class _Dataless:
                    st_mode = st.st_mode
                    st_flags = dataless_flag
                return _Dataless()
            return st

        try:
            with mock.patch.object(Path, "lstat", fake_lstat):
                status = self._status().get("status")
        finally:
            self.extractor.sha256_of = real_hash

        self.assertEqual(
            status, "available-nontext",
            "a placeholder has no text yet; it must not become unavailable")
        self.assertEqual(
            reads, [],
            "the index hashed a cloud placeholder -- that is a download, and "
            "the extractor already refuses to do it from the other side")

    def test_an_empty_extraction_is_an_answer_not_a_gap(self) -> None:
        """`empty` means the document genuinely holds no text. It must not be
        retried forever, and it must not read as a lost body."""
        self._write_cache(status="empty", text="")
        source = self._status()
        self.assertEqual(source.get("status"), "available-text")
        self.assertEqual(source.get("text"), "")
        self.assertEqual(
            source.get("raw"), b"",
            "an empty extraction is the verified-zero-byte case downstream, "
            "which is what stops it reading as MOUNTED-FTS-BODY-LOSS")

    def test_a_derived_body_going_dark_is_reported_loudly_with_the_cure(
        self,
    ) -> None:
        """Not optional, and not a softening of the guard.

        metis-g104's ruling: reporting is the difference between the guard
        being satisfied and the guard being right. A body disappearing without
        a word is exactly what g99 built MOUNTED-FTS-BODY-LOSS to prevent, and
        "curable" is not the same as "invisible-worthy".
        """
        self._write_cache()
        self.fx.build()
        self.assertTrue(self.fx.content_search(self.CANARY), 'baseline: searchable')

        self.docx.write_bytes(b'PK\x03\x04 edited, so the cache is now stale')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.fx.build()
        message = err.getvalue()
        self.assertIn('MOUNTED-TEXT', message, 'the drop must be announced')
        self.assertIn(self.uid, message, 'it must name which body went dark')
        self.assertIn(
            'tropo-extract-text.py sync', message,
            'it must name the cure — a report nobody can act on is noise')

    def test_a_READ_body_going_empty_still_refuses_the_guard_stays_hard(
        self,
    ) -> None:
        """The half that must NOT change, asserted beside the half that did.

        The origin property exists to narrow this guard to the case it was
        built for, not to weaken it. A .md whose source becomes unreadable is
        still evidence of loss and must still freeze rather than silently
        empty. If this ever goes green, the read/derived distinction has been
        implemented as a blanket exemption and g99's defect is back.
        """
        md_uid = 'b4000002'
        (self.mount / 'notes.md').write_text(
            '# Notes\n\nreadbodycanaryterm\n', encoding='utf-8')
        self.fx.add_record(md_uid, self.mount_uid, 'notes.md', title='Notes')
        self.fx.build()
        self.assertTrue(
            self.fx.content_search('readbodycanaryterm'), 'baseline: searchable')

        (self.mount / 'notes.md').unlink()
        with self.assertRaises(Exception) as caught:
            self.fx.build()
        self.assertIn(
            'MOUNTED-FTS-BODY-LOSS', str(caught.exception),
            'a READ body going empty must still refuse — the derived carve-out '
            'must not have widened into a blanket exemption')

    def test_the_index_never_extracts_only_ever_reads(self) -> None:
        """The two-gesture rule, asserted on the mechanism.

        If a rebuild could extract, a 1,000-document corpus would add ~6 minutes
        to every rebuild -- and the cost would appear as 'the index got slow',
        far from its cause.
        """
        calls = []
        real_extract = self.extractor.extract
        self.extractor.extract = lambda p: (calls.append(p), real_extract(p))[1]
        try:
            self._status()
            self.fx.build()
        finally:
            self.extractor.extract = real_extract
        self.assertEqual(
            calls, [],
            "the rebuild invoked the extractor; the index READS the cache and "
            "`sync` fills it -- two gestures on purpose")


class LegacyRecordCarveOutMustNotExpireTests(unittest.TestCase):
    """The record-level twin of the class above, and the same bug one level down.

    G99 fixed "absent `availability` means unavailable" for RECORDS on
    2026-08-02, then gated her own fix on `registry_schema_version < 2`. G103
    fixed the MOUNT-level version of it on 2026-08-06 and removed the flag as
    authority outright, because "the lstat() below already answers the
    reachability question locally and correctly."

    The record-level gate survived that pass. On 2026-08-07 G104's `adopt`
    rewrote `folder-mounts.json` at schema_version 2, the carve-out expired for
    every pre-existing mounted record in the same instant, and 42 projections
    whose files were sitting readable on local disk all resolved `unavailable`.
    `MOUNTED-FTS-BODY-LOSS` then correctly refused to blank them and froze every
    index write in the studio (P0, note 254a360b).

    Nobody narrowed the carve-out. A version number moved. That is what makes
    this worth a test rather than a fix: a compatibility bridge with an expiry
    condition will expire, on a day nobody chose, and the failure lands on the
    write path where it stops everyone at once.

    Both directions are asserted, matching the sibling above: an ABSENT field
    must not suppress a readable file, and an EXPLICIT tombstone must still
    suppress. A fix that only suppressed less would be the other regression.
    """

    def setUp(self) -> None:
        self.fx = MountedFixture()
        self.addCleanup(self.fx.close)
        self.mount = self.fx.root / "outside/legacy-notes"
        self.mount.mkdir(parents=True)
        self.uid = "b3000001"
        self.mount_uid = "e3000001"
        self.body = "# Legacy\n\nlegacycarveoutcanaryterm\n"
        (self.mount / "legacy.md").write_text(self.body, encoding="utf-8")
        self.fx.add_mount(self.mount_uid, self.mount)
        # No `availability` KEY at all -- exactly what a pre-migration
        # projection looks like on disk.
        self.record = self.fx.add_record(
            self.uid,
            self.mount_uid,
            "legacy.md",
            title="Legacy",
            availability=None,
        )
        self.assertNotIn(
            "availability", self.record,
            "fixture control: the record must genuinely LACK the field, not "
            "carry an explicit null -- otherwise this suite tests the wrong "
            "branch and passes for the wrong reason")

    def test_absent_availability_survives_a_registry_schema_bump(self) -> None:
        # 999 is not padding. Re-gating on `< 9` leaves 0..7 covered, so the
        # first five cases would all still pass against that mutant and this
        # test would report green on the bug it exists to catch. A version far
        # above any plausible gate is what makes the behavioural half
        # adversarial rather than confirmatory.
        for schema_version in (0, 1, 2, 3, 7, 999):
            with self.subTest(schema_version=schema_version):
                self.fx.write_registry(schema_version=schema_version)
                self.fx.build()
                self.assertEqual(
                    self.fx.body(self.uid), self.body,
                    f"registry schema_version={schema_version} blanked a mounted "
                    f"body whose file is readable on this disk. At 0 and 1 the "
                    f"legacy carve-out covers it; at 2+ it expired and froze "
                    f"every index write in the studio (254a360b)")
                self.assertEqual(
                    [row["uid"] for row in
                     self.fx.content_search("legacycarveoutcanaryterm")],
                    [self.uid],
                    f"schema_version={schema_version} removed a readable "
                    f"mounted file from search")

    def test_an_explicit_tombstone_still_suppresses_at_any_schema_version(
        self,
    ) -> None:
        """The other direction. Absent and 'unavailable' are different facts."""
        self.fx.write_registry(schema_version=2)
        self.fx.build()
        self.assertEqual(self.fx.body(self.uid), self.body, "baseline: it reads")

        # The record `build()` consumes is this dict, so the tombstone is
        # declared here. The file stays readable on purpose: the claim under
        # test is that an EXPLICIT tombstone suppresses on its own authority,
        # not that a missing file does it.
        self.record["availability"] = "unavailable"
        self.fx.build()
        self.assertNotIn(
            "legacycarveoutcanaryterm", self.fx.body(self.uid) or "",
            "a declared tombstone must still take the body down -- suppressing "
            "less across the board would be the opposite regression")

    def test_the_version_gate_itself_is_gone_from_the_resolver(self) -> None:
        """The mutation guard, and the reason this suite is not decoration.

        The behavioural tests above pass on ANY resolver that reads the file,
        so they would also pass if someone re-gated the carve-out on
        `schema_version < 9` and the fixture happened to sit below it. This
        asserts the mechanism directly: the resolver must not condition the
        legacy fall-through on a registry version at all, because that is the
        shape that expires.

        Re-add `and self.registry_schema_version < N` to `legacy_record` and
        this goes red no matter what N is.
        """
        source = Path(rebuild.__file__).read_text(encoding="utf-8")
        self.assertNotIn(
            "registry_schema_version <", source,
            "the legacy carve-out has been re-gated on a registry version. "
            "That is the exact construction that expired on 2026-08-07 and "
            "froze every index write (254a360b). An absent `availability` must "
            "fall through to a real read, which fails closed on its own if the "
            "file is genuinely unreachable -- the read IS the test")


class IncrementalDependencyAndManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = MountedFixture()
        self.addCleanup(self.fx.close)
        self.mount = self.fx.root / "mounted-notes"
        self.mount.mkdir()
        self.mount_uid = "f1800001"
        self.fx.add_mount(self.mount_uid, self.mount)
        self.source_uid = "a1800001"
        self.source_path = self.mount / "source.md"
        self.source_path.write_text("[[Target]]\n", encoding="utf-8")
        self.source = self.fx.add_record(
            self.source_uid,
            self.mount_uid,
            "source.md",
            title="Source",
        )
        self.fx.seal_git("initial mounted source")
        self.fx.full_build()

    def _observations(self) -> list[tuple]:
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            return connection.execute(
                "SELECT kind, raw_target, candidate_uids "
                "FROM index_observations WHERE src_uid=? ORDER BY raw_target",
                (self.source_uid,),
            ).fetchall()

    def _edges(self) -> list[tuple]:
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            return connection.execute(
                "SELECT rel, dst_uid FROM edges WHERE src_uid=? ORDER BY dst_uid",
                (self.source_uid,),
            ).fetchall()

    def _derived_surface_bytes(self) -> dict[Path, bytes]:
        candidates = (
            self.fx.root / "vault/00-index.jsonl",
            self.fx.root / "vault/00-archive-index.jsonl",
            self.fx.root / "vault/00-index.sqlite",
            self.fx.root
            / rebuild.index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
            self.fx.root / rebuild.index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
        )
        return {path: path.read_bytes() for path in candidates if path.is_file()}

    def test_target_add_and_rename_batch_equals_full_rebuild(self) -> None:
        target_uid = "a1800002"
        target_source = self.mount / "target.md"
        target_source.write_text("# Target\n", encoding="utf-8")
        target = self.fx.add_record(
            target_uid,
            self.mount_uid,
            "target.md",
            title="Target",
        )

        self.assertEqual(rebuild.freshen_many((target_uid,), self.fx.root), 0)
        self.assertEqual(self._edges(), [("mentions", target_uid)])
        self.assertEqual(self._observations(), [])
        incremental_add = self.fx.sqlite_semantics()
        self.fx.seal_git("add alias target")
        self.fx.full_build()
        self.assertEqual(self.fx.sqlite_semantics(), incremental_add)

        renamed_source = self.mount / "renamed.md"
        target_source.rename(renamed_source)
        target_sidecar = self.mount / ".tropo-studio/target.md.tropo.md"
        renamed_sidecar = self.mount / ".tropo-studio/renamed.md.tropo.md"
        renamed_sidecar.write_text(
            target_sidecar.read_text(encoding="utf-8").replace(
                "../target.md",
                "../renamed.md",
            ),
            encoding="utf-8",
        )
        target_sidecar.unlink()
        target["title"] = "Renamed"
        target["mount_relpath"] = "renamed.md"
        target["source_sidecar"] = str(renamed_sidecar)
        (self.fx.files / f"{target_uid}.md").write_text(
            _projection_text(target),
            encoding="utf-8",
        )

        self.assertEqual(rebuild.freshen_many((target_uid,), self.fx.root), 0)
        self.assertEqual(self._edges(), [])
        self.assertEqual(
            self._observations(),
            [("wikilink-alias-missing", "Target", "[]")],
        )
        incremental_rename = self.fx.sqlite_semantics()
        self.fx.seal_git("rename alias target")
        self.fx.full_build()
        self.assertEqual(self.fx.sqlite_semantics(), incremental_rename)

    def test_manifest_has_portable_registry_and_exact_source_digest(self) -> None:
        manifest = rebuild.index_surfaces.load_trusted_derivation_manifest(
            self.fx.root
        )
        entries = {(kind, path): digest for kind, path, _mode, digest in manifest}
        self.assertIn(
            ("input", ".tropo-studio/folder-mounts.json"),
            entries,
        )
        self.assertEqual(
            entries[("input", ".tropo-studio/folder-mounts.json")],
            rebuild.hashlib.sha256(
                (
                    self.fx.root
                    / ".tropo-studio/folder-mounts.json"
                ).read_bytes()
            ).hexdigest(),
        )
        virtual_path = f"@mounted-source/{self.mount_uid}/{self.source_uid}"
        self.assertIn(("virtual", virtual_path), entries)
        source = rebuild._MountedSourceCatalog(
            self.fx.root,
            self.fx.records,
        ).source(self.source)
        expected = {
            "content_sha256": source["content_sha256"],
            "relpath": "source.md",
            "size": None,
            "status": "available-text",
            "trust_reason": None,
        }
        expected_digest = rebuild.hashlib.sha256(
            json.dumps(
                expected,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(entries[("virtual", virtual_path)], expected_digest)
        serialized = json.dumps(manifest)
        self.assertNotIn(str(self.mount), serialized)

    def test_concurrent_mounted_source_change_refuses_every_surface(self) -> None:
        before = self._derived_surface_bytes()
        real_signature = rebuild._MountedSourceCatalog.signature
        calls = 0

        def race(catalog):
            nonlocal calls
            result = real_signature(catalog)
            calls += 1
            if calls == 1:
                self.source_path.write_text(
                    "[[Target]] concurrent-change\n",
                    encoding="utf-8",
                )
            return result

        with mock.patch.object(
            rebuild._MountedSourceCatalog,
            "signature",
            autospec=True,
            side_effect=race,
        ):
            self.assertEqual(
                rebuild.freshen_many((self.source_uid,), self.fx.root),
                1,
            )
        self.assertGreaterEqual(calls, 2)
        self.assertEqual(
            {path: path.read_bytes() for path in before},
            before,
        )

    def test_concurrent_mount_registry_change_refuses_every_surface(self) -> None:
        before = self._derived_surface_bytes()
        registry_path = self.fx.root / ".tropo-studio/folder-mounts.json"
        real_signature = rebuild._MountedSourceCatalog.signature
        calls = 0

        def race(catalog):
            nonlocal calls
            result = real_signature(catalog)
            calls += 1
            if calls == 1:
                changed = json.loads(registry_path.read_text(encoding="utf-8"))
                changed["mounts"][self.mount_uid]["availability"] = "unavailable"
                registry_path.write_text(
                    json.dumps(changed, sort_keys=True),
                    encoding="utf-8",
                )
            return result

        with mock.patch.object(
            rebuild._MountedSourceCatalog,
            "signature",
            autospec=True,
            side_effect=race,
        ):
            self.assertEqual(
                rebuild.freshen_many((self.source_uid,), self.fx.root),
                1,
            )
        self.assertGreaterEqual(calls, 1)
        self.assertEqual(
            {path: path.read_bytes() for path in before},
            before,
        )

    def test_incremental_refuses_preexisting_cross_mount_source_drift(self) -> None:
        other_mount = self.fx.root / "other-mount"
        other_mount.mkdir()
        other_mount_uid = "f1800002"
        self.fx.add_mount(other_mount_uid, other_mount)
        other_source_path = other_mount / "other.md"
        other_source_path.write_text("other-before\n", encoding="utf-8")
        other = self.fx.add_record(
            "b1800001",
            other_mount_uid,
            "other.md",
            title="Other",
        )
        self.fx.seal_git("add second mount")
        self.fx.full_build()
        self.fx.seal_git("seal second mount")
        before = self._derived_surface_bytes()
        manifest_before = (
            rebuild.index_surfaces.load_trusted_derivation_manifest(
                self.fx.root
            )
        )
        self.assertEqual(self.fx.body(other["uid"]), "other-before\n")

        other_source_path.write_text("other-after\n", encoding="utf-8")
        self.assertEqual(
            rebuild.freshen_many((self.source_uid,), self.fx.root),
            1,
        )

        self.assertEqual(
            {path: path.read_bytes() for path in before},
            before,
        )
        self.assertEqual(
            rebuild.index_surfaces.load_trusted_derivation_manifest(
                self.fx.root
            ),
            manifest_before,
        )
        self.assertEqual(self.fx.body(other["uid"]), "other-before\n")

    def test_incremental_refuses_cross_mount_registry_companion_drift(self) -> None:
        other_mount = self.fx.root / "registry-other-mount"
        other_mount.mkdir()
        other_mount_uid = "f1800003"
        self.fx.add_mount(other_mount_uid, other_mount)
        other_source_path = other_mount / "other.md"
        other_source_path.write_text("other\n", encoding="utf-8")
        self.fx.add_record(
            "b1800002",
            other_mount_uid,
            "other.md",
            title="Other",
        )
        self.fx.seal_git("add registry second mount")
        self.fx.full_build()
        self.fx.seal_git("seal registry second mount")
        before = self._derived_surface_bytes()
        registry_path = self.fx.root / ".tropo-studio/folder-mounts.json"
        replacement = json.loads(registry_path.read_text(encoding="utf-8"))
        replacement["mounts"][other_mount_uid]["name"] = "changed-elsewhere"
        replacement_raw = json.dumps(
            replacement,
            sort_keys=True,
        ).encode("utf-8")

        self.assertEqual(
            rebuild.freshen_many(
                (self.source_uid,),
                self.fx.root,
                companion_replacements=((registry_path, replacement_raw),),
            ),
            1,
        )

        self.assertEqual(
            {path: path.read_bytes() for path in before},
            before,
        )
        self.assertNotEqual(registry_path.read_bytes(), replacement_raw)


class MountedAliasRemovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = MountedFixture()
        self.addCleanup(self.fx.close)
        self.mount = self.fx.root / "mounted-notes"
        self.mount.mkdir()
        self.mount_uid = "f1900001"
        self.fx.add_mount(self.mount_uid, self.mount)

    def _add(self, uid: str, relpath: str, title: str, body: str) -> dict:
        path = self.mount / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return self.fx.add_record(
            uid,
            self.mount_uid,
            relpath,
            title=title,
        )

    def _seal_semantics(self) -> dict:
        meta_path = (
            self.fx.root
            / rebuild.index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
        )
        ratchet_path = (
            self.fx.root
            / rebuild.index_surfaces.INDEX_RATCHET_RELATIVE_PATH
        )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ratchet = json.loads(ratchet_path.read_text(encoding="utf-8"))
        return {
            "manifest": rebuild.index_surfaces.load_trusted_derivation_manifest(
                self.fx.root
            ),
            "meta_surfaces": meta["surfaces"],
            "source_inventory": meta["source_inventory"],
            "ratchet_surfaces": ratchet["surfaces"],
        }

    def _all_semantics(self) -> dict:
        def rows(name: str) -> list[dict]:
            path = self.fx.root / "vault" / name
            return [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        return {
            "current_jsonl": rows("00-index.jsonl"),
            "archive_jsonl": rows("00-archive-index.jsonl"),
            "sqlite": self.fx.sqlite_semantics(),
            "seals": self._seal_semantics(),
        }

    def _assert_record_surfaces(
        self,
        source: dict,
        removed_uid: str,
        *,
        expected_edges: list[tuple],
        expected_observations: list[tuple],
    ) -> None:
        semantics = self._all_semantics()
        union = (
            semantics["current_jsonl"] + semantics["archive_jsonl"]
        )
        by_uid = {row["uid"]: row for row in union}
        self.assertIn(source["uid"], by_uid)
        self.assertNotIn(removed_uid, by_uid)
        sqlite_rows = semantics["sqlite"]
        sqlite_fm = {
            uid: json.loads(fm_json)
            for uid, _title, fm_json in sqlite_rows["entries"]
        }
        self.assertEqual(sqlite_fm[source["uid"]], by_uid[source["uid"]])
        self.assertNotIn(removed_uid, sqlite_fm)
        self.assertEqual(
            [
                row
                for row in sqlite_rows["edges"]
                if row[0] == source["uid"]
            ],
            expected_edges,
        )
        self.assertEqual(
            [
                row
                for row in sqlite_rows["observations"]
                if row[0] == source["uid"]
            ],
            expected_observations,
        )
        fts = {uid: body for uid, _title, body in sqlite_rows["fts"]}
        self.assertEqual(fts[source["uid"]], (self.mount / "source.md").read_text())
        self.assertNotIn(removed_uid, fts)
        manifest_paths = {
            path
            for _kind, path, _mode, _digest
            in semantics["seals"]["manifest"]
        }
        self.assertIn(
            f"@mounted-source/{self.mount_uid}/{source['uid']}",
            manifest_paths,
        )
        self.assertNotIn(
            f"@mounted-source/{self.mount_uid}/{removed_uid}",
            manifest_paths,
        )

    def _assert_full_rebuild_equivalent(self, incremental: dict) -> None:
        self.fx.seal_git("commit mounted projection removal")
        self.fx.full_build()
        rebuilt = self._all_semantics()
        for key in ("current_jsonl", "archive_jsonl", "sqlite"):
            self.assertEqual(rebuilt[key], incremental[key])
        # The deletion changes from an uncommitted source-absence receipt to
        # the committed baseline before the full rebuild. The portable
        # manifests therefore differ by design, but both seals must validate
        # and certify byte-identical JSONL surfaces and ratchets.
        self.assertTrue(incremental["seals"]["manifest"])
        self.assertTrue(rebuilt["seals"]["manifest"])
        for key in ("meta_surfaces", "ratchet_surfaces"):
            self.assertEqual(
                rebuilt["seals"][key],
                incremental["seals"][key],
            )

    def test_single_removal_rederives_ambiguous_alias_to_unique(self) -> None:
        source = self._add(
            "a1900001",
            "source.md",
            "Source",
            "[[Shared]] exact-removal-fts\n",
        )
        target_one = self._add(
            "a1900002", "one.md", "Shared", "# one\n"
        )
        target_two = self._add(
            "a1900003", "two.md", "Shared", "# two\n"
        )
        self.fx.seal_git("ambiguous removal fixture")
        self.fx.full_build()
        self.fx.seal_git("sealed ambiguous baseline")
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT kind, candidate_uids FROM index_observations "
                    "WHERE src_uid=?",
                    (source["uid"],),
                ).fetchall(),
                [(
                    "wikilink-alias-ambiguous",
                    json.dumps(
                        (target_one["uid"], target_two["uid"]),
                        separators=(",", ":"),
                    ),
                )],
            )

        (self.fx.files / f"{target_two['uid']}.md").unlink()
        self.assertEqual(rebuild.remove_one(target_two["uid"], self.fx.root), 0)
        self._assert_record_surfaces(
            source,
            target_two["uid"],
            expected_edges=[
                (source["uid"], "mentions", target_one["uid"]),
            ],
            expected_observations=[],
        )
        incremental = self._all_semantics()
        self._assert_full_rebuild_equivalent(incremental)

    def test_batch_removal_rederives_unique_alias_to_missing(self) -> None:
        source = self._add(
            "a1910001",
            "source.md",
            "Source",
            "[[Gone]] exact-removal-fts\n",
        )
        target = self._add(
            "a1910002", "gone.md", "Gone", "# gone\n"
        )
        self.fx.seal_git("unique removal fixture")
        self.fx.full_build()
        self.fx.seal_git("sealed unique baseline")
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT src_uid, rel, dst_uid FROM edges WHERE src_uid=?",
                    (source["uid"],),
                ).fetchall(),
                [(source["uid"], "mentions", target["uid"])],
            )

        (self.fx.files / f"{target['uid']}.md").unlink()
        self.assertEqual(
            rebuild.remove_many((target["uid"],), self.fx.root),
            0,
        )
        self._assert_record_surfaces(
            source,
            target["uid"],
            expected_edges=[],
            expected_observations=[(
                source["uid"],
                "wikilink-alias-missing",
                "Gone",
                self.mount_uid,
                "[]",
            )],
        )
        incremental = self._all_semantics()
        self._assert_full_rebuild_equivalent(incremental)

    def test_removal_refuses_cross_mount_source_drift_without_advancing_seal(self) -> None:
        source = self._add(
            "a1920001",
            "source.md",
            "Source",
            "[[Gone]] mount-a-body\n",
        )
        target = self._add(
            "a1920002", "gone.md", "Gone", "# gone\n"
        )
        other_mount = self.fx.root / "other-mounted-notes"
        other_mount.mkdir()
        other_mount_uid = "f1920002"
        self.fx.add_mount(other_mount_uid, other_mount)
        other_source_path = other_mount / "other.md"
        other_source_path.write_text("foreign-body-before\n", encoding="utf-8")
        other = self.fx.add_record(
            "b1920001",
            other_mount_uid,
            "other.md",
            title="Other",
        )
        self.fx.seal_git("cross-mount removal fixture")
        self.fx.full_build()
        self.fx.seal_git("sealed cross-mount baseline")
        protected = (
            self.fx.root / "vault/00-index.jsonl",
            self.fx.root / "vault/00-archive-index.jsonl",
            self.fx.root / "vault/00-index.sqlite",
            self.fx.root
            / rebuild.index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
            self.fx.root
            / rebuild.index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
        )
        before = {path: path.read_bytes() for path in protected}
        manifest_before = (
            rebuild.index_surfaces.load_trusted_derivation_manifest(
                self.fx.root
            )
        )
        self.assertEqual(self.fx.body(other["uid"]), "foreign-body-before\n")

        other_source_path.write_text("foreign-body-after\n", encoding="utf-8")
        (self.fx.files / f"{target['uid']}.md").unlink()
        self.assertEqual(
            rebuild.remove_many((target["uid"],), self.fx.root),
            1,
        )

        self.assertEqual(
            {path: path.read_bytes() for path in protected},
            before,
        )
        self.assertEqual(
            rebuild.index_surfaces.load_trusted_derivation_manifest(
                self.fx.root
            ),
            manifest_before,
        )
        self.assertEqual(self.fx.body(other["uid"]), "foreign-body-before\n")
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT src_uid, rel, dst_uid FROM edges WHERE src_uid=?",
                    (source["uid"],),
                ).fetchall(),
                [(source["uid"], "mentions", target["uid"])],
            )


class MountScopedWikilinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = MountedFixture()
        self.addCleanup(self.fx.close)
        self.a = self.fx.root / "mount-a"
        self.b = self.fx.root / "mount-b"
        self.a.mkdir()
        self.b.mkdir()
        self.fx.add_mount("f2000001", self.a)
        self.fx.add_mount("f2000002", self.b)

    def _source(self, root: Path, relpath: str, text: str) -> None:
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_unique_path_and_title_edges_ambiguous_and_cross_mount_do_not(self) -> None:
        self._source(
            self.a,
            "source.md",
            "[[people/alice#Role|Alice label]] [[dup]] "
            "[[foreign-only]] [[Unique Person|label]] "
            "[[a2000002]] [[b2000001]] [[Shared]]\n",
        )
        self._source(self.a, "people/alice.md", "# Alice\n")
        self._source(self.a, "one/dup.md", "# One\n")
        self._source(self.a, "two/dup.md", "# Two\n")
        self._source(self.a, "unique.md", "# Unique\n")
        self._source(self.a, "title-one.md", "# Shared one\n")
        self._source(self.a, "title-two.md", "# Shared two\n")
        self._source(self.b, "people/alice.md", "# Foreign Alice\n")
        self._source(self.b, "foreign-only.md", "# Foreign only\n")
        source = self.fx.add_record(
            "a2000001", "f2000001", "source.md", title="Source"
        )
        alice = self.fx.add_record(
            "a2000002",
            "f2000001",
            "people/alice.md",
            title="Alice",
            availability="unavailable",
        )
        duplicate_one = self.fx.add_record(
            "a2000003", "f2000001", "one/dup.md", title="Duplicate one"
        )
        duplicate_two = self.fx.add_record(
            "a2000004", "f2000001", "two/dup.md", title="Duplicate two"
        )
        unique = self.fx.add_record(
            "a2000005", "f2000001", "unique.md", title="Unique Person"
        )
        shared_one = self.fx.add_record(
            "a2000006", "f2000001", "title-one.md", title="Shared"
        )
        shared_two = self.fx.add_record(
            "a2000007", "f2000001", "title-two.md", title="Shared"
        )
        foreign_alice = self.fx.add_record(
            "b2000001", "f2000002", "people/alice.md", title="Alice"
        )
        foreign_only = self.fx.add_record(
            "b2000002", "f2000002", "foreign-only.md", title="Foreign only"
        )

        self.fx.build()

        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            edges = connection.execute(
                "SELECT rel, dst_uid FROM edges WHERE src_uid=? ORDER BY dst_uid",
                (source["uid"],),
            ).fetchall()
            observations = connection.execute(
                "SELECT kind, raw_target, candidate_uids "
                "FROM index_observations WHERE src_uid=? ORDER BY raw_target",
                (source["uid"],),
            ).fetchall()
        self.assertEqual(
            edges,
            [("mentions", alice["uid"]), ("mentions", unique["uid"])],
        )
        self.assertNotIn(("mentions", foreign_alice["uid"]), edges)
        self.assertNotIn(("mentions", foreign_only["uid"]), edges)
        self.assertEqual(
            {
                raw_target: (kind, candidate_uids)
                for kind, raw_target, candidate_uids in observations
            },
            {
                "Shared": (
                    "wikilink-alias-ambiguous",
                    json.dumps(
                        (shared_one["uid"], shared_two["uid"]),
                        separators=(",", ":"),
                    ),
                ),
                "b2000001": ("wikilink-alias-missing", "[]"),
                "dup": (
                    "wikilink-alias-ambiguous",
                    json.dumps(
                        (duplicate_one["uid"], duplicate_two["uid"]),
                        separators=(",", ":"),
                    ),
                ),
                "foreign-only": ("wikilink-alias-missing", "[]"),
            },
        )

    def test_ordinary_governed_wikilink_uid_parser_is_unchanged(self) -> None:
        self.assertEqual(
            rebuild._get_mentions(
                "[[a2000002]]",
                "a2000001",
                set(),
                {"a2000001", "a2000002"},
            ),
            ["a2000002"],
        )

    def test_invalid_provenance_is_neither_alias_source_nor_target(self) -> None:
        self._source(
            self.a,
            "source.md",
            "[[Collision]] [[BadOnly]] [[Invalid Source]]\n",
        )
        self._source(self.a, "valid.md", "# valid\n")
        self._source(self.a, "invalid-collision.md", "# invalid collision\n")
        self._source(self.a, "invalid-only.md", "# invalid only\n")
        self._source(self.a, "invalid-source.md", "[[Collision]]\n")
        source = self.fx.add_record(
            "a2100001", "f2000001", "source.md", title="Source"
        )
        valid = self.fx.add_record(
            "a2100002", "f2000001", "valid.md", title="Collision"
        )
        invalid_collision = self.fx.add_record(
            "a2100003",
            "f2000001",
            "invalid-collision.md",
            title="Collision",
        )
        invalid_only = self.fx.add_record(
            "a2100004",
            "f2000001",
            "invalid-only.md",
            title="BadOnly",
            projection_authority="authored",
        )
        invalid_source = self.fx.add_record(
            "a2100005",
            "f2000001",
            "invalid-source.md",
            title="Invalid Source",
        )
        for record, replacement_uid in (
            (invalid_collision, "deadbeef"),
            (invalid_source, "feedface"),
        ):
            sidecar = Path(record["source_sidecar"])
            sidecar.write_text(
                sidecar.read_text(encoding="utf-8").replace(
                    f"uid: {record['uid']}",
                    f"uid: {replacement_uid}",
                ),
                encoding="utf-8",
            )

        self.fx.build()

        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT rel, dst_uid FROM edges WHERE src_uid=?",
                    (source["uid"],),
                ).fetchall(),
                [("mentions", valid["uid"])],
            )
            self.assertEqual(
                connection.execute(
                    "SELECT kind, raw_target, candidate_uids "
                    "FROM index_observations WHERE src_uid=? ORDER BY raw_target",
                    (source["uid"],),
                ).fetchall(),
                [
                    ("wikilink-alias-missing", "BadOnly", "[]"),
                    ("wikilink-alias-missing", "Invalid Source", "[]"),
                ],
            )
            for record, reason in (
                (invalid_collision, "sidecar-uid-mismatch"),
                (
                    invalid_only,
                    "projection-authority-not-derived-only",
                ),
                (invalid_source, "sidecar-uid-mismatch"),
            ):
                self.assertEqual(
                    connection.execute(
                        "SELECT kind, raw_target FROM index_observations "
                        "WHERE src_uid=?",
                        (record["uid"],),
                    ).fetchall(),
                    [("mounted-source-provenance-invalid", reason)],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT rel, dst_uid FROM edges WHERE src_uid=?",
                        (record["uid"],),
                    ).fetchall(),
                    [],
                )

    def test_unavailable_source_removes_body_edges_and_observations(self) -> None:
        self._source(self.a, "source.md", "[[target]] [[missing]]\n")
        self._source(self.a, "target.md", "# Target\n")
        source = self.fx.add_record(
            "a2000010", "f2000001", "source.md", title="Source"
        )
        target = self.fx.add_record(
            "a2000011", "f2000001", "target.md", title="Target"
        )
        self.fx.build()
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT rel, dst_uid FROM edges WHERE src_uid=?",
                    (source["uid"],),
                ).fetchall(),
                [("mentions", target["uid"])],
            )
            self.assertEqual(
                connection.execute(
                    "SELECT kind FROM index_observations WHERE src_uid=?",
                    (source["uid"],),
                ).fetchall(),
                [("wikilink-alias-missing",)],
            )

        source["availability"] = "ambiguous"
        self.fx.mounts["f2000001"]["availability"] = "ambiguous"
        self.fx.write_registry()
        self.fx.build()
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT body FROM entries_fts WHERE uid=?", (source["uid"],)
                ).fetchone()[0],
                "",
            )
            self.assertEqual(
                connection.execute(
                    "SELECT * FROM edges WHERE src_uid=?", (source["uid"],)
                ).fetchall(),
                [],
            )
            self.assertEqual(
                connection.execute(
                    "SELECT * FROM index_observations WHERE src_uid=?",
                    (source["uid"],),
                ).fetchall(),
                [],
            )

        source["availability"] = "available"
        self.fx.mounts["f2000001"]["availability"] = "available"
        self.fx.write_registry()
        self.fx.build()
        with sqlite3.connect(self.fx.root / "vault/00-index.sqlite") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT rel, dst_uid FROM edges WHERE src_uid=?",
                    (source["uid"],),
                ).fetchall(),
                [("mentions", target["uid"])],
            )
            self.assertEqual(
                connection.execute(
                    "SELECT kind FROM index_observations WHERE src_uid=?",
                    (source["uid"],),
                ).fetchall(),
                [("wikilink-alias-missing",)],
            )


class TemplateExemptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="mounted-template-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = self.root / "vault/files"
        capsules = self.root / "vault/capsules"
        self.files.mkdir(parents=True)
        capsules.mkdir()
        (self.root / ".tropo").mkdir()
        (self.root / ".tropo-studio").mkdir()
        self.mount = self.root / "mounted"
        self.mount.mkdir()
        self.mount_uid = "f3000001"
        self.registry_path = self.root / ".tropo-studio/folder-mounts.json"
        self._write_registry(
            state="adopted",
            availability="available",
            projection_uids=["c3000001", "c3000006"],
        )
        (capsules / "tropo-note.capsule.md").write_text(
            "---\nversion: '1.0'\ntemplate_enforced_from: '2026-08-01'\n---\n"
            "## §Template\n~~~markdown\n---\nuid: <<MINT:uid>>\n"
            "type: note\n---\n## Required Shape\n~~~\n",
            encoding="utf-8",
        )
        (capsules / "tropo-external-artifact.capsule.md").write_text(
            "---\nversion: '1.0'\ntemplate_enforced_from: '2026-08-01'\n---\n"
            "## §Template\n~~~markdown\n---\nuid: <<MINT:uid>>\n"
            "type: external-artifact\n---\n## Required Shape\n~~~\n",
            encoding="utf-8",
        )
        (capsules / "tropo-capsule-definition.capsule.md").write_text(
            "---\nversion: '1.0'\ninstance_verifier_severity:\n"
            "  sections-present: WARN\n"
            "  placeholder-survival: FAIL\n"
            "  stray-mint-token: ERROR\n"
            "  body-unreadable: FAIL\n---\n",
            encoding="utf-8",
        )

    def _write_registry(
        self,
        *,
        state: str,
        availability: str,
        projection_uids: list[str],
    ) -> None:
        self.registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "mounts": {
                        self.mount_uid: {
                            "path": str(self.mount),
                            "state": state,
                            "availability": availability,
                            "projection_uids": projection_uids,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def _entry(self, uid: str, entry_type: str) -> None:
        (self.files / f"{uid}.md").write_text(
            "---\n"
            f"uid: {uid}\ntype: {entry_type}\ntitle: {uid}\n"
            "status: active\ncreated: '2026-08-02'\n---\n\n# No shape\n",
            encoding="utf-8",
        )

    def _projection(
        self,
        uid: str,
        *,
        availability: str = "available",
        sidecar_uid: str | None = None,
    ) -> dict:
        record = {
            "uid": uid,
            "type": "external-artifact",
            "title": uid,
            "status": "active",
            "availability": availability,
            "projection_authority": "derived-only",
            "mount_uid": self.mount_uid,
            "path": f"vault/files/{uid}.md",
        }
        if availability == "available":
            source = self.mount / f"{uid}.md"
            source.write_text("# source\n", encoding="utf-8")
            sidecar = self.mount / ".tropo-studio" / f"{uid}.md.tropo.md"
            sidecar.parent.mkdir(exist_ok=True)
            sidecar.write_text(
                "---\n"
                f"uid: {sidecar_uid or uid}\n"
                "type: external-artifact\n"
                f"source_path: ../{uid}.md\n"
                "---\n",
                encoding="utf-8",
            )
            record.update({
                "mount_relpath": f"{uid}.md",
                "source_sidecar": str(sidecar),
                "source_path": str(source),
            })
        (self.files / f"{uid}.md").write_text(
            _projection_text(record),
            encoding="utf-8",
        )
        return record

    def test_duplicate_same_uid_sidecar_denies_same_trust_in_index_and_template(self) -> None:
        projection = self._projection("c3000001")
        duplicate_source = self.mount / "duplicate" / "other.md"
        duplicate_source.parent.mkdir()
        duplicate_source.write_text("# duplicate\n", encoding="utf-8")
        duplicate_sidecar = (
            duplicate_source.parent
            / ".tropo-studio"
            / "other.md.tropo.md"
        )
        duplicate_sidecar.parent.mkdir()
        duplicate_sidecar.write_text(
            "---\n"
            f"uid: {projection['uid']}\n"
            "type: external-artifact\n"
            "source_path: ../other.md\n"
            "---\n",
            encoding="utf-8",
        )
        mounts = validate._folder_mount_registry(self.root)
        validator_decision = (
            validate._template_body_shape_exemption_decision(
                projection,
                vault=self.root,
                mounts=mounts,
            )
        )
        catalog = rebuild._MountedSourceCatalog(
            self.root,
            [projection],
        )
        index_source = catalog.source(projection)
        self.assertEqual(
            validator_decision,
            (False, "sidecar-binding-ambiguous"),
        )
        self.assertEqual(index_source["status"], "untrusted")
        self.assertEqual(
            index_source["trust_reason"],
            validator_decision[1],
        )

        (self.root / "vault/00-index.jsonl").write_text(
            json.dumps(projection) + "\n",
            encoding="utf-8",
        )
        (self.root / "vault/00-archive-index.jsonl").write_text(
            "",
            encoding="utf-8",
        )
        findings, checked, _defects = (
            validate.check_live_template_body_shape(self.root)
        )
        self.assertEqual(checked, 1)
        self.assertTrue(
            any(
                "MOUNTED-PROJECTION-PROVENANCE-INVALID" in finding
                and "sidecar-binding-ambiguous" in finding
                for finding in findings
            ),
            findings,
        )

    def test_template_body_shape_preserves_python_and_json_exclusion(self) -> None:
        tools = self.root / "vault/tools"
        tools.mkdir()
        rows = []
        for uid, suffix in (("c3100001", ".py"), ("c3100002", ".json")):
            (tools / f"{uid}{suffix}").write_text(
                "{}\n" if suffix == ".json" else "# tool\n",
                encoding="utf-8",
            )
            rows.append({
                "uid": uid,
                "type": "external-artifact",
                "mount_uid": self.mount_uid,
                "projection_authority": "derived-only",
                "availability": "available",
                "path": f"vault/tools/{uid}{suffix}",
            })
        (self.root / "vault/00-index.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        (self.root / "vault/00-archive-index.jsonl").write_text(
            "",
            encoding="utf-8",
        )

        findings, checked, defects = (
            validate.check_live_template_body_shape(self.root)
        )

        self.assertEqual((checked, defects), (0, 0))
        self.assertFalse(
            any(
                row["uid"] in finding
                for row in rows
                for finding in findings
            ),
            findings,
        )

    def test_only_template_body_shape_is_exempt_structural_union_still_runs(self) -> None:
        valid_projection = self._projection("c3000001")
        mounts = validate._folder_mount_registry(self.root)
        self.assertTrue(
            validate._template_body_shape_exempt(
                valid_projection,
                vault=self.root,
                mounts=mounts,
            )
        )
        self.assertFalse(
            validate._template_body_shape_exempt(
                {
                    "uid": "c3000000",
                    "type": "note",
                    "mount_uid": "f3000001",
                    "projection_authority": "derived-only",
                    "path": "vault/files/c3000000.md",
                },
                vault=self.root,
                mounts=mounts,
            )
        )
        for override in (
            {"mount_uid": "f3999999"},
            {"projection_authority": "authored"},
            {"path": "vault/files/not-the-uid.md"},
        ):
            with self.subTest(override=override):
                self.assertFalse(
                    validate._template_body_shape_exempt(
                        {**valid_projection, **override},
                        vault=self.root,
                        mounts=mounts,
                    )
                )
        attached_mounts = json.loads(json.dumps(mounts))
        attached_mounts[self.mount_uid]["state"] = "attached"
        self.assertFalse(
            validate._template_body_shape_exempt(
                valid_projection,
                vault=self.root,
                mounts=attached_mounts,
            )
        )
        invalid_sidecar = self._projection(
            "c3000006",
            sidecar_uid="deadbeef",
        )
        self.assertFalse(
            validate._template_body_shape_exempt(
                invalid_sidecar,
                vault=self.root,
                mounts=mounts,
            )
        )
        unavailable = self._projection(
            "c3000007",
            availability="unavailable",
        )
        unavailable_mounts = json.loads(json.dumps(mounts))
        unavailable_mounts[self.mount_uid]["availability"] = "unavailable"
        unavailable_mounts[self.mount_uid]["projection_uids"].append(
            unavailable["uid"]
        )
        unavailable_mounts[self.mount_uid]["projection_hashes"] = {
            unavailable["uid"]: rebuild.hashlib.sha256(
                (self.files / f"{unavailable['uid']}.md").read_bytes()
            ).hexdigest(),
        }
        self.assertTrue(
            validate._template_body_shape_exempt(
                unavailable,
                vault=self.root,
                mounts=unavailable_mounts,
            )
        )
        spoofed_unavailable = self._projection(
            "c3000008",
            availability="unavailable",
        )
        self.assertFalse(
            validate._template_body_shape_exempt(
                spoofed_unavailable,
                vault=self.root,
                mounts=unavailable_mounts,
            )
        )
        mounted_uid, spoofed_note_uid, authored_uid, ordinary_uid = (
            "c3000001",
            "c3000002",
            "c3000003",
            "c3000005",
        )
        for uid, entry_type in (
            (spoofed_note_uid, "note"),
            (authored_uid, "external-artifact"),
            (ordinary_uid, "note"),
        ):
            self._entry(uid, entry_type)
        rows = [
            valid_projection,
            {
                "uid": spoofed_note_uid,
                "type": "note",
                "mount_uid": "f3000001",
                "projection_authority": "derived-only",
                "path": f"vault/files/{spoofed_note_uid}.md",
            },
            {
                "uid": authored_uid,
                "type": "external-artifact",
                "mount_uid": "f3000001",
                "projection_authority": "authored",
                "path": f"vault/files/{authored_uid}.md",
            },
            {
                "uid": ordinary_uid,
                "type": "note",
                "path": f"vault/files/{ordinary_uid}.md",
            },
        ]
        current = self.root / "vault/00-index.jsonl"
        archive = self.root / "vault/00-archive-index.jsonl"
        archived_uid = "c3000004"
        self._entry(archived_uid, "note")
        current.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        archive.write_text(
            json.dumps({
                "uid": archived_uid,
                "type": "note",
                "state": "archived",
                "path": f"vault/files/{archived_uid}.md",
            }) + "\n",
            encoding="utf-8",
        )

        findings, checked, defects = validate.check_live_template_body_shape(
            self.root
        )
        self.assertEqual(checked, 3)
        self.assertEqual(defects, 0)
        self.assertFalse(any(mounted_uid in finding for finding in findings))

        union_findings, union_checked, union_defects = (
            validate.check_index_union_integrity(self.root)
        )
        self.assertEqual((union_checked, union_defects), (5, 0), union_findings)
        archive.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
        union_findings, _, union_defects = validate.check_index_union_integrity(
            self.root
        )
        self.assertGreater(union_defects, 0)
        self.assertTrue(any("UID uniqueness" in item for item in union_findings))


if __name__ == "__main__":
    unittest.main()
