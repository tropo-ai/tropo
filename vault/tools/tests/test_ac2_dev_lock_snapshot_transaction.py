"""AC2: the dev lock writes the complete snapshot transaction (0a0a6777 §2).

"Dev-spec lock atomically writes one activation/root plus one
pipeline-run/run-folder containing immutable hashes of the spec, ACs, committed
substrate, and full declarations; Specify only confirms that snapshot."

This is the half of the symmetric pair that was never built. The release side
had the transaction; until it existed on both, "symmetric release ignition" was
a phrase rather than a property.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_ac2_dev_lock_snapshot_transaction
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location(
    "lock_dev_spec", TOOLS / "tropo-lock-dev-spec.py")
dl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dl)

import yaml  # noqa: E402

from lib import ignition, lock_transaction as lt  # noqa: E402


class TheDevLockWritesItsSnapshot(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac2-dev-lock-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.runs = self.tmp / "vault" / "pipeline-runs"
        self.files.mkdir(parents=True)
        self.runs.mkdir(parents=True)
        self._orig = (lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT)
        lt.LOCK_JOURNAL_DIR = self.tmp / "journal"
        lt.WORKSPACE_LOCK_PATH = self.tmp / "journal" / "ignition.lock"
        lt.VAULT_ROOT = self.tmp
        self._build()

    def tearDown(self) -> None:
        lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, uid: str, lines: list) -> None:
        (self.files / f"{uid}.md").write_text(
            "---\n" + f"uid: {uid}\n" + "\n".join(lines) + "\n---\n\n# " + uid + "\n",
            encoding="utf-8")

    def _build(self) -> None:
        self._write(dl.DEFAULT_PIPELINE_UID, [
            "type: pipeline", "title: dev-pipeline", "status: active",
            "version: 2.0.0", "children:", "  - 0c6518ef", "  - fa3a49c8"])
        self._write("0c6518ef", ["type: pipeline", "subtype: workflow-node",
                                 "title: specify", "status: active"])
        self._write("fa3a49c8", ["type: pipeline", "subtype: workflow-node",
                                 "title: build", "status: active"])
        self._write("5ec00001", ["type: dev-spec", "title: the spec",
                                 "status: draft"])

    def _plan(self):
        """Called inside a span by the tests that apply it.

        The activation argument is gone: since blocker 1 the plan authors the
        activation itself when none is correlated, because a subprocess that
        wrote one before the lock could not join the transaction.
        """
        return dl.plan_dev_snapshot_transaction(
            "5ec00001", "talos", files_dir=self.files, runs_dir=self.runs)

    def test_the_plan_writes_activation_root_run_and_declaration_snapshot(self) -> None:
        """All four writes in ONE plan (argus-a147 blocker 1).

        This expected two governed entries until 2026-08-10, because the
        activation was authored by a pipeline-activate.py subprocess BEFORE the
        lock. That subprocess could not join the transaction — so a refusal left
        an activation and a root behind with no journal, and a success produced
        two roots, since it authored one and the ignition authored another.
        """
        plan = self._plan()
        contents = [op.content for op in plan.operations]
        names = [Path(op.path).name for op in plan.operations]

        self.assertIn("declaration-snapshot.json", names)
        self.assertEqual(len([n for n in names if n.endswith(".md")]), 3,
                         "expected an activation, ONE root, and a run")
        self.assertEqual(len([c for c in contents if "type: activation" in c]), 1)
        self.assertEqual(len([c for c in contents if "type: project" in c]), 1,
                         "two activation roots is the blocker-1 defect")
        self.assertEqual(len([c for c in contents if "type: pipeline-run" in c]), 1)

    def _existing_activation_with_root(self) -> None:
        self._write("ac700099", ["type: activation", "title: pre-existing",
                                 "status: active", "dev_spec_uid: '5ec00001'",
                                 "activation_root_project: 'a0070099'"])
        self._write("a0070099", ["type: project", "title: pre-existing root",
                                 "status: active", "activation_uid: 'ac700099'"])

    def test_a_correlated_activation_is_reused_never_duplicated(self) -> None:
        """ADR-052's "existence is the gate": one activation per dev-spec."""
        self._existing_activation_with_root()
        plan = self._plan()
        authored = [c for c in (op.content for op in plan.operations)
                    if "type: activation" in c]
        self.assertEqual(authored, [], "a second activation was authored")
        self.assertTrue(plan.notes["activation_reused"])
        self.assertEqual(plan.notes["activation_uid"], "ac700099")

    def test_reusing_an_activation_reuses_ITS_root_and_mints_none(self) -> None:
        """argus-a147 residual 1: reusing half an identity is not reuse.

        The first version reused the activation and minted a fresh root anyway,
        so the reuse path produced a second root just as the subprocess path
        had. Two roots claiming one cycle means Rule 12 has two things to
        archive and two places to stamp final_commit.
        """
        self._existing_activation_with_root()
        plan = self._plan()
        self.assertEqual(plan.notes["activation_root_uid"], "a0070099")
        authored_roots = [c for c in (op.content for op in plan.operations)
                          if "type: project" in c]
        self.assertEqual(authored_roots, [],
                         "a second activation root was minted on the reuse path")

    def test_an_activation_with_no_root_is_refused_not_papered_over(self) -> None:
        self._write("ac700099", ["type: activation", "title: rootless",
                                 "status: active", "dev_spec_uid: '5ec00001'"])
        with self.assertRaises(ignition.IgnitionRefusal) as caught:
            self._plan()
        self.assertIn("names no activation root", str(caught.exception))

    def test_an_activation_naming_a_missing_root_is_refused(self) -> None:
        self._write("ac700099", ["type: activation", "title: dangling",
                                 "status: active", "dev_spec_uid: '5ec00001'",
                                 "activation_root_project: 'a00700ff'"])
        with self.assertRaises(ignition.IgnitionRefusal) as caught:
            self._plan()
        self.assertIn("does not resolve", str(caught.exception))

    def test_multiple_roots_claiming_one_activation_are_refused(self) -> None:
        self._existing_activation_with_root()
        self._write("a007009a", ["type: project", "title: rival root",
                                 "status: active", "activation_uid: 'ac700099'"])
        with self.assertRaises(ignition.IgnitionRefusal) as caught:
            self._plan()
        self.assertIn("claimed by 2 roots", str(caught.exception))

    def test_disagreeing_root_records_are_refused(self) -> None:
        """The activation names one root; a different project claims it."""
        self._write("ac700099", ["type: activation", "title: disagreeing",
                                 "status: active", "dev_spec_uid: '5ec00001'",
                                 "activation_root_project: 'a0070099'"])
        self._write("a0070099", ["type: note", "title: not a project"])
        self._write("a007009b", ["type: project", "title: other claimant",
                                 "status: active", "activation_uid: 'ac700099'"])
        with self.assertRaises(ignition.IgnitionRefusal) as caught:
            self._plan()
        self.assertIn("disagree about", str(caught.exception))

    def test_the_snapshot_carries_the_full_declarations(self) -> None:
        """§1 says a started run executes only its own snapshot. On the dev side
        there was no snapshot at all, so §1 had nothing to point at."""
        plan = self._plan()
        op = next(o for o in plan.operations
                  if Path(o.path).name == "declaration-snapshot.json")
        body = json.loads(op.content)
        self.assertEqual(body["declared_steps"], ["0c6518ef", "fa3a49c8"])
        self.assertEqual(body["pipeline_version"], "2.0.0")
        self.assertEqual(len(body["declaration_digest"]), 64)

    def test_the_spec_hash_is_of_the_bytes_on_disk(self) -> None:
        plan = self._plan()
        expected = hashlib.sha256(
            (self.files / "5ec00001.md").read_bytes()).hexdigest()
        self.assertEqual(plan.notes["dev_spec_sha256"], expected)

    def test_the_activation_root_is_authored(self) -> None:
        """Rule 12 archives the root at close; without one there is nothing to
        archive and final_commit has nowhere to land."""
        plan = self._plan()
        root = next(o for o in plan.operations
                    if o.path.parent == self.files and "type: project" in o.content)
        frontmatter = yaml.safe_load(root.content.split("---", 2)[1])
        self.assertEqual(frontmatter["activated_by_pipeline"], dl.DEFAULT_PIPELINE_UID)
        self.assertEqual(frontmatter["dev_spec_uid"], "5ec00001")

    def test_the_run_records_the_real_pipeline_version(self) -> None:
        plan = self._plan()
        run = next(o for o in plan.operations
                   if "type: pipeline-run" in o.content)
        self.assertIn("pipeline_version: '2.0.0'", run.content)

    def test_a_draft_dev_pipeline_root_cannot_be_ignited(self) -> None:
        path = self.files / f"{dl.DEFAULT_PIPELINE_UID}.md"
        path.write_text(path.read_text().replace("status: active", "status: draft"))
        with self.assertRaises(ignition.IgnitionRefusal):
            self._plan()

    def test_a_missing_spec_refuses_rather_than_hashing_nothing(self) -> None:
        (self.files / "5ec00001.md").unlink()
        with self.assertRaises(ignition.IgnitionRefusal) as caught:
            self._plan()
        self.assertIn("does not resolve", str(caught.exception))

    def test_the_whole_transaction_applies_as_one_act(self) -> None:
        spec = self.files / "5ec00001.md"
        with lt.exclusive_workspace_lock():
            plan = self._plan()
            plan.patch(spec, spec.read_text(), spec.read_text().replace(
                "status: draft", "status: locked"))
            lt.apply_plan(plan, recycle=None)

        self.assertIn("status: locked", spec.read_text())
        runs = list(self.runs.glob("dev-pipeline-*/declaration-snapshot.json"))
        self.assertEqual(len(runs), 1, "expected exactly one run folder")

    def test_a_failure_mid_apply_leaves_the_spec_untouched(self) -> None:
        """The property the original lock claimed and did not have: it wrote the
        status flip directly, so a later failure left a locked spec with no run."""
        spec = self.files / "5ec00001.md"
        before = spec.read_text()
        with self.assertRaises(lt.LockApplyFailure):
            with lt.exclusive_workspace_lock():
                plan = self._plan()
                plan.patch(spec, before, before.replace("status: draft", "status: locked"))
                # An unwritable target after the patch, so the commit fails part-way.
                plan.create(self.files / "5ec00001.md" / "impossible.md", "x")
                lt.apply_plan(plan, recycle=None)

        self.assertEqual(spec.read_text(), before,
                         "the dev-spec was left flipped after a failed transaction")

    def test_both_ignitions_use_the_same_transaction(self) -> None:
        """What makes §2's symmetry real rather than a phrase.

        Two mechanisms that happen to agree today drift; one mechanism cannot.
        """
        dev_source = (TOOLS / "tropo-lock-dev-spec.py").read_text(encoding="utf-8")
        release_source = (TOOLS / "tropo-lock-release-plan.py").read_text(encoding="utf-8")
        for source, name in ((dev_source, "dev"), (release_source, "release")):
            with self.subTest(ignition=name):
                self.assertIn("lock_transaction", source)
                self.assertIn("ignition", source)
                self.assertIn("exclusive_workspace_lock", source)


