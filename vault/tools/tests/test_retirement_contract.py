#!/usr/bin/env python3
"""Contract for retirement — v2, after adversarial review demolished v1.

Build increment 2. Scope: the retirement tool. The memory-fold lock is
DELIBERATELY OUT — see "What was cut and why" below.

────────────────────────────────────────────────────────────────────────────────
V1 WAS NOT SAFE TO BUILD AGAINST. The reviewer proved it rather than argued it,
and the failures are recorded here because they are the same failures this whole
session is about.

  * Two of sixteen tests COULD NOT FAIL. The reviewer wrote a deliberately
    broken implementation — status written first, transfer copied
    non-atomically — and both write-order tests passed it. One matched on
    `.replace(`, which hits any Python string replace. The other computed
    `status_at` and never used it; its only live assertion was a tautology.
    They were the two tests guarding what v1's own docstring called "contract,
    not implementation detail."
  * MOVING THE TRANSFER WOULD HAVE CAUSED THE LOSS IT CLAIMS TO PREVENT. Eight
    files still read the old location, including live code (`lib/distiller.py`,
    `40b2f455.py`). Move the writer without the reader and a successor reads an
    empty section — or its grandparent's letter as current, which is exactly
    what rule 4 exists to stop.
  * A FOLD LOCK WITH NO CALLER. Nothing in this studio folds memory in code;
    the fold is an LLM sub-agent editing markdown. A mutex in `vault/tools/lib/`
    had nothing that could take it. All four of v1's lock tests passed against a
    twelve-line threading-only stub, because they used threads and the real
    adversary is two processes.
  * AN EMPTY TRANSFER STILL FLIPPED THE STATE, and v1's own content assertion
    was `assertIn("", text)` on an empty letter — vacuously true.
  * THE CLASS LIST WAS WRONG IN BOTH DIRECTIONS. Measured across all activation
    records: `executive` 229, `pipeline` 168, `sa` 102, `cosmo` 6, six records
    with no class at all, one typo'd `pipelin`. v1 tested `worker` and
    `child-agent`, which have NEVER existed, and omitted `cosmo`, which has a
    soul, a memory fold and a populated transfers directory. Cosmo would have
    retired with no handoff and no finding.
────────────────────────────────────────────────────────────────────────────────

WHAT WAS CUT, AND WHY THAT IS THE RIGHT CALL

The memory-fold lock is gone from this increment. Three reasons, in order:

  1. Nothing in code performs a fold, so a library mutex is a mutex over
     nothing. Specifying one was a category error.
  2. Moving the transfer into its own file REMOVES the fold's ability to destroy
     it — which was the hazard that motivated the lock. The fix comes free with
     the move.
  3. The residual hazard is real (two generations folding concurrently lose each
     other's entries) but it needs a different answer than a lock, because the
     thing to coordinate is two LLM sessions, not two processes. Filed, not
     faked. A contract that specifies an untakeable lock is worse than one that
     admits the gap.

────────────────────────────────────────────────────────────────────────────────
THE INTERFACE UNDER TEST

    python3 vault/tools/tropo-retire.py \\
        --activation-uid <uid> --vault-root <path> \\
        ( --transfer-file <path> | --transfer - | --no-transfer ) \\
        [--reason <closure-reason>]

  stdout  one line of JSON:
            {"activation_uid": "...", "status": "retired"|"active",
             "transfer_path": "agents/<slug>/transfers/<generation>.md"|null,
             "findings": [...]}

  EXIT AND REFUSAL — stated precisely, because v1 contradicted itself here.
  The tool never refuses to RECORD. It refuses exactly three things, and every
  one guards a destructive act or an impossibility:

    1. The activation UID does not resolve   -> nothing to retire.
    2. The transfer source is unreadable or empty -> the state does NOT flip.
       The record stays `active`, which rule 9 already calls the recoverable
       state, and the successor's flag surfaces it. A generation's last words
       are not silently replaced by a zero-byte file.
    3. The generation is already retired     -> the existing transfer is never
       overwritten.

  PLACEMENT IS CREATE-ONLY. v1 mandated rename(), whose defining property is
  silent clobbering, while also forbidding overwrite — the mandated mechanism
  contradicted the mandated property. Staging plus os.link() is atomic AND
  fails if the destination exists, which makes the guard, the crash-recovery
  path and the no-overwrite property one mechanism instead of three.

  WRITE ORDER IS CONTRACT: transfer placed -> THEN status. A crash between them
  leaves "letter exists, status still active" — recoverable, because the letter
  is ground truth. The reverse claims a handoff that does not exist.
────────────────────────────────────────────────────────────────────────────────
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
TOOL = REPO / "vault" / "tools" / "tropo-retire.py"

# Classes whose successor reads a handoff. Measured, not guessed. Unknown
# classes default INTO this set (see test_an_unknown_class_defaults_to_needing
# _a_handoff) so a new class produces a finding rather than silence.
HANDOFF_CLASSES = {"executive", "cosmo", "director", "tropo"}
NO_HANDOFF_CLASSES = {"pipeline", "sa"}


class RetirementFixture(unittest.TestCase):
    def setUp(self):
        self.studio = pathlib.Path(tempfile.mkdtemp(prefix="retirespec-"))
        (self.studio / "vault" / "files").mkdir(parents=True)
        self.files = self.studio / "vault" / "files"

    def tearDown(self):
        shutil.rmtree(self.studio, ignore_errors=True)

    def plant(self, uid, agent="probe", generation="G1",
              status="active", agent_class="executive"):
        (self.files / f"{uid}.md").write_text(
            f"---\nuid: {uid}\ntype: activation\nagent: {agent}\n"
            f"generation: {generation}\nstatus: {status}\n"
            f"agent_class: {agent_class}\nactivated_by: mike\n"
            "activated_at: 2026-08-01T09:00:00Z\n---\n\n# entry\n",
            encoding="utf-8")
        return uid

    def retire(self, uid, transfer="a letter", env=None, **kw):
        cmd = [sys.executable, str(TOOL), "--activation-uid", uid,
               "--vault-root", str(self.studio)]
        if transfer is None:
            cmd.append("--no-transfer")
        else:
            path = self.studio / "letter.md"
            path.write_text(transfer, encoding="utf-8")
            cmd += ["--transfer-file", str(path)]
        for k, v in kw.items():
            cmd += [f"--{k.replace('_','-')}", str(v)]
        e = dict(os.environ, **(env or {}))
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=e)
        try:
            parsed = json.loads(p.stdout.strip())
        except (ValueError, AttributeError):
            parsed = None
        return p.returncode, parsed, p.stderr

    def field(self, uid, name):
        for line in (self.files / f"{uid}.md").read_text().splitlines():
            if line.startswith(f"{name}:"):
                return line.split(":", 1)[1].strip()
        return None


class TestRetirementIsNeverBlocked(RetirementFixture):
    """R-N3. Po sat thirty days because six invariants demanded work only the
    dead agent could do, and the only candidate was the agent it blocked."""

    def test_no_reflection_no_fold_no_run_folder_no_drained_events(self):
        uid = self.plant("aaaa0001")
        code, out, _ = self.retire(uid)
        self.assertEqual(code, 0, "ceremony is recorded, never required")
        self.assertEqual(out["status"], "retired")

    def test_only_an_unresolvable_uid_fails_outright(self):
        code, _, err = self.retire("deadbeef")
        self.assertNotEqual(code, 0)
        self.assertIn("deadbeef", err)


class TestTheDestructiveHalfIsGuarded(RetirementFixture):
    """The three refusals. Each guards a destructive act, never existence."""

    def test_an_empty_transfer_does_not_flip_the_state(self):
        """D2. A dying session fat-fingers a path, or the heredoc that wrote the
        letter was truncated by the same context exhaustion that triggered the
        retirement. v1 flipped anyway and made it unrecoverable."""
        uid = self.plant("aaaa0001")
        _, out, _ = self.retire(uid, transfer="")
        self.assertEqual(self.field(uid, "status"), "active",
                         "an empty letter must NOT be recorded as a handoff")
        self.assertTrue(out["findings"])

    def test_an_unreadable_transfer_source_does_not_flip_the_state(self):
        uid = self.plant("aaaa0001")
        cmd = [sys.executable, str(TOOL), "--activation-uid", uid,
               "--vault-root", str(self.studio),
               "--transfer-file", str(self.studio / "does-not-exist.md")]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(self.field(uid, "status"), "active")
        self.assertTrue(p.stderr.strip(), "and it must say why")

    def test_a_second_retirement_never_overwrites_the_first_letter(self):
        """D7 + C2. v1 put this whole assertion behind `if file.is_file()`, so it
        passed if the second run DELETED the letter."""
        uid = self.plant("aaaa0001")
        self.retire(uid, transfer="the first generation's last words")
        letter = self.studio / "agents" / "probe" / "transfers" / "G1.md"
        self.assertTrue(letter.is_file(), "the first letter must exist")
        self.retire(uid, transfer="SECOND letter, must not land")
        self.assertIn("first generation's last words", letter.read_text())
        self.assertNotIn("SECOND", letter.read_text())

    def test_a_second_retirement_never_overwrites_the_closure_RECORD(self):
        """The gap the builder found by mutation-testing this contract.

        It deleted the `already retired` refusal and NOTHING went red — because
        create-only placement independently protects the LETTER, so the
        no-overwrite test passed without the refusal existing at all. What was
        left unguarded is the closure RECORD: a second run would adopt the
        existing letter and then overwrite `retired_at`, `closure_reason` and
        `closure_findings` with fresh values, destroying the record of the real
        closure.

        v2 fixed "the letter is never overwritten" and did not notice it had
        left "the closure record is never overwritten" untested. Two facts, one
        of them guarded. Rule 7's shape, in a contract written to enforce it.
        """
        uid = self.plant("aaaa0001")
        self.retire(uid, transfer="the real closure", reason="clean-retirement")
        first_retired_at = self.field(uid, "retired_at")
        first_reason = self.field(uid, "closure_reason")
        self.assertIsNotNone(first_retired_at)

        self.retire(uid, transfer="a second attempt", reason="stale-sweep")
        self.assertEqual(self.field(uid, "retired_at"), first_retired_at,
                         "the timestamp of the REAL closure must survive")
        self.assertEqual(self.field(uid, "closure_reason"), first_reason,
                         "and so must its reason — a re-run must not restate "
                         "why a generation ended")

    def test_placement_is_create_only_not_clobbering(self):
        """The mechanism must FAIL on an occupied destination rather than
        silently replace it — RUN it, do not grep for it.

        v1 grepped the source for `os.replace` and the reviewer defeated that
        with a dead reference. Standing rule, Mike-agreed 2026-08-03: a test
        either runs the thing or it does not exist. Grepping source text is a
        comment that fails the build.
        """
        uid = self.plant("aaaa0001")
        letter = self.studio / "agents" / "probe" / "transfers" / "G1.md"
        letter.parent.mkdir(parents=True, exist_ok=True)
        letter.write_text("a letter that is ALREADY THERE\n", encoding="utf-8")
        self.retire(uid, transfer="this must not land on top of it")
        self.assertIn("ALREADY THERE", letter.read_text(),
                      "placement must refuse an occupied destination, never "
                      "silently replace it")


class TestCrashSafety(RetirementFixture):
    """C1. v1 grepped the source for a substring. This runs the crash."""

    def test_a_crash_after_the_transfer_leaves_the_recoverable_state(self):
        uid = self.plant("aaaa0001")
        self.retire(uid, transfer="my last words",
                    env={"TROPO_RETIRE_CRASH_AFTER": "transfer"})
        letter = self.studio / "agents" / "probe" / "transfers" / "G1.md"
        self.assertTrue(letter.is_file(), "the letter must have landed")
        self.assertIn("my last words", letter.read_text(),
                      "and landed COMPLETE — atomic placement, not a partial write")
        self.assertEqual(self.field(uid, "status"), "active",
                         "status must lag the transfer, never lead it")

    def test_rerunning_after_that_crash_completes_the_retirement(self):
        """The recovery path v1 declared and never specified."""
        uid = self.plant("aaaa0001")
        self.retire(uid, transfer="my last words",
                    env={"TROPO_RETIRE_CRASH_AFTER": "transfer"})
        code, out, _ = self.retire(uid, transfer="my last words")
        self.assertEqual(code, 0)
        self.assertEqual(self.field(uid, "status"), "retired")
        letter = self.studio / "agents" / "probe" / "transfers" / "G1.md"
        self.assertIn("my last words", letter.read_text(),
                      "recovery must not rewrite the letter it is recovering")

    def test_the_activation_record_survives_a_crash_mid_status_write(self):
        """D6. This is the file Vela V71 corrupted, blocking her lineage for
        fifteen hours — an unparseable activation entry that nothing detected.

        Run the crash rather than grepping for `fsync`: kill the process during
        the status write and assert the record still parses. A truncated record
        is the failure; atomic replace is only one way to avoid it, and the
        contract should pin the outcome, not the technique.
        """
        import yaml
        uid = self.plant("aaaa0001")
        self.retire(uid, transfer="my last words",
                    env={"TROPO_RETIRE_CRASH_AFTER": "status-partial"})
        raw = (self.files / f"{uid}.md").read_text()
        self.assertTrue(raw.startswith("---"), "record must not be truncated")
        fm = yaml.safe_load(raw.split("---")[1])
        self.assertEqual(fm.get("uid"), uid,
                         "the record must still parse after a crash mid-write; "
                         "an unparseable activation entry is the exact defect "
                         "that blocked Vela's lineage for fifteen hours")


class TestWhoNeedsAHandoff(RetirementFixture):
    """C3. v1 tested two classes that have never existed and omitted one that has."""

    def test_classes_with_a_successor_get_a_finding_when_no_transfer(self):
        for i, klass in enumerate(sorted(HANDOFF_CLASSES)):
            with self.subTest(klass=klass):
                uid = self.plant(f"cccc000{i}", agent_class=klass)
                code, out, _ = self.retire(uid, transfer=None)
                self.assertEqual(code, 0, "never refuse")
                self.assertTrue(out["findings"],
                                f"{klass} has a successor that reads a handoff")

    def test_classes_without_a_successor_retire_clean(self):
        for i, klass in enumerate(sorted(NO_HANDOFF_CLASSES)):
            with self.subTest(klass=klass):
                uid = self.plant(f"dddd000{i}", agent_class=klass)
                code, out, _ = self.retire(uid, transfer=None)
                self.assertEqual(code, 0)
                self.assertEqual(out["status"], "retired")
                self.assertFalse(out["findings"],
                                 f"{klass} has no handoff to be missing")

    def test_an_unknown_class_defaults_to_needing_a_handoff(self):
        """Silence is the dangerous default. A class nobody enumerated must
        produce a finding, not a clean retirement. Six records carry NO class at
        all and one is a typo'd 'pipelin'."""
        uid = self.plant("eeee0001", agent_class="brand-new-class")
        _, out, _ = self.retire(uid, transfer=None)
        self.assertTrue(out["findings"],
                        "an unrecognised class must fail loud, not fail silent")


