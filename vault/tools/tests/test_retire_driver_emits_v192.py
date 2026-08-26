"""AC2 (b1e78abb, v1.92): the driver VERIFIES step 8 rather than emitting
it, and performs step 7's crew-brief re-render itself.

`tropo-lineage.py retire`'s own `announce()` already emits the
`category: retirement` broadcast (29506520 AC4(b), shipped and pinned by
test_retirement_notice_category_v191.py) -- a driver that ALSO emits makes
two broadcasts per retirement and rebuilds the one-writer defect class this
whole spec family exists to cure. This file proves the driver is a reader on
that axis, and a real actor (not just a returning subprocess) on the
crew-brief axis.

Extends the temp-studio harness per the spec's own §Handoff warning (its
TOOL_SCRIPTS list covers neither tropo-lineage.py's own event side-effects
against a fixture bus, nor the crew-brief renderer's file-discovery
requirements) -- builds the minimal real fixture the renderer needs
(an agent-root project, an activation thin-pointer, a unified entry) rather
than assuming the harness already covers it.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_retire_driver_emits_v192
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("retire_driver_ac2", TOOLS / "tropo-retire-driver.py")
driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(driver)

LINEAGE_TOOL = TOOLS / "tropo-lineage.py"
RENDERER_SOURCE = TOOLS / "6510afc7.py"

REPO_ROOT = Path(__file__).resolve().parents[3]

AGENT = "emitfix"
UID = "fa000001"


class DriverIsAReaderNotAWriterOfStep8(unittest.TestCase):

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="retire-driver-emits-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self._build_fixture()

    def _write(self, relative: str, content: str) -> Path:
        p = self.root / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def _build_fixture(self) -> None:
        # A real, resolvable crew-brief target: renderer requirements per
        # discover_crew() — a project entry, an activation thin-pointer, a
        # unified entry to render as the status card.
        self._write(
            f"vault/files/{UID}.md",
            f"---\nuid: {UID}\ntype: project\ntitle: {AGENT} Agent-Root-Project\n"
            f"agent_slug: {AGENT}\nagent_class: executive\n---\n\n# root\n",
        )
        self._write(
            f"agents/{AGENT}/{AGENT}-activation.md",
            f"---\nagent_uid: {UID}\n---\n\n# activation\n",
        )
        self._write(
            f"vault/agents/{UID}.md",
            f"---\nuid: {UID}\ntype: agent\nagent: {AGENT}\nparty_uid: aaaaaaaa\n"
            f"role: Fixture Role\nstatus: active\ngeneration: F1\n"
            f"last_session: '2026-08-24'\n---\n\n"
            f"# {AGENT}\n\n## §Status-Notes\n\nNothing yet.\n",
        )
        self._write(
            "00-crew-brief.md",
            "---\nowner: fixture\n---\n\n# Crew Brief\n\n"
            "<!-- crew-table:start -->\n(not yet rendered)\n<!-- crew-table:end -->\n",
        )
        # The renderer AND the emit tool, copied to the fixture's own
        # vault/tools/ — both resolve VAULT_ROOT from Path(__file__), so a
        # copy at the fixture path re-roots correctly (same technique as
        # temp_studio.py). announce() silently no-ops if tropo-emit-event.py
        # isn't found at <root>/vault/tools/ (found live: the first version
        # of this fixture had only the renderer, and the close's own
        # broadcast never landed at all -- 0, not 1).
        (self.root / "vault" / "tools").mkdir(parents=True, exist_ok=True)
        shutil.copy2(RENDERER_SOURCE, self.root / "vault" / "tools" / "6510afc7.py")
        shutil.copy2(TOOLS / "tropo-emit-event.py", self.root / "vault" / "tools" / "tropo-emit-event.py")
        shutil.copytree(TOOLS / "lib", self.root / "vault" / "tools" / "lib", dirs_exist_ok=True)
        # The retirement playbook and a synthetic step registry, so the
        # driver's own refusal gate has something valid to parse (only
        # needed if a test also runs the full driver; kept for parity).
        (self.root / "vault" / "playbooks").mkdir(parents=True, exist_ok=True)

    def _run_lineage(self, *args):
        p = subprocess.run(
            [sys.executable, str(LINEAGE_TOOL), "--root", str(self.root), *args],
            capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout, p.stderr

    def _broadcast_count(self) -> int:
        sys.path.insert(0, str(TOOLS))
        from lib import event_identity
        events = event_identity.load_event_union(self.root)
        return sum(
            1 for ev in events
            if ev.get("type") == "tropo.broadcast.crew"
            and (ev.get("data") or {}).get("category") == "retirement"
            and (ev.get("data") or {}).get("agent") == AGENT
        )

    def test_exactly_one_broadcast_exists_after_driver_plus_close(self) -> None:
        # Born, then closed for real — announce() fires here, the ONLY writer.
        c, out, err = self._run_lineage("born", "--agent", AGENT, "--by", "test")
        self.assertEqual(c, 0, err)
        gen = json.loads(out)["generation"]

        c, out, err = self._run_lineage("retire", "--agent", AGENT)
        self.assertEqual(c, 0, err)
        self.assertEqual(self._broadcast_count(), 1, "close's own announce() must be the sole writer")

        # The driver reads the same bus back — it must NOT add a second one.
        ok, evidence = driver.observe_retirement_notice(self.root, AGENT, gen)
        self.assertTrue(ok, evidence)
        self.assertEqual(
            self._broadcast_count(), 1,
            "the driver's own read of step 8 must not itself write anything",
        )

    def test_a_bus_without_category_retirement_reports_step_8_open(self) -> None:
        """Known-negative: a notice exists but lacks the required category —
        step 8 must still report open, not pass on any broadcast's presence."""
        self._write(
            "vault/events/streams/wrong-category.jsonl",
            json.dumps({
                "specversion": "1.0", "type": "tropo.broadcast.crew",
                "source": f"/agents/{AGENT}", "time": "2026-08-24T00:00:00Z",
                "source_uid": "aaaaaaaa", "lifecycle": "evergreen",
                "data": {"category": "crew-state", "agent": AGENT, "gen": "F1", "t": "retired"},
                "id": "evt_wrongcategory_00000001", "event_uid": "evt_wrongcategory_00000001",
                "writer_instance_uid": "wrongcategory", "stream_uid": "wrongcategory", "local_seq": 1,
            }) + "\n",
        )
        ok, evidence = driver.observe_retirement_notice(self.root, AGENT, "F1")
        self.assertFalse(ok, evidence)

    def test_crew_brief_rerender_is_observed_by_rendered_output(self) -> None:
        """Crew-brief re-render is a real act with a real, checkable
        artifact — not just a subprocess returning 0."""
        before = (self.root / "00-crew-brief.md").read_text(encoding="utf-8")
        self.assertNotIn(AGENT, before)

        ok, evidence = driver.perform_crew_brief_rerender(self.root)
        self.assertTrue(ok, evidence)

        after = (self.root / "00-crew-brief.md").read_text(encoding="utf-8")
        self.assertIn(AGENT.title(), after, "the fixture agent must appear in the re-rendered crew table")
        self.assertNotEqual(before, after)

    def test_mutation_a_missing_renderer_is_reported_not_silently_ok(self) -> None:
        """Teeth: if the renderer tool itself is absent, the act must fail
        loudly, not report success on a call that never ran."""
        (self.root / "vault" / "tools" / "6510afc7.py").unlink()
        ok, evidence = driver.perform_crew_brief_rerender(self.root)
        self.assertFalse(ok, evidence)



