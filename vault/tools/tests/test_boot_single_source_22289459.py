#!/usr/bin/env python3
"""S4 single-source doctrine: the executable contract for dev-spec 22289459.

Argus A147 authored the locked spec and the doctrine surfaces; Talos T40 builds
the guard and this test (spec §Handoff).

WHAT THE SPEC ASKS THIS FILE TO GUARD, and why each one is here rather than
trusted:

  - EXACTLY TWO SURFACES carry the boot procedure, and the guard names those
    exact paths rather than counting files. A count is satisfied by any two.
  - THE PLANT: one Group heading added to a kernel stub must ERROR by name, and
    removing it must go green. The spec's words: "the drift class that required
    the A97 hand-fix becomes impossible to hold silently."
  - NO FULL VALIDATOR OR SUITE AT BOOT. A147 measured the two commands that had
    accreted onto the established path: `--fleet-boot-health` at 53.7 seconds
    and `npm run test:lifecycle` at 5.7 seconds / 75 tests. Neither belongs in
    an activation.
  - FLEET HEALTH IS LINEAGE-NATIVE. Births stopped going through activation
    entries at the 2026-08-06 cutover, so a check that reads them is aimed at a
    retired authority.
  - THE REMOVED FLAG STAYS REMOVED.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location(
    "tropo_validate_s4", TOOLS / "tropo-validate.py"
)
assert _spec and _spec.loader
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)


def _stub(text: str) -> str:
    return "---\nuid: 'aa11bb22'\ntype: os-config-pointer\n---\n\n" + text


class ExactlyTwoProcedureSurfaces(unittest.TestCase):
    def test_the_live_studio_carries_the_procedure_at_exactly_those_two_paths(self) -> None:
        findings, checked, _ = validate.check_kernel_pointer_stub(ROOT)
        self.assertGreater(checked, 50, "the boot-surface scan found almost nothing")
        two_source = [f for f in findings if "sanctions" in f or "SANCTIONED" in f]
        self.assertEqual(two_source, [], "the procedure is not where S4 says it is")

    def test_the_sanctioned_paths_are_named_not_counted(self) -> None:
        """A count is satisfied by any two files; this claim is about WHICH two."""
        self.assertEqual(
            set(validate.SANCTIONED_PROCEDURE_SURFACES),
            {"vault/playbooks/99341618.md", ".tropo/boot-fast-path.md"},
        )

    def test_a_third_copy_on_the_boot_path_errors(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".tropo").mkdir(parents=True)
            (root / "vault" / "playbooks").mkdir(parents=True)
            procedure = "\n".join(f"## {name}" for name in validate.BOOT_MILESTONE_NAMES)
            (root / "vault" / "playbooks" / "99341618.md").write_text(procedure)
            (root / ".tropo" / "boot-fast-path.md").write_text(procedure)
            (root / ".tropo" / "a-third-copy.md").write_text(procedure)
            findings, _, _ = validate.check_kernel_pointer_stub(root)
            self.assertTrue(
                any("a-third-copy.md" in f and "sanctions" in f for f in findings),
                findings,
            )

    def test_a_MISSING_sanctioned_surface_is_reported_as_loudly(self) -> None:
        """Fewer copies is not the goal.

        A guard that only counts down treats a vanished canonical as progress —
        the same shape as a check that stops running and reports zero findings.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".tropo").mkdir(parents=True)
            (root / "vault" / "playbooks").mkdir(parents=True)
            procedure = "\n".join(f"## {name}" for name in validate.BOOT_MILESTONE_NAMES)
            (root / "vault" / "playbooks" / "99341618.md").write_text(procedure)
            # boot-fast-path.md deliberately absent
            findings, _, _ = validate.check_kernel_pointer_stub(root)
            self.assertTrue(
                any(".tropo/boot-fast-path.md" in f and "SANCTIONED" in f for f in findings),
                findings,
            )

    def test_a_document_that_merely_mentions_milestones_is_not_a_copy(self) -> None:
        """Scope control, and the reason this guard is not noise.

        The architecture spec 78c2126d describes all six milestones, reflections
        quote them, and the rendered nav projects them. None is a surface anyone
        boots from. A guard that erred on those would be routed around within a
        week — which is precisely how the permanently-red debt ratchet got
        ignored for months.
        """
        self.assertNotIn("vault/files", validate.BOOT_SURFACE_ROOTS)
        self.assertNotIn("00-tropo-nav", validate.BOOT_SURFACE_ROOTS)
        spec_78 = ROOT / "vault" / "files" / "78c2126d.md"
        if spec_78.is_file():
            carried = sum(
                1 for name in validate.BOOT_MILESTONE_NAMES
                if name in spec_78.read_text(errors="ignore")
            )
            self.assertGreaterEqual(
                carried, 4, "fixture assumption changed: the spec no longer mentions them"
            )
            findings, _, _ = validate.check_kernel_pointer_stub(ROOT)
            self.assertFalse(
                any("78c2126d" in f for f in findings),
                "the architecture spec is being read as a procedure copy",
            )


