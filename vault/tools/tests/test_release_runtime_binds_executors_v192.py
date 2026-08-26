"""AC2 (5b608d28, v1.92 Stream 1): every declared leaf of the release pipeline
binds exactly one executor, the binding declares its kind, and a refusal names
the pipeline step it belongs to.

Measured motivation, 2026-08-24: `tropo-build-release.py` carries 28 step
functions of its own numbering and referenced `634913c2` or any of its step
uids ZERO times; `tropo-publish-release.py` zero; and the pipeline's first leaf
(`f9365ede`) and terminal leaf (`3dd817cb`) were named in no tool at all. The
layer that RECORDS a release knew the pipeline; the layer that PERFORMS one did
not, and a human stood in the gap telling the runtime what had happened.

NOT exactly one TOOL — exactly one EXECUTOR. Five leaves are agent- or
human-executed by design and two leaves legitimately share one tool, so
requiring a tool entry point per leaf would force fake entry points onto human
work. That is the distinction `lib/release_bindings.py` exists to carry.

Enumeration here is DYNAMIC. The leaf set is walked out of `634913c2` at test
time, never pinned: a pinned list is a second copy of the pipeline, and the
first time a stage gains a step the copy and the world disagree — which is the
defect class this whole stream is about.

Verify command (locked in the spec; pytest collects these unittest cases):
    python3 -m pytest -q vault/tools/tests/test_release_runtime_binds_executors_v192.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
LIB = STUDIO_ROOT / "vault" / "tools" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import release_bindings as rb  # noqa: E402  - path set above


def _load_build_tool():
    """The real build tool, loaded to drive its real refusal path.

    Importing it runs its module body — which is exactly what
    `release_bindings.declarations_in_source` refuses to do when merely READING
    a declaration. Here the intent is the opposite: to exercise production code,
    the production module is what must run.
    """
    import importlib.util

    path = STUDIO_ROOT / "vault" / "tools" / "tropo-build-release.py"
    spec = importlib.util.spec_from_file_location("tropo_build_release_ac2", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["tropo_build_release_ac2"] = module
    spec.loader.exec_module(module)
    return module


class DeclaredLeavesResolve(unittest.TestCase):
    """The leaf set comes from the pipeline entry, not from a literal here."""

    def test_the_pipeline_declares_leaves_and_they_all_have_entries(self) -> None:
        leaves = rb.declared_leaves(STUDIO_ROOT)
        self.assertTrue(leaves, "634913c2 resolved to no leaves at all")
        self.assertEqual(
            len(leaves), len(set(leaves)), "a leaf uid appears twice in the walk"
        )
        for uid in leaves:
            with self.subTest(uid=uid):
                self.assertTrue(
                    (STUDIO_ROOT / "vault" / "files" / f"{uid}.md").exists(),
                    f"leaf {uid} is walked but has no vault entry",
                )

    def test_leaf_names_cover_every_leaf(self) -> None:
        """Refusal text names the leaf in words, so every leaf needs one."""
        leaves = rb.declared_leaves(STUDIO_ROOT)
        names = rb.leaf_names(STUDIO_ROOT)
        for uid in leaves:
            with self.subTest(uid=uid):
                self.assertTrue(names.get(uid), f"leaf {uid} resolved no name")


class EveryLeafBindsExactlyOneExecutor(unittest.TestCase):
    """AC2's coverage half."""

    def setUp(self) -> None:
        self.leaves = rb.declared_leaves(STUDIO_ROOT)
        self.bindings, self.source_of = rb.collect_from_tools(STUDIO_ROOT)

    def test_every_declared_leaf_has_a_binding(self) -> None:
        bound = {b.step_uid for b in self.bindings}
        missing = sorted(set(self.leaves) - bound)
        self.assertEqual(
            missing, [],
            "these declared leaves bind no executor, so a runner reaching them "
            "cannot say what performs them: " + ", ".join(missing),
        )

    def test_no_binding_names_a_step_that_is_not_a_live_leaf(self) -> None:
        """A binding on an archived or invented uid reads exactly like coverage
        from the outside, which is worse than an honest gap."""
        stray = sorted({b.step_uid for b in self.bindings} - set(self.leaves))
        self.assertEqual(stray, [], "bindings name non-leaves: " + ", ".join(stray))

    def test_exactly_one_binding_per_leaf(self) -> None:
        seen: dict = {}
        for binding in self.bindings:
            prior = seen.get(binding.step_uid)
            self.assertIsNone(
                prior,
                f"leaf {binding.step_uid} is bound twice "
                f"({prior.entry if prior else ''} and {binding.entry}); "
                "the runner could not say what comes next",
            )
            seen[binding.step_uid] = binding

    def test_every_binding_declares_a_known_kind(self) -> None:
        for binding in self.bindings:
            with self.subTest(step=binding.step_uid):
                self.assertIn(binding.kind, rb.KINDS)

    def test_every_executor_resolves_to_at_least_one_live_leaf(self) -> None:
        """The reverse direction. A declared executor bound to nothing live is
        a tool claiming a job the pipeline no longer has."""
        leaves = set(self.leaves)
        for binding in self.bindings:
            with self.subTest(entry=binding.entry):
                self.assertIn(binding.step_uid, leaves)


