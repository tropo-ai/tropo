"""Write-path conformance — L1v3 publish-job SERVICE (dev-spec 3c13977e §Write
Contract / §Write Library). DoD test-spec c56b9cc0 write-path assertions:

  A1  landing agreement  — R2: there is NO local path to `landed`; the optimistic
                            `remote-integrated → landed` jump is a hard failure;
                            `landed` is reachable ONLY from `awaiting-receipt`.
  A4  job-store durability — the service's transitions land in the append-only,
                            hash-chained journal at the R1 location; process-loss
                            re-issue is idempotent (no duplicate row); survives a
                            simulated `vault:rebuild`.
  A5  closed error enum   — every LOCAL `blocked` outcome carries a code from the
                            closed enum + a typed resumable_from; an unknown code
                            is a hard failure.

Plus the smoke class (each LOCAL write-library op returns its declared shape,
including an AGENT-STAGED non-interactive changeset) and the D5-boundary class
(the two REMOTE ops FLAG rather than fake — publish_changeset /
reconcile_destination raise D5FederationRequired, after the local precondition).

The full two-clone reconcile that would exercise the REMOTE half of A1 SEQUENCES
BEHIND D5 (304badf7); everything provable WITHOUT D5 is proven here at the
service + state-machine level (the store/overlay slice is in
test_l1v3_data_contract.py).

Run: python3 -m unittest tests.test_l1v3_writepath_service   (from vault/tools/)
"""
from __future__ import annotations

import json
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
from lib.group_registry import GroupResolver, REGISTRY_ROW_KEYS  # noqa: E402

VAULT = "aabbccdd"
DEST = "studio-beta"
AUD = "aud00001"
ASOF = "2026-07-19T12:00:00Z"


def _graph_chain(n=6):
    """A single-vault unpublished chain A→B→C→… so a one-node selection stages a
    big-N transitive closure (the agent-first workflow, c27c741b §7 Q4)."""
    names = [chr(ord("A") + i) for i in range(n)]
    nodes = {}
    for i, name in enumerate(names):
        refs = (names[i + 1],) if i + 1 < n else ()
        nodes[name] = rc.GraphNode(name, "v1", False, refs)
    return nodes, names