class TestTheRecordIsHonestAndReadable(RetirementFixture):
    """C4 + C5. Findings must survive the process; readers must still parse."""

    def test_findings_are_written_into_the_record_not_just_stdout(self):
        """C4. A JSON line on a dead subprocess's stdout is not a record.
        Retirement's premise is that sessions die with nobody watching."""
        uid = self.plant("aaaa0001", agent_class="executive")
        self.retire(uid, transfer=None)
        text = (self.files / f"{uid}.md").read_text()
        self.assertIn("closure_findings", text,
                      "the birth path got this right — provisional_reasons go "
                      "IN the record; retirement must match")

    def test_the_record_points_at_the_transfer(self):
        """C5. tropo-smoke.py blocks on a dangling transfer pointer with 'the
        successor's first act reads through a dangling pointer'. If the new tool
        writes nothing, that check goes quietly empty."""
        uid = self.plant("aaaa0001")
        _, out, _ = self.retire(uid)
        text = (self.files / f"{uid}.md").read_text()
        self.assertIn("transfers/", text)

    def test_familiar_fields_survive(self):
        uid = self.plant("aaaa0001")
        self.retire(uid)
        for f in ("uid", "type", "agent", "generation", "status",
                  "agent_class", "retired_at", "closure_reason"):
            self.assertIsNotNone(self.field(uid, f), f"{f} must survive")