class KindsAreHonest(unittest.TestCase):
    """A kind is a claim about who acts. Both directions are checked."""

    def setUp(self) -> None:
        self.bindings, _ = rb.collect_from_tools(STUDIO_ROOT)

    def test_playbook_bindings_name_an_executor_class(self) -> None:
        for binding in self.bindings:
            if binding.kind == rb.KIND_PLAYBOOK:
                with self.subTest(step=binding.step_uid):
                    self.assertTrue(
                        binding.executor,
                        "a procedure with no executor is an event with no "
                        "emitter — the runner would stop and be unable to say "
                        "who acts",
                    )

    def test_tool_bindings_name_no_executor_class(self) -> None:
        """A deterministic step naming a human is a judgment step mislabelled."""
        for binding in self.bindings:
            if binding.kind == rb.KIND_TOOL:
                with self.subTest(step=binding.step_uid):
                    self.assertIsNone(binding.executor)

    def test_every_playbook_entry_resolves_to_something_real(self) -> None:
        """THE REGRESSION GUARD FOR A LIVE DEFECT, not a hypothetical.

        The contract's own worked example bound the cold-boot-walk leaf to
        `e2c7d185` — the AGENT RETIREMENT playbook — while the leaf names
        `6f3d2a18` in its Flow Rules. A runner prints `entry` to whoever is
        standing at a judgment slot, so uncorrected that sends a release
        operator into the retirement procedure. It was caught before either
        reader consumed it (argus-a157, 2026-08-25).

        Non-emptiness would not have caught it: `e2c7d185` is a real uid. What
        catches it is requiring the target to EXIST as a procedure or a leaf,
        and pairing that with the leaf-agreement test below.
        """
        files = STUDIO_ROOT / "vault" / "files"
        playbooks = STUDIO_ROOT / "vault" / "playbooks"
        for binding in self.bindings:
            if binding.kind != rb.KIND_PLAYBOOK:
                continue
            with self.subTest(step=binding.step_uid, entry=binding.entry):
                self.assertTrue(
                    (playbooks / f"{binding.entry}.md").exists()
                    or (files / f"{binding.entry}.md").exists(),
                    f"playbook binding for {binding.step_uid} names "
                    f"{binding.entry}, which resolves to no entry",
                )

    def test_a_playbook_entry_is_named_by_its_own_leaf(self) -> None:
        """The half that makes the test above load-bearing.

        `e2c7d185` exists, so existence alone passes. What fails is that the
        cold-boot-walk leaf never mentions it. A playbook binding must name
        either the leaf's own entry (the procedure IS that body) or a uid the
        leaf itself cites — never a third procedure nobody connected to it.
        """
        files = STUDIO_ROOT / "vault" / "files"
        for binding in self.bindings:
            if binding.kind != rb.KIND_PLAYBOOK:
                continue
            if binding.entry == binding.step_uid:
                continue  # the procedure is the leaf's own body
            leaf_text = (files / f"{binding.step_uid}.md").read_text(
                errors="replace"
            )
            with self.subTest(step=binding.step_uid):
                # assertTrue, not assertIn: assertIn dumps the entire leaf
                # entry into the failure output, and these run to 8 KB. The
                # person reading a red test needs the two uids, not the file.
                self.assertTrue(
                    binding.entry in leaf_text,
                    f"leaf {binding.step_uid} is bound to procedure "
                    f"{binding.entry}, which the leaf never mentions",
                )


