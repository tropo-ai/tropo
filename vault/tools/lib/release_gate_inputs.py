"""What the release gates need to know, read from the vault.

v1.92 Stream 3 (dev-spec 61f3153a), AC1.

THE PROBLEM THIS EXISTS FOR. v1.91 produced roughly twenty refusals in one
night. Every one was correct. Not one was knowable before the run started. The
retrospective's Action 1 asked for one preflight that reports every unmet
precondition at once, and Stream 1 answered half of it: seven governance gates
are registered at `lock-static`, each declaring the inputs it needs.

Nothing supplies them. `tropo-release-preflight.py:main` builds a context of
exactly two keys — `source_tree` and `shipped_tool_corpus` — so six of the seven
gates report SKIPPED-INPUTS-ABSENT and the command exits 0 having evaluated one
precondition. `tropo-lock-release-plan.py`, the tool that performs the gesture
`lock-static` governs, references the preflight zero times.

The gates declare what they need; this reads it. That is the whole module.

    from lib.release_gate_inputs import build_context
    context = build_context(studio_root, plan_uid="088e21aa")
    outcomes = registry.run_phase("lock-static", context)

"I CANNOT SEE" IS NEVER "YOU ARE WRONG". Every read here can fail — a plan uid
that does not resolve, an unparseable entry, a missing index. None of those is a
release verdict, and this module never converts one into a refusal: it raises
`GateInputError`, which the preflight maps to its OPERATIONAL exit code (3),
"deliberately not 2". A gate that cannot reach an answer must not be allowed to
answer.

THE CORPUS ROOT IS THE STUDIO ROOT. `lock-verify-commands-runnable` resolves
each acceptance criterion's verify command against `shipped_tool_corpus`. The
tokens in those commands are studio-relative (`vault/tools/tests/x.py`), and the
CLI set that key to `<studio>/vault/tools`, so the gate looked for
`<studio>/vault/tools/vault/tools/tests/x.py` and refused on files that exist.
Measured both ways against the real v1.92 members: studio root PASS, CLI value
REFUSED naming a real file as missing. It was untriggered only because the other
inputs never arrived — so supplying them without fixing this would have turned a
dormant defect into a false refusal on the first real run, which is worse than
the gap it closes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import fast_yaml

__all__ = [
    "GateInputError",
    "build_context",
    "plan_frontmatter",
    "fan_in_members",
    "member_states",
    "governed_index",
]


class GateInputError(RuntimeError):
    """An input could not be read. NEVER a release verdict.

    Mapped by callers to the operational exit class. The distinction is the one
    `tropo-release-preflight.py` already codifies and `lib/release_gates.py`
    carries as `ReleaseGateError — registry misuse, never a release verdict`;
    this reuses that vocabulary rather than minting a second one.
    """


def _entry_path(studio_root: Path, uid: str) -> Path:
    return Path(studio_root) / "vault" / "files" / f"{uid}.md"


def _frontmatter(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise GateInputError(f"no governed entry at {path}")
    text = path.read_text(errors="replace")
    if not text.startswith("---"):
        raise GateInputError(f"{path.name} carries no frontmatter")
    end = text.find("\n---", 3)
    if end == -1:
        raise GateInputError(f"{path.name} has an unterminated frontmatter block")
    try:
        parsed = fast_yaml.safe_load(text[3:end])
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        raise GateInputError(f"{path.name} frontmatter does not parse: {exc}") from exc
    if not isinstance(parsed, dict):
        raise GateInputError(f"{path.name} frontmatter is not a mapping")
    return parsed


def plan_frontmatter(studio_root: Path, plan_uid: str) -> Dict[str, Any]:
    """The release plan as data."""
    if not plan_uid or len(plan_uid) != 8:
        raise GateInputError(
            f"release plan uid {plan_uid!r} is not an 8-hex governed uid"
        )
    plan = _frontmatter(_entry_path(studio_root, plan_uid))
    if plan.get("type") != "release-plan":
        raise GateInputError(
            f"{plan_uid} is type {plan.get('type')!r}, not a release-plan"
        )
    return plan


def fan_in_members(plan: Dict[str, Any]) -> List[str]:
    """The dev-specs the plan fans in, in declared order.

    Quote-stripped: the field is authored as a YAML list whose entries are
    sometimes quoted uids, and an unstripped `"'1a478c48'"` resolves to no
    entry — which would read from the outside exactly like a missing member.
    """
    raw = plan.get("dev_spec_uids") or []
    if not isinstance(raw, list):
        raise GateInputError("dev_spec_uids is not a list")
    return [str(uid).strip().strip("'\"") for uid in raw if str(uid).strip()]


def member_states(studio_root: Path, members: List[str]) -> Dict[str, str]:
    """uid -> status, read from each member's OWN entry.

    Not from the index. The index is a derived surface and this Studio has
    measured it disagreeing with the files it describes; a lock decision must
    rest on the entry, not on a projection of it.
    """
    states: Dict[str, str] = {}
    for uid in members:
        try:
            states[uid] = str(_frontmatter(_entry_path(studio_root, uid)).get("status") or "")
        except GateInputError:
            # An unreadable member is not a member that is "not done" — it is a
            # read this producer could not complete, and saying otherwise would
            # convert an operational failure into a governance verdict.
            raise
    return states


def governed_index(studio_root: Path, members: List[str]) -> Dict[str, Dict[str, Any]]:
    """The index rows the gates read, with each member's acceptance criteria
    folded in from its own entry.

    `lock-criteria-readable` and `lock-verify-commands-runnable` both read
    `acceptance_criteria` off the index row.

    THE FOLD IS DEFENSIVE, NOT LOAD-BEARING TODAY, and the distinction was
    measured rather than assumed. This docstring first claimed the index does
    not carry `acceptance_criteria` at all — checked, and it does, for all four
    v1.92 members. So the fold changes nothing for a fresh index and everything
    for a stale one: the index is rebuilt on a cadence, a criterion added or
    reworded between rebuilds is invisible to it, and a gate reading a lagging
    row would report a spec as carrying no criteria — a REFUSAL manufactured by
    the producer's own staleness.

    The entry wins because the entry is the world and the index is a projection
    of it. That is the same reason `member_states` reads entries directly.
    """
    index: Dict[str, Dict[str, Any]] = {}
    index_path = Path(studio_root) / "vault" / "00-index.jsonl"
    if index_path.is_file():
        for line in index_path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            uid = row.get("uid")
            if uid:
                index[uid] = row

    for uid in members:
        row = dict(index.get(uid) or {})
        entry = _frontmatter(_entry_path(studio_root, uid))
        if entry.get("acceptance_criteria"):
            row["acceptance_criteria"] = entry["acceptance_criteria"]
        row.setdefault("type", entry.get("type"))
        row.setdefault("status", entry.get("status"))
        index[uid] = row
    return index


def build_context(
    studio_root: Path,
    plan_uid: Optional[str] = None,
    version_string: str = "",
) -> Dict[str, Any]:
    """Every input the lock-static gates declare, read from the vault.

    `plan_uid` omitted returns the two path inputs alone — the pre-existing
    behaviour, kept so a caller with no plan in hand (the `ship-python-floor`
    gate needs none) is unchanged rather than newly refused.
    """
    root = Path(studio_root).resolve()
    context: Dict[str, Any] = {
        "source_tree": str(root),
        # THE STUDIO ROOT, not vault/tools. See the module docstring: the verify
        # commands are studio-relative, and rooting them at vault/tools made the
        # gate refuse on files that exist.
        "shipped_tool_corpus": str(root),
    }
    if not plan_uid:
        return context

    plan = plan_frontmatter(root, plan_uid)
    members = fan_in_members(plan)
    context.update({
        "release_plan": plan,
        "fan_in_manifest": members,
        "member_states": member_states(root, members),
        "governed_index": governed_index(root, members),
        "version_string": version_string or str(plan.get("release_version") or ""),
    })
    return context