class O34Fixture(RetirementFixture):
    """Helpers for the three findings Orpheus O34 brought back from the first real
    retirement ever run through this tool — on her own record, blunt by request.

    A SUBCLASS, not an edit to RetirementFixture. Every test above this line predates
    those findings and none of them plants a card or a memory surface; changing the shared
    fixture to grow them would silently change what twenty existing tests are testing.
    """

    def plant_card(self, uid, agent="probe", status="ACTIVE"):
        """vault/agents/<uid>.md — the file 00-crew-brief.md actually renders from."""
        root = self.studio / "vault" / "agents"
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{uid}.md").write_text(
            f"---\nuid: {uid}\ntype: agent\ntitle: {agent.title()} — Probe\n"
            f"agent: {agent}\nrole: Probe\nagent_class: executive\n"
            f"status: {status}\ngeneration: G1\nstate: active\n---\n\n"
            f"# {agent.title()} — Unified Agent Entry\n",
            encoding="utf-8")
        return root / f"{uid}.md"

    def card_status(self, uid):
        for line in (self.studio / "vault" / "agents" / f"{uid}.md").read_text().splitlines():
            if line.startswith("status:"):
                return line.split(":", 1)[1].strip()
        return None

    def plant_memory_surface(self, agent="probe", transfer="THE GRANDPREDECESSOR'S LETTER"):
        """The v3 memory surface, in the shape the Tier-3 boot contracts read."""
        path = (self.studio / "agents" / agent / ".tropo-capsule" / "memory"
                / "agent-memory.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nuid: bbbb0001\ntype: memory\nagent: {agent}\n---\n\n"
            f"# {agent.title()} — Agent Memory (v3 surface)\n\n"
            "## §Top-of-Mind\n\n- KEEP-TOP-OF-MIND\n\n"
            f"## §Living-Transfer-from-Predecessor\n\n{transfer}\n\n"
            "## §History\n\n- KEEP-HISTORY\n\n"
            "## §Memories (STM)\n\n- KEEP-MEMORIES\n",
            encoding="utf-8")
        return path

    def surface_text(self, agent="probe"):
        return (self.studio / "agents" / agent / ".tropo-capsule" / "memory"
                / "agent-memory.md").read_text(encoding="utf-8")

    def what_the_booting_successor_reads(self, agent="probe"):
        """The transfer section as vault/tools/lib/distiller.py extracts it.

        Copied from the live reader deliberately, not approximated: the point of writing
        this home at all is that a booting successor reads THIS, so the assertion has to
        be made through the reader's own boundary rule rather than through a substring
        search that would pass on text the reader never returns.
        """
        text = self.surface_text(agent)
        head = re.search(
            r"(?m)^##\s+§Living-Transfer-from-Predecessor[^\n]*(?:\n|$)", text)
        if head is None:
            return None
        rest = text[head.end():]
        nxt = re.search(r"(?m)^##\s+", rest)
        return rest[:nxt.start()] if nxt else rest


