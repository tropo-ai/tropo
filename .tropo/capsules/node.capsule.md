---
uid: 1f22c2df
name: "node"
type: capsule-definition
extends: core
version: "1.0"
tier: os
author: argus
created: 2026-06-14
created_by: argus-a112
modified: 2026-06-14
modified_by: argus-a112
status: draft
meta_status_rollup:
  to-do: [draft]
  in-progress: [active]
  done: [locked, archived]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
member_of:
  - "8dd772a0"   # tropo-governance
composes_with:
  - ee814120   # core.capsule — inherited floor
  - 1e9c3f7a   # entity.capsule — the ACTOR primitive; node is its deliberate counterpart (see §Node vs Entity)
tags: [capsule-definition, node, graph-node, knowledge-graph, person, organization, concept, visibility, private-by-construction, market-map]
---

# node — Capsule Definition v1.0

## 1. Intent

A **node** is the generic graph node — a durable vessel for **a person, organization, or concept you have a long-running association with**, in your personal or professional life. Where `project` / `document` / `task` are *purpose-built* nodes (they exist to move work), a `node` is open-purpose: it exists to **remember a thing and connect it** — Tracy (`subtype: person`, your wife), Karpathy (`subtype: person`, the field), a competitor (`subtype: organization`), `agents-md` (`subtype: concept`).

Two things give a node its value, and the capsule optimizes for both being **cheap**:
1. **A freeform body** — the node file IS a vessel. Write whatever you want in the body: *"Tracy is my wife, birthday March 3, anniversary June 12, favorite color white."* The capsule does **not** mandate body structure (§6). The value is in-the-flow accretion, not ceremony.
2. **Provenance-carrying edges** — relationships to other nodes (`writes-about`, `competes-with`, `aligned-with`, …), each dated + sourced. The graph of edges is what makes the public market-map projection possible.

**The map is a projection, never the source.** The public market map on tropo-ai.com is a *derived* render of the public subset of this graph — never hand-authored, and never an automatic consequence of a node existing. See §4 (the cardinal rule).

This capsule was forged because Metis G78 invented the substrate as a hand-built prototype (`entity_prototype: true` on every node) and Mike-G78 routed the capsule to Argus (event 3590). It is named `node` — **not** `entity` — deliberately: `entity` is already the locked actor primitive. See §Node vs Entity.

---

## 2. Node vs Entity (read this — they collide on the word, not the meaning)

| | **`entity` (1e9c3f7a, LOCKED)** | **`node` (this capsule)** |
|---|---|---|
| What | An **actor** in the vault | A **thing in the world** you track |
| Examples | the crew, you, the vault, a team | Tracy, Karpathy, a competitor, an idea |
| Does it act? | **Yes** — requests/owns/signs work | **No** — it is referenced, never an actor |
| Cardinal field | `principal:` (who it grounds to) | `visibility:` (public or private) |
| Lives where | actor registry | `vault/entities/` (prototype home; folder rename to `vault/nodes/` is an optional follow-up) |

**A node has NO `principal:`** — that is the actor primitive's load-bearing field and it is meaningless here (Tracy does not sign vault work). This absence is the clean line between the two types.

---

## 3. Schema

### Required Frontmatter (in addition to core) — the minimal floor (ergonomics)

| Field | Type | Constraint |
|---|---|---|
| `uid` | 8-hex | Per core. The **canonical** key; graph edges target `to_uid`. |
| `type` | literal | `node`. |
| `subtype` | enum | `person` / `organization` / `concept`. Extensible (earn-the-abstraction — add `place`/`event`/… via amendment when they pull weight). |
| `slug` | string | Lowercase-hyphen; **the filename** (`tracy.md`, `karpathy.md`) + the human reference target for `[[wikilinks]]`. This is the one substrate Tropo names by slug, not UID (§5). |
| `title` | string | ≤120 chars; the readable name ("Tracy", "Andrej Karpathy"). |
| `visibility` | enum | `public` / `private`. **The cardinal field — see §4.** |
| `freshness` | date | When this node was last verified/touched. Lets the map say "verified June 2026" by construction; stale-but-dated beats undated. |
| `state` | enum | `active` / `archived` (per core; no work-status machine — nodes are reference substrate, not work). |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `edges` | list of objects | The graph relationships. Each: `{verb, to (slug), to_uid (8-hex), source, asof, note}`. Inline list (cheap). Verb vocabulary in §7. |
| `tags` | string array | The sort/slice layer (`influencer`, `competitor`, `thesis`, `mindbridge`, `standard`, `wedge-tierN`, …). **`mindbridge` is a forced-private trigger — §4.** |
| `sources` | string array | Provenance for the node itself. |
| `name` | string | Optional short identifier distinct from `title`. |
| `entity_prototype` | boolean | LEGACY — present on the 63 hand-built prototype nodes; dropped on migration to this capsule (§Migration). |

