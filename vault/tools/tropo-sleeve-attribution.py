#!/usr/bin/env python3
"""
---
uid: 241f685d
name: sleeve-attribution
type: tool
title: "sleeve-attribution — which model produced which governed artifact"
status: active
owner: argus
domain: "Multi-model crew measurement"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-sleeve-attribution.py"
script_path: vault/tools/tropo-sleeve-attribution.py
spawnable_by:
  - all-executives
created: 2026-08-21
created_by: argus-a152
modified: 2026-08-21
modified_by: argus-a152
version: "1.0"
schema_version: 2
extraction_scope: argo-reference
belt: false
trigger_description: "Ask which sleeve authored a governed artifact, or how authorship distributes across models. Read-only derivation; writes nothing."
---

WHY THIS DERIVES RATHER THAN STORES
-----------------------------------
Mike, 2026-08-21, on running a deliberately multi-model crew (Talos on GLM,
Argus on Opus, Metis moving to Fable): stamping the sleeve on findings turns
the crew into an instrument you can read. Over releases you learn which model
catches which defect class.

The obvious build is a `sleeve:` field on every artifact. That is the wrong
build, and this studio already has the scar: a stored copy of a derivable fact
goes stale and then lies. Argus A152's own agent card read `model: GPT-5.6 Sol`
for four generations after that sleeve was gone, because a stored lifecycle
field was synced by events that had already happened.

Nothing needs storing. `created_by: argus-a152` already names the generation,
and `agents/<slug>/lineage.jsonl` already records the model that generation was
born on. The join is the answer, it is exact, and it is retroactive: 1,478 of
the 1,801 artifacts carrying an agent-generation `created_by` resolve to a
sleeve today with zero writes and zero migration.

WHAT IT CANNOT TELL YOU
-----------------------
323 artifacts do not resolve — their generation predates sleeve recording in
lineage. Those are reported as `unrecorded`, never guessed.

The sleeve string itself is free text supplied at birth and has drifted into
non-comparable variants (`claude-opus-5[1m]`, `Claude Opus 5 (1M) — Claude Code
/ VSCode`, `auto`, truncated Cursor strings). `--family` folds them to a coarse
family for comparison; `--raw` shows exactly what was recorded. Normalising the
value AT BIRTH is the real fix and is not in this tool's scope — this tool
reports what lineage holds, including its mess.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

GEN_RE = re.compile(r"^[a-z]+-[a-z]\d+$")
FAMILIES = ("opus", "sonnet", "fable", "haiku", "glm", "gpt", "grok", "gemini")


def studio_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def sleeve_by_generation(root: pathlib.Path) -> dict[str, str]:
    """generation key -> model string, read from every agent's lineage."""
    out: dict[str, str] = {}
    for lineage in sorted((root / "agents").glob("*/lineage.jsonl")):
        agent = lineage.parent.name
        for line in lineage.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # a malformed line is not evidence of a sleeve
            if rec.get("t") == "born" and rec.get("model"):
                out[f"{agent}-{str(rec['gen']).lower()}"] = str(rec["model"])
    return out


def family(model: str) -> str:
    low = model.lower()
    for name in FAMILIES:
        if name in low:
            return name
    return "other"


def index_rows(root: pathlib.Path):
    path = root / "vault" / "00-index.jsonl"
    if not path.is_file():
        return
    for line in path.open(encoding="utf-8"):
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Which sleeve produced which governed artifact.")
    ap.add_argument("--uid", help="attribute one artifact")
    ap.add_argument("--type", help="restrict the roll-up to one artifact type")
    ap.add_argument("--agent", help="restrict to one agent")
    ap.add_argument("--raw", action="store_true",
                    help="report the exact recorded model string, unfolded")
    args = ap.parse_args(argv)

    root = studio_root()
    sleeves = sleeve_by_generation(root)
    label = (lambda m: m) if args.raw else family

    if args.uid:
        for row in index_rows(root):
            if row.get("uid") == args.uid:
                by = str(row.get("created_by") or "").strip().lower()
                model = sleeves.get(by)
                print(f"{args.uid}  {row.get('type','?')}")
                print(f"  created_by : {by or '(none)'}")
                print(f"  sleeve     : {model or 'unrecorded'}")
                return 0
        print(f"{args.uid}: not in the current index", file=sys.stderr)
        return 1

    counts: collections.Counter = collections.Counter()
    unresolved = 0
    for row in index_rows(root):
        if args.type and row.get("type") != args.type:
            continue
        by = str(row.get("created_by") or "").strip().lower()
        if not GEN_RE.match(by):
            continue
        if args.agent and not by.startswith(args.agent.lower() + "-"):
            continue
        model = sleeves.get(by)
        if model is None:
            unresolved += 1
            continue
        counts[label(model)] += 1

    total = sum(counts.values())
    scope = args.type or "all types"
    if args.agent:
        scope += f" · {args.agent}"
    print(f"governed artifacts by sleeve — {scope}")
    print(f"  resolved {total} · unrecorded {unresolved}")
    for name, n in counts.most_common():
        share = (100.0 * n / total) if total else 0.0
        print(f"    {name:<22} {n:>5}  {share:4.1f}%")
    if unresolved:
        print("  (unrecorded = generation predates sleeve recording; never guessed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
