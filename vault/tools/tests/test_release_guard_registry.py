#!/usr/bin/env python3
"""v1.95 Spine B (f015997f8d8e) — the build's guards are registered Gates.

tropo-build-release.py called its guards directly, in sequence, so the v1.94
box failed at the first one each attempt (eight attempts) while the release
preflight built for exactly this in 2fae6312 could not see a single build
guard. This suite grows with the roster; the first guard registered is the
smallest, assert_mission_brief_slot, as the shape proof (spec §Handoff).

Mutation clauses, each proven here both ways:
  * drop register_build_gates from build_registry and Registry goes red;
  * the gate REFUSES a planted leak and an absent slot, PASSES the template;
  * at lock-static the gate is skipped-inputs-absent (the box does not exist);
  * the build tool's wrapper and the gate read ONE definition of the markers.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import git_env  # noqa: E402  (contained git for the ComposedPath fixture tree)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

from lib import build_guards  # noqa: E402
from lib import release_gates  # noqa: E402


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PREFLIGHT = _load("release_preflight_guard_registry", "tropo-release-preflight.py")
GATE = "build-mission-brief-slot"
TEMPLATE = TOOLS.parents[1] / "vault" / "templates" / "root-docs" / "mission-brief.template.md"


class _Box(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="guard-registry-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.box = self.tmp / "tropo-os-v9.9.9"
        (self.box / ".tropo-studio").mkdir(parents=True)

    def _slot(self, body: str) -> None:
        (self.box / build_guards.MISSION_BRIEF_SLOT_REL).write_text(body, encoding="utf-8")

    def _run(self, phase: str = "candidate", context=None):
        registry = PREFLIGHT.build_registry()
        ctx = {"extracted_tree": str(self.box)} if context is None else context
        return {o.gate_id: o for o in registry.run_phase(phase, ctx)}


class Registry(_Box):
    def test_build_mission_brief_slot_is_registered_at_candidate(self):
        registry = PREFLIGHT.build_registry()
        self.assertIn(GATE, registry)
        self.assertIn(GATE, [g.gate_id for g in registry.gates_for_phase("candidate")])
        self.assertNotIn(GATE, [g.gate_id for g in registry.gates_for_phase("lock-static")])

    def test_every_roster_row_has_a_verifier_and_no_verifier_is_stray(self):
        self.assertEqual({r[0] for r in PREFLIGHT.BUILD_GUARD_ROSTER},
                         set(PREFLIGHT.BUILD_GUARD_VERIFIERS))

    def test_declared_inputs_are_known_to_the_input_table(self):
        for gate_id, _cls, inputs, _desc in PREFLIGHT.BUILD_GUARD_ROSTER:
            for name in inputs:
                self.assertIn(name, release_gates.INPUT_FIRST_AVAILABLE,
                              "%s declares unknown input %r" % (gate_id, name))

    # The three ids Spine B AC1's verify command names (f015997f8d8e), delegating
    # to the census assertions below -- a non-author runs the command verbatim.
    def test_every_build_guard_is_registered(self):
        Census("test_every_build_guard_is_registered").debug()

    def test_no_direct_guard_calls_in_build_tool(self):
        Census("test_no_direct_guard_calls_in_build_tool").debug()

    def test_unreached_gates_empty_for_build_phases(self):
        Census("test_unreached_gates_empty_for_build_phases").debug()

    def test_mutation_unregistered_registry_lacks_the_gate(self):
        bare = release_gates.GateRegistry()
        PREFLIGHT.register_governance_gates(bare)
        self.assertNotIn(GATE, bare)
        PREFLIGHT.register_build_gates(bare)
        self.assertIn(GATE, bare)

class MissionBriefSlotGate(_Box):
    def test_generic_template_passes(self):
        self._slot(TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(self._run()[GATE].verdict, release_gates.VERDICT_PASS)

    def test_planted_argo_prose_is_refused_naming_the_markers(self):
        self._slot("# Mission Brief\n\nArgo builds Tropo. Metis designs forward.\n")
        out = self._run()[GATE]
        self.assertEqual(out.verdict, release_gates.VERDICT_REFUSED)
        self.assertEqual(out.evidence["count"], 2)   # no <FILL:> AND markers
        self.assertIn("argo", out.detail)
        self.assertIn("metis", out.detail)

    def test_word_boundary_cargo_is_not_argo(self):
        self._slot("# <FILL: name>\n\nWe ship cargo and study the Argonauts.\n")
        self.assertEqual(self._run()[GATE].verdict, release_gates.VERDICT_PASS)

    def test_absent_slot_is_refused(self):
        out = self._run()[GATE]
        self.assertEqual(out.verdict, release_gates.VERDICT_REFUSED)
        self.assertIn("absent", out.detail)

    def test_lock_static_skips_it_because_the_box_does_not_exist(self):
        registry = PREFLIGHT.build_registry()
        ids = [g.gate_id for g in registry.gates_for_phase("lock-static")]
        self.assertNotIn(GATE, ids)
        # And with the input missing at its own phase, it reports skipped, never pass.
        out = self._run(context={})[GATE]
        self.assertEqual(out.verdict, release_gates.VERDICT_SKIPPED)


BOX_GATES = (
    "build-mission-brief-slot", "build-shipped-surfaces", "build-no-stale-system-dir",
    "build-no-studio-identity", "build-shadow-substitutions", "build-release-harness",
    "build-box-self-test", "build-box-registry-rows",
    # Spine A AC7's reachability rows (f015de6b3a18), registered here
    "build-doc-currency", "build-no-shell-instructions", "build-changelog-names-version",
    "build-memory-surfaces",
    # The score-formula doctrine the shipped curator reads at boot. Absent from
    # every box for six releases while the build reported it copied — the
    # skeleton step deleted the folder it had been copied into. talos-t66,
    # 2026-09-08, ship-artifact f0155122c0b8.
    "build-score-formula-doctrine",
)
TREE_GATES = ("build-covenant-floor", "build-overwrite-guard", "build-no-absolute-paths",
              "build-activation-key")
#: The build tool's guard functions that Spine B AC1 says main() may not call
#: directly once registered. Their definitions stay (wrappers other tests call).
DIRECT_CALL_FORBIDDEN = (
    "assert_mission_brief_slot", "assert_shipped_surfaces", "assert_no_stale_system_dir",
    "assert_no_studio_identity", "verify_shadow_substitutions", "guard_overwrite",
    "require_release_authorization", "attested_build_authorization",
)


class Census(unittest.TestCase):
    """AC1: every build guard is a registered Gate and nothing else decides when it runs."""

    def test_every_build_guard_is_registered(self):
        registry = PREFLIGHT.build_registry()
        for gate_id in BOX_GATES + TREE_GATES:
            self.assertIn(gate_id, registry, gate_id)

    def test_box_readers_compute_to_candidate_and_tree_readers_to_lock_static(self):
        registry = PREFLIGHT.build_registry()
        candidate = {g.gate_id for g in registry.gates_for_phase("candidate")}
        lock_static = {g.gate_id for g in registry.gates_for_phase("lock-static")}
        for gate_id in BOX_GATES:
            self.assertIn(gate_id, candidate, gate_id)
            self.assertNotIn(gate_id, lock_static, gate_id)
        for gate_id in TREE_GATES:
            self.assertIn(gate_id, lock_static, gate_id)
            self.assertNotIn(gate_id, candidate, gate_id)

    def test_unreached_gates_empty_for_build_phases(self):
        registry = PREFLIGHT.build_registry()   # no fire verifiers: the CLI's and lock tool's registry
        self.assertEqual(registry.unreached_gates(["lock-static", "candidate"]), [])

    def test_no_direct_guard_calls_in_build_tool(self):
        """AST walk of tropo-build-release.py: a Name/Attribute call to any
        registered guard outside its own def is a direct call. Known-negative:
        re-add `assert_shipped_surfaces(build_dir)` anywhere in main() and this
        names it."""
        import ast
        src = (TOOLS / "tropo-build-release.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if name in DIRECT_CALL_FORBIDDEN:
                offenders.append("%s at line %d" % (name, node.lineno))
        self.assertEqual(offenders, [], "direct guard call(s) survive in the build tool: %s" % offenders)

    def test_the_candidate_step_exists_and_refuses_on_skipped(self):
        src = (TOOLS / "tropo-build-release.py").read_text(encoding="utf-8")
        self.assertIn("def step_10_9_candidate_gates(", src)
        self.assertIn("step_10_9_candidate_gates(build_dir, activation_uid, dist_dir,", src)
        # the version being cut reaches the candidate context (v1.95 candidate #1 carried '')
        self.assertIn("version_string=new_version)", src)
        self.assertIn("o.verdict != preflight.VERDICT_PASS", src)   # skipped is NOT ok at the seal


class BoxGatesBothWays(_Box):
    """Each pure box gate refuses its planted break and passes the cured box."""

    def _cured_box(self):
        for d in build_guards.SHIPPED_SURFACES:
            (self.box / d).mkdir(exist_ok=True)
        (self.box / "00-tropo-nav" / "index.md").write_text("# nav\n")
        (self.box / "vault" / "updates").mkdir(parents=True, exist_ok=True)
        (self.box / "vault" / "updates" / ".gitkeep").write_text("")
        (self.box / "vault" / "00-index.jsonl").write_text(
            '{"uid": "11111111", "type": "note", "path": "vault/files/11111111.md"}\n')
        self._slot(TEMPLATE.read_text(encoding="utf-8"))

    def test_shipped_surfaces(self):
        self._cured_box()
        self.assertEqual(self._run()["build-shipped-surfaces"].verdict, release_gates.VERDICT_PASS)
        shutil.rmtree(self.box / "03-design")
        (self.box / "00-tropo-nav" / "index.md").unlink()
        out = self._run()["build-shipped-surfaces"]
        self.assertEqual(out.verdict, release_gates.VERDICT_REFUSED)
        self.assertEqual(out.evidence["count"], 2)   # missing folder AND empty nav, both named

    def test_no_stale_system_dir(self):
        self._cured_box()
        self.assertEqual(self._run()["build-no-stale-system-dir"].verdict, release_gates.VERDICT_PASS)
        (self.box / "system" / "updates").mkdir(parents=True)
        (self.box / "system" / "updates" / "x.md").write_text("stale\n")
        out = self._run()["build-no-stale-system-dir"]
        self.assertEqual(out.verdict, release_gates.VERDICT_REFUSED)
        self.assertIn("system/ shipped", out.detail)

    def test_no_studio_identity(self):
        self._cured_box()
        self.assertEqual(self._run()["build-no-studio-identity"].verdict, release_gates.VERDICT_PASS)
        (self.box / ".tropo").mkdir(exist_ok=True)
        (self.box / ".tropo" / "studio-identity.md").write_text("---\nstudio_id: b4e250caf19a\n---\n")
        with (self.box / "vault" / "00-index.jsonl").open("a") as fh:
            fh.write('{"uid": "b4e2b7f272e8", "type": "entity", "subtype": "vault-entity", "path": "vault/files/b4e2b7f272e8.md"}\n')
        out = self._run()["build-no-studio-identity"]
        self.assertEqual(out.verdict, release_gates.VERDICT_REFUSED)
        self.assertEqual(out.evidence["count"], 2)   # manifest AND pair, both named

    def test_every_candidate_gate_reports_and_the_count_matches(self):
        """AC4's shape: outcomes == registered candidate gates, whatever they say.
        The subprocess gates report operational/refused against a fixture box
        (no harness, no tropo-test.py) — they REPORT, they do not vanish."""
        self._cured_box()
        registry = PREFLIGHT.build_registry()
        outcomes = registry.run_phase("candidate", {"source_tree": str(TOOLS.parents[1]),
                                                    "extracted_tree": str(self.box)})
        self.assertEqual(len(outcomes), len(registry.gates_for_phase("candidate")))
        self.assertEqual({o.gate_id for o in outcomes}, set(BOX_GATES))
        by_id = {o.gate_id: o for o in outcomes}
        self.assertNotEqual(by_id["build-box-self-test"].verdict, release_gates.VERDICT_PASS)

    def test_skipped_is_reported_when_the_box_input_is_absent(self):
        """THE SKIPPED ARM (AC4): no extracted_tree → every candidate gate reports
        skipped-inputs-absent, count still matches; the seal must refuse on it."""
        registry = PREFLIGHT.build_registry()
        outcomes = registry.run_phase("candidate", {"source_tree": str(TOOLS.parents[1])})
        self.assertEqual(len(outcomes), len(registry.gates_for_phase("candidate")))
        self.assertTrue(all(o.verdict == release_gates.VERDICT_SKIPPED for o in outcomes))
        self.assertTrue(all(not (o.verdict == release_gates.VERDICT_PASS) for o in outcomes))


class Preflight(unittest.TestCase):
    """AC2: the existing preflight reports EVERY build-guard failure at once,
    each naming its harm, one evidence row per gate carrying tree_commit."""

    def _tree(self):
        tmp = Path(tempfile.mkdtemp(prefix="guard-preflight-tree-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        tools = tmp / "vault" / "tools"
        (tools / "tests").mkdir(parents=True)
        # the instruments the lock-static gates need in a tree
        (tools / "tests" / "test_clean_update_floor.py").write_text(
            "#!/usr/bin/env python3\nimport sys\nprint('floor stub PASS')\nsys.exit(0)\n")
        shutil.copy(TOOLS / "tropo-validate-no-absolute-paths.py", tools / "tropo-validate-no-absolute-paths.py")
        (tmp / ".tropo").mkdir()
        (tmp / ".tropo" / "version.md").write_text("---\nversion: 9.9.8\n---\n")
        # a clean shipped tool for ship-python-floor
        (tools / "tropo-probe.py").write_text(
            '#!/usr/bin/env python3\n"""---\nuid: deadbeef\ntype: tool\nstatus: active\nextraction_scope: ship\n---\n"""\n'
            "from __future__ import annotations\n\n\ndef probe(v: str | None = None):\n    return v\n")
        releases = tmp / "releases"
        releases.mkdir()
        return tmp, tools, releases

    def _context(self, tmp, releases, version="9.9.9"):
        from lib import release_gate_inputs
        ctx = release_gate_inputs.build_context(tmp, version_string=version)
        ctx["releases_root"] = str(releases)
        return ctx

    #: The three plants AC2 reports together, as helpers so ComposedPath
    #: plants and cures exactly the same three rather than a second set.
    _CLEAN_PROBE = (
        '#!/usr/bin/env python3\n"""---\nuid: deadbeef\ntype: tool\nstatus: active\n'
        'extraction_scope: ship\n---\n"""\n'
        "from __future__ import annotations\n\n\ndef probe(v: str | None = None):\n    return v\n")

    def _plant_three(self, tools, releases):
        (releases / "v9.9.9" / "testing" / "tropo-os-v9.9.9").mkdir(parents=True, exist_ok=True)
        planted = "ROOT = '/" + "Users/somebody/git/tropo-studios/argo-os'\n"
        (tools / "tests" / "fixture_paths.py").write_text(planted)
        (tools / "tropo-probe.py").write_text(
            '#!/usr/bin/env python3\n"""---\nuid: deadbeef\ntype: tool\nstatus: active\n'
            'extraction_scope: ship\n---\n"""\n'
            "\n\ndef probe(v: str | None = None):\n    return v\n")

    def _cure_three(self, tools, releases):
        stale = releases / "v9.9.9"
        if stale.exists():
            shutil.rmtree(stale)
        fixture = tools / "tests" / "fixture_paths.py"
        if fixture.exists():
            fixture.unlink()
        (tools / "tropo-probe.py").write_text(self._CLEAN_PROBE)

    def _fixture_box(self, tmp):
        """A box shaped enough for the pure box gates to judge it."""
        box = tmp / "box" / "tropo-os-v9.9.9"
        (box / ".tropo-studio").mkdir(parents=True, exist_ok=True)
        for d in build_guards.SHIPPED_SURFACES:
            (box / d).mkdir(parents=True, exist_ok=True)
        (box / "00-tropo-nav" / "index.md").write_text("# nav\n")
        (box / "vault" / "updates").mkdir(parents=True, exist_ok=True)
        (box / "vault" / "updates" / ".gitkeep").write_text("")
        (box / "vault" / "00-index.jsonl").write_text(
            '{"uid": "11111111", "type": "note", "path": "vault/files/11111111.md"}\n')
        (box / build_guards.MISSION_BRIEF_SLOT_REL).write_text(
            TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        return box

    def test_three_planted_tree_violations_reported_together(self):
        """Three guards, one run, three refused outcomes — never first-failure.
        (The spec's third plant, a stale version stamp in the box, is Spine A
        A3's box-side guard; the tree-side plant here is the interpreter floor.)"""
        tmp, tools, releases = self._tree()
        # (a) an unstamped testing dir for the target version -> overwrite guard
        (releases / "v9.9.9" / "testing" / "tropo-os-v9.9.9").mkdir(parents=True)
        # (b) a /Users/ path inside a shipped test fixture -> absolute paths
        # the planted literal is assembled at runtime so THIS file does not carry it
        planted = "ROOT = '/" + "Users/somebody/git/tropo-studios/argo-os'\n"
        (tools / "tests" / "fixture_paths.py").write_text(planted)
        # (c) a PEP-604 annotation without the future import -> python floor
        (tools / "tropo-probe.py").write_text(
            '#!/usr/bin/env python3\n"""---\nuid: deadbeef\ntype: tool\nstatus: active\nextraction_scope: ship\n---\n"""\n'
            "\n\ndef probe(v: str | None = None):\n    return v\n")
        registry = PREFLIGHT.build_registry()
        outcomes = {o.gate_id: o for o in registry.run_phase("lock-static", self._context(tmp, releases))}
        refused = sorted(g for g, o in outcomes.items() if o.verdict == release_gates.VERDICT_REFUSED)
        self.assertEqual(refused, ["build-no-absolute-paths", "build-overwrite-guard", "ship-python-floor"])
        for gate_id in refused:
            self.assertTrue(registry.get(gate_id).description, gate_id)   # each names its harm
            self.assertTrue(registry.get(gate_id).refusal_class, gate_id)
        self.assertIn("fixture_paths.py:1", outcomes["build-no-absolute-paths"].detail)
        self.assertIn("no version.md stamp", outcomes["build-overwrite-guard"].detail)

    def test_clean_tree_all_pass_one_row_per_gate_with_tree_commit(self):
        import json
        tmp, tools, releases = self._tree()
        run_dir = tmp / "run"
        registry = PREFLIGHT.build_registry()
        ctx = self._context(tmp, releases)
        ctx["tree_commit"] = "f" * 40   # a scratch tree has no git; the caller names it
        outcomes = registry.run_phase("lock-static", ctx)
        bad = [(o.gate_id, o.verdict) for o in outcomes
               if o.verdict not in (release_gates.VERDICT_PASS, release_gates.VERDICT_SKIPPED)]
        self.assertEqual(bad, [])
        path = release_gates.write_evidence(run_dir, "lock-static", outcomes, registry,
                                            tree_commit=ctx["tree_commit"])
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        self.assertEqual(len(rows), len(registry.gates_for_phase("lock-static")))
        self.assertTrue(all(r["tree_commit"] == "f" * 40 for r in rows))

    def test_overwrite_guard_honours_force_and_agreeing_stamp(self):
        tmp, tools, releases = self._tree()
        build = releases / "v9.9.9" / "builds" / "tropo-os-v9.9.9"
        (build / ".tropo").mkdir(parents=True)
        (build / ".tropo" / "version.md").write_text("version: 9.9.8\n")   # another version's content
        registry = PREFLIGHT.build_registry()
        ctx = self._context(tmp, releases)
        out = {o.gate_id: o for o in registry.run_phase("lock-static", ctx)}["build-overwrite-guard"]
        self.assertEqual(out.verdict, release_gates.VERDICT_REFUSED)
        self.assertIn("9.9.8", out.detail)
        ctx["force"] = True
        out = {o.gate_id: o for o in registry.run_phase("lock-static", ctx)}["build-overwrite-guard"]
        self.assertEqual(out.verdict, release_gates.VERDICT_PASS)
        (build / ".tropo" / "version.md").write_text("version: 9.9.9\n")
        ctx["force"] = False
        out = {o.gate_id: o for o in registry.run_phase("lock-static", ctx)}["build-overwrite-guard"]
        self.assertEqual(out.verdict, release_gates.VERDICT_PASS)

    def test_activation_key_skips_without_an_activation_and_refuses_a_bogus_one(self):
        registry = PREFLIGHT.build_registry()
        from lib import release_gate_inputs
        ctx = release_gate_inputs.build_context(TOOLS.parents[1], version_string="9.9.9")
        out = {o.gate_id: o for o in registry.run_phase("lock-static", ctx)}["build-activation-key"]
        self.assertEqual(out.verdict, release_gates.VERDICT_SKIPPED)
        ctx = release_gate_inputs.build_context(TOOLS.parents[1], version_string="9.9.9",
                                                activation_uid="0000000000ab")
        out = {o.gate_id: o for o in registry.run_phase("lock-static", ctx)}["build-activation-key"]
        self.assertEqual(out.verdict, release_gates.VERDICT_REFUSED)
        self.assertIn("no valid Pipeline Activation Key", out.detail)


class BuildOwnLockStaticPass(unittest.TestCase):
    """The build runs the lock-static phase itself at Step 0.4 (before any
    write); a standalone invocation with no activation is REFUSED there by
    build-activation-key — the old 'no key, no build' held, not waved through
    as skipped."""

    @classmethod
    def setUpClass(cls):
        cls.build = _load("build_release_guard_registry", "tropo-build-release.py")

    def test_standalone_build_without_activation_is_refused_at_step_0_4(self):
        import contextlib, io
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                self.build.step_0_4_lock_static_gates(None, "9.9.9")
        self.assertEqual(cm.exception.code, 3)
        self.assertIn("build-activation-key", err.getvalue())

    def test_bogus_activation_is_refused_not_skipped(self):
        import contextlib, io
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit):
                self.build.step_0_4_lock_static_gates("0000000000ab", "9.9.9")
        self.assertIn("no valid Pipeline Activation Key", err.getvalue())