class ThePlant(unittest.TestCase):
    """The spec's named acceptance: one heading in, ERROR by name; out, green."""

    def _fixture(self, root: Path, stub_body: str) -> None:
        (root / ".tropo").mkdir(parents=True, exist_ok=True)
        (root / "vault" / "playbooks").mkdir(parents=True, exist_ok=True)
        procedure = "\n".join(f"## {n}" for n in validate.BOOT_MILESTONE_NAMES)
        (root / "vault" / "playbooks" / "99341618.md").write_text(procedure)
        (root / ".tropo" / "boot-fast-path.md").write_text(procedure)
        (root / ".tropo" / "boot-config.md").write_text(_stub(stub_body))

    def test_one_group_heading_in_a_stub_errors_naming_the_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            # Green first. Without this the red below could be red for any reason.
            self._fixture(root, "Read the canonical at vault/playbooks/99341618.md.\n")
            clean, _, _ = validate.check_kernel_pointer_stub(root)
            self.assertEqual(clean, [], f"the control fixture is not clean: {clean}")

            # Plant exactly one heading — the spec's gesture, verbatim.
            self._fixture(
                root,
                "Read the canonical.\n\n## Group 0 — Boot Configuration\n\nDo the thing.\n",
            )
            planted, _, _ = validate.check_kernel_pointer_stub(root)
            self.assertTrue(planted, "the plant did not fire")
            self.assertTrue(
                any(".tropo/boot-config.md" in f and "Group heading" in f for f in planted),
                planted,
            )

            # Remove it — green again. Proves the plant is what fired.
            self._fixture(root, "Read the canonical at vault/playbooks/99341618.md.\n")
            self.assertEqual(validate.check_kernel_pointer_stub(root)[0], [])

    def test_a_stub_over_the_ceiling_errors(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root, "x" * (validate.KERNEL_STUB_CEILING_BYTES + 1))
            findings, _, _ = validate.check_kernel_pointer_stub(root)
            self.assertTrue(
                any("stub ceiling" in f and "boot-config.md" in f for f in findings),
                findings,
            )

    def test_the_ceiling_is_read_from_the_constant_not_restated(self) -> None:
        """Item 4's rule: one definition, two readers."""
        self.assertEqual(validate.KERNEL_STUB_CEILING_BYTES, 4096)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root, "y" * (validate.KERNEL_STUB_CEILING_BYTES - 200))
            self.assertEqual(validate.check_kernel_pointer_stub(root)[0], [])


