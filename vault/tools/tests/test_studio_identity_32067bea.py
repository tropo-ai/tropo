#!/usr/bin/env python3
"""Studio-Identity Primitive gauntlets — dev-spec 32067bea acceptance criteria.

Federation Phase A ("the crux"): a self-sovereign studio-identity manifest, minted
locally at genesis, plus segment-aware mint prefixing (team reads the manifest and
prefixes; private stays bare). Composes ADR-050 (cb0f8e46) `--kind studio`.

Three mandatory fixtures per Argus's MODERATE calibration:
  AC2 — two freshly-initialized studios produce two DISTINCT studio-identity codes.
  AC4 — two segments (team vs private) on the SAME studio produce two different UID
        SHAPES (prefixed vs bare) for the same underlying mint call.
  AC5 — a team-segment write with a MISSING or CORRUPT manifest FAILS LOUD.

None of these need a live git repo, so they run for real in this sandbox (no skips).
"""
from __future__ import annotations

import importlib.util
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
    spec.loader.exec_module(mod)
    return mod


MINT = _load('tropo_mint_id', TOOLS / 'tropo-mint-id.py')


class StudioFixture:
    """Minimal isolated studio tree — no git needed for this dev-spec's fixtures."""

    def __init__(self):
        test_root = ROOT / '.tmp-studio-identity-tests'
        test_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=str(test_root))
        self.root = Path(self.tmp.name)
        (self.root / 'vault' / 'files').mkdir(parents=True)
        (self.root / 'vault' / '00-index.jsonl').write_text('')

    def cleanup(self):
        self.tmp.cleanup()


class TestAC1ManifestShape(unittest.TestCase):
    """AC1 — the manifest exists at the stable path with the required fields."""

    def test_genesis_writes_expected_fields_at_stable_path(self):
        fx = StudioFixture()
        try:
            identity = MINT.mint_studio_identity(root=fx.root, minted_by='test-suite')
            manifest_path = fx.root / '.tropo' / 'studio-identity.md'
            self.assertTrue(manifest_path.exists())
            for field in ('studio_id', 'mint_prefix', 'created', 'minted_by',
                          'hq_registered', 'schema_version'):
                self.assertIn(field, identity, f'missing required field {field!r}')
            self.assertRegex(identity['studio_id'], r'^[0-9a-f]{8}$')
            self.assertRegex(identity['mint_prefix'], r'^[a-z0-9]{4,6}$')
            self.assertIs(identity['hq_registered'], False)
            self.assertEqual(identity['minted_by'], 'test-suite')
        finally:
            fx.cleanup()


class TestAC2TwoStudiosDistinct(unittest.TestCase):
    """AC2 — two freshly-initialized studios produce two DISTINCT identity codes."""

    def test_two_fresh_studios_mint_distinct_studio_id_and_prefix(self):
        fx_a = StudioFixture()
        fx_b = StudioFixture()
        try:
            identity_a = MINT.mint_studio_identity(root=fx_a.root)
            identity_b = MINT.mint_studio_identity(root=fx_b.root)
            self.assertNotEqual(identity_a['studio_id'], identity_b['studio_id'],
                                 'two fresh studios collided on studio_id')
            self.assertNotEqual(identity_a['mint_prefix'], identity_b['mint_prefix'],
                                 'two fresh studios collided on mint_prefix')
        finally:
            fx_a.cleanup()
            fx_b.cleanup()

    def test_genesis_mints_no_network_no_hq_dependency(self):
        # Self-sovereign: minting works purely against a local, otherwise-empty tree.
        # There is no HQ client/URL/socket import anywhere in the tool; assert that
        # structurally rather than by (unavailable) network mocking.
        text = (TOOLS / 'tropo-mint-id.py').read_text()
        for banned in ('requests.', 'urllib.request', 'socket.', 'http.client'):
            self.assertNotIn(banned, text, f'studio genesis must stay offline; found {banned!r}')


