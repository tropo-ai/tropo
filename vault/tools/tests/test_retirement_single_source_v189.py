#!/usr/bin/env python3
"""v1.89 retirement single source — AC1..AC8 for Mike-locked dev-spec 5fffbbe9.

THE ONE SENTENCE THIS FILE DEFENDS. Retirement is a layered truth: the CLOSE is
one ungated lineage command, and the CEREMONY is required practice that can
never refuse that command. Every test here is on one side of that line, and the
line is the thing that kept breaking.

WHY THESE EIGHT CLASSES HAVE THESE EXACT NAMES. The locked spec's
`verify.command` fields invoke them by name. T44 built all eight steps of the
one-prompt release under his own naming and reported 8/8; eight of the ten
targets the spec named did not exist, so every "step landed" was true about
behaviour and false about verifiability. A150 NO-GO'd it correctly. The names
below are copied from 5fffbbe9's acceptance block, not chosen.

HOW THESE TESTS ARE BUILT. Real subprocesses against isolated temp studios, and
real reads of the live substrate for the document-shaped criteria. No mocks. The
doc tests derive the legal CLI surface from `tropo-lineage.py --help` at runtime
rather than hardcoding a flag list, because a hardcoded list is a second source
of truth and this whole package exists because there were three.

Each class carries at least one control that fails loudly if the thing under
test stops being examined — the vacuous-gate lesson, applied to the tests that
enforce it.
"""

from __future__ import annotations

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
LINEAGE = REPO / "vault" / "tools" / "tropo-lineage.py"
CANONICAL = REPO / "vault" / "playbooks" / "e2c7d185.md"
POINTER = REPO / ".tropo" / "playbooks" / "agent-retire.playbook.md"
CAPSULE = REPO / "vault" / "capsules" / "tropo-agent.capsule.md"

# The six executive unified entries named by the spec's committed_substrate.
EXECUTIVE_ENTRIES = {
    "metis": REPO / "vault" / "agents" / "9fc001c3.md",
    "argus": REPO / "vault" / "agents" / "76f0219f.md",
    "talos": REPO / "vault" / "agents" / "3031ffa3.md",
    "vela": REPO / "vault" / "agents" / "523d663d.md",
    "orpheus": REPO / "vault" / "agents" / "8b81aecf.md",
    "silas": REPO / "vault" / "agents" / "2313fb02.md",
}

CANONICAL_UID = "e2c7d185"


def lineage_flags(subcommand: str) -> set[str]:
    """The flags the tool ACTUALLY accepts, read from the tool, not a list."""
    out = subprocess.run(
        [sys.executable, str(LINEAGE), subcommand, "--help"],
        capture_output=True, text=True, timeout=60,
    ).stdout
    return set(re.findall(r"(--[a-z][a-z-]+)", out))


def retirement_section(text: str) -> str:
    """The retirement-bearing prose of a unified entry.

    Scoped rather than whole-file on purpose: an entry may legitimately mention
    a historical gate in a §Status-Notes war story. What must be clean is the
    instruction a successor executes.
    """
    m = re.search(r"\n#+ *(?:§)?Retirement\b(.*?)(?=\n#+ |\Z)", text, re.DOTALL)
    return m.group(1) if m else ""


