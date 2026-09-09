"""Actual mint behavior after one isolated edit to the width history.

No live width flip or index writes: each case executes a fresh authority and
minter against a temporary Studio. Only entropy is controlled; the manifest
reader, collision scanner, filename parser, and retry loop are production code.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
import types
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import lib
from lib import governed_path as live_gp


def load_for_history(history):
    """Change only the authority's history, then import the real consumers."""
    path = TOOLS / 'lib/governed_path.py'
    tree = ast.parse(path.read_text(), filename=str(path))
    assignments = [node for node in tree.body if isinstance(node, ast.AnnAssign)
                   and isinstance(node.target, ast.Name)
                   and node.target.id == 'MINT_HEX_HISTORY']
    assert len(assignments) == 1, 'the width history must have exactly one home'
    assignments[0].value = ast.parse(repr(history), mode='eval').body
    ast.fix_missing_locations(tree)
    authority = types.ModuleType('isolated_governed_path')
    authority.__file__ = str(path)
    exec(compile(tree, str(path), 'exec'), authority.__dict__)
    spec = importlib.util.spec_from_file_location('isolated_minter', TOOLS / 'tropo-mint-id.py')
    minter = importlib.util.module_from_spec(spec)
    with patch.object(lib, 'governed_path', authority):
        spec.loader.exec_module(minter)
    assert minter.gp is authority
    assert lib.governed_path is live_gp
    return authority, minter


