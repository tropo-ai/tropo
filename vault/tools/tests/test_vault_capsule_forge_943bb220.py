#!/usr/bin/env python3
"""vault.capsule forge gauntlets — dev-spec 943bb220 acceptance criteria (ADR-051 Fork 1).

Builds the NEW `vault` manifest type + renames the vault-ENTITY `4d6e2f9a` -> `vault-entity`
(UID preserved) + validator recognition + `tropo-mint-id.py --kind vault`.

Mandatory fixtures per Argus's MODERATE calibration (943bb220 §7 + queue item 1/4):
  AC1 — a VALID sample manifest (all required fields) validates clean; an INVALID manifest
        per each guarded rule (missing field; inlined studio prefix; inline audience list;
        deprecated without successor; missing curator; regulated without acceptance) FAILS
        with a clear error. (`kind` change after `active` is a documented, deferred
        cross-version check — see NOTE in TestKindImmutableAfterActiveDeferred.)
  AC2 — the 2 live instances (7f5b1d83, 7c3a8e91) re-validate clean against vault-entity
        (read from the REAL files on disk — proves the migration, not a synthetic double);
        a planted second vault-entity in the same vault-node FAILS (isolated fixture).
  AC3 — every former `governed_by: 4d6e2f9a` caller resolves post-rename (UID preserved,
        checked against the real files on disk).
  AC4 — the negative mis-validation: a `type: vault` manifest is never checked against the
        entity schema, and a `vault-entity` instance is never checked against the manifest
        schema (structural, by dispatch — proven directly on the two validator functions).
  AC6 — `tropo-mint-id.py --kind vault` mints without NotImplementedError; shape is the
        ADR-050 Decision 3 "short registered code" (4-6 lowercase alnum), NOT flat 8-hex.

None of these need a live git repo, so they run for real in this sandbox (no skips).
"""
from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / 'vault' / 'tools'
sys.path.insert(0, str(TOOLS))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


VALIDATOR = _load('tropo_validate_943bb220', TOOLS / 'tropo-validate.py')
MINT = _load('tropo_mint_id_943bb220', TOOLS / 'tropo-mint-id.py')

SHORT_CODE_RE = re.compile(r'^[a-z0-9]{4,6}$')
HEX8_RE = re.compile(r'^[0-9a-f]{8}$')


def _valid_manifest_fixture(**overrides) -> dict:
    """A conforming `type: vault` manifest carrying every required field (943bb220 AC1)."""
    fm = {
        'uid': 'aaaa1111',
        'type': 'vault',
        'title': 'Fixture Vault',
        'status': 'active',
        'kind': 'team',
        'owner': 'talos',
        'audience': 'bbbb2222',
        'remote': 'git@example.com:acme/fixture-vault.git',
        'prefix_policy': {'references': '32067bea', 'mint_policy': 'post-genesis-remint'},
        'publish_policy': {'publishers': ['talos'], 'attestation_required': True},
        'curation_policy': {'mode': 'gardener', 'cadence': 'weekly'},
        'curator': 'orpheus',
        'version': '1.0.0',
        'contract': {'types': ['task', 'decision'], 'capsule_versions': {'task': '3.0'}},
        'regulated_acceptance': {'accepted': False, 'ceiling': 'forward-only-revocation'},
    }
    fm.update(overrides)
    return fm


def _valid_entity_fixture(**overrides) -> dict:
    """A conforming renamed `vault-entity` instance frontmatter (943bb220 AC2)."""
    fm = {
        'uid': 'cccc3333',
        'type': 'entity',
        'subtype': 'vault-entity',
        'title': 'Fixture Vault Entity',
        'principal': 'dddd4444',
        'inbox_project': 'eeee5555',
    }
    fm.update(overrides)
    return fm


class TestAC1ManifestValidFixturePasses(unittest.TestCase):
    """AC1 — a VALID sample manifest carrying all required fields validates clean."""

    def test_valid_manifest_zero_errors(self):
        errors = VALIDATOR.validate_vault_manifest_fields(_valid_manifest_fixture())
        self.assertEqual(errors, [], f'expected 0 errors on a conforming manifest, got: {errors}')

    def test_valid_manifest_with_team_type_lookup_passes(self):
        fm = _valid_manifest_fixture()
        errors = VALIDATOR.validate_vault_manifest_fields(fm, type_lookup={'bbbb2222': 'team'})
        self.assertEqual(errors, [])


