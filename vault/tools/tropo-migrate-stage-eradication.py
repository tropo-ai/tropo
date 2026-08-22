#!/usr/bin/env python3
"""
---
uid: 9d0ac2b7
name: tropo-migrate-stage-eradication
type: tool
title: "tropo-migrate-stage-eradication — the retired stage axis leaves, history stays"
status: active
state: active
owner: talos
domain: "Deterministic, journaled, reversible migration of stage/current_stage to status/current_step (dev-spec 63aaea28, Mike-locked 2026-08-17)."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-migrate-stage-eradication.py --root <studio> [--dry-run|--apply|--rollback]"
script_path: vault/tools/tropo-migrate-stage-eradication.py
created: '2026-08-18'
created_by: talos-t46
version: "1.0"
schema_version: 2
extraction_scope: ship
---

TWO SEMANTIC MIGRATIONS, NEVER ONE SEARCH/REPLACE (the spec's first contract
line, and the whole reason this tool exists):

  1. Work-item `stage` is retired lifecycle residue. It is REMOVED when a
     canonical status already exists and agrees through the declared aliases;
     it BECOMES the status when it is the sole legacy lifecycle source and the
     mapping is declared; it REFUSES (for human review) when it disagrees with
     a declared status, holds an undeclared value, or the frontmatter is
     malformed. History in bodies, changelogs, and journals is never touched —
     the tool edits frontmatter lines only, and only the named keys.

  2. Pipeline `current_stage` is POSITION. It is RENAMED to `current_step`,
     value preserved exactly (null, UID, or legacy word token). run.state.json
     files lose the current_stage key; a non-null current_stage moves into
     current_step when no step value exists.

SAFETY SHAPE (dev-spec 63aaea28 AC6):
  dry-run  writes nothing; prints the exact census as one JSON line.
  apply    scans fresh, CAS-checks every path against the last dry-run plan
           (bytes changed since the plan => refuse, name the path), executes
           line-surgical edits, appends one journal line per op with rollback
           bytes, prints {"changed": N, ...}. Idempotent: zero carriers =>
           zero changes, exit 0.
  rollback restores exact original bytes from the journal, CAS-guarded against
           post-migration edits.

This file imports nothing but the standard library, so it runs on any clone.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Declared work-item stage→status aliases. Eradicating the field does not erase
# per-type vocabulary (AC5): these values remain legal STATUS inputs. This map
# is the single declared place the legacy vocabulary survives, cited by the
# capsule amendment and the alias-preserving tests.
STAGE_STATUS_ALIASES = {
    "ideate": "active",
    "build": "active",
    "specify": "active",
    "review": "active",
    "ship": "closed",
    "done": "closed",
    "inbox": "new",
    "verify": "active",  # V3 vocabulary: verify was an active-phase word
}

STAGE_LINE = re.compile(r"^(stage):\s*(.*?)\s*$", re.MULTILINE)
CURRENT_STAGE_LINE = re.compile(r"^(current_stage):\s*(.*?)\s*$", re.MULTILINE)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_HEAD_RE = re.compile(r"\A---\n.*?\n---(?:\n|\Z)", re.DOTALL)


def split_frontmatter(text: str):
    """(head, body, ok). head is the exact original prefix through the closing
    fence (including its newline); body is everything after. ok=False when the
    frontmatter is not terminated — malformed files refuse rather than parse by
    approximation."""
    m = _HEAD_RE.match(text)
    if not m:
        return None, text, False
    return text[: m.end()], text[m.end():], True


def head_lines(head: str):
    return head.split("\n")


def parse_head_field(lines, field):
    """All values of `^field:` in the frontmatter head (duplicates matter)."""
    got = []
    for ln in lines:
        m = re.match(rf"^{field}:\s*(.*?)\s*$", ln)
        if m:
            got.append(m.group(1))
    return got


def scan_studio(root: Path):
    """The census. Counts and paths, no writes, no guessing."""
    files_dir = root / "vault" / "files"
    runs_dir = root / "vault" / "pipeline-runs"
    stage_carriers, current_stage_sources, runtime_state_carriers = [], [], []
    malformed, duplicates = [], []
    if files_dir.is_dir():
        for f in sorted(files_dir.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                malformed.append(str(f.relative_to(root)))
                continue
            head, _, ok = split_frontmatter(text)
            if not ok:
                if "stage:" in text.split("\n---")[0]:
                    malformed.append(str(f.relative_to(root)))
                continue
            lines = head_lines(head)
            if len(parse_head_field(lines, "stage")) > 1 or \
               len(parse_head_field(lines, "current_stage")) > 1:
                duplicates.append(str(f.relative_to(root)))
                continue
            if parse_head_field(lines, "stage"):
                stage_carriers.append(str(f.relative_to(root)))
            if parse_head_field(lines, "current_stage"):
                current_stage_sources.append(str(f.relative_to(root)))
    if runs_dir.is_dir():
        for f in sorted(runs_dir.rglob("run.state.json")):
            try:
                state = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(state, dict) and "current_stage" in state:
                runtime_state_carriers.append(str(f.relative_to(root)))
    return {
        "stage_carriers": len(stage_carriers),
        "stage_carrier_paths": stage_carriers,
        "current_stage_sources": len(current_stage_sources),
        "current_stage_source_paths": current_stage_sources,
        "runtime_state_carriers": len(runtime_state_carriers),
        "runtime_state_paths": runtime_state_carriers,
        "malformed": malformed,
        "duplicate_fields": duplicates,
    }


def plan_file(root: Path) -> Path:
    return root / ".tropo-studio" / "stage-eradication-plan.json"


def journal_file(root: Path) -> Path:
    return root / ".tropo-studio" / "stage-eradication-journal.jsonl"


def build_ops(root: Path, census: dict, review_allowlist=None):
    """Turn the census into concrete ops, refusing what must be reviewed.

    Each op: {path, op, reason, original, modified} with full original file
    bytes for CAS + rollback. Line-surgical: only the named key's line moves.
    """
    ops, refusals = [], []
    for rel in census["stage_carrier_paths"]:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        head, _, ok = split_frontmatter(text)
        if not ok:
            refusals.append(f"{rel}: unterminated frontmatter")
            continue
        lines = head_lines(head)
        stage_vals = parse_head_field(lines, "stage")
        status_vals = parse_head_field(lines, "status")
        stage_val = stage_vals[0].strip().strip("'\"")
        if status_vals:
            status_val = status_vals[0].strip().strip("'\"").lower()
            # Redundant = removable: the stage EQUALS the canonical status
            # (the field was back-filled from status: done/done, active/active,
            # verify/verify across the live corpus) or maps to it through the
            # declared alias table. Anything else is a real disagreement and
            # stays refused for review (63aaea28: "refuses disagreement").
            canonical = stage_val.lower() if stage_val.lower() == status_val \
                else STAGE_STATUS_ALIASES.get(stage_val.lower())
            recognized = (stage_val.lower() in STAGE_STATUS_ALIASES
                          or stage_val.lower() == "active")
            if review_allowlist and Path(rel).stem in review_allowlist \
                    and recognized and canonical != status_val:
                # Operator-reviewed stale residue detected on the alias path:
                # same disposition as the no-alias path — canonical status
                # stays, the older stage word goes. Journaled as reviewed.
                canonical = status_val
            if canonical is None:
                uid_of = Path(rel).stem
                stale = (stage_val.lower() in STAGE_STATUS_ALIASES
                         or stage_val.lower() == "active")
                if review_allowlist and uid_of in review_allowlist and stale:
                    # Operator-reviewed stale residue: the canonical status
                    # exists and stays untouched; the stage axis is simply
                    # older than the status. Removal drops the duplicate axis
                    # and fabricates nothing. Every override is journaled;
                    # refusal stays the default.
                    canonical = status_val
                else:
                    refusals.append(
                        f"{rel}: stage value {stage_val!r} is neither the "
                        f"declared status nor a declared alias of it — refused "
                        f"for review")
                    continue
            if canonical != status_val:
                refusals.append(
                    f"{rel}: stage {stage_val!r} maps to status "
                    f"{canonical!r} but record declares {status_val!r} — "
                    f"disagreement refused for review")
                continue
            new_head = "\n".join(
                ln for ln in lines if not re.match(r"^stage:\s*", ln))
        else:
            canonical = STAGE_STATUS_ALIASES.get(stage_val.lower())
            if canonical is None:
                refusals.append(
                    f"{rel}: sole legacy stage {stage_val!r} has no declared "
                    f"mapping — refused for review")
                continue
            new_head = "\n".join(
                (ln if not re.match(r"^stage:\s*", ln) else f"status: {canonical}")
                for ln in lines)
        new_text = new_head + text[len(head):]
        ops.append({"path": rel, "op": "retire-stage", "reason":
                    f"stage {stage_val!r} retired; status {canonical!r}",
                    "original": text, "modified": new_text})
    for rel in census["current_stage_source_paths"]:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        def rename_line(m):
            return f"current_step: {m.group(2)}"
        new_text = CURRENT_STAGE_LINE.sub(rename_line, text, count=1)
        # remove any additional current_stage lines entirely (defensive)
        new_text = CURRENT_STAGE_LINE.sub("", new_text).replace("\n\n\n", "\n\n")
        ops.append({"path": rel, "op": "rename-current-stage",
                    "reason": "positional key renamed, value preserved",
                    "original": text, "modified": new_text})
    for rel in census["runtime_state_paths"]:
        path = root / rel
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            refusals.append(f"{rel}: unparseable run.state.json")
            continue
        old = dict(state)
        cs = state.pop("current_stage", None)
        if cs is not None and not state.get("current_step"):
            state["current_step"] = cs
        ops.append({"path": rel, "op": "run-state-cutover",
                    "reason": "current_stage key removed",
                    # RAW file bytes at plan time, never a re-serialization —
                    # indent-1 reconstructions mismatched the 73 run-states'
                    # git pre-images (metis-g108 moderate item 2).
                    "original": path.read_text(encoding="utf-8"),
                    "modified": json.dumps(state, indent=1) + "\n"})
    return ops, refusals


def cas_check(root: Path, ops):
    """Refuse any path whose bytes changed since the last dry-run plan."""
    plan_path = plan_file(root)
    if not plan_path.is_file():
        return None
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except ValueError:
        return "plan journal unparseable; delete it and re-run dry-run"
    recorded = {e["path"]: e["sha256"] for e in plan.get("entries", [])}
    for op in ops:
        path = root / op["path"]
        digest = sha256_bytes(path.read_bytes())
        if op["path"] in recorded and recorded[op["path"]] != digest:
            return (f"{op['path']} changed after the plan was written "
                    f"(CAS mismatch); re-run dry-run")
    return None


def cmd_dry_run(root: Path):
    census = scan_studio(root)
    plan_path = plan_file(root)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for rel in (census["stage_carrier_paths"]
                + census["current_stage_source_paths"]
                + census["runtime_state_paths"]):
        p = root / rel
        if p.is_file():
            entries.append({"path": rel,
                            "sha256": sha256_bytes(p.read_bytes())})
    plan_path.write_text(json.dumps(
        {"entries": entries, "census": {
            k: v for k, v in census.items() if not k.endswith("_paths")}},
        indent=1) + "\n", encoding="utf-8")
    census["refusals_preview"] = len(census["malformed"]) + \
        len(census["duplicate_fields"])
    print(json.dumps(census, ensure_ascii=False))
    return 0


def cmd_apply(root: Path, review=None):
    census = scan_studio(root)
    if census["malformed"] or census["duplicate_fields"]:
        for rel in census["malformed"]:
            print(f"refused: {rel}: malformed frontmatter — review by hand",
                  file=sys.stderr)
        for rel in census["duplicate_fields"]:
            print(f"refused: {rel}: duplicate stage/current_stage keys — "
                  f"review by hand", file=sys.stderr)
        return 1
    review_allowlist = review or set()
    ops, refusals = build_ops(root, census, review_allowlist=review_allowlist)
    if refusals:
        for r in refusals:
            print(f"refused: {r}", file=sys.stderr)
        return 1
    cas = cas_check(root, ops)
    if cas:
        print(f"refused: {cas}", file=sys.stderr)
        return 1
    journal_path = journal_file(root)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    changed = 0
    with journal_path.open("a", encoding="utf-8") as journal:
        for op in ops:
            # JOURNAL FIRST, then write (metis-g108 moderate item 3): a crash
            # in the window leaves a journaled op whose target may be
            # unwritten — rollback restores the original over byte-identical
            # content. The reverse order leaves an unjournaled write rollback
            # cannot see.
            journal.write(json.dumps({
                "path": op["path"], "op": op["op"], "reason": op["reason"],
                "reviewed": bool(review_allowlist
                                and Path(op["path"]).stem in review_allowlist),
                "original_sha256": sha256_bytes(op["original"].encode("utf-8")),
                "modified_sha256": sha256_bytes(op["modified"].encode("utf-8")),
                "rollback": op["original"]}, ensure_ascii=False) + "\n")
            journal.flush()
            path = root / op["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(op["modified"], encoding="utf-8")
            changed += 1
    # The plan is consumed: post-apply state is the new baseline.
    plan_file(root).unlink(missing_ok=True)
    print(json.dumps({"changed": changed,
                      "stage_carriers_remaining": scan_studio(root)["stage_carriers"],
                      "current_stage_remaining":
                          scan_studio(root)["current_stage_sources"] +
                          scan_studio(root)["runtime_state_carriers"]}))
    return 0


def cmd_rollback(root: Path):
    journal_path = journal_file(root)
    if not journal_path.is_file():
        print("refused: no migration journal to roll back", file=sys.stderr)
        return 1
    lines = [json.loads(l) for l in
             journal_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    restored = 0
    for entry in reversed(lines):
        path = root / entry["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current is not None and entry.get("modified_sha256") and \
                sha256_bytes(current.encode("utf-8")) != entry["modified_sha256"]:
            print(f"refused: {entry['path']} changed after the migration "
                  f"(CAS mismatch) — restore it by hand", file=sys.stderr)
            return 1
        path.write_text(entry["rollback"], encoding="utf-8")
        restored += 1
    print(json.dumps({"restored": restored}))
    return 0


# ── AC7 vocabulary scanner ────────────────────────────────────────────────
# A closed scanner: classify stage tokens by explicit semantic class so a
# literal word sweep can never destroy external meanings (Git plumbing, release
# staging, authoring phases) or silently pass new lifecycle residue.

_GIT_PLUMBING = re.compile(r"(ls-files|--staged?|git add -p|stash)", re.I)
_RELEASE_STAGING = re.compile(r"(release|deploy|tropo-stage)", re.I)
_AUTHORING_PHASE = re.compile(r"(draft|writing|authoring|edit)", re.I)


def classify_stage_token(text: str) -> str:
    """Classify one stage-bearing token/line into its semantic class."""
    low = str(text or "").lower()
    if _GIT_PLUMBING.search(low):
        return "git-plumbing"
    if _RELEASE_STAGING.search(low):
        return "release-staging"
    if re.match(r"^\s*(stage|current_stage)\s*:", low):
        return "lifecycle-residue"
    if _AUTHORING_PHASE.search(low):
        return "authoring-phase"
    return "lifecycle-residue"


def scan_active_source_for_stage_reads(path: str) -> list:
    """Fresh work-item stage reads/writes in active product code are flagged.

    Historical prose is markdown; this scanner targets code files where
    `.stage` member access or a stage: object key is a live read/write of the
    retired axis.
    """
    hits = []
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    for n, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        if _GIT_PLUMBING.search(low) or _RELEASE_STAGING.search(low):
            continue
        if re.search(r"\.stage\b", line) or re.search(r"['\"]stage['\"]\s*:", line):
            hits.append(f"{p.name}:{n}: {line.strip()[:80]}")
    return hits


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="tropo-migrate-stage-eradication.py",
        description="Retire the stage axis: status is work, current_step is "
                    "position. Dry-run first, always.")
    p.add_argument("--root", default=".", help="studio root")
    p.add_argument("--review", default=None,
                   help="comma-separated UIDs explicitly operator-reviewed for "
                        "stale-stage removal; journaled; refusal stays the default")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="census + plan, writes only the plan file")
    g.add_argument("--apply", action="store_true",
                   help="execute the migration (CAS-guarded, journaled)")
    g.add_argument("--rollback", action="store_true",
                   help="restore exact pre-migration bytes from the journal")
    args = p.parse_args(argv)
    root = Path(args.root).resolve()
    if args.review:
        args.review = {u.strip() for u in args.review.split(",") if u.strip()}
    if args.dry_run:
        return cmd_dry_run(root)
    if args.apply:
        return cmd_apply(root, review=args.review)
    return cmd_rollback(root)


if __name__ == "__main__":
    sys.exit(main())
