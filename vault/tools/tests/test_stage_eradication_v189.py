#!/usr/bin/env python3
"""v1.89 stage eradication — AC1/AC2/AC3/AC6/AC7 for Mike-locked dev-spec 63aaea28.

THE ONE SENTENCE THIS FILE DEFENDS. Work owns `status`; visibility is `state`;
kind-over-time is `lifecycle`; pipeline position is `current_step`. The retired
`stage` axis exists nowhere that code reads, nowhere that indexes project it,
and nowhere that new writes can recreate it — while history stays byte-identical.

NAMES ARE COPIED FROM THE SPEC. The verify.command fields invoke these classes
by name (t44-verify-commands-are-the-contract). Do not rename.

HOW THESE TESTS ARE BUILT. Real subprocesses against isolated temp studios: the
migration tool through its real CLI, the index through the real rebuild, the
runtime through the real state functions. No mocks on production doors. Each
class carries a control that fails loudly if the thing under test stops being
examined (the vacuous-gate lesson).

The three non-null pipeline positions named by the spec's evidence (UID round-
trips) are asserted individually, not as a count.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
MIGRATE = REPO / "vault" / "tools" / "tropo-migrate-stage-eradication.py"
REBUILD = REPO / "vault" / "tools" / "tropo-rebuild-index.py"

# The three non-null pipeline positions the spec names. Values round-trip.
# The LIVE non-null positions, verified against the migrated tree 2026-08-18
# (4816b022 sits on a template record whose value carries a prose comment —
# metis-g108 reviewers caught the wrong constant; the live three are these).
NON_NULL_POSITIONS = ["e2b7c493", "78ec3a22", "075fe874"]


def run_tool(tool: pathlib.Path, *args, root: pathlib.Path, timeout=120):
    p = subprocess.run([sys.executable, str(tool), "--root", str(root), *args],
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def parse_json_out(stdout: str):
    try:
        return json.loads(stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


class StageEradicationStudio(unittest.TestCase):
    """A temp studio with production-shaped carriers.

    Shapes copied from live substrate, not invented: run.state.json carries
    current_stage/current_step/step_status; source records carry status+stage
    (redundant), stage alone (sole legacy), or disagreeing pairs; prose bodies
    mention stage as history; a capsule example mentions current_stage as
    external protocol prose.
    """

    def setUp(self):
        self.studio = pathlib.Path(tempfile.mkdtemp(prefix="stage189-"))
        (self.studio / "vault" / "files").mkdir(parents=True)
        (self.studio / "vault" / "tools").mkdir(parents=True)
        (self.studio / "vault" / "pipeline-runs").mkdir(parents=True)
        (self.studio / ".tropo").mkdir()  # rebuild resolves roots that carry it
        (self.studio / "vault" / "capsules").mkdir(exist_ok=True)  # rebuild requires it

    def tearDown(self):
        shutil.rmtree(self.studio, ignore_errors=True)

    # ── fixture authors ──────────────────────────────────────────

    def file_record(self, uid, body="history: the stage axis was retired\n",
                    **fm):
        lines = ["---", f"uid: {uid}", "type: note"]
        for k, v in fm.items():
            lines.append(f"{k}: {v}")
        lines += ["---", "", body]
        (self.studio / "vault" / "files" / f"{uid}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        return uid

    def pipeline_record(self, uid, current_stage="null"):
        (self.studio / "vault" / "files" / f"{uid}.md").write_text(
            f"---\nuid: {uid}\ntype: pipeline-run\nstatus: active\n"
            f"current_stage: {current_stage}\n---\n\nrun record\n",
            encoding="utf-8")
        return uid

    def run_state(self, run_name, current_stage="null", current_step="null"):
        d = self.studio / "vault" / "pipeline-runs" / run_name
        d.mkdir(parents=True, exist_ok=True)
        state = {"current_stage": None if current_stage == "null" else current_stage,
                 "current_step": None if current_step == "null" else current_step,
                 "step_status": {}, "eligible_steps": []}
        (d / "run.state.json").write_text(json.dumps(state, indent=1) + "\n",
                                          encoding="utf-8")
        return d / "run.state.json"

    def plant_default_carriers(self):
        """The canonical carrier set every census test starts from."""
        self.file_record("aaaa0001", status="new", stage="inbox")
        self.file_record("aaaa0002", status="active", stage="build",
                         state="active")
        self.file_record("aaaa0003", stage="build")  # sole legacy source
        self.pipeline_record("bbbb0001")
        for uid in NON_NULL_POSITIONS:
            self.pipeline_record(f"pos{uid}", current_stage=uid)
        self.run_state("run-x-2026-08-18")
        self.run_state("run-y-2026-08-18", current_step="11112222")

    # ── doors ────────────────────────────────────────────────────

    def migrate(self, *args):
        return run_tool(MIGRATE, *args, root=self.studio)

    def rebuild(self):
        p = subprocess.run(
            [sys.executable, str(REBUILD), "--vault-path", str(self.studio),
             "--apply", "--skip-rehydrate"],
            capture_output=True, text=True, timeout=300)
        return p.returncode, p.stdout, p.stderr

    def index_rows(self):
        path = self.studio / "vault" / "00-index.jsonl"
        if not path.exists():
            return []
        return [json.loads(l) for l in path.read_text().splitlines()
                if l.strip()]

    def stage_keys_everywhere(self):
        """Every stage-shaped key the migrated surfaces still expose."""
        found = []
        for row in self.index_rows():
            for key in row:
                if "stage" in key.lower():
                    found.append(f"index:{key}")
        for f in (self.studio / "vault" / "files").glob("*.md"):
            text = f.read_text()
            head = text.split("---")[1] if text.startswith("---") else ""
            for m in re.finditer(r"^(stage|current_stage):", head, re.MULTILINE):
                found.append(f"{f.name}:{m.group(1)}")
        for f in (self.studio / "vault" / "pipeline-runs").rglob("run.state.json"):
            if "current_stage" in f.read_text():
                found.append(f"{f}:current_stage")
        return found


# ───────────────────────────── AC1 ─────────────────────────────

class SourceFrontmatterTests(StageEradicationStudio):
    """AC1 — zero parsed stage keys; history stays byte-identical."""

    def test_migration_reaches_zero_stage_keys(self):
        self.plant_default_carriers()
        code, out, err = self.migrate("--apply")
        self.assertEqual(code, 0, f"apply failed: {err}")
        leftovers = [k for k in self.stage_keys_everywhere()
                     if "current_stage" not in k or "files" in k]
        # files must have no stage AND no current_stage; run.state no current_stage
        self.assertEqual(
            [k for k in self.stage_keys_everywhere() if k.split(":")[0] != "index"],
            [], "stage/current_stage survived source migration")

    def test_sole_legacy_stage_maps_through_declared_alias(self):
        self.file_record("aaaa0003", stage="build")  # no status
        self.migrate("--apply")
        text = (self.studio / "vault" / "files" / "aaaa0003.md").read_text()
        self.assertIn("status: active", text,
                      "declared alias build→active must become the status")
        self.assertNotIn("stage:", text)

    def test_redundant_stage_is_removed_status_preserved(self):
        self.file_record("aaaa0002", status="active", stage="build")
        self.migrate("--apply")
        text = (self.studio / "vault" / "files" / "aaaa0002.md").read_text()
        self.assertIn("status: active", text)
        self.assertNotIn("stage:", text)

    def test_disagreeing_stage_refuses_for_review(self):
        self.file_record("aaaa0004", status="closed", stage="build")
        code, out, err = self.migrate("--apply")
        self.assertNotEqual(code, 0,
                            "stage disagreeing with status must be refused, "
                            "not silently resolved")
        text = (self.studio / "vault" / "files" / "aaaa0004.md").read_text()
        self.assertIn("stage: build", text, "refused record is untouched")

    def test_bodies_and_prose_remain_byte_identical(self):
        self.plant_default_carriers()
        before = {f.name: f.read_bytes()
                  for f in (self.studio / "vault" / "files").glob("*.md")}
        self.migrate("--apply")
        after = {f.name: f.read_bytes()
                 for f in (self.studio / "vault" / "files").glob("*.md")}
        for name, was in before.items():
            head_before = was.split(b"---")[1]
            head_after = after[name].split(b"---")[1]
            body_before = was.split(b"---", 2)[2]
            body_after = after[name].split(b"---", 2)[2]
            self.assertEqual(body_before, body_after,
                             f"{name}: body changed under frontmatter-only "
                             "migration")
            self.assertNotEqual(head_before, head_after,
                                f"{name}: carrier head unchanged — control: "
                                "this test examined nothing")

    def test_reintroduced_stage_key_is_detected(self):
        self.plant_default_carriers()
        self.migrate("--apply")
        self.file_record("eeee0001", status="new", stage="inbox")
        code, out, _ = self.migrate("--dry-run")
        census = parse_json_out(out)
        self.assertTrue(census and census.get("stage_carriers", 0) > 0,
                        "census went blind to a reintroduced stage key")


# ───────────────────────────── AC2 ─────────────────────────────

class PipelinePositionTests(StageEradicationStudio):
    """AC2 — current_step only; the three UID positions round-trip."""

    def test_the_three_non_null_positions_round_trip_by_uid(self):
        for uid in NON_NULL_POSITIONS:
            self.pipeline_record(f"pos{uid}", current_stage=uid)
        self.migrate("--apply")
        for uid in NON_NULL_POSITIONS:
            text = (self.studio / "vault" / "files" / f"pos{uid}.md").read_text()
            self.assertIn(f"current_step: {uid}", text,
                          f"position {uid} did not round-trip")
            self.assertNotIn("current_stage", text)

    def test_null_positions_migrate_to_null_steps(self):
        self.pipeline_record("bbbb0001")
        self.run_state("run-x-2026-08-18")
        self.migrate("--apply")
        text = (self.studio / "vault" / "files" / "bbbb0001.md").read_text()
        self.assertIn("current_step: null", text)
        state = json.loads((self.studio / "vault" / "pipeline-runs" /
                            "run-x-2026-08-18" / "run.state.json").read_text())
        self.assertIn("current_step", state)
        self.assertNotIn("current_stage", state)

    def test_runtime_state_round_trips_existing_step_values(self):
        self.run_state("run-y-2026-08-18", current_step="11112222")
        self.migrate("--apply")
        state = json.loads((self.studio / "vault" / "pipeline-runs" /
                            "run-y-2026-08-18" / "run.state.json").read_text())
        self.assertEqual(state.get("current_step"), "11112222")

    def test_runtime_emits_no_current_stage_after_cutover(self):
        """The production runtime state shape must not carry current_stage."""
        src = (REPO / "vault" / "tools" / "9e7003b1.py").read_text()
        self.assertNotIn(
            '"current_stage"', src,
            "runtime still writes a current_stage key; the write path is the "
            "axis recreating itself after every cleanup")

    def test_control_the_scans_examine_something(self):
        self.plant_default_carriers()
        code, out, _ = self.migrate("--dry-run")
        census = parse_json_out(out)
        self.assertIsNotNone(census, "dry-run produced no census JSON")
        self.assertGreater(census.get("stage_carriers", 0), 0)
        self.assertGreater(census.get("current_stage_sources", 0), 0)
        self.assertGreater(census.get("runtime_state_carriers", 0), 0)


# ───────────────────────────── AC3 ─────────────────────────────

class IndexProjectionTests(StageEradicationStudio):
    """AC3 — the index emits no stage anywhere and never synthesizes ideate."""

    def setUp(self):
        super().setUp()
        # The real rebuild needs its support tree; copy the minimum.
        for name in ("tropo-rebuild-index.py", "rehydrate.py"):
            src = REPO / "vault" / "tools" / name
            if src.is_file():
                shutil.copy(src, self.studio / "vault" / "tools" / name)
        lib = self.studio / "vault" / "tools" / "lib"
        lib.mkdir(exist_ok=True)
        real_lib = REPO / "vault" / "tools" / "lib"
        if real_lib.is_dir():
            for p in real_lib.glob("*.py"):
                shutil.copy(p, lib / p.name)

    def test_full_rebuild_emits_zero_stage_keys(self):
        # Index-door tests plant work items only: pipeline-run records carry
        # capsule-required fields this minimal fixture does not model, and the
        # projection under test is the work-item stage key.
        self.file_record("aaaa0001", status="new", stage="inbox")
        self.file_record("aaaa0002", status="active", stage="build")
        self.migrate("--apply")
        code, out, err = self.rebuild()
        self.assertEqual(code, 0, f"rebuild failed: {err[-500:]}")
        stage_keys = [k for k in self.stage_keys_everywhere()
                      if k.startswith("index:")]
        self.assertEqual(stage_keys, [],
                         f"index still projects stage keys: {stage_keys}")

    def test_no_row_is_costumed_as_ideate(self):
        # A record whose status the projector does not know must surface as a
        # finding, never be fabricated into ideate.
        self.file_record("ffff0001", status="flibberish")
        code, out, err = self.rebuild()
        self.assertEqual(code, 0)
        rows = [r for r in self.index_rows() if r.get("uid") == "ffff0001"]
        self.assertTrue(rows, "control: the record reached the index")
        self.assertNotIn("stage", rows[0])
        self.assertNotIn("ideate", json.dumps(rows[0]).lower(),
                         "unknown status was costumed as ideate")

    def test_meta_status_still_derives_from_status(self):
        self.file_record("aaaa0002", status="active")
        self.rebuild()
        rows = [r for r in self.index_rows() if r.get("uid") == "aaaa0002"]
        self.assertTrue(rows)
        self.assertIn(str(rows[0].get("meta_status", "")).lower(), "active")

    def test_the_normalizer_is_gone_not_dormant(self):
        """Restoring normalize_stage_state must turn red (AC3 evidence line).
        Absence is the assertion, same class as the retired R-3 control: a
        dormant function is one rename away from being wired back in."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "rebuild_mod", REPO / "vault" / "tools" / "tropo-rebuild-index.py")
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass  # module may exit on arg parsing in import context; hasattr still works
        self.assertFalse(
            hasattr(mod, "normalize_stage_state"),
            "normalize_stage_state is back: the stage axis has a factory "
            "waiting to be re-wired")

    def test_sqlite_has_no_stage_column(self):
        self.file_record("aaaa0002", status="active")
        self.rebuild()
        db = self.studio / "vault" / "00-index.sqlite"
        if not db.exists():
            self.skipTest("sqlite not produced for this fixture")
        con = sqlite3.connect(str(db))
        cols = [r[1] for r in con.execute("PRAGMA table_info(entries)")]
        con.close()
        self.assertNotIn("stage", [c.lower() for c in cols],
                         "SQLite entries.stage survived the cutover")


