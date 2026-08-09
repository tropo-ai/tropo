"""D5 Atomic-Promotion Landing fixture — test-spec 0f06a8b5 (dev-spec 396d88a4).

Two-clone / two-Studio landing fixture over REAL git remotes (local bare repos
stand in for github.com; the CAS/ff/custom-ref plumbing is identical). Assertions
P1–P7:

  P1  atomic promotion   — one retry-safe transaction; fault-inject at EVERY step
                           → single clean outcome, no duplicated node, ZERO
                           orphaned refs.
  P2  protected-ref CAS  — non-force fast-forward to the exact candidate; two
                           Studios race → one winner, loser REMOTE_CAS_FAILED;
                           host rewrite refused; stale plan → STALE_PLAN.
  P3  landed=local-only  — integrated stays publishing; landed ONLY after local
                           reconcile + receipt; optimistic jump IllegalTransition;
                           dest-A landing does not flip dest-B.
  P4  receipt-ref        — append-only single-parent CAS, content-addressed,
                           non-recursive; forged-writer/CAS-race/replay/
                           receipt-of-receipt each fail exactly.
  P5  closed enum + supersede — RECONCILE_FAILED closed code + resumable_from;
                           superseded-before-reconcile terminal not-landed;
                           landed-then-superseded distinguished; unknown code hard.
  P6  GitHub gate        — validator BLOCKS broken governed files; clean passes;
                           pre-commit hook absence detected + refused.
  P7  end-to-end         — full walk; draftStatus/receipts reconstruct from the
                           durable journal + receipt-refs after a rebuild/cold-boot.

github.com-only prerequisite (FLAGGED, not faked): the disposable PROTECTED repo
+ least-privilege GitHub App credential prove server-side branch-rule
unbypassability (P2 host-rewrite blocked BY the host, P6 required-Action). The
CLIENT mechanics (CAS non-ff, exact-sha/changed-tree refusal, validator + hook)
are proven here against the bare remote.

Run: python3 -m unittest tests.test_d5_atomic_promotion_0f06a8b5   (from vault/tools/)
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import publish_service as svc  # noqa: E402
from lib import publish_journal as pj  # noqa: E402
from lib import draft_status as ds  # noqa: E402
from lib import ref_closure as rc  # noqa: E402
from lib import github_transport as ght  # noqa: E402
from lib import receipt_ref as rref  # noqa: E402
from lib import governance_gate as gg  # noqa: E402

VAULT = "aabbccdd"
WRITER = "wr000001"
WKEY = "key-least-priv"


def _git(args, cwd=None):
    return ght.run_git(args, cwd=cwd)


def _priv_file(uid, *, scope="argo-private", title="Note", refs=None, body="body"):
    lines = ["---", f"uid: {uid}", "type: note", f'title: "{title}"', "owner: mike",
             f"extraction_scope: {scope}"]
    if refs:
        lines.append("refs:")
        lines += [f"  - {r}" for r in refs]
    lines.append("---")
    return "\n".join(lines) + "\n" + body + "\n"


class D5Fixture(unittest.TestCase):
    """A private source Studio, a team canonical (bare) + working clone, a
    destination Studio clone, and a bare receipts repo — all real git."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

        # private source studio (also the vault_root for journal + envelopes)
        self.priv = self.d / "private"
        (self.priv / "files").mkdir(parents=True)
        (self.priv / "files" / "11111111.md").write_text(_priv_file("11111111", title="P"))
        (self.priv / "files" / "22222222.md").write_text(
            _priv_file("22222222", title="Q", refs=["11111111"], body="see [P](11111111.md)"))
        (self.priv / "files" / "33333333.md").write_text(_priv_file("33333333", title="R"))
        _git(["init", "-q", "-b", "main", "."], cwd=self.priv)
        _git(["add", "-A"], cwd=self.priv)
        _git(["commit", "-qm", "seed private"], cwd=self.priv)

        # team canonical (bare) with a base commit
        self.team_bare = ght.init_bare_remote(self.d / "team.git")
        seed = self.d / "seed"
        _git(["clone", "-q", self.team_bare, str(seed)])
        (seed / "README.md").write_text("team canonical\n")
        _git(["add", "-A"], cwd=seed)
        _git(["commit", "-qm", "team base"], cwd=seed)
        _git(["push", "-q", self.team_bare, "main"], cwd=seed)

        # destination studio clone + receipts repo
        self.dest_clone = self.d / "dest_clone"
        _git(["clone", "-q", self.team_bare, str(self.dest_clone)])
        self.receipts_bare = rref.init_bare_receipts_repo(self.d / "receipts.git")
        self.receipts = rref.ReceiptRefClient(self.receipts_bare, authorized_writers={WRITER: WKEY})

    def tearDown(self):
        self._tmp.cleanup()

    # -- helpers -------------------------------------------------------------
    def _fresh_team_clone(self, name="tc"):
        clone = self.d / name
        _git(["clone", "-q", self.team_bare, str(clone)])
        tip = _git(["rev-parse", "HEAD"], cwd=clone).stdout.strip()
        return clone, tip

    def _plan_ready(self, uid, destination):
        graph = {uid: rc.GraphNode(uid, "v1", False, ())}
        plan = svc.plan_changeset(self.priv, VAULT, selection=[uid], destination=destination,
                                  target_audience="aud00001", graph=graph, actor="talos", asof="T")
        svc.validate_changeset(self.priv, VAULT, plan.changeset_uid, actor="talos", asof="T")
        svc.request_assent(self.priv, VAULT, plan.changeset_uid, actor="mike", asof="T")
        svc.record_assent(self.priv, VAULT, plan.changeset_uid, assented_by="mike", asof="T")
        return plan

    def _promo_ctx(self, team_clone, tip):
        return svc.PromotionContext(private_repo=self.priv, team_clone=team_clone,
                                    transport=ght.GitHubTransport(self.team_bare),
                                    team_scope="team-mktg", expected_tip=tip)

    def _recon_ctx(self):
        return svc.ReconcileContext(destination_clone=self.dest_clone, team_remote=self.team_bare,
                                    receipts=self.receipts, writer_instance_uid=WRITER,
                                    writer_key=WKEY, source_attestation_hash="att-src-1")


