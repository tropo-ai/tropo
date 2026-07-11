#!/usr/bin/env python3
"""test_two_machine_sovereignty_44badb55.py — adversarial gauntlet for the
two-machine sovereignty proof + Git Beat 2 federation transport (dev-spec
44badb55, ADR-051, the v1.84 DoD; red-team-hardened 2026-07-08).

Runs entirely against ISOLATED fixture tempdirs: a fixture "team vault" repo
(real `git init`, a real `.tropo/vault-manifest.md`, real commits), a real
bare-repo remote, and a fixture "machine B" clone of that remote — mirroring
the `test_mount_gate_409ef1cc.py` / `test_shard_index_c6f6bea4.py`
convention of real execution against real git plumbing, never a mock.

There are ZERO real published team-vaults in this studio today (the dev-spec's
own grounding — no compose.lock entry has ever completed a publish), so every
plant constructs its own fixture two-machine topology to exercise the real
publish -> push -> pull -> mount -> compose path.

Never points any write-path invocation at the real studio repo
(/Users/mike/git/tropo-studios/argo-os). All writes happen inside
tempfile.mkdtemp() fixture roots, cleaned up in tearDown().
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
PUBLISH_PATH = ROOT / "vault" / "tools" / "tropo-publish.py"
MOUNT_PATH = ROOT / "vault" / "tools" / "tropo-mount.py"
VALIDATE_PATH = ROOT / "vault" / "tools" / "tropo-validate.py"
LIB_DIR = ROOT / "vault" / "tools" / "lib"

sys.path.insert(0, str(LIB_DIR.parent))  # so `import lib.X` / `from lib.segment import ...` resolves

_publish_spec = importlib.util.spec_from_file_location("tropo_publish_under_test_44badb55", str(PUBLISH_PATH))
tropo_publish = importlib.util.module_from_spec(_publish_spec)
_publish_spec.loader.exec_module(tropo_publish)

_mount_spec = importlib.util.spec_from_file_location("tropo_mount_under_test_44badb55", str(MOUNT_PATH))
tropo_mount = importlib.util.module_from_spec(_mount_spec)
_mount_spec.loader.exec_module(tropo_mount)

_validate_spec = importlib.util.spec_from_file_location("tropo_validate_under_test_44badb55", str(VALIDATE_PATH))
tropo_validate = importlib.util.module_from_spec(_validate_spec)
_validate_spec.loader.exec_module(tropo_validate)

from lib import segment as segment_lib  # noqa: E402

check_publish_boundary = tropo_validate.check_publish_boundary


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _git(*args, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


def _init_team_vault(tmp: Path, name: str, vault_uid: str = "aaaabbbb") -> Path:
    """A fresh git-initted fixture team-vault root with a COMPLETE, schema-
    valid vault-manifest.md (required fields per tropo-validate.py's
    _VAULT_MANIFEST_REQUIRED_FIELDS + the sibling-boundary prefix_policy
    rule) and a vault/files/ tree."""
    root = tmp / name
    (root / ".tropo").mkdir(parents=True)
    (root / "vault" / "files").mkdir(parents=True)
    _git("init", "-q", cwd=root)
    _git("config", "user.email", "fixture@test.local", cwd=root)
    _git("config", "user.name", "fixture", cwd=root)

    manifest = (
        "---\n"
        f"uid: {vault_uid}\n"
        "kind: team\n"
        "owner: mike\n"
        "audience: 12345678\n"
        "remote: local\n"
        "prefix_policy:\n"
        "  references: 32067bea\n"
        "publish_policy:\n"
        "  publishers: [mike]\n"
        "curation_policy:\n"
        "  mode: gardener\n"
        "  cadence: daily\n"
        "curator: mike\n"
        "version: 1.0.0\n"
        "status: active\n"
        "contract:\n"
        "  registered_types: [note]\n"
        "  capsule_versions: {core: \"1.0\"}\n"
        "  capabilities: []\n"
        "regulated_acceptance:\n"
        "  accepted: false\n"
        "---\n# Team Vault Manifest\n"
    )
    (root / ".tropo" / "vault-manifest.md").write_text(manifest, encoding="utf-8")
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", "seed manifest", cwd=root)
    return root


def _write_governed_file(root: Path, uid: str, extraction_scope: Optional[str], body: str = "content") -> Path:
    """`uid` is always YAML-quoted so an all-digit fixture uid (e.g.
    "11111111") parses back as a str, matching how real 8-hex UIDs behave
    (they almost always mix in a-f, but a fixture shouldn't rely on that
    coincidence — quoting makes the type deterministic regardless of the
    literal chosen)."""
    fp = root / "vault" / "files" / f"{uid}.md"
    scope_line = f"extraction_scope: {extraction_scope}\n" if extraction_scope is not None else ""
    fm = f'---\nuid: "{uid}"\ntype: note\n{scope_line}---\n{body}\n'
    fp.write_text(fm, encoding="utf-8")
    return fp


def _commit_all(root: Path, message: str = "commit") -> str:
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", message, cwd=root)
    return _git("rev-parse", "HEAD", cwd=root)


def _init_bare_remote(tmp: Path, name: str = "bare-remote.git") -> Path:
    remote = tmp / name
    _git("init", "-q", "--bare", str(remote), cwd=tmp)
    return remote


def _clone_local(src: Path, tmp: Path, name: str) -> Path:
    dest = tmp / name
    _git("clone", "-q", str(src), str(dest), cwd=tmp)
    _git("config", "user.email", "fixture@test.local", cwd=dest)
    _git("config", "user.name", "fixture", cwd=dest)
    return dest


def _receipt(team_vault_root: Path, remote: Path, apply: bool = True, branch: str = "team-main") -> dict:
    return tropo_publish.run_publish(
        team_vault_root=team_vault_root,
        remote=str(remote),
        branch=branch,
        apply=apply,
        committer_name=tropo_publish.FEDERATION_COMMITTER_NAME,
        committer_email=tropo_publish.FEDERATION_COMMITTER_EMAIL,
    )


def _blob_contains(repo_dir: Path, needle: str) -> bool:
    """Scans every blob object in repo_dir's OWN object store for `needle` —
    the real proof private content never crossed, not merely that the
    latest tree doesn't list it (a stale/dangling blob would still be a
    leak)."""
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "cat-file", "--batch-all-objects", "--batch-check"],
        capture_output=True, text=True, timeout=30,
    )
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] != "blob":
            continue
        content_result = subprocess.run(
            ["git", "-C", str(repo_dir), "cat-file", "-p", parts[0]],
            capture_output=True, text=True, timeout=10,
        )
        if needle in content_result.stdout:
            return True
    return False


class TestTwoMachineSovereignty44badb55(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="two_machine_sovereignty_fixture_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- AC1: TWO-MACHINE SYNC (the DoD) --------------------------------

    def test_ac1_two_machine_sync_and_noop_resync(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "11111111", "ship")
        _write_governed_file(team, "22222222", "argo-reference")
        _commit_all(team)

        receipt = _receipt(team, remote)
        self.assertTrue(receipt["applied"])
        self.assertEqual({c["uid"] for c in receipt["crossed"]}, {"11111111"})

        machine_b = _clone_local(remote, self.tmp, "machine-b")
        # A plain clone creates refs/remotes/origin/team-main, not a local
        # branch (the clone's HEAD/default branch is `main`, not
        # `team-main`) — check it out locally, exactly what a real Machine
        # B user does to actually look at the synced content.
        _git("checkout", "-q", "-b", "team-main", "origin/team-main", cwd=machine_b)
        self.assertEqual(_git("rev-parse", "team-main", cwd=machine_b), receipt["new_commit"])
        b_tree = _git("ls-tree", "-r", "--name-only", "team-main", cwd=machine_b)
        self.assertIn("vault/files/11111111.md", b_tree)
        self.assertNotIn("vault/files/22222222.md", b_tree)

        # second sync, nothing changed -> no-op: crossed still reflects the
        # currently-public set (11111111 is still public), but NO new
        # commit is created since the tree is byte-identical to the tip.
        receipt2 = _receipt(team, remote)
        self.assertEqual({c["uid"] for c in receipt2["crossed"]}, {"11111111"})
        self.assertIsNone(receipt2.get("new_commit"))
        self.assertIn("no-op", receipt2.get("note", ""))

    # -- AC2: PUBLIC-ONLY, ALLOWLIST + DEFAULT-DENY, NORMALIZED ---------

    def test_ac2_allowlist_default_deny_normalized_variants(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "a0000001", "ship")
        _write_governed_file(team, "a0000002", "external")
        _write_governed_file(team, "a0000003", None)  # unmarked
        _write_governed_file(team, "a0000004", "argo-private")
        _write_governed_file(team, "a0000005", "argo-reference")
        _write_governed_file(team, "a0000006", "bogus-scope")
        _write_governed_file(team, "a0000007", "Ship")       # case variant
        _write_governed_file(team, "a0000008", " ship ")     # whitespace variant
        _write_governed_file(team, "a0000009", "ｓｈｉｐ")  # fullwidth 'ship'
        _commit_all(team)

        receipt = _receipt(team, remote)
        crossed_uids = {c["uid"] for c in receipt["crossed"]}
        self.assertEqual(
            crossed_uids,
            {"a0000001", "a0000002", "a0000007", "a0000008", "a0000009"},
            "only true-public + normalization variants of true-public scopes should cross",
        )
        held_back_uids = {h["uid"] for h in receipt["held_back"]}
        self.assertEqual(held_back_uids, {"a0000003", "a0000004", "a0000005", "a0000006"})

    def test_ac2_editing_public_frozenset_to_include_private_fails_the_build(self) -> None:
        """A structural regression test: PUBLIC_EXTRACTION_SCOPES must stay a
        code-constant containing exactly {ship, external}. If a future edit
        widens it to include a private-shaped scope, THIS test fails loudly
        rather than the widening silently taking effect."""
        self.assertEqual(segment_lib.PUBLIC_EXTRACTION_SCOPES, frozenset({"ship", "external"}))

    # -- AC3: SEGMENT IS UN-FORGEABLE ------------------------------------

    def test_ac3_hand_edited_segment_and_scope_frontmatter_do_not_govern(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        # A record whose frontmatter carries a bogus `segment:` field and a
        # bogus `extraction_scope: ship` claim, physically inside the team
        # vault's own tree — derive_segment() must still resolve correctly
        # (it never reads a per-record segment field at all), and the
        # legitimate ship-scope claim IS honored on ITS OWN merits (a
        # per-file authored extraction_scope is the intended trust root;
        # see lib/segment.py's module docstring) precisely BECAUSE the
        # segment agrees with this vault's own manifest UID.
        fp = team / "vault" / "files" / "b0000001.md"
        fp.write_text(
            "---\nuid: b0000001\ntype: note\nextraction_scope: ship\nsegment: some-other-vault\n---\ncontent\n",
            encoding="utf-8",
        )
        _commit_all(team)

        rec = {"uid": "b0000001", "extraction_scope": "ship", "path": "vault/files/b0000001.md"}
        derived = segment_lib.derive_segment(rec, team)
        self.assertEqual(derived, "aaaabbbb", "derive_segment must ignore the hand-edited segment: field entirely")

    def test_ac3_foreign_vault_uid_is_refused(self) -> None:
        """derive_segment resolves to the vault_root's OWN manifest uid,
        never a foreign one — a foreign vault claiming the team's UID
        cannot make this function agree, because it derives strictly from
        the vault_root actually passed in."""
        team_a = _init_team_vault(self.tmp, "team-a", vault_uid="aaaaaaaa")
        team_b = _init_team_vault(self.tmp, "team-b", vault_uid="bbbbbbbb")
        rec = {"uid": "c0000001", "extraction_scope": "ship", "path": "vault/files/c0000001.md"}
        self.assertEqual(segment_lib.derive_segment(rec, team_a), "aaaaaaaa")
        self.assertEqual(segment_lib.derive_segment(rec, team_b), "bbbbbbbb")
        self.assertNotEqual(segment_lib.derive_segment(rec, team_a), segment_lib.derive_segment(rec, team_b))

    # -- AC "UN-FORGEABLE NEGATIVE" (file-level, covenant) ---------------

    def test_ac_covenant_private_never_crosses_file_level(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "d0000001", "argo-private", body="PRIVATE SECRET ONE")
        _write_governed_file(team, "d0000002", "argo-reference", body="PRIVATE SECRET TWO")
        _write_governed_file(team, "d0000003", "ship", body="public content")
        _commit_all(team)

        receipt = _receipt(team, remote)
        machine_b = _clone_local(remote, self.tmp, "machine-b")

        for secret in ("PRIVATE SECRET ONE", "PRIVATE SECRET TWO"):
            self.assertFalse(_blob_contains(remote, secret), f"{secret!r} leaked onto the remote's object store")
            self.assertFalse(_blob_contains(machine_b, secret), f"{secret!r} leaked into machine B's clone")
        self.assertTrue(_blob_contains(remote, "public content"))

    # -- AC "UN-FORGEABLE NEGATIVE" (git-history-level, covenant) --------

    def test_ac_covenant_no_private_ancestry_across_publishes(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)

        # A file committed while PRIVATE (never published) ...
        _write_governed_file(team, "e0000001", "argo-reference", body="was private")
        _commit_all(team, "private commit")
        r1 = _receipt(team, remote)
        self.assertEqual(r1["crossed"], [])  # nothing crossed yet

        # ... then re-created PUBLIC (a content edit, not a git history rewrite).
        _write_governed_file(team, "e0000001", "ship", body="now public")
        _commit_all(team, "flip to public")
        r2 = _receipt(team, remote)
        self.assertEqual({c["uid"] for c in r2["crossed"]}, {"e0000001"})
        self.assertIsNone(r2["parent"], "the FIRST publish must be a true orphan root")

        holds, detail = segment_lib.verify_clean_ancestry(team, r2["new_commit"])
        self.assertTrue(holds, detail)

        objects_result = subprocess.run(
            ["git", "-C", str(remote), "rev-list", "--objects", "team-main"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(objects_result.returncode, 0)
        self.assertFalse(_blob_contains(remote, "was private"))

        # A second, ACCUMULATING publish must NOT be a fresh orphan.
        _write_governed_file(team, "e0000002", "ship", body="round 2")
        _commit_all(team, "round 2")
        r3 = _receipt(team, remote)
        self.assertEqual(r3["parent"], r2["new_commit"], "subsequent publishes must accumulate, not re-orphan")

    # -- AC: ADVERSARIAL PATH-ESCAPE --------------------------------------

    def test_ac_path_escape_symlink_hardlink_refused(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)

        outside = self.tmp / "outside-secret"
        outside.mkdir()
        leak = outside / "leak.md"
        leak.write_text("---\nuid: f0000001\ntype: note\nextraction_scope: ship\n---\nESCAPED SECRET\n", encoding="utf-8")
        (team / "vault" / "files" / "symlinked.md").symlink_to(leak)

        _write_governed_file(team, "f0000002", "argo-reference", body="hardlink target")
        _commit_all(team)
        import os
        os.link(team / "vault" / "files" / "f0000002.md", team / "vault" / "files" / "hardlinked.md")

        receipt = _receipt(team, remote)
        # 3, not 2: os.link() raises BOTH paths' st_nlink to 2 — the
        # hardlink SOURCE (f0000002.md) and its new hardlinked.md sibling
        # both get refused as hardlinks, in addition to the symlink. This
        # is the correct, conservative outcome (both paths of the same
        # inode are equally suspect), not a bug to work around.
        self.assertEqual(len(receipt["path_refusals"]), 3)
        self.assertNotIn("f0000001", {c["uid"] for c in receipt["crossed"]})
        self.assertFalse(_blob_contains(remote, "ESCAPED SECRET"))

    # -- AC: PULL-SIDE ENFORCEMENT (B does not trust A) -------------------

    def test_ac_pull_side_shallow_clone_refused_at_mount(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "10000001", "ship")
        _commit_all(team)
        _receipt(team, remote)

        shallow = self.tmp / "shallow-clone"
        _git("clone", "-q", "--depth", "1", f"file://{team}", str(shallow), cwd=self.tmp)
        self.assertEqual(_git("rev-parse", "--is-shallow-repository", cwd=shallow), "true")

        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(
                mount_path=shallow, consent=False, force_remount=False,
                compose_lock_path=self.tmp / "compose.lock", mounted_by="test",
            )
        self.assertIn("SHALLOW", str(ctx.exception))

    def test_ac_pull_side_boundary_violation_refuses_mount(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "10000002", "ship")
        _commit_all(team)
        receipt = _receipt(team, remote)

        # BOUNCE finding #9 (Argus A128, 2026-07-09): tropo-publish.py no
        # longer creates/updates a LOCAL team-main ref as a side effect (it
        # pushes the constructed commit hash directly to the remote) — so
        # this fixture creates one explicitly, simulating a legitimate
        # local tracking ref (e.g. `git fetch origin team-main:team-main`)
        # rather than relying on a publish-time side effect that no longer
        # exists (and, per the bounce, never should have — a local ref a
        # push can leave dangling on failure was exactly finding #9).
        _git("update-ref", "refs/heads/team-main", receipt["new_commit"], cwd=team)

        # Simulate a bypass DIRECTLY VIA GIT PLUMBING — never `git checkout`
        # team-main in team's own working tree, which would hide
        # .tropo/vault-manifest.md (it lives only on `main`) and make
        # run_mount fail at manifest-read, before ever reaching the
        # boundary check this test targets. A real bypass (a bug, a
        # compromised remote, a hand-run git command against the ref)
        # would not touch team's checked-out branch either — it manipulates
        # the ref directly, exactly like this. Reuses tropo_publish's own
        # (already-tested) build_tree() for correct nested-path tree
        # construction rather than hand-rolling raw mktree.
        bad_file = self.tmp / "bad_file_10000003.md"
        bad_file.write_text('---\nuid: "10000003"\ntype: note\nextraction_scope: argo-reference\n---\nbypassed\n', encoding="utf-8")
        bad_tree = tropo_publish.build_tree(team, [{"path": "vault/files/10000003.md", "content_bytes": bad_file.read_bytes()}])
        prior_tip = _git("rev-parse", "team-main", cwd=team)
        bypass_commit = _git("commit-tree", bad_tree, "-p", prior_tip, "-m", "bypass commit", cwd=team)
        _git("update-ref", "refs/heads/team-main", bypass_commit, cwd=team)

        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(
                mount_path=team, consent=False, force_remount=False,
                compose_lock_path=self.tmp / "compose2.lock", mounted_by="test",
            )
        self.assertIn("publish-boundary refusal", str(ctx.exception))

    def test_ac_pull_side_shard_index_excludes_private_records(self) -> None:
        from lib import shard_index

        team = _init_team_vault(self.tmp, "team")
        _write_governed_file(team, "10000004", "ship")
        _write_governed_file(team, "10000005", "argo-reference")
        _commit_all(team)

        def process_file(path: Path):
            text = path.read_text(encoding="utf-8")
            m = re.match(r'^---\n(.*?\n)---\n', text, re.DOTALL)
            if not m:
                return None
            import yaml
            fm = yaml.safe_load(m.group(1))
            return dict(fm) if isinstance(fm, dict) else None

        records = shard_index.derive_mounted_shard_records(team, process_file, "aaaabbbb")
        self.assertEqual({r["uid"] for r in records}, {"10000004"})

    # -- AC: REFLOG + SERVER-TRUST -----------------------------------------

    def test_ac_reflog_enabled_remote_refuses_publish(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _git("config", "core.logallrefupdates", "true", cwd=remote)
        _write_governed_file(team, "20000001", "ship")
        _commit_all(team)

        with self.assertRaises(tropo_publish.PublishRefused) as ctx:
            _receipt(team, remote)
        self.assertIn("reflog ENABLED", str(ctx.exception))

    # -- AC: TOCTOU-CLOSED --------------------------------------------------

    def test_ac_toctou_validation_reads_committed_tree_not_working_tree(self) -> None:
        """check_publish_boundary must re-read the COMMITTED tip via `git
        show`, so a working-tree-only edit made AFTER a publish (never
        committed) must NOT influence the boundary re-check either way."""
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "30000001", "ship")
        _commit_all(team)
        receipt = _receipt(team, remote)
        # BOUNCE finding #9: publish no longer leaves a local team-main ref
        # as a side effect — create one explicitly (simulating a legitimate
        # local tracking fetch) so check_publish_boundary's ref lookup at
        # mount_path=team finds something to audit.
        _git("update-ref", "refs/heads/team-main", receipt["new_commit"], cwd=team)

        # Dirty the working tree with an uncommitted private file AFTER the
        # publish — this must not appear in the boundary re-check at all,
        # since the re-check operates on the committed tip, not the tree.
        _write_governed_file(team, "30000002", "argo-reference", body="uncommitted dirt")

        fixture_studio = self.tmp / "fixture-studio"
        (fixture_studio / ".tropo-studio").mkdir(parents=True)
        (fixture_studio / ".tropo-studio" / "compose.lock").write_text(json.dumps({
            "schema_version": 1,
            "vaults": {"aaaabbbb": {"vault_uid": "aaaabbbb", "resolved_commit": "x", "mount_path": str(team), "remote": str(remote)}},
        }))
        findings, checked, violations = check_publish_boundary(fixture_studio)
        self.assertEqual(checked, 1)
        self.assertEqual(violations, 0, f"an uncommitted dirty-tree file must not affect the committed-tip re-check: {findings}")

    # -- AC: HONEST EXCLUSION RECEIPT ---------------------------------------

    def test_ac_receipt_held_back_carries_no_title_or_body(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "40000001", "argo-reference", body="a very secret body nobody should see in a receipt")
        _commit_all(team)

        receipt = _receipt(team, remote)
        self.assertEqual(receipt["held_back_count"], 1)
        held = receipt["held_back"][0]
        self.assertEqual(set(held.keys()), {"uid", "extraction_scope", "segment"})
        receipt_json = json.dumps(receipt)
        self.assertNotIn("a very secret body", receipt_json)

    # -- AC: DETERMINISM ------------------------------------------------

    def test_ac_determinism_same_input_same_output_across_clones(self) -> None:
        team = _init_team_vault(self.tmp, "team")
        for i in range(5):
            _write_governed_file(team, f"5000000{i}", "ship" if i % 2 == 0 else "argo-reference")
        _commit_all(team)

        remote_a = self.tmp / "remote-a.git"
        _git("init", "-q", "--bare", str(remote_a), cwd=self.tmp)
        remote_b = self.tmp / "remote-b.git"
        _git("init", "-q", "--bare", str(remote_b), cwd=self.tmp)

        # Two independent clones of the SAME committed content, published
        # separately — the crossed set (by uid/scope/segment/hash) must be
        # byte-identical regardless of any filesystem-ordering difference
        # between the two clone operations.
        clone_x = _clone_local(team, self.tmp, "clone-x")
        clone_y = _clone_local(team, self.tmp, "clone-y")
        # both clones need their own vault-manifest (clone carries it; the
        # uid must match for derive_segment to resolve identically)
        receipt_x = _receipt(clone_x, remote_a)
        receipt_y = _receipt(clone_y, remote_b)

        norm = lambda crossed: sorted(
            [{k: v for k, v in c.items()} for c in crossed], key=lambda c: c["uid"]
        )
        self.assertEqual(norm(receipt_x["crossed"]), norm(receipt_y["crossed"]))


class TestBounceRegressions44badb55(unittest.TestCase):
    """Argus A128 HEAVY-verify BOUNCE, 2026-07-09 (event 00006001): 4/6
    adversarial attackers forced a private byte across against the
    original build. One regression plant per HIGH finding, reproducing
    the EXACT leak the fleet found — not a re-test of the original
    (self-consistent) test suite's own assumptions."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="bounce_regression_fixture_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bounce1_manifest_fail_open_via_orphan_branch_no_manifest(self) -> None:
        """Finding #1: the published team-main branch never carries
        .tropo/vault-manifest.md (tropo-publish.py only ever scans
        vault/files/*.md) — a real Machine-B clone reflecting ONLY that
        branch has no manifest to re-read. The prior derive_mounted_shard_
        records failed OPEN in exactly this state (the two-gate filter was
        skipped entirely when no manifest resolved). Prove closed."""
        from lib import shard_index

        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "60000001", "ship")
        _write_governed_file(team, "60000002", "argo-reference", body="PRIVATE VIA NO-MANIFEST STATE")
        _commit_all(team)
        _receipt(team, remote)

        clone_dir = self.tmp / "machine-b-clone"
        _git("clone", "-q", str(remote), str(clone_dir), cwd=self.tmp)
        _git("checkout", "-q", "-b", "team-main", "origin/team-main", cwd=clone_dir)
        self.assertFalse((clone_dir / ".tropo" / "vault-manifest.md").exists(),
                          "fixture invalid — this test requires the published clone to genuinely lack a manifest")

        def process_file(path: Path):
            text = path.read_text(encoding="utf-8")
            m = re.match(r'^---\n(.*?\n)---\n', text, re.DOTALL)
            if not m:
                return None
            import yaml
            fm = yaml.safe_load(m.group(1))
            return dict(fm) if isinstance(fm, dict) else None

        records = shard_index.derive_mounted_shard_records(clone_dir, process_file, "aaaabbbb")
        self.assertEqual(
            {r["uid"] for r in records}, {"60000001"},
            "manifest-less mount must fail CLOSED (exclude everything not provably public), "
            "not open (include everything unfiltered)",
        )

    def test_bounce2_ancestry_poisoning_via_poisoned_ancestor_commit(self) -> None:
        """Finding #2: a private blob committed into an ANCESTOR of the
        team branch (not the tip) stays reachable forever once a later,
        clean-looking commit is built on top of it — the prior
        find_boundary_violations_in_committed_tree checked only the tip's
        tree. Prove closed: poison an ancestor directly via git plumbing
        (bypassing tropo-publish.py, as a bug or compromise would), then
        attempt the next legitimate publish on top of it."""
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "70000001", "ship")
        _commit_all(team)
        receipt1 = _receipt(team, remote)
        self.assertIsNotNone(receipt1["new_commit"])

        poison_file = self.tmp / "poison_70000002.md"
        poison_file.write_text(
            '---\nuid: "70000002"\ntype: note\nextraction_scope: argo-private\n---\nPOISONED ANCESTOR SECRET\n',
            encoding="utf-8",
        )
        poison_tree = tropo_publish.build_tree(team, [
            {"path": "vault/files/70000001.md", "content_bytes": (team / "vault" / "files" / "70000001.md").read_bytes()},
            {"path": "vault/files/70000002.md", "content_bytes": poison_file.read_bytes()},
        ])
        poisoned_commit = _git("commit-tree", poison_tree, "-p", receipt1["new_commit"], "-m", "poisoned ancestor", cwd=team)
        _git("push", str(remote), f"{poisoned_commit}:refs/heads/team-main", cwd=team)

        _write_governed_file(team, "70000003", "ship")
        _commit_all(team)
        with self.assertRaises(tropo_publish.PublishRefused) as ctx:
            _receipt(team, remote)
        self.assertIn("70000002", str(ctx.exception), "the poisoned ancestor must be named in the refusal")

    def test_bounce3_committed_bytes_match_receipt_hash_exactly(self) -> None:
        """Finding #3 'TOCTOU content-swap': the receipt's content_sha256
        must be computed from the EXACT SAME bytes that get committed — a
        prior version read the file's bytes twice (once in enumerate_and_
        filter for the hash, again inside build_tree for hash-object),
        leaving a window where the two reads could disagree. Prove the
        fix: what's actually in the object store at the published commit
        hashes to exactly what the receipt claims."""
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "80000001", "ship", body="authoritative content")
        _commit_all(team)

        receipt = _receipt(team, remote)
        crossed = receipt["crossed"][0]
        show_result = subprocess.run(
            ["git", "-C", str(team), "show", f"{receipt['new_commit']}:{crossed['path']}"],
            capture_output=True, timeout=10,
        )
        self.assertEqual(show_result.returncode, 0)
        self.assertEqual(
            hashlib.sha256(show_result.stdout).hexdigest(), crossed["content_sha256"],
            "the committed blob's bytes must hash to exactly what the receipt claims — one read, not two",
        )

    def test_bounce4_frontmatter_segment_mismatch_refuses(self) -> None:
        """Finding #4 'tautological segment gate': a record's own
        frontmatter `segment:` field, if present, must AGREE with the
        vault's actual uid — a disagreement is the tamper signature and
        must refuse loudly (AC3), never get silently resolved either way."""
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        fp = team / "vault" / "files" / "90000001.md"
        fp.write_text(
            '---\nuid: "90000001"\ntype: note\nextraction_scope: ship\nsegment: deadbeef\n---\nmismatched claim\n',
            encoding="utf-8",
        )
        _commit_all(team)

        with self.assertRaises(tropo_publish.PublishRefused) as ctx:
            _receipt(team, remote)
        self.assertIn("DISAGREES", str(ctx.exception))

    def test_bounce4b_shard_index_also_refuses_frontmatter_segment_mismatch(self) -> None:
        """The pull-side (shard_index) half of finding #4's AC3 fix — same
        mismatch, caught on the read/compose side too, not just publish."""
        from lib import shard_index

        team = _init_team_vault(self.tmp, "team", vault_uid="aaaabbbb")
        fp = team / "vault" / "files" / "90000002.md"
        fp.write_text(
            '---\nuid: "90000002"\ntype: note\nextraction_scope: ship\nsegment: deadbeef\n---\nmismatched claim\n',
            encoding="utf-8",
        )
        _commit_all(team)

        def process_file(path: Path):
            text = path.read_text(encoding="utf-8")
            m = re.match(r'^---\n(.*?\n)---\n', text, re.DOTALL)
            if not m:
                return None
            import yaml
            fm = yaml.safe_load(m.group(1))
            return dict(fm) if isinstance(fm, dict) else None

        with self.assertRaises(ValueError) as ctx:
            shard_index.derive_mounted_shard_records(team, process_file, "aaaabbbb")
        self.assertIn("DISAGREES", str(ctx.exception))

    def test_bounce5_expect_vault_uid_refuses_foreign_claim(self) -> None:
        """Finding #5 'foreign-vault-uid-claim': a vault whose manifest
        claims a UID the caller does NOT expect must be refused —
        --expect-vault-uid is the authenticated cross-check, independent
        of anything the manifest itself asserts."""
        team = _init_team_vault(self.tmp, "team", vault_uid="aaaaaaaa")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "a1000001", "ship")
        _commit_all(team)

        with self.assertRaises(tropo_publish.PublishRefused) as ctx:
            tropo_publish.run_publish(
                team_vault_root=team, remote=str(remote), branch="team-main", apply=True,
                committer_name=tropo_publish.FEDERATION_COMMITTER_NAME,
                committer_email=tropo_publish.FEDERATION_COMMITTER_EMAIL,
                expect_vault_uid="bbbbbbbb",
            )
        self.assertIn("foreign-vault-uid-claim", str(ctx.exception))

        # The matching uid must still succeed.
        receipt = tropo_publish.run_publish(
            team_vault_root=team, remote=str(remote), branch="team-main", apply=True,
            committer_name=tropo_publish.FEDERATION_COMMITTER_NAME,
            committer_email=tropo_publish.FEDERATION_COMMITTER_EMAIL,
            expect_vault_uid="aaaaaaaa",
        )
        self.assertTrue(receipt["applied"])

    def test_bounce6_fifo_named_md_refused(self) -> None:
        """Finding #6 (MEDIUM): a FIFO/device/socket named *.md previously
        passed path_safety_refusal — only symlink-mode was excluded."""
        import os

        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "b1000001", "ship")
        _commit_all(team)
        fifo_path = team / "vault" / "files" / "fifo_file.md"
        os.mkfifo(fifo_path)
        try:
            receipt = _receipt(team, remote)
            self.assertEqual(len(receipt["path_refusals"]), 1)
            self.assertIn("not a regular file", receipt["path_refusals"][0])
        finally:
            fifo_path.unlink()

    def test_bounce9_no_local_ref_created_and_remote_tip_used_as_parent(self) -> None:
        """Finding #9: publish must never leave a local ref for the caller
        to accidentally trust, and the no-op/parent decision must be based
        on the REMOTE's actual tip, not a local mirror of it."""
        team = _init_team_vault(self.tmp, "team")
        remote = _init_bare_remote(self.tmp)
        _write_governed_file(team, "c1000001", "ship")
        _commit_all(team)
        receipt = _receipt(team, remote)
        self.assertTrue(receipt["applied"])

        local_ref = subprocess.run(
            ["git", "-C", str(team), "rev-parse", "--verify", "refs/heads/team-main"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(local_ref.returncode, 0, "publish must not create/update a local team-main ref")

        remote_tip = subprocess.run(
            ["git", "ls-remote", str(remote), "refs/heads/team-main"],
            capture_output=True, text=True, timeout=10,
        ).stdout.split()[0]
        self.assertEqual(remote_tip, receipt["new_commit"])


if __name__ == "__main__":
    unittest.main()