class BlankPathInputNeverJudgesTheLiveStudio(unittest.TestCase):
    """Talos T62's finding (evt_32a4374c291f9a09_00000005): run_phase treats an
    empty string as PRESENT, so Path('') is the current directory and five box
    gates PASSED while judging the live Studio. The registry's absence rule is
    by phase, not type (a settled contract), so the cure is in the build
    verifiers: a blank path is an operational error naming itself. Mutation:
    remove _tree() and this test reports passes again."""

    def test_blank_extracted_tree_is_an_error_on_every_box_gate(self):
        registry = PREFLIGHT.build_registry()
        outcomes = registry.run_phase("candidate", {"extracted_tree": "", "source_tree": str(TOOLS.parents[1]),
                                                    "version_string": "9.9.9"})
        self.assertTrue(outcomes)
        for o in outcomes:
            with self.subTest(gate=o.gate_id):
                self.assertNotEqual(o.verdict, release_gates.VERDICT_PASS, o.detail)
                self.assertIn("blank", o.detail)
        # and nothing judged the live tree: the identity gate would have REFUSED on
        # this Studio's own manifest had it read the cwd
        self.assertNotIn("studio-identity.md is present", {o.gate_id: o.detail for o in outcomes}["build-no-studio-identity"])

    def test_blank_source_tree_is_an_error_on_the_tree_gates(self):
        registry = PREFLIGHT.build_registry()
        out = {o.gate_id: o for o in registry.run_phase("lock-static", {"source_tree": "   ", "version_string": "9.9.9",
                                                                      "releases_root": str(TOOLS.parents[1])})}
        for gate_id in ("build-covenant-floor", "build-no-absolute-paths"):
            self.assertEqual(out[gate_id].verdict, release_gates.VERDICT_ERROR, out[gate_id].detail)


