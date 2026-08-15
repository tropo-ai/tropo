"""Tree identity for verification evidence (0a0a6777 AC3; argus-a147 boundary 3).

THE RULING THIS IMPLEMENTS
--------------------------
Terminal-only stamping is weaker than locked AC3: it lets different ACs pass on
different trees without the terminal having the provenance to notice. So the
binding is pushed down to the emitter — every `verification_receipt` and every
verification-class natural verdict records the exact 40-hex commit whose CLEAN
tree the command exercised, and the terminal only AGGREGATES that provenance. It
never invents it.

WHAT "TESTED" HAS TO MEAN
-------------------------
A receipt saying `tested_commit_sha: <x>` is claiming: this command ran against
the tree of commit x, and that tree did not move while it ran. Three things can
break that claim, and they are NOT the same failure:

  dirty      the working tree differs from HEAD, so no commit describes what ran
  moved      the tree changed DURING execution, so no single commit describes it
  unknown    this is not a git work tree, or git could not be consulted

Each is recorded distinctly. Folding them into one "no SHA" would lose the
distinction between "I cannot see" and "you are wrong", and `.tropo` doctrine is
explicit that those are different verdicts.

WHY THIS WARNS AND THE TERMINAL REFUSES (deb77758)
--------------------------------------------------
Mike's warn-safe ruling: a refusal must name the irreversible harm it prevents,
or be a warning that proceeds and records. Refusing to RUN a verification command
on a dirty tree would sit on the hottest path in the studio — every step
verification during ordinary development — and the harm it prevents at that
moment is zero, because nobody has believed anything yet.

The harm appears later, at the terminal, where a mixed or missing SHA would let a
release believe ACs passed together on one tree when they did not. That is the
false-success class deb77758 names as earning fail-closed. So:

    emitter  runs, records what it can prove, and NEVER invents a SHA (warn)
    terminal refuses on missing or mixed provenance (fail-closed, harm named)

The rule Argus stated — "do not invent a commit for dirty work; refuse and
require a committed clean test subject" — is honored exactly: no receipt ever
carries a SHA it cannot substantiate, and a dirty-tree receipt can never satisfy
the terminal. What moves is WHERE the refusal fires, from the hot path to the
believing point.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

COMMIT_RE_LEN = 40


@dataclass(frozen=True)
class TreeIdentity:
    """What a commit-shaped claim about a working tree can honestly say."""

    commit_sha: Optional[str]  # 40-hex ONLY when the tree is clean at that commit
    state: str                 # "clean" | "dirty" | "unknown"
    detail: str = ""

    @property
    def is_bindable(self) -> bool:
        """May a receipt cite this as its tested tree?"""
        return self.state == "clean" and bool(self.commit_sha)


def _git(args: list[str], cwd: str | Path) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30,
        )
        return result.returncode, (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"


def read_tree_identity(cwd: str | Path = ".") -> TreeIdentity:
    """The tree's identity right now, stated honestly.

    Never raises and never guesses. A repo that cannot be consulted yields
    `unknown`, which is a third answer — not a quiet `dirty`, and certainly not a
    commit we would then attach to evidence.
    """
    code, head = _git(["rev-parse", "HEAD"], cwd)
    if code != 0 or len(head) != COMMIT_RE_LEN:
        return TreeIdentity(None, "unknown", f"cannot resolve HEAD: {head[:200]}")

    code, porcelain = _git(["status", "--porcelain", "--untracked-files=no"], cwd)
    if code != 0:
        return TreeIdentity(None, "unknown", f"cannot read status: {porcelain[:200]}")

    if porcelain:
        changed = len([line for line in porcelain.splitlines() if line.strip()])
        return TreeIdentity(
            None, "dirty",
            f"{changed} tracked file(s) differ from {head[:12]}; no commit describes "
            "what would run, so this receipt cannot carry a tested_commit_sha",
        )
    return TreeIdentity(head, "clean", "")


def bind_execution(before: TreeIdentity, after: TreeIdentity) -> TreeIdentity:
    """Reconcile the tree identity captured either side of a command.

    A command that ran while the tree moved has no single tree to name, even if
    both endpoints were individually clean. This is the case the ruling calls out
    explicitly and the one a single before-reading would miss.
    """
    if not before.is_bindable or not after.is_bindable:
        unbindable = before if not before.is_bindable else after
        return TreeIdentity(None, unbindable.state, unbindable.detail)
    if before.commit_sha != after.commit_sha:
        return TreeIdentity(
            None, "moved",
            f"the tree moved during execution ({before.commit_sha[:12]} -> "
            f"{after.commit_sha[:12]}); no single commit describes what ran",
        )
    return before


def provenance_fields(identity: TreeIdentity) -> dict:
    """The fields every receipt and natural-verdict event carries.

    `tested_commit_sha` is present and null rather than absent when unbindable:
    an absent key reads as an older emitter that never knew about provenance,
    while an explicit null is this emitter saying it looked and could not bind.
    """
    return {
        "tested_commit_sha": identity.commit_sha,
        "tested_tree_state": identity.state,
        "tested_tree_detail": identity.detail,
    }


def mutation_evidence_fields(
    baseline: TreeIdentity,
    mutant_diff: str,
    red_verdict: str,
    green_verdict: str,
    green_receipt_sha: Optional[str],
) -> dict:
    """The shape mutation evidence must carry (boundary-3 ruling).

    A mutation proof is only worth its name if the red and the green describe the
    SAME subject: the mutant must have been applied to, and reverted from, the
    tree the green receipt cites. `mutant_diff_sha256` identifies what was
    planted, so a proof cannot later be re-described as having planted something
    else.
    """
    return {
        "baseline_tested_commit_sha": baseline.commit_sha,
        "baseline_tree_state": baseline.state,
        "mutant_diff_sha256": hashlib.sha256(mutant_diff.encode("utf-8")).hexdigest(),
        "red_verdict": red_verdict,
        "green_after_verdict": green_verdict,
        "green_receipt_tested_commit_sha": green_receipt_sha,
        "binds_one_tree": bool(
            baseline.commit_sha
            and green_receipt_sha
            and baseline.commit_sha == green_receipt_sha
        ),
    }