# ── P1: atomic promotion + fault-injection + no orphaned refs ────────────────
class TestP1AtomicPromotion(D5Fixture):
    def test_clean_promotion_no_orphaned_refs(self):
        plan = self._plan_ready("11111111", "studio-beta")
        tc, tip = self._fresh_team_clone()
        svc.publish_changeset(self.priv, VAULT, plan.changeset_uid, actor="talos", asof="T",
                              promotion=self._promo_ctx(tc, tip))
        team_uid = self._promo_ctx(tc, tip).remap("11111111")
        # write-to-team: the promoted artifact exists team-side with team scope.
        team_text = (tc / "files" / f"{team_uid}.md").read_text()
        self.assertIn(f"uid: {team_uid}", team_text)
        self.assertIn("extraction_scope: team-mktg", team_text)
        # original redirect: no half-promoted state, the source points forward.
        redirect = (self.priv / "files" / "11111111.md").read_text()
        self.assertIn(f"redirect_to: {team_uid}", redirect)
        self.assertIn("type: redirect", redirect)
        # ZERO orphaned refs: the referencing private file now points to team_uid.
        q = (self.priv / "files" / "22222222.md").read_text()
        self.assertNotIn("11111111", q)
        self.assertIn(team_uid, q)

    def test_fault_injection_every_step_single_clean_outcome(self):
        for step in ["write-to-team", "pushed", "cas", "fixup"]:
            with self.subTest(step=step):
                # a fresh vault per step so the crash/retry is isolated
                self.setUp()
                plan = self._plan_ready("11111111", "studio-beta")
                tc, tip = self._fresh_team_clone(f"tc-{step}")
                promo = self._promo_ctx(tc, tip)
                with self.assertRaises(svc.PromotionFault):
                    svc.publish_changeset(self.priv, VAULT, plan.changeset_uid,
                                          actor="talos", asof="T", promotion=promo, fault_after=step)
                # retry resumes from journal + progress evidence
                svc.publish_changeset(self.priv, VAULT, plan.changeset_uid, actor="talos", asof="T", promotion=promo)
                state = svc.get_publish_job(self.priv, VAULT, plan.job_uid)["state"]
                self.assertEqual(state, "awaiting-receipt")
                # single clean outcome: exactly ONE promotion commit (no duplicate node)
                team_commits = len(_git(["log", "--oneline"], cwd=tc).stdout.strip().splitlines())
                self.assertEqual(team_commits, 2)  # base + one promotion
                # remote == exact candidate; redirect present (fixup completed)
                candidate = _git(["rev-parse", "HEAD"], cwd=tc).stdout.strip()
                self.assertEqual(ght.GitHubTransport(self.team_bare).remote_tip(), candidate)
                self.assertIn("redirect_to", (self.priv / "files" / "11111111.md").read_text())