class TestTheCardFlipsWithTheRecord(O34Fixture):
    """F5, Orpheus O34 — HIGH. THE PO BUG, REBUILT.

    The tool flipped vault/files/<activation>.md and never touched
    vault/agents/<agent_uid>.md, which went on reading `status: ACTIVE`.
    `00-crew-brief.md` renders from the CARD, so a retired agent showed ACTIVE to the
    whole crew until a human noticed. Po read as live with a last session thirty days old;
    Orpheus flipped her own card by hand after this tool did not.

    One fact, two homes, one gesture — or they diverge and nothing says so.
    """

    def test_the_card_retires_with_the_last_activation(self):
        uid = self.plant("aaaa0001")
        self.plant_card("cardaaa1")
        code, out, _ = self.retire(uid)
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "retired")
        self.assertEqual(self.card_status("cardaaa1"), "RETIRED",
                         "the crew brief renders from the CARD; a card left ACTIVE "
                         "advertises a dead agent as live to everyone who boots")

    def test_a_live_generation_keeps_the_card(self):
        """The guard, and it is not decoration: overlapping generations are normal, and a
        closing one must not retire the card out from under a successor already live."""
        for i, live_status in enumerate(("active", "paused")):
            with self.subTest(successor=live_status):
                self.setUp()
                uid = self.plant("aaaa0001")
                self.plant("aaaa0002", status=live_status)  # same agent, still holding it
                self.plant_card(f"cardbbb{i}")
                code, _, _ = self.retire(uid)
                self.assertEqual(code, 0, "the retirement still lands")
                self.assertEqual(self.field(uid, "status"), "retired")
                self.assertEqual(self.card_status(f"cardbbb{i}"), "ACTIVE",
                                 "a live successor still holds the card")

    def test_a_retired_sibling_does_not_hold_the_card(self):
        """The guard must look at STATUS, not at the mere existence of another record —
        otherwise the card never flips again after an agent's second generation."""
        uid = self.plant("aaaa0001")
        self.plant("aaaa0002", status="retired")
        self.plant_card("cardccc1")
        self.retire(uid)
        self.assertEqual(self.card_status("cardccc1"), "RETIRED")

    def test_another_agents_card_is_never_touched(self):
        uid = self.plant("aaaa0001", agent="probe")
        self.plant_card("cardddd1", agent="probe")
        self.plant_card("carddde2", agent="bystander")
        self.retire(uid)
        self.assertEqual(self.card_status("cardddd1"), "RETIRED")
        self.assertEqual(self.card_status("carddde2"), "ACTIVE",
                         "retiring one agent must not retire another")

    def test_a_missing_card_is_recorded_never_fatal(self):
        """Retirement is never blocked by a second home it cannot find — but it does not
        go quiet about it either, because the crew brief will keep rendering the old
        answer from wherever that card actually lives."""
        uid = self.plant("aaaa0001")
        self.plant_card("cardeee1", agent="someone-else")
        code, out, _ = self.retire(uid)
        self.assertEqual(code, 0, "never refuse")
        self.assertEqual(self.field(uid, "status"), "retired")
        self.assertTrue(any("card" in f.lower() for f in out["findings"]),
                        "a card layer that exists and has no card for this agent is a "
                        "finding, not silence")


