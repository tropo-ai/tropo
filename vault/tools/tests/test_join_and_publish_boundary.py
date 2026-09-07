#!/usr/bin/env python3
"""bb3911f5 — the join ceremony and the authorship-aware publish boundary.

The gauntlet for W4/B-5 + B-4: seven ACs, each runnable by its spec-named
selector (the verify commands are the contract, so the file accepts -k
directly — python3 vault/tools/tests/test_join_and_publish_boundary.py -v -k
succession_bundle_atomic, and every AC's name below matches its AC row).

The writer and the reader are built by one spec precisely so AC6 can exist:
a suite that tests them separately proves the parts and not the seam.
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)

_spec = _ilu.spec_from_file_location("join_teammate", TOOLS / "tropo-join-teammate.py")
jt = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(jt)

from lib import gardener  # noqa: E402

OWNER_UID = "111111221a2b"  # fixture-shaped, not a real-mint claim


def _fixture_key():
    key = Ed25519PrivateKey.generate()
    pub_hex = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    return key, pub_hex


def _sign(key, digest_hex: str) -> str:
    return key.sign(bytes.fromhex(digest_hex)).hex()


class JoinFixture:
    """A temp studio with patched module homes and a trusted owner key."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="join-w4-")).resolve()
        self.authority = self.root / ".tropo-studio" / "group-authority"
        self.authority.mkdir(parents=True)
        self.principals_path = self.authority / "principals.jsonl"
        self.groups_dir = self.root / "group-authority" / "groups"
        self.key, self.pub_hex = _fixture_key()
        self.trust = {OWNER_UID: {"ed25519_public_key_hex": self.pub_hex}}
        trust_file = self.root / ".tropo-studio" / "authorities" / \
            "group-authority" / "accepted-trust.json"
        trust_file.parent.mkdir(parents=True)
        trust_file.write_text(json.dumps(self.trust), encoding="utf-8")
        self._patches = [
            mock.patch.object(jt, "PRINCIPALS_FILE", self.principals_path),
            mock.patch.object(jt, "BUNDLE_DIR", self.root / "join-bundles"),
            mock.patch.object(jt, "JOURNAL_FILE",
                               self.root / "join-bundles" / "journal.jsonl"),
            mock.patch.object(jt, "TRUST_FILE", trust_file),
            # THE FIFTH HOME. Its absence is why AC1 closed green over a leg
            # that landed nowhere: with no groups home patched, the "three
            # planted failures, one per leg" were all observed on the ONE file
            # that was ever written (f015bac58b28).
            mock.patch.object(jt, "GROUPS_DIR", self.groups_dir),
        ]
        for p in self._patches:
            p.start()
        # seed: the org owner exists as a resident principal
        # The owner is ARG0-CREW (no residency): an argo-crew-authored twin
        # must derive argo-reference — seeding the owner team-resident would
        # make AC6's negative half fail CORRECTLY (the derivation would be
        # right and the fixture wrong).
        self.principals_path.write_text(json.dumps([{
            "principal_uid": OWNER_UID, "principal_class": "human",
            "status": "active", "display_name": "Fixture Owner",
        }]), encoding="utf-8")

    def mint_uid(self) -> str:
        """A composite uid from the LIVE seam (the flip's generation shape)."""
        return jt._load_mint_tool().mint(1, kind="file")[0]

    def principals_bytes(self) -> bytes:
        return self.principals_path.read_bytes()

    def groups_bytes(self) -> bytes:
        """Every group source under the groups home, as one comparable blob.

        A DIRECTORY digest, not a single file: the first join MINTS a source
        that did not exist, so reading one path would compare absence with
        absence and see nothing. Names are included, so a draft landing under a
        new uid is a difference even when its bytes resemble another's.
        """
        if not self.groups_dir.is_dir():
            return b""
        return b"\0\0".join(
            entry.name.encode("utf-8") + b"\0" + entry.read_bytes()
            for entry in sorted(self.groups_dir.glob("*.json")))

    def cleanup(self):
        for p in self._patches:
            p.stop()