class TestAC1ManifestGuardedRuleFailures(unittest.TestCase):
    """AC1 — an INVALID manifest per each guarded rule FAILS with a clear error."""

    def test_missing_required_field_fails(self):
        fm = _valid_manifest_fixture()
        del fm['curator']
        del fm['remote']
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertTrue(any('missing required field' in e for e in errors))
        self.assertTrue(any('remote' in e for e in errors))

    def test_kind_not_in_enum_fails(self):
        fm = _valid_manifest_fixture(kind='enterprise')
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertTrue(any('kind=' in e and 'enum' in e for e in errors))

    def test_inlined_studio_prefix_fails(self):
        """Sibling boundary (ADR-051 §2, Rule 2): a manifest that INLINES a studio prefix
        instead of referencing 32067bea must fail."""
        fm = _valid_manifest_fixture(prefix_policy={'mint_prefix': 'acme1', 'references': None})
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertTrue(any('INLINES a studio prefix' in e for e in errors), errors)

    def test_prefix_policy_missing_studio_reference_fails(self):
        fm = _valid_manifest_fixture(prefix_policy={'mint_policy': 'post-genesis-remint'})
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertTrue(any('does not reference the studio identity' in e for e in errors), errors)

    def test_inline_audience_member_list_fails(self):
        fm = _valid_manifest_fixture(audience=['6c0e4a2b', '7ddf4814'])
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertTrue(any('inline member list' in e for e in errors), errors)

    def test_audience_not_resolving_to_group_fails(self):
        fm = _valid_manifest_fixture(audience='bbbb2222')
        errors = VALIDATOR.validate_vault_manifest_fields(fm, type_lookup={'bbbb2222': 'task'})
        self.assertTrue(any('not a group/team entity' in e for e in errors), errors)

    def test_deprecated_without_successor_fails(self):
        fm = _valid_manifest_fixture(status='deprecated')
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertTrue(any('requires a resolvable successor' in e for e in errors), errors)

    def test_deprecated_with_successor_passes_that_rule(self):
        fm = _valid_manifest_fixture(status='deprecated', successor='ffff6666')
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertFalse(any('successor' in e for e in errors), errors)

    def test_missing_curator_fails(self):
        fm = _valid_manifest_fixture(curator='')
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertTrue(any('curator is missing' in e for e in errors), errors)

    def test_regulated_accepted_without_accepted_by_fails(self):
        fm = _valid_manifest_fixture(regulated_acceptance={'accepted': True})
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertTrue(any('accepted_by is missing' in e for e in errors), errors)

    def test_regulated_accepted_with_accepted_by_passes_that_rule(self):
        fm = _valid_manifest_fixture(
            regulated_acceptance={'accepted': True, 'accepted_by': '6c0e4a2b'}
        )
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertFalse(any('regulated_acceptance' in e for e in errors), errors)


class TestKindImmutableAfterActiveDeferred(unittest.TestCase):
    """Validation Check 3 (capsule): `kind` immutable after `active` (Fork 3).

    The CURRENT-STATE half (kind must be in the enum) is enforced now — proven above.
    The CROSS-VERSION half (a kind CHANGE on a manifest that was EVER active) requires
    git-log inspection across commits; the manifest doesn't even have a canonical
    per-vault-root home yet (Fork 2, downstream), so there's nowhere real to diff
    against. Deferred to a later ratchet — same documented precedent as
    check_article_state_machine_invariants's sequential-transition-history note in
    tropo-validate.py. This test documents the decision is DELIBERATE, not an oversight:
    a single-snapshot dict has no way to know a manifest's history, by construction.
    """

    def test_single_snapshot_cannot_detect_a_kind_change(self):
        fm = _valid_manifest_fixture(kind='team')
        # A single frontmatter snapshot is, structurally, all validate_vault_manifest_fields
        # ever sees — there is no previous-kind parameter in the pure-function contract.
        self.assertNotIn('previous_kind', fm)
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertEqual(errors, [])  # current-state shape is fine; that's all v1.0 checks


