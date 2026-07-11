#!/usr/bin/env python3
"""v1.82 Gardener gauntlets — test-spec c220d66f (paired to dev-spec 8e551957).

Seven behaviors, one per acceptance criterion. Plant → watch → remove pattern.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'vault' / 'tools'))

from lib.gardener import (  # noqa: E402
    DEFAULT_THRESHOLDS,
    apply_gardener_pass,
    backfill_extraction_scope_by_path,
    discriminate_segment,
    gardener_flags_stale,
    l2_backlog_counts,
    load_gardener_config,
    resolve_effective_scope,
    safety_net_segment,
    wall_clock_age_days,
)


def _rec(uid: str, **kwargs) -> dict:
    base = {'uid': uid, 'type': 'note', 'state': 'active', 'status': 'draft',
            'created': '2026-01-01', 'path': f'vault/files/{uid}.md'}
    base.update(kwargs)
    return base


class TestGardenerS0Backfill(unittest.TestCase):
    """AC1 — D0-lite backfill + os|private discriminator."""

    def test_kernel_path_backfill_os(self):
        scope, bf = resolve_effective_scope(_rec('aabbcc01', path='.tropo/kernel/foo.md'))
        self.assertTrue(bf)
        self.assertEqual(scope, 'ship')
        seg = discriminate_segment(_rec('aabbcc01', path='.tropo/kernel/foo.md'), scope, set())
        self.assertEqual(seg, 'os')

    def test_agents_path_backfill_private(self):
        scope = backfill_extraction_scope_by_path('agents/talos/foo.md')
        self.assertEqual(scope, 'argo-private')
        seg = discriminate_segment(_rec('aabbcc02', extraction_scope=scope), scope, set())
        self.assertEqual(seg, 'private')

    def test_unlisted_path_safety_net(self):
        self.assertEqual(safety_net_segment('.tropo/foo.md'), 'os')
        self.assertEqual(safety_net_segment('unknown/path.md'), 'private')

    def test_gauntlet_plant_unscoped_kernel(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / 'vault' / 'files').mkdir(parents=True)
            (vault / '.tropo').mkdir()
            (vault / '.tropo-studio').mkdir()
            plant_uid = 'deadbeef'
            records = [_rec(plant_uid, path='.tropo/kernel/plant.md')]
            stats = apply_gardener_pass(vault, records, apply_writes=False)
            self.assertEqual(records[0]['segment'], 'os')
            self.assertEqual(records[0]['extraction_scope'], 'ship')
            # remove plant
            records = []
            stats2 = apply_gardener_pass(vault, records, apply_writes=False)
            self.assertEqual(stats2['unscoped_after'], 0)


class TestGardenerS1SegmentLocal(unittest.TestCase):
    """AC2 — viewer-free per-segment stamping."""

    def test_promoted_at_prevents_machine_aged(self):
        from lib.gardener import signal_machine_aged
        rec = _rec('aabbcc03', created='2026-01-01', promoted_at='2026-06-01',
                   created_by='foo.py', status='draft')
        as_of = date(2026, 6, 15)
        self.assertIsNone(signal_machine_aged(rec, as_of))

    def test_cross_segment_lint_surfaced(self):
        os_node = _rec('os000001', extraction_scope='ship', path='vault/files/os000001.md',
                       modified='2026-06-01', created='2026-06-01')
        private = _rec('priv0001', refs=['os000001'], path='agents/talos/x.md',
                       extraction_scope='argo-private', modified='2026-06-01', created='2026-06-01')
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / '.tropo-studio').mkdir()
            stats = apply_gardener_pass(vault, [os_node, private], apply_writes=False)
            self.assertEqual(os_node['segment'], 'os')
            self.assertEqual(private['segment'], 'private')
            self.assertGreaterEqual(stats['lint_count'], 1)
            self.assertEqual(os_node.get('inbound_live_edges'), 0)

    def test_member_of_cycle_does_not_crash(self):
        a = _rec('cyc00001', member_of=['cyc00002'])
        b = _rec('cyc00002', member_of=['cyc00001'])
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / '.tropo-studio').mkdir()
            apply_gardener_pass(vault, [a, b], apply_writes=False)
            self.assertIn('decay', a)
            self.assertIn('decay', b)

    def test_nested_tropo_path_segments_os(self):
        scope, _ = resolve_effective_scope(_rec('aabbcc04', path='argo-os/.tropo/kernel/x.md'))
        self.assertEqual(scope, 'ship')
        self.assertEqual(safety_net_segment('peer/studio/.tropo/foo.md'), 'os')


class TestGardenerS1Calibration(unittest.TestCase):
    """AC3 — adjudicated ~6% clean set + annotate-only."""

    def test_lineage_type_excluded_from_clean_set(self):
        rec = _rec('actv0001', type='activation', state='active', status='done')
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / '.tropo-studio').mkdir()
            apply_gardener_pass(vault, [rec], apply_writes=False)
            self.assertFalse(rec['decay']['stale'])

    def test_published_not_terminal_contradiction(self):
        rec = _rec('pub00001', state='active', status='published')
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / '.tropo-studio').mkdir()
            apply_gardener_pass(vault, [rec], apply_writes=False)
            self.assertFalse(rec['decay']['stale'])


class TestGardenerS2WallClock(unittest.TestCase):
    """AC4 — wall-clock overlay + configurable window + two-consumer proof."""

    def test_45_day_two_consumer_proof(self):
        rec = _rec('draft045', status='draft', modified='2026-05-21', created='2026-05-21')
        as_of = date(2026, 7, 5)
        age = wall_clock_age_days(rec, as_of)
        self.assertGreaterEqual(age, 45)
        cfg = dict(DEFAULT_THRESHOLDS)
        self.assertFalse(gardener_flags_stale(rec, age, cfg))  # gardener: <90d
        self.assertTrue(l2_backlog_counts(rec, age))  # L2: >=30d

    def test_config_knob_changes_flagging(self):
        rec = _rec('draft095', status='draft', modified='2026-04-01')
        age = 95
        cfg90 = {'decay_threshold_unshared_draft_days': 90, 'decay_threshold_general_days': 180}
        cfg120 = {'decay_threshold_unshared_draft_days': 120, 'decay_threshold_general_days': 180}
        self.assertTrue(gardener_flags_stale(rec, age, cfg90))
        self.assertFalse(gardener_flags_stale(rec, age, cfg120))


class TestGardenerS3SupersededOS(unittest.TestCase):
    """AC5 — superseded-OS walked-but-flagged."""

    def test_superseded_adr_flagged_not_live(self):
        rec = _rec('adr00001', type='decision', state='archived', status='superseded',
                   superseded_by='adr00002', extraction_scope='ship')
        rec['segment'] = 'os'
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / '.tropo-studio').mkdir()
            apply_gardener_pass(vault, [rec], apply_writes=False)
            self.assertTrue(rec.get('superseded_os'))
            self.assertEqual(rec.get('superseded_by_projection'), 'adr00002')


class TestGardenerI5NeverSync(unittest.TestCase):
    """AC6 — source frontmatter byte-unchanged."""

    def test_no_source_write_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            files = vault / 'vault' / 'files'
            files.mkdir(parents=True)
            (vault / '.tropo-studio').mkdir()
            uid = 'cafebabe'
            original = "---\nuid: cafebabe\ntype: note\nstatus: draft\nstate: active\n---\n# Body\n"
            fp = files / f'{uid}.md'
            fp.write_text(original, encoding='utf-8')
            before = fp.read_bytes()
            rec = _rec(uid, status='done', state='active')  # contradiction → stale
            apply_gardener_pass(vault, [rec], apply_writes=True)
            after = fp.read_bytes()
            self.assertEqual(before, after)


class TestGardenerMaintenanceLoop(unittest.TestCase):
    """AC7 — registered maintenance loop."""

    def test_config_file_loads(self):
        cfg_path = ROOT / 'vault' / 'files' / 'be2296f9.md'
        if cfg_path.exists():
            cfg = load_gardener_config(ROOT)
            self.assertEqual(cfg['decay_threshold_unshared_draft_days'], 90)
            self.assertEqual(cfg['decay_threshold_general_days'], 180)

    def test_loop_registry_exists(self):
        self.assertTrue((ROOT / 'vault' / 'files' / 'be2296f9.md').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
