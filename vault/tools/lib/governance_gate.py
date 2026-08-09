"""lib/governance_gate.py — the D3b governance-validator GATE client (D5 P6).

Dev-spec 396d88a4 (GitHub.com enforcement transport, Phase T) + cycle brief
304badf7 D3a/D3b. Test-spec 0f06a8b5 assertion P6.

WHAT THIS IS
  The client + defence-in-depth wiring for the governance-validator gate that
  keeps a BROKEN governed file off the canonical ref. On github.com the gate is
  a REQUIRED GitHub Action (unbypassable onto main) running the hardened
  validator `vault/tools/federation/tropo_validate_governed.py`; the local
  pre-commit hook is best-effort defence-in-depth. This module:
    - `validate_paths`   — run the validator over files; raise GovernanceBlocked
                           on any BROKEN file (the gate's decision, exit 1).
    - `install_hook`     — install the pre-commit hook into a repo.
    - `assert_hook_installed` — DETECT + REFUSE a missing/wrong hook (the P6
                           "absence is detected + refused, not silently skipped"
                           requirement).

  "UNBYPASSABLE ONTO MAIN, BEST-EFFORT LOCALLY" (304badf7 D3a): the LOCAL hook
  can be removed, so it is not the trust anchor — the REQUIRED Action on the
  protected repo is. Wiring that required Action + branch-protection on the
  disposable protected repo is the github.com-only proof, flagged as a
  credential/repo prerequisite; the validator LOGIC + hook mechanics are proven
  here against the real validator CLI.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable

# The hardened D3b validator (reconstructed + re-verified, 304badf7 §4).
VALIDATOR = Path(__file__).resolve().parents[1] / "federation" / "tropo_validate_governed.py"

# Governed content the gate covers (single-doc governed markdown under files/).
GOVERNED_GLOBS = ("files/*.md", "vault/files/*.md", "teams/*/files/*.md")

_HOOK_MARKER = "tropo-governance-gate"


class GovernanceError(Exception):
    """Base class for gate refusals."""


class GovernanceBlocked(GovernanceError):
    """The validator ruled at least one governed file BROKEN (gate exit 1)."""

    def __init__(self, results: list[tuple[str, str, list[str]]]):
        self.results = results
        broken = [r for r in results if r[1] != "VALID"]
        detail = "; ".join(f"{p}: {status} ({', '.join(probs)})" for p, status, probs in broken)
        super().__init__(f"governance gate BLOCKED {len(broken)} file(s): {detail}")


class GateNotInstalled(GovernanceError):
    """The pre-commit hook is missing or does not invoke the gate — refused, NOT
    silently skipped (P6)."""


def _validate_one(path: Path) -> tuple[str, list[str]]:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True, text=True,
    )
    # exit 0=VALID · 1=BROKEN · 2=NEEDS-RESOLUTION (tropo_validate_governed.py)
    status = {0: "VALID", 1: "BROKEN", 2: "NEEDS-RESOLUTION"}.get(proc.returncode, "BROKEN")
    problems = [ln.strip("- ").strip() for ln in proc.stdout.splitlines() if ln.strip().startswith("-")]
    return status, problems


def validate_paths(paths: Iterable[Path], *, raise_on_block: bool = True) -> list[tuple[str, str, list[str]]]:
    """Run the hardened validator over `paths`. Returns [(path, status,
    problems)]. With `raise_on_block` (the gate's posture), any non-VALID file
    raises GovernanceBlocked — the same decision the required Action makes."""
    results: list[tuple[str, str, list[str]]] = []
    for p in paths:
        p = Path(p)
        status, problems = _validate_one(p)
        results.append((str(p), status, problems))
    if raise_on_block and any(status != "VALID" for _, status, _ in results):
        raise GovernanceBlocked(results)
    return results


def hook_script() -> str:
    """The pre-commit hook body: validate every STAGED governed file, block the
    commit on any BROKEN file. Best-effort local defence-in-depth."""
    return f"""#!/usr/bin/env bash
# {_HOOK_MARKER}: D3b governance-validator gate (defence-in-depth; the REQUIRED
# GitHub Action is the unbypassable anchor onto main).
set -euo pipefail
VALIDATOR="{VALIDATOR}"
mapfile -t staged < <(git diff --cached --name-only --diff-filter=ACM | grep -E '(^|/)files/.*\\.md$' || true)
if [ "${{#staged[@]}}" -eq 0 ]; then exit 0; fi
if ! python3 "$VALIDATOR" "${{staged[@]}}"; then
  echo "governance gate: refusing commit — a governed file is BROKEN" >&2
  exit 1
fi
"""


def hook_path(repo: Path) -> Path:
    return Path(repo) / ".git" / "hooks" / "pre-commit"


def install_hook(repo: Path) -> Path:
    """Install the pre-commit hook (defence-in-depth). Returns the hook path."""
    hp = hook_path(repo)
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(hook_script(), encoding="utf-8")
    hp.chmod(0o755)
    return hp


def assert_hook_installed(repo: Path) -> None:
    """DETECT + REFUSE a missing/wrong gate hook (P6: not silently skipped). A
    studio whose defence-in-depth hook is absent must be refused, so a missing
    hook cannot let raw markers reach the shared graph unnoticed."""
    hp = hook_path(repo)
    if not hp.is_file():
        raise GateNotInstalled(
            f"pre-commit governance gate is NOT installed at {hp} — refused "
            f"(the local defence-in-depth hook must be present, not silently skipped)"
        )
    if _HOOK_MARKER not in hp.read_text(encoding="utf-8"):
        raise GateNotInstalled(
            f"pre-commit hook at {hp} does not invoke the governance gate "
            f"(missing marker {_HOOK_MARKER!r}) — refused"
        )


__all__ = [
    "VALIDATOR", "GOVERNED_GLOBS",
    "GovernanceError", "GovernanceBlocked", "GateNotInstalled",
    "validate_paths", "hook_script", "hook_path", "install_hook", "assert_hook_installed",
]