class TestAC2VaultEntityRenameLiveInstances(unittest.TestCase):
    """AC2/AC3 — the 2 REAL live instances re-validate clean post-rename; UID preserved."""

    def _read_fm(self, uid: str) -> dict:
        path = ROOT / 'vault' / 'files' / f'{uid}.md'
        text = path.read_text(encoding='utf-8')
        fm_text = VALIDATOR.split_frontmatter(text)
        self.assertIsNotNone(fm_text, f'{uid}.md has no frontmatter')
        import yaml
        fm = yaml.safe_load(fm_text)
        self.assertIsInstance(fm, dict)
        return fm

    def test_argo_vault_entity_7f5b1d83_validates_clean(self):
        fm = self._read_fm('7f5b1d83')
        self.assertEqual(fm.get('subtype'), 'vault-entity')
        self.assertEqual(fm.get('governed_by'), '4d6e2f9a', 'governed_by must be UNCHANGED (UID preserved)')
        errors = VALIDATOR.validate_vault_entity_fields(fm)
        self.assertEqual(errors, [], f'7f5b1d83 should validate clean, got: {errors}')

    def test_starter_vault_entity_7c3a8e91_validates_clean(self):
        fm = self._read_fm('7c3a8e91')
        self.assertEqual(fm.get('subtype'), 'vault-entity')
        self.assertEqual(fm.get('governed_by'), '4d6e2f9a', 'governed_by must be UNCHANGED (UID preserved)')
        errors = VALIDATOR.validate_vault_entity_fields(fm)
        self.assertEqual(errors, [], f'7c3a8e91 should validate clean, got: {errors}')

    def test_renamed_capsule_file_preserves_uid_and_updates_name(self):
        capsule_path = ROOT / 'vault' / 'capsules' / 'tropo-vault-entity.capsule.md'
        self.assertTrue(capsule_path.is_file(), 'renamed capsule file must exist')
        text = capsule_path.read_text(encoding='utf-8')
        fm_text = VALIDATOR.split_frontmatter(text)
        self.assertEqual(VALIDATOR.get_scalar(fm_text, 'uid'), '4d6e2f9a', 'UID must be PRESERVED across the rename')
        self.assertEqual(VALIDATOR.get_scalar(fm_text, 'name'), 'vault-entity')

    def test_old_capsule_filename_no_longer_exists(self):
        old_path = ROOT / 'vault' / 'capsules' / 'tropo-vault.capsule.md'
        # The path is REUSED by the NEW manifest type (a1f7c750), not left dangling —
        # confirm the file at this path now carries the NEW uid, not the old one.
        self.assertTrue(old_path.is_file())
        text = old_path.read_text(encoding='utf-8')
        fm_text = VALIDATOR.split_frontmatter(text)
        self.assertEqual(VALIDATOR.get_scalar(fm_text, 'uid'), 'a1f7c750',
                         'tropo-vault.capsule.md must now be the NEW manifest type, not the old entity')

    def test_new_manifest_capsule_authored_with_correct_uid(self):
        capsule_path = ROOT / 'vault' / 'capsules' / 'tropo-vault.capsule.md'
        text = capsule_path.read_text(encoding='utf-8')
        fm_text = VALIDATOR.split_frontmatter(text)
        self.assertEqual(VALIDATOR.get_scalar(fm_text, 'uid'), 'a1f7c750')
        self.assertEqual(VALIDATOR.get_scalar(fm_text, 'name'), 'vault')
        self.assertEqual(VALIDATOR.get_scalar(fm_text, 'extends'), 'core')