class SuccessionBundleAtomic(unittest.TestCase):
    """AC1 — the join is a succession, applied all-or-none by one gesture."""

    def _prepared(self, fx: JoinFixture):
        # The REAL identity seam (the live composite mint) — unmocked on
        # purpose: the ceremony must run against the seam it will run against.
        return jt.prepare("Fixture Colleague", "fixture-team")

    def test_succession_bundle_atomic(self):
        fx = JoinFixture()
        try:
            path, digest = self._prepared(fx)
            before = fx.principals_bytes()

            # Tampered bundle: alter a leg AFTER prepare — the digest the
            # owner signs no longer matches the bundle bytes on disk.
            bundle = json.loads(path.read_text(encoding="utf-8"))
            bundle["colleague_name"] = "Tampered Name"
            path.write_text(json.dumps(bundle, indent=1, sort_keys=True),
                            encoding="utf-8")
            with self.assertRaises(SystemExit) as refused:
                jt.apply(path, _sign(fx.key, digest))
            self.assertIn("does not verify", str(refused.exception))
            self.assertEqual(fx.principals_bytes(), before,
                             "a tampered bundle landed something")

            # Three planted per-leg failures, each SIGNED by the real owner:
            # the signer signs bad content, so verification passes and the
            # LEG's own validation must refuse before anything lands.
            plants = {
                "principal": lambda b: b["principal"].__setitem__(
                    "principal_uid", "not-a-uid-shape"),
                "group-generation": lambda b: b["group_draft"].__setitem__(
                    "slug", "NOT_KEBAB"),
                "residency": lambda b: b["residency"].__setitem__(
                    "principal_uid", "mismatched-uid"),
            }
            for leg, plant in plants.items():
                with self.subTest(planted_leg=leg):
                    path2, digest2 = self._prepared(fx)
                    bundle2 = json.loads(path2.read_text(encoding="utf-8"))
                    plant(bundle2)
                    path2.write_text(json.dumps(bundle2, indent=1, sort_keys=True),
                                     encoding="utf-8")
                    snapshot = fx.principals_bytes()
                    groups_snapshot = fx.groups_bytes()
                    with self.assertRaises((SystemExit, Exception)) as refused_leg:
                        jt.apply(path2, _sign(fx.key, digest2))
                    self.assertEqual(fx.principals_bytes(), snapshot,
                                     f"the planted {leg} leg landed something")
                    # All-or-none means BOTH governed files, not the one that
                    # happened to be written. Without this line a planted
                    # group-generation failure that leaves a partial draft
                    # behind is missed entirely.
                    self.assertEqual(fx.groups_bytes(), groups_snapshot,
                                     f"the planted {leg} leg left a group source behind")

            # The clean control: one verifying gesture lands all three.
            path3, digest3 = self._prepared(fx)
            journal = jt.apply(path3, _sign(fx.key, digest3))
            self.assertEqual(journal["legs"],
                             ["principal", "group-generation", "residency"])
            # The journal has always CLAIMED three legs. Assert the group one
            # actually landed, in the shape the finalizer reads: a draft at
            # <groups>/<uid>.json with a null semantic_hash. This is the
            # assertion whose absence let the tool ship a leg that wrote
            # nothing while its own journal row named it.
            draft_path = fx.groups_dir / f"{journal['group_draft_uid']}.json"
            self.assertTrue(draft_path.is_file(),
                            "the group-generation leg landed nowhere")
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            self.assertEqual(draft["uid"], journal["group_draft_uid"])
            self.assertEqual(draft["slug"], journal["group_slug"])
            self.assertEqual(draft["status"], "draft")
            self.assertIsNone(draft["semantic_hash"])
            self.assertIn(journal["principal_uid"], draft["members"])
            self.assertEqual(draft["owner"], journal["authorizing_principal_uid"])
            landed = json.loads(fx.principals_path.read_text(encoding="utf-8"))
            by_uid = {r["principal_uid"]: r for r in landed}
            self.assertIn(journal["principal_uid"], by_uid)
            self.assertEqual(by_uid[journal["principal_uid"]]["residency"],
                             "team-resident")
        finally:
            fx.cleanup()

    def test_negative_control_removing_the_group_write_is_seen(self):
        """The world assertion above must CHANGE VERDICT when the write it names
        is removed -- otherwise it proves nothing (boot digest: a green test over
        a blind mechanism is worse than no test). With _write_group_draft mocked
        to a no-op the join still journals three legs, and the draft must be
        ABSENT; if this test ever passes with the draft present, the assertion
        in test_succession_bundle_lands_all_or_none has gone blind. Added by
        argus-a169 2026-09-04 as Control 2 of f015bac58b28.
        """
        fx = JoinFixture()
        try:
            path, digest = self._prepared(fx)
            with mock.patch.object(jt, "_write_group_draft", lambda *a, **k: None):
                journal = jt.apply(path, _sign(fx.key, digest))
            self.assertEqual(journal["legs"],
                             ["principal", "group-generation", "residency"],
                             "the journal still CLAIMS the leg with the writer removed")
            draft_path = fx.groups_dir / f"{journal['group_draft_uid']}.json"
            self.assertFalse(draft_path.is_file(),
                             "the negative control could not remove the group write; "
                             "the world assertion is not proven to see its subject")
            # And the principals leg landed regardless -- the shape AC1 was green over.
            landed = json.loads(fx.principals_path.read_text(encoding="utf-8"))
            self.assertIn(journal["principal_uid"],
                          {r["principal_uid"] for r in landed})
        finally:
            fx.cleanup()


    def test_a_failure_between_the_two_legs_restores_both(self):
        """All-or-none across BOTH governed files, not just the written one.

        The planted-bundle failures above all refuse during validation, before
        anything is written — so they cannot demonstrate that a PARTIAL write is
        undone. This one fails the second leg after the first has landed, which
        is the only shape that leaves residue, and the only one that can tell a
        real restore from an absent one.
        """
        fx = JoinFixture()
        try:
            path, digest = self._prepared(fx)
            principals_before = fx.principals_bytes()
            groups_before = fx.groups_bytes()

            real_write = jt._write_principals

            def failing_second_leg(*a, **k):
                raise RuntimeError("planted: the principals leg fails mid-apply")

            with mock.patch.object(jt, "_write_principals", failing_second_leg):
                with self.assertRaises(RuntimeError):
                    jt.apply(path, _sign(fx.key, digest))

            self.assertEqual(fx.groups_bytes(), groups_before,
                             "the group draft survived a failed apply")
            self.assertEqual(fx.principals_bytes(), principals_before,
                             "principals changed under a failed apply")
            self.assertIs(jt._write_principals, real_write)

            # And the clean path still lands both, so the restore is not simply
            # preventing the write.
            path2, digest2 = self._prepared(fx)
            journal = jt.apply(path2, _sign(fx.key, digest2))
            self.assertTrue((fx.groups_dir / f"{journal['group_draft_uid']}.json").is_file())
            self.assertNotEqual(fx.principals_bytes(), principals_before)
        finally:
            fx.cleanup()

