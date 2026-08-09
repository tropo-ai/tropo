#!/usr/bin/env python3
"""Focused executable contract for the B4a one-shot group finalizer.

Covers the acceptance criteria this slice owns:

* AC1 GOVERNED BIRTH (the finalize half): one authored ``draft`` seals into
  exactly one immutable candidate generation whose corpus digest is the locked
  AV1 vector; drafts and the unsigned candidate are never resolver-visible.
* AC11 CONCURRENCY AND RECOVERY: process loss injected *before and after* every
  named transaction boundary either completes the finalize exactly once
  idempotently or refuses with a typed stale/recovery code while leaving every
  authored source intact; a second resume is a no-op; input mutation mid-flight
  refuses ``GROUP_CORPUS_STALE`` / ``PROJECTION_MISMATCH`` as appropriate; and
  same-slug concurrent finalizers yield exactly one success.

The tool under test is loaded by file path with ``importlib`` (mirroring
``test_b4a_group_registry.py``); the pure ``lib.group_contract`` dependency is
imported normally so both share one ``GroupErrorCode`` / ``GroupContractError``
identity.  Everything runs inside ``tempfile.TemporaryDirectory()`` corpora.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import multiprocessing
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


finalize = _load("b4a_finalize_group_under_test", TOOLS / "tropo-finalize-group.py")

from lib.group_contract import (  # noqa: E402
    GroupContractError,
    GroupErrorCode,
    semantic_hash,
)

finalize_group = finalize.finalize_group
recover_candidate = finalize.recover_candidate
SimulatedProcessLoss = finalize.SimulatedProcessLoss


# --------------------------------------------------------------------------- #
# Locked AV1 vector literals (dev-spec 0bfa771d, "Locked authority vector AV1"). #
# --------------------------------------------------------------------------- #

MIKE_UID = "7b921d17"
MIKE_GROUP_UID = "11111111"
AV1_AUTHORITY_UID = "a1b2c3d4"
AV1_GROUP_SHA256 = "8fac9a9ce622c9b265ee91c1f9176bb9ac6054ea3ee49763bf36b37a4516002f"
AV1_CORPUS_REVISION = f"sha256:{AV1_GROUP_SHA256}"
AV1_PRINCIPAL_DIRECTORY_REVISION = (
    "sha256:9af1ee55eafdc2261db97211ab959c9ca9fdab66d5e70f5c24d178e58fa84d83"
)
AV1_GROUPS_JSONL_LINE = (
    b'{"uid":"11111111","type":"group","slug":"mike","title":"Mike",'
    b'"description":"Personal work visible to Mike.","owner":"7b921d17",'
    b'"members":["7b921d17"],"includes_groups":[],"status":"active","version":1}\n'
)


# Every named transaction boundary, with a "before" and "after" injection point.
ALL_BOUNDARIES = (
    "backup_write:before",
    "backup_write:after",
    "stage_write:before",
    "stage_write:after",
    "journal_fsync:before",
    "journal_fsync:after",
    "source_swap:before",
    "source_swap:after",
    "generation_swap:before",
    "generation_swap:after",
    "jsonl_swap:before",
    "jsonl_swap:after",
    "sqlite_swap:before",
    "sqlite_swap:after",
    "wrapper_index:before",
    "wrapper_index:mid",
    "wrapper_index:after",
    "verification:before",
    "verification:after",
    "committed_record:before",
    "committed_record:after",
    "cleanup:before",
    "cleanup:after",
)

# Boundaries reached before the PREPARED journal row is durable: recovery finds
# no journaled transaction (nothing was swapped, the draft is untouched).
PRE_JOURNAL = frozenset(
    {
        "backup_write:before",
        "backup_write:after",
        "stage_write:before",
        "stage_write:after",
        "journal_fsync:before",
    }
)
# Boundaries reached after the COMMITTED journal row is durable: recovery just
# verifies + cleans (the transaction is already settled).
SETTLED = frozenset({"committed_record:after", "cleanup:before", "cleanup:after"})


def _principals(*, extra: dict | None = None) -> dict:
    principals = {
        MIKE_UID: {
            "principal_uid": MIKE_UID,
            "principal_class": "human",
            "status": "active",
            "source_authority_uid": AV1_AUTHORITY_UID,
            "source_revision": "1",
            "source_hash": "0" * 64,
        }
    }
    if extra:
        principals.update(extra)
    return principals


def _draft(uid: str, slug: str, *, owner: str = MIKE_UID, members=None) -> dict:
    return {
        "uid": uid,
        "type": "group",
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "description": f"Purpose of {slug}.",
        "owner": owner,
        "members": list(members if members is not None else [owner]),
        "includes_groups": [],
        "status": "draft",
        "version": 1,
        "semantic_hash": None,
    }


def _mike_draft() -> dict:
    return {
        "uid": MIKE_GROUP_UID,
        "type": "group",
        "slug": "mike",
        "title": "Mike",
        "description": "Personal work visible to Mike.",
        "owner": MIKE_UID,
        "members": [MIKE_UID],
        "includes_groups": [],
        "status": "draft",
        "version": 1,
        "semantic_hash": None,
    }


# Top-level worker for the fork-based concurrency test (must be importable so a
# forked child can run it against the inherited, importlib-loaded module).
def _concurrent_worker(root_str, draft_uid, principals, barrier, queue):
    try:
        barrier.wait(timeout=30)
    except Exception:
        pass
    try:
        result = finalize_group(
            root_str,
            draft_uid,
            principals=principals,
            authority_uid=AV1_AUTHORITY_UID,
            principal_directory_revision=AV1_PRINCIPAL_DIRECTORY_REVISION,
            lock_timeout=60.0,
        )
        queue.put(("ok", result.status, result.candidate_revision))
    except GroupContractError as error:  # typed refusal
        queue.put(("err", error.code.value, None))
    except BaseException as error:  # pragma: no cover - defensive
        queue.put(("exc", type(error).__name__, str(error)))


class B4aFinalizeGroupTests(unittest.TestCase):
    # ------------------------------------------------------------- helpers

    def _new_root(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "groups").mkdir(parents=True)
        return root

    def _write_source(self, root: Path, obj: dict) -> None:
        (root / "groups" / f"{obj['uid']}.json").write_text(
            json.dumps(obj), encoding="utf-8"
        )

    def _seed_mike(self) -> Path:
        root = self._new_root()
        self._write_source(root, _mike_draft())
        return root

    def _finalize(self, root: Path, uid: str = MIKE_GROUP_UID, *, failpoint=None):
        return finalize_group(
            root,
            uid,
            principals=_principals(),
            authority_uid=AV1_AUTHORITY_UID,
            principal_directory_revision=AV1_PRINCIPAL_DIRECTORY_REVISION,
            failpoint=failpoint,
        )

    def _journal_rows(self, root: Path) -> list:
        path = root / finalize.JOURNAL_RELATIVE
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def _source_status(self, root: Path, uid: str) -> str | None:
        path = root / "groups" / f"{uid}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("status")

    def _snapshot(self, root: Path) -> dict:
        """Digest every durable surface finalize may touch (published excluded)."""

        relatives = [
            f"groups/{MIKE_GROUP_UID}.json",
            finalize.GEN_GROUPS_RELATIVE,
            finalize.GEN_REGISTRY_RELATIVE,
            finalize.GEN_SQLITE_RELATIVE,
            finalize.GEN_WRAPPER_RELATIVE,
            finalize.GEN_INDEX_RELATIVE,
            finalize.JOURNAL_RELATIVE,
        ]
        snapshot = {}
        for relative in relatives:
            path = root / relative
            snapshot[relative] = (
                hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            )
        return snapshot

    def assert_code(self, expected: GroupErrorCode, operation) -> GroupContractError:
        with self.assertRaises(GroupContractError) as raised:
            operation()
        self.assertEqual(raised.exception.code, expected)
        self.assertTrue(str(raised.exception).startswith(expected.value + ":"))
        return raised.exception

    def _assert_published_absent(self, root: Path) -> None:
        self.assertFalse(
            (root / finalize.PUBLISHED_REGISTRY_RELATIVE).exists(),
            "finalize must never write the resolver-visible published registry",
        )

    # -------------------------------------------------------------- AC1

    def test_ac1_single_draft_seals_one_candidate_matching_av1(self) -> None:
        root = self._seed_mike()
        result = self._finalize(root)

        self.assertEqual(result.status, "committed")
        self.assertEqual(result.group_uid, MIKE_GROUP_UID)
        # Locked AV1 corpus digest / revision.
        self.assertEqual(result.corpus_sha256, AV1_GROUP_SHA256)
        self.assertEqual(result.candidate_revision, AV1_CORPUS_REVISION)
        self.assertEqual(result.finalized_group_uids, (MIKE_GROUP_UID,))
        self.assertFalse(result.resolver_visible)

        # The authority corpus is byte-identical to the locked AV1 groups.jsonl.
        groups_bytes = (root / finalize.GEN_GROUPS_RELATIVE).read_bytes()
        self.assertEqual(groups_bytes, AV1_GROUPS_JSONL_LINE)
        self.assertEqual(hashlib.sha256(groups_bytes).hexdigest(), AV1_GROUP_SHA256)

        # The authored source is now sealed active with the correct semantic hash.
        active = json.loads(
            (root / "groups" / f"{MIKE_GROUP_UID}.json").read_text("utf-8")
        )
        self.assertEqual(active["status"], "active")
        self.assertEqual(active["semantic_hash"], semantic_hash(active))

        # Exactly one candidate registry row, bound by the wrapper.
        registry = (root / finalize.GEN_REGISTRY_RELATIVE).read_bytes()
        rows = [json.loads(x) for x in registry.decode("utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["group_uid"], MIKE_GROUP_UID)
        self.assertEqual(rows[0]["source_hash"], AV1_GROUP_SHA256)
        wrapper = json.loads((root / finalize.GEN_WRAPPER_RELATIVE).read_bytes())
        self.assertEqual(wrapper["row_count"], 1)
        self.assertEqual(wrapper["source_revision"], AV1_CORPUS_REVISION)

        # SQLite parity holds on the committed candidate database.
        index = json.loads((root / finalize.GEN_INDEX_RELATIVE).read_bytes())
        self.assertFalse(index["resolver_visible"])

        # Journal shows exactly one PREPARED -> COMMITTED transaction.
        types = [r["type"] for r in self._journal_rows(root)]
        self.assertEqual(types, ["PREPARED", "COMMITTED"])

        self._assert_published_absent(root)

    def test_ac1_drafts_never_resolver_visible(self) -> None:
        root = self._new_root()
        self._write_source(root, _mike_draft())
        self._write_source(root, _draft("22222222", "second-group"))

        result = self._finalize(root, MIKE_GROUP_UID)
        self.assertEqual(result.finalized_group_uids, (MIKE_GROUP_UID,))

        # The sibling draft is still a draft and absent from the candidate.
        self.assertEqual(self._source_status(root, "22222222"), "draft")
        groups_bytes = (root / finalize.GEN_GROUPS_RELATIVE).read_bytes()
        self.assertIn(MIKE_GROUP_UID.encode(), groups_bytes)
        self.assertNotIn(b"22222222", groups_bytes)
        registry_bytes = (root / finalize.GEN_REGISTRY_RELATIVE).read_bytes()
        self.assertNotIn(b"22222222", registry_bytes)

        self._assert_published_absent(root)

    def test_ac1_candidate_is_machine_local_not_published(self) -> None:
        root = self._seed_mike()
        result = self._finalize(root)

        # The sealed candidate lives under machine-local .tropo-studio ...
        self.assertTrue(result.generation_dir.startswith(".tropo-studio/"))
        self.assertTrue((root / finalize.GEN_GROUPS_RELATIVE).exists())
        self.assertIn(MIKE_GROUP_UID.encode(), (root / finalize.GEN_REGISTRY_RELATIVE).read_bytes())

        # ... but the single resolver-visible surface is never written, so a
        # resolver reading the published registry sees nothing.
        self._assert_published_absent(root)

    def test_ac1_idempotent_refinalize_is_a_noop(self) -> None:
        root = self._seed_mike()
        first = self._finalize(root)
        snapshot = self._snapshot(root)

        second = self._finalize(root)
        self.assertEqual(second.status, "idempotent")
        self.assertEqual(second.candidate_revision, first.candidate_revision)
        # Transition-once: no re-sealing, no new journal rows, byte-stable.
        self.assertEqual(self._snapshot(root), snapshot)
        self.assertEqual([r["type"] for r in self._journal_rows(root)], ["PREPARED", "COMMITTED"])

    def test_ac1_sequential_finalize_accumulates_and_chains(self) -> None:
        # A second finalize seals both groups into the candidate and appends a
        # second hash-chained PREPARED->COMMITTED pair (exercising non-null old
        # digests + verified backups for the pre-existing candidate files).
        root = self._new_root()
        self._write_source(root, _mike_draft())
        self._write_source(root, _draft("22222222", "team-x", owner="22222222"))
        principals = _principals(
            extra={
                "22222222": {
                    "principal_uid": "22222222",
                    "principal_class": "human",
                    "status": "active",
                    "source_authority_uid": AV1_AUTHORITY_UID,
                    "source_revision": "1",
                    "source_hash": "0" * 64,
                }
            }
        )

        first = finalize_group(
            root, MIKE_GROUP_UID, principals=principals,
            authority_uid=AV1_AUTHORITY_UID,
            principal_directory_revision=AV1_PRINCIPAL_DIRECTORY_REVISION,
        )
        self.assertEqual(first.finalized_group_uids, (MIKE_GROUP_UID,))
        second = finalize_group(
            root, "22222222", principals=principals,
            authority_uid=AV1_AUTHORITY_UID,
            principal_directory_revision=AV1_PRINCIPAL_DIRECTORY_REVISION,
        )
        self.assertEqual(second.finalized_group_uids, (MIKE_GROUP_UID, "22222222"))
        self.assertEqual(self._source_status(root, MIKE_GROUP_UID), "active")
        self.assertEqual(self._source_status(root, "22222222"), "active")

        registry = (root / finalize.GEN_REGISTRY_RELATIVE).read_bytes()
        rows = [json.loads(x) for x in registry.decode("utf-8").splitlines()]
        self.assertEqual([r["group_uid"] for r in rows], [MIKE_GROUP_UID, "22222222"])

        self.assertEqual(
            [r["type"] for r in self._journal_rows(root)],
            ["PREPARED", "COMMITTED", "PREPARED", "COMMITTED"],
        )
        # The full chain re-verifies cleanly and settles.
        self.assertEqual(recover_candidate(root).state, "settled")
        self._assert_published_absent(root)

    def test_ac1_finalize_unknown_uid_refuses(self) -> None:
        root = self._seed_mike()
        self.assert_code(
            GroupErrorCode.GROUP_NOT_FOUND,
            lambda: self._finalize(root, "deadbeef"),
        )
        self._assert_published_absent(root)

    def test_ac1_finalize_duplicate_slug_refuses(self) -> None:
        root = self._seed_mike()
        self._finalize(root, MIKE_GROUP_UID)
        # A second draft claiming the same slug as the now-active Mike group.
        self._write_source(root, _draft("33333333", "mike", owner=MIKE_UID))
        self.assert_code(
            GroupErrorCode.GROUP_SLUG_DUPLICATE,
            lambda: self._finalize(root, "33333333"),
        )

    def test_ac1_finalize_unresolved_principal_refuses(self) -> None:
        root = self._new_root()
        # Owner/member 99999999 is not in the injected principal directory.
        self._write_source(
            root, _draft(MIKE_GROUP_UID, "mike", owner="99999999", members=["99999999"])
        )
        self.assert_code(
            GroupErrorCode.PRINCIPAL_UNRESOLVED,
            lambda: self._finalize(root, MIKE_GROUP_UID),
        )

    def test_ac1_active_source_without_candidate_refuses(self) -> None:
        # An already-active authored source with no candidate generation is an
        # inconsistent state, not an idempotent finalize.
        root = self._new_root()
        active = {k: v for k, v in _mike_draft().items() if k != "semantic_hash"}
        active["status"] = "active"
        active["semantic_hash"] = semantic_hash(active)
        self._write_source(root, active)
        self.assert_code(
            GroupErrorCode.PROJECTION_MISMATCH,
            lambda: self._finalize(root, MIKE_GROUP_UID),
        )

    # -------------------------------------------------------------- AC11

    def test_ac11_recover_empty_corpus_is_noop(self) -> None:
        root = self._new_root()
        outcome = recover_candidate(root)
        self.assertEqual(outcome.state, "none")

    def test_ac11_recovery_across_every_boundary(self) -> None:
        for boundary in ALL_BOUNDARIES:
            with self.subTest(boundary=boundary):
                root = self._seed_mike()

                # Inject process loss at the boundary.
                with self.assertRaises(SimulatedProcessLoss):
                    self._finalize(root, failpoint=boundary)

                # Self-contained recovery: complete-once or observe no/settled txn.
                outcome = recover_candidate(root)
                if boundary in PRE_JOURNAL:
                    self.assertEqual(outcome.state, "none")
                    self.assertEqual(self._source_status(root, MIKE_GROUP_UID), "draft")
                elif boundary in SETTLED:
                    self.assertEqual(outcome.state, "settled")
                else:
                    self.assertEqual(outcome.state, "completed")

                # The finalize (which embeds recovery) reaches the sealed state.
                first = self._finalize(root)
                self.assertEqual(first.candidate_revision, AV1_CORPUS_REVISION)
                self.assertEqual(
                    (root / finalize.GEN_GROUPS_RELATIVE).read_bytes(),
                    AV1_GROUPS_JSONL_LINE,
                )
                self.assertEqual(self._source_status(root, MIKE_GROUP_UID), "active")
                self._assert_published_absent(root)

                # A second resume is a strict no-op.
                settled = self._snapshot(root)
                second = self._finalize(root)
                self.assertEqual(second.candidate_revision, AV1_CORPUS_REVISION)
                self.assertEqual(self._snapshot(root), settled)
                self.assertEqual(
                    [r["type"] for r in self._journal_rows(root)],
                    ["PREPARED", "COMMITTED"],
                )

    def test_ac11_recovery_completes_exactly_once_via_direct_recover(self) -> None:
        # For a durable-but-incomplete transaction, recover_candidate itself
        # completes it, and a second recover is a no-op ("settled").
        root = self._seed_mike()
        with self.assertRaises(SimulatedProcessLoss):
            self._finalize(root, failpoint="jsonl_swap:after")

        first = recover_candidate(root)
        self.assertEqual(first.state, "completed")
        self.assertEqual(first.candidate_revision, AV1_CORPUS_REVISION)
        snapshot = self._snapshot(root)

        second = recover_candidate(root)
        self.assertEqual(second.state, "settled")
        self.assertEqual(self._snapshot(root), snapshot)
        self._assert_published_absent(root)

    def test_ac11_input_mutation_midflight_returns_stale(self) -> None:
        root = self._seed_mike()
        with self.assertRaises(SimulatedProcessLoss):
            self._finalize(root, failpoint="journal_fsync:after")

        # Mutate the authored draft under the prepared transaction.
        mutated = _mike_draft()
        mutated["title"] = "Mutated Mike"
        self._write_source(root, mutated)

        self.assert_code(GroupErrorCode.GROUP_CORPUS_STALE, lambda: recover_candidate(root))
        # The user's file is left intact; no partial candidate was published.
        self.assertEqual(self._source_status(root, MIKE_GROUP_UID), "draft")
        self.assertFalse((root / finalize.GEN_GROUPS_RELATIVE).exists())
        self._assert_published_absent(root)
        # A second resume is the same deterministic refusal (no state change).
        self.assert_code(GroupErrorCode.GROUP_CORPUS_STALE, lambda: recover_candidate(root))

    def test_ac11_input_mutation_stale_self_heals_when_restored(self) -> None:
        root = self._seed_mike()
        original = (root / "groups" / f"{MIKE_GROUP_UID}.json").read_bytes()
        with self.assertRaises(SimulatedProcessLoss):
            self._finalize(root, failpoint="journal_fsync:after")

        mutated = _mike_draft()
        mutated["description"] = "changed under the transaction"
        self._write_source(root, mutated)
        self.assert_code(GroupErrorCode.GROUP_CORPUS_STALE, lambda: recover_candidate(root))

        # Restoring the exact original input lets recovery roll forward.
        (root / "groups" / f"{MIKE_GROUP_UID}.json").write_bytes(original)
        outcome = recover_candidate(root)
        self.assertEqual(outcome.state, "completed")
        self.assertEqual(outcome.candidate_revision, AV1_CORPUS_REVISION)
        self.assertEqual((root / finalize.GEN_GROUPS_RELATIVE).read_bytes(), AV1_GROUPS_JSONL_LINE)

    def test_ac11_projection_corruption_returns_projection_mismatch(self) -> None:
        root = self._seed_mike()
        with self.assertRaises(SimulatedProcessLoss):
            self._finalize(root, failpoint="generation_swap:after")

        # Corrupt the just-swapped candidate corpus to an unknown digest.
        (root / finalize.GEN_GROUPS_RELATIVE).write_bytes(b"garbage-not-old-not-new\n")

        self.assert_code(GroupErrorCode.PROJECTION_MISMATCH, lambda: recover_candidate(root))
        # The authored source is rolled back intact to its draft state.
        self.assertEqual(self._source_status(root, MIKE_GROUP_UID), "draft")
        self._assert_published_absent(root)

    def test_ac11_corrupt_staging_returns_recovery_required(self) -> None:
        root = self._seed_mike()
        with self.assertRaises(SimulatedProcessLoss):
            self._finalize(root, failpoint="journal_fsync:after")

        # Damage a staged surface so roll-forward cannot verify it.
        (root / finalize.STAGING_DIR / "jsonl").write_bytes(b"corrupt")

        self.assert_code(GroupErrorCode.RECOVERY_REQUIRED, lambda: recover_candidate(root))
        self.assertEqual(self._source_status(root, MIKE_GROUP_UID), "draft")
        self._assert_published_absent(root)
        # Terminal + deterministic: a second resume returns the same code.
        self.assert_code(GroupErrorCode.RECOVERY_REQUIRED, lambda: recover_candidate(root))

    def test_ac11_tampered_journal_returns_recovery_required(self) -> None:
        root = self._seed_mike()
        with self.assertRaises(SimulatedProcessLoss):
            self._finalize(root, failpoint="journal_fsync:after")

        journal = root / finalize.JOURNAL_RELATIVE
        tampered = journal.read_bytes().replace(b'"group_uid":"11111111"', b'"group_uid":"22222222"')
        self.assertNotEqual(tampered, journal.read_bytes())
        journal.write_bytes(tampered)

        self.assert_code(GroupErrorCode.RECOVERY_REQUIRED, lambda: recover_candidate(root))
        # The crash preceded the source swap, so the authored draft is intact.
        self.assertEqual(self._source_status(root, MIKE_GROUP_UID), "draft")
        self._assert_published_absent(root)

    def test_ac11_same_slug_concurrent_finalizers_one_success(self) -> None:
        if not hasattr(multiprocessing, "get_context"):  # pragma: no cover
            self.skipTest("multiprocessing context unavailable")
        try:
            ctx = multiprocessing.get_context("fork")
        except ValueError:  # pragma: no cover - non-fork platforms
            self.skipTest("fork start method unavailable")

        root = self._seed_mike()
        barrier = ctx.Barrier(2)
        queue = ctx.Queue()
        principals = _principals()
        procs = [
            ctx.Process(
                target=_concurrent_worker,
                args=(str(root), MIKE_GROUP_UID, principals, barrier, queue),
            )
            for _ in range(2)
        ]
        for proc in procs:
            proc.start()
        results = [queue.get(timeout=60) for _ in range(2)]
        for proc in procs:
            proc.join(timeout=60)
            self.assertFalse(proc.is_alive())

        kinds = [row[0] for row in results]
        self.assertEqual(kinds, ["ok", "ok"], msg=f"unexpected worker outcomes: {results}")
        statuses = [row[1] for row in results]
        # Exactly one finalizer performs the real seal; the other is a no-op.
        self.assertEqual(statuses.count("committed"), 1, msg=f"statuses={statuses}")
        other = [s for s in statuses if s != "committed"]
        self.assertEqual(len(other), 1)
        self.assertIn(other[0], ("idempotent", "recovered"))
        # Both observe the same sealed revision.
        self.assertEqual({row[2] for row in results}, {AV1_CORPUS_REVISION})
        # The journal proves exactly one transaction occurred.
        self.assertEqual(
            [r["type"] for r in self._journal_rows(root)], ["PREPARED", "COMMITTED"]
        )
        self._assert_published_absent(root)

    # ------------------------------------------------------- thin CLI

    def test_cli_finalize_then_recover_roundtrip(self) -> None:
        root = self._seed_mike()
        principals_file = root / "principals.json"
        principals_file.write_text(json.dumps(_principals()), encoding="utf-8")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = finalize.main(
                [
                    "finalize",
                    "--corpus-root",
                    str(root),
                    "--draft-uid",
                    MIKE_GROUP_UID,
                    "--authority-uid",
                    AV1_AUTHORITY_UID,
                    "--principal-directory-revision",
                    AV1_PRINCIPAL_DIRECTORY_REVISION,
                    "--principals-file",
                    str(principals_file),
                ]
            )
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "committed")
        self.assertEqual(payload["candidate_revision"], AV1_CORPUS_REVISION)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = finalize.main(["recover", "--corpus-root", str(root)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["state"], "settled")
        self._assert_published_absent(root)


if __name__ == "__main__":
    unittest.main()
