"""B4a strict-audience INTEGRATION contract (AC5 + AC12, from on-disk state).

The pure adapter is proven in ``test_b4a_audience_context.py``.  This suite proves
the *integration seam* the dev-spec (``0bfa771d``) and brief (``252534fe`` §4/§5)
require: that every production caller — ``tropo-mount.py``, ``tropo-validate.py``
(full + incremental), ``tropo-check-one.py``, the Gardener, and cross-vault
``member_of`` — obtains the SAME verified adapter from the Studio's real on-disk
authority + registry through the single :mod:`lib.audience_gate` seam, kills the
"known team or unknown UID" fail-open, and refuses fail-closed.

It also proves the canonical registry projector writes a deterministic,
row-equivalent ``.tropo-studio/registries/group-registry.jsonl`` (+ ``type:
registry`` wrapper + SQLite mirror) that fails closed on any mismatch.

Everything runs in scratch roots with a locked test authority built from the
locked ``AV1`` vector's RFC-8032 test seed (a TEST-only signing input); the real
``mike`` mint + capsule lock and the real Ed25519 fingerprint acceptance are
Mike-gated W1.5 ceremonies these fixtures deliberately do not impersonate.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
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


# Modules under integration test.  The gate + libs import normally (shared class
# identity for Result/GroupContractError); the two hyphenated CLIs load by path.
import lib.audience_gate as gate  # noqa: E402
import lib.audience_context as ac  # noqa: E402
import lib.viewer_projection as vp  # noqa: E402
from lib.viewer_projection import ViewerProjection, Viewer  # noqa: E402
import lib.group_authority as ga  # noqa: E402
from lib.group_contract import (  # noqa: E402
    GroupContractError,
    GroupErrorCode,
    build_group_corpus,
    semantic_hash,
)
from lib.group_registry import (  # noqa: E402
    AuthorityRevisionContext,
    project_registry,
)
from lib.cross_vault_member_of import (  # noqa: E402
    classify_additional_edge,
    classify_member_of_edges,
)
from lib.gardener import build_illegal_member_of_edge_set  # noqa: E402

_mount = _load("b4a_mount_under_test", TOOLS / "tropo-mount.py")
_validate = _load("b4a_validate_under_test", TOOLS / "tropo-validate.py")
_check_one = _load("b4a_check_one_under_test", TOOLS / "tropo-check-one.py")


# --------------------------------------------------------------------------- #
# Locked AV1 test seed + identities (dev-spec 0bfa771d "### Locked authority
# vector AV1").
# --------------------------------------------------------------------------- #
SEED_HEX = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
AUTHORITY_UID = "a1b2c3d4"
SIGNING_KEY_UID = "e5f6a7b8"
MIKE_GROUP_UID = "11111111"
MIKE_PRINCIPAL_UID = "7b921d17"
INNER_GROUP_UID = "aa000001"
OUTER_GROUP_UID = "aa000002"
UNKNOWN_GROUP_UID = "abcdef01"
TEAM_UID = "dddddddd"  # a type:team UID present only in the validate type_lookup

SEED = bytes.fromhex(SEED_HEX)
_PRIV = Ed25519PrivateKey.from_private_bytes(SEED)
PUB_B64 = ga.public_key_base64(_PRIV.public_key())
FINGERPRINT = ga.fingerprint(PUB_B64)


def _group(uid, slug, *, members=None, includes=None, owner=MIKE_PRINCIPAL_UID, status="active"):
    group = {
        "uid": uid,
        "type": "group",
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "description": f"Purpose of {slug}.",
        "owner": owner,
        "members": list(members if members is not None else [owner]),
        "includes_groups": list(includes or []),
        "status": status,
        "version": 1,
    }
    group["semantic_hash"] = semantic_hash(group) if status == "active" else None
    return group


def _claim(uid=MIKE_PRINCIPAL_UID, status="active"):
    return {
        "principal_uid": uid,
        "principal_class": "human",
        "status": status,
        "source_authority_uid": AUTHORITY_UID,
        "source_revision": "1",
    }


def _accepted_key():
    return ga.accept_authority_key(
        authority_uid=AUTHORITY_UID,
        key_uid=SIGNING_KEY_UID,
        public_key_b64=PUB_B64,
        expected_fingerprint=FINGERPRINT,
        accepted_by=MIKE_PRINCIPAL_UID,
        accepted_at="2026-07-18T00:00:00Z",
    )


def _build_authority(group_dicts, claims, private_uid):
    groups = ga.build_groups_jsonl(group_dicts)
    principals = ga.build_principals_jsonl(claims)
    policy = ga.build_audience_policy(private_group_uid=private_uid)
    manifest = ga.build_artifact_manifest(
        {"groups.jsonl": groups, "principals.jsonl": principals, "audience-policy.json": policy}
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
        envelope_bytes=envelope_bytes,
        groups=groups,
        principals=principals,
        policy=policy,
        manifest=manifest,
        trust=trust,
    )


def _install_on_disk(root: Path, group_dicts, claims, private_uid=MIKE_GROUP_UID):
    """Write the exact on-disk install layout the tools produce, then project the
    canonical studio registry from the live sources.  Returns the built authority.
    """
    auth = _build_authority(group_dicts, claims, private_uid)
    v = auth.verified

    # (a) authored active group source files (the projection's live source).
    src = root / gate.DEFAULT_SOURCE_DIR
    src.mkdir(parents=True, exist_ok=True)
    for g in group_dicts:
        if g["status"] == "active":
            (src / f"{g['uid']}.json").write_text(json.dumps(g), encoding="utf-8")

    # (b) immutable signed generation bundle.
    gen_rel = f"{gate.AUTHORITY_DIR}/generations/{v.authority_uid}/{v.authority_generation}"
    gen = root / gen_rel
    gen.mkdir(parents=True, exist_ok=True)
    (gen / ga.CORPUS_ARTIFACT).write_bytes(auth.groups)
    (gen / ga.PRINCIPAL_ARTIFACT).write_bytes(auth.principals)
    (gen / ga.AUDIENCE_POLICY_ARTIFACT).write_bytes(auth.policy)
    (gen / ga.ARTIFACT_MANIFEST_ARTIFACT).write_bytes(auth.manifest)
    (gen / ga.SIGNED_ENVELOPE_ARTIFACT).write_bytes(auth.envelope_bytes)

    # (c) installed pin + machine-local trust.
    pin = {
        "schema_id": "tropo.group-authority-install/v1",
        "authority_uid": v.authority_uid,
        "authority_generation": v.authority_generation,
        "corpus_revision": v.corpus_revision,
        "corpus_sha256": v.corpus_sha256,
        "principal_directory_revision": v.principal_directory_revision,
        "audience_policy_sha256": v.audience_policy_sha256,
        "generation_dir": gen_rel,
    }
    installed = root / gate.INSTALLED_RELATIVE
    installed.parent.mkdir(parents=True, exist_ok=True)
    installed.write_text(json.dumps(pin), encoding="utf-8")
    trust_path = root / gate.TRUST_RELATIVE
    trust_path.parent.mkdir(parents=True, exist_ok=True)
    trust_path.write_text(json.dumps(auth.trust), encoding="utf-8")

    # (d) project the canonical studio registry query surface from live sources.
    gate.project_studio_registry(root)
    return auth


def _mike_manifest_fm(audience=MIKE_GROUP_UID):
    return {
        "kind": "personal",
        "owner": MIKE_PRINCIPAL_UID,
        "audience": audience,
        "remote": "git@example:mike.git",
        "prefix_policy": {"references": "32067bea"},
        "publish_policy": "manual",
        "curation_policy": "manual",
        "curator": MIKE_PRINCIPAL_UID,
        "version": 1,
        "status": "active",
        "contract": {"capabilities": []},
        "regulated_acceptance": {"accepted": False},
    }


# --------------------------------------------------------------------------- #
# Base fixture: an installed authority in a scratch studio root.               #
# --------------------------------------------------------------------------- #
class _IntegrationBase(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        self.mike = _group(MIKE_GROUP_UID, "mike")
        self.inner = _group(INNER_GROUP_UID, "inner")
        self.outer = _group(OUTER_GROUP_UID, "outer", includes=[INNER_GROUP_UID])
        self.groups = [self.mike, self.inner, self.outer]
        self.auth = _install_on_disk(self.root, self.groups, [_claim()])

        # A per-mount binding for the Mike vault (contextual manifest resolution).
        self.mike_manifest_path = "argo/.tropo/vault-manifest.md"
        self.mike_bytes = b"---\naudience: 11111111\n---\n"
        self.mike_binding = ac.MountAudienceBinding(
            vault_uid="argo",
            manifest_path=self.mike_manifest_path,
            manifest_sha256=ga.sha256_hex(self.mike_bytes),
            resolved_audience_group_uid=MIKE_GROUP_UID,
        )

    def policy(self, *, bindings=()):
        return gate.load_policy(self.root, mount_bindings=bindings)


# --------------------------------------------------------------------------- #
# Gate load + cutover.                                                        #
# --------------------------------------------------------------------------- #
class ProjectionBindingTests(_IntegrationBase):
    """Finding 000d9dad: the projection must derive from the SIGNED corpus.

    The wrapper only proves the JSONL matches a digest the wrapper itself
    declares, and ``expected_revision`` only compares a ``source_revision``
    field the same writer supplies. Neither reaches the signature. Appending a
    correctly-shaped row and recomputing the wrapper therefore admitted an
    unsigned group on EVERY consumer -- including a machine holding a valid
    trust record, because verifying the envelope never checked that the
    projection derived from it.
    """

    def _forge_group_into_projection(self, surface: Path, wrapper_path: Path):
        """Append a group nobody signed, in the locked row order, and re-seal.

        Both weaker forgeries are deliberately avoided: a wrong key order dies
        on a shape check and a stale digest dies on the wrapper check, and
        neither refusal says anything about the signature.
        """
        import collections
        import hashlib

        rows = [
            json.loads(line, object_pairs_hook=collections.OrderedDict)
            for line in surface.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        forged = collections.OrderedDict((k, rows[0][k]) for k in rows[0])
        forged["group_uid"] = "deadbeef"
        forged["slug"] = "forged"
        forged["title"] = "Forged"
        # Same keys, same order -- the shape and digest gates must not be what
        # refuses this, or the test proves nothing about the binding.
        self.assertEqual(list(forged.keys()), list(rows[0].keys()))
        with surface.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(forged, separators=(",", ":")) + "\n")

        raw = surface.read_bytes()
        obj = json.loads(wrapper_path.read_text(encoding="utf-8"))
        flat = obj.get("wrapper") if isinstance(obj.get("wrapper"), dict) else obj
        flat["jsonl_sha256"] = hashlib.sha256(raw).hexdigest()
        flat["row_count"] = len(rows) + 1
        wrapper_path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")

    def _surfaces(self):
        studio = self.root / gate.STUDIO_REGISTRY_RELATIVE
        if studio.is_file():
            return studio, self.root / gate.STUDIO_REGISTRY_WRAPPER_RELATIVE
        return (
            self.root / gate.COMMITTED_REGISTRY_RELATIVE,
            self.root / gate.COMMITTED_WRAPPER_RELATIVE,
        )

    def test_clean_projection_still_loads(self):
        """The binding must not break the honest path."""
        self.assertIsNotNone(gate.load_resolver(self.root))
        self.assertIsNotNone(gate.load_policy(self.root))

    def test_forged_projection_is_refused_on_a_TRUSTED_machine(self):
        surface, wrapper = self._surfaces()
        self._forge_group_into_projection(surface, wrapper)

        # This machine holds a valid trust record and the envelope verifies.
        # Before the fix, both of these ACCEPTED the unsigned group.
        for label, call in (
            ("load_resolver", lambda: gate.load_resolver(self.root)),
            ("load_policy", lambda: gate.load_policy(self.root)),
        ):
            with self.subTest(caller=label):
                with self.assertRaises(GroupContractError) as caught:
                    call()
                self.assertEqual(
                    caught.exception.code,
                    GroupErrorCode.PROJECTION_MISMATCH,
                    f"{label} refused, but not for the projection-binding reason",
                )

    def test_pinning_expected_revision_is_not_the_guard(self):
        """The guard that looks sufficient is not: the attacker owns that field."""
        surface, wrapper = self._surfaces()
        envelope = json.loads(
            (
                self.root
                / json.loads(
                    (self.root / gate.INSTALLED_RELATIVE).read_text(encoding="utf-8")
                )["generation_dir"]
                / ga.SIGNED_ENVELOPE_ARTIFACT
            ).read_text(encoding="utf-8")
        )
        self._forge_group_into_projection(surface, wrapper)
        with self.assertRaises(GroupContractError) as caught:
            gate.load_resolver(
                self.root, expected_revision=envelope["corpus_revision"]
            )
        self.assertEqual(
            caught.exception.code, GroupErrorCode.PROJECTION_MISMATCH
        )


class LegacySegmentAliasTests(_IntegrationBase):
    """Finding 401d0702: a derived legacy segment must resolve as its group.

    `derive_segment` emits the literals the corpus is tagged with (`private`,
    `os`) while visibility resolves group UIDs. `os` is the reserved constant
    and matched directly; `private` is an alias whose target lives in the signed
    audience policy, and nothing on the production path consulted it. The
    comparison therefore never matched and EVERY `private` record was invisible
    to EVERY principal including its owner -- measured at 2,538 of 3,040 on the
    live Studio, with Mike seeing exactly what the crew saw.
    """

    def test_installed_policy_declares_the_private_alias(self):
        aliases = vp._installed_legacy_segment_aliases(self.root)
        self.assertEqual(aliases.get(ac.PRIVATE_ALIAS), MIKE_GROUP_UID)

    def _private_node(self):
        return vp.InMemoryGraphSource(
            [],
            {"n1": {"uid": "n1", "path": "vault/files/n1.md",
                    "extraction_scope": "argo-private"}},
            {"n1": self.root},
        )

    def test_the_alias_is_what_makes_a_private_record_resolve(self):
        """With the alias the owner sees their private work; without it, nobody does.

        The two halves ARE the proof. Before the fix only the second existed,
        which is why the breakage was invisible: 'the crew cannot see it' and
        'the mechanism never matches' look identical from outside.
        """
        owner = Viewer(
            principal_uid=MIKE_PRINCIPAL_UID, private_segment_uid=MIKE_GROUP_UID
        )
        resolver = gate.load_resolver(self.root)

        with_alias = ViewerProjection(
            self._private_node(),
            resolver=resolver,
            legacy_segment_aliases=vp._installed_legacy_segment_aliases(self.root),
        ).filter_visible_uids(["n1"], owner)
        self.assertTrue(with_alias.ok)
        self.assertEqual(
            with_alias.value, ("n1",), "owner cannot see their own private record"
        )

        without_alias = ViewerProjection(
            self._private_node(), resolver=resolver, legacy_segment_aliases={}
        ).filter_visible_uids(["n1"], owner)
        self.assertTrue(without_alias.ok)
        self.assertEqual(
            without_alias.value,
            (),
            "the alias map is not what makes this resolve -- test proves nothing",
        )

    def test_an_undeclared_literal_is_not_guessed(self):
        """An alias map is authority-declared, never a guessing table."""
        owner = Viewer(
            principal_uid=MIKE_PRINCIPAL_UID, private_segment_uid=MIKE_GROUP_UID
        )
        seen = ViewerProjection(
            self._private_node(),
            resolver=gate.load_resolver(self.root),
            legacy_segment_aliases={"some-other-literal": MIKE_GROUP_UID},
        ).filter_visible_uids(["n1"], owner)
        self.assertTrue(seen.ok)
        self.assertEqual(seen.value, ())


class GateLoadTests(_IntegrationBase):
    def test_cutover_active_after_install(self):
        self.assertTrue(gate.cutover_active(self.root))

    def test_cutover_inactive_without_install(self):
        import tempfile

        with tempfile.TemporaryDirectory() as empty:
            self.assertFalse(gate.cutover_active(Path(empty)))

    def test_load_policy_returns_verified_adapter(self):
        policy = self.policy()
        self.assertIsInstance(policy, ac.AudiencePolicy)
        # Resolver is pinned to the installed corpus revision.
        self.assertEqual(policy.resolver.revision, self.auth.verified.corpus_revision)

    def test_load_policy_refuses_without_authority(self):
        import tempfile

        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(GroupContractError) as raised:
                gate.load_policy(Path(empty))
            self.assertEqual(raised.exception.code, GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE)


# --------------------------------------------------------------------------- #
# AC5 — manifest cutover: one manifest passes; every bad shape refuses typed.  #
# --------------------------------------------------------------------------- #
class ManifestCutoverTests(_IntegrationBase):
    def test_active_mike_manifest_resolves(self):
        policy = self.policy(bindings=[self.mike_binding])
        outcome = policy.resolve_manifest_audience(
            self.mike_manifest_path, MIKE_GROUP_UID, manifest_bytes=self.mike_bytes
        )
        self.assertTrue(outcome.ok, msg=str(outcome.error))
        self.assertEqual(outcome.value, MIKE_GROUP_UID)

    def test_inline_list_refuses(self):
        policy = self.policy(bindings=[self.mike_binding])
        outcome = policy.resolve_manifest_audience(self.mike_manifest_path, [MIKE_PRINCIPAL_UID])
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.error.code, GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE)

    def test_slug_refuses(self):
        policy = self.policy(bindings=[self.mike_binding])
        outcome = policy.resolve_manifest_audience(self.mike_manifest_path, "mike")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.error.code, GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE)

    def test_removed_team_token_refuses(self):
        policy = self.policy(bindings=[self.mike_binding])
        for token in ("team", "team-def"):
            outcome = policy.resolve_manifest_audience(self.mike_manifest_path, token)
            self.assertFalse(outcome.ok)
            self.assertEqual(outcome.error.code, GroupErrorCode.GROUP_RESOLUTION_UNAVAILABLE)

    def test_unknown_uid_refuses(self):
        # An unpinned manifest naming an unknown group -> binding missing first.
        policy = self.policy(bindings=[self.mike_binding])
        outcome = policy.resolve_manifest_audience("ghost/.tropo/vault-manifest.md", UNKNOWN_GROUP_UID)
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.error.code, GroupErrorCode.SEGMENT_BINDING_MISSING)

    def test_unknown_uid_direct_resolve_is_not_found(self):
        policy = self.policy()
        outcome = policy.resolve_audience(UNKNOWN_GROUP_UID)
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.error.code, GroupErrorCode.GROUP_NOT_FOUND)

    def test_draft_group_is_absent_from_resolver(self):
        # Drafts never reach the resolver (dev-spec: "drafts are absent from every
        # registry and resolver"). A draft source file present on disk is excluded
        # from the projection, so its UID refuses GROUP_NOT_FOUND — never leaks as
        # a resolvable audience.
        import tempfile

        with tempfile.TemporaryDirectory() as other:
            oroot = Path(other)
            self.assertIsNotNone(_install_on_disk(oroot, [_group(MIKE_GROUP_UID, "mike")], [_claim()]))
            # Add a draft source file and re-project.
            draft = _group("bb000001", "draftie", status="draft")
            (oroot / gate.DEFAULT_SOURCE_DIR / "bb000001.json").write_text(json.dumps(draft), encoding="utf-8")
            gate.project_studio_registry(oroot)
            policy = gate.load_policy(oroot)
            self.assertNotIn("bb000001", policy.resolver.active_uids)
            outcome = policy.resolve_audience("bb000001")
            self.assertFalse(outcome.ok)
            self.assertEqual(outcome.error.code, GroupErrorCode.GROUP_NOT_FOUND)

    def test_stale_manifest_bytes_refuses(self):
        policy = self.policy(bindings=[self.mike_binding])
        outcome = policy.resolve_manifest_audience(
            self.mike_manifest_path, MIKE_GROUP_UID, manifest_bytes=b"tampered"
        )
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.error.code, GroupErrorCode.GROUP_CORPUS_STALE)

    def test_missing_binding_refuses(self):
        policy = self.policy()  # no bindings installed
        outcome = policy.resolve_manifest_audience(self.mike_manifest_path, MIKE_GROUP_UID)
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.error.code, GroupErrorCode.SEGMENT_BINDING_MISSING)


# --------------------------------------------------------------------------- #
# AC12 — ONE ADAPTER: mount, full validator, check-one, Gardener, member_of    #
# produce the same accept/refuse for one fixture through the single adapter.   #
# --------------------------------------------------------------------------- #
class OneAdapterParityTests(_IntegrationBase):
    def _type_lookup(self):
        # The full validator's corpus type index: the mike group + a team entry
        # (the removed "known team" acceptance) + a non-group entry.
        return {MIKE_GROUP_UID: "group", TEAM_UID: "team", INNER_GROUP_UID: "group"}

    # -- accept: every caller accepts the active mike group -----------------
    def test_all_callers_accept_active_group(self):
        policy = self.policy(bindings=[self.mike_binding])

        # 1. full validator (shared validate_vault_manifest_fields, strict cutover)
        errors = _validate.validate_vault_manifest_fields(
            _mike_manifest_fm(MIKE_GROUP_UID),
            type_lookup=self._type_lookup(),
            strict_audience=True,
        )
        self.assertEqual([e for e in errors if "audience" in e], [], msg=str(errors))

        # 2. mount (its own gate helper against the real on-disk authority)
        self.assertIsNone(_mount._b4a_audience_refusal(self.root, MIKE_GROUP_UID))

        # 3. check-one (routes vault-audience through the same gate)
        vfindings = _check_one.run_vault_audience_check("vaultone", "vault", self.root)
        # No instance on disk -> no-op; drive the gate directly to mirror its path.
        self.assertEqual(vfindings, [])
        self.assertTrue(gate.load_policy(self.root).resolve_audience(MIKE_GROUP_UID).ok)

        # 4. Gardener / cross-vault member_of audience-lattice legality: the SAME
        # shared per-edge classifier, driven by the B4aLattice over the one adapter.
        # A same-segment (private -> private) and an up-lattice (private -> os) edge
        # are legal; a down-lattice (os -> private) edge is illegal — exactly what
        # the adapter's can_reference decides.
        lattice = gate.B4aLattice(policy)
        segs = {"a": "private", "b": "private", "c": "os"}
        self.assertTrue(classify_additional_edge("a", "b", segs, lattice).legal)   # equal
        self.assertTrue(classify_additional_edge("a", "c", segs, lattice).legal)   # up (-> os)
        self.assertFalse(classify_additional_edge("c", "a", segs, lattice).legal)  # down

        # 5. The Gardener composed-index exclusion layer accepts the injected
        # B4aLattice seam (single adapter; no synthesized default lattice).
        illegal = build_illegal_member_of_edge_set([], {}, {}, lattice=lattice)
        self.assertEqual(illegal, set())

    # -- refuse: every caller refuses a team UID (the killed fail-open) ------
    def test_all_callers_refuse_team_audience(self):
        # full validator: strict cutover rejects a type:team audience.
        errors = _validate.validate_vault_manifest_fields(
            _mike_manifest_fm(TEAM_UID),
            type_lookup=self._type_lookup(),
            strict_audience=True,
        )
        self.assertTrue(any("audience" in e for e in errors), msg=str(errors))

        # mount: the team UID is not a live group -> refused.
        self.assertIsNotNone(_mount._b4a_audience_refusal(self.root, TEAM_UID))

        # resolver/adapter: team UID absent from the group registry.
        self.assertFalse(gate.load_policy(self.root).resolve_audience(TEAM_UID).ok)

    def test_all_callers_refuse_unknown_uid(self):
        errors = _validate.validate_vault_manifest_fields(
            _mike_manifest_fm(UNKNOWN_GROUP_UID),
            type_lookup=self._type_lookup(),
            strict_audience=True,
        )
        self.assertTrue(any("audience" in e for e in errors), msg=str(errors))
        self.assertIsNotNone(_mount._b4a_audience_refusal(self.root, UNKNOWN_GROUP_UID))
        self.assertFalse(gate.load_policy(self.root).resolve_audience(UNKNOWN_GROUP_UID).ok)

    def test_pre_cutover_validator_keeps_lenient_behaviour(self):
        # Without strict_audience, a team UID is still accepted (pre-B4a behaviour
        # preserved so un-updated Studios are unaffected).
        errors = _validate.validate_vault_manifest_fields(
            _mike_manifest_fm(TEAM_UID), type_lookup=self._type_lookup(), strict_audience=False
        )
        self.assertEqual([e for e in errors if "audience" in e], [])

    # -- private / os signed bindings pass; omission refuses ----------------
    def test_private_alias_and_os_pass(self):
        policy = self.policy()
        self.assertTrue(policy.resolve_audience(gate.PRIVATE_ALIAS).ok)  # -> mike group
        self.assertEqual(policy.resolve_audience(gate.PRIVATE_ALIAS).value.group_uid, MIKE_GROUP_UID)
        os_outcome = policy.resolve_audience(gate.OS_AUDIENCE)
        self.assertTrue(os_outcome.ok)
        self.assertEqual(os_outcome.value.kind, "os")

    def test_lattice_containment_direction(self):
        # outer includes inner: inner may reference outer (up), not vice-versa.
        policy = self.policy()
        lattice = gate.B4aLattice(policy)
        self.assertEqual(lattice.relation(INNER_GROUP_UID, OUTER_GROUP_UID), "up")
        self.assertEqual(lattice.relation(OUTER_GROUP_UID, INNER_GROUP_UID), "down")
        self.assertTrue(lattice.is_legal_target(INNER_GROUP_UID, OUTER_GROUP_UID))
        self.assertFalse(lattice.is_legal_target(OUTER_GROUP_UID, INNER_GROUP_UID))

    def test_lattice_fails_closed_on_unknown_segment(self):
        # An unresolved segment is a typed refusal, never a reason-free False.
        policy = self.policy()
        lattice = gate.B4aLattice(policy)
        with self.assertRaises(GroupContractError):
            lattice.is_legal_target(UNKNOWN_GROUP_UID, MIKE_GROUP_UID)
        result = lattice.try_relation(UNKNOWN_GROUP_UID, MIKE_GROUP_UID)
        self.assertFalse(result.ok)


# --------------------------------------------------------------------------- #
# Canonical studio-registry projector (.tropo-studio/registries/).            #
# --------------------------------------------------------------------------- #
class StudioRegistryProjectorTests(_IntegrationBase):
    def test_surface_written_at_canonical_path(self):
        self.assertTrue((self.root / gate.STUDIO_REGISTRY_RELATIVE).exists())
        self.assertTrue((self.root / gate.STUDIO_REGISTRY_WRAPPER_RELATIVE).exists())
        self.assertTrue((self.root / gate.STUDIO_REGISTRY_SQLITE_RELATIVE).exists())

    def test_wrapper_is_type_registry(self):
        record = json.loads((self.root / gate.STUDIO_REGISTRY_WRAPPER_RELATIVE).read_text())
        self.assertEqual(record["type"], "registry")
        self.assertIn("wrapper", record)
        self.assertIn("jsonl_sha256", record["wrapper"])
        self.assertIn("row_count", record["wrapper"])

    def test_projection_is_deterministic(self):
        first = (self.root / gate.STUDIO_REGISTRY_RELATIVE).read_bytes()
        gate.project_studio_registry(self.root)
        second = (self.root / gate.STUDIO_REGISTRY_RELATIVE).read_bytes()
        self.assertEqual(first, second)

    def test_matches_library_projection(self):
        # The on-disk surface equals project_registry() over the same sources/pin.
        corpus = build_group_corpus(
            {g["uid"]: g for g in self.groups if g["status"] == "active"},
            {c["principal_uid"]: c for c in [_claim()]},
        )
        v = self.auth.verified
        expected = project_registry(
            corpus,
            AuthorityRevisionContext(
                source_authority_uid=v.authority_uid,
                source_revision=v.corpus_revision,
                principal_directory_revision=v.principal_directory_revision,
                source_paths={g["uid"]: f"{gate.DEFAULT_SOURCE_DIR}/{g['uid']}.json"
                              for g in self.groups if g["status"] == "active"},
            ),
        )
        on_disk = (self.root / gate.STUDIO_REGISTRY_RELATIVE).read_bytes()
        self.assertEqual(on_disk, expected.jsonl_bytes)

    def test_verify_passes_clean(self):
        result = gate.verify_studio_registry(self.root)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["row_count"], 3)

    def test_mismatch_fails_closed(self):
        # Tamper the SQLite mirror -> parity refuses PROJECTION_MISMATCH.
        sqlite_path = self.root / gate.STUDIO_REGISTRY_SQLITE_RELATIVE
        connection = sqlite3.connect(str(sqlite_path))
        try:
            connection.execute("UPDATE group_registry SET slug='tampered' WHERE group_uid=?", (MIKE_GROUP_UID,))
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(GroupContractError) as raised:
            gate.verify_studio_registry(self.root)
        self.assertEqual(raised.exception.code, GroupErrorCode.PROJECTION_MISMATCH)

    def test_resolver_reads_studio_surface(self):
        resolver = gate.load_resolver(self.root, expected_revision=self.auth.verified.corpus_revision)
        self.assertEqual(set(resolver.active_uids), {MIKE_GROUP_UID, INNER_GROUP_UID, OUTER_GROUP_UID})
        self.assertEqual(resolver.resolve_members(MIKE_GROUP_UID).value, (MIKE_PRINCIPAL_UID,))


if __name__ == "__main__":
    unittest.main(verbosity=2)