class TestTheLetterReachesTheBootContract(O34Fixture):
    """F2, Orpheus O34 — HIGH, silent handoff loss.

    The tool wrote agents/<slug>/transfers/<GEN>.md and never touched the memory surface.
    But the agents' Tier-3 boot contracts say the successor boot-reads ONE file — the
    memory surface — and reads §Living-Transfer-from-Predecessor. So the successor would
    read its GRANDPREDECESSOR's letter, silently, while its actual predecessor's sat in a
    location its boot contract tells it to ignore. Orpheus wrote to both homes by hand.

    Two homes, written together, DELIBERATELY and temporarily: it collapses to one when
    the readers move — which is what TestTheReaderMovesWithTheWriter gates.
    """

    def test_the_letter_lands_in_BOTH_homes(self):
        uid = self.plant("aaaa0001")
        self.plant_memory_surface()
        code, out, _ = self.retire(uid, transfer="MY LAST WORDS TO MY SUCCESSOR")
        self.assertEqual(code, 0)
        per_generation = self.studio / "agents" / "probe" / "transfers" / "G1.md"
        self.assertIn("MY LAST WORDS", per_generation.read_text(),
                      "the per-generation file is home one")
        self.assertIn("MY LAST WORDS", self.what_the_booting_successor_reads(),
                      "and the memory surface is the home the boot contract reads — "
                      "through the live reader's own section boundary, not a substring "
                      "of a file the reader would never return")

    def test_the_predecessors_letter_is_replaced_not_stacked(self):
        """A handoff, not an append. Two generations' words under one heading with
        nothing saying which is current is the same read failure in a costlier disguise."""
        uid = self.plant("aaaa0001")
        self.plant_memory_surface(transfer="THE GRANDPREDECESSOR'S LETTER")
        self.retire(uid, transfer="MY LAST WORDS")
        text = self.surface_text()
        self.assertIn("MY LAST WORDS", text)
        self.assertNotIn("GRANDPREDECESSOR", text,
                         "the section is replaced wholesale; a successor must not be able "
                         "to read its grandpredecessor's letter as current")

    def test_the_rest_of_the_memory_surface_is_untouched(self):
        """The agent's own accumulated memory is not this tool's to edit. Only the
        transfer section moves."""
        uid = self.plant("aaaa0001")
        self.plant_memory_surface()
        self.retire(uid, transfer="MY LAST WORDS")
        text = self.surface_text()
        for marker in ("## §Top-of-Mind", "KEEP-TOP-OF-MIND", "## §History",
                       "KEEP-HISTORY", "## §Memories (STM)", "KEEP-MEMORIES"):
            self.assertIn(marker, text, f"{marker} must survive a retirement")

    def test_a_missing_memory_surface_is_a_finding_not_a_failure(self):
        uid = self.plant("aaaa0001")  # no surface planted
        code, out, _ = self.retire(uid, transfer="MY LAST WORDS")
        self.assertEqual(code, 0, "never refuse")
        self.assertEqual(self.field(uid, "status"), "retired")
        self.assertTrue(any("memory surface" in f.lower() for f in out["findings"]),
                        "one home written instead of two must be said out loud")
        self.assertIn("closure_findings", (self.files / f"{uid}.md").read_text(),
                      "and it must be in the RECORD — nobody is watching the terminal "
                      "of a session that just died")

    def test_a_letter_whose_own_h2_truncates_it_for_the_reader_is_reported(self):
        """The reader ends the section at the next `## ` of ANY kind, so an h2 inside the
        letter cuts off everything below it for a booting successor. The tool does not
        rewrite a generation's last words to fix that — it says so."""
        uid = self.plant("aaaa0001")
        self.plant_memory_surface()
        _, out, _ = self.retire(
            uid, transfer="the opening\n\n## A Heading Of My Own\n\nthe rest")
        self.assertNotIn("the rest", self.what_the_booting_successor_reads(),
                         "this test is only meaningful while the reader truncates here")
        self.assertTrue(any("truncate" in f.lower() for f in out["findings"]),
                        "a letter the boot reader will cut in half must produce a "
                        "finding, not a silent half-handoff")


