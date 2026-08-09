#!/usr/bin/env python3
"""Property + fault plants for the memory-reinforcement feature (dev-spec 47c26a60).

Built by talos-t35 under the LOCKED memory-reinforcement dev-spec 47c26a60
(activation b233b7ac; Mike-endorsed + Mike-authorized memory.capsule v1.6
lock-break). Paired test-spec: 5c462e0d.

Stdlib `unittest` only — no pytest dependency. Run with either:

    python3 -m unittest test_memory_reinforcement          # from vault/tools/tests/
    python3 vault/tools/tests/test_memory_reinforcement.py  # direct

What this proves (one class per dev-spec acceptance criterion, 1-based):

  AC1  REINFORCE FIELD ............ capsule documents both fields; validator checks
                                    reinforcement_count is a non-negative int and
                                    reinforced_by is well-formed; a non-curator write
                                    surfaces the same discipline finding as score/tier.
  AC2  MERGE INCREMENTS + LINEAGE . a ratified MERGE bumps the survivor by
                                    (merged.reinforcement_count + 1) and appends the
                                    merged generation(s) to reinforced_by (dedup); an
                                    unratified/rejected merge changes neither field.
  AC3  SCORE INTEGRATION .......... the composite gains a log-compressed reinforce term;
                                    the five weights sum to EXACTLY 1.0; the score is
                                    monotonic in reinforcement_count and never negative.
  AC4  DISTINCT SIGNAL ............ reinforcement_count is never conflated with
                                    reference_count; the doctrine states the distinction.
  AC5  SEEDING .................... an evidence-backed backfill sets reinforcement_count
                                    from distinct contributing generations and refuses to
                                    fabricate a count when there is no evidence.
  AC6  NO RUNAWAY BY CONSTRUCTION . every increment is gated by ratification (no
                                    auto-increment) and log-compression bounds any single
                                    entry's contribution.
  AC7  NON-DESTRUCTIVE ............ the reinforced_by lineage preserves every contributing
                                    generation (auditable); the curator archives, never
                                    destroys, the merged-away entry.

The reference model below (REINFORCE_CAP, weights, reinforce_signal, composite_score,
merge_reinforce, seed_from_evidence) is the canonical encoding of score-formula-doctrine
v1.1 (5f2c1b94) + sa.memory-curator v1.2 (50c0bdce) Phase 2/6/7. The doctrine/capsule/
curator source files are separately parsed so the tests FAIL LOUD if the shipped
substrate ever drifts from this model (e.g. weights stop summing to 1.0).
"""
from __future__ import annotations

import importlib.util
import math
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# Locate substrate + import the (hyphenated) validator by path.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]
DOCTRINE_PATH = ROOT / ".tropo-studio" / "score-formula-doctrine.md"
CAPSULE_PATH = ROOT / "vault" / "capsules" / "tropo-memory.capsule.md"
CURATOR_PATH = ROOT / "vault" / "session-agents" / "50c0bdce.md"
VALIDATE_PATH = ROOT / "vault" / "tools" / "tropo-validate.py"

_spec = importlib.util.spec_from_file_location("tropo_validate_mr_tests", VALIDATE_PATH)
tropo_validate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(tropo_validate)


# ===========================================================================
# Reference model — canonical encoding of doctrine v1.1 + curator v1.2.
# ===========================================================================
REINFORCE_CAP = 100

# v1.1 five-weight allocation (score-formula-doctrine 5f2c1b94; MUST sum to 1.0).
WEIGHTS = {
    "recency": 0.20,
    "usage": 0.30,
    "pin": 0.25,
    "reinforce": 0.15,
    "subtype": 0.10,
}


def reinforce_signal(reinforcement_count: int, cap: int = REINFORCE_CAP) -> float:
    """Signal 4 — log-compressed recurrence, normalized by cap, clamped to 1.0."""
    return min(
        math.log10(max(reinforcement_count, 1)) / math.log10(cap),
        1.0,
    )


def composite_score(
    *,
    age_decay: float,
    usage_normalized: float,
    wilson: float,
    reinforcement_count: int,
    subtype_weight: float,
) -> float:
    """The v1.1 five-signal composite. reinforcement_count is a DISTINCT input
    from reference_count (usage_normalized) — never summed into one counter."""
    return (
        WEIGHTS["recency"] * age_decay
        + WEIGHTS["usage"] * usage_normalized
        + WEIGHTS["pin"] * wilson
        + WEIGHTS["reinforce"] * reinforce_signal(reinforcement_count)
        + WEIGHTS["subtype"] * subtype_weight
    )