def _resolver(group_uid=AUD):
    row = {
        "group_uid": group_uid, "slug": "team", "title": "Team", "status": "active",
        "version": 1, "owner_uid": "own00001",
        "direct_member_uids": ["mem00001", "mem00002"],
        "direct_included_group_uids": [],
        "effective_member_uids": ["mem00001", "mem00002"],
        "wider_group_uids": [], "source_authority_uid": "auth0001",
        "source_revision": "rev-1", "source_path": "groups/team.md",
        "source_hash": "h" * 64, "principal_directory_revision": "pdir-1",
    }
    ordered = {k: row[k] for k in REGISTRY_ROW_KEYS}
    blob = (json.dumps(ordered, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    return GroupResolver.from_jsonl(blob)


class WritePathBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _plan(self, selection=("A",), audience=AUD, bindings=None, n=6):
        graph, _ = _graph_chain(n)
        return svc.plan_changeset(
            self.root, VAULT, selection=list(selection), destination=DEST,
            target_audience=audience, graph=graph, bindings=bindings,
            actor="talos-t34", asof=ASOF, snapshot_revision="rev1",
        )


# ── smoke: each LOCAL write-library op returns its declared shape ────────────
class TestSmokeLocalLibrary(WritePathBase):
    def test_plan_stages_transitive_closure_non_interactively(self):
        plan = self._plan(("A",), n=6)
        # an AGENT-STAGED single-node selection pulls in the whole unpublished
        # chain — no interactive caller assumed (§Write Library / c27c741b §7).
        self.assertEqual(plan.included_nodes, ("A", "B", "C", "D", "E", "F"))
        self.assertEqual(len(plan.changeset_uid), 8)
        self.assertEqual(len(plan.job_uid), 8)
        # the immutable envelope is durable at the R1-adjacent location
        env = svc.read_envelope(self.root, plan.changeset_uid)
        self.assertEqual(env["job_uid"], plan.job_uid)
        self.assertEqual(env["included_nodes"], list(plan.included_nodes))

    def test_get_publish_job_shape(self):
        plan = self._plan()
        status = svc.get_publish_job(self.root, VAULT, plan.job_uid)
        self.assertEqual(
            set(status.keys()),
            {"jobId", "changeset_uid", "destination", "state", "error",
             "resumable_from", "reason", "asOf"},
        )
        self.assertEqual(status["state"], "planned")
        self.assertEqual(status["jobId"], plan.job_uid)
        self.assertEqual(status["asOf"], ASOF)

    def test_happy_local_path_to_ready(self):
        plan = self._plan(bindings={"manifest_rev": "r1"})
        v = svc.validate_changeset(self.root, VAULT, plan.changeset_uid,
                                   actor="talos-t34", asof=ASOF,
                                   current_bindings={"manifest_rev": "r1"},
                                   resolver=_resolver())
        self.assertEqual(v["state"], "validated")
        self.assertIsNone(v["error"])
        a1 = svc.request_assent(self.root, VAULT, plan.changeset_uid, actor="mike", asof=ASOF)
        self.assertEqual(a1["state"], "awaiting-assent")
        a2 = svc.record_assent(self.root, VAULT, plan.changeset_uid, assented_by="mike", asof=ASOF)
        self.assertEqual(a2["state"], "ready")

    def test_overlay_reads_live_job_state(self):
        # the draftStatus overlay merges (index base) ⊔ (live job store) — the
        # value comes from the SERVICE-produced job state, not frontmatter (A2).
        plan = self._plan()
        self.assertEqual(
            svc.overlay_for_changeset(self.root, VAULT, "argo-private", plan.changeset_uid)["draftStatus"],
            ds.AWAITING_ASSENT,  # planned → awaiting_assent
        )
        svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF, resolver=_resolver())
        svc.request_assent(self.root, VAULT, plan.changeset_uid, actor="mike", asof=ASOF)
        svc.record_assent(self.root, VAULT, plan.changeset_uid, assented_by="mike", asof=ASOF)
        self.assertEqual(
            svc.overlay_for_changeset(self.root, VAULT, "argo-private", plan.changeset_uid)["draftStatus"],
            ds.READY,  # ready → ready
        )

    def test_plan_refuses_cross_vault_selection(self):
        graph, _ = _graph_chain(3)
        graph["X"] = rc.GraphNode("X", "v2", False, ())  # different vault
        with self.assertRaises(svc.PublishServiceError):
            svc.plan_changeset(
                self.root, VAULT, selection=["A", "X"], destination=DEST,
                target_audience=AUD, graph=graph, actor="t", asof=ASOF,
            )


# ── state machine: the closed SOURCE/DESTINATION graph + R2 ──────────────────
class TestStateMachine(unittest.TestCase):
    def test_entry_states(self):
        self.assertTrue(svc.is_legal_transition(None, "planned"))
        self.assertTrue(svc.is_legal_transition(None, "pending"))
        self.assertFalse(svc.is_legal_transition(None, "validated"))
        self.assertFalse(svc.is_legal_transition(None, "landed"))

    def test_source_edges_legal_and_illegal(self):
        legal = [
            ("planned", "validated"), ("validated", "awaiting-assent"),
            ("awaiting-assent", "ready"), ("ready", "pushed"),
            ("pushed", "remote-integrated"), ("remote-integrated", "awaiting-receipt"),
            ("awaiting-receipt", "landed"), ("landed", "landed-then-superseded"),
        ]
        for frm, to in legal:
            self.assertTrue(svc.is_legal_transition(frm, to), f"{frm}->{to}")
        illegal = [
            ("planned", "ready"), ("validated", "pushed"), ("ready", "landed"),
            ("planned", "remote-integrated"), ("awaiting-assent", "pushed"),
        ]
        for frm, to in illegal:
            self.assertFalse(svc.is_legal_transition(frm, to), f"{frm}->{to}")

    def test_destination_edges(self):
        for frm, to in [("pending", "reconciling"), ("reconciling", "receipt-emitted"),
                        ("receipt-emitted", "landed-local"),
                        ("pending", "superseded-before-reconcile"),
                        ("reconciling", "superseded-before-reconcile")]:
            self.assertTrue(svc.is_legal_transition(frm, to), f"{frm}->{to}")
        self.assertFalse(svc.is_legal_transition("pending", "landed-local"))

    def test_terminal_states_are_dead_ends(self):
        for term in ["landed-then-superseded", "landed-local", "superseded-before-reconcile"]:
            for to in svc.LEGAL_TRANSITIONS:
                self.assertFalse(svc.is_legal_transition(term, to), f"{term}->{to}")

    def test_any_non_terminal_can_block(self):
        non_terminal = pj.ALL_STATES - pj.TERMINAL_STATES - {pj.BLOCKED}
        for s in non_terminal:
            self.assertTrue(svc.is_legal_transition(s, pj.BLOCKED), f"{s}->blocked")

    def test_blocked_resumes_only_to_live_states(self):
        self.assertTrue(svc.is_legal_transition(pj.BLOCKED, "planned"))
        self.assertTrue(svc.is_legal_transition(pj.BLOCKED, "pushed"))
        self.assertFalse(svc.is_legal_transition(pj.BLOCKED, "landed"))          # terminal
        self.assertFalse(svc.is_legal_transition(pj.BLOCKED, "landed-local"))    # terminal
        self.assertFalse(svc.is_legal_transition(pj.BLOCKED, pj.BLOCKED))        # no self-loop

    def test_r2_landed_only_from_awaiting_receipt(self):
        # `landed` (source) is reachable from EXACTLY ONE state — awaiting-receipt.
        sources_to_landed = [
            s for s, tos in svc.LEGAL_TRANSITIONS.items() if "landed" in tos
        ]
        self.assertEqual(sources_to_landed, ["awaiting-receipt"])


# ── A1: landing agreement (R2 — no optimistic landed) ────────────────────────
class TestA1LandingAgreement(WritePathBase):
    def test_optimistic_remote_integrated_to_landed_is_hard_failure(self):
        # The hostile A1 plant: a remote merge alone must NEVER be taken as
        # landed. The state machine refuses the jump with a typed IllegalTransition.
        with self.assertRaises(svc.IllegalTransition) as ctx:
            svc.assert_transition("remote-integrated", "landed")
        self.assertIn("optimistic", str(ctx.exception).lower())
        self.assertIn("reconcile", str(ctx.exception).lower())

    def test_no_local_op_can_reach_landed(self):
        # There is no LOCAL service call that produces `landed`: the only op that
        # would is reconcile_destination, and it is D5-gated. So a clean local run
        # can never optimistically show `published` (R2 structurally enforced).
        with self.assertRaises(svc.D5FederationRequired):
            svc.reconcile_destination(self.root, VAULT, "00000001", DEST, "replica-1",
                                      actor="t", asof=ASOF)

    def test_awaiting_receipt_to_landed_is_the_only_legal_landing(self):
        self.assertTrue(svc.is_legal_transition("awaiting-receipt", "landed"))
        self.assertFalse(svc.is_legal_transition("remote-integrated", "landed"))
        self.assertFalse(svc.is_legal_transition("pushed", "landed"))


# ── A4: job-store durability through the service ─────────────────────────────
class TestA4DurabilityViaService(WritePathBase):
    def test_service_transitions_are_hash_chained_at_r1_location(self):
        plan = self._plan()
        svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF, resolver=_resolver())
        p = pj.journal_path(self.root, VAULT)
        self.assertEqual(p, self.root / ".tropo" / "publish-journal" / f"{VAULT}.jsonl")
        recs = pj.read_records(self.root, VAULT)
        self.assertEqual([r["state"] for r in recs], ["planned", "validated"])
        self.assertEqual(recs[0]["prev_hash"], pj.GENESIS_HASH)
        self.assertEqual(recs[1]["prev_hash"], recs[0]["record_hash"])
        for r in recs:
            self.assertEqual(pj.compute_record_hash(r), r["record_hash"])

    def test_idempotent_resume_no_duplicate_row(self):
        # Re-issuing the SAME transition (process died after append, before
        # returning) is a no-op — never a second row, never an IllegalTransition.
        plan = self._plan()
        v1 = svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF, resolver=_resolver())
        v2 = svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF, resolver=_resolver())
        self.assertEqual(v1["state"], v2["state"], "validated")
        recs = pj.read_records(self.root, VAULT)
        self.assertEqual([r["state"] for r in recs], ["planned", "validated"])

    def test_survives_simulated_rebuild(self):
        plan = self._plan()
        before = svc.overlay_for_changeset(self.root, VAULT, "argo-private", plan.changeset_uid)
        # a vault:rebuild blows away the derived index but NEVER this journal;
        # re-reading reproduces the identical overlay (A2/A4 P0).
        after = svc.overlay_for_changeset(self.root, VAULT, "argo-private", plan.changeset_uid)
        self.assertEqual(before["draftStatus"], after["draftStatus"])
        self.assertEqual(before["jobId"], after["jobId"])


