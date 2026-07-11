---
uid: null
title: "Tropo Cross-Vault member_of — Edge-Legality Contract Reference"
status: locked
type: schema-reference
tier: os
schema_version: 1
owner: talos
created: '2026-07-08'
modified: '2026-07-08'
refs:
 - path: "vault/files/4275b01c.md"
   title: "Cross-vault member_of primitive — per-vault D7 grounding + up-lattice cross-segment edges (ADR-051)"
 - path: "vault/files/18059aef.md"
   title: "ADR-051"
 - path: "vault/files/dd16c90c.md"
   title: "Signed graph gate (I1/I3/I5)"
 - path: "vault/files/5d3ab142.md"
   title: "Audience lattice + publish/mount rulings"
---

# Tropo Cross-Vault `member_of` — Edge-Legality Contract Reference v1

*The authoritative contract for how a `member_of` edge is classified once it crosses a vault boundary — the enforcement surface `check_cross_vault_member_of` (`vault/tools/tropo-validate.py`) and the composed-index edge-exclusion layer (`vault/tools/lib/gardener.py`) both implement.*
*Locked v1 on 2026-07-08 by Talos T26, per dev-spec [4275b01c](../../vault/files/4275b01c.md) implementing [ADR-051](../../vault/files/18059aef.md).*
*Style mirrors [`compose-lockfile-schema.md`](compose-lockfile-schema.md) in this folder.*

---

## Overview

`member_of` carries **two distinct roles**, and this contract governs both:

1. **PRIMARY grounding `member_of`** — the D7 anchor. Makes a work-item *grounded* (not orphaned): the edge (possibly via a project chain) traces to a `vault-entity`. **Must be same-vault** — exactly, not merely equal-or-wider.
2. **ADDITIONAL `member_of`** — organizational/relational membership. Does **not** re-ground the item. Legal only **up the audience lattice** (equal-or-wider target).

Every real classification runs through **one shared authority**: `vault/tools/lib/cross_vault_member_of.py`. Both the validator check and the composed-index exclusion layer import and call the SAME functions — this is a dev-spec-mandated constraint (no reimplementation, no drift).

---

## The primary-vs-additional classification rule (judgment call, disclosed)

`f2e8a7b1` §3.1/§8.1 only requires "member_of non-empty; ≥1 entry vault-entity-owned" — there is no `primary_member_of:` field and no ordering contract in the schema. This contract adopts:

> **The PRIMARY grounding edge is the FIRST entry in a record's `member_of` list (declared frontmatter order) that resolves — directly, or transitively through a `type: project` chain — to a project owned by a `vault-entity` homed in the SAME vault-node as the record itself.** Every other entry is ADDITIONAL, classified against the audience lattice.

If NO entry resolves same-vault, but at least one resolves to a *different* vault-entity, the record has a **foreign-primary** (D7-per-vault violation — hard ERROR). If NO entry resolves to *any* vault-entity, the record is a **bare orphan** — a pre-existing, different failure class this primitive does not re-flag (avoids double-reporting under two checks).

---

## Segment/home-node resolution — the authoritative source (v1 correctness fix, 2026-07-08)

Every record's home vault-node is its **own `segment` tag** from the composed index (`vault/00-index.jsonl`, gardener-assigned; defaults to `'private'` when absent — the safety-net floor). This is the SAME source for every record type — work-items AND projects AND vault-entities alike. There is deliberately **no separate ownership-chain-walk as the primary resolution path** for a project's home-node:

- **Resolution order:** (1) if the candidate's own `segment` tag is a tag some real, live `vault-entity` anchors, use it directly — no walk. (2) FALLBACK ONLY (structurally unreachable on today's real substrate, since every record has a segment tag): walk `project.owner` → vault-entity UID → its home tag, then `member_of` parents, recursively (cycle-guarded).

**Why this matters (the bug this fix closes):** an earlier draft walked a project's owner/`member_of` ancestry looking for *any* reachable vault-entity, ignoring the project's own segment tag entirely. A same-segment project whose *sibling* `member_of` entry happened to reference an unrelated wider-segment project would resolve to the WRONG (sibling's) home-node — a false foreign-primary flag on a genuinely same-vault record. Trusting the segment tag directly (matching how work-items are already homed) closes this without needing any new discovery infrastructure.

A `vault-entity`'s own home-node identifier is likewise **its own segment tag**, not its raw UID — `vault_entity_home_node[entity_uid] = segments.get(entity_uid, 'private')`. (An earlier draft used the entity's raw UID, a different keyspace than `segments`, which meant `home == record_home` could never be true for any real record — 259 false-positive ERRORs on live substrate before this fix.)

