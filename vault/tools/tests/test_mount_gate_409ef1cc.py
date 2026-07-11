#!/usr/bin/env python3
"""test_mount_gate_409ef1cc.py — adversarial gauntlet for the mount-gate +
compose-lockfile + per-vault-root manifest governed-write gate (dev-spec
409ef1cc, ADR-051 Fork 2, paired test-spec 314b3329).

Runs against ISOLATED fixture vault-roots (fresh tempdirs, each `git init`d
and committed with its own .tropo/vault-manifest.md) rather than any real
mounted vault — there are ZERO real type:vault instances in this studio
today (dev-spec's own grounding), so every plant constructs its own fixture.

Each plant is a REAL execution: fixture files are actually written to disk,
tropo-mount.py is actually invoked (in-process, via its run_mount()
function, so refusal messages and compose.lock contents are asserted
directly — not shelled out to a subprocess and string-matched), and
check_vault_manifest_governed_write_gate (tropo-validate.py) is actually run
against the resulting compose.lock and asserted to fire or stay silent.

"Test-done" = the mechanism runs against real planted fixtures and its
outcome is asserted, not merely that code compiles or a mock agrees with
itself.
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
MOUNT_PATH = ROOT / "vault" / "tools" / "tropo-mount.py"
VALIDATE_PATH = ROOT / "vault" / "tools" / "tropo-validate.py"

_mount_spec = importlib.util.spec_from_file_location("tropo_mount_under_test_409ef1cc", str(MOUNT_PATH))
tropo_mount = importlib.util.module_from_spec(_mount_spec)
_mount_spec.loader.exec_module(tropo_mount)

_validate_spec = importlib.util.spec_from_file_location("tropo_validate_under_test_409ef1cc", str(VALIDATE_PATH))
tropo_validate = importlib.util.module_from_spec(_validate_spec)
_validate_spec.loader.exec_module(tropo_validate)

check_governed_write_gate = tropo_validate.check_vault_manifest_governed_write_gate


def _git(*args, cwd: Path) -> None:
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"


def _init_fixture_vault_root(tmp: Path, name: str) -> Path:
    """A fresh git-initted fixture vault-root with no manifest yet."""
    root = tmp / name
    (root / ".tropo").mkdir(parents=True)
    _git("init", "-q", cwd=root)
    _git("config", "user.email", "fixture@test.local", cwd=root)
    _git("config", "user.name", "fixture", cwd=root)
    return root


def _write_manifest(root: Path, uid: str, version: str = "1.0.0",
                     registered_types=("task",), capsule_versions=None,
                     capabilities=(), kind: str = "knowledgebase",
                     status: str = "active") -> None:
    capsule_versions = capsule_versions if capsule_versions is not None else {"core": "1.0"}
    manifest = {
        "uid": uid,
        "type": "vault",
        "kind": kind,
        "owner": "mike",
        "audience": "bbbb2222",
        "remote": "https://example.com/fixture.git",
        "prefix_policy": {"references": "32067bea"},
        "publish_policy": {"who": "owner"},
        "curation_policy": {"mode": "gardener"},
        "curator": "mike",
        "version": version,
        "status": status,
        "contract": {
            "registered_types": list(registered_types),
            "capsule_versions": capsule_versions,
            "capabilities": list(capabilities),
        },
        "regulated_acceptance": {"accepted": False},
    }
    import yaml
    fm_text = yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False)
    (root / ".tropo" / "vault-manifest.md").write_text(f"---\n{fm_text}---\n\n# Fixture vault\n", encoding="utf-8")


def _commit_all(root: Path, message: str = "commit") -> None:
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", message, cwd=root)


class TestMountGate409ef1cc(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mount_gate_fixture_"))
        self.compose_lock = self.tmp / "compose.lock"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -----------------------------------------------------------------
    # AC-1: off-gate manifest edit is CAUGHT; the same edit through the
    # gate passes. We prove this via compose.lock cross-validation: a
    # gated mount records a contract whose recomputed hash matches
    # contract_hash (passes); a compose.lock record hand-corrupted OFF
    # the gate (simulating an off-gate edit to the pinned state) is
    # caught by check_vault_manifest_governed_write_gate.
    # -----------------------------------------------------------------
    def test_ac1_gated_write_passes_offgate_edit_caught(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac1")
        _write_manifest(root, "aaaa1111")
        _commit_all(root)

        record = tropo_mount.run_mount(
            mount_path=root, consent=False, force_remount=False,
            compose_lock_path=self.compose_lock, mounted_by="test",
        )
        self.assertEqual(record["vault_uid"], "aaaa1111")

        # The gate-written compose.lock passes governed-write validation clean.
        findings, checked, violations = check_governed_write_gate(self.tmp, compose_lock_path=self.compose_lock)
        self.assertEqual(checked, 1)
        self.assertEqual(violations, 0, findings)

        # Now simulate an OFF-GATE edit: hand-mutate the compose.lock record's
        # contract WITHOUT going through tropo-mount.py (direct frontmatter-
        # mutation-equivalent for the lockfile — a hand-edit bypassing the gate).
        lock_data = json.loads(self.compose_lock.read_text())
        lock_data["vaults"]["aaaa1111"]["contract"]["registered_types"].append("SNUCK_IN_OFF_GATE")
        self.compose_lock.write_text(json.dumps(lock_data, indent=2))

        findings2, checked2, violations2 = check_governed_write_gate(self.tmp, compose_lock_path=self.compose_lock)
        self.assertEqual(checked2, 1)
        self.assertEqual(violations2, 1, findings2)
        self.assertTrue(any("off-gate" in f or "hand-edited" in f for f in findings2), findings2)

    def test_ac1_direct_manifest_file_hand_edit_is_caught(self) -> None:
        """Confirmed-finding regression plant (security review 2026-07-08):
        the LITERAL AC-1 scenario — a per-vault-root type:vault manifest
        edited DIRECTLY ON DISK, bypassing tropo-mount.py entirely — must be
        caught. Previously the validator only re-hashed compose.lock's own
        embedded contract against its own contract_hash, which is blind to
        this (compose.lock is untouched; only the manifest file changed).
        """
        root = _init_fixture_vault_root(self.tmp, "vroot_ac1_direct")
        _write_manifest(root, "a1a1a1a1", registered_types=("task", "decision"))
        _commit_all(root)

        record = tropo_mount.run_mount(
            mount_path=root, consent=False, force_remount=False,
            compose_lock_path=self.compose_lock, mounted_by="test",
        )
        self.assertEqual(record["mount_path"], str(root))

        findings, checked, violations = check_governed_write_gate(self.tmp, compose_lock_path=self.compose_lock)
        self.assertEqual(violations, 0, findings)

        # Edit the manifest FILE directly on disk — bypassing tropo-mount.py
        # entirely — narrowing the contract AND injecting a reserved-name
        # shadow (the exact AC-2 dependency-confusion scenario), then commit
        # (so it would be a real, discoverable git state, not just a dirty
        # working tree).
        _write_manifest(root, "a1a1a1a1", registered_types=("task",),
                         capabilities=["mint-id"])
        _commit_all(root, "off-gate direct edit")

        findings2, checked2, violations2 = check_governed_write_gate(self.tmp, compose_lock_path=self.compose_lock)
        self.assertEqual(checked2, 1)
        self.assertGreaterEqual(violations2, 1, findings2)
        self.assertTrue(
            any("LIVE" in f and "off-gate" in f for f in findings2) or
            any("hand-edit" in f for f in findings2),
            findings2,
        )

    # -----------------------------------------------------------------
    # AC-2: dependency-confusion refused; qualified name mounts clean.
    # -----------------------------------------------------------------
    def test_ac2_unqualified_shadowing_name_refused(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac2_bad")
        _write_manifest(root, "cccc3333", capabilities=["mint-id"])
        _commit_all(root)

        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(
                mount_path=root, consent=True, force_remount=False,
                compose_lock_path=self.compose_lock, mounted_by="test",
            )
        self.assertIn("dependency-confusion", str(ctx.exception))
        self.assertIn("mint-id", str(ctx.exception))
        # Refused -> nothing written.
        self.assertFalse(self.compose_lock.exists())

    def test_ac2_case_variant_shadowing_name_refused(self) -> None:
        """Confirmed-finding regression plant (security review 2026-07-08):
        a case-variant of a reserved name (e.g. `Mint-Id` vs the reserved
        `mint-id`) must be refused exactly like the exact-case form —
        dependency-confusion via case/near-miss variants is the textbook
        Birsan-era technique. Previously there was no .casefold()/.lower()
        anywhere in qualification_violations()/reserved_capability_names(),
        so this mounted cleanly.
        """
        root = _init_fixture_vault_root(self.tmp, "vroot_ac2_case")
        _write_manifest(root, "ca5eca5e", capabilities=["Mint-Id"])
        _commit_all(root)

        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(
                mount_path=root, consent=True, force_remount=False,
                compose_lock_path=self.compose_lock, mounted_by="test",
            )
        self.assertIn("dependency-confusion", str(ctx.exception))
        self.assertFalse(self.compose_lock.exists())

        # Also try an all-caps variant for good measure.
        root2 = _init_fixture_vault_root(self.tmp, "vroot_ac2_case2")
        _write_manifest(root2, "ca5eca5f", capabilities=["MINT-ID"])
        _commit_all(root2)
        with self.assertRaises(tropo_mount.MountRefused):
            tropo_mount.run_mount(
                mount_path=root2, consent=True, force_remount=False,
                compose_lock_path=self.compose_lock, mounted_by="test",
            )

    def test_ac2_qualified_name_mounts_clean(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac2_good")
        _write_manifest(root, "dddd4444", capabilities=["dddd4444:mint-id"])
        _commit_all(root)

        record = tropo_mount.run_mount(
            mount_path=root, consent=True, force_remount=False,
            compose_lock_path=self.compose_lock, mounted_by="test",
        )
        self.assertEqual(record["vault_uid"], "dddd4444")
        self.assertIn("dddd4444:mint-id", record["contract"]["capabilities"])


    # -----------------------------------------------------------------
    # AC-2 normalization-variant family (Argus A128 two-sided verify
    # BOUNCE, event 00005962, on the mount-gate BUILT report 00005961):
    # the case-insensitive fix alone (test_ac2_case_variant_shadowing_
    # name_refused above) left whitespace and Unicode-homoglyph variants
    # unrefused — `.casefold()` does not strip whitespace or apply NFKC
    # normalization. A fullwidth 'ｍｉｎｔ－ｉｄ' NFKC-normalizes to the
    # exact reserved string 'mint-id', which is the sharp case: NFKC is
    # itself a standard security-normalization step a real consumer
    # would apply, not an exotic edge case being special-cased away.
    #
    # Every variant below must be REFUSED identically to the exact-case
    # 'mint-id' — the durable fix Argus required ("the test is the fix;
    # the discipline pin isn't"), covering the whole variant family in
    # one parametrized method rather than one more one-off plant.
    # -----------------------------------------------------------------

    # (label, capability_name) — every one must collide with the reserved
    # 'mint-id' capability (vault/tools/tropo-mint-id.py's own `name:`
    # frontmatter field) after _normalize_capability_name's pipeline
    # (NFKC -> strip Cf/Cc -> strip() -> casefold()).
    NORMALIZATION_VARIANTS = [
        ("exact", "mint-id"),
        ("uppercase", "MINT-ID"),
        ("mixed-case", "Mint-Id"),
        ("trailing-space", "mint-id "),
        ("leading-space", " mint-id"),
        ("leading-and-trailing-space", "  mint-id  "),
        ("interior-zero-width-space", "mint-​id"),
        ("interior-zero-width-joiner", "mint‍-id"),
        ("fullwidth-nfkc-homoglyph", "Ｍｉｎｔ－ｉｄ"),  # ｍｉｎｔ－ｉｄ
    ]

    def test_every_normalization_variant_of_reserved_name_is_refused(self) -> None:
        for i, (label, variant) in enumerate(self.NORMALIZATION_VARIANTS):
            with self.subTest(label=label, variant=repr(variant)):
                # Sanity: prove the variant actually collides post-normalization —
                # otherwise a passing refusal-assertion below would be vacuous.
                normalized = tropo_mount._normalize_capability_name(variant)
                self.assertEqual(
                    normalized, "mint-id",
                    f"test fixture bug: variant {label!r} ({variant!r}) does not "
                    f"normalize to 'mint-id' (got {normalized!r}) — the plant "
                    f"wouldn't actually exercise the collision path",
                )

                root = _init_fixture_vault_root(self.tmp, f"vroot_normvariant_{i}")
                _write_manifest(root, f"{i:08x}", capabilities=[variant])
                _commit_all(root)

                with self.assertRaises(tropo_mount.MountRefused, msg=f"variant {label!r} ({variant!r}) mounted clean — normalization bypass") as ctx:
                    tropo_mount.run_mount(
                        mount_path=root, consent=True, force_remount=False,
                        compose_lock_path=self.compose_lock, mounted_by="test",
                    )
                self.assertIn("dependency-confusion", str(ctx.exception))

    def test_qualified_variant_still_mounts_clean(self) -> None:
        """Namespacing must still defeat the collision by construction even
        for a normalization-variant bare name — qualification is checked
        BEFORE the reserved-name comparison, so a qualified fullwidth name
        is never even compared against the reserved set."""
        root = _init_fixture_vault_root(self.tmp, "vroot_normvariant_qualified")
        qualified_fullwidth = "abcd1234:Ｍｉｎｔ－ｉｄ"
        _write_manifest(root, "abcd1234", capabilities=[qualified_fullwidth])
        _commit_all(root)

        record = tropo_mount.run_mount(
            mount_path=root, consent=True, force_remount=False,
            compose_lock_path=self.compose_lock, mounted_by="test",
        )
        self.assertIn(qualified_fullwidth, record["contract"]["capabilities"])

    # -----------------------------------------------------------------
    # AC-3: executable-consent required as a governed write; refused
    # without --consent; admitted + persists to disk (fresh module
    # re-read, proving it's not in-process-only) with --consent.
    # -----------------------------------------------------------------
    def test_ac3_executable_mount_without_consent_refused(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac3")
        _write_manifest(root, "eeee5555", capabilities=["eeee5555:some-tool"])
        _commit_all(root)

        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(
                mount_path=root, consent=False, force_remount=False,
                compose_lock_path=self.compose_lock, mounted_by="test",
            )
        self.assertIn("no --consent was given", str(ctx.exception))
        self.assertFalse(self.compose_lock.exists(), "refused mount must not write compose.lock at all")

    def test_ac3_consent_admits_and_survives_fresh_read(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac3b")
        _write_manifest(root, "ffff6666", capabilities=["ffff6666:some-tool"])
        _commit_all(root)

        record = tropo_mount.run_mount(
            mount_path=root, consent=True, force_remount=False,
            compose_lock_path=self.compose_lock, mounted_by="test-consenter",
        )
        self.assertTrue(record["consent"]["consented"])
        self.assertEqual(record["consent"]["consented_by"], "test-consenter")

        # "Survives a reboot" — re-read compose.lock from a COMPLETELY FRESH
        # process (subprocess, not this test's in-memory state) to prove the
        # consent record is genuinely on disk, not held in-process.
        result = subprocess.run(
            ["python3", "-c",
             f"import json; d = json.load(open('{self.compose_lock}')); "
             f"print(d['vaults']['ffff6666']['consent']['consented'])"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "True")

    def test_ac3_ac4_dirty_working_tree_with_hidden_executable_refused(self) -> None:
        """Confirmed-finding regression plant (security review 2026-07-08):
        a dirty working tree where the COMMITTED manifest (HEAD, what
        resolved_commit pins) declares an executable capability but the
        WORKING TREE (what read_manifest() actually evaluates) shows none —
        must be refused, not silently admitted with consent=False and an
        empty capability_set while pinning a commit whose real content says
        otherwise. This is the confirmed consent-and-reproducibility bypass:
        previously resolve_commit_hash() never checked tree cleanliness and
        read_manifest()/pin evaluation were never cross-verified.
        """
        root = _init_fixture_vault_root(self.tmp, "vroot_ac3ac4_dirty")
        # Commit a manifest WITH an executable capability.
        _write_manifest(root, "d17d17d1", capabilities=["d17d17d1:tool-x"])
        _commit_all(root)

        # Now, WITHOUT committing, overwrite the working tree to show no
        # capabilities at all — simulating an attacker (or accident) hiding
        # the real committed contract from whatever evaluates the working
        # tree at mount time.
        _write_manifest(root, "d17d17d1", capabilities=[])

        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(
                mount_path=root, consent=False, force_remount=False,
                compose_lock_path=self.compose_lock, mounted_by="test",
            )
        msg = str(ctx.exception)
        self.assertTrue("dirty" in msg.lower() or "diverge" in msg.lower(), msg)
        self.assertFalse(self.compose_lock.exists(), "refused mount must not write compose.lock at all")

        # Reverse direction (previously ALSO refused, per the finding's own
        # verification) stays refused: dirty tree ADDS a capability not
        # present at HEAD.
        root2 = _init_fixture_vault_root(self.tmp, "vroot_ac3ac4_dirty_add")
        _write_manifest(root2, "d17d17d2", capabilities=[])
        _commit_all(root2)
        _write_manifest(root2, "d17d17d2", capabilities=["d17d17d2:tool-y"])
        with self.assertRaises(tropo_mount.MountRefused) as ctx2:
            tropo_mount.run_mount(
                mount_path=root2, consent=True, force_remount=False,
                compose_lock_path=self.tmp / "compose_dirty2.lock", mounted_by="test",
            )
        msg2 = str(ctx2.exception)
        self.assertTrue("dirty" in msg2.lower() or "diverge" in msg2.lower(), msg2)

    # -----------------------------------------------------------------
    # AC-4: lockfile pins reproducibly; composing twice from one lockfile
    # yields identical resolved state; unpinned (non-git) mount refused.
    # -----------------------------------------------------------------
    def test_ac4_reproducible_pin_and_unpinned_refused(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac4")
        _write_manifest(root, "11112222")
        _commit_all(root)

        lock1 = self.tmp / "compose1.lock"
        lock2 = self.tmp / "compose2.lock"
        rec1 = tropo_mount.run_mount(mount_path=root, consent=False, force_remount=False,
                                      compose_lock_path=lock1, mounted_by="t")
        rec2 = tropo_mount.run_mount(mount_path=root, consent=False, force_remount=False,
                                      compose_lock_path=lock2, mounted_by="t")
        self.assertEqual(rec1["resolved_commit"], rec2["resolved_commit"])
        self.assertEqual(
            json.loads(lock1.read_text())["vaults"]["11112222"]["resolved_commit"],
            json.loads(lock2.read_text())["vaults"]["11112222"]["resolved_commit"],
        )

        # Unpinned: a mount-path with no .git at all is refused.
        nogit_root = self.tmp / "vroot_ac4_nogit"
        (nogit_root / ".tropo").mkdir(parents=True)
        _write_manifest(nogit_root, "33334444")
        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(mount_path=nogit_root, consent=False, force_remount=False,
                                   compose_lock_path=self.tmp / "compose3.lock", mounted_by="t")
        self.assertIn("not a git repository", str(ctx.exception))

    # -----------------------------------------------------------------
    # AC-5: one-clone-per-vault-UID — second mount of the same vault-UID
    # fails.
    # -----------------------------------------------------------------
    def test_ac5_second_mount_of_same_uid_refused(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac5")
        _write_manifest(root, "55556666")
        _commit_all(root)

        tropo_mount.run_mount(mount_path=root, consent=False, force_remount=False,
                               compose_lock_path=self.compose_lock, mounted_by="t")

        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(mount_path=root, consent=False, force_remount=False,
                                   compose_lock_path=self.compose_lock, mounted_by="t")
        self.assertIn("already has a compose.lock record", str(ctx.exception))
        self.assertIn("one-clone-per-vault-UID", str(ctx.exception))

        # Exactly one record for this UID, never duplicated.
        lock_data = json.loads(self.compose_lock.read_text())
        self.assertEqual(list(lock_data["vaults"].keys()), ["55556666"])

    # -----------------------------------------------------------------
    # AC-6: manifest+contract validated at mount (invalid manifest
    # refused); contract-narrowing without version bump refused; with
    # version bump but no re-consent refused; with both, admitted.
    # -----------------------------------------------------------------
    def test_ac6_invalid_manifest_refused(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac6_invalid")
        # Missing required fields (owner, audience, etc.) -> schema validation fails.
        import yaml
        bad_manifest = {"uid": "77778888", "type": "vault", "kind": "knowledgebase"}
        fm_text = yaml.safe_dump(bad_manifest, sort_keys=False)
        (root / ".tropo" / "vault-manifest.md").write_text(f"---\n{fm_text}---\n\n# bad\n", encoding="utf-8")
        _commit_all(root)

        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(mount_path=root, consent=False, force_remount=False,
                                   compose_lock_path=self.compose_lock, mounted_by="t")
        self.assertIn("schema validation", str(ctx.exception))
        self.assertFalse(self.compose_lock.exists())

    def test_ac6_valid_manifest_admits(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac6_valid")
        _write_manifest(root, "99990000", registered_types=("task", "decision"))
        _commit_all(root)
        record = tropo_mount.run_mount(mount_path=root, consent=False, force_remount=False,
                                        compose_lock_path=self.compose_lock, mounted_by="t")
        self.assertEqual(record["vault_uid"], "99990000")

    def test_ac6_contract_narrowing_without_version_bump_refused(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac6_narrow")
        _write_manifest(root, "aabbccdd", version="1.0.0", registered_types=("task", "decision"))
        _commit_all(root)
        tropo_mount.run_mount(mount_path=root, consent=False, force_remount=False,
                               compose_lock_path=self.compose_lock, mounted_by="t")

        # Narrow the contract (drop "decision"), SAME version.
        _write_manifest(root, "aabbccdd", version="1.0.0", registered_types=("task",))
        _commit_all(root, "narrow no bump")

        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(mount_path=root, consent=True, force_remount=True,
                                   compose_lock_path=self.compose_lock, mounted_by="t")
        self.assertIn("NARROWING", str(ctx.exception))
        self.assertIn("version bump", str(ctx.exception))

        # compose.lock UNCHANGED — still has the original wider contract.
        lock_data = json.loads(self.compose_lock.read_text())
        self.assertIn("decision", lock_data["vaults"]["aabbccdd"]["contract"]["registered_types"])

    def test_ac6_contract_narrowing_with_bump_no_consent_refused(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac6_narrow_bump_noconsent")
        _write_manifest(root, "bbccddee", version="1.0.0", registered_types=("task", "decision"))
        _commit_all(root)
        tropo_mount.run_mount(mount_path=root, consent=False, force_remount=False,
                               compose_lock_path=self.compose_lock, mounted_by="t")

        _write_manifest(root, "bbccddee", version="2.0.0", registered_types=("task",))
        _commit_all(root, "narrow with bump")

        with self.assertRaises(tropo_mount.MountRefused) as ctx:
            tropo_mount.run_mount(mount_path=root, consent=False, force_remount=True,
                                   compose_lock_path=self.compose_lock, mounted_by="t")
        self.assertIn("re-consent", str(ctx.exception))

    def test_ac6_contract_narrowing_with_bump_and_consent_admitted(self) -> None:
        root = _init_fixture_vault_root(self.tmp, "vroot_ac6_narrow_bump_consent")
        _write_manifest(root, "ccddeeff", version="1.0.0", registered_types=("task", "decision"))
        _commit_all(root)
        tropo_mount.run_mount(mount_path=root, consent=False, force_remount=False,
                               compose_lock_path=self.compose_lock, mounted_by="t")

        _write_manifest(root, "ccddeeff", version="2.0.0", registered_types=("task",))
        _commit_all(root, "narrow with bump")

        record = tropo_mount.run_mount(mount_path=root, consent=True, force_remount=True,
                                        compose_lock_path=self.compose_lock, mounted_by="t")
        self.assertEqual(record["manifest_version"], "2.0.0")
        self.assertNotIn("decision", record["contract"]["registered_types"])

        # Validator agrees the resulting compose.lock is clean (hash matches).
        findings, checked, violations = check_governed_write_gate(self.tmp, compose_lock_path=self.compose_lock)
        self.assertEqual(violations, 0, findings)

    # -----------------------------------------------------------------
    # Sanity: check_vault_manifest_governed_write_gate is silent when
    # compose.lock does not exist (this studio's real current state) —
    # proves the new check has NOTHING to flag on unrelated substrate.
    # -----------------------------------------------------------------
    def test_no_compose_lock_is_silent(self) -> None:
        findings, checked, violations = check_governed_write_gate(
            self.tmp, compose_lock_path=self.tmp / "does-not-exist.lock"
        )
        self.assertEqual((findings, checked, violations), ([], 0, 0))

    def test_record_persists_mount_path_and_manifest_kind(self) -> None:
        """Sanity check for the schema amendment (security review 2026-07-08
        fix): compose.lock records now carry mount_path + manifest_kind,
        which is what makes the live-manifest-re-read AC-1 fix and the
        Fork-3 kind-immutability cross-check possible at all."""
        root = _init_fixture_vault_root(self.tmp, "vroot_schema")
        _write_manifest(root, "5c4e5c4e", kind="knowledgebase")
        _commit_all(root)
        record = tropo_mount.run_mount(
            mount_path=root, consent=False, force_remount=False,
            compose_lock_path=self.compose_lock, mounted_by="test",
        )
        self.assertEqual(record["mount_path"], str(root))
        self.assertEqual(record["manifest_kind"], "knowledgebase")

    def test_real_studio_has_no_compose_lock_findings(self) -> None:
        # Integration sanity check against the REAL studio: confirms this
        # check has nothing to flag on the current live vault (0 real
        # type:vault instances, no real compose.lock yet).
        findings, checked, violations = check_governed_write_gate(ROOT)
        self.assertEqual(violations, 0, findings)


if __name__ == "__main__":
    unittest.main()