class SignatureIsAuthorization(unittest.TestCase):
    """AC2 — the signature IS the authorization; UIDs, never names."""

    def test_signature_is_authorization(self):
        fx = JoinFixture()
        try:
            path, digest = jt.prepare("Fixture Colleague", "fixture-team")
            before = fx.principals_bytes()

            # Unsigned (garbage) signature refuses.
            with self.assertRaises(SystemExit) as unsigned:
                jt.apply(path, "00" * 64)
            self.assertIn("does not verify", str(unsigned.exception))
            self.assertEqual(fx.principals_bytes(), before)

            # A VALID signature from a key the trust file does not carry refuses.
            stranger, _ = _fixture_key()
            with self.assertRaises(SystemExit) as untrusted:
                jt.apply(path, _sign(stranger, digest))
            self.assertIn("does not verify", str(untrusted.exception))
            self.assertEqual(fx.principals_bytes(), before)

            # The owner's verifying gesture applies, and the journal carries
            # the principal UID — never the display name.
            journal = jt.apply(path, _sign(fx.key, digest))
            self.assertEqual(journal["authorizing_principal_uid"], OWNER_UID)
            rendered = json.dumps(journal)
            self.assertNotIn("Fixture Owner", rendered,
                             "a display name leaked into the journal")
            self.assertIn(OWNER_UID, rendered)
        finally:
            fx.cleanup()


