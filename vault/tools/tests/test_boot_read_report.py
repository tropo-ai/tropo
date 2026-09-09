"""AC3–6: scratch-only observer, caller and real emitter composition proofs.

Native-shaped synthetic envelopes verify wiring. AC7 real Claude/unsupported
harness acceptance is intentionally outside these tests.
"""
import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from lib import boot_reads as br


def write(root, rel, content):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def declaration(path, ident=None, optional=False):
    return '<!-- tropo-boot-read ' + json.dumps(dict(id=ident or path, path=path,
               applicability='if-present' if optional else 'required')) + ' -->'


def copy_runtime(root):
    for rel in ('tropo-boot-read-observe.py', 'tropo-boot-read-report.py',
                'lib/boot_reads.py', 'lib/boot_identity.py'):
        target = root / 'vault/tools' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TOOLS / rel, target)


class Scratch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="boot reads ' ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.envpatch = patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                  if not k.startswith('TROPO_BOOT_READ_')}, clear=True)
        self.envpatch.start()
        self.addCleanup(self.envpatch.stop)
        copy_runtime(self.root)
        write(self.root, 'x.md', 'one\ntwo\nthree\n')
        write(self.root, 'y.md', 'other\n')
        self.manifest = 'manifest.md'
        write(self.root, self.manifest, '## Boot Protocol\n' + declaration('x.md') + '\n' + declaration('y.md'))
        self.session = 'session-A'
        self.start()

    def payload(self, event, **fields):
        return dict(session_id=self.session, cwd=str(self.root), hook_event_name=event, **fields)

    def start(self):
        return br.observe('session-start', self.payload('SessionStart', source='startup'), self.root)

    def args(self, **kw):
        values = dict(vault_root=str(self.root), harness='claude', session_id=self.session,
                      manifest=self.manifest, agent=None, receipt=None, begin=False,
                      audit=False, window_id=None)
        values.update(kw)
        return argparse.Namespace(**values)

    def begin(self, **kw):
        return br.report(self.args(begin=True, **kw))['window_id']

    def read(self, path='x.md', start=1, count=None, response=None, **extra):
        lines = (self.root / path).read_text().splitlines(keepends=True)
        count = len(lines) - start + 1 if count is None else count
        if response is None:
            response = dict(type='text', file=dict(content=''.join(lines[start - 1:start - 1 + count]),
                            startLine=start, numLines=count, totalLines=len(lines)))
        p = self.payload('PostToolUse', tool_name='Read', tool_use_id='use-1',
                         tool_input=dict(file_path=str(self.root / path), offset=start, limit=count),
                         tool_response=response)
        p.update(extra)
        return br.observe('post-read', p, self.root)

    def result(self, token, **kw):
        return br.report(self.args(window_id=token, **kw))

    def rows(self):
        return [json.loads(l) for l in br.receipt_path(self.root, self.session).read_text().splitlines()]

    def rewrite(self, rows):
        br.receipt_path(self.root, self.session).write_text(''.join(json.dumps(r)+'\n' for r in rows))

    def cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(self.root / 'vault/tools/tropo-boot-read-report.py'),
                 '--vault-root', str(self.root), '--manifest', self.manifest, *args], input=stdin,
                 capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}, timeout=15)


