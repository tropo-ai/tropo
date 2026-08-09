#!/usr/bin/env python3
"""Contract for the activation mint — written BEFORE the implementation exists.

Scope: the MINT ONLY. Birth. Not retirement, not the sweep, not the cutover.
Mike scoped this increment on 2026-08-03 so we could prove one piece before
betting more on it.

Derived from the test-spec at vault/files/cc32cb2a.md and the eleven rules at
vault/files/40b13b5b.md, incorporating Argus A144's four rulings.

WHY THESE ARE WRITTEN FIRST. Tests written to an implementation pass while the
behaviour is wrong. Twenty-five tests in the authority-chain suite were green for
months while pinning a contract Mike had ruled out, because they had been written
to match what the code did rather than what the system was for. These are written
from the contract, and they are expected to be RED until the tool exists.

────────────────────────────────────────────────────────────────────────────────
THE INTERFACE UNDER TEST — stated here so the builder has nothing to guess at.

    python3 vault/tools/tropo-activate.py \\
        --agent <slug> --authorized-by <principal> \\
        [--agent-class <class>] [--agent-root <uid>] \\
        [--model <s>] [--platform <s>] [--member-of <csv>] [--run-folder <p>]

  stdout  exactly one line of JSON:
            {"activation_uid": "<8hex>", "generation": "G101",
             "provisional": false, "findings": []}
  stderr  human narration: findings, the PROVISIONAL banner when applicable.
  exit    0 whenever an identity was issued — which is ALWAYS, except for a
          malformed --agent-class, the one case where there is no identity to
          record.

  The agent does NOT pass a generation. The mint issues it. (Rule 1, Mike-locked.)
────────────────────────────────────────────────────────────────────────────────
"""

import contextlib
import importlib.util
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[3]
TOOL = REPO / "vault" / "tools" / "tropo-activate.py"


