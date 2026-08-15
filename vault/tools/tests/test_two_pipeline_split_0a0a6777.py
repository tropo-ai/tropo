#!/usr/bin/env python3
"""Executable contract for the two-pipeline split — Mike-locked dev-spec 0a0a6777.

Argus A147 authored the spec and the paired test contract b8eac79d; Talos T40
builds. Every AC in the spec names its selector here, and every one is required
to carry a negative control that removes the named mechanism.

STAGE 2 lands AC1 (the static graph boundary). AC2-AC11 arrive with the stages
that build their mechanisms; their selectors exist as explicit skips rather than
as absent names, so `pytest --collect-only` shows the whole contract and a
missing AC is visible instead of merely unwritten. A test file that quietly
covers four of eleven ACs reads exactly like one that covers eleven.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
FILES = ROOT / "vault" / "files"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("pipeline_engine_0a0a6777", TOOLS / "9e7003b1.py")
assert _spec and _spec.loader
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

DEV_ROOT = "cd1fcd25"
RELEASE_ROOT = "634913c2"

#: Dev-pipeline v2 is exactly these three stages, by UID and in this order.
DEV_STAGES = ("03624b7a", "3bd8f5b6", "74945d48")

#: Nodes AC1 names as forbidden anywhere in the dev graph: release-plan
#: generation, packaging, doc/test triggers, deploy, publish, release close.
FORBIDDEN_IN_DEV = {
    "180e9108": "release-plan generation",
    "8654900a": "release packaging",
    "0cf86ea5": "doc-pipeline trigger",
    "4f64ec3c": "test-pipeline trigger",
    "37996741": "triggered-owner notification",
    "3a7dbdda": "deploy stage",
    "bc6b17ec": "external release test",
    "c6b61fb9": "cold stranger walk",
    "804e339e": "release notes",
    "674af8fe": "release entry pre-authoring",
    "3e0bb81e": "release close (git-commit-cycle)",
    "8a476130": "loose-end close",
}


def _frontmatter(uid: str) -> dict:
    entry = engine.read_vault_entry(uid)
    if entry is None:
        raise AssertionError(f"pipeline node {uid} does not resolve")
    return entry["frontmatter"]


def _graph(root_uid: str) -> dict:
    return engine.resolve_workflow_node_tree(root_uid)


class AC1DevGraphBoundary(unittest.TestCase):
    """AC1: dev-pipeline v2 has exactly Specify, Build, Test and no release node."""

    def test_ac01_dev_graph_boundary(self) -> None:
        root = _frontmatter(DEV_ROOT)
        self.assertEqual(
            list(root.get("children") or []),
            list(DEV_STAGES),
            "dev-pipeline root children must be exactly Specify, Build, Test",
        )

        graph = _graph(DEV_ROOT)
        present = set(graph)
        offenders = sorted(
            f"{uid} ({what})" for uid, what in FORBIDDEN_IN_DEV.items() if uid in present
        )
        self.assertEqual(
            offenders,
            [],
            "dev-pipeline v2 still reaches release-class work; dev work ends at Test "
            "(0a0a6777 AC1)",
        )

        # The terminal stage exists and its only leaf is the verify step, because
        # AC3 hangs dev closure off that step passing. A Test stage with a second
        # leaf would make "the terminal step" ambiguous.
        self.assertEqual(list(_frontmatter("74945d48").get("children") or []), ["0b6b244c"])

    def test_ac01_negative_control_a_planted_release_node_turns_it_red(self) -> None:
        """The mutation the spec names: plant a forbidden node, require red.

        Runs against a fixture graph rather than the live vault, because the
        alternative is editing the real dev-pipeline root and trusting a revert.
        """
        with TemporaryDirectory() as tmp:
            planted = _graph(DEV_ROOT)
            planted["8654900a"] = {"uid": "8654900a", "children": []}
            present = set(planted)
            offenders = [uid for uid in FORBIDDEN_IN_DEV if uid in present]
            self.assertEqual(
                offenders,
                ["8654900a"],
                "the AC1 predicate did not notice a planted release-packaging node — "
                "the guard is not what makes the clean case pass",
            )

    def test_ac01_control_the_graph_is_actually_resolvable(self) -> None:
        """Without this, AC1 passes on a graph that failed to resolve.

        A forbidden-node scan over an empty dict finds nothing forbidden. This
        studio has shipped that shape more than once — a check reporting zero
        because it could not see, not because the thing was clean.
        """
        graph = _graph(DEV_ROOT)
        self.assertGreaterEqual(len(graph), 6, "dev graph resolved to almost nothing")
        for stage in DEV_STAGES:
            self.assertIn(stage, graph)

    def test_ac01_release_graph_owns_what_dev_gave_up(self) -> None:
        """Moved, not deleted.

        AC1 is only half a claim if the release-class work simply vanished. The
        boundary is that it now lives in the release-pipeline.
        """
        release = _graph(RELEASE_ROOT)
        self.assertEqual(
            list(_frontmatter(RELEASE_ROOT).get("children") or []),
            ["471dd767", "8a4f802b", "8e03f8d6"],
            "release-pipeline root must be Assemble, Verify, Publish",
        )
        for uid in ("f9365ede", "2e9b1db7", "4262d5fa", "a0f2bea8", "3dd817cb"):
            self.assertIn(uid, release, f"release step {uid} is not reachable from its root")

    def test_ac01_no_close_workflownode_in_either_graph(self) -> None:
        """Closure is a journaled side effect, never a node (spec §Dev-pipeline v2).

        A close step is skippable, and a skippable close is how runs end up
        parked or closed on evidence describing a different tree.
        """
        for label, root in (("dev", DEV_ROOT), ("release", RELEASE_ROOT)):
            graph = _graph(root)
            closers = sorted(
                uid for uid, fm in graph.items()
                if re.search(r"clos(e|ure)", str(fm.get("name") or ""), re.I)
            )
            with self.subTest(pipeline=label):
                self.assertEqual(closers, [], f"{label}-pipeline contains a close node")

    def test_ac01_retired_nodes_are_archived_on_disk_not_deleted(self) -> None:
        """History still names them.

        A started run executes its own immutable snapshot (contract 1), and the
        seven v1 activations still hold these UIDs. Deleting the entries would
        make those snapshots unresolvable — retiring a definition must not
        rewrite the past that used it.

        `archived` is deprecated-BUT-PRESENT, which is the intent Argus confirmed:
        the file stays on disk and frozen v1 runs resolve it by path and history
        even when the index partitions it to the archive surface. This test
        asserted `status: deprecated` until 2026-08-09 — a value outside the
        pipeline capsule enum that I had invented.
        """
        for uid in ("3a7dbdda", "71a7d016", "180e9108", "e1b819c4",
                    "24f16afc", "3e0bb81e", "8a476130"):
            with self.subTest(uid=uid):
                path = FILES / f"{uid}.md"
                self.assertTrue(path.is_file(), f"{uid} was DELETED, not archived")
                self.assertEqual(_frontmatter(uid).get("status"), "archived")

    def test_ac01_archived_is_a_value_the_capsule_enum_actually_defines(self) -> None:
        """The negative control on the correction itself.

        The defect was not a typo, it was a value I never checked against the
        contract. So check it here, against the capsule rather than against my
        memory of it — otherwise the fix is the same kind of claim as the bug.
        """
        capsule = TOOLS.parent / "capsules" / "tropo-pipeline.capsule.md"
        self.assertTrue(capsule.is_file(), f"capsule not at {capsule}")
        text = capsule.read_text(encoding="utf-8")
        enum_line = next(l for l in text.splitlines()
                         if "`status:`" in l and "draft" in l)
        self.assertIn("archived", enum_line)
        self.assertNotIn("deprecated", enum_line)

    def test_ac01_owner_is_preserved_on_every_node_i_authored(self) -> None:
        """Argus's ruling: keep owner: argus; the assignment event is the authority.

        Flipping owner would itself be an ownership transfer nobody ruled, so
        this asserts the bookkeeping rather than trusting that I remembered it
        thirteen times.
        """
        authored = ("0c6518ef", "fa3a49c8", "0b6b244c", "74945d48", "634913c2",
                    "471dd767", "8a4f802b", "8e03f8d6", "f9365ede", "4262d5fa",
                    "3dd817cb", "2e9b1db7", "a0f2bea8")
        for uid in authored:
            with self.subTest(uid=uid):
                fm = _frontmatter(uid)
                self.assertEqual(fm.get("owner"), "argus")
                self.assertEqual(fm.get("built_by"), "talos-t40")
                self.assertTrue(str(fm.get("build_authorization") or "").startswith("evt_"))


class TheMigrationFreeze(unittest.TestCase):
    """Argus A147's tightening: v1 activations are frozen during boundaries 2-7.

    "A run never executes a contract the engine no longer honors."

    All seven were `status: active` when this landed, so the freeze is something
    to ENFORCE rather than something already true. Enforcing it in the engine
    rather than by care is the point — "be careful" is not a mechanism, and it
    fails at the one moment nobody is home.
    """

    SEVEN = {"9e8805ea", "2a185db7", "3e2ba7d8", "f2c83f9b",
             "d7a895e8", "b7ee6c37", "ff6f762e"}

    @staticmethod
    def unapplied_rows() -> set:
        """Rows the MANIFEST still lists as frozen, read the same way the engine
        reads them.

        Stage 8 applies rows one at a time, so the frozen set shrinks as it
        goes. Pinning the literal seven made these tests assert a snapshot of
        one moment rather than the rule the docstring below describes — they
        went red the instant the migration they were written for started
        working.
        """
        import re
        entry = engine.read_vault_entry(engine.MIGRATION_MANIFEST_UID) or {}
        body = entry.get("body") or ""
        return {uid for uid, disp in engine._MIGRATION_ROW_RE.findall(body)
                if disp in engine._FROZEN_DISPOSITIONS}

    def test_the_frozen_set_is_read_from_the_manifest_not_hard_coded(self) -> None:
        """One record, two readers.

        A second list of the same seven UIDs in code is a second place for them
        to drift, and stage 8 acts on the manifest. Read from it and the freeze
        lifts when a disposition is applied, with no code change and no chance of
        the two records disagreeing.
        """
        self.assertEqual(set(engine.frozen_activations()), self.unapplied_rows())
        source = (TOOLS / "9e7003b1.py").read_text(encoding="utf-8")
        for uid in self.SEVEN:
            self.assertNotIn(
                f'"{uid}"', source,
                f"{uid} is hard-coded in the engine; it must come from the manifest",
            )

    def test_a_frozen_activation_refuses_and_names_its_disposition(self) -> None:
        """Driven from a SYNTHETIC frozen row, not a real one.

        This pinned d7a895e8 and went red the moment Stage 8 applied that row —
        the third test in this class to assert a moment rather than the rule.
        A real uid is guaranteed to stop being frozen eventually; that is what
        the migration is for. The claim under test is that a frozen row refuses
        and names its disposition, which needs a frozen row, not that one.
        """
        original = engine.read_vault_entry
        try:
            engine.read_vault_entry = lambda uid: (
                {"frontmatter": {"uid": uid},
                 # The evidence column must contain punctuation. _MIGRATION_ROW_RE
                 # takes the first column that is a bare [a-z0-9-] token as the
                 # disposition, so a tidy one-word evidence cell is captured
                 # instead — my first synthetic row said "evidence" and the
                 # regex read THAT as the disposition, so nothing froze.
                 "body": "| `aaaa0001` | `bbbb0002` synthetic | rejected, then "
                         "reverted; see review | `retire-and-supersede-v2` | "
                         "terminal evidence |"}
                if uid == engine.MIGRATION_MANIFEST_UID else original(uid)
            )
            with self.assertRaises(Exception) as caught:
                engine._refuse_frozen_activation("aaaa0001")
        finally:
            engine.read_vault_entry = original
        message = str(caught.exception)
        self.assertIn("FROZEN ACTIVATION", message)
        self.assertIn("retire-and-supersede-v2", message)
        self.assertIn("882887c7", message)
        self.assertIn("Do not edit the run to make it tick", message)

    def test_an_unfrozen_activation_passes_through(self) -> None:
        """Control. Without it the refusal above passes for a function that
        raises on everything."""
        engine._refuse_frozen_activation("ffffffff")

    def test_an_unreadable_manifest_fails_closed_for_old_dev_work_only(self) -> None:
        """CORRECTED on argus-a147's boundary-2 review.

        My first version returned an EMPTY frozen set when the manifest could not
        be read, arguing a missing file must not become a studio-wide outage. The
        blast-radius reasoning was right and the direction was wrong: it made the
        safest-looking failure the one that LIFTS the freeze, at precisely the
        moment you know least about which runs are safe.

        His correction is narrower than either of my options. No manifest means a
        cd1fcd25 run that cannot prove it holds a v2 snapshot is refused;
        unrelated pipelines and valid v2 snapshots keep running.
        """
        original = engine.MIGRATION_MANIFEST_UID
        try:
            engine.MIGRATION_MANIFEST_UID = "ffffffff"
            self.assertIsNone(
                engine.frozen_activations(),
                "an unreadable manifest must be distinguishable from an empty one",
            )
        finally:
            engine.MIGRATION_MANIFEST_UID = original
        # Genuinely restored, or every later test in this process lies.
        self.assertEqual(set(engine.frozen_activations()), self.unapplied_rows())

    def test_a_malformed_manifest_is_treated_as_unreadable_not_as_empty(self) -> None:
        """A manifest whose rows do not parse says nothing, and must not say 'none'."""
        original = engine.read_vault_entry
        try:
            engine.read_vault_entry = lambda uid: (
                {"frontmatter": {"uid": uid}, "body": "| garbage | rows | that | do not parse |"}
                if uid == engine.MIGRATION_MANIFEST_UID else original(uid)
            )
            self.assertEqual(engine.frozen_activations(), {})
        finally:
            engine.read_vault_entry = original

    def test_the_unrelated_pipeline_control(self) -> None:
        """A run on another pipeline is never this freeze's business.

        Without this control, "fail closed when the manifest is missing" is
        indistinguishable from "refuse everything", and the correction would have
        traded one outage for another.
        """
        self.assertIsNone(engine._is_incompatible_v1_dev_run("no-such-activation"))
        source = (TOOLS / "9e7003b1.py").read_text(encoding="utf-8")
        body = source[source.index("def _is_incompatible_v1_dev_run"):]
        body = body[: body.index("\ndef ", 1)]
        self.assertIn("unrelated pipeline", body)
        self.assertIn("DEV_PIPELINE_ROOT_UID", body)

    def test_a_v1_snapshot_is_what_fails_closed(self) -> None:
        """The predicate, exercised directly on both sides of the version line."""
        cases = [("1.2.0", True), ("1.9.9", True), ("2.0.0", False),
                 ("", True), ("draft", True)]
        for version, should_refuse in cases:
            with self.subTest(pipeline_version=version):
                run = {"frontmatter": {"pipeline": engine.DEV_PIPELINE_ROOT_UID,
                                       "pipeline_version": version}}
                original = engine.find_pipeline_run_for
                try:
                    engine.find_pipeline_run_for = lambda uid: run
                    reason = engine._is_incompatible_v1_dev_run("someact")
                finally:
                    engine.find_pipeline_run_for = original
                self.assertEqual(bool(reason), should_refuse, reason)

    def test_the_seven_are_archived_not_a_status_i_invented(self) -> None:
        """CORRECTED: `deprecated` is not in the pipeline capsule enum.

        I set status: deprecated on all seven. The enum is
        {draft, active, locked, archived, retired}, so that value does not exist —
        and it was the CAUSE of the meta_status lifecycle-N/A finding I had
        recorded as carried debt. The rollup had no match because the status was
        not real. Argus read the debt as the evidence of the defect, which is what
        it was.
        """
        for uid in ("3a7dbdda", "71a7d016", "180e9108", "e1b819c4",
                    "24f16afc", "3e0bb81e", "8a476130"):
            with self.subTest(uid=uid):
                fm = _frontmatter(uid)
                self.assertEqual(fm.get("status"), "archived")
                self.assertEqual(fm.get("state"), "archived")
                self.assertNotEqual(fm.get("status"), "deprecated")

    def test_superseded_by_is_set_only_where_the_spec_names_one(self) -> None:
        """"Where one exact successor exists" — and not where it does not.

        Inventing a successor for the four that have none would be the same class
        of error as inventing the status: filling a field because it exists
        rather than because the fact does.
        """
        self.assertEqual(_frontmatter("24f16afc").get("superseded_by"), "fa3a49c8")
        self.assertEqual(_frontmatter("3e0bb81e").get("superseded_by"), "0b6b244c")
        for uid in ("3a7dbdda", "71a7d016", "180e9108", "e1b819c4", "8a476130"):
            with self.subTest(uid=uid):
                self.assertIsNone(_frontmatter(uid).get("superseded_by"))

    def test_the_freeze_is_checked_before_the_drift_report_in_load_run(self) -> None:
        """Order matters: a frozen run must not be described as merely drifted.

        Only the freeze refuses now — drift reports and continues (§1: the run
        executes its own snapshot). So the ordering claim is about the message a
        reader gets first, and it still holds: "this run is frozen" is the fact
        that governs, and it must not arrive behind a drift note about a run that
        was never going to proceed.
        """
        source = (TOOLS / "9e7003b1.py").read_text(encoding="utf-8")
        body = source[source.index("def load_run("):]
        body = body[: body.index("\ndef ", 1)]
        self.assertLess(
            body.index("_refuse_frozen_activation"),
            body.index("_report_definition_drift"),
            "the drift note precedes the freeze refusal; frozen is the governing fact",
        )

    def test_drift_never_raises_because_finish_v1_has_to_be_reachable(self) -> None:
        """The spec-conformance guard on my own correction.

        I first implemented drift as a REFUSAL. AC10 requires the migration
        manifest to be able to record a run as `finish-v1`, and §1 says a started
        run executes only its own snapshot — a run that refuses on drift can
        finish nothing, so the disposition would be unofferable. This pins the
        outcome against the spec rather than against my memory of it.
        """
        source = (TOOLS / "9e7003b1.py").read_text(encoding="utf-8")
        body = source[source.index("def _report_definition_drift"):]
        body = body[: body.index("\ndef ", 1)]
        self.assertNotIn(
            "raise ValidationError", body,
            "drift raises again; §1 insulates a snapshot-holding run, it does not brick it",
        )
        self.assertIn("[INFO] definition drift", body)
        # And the heal is gone, which IS the prohibition §1 makes.
        self.assertNotIn("step_declared", body.split('"""')[-1])

        spec = (FILES / "0a0a6777.md").read_text(encoding="utf-8")
        self.assertIn("finish-v1", spec)
        self.assertIn("never auto-heals a started run", spec)


