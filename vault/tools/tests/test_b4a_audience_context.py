"""Focused executable contract for the B4a single AudienceContext adapter.

Covers the two acceptance criteria this pure slice owns:

* AC5 MANIFEST CUTOVER — an active Mike-group manifest passes all consumers,
  while an inline list, slug, unknown UID, ``team``, ``team-def``, draft, stale
  authority, unpinned manifest, or missing binding each refuses *contextually*
  with the exact typed :class:`GroupErrorCode`, never an empty result.
* AC12 ONE ADAPTER — mount, full validator, check-one, Gardener, and cross-vault
  ``member_of`` produce the SAME tagged result for one fixture through the one
  adapter; the explicit ``private``/``os`` bindings pass and omission refuses.

The module under test is loaded by file path with ``importlib`` (per
``test_event_ledger_distributed_identity.py``); the sibling ``lib`` libraries it
composes are imported normally so every ``GroupErrorCode`` / ``Result`` /
``GroupResolver`` / ``VerifiedAuthority`` shares one class identity with the
adapter.

The authority fixtures are grounded in the locked ``### Locked authority vector
AV1`` block of dev-spec ``0bfa771d``: the RFC 8032 test-vector-1 seed is a
TEST-only signing input, and the Mike-group corpus / audience-policy digests are
asserted byte-for-byte against the AV1 literals.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


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


# The module under test — loaded by file path.
ac = _load("b4a_audience_context_under_test", TOOLS / "lib" / "audience_context.py")

# Siblings composed by the adapter — imported normally for shared identity.
import lib.group_authority as ga  # noqa: E402
from lib.group_contract import (  # noqa: E402
    GroupContractError,
    GroupErrorCode,
    build_group_corpus,
    semantic_hash,
)
from lib.group_registry import (  # noqa: E402
    AuthorityRevisionContext,
    DEFAULT_CONSUMERS,
    GroupResolver,
    Result,
    project_registry,
)


# --------------------------------------------------------------------------- #
# AV1 literals (dev-spec 0bfa771d, "### Locked authority vector AV1").
# --------------------------------------------------------------------------- #
SEED_HEX = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
AUTHORITY_UID = "a1b2c3d4"
SIGNING_KEY_UID = "e5f6a7b8"
MIKE_GROUP_UID = "11111111"
MIKE_PRINCIPAL_UID = "7b921d17"

AV1_GROUPS_SHA = "8fac9a9ce622c9b265ee91c1f9176bb9ac6054ea3ee49763bf36b37a4516002f"
AV1_CORPUS_REVISION = f"sha256:{AV1_GROUPS_SHA}"
AV1_POLICY_SHA = "37fa8842e4ea2810ddd0f0b64eb92d08f54c474c47a8a43868d16d16f009e2f7"
AV1_PUBKEY_B64 = "11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo="
AV1_FINGERPRINT = "21fe31dfa154a261626bf854046fd2271b7bed4b6abe45aa58877ef47f9721b9"

# A well-formed 8-hex group UID that is deliberately absent from the corpus.
UNKNOWN_GROUP_UID = "abcdef01"
# A distinct, valid group UID used for "declared audience is not the pin".
OTHER_GROUP_UID = "22222222"

SEED = bytes.fromhex(SEED_HEX)
_PRIV = Ed25519PrivateKey.from_private_bytes(SEED)
PUB_B64 = ga.public_key_base64(_PRIV.public_key())
FINGERPRINT = ga.fingerprint(PUB_B64)


# --------------------------------------------------------------------------- #
# Fixture builders (reuse the sibling build/verify APIs; never reimplement).
# --------------------------------------------------------------------------- #
def _group(
    uid: str,
    slug: str,
    *,
    members: list[str] | None = None,
    includes: list[str] | None = None,
    owner: str = MIKE_PRINCIPAL_UID,
    status: str = "active",
    title: str | None = None,
    description: str | None = None,
) -> dict:
    group = {
        "uid": uid,
        "type": "group",
        "slug": slug,
        "title": title or slug.replace("-", " ").title(),
        "description": description or f"Purpose of {slug}.",
        "owner": owner,
        "members": list(members if members is not None else [owner]),
        "includes_groups": list(includes or []),
        "status": status,
        "version": 1,
    }
    group["semantic_hash"] = semantic_hash(group) if status == "active" else None
    return group


def _claim(uid: str = MIKE_PRINCIPAL_UID, status: str = "active") -> dict:
    return {
        "principal_uid": uid,
        "principal_class": "human",
        "status": status,
        "source_authority_uid": AUTHORITY_UID,
        "source_revision": "1",
    }


def _accepted_key(authority_uid: str = AUTHORITY_UID, key_uid: str = SIGNING_KEY_UID) -> dict:
    return ga.accept_authority_key(
        authority_uid=authority_uid,
        key_uid=key_uid,
        public_key_b64=PUB_B64,
        expected_fingerprint=FINGERPRINT,
        accepted_by=MIKE_PRINCIPAL_UID,
        accepted_at="2026-07-18T00:00:00Z",
    )


def _build_authority(group_dicts: list[dict], claims: list[dict], private_uid: str) -> SimpleNamespace:
    groups = ga.build_groups_jsonl(group_dicts)
    principals = ga.build_principals_jsonl(claims)
    policy = ga.build_audience_policy(private_group_uid=private_uid)
    manifest = ga.build_artifact_manifest(
        {
            "groups.jsonl": groups,
            "principals.jsonl": principals,
            "audience-policy.json": policy,
        }
    )
    tuple_fields = ga.build_authority_tuple(
        authority_uid=AUTHORITY_UID,
        groups_jsonl=groups,
        principals_jsonl=principals,
        audience_policy_json=policy,
        artifact_manifest_json=manifest,
        authority_generation=1,
        signing_key_uid=SIGNING_KEY_UID,
        previous_envelope_sha256=None,
    )
    signature = ga.sign_authority_tuple(tuple_fields, SEED)
    envelope = ga.build_signed_envelope(tuple_fields, signature)
    envelope_bytes = ga.canonical_envelope_bytes(envelope)
    trust = {"accepted_keys": [_accepted_key()], "high_water": {}}
    verified = ga.verify_authority(
        signed_envelope=envelope_bytes,
        artifacts={
            "groups.jsonl": groups,
            "principals.jsonl": principals,
            "audience-policy.json": policy,
            "artifact-manifest.json": manifest,
        },
        trust_record=trust,
        expected_fingerprint=FINGERPRINT,
    )
    return SimpleNamespace(
        verified=verified,
        envelope=envelope,
        envelope_bytes=envelope_bytes,
        signature=signature,
        groups=groups,
        principals=principals,
        policy=policy,
        manifest=manifest,
    )


def _build_resolver(
    group_dicts: list[dict],
    claims: list[dict],
    *,
    source_revision: str,
    principal_directory_revision: str,
) -> tuple[GroupResolver, object]:
    corpus = build_group_corpus(
        {g["uid"]: g for g in group_dicts},
        {c["principal_uid"]: c for c in claims},
    )
    projection = project_registry(
        corpus,
        AuthorityRevisionContext(
            source_authority_uid=AUTHORITY_UID,
            source_revision=source_revision,
            principal_directory_revision=principal_directory_revision,
            source_paths={g["uid"]: f"vault/groups/{g['uid']}.md" for g in group_dicts},
        ),
    )
    return GroupResolver.from_projection(projection), projection


class _AudienceBase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        # A three-group corpus: the Mike personal group plus an inner/outer
        # containment pair (outer includes inner) for the lattice checks.
        self.mike = _group(
            MIKE_GROUP_UID,
            "mike",
            title="Mike",
            description="Personal work visible to Mike.",
        )
        self.inner = _group("aa000001", "inner")
        self.outer = _group("aa000002", "outer", includes=["aa000001"])
        self.claim = _claim()
        self.corpus_groups = [self.mike, self.inner, self.outer]

        self.authority = _build_authority(self.corpus_groups, [self.claim], MIKE_GROUP_UID)
        self.verified = self.authority.verified
        self.envelope = self.authority.envelope

        self.resolver, self.projection = _build_resolver(
            self.corpus_groups,
            [self.claim],
            source_revision=self.verified.corpus_revision,
            principal_directory_revision=self.verified.principal_directory_revision,
        )

        # A pinned Mike vault and a pinned "ghost" vault whose resolution points
        # at a UID absent from the corpus.
        self.mike_manifest_path = "argo/.tropo/vault-manifest.md"
        self.mike_manifest_bytes = b"---\naudience: 11111111\n---\n"
        self.mike_binding = ac.MountAudienceBinding(
            vault_uid="argo",
            manifest_path=self.mike_manifest_path,
            manifest_sha256=ga.sha256_hex(self.mike_manifest_bytes),
            resolved_audience_group_uid=MIKE_GROUP_UID,
        )
        self.unknown_manifest_path = "ghost/.tropo/vault-manifest.md"
        self.unknown_binding = ac.MountAudienceBinding(
            vault_uid="ghost",
            manifest_path=self.unknown_manifest_path,
            manifest_sha256="0" * 64,
            resolved_audience_group_uid=UNKNOWN_GROUP_UID,
        )

        self.context = ac.AudienceContext.build(
            group_authority=self.envelope,
            verified=self.verified,
            private_alias_group_uid=MIKE_GROUP_UID,
            reserved_os_always_readable=True,
            mount_bindings=[self.mike_binding, self.unknown_binding],
        )
        self.policy = self.context.adapter(self.resolver)

    # -- resolvers for the negative contextual cases -----------------------
    def draft_policy(self) -> "ac.AudiencePolicy":
        draft_jsonl = self.projection.jsonl_bytes.replace(
            b'"status":"active"', b'"status":"draft"'
        )
        draft_resolver = GroupResolver.from_jsonl(draft_jsonl)
        return self.context.adapter(draft_resolver)

    def stale_policy(self) -> "ac.AudiencePolicy":
        stale_resolver, _ = _build_resolver(
            self.corpus_groups,
            [self.claim],
            source_revision="sha256:" + ("f" * 64),
            principal_directory_revision=self.verified.principal_directory_revision,
        )
        return self.context.adapter(stale_resolver)

    # -- assertion helpers -------------------------------------------------
    def assert_code(self, expected: GroupErrorCode, operation) -> GroupContractError:
        with self.assertRaises(GroupContractError) as raised:
            operation()
        self.assertEqual(
            raised.exception.code,
            expected,
            f"expected {expected} got {raised.exception.code}: {raised.exception}",
        )
        self.assertTrue(str(raised.exception).startswith(expected.value + ":"))
        return raised.exception

    def assert_result_error(self, result, expected: GroupErrorCode) -> GroupContractError:
        self.assertIsInstance(result, Result)
        self.assertFalse(result.ok)
        self.assertIsNone(result.value)
        self.assertIsNotNone(result.error)
        self.assertEqual(
            result.error.code,
            expected,
            f"expected {expected} got {result.error.code}: {result.error}",
        )
        # A refusal is a typed, raiseable error — never a bare False/empty.
        with self.assertRaises(GroupContractError) as raised:
            result.unwrap()
        self.assertEqual(raised.exception.code, expected)
        return result.error

    def assert_result_value(self, result, expected) -> None:
        self.assertIsInstance(result, Result)
        self.assertTrue(result.ok, msg=result.error)
        self.assertIsNone(result.error)
        self.assertEqual(result.value, expected)
        self.assertEqual(result.unwrap(), expected)

    def tag(self, result):
        """A comparable ``(status, payload)`` tuple for one adapter Result."""

        if result.ok:
            value = result.value
            if isinstance(value, ac.ResolvedAudience):
                value = ("resolved", value.kind, value.group_uid)
            return ("ok", value)
        return ("err", result.error.code)


class Av1GroundingTests(_AudienceBase):
    """The fixtures are the locked AV1 authority, referenced byte-for-byte."""

    def test_signing_key_material_matches_av1(self) -> None:
        self.assertEqual(PUB_B64, AV1_PUBKEY_B64)
        self.assertEqual(FINGERPRINT, AV1_FINGERPRINT)

    def test_mike_only_authority_matches_av1_digests(self) -> None:
        authority = _build_authority([self.mike], [self.claim], MIKE_GROUP_UID)
        self.assertEqual(ga.sha256_hex(authority.groups), AV1_GROUPS_SHA)
        self.assertEqual(authority.verified.corpus_sha256, AV1_GROUPS_SHA)
        self.assertEqual(authority.verified.corpus_revision, AV1_CORPUS_REVISION)
        self.assertEqual(ga.sha256_hex(authority.policy), AV1_POLICY_SHA)
        self.assertEqual(authority.verified.audience_policy_sha256, AV1_POLICY_SHA)

    def test_context_binds_the_av1_policy_and_revision(self) -> None:
        # The audience policy depends only on private-uid + os, so even the
        # three-group fixture pins exactly the AV1 policy digest.
        self.assertEqual(self.context.audience_policy_sha256, AV1_POLICY_SHA)
        self.assertEqual(self.context.private_alias_group_uid, MIKE_GROUP_UID)
        self.assertTrue(self.context.reserved_os_always_readable)
        self.assertEqual(self.resolver.revision, self.context.corpus_revision)


class PureManifestShapeTests(unittest.TestCase):
    """Pure manifest-shape validation is independently callable (no context)."""

    def _refuses(self, audience, code=GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE):
        with self.assertRaises(GroupContractError) as raised:
            ac.validate_manifest_audience_shape(audience)
        self.assertEqual(raised.exception.code, code)

    def test_accepts_a_single_group_uid(self) -> None:
        self.assertEqual(ac.validate_manifest_audience_shape("11111111"), "11111111")
        self.assertEqual(ac.validate_manifest_audience_shape("  aa000001 "), "aa000001")

    def test_rejects_inline_member_list(self) -> None:
        self._refuses([MIKE_PRINCIPAL_UID])
        self._refuses((MIKE_PRINCIPAL_UID, "22222222"))

    def test_rejects_inline_object(self) -> None:
        self._refuses({"members": [MIKE_PRINCIPAL_UID]})

    def test_rejects_slug(self) -> None:
        self._refuses("mike")
        self._refuses("mike-audience-group")

    def test_rejects_team_and_team_def(self) -> None:
        self._refuses("team")
        self._refuses("team-def")

    def test_rejects_legacy_aliases_as_manifest_audience(self) -> None:
        # private/os are record-level policy aliases, never a manifest's own
        # declared audience.
        self._refuses("private")
        self._refuses("os")

    def test_rejects_non_string_and_blank(self) -> None:
        self._refuses(None)
        self._refuses(5)
        self._refuses("")
        self._refuses("   ")


class AudienceContextConstructionTests(_AudienceBase):
    """AudienceContext is constructed ONLY from verified inputs; else refuses."""

    def test_valid_context_exposes_the_verified_bindings(self) -> None:
        self.assertIsInstance(self.context, ac.AudienceContext)
        self.assertEqual(self.context.authority_uid, AUTHORITY_UID)
        self.assertEqual(self.context.corpus_revision, self.verified.corpus_revision)
        self.assertEqual(self.context.mount_for_vault("argo"), self.mike_binding)
        self.assertEqual(
            self.context.mount_for_manifest_path(self.mike_manifest_path),
            self.mike_binding,
        )
        self.assertIsNone(self.context.mount_for_vault("nope"))

    def test_missing_private_binding_refuses(self) -> None:
        self.assert_code(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            lambda: ac.AudienceContext.build(
                group_authority=self.envelope,
                verified=self.verified,
                private_alias_group_uid=None,
                reserved_os_always_readable=True,
            ),
        )

    def test_missing_or_false_os_binding_refuses(self) -> None:
        for os_value in (None, False):
            with self.subTest(reserved_os_always_readable=os_value):
                self.assert_code(
                    GroupErrorCode.SEGMENT_BINDING_MISSING,
                    lambda os_value=os_value: ac.AudienceContext.build(
                        group_authority=self.envelope,
                        verified=self.verified,
                        private_alias_group_uid=MIKE_GROUP_UID,
                        reserved_os_always_readable=os_value,
                    ),
                )

    def test_unverified_authority_result_refuses(self) -> None:
        self.assert_code(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            lambda: ac.AudienceContext.build(
                group_authority=self.envelope,
                verified="not-a-verified-authority",
                private_alias_group_uid=MIKE_GROUP_UID,
                reserved_os_always_readable=True,
            ),
        )

    def test_compose_lock_tuple_disagreeing_with_envelope_refuses(self) -> None:
        tampered = dict(self.envelope)
        tampered["authority_uid"] = "b1b2c3d4"
        self.assert_code(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            lambda: ac.AudienceContext.build(
                group_authority=tampered,
                verified=self.verified,
                private_alias_group_uid=MIKE_GROUP_UID,
                reserved_os_always_readable=True,
            ),
        )

    def test_compose_lock_signature_mismatch_refuses(self) -> None:
        tampered = dict(self.envelope)
        tampered["signature"] = "A" * len(self.envelope["signature"])
        self.assert_code(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            lambda: ac.AudienceContext.build(
                group_authority=tampered,
                verified=self.verified,
                private_alias_group_uid=MIKE_GROUP_UID,
                reserved_os_always_readable=True,
            ),
        )

    def test_compose_lock_extra_key_refuses(self) -> None:
        tampered = dict(self.envelope)
        tampered["rogue_field"] = "x"
        self.assert_code(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            lambda: ac.AudienceContext.build(
                group_authority=tampered,
                verified=self.verified,
                private_alias_group_uid=MIKE_GROUP_UID,
                reserved_os_always_readable=True,
            ),
        )

    def test_private_binding_not_signed_by_authority_refuses(self) -> None:
        # A well-formed 8-hex UID, but not the one the signed policy attests:
        # the reconstructed policy digest cannot match the verified authority.
        self.assert_code(
            GroupErrorCode.AUTHORITY_UNTRUSTED,
            lambda: ac.AudienceContext.build(
                group_authority=self.envelope,
                verified=self.verified,
                private_alias_group_uid=OTHER_GROUP_UID,
                reserved_os_always_readable=True,
            ),
        )

    def test_malformed_mount_binding_refuses(self) -> None:
        bad_dict = {
            "vault_uid": "argo",
            "manifest_path": "argo/m.md",
            "resolved_audience_group_uid": MIKE_GROUP_UID,
            # manifest_sha256 omitted
        }
        self.assert_code(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            lambda: ac.AudienceContext.build(
                group_authority=self.envelope,
                verified=self.verified,
                private_alias_group_uid=MIKE_GROUP_UID,
                reserved_os_always_readable=True,
                mount_bindings=[bad_dict],
            ),
        )
        bad_uid = ac.MountAudienceBinding(
            vault_uid="argo",
            manifest_path="argo/m.md",
            manifest_sha256="0" * 64,
            resolved_audience_group_uid="not-a-uid",
        )
        self.assert_code(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            lambda: ac.AudienceContext.build(
                group_authority=self.envelope,
                verified=self.verified,
                private_alias_group_uid=MIKE_GROUP_UID,
                reserved_os_always_readable=True,
                mount_bindings=[bad_uid],
            ),
        )


class Ac5ManifestCutoverTests(_AudienceBase):
    """AC5 — one active Mike group passes; every bad shape refuses contextually."""

    def test_valid_active_mike_group_manifest_passes(self) -> None:
        result = self.policy.resolve_manifest_audience(
            self.mike_manifest_path,
            MIKE_GROUP_UID,
            manifest_bytes=self.mike_manifest_bytes,
        )
        self.assert_result_value(result, MIKE_GROUP_UID)
        # And the functional form (manifest path + context + resolver) agrees.
        functional = ac.resolve_manifest_audience(
            self.mike_manifest_path,
            MIKE_GROUP_UID,
            self.context,
            self.resolver,
            manifest_bytes=self.mike_manifest_bytes,
        )
        self.assert_result_value(functional, MIKE_GROUP_UID)

    def test_inline_member_list_refuses(self) -> None:
        self.assert_result_error(
            self.policy.resolve_manifest_audience(
                self.mike_manifest_path, [MIKE_PRINCIPAL_UID]
            ),
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
        )

    def test_slug_refuses(self) -> None:
        self.assert_result_error(
            self.policy.resolve_manifest_audience(self.mike_manifest_path, "mike"),
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
        )

    def test_unknown_uid_refuses(self) -> None:
        result = self.policy.resolve_manifest_audience(
            self.unknown_manifest_path, UNKNOWN_GROUP_UID
        )
        self.assert_result_error(result, GroupErrorCode.GROUP_NOT_FOUND)

    def test_team_refuses(self) -> None:
        self.assert_result_error(
            self.policy.resolve_manifest_audience(self.mike_manifest_path, "team"),
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
        )

    def test_team_def_refuses(self) -> None:
        self.assert_result_error(
            self.policy.resolve_manifest_audience(self.mike_manifest_path, "team-def"),
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
        )

    def test_draft_group_refuses(self) -> None:
        result = self.draft_policy().resolve_manifest_audience(
            self.mike_manifest_path, MIKE_GROUP_UID
        )
        self.assert_result_error(result, GroupErrorCode.GROUP_INACTIVE)

    def test_stale_authority_refuses(self) -> None:
        result = self.stale_policy().resolve_manifest_audience(
            self.mike_manifest_path, MIKE_GROUP_UID
        )
        self.assert_result_error(result, GroupErrorCode.GROUP_CORPUS_STALE)

    def test_unpinned_manifest_refuses(self) -> None:
        result = self.policy.resolve_manifest_audience(
            "unmounted/.tropo/vault-manifest.md", MIKE_GROUP_UID
        )
        self.assert_result_error(result, GroupErrorCode.SEGMENT_BINDING_MISSING)

    def test_manifest_sha256_mismatch_refuses(self) -> None:
        result = self.policy.resolve_manifest_audience(
            self.mike_manifest_path,
            MIKE_GROUP_UID,
            manifest_bytes=b"---\naudience: 11111111\n---\ntampered\n",
        )
        self.assert_result_error(result, GroupErrorCode.GROUP_CORPUS_STALE)

    def test_declared_audience_not_the_pin_refuses(self) -> None:
        # Well-formed UID, but not the pinned resolved_audience_group_uid.
        result = self.policy.resolve_manifest_audience(
            self.mike_manifest_path, OTHER_GROUP_UID
        )
        self.assert_result_error(result, GroupErrorCode.SEGMENT_BINDING_MISSING)


class Ac12OneAdapterTests(_AudienceBase):
    """AC12 — one adapter; private/os pass, omission refuses; callers agree."""

    def test_explicit_private_and_os_bindings_pass(self) -> None:
        private = self.policy.resolve_audience("private")
        self.assertTrue(private.ok)
        self.assertEqual(private.value.kind, "group")
        self.assertEqual(private.value.group_uid, MIKE_GROUP_UID)

        os_result = self.policy.resolve_audience("os")
        self.assertTrue(os_result.ok)
        self.assertEqual(os_result.value.kind, "os")
        self.assertIsNone(os_result.value.group_uid)

        # os is universally readable; private resolves through the Mike group.
        self.assert_result_value(self.policy.can_reference("private", "os"), True)
        self.assert_result_value(self.policy.can_reference("os", "private"), False)
        self.assert_result_value(self.policy.can_reference("private", "private"), True)
        self.assert_result_value(self.policy.can_reference("os", "os"), True)

    def test_omission_of_private_or_os_refuses(self) -> None:
        # The AC12 pair to "explicit bindings pass": omission refuses.
        self.assert_code(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            lambda: ac.AudienceContext.build(
                group_authority=self.envelope,
                verified=self.verified,
                private_alias_group_uid=None,
                reserved_os_always_readable=True,
            ),
        )
        self.assert_code(
            GroupErrorCode.SEGMENT_BINDING_MISSING,
            lambda: ac.AudienceContext.build(
                group_authority=self.envelope,
                verified=self.verified,
                private_alias_group_uid=MIKE_GROUP_UID,
                reserved_os_always_readable=None,
            ),
        )

    def test_can_reference_lattice_direction_and_transitivity(self) -> None:
        # outer includes inner, so outer is equal-or-wider than inner.
        self.assert_result_value(self.policy.can_reference("aa000001", "aa000002"), True)
        self.assert_result_value(self.policy.can_reference("aa000002", "aa000001"), False)
        self.assert_result_value(self.policy.can_reference("aa000001", "aa000001"), True)
        self.assert_result_value(self.policy.can_reference("aa000002", "aa000002"), True)

        # Equal member snapshots without an includes edge stay incomparable:
        # Mike and inner both resolve to [7b921d17] but neither contains the
        # other.
        self.assert_result_value(
            self.policy.can_reference(MIKE_GROUP_UID, "aa000001"), False
        )
        self.assert_result_value(
            self.policy.can_reference("aa000001", MIKE_GROUP_UID), False
        )

        # os is wider than every audience; nothing but os is wider than os.
        self.assert_result_value(self.policy.can_reference("aa000001", "os"), True)
        self.assert_result_value(self.policy.can_reference("os", "aa000001"), False)

    def test_one_adapter_many_callers_same_tagged_result(self) -> None:
        # The five callers named by the dev-spec are the registry's declared
        # consumers; each constructs the one adapter over the same verified
        # inputs and must produce the same tagged result for one fixture.
        callers = DEFAULT_CONSUMERS
        self.assertEqual(
            callers,
            ("tropo-mount", "tropo-validate", "tropo-check-one", "gardener", "cross_vault_member_of"),
        )

        per_caller = []
        for caller in callers:
            adapter = self.context.adapter(self.resolver)
            per_caller.append(
                {
                    "manifest_valid": self.tag(
                        adapter.resolve_manifest_audience(
                            self.mike_manifest_path,
                            MIKE_GROUP_UID,
                            manifest_bytes=self.mike_manifest_bytes,
                        )
                    ),
                    "manifest_unknown": self.tag(
                        adapter.resolve_manifest_audience(
                            self.unknown_manifest_path, UNKNOWN_GROUP_UID
                        )
                    ),
                    "manifest_inline": self.tag(
                        adapter.resolve_manifest_audience(
                            self.mike_manifest_path, [MIKE_PRINCIPAL_UID]
                        )
                    ),
                    "can_ref_up": self.tag(adapter.can_reference("aa000001", "aa000002")),
                    "can_ref_down": self.tag(adapter.can_reference("aa000002", "aa000001")),
                    "resolve_private": self.tag(adapter.resolve_audience("private")),
                    "resolve_os": self.tag(adapter.resolve_audience("os")),
                }
            )

        baseline = per_caller[0]
        for caller, tags in zip(callers, per_caller):
            self.assertEqual(tags, baseline, msg=f"caller {caller!r} diverged")

        # And the one tagged result is exactly the expected value/refusal.
        self.assertEqual(baseline["manifest_valid"], ("ok", MIKE_GROUP_UID))
        self.assertEqual(
            baseline["manifest_unknown"], ("err", GroupErrorCode.GROUP_NOT_FOUND)
        )
        self.assertEqual(
            baseline["manifest_inline"],
            ("err", GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE),
        )
        self.assertEqual(baseline["can_ref_up"], ("ok", True))
        self.assertEqual(baseline["can_ref_down"], ("ok", False))
        self.assertEqual(
            baseline["resolve_private"], ("ok", ("resolved", "group", MIKE_GROUP_UID))
        )
        self.assertEqual(baseline["resolve_os"], ("ok", ("resolved", "os", None)))

    def test_refusals_never_empty_membership_or_bare_false(self) -> None:
        # An unresolvable audience is a typed failure, not () or False.
        inline = self.policy.resolve_audience([MIKE_PRINCIPAL_UID])
        self.assert_result_error(inline, GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE)
        self.assertIsNone(inline.value)
        self.assertIsNot(inline.value, ())
        self.assertIsNot(inline.value, False)

        # A can_reference over an unresolvable side (a slug) refuses with a
        # typed code; it is not a bare False.  A group slug is never a declared
        # audience — only a group UID or a signed alias is.
        bad_ref = self.policy.can_reference("mike", "os")
        self.assert_result_error(bad_ref, GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE)
        self.assertIsNone(bad_ref.value)
        self.assertIsNot(bad_ref.value, False)

        # A mounted-but-unpinned vault refuses rather than defaulting to a
        # lattice.  A vault code is resolved by the dedicated vault surface, not
        # by resolve_audience (a vault code is not a record's declared audience).
        unpinned = self.policy.resolve_vault_audience("bcam")
        self.assert_result_error(unpinned, GroupErrorCode.SEGMENT_BINDING_MISSING)

        # And a vault code is itself refused as a declared record audience: it
        # is a slug/vault-shaped token, never an audience UID or signed alias.
        as_audience = self.policy.resolve_audience("bcam")
        self.assert_result_error(as_audience, GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE)

    def test_unavailable_context_refuses(self) -> None:
        # A well-formed context but no resolver is unavailable, not a fallback.
        no_resolver = ac.AudiencePolicy(self.context, None)
        self.assert_result_error(
            no_resolver.resolve_audience(MIKE_GROUP_UID),
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
        )
        self.assert_result_error(
            no_resolver.can_reference(MIKE_GROUP_UID, "os"),
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
        )
        self.assert_result_error(
            no_resolver.resolve_vault_audience("argo"),
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
        )
        self.assert_result_error(
            no_resolver.resolve_manifest_audience(self.mike_manifest_path, MIKE_GROUP_UID),
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
        )

    def test_resolve_vault_audience_resolves_pinned_vault(self) -> None:
        # A pinned, mounted vault resolves through its own binding to the active
        # audience group — the cross-vault lane's single segment-derivation path.
        resolved = self.policy.resolve_vault_audience("argo")
        self.assertTrue(resolved.ok, msg=resolved.error)
        self.assertEqual(resolved.value.kind, "group")
        self.assertEqual(resolved.value.group_uid, MIKE_GROUP_UID)

        # A pinned vault whose resolved group is absent from the corpus is an
        # unknown UID, not an empty membership.
        self.assert_result_error(
            self.policy.resolve_vault_audience("ghost"),
            GroupErrorCode.GROUP_NOT_FOUND,
        )

        # A token outside the ADR-050 vault grammar is a shape refusal.
        self.assert_result_error(
            self.policy.resolve_vault_audience("mike-audience-group"),
            GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE,
        )


class PurityTests(unittest.TestCase):
    """The adapter is a pure library: no absolute paths, no network imports."""

    def test_module_has_no_absolute_paths(self) -> None:
        source = Path(ac.__file__).read_text(encoding="utf-8")
        for needle in ("/workspace", "/home", "/Users"):
            self.assertNotIn(needle, source, f"module must not hardcode {needle!r}")

    def test_module_has_no_network_imports(self) -> None:
        source = Path(ac.__file__).read_text(encoding="utf-8")
        for needle in (
            "import socket",
            "import urllib",
            "import http",
            "import requests",
            "import ftplib",
            "import ssl",
            "from urllib",
            "from http",
            "socket.",
            "urlopen(",
        ):
            self.assertNotIn(needle, source, f"module must not import network surface {needle!r}")


if __name__ == "__main__":
    unittest.main()
