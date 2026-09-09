#!/usr/bin/env python3
"""Locked promotion ACs: real command heads, scratch state, stubbed outward boundaries."""
import ast
import contextlib
import hashlib
import inspect
import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

# The box collects shipped tests under the package form (`python3 -m unittest
# vault.tools.tests.<module>`), where this file's own directory is not on sys.path
# and the bare sibling import below fails to collect. The build's F1 gate refused
# v1.96 on exactly that (2026-09-09 03:26Z). Running the file directly worked all
# along, which is why nobody saw it. Put our own directory first, then import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_fire_selects_by_recency_not_identity as selection
pub, TOOLS = selection.pub, selection.TOOLS
SAGA = pub._saga()
RUNTIME = pub._load_pipeline_runtime()
ORCHESTRATOR = pub._load_vault_lib_by_path(
    "tropo_publish_release_orchestrator", TOOLS / "tropo-release.py")


def selection_violations(source):
    """In-module reachable-function tripwire, including nested verifier closures.

    This does not claim to analyze imported modules or subprocess programs.
    Directory iteration for receipts/assets is not record/run selection.
    """
    tree = ast.parse(source)
    functions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    todo = ['cmd_promote', 'cmd_fire', 'cmd_preflight', 'cmd_defer']
    seen, violations = set(), []
    while todo:
        name = todo.pop()
        if name in seen or name not in functions:
            continue
        seen.add(name)
        function = functions[name]
        nodes = list(ast.walk(function))
        # Carry aliases of the two selection roots through assignments.
        aliases = {'RELEASES_DIR'}
        for _ in range(len(nodes)):
            before = set(aliases)
            for node in nodes:
                if isinstance(node, ast.Assign):
                    value = ast.unparse(node.value)
                    if 'pipeline-runs' in value or any(isinstance(x, ast.Name) and x.id in aliases or isinstance(x, ast.Attribute) and x.attr == 'RELEASES_DIR' for x in ast.walk(node.value)):
                        aliases.update(x.id for target in node.targets for x in ast.walk(target) if isinstance(x, ast.Name))
            if aliases == before:
                break
        for node in nodes:
            if isinstance(node, ast.Attribute) and node.attr in {'st_mtime', 'getmtime', 'getctime'}:
                violations.append((name, node.attr))
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    todo.append(node.func.id)
                operation = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
                if operation in {'sorted', 'glob', 'iterdir', 'max'}:
                    expression = ast.unparse(node)
                    if 'pipeline-runs' in expression or any(isinstance(x, ast.Name) and x.id in aliases or isinstance(x, ast.Attribute) and x.attr == 'RELEASES_DIR' for x in ast.walk(node)):
                        violations.append((name, operation))
    return violations


