"""The release ignition, end to end in an isolated studio (0a0a6777 AC4/AC5).

The library tests next door prove the transaction and the gate in isolation.
This proves the TOOL: that a real release-plan lock writes the whole
transaction, that each refusal leaves the studio byte-for-byte untouched, and
that "zero partial state" holds for the tool and not just for the primitive it
is built on.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

_spec = importlib.util.spec_from_file_location(
    "lock_release_plan", TOOLS / "tropo-lock-release-plan.py")
rl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rl)

from lib import fan_in, lock_transaction as lt  # noqa: E402
import temp_studio  # noqa: E402

TESTED_SHA = "a1b2c3d4" * 5  # 40 hex
RELEASE_GRAPH_UIDS = (
    "634913c2", "471dd767", "8a4f802b", "8e03f8d6",
    "f9365ede", "8654900a", "0cf86ea5", "4f64ec3c", "37996741",
    "2e9b1db7", "4262d5fa", "a0f2bea8", "bc6b17ec", "c6b61fb9",
    "3dd817cb",
)


def _entry(uid: str, **fields) -> str:
    lines = [f"{k}: {v}" for k, v in fields.items()]
    return "---\n" + f"uid: {uid}\n" + "\n".join(lines) + "\n---\n\n# " + uid + "\n"


def _journalled(body: dict) -> str:
    """Render a synthetic journal with a CORRECT plan_digest.

    Recovery now recomputes the digest rather than shape-checking it, so a
    fixture with a placeholder digest is refused as tampered — correctly. These
    fixtures are testing recovery's behaviour on VALID journals, so they have to
    produce valid ones; the tamper cases live in the crash matrix.
    """
    body = dict(body)
    body["plan_digest"] = lt.journal_plan_digest(body)
    return json.dumps(body, indent=2, sort_keys=True) + "\n"


class ReleaseLockEndToEnd(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="release-lock-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.runs = self.tmp / "vault" / "pipeline-runs"
        self.files.mkdir(parents=True)
        self.runs.mkdir(parents=True)
        self._orig = (lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT)
        lt.LOCK_JOURNAL_DIR = self.tmp / "journal"
        lt.WORKSPACE_LOCK_PATH = self.tmp / "journal" / "ignition.lock"
        lt.VAULT_ROOT = self.tmp
        self._build_studio()

    def tearDown(self) -> None:
        lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, uid: str, text: str) -> None:
        (self.files / f"{uid}.md").write_text(text, encoding="utf-8")

    #: The activation/root/spec each run belongs to, so receipts can bind a real
    #: identity chain rather than a bare SHA.
    CHAIN = {
        "0bb00001": ("5ec00001", "ac700001", "a0000001"),
        "0bb00002": ("5ec00002", "ac700002", "a0000002"),
    }

    def _close_receipt(self, run_uid: str, sha: str = TESTED_SHA, count: int = 1,
                       **override) -> None:
        """A CANONICAL dev-close receipt in the run's own event log.

        Blocker 3: the earlier fixture wrote `{"event": "dev_closed",
        "tested_sha": ...}` and called it authoritative. That shape is trivially
        forgeable and binds nothing, so consuming it proved only that a line
        existed. A real receipt names the whole chain — spec, activation, run,
        root, journal, tree — and `override` lets the plants below corrupt
        exactly one link at a time.
        """
        spec_uid, activation_uid, root_uid = self.CHAIN[run_uid]
        folder = self.runs / f"dev-run-{run_uid}"
        folder.mkdir(parents=True, exist_ok=True)
        lines = []
        for index in range(count):
            data = {
                "receipt_kind": "canonical-dev-close",
                "tested_sha": sha if index == 0 else f"{index:040x}",
                "tested_commit_sha": sha if index == 0 else f"{index:040x}",
                "dev_spec_uid": spec_uid,
                "activation_uid": activation_uid,
                "pipeline_run_uid": run_uid,
                "activation_root_uid": root_uid,
                "journal": f".tropo-studio/pipeline-close/{activation_uid}.json",
                "verdict": "complete",
                "closed": ["run", "activation", "root"],
            }
            data.update(override)
            lines.append(json.dumps({
                "event": "dev_closed", "trace_id": activation_uid, "data": data,
            }))
        (folder / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _build_studio(self) -> None:
        """One release-plan at specify with two done, receipt-backed members."""
        # Typed PASSING evidence. A note has no verdict field, so "the ACs
        # passed" and "someone wrote something down" would be the same claim.
        self._write("e0000001", _entry("e0000001", type="completion-report",
                                       title="evidence one", status="done"))
        self._write("e0000002", _entry("e0000002", type="completion-report",
                                       title="evidence two", status="done"))
        for root, act in (("a0000001", "ac700001"), ("a0000002", "ac700002")):
            self._write(root, _entry(root, type="project", title="activation root",
                                     status="active", activation_uid=f"'{act}'"))
        self._write("0ef00001", _entry("0ef00001", type="completion-report", title="report one"))
        self._write("0ef00002", _entry("0ef00002", type="completion-report", title="report two"))

        # The release-pipeline root and one step, ACTIVE and versioned, so the
        # ignition can snapshot a real declaration set instead of a hardcoded one.
        self._write(rl.RELEASE_PIPELINE_UID, _entry(
            rl.RELEASE_PIPELINE_UID, type="pipeline", title="release-pipeline",
            status="active", version="1.0.0", children="\n  - 57e90001"))
        self._write("57e90001", _entry("57e90001", type="pipeline",
                                       subtype="workflow-node", title="assemble",
                                       status="active"))

        for n, (spec, act, run, rep, ev) in enumerate([
            ("5ec00001", "ac700001", "0bb00001", "0ef00001", "e0000001"),
            ("5ec00002", "ac700002", "0bb00002", "0ef00002", "e0000002"),
        ], start=1):
            self._write(spec, "---\n" + "\n".join([
                f"uid: {spec}", "type: dev-spec", f"title: spec {n}", "status: done",
                f"dev_spec_activation_uid: '{act}'",
                f"completion_report_uid: '{rep}'",
                "acceptance_evidence:", f"  - {ev}",
            ]) + "\n---\n\n# spec\n")
            self._write(act, _entry(act, type="activation", title=f"act {n}",
                                    status="done"))
            self._write(run, "---\n" + "\n".join([
                f"uid: {run}", "type: pipeline-run", f"title: run {n}",
                "status: done", f"activation: '{act}'",
                f"run_folder: 'vault/pipeline-runs/dev-run-{run}'",
            ]) + "\n---\n\n# run\n")
            self._close_receipt(run)

        self._write("b1a00001", "---\n" + "\n".join([
            "uid: b1a00001", "type: release-plan", "title: test release plan",
            "status: specify", "state: active", "release_version: 9.9.9",
            "dev_spec_uids:", "  - 5ec00001", "  - 5ec00002",
        ]) + "\n---\n\n# plan\n")

    def _snapshot(self) -> dict:
        """Studio substrate only.

        The journal directory is deliberately excluded: it holds the workspace
        lock and transaction journals, which are machine-local recovery state
        and are gitignored. "The refusal changed nothing" is a claim about the
        vault, not about whether a lock file was touched.
        """
        out = {}
        for path in sorted(self.tmp.rglob("*")):
            if path.is_file() and "journal" not in path.relative_to(self.tmp).parts:
                out[str(path.relative_to(self.tmp))] = hashlib.sha256(
                    path.read_bytes()).hexdigest()
        return out

    def _lock(self):
        # NOT wrapped in the workspace lock. The tool acquires its own span, and
        # wrapping it here is what hid the fact that it did not: the suite
        # passed while the real CLI path refused.
        return rl.lock_release_plan("b1a00001", "talos", self.files, self.runs)

    # ---------------------------------------------------------------- happy path

    def test_a_clean_lock_writes_the_whole_transaction(self) -> None:
        code, message = self._lock()
        self.assertEqual(code, 0, message)

        fm = rl.read_entry("b1a00001", self.files)["frontmatter"]
        self.assertEqual(fm["status"], "locked")
        self.assertEqual(fm["dev_spec_uids"], ["5ec00001", "5ec00002"])
        for key in ("fan_in_manifest_ref", "fan_in_digest",
                    "release_activation_uid", "release_pipeline_run_uid"):
            self.assertTrue(fm.get(key), f"{key} missing after lock")

        manifest = self.tmp / fm["fan_in_manifest_ref"]
        self.assertTrue(manifest.is_file(), f"no manifest at {manifest}")
        body = json.loads(manifest.read_text())
        self.assertEqual(body["row_count"], 2)
        self.assertEqual(body["fan_in_digest"], fm["fan_in_digest"],
                         "the plan's digest and its manifest disagree")

        for row in body["rows"]:
            for field_name in fan_in.REQUIRED_ROW_FIELDS:
                self.assertTrue(row.get(field_name), f"row missing {field_name}")
            self.assertEqual(row["tested_final_commit"], TESTED_SHA)

        run_fm = rl.read_entry(fm["release_pipeline_run_uid"], self.files)["frontmatter"]
        self.assertEqual(run_fm["pipeline"], rl.RELEASE_PIPELINE_UID)
        self.assertEqual(run_fm["activation"], fm["release_activation_uid"])

    def test_real_release_lock_then_real_runtime_dry_run_bootstrap(self) -> None:
        """Join the two production entry points that previously passed apart.

        The release-lock E2E used to stop after asserting that an activation
        existed. Runtime bootstrap tests used dev-lock activations rendered by
        the shared producer. Both suites passed while the release lock's private
        renderer omitted the canonical activation contract and its output was
        refused by the real runtime.
        """
        studio = temp_studio.TempStudio(self.tmp).build()
        production_before = temp_studio.production_fingerprint()
        script = self.tmp / "release_lock_then_bootstrap.py"
        script.write_text(
            "import importlib.util, json, sys\n"
            "from pathlib import Path\n"
            f"STUDIO = Path({str(studio.root)!r})\n"
            f"TOOLS = Path({str(studio.tools)!r})\n"
            "sys.path.insert(0, str(STUDIO / '.tropo' / 'scripts'))\n"
            "sys.path.insert(0, str(TOOLS))\n"
            "spec = importlib.util.spec_from_file_location(\n"
            "    'release_lock', TOOLS / 'tropo-lock-release-plan.py')\n"
            "release_lock = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(release_lock)\n"
            "from lib import lock_transaction as lt\n"
            "spec = importlib.util.spec_from_file_location(\n"
            "    'runtime', TOOLS / '9e7003b1.py')\n"
            "runtime = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(runtime)\n"
            "assert Path(release_lock.VAULT_ROOT).resolve() == STUDIO\n"
            "assert Path(runtime.VAULT_ROOT).resolve() == STUDIO\n"
            "assert Path(lt.VAULT_ROOT).resolve() == STUDIO\n"
            "files = STUDIO / 'vault' / 'files'\n"
            "runs = STUDIO / 'vault' / 'pipeline-runs'\n"
            "code, message = release_lock.lock_release_plan(\n"
            "    'b1a00001', 'talos-isolated', files, runs)\n"
            "print('LOCK_CODE', code)\n"
            "assert code == 0, message\n"
            "plan = release_lock.read_entry('b1a00001', files)['frontmatter']\n"
            "activation_uid = plan['release_activation_uid']\n"
            "activation = release_lock.read_entry(\n"
            "    activation_uid, files)['frontmatter']\n"
            "print('ACTIVATION_CLASS', activation.get('activation_class'))\n"
            "print('PIPELINE_UID', activation.get('pipeline_uid'))\n"
            "print('ROOT_MATCH', activation.get('activation_root_project') in "
            "      (activation.get('member_of') or []))\n"
            "contract = STUDIO / 'contract-input.json'\n"
            "contract.write_text(json.dumps({\n"
            "    'skips_authorized_upfront': [],\n"
            "    'additional_steps_added': [],\n"
            "    'trust_overrides': {},\n"
            "    'human_instructions': '',\n"
            "}))\n"
            "runtime.action_bootstrap(activation_uid, str(contract), True)\n"
            "print('BOOTSTRAP_DRY_RUN_OK')\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        production_after = temp_studio.production_fingerprint()
        self.assertEqual(
            temp_studio.diff_fingerprints(production_before, production_after),
            {},
            "the isolated lock→bootstrap regression touched the production Studio",
        )
        self.assertEqual(
            result.returncode,
            0,
            f"stdout={result.stdout}\nstderr={result.stderr[-2500:]}",
        )
        self.assertIn("LOCK_CODE 0", result.stdout)
        self.assertIn("ACTIVATION_CLASS pipeline", result.stdout)
        self.assertIn(f"PIPELINE_UID {rl.RELEASE_PIPELINE_UID}", result.stdout)
        self.assertIn("ROOT_MATCH True", result.stdout)
        self.assertIn("BOOTSTRAP_DRY_RUN_OK", result.stdout)

    def test_real_release_lock_then_real_runtime_bootstrap_preserves_lock_provenance(self) -> None:
        """The adopted run keeps the immutable identity the lock already authored.

        Dry-run cannot expose this class because the destructive write is after
        the dry-run return. This drives both production entry points non-dry-run
        in a TempStudio and binds the lock's values across adoption.
        """
        studio = temp_studio.TempStudio(self.tmp).build()
        production_before = temp_studio.production_fingerprint()
        script = self.tmp / "release_lock_then_real_bootstrap.py"
        script.write_text(
            "import importlib.util, json, sys\n"
            "from pathlib import Path\n"
            f"STUDIO = Path({str(studio.root)!r})\n"
            f"TOOLS = Path({str(studio.tools)!r})\n"
            "sys.path.insert(0, str(TOOLS))\n"
            "spec = importlib.util.spec_from_file_location(\n"
            "    'release_lock', TOOLS / 'tropo-lock-release-plan.py')\n"
            "release_lock = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(release_lock)\n"
            "spec = importlib.util.spec_from_file_location(\n"
            "    'runtime', TOOLS / '9e7003b1.py')\n"
            "runtime = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(runtime)\n"
            "files = STUDIO / 'vault' / 'files'\n"
            "runs = STUDIO / 'vault' / 'pipeline-runs'\n"
            "code, message = release_lock.lock_release_plan(\n"
            "    'b1a00001', 'talos-isolated', files, runs)\n"
            "assert code == 0, message\n"
            "plan = release_lock.read_entry('b1a00001', files)['frontmatter']\n"
            "activation_uid = plan['release_activation_uid']\n"
            "run_uid = plan['release_pipeline_run_uid']\n"
            "before = release_lock.read_entry(run_uid, files)['frontmatter']\n"
            "bound_fields = ('declaration_digest', 'activation', "
            "'release_plan_uid', 'run_folder', 'pipeline_version', 'created_by', "
            "'substrate_authored_by')\n"
            "locked_values = {key: before.get(key) for key in bound_fields}\n"
            "folder = STUDIO / before['run_folder']\n"
            "manifest = folder / 'fan-in-manifest.json'\n"
            "manifest_before = manifest.read_bytes()\n"
            "contract = STUDIO / 'contract-input.json'\n"
            "contract.write_text(json.dumps({\n"
            "    'skips_authorized_upfront': [],\n"
            "    'additional_steps_added': [],\n"
            "    'trust_overrides': {},\n"
            "    'human_instructions': '',\n"
            "}))\n"
            "returned = runtime.action_bootstrap(\n"
            "    activation_uid, str(contract), False)\n"
            "after = release_lock.read_entry(run_uid, files)['frontmatter']\n"
            "print('ADOPTED_SAME_RUN', returned == run_uid)\n"
            "print('PROVENANCE_PRESERVED', all(\n"
            "    after.get(key) == value for key, value in locked_values.items()))\n"
            "print('EVENTS_EXIST', runtime._run_has_events(folder))\n"
            "print('MANIFEST_PRESERVED', manifest.read_bytes() == manifest_before)\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        production_after = temp_studio.production_fingerprint()
        self.assertEqual(
            temp_studio.diff_fingerprints(production_before, production_after),
            {},
            "the isolated non-dry-run lock→bootstrap regression touched production",
        )
        self.assertEqual(
            result.returncode,
            0,
            f"stdout={result.stdout}\nstderr={result.stderr[-2500:]}",
        )
        self.assertIn("ADOPTED_SAME_RUN True", result.stdout)
        self.assertIn("PROVENANCE_PRESERVED True", result.stdout)
        self.assertIn("EVENTS_EXIST True", result.stdout)
        self.assertIn("MANIFEST_PRESERVED True", result.stdout)

    def test_real_release_lock_bootstrap_opens_both_release_legs_with_run_plan_provenance(self) -> None:
        """Drive AC6's two real trigger steps from one real locked release run.

        The release activation deliberately has no dev_spec_uid. Each child spec,
        activation, and auto-bootstrapped run must bind to the parent release
        activation/run/plan instead, while malformed or class-mismatched input
        refuses before the first write.
        """
        studio = temp_studio.TempStudio(self.tmp).build()
        production_before = temp_studio.production_fingerprint()
        real_files = TOOLS.parent / "files"
        for uid in RELEASE_GRAPH_UIDS + ("5a4337ff", "da3f50dc"):
            shutil.copy2(real_files / f"{uid}.md", studio.files / f"{uid}.md")

        script = self.tmp / "release_lock_bootstrap_trigger_both_legs.py"
        script.write_text(
            "import importlib.util, json, sys\n"
            "from pathlib import Path\n"
            f"STUDIO = Path({str(studio.root)!r})\n"
            f"TOOLS = Path({str(studio.tools)!r})\n"
            "sys.path.insert(0, str(STUDIO / '.tropo' / 'scripts'))\n"
            "sys.path.insert(0, str(TOOLS))\n"
            "def load(name, filename):\n"
            "    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)\n"
            "    module = importlib.util.module_from_spec(spec)\n"
            "    spec.loader.exec_module(module)\n"
            "    return module\n"
            "release_lock = load('release_lock_both_legs', 'tropo-lock-release-plan.py')\n"
            "runtime = load('runtime_both_legs', '9e7003b1.py')\n"
            "files = STUDIO / 'vault' / 'files'\n"
            "runs = STUDIO / 'vault' / 'pipeline-runs'\n"
            "code, message = release_lock.lock_release_plan(\n"
            "    'b1a00001', 'talos-isolated', files, runs)\n"
            "assert code == 0, message\n"
            "plan = release_lock.read_entry('b1a00001', files)['frontmatter']\n"
            "activation_uid = plan['release_activation_uid']\n"
            "run_uid = plan['release_pipeline_run_uid']\n"
            "activation = runtime.read_vault_entry(activation_uid)['frontmatter']\n"
            "assert 'dev_spec_uid' not in activation\n"
            "contract = STUDIO / 'contract-input.json'\n"
            "contract.write_text(json.dumps({\n"
            "    'skips_authorized_upfront': [], 'additional_steps_added': [],\n"
            "    'trust_overrides': {}, 'human_instructions': '',\n"
            "}))\n"
            "assert runtime.action_bootstrap(activation_uid, str(contract), False) == run_uid\n"
            "parent = runtime.find_pipeline_run_for(activation_uid)\n"
            "folder = runtime.run_folder_for(parent['frontmatter'])\n"
            "runtime.append_event(folder, runtime.make_event(\n"
            "    'verification_receipt', 'tempstudio-replay', step='f9365ede',\n"
            "    trace_id=activation_uid, parent_span_id=None,\n"
            "    data={'verdict': 'pass'}))\n"
            "dev_paths = [files / '5ec00001.md', files / '5ec00002.md']\n"
            "dev_before = {p.name: p.read_bytes() for p in dev_paths}\n"
            "try:\n"
            "    runtime.action_trigger_step(\n"
            "        activation_uid, '0cf86ea5', 'd0c0bad0', 'not-frontmatter',\n"
            "        '5a4337ff', 'doc-pipeline', 'talos-isolated', dry_run=True)\n"
            "except runtime.ValidationError:\n"
            "    print('MALFORMED_REFUSED True')\n"
            "else:\n"
            "    raise AssertionError('trigger accepted malformed spec body')\n"
            "bad_body = '---\\nuid: d0c0bad1\\ntype: test-spec\\n---\\n\\nbad\\n'\n"
            "try:\n"
            "    runtime.action_trigger_step(\n"
            "        activation_uid, '0cf86ea5', 'd0c0bad1', bad_body,\n"
            "        '5a4337ff', 'doc-pipeline', 'talos-isolated', dry_run=True)\n"
            "except runtime.ValidationError:\n"
            "    print('MISMATCH_REFUSED True')\n"
            "else:\n"
            "    raise AssertionError('doc trigger accepted a test-spec body')\n"
            "wrong_pipeline_body = '---\\nuid: d0c0bad2\\ntype: doc-spec\\n---\\n\\nbad\\n'\n"
            "try:\n"
            "    runtime.action_trigger_step(\n"
            "        activation_uid, '0cf86ea5', 'd0c0bad2', wrong_pipeline_body,\n"
            "        'da3f50dc', 'test-pipeline', 'talos-isolated', dry_run=True)\n"
            "except runtime.ValidationError:\n"
            "    print('CLASS_PIPELINE_MISMATCH_REFUSED True')\n"
            "else:\n"
            "    raise AssertionError('doc trigger accepted test class/pipeline')\n"
            "assert not (files / 'd0c0bad0.md').exists()\n"
            "assert not (files / 'd0c0bad1.md').exists()\n"
            "assert not (files / 'd0c0bad2.md').exists()\n"
            "doc_body = ('---\\nuid: d0c00001\\ntype: doc-spec\\nstatus: active\\n'\n"
            "            'target_subsystem: null\\ntarget_tier: multi\\n'\n"
            "            'doc_changes_required: []\\nacceptance_criteria: release docs\\n'\n"
            "            '---\\n\\n# release doc leg\\n')\n"
            "test_body = ('---\\nuid: 7e570001\\ntype: test-spec\\nstatus: active\\n'\n"
            "             \"capsule_version: '1.3'\\ntarget_substrate: []\\n\"\n"
            "             'target_subsystem: null\\nbehaviors_covered: []\\n'\n"
            "             'coverage_class: smoke\\nacceptance_criteria: release tests\\n'\n"
            "             '---\\n\\n# release test leg\\n')\n"
            "doc = runtime.action_trigger_step(\n"
            "    activation_uid, '0cf86ea5', 'd0c00001', doc_body,\n"
            "    '5a4337ff', 'doc-pipeline', 'talos-isolated')\n"
            "test = runtime.action_trigger_step(\n"
            "    activation_uid, '4f64ec3c', '7e570001', test_body,\n"
            "    'da3f50dc', 'test-pipeline', 'talos-isolated')\n"
            "def assert_chain(spec_uid, result, pipeline_class):\n"
            "    spec_fm = runtime.read_vault_entry(spec_uid)['frontmatter']\n"
            "    act_fm = runtime.read_vault_entry(\n"
            "        result['triggered_activation_uid'])['frontmatter']\n"
            "    child = runtime.find_pipeline_run_for(result['triggered_activation_uid'])\n"
            "    child_fm = child['frontmatter']\n"
            "    for fm in (spec_fm, act_fm, child_fm):\n"
            "        assert fm['release_plan_uid'] == 'b1a00001', fm\n"
            "        assert fm['release_pipeline_run_uid'] == run_uid, fm\n"
            "    assert spec_fm['triggered_by_release_pipeline'] == activation_uid\n"
            "    assert spec_fm['triggered_activation_uid'] == result['triggered_activation_uid']\n"
            "    assert 'triggered_by_dev_cycle' not in spec_fm\n"
            "    assert act_fm['triggered_by_activation'] == activation_uid\n"
            "    assert act_fm['triggered_spec_uid'] == spec_uid\n"
            "    assert act_fm['triggered_pipeline_class'] == pipeline_class\n"
            "    assert child_fm['triggered_by_activation'] == activation_uid\n"
            "    assert child_fm['triggered_spec_uid'] == spec_uid\n"
            "    context = runtime.build_run_context_uids(\n"
            "        child, result['triggered_activation_uid'])\n"
            "    own_spec_handle = ('doc_spec' if pipeline_class == 'doc-pipeline'\n"
            "                       else 'test_spec')\n"
            "    assert context[own_spec_handle] == spec_uid, context\n"
            "    assert context['release_plan'] == 'b1a00001', context\n"
            "    assert context['release_pipeline_run'] == run_uid, context\n"
            "    assert context['triggering_release_activation'] == activation_uid, context\n"
            "assert_chain('d0c00001', doc, 'doc-pipeline')\n"
            "assert_chain('7e570001', test, 'test-pipeline')\n"
            "assert dev_before == {p.name: p.read_bytes() for p in dev_paths}\n"
            "records = runtime._release_leg_records(runtime.read_events(folder))\n"
            "assert records['doc']['activation_uid'] == doc['triggered_activation_uid']\n"
            "assert records['test']['activation_uid'] == test['triggered_activation_uid']\n"
            "print('BOTH_RELEASE_LEGS_BOUND True')\n"
            "print('CHILD_CONTEXT_BOUND True')\n"
            "print('DEV_SPECS_UNCHANGED True')\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        production_after = temp_studio.production_fingerprint()
        self.assertEqual(
            temp_studio.diff_fingerprints(production_before, production_after),
            {},
            "the isolated release trigger regression touched production",
        )
        self.assertEqual(
            result.returncode,
            0,
            f"stdout={result.stdout}\nstderr={result.stderr[-4000:]}",
        )
        self.assertIn("MALFORMED_REFUSED True", result.stdout)
        self.assertIn("MISMATCH_REFUSED True", result.stdout)
        self.assertIn("CLASS_PIPELINE_MISMATCH_REFUSED True", result.stdout)
        self.assertIn("BOTH_RELEASE_LEGS_BOUND True", result.stdout)
        self.assertIn("CHILD_CONTEXT_BOUND True", result.stdout)
        self.assertIn("DEV_SPECS_UNCHANGED True", result.stdout)

    def test_all_digit_minted_uids_remain_strings_through_real_bootstrap(self) -> None:
        """YAML must not coerce a valid all-digit eight-hex UID into an integer.

        Random minting made this a roughly two-percent flake: the transaction
        succeeded, but runtime adoption returned an integer run UID while the
        locked plan carried a string. Force all three ignition identities into
        that shape and drive the real bootstrap boundary.
        """
        studio = temp_studio.TempStudio(self.tmp).build()
        production_before = temp_studio.production_fingerprint()
        minted = iter(("12345678", "23456789", "34567890"))
        original_mint = rl._mint_uid
        rl._mint_uid = lambda *_args, **_kwargs: next(minted)
        try:
            code, message = self._lock()
        finally:
            rl._mint_uid = original_mint
        self.assertEqual(code, 0, message)

        plan = rl.read_entry("b1a00001", self.files)["frontmatter"]
        self.assertEqual(plan["release_activation_uid"], "23456789")
        self.assertEqual(plan["release_pipeline_run_uid"], "34567890")
        for uid in ("12345678", "23456789", "34567890"):
            parsed = rl.read_entry(uid, self.files)["frontmatter"]
            self.assertIsInstance(parsed["uid"], str)
            self.assertEqual(parsed["uid"], uid)

        runtime = studio.load("9e7003b1.py", "numeric_uid_runtime")
        contract = self.tmp / "numeric-uid-contract.json"
        contract.write_text(json.dumps({
            "skips_authorized_upfront": [],
            "additional_steps_added": [],
            "trust_overrides": {},
            "human_instructions": "",
        }))
        returned = runtime.action_bootstrap("23456789", str(contract), False)
        self.assertIsInstance(returned, str)
        self.assertEqual(returned, "34567890")
        production_after = temp_studio.production_fingerprint()
        self.assertEqual(
            temp_studio.diff_fingerprints(production_before, production_after),
            {},
            "numeric-UID lock→bootstrap regression touched production",
        )

    def test_release_stage_boundaries_are_runtime_dependencies(self) -> None:
        """The release DAG enforces Assemble → Verify → Publish at leaf level.

        Runtime eligibility is derived from leaf `depends_on_steps`; composite
        stage prose and `next_steps` cannot be the only barrier. Receipts below
        are synthetic TempStudio replay evidence and execute no release action.
        """
        studio = temp_studio.TempStudio(self.tmp).build()
        production_before = temp_studio.production_fingerprint()
        real_files = TOOLS.parent / "files"
        for uid in RELEASE_GRAPH_UIDS:
            shutil.copy2(real_files / f"{uid}.md", studio.files / f"{uid}.md")

        script = self.tmp / "release_stage_eligibility.py"
        script.write_text(
            "import importlib.util, json, sys\n"
            "from pathlib import Path\n"
            f"STUDIO = Path({str(studio.root)!r})\n"
            f"TOOLS = Path({str(studio.tools)!r})\n"
            "sys.path.insert(0, str(TOOLS))\n"
            "spec = importlib.util.spec_from_file_location(\n"
            "    'release_lock', TOOLS / 'tropo-lock-release-plan.py')\n"
            "release_lock = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(release_lock)\n"
            "spec = importlib.util.spec_from_file_location(\n"
            "    'runtime', TOOLS / '9e7003b1.py')\n"
            "runtime = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(runtime)\n"
            "files = STUDIO / 'vault' / 'files'\n"
            "runs = STUDIO / 'vault' / 'pipeline-runs'\n"
            "code, message = release_lock.lock_release_plan(\n"
            "    'b1a00001', 'talos-isolated', files, runs)\n"
            "assert code == 0, message\n"
            "plan = release_lock.read_entry('b1a00001', files)['frontmatter']\n"
            "activation_uid = plan['release_activation_uid']\n"
            "contract = STUDIO / 'contract-input.json'\n"
            "contract.write_text(json.dumps({\n"
            "    'skips_authorized_upfront': [],\n"
            "    'additional_steps_added': [],\n"
            "    'trust_overrides': {},\n"
            "    'human_instructions': '',\n"
            "}))\n"
            "runtime.action_bootstrap(activation_uid, str(contract), False)\n"
            "run = runtime.find_pipeline_run_for(activation_uid)\n"
            "folder = runtime.run_folder_for(run['frontmatter'])\n"
            "def eligible():\n"
            "    return runtime.action_resume_from_log(activation_uid)['eligible_steps']\n"
            "def verify(step_uid):\n"
            "    runtime.append_event(folder, runtime.make_event(\n"
            "        'verification_receipt', 'tempstudio-replay', step=step_uid,\n"
            "        trace_id=activation_uid, data={'verdict': 'pass'}))\n"
            "print('INITIAL', ','.join(eligible()))\n"
            "verify('f9365ede')\n"
            "print('AFTER_FAN_IN', ','.join(eligible()))\n"
            "verify('0cf86ea5')\n"
            "print('AFTER_DOC_TRIGGER', ','.join(eligible()))\n"
            "verify('4f64ec3c')\n"
            "print('AFTER_BRANCHES', ','.join(eligible()))\n"
            "verify('37996741')\n"
            "print('AFTER_NOTIFY', ','.join(eligible()))\n"
            "verify('2e9b1db7')\n"
            "print('BEFORE_PACKAGE', ','.join(eligible()))\n"
            "verify('8654900a')\n"
            "print('AFTER_PACKAGE', ','.join(eligible()))\n"
            "verify('4262d5fa')\n"
            "print('AFTER_FULL_VALIDATION', ','.join(eligible()))\n"
            "verify('a0f2bea8')\n"
            "print('AFTER_HARNESS', ','.join(eligible()))\n"
            "verify('bc6b17ec')\n"
            "print('AFTER_EXTERNAL', ','.join(eligible()))\n"
            "verify('c6b61fb9')\n"
            "print('AFTER_VERIFY_CHAIN', ','.join(eligible()))\n"
            "verify('3dd817cb')\n"
            "print('AFTER_PUBLISH', ','.join(eligible()))\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        production_after = temp_studio.production_fingerprint()
        self.assertEqual(
            temp_studio.diff_fingerprints(production_before, production_after),
            {},
            "the isolated stage-order regression touched production",
        )
        self.assertEqual(
            result.returncode,
            0,
            f"stdout={result.stdout}\nstderr={result.stderr[-2500:]}",
        )
        prefixes = {
            "INITIAL", "AFTER_FAN_IN", "AFTER_DOC_TRIGGER",
            "AFTER_BRANCHES", "AFTER_NOTIFY", "BEFORE_PACKAGE", "AFTER_PACKAGE",
            "AFTER_FULL_VALIDATION", "AFTER_HARNESS", "AFTER_EXTERNAL",
            "AFTER_VERIFY_CHAIN", "AFTER_PUBLISH",
        }
        observed = {
            key: value
            for line in result.stdout.splitlines()
            if " " in line
            for key, value in [line.split(" ", 1)]
            if key in prefixes
        }
        self.assertEqual(observed.get("INITIAL"), "f9365ede")
        self.assertEqual(observed.get("AFTER_FAN_IN"), "0cf86ea5,4f64ec3c")
        self.assertEqual(observed.get("AFTER_DOC_TRIGGER"), "4f64ec3c")
        self.assertEqual(observed.get("AFTER_BRANCHES"), "37996741")
        self.assertEqual(observed.get("AFTER_NOTIFY"), "2e9b1db7")
        self.assertEqual(observed.get("BEFORE_PACKAGE"), "8654900a")
        self.assertEqual(observed.get("AFTER_PACKAGE"), "4262d5fa")
        self.assertEqual(observed.get("AFTER_FULL_VALIDATION"), "a0f2bea8")
        self.assertEqual(observed.get("AFTER_HARNESS"), "bc6b17ec")
        self.assertEqual(observed.get("AFTER_EXTERNAL"), "c6b61fb9")
        self.assertEqual(observed.get("AFTER_VERIFY_CHAIN"), "3dd817cb")
        self.assertEqual(observed.get("AFTER_PUBLISH"), "")
        for point in (
            "INITIAL", "AFTER_FAN_IN", "AFTER_DOC_TRIGGER", "AFTER_BRANCHES",
            "AFTER_NOTIFY", "BEFORE_PACKAGE",
        ):
            self.assertNotIn(
                "4262d5fa", observed.get(point, ""),
                f"Verify shortcut became eligible at {point}",
            )
        for point in (
            "INITIAL", "AFTER_FAN_IN", "AFTER_DOC_TRIGGER", "AFTER_BRANCHES",
            "AFTER_NOTIFY", "BEFORE_PACKAGE", "AFTER_PACKAGE",
            "AFTER_FULL_VALIDATION", "AFTER_HARNESS", "AFTER_EXTERNAL",
        ):
            self.assertNotIn(
                "3dd817cb", observed.get(point, ""),
                f"Publish shortcut became eligible at {point}",
            )

    def test_the_order_of_members_survives_into_the_digest(self) -> None:
        """`dev_spec_uids` is ordered by contract, so the digest must honor it."""
        self.assertEqual(self._lock()[0], 0)
        forward = rl.read_entry("b1a00001", self.files)["frontmatter"]["fan_in_digest"]

        self.tearDown()
        self.setUp()
        plan = self.files / "b1a00001.md"
        plan.write_text(plan.read_text().replace(
            "  - 5ec00001\n  - 5ec00002", "  - 5ec00002\n  - 5ec00001"))
        self.assertEqual(self._lock()[0], 0)
        reversed_digest = rl.read_entry("b1a00001", self.files)["frontmatter"]["fan_in_digest"]

        self.assertNotEqual(forward, reversed_digest,
                            "member order does not reach the fan-in digest")

    # ---------------------------------------------------------------- refusals

    def _assert_refuses_without_touching_anything(self, expect: str) -> None:
        before = self._snapshot()
        code, message = self._lock()
        self.assertEqual(code, 1, f"expected refusal, got {code}: {message}")
        self.assertIn(expect, message)
        self.assertEqual(before, self._snapshot(),
                         "a refusal changed the studio; AC4 requires zero partial state")

    def test_an_unfinished_member_refuses_and_writes_nothing(self) -> None:
        path = self.files / "5ec00002.md"
        path.write_text(path.read_text().replace("status: done", "status: active"))
        self._assert_refuses_without_touching_anything("not 'done'")

    def test_a_member_reserved_by_another_live_plan_refuses(self) -> None:
        self._write("b1a00002", "---\n" + "\n".join([
            "uid: b1a00002", "type: release-plan", "title: rival",
            "status: locked", "dev_spec_uids:", "  - 5ec00002",
        ]) + "\n---\n\n# rival\n")
        self._assert_refuses_without_touching_anything("already reserved")

    def test_a_member_whose_run_never_closed_refuses(self) -> None:
        """No dev_closed event means nothing for the row to bind."""
        (self.runs / "dev-run-0bb00001" / "events.jsonl").unlink()
        self._assert_refuses_without_touching_anything("carries no CANONICAL")

    def test_a_member_that_closed_against_two_trees_refuses(self) -> None:
        """No single tree is THE tested one, so the row cannot name it."""
        self._close_receipt("0bb00001", count=2)
        self._assert_refuses_without_touching_anything("different trees")

    def test_a_hand_written_frontmatter_sha_is_not_evidence(self) -> None:
        """NO-GO item 3, stated as a test.

        The first version searched spec, then activation, then run, for any of
        final_commit / tested_final_commit / tested_sha and took the first hit.
        A dev-spec hand-edited with a plausible SHA satisfied it. Provenance now
        comes from the close that actually happened, so decorating the spec
        while deleting the receipt must still refuse.
        """
        (self.runs / "dev-run-0bb00001" / "events.jsonl").unlink()
        path = self.files / "5ec00001.md"
        path.write_text(path.read_text().replace(
            "status: done", f"status: done\nfinal_commit: '{TESTED_SHA}'"))
        self._assert_refuses_without_touching_anything("carries no CANONICAL")

    def test_the_row_carries_the_sha_the_receipt_recorded(self) -> None:
        """Control: the receipt is genuinely the source, not just a gate."""
        other = "9" * 40
        self._close_receipt("0bb00002", sha=other)
        self.assertEqual(self._lock()[0], 0)
        fm = rl.read_entry("b1a00001", self.files)["frontmatter"]
        rows = json.loads((self.tmp / fm["fan_in_manifest_ref"]).read_text())["rows"]
        by_spec = {r["dev_spec_uid"]: r["tested_final_commit"] for r in rows}
        self.assertEqual(by_spec["5ec00001"], TESTED_SHA)
        self.assertEqual(by_spec["5ec00002"], other)

    def test_a_member_with_empty_acceptance_evidence_refuses(self) -> None:
        path = self.files / "5ec00001.md"
        path.write_text(path.read_text().replace(
            "acceptance_evidence:\n  - e0000001", "acceptance_evidence: []"))
        self._assert_refuses_without_touching_anything("acceptance_evidence")

    def test_evidence_that_does_not_resolve_refuses(self) -> None:
        (self.files / "e0000001.md").unlink()
        self._assert_refuses_without_touching_anything("does not resolve")

    def test_a_plan_with_no_members_refuses(self) -> None:
        path = self.files / "b1a00001.md"
        path.write_text(path.read_text().replace(
            "dev_spec_uids:\n  - 5ec00001\n  - 5ec00002", "dev_spec_uids: []"))
        self._assert_refuses_without_touching_anything("lists no dev_spec_uids")

    def test_an_already_locked_plan_refuses_rather_than_opening_a_second_run(self) -> None:
        self.assertEqual(self._lock()[0], 0)
        before = self._snapshot()
        code, message = self._lock()
        self.assertEqual(code, 1, message)
        self.assertIn("already locked", message)
        self.assertEqual(before, self._snapshot(),
                         "a second lock attempt mutated a locked plan")

    def test_a_dead_rival_plan_does_not_block(self) -> None:
        """Control for the reservation refusal above."""
        self._write("b1a00002", "---\n" + "\n".join([
            "uid: b1a00002", "type: release-plan", "title: cancelled rival",
            "status: cancelled", "dev_spec_uids:", "  - 5ec00002",
        ]) + "\n---\n\n# rival\n")
        self.assertEqual(self._lock()[0], 0)

    def test_the_lock_writes_an_activation_root_and_a_declaration_snapshot(self) -> None:
        """NO-GO item 4. Without a root, Rule 12 has nothing to archive at close;
        without declarations, the run has no snapshot and would fall back to the
        definition of the day — the §1 contract swap, from the ignition itself."""
        self.assertEqual(self._lock()[0], 0)
        fm = rl.read_entry("b1a00001", self.files)["frontmatter"]
        activation = rl.read_entry(fm["release_activation_uid"], self.files)["frontmatter"]

        root = rl.read_entry(
            activation["activation_root_project"], self.files)["frontmatter"]
        self.assertEqual(root["type"], "project")
        self.assertEqual(root["activated_by_pipeline"], rl.RELEASE_PIPELINE_UID)

        snapshot = json.loads(
            (self.runs / f"release-pipeline-{fm['release_pipeline_run_uid']}"
             f"-{time.strftime('%Y-%m-%d')}" / "declaration-snapshot.json").read_text())
        self.assertEqual(snapshot["declared_steps"], ["57e90001"])
        self.assertEqual(len(snapshot["declaration_digest"]), 64)

    def test_the_run_records_the_roots_real_version_not_a_hardcoded_one(self) -> None:
        """The fixture root is 1.0.0; the first version stamped 2.0 regardless."""
        self.assertEqual(self._lock()[0], 0)
        fm = rl.read_entry("b1a00001", self.files)["frontmatter"]
        run = rl.read_entry(fm["release_pipeline_run_uid"], self.files)["frontmatter"]
        self.assertEqual(str(run["pipeline_version"]), "1.0.0")

    def test_a_draft_release_root_cannot_be_ignited(self) -> None:
        """Which is the live state of 634913c2 today."""
        path = self.files / f"{rl.RELEASE_PIPELINE_UID}.md"
        path.write_text(path.read_text().replace("status: active", "status: draft"))
        self._assert_refuses_without_touching_anything("draft")

    def test_the_locked_plan_has_no_duplicate_yaml_keys(self) -> None:
        """NO-GO item 5. YAML resolves duplicates by taking the last, so a plan
        can display one member list and be READ as another."""
        self.assertEqual(self._lock()[0], 0)
        raw = (self.files / "b1a00001.md").read_text()
        head = raw.split("---")[1]
        keys = [line.split(":")[0] for line in head.splitlines()
                if line and not line.startswith((" ", "\t", "-"))]
        self.assertEqual(sorted(keys), sorted(set(keys)),
                         f"duplicate top-level keys: {sorted(k for k in keys if keys.count(k) > 1)}")
        self.assertEqual(head.count("dev_spec_uids:"), 1)

    def test_the_lock_records_its_own_provenance(self) -> None:
        self.assertEqual(self._lock()[0], 0)
        fm = rl.read_entry("b1a00001", self.files)["frontmatter"]
        self.assertEqual(fm["locked_by"], "talos")
        self.assertTrue(fm.get("locked_at"))

    def test_the_duplicate_key_guard_refuses_when_reached(self) -> None:
        """Tested directly, because nothing reaches it any more.

        A mutation removing this guard survived the whole suite: with the
        block-aware patcher fixed, no duplicate is produced, so the guard is
        defence-in-depth against a future regression in the patcher rather than
        a live gate. That is worth keeping and worth testing on its own terms —
        an untested guard is a comment.
        """
        with self.assertRaises(rl.LockRefused) as caught:
            rl._refuse_duplicate_keys("uid: b1a00001\nstatus: locked\nstatus: done\n")
        self.assertIn("duplicate key", str(caught.exception))
        self.assertIn("status", str(caught.exception))

    def test_the_duplicate_key_guard_passes_clean_frontmatter(self) -> None:
        """Control: a guard that refuses everything guards nothing."""
        rl._refuse_duplicate_keys("uid: b1a00001\nstatus: locked\nowner: talos\n")

    def test_the_patcher_removes_a_block_valued_key_entirely(self) -> None:
        """The bug itself, pinned at the unit.

        `^key:\\s` never matches `dev_spec_uids:` — there is nothing after the
        colon — so the old key survived and a second one was appended, and the
        indented items would have been orphaned even if it had matched.
        """
        raw = ("---\nuid: b1a00001\ntype: release-plan\nstatus: specify\n"
               "dev_spec_uids:\n  - 5ec00009\nowner: argus\n---\n\n# plan\n")
        out = rl._patch_plan_frontmatter(raw, {
            "dev_spec_uids": ["5ec00001"], "fan_in_manifest_ref": "x",
            "fan_in_digest": "d", "release_activation_uid": "a",
            "release_pipeline_run_uid": "r", "locked_by": "talos",
            "locked_at": "2026-08-10"})
        head = out.split("---")[1]
        self.assertEqual(head.count("dev_spec_uids:"), 1)
        self.assertNotIn("5ec00009", head, "the superseded member list survived")
        self.assertIn("owner: argus", head, "an unmanaged key was dropped")

    def test_a_stale_applying_journal_is_recovered_before_planning(self) -> None:
        """NO-GO item 2: recovery has to have a CALLER, inside the same span.

        `recover_incomplete` existed and nothing invoked it, so a crashed prior
        attempt left half-written substrate that the reservation scan would then
        read as real. A mutation removing the call survived the suite until this
        test existed, which is the honest measure of how covered it was.
        """
        orphan = self.files / "0dd00001.md"
        orphan.write_text("---\nuid: 0dd00001\ntype: note\n---\n\n# orphan\n")
        lt.LOCK_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        (lt.LOCK_JOURNAL_DIR / "release-plan-lock-0dd0dead.json").write_text(
            _journalled({
                "kind": "release-plan-lock", "subject_uid": "0dd0dead",
                "actor": "talos", "state": "applying", "plan_digest": "x" * 64,
                "operations": [{
                    "op": "create", "path": str(orphan), "governed": False,
                    # The recorded digest must match the recorded content, or
                    # strict validation refuses the journal as corrupt — which
                    # it should, and which this fixture is not testing.
                    "sha256": lt.sha256_text(orphan.read_text()),
                    "pre_existed": False,
                    "post_content": orphan.read_text(),
                }],
            }))

        self.assertEqual(self._lock()[0], 0)
        self.assertFalse(
            orphan.exists(),
            "the crashed transaction's artifact survived; recovery did not run "
            "before planning")

    def test_an_unrecoverable_journal_blocks_the_lock(self) -> None:
        """Divergence means stop, not proceed-and-hope.

        If a crashed transaction's files match neither its pre- nor post-state,
        someone has touched them since. Planning on top of that is planning
        against substrate that is still half-written.
        """
        orphan = self.files / "0dd00002.md"
        orphan.write_text("---\nuid: 0dd00002\ntype: note\n---\n\n# edited by hand\n")
        lt.LOCK_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        (lt.LOCK_JOURNAL_DIR / "release-plan-lock-0dd0beef.json").write_text(
            _journalled({
                "kind": "release-plan-lock", "subject_uid": "0dd0beef",
                "actor": "talos", "state": "applying", "plan_digest": "x" * 64,
                "operations": [{
                    "op": "create", "path": str(orphan), "governed": False,
                    "sha256": lt.sha256_text("something else entirely\n"),
                    "pre_existed": False,
                    "post_content": "something else entirely\n",
                }],
            }))

        before = self._snapshot()
        code, message = self._lock()
        self.assertEqual(code, 2, message)
        self.assertIn("cannot be recovered automatically", message)
        self.assertEqual(before, self._snapshot(),
                         "the blocked lock still changed the studio")

    # ------------------------------------------------- blocker-3 adversarial plants

    def test_a_forged_bare_close_line_is_not_a_receipt(self) -> None:
        """The shape the first version accepted, planted deliberately.

        `{"event": "dev_closed", "tested_sha": ...}` in any jsonl under the run
        folder used to be sufficient. Anyone can type that line.
        """
        folder = self.runs / "dev-run-0bb00001"
        (folder / "events.jsonl").write_text(json.dumps({
            "event": "dev_closed", "trace_id": "ac700001",
            "data": {"tested_sha": TESTED_SHA},
        }) + "\n", encoding="utf-8")
        self._assert_refuses_without_touching_anything("does not declare itself")

    def test_a_receipt_from_ANOTHER_run_does_not_satisfy_this_one(self) -> None:
        """Wrong trace. Without this check a receipt copied from any other cycle
        closes this one."""
        self._close_receipt("0bb00001")
        folder = self.runs / "dev-run-0bb00001"
        body = json.loads(folder.joinpath("events.jsonl").read_text().strip())
        body["trace_id"] = "ac7000ff"
        folder.joinpath("events.jsonl").write_text(json.dumps(body) + "\n")
        self._assert_refuses_without_touching_anything("traced to")

    def test_a_receipt_whose_identity_disagrees_is_refused(self) -> None:
        """Each link is checked against the member being fanned in, so a receipt
        naming a different spec cannot vouch for this one."""
        self._close_receipt("0bb00001", dev_spec_uid="5ec000ff")
        self._assert_refuses_without_touching_anything("identity disagrees")

    def test_a_receipt_naming_an_unresolvable_root_is_refused(self) -> None:
        self._close_receipt("0bb00001", activation_root_uid="a00000ff")
        self._assert_refuses_without_touching_anything("does not resolve")

    def test_a_receipt_with_a_failing_verdict_is_refused(self) -> None:
        """A close that happened is not a close that PASSED."""
        self._close_receipt("0bb00001", verdict="incomplete")
        self._assert_refuses_without_touching_anything("not a passing close")

    def test_two_canonical_receipts_for_one_run_are_refused(self) -> None:
        """A cycle closes once. Duplicates make it undecidable which governs."""
        self._close_receipt("0bb00001", count=2)
        self._assert_refuses_without_touching_anything("different trees")

    def test_two_identical_receipts_are_still_refused_as_duplicates(self) -> None:
        """Even agreeing duplicates mean the close ran twice."""
        folder = self.runs / "dev-run-0bb00001"
        self._close_receipt("0bb00001")
        line = folder.joinpath("events.jsonl").read_text().strip()
        folder.joinpath("events.jsonl").write_text(line + "\n" + line + "\n")
        self._assert_refuses_without_touching_anything("closes ONCE")

    def test_untyped_acceptance_evidence_is_refused(self) -> None:
        """A note has no verdict, so it cannot attest that anything passed."""
        self._write("e0000001", _entry("e0000001", type="note", title="looks fine"))
        self._assert_refuses_without_touching_anything("carries no verdict")

    def test_typed_but_FAILING_acceptance_evidence_is_refused(self) -> None:
        """The case a resolves-only check passed: a real completion report whose
        verdict is fail."""
        self._write("e0000001", _entry("e0000001", type="completion-report",
                                       title="it failed", status="failed"))
        self._assert_refuses_without_touching_anything("is not a pass")

    def test_the_control_a_canonical_receipt_and_typed_evidence_lock(self) -> None:
        """Without this every plant above passes for a gate that refuses all."""
        self.assertEqual(self._lock()[0], 0)

    def test_the_reservation_scan_reads_files_not_the_index(self) -> None:
        """A gate that depends on a rebuild having run is not a gate.

        The index is gitignored per-machine derived state, so a reservation
        check that consulted it would pass or fail depending on how recently
        someone ran a rebuild.
        """
        source = (TOOLS / "tropo-lock-release-plan.py").read_text(encoding="utf-8")
        body = source[source.index("def all_release_plans"):]
        body = body[: body.index("\ndef ", 1)]
        self.assertIn("glob", body)
        self.assertNotIn("00-index", body)


if __name__ == "__main__":
    unittest.main()