class DerivationPrecedence(unittest.TestCase):
    """AC3 — explicit > authorship residency > path, with the regression pin."""

    def test_derivation_precedence(self):
        teammate_uid = "2222222a2b2c"
        registry = {
            OWNER_UID: {"principal_uid": OWNER_UID, "residency": "team-resident"},
            teammate_uid: {"principal_uid": teammate_uid,
                           "residency": "team-resident"},
            "3333332a2b2c": {"principal_uid": "3333332a2b2c",
                                 "residency": None},  # argo-crew resident
        }
        cases = [
            # explicit wins in BOTH directions
            {"extraction_scope": "private", "created_by": teammate_uid,
             "path": "vault/files/x.md", "want": ("private", False)},
            {"extraction_scope": "argo-reference", "created_by": OWNER_UID,
             "path": "vault/files/x.md", "want": ("argo-reference", False)},
            # teammate-authored, no explicit scope → the team-shareable class
            {"created_by": teammate_uid, "path": "vault/files/x.md",
             "want": ("team-reference", True)},
            # argo-crew-authored twin → exactly today's path derivation
            {"created_by": "3333332a2b2c", "path": "vault/files/x.md",
             "want": ("argo-reference", True)},
        ]
        for case in cases:
            rec = {k: v for k, v in case.items() if k != "want"}
            got = gardener.resolve_effective_scope(rec, registry)
            self.assertEqual(got, case["want"], case)

        # Unattributed record: BYTE-IDENTICAL to the registry=None world —
        # this must not re-stamp one legacy record.
        legacy = {"path": "vault/files/legacy.md", "created": "2026-01-01"}
        self.assertEqual(gardener.resolve_effective_scope(legacy, registry),
                         gardener.resolve_effective_scope(legacy, None),
                         "the authorship leg re-stamped an unattributed record")

        # Safety-net branch: unlisted path, segment-only, scope stays absent —
        # a new precedence leg must not erode never-tag-by-silence.
        unlisted = {"path": "somewhere/else/x.md"}
        scope_none, was_bf = gardener.resolve_effective_scope(unlisted, registry)
        self.assertEqual((scope_none, was_bf),
                         gardener.resolve_effective_scope(unlisted, None))
        self.assertEqual(scope_none, "")


class ResolvesUidsNotNames(unittest.TestCase):
    """AC4 — the derivation reads UIDs, never names."""

    def test_resolves_uids_not_names(self):
        registry = {"4444444a2b2c": {"principal_uid": "4444444a2b2c",
                                         "display_name": "Fixture Colleague",
                                         "residency": "team-resident"}}
        # created_by is the DISPLAY NAME that would string-match — it must
        # NOT resolve; the record falls through to the path rule.
        by_name = {"created_by": "Fixture Colleague", "path": "vault/files/x.md"}
        self.assertEqual(gardener.resolve_effective_scope(by_name, registry),
                         ("argo-reference", True),
                         "a display name was matched as authorship")

        # The UID resolves.
        by_uid = {"created_by": "4444444a2b2c", "path": "vault/files/x.md"}
        self.assertEqual(gardener.resolve_effective_scope(by_uid, registry),
                         ("team-reference", True))


class GenesisPairScopes(unittest.TestCase):
    """AC5 — resolved THROUGH the identity manifest, never fixed uids."""

    def test_genesis_pair_scopes(self):
        mint = jt._load_mint_tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = mint.mint_studio_identity(root=root,
                                                 minted_by="fixture-genesis")
            prefix = identity["mint_prefix"]
            manifest = root / ".tropo" / "studio-identity.md"
            self.assertTrue(manifest.is_file(),
                            "the genesis pair's manifest half is missing")
            # Resolved THROUGH the manifest, by PARSING it — never by
            # string-matching raw YAML (Metis's confirm-on-diff: a raw
            # assertIn('mint_prefix: 4377', ...) argues against the writer's
            # QUOTING, and the quoting is load-bearing: an unquoted all-digit
            # prefix parses as a number, and a leading-zero one as OCTAL —
            # 0015 becomes 13 and the studio's mint namespace shifts under
            # it with nothing raising a hand). The isinstance half is the
            # teeth: equality alone passes for unquoted 4377 == 4377.
            import yaml
            fm_text = manifest.read_text(encoding="utf-8")
            fm = yaml.safe_load(fm_text.split("\n---\n", 1)[0][4:])
            self.assertEqual(fm["mint_prefix"], prefix)
            self.assertIsInstance(fm["mint_prefix"], str,
                                  "the manifest prefix must round-trip as a "
                                  "STRING — a numeric parse is the octal "
                                  "corruption the quoting exists to prevent")
            # Negative control (the hazard itself): an UNQUOTED all-digit
            # prefix does not survive a YAML round-trip as itself.
            unquoted = fm_text.replace(f"mint_prefix: '{prefix}'",
                                       f"mint_prefix: {prefix}")
            if unquoted != fm_text:  # the all-digit case this control exists for
                parsed = yaml.safe_load(unquoted.split("\n---\n", 1)[0][4:])
                self.assertNotIsInstance(parsed["mint_prefix"], str,
                                         "unquoted all-digit prefix parsed as "
                                         "a string — revise this control")
            self.assertEqual(len(prefix), 4,
                             "the issued prefix composes the composite shape")
            uid = mint.mint(1, kind="file", studio_root=root)[0]
            self.assertTrue(uid.startswith(prefix),
                            "a mint did not carry the manifest's issued prefix")


