#!/usr/bin/env python3
"""Property + fault plants for the durable-pipeline-closure feature (dev-spec c392d833).

Built by talos-t35 under the LOCKED dev-spec c392d833 (activation 63988cfb; Argus
A136), diagnosed by metis-g91 (task 1d689277). Paired test-spec: af7e31f9.

Stdlib `unittest` only — no pytest dependency. Run with either:

    python3 -m unittest test_pipeline_durable_closure          # from vault/tools/tests/
    python3 vault/tools/tests/test_pipeline_durable_closure.py  # direct

What this proves (one class per dev-spec acceptance criterion, 1-based):

  AC1  CLOSE WELDED TO SHIP ....... tropo-build-release.py's ship path invokes the
                                    close-out hook as a guaranteed side-effect (gated
                                    non-blocking, passes the ship SHA); 9e7003b1.py
                                    exposes the standalone `close-out` CLI action.
  AC2  ARCHIVE + STAMP ............ run_close_out_hook sets the root state:archived +
                                    stamps final_commit; re-running on an already
                                    archived+stamped root is a no-op (no re-stamp);
                                    a SHA-less close still archives, a later ship fills
                                    final_commit (fill-if-absent, never overwrite).
  AC3  SYMMETRIC RULE 10 INVARIANT  pipeline.capsule v3.4 declares the Rule 12 terminal
                                    invariant + Check 21; the validator check flags a
                                    shipped root still state:active and passes an
                                    archived one (and never flags an in-flight root).
  AC4  PORTED TO ALL PIPELINES .... the close step exists + is wired terminal in the
                                    doc/test/web/app pipeline definitions (not only dev).
  AC5  SWEEP BACKSTOP PRESERVED ... tropo-sweep-stale-roots.py still exists (exactly
                                    once, not removed / not duplicated) and its
                                    classify() still archives an orphaned older root
                                    while keeping each pipeline's live head.
  AC6  OPTION-A REVERSAL IS HONEST  the hook + capsule record the Option-A supersession
                                    (state:active-on-done -> state:archived-on-ship) with
                                    the 93-stuck-roots rationale.
  AC7  PARALLEL CYCLES UNBROKEN ... closing one root archives ONLY that root and leaves
                                    a sibling in-flight root untouched — no global
                                    single-active-root lock (Mike-A94 concurrency).

  GAP  CHECK-32 COMPLETION RECORD  the welded close ALSO emits the correlated
                                    tropo.cycle.closed completion event (correlationid ==
                                    root uid) + rebuilds the events-sqlite, so a real ship
                                    does not archive a root and then trip Check 32
                                    (Completion Recording Enforcement, 2fe61817) as an
                                    ERROR; idempotent (re-close emits no duplicate),
                                    archive-path only.

The hook is exercised against a sandboxed temp vault (eng.VAULT_FILES monkeypatched),
mirroring the established pattern in test_v1_84_1_closeout_hardening_8c8ca68c.py.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Locate substrate + import the (hyphen/digit-named) tools by path.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]
VAULT_TOOLS = ROOT / "vault" / "tools"
VAULT_FILES = ROOT / "vault" / "files"
CAPSULE = ROOT / "vault" / "capsules" / "tropo-pipeline.capsule.md"
BUILD_RELEASE = VAULT_TOOLS / "tropo-build-release.py"
RUNTIME = VAULT_TOOLS / "9e7003b1.py"
VALIDATE = VAULT_TOOLS / "tropo-validate.py"
SWEEP = VAULT_TOOLS / "tropo-sweep-stale-roots.py"

_TROPO_SCRIPTS = ROOT / ".tropo" / "scripts"
if str(_TROPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TROPO_SCRIPTS))


def _load(mod_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


eng = _load("eng_durable_closure", RUNTIME)


def _real_fm(uid: str) -> dict:
    """Parse the frontmatter of a real vault entry by UID."""
    text = (VAULT_FILES / f"{uid}.md").read_text()
    m = re.match(r"^---\n(.*?\n)---\n", text, re.DOTALL)
    assert m, f"{uid} has no frontmatter"
    return yaml.safe_load(m.group(1)) or {}


# ---------------------------------------------------------------------------
# Shared sandbox for the hook (AC2 / AC7): patch eng's module-level path globals.
# ---------------------------------------------------------------------------
class _SandboxedHook(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="durable-closure-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.files.mkdir(parents=True)
        self._orig_root, self._orig_files = eng.VAULT_ROOT, eng.VAULT_FILES
        eng.VAULT_ROOT, eng.VAULT_FILES = self.tmp, self.files

    def tearDown(self):
        eng.VAULT_ROOT, eng.VAULT_FILES = self._orig_root, self._orig_files
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_root(self, uid: str, **over) -> dict:
        fm = {
            "uid": uid, "type": "project",
            "title": "dev-pipeline — Activation Root (2026-07-22)",
            "status": "active", "state": "active",
            "created": "2026-07-22", "modified": "2026-07-22",
        }
        fm.update(over)
        eng.write_vault_entry(uid, fm, "root body\n")
        return fm

    def _activation(self, root_uid: str, dev_spec_uid=None) -> dict:
        return {"frontmatter": {"activation_root_project": root_uid,
                                "dev_spec_uid": dev_spec_uid}, "body": "act\n"}

    def _root_fm(self, uid: str) -> dict:
        return eng.read_vault_entry(uid)["frontmatter"]


# ─── AC1 — CLOSE WELDED TO SHIP ───────────────────────────────────────────────
class TestAC1CloseWeldedToShip(unittest.TestCase):
    """A release ship (build-release.py ship path) invokes the close-out hook as a
    guaranteed side-effect; a ship cannot leave its own root state:active."""

    def test_build_release_ship_path_invokes_close_out(self):
        src = BUILD_RELEASE.read_text()
        # The weld exists on the ship path, invoking pipeline-runtime.py close-out.
        self.assertIn("close-out", src, "build-release must invoke the close-out action")
        self.assertIn("9e7003b1.py", src, "build-release must call pipeline-runtime.py")
        self.assertIn("--final-commit", src, "the ship SHA must be passed for final_commit")
        self.assertRegex(src, r"rev-parse['\"],\s*['\"]HEAD",
                         "the ship SHA is derived from git rev-parse HEAD")
        # Guaranteed side-effect: welded near ship completion, gated on a real build
        # (not --dry-run) and on having an activation to close; non-blocking.
        self.assertRegex(src, r"if\s+not\s+DRY_RUN\s+and\s+activation_uid",
                         "close must fire on a real build with an activation-uid")

    def test_runtime_exposes_standalone_close_out(self):
        src = RUNTIME.read_text()
        self.assertIn("def action_close_out", src)
        self.assertIn('sub.add_parser("close-out"', src)
        self.assertIn('elif action == "close-out"', src)
        # Standalone: does NOT require a live pipeline-run/run folder.
        self.assertTrue(hasattr(eng, "action_close_out"))


# ─── AC2 — ARCHIVE + STAMP (idempotent) ───────────────────────────────────────
class TestAC2ArchiveAndStamp(_SandboxedHook):
    """run_close_out_hook sets the root state:archived + stamps final_commit; re-running
    on an already-archived root is idempotent (no error, no re-stamp)."""

    SHA_A = "a" * 40
    SHA_B = "b" * 40

    def test_ship_archives_and_stamps_the_root(self):
        self._write_root("root0001")
        closed = eng.run_close_out_hook(self._activation("root0001"), None,
                                        "talos-t35", final_commit=self.SHA_A)
        self.assertEqual(closed, ["root0001"])
        fm = self._root_fm("root0001")
        self.assertEqual(fm["state"], "archived")          # SUPERSEDES Option A
        self.assertEqual(fm["status"], "done")             # kept as-is
        self.assertEqual(fm["final_commit"], self.SHA_A)   # stamped ship SHA
        self.assertIn("archived_at", fm)                   # reversible provenance
        self.assertIn("archived_by", fm)

    def test_reclose_is_idempotent_no_error_no_restamp(self):
        self._write_root("root0002")
        eng.run_close_out_hook(self._activation("root0002"), None, "talos-t35",
                               final_commit=self.SHA_A)
        # Second close with a DIFFERENT SHA — must be a no-op, never re-stamp.
        closed2 = eng.run_close_out_hook(self._activation("root0002"), None, "talos-t35",
                                         final_commit=self.SHA_B)
        self.assertEqual(closed2, [], "already archived+stamped root must be a no-op")
        fm = self._root_fm("root0002")
        self.assertEqual(fm["final_commit"], self.SHA_A, "final_commit must NOT be re-stamped")
        self.assertEqual(fm["state"], "archived")

    def test_shaless_close_archives_then_ship_fills_final_commit(self):
        # complete-workflow path (no SHA) archives; a later ship-path close fills the SHA.
        self._write_root("root0003")
        eng.run_close_out_hook(self._activation("root0003"), None, "pipeline-runtime")
        fm = self._root_fm("root0003")
        self.assertEqual(fm["state"], "archived")
        self.assertNotIn("final_commit", fm, "no SHA passed -> not stamped yet")
        closed = eng.run_close_out_hook(self._activation("root0003"), None,
                                        "tropo-build-release.py", final_commit=self.SHA_A)
        self.assertEqual(closed, ["root0003"], "fill-if-absent close is a real write")
        self.assertEqual(self._root_fm("root0003")["final_commit"], self.SHA_A)

    def test_no_activation_root_is_safe_noop(self):
        # An activation with no activation_root_project must not error.
        closed = eng.run_close_out_hook({"frontmatter": {}, "body": ""}, None, "talos-t35",
                                        final_commit=self.SHA_A)
        self.assertEqual(closed, [])


# ─── AC3 — SYMMETRIC RULE 10 INVARIANT + validator check ──────────────────────
class TestAC3Rule10SymmetricInvariant(unittest.TestCase):
    """pipeline.capsule declares a terminal close invariant mirroring the step-0
    authoring invariant, with a validator check that flags a shipped cycle whose root
    is still state:active."""

    @classmethod
    def setUpClass(cls):
        cls.val = _load("val_durable_closure", VALIDATE)

    def test_capsule_declares_rule12_and_check21_at_v34(self):
        text = CAPSULE.read_text()
        fm = yaml.safe_load(re.match(r"^---\n(.*?\n)---\n", text, re.DOTALL).group(1))
        self.assertEqual(str(fm["version"]), "3.4", "capsule bumped to v3.4")
        self.assertIn("v3_4_amendment_note", fm)
        # Rule 12 (terminal invariant) + Check 21 (validator check) present in body.
        self.assertRegex(text, r"12\.\s+\*\*\(v3\.4[^\n]*TERMINAL closure")
        self.assertIn("check_pipeline_root_terminal_closure", text)
        self.assertIn("state: archived", text)
        self.assertIn("final_commit", text)

    def _mk_vault(self, roots: list[dict]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="rule12-check-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        fdir = tmp / "vault" / "files"
        fdir.mkdir(parents=True)
        for r in roots:
            (fdir / f"{r['uid']}.md").write_text(
                "---\n" + yaml.safe_dump(r, sort_keys=False) + "---\nbody\n")
        return tmp

    def test_check_flags_shipped_root_still_active(self):
        vault = self._mk_vault([{
            "uid": "shp00001", "type": "project",
            "title": "dev-pipeline — Activation Root (2026-07-01)",
            "status": "done", "state": "active",   # shipped but not archived => VIOLATION
        }])
        findings, roots, violations = self.val.check_pipeline_root_terminal_closure(vault)
        self.assertEqual(violations, 1)
        self.assertEqual(roots, 1)
        self.assertTrue(any("shp00001" in f and "[WARN]" in f for f in findings))

    def test_check_passes_archived_root(self):
        vault = self._mk_vault([{
            "uid": "arc00001", "type": "project",
            "title": "dev-pipeline — Activation Root (2026-07-01)",
            "status": "done", "state": "archived", "final_commit": "a" * 40,
        }])
        findings, roots, violations = self.val.check_pipeline_root_terminal_closure(vault)
        self.assertEqual(violations, 0, "an archived shipped root must PASS")
        self.assertEqual(roots, 1)

    def test_check_ignores_in_flight_root(self):
        # An in-flight (status:active) root is NOT flagged — parallel cycles stay legal.
        vault = self._mk_vault([{
            "uid": "inf00001", "type": "project",
            "title": "dev-pipeline — Activation Root (2026-07-22)",
            "status": "active", "state": "active",
        }])
        findings, roots, violations = self.val.check_pipeline_root_terminal_closure(vault)
        self.assertEqual(violations, 0, "in-flight root must not be flagged")


# ─── AC4 — PORTED TO ALL PIPELINES ────────────────────────────────────────────
class TestAC4PortedToAllPipelines(unittest.TestCase):
    """The close step exists in the doc/test/web/app pipeline definitions, not only dev."""

    # pipeline -> (new/existing close-step uid, its predecessor terminal step uid)
    PORTS = {
        "dev":  ("8a476130", "3e0bb81e"),   # pre-existing (reference)
        "test": ("547e0cac", "047c147c"),   # pre-existing (note 5220fb25)
        "doc":  ("b4081ddb", "343dd5d8"),   # ported this cycle
        "web":  ("008b86cc", "1f6c4a9d"),   # ported this cycle
        "app":  ("712fe8c6", "b68e3332"),   # ported this cycle
    }

    def test_each_pipeline_has_a_terminal_close_step(self):
        for label, (close_uid, pred_uid) in self.PORTS.items():
            with self.subTest(pipeline=label):
                close = _real_fm(close_uid)
                self.assertEqual(close.get("name"), "close-loose-ends",
                                 f"{label}: {close_uid} must be a close-loose-ends step")
                self.assertIn("activation_root_project.state == archived",
                              close.get("exit_criteria", []),
                              f"{label}: close step must verify the root archived")
                self.assertEqual(close.get("next_steps") or [], [],
                                 f"{label}: close step must be terminal")

    def test_predecessor_chains_into_the_close_step(self):
        for label, (close_uid, pred_uid) in self.PORTS.items():
            with self.subTest(pipeline=label):
                pred = _real_fm(pred_uid)
                self.assertIn(close_uid, pred.get("next_steps") or [],
                              f"{label}: predecessor {pred_uid} must chain -> {close_uid}")

    def test_doc_test_web_app_all_covered(self):
        # The dev-spec's explicit target set: doc/test/web/app all close symmetrically.
        for label in ("doc", "test", "web", "app"):
            self.assertIn(label, self.PORTS)


# ─── AC5 — SWEEP BACKSTOP PRESERVED ───────────────────────────────────────────
class TestAC5SweepBackstopPreserved(unittest.TestCase):
    """The metis-g91 stale-root sweep remains the belt-and-suspenders backstop; the weld
    is primary, the sweep is recovery — they compose, neither is removed."""

    def test_sweep_tool_exists_exactly_once(self):
        matches = list((ROOT / "vault" / "tools").glob("tropo-sweep-stale-roots.py"))
        self.assertEqual(len(matches), 1, "sweep tool must exist and not be duplicated")
        self.assertTrue(SWEEP.stat().st_size > 0)

    def test_sweep_classify_archives_orphan_keeps_head(self):
        sweep = _load("sweep_durable_closure", SWEEP)
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE entries (uid TEXT, title TEXT, type TEXT, state TEXT, "
                   "created TEXT, modified TEXT, fm_json TEXT)")
        db.execute("CREATE TABLE edges (src_uid TEXT, dst_uid TEXT, rel TEXT)")
        today = date.today()
        old = (today - timedelta(days=40)).isoformat()
        head = today.isoformat()
        rows = [
            ("pipe0001", "dev-pipeline", "pipeline", "active", head, head, "{}"),
            ("rootold1", "dev-pipeline — Activation Root (old)", "project", "active",
             old, old, '{"state": "active"}'),
            ("roothead", "dev-pipeline — Activation Root (head)", "project", "active",
             head, head, '{"state": "active"}'),
        ]
        db.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?,?)", rows)
        db.executemany("INSERT INTO edges VALUES (?,?,?)", [
            ("rootold1", "pipe0001", "member_of"),
            ("roothead", "pipe0001", "member_of"),
        ])
        roots = sweep.load_stuck_roots(db)
        self.assertEqual({r["uid"] for r in roots}, {"rootold1", "roothead"})
        ptitles = sweep.pipeline_titles(db)
        root_pipes = sweep.root_pipelines(db, set(ptitles.keys()))
        targets, kept = sweep.classify(roots, root_pipes, today, 14)
        target_uids = {t["uid"] for t in targets}
        kept_uids = {k["uid"] for k in kept}
        self.assertIn("rootold1", target_uids, "orphaned older root is a sweep target")
        self.assertIn("roothead", kept_uids, "live head is kept, not swept")
        self.assertNotIn("roothead", target_uids)


# ─── AC6 — OPTION-A REVERSAL IS HONEST ────────────────────────────────────────
class TestAC6OptionAReversalHonest(unittest.TestCase):
    """The change from state:active-on-done (Option A) to state:archived-on-ship is
    recorded with rationale (93 roots stuck state:active proved Option A caused sprawl)."""

    def test_hook_records_option_a_supersession_with_rationale(self):
        src = RUNTIME.read_text()
        # The run_close_out_hook docstring/comments must name the supersession + 93 roots.
        hook = src[src.index("def run_close_out_hook"):src.index("def action_close_out")]
        self.assertRegex(hook, r"(?i)supersede", "must record it supersedes Option A")
        self.assertIn("Option A", hook)
        self.assertIn("99e52c18", hook, "cite the Option-A commit")
        self.assertIn("93", hook, "cite the 93-stuck-roots rationale")

    def test_capsule_records_option_a_supersession(self):
        text = CAPSULE.read_text()
        self.assertIn("99e52c18", text)
        self.assertRegex(text, r"(?i)SUPERSED")
        self.assertIn("93", text)


# ─── AC7 — PARALLEL CYCLES UNBROKEN ───────────────────────────────────────────
class TestAC7ParallelCyclesUnbroken(_SandboxedHook):
    """The fix does NOT add a single-active-root lock; closing is per-root at that
    root's own ship, never a global gate."""

    def test_closing_one_root_leaves_sibling_in_flight(self):
        # Two parallel cycles for the same pipeline, both roots state:active.
        self._write_root("rootpar1")
        self._write_root("rootpar2")
        # Close ONLY cycle 1's root.
        closed = eng.run_close_out_hook(self._activation("rootpar1"), None,
                                        "talos-t35", final_commit="c" * 40)
        self.assertEqual(closed, ["rootpar1"])
        self.assertEqual(self._root_fm("rootpar1")["state"], "archived")
        # The sibling in-flight root is untouched — no global lock, no force-close.
        sib = self._root_fm("rootpar2")
        self.assertEqual(sib["state"], "active", "sibling parallel cycle must stay active")
        self.assertEqual(sib["status"], "active")

    def test_no_single_active_root_lock_in_close_path(self):
        # The close path must not refuse when other active roots exist (no global gate).
        src = RUNTIME.read_text()
        hook = src[src.index("def run_close_out_hook"):src.index("def action_close_out")]
        self.assertNotRegex(hook, r"(?i)single[- ]active", "must not add a single-active lock")
        # It only touches the one root named by activation_root_project.
        self.assertIn("activation_root_project", hook)


