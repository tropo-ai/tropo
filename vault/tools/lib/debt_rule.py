"""v1.91 S1 AC4 (0a0e94d1) — THE one debt predicate.

Argus F-02: two predicates for one question ("did validator debt get
worse?") disagreed three times on v1.90 — the build ratchet passing while
the release-validation gate refused. This module is the one answer both call
sites resolve through:

  * the build's Step 0a ratchet (test_post_migration_release_clean.py)
  * the release-validation gate (tropo-release-validation-gate.py compare —
    step 4262d5fa's verifier)

The rule, in words: growth in a GATING class fails; total growth with no
gating growth still fails (a gate that finds a technicality to say yes is
the failure mode); equal passes; improvement passes and says so. No caller
may keep a private copy — two readers of one journal cannot return
different answers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DebtVerdict:
    ok: bool
    reason: str
    direction: Optional[str] = None  # "down" when debt improved


def debt_verdict(
    current_failed: int,
    ceiling: int,
    gating_growth: int = 0,
) -> DebtVerdict:
    """The one answer to the one debt question.

    `current_failed` — this run's enumerable failure count.
    `ceiling` — the recorded baseline the ratchet allows.
    `gating_growth` — new findings in gating classes (the per-class delta);
    excused-class growth arrives as total growth with zero gating growth and
    is still refused: honest reporting, never a technicality pass.
    """
    if gating_growth > 0:
        return DebtVerdict(
            False,
            f"{gating_growth} new finding(s) in gating classes — pay it "
            f"down, re-record the baseline with the reason, or excuse the "
            f"class by recorded decision",
        )
    if current_failed > ceiling:
        return DebtVerdict(
            False,
            f"studio debt UP {current_failed - ceiling}, from {ceiling} to "
            f"{current_failed}, with no gating class grown — growth inside "
            f"excused classes or an unattributed shape; either way the "
            f"ceiling does not allow it",
        )
    if current_failed < ceiling:
        return DebtVerdict(
            True,
            f"studio debt DOWN {ceiling - current_failed} from the recorded "
            f"baseline — re-record to lock the gain in",
            direction="down",
        )
    return DebtVerdict(True, f"studio debt unchanged at {current_failed}")