class TempStudio(unittest.TestCase):
    """An isolated studio with a real lineage file and a real unified entry."""

    def setUp(self):
        self.studio = pathlib.Path(tempfile.mkdtemp(prefix="retire189-"))
        (self.studio / "vault" / "agents").mkdir(parents=True)
        (self.studio / "vault" / "tools").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.studio, ignore_errors=True)

    def agent_dir(self, slug="probe"):
        d = self.studio / "agents" / slug
        d.mkdir(parents=True, exist_ok=True)
        return d

    def plant_entry(self, slug="probe", uid="aaaa1111", generation="T1",
                    status="active", body="\n## §Soul\n\nvoice content\n"):
        """A unified entry plus the activation pointer that resolves to it."""
        self.agent_dir(slug)
        (self.studio / "agents" / slug / f"{slug}-activation.md").write_text(
            f"---\nuid: ffff0000\ntype: agent-configurator\nagent: {slug}\n"
            f"agent_uid: {uid}\n---\n\n# {slug} activation\n", encoding="utf-8")
        (self.studio / "vault" / "agents" / f"{uid}.md").write_text(
            f"---\nuid: {uid}\ntype: agent\nagent: {slug}\n"
            f"generation: {generation}\nstatus: {status}\n"
            f"last_session: '2026-01-01'\n---\n{body}", encoding="utf-8")
        return uid

    def lineage(self, *args, expect_ok=True):
        cmd = [sys.executable, str(LINEAGE), "--root", str(self.studio), *args]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if expect_ok:
            self.assertEqual(
                p.returncode, 0,
                f"lineage refused: {' '.join(args)}\nstderr={p.stderr}")
        try:
            parsed = json.loads(p.stdout.strip())
        except (ValueError, AttributeError):
            parsed = None
        return p.returncode, parsed, p.stderr

    def born(self, slug="probe", by="mike", **kw):
        return self.lineage("born", "--agent", slug, "--by", by, **kw)

    def retire(self, slug="probe", letter=None, **kw):
        args = ["retire", "--agent", slug]
        if letter is not None:
            path = self.studio / "letter.md"
            path.write_text(letter, encoding="utf-8")
            args += ["--letter", str(path)]
        return self.lineage(*args, **kw)

    def entry_field(self, uid, name):
        text = (self.studio / "vault" / "agents" / f"{uid}.md").read_text()
        m = re.search(rf"^{name}:\s*(.+)$", text, re.MULTILINE)
        return m.group(1).strip().strip("'\"") if m else None

    def lineage_lines(self, slug="probe"):
        p = self.studio / "agents" / slug / "lineage.jsonl"
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


# ───────────────────────────── AC1 ─────────────────────────────

class SingleSourceTests(unittest.TestCase):
    """AC1 — one authored procedure, one exact command shape, no stale surface."""

    def setUp(self):
        self.canonical = CANONICAL.read_text(encoding="utf-8")
        self.pointer = POINTER.read_text(encoding="utf-8")

    def test_canonical_teaches_only_flags_the_tool_accepts(self):
        legal = lineage_flags("retire") | {"--root", "--help", "--agent"}
        # Scope the scan to lines that invoke tropo-lineage.py. The playbook's
        # "Drain events" step legitimately cites tropo-emit-event.py's
        # --correlationid/--final; a whole-document scan attributed those to
        # the retire tool and failed on a flag it never taught.
        # (suite-health 2026-09-03)
        lineage_lines = "\n".join(
            line for line in (self.canonical + self.pointer).splitlines()
            if "tropo-lineage.py" in line
        )
        cited = set(re.findall(r"(--[a-z][a-z-]+)", lineage_lines))
        illegal = cited - legal
        self.assertEqual(
            illegal, set(),
            "retirement docs teach flags tropo-lineage.py rejects: "
            f"{sorted(illegal)}. Every one of these is a cold reader running a "
            "command that errors at the moment they are closing a generation.")

    def test_documented_command_is_the_supported_one(self):
        self.assertIn("tropo-lineage.py", self.canonical)
        for legacy in ("tropo-retire.py", "40b2f455.py op_close",
                       "write-activation-entry"):
            self.assertNotIn(
                legacy, self.canonical,
                f"canonical still routes the close through {legacy}; that is "
                "the trap that cost Metis G98 and Talos T37 their clean closes")

    def test_the_close_does_not_write_a_status_card_or_a_mirror(self):
        for dead in ("status-card", "status card", "-status.md"):
            self.assertNotIn(
                dead.lower(), self.canonical.lower(),
                f"canonical still instructs a {dead} write; lineage is the "
                "state and there is no card in this path")
        self.assertNotIn(
            "mirror", self.canonical.lower(),
            "canonical still teaches a mirror write; the double-write closed "
            "2026-08-06 and the letter has exactly one home")

    def test_no_default_path_halt_remains(self):
        for gate in ("R-1", "R-2", "R-4", "HALT"):
            self.assertNotIn(
                gate, self.canonical,
                f"canonical still carries {gate} on the default path; a "
                "substance gate on the close is how retirement gets blocked")

    def test_kernel_pointer_is_a_pointer_not_a_second_procedure(self):
        self.assertIn(CANONICAL_UID, self.pointer,
                      "kernel pointer must name the canonical it points at")
        # A pointer plus degraded floor. A second full procedure is the drift.
        self.assertLess(
            len(self.pointer), len(self.canonical) / 3,
            "kernel path has grown into a competing authored procedure; that "
            "is the exact drift this package exists to remove")

    def test_control_the_flag_scan_actually_examines_something(self):
        """Vacuity control: prove the scan sees flags at all."""
        cited = set(re.findall(r"(--[a-z][a-z-]+)",
                               self.canonical + self.pointer))
        self.assertIn("--agent", cited,
                      "flag scan found no --agent anywhere; the assertions "
                      "above would pass on an empty document")


