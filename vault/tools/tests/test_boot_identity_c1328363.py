#!/usr/bin/env python3
"""The two v1.95 external-test defects, and the negative controls for both.

f015b61d2291 AC1 — a three-file end-user agent never reaches "soul loads
first", with the mandated negative control: *an agent with none of the three
files refuses at that step BY NAME*.

f01579bf3aee — the first-boot orientation tour has never fired for a human,
because the one surface that reads its flag is the one agent who can skip
reading it unobserved.

EVERY test here is written so its verdict FLIPS when the mechanism under it is
removed. That is this studio's own rule, from the report that produced these
records: *"A passing check is evidence only when the named behavior actually
ran and could change verdict."* Each class names, in its docstring, exactly
what to delete to turn it red.

Fixtures are built from the REAL shipped templates
(`vault/templates/tropo-executive-{activation,charter}.template.md`) exactly as
`vault/skills/tropo-create-executive-agent.md` steps 5 and 7 direct -- not from
a hand-written stand-in that happens to carry the keys the resolver wants. If
the templates change shape, these tests must break; a fixture that cannot
notice the templates drifting is the same blind check one level down.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import boot_identity as bi  # noqa: E402
from lib import po_first_boot as pfb  # noqa: E402
from lib import run_journal as rj  # noqa: E402

CLI = TOOLS / "tropo-boot-identity.py"
ACTIVATION_TEMPLATE = ROOT / "vault" / "templates" / "tropo-executive-activation.template.md"
CHARTER_TEMPLATE = ROOT / "vault" / "templates" / "tropo-executive-charter.template.md"
PLAYBOOK = ROOT / "vault" / "playbooks" / "99341618.md"
KERNEL_POINTER = ROOT / ".tropo" / "playbooks" / "agent-activation.playbook.md"
CONCIERGE = ROOT / ".tropo" / "concierge" / "activate.md"

# The founder's own words for the fixture agent, so a "resolved" verdict can be
# checked against CONTENT and not merely against a status string.
SAGE_ROLE = "Research Lead"
SAGE_VALUE = "Read the primary source before repeating the summary."
SAGE_VOICE = "Plain, unhurried, allergic to hedging."


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
    )


def make_studio(tmp: Path) -> Path:
    root = tmp / "studio"
    (root / "agents").mkdir(parents=True)
    (root / "vault" / "agents").mkdir(parents=True)
    (root / "vault" / "files").mkdir(parents=True)
    (root / ".tropo" / "flags").mkdir(parents=True)
    return root


def _fill(text: str, name: str, *, fill_soul: bool) -> str:
    out = (
        text.replace("[agent-name]", name)
        .replace("[Agent Name]", name.capitalize())
        .replace("[Founder Name]", "Mike")
        .replace("[founder-name]", "Mike")
        .replace("[YYYY-MM-DD]", "2026-09-07")
        .replace("[uid as minted by tropo-mint-id.py]", "aaaa1111")
        .replace("[One-line role description]", "Runs the reading and reports what it found.")
    )
    if fill_soul:
        out = (
            out.replace(
                "[Named role — e.g., Chief of Staff, Strategist, Architect]", SAGE_ROLE
            )
            .replace("[Core value 1]", SAGE_VALUE)
            .replace("[Core value 2]", "Say what is not known.")
            .replace("[Core value 3]", "One finding beats ten citations.")
            .replace(
                "[Communication style — e.g., precise and direct, warm and strategic]",
                SAGE_VOICE,
            )
            .replace(
                "[How this agent handles ambiguity — e.g., principle-driven, "
                "consensus-seeking, action-biased]",
                "Evidence-first; names the gap rather than filling it.",
            )
            .replace(
                "[Brief context about this agent's founding purpose.]",
                "Founded to read the sources nobody has time for.",
            )
            # The `## Identity` BODY, not just the `soul:` frontmatter. The
            # end-to-end run caught this: filling only the frontmatter left
            # "You are **Sage**, [role] for [team/organization name]" and the
            # resolver reported a clean `resolved`. A fixture that fills only
            # the half the resolver reads first cannot notice that.
            .replace("[role]", "research lead")
            .replace("[team/organization name]", "Mike's studio")
            .replace(
                "[2-3 sentences describing who this agent is, what they care "
                "about, and how they approach their work. This is the seed of "
                "soul — it grows through lived experience.]",
                "Sage reads the sources nobody has time for and reports what is "
                "actually in them. Sage would rather say 'I do not know' than "
                "produce a confident summary of something unread.",
            )
        )
    return out


def create_three_file_agent(root: Path, name: str, *, fill_soul: bool = True) -> Path:
    """Exactly what `tropo-create-executive-agent.md` steps 5 and 7 produce:
    an activation pointer declaring `charter_file:`, and a charter. No
    `agent_uid:`, no Tier-3 extension, no unified entry -- the shape a customer
    actually gets, and the shape Shape A and Shape B were both blind to."""
    folder = root / "agents" / name
    folder.mkdir(parents=True, exist_ok=True)
    activation = folder / "{}-activation.md".format(name)
    activation.write_text(
        _fill(ACTIVATION_TEMPLATE.read_text(encoding="utf-8"), name, fill_soul=fill_soul),
        encoding="utf-8",
    )
    (folder / "{}-charter.md".format(name)).write_text(
        _fill(CHARTER_TEMPLATE.read_text(encoding="utf-8"), name, fill_soul=fill_soul),
        encoding="utf-8",
    )
    return activation


def create_bare_agent(root: Path, name: str) -> Path:
    """An activation pointer that declares NONE of the four shapes. This is the
    negative control's subject: not a broken file, a well-formed pointer with
    no identity behind it."""
    folder = root / "agents" / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "{}-activation.md".format(name)
    path.write_text(
        "---\n"
        'uid: "bbbb2222"\n'
        'agent_name: "{}"\n'
        "type: activation\n"
        'owner: "Mike"\n'
        'boot_playbook: ".tropo/playbooks/agent-activation.playbook.md"\n'
        "---\n\n# {} — Activation\n".format(name, name),
        encoding="utf-8",
    )
    return path


def write_journal(path: Path, rows) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    return path


# ---------------------------------------------------------------------------


class ShapeCResolvesEndUserAgents(unittest.TestCase):
    """DEFECT 1. Reproduces the measured failure: an agent built strictly from
    the shipped templates, whose Step 2.0 was never entered because no
    resolution shape matched its files.

    MUTATION (verdict flips): delete the `charter_file` branch from
    `lib/boot_identity.resolve_soul` -- or just the line
    `charter_file = fm.get("charter_file")` -- and every test in this class
    fails, because Shape A, D and B all legitimately miss for this agent.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_studio(Path(self._tmp.name))
        create_three_file_agent(self.root, "sage")

    def tearDown(self):
        self._tmp.cleanup()

    def test_shape_c_resolves_for_a_three_file_agent(self):
        res = bi.resolve_soul(self.root, "sage")
        self.assertTrue(
            res.loaded,
            "Step 2.0 did not resolve for a three-file agent. tried={}".format(res.tried),
        )
        self.assertEqual("C", res.shape)
        self.assertEqual("agents/sage/sage-charter.md", res.source)
        self.assertEqual(
            bi.STATUS_RESOLVED,
            res.status,
            "a fully-filled charter must be a clean resolve, not a warn: {}".format(
                res.placeholders
            ),
        )

    def test_a_half_filled_charter_warns_rather_than_reporting_clean(self):
        """The case the end-to-end run caught. `soul:` frontmatter filled, the
        `## Identity` body still reading "You are **Sage**, [role] for
        [team/organization name]" -- the resolver called that `resolved`. A
        soul-loaded verdict over a paragraph that still says [role] is a false
        green, which is the species of defect this whole change exists to end."""
        folder = self.root / "agents" / "halfway"
        folder.mkdir(parents=True)
        (folder / "halfway-activation.md").write_text(
            _fill(ACTIVATION_TEMPLATE.read_text(encoding="utf-8"), "halfway", fill_soul=True),
            encoding="utf-8",
        )
        charter = CHARTER_TEMPLATE.read_text(encoding="utf-8")
        # Fill ONLY the frontmatter soul block; leave the body template alone.
        head, sep, body = charter.partition("\n## Identity")
        (folder / "halfway-charter.md").write_text(
            _fill(head, "halfway", fill_soul=True) + sep + body, encoding="utf-8"
        )
        res = bi.resolve_soul(self.root, "halfway")
        self.assertTrue(res.loaded)
        self.assertEqual(bi.STATUS_PLACEHOLDER, res.status)
        self.assertIn("[role]", res.placeholders)

    def test_the_other_shapes_genuinely_miss(self):
        """Guards against a false green: if a future edit made Shape A or B
        resolve here by accident, this class would pass without Shape C ever
        being exercised."""
        res = bi.resolve_soul(self.root, "sage")
        reasons = dict(res.tried)
        self.assertIn("A", reasons)
        self.assertIn("no agent_uid", reasons["A"])

    def test_resolved_payload_carries_the_founders_own_words(self):
        """A status string is not a soul. The bytes the founder dictated have
        to be in the text an agent reads."""
        res = bi.resolve_soul(self.root, "sage")
        self.assertIn(SAGE_ROLE, res.text)
        self.assertIn(SAGE_VALUE, res.text)
        self.assertIn(SAGE_VOICE, res.text)

    def test_cli_prints_the_soul_and_exits_zero(self):
        proc = run_cli(
            "--vault-root", str(self.root), "soul", "--agent", "sage", "--no-journal"
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("soul: LOADED — shape C", proc.stdout)
        self.assertIn(SAGE_VALUE, proc.stdout)

    def test_unfilled_template_warns_and_still_loads(self):
        """WARN-SAFE. A charter still full of `[Core value 1]` is a warning
        with the agent's own name on it, never a stop -- the harm is a generic
        `voice:` string, which is a text edit away from fixed."""
        create_three_file_agent(self.root, "husk", fill_soul=False)
        res = bi.resolve_soul(self.root, "husk")
        self.assertEqual(bi.STATUS_PLACEHOLDER, res.status)
        self.assertTrue(res.loaded)
        self.assertTrue(res.placeholders)
        proc = run_cli(
            "--vault-root", str(self.root), "soul", "--agent", "husk", "--no-journal"
        )
        self.assertEqual(0, proc.returncode)
        self.assertIn("UNFILLED TEMPLATE VALUES", proc.stdout)


class NegativeControlNamedRefusal(unittest.TestCase):
    """MANDATORY NEGATIVE CONTROL (f015b61d2291 AC1). An agent with none of the
    shapes must be refused at the identity step BY NAME, not silently skipped
    -- and, because warn-safe outranks everything here, must still boot.

    "Refuses" is refusal to REPORT ITSELF SATISFIED, in a fixed greppable
    string carrying the agent's name and every shape it tried. It is not
    refusal to proceed: no branch in this tool can stop a founder.

    MUTATION (verdict flips): make `resolve_soul` return
    `Resolution(agent=slug, status=bi.STATUS_RESOLVED)` on the fall-through
    instead of `STATUS_NOT_RESOLVED`, or drop the `⛔ SOUL NOT LOADED` banner
    from `_print_soul_human` -- the silent-skip behaviour this record exists to
    end -- and these fail.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_studio(Path(self._tmp.name))
        create_bare_agent(self.root, "ghost")

    def tearDown(self):
        self._tmp.cleanup()

    def test_unresolvable_agent_is_not_reported_as_loaded(self):
        res = bi.resolve_soul(self.root, "ghost")
        self.assertEqual(bi.STATUS_NOT_RESOLVED, res.status)
        self.assertFalse(res.loaded)

    def test_refusal_names_the_agent_and_every_shape_it_tried(self):
        proc = run_cli(
            "--vault-root", str(self.root), "soul", "--agent", "ghost", "--no-journal"
        )
        self.assertIn("⛔ SOUL NOT LOADED", proc.stdout)
        self.assertIn("`ghost`", proc.stdout)
        for shape in ("A:", "B:", "C:", "D:"):
            self.assertIn(shape, proc.stdout, "shape {} unnamed in the refusal".format(shape))
        self.assertIn("agents/ghost/ghost-activation.md", proc.stdout)

    def test_refusal_is_warn_safe_and_exits_zero(self):
        """The one rule that outranks cleverness: nothing built here may refuse
        the founder. A named gap proceeds and records."""
        proc = run_cli(
            "--vault-root", str(self.root), "soul", "--agent", "ghost", "--no-journal"
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("CONTINUE the boot", proc.stdout)

    def test_missing_agent_folder_is_named_not_crashed(self):
        proc = run_cli(
            "--vault-root", str(self.root), "soul", "--agent", "nobody", "--no-journal"
        )
        self.assertEqual(0, proc.returncode)
        self.assertIn("⛔ SOUL NOT LOADED", proc.stdout)
        self.assertIn("`nobody`", proc.stdout)

    def test_uncommissioned_placeholder_gets_no_alarm(self):
        """A red marker that fires on a healthy declared state is how a founder
        learns to stop reading red markers. `nestor` and `tiphys` ship this way
        on the founder's own install."""
        folder = self.root / "agents" / "sleeper"
        folder.mkdir(parents=True)
        (folder / "sleeper-activate.md").write_text(
            "---\n"
            "agent_class: executive\n"
            "placeholder: true\n"
            'current_agent_status: "not-commissioned"\n'
            "---\n\n# Sleeper\n",
            encoding="utf-8",
        )
        proc = run_cli(
            "--vault-root", str(self.root), "soul", "--agent", "sleeper", "--no-journal"
        )
        self.assertEqual(0, proc.returncode)
        self.assertNotIn("⛔", proc.stdout)
        self.assertIn("uncommissioned placeholder", proc.stdout)


class RunJournalCanSayTheStepDidNotHappen(unittest.TestCase):
    """The vocabulary the run journal did not have. Sage's journal fired the
    Group 2 milestone `Context Loaded` with Step 2.0 never entered, and because
    milestones are per-GROUP there was no way to write down that a step was
    skipped. This is the reader that says it -- and the reader is not the agent
    whose boot is in question.

    MUTATION (verdict flips): empty `lib/run_journal.STEP_ACCOUNTABILITY` (set
    it to `{}`) and `test_milestone_over_unaccounted_step_is_reported` fails --
    the audit goes back to reporting a clean boot over the exact hole that
    shipped.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_studio(Path(self._tmp.name))
        self.journal = self.root / "playbook-runs" / "agent-activation-sage-1-2026-09-07" / "run.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def test_milestone_over_unaccounted_step_is_reported(self):
        write_journal(
            self.journal,
            [
                {"event": "run_created", "agent": "sage"},
                {"event": "milestone_fired", "milestone": "Boot Config Chain Complete"},
                {"event": "milestone_fired", "milestone": "Context Loaded"},
            ],
        )
        result = rj.audit(self.journal)
        self.assertIn("2.0", result.unaccounted)
        self.assertFalse(result.clean)
        self.assertTrue(any("Context Loaded" in f for f in result.findings))
        self.assertTrue(any("Step 2.0" in f for f in result.findings))

    def test_a_recorded_disposition_makes_the_step_accounted(self):
        write_journal(self.journal, [{"event": "run_created", "agent": "sage"}])
        problem = rj.append_step_disposition(
            self.journal, "2.0", "resolved", {"shape": "C"}, "2026-09-07T00:00:00Z"
        )
        self.assertIsNone(problem)
        with self.journal.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "milestone_fired", "milestone": "Context Loaded"}) + "\n")
        result = rj.audit(self.journal)
        self.assertEqual([], result.unaccounted)
        self.assertTrue(result.clean)

    def test_an_unresolved_soul_is_still_accounted_and_still_visible(self):
        """The point is not that the step succeeded -- it is that the record can
        distinguish 'ran and failed' from 'left no evidence'."""
        write_journal(self.journal, [{"event": "run_created", "agent": "ghost"}])
        rj.append_step_disposition(
            self.journal, "2.0", bi.STATUS_NOT_RESOLVED, {"shape": None}, "t"
        )
        with self.journal.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "milestone_fired", "milestone": "Context Loaded"}) + "\n")
        result = rj.audit(self.journal)
        self.assertTrue(result.clean)
        self.assertTrue(any("not_resolved" in a for a in result.accounted))

    def test_cli_writes_the_disposition_during_a_real_resolve(self):
        create_three_file_agent(self.root, "sage")
        write_journal(self.journal, [{"event": "run_created", "agent": "sage"}])
        proc = run_cli(
            "--vault-root", str(self.root),
            "soul", "--agent", "sage", "--terse",
            "--run-journal", str(self.journal),
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        rows = rj.read_rows(self.journal)
        dispositions = [r for r in rows if r.get("event") == rj.EVENT]
        self.assertEqual(1, len(dispositions))
        self.assertEqual("2.0", dispositions[0]["step"])
        self.assertEqual("C", dispositions[0]["detail"]["shape"])

    def test_audit_exits_zero_even_when_it_finds_the_hole(self):
        write_journal(
            self.journal, [{"event": "milestone_fired", "milestone": "Context Loaded"}]
        )
        proc = run_cli(
            "--vault-root", str(self.root), "audit", "--run-journal", str(self.journal)
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("UNACCOUNTED", proc.stdout)

    def test_an_unwritable_journal_is_a_note_not_a_stop(self):
        create_three_file_agent(self.root, "sage")
        proc = run_cli(
            "--vault-root", str(self.root),
            "soul", "--agent", "sage", "--terse",
            "--run-journal", str(self.root / "no" / "such" / "dir" / "x" / "run.jsonl"),
        )
        self.assertEqual(0, proc.returncode)
        self.assertIn("soul: LOADED", proc.stdout)


class AgentDirectOrientationOffer(unittest.TestCase):
    """DEFECT 2. The walk's trigger reads one fact correctly; the only surface
    that read it was the concierge, and on the founder's own install the
    concierge skipped the step and said so only in her retrospective.

    This adds a SECOND reader of the SAME fact on a different agent's boot, so
    Po's skip becomes visible to somebody who is not Po.

    MUTATION (verdict flips): make `should_fold_agent_offer` return `False`
    unconditionally and `test_offer_fires_when_the_walk_has_never_been_offered`
    plus `test_po_skipping_step_8_becomes_visible_to_a_later_reader` fail.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_studio(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_offer_fires_when_the_walk_has_never_been_offered(self):
        self.assertTrue(pfb.should_fold_agent_offer(self.root))
        proc = run_cli("--vault-root", str(self.root), "orientation")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("orientation tour", proc.stdout)

    def test_it_reads_the_same_fact_the_concierge_reads(self):
        """Trigger and walk could never disagree; nor may this third surface."""
        pfb.mark_walk_offered(self.root)
        self.assertFalse(pfb.should_fire_automatic_walk(self.root))
        self.assertFalse(pfb.should_fold_agent_offer(self.root))
        proc = run_cli("--vault-root", str(self.root), "orientation")
        self.assertEqual(0, proc.returncode)
        self.assertEqual("", proc.stdout.strip(), "a taken tour must be silent")

    def test_it_fires_at_most_once_per_install(self):
        """The nag control. This studio's founder nearly ended the project over
        machinery that repeats itself at him. Declining is not required to
        silence it -- surfacing once is."""
        first = run_cli("--vault-root", str(self.root), "orientation", "--record")
        self.assertIn("orientation tour", first.stdout)
        for _ in range(3):
            again = run_cli("--vault-root", str(self.root), "orientation", "--record")
            self.assertEqual(0, again.returncode)
            self.assertEqual("", again.stdout.strip(), "the offer repeated — that is a nag")

    def test_the_record_never_claims_a_human_saw_the_offer(self):
        """F1, found by the non-author verifier 2026-09-07: the first build wrote
        the flag on its own stdout and then reported the offer "surfaced ... in a
        startup signal" -- a claim about a thing it cannot observe, inside the
        change written to end self-reports of compliance.

        MUTATION CLAUSE: restore either the summary wording in po_first_boot or
        the CLI's "[recorded] ... surfaced once" line and this test goes red on
        the claim, not on a count."""
        run_cli("--vault-root", str(self.root), "orientation", "--record")
        state = pfb.orientation_state(self.root)

        # what the tool knows
        self.assertEqual(1, state["agent_offer_handoffs"])
        self.assertFalse(state["walk_offered"])

        # what it must NOT assert: that a human read it
        summary = state["summary"].lower()
        self.assertIn("handed", summary)
        self.assertNotIn(
            "surfaced the one-line tour offer in a startup signal", summary,
            "the record claims delivery it cannot observe (F1)")

        # and the audit, read by somebody who was not the agent, must say so too
        proc = run_cli("--vault-root", str(self.root), "audit")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("handed", proc.stdout.lower())

    def test_a_handoff_is_ledgered_not_merely_marked(self):
        """The flag carries one ISO stamp per hand-off, so a reader can say WHEN
        and HOW MANY rather than only that something happened once."""
        run_cli("--vault-root", str(self.root), "orientation", "--record")
        body = (self.root / pfb.AGENT_OFFER_FLAG_REL).read_text(encoding="utf-8")
        lines = [x for x in body.splitlines() if x.strip()]
        self.assertEqual(1, len(lines))
        self.assertRegex(lines[0], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        # a legacy empty marker from the first build still counts as one
        (self.root / pfb.AGENT_OFFER_FLAG_REL).write_text("", encoding="utf-8")
        self.assertEqual(1, pfb.agent_offer_handoffs(self.root))

    def test_po_skipping_step_8_becomes_visible_to_a_later_reader(self):
        """The exact measured state: no walk flag (Po never offered), and an
        agent-direct offer that did fire. A reader who is not either agent can
        say so, from files on disk."""
        run_cli("--vault-root", str(self.root), "orientation", "--record")
        state = pfb.orientation_state(self.root)
        self.assertFalse(state["walk_offered"])
        self.assertTrue(state["agent_offer_surfaced"])
        self.assertIn("NEVER been offered through the walk playbook", state["summary"])
        proc = run_cli("--vault-root", str(self.root), "audit")
        self.assertEqual(0, proc.returncode)
        self.assertIn("did not reach the walk", proc.stdout)

    def test_a_fresh_install_reports_the_tour_has_never_been_offered(self):
        state = pfb.orientation_state(self.root)
        self.assertFalse(state["walk_offered"])
        self.assertFalse(state["agent_offer_surfaced"])
        self.assertIn("never been offered", state["summary"])

    def test_the_offer_text_has_exactly_one_source(self):
        proc = run_cli("--vault-root", str(self.root), "orientation")
        self.assertIn(pfb.AGENT_OFFER_LINE, proc.stdout)

    def test_taking_the_walk_later_still_silences_everything(self):
        run_cli("--vault-root", str(self.root), "orientation", "--record")
        pfb.mark_walk_offered(self.root)
        state = pfb.orientation_state(self.root)
        self.assertTrue(state["walk_offered"])
        self.assertFalse(state["agent_fold_armed"])


class BootProseCarriesTheShapes(unittest.TestCase):
    """For an agent that reads rather than runs, the DOCUMENT is the mechanism.
    These assert the prose that a prose-following agent actually resolves
    against, in every surface that gates soul-loading -- including the kernel
    thin-pointer, which carries its own two-shape ruling and is the file a
    customer's agent reads FIRST.

    MUTATION (verdict flips): revert any one of the amended paragraphs and its
    test fails by name.
    """

    def setUp(self):
        self.playbook = PLAYBOOK.read_text(encoding="utf-8")
        self.pointer = KERNEL_POINTER.read_text(encoding="utf-8")
        self.concierge = CONCIERGE.read_text(encoding="utf-8")

    def test_playbook_rules_name_shape_c(self):
        rules = self.playbook.split("## Resources")[0]
        self.assertIn("Shape C", rules)
        self.assertIn("charter_file", rules)

    def test_step_2_0_is_no_longer_tier_3_gated(self):
        """A customer's agent structurally has no Tier 3. Gating soul-loading
        on a tier it cannot have is how the step got dropped on the tag alone."""
        heading = [
            line for line in self.playbook.splitlines()
            if line.startswith("#### Step 2.0 ")
        ]
        self.assertEqual(1, len(heading), "Step 2.0 heading not found exactly once")
        self.assertNotIn("[Tier 3]", heading[0])
        block = self.playbook.split("#### Step 2.0 ")[1].split("#### ")[0]
        self.assertIn("**Only if:** ALWAYS", block)

    def test_step_2_0_names_the_resolver_and_the_named_refusal(self):
        block = self.playbook.split("#### Step 2.0 ")[1].split("#### ")[0]
        self.assertIn("tropo-boot-identity.py", block)
        self.assertIn("SOUL NOT LOADED", block)

    def test_the_escalation_predicate_is_decidable(self):
        """`executive agent` was used 13 times as an escalation condition and
        never defined; a customer's agent could not evaluate the condition that
        would make its own missing soul loud."""
        rules = self.playbook.split("## Resources")[0]
        self.assertIn("agent_class: executive", rules)
        self.assertNotIn(
            "For executive agents, a missing soul is a CRITICAL gap", rules
        )

    def test_kernel_pointer_resolves_the_charter_shapes(self):
        """The sixth gate. The activation template sends a customer's agent
        HERE first, and this file closed with its own `agent_uid:`-only ruling
        -- so a Shape-C agent was told its identity was unresolvable before it
        ever reached the playbook's table."""
        self.assertIn("charter_file", self.pointer)

    def test_kernel_pointer_floor_stays_self_contained(self):
        """`Canonical-unreachable floor` exists to work when other things do
        not. It must not be rewritten into "run a tool"."""
        floor = self.pointer.split("Canonical-unreachable floor")[1]
        self.assertNotIn("tropo-boot-identity.py", floor)

    def test_group_5_folds_the_orientation_offer(self):
        """Asserts the STEP BODY, not the heading string. The first draft of
        this test checked only that `Step 5.1.6b` appeared somewhere in the
        file, and its own mutation run did not flip -- a heading renamed to
        `Step 5.1.6b — REMOVED` still satisfied it. A green check over a blind
        mechanism is worse than no check; caught here before it shipped."""
        self.assertIn("#### Step 5.1.6b — ", self.playbook)
        block = self.playbook.split("#### Step 5.1.6b — ")[1].split("#### ")[0]
        self.assertIn("tropo-boot-identity.py orientation", block)
        self.assertIn("should_fold_agent_offer", block)
        self.assertIn("startup signal", block)
        self.assertIn("at most once", block.lower())
        # It must sit in Group 5, between 5.1.6 and 5.1.7, where the four
        # proven signal-fold steps live.
        g5 = self.playbook.split("### Group 5 — Startup Signal")[1]
        self.assertIn("#### Step 5.1.6b — ", g5)
        self.assertLess(
            g5.index("#### Step 5.1.6b — "), g5.index("#### Step 5.1.7 — ")
        )

    def test_concierge_step_8_still_reads_the_one_fact(self):
        """Do NOT let the fix drift the concierge's own trigger: it was correct
        and it stays."""
        self.assertIn("should_fire_automatic_walk", self.concierge)

    def test_activation_file_definition_names_all_three_live_spellings(self):
        rules = self.playbook.split("## Resources")[0]
        for spelling in ("<name>-activation.md", "<name>-activate.md", "activate.md"):
            self.assertIn(spelling, rules)


class WarnSafeContract(unittest.TestCase):
    """Rule 1, applied to every reachable state of everything added here:
    nothing may refuse the founder. Named harm, or it proceeds and records.

    MUTATION (verdict flips): change any `return 0` in
    `tropo-boot-identity.py` to a nonzero exit and this class fails.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_studio(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_every_verb_exits_zero_on_every_state(self):
        create_three_file_agent(self.root, "sage")
        create_bare_agent(self.root, "ghost")
        cases = [
            ("soul", "--agent", "sage", "--no-journal"),
            ("soul", "--agent", "ghost", "--no-journal"),
            ("soul", "--agent", "absent-entirely", "--no-journal"),
            ("orientation",),
            ("orientation", "--record"),
            ("orientation", "--json"),
            ("audit",),
            ("audit", "--agent", "sage"),
            ("audit", "--json"),
        ]
        for case in cases:
            with self.subTest(case=case):
                proc = run_cli("--vault-root", str(self.root), *case)
                self.assertEqual(0, proc.returncode, "{} -> {}".format(case, proc.stderr))

    def test_it_survives_a_corrupt_studio_without_refusing(self):
        bad = self.root / "agents" / "broken"
        bad.mkdir(parents=True)
        (bad / "broken-activation.md").write_text(
            "not: [valid\n---\ngarbage", encoding="utf-8"
        )
        proc = run_cli(
            "--vault-root", str(self.root), "soul", "--agent", "broken", "--no-journal"
        )
        self.assertEqual(0, proc.returncode, proc.stderr)

    def test_no_added_surface_can_halt_a_boot(self):
        """Grep-level guard against the failure mode a later generation is most
        likely to add back: a halt in the boot-identity path."""
        source = (TOOLS / "tropo-boot-identity.py").read_text(encoding="utf-8")
        self.assertNotIn("sys.exit(1)", source)
        self.assertFalse(
            re.search(r"return\s+[1-9]\d*\b", source),
            "a nonzero return crept into the warn-safe tool",
        )


class ResolverIsCorrectOnRealSubstrate(unittest.TestCase):
    """The resolver runs against this studio's own live agents, because a
    resolver validated only on fixtures is a resolver validated on the shapes
    its author remembered.

    MUTATION (verdict flips): revert `extract_section`'s title ranking to
    first-match and `test_unified_entries_resolve_to_soul_not_charter_identity`
    fails -- that first-match rule reported six live agents as souls-loaded
    while handing them their charter's `## 1. IDENTITY` paragraph.
    """

    def test_unified_entries_resolve_to_soul_not_charter_identity(self):
        for slug in ("argus", "metis", "vela", "po"):
            with self.subTest(agent=slug):
                res = bi.resolve_soul(ROOT, slug)
                self.assertTrue(res.loaded, res.tried)
                self.assertEqual("A", res.shape)
                self.assertIn("Soul", res.section or "", "resolved to the wrong section")

    def test_the_live_shape_c_agent_resolves(self):
        """`kb-curator` is a real Shape-C agent already in this studio: no
        `agent_uid:`, a `charter_file:`, a populated `soul:` block. The cure is
        measured on real frontmatter, not only on a fixture."""
        res = bi.resolve_soul(ROOT, "kb-curator")
        self.assertEqual("C", res.shape)
        self.assertTrue(res.loaded)
        self.assertIn("Knowledgebase Curator", res.text)

    def test_uncommissioned_crew_are_not_alarmed(self):
        for slug in ("nestor", "tiphys"):
            with self.subTest(agent=slug):
                res = bi.resolve_soul(ROOT, slug)
                self.assertEqual(bi.STATUS_NOT_COMMISSIONED, res.status)

    def test_a_redirect_stub_is_followed_not_reported_as_a_soul(self):
        """Talos's `§Soul` is three lines saying the soul lives inline in
        `§Boot-Extension`. Reporting the stub is a false pass."""
        res = bi.resolve_soul(ROOT, "talos")
        self.assertTrue(res.loaded)
        self.assertIn("redirect", res.section or "")
        self.assertGreater(len(res.text), 400)


if __name__ == "__main__":
    unittest.main()