class EvidenceRowsCarryTheTree(unittest.TestCase):
    """AC2: every evidence row names the commit the phase ran against."""

    def test_write_evidence_carries_tree_commit(self):
        import json
        run_dir = Path(tempfile.mkdtemp(prefix="guard-evidence-"))
        self.addCleanup(shutil.rmtree, run_dir, True)
        registry = PREFLIGHT.build_registry()
        outcomes = registry.run_phase("candidate", {})
        path = release_gates.write_evidence(run_dir, "candidate", outcomes, registry,
                                            tree_commit="abc123def456")
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        self.assertEqual(len(rows), len(registry.gates_for_phase("candidate")))
        self.assertTrue(all(r["tree_commit"] == "abc123def456" for r in rows))

    def test_build_context_names_its_tree(self):
        from lib import release_gate_inputs
        ctx = release_gate_inputs.build_context(TOOLS.parents[1])
        self.assertRegex(ctx["tree_commit"], r"^[0-9a-f]{40}$")


class Runner(unittest.TestCase):
    """AC3: the runner refuses a real build without a clean lock-static preflight
    for THIS tree. Four arms including the positive; mutation: remove the
    require_clean_lock_static call from the adapter and the three refusals go
    red while the positive stays green."""

    @classmethod
    def setUpClass(cls):
        cls.runner = _load("release_run_guard_registry", "tropo-release-run.py")
        cls.runner.RUNTIME_DRIVER = lambda *a, **k: None
        cls.head = cls.runner._tree_head(TOOLS.parents[1])
        assert cls.head, "this suite needs a git tree"

    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp(prefix="guard-runner-")).resolve()
        self.addCleanup(shutil.rmtree, self.run_dir, True)
        self.calls = []

    def _ctx(self):
        return self.runner.RunContext(vault_root=TOOLS.parents[1], release_plan_uid="f015ba71c711",
                                      run_dir=self.run_dir, activation_uid="f0157194f1e2",
                                      version="9.9.9")

    def _rows(self, tree_commit, verdicts):
        import json
        registry = PREFLIGHT.build_registry()
        with (self.run_dir / release_gates.PREFLIGHT_EVIDENCE_FILENAME).open("a") as fh:
            for gate in registry.gates_for_phase("lock-static"):
                fh.write(json.dumps({"phase": "lock-static", "gate_id": gate.gate_id,
                                     "verdict": verdicts.get(gate.gate_id, "pass"),
                                     "tree_commit": tree_commit}) + "\n")

    def _fn(self):
        def fn():
            self.calls.append(list(sys.argv))
            return 0
        return fn

    def test_refuses_without_preflight_row(self):
        with self.assertRaisesRegex(ValueError, "no lock-static preflight"):
            self.runner._adapt_build_release(self._fn(), self._ctx())
        self.assertEqual(self.calls, [])

    def test_refuses_stale_commit_row(self):
        self._rows("0" * 40, {})
        with self.assertRaisesRegex(ValueError, self.head[:12]) as cm:
            self.runner._adapt_build_release(self._fn(), self._ctx())
        self.assertIn("000000000000", str(cm.exception))   # names BOTH commits
        self.assertEqual(self.calls, [])

    def test_refuses_on_any_refused_outcome(self):
        self._rows(self.head, {"build-covenant-floor": "refused"})
        with self.assertRaisesRegex(ValueError, "build-covenant-floor \\[refused\\]"):
            self.runner._adapt_build_release(self._fn(), self._ctx())
        self.assertEqual(self.calls, [])

    def test_proceeds_on_clean_row(self):
        self._rows(self.head, {"lock-plan-record": "skipped-inputs-absent"})   # skipped is honest at lock-static
        self.assertIsNone(self.runner._adapt_build_release(self._fn(), self._ctx()))
        self.assertEqual(len(self.calls), 1)
        self.assertIn("--target", self.calls[0])

    def test_latest_row_per_gate_wins(self):
        """A cured gate's later PASS supersedes its earlier refusal for the same tree."""
        self._rows(self.head, {"build-covenant-floor": "refused"})
        self._rows(self.head, {})
        self.assertIsNone(self.runner._adapt_build_release(self._fn(), self._ctx()))


