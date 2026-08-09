#!/usr/bin/env python3
"""
tropo-sweep-stale-roots.py — close pipeline activation roots whose cycle is over.

THE PROBLEM (diagnosed by metis-g91, 2026-07-21): pipelines open an activation
root at cycle start (welded to the spec lock, so it always happens) but closing
is honor-system. Only the dev-pipeline has a close step, and nothing forces it to
run, so roots pile up at state:active long after the work shipped. 93 roots were
stuck open across all pipelines at diagnosis time (dev 17, test 30, doc 29, ...).

WHAT THIS DOES: the backstop sweep — the never-landed "Option B stale-sweep" from
note c3b8a7e1, re-scoped from the activation ENTRY to the activation-ROOT project.
It archives (state:active -> archived, via the sanctioned tropo-archive.py, which
stamps provenance + emits an event and is REVERSIBLE with --unarchive) every
activation-root project whose cycle is demonstrably over.

STALENESS RULE (conservative — never touches a plausibly-live cycle):
  A stuck-open root is archived if EITHER
    (a) it is SUPERSEDED: a strictly-newer activation root exists for the same
        pipeline (a later cycle has opened, so this one is finished), OR
    (b) it is STALE BY AGE: modified more than --max-age-days days ago (default 14).
  The single newest root per pipeline is KEPT ACTIVE when it is within the age
  window, on the assumption it may be an in-flight cycle. Parallel cycles are
  respected: only strictly-older roots are sweep targets.

Dry-run by default. Pass --execute to actually archive. Fully reversible.

Usage:
  python3 vault/tools/tropo-sweep-stale-roots.py                 # dry-run
  python3 vault/tools/tropo-sweep-stale-roots.py --execute       # archive
  python3 vault/tools/tropo-sweep-stale-roots.py --max-age-days 21 --execute
"""
import argparse
import datetime
import os
import sqlite3
import subprocess
import sys

VAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX = os.path.join(VAULT_ROOT, "vault", "00-index.sqlite")
ARCHIVE_TOOL = os.path.join(VAULT_ROOT, "vault", "tools", "tropo-archive.py")


def load_stuck_roots(db):
    """Each activation-root project still at state:active — ONE row per uid (member_of
    is many-to-many, so a root can have several parents; we dedup here)."""
    rows = db.execute(
        """
        SELECT DISTINCT c.uid, c.title,
               substr(COALESCE(c.modified, c.created, ''), 1, 10) AS modified
        FROM entries c
        WHERE c.type = 'project'
          AND c.title LIKE '%Activation Root%'
          AND COALESCE(c.state, json_extract(c.fm_json, '$.state')) = 'active'
        """
    ).fetchall()
    return [dict(r) for r in rows]


def pipeline_titles(db):
    return {r["uid"]: (r["title"] or r["uid"]) for r in db.execute(
        "SELECT uid, title FROM entries WHERE type = 'pipeline'"
    )}


def root_pipelines(db, pipeline_uids):
    """Map root uid -> set of its parent pipelines (member_of parents that are type:pipeline)."""
    from collections import defaultdict
    m = defaultdict(set)
    for r in db.execute("SELECT src_uid, dst_uid FROM edges WHERE rel = 'member_of'"):
        if r["dst_uid"] in pipeline_uids:
            m[r["src_uid"]].add(r["dst_uid"])
    return m


def classify(roots, root_pipes, today, max_age_days):
    """Classify each UNIQUE root once. A root is kept live only if it is within the
    age window AND is the newest root in at least one pipeline it belongs to."""
    # Head date per pipeline = newest modified among all stuck roots in that pipeline.
    head_date = {}
    for r in roots:
        for p in root_pipes.get(r["uid"], ()):  # only pipeline parents
            d = r["modified"] or ""
            if d > head_date.get(p, ""):
                head_date[p] = d

    targets, kept = [], []
    for r in roots:
        a = age_days(r["modified"], today)
        pipes = root_pipes.get(r["uid"], set())
        within_age = a is not None and a <= max_age_days
        is_head = any((r["modified"] or "") == head_date.get(p) for p in pipes)
        # a superseding sibling to cite (any pipeline whose head is newer than this root)
        supersedes = [head_date[p] for p in pipes if head_date.get(p, "") > (r["modified"] or "")]

        if within_age and is_head:
            kept.append({**r, "age": a, "pipes": pipes, "reason": "current head (kept live)"})
        elif within_age and not pipes:
            kept.append({**r, "age": a, "pipes": pipes, "reason": "recent, no pipeline parent (kept live)"})
        else:
            reason = f"stale by age (>{max_age_days}d)" if not within_age else "superseded by newer cycle"
            targets.append({**r, "age": a, "pipes": pipes, "reason": reason,
                            "superseded_by": None})  # superseded_by resolved at execute
    return targets, kept


def age_days(iso, today):
    try:
        return (today - datetime.date.fromisoformat(iso)).days
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="Actually archive (default: dry-run).")
    ap.add_argument("--max-age-days", type=int, default=14, help="Roots older than this are stale (default 14).")
    ap.add_argument("--actor", default="metis-g91", help="Provenance actor for the archive events.")
    args = ap.parse_args()

    today = datetime.date.today()
    db = sqlite3.connect(INDEX)
    db.row_factory = sqlite3.Row
    roots = load_stuck_roots(db)
    ptitles = pipeline_titles(db)
    root_pipes = root_pipelines(db, set(ptitles.keys()))
    targets, kept = classify(roots, root_pipes, today, args.max_age_days)

    def pipe_label(pipes):
        if not pipes:
            return "(no pipeline)"
        return ", ".join(sorted(str(ptitles.get(p, p))[:16] for p in pipes))

    print(f"Stuck-open activation roots (unique): {len(roots)}")
    print(f"  -> archive: {len(targets)}   keep live: {len(kept)}\n")
    print("KEEPING LIVE:")
    for k in sorted(kept, key=lambda r: pipe_label(r["pipes"])):
        print(f"  {k['uid']}  {pipe_label(k['pipes']):<26} age={k['age']}d  {k['reason']}")
    print(f"\nARCHIVING ({len(targets)}):")
    for t in sorted(targets, key=lambda r: (pipe_label(r["pipes"]), -(r["age"] or 9999))):
        print(f"  {t['uid']}  {pipe_label(t['pipes']):<26} age={str(t['age']):>4}d  {t['reason']}")

    if not args.execute:
        print(f"\nDRY-RUN. Re-run with --execute to archive these {len(targets)} roots (reversible).")
        return

    print(f"\nEXECUTING — archiving {len(targets)} roots via tropo-archive.py ...")
    ok = fail = 0
    for t in targets:
        # cite a superseding head if one exists among this root's pipelines
        head = None
        for p in t["pipes"]:
            hd = [r for r in roots if p in root_pipes.get(r["uid"], ()) and (r["modified"] or "") > (t["modified"] or "")]
            if hd:
                head = max(hd, key=lambda r: r["modified"] or "")["uid"]
                break
        cmd = [sys.executable, ARCHIVE_TOOL, t["uid"],
               "--reason", f"Stale activation root swept ({t['reason']}); cycle complete. tropo-sweep-stale-roots, metis-g91 2026-07-21.",
               "--actor", args.actor]
        if head:
            cmd += ["--superseded-by", head]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            ok += 1
        else:
            fail += 1
            print(f"  FAIL {t['uid']}: {res.stderr.strip()[:120]}")
    print(f"\nDone. archived={ok}  failed={fail}")
    print("Reverse any single one with:  python3 vault/tools/tropo-archive.py <uid> --unarchive")


if __name__ == "__main__":
    main()
