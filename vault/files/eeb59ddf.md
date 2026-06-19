---
uid: eeb59ddf
name: "ship-artifact"
type: capsule-definition
extends: core
version: "1.4"
supersedes_version: "1.3"
tier: os
author: argus
created: 2026-04-25
created_by: argus-a34
modified: 2026-06-09
modified_by: argus-a105
meta_status_rollup_added: "argus-a104 2026-06-08 — new meta_status_rollup per 4acf3f2d v0.4 DERIVE (Mike-signed 7-capsule lock-break batch); additive (type had no rollup); prior modified argus-a77 2026-05-20"
status: draft
last_body_refactor: 2026-05-20
v1_4_amendment_note: "v1.3 → v1.4 amendment authored 2026-05-20 by argus-a77 under v1.48.0 cycle [c184b781] Stream A per design-spec [6a8d3f17] v0.3 LOCKED. Four substrate-load-bearing additions: (1) Article subtype + editorial state machine — `subtype: article` extension to document type with 4-state editorial enum (draft → reviewed → locked → archived); ship-artifact wrappers inherit the source article's editorial state implicitly. (2) Publish-act semantics — pipeline-written `publication_state:` per-target frontmatter map on ship-artifact wrappers, keyed by target slug, values `live | retracted`; canonical source-of-truth = pipeline §5 sub-gate artifacts; frontmatter = queryable cache (same pattern as existing pipeline-written fields `locked_by` / `locked_at`). (3) External-work/ staging architecture — per-target editorial staging at `argo-os/external-work/<target>/`; gitignored at Studio level; non-destructive invariants protect manually-composed assets from re-extract clobber. (4) L1/L2 composition pattern — markdown-native L1 substrate composes with future real-code L2 apps via the external-work/ staging surface; pipeline accepts binary outputs from anywhere without coupling to how they were produced. Five new validator checks (25-29; WARN at v1.4 / ERROR at v1.5 ratchet except Check 28+29 which stay WARN). New Rule 13 (article-wrapper composition). Entry-level backward-compat 100% (existing v1.3-shape entries continue valid; absent `subtype:` field is the v1.3 default; absent `publication_state:` map is the not-yet-published default). Body-replacement pattern per Mike-A75 lock: UID preserved; v1.3 body content where structurally equivalent preserved verbatim; v1.0/v1.1/v1.2/v1.3 amendment-block prose previously extracted to ship-artifact.history.md remains there; v1.4 amendment narrative landed in this frontmatter field + a new entry in ship-artifact.history.md."
history_file: 437e8944
enforced_enums:
  status: [draft, active, reviewed, locked, archived]
meta_status_rollup:
  to-do: [draft, active]
  in-progress: [reviewed]
  done: [locked, archived]
schema_version: 2
extraction_scope: ship
governed_by: 222873b9
pattern_exemplar: e7b3c509   # playbook.capsule v2.5 — 5-section pedagogy
aligned_with:
  - 7b42d916   # Release Structure as Graph design brief
  - a7c4e5b2   # ADR-035 Declared-Presence Validation Rule
  - 4e5a2011   # Stream 2 D2.1 project-plan
  - c8f2a1d7   # Phase D project-plan
  - a4b9d731   # Metis G54 v1.3 source brief
  - fdda7ceb   # v1.42.0 cycle brief
  - c5a7e391   # Tropo Extraction-and-Publish Pipeline brief (v1.4 NEW)
  - b8f5d293   # Web v1 Release Plan (v1.4 NEW)
  - 6a8d3f17   # v1.46.0 Cycle A design-spec (v1.4 NEW — direct source for amendment)
  - c184b781   # v1.48.0 cycle brief (v1.4 NEW — cycle landing this amendment; brief authored as v1.47 substrate; cycle renumbered v1.47 → v1.48 per Mike-V49 chain-mutability override 2026-05-21)
manifest_root_uid:
  release: b2e7d4a9   # Tropo Release Structure evergreen project (v1.1.1 — release target; default when target field absent)
  web: 4a99638d       # Tropo Website Content Structure evergreen project (v1.3 NEW — web target; minted at v1.42.0 activation)
member_of:
  - "8dd772a0"   # tropo-governance
tags: [capsule-definition, ship-artifact, 5-section-pedagogy, v1.3-multi-target-extraction, v1.4-article-state-publish-act-staging-composition]
---

# ship-artifact — Capsule Definition v1.4

## 1. Intent

Replace the drift-prone parallel `argo-os/starter/` mirror with a **single, graph-shaped, queryable release manifest**. Every shippable file or folder is declared as a ship-artifact vault entry pointing at its canonical source in argo. The default is *"doesn't ship unless declared"*; canonical source is always the live argo vault; cleanup strips Argo-specific blocks at ship-time per declared rules.

The capsule defines the contract every ship-artifact vault entry must satisfy. `build-release.py` walks the ship-artifact graph rooted at the `manifest_root_uid:` project, applies `source_mode:` + `cleanup_rules:` per entry, and produces the release output.

**Load-bearing invariants:**

1. No file ships unless declared in the release manifest AND its canonical source resolves to a file in `argo-os/`.
2. Adding a file to argo does not auto-ship unless under a folder declared `recursive-ship-all`.
3. Removing a declaration removes the file from ship.
4. Build fails loud on missing declaration with present source, OR present declaration with missing source.

Failure mode prevented: silent ship drift between argo and recipient vaults — files appearing or disappearing without manifest intent; broken cross-references shipping to recipients; release output diverging from the canonical argo source-of-truth.

**v1.4 extends the contract** to cover the extraction-and-publish pipeline: editorial-class content (articles) carries its own state machine on the source entry; ship-artifact wrappers declare publication intent via `target:`; the pipeline writes publication outcome via `publication_state:` at publish-act sub-gate-3 completion. Editorial state ≠ extraction-target membership ≠ publication state. Three orthogonal dimensions, declared on the substrate the same way the wrapper itself was declared at v1.0.

---

## 2. Schema

### Required Frontmatter (beyond core)

| Field | Type | Constraint |
|---|---|---|
| `kind` | enum | `folder` or `file`. Determines which other fields apply. Immutable once set. |
| `canonical_source` | string | Vault-root-relative path to argo source. Folders: directory path WITH trailing slash recommended (convention, not enforced). Files: file path. MUST resolve at lock time (Rule 2; see exceptions for `skip` + `structure-only`). Mutable post-lock when change reflects argo path-rename without semantic change. Supersession (Rule 9) required ONLY when recipient-output meaning changes. |
| `source_mode` | enum | One of: `recursive-ship-all`, `recursive-ship-tagged`, `explicit-children`, `structure-only`, `skip`, `direct-copy`. See §Source Modes. |
| `extraction_scope` | enum | One of: `ship`, `argo-reference`, `argo-private`. See §Extraction Scope. |
| `parent` | UID OR `null` | UID of parent folder ship-artifact, OR explicit `null` for the root entry (the manifest-root project). The root is the only entry with `parent: null`; every other entry's `parent:` chain MUST terminate at it. |
| `member_of` | UID array | MUST include the `manifest_root_uid:` capsule-frontmatter value. May include additional projects. |
| `description` | string | ≤280 chars. One-line scannable summary for the vault index. Substantive prose lives in `## Purpose` body section. |

### Optional Frontmatter

