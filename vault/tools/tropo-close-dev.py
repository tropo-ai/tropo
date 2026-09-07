#!/usr/bin/env python3
"""
---
uid: 41b7c9e2
title: tropo-close-dev — the one-command dev-spec close
name: tropo-close-dev
type: tool
status: active
owner: metis
domain: "Close a dev-spec in one ungated gesture: canonical dev_closed receipt for the release fan-in, status flip, close note, best-effort root archive. Mirrors tropo-lineage retire (5fffbbe9). Never refuses a close."
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/tropo-close-dev.py --dev-spec-uid <uid> --actor <who> [--evidence u1,u2] [--note "..."]
script_path: vault/tools/tropo-close-dev.py
destructive: false
governance_category: lifecycle
created: 2026-08-21
created_by: metis-g109
governed_by: 9a640a8a
---

Mike, 2026-08-21: "All the machinery we have still resulted in our agents failing to
complete work properly and the unwind is crazy long. I just don't see any value.
I think you fix it now."

The close records what happened; it does not gate it. Facts that used to be
refusals (dirty tree, wedged ceremony state, superseded prior runs) are recorded
on the receipt instead. The ONLY hard stop is a spec/activation/run that does not
resolve, because a receipt needs a journal to live in. Idempotent: a run already
holding a canonical receipt is reported, never double-stamped — the release
fan-in requires exactly one.
"""
from __future__ import annotations

import argparse, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

# 3d430852 (close-dev row): spec read/write resolve via the authority — a
# bare-path write-back on a slug-named record forks or misses it post-D7;
# the completion report's filename routes through mint_basename.
import importlib.util as _ilu
_gp_spec = _ilu.spec_from_file_location(
    "_close_dev_governed_path", Path(__file__).resolve().parent / "lib" / "governed_path.py")
gp = _ilu.module_from_spec(_gp_spec)
_gp_spec.loader.exec_module(gp)
# f01519144119: the close compares the spec's component digests against the
# run's lock-time snapshot; the digest function is the lock's own (lib/ignition).
_ig_spec = _ilu.spec_from_file_location(
    "_close_dev_ignition", Path(__file__).resolve().parent / "lib" / "ignition.py")
ig = _ilu.module_from_spec(_ig_spec)
sys.modules[_ig_spec.name] = ig  # dataclasses resolve their annotations through sys.modules
_ig_spec.loader.exec_module(ig)


COMPARED_COMPONENTS = ("acceptance_criteria_sha256", "committed_substrate_sha256")


def spec_drift_since_lock(run_folder: Path, spec_path: Path) -> tuple:
    """(amended_components, detail, warnings) — the reader the snapshot never had.

    f01519144119 (argus-a172, found verifying T62's Spine B run): the lock pins
    `acceptance_criteria_sha256` and `committed_substrate_sha256` into
    `<run>/declaration-snapshot.json` and NOTHING compared them at close, so a
    run could close against acceptance criteria rewritten after its lock and the
    instrument that says "the spec moved under you" stayed a declared primitive
    with no caller. WARN-SAFE (deb77758; Mike 2026-09-01: gates assert shape,
    not truth): a mismatch is reported and recorded on the receipt, never
    refused — an amendment can be Mike-ruled, and the one measured was.
    """
    warnings = []
    snap_path = run_folder / "declaration-snapshot.json"
    if not snap_path.is_file():
        warnings.append(f"no declaration-snapshot.json in {run_folder.name}; the lock-time "
                        "digests cannot be compared (run predates the snapshot, or it was removed)")
        return [], {}, warnings
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        warnings.append(f"declaration-snapshot.json unreadable ({exc}); digests not compared")
        return [], {}, warnings
    current = ig.spec_component_digests(spec_path.read_text(encoding="utf-8"))
    amended, detail = [], {}
    for key in COMPARED_COMPONENTS:
        pinned = str(snap.get(key) or "")
        now = str(current.get(key) or "")
        if not pinned:
            continue  # the lock never pinned this component; nothing to compare
        detail[key] = {"pinned_at_lock": pinned, "at_close": now}
        if pinned != now:
            amended.append(key)
    return amended, detail, warnings