# ── P2: protected-ref compare-and-swap ───────────────────────────────────────
class TestP2ProtectedRefCAS(D5Fixture):
    def test_two_studios_race_one_winner(self):
        plan_a = self._plan_ready("11111111", "studio-beta")
        plan_b = self._plan_ready("33333333", "studio-gamma")
        tc_a, tip = self._fresh_team_clone("tc-a")
        tc_b, _ = self._fresh_team_clone("tc-b")  # both cloned at the SAME tip
        # A integrates first.
        svc.publish_changeset(self.priv, VAULT, plan_a.changeset_uid, actor="talos", asof="T",
                              promotion=self._promo_ctx(tc_a, tip))
        self.assertEqual(svc.get_publish_job(self.priv, VAULT, plan_a.job_uid)["state"], "awaiting-receipt")
        # B built on the now-stale tip → its candidate is a sibling → CAS loses.
        svc.publish_changeset(self.priv, VAULT, plan_b.changeset_uid, actor="talos", asof="T",
                              promotion=self._promo_ctx(tc_b, tip))
        b = svc.get_publish_job(self.priv, VAULT, plan_b.job_uid)
        self.assertEqual(b["state"], pj.BLOCKED)
        self.assertEqual(b["error"], "REMOTE_CAS_FAILED")
        self.assertEqual(b["resumable_from"], "ready")

    def test_host_rewrite_refused(self):
        tc, tip = self._fresh_team_clone("tc")
        (tc / "x.md").write_text("candidate\n"); _git(["add", "-A"], cwd=tc); _git(["commit", "-qm", "cand"], cwd=tc)
        candidate = _git(["rev-parse", "HEAD"], cwd=tc).stdout.strip()
        T = ght.GitHubTransport(self.team_bare)
        T.cas_advance(tc, expected_tip=tip, candidate_sha=candidate)
        # host squashes/rewrites the ref out of band → exact-sha check refuses.
        h, _ = self._fresh_team_clone("h")
        _git(["reset", "--hard", tip], cwd=h)
        (h / "y.md").write_text("host-squash\n"); _git(["add", "-A"], cwd=h); _git(["commit", "-qm", "squash"], cwd=h)
        squashed = _git(["rev-parse", "HEAD"], cwd=h).stdout.strip()
        _git(["push", "--force", self.team_bare, f"{squashed}:refs/heads/main"], cwd=h)
        with self.assertRaises(ght.RemoteIntegrationError) as ctx:
            T.verify_integrated(tc, candidate)
        self.assertEqual(ctx.exception.code, "REMOTE_CHECK_FAILED")

    def test_stale_plan_when_candidate_not_built_on_pinned_tip(self):
        tc, tip = self._fresh_team_clone("tc")
        # a divergent commit the candidate does NOT descend from
        div, _ = self._fresh_team_clone("div")
        _git(["checkout", "-q", "-b", "diverge"], cwd=div)
        (div / "z.md").write_text("divergent\n"); _git(["add", "-A"], cwd=div); _git(["commit", "-qm", "div"], cwd=div)
        divergent = _git(["rev-parse", "HEAD"], cwd=div).stdout.strip()
        (tc / "c.md").write_text("cand\n"); _git(["add", "-A"], cwd=tc); _git(["commit", "-qm", "c"], cwd=tc)
        candidate = _git(["rev-parse", "HEAD"], cwd=tc).stdout.strip()
        # candidate is a child of `tip`, not of `divergent` → STALE_PLAN.
        # bring the divergent commit into tc's object store so is-ancestor can run.
        _git(["fetch", "-q", str(div), "diverge"], cwd=tc)
        with self.assertRaises(ght.RemoteIntegrationError) as ctx:
            ght.GitHubTransport(self.team_bare).cas_advance(tc, expected_tip=divergent, candidate_sha=candidate)
        self.assertEqual(ctx.exception.code, "STALE_PLAN")


