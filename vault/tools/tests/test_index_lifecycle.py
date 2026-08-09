#!/usr/bin/env python3
"""Fixture-vault proofs for locked index-lifecycle dev-spec 8c21f26a."""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock


TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib import index_surfaces  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rebuild = _load_module(
    "tropo_rebuild_index_lifecycle",
    TOOLS_DIR / "tropo-rebuild-index.py",
)
validate = _load_module(
    "tropo_validate_index_lifecycle",
    TOOLS_DIR / "tropo-validate.py",
)

SUNSET = index_surfaces.LEGACY_DIGEST_DOOR_SUNSET
ONE_DAY = datetime.timedelta(days=1)
LAST_OPEN_DAY = SUNSET - ONE_DAY
FIRST_CLOSED_DAY = SUNSET
INDEX_SURFACES_TOOL = TOOLS_DIR / "lib" / "index_surfaces.py"


def _on_day(day: datetime.date):
    """Run the block as if today were ``day``.

    The sunset tests patch the clock rather than the constant, so what they
    exercise is the real pinned date being compared against a moving today —
    which is the thing that will actually happen. Patching the constant instead
    would leave the shipped date untested.
    """
    return mock.patch.object(index_surfaces, "_utc_today", lambda: day)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr}"
        )
    return result.stdout.strip()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _initialize_trusted_pair(
    current_path: Path,
    archive_path: Path,
    current_rows: list[dict],
    archive_rows: list[dict],
) -> None:
    """Initialize direct-library fixtures through the explicit recovery gate."""
    inventory = tuple(
        (
            f"vault/files/{index + 1:08x}.md",
            "100644",
            f"{index + 1:040x}",
        )
        for index, _row in enumerate(current_rows + archive_rows)
    )
    proof = index_surfaces.prove_full_source_derivation(
        current_rows,
        archive_rows,
        source_complete=True,
        source_inventory=inventory,
    )
    index_surfaces.write_jsonl_pair_atomic(
        (
            (current_path, current_rows),
            (archive_path, archive_rows),
        ),
        full_source_derivation_proof=proof,
        surface_metadata_recovery_reason="test-source-complete-reconcile",
    )


def _install_schema2_sidecar(fixture: "FixtureStudio") -> dict:
    """Replace generated floor copies with the exact pre-schema3 shape."""
    meta_path = (
        fixture.root / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
    )
    ratchet_path = (
        fixture.root / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
    )
    surfaces = {}
    for path in (fixture.current_surface, fixture.archive_surface):
        raw = path.read_bytes()
        surfaces[path.name] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "record_count": len(
                index_surfaces.read_jsonl_strict(path)
            ),
        }
    schema2 = {
        "schema_version": 2,
        "surfaces": surfaces,
    }
    schema2["pair_sha256"] = index_surfaces._surface_meta_digest(schema2)
    meta_path.write_text(
        json.dumps(schema2, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    ratchet_path.unlink()
    sqlite_path = fixture.root / "vault" / "00-index.sqlite"
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("DROP TABLE index_ratchet_metadata")
    return schema2


def _entry_text(
    uid: str,
    *,
    state: str,
    status: str,
    title: str | None = None,
    entry_type: str = "note",
    body: str | None = None,
) -> str:
    title = title or f"fixture {uid}"
    body = body if body is not None else f"# {title}\n"
    return (
        "---\n"
        f'uid: "{uid}"\n'
        f"type: {entry_type}\n"
        f'title: "{title}"\n'
        f"state: {state}\n"
        f"status: {status}\n"
        "created: '2026-07-26'\n"
        "modified: '2026-07-26'\n"
        "schema_version: 2\n"
        "extraction_scope: argo-private\n"
        "---\n\n"
        f"{body}"
    )


class FixtureStudio:
    def __init__(
        self,
        root: Path,
        *,
        current_count: int = 2,
        archive_count: int = 3,
    ) -> None:
        # .resolve() because on macOS tempfile hands back /var/folders/...,
        # which is a symlink to /private/var/folders/.... The rebuild resolves
        # its own root internally and then checks every transaction destination
        # against an allowlist, so an unresolved fixture root failed with
        # "REFUSAL: unauthorized index transaction companion destination(s)"
        # before a single assertion ran -- 67 failures + 3 errors out of 75, on
        # every Mac, green on Linux CI. The 70 call sites all pass Path(tmp)
        # unresolved, so this is fixed once here rather than 70 times there.
        #
        # Third instance of this exact defect today (metis-g103 2026-08-06);
        # test_typed_mint_phase1.py and test_test_spec_mint_v13.py were the
        # other two. The tool was never wrong in any of them -- the fixtures
        # described a machine nobody runs on.
        root = Path(root).resolve()
        self.root = root
        self.files = root / "vault" / "files"
        self.files.mkdir(parents=True)
        (root / ".tropo").mkdir()
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "fixture@test.local")
        _git(root, "config", "user.name", "fixture")
        (root / ".gitignore").write_text(
            ".tropo-studio/\n"
            "vault/00-index.jsonl\n"
            "vault/00-archive-index.jsonl\n"
            "vault/00-project-tree.jsonl\n"
            "vault/00-index.sqlite\n",
            encoding="utf-8",
        )

        self.current_uids = [
            f"{index + 1:08x}" for index in range(current_count)
        ]
        self.archive_uids = [
            f"{0x10000000 + index:08x}" for index in range(archive_count)
        ]
        for uid in self.current_uids:
            (self.files / f"{uid}.md").write_text(
                _entry_text(uid, state="active", status="active"),
                encoding="utf-8",
            )
        for uid in self.archive_uids:
            (self.files / f"{uid}.md").write_text(
                _entry_text(uid, state="archived", status="done"),
                encoding="utf-8",
            )
        self.commit_sources("fixture sources")

    @property
    def current_surface(self) -> Path:
        return self.root / "vault" / index_surfaces.CURRENT_INDEX_NAME

    @property
    def archive_surface(self) -> Path:
        return self.root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME

    @property
    def cache_jsonl(self) -> Path:
        return self.root / rebuild.ARCHIVE_CACHE_JSONL_REL

    @property
    def cache_meta(self) -> Path:
        return self.root / rebuild.ARCHIVE_CACHE_META_REL

    @property
    def run_artifact(self) -> Path:
        return self.root / rebuild.INDEX_RUN_ARTIFACT_REL

    def commit_sources(self, message: str) -> str:
        _git(self.root, "add", "vault/files", ".gitignore")
        _git(self.root, "commit", "-q", "-m", message)
        return _git(self.root, "rev-parse", "HEAD")

    def prime(self) -> None:
        rc = rebuild.rebuild_index(
            self.root,
            True,
            reconcile=True,
        )
        if rc != 0:
            raise AssertionError(f"fixture prime failed with {rc}")


class BatchInheritsTheManifestTests(unittest.TestCase):
    """The BATCH path is the one agents actually take, and it was untested.

    Added 2026-08-06 (metis-g103). I removed the whole-vault proof from
    `_freshen_one_locked`, measured 26.1s -> 1.39s, and then measured the REAL
    gesture: `tropo-mint-id.py --type note` still took 7.16s, because the mint
    routes through `freshen_many`. I had optimised the path nobody takes.

    Worse, when I fixed the batch path and mutation-tested it, reverting it to
    the whole-vault proof left the entire suite GREEN. Nothing pinned the
    behaviour, so a future revert would be silent. This pins it.
    """

    def test_a_batch_write_is_not_refused_by_an_unrelated_dirty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=2)
            fixture.prime()

            target_uid = fixture.current_uids[0]
            target = fixture.files / f"{target_uid}.md"
            target.write_text(
                target.read_text(encoding="utf-8").replace(
                    f"fixture {target_uid}", "batch owned target"
                ),
                encoding="utf-8",
            )
            # Somebody else's file, dirty, and none of this batch's business.
            # This is the shape that refused a live write when Orpheus booted.
            unrelated = fixture.files / f"{fixture.archive_uids[0]}.md"
            unrelated.write_bytes(
                unrelated.read_bytes().replace(b"# fixture", b"# unrelated dirty")
            )

            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                result = rebuild.freshen_many({target_uid}, fixture.root)
            self.assertEqual(
                result,
                0,
                "an unrelated dirty file refused a batch write -- the batch "
                "path is what the mint uses, so this is the one that reaches "
                "an agent doing ordinary work",
            )


class ValidatedManifestMemoTests(unittest.TestCase):
    """The manifest memo must never turn an invalid manifest into a valid one.

    Added 2026-08-06 (metis-g103) because the memo shipped WITHOUT this and
    mutation proved it: moving the cache write ahead of validation, and
    returning the input unsorted, both left the full 75-test suite GREEN. A
    cache on a validation function is exactly where a silent yes is dangerous,
    and nothing was checking it.
    """

    VALID = (
        ("source", "vault/files/aaaaaaaa.md", "100644", "a" * 64),
        ("input", "vault/tools/lib/gardener.py", "100644", "b" * 64),
    )

    def setUp(self) -> None:
        index_surfaces._VALIDATED_MANIFEST_MEMO.clear()
        self.addCleanup(index_surfaces._VALIDATED_MANIFEST_MEMO.clear)

    def test_an_invalid_manifest_raises_every_time_it_is_presented(self) -> None:
        """Caching a failure would let the second attempt through."""
        bad = (("source", "vault/files/aaaaaaaa.md", "100644", "not-a-sha"),)
        for attempt in (1, 2, 3):
            with self.assertRaises(
                index_surfaces.IndexSurfaceRefusal,
                msg=f"attempt {attempt} was accepted; a failure was cached",
            ):
                index_surfaces._validated_derivation_manifest(iter(bad))

    def test_a_valid_manifest_is_returned_sorted_on_the_cached_path_too(self) -> None:
        """The caller compares the result positionally, so order is contract."""
        unsorted = tuple(reversed(self.VALID))
        first = index_surfaces._validated_derivation_manifest(iter(unsorted))
        second = index_surfaces._validated_derivation_manifest(iter(unsorted))
        self.assertEqual(first, tuple(sorted(self.VALID)))
        self.assertEqual(second, first, "the cached path returned a different shape")

    def test_the_memo_survives_a_generator_argument(self) -> None:
        """Callers pass GENERATORS. Building a cache key by consuming one and
        then validating the corpse is the bug that cost me two attempts."""
        gen = (entry for entry in self.VALID)
        result = index_surfaces._validated_derivation_manifest(gen)
        self.assertEqual(len(result), len(self.VALID))
        self.assertEqual(result, tuple(sorted(self.VALID)))