def _load_activation_module():
    name = "tropo_activate_atomic_birth_tests"
    spec = importlib.util.spec_from_file_location(name, TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ACTIVATE_MODULE = _load_activation_module()


class ActivationMintFixture(unittest.TestCase):
    """Each test gets a scratch studio. Nothing here touches the real vault."""

    def setUp(self):
        self.studio = pathlib.Path(tempfile.mkdtemp(prefix="mintspec-"))
        (self.studio / "vault" / "files").mkdir(parents=True)
        (self.studio / "vault" / "agents").mkdir(parents=True)
        self.files = self.studio / "vault" / "files"

    def tearDown(self):
        shutil.rmtree(self.studio, ignore_errors=True)

    def activate(self, agent="probe", authorized_by="mike", **kw):
        """Run the mint. Returns (exit_code, parsed_stdout_or_None, stderr)."""
        cmd = [
            sys.executable, str(TOOL),
            "--agent", agent, "--authorized-by", authorized_by,
            "--agent-class", kw.pop("agent_class", "executive"),
            "--vault-root", str(self.studio),
        ]
        for flag, value in kw.items():
            cmd += [f"--{flag.replace('_', '-')}", str(value)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        try:
            parsed = json.loads(proc.stdout.strip())
        except (ValueError, AttributeError):
            parsed = None
        return proc.returncode, parsed, proc.stderr

    def plant(self, uid, agent, generation, status="retired", **extra):
        """Write an activation record directly, to set up lineage."""
        lines = [
            "---", f"uid: {uid}", "type: activation", f"agent: {agent}",
            f"generation: {generation}", f"status: {status}",
            "agent_class: executive", "activated_by: mike",
            f"activated_at: {extra.pop('activated_at', '2026-07-01T09:00:00Z')}",
        ]
        for k, v in extra.items():
            lines.append(f"{k}: {v}")
        lines += ["---", "", f"# {agent} {generation}", ""]
        (self.files / f"{uid}.md").write_text("\n".join(lines), encoding="utf-8")

    def record(self, uid):
        return (self.files / f"{uid}.md").read_text(encoding="utf-8")


class TestNothingRefusesABirth(ActivationMintFixture):
    """B-N1. The deadlock that cost G97, G99, G100 and Po."""

    def test_genesis_succeeds(self):
        """B-P1. An agent that has never existed. Never once tested before today."""
        code, out, _ = self.activate(agent="brand-new")
        self.assertEqual(code, 0)
        self.assertRegex(out["activation_uid"], r"^[0-9a-f]{8}$")
        self.assertEqual(
            out["generation"], "G1",
            "the first generation of a lineage is G1 — genesis is not mentioned "
            "once in the eleven rules and has never been exercised",
        )

    def test_an_unreadable_predecessor_does_not_block(self):
        """B-P8. A broken chain yields a finding, never a refusal."""
        (self.files / "bad00001.md").write_text(
            "---\nuid: bad00001\ntype: activation\nagent: probe\n"
            "generation: [this is not\n  valid yaml\n---\n", encoding="utf-8")
        code, out, _ = self.activate(agent="probe")
        self.assertEqual(
            code, 0,
            "a corrupt predecessor record must not prevent a birth — this is the "
            "exact shape that made 19 agents silently unbootable",
        )
        self.assertIsNotNone(out)
        self.assertTrue(
            out["findings"],
            "it must not refuse, and it must not be SILENT either — the problem "
            "is recorded as a finding",
        )

    def test_a_live_predecessor_does_not_block(self):
        """B-P4 + rule 2. Overlap is normal; a parent is alive when the child is."""
        self.plant("aaaa0001", "probe", "G1", status="active")
        code, out, _ = self.activate(agent="probe")
        self.assertEqual(code, 0, "ADR-016 is a finding now, not a gate")
        self.assertTrue(out["provisional"] or out["findings"],
                        "overlap is allowed but it is still worth saying out loud")

    def test_only_a_malformed_class_refuses(self):
        """The single surviving refusal: no identity to record without a class."""
        code, _, err = self.activate(agent="probe", agent_class="not-a-real-class")
        self.assertNotEqual(code, 0)
        self.assertIn("agent_class", err)


class TestTheMintOwnsTheNumber(ActivationMintFixture):
    """Rule 1, Mike-locked. The agent is TOLD what it is."""

    def test_the_agent_cannot_choose_its_generation(self):
        """B-P6. There is no --generation flag, so there is no claim to verify."""
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--help"],
            capture_output=True, text=True, timeout=60)
        self.assertNotIn(
            "--generation", proc.stdout,
            "the mint issues the number; accepting one from the caller "
            "reintroduces the mismatch check that ADR-028 enforced and that "
            "blocked this very lineage",
        )

    def test_the_number_is_highest_known_local_plus_one(self):
        """Argus ruling O1. No network, no shared authority, works offline."""
        self.plant("aaaa0001", "probe", "G1")
        self.plant("aaaa0002", "probe", "G2")
        _, out, _ = self.activate(agent="probe")
        self.assertEqual(out["generation"], "G3")

    def test_a_gap_in_history_does_not_stall_the_counter(self):
        """Highest-known + 1, not a contiguity check."""
        self.plant("aaaa0001", "probe", "G1")
        self.plant("aaaa0009", "probe", "G9")
        _, out, _ = self.activate(agent="probe")
        self.assertEqual(out["generation"], "G10")

    def test_other_agents_do_not_advance_this_counter(self):
        self.plant("bbbb0001", "someone-else", "G7")
        _, out, _ = self.activate(agent="probe")
        self.assertEqual(out["generation"], "G1")


class TestTheRecordIsHonestAndReadable(ActivationMintFixture):
    """C-P2 + S-P3 + B-P9."""

    def test_familiar_fields_survive_so_old_readers_still_parse(self):
        """C-P2, Argus ruling O4. Rule 11's safety argument covered writers only."""
        _, out, _ = self.activate(agent="probe")
        text = self.record(out["activation_uid"])
        for field in ("uid", "type", "agent", "generation", "activated_at",
                      "activated_by", "status", "agent_class", "member_of"):
            self.assertIn(f"{field}:", text,
                          f"{field} must survive or existing readers go silently wrong")

    def test_activated_at_is_a_full_instant_never_a_bare_date(self):
        """S-P3. A bare local date read as midnight UTC over-stated age by a
        timezone offset and made every sub-agent sweepable AT BIRTH."""
        _, out, _ = self.activate(agent="probe")
        text = self.record(out["activation_uid"])
        line = next(l for l in text.splitlines() if l.startswith("activated_at:"))
        self.assertRegex(line, r"activated_at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

    def test_the_durable_reference_is_the_uid_not_the_label(self):
        """B-P9, Argus ruling O1 — the piece both Metis and Argus missed alone.

        Artifacts carry the immutable activation UID, so a post-merge
        renumbering renames no file, no filename and no Git object.
        """
        _, out, _ = self.activate(agent="probe")
        text = self.record(out["activation_uid"])
        self.assertIn("created_by_activation_uid:", text)
        self.assertIn(out["activation_uid"], text)

    def test_the_predecessor_link_is_recorded_when_there_is_one(self):
        """B-P2. Attribution and continuity — the whole bar."""
        self.plant("aaaa0001", "probe", "G1")
        _, out, _ = self.activate(agent="probe")
        self.assertIn("predecessor_activation_uid: aaaa0001",
                      self.record(out["activation_uid"]))

    def test_genesis_records_no_predecessor(self):
        _, out, _ = self.activate(agent="brand-new")
        text = self.record(out["activation_uid"])
        self.assertNotRegex(text, r"predecessor_activation_uid: [0-9a-f]{8}")


class TestBirthOnlyCreates(ActivationMintFixture):
    """B-N2 + B-N4. Rule 3's premise, made true by construction."""

    def test_no_existing_record_is_modified(self):
        """B-N2. Birth is currently the studio's ONLY automatic closer, which is
        why 'the act that cannot destroy anything' was false when written."""
        self.plant("aaaa0001", "probe", "G1", status="active")
        before = self.record("aaaa0001")
        self.activate(agent="probe")
        self.assertEqual(before, self.record("aaaa0001"),
                         "activate must not close, sweep or edit anything")

    def test_no_key_material_is_created(self):
        """B-N4, Argus ruling O2. The lifecycle mints no cryptographic keys —
        which REMOVES the destructive shared key-root problem rather than
        relocating it, and deletes the whole broker-loss family with it."""
        _, out, _ = self.activate(agent="probe")
        text = self.record(out["activation_uid"])
        for banned in ("agent_public_key", "ssh-ed25519", "key_custody"):
            self.assertNotIn(banned, text)

    def test_no_network_or_broker_is_required(self):
        """X5. True by construction now, rather than by care."""
        code, out, _ = self.activate(agent="probe")
        self.assertEqual(code, 0)
        self.assertIsNotNone(out)


class TestThreeGenerationsDeep(ActivationMintFixture):
    """B-P3. ANY birth test that stops at the first successor is INVALID.

    G99 verified her own birth and shipped. The defect surfaced one generation
    later, on G100, and cost Mike an hour he should not have spent.
    """

    def test_born_succeeded_and_succeeded_again(self):
        _, first, _ = self.activate(agent="probe")
        self.plant(first["activation_uid"], "probe", first["generation"])

        _, second, _ = self.activate(agent="probe")
        self.assertEqual(second["generation"], "G2")
        self.plant(second["activation_uid"], "probe", second["generation"])

        _, third, _ = self.activate(agent="probe")
        self.assertEqual(third["generation"], "G3")
        self.assertIn(f"predecessor_activation_uid: {second['activation_uid']}",
                      self.record(third["activation_uid"]))


class TestSystemOnlyType(ActivationMintFixture):
    """Argus's mint integration ruling: one writer, and the generic door refuses."""

    def test_generic_mint_refuses_to_mint_an_activation(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "vault" / "tools" / "tropo-mint-id.py"),
             "--kind", "file", "--type", "activation", "--author", "test"],
            capture_output=True, text=True, cwd=str(REPO), timeout=120)
        self.assertNotEqual(
            proc.returncode, 0,
            "activation is system-only: it must be reachable through the "
            "lifecycle writer alone, or we grow a second writer — which is "
            "exactly what pipelines already are today",
        )