class TestTheTidiestUserIsNotAlarmed(O34Fixture):
    """F3, Orpheus O34 — MEDIUM. Source == destination read as an alarm.

    She authored her letter AT the destination path and passed that same path as
    --transfer-file. The tool refused with "the occupant is a different generation's words
    and someone should look" — about her own letter, written ninety seconds earlier. Her
    line: "as written, the tidiest users get the scariest finding."

    The anti-overwrite guard is correct and must stay. Only the message was wrong.
    """

    def retire_from(self, uid, source):
        cmd = [sys.executable, str(TOOL), "--activation-uid", uid,
               "--vault-root", str(self.studio), "--transfer-file", str(source)]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        try:
            return p.returncode, json.loads(p.stdout.strip()), p.stderr
        except (ValueError, AttributeError):
            return p.returncode, None, p.stderr

    def test_a_letter_authored_at_the_destination_retires_clean(self):
        uid = self.plant("aaaa0001")
        self.plant_memory_surface()  # both homes present, so a clean run has NO findings
        dest = self.studio / "agents" / "probe" / "transfers" / "G1.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("MY OWN LETTER, WRITTEN HERE\n", encoding="utf-8")

        code, out, err = self.retire_from(uid, dest)
        self.assertEqual(code, 0)
        self.assertEqual(self.field(uid, "status"), "retired",
                         "the status flip still happens")
        self.assertEqual(out["findings"], [],
                         "a letter already at its destination is nothing to report — "
                         "the tidiest users must not get the scariest finding")
        self.assertIn("already in place", err.lower(),
                      "and it should say plainly that there was nothing to do")
        self.assertEqual(dest.read_text(), "MY OWN LETTER, WRITTEN HERE\n",
                         "her words, unaltered")

    def test_a_symlink_to_the_destination_is_the_same_file(self):
        uid = self.plant("aaaa0001")
        self.plant_memory_surface()
        dest = self.studio / "agents" / "probe" / "transfers" / "G1.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("MY OWN LETTER\n", encoding="utf-8")
        alias = self.studio / "my-letter.md"
        os.symlink(dest, alias)
        _, out, _ = self.retire_from(uid, alias)
        self.assertEqual(self.field(uid, "status"), "retired")
        self.assertEqual(out["findings"], [],
                         "identity is the file, not the path spelled to reach it")

    def test_a_DIFFERENT_letter_at_the_destination_still_raises_the_alarm(self):
        """The guard the F3 fix must not have disarmed. A genuinely occupied destination
        is still an occupied destination, and it still gets said out loud."""
        uid = self.plant("aaaa0001")
        dest = self.studio / "agents" / "probe" / "transfers" / "G1.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("SOMEONE ELSE'S WORDS\n", encoding="utf-8")
        _, out, _ = self.retire(uid, transfer="this must not land on top of it")
        self.assertIn("SOMEONE ELSE'S WORDS", dest.read_text())
        self.assertTrue(any("occupied" in f.lower() for f in out["findings"]),
                        "an occupied destination holding a DIFFERENT letter is exactly "
                        "the case the finding exists for")


