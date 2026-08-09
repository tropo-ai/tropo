#!/usr/bin/env python3
"""Safety properties of the boot stale-sweep.

WHY THIS FILE EXISTS. The sweep landed on main on 2026-08-03 and an adversarial
review found three defects in it within hours — every one of them a way for a
mechanism built to UNBLOCK agents to instead destroy one. None was caught by the
existing suites, because the existing suites test that the sweep closes what it
should. Nothing tested what it must NOT close, or what happens when the world is
not cooperative.

The three, and the property each one now pins:

  1. `activated_at` is a bare LOCAL date. Parsed as midnight UTC it over-stated
     age by a full timezone offset, so a record written *this second* computed as
     16.6h old — and against `sa: 2h` / `child-agent: 4h` / `worker: 6h`, every
     sub-agent activation in the studio was sweepable AT BIRTH. Two overlapping
     sa.skeptic runs (26 were written on one day in May) and the second boot
     would have retired the first mid-work and killed its broker.
     -> AGE IS NEVER OVER-ESTIMATED.

  2. The sweep runs before the newborn's own entry exists, so the card-sync
     guard found no live activation and retired the CARD — for an agent being
     born milliseconds later, with nothing to set it back. The crew brief renders
     from cards, so the new generation would be born invisible. The Po failure
     inverted, produced by the fix for Po, the same day.
     -> A BOOT SWEEP NEVER TOUCHES THE CARD.

  3. The sweep hard-coded the SIGNED close path, which needs a live ssh-agent
     belonging to the agent being closed — but that agent is by definition gone,
     and /private/tmp is cleared on reboot. So it failed deterministically in the
     commonest death mode, forever. Three of five open activations already had no
     key directory when this was found.
     -> THE CLOSE PATH IS CHOSEN BY PROBING, NOT ASSUMED.

The general rule these share, and the one worth carrying: **when a value is
ambiguous and the answer is wired to a destructive action, resolve it in the
direction that cannot destroy.** Sweeping a dead record a day late is harmless.
Sweeping a live agent early is not.
"""

import datetime
import importlib.util
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "vault" / "tools"))
_spec = importlib.util.spec_from_file_location(
    "activation_tool", REPO / "vault" / "tools" / "40b2f455.py"
)
TOOL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TOOL)


