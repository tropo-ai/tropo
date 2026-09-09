"""lib/run_journal.py -- give the boot run journal the vocabulary to say
"this step did not happen".

The v1.95 external test measured the exact hole this closes. A cold walker's
agent "sage" fired the Group 2 milestone `Context Loaded` while Step 2.0 (soul)
was never entered. Milestones in `run.jsonl` are per-GROUP, so the journal had
no way to express a skipped STEP: a green group over an unaccounted step and a
green group over a satisfied one are byte-identical. That is why the defect
shipped, and why nobody -- including the agent -- could see it afterwards.

Two functions, both small, both stdlib:

  `append_step_disposition()` writes one `step_disposition` row per declared
  step, with a status COMPUTED by a resolver from files on disk, not asserted
  by the agent.

  `audit()` is the half that matters: a reader that is NOT the booting agent
  answers "did Step 2.0 actually run?" from the journal alone. A `Context
  Loaded` milestone with no preceding `step_disposition` for `2.0` is reported
  as UNACCOUNTED. That is the sentence the journal could not previously say.

WARN-SAFE: every function here reports and returns. Nothing refuses, nothing
raises on a malformed or absent journal, and `audit` never exits nonzero on
findings -- findings are output, not a verdict on whether the founder may
proceed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

EVENT = "step_disposition"

# Which milestone is accountable for which declared step. Adding a row here is
# how a future step joins the accounting; nothing else changes.
STEP_ACCOUNTABILITY = {
    "Context Loaded": ["2.0"],
}


def find_latest_run_journal(vault_root: Path, slug: str) -> Optional[Path]:
    """Newest `playbook-runs/agent-activation-<slug>-*/run.jsonl`, by mtime.
    Returns None rather than raising when there is no run folder yet -- a first
    boot legitimately has none."""
    runs = Path(vault_root) / "playbook-runs"
    if not runs.is_dir():
        return None
    best: Optional[Path] = None
    best_mtime = -1.0
    try:
        candidates = sorted(runs.glob("agent-activation-{}-*".format(slug)))
    except OSError:
        return None
    for folder in candidates:
        journal = folder / "run.jsonl"
        if not journal.is_file():
            continue
        try:
            mtime = journal.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            best, best_mtime = journal, mtime
    return best


def append_step_disposition(
    journal: Path,
    step: str,
    status: str,
    detail: Dict[str, Any],
    timestamp: str,
) -> Optional[str]:
    """Append one row. Returns None on success, or a human-readable reason the
    write did not happen -- the caller prints that reason and CONTINUES. A boot
    is never blocked by a journal that could not be written."""
    row = {
        "event": EVENT,
        "step": step,
        "status": status,
        "timestamp": timestamp,
        "detail": detail,
    }
    try:
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        return "{}: {}".format(type(exc).__name__, exc)
    return None


def read_rows(journal: Path) -> List[Dict[str, Any]]:
    """Every parseable JSON object in the journal, in file order. Unparseable
    lines are skipped silently -- a half-written line must not blind the audit
    to the rows around it."""
    rows: List[Dict[str, Any]] = []
    try:
        text = journal.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


@dataclass
class AuditResult:
    journal: str
    findings: List[str] = field(default_factory=list)
    accounted: List[str] = field(default_factory=list)
    unaccounted: List[str] = field(default_factory=list)
    milestones: List[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.unaccounted


def audit(journal: Path) -> AuditResult:
    """Read a run journal as somebody who did not write it.

    A milestone that fired without a `step_disposition` for each step it is
    accountable for is UNACCOUNTED: the group reported complete over a step
    that left no evidence either way. This is the check that would have caught
    sage, and it consults no agent's account of its own compliance -- only rows
    on disk.
    """
    result = AuditResult(journal=str(journal))
    rows = read_rows(journal)
    if not rows:
        result.findings.append(
            "run journal is absent, empty or unparseable: {}".format(journal)
        )
        return result

    dispositions: Dict[str, str] = {}
    for row in rows:
        if row.get("event") == EVENT and isinstance(row.get("step"), str):
            dispositions[row["step"]] = str(row.get("status", "unknown"))
        elif row.get("event") == "milestone_fired":
            milestone = str(row.get("milestone", ""))
            result.milestones.append(milestone)
            for step in STEP_ACCOUNTABILITY.get(milestone, []):
                if step in dispositions:
                    result.accounted.append(
                        "Step {} — {} (milestone `{}`)".format(
                            step, dispositions[step], milestone
                        )
                    )
                else:
                    result.unaccounted.append(step)
                    result.findings.append(
                        "milestone `{}` fired with NO step_disposition row for Step {} — "
                        "the group reported complete over a step that left no evidence "
                        "either way.".format(milestone, step)
                    )
    return result
