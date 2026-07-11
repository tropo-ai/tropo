#!/usr/bin/env python3
"""test_shard_index_c6f6bea4.py — adversarial gauntlet for the shard-keyed
incremental composed index (dev-spec c6f6bea4, ADR-051 Fork 4), paired
test-spec ea352a6b.

Runs entirely against ISOLATED fixture tempdirs — a fixture STUDIO-ROOT
(its own vault/files/, vault/00-index.jsonl, .tropo-studio/compose.lock,
.tropo-studio/shards/) plus one or more fixture "MOUNTED VAULT" source
repos (real `git init`'d tempdirs with real commit history, mirroring the
_init_fixture_vault_root pattern from test_mount_gate_409ef1cc.py). There
are ZERO real type:vault mounts in this studio today (the dev-spec's own
grounding — .tropo-studio/compose.lock does not exist on disk in the real
repo), so every plant constructs its own fixture "mounted vault" to
exercise the real re-derivation path.

Each plant is a REAL execution: fixture files are actually written to
disk, resolve_shards()/derive_mounted_shard_records()/staleness_findings()
(vault/tools/lib/shard_index.py — the SAME module tropo-rebuild-index.py's
writer and tropo-validate.py's check_shard_index_consistency both import)
are actually called, and real git commits are actually made and read via
`git rev-parse HEAD` — not a self-consistent mock.

Never points any write-path invocation at the real studio repo
(/Users/mike/git/tropo-studios/argo-os). All writes happen inside
tempfile.mkdtemp() fixture roots, cleaned up in tearDown().
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
REBUILD_PATH = ROOT / "vault" / "tools" / "tropo-rebuild-index.py"
VALIDATE_PATH = ROOT / "vault" / "tools" / "tropo-validate.py"
LIB_DIR = ROOT / "vault" / "tools" / "lib"

import sys
sys.path.insert(0, str(LIB_DIR.parent))  # so `import lib.X` resolves like the tools do

_rebuild_spec = importlib.util.spec_from_file_location("tropo_rebuild_index_under_test_c6f6bea4", str(REBUILD_PATH))
tropo_rebuild_index = importlib.util.module_from_spec(_rebuild_spec)
_rebuild_spec.loader.exec_module(tropo_rebuild_index)

_validate_spec = importlib.util.spec_from_file_location("tropo_validate_under_test_c6f6bea4", str(VALIDATE_PATH))
tropo_validate = importlib.util.module_from_spec(_validate_spec)
_validate_spec.loader.exec_module(tropo_validate)

process_file = tropo_rebuild_index.process_file
rebuild_index = tropo_rebuild_index.rebuild_index
check_shard_index_consistency = tropo_validate.check_shard_index_consistency

from lib import shard_index  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _git(*args, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


def _init_fixture_mounted_vault(tmp: Path, name: str) -> Path:
    """A fresh git-initted fixture 'mounted vault' source tree with its own
    vault/files/ directory — mirrors _init_fixture_vault_root from
    test_mount_gate_409ef1cc.py, extended with a vault/files/ tree since
    THIS fixture stands in for the shard-derivation source, not just a
    manifest-bearing root."""
    root = tmp / name
    (root / "vault" / "files").mkdir(parents=True)
    _git("init", "-q", cwd=root)
    _git("config", "user.email", "fixture@test.local", cwd=root)
    _git("config", "user.name", "fixture", cwd=root)
    return root


def _write_governed_file(root: Path, uid: str, title: str, ftype: str = "task", extra_fm: str = "") -> Path:
    # BOUNCE finding #1 fix (Argus A128, 2026-07-09; landed in
    # lib/shard_index.py's derive_mounted_shard_records): the scope gate
    # now runs unconditionally, even for a manifest-less mounted vault —
    # this suite's fixtures predate that filter and never set
    # extraction_scope at all. Default to a legitimately public scope so
    # these plants keep testing what they've always tested (shard-caching
    # mechanics: pin-matching, incremental reuse, staleness) rather than
    # silently colliding with the unrelated boundary filter. Any test that
    # wants a specific/absent scope still can via extra_fm.
    if "extraction_scope" not in extra_fm:
        extra_fm = f"extraction_scope: ship\n{extra_fm}"
    fp = root / "vault" / "files" / f"{uid}.md"
    fm = (
        f"---\n"
        f"uid: {uid}\n"
        f"type: {ftype}\n"
        f"title: \"{title}\"\n"
        f"status: active\n"
        f"state: active\n"
        f"created: '2026-07-08'\n"
        f"modified: '2026-07-08'\n"
        f"{extra_fm}"
        f"---\n\n# {title}\n"
    )
    fp.write_text(fm, encoding="utf-8")
    return fp


def _commit_all(root: Path, message: str = "commit") -> str:
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", message, cwd=root)
    return _git("rev-parse", "HEAD", cwd=root)


def _init_fixture_studio_root(tmp: Path, name: str = "studio") -> Path:
    """A fixture STUDIO-ROOT (the composing side): its own vault/files/,
    an empty vault/00-index.jsonl parent dir, and a .tropo-studio/ dir
    ready to receive compose.lock + shards/. This is the counterpart
    fixture-builder test_mount_gate_409ef1cc.py's grounding noted was
    missing — the composing side, not the mounted-source side."""
    root = tmp / name
    (root / "vault" / "files").mkdir(parents=True)
    (root / ".tropo-studio").mkdir(parents=True)
    return root


def _write_compose_lock(root: Path, vaults: dict) -> Path:
    lock_path = root / ".tropo-studio" / "compose.lock"
    lock_path.write_text(json.dumps({"schema_version": 1, "vaults": vaults}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return lock_path


def _compose_lock_record(vault_uid: str, mount_root: Path, resolved_commit: Optional[str] = None) -> dict:
    commit = resolved_commit or _git("rev-parse", "HEAD", cwd=mount_root)
    return {
        "vault_uid": vault_uid,
        "resolved_commit": commit,
        "manifest_version": "1.0.0",
        "contract_hash": "fixture-hash",
        "contract": {"registered_types": ["task"], "capsule_versions": {}, "capabilities": []},
        "consent": {"consented": False, "capability_set": []},
        "name_prefix": vault_uid,
        "mounted_at": "2026-07-08T00:00:00Z",
        "mounted_by": "test",
        "mount_path": str(mount_root),
        "manifest_kind": "knowledgebase",
    }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


class TestShardIndexC6f6bea4(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="shard_index_fixture_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -----------------------------------------------------------------
    # AC-1: SAME LOCKFILE => ZERO SHARD REBUILD.
    # -----------------------------------------------------------------
    def test_ac1_same_lockfile_zero_shard_rebuild_identical_output(self) -> None:
        studio = _init_fixture_studio_root(self.tmp, "studio_ac1")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_ac1")
        _write_governed_file(mounted_a, "aaaa1111", "Mounted A task 1")
        commit_a = _commit_all(mounted_a, "initial")

        mounted_b = _init_fixture_mounted_vault(self.tmp, "mounted_b_ac1")
        _write_governed_file(mounted_b, "bbbb2222", "Mounted B task 1")
        commit_b = _commit_all(mounted_b, "initial")

        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a),
            "bbbb2222": _compose_lock_record("bbbb2222", mounted_b, commit_b),
        })

        # First rebuild: both shards are NEW -> both derived.
        mounted_records_1, statuses_1 = shard_index.resolve_shards(studio, process_file, "2026-07-08T00:00:00Z")
        self.assertEqual({s.action for s in statuses_1}, {"derived"})
        self.assertEqual(len(mounted_records_1), 2)

        # Second rebuild: compose.lock UNCHANGED -> both shards REUSED, zero re-derivations.
        mounted_records_2, statuses_2 = shard_index.resolve_shards(studio, process_file, "2026-07-08T00:05:00Z")
        derived_count = sum(1 for s in statuses_2 if s.action == "derived")
        reused_count = sum(1 for s in statuses_2 if s.action == "reused")
        self.assertEqual(derived_count, 0, statuses_2)
        self.assertEqual(reused_count, 2, statuses_2)

        # Byte-identical composed output: same UIDs, same content, same segment-eligible rows.
        uids_1 = sorted(r["uid"] for r in mounted_records_1)
        uids_2 = sorted(r["uid"] for r in mounted_records_2)
        self.assertEqual(uids_1, uids_2)
        by_uid_1 = {r["uid"]: r for r in mounted_records_1}
        by_uid_2 = {r["uid"]: r for r in mounted_records_2}
        for uid in uids_1:
            self.assertEqual(
                json.dumps(by_uid_1[uid], sort_keys=True),
                json.dumps(by_uid_2[uid], sort_keys=True),
                f"shard row for {uid} changed across a reuse-only rebuild",
            )

        # The cached .meta commit for each shard equals the pin.
        for uid, commit in (("aaaa1111", commit_a), ("bbbb2222", commit_b)):
            meta = shard_index.read_shard_meta(studio, uid)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["resolved_commit"], commit)

    # -----------------------------------------------------------------
    # AC-2: CHANGED PIN RE-INDEXES ONLY THAT SHARD.
    # -----------------------------------------------------------------
    def test_ac2_changed_pin_reindexes_only_that_shard(self) -> None:
        studio = _init_fixture_studio_root(self.tmp, "studio_ac2")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_ac2")
        _write_governed_file(mounted_a, "aaaa1111", "A v1")
        commit_a1 = _commit_all(mounted_a, "v1")

        mounted_b = _init_fixture_mounted_vault(self.tmp, "mounted_b_ac2")
        _write_governed_file(mounted_b, "bbbb2222", "B v1")
        commit_b1 = _commit_all(mounted_b, "v1")

        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a1),
            "bbbb2222": _compose_lock_record("bbbb2222", mounted_b, commit_b1),
        })

        # Prime the cache (both derived).
        shard_index.resolve_shards(studio, process_file, "2026-07-08T00:00:00Z")
        meta_b_before = shard_index.read_shard_meta(studio, "bbbb2222")

        # Advance ONLY vault A's pin: new commit on mounted_a's repo.
        _write_governed_file(mounted_a, "aaaa1111", "A v2 — changed")
        commit_a2 = _commit_all(mounted_a, "v2")
        self.assertNotEqual(commit_a1, commit_a2)

        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a2),
            "bbbb2222": _compose_lock_record("bbbb2222", mounted_b, commit_b1),  # unchanged
        })

        mounted_records, statuses = shard_index.resolve_shards(studio, process_file, "2026-07-08T00:10:00Z")
        by_uid_status = {s.vault_uid: s for s in statuses}
        self.assertEqual(by_uid_status["aaaa1111"].action, "derived", statuses)
        self.assertEqual(by_uid_status["bbbb2222"].action, "reused", statuses)

        # B's cache file was NOT rewritten (same meta content as before).
        meta_b_after = shard_index.read_shard_meta(studio, "bbbb2222")
        self.assertEqual(meta_b_before, meta_b_after)

        # Composed output reflects ONLY A's delta.
        by_uid = {r["uid"]: r for r in mounted_records}
        self.assertEqual(by_uid["aaaa1111"]["title"], "A v2 — changed")
        self.assertEqual(by_uid["bbbb2222"]["title"], "B v1")

    # -----------------------------------------------------------------
    # AC-3: UNION CORRECTNESS + SEGMENT TAGS PRESERVED.
    # -----------------------------------------------------------------
    def test_ac3_union_correctness_and_segment_tags_preserved(self) -> None:
        studio = _init_fixture_studio_root(self.tmp, "studio_ac3")
        # Local shard content: one governed file directly in the studio's own vault/files/.
        _write_governed_file(studio, "cccc3333", "Local studio task")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_ac3")
        _write_governed_file(mounted_a, "aaaa1111", "Mounted A task")
        commit_a = _commit_all(mounted_a, "v1")

        mounted_b = _init_fixture_mounted_vault(self.tmp, "mounted_b_ac3")
        _write_governed_file(mounted_b, "bbbb2222", "Mounted B task")
        commit_b = _commit_all(mounted_b, "v1")

        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a),
            "bbbb2222": _compose_lock_record("bbbb2222", mounted_b, commit_b),
        })

        # Run the FULL rebuild_index() (dry-run — apply_writes=False is fine, the shard
        # reconciliation + union happens regardless of apply_writes; only the FINAL
        # vault/00-index.jsonl write is apply-gated) against the fixture studio-root.
        rc = rebuild_index(studio, apply_writes=True)
        self.assertEqual(rc, 0)

        composed = _read_jsonl(studio / "vault" / "00-index.jsonl")
        by_uid = {r["uid"]: r for r in composed}

        # All three records present.
        self.assertIn("cccc3333", by_uid)
        self.assertIn("aaaa1111", by_uid)
        self.assertIn("bbbb2222", by_uid)

        # No duplicate UIDs (one-clone guarantee).
        uids = [r["uid"] for r in composed]
        self.assertEqual(len(uids), len(set(uids)), "duplicate UID in composed index")

        # Every record carries a segment tag (Gardener pass ran over the full union).
        for uid in ("cccc3333", "aaaa1111", "bbbb2222"):
            self.assertIn("segment", by_uid[uid], f"{uid} missing segment tag after union")
            self.assertTrue(by_uid[uid]["segment"], f"{uid} has an empty segment tag")

    # -----------------------------------------------------------------
    # AC-4: STALENESS GUARD FAILS CLOSED.
    # -----------------------------------------------------------------
    def test_ac4_staleness_guard_fails_closed_missing_shard_cache(self) -> None:
        studio = _init_fixture_studio_root(self.tmp, "studio_ac4a")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_ac4a")
        _write_governed_file(mounted_a, "aaaa1111", "A task")
        commit_a = _commit_all(mounted_a, "v1")

        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a),
        })

        # Validator BEFORE any rebuild has ever run: no shard cache exists yet -> cannot-compose.
        # (mount_path IS reachable here — this specifically proves the VALIDATOR's read-only
        # "cache absent" check fires even when a writer COULD self-heal it; the validator must
        # never assume a future rebuild will happen and stay silent in the meantime.)
        findings, checked, violations = check_shard_index_consistency(studio)
        self.assertEqual(checked, 1)
        self.assertEqual(violations, 1, findings)
        self.assertTrue(any("aaaa1111" in f and "CANNOT-COMPOSE" in f for f in findings), findings)
        self.assertTrue(any("[WARN]" in f for f in findings), findings)

        # The writer's reconciliation path (resolve_shards) is DIFFERENT from the read-only
        # validator: when mount_path IS reachable, a missing/stale cache is exactly the
        # "new shard" case, which it correctly self-heals by deriving (not cannot-compose) —
        # this is the documented "changed/new -> re-derive" rule, not a staleness failure.
        mounted_records, statuses = shard_index.resolve_shards(studio, process_file, "2026-07-08T00:00:00Z")
        self.assertEqual(len(mounted_records), 1)
        self.assertEqual(statuses[0].action, "derived")

        # Now that a real rebuild has happened (cache primed), the validator's finding clears.
        rc = rebuild_index(studio, apply_writes=True)
        self.assertEqual(rc, 0)
        findings2, checked2, violations2 = check_shard_index_consistency(studio)
        self.assertEqual(violations2, 0, findings2)

    def test_ac4_staleness_guard_fails_closed_missing_cache_AND_unreachable_mount(self) -> None:
        """The genuinely un-self-healing case: shard cache missing AND
        mount_path unreachable. Here BOTH the validator AND the writer's
        own resolve_shards() must agree: cannot-compose, zero rows
        contributed — there is no reachable source to derive from."""
        studio = _init_fixture_studio_root(self.tmp, "studio_ac4c")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_ac4c")
        _write_governed_file(mounted_a, "aaaa1111", "A task")
        commit_a = _commit_all(mounted_a, "v1")

        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a),
        })
        shutil.rmtree(mounted_a)  # mount_path unreachable from the start; cache also absent

        findings, checked, violations = check_shard_index_consistency(studio)
        self.assertEqual(violations, 1, findings)
        self.assertTrue(any("aaaa1111" in f and "CANNOT-COMPOSE" in f for f in findings), findings)

        mounted_records, statuses = shard_index.resolve_shards(studio, process_file, "2026-07-08T00:00:00Z")
        self.assertEqual(len(mounted_records), 0)
        self.assertEqual(statuses[0].action, "cannot-compose")

        # A rebuild also does not crash and does not fabricate rows for this vault_uid.
        rc = rebuild_index(studio, apply_writes=True)
        self.assertEqual(rc, 0)
        composed = _read_jsonl(studio / "vault" / "00-index.jsonl")
        self.assertFalse(any(r["uid"] == "aaaa1111" for r in composed))

    def test_ac4_staleness_guard_fails_closed_stale_meta_and_unreachable_mount(self) -> None:
        """Argus's adversarial angle: a shard cache that IS present but is
        STALE (meta commit != pin) with an unreachable mount_path must NOT
        be silently served as if complete — this is the direct attempt to
        smuggle a stale/partial shard into the composed index as if it were
        current."""
        studio = _init_fixture_studio_root(self.tmp, "studio_ac4b")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_ac4b")
        _write_governed_file(mounted_a, "aaaa1111", "A v1")
        commit_a1 = _commit_all(mounted_a, "v1")

        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a1),
        })
        # Prime a valid cache at commit_a1.
        rebuild_index(studio, apply_writes=True)
        pre_attack_index = _read_jsonl(studio / "vault" / "00-index.jsonl")
        self.assertTrue(any(r["uid"] == "aaaa1111" for r in pre_attack_index))

        # ATTACK: advance the pin in compose.lock (simulating a new commit on the
        # mounted vault) but then DELETE the mounted vault entirely, so mount_path
        # is unreachable AND the cached .meta is now stale relative to the new pin.
        _write_governed_file(mounted_a, "aaaa1111", "A v2 — should NOT surface")
        commit_a2 = _commit_all(mounted_a, "v2")
        self.assertNotEqual(commit_a1, commit_a2)
        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a2),
        })
        shutil.rmtree(mounted_a)  # mount_path now unreachable

        # Validator must fire CANNOT-COMPOSE (stale cache, unreachable mount_path).
        findings, checked, violations = check_shard_index_consistency(studio)
        self.assertEqual(violations, 1, findings)
        self.assertTrue(any("stale" in f.lower() and "aaaa1111" in f for f in findings), findings)

        # The rebuild's union must EXCLUDE this shard entirely — neither the stale
        # v1 content NOR a phantom v2 may appear as if the index were complete.
        rc = rebuild_index(studio, apply_writes=True)
        self.assertEqual(rc, 0)
        composed = _read_jsonl(studio / "vault" / "00-index.jsonl")
        aaaa_rows = [r for r in composed if r["uid"] == "aaaa1111"]
        self.assertEqual(
            len(aaaa_rows), 0,
            f"a stale/unreachable shard was served into the composed index: {aaaa_rows}",
        )

    # -----------------------------------------------------------------
    # AC-5: SHARD CACHE IS LOCAL/GITIGNORED (I5).
    # -----------------------------------------------------------------
    def test_ac5_shard_cache_gitignored_and_wipe_rebuild_identical(self) -> None:
        # Use the REAL repo's .gitignore rules against a FIXTURE git repo (never
        # the real repo itself) to prove .tropo-studio/shards/ is actually ignored
        # by the pattern this build added.
        studio = _init_fixture_studio_root(self.tmp, "studio_ac5")
        _git("init", "-q", cwd=studio)
        _git("config", "user.email", "fixture@test.local", cwd=studio)
        _git("config", "user.name", "fixture", cwd=studio)
        real_gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".tropo-studio/shards/", real_gitignore,
                      ".gitignore must declare .tropo-studio/shards/ (this build's AMENDED target)")
        (studio / ".gitignore").write_text(real_gitignore, encoding="utf-8")
        _commit_all(studio, "initial (gitignore only)")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_ac5")
        _write_governed_file(mounted_a, "aaaa1111", "A task")
        commit_a = _commit_all(mounted_a, "v1")
        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a),
        })

        rc = rebuild_index(studio, apply_writes=True)
        self.assertEqual(rc, 0)
        shards_dir = studio / ".tropo-studio" / "shards"
        self.assertTrue(shards_dir.is_dir())
        self.assertTrue(any(shards_dir.iterdir()), "shard cache should be non-empty after a rebuild with a mount")

        # git check-ignore: the shard dir itself is ignored.
        result = subprocess.run(
            ["git", "check-ignore", "-q", ".tropo-studio/shards/aaaa1111.jsonl"],
            cwd=str(studio), capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, "shard cache file is NOT gitignored per the fixture .gitignore")

        # git status --porcelain: nothing under .tropo-studio/shards/ shows as untracked-but-visible
        # (i.e. it's excluded from status entirely, not merely untracked).
        status = subprocess.run(
            ["git", "status", "--porcelain", "--ignored=no"],
            cwd=str(studio), capture_output=True, text=True,
        )
        self.assertNotIn(".tropo-studio/shards", status.stdout,
                          f"shard cache leaked into git status: {status.stdout}")

        composed_before = _read_jsonl(studio / "vault" / "00-index.jsonl")

        # WIPE the entire shard cache dir and do a full rebuild.
        shutil.rmtree(shards_dir)
        self.assertFalse(shards_dir.exists())
        rc2 = rebuild_index(studio, apply_writes=True)
        self.assertEqual(rc2, 0)
        self.assertTrue(shards_dir.is_dir(), "rebuild must reconstruct the shard cache from source")

        composed_after = _read_jsonl(studio / "vault" / "00-index.jsonl")
        uids_before = sorted(r["uid"] for r in composed_before)
        uids_after = sorted(r["uid"] for r in composed_after)
        self.assertEqual(uids_before, uids_after)
        by_uid_before = {r["uid"]: r for r in composed_before}
        by_uid_after = {r["uid"]: r for r in composed_after}
        for uid in uids_before:
            self.assertEqual(
                json.dumps(by_uid_before[uid], sort_keys=True),
                json.dumps(by_uid_after[uid], sort_keys=True),
                f"record {uid} differs after wipe-and-rebuild",
            )

    # -----------------------------------------------------------------
    # AC-6: REMOVED MOUNT DROPS ITS SHARD.
    # -----------------------------------------------------------------
    def test_ac6_removed_mount_drops_its_shard(self) -> None:
        studio = _init_fixture_studio_root(self.tmp, "studio_ac6")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_ac6")
        _write_governed_file(mounted_a, "aaaa1111", "A task")
        commit_a = _commit_all(mounted_a, "v1")

        mounted_b = _init_fixture_mounted_vault(self.tmp, "mounted_b_ac6")
        _write_governed_file(mounted_b, "bbbb2222", "B task")
        commit_b = _commit_all(mounted_b, "v1")

        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a),
            "bbbb2222": _compose_lock_record("bbbb2222", mounted_b, commit_b),
        })
        rc = rebuild_index(studio, apply_writes=True)
        self.assertEqual(rc, 0)
        composed_before = _read_jsonl(studio / "vault" / "00-index.jsonl")
        self.assertTrue(any(r["uid"] == "bbbb2222" for r in composed_before))
        self.assertTrue(shard_index.shard_jsonl_path(studio, "bbbb2222").exists())

        # Unmount B: remove its record from compose.lock.
        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a),
        })

        rc2 = rebuild_index(studio, apply_writes=True)
        self.assertEqual(rc2, 0)
        composed_after = _read_jsonl(studio / "vault" / "00-index.jsonl")
        self.assertFalse(any(r["uid"] == "bbbb2222" for r in composed_after),
                          "unmounted vault's records are still present in the composed index")
        self.assertTrue(any(r["uid"] == "aaaa1111" for r in composed_after),
                         "unrelated still-mounted vault's records were dropped too")

        # The cache itself is retired (no dangling shard files left behind).
        self.assertFalse(shard_index.shard_jsonl_path(studio, "bbbb2222").exists(),
                          "retired shard's .jsonl cache file was not removed")
        self.assertFalse(shard_index.shard_meta_path(studio, "bbbb2222").exists(),
                          "retired shard's .meta cache file was not removed")


    # -----------------------------------------------------------------
    # SECURITY-REVIEW REGRESSION PLANTS (2026-07-08) — 3 real findings from
    # adversarial verify, all confirmed and fixed. Each plant proves the
    # specific attack is now caught, not just that the happy path holds.
    # -----------------------------------------------------------------
    def test_crash_consistency_desynchronized_meta_and_jsonl_detected(self) -> None:
        """DEDICATED REGRESSION PLANT: write_shard()'s two os.replace calls
        (jsonl, then meta) are not one atomic transaction. Simulate the
        exact crash window: a valid cache is primed, then the .jsonl content
        is overwritten DIRECTLY (bypassing write_shard entirely — modeling
        'jsonl swap succeeded, meta swap did not run yet') while .meta's
        resolved_commit and jsonl_sha256 still describe the OLD content.
        Both the validator (staleness_findings/check_shard_index_consistency)
        and the writer's own reuse decision (resolve_shards) must treat this
        as cannot-compose / not-reusable — commit-string agreement alone
        must NOT be trusted."""
        studio = _init_fixture_studio_root(self.tmp, "studio_crashconsist")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_crashconsist")
        _write_governed_file(mounted_a, "aaaa1111", "A v1")
        commit_a = _commit_all(mounted_a, "v1")

        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a),
        })
        # Prime a genuinely valid cache.
        shard_index.resolve_shards(studio, process_file, "2026-07-08T00:00:00Z")
        meta_before = shard_index.read_shard_meta(studio, "aaaa1111")
        self.assertIsNotNone(meta_before)
        self.assertIn("jsonl_sha256", meta_before, "fix must add jsonl_sha256 to the .meta record shape")

        # SIMULATE THE CRASH: directly overwrite the .jsonl content (as if a
        # NEW derivation's jsonl-swap succeeded) WITHOUT going through
        # write_shard() — so .meta (still describing the OLD content) is now
        # desynchronized from the live .jsonl, while resolved_commit in
        # .meta still happens to equal the current pin (the exact scenario:
        # a later re-pin lands back on a commit whose meta is stale-paired).
        jsonl_path = shard_index.shard_jsonl_path(studio, "aaaa1111")
        desynced_row = {"uid": "aaaa1111", "type": "task", "title": "INJECTED — should never surface", "path": "mounted/aaaa1111/vault/files/aaaa1111.md"}
        jsonl_path.write_text(json.dumps(desynced_row) + "\n", encoding="utf-8")

        # Validator must catch the desync — never silently trust commit-match alone.
        findings, checked, violations = check_shard_index_consistency(studio)
        self.assertEqual(violations, 1, findings)
        self.assertTrue(
            any("DESYNCHRONIZED" in f and "aaaa1111" in f for f in findings),
            findings,
        )

        # The writer's OWN reuse decision must also refuse to reuse the desynced cache.
        mounted_records, statuses = shard_index.resolve_shards(studio, process_file, "2026-07-08T00:10:00Z")
        by_uid_status = {s.vault_uid: s for s in statuses}
        self.assertNotEqual(by_uid_status["aaaa1111"].action, "reused", statuses)
        # It self-heals by re-deriving (mount_path IS still reachable) — the injected
        # row must NOT survive into the freshly-derived output.
        titles = [r.get("title") for r in mounted_records if r.get("uid") == "aaaa1111"]
        self.assertNotIn("INJECTED — should never surface", titles, mounted_records)

    def test_dry_run_writes_nothing_to_shard_cache(self) -> None:
        """DEDICATED REGRESSION PLANT: resolve_shards() previously had no
        apply_writes parameter and always performed real disk writes
        (write_shard/retire_shard) regardless of the caller's --apply flag —
        a plain dry-run CLI invocation would silently write shard-cache
        files, contradicting the tool's own 'DRY-RUN (no writes)' banner.
        Prove a dry-run rebuild against a fixture WITH a real mounted vault
        performs ZERO filesystem writes under .tropo-studio/shards/."""
        studio = _init_fixture_studio_root(self.tmp, "studio_dryrun")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_dryrun")
        _write_governed_file(mounted_a, "aaaa1111", "A task")
        commit_a = _commit_all(mounted_a, "v1")
        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a),
        })

        shards_dir = studio / ".tropo-studio" / "shards"
        self.assertFalse(shards_dir.exists(), "precondition: no shard cache before the dry-run")

        rc = rebuild_index(studio, apply_writes=False)
        self.assertEqual(rc, 0)
        self.assertFalse(
            shards_dir.exists() and any(shards_dir.iterdir()),
            "dry-run (apply_writes=False) must write ZERO shard-cache files",
        )
        self.assertFalse((studio / "vault" / "00-index.jsonl").exists(),
                          "dry-run must also not write the composed index (pre-existing contract)")

        # A REAL (--apply) rebuild afterward DOES populate the cache — proving the
        # dry-run's silence was because of apply_writes gating, not a derivation bug.
        rc2 = rebuild_index(studio, apply_writes=True)
        self.assertEqual(rc2, 0)
        self.assertTrue(shards_dir.is_dir() and any(shards_dir.iterdir()))

    def test_cross_vault_uid_collision_with_matching_type_title_fails_loud(self) -> None:
        """DEDICATED REGRESSION PLANT (HIGH severity): derive_mounted_shard_
        records() previously set a mounted record's `path` to a bare
        'vault/files/<uid>.md' string — identical in shape to a LOCAL
        record's own path. tropo-rebuild-index.py's pre-existing S7
        source-precedence dedup classified both at the SAME tier (path
        prefix 'vault/files/') and, when a local record and a mounted
        record shared a UID AND coincidentally matched type+title, silently
        collapsed them into one — discarding the other vault's genuinely
        distinct document with NO warning, a live one-clone-per-vault-UID
        (I1) violation. Prove this now FAILS LOUD (never silently merges
        two different vaults' records) even when type+title coincide."""
        studio = _init_fixture_studio_root(self.tmp, "studio_crossvault_collision")
        # LOCAL record: same UID, same type+title as the mounted one below.
        _write_governed_file(studio, "c011de00", "Ambiguous Title", ftype="task")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_collision")
        _write_governed_file(mounted_a, "c011de00", "Ambiguous Title", ftype="task")  # SAME uid+type+title, DIFFERENT vault
        commit_a = _commit_all(mounted_a, "v1")
        _write_compose_lock(studio, {
            "c011de00": _compose_lock_record("c011de00", mounted_a, commit_a),
        })

        with self.assertRaises(SystemExit) as ctx:
            rebuild_index(studio, apply_writes=True)
        self.assertEqual(ctx.exception.code, 1)

    def test_cross_vault_uid_collision_different_type_title_still_fails_loud(self) -> None:
        """Sanity companion: the PRE-EXISTING fail-loud path (different
        type/title on a colliding UID) must still fire correctly for a
        local-vs-mounted collision too, not just local-vs-local — confirming
        the fix didn't narrow the existing protection."""
        studio = _init_fixture_studio_root(self.tmp, "studio_crossvault_collision2")
        _write_governed_file(studio, "d022ef11", "Local Title", ftype="task")

        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_collision2")
        _write_governed_file(mounted_a, "d022ef11", "Totally Different Title", ftype="decision")
        commit_a = _commit_all(mounted_a, "v1")
        _write_compose_lock(studio, {
            "d022ef11": _compose_lock_record("d022ef11", mounted_a, commit_a),
        })

        with self.assertRaises(SystemExit) as ctx:
            rebuild_index(studio, apply_writes=True)
        self.assertEqual(ctx.exception.code, 1)

    def test_shard_vault_uid_marker_stripped_from_composed_index(self) -> None:
        """The internal-only `_shard_vault_uid` dedup marker must never leak
        into the final vault/00-index.jsonl — it is dedup-time-only
        provenance, not part of the committed index schema."""
        studio = _init_fixture_studio_root(self.tmp, "studio_marker_strip")
        mounted_a = _init_fixture_mounted_vault(self.tmp, "mounted_a_markerstrip")
        _write_governed_file(mounted_a, "aaaa1111", "A task")
        commit_a = _commit_all(mounted_a, "v1")
        _write_compose_lock(studio, {
            "aaaa1111": _compose_lock_record("aaaa1111", mounted_a, commit_a),
        })
        rc = rebuild_index(studio, apply_writes=True)
        self.assertEqual(rc, 0)
        composed = _read_jsonl(studio / "vault" / "00-index.jsonl")
        for rec in composed:
            self.assertNotIn("_shard_vault_uid", rec, f"internal marker leaked into composed index: {rec}")


if __name__ == "__main__":
    unittest.main()
