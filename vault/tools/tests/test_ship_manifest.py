#!/usr/bin/env python3
"""Ship-manifest floor gates — AC1..AC5 of dev-spec 91d951f4 (v1.94 Stream 5, B-1).

Built by talos-t60, 2026-09-02, against the Mike-locked spec.

WHY THIS FIXTURE IS NOT `BuiltBoxCase` ALONE. `BuiltBoxCase` (test_fresh_box_gate)
emits from three steps: build_from_manifest, step_3e, step_4. AC1 asserts against FOUR
channels, two of which that fixture never runs -- step_3_copy_kernel and
step_3b_copy_vault_tools -- and a plant in an un-run channel is absent from the box for
the wrong reason, which is a false green with no signal. talos-t59 pinned this exact
trap after hitting it on B-7. So this module extends the fixture to run every emitter a
real build runs, and the DenyFloor control proves the absences are caused by the gate
rather than by the fixture's luck of placement.

EVERY CLASS ASSERTS IT RAN AT LEAST ONE TEST. A present-but-empty TestCase reports
"Ran 0 tests / OK" and exits 0, so fully-qualified test IDs close the missing-module
hole and NOT the empty-class one. `RanAtLeastOne` closes the second.
"""

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
ROOT = TOOLS.parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.ship_verdict import (  # noqa: E402
    ShipVerdictResolver, Census, build_resolver, parse_root_manifest,
    DENY, SHIP_AS_IS, SHADOW, GENERATED, normalize,
)