---

## The audience lattice — additional-edge legality

```
relation(source_segment, target_segment) -> 'equal' | 'up' | 'down' | 'incomparable'
legal = relation in ('equal', 'up')
```

| Relation | Meaning | Legal? |
|---|---|---|
| `equal` | same segment | Yes |
| `up` | target strictly wider (e.g. private → team the owner sees, or anything → `os`) | Yes |
| `down` | target strictly narrower (e.g. team → private) | **No — illegal-but-present** |
| `incomparable` | neither contains the other (e.g. team-A ↔ team-B) | **No — illegal-but-present** |

`os` is universally wider than every other segment (5d3ab142 §3) — legal as an ADDITIONAL edge target from any source. It is **not** automatically legal as a PRIMARY grounding target for a narrower-segment record — the primary rule (above) requires *exact* same-vault, deliberately stricter than the additional-edge rule, per Mike's per-vault ruling (this is intentional, not an oversight; see `4275b01c` §2a).

The live lattice today (`default_two_segment_lattice()`) covers exactly the two real segments in this studio: `{os, private}`. A `team:<uid>` segment (and its own lattice edges) is future work — the `GroupLattice` dataclass's `wider: dict[str, set[str]]` shape is fixture-constructable for tests today and designed to take real group-registry data once one exists (`5d3ab142` §3 names the intended real mechanism; no `type: group` registry exists in this studio yet — a disclosed grounding gap, not built here).

---

## Illegal-but-present semantics (I3, `dd16c90c` / `c2b1b612` §3 v2.1)

An illegal ADDITIONAL edge is never silently dropped and never silently walked:

- **Excluded from adjacency** — `gardener.py`'s `build_illegal_member_of_edge_set()` computes the exact `(source_uid, target_uid)` pairs the graph layer must never traverse, for ALL viewers.
- **Excluded from authority** — contributes nothing to `inbound_live_edges` / rank.
- **Raised as a lint ERROR** — `check_cross_vault_member_of` surfaces it, naming the record, the target, and whether the failure is `down` or `incomparable`.

The record itself remains validly grounded (its primary is unaffected) — only the one illegal edge is excluded + flagged. This is distinct from a foreign-primary violation, which means the record has **no** valid home anchor at all.

---

## Two failure classes — kept distinct

| Failure | What it is | Consequence |
|---|---|---|
| **D7-per-vault violation** | PRIMARY grounding points at another vault-node's `vault-entity` (or none) | Item **not grounded** — hard ERROR, like an orphan |
| **Illegal-but-present edge** | An ADDITIONAL edge points down-lattice / incomparable | Item **still validly grounded**; the edge is excluded + lint ERROR |

---

## Real, disclosed finding on live substrate (not a schema violation to fix here)

Running this check against the real studio (before reporting BUILT) surfaced 8 records — old `status: closed` backlog tasks, `owner: unknown`, bare `member_of: [cd1fcd25]` — with no explicitly-authored `segment:` field, falling to the `'private'` safety-net default while genuinely organized under the shared `os`-segment `dev-pipeline` project. Per this contract's deliberately strict primary rule, these are literal D7-per-vault violations. This is disclosed as a real segment-tagging-hygiene finding for Argus/Vela's judgment (a candidate for an explicit `segment: os` re-tag, since they are shared backlog, not personal-private items) — **not silently re-tagged by this build**, which validates grounding and does not own re-classifying unrelated work-items.

---

## Refs

- **Dev-spec:** `vault/files/4275b01c.md` — Cross-vault member_of primitive (ADR-051)
- **ADR-051:** `vault/files/18059aef.md`
- **Signed graph gate:** `vault/files/dd16c90c.md` (I1/I3/I5)
- **Audience lattice + mount rulings:** `vault/files/5d3ab142.md`
- **D7 grounding invariant:** `vault/files/f2e8a7b1.md`
- **Vault-entity capsule (per-vault-node reframe):** `vault/capsules/tropo-vault-entity.capsule.md`
- **Compose-Lockfile Schema (style precedent, sibling primitive):** `.tropo/schema/compose-lockfile-schema.md`
- **Shared classification module:** `vault/tools/lib/cross_vault_member_of.py`
- **Validator check:** `vault/tools/tropo-validate.py::check_cross_vault_member_of`
- **Composed-index exclusion:** `vault/tools/lib/gardener.py::build_illegal_member_of_edge_set`

---

*Cross-Vault member_of Edge-Legality Contract v1 | Locked | Talos T26 | 2026-07-08*
*"Primary is home. Additional only ever points up."*