# ── P3: landed = local reconcile only ────────────────────────────────────────
class TestP3LandedLocalOnly(D5Fixture):
    def test_integrated_stays_publishing_until_reconcile(self):
        plan = self._plan_ready("11111111", "studio-beta")
        tc, tip = self._fresh_team_clone()
        svc.publish_changeset(self.priv, VAULT, plan.changeset_uid, actor="talos", asof="T",
                              promotion=self._promo_ctx(tc, tip))
        # integrated + awaiting the destination receipt, but NOT landed.
        overlay = svc.overlay_for_changeset(self.priv, VAULT, "argo-private", plan.changeset_uid)
        self.assertEqual(overlay["draftStatus"], ds.PUBLISHING)
        self.assertNotEqual(overlay["draftStatus"], ds.PUBLISHED)

    def test_optimistic_remote_integrated_to_landed_is_illegal(self):
        with self.assertRaises(svc.IllegalTransition):
            svc.assert_transition("remote-integrated", "landed")

    def test_reconcile_lands_and_writes_receipt(self):
        plan = self._plan_ready("11111111", "studio-beta")
        tc, tip = self._fresh_team_clone()
        svc.publish_changeset(self.priv, VAULT, plan.changeset_uid, actor="talos", asof="T",
                              promotion=self._promo_ctx(tc, tip))
        svc.reconcile_destination(self.priv, VAULT, plan.job_uid, "studio-beta", "rep1",
                                  actor="talos", asof="T", reconcile=self._recon_ctx())
        self.assertEqual(svc.get_publish_job(self.priv, VAULT, plan.job_uid)["state"], "landed")
        self.assertEqual(len(self.receipts.read_receipts(WRITER)), 1)
        self.assertEqual(
            svc.overlay_for_changeset(self.priv, VAULT, "argo-private", plan.changeset_uid)["draftStatus"],
            ds.PUBLISHED)

    def test_destination_A_landing_does_not_flip_destination_B(self):
        # csA → studio-beta: integrate + reconcile to `landed` (terminal) FIRST,
        # so it is not an in-flight same-vault job when csB plans (the
        # OVERLAPPING_CHANGESET guard serialises concurrent same-vault publishes).
        plan_a = self._plan_ready("11111111", "studio-beta")
        tc_a, tip_a = self._fresh_team_clone("tc-a")
        svc.publish_changeset(self.priv, VAULT, plan_a.changeset_uid, actor="talos", asof="T",
                              promotion=self._promo_ctx(tc_a, tip_a))
        svc.reconcile_destination(self.priv, VAULT, plan_a.job_uid, "studio-beta", "repA",
                                  actor="talos", asof="T", reconcile=self._recon_ctx())
        # csB → studio-gamma: integrate but do NOT reconcile.
        plan_b = self._plan_ready("33333333", "studio-gamma")
        tc_b, tip_b = self._fresh_team_clone("tc-b")
        svc.publish_changeset(self.priv, VAULT, plan_b.changeset_uid, actor="talos", asof="T",
                              promotion=self._promo_ctx(tc_b, tip_b))
        a = svc.overlay_for_changeset(self.priv, VAULT, "argo-private", plan_a.changeset_uid)
        b = svc.overlay_for_changeset(self.priv, VAULT, "argo-private", plan_b.changeset_uid)
        self.assertEqual(a["draftStatus"], ds.PUBLISHED)     # beta landed
        self.assertEqual(b["draftStatus"], ds.PUBLISHING)    # gamma integrated, not landed