| Field | Type | Purpose |
|---|---|---|
| `output_path` | string | Vault-root-relative path in recipient vault. Defaults to mirror `canonical_source` minus `argo-os/` prefix. Override for ship destination ≠ source path (e.g., root-doc relocations). |
| `children` | UID array | Folder-only. Required when `source_mode: explicit-children`; ignored otherwise. Lists ship-artifact UIDs shipping under this folder. |
| `cleanup_rules` | object | File-only (mostly). Keys: `strip_markers`, `broken_link_policy`, `rewrite_uid_refs`, `uid_rewrite_template`. Defaults diverge per target — see Cleanup Rules §Per-target defaults. |
| `governed_folder_capsule` | UID | Optional pointer to folder's CAPSULE.md if it has one. Informational. |
| `notes` | string | Free-form note for non-obvious decisions. |
| `supersedes` / `superseded_by` | UID | Standard supersession pattern for reauthored entries. Bidirectional pair set atomically. |
| `archived_by` / `archived_at` | string / ISO date | Required when direct-retirement archival (not supersession-driven) per Rule 11. |
| `locked_by` / `locked_at` | string / ISO date | Required when `status: locked`. |
| `target` | array | **v1.3.** Always-array. Allowed elements: `release` \| `web`. Default when absent: implicit `[release]` (backward compat 100% with v1.2 entries). Engine iterates per-target; per-target defaults evaluate independently per iteration; output uniqueness per-target namespace. See §Target Semantics below. |
| `publication_state` | object | **NEW v1.4.** PIPELINE-WRITTEN ONLY. Per-target map keyed by target slug. Values: `live` (pipeline confirmed publish-act sub-gate-3 clean for this target) or `retracted` (pipeline executed retract-act for this target). Absent key = never published to that target. Authors do NOT edit this field; Check 27 detects hand-edit drift via git-blame heuristics at build pre-flight. See §Publish-Act Semantics. |

### Target Semantics (v1.3)

The `target:` field declares which extraction target(s) an entry ships to. Multi-target architecture: same content can extract to release zip AND web-content repo via per-target iteration.

```yaml
# v1.2 entries (absent field):
# target: <absent>                # implicit [release] — backward compat 100%; zero migration

# v1.3+ single-target:
target: [release]                 # release-only (matches v1.2 implicit behavior; explicit at v1.3)
target: [web]                     # web-only (new at v1.3)

# v1.3+ dual-target:
target: [release, web]            # extracts to BOTH targets via per-target iteration
```

**Per-iteration execution model:**

When the engine processes an entry with `target: [release, web]`:
1. **Iteration 1 (release):** apply release-target defaults to cleanup_rules (`rewrite_uid_refs: false`), evaluate `source_mode:` under release manifest_root_uid context (`b2e7d4a9`), extract to release output tree at the entry's `output_path:`.
2. **Iteration 2 (web):** apply web-target defaults to cleanup_rules (`rewrite_uid_refs: true` + `uid_rewrite_template: /kb/<uid>`), evaluate `source_mode:` under web manifest_root_uid context (`4a99638d`), extract to web output tree at the entry's `output_path:`.

Each iteration is independent. Entry declares CONTENT once; each target applies its own per-target defaults. Explicit `cleanup_rules:` on the entry overrides BOTH iterations (declarative-override semantics).

**Capsule-frontmatter `manifest_root_uid:` map shape:**

```yaml
manifest_root_uid:
  release: b2e7d4a9                  # Tropo Release Structure (existing)
  web: 4a99638d                      # Tropo Website Content Structure
```

Validator Check 14 reads target-keyed: an entry's `member_of:` must include the manifest_root_uid for EACH target the entry declares. Dual-target entries `member_of:` BOTH roots.

### Publication State Semantics (v1.4 NEW)

The `publication_state:` field is a per-target map captured ON THE WRAPPER (not the source entry) and PIPELINE-WRITTEN at publish-act sub-gate-3 completion. Shape:

```yaml
publication_state:
  web: live                          # pipeline wrote 'live' after publish-act sub-gate-3 clean
  release: live                      # pipeline wrote 'live' for release target on its publish-act
  # mindbridge: (key absent)         # never targeted; pipeline never wrote anything
```

**Enum** (minimal by design — granular pipeline progress is observable via §5 sub-gate artifacts):

| Value | Semantic | Written by |
|---|---|---|
| `live` | Pipeline completed sub-gate-3 (post-deploy verification) for this target | pipeline at publish-act |
| `retracted` | Article was live; pipeline executed retract-act (target sync removed entry) | pipeline at retract-act |
| (key absent) | Never published to this target | implicit; no pipeline write needed |

**Substrate precedent for pipeline-written frontmatter:** capsule v1.3 already establishes `locked_by` / `locked_at` populated at lock-act; `archived_by` / `archived_at` populated at archival-act. The new `publication_state:` field follows the same pattern: substrate captures *what the pipeline did at the act*, not what the author declares in advance.

**Why pipeline-writes-only is convention + detection, not technical lockout:** if authors hand-edit `publication_state:`, substrate drifts from pipeline reality. Mechanism = convention + detection, not write-lockout: pipeline writes at publish-act; authors don't. Check 27 detects hand-edit drift via git-blame heuristics at build pre-flight + flags as substrate-discipline drift. Detection catches drift; the discipline is what prevents it. Same shape as existing pipeline-written fields (`locked_by` / `locked_at`).

**Index queryability:** `publication_state:` flows through the existing `vault/00-index.jsonl` rebuild; O(1) grep answers "list all articles published to web" without walking filesystem state. The index IS the answer to discoverability questions per OP-12 human-navigation doctrine.

### Extraction Scope semantics

| Value | Behavior |
|---|---|
| `ship` | Artifact ships in every Tropo-OS release zip; recipients see this content. |
| `argo-reference` | Lives in argo for crew ops + cross-reference but does NOT ship to recipients. |
| `argo-private` | Argo-only operational content. Does NOT ship. |

**Override mechanism for folder-mode entries:**

- Under `recursive-ship-all`: parent's `extraction_scope:` is ABSOLUTE; file-frontmatter `extraction_scope:` is IGNORED. Exclude specific files by authoring child ship-artifact with `source_mode: skip`.
- Under `recursive-ship-tagged`: file-frontmatter `extraction_scope:` IS load-bearing — that's the discriminator.
- Under `explicit-children`: parent's `extraction_scope:` is informational; only listed `children:` ship.
- Under `structure-only`: parent's `extraction_scope:` determines whether the empty directory is created in recipient vault.
- Under `skip`: field is informational; entry doesn't ship by definition.

