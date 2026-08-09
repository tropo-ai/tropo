#!/usr/bin/env python3
"""One-time backfill: build each durable agent's lineage.jsonl from its history.

Run once, read-only against the vault, create-only against agents/<slug>/.
It never touches an existing lineage.jsonl and never modifies an activation
record. The 516 activation entries stay exactly where they are as frozen
history; this only projects them forward into the file the lifecycle reads.

Durable agents only, and the list is derived rather than typed: an agent is
durable if it has a folder with identity in it. sa.* agents, pipeline runs and
workers keep no lineage because nothing succeeds them.

--check prints what it would write and exits without writing anything.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIELD = lambda k: re.compile(rf"(?m)^{k}:\s*[\"']?([^\"'\n]+)[\"']?\s*$")
F_TYPE, F_AGENT = FIELD("type"), FIELD("agent")
F_GEN, F_AT, F_BY = FIELD("generation"), FIELD("activated_at"), FIELD("activated_by")
F_STATUS, F_MODEL = FIELD("status"), FIELD("model")
CLOSED = {"retired", "closed", "abandoned", "stale", "failed"}


def durable_agents(root):
    """An agent is durable if it has an activation pointer or a memory capsule."""
    out = []
    for d in sorted((root / "agents").iterdir()):
        if not d.is_dir() or d.name == "sa":
            continue
        if (d / f"{d.name}-activation.md").exists() or (d / ".tropo-capsule").exists():
            out.append(d.name)
    return out


def history(root, agent):
    rows = []
    for p in (root / "vault" / "files").glob("*.md"):
        try:
            head = p.read_text(encoding="utf-8")[:1500]
        except OSError:
            continue
        t, a = F_TYPE.search(head), F_AGENT.search(head)
        if not t or t.group(1).strip() != "activation":
            continue
        if not a or a.group(1).strip() != agent:
            continue
        g, at = F_GEN.search(head), F_AT.search(head)
        if not (g and at):
            continue
        st = (F_STATUS.search(head).group(1).strip().lower()
              if F_STATUS.search(head) else "")
        by = F_BY.search(head).group(1).strip() if F_BY.search(head) else "unknown"
        model = F_MODEL.search(head).group(1).strip() if F_MODEL.search(head) else None
        rows.append({"gen": g.group(1).strip(), "at": at.group(1).strip(),
                     "by": by, "model": model, "closed": st in CLOSED, "uid": p.stem})
    rows.sort(key=lambda r: (r["at"], r["gen"]))
    return rows


def lines_for(rows):
    out = []
    for r in rows:
        born = {"t": "born", "gen": r["gen"], "at": r["at"], "by": r["by"],
                "backfilled_from": r["uid"]}
        if r["model"]:
            born["model"] = r["model"]
        out.append(born)
        if r["closed"]:
            out.append({"t": "retired", "gen": r["gen"], "at": r["at"],
                        "backfilled_from": r["uid"]})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--check", action="store_true", help="print, write nothing")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    for agent in durable_agents(root):
        dest = root / "agents" / agent / "lineage.jsonl"
        rows = history(root, agent)
        if not rows:
            print(f"{agent:12} no activation history — skipped (a first birth gives G1)")
            continue
        if dest.exists():
            print(f"{agent:12} lineage.jsonl already exists — untouched")
            continue
        lines = lines_for(rows)
        last = rows[-1]
        state = "retired" if last["closed"] else "ACTIVE"
        print(f"{agent:12} {len(rows):>3} generations -> {len(lines):>3} lines, "
              f"ends {last['gen']} {state}")
        if not args.check:
            dest.write_text(
                "".join(json.dumps(l, ensure_ascii=False, sort_keys=True) + "\n"
                        for l in lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