class TestAC2SingletonPlantAdversarial(unittest.TestCase):
    """AC2 — a planted SECOND vault-entity in the same vault-node FAILS.

    Adversarially isolated (A112/A113 gauntlet binding, per the test_no_two_homes_gate.py
    precedent): an isolated fixture tree, never the real vault, so this proves the
    ENFORCEMENT CODE fires, not just that the spec says it should.
    """

    def setUp(self):
        test_root = ROOT / '.tmp-vault-capsule-forge-tests'
        test_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=str(test_root))
        self.root = Path(self.tmp.name)
        (self.root / 'vault' / 'files').mkdir(parents=True)
        (self.root / 'vault' / '00-index.jsonl').write_text('')

    def tearDown(self):
        self.tmp.cleanup()

    def _write_entity(self, uid: str, extraction_scope: str) -> None:
        text = (
            "---\n"
            f"uid: {uid}\n"
            "type: entity\n"
            "subtype: vault-entity\n"
            f"principal: {'a' * 8}\n"
            f"extraction_scope: {extraction_scope}\n"
            "---\n\nFixture.\n"
        )
        (self.root / 'vault' / 'files' / f'{uid}.md').write_text(text)

    def test_single_vault_entity_passes(self):
        self._write_entity('11111111', 'argo-reference')
        findings, checked, violations = VALIDATOR.check_vault_capsule_types(self.root)
        self.assertEqual(checked, 1)
        self.assertEqual(violations, 0, findings)

    def test_two_vault_entities_same_scope_fails(self):
        self._write_entity('11111111', 'argo-reference')
        self._write_entity('22222222', 'argo-reference')
        findings, checked, violations = VALIDATOR.check_vault_capsule_types(self.root)
        self.assertEqual(checked, 2)
        self.assertGreaterEqual(violations, 1, 'planted 2nd vault-entity in same scope must FAIL')
        self.assertTrue(any('singleton-per-vault-node' in f for f in findings), findings)

    def test_two_vault_entities_different_scope_pass(self):
        """Different extraction_scope = different vault-node (this studio's proxy,
        943bb220 build report) — must NOT collide."""
        self._write_entity('11111111', 'argo-reference')
        self._write_entity('22222222', 'ship')
        findings, checked, violations = VALIDATOR.check_vault_capsule_types(self.root)
        self.assertEqual(checked, 2)
        self.assertEqual(violations, 0, findings)

    def test_removing_the_plant_clears_the_violation(self):
        self._write_entity('11111111', 'argo-reference')
        self._write_entity('22222222', 'argo-reference')
        _, _, violations_before = VALIDATOR.check_vault_capsule_types(self.root)
        self.assertGreaterEqual(violations_before, 1)
        (self.root / 'vault' / 'files' / '22222222.md').unlink()
        _, _, violations_after = VALIDATOR.check_vault_capsule_types(self.root)
        self.assertEqual(violations_after, 0)


class TestAC4NegativeMisvalidation(unittest.TestCase):
    """AC4 — a `type: vault` manifest is NEVER checked against the entity schema, and a
    `vault-entity` instance is NEVER checked against the manifest schema."""

    def test_manifest_validator_does_not_require_entity_only_fields(self):
        """A manifest fixture missing `principal`/`subtype` (entity-only concerns) must
        NOT fail for those reasons — the manifest schema simply doesn't check them."""
        fm = _valid_manifest_fixture()
        self.assertNotIn('principal', fm)
        self.assertNotIn('subtype', fm)
        errors = VALIDATOR.validate_vault_manifest_fields(fm)
        self.assertEqual(errors, [])

    def test_entity_validator_does_not_require_manifest_only_fields(self):
        """A vault-entity fixture missing `kind`/`remote`/`audience`/etc. (manifest-only
        concerns) must NOT fail for those reasons — the entity schema doesn't check them."""
        fm = _valid_entity_fixture()
        for manifest_field in ('kind', 'remote', 'audience', 'curator', 'contract'):
            self.assertNotIn(manifest_field, fm)
        errors = VALIDATOR.validate_vault_entity_fields(fm)
        self.assertEqual(errors, [])

    def test_check_vault_capsule_types_dispatches_by_type_not_by_shared_scan(self):
        """Structural proof: a live-tree scan with ONE manifest + ONE entity, each
        missing fields only relevant to the OTHER schema, produces errors attributable
        ONLY to each entry's OWN schema (never cross-applied)."""
        test_root = ROOT / '.tmp-vault-capsule-forge-tests'
        test_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(test_root)) as tmp:
            root = Path(tmp)
            (root / 'vault' / 'files').mkdir(parents=True)
            (root / 'vault' / '00-index.jsonl').write_text('')
            # A conforming manifest instance (no principal/subtype field at all).
            (root / 'vault' / 'files' / 'aaaaaaaa.md').write_text(
                "---\nuid: aaaaaaaa\ntype: vault\nkind: team\nowner: talos\n"
                "audience: bbbbbbbb\nremote: git@x:y.git\n"
                "prefix_policy:\n  references: 32067bea\n"
                "publish_policy:\n  publishers: [talos]\n"
                "curation_policy:\n  mode: gardener\n"
                "curator: orpheus\nversion: 1.0.0\nstatus: active\n"
                "contract:\n  types: [task]\n"
                "regulated_acceptance:\n  accepted: false\n"
                "---\n\nFixture manifest.\n"
            )
            # A conforming vault-entity instance (no kind/remote/audience/curator fields at all).
            (root / 'vault' / 'files' / 'cccccccc.md').write_text(
                "---\nuid: cccccccc\ntype: entity\nsubtype: vault-entity\n"
                "principal: dddddddd\nextraction_scope: fixture-scope\n"
                "---\n\nFixture entity.\n"
            )
            findings, checked, violations = VALIDATOR.check_vault_capsule_types(root)
            self.assertEqual(checked, 2)
            self.assertEqual(violations, 0, findings)