class OneFactOneReader(unittest.TestCase):
    """The contract and the profile must not disagree about a leaf.

    `release_bindings`'s own docstring promises: "the AC5 release profile binds
    its slots with the SAME vocabulary, so a profile and a tool cannot disagree
    about what 'deterministic' means." An independent adversarial pass measured
    them disagreeing on 9 of 11 shared leaves — on `entry` for seven and on
    `executor` class for four — with no test comparing them. One fact, two
    readers, drifting, inside the stream built to end that.

    I had SEEN one of those divergences: cold-walking the profile printed
    `0cf86ea5 -> 5a4337ff/agent` against the contract's `0cf86ea5/argus`. I
    wrote "worth noting" and moved on. This test is what noticing should have
    become.
    """

    PROFILE = STUDIO_ROOT / "vault" / "files" / "6bf18510.md"

    def _profile_steps(self):
        import yaml

        fm = yaml.safe_load(self.PROFILE.read_text(errors="replace").split("---", 2)[1])
        steps = {}
        for slot in fm.get("slots") or []:
            for step in slot.get("steps") or []:
                # str() DELIBERATELY. `37996741` is all digits, so YAML parses
                # it as an INT — and `set(mine) & set(theirs)` then silently
                # dropped that leaf, comparing 11 of 12. The dropped one was the
                # only leaf that still disagreed. A type coercion hid a live
                # divergence from the test written to catch divergence.
                steps[str(step["step_uid"])] = (
                    step.get("kind"), step.get("entry"), step.get("executor")
                )
        return steps

    def test_the_profile_and_the_contract_agree_on_every_shared_leaf(self) -> None:
        bindings, _ = rb.collect_from_tools(STUDIO_ROOT)
        mine = {b.step_uid: (b.kind, b.entry, b.executor) for b in bindings}
        theirs = self._profile_steps()
        shared = sorted(set(mine) & set(theirs))
        self.assertTrue(shared, "the profile shares no leaves with the contract")
        # EVERY leaf, not merely the ones both sides happen to key alike. Without
        # this the comparison silently narrowed to 11 of 12 and reported clean.
        self.assertEqual(
            len(shared), len(rb.declared_leaves(STUDIO_ROOT)),
            f"the profile and the contract share only {len(shared)} of "
            f"{len(rb.declared_leaves(STUDIO_ROOT))} declared leaves; a leaf "
            f"missing from either side is not compared, and an uncompared leaf "
            f"is where a disagreement hides",
        )
        disagree = [u for u in shared if mine[u] != theirs[u]]
        self.assertEqual(
            [], disagree,
            "the profile and the executor contract disagree on:\n  "
            + "\n  ".join(
                f"{u}\n     contract: {mine[u]}\n     profile : {theirs[u]}"
                for u in disagree
            ),
        )

    def test_every_tool_entry_resolves_to_something_runnable(self) -> None:
        """The gap that let two of these drift unnoticed.

        Playbook entries were existence-checked from the start; tool entries
        were not, so `tropo-release-validation-gate.py:capture` sat in the
        contract naming a callable that does not exist — `capture` is an
        argparse subcommand and the function is `capture_baseline`.
        """
        bindings, _ = rb.collect_from_tools(STUDIO_ROOT)
        tools_dir = STUDIO_ROOT / "vault" / "tools"
        for binding in bindings:
            if binding.kind != rb.KIND_TOOL:
                continue
            entry = binding.entry
            with self.subTest(step=binding.step_uid, entry=entry):
                if entry.startswith("python3 "):
                    target = entry.split()[1]
                    self.assertTrue(
                        (STUDIO_ROOT / target).exists(),
                        f"command entry names {target}, which does not exist",
                    )
                    continue
                self.assertIn(":", entry, "a tool entry names a callable")
                script, callable_name = entry.split(":", 1)
                path = tools_dir / script
                self.assertTrue(path.exists(), f"{script} does not exist")
                self.assertIn(
                    f"def {callable_name}(", path.read_text(errors="replace"),
                    f"{script} declares no callable named {callable_name!r}; a "
                    f"runner told to invoke it would find nothing",
                )