class TheDriverItselfEmitsNothing(DriverIsAReaderNotAWriterOfStep8):
    """AC2's evidence says "after a driver run plus a close". THERE WAS NO
    DRIVER RUN.

    The suite did `born` -> `retire` -> count == 1 -> called exactly one
    function, `observe_retirement_notice`, and re-counted. `run_driver` was
    never invoked, and the fixture could not have supported it: it created
    `vault/playbooks/` and wrote no playbook, with a comment saying the registry
    was "kept for parity".

    An independent adversarial pass proved the consequence: it injected a second
    `tropo.broadcast.crew` / `category: retirement` emit into `run_driver` —
    precisely the defect AC2 was rewritten on measurement to prevent, "a driver
    that also emits makes TWO broadcasts per retirement and rebuilds the
    one-writer defect class inside the spec written to cure it" — and ALL FIVE
    SUITES, 48 TESTS, STAYED GREEN. The count assertion was live only within one
    function's blast radius.

    This drives the whole walk against a real playbook and a bus that already
    carries the close's notice, and requires the count to still be exactly one.
    """

    def test_a_full_driver_walk_adds_no_broadcast(self) -> None:
        # The playbook the driver refuses without. Copied from the REAL one so
        # the step registry is bound to production shape rather than to a
        # fixture authored in the reader's shape.
        real = REPO_ROOT / driver.PLAYBOOK_RELATIVE_PATH
        target = self.root / driver.PLAYBOOK_RELATIVE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(real.read_text(encoding="utf-8"), encoding="utf-8")

        # A bus that already carries the close's notice — the state a driver
        # actually runs against.
        self._run_lineage("born", "--agent", AGENT, "--by", "t", "--model", "m")
        self._run_lineage("retire", "--agent", AGENT)

        before = self._broadcast_count()
        driver.run_driver(self.root, AGENT, "F1", perform_acts=False)
        after = self._broadcast_count()

        self.assertEqual(
            before, after,
            "run_driver added a crew broadcast. The driver OBSERVES step 8; the "
            "close is the only writer. Two broadcasts per retirement is the "
            "one-writer defect this spec exists to cure.",
        )


class TheStepRegistryIsBoundToTheRealPlaybook(unittest.TestCase):
    """Nothing compared REQUIRED_STEP_LABELS to the actual playbook.

    The adversarial pass renamed one bold label in the REAL
    `vault/playbooks/e2c7d185.md`: every production invocation refused with
    exit 3 — the tool 100% dead — and all 15 AC1 tests stayed green. The
    Implementation Contract's justification ("a playbook amendment then breaks
    the driver loudly instead of silently orphaning an observer") held only in
    production and never on the board.
    """

    def test_the_real_playbook_parses_to_the_registry(self) -> None:
        parsed = driver.parse_required_steps(REPO_ROOT)
        self.assertEqual(
            parsed, list(driver.REQUIRED_STEP_LABELS),
            "e2c7d185 §Required Practice no longer matches the driver's step "
            "registry; the driver is dead in production and only this test says so",
        )

if __name__ == "__main__":
    unittest.main()