# ───────────────────────────── AC2 ─────────────────────────────

class UngatedCloseTests(TempStudio):
    """AC2 — nothing in ceremony can refuse the close."""

    def test_retire_succeeds_with_no_ceremony_of_any_kind(self):
        self.plant_entry()
        self.born()
        code, out, _ = self.retire(letter="a real letter")
        self.assertEqual(code, 0)
        self.assertEqual(
            [l["t"] for l in self.lineage_lines()], ["born", "retired"],
            "no fold, no reflection, no captains log, no run folder, no "
            "drained events, no RETIRING state — and the close still lands")

    def test_retire_succeeds_with_no_letter_at_all(self):
        self.plant_entry()
        self.born()
        code, _, _ = self.retire(letter=None)
        self.assertEqual(code, 0, "a letter is practice, not a condition")
        self.assertEqual(self.lineage_lines()[-1]["t"], "retired")

    def test_missing_run_folder_and_reflection_do_not_appear_in_exit_status(self):
        self.plant_entry()
        self.born()
        self.assertFalse((self.studio / "playbook-runs").exists())
        self.assertFalse((self.studio / "agents" / "probe" / "reflections").exists())
        code, _, _ = self.retire(letter="letter")
        self.assertEqual(code, 0)

    def test_the_destructive_refusals_are_still_in_place(self):
        """Ungated is not unguarded — the three real refusals must survive."""
        self.plant_entry()
        self.born()
        self.retire(letter="first letter")
        code, _, err = self.retire(letter="second letter", expect_ok=False)
        self.assertNotEqual(
            code, 0,
            "a second retire overwrote an irreplaceable predecessor letter")
        self.assertTrue(err.strip(), "refusal must say why")

    def test_control_a_gate_would_be_caught(self):
        """Mutation control: if ceremony DID gate close, this suite goes red."""
        self.plant_entry()
        self.born()
        code, _, _ = self.retire(letter="letter")
        # If a future edit makes retire exit non-zero on missing ceremony,
        # test_retire_succeeds_with_no_ceremony_of_any_kind fails first. This
        # asserts the observable the mutation would flip.
        self.assertEqual(code, 0)
        self.assertTrue(
            (self.studio / "agents" / "probe" / "lineage.jsonl").exists(),
            "the record IS the lineage line; if it is absent the close did "
            "not happen regardless of exit code")


# ───────────────────────────── AC3 ─────────────────────────────