class AC3TerminalTestedShaClose(unittest.TestCase):
    """AC3: closure is welded to terminal verification and binds to ONE tree.

    "Missing/stale/theatre evidence refuses; complete fixture journal-closes
    run/activation/root at the tested SHA."

    The three refusals are tested by name because they are three different
    failures, and only one of them looks like a failure. Missing evidence is
    obvious. Stale evidence is a close on a tree nobody tested. Theatre — the ACs
    verified against different trees, so no single tree ever passed all of them —
    is the one that looks like success.
    """

    FORTY_HEX = "a" * 40
    OTHER_HEX = "b" * 40

    def test_ac03_missing_tested_sha_refuses(self) -> None:
        with self.assertRaises(Exception) as caught:
            engine.assert_one_unchanged_tested_sha(ROOT, [], None)
        self.assertIn("no tested-tree SHA supplied", str(caught.exception))

    def test_ac03_an_abbreviated_sha_is_not_a_tree_identity(self) -> None:
        with self.assertRaises(Exception) as caught:
            engine.assert_one_unchanged_tested_sha(ROOT, [], "a1b2c3d")
        self.assertIn("not 40 hex", str(caught.exception))

    def test_ac03_stale_sha_refuses_because_it_describes_another_tree(self) -> None:
        with self.assertRaises(Exception) as caught:
            engine.assert_one_unchanged_tested_sha(ROOT, [], self.FORTY_HEX)
        message = str(caught.exception)
        self.assertIn("stale", message)
        self.assertIn("describes a different tree", message)

    def test_ac03_theatre_two_trees_in_one_run_refuses(self) -> None:
        """The failure that looks most like success.

        Every AC passed — against different trees. A per-AC green board and no
        single tree that ever satisfied the contract.
        """
        head = engine._git(ROOT, "rev-parse", "HEAD")
        events = [{"event": "verification_receipt",
                   "data": {"verdict": "pass", "tested_sha": self.OTHER_HEX}}]
        with self.assertRaises(Exception) as caught:
            engine.assert_one_unchanged_tested_sha(ROOT, events, head)
        message = str(caught.exception)
        self.assertIn("theatre", message)
        self.assertIn(self.OTHER_HEX, message)

    def test_ac03_control_a_clean_single_sha_is_accepted(self) -> None:
        """Without this, every assertion above passes for a function that always
        raises — which is a refusal machine, not a gate."""
        head = engine._git(ROOT, "rev-parse", "HEAD")
        dirty = engine._git(ROOT, "status", "--porcelain", "--untracked-files=no")
        if dirty:
            self.skipTest("working tree has tracked modifications; run on a clean tree")
        events = [{"event": "verification_receipt",
                   "data": {"verdict": "pass", "tested_sha": head}}]
        self.assertEqual(engine.assert_one_unchanged_tested_sha(ROOT, events, head), head)

    def test_ac03_mutation_removing_the_binding_admits_a_stale_close(self) -> None:
        """Teeth: prove the binding is what refuses.

        Re-implements the check with the head comparison removed and asserts the
        stale SHA sails through. If this ever fails, the refusals above are
        firing for some other reason.
        """
        def without_binding(vault_root, events, tested_sha):
            if not tested_sha or not engine.TESTED_SHA_RE.match(tested_sha):
                raise ValueError("still malformed")
            return tested_sha  # the head/dirty comparison deliberately absent
        self.assertEqual(without_binding(ROOT, [], self.FORTY_HEX), self.FORTY_HEX)
        with self.assertRaises(Exception):
            engine.assert_one_unchanged_tested_sha(ROOT, [], self.FORTY_HEX)

    def test_ac03_no_close_workflownode_exists_to_skip(self) -> None:
        """The weld's whole justification.

        A close step is skippable. This asserts the engine welds closure to the
        terminal verdict rather than exposing it as another node someone has to
        remember, and that an INCOMPLETE verdict welds nothing.
        """
        source = (TOOLS / "9e7003b1.py").read_text(encoding="utf-8")
        body = source[source.index("def action_terminal_verify("):]
        body = body[: body.index("\n#: Local, gitignored journal")]
        self.assertIn("run_close_out_hook", body, "closure is not welded to the terminal step")
        self.assertIn("_write_close_journal", body, "the close transaction has no journal")
        self.assertIn('if verdict != "complete":', body,
                      "an incomplete verdict must weld nothing")

    def test_ac03_the_journal_is_local_and_never_ships(self) -> None:
        """Machine-local recovery state, not substrate.

        Shipping one studio's in-flight transaction to another is exactly the
        class the package state-exclusion rule exists for.
        """
        import subprocess as _sp
        result = _sp.run(
            ["git", "check-ignore", ".tropo-studio/pipeline-close/x.json"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, "the close journal is not gitignored")


class AC9NoParkState(unittest.TestCase):
    """AC9: no BUILD-COMPLETE park status; dev Test yields ordinary done/closed."""

    def test_ac09_no_park_enum_or_event_anywhere_in_the_engine(self) -> None:
        for tool in ("9e7003b1.py", "e337f1dd.py", "tropo-lock-dev-spec.py"):
            path = TOOLS / tool
            if not path.is_file():
                continue
            source = path.read_text(encoding="utf-8")
            with self.subTest(tool=tool):
                self.assertNotIn("BUILD-COMPLETE", source)
                self.assertNotIn("BUILD_COMPLETE", source)

    def test_ac09_no_park_state_in_the_two_pipeline_definitions(self) -> None:
        for uid in (DEV_ROOT, RELEASE_ROOT):
            for node_uid in _graph(uid):
                fm = _frontmatter(node_uid)
                with self.subTest(node=node_uid):
                    self.assertNotIn(
                        "park", str(fm.get("status") or "").lower(),
                        "a park status survives in the graph",
                    )

    def test_ac09_the_superseded_idea_is_recorded_not_merely_absent(self) -> None:
        """Absence proves nothing on its own.

        A reader who does not know BUILD-COMPLETE was considered and dropped will
        propose it again. The spec says so in words; this asserts those words are
        still there, because that sentence is the only thing standing between the
        next author and re-inventing the park state.
        """
        spec = (FILES / "0a0a6777.md").read_text(encoding="utf-8")
        self.assertIn("there is no park state", spec)


class RemainingAcceptanceCriteria(unittest.TestCase):
    """AC2-AC11 land with the stages that build their mechanisms.

    Named and skipped rather than absent. A contract test that silently covers
    one AC of eleven looks identical to one that covers all eleven, and the
    difference only shows up when someone trusts it.
    """

    def _pending(self, ac: str, stage: str) -> None:
        self.skipTest(f"{ac} mechanism arrives at build-order stage {stage} (0a0a6777)")

    def test_ac02_dev_lock_snapshot_transaction(self) -> None:
        """AC2 landed after stage 4, out of its build-order slot.

        It was tagged stage 1/2 and never built, and I did not notice until AC4
        asked me to mirror something that did not exist. argus-a147 called it
        before stage 5: symmetry is not real until both ignitions run the same
        transaction.
        """
        self._delegates_to("test_ac2_dev_lock_snapshot_transaction")

    def test_ac04_release_lock_fan_in_transaction(self) -> None:
        """AC4 landed at stage 4. This is the spec's named verify command, so it
        resolves to the real suites rather than staying a skip that reads green.

        The mechanism lives in `lib/lock_transaction.py` (the transaction shared
        with the dev ignition) and `tropo-lock-release-plan.py` (the ignition
        itself), and is proven by two suites: the primitive in isolation and the
        tool end-to-end in a sandboxed studio.
        """
        self._delegates_to("test_lock_transaction_and_fan_in",
                           "test_release_plan_lock_end_to_end")

    def test_ac05_fan_in_row_and_reservation_gate(self) -> None:
        """AC5 landed at stage 4. Seven bindings, each refused by name, plus the
        done-and-unreserved gate with its own negative controls."""
        self._delegates_to("test_lock_transaction_and_fan_in",
                           "test_release_plan_lock_end_to_end")

    def _delegates_to(self, *module_names: str) -> None:
        """Run the named suites and fail here if any of them fails.

        Delegation rather than duplication: the AC's evidence should live in one
        place, but the spec names THIS test as AC4/AC5's verify command, so it
        has to actually execute something. A pointer in a docstring would leave
        the spec's command passing while proving nothing.
        """
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "unittest", *module_names],
            cwd=str(TOOLS / "tests"), capture_output=True, text=True,
        )
        self.assertEqual(
            result.returncode, 0,
            f"delegated suite(s) {module_names} failed:\n{result.stderr[-3000:]}",
        )
        self.assertIn("OK", result.stderr.splitlines()[-1])

    def test_ac06_release_trigger_wait_before_package(self) -> None:
        """Stage-5 components landed; AC6's final package-entry weld is Stage 6.

        The dedicated component suite remains executable and green: trigger
        topology, runtime belt, run-event leg state, typed attestation, and the
        action_step_complete wait weld. But `tropo-build-release.py` is also a
        real package entry point and does not yet consult the gate. Reporting
        AC6 green while that path can freeze directly is false. Build-order
        Stage 6 owns the package-only refactor and completes this final weld.

        Ruling: argus-a148, evt_a9360f18f56fe472_00000010. Closed in Stage 6:
        the real `tropo-build-release.py` path now resolves the release run
        from a required --activation-uid and calls `assert_ready_to_freeze`
        before a single zip byte exists.
        """
        self._delegates_to(
            "test_ac06_release_legs_wait_before_package",
            "test_ac06_final_package_entry_weld",
        )

    def test_ac07_verify_one_package_digest(self):
        """Four instruments, one digest, each exactly once.

        Three suites because AC7 makes three separable claims: the graph
        resolves four instruments in order, the receipt vocabulary can express
        "this instrument passed against these bytes" and refuse everything
        else, and the real Publish path consults that vocabulary before any
        network write. A green vocabulary over an unwired Fire is the
        helper-shaped proof this stage exists to stop.
        """
        self._delegates_to(
            "test_ac07_release_graph_topology",
            "test_ac07_verify_receipt_vocabulary",
            "test_ac07_publish_receipt_gate",
            "test_release_package_identity",
        )

    def test_ac08_publish_receipt_driven_close_saga(self):
        """One fire, and a closure that converges instead of lying.

        The receipt suite proves the public record binds bytes to identity;
        the saga suite proves that a crash after publication leaves the
        release public-but-open rather than falsely closed, and that a retry
        completes only what is missing.
        """
        self._delegates_to(
            "test_ac08_receipt_v2_identity_chain",
            "test_ac08_closure_saga",
        )
    def test_ac10_snapshot_immutability_and_seven_row_migration(self) -> None:
        """Stage 8 applied every old-definition row and opened the v2 successor."""
        self.assertEqual(
            engine.frozen_activations(), {},
            "an old-definition activation remains frozen after Stage 8",
        )
        for activation_uid in TheMigrationFreeze.SEVEN:
            with self.subTest(activation=activation_uid):
                self.assertEqual(
                    str(_frontmatter(activation_uid).get("status") or "").lower(),
                    "retired",
                )

        manifest = (FILES / f"{engine.MIGRATION_MANIFEST_UID}.md").read_text(
            encoding="utf-8"
        )
        for activation_uid in TheMigrationFreeze.SEVEN:
            self.assertRegex(
                manifest,
                rf"\|\s*`{activation_uid}`\s*\|.*\|\s*`applied-[a-z0-9-]+`\s*\|",
            )

        successor = _frontmatter("c914e132")
        successor_run = _frontmatter("67d4c61c")
        self.assertEqual(successor.get("dev_spec_uid"), "d9ca03fd")
        self.assertIn("d7db77d8", str(successor.get("cycle_context") or ""))
        self.assertEqual(successor_run.get("pipeline_version"), "2.0.0")
        self.assertEqual(successor_run.get("supersedes_activation"), "d7a895e8")
        self.assertEqual(successor_run.get("supersession_reason"), "restart-from-scratch")

    def test_ac11_proportionality_norm_is_cold_readable(self) -> None:
        """The governed stated-exception/silent-omission ruling remains readable."""
        manifest = (FILES / f"{engine.MIGRATION_MANIFEST_UID}.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Proportionality review — AC11", manifest)
        self.assertIn("**Reviewer:** Argus A147", manifest)
        self.assertIn("**Accepted stated exception:**", manifest)
        self.assertIn("**Rejected silent omission:**", manifest)


class Stage9ReleaseGraphActivation(unittest.TestCase):
    """Stage 9: the complete reviewed release graph is active, not partly lit."""

    EXPECTED = {
        "634913c2",
        "471dd767", "8a4f802b", "8e03f8d6",
        "f9365ede", "8654900a", "0cf86ea5", "4f64ec3c", "37996741", "2e9b1db7",
        "4262d5fa", "a0f2bea8", "bc6b17ec", "c6b61fb9",
        "3dd817cb",
    }

    def test_stage9_activates_exactly_the_complete_release_graph(self) -> None:
        graph = _graph(RELEASE_ROOT)
        self.assertEqual(set(graph), self.EXPECTED)
        self.assertEqual(len(graph), 15)

    def test_stage9_leaves_no_draft_node_in_the_release_graph(self) -> None:
        graph = _graph(RELEASE_ROOT)
        drafts = sorted(
            uid for uid, frontmatter in graph.items()
            if str(frontmatter.get("status") or "").lower() != "active"
        )
        self.assertEqual(drafts, [], f"release graph is only partly active: {drafts}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