STUDIO = Path(__file__).resolve().parents[2]
FILES = STUDIO / "vault" / "files"
RUNS = STUDIO / "vault" / "pipeline-runs"

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_fm(uid: str) -> dict | None:
    p = gp.resolve_governed_path(uid, STUDIO, home="vault/files") or (FILES / f"{uid}.md")
    if p is None or not p.is_file():
        p = FILES / f"{uid}.md"  # authority answered bare; the fallback stays until D7 emission
    if not p.is_file():
        return None
    import yaml
    m = FM_RE.match(p.read_text(encoding="utf-8"))
    return yaml.safe_load(m.group(1)) if m else None


def read_fm_path(p: Path) -> dict | None:
    """Frontmatter of a file we already hold, read from the path — never by
    re-resolving its stem as a uid. Slug-named governed files
    (`<slug>-<uid>.md`) are canonical since the 2026-08-31 filename ruling, and
    their stem is not a uid shape; `read_fm(f.stem)` raised UnsafeGovernedPath
    on the first one the vault-wide scans below met, so no dev-spec could close
    in a vault containing any. The name proposes; the frontmatter decides.
    (metis-g117, 2026-09-03 — the same class T60 cured in tropo-recycle.py.)"""
    if not p.is_file():
        return None
    import yaml
    m = FM_RE.match(p.read_text(encoding="utf-8"))
    return yaml.safe_load(m.group(1)) if m else None


def git(*args) -> str:
    r = subprocess.run(["git", *args], cwd=STUDIO, capture_output=True, text=True, timeout=30)
    return (r.stdout or "").strip()


def _author_completion_report(spec_uid: str, act_uid: str, run_uid: str, head: str,
                              tree_state: str, actor: str, evidence: list, note: str) -> str:
    """Author the completion-report the fan-in row hashes.

    gather_row demands completion_report_uid on the spec (A153's 1/9 ignition
    finding, 2026-08-21). This is the report the old complete-workflow gate used
    to author — authored without the gate, naming its basis.
    """
    r = subprocess.run([sys.executable, str(STUDIO / "vault/tools/tropo-mint-id.py"),
                        "--reason", f"completion report for {spec_uid} close",
                        "--minted-by", actor], capture_output=True, text=True, timeout=60)
    uid = (r.stdout or "").strip().splitlines()[-1].strip()
    # Ownership is the LINE, authorship is the GENERATION (Mike-ruled 2026-09-01 on
    # f01564310146: the bare line-slug cannot orphan; the generation-qualified form is
    # what made an entry unreachable when its owner retired). vela-v77 governance sweep
    # 008 caught five reports at owner:metis-g118 on 2026-09-03; fixed here at the source.
    owner = re.sub(r"-[a-z]\d+$", "", actor)
    rel_lines = "\n".join(f"  - rel: references\n    to: {u}" for u in [spec_uid, *evidence])
    ev_links = ", ".join(f"[{u}]({u}.md)" for u in evidence) if evidence else "named in the close note"
    body = f"""---
uid: '{uid}'
type: completion-report
title: "Completion report — {spec_uid} (activation {act_uid})"
description: "Machine-authored at single-source close (9a640a8a); the run-ended receipt the release fan-in hashes."
status: done
verdict: pass
state: active
owner: "{owner}"
author: "{actor}"
reports_on_dev_spec: {spec_uid}
relationships:
{rel_lines}
created: '{now()[:10]}'
created_by: "{actor}"
modified: '{now()[:10]}'
modified_by: "{actor}"
schema_version: 2
governed_by: 9a640a8a
---

# Completion report — {spec_uid}

Single-source close (9a640a8a, ungated) by {actor} at `{head[:12]}` (tree {tree_state}).
The canonical dev_closed receipt in run {run_uid}'s journal is the record; this report is
the completion attestation the fan-in row hashes. Acceptance evidence: {ev_links}.
{note}
"""
    (gp.resolve_governed_path(uid, STUDIO, home="vault/files") or (FILES / f"{uid}.md")).write_text(body, encoding="utf-8")
    return uid