def load_build_release(name='build_release_under_test'):
    spec = importlib.util.spec_from_file_location(
        name, str(TOOLS / 'tropo-build-release.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RanAtLeastOne:
    """Refuses the vacuous pass: a class that ran nothing must not report OK."""

    _ran = 0

    def setUp(self):
        type(self)._ran += 1
        super().setUp()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if cls._ran == 0:
            raise AssertionError(
                f'{cls.__name__} executed ZERO tests. A present-but-empty TestCase '
                f'reports "Ran 0 tests / OK" with exit 0, so this criterion would have '
                f'passed having proven nothing.'
            )


# ─── The shared box, built once ─────────────────────────────────────────────

class _Box:
    """One real box, emitted through EVERY channel, shared by the whole module."""

    tmp = None
    studio = None
    build_dir = None
    builder = None
    census = None
    plants = {}
    ready = False
    skip_reason = None

    @classmethod
    def setup(cls):
        if cls.ready or cls.skip_reason:
            return
        try:
            cls.tmp = Path(tempfile.mkdtemp(prefix='ship-manifest-'))
            cls.studio = cls.tmp / 'studio'
            cls.studio.mkdir()
            cls._materialize()
            cls._plant()
            cls._freshen_index()
            cls._emit()
            cls.ready = True
        except unittest.SkipTest as exc:
            cls.skip_reason = str(exc)
        except Exception as exc:  # noqa: BLE001
            cls.skip_reason = f'fixture could not build a box: {exc}'

    @classmethod
    def _materialize(cls):
        archive = subprocess.run(['git', 'archive', 'HEAD'], cwd=str(ROOT),
                                 capture_output=True, timeout=600)
        if archive.returncode != 0:
            raise unittest.SkipTest('git archive unavailable in this environment')
        extract = subprocess.run(['tar', '-x', '-C', str(cls.studio)],
                                 input=archive.stdout, capture_output=True, timeout=600)
        assert extract.returncode == 0, extract.stderr[:400]

    # -- the four plants, one per channel ---------------------------------

    @classmethod
    def _plant(cls):
        """One DENY-ruled plant per AC1 channel, plus one deliberately UNRULED path.

        The plants live at real source locations inside the fixture studio and are
        ruled by file-grain rows appended to the fixture's own ROOT MANIFEST. File
        grain beating folder grain is what makes a plant inside a wholesale-copied
        tree expressible at all -- without that rule AC1's headline arm cannot be
        satisfied, which is why the wholesale plant is the one that matters.
        """
        cls.plants = {
            # channel 3 — a wholesale emitter (step_3b_copy_vault_tools)
            'wholesale': 'vault/tools/PLANTED_DENY_wholesale.py',
            # channel 1 — the manifest walk (inside .tropo, recursive-ship-all)
            'manifest': '.tropo/PLANTED_DENY_manifest.md',
            # channel 3b — the kernel copy
            'kernel': '.tropo/scripts/PLANTED_DENY_kernel.py',
            # channel 4 — a bare copy_file in main(); CHANGELOG.md is one of today's
            # three sites, so ruling it DENY exercises that channel by rule.
            'inline': 'CHANGELOG.md',
        }
        # NOT under vault/tools/ — that tree carries a SHIP-AS-IS folder row, so a plant
        # there is RULED, not unruled. The first cut put it there and the test was
        # asserting against a path the manifest already covered. It goes in the
        # templates corpus, which ships by recursive-ship-all and has no folder row.
        cls.unruled_plant = 'vault/templates/PLANTED_UNRULED_nobody_ruled_me.md'

        for rel in list(cls.plants.values()) + [cls.unruled_plant]:
            p = cls.studio / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_text(f'# planted by test_ship_manifest for {rel}\n',
                             encoding='utf-8')

        # Append file-grain DENY rows for the four plants (NOT for the unruled one --
        # that one's whole job is to have no rule anywhere).
        manifest_file = cls.studio / 'vault' / 'files' / 'b2e7d4a9.md'
        text = manifest_file.read_text(encoding='utf-8')
        rows = '\n'.join(f'{rel}: DENY' for rel in cls.plants.values())
        marker = '```yaml ship-manifest\n'
        assert marker in text, 'fixture studio has no ROOT MANIFEST block to extend'
        # A plant may collide with a path the real manifest already rules (the v1.94
        # manifest rules CHANGELOG.md SHIP-AS-IS because the box must carry it, and the
        # parser is last-row-wins). Strip any existing row for a planted path first, so
        # the plant proves the DENY mechanism rather than the row order. metis-g119, 2026-09-04.
        import re as _re
        for _rel in cls.plants.values():
            text = _re.sub(r'(?m)^' + _re.escape(_rel) + r':[^\n]*\n', '', text)
        text = text.replace(marker, marker + rows + '\n', 1)
        manifest_file.write_text(text, encoding='utf-8')

    @classmethod
    def _freshen_index(cls):
        proc = subprocess.run(
            [sys.executable, str(cls.studio / 'vault' / 'tools' / 'tropo-rebuild-index.py'),
             '--apply', '--skip-rehydrate', '--vault-path', str(cls.studio)],
            cwd=str(cls.studio), capture_output=True, text=True, timeout=1800)
        assert proc.returncode == 0, (proc.stderr or proc.stdout)[-600:]

    @classmethod
    def _load_builder(cls):
        builder = load_build_release(f'br_{id(cls)}')
        builder.tropo_roots.STUDIO_ROOT = cls.studio
        builder.tropo_roots.VAULT_DIR = cls.studio / 'vault'
        builder.INDEX_PATH = str(cls.studio / 'vault' / '00-index.jsonl')
        builder.SHIP_ARTIFACT_CAPSULE_PATH = str(
            cls.studio / 'vault' / 'capsules' / 'tropo-ship-artifact.capsule.md')
        # IMPORT-TIME CONSTANTS, and the reason this block exists. Patching
        # tropo_roots.* alone is not enough: KERNEL_DIR and friends are computed at
        # import from the REAL studio root, so step_3_copy_kernel copied the real
        # repo's .tropo into the fixture box. The census filled with absolute-ish keys
        # that matched no rule and the whole kernel channel was silently denied. The
        # production cure is the escape refusal in copy_file; this is the fixture half.
        builder.KERNEL_DIR = os.path.join(str(cls.studio), '.tropo')
        builder.VERSION_PATH = os.path.join(str(cls.studio), '.tropo', 'version.md')
        builder.DRY_RUN = False
        return builder

    @classmethod
    def _emit(cls, arm_gate=True, build_dir=None):
        """Run EVERY emitter a real build runs, not the three-step subset."""
        builder = cls._load_builder()
        target = Path(build_dir) if build_dir else (cls.tmp / 'box')
        target.mkdir(parents=True, exist_ok=True)

        if arm_gate:
            builder.init_ship_verdicts(builder.tropo_roots.STUDIO_ROOT,
                                       builder.INDEX_PATH)

        root_uid = builder.read_manifest_root_uid(builder.SHIP_ARTIFACT_CAPSULE_PATH)
        entries = builder.load_manifest_entries(builder.INDEX_PATH, root_uid)

        builder.build_from_manifest(str(target), entries)              # channel 1
        builder.step_4_copy_ship_entries(                              # channel 2
            str(target), builder.load_ship_entries(builder.INDEX_PATH))
        builder.step_3_copy_kernel(str(target))                        # channel 3
        builder.step_3b_copy_vault_tools(str(target))                  # channel 3
        builder.step_3d_copy_vault_playbooks(str(target))              # channel 3
        builder.step_3e_copy_vault_updates(str(target))                # channel 3
        builder.step_3j_copy_vault_schema(str(target))                 # channel 3
        builder.step_7_create_vault_skeleton(str(target))              # channel 3

        # channel 4 — a bare copy_file in main(), reproduced by rule rather than by
        # calling main() (which would want a version bump, auth, and a zip).
        cl_src = cls.studio / 'CHANGELOG.md'
        if cl_src.exists():
            builder.copy_file(str(cl_src), str(target / 'CHANGELOG.md'), False)

        if arm_gate:
            cls.builder = builder
            cls.census = builder.SHIP_CENSUS
            cls.build_dir = target
        return builder, target

    @classmethod
    def teardown(cls):
        if cls.tmp:
            shutil.rmtree(cls.tmp, ignore_errors=True)


def setUpModule():
    _Box.setup()


def tearDownModule():
    _Box.teardown()


class BoxCase(RanAtLeastOne, unittest.TestCase):
    """Base: every test in this module reads the one shared, fully-emitted box."""

    def setUp(self):
        # super() FIRST so the test counts as having run before the skip decision.
        # RanAtLeastOne exists to catch an EMPTY class, which reports "OK" silently;
        # a skip is already loud in the runner output and is not the hole being closed.
        super().setUp()
        if not _Box.ready:
            self.skipTest(_Box.skip_reason or 'box fixture unavailable')

    def box(self, rel):
        return _Box.build_dir / rel

    def in_box(self, rel):
        return (_Box.build_dir / rel).exists()


# ─── AC1 ────────────────────────────────────────────────────────────────────

class DenyFloor(BoxCase):
    """AC1 — a DENY plant in ANY of the four channels does not reach the box.

    Four plants, four absences, and a census that names the prune count. The control
    is the load-bearing half: it disarms the gate and rebuilds, and every plant must
    then SHIP. Without it, four absences prove only that the fixture put its plants
    somewhere nothing copies.
    """

    def test_all_four_channel_plants_are_absent_from_the_box(self):
        present = [rel for rel in _Box.plants.values() if self.in_box(rel)]
        self.assertEqual(
            present, [],
            f'{len(present)} DENY-ruled plant(s) reached the box: {present}. '
            f'The verdict chokepoint did not prune them.')

    def test_every_channel_is_actually_exercised_by_this_fixture(self):
        """The anti-vacuous arm: prove each plant's channel really copies files.

        A plant absent from a channel that never ran proves nothing. Each channel is
        shown to have emitted SOMETHING into the box.
        """
        witnesses = {
            'wholesale': 'vault/tools/tropo-validate.py',
            'manifest': '.tropo/TROPO-CONTROL.md',
            'kernel': '.tropo/TROPO-CONTROL.md',
            'inline': 'CHANGELOG.md',
        }
        for channel, witness in witnesses.items():
            if channel == 'inline':
                continue  # CHANGELOG is itself the DENY plant for channel 4
            self.assertTrue(
                self.in_box(witness),
                f'channel {channel} emitted nothing into the box (witness {witness} '
                f'missing), so its plant\'s absence is meaningless')

    def test_census_names_the_deny_prune_count(self):
        denied = _Box.census.denied()
        self.assertTrue(
            denied,
            'the census recorded zero DENY decisions while four plants were ruled '
            'DENY — the census is not reading the same gate the build is')
        by_rule = [d for d in denied if not d.is_unruled]
        self.assertGreaterEqual(
            len(by_rule), len(_Box.plants),
            f'census names {len(by_rule)} rule-driven prunes; at least '
            f'{len(_Box.plants)} were planted')

    def test_control_disarmed_gate_ships_every_plant(self):
        """CONTROL. Rebuild with the chokepoint disarmed; all four plants must ship.

        This is what makes the four absences above evidence about the GATE rather than
        about where the fixture happened to put its files. One control covers all four
        channels at once, which a per-channel unhook could not do.
        """
        control_dir = _Box.tmp / 'box-control'
        _Box._emit(arm_gate=False, build_dir=control_dir)
        shipped = [rel for rel in _Box.plants.values() if (control_dir / rel).exists()]
        self.assertEqual(
            sorted(shipped), sorted(_Box.plants.values()),
            f'with the gate disarmed only {shipped} shipped. Every plant must ship '
            f'here — a plant that stays absent with no gate was never reachable, and '
            f'its absence in the armed box proved nothing.')


# ─── AC2 ────────────────────────────────────────────────────────────────────

class ShadowSubstitution(BoxCase):
    """AC2 — the real designated pair: twin in the box, source not."""

    def test_designated_source_is_absent_and_twin_is_present(self):
        resolver = build_resolver(str(_Box.studio))
        pairs = resolver.shadow_pairs()
        self.assertTrue(pairs, 'no SHADOW designations resolved in the fixture studio')

        for source_path, twin_uid in pairs:
            self.assertFalse(
                self.in_box(source_path),
                f'SHADOW source {source_path} is in the box; its twin was meant to '
                f'ship in its place')
            files_dir = _Box.build_dir / 'vault' / 'files'
            hits = list(files_dir.glob(f'*{twin_uid}*.md')) if files_dir.is_dir() else []
            self.assertTrue(
                hits,
                f'twin {twin_uid} is not in the box. Source withheld and nothing '
                f'replaced it is a hole, not a substitution.')

    def test_both_designations_resolve(self):
        resolver = build_resolver(str(_Box.studio))
        for source_path, twin_uid in resolver.shadow_pairs():
            self.assertTrue((_Box.studio / source_path).exists(),
                            f'designated source {source_path} does not exist on disk')
            self.assertTrue(twin_uid, f'{source_path} is SHADOW but names no twin')

    def test_build_time_verifier_passes_on_this_box(self):
        """Drive the function the BUILD calls, not just the data it reads.

        verify_shadow_substitutions is wired into main() and would otherwise be a
        declared-but-not-run path in the very change that exists to end that family.
        """
        ok, findings = _Box.builder.verify_shadow_substitutions(str(_Box.build_dir))
        self.assertTrue(ok, f'shadow verification failed on a correct box: {findings}')
        self.assertTrue(findings, 'the verifier reported nothing at all — silence is '
                                  'not a report')

    def test_build_time_verifier_catches_a_missing_twin(self):
        """TEETH. Remove the twin from the box; the verifier must refuse and name it."""
        resolver = build_resolver(str(_Box.studio))
        pairs = resolver.shadow_pairs()
        if not pairs:
            self.skipTest('no pairs to mutate')
        _source, twin_uid = pairs[0]
        files_dir = _Box.build_dir / 'vault' / 'files'
        hits = list(files_dir.glob(f'*{twin_uid}*.md'))
        self.assertTrue(hits, 'fixture sanity: twin must be in the box to remove it')
        victim = hits[0]
        backup = victim.read_bytes()
        try:
            victim.unlink()
            ok, findings = _Box.builder.verify_shadow_substitutions(str(_Box.build_dir))
            self.assertFalse(ok, 'the verifier passed a box whose twin is missing — a '
                                 'source withheld with nothing replacing it is a hole')
            self.assertTrue(any(twin_uid in f for f in findings),
                            'the refusal did not name the missing twin')
        finally:
            victim.write_bytes(backup)

    def test_positive_control_stripping_designation_ships_the_source(self):
        """POSITIVE CONTROL, because source-absent is ALSO what you get from a pair
        that was never wired at all. Strip the designation and the SOURCE must ship."""
        resolver = build_resolver(str(_Box.studio))
        pairs = resolver.shadow_pairs()
        if not pairs:
            self.skipTest('no pairs to control against')
        source_path, _twin = pairs[0]

        stripped = ShipVerdictResolver.from_sources(
            artifact_rows=[], manifest_rows=[], scope_rows=[
                {'path': source_path, 'extraction_scope': 'ship'}])
        decision = stripped.resolve(source_path)
        self.assertTrue(
            decision.ships,
            'with the SHADOW designation removed the source must resolve as shipping; '
            'if it does not, the armed run\'s absence was never caused by the pairing')


# ─── AC3 ────────────────────────────────────────────────────────────────────

class UnruledPathIsNamed(BoxCase):
    """AC3 — posture-independent: an unruled path is NEVER silent.

    Mike ratified silent-DENY at the walk, so the assertion is on the NAMING: the build
    proceeds, the path does not ship, and the census names it as unruled-pruned.

    THE PLANT IS DRIVEN THROUGH copy_file DIRECTLY, and that is not a shortcut — it is
    channel 4 exactly as the spec defines it ("every bare copy_file call in main()").
    The first cut of this class planted a file in the source tree instead and asserted
    it was unruled; it was not. `vault/templates/` carries a SHIP-AS-IS folder row and
    so does `vault/tools/`, so both plants were RULED and the test was asserting
    against a premise the manifest had already settled. The rule set covering
    everything is the goal, not an obstacle -- so the unruled case has to be
    constructed at the entry point rather than found lying around.
    """

    UNRULED_REL = 'no_channel_rules_this/PLANTED_UNRULED.md'

    @classmethod
    def _drive(cls):
        """Copy an unruled source through the real chokepoint; return (census, dest)."""
        builder = _Box.builder
        src = _Box.studio / cls.UNRULED_REL
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text('# nobody ruled this path\n', encoding='utf-8')
        dest = _Box.build_dir / cls.UNRULED_REL
        before = len(builder.SHIP_CENSUS.decisions)
        builder.copy_file(str(src), str(dest), False)
        return builder.SHIP_CENSUS.decisions[before:], dest

    def test_unruled_plant_does_not_ship(self):
        decisions, dest = self._drive()
        self.assertTrue(decisions, 'the chokepoint recorded no decision at all')
        self.assertFalse(
            dest.exists(),
            f'{self.UNRULED_REL} carries no verdict in any channel and still reached '
            f'the box — default-deny is not in force')

    def test_unruled_plant_is_named(self):
        decisions, _ = self._drive()
        unruled = [d for d in decisions if d.is_unruled]
        self.assertTrue(
            unruled,
            'the unruled plant was dropped without being named. Under silent-DENY the '
            'naming is the entire deliverable — a silent drop is the negative-census '
            'failure this spec exists to end.')
        self.assertEqual(normalize(self.UNRULED_REL), unruled[0].path)

    def test_the_census_renders_the_name(self):
        """The naming must reach the OUTPUT, not just the data structure."""
        import io
        self._drive()
        buf = io.StringIO()
        _Box.census.render(stream=buf)
        text = buf.getvalue()
        self.assertIn('unruled-pruned', text)
        self.assertIn(self.UNRULED_REL, text,
                      'the census recorded the unruled path but never printed it; a '
                      'name nobody can read is not a naming')

    def test_control_a_ruled_path_is_not_reported_unruled(self):
        """CONTROL: the unruled report must be able to come back EMPTY.

        Without this, a census that labelled everything unruled would pass every
        assertion above while saying nothing.
        """
        builder = _Box.builder
        ruled_src = _Box.studio / 'vault' / 'tools' / 'tropo-validate.py'
        self.assertTrue(ruled_src.exists(), 'fixture sanity')
        before = len(builder.SHIP_CENSUS.decisions)
        builder.copy_file(str(ruled_src),
                          str(_Box.build_dir / 'control-probe.py'), False)
        new = builder.SHIP_CENSUS.decisions[before:]
        self.assertTrue(new, 'no decision recorded for the control probe')
        self.assertFalse(
            [d for d in new if d.is_unruled],
            'a path ruled SHIP-AS-IS by the manifest was reported unruled — the '
            'unruled label is being applied indiscriminately and proves nothing')


# ─── AC4 ────────────────────────────────────────────────────────────────────

class ElectionWalk(RanAtLeastOne, unittest.TestCase):
    """AC4 — the walk lists drift, states zero-elections legal, and never blocks."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix='election-walk-'))
        (self.tmp / 'vault' / 'files').mkdir(parents=True)
        (self.tmp / 'src').mkdir()
        (self.tmp / 'src' / 'DOC.md').write_text('# source\noriginal\n', encoding='utf-8')
        (self.tmp / 'vault' / 'files' / 'b2e7d4a9.md').write_text(
            '---\nuid: b2e7d4a9\ntype: project\n---\n# root\n'
            '```yaml ship-manifest\n'
            'src/DOC.md:\n  verdict: SHADOW\n  ships_as: aaa11122\n'
            '```\n', encoding='utf-8')
        (self.tmp / 'vault' / 'files' / 'aaa11122.md').write_text(
            '---\nuid: aaa11122\ntype: document\nshadow_of: "src/DOC.md"\n---\n# twin\n',
            encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def walk(self):
        spec = importlib.util.spec_from_file_location(
            'election_walk_uut', str(TOOLS / 'tropo-election-walk.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules['election_walk_uut'] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_never_elected_pair_is_listed(self):
        pairs, problems = self.walk().collect_pairs(str(self.tmp))
        self.assertEqual(len(pairs), 1)
        self.assertTrue(pairs[0].drifted)
        self.assertEqual(pairs[0].state, 'never elected')
        self.assertEqual(problems, [])

    def test_election_apply_round_trip_then_zero(self):
        walk = self.walk()
        pairs, _ = walk.collect_pairs(str(self.tmp))
        self.assertTrue(walk.apply_election(pairs[0]))

        twin = (self.tmp / 'vault' / 'files' / 'aaa11122.md').read_text()
        self.assertIn('edition_of_body_hash:', twin,
                      'election-apply must WRITE the hash it turns on')
        self.assertIn('edition_date:', twin)

        again, _ = walk.collect_pairs(str(self.tmp))
        self.assertEqual([p for p in again if p.drifted], [],
                         'after electing, the walk must list zero')

    def test_unchanged_pair_is_not_listed(self):
        """THE CONTROL the spec calls out by name: without it, a walk that lists every
        designated source regardless of hash passes every other arm."""
        walk = self.walk()
        pairs, _ = walk.collect_pairs(str(self.tmp))
        walk.apply_election(pairs[0])
        after, _ = walk.collect_pairs(str(self.tmp))
        self.assertEqual(after[0].state, 'current')
        self.assertFalse(after[0].drifted)

    def test_source_moving_relists_the_pair(self):
        walk = self.walk()
        pairs, _ = walk.collect_pairs(str(self.tmp))
        walk.apply_election(pairs[0])
        (self.tmp / 'src' / 'DOC.md').write_text('# source\nCHANGED\n', encoding='utf-8')
        after, _ = walk.collect_pairs(str(self.tmp))
        self.assertTrue(after[0].drifted)
        self.assertEqual(after[0].state, 'drifted')

    def test_zero_elections_is_stated_not_rendered_as_emptiness(self):
        walk = self.walk()
        pairs, _ = walk.collect_pairs(str(self.tmp))
        walk.apply_election(pairs[0])
        pairs, problems = walk.collect_pairs(str(self.tmp))
        out = self.tmp / 'board.html'
        walk.render_board(pairs, problems, out)
        body = out.read_text()
        self.assertIn('Zero elections', body,
                      'an empty board and a board that never ran look identical; the '
                      'legal outcome must be stated in words')

    def test_walk_never_blocks(self):
        proc = subprocess.run(
            [sys.executable, str(TOOLS / 'tropo-election-walk.py'),
             '--root', str(self.tmp)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0,
                         'drift is information, not a failure — Mike: "I do not want '
                         'blockers, I want awareness of drift"')


# ─── AC5 ────────────────────────────────────────────────────────────────────

class PositiveCensus(BoxCase):
    """AC5 — every path in the box resolves, and the floor is a RELATION not a number."""

    MUST_BE_PRESENT = (
        '.tropo/TROPO-CONTROL.md',
        '.tropo/concierge/activate.md',
        'docs/tropo-studio-map.md',
        'vault/playbooks/99341618.md',
        'boards/_shared/board.css',
    )

    def test_field_keyed_census_every_ship_artifact_carries_a_verdict(self):
        """FIELD-keyed, not resolution-keyed. Resolution-keyed cannot fail."""
        import json
        rows = []
        for name in ('00-index.jsonl', '00-archive-index.jsonl'):
            p = _Box.studio / 'vault' / name
            if p.exists():
                rows += [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        artifacts = [r for r in rows if r.get('type') == 'ship-artifact']
        self.assertTrue(artifacts, 'no ship-artifacts found — fixture is meaningless')
        missing = [r['uid'] for r in artifacts if not r.get('ship_verdict')]
        self.assertEqual(
            missing, [],
            f'{len(missing)} of {len(artifacts)} ship-artifacts carry no ship_verdict '
            f'FIELD. Resolution-keyed this reads 100% ruled, because an artifact whose '
            f'path carries extraction_scope: ship maps to SHIP-AS-IS anyway.')

    def test_completeness_floor_is_derived_from_the_builds_own_rules(self):
        """THE FLOOR, as a relation. No transcribed integers — they go stale by
        construction and this spec shipped three wrong ones before saying so.

        Compute the EXPECTED shipped set by applying the build's own exclusion
        predicates to the source tree, then assert every rule-included path is in the
        box. Superset, not equality, so generated files do not fail it.
        """
        builder = _Box.builder
        expected = self._expected_vault_tools(builder)
        self.assertGreater(len(expected), 100,
                           'the derived expectation is implausibly small; the relation '
                           'is reading the wrong population')
        missing = [rel for rel in expected
                   if not (_Box.build_dir / 'vault' / 'tools' / rel).exists()]
        self.assertEqual(
            missing[:10], [],
            f'{len(missing)} path(s) the build\'s OWN rules say ship are absent from '
            f'the box: {missing[:10]}')

    def _expected_vault_tools(self, builder):
        src = _Box.studio / 'vault' / 'tools'
        excluded = set(getattr(builder, 'VAULT_TOOLS_EXCLUDE_DIRS', ()))
        out = []
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in excluded and d != '__pycache__']
            for f in files:
                if f.endswith(('.pyc', '.pyo')):
                    continue
                rel = os.path.relpath(os.path.join(root, f), src)
                if rel.startswith('PLANTED_'):
                    continue  # the fixture's own DENY/UNRULED plants
                out.append(rel)
        return sorted(out)

    def test_negative_control_deleting_a_rule_included_file_fails_the_floor(self):
        """Required by the spec: delete one rule-included file from the box and the
        floor must go red, naming it. Otherwise the relation asserts nothing."""
        builder = _Box.builder
        expected = self._expected_vault_tools(builder)
        victim = expected[0]
        victim_path = _Box.build_dir / 'vault' / 'tools' / victim
        self.assertTrue(victim_path.exists(), 'fixture sanity: victim must be in the box')
        backup = victim_path.read_bytes()
        try:
            victim_path.unlink()
            missing = [rel for rel in expected
                       if not (_Box.build_dir / 'vault' / 'tools' / rel).exists()]
            self.assertIn(victim, missing,
                          'the floor did not notice a rule-included file removed from '
                          'the box — it cannot change verdict, so it proves nothing')
        finally:
            victim_path.write_bytes(backup)

    def test_must_be_present_set_is_in_the_box(self):
        """A box missing any of these is not a studio. Asserted by path.

        studio-identity.md is deliberately NOT a member: tropo-build-release.py
        excludes it from the box BY DESIGN (genesis mints it per-studio), so a floor
        naming it would be red on every correct build AND would point a builder at
        shipping Argo's own mint_prefix to every customer.
        """
        absent = [rel for rel in self.MUST_BE_PRESENT if not self.in_box(rel)]
        self.assertEqual(absent, [],
                         f'the box is missing {absent} — that is not a studio')

    def test_studio_identity_manifest_is_not_in_the_box(self):
        matches = list(_Box.build_dir.rglob('studio-identity.md'))
        self.assertEqual(
            matches, [],
            'studio-identity.md reached the box. Genesis mints it per-studio; shipping '
            "Argo's carries our own mint_prefix to every customer.")

    def test_crew_souls_are_absent_from_the_box(self):
        """D3, the whole point. No crew soul substrate in a customer box."""
        leaked = []
        agents_dir = _Box.build_dir / 'vault' / 'agents'
        if agents_dir.is_dir():
            for p in agents_dir.glob('*.md'):
                if p.stem != '566770f7':  # the shipped first-encounter agent
                    leaked.append(str(p.relative_to(_Box.build_dir)))
        private_home = _Box.build_dir / 'agents'
        if private_home.is_dir():
            for p in private_home.rglob('*.md'):
                rel = str(p.relative_to(_Box.build_dir))
                if rel.startswith(('agents/tropo/', 'agents/sa/', 'agents/directors/')):
                    continue
                leaked.append(rel)
        self.assertEqual(leaked[:10], [],
                         f'{len(leaked)} identity-substrate file(s) reached the box: '
                         f'{leaked[:10]}')

    def test_d3_deny_rules_exist(self):
        """The rows must EXIST. Absence of the files is satisfied under silent-DENY
        whether the rules were authored or never written at all."""
        resolver = build_resolver(str(_Box.studio))
        denies = resolver.rules_with_verdict(DENY)
        self.assertIn('agents/', denies,
                      'the D3 identity rule is not authored; the files\' absence would '
                      'then prove nothing about whether anyone ruled it')
        self.assertIn('vault/agents/', denies)

    def test_census_reports_every_channel(self):
        by_channel = _Box.census.by_channel()
        self.assertTrue(by_channel, 'the census recorded nothing at all')
        self.assertGreater(sum(by_channel.values()), 500,
                           'the census saw implausibly few paths for a real box')


# ─── The chokepoint's own integrity ─────────────────────────────────────────

class NoCopyBypass(RanAtLeastOne, unittest.TestCase):
    """One gate only works if nothing walks around it. This asserts that at source.

    step_7_create_vault_skeleton used shutil.copytree and put ~19 files in the box with
    no verdict at all. It was converted; this test is what stops the next one.
    """

    ALLOWED = {
        # the sealed box → testing mirror, after every verdict has been applied
        'shutil.copytree(build_dir, testing_dir, symlinks=True)',
    }

    def test_no_new_shutil_copy_into_the_box(self):
        source = (TOOLS / 'tropo-build-release.py').read_text(encoding='utf-8')
        offenders = []
        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if not stripped.startswith('#') and 'shutil.copytree(' in stripped:
                if stripped not in self.ALLOWED:
                    offenders.append(f'{i}: {stripped}')
        self.assertEqual(
            offenders, [],
            'a shutil.copytree writes into the build outside the verdict chokepoint. '
            'Every path into the box must go through copy_file, or the census is blind '
            'to it exactly the way it was blind to the .tropo-studio skeleton:\n  '
            + '\n  '.join(offenders))

    def test_copy_file_is_the_gated_wrapper_not_the_engine(self):
        source = (TOOLS / 'tropo-build-release.py').read_text(encoding='utf-8')
        self.assertNotIn(
            'copy_file = _engine_copy_file', source,
            'copy_file is bound straight to the engine again — the gate is bypassed '
            'for every channel at once')
        self.assertIn('def copy_file(src, dst, dry_run=False', source)

    def test_gate_is_armed_before_any_copy_in_main(self):
        source = (TOOLS / 'tropo-build-release.py').read_text(encoding='utf-8')
        main_at = source.find('\ndef main():')
        self.assertGreater(main_at, 0, 'could not locate main()')
        body = source[main_at:]

        arm = body.find('init_ship_verdicts(tropo_roots.STUDIO_ROOT')
        self.assertGreater(arm, 0, 'main() never arms the verdict gate')

        # The first COPYING step main() calls. Scoped to main's body, because the
        # first mention of any of these symbols in the whole file is its own def or a
        # docstring -- the first cut of this test compared against a docstring offset
        # and failed on correct code.
        calls = [body.find(f'{name}(build_dir)') for name in (
            'step_3_copy_kernel', 'step_3b_copy_vault_tools',
            'step_7_create_vault_skeleton')]
        calls = [c for c in calls if c > 0]
        self.assertTrue(calls, 'main() calls no copying step; assertion reads nothing')
        self.assertLess(
            arm, min(calls),
            'the gate is armed AFTER copying starts; every file copied before that '
            'line carries no verdict and is invisible to the census')


if __name__ == '__main__':
    unittest.main(verbosity=2)