class ObserverContract(Scratch):
    def test_pre_begin_and_post_close_reads_cannot_fulfill(self):
        self.read()
        token = self.begin()
        self.assertEqual(self.result(token)['done'], 0)
        self.read()
        self.assertIsNone(self.rows()[-1]['window_id'])
        with self.assertRaisesRegex(ValueError, 'no begin token'):
            br.report(self.args())
        with self.assertRaisesRegex(ValueError, 'closed'):
            self.result(token)

    def test_po_cal_po_and_abandoned_windows(self):
        a = self.begin(agent='po'); self.read()
        b = self.begin(agent='cal')
        with self.assertRaisesRegex(ValueError, 'superseded'):
            self.result(a, agent='po')
        self.assertEqual(self.result(b, agent='cal')['done'], 0)
        c = self.begin(agent='po')
        self.assertEqual(self.result(c, agent='po')['done'], 0)
        d = self.begin(agent='po'); self.read()
        self.assertEqual(self.result(d, agent='po')['done'], 1)

    def test_session_and_window_removal_controls(self):
        a = self.begin(); self.read()
        saved = self.rows()
        # Removing the binding row must lose the positive, restoration recovers it.
        self.rewrite([r for r in saved if r['kind'] != 'begin'])
        with self.assertRaisesRegex(ValueError, 'absent'):
            self.result(a)
        self.rewrite(saved)
        self.session = 'session-B'; self.start(); b = self.begin()
        with self.assertRaisesRegex(ValueError, 'mismatched'):
            self.result(a)
        self.assertEqual(self.result(b)['done'], 0)
        with self.assertRaisesRegex(ValueError, 'receipt'):
            self.result(a, receipt=str(br.receipt_path(self.root, 'session-A')))
        self.session = 'session-A'
        self.assertEqual(self.result(a)['done'], 1)

    def test_binding_agent_manifest_environment_and_root(self):
        a = self.begin(agent='po'); self.read()
        for overrides in (dict(agent='cal'), dict(manifest='other.md')):
            if 'manifest' in overrides:
                shutil.copy2(self.root/self.manifest, self.root/'other.md')
            with self.assertRaisesRegex(ValueError, 'mismatched'):
                self.result(a, **overrides)
        with patch.dict(os.environ, {'TROPO_BOOT_READ_SESSION_ID':'wrong'}):
            with self.assertRaisesRegex(ValueError, 'environment'):
                self.result(a, agent='po')
        with patch.dict(os.environ, {'TROPO_BOOT_READ_ROOT':str(self.root/'other')}):
            with self.assertRaisesRegex(ValueError, 'root'):
                self.result(a, agent='po')
        self.assertEqual(self.result(a, agent='po')['done'], 1)

    def test_success_filter_and_content_free_receipts(self):
        a = self.begin()
        for fields in ({'tool_name':'Bash'}, {'is_error':True}, {'agent_id':'child'},
                       {'tool_response':{'is_error':True}}, {'hook_event_name':'PreToolUse'}):
            with self.assertRaises(ValueError):
                self.read(**fields)
        self.read()
        raw = br.receipt_path(self.root, self.session).read_text()
        self.assertNotIn('one\\ntwo', raw)
        self.assertNotIn('"content"', raw)
        self.assertEqual(self.result(a)['done'], 1)

    def test_native_cli_environment_binding_quotes_and_resume(self):
        envfile = self.root/'env.sh'
        env = {**os.environ, 'CLAUDE_ENV_FILE':str(envfile), 'PYTHONDONTWRITEBYTECODE':'1'}
        cmd = [sys.executable, str(self.root/'vault/tools/tropo-boot-read-observe.py'), 'session-start']
        p = subprocess.run(cmd, input=json.dumps(self.payload('SessionStart',source='resume')),
                           capture_output=True,text=True,env=env,timeout=15)
        self.assertEqual(p.returncode,0); self.assertIn('bound',p.stdout)
        p = subprocess.run(['sh','-c','. "$1"; printf "%s" "$TROPO_BOOT_READ_ROOT"','sh',str(envfile)],
                           capture_output=True,text=True,timeout=15)
        self.assertEqual(p.stdout,str(self.root))
        self.assertIsNone(br.active_window(self.rows()))
        p = subprocess.run(cmd,input='{malformed',capture_output=True,text=True,env=env,timeout=15)
        self.assertEqual(p.returncode,0);self.assertIn('unavailable',p.stdout)

    def test_missing_cwd_and_unavailable_lock_backend_are_honest(self):
        payload=self.payload('SessionStart',source='startup');payload.pop('cwd')
        with self.assertRaisesRegex(ValueError,'working directory'):
            br.observe('session-start',payload,self.root)
        with patch.object(br,'fcntl',None):
            with self.assertRaisesRegex(ValueError,'serialization'):
                self.begin()
            with self.assertRaisesRegex(ValueError,'not observable in this harness'):
                br.report(self.args(harness='codex'))

    def test_explicit_historical_audit_not_greeting(self):
        a=self.begin();self.read();self.result(a)
        audit=self.result(a,audit=True)
        self.assertTrue(audit['summary'].startswith('Historical audit'))
        with self.assertRaises(ValueError):self.result(a)