# ───────────────────────────── AC6 ─────────────────────────────

class MigrationSafetyTests(StageEradicationStudio):
    """AC6 — dry-run-first, journaled, idempotent, reversible, CAS-guarded."""

    def test_dry_run_writes_nothing(self):
        self.plant_default_carriers()
        before = {f.name: f.read_bytes()
                  for f in (self.studio / "vault" / "files").glob("*.md")}
        code, out, err = self.migrate("--dry-run")
        self.assertEqual(code, 0)
        after = {f.name: f.read_bytes()
                 for f in (self.studio / "vault" / "files").glob("*.md")}
        self.assertEqual(before, after, "dry-run mutated sources")

    def test_second_apply_is_a_noop(self):
        self.plant_default_carriers()
        self.migrate("--apply")
        first = {f.name: f.read_bytes()
                 for f in (self.studio / "vault" / "files").glob("*.md")}
        code, out, _ = self.migrate("--apply")
        self.assertEqual(code, 0)
        result = parse_json_out(out)
        self.assertEqual(result.get("changed", -1), 0,
                         "second apply changed records — not idempotent")
        second = {f.name: f.read_bytes()
                  for f in (self.studio / "vault" / "files").glob("*.md")}
        self.assertEqual(first, second)

    def test_rollback_restores_exact_bytes(self):
        self.plant_default_carriers()
        before = sorted(
            (str(f.relative_to(self.studio)), f.read_bytes())
            for f in self.studio.rglob("*.md"))
        before += sorted(
            (str(f.relative_to(self.studio)), f.read_bytes())
            for f in self.studio.rglob("run.state.json"))
        self.migrate("--apply")
        code, out, err = self.migrate("--rollback")
        self.assertEqual(code, 0, f"rollback failed: {err}")
        after = sorted(
            (str(f.relative_to(self.studio)), f.read_bytes())
            for f in self.studio.rglob("*.md"))
        after += sorted(
            (str(f.relative_to(self.studio)), f.read_bytes())
            for f in self.studio.rglob("run.state.json"))
        self.assertEqual(after, before, "rollback did not restore exact bytes")

    def test_changed_source_bytes_are_refused(self):
        self.plant_default_carriers()
        code, out, _ = self.migrate("--dry-run")
        # Tamper between plan and apply: CAS must refuse, not clobber.
        target = self.studio / "vault" / "files" / "aaaa0002.md"
        target.write_text(target.read_text().replace("status: active",
                                                     "status: paused"))
        code, out, err = self.migrate("--apply")
        self.assertNotEqual(code, 0,
                            "apply clobbered a source that changed after the "
                            "plan was written")

    def test_malformed_frontmatter_is_refused_not_guessed(self):
        (self.studio / "vault" / "files" / "zzzz0001.md").write_text(
            "---\nuid: zzzz0001\ntype: note\nstage: build\n", encoding="utf-8")
        code, _, err = self.migrate("--apply")
        self.assertNotEqual(code, 0,
                            "unterminated frontmatter must refuse, never "
                            "parse by approximation")