def runbook_violations(source):
    tree = ast.parse(source)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    # Walking Constant nodes includes the literal portions of JoinedStr f-strings.
    literals = [n.value for n in ast.walk(main) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return [v for v in literals if 'echo "' in v or ('PUBLISH' in v and '5.' in v) or 'tropo-publish-release.py stage' in v or 'tropo-publish-release.py --fire' in v]


def assert_candidate(test, source):
    import yaml
    document = yaml.safe_load(source)
    steps = [step for job in document['jobs'].values() for step in job['steps']]
    upload = next(s for s in steps if str(s.get('uses', '')).startswith('actions/upload-artifact'))
    test.assertEqual(upload['with']['path'], '${{ runner.temp }}/candidate')
    test.assertEqual(upload['with']['name'], 'candidate-${{ github.sha }}')
    test.assertEqual(upload['if'], 'always()')
    test.assertEqual(upload['with']['retention-days'], 14)
    reports = [s for s in steps if '--phase candidate' in s.get('run', '')]
    test.assertEqual(len(reports), 1)
    test.assertTrue(reports[0]['continue-on-error'])
    for literal in ['--extracted-tree', '${RUNNER_TEMP}/candidate/box', 'GITHUB_STEP_SUMMARY', 'Spine A item 1']:
        test.assertIn(literal, reports[0]['run'])
    test.assertNotIn('--version-string', reports[0]['run'])
    test.assertNotIn('NOT YET IN THIS LANE', source)
    test.assertRegex(source, r'2026-09-\d\d')


class Promotion(unittest.TestCase):
    def setUp(self):
        selection.FireSelection.setUp(self)
        self.stack.enter_context(patch.object(pub, "_saga", return_value=SAGA))
        self.run = self.root / 'vault/pipeline-runs/named'
        self.run.mkdir(parents=True)
        self.run_identity = {'saga_id': SAGA.saga_id_for('cccccccccccc'),
                             'pipeline_run_uid': 'cccccccccccc'}
        RUNTIME.append_event(self.run, RUNTIME.make_event(
            'tropo.release.orchestrator_invoked', 'fixture',
            data=self.run_identity, trace_id=self.args.activation_uid))
        self.runtime = Mock()
        self.runtime.read_events.side_effect = lambda folder: [json.loads(line) for line in (folder / 'run.jsonl').read_text().splitlines()] if (folder / 'run.jsonl').exists() else []
        self.stack.enter_context(patch.object(pub, '_load_pipeline_runtime', return_value=self.runtime))
        self.stack.enter_context(patch.object(pub, '_named_run_folder', return_value=self.run))
        self.receipts = self.stack.enter_context(patch.object(pub.release_receipt, 'load_release_receipts', return_value={}))
        self.zip = pub._state_path('9.8.7').parent / 'dist/tropo-os-v9.8.7.zip'
        self.zip.parent.mkdir()
        self.zip.write_bytes(b'frozen fixture zip bytes')
        self.ac7 = {'identity': SimpleNamespace(run_uid='cccccccccccc', activation_uid=self.args.activation_uid), 'package_sha256': hashlib.sha256(self.zip.read_bytes()).hexdigest()}
        journal = pub._fire_journal(self.args.version, self.args.activation_uid)
        for checkpoint in pub.FIRE_WIRED_CHECKPOINTS:
            journal.append(pub._saga().OBSERVED_EVENT, checkpoint)
        self.output = io.StringIO()
        self.stack.enter_context(contextlib.redirect_stderr(self.output))
        self.stack.enter_context(contextlib.redirect_stdout(self.output))

    def test_all_publication_arms_and_removal_controls(self):
        guard_source = inspect.getsource(pub._refuse_if_published)
        real_confirm = pub._confirm_tty
        for arm in ['journal', 'state', 'receipt']:
            with self.subTest(arm=arm):
                state = dict(self.good)
                rows, receipts = [], {}
                if arm == 'journal':
                    rows = [{'type': 'tropo.release.published', 'data': {'published_at': 'fixture-time'}}]
                    mutation = 'release_closure.event_type(row) == release_closure.PUBLISHED_EVENT'
                elif arm == 'state':
                    state['published_at'] = 'fixture-time'
                    mutation = 'state.get("published_at")'
                else:
                    receipts = {'d8e30a9858ac' + '0' * 52: {'version': '9.8.7', 'published_at': '2026-09-07T11:32:58Z'}}
                    mutation = 'receipt.get("version") == version'
                with patch.object(self.runtime, 'read_events', return_value=rows), patch.object(pub.release_receipt, 'load_release_receipts', return_value=receipts), patch.object(pub, '_confirm_tty', return_value=False) as confirm:
                    with self.assertRaises(pub.PublishError):
                        pub._refuse_if_published('9.8.7', state, self.run)
                    confirm.assert_called_once()
                    confirm.return_value = True
                    pub._refuse_if_published('9.8.7', state, self.run)
                    confirm.return_value = False
                    with patch.object(pub, '_confirm_tty', real_confirm), patch.object(pub.sys.stdin, 'isatty', return_value=False), self.assertRaises(pub.PublishError):
                        pub._refuse_if_published('9.8.7', state, self.run)
                    for text in ['force-pushed', 're-uploaded', 'regenerated', 'Cut a new version']:
                        self.assertIn(text, self.output.getvalue())
                    namespace = dict(pub.__dict__)
                    exec(compile(guard_source.replace(mutation, 'False', 1), '<removed-arm>', 'exec'), namespace)
                    confirm.reset_mock()
                    namespace['_refuse_if_published']('9.8.7', state, self.run)
                    with self.assertRaises(AssertionError):
                        confirm.assert_called_once()  # Removing this arm is demonstrably red.
        with patch.object(pub, '_confirm_tty') as confirm:
            pub._refuse_if_published('9.8.7', dict(self.good, published_at=''), self.run)
            confirm.assert_not_called()

    def test_publisher_journal_writer_is_detected(self):
        # Actual producer and journal I/O, confined to this disposable run.
        # Historical type-key envelopes remain covered by the independent arm.
        with patch.object(pub, '_load_pipeline_runtime', return_value=RUNTIME), patch.object(pub, '_run_journal_folder', return_value=self.run):
            pub._mirror_published_event_to_journal(self.ac7, {'receipt_sha256': 'd' * 64}, 'd' * 64)
            row, = [row for row in RUNTIME.read_events(self.run)
                    if pub.release_closure.event_type(row) == pub.release_closure.PUBLISHED_EVENT]
            self.assertEqual(row['event'], pub.release_closure.PUBLISHED_EVENT)
            self.assertEqual(row['actor'], pub.release_receipt.PUBLISHER_TOOL_UID)
            self.assertEqual(row['trace_id'], self.args.activation_uid)
            with patch.object(pub, '_confirm_tty', return_value=False) as confirm, self.assertRaises(pub.PublishError):
                pub._refuse_if_published('9.8.7', self.good, self.run)
            confirm.assert_called_once()

    def test_incomplete_saga_warns_and_resumes_without_extra_confirm(self):
        journal = pub._fire_journal('9.8.7', self.args.activation_uid)
        journal.path.write_text('')
        with patch.object(pub, '_confirm_tty') as confirm:
            pub._refuse_if_published('9.8.7', dict(self.good, published_at='fixture-time'), self.run)
            confirm.assert_not_called()
        self.assertIn('SAGA INCOMPLETE', self.output.getvalue())
        self.assertIn('--activation-uid aaaaaaaaaaaa', self.output.getvalue())

    def test_absent_and_unreadable_receipts_warn(self):
        for effect in [None, pub.release_receipt.ReleaseReceiptError('bad.json unreadable')]:
            self.receipts.side_effect = effect
            pub._refuse_if_published('9.8.7', self.good, self.run)
        self.assertIn('release-receipts', self.output.getvalue())
        self.assertIn('bad.json', self.output.getvalue())
        self.assertIn('carry the decision', self.output.getvalue())

    def test_published_guard_runs_before_preflight_for_fire_and_promote(self):
        pub._state_path('9.8.7').write_text(json.dumps(dict(self.good, published_at='fixture-time')))
        for command in [pub.cmd_fire, pub.cmd_promote]:
            with patch.object(pub.sys.stdin, 'isatty', return_value=False), patch.object(pub, 'run_fire_preflight') as preflight:
                with self.assertRaises(pub.PublishError):
                    command(self.args)
                preflight.assert_not_called()
        self.assertIn('not a TTY', self.output.getvalue())

    def test_changed_zip_guard_and_removal_control(self):
        with patch.object(pub, '_confirm_tty', return_value=False) as confirm:
            pub._confirm_shipping_digest('9.8.7', self.ac7)
            confirm.assert_not_called()
            self.zip.write_bytes(self.zip.read_bytes() + b'!')
            with self.assertRaises(pub.PublishError):
                pub._confirm_shipping_digest('9.8.7', self.ac7)
            confirm.assert_called_once()
        with patch.object(pub.sys.stdin, 'isatty', return_value=False), self.assertRaises(pub.PublishError):
            pub._confirm_shipping_digest('9.8.7', self.ac7)
        for digest in [self.ac7['package_sha256'], hashlib.sha256(self.zip.read_bytes()).hexdigest()]:
            self.assertIn(digest, self.output.getvalue())
        self.assertIn('Bytes nobody verified', self.output.getvalue())
        namespace = dict(pub.__dict__)
        source = inspect.getsource(pub._confirm_shipping_digest).replace('if actual != expected:', 'if False:')
        exec(compile(source, '<removed-hash-check>', 'exec'), namespace)
        with self.assertRaises(AssertionError):
            with self.assertRaises(pub.PublishError):
                namespace['_confirm_shipping_digest']('9.8.7', self.ac7)

    def test_fire_calls_zip_guard_before_ordinary_confirm_and_removal_is_red(self):
        self.zip.write_bytes(self.zip.read_bytes() + b'changed')
        source = inspect.getsource(pub.cmd_fire)
        with patch.object(pub, 'run_fire_preflight', return_value=0), patch.object(pub, 'require_ac7_receipt_set', return_value=dict(self.ac7)), patch.object(pub, '_release_entry_uid_for', return_value='release'), patch.object(pub, '_require_pinned_remote', return_value='https://example.invalid'), patch.object(pub, '_render_scorecard_so_far'), patch.object(pub, '_run_journal_folder', return_value=self.run), patch.object(pub, '_confirm_tty', return_value=False) as confirm:
            pub.cmd_fire(self.args)
            self.assertIn('Bytes nobody verified', confirm.call_args.args[0])
            # Compile against the currently stubbed globals; the removed call
            # reaches the ordinary confirm silently and the same assertion reds.
            namespace = dict(pub.__dict__)
            exec(compile(source.replace('        _confirm_shipping_digest(version, _ac7)\n', ''), '<removed-call>', 'exec'), namespace)
            confirm.reset_mock()
            namespace['cmd_fire'](self.args)
            with self.assertRaises(AssertionError):
                self.assertIn('Bytes nobody verified', confirm.call_args.args[0])

    def test_orchestrator_carries_run_state_identity_to_gate_and_fire(self):
        # _identity deliberately supplies only saga/run identity. The caller
        # must add the activation from real bootstrap state, not assume it exists.
        (self.run / 'run.state.json').write_text(json.dumps(
            {'activation_uid': self.args.activation_uid, 'run_status': 'active'}))
        self.assertNotIn('activation_uid', ORCHESTRATOR._identity(self.run))
        delegated = Mock(return_value=6)
        args = SimpleNamespace(run_dir=self.run, vault=self.root,
                               version=self.args.version, authorize=True)
        with patch.object(ORCHESTRATOR, 'fire_refusal', return_value=None), patch.object(ORCHESTRATOR, '_fire_sequence_gate', return_value=None) as sequence, patch.object(ORCHESTRATOR, '_rehearsal_gate', return_value=None), patch.object(ORCHESTRATOR, '_write_scorecard_so_far'), patch.object(ORCHESTRATOR, '_load_wired_publisher', return_value=SimpleNamespace(cmd_fire=delegated)), patch.object(ORCHESTRATOR, '_write_real_fire_scorecard') as writer:
            self.assertEqual(ORCHESTRATOR.cmd_fire(args), 6)
            sequence.assert_called_once_with(
                self.run, self.root,
                dict(self.run_identity, activation_uid=self.args.activation_uid),
                self.args.version)
            delegated.assert_called_once()
            fire_args = delegated.call_args.args[0]
            self.assertEqual(fire_args.activation_uid, self.args.activation_uid)
            self.assertEqual(fire_args.version, self.args.version)
            fire_args.scorecard_producer(fire_args.version)
            writer.assert_called_once_with(self.run_identity, self.run, self.root, self.args.version)

    def test_promote_cli_attaches_existing_named_scorecard_producer(self):
        argv = ['publisher', 'promote', '--version', self.args.version,
                '--activation-uid', self.args.activation_uid]
        with patch.object(sys, 'argv', argv), patch.object(pub, 'run_fire_preflight', return_value=0), patch.object(pub.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='fixture GO', stderr='')), patch.object(pub, 'cmd_fire', return_value=6) as fire, patch.object(ORCHESTRATOR, '_write_real_fire_scorecard') as writer:
            self.assertEqual(pub.main(), 6)
            fire.assert_called_once()
            args = fire.call_args.args[0]
            self.assertEqual(args.version, self.args.version)
            self.assertEqual(args.activation_uid, self.args.activation_uid)
            producer = getattr(args, 'scorecard_producer', None)
            self.assertTrue(callable(producer))
            writer.assert_not_called()  # Attachment does not invent any measurement.
            producer(args.version)
            writer.assert_called_once_with(self.run_identity, self.run, self.root, self.args.version)

    def test_promote_keeps_evaluated_state_when_shadow_changes_disk(self):
        evaluated = dict(self.good, staged_sha='a' * 40)
        changed = dict(evaluated, staged_sha='b' * 40)
        state_path = pub._state_path(self.args.version)
        state_path.write_text(json.dumps(evaluated))
        def shadow_changes_record(*args, **kwargs):
            state_path.write_text(json.dumps(changed))
            return SimpleNamespace(returncode=0, stdout='fixture GO', stderr='')
        with patch.object(pub, 'run_fire_preflight', return_value=0) as preflight, patch.object(pub.subprocess, 'run', side_effect=shadow_changes_record), patch.object(pub, 'require_ac7_receipt_set', return_value=dict(self.ac7)) as receipt_set, patch.object(pub, '_release_entry_uid_for', return_value='release'), patch.object(pub, '_require_pinned_remote', return_value='https://example.invalid'), patch.object(pub, '_render_scorecard_so_far'), patch.object(pub, '_run_journal_folder', return_value=self.run), patch.object(pub, '_confirm_tty', return_value=False) as confirm, patch.object(pub, '_read_state', wraps=pub._read_state) as read_state:
            self.assertEqual(pub.cmd_promote(self.args), 6)
            read_state.assert_called_once_with(self.args.version)
            preflight.assert_called_once_with(self.args.version, evaluated)
            receipt_set.assert_called_once_with(evaluated, self.args.version)
            self.assertIs(receipt_set.call_args.args[0], preflight.call_args.args[1])
            self.assertEqual(json.loads(state_path.read_text()), changed)
            confirm.assert_called_once()

    def test_promote_preflight_shadow_and_normal_confirm_once_in_both_branches(self):
        for ship_rc in [0, 1]:
            with self.subTest(ship_rc=ship_rc), patch.object(pub, 'run_fire_preflight', side_effect=lambda *a: print('FULL PREFLIGHT VERDICT') or 0) as preflight, patch.object(pub.subprocess, 'run', return_value=SimpleNamespace(returncode=ship_rc, stdout='FULL SHADOW VERDICT', stderr='')) as ship, patch.object(pub, 'require_ac7_receipt_set', return_value=dict(self.ac7)), patch.object(pub, '_release_entry_uid_for', return_value='release'), patch.object(pub, '_require_pinned_remote', return_value='https://example.invalid'), patch.object(pub, '_render_scorecard_so_far'), patch.object(pub, '_run_journal_folder', return_value=self.run), patch.object(pub, '_confirm_tty', side_effect=lambda prompt: self.assertIn('FULL SHADOW VERDICT', self.output.getvalue()) or False) as confirm:
                self.assertEqual(pub.cmd_promote(self.args), 6)
                preflight.assert_called_once_with('9.8.7', self.good)
                ship.assert_called_once()
                self.assertEqual(ship.call_args.args[0][-5:], ['--run-dir', str(self.run), '--candidate', str(self.zip), '--json'])
                confirm.assert_called_once()
                comparison = json.loads((pub._state_path('9.8.7').parent / 'promotion-comparison.json').read_text())
                self.assertEqual(comparison['agreement'], ship_rc == 0)
                self.assertEqual(comparison['ship_rc'], ship_rc)
                self.assertIn('FULL PREFLIGHT VERDICT', self.output.getvalue())