class ReportContract(Scratch):
    def test_complete_same_version_ranges_and_removed_row(self):
        a=self.begin();self.read(start=1,count=1);self.read(start=2,count=2);self.read('y.md')
        saved=self.rows()
        self.rewrite([r for r in saved if not (r['kind']=='read' and r['path']=='y.md')])
        result=self.result(a)
        self.assertEqual(result['done'],1)
        self.assertEqual(result['items'][1]['status'],'skipped (no successful Read observed)')
        self.rewrite(saved)
        self.assertEqual(self.result(a)['done'],2)

    def test_unknown_line_coverage_is_still_an_observed_read(self):
        # Real Claude PostToolUse Read envelopes carry no startLine/numLines block,
        # so every row lands coverage unknown while its content version still
        # matches. Those are observed reads; only line coverage is unknown.
        a=self.begin()
        self.read(response='one\ntwo\nthree\n')
        self.read('y.md',response=dict(type='text',file=dict(filePath='y.md',content='other\n')))
        saved=self.rows()
        self.assertTrue(all(r['coverage']=='unknown' and r['ranges']==[] for r in saved if r['kind']=='read'))
        r=self.result(a)
        self.assertEqual((r['observed'],r['due'],r['done'],r['coverage_unknown']),(2,2,0,2))
        self.assertEqual({i['status'] for i in r['items']},{'observed (line coverage unknown)'})
        self.assertTrue(r['summary'].startswith('2/2 declared file reads observed'),r['summary'])
        self.assertIn('line coverage unknown for 2',r['summary'])
        self.assertNotIn('full line coverage',r['summary'])
        # Remove that row and the count must fall with it; a version that no longer
        # matches is not an observed read of the file now declared.
        self.rewrite([row for row in saved if not (row['kind']=='read' and row['path']=='y.md')])
        dropped=self.result(a)
        self.assertEqual(dropped['observed'],1)
        self.assertTrue(dropped['summary'].startswith('1/2 declared file reads observed'),dropped['summary'])
        self.assertEqual(dropped['items'][1]['status'],'skipped (no successful Read observed)')
        self.rewrite(saved);write(self.root,'y.md','replaced\n')
        changed=self.result(a)
        self.assertEqual((changed['observed'],changed['coverage_unknown']),(1,1))
        self.assertEqual(changed['items'][1]['status'],'changed since observed')
        self.assertTrue(changed['summary'].startswith('1/2 declared file reads observed'),changed['summary'])

    def test_partial_and_full_line_coverage_are_reported_beside_the_count(self):
        # A verified full Read keeps full-coverage semantics; a verified range and
        # an unknown-coverage row are both observed, and say so distinctly.
        a=self.begin();self.read(count=1);self.read('y.md',response='other\n')
        r=self.result(a)
        self.assertEqual((r['observed'],r['done'],r['partial'],r['coverage_unknown']),(2,0,1,1))
        self.assertEqual([i['status'] for i in r['items']],
                         ['observed (partial line coverage)','observed (line coverage unknown)'])
        self.assertIn('partial line coverage for 1; line coverage unknown for 1',r['summary'])
        a=self.begin();self.read();self.read('y.md')
        r=self.result(a)
        self.assertEqual((r['observed'],r['done'],r['due']),(2,2,2))
        self.assertEqual({i['status'] for i in r['items']},{'done (full Read observed)'})
        self.assertIn('full line coverage verified for 2',r['summary'])
        self.assertNotIn('unknown',r['summary'])

    def test_offset_limit_default_and_long_line_truncation_unknown(self):
        for mode in ('offset','limit','default','long','unknown'):
            with self.subTest(mode=mode):
                a=self.begin()
                if mode=='offset':self.read(start=2,count=2)
                elif mode=='limit':self.read(count=1)
                elif mode=='default':self.read(response=dict(type='text',file=dict(content='one\n...',startLine=1,numLines=3,totalLines=3)))
                elif mode=='long':self.read(response=dict(type='text',file=dict(content='one\ntw…\nthree\n',startLine=1,numLines=3,totalLines=3)))
                else:self.read(response={'content':'one\ntwo\nthree\n'})
                self.assertEqual(self.result(a)['done'],0)

    def test_changed_version_invalidates_full_credit(self):
        a=self.begin();self.read();write(self.root,'x.md','replacement\n')
        r=self.result(a);self.assertEqual(r['done'],0)
        self.assertEqual(r['items'][0]['status'],'changed since observed')

    def test_missing_start_malformed_duplicate_and_empty_receipts(self):
        a=self.begin();self.read();saved=self.rows()
        self.rewrite([r for r in saved if r['kind']!='session_start'])
        with self.assertRaisesRegex(ValueError,'SessionStart'):self.result(a)
        self.rewrite(saved+[saved[-1]])
        self.assertEqual(self.result(a)['done'],1)
        self.rewrite(saved)
        with br.receipt_path(self.root,self.session).open('a') as f:f.write('{bad\n')
        p=self.cli('--harness','claude','--session-id',self.session,'--window-id',a,'--json')
        self.assertEqual(p.returncode,0);self.assertEqual(json.loads(p.stdout)['status'],'unobservable')

    def test_unsupported_overrides_stale_claude_and_missing_token(self):
        a=self.begin();self.read()
        with patch.dict(os.environ,{'TROPO_BOOT_READ_HARNESS':'claude','TROPO_BOOT_READ_SESSION_ID':self.session}):
            for harness in ('codex','gemini','unknown'):
                p=self.cli('--harness',harness,'--window-id',a)
                self.assertEqual(p.stdout.strip(),'not observable in this harness');self.assertEqual(p.returncode,0)
            p=self.cli('--harness','claude','--json')
            self.assertIn('no begin token',p.stdout)

    def test_optional_absent_present_and_unknown_manifest(self):
        write(self.root,self.manifest,'## Boot Protocol\n'+declaration('absent.md',optional=True)+'\n'+declaration('x.md'))
        a=self.begin();self.read();r=self.result(a)
        self.assertEqual((r['done'],r['due']),(1,1))
        write(self.root,'absent.md','now due')
        a=self.begin();self.read();r=self.result(a)
        self.assertEqual((r['done'],r['due']),(1,2))
        for text in ('## Other\n'+declaration('x.md'),'## Boot Protocol\nRead `x.md`',
                     '## Boot Protocol\n'+declaration('x.md').replace('required','maybe')):
            write(self.root,self.manifest,text)
            with self.assertRaises(ValueError):self.begin()

    def test_no_attachment_or_begin_credit_and_manifest_version_binding(self):
        a=self.begin()
        self.assertEqual(self.result(a)['done'],0)
        a=self.begin();self.read()
        with (self.root/self.manifest).open('a') as f:f.write('\nchanged instructions')
        with self.assertRaisesRegex(ValueError,'mismatched'):self.result(a)


