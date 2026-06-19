---
uid: d4f9c2e1
folder: ".tropo/definitions/"
type: capsule
owner: argus
governed_by: 222873b9
created: 2026-04-16
created_by: argus-a24
v1_61_channel_tail_note: "Argus A97 2026-06-04 — v1.61 channel-retirement tail fix; replaced dead channel-post instructions with the canonical tropo.broadcast.crew event-log pattern. No contract change."
member_of:
  - "8dd772a0"   # tropo-governance (v1.8 Stream B1 backfill)

---

# `.tropo/definitions/` — Controlled Vocabulary Definitions

This folder holds the canonical vocabulary definitions for all Tropo-OS controlled terms. Every term used in frontmatter — stage values, relationship types, tag labels — is defined here with its canonical name, prose definition, and natural language aliases.

**Governing spec:** [Ledger Schema v2 Architecture Specification](../../vault/files/222873b9.md) §2.5 and §3.

---

## What Belongs Here

Three JSONL definition files — one per vocabulary class:

| File | Vocabulary class | Governs |
|------|-----------------|---------|
| `stages.definitions.jsonl` | Pipeline stages | Valid values for `stage:` frontmatter field |
| `edge-types.definitions.jsonl` | Relationship types | Valid `rel:` values in `relationships:` array and `00-graph.jsonl` |
| `tags.definitions.jsonl` | Tag labels | Conventional tag values for `tags:` frontmatter field |

No other files belong here. The JSONL files are the definitions. The spec (governing spec above) explains how to use them.

---

## The Definitions Pattern

Every row in a definitions file:

```jsonl
{"term":"<canonical>","definition":"<prose meaning>","aliases":["<alt>","<alt>"],"type":"<stage|edge|tag>"}
```

- **`term`** — the canonical value. Always what agents write in frontmatter.
- **`definition`** — human-readable prose. What this term means.
- **`aliases`** — natural language synonyms. When an agent encounters any alias in human input, it writes the canonical `term` instead. Natural language in, canonical term out.

---

## Alias Resolution Contract

This is the governing behavior for any agent reading these files:

1. When receiving human input containing a term from any `aliases` array → write the canonical `term` in frontmatter output
2. When writing frontmatter independently → always use the canonical `term`, never an alias
3. When reading existing frontmatter → both canonical terms and known aliases are valid inputs; normalize on write

This produces natural vocabulary normalization without enforcement. Agents self-correct to canonical terms because they read the definitions first.

---

## Write Access

| Agent | Can do |
|-------|--------|
| Argus | Add new edge types; update definitions; create new vocabulary classes |
| Vela | Add new stages; add new tags; maintain all three files |
| Metis | Propose new terms via channel; does not write directly |
| Any executive | Propose new terms via a `tropo.broadcast.crew` event (`category: ops`) (`channels/ops.md` retired per Rule 13); Vela or Argus adds them |

**To add a new term:** append a new JSONL row to the appropriate file. Include `term`, `definition`, at least two `aliases`, and `type`. Emit a `tropo.broadcast.crew` event (`category: ops`) announcing the addition (`channels/ops.md` retired per Rule 13).

**To deprecate a term:** add `"deprecated": true, "replaced_by": "<canonical-term>"` to the row. Do NOT remove the row — existing frontmatter may reference it, and the alias resolver needs to know what it maps to.

**To change a canonical term:** you cannot rename a canonical term that is already in use in frontmatter. Create a new term, deprecate the old one with `replaced_by`. Run a migration sweep to update existing frontmatter.

---

## What Does NOT Belong Here

- Capsule definitions → `.tropo/capsules/`
- Templates → `.tropo/templates/`
- Playbooks → `.tropo/playbooks/`
- Skills → `.tropo/skills/`
- Agent governance → `agents/`

---

## Governance Rules

1. Every term must have a `definition` (prose) and at least two `aliases`.
2. No two terms in the same file may share a `term` value or share an `aliases` entry — aliases must be unique across the file.
3. The `term` value, once used in any vault frontmatter, is immutable. Deprecate, don't rename.
4. New vocabulary classes (additional definition files) require Argus architectural review before adding.

---

*`.tropo/definitions/` | Controlled Vocabulary | Governed by Ledger Schema v2 spec `222873b9` | Created 2026-04-16 by Argus A24*
*"Natural language in. Canonical term out. Always."*