# ───────────────────────────── AC7 ─────────────────────────────

class ActiveSourceVocabularyTests(StageEradicationStudio):
    """AC7 — the scanner classifies external meanings; new stage use fails."""

    def _scanner(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("migrate_mod", MIGRATE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_git_plumbing_and_release_staging_are_classified_not_flagged(self):
        mod = self._scanner()
        allowed = mod.classify_stage_token("run git ls-files --stage to list")
        self.assertEqual(allowed, "git-plumbing")
        self.assertEqual(
            mod.classify_stage_token("release stage: tropo-stage-release.py"),
            "release-staging")

    def test_new_work_item_stage_use_is_flagged(self):
        mod = self._scanner()
        self.assertEqual(mod.classify_stage_token("stage: build"),
                         "lifecycle-residue")

    def test_scanner_flags_a_new_stage_field_in_active_code(self):
        # A new work-item stage read/write in app code must be caught by the
        # scanner, not pass as historical prose.
        probe = self.studio / "work.tsx"
        probe.write_text("const stage = item.stage;\n", encoding="utf-8")
        mod = self._scanner()
        hits = mod.scan_active_source_for_stage_reads(str(probe))
        self.assertTrue(hits, "a fresh stage read in active code passed")

    def test_control_classification_is_not_a_tautology(self):
        mod = self._scanner()
        # If everything classified as one class, the tests above lie.
        classes = {mod.classify_stage_token(t) for t in (
            "stage: build", "git ls-files --stage", "stage the release")}
        self.assertGreater(len(classes), 1,
                           "classifier collapsed every token to one class")


if __name__ == "__main__":
    unittest.main()