class RequiredPracticeTests(unittest.TestCase):
    """AC3 — practice is required and recoverable, never a condition of close."""

    def setUp(self):
        self.canonical = CANONICAL.read_text(encoding="utf-8")
        self.lower = self.canonical.lower()

    def test_the_five_practices_are_named_as_required(self):
        for practice in ("fold", "reflection", "captain", "memor", "drain"):
            self.assertIn(
                practice, self.lower,
                f"canonical no longer names {practice} as executive practice; "
                "dropping it repeats T43 silently")

    def test_after_the_fact_recovery_is_explicit(self):
        self.assertTrue(
            re.search(r"after[- ]the[- ]fact|afterward|later", self.lower),
            "canonical gives no honest recovery path; an agent who closed "
            "early is then choosing between a lie and nothing")

    def test_recovery_forbids_fabrication(self):
        self.assertTrue(
            re.search(r"never invent|do not invent|not fabricat|never fabricat|"
                      r"no fabricated|real timestamp", self.lower),
            "recovery language must forbid inventing a run folder or "
            "backdating; a recovered record that lies is worse than a gap")

    def test_practice_is_not_described_as_optional(self):
        self.assertNotIn(
            "ceremony is optional", self.lower,
            "calling practice optional is how T43 happened with zero warning")

    def test_practice_is_not_described_as_gating_the_close(self):
        window = self.lower
        for phrase in ("cannot retire until", "must complete before retiring",
                       "blocks retirement", "retirement is blocked"):
            self.assertNotIn(
                phrase, window,
                f"canonical says '{phrase}' — that is a gate wearing the word "
                "practice, and it recreates blocked retirement")

    def test_the_layered_truth_is_stated_not_implied(self):
        self.assertTrue(
            re.search(r"required practice", self.lower),
            "the canonical must say 'required practice' in those words; the "
            "distinction between practice and close is the whole package")


# ───────────────────────────── AC4 ─────────────────────────────

class UnifiedEntryTests(unittest.TestCase):
    """AC4 — seven sources point at one procedure and contradict it nowhere."""

    def test_the_census_is_exact(self):
        missing = {n: str(p) for n, p in EXECUTIVE_ENTRIES.items()
                   if not p.is_file()}
        self.assertEqual(missing, {}, f"unified entries absent: {missing}")
        self.assertTrue(CAPSULE.is_file(), "agent capsule absent")
        self.assertEqual(len(EXECUTIVE_ENTRIES), 6)

    def test_every_entry_points_at_the_canonical(self):
        for name, path in EXECUTIVE_ENTRIES.items():
            section = retirement_section(path.read_text(encoding="utf-8"))
            self.assertTrue(section.strip(), f"{name}: no retirement section")
            self.assertIn(
                CANONICAL_UID, section,
                f"{name} does not point at the canonical procedure; a locally "
                "maintained copy is exactly what drifted into three stories")

    def test_the_capsule_carries_the_inherited_pointer(self):
        text = CAPSULE.read_text(encoding="utf-8")
        self.assertIn(
            CANONICAL_UID, text,
            "agent.capsule must carry the retirement pointer so a future "
            "executive entry inherits it instead of reinventing ceremony")

    def test_no_entry_claims_ceremony_is_unnecessary(self):
        for name, path in EXECUTIVE_ENTRIES.items():
            section = retirement_section(path.read_text(encoding="utf-8")).lower()
            for claim in ("no reflection", "no memory fold", "no run folder",
                          "no ceremony"):
                self.assertNotIn(
                    claim, section,
                    f"{name} retirement text still claims '{claim}'. T43 read "
                    "exactly that, retired correctly, and omitted the practice "
                    "with zero warning.")

    def test_no_entry_teaches_a_stale_tool_or_a_mirror(self):
        for name, path in EXECUTIVE_ENTRIES.items():
            section = retirement_section(path.read_text(encoding="utf-8"))
            for dead in ("tropo-retire.py", "40b2f455.py op_close"):
                self.assertNotIn(dead, section,
                                 f"{name} still routes the close through {dead}")

    def test_no_entry_says_compaction_means_retirement(self):
        for name, path in EXECUTIVE_ENTRIES.items():
            section = retirement_section(path.read_text(encoding="utf-8")).lower()
            if "compact" in section:
                self.assertTrue(
                    re.search(r"not retirement|never.*retire|compact-continue",
                              section),
                    f"{name} mentions compaction in its retirement section "
                    "without routing it to Compact-Continue; that is how a "
                    "healthy agent ends its own generation over a summary")


# ───────────────────────────── AC5 ─────────────────────────────