class NoExpensiveCommandAtBoot(unittest.TestCase):
    """A147 measured 53.7s + 5.7s of command work accreted onto activation."""

    BOOT_SURFACES = (
        ".tropo/boot-config.md",
        ".tropo/boot-fast-path.md",
        ".tropo/playbooks/agent-activation.playbook.md",
        ".tropo-studio/agent-boot.extension.md",
        "vault/playbooks/99341618.md",
    )

    #: Words that turn a mention into a PROHIBITION. Needed because the canonical
    #: playbook's Step 5.1.9 is titled "Retired from boot" and says "Do not run
    #: the legacy `--fleet-boot-health` full-vault probe during activation" — a
    #: sentence that must keep existing. The first version of this test matched
    #: the bare string and failed on that line, i.e. it could not tell "do X"
    #: from "do not do X" and would have had Argus delete the very prose that
    #: records the retirement.
    NEGATIONS = (
        "do not", "don't", "never", "retired", "no longer", "removed",
        "not run", "stop running", "instead of",
    )

    #: How far back to look for the negation. One sentence, not the whole file:
    #: a document-wide search would let a prohibition anywhere excuse an
    #: instruction everywhere.
    CONTEXT_CHARS = 220

    def _boot_text(self):
        for rel in self.BOOT_SURFACES:
            path = ROOT / rel
            if path.is_file():
                yield rel, path.read_text(errors="ignore")

    def _unnegated_mentions(self, needle: str) -> list[str]:
        offenders = []
        for rel, text in self._boot_text():
            start = 0
            while True:
                at = text.find(needle, start)
                if at == -1:
                    break
                start = at + len(needle)
                context = text[max(0, at - self.CONTEXT_CHARS): at + len(needle)].lower()
                if not any(word in context for word in self.NEGATIONS):
                    offenders.append(f"{rel}: {text[max(0, at-90):at+60].strip()!r}")
        return offenders

    def test_no_activation_surface_invokes_the_retired_fleet_flag(self) -> None:
        self.assertEqual(
            self._unnegated_mentions("--fleet-boot-health"),
            [],
            "a boot surface still tells every agent to run a flag that no longer "
            "exists — they would hit an argparse error at Group 5",
        )

    def test_no_activation_surface_invokes_the_lifecycle_suite(self) -> None:
        offenders = self._unnegated_mentions("npm run test:lifecycle")
        offenders += self._unnegated_mentions("tropo-run-suites.py --filter activation")
        self.assertEqual(
            offenders,
            [],
            "running the regression suite at every boot is not activation; it also "
            "dirtied the kernel derivations' gauntlet dates while doing it",
        )

    def test_control_a_real_instruction_would_still_be_caught(self) -> None:
        """The teeth for the negation logic.

        Without this, "look for the flag unless something nearby sounds like a
        denial" is a rule that can be satisfied by any nearby denial — and a
        guard that cannot fail is the shape this whole spec exists to end.
        """
        instruction = (
            "#### Step 5.1.9\n\nRun `python3 vault/tools/tropo-validate.py "
            "--fleet-boot-health` and fold the result into your signal.\n"
        )
        prohibition = (
            "#### Step 5.1.9 — Retired from boot\n\nDo not run the legacy "
            "`--fleet-boot-health` full-vault probe during activation.\n"
        )
        original = self.BOOT_SURFACES
        with TemporaryDirectory() as tmp:
            for body, should_flag in ((instruction, True), (prohibition, False)):
                path = Path(tmp) / "surface.md"
                path.write_text(body, encoding="utf-8")
                case = self

                class _Probe(NoExpensiveCommandAtBoot):
                    def _boot_text(self_inner):
                        yield "surface.md", body

                probe = _Probe("test_control_a_real_instruction_would_still_be_caught")
                found = probe._unnegated_mentions("--fleet-boot-health")
                case.assertEqual(
                    bool(found),
                    should_flag,
                    f"negation logic wrong for: {body[:60]!r}",
                )
        self.assertEqual(self.BOOT_SURFACES, original)

    def test_the_explicit_lifecycle_run_still_exists_outside_boot(self) -> None:
        """Removed from activation, NOT removed from the studio.

        The spec is explicit that the explicit test command remains valuable.
        Deleting it would be a different and worse change.
        """
        package = ROOT / "package.json"
        if not package.is_file():
            self.skipTest("no package.json")
        scripts = json.loads(package.read_text()).get("scripts", {})
        self.assertIn("test:lifecycle", scripts)