class GreetingContract(Scratch):
    def test_real_companion_declarations_cover_numbered_and_memory_reads(self):
        for slug in ('po','cal','darin'):
            rel=f'vault/templates/companions/{slug}.md'
            target=self.root/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,target)
            _,items=br.manifest_for(self.root,rel)
            section=br.extract_section(target.read_text(),('boot-extension',))[1]
            paths=re.findall(r'^(?:\d+\. |\- )(?:Read )?`([^`]+)`',section,re.M)
            self.assertEqual(len(paths),8)
            self.assertEqual(set(paths),{i['path'] for i in items})
            self.assertIn('command, not a Read-observable action',section)
            for line in section.splitlines():
                if re.match(r'^(?:\d+\. |\- )(?:Read )?`',line):self.assertRegex(line,br.MARKER)
            # A new plain declared read must turn this source-coverage assertion red.
            altered=section+'\n9. Read `new-required.md`\n'
            self.assertNotEqual(set(re.findall(r'^(?:\d+\. |\- )(?:Read )?`([^`]+)`',altered,re.M)),{i['path'] for i in items})

    def test_po_real_governance_discovery_and_version_manifest(self):
        rel='.tropo/concierge/activate.md';target=self.root/rel
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,target)
        _,items=br.manifest_for(self.root,rel)
        expected={'.tropo/version.md','vault/files/eca73d77.md','.tropo/TROPO-CONTROL.md','STUDIO.md',
                  'operating-agreement.md','.tropo-studio/registries/agent-registry.yaml','vault/00-index.jsonl',
                  '.tropo/tool-catalog.md','.tropo/skill-catalog.md','.tropo/sa-agent-catalog.md','.tropo/update-source.json'}
        self.assertEqual({i['path'] for i in items},expected)
        self.assertEqual(next(i for i in items if i['path']=='operating-agreement.md')['applicability'],'if-present')
        self.assertNotIn('vault/tools/tropo-studio-status.py',expected)
        section=br.extract_section(target.read_text(),('boot protocol',))[1]
        # Every directly commanded Read path carries an annotation on that line;
        # the discovery paragraph declares its multi-file list immediately beneath.
        for line in section.splitlines():
            if re.search(r'(?i)\bread\s+(?:\[)?`(?:\.tropo/|STUDIO|operating-agreement|vault/files/eca73d77)',line):
                if 'When you read' not in line and 'message' not in line:
                    self.assertRegex(line,br.MARKER)
        direct=set(re.findall(r'(?i)\bread\s+(?:\[)?`([^`]+)`',section.split('8. **First-boot')[0]))
        discovery=next(l for l in section.splitlines() if l.startswith('4. **Read the discovery'))
        direct.update(re.findall(r'`([^`]+\.(?:md|jsonl|yaml))`',discovery))
        self.assertLessEqual(direct,expected)
        altered=section.split('8. **First-boot')[0]+'\n9. Read `another-new-file.md`'
        self.assertFalse(set(re.findall(r'(?i)\bread\s+(?:\[)?`([^`]+)`',altered)) <= expected)
        self.assertIn('not yet due at greeting',section)

    def test_begin_precedes_reads_and_custom_fallback_greetings_fold(self):
        for rel in ('.tropo/concierge/activate.md','vault/playbooks/99341618.md','.tropo/boot-fast-path.md'):
            text=(ROOT/rel).read_text()
            self.assertIn('--begin',text);self.assertIn('--window-id <returned-token>',text)
            self.assertLess(text.index('--begin'),text.index('--window-id <returned-token>'))
            self.assertIn('agent-reported',text);self.assertIn('environment',text)
            self.assertIn('verbatim',text)
            if rel!='.tropo/concierge/activate.md':
                self.assertIn('custom',text);self.assertIn('fallback',text)
            self.assertNotIn('Silent means this Studio has its own identity',text)
        text=(ROOT/'vault/playbooks/99341618.md').read_text()
        self.assertLess(text.index('--begin'),text.index('#### Step 0.1'))
        self.assertLess(text.index('- Identity confirmation'),text.index('- Capability/environment'))
        text=(ROOT/'.tropo/concierge/activate.md').read_text()
        self.assertLess(text.index('--begin'),text.index('**0c. Version'))

    def test_begin_real_birth_sync_read_report_and_declaration_change(self):
        slug='metis'; rel='vault/agents/abcdef12.md'
        write(self.root,f'agents/{slug}/{slug}-activation.md','---\nagent_uid: abcdef12\n---\n')
        entry=write(self.root,rel,'---\nuid: abcdef12\ntype: agent\nstatus: retired\n'
                    'generation: G0\nretired_at: yesterday\n---\n## §Boot-Extension\n'
                    '1. Read `x.md` '+declaration('x.md')+'\n## §Status-Notes\nBefore birth.\n')
        before=entry.read_text()
        token=self.begin(manifest=None,agent=slug)
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        # Real cmd_born and sync_entry, explicit scratch root. No event emitter
        # exists in this fixture, so there can be no live event side effect.
        born=subprocess.run([sys.executable,str(TOOLS/'tropo-lineage.py'),'--root',str(self.root),
             'born','--agent',slug,'--by','fixture-owner','--model','fixture-model'],
             cwd=self.root,env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(born.returncode,0,born.stderr)
        self.assertEqual(json.loads(born.stdout)['generation'],'G1')
        self.assertNotEqual(entry.read_text(),before)
        self.assertIn('status: active',entry.read_text())
        payload=self.payload('PostToolUse',tool_name='Read',tool_use_id='birth-read',
             tool_input=dict(file_path=str(self.root/'x.md')),
             tool_response=dict(type='text',file=dict(content='one\ntwo\nthree\n',
                  startLine=1,numLines=3,totalLines=3)))
        observed=subprocess.run([sys.executable,str(self.root/'vault/tools/tropo-boot-read-observe.py'),'post-read'],
             cwd=self.root,env=env,input=json.dumps(payload),capture_output=True,text=True,timeout=15)
        self.assertEqual(observed.returncode,0,observed.stderr)
        self.assertIn('Read observation recorded',observed.stdout)
        report_command=[sys.executable,str(self.root/'vault/tools/tropo-boot-read-report.py'),
             '--agent',slug,'--harness','claude','--session-id',self.session,'--window-id',token,'--json']
        reported=subprocess.run(report_command,cwd=self.root,env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(reported.returncode,0,reported.stderr)
        result=json.loads(reported.stdout)
        self.assertEqual((result['done'],result['due']),(1,1),result)
        token=self.begin(manifest=None,agent=slug)
        self.read()
        saved=entry.read_text()
        entry.write_text(saved.replace(declaration('x.md'),declaration('y.md')))
        with self.assertRaisesRegex(ValueError,'mismatched'):
            self.result(token,manifest=None,agent=slug)
        entry.write_text(saved)
        self.assertEqual(self.result(token,manifest=None,agent=slug)['done'],1)

    def test_agent_resolution_uses_instantiated_entry_and_charter(self):
        for shape in ('unified','charter','legacy'):
            with self.subTest(shape=shape):
                slug=shape
                rel={'unified':'vault/agents/testuid.md','charter':'agents/charter/charter.md',
                     'legacy':'agents/legacy/agent-boot.extension.md'}[shape]
                front={'unified':'agent_uid: testuid','charter':'charter_file: '+rel,'legacy':'name: legacy'}[shape]
                write(self.root,f'agents/{slug}/{slug}-activation.md','---\n'+front+'\n---\n')
                write(self.root,rel,'## §Boot-Extension\n1. `x.md` '+declaration('x.md'))
                b,items=br.manifest_for(self.root,agent=slug)
                self.assertEqual(b['manifest'],rel)
                self.assertEqual(items[0]['path'],'x.md')
                a=self.begin(manifest=None,agent=slug);self.read()
                self.assertEqual(self.result(a,manifest=None,agent=slug)['done'],1)


class ShippedContract(Scratch):
    def package(self):
        spec=importlib.util.spec_from_file_location('boot_reads_release_test',TOOLS/'tropo-build-release.py')
        builder=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        source=self.root/'source';source.mkdir()
        # The actual artifact rows and ROOT MANIFEST arm the same verdict gate as
        # release. A minimal source tree keeps all emitter writes inside scratch.
        # Existing manifest walker opens source records without context managers.
        # Keep that unrelated ResourceWarning local to this fixture read.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', ResourceWarning)
            entries=builder.load_manifest_entries(str(ROOT/'vault/00-index.jsonl'),'b2e7d4a9')
        selected=[e for e in entries if e['uid'] in {'0283151e','645e58cd','f51f268c'}]
        self.assertEqual({e['uid'] for e in selected},{'0283151e','645e58cd','f51f268c'})
        paths=['vault/00-index.jsonl','vault/files/b2e7d4a9.md',
               'vault/templates/harness-configs/.claude/settings.json',
               '.tropo/concierge/activate.md','.tropo/boot-fast-path.md',
               'vault/playbooks/99341618.md',
               *[f'vault/templates/companions/{s}.md' for s in ('po','cal','darin')]]
        for rel in paths:
            target=source/rel;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/rel,target)
        copy_runtime(source)
        target=source/'vault/tools/tests/test_boot_read_report.py';target.parent.mkdir(parents=True)
        shutil.copy2(Path(__file__),target)
        write(source,'.tropo/flags/boot-read-receipt-source.jsonl','private source receipt\n')
        build=self.root/'box';build.mkdir();dist=self.root/'dist';dist.mkdir()
        # Both import-time constants and shared roots are patched, restoring them
        # after this bounded emitter call. No release main, freeze or publish.
        with patch.multiple(builder.tropo_roots,STUDIO_ROOT=source,VAULT_DIR=source/'vault'), \
             patch.multiple(builder,KERNEL_DIR=str(source/'.tropo'),INDEX_PATH=str(source/'vault/00-index.jsonl'),DRY_RUN=False), \
             redirect_stdout(io.StringIO()):
            builder.init_ship_verdicts(source,source/'vault/00-index.jsonl')
            builder.build_from_manifest(str(build),selected)
            builder.step_3_copy_kernel(str(build))
            builder.step_3b_copy_vault_tools(str(build))
            builder.step_3d_copy_vault_playbooks(str(build))
            builder.step_11_zip_and_upload(str(build),'0.0.0-test',str(dist))
        self.assertTrue((source/'.tropo/publish-pending.json').is_file())
        extracted=self.root/'extracted box';extracted.mkdir()
        with zipfile.ZipFile(dist/'tropo-os-v0.0.0-test.zip') as archive:
            archive.extractall(extracted)
        self.assertEqual((extracted/'.claude/settings.json').read_bytes(),
                         (ROOT/'vault/templates/harness-configs/.claude/settings.json').read_bytes())
        self.assertFalse((extracted/'vault/templates/harness-configs/.claude/settings.json').exists())
        self.assertFalse((extracted/'.tropo/flags/boot-read-receipt-source.jsonl').exists())
        self.assertFalse((extracted/'.tropo/publish-pending.json').exists())
        for rel in ('vault/tools/lib/boot_reads.py','vault/tools/lib/boot_identity.py',
                    'vault/tools/tests/test_boot_read_report.py','vault/playbooks/99341618.md',
                    '.tropo/concierge/activate.md','vault/templates/companions/cal.md'):
            self.assertTrue((extracted/rel).is_file(),rel)
        self.assertNotIn(str(ROOT),(extracted/'.claude/settings.json').read_text())
        return extracted

    def hook_chain(self,root,settings=None):
        config=json.loads((settings or root/'.claude/settings.json').read_text())
        env={**os.environ,'CLAUDE_PROJECT_DIR':str(root),'CLAUDE_ENV_FILE':str(root/'hook-env.sh'),
             'PYTHONDONTWRITEBYTECODE':'1'}
        sid='native-shaped-fixture'
        def hook(event,verb,payload):
            value=payload.get('tool_name') if event=='PostToolUse' else payload.get('source')
            # Dispatch using the native matcher target before selecting this
            # observer's command. A Read->Bash mutation must never fire on Read.
            matched=[group for group in config['hooks'].get(event,[])
                     if not group.get('matcher') or re.fullmatch(group['matcher'],value or '')]
            commands=[h['command'] for group in matched for h in group['hooks']
                      if 'tropo-boot-read-observe.py' in h.get('command','') and verb in h['command']]
            self.assertEqual(len(commands),1,'shipped observer hook missing or ambiguous')
            p=subprocess.run(commands[0],shell=True,cwd=root,env=env,input=json.dumps(dict(
               session_id=sid,cwd=str(root),hook_event_name=event,**payload)),capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertNotIn('unavailable',p.stdout)
        hook('SessionStart','session-start',dict(source='startup'))
        # The caller manifest is a real emitted companion, not a test-only list.
        manifest='vault/templates/companions/cal.md'
        cmd=[sys.executable,str(root/'vault/tools/tropo-boot-read-report.py'),'--manifest',manifest,
             '--session-id',sid,'--harness','claude','--json']
        def call(extra):
            p=subprocess.run(cmd+extra,cwd=root,env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stderr)
            return json.loads(p.stdout)
        begin=call(['--begin']);self.assertEqual(begin['status'],'begun',begin)
        # One full native-shaped Read after begin. Missing remaining declarations
        # must be reported as skipped, even when their catalogs do not exist.
        rel='.tropo/tool-catalog.md';write(root,rel,'fixture catalog\n')
        hook('PostToolUse','post-read',dict(tool_name='Read',tool_use_id='native-use',
             tool_input=dict(file_path=str(root/rel)),tool_response=dict(type='text',file=dict(
                 content='fixture catalog\n',startLine=1,numLines=1,totalLines=1))))
        result=call(['--window-id',begin['window_id']])
        self.assertEqual((result['done'],result['due']),(1,8),result)
        self.assertEqual(sum(i['status'].startswith('skipped') for i in result['items']),7)
        self.assertTrue(br.receipt_path(root,sid).exists())
        return result

    def test_actual_manifest_emit_extract_settings_observer_receipt_report(self):
        self.hook_chain(self.package())

    def test_live_settings_commands_match_and_execute_from_scratch(self):
        root=self.root/'live settings fixture';root.mkdir();copy_runtime(root)
        rel='vault/templates/companions/cal.md';target=root/rel;target.parent.mkdir(parents=True)
        shutil.copy2(ROOT/rel,target)
        self.hook_chain(root,ROOT/'.claude/settings.json')
        live=json.loads((ROOT/'.claude/settings.json').read_text())
        shipped=json.loads((ROOT/'vault/templates/harness-configs/.claude/settings.json').read_text())
        for event in ('SessionStart','PostToolUse'):
            def commands(config):return [h['command'] for g in config['hooks'][event] for h in g['hooks']
                           if 'tropo-boot-read-observe.py' in h['command']]
            self.assertEqual(commands(live),commands(shipped))

    def test_removed_shipping_hook_and_observer_import_causal_controls(self):
        root=self.package();settings=root/'.claude/settings.json';original=settings.read_text()
        config=json.loads(original);config['hooks'].pop('PostToolUse')
        settings.write_text(json.dumps(config))
        with self.assertRaises(AssertionError):self.hook_chain(root)
        settings.write_text(original)
        config=json.loads(original)
        for group in config['hooks']['PostToolUse']:
            if group.get('matcher')=='Read':group['matcher']='Bash'
        settings.write_text(json.dumps(config))
        with self.assertRaises(AssertionError):self.hook_chain(root)
        settings.write_text(original)
        observer=root/'vault/tools/lib/boot_reads.py';content=observer.read_text()
        observer.write_text('raise ImportError("negative control")\n')
        with self.assertRaises(AssertionError):self.hook_chain(root)
        observer.write_text(content)
        self.hook_chain(root)

    def test_compact_literal_and_existing_operator_settings_survive_apply(self):
        for rel in ('.claude/settings.json','vault/templates/harness-configs/.claude/settings.json'):
            config=json.loads((ROOT/rel).read_text())
            command=next(h['command'] for g in config['hooks']['SessionStart'] if g['matcher']=='compact'
                         for h in g['hooks'] if h['command'].startswith('printf'))
            p=subprocess.run(command,shell=True,cwd=self.root,capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0)
            self.assertIn('never run `born`',p.stdout)
            self.assertIn('`python3 vault/tools/tropo-compact-continue.py --agent <slug>`',p.stdout)
            self.assertEqual(p.stderr,'')
        from vault.tools.tests.test_lift_and_replace_v190 import _load_applier,_write_image,_prior_manifest
        root=self.root/'apply fixture';root.mkdir();studio=root/'studio';studio.mkdir()
        write(studio,'.claude/settings.json','{"operator": true}')
        image=_write_image(root,{'.claude/settings.json':'{"vendor": true}','tool.py':'updated'})
        prior=_prior_manifest(root,{'.claude/settings.json':'{"old": true}'})
        applier=_load_applier()
        applier.apply(image_dir=image,studio_dir=studio,prior_manifest=prior)
        self.assertEqual((studio/'.claude/settings.json').read_text(),'{"operator": true}')
        self.assertEqual((studio/'tool.py').read_text(),'updated')


if __name__ == '__main__':
    unittest.main()
