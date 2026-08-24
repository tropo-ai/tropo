#!/usr/bin/env python3
"""v1.91 S1 AC4 (0a0e94d1) — ONE debt question, ONE predicate.

Argus F-02: the build ratchet (test_post_migration_release_clean.py — the
debt ceiling gate Step 0a runs) and the release-validation gate
(tropo-release-validation-gate.py compare — step 4262d5fa's verifier) are
two predicates for one question: "did validator debt get worse?" They
disagreed three times on v1.90 — one passing while the other refused.

The contract: both call sites resolve their verdict through ONE function in
ONE module (lib/debt_rule.py). Red at birth: the module does not exist.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
STUDIO = TOOLS.parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _source(path: str) -> str:
    return (STUDIO / path).read_text(encoding="utf-8")


class SingleDebtRuleTests(unittest.TestCase):
    def test_the_one_module_exists_and_exports_the_verdict(self) -> None:
        try:
            from lib import debt_rule
        except ImportError as exc:
            self.fail(
                f"lib/debt_rule.py does not exist — the one debt question has "
                f"no one predicate (S1 AC4, Argus F-02): {exc}")
        self.assertTrue(
            hasattr(debt_rule, "debt_verdict"),
            "lib/debt_rule.py must export debt_verdict(current_failed, "
            "ceiling, gating_growth) -> DebtVerdict")

    def test_build_ratchet_calls_the_one_predicate(self) -> None:
        src = _source("vault/tools/tests/test_post_migration_release_clean.py")
        self.assertIn(
            "debt_verdict",
            src,
            "the build-ratchet call site (Step 0a's gate) must resolve its "
            "verdict through lib.debt_rule — a private copy of the rule is "
            "the second-reader defect this AC closes")

    def test_release_gate_calls_the_one_predicate(self) -> None:
        src = _source("vault/tools/tropo-release-validation-gate.py")
        self.assertIn(
            "debt_verdict",
            src,
            "the release-validation gate (step 4262d5fa's verifier) must "
            "resolve its verdict through lib.debt_rule — two predicates for "
            "one question refused while the other passed (F-02)")

    def test_the_rule_itself(self) -> None:
        from lib import debt_rule
        # gating-class growth always fails
        v = debt_rule.debt_verdict(current_failed=10, ceiling=8, gating_growth=1)
        self.assertFalse(v.ok)
        self.assertIn("gating", v.reason)
        # total growth with no gating growth still fails (no technicality pass)
        v = debt_rule.debt_verdict(current_failed=10, ceiling=8, gating_growth=0)
        self.assertFalse(v.ok)
        # equal passes; improvement passes with direction=down
        self.assertTrue(debt_rule.debt_verdict(8, 8, 0).ok)
        v = debt_rule.debt_verdict(6, 8, 0)
        self.assertTrue(v.ok)
        self.assertEqual(v.direction, "down")


if __name__ == "__main__":
    unittest.main()