# ─── CHECK-32 GAP-FIX — welded close emits the correlated completion event ────
class TestWeldedCloseEmitsCompletionEvent(_SandboxedHook):
    """dev-spec c392d833 gap-fix: the durable-closure weld archives the root, but
    Check 32 (Completion Recording Enforcement, 2fe61817) FAILs a terminal work-item
    whose uid has NO correlated completion event. So the weld MUST also emit the
    tropo.cycle.closed event (correlationid == root uid) that Check 32 accepts, and
    rebuild the derived events-sqlite — otherwise every real ship archives a root and
    then trips Check 32 as an ERROR. IDEMPOTENT: re-close emits no duplicate; ARCHIVE
    PATH ONLY: a non-archiving call never records a close."""

    def _events(self) -> list[dict]:
        p = self.tmp / "vault" / "events" / "00-events.jsonl"
        if not p.is_file():
            return []
        return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]

    def _cycle_closed_for(self, uid: str) -> list[dict]:
        return [e for e in self._events()
                if e.get("type") == "tropo.cycle.closed" and e.get("correlationid") == uid]

    def _sqlite_cycle_closed_count(self, uid: str) -> int:
        sq = self.tmp / "vault" / "events" / "00-events-index.sqlite"
        if not sq.is_file():
            return -1
        con = sqlite3.connect(str(sq))
        try:
            return con.execute(
                "SELECT COUNT(*) FROM events WHERE type='tropo.cycle.closed' "
                "AND correlationid=?", (uid,)).fetchone()[0]
        finally:
            con.close()

    def test_welded_close_emits_correlated_completion_event(self):
        self._write_root("evt00001")
        eng.run_close_out_hook(self._activation("evt00001"), None, "talos-t35",
                               final_commit="d" * 40)
        fm = self._root_fm("evt00001")
        self.assertEqual(fm["state"], "archived")          # archive still happens
        self.assertEqual(fm["final_commit"], "d" * 40)     # stamp still happens
        # A single correlated completion event Check 32 will accept.
        matches = self._cycle_closed_for("evt00001")
        self.assertEqual(len(matches), 1, "exactly one correlated completion event")
        self.assertEqual(matches[0]["correlationid"], "evt00001",
                         "correlationid must equal the activation-root uid (Check 32)")
        # Rebuilt into the derived events-sqlite (Check 32's derived surface).
        self.assertEqual(self._sqlite_cycle_closed_count("evt00001"), 1,
                         "the completion event is in the rebuilt events-sqlite")

    def test_reclose_emits_no_duplicate_event(self):
        self._write_root("evt00002")
        eng.run_close_out_hook(self._activation("evt00002"), None, "talos-t35",
                               final_commit="d" * 40)
        # Re-close (idempotent archive, different SHA) must not emit a 2nd event.
        eng.run_close_out_hook(self._activation("evt00002"), None, "talos-t35",
                               final_commit="e" * 40)
        self.assertEqual(len(self._cycle_closed_for("evt00002")), 1,
                         "re-close must not emit a duplicate completion event")
        self.assertEqual(self._sqlite_cycle_closed_count("evt00002"), 1)

    def test_shaless_then_ship_emits_exactly_once(self):
        # SHA-less complete-workflow close archives + records; the later fill-if-absent
        # ship close stamps the SHA but must NOT emit a second completion event.
        self._write_root("evt00003")
        eng.run_close_out_hook(self._activation("evt00003"), None, "pipeline-runtime")
        self.assertEqual(len(self._cycle_closed_for("evt00003")), 1,
                         "SHA-less archive records the completion once")
        eng.run_close_out_hook(self._activation("evt00003"), None,
                               "tropo-build-release.py", final_commit="f" * 40)
        self.assertEqual(self._root_fm("evt00003")["final_commit"], "f" * 40)
        self.assertEqual(len(self._cycle_closed_for("evt00003")), 1,
                         "fill-if-absent ship close reuses the existing completion event")

    def test_no_archive_no_completion_event(self):
        # A hook call that archives nothing (no activation_root_project) records no
        # close — the completion event fires only on the archive/terminal path.
        eng.run_close_out_hook({"frontmatter": {}, "body": ""}, None, "talos-t35",
                               final_commit="d" * 40)
        self.assertEqual(self._events(), [], "no archive => no completion event (never mid-run)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
