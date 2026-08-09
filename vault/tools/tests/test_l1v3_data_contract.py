"""Landing-Agreement Conformance Test — L1v3 Data Contract (dev-spec 3c13977e).

Executable coverage for test-spec c56b9cc0 (assertions A1–A8) over the READ-SIDE
substrate + the R1 publish-journal store, all buildable NOW (the publish
write-path / two-clone reconcile SEQUENCES BEHIND D5, 304badf7 — the parts of A1
that require the real reconcile service are marked and covered at the
store/state-machine level, which is what is provable without D5).

Coverage classes exercised (c56b9cc0 §Coverage classes):
  - smoke      — each read surface returns its declared shape;
  - property   — the full draftStatus matrix (A2) + ref-closure exclusion algebra (A6);
  - regression — rebuild-does-not-erase-job-state (A2/A4);
  - gauntlet   — process-loss / torn-tail / CAS (A4), unknown error code (A5),
                 cross-vault closure attempt (A6), optimistic-landed (A1),
                 hand-set segment write (A3);
  - cold-boot  — journal + derived reads reconstruct identical draftStatus + health.

Run: python3 -m unittest tests.test_l1v3_data_contract   (from vault/tools/)
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

from lib import publish_journal as pj  # noqa: E402
from lib import draft_status as ds  # noqa: E402
from lib import ref_closure as rc  # noqa: E402
from lib import l1v3_read_surface as rs  # noqa: E402
from lib.group_registry import GroupResolver, REGISTRY_ROW_KEYS  # noqa: E402

VAULT = "aabbccdd"
DEST_A = "studio-alpha"
DEST_B = "studio-beta"
ASOF = "2026-07-19T12:00:00Z"


def _append(root: Path, *, job, state, dest=DEST_A, path_set=("uid-1",),
            error=None, resumable_from=None, changeset="cs000001",
            expected_tip=None, asof=ASOF):
    return pj.append_transition(
        root, VAULT, job_uid=job, changeset_uid=changeset, destination=dest,
        path_set=path_set, state=state, actor="talos-t34", asof=asof,
        error=error, resumable_from=resumable_from, expected_tip=expected_tip,
    )


class TmpVault(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


# ── A4: job-store durability (R1) ───────────────────────────────────────────
class TestA4Durability(TmpVault):
    def test_append_only_hash_chained_and_located_correctly(self):
        _append(self.root, job="00000001", state="planned")
        _append(self.root, job="00000001", state="validated")
        p = pj.journal_path(self.root, VAULT)
        # located at .tropo/publish-journal/<vault_uid>.jsonl, OUTSIDE the index
        self.assertEqual(p, self.root / ".tropo" / "publish-journal" / f"{VAULT}.jsonl")
        recs = pj.read_records(self.root, VAULT)
        self.assertEqual([r["state"] for r in recs], ["planned", "validated"])
        # hash chain: each record binds the prior record's hash
        self.assertEqual(recs[0]["prev_hash"], pj.GENESIS_HASH)
        self.assertEqual(recs[1]["prev_hash"], recs[0]["record_hash"])
        for r in recs:
            self.assertEqual(pj.compute_record_hash(r), r["record_hash"])

    def test_idempotent_resume_no_duplicate(self):
        # Process loss then retry of the SAME transition = no-op (R1 resume).
        r1 = _append(self.root, job="00000001", state="pushed")
        r2 = _append(self.root, job="00000001", state="pushed")
        self.assertEqual(r1["record_hash"], r2["record_hash"])
        self.assertEqual(len(pj.read_records(self.root, VAULT)), 1)

    def test_cas_guard_refuses_stale_writer(self):
        first = _append(self.root, job="00000001", state="planned")
        # a concurrent writer advances the tip
        _append(self.root, job="00000001", state="validated")
        # our stale CAS (pinned to the old tip) must refuse, not fork the chain
        with self.assertRaises(pj.PublishJournalCASError):
            _append(self.root, job="00000001", state="ready",
                    expected_tip=first["record_hash"])

    def test_torn_tail_tolerated_and_resumes(self):
        _append(self.root, job="00000001", state="planned")
        _append(self.root, job="00000001", state="validated")
        p = pj.journal_path(self.root, VAULT)
        # simulate a crash mid-append: a partial trailing line, no newline
        with p.open("a", encoding="utf-8") as fh:
            fh.write('{"schema_id":"tropo.publish-journal/v1","seq":3,"job')
        recs = pj.read_records(self.root, VAULT)  # drops ONLY the torn tail
        self.assertEqual([r["state"] for r in recs], ["planned", "validated"])
        # and the store resumes cleanly (next real append chains from the tail)
        _append(self.root, job="00000001", state="ready")
        recs2 = pj.read_records(self.root, VAULT)
        self.assertEqual([r["state"] for r in recs2], ["planned", "validated", "ready"])

    def test_midstream_corruption_is_hard_failure(self):
        _append(self.root, job="00000001", state="planned")
        _append(self.root, job="00000001", state="validated")
        _append(self.root, job="00000001", state="ready")
        p = pj.journal_path(self.root, VAULT)
        lines = p.read_text().splitlines()
        lines[1] = '{"schema_id":"tropo.publish-journal/v1","seq":2,"tampered":true}'
        p.write_text("\n".join(lines) + "\n")
        with self.assertRaises(pj.PublishJournalCorruption):
            pj.read_records(self.root, VAULT)

    def test_survives_simulated_full_rebuild(self):
        # A vault:rebuild regenerates the derived index from frontmatter; it does
        # NOT touch this journal. Model "rebuild" by re-deriving draftStatus from
        # a FRESH index base ⊔ the UNCHANGED journal — a live publishing state
        # must not be erased or downgraded (A2/A4 P0).
        _append(self.root, job="00000001", state="pushed")
        recs = pj.read_records(self.root, VAULT)
        before = ds.resolve_row("argo-private", recs, destination=DEST_A, path_set=("uid-1",))
        self.assertEqual(before["draftStatus"], ds.PUBLISHING)
        # ... rebuild happens (index blown away + rebuilt); journal untouched ...
        recs_after = pj.read_records(self.root, VAULT)
        after = ds.resolve_row("argo-private", recs_after, destination=DEST_A, path_set=("uid-1",))
        self.assertEqual(after["draftStatus"], ds.PUBLISHING)


# ── A5: closed error enum ────────────────────────────────────────────────────
class TestA5ClosedErrorEnum(TmpVault):
    def test_valid_blocked_code_accepted(self):
        rec = _append(self.root, job="00000001", state=pj.BLOCKED,
                      error="REMOTE_CAS_FAILED", resumable_from="pushed")
        self.assertEqual(rec["error"], "REMOTE_CAS_FAILED")
        self.assertEqual(rec["resumable_from"], "pushed")

    def test_unknown_code_is_hard_failure(self):
        with self.assertRaises(pj.PublishJournalValidationError):
            _append(self.root, job="00000001", state=pj.BLOCKED,
                    error="NOT_A_REAL_CODE", resumable_from="pushed")

    def test_blocked_requires_a_code(self):
        with self.assertRaises(pj.PublishJournalValidationError):
            _append(self.root, job="00000001", state=pj.BLOCKED, error=None)

    def test_non_blocked_state_rejects_an_error(self):
        with self.assertRaises(pj.PublishJournalValidationError):
            _append(self.root, job="00000001", state="pushed", error="CONFLICT")

    def test_every_enum_member_is_writable(self):
        for i, code in enumerate(sorted(pj.CLOSED_ERROR_ENUM), start=1):
            job = f"{i:08d}"
            rec = _append(self.root, job=job, state=pj.BLOCKED, error=code,
                          resumable_from="pushed", path_set=(f"u{i}",))
            self.assertIn(rec["error"], pj.CLOSED_ERROR_ENUM)


# ── A2: draftStatus two-source merge (the full matrix) ───────────────────────
class TestA2DraftStatusMatrix(unittest.TestCase):
    def test_base_rows_no_job(self):
        self.assertEqual(ds.resolve_draft_status("argo-private", None), ds.DRAFT)
        self.assertEqual(ds.resolve_draft_status(None, None), ds.DRAFT)
        self.assertEqual(ds.resolve_draft_status("argo-reference", None), ds.DRAFT)
        self.assertEqual(ds.resolve_draft_status("ship", None), ds.PUBLISHED)
        self.assertEqual(ds.resolve_draft_status("external", None), ds.PUBLISHED)

    def test_overlay_rows_full_matrix(self):
        cases = {
            "planned": ds.AWAITING_ASSENT,
            "validated": ds.AWAITING_ASSENT,
            "awaiting-assent": ds.AWAITING_ASSENT,
            "ready": ds.READY,
            "pushed": ds.PUBLISHING,
            "remote-integrated": ds.PUBLISHING,
            "awaiting-receipt": ds.PUBLISHING,
            "reconciling": ds.PUBLISHING,
            "superseded-before-reconcile": ds.BLOCKED,
            pj.BLOCKED: ds.BLOCKED,
            "landed": ds.PUBLISHED,
            "landed-local": ds.PUBLISHED,
        }
        for state, expected in cases.items():
            # overlay wins over EITHER base (private or public) per "any" rows
            self.assertEqual(ds.resolve_draft_status("argo-private", state), expected, state)
            self.assertEqual(ds.resolve_draft_status("ship", state), expected, state)

    def test_unknown_state_refused(self):
        with self.assertRaises(pj.PublishJournalValidationError):
            ds.resolve_draft_status("argo-private", "teleported")


class TestA2RowResolution(TmpVault):
    def test_later_landed_supersedes_older_blocked(self):
        # history stays queryable but an old blocked row cannot dominate (§Read
        # Contract item 3 / §9): a later landed job wins the current overlay.
        _append(self.root, job="00000001", state=pj.BLOCKED,
                error="CONFLICT", resumable_from="pushed")
        recs = pj.read_records(self.root, VAULT)
        self.assertEqual(
            ds.resolve_row("argo-private", recs, destination=DEST_A, path_set=("uid-1",))["draftStatus"],
            ds.BLOCKED,
        )
        _append(self.root, job="00000002", state="landed")  # newer job lands
        recs = pj.read_records(self.root, VAULT)
        row = ds.resolve_row("argo-private", recs, destination=DEST_A, path_set=("uid-1",))
        self.assertEqual(row["draftStatus"], ds.PUBLISHED)
        # the older blocked record is still in history (queryable), just not current
        self.assertEqual(len(pj.records_for_row(recs, DEST_A, ("uid-1",))), 2)


# ── A1: landing agreement (store/state-machine level; full reconcile is D5) ──
class TestA1LandingAgreement(TmpVault):
    def test_remote_integrated_is_not_published(self):
        # A remote merge alone is remote-integrated, NEVER destination-landed.
        # An optimistic pre-reconcile `published` is a hard failure (R2/§7/R10):
        # the overlay maps remote-integrated → publishing, only landed → published.
        _append(self.root, job="00000001", state="remote-integrated")
        recs = pj.read_records(self.root, VAULT)
        row = ds.resolve_row("argo-private", recs, destination=DEST_A, path_set=("uid-1",))
        self.assertEqual(row["draftStatus"], ds.PUBLISHING)
        self.assertNotEqual(row["draftStatus"], ds.PUBLISHED)

    def test_destination_A_landing_does_not_flip_destination_B(self):
        # landed is per named destination; one clone's pull cannot certify another.
        _append(self.root, job="00000001", state="remote-integrated", dest=DEST_A)
        _append(self.root, job="00000001", state="remote-integrated", dest=DEST_B)
        _append(self.root, job="00000001", state="landed", dest=DEST_A)
        recs = pj.read_records(self.root, VAULT)
        row_a = ds.resolve_row("argo-private", recs, destination=DEST_A, path_set=("uid-1",))
        row_b = ds.resolve_row("argo-private", recs, destination=DEST_B, path_set=("uid-1",))
        self.assertEqual(row_a["draftStatus"], ds.PUBLISHED)
        self.assertEqual(row_b["draftStatus"], ds.PUBLISHING)  # B still not landed


# ── A3: segment is derived, never hand-editable (R3) ─────────────────────────
class TestA3SegmentDerived(TmpVault):
    def _make_manifest(self, uid: str):
        mp = self.root / ".tropo" / "vault-manifest.md"
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(f"---\nuid: {uid}\ntype: vault\n---\n# manifest\n")

    def test_read_exposes_derived_segment(self):
        self._make_manifest("beefcafe")
        rec = {"uid": "12345678", "extraction_scope": "argo-private", "path": "vault/files/12345678.md"}
        self.assertEqual(rs.read_segment(rec, self.root), "beefcafe")

    def test_hand_set_segment_write_is_refused(self):
        self._make_manifest("beefcafe")
        # a hand-authored segment claiming a DIFFERENT vault must be ignored;
        # the derived value stays authoritative.
        rec = {"uid": "12345678", "extraction_scope": "argo-private",
               "path": "vault/files/12345678.md", "segment": "deadbeef"}
        out = rs.apply_derived_segment(rec, self.root)
        self.assertTrue(out["hand_set_rejected"])
        self.assertEqual(out["rejected_value"], "deadbeef")
        self.assertEqual(out["record"]["segment"], "beefcafe")  # forced to derived

    def test_matching_hand_set_is_not_flagged(self):
        self._make_manifest("beefcafe")
        rec = {"uid": "12345678", "extraction_scope": "argo-private",
               "path": "vault/files/12345678.md", "segment": "beefcafe"}
        out = rs.apply_derived_segment(rec, self.root)
        self.assertFalse(out["hand_set_rejected"])
        self.assertEqual(out["record"]["segment"], "beefcafe")


# ── A6: ref-closure query (vault-scoped, exclusion-aware, re-runnable) ───────
class TestA6RefClosure(unittest.TestCase):
    def _graph(self):
        # A → B → C (all vault V1, all unpublished); B → P (published);
        # A → X (vault V2, cross-vault). D unpublished, referenced only by C.
        n = rc.GraphNode
        return {
            "A": n("A", "v1", False, ("B", "X")),
            "B": n("B", "v1", False, ("C", "P")),
            "C": n("C", "v1", False, ("D",)),
            "D": n("D", "v1", False, ()),
            "P": n("P", "v1", True, ()),   # already published
            "X": n("X", "v2", False, ()),  # different vault
        }

    def test_transitive_closure_of_unpublished_refs(self):
        res = rc.compute_ref_closure(self._graph(), ["A"], snapshot_revision="rev1")
        self.assertFalse(res.refused)
        self.assertEqual(res.vault_uid, "v1")
        # A pulls in B, C, D (unpublished, same vault); P excluded (published)
        self.assertEqual(res.included_nodes, ["A", "B", "C", "D"])
        # X is cross-vault → external pin, never in the closure
        self.assertEqual([p["node"] for p in res.external_dependency_pins], ["X"])
        self.assertEqual(res.snapshot_revision, "rev1")

    def test_cross_vault_selection_refused(self):
        g = self._graph()
        res = rc.compute_ref_closure(g, ["A", "X"])  # A∈v1, X∈v2
        self.assertTrue(res.refused)
        self.assertIn("cross-vault", res.reason)

    def test_exclusion_cuts_edges_and_strands_subtree(self):
        # exclude B: A→B becomes a cut edge; C and D are stranded (reachable only
        # through B). Prune is a graph op, not per-row.
        res = rc.compute_ref_closure(self._graph(), ["A"], exclusions=["B"])
        self.assertFalse(res.refused)
        self.assertEqual(res.included_nodes, ["A"])
        self.assertEqual(res.cut_edges, [["A", "B"]])
        self.assertEqual(res.stranded_nodes, ["C", "D"])

    def test_re_runnable_recomputes(self):
        g = self._graph()
        full = rc.compute_ref_closure(g, ["A"])
        pruned = rc.compute_ref_closure(g, ["A"], exclusions=["C"])
        self.assertEqual(full.included_nodes, ["A", "B", "C", "D"])
        # excluding C strands only D; A, B stay in
        self.assertEqual(pruned.included_nodes, ["A", "B"])
        self.assertEqual(pruned.stranded_nodes, ["D"])
        self.assertEqual(pruned.cut_edges, [["B", "C"]])


# ── A7: /api/vaults (memberCount from B4 registry, never GitHub) ─────────────
def _registry_jsonl(rows):
    lines = []
    for r in rows:
        ordered = {k: r[k] for k in REGISTRY_ROW_KEYS}
        lines.append(json.dumps(ordered, ensure_ascii=False, separators=(",", ":")))
    return ("\n".join(lines) + "\n").encode("utf-8")


class TestA7ApiVaults(unittest.TestCase):
    def _resolver(self):
        row = {
            "group_uid": "aud00001",
            "slug": "marketing-team",
            "title": "Marketing Team",
            "status": "active",
            "version": 1,
            "owner_uid": "own00001",
            "direct_member_uids": ["mem00001", "mem00002", "mem00003"],
            "direct_included_group_uids": [],
            "effective_member_uids": ["mem00001", "mem00002", "mem00003"],
            "wider_group_uids": [],
            "source_authority_uid": "auth0001",
            "source_revision": "rev-1",
            "source_path": "groups/marketing.md",
            "source_hash": "h" * 64,
            "principal_directory_revision": "pdir-1",
        }
        return GroupResolver.from_jsonl(_registry_jsonl([row]))

    def test_shape_and_membercount_from_registry(self):
        spec = {
            "id": "vault-1", "name": "Marketing", "kind": "team",
            "audience": "aud00001", "segmentColor": "#3366ff",
            "remoteHealth": "ok",
        }
        rows = rs.vaults_surface([spec], self._resolver(), count_as_of=ASOF)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(set(row.keys()), {
            "id", "name", "kind", "audience", "segmentColor",
            "memberCount", "countAsOf", "remoteHealth",
        })
        # memberCount equals the registry effective-member count (never GitHub)
        self.assertEqual(row["memberCount"], 3)
        self.assertIsNotNone(row["countAsOf"])  # always paired
        self.assertEqual(row["countAsOf"], ASOF)


# ── A8: jobId/asOf on reads + scope-vs-location lint + studio-health ─────────
class TestA8HealthAndLint(TmpVault):
    def test_read_result_carries_jobid_and_asof(self):
        _append(self.root, job="0000abcd", state="pushed")
        recs = pj.read_records(self.root, VAULT)
        row = ds.resolve_row("argo-private", recs, destination=DEST_A, path_set=("uid-1",))
        self.assertEqual(row["jobId"], "0000abcd")
        self.assertEqual(row["asOf"], ASOF)

    def test_scope_vs_location_lint_flags_private_in_shared(self):
        files = [
            {"path": "shared/draft.md", "extraction_scope": "argo-private", "in_shared_tree": True},
            {"path": "shared/shipped.md", "extraction_scope": "ship", "in_shared_tree": True},
            {"path": "private/draft.md", "extraction_scope": "argo-private", "in_shared_tree": False},
        ]
        findings = rs.scope_vs_location_lint(files)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "shared/draft.md")
        self.assertEqual(findings[0]["severity"], rs.SEVERITY_ERROR)
        self.assertEqual(findings[0]["kind"], "misplaced-draft")

    def test_studio_health_agrees_before_and_after_rebuild(self):
        _append(self.root, job="0000abcd", state=pj.BLOCKED,
                error="RECONCILE_FAILED", resumable_from="reconciling")
        files = [{"path": "shared/draft.md", "extraction_scope": "argo-private", "in_shared_tree": True}]
        recs = pj.read_records(self.root, VAULT)
        health_before = rs.studio_health(files=files, journal_records=recs)
        # lint ERROR count == health misplaced-draft count (A8)
        lint = rs.scope_vs_location_lint(files)
        self.assertEqual(health_before["misplacedDraftCount"], len(lint))
        self.assertEqual(health_before["blockedJobCount"], 1)
        self.assertEqual(health_before["errorCount"], 2)
        # a blocked-job finding carries jobId + asOf from the durable record
        blocked = [f for f in health_before["findings"] if f["kind"] == "blocked-job"][0]
        self.assertEqual(blocked["jobId"], "0000abcd")
        self.assertEqual(blocked["asOf"], ASOF)
        # ... full vault:rebuild (index blown away + rebuilt; journal + physical
        # files untouched) ... counts must be identical (cold-boot / A8).
        recs_after = pj.read_records(self.root, VAULT)
        health_after = rs.studio_health(files=files, journal_records=recs_after)
        self.assertEqual(health_after["errorCount"], health_before["errorCount"])
        self.assertEqual(health_after["misplacedDraftCount"], health_before["misplacedDraftCount"])
        self.assertEqual(health_after["blockedJobCount"], health_before["blockedJobCount"])

    def test_studio_health_rejects_unknown_drift_kind(self):
        with self.assertRaises(ValueError):
            rs.studio_health(drift_findings=[{"kind": "not-a-drift-kind"}])


if __name__ == "__main__":
    unittest.main()
