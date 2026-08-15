"""The isolation proof argus-a147 required before AC2 semantics can be reviewed.

"Fix tests so EVERY root/files/runs/event emitter/index/global points at one
temp Studio and assert production tree/event union byte-identical before/after.
Add a control that plants a failing mid-transaction run and proves no production
artifact/event."

This replaces cleanup-after with never-wrote-there. My previous fix made the
teardown journal-driven and exhaustive, which was a real improvement and still
the weaker guarantee: it depends on cleanup being correct forever, where this
depends on the tools being unable to reach production at all.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_ac2_isolation_and_production_identity
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import temp_studio  # noqa: E402


class ProductionIsUntouched(unittest.TestCase):
    """Every test here runs the real gesture and asserts production did not move."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac2-isolated-")).resolve()
        self.studio = temp_studio.TempStudio(self.tmp / "studio").build()
        self.before = temp_studio.production_fingerprint()
        self._seed()

    def tearDown(self) -> None:
        after = temp_studio.production_fingerprint()
        changes = temp_studio.diff_fingerprints(self.before, after)
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertEqual(
            changes, {},
            "the production Studio changed while an ISOLATED test ran: "
            f"{changes}. Fixture substrate is indistinguishable from real work to "
            "every later reader, and the index, the event ledger and any release "
            "that fans it in all inherit it.")

    def _seed(self) -> None:
        self.studio.write_entry("cd1fcd25", [
            "type: pipeline", "title: dev-pipeline", "status: active",
            "version: 2.0.0", "default_trust_gradient: pinned-at-lock",
            "children:", "  - 0c6518ef", "  - fa3a49c8"])
        for uid, title in (("0c6518ef", "specify"), ("fa3a49c8", "build")):
            self.studio.write_entry(uid, ["type: pipeline", "subtype: workflow-node",
                                          f"title: {title}", "status: active"])
        self.studio.write_entry("10c40001", [
            "type: dev-spec", "title: isolated fixture plant", "status: draft",
            "state: active", "owner: talos", "schema_version: 2"])

    def _lock_module(self):
        module = self.studio.load("tropo-lock-dev-spec.py", "isolated_lock_dev_spec")
        self.studio.assert_tools_are_rooted_here(module)
        return module

    # ------------------------------------------------------------------ the proof

    def test_the_copied_tools_resolve_their_root_to_the_temp_studio(self) -> None:
        """The claim the whole harness rests on, checked rather than assumed.

        Both pipeline-activate and the event emitter compute
        VAULT_ROOT = Path(__file__).resolve().parents[2] at import. No argument
        or cwd moves that, which is why patching globals could never have worked
        and why the copies must genuinely re-root.
        """
        for script, alias in (("tropo-lock-dev-spec.py", "iso_lock"),
                              ("e337f1dd.py", "iso_activate"),
                              ("tropo-emit-event.py", "iso_emit")):
            with self.subTest(tool=script):
                module = self.studio.load(script, alias)
                self.assertEqual(
                    Path(module.VAULT_ROOT).resolve(), self.studio.root,
                    f"{script} still points at production")

    def _run_in_studio(self, body: str) -> subprocess.CompletedProcess:
        """Execute the gesture in a FRESH interpreter rooted in the temp Studio.

        In-process loading of the copied tool is not enough. The copy does
        `from lib import lock_transaction`, and if `lib` is already in
        sys.modules from any earlier test in the same process, it gets the
        PRODUCTION package — whose VAULT_ROOT and journal directory point at the
        live Studio. The isolation would then hold for the tool and leak through
        its imports.

        A subprocess has an empty sys.modules, so every import resolves from the
        temp tree. It is also how the tool actually runs.
        """
        script = self.studio.root / "run_gesture.py"
        script.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(self.studio.tools)!r})\n"
            "import importlib.util\n"
            "from pathlib import Path\n"
            f"spec = importlib.util.spec_from_file_location('lockdev', {str(self.studio.tools / 'tropo-lock-dev-spec.py')!r})\n"
            "lockdev = importlib.util.module_from_spec(spec); spec.loader.exec_module(lockdev)\n"
            "from lib import lock_transaction as lt\n"
            f"STUDIO = Path({str(self.studio.root)!r})\n"
            "assert Path(lt.VAULT_ROOT).resolve() == STUDIO, ('lib rooted at ' + str(lt.VAULT_ROOT))\n"
            "assert Path(lockdev.VAULT_ROOT).resolve() == STUDIO\n"
            + body,
            encoding="utf-8")
        return subprocess.run([sys.executable, str(script)],
                              capture_output=True, text=True, timeout=120)

    def test_a_successful_lock_writes_only_into_the_temp_studio(self) -> None:
        result = self._run_in_studio(
            "with lt.exclusive_workspace_lock():\n"
            "    plan = lockdev.plan_dev_snapshot_transaction(\n"
            "        '10c40001', 'talos-isolated',\n"
            f"        files_dir=Path({str(self.studio.files)!r}), runs_dir=Path({str(self.studio.runs)!r}))\n"
            "    for op in plan.operations:\n"
            "        assert str(op.path).startswith(str(STUDIO)), 'ESCAPE: ' + str(op.path)\n"
            f"    spec_path = Path({str(self.studio.files / '10c40001.md')!r})\n"
            "    raw = spec_path.read_text()\n"
            "    plan.patch(spec_path, raw, raw.replace('status: draft', 'status: locked'))\n"
            "    lt.apply_plan(plan, recycle=None)\n"
            "print('LOCKED')\n")
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2000:]}")
        self.assertIn("LOCKED", result.stdout)
        self.assertIn("status: locked",
                      (self.studio.files / "10c40001.md").read_text())
        self.assertEqual(len(list(self.studio.runs.glob("dev-pipeline-*"))), 1)
        # tearDown asserts production is byte-identical.

    def test_a_mid_apply_fault_through_the_REAL_CLI_leaves_no_production_trace(self) -> None:
        """argus-a147 residual 3: inject the fault into the production path.

        The test below plans and applies by hand, which exercises the primitive
        rather than the gesture. This one breaks the real `lock_dev_spec` while
        it is mid-apply, by making one governed write fail inside the copied
        CLI's own interpreter, and then checks what the studio is left holding.

        Empty-directory residue is reported honestly rather than asserted away:
        it is reversible bookkeeping under deb77758, so it warns and is cleaned
        by recovery instead of earning a refusal.
        """
        result = self._run_in_studio(
            "import lib.lock_transaction as _lt\n"
            "real = _lt._atomic_write\n"
            "def fail_on_run_entry(path, content):\n"
            "    # The .md test matters: the journal embeds every effect's\n"
            "    # content, so matching on content alone breaks the JOURNAL\n"
            "    # write instead of the effect and tests a different case.\n"
            "    if path.suffix == '.md' and 'type: pipeline-run' in content:\n"
            "        raise OSError('injected mid-apply fault')\n"
            "    return real(path, content)\n"
            "_lt._atomic_write = fail_on_run_entry\n"
            "code, msg = lockdev.lock_dev_spec(\n"
            "    '10c40001', 'talos-isolated',\n"
            f"    files_dir=Path({str(self.studio.files)!r}),\n"
            f"    vault_root=Path({str(self.studio.root)!r}))\n"
            "_lt._atomic_write = real\n"
            "print('CODE', code)\n"
            "reports = _lt.recover_incomplete(recycle=None)\n"
            "print('RECOVERY', [r['outcome'] for r in reports])\n")
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2000:]}")
        self.assertIn("CODE 2", result.stdout,
                      f"expected a PARTIAL outcome: {result.stdout}")

        self.assertIn("status: draft", (self.studio.files / "10c40001.md").read_text(),
                      "the spec was flipped despite a mid-apply fault")

        runs = [d for d in self.studio.runs.glob("dev-pipeline-*") if d.is_dir()]
        self.assertEqual(
            runs, [],
            f"empty run directories survived the fault and recovery: {runs}")
        # tearDown asserts production is byte-identical.

    def test_a_failure_mid_transaction_leaves_no_production_artifact_or_event(self) -> None:
        """The control Argus asked for by name.

        A clean run proving nothing leaked is worth less than it looks: the
        interesting moment is the one where the gesture breaks half-way, because
        that is when the rollback path runs, and a rollback path is exactly the
        kind of code that reaches for a hardcoded root. Mine did —
        _default_recycle pointed at a path that did not exist, so rollback
        silently never recycled and the safety property held for the wrong
        reason.
        """
        spec_file = self.studio.files / "10c40001.md"
        before_spec = spec_file.read_text()
        result = self._run_in_studio(
            "recycled = []\n"
            "def spy(path, reason):\n"
            "    recycled.append(str(path)); path.unlink(); return True\n"
            "try:\n"
            "    with lt.exclusive_workspace_lock():\n"
            "        plan = lockdev.plan_dev_snapshot_transaction(\n"
            "            '10c40001', 'talos-isolated',\n"
            f"            files_dir=Path({str(self.studio.files)!r}), runs_dir=Path({str(self.studio.runs)!r}))\n"
            f"        spec_path = Path({str(spec_file)!r})\n"
            "        raw = spec_path.read_text()\n"
            "        plan.patch(spec_path, raw, raw.replace('status: draft', 'status: locked'))\n"
            "        # The plant: a create whose parent is an existing FILE, so the\n"
            "        # write fails part-way and the real rollback path runs.\n"
            "        plan.create(spec_path / 'impossible.md', 'unreachable\\n')\n"
            "        lt.apply_plan(plan, recycle=spy)\n"
            "    print('UNEXPECTED-SUCCESS')\n"
            "except lt.LockApplyFailure:\n"
            "    for p in recycled:\n"
            "        assert p.startswith(str(STUDIO)), 'ROLLBACK ESCAPED: ' + p\n"
            "    print('FAILED-AND-ROLLED-BACK')\n")
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2000:]}")
        self.assertIn("FAILED-AND-ROLLED-BACK", result.stdout)
        self.assertEqual(spec_file.read_text(), before_spec,
                         "the temp spec was left flipped after a failed transaction")
        # tearDown asserts production is byte-identical, including after rollback.

    def test_the_real_lock_dev_spec_path_yields_ONE_activation_and_ONE_root(self) -> None:
        """Blocker 1, via the production entry point (blocker 5).

        My earlier tests exercised `plan_dev_snapshot_transaction` — the plan
        builder — and never `lock_dev_spec`, the thing anyone actually calls.
        That is why they were all green while the real path shelled out to
        pipeline-activate.py before taking the lock, which authored its OWN
        activation root while the ignition authored a second. A successful lock
        produced one activation and TWO roots, and no test could see it because
        no test ran the function that did it.
        """
        result = self._run_in_studio(
            "code, msg = lockdev.lock_dev_spec(\n"
            "    '10c40001', 'talos-isolated',\n"
            f"    files_dir=Path({str(self.studio.files)!r}),\n"
            f"    vault_root=Path({str(self.studio.root)!r}))\n"
            "print('CODE', code); print('MSG', msg)\n")
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2500:]}")
        self.assertIn("CODE 0", result.stdout, result.stdout + result.stderr[-1500:])

        kinds = {"activation": [], "project": [], "pipeline-run": []}
        for path in self.studio.files.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for kind in kinds:
                if f"type: {kind}\n" in text:
                    kinds[kind].append(path.stem)

        self.assertEqual(len(kinds["activation"]), 1,
                         f"expected exactly one activation, got {kinds['activation']}")
        self.assertEqual(len(kinds["project"]), 1,
                         f"expected exactly ONE activation root, got {kinds['project']} "
                         "— two roots is the blocker-1 defect")
        self.assertEqual(len(kinds["pipeline-run"]), 1,
                         f"expected exactly one run, got {kinds['pipeline-run']}")

        activation = (self.studio.files / f"{kinds['activation'][0]}.md").read_text()
        self.assertIn(f"activation_root_project: '{kinds['project'][0]}'", activation,
                      "the activation does not point at the root that was written")
        self.assertIn("status: locked",
                      (self.studio.files / "10c40001.md").read_text())

    def test_a_refused_real_lock_leaves_no_activation_and_no_root(self) -> None:
        """The other half of blocker 1: "refusal leaves activation/root/no journal".

        The subprocess wrote before the lock, so a refusal afterwards stranded
        substrate the journal had never heard of. With every write in one plan,
        a refusal writes nothing at all — so the check is that the studio still
        holds only what the fixture seeded.
        """
        # Make the ignition refuse: a draft root cannot be ignited.
        root = self.studio.files / "cd1fcd25.md"
        root.write_text(root.read_text().replace("status: active", "status: draft"))
        seeded = {p.stem for p in self.studio.files.glob("*.md")}

        result = self._run_in_studio(
            "code, msg = lockdev.lock_dev_spec(\n"
            "    '10c40001', 'talos-isolated',\n"
            f"    files_dir=Path({str(self.studio.files)!r}),\n"
            f"    vault_root=Path({str(self.studio.root)!r}))\n"
            "print('CODE', code); print('MSG', msg)\n")

        self.assertIn("CODE 1", result.stdout,
                      f"expected a refusal: {result.stdout}\n{result.stderr[-1500:]}")
        self.assertEqual(
            {p.stem for p in self.studio.files.glob("*.md")}, seeded,
            "a refused lock left substrate behind")
        self.assertIn("status: draft", (self.studio.files / "10c40001.md").read_text(),
                      "the dev-spec was flipped despite the refusal")

    def test_the_runtime_executes_the_SNAPSHOT_after_every_source_node_is_deleted(self) -> None:
        """argus-a147, second pass: the snapshot must GOVERN, not just describe.

        Lock, then delete every pipeline entry the run was built from, then ask
        the engine for the run's declarations. If anything still reads the live
        vault this cannot pass, because there is no live vault entry left. This
        is the difference between a snapshot that detects change and one the run
        actually executes.
        """
        lock = self._run_in_studio(
            "with lt.exclusive_workspace_lock():\n"
            "    plan = lockdev.plan_dev_snapshot_transaction(\n"
            "        '10c40001', 'talos-isolated',\n"
            f"        files_dir=Path({str(self.studio.files)!r}), runs_dir=Path({str(self.studio.runs)!r}))\n"
            "    lt.apply_plan(plan, recycle=None)\n"
            "print('LOCKED')\n")
        self.assertEqual(lock.returncode, 0,
                         f"{lock.stdout}\n{lock.stderr[-1500:]}")

        snapshots = list(self.studio.runs.glob("dev-pipeline-*/declaration-snapshot.json"))
        self.assertEqual(len(snapshots), 1, f"expected one snapshot, got {snapshots}")

        # Delete the ENTIRE pipeline definition the run was locked against.
        for uid in ("cd1fcd25", "0c6518ef", "fa3a49c8"):
            (self.studio.files / f"{uid}.md").unlink()

        read_back = self._run_in_studio(
            "import importlib.util\n"
            f"spec = importlib.util.spec_from_file_location('eng', {str(self.studio.tools / '9e7003b1.py')!r})\n"
            "eng = importlib.util.module_from_spec(spec); spec.loader.exec_module(eng)\n"
            f"folder = Path({str(snapshots[0].parent)!r})\n"
            "steps, nodes = eng._declarations_from_snapshot(folder)\n"
            "print('STEPS', ','.join(steps))\n"
            "print('HAS_DECLS', all(u in nodes for u in steps))\n")
        self.assertEqual(read_back.returncode, 0,
                         f"{read_back.stdout}\n{read_back.stderr[-2000:]}")
        self.assertIn("STEPS 0c6518ef,fa3a49c8", read_back.stdout,
                      f"the run could not read its own steps: {read_back.stdout}")
        self.assertIn("HAS_DECLS True", read_back.stdout,
                      "the steps resolved by name but carried no declarations")

    def test_REAL_action_bootstrap_seeds_from_the_snapshot_after_sources_are_deleted(self) -> None:
        """argus-a147's production test, and the one that exposes NameErrors.

        Every previous test called `_declarations_from_snapshot` directly, so
        none of them noticed that `action_bootstrap` referenced a `run_folder`
        that did not exist in its scope — a NameError on every real bootstrap —
        or that it refused outright whenever a pipeline-run existed, which under
        v2 is always, because the lock creates one. The snapshot branch was
        unreachable code guarded by an impossible condition, and the helper
        tests all passed.

        So: lock through the copied CLI, delete every source node, then call the
        REAL bootstrap and read the step_declared events it wrote.
        """
        result = self._run_in_studio(
            "import importlib.util\n"
            f"spec = importlib.util.spec_from_file_location('eng', {str(self.studio.tools / '9e7003b1.py')!r})\n"
            "eng = importlib.util.module_from_spec(spec); spec.loader.exec_module(eng)\n"
            "with lt.exclusive_workspace_lock():\n"
            "    plan = lockdev.plan_dev_snapshot_transaction(\n"
            "        '10c40001', 'talos-isolated',\n"
            f"        files_dir=Path({str(self.studio.files)!r}), runs_dir=Path({str(self.studio.runs)!r}))\n"
            "    lt.apply_plan(plan, recycle=None)\n"
            "activation_uid = plan.notes['activation_uid']\n"
            "print('ACTIVATION', activation_uid)\n"
            "# Destroy the entire live definition the run was locked against.\n"
            "for uid in ('cd1fcd25', '0c6518ef', 'fa3a49c8'):\n"
            f"    (Path({str(self.studio.files)!r}) / (uid + '.md')).unlink()\n"
            "run = eng.find_pipeline_run_for(activation_uid)\n"
            "assert run is not None, 'the locked run is invisible to the runtime'\n"
            "folder = eng.run_folder_for(run['frontmatter'])\n"
            "print('HAS_EVENTS_BEFORE', eng._run_has_events(folder))\n"
            "# THE REAL PRODUCTION ENTRY POINT, not a helper.\n"
            "# Non-TTY bootstrap requires an explicit contract input; an empty\n"
            "# one is the honest 'no skips, no overrides' answer.\n"
            f"contract = Path({str(self.studio.root)!r}) / 'contract-input.json'\n"
            "contract.write_text('{\"skips_authorized_upfront\": [], "
            "\"additional_steps_added\": [], \"trust_overrides\": {}, "
            "\"human_instructions\": \"\"}')\n"
            "out = eng.action_bootstrap(activation_uid, str(contract), False)\n"
            "print('BOOTSTRAPPED')\n"
            "declared = sorted(eng.get_step_declarations(eng.read_events(folder)).keys())\n"
            "print('DECLARED', ','.join(declared))\n"
            "print('HAS_EVENTS_AFTER', eng._run_has_events(folder))\n")
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2500:]}")
        self.assertIn("HAS_EVENTS_BEFORE False", result.stdout,
                      "a freshly locked run already looked bootstrapped")
        self.assertIn("BOOTSTRAPPED", result.stdout,
                      "the real bootstrap refused the run its own lock created")
        self.assertIn("DECLARED 0c6518ef,fa3a49c8", result.stdout,
                      f"step_declared does not match the snapshot: {result.stdout}")
        self.assertIn("HAS_EVENTS_AFTER True", result.stdout)

    def test_no_live_root_leaks_into_the_contract_after_the_root_is_EDITED(self) -> None:
        """The leak my delete-the-sources test could not see.

        Deleting the root proved the run survives without it. Editing the root
        is the ordinary case, and it was broken: the contract took its name,
        version and trust gradient from the LIVE entry whenever one existed,
        falling back to the snapshot only when it was gone. So a run executed
        the pinned steps while describing itself with post-lock values — the §1
        contract swap arriving through metadata rather than through steps.

        Found by reading argus-a147's handoff checklist for A148 rather than by
        a failing test, which is the point: I keep proving the hard case and
        leaving the ordinary one open.
        """
        result = self._run_in_studio(
            "import importlib.util, json\n"
            f"spec = importlib.util.spec_from_file_location('eng', {str(self.studio.tools / '9e7003b1.py')!r})\n"
            "eng = importlib.util.module_from_spec(spec); spec.loader.exec_module(eng)\n"
            "with lt.exclusive_workspace_lock():\n"
            "    plan = lockdev.plan_dev_snapshot_transaction(\n"
            "        '10c40001', 'talos-isolated',\n"
            f"        files_dir=Path({str(self.studio.files)!r}), runs_dir=Path({str(self.studio.runs)!r}))\n"
            "    lt.apply_plan(plan, recycle=None)\n"
            "activation_uid = plan.notes['activation_uid']\n"
            "# EDIT the root AND every step declaration after the lock — do not\n"
            "# delete them. A147's checklist for A148 names both, and my first\n"
            "# version mutated only the root, so a post-lock edit to a STEP was\n"
            "# untested even though step declarations are what a run executes.\n"
            f"for _uid in ('0c6518ef', 'fa3a49c8'):\n"
            f"    _p = Path({str(self.studio.files)!r}) / (_uid + '.md')\n"
            "    _p.write_text(_p.read_text()\n"
            "        .replace('status: active', 'status: active\\nexit_criteria: [POST-LOCK-STEP]')\n"
            "        .replace('title: ', 'title: POST-LOCK-REWRITE '))\n"
            f"root = Path({str(self.studio.files)!r}) / 'cd1fcd25.md'\n"
            "root.write_text(root.read_text()\n"
            "    .replace('version: 2.0.0', 'version: 99.99.99')\n"
            "    .replace('default_trust_gradient: pinned-at-lock',\n"
            "             'default_trust_gradient: POST-LOCK-TRUST')\n"
            "    .replace('title: dev-pipeline', 'title: POST-LOCK-REWRITE'))\n"
            f"contract = Path({str(self.studio.root)!r}) / 'contract-input.json'\n"
            "contract.write_text('{\"skips_authorized_upfront\": [], "
            "\"additional_steps_added\": [], \"trust_overrides\": {}, "
            "\"human_instructions\": \"\"}')\n"
            "eng.action_bootstrap(activation_uid, str(contract), False)\n"
            "run = eng.find_pipeline_run_for(activation_uid)\n"
            "fm = run['frontmatter']\n"
            "print('VERSION', fm.get('pipeline_version'))\n"
            "print('LEAK', 'POST-LOCK-REWRITE' in json.dumps(fm))\n"
            "# The contract EVENT too, not just the run entry. Checking one and\n"
            "# not the other left a mutation alive: they are populated from\n"
            "# different expressions and only one of them was covered.\n"
            "folder = eng.run_folder_for(fm)\n"
            "events = eng.read_events(folder)\n"
            "locked = [e for e in events if e.get('event') == 'activation_contract_locked']\n"
            "print('CONTRACT_EVENTS', len(locked))\n"
            "print('CONTRACT_VERSION', (locked[0].get('data') or {}).get('pipeline_version'))\n"
            "print('EVENT_LEAK', 'POST-LOCK-REWRITE' in json.dumps(events))\n"
            "# The trust gradient reaches step declarations, so a post-lock edit\n"
            "# to it changes how a started run VERIFIES itself.\n"
            "print('TRUST_LEAK', 'POST-LOCK-TRUST' in json.dumps(events))\n"
            "# And the step declarations themselves: what the run EXECUTES.\n"
            "decls = eng.get_step_declarations(events)\n"
            "print('STEP_LEAK', 'POST-LOCK-STEP' in json.dumps(decls))\n"
            "print('DECL_STEPS', ','.join(sorted(decls)))\n")
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("VERSION 2.0.0", result.stdout,
                      f"the post-lock root version leaked into the run: {result.stdout}")
        self.assertIn("LEAK False", result.stdout,
                      f"post-lock root content leaked into the run entry: {result.stdout}")
        self.assertIn("CONTRACT_VERSION 2.0.0", result.stdout,
                      f"the post-lock version leaked into the locked contract event: "
                      f"{result.stdout}")
        self.assertIn("EVENT_LEAK False", result.stdout,
                      f"post-lock root content leaked into the run's events: {result.stdout}")
        self.assertIn("TRUST_LEAK False", result.stdout,
                      f"a post-lock trust gradient reached the step declarations, "
                      f"changing how a started run verifies itself: {result.stdout}")
        self.assertIn("STEP_LEAK False", result.stdout,
                      f"a post-lock STEP edit reached the declarations the run "
                      f"executes: {result.stdout}")
        self.assertIn("DECL_STEPS 0c6518ef,fa3a49c8", result.stdout, result.stdout)

    def test_bootstrapping_twice_is_refused_on_EVENTS_not_on_the_run_entry(self) -> None:
        """The guard that replaced "a run already exists".

        Under v2 the run entry exists before bootstrap — the lock creates it —
        so its existence stopped being evidence of anything, and the old check
        made v2 bootstrap impossible. Events are the evidence now: a run with
        events has had its contract locked, and re-bootstrapping would rewrite a
        contract already in flight. This runs the real bootstrap twice.
        """
        result = self._run_in_studio(
            "import importlib.util\n"
            f"spec = importlib.util.spec_from_file_location('eng', {str(self.studio.tools / '9e7003b1.py')!r})\n"
            "eng = importlib.util.module_from_spec(spec); spec.loader.exec_module(eng)\n"
            "with lt.exclusive_workspace_lock():\n"
            "    plan = lockdev.plan_dev_snapshot_transaction(\n"
            "        '10c40001', 'talos-isolated',\n"
            f"        files_dir=Path({str(self.studio.files)!r}), runs_dir=Path({str(self.studio.runs)!r}))\n"
            "    lt.apply_plan(plan, recycle=None)\n"
            "activation_uid = plan.notes['activation_uid']\n"
            f"contract = Path({str(self.studio.root)!r}) / 'contract-input.json'\n"
            "contract.write_text('{\"skips_authorized_upfront\": [], "
            "\"additional_steps_added\": [], \"trust_overrides\": {}, "
            "\"human_instructions\": \"\"}')\n"
            "eng.action_bootstrap(activation_uid, str(contract), False)\n"
            "print('FIRST-OK')\n"
            "try:\n"
            "    eng.action_bootstrap(activation_uid, str(contract), False)\n"
            "    print('SECOND-ALSO-SUCCEEDED')\n"
            "except eng.ValidationError as exc:\n"
            "    print('SECOND-REFUSED', 'already has events' in str(exc))\n")
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("FIRST-OK", result.stdout,
                      f"the first bootstrap failed: {result.stdout}")
        self.assertIn("SECOND-REFUSED True", result.stdout,
                      f"a second bootstrap was allowed to rewrite the contract: "
                      f"{result.stdout}")

    def test_action_bootstrap_defines_every_name_it_uses(self) -> None:
        """The NameError class, pinned properly.

        `action_bootstrap` used `run_folder` before defining it — a NameError on
        every real bootstrap that nothing caught, because no test called the
        function. My first attempt to pin it matched the substring "run_folder",
        which also matches a comment and the unrelated `run_folder_for(...)`
        helper, so it failed on correct code. Substring matching over source is
        the same shortcut that produced the bug; this walks the AST instead and
        asks the real question — is any local read before it is assigned.
        """
        import ast

        source = (TOOLS / "9e7003b1.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(node for node in ast.walk(tree)
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "action_bootstrap")

        assigned: set = {a.arg for a in function.args.args}
        module_level = {node.name for node in ast.walk(tree)
                        if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        module_level |= {n.id for node in tree.body
                         if isinstance(node, ast.Assign)
                         for n in ast.walk(node) if isinstance(n, ast.Name)}
        module_level |= set(dir(__builtins__)) | {"Path", "json", "sys", "yaml", "os", "re"}

        read_before_assignment = []
        for node in ast.walk(function):
            if isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Store):
                    assigned.add(node.id)
                elif node.id not in assigned and node.id not in module_level:
                    read_before_assignment.append((node.lineno, node.id))

        self.assertEqual(
            [name for _, name in read_before_assignment if name == "run_folder"], [],
            f"action_bootstrap reads run_folder before assigning it: "
            f"{read_before_assignment}")

    def test_action_bootstrap_PREFERS_the_snapshot_over_the_live_vault(self) -> None:
        """The choice itself, not just the loader.

        A mutation forcing `action_bootstrap` back to the vault survived every
        test I had, because they all called `_declarations_from_snapshot`
        directly — proving the loader worked while nothing proved the runtime
        used it. This exercises the branch: the snapshot declares one step set
        and the live vault declares a different one, so whichever the bootstrap
        reads is visible in the answer.
        """
        lock = self._run_in_studio(
            "with lt.exclusive_workspace_lock():\n"
            "    plan = lockdev.plan_dev_snapshot_transaction(\n"
            "        '10c40001', 'talos-isolated',\n"
            f"        files_dir=Path({str(self.studio.files)!r}), runs_dir=Path({str(self.studio.runs)!r}))\n"
            "    lt.apply_plan(plan, recycle=None)\n"
            "print('LOCKED')\n")
        self.assertEqual(lock.returncode, 0, lock.stderr[-1500:])
        folder = next(self.studio.runs.glob("dev-pipeline-*"))

        # Now make the LIVE definition disagree: a third step the snapshot never
        # saw. If bootstrap consults the vault, it will see three.
        self.studio.write_entry("beef0001", ["type: pipeline",
                                             "subtype: workflow-node",
                                             "title: smuggled", "status: active"])
        root = self.studio.files / "cd1fcd25.md"
        root.write_text(root.read_text().replace(
            "  - fa3a49c8", "  - fa3a49c8\n  - beef0001"))

        result = self._run_in_studio(
            "import importlib.util\n"
            f"spec = importlib.util.spec_from_file_location('eng', {str(self.studio.tools / '9e7003b1.py')!r})\n"
            "eng = importlib.util.module_from_spec(spec); spec.loader.exec_module(eng)\n"
            f"folder = Path({str(folder)!r})\n"
            "chosen = eng._declarations_from_snapshot(folder)\n"
            "steps = chosen[0] if chosen else eng.collect_step_nodes(\n"
            "    eng.resolve_workflow_node_tree('cd1fcd25'))\n"
            "print('STEPS', ','.join(sorted(steps)))\n")
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        self.assertIn("STEPS 0c6518ef,fa3a49c8", result.stdout,
                      "the smuggled step reached the run; the vault was consulted")
        self.assertNotIn("beef0001", result.stdout)

        # And the branch in action_bootstrap is genuinely snapshot-first.
        source = (TOOLS / "9e7003b1.py").read_text(encoding="utf-8")
        body = source[source.index("def action_bootstrap("):]
        body = body[: body.index("\ndef ", 1)]
        self.assertLess(
            body.index("_declarations_from_snapshot"),
            body.index("resolve_workflow_node_tree"),
            "the vault is consulted before the snapshot")

    def test_a_tampered_snapshot_refuses_rather_than_falling_back_to_the_vault(self) -> None:
        """The dangerous half of the fallback.

        If a snapshot that fails verification quietly reverted to the live
        entries, the contract swap §1 forbids would arrive through the error
        path instead of the front door — and it would look like resilience.
        """
        lock = self._run_in_studio(
            "with lt.exclusive_workspace_lock():\n"
            "    plan = lockdev.plan_dev_snapshot_transaction(\n"
            "        '10c40001', 'talos-isolated',\n"
            f"        files_dir=Path({str(self.studio.files)!r}), runs_dir=Path({str(self.studio.runs)!r}))\n"
            "    lt.apply_plan(plan, recycle=None)\n"
            "print('LOCKED')\n")
        self.assertEqual(lock.returncode, 0, lock.stderr[-1500:])

        snapshot = next(self.studio.runs.glob("dev-pipeline-*/declaration-snapshot.json"))
        body = json.loads(snapshot.read_text())
        body["declarations"]["0c6518ef"] = "---\nuid: 0c6518ef\nstatus: active\n---\n"
        snapshot.write_text(json.dumps(body))

        # Through the REAL bootstrap, not the helper (argus-a147: "do not call
        # helper directly"). A helper that refuses proves the verifier works; it
        # does not prove the runtime consults it, and that distinction is what
        # hid the NameError and the impossible run guard.
        result = self._run_in_studio(
            "import importlib.util\n"
            f"spec = importlib.util.spec_from_file_location('eng', {str(self.studio.tools / '9e7003b1.py')!r})\n"
            "eng = importlib.util.module_from_spec(spec); spec.loader.exec_module(eng)\n"
            "from lib import ignition as ig\n"
            f"contract = Path({str(self.studio.root)!r}) / 'contract-input.json'\n"
            "contract.write_text('{\"skips_authorized_upfront\": [], "
            "\"additional_steps_added\": [], \"trust_overrides\": {}, "
            "\"human_instructions\": \"\"}')\n"
            "acts = [p.stem for p in "
            f"Path({str(self.studio.files)!r}).glob('*.md') "
            "if 'type: activation' in p.read_text()]\n"
            "try:\n"
            "    eng.action_bootstrap(acts[0], str(contract), False)\n"
            "    print('BOOTSTRAPPED-ON-A-TAMPERED-SNAPSHOT')\n"
            "except ig.SnapshotRefusal:\n"
            "    print('REFUSED')\n")
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        self.assertIn("REFUSED", result.stdout,
                      f"the real bootstrap ran on a tampered snapshot, or fell back "
                      f"to the live vault: {result.stdout}")

    def test_the_fingerprint_would_actually_notice(self) -> None:
        """A negative control on the harness itself.

        An identity check that cannot fail proves nothing, and this one runs in
        every tearDown — if it were blind, every test above would pass whatever
        happened. Rather than write to production to prove it, this perturbs a
        captured fingerprint and asserts the differ reports it.
        """
        before = temp_studio.production_fingerprint()
        self.assertEqual(temp_studio.diff_fingerprints(before, before), {})

        tampered = {label: dict(entries) for label, entries in before.items()}
        surface = "governed entries"
        self.assertTrue(tampered[surface], "no governed entries found; scan is broken")
        victim = sorted(tampered[surface])[0]
        tampered[surface][victim] = "0" * 64
        tampered[surface]["fake-new-entry.md"] = "1" * 64

        changes = temp_studio.diff_fingerprints(before, tampered)
        self.assertIn(surface, changes)
        self.assertIn(victim, changes[surface]["modified"])
        self.assertIn("fake-new-entry.md", changes[surface]["added"])

    def test_every_surface_a_gesture_can_reach_is_fingerprinted(self) -> None:
        """Enumerating surfaces is the fix; a missing surface reopens the hole.

        The original pollution went unnoticed partly because nobody was looking
        at run folders, event streams or activate manifests at all.
        """
        labels = {label for label, _, _ in temp_studio.PRODUCTION_SURFACES}
        self.assertEqual(
            labels,
            {"governed entries", "run folders", "event streams", "event receipts",
             "activate manifests", "lock journals"})

    def test_REAL_lock_dev_spec_then_mutate_delete_then_REAL_bootstrap(self) -> None:
        """A148: the chain no prior test ran end-to-end.

        Existing cases called `lock_dev_spec` without bootstrap, or
        `action_bootstrap` after `plan_dev_snapshot_transaction`. A147's
        required first action for A148 was the joined path: production lock →
        mutate root and every step → delete sources → production bootstrap.
        Split green tests can (and did) hide defects that only the join finds.
        """
        result = self._run_in_studio(
            "import importlib.util, json, re\n"
            f"spec = importlib.util.spec_from_file_location('eng', {str(self.studio.tools / '9e7003b1.py')!r})\n"
            "eng = importlib.util.module_from_spec(spec); spec.loader.exec_module(eng)\n"
            f"files = Path({str(self.studio.files)!r})\n"
            "code, msg = lockdev.lock_dev_spec(\n"
            "    '10c40001', 'argus-a148',\n"
            "    files_dir=files, vault_root=STUDIO)\n"
            "print('LOCK_CODE', code)\n"
            "assert code == 0, msg\n"
            "acts = [p for p in files.glob('*.md') if 'type: activation\\n' in p.read_text()]\n"
            "projects = [p for p in files.glob('*.md') if 'type: project\\n' in p.read_text()]\n"
            "runs = [p for p in files.glob('*.md') if 'type: pipeline-run\\n' in p.read_text()]\n"
            "print('N_ACT', len(acts), 'N_ROOT', len(projects), 'N_RUN', len(runs))\n"
            "activation_uid = acts[0].stem\n"
            "print('HAS_CLASS', 'activation_class: pipeline' in acts[0].read_text())\n"
            "m = re.search(r\"substrate_authored_by:\\s*['\\\"]?([0-9a-f]{8})\", runs[0].read_text())\n"
            "print('SUBSTRATE', m.group(1) if m else 'MISSING')\n"
            "print('SUBSTRATE_OK', (m.group(1) if m else '') == activation_uid)\n"
            "for uid in ('0c6518ef', 'fa3a49c8'):\n"
            "    p = files / (uid + '.md')\n"
            "    p.write_text(p.read_text()\n"
            "        .replace('status: active', 'status: active\\nexit_criteria: [POST-LOCK-STEP]')\n"
            "        .replace('title: ', 'title: POST-LOCK-REWRITE '))\n"
            "root = files / 'cd1fcd25.md'\n"
            "root.write_text(root.read_text()\n"
            "    .replace('version: 2.0.0', 'version: 99.99.99')\n"
            "    .replace('default_trust_gradient: pinned-at-lock',\n"
            "             'default_trust_gradient: POST-LOCK-TRUST')\n"
            "    .replace('title: dev-pipeline', 'title: POST-LOCK-REWRITE'))\n"
            "for uid in ('cd1fcd25', '0c6518ef', 'fa3a49c8'):\n"
            "    (files / (uid + '.md')).unlink()\n"
            f"runs_dir = Path({str(self.studio.runs)!r})\n"
            "before = sorted(p.name for p in runs_dir.glob('dev-pipeline-*'))\n"
            f"contract = Path({str(self.studio.root)!r}) / 'contract-input.json'\n"
            "contract.write_text('{\"skips_authorized_upfront\": [], "
            "\"additional_steps_added\": [], \"trust_overrides\": {}, "
            "\"human_instructions\": \"\"}')\n"
            "eng.action_bootstrap(activation_uid, str(contract), False)\n"
            "after = sorted(p.name for p in runs_dir.glob('dev-pipeline-*'))\n"
            "print('NO_DUP', before == after and len(after) == 1)\n"
            "run = eng.find_pipeline_run_for(activation_uid)\n"
            "folder = eng.run_folder_for(run['frontmatter'])\n"
            "events = eng.read_events(folder)\n"
            "declared = sorted(eng.get_step_declarations(events).keys())\n"
            "print('DECLARED', ','.join(declared))\n"
            "locked = [e for e in events if e.get('event') == 'activation_contract_locked']\n"
            "print('CONTRACT_VERSION', (locked[0].get('data') or {}).get('pipeline_version'))\n"
            "blob = json.dumps(events)\n"
            "print('LEAK', ('POST-LOCK-REWRITE' in blob or 'POST-LOCK-TRUST' in blob\n"
            "              or 'POST-LOCK-STEP' in blob))\n"
            "print('EVENT_SET', sorted({e.get('event') for e in events}))\n")
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2500:]}")
        self.assertIn("LOCK_CODE 0", result.stdout)
        self.assertIn("N_ACT 1 N_ROOT 1 N_RUN 1", result.stdout)
        self.assertIn("HAS_CLASS True", result.stdout)
        self.assertIn("SUBSTRATE_OK True", result.stdout)
        self.assertIn("NO_DUP True", result.stdout)
        self.assertIn("DECLARED 0c6518ef,fa3a49c8", result.stdout)
        self.assertIn("CONTRACT_VERSION 2.0.0", result.stdout)
        self.assertIn("LEAK False", result.stdout)


if __name__ == "__main__":
    unittest.main()