def merge_reinforce(survivor: dict, merged: dict, *, ratified: bool) -> dict:
    """sa.memory-curator Phase 7 MERGE reinforcement increment.

    On a human-ratified merge only: survivor.reinforcement_count +=
    (merged.reinforcement_count + 1); merged's contributing generation(s) append
    (deduplicated, order-preserving) to survivor.reinforced_by. A rejected/deferred
    merge is a no-op on BOTH fields. Returns the survivor's new curator-mutable state.
    """
    s_count = int(survivor.get("reinforcement_count", 0) or 0)
    s_lineage = list(survivor.get("reinforced_by", []) or [])
    if not ratified:
        return {"reinforcement_count": s_count, "reinforced_by": s_lineage}
    m_count = int(merged.get("reinforcement_count", 0) or 0)
    m_lineage = list(merged.get("reinforced_by", []) or [])
    m_generations = list(merged.get("generations", []) or [])
    new_count = s_count + m_count + 1
    # order-preserving dedup
    new_lineage = list(dict.fromkeys(s_lineage + m_lineage + m_generations))
    return {"reinforcement_count": new_count, "reinforced_by": new_lineage}


def seed_from_evidence(evidence_generations: list[str]) -> dict:
    """Evidence-backed one-time backfill (dev-spec §Design.5).

    Sets reinforcement_count from the DISTINCT contributing generations recorded
    as evidence; refuses to fabricate a count when there is no evidence.
    """
    if not evidence_generations:
        raise ValueError(
            "seeding is evidence-backed only — refuse to fabricate a count"
        )
    distinct = list(dict.fromkeys(evidence_generations))
    return {"reinforcement_count": len(distinct), "reinforced_by": distinct}