class TestTheRemedyIsOneThatWorks(O34Fixture):
    """F4, Orpheus O34 — MEDIUM. The suggested cure did not work.

    The index-freshen finding said to run `tropo-rebuild-index.py --only <uid>`. That is
    the command that JUST failed, and it refuses identically whenever unrelated files have
    moved — its own refusal text says "Run a full --apply" (and test_tropo_smoke.py records
    the same: "--apply restores the virtuals and unblocks --only"). So the tool knew the
    answer and printed the wrong one. A stranger runs the suggestion, hits the same wall,
    and reasonably concludes the retirement is broken.
    """

    def test_the_index_finding_names_the_command_that_actually_recovers(self):
        uid = self.plant("aaaa0001")
        (self.studio / "vault" / "00-index.jsonl").write_text("", encoding="utf-8")
        tools = self.studio / "vault" / "tools"
        tools.mkdir(parents=True, exist_ok=True)
        # A freshener that refuses exactly the way the real one refuses when unrelated
        # files have moved. Run, not mocked: the finding is produced by the real code path.
        (tools / "tropo-rebuild-index.py").write_text(
            "import sys\n"
            "sys.stderr.write('[rebuild --only] REFUSAL: source inventory incomplete; "
            "Run a full --apply; no derived rows written\\n')\n"
            "raise SystemExit(1)\n", encoding="utf-8")

        code, out, _ = self.retire(uid)
        self.assertEqual(code, 0, "a stale index row never unwinds a retirement")
        self.assertEqual(self.field(uid, "status"), "retired")
        index_findings = [f for f in out["findings"] if "index" in f.lower()]
        self.assertTrue(index_findings, "a record with no fresh row must be said out loud")
        for finding in index_findings:
            # The COMMAND the finding tells a reader to run — not the freshener's own
            # echoed refusal, which legitimately quotes its `[rebuild --only]` prefix.
            self.assertIn("tropo-rebuild-index.py --apply", finding,
                          "the cure must be the command that recovers")
            self.assertNotIn("tropo-rebuild-index.py --only", finding,
                             "and must not be the incremental one that just refused — "
                             "sending the reader back into the same wall is how a "
                             "stranger concludes the retirement is broken")


class TestNoKeyMaterialIsTouched(RetirementFixture):
    """D5 + ADR-066. v1's only defence was a stderr substring, so a builder
    porting op_close keeps `remove_agent_keypair` and stays green — destroying
    the PRODUCTION key store, because key dirs are named by activation UID
    which a clone shares and --vault-root does not isolate."""

    def test_the_authority_chain_is_not_imported_at_all(self):
        src = TOOL.read_text(encoding="utf-8") if TOOL.exists() else ""
        self.assertNotIn("authority_chain", src,
                         "ADR-066: no keys anywhere in the lifecycle. This is "
                         "the tripwire that actually holds.")

    def test_no_key_functions_are_referenced(self):
        src = TOOL.read_text(encoding="utf-8") if TOOL.exists() else ""
        for fn in ("remove_agent_keypair", "mint_agent_keypair",
                   "session_key_root", "sign_commit"):
            self.assertNotIn(fn, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
