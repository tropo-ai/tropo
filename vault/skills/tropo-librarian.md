---
skill: tropo-librarian
name: tropo-librarian
type: how-to
purpose: Spawn and run a session librarian — a subordinate agent that holds your working set warm and answers with citations, so substrate questions stop costing executive context
when: Entering a heavy work phase (build cycle, release coordination, deep review) where you will ask many questions of the same working set
mode: inline
params:
  - task_uid      # the active work item the feed is built around
  - body_budget   # chars of governed bodies in the feed; default 400000
uid: 69589e4d
status: active
owner: metis
created: 2026-08-15
created_by: metis-g107
governed_by: 8dd772a0
extraction_scope: ship
schema_version: 2
trigger_description: 'Reach for this when your next hour holds many questions about the same work. One orient() call builds the feed; one spawn gives you a colleague who answers in seconds with citations. Librarian L1 contract per dev-spec d317f532; design: vault/files/0e46a5ab.md.'
tags:
  - librarian
  - active-mode
  - context-architecture
refs:
  - d317f532
  - 0e46a5ab
---

# tropo-librarian — spawn the session librarian

**What it is:** a subordinate agent (Haiku-class) whose context window holds your working set so
that "what does the spec say about AC5?" is one question to a warm colleague instead of a
grep-and-read expedition. **orient() finds the evidence, the librarian keeps it warm, the
substrate keeps it true.**

## 1. Build the feed

```bash
python3 vault/tools/tropo-orient.py --task <task_uid> --as <you> \
    --for-librarian /path/to/scratch/librarian-feed.md [--body-budget 400000]
```

One deterministic artifact: the tier-labeled evidence (ranked view, COMPLETE one-hop roster with
governed ranks, keyword hits) plus the bodies of the top-ranked governed documents, budget-capped
with every exclusion named.

## 2. Spawn and feed

Spawn one subagent (cheapest capable model class) with the feed artifact plus your standing set:
the active plan/spec, your own charter + transfer, and the latest crew brief. Bind the contract
in the spawn prompt — these three rules verbatim:

- **write-never** — the librarian writes nothing, proposes nothing, runs nothing that mutates.
- **citations-always** — every answer names the UID(s) it draws from; an uncited claim is void.
- **not-in-my-context** — when the feed doesn't contain the answer, it says exactly that and
  suggests which UID from the roster might; it never guesses.

The librarian inherits AGENT-ORIENTATION's boundaries. No executive may cite "the librarian
said" as provenance — the librarian's *citation* is the source, and any claim that matters gets
verified against the cited file before it drives a decision.

## 3. Use, refresh, measure

- **Ask in plain questions.** Treat answers as *where-it-is* plus *what-it-says-per-citation*.
- **Refresh = feed a new packet, not respawn.** On task switch, run step 1 for the new task and
  send the artifact as a message; the librarian keeps its accumulated set.
- **Log every exchange** (AC3, the numbers decide L2): append to
  `agents/<slug>/.tropo-capsule/librarian-log.jsonl`:

```json
{"ts": "YYYY-MM-DDTHH:MMZ", "task_uid": "...", "question": "...", "cited_uids": ["..."], "useful": "y", "est_tokens_saved": 8000}
```

## 4. Stand down

The librarian is **cache, never memory** — anything it surfaced that matters must already be in
substrate by normal governed paths. When the work phase ends, let it die with the session; note
the stand-down. Its successor rebuilds from files + orient() in minutes, and that cheapness is
the proof the design is right.