# ── P4: receipt-ref stream (append-only single-parent CAS, non-recursive) ────
class TestP4ReceiptRef(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = rref.init_bare_receipts_repo(Path(self._tmp.name) / "receipts.git")
        self.client = rref.ReceiptRefClient(self.repo, authorized_writers={WRITER: WKEY})

    def tearDown(self):
        self._tmp.cleanup()

    def _payload(self, commit):
        return {"payload_type": rref.RECONCILIATION_TYPE, "destination": "studio-beta",
                "replica": "rep1", "integrated_commit": commit, "result_tree_hash": "t" + commit,
                "source_attestation_hash": "att", "writer": WRITER}

    def test_append_and_read_single_parent_chain(self):
        self.client.append_receipt(WRITER, self._payload("aaa"), presented_key=WKEY)
        self.client.append_receipt(WRITER, self._payload("bbb"), presented_key=WKEY)
        stream = self.client.read_receipts(WRITER)
        self.assertEqual([r["integrated_commit"] for r in stream], ["aaa", "bbb"])

    def test_forged_writer_refused(self):
        with self.assertRaises(rref.ReceiptError) as ctx:
            self.client.append_receipt("evil0000", self._payload("ccc"), presented_key="x")
        self.assertEqual(ctx.exception.code, "RECEIPT_REF_FAILED")

    def test_wrong_key_refused(self):
        with self.assertRaises(rref.ReceiptError) as ctx:
            self.client.append_receipt(WRITER, self._payload("ddd"), presented_key="wrong")
        self.assertEqual(ctx.exception.code, "RECEIPT_REF_FAILED")

    def test_replay_refused(self):
        self.client.append_receipt(WRITER, self._payload("aaa"), presented_key=WKEY)
        with self.assertRaises(rref.ReceiptError) as ctx:
            self.client.append_receipt(WRITER, self._payload("aaa"), presented_key=WKEY)
        self.assertEqual(ctx.exception.code, "RECEIPT_INVALID")

    def test_receipt_of_receipt_refused(self):
        rec = self._payload("eee"); rec["subject"] = {"kind": "receipt", "ref": "refs/tropo/receipts/x"}
        with self.assertRaises(rref.ReceiptError) as ctx:
            self.client.append_receipt(WRITER, rec, presented_key=WKEY)
        self.assertEqual(ctx.exception.code, "RECEIPT_INVALID")

    def test_cas_race_refused(self):
        stale = self.client.tip(WRITER)  # None
        self.client.append_receipt(WRITER, self._payload("aaa"), presented_key=WKEY)  # advances tip
        with self.assertRaises(rref.ReceiptError) as ctx:
            self.client.append_receipt(WRITER, self._payload("bbb"), presented_key=WKEY,
                                       expected_parent=stale or rref.ZERO_OID)
        self.assertEqual(ctx.exception.code, "RECEIPT_REF_FAILED")

    def test_content_address_tamper_detected(self):
        self.client.append_receipt(WRITER, self._payload("aaa"), presented_key=WKEY)
        # tamper the stored blob: rewrite the ref's receipt content, keep the id
        tip = self.client.tip(WRITER)
        blob = ght.run_git(["cat-file", "-p", f"{tip}:receipt.json"], git_dir=self.repo).stdout
        forged = blob.replace('"aaa"', '"zzz"')  # content changes, receipt_id no longer matches
        new_blob = ght.run_git(["hash-object", "-w", "--stdin"], git_dir=self.repo, input_text=forged).stdout.strip()
        tree = ght.run_git(["mktree"], git_dir=self.repo, input_text=f"100644 blob {new_blob}\treceipt.json\n").stdout.strip()
        commit = ght.run_git(["commit-tree", tree, "-m", "tamper"], git_dir=self.repo).stdout.strip()
        ght.run_git(["update-ref", f"refs/tropo/receipts/{WRITER}", commit], git_dir=self.repo)
        with self.assertRaises(rref.ReceiptError) as ctx:
            self.client.read_receipts(WRITER)
        self.assertEqual(ctx.exception.code, "RECEIPT_INVALID")


# ── P5: closed error enum + supersede ────────────────────────────────────────
class TestP5ClosedEnumSupersede(D5Fixture):
    def _integrate(self, uid="11111111", dest="studio-beta"):
        plan = self._plan_ready(uid, dest)
        tc, tip = self._fresh_team_clone()
        svc.publish_changeset(self.priv, VAULT, plan.changeset_uid, actor="talos", asof="T",
                              promotion=self._promo_ctx(tc, tip))
        return plan

    def test_reconcile_failed_is_closed_code_with_resumable_from(self):
        plan = self._integrate()
        # tamper the integrated sha so the destination integrity check fails
        prog = svc._read_progress(self.priv, plan.changeset_uid)
        prog["integrated_sha"] = "0" * 40
        svc._write_progress(self.priv, plan.changeset_uid, prog)
        svc.reconcile_destination(self.priv, VAULT, plan.job_uid, "studio-beta", "rep1",
                                  actor="talos", asof="T", reconcile=self._recon_ctx())
        st = svc.get_publish_job(self.priv, VAULT, plan.job_uid)
        self.assertEqual(st["state"], pj.BLOCKED)
        self.assertEqual(st["error"], "RECONCILE_FAILED")
        self.assertEqual(st["resumable_from"], "awaiting-receipt")
        self.assertIn(st["error"], pj.CLOSED_ERROR_ENUM)

    def test_superseded_before_reconcile_is_terminal_not_landed(self):
        plan = self._integrate()
        svc.reconcile_destination(self.priv, VAULT, plan.job_uid, "studio-beta", "rep1",
                                  actor="talos", asof="T", reconcile=self._recon_ctx(), superseded=True)
        recs = pj.read_records(self.priv, VAULT)
        # the SOURCE per-destination row never reached landed
        src = pj.current_row_record(recs, "studio-beta", plan.included_nodes)
        self.assertEqual(src["state"], "awaiting-receipt")
        # the receiver row records the terminal not-landed outcome
        recv = pj.current_row_record(recs, "recv:studio-beta:rep1", plan.included_nodes)
        self.assertEqual(recv["state"], "superseded-before-reconcile")

    def test_landed_then_superseded_is_distinguished(self):
        plan = self._integrate()
        svc.reconcile_destination(self.priv, VAULT, plan.job_uid, "studio-beta", "rep1",
                                  actor="talos", asof="T", reconcile=self._recon_ctx())
        self.assertEqual(svc.get_publish_job(self.priv, VAULT, plan.job_uid)["state"], "landed")
        st = svc.mark_landed_then_superseded(self.priv, VAULT, plan.job_uid, "studio-beta",
                                             actor="talos", asof="T")
        self.assertEqual(st["state"], "landed-then-superseded")
        self.assertNotEqual(st["state"], "superseded-before-reconcile")

    def test_unknown_error_code_is_hard_failure(self):
        with self.assertRaises(pj.PublishJournalValidationError):
            pj.append_transition(self.priv, VAULT, job_uid="00000009", changeset_uid="cs000001",
                                 destination="studio-beta", path_set=("11111111",), state=pj.BLOCKED,
                                 actor="t", asof="T", error="NOT_A_REAL_CODE", resumable_from="pushed")

    def test_every_d5_error_code_is_in_the_closed_enum(self):
        self.assertTrue(svc.D5_ONLY_ERROR_CODES <= pj.CLOSED_ERROR_ENUM)


# ── P6: GitHub governance gate ───────────────────────────────────────────────
class TestP6GitHubGate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        (self.d / "files").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, text):
        p = self.d / "files" / name
        p.write_text(text)
        return p

    def test_clean_governed_file_passes(self):
        p = self._write("aaaa1111.md", "---\nuid: aaaa1111\ntype: note\ntitle: \"Ok\"\nowner: mike\n---\nbody\n")
        self.assertEqual(gg.validate_paths([p])[0][1], "VALID")

    def test_broken_files_blocked(self):
        plants = {
            "dup-key": "---\nuid: bbbb2222\ntype: note\ntitle: \"D\"\nowner: mike\nuid: x\n---\nb\n",
            "marker-in-frontmatter": "---\nuid: cccc3333\ntype: note\ntitle: \"M\"\nowner: mike\n<<<<<<< HEAD\n---\nb\n",
            "missing-required-key": "---\nuid: dddd4444\ntype: note\ntitle: \"N\"\n---\nb\n",
            "empty-body": "---\nuid: eeee5555\ntype: note\ntitle: \"E\"\nowner: mike\n---\n\n",
        }
        for name, text in plants.items():
            with self.subTest(plant=name):
                p = self._write(f"{name.replace('-', '')[:8]}.md", text)
                with self.assertRaises(gg.GovernanceBlocked):
                    gg.validate_paths([p])

    def test_pre_commit_hook_absence_detected_and_refused(self):
        repo = self.d / "repo"
        (repo / "files").mkdir(parents=True)
        ght.run_git(["init", "-q", "-b", "main", "."], cwd=repo)
        with self.assertRaises(gg.GateNotInstalled):
            gg.assert_hook_installed(repo)
        gg.install_hook(repo)
        gg.assert_hook_installed(repo)  # now accepted, not silently skipped