class IndexLifecycleTests(unittest.TestCase):
    def test_transaction_destination_allowlist_rejects_unrelated_traversal_and_symlink(
        self,
    ) -> None:
        for attack in (
            "unrelated",
            "traversal",
            "symlink",
            "journal",
            "source-traversal",
            "source-symlink",
        ):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as tmp:
                fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=0)
                fixture.prime()
                current = index_surfaces.read_jsonl_strict(fixture.current_surface)
                archive = index_surfaces.read_jsonl_strict(fixture.archive_surface)
                unrelated = fixture.root / "unrelated.txt"
                unrelated.write_bytes(b"human-owned bytes\n")
                if attack == "unrelated":
                    destination = unrelated
                elif attack == "traversal":
                    destination = (
                        fixture.root / ".tropo-studio" / ".." / "unrelated.txt"
                    )
                elif attack == "journal":
                    destination = (
                        fixture.root
                        / index_surfaces.INDEX_TRANSACTION_RELATIVE_PATH
                    )
                elif attack == "symlink":
                    destination = (
                        fixture.root / ".tropo-studio" / "dirty-counter.json"
                    )
                    destination.unlink(missing_ok=True)
                    destination.symlink_to(unrelated)
                elif attack == "source-traversal":
                    destination = (
                        fixture.root
                        / "vault"
                        / "files"
                        / ".."
                        / ".."
                        / "unrelated.txt"
                    )
                else:
                    destination = fixture.files / "deadbeef.md"
                    destination.symlink_to(unrelated)
                journal = (
                    fixture.root
                    / index_surfaces.INDEX_TRANSACTION_RELATIVE_PATH
                )

                with self.assertRaises(index_surfaces.IndexSurfaceRefusal):
                    index_surfaces.write_jsonl_pair_atomic(
                        (
                            (fixture.current_surface, current),
                            (fixture.archive_surface, archive),
                        ),
                        companion_replacements=(
                            ()
                            if attack.startswith("source-")
                            else ((destination, b"ATTACK\n"),)
                        ),
                        source_replacements=(
                            ((destination, b"ATTACK\n"),)
                            if attack.startswith("source-")
                            else ()
                        ),
                    )

                self.assertEqual(unrelated.read_bytes(), b"human-owned bytes\n")
                self.assertFalse(journal.exists())

    def test_allowed_companion_interruption_recovers_its_own_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=0)
            fixture.prime()
            current = index_surfaces.read_jsonl_strict(fixture.current_surface)
            archive = index_surfaces.read_jsonl_strict(fixture.archive_surface)
            counter = fixture.root / ".tropo-studio" / "dirty-counter.json"
            before = counter.read_bytes()
            real_replace = index_surfaces.os.replace
            interrupted = False

            def interrupt_counter(src, dst):
                nonlocal interrupted
                if Path(dst) == counter and not interrupted:
                    interrupted = True
                    raise KeyboardInterrupt("reviewer-injected companion crash")
                return real_replace(src, dst)

            with mock.patch.object(
                index_surfaces.os,
                "replace",
                side_effect=interrupt_counter,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    index_surfaces.write_jsonl_pair_atomic(
                        (
                            (fixture.current_surface, current),
                            (fixture.archive_surface, archive),
                        ),
                        companion_replacements=((counter, b'{"writes":999}\n'),),
                    )

            journal = (
                fixture.root / index_surfaces.INDEX_TRANSACTION_RELATIVE_PATH
            )
            self.assertTrue(journal.is_file())
            index_surfaces.recover_pending_index_transaction(fixture.root)
            self.assertFalse(journal.exists())
            self.assertEqual(counter.read_bytes(), before)
            index_surfaces.read_jsonl_strict(fixture.current_surface)
            index_surfaces.read_jsonl_strict(fixture.archive_surface)

    def test_incremental_batch_freshens_two_dirty_sources_in_one_sealed_transaction(
        self,
    ) -> None:
        """Mounted reconcile owns every changed projection, not one arbitrary UID."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=1)
            fixture.prime()
            first_uid, second_uid = fixture.current_uids
            archive_uid = fixture.archive_uids[0]
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"
            cache_jsonl = fixture.cache_jsonl
            cache_meta = fixture.cache_meta
            cache_jsonl.parent.mkdir(parents=True, exist_ok=True)
            cache_jsonl.write_text("stale cache\n", encoding="utf-8")
            cache_meta.write_text("{}\n", encoding="utf-8")

            first_source = fixture.files / f"{first_uid}.md"
            second_source = fixture.files / f"{second_uid}.md"
            first_source.write_text(
                _entry_text(
                    first_uid,
                    state="active",
                    status="active",
                    title="first batch title",
                    body=f"# first\n\nrefs {archive_uid}\n",
                ),
                encoding="utf-8",
            )
            second_source.write_text(
                _entry_text(
                    second_uid,
                    state="archived",
                    status="done",
                    title="second batch title",
                    body="# second batch body\n",
                ),
                encoding="utf-8",
            )

            # AMENDED 2026-08-06 (metis-g103) under Mike's ruling: a single-file
            # write no longer has to prove the whole vault is unchanged, so a
            # second dirty source no longer refuses it. The single write is
            # documented non-authoritative and self-healing; the next full
            # rebuild reconciles. Previously this asserted refusal, which is the
            # behaviour that made two agents working at once block each other.
            #
            # WHAT THIS STILL PROTECTS, and it is the load-bearing half: the
            # BATCH path must still advance both sources in ONE sealed
            # transaction. That is asserted below and is unchanged.
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(rebuild.freshen_one(first_uid, fixture.root), 0)
            self.assertEqual(
                rebuild.freshen_many({first_uid, second_uid}, fixture.root),
                0,
            )

            current_rows = index_surfaces.read_jsonl_strict(
                fixture.current_surface
            )
            archive_rows = index_surfaces.read_jsonl_strict(
                fixture.archive_surface
            )
            current_by_uid = {row["uid"]: row for row in current_rows}
            archive_by_uid = {row["uid"]: row for row in archive_rows}
            self.assertEqual(current_by_uid[first_uid]["title"], "first batch title")
            self.assertNotIn(second_uid, current_by_uid)
            self.assertEqual(
                archive_by_uid[second_uid]["title"],
                "second batch title",
            )

            with sqlite3.connect(sqlite_path) as connection:
                entries = {
                    uid: (title, state)
                    for uid, title, state in connection.execute(
                        "SELECT uid, title, state FROM entries "
                        "WHERE uid IN (?, ?)",
                        (first_uid, second_uid),
                    )
                }
                fts = {
                    uid: (title, body)
                    for uid, title, body in connection.execute(
                        "SELECT uid, title, body FROM entries_fts "
                        "WHERE uid IN (?, ?)",
                        (first_uid, second_uid),
                    )
                }
            self.assertEqual(
                entries,
                {
                    first_uid: ("first batch title", "active"),
                    second_uid: ("second batch title", "archived"),
                },
            )
            self.assertIn("first batch title", fts[first_uid][0])
            self.assertIn("second batch body", fts[second_uid][1])

            # A strict read verifies the pair seal; SQLite carries the same
            # transaction-bound ratchet evidence, and cache/counter maintenance
            # happens once for the batch.
            sidecar_evidence = index_surfaces._load_ratchet_evidence(fixture.root)
            sqlite_evidence = index_surfaces._load_sqlite_ratchet_evidence(
                fixture.root
            )
            self.assertEqual(sqlite_evidence, sidecar_evidence)
            self.assertFalse(cache_jsonl.exists())
            self.assertFalse(cache_meta.exists())
            counter = json.loads(
                (fixture.root / ".tropo-studio" / "dirty-counter.json").read_text(
                    encoding="utf-8"
                )
            )
            # 2, not 1, since the 2026-08-06 ruling: the single-file write above
            # now SUCCEEDS instead of being refused, so it counts. The property
            # under test is that the batch is ONE sealed transaction, not two —
            # which is the second write, not the total.
            self.assertEqual(counter["writes_since_full_rebuild"], 2)

    def test_batch_keeps_unrelated_symlink_source_and_target_manifest_entries(
        self,
    ) -> None:
        """A staged regular projection must not erase another source's symlink entry."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=1)
            symlink_uid, batch_uid = fixture.current_uids
            symlink_source = fixture.files / f"{symlink_uid}.md"
            target = fixture.root / "library" / "handbook.md"
            target.parent.mkdir(parents=True)
            target.write_bytes(symlink_source.read_bytes())
            symlink_source.unlink()
            symlink_source.symlink_to("../../library/handbook.md")
            _git(fixture.root, "add", "-A", "vault/files", "library/handbook.md")
            _git(fixture.root, "commit", "-q", "-m", "symlink canonical source")
            fixture.prime()

            manifest_before = index_surfaces.load_trusted_derivation_manifest(
                fixture.root
            )
            source_key = ("source", f"vault/files/{symlink_uid}.md")
            target_key = ("symlink-target", f"vault/files/{symlink_uid}.md")
            before_by_key = {
                (kind, path): (mode, digest)
                for kind, path, mode, digest in manifest_before
            }
            self.assertEqual(
                before_by_key[source_key],
                (
                    "120000",
                    hashlib.sha256(symlink_source.read_bytes()).hexdigest(),
                ),
            )
            self.assertIn(target_key, before_by_key)

            batch_path = fixture.files / f"{batch_uid}.md"
            staged = batch_path.read_bytes().replace(
                f"fixture {batch_uid}".encode(),
                b"staged batch title",
            )
            self.assertEqual(
                rebuild.freshen_many(
                    (batch_uid,),
                    fixture.root,
                    source_replacements={batch_path: staged},
                ),
                0,
            )
            self.assertEqual(batch_path.read_bytes(), staged)

            manifest_after = index_surfaces.load_trusted_derivation_manifest(
                fixture.root
            )
            after_by_key = {
                (kind, path): (mode, digest)
                for kind, path, mode, digest in manifest_after
            }
            self.assertEqual(after_by_key[source_key], before_by_key[source_key])
            self.assertEqual(after_by_key[target_key], before_by_key[target_key])

    def test_batch_gardener_inbound_edges_match_one_full_union_pass(self) -> None:
        """Every fresh row must see every other fresh row in the same pass."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=1)
            fixture.prime()
            first_uid, second_uid = fixture.current_uids
            for uid, target in (
                (first_uid, second_uid),
                (second_uid, first_uid),
            ):
                source = fixture.files / f"{uid}.md"
                source.write_text(
                    source.read_text(encoding="utf-8").replace(
                        "created: '2026-07-26'\n",
                        f"refs:\n  - \"{target}\"\ncreated: '2026-07-26'\n",
                        1,
                    ),
                    encoding="utf-8",
                )

            self.assertEqual(
                rebuild.freshen_many({first_uid, second_uid}, fixture.root),
                0,
            )
            batch_rows = {
                row["uid"]: row["inbound_live_edges"]
                for row in index_surfaces.load_index_records(
                    fixture.root,
                    include_archive=True,
                    require_complete_union=True,
                )
                if row["uid"] in {first_uid, second_uid}
            }

            fixture.commit_sources("land reciprocal batch references")
            self.assertEqual(
                rebuild.rebuild_index(
                    fixture.root,
                    True,
                    reconcile=True,
                ),
                0,
            )
            full_rows = {
                row["uid"]: row["inbound_live_edges"]
                for row in index_surfaces.load_index_records(
                    fixture.root,
                    include_archive=True,
                    require_complete_union=True,
                )
                if row["uid"] in {first_uid, second_uid}
            }

            self.assertEqual(batch_rows, full_rows)
            self.assertEqual(
                batch_rows,
                {first_uid: 1, second_uid: 1},
            )

    def test_freshening_source_routes_gardener_dependent_target_fm_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=0)
            fixture.prime()
            source_uid, target_uid = fixture.current_uids
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"
            with sqlite3.connect(sqlite_path) as conn:
                target_fts_before = conn.execute(
                    "SELECT title, body FROM entries_fts WHERE uid = ?",
                    (target_uid,),
                ).fetchone()
                target_edges_before = conn.execute(
                    "SELECT rel, dst_uid FROM edges WHERE src_uid = ? ORDER BY rel, dst_uid",
                    (target_uid,),
                ).fetchall()
            source = fixture.files / f"{source_uid}.md"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    "created: '2026-07-26'\n",
                    f"refs:\n  - \"{target_uid}\"\ncreated: '2026-07-26'\n",
                    1,
                ),
                encoding="utf-8",
            )

            self.assertEqual(rebuild.freshen_many({source_uid}, fixture.root), 0)
            batch_target = next(
                row
                for row in index_surfaces.load_index_records(
                    fixture.root,
                    include_archive=True,
                    require_complete_union=True,
                )
                if row["uid"] == target_uid
            )
            self.assertEqual(batch_target["inbound_live_edges"], 1)
            with sqlite3.connect(sqlite_path) as conn:
                sqlite_target = json.loads(
                    conn.execute(
                        "SELECT fm_json FROM entries WHERE uid = ?",
                        (target_uid,),
                    ).fetchone()[0]
                )
                self.assertEqual(
                    conn.execute(
                        "SELECT title, body FROM entries_fts WHERE uid = ?",
                        (target_uid,),
                    ).fetchone(),
                    target_fts_before,
                )
                self.assertEqual(
                    conn.execute(
                        "SELECT rel, dst_uid FROM edges WHERE src_uid = ? ORDER BY rel, dst_uid",
                        (target_uid,),
                    ).fetchall(),
                    target_edges_before,
                )
            self.assertEqual(sqlite_target, batch_target)

            fixture.commit_sources("land dependent inbound edge")
            self.assertEqual(
                rebuild.rebuild_index(
                    fixture.root,
                    True,
                    reconcile=True,
                ),
                0,
            )
            full_target = next(
                row
                for row in index_surfaces.load_index_records(
                    fixture.root,
                    include_archive=True,
                    require_complete_union=True,
                )
                if row["uid"] == target_uid
            )
            self.assertEqual(batch_target, full_target)

    def test_batch_freshen_rolls_back_cache_and_counter_with_index_surfaces(
        self,
    ) -> None:
        """A maintenance-companion failure cannot leave a mixed transaction."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=1)
            fixture.prime()
            uid = fixture.current_uids[0]
            source = fixture.files / f"{uid}.md"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    f"fixture {uid}",
                    "batch title that must roll back",
                ),
                encoding="utf-8",
            )
            cache_jsonl = fixture.cache_jsonl
            cache_meta = fixture.cache_meta
            cache_jsonl.parent.mkdir(parents=True, exist_ok=True)
            cache_jsonl.write_bytes(b"stale cache bytes\n")
            cache_meta.write_bytes(b'{"stale":true}\n')
            dirty_counter = rebuild._dirty_counter_path(fixture.root)
            participants = (
                fixture.current_surface,
                fixture.archive_surface,
                fixture.root / "vault" / "00-index.sqlite",
                fixture.root / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
                fixture.root / index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
                cache_jsonl,
                cache_meta,
                dirty_counter,
            )
            before = tuple(path.read_bytes() for path in participants)
            real_replace = index_surfaces.os.replace

            def fail_dirty_counter_swap(src, dst):
                if Path(dst) == dirty_counter:
                    raise OSError("reviewer-injected dirty-counter replace failure")
                return real_replace(src, dst)

            stderr = io.StringIO()
            with mock.patch.object(
                index_surfaces.os,
                "replace",
                side_effect=fail_dirty_counter_swap,
            ), contextlib.redirect_stderr(stderr):
                rc = rebuild.freshen_many({uid}, fixture.root)

            self.assertNotEqual(rc, 0)
            self.assertIn("REFUSAL", stderr.getvalue())
            self.assertEqual(
                tuple(path.read_bytes() for path in participants),
                before,
            )

    def test_batch_remove_rolls_back_cache_and_counter_with_index_surfaces(
        self,
    ) -> None:
        """Batch removal includes invalidation and maintenance in its rollback."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=1)
            fixture.prime()
            uid = fixture.archive_uids[0]
            (fixture.files / f"{uid}.md").unlink()
            cache_jsonl = fixture.cache_jsonl
            cache_meta = fixture.cache_meta
            cache_jsonl.parent.mkdir(parents=True, exist_ok=True)
            cache_jsonl.write_bytes(b"stale cache bytes\n")
            cache_meta.write_bytes(b'{"stale":true}\n')
            dirty_counter = rebuild._dirty_counter_path(fixture.root)
            participants = (
                fixture.current_surface,
                fixture.archive_surface,
                fixture.root / "vault" / "00-index.sqlite",
                fixture.root / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
                fixture.root / index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
                cache_jsonl,
                cache_meta,
                dirty_counter,
            )
            before = tuple(path.read_bytes() for path in participants)
            real_replace = index_surfaces.os.replace

            def fail_dirty_counter_swap(src, dst):
                if Path(dst) == dirty_counter:
                    raise OSError("reviewer-injected dirty-counter replace failure")
                return real_replace(src, dst)

            stderr = io.StringIO()
            with mock.patch.object(
                index_surfaces.os,
                "replace",
                side_effect=fail_dirty_counter_swap,
            ), contextlib.redirect_stderr(stderr):
                rc = rebuild.remove_many({uid}, fixture.root)

            self.assertNotEqual(rc, 0)
            self.assertIn("REFUSAL", stderr.getvalue())
            self.assertEqual(
                tuple(path.read_bytes() for path in participants),
                before,
            )

    def test_incremental_only_preflights_both_surfaces_before_sqlite(self) -> None:
        """Reviewer plant 1: corrupt archive cannot partially freshen SQLite/current."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=1)
            fixture.prime()
            uid = fixture.current_uids[0]
            source = fixture.files / f"{uid}.md"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    f"fixture {uid}",
                    "fresh title that must not land",
                ),
                encoding="utf-8",
            )
            fixture.archive_surface.write_text(
                '{"uid":"syntactically-truncated"',
                encoding="utf-8",
            )
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = rebuild.freshen_one(uid, fixture.root)

            self.assertNotEqual(rc, 0)
            self.assertIn("REFUSAL", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                ),
                before,
            )

    def test_incremental_remove_preflights_both_surfaces_before_sqlite(self) -> None:
        """A corrupt archive cannot partially remove SQLite/current rows."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=1)
            fixture.prime()
            uid = fixture.current_uids[0]
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"
            fixture.archive_surface.write_bytes(b"")
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = rebuild.remove_one(uid, fixture.root)

            self.assertNotEqual(rc, 0)
            self.assertIn("REFUSAL", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                ),
                before,
            )

    def test_incremental_only_sqlite_swap_failure_restores_all_three(self) -> None:
        """A third-destination failure restores current/archive/SQLite bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=1)
            fixture.prime()
            uid = fixture.current_uids[0]
            source = fixture.files / f"{uid}.md"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    f"fixture {uid}",
                    "fresh title blocked by SQLite swap",
                ),
                encoding="utf-8",
            )
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
            )
            real_replace = index_surfaces.os.replace

            def fail_sqlite_swap(src, dst):
                if Path(dst) == sqlite_path:
                    raise OSError("reviewer-injected SQLite replace failure")
                return real_replace(src, dst)

            stderr = io.StringIO()
            with mock.patch.object(
                index_surfaces.os,
                "replace",
                side_effect=fail_sqlite_swap,
            ), contextlib.redirect_stderr(stderr):
                rc = rebuild.freshen_one(uid, fixture.root)

            self.assertNotEqual(rc, 0)
            self.assertIn("REFUSAL", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                ),
                before,
            )

    def test_incremental_remove_second_swap_failure_restores_all_three(self) -> None:
        """Removal uses the same rollback-capable three-destination transaction."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=1)
            fixture.prime()
            uid = fixture.current_uids[0]
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
            )
            real_replace = index_surfaces.os.replace

            def fail_archive_swap(src, dst):
                if Path(dst) == fixture.archive_surface:
                    raise OSError("reviewer-injected archive replace failure")
                return real_replace(src, dst)

            stderr = io.StringIO()
            with mock.patch.object(
                index_surfaces.os,
                "replace",
                side_effect=fail_archive_swap,
            ), contextlib.redirect_stderr(stderr):
                rc = rebuild.remove_one(uid, fixture.root)

            self.assertNotEqual(rc, 0)
            self.assertIn("REFUSAL", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                ),
                before,
            )

    def test_a_meta_sealed_in_the_previous_digest_format_bootstraps_forward(self) -> None:
        """2dcadf62 relabelled the source-inventory digest tag with no migration.

        Every meta sealed by the previous writer then failed verification, and
        the failure deadlocked: readers refuse, and the full rebuild that would
        re-stamp the meta is gated behind the same check, so the only sanctioned
        repair path could not run. Observed on the live Studio as three checks
        reporting "0 rows checked" — not failing loudly on bad data, silently
        validating nothing.

        Pinned to the last day the door is open, not to the wall clock. The
        door now has a dated close, and a pre-sunset proof read from the
        calendar would quietly stop being a pre-sunset proof on
        LEGACY_DIGEST_DOOR_SUNSET and redden for a reason that has nothing to
        do with what it claims.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fixture, meta_path, legacy_seal = self._legacy_sealed_fixture(tmp)

            with _on_day(LAST_OPEN_DAY):
                # Accepted rather than refused: a correct seal in a superseded
                # format is not a tampered one.
                index_surfaces._load_surface_meta(fixture.current_surface)

                # And the full rebuild — the sanctioned repair path, which was
                # previously gated behind this very check — now runs and
                # migrates the seal forward, so the bootstrap is a one-time
                # door rather than a permanent tolerance.
                self.assertEqual(
                    rebuild.rebuild_index(fixture.root, True, reconcile=True), 0
                )
            healed = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(
                healed["pair_sha256"],
                index_surfaces._surface_meta_digest(healed),
            )
            self.assertNotEqual(healed["pair_sha256"], legacy_seal)

    def _seal_under_the_previous_format(
        self, fixture: "FixtureStudio"
    ) -> tuple[Path, str]:
        """Re-seal this fixture's meta the way the pre-2dcadf62 writer did."""
        meta_path = (
            fixture.root / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
        )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        legacy_seal = index_surfaces._surface_meta_digest(
            meta, legacy_inventory_tag=True
        )
        # Without this the fixture would be one where both formats hash
        # identically, the door would never be consulted, and every assertion
        # downstream would hold for a reason that has nothing to do with the
        # door.
        self.assertNotEqual(
            legacy_seal,
            index_surfaces._surface_meta_digest(meta),
            "this fixture's two digest formats agree, so nothing below "
            "reaches the door",
        )
        meta["pair_sha256"] = legacy_seal
        meta_path.write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return meta_path, legacy_seal

    def _legacy_sealed_fixture(
        self, tmp: str
    ) -> tuple["FixtureStudio", Path, str]:
        """A primed studio holding a valid seal in the superseded format."""
        fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
        fixture.prime()
        self.assertEqual(
            rebuild.freshen_one(fixture.current_uids[0], fixture.root), 0
        )
        meta_path, legacy_seal = self._seal_under_the_previous_format(fixture)
        return fixture, meta_path, legacy_seal

    def _load_verdict(self, fixture: "FixtureStudio") -> Optional[str]:
        """The refusal text, or None when the surface metadata loaded."""
        try:
            index_surfaces._load_surface_meta(fixture.current_surface)
        except index_surfaces.IndexSurfaceRefusal as exc:
            return str(exc)
        return None

    def _seal_and_load(
        self,
        fixture: "FixtureStudio",
        meta_path: Path,
        mutate,
        *,
        legacy: bool,
    ) -> Optional[str]:
        """Apply `mutate`, seal under the chosen format, return the refusal or None."""
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        mutate(meta)
        meta["pair_sha256"] = index_surfaces._surface_meta_digest(
            {**meta, "pair_sha256": None}, legacy_inventory_tag=legacy
        )
        meta_path.write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        try:
            index_surfaces._load_surface_meta(fixture.current_surface)
        except index_surfaces.IndexSurfaceRefusal as exc:
            return str(exc)
        return None

    def test_the_legacy_digest_door_grants_no_admission_the_current_format_denies(
        self,
    ) -> None:
        """The door is a format ALIAS, not a permission.

        Argus A143 ratification counter on 377f7ef8. The plant this replaces
        forged ``record_count`` to 99999 and called it "the strongest form of
        the attack the new door could enable" -- but 99999 exceeds
        ``protected_record_count``, so it refuses at the shrink-ratchet guard
        (``protected_count < record_count``) BEFORE control ever reaches the
        digest comparison. It therefore refused identically with the door
        removed, which is exactly what Talos observed and read as the test
        holding. A negative test that cannot distinguish the two worlds
        certifies neither.

        The property that actually needs pinning is differential: whatever a
        forger can smuggle past the legacy tag, they can smuggle past the
        current tag too, because the digest is an unkeyed SHA-256 over bytes
        anyone holding the repo can recompute. It is a staleness/corruption
        checksum, not a tamper seal, and widening the accepted tag set costs
        nothing that was ever being defended.

        Pinned to the last open day: the differential claim is about what the
        door admits WHILE IT IS OPEN. After the sunset the legacy tag admits
        strictly less than the current one, which satisfies the property in
        substance and breaks it as an equality, so reading the date off the
        wall clock would turn this into a test that expires.
        """
        name = index_surfaces.CURRENT_INDEX_NAME

        def forge_beyond_ratchet(meta: dict) -> None:
            meta["surfaces"][name]["record_count"] = 99999

        def forge_within_ratchet(meta: dict) -> None:
            # Understating the count clears `protected_count >= record_count`,
            # so this one actually reaches the digest door.
            meta["surfaces"][name]["record_count"] = 0

        for mutate, label, reaches_door in (
            (forge_beyond_ratchet, "record_count=99999", False),
            (forge_within_ratchet, "record_count=0", True),
        ):
            verdicts = {}
            for legacy in (True, False):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = FixtureStudio(
                        Path(tmp), current_count=2, archive_count=3
                    )
                    fixture.prime()
                    meta_path = (
                        fixture.root
                        / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
                    )
                    self.assertEqual(
                        rebuild.freshen_one(
                            fixture.current_uids[0], fixture.root
                        ),
                        0,
                    )
                    with _on_day(LAST_OPEN_DAY):
                        verdicts[legacy] = self._seal_and_load(
                            fixture, meta_path, mutate, legacy=legacy
                        )

            with self.subTest(forgery=label):
                # THE claim: the legacy tag admits exactly what the current
                # tag admits. Same verdict, same reason, both directions.
                self.assertEqual(
                    verdicts[True] is None,
                    verdicts[False] is None,
                    f"{label}: legacy door and current format disagree — "
                    f"legacy={verdicts[True]!r} current={verdicts[False]!r}",
                )

            if not reaches_door:
                # Name why this case proves nothing about the door, so the
                # next reader does not mistake it for digest coverage.
                with self.subTest(forgery=label, assertion="refuses pre-door"):
                    self.assertIsNotNone(verdicts[True])
                    self.assertIn("invalid shrink ratchet", verdicts[True])
                    self.assertNotIn("pair digest mismatch", verdicts[True])

    def test_the_legacy_digest_door_is_exactly_one_pinned_format_wide(
        self,
    ) -> None:
        """A seal matching NEITHER emitted format is still refused.

        This is the door's own claim and nothing else, so it reads COLD. The
        memo is cleared immediately before the read and the refusal text is
        asserted, which together pin WHICH gate fired: six gates sit in front of
        the digest comparison and every one of them raises the same exception
        type, so a bare assertRaises here would pass on a malformed inventory
        and prove nothing about the door.

        The warm path is a separate claim and has its own test below. Splitting
        them is the repair (argus-a146, ruling on 39fe41c3): until 2026-08-08
        this single test tried to make both statements at once, warmed the memo
        as a side effect of setting the fixture up, and then measured the cache
        instead of the door -- red for a reason that had nothing to do with its
        label, which is the ADR-063 failure mode reappearing inside the test
        written to enforce ADR-063.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            self.assertEqual(
                rebuild.freshen_one(fixture.current_uids[0], fixture.root), 0
            )

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["pair_sha256"] = "0" * 64
            meta_path.write_text(
                json.dumps(meta, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            index_surfaces._SURFACE_META_MEMO.clear()
            with self.assertRaises(index_surfaces.IndexSurfaceRefusal) as caught:
                index_surfaces._load_surface_meta(fixture.current_surface)
            self.assertIn("pair digest mismatch", str(caught.exception))

    def test_a_warm_memo_cannot_serve_a_validation_of_bytes_that_are_gone(
        self,
    ) -> None:
        """A same-size rewrite is refused WITHOUT clearing the memo.

        The companion claim to the test above, and the one the old single test
        could not make. It reads a valid seal first so the memo is genuinely
        warm, then rewrites the file at identical length with a corrupted
        digest, then reads again with the cache left exactly as the first read
        left it.

        ``pair_sha256`` is fixed width, so a digest swap NEVER changes the file
        size, and rewriting in place moves neither device nor inode. Under the
        old ``(st_dev, st_ino, st_size, st_mtime_ns)`` key that left mtime as
        the only discriminator, and mtime is quantised to ~4ms: two writes in
        one tick produced an identical key and the second read was served from
        cache unvalidated. The one write the key could not see was the only
        write the seal exists to notice.

        Mutating the memo key back to the stat tuple must turn this test red.
        Verified by doing it, 2026-08-08 -- restoring the stat key admits the
        corrupted seal here while the cold test above stays green, which is why
        both tests are needed and neither alone is sufficient.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            self.assertEqual(
                rebuild.freshen_one(fixture.current_uids[0], fixture.root), 0
            )

            # Warm the memo on a seal that is genuinely valid: if this read
            # refuses, nothing was cached and the rest of the test would pass
            # while measuring an empty cache.
            self.assertIsNone(
                self._seal_and_load(fixture, meta_path, lambda meta: None, legacy=False),
                "the fixture must present a VALID seal here or the memo never warms",
            )
            before = meta_path.stat()

            corrupted = json.loads(meta_path.read_text(encoding="utf-8"))
            corrupted["pair_sha256"] = "0" * 64
            meta_path.write_text(
                json.dumps(corrupted, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            after = meta_path.stat()

            # The control. This test only exercises the dangerous case when the
            # rewrite is invisible to the retired stat key; if the two writes
            # happened to straddle an mtime tick, the old key would have missed
            # the cache on its own and a green result would say nothing. Assert
            # the collision is real before asserting the refusal.
            self.assertEqual(
                before.st_size,
                after.st_size,
                "a digest swap must be a same-size rewrite or this test is not "
                "exercising the collision it exists to cover",
            )
            self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
            retired_stat_key_collides = before.st_mtime_ns == after.st_mtime_ns
            if not retired_stat_key_collides:
                self.skipTest(
                    "the two writes straddled an mtime tick, so the retired stat "
                    "key would have missed the cache anyway; this run cannot "
                    "distinguish a sound key from a lucky one"
                )

            # No memo clear. This is the whole point.
            with self.assertRaises(index_surfaces.IndexSurfaceRefusal) as caught:
                index_surfaces._load_surface_meta(fixture.current_surface)
            self.assertIn("pair digest mismatch", str(caught.exception))

    def test_the_legacy_digest_door_stops_admitting_on_its_pinned_sunset(
        self,
    ) -> None:
        """ADR-063 consequence 3, first half: the dated removal.

        A bootstrap with no end date is a format. So the door has one, and the
        one thing that must be shown is that the DATE is what closes it —
        nothing else about the fixture changes across these three runs. The
        last-open-day run is not decoration: it is the control that proves this
        seal reaches the door at all. Without it, a refusal on the sunset day
        could be the shrink ratchet, a malformed inventory, or any of the six
        gates that sit in front of the digest comparison, and the test would be
        the blind plant ADR-063 replaced wearing different clothes.
        """
        self.assertIsInstance(SUNSET, datetime.date)
        ratified = datetime.date(2026, 7, 31)
        self.assertGreater(
            SUNSET,
            ratified,
            "a sunset on or before the ratification date is a door born shut",
        )
        self.assertLessEqual(
            (SUNSET - ratified).days,
            366,
            "a sunset more than a year past the ratification is the door "
            "becoming permanent by default, which is the outcome ADR-063 "
            "named; the window is sized for machines that are dark, and no "
            "machine is dark for a year and then merely resumes",
        )

        verdicts: dict[str, Optional[str]] = {}
        for label, day in (
            ("last open day", LAST_OPEN_DAY),
            ("sunset day", FIRST_CLOSED_DAY),
            ("day after sunset", SUNSET + ONE_DAY),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                fixture, _meta_path, _seal = self._legacy_sealed_fixture(tmp)
                with _on_day(day):
                    verdicts[label] = self._load_verdict(fixture)

        self.assertIsNone(
            verdicts["last open day"],
            "the control did not reach the door, so the refusals below prove "
            f"nothing about the sunset: {verdicts['last open day']!r}",
        )
        for label in ("sunset day", "day after sunset"):
            with self.subTest(day=label):
                refusal = verdicts[label]
                self.assertIsNotNone(refusal)
                # Refused for the sunset, and said so. Not the corruption
                # message: this seal is correct, in a format that expired.
                self.assertNotIn("pair digest mismatch", refusal)
                self.assertIn(
                    index_surfaces._LEGACY_SOURCE_INVENTORY_TAG, refusal
                )
                self.assertIn(SUNSET.isoformat(), refusal)
                self.assertIn(index_surfaces.LEGACY_DIGEST_DOOR_CURE, refusal)

    def test_the_closed_door_names_the_cure_that_actually_recovers(
        self,
    ) -> None:
        """ADR-063 consequence 3: a refusal is only usable if the cure cures.

        The deadlock 2dcadf62 shipped was not "readers refuse" — it was
        "readers refuse AND the sanctioned repair is gated behind the same
        check." Closing the door re-creates the first half on purpose, so the
        second half has to be measured rather than assumed, past the sunset,
        with the door genuinely shut.

        Both directions are checked, because naming the wrong flag is the
        failure mode: a bare ``--apply`` reads the seal through the same closed
        door and refuses again, and an operator who runs a printed cure and
        gets the same refusal back learns to stop reading cure lines.
        """
        cure = index_surfaces.LEGACY_DIGEST_DOOR_CURE
        self.assertIn("--apply", cure)
        self.assertIn(
            "--reconcile",
            cure,
            "only a source-complete reconcile authorizes metadata recovery; a "
            "cure without it names a command that refuses again",
        )

        with tempfile.TemporaryDirectory() as tmp:
            fixture, meta_path, legacy_seal = self._legacy_sealed_fixture(tmp)
            with _on_day(SUNSET + ONE_DAY):
                refusal = self._load_verdict(fixture)
                self.assertIsNotNone(refusal)
                self.assertIn(cure, refusal)

                # The command the cure does NOT name, run: still refused, and
                # nothing moved.
                stderr = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), (
                    contextlib.redirect_stderr(stderr)
                ):
                    bare_apply = rebuild.rebuild_index(
                        fixture.root, True, reconcile=False
                    )
                self.assertEqual(
                    bare_apply,
                    1,
                    "a bare --apply cleared a seal the door had just refused, "
                    "so the cure is naming the wrong command",
                )
                self.assertIn(SUNSET.isoformat(), stderr.getvalue())
                self.assertEqual(
                    json.loads(meta_path.read_text(encoding="utf-8"))[
                        "pair_sha256"
                    ],
                    legacy_seal,
                )

                # The command the cure DOES name, run: recovers.
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        rebuild.rebuild_index(
                            fixture.root, True, reconcile=True
                        ),
                        0,
                    )
                healed = json.loads(meta_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    healed["pair_sha256"],
                    index_surfaces._surface_meta_digest(healed),
                )
                self.assertNotEqual(healed["pair_sha256"], legacy_seal)
                # And the surface reads again with the door still shut.
                self.assertIsNone(self._load_verdict(fixture))

    def test_the_door_records_its_own_use_so_it_can_be_counted_later(
        self,
    ) -> None:
        """ADR-063 consequence 3, second half: the count.

        There is no bus to count metas on. ``.tropo-studio/locks/`` is
        gitignored, the seal is per-machine and never pushed, and that
        invisibility is itself a logged incident — a stale per-machine digest
        put three validator gates on `0 rows checked`. So the door reports its
        own use to the only place that can hold it: this machine.

        The control at the bottom is the load-bearing half. The write has to
        live inside the door's branch, because ``_load_surface_meta`` runs
        twice per surface read in every reader and validator in the studio; a
        write that also fires when the seal is current is a write on the hot
        read path wearing a telemetry label.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fixture, _meta_path, _seal = self._legacy_sealed_fixture(tmp)
            log_path = (
                fixture.root
                / index_surfaces.INDEX_LEGACY_DOOR_RELATIVE_PATH
            )
            self.assertFalse(log_path.exists())

            with _on_day(LAST_OPEN_DAY):
                index_surfaces._load_surface_meta(fixture.current_surface)
                self.assertTrue(
                    log_path.exists(),
                    "the door admitted a superseded seal and left no record "
                    "of it, so its use cannot be counted anywhere",
                )
                first = json.loads(log_path.read_text(encoding="utf-8"))
                index_surfaces._load_surface_meta(fixture.current_surface)
                second = json.loads(log_path.read_text(encoding="utf-8"))

            self.assertEqual(first["admissions_observed"], 1)
            self.assertEqual(second["admissions_observed"], 2)
            self.assertEqual(
                second["first_admitted_at"], first["first_admitted_at"]
            )
            self.assertEqual(second["sunset"], SUNSET.isoformat())
            self.assertEqual(
                second["legacy_tag"],
                index_surfaces._LEGACY_SOURCE_INVENTORY_TAG,
            )

        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            log_path = (
                fixture.root
                / index_surfaces.INDEX_LEGACY_DOOR_RELATIVE_PATH
            )
            with _on_day(LAST_OPEN_DAY):
                index_surfaces._load_surface_meta(fixture.current_surface)
            self.assertFalse(
                log_path.exists(),
                "a machine whose seal is current wrote a door-admission "
                "record, so the write is on the read path and not on the door",
            )

    def test_an_unwritable_admission_record_still_admits_the_read(
        self,
    ) -> None:
        """Telemetry may not become a new way for a read to fail.

        Read-only checkouts, a full disk, and a permission-stripped lock
        directory are all real. A door that raises because it could not write
        down that it opened would be a fresh deadlock introduced by the
        instrument built to close one.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fixture, _meta_path, _seal = self._legacy_sealed_fixture(tmp)
            log_path = (
                fixture.root
                / index_surfaces.INDEX_LEGACY_DOOR_RELATIVE_PATH
            )
            locks_dir = log_path.parent
            before = sorted(path.name for path in locks_dir.iterdir())

            with _on_day(LAST_OPEN_DAY), mock.patch.object(
                index_surfaces.os,
                "replace",
                side_effect=OSError("read-only lock directory"),
            ):
                self.assertIsNone(self._load_verdict(fixture))

            self.assertFalse(log_path.exists())
            self.assertEqual(
                sorted(path.name for path in locks_dir.iterdir()),
                before,
                "the failed telemetry write left its scratch file behind",
            )

    def test_the_door_report_answers_for_this_machine_or_says_it_cannot(
        self,
    ) -> None:
        """The instrument ADR-063 ordered, and the four answers it can give.

        The reading is live — it re-derives both digests from the seal on disk
        — rather than a playback of the admission log, because a log is stale
        the moment the machine heals and absent on a machine that has not read
        its index yet. And it does not go through ``_load_surface_meta``: that
        function refuses at the shrink ratchet before the digest branch, and
        after the sunset it refuses on the door itself, so an instrument built
        on it would go blind on exactly the machines it exists to find. The
        post-sunset case below is where that is measured.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            self.assertEqual(
                rebuild.freshen_one(fixture.current_uids[0], fixture.root), 0
            )
            root = fixture.root

            with _on_day(LAST_OPEN_DAY):
                healthy = index_surfaces.legacy_digest_door_report(root)
            self.assertEqual(healthy["verdict"], "current-sealed")
            self.assertIs(healthy["needs_door"], False)
            self.assertIs(healthy["door_open"], True)
            self.assertIs(healthy["stranded"], False)

            meta_path, _seal = self._seal_under_the_previous_format(fixture)
            with _on_day(LAST_OPEN_DAY):
                index_surfaces._load_surface_meta(fixture.current_surface)
                carried = index_surfaces.legacy_digest_door_report(root)
            self.assertEqual(carried["verdict"], "legacy-sealed")
            self.assertIs(carried["needs_door"], True)
            self.assertIs(carried["formats_are_distinguishable"], True)
            self.assertIs(carried["stranded"], False)
            self.assertEqual(
                carried["admissions"]["observed"],
                1,
                "the door fired and the report did not see it, so the two "
                "halves of the instrument are not wired to each other",
            )

            with _on_day(SUNSET + ONE_DAY):
                stranded = index_surfaces.legacy_digest_door_report(root)
            self.assertIs(
                stranded["needs_door"],
                True,
                "the instrument stopped seeing a machine the moment that "
                "machine became the one it was built to find",
            )
            self.assertIs(stranded["stranded"], True)
            self.assertIs(stranded["door_open"], False)
            self.assertEqual(
                stranded["cure"], index_surfaces.LEGACY_DIGEST_DOOR_CURE
            )

            meta_path.write_bytes(b"{ not json at all\n")
            with _on_day(LAST_OPEN_DAY):
                unknown = index_surfaces.legacy_digest_door_report(root)
            self.assertEqual(unknown["verdict"], "unreadable-meta")
            self.assertIsNone(
                unknown["needs_door"],
                "a seal it could not read was reported as an answer; a clean "
                "bill issued from missing data is the whole 1f29bcfb family, "
                "and summing it as a zero is how the door gets closed on a "
                "guess",
            )

            meta_path.unlink()
            with _on_day(LAST_OPEN_DAY):
                absent = index_surfaces.legacy_digest_door_report(root)
            self.assertEqual(absent["verdict"], "no-meta")
            self.assertIs(absent["needs_door"], False)
            self.assertIs(absent["meta_present"], False)

    def test_the_reported_door_state_never_disagrees_with_the_door(
        self,
    ) -> None:
        """One predicate, measured against the mechanism on both sides.

        ADR-063's finding is an instrument aimed one gate off from the thing it
        named. The reporting direction has the same failure available to it: a
        report that computes its own idea of "open" can say CLOSED on a day the
        door still opens, and the crew would close the door on a reading that
        was never about the door. So the claim and the behaviour are taken from
        the same fixture on the same day, across the boundary.
        """
        for offset in (-30, -1, 0, 1, 30):
            day = SUNSET + datetime.timedelta(days=offset)
            with tempfile.TemporaryDirectory() as tmp:
                fixture, _meta_path, _seal = self._legacy_sealed_fixture(tmp)
                with _on_day(day):
                    report = index_surfaces.legacy_digest_door_report(
                        fixture.root
                    )
                    admitted = self._load_verdict(fixture) is None
            with self.subTest(day=day.isoformat()):
                self.assertEqual(
                    report["door_open"],
                    admitted,
                    f"on {day.isoformat()} the report says "
                    f"door_open={report['door_open']} and the door "
                    f"{'admitted' if admitted else 'refused'} the same seal",
                )
                self.assertEqual(report["stranded"], not admitted)

    def test_the_door_reading_is_a_command_any_machine_can_run(self) -> None:
        """The reporting surface, reached the way a probe reaches it.

        ``tropo-smoke.py`` drives this as a subprocess from its INDEX probe
        rather than importing it, so the contract that matters is the process
        one: JSON on stdout, and an exit code that does not call an unanswered
        question a pass.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fixture, _meta_path, _seal = self._legacy_sealed_fixture(tmp)
            done = subprocess.run(
                [
                    sys.executable,
                    str(INDEX_SURFACES_TOOL),
                    "--json",
                    "--studio",
                    str(fixture.root),
                ],
                capture_output=True,
                text=True,
            )
            payload = json.loads(done.stdout)
            self.assertEqual(payload["verdict"], "legacy-sealed")
            self.assertIs(payload["needs_door"], True)
            self.assertEqual(
                done.returncode,
                1,
                "a machine that still needs the door exited 0, so a fleet "
                "sweep would count it as clear",
            )

            human = subprocess.run(
                [
                    sys.executable,
                    str(INDEX_SURFACES_TOOL),
                    "--studio",
                    str(fixture.root),
                ],
                capture_output=True,
                text=True,
            )
            self.assertIn(
                index_surfaces.LEGACY_DIGEST_DOOR_CURE, human.stdout
            )

        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            done = subprocess.run(
                [
                    sys.executable,
                    str(INDEX_SURFACES_TOOL),
                    "--json",
                    "--studio",
                    str(fixture.root),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(done.returncode, 0)
            self.assertIs(json.loads(done.stdout)["needs_door"], False)

    def test_full_apply_atomically_cures_sidecar_then_only_succeeds(self) -> None:
        """Metis F-P3-2: full apply is the real cure for stale pair metadata."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            uid = fixture.current_uids[0]
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"

            self.assertEqual(rebuild.freshen_one(uid, fixture.root), 0)
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            current_entry = meta["surfaces"][
                index_surfaces.CURRENT_INDEX_NAME
            ]
            current_entry["sha256"] = "0" * 64
            meta["pair_sha256"] = index_surfaces._surface_meta_digest(meta)
            meta_path.write_text(
                json.dumps(meta, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            refused_before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
                meta_path.read_bytes(),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.freshen_one(uid, fixture.root), 1)
            self.assertIn(
                "does not match trusted index-surface metadata",
                stderr.getvalue(),
            )
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                    meta_path.read_bytes(),
                ),
                refused_before,
            )

            self.assertEqual(
                rebuild.rebuild_index(fixture.root, True, reconcile=True),
                0,
            )
            self.assertNotEqual(meta_path.read_bytes(), refused_before[3])
            self.assertEqual(
                len(index_surfaces.read_jsonl_strict(fixture.current_surface)),
                2,
            )
            self.assertEqual(
                len(index_surfaces.read_jsonl_strict(fixture.archive_surface)),
                3,
            )
            with sqlite3.connect(sqlite_path) as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0],
                    5,
                )
            self.assertEqual(rebuild.freshen_one(uid, fixture.root), 0)

    def test_schema2_bootstrap_allows_dirty_target_only_and_refuses_mismatch(
        self,
    ) -> None:
        """Upgrade-day --only atomically mints schema3 copies from verified v2."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            schema2 = _install_schema2_sidecar(fixture)
            schema2["surfaces"][index_surfaces.CURRENT_INDEX_NAME][
                "record_count"
            ] += 4
            schema2["pair_sha256"] = index_surfaces._surface_meta_digest(
                schema2
            )
            (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            ).write_text(
                json.dumps(schema2, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            uid = fixture.current_uids[0]
            target = fixture.files / f"{uid}.md"
            target.write_text(
                target.read_text(encoding="utf-8").replace(
                    f"fixture {uid}",
                    "schema2 bootstrap dirty target",
                ),
                encoding="utf-8",
            )

            self.assertEqual(rebuild.freshen_one(uid, fixture.root), 0)
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            ratchet_path = (
                fixture.root
                / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
            )
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            ratchet = json.loads(ratchet_path.read_text(encoding="utf-8"))
            sqlite_evidence = index_surfaces._load_sqlite_ratchet_evidence(
                fixture.root
            )
            self.assertEqual(meta["schema_version"], 3)
            self.assertEqual(
                meta["metadata_recovery"]["reason"],
                "schema2-to-schema3-bootstrap",
            )
            self.assertEqual(
                meta["metadata_recovery"]["schema_migration"],
                {
                    "from": 2,
                    "to": 3,
                    "basis": (
                        "max(schema2-recorded-count,"
                        "verified-current-surface-count)"
                    ),
                },
            )
            for path in (fixture.current_surface, fixture.archive_surface):
                expected_floor = max(
                    schema2["surfaces"][path.name]["record_count"],
                    len(index_surfaces.read_jsonl_strict(path)),
                )
                for evidence in (meta, ratchet, sqlite_evidence):
                    self.assertEqual(
                        evidence["surfaces"][path.name][
                            "protected_record_count"
                        ],
                        expected_floor,
                    )
            self.assertEqual(ratchet, sqlite_evidence)
            self.assertEqual(rebuild.freshen_one(uid, fixture.root), 0)

        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=2)
            fixture.prime()
            schema2 = _install_schema2_sidecar(fixture)
            schema2["surfaces"][index_surfaces.CURRENT_INDEX_NAME][
                "sha256"
            ] = "0" * 64
            schema2["pair_sha256"] = index_surfaces._surface_meta_digest(
                schema2
            )
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            meta_path.write_text(
                json.dumps(schema2, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                (fixture.root / "vault" / "00-index.sqlite").read_bytes(),
                meta_path.read_bytes(),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(
                    rebuild.freshen_one(
                        fixture.current_uids[0],
                        fixture.root,
                    ),
                    1,
                )
            self.assertIn(
                "does not match trusted index-surface metadata",
                stderr.getvalue(),
            )
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    (fixture.root / "vault" / "00-index.sqlite").read_bytes(),
                    meta_path.read_bytes(),
                ),
                before,
            )
            self.assertFalse(
                (
                    fixture.root
                    / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
                ).exists()
            )
            self.assertIsNone(
                index_surfaces._load_sqlite_ratchet_evidence(fixture.root)
            )

    def test_schema2_only_escalates_full_and_never_leaves_stale_b(
        self,
    ) -> None:
        """Schema2 has no global manifest: --only A must fully rederive A+B."""
        for dirty_a in (False, True):
            with self.subTest(dirty_a=dirty_a), tempfile.TemporaryDirectory() as tmp:
                fixture = FixtureStudio(
                    Path(tmp),
                    current_count=2,
                    archive_count=1,
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    fixture.prime()
                _install_schema2_sidecar(fixture)
                uid_a, uid_b = fixture.current_uids
                source_a = fixture.files / f"{uid_a}.md"
                source_b = fixture.files / f"{uid_b}.md"
                if not dirty_a:
                    source_a.write_text(
                        source_a.read_text(encoding="utf-8").replace(
                            f"fixture {uid_a}",
                            "committed A after schema2",
                        ),
                        encoding="utf-8",
                    )
                source_b.write_text(
                    source_b.read_text(encoding="utf-8").replace(
                        f"fixture {uid_b}",
                        "committed B after schema2",
                    ),
                    encoding="utf-8",
                )
                fixture.commit_sources("A+B movement after schema2")
                if dirty_a:
                    source_a.write_text(
                        source_a.read_text(encoding="utf-8").replace(
                            f"fixture {uid_a}",
                            "dirty A after schema2",
                        ),
                        encoding="utf-8",
                    )

                before_rows = {
                    row["uid"]: row
                    for row in index_surfaces.load_index_records(
                        fixture.root,
                        include_archive=True,
                    )
                }
                self.assertNotEqual(
                    before_rows[uid_b]["title"],
                    "committed B after schema2",
                )
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(
                        rebuild.freshen_one(uid_a, fixture.root),
                        0,
                    )
                self.assertIn(
                    "escalating atomically to a full source-complete bootstrap",
                    stdout.getvalue(),
                )
                self.assertIn(
                    "all rows now match the trusted schema3 manifest",
                    stdout.getvalue(),
                )

                rows = {
                    row["uid"]: row
                    for row in index_surfaces.load_index_records(
                        fixture.root,
                        include_archive=True,
                        require_complete_union=True,
                    )
                }
                self.assertEqual(rows[uid_b]["title"], "committed B after schema2")
                self.assertEqual(
                    rows[uid_a]["title"],
                    (
                        "dirty A after schema2"
                        if dirty_a
                        else "committed A after schema2"
                    ),
                )
                meta = json.loads(
                    (
                        fixture.root
                        / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
                    ).read_text(encoding="utf-8")
                )
                artifact = json.loads(
                    fixture.run_artifact.read_text(encoding="utf-8")
                )
                self.assertEqual(
                    meta["metadata_recovery"]["reason"],
                    "schema2-to-schema3-bootstrap",
                )
                self.assertEqual(
                    artifact["parsed_record_count"],
                    len(rows),
                    "schema2 --only must parse every source, not only A",
                )
                self.assertEqual(
                    meta["derived_from_uncommitted"],
                    dirty_a,
                )
                self.assertEqual(
                    artifact["derived_from_uncommitted"],
                    dirty_a,
                )
                if dirty_a:
                    expected_path = source_a.relative_to(
                        fixture.root
                    ).as_posix()
                    self.assertEqual(
                        [
                            receipt["path"]
                            for receipt in meta["source_inventory"][
                                "uncommitted_inputs"
                            ]
                        ],
                        [expected_path],
                    )
                    with self.assertRaisesRegex(
                        index_surfaces.IndexSurfaceRefusal,
                        "does not authorize release",
                    ):
                        index_surfaces.load_index_records(
                            fixture.root,
                            include_archive=True,
                            require_complete_union=True,
                            require_authoritative=True,
                        )
                else:
                    self.assertEqual(
                        artifact["mode"],
                        "schema2-full-bootstrap",
                    )
                    self.assertEqual(
                        len(index_surfaces.load_index_records(
                            fixture.root,
                            include_archive=True,
                            require_complete_union=True,
                            require_authoritative=True,
                        )),
                        len(rows),
                    )

        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(
                Path(tmp),
                current_count=1,
                archive_count=1,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                fixture.prime()
            _install_schema2_sidecar(fixture)
            (fixture.files / f"{fixture.archive_uids[0]}.md").unlink()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            participants = (
                fixture.current_surface,
                fixture.archive_surface,
                fixture.root / "vault" / "00-index.sqlite",
                meta_path,
            )
            before = tuple(path.read_bytes() for path in participants)
            stderr = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                self.assertEqual(
                    rebuild.freshen_one(
                        fixture.current_uids[0],
                        fixture.root,
                    ),
                    1,
                )
            self.assertIn("full bootstrap could not prove", stderr.getvalue())
            self.assertEqual(
                tuple(path.read_bytes() for path in participants),
                before,
            )

    def test_incremental_source_scope_owns_only_target_paths(self) -> None:
        """--only/--remove allow their target and reject every other source."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=20)
            runtime = fixture.root / "vault" / "events" / "receipts" / "r.json"
            runtime.parent.mkdir(parents=True)
            runtime.write_text('{"sequence":1}\n', encoding="utf-8")
            _git(fixture.root, "add", runtime.relative_to(fixture.root).as_posix())
            _git(fixture.root, "commit", "-qm", "tracked runtime noninput")
            fixture.prime()

            target_uid = fixture.current_uids[0]
            target = fixture.files / f"{target_uid}.md"
            target.write_text(
                target.read_text(encoding="utf-8").replace(
                    f"fixture {target_uid}",
                    "owned dirty only target",
                ),
                encoding="utf-8",
            )
            unrelated = fixture.files / f"{fixture.archive_uids[0]}.md"
            unrelated_before = unrelated.read_bytes()
            unrelated.write_bytes(
                unrelated_before.replace(b"# fixture", b"# unrelated dirty")
            )
            untracked = fixture.files / "deadbeef.md"
            untracked.write_text(
                _entry_text(
                    "deadbeef",
                    state="active",
                    status="active",
                ),
                encoding="utf-8",
            )
            runtime.write_text('{"sequence":2}\n', encoding="utf-8")
            surface_before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                (fixture.root / "vault" / "00-index.sqlite").read_bytes(),
            )

            # AMENDED 2026-08-06 (metis-g103) under Mike's ruling. This block
            # asserted that a dirty UNRELATED file refuses the target's write,
            # and that the refusal message names it. That rule is gone: saving
            # one file no longer proves the whole vault. It was measured at 26.1s
            # per write, and it refused live when Orpheus's boot touched her own
            # agent card while an unrelated write was in flight.
            #
            # The new contract, asserted here: an unrelated dirty file is NOT
            # this operation's business, so the write proceeds.
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(
                    rebuild.freshen_one(target_uid, fixture.root),
                    0,
                    "an unrelated dirty file must no longer refuse a single "
                    "write -- that rule is what made two agents block each other",
                )
            # STILL LOAD-BEARING, and the reason this test survives rather than
            # being deleted: the write must touch the TARGET only. An unrelated
            # file being dirty must neither block the write nor be dragged into
            # it. Nothing about the unrelated or untracked paths may appear in
            # this operation's receipt.
            incremental_receipt = json.loads(
                fixture.run_artifact.read_text(encoding="utf-8")
            )
            receipt_text = json.dumps(incremental_receipt)
            self.assertNotIn(
                unrelated.relative_to(fixture.root).as_posix(), receipt_text,
                "an unrelated dirty file was pulled into the target's write")
            self.assertNotIn(
                untracked.relative_to(fixture.root).as_posix(), receipt_text,
                "an untracked file was pulled into the target's write")

            unrelated.write_bytes(unrelated_before)
            untracked.unlink()
            self.assertEqual(rebuild.freshen_one(target_uid, fixture.root), 0)
            target_relative = target.relative_to(fixture.root).as_posix()
            target_receipt = [{
                "content_sha256": hashlib.sha256(
                    target.read_bytes()
                ).hexdigest(),
                "mode": "100644",
                "path": target_relative,
                "symlink_target_sha256": None,
            }]
            incremental_artifact = json.loads(
                fixture.run_artifact.read_text(encoding="utf-8")
            )
            incremental_meta = json.loads(
                (
                    fixture.root
                    / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(incremental_artifact["mode"], "incremental-only")
            self.assertTrue(
                incremental_artifact["derived_from_uncommitted"]
            )
            self.assertEqual(
                incremental_artifact["uncommitted_inputs"],
                target_receipt,
            )
            self.assertEqual(
                incremental_meta["source_inventory"]["uncommitted_inputs"],
                target_receipt,
            )
            self.assertEqual(
                {
                    row["uid"]: row["title"]
                    for row in index_surfaces.read_jsonl_strict(
                        fixture.current_surface
                    )
                }[target_uid],
                "owned dirty only target",
            )
            _git(
                fixture.root,
                "add",
                target.relative_to(fixture.root).as_posix(),
            )
            _git(fixture.root, "commit", "-qm", "land owned only target")

            remove_uid = fixture.archive_uids[1]
            remove_target = fixture.files / f"{remove_uid}.md"
            remove_target.unlink()
            unrelated.write_bytes(
                unrelated_before.replace(b"# fixture", b"# still unrelated")
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.remove_one(remove_uid, fixture.root), 1)
            self.assertIn(
                unrelated.relative_to(fixture.root).as_posix(),
                stderr.getvalue(),
            )
            self.assertNotIn(
                remove_target.relative_to(fixture.root).as_posix(),
                stderr.getvalue(),
            )
            unrelated.write_bytes(unrelated_before)
            self.assertEqual(rebuild.remove_one(remove_uid, fixture.root), 0)

    def test_corrupt_active_mounted_cache_cannot_authorize_surface_shrink(self) -> None:
        """Reviewer plant 2: only compose.lock removal is retirement evidence."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=0)
            fixture.prime()
            mounted_vault_uid = "feed0001"
            mounted_row = {
                "uid": "feed0002",
                "type": "note",
                "title": "mounted row that must survive refusal",
                "state": "active",
                "status": "active",
                "path": (
                    f"mounted/{mounted_vault_uid}/vault/files/feed0002.md"
                ),
            }
            current_rows = index_surfaces.read_jsonl_strict(
                fixture.current_surface
            )
            archive_rows = index_surfaces.read_jsonl_strict(
                fixture.archive_surface
            )
            index_surfaces.write_jsonl_pair_atomic(
                (
                    (fixture.current_surface, current_rows + [mounted_row]),
                    (fixture.archive_surface, archive_rows),
                ),
                allow_shrink=True,
            )
            pin = "a" * 40
            compose_lock = fixture.root / rebuild.shard_index.COMPOSE_LOCK_REL
            compose_lock.parent.mkdir(parents=True, exist_ok=True)
            compose_lock.write_text(
                json.dumps({
                    "vaults": {
                        mounted_vault_uid: {
                            "resolved_commit": pin,
                            "mount_path": str(
                                fixture.root / "unreachable-mounted-vault"
                            ),
                        },
                    },
                }) + "\n",
                encoding="utf-8",
            )
            shard_jsonl = rebuild.shard_index.shard_jsonl_path(
                fixture.root, mounted_vault_uid
            )
            shard_meta = rebuild.shard_index.shard_meta_path(
                fixture.root, mounted_vault_uid
            )
            shard_jsonl.parent.mkdir(parents=True, exist_ok=True)
            shard_jsonl.write_text('{"uid":"corrupt"', encoding="utf-8")
            shard_meta.write_text(
                json.dumps({
                    "cache_kind": "mounted-vault-shard",
                    "vault_uid": mounted_vault_uid,
                    "resolved_commit": pin,
                    "derived_at": "2026-07-26T00:00:00Z",
                    "record_count": 1,
                    "jsonl_sha256": "0" * 64,
                }) + "\n",
                encoding="utf-8",
            )
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = rebuild.rebuild_index(fixture.root, True)

            self.assertNotEqual(rc, 0)
            self.assertIn("REFUSAL", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                ),
                before,
            )

    def test_hash_valid_stale_active_mount_refuses_without_shrink(self) -> None:
        """A still-pinned stale shard is unavailability, never retirement."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=0)
            fixture.prime()
            mounted_vault_uid = "feed0011"
            mounted_row = {
                "uid": "feed0012",
                "type": "note",
                "title": "hash-valid stale mounted row",
                "state": "active",
                "status": "active",
                "path": (
                    f"mounted/{mounted_vault_uid}/vault/files/feed0012.md"
                ),
            }
            current_rows = index_surfaces.read_jsonl_strict(
                fixture.current_surface
            )
            archive_rows = index_surfaces.read_jsonl_strict(
                fixture.archive_surface
            )
            index_surfaces.write_jsonl_pair_atomic(
                (
                    (fixture.current_surface, current_rows + [mounted_row]),
                    (fixture.archive_surface, archive_rows),
                ),
                allow_shrink=True,
            )
            old_pin = "a" * 40
            active_pin = "b" * 40
            compose_lock = fixture.root / rebuild.shard_index.COMPOSE_LOCK_REL
            compose_lock.parent.mkdir(parents=True, exist_ok=True)
            compose_lock.write_text(
                json.dumps({
                    "vaults": {
                        mounted_vault_uid: {
                            "resolved_commit": active_pin,
                            "mount_path": str(
                                fixture.root / "unreachable-mounted-vault"
                            ),
                        },
                    },
                }) + "\n",
                encoding="utf-8",
            )
            shard_jsonl = rebuild.shard_index.shard_jsonl_path(
                fixture.root, mounted_vault_uid
            )
            shard_jsonl.parent.mkdir(parents=True, exist_ok=True)
            shard_raw = (
                json.dumps(mounted_row, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            shard_jsonl.write_bytes(shard_raw)
            rebuild.shard_index.shard_meta_path(
                fixture.root, mounted_vault_uid
            ).write_text(
                json.dumps({
                    "cache_kind": "mounted-vault-shard",
                    "vault_uid": mounted_vault_uid,
                    "resolved_commit": old_pin,
                    "derived_at": "2026-07-26T00:00:00Z",
                    "record_count": 1,
                    "jsonl_sha256": rebuild.hashlib.sha256(
                        shard_raw
                    ).hexdigest(),
                }) + "\n",
                encoding="utf-8",
            )
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = rebuild.rebuild_index(fixture.root, True)

            self.assertNotEqual(rc, 0)
            self.assertIn("REFUSAL", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                ),
                before,
            )

    def test_derivation_fingerprint_change_rejects_and_rederives_cache(self) -> None:
        """Reviewer plant 3: code/predicate/Gardener drift invalidates cache."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            meta = json.loads(fixture.cache_meta.read_text(encoding="utf-8"))
            self.assertEqual(
                set(meta["derivation_fingerprints"]),
                {"parser", "archive_predicate", "gardener", "implementation"},
            )
            self.assertEqual(
                set(meta["derivation_identity"]),
                {
                    "derivation_input_sha256",
                    "source_inventory_sha256",
                    "source_inventory_count",
                    "repo_clock_date",
                    "wall_clock_date",
                    "compose_lock_sha256",
                    "mounted_pins",
                    "mounted_cache_identities",
                    "derivation_fingerprints",
                },
            )
            meta["derivation_fingerprints"]["parser"] = "simulated-old-parser"
            meta["derivation_identity"]["derivation_fingerprints"][
                "parser"
            ] = "simulated-old-parser"
            fixture.cache_meta.write_text(
                json.dumps(meta, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            archive_before = fixture.archive_surface.read_bytes()

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = rebuild.rebuild_index(fixture.root, True)

            artifact = json.loads(
                fixture.run_artifact.read_text(encoding="utf-8")
            )
            refreshed_meta = json.loads(
                fixture.cache_meta.read_text(encoding="utf-8")
            )
            self.assertEqual(rc, 0)
            self.assertIn("rejected-derivation-input-changed", stdout.getvalue())
            self.assertEqual(artifact["archive_cache_action"], "derived")
            self.assertEqual(artifact["parsed_record_count"], 5)
            self.assertEqual(fixture.archive_surface.read_bytes(), archive_before)
            self.assertNotEqual(
                refreshed_meta["derivation_fingerprints"]["parser"],
                "simulated-old-parser",
            )

    def test_title_preservation_survives_reconcile_and_archive_cache_reuse(self) -> None:
        """Every derived surface keeps the complete canonical source title."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=1)
            long_title = "cache-title-" + ("x" * 140)
            for uid in fixture.current_uids + fixture.archive_uids:
                source = fixture.files / f"{uid}.md"
                source.write_text(
                    source.read_text(encoding="utf-8").replace(
                        f"fixture {uid}",
                        long_title,
                    ),
                    encoding="utf-8",
                )
            fixture.commit_sources("install long-title fixtures")

            actions = []
            skips = []
            for reconcile in (True, False):
                self.assertEqual(
                    rebuild.rebuild_index(
                        fixture.root,
                        True,
                        reconcile=reconcile,
                    ),
                    0,
                )
                artifact = json.loads(
                    fixture.run_artifact.read_text(encoding="utf-8")
                )
                actions.append(artifact["archive_cache_action"])
                skips.append(artifact["archive_source_skip_count"])

                current_rows = index_surfaces.read_jsonl_strict(
                    fixture.current_surface
                )
                archive_rows = index_surfaces.read_jsonl_strict(
                    fixture.archive_surface
                )
                cache_rows = index_surfaces.read_jsonl_strict(
                    fixture.cache_jsonl,
                    verify_surface_metadata=False,
                )
                self.assertEqual(current_rows[0]["title"], long_title)
                self.assertEqual(archive_rows[0]["title"], long_title)
                self.assertEqual(cache_rows[0]["title"], long_title)
                with sqlite3.connect(
                    fixture.root / "vault" / "00-index.sqlite"
                ) as connection:
                    sqlite_titles = {
                        row[0]: row[1]
                        for row in connection.execute(
                            "SELECT uid, title FROM entries"
                        )
                    }
                    fts_titles = {
                        row[0]: row[1]
                        for row in connection.execute(
                            "SELECT uid, title FROM entries_fts"
                        )
                    }
                for uid in fixture.current_uids + fixture.archive_uids:
                    self.assertEqual(sqlite_titles[uid], long_title)
                    self.assertEqual(fts_titles[uid], long_title)

            self.assertEqual(actions, ["recreated", "reused"])
            self.assertEqual(skips, [0, 1])

    def test_current_input_change_rejects_archive_cache_and_rederives(self) -> None:
        """Current graph inputs can change derived fields on archived records."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            uid = fixture.current_uids[0]
            source = fixture.files / f"{uid}.md"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    f"fixture {uid}",
                    "current graph input changed",
                ),
                encoding="utf-8",
            )
            fixture.commit_sources("mutate current derivation input")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = rebuild.rebuild_index(fixture.root, True)

            artifact = json.loads(
                fixture.run_artifact.read_text(encoding="utf-8")
            )
            self.assertEqual(rc, 0)
            self.assertIn("rejected-derivation-input-changed", stdout.getvalue())
            self.assertEqual(artifact["archive_cache_action"], "derived")
            self.assertEqual(artifact["parsed_record_count"], 5)

    def test_dirty_relevant_config_disables_reuse_but_runtime_files_do_not(
        self,
    ) -> None:
        """Only actual source/code/config drift makes identity unavailable."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            attributes = fixture.root / ".gitattributes"
            attributes.write_text(
                "vault/files/*.md filter=navblockstrip\n",
                encoding="utf-8",
            )
            _git(fixture.root, "add", ".gitattributes")
            _git(fixture.root, "commit", "-q", "-m", "track derivation config")
            fixture.prime()

            attributes.write_text(
                attributes.read_text(encoding="utf-8")
                + "# substantive derivation config edit\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
            artifact = json.loads(fixture.run_artifact.read_text(encoding="utf-8"))

            self.assertIn("rejected-identity-unproven", stdout.getvalue())
            self.assertTrue(
                artifact["archive_cache_action"].startswith("not-written:")
            )
            self.assertEqual(artifact["archive_source_skip_count"], 0)
            self.assertEqual(artifact["parsed_record_count"], 5)

    def test_derivation_cleanliness_strips_navblock_in_process_and_stays_fail_closed(
        self,
    ) -> None:
        """Canonical in-process cleaning is fast, exact, and conservative."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "vault" / "files" / "abc00001.md"
            source.parent.mkdir(parents=True)
            source_text = _entry_text(
                "abc00001",
                state="active",
                status="active",
            )
            source.write_text(source_text, encoding="utf-8")
            attributes_text = "vault/files/*.md filter=navblockstrip\n"
            (root / ".gitattributes").write_text(
                attributes_text,
                encoding="utf-8",
            )
            marker = root / "filter-was-invoked"
            filter_driver = root / "slow-failing-filter.py"
            filter_driver.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "import time\n"
                "Path(sys.argv[1]).write_text('invoked', encoding='utf-8')\n"
                "time.sleep(3)\n"
                "raise SystemExit(17)\n",
                encoding="utf-8",
            )
            _git(root, "init", "-q")
            _git(root, "config", "user.email", "fixture@test.local")
            _git(root, "config", "user.name", "fixture")
            _git(root, "add", ".gitattributes", "vault/files", filter_driver.name)
            _git(root, "commit", "-q", "-m", "fixture source")

            configured_driver = " ".join(
                (
                    shlex.quote(sys.executable),
                    shlex.quote(str(filter_driver)),
                    shlex.quote(str(marker)),
                )
            )
            _git(
                root,
                "config",
                "filter.navblockstrip.clean",
                configured_driver,
            )
            _git(root, "config", "filter.navblockstrip.required", "true")
            config_path = root / ".git" / "config"
            config_before = config_path.read_bytes()

            nav_block = (
                "<!-- nav-block:start -->\n"
                "machine-derived navigation\n"
                "<!-- nav-block:end -->\n"
            )
            source.write_text(source_text + nav_block, encoding="utf-8")
            started = time.monotonic()
            identity, reason = rebuild._archive_derivation_identity(root)

            self.assertIsNotNone(identity)
            self.assertEqual(reason, "complete")
            self.assertLess(time.monotonic() - started, 2.0)
            self.assertFalse(marker.exists())
            self.assertEqual(config_path.read_bytes(), config_before)

            attributes = root / ".gitattributes"
            attributes.write_text(
                attributes_text + "# ordinary dirty path\n",
                encoding="utf-8",
            )
            identity, reason = rebuild._archive_derivation_identity(root)
            self.assertIsNone(identity)
            self.assertIn("dirty ordinary source/input", reason)
            self.assertFalse(marker.exists())
            attributes.write_text(attributes_text, encoding="utf-8")

            source.write_text(
                source_text + "# substantive edit\n" + nav_block,
                encoding="utf-8",
            )
            identity, reason = rebuild._archive_derivation_identity(root)

            self.assertIsNone(identity)
            self.assertIn("dirty", reason)
            self.assertFalse(marker.exists())
            self.assertEqual(config_path.read_bytes(), config_before)

            source.write_text(source_text + nav_block, encoding="utf-8")
            untracked = root / "untracked.txt"
            untracked.write_text("not ignored\n", encoding="utf-8")
            identity, reason = rebuild._archive_derivation_identity(root)
            self.assertIsNotNone(identity)
            self.assertEqual(reason, "complete")
            untracked.unlink()

            attributes.write_text(
                attributes.read_text(encoding="utf-8") + "# staged change\n",
                encoding="utf-8",
            )
            _git(root, "add", ".gitattributes")
            identity, reason = rebuild._archive_derivation_identity(root)
            self.assertIsNone(identity)
            self.assertIn("staged", reason)
            self.assertFalse(marker.exists())
            self.assertEqual(config_path.read_bytes(), config_before)
            self.assertEqual(
                _git(root, "config", "--get", "filter.navblockstrip.clean"),
                configured_driver,
            )
            head = _git(root, "rev-parse", "HEAD")
            with mock.patch.object(
                rebuild.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("git", 20),
            ):
                clean, reason = rebuild._derivation_worktree_clean(root, head)
            self.assertIsNone(clean)
            self.assertIn("cannot verify derivation working tree", reason)

    def test_tracked_dirty_counter_inode_rewrite_keeps_cache_eligible(self) -> None:
        """Tracked runtime state churn is outside archive derivation identity."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            counter = rebuild._dirty_counter_path(fixture.root)
            counter.parent.mkdir(parents=True, exist_ok=True)
            counter.write_text(
                json.dumps({
                    "writes_since_full_rebuild": 647,
                    "last_full_rebuild": "2026-07-25",
                    "last_updated": "2026-07-25",
                }) + "\n",
                encoding="utf-8",
            )
            _git(fixture.root, "add", "-f", str(counter.relative_to(fixture.root)))
            _git(fixture.root, "commit", "-q", "-m", "track live dirty counter")

            actions = []
            skip_counts = []
            parsed_counts = []
            for reconcile in (True, False, False):
                self.assertEqual(
                    rebuild.rebuild_index(
                        fixture.root,
                        True,
                        reconcile=reconcile,
                    ),
                    0,
                )
                artifact = json.loads(
                    fixture.run_artifact.read_text(encoding="utf-8")
                )
                actions.append(artifact["archive_cache_action"])
                skip_counts.append(artifact["archive_source_skip_count"])
                parsed_counts.append(artifact["parsed_record_count"])

            self.assertEqual(actions, ["recreated", "reused", "reused"])
            self.assertEqual(skip_counts, [0, 3, 3])
            self.assertEqual(parsed_counts, [5, 2, 2])
            self.assertEqual(
                json.loads(counter.read_text(encoding="utf-8"))[
                    "writes_since_full_rebuild"
                ],
                0,
            )

    def test_runtime_counter_events_receipts_and_cursor_do_not_disable_reuse(
        self,
    ) -> None:
        """Live-shaped runtime churn permits full→only and three-pass reuse."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            counter = rebuild._dirty_counter_path(fixture.root)
            receipt = fixture.root / "vault" / "events" / "receipts" / "talos.jsonl"
            stream = fixture.root / "vault" / "events" / "streams" / "talos.jsonl"
            cursor = fixture.root / ".tropo-studio" / "events" / "cursor.json"
            for path in (counter, receipt, stream, cursor):
                path.parent.mkdir(parents=True, exist_ok=True)
            counter.write_text('{"writes_since_full_rebuild":647}\n', encoding="utf-8")
            receipt.write_text('{"seq":1}\n', encoding="utf-8")
            stream.write_text('{"seq":1}\n', encoding="utf-8")
            cursor.write_text('{"cursor":1}\n', encoding="utf-8")
            _git(
                fixture.root,
                "add",
                "-f",
                *(str(path.relative_to(fixture.root)) for path in (
                    counter,
                    receipt,
                    stream,
                    cursor,
                )),
            )
            _git(fixture.root, "commit", "-q", "-m", "track runtime state")

            actions = []
            skips = []
            parsed = []
            self.assertEqual(
                rebuild.rebuild_index(fixture.root, True, reconcile=True),
                0,
            )
            artifact = json.loads(fixture.run_artifact.read_text(encoding="utf-8"))
            actions.append(artifact["archive_cache_action"])
            skips.append(artifact["archive_source_skip_count"])
            parsed.append(artifact["parsed_record_count"])

            receipt.write_text('{"seq":1}\n{"seq":2}\n', encoding="utf-8")
            stream.write_text('{"seq":1}\n{"seq":2}\n', encoding="utf-8")
            cursor.write_text('{"cursor":2}\n', encoding="utf-8")
            self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
            artifact = json.loads(fixture.run_artifact.read_text(encoding="utf-8"))
            actions.append(artifact["archive_cache_action"])
            skips.append(artifact["archive_source_skip_count"])
            parsed.append(artifact["parsed_record_count"])

            receipt.write_text(
                receipt.read_text(encoding="utf-8") + '{"seq":3}\n',
                encoding="utf-8",
            )
            cursor.write_text('{"cursor":3}\n', encoding="utf-8")
            self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
            artifact = json.loads(fixture.run_artifact.read_text(encoding="utf-8"))
            actions.append(artifact["archive_cache_action"])
            skips.append(artifact["archive_source_skip_count"])
            parsed.append(artifact["parsed_record_count"])

            self.assertEqual(actions, ["recreated", "reused", "reused"])
            self.assertEqual(skips, [0, 3, 3])
            self.assertEqual(parsed, [5, 2, 2])
            self.assertEqual(
                rebuild.freshen_one(fixture.current_uids[0], fixture.root),
                0,
            )

    def test_tracked_symlink_is_clean_until_link_target_bytes_change(self) -> None:
        """Mode 120000 hashes the link text exactly and still detects retargeting."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            library = fixture.root / "library"
            library.mkdir()
            symlink_uid = "c92ae197"
            handbook_text = _entry_text(
                symlink_uid,
                state="active",
                status="active",
                title="tracked handbook symlink fixture",
            )
            first_target = library / "handbook-a.md"
            second_target = library / "handbook-b.md"
            first_target.write_text(handbook_text, encoding="utf-8")
            second_target.write_text(handbook_text, encoding="utf-8")
            link = fixture.files / f"{symlink_uid}.md"
            link.symlink_to("../../library/handbook-a.md")
            _git(fixture.root, "add", "library", "vault/files")
            _git(fixture.root, "commit", "-q", "-m", "track governed symlink")

            actions = []
            skip_counts = []
            for reconcile in (True, False, False):
                self.assertEqual(
                    rebuild.rebuild_index(
                        fixture.root,
                        True,
                        reconcile=reconcile,
                    ),
                    0,
                )
                artifact = json.loads(
                    fixture.run_artifact.read_text(encoding="utf-8")
                )
                actions.append(artifact["archive_cache_action"])
                skip_counts.append(artifact["archive_source_skip_count"])

            self.assertEqual(actions, ["recreated", "reused", "reused"])
            self.assertEqual(skip_counts, [0, 3, 3])
            identity, reason = rebuild._archive_derivation_identity(fixture.root)
            self.assertIsNotNone(identity)
            self.assertEqual(reason, "complete")

            link.unlink()
            link.symlink_to("../../library/handbook-b.md")
            identity, reason = rebuild._archive_derivation_identity(fixture.root)
            self.assertIsNone(identity)
            self.assertIn("dirty navblock source/input", reason)
            self.assertIn(symlink_uid, reason)

    def test_pair_write_rolls_back_first_surface_when_second_replace_fails(self) -> None:
        """Reviewer plant 4: the pair remains byte-identical after swap failure."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "vault").mkdir()
            current_path = root / "vault" / index_surfaces.CURRENT_INDEX_NAME
            archive_path = root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME
            _write_jsonl(current_path, [{"uid": "aaa00001", "version": 1}])
            _write_jsonl(archive_path, [{"uid": "bbb00001", "version": 1}])
            _initialize_trusted_pair(
                current_path,
                archive_path,
                [{"uid": "aaa00001", "version": 1}],
                [{"uid": "bbb00001", "version": 1}],
            )
            before = (current_path.read_bytes(), archive_path.read_bytes())
            real_replace = index_surfaces.os.replace

            def fail_archive_swap(src, dst):
                if Path(dst) == archive_path:
                    raise OSError("reviewer-injected second replace failure")
                return real_replace(src, dst)

            with mock.patch.object(
                index_surfaces.os,
                "replace",
                side_effect=fail_archive_swap,
            ):
                with self.assertRaises(index_surfaces.IndexSurfaceRefusal):
                    index_surfaces.write_jsonl_pair_atomic(
                        (
                            (
                                current_path,
                                [{"uid": "aaa00001", "version": 2}],
                            ),
                            (
                                archive_path,
                                [{"uid": "bbb00001", "version": 2}],
                            ),
                        ),
                    )

            self.assertEqual(
                (current_path.read_bytes(), archive_path.read_bytes()),
                before,
            )

    def test_interrupted_pair_recovers_deterministically_on_next_entry(self) -> None:
        """A crash between swaps leaves a journal that the next lock recovers."""
        class SimulatedInterruption(BaseException):
            pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "vault").mkdir()
            current_path = root / "vault" / index_surfaces.CURRENT_INDEX_NAME
            archive_path = root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME
            _write_jsonl(current_path, [{"uid": "aaa00001", "version": 1}])
            _write_jsonl(archive_path, [{"uid": "bbb00001", "version": 1}])
            _initialize_trusted_pair(
                current_path,
                archive_path,
                [{"uid": "aaa00001", "version": 1}],
                [{"uid": "bbb00001", "version": 1}],
            )
            before = (current_path.read_bytes(), archive_path.read_bytes())
            real_replace = index_surfaces.os.replace

            def interrupt_archive_swap(src, dst):
                if Path(dst) == archive_path:
                    raise SimulatedInterruption()
                return real_replace(src, dst)

            with mock.patch.object(
                index_surfaces.os,
                "replace",
                side_effect=interrupt_archive_swap,
            ):
                with self.assertRaises(SimulatedInterruption):
                    index_surfaces.write_jsonl_pair_atomic(
                        (
                            (
                                current_path,
                                [{"uid": "aaa00001", "version": 2}],
                            ),
                            (
                                archive_path,
                                [{"uid": "bbb00001", "version": 2}],
                            ),
                        ),
                    )

            journal = (
                root / index_surfaces.INDEX_TRANSACTION_RELATIVE_PATH
            )
            self.assertTrue(journal.is_file())
            self.assertNotEqual(
                (current_path.read_bytes(), archive_path.read_bytes()),
                before,
            )

            index_surfaces.recover_pending_index_transaction(root)

            self.assertEqual(
                (current_path.read_bytes(), archive_path.read_bytes()),
                before,
            )
            self.assertFalse(journal.exists())
            self.assertFalse(list(root.rglob("*.before")))
            self.assertFalse(list(root.rglob("*.after")))

    def test_pair_callers_serialize_without_lost_updates_or_temp_leaks(self) -> None:
        """Canonical lock serializes direct route callers in one process."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            vault = root / "vault"
            vault.mkdir()
            current_path = vault / index_surfaces.CURRENT_INDEX_NAME
            archive_path = vault / index_surfaces.ARCHIVE_INDEX_NAME
            _write_jsonl(current_path, [{"uid": "aaa00001", "state": "active"}])
            _write_jsonl(
                archive_path,
                [{"uid": "bbb00001", "state": "archived"}],
            )
            _initialize_trusted_pair(
                current_path,
                archive_path,
                [{"uid": "aaa00001", "state": "active"}],
                [{"uid": "bbb00001", "state": "archived"}],
            )
            barrier = threading.Barrier(3)
            errors: list[BaseException] = []

            def route(uid: str) -> None:
                try:
                    barrier.wait()
                    index_surfaces.route_record(
                        root,
                        {"uid": uid, "state": "active", "status": "active"},
                    )
                except BaseException as exc:
                    errors.append(exc)

            threads = [
                threading.Thread(target=route, args=("aaa00002",)),
                threading.Thread(target=route, args=("aaa00003",)),
            ]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join(timeout=10)

            self.assertFalse(errors)
            self.assertEqual(
                {
                    row["uid"]
                    for row in index_surfaces.read_jsonl_strict(current_path)
                },
                {"aaa00001", "aaa00002", "aaa00003"},
            )
            self.assertFalse(
                (root / index_surfaces.INDEX_TRANSACTION_RELATIVE_PATH).exists()
            )
            self.assertFalse(list(root.rglob("*.before")))
            self.assertFalse(list(root.rglob("*.after")))

    def test_union_validation_refuses_missing_archive_surface(self) -> None:
        """Reviewer plant 5: a required union cannot silently become current-only."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = root / "vault" / "files"
            files.mkdir(parents=True)
            (root / ".tropo").mkdir()
            uid = "ace00001"
            (files / f"{uid}.md").write_text(
                _entry_text(uid, state="active", status="active"),
                encoding="utf-8",
            )
            _write_jsonl(
                root / "vault" / index_surfaces.CURRENT_INDEX_NAME,
                [{
                    "uid": uid,
                    "type": "note",
                    "path": f"vault/files/{uid}.md",
                }],
            )

            findings, checked, defects = validate.check_index_union_integrity(root)

            self.assertEqual(checked, 1)
            self.assertEqual(defects, 1)
            self.assertTrue(
                any(
                    finding.startswith("[ERROR]")
                    and index_surfaces.ARCHIVE_INDEX_NAME in finding
                    and "missing" in finding
                    for finding in findings
                ),
                findings,
            )
            self.assertEqual(
                [
                    row["uid"]
                    for row in index_surfaces.load_index_records(
                        root,
                        include_archive=True,
                    )
                ],
                [uid],
            )
            with self.assertRaises(index_surfaces.IndexSurfaceRefusal):
                index_surfaces.load_index_records(
                    root,
                    include_archive=True,
                    require_complete_union=True,
                )

    def test_strict_surface_reader_refuses_missing_final_newline(self) -> None:
        """Reviewer plant 6: valid JSON without writer newline is truncation."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            current_path = root / index_surfaces.CURRENT_INDEX_NAME
            archive_path = root / index_surfaces.ARCHIVE_INDEX_NAME
            current_row = {"uid": "cab00001", "state": "active"}
            archive_row = {"uid": "cab00002", "state": "archived"}
            _write_jsonl(current_path, [current_row])
            archive_path.write_text(
                json.dumps(archive_row, separators=(",", ":")),
                encoding="utf-8",
            )
            before = (current_path.read_bytes(), archive_path.read_bytes())

            with self.assertRaises(index_surfaces.IndexSurfaceRefusal):
                index_surfaces.read_jsonl_strict(archive_path)
            with self.assertRaises(index_surfaces.IndexSurfaceRefusal):
                index_surfaces.write_jsonl_pair_atomic(
                    (
                        (current_path, [current_row]),
                        (archive_path, [archive_row]),
                    ),
                )

            self.assertEqual(
                (current_path.read_bytes(), archive_path.read_bytes()),
                before,
            )

    def test_empty_surface_requires_trusted_pair_metadata(self) -> None:
        """Zero-byte/newline-only truncation needs a proven zero-row pair."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            vault = root / "vault"
            vault.mkdir()
            current_path = vault / index_surfaces.CURRENT_INDEX_NAME
            archive_path = vault / index_surfaces.ARCHIVE_INDEX_NAME
            _write_jsonl(current_path, [{"uid": "cab00001", "state": "active"}])
            archive_path.write_bytes(b"\n")
            with self.assertRaises(index_surfaces.IndexSurfaceRefusal):
                index_surfaces.read_jsonl_strict(archive_path)

            archive_path.write_bytes(b"")

            with self.assertRaises(index_surfaces.IndexSurfaceRefusal):
                index_surfaces.read_jsonl_strict(archive_path)

            archive_path.unlink()
            current_rows = [{"uid": "cab00001", "state": "active"}]
            proof = index_surfaces.prove_full_source_derivation(
                current_rows,
                [],
                source_complete=True,
                source_inventory=(
                    (
                        "vault/files/cab00001.md",
                        "100644",
                        "a" * 40,
                    ),
                ),
            )
            index_surfaces.write_jsonl_pair_atomic(
                (
                    (current_path, current_rows),
                    (archive_path, []),
                ),
                full_source_derivation_proof=proof,
                surface_metadata_recovery_reason=(
                    "test-source-complete-reconcile"
                ),
            )
            self.assertEqual(
                index_surfaces.read_jsonl_strict(archive_path),
                [],
            )

            current_path.write_bytes(b"")
            with self.assertRaises(index_surfaces.IndexSurfaceRefusal):
                index_surfaces.read_jsonl_strict(current_path)

    def test_fresh_clone_full_derivation_proves_legitimate_empty_archive(self) -> None:
        """An absent pair may be created when a full scan proves zero archive rows."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=0)

            rc = rebuild.rebuild_index(fixture.root, True, reconcile=True)

            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(rc, 0)
            self.assertTrue(fixture.current_surface.is_file())
            self.assertTrue(fixture.archive_surface.is_file())
            self.assertEqual(
                index_surfaces.read_jsonl_strict(fixture.archive_surface),
                [],
            )
            self.assertEqual(
                meta["surfaces"][index_surfaces.ARCHIVE_INDEX_NAME][
                    "record_count"
                ],
                0,
            )
            self.assertEqual(meta["schema_version"], 3)
            self.assertEqual(meta["source_inventory"]["tracked_source_count"], 2)
            self.assertEqual(len(meta["source_inventory"]["sha256"]), 64)
            self.assertEqual(
                meta["surfaces"][index_surfaces.ARCHIVE_INDEX_NAME][
                    "protected_record_count"
                ],
                0,
            )

    def test_fresh_clone_indexes_dirty_governed_wip_with_explicit_receipt(
        self,
    ) -> None:
        """G97 A: initial creation accounts for every present governed WIP path."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=1)
            tracked = fixture.files / f"{fixture.archive_uids[0]}.md"
            tracked.write_text(
                tracked.read_text(encoding="utf-8").replace(
                    f"fixture {fixture.archive_uids[0]}",
                    "worktree archive title",
                ),
                encoding="utf-8",
            )
            new_uid = "deadbeef"
            untracked_governed = fixture.files / f"{new_uid}.md"
            untracked_governed.write_text(
                _entry_text(
                    new_uid,
                    state="active",
                    status="active",
                    title="untracked governed WIP",
                ),
                encoding="utf-8",
            )
            unrelated = fixture.root / "scratch-not-a-source.txt"
            unrelated.write_text("untracked non-governed note\n", encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = rebuild.rebuild_index(fixture.root, True)

            artifact = json.loads(
                fixture.run_artifact.read_text(encoding="utf-8")
            )
            rows = index_surfaces.load_index_records(
                fixture.root,
                include_archive=True,
                require_complete_union=True,
            )
            by_uid = {row["uid"]: row for row in rows}
            expected_dirty_paths = sorted([
                tracked.relative_to(fixture.root).as_posix(),
                untracked_governed.relative_to(fixture.root).as_posix(),
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(by_uid[new_uid]["title"], "untracked governed WIP")
            self.assertEqual(
                by_uid[fixture.archive_uids[0]]["title"],
                "worktree archive title",
            )
            self.assertEqual(artifact["mode"], "initial-worktree-derived")
            self.assertTrue(artifact["worktree_derived"])
            self.assertTrue(artifact["archive_cache_reuse_disabled"])
            self.assertEqual(
                artifact["worktree_derived_paths"],
                expected_dirty_paths,
            )
            self.assertNotIn(
                unrelated.relative_to(fixture.root).as_posix(),
                artifact["worktree_derived_paths"],
            )
            self.assertIn(
                "initial worktree-derived proof accepted",
                stdout.getvalue(),
            )
            self.assertEqual(artifact["archive_source_skip_count"], 0)
            self.assertTrue(
                artifact["archive_cache_action"].startswith(
                    "not-written: initial worktree-derived"
                )
            )
            self.assertFalse(fixture.cache_jsonl.exists())
            self.assertFalse(fixture.cache_meta.exists())

    def test_dirty_full_apply_proves_exact_bytes_and_refuses_authority(
        self,
    ) -> None:
        """fd306ca8: dirty output has a distinct exact, local-only receipt."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(
                Path(tmp),
                current_count=1,
                archive_count=1,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                fixture.prime()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            ratchet_path = (
                fixture.root
                / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
            )
            clean_meta = json.loads(meta_path.read_text(encoding="utf-8"))

            uid = fixture.current_uids[0]
            source = fixture.files / f"{uid}.md"
            dirty_title = "UNCOMMITTED TITLE PROBE"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    f"fixture {uid}",
                    dirty_title,
                ),
                encoding="utf-8",
            )
            expected_receipt = [{
                "content_sha256": hashlib.sha256(
                    rebuild._parser_canonical_derivation_bytes(
                        source,
                        source.read_bytes(),
                    )
                ).hexdigest(),
                "mode": "100644",
                "path": source.relative_to(fixture.root).as_posix(),
                "symlink_target_sha256": None,
            }]

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    rebuild.rebuild_index(fixture.root, True),
                    0,
                )

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            ratchet = json.loads(ratchet_path.read_text(encoding="utf-8"))
            sqlite_evidence = index_surfaces._load_sqlite_ratchet_evidence(
                fixture.root
            )
            artifact = json.loads(
                fixture.run_artifact.read_text(encoding="utf-8")
            )
            inventory = meta["source_inventory"]
            expected_authorities = {
                "federation": False,
                "local": True,
                "ratchet_baseline": False,
                "release": False,
            }

            rows = index_surfaces.load_index_records(
                fixture.root,
                include_archive=True,
                require_complete_union=True,
            )
            self.assertEqual(
                {row["uid"]: row["title"] for row in rows}[uid],
                dirty_title,
            )
            self.assertNotEqual(
                clean_meta["source_inventory"]["sha256"],
                inventory["sha256"],
            )
            self.assertTrue(meta["derived_from_uncommitted"])
            self.assertTrue(inventory["derived_from_uncommitted"])
            self.assertEqual(
                inventory["uncommitted_inputs"],
                expected_receipt,
            )
            self.assertEqual(
                inventory["authoritative_for"],
                expected_authorities,
            )
            for evidence in (ratchet, sqlite_evidence):
                self.assertEqual(evidence["source_inventory"], inventory)
            self.assertTrue(artifact["derived_from_uncommitted"])
            self.assertEqual(
                artifact["uncommitted_inputs"],
                expected_receipt,
            )
            self.assertEqual(
                artifact["source_inventory_sha256"],
                inventory["sha256"],
            )
            self.assertEqual(
                artifact["authoritative_for"],
                expected_authorities,
            )
            self.assertNotIn(dirty_title, json.dumps(inventory))
            self.assertNotIn(dirty_title, json.dumps(artifact))
            for entry in meta["surfaces"].values():
                self.assertEqual(
                    entry["protected_record_count"],
                    entry["record_count"],
                )
            for purpose in ("federation", "ratchet_baseline", "release"):
                with self.subTest(purpose=purpose), self.assertRaisesRegex(
                    index_surfaces.IndexSurfaceRefusal,
                    purpose,
                ):
                    index_surfaces.load_index_records(
                        fixture.root,
                        include_archive=True,
                        require_complete_union=True,
                        require_authoritative=True,
                        authority_purpose=purpose,
                    )
            trusted_meta_bytes = meta_path.read_bytes()
            forged = json.loads(trusted_meta_bytes)
            forged["derived_from_uncommitted"] = False
            forged["source_inventory"]["derived_from_uncommitted"] = False
            forged["source_inventory"]["uncommitted_inputs"] = []
            for purpose in ("federation", "ratchet_baseline", "release"):
                forged["source_inventory"]["authoritative_for"][purpose] = True
            forged["pair_sha256"] = index_surfaces._surface_meta_digest(forged)
            meta_path.write_text(
                json.dumps(forged, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                index_surfaces.IndexSurfaceRefusal,
                "transaction-bound provenance",
            ):
                index_surfaces.load_index_records(
                    fixture.root,
                    include_archive=True,
                    require_complete_union=True,
                    require_authoritative=True,
                )
            meta_path.write_bytes(trusted_meta_bytes)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    rebuild.rebuild_index(fixture.root, True),
                    0,
                )
            repeated_meta = json.loads(
                meta_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                repeated_meta["source_inventory"]["sha256"],
                inventory["sha256"],
            )
            self.assertEqual(
                repeated_meta["source_inventory"]["uncommitted_inputs"],
                expected_receipt,
            )

    def test_parser_canonical_navblock_proof_and_global_only_authority(
        self,
    ) -> None:
        """evt #18: semantic manifest deltas, not Git dirt, gate --only."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(
                Path(tmp),
                current_count=2,
                archive_count=1,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                fixture.prime()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            clean_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            clean_inventory = clean_meta["source_inventory"]
            self.assertEqual(clean_inventory["schema_version"], 3)
            self.assertEqual(
                clean_inventory["source_path_count"],
                len(clean_inventory["collected_source_paths"]),
            )
            self.assertEqual(
                clean_inventory["tracked_source_count"],
                len(clean_inventory["collected_source_paths"]),
            )
            self.assertEqual(
                clean_inventory["manifest"],
                sorted(
                    clean_inventory["manifest"],
                    key=lambda entry: (
                        entry["kind"],
                        entry["path"],
                        entry["mode"],
                        entry["content_sha256"],
                    ),
                ),
            )

            uid_a, uid_b = fixture.current_uids
            source_a = fixture.files / f"{uid_a}.md"
            source_b = fixture.files / f"{uid_b}.md"
            original_b = source_b.read_bytes()
            navblock = (
                b"<!-- nav-block:start -->\n"
                b"viewer-only private chrome\n"
                b"<!-- nav-block:end -->\n\n"
            )
            with_navblock = original_b.replace(
                b"---\n\n",
                b"---\n\n" + navblock,
                1,
            )
            self.assertEqual(
                rebuild._parser_canonical_derivation_bytes(
                    source_b,
                    with_navblock,
                ),
                original_b,
            )
            source_b.write_bytes(with_navblock)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
            navblock_meta = json.loads(
                meta_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                navblock_meta["source_inventory"]["sha256"],
                clean_inventory["sha256"],
            )
            self.assertFalse(navblock_meta["derived_from_uncommitted"])
            self.assertNotIn(
                "viewer-only private chrome",
                json.dumps(navblock_meta),
            )
            self.assertEqual(
                rebuild.freshen_one(uid_a, fixture.root),
                0,
                "unrelated navblock-only chrome is not a semantic delta",
            )

            # A committed B change is clean relative to HEAD but stale relative
            # to the trusted pair. --only A must name B and preserve all bytes.
            source_b.write_bytes(original_b.replace(
                f"fixture {uid_b}".encode(),
                b"committed B title",
            ))
            _git(fixture.root, "add", str(source_b.relative_to(fixture.root)))
            _git(fixture.root, "commit", "-q", "-m", "commit B semantic change")
            participants = (
                fixture.current_surface,
                fixture.archive_surface,
                fixture.root / "vault" / "00-index.sqlite",
                meta_path,
                fixture.root / index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
            )
            before = tuple(path.read_bytes() for path in participants)
            stderr = io.StringIO()
            # AMENDED 2026-08-06 (metis-g103) under Mike's ruling: a semantic
            # delta in ANOTHER source (source_b) no longer gates this write.
            # Detecting that a file drifted from its record is a read-time
            # question answered by the full rebuild — the architecture review
            # says hand-edits are caught DOWNSTREAM, and this restores that.
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.freshen_one(uid_a, fixture.root), 0)
            # The surfaces now DO advance -- the write happened, which is the
            # point. What still matters is that the write advanced A only and
            # did not silently adopt B's uncommitted edit; the full apply below
            # is what brings B in, and it still asserts exactly that.
            rows_after_incremental = index_surfaces.load_index_records(
                fixture.root,
                include_archive=True,
                require_complete_union=True,
            )
            self.assertNotEqual(
                {row["uid"]: row["title"] for row in rows_after_incremental}[uid_b],
                "committed B title",
                "an incremental write of A must not have re-derived B",
            )

            # A full apply is the cure and updates B plus the trusted manifest.
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
            rows = index_surfaces.load_index_records(
                fixture.root,
                include_archive=True,
                require_complete_union=True,
            )
            self.assertEqual(
                {row["uid"]: row["title"] for row in rows}[uid_b],
                "committed B title",
            )

            # Real title/frontmatter/body WIP on A and body WIP on B all enter a
            # dirty full apply, with canonical hash-only receipts and output.
            source_a.write_text(
                source_a.read_text(encoding="utf-8")
                .replace(f"fixture {uid_a}", "dirty A title")
                .replace("type: note\n", "type: note\nowner: dirty-owner\ntags: [proof]\n")
                + "\nPRIVATE_BODY_PROBE_A\n",
                encoding="utf-8",
            )
            source_b.write_text(
                source_b.read_text(encoding="utf-8")
                + "\nPRIVATE_BODY_PROBE_B\n",
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
            dirty_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertNotEqual(
                dirty_meta["source_inventory"]["sha256"],
                navblock_meta["source_inventory"]["sha256"],
            )
            receipts = dirty_meta["source_inventory"]["uncommitted_inputs"]
            self.assertEqual(
                [receipt["path"] for receipt in receipts],
                sorted([
                    source_a.relative_to(fixture.root).as_posix(),
                    source_b.relative_to(fixture.root).as_posix(),
                ]),
            )
            serialized = json.dumps(dirty_meta)
            self.assertNotIn(str(fixture.root), serialized)
            self.assertNotIn("PRIVATE_BODY_PROBE", serialized)
            dirty_rows = {
                row["uid"]: row
                for row in index_surfaces.load_index_records(
                    fixture.root,
                    include_archive=True,
                    require_complete_union=True,
                )
            }
            self.assertEqual(dirty_rows[uid_a]["title"], "dirty A title")
            self.assertEqual(dirty_rows[uid_a]["owner"], "dirty-owner")
            self.assertEqual(dirty_rows[uid_a]["tags"], ["proof"])
            with sqlite3.connect(fixture.root / "vault" / "00-index.sqlite") as connection:
                body = connection.execute(
                    "SELECT body FROM entries_fts WHERE uid = ?",
                    (uid_a,),
                ).fetchone()[0]
            self.assertIn("PRIVATE_BODY_PROBE_A", body)

            # Once full apply has accounted for B, unchanged B dirt is valid:
            # a further A-only semantic change is the sole manifest delta.
            source_a.write_text(
                source_a.read_text(encoding="utf-8").replace(
                    "dirty A title",
                    "dirty A title v2",
                ),
                encoding="utf-8",
            )
            self.assertEqual(rebuild.freshen_one(uid_a, fixture.root), 0)

            # AMENDED 2026-08-06 (metis-g103) under Mike's ruling. This whole
            # section asserted that a B change, a rename, a deletion or a
            # derivation-code change each BLOCK an A-only write and name the
            # global blocker. None of them block it now: saving one file does
            # not prove the whole vault. Each is still caught by the full
            # rebuild that follows it here, which is the contract that replaced
            # the refusal -- detection downstream, not a gate on every write.
            source_b.write_text(
                source_b.read_text(encoding="utf-8") + "new B delta\n",
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.freshen_one(uid_a, fixture.root), 0)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)

            renamed_b = source_b.with_name(f"{uid_b}-renamed.md")
            source_b.rename(renamed_b)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.freshen_one(uid_a, fixture.root), 0)
            renamed_b.rename(source_b)

            saved_b = source_b.read_bytes()
            source_b.unlink()
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.freshen_one(uid_a, fixture.root), 0)
            source_b.write_bytes(saved_b)

            code_path = (
                fixture.root / "vault" / "tools" / "lib" / "gardener.py"
            )
            code_path.parent.mkdir(parents=True)
            code_path.write_text("# uncommitted derivation code\n", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                # Derivation CODE changing still blocks: if the gardener changed,
                # every existing row may be stale. Inputs are re-hashed fresh
                # (8 files) while sources are inherited (6,140).
                self.assertEqual(rebuild.freshen_one(uid_a, fixture.root), 1)
            self.assertIn("vault/tools/lib/gardener.py", stderr.getvalue())
            self.assertIn("full --apply", stderr.getvalue())
            code_path.unlink()

            attributes = fixture.root / ".gitattributes"
            attributes.write_text("*.md text\n", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                # INPUT class, like the gardener above: .gitattributes governs
                # how bytes are canonicalized, so a change to it can restate
                # every existing row. Still blocks.
                self.assertEqual(rebuild.freshen_one(uid_a, fixture.root), 1)
            self.assertIn(".gitattributes", stderr.getvalue())
            attributes.unlink()

            compose_lock = (
                fixture.root / rebuild.shard_index.COMPOSE_LOCK_REL
            )
            compose_lock.parent.mkdir(parents=True, exist_ok=True)
            compose_lock.write_text('{"vaults":{}}\n', encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                # INPUT class: the compose lock pins which vaults compose into
                # this index. Still blocks.
                self.assertEqual(rebuild.freshen_one(uid_a, fixture.root), 1)
            self.assertIn(".tropo-studio/compose.lock", stderr.getvalue())

    def test_current_like_clean_only_and_mint_smoke_with_navblock_filter(
        self,
    ) -> None:
        """P0 smoke: canonical mint can create its source and freshen in-gesture."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(
                Path(tmp),
                current_count=1,
                archive_count=1,
            )
            tools = fixture.root / "vault" / "tools"
            capsules = fixture.root / "vault" / "capsules"
            tools.mkdir(parents=True)
            capsules.mkdir(parents=True)
            for name in (
                "tropo-generate-mint-registry.py",
                "tropo-generate-relations-header.py",
                "tropo-mint-id.py",
                "tropo-navblock-strip.py",
                "tropo-rebuild-index.py",
            ):
                shutil.copy2(TOOLS_DIR / name, tools / name)
            shutil.copytree(TOOLS_DIR / "lib", tools / "lib")
            shutil.copy2(
                Path(__file__).resolve().parents[2]
                / "capsules"
                / "tropo-note.capsule.md",
                capsules / "tropo-note.capsule.md",
            )
            templates = capsules / "templates"
            templates.mkdir()
            shutil.copy2(
                Path(__file__).resolve().parents[2]
                / "capsules"
                / "templates"
                / "note.template.md",
                templates / "note.template.md",
            )
            registry_result = subprocess.run(
                [
                    sys.executable,
                    str(tools / "tropo-generate-mint-registry.py"),
                    "--vault-path",
                    str(fixture.root),
                ],
                cwd=fixture.root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(
                registry_result.returncode,
                0,
                registry_result.stdout + registry_result.stderr,
            )
            attributes = fixture.root / ".gitattributes"
            attributes.write_text(
                "vault/files/*.md filter=navblockstrip\n",
                encoding="utf-8",
            )
            _git(
                fixture.root,
                "config",
                "filter.navblockstrip.clean",
                f"{sys.executable} {tools / 'tropo-navblock-strip.py'} --clean",
            )
            _git(
                fixture.root,
                "config",
                "filter.navblockstrip.required",
                "true",
            )
            _git(
                fixture.root,
                "add",
                ".gitattributes",
                "vault/tools",
                "vault/capsules",
            )
            _git(fixture.root, "commit", "-q", "-m", "install mint smoke tools")
            with contextlib.redirect_stdout(io.StringIO()):
                fixture.prime()

            uid = fixture.current_uids[0]
            self.assertEqual(
                rebuild.freshen_one(uid, fixture.root),
                0,
                "current-like clean --only must remain available",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(tools / "tropo-mint-id.py"),
                    "--type",
                    "note",
                    "--author",
                    "index-lifecycle-test",
                ],
                cwd=fixture.root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(
                result.returncode,
                0,
                result.stdout + result.stderr,
            )
            self.assertNotIn("source-first orphan", result.stderr)
            minted_uid = result.stdout.splitlines()[0].strip()
            minted_path = fixture.files / f"{minted_uid}.md"
            self.assertTrue(minted_path.is_file())
            rows = index_surfaces.load_index_records(
                fixture.root,
                include_archive=True,
                require_complete_union=True,
            )
            self.assertIn(minted_uid, {row.get("uid") for row in rows})
            with sqlite3.connect(
                fixture.root / "vault" / "00-index.sqlite"
            ) as connection:
                self.assertIsNotNone(connection.execute(
                    "SELECT 1 FROM entries WHERE uid = ?",
                    (minted_uid,),
                ).fetchone())

    def test_fresh_clone_deleted_tracked_source_refuses_without_minting_state(
        self,
    ) -> None:
        """G97 B: initial dirty exception covers no tracked deletion/type loss."""
        for damage in ("deleted", "type-loss"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as tmp:
                fixture = FixtureStudio(
                    Path(tmp),
                    current_count=1,
                    archive_count=1,
                )
                source = fixture.files / f"{fixture.archive_uids[0]}.md"
                source.unlink()
                if damage == "type-loss":
                    source.symlink_to(f"{fixture.current_uids[0]}.md")
                (fixture.root / "scratch-not-a-source.txt").write_text(
                    "untracked non-governed note\n",
                    encoding="utf-8",
                )
                participants = (
                    fixture.current_surface,
                    fixture.archive_surface,
                    fixture.root / "vault" / "00-index.sqlite",
                    fixture.root
                    / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
                    fixture.root / index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
                )

                stderr = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), (
                    contextlib.redirect_stderr(stderr)
                ):
                    rc = rebuild.rebuild_index(fixture.root, True)

                refusal = stderr.getvalue()
                self.assertEqual(rc, 1)
                self.assertIn(
                    source.relative_to(fixture.root).as_posix(),
                    refusal,
                )
                self.assertIn(
                    (
                        "deleted tracked source/input"
                        if damage == "deleted"
                        else "invalid worktree mode"
                    ),
                    refusal,
                )
                self.assertIn("Land, revert, or isolate", refusal)
                self.assertTrue(
                    all(not path.exists() for path in participants)
                )
                self.assertFalse(fixture.run_artifact.exists())

    def test_partial_restore_cannot_mint_empty_archive_metadata(self) -> None:
        """Missing archive+cache plus a skipped archive source refuses all writes."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=1)
            fixture.prime()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"
            fixture.archive_surface.unlink()
            fixture.cache_jsonl.unlink()
            fixture.cache_meta.unlink()
            before = (
                fixture.current_surface.read_bytes(),
                meta_path.read_bytes(),
                sqlite_path.read_bytes(),
            )
            archived_source = fixture.files / f"{fixture.archive_uids[0]}.md"
            real_skip = rebuild._skip_cached_archive_source

            def skip_archived(path, vault_root, skip_paths):
                if path == archived_source:
                    return True
                return real_skip(path, vault_root, skip_paths)

            stderr = io.StringIO()
            with mock.patch.object(
                rebuild,
                "_skip_cached_archive_source",
                side_effect=skip_archived,
            ), contextlib.redirect_stderr(stderr):
                rc = rebuild.rebuild_index(fixture.root, True)

            self.assertEqual(rc, 1)
            self.assertIn("full source-complete derivation proof", stderr.getvalue())
            self.assertFalse(fixture.archive_surface.exists())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    meta_path.read_bytes(),
                    sqlite_path.read_bytes(),
                ),
                before,
            )

    def test_deleted_or_truncated_tracked_source_cannot_certify_absent_archive(
        self,
    ) -> None:
        """Talos #8428: source inventory, not shortcut absence, proves complete."""
        for damage in ("deleted", "truncated"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as tmp:
                fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=2)
                fixture.prime()
                meta_path = (
                    fixture.root
                    / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
                )
                sqlite_path = fixture.root / "vault" / "00-index.sqlite"
                fixture.archive_surface.unlink()
                fixture.cache_jsonl.unlink()
                fixture.cache_meta.unlink()
                before = (
                    fixture.current_surface.read_bytes(),
                    meta_path.read_bytes(),
                    sqlite_path.read_bytes(),
                )
                source = fixture.files / f"{fixture.archive_uids[0]}.md"
                if damage == "deleted":
                    source.unlink()
                else:
                    source.write_bytes(b"")

                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    rc = rebuild.rebuild_index(fixture.root, True)

                self.assertEqual(rc, 1)
                if damage == "deleted":
                    self.assertIn(
                        "[SOURCE COMPLETENESS] proof unavailable",
                        stderr.getvalue(),
                    )
                self.assertIn(
                    "full source-complete derivation proof",
                    stderr.getvalue(),
                )
                self.assertFalse(fixture.archive_surface.exists())
                self.assertEqual(
                    (
                        fixture.current_surface.read_bytes(),
                        meta_path.read_bytes(),
                        sqlite_path.read_bytes(),
                    ),
                    before,
                )

    def test_reconcile_names_all_source_blockers_and_ignores_runtime_state(
        self,
    ) -> None:
        """Full reconcile refuses with every exact land/revert/isolate path."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=2)
            runtime = fixture.root / "vault" / "events" / "receipts" / "r.json"
            runtime.parent.mkdir(parents=True)
            runtime.write_text('{"sequence":1}\n', encoding="utf-8")
            _git(fixture.root, "add", runtime.relative_to(fixture.root).as_posix())
            _git(fixture.root, "commit", "-qm", "tracked runtime receipt")
            fixture.prime()

            tracked = fixture.files / f"{fixture.current_uids[0]}.md"
            tracked_before = tracked.read_bytes()
            tracked.write_bytes(tracked_before + b"\nblocking source edit\n")
            untracked = fixture.files / "deadbeef.md"
            untracked.write_text(
                _entry_text("deadbeef", state="active", status="active"),
                encoding="utf-8",
            )
            runtime.write_text('{"sequence":2}\n', encoding="utf-8")
            participants_before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                (fixture.root / "vault" / "00-index.sqlite").read_bytes(),
                (
                    fixture.root
                    / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
                ).read_bytes(),
                (
                    fixture.root
                    / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
                ).read_bytes(),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), (
                contextlib.redirect_stderr(stderr)
            ):
                self.assertEqual(
                    rebuild.rebuild_index(
                        fixture.root,
                        True,
                        reconcile=True,
                    ),
                    1,
                )
            refusal = stderr.getvalue()
            self.assertIn("Land, revert, or isolate", refusal)
            self.assertIn(tracked.relative_to(fixture.root).as_posix(), refusal)
            self.assertIn(untracked.relative_to(fixture.root).as_posix(), refusal)
            self.assertNotIn(runtime.relative_to(fixture.root).as_posix(), refusal)
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    (fixture.root / "vault" / "00-index.sqlite").read_bytes(),
                    (
                        fixture.root
                        / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
                    ).read_bytes(),
                    (
                        fixture.root
                        / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
                    ).read_bytes(),
                ),
                participants_before,
            )

            tracked.write_bytes(tracked_before)
            untracked.unlink()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    rebuild.rebuild_index(
                        fixture.root,
                        True,
                        reconcile=True,
                    ),
                    0,
                )

    def test_reconcile_cannot_shrink_1789_to_1289_without_uid_authority(
        self,
    ) -> None:
        """Talos #8460: derivation mode and shrink authority are independent."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(
                Path(tmp),
                current_count=1,
                archive_count=1789,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                fixture.prime()
            for uid in fixture.archive_uids[:500]:
                (fixture.files / f"{uid}.md").unlink()
            fixture.commit_sources("reviewed 1789 to 1289 archive reduction")
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            ratchet_path = (
                fixture.root
                / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
            )
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
                meta_path.read_bytes(),
                ratchet_path.read_bytes(),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), (
                contextlib.redirect_stderr(stderr)
            ):
                self.assertEqual(
                    rebuild.rebuild_index(
                        fixture.root,
                        True,
                        reconcile=True,
                    ),
                    1,
                )
            shrink_refusal = stderr.getvalue()
            self.assertIn("1789 to 1289", shrink_refusal)
            self.assertIn("--allow-index-shrink", shrink_refusal)
            self.assertIn("--shrink-authorization-uid", shrink_refusal)
            self.assertIn("--shrink-evidence-uid", shrink_refusal)
            self.assertNotIn("reconcile", shrink_refusal.lower())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                    meta_path.read_bytes(),
                    ratchet_path.read_bytes(),
                ),
                before,
            )

            argv = [
                "tropo-rebuild-index.py",
                "--apply",
                "--reconcile",
                "--skip-rehydrate",
                "--vault-path",
                str(fixture.root),
                "--allow-index-shrink",
                "--shrink-authorization-uid",
                "a142a006",
                "--shrink-evidence-uid",
                "84608431",
            ]
            unrelated = fixture.files / f"{fixture.current_uids[0]}.md"
            unrelated_before = unrelated.read_bytes()
            unrelated.write_bytes(
                unrelated_before + b"\nunrelated incomplete source\n"
            )
            stderr = io.StringIO()
            with mock.patch.object(sys, "argv", argv), (
                contextlib.redirect_stdout(io.StringIO())
            ), contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.main(), 1)
            self.assertIn(
                unrelated.relative_to(fixture.root).as_posix(),
                stderr.getvalue(),
            )
            self.assertIn("Land, revert, or isolate", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                    meta_path.read_bytes(),
                    ratchet_path.read_bytes(),
                ),
                before,
            )
            unrelated.write_bytes(unrelated_before)
            with mock.patch.object(sys, "argv", argv), (
                contextlib.redirect_stdout(io.StringIO())
            ):
                self.assertEqual(rebuild.main(), 0)
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            archive_meta = meta["surfaces"][
                index_surfaces.ARCHIVE_INDEX_NAME
            ]
            self.assertEqual(archive_meta["record_count"], 1289)
            self.assertEqual(archive_meta["protected_record_count"], 1289)
            reason = archive_meta["baseline_advance"]["reason"]
            self.assertIn("authorization_uid=a142a006", reason)
            self.assertIn("evidence_uid=84608431", reason)

    def test_authorized_floor_update_is_exact_then_growth_restores_high_water(
        self,
    ) -> None:
        """G97 floor rule: adjudicated 3018 is exact; later 3019 is high-water."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            vault = root / "vault"
            vault.mkdir()
            (root / ".tropo").mkdir()
            current_path = vault / index_surfaces.CURRENT_INDEX_NAME
            archive_path = vault / index_surfaces.ARCHIVE_INDEX_NAME
            sqlite_path = vault / "00-index.sqlite"
            current_rows = [
                {"uid": f"{index + 1:08x}", "state": "active"}
                for index in range(3019)
            ]
            reduced_rows = current_rows[:-1]
            proof = index_surfaces.prove_full_source_derivation(
                current_rows,
                [],
                source_complete=True,
                source_inventory=tuple(
                    (
                        f"vault/files/{row['uid']}.md",
                        "100644",
                        f"{index + 1:040x}",
                    )
                    for index, row in enumerate(current_rows)
                ),
            )
            base_sqlite = root / "base.sqlite"
            with sqlite3.connect(base_sqlite) as connection:
                connection.execute("CREATE TABLE fixture (value INTEGER)")
            sqlite_raw = base_sqlite.read_bytes()
            base_sqlite.unlink()
            index_surfaces.write_jsonl_pair_atomic(
                (
                    (current_path, current_rows),
                    (archive_path, []),
                ),
                companion_replacements=((sqlite_path, sqlite_raw),),
                full_source_derivation_proof=proof,
                surface_metadata_recovery_reason=(
                    "test-source-complete-initialization"
                ),
            )
            meta_path = (
                root / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )

            def current_meta() -> dict:
                return json.loads(
                    meta_path.read_text(encoding="utf-8")
                )["surfaces"][index_surfaces.CURRENT_INDEX_NAME]

            index_surfaces.write_jsonl_pair_atomic(
                (
                    (current_path, reduced_rows),
                    (archive_path, []),
                ),
                companion_replacements=(
                    (sqlite_path, sqlite_path.read_bytes()),
                ),
            )
            self.assertEqual(current_meta()["record_count"], 3018)
            self.assertEqual(current_meta()["protected_record_count"], 3019)

            authorization = index_surfaces.GovernedShrinkAuthorization(
                authorization_uid="a142a007",
                evidence_uid="8508f001",
            )
            index_surfaces.write_jsonl_pair_atomic(
                (
                    (current_path, reduced_rows),
                    (archive_path, []),
                ),
                allow_shrink=True,
                companion_replacements=(
                    (sqlite_path, sqlite_path.read_bytes()),
                ),
                governed_shrink_authorization=authorization,
            )
            adjudicated = current_meta()
            self.assertEqual(adjudicated["record_count"], 3018)
            self.assertEqual(adjudicated["protected_record_count"], 3018)
            self.assertEqual(adjudicated["baseline_advance"]["from"], 3019)
            self.assertEqual(adjudicated["baseline_advance"]["to"], 3018)
            self.assertIn(
                "authorization_uid=a142a007",
                adjudicated["baseline_advance"]["reason"],
            )
            for evidence in (
                json.loads(
                    (
                        root
                        / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
                    ).read_text(encoding="utf-8")
                ),
                index_surfaces._load_sqlite_ratchet_evidence(root),
            ):
                self.assertEqual(
                    evidence["surfaces"][
                        index_surfaces.CURRENT_INDEX_NAME
                    ]["protected_record_count"],
                    3018,
                )

            index_surfaces.write_jsonl_pair_atomic(
                (
                    (current_path, current_rows),
                    (archive_path, []),
                ),
                companion_replacements=(
                    (sqlite_path, sqlite_path.read_bytes()),
                ),
            )
            grown = current_meta()
            self.assertEqual(grown["protected_record_count"], 3019)
            self.assertEqual(
                grown["baseline_advance"],
                {
                    "from": 3018,
                    "to": 3019,
                    "reason": "growth-high-water",
                },
            )

            index_surfaces.write_jsonl_pair_atomic(
                (
                    (current_path, reduced_rows),
                    (archive_path, []),
                ),
                companion_replacements=(
                    (sqlite_path, sqlite_path.read_bytes()),
                ),
            )
            ratcheted = current_meta()
            self.assertEqual(ratcheted["record_count"], 3018)
            self.assertEqual(ratcheted["protected_record_count"], 3019)

    def test_exact_ten_percent_shrink_refuses_all_participants(self) -> None:
        """The 10.0% boundary is inclusive and preserves pair metadata + SQLite."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=10)
            fixture.prime()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                meta_path.read_bytes(),
                sqlite_path.read_bytes(),
            )
            (fixture.files / f"{fixture.archive_uids[0]}.md").unlink()
            fixture.commit_sources("remove exactly one of ten archive sources")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = rebuild.rebuild_index(fixture.root, True)

            self.assertEqual(rc, 1)
            self.assertIn("10.0%", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    meta_path.read_bytes(),
                    sqlite_path.read_bytes(),
                ),
                before,
            )

    def test_cumulative_shrink_ratchet_refuses_and_recovers_across_crash(
        self,
    ) -> None:
        """Thirty drops cannot reach 52; crash preserves all three floor copies."""
        class SimulatedInterruption(BaseException):
            pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            vault = root / "vault"
            vault.mkdir()
            current_path = vault / index_surfaces.CURRENT_INDEX_NAME
            archive_path = vault / index_surfaces.ARCHIVE_INDEX_NAME
            sqlite_path = vault / "00-index.sqlite"
            current_rows = [{"uid": "00000001", "state": "active"}]
            archive_rows = [
                {"uid": f"{0x10000000 + index:08x}", "state": "archived"}
                for index in range(100)
            ]
            _write_jsonl(current_path, current_rows)
            _write_jsonl(archive_path, archive_rows)
            with sqlite3.connect(sqlite_path) as connection:
                connection.execute(
                    "CREATE TABLE fixture_payload(uid TEXT PRIMARY KEY)"
                )
            _initialize_trusted_pair(
                current_path,
                archive_path,
                current_rows,
                archive_rows,
            )
            meta_path = root / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            ratchet_path = root / index_surfaces.INDEX_RATCHET_RELATIVE_PATH

            accepted = 0
            refused = 0
            for round_number in range(1, 31):
                target_count = max(52, 100 - (round_number * 2))
                candidate = archive_rows[:target_count]
                try:
                    index_surfaces.write_jsonl_pair_atomic(
                        (
                            (current_path, current_rows),
                            (archive_path, candidate),
                        )
                    )
                except index_surfaces.IndexSurfaceRefusal:
                    refused += 1
                    continue
                archive_rows = candidate
                accepted += 1

            self.assertLess(accepted, 30)
            self.assertGreater(refused, 0)
            self.assertEqual(len(archive_rows), 92)
            self.assertGreater(len(archive_rows), 52)
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            archive_meta = meta["surfaces"][index_surfaces.ARCHIVE_INDEX_NAME]
            self.assertEqual(archive_meta["record_count"], 92)
            self.assertEqual(archive_meta["protected_record_count"], 100)

            refused_before = (
                current_path.read_bytes(),
                archive_path.read_bytes(),
                sqlite_path.read_bytes(),
                meta_path.read_bytes(),
                ratchet_path.read_bytes(),
            )
            with self.assertRaises(index_surfaces.IndexSurfaceRefusal):
                index_surfaces.write_jsonl_pair_atomic(
                    (
                        (current_path, current_rows),
                        (archive_path, archive_rows[:90]),
                    )
                )
            self.assertEqual(
                (
                    current_path.read_bytes(),
                    archive_path.read_bytes(),
                    sqlite_path.read_bytes(),
                    meta_path.read_bytes(),
                    ratchet_path.read_bytes(),
                ),
                refused_before,
            )

            adjudicated_rows = archive_rows[:10]
            index_surfaces.write_jsonl_pair_atomic(
                (
                    (current_path, current_rows),
                    (archive_path, adjudicated_rows),
                ),
                allow_shrink=True,
            )
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            archive_meta = meta["surfaces"][index_surfaces.ARCHIVE_INDEX_NAME]
            self.assertEqual(archive_meta["protected_record_count"], 10)
            self.assertEqual(
                archive_meta["baseline_advance"]["reason"],
                "explicit-adjudicated-shrink-override",
            )
            with self.assertRaises(index_surfaces.IndexSurfaceRefusal):
                index_surfaces.write_jsonl_pair_atomic(
                    (
                        (current_path, current_rows),
                        (archive_path, adjudicated_rows[:9]),
                    )
                )

            before_crash = (
                current_path.read_bytes(),
                archive_path.read_bytes(),
                sqlite_path.read_bytes(),
                meta_path.read_bytes(),
                ratchet_path.read_bytes(),
            )
            real_replace = index_surfaces.os.replace

            def interrupt_ratchet_swap(src, dst):
                if Path(dst) == ratchet_path:
                    raise SimulatedInterruption()
                return real_replace(src, dst)

            with mock.patch.object(
                index_surfaces.os,
                "replace",
                side_effect=interrupt_ratchet_swap,
            ):
                with self.assertRaises(SimulatedInterruption):
                    index_surfaces.write_jsonl_pair_atomic(
                        (
                            (current_path, current_rows),
                            (archive_path, adjudicated_rows[:5]),
                        ),
                        allow_shrink=True,
                    )
            index_surfaces.recover_pending_index_transaction(root)
            self.assertEqual(
                (
                    current_path.read_bytes(),
                    archive_path.read_bytes(),
                    sqlite_path.read_bytes(),
                    meta_path.read_bytes(),
                    ratchet_path.read_bytes(),
                ),
                before_crash,
            )
            sqlite_evidence = index_surfaces._load_sqlite_ratchet_evidence(root)
            self.assertEqual(
                sqlite_evidence["surfaces"][
                    index_surfaces.ARCHIVE_INDEX_NAME
                ]["protected_record_count"],
                10,
            )

    def test_two_deleted_floor_files_recover_from_sqlite_without_lowering(
        self,
    ) -> None:
        """SQLite independently preserves 20 after sidecar+ratchet deletion."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=20)
            fixture.prime()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            ratchet_path = (
                fixture.root
                / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
            )
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"

            first_source = fixture.files / f"{fixture.archive_uids[0]}.md"
            first_source.unlink()
            fixture.commit_sources("first accepted sub-floor archive reduction")
            self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(
                meta["surfaces"][index_surfaces.ARCHIVE_INDEX_NAME][
                    "record_count"
                ],
                19,
            )
            self.assertEqual(
                meta["surfaces"][index_surfaces.ARCHIVE_INDEX_NAME][
                    "protected_record_count"
                ],
                20,
            )
            sqlite_evidence = index_surfaces._load_sqlite_ratchet_evidence(
                fixture.root
            )
            self.assertEqual(
                sqlite_evidence["surfaces"][
                    index_surfaces.ARCHIVE_INDEX_NAME
                ]["protected_record_count"],
                20,
            )

            meta_path.unlink()
            ratchet_path.unlink()
            preserved_without_file_copies = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
            )
            for mutate in (
                lambda: rebuild.freshen_one(
                    fixture.current_uids[0],
                    fixture.root,
                ),
                lambda: rebuild.rebuild_index(fixture.root, True),
            ):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(mutate(), 1)
                self.assertIn("source-complete reconcile", stderr.getvalue())
                self.assertFalse(meta_path.exists())
                self.assertFalse(ratchet_path.exists())
                self.assertEqual(
                    (
                        fixture.current_surface.read_bytes(),
                        fixture.archive_surface.read_bytes(),
                        sqlite_path.read_bytes(),
                    ),
                    preserved_without_file_copies,
                )

            self.assertEqual(
                rebuild.rebuild_index(fixture.root, True, reconcile=True),
                0,
            )
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            ratchet = json.loads(ratchet_path.read_text(encoding="utf-8"))
            archive_meta = meta["surfaces"][
                index_surfaces.ARCHIVE_INDEX_NAME
            ]
            self.assertEqual(archive_meta["record_count"], 19)
            self.assertEqual(archive_meta["protected_record_count"], 20)
            self.assertEqual(
                meta["metadata_recovery"]["sidecar_state"],
                "missing",
            )
            self.assertEqual(
                meta["metadata_recovery"]["ratchet_state"],
                "missing",
            )
            self.assertEqual(
                meta["metadata_recovery"]["sqlite_state"],
                "valid",
            )
            self.assertIn(
                "sqlite-ratchet",
                meta["metadata_recovery"]["evidence"],
            )
            self.assertEqual(ratchet["recovery_count"], 1)
            self.assertEqual(
                ratchet["surfaces"][index_surfaces.ARCHIVE_INDEX_NAME][
                    "protected_record_count"
                ],
                20,
            )
            sqlite_evidence = index_surfaces._load_sqlite_ratchet_evidence(
                fixture.root
            )
            self.assertEqual(
                sqlite_evidence["surfaces"][
                    index_surfaces.ARCHIVE_INDEX_NAME
                ]["protected_record_count"],
                20,
            )

            second_source = fixture.files / f"{fixture.archive_uids[1]}.md"
            second_source.unlink()
            fixture.commit_sources("second cumulative archive reduction")
            before_second_refusal = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
                meta_path.read_bytes(),
                ratchet_path.read_bytes(),
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 1)
            self.assertIn("10.0%", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                    meta_path.read_bytes(),
                    ratchet_path.read_bytes(),
                ),
                before_second_refusal,
            )

    def test_corrupt_sidecar_requires_named_reconcile_cure(self) -> None:
        """Valid duplicated floor evidence cannot make ordinary repair implicit."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            ratchet_path = (
                fixture.root
                / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
            )
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"
            meta_path.write_bytes(b'{"schema_version":3')
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
                meta_path.read_bytes(),
                ratchet_path.read_bytes(),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 1)
            self.assertIn("trusted index-surface metadata", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                    meta_path.read_bytes(),
                    ratchet_path.read_bytes(),
                ),
                before,
            )

            self.assertEqual(
                rebuild.rebuild_index(fixture.root, True, reconcile=True),
                0,
            )
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            ratchet = json.loads(ratchet_path.read_text(encoding="utf-8"))
            self.assertEqual(
                meta["metadata_recovery"]["sidecar_state"],
                "corrupt",
            )
            self.assertEqual(
                ratchet["last_metadata_recovery"]["sidecar_state"],
                "corrupt",
            )
            self.assertEqual(ratchet["recovery_count"], 1)

    def test_all_floor_evidence_loss_requires_governed_cli_recovery(self) -> None:
        """Neither ordinary nor reconcile may infer a floor after total loss."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=20)
            fixture.prime()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            ratchet_path = (
                fixture.root
                / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
            )
            sqlite_path = fixture.root / "vault" / "00-index.sqlite"

            first_source = fixture.files / f"{fixture.archive_uids[0]}.md"
            first_source.unlink()
            fixture.commit_sources("establish nineteen rows below floor twenty")
            self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)

            meta_path.unlink()
            ratchet_path.unlink()
            with sqlite3.connect(sqlite_path) as connection:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("DROP TABLE index_ratchet_metadata")
            evidence_loss_state = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 1)
            self.assertIn("source-complete reconcile", stderr.getvalue())
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(
                    rebuild.rebuild_index(
                        fixture.root,
                        True,
                        reconcile=True,
                    ),
                    1,
                )
            self.assertIn(
                "all cumulative index shrink-floor evidence",
                stderr.getvalue(),
            )
            self.assertFalse(meta_path.exists())
            self.assertFalse(ratchet_path.exists())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                ),
                evidence_loss_state,
            )

            def governed_recovery(floors: str) -> int:
                argv = [
                    "tropo-rebuild-index.py",
                    "--apply",
                    "--reconcile",
                    "--skip-rehydrate",
                    "--vault-path",
                    str(fixture.root),
                    "--recover-index-floors",
                    floors,
                    "--floor-recovery-evidence-uid",
                    "a142f005",
                ]
                with mock.patch.object(sys, "argv", argv):
                    return rebuild.main()

            unrelated = fixture.files / f"{fixture.current_uids[0]}.md"
            unrelated_before = unrelated.read_bytes()
            unrelated.write_bytes(
                unrelated_before + b"\nunrelated recovery blocker\n"
            )
            stderr = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), (
                contextlib.redirect_stderr(stderr)
            ):
                self.assertEqual(governed_recovery("1:20"), 1)
            self.assertIn(
                unrelated.relative_to(fixture.root).as_posix(),
                stderr.getvalue(),
            )
            self.assertIn("Land, revert, or isolate", stderr.getvalue())
            self.assertFalse(meta_path.exists())
            self.assertFalse(ratchet_path.exists())
            unrelated.write_bytes(unrelated_before)

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(governed_recovery("1:18"), 1)
            self.assertIn("below the observed 19 rows", stderr.getvalue())
            self.assertFalse(meta_path.exists())
            self.assertFalse(ratchet_path.exists())

            self.assertEqual(governed_recovery("1:20"), 0)
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            ratchet = json.loads(ratchet_path.read_text(encoding="utf-8"))
            sqlite_evidence = index_surfaces._load_sqlite_ratchet_evidence(
                fixture.root
            )
            for evidence in (meta, ratchet, sqlite_evidence):
                self.assertEqual(
                    evidence["surfaces"][
                        index_surfaces.ARCHIVE_INDEX_NAME
                    ]["protected_record_count"],
                    20,
                )
            governed = meta["metadata_recovery"][
                "governed_floor_recovery"
            ]
            self.assertEqual(
                governed["authorization_evidence_uid"],
                "a142f005",
            )
            self.assertEqual(
                governed["caller_supplied_protected_record_counts"][
                    index_surfaces.ARCHIVE_INDEX_NAME
                ],
                20,
            )

            second_source = fixture.files / f"{fixture.archive_uids[1]}.md"
            second_source.unlink()
            fixture.commit_sources("attempt exact ten percent after recovery")
            before_refusal = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                sqlite_path.read_bytes(),
                meta_path.read_bytes(),
                ratchet_path.read_bytes(),
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 1)
            self.assertIn("10.0%", stderr.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    sqlite_path.read_bytes(),
                    meta_path.read_bytes(),
                    ratchet_path.read_bytes(),
                ),
                before_refusal,
            )

    def test_conflicting_and_two_corrupt_copies_recover_max_sqlite_floor(
        self,
    ) -> None:
        """A lower conflict loses to max; two corrupt files heal from SQLite."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=1, archive_count=20)
            fixture.prime()
            meta_path = (
                fixture.root
                / index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH
            )
            ratchet_path = (
                fixture.root
                / index_surfaces.INDEX_RATCHET_RELATIVE_PATH
            )

            first_source = fixture.files / f"{fixture.archive_uids[0]}.md"
            first_source.unlink()
            fixture.commit_sources("establish protected floor twenty")
            self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)

            lower_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            lower_meta["surfaces"][index_surfaces.ARCHIVE_INDEX_NAME][
                "protected_record_count"
            ] = 19
            lower_meta["pair_sha256"] = index_surfaces._surface_meta_digest(
                lower_meta
            )
            meta_path.write_text(
                json.dumps(lower_meta, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 1)
            self.assertIn("cumulative index shrink-floor", stderr.getvalue())

            self.assertEqual(
                rebuild.rebuild_index(fixture.root, True, reconcile=True),
                0,
            )
            healed_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(
                healed_meta["surfaces"][
                    index_surfaces.ARCHIVE_INDEX_NAME
                ]["protected_record_count"],
                20,
            )

            meta_path.write_bytes(b'{"corrupt":')
            ratchet_path.write_bytes(b'{"corrupt":')
            self.assertEqual(
                rebuild.rebuild_index(fixture.root, True, reconcile=True),
                0,
            )
            healed_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            healed_ratchet = json.loads(
                ratchet_path.read_text(encoding="utf-8")
            )
            healed_sqlite = index_surfaces._load_sqlite_ratchet_evidence(
                fixture.root
            )
            self.assertEqual(
                healed_meta["metadata_recovery"]["sidecar_state"],
                "corrupt",
            )
            self.assertEqual(
                healed_meta["metadata_recovery"]["ratchet_state"],
                "corrupt",
            )
            self.assertEqual(
                healed_meta["metadata_recovery"]["sqlite_state"],
                "valid",
            )
            for evidence in (healed_meta, healed_ratchet, healed_sqlite):
                self.assertEqual(
                    evidence["surfaces"][
                        index_surfaces.ARCHIVE_INDEX_NAME
                    ]["protected_record_count"],
                    20,
                )

    def test_governing_current_only_pass_refuses_without_surface_mutation(self) -> None:
        """Criterion 3: literal destructive hazard, isolated from the live Studio."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = root / "vault" / "files"
            files.mkdir(parents=True)
            (root / ".tropo").mkdir()
            current_rows: list[dict] = []
            for index in range(20):
                uid = f"{index + 1:08x}"
                (files / f"{uid}.md").write_text(
                    _entry_text(uid, state="active", status="active"),
                    encoding="utf-8",
                )
                current_rows.append(
                    {
                        "uid": uid,
                        "type": "note",
                        "state": "active",
                        "status": "active",
                        "path": f"vault/files/{uid}.md",
                    }
                )
            archive_rows = [
                {
                    "uid": f"{0x20000000 + index:08x}",
                    "type": "note",
                    "state": "archived",
                    "status": "done",
                    "path": f"vault/files/{0x20000000 + index:08x}.md",
                }
                for index in range(20)
            ]
            current_surface = root / "vault" / index_surfaces.CURRENT_INDEX_NAME
            archive_surface = root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME
            _write_jsonl(current_surface, current_rows)
            _write_jsonl(archive_surface, archive_rows)
            before = (current_surface.read_bytes(), archive_surface.read_bytes())

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = rebuild.rebuild_index(root, True)

            self.assertNotEqual(rc, 0)
            self.assertIn("REFUSAL", stderr.getvalue())
            self.assertEqual(
                (current_surface.read_bytes(), archive_surface.read_bytes()),
                before,
            )

    def test_verified_reuse_skips_archived_parse_and_is_byte_identical(self) -> None:
        """Criteria 1 + 8: reuse is measured and preserves both projections."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
            )

            self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
            after = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
            )
            artifact = json.loads(fixture.run_artifact.read_text(encoding="utf-8"))

            self.assertEqual(after, before)
            self.assertEqual(artifact["archive_cache_action"], "reused")
            self.assertEqual(artifact["parsed_record_count"], 2)
            self.assertIsInstance(artifact["wall_clock_seconds"], (int, float))
            self.assertGreaterEqual(artifact["wall_clock_seconds"], 0)

    def test_local_archive_cache_survives_mounted_shard_retirement(self) -> None:
        """Shared shard cleanup discriminates cache kinds across three applies."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            actions = [
                json.loads(
                    fixture.run_artifact.read_text(encoding="utf-8")
                )["archive_cache_action"]
            ]
            local_cache_bytes = (
                fixture.cache_jsonl.read_bytes(),
                fixture.cache_meta.read_bytes(),
            )

            stale_uid = "deadbeef"
            rebuild.shard_index.write_shard(
                fixture.root,
                stale_uid,
                "stale-mounted-pin",
                [],
                "2026-07-26T00:00:00Z",
                derivation_identity={},
            )
            stale_paths = (
                rebuild.shard_index.shard_jsonl_path(fixture.root, stale_uid),
                rebuild.shard_index.shard_meta_path(fixture.root, stale_uid),
            )
            shards_dir = fixture.root / rebuild.shard_index.SHARDS_REL
            malformed_paths = (
                shards_dir / "unknown-cache.jsonl",
                shards_dir / "unknown-cache.meta",
            )
            malformed_paths[0].write_text("{}\n", encoding="utf-8")
            malformed_paths[1].write_text("{malformed", encoding="utf-8")

            for _ in range(2):
                self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
                actions.append(
                    json.loads(
                        fixture.run_artifact.read_text(encoding="utf-8")
                    )["archive_cache_action"]
                )
                self.assertEqual(
                    (
                        fixture.cache_jsonl.read_bytes(),
                        fixture.cache_meta.read_bytes(),
                    ),
                    local_cache_bytes,
                )

            self.assertEqual(actions, ["recreated", "reused", "reused"])
            self.assertTrue(all(not path.exists() for path in stale_paths))
            self.assertTrue(all(path.exists() for path in malformed_paths))

    def test_archived_source_mutation_rejects_cache_and_rederives(self) -> None:
        """Criterion 1 adversarial plant: source movement cannot serve stale rows."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            uid = fixture.archive_uids[0]
            source = fixture.files / f"{uid}.md"
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    f"fixture {uid}",
                    "archive source changed",
                ),
                encoding="utf-8",
            )
            fixture.commit_sources("mutate archived source")

            self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
            artifact = json.loads(fixture.run_artifact.read_text(encoding="utf-8"))
            archive_text = fixture.archive_surface.read_text(encoding="utf-8")

            self.assertEqual(artifact["archive_cache_action"], "derived")
            self.assertEqual(artifact["parsed_record_count"], 5)
            self.assertIn("archive source changed", archive_text)

    def test_reconcile_without_cache_recreates_byte_identical_surfaces(self) -> None:
        """Criterion 2: cache deletion cannot impair source-only rebuildability."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
            fixture.prime()
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
            )
            fixture.cache_jsonl.unlink()
            fixture.cache_meta.unlink()

            self.assertEqual(
                rebuild.rebuild_index(fixture.root, True, reconcile=True),
                0,
            )
            after = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
            )
            artifact = json.loads(fixture.run_artifact.read_text(encoding="utf-8"))

            self.assertEqual(after, before)
            self.assertTrue(fixture.cache_jsonl.is_file())
            self.assertTrue(fixture.cache_meta.is_file())
            self.assertEqual(artifact["archive_cache_action"], "recreated")
            self.assertEqual(artifact["parsed_record_count"], 5)

    def test_corrupt_truncated_hash_mismatch_cache_and_surface_refuse(self) -> None:
        """Criterion 4: four independent damage shapes all fail closed."""
        mutations = (
            "truncated-cache",
            "hash-mismatch-cache",
            "corrupt-surface",
            "corrupt-surface-no-cache",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=3)
                fixture.prime()
                surfaces_before = (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                )

                if mutation == "truncated-cache":
                    fixture.cache_jsonl.write_bytes(
                        fixture.cache_jsonl.read_bytes()[:-1]
                    )
                elif mutation == "hash-mismatch-cache":
                    rows = index_surfaces.read_jsonl_strict(fixture.cache_jsonl)
                    rows[0]["title"] = "tampered but syntactically valid"
                    _write_jsonl(fixture.cache_jsonl, rows)
                else:
                    if mutation == "corrupt-surface-no-cache":
                        fixture.cache_jsonl.unlink()
                        fixture.cache_meta.unlink()
                    fixture.archive_surface.write_text('{"uid":"truncated"', encoding="utf-8")
                    surfaces_before = (
                        fixture.current_surface.read_bytes(),
                        fixture.archive_surface.read_bytes(),
                    )

                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    rc = rebuild.rebuild_index(fixture.root, True)

                self.assertNotEqual(rc, 0)
                self.assertIn("REFUSAL", stderr.getvalue())
                self.assertEqual(
                    (
                        fixture.current_surface.read_bytes(),
                        fixture.archive_surface.read_bytes(),
                    ),
                    surfaces_before,
                )

    def test_reconcile_dry_run_lists_purge_but_deletes_nothing(self) -> None:
        """Criterion 5: purge is preview-only without the explicit apply gesture."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FixtureStudio(Path(tmp), current_count=2, archive_count=20)
            fixture.prime()
            removed_uid = fixture.archive_uids[0]
            (fixture.files / f"{removed_uid}.md").unlink()
            fixture.commit_sources("remove one fixture source")
            before = (
                fixture.current_surface.read_bytes(),
                fixture.archive_surface.read_bytes(),
                fixture.cache_jsonl.read_bytes(),
                fixture.cache_meta.read_bytes(),
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = rebuild.rebuild_index(
                    fixture.root,
                    False,
                    reconcile=True,
                )

            self.assertEqual(rc, 0)
            self.assertIn("[PURGE-LIST]", output.getvalue())
            self.assertIn(removed_uid, output.getvalue())
            self.assertEqual(
                (
                    fixture.current_surface.read_bytes(),
                    fixture.archive_surface.read_bytes(),
                    fixture.cache_jsonl.read_bytes(),
                    fixture.cache_meta.read_bytes(),
                ),
                before,
            )

    def _template_leg_fixture(
        self,
        root: Path,
        *,
        enforced_from: str | None = "2026-07-20",
        declare_severity: bool = True,
    ) -> Path:
        """A minimal vault whose `fixture` type carries a §Template leg.

        The leg requires a '## Verification' section. `enforced_from` sets the
        capsule's declared template_enforced_from (None = undeclared); the
        capsule-of-capsules carries the generic-tier severity declaration the
        verifier reads its grades from.
        """
        files = root / "vault" / "files"
        capsules = root / "vault" / "capsules"
        files.mkdir(parents=True)
        capsules.mkdir()
        (root / ".tropo").mkdir()

        enforced_line = (
            f"template_enforced_from: '{enforced_from}'\n" if enforced_from else ""
        )
        (capsules / "tropo-fixture.capsule.md").write_text(
            f"---\nversion: '1.0'\n{enforced_line}---\n"
            "## §Template\n"
            "~~~markdown\n"
            "---\nuid: <<MINT:uid>>\ntype: fixture\n"
            "capsule_version: <<MINT:capsule_version>>\n---\n"
            "# Fixture\n\n## Verification\n"
            "<!-- REQUIRED: evidence -->\n"
            "~~~\n",
            encoding="utf-8",
        )
        severity_block = (
            "instance_verifier_severity:\n"
            "  sections-present: WARN\n"
            "  placeholder-survival: FAIL\n"
            "  stray-mint-token: ERROR\n"
            "  body-unreadable: FAIL\n"
        ) if declare_severity else ""
        (capsules / "tropo-capsule-definition.capsule.md").write_text(
            f"---\nversion: '1.1'\n{severity_block}---\n"
            "# capsule-definition\n",
            encoding="utf-8",
        )
        return files

    def test_archived_body_shape_is_excluded_but_current_still_fails(self) -> None:
        """Criterion 6 adversarial plant: exemption cannot widen to live work.

        Both entries postdate the leg, so grandfathering is not in play -- this
        keeps proving that the archive exemption alone does not shelter live work.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = self._template_leg_fixture(root, enforced_from="2026-07-20")
            current_uid = "abc00001"
            archive_uid = "abc00002"
            for uid in (current_uid, archive_uid):
                (files / f"{uid}.md").write_text(
                    _entry_text(
                        uid,
                        state="active" if uid == current_uid else "archived",
                        status="active" if uid == current_uid else "done",
                        entry_type="fixture",
                        body="# Fixture without verification\n",
                    ),
                    encoding="utf-8",
                )
            _write_jsonl(
                root / "vault" / index_surfaces.CURRENT_INDEX_NAME,
                [{
                    "uid": current_uid,
                    "type": "fixture",
                    "state": "active",
                    "status": "active",
                    "path": f"vault/files/{current_uid}.md",
                }],
            )
            _write_jsonl(
                root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME,
                [{
                    "uid": archive_uid,
                    "type": "fixture",
                    "state": "archived",
                    "status": "done",
                    "path": f"vault/files/{archive_uid}.md",
                }],
            )

            findings, checked, defects = validate.check_live_template_body_shape(root)

            self.assertEqual(checked, 1)
            missing = [f for f in findings if "MISSING-SECTION" in f]
            self.assertEqual(len(missing), 1)
            self.assertTrue(missing[0].startswith("[WARN]"))
            self.assertIn(current_uid, missing[0])
            self.assertFalse(any(archive_uid in finding for finding in findings))
            self.assertTrue(any("CURRENT surface only" in finding for finding in findings))
            # Capsule-declared WARN is advisory: it must not gate the exit code.
            self.assertEqual(defects, 0)

    def test_pre_template_entry_is_grandfathered_for_sections_only(self) -> None:
        """The mint-time contract does not reach back past its own start date --
        and grandfathering buys exemption from MISSING-SECTION and nothing else.

        Same body defect on both entries; only the `created` date differs.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = self._template_leg_fixture(root, enforced_from="2026-07-20")
            old_uid, new_uid = "abc00003", "abc00004"
            rows = []
            for uid, created in ((old_uid, "2026-05-01"), (new_uid, "2026-07-21")):
                text = _entry_text(
                    uid,
                    state="active",
                    status="active",
                    entry_type="fixture",
                    # No '## Verification' heading, plus a surviving REQUIRED
                    # placeholder and a stray mint token -- the two non-grandfathered
                    # defect classes, planted on BOTH entries.
                    body="# Fixture without verification\n"
                         "<!-- REQUIRED: evidence -->\n"
                         "<<MINT:uid>>\n",
                ).replace("created: '2026-07-26'", f"created: '{created}'")
                (files / f"{uid}.md").write_text(text, encoding="utf-8")
                rows.append({
                    "uid": uid,
                    "type": "fixture",
                    "state": "active",
                    "status": "active",
                    "path": f"vault/files/{uid}.md",
                })
            _write_jsonl(root / "vault" / index_surfaces.CURRENT_INDEX_NAME, rows)
            _write_jsonl(root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME, [])

            findings, checked, _ = validate.check_live_template_body_shape(root)

            self.assertEqual(checked, 2)
            missing = [f for f in findings if "MISSING-SECTION" in f]
            self.assertEqual(len(missing), 1, "only the post-leg entry may be flagged")
            self.assertIn(new_uid, missing[0])
            self.assertNotIn(old_uid, missing[0])
            # Narrowness: the grandfathered entry is still fully checked otherwise.
            for kind in ("INCOMPLETE", "MALFORMED-MINT"):
                hits = [f for f in findings if kind in f and old_uid in f]
                self.assertEqual(len(hits), 1, f"{kind} must still fire on a pre-leg entry")

    def test_boundary_and_undeclared_cases_do_not_manufacture_findings(self) -> None:
        """An entry created ON the declared date, an entry with no `created`, and a
        capsule that declares no date are all unprovable -- none may be flagged, and
        the undeclared capsule must say so out loud instead of failing silently."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = self._template_leg_fixture(root, enforced_from="2026-07-20")
            boundary_uid, undated_uid = "abc00005", "abc00006"
            rows = []
            for uid, created in ((boundary_uid, "2026-07-20"), (undated_uid, None)):
                text = _entry_text(
                    uid, state="active", status="active", entry_type="fixture",
                    body="# Fixture without verification\n",
                )
                text = (text.replace("created: '2026-07-26'", f"created: '{created}'")
                        if created else text.replace("created: '2026-07-26'\n", ""))
                (files / f"{uid}.md").write_text(text, encoding="utf-8")
                rows.append({
                    "uid": uid, "type": "fixture", "state": "active",
                    "status": "active", "path": f"vault/files/{uid}.md",
                })
            _write_jsonl(root / "vault" / index_surfaces.CURRENT_INDEX_NAME, rows)
            _write_jsonl(root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME, [])

            findings, _, _ = validate.check_live_template_body_shape(root)
            self.assertEqual([f for f in findings if "MISSING-SECTION" in f], [])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = self._template_leg_fixture(root, enforced_from=None)
            uid = "abc00007"
            (files / f"{uid}.md").write_text(
                _entry_text(uid, state="active", status="active", entry_type="fixture",
                            body="# Fixture without verification\n"),
                encoding="utf-8",
            )
            _write_jsonl(
                root / "vault" / index_surfaces.CURRENT_INDEX_NAME,
                [{"uid": uid, "type": "fixture", "state": "active",
                  "status": "active", "path": f"vault/files/{uid}.md"}],
            )
            _write_jsonl(root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME, [])

            findings, _, _ = validate.check_live_template_body_shape(root)
            self.assertEqual([f for f in findings if "MISSING-SECTION" in f], [])
            self.assertTrue(
                any("TEMPLATE-ENFORCEMENT-UNDECLARED" in f for f in findings),
                "an undeclared enforcement start must be loud, not silent",
            )

    def test_severity_is_read_from_the_capsule_not_hardcoded(self) -> None:
        """Editing the capsule's declared grade changes what the validator emits --
        the enforced_enums contract, applied to severity. With no declaration the
        verifier withholds the finding and ERRORs rather than inventing a grade."""
        def run(declare_severity: bool, grade: str = "WARN"):
            tmp = tempfile.mkdtemp()
            root = Path(tmp).resolve()
            files = self._template_leg_fixture(
                root, enforced_from="2026-07-20", declare_severity=declare_severity)
            if declare_severity and grade != "WARN":
                capsule = root / "vault/capsules/tropo-capsule-definition.capsule.md"
                capsule.write_text(
                    capsule.read_text(encoding="utf-8").replace(
                        "sections-present: WARN", f"sections-present: {grade}"),
                    encoding="utf-8")
            uid = "abc00008"
            (files / f"{uid}.md").write_text(
                _entry_text(uid, state="active", status="active", entry_type="fixture",
                            body="# Fixture without verification\n"),
                encoding="utf-8",
            )
            _write_jsonl(
                root / "vault" / index_surfaces.CURRENT_INDEX_NAME,
                [{"uid": uid, "type": "fixture", "state": "active",
                  "status": "active", "path": f"vault/files/{uid}.md"}],
            )
            _write_jsonl(root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME, [])
            try:
                return validate.check_live_template_body_shape(root)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        findings, _, defects = run(True, "WARN")
        self.assertTrue(any(f.startswith("[WARN]") and "MISSING-SECTION" in f
                            for f in findings))
        self.assertEqual(defects, 0)

        findings, _, defects = run(True, "ERROR")
        self.assertTrue(any(f.startswith("[ERROR]") and "MISSING-SECTION" in f
                            for f in findings))
        self.assertEqual(defects, 1, "the capsule can ratchet the grade without a code change")

        findings, _, defects = run(False)
        self.assertEqual([f for f in findings if "MISSING-SECTION" in f], [])
        self.assertTrue(any("INSTANCE-VERIFIER-SEVERITY" in f for f in findings))
        self.assertGreaterEqual(defects, 1, "an ungraded check must fail loudly")

    def test_union_integrity_uses_both_surfaces_and_errors(self) -> None:
        """Criterion 7: duplicate UID + fileless row are ERROR-grade."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = root / "vault" / "files"
            files.mkdir(parents=True)
            (root / ".tropo").mkdir()
            duplicate_uid = "def00001"
            (files / f"{duplicate_uid}.md").write_text(
                _entry_text(duplicate_uid, state="active", status="active"),
                encoding="utf-8",
            )
            duplicate_row = {
                "uid": duplicate_uid,
                "type": "note",
                "path": f"vault/files/{duplicate_uid}.md",
            }
            _write_jsonl(
                root / "vault" / index_surfaces.CURRENT_INDEX_NAME,
                [duplicate_row],
            )
            _write_jsonl(
                root / "vault" / index_surfaces.ARCHIVE_INDEX_NAME,
                [
                    {**duplicate_row, "state": "archived"},
                    {
                        "uid": "def00002",
                        "type": "note",
                        "path": "vault/files/def00002.md",
                    },
                ],
            )

            findings, checked, defects = validate.check_index_union_integrity(root)

            self.assertEqual(checked, 3)
            self.assertEqual(defects, 2)
            self.assertTrue(all(finding.startswith("[ERROR]") for finding in findings))
            self.assertTrue(any("UID uniqueness" in finding for finding in findings))
            self.assertTrue(any("row resolution" in finding for finding in findings))
            self.assertTrue(any("current + archive" in finding for finding in findings))


class KernelDoctrineIndexingTests(unittest.TestCase):
    """ADR-064: `.tropo/` doctrine is governed content and must be indexable.

    The Studio's own rules were unfindable by the Studio's own search: zero of
    70 kernel files were indexed, so orient() answered about the work but
    returned NODE_NOT_FOUND for the Wake Discipline -- the one class of content
    a cold agent needs first (metis-g98, 2026-08-01).

    Admission is the EXISTING identifier contract, never a maintained exclusion
    list: a conforming 8-hex uid makes a file a governed entry and its absence
    makes it not one. Two scoping rules fall out of that rather than being
    special cases -- generated catalogs carry word UIDs, and `.tropo/seed/`
    holds bootstrap copies addressed to a DIFFERENT Studio which collide by
    design with the entries they were copied from.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / '.tropo' / 'seed' / 'vault').mkdir(parents=True)
        (self.root / '.tropo' / 'playbooks').mkdir(parents=True)

    def _write(self, rel: str, uid: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        head = f"---\nuid: {uid}\n" if uid is not None else "---\n"
        path.write_text(
            head + "type: os-primitive\ntitle: T\n---\n\n# T\n", encoding='utf-8'
        )

    def _admitted(self):
        admitted, skipped = rebuild._tropo_kernel_sources(self.root)
        rel = lambda paths: {p.relative_to(self.root).as_posix() for p in paths}
        return rel(admitted), rel(skipped)

    def test_governed_doctrine_is_admitted(self):
        self._write('.tropo/WAKE-DISCIPLINE.md', 'd2bb4dda')
        self._write('.tropo/playbooks/agent-activation.playbook.md', 'c2caddf4')
        admitted, _ = self._admitted()
        self.assertEqual(
            admitted,
            {'.tropo/WAKE-DISCIPLINE.md',
             '.tropo/playbooks/agent-activation.playbook.md'},
        )

    def test_non_conforming_identifiers_are_skipped_and_VISIBLE(self):
        """A skip nobody can see is how a gate reports success while blind."""
        self._write('.tropo/toolbelt.md', 'toolbelt')          # generated catalog
        self._write('.tropo/schema/x-schema.md', 'null')       # stub
        self._write('.tropo/AGENTS.md', None)                  # no frontmatter uid
        admitted, skipped = self._admitted()
        self.assertEqual(admitted, set())
        self.assertEqual(
            skipped,
            {'.tropo/toolbelt.md', '.tropo/schema/x-schema.md', '.tropo/AGENTS.md'},
            'skips must be returned for reporting, never silently dropped',
        )

    def test_seed_payload_is_scoped_out(self):
        """Seed copies share UIDs by design and collide with the live entry."""
        self._write('.tropo/SELF-HEALING.md', 'db0fd9b1')
        self._write('.tropo/seed/vault/project-board.board-definition.md', 'c72f1a85')
        admitted, skipped = self._admitted()
        self.assertEqual(admitted, {'.tropo/SELF-HEALING.md'})
        self.assertIn('.tropo/seed/vault/project-board.board-definition.md', skipped)

    def test_the_two_readers_cannot_disagree(self):
        """The predicate and the enumerator ARE the completeness proof's two
        readers. A disagreement makes the proof report a legitimate file as a
        deleted source -- observed, and it refused 45 paths."""
        self._write('.tropo/WAKE-DISCIPLINE.md', 'd2bb4dda')
        self._write('.tropo/toolbelt.md', 'toolbelt')
        rebuild._KERNEL_ADMITTED_MEMO.clear()
        self.assertTrue(
            rebuild._is_canonical_index_source(Path('.tropo/WAKE-DISCIPLINE.md'))
            if str(self.root.resolve()) in rebuild._KERNEL_ADMITTED_MEMO
            or rebuild._tropo_kernel_admitted(self.root)
            else False
        )
        admitted = rebuild._tropo_kernel_admitted(self.root)
        self.assertIn('.tropo/WAKE-DISCIPLINE.md', admitted)
        self.assertNotIn('.tropo/toolbelt.md', admitted)


if __name__ == "__main__":
    unittest.main()
