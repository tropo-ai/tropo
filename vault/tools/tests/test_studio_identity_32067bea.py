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

# 3d430852 suite migration: mint-output assertions follow the AUTHORITY mint
# constant incl. studio_id — Stage A passed unchanged; the Stage B flip is
# followed, not broken. The team-segment parked-seam cases assert their
# refusal exactly as before.
_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
from lib.governed_path import MINT_HEX_LEN as _MINT_LEN  # noqa: E402
_MINT_SHAPE = r'^[0-9a-f]{%d}$' % _MINT_LEN

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
                          'hq_registered', 'schema_version', 'entity_name'):
                self.assertIn(field, identity, f'missing required field {field!r}')
            self.assertRegex(identity['studio_id'], _MINT_SHAPE)  # follows the authority constant
            self.assertRegex(identity['mint_prefix'], r'^[a-z0-9]{4,6}$')
            self.assertIs(identity['hq_registered'], False)
            self.assertEqual(identity['minted_by'], 'test-suite')
            # 5854773a AC3: silent folder-name default, never blank.
            self.assertEqual(identity['entity_name'], fx.root.resolve().name)
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
    """AC4 at the Stage B flip (3d430852): private/default mints are COMPOSITE
    — the studio's issued 4-hex prefix + 8 local hex, no separator — and the
    team segment PARKS with a loud refusal: the hyphenated
    <mint_prefix>-<hex> identifier retired when composites became the mint."""

    def test_team_parks_private_mints_composite_same_studio(self):
        fx = StudioFixture()
        try:
            identity = MINT.mint_studio_identity(root=fx.root)
            prefix = identity['mint_prefix']
            self.assertRegex(prefix, r'^[0-9a-f]{4}$',
                             'the issued prefix is exactly 4-hex at the flip')
            private_uid = MINT.mint(1, kind='file', segment='private', studio_root=fx.root)[0]
            self.assertRegex(private_uid, rf"^{prefix}[0-9a-f]{{8}}$",
                             'private-segment mint is composite: issued prefix + 8 local, no separator')
            with self.assertRaises(ValueError) as parked:
                MINT.mint(1, kind='file', segment='team', studio_root=fx.root)
            self.assertIn('PARKED', str(parked.exception),
                          'the team park names itself')
        finally:
            fx.cleanup()

    def test_agent_kind_composite_and_team_parks_too(self):
        fx = StudioFixture()
        try:
            identity = MINT.mint_studio_identity(root=fx.root)
            private_uid = MINT.mint(1, kind='agent', segment='private', studio_root=fx.root)[0]
            self.assertTrue(private_uid.startswith(identity['mint_prefix']))
            self.assertRegex(private_uid, rf"^[0-9a-f]{{12}}$")
            with self.assertRaises(ValueError):
                MINT.mint(1, kind='agent', segment='team', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_default_segment_mints_composite(self):
        fx = StudioFixture()
        try:
            identity = MINT.mint_studio_identity(root=fx.root)
            default_uid = MINT.mint(1, kind='file', studio_root=fx.root)[0]
            self.assertRegex(default_uid,
                             rf"^{identity['mint_prefix']}[0-9a-f]{{8}}$",
                             'the default mint carries the issued prefix — '
                             'every new bare mint is composite (no regression to flat random)')
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

    def test_explicit_prefix_parks_at_the_flip(self):
        """The S8 --prefix seam retired with the hyphen (3d430852): found live
        by Metis at the flip verify — `--prefix abcd` produced
        abcd-f015b0743329, a ruled-out hyphen wrapped around an
        already-namespaced composite. Substitution was considered and refused:
        an explicit foreign prefix would mint identity in a namespace this
        studio cannot assign (the issued-prefix ruling cuts both ways)."""
        fx = StudioFixture()
        try:
            MINT.mint_studio_identity(root=fx.root)
            with self.assertRaises(ValueError) as parked:
                MINT.mint(1, kind='file', prefix='abcd', studio_root=fx.root)
            self.assertIn('PARKED', str(parked.exception))
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
    """AC5 at the Stage B flip — the manifest-reading mint FAILS LOUD.

    The team segment parked, so the fail-loud contract rides the BARE mint:
    composite generation reads the studio-identity manifest, and a missing or
    corrupt one raises StudioIdentityError — never silently falls back to a
    flat-random or fabricated identity (Metis-ruled: a studio never
    self-assigns a prefix; refuse-if-absent is the design).
    """

    def test_missing_manifest_raises_studio_identity_error(self):
        fx = StudioFixture()
        try:
            # No mint_studio_identity() call — the manifest genuinely does not exist.
            with self.assertRaises(MINT.StudioIdentityError):
                MINT.mint(1, kind='file', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_missing_manifest_never_falls_back_to_bare(self):
        """The failure mode itself is the assertion: no UID is ever returned."""
        fx = StudioFixture()
        try:
            try:
                MINT.mint(1, kind='file', studio_root=fx.root)
                self.fail('composite mint with no manifest must raise, not return a UID')
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
                MINT.mint(1, kind='file', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_corrupt_manifest_missing_frontmatter_raises(self):
        fx = StudioFixture()
        try:
            manifest_path = fx.root / '.tropo' / 'studio-identity.md'
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text('# Not a manifest at all\n', encoding='utf-8')
            with self.assertRaises(MINT.StudioIdentityError):
                MINT.mint(1, kind='file', studio_root=fx.root)
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
                MINT.mint(1, kind='file', studio_root=fx.root)
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
                MINT.mint(1, kind='file', studio_root=fx.root)
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
                MINT.mint(1, kind='file', studio_root=fx.root)
        finally:
            fx.cleanup()

    def test_private_segment_requires_the_manifest_at_the_flip(self):
        """Doctrine INVERTED at the Stage B flip: private (bare composite) mints
        READ the manifest and refuse without it — a studio must never
        self-assign a random prefix (Metis-ruled, 3d430852). This row asserted
        the retired single-Studio behavior until the flip; it now pins the
        refuse-if-absent contract that makes the composite seam honest."""
        fx = StudioFixture()
        try:
            with self.assertRaises(MINT.StudioIdentityError):
                MINT.mint(1, kind='file', segment='private', studio_root=fx.root)
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
