---

---

# Tropo Studio — Gemini entry

## Compacted session? Continue — do not activate

> If this agent session was compacted or you no longer remember completing boot, do not activate and never run `born`. Run `python3 vault/tools/tropo-compact-continue.py --agent <slug>` before any other work.

Continue means this same agent session keeps going. Nothing is born, retired, or added to
permanent lineage. Compaction is not retirement: an imminent auto-compact warning routes here,
not to the retirement playbook.

## Ordinary cold start

This is not a compacted session? Then this is a normal start: read
[START-TROPO.md](START-TROPO.md) and follow its activation path. Gemini CLI loads this file
automatically; `START-TROPO.md` is the universal human-invoked entry for every harness.

## Why this file exists

Gemini reads `GEMINI.md` the way Claude reads `CLAUDE.md` and Codex reads `AGENTS.md`. Without it,
a compacted Gemini session would reach no Tropo instruction at all and could route itself to
activation — minting a successor for a session that is still alive.