class TheLockCannotCommitUnparseableYaml(TheDevLockWritesItsSnapshot):
    """A148's surgical Stage-6 prerequisite (evt_a9360f18f56fe472_00000020).

    `render_activation` wrapped free text in single quotes, so Metis's cycle
    context — which contained an apostrophe — closed the quote early and the
    lock committed an activation nobody could parse. `ddc56dab` had to be
    repaired by hand after the fact.

    The reason this is worse than a malformed file, and the reason it is worth
    a class of its own: the lock transaction did its job perfectly. It was
    atomic, it was journalled, it refused nothing, and it durably committed a
    VALID transaction containing an INVALID record. Transactional integrity
    cannot see content validity, so nothing in that machinery was ever going
    to catch this. Only parsing the thing we wrote catches it.

    Driven through the real plan-and-apply gesture rather than by calling the
    renderer, because the renderer returning good text proves nothing about
    what the lock commits.
    """

    HOSTILE = {
        "apostrophe": "Mike's compact-continue cycle",
        "colon": "cycle: phase 1, ratio 15%",
        "newline": "first line\nsecond line",
        "double_quote": 'the "quoted" cycle',
        "backslash": r"a\path\like\this",
        "all_at_once": "Mike's \"phase: 2\"\nwith a\\slash",
    }

    def _lock_with_context(self, context: str) -> dict:
        """Run the real gesture and return the activation's parsed frontmatter."""
        spec = self.files / "5ec00001.md"
        with lt.exclusive_workspace_lock():
            plan = dl.plan_dev_snapshot_transaction(
                "5ec00001", "talos", files_dir=self.files,
                runs_dir=self.runs, cycle_context=context)
            lt.apply_plan(plan, recycle=None)

        written = [
            path for path in self.files.glob("*.md")
            if "type: activation" in path.read_text(encoding="utf-8")
            and "activation-root" not in path.read_text(encoding="utf-8")
        ]
        self.assertPlantedOne(written)
        text = written[0].read_text(encoding="utf-8")
        _, frontmatter, _ = text.split("---", 2)
        return yaml.safe_load(frontmatter)

    def assertPlantedOne(self, written) -> None:
        self.assertEqual(
            len(written), 1,
            f"expected exactly one activation entry, found {len(written)}",
        )

    def _fresh_fixture(self) -> None:
        """Clear the vault between shapes WITHOUT re-running setUp.

        Calling `setUp` again from inside a test looks harmless and is not:
        it re-captures the already-patched module globals as `self._orig`, so
        the teardown that follows restores a temp path over the real one and
        every later test in the same interpreter inherits a `VAULT_ROOT` that
        no longer exists. The first version of this test did exactly that and
        took an unrelated case in another file down with it -- the same
        cross-test pollution class this suite was quarantined for once before.
        """
        shutil.rmtree(self.files, ignore_errors=True)
        shutil.rmtree(self.runs, ignore_errors=True)
        self.files.mkdir(parents=True)
        self.runs.mkdir(parents=True)
        self._build()

    def test_every_hostile_cycle_context_still_parses_and_round_trips(self):
        for name, context in self.HOSTILE.items():
            with self.subTest(shape=name):
                self._fresh_fixture()
                try:
                    parsed = self._lock_with_context(context)
                except yaml.YAMLError as exc:
                    self.fail(
                        f"the lock committed an activation that will not "
                        f"parse for the {name} shape: {exc}"
                    )
                self.assertEqual(
                    parsed.get("cycle_context"), context,
                    f"the {name} shape parsed but came back changed; a value "
                    f"that survives parsing while losing its content is a "
                    f"quieter version of the same bug",
                )

    def test_an_actor_name_carrying_punctuation_cannot_break_the_entry(self):
        """`actor` reaches the same renderer and comes from the environment.

        Fixed alongside `cycle_context` rather than after it. The whole reason
        this defect reached a governed file is that the previous instance of
        this class was fixed in one place while its twin stayed put.
        """
        spec = self.files / "5ec00001.md"
        hostile_actor = "o'brien: the \"deputy\""
        with lt.exclusive_workspace_lock():
            plan = dl.plan_dev_snapshot_transaction(
                "5ec00001", hostile_actor, files_dir=self.files,
                runs_dir=self.runs)
            lt.apply_plan(plan, recycle=None)

        for path in self.files.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            if "type: activation" not in text:
                continue
            _, frontmatter, _ = text.split("---", 2)
            parsed = yaml.safe_load(frontmatter)
            self.assertEqual(
                parsed.get("owner"), hostile_actor,
                "the actor name did not survive being written into YAML",
            )


if __name__ == "__main__":
    unittest.main()