class OneDefinitionTwoReaders(unittest.TestCase):
    def test_build_tool_wrapper_reads_the_lib_not_its_own_markers(self):
        src = (TOOLS / "tropo-build-release.py").read_text(encoding="utf-8")
        self.assertNotIn("_MISSION_BRIEF_LEAK_MARKERS = (", src)
        self.assertIn("_build_guards.mission_brief_slot_problems(build_dir)", src)
        self.assertEqual(build_guards.MISSION_BRIEF_LEAK_MARKERS[0], "argo")


class CandidatePhase(_Box):
    """AC4/AC5 by the ids the spec's verify commands name, EXECUTING the seal step.

    `Census.test_the_candidate_step_exists_and_refuses_on_skipped` asserts the
    step's source text. These call `step_10_9_candidate_gates` and read what it
    did, so a change that keeps the strings and breaks the decision goes red here.
    """

    @classmethod
    def setUpClass(cls):
        cls.build = _load("build_release_candidate_phase", "tropo-build-release.py")

    def setUp(self):
        super().setUp()
        self.dist = self.tmp / "dist"
        self.dist.mkdir()
        for d in build_guards.SHIPPED_SURFACES:
            (self.box / d).mkdir(exist_ok=True)
        (self.box / "00-tropo-nav" / "index.md").write_text("# nav\n")
        (self.box / "vault" / "updates").mkdir(parents=True, exist_ok=True)
        (self.box / "vault" / "updates" / ".gitkeep").write_text("")
        (self.box / "vault" / "00-index.jsonl").write_text(
            '{"uid": "11111111", "type": "note", "path": "vault/files/11111111.md"}\n')
        self._slot(TEMPLATE.read_text(encoding="utf-8"))

    def _seal(self, *, force=None, version_string=None):
        """Run the real step; return (SystemExit or None, pre-seal claims dict)."""
        import json
        raised = None
        try:
            self.build.step_10_9_candidate_gates(self.box, None, self.dist, force=force,
                                                 version_string=version_string)
        except SystemExit as exc:
            raised = exc
        claims_path = self.dist / self.build.PRE_SEAL_CLAIMS_FILENAME
        claims = json.loads(claims_path.read_text()) if claims_path.is_file() else None
        return raised, claims

    def test_all_candidate_gates_run_and_count_matches(self):
        """Every registered candidate gate reports, and the claims file says so."""
        registry = PREFLIGHT.build_registry()
        expected = len(registry.gates_for_phase("candidate"))
        _, claims = self._seal()
        self.assertIsNotNone(claims, "pre-seal-claims.json was not written")
        self.assertEqual(claims["gates_expected"], expected)
        self.assertEqual(len(claims["outcomes"]), expected)
        self.assertEqual({o["gate_id"] for o in claims["outcomes"]},
                         {g.gate_id for g in registry.gates_for_phase("candidate")})
        self.assertTrue(all(o["verdict"] for o in claims["outcomes"]))

    def test_changelog_gate_reads_the_version_the_build_passes(self):
        """v1.95 candidate #1 (2026-09-06): the box named `## [1.95.0]` at line 10 and
        build-changelog-names-version refused against `## []` -- Step 10.9 built its
        context with version_string hard-coded empty. The step now carries the version
        the build is cutting; the negative control is the empty string it used to send.
        """
        (self.box / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [Unreleased]\n\n## [1.2.3] - 2026-09-06\n\n- planted\n")
        _, claims = self._seal(version_string="1.2.3")
        verdicts = {o["gate_id"]: o for o in claims["outcomes"]}
        self.assertEqual(verdicts["build-changelog-names-version"]["verdict"],
                         release_gates.VERDICT_PASS, verdicts["build-changelog-names-version"])
        _, claims = self._seal()          # no version: what the runner path used to send
        verdicts = {o["gate_id"]: o for o in claims["outcomes"]}
        self.assertEqual(verdicts["build-changelog-names-version"]["verdict"],
                         release_gates.VERDICT_REFUSED)
        self.assertIn("`## []`", str(verdicts["build-changelog-names-version"].get("detail", "")))

    def test_seal_refuses_on_refused(self):
        (self.box / ".tropo").mkdir(exist_ok=True)
        (self.box / ".tropo" / "studio-identity.md").write_text("---\nstudio_id: b4e250caf19a\n---\n")
        raised, claims = self._seal()
        self.assertIsNotNone(raised, "the seal did not refuse a planted break")
        self.assertEqual(raised.code, 12)
        verdicts = {o["gate_id"]: o["verdict"] for o in claims["outcomes"]}
        self.assertEqual(verdicts["build-no-studio-identity"], release_gates.VERDICT_REFUSED)

    def test_seal_refuses_on_skipped(self):
        """A skipped gate is a refusal HERE — the box is not sealed by silence.

        Driven at the step's decision, which is the thing AC4 added: the registry
        is stubbed to report every candidate gate skipped-inputs-absent, the shape
        `run_phase` produces when an input the build owed is missing.
        """
        registry = PREFLIGHT.build_registry()
        gates = registry.gates_for_phase("candidate")

        class _AllSkipped:
            def build_registry(inner):
                return inner
            def gates_for_phase(inner, phase):
                return gates
            def get(inner, gate_id):
                return registry.get(gate_id)
            def run_phase(inner, phase, context):
                return [PREFLIGHT.GateOutcome(g.gate_id, release_gates.VERDICT_SKIPPED,
                                              "inputs absent at candidate: extracted_tree")
                        for g in gates]
            VERDICT_PASS = PREFLIGHT.VERDICT_PASS
            VERDICT_ERROR = PREFLIGHT.VERDICT_ERROR
            GateOutcome = PREFLIGHT.GateOutcome

        original = self.build._load_release_preflight
        self.build._load_release_preflight = lambda: _AllSkipped()
        self.addCleanup(setattr, self.build, "_load_release_preflight", original)
        raised, claims = self._seal()
        self.assertIsNotNone(raised, "the seal proceeded on an all-skipped candidate phase")
        self.assertEqual(raised.code, 12)
        self.assertEqual(len(claims["outcomes"]), len(gates))   # count still matches
        self.assertTrue(all(o["verdict"] == release_gates.VERDICT_SKIPPED
                            for o in claims["outcomes"]))

    def test_force_does_not_bypass(self):
        """--force is the overwrite guard's flag; it buys nothing at the seal."""
        (self.box / ".tropo").mkdir(exist_ok=True)
        (self.box / ".tropo" / "studio-identity.md").write_text("---\nstudio_id: b4e250caf19a\n---\n")
        raised, claims = self._seal(force=True)
        self.assertIsNotNone(raised, "--force sealed a box with a planted break")
        self.assertEqual(raised.code, 12)
        verdicts = {o["gate_id"]: o["verdict"] for o in claims["outcomes"]}
        self.assertEqual(verdicts["build-no-studio-identity"], release_gates.VERDICT_REFUSED)


class ComposedPath(unittest.TestCase):
    """AC5 fixture half: refuse -> preflight -> cure -> build -> catch -> cure.

    One throwaway tree, one run folder, the whole chain in order, every count
    computed from the registry and never hard-coded. Inherits Preflight's tree
    fixture so the three planted tree violations are the same three AC2 reports.

    The fixture tree is a REAL git repository, stood up through
    tests/git_env.py's contained seam, because the runner resolves the tree it
    is about to build with `git rev-parse` and a scratch tree with no repo
    cannot answer. Contained: GIT_* is scrubbed, so an inherited GIT_DIR cannot
    point this `git init` at anything but the fixture.
    """

    @classmethod
    def setUpClass(cls):
        cls.runner = _load("release_run_composed_path", "tropo-release-run.py")
        cls.runner.RUNTIME_DRIVER = lambda *a, **k: None
        cls.build = _load("build_release_composed_path", "tropo-build-release.py")

    # Preflight's fixture, borrowed as behaviour rather than inherited as a base
    # class: subclassing re-collects its four tests under this class's name, and
    # the studio's own idiom (test_lock_writes_entry_uid_v191) is to borrow the
    # fixture as an object so a suite reports each test exactly once.
    _tree = Preflight._tree
    _context = Preflight._context
    _plant_three = Preflight._plant_three
    _cure_three = Preflight._cure_three
    _fixture_box = Preflight._fixture_box
    _CLEAN_PROBE = Preflight._CLEAN_PROBE

    def _journal(self, run_dir, event):
        with (run_dir / "run.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": event, "ts": _now()}) + "\n")

    def _rows_in(self, run_dir, phase):
        path = run_dir / release_gates.PREFLIGHT_EVIDENCE_FILENAME
        return [json.loads(l) for l in path.read_text().splitlines()
                if l.strip() and json.loads(l).get("phase") == phase]

    def test_refuse_preflight_cure_build_catch_cure_seal_on_fixture(self):
        registry = PREFLIGHT.build_registry()
        lock_static_count = len(registry.gates_for_phase("lock-static"))
        tmp, tools, releases = self._tree()
        git_env.init_repo(tmp)                      # the runner needs a real tree to name
        git_env.git_run("add", "-A", cwd=tmp)
        git_env.git_run("commit", "-q", "-m", "fixture tree", cwd=tmp)
        head = self.runner._tree_head(tmp)
        self.assertTrue(head, "the fixture tree has no HEAD for the runner to name")
        run_dir = tmp / "run"
        run_dir.mkdir()
        ctx = self._context(tmp, releases)
        ctx["tree_commit"] = head

        # --- 1. THE RUNNER REFUSES THE BUILD (AC3): no lock-static evidence yet
        rc = self.runner.RunContext(vault_root=tmp, release_plan_uid="f015ba71c711",
                                    run_dir=run_dir, activation_uid="f0157194f1e2",
                                    version="9.9.9")
        calls = []
        with self.assertRaisesRegex(ValueError, "no lock-static preflight"):
            self.runner._adapt_build_release(lambda: calls.append(1), rc)
        self.assertEqual(calls, [], "the build ran despite the refusal")
        self._journal(run_dir, "refused_build")

        # --- 2. THE PREFLIGHT REPORTS ALL THREE AT ONCE (AC2)
        self._plant_three(tools, releases)
        first = registry.run_phase("lock-static", ctx)
        refused = sorted(o.gate_id for o in first if o.verdict == release_gates.VERDICT_REFUSED)
        self.assertEqual(refused, ["build-no-absolute-paths", "build-overwrite-guard",
                                   "ship-python-floor"])
        release_gates.write_evidence(run_dir, "lock-static", first, registry,
                                     tree_commit=head)

        # --- 3. THE DRIVER CURES THEM; A SECOND PREFLIGHT IS CLEAN
        self._cure_three(tools, releases)
        second = registry.run_phase("lock-static", ctx)
        still = [o.gate_id for o in second if o.verdict == release_gates.VERDICT_REFUSED]
        self.assertEqual(still, [], "cure did not clear the plants")
        release_gates.write_evidence(run_dir, "lock-static", second, registry,
                                     tree_commit=head)

        # --- 4. THE RUNNER NOW BUILDS
        self.assertIsNone(self.runner._adapt_build_release(lambda: calls.append(1), rc))
        self.assertEqual(len(calls), 1, "the runner did not build on clean evidence")
        self._journal(run_dir, "candidate_built")

        # --- 5. THE CANDIDATE PHASE CATCHES THE BOX PLANT AND REFUSES (AC4)
        box = self._fixture_box(tmp)
        (box / ".tropo").mkdir(exist_ok=True)
        (box / ".tropo" / "studio-identity.md").write_text(
            "---\nstudio_id: b4e250caf19a\n---\n", encoding="utf-8")
        planted = registry.run_phase("candidate", {"source_tree": str(TOOLS.parents[1]),
                                                   "extracted_tree": str(box),
                                                   "tree_commit": head,
                                                   "version_string": "9.9.9"})
        by_id = {o.gate_id: o for o in planted}
        self.assertEqual(by_id["build-no-studio-identity"].verdict,
                         release_gates.VERDICT_REFUSED)
        release_gates.write_evidence(run_dir, "candidate", planted, registry, tree_commit=head)

        # --- 6. CURED: the gate that caught it now passes
        (box / ".tropo" / "studio-identity.md").unlink()
        cured = {o.gate_id: o for o in
                 registry.run_phase("candidate", {"source_tree": str(TOOLS.parents[1]),
                                                  "extracted_tree": str(box),
                                                  "tree_commit": head,
                                                  "version_string": "9.9.9"})}
        self.assertEqual(cured["build-no-studio-identity"].verdict, release_gates.VERDICT_PASS)
        self._journal(run_dir, "seal")

        # --- SHAPES, computed from the registry, never hard-coded
        self.assertEqual(len(self._rows_in(run_dir, "lock-static")), 2 * lock_static_count)
        self.assertEqual(len(self._rows_in(run_dir, "candidate")),
                         len(registry.gates_for_phase("candidate")))
        events = [json.loads(l)["event"] for l in
                  (run_dir / "run.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual(events, ["refused_build", "candidate_built", "seal"])

    def test_live_sequencing_reads_the_run_and_refuses_an_unsequenced_one(self):
        """AC5's live arm, both ways, against a fixture run folder."""
        registry = PREFLIGHT.build_registry()
        tmp, tools, releases = self._tree()
        run_dir = tmp / "run"
        run_dir.mkdir()
        head = "a" * 40
        (run_dir / "pre-seal-claims.json").write_text(
            json.dumps({"phase": "candidate", "tree_commit": head}), encoding="utf-8")

        # no candidate_built yet -> refuses, and says why
        code, lines = live_sequencing(run_dir)
        self.assertEqual(code, 1)
        self.assertTrue(any("no tropo.release.candidate_built" in l for l in lines))

        ctx = self._context(tmp, releases)
        ctx["tree_commit"] = head
        self._cure_three(tools, releases)
        outcomes = registry.run_phase("lock-static", ctx)
        release_gates.write_evidence(run_dir, "lock-static", outcomes, registry, tree_commit=head)

        # candidate_built BEFORE the evidence -> the sequencing is wrong, and it prints both
        (run_dir / "run.jsonl").write_text(json.dumps(
            {"event": "tropo.release.candidate_built", "ts": "2000-01-01T00:00:00Z"}) + "\n")
        code, lines = live_sequencing(run_dir)
        self.assertEqual(code, 1)
        self.assertTrue(any("does NOT precede" in l for l in lines))
        self.assertTrue(any("2000-01-01T00:00:00Z" in l for l in lines))

        # candidate_built after -> passes
        (run_dir / "run.jsonl").write_text(json.dumps(
            {"event": "tropo.release.candidate_built", "ts": "2099-01-01T00:00:00Z"}) + "\n")
        code, lines = live_sequencing(run_dir)
        self.assertEqual(code, 0, lines)
        self.assertTrue(any(l.startswith("PASS") for l in lines))


# --------------------------------------------------------------------------
# AC5 LIVE HALF — the Fork-4 sequencing ruling as a journal fact.
#
# RULED by argus-a171 2026-09-05 (evt_b51c083be28ac6fe_00000473) after I
# measured that the AC could not be written as drafted: `candidate_built` names
# NO tree commit (its payload is identity.binding() + package_path /
# candidate_sha256 / version, and candidate_sha256 is the ZIP digest), and
# evidence rows carried NO timestamp, so "timestamped before candidate_built"
# and "print the two timestamps" had one timestamp between them.
#
# The ruling: `ts` on the evidence rows is mine and additive; the candidate's
# commit is resolved from <run_dir>/pre-seal-claims.json (tree_commit, written
# by Step 10.9 immediately before the seal) paired with the LAST candidate_built
# row. candidate_built's payload is NOT touched — identity.binding() fields are
# repeated verbatim downstream and widening them is a governance change outside
# this spec.
# --------------------------------------------------------------------------

CANDIDATE_BUILT = "tropo.release.candidate_built"


def _journal_rows(run_dir: Path):
    path = run_dir / "run.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def live_sequencing(run_dir: Path):
    """Did a clean lock-static set for the candidate's own tree precede the build?

    Returns (exit_code, lines). Exit 0 only when every condition holds; every
    other path prints why and returns 1. A missing input is never a pass — the
    whole point of this arm is that a release cannot claim a sequencing it
    cannot show.
    """
    out = []
    claims_path = run_dir / "pre-seal-claims.json"
    if not claims_path.is_file():
        return 1, ["REFUSED: %s is absent — the candidate phase never wrote its "
                   "claims, so the commit the box was built from is unknown." % claims_path]
    claims = json.loads(claims_path.read_text(encoding="utf-8"))
    commit = str(claims.get("tree_commit") or "")
    if not commit:
        return 1, ["REFUSED: %s carries no tree_commit." % claims_path]

    built = [r for r in _journal_rows(run_dir)
             if (r.get("event") or r.get("type")) == CANDIDATE_BUILT]
    if not built:
        return 1, ["REFUSED: no %s row in %s/run.jsonl — nothing was built to sequence."
                   % (CANDIDATE_BUILT, run_dir)]
    last = built[-1]                      # the attempt that became the candidate
    built_ts = str(last.get("ts") or "")
    out.append("candidate_built (last of %d): ts=%s" % (len(built), built_ts or "<none>"))
    out.append("candidate tree_commit (pre-seal-claims.json): %s" % commit)

    pf = run_dir / release_gates.PREFLIGHT_EVIDENCE_FILENAME
    if not pf.is_file():
        return 1, out + ["REFUSED: %s is absent — no lock-static evidence at all." % pf]
    latest = {}
    for line in pf.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("phase") != "lock-static":
            continue
        if str(row.get("tree_commit") or "") != commit:
            continue
        latest[row.get("gate_id")] = row     # last row per gate wins, as the runner does
    if not latest:
        return 1, out + ["REFUSED: no lock-static rows name %s — the tree that was "
                         "built was never judged." % commit[:12]]

    refused = sorted(g for g, r in latest.items()
                     if r.get("verdict") not in (release_gates.VERDICT_PASS,
                                                 release_gates.VERDICT_SKIPPED))
    out.append("lock-static gates naming that commit: %d (refused: %d)" % (len(latest), len(refused)))
    if refused:
        return 1, out + ["REFUSED: lock-static was not clean for the built tree: %s"
                         % ", ".join(refused)]

    stamps = sorted(str(r.get("ts") or "") for r in latest.values())
    if not stamps[-1]:
        return 1, out + ["REFUSED: lock-static rows for %s carry no ts — they predate the "
                         "ts field, so the sequencing cannot be shown. Re-run the preflight."
                         % commit[:12]]
    newest = stamps[-1]
    out.append("newest clean lock-static row: ts=%s" % newest)
    if not built_ts:
        return 1, out + ["REFUSED: candidate_built carries no ts."]
    if newest >= built_ts:
        return 1, out + ["REFUSED: the lock-static set does NOT precede the build.",
                         "  lock-static newest : %s" % newest,
                         "  candidate_built    : %s" % built_ts]
    out.append("PASS: a clean lock-static set for %s precedes candidate_built." % commit[:12])
    return 0, out


def _live_sequencing_main(argv):
    run_dir = None
    for i, arg in enumerate(argv):
        if arg == "--run-dir" and i + 1 < len(argv):
            run_dir = Path(argv[i + 1])
        elif arg.startswith("--run-dir="):
            run_dir = Path(arg.split("=", 1)[1])
    if run_dir is None:
        print("usage: test_release_guard_registry.py --live-sequencing --run-dir <release run folder>")
        return 2
    code, lines = live_sequencing(run_dir)
    for line in lines:
        print(("  " if not line.startswith(("PASS", "REFUSED")) else "") + line)
    return code


if __name__ == "__main__":
    if "--live-sequencing" in sys.argv:
        sys.exit(_live_sequencing_main(sys.argv[1:]))
    unittest.main()