class _RecordingFreshener:
    def __init__(self, *, refuse=False, refuse_times=None):
        """``refuse`` refuses forever; ``refuse_times`` refuses exactly N times.

        The bounded form exists for the reconcile-and-retry path (talos-t38,
        2026-08-05): the interesting case is a transaction that refuses on a stale
        manifest and SUCCEEDS once the manifest is reconciled, which a
        refuse-forever double cannot express.
        """
        self.refuse = refuse
        self.refusals_left = refuse_times
        self.calls = []
        self.source_absent_at_entry = None

    def freshen_many(
        self,
        uids,
        root,
        *,
        source_replacements,
        require_absent_sources,
    ):
        self.calls.append({
            "uids": tuple(uids),
            "root": root,
            "source_replacements": source_replacements,
            "require_absent_sources": tuple(require_absent_sources),
        })
        ((path, raw),) = source_replacements.items()
        self.source_absent_at_entry = not path.exists()
        refusing = self.refuse
        if self.refusals_left:
            refusing = True
            self.refusals_left -= 1
        if refusing:
            print(
                "[rebuild --batch] REFUSAL: semantic derivation inputs changed "
                "outside the owned projections; no derived rows written",
                file=sys.stderr,
            )
            return 1
        path.write_bytes(raw)
        return 0