**v1.4 note on articles + extraction_scope:** article entries (`subtype: article`) typically carry `extraction_scope: argo-reference` (they live in argo's vault as canonical substrate; they ship to recipients ONLY if a ship-artifact wrapper points at them with `target:` including a published target). The article's own `extraction_scope:` does not gate publication — the wrapper's `target:` does. This decouples *what the article is in argo* from *where the article publishes*.

### Body shape — 2 required sections + 3 optional

1. **`## Purpose`** — One paragraph. Why does this artifact ship? What does it deliver to the recipient vault? Anchored to artifact's role in the release.
2. **`## Description`** — One to three paragraphs. What does the recipient see + use this for? Self-contained — readable without consulting the source.
3. *(optional)* **`## Notes`** — non-obvious decisions captured at authoring time.
4. *(optional)* **`## Cleanup Notes`** — for files with non-trivial `cleanup_rules:`, prose describing what gets stripped + why.
5. *(optional)* **`## Migration Provenance`** — for ship-artifacts authored during Phase D sprint, optional reference to the v1.3.1 path the entry derived from.

---

## Source Modes (substrate-load-bearing)

Six modes. The `source_mode:` field is the primary discriminator for build behavior.

| `source_mode` | Kind | Behavior |
|---|---|---|
| `recursive-ship-all` | folder | Ship every file under `canonical_source` recursively. No per-file check. Use for homogeneous ship-trees. File-frontmatter `extraction_scope:` is IGNORED. |
| `recursive-ship-tagged` | folder | Recurse, but ship only files with frontmatter `extraction_scope: ship`. Use for heterogeneous trees mixing shippable + Argo-private content. |
| `explicit-children` | folder | No source default. Only listed `children:` ship. Use for curated trees where most contents stay private. |
| `structure-only` | folder | Ship the directory in recipient vault but no files. Use for fresh-vault scaffolding. |
| `skip` | folder or file | Entry exists in manifest but does NOT appear in release output. Use as child override under permissive parent. |
| `direct-copy` | file | Copy file as-is, apply `cleanup_rules`. Use for individual files. |

### Override-child shapes under a `recursive-ship-all` parent

When a `recursive-ship-all` parent has child ship-artifact entries, the child's declarations OVERRIDE the parent's recursive default for the specific path. Legal override-child shapes:

| Child source_mode | `output_path:` only | `cleanup_rules:` only | Both |
|---|---|---|---|
| `direct-copy` | ✓ Relocates this file to override path | ✓ Ships to mirror path with non-default cleanup | ✓ Relocates AND applies cleanup |
| `skip` | (skip doesn't ship) | (n/a) | Excludes file from kernel ship; `## Purpose` MUST document why |
| `recursive-ship-all` sub-tree | REJECTED | REJECTED | REJECTED — redundant; use per-file `direct-copy` |
| `structure-only` | REJECTED | REJECTED | REJECTED |
| `recursive-ship-tagged` | REJECTED | REJECTED | REJECTED |
| `explicit-children` | REJECTED | REJECTED | REJECTED |

Check 19 confirms a per-file override's `canonical_source:` falls under its parent's recursive tree. REJECTED shapes fail Check 5.

### When `skip` applies

`skip` is THE positive-rule exclusion mechanism. Scope:

- **Top-level `skip`** (parent = `null`): REJECTED. Top-level entries either ship or are omitted.
- **`skip` under `recursive-ship-all`**: LEGAL. Excludes specific file/folder from blanket-ship. `## Purpose` MUST document reason.
- **`skip` under `recursive-ship-tagged`**: LEGAL. Overrides tag-based ship. Same audit requirement.
- **`skip` under `explicit-children`**: REJECTED. Exclusion is by omission from `children:`.
- **`skip` under `structure-only`**: REJECTED. Structure-only ships zero files; child overrides meaningless.

`skip` entries' `canonical_source:` is informational (Check 4 exception); path doesn't have to exist. Skip entries appear in manifest graph for audit; don't appear in release output.

### Folder-mode directory creation

All folder-mode source_modes implicitly create the recipient-vault directory at `output_path:`. `explicit-children` creates the directory AND ships only listed children; empty `children:` is equivalent to `structure-only`. `skip` folders do NOT create the directory.

**Exclusion semantics:** Exclusion is always by omission or explicit `skip`. There is no "ship all except X" negative rule — negative rules are where drift lives. This is the hardening payoff.

---

## Cleanup Rules

Files that mostly ship but contain Argo-specific or release-specific blocks use **sub-file marker cleanup**:

```markdown
<!-- argo-only:start -->
This block is in argo source; STRIPPED at release-build.
<!-- argo-only:end -->

<!-- release-only:start -->
This block is in argo source; KEPT in release output; argo readers ignore by convention.
<!-- release-only:end -->
```

**Strip rules:**

| Block type | Argo source contains | Release output contains |
|---|---|---|
| `argo-only` | ✓ | ✗ (stripped, including markers) |
| `release-only` | ✓ | ✓ (kept, including markers — readers learn the convention) |
| Default (no block) | ✓ | ✓ |

**`cleanup_rules:` frontmatter shape (per-target defaults table; `uid_rewrite_template:` field):**

```yaml
cleanup_rules:
  strip_markers: true              # default true (universal across targets)
  broken_link_policy: fail-loud    # default fail-loud per Decision 2 (universal)
  rewrite_uid_refs: false          # default DIVERGES per target — see table
  uid_rewrite_template: null       # default /kb/<uid> for web target; null for release target
```

**Per-target defaults:**

| Field | `target: [release]` default | `target: [web]` default | Rationale |
|---|---|---|---|
| `rewrite_uid_refs` | `false` | `true` | Web renders UIDs at URL pattern; release ships UIDs literally (recipients read in their vault). |
| `uid_rewrite_template` | n/a (no rewriting) | `/kb/<uid>` | Configurable per web surface. Different web routes (e.g., `/agentic-builders/<uid>`, `/docs/<uid>`) override per-entry via explicit `cleanup_rules:`. |
| `strip_markers` | `true` | `true` | Universal — unchanged. |
| `broken_link_policy` | `fail-loud` | `fail-loud` | Universal — unchanged. |

**Declarative-override semantics:** If entry declares explicit `cleanup_rules:`, those values override per-target defaults universally (applies to all iterations regardless of target). Author's intent beats engine convention.

**Broken-link policy:** `fail-loud` is default. After cleanup + path rewriting, every outbound markdown link in release output is checked against the release output tree. Broken links HALT the build with tabular violation report. `--strict-broken-links=warn` flag (off by default) lets emergency builds proceed for triage.

**Code-fence boundary handling:** Parser model is CommonMark + GFM extensions. Fenced code blocks, indented code blocks, and inline-code spans protect their contents from marker scanning. Markers inside any of the three protected forms are LITERAL CONTENT, not strip directives.

### Cross-reference forms recognized by the broken-link checker

| Form | Example | Checked? |
|---|---|---|
| Explicit markdown link | `[text](path/to/file.md)` | ✓ Against release output tree |
| Anchor-only link (same file) | `[text](#section)` | ✓ Against section IDs (post-cleanup) |
| Cross-file anchor | `[text](other.md#section)` | ✓ Both file existence AND section ID |
| Wikilink | `[[<uid>]]` | Checked IFF `cleanup_rules.rewrite_uid_refs: true` |
| Bare reference-link | `[<uid>]` | NOT checked; ships literally |
| External URL | `[text](https://...)` | NOT checked at v1.1; v1.5+ optional `--check-external` |

---

## Article Subtype + Editorial State Machine (v1.4 NEW)

The v1.4 amendment introduces an `article` subtype of the `document` type. The subtype carries its own editorial state machine on the SOURCE article entry (`vault/files/<article-uid>.md`), distinct from the ship-artifact wrapper's own lifecycle.

### Article entry shape

```yaml
type: document
subtype: article                  # NEW v1.4 subtype value
status: draft                     # editorial state — 4-state enum
extraction_scope: argo-reference  # unchanged; substrate-class boundary
title: "<readable article title>"
# ... standard document fields ...
```

### 4-state editorial enum

Article entries carry a 4-state editorial state machine on the existing `status:` field — **extending** ship-artifact capsule's 3-state pattern with one additional intermediate state (`reviewed`) for an editorial review pass:

| State | Semantic |
|---|---|
| `draft` | Author/agent working; not yet review-ready |
| `reviewed` | Review pass complete (R1 director or human review); editorially-ready pending lock |
| `locked` | Editorial-ready; immutable except for substantive supersession |
| `archived` | Superseded or retracted; honest-record preserved per [OP-13 Preservation Discipline](../../.tropo-studio/operating-principles.md) |

**Valid transitions:**

- `draft → reviewed` — triggered by author when ready for review pass
- `draft → locked` — fast-path NOT permitted for articles; review pass is required (substantive content)
- `reviewed → draft` — revision required
- `reviewed → locked` — triggered by author + reviewer agreement OR Mike-lock for principal-owned articles
- `locked → archived` — requires supersession (via `superseded_by:`) OR retraction note explaining why
- `archived → *` — NOT ALLOWED (honest-record invariant; preservation discipline OP-13)

**Validator rule:** an article entry MUST progress through states sequentially; skipping the `reviewed` state on the path to `locked` is a substrate-honesty break. Check 25 enforces.

### Wrapper-article composition rule

When a ship-artifact wrapper's `canonical_source:` points at an article entry (`subtype: article`), the wrapper inherits the article's editorial state implicitly:

- **Wrapper does NOT extract until article `status: locked`.** Build pre-flight inspects each wrapper-with-article-source; if article is `draft` or `reviewed`, the wrapper is skipped for that build iteration + a WARN posts to the build log naming the unlocked article. **The wrapper's own `status: locked` is independently required per capsule v1.3 §State Machine (wrapper lifecycle unchanged at v1.4); Rule 13 + Check 26 add article-locked as a SECOND gate on extraction, not a substitute for wrapper-locked. Both gates must clear for extraction to fire.**
- **Wrapper at `target:` declaring any published target requires source article `status: locked`.** Wrappers with web in target but article not yet locked produce a build-time FAIL at v1.5 (WARN at v1.4 — migration window).
- **Article `status: locked → archived` cascades to wrapper publication retraction.** When an article archives (substantive correction needed; retraction note added), every wrapper with `publication_state.<target>: live` for that article gets a pipeline-fired retract-act on the next build. The article's archival IS the retract trigger; no separate wrapper edit required.

This rule preserves the existing ship-artifact lifecycle (wrapper's own `status:` enum unchanged) while binding wrapper extraction behavior to article editorial state. The wrapper still passes its own validation independently; what gates extraction is the COMPOSITION (wrapper + article both in correct state).

### Editorial state ≠ publication state ≠ extraction-target membership

Three orthogonal dimensions, each declared on different substrate:

| Dimension | Field | Declared on | Author writes? |
|---|---|---|---|
| Editorial state | `status:` (4-state enum) | source article entry | YES |
| Target-declared membership | `target:` array | ship-artifact wrapper | YES |
| Publication state | `publication_state:` map | ship-artifact wrapper | NO (pipeline writes) |

Publish-act = all three coherent: article `status: locked` (editorially ready) AND wrapper `target:` includes the target (author declared intent) AND pipeline writes `publication_state.<target>: live` at sub-gate-3 completion (actually published).

### Migration

The v1.4 article-backfill migration approach (identify → assess editorial state → backfill `subtype: article`) is preserved in the [history companion (437e8944)](ship-artifact.history.md) §v1.69 additions. Check 25's WARN window covers un-migrated articles.

---

## Publish-Act Semantics (v1.4 NEW)

The publish-act is the **pipeline event** that transitions an article from "editorially locked + targeted for web" to "actually live on web." It is NOT a single author-edit on any frontmatter field; it is a multi-stage pipeline-driven event that culminates in a pipeline write to `publication_state.<target>: live` after post-deploy verification clean.

### Definition

**Publish-act = (article `status: locked`) ∧ (wrapper exists with `target:` including the target) ∧ (pipeline executes publish-act sub-gates 1-3 clean for the target).**

The first two conditions are author-controlled and substrate-declared. The third is pipeline-controlled; the pipeline records its outcome by writing `publication_state.<target>: live` (or leaving the key absent on failure).

### Operational flow

```
1. Author drafts article → article entry created with:
     type: document, subtype: article, status: draft, extraction_scope: argo-reference
2. Author + reviewer iterate → article status: draft → reviewed
3. Lock event → article status: reviewed → locked. Editorial freeze.
4. Wrapper authored (or amended to add 'web' to target:) → ship-artifact wrapper points at article;
     target: declares publication intent.
5. build-web-content.py runs (the thin-orchestrator at `.tropo/scripts/build-web-content.py`; publish-act + sync hooks per design-spec [6a8d3f17](../../vault/files/6a8d3f17.md) §6):
     a. Walks ship-artifact graph at manifest_root_uid.web
     b. For each wrapper with target including 'web' AND source article status: locked:
        - Extracts markdown body to external-work/web/articles/<article-uid>/index.md
        - Applies per-target cleanup_rules (rewrite_uid_refs + uid_rewrite_template)
        - Preserves assets/ subfolder untouched (non-destructive invariant — see §External-Work)
        - Logs to _sync-state.jsonl
     c. Validates cross-references (Surface 4 pre-publish gate per design-spec 6a8d3f17 §3)
6. Step 3 review pass (Design + Format) → Mike + Metis review staged content;
     graphics dropped into assets/ if needed.
7. Publish push:
     a. rsync external-work/web/ → tropo-ai/website-content working copy
     b. Structured commit message per publish-act
     c. git push → Vercel auto-deploys
8. Pipeline sub-gate-3 verification (post-deploy smoke + production-walk per release-plan b8f5d293). **Sub-gates 1 + 2 are pipeline-internal stages defined at design-spec [6a8d3f17](../../vault/files/6a8d3f17.md) §Surface 2** — sub-gate-1 = pre-publish extraction-clean (article locked + wrapper target declared + cross-reference validation pass); sub-gate-2 = staging-clean (rsync to working copy + git commit + push without conflict); sub-gate-3 = post-deploy verification (this step; smoke + production-walk; publication_state pipeline-write fires on clean). Sub-gates 1+2 run as part of build-web-content.py orchestration steps 1-7 above; sub-gate-3 is the terminal verification that licenses the publication_state.<target>: live write.
     a. If clean: pipeline writes publication_state.web: live on the wrapper
     b. If failed: pipeline writes nothing; publication_state remains absent for web key;
                  ops.md gets a BULLETIN naming the verification failure
```

### Multi-target publish

When a wrapper declares `target: [web, release]`, pipeline iterates per target. Each iteration's publish-act is independent:

```yaml
# Wrapper after web publish-act sub-gate-3 clean:
target: [web, release]
publication_state:
  web: live

# After release publish-act sub-gate-3 clean (different iteration):
target: [web, release]
publication_state:
  web: live
  release: live
```

Both updates are atomic per the per-target iteration semantics defined in §Target Semantics. The wrapper's frontmatter accumulates per-target outcomes; no cross-target coupling.

### Retraction

**Retract-act** is the inverse pipeline event: removes content from a target's working copy and updates wrapper substrate to `publication_state.<target>: retracted`.

Operational flow:

```
1. Editorial-fault retraction (substantive correction needed):
   a. Author flips article status: locked → archived (with retraction_note in body explaining why)
   b. Next build-web-content.py run detects archived article + still-live wrapper publication_state
   c. Pipeline executes retract-act:
      - Removes article from external-work/web/articles/<article-uid>/
      - Sync removes article from tropo-ai/website-content working copy
      - git commit + push → Vercel auto-deploy
      - Production URL returns 410 Gone (preferred over 404 — signals deliberate retraction)
   d. Pipeline writes publication_state.web: live → retracted on the wrapper

2. Target-removal retraction (article stays published elsewhere; only this target retracts):
   a. Author amends wrapper: removes target from target: array (or flips publication_state intent)
   b. Wrapper is now target: [<other targets>] — web absent
   c. Next build sees wrapper no longer targets web; pipeline retracts from web target;
        publication_state.web flips live → retracted
   d. Article stays status: locked (still editorially ready); other targets continue live
```

**Multi-target retraction:** publication_state captures per-target outcome; retracting from one target does not affect others. A wrapper at `target: [web]` with `publication_state: {web: retracted, release: live}` is valid — web was retracted; release still live.

**Retracted URL behavior:** v1.4 lean = HTTP 410 Gone (signals "deliberately removed"; better than 404's "never existed" for retracted content). Implementation detail at Cycle B engineering scope; this spec names the lean. Future-cycle option: visible-with-correction-notice (URL still resolves; banner explains retraction) — deferred.

### Re-publish (edits to a locked article)

Existing capsule discipline preserves author-mutable invariant for in-locked-state edits to article body — re-publishing an edited locked article does NOT require a state transition. Mechanism:

1. Author updates the article body (locked-state edit, per existing discipline)
2. Wrapper extraction fires on next build → fresh content lands at target destination
3. Pipeline re-confirms `publication_state.<target>: live` (idempotent write)
4. No state machine transition required

For substantive content changes that materially shift the article's claim, the discipline is to archive the locked version (with retraction_note) + author a new article with `supersedes:` pointing at the old. The supersession path is the audit trail for substantive change; in-place edits to locked articles are reserved for typo/formatting/citation fixes.

### Cross-article reference validation (pre-publish gate)

Before publish-act fires, build-web-content.py validates that all internal references in the article-being-published resolve to either:

- (a) already-published web entries (publication_state.web: live elsewhere in the manifest), OR
- (b) entries about to publish in the same build run

If references point at unpublished entries, the build surfaces a WARN ("Article A links to Article B; B not yet on web; 404 window") + author resolves before push. This closes the "Article links to not-yet-published Article" edge surfaced by d.fresh-reader's R1 stranger-engineer walk on the source design-spec.

### Out-of-scope at v1.4 (future-cycle)

Named explicitly so the boundary is honest:

- **Multi-author atomic-batch publish mode** — v2+ if/when needed; v1 single-author per-article suffices.
- **Re-publish cascade automation** — author-driven opt-in only at v1; if Article A updates and Article B quotes A, B's already-published version stays as-is unless author flips B's wrapper target.
- **Retract-act trigger UX details** — Cycle B engineering scope. v1 = author signals retraction by archiving article or amending wrapper target; pipeline picks up at next build.
- **Visible-with-correction-notice retraction mode** — v1 = 410 Gone removal; correction-notice mode is a future product call.

---

## External-Work Staging Architecture (v1.4 NEW)

The extraction-and-publish pipeline introduces a per-target editorial staging surface at `argo-os/external-work/`. The directory is the boundary between argo's canonical markdown substrate and the target-specific binary + formatting that ships to each publication destination.

### Directory shape

```
argo-os/
├── vault/                              # Canonical: markdown + jsonl ONLY
├── external-work/                      # Staging — gitignored at Studio level
│   ├── web/                            # Web-target staging
│   │   ├── articles/<article-uid>/     # Per-article folder
│   │   │   ├── index.md                # Extracted + cleaned markdown (engine writes)
│   │   │   ├── frontmatter.yml         # Optional: extracted frontmatter for ArticleLayout
│   │   │   └── assets/                 # Manual drops (graphics, layout assets)
│   │   │       ├── hero.png
│   │   │       └── inline-figure-1.png
│   │   ├── pages/                      # Future: static page extractions (about, etc.)
│   │   └── _sync-state.jsonl           # Sync log: last-sync timestamp per article; what landed; what changed
│   ├── mindbridge/                     # Future target (post-Cycle-C)
│   └── ...
```

Same article in vault can ship to web + future MindBridge — each target's `external-work/<target>/<article-uid>/` holds its own target-specific binaries + formatting. Vault stays text-canonical; staging carries target-specific shape.

### Sync mechanism

`build-web-content.py` orchestrates the extract-and-publish flow:

```
1. Walk ship-artifact graph at manifest_root_uid.web (4a99638d) via lib/ship_extract/ engine
2. Per wrapper with target including 'web' AND canonical_source article status: locked:
   a. Extract markdown body to external-work/web/articles/<article-uid>/index.md
   b. Apply per-target cleanup_rules (rewrite_uid_refs: true + uid_rewrite_template: /kb/<uid>)
   c. Preserve assets/ subfolder untouched (non-destructive invariant)
   d. Log to _sync-state.jsonl
3. Validate cross-references (pre-publish gate per §Publish-Act Semantics)
4. rsync external-work/web/ → <repo-path>/tropo-ai/website-content/
5. Commit with structured message (which articles, by whom, when)
6. git push → Vercel auto-deploys
7. Post-deploy sub-gate-3 verification → pipeline writes publication_state.web: live on success
```

### Non-destructive invariants

The staging surface preserves manually-composed content across re-extracts:

1. **Re-extracts of an article body do NOT touch `assets/` subfolder.** Graphics composed by hand at step 3 (Design + Format) persist across re-extracts. The extraction engine writes ONLY to `index.md` + `frontmatter.yml`; the `assets/` subfolder is owned by step 3.
2. **Sync removes entries that no longer target web** (retraction case) but only those entries; sync does NOT wipe-and-rewrite the entire target working copy.
3. **Manual edits to `external-work/web/<article-uid>/index.md`** are preserved at next extract iff the body hasn't materially changed in vault (substrate diff check). If vault body changed, manual external-work edits are overwritten + WARN posts naming the clobber.

### Gitignore discipline

`argo-os/external-work/` is gitignored at the Studio level (top-level `.gitignore`). The Studio git tracks vault canonical + .tropo/ + .tropo-studio/ + tracked agent files; `external-work/` is editorial workspace + per-target staging, NOT canonical substrate. Check 29 verifies the gitignore entry is in place; surfaces drift if external-work/ is mistakenly committed.

**Two valid gitignore shapes (Check 29 accepts either):** (1) **specific exclusion** — a literal `external-work/` or `argo-os/external-work/` line in `.gitignore`; (2) **parent-folder coverage** — a parent directory wholesale-ignored at a higher-level `.gitignore` (e.g., the Studio lives inside the tropo-ai platform repo, where `/argo-os/` is wholesale gitignored at the platform-repo root per Mike-A72 directive 2026-05-18 — the staging surface is covered transitively). **Downstream Studio caveat:** standalone Studio installs (where the Studio IS its own git repo without parent-folder wholesale-ignore at a containing repo) MUST declare a specific `external-work/` line — parent coverage doesn't apply.

**Why staging is gitignored:** The target working copy (e.g., `tropo-ai/website-content`) is the canonical destination; that repo has its own git history. Staging is the intermediate workspace where extraction output meets manually-composed assets before being synced to the destination repo. Tracking staging in argo's git would create three-way drift (argo vault canonical + argo staging copy + destination repo) — exactly the failure mode the v1.0 ship-artifact capsule was designed to prevent.

### Cross-target separation

Each target's external-work subfolder is isolated. The same article ID in vault produces independent staging artifacts per target — web's `external-work/web/articles/<uid>/` is completely disjoint from a future MindBridge target's `external-work/mindbridge/articles/<uid>/`. Targets do not share staging; cross-target coupling is rejected by construction.

This composes with capsule v1.3's per-target iteration semantics: vault declares CONTENT once; staging holds per-target FORMATTING; each target's working copy is the canonical destination.

---

## L1/L2 Composition Pattern (v1.4 NEW)

Tropo's substrate inhabits two architectural layers:

- **L1 (markdown-native)** — Agents write markdown. Scripts process markdown. Templates wrap markdown. Pandoc converts. MDX renders. The substrate Tropo-OS is built on.
- **L2 (real-code apps in `tropo-ai.app/`)** — Sophisticated capabilities requiring real engineering: image generation, programmatic Word/PowerPoint assembly, brand-system formatters, RAG pipelines, complex format converters.

### Composition at step 3 (Design + Format)

The extraction-and-publish pipeline's step 3 is where L1 and L2 compose. For web v1, step 3 is entirely L1 (Mike composes graphics manually). For future targets + future capabilities, step 3 evolves to invoke L2 apps programmatically.

```
Step 3 (Design + Format) per target:
  ├── L1 path: agent edits markdown in vault; templates + MDX render at extraction
  └── L2 path: L1 agent invokes L2 app API; L2 produces binary (image, formatted doc);
              output lands in external-work/<target>/<entry-uid>/assets/;
              L1 markdown body references the asset; render pipeline composes both at extraction
```

### Design constraint

The pipeline MUST allow L1↔L2 composition WITHOUT locking out future L2 capabilities. The step-3 surface accepts binary outputs from anywhere:

- Manual file drop today (Mike composes in Figma, drops into `assets/`)
- L2 app output tomorrow (image-gen app writes to `assets/`)

The pipeline doesn't care HOW the binary got into `external-work/<target>/<entry-uid>/assets/`, only that it's there at extraction time. This decouples publish-act from capability provenance — same pipeline serves manual + programmatic step 3 indistinguishably.

### v1 scope

No L2 capabilities are built at v1.4. Step 3 happens manually for web v1 — Mike composes graphics by hand; drops them into `external-work/web/articles/<uid>/assets/`. MDX component library at step 3 is L1.

As L2 capabilities ship in later cycles (image-gen app, MindBridge brand-system formatter, etc.), step 3 evolves to invoke them programmatically. The pipeline composes both layers without any capsule-level change required — the staging surface is the composition point.

---

## 3. State Machine

```
draft → reviewed → locked → archived (supersession or retirement)
   ↑________↓ revision during draft or reviewed
   └── fast-path → locked (trivial mirror entries; document in ## Notes)
```

**Required starting state:** every new ship-artifact entry MUST be authored at `status: draft`.

**Strict base status enum:** `status:` ∈ {draft, active, reviewed, locked, archived} (the wrapper base lifecycle; the `subtype: article` editorial enum at §Article Subtype is a distinct subtype-scoped variant).

| Status | Meaning |
|---|---|
| `draft` | Entry being authored. Manifest not yet validated. |
| `reviewed` | Entry has been reviewed (Argus + Mike for human review; OR orphan/zombie scanner for mechanical review). |
| `locked` | Entry committed. build-release.py honors as authoritative. |
| `archived` | Historical. Either superseded by successor (same canonical_source, new design) OR retired from ship. |

**Valid transitions:**

- `draft → draft` — revision during authoring
- `draft → reviewed` — orphan/zombie scanner PASS + human review acknowledgement
- `draft → locked` — **fast-path** for trivial mirror-shape entries (e.g., direct-copy mirroring canonical_source = output_path with no cleanup_rules). Document rationale in `## Notes`. For non-trivial entries, run full path.
- `reviewed → draft` — revision required
- `reviewed → locked` — entry committed; `locked_by:` + `locked_at:` set
- `locked → archived (superseded)` — successor entry locks; bidirectional `supersedes:` / `superseded_by:` set atomically (Rule 9)
- `locked → archived (retired)` — artifact removed from ship without successor; `archived_by:` + `archived_at:` set; `## Notes` documents reason (Rule 11)
- `any → archived (retired)` — direct retirement; same audit requirements (Rule 11)

**Article subtype state machine** — see §Article Subtype + Editorial State Machine above. Articles use a 4-state enum (draft → reviewed → locked → archived) with the `reviewed` state REQUIRED on the path to `locked` (no fast-path); wrappers pointing at article entries inherit editorial-lock gating per the wrapper-article composition rule.

---

## 4. Validation Rules

### Governance Rules (13)

1. **Every ship-artifact MUST be `member_of:` the manifest-root project for each target it declares.** Validator reads `manifest_root_uid:` from capsule frontmatter (the canonical lookup — MUST NOT hard-code in source, MUST NOT title-match). `manifest_root_uid:` is a per-target MAP (`release: b2e7d4a9` Tropo Release Structure; `web: 4a99638d` Tropo Website Content Structure). Dual-root graph governance: entries declaring `target: [release]` (or implicit `[release]` via absent field) must member_of: `b2e7d4a9`; entries declaring `target: [web]` must member_of: `4a99638d`; entries declaring `target: [release, web]` must member_of: BOTH roots.
2. **`canonical_source:` MUST resolve.** Validator confirms path exists in `argo-os/` at lock time. EXCEPTIONS: (1) `source_mode: skip` — resolution informational. (2) `source_mode: structure-only` — resolution informational; entry semantic is "create empty directory."
3. **`output_path:` defaults to mirror canonical_source.** If absent, build emits to `<canonical_source minus argo-os/ prefix>` in recipient vault.
4. **`source_mode:` is the build-decision discriminator.** build-release.py reads `source_mode:` to decide ship behavior.
5. **`recursive-ship-all` + per-file overrides compose with explicit shapes** per §Source Modes "Override-child shapes" table. Only enumerated shapes are legal; all others REJECTED by Check 5 + Check 19.
6. **Marker syntax is locked at HTML comments.** Custom marker tokens, YAML-fenced sections, or alternative conventions are NOT permitted. New marker pair names require a v1.x amendment + arch-spec update.
7. **Broken-link policy is fail-loud.** Build halts on any broken outbound markdown link in release output. `--strict-broken-links=warn` flag for emergency triage. Cross-reference forms enumerated in §Cleanup Rules.
8. **Validator ownership is L2 tooling.** Orphan/zombie scanner + manifest health check live as standalone CLI script + step in build-release.py. Sa.* wrapper deferred to v1.5+.
9. **Supersession is atomic-commit.** When a ship-artifact is reauthored under a new design (recipient-output meaning changes — new `output_path:` AND/OR new `## Purpose` AND/OR new `cleanup_rules:`), transition is one commit publishing successor at `status: locked`, flipping predecessor to `archived`, setting bidirectional pair. Path-only changes (argo rename without semantic change) do NOT require supersession.
10. **The graph is acyclic per-target subgraph.** A ship-artifact's `parent:` chain MUST terminate at the correct manifest_root_uid for each target the entry declares, without revisiting any node within the per-target subgraph. **Cross-target parent/child entries are explicitly illegal** (e.g., a `target: [web]` entry cannot have a `target: [release]` parent) — preserves per-target graph integrity. Dual-target entries: parent chain validates per-iteration; chain for release-iteration terminates at `b2e7d4a9`, chain for web-iteration terminates at `4a99638d`.
11. **(v1.1) Direct retirement requires audit.** Any `state: archived` transition NOT supersession-driven MUST: (a) set `archived_by:` + `archived_at:` frontmatter; (b) include `## Notes` body section documenting retirement reason. Supersession path (Rule 9) carries its own audit via bidirectional pair.
12. **(v1.1) Atomic-commit for cross-referenced new entries.** New ship-artifact entries that cross-reference each other (parent + its `children:` UIDs newly authored in same session) are authored as atomic commit. Partial commits leave manifest broken; validation fails. For mass-authoring sprints, `draft-ship-manifest.py` emits all entries to workspace + commits as one atomic batch.
13. **(v1.4) Wrapper-article editorial-lock composition.** When a ship-artifact wrapper's `canonical_source:` points at an article entry (`subtype: article`), the wrapper inherits the article's editorial state implicitly: (a) wrapper does NOT extract until article `status: locked`; (b) wrapper at `target:` declaring any published target requires source article `status: locked` (Check 26 enforces; WARN at v1.4 / ERROR at v1.5); (c) article `status: locked → archived` cascades to pipeline-fired retract-act on any wrapper with `publication_state.<target>: live` for the archived article. See §Article Subtype + Editorial State Machine + §Publish-Act Semantics.

### Validation Checks (29, version-gated where noted)

Each labeled **[enforced]** (mechanically checked by validator + build-release.py) or **[honor-system]** (reader-verified; mechanically enforced later).

1. **[enforced]** `type: ship-artifact`
2. **[enforced]** `kind:` ∈ {`folder`, `file`}
3. **[enforced]** `canonical_source:` non-empty string
4. **[enforced]** `canonical_source:` resolves in `argo-os/`. EXCEPTIONS: `source_mode: skip` (informational); `source_mode: structure-only` (informational; recipient-scaffolding folders may have no argo counterpart).
5. **[enforced]** `source_mode:` ∈ {recursive-ship-all, recursive-ship-tagged, explicit-children, structure-only, skip, direct-copy}. Folder-only modes rejected on `kind: file`; `direct-copy` rejected on `kind: folder`.
6. **[enforced]** `extraction_scope:` ∈ {ship, argo-reference, argo-private}
7. **[enforced]** `parent:` either resolves to another ship-artifact OR is `null` for root
8. **[enforced]** If `kind: folder` AND `source_mode: explicit-children`: `children:` non-empty; every UID resolves; every child's `parent:` points back
9. **[enforced]** **Effective output_path uniqueness:** after resolving recursive-default output paths AND applying per-file overrides, every effective output_path is unique across release output. Two files arriving at same recipient path = collision = build halts.
10. **[enforced]** If `cleanup_rules:` present, valid object with recognized keys (`strip_markers`, `broken_link_policy`, `rewrite_uid_refs`, `uid_rewrite_template`).
11. **[enforced]** New entries start at `status: draft`. Direct creation at `reviewed`/`locked` rejected. Fast-path `draft → locked` requires authoring at draft first; transition documented in `## Notes`.
12. **[enforced]** If `status: locked`: `locked_by:` + `locked_at:` present.
13. **[enforced]** Body contains both REQUIRED sections (`## Purpose`, `## Description`).
14. **[enforced — mechanical enforcement awaits Phase E validator; honor-system in practice]** **(v1.3 target-keyed)** `member_of:` includes the manifest_root_uid for EACH target the entry declares. Dual-target entries must `member_of:` BOTH `manifest_root_uid.release` AND `manifest_root_uid.web`. Absent `target:` field defaults to implicit `[release]` for this check.
15. **[enforced]** `supersedes:` / `superseded_by:` (if present) form bidirectional pairs and both resolve.
16. **[enforced]** Graph integrity: `parent:` chain terminates at root without cycles (Rule 10).
17. **[honor-system]** `description:` and `## Purpose` body substantive, not boilerplate (validator catches empty/placeholder; semantic quality reader-verified).
18. **[honor-system]** Cleanup notes (where present) accurately describe strip behavior.
19. **[enforced]** **(v1.1)** Composition path-tree containment: when entry's `parent:` is a ship-artifact with `source_mode: recursive-ship-all`, this entry's `canonical_source:` MUST be a path under parent's tree.
20. **[enforced]** **(v1.1)** Override-child shape legality: when entry's `parent:` has `source_mode: recursive-ship-all`, this entry's `source_mode:` MUST be one of the legal override shapes (`direct-copy` or `skip`). Other source_modes under `recursive-ship-all` parent = REJECTED.
21. **[enforced]** **(v1.1)** `skip` applicability: top-level `skip` REJECTED; `skip` under `explicit-children` REJECTED; `skip` under `structure-only` REJECTED. Legal: `skip` under `recursive-ship-all` OR `recursive-ship-tagged`.
22. **[enforced]** **(v1.1)** Direct-retirement audit (Rule 11): if `state: archived` AND no `superseded_by:` set, then `archived_by:` + `archived_at:` MUST be present.
23. **[honor-system]** `## Notes` body section accurately documents reasons for `skip` source_mode AND direct retirement (Rule 11 audit).
24. **[enforced]** **(v1.3)** **`target:` field shape + enum.** If `target:` field present: MUST be a YAML array (scalar values REJECTED); every element MUST be `release` or `web`; field absence is permitted (implicit `[release]`). ERROR at v1.3 directly (no WARN/ratchet phase — enum-constrained from introduction; no pre-existing values to migrate).
25. **[enforced]** **(v1.4 NEW)** **`check_article_state_machine_invariants`.** For each entry with `subtype: article`: **v1.4 enforces** — confirm `status:` ∈ {draft, reviewed, locked, archived}; confirm `subtype:article` entries declare a `status:` field; confirm if `archived` then any of `superseded_by:` frontmatter OR `retraction_note:` frontmatter OR a body `## Retraction` / `## Retraction Note` section header is present (any of the three signals satisfies the preservation-discipline rule per OP-13). **v1.5 ratchet adds** — sequential state-transition history check (skipping `reviewed` on path to `locked` REJECTED via git-log inspection of the entry's status-field commit history). Severity: **WARN at v1.4 / ERROR ratchet at v1.5** — one-cycle migration window for existing articles needing editorial-state backfill.
26. **[enforced]** **(v1.4 NEW)** **`check_wrapper_article_editorial_lock`.** For each ship-artifact wrapper with `canonical_source:` pointing at a `subtype: article` entry: confirm the article exists; if wrapper's `target:` includes any published target AND article's `status: != locked`, fail with explicit message ("wrapper targets <target> but article is not editorially locked; either lock article or remove <target> from wrapper target"). **WARN at v1.4 / ERROR at v1.5.**
27. **[enforced]** **(v1.4 NEW)** **`check_publication_state_pipeline_write_only`.** **v1.4 enforces** — field-shape audit on the `publication_state:` map: top-level shape is a block-form YAML map (scalar/array REJECTED); keys are valid target slugs (subset of `{release, web}`); values are in `{live, retracted}`; empty map REJECTED (omit field for "never published" semantic). **v1.5 ratchet adds** — git-blame hand-edit-drift detection on the `publication_state:` field's commit history (pipeline commits use a sentinel author; author commits use human/agent identity; mismatch flags substrate-discipline drift). The v1.5 activation depends on the pipeline-write sentinel author convention being established at Stream B engineering (Cycle B / v1.48.0); at v1.4 ship the pipeline-write convention is not yet active. Severity: **WARN at v1.4 / ERROR ratchet at v1.5.**
28. **[enforced]** **(v1.4 NEW)** **`check_publication_state_target_coherence`.** Verify `publication_state:` keys are a subset of `target:` array values (absent `target:` field treated as implicit `[release]` per v1.3 backward-compat default). Cannot be `live` on a target the wrapper doesn't declare. **WARN at v1.4** (no ratchet planned — coherence violations should not occur if pipeline is well-behaved; WARN as audit signal).
29. **[enforced]** **(v1.4 NEW)** **`check_external_work_gitignore`.** Verify `argo-os/external-work/` is gitignored at Studio root OR via parent-folder coverage (e.g., if a parent directory like `/argo-os/` is wholesale gitignored at the platform-repo level, the staging surface is covered transitively). Check accepts either a specific `external-work/` line OR parent-folder coverage. **Downstream Studio caveat:** standalone Studio installs (where the Studio IS its own git repo without a parent-folder wholesale-ignore) need an explicit `external-work/` line in their `.gitignore`. If neither specific nor parent coverage is found, surface as substrate-discipline drift. **WARN at v1.4** (audit signal; failure to gitignore creates the three-way drift failure mode this capsule was designed to prevent).

Core checks inherited: UID uniqueness + immutability, type immutability, owner / created / modified invariants.

### Validation Checks — Target-Coherence Pass (v1.3)

Beyond Check 24 (target shape) and Check 14 (member_of target-keyed), per-check target-coherence audit across the existing 23 checks:

| Check | Target-coherence behavior |
|---|---|
| 1-3, 5, 8, 10, 11, 12, 13, 15-18, 20-23 | Universal regardless of target — no per-target divergence |
| Check 4 (canonical_source resolves) | Universal — argo-os/ is single source-of-truth across all targets |
| Check 6 (extraction_scope enum) | Universal enum values; convention noted: typical web-target entries carry `extraction_scope: argo-reference` (rendered to web; not OS-release-shippable) |
| Check 7 (parent resolves) | **Per-target chain termination** — entry's `parent:` chain must terminate at the correct manifest_root_uid for each target the entry declares; cross-target parent/child illegal (per Rule 10) |
| Check 9 (effective output_path uniqueness) | **Per-target namespace** — release manifest output_paths unique among release entries; web manifest output_paths unique among web entries; cross-target collisions ALLOWED (different output trees) |
| Check 14 (member_of includes manifest_root_uid) | **Target-keyed** — entry's `member_of:` must include the manifest_root_uid for EACH target the entry declares (per Rule 1 v1.3 amendment) |
| Check 19 (composition path-tree containment) | **Per-target** — if parent is `recursive-ship-all`, containment evaluates per parent's target context; cross-target parent/child illegal (Rule 10) |

### v1.4 ratchet pattern

Checks 25-27 ratchet **WARN → ERROR over one cycle** (v1.4 ship → v1.5 ship) to give existing articles + existing wrappers a migration window for editorial-state backfill + initial pipeline-write semantics. Checks 28-29 stay WARN indefinitely — coherence + gitignore audit signals; not enum-class violations needing ratchet enforcement.

Check 24 (added v1.3) was immediate-ERROR (no migration window) because legacy entries had a clean default (absent target = `[release]`). Checks 25-27 amend article state semantics where existing articles may need backfill — migration-friendly ratchet matches the substrate-class context.

---

## 5. Composes-With

- **[core.capsule (ee814120)](core.capsule.md)** — inherited floor (UID immutability, type immutability, owner/created/modified invariants).
- **[capsule-definition meta-capsule (222873b9)](../../vault/files/222873b9.md)** — governs this capsule.
- **[document.capsule (d0c00001)](document.capsule.md)** — pattern exemplar per v3 Decision 3. ship-artifact patterns on document with additional discipline: graph-shape enforcement (parent + children + acyclicity), path resolution at lock time, source_mode enum + behavior contracts, cleanup_rules + marker handling, build-time integration. **(v1.4)** Article subtype (`subtype: article`) extends document.capsule; ship-artifact wrappers pointing at article entries inherit editorial-state gating per Rule 13 + Check 26.
- **[build.capsule (b3d7e5a1)](build.capsule.md)** — sibling at build/release infrastructure layer. Builds package versioned software; ship-artifacts declare what goes INTO a build's output.
- **[release.capsule (b19e8d43)](release.capsule.md)** — sibling at build/release infrastructure layer. Releases record what shipped; ship-artifacts declare what's shippable.
- **[release-plan.capsule (a3f1e7b2)](release-plan.capsule.md)** — coordination precedent. A release-plan coordinates a release; ship-artifacts coordinate the manifest within that release's build.
- **[playbook.capsule (e7b3c509)](playbook.capsule.md)** — pattern precedent for §Studio + Relations Header convention.
- **[project-plan.capsule (f7b9c4a2)](project-plan.capsule.md)** — governs [Stream 2 D2.1 project-plan (4e5a2011)](../../vault/files/4e5a2011.md), the project-plan delivering this capsule's v1.0-v1.1.
- **[pipeline.capsule (e4c8a6b2)](pipeline.capsule.md)** + **[pipeline-run.capsule](pipeline-run.capsule.md)** — **(v1.4 NEW)** the pipeline substrate that executes publish-act + retract-act. Publish-act is a pipeline event; pipeline-run.capsule records what fired; ship-artifact.capsule v1.4 defines what gets written to wrapper substrate at sub-gate-3 completion.
- **[Build-Release Pipeline arch-spec (747c33c9)](../../vault/files/747c33c9.md)** — validator + build implementation spec; capsule version-drift policy per §3.4.
- **[Tropo Release Structure project (b2e7d4a9)](../../vault/files/b2e7d4a9.md)** — the manifest-root project for `target: [release]` entries (keyed under `manifest_root_uid.release:`).
- **[Tropo Website Content Structure project (4a99638d)](../../vault/files/4a99638d.md)** — the manifest-root project for `target: [web]` entries (keyed under `manifest_root_uid.web:`).
- **[Tropo Extraction-and-Publish Pipeline brief (c5a7e391)](../../vault/files/c5a7e391.md)** — the universal extraction-and-publish pattern this capsule's v1.4 sections substrate-support.
- **[Web v1 Release Plan (b8f5d293)](../../vault/files/b8f5d293.md)** — Cycle A/B/C sequencer for the web target.
- **[v1.46.0 Cycle A Design-Spec (6a8d3f17)](../../vault/files/6a8d3f17.md)** — direct source for the v1.3 → v1.4 amendment. *(Cycle provenance, incl. the v1.47→v1.48 renumbering story, in the [history companion (437e8944)](ship-artifact.history.md).)*

### History

The v1.0/v1.1/v1.1.1-v1.1.4 amendment-block opener prose, the §Conscious Trade-offs section (5 entries), the §Known Enforcement Gaps table, the §Studio — Shop Signage human-facing quick-ref, the Relationship-to-Other-Capsules narrative, the Inheritance section, the v1.2 body-refactor entry, the v1.3 multi-target extraction migration entry, and the full changelog are preserved in the companion [ship-artifact.history.md (437e8944)](ship-artifact.history.md) governed by `capsule-history.capsule` (5ec083a3). The v1.4 amendment narrative lands there alongside the v1.3 migration entry.

---

*ship-artifact capsule definition | DRAFT v1.4 (status: draft pending cycle close lock) | UID `eeb59ddf` | full version history at [ship-artifact.history.md (437e8944)](ship-artifact.history.md)*
*"One declaration per shippable artifact. Canonical source in argo. Default doesn't-ship. The graph is the manifest. Editorial state on the source; target membership on the wrapper; publication state pipeline-written at the act."*