class ComposedFederationLoop(unittest.TestCase):
    """AC6 — THE COMPOSED PATH: join, author, derive, observe the boundary."""

    def test_composed_federation_loop(self):
        fx = JoinFixture()
        try:
            # Ceremony 1: join a fixture teammate end to end.
            with mock.patch.object(jt, "BUNDLE_DIR", fx.root / "join-bundles"):
                path, digest = jt.prepare("Loop Colleague", "loop-team")
            journal = jt.apply(path, _sign(fx.key, digest))
            teammate_uid = journal["principal_uid"]

            # The teammate authors a governed record with no explicit scope.
            teammate_record = {
                "uid": "5555555a2b2c", "path": "vault/files/teammate.md",
                "created_by": teammate_uid,
            }
            # The argo-crew twin of the same record.
            argo_twin = {
                "uid": "6666666a2b2c", "path": "vault/files/twin.md",
                "created_by": OWNER_UID,
            }
            # Legacy unattributed control.
            legacy = {"uid": "7777777a2b2c",
                      "path": "vault/files/legacy.md"}

            def _registry(_vault_root):
                return {r["principal_uid"]: r for r in json.loads(
                    fx.principals_path.read_text(encoding="utf-8"))}

            with mock.patch.object(gardener, "load_principal_registry", _registry):
                records = [teammate_record, argo_twin, legacy]
                gardener.apply_gardener_pass(fx.root, records, apply_writes=False)

            scopes = {r["uid"]: r.get("extraction_scope") for r in records}
            segments = {r["uid"]: r.get("segment") for r in records}

            self.assertEqual(scopes["5555555a2b2c"], "team-reference")
            self.assertEqual(segments["5555555a2b2c"], "os",
                             "the teammate's record did not cross")
            self.assertEqual(scopes["6666666a2b2c"], "argo-reference")
            self.assertNotEqual(segments["6666666a2b2c"], "os",
                                "the argo twin crossed")
            self.assertEqual(scopes["7777777a2b2c"], "argo-reference",
                             "the legacy control was re-stamped")
        finally:
            fx.cleanup()


# AC7 is the manual cold-read walk by the concierge (be9abd46 method: run it,
# do not read it) — no automated case by design; the walk record is the
# acceptance surface.


def _main_with_k() -> int:
    """The spec's verify commands call this file with -k <name> directly —
    the command is the contract, so the file honors it (mapped onto
    unittest's own -k)."""
    argv = sys.argv[1:]
    loader_flags = []
    while "-k" in argv:
        i = argv.index("-k")
        loader_flags += ["-k", argv[i + 1]]
        del argv[i:i + 2]
    program = unittest.main(argv=['join-gauntlet'] + argv + loader_flags,
                            module=__name__, exit=False)
    # A -k selector that matches nothing is RED, not green: unittest reports
    # "Ran 0 tests ... OK" with exit 0, so a typo'd or drifted AC selector
    # would report PASS having executed nothing (Metis's release-wide
    # measurement, 2026-08-31: 41 of 92 v1.94 criteria exposed; four locked
    # specs). Every spec-verify entry point that honors -k owes this refusal.
    if loader_flags and program.result.testsRun == 0:
        print(f"VACUOUS VERIFY: -k {loader_flags[1]!r} matched no tests — "
              "a green from nothing is the most expensive green there is.",
              file=sys.stderr)
        return 1
    return 0 if program.result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_main_with_k())