class TestCanonicalBirthIsOneAtomicIndexGesture(ActivationMintFixture):
    """Regression for the rowless 3c9243b7 activation born on 2026-08-03."""

    UID = "abcddcba"

    def setUp(self):
        super().setUp()
        tools = self.studio / "vault" / "tools"
        tools.mkdir()
        (tools / "tropo-rebuild-index.py").write_text(
            "# canonical freshener marker for the fixture\n",
            encoding="utf-8",
        )
        self.index = self.studio / "vault" / "00-index.jsonl"
        self.index.write_text('{"uid":"existing"}\n', encoding="utf-8")

    def run_in_process(self, freshener):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(
                ACTIVATE_MODULE._MINT,
                "mint",
                return_value=[self.UID],
            ),
            mock.patch.object(
                ACTIVATE_MODULE._MINT,
                "_load_rebuild_index",
                return_value=freshener,
            ),
            mock.patch.object(
                ACTIVATE_MODULE._MINT,
                "_verify_minted_index_row",
            ) as verify,
            mock.patch.object(
                ACTIVATE_MODULE,
                "freshen_index",
                side_effect=AssertionError(
                    "canonical birth must not use post-write --only"
                ),
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = ACTIVATE_MODULE.main([
                "--agent", "probe",
                "--authorized-by", "mike",
                "--agent-class", "executive",
                "--vault-root", str(self.studio),
            ])
        return code, stdout.getvalue(), stderr.getvalue(), verify

    def test_success_stages_create_only_source_inside_index_transaction(self):
        freshener = _RecordingFreshener()
        # .resolve() (metis-g101, 2026-08-04): tempfile.mkdtemp() returns
        # /var/folders/... on macOS, which is a symlink to /private/var/folders/...
        # The tool resolves its own paths, so an unresolved expectation here passes
        # on Linux — where this was authored, in Cursor Cloud — and fails on macOS,
        # where Mike works and where boot step 5.1.10 runs this suite on EVERY
        # activation. The call["root"] assertion below already resolved; these did
        # not. Author's-environment-as-mock, caught by the boot check doing its job.
        out_path = (self.files / f"{self.UID}.md").resolve()

        code, stdout, _stderr, verify = self.run_in_process(freshener)

        self.assertEqual(code, 0)
        self.assertTrue(
            freshener.source_absent_at_entry,
            "the activation source must not be committed before the index transaction",
        )
        self.assertEqual(len(freshener.calls), 1)
        call = freshener.calls[0]
        self.assertEqual(call["uids"], (self.UID,))
        self.assertEqual(call["root"], self.studio.resolve())
        self.assertEqual(call["require_absent_sources"], (out_path,))
        self.assertEqual(set(call["source_replacements"]), {out_path})
        self.assertEqual(
            call["source_replacements"][out_path],
            out_path.read_bytes(),
        )
        verify.assert_called_once_with(
            self.studio.resolve(),
            self.UID,
            out_path,
            "activation",
        )
        self.assertEqual(json.loads(stdout)["activation_uid"], self.UID)

    def test_a_refusal_is_reconciled_and_retried_and_the_birth_is_clean(self):
        """The path that was costing agents their existence.

        Measured on real copies of this studio (talos-t38, 2026-08-05): a stale
        manifest with a predecessor that never retired refused the birth outright
        — exit 1, no identity — while the SAME staleness with a retired
        predecessor was born clean, because retirement refreshes the manifest as
        a side effect on its way past. One refusal, reconcile, retry.
        """
        freshener = _RecordingFreshener(refuse_times=1)
        out_path = self.files / f"{self.UID}.md"

        code, stdout, stderr, verify = self.run_in_process(freshener)

        self.assertEqual(code, 0)
        self.assertTrue(out_path.exists(), "the agent must be born")
        self.assertEqual(len(freshener.calls), 2, "refused once, retried once")
        payload = json.loads(stdout)
        self.assertEqual(payload["activation_uid"], self.UID)
        # A refusal the reconcile repaired must leave NO surviving refusal
        # finding: announced, then resolved out loud, so the record shows the
        # sequence rather than handing the successor an alarm whose cure has
        # already run. Asserted on the refusal specifically rather than on
        # `provisional` overall — this fixture studio has no agent card for its
        # probe slug, and that unrelated finding is not what this case measures.
        self.assertFalse(
            [f for f in payload["findings"] if "index refused" in f],
            f"the repaired refusal should not survive: {payload['findings']}",
        )
        self.assertIn("RESOLVED: index refused the birth transaction", stderr)
        verify.assert_called_once()

    def test_a_second_refusal_still_births_the_agent_provisionally(self):
        """Metis G102's boundary: a second refusal must not cost an existence.

        The index declining twice is a fact about a projection. The agent is born
        source-only, `provisional: true`, and the finding carries the exact
        command that derives the missing row — never `exit 1` with no identity.
        """
        freshener = _RecordingFreshener(refuse=True)
        out_path = self.files / f"{self.UID}.md"

        code, stdout, stderr, _verify = self.run_in_process(freshener)

        self.assertEqual(code, 0, "a refusal must never cost an agent its existence")
        self.assertTrue(out_path.exists(), "the record is written even when the index refuses")
        self.assertEqual(len(freshener.calls), 2, "one retry, not an unbounded loop")
        payload = json.loads(stdout)
        self.assertEqual(payload["activation_uid"], self.UID)
        self.assertTrue(payload["provisional"])
        self.assertTrue(payload["findings"])
        joined = " ".join(payload["findings"])
        self.assertIn("this birth stands", joined)
        self.assertIn("tropo-rebuild-index.py --apply", joined,
                      "the finding must name the command that closes it")
        self.assertIn("semantic derivation inputs changed", stderr)

    def test_the_retry_is_bounded_and_never_loops(self):
        # A retry policy that can run twice can run forever if the bound is
        # implicit. Pin it: exactly two attempts, no more, however hard it refuses.
        freshener = _RecordingFreshener(refuse=True)
        code, _stdout, _stderr, _verify = self.run_in_process(freshener)
        self.assertEqual(code, 0)
        self.assertEqual(len(freshener.calls), 2)

    def test_the_governed_birth_reconciles_the_index_before_it_returns(self):
        """The wiring, not the function. Mutation-driven (metis-g102, 2026-08-05).

        My first three tests for the reconcile all passed while the call was DELETED
        from this, the branch a real studio takes — they exercised the function in
        isolation and never proved it ran. An audit inherits the shape of its
        instrument, and mine could not look at the wiring. Found by mutation, which is
        the acceptance; the green run was not.
        """
        calls = []
        real_run = subprocess.run

        def spy(cmd, **kw):
            argv = [str(c) for c in cmd]
            calls.append(argv)
            if "--apply" in argv:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return real_run(cmd, **kw)

        with mock.patch.object(ACTIVATE_MODULE.subprocess, "run", spy):
            code, _stdout, _stderr, _verify = self.run_in_process(_RecordingFreshener())

        self.assertEqual(code, 0)
        self.assertTrue(
            any("--apply" in argv for argv in calls),
            "a governed birth must leave the index fit for the NEXT birth — without "
            "this the successor's transaction refuses with exit 1 and no identity is "
            "issued, which is the refusal Mike ruled out",
        )

    def test_the_card_is_flipped_on_the_path_a_real_studio_takes(self):
        """metis-g102, 2026-08-05, found at my own birth.

        `sync_agent_card()` was called only on the fallback branch — the one taken
        when `vault/00-index.jsonl` does not exist. That file is GITIGNORED, so it
        is absent in exactly one kind of studio: a fresh throwaway clone. Vela V71
        proved the Po-bug weld by cloning the studio and running a real
        retire-then-birth; the clone took the fallback branch, so her fix worked
        there and had never once run in argo-os. My own card still read
        `status: RETIRED, generation: G101` after a clean, non-provisional birth,
        and `00-crew-brief.md` renders FROM THE CARD.

        THIS CLASS is the one the governed path runs in — `self.index` exists — so
        this test sits where the branch it pins actually lives. Mutation-proven:
        moving the `sync_agent_card()` call back below the governed return reds it.
        """
        card = self.studio / "vault" / "agents" / "9f000001.md"
        card.write_text(
            "---\n"
            "uid: 9f000001\n"
            "type: agent\n"
            "agent: probe\n"
            "status: RETIRED\n"
            "generation: G101\n"
            "current_activation_uid: deadbeef\n"
            "---\n\n# probe\n",
            encoding="utf-8",
        )

        code, stdout, _stderr, _verify = self.run_in_process(_RecordingFreshener())
        self.assertEqual(code, 0)

        after = card.read_text(encoding="utf-8")
        self.assertIn("status: ACTIVE", after)
        self.assertNotIn("status: RETIRED", after)
        self.assertIn(f"current_activation_uid: {self.UID}", after)
        self.assertNotIn("current_activation_uid: deadbeef", after)
        self.assertIn(
            f"generation: {json.loads(stdout)['generation']}",
            after,
            "the card must name the generation the mint just issued, not its predecessor",
        )


class TestBirthLeavesTheIndexFitForTheNextBirth(ActivationMintFixture):
    """metis-g102, 2026-08-05. The refusal that had nothing to do with identity.

    Reproduced in a clone before it was fixed: retire, then birth, and the birth dies
    with exit 1, no record and no identity issued —

        [rebuild --batch] REFUSAL: semantic derivation inputs changed outside the
        owned projections: agents/metis/transfers/G102.md, vault/agents/9fc001c3.md

    Retirement writes the transfer letter and flips the card; birth flips the card.
    None of those are owned by the incremental index target, so the manifest goes
    stale and the NEXT lifecycle event's transaction refuses. Every birth follows a
    retirement, so every birth was refused. Mine was.

    It is the ruled-out class at a lower layer: the identity gates were made unable to
    refuse a birth, and the index layer refuses harder than they ever did — a
    provisional birth still issues a number, this issues nothing. Mike's bar: "I NEVER
    EVER want to see my agents telling me they are failing to boot."

    The cure is welded to both terminal transitions. This pins the birth half; the
    acceptance evidence is the clone rehearsal (two full retire-birth cycles, zero
    manual steps, both non-provisional).
    """

    def test_the_full_reconcile_runs_after_the_card_is_written(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append([str(c) for c in cmd])
            return subprocess.CompletedProcess(cmd, 0, "", "")

        card = self.studio / "vault" / "agents" / "9f000002.md"
        card.write_text(
            "---\nuid: 9f000002\ntype: agent\nagent: probe\nstatus: RETIRED\n"
            "generation: G101\ncurrent_activation_uid: deadbeef\n---\n\n# probe\n",
            encoding="utf-8",
        )
        tools = self.studio / "vault" / "tools"
        tools.mkdir(parents=True, exist_ok=True)
        (tools / "tropo-rebuild-index.py").write_text("# marker\n", encoding="utf-8")
        (self.studio / "vault" / "00-index.jsonl").write_text("{}\n", encoding="utf-8")

        with mock.patch.object(ACTIVATE_MODULE.subprocess, "run", fake_run):
            findings = ACTIVATE_MODULE.Findings()
            ACTIVATE_MODULE.reconcile_index_after_lifecycle_write(
                self.studio.resolve(), findings
            )

        self.assertEqual(len(calls), 1, "the reconcile must actually shell out")
        self.assertIn("--apply", calls[0],
                      "the incremental path is what refuses; only a full apply recovers")
        self.assertNotIn("--only", calls[0])
        self.assertEqual(findings.items, [], "a successful reconcile leaves no alarm")

    def test_a_failed_reconcile_names_the_command_and_never_refuses(self):
        def failing_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, "", "boom")

        tools = self.studio / "vault" / "tools"
        tools.mkdir(parents=True, exist_ok=True)
        (tools / "tropo-rebuild-index.py").write_text("# marker\n", encoding="utf-8")
        (self.studio / "vault" / "00-index.jsonl").write_text("{}\n", encoding="utf-8")

        with mock.patch.object(ACTIVATE_MODULE.subprocess, "run", failing_run):
            findings = ACTIVATE_MODULE.Findings()
            ACTIVATE_MODULE.reconcile_index_after_lifecycle_write(
                self.studio.resolve(), findings
            )

        self.assertEqual(len(findings.items), 1)
        # O34's F4 rule applies to THIS finding too — it caught mine when I first wrote
        # it without the command, which is exactly the defect the rule exists for.
        self.assertIn("tropo-rebuild-index.py --apply", findings.items[0])

    def test_a_repaired_alarm_is_resolved_not_left_standing(self):
        findings = ACTIVATE_MODULE.Findings()
        findings.record("index freshen failed", "the incremental target refused")
        self.assertTrue(findings)

        self.assertTrue(findings.resolve("index freshen failed", "repaired"))
        self.assertEqual(findings.items, [])
        self.assertFalse(
            findings,
            "a retirement whose index was repaired in the same run is not provisional",
        )
        self.assertFalse(findings.resolve("index freshen failed", "again"),
                         "resolving something that never fired must report honestly")


if __name__ == "__main__":
    unittest.main(verbosity=2)