class TestAC6MinterKindVault(unittest.TestCase):
    """AC6 — `tropo-mint-id.py --kind vault` mints without NotImplementedError; the
    identifier SHAPE is the ADR-050 Decision 3 "short registered code" (4-6 lowercase
    alnum), NOT the flat-8-hex file/agent shape (943bb220's own caution: "do not assume
    it matches file/agent's flat-8-hex shape without checking the spec")."""

    def test_kind_vault_is_declared_and_implemented(self):
        self.assertIn('vault', MINT.VALID_KINDS)
        self.assertIn('vault', MINT._IMPLEMENTED_KINDS)

    def test_kind_vault_mints_without_not_implemented_error(self):
        codes = MINT.mint(1, kind='vault', studio_root=Path('/nonexistent-fixture-root'))
        self.assertEqual(len(codes), 1)

    def test_kind_vault_shape_is_short_registered_code_not_flat_hex8(self):
        codes = MINT.mint(1, kind='vault', studio_root=Path('/nonexistent-fixture-root'))
        self.assertRegex(codes[0], SHORT_CODE_RE, 'vault code must be 4-6 lowercase alnum')
        self.assertNotRegex(codes[0], r'^[0-9a-f]{8}$', 'vault code must NOT be flat 8-hex (file/agent shape)')

    def test_kind_vault_mints_count_greater_than_one_all_distinct(self):
        codes = MINT.mint(5, kind='vault', studio_root=Path('/nonexistent-fixture-root'))
        self.assertEqual(len(codes), 5)
        self.assertEqual(len(set(codes)), 5, 'vault codes minted in one call must not collide')
        for c in codes:
            self.assertRegex(c, SHORT_CODE_RE)

    def test_kind_vault_rejects_explicit_prefix(self):
        with self.assertRaises(ValueError):
            MINT.mint(1, kind='vault', prefix='nope', studio_root=Path('/nonexistent-fixture-root'))

    def test_kind_vault_disjoint_from_this_studios_mint_prefix(self):
        """A composed <studio_prefix>-<vault_code> federated identifier must never
        self-collide: a fresh vault code must never equal this studio's own mint_prefix."""
        test_root = ROOT / '.tmp-vault-capsule-forge-tests'
        test_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(test_root)) as tmp:
            fixture_root = Path(tmp)
            identity = MINT.mint_studio_identity(root=fixture_root)
            existing = {identity['mint_prefix']}
            codes = MINT.mint(20, kind='vault', studio_root=fixture_root, extra_existing=set())
            for c in codes:
                self.assertNotIn(c, existing, 'a vault code collided with this studio\'s own mint_prefix')

    def test_kind_vault_respects_extra_existing_exclusion_set(self):
        codes_first = MINT.mint(1, kind='vault', studio_root=Path('/nonexistent-fixture-root'))
        codes_second = MINT.mint(
            1, kind='vault', studio_root=Path('/nonexistent-fixture-root'),
            extra_existing=set(codes_first),
        )
        self.assertNotEqual(codes_first[0], codes_second[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