# ── P7: end-to-end + cold-boot ───────────────────────────────────────────────
class TestP7EndToEndColdBoot(D5Fixture):
    def test_full_walk_and_rebuild_reproduces_landed(self):
        plan = self._plan_ready("11111111", "studio-beta")
        tc, tip = self._fresh_team_clone()
        # plan → validate → assent (done) → publish (CAS integrate) → reconcile (receipt) → landed
        svc.publish_changeset(self.priv, VAULT, plan.changeset_uid, actor="talos", asof="T",
                              promotion=self._promo_ctx(tc, tip))
        svc.reconcile_destination(self.priv, VAULT, plan.job_uid, "studio-beta", "rep1",
                                  actor="talos", asof="T", reconcile=self._recon_ctx())
        before = svc.overlay_for_changeset(self.priv, VAULT, "argo-private", plan.changeset_uid)
        self.assertEqual(before["draftStatus"], ds.PUBLISHED)
        self.assertEqual(svc.get_publish_job(self.priv, VAULT, plan.job_uid)["state"], "landed")

        # COLD-BOOT: a full index rebuild blows away every DERIVED surface but
        # NEVER the durable journal or the receipt-refs. Re-read both from disk
        # (fresh clients) → identical landed state + the same receipt.
        cold_records = pj.read_records(self.priv, VAULT)
        after = ds.resolve_row("argo-private", cold_records,
                               destination="studio-beta", path_set=plan.included_nodes)
        self.assertEqual(after["draftStatus"], before["draftStatus"])
        self.assertEqual(after["jobId"], plan.job_uid)
        cold_receipts = rref.ReceiptRefClient(self.receipts_bare, authorized_writers={WRITER: WKEY})
        stream = cold_receipts.read_receipts(WRITER)
        self.assertEqual(len(stream), 1)
        self.assertEqual(stream[0]["changeset_uid"], plan.changeset_uid)


if __name__ == "__main__":
    unittest.main()