class StaticContract(unittest.TestCase):
    def test_reachable_selection_and_planted_negative(self):
        source = (TOOLS / 'tropo-publish-release.py').read_text()
        self.assertEqual(selection_violations(source), [])
        for statement in ['max(RELEASES_DIR.iterdir(), key=os.path.getctime)', 'sorted(RELEASES_DIR.glob("*"))', 'runs = Path("vault/pipeline-runs"); sorted(runs.glob("*"))']:
            planted = source.replace('def cmd_preflight(args) -> int:', 'def cmd_preflight(args) -> int:\n    ' + statement)
            self.assertTrue(selection_violations(planted), statement)

    def test_candidate_workflow_and_negative(self):
        source = (TOOLS.parents[1] / '.github/workflows/candidate.yml').read_text()
        assert_candidate(self, source)
        with self.assertRaises(AssertionError):
            assert_candidate(self, source.replace('path: ${{ runner.temp }}/candidate', 'path: ${{ runner.temp }}/candidate/CANDIDATE-BOX-MANIFEST.json'))

    def test_build_runbook_joined_strings_and_negative(self):
        source = (TOOLS / 'tropo-build-release.py').read_text()
        self.assertEqual(runbook_violations(source), [])
        for required in ['cold-boot-test.playbook.md', 'Stranger-walk', 'Generate RELEASE-NOTES.md']:
            self.assertIn(required, source)
        planted = source.replace('def main():', '''def main():
    print(f'  5. PUBLISH {new_version}')
    print(f'echo "v{new_version}"')''')
        self.assertTrue(runbook_violations(planted))


if __name__ == '__main__':
    unittest.main()