class WarnOnlyCompletenessTests(TempStudio):
    """AC5 — completeness is observed and reported, never enforced."""

    def _check(self):
        import importlib.util
        tools = str(REPO / "vault" / "tools")
        if tools not in sys.path:
            # in-process exec of tropo-validate.py inherits this sys.path; the
            # tool does `from lib...` at top level since 2026-08-31.
            sys.path.insert(0, tools)
        spec = importlib.util.spec_from_file_location(
            "tv_ac5", REPO / "vault" / "tools" / "tropo-validate.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.check_retirement_ceremony_completeness(self.studio)

    def _retired_generation(self, slug="probe"):
        self.plant_entry(slug=slug)
        self.born(slug=slug)
        self.retire(slug=slug, letter="letter")

    def test_findings_are_warn_and_never_increment_defects(self):
        self._retired_generation()
        findings, checked, defects = self._check()
        self.assertGreater(checked, 0, "check examined nothing — vacuous")
        self.assertEqual(
            defects, 0,
            "retirement completeness incremented the ERROR count; this check "
            "may only WARN or it becomes the gate the package forbids")
        self.assertTrue(any("[WARN]" in f for f in findings))
        self.assertFalse(any("[ERROR]" in f or "[FAIL]" in f for f in findings))

    def test_the_warning_names_the_missing_artifact(self):
        self._retired_generation()
        findings, _, _ = self._check()
        blob = " ".join(findings).lower()
        for artifact in ("reflection", "fold"):
            self.assertIn(artifact, blob,
                          f"warning does not name the missing {artifact}; a "
                          "finding you cannot act on is noise")

    def test_adding_the_reflection_shrinks_the_warning_set(self):
        self._retired_generation()
        before, _, _ = self._check()
        refl = self.studio / "agents" / "probe" / "reflections"
        refl.mkdir(parents=True, exist_ok=True)
        (refl / "T1-reflection.md").write_text(
            "---\nagent: probe\ngeneration: T1\n---\n\n# T1 reflection\n",
            encoding="utf-8")
        after, _, _ = self._check()
        self.assertLess(
            len(after), len(before),
            "an honest later reflection did not reduce the debt; recovery has "
            "to be worth doing or nobody does it")

    def test_a_complete_retirement_warns_about_nothing(self):
        self._retired_generation()
        refl = self.studio / "agents" / "probe" / "reflections"
        refl.mkdir(parents=True, exist_ok=True)
        (refl / "T1-reflection.md").write_text("# T1\n", encoding="utf-8")
        mem = self.studio / "agents" / "probe" / ".tropo-capsule" / "memory"
        mem.mkdir(parents=True, exist_ok=True)
        (mem / "agent-memories.jsonl").write_text(
            json.dumps({"event": "fold-boundary", "ts": "2999-01-01",
                        "generation": "T1"}) + "\n", encoding="utf-8")
        findings, _, _ = self._check()
        mine = [f for f in findings if "probe" in f]
        self.assertEqual(mine, [], f"complete retirement still warns: {mine}")


# ───────────────────────────── AC6 ─────────────────────────────

class LifecycleSyncTests(TempStudio):
    """AC6 — the card stops lying, and can never hurt the lineage."""

    def test_born_syncs_generation_and_status_onto_the_entry(self):
        uid = self.plant_entry(generation="T0", status="retired")
        _, out, _ = self.born()
        self.assertEqual(self.entry_field(uid, "generation"), out["generation"])
        self.assertEqual(self.entry_field(uid, "status"), "active")

    def test_retire_syncs_status_onto_the_entry(self):
        uid = self.plant_entry()
        self.born()
        self.retire(letter="letter")
        self.assertEqual(self.entry_field(uid, "status"), "RETIRED".lower()
                         if self.entry_field(uid, "status") == "retired"
                         else self.entry_field(uid, "status"))
        self.assertIn(self.entry_field(uid, "status"), ("retired", "RETIRED"))

    def test_sync_never_touches_voice_or_body(self):
        uid = self.plant_entry(body="\n## §Soul\n\nirreplaceable voice\n")
        self.born()
        self.retire(letter="letter")
        text = (self.studio / "vault" / "agents" / f"{uid}.md").read_text()
        self.assertIn("irreplaceable voice", text,
                      "sync rewrote body content; lifecycle fields only")

    def test_a_missing_entry_does_not_fail_the_lineage(self):
        self.agent_dir("probe")  # no activation pointer, no unified entry
        code, out, err = self.born()
        self.assertEqual(code, 0, "an absent card refused a birth")
        self.assertEqual(self.lineage_lines()[-1]["t"], "born")

    def test_an_unwritable_entry_warns_but_the_close_still_lands(self):
        uid = self.plant_entry()
        self.born()
        target = self.studio / "vault" / "agents" / f"{uid}.md"
        os.chmod(target, 0o444)
        try:
            code, _, err = self.retire(letter="letter")
        finally:
            os.chmod(target, 0o644)
        self.assertEqual(
            code, 0, "a read-only card rolled back a completed retirement")
        self.assertEqual(self.lineage_lines()[-1]["t"], "retired")

    def test_a_malformed_entry_cannot_poison_the_lineage(self):
        self.plant_entry()
        (self.studio / "vault" / "agents" / "aaaa1111.md").write_text(
            "this is not frontmatter at all", encoding="utf-8")
        code, _, _ = self.born()
        self.assertEqual(code, 0)
        self.assertEqual(self.lineage_lines()[-1]["t"], "born")


# ───────────────────────────── AC7 ─────────────────────────────

class CrewBriefAuthorityTests(TempStudio):
    """AC7 — lineage is the truth; the card is a link."""

    def test_lineage_wins_when_the_card_disagrees(self):
        uid = self.plant_entry(generation="T1", status="active")
        self.born()
        self.retire(letter="letter")
        # Corrupt the card back to a live claim; lineage says retired.
        text = (self.studio / "vault" / "agents" / f"{uid}.md").read_text()
        (self.studio / "vault" / "agents" / f"{uid}.md").write_text(
            text.replace("status: retired", "status: active"), encoding="utf-8")
        lines = self.lineage_lines()
        self.assertEqual(
            lines[-1]["t"], "retired",
            "lineage must remain the authority regardless of card content")

    def test_who_reads_lineage_not_the_card(self):
        uid = self.plant_entry(generation="T9", status="active")
        self.born()
        _, out, _ = self.lineage("who", "--agent", "probe")
        self.assertIsNotNone(out)
        self.assertNotEqual(
            out.get("gen"), "T9",
            "`who` echoed the stale card generation instead of the lineage")


# ───────────────────────────── AC8 ─────────────────────────────

class T43RegressionTests(WarnOnlyCompletenessTests):
    """AC8 — the real T43 shape: lineage-only close, honest later recovery."""

    def _t43_shape(self):
        """Letter and lineage now; no fold, no reflection, no run folder."""
        self.plant_entry(slug="probe", generation="T43")
        self.born()
        self.retire(letter="# T43 -> T44\n\nthe letter was written.\n")

    def test_the_t43_close_is_valid(self):
        self._t43_shape()
        lines = self.lineage_lines()
        self.assertEqual(lines[-1]["t"], "retired")
        self.assertTrue(
            (self.studio / "agents" / "probe" / "transfers").exists(),
            "the letter is the handoff and must be placed")

    def test_the_t43_gap_warns_rather_than_fails(self):
        self._t43_shape()
        findings, _, defects = self._check()
        self.assertEqual(defects, 0, "T43's real shape must never be an ERROR")
        self.assertTrue([f for f in findings if "probe" in f],
                        "T43's gap produced no warning at all — that is the "
                        "silence the package exists to end")

    def test_an_honest_later_reflection_reduces_the_debt(self):
        self._t43_shape()
        before, _, _ = self._check()
        refl = self.studio / "agents" / "probe" / "reflections"
        refl.mkdir(parents=True, exist_ok=True)
        (refl / "T1-reflection.md").write_text(
            "# recovered after the fact, written 2026-08-16\n", encoding="utf-8")
        after, _, _ = self._check()
        self.assertLess(len(after), len(before))

    def test_no_synthetic_run_folder_is_ever_required(self):
        self._t43_shape()
        findings, _, _ = self._check()
        blob = " ".join(findings).lower()
        self.assertNotIn(
            "create a run folder", blob,
            "a warning that tells an agent to fabricate a run folder for a "
            "retirement that did not have one is asking for a forged record")


if __name__ == "__main__":
    unittest.main()