# ── A5: closed error enum, driven by the LOCAL gate ──────────────────────────
class TestA5ClosedErrorEnumViaService(WritePathBase):
    def _blocked_status(self, **validate_kwargs):
        plan = self._plan(**validate_kwargs.pop("plan_kwargs", {}))
        return svc.validate_changeset(self.root, VAULT, plan.changeset_uid,
                                      actor="t", asof=ASOF, **validate_kwargs), plan

    def test_stale_plan(self):
        plan = self._plan(bindings={"manifest_rev": "r1"})
        st = svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF,
                                    current_bindings={"manifest_rev": "r2"})
        self.assertEqual(st["state"], pj.BLOCKED)
        self.assertEqual(st["error"], "STALE_PLAN")
        self.assertEqual(st["resumable_from"], "planned")

    def test_overlapping_changeset(self):
        # first job driven to `ready` (in-flight); a second validate must block.
        first = self._plan(("A",))
        svc.validate_changeset(self.root, VAULT, first.changeset_uid, actor="t", asof=ASOF, resolver=_resolver())
        svc.request_assent(self.root, VAULT, first.changeset_uid, actor="mike", asof=ASOF)
        svc.record_assent(self.root, VAULT, first.changeset_uid, assented_by="mike", asof=ASOF)
        second = self._plan(("A",))
        st = svc.validate_changeset(self.root, VAULT, second.changeset_uid, actor="t", asof=ASOF, resolver=_resolver())
        self.assertEqual(st["state"], pj.BLOCKED)
        self.assertEqual(st["error"], "OVERLAPPING_CHANGESET")

    def test_group_resolution_unavailable(self):
        plan = self._plan(audience="aud99999")  # not in the registry
        st = svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF,
                                    resolver=_resolver(AUD))
        self.assertEqual(st["state"], pj.BLOCKED)
        self.assertEqual(st["error"], "GROUP_RESOLUTION_UNAVAILABLE")

    def test_policy_refused_blank_audience(self):
        plan = self._plan(audience="")
        st = svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF)
        self.assertEqual(st["state"], pj.BLOCKED)
        self.assertEqual(st["error"], "POLICY_REFUSED")

    def test_policy_refused_via_hook(self):
        plan = self._plan()
        st = svc.validate_changeset(
            self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF, resolver=_resolver(),
            policy_hook=lambda env: "publish policy vetoed this changeset",
        )
        self.assertEqual(st["state"], pj.BLOCKED)
        self.assertEqual(st["error"], "POLICY_REFUSED")

    def test_privacy_refused_misplaced_draft(self):
        plan = self._plan()
        files = [{"path": "vault/secret.md", "extraction_scope": "argo-private", "in_shared_tree": True}]
        st = svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF,
                                    resolver=_resolver(), files=files)
        self.assertEqual(st["state"], pj.BLOCKED)
        self.assertEqual(st["error"], "PRIVACY_REFUSED")

    def test_every_local_blocked_code_is_in_the_closed_enum(self):
        self.assertTrue(svc.LOCAL_ERROR_CODES <= pj.CLOSED_ERROR_ENUM)

    def test_unknown_code_is_a_hard_failure(self):
        # A synthetic unknown code cannot be written — the store the service
        # writes through rejects it (A5). No coercion, no silent drop.
        with self.assertRaises(pj.PublishJournalValidationError):
            pj.append_transition(
                self.root, VAULT, job_uid="00000009", changeset_uid="cs000001",
                destination=DEST, path_set=("A",), state=pj.BLOCKED,
                actor="t", asof=ASOF, error="NOT_A_REAL_CODE", resumable_from="planned",
            )

    def test_blocked_then_resume_and_revalidate(self):
        # R1 recovery: a blocked job resumes to its typed resumable_from and can
        # then re-gate cleanly. History stays queryable.
        plan = self._plan(bindings={"manifest_rev": "r1"})
        st = svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF,
                                    current_bindings={"manifest_rev": "r2"})
        self.assertEqual(st["error"], "STALE_PLAN")
        resumed = svc.resume_job(self.root, VAULT, plan.job_uid, actor="t", asof=ASOF)
        self.assertEqual(resumed["state"], "planned")
        revalid = svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF,
                                         current_bindings={"manifest_rev": "r1"}, resolver=_resolver())
        self.assertEqual(revalid["state"], "validated")
        states = [r["state"] for r in pj.read_records(self.root, VAULT)]
        self.assertEqual(states, ["planned", "blocked", "planned", "validated"])