class RefusalsNameThePipelineStep(unittest.TestCase):
    """AC2's second half: a refusal says WHERE IN THE RELEASE, not just which
    script raised. The step uid is the coordinate that means something to a
    person standing there."""

    def test_a_triggered_refusal_names_the_step_uid(self) -> None:
        """Triggered from the PRODUCTION path, not constructed here.

        The first version of this test raised `StepRefusal` in its own body and
        asserted the string it had just built contained the uid it had just
        passed in. An independent adversarial pass measured zero production call
        sites: delete the class from the runtime and this stayed green. A test
        that supplies its own subject proves the constructor works and nothing
        about the release.

        This drives the real fan-in verification with a plan that names no
        manifest ref — one of the ~80 real stop sites — and asserts the message
        the operator would actually read names leaf f9365ede.
        """
        build = _load_build_tool()

        class _Identity:
            plan_uid = "aaaaaaaa"
            run_uid = "bbbbbbbb"

        class _Runtime:
            def read_vault_entry(self, uid):
                return {"frontmatter": {}}  # a plan naming no fan_in_manifest_ref

        with self.assertRaises(Exception) as caught:
            build._verify_fan_in_against_manifest(_Identity(), _Runtime())
        message = str(caught.exception)
        self.assertIn(
            "f9365ede", message,
            "a real refusal in the build path must name the pipeline step it "
            "belongs to, not only the script that raised it. Message was: "
            + message,
        )
        self.assertIn("validate-release-plan-fan-in", message,
                      "the readable leaf name travels with the uid")

    def test_the_production_refusal_is_priced_in_its_text(self) -> None:
        """The harm rides in the operator-visible message, not only in a
        source comment nobody reads at 2am."""
        build = _load_build_tool()

        class _Identity:
            plan_uid = "aaaaaaaa"

        class _Runtime:
            def read_vault_entry(self, uid):
                return {"frontmatter": {}}

        with self.assertRaises(Exception) as caught:
            build._verify_fan_in_against_manifest(_Identity(), _Runtime())
        self.assertIn("refusing prevents:", str(caught.exception))

    def test_step_refusal_has_production_callers(self) -> None:
        """The measurement that was zero. A vocabulary with no callers is a
        criterion satisfied by its own test."""
        tools = STUDIO_ROOT / "vault" / "tools"
        callers = []
        for path in sorted(tools.glob("*.py")):
            text = path.read_text(errors="replace")
            if "StepRefusal" in text or "_step_refusal_text" in text:
                callers.append(path.name)
        self.assertTrue(
            callers,
            "StepRefusal has no production callers; AC2's refusal half would be "
            "satisfied entirely by the test that asserts it",
        )

    def test_the_readable_leaf_name_travels_with_the_uid(self) -> None:
        names = rb.leaf_names(STUDIO_ROOT)
        leaf = rb.declared_leaves(STUDIO_ROOT)[0]
        refusal = rb.StepRefusal(
            leaf, "the locked plan names no dev-specs", step_name=names[leaf]
        )
        self.assertIn(leaf, refusal.rendered())
        self.assertIn(names[leaf], refusal.rendered())

    def test_a_refusal_that_cannot_name_its_step_is_refused_at_construction(
        self,
    ) -> None:
        """2am is the wrong time to discover a message is uninformative."""
        for bad in ("", None, "nope"):
            with self.subTest(step_uid=bad):
                with self.assertRaises(rb.BindingError):
                    rb.StepRefusal(bad, "something went wrong")

    def test_priced_is_reported_but_never_required_here(self) -> None:
        """AC3 requires the harm text; this class must NOT, or the enumeration
        it depends on could never observe an unpriced site."""
        leaf = rb.declared_leaves(STUDIO_ROOT)[0]
        unpriced = rb.StepRefusal(leaf, "reason")
        self.assertFalse(unpriced.priced)
        priced = rb.StepRefusal(leaf, "reason", harm="an unwithdrawable claim")
        self.assertTrue(priced.priced)
        self.assertIn("an unwithdrawable claim", priced.rendered())