### Body — deliberately freeform (§6)

No required sections. The body is a vessel. Write notes, ideas, history, anything.

---

## 4. The cardinal rule — private-by-construction (the one safety invariant)

**You mix your personal life, your day-job (MindBridge), and your public work in one studio. A node's private content must NEVER reach the public map.** Tracy's birthday, a MindBridge detail — these can never land on tropo-ai.com. The guard is **private-by-construction**, owned by the validator + the renderer, **fail-closed**:

1. **A node is PUBLIC only if `visibility: public` AND no forced-private trigger fires.** Forced-private triggers (override the `visibility` field): `tags` contains a **forced-private tag** — the set `{mindbridge, personal}` (small + extensible; `mindbridge` = day-job, `personal` = e.g. Tracy) · the node is in a private graph/collection · `visibility` is absent or unparseable (**uncertainty → private**).
2. **The public projection is an explicit publish gate.** `render-entity-map.py` is a deliberate, derived-never-authored render; it MUST filter to public-only and exclude every forced-private node. A node being `visibility: public` is **necessary but not sufficient** — publishing is an act, never an automatic consequence.
3. **The validator owns the guard.** A check (§Validation) asserts no forced-private / `visibility: private` node appears in any public projection artifact, and that the projection was produced by the publish step. This is the `node` capsule's equivalent of the loop's brake: the safety property is *guaranteed by the platform*, not trusted to the author.

*If you ever can't tell whether a node should be public, it is private. That default is the whole point.*

---

## 5. Slug-vs-UID (dual-keyed)

Nodes are the one slug-named substrate. Resolution is dual-keyed:
- **`uid`** is canonical: graph edges target `to_uid`; the index keys the node by `uid` like everything else; identity is the UID.
- **`slug`** is the filename + the human/wikilink layer: `[[tracy]]` resolves via a **slug→uid alias map** (built at index time) to the node's `uid`. Edges SHOULD carry both `to` (slug, human-readable) and `to_uid` (canonical); a rebuild backfills `to_uid` from the slug map and flags any `to` slug that doesn't resolve.

This preserves the UID-canonical invariant (everything has a uid) while giving the cheap human-named ergonomic layer.

---

## 6. Body is a vessel (the ergonomic constraint — Mike-G79 lock)

**The map grows by living, not by batch.** Low friction is the design constraint: if adding a node or edge is expensive, the discipline dies. So this capsule mandates **no body structure** — the body is freeform notes. Node + edge creation should be a one-gesture path (a forthcoming `add-node` / `add-edge` skill/tool); the capsule deliberately imposes a *minimal* required-frontmatter floor (§3) and leaves everything else optional. This is a Self-Healing-adjacent habit (notice a person/org/idea that matters → add or refresh its node), not a scheduled chore.

---

## State Machine

```
active → archived   (a node you no longer track; historical record remains)
```

No `status` work-machine. `state: active|archived` per core; `freshness:` is the dated currency field.

---

## 7. Edge verb vocabulary (the relation taxonomy — answers Metis G79 event 3598)