def _archive_root_best_effort(root_uid: str | None, head: str) -> list[str]:
    """Rule 12 best-effort: flip the activation root to done/archived with final_commit.
    A failure is a WARN, never a block. Slug-aware. Shared by the normal close and the
    already-receipted (idempotent) branch — before 2026-09-03 only the normal path did
    this, so a close that wedged after its receipt left the root active forever."""
    warn: list[str] = []
    if not root_uid:
        warn.append("no activation_root_uid resolved; receipt stands regardless")
        return warn
    rp = gp.resolve_governed_path(root_uid, STUDIO, home="vault/files") or (FILES / f"{root_uid}.md")
    if rp.is_file():
        try:
            rt = rp.read_text(encoding="utf-8")
            rt = re.sub(r"^status: .*$", "status: done", rt, count=1, flags=re.MULTILINE)
            rt = re.sub(r"^state: .*$", "state: archived", rt, count=1, flags=re.MULTILINE)
            if "final_commit:" in rt:
                rt = re.sub(r"^final_commit: .*$", f"final_commit: {head}", rt, count=1, flags=re.MULTILINE)
            else:
                rt = rt.replace("state: archived", f"state: archived\nfinal_commit: {head}", 1)
            rp.write_text(rt, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            warn.append(f"root archive best-effort failed: {e}")
    else:
        warn.append(f"root {root_uid} did not resolve; not archived")
    return warn

def _emit_cycle_closed_best_effort(spec_uid: str, act_uid: str, run_uid: str, head: str,
                                   report_uid: str, actor: str) -> list[str]:
    """2fe61817 §S2.4 emit-on-completion: a terminal close carries a correlated
    tropo.cycle.closed event (correlationid = the spec uid), which Check 32 reads.
    Before 2026-09-03 this tool wrote the receipt and the report and emitted
    nothing, so an archived spec read as a silent close. Best-effort: a failed
    emit is a WARN, never a block -- the receipt is the record."""
    line = re.sub(r"-[a-z]\d+$", "", actor)
    data = {"dev_spec_uid": spec_uid, "activation_uid": act_uid, "pipeline_run_uid": run_uid,
            "completion_report_uid": report_uid, "tested_commit_sha": head, "closed_by": actor,
            "receipt_kind": "canonical-dev-close"}
    try:
        r = subprocess.run([sys.executable, str(STUDIO / "vault/tools/tropo-emit-event.py"),
                            "--type", "tropo.cycle.closed", "--as", line, "--source", f"/agents/{line}",
                            "--lifecycle", "evergreen", "--subject", spec_uid, "--correlationid", spec_uid,
                            "--final", "--data", json.dumps(data)], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return [f"tropo.cycle.closed emit failed (rc {r.returncode}): {(r.stderr or r.stdout)[-160:].strip()}"]
    except Exception as e:  # noqa: BLE001
        return [f"tropo.cycle.closed emit failed: {e}"]
    return []

def _stamp_spec_completion(spec_path: Path, report_uid: str, evidence: list) -> None:
    """completion_report_uid + acceptance_evidence onto the spec frontmatter, idempotently."""
    txt = spec_path.read_text(encoding="utf-8")
    if "completion_report_uid:" not in txt:
        txt = re.sub(r"^(status: .*)$", r"\1" + f"\ncompletion_report_uid: {report_uid}",
                     txt, count=1, flags=re.MULTILINE)
    if evidence and "acceptance_evidence:" not in txt:
        ev_yaml = "acceptance_evidence:\n" + "".join(f"- {u}\n" for u in evidence)
        txt = re.sub(r"^(completion_report_uid: .*)$", r"\1\n" + ev_yaml.rstrip(),
                     txt, count=1, flags=re.MULTILINE)
    spec_path.write_text(txt, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-spec-uid", required=True)
    ap.add_argument("--actor", required=True)
    ap.add_argument("--evidence", default="", help="comma-separated evidence uids")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    spec_uid = a.dev_spec_uid
    # Slug-aware (2026-09-03, metis-g118): <slug>-<uid>.md is canonical since 08-31; the bare
    # path crashed this tool AFTER it had welded the receipt (B-7, f01564310146), leaving a
    # receipted-but-locked spec. read_fm() already resolves by uid; the path must too.
    spec_path = gp.resolve_governed_path(spec_uid, STUDIO, home="vault/files") or (FILES / f"{spec_uid}.md")
    spec = read_fm(spec_uid)
    if spec is None:
        print(f"[STOP] dev-spec {spec_uid} does not resolve — a close needs a spec to close", file=sys.stderr)
        return 2

    act_uid = spec.get("dev_spec_activation_uid")
    if not act_uid:
        # fall back: scan activations naming this spec
        for f in FILES.glob("*.md"):
            fm = read_fm_path(f)
            if fm and fm.get("type") == "activation" and fm.get("dev_spec_uid") == spec_uid:
                act_uid = str(fm.get("uid") or f.stem)
                break
    if not act_uid:
        print(f"[STOP] no activation resolves for dev-spec {spec_uid}", file=sys.stderr)
        return 2

    # LIVE run first; superseded runs yield (the pilot's resolver lesson).
    run_fm, run_fallback = None, None
    for f in FILES.glob("*.md"):
        fm = read_fm_path(f)
        if fm and fm.get("type") == "pipeline-run" and fm.get("substrate_authored_by") == act_uid:
            if fm.get("activation_superseded"):
                run_fallback = run_fallback or fm
            else:
                run_fm = fm
                break
    run_fm = run_fm or run_fallback
    if run_fm is None:
        print(f"[STOP] no pipeline-run resolves for activation {act_uid}", file=sys.stderr)
        return 2
    run_uid = run_fm.get("uid")

    run_folder = None
    for d in RUNS.glob(f"*{run_uid}*"):
        if d.is_dir():
            run_folder = d
            break
    if run_folder is None:
        print(f"[STOP] no run folder resolves for run {run_uid}", file=sys.stderr)
        return 2

    journal = run_folder / "run.jsonl"
    root_uid = None
    existing = None
    if journal.is_file():
        for line in journal.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"dev_closed"' not in line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "dev_closed" and (ev.get("data") or {}).get("receipt_kind") == "canonical-dev-close":
                existing = ev
    if existing:
        sha = (existing.get("data") or {}).get("tested_commit_sha")
        print(f"already-receipted: canonical receipt exists in {run_folder.name} (tested {str(sha)[:12]}) — the fan-in requires exactly one; receipt untouched")
        # Complete the PROJECTION idempotently: a wedged ceremony often welded its
        # receipt and then died at the completion gates, leaving the spec still
        # status:locked. The receipt is the record; finish the projection.
        head = str(sha) if sha else git("rev-parse", "HEAD")
        txt = spec_path.read_text(encoding="utf-8")
        if not re.search(r"^status: done$", txt, flags=re.MULTILINE):
            txt = re.sub(r"^status: .*$", "status: done", txt, count=1, flags=re.MULTILINE)
            txt = re.sub(r"^modified: .*$", f"modified: '{now()[:10]}'", txt, count=1, flags=re.MULTILINE)
            txt = re.sub(r"^modified_by: .*$", f"modified_by: {a.actor}", txt, count=1, flags=re.MULTILINE)
            evidence = [u for u in a.evidence.split(",") if u.strip()]
            note_block = (
                f"\n\n## Close note ({now()[:10]}, {a.actor} — single-source close, 9a640a8a)\n\n"
                f"Receipt already welded at `{head[:12]}` by the prior ceremony; this close completes "
                f"the projection the ceremony's completion gates blocked. "
                + (f"Evidence: {', '.join('[' + u + '](' + u + '.md)' for u in evidence)}. " if evidence else "")
                + (a.note if a.note else "") + "\n"
            )
            spec_path.write_text(txt.rstrip() + note_block, encoding="utf-8")
            print(f"projection completed: {spec_uid} -> done (receipt was already welded)")
        # The fan-in also demands completion_report_uid + typed passing evidence
        # (A153's 1/9 ignition finding) — backfill idempotently.
        if "completion_report_uid:" not in spec_path.read_text(encoding="utf-8"):
            evidence = [u for u in a.evidence.split(",") if u.strip()]
            report_uid = _author_completion_report(
                spec_uid, act_uid, run_uid, str(sha) if sha else git("rev-parse", "HEAD"),
                "receipt-welded-prior", a.actor, evidence, a.note)
            _stamp_spec_completion(spec_path, report_uid, evidence)
            print(f"completion report backfilled: {report_uid}")
        root_uid = (read_fm(act_uid) or {}).get("activation_root_project")
        for w in _archive_root_best_effort(root_uid, head):
            print(f"[WARN] {w}")
        _rep = re.search(r"^completion_report_uid: *['\"]?([0-9a-f]{8,12})", spec_path.read_text(encoding="utf-8"), flags=re.MULTILINE)
        for w in _emit_cycle_closed_best_effort(spec_uid, str(act_uid), str(run_uid), head, _rep.group(1) if _rep else "", a.actor):
            print(f"[WARN] {w}")
        return 0

    head = git("rev-parse", "HEAD")
    dirty = git("status", "--porcelain", "--untracked-files=no")
    tree_state = "clean" if not dirty else f"dirty ({len(dirty.splitlines())} tracked file(s) modified)"

    evidence = [u for u in a.evidence.split(",") if u.strip()]

    # f01519144119 — compare the spec's component digests against the lock-time
    # snapshot and SAY what moved, on the receipt and on stderr. Warn-safe.
    amended, drift_detail, drift_warnings = spec_drift_since_lock(run_folder, spec_path)
    for w in drift_warnings:
        print(f"[WARN] {w}", file=sys.stderr)
    if amended:
        touching = git("log", "--format=%h %ad %s", "--date=short", "-n", "5", "--", str(spec_path))
        for key in amended:
            d = drift_detail[key]
            print(f"[WARN] spec amended after lock: {key} pinned {d['pinned_at_lock'][:12]} at lock, "
                  f"{d['at_close'][:12]} at close -- the run is closing against "
                  f"{'acceptance criteria' if key.startswith('acceptance') else 'a committed-substrate declaration'} "
                  f"that changed under it; recorded on the receipt, not refused (deb77758). "
                  f"Recent commits touching the spec: {touching.replace(chr(10), ' | ') or 'none in git'}",
                  file=sys.stderr)

    data = {
        "receipt_kind": "canonical-dev-close",
        "dev_spec_uid": spec_uid,
        "activation_uid": act_uid,
        "pipeline_run_uid": run_uid,
        "activation_root_uid": (read_fm(act_uid) or {}).get("activation_root_project")
                               or run_fm.get("activation_root_project"),
        "tested_sha": head,
        "tested_commit_sha": head,
        "tree_state_at_close": tree_state,
        "acceptance_evidence": evidence,
        "closed_by": a.actor,
        "close_mode": "single-source (9a640a8a; ungated)",
        "note": a.note,
    }
    if amended:
        data["spec_amended_after_lock"] = True
        data["spec_amended_components"] = list(amended)
        data["spec_digests"] = drift_detail
    ev = {"event": "dev_closed", "trace_id": act_uid, "actor": a.actor, "ts": now(), "data": data}
    with journal.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    # Flip the spec: status done + close note. A projection of the receipt, never the record.
    txt = spec_path.read_text(encoding="utf-8")
    txt = re.sub(r"^status: .*$", "status: done", txt, count=1, flags=re.MULTILINE)
    if not re.search(r"^closed_at:", txt, flags=re.MULTILINE):
        # dev-spec.capsule Check 8: status:done + state:active requires closed_at.
        # The first single-source close (49c93363, 2026-09-03) landed without it
        # and check-one WARNed; stamp it from the receipt's own timestamp.
        txt = re.sub(r"^status: done$", f"status: done\nclosed_at: '{ev['ts']}'", txt,
                     count=1, flags=re.MULTILINE)
    txt = re.sub(r"^modified: .*$", f"modified: '{now()[:10]}'", txt, count=1, flags=re.MULTILINE)
    txt = re.sub(r"^modified_by: .*$", f"modified_by: {a.actor}", txt, count=1, flags=re.MULTILINE)
    note_block = (
        f"\n\n## Close note ({now()[:10]}, {a.actor} — single-source close, 9a640a8a)\n\n"
        f"Closed ungated at `{head[:12]}` (tree {tree_state}). "
        + (f"Evidence: {', '.join('[' + u + '](' + u + '.md)' for u in evidence)}. " if evidence else "")
        + (a.note if a.note else "")
        + "\nReceipt: canonical dev_closed in the live run journal (the record; this note is the projection).\n"
    )
    spec_path.write_text(txt.rstrip() + note_block, encoding="utf-8")

    # Best-effort root archive + final_commit (Rule 12). A failure here is a WARN, never a block.
    warn = []
    root_uid = data["activation_root_uid"]
    warn += _archive_root_best_effort(root_uid, head)

    report_uid = _author_completion_report(spec_uid, act_uid, run_uid, head,
                                           tree_state, a.actor, evidence, a.note)
    _stamp_spec_completion(spec_path, report_uid, evidence)
    warn += _emit_cycle_closed_best_effort(spec_uid, str(act_uid), str(run_uid), head, report_uid, a.actor)

    for w in warn:
        print(f"[WARN] {w}", file=sys.stderr)
    print(f"closed: {spec_uid} (run {run_uid}, tested {head[:12]}, tree {tree_state}, report {report_uid})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