class NegativeControls(unittest.TestCase):
    """Each asserts the gate fires on the shape it exists for. A green suite
    over a mechanism that cannot go red is worse than no suite."""

    def test_a_binding_on_a_nonexistent_uid_fails(self) -> None:
        leaves = rb.declared_leaves(STUDIO_ROOT)
        with self.assertRaises(rb.BindingError):
            rb.collect(
                [{
                    "step_uid": "deadbeef",
                    "kind": rb.KIND_TOOL,
                    "entry": "x.py:main",
                    "description": "invented",
                }],
                leaves,
            )

    def test_a_playbook_binding_with_no_executor_fails(self) -> None:
        with self.assertRaises(rb.BindingError) as caught:
            rb.binding_from_declaration({
                "step_uid": "c6b61fb9",
                "kind": rb.KIND_PLAYBOOK,
                "entry": "6f3d2a18",
                "description": "no executor named",
            })
        self.assertIn("executor", str(caught.exception))

    def test_a_tool_binding_that_names_an_executor_fails(self) -> None:
        with self.assertRaises(rb.BindingError):
            rb.binding_from_declaration({
                "step_uid": "3dd817cb",
                "kind": rb.KIND_TOOL,
                "entry": "tropo-publish-release.py:cmd_fire",
                "executor": "human",
                "description": "mislabelled judgment step",
            })

    def test_two_bindings_for_one_leaf_fail(self) -> None:
        leaves = rb.declared_leaves(STUDIO_ROOT)
        row = {
            "step_uid": leaves[0],
            "kind": rb.KIND_TOOL,
            "entry": "a.py:main",
            "description": "first",
        }
        with self.assertRaises(rb.BindingError) as caught:
            rb.collect([row, dict(row, entry="b.py:main")], leaves)
        self.assertIn("bound twice", str(caught.exception))

    def test_a_positional_declaration_is_refused(self) -> None:
        """Tuples reorder silently and this contract has two readers."""
        with self.assertRaises(rb.BindingError):
            rb.binding_from_declaration(("3dd817cb", "tool", "x.py:main", "d"))

    def test_an_unknown_key_is_refused(self) -> None:
        with self.assertRaises(rb.BindingError):
            rb.binding_from_declaration({
                "step_uid": "3dd817cb",
                "kind": rb.KIND_TOOL,
                "entry": "x.py:main",
                "description": "d",
                "runner": "typo for executor",
            })

    def test_a_computed_binding_value_is_refused(self) -> None:
        """Bindings are data. This reader must never execute a release tool to
        learn what it declares, so a computed value cannot be admitted."""
        import tempfile

        source = (
            "PIPELINE_BINDINGS = (\n"
            "    {'step_uid': compute_it(), 'kind': 'tool',\n"
            "     'entry': 'x.py:main', 'description': 'd'},\n"
            ")\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tropo-fake-release.py"
            path.write_text(source)
            with self.assertRaises(rb.BindingError):
                rb.declarations_in_source(path)

    def test_a_module_constant_IS_admitted(self) -> None:
        """The companion to the test above: refusing constants would push every
        declarer into duplicating a uid it already defines beside the binding."""
        import tempfile

        source = (
            "FREEZE_STEP = '7de2c49f'\n"
            "PIPELINE_BINDINGS = (\n"
            "    {'step_uid': FREEZE_STEP, 'kind': KIND_TOOL,\n"
            "     'entry': 'x.py:decide', 'description': 'd'},\n"
            ")\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tropo-fake-release.py"
            path.write_text(source)
            rows = rb.declarations_in_source(path)
        self.assertEqual(rows[0]["step_uid"], "7de2c49f")
        self.assertEqual(rows[0]["kind"], rb.KIND_TOOL)

    def test_reading_a_declaration_does_not_execute_the_module(self) -> None:
        """The reason this reader parses instead of importing. These tools
        build and publish releases; importing one to ask what it declares would
        run its module body."""
        import tempfile

        source = (
            "raise SystemExit('module body executed')\n"
            "PIPELINE_BINDINGS = ()\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tropo-fake-release.py"
            path.write_text(source)
            self.assertEqual(rb.declarations_in_source(path), [])


class TheDeclarationSitesAreReal(unittest.TestCase):
    """Coverage must come from the tools, not from one convenient literal."""

    def test_the_tool_side_declares_the_deterministic_leaves(self) -> None:
        bindings, source_of = rb.collect_from_tools(STUDIO_ROOT)
        contract_file = Path(rb.__file__).name
        tool_declared = [
            b for b in bindings
            if source_of[b.step_uid].name != contract_file
        ]
        self.assertGreaterEqual(
            len(tool_declared), 5,
            "the tools that perform the release must declare their own leaves; "
            "collapsing every binding into the contract module would restore "
            "the gap AC2 exists to close",
        )
        for binding in tool_declared:
            with self.subTest(step=binding.step_uid):
                self.assertEqual(binding.kind, rb.KIND_TOOL)

    def test_the_two_leaves_that_share_one_tool_are_still_two_bindings(
        self,
    ) -> None:
        """Sharing a tool is legitimate; sharing a binding is not. capture
        fixes the baseline at fan-in, compare re-runs it at Verify."""
        bindings, _ = rb.collect_from_tools(STUDIO_ROOT)
        gate = [b for b in bindings if "validation-gate" in b.entry]
        self.assertEqual(len(gate), 2)
        self.assertNotEqual(gate[0].step_uid, gate[1].step_uid)
        self.assertNotEqual(gate[0].entry, gate[1].entry)


if __name__ == "__main__":
    unittest.main()
