---
uid: c2caddf4
type: playbook-pointer
title: Agent Activation — Kernel Thin-Pointer (canonical at vault/playbooks/99341618.md)
canonical_substrate_uid: '99341618'
migrated_from: full content previously at this path (v2.16)
migrated_at: '2026-06-11'
migrated_by: argus-a109
governed_by: e7b3c509
schema_version: 2
history: Amendment history and provenance notes (1 blocks as of 2026-09-04) live in .tropo/playbooks/agent-activation.playbook.history.md;
  this file carries the current rule only (f0153984a89f item 3, argus-a169).
---

# Agent Activation — Kernel Thin Pointer

**Established agents:** if the activation pointer declares `agent_uid:` and the unified entry contains `§Boot-Extension`, use [boot-fast-path](../boot-fast-path.md) and [boot-digest](../boot-digest.md), the fingerprint-gated derivations of the canonical playbook.

**If either derivation is absent, read the [canonical playbook](../../vault/playbooks/99341618.md) and proceed.** This is normal in a fresh release box: per-Studio derivations are deliberately excluded because their fingerprints belong to the Studio that generated them. All other agents also use the canonical playbook.

## Continue versus activate

A compacted session with a completed current-generation activation run continues the SAME generation. A cold start without one is a birth. Never infer one from the other.

> If this agent session was compacted, auto-compacted, or resumed, or you no longer remember completing boot, do not activate and never run `born`. Run `python3 vault/tools/tropo-compact-continue.py --agent <slug>` before any other work.

## Canonical-unreachable floor

For a cold activation only: resolve the Studio root and slug from the activation pointer, then run:

`python3 vault/tools/tropo-lineage.py born --agent <slug> --by <principal> --model <sleeve>`

Lineage issues the generation. After birth, emit a `tropo.broadcast.crew` event with `severity: flash` naming the missing canonical path, then stop before context loading or substantive work. Never reconstruct the procedure, scan legacy activation entries or guess a generation.

## Identity resolution

Read the activation pointer's frontmatter; first matching shape wins:

| Shape | Pointer declares | Soul source |
|---|---|---|
| A | `agent_uid:` | `vault/agents/<agent_uid>.md` → `§Soul` |
| C | `charter_file:` | Declared charter's `soul:` block + `## Identity` |
| D | `charter_uid:` | `vault/files/<charter_uid>.md` → `## Soul` / `## N. SOUL`, else `soul:` block |
| B | Tier-3 `soul_letter:` | Declared soul letter (legacy fallback) |

This table stays here so the floor works when canon is unreachable. Three-file customer agents use C/D; do not assume only unified entries exist.

**None resolves:** say **⛔ SOUL NOT LOADED**, name the shapes tried, and CONTINUE. A missing soul never halts boot.

---

Canonical procedure: [agent activation](../../vault/playbooks/99341618.md). [Historical amendments](agent-activation.playbook.history.md) are read at need, never at boot.