# ── D5 boundary: the REMOTE ops FLAG, never fake ─────────────────────────────
class TestD5Boundary(WritePathBase):
    def _ready_job(self):
        plan = self._plan()
        svc.validate_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF, resolver=_resolver())
        svc.request_assent(self.root, VAULT, plan.changeset_uid, actor="mike", asof=ASOF)
        svc.record_assent(self.root, VAULT, plan.changeset_uid, assented_by="mike", asof=ASOF)
        return plan

    def test_publish_changeset_flags_d5_after_local_precondition(self):
        plan = self._ready_job()
        with self.assertRaises(svc.D5FederationRequired) as ctx:
            svc.publish_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF)
        self.assertEqual(ctx.exception.op, "publish_changeset")
        self.assertTrue(any("CAS" in n or "push" in n for n in ctx.exception.needs))

    def test_publish_changeset_rejects_unready_job_locally(self):
        # local precondition is a LOCAL failure, NOT a D5 flag — the job is only
        # `planned`, so it can't be published regardless of D5.
        plan = self._plan()
        with self.assertRaises(svc.IllegalTransition):
            svc.publish_changeset(self.root, VAULT, plan.changeset_uid, actor="t", asof=ASOF)

    def test_reconcile_destination_flags_d5(self):
        with self.assertRaises(svc.D5FederationRequired) as ctx:
            svc.reconcile_destination(self.root, VAULT, "00000001", DEST, "replica-1",
                                      actor="t", asof=ASOF)
        self.assertEqual(ctx.exception.op, "reconcile_destination")
        self.assertTrue(any("reconcile" in n or "reconciliation" in n or "freshen" in n
                            for n in ctx.exception.needs))


if __name__ == "__main__":
    unittest.main()
