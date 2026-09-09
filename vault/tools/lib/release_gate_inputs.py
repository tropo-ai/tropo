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

#: The uid as minted: 12-hex composite since 3d430852 Stage B, 8-hex on legacy
#: records. ONE authority studio-wide — lib/governed_path (test_uid_shape_has_one_home
#: refuses a local re-derivation, and rightly caught the first cut of this cure).
from .governed_path import is_governed_uid_shape as _is_governed_uid_shape

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
    """Slug-aware (2026-09-03, metis-g118): <slug>-<uid>.md is canonical since 08-31. The bare path is tried first (unchanged behaviour for every bare-named record); a single hyphen-anchored `*-<uid>.md` match is accepted otherwise. Found when the v1.94 plan lock's governance preconditions could not read a slug-named member spec and fell to warn-safe -- a gate that cannot see its subject."""
    base = Path(studio_root) / "vault" / "files"
    bare = base / f"{uid}.md"
    if bare.is_file():
        return bare
    hits = [p for p in base.glob(f"*-{uid}.md") if p.name.endswith(f"-{uid}.md")]
    return hits[0] if len(hits) == 1 else bare


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
    # Accepts-both (S5, 2026-09-05, argus-a171): the v1.95 plan f015ba71c711 is a
    # 12-hex composite (3d430852 Stage B) and this refused it as "not an 8-hex
    # governed uid" on the first real lock-static run — the hard-coded length
    # class Mike ruled swept, alive on the release path's critical instrument.
    if not plan_uid or not _is_governed_uid_shape(str(plan_uid)):
        raise GateInputError(
            f"release plan uid {plan_uid!r} is not a governed uid (8-hex legacy or 12-hex composite)"
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


def _tree_commit(root: Path) -> str:
    """HEAD of the tree at `root`, or '' outside git. Kept here rather than in
    build_guards so this module stays free of that import."""
    import subprocess
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001
        return ""
    return (result.stdout or "").strip() if result.returncode == 0 else ""


def _releases_root(root: Path) -> str:
    """Where built releases live, from the roots seam (S1 f0159f5c5663 owns the
    derivation; this only reads it). '' when the seam cannot be loaded."""
    try:
        from . import tropo_roots
        return str(tropo_roots.RELEASES_DIR)
    except Exception:  # noqa: BLE001
        return ""


def build_context(
    studio_root: Path,
    plan_uid: Optional[str] = None,
    version_string: str = "",
    activation_uid: Optional[str] = None,
    force: bool = False,
    extracted_tree: Optional[Path] = None,
) -> Dict[str, Any]:
    """Every input the lock-static AND candidate gates declare, read from the vault.

    `plan_uid` omitted returns the two path inputs alone — the pre-existing
    behaviour, kept so a caller with no plan in hand (the `ship-python-floor`
    gate needs none) is unchanged rather than newly refused.

    `extracted_tree` is the assembled box a candidate gate judges. Omitted, the
    twelve candidate gates report skipped-inputs-absent exactly as before —
    which was their ONLY behaviour from any caller but the build's own
    in-process path, because nothing outside it could supply this key. Same
    defect this function's own header comment in the preflight already records
    for lock-static ("The gates declared what they needed and nothing read
    it"), cured there and left standing here.
    *(metis-g124, 2026-09-07, after measuring all twelve skip from the CLI.)*
    """
    root = Path(studio_root).resolve()
    context: Dict[str, Any] = {
        "source_tree": str(root),
        # v1.95 Spine B (f015997f8d8e AC2): the HEAD this context was read at,
        # so every evidence row can name the tree it judged. Not a gate input
        # (absent from INPUT_FIRST_AVAILABLE by design — no gate may require
        # it); a context fact for write_evidence.
        "tree_commit": _tree_commit(root),
        # v1.95 Spine B: the two build guards that read the world OUTSIDE the tree.
        # releases_root and force are context facts, not gate inputs (absent from
        # INPUT_FIRST_AVAILABLE by design); pipeline_run IS an input — the
        # activation whose run minted the key — and is None when no activation
        # is in hand, so build-activation-key reports skipped rather than
        # guessing.
        "releases_root": _releases_root(root),
        "force": bool(force),
        "pipeline_run": activation_uid or None,
        # Present with or without a plan: build-overwrite-guard and
        # build-activation-key key on it, and both must speak for a standalone
        # build that has no plan in hand. '' reads as absent to run_phase's
        # None check only if we let it — so None when empty, on purpose.
        "version_string": str(version_string) if version_string else None,
        # THE STUDIO ROOT, not vault/tools. See the module docstring: the verify
        # commands are studio-relative, and rooting them at vault/tools made the
        # gate refuse on files that exist.
        "shipped_tool_corpus": str(root),
    }
    # Present only when a caller actually has a box in hand. Absent, run_phase's
    # None check reports skipped-inputs-absent per gate, which is the honest
    # answer and the pre-existing one — never a silent pass.
    # BLANK IS ABSENT, and the `.strip()` is the whole fix (argus-a173 peer
    # review, 2026-09-07, FAIL). Written first as `is not None`, which let
    # `--extracted-tree ""` -- ordinary shell hygiene with an unset variable --
    # become `Path("").resolve()`, i.e. the OPERATOR'S WORKING DIRECTORY. He
    # reproduced it against a decoy holding two empty folders and a README:
    # THREE box gates returned PASS. They are the ones phrased as absence
    # checks, so an empty directory passes every "nothing bad is here" test --
    # which means the false-PASS count RISES as the product gets better, and
    # would rise again the moment Talos closes the builder gap and today's
    # genuine refusals turn green. A release gate printing PASS over a tree
    # nothing examined is worse than the skip it replaced.
    #
    # Same shape this function already uses for `version_string` at :264.
    if extracted_tree is not None and str(extracted_tree).strip():
        context["extracted_tree"] = str(Path(extracted_tree).resolve())
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