class TestAC3GenesisIdempotent(unittest.TestCase):
    """The dev-spec's genesis gesture must be idempotent — re-running never regenerates."""

    def test_second_call_reads_back_unchanged(self):
        fx = StudioFixture()
        try:
            first = MINT.mint_studio_identity(root=fx.root)
            second = MINT.mint_studio_identity(root=fx.root)
            self.assertEqual(first, second)
        finally:
            fx.cleanup()

    def test_cli_kind_studio_idempotent_via_mint(self):
        fx = StudioFixture()
        try:
            first = MINT.mint(1, kind='studio', studio_root=fx.root)
            second = MINT.mint(1, kind='studio', studio_root=fx.root)
            self.assertEqual(first, second)
        finally:
            fx.cleanup()

    def test_kind_studio_rejects_explicit_prefix(self):
        fx = StudioFixture()
        try:
            with self.assertRaises(ValueError):
                MINT.mint(1, kind='studio', prefix='nope', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_kind_studio_rejects_count_other_than_one(self):
        fx = StudioFixture()
        try:
            with self.assertRaises(ValueError):
                MINT.mint(3, kind='studio', studio_root=fx.root)
        finally:
            fx.cleanup()


class TestAC4SegmentAwareShapes(unittest.TestCase):
    """AC4 — same tool, two segments, two UID shapes on the SAME studio."""

    def test_team_prefixed_private_bare_same_studio(self):
        fx = StudioFixture()
        try:
            identity = MINT.mint_studio_identity(root=fx.root)
            private_uid = MINT.mint(1, kind='file', segment='private', studio_root=fx.root)[0]
            team_uid = MINT.mint(1, kind='file', segment='team', studio_root=fx.root)[0]

            self.assertRegex(private_uid, r'^[0-9a-f]{8}$',
                              'private-segment mint must stay bare 8-hex')
            self.assertRegex(team_uid, rf"^{identity['mint_prefix']}-[0-9a-f]{{8}}$",
                              'team-segment mint must be <mint_prefix>-<8hex>')
            self.assertNotEqual(private_uid, team_uid)
        finally:
            fx.cleanup()

    def test_agent_kind_also_segment_aware(self):
        fx = StudioFixture()
        try:
            identity = MINT.mint_studio_identity(root=fx.root)
            private_uid = MINT.mint(1, kind='agent', segment='private', studio_root=fx.root)[0]
            team_uid = MINT.mint(1, kind='agent', segment='team', studio_root=fx.root)[0]
            self.assertRegex(private_uid, r'^[0-9a-f]{8}$')
            self.assertTrue(team_uid.startswith(identity['mint_prefix'] + '-'))
        finally:
            fx.cleanup()

    def test_default_segment_is_private(self):
        fx = StudioFixture()
        try:
            MINT.mint_studio_identity(root=fx.root)
            default_uid = MINT.mint(1, kind='file', studio_root=fx.root)[0]
            self.assertRegex(default_uid, r'^[0-9a-f]{8}$',
                              'default segment must remain private/bare (no regression)')
        finally:
            fx.cleanup()

    def test_explicit_prefix_with_team_segment_rejected(self):
        fx = StudioFixture()
        try:
            MINT.mint_studio_identity(root=fx.root)
            with self.assertRaises(ValueError):
                MINT.mint(1, kind='file', segment='team', prefix='manual', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_unknown_segment_rejected(self):
        fx = StudioFixture()
        try:
            with self.assertRaises(ValueError):
                MINT.mint(1, kind='file', segment='bogus', studio_root=fx.root)
        finally:
            fx.cleanup()


class TestAC5FailLoudOnMissingOrCorruptManifest(unittest.TestCase):
    """AC5 — a team-segment write with a MISSING or CORRUPT manifest FAILS LOUD.

    Never silently falls back to an unprefixed or fabricated identity.
    """

    def test_missing_manifest_raises_studio_identity_error(self):
        fx = StudioFixture()
        try:
            # No mint_studio_identity() call — the manifest genuinely does not exist.
            with self.assertRaises(MINT.StudioIdentityError):
                MINT.mint(1, kind='file', segment='team', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_missing_manifest_never_falls_back_to_bare(self):
        """The failure mode itself is the assertion: no UID is ever returned."""
        fx = StudioFixture()
        try:
            try:
                MINT.mint(1, kind='file', segment='team', studio_root=fx.root)
                self.fail('team-segment mint with no manifest must raise, not return a UID')
            except MINT.StudioIdentityError:
                pass
        finally:
            fx.cleanup()

    def test_corrupt_manifest_invalid_yaml_raises(self):
        fx = StudioFixture()
        try:
            manifest_path = fx.root / '.tropo' / 'studio-identity.md'
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text('---\nstudio_id: [unterminated\n---\n', encoding='utf-8')
            with self.assertRaises(MINT.StudioIdentityError):
                MINT.mint(1, kind='file', segment='team', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_corrupt_manifest_missing_frontmatter_raises(self):
        fx = StudioFixture()
        try:
            manifest_path = fx.root / '.tropo' / 'studio-identity.md'
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text('# Not a manifest at all\n', encoding='utf-8')
            with self.assertRaises(MINT.StudioIdentityError):
                MINT.mint(1, kind='file', segment='team', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_corrupt_manifest_missing_required_field_raises(self):
        fx = StudioFixture()
        try:
            manifest_path = fx.root / '.tropo' / 'studio-identity.md'
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                '---\nstudio_id: deadbeef\nmint_prefix: ab12c\n---\n\nMissing fields.\n',
                encoding='utf-8',
            )
            with self.assertRaises(MINT.StudioIdentityError):
                MINT.mint(1, kind='file', segment='team', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_corrupt_manifest_malformed_studio_id_raises(self):
        fx = StudioFixture()
        try:
            manifest_path = fx.root / '.tropo' / 'studio-identity.md'
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                '---\n'
                'studio_id: not-hex-at-all\n'
                'mint_prefix: ab12c\n'
                'created: "2026-07-06"\n'
                'minted_by: test\n'
                'hq_registered: false\n'
                'schema_version: 1\n'
                '---\n\nBody.\n',
                encoding='utf-8',
            )
            with self.assertRaises(MINT.StudioIdentityError):
                MINT.mint(1, kind='file', segment='team', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_corrupt_manifest_malformed_prefix_raises(self):
        fx = StudioFixture()
        try:
            manifest_path = fx.root / '.tropo' / 'studio-identity.md'
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                '---\n'
                'studio_id: deadbeef\n'
                'mint_prefix: "TOO-LONG-PREFIX!!"\n'
                'created: "2026-07-06"\n'
                'minted_by: test\n'
                'hq_registered: false\n'
                'schema_version: 1\n'
                '---\n\nBody.\n',
                encoding='utf-8',
            )
            with self.assertRaises(MINT.StudioIdentityError):
                MINT.mint(1, kind='file', segment='team', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_private_segment_unaffected_by_missing_manifest(self):
        """The fail-loud rule is scoped to team writes — private must keep working
        with no manifest at all (today's default single-Studio behavior, unchanged)."""
        fx = StudioFixture()
        try:
            uid = MINT.mint(1, kind='file', segment='private', studio_root=fx.root)[0]
            self.assertRegex(uid, r'^[0-9a-f]{8}$')
        finally:
            fx.cleanup()

    def test_read_studio_identity_directly_raises_on_missing(self):
        fx = StudioFixture()
        try:
            with self.assertRaises(MINT.StudioIdentityError):
                MINT.read_studio_identity(root=fx.root)
        finally:
            fx.cleanup()


class TestReservedPrefixNamespace(unittest.TestCase):
    """d89b5da3: `tropo` is a reserved namespace; a genesis mint must never claim it."""

    def test_generated_prefix_never_equals_reserved_word(self):
        for _ in range(200):
            prefix = MINT._generate_mint_prefix()
            self.assertNotEqual(prefix, 'tropo')


if __name__ == '__main__':
    unittest.main(verbosity=2)