Edges use an **open, curated** verb vocabulary — keep small, earn new verbs. The capsule lists the catalog; an unknown verb is a **WARN** (surface, don't block — ergonomics), not an ERROR.

**Catalog (v1.0):** `writes-about` · `aligned-with` · `works-at` · `builds` · `embodies` · `embodied-by` · `competes-with` · `opposed-by` · `held-by` · `originated-by` · `partners-with` · `funds` · `cites`.

Each edge carries provenance: `verb · to (slug) · to_uid · source · asof · note`. A new verb is allowed (WARN) and should be added to this catalog by amendment when it earns recurring use.

---

## 8. Governance Rules (in addition to core)

1. **A node has no `principal:`.** It is not an actor (the clean line vs `entity.capsule`).
2. **Private-by-construction is fail-closed (§4).** Public requires `visibility: public` AND no forced-private trigger; uncertainty resolves to private; the public projection is a publish gate the validator guards.
3. **`subtype` is immutable** (core Rule 4 extends to subtype); re-classify by archiving + re-authoring.
4. **Edges carry provenance.** Each edge has `source` + `asof`; `to_uid` is canonical (backfilled from the slug map).
5. **`freshness` is maintained on touch.** When you touch a node and the world has moved, bump `freshness`. Stale-undated is worse than absent on a map that claims "verified."
6. **Cheap creation is a rule, not a nicety.** Amendments that add required frontmatter or mandate body structure must justify against the ergonomic constraint (§6) — the substrate's value depends on in-the-flow accretion.

---

## 9. Validation Checks (WARN at v1.0; ERROR-ratchet once the renderer + add-node path land)

1. `type: node`; `subtype ∈ {person, organization, concept}`; `slug` present (lowercase-hyphen) + matches filename; `title` present; `state ∈ {active, archived}`.
2. `visibility ∈ {public, private}`; **absent/unparseable → treated as private** (fail-closed, §4).
3. **`check_node_private_by_construction`** — no node with a forced-private trigger (`mindbridge` tag / private graph / personal flag) AND `visibility: public`; and no forced-private / `visibility: private` node appears in any public projection artifact. **The cardinal safety check.** ERROR-ratchet.
4. **`check_node_edges_resolve`** — each edge's `to_uid` resolves to a node; each `to` slug resolves via the slug→uid map; verb is in the §7 catalog (unknown → WARN).
5. `freshness` is a valid date.
6. **`check_node_no_principal`** — a `type: node` entry MUST NOT carry `principal:` (Rule 1; the entity/node line).

Core checks inherited.

---

## 10. Composes-With

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor.
- **[entity.capsule (1e9c3f7a, LOCKED)](entity.capsule.md)** — the **actor** primitive; `node` is its deliberate counterpart (§2). They share `person`/`organization`-shaped concepts but differ in kind: entities *act*, nodes are *tracked*. Untouched by this capsule.
- **`render-entity-map.py`** (`.tropo-studio/scripts/`) — the publish-gated renderer that projects the **public** subset to the market map; the §4 cardinal rule is enforced here + at the validator.
- **A forthcoming `add-node` / `add-edge` skill** — the one-gesture creation path the ergonomic constraint (§6) requires.

---

## Migration (the 63 prototype nodes)

The hand-built prototype at `vault/entities/` carries `entity_prototype: true` + flat `type: organization|person|concept`. Migration to this capsule: `type: <flat>` → `type: node, subtype: <flat>`; drop `entity_prototype`; backfill `to_uid` on edges from the slug map; confirm `visibility` + `freshness` present (default-private on absence). A bulk migration (script or sa.* fan-out) is a follow-up, gated on this capsule's lock; until then the prototype nodes remain `entity_prototype: true` and are exempt from the §9 checks.

---

## Changelog

| Version | Date | Change | By |
|---|---|---|---|
| 1.0 | 2026-06-14 | Initial draft. Forged per Mike-G78 directive (event 3590) + the Metis G78/G79 entity-substrate prototype (`vault/entities/00-README.md`). Defines `type: node` + `subtype: person\|organization\|concept` — the generic, open-purpose graph node (vessel for personal + professional associations), deliberately named `node` (not `entity`, which is the locked actor primitive — §2). Cardinal rule: private-by-construction, validator-owned + fail-closed (§4). Edge verb taxonomy answers Metis 3598. Body deliberately freeform (§6). Mike-A112 walk locked the name (`node` + subtypes), the safety crux, and the six design questions. | argus-a112 |

---

*node capsule definition | v1.0 DRAFT | the generic graph node | counterpart to the locked entity (actor) capsule | UID `1f22c2df`*
*"project/document/task move work. A node remembers a thing and connects it. The map is a projection — and a private node never leaves home."*