class TheRemovedFlagStaysRemoved(unittest.TestCase):
    def test_the_cli_no_longer_accepts_it(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TOOLS / "tropo-validate.py"), "--fleet-boot-health"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments: --fleet-boot-health",
                      result.stdout + result.stderr)

    def test_no_standalone_mode_survives_in_the_source(self) -> None:
        source = (TOOLS / "tropo-validate.py").read_text(encoding="utf-8")
        self.assertNotIn("args.fleet_boot_health", source)
        self.assertNotIn("--fleet-boot-health'", source)


class FleetHealthIsLineageNative(unittest.TestCase):
    def test_it_reads_lineage_files_not_activation_entries(self) -> None:
        """The check was interrogating a retired authority.

        Births stopped going through `type: activation` entries at the
        2026-08-06 cutover. A check that reads them is aimed one gate off from
        the mechanism it claims to measure — and cost 53.7 seconds to be.
        """
        source = (TOOLS / "tropo-validate.py").read_text(encoding="utf-8")
        body = source[source.index("def check_every_agent_can_still_boot"):]
        body = body[: body.index("\ndef ", 1)]
        self.assertIn("lineage.jsonl", body)
        self.assertIn("tropo-lineage.py", body)
        self.assertNotIn("load_canonical_activation_entries", body)
        self.assertNotIn("git log", body)

    def test_it_asks_the_lineage_tool_rather_than_modelling_it(self) -> None:
        """One derivation, so the check and the birth cannot disagree."""
        source = (TOOLS / "tropo-validate.py").read_text(encoding="utf-8")
        body = source[source.index("def check_every_agent_can_still_boot"):]
        body = body[: body.index("\ndef ", 1)]
        self.assertIn("next_generation", body)
        self.assertIn("read_lines", body)

    def test_an_unreadable_lineage_is_the_one_blocking_condition(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vault" / "tools").mkdir(parents=True)
            (root / "vault" / "tools" / "tropo-lineage.py").write_bytes(
                (TOOLS / "tropo-lineage.py").read_bytes()
            )
            broken = root / "agents" / "ghost"
            broken.mkdir(parents=True)
            (broken / "lineage.jsonl").write_text("{not json at all\n")
            findings, checked, blocked = validate.check_every_agent_can_still_boot(root)
            self.assertEqual(checked, 1)
            self.assertEqual(blocked, 1, findings)
            self.assertTrue(any("ghost" in f for f in findings), findings)

    def test_an_open_generation_is_a_note_and_never_a_block(self) -> None:
        """Mike's standing rule: a finding never refuses existence."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vault" / "tools").mkdir(parents=True)
            (root / "vault" / "tools" / "tropo-lineage.py").write_bytes(
                (TOOLS / "tropo-lineage.py").read_bytes()
            )
            agent = root / "agents" / "liveone"
            agent.mkdir(parents=True)
            (agent / "lineage.jsonl").write_text(
                json.dumps({"t": "born", "gen": "T7", "at": "2026-08-09"}) + "\n"
            )
            findings, checked, blocked = validate.check_every_agent_can_still_boot(root)
            self.assertEqual((checked, blocked), (1, 0), findings)
            self.assertTrue(any("T7 is still open" in f for f in findings), findings)
            self.assertTrue(any("NOT a block" in f for f in findings), findings)

    def test_a_healthy_retired_lineage_reports_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vault" / "tools").mkdir(parents=True)
            (root / "vault" / "tools" / "tropo-lineage.py").write_bytes(
                (TOOLS / "tropo-lineage.py").read_bytes()
            )
            agent = root / "agents" / "clean"
            agent.mkdir(parents=True)
            (agent / "lineage.jsonl").write_text(
                json.dumps({"t": "born", "gen": "T1", "at": "2026-08-01"}) + "\n"
                + json.dumps({"t": "retired", "gen": "T1", "at": "2026-08-02"}) + "\n"
            )
            findings, checked, blocked = validate.check_every_agent_can_still_boot(root)
            self.assertEqual((checked, blocked, findings), (1, 0, []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
