"""B4a authenticated-authority plants and the locked AV1 oracle.

This suite pins the ``### Locked authority vector AV1`` block of the B4a
dev-spec (uid ``0bfa771d``) as an independent oracle and proves
``vault/tools/lib/group_authority.py`` reproduces every AV1 byte length,
digest, public key, fingerprint, and Ed25519 signature EXACTLY.

The AV1 literals below are transcribed byte-for-byte from the dev-spec.  They
are NOT produced by the library under test.  The RFC 8032 test-vector-1 seed is
a TEST-only input used to synthesize the signature; production code consumes
only the public key, the out-of-band expected fingerprint, and the signature.

Each hostile plant asserts the exact typed ``GroupErrorCode`` from the stable
refusal vocabulary; a refusal is never converted to empty membership or a
reason-free ``False``.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
import unittest
from collections import OrderedDict
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "b4a-authority-v1"
SCHEMA_PATH = ROOT / ".tropo" / "schema" / "group-authority-v1.schema.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ga = _load("b4a_group_authority_under_test", TOOLS / "lib" / "group_authority.py")
GroupErrorCode = ga.GroupErrorCode
GroupAuthorityError = ga.GroupAuthorityError


# --------------------------------------------------------------------------- #
# AV1 literals — transcribed byte-for-byte from dev-spec 0bfa771d.
# --------------------------------------------------------------------------- #
SEED_HEX = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"

AUTHORITY_UID = "a1b2c3d4"
SIGNING_KEY_UID = "e5f6a7b8"
MIKE_GROUP_UID = "11111111"
MIKE_PRINCIPAL_UID = "7b921d17"

GROUPS_LEN = 203
GROUPS_SHA = "8fac9a9ce622c9b265ee91c1f9176bb9ac6054ea3ee49763bf36b37a4516002f"

PRINCIPAL_CLAIM_LEN = 129
PRINCIPAL_CLAIM_SHA = "fb1c89a9962dcccc4cc1c3b5bc3e06267726854134812495ca5e79a90b78c33d"

PRINCIPALS_LEN = 210
PRINCIPALS_SHA = "9af1ee55eafdc2261db97211ab959c9ca9fdab66d5e70f5c24d178e58fa84d83"

POLICY_LEN = 81
POLICY_SHA = "37fa8842e4ea2810ddd0f0b64eb92d08f54c474c47a8a43868d16d16f009e2f7"

MANIFEST_LEN = 430
MANIFEST_SHA = "047fc3d21d412c7c6197bc6ba9fcca49141557d10d9cf8aa6517cb93dbd143ef"

TUPLE_LEN = 698
TUPLE_SHA = "b7eeceb39d5fabcc42dfed49fef2d9190191800620ff754939be247b14a23c92"

SIGINPUT_LEN = 724
SIGINPUT_SHA = "13acaf1fb525ca99c6c7285b17df049fb09907cb63c75b58cdd13601f248f8d0"

PUBKEY_HEX = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
PUBKEY_B64 = "11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo="
FINGERPRINT = "21fe31dfa154a261626bf854046fd2271b7bed4b6abe45aa58877ef47f9721b9"

SIG_HEX = (
    "cc7cd97413ca3ba41a7aae1bccb7b49414a28b0579fdb2ec59d4cc3126b5e448"
    "7510c8155b8efda6ce949412488d9fd0ad99db5f36a8d4c303f095a77eb6f700"
)
SIG_B64 = "zHzZdBPKO6Qaeq4bzLe0lBSiiwV5/bLsWdTMMSa15Eh1EMgVW479ps6UlBJIjZ/QrZnbXzao1MMD8JWnfrb3AA=="

ENVELOPE_LEN = 802
ENVELOPE_SHA = "14a2885fed3d99f671af09f2a1845f8e8fb65c6d1083a896582f2a64d6f62a8d"

# Source objects the AV1 artifacts are built from.
MIKE_GROUP = {
    "uid": MIKE_GROUP_UID,
    "type": "group",
    "slug": "mike",
    "title": "Mike",
    "description": "Personal work visible to Mike.",
    "owner": MIKE_PRINCIPAL_UID,
    "members": [MIKE_PRINCIPAL_UID],
    "includes_groups": [],
    "status": "active",
    "version": 1,
}
PRINCIPAL_CLAIM = {
    "principal_uid": MIKE_PRINCIPAL_UID,
    "principal_class": "human",
    "status": "active",
    "source_authority_uid": AUTHORITY_UID,
    "source_revision": "1",
}

# A second, distinct Ed25519 key (RFC 8032 test-vector-2 seed) for the
# "wrong public key" plant.
SECOND_SEED_HEX = "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"


def _fx(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _priv() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(SEED_HEX))


def _pub_b64() -> str:
    return ga.public_key_base64(_priv().public_key())


class _AuthorityTestBase(unittest.TestCase):
    """Shared AV1 build helpers and a typed-refusal assertion."""

    maxDiff = None

    def setUp(self) -> None:
        self.seed = bytes.fromhex(SEED_HEX)
        self.priv = _priv()
        self.pub_b64 = _pub_b64()
        self.fingerprint = ga.fingerprint(self.pub_b64)

        # Build the AV1 artifact set from source objects (round-trip build).
        self.groups = ga.build_groups_jsonl([MIKE_GROUP])
        self.principals = ga.build_principals_jsonl([PRINCIPAL_CLAIM])
        self.policy = ga.build_audience_policy(private_group_uid=MIKE_GROUP_UID)
        self.manifest = ga.build_artifact_manifest(
            {
                "groups.jsonl": self.groups,
                "principals.jsonl": self.principals,
                "audience-policy.json": self.policy,
            }
        )
        self.tuple_fields = ga.build_authority_tuple(
            authority_uid=AUTHORITY_UID,
            groups_jsonl=self.groups,
            principals_jsonl=self.principals,
            audience_policy_json=self.policy,
            artifact_manifest_json=self.manifest,
            authority_generation=1,
            signing_key_uid=SIGNING_KEY_UID,
            previous_envelope_sha256=None,
        )
        self.signature = ga.sign_authority_tuple(self.tuple_fields, self.seed)
        self.envelope = ga.canonical_envelope_bytes(
            ga.build_signed_envelope(self.tuple_fields, self.signature)
        )
        self.artifacts = {
            "groups.jsonl": self.groups,
            "principals.jsonl": self.principals,
            "audience-policy.json": self.policy,
            "artifact-manifest.json": self.manifest,
        }

    def _accepted_key(self, **overrides):
        row = ga.accept_authority_key(
            authority_uid=AUTHORITY_UID,
            key_uid=SIGNING_KEY_UID,
            public_key_b64=self.pub_b64,
            expected_fingerprint=self.fingerprint,
            accepted_by=MIKE_PRINCIPAL_UID,
            accepted_at="2026-07-18T00:00:00Z",
        )
        row.update(overrides)
        return row

    def _trust(self, accepted=None, high_water=None):
        return {
            "accepted_keys": [self._accepted_key()] if accepted is None else accepted,
            "high_water": {} if high_water is None else high_water,
        }

    @contextlib.contextmanager
    def assertRefusal(self, code):
        with self.assertRaises(GroupAuthorityError) as ctx:
            yield ctx
        self.assertEqual(
            ctx.exception.code,
            code,
            f"expected {code} but got {ctx.exception.code}: {ctx.exception}",
        )


class Av1OracleTests(_AuthorityTestBase):
    """The library reproduces every AV1 literal, and fixtures match AV1."""

    def test_fixtures_match_av1_lengths_and_digests(self) -> None:
        for name, length, digest in (
            ("groups.jsonl", GROUPS_LEN, GROUPS_SHA),
            ("principals.jsonl", PRINCIPALS_LEN, PRINCIPALS_SHA),
            ("audience-policy.json", POLICY_LEN, POLICY_SHA),
            ("artifact-manifest.json", MANIFEST_LEN, MANIFEST_SHA),
            ("signed-envelope.json", ENVELOPE_LEN, ENVELOPE_SHA),
        ):
            data = _fx(name)
            self.assertEqual(len(data), length, name)
            self.assertEqual(ga.sha256_hex(data), digest, name)
            self.assertTrue(data.endswith(b"\n"), f"{name} must end in one LF")

    def test_library_build_reproduces_av1_artifacts(self) -> None:
        self.assertEqual(len(self.groups), GROUPS_LEN)
        self.assertEqual(ga.sha256_hex(self.groups), GROUPS_SHA)
        self.assertEqual(self.groups, _fx("groups.jsonl"))

        self.assertEqual(len(self.principals), PRINCIPALS_LEN)
        self.assertEqual(ga.sha256_hex(self.principals), PRINCIPALS_SHA)
        self.assertEqual(self.principals, _fx("principals.jsonl"))

        self.assertEqual(len(self.policy), POLICY_LEN)
        self.assertEqual(ga.sha256_hex(self.policy), POLICY_SHA)
        self.assertEqual(self.policy, _fx("audience-policy.json"))

        self.assertEqual(len(self.manifest), MANIFEST_LEN)
        self.assertEqual(ga.sha256_hex(self.manifest), MANIFEST_SHA)
        self.assertEqual(self.manifest, _fx("artifact-manifest.json"))

    def test_principal_source_hash_over_first_five_fields(self) -> None:
        claim_line = ga.canonical_json_line(
            OrderedDict((key, PRINCIPAL_CLAIM[key]) for key in ga.PRINCIPAL_CLAIM_KEYS)
        )
        self.assertEqual(len(claim_line), PRINCIPAL_CLAIM_LEN)
        self.assertEqual(ga.sha256_hex(claim_line), PRINCIPAL_CLAIM_SHA)
        self.assertEqual(ga.principal_source_hash(PRINCIPAL_CLAIM), PRINCIPAL_CLAIM_SHA)
        # The full row carries source_hash as its sixth field.
        row = ga.build_principal_row(PRINCIPAL_CLAIM)
        self.assertEqual(tuple(row.keys()), ga.PRINCIPAL_ROW_KEYS)
        self.assertEqual(row["source_hash"], PRINCIPAL_CLAIM_SHA)

    def test_canonical_tuple_and_signature_input(self) -> None:
        tuple_bytes = ga.canonical_tuple_bytes(self.tuple_fields)
        self.assertEqual(len(tuple_bytes), TUPLE_LEN)
        self.assertEqual(ga.sha256_hex(tuple_bytes), TUPLE_SHA)
        self.assertFalse(tuple_bytes.endswith(b"\n"), "the tuple has no trailing LF")

        sig_input = ga.signature_input(self.tuple_fields)
        self.assertEqual(len(sig_input), SIGINPUT_LEN)
        self.assertEqual(ga.sha256_hex(sig_input), SIGINPUT_SHA)
        self.assertTrue(sig_input.startswith(b"tropo.group-authority.v1\n"))
        self.assertTrue(sig_input.endswith(b"\n"))

    def test_public_key_fingerprint_and_signature_match_av1(self) -> None:
        self.assertEqual(self.pub_b64, PUBKEY_B64)
        self.assertEqual(ga.public_key_raw_bytes(self.pub_b64).hex(), PUBKEY_HEX)
        # The verification-bar fingerprint.
        self.assertEqual(self.fingerprint, FINGERPRINT)

        import base64

        signature_raw = base64.b64decode(self.signature)
        # The verification-bar signature.
        self.assertEqual(signature_raw.hex(), SIG_HEX)
        self.assertEqual(self.signature, SIG_B64)

    def test_signed_envelope_matches_av1_and_fixture(self) -> None:
        self.assertEqual(len(self.envelope), ENVELOPE_LEN)
        self.assertEqual(ga.sha256_hex(self.envelope), ENVELOPE_SHA)
        self.assertEqual(self.envelope, _fx("signed-envelope.json"))

    def test_verify_the_fixture_envelope(self) -> None:
        verified = ga.verify_authority(
            signed_envelope=_fx("signed-envelope.json"),
            artifacts={
                "groups.jsonl": _fx("groups.jsonl"),
                "principals.jsonl": _fx("principals.jsonl"),
                "audience-policy.json": _fx("audience-policy.json"),
                "artifact-manifest.json": _fx("artifact-manifest.json"),
            },
            trust_record=self._trust(),
            expected_fingerprint=FINGERPRINT,
        )
        self.assertEqual(verified.authority_uid, AUTHORITY_UID)
        self.assertEqual(verified.authority_generation, 1)
        self.assertIsNone(verified.previous_envelope_sha256)
        self.assertEqual(verified.corpus_sha256, GROUPS_SHA)
        self.assertEqual(verified.corpus_revision, f"sha256:{GROUPS_SHA}")
        self.assertEqual(verified.principal_directory_sha256, PRINCIPALS_SHA)
        self.assertEqual(verified.audience_policy_sha256, POLICY_SHA)
        self.assertEqual(verified.artifact_identity, MANIFEST_SHA)
        self.assertEqual(verified.signing_key_uid, SIGNING_KEY_UID)
        self.assertEqual(verified.signature, SIG_B64)
        self.assertEqual(verified.envelope_sha256, ENVELOPE_SHA)


class Av1RoundTripTests(_AuthorityTestBase):
    """Positive round trip: build -> sign (test-only) -> verify -> install."""

    def test_build_sign_verify_install_idempotent(self) -> None:
        trust = self._trust()
        verified = ga.verify_authority(
            signed_envelope=self.envelope,
            artifacts=self.artifacts,
            trust_record=trust,
            expected_fingerprint=self.fingerprint,
        )
        self.assertEqual(verified.envelope_sha256, ENVELOPE_SHA)

        trust_after, status = ga.install_authority(trust, verified)
        self.assertEqual(status, ga.InstallStatus.INSTALLED)
        self.assertEqual(
            trust_after["high_water"][AUTHORITY_UID],
            {"authority_generation": 1, "envelope_sha256": ENVELOPE_SHA},
        )
        # The pure install never mutates the input trust record.
        self.assertEqual(trust["high_water"], {})

        # Exact-digest reinstall is idempotent.
        trust_again, status_again = ga.install_authority(trust_after, verified)
        self.assertEqual(status_again, ga.InstallStatus.IDEMPOTENT)
        self.assertEqual(
            trust_again["high_water"][AUTHORITY_UID],
            {"authority_generation": 1, "envelope_sha256": ENVELOPE_SHA},
        )

    def test_accept_key_produces_exact_design_brief_row(self) -> None:
        row = self._accepted_key()
        self.assertEqual(
            tuple(row.keys()),
            (
                "authority_uid",
                "key_uid",
                "algorithm",
                "public_key",
                "sha256_fingerprint",
                "accepted_by",
                "accepted_at",
                "acceptance",
            ),
        )
        self.assertEqual(row["algorithm"], "ed25519")
        self.assertEqual(row["sha256_fingerprint"], FINGERPRINT)
        self.assertEqual(row["acceptance"], "human-fingerprint")

    def test_verified_principal_directory_and_audience_policy(self) -> None:
        directory = ga.verify_principal_directory(self.principals)
        self.assertIn(MIKE_PRINCIPAL_UID, directory)
        resolved = ga.resolve_principal(MIKE_PRINCIPAL_UID, directory)
        self.assertEqual(resolved["principal_uid"], MIKE_PRINCIPAL_UID)

        policy = ga.verify_audience_policy(self.policy)
        self.assertEqual(policy["legacy_aliases"]["private"], MIKE_GROUP_UID)
        self.assertTrue(policy["reserved_os"]["always_readable"])


class NewerGenerationFreshnessTests(_AuthorityTestBase):
    """A newer envelope must chain onto the installed envelope digest."""

    def _envelope_for(self, generation: int, previous: str | None) -> bytes:
        tuple_fields = ga.build_authority_tuple(
            authority_uid=AUTHORITY_UID,
            groups_jsonl=self.groups,
            principals_jsonl=self.principals,
            audience_policy_json=self.policy,
            artifact_manifest_json=self.manifest,
            authority_generation=generation,
            signing_key_uid=SIGNING_KEY_UID,
            previous_envelope_sha256=previous,
        )
        signature = ga.sign_authority_tuple(tuple_fields, self.seed)
        return ga.canonical_envelope_bytes(
            ga.build_signed_envelope(tuple_fields, signature)
        )

    def _verify(self, envelope: bytes):
        return ga.verify_authority(
            signed_envelope=envelope,
            artifacts=self.artifacts,
            trust_record=self._trust(),
            expected_fingerprint=self.fingerprint,
        )

    def test_chained_generations_install_and_broken_chain_refuses(self) -> None:
        trust = self._trust()
        v1 = self._verify(self.envelope)
        trust, status = ga.install_authority(trust, v1)
        self.assertEqual(status, ga.InstallStatus.INSTALLED)

        env2 = self._envelope_for(2, previous=v1.envelope_sha256)
        v2 = self._verify(env2)
        trust, status = ga.install_authority(trust, v2)
        self.assertEqual(status, ga.InstallStatus.INSTALLED)

        # A properly chained gen-3 installs.
        env3 = self._envelope_for(3, previous=v2.envelope_sha256)
        v3 = self._verify(env3)
        chained_trust, status = ga.install_authority(trust, v3)
        self.assertEqual(status, ga.InstallStatus.INSTALLED)

        # A gen-3 whose previous does not match the installed gen-2 envelope
        # is a broken chain / fork of the installed lineage.
        env3_broken = self._envelope_for(3, previous="0" * 64)
        v3_broken = self._verify(env3_broken)
        with self.assertRefusal(GroupErrorCode.AUTHORITY_ROLLBACK):
            ga.install_authority(trust, v3_broken)


class TrustPlantTests(_AuthorityTestBase):
    """Trust-boundary plants: unknown/self/unsupported/fingerprint/key."""

    def test_unknown_key_refuses(self) -> None:
        # A concrete, validly-accepted key exists, but not for this signer.
        other = ga.accept_authority_key(
            authority_uid=AUTHORITY_UID,
            key_uid="aaaaaaaa",
            public_key_b64=self.pub_b64,
            expected_fingerprint=self.fingerprint,
            accepted_by=MIKE_PRINCIPAL_UID,
            accepted_at="2026-07-18T00:00:00Z",
        )
        trust = {"accepted_keys": [other], "high_water": {}}
        with self.assertRefusal(GroupErrorCode.AUTHORITY_UNTRUSTED):
            ga.verify_authority(
                signed_envelope=self.envelope,
                artifacts=self.artifacts,
                trust_record=trust,
                expected_fingerprint=self.fingerprint,
            )

    def test_self_accepted_key_refuses(self) -> None:
        # No trust-on-first-use: an empty store never self-accepts the
        # envelope's own signing key, even though the signature is valid.
        with self.assertRefusal(GroupErrorCode.AUTHORITY_UNTRUSTED):
            ga.verify_authority(
                signed_envelope=self.envelope,
                artifacts=self.artifacts,
                trust_record={"accepted_keys": [], "high_water": {}},
                expected_fingerprint=self.fingerprint,
            )
        # A row minted by self-accept (not an out-of-band human fingerprint)
        # is refused even though its key material is otherwise correct.
        self_accepted = self._accepted_key(acceptance="self-accept")
        with self.assertRefusal(GroupErrorCode.AUTHORITY_UNTRUSTED):
            ga.verify_authority(
                signed_envelope=self.envelope,
                artifacts=self.artifacts,
                trust_record={"accepted_keys": [self_accepted], "high_water": {}},
                expected_fingerprint=self.fingerprint,
            )
        # Acceptance can never be requested with a wildcard/self key identity.
        with self.assertRefusal(GroupErrorCode.AUTHORITY_UNTRUSTED):
            ga.accept_authority_key(
                authority_uid=AUTHORITY_UID,
                key_uid="*",
                public_key_b64=self.pub_b64,
                expected_fingerprint=self.fingerprint,
                accepted_by=MIKE_PRINCIPAL_UID,
                accepted_at="2026-07-18T00:00:00Z",
            )
        # ... nor via a trust-on-first-use acceptance mode.
        with self.assertRefusal(GroupErrorCode.AUTHORITY_UNTRUSTED):
            ga.accept_authority_key(
                authority_uid=AUTHORITY_UID,
                key_uid=SIGNING_KEY_UID,
                public_key_b64=self.pub_b64,
                expected_fingerprint=self.fingerprint,
                accepted_by=MIKE_PRINCIPAL_UID,
                accepted_at="2026-07-18T00:00:00Z",
                acceptance="trust-on-first-use",
            )

    def test_unsupported_algorithm_refuses(self) -> None:
        with self.assertRefusal(GroupErrorCode.AUTHORITY_UNTRUSTED):
            ga.accept_authority_key(
                authority_uid=AUTHORITY_UID,
                key_uid=SIGNING_KEY_UID,
                public_key_b64=self.pub_b64,
                expected_fingerprint=self.fingerprint,
                accepted_by=MIKE_PRINCIPAL_UID,
                accepted_at="2026-07-18T00:00:00Z",
                algorithm="ed448",
            )
        # A trust row carrying an unsupported algorithm is refused at verify.
        bad_algo = self._accepted_key(algorithm="rsa")
        with self.assertRefusal(GroupErrorCode.AUTHORITY_UNTRUSTED):
            ga.verify_authority(
                signed_envelope=self.envelope,
                artifacts=self.artifacts,
                trust_record={"accepted_keys": [bad_algo], "high_water": {}},
                expected_fingerprint=self.fingerprint,
            )

    def test_wrong_fingerprint_refuses(self) -> None:
        wrong = "0" * 64
        with self.assertRefusal(GroupErrorCode.AUTHORITY_FINGERPRINT_MISMATCH):
            ga.verify_authority(
                signed_envelope=self.envelope,
                artifacts=self.artifacts,
                trust_record=self._trust(),
                expected_fingerprint=wrong,
            )
        # Acceptance also refuses when the out-of-band value does not match.
        with self.assertRefusal(GroupErrorCode.AUTHORITY_FINGERPRINT_MISMATCH):
            ga.accept_authority_key(
                authority_uid=AUTHORITY_UID,
                key_uid=SIGNING_KEY_UID,
                public_key_b64=self.pub_b64,
                expected_fingerprint=wrong,
                accepted_by=MIKE_PRINCIPAL_UID,
                accepted_at="2026-07-18T00:00:00Z",
            )

    def test_wrong_public_key_refuses(self) -> None:
        second = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(SECOND_SEED_HEX))
        second_pub = ga.public_key_base64(second.public_key())
        second_fp = ga.fingerprint(second_pub)
        # The accepted key is a different valid key; its fingerprint is
        # self-consistent (so the fingerprint gate passes), but the AV1
        # signature was made by the real key, so verification fails.
        wrong_key = ga.accept_authority_key(
            authority_uid=AUTHORITY_UID,
            key_uid=SIGNING_KEY_UID,
            public_key_b64=second_pub,
            expected_fingerprint=second_fp,
            accepted_by=MIKE_PRINCIPAL_UID,
            accepted_at="2026-07-18T00:00:00Z",
        )
        with self.assertRefusal(GroupErrorCode.AUTHORITY_SIGNATURE_INVALID):
            ga.verify_authority(
                signed_envelope=self.envelope,
                artifacts=self.artifacts,
                trust_record={"accepted_keys": [wrong_key], "high_water": {}},
                expected_fingerprint=second_fp,
            )


class SignatureAndTuplePlantTests(_AuthorityTestBase):
    """Signature, tuple-shape, and canonical-JSON plants."""

    def test_wrong_signature_refuses(self) -> None:
        # A syntactically valid signature over a different tuple.
        alt = OrderedDict(self.tuple_fields)
        alt["authority_uid"] = "b1b2c3d4"
        wrong_sig = ga.sign_authority_tuple(alt, self.seed)
        envelope = ga.canonical_envelope_bytes(
            ga.build_signed_envelope(self.tuple_fields, wrong_sig)
        )
        with self.assertRefusal(GroupErrorCode.AUTHORITY_SIGNATURE_INVALID):
            ga.verify_authority(
                signed_envelope=envelope,
                artifacts=self.artifacts,
                trust_record=self._trust(),
                expected_fingerprint=self.fingerprint,
            )

    def test_internally_inconsistent_signed_tuple_refuses(self) -> None:
        # A trusted key signs a tuple whose corpus_revision does not match its
        # corpus_sha256; the signature verifies but the tuple is structurally
        # invalid.
        bad = OrderedDict(self.tuple_fields)
        bad["corpus_revision"] = "sha256:" + "0" * 64
        bad_sig = ga.sign_authority_tuple(bad, self.seed)
        envelope = ga.canonical_envelope_bytes(ga.build_signed_envelope(bad, bad_sig))
        with self.assertRefusal(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH):
            ga.verify_authority(
                signed_envelope=envelope,
                artifacts=self.artifacts,
                trust_record=self._trust(),
                expected_fingerprint=self.fingerprint,
            )

    def test_duplicate_json_key_refuses(self) -> None:
        envelope_str = _fx("signed-envelope.json").decode("utf-8")
        duplicated = envelope_str.replace(
            '"authority_uid":"a1b2c3d4",',
            '"authority_uid":"a1b2c3d4","authority_uid":"a1b2c3d4",',
            1,
        ).encode("utf-8")
        with self.assertRefusal(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH):
            ga.verify_authority(
                signed_envelope=duplicated,
                artifacts=self.artifacts,
                trust_record=self._trust(),
                expected_fingerprint=self.fingerprint,
            )
        # The canonical parser rejects duplicate keys directly.
        with self.assertRaises(ga.CanonicalJSONError):
            ga.parse_canonical_json(b'{"a":1,"a":2}')

    def test_lone_surrogate_refuses(self) -> None:
        envelope_str = _fx("signed-envelope.json").decode("utf-8")
        surrogate = envelope_str.replace(
            '"signing_key_uid":"e5f6a7b8"',
            '"signing_key_uid":"e5f6a7\\ud800"',
            1,
        ).encode("utf-8")
        with self.assertRefusal(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH):
            ga.verify_authority(
                signed_envelope=surrogate,
                artifacts=self.artifacts,
                trust_record=self._trust(),
                expected_fingerprint=self.fingerprint,
            )
        # The canonical parser rejects escaped lone surrogates directly.
        with self.assertRaises(ga.CanonicalJSONError):
            ga.parse_canonical_json(b'{"x":"\\ud800"}')

    def test_floats_are_forbidden(self) -> None:
        with self.assertRaises(ga.CanonicalJSONError):
            ga.parse_canonical_json(b'{"authority_generation":1.0}')
        with self.assertRaises(ga.CanonicalJSONError):
            ga.canonical_json_bytes({"x": 1.5})

    def test_envelope_key_order_is_enforced(self) -> None:
        parsed = json.loads(_fx("signed-envelope.json").decode("utf-8"))
        reordered = OrderedDict()
        reordered["signature"] = parsed.pop("signature")
        for key, value in parsed.items():
            reordered[key] = value
        scrambled = (
            json.dumps(reordered, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        with self.assertRefusal(GroupErrorCode.AUTHORITY_TUPLE_MISMATCH):
            ga.verify_authority(
                signed_envelope=scrambled,
                artifacts=self.artifacts,
                trust_record=self._trust(),
                expected_fingerprint=self.fingerprint,
            )


class ArtifactPlantTests(_AuthorityTestBase):
    """Corpus/artifact-binding plants: altered claim, truncation."""

    def test_altered_principal_claim_refuses(self) -> None:
        tampered = self.principals.replace(b'"principal_class":"human"', b'"principal_class":"agent-x"')
        self.assertNotEqual(tampered, self.principals)
        artifacts = dict(self.artifacts)
        artifacts["principals.jsonl"] = tampered
        with self.assertRefusal(GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH):
            ga.verify_authority(
                signed_envelope=self.envelope,
                artifacts=artifacts,
                trust_record=self._trust(),
                expected_fingerprint=self.fingerprint,
            )

    def test_truncated_jsonl_refuses(self) -> None:
        artifacts = dict(self.artifacts)
        artifacts["groups.jsonl"] = self.groups[:-8]
        with self.assertRefusal(GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH):
            ga.verify_authority(
                signed_envelope=self.envelope,
                artifacts=artifacts,
                trust_record=self._trust(),
                expected_fingerprint=self.fingerprint,
            )

    def test_manifest_row_disagreeing_with_bytes_refuses(self) -> None:
        # Corrupt the audience-policy bytes so the manifest's row no longer
        # matches, while leaving the (now stale) audience_policy_sha256 pin.
        artifacts = dict(self.artifacts)
        artifacts["audience-policy.json"] = self.policy.replace(b"true", b"fals", 1) + b"e"
        with self.assertRefusal(GroupErrorCode.AUTHORITY_ARTIFACT_MISMATCH):
            ga.verify_authority(
                signed_envelope=self.envelope,
                artifacts=artifacts,
                trust_record=self._trust(),
                expected_fingerprint=self.fingerprint,
            )


class InstallFreshnessPlantTests(_AuthorityTestBase):
    """High-water anti-rollback / anti-replay and recovery plants."""

    def _verified(self):
        return ga.verify_authority(
            signed_envelope=self.envelope,
            artifacts=self.artifacts,
            trust_record=self._trust(),
            expected_fingerprint=self.fingerprint,
        )

    def test_same_generation_different_digest_is_rollback(self) -> None:
        verified = self._verified()
        stored = {"authority_generation": 1, "envelope_sha256": "a" * 64}
        with self.assertRefusal(GroupErrorCode.AUTHORITY_ROLLBACK):
            ga.evaluate_install(verified=verified, high_water_entry=stored)

    def test_rollback_to_older_generation_refuses(self) -> None:
        verified = self._verified()
        stored = {"authority_generation": 9, "envelope_sha256": "b" * 64}
        with self.assertRefusal(GroupErrorCode.AUTHORITY_ROLLBACK):
            ga.evaluate_install(verified=verified, high_water_entry=stored)
        # Also via the real install path after a higher generation installed.
        trust = self._trust()
        trust, _ = ga.install_authority(trust, verified)
        higher = ga.VerifiedAuthority(
            **{
                **verified.__dict__,
                "authority_generation": 5,
                "previous_envelope_sha256": verified.envelope_sha256,
                "envelope_sha256": "d" * 64,
            }
        )
        trust, status = ga.install_authority(trust, higher)
        self.assertEqual(status, ga.InstallStatus.INSTALLED)
        with self.assertRefusal(GroupErrorCode.AUTHORITY_ROLLBACK):
            ga.install_authority(trust, verified)

    def test_pending_recovery_refuses(self) -> None:
        verified = self._verified()
        with self.assertRefusal(GroupErrorCode.RECOVERY_REQUIRED):
            ga.evaluate_install(
                verified=verified, high_water_entry=None, pending_recovery=True
            )
        with self.assertRefusal(GroupErrorCode.RECOVERY_REQUIRED):
            ga.install_authority(self._trust(), verified, pending_recovery=True)


class PrincipalAndSegmentPlantTests(_AuthorityTestBase):
    """Principal-directory and audience-binding plants."""

    def test_altered_claim_breaks_source_hash(self) -> None:
        # Change a claim field but keep the stale AV1 source_hash: the
        # directory row is internally inconsistent.
        tampered = self.principals.replace(
            b'"source_revision":"1"', b'"source_revision":"2"'
        )
        self.assertNotEqual(tampered, self.principals)
        with self.assertRefusal(GroupErrorCode.PRINCIPAL_UNRESOLVED):
            ga.verify_principal_directory(tampered)

    def test_unresolved_principal_refuses(self) -> None:
        directory = ga.verify_principal_directory(self.principals)
        with self.assertRefusal(GroupErrorCode.PRINCIPAL_UNRESOLVED):
            ga.resolve_principal("deadbeef", directory)

    def test_missing_audience_binding_refuses(self) -> None:
        missing_private = b'{"legacy_aliases":{},"reserved_os":{"always_readable":true}}\n'
        with self.assertRefusal(GroupErrorCode.SEGMENT_BINDING_MISSING):
            ga.verify_audience_policy(missing_private)
        missing_os = b'{"legacy_aliases":{"private":"11111111"},"reserved_os":{}}\n'
        with self.assertRefusal(GroupErrorCode.SEGMENT_BINDING_MISSING):
            ga.verify_audience_policy(missing_os)
        with self.assertRefusal(GroupErrorCode.SEGMENT_BINDING_MISSING):
            ga.build_audience_policy(private_group_uid="not-a-uid")


class SchemaShapeTests(unittest.TestCase):
    """The closed schema is present, valid JSON, and closed everywhere."""

    def test_schema_is_closed_and_covers_the_four_shapes(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )
        refs = {entry["$ref"] for entry in schema["oneOf"]}
        self.assertEqual(
            refs,
            {
                "#/$defs/principal_directory_row",
                "#/$defs/trust_record",
                "#/$defs/artifact_manifest",
                "#/$defs/group_authority",
            },
        )
        for name, definition in schema["$defs"].items():
            if definition.get("type") == "object":
                self.assertIs(
                    definition.get("additionalProperties"),
                    False,
                    f"object def {name} must be closed",
                )


if __name__ == "__main__":
    unittest.main()