# ---------------------------------------------------------------------------
# Temp-vault helper for validator integration plants.
# ---------------------------------------------------------------------------
class TempVault:
    """Minimal on-disk vault so check_memory_typing() can sweep planted entries."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="mem_reinforce_"))
        (self.root / ".tropo-studio" / "memory" / "entries").mkdir(parents=True)
        (self.root / "vault" / "files").mkdir(parents=True)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def write_entry(self, uid: str, frontmatter_lines: list[str], body: str = "A durable rule.") -> Path:
        path = self.root / ".tropo-studio" / "memory" / "entries" / f"{uid}.md"
        fm = "\n".join(frontmatter_lines)
        path.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")
        return path

    def findings(self) -> list[str]:
        out, _checked, _defects = tropo_validate.check_memory_typing(self.root)
        return out


def _base_entry_lines(uid: str, **overrides) -> list[str]:
    """A well-formed v1.6 memory entry; overrides replace/add frontmatter lines."""
    fields = {
        "uid": uid,
        "type": "memory",
        "subtype": "feedback",
        "scope": "studio",
        "context": "reinforcement test fixture",
        "created": "2026-07-22",
        "state": "active",
    }
    fields.update(overrides)
    return [f"{k}: {v}" for k, v in fields.items()]


# ===========================================================================
# AC1 — REINFORCE FIELD
# ===========================================================================
class TestAC1ReinforceField(unittest.TestCase):
    def test_capsule_documents_both_fields(self):
        text = CAPSULE_PATH.read_text(encoding="utf-8")
        self.assertRegex(text, r"\|\s*`reinforcement_count`\s*\|", "capsule Optional Frontmatter must document reinforcement_count")
        self.assertRegex(text, r"\|\s*`reinforced_by`\s*\|", "capsule Optional Frontmatter must document reinforced_by")
        # curator-mutable governance + version bump
        self.assertIn("reinforcement_count", text)
        self.assertIn("reinforced_by", text)
        self.assertRegex(text, r"(?m)^version:\s*1\.6\s*$", "capsule must be v1.6")

    def test_validator_reinforcement_count_must_be_nonneg_int(self):
        vault = TempVault()
        try:
            vault.write_entry("aaaa1101", _base_entry_lines("aaaa1101", reinforcement_count="-3", modified_by="sa.memory-curator-009"))
            vault.write_entry("aaaa1102", _base_entry_lines("aaaa1102", reinforcement_count="3.5", modified_by="sa.memory-curator-009"))
            vault.write_entry("aaaa1103", _base_entry_lines("aaaa1103", reinforcement_count="abc", modified_by="sa.memory-curator-009"))
            vault.write_entry("aaaa1104", _base_entry_lines("aaaa1104", reinforcement_count="0", modified_by="sa.memory-curator-009"))
            vault.write_entry("aaaa1105", _base_entry_lines("aaaa1105", reinforcement_count="12", modified_by="sa.memory-curator-009"))
            findings = vault.findings()
        finally:
            vault.close()
        joined = "\n".join(findings)
        for bad in ("aaaa1101", "aaaa1102", "aaaa1103"):
            self.assertTrue(
                any(bad in f and "reinforcement_count" in f and "non-negative integer" in f for f in findings),
                f"expected non-negative-integer WARN for {bad}; got:\n{joined}",
            )
        for good in ("aaaa1104", "aaaa1105"):
            self.assertFalse(
                any(good in f and "non-negative integer" in f for f in findings),
                f"unexpected non-negative-integer WARN for {good}",
            )

    def test_validator_reinforced_by_wellformed(self):
        vault = TempVault()
        try:
            # scalar (not a list) -> WARN
            vault.write_entry("aaaa1201", _base_entry_lines("aaaa1201", reinforced_by="A115", modified_by="sa.memory-curator-009"))
            # blank entry in list -> WARN
            vault.write_entry("aaaa1202", _base_entry_lines("aaaa1202", reinforced_by='[A115, ""]', modified_by="sa.memory-curator-009"))
            # well-formed list -> no WARN
            vault.write_entry("aaaa1203", _base_entry_lines("aaaa1203", reinforced_by="[A115, A124, A129]", modified_by="sa.memory-curator-009"))
            findings = vault.findings()
        finally:
            vault.close()
        joined = "\n".join(findings)
        self.assertTrue(any("aaaa1201" in f and "reinforced_by" in f for f in findings), f"scalar reinforced_by must WARN:\n{joined}")
        self.assertTrue(any("aaaa1202" in f and "reinforced_by" in f for f in findings), f"blank label must WARN:\n{joined}")
        self.assertFalse(any("aaaa1203" in f and "reinforced_by" in f for f in findings), "well-formed reinforced_by must NOT WARN")

    def test_noncurator_write_flagged_same_as_score_tier(self):
        """AC1: a non-curator write to reinforcement_count surfaces the SAME
        discipline finding class as the other curator-mutable fields."""
        vault = TempVault()
        try:
            # non-curator writer with reinforcement_count -> discipline WARN
            vault.write_entry("aaaa1301", _base_entry_lines("aaaa1301", reinforcement_count="4", modified_by="talos-t99"))
            # curator writer -> NO discipline WARN
            vault.write_entry("aaaa1302", _base_entry_lines("aaaa1302", reinforcement_count="4", modified_by="sa.memory-curator-009"))
            # non-curator writer with score/tier only -> SAME discipline WARN class
            vault.write_entry("aaaa1303", _base_entry_lines("aaaa1303", score="0.5", tier="current", modified_by="talos-t99"))
            findings = vault.findings()
        finally:
            vault.close()
        joined = "\n".join(findings)
        disc = "curator-mutable-field discipline"
        self.assertTrue(
            any("aaaa1301" in f and disc in f and "reinforcement_count" in f for f in findings),
            f"non-curator reinforcement_count write must surface discipline WARN:\n{joined}",
        )
        self.assertFalse(
            any("aaaa1302" in f and disc in f for f in findings),
            "curator write must NOT surface discipline WARN",
        )
        self.assertTrue(
            any("aaaa1303" in f and disc in f for f in findings),
            "score/tier non-curator write must surface the SAME discipline WARN class",
        )


# ===========================================================================
# AC2 — MERGE INCREMENTS + LINEAGE
# ===========================================================================
class TestAC2MergeIncrementsAndLineage(unittest.TestCase):
    def test_ratified_merge_increments_by_merged_plus_one(self):
        survivor = {"reinforcement_count": 2, "reinforced_by": ["A115", "A124"]}
        merged = {"reinforcement_count": 3, "generations": ["A129"]}
        result = merge_reinforce(survivor, merged, ratified=True)
        # 2 + (3 + 1) = 6
        self.assertEqual(result["reinforcement_count"], 6)

    def test_ratified_merge_appends_generation_lineage_dedup(self):
        survivor = {"reinforcement_count": 1, "reinforced_by": ["A115", "A124"]}
        merged = {"reinforcement_count": 0, "reinforced_by": ["A124"], "generations": ["A129", "A135"]}
        result = merge_reinforce(survivor, merged, ratified=True)
        # A124 already present -> deduplicated; order preserved
        self.assertEqual(result["reinforced_by"], ["A115", "A124", "A129", "A135"])

    def test_unratified_merge_touches_neither_field(self):
        survivor = {"reinforcement_count": 5, "reinforced_by": ["A115"]}
        merged = {"reinforcement_count": 9, "generations": ["A200"]}
        result = merge_reinforce(survivor, merged, ratified=False)
        self.assertEqual(result["reinforcement_count"], 5)
        self.assertEqual(result["reinforced_by"], ["A115"])

    def test_curator_documents_merge_increment_rule(self):
        text = CURATOR_PATH.read_text(encoding="utf-8")
        self.assertIn("reinforcement_count", text)
        self.assertIn("reinforced_by", text)
        # the +=(merged+1) rule and the reject/defer no-op must be documented
        self.assertRegex(text, r"reinforcement_count\s*\+?=?.*merged", "curator must document the += (merged + 1) rule")
        self.assertRegex(text, r"(REJECT|reject).*(DEFER|defer).*(NEITHER|neither)", "curator must document reject/defer no-op")


# ===========================================================================
# AC3 — SCORE INTEGRATION
# ===========================================================================
class TestAC3ScoreIntegration(unittest.TestCase):
    def test_weight_sum_invariant_reference(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0, places=9,
                               msg="reference weights must sum to exactly 1.0")

    def test_weight_sum_invariant_doctrine_file(self):
        """FAIL LOUD if the shipped doctrine ever stops summing to 1.0."""
        text = DOCTRINE_PATH.read_text(encoding="utf-8")
        weights = {}
        for name in ("w_recency", "w_usage", "w_pin", "w_reinforce", "w_subtype"):
            m = re.search(rf"`{name}`\s*\|\s*([0-9.]+)\s*\|", text)
            self.assertIsNotNone(m, f"doctrine must declare {name} in the weight table")
            weights[name] = float(m.group(1))
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=9,
                               msg=f"doctrine weights must sum to 1.0; got {weights}")
        # doctrine weights must match the reference model
        self.assertEqual(weights["w_reinforce"], WEIGHTS["reinforce"])

    def test_weight_sum_invariant_capsule_mirror(self):
        text = CAPSULE_PATH.read_text(encoding="utf-8")
        vals = []
        for name in ("w_recency", "w_usage", "w_pin", "w_reinforce", "w_subtype"):
            m = re.search(rf"`{name}\s*=\s*([0-9.]+)`", text)
            self.assertIsNotNone(m, f"capsule score-formula mirror must declare {name}")
            vals.append(float(m.group(1)))
        self.assertAlmostEqual(sum(vals), 1.0, places=9,
                               msg=f"capsule contract-mirror weights must sum to 1.0; got {vals}")

    def test_score_monotonic_and_never_negative_in_reinforcement(self):
        prev = -1.0
        for rc in range(0, 151):
            score = composite_score(
                age_decay=0.5, usage_normalized=0.4, wilson=0.2,
                reinforcement_count=rc, subtype_weight=0.7,
            )
            self.assertGreaterEqual(score, 0.0, "score is never negative")
            self.assertGreaterEqual(round(score, 12), round(prev, 12),
                                    f"score must be monotonic non-decreasing in reinforcement_count (rc={rc})")
            prev = score

    def test_higher_reinforcement_scores_at_least_as_high(self):
        low = composite_score(age_decay=0.9, usage_normalized=0.5, wilson=0.2, reinforcement_count=0, subtype_weight=0.9)
        high = composite_score(age_decay=0.9, usage_normalized=0.5, wilson=0.2, reinforcement_count=10, subtype_weight=0.9)
        self.assertGreater(high, low, "reinforcement_count=10 must outrank =0, all else equal")


# ===========================================================================
# AC4 — DISTINCT SIGNAL (reads != re-learns)
# ===========================================================================
class TestAC4DistinctSignal(unittest.TestCase):
    def test_reinforcement_independent_of_reference_count(self):
        """Varying reinforcement_count changes only the reinforce term; varying
        usage changes only the usage term. The two signals never cross-wire."""
        base = composite_score(age_decay=0.5, usage_normalized=0.4, wilson=0.2, reinforcement_count=0, subtype_weight=0.7)
        more_reads = composite_score(age_decay=0.5, usage_normalized=0.9, wilson=0.2, reinforcement_count=0, subtype_weight=0.7)
        more_relearns = composite_score(age_decay=0.5, usage_normalized=0.4, wilson=0.2, reinforcement_count=50, subtype_weight=0.7)
        self.assertAlmostEqual(more_reads - base, WEIGHTS["usage"] * (0.9 - 0.4), places=9)
        self.assertAlmostEqual(more_relearns - base, WEIGHTS["reinforce"] * reinforce_signal(50), places=9)

    def test_doctrine_states_distinction_explicitly(self):
        text = DOCTRINE_PATH.read_text(encoding="utf-8")
        self.assertRegex(text, r"[Dd]istinct", "doctrine must state reinforcement is distinct")
        self.assertRegex(text, r"reads.*re-learns|re-learns.*reads", "doctrine must state reads != re-learns explicitly")
        # reinforce_signal formula + cap present
        self.assertIn("reinforce_signal", text)
        self.assertRegex(text, r"reinforce_cap\s*=\s*100")


# ===========================================================================
# AC5 — SEEDING (evidence-backed backfill)
# ===========================================================================
class TestAC5Seeding(unittest.TestCase):
    def test_seed_from_evidence_counts_distinct_generations(self):
        result = seed_from_evidence(["A115", "A124", "A129", "A135"])
        self.assertEqual(result["reinforcement_count"], 4)
        self.assertEqual(result["reinforced_by"], ["A115", "A124", "A129", "A135"])

    def test_seed_dedups_repeated_evidence(self):
        result = seed_from_evidence(["A115", "A124", "A115"])
        self.assertEqual(result["reinforcement_count"], 2)
        self.assertEqual(result["reinforced_by"], ["A115", "A124"])

    def test_seed_refuses_to_fabricate_without_evidence(self):
        with self.assertRaises(ValueError):
            seed_from_evidence([])


# ===========================================================================
# AC6 — NO RUNAWAY BY CONSTRUCTION
# ===========================================================================
class TestAC6NoRunaway(unittest.TestCase):
    def test_increment_gated_by_ratification(self):
        survivor = {"reinforcement_count": 7, "reinforced_by": ["A1"]}
        merged = {"reinforcement_count": 100, "generations": ["A2"]}
        # Without ratification, no increment can happen (no auto-increment).
        self.assertEqual(merge_reinforce(survivor, merged, ratified=False)["reinforcement_count"], 7)

    def test_log_compression_caps_single_entry_contribution(self):
        # zero and one are both zero (one occurrence is not a recurrence)
        self.assertEqual(reinforce_signal(0), 0.0)
        self.assertEqual(reinforce_signal(1), 0.0)
        # monotonic up to saturation at the cap
        self.assertAlmostEqual(reinforce_signal(10), 0.5, places=9)
        self.assertAlmostEqual(reinforce_signal(100), 1.0, places=9)
        # beyond the cap saturates at 1.0 (never exceeds)
        self.assertEqual(reinforce_signal(10_000), 1.0)
        # the max possible reinforce contribution to score is bounded by its weight
        max_contrib = WEIGHTS["reinforce"] * reinforce_signal(10**9)
        self.assertLessEqual(max_contrib, WEIGHTS["reinforce"])

    def test_curator_documents_no_autoincrement(self):
        text = CURATOR_PATH.read_text(encoding="utf-8")
        self.assertRegex(text, r"NO RUNAWAY|no auto-merge|no write-time|human-ratified",
                         "curator must document that increments are ratification-gated")


# ===========================================================================
# AC7 — NON-DESTRUCTIVE (auditable lineage)
# ===========================================================================
class TestAC7NonDestructive(unittest.TestCase):
    def test_lineage_preserves_every_contributing_generation(self):
        survivor = {"reinforcement_count": 0, "reinforced_by": ["A115"]}
        # chain three ratified merges; every contributing generation stays auditable
        survivor = merge_reinforce(survivor, {"reinforcement_count": 0, "generations": ["A124"]}, ratified=True)
        survivor = merge_reinforce(survivor, {"reinforcement_count": 0, "generations": ["A129"]}, ratified=True)
        survivor = merge_reinforce(survivor, {"reinforcement_count": 0, "generations": ["A135"]}, ratified=True)
        self.assertEqual(survivor["reinforcement_count"], 3)
        self.assertEqual(survivor["reinforced_by"], ["A115", "A124", "A129", "A135"])

    def test_curator_documents_archive_not_destroy(self):
        text = CURATOR_PATH.read_text(encoding="utf-8")
        self.assertRegex(text, r"archived, not destroyed|archived.*not.*destroy",
                         "curator must document merged entry is archived, not destroyed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