class TestAgeIsNeverOverEstimated(unittest.TestCase):
    """Age drives an automatic irreversible close. It must under-state, never over."""

    def _age(self, activated_at):
        return TOOL._activation_age_hours({"activated_at": activated_at})

    def test_a_record_written_today_is_not_sweepable_at_any_threshold(self):
        """The defect, pinned. This is the one that could have killed a live agent."""
        age = self._age(TOOL.TODAY)
        for agent_class, threshold in TOOL.STALE_THRESHOLD_DEFAULTS.items():
            self.assertLess(
                age,
                threshold,
                f"a {agent_class} activation written TODAY computes as {age:.1f}h "
                f"against its own {threshold}h threshold — it would be swept, and "
                f"its signing key destroyed, at birth",
            )

    def test_bare_date_resolves_to_the_youngest_reading(self):
        """A date has 24h of ambiguity. Resolve it in the safe direction.

        This assertion used to read `== 0.0`, which was only true while the
        machine was still inside that UTC day. It failed at 01:07Z the night it
        was written — a test that goes red every midnight regardless of the
        code. The PROPERTY is what matters: a bare date must never resolve
        older than the last instant of that day. Pin the property, not a clock.
        """
        age = self._age(TOOL.TODAY)
        naive = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.datetime.fromisoformat(TOOL.TODAY).replace(
                tzinfo=datetime.timezone.utc)
        ).total_seconds() / 3600.0
        self.assertLess(
            age, naive,
            "a bare date must resolve to the LAST instant of that day, not the "
            "first — the first over-states age by up to 24h plus the machine's "
            "timezone offset, which is what made every sub-agent activation "
            "sweepable at birth",
        )
        self.assertGreaterEqual(age, 0.0, "and never negative")

    def test_a_full_instant_is_used_as_given(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        six_hours_ago = (now - datetime.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertAlmostEqual(self._age(six_hours_ago), 6.0, delta=0.1)

    def test_new_records_carry_an_instant_not_a_date(self):
        """The legacy leniency must shrink, not become permanent."""
        self.assertRegex(
            TOOL.NOW_ISO,
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
            "activated_at on new records must be a full UTC instant; a bare date "
            "is what made the arithmetic unsafe in the first place",
        )

    def test_genuinely_old_records_still_sweep(self):
        """The fix must not disarm the sweep — Po sat 30 days for want of this."""
        thirty_days = (
            datetime.date.today() - datetime.timedelta(days=30)
        ).isoformat()
        self.assertGreater(self._age(thirty_days), 168.0)

    def test_an_unreadable_date_is_never_treated_as_old(self):
        for bad in ("", "not-a-date", "2026-13-45", None):
            self.assertIsNone(
                TOOL._activation_age_hours({"activated_at": bad}),
                f"{bad!r} must yield None (unknown), never a large number — an "
                "unparseable date must not read as 'ancient, safe to close'",
            )


class TestSweepDoesNotTouchTheNewbornsCard(unittest.TestCase):
    def test_boot_sweep_suppresses_card_sync(self):
        """The signature carries the flag the boot path uses to opt out."""
        import inspect

        sig = inspect.signature(TOOL._run_post_close_side_effects)
        self.assertIn(
            "sync_card",
            sig.parameters,
            "the boot sweep must be able to suppress the card sync; without it, "
            "the sweep retires the card of the agent being born",
        )
        self.assertTrue(
            sig.parameters["sync_card"].default,
            "an ordinary close must still sync the card — only the boot sweep opts out",
        )

    def test_the_sweep_sets_the_boot_sweep_flag(self):
        """Read the source: the sweep must mark its closes as boot-originated."""
        src = inspect_source = pathlib.Path(
            REPO / "vault" / "tools" / "40b2f455.py"
        ).read_text(encoding="utf-8")
        start = src.index("def _sweep_abandoned_predecessors")
        body = src[start : src.index("\ndef ", start + 10)]
        self.assertIn(
            "boot_sweep=True",
            body,
            "the sweep's close args must carry boot_sweep=True, or the card of "
            "the newborn generation is retired at its own birth",
        )


class TestClosePathIsProbedNotAssumed(unittest.TestCase):
    def test_the_sweep_probes_the_broker(self):
        src = pathlib.Path(REPO / "vault" / "tools" / "40b2f455.py").read_text(
            encoding="utf-8"
        )
        start = src.index("def _sweep_abandoned_predecessors")
        body = src[start : src.index("\ndef ", start + 10)]
        self.assertIn(
            "probe_signing_broker",
            body,
            "the sweep must PROBE rather than assume a close path: hard-coding "
            "signed fails forever once the broker is gone (the common case), and "
            "hard-coding attested is refused outright when the broker is live",
        )
        self.assertIn(
            "broker_lost=not broker_alive",
            body,
            "world-state chooses the path — an attested grade must mean the "
            "signature was impossible, never merely inconvenient",
        )




class TestAnEndedLineageIsNeverAskedAboutAgain(unittest.TestCase):
    """A decided question must never be reported as an open defect.

    The tropo agent was renamed to Po and formally retired on 2026-08-01 by
    argus-a143, carrying Mike's verbatim ruling and the explicit sentence "no T2
    is to be born". The answer has been written down since then.

    The fleet health check never read it. It probed every lineage, could not
    resolve a successor for a lineage somebody had deliberately ended, and
    reported it as CANNOT BOOT — on every run, forever. Agent after agent then
    raised it with Mike as a loose end. Mike, 2026-08-03: "I never want to hear
    about this issue again."

    Two costs, and the second is the worse one. The human is made to re-decide
    something already decided. And a check that is PERMANENTLY red teaches the
    crew to ignore the one instrument that would have caught a real blocker —
    which is exactly how this studio spent thirty days not noticing Po's own
    record was stuck open.
    """

    def test_superseded_agents_are_excluded_from_the_birth_probe(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tv", REPO / "vault" / "tools" / "tropo-validate.py")
        tv = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(tv)
        except SystemExit:
            pass
        findings, _checked, _blocked = tv.check_every_agent_can_still_boot(REPO)
        for line in findings:
            self.assertNotIn(
                "tropo (", line,
                "the tropo lineage was ENDED, not broken — superseded_by names "
                "Po. Re-litigating a decided question is a defect in the "
                "instrument, not a finding about the fleet",
            )

    def test_the_marker_is_read_from_the_agent_record(self):
        """superseded_by is the marker. It already exists; nothing new invented."""
        card = (REPO / "vault" / "agents" / "566770f7.md").read_text(encoding="utf-8")
        self.assertIn("superseded_by:", card)
        self.assertIn("no T2 is to be born", card,
                      "the ruling text is the durable record; the check merely "
                      "has to stop asking past it")

if __name__ == "__main__":
    unittest.main(verbosity=2)