class CurrentMintWidth(unittest.TestCase):
    history = (8, 12)

    def setUp(self):
        self.gp, self.minter = load_for_history(self.history)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'vault/files').mkdir(parents=True)
        # Existing identity is retained when the generation width changes.
        self.identity = dict(studio_id='f01512345678', mint_prefix='f015',
                             created='2026-09-07', minted_by='fixture',
                             hq_registered=False, schema_version=1,
                             entity_name='Fixture Studio')
        self.manifest = self.root / self.minter.STUDIO_IDENTITY_REL
        self.minter._write_manifest(self.manifest, self.identity)

    def test_history_retains_old_shapes_and_derives_generation(self):
        gp = self.gp
        self.assertEqual(gp.MINT_HEX_LEN, self.history[-1])
        self.assertEqual(gp.UID_SHAPES, frozenset(self.history))
        for width in self.history:
            with self.subTest(width=width):
                uid = 'a' * width
                self.assertTrue(gp.is_governed_uid_shape(uid))
                self.assertEqual(gp.parse_anchored_uid(f'readable-title-{uid}.md'),
                                 ('readable-title', uid))
                self.assertEqual(gp.new_uid_is_valid_shape(uid), width == gp.MINT_HEX_LEN)
        self.assertTrue(gp.is_legacy_uid('a' * 8))
        for width in range(max(gp.UID_SHAPES) + 5):
            self.assertEqual(gp.is_governed_uid_shape('a' * width), width in gp.UID_SHAPES)

    def test_file_and_agent_keep_prefix_and_current_random_width(self):
        local_width = self.gp.MINT_HEX_LEN - 4
        for kind in ('file', 'agent'):
            with self.subTest(kind=kind):
                digits = iter('ab')
                with patch.object(self.minter.secrets, 'token_hex',
                                  side_effect=lambda n: next(digits) * (2 * n)) as entropy:
                    minted = self.minter.mint(2, kind=kind, studio_root=self.root)
                self.assertEqual(minted, ['f015' + digit * local_width for digit in 'ab'])
                self.assertEqual([call.args for call in entropy.call_args_list],
                                 [(local_width // 2,), (local_width // 2,)])
                self.assertTrue(all(self.gp.new_uid_is_valid_shape(uid) for uid in minted))

    def _check_collision_surface(self, surface):
        local_width = self.gp.MINT_HEX_LEN - 4
        collision = 'f015' + 'a' * local_width
        if surface == 'filename':
            (self.root / 'vault/files' / f'unindexed-title-{collision}.md').write_text('# claimed\n')
        else:
            name = '00-archive-index.jsonl' if surface == 'archive' else '00-index.jsonl'
            value = collision.upper() if surface == 'uppercase-index' else collision
            (self.root / 'vault' / name).write_text(json.dumps({'uid': value}) + '\n')
        self.assertIn(collision, self.minter.load_existing_uids(studio_root=self.root))
        digits = iter('abbc')  # persisted collision, free b, in-batch collision, free c
        with patch.object(self.minter.secrets, 'token_hex',
                          side_effect=lambda n: next(digits) * (2 * n)):
            self.assertEqual(self.minter.mint(2, studio_root=self.root),
                             ['f015' + digit * local_width for digit in 'bc'])

    def test_current_index_collision(self):
        self._check_collision_surface('current')

    def test_archive_index_collision(self):
        self._check_collision_surface('archive')

    def test_unindexed_filename_collision(self):
        self._check_collision_surface('filename')

    def test_uppercase_index_collision_is_conservatively_reserved(self):
        self._check_collision_surface('uppercase-index')

    def test_collision_storm_refuses_after_bounded_retries(self):
        collision = 'f015' + 'a' * (self.gp.MINT_HEX_LEN - 4)
        with patch.object(self.minter.secrets, 'token_hex',
                          side_effect=lambda n: 'a' * (n * 2)) as entropy:
            with self.assertRaisesRegex(RuntimeError, 'collision storm'):
                self.minter.mint(1, studio_root=self.root, extra_existing={collision})
        self.assertEqual(entropy.call_count, 64)

    def test_collision_scan_keeps_all_historical_widths(self):
        expected = {'a' * width for width in self.history}
        (self.root / 'vault/00-archive-index.jsonl').write_text(
            ''.join(json.dumps({'uid': uid}) + '\n' for uid in expected))
        self.assertEqual(self.minter.load_existing_uids(studio_root=self.root), expected)

    def test_genesis_uses_current_composite_shape_and_is_idempotent(self):
        fresh = self.root / 'fresh-studio'
        minted = self.minter.mint(1, kind='studio', studio_root=fresh)[0]
        identity = self.minter.read_studio_identity(fresh)
        self.assertEqual(minted, identity['studio_id'])
        self.assertTrue(self.gp.new_uid_is_valid_shape(minted))
        self.assertTrue(self.gp.is_composite_mint_prefix(identity['mint_prefix']))
        self.assertTrue(minted.startswith(identity['mint_prefix']))
        self.assertEqual(self.minter.mint(1, kind='studio', studio_root=fresh), [minted])
        self.assertEqual(self.minter.read_studio_identity(fresh), identity)

    def test_composite_mint_refuses_unusable_identity_without_entropy(self):
        for bad_identity in ('missing', 'corrupt', 'nonhex-prefix'):
            with self.subTest(bad_identity=bad_identity):
                root = self.root
                if bad_identity == 'missing':
                    root = root / 'missing-studio'
                elif bad_identity == 'corrupt':
                    self.manifest.write_text('not frontmatter\n')
                else:
                    self.identity['mint_prefix'] = 'zzzz'
                    self.minter._write_manifest(self.manifest, self.identity)
                with patch.object(self.minter.secrets, 'token_hex') as entropy:
                    with self.assertRaises(self.minter.StudioIdentityError):
                        self.minter.mint(1, studio_root=root)
                    entropy.assert_not_called()

    def test_new_width_does_not_revive_parked_namespace_seams(self):
        for kwargs in (dict(prefix='other'), dict(segment='team')):
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, 'PARKED'):
                    self.minter.mint(1, studio_root=self.root, **kwargs)

    def test_manifest_admission_stays_strict(self):
        valid = 'a' * self.gp.MINT_HEX_LEN
        for malformed in (valid.upper(), valid[:-1] + '\n', valid[:-1] + ' '):
            with self.subTest(malformed=malformed):
                self.assertFalse(self.gp.is_governed_uid_shape(malformed))
                self.assertFalse(self.gp.new_uid_is_valid_shape(malformed))
                self.identity['studio_id'] = malformed
                self.minter._write_manifest(self.manifest, self.identity)
                with self.assertRaises(self.minter.StudioIdentityError):
                    self.minter.read_studio_identity(self.root)

    def test_bare_current_uid_cannot_become_a_human_entity_name(self):
        with self.assertRaisesRegex(ValueError, 'bare hex uid'):
            self.minter.set_entity_name('a' * self.gp.MINT_HEX_LEN, root=self.root)
        self.assertEqual(self.minter.read_studio_identity(self.root), self.identity)


class FutureMintWidth(CurrentMintWidth):
    history = (8, 12, 16)


class InvalidAndLegacyConfigurations(unittest.TestCase):
    def test_partial_composite_configuration_refuses_before_entropy(self):
        for width in (8, 10, 13, 15):
            with self.subTest(width=width):
                history = (8,) if width == 8 else (8, 12, width)
                gp, _ = load_for_history(history)
                with patch.object(gp.secrets, 'token_hex') as entropy:
                    with self.assertRaisesRegex(RuntimeError, 'cannot mint a composite UID'):
                        gp.composite_uid('f015')
                    entropy.assert_not_called()

    def test_legacy_generation_remains_available_in_legacy_configuration(self):
        gp, minter = load_for_history((8,))
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(minter.secrets, 'token_hex', side_effect=lambda n: 'a' * (n * 2)):
                self.assertFalse(gp.mint_is_composite())
                self.assertEqual(minter.mint(1, studio_root=Path(directory)), ['a' * 8])


if __name__ == '__main__':
    unittest.main(verbosity=2)
