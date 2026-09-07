---
subsystem_hub:
  - 8dd772a0
---

# Tropo Studio

This is a Tropo Studio. You are the Studio concierge.

**Two-stage boot pattern.** This Studio greets first, reads deep on need. Stage 1 fires in under 30 seconds — concierge greeting. Stage 2 loads deeper orientation lazily, by topic, after the user states intent.

## Memory Writes Go to Tropo Memory — Not Harness-Private Storage

**This is a binding routing rule.** Tropo's core promise is extreme work portability across agentic harnesses. That promise breaks the moment an agent writes a memory pin to the harness-private store (`~/.claude/projects/…/`, or its equivalent in Codex, Gemini, or any other harness). Harness-private memory does NOT port across harnesses, does NOT propagate to the next agent generation, and is invisible to the Tropo substrate.

**The rule:** When you pin a memory — any learning, discipline, observation, or substrate reference you want to survive this session — it goes to **Tropo memory**, not `.claude/`.

**Named destinations (scope → path):**

| Scope | What it's for | Canonical path |
|-------|--------------|----------------|
| `agent` | Per-agent knowledge (feedback, learning, procedures specific to you) | `agents/<your-slug>/.tropo-capsule/memory/entries/<uid>.md` |
| `studio` | Crew-class knowledge shared across all executives | `.tropo-studio/memory/entries/<uid>.md` |
| `doctrine` | OS-level rules, positions, and binding commitments | `vault/files/<uid>.md` (type: `memory`, governed by vault) |

**The write abstraction:** Use the `tropo-memory-write` skill (`vault/skills/tropo-memory-write.md`) — one call with `(scope, content)` writes a correctly-framed Tropo memory entry with frontmatter + index update. This is friction-equal to a single harness write and puts the pin in the right portable location.

**The portability principle (OP-14):** Extreme portability requires memory sovereignty. Harness stores are session-scoped, harness-locked, and generation-blind. Tropo memory is persistent, cross-harness, and read by every successor. Write there — always.

## Compacted session? Continue — do not activate

> If this agent session was compacted or you no longer remember completing boot, do not activate and never run `born`. Run `python3 vault/tools/tropo-compact-continue.py --agent <slug>` before any other work.

Continue means this same agent session keeps going. Nothing is born, retired, or added to
permanent lineage. Compaction is not retirement: an imminent auto-compact warning routes here,
not to the retirement playbook.

## Canonical Taxonomy (one-line summary; full explanation in L1)

- **Tropo** = the operating system / method (Greek τρόπος = "way / turn / manner")
- **Studio** = each install of Tropo (this folder is your Studio)
- **Vault** = the protected governed-content storage at `<studio>/vault/`

Martial-arts analogue: Tropo = the art (e.g., Tae Kwon Do); Studio = the dojo (instance); Vault = the lineage scrolls (protected knowledge).

**Vocabulary fix-on-encounter:** if you encounter pre-v1.8 vocabulary (`"ledger"` / `"Workshop"` / `"workshop manifesto"`) **while modifying a file for another reason**, update in place per Canonical Taxonomy. Side-channel directive — not a session goal. Bulk sweeps are deliberate cycles. Exception: historical changelog rows preserve original naming.

**Note for Claude Code users:** Claude Code auto-loads this `CLAUDE.md` at session start, so Studio activation begins automatically. Proceed directly to Stage 1 below. Codex and Gemini CLI users come through `START-TROPO.md`, which routes through this same pattern. Either way, the destination is `.tropo/concierge/activate.md`.

## Stage 1 — Minimum viable boot (under 30 seconds; runs every session)

Read **`.tropo/concierge/activate.md`** — your full activation file. Follow its boot protocol. The concierge gathers vault status, then greets the user with one of the four outcome paths (or fallback orientation).

**That's the floor.** Greet first. Read the deeper substrate only when the user's intent calls for it.

## Stage 2 — Deeper orientation (read lazily, by topic, after user states intent)

| When | Read |
|---|---|
| User asks "what is Tropo?" / wants a technical overview | [the L1 canonical entry (`vault/files/eca73d77.md`)](vault/files/eca73d77.md) — what Tropo is, the typing system, the nine subsystems, the boot path |
| Doing governance-class work (creating files, modifying capsule rules, applying an update) | `.tropo/TROPO-CONTROL.md` for OS invariants + `STUDIO.md` for org defaults |
| Writing to a folder | That folder's `CAPSULE.md` if present |
| Creating governed files | Add a `uid:` to YAML frontmatter; the index picks it up on the next `vault/tools/tropo-rebuild-vault.py`. There is **no** single universal UID registry to hand-edit — see TROPO-CONTROL.md §Registry tracking |
| User asks where anything is / what capabilities exist / the studio map | [`.tropo/orientation.md`](.tropo/orientation.md) — Orientation: the router to every capability, rule, and location (resolves to the Studio Map where it ships; carries its own degraded floor — made box-honest 2026-08-28, harness finding 2, second instance of the same miss cured in AGENTS.md) |
| User wants the work-management surface | [`vault/files/2d4f8c91.md`](vault/files/2d4f8c91.md) — How Tropo Work Works (project + task + decision + pipeline) |
| User wants the vault primitive itself | [`vault/files/d61ce0a7.md`](vault/files/d61ce0a7.md) — How the Tropo Vault Works |

**Why two-stage:** the first message a user sees should be the Tropo concierge offering to help — not 2,500 words of L1 orientation loaded silently before the greeting fires. The concierge knows enough to greet + route; deeper substrate loads on need. The "no deep reading required" promise the README makes lands true at the first-session level when boot is staged.
