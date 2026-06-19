---
uid: 7e3a91c8
type: capsule-definition
title: "publish.pipeline.capsule v1.3 — Typed Primitive for Lightweight Extract-and-Publish Pipelines"
version: "1.3.0"
history_companion: "78c51bdf"
history_split_2026_06_11_a110: "v1.69 S3 token-performance SPLIT by Argus A110 (NO CONTRACT CHANGE). Was 59,797 bytes vs the 51,200 write-time budget. Extracted to the publish.pipeline.history companion (78c51bdf): v1_1 amendment note, §12 Provenance, §13 Implementation Status (frozen v1.49.0.2 snapshot), the stranded mid-file v1.2 footer (defect: §17/§18 were appended after it at v1.3, leaving a duplicate stale footer mid-document), §17.5 design history. v1.3 + v1.2 notes stay per the current+previous fold rule."
v1_3_amendment_note: "v1.2 → v1.3 amendment 2026-05-24 by Metis G60 (cross-lane substrate-class work per Mike-G60 directive 'anything you gave to Argus you can do? He has more of a backlog'; capsule amendment is bounded; content authored in companion briefs; reduces A81 queue without architectural impact). Three new sections absorbing G60 design lock briefs same-session: (1) NEW §17 Activation Modes — strict/standard/express parameter shape per [c8a47e91 v1.1](../../vault/files/c8a47e91.md); calling agent picks rigor at activation; engine reads + enforces per chosen mode's gate-list; resolves the lightweight-vs-heavy verification tension by making rigor a typed parameter. (2) NEW §18 Multi-Target Activation + Output Path Convention — wrapper.target as list-of-strings supports multi-target wrappers; publish.py iterates over resolved target list from --target activation parameter OR wrapper.target default; output path lands at 02-outbox/<sub_system>/<sub_sub_system>/<slug>/<slug>-<timestamp>.<ext> per Mike-G60 hierarchical content-grouped framing; working-copy/import-export loop at external-work/docx/ preserved per 5a89297a (different use case; different lineage); full design at [e7d4b58f v1.0](../../vault/files/e7d4b58f.md). (3) Amended §3 schema docs: target field accepts string OR list-of-strings; output_path default amended per §18 convention. Companions: [c8a47e91 v1.1](../../vault/files/c8a47e91.md) activation-modes design lock + [e7d4b58f v1.0](../../vault/files/e7d4b58f.md) Phase 3a integration design + [b7e4f192](../../vault/files/b7e4f192.md) bio template (LOCKED; already in §16). T10 engine specs for §17 + §18 wiring filed on metis-talos.md 2026-05-24. Composes with: publish_targets/web.py + publish_targets/docx.py (engine reads the modes block); manifest-walker.py (target schema validation); publish-check.py (preflight per-mode gate-list check)."
v1_2_amendment_note: "v1.1 → v1.2 amendment 2026-05-24 by Argus A81 captain-mode under v1.52 cycle P-lane P1+P2+P5 coupled substrate-class amendment per Mike-A81 'proceed' directive 2026-05-24 + stm-a81-003 strong-lean execute calibration. Absorbs three Metis G58+G59 LOCKED design briefs into capsule binding contract: (1) NEW §14 Package Step Specification — Dated-Filename Model + Check-and-Move Rule + Conflict Surfacing per [2f5e8c1a v1.3]; (2) NEW §15 Design Step Specification — Substrate Inputs + Brand-Kit Inheritance + Agent Behavior + Iteration Modes + Diff-Aware Re-Runs + Close + Handoff per [5b3e9c47 v1.1]; (3) NEW §16 Section-Scope Substrate Composition + Bio Cascade per [b7e4f192] G59 finding (5 design-space questions resolved captain-mode per Metis G59 leans: WHERE section-scope 03-design + WHO author content + section-owner placement + HOW format-step substitution + WHEN every publish + WHAT explicit republish-cycle). Composes with: numeric-folder-prefix.capsule v1.0 [61f650aa] (governs 02-outbox + 03-design canonical reservations) + 02-outbox/AGENTS.md + 03-design/AGENTS.md (P4 governance contracts authored same session). Does NOT block Metis G59 parallel-track cleanup_rules fix at [8a3f1c52] (engine implementation, separate lane). v1.2 amendments are substrate-class binding contract; briefs carry the full design narrative."
status: active
state: active
owner: argus
author: argus-a78
created: 2026-05-22
modified: 2026-05-24
created_by: argus-a78
modified_by: metis-g60
schema_version: 2
extraction_scope: ship
governed_by: 8dd772a0
aligned_with:
  - "c5a7e391"   # Extraction-and-Publish Pipeline brief v0.5 (§3.6 class-core/workflow distinction + §3.7 implementation status + §13 polish backlog)
  - "143c74d5"   # v1.49.0 cycle brief v0.3 (codification cycle)
  - "eeb59ddf"   # ship-artifact.capsule v1.4 (composes with §Publish-Act + Check 27)
  - "e2e45d6b"   # architectural-pattern observation (substrate-resident discipline)
member_of:
  - "76bab75f"   # tropo-playbooks (capsule definitions)
tags: [capsule-definition, publish-pipeline, typed-primitive, lightweight-class, workflow-utility, v1-49-0, v1-49-0-2-polish-absorbed, argus-a78-authored, talos-t9-engineered]
implements_in_code:
  - ".tropo/scripts/publish.py"             # thin shared runner (class core)
  - ".tropo/scripts/publish_types.py"       # StageResult / PublishResult / PublishTargetError
  - ".tropo/scripts/publish-check.py"       # NEW v1.1: pre-publish readiness check (composes validator + manifest-walker; user-facing CLI; --create-wrapper auto-authors per c5a7e391 §13.3 P4)
  - ".tropo/scripts/publish_targets/web.py"  # web target implementation (stage + publish gesture); v1.49.0.1 Talos patch added _platform_commit + publication_state.web update
  - ".tropo/scripts/lib/article_readiness.py"  # NEW v1.1 DRY-refactor: shared field-presence rule logic; consumed by both tropo-validate.py validators + publish-check.py CLI checks; single source of truth for what makes an article+wrapper publish-ready
  - ".tropo/scripts/publish_targets/docx.py" # docx target implementation (stage only)
example_definitions:
  - "f1b4c8d2"   # publish-to-web operational
  - "e0a3d9c7"   # publish-to-docx example
---

# publish.pipeline.capsule v1.3 — Typed Primitive for Lightweight Extract-and-Publish Pipelines

*The publish.pipeline class is a lightweight typed primitive in Tropo-OS that automates **workflow steps 1-3** of c5a7e391's locked five-step universal extract-and-publish pattern (extract / package / design+format) inside a thin shared runner script. Workflow step 4 (publish) lives as target-specific extension outside class core. Workflow step 5 (verify) lives as human activity outside class core. Per [c5a7e391 v0.4 §3.6](../../vault/files/c5a7e391.md).*

*Distinct from dev-pipeline class: dev-pipeline ships releases (heavy; multi-week; gate-heavy); publish.pipeline ships content from vault to external targets (light; same-session; common human work).*

---

## §1. Intent

Codify a reusable typed primitive that lets users (and agents) author short markdown files declaring "publish these vault files to this target with this template" and have the publish run via a single command.

The class is **lightweight by design**. Six friction minimizers are binding contract:

1. **Convention over configuration** — minimum 4 required fields; sensible defaults for everything else
2. **Single-command invocation** — `python3 .tropo/scripts/publish.py <pipeline-uid-or-path>`; no flags for common case
3. **No mid-run prompts** — fully automated; fail-fast at start with actionable error if config bad
4. **Idempotent re-runs** — overwrites cleanly; no accumulated cruft
5. **Clear actionable error output** — names file + line + fix; no stack traces as primary surface
6. **Defaults inherited from capsule** — pipeline definitions are typically ~10 lines; long only when needed

---

## §2. Class Core vs Workflow Steps

Per [c5a7e391 §3.6](../../vault/files/c5a7e391.md), the publish.pipeline class operates as a SHARED-RUNNER SUBSET of c5a7e391's five-step universal workflow:

| Workflow step (c5a7e391 §3) | publish.pipeline class-core stage | Implementation |
|---|---|---|
| Step 1 — Extraction | **extract** (with cleanup_rules applied) | publish.py extract_*() + lib/ship_extract/ engine |
| Step 2 — Packaging | (collapsed into extract output shape) | Per-target packaging via stage() |
| Step 3 — Design & Formatting | **template** (apply target template) | Target module's stage() function |
| (artifact lands) | **stage** (write to external-work/) | Target's stage() returns StageResult |
| Step 4 — Publish | **TARGET-SPECIFIC EXTENSION** (outside class core) | Optional publish() entrypoint on target module |
| Step 5 — Verify | **HUMAN ACTIVITY** (outside class core) | User opens artifact + visually validates |

**Class core is 3 stages observable to the user** (extract → template → stage); workflow steps 4 + 5 are extensions/human-activity outside class core. Per Mike-A78 v1.49.0 walk Q3 reshape.

---

## §3. Pipeline Definition Schema

A publish.pipeline.md definition lives at `vault/files/<uid>.md` with `type: publish-pipeline` frontmatter.

### Required fields

| Field | Type | Purpose |
|---|---|---|
| `uid` | 8-hex string | Standard vault entry UID |
| `type` | literal `"publish-pipeline"` | Type discriminator |
| `title` | string | Human-readable name |
| `source` | UID string | Project UID OR manifest_root UID (where source files live) |
| `target` | string OR list-of-strings | One of `web`, `docx`, `pdf`, `pptx`, ... (extensible via new target modules); list-shape `[web, docx, pdf]` declares multi-target wrappers per §18 (calling agent picks subset via `--target` activation parameter; default fires all declared) |
| `selection_rules` | dict | How to pick files from source (one of three shapes — see §3.1) |

### Optional fields (defaults inherited from capsule)

| Field | Type | Default | Purpose |
|---|---|---|---|
| `template` | string | per-target default | Target template name (e.g., `default` for web; `standard` for docx) |
| `cleanup_rules` | dict | per-target defaults from manifest | Per [c5a7e391 §3.5 six-field schema](../../vault/files/c5a7e391.md) — strip_nav_block / strip_relations_tables / etc. |
| `output_path` | string | auto-derived from target convention per §18 | Phase 3a default (publish-pipeline outputs): `02-outbox/<sub_system>/<sub_sub_system>/<slug>/<slug>-<timestamp>.<ext>` (hierarchical content-grouped per §18). Working-copy/import-export loop default (per [5a89297a v0.5](../../vault/files/5a89297a.md)): `external-work/<target>/<pipeline-slug>/<filename>.<ext>` — preserved as-is for that lineage. Explicit override always honored. |
| `expected_output` | string | per-target template's output pattern | What stage() should produce |

### §3.1 — selection_rules shapes

Three shapes supported. A pipeline declares exactly one.

**Shape A — `manifest_root: <uid>`** (web target operational pattern)

Walks all ship-artifact wrapper entries declared in the named manifest root for the pipeline's target.

```yaml
selection_rules:
  manifest_root: 4a99638d   # Tropo Website Content Structure
```

**Shape B — `explicit_uids: [<uid1>, <uid2>, ...]`**

Selects an explicit list of vault entries.

```yaml
selection_rules:
  explicit_uids:
    - 7d4c3e8a
    - a2c8f4e1
```

**Shape C — `all_files_of_type: [<type1>, <type2>, ...]`** (note: planned; not yet operational in v1.0)

Selects all entries member_of the source project where `type:` matches any in the list.

```yaml
selection_rules:
  all_files_of_type: [note, document]
```

---

## §4. Minimum + Maximum Examples

### Minimum example (8 lines)

```yaml
---
uid: <generated>
type: publish-pipeline
title: "Publish my agent work to docx for colleague"
source: <vault-project-uid>
target: docx
template: standard
selection_rules:
  all_files_of_type: [note, document]
---
```

That's the floor. Everything else inherits from capsule defaults.

### Maximum example (25 lines)

```yaml
---
uid: <generated>
type: publish-pipeline
title: "Publish KGAE article to tropo-ai.com via web target"
source: 7d4c3e8a
target: web
template: article-layout
selection_rules:
  explicit_uids: [7d4c3e8a]
cleanup_rules:
  strip_nav_block: true
  strip_relations_tables: true
  strip_italic_provenance_lines: true
  non_rendering_sections:
    mode: convention
  frontmatter_strip:
    mode: minimal
  uid_link_rewriting:
    mode: published_only
    published_target_pattern: "/kb/<uid>"
    unpublished_behavior: strip_link_render_text
output_path: external-work/web/agentic-builders/
expected_output: external-work/web/agentic-builders/7d4c3e8a/index.md
---
```

For target-specific cleanup_rules, see [c5a7e391 §3.5 Cleanup Rules Schema](../../vault/files/c5a7e391.md) for full field specification.

---

## §5. Target-Implementation Interface Contract

Each target lives at `.tropo/scripts/publish_targets/<target>.py` and exports a function-level interface.

### Required entrypoint

```python
def stage(extracted_content: dict[str, str], pipeline_definition: dict) -> StageResult:
    """
    Apply target template to extracted+cleaned content; write to staging path.

    Args:
        extracted_content: dict of {output_path: cleaned_markdown_content}
                          from publish.py class-core extract+cleanup pass
        pipeline_definition: parsed publish.pipeline.md frontmatter dict

    Returns:
        StageResult(success, output_paths, extracted_count, errors, warnings, metadata)

    Raises:
        PublishTargetError on actionable failures (must specify file_path + line when applicable)
    """
```

### Optional entrypoint (workflow step 4 extension)

```python
def publish(stage_result: StageResult, pipeline_definition: dict) -> PublishResult:
    """
    Workflow step 4: publish gesture (target-specific delivery).

    Web target implements: rsync external-work/web/ → tropo-ai/website-content
    working copy; sentinel commit (pipeline-bot@argo-os); git push; Vercel hook.

    Docx target omits this entrypoint (stops at stage; user attaches docx
    to email or whatever colleague-delivery is needed).

    Args:
        stage_result: StageResult returned by stage()
        pipeline_definition: parsed publish.pipeline.md frontmatter dict

    Returns:
        PublishResult(success, committed, errors)

    Raises:
        PublishTargetError on actionable failures
    """
```

### Discovery

`publish.py` imports `publish_targets.<target>` based on `target:` field in pipeline definition. Missing module → exit 3 with clear error naming expected module path (`.tropo/scripts/publish_targets/<target>.py`).

### Data types

All target implementations use shared dataclasses from `.tropo/scripts/publish_types.py`:

```python
@dataclass
class StageResult:
    success: bool
    output_paths: list[str]
    extracted_count: int
    errors: list[str]
    warnings: list[str]
    metadata: dict

@dataclass
class PublishResult:
    success: bool
    committed: bool
    errors: list[str]

class PublishTargetError(Exception):
    """message + optional file_path + optional line"""
```

---

## §6. Publish-Act Semantics (Sentinel Convention)

*This section resolves S0.1 of the v1.49.0 cycle per Talos T9 + Argus A78 pair-call 2026-05-22.*

For web target (and any future target that implements publish gesture extending into the vault substrate), the publish-act event is defined by **commit-author-email identity**, NOT by message prefix.

### The Sentinel

**Sentinel identity:** `pipeline-bot@argo-os` (commit author email)

Rationale: commit-author identity is structurally harder to forge than message prefix (which is mutable via `git commit --amend`). Author-email is git-blame-readable and tamper-evident.

### Two-Commit Publish-Act Flow (Web Target)

1. **Sentinel commit to target repo** (e.g., `tropo-ai/website-content`) — extracts + staged content; author = `pipeline-bot@argo-os`. **This commit IS the publish-act event.**
2. **Git push + Vercel hook** — target's CI fires (Vercel build → deploy).
3. **Post-push: vault publication_state update** — second commit to vault updates `publication_state.<target>: live` on the ship-artifact wrapper; also authored as `pipeline-bot@argo-os`.

### Composition with ship-artifact.capsule v1.4 Check 27

Check 27 (publication_state pipeline-write) **derives from the sentinel**. Validation surface: `git blame` on the wrapper's `publication_state` field → author must be `pipeline-bot@argo-os` for the field-write commit. If a human-authored commit modifies publication_state, Check 27 fails (humans don't author publish-act; publish.pipeline does).

Message prefix `[pipeline-bot]` is SECONDARY (provides grep-ability + scan-readability) but NOT the Check 27 enforcement surface.

### Operational Status (v1.1 amendment 2026-05-22)

**The two-commit publish-act flow is OPERATIONAL** in publish_targets/web.py per Talos's v1.49.0.1 surgical patch (shipped 2026-05-22). Concrete 6-step sequence the web target now runs:

1. **rsync** `external-work/web/` → working copy (non-destructive invariants)
2. **Sentinel commit** to `tropo-ai/website-content` (author: `pipeline-bot@argo-os`)
3. **Push** to website-content origin
4. **`_platform_commit()`** — updates `publication_state.<target>: live` on each published wrapper's frontmatter + stages `app/(web)/kb-content/` mirror + commits + pushes platform repo (author: `pipeline-bot@argo-os`)
5. **Vercel deploy hook** (fires LAST, after platform push, so Vercel reads current content)
6. **Done**

Sequencing is load-bearing: step 4 must complete BEFORE step 5 fires so Vercel reads the just-committed platform state. Reversing order causes Vercel to deploy stale content (Fire 2 class of c5a7e391 §13.2 KGAE retrospective).

### Per-Target Sentinel Behavior

| Target | Publish gesture | Sentinel applies? |
|---|---|---|
| **web** | rsync + sentinel commit + push + Vercel hook | YES — sentinel commit IS publish-act event |
| **docx** | None (stops at stage) | N/A — no publish gesture, no sentinel needed |
| **pdf / pptx / future** | Per target; if no vault state change, no sentinel | Sentinel required only if target writes back to vault |

---

## §7. Validator Checks

**Four validator checks fire against publish.pipeline + ship-artifact + source-article substrate during `tropo-validate.py` runs. All four SHIPPED at v1.49.0 + v1.49.0.2 (Argus A78 2026-05-22) — see §13.**

### check_publish_pipeline_md_schema  ✅ SHIPPED v1.49.0

**Scope:** every vault entry with `type: publish-pipeline`
**Validates:** required fields present (target, source, selection_rules); target is a string; selection_rules shape matches one of A/B/C; if cleanup_rules declared, conforms to dict shape
**Severity:** WARN at v1.49.0 → ERROR ratchet at v1.50.0+

### check_target_module_present  ✅ SHIPPED v1.49.0

**Scope:** every publish.pipeline.md definition's `target:` value
**Validates:** `.tropo/scripts/publish_targets/<target>.py` exists + is importable
**Severity:** WARN at v1.49.0 → ERROR ratchet at v1.50.0+
**Rationale:** publish.py exits 3 if target module missing at runtime — validator catches before runtime invocation, preserving fail-fast posture per friction minimizer #3.

### check_article_source_required_fields  ✅ SHIPPED v1.49.0.2

**Scope:** every vault entry with `subtype: article` AND `status` not in {draft, archived, recycled}
**Validates:** required fields `slug` + `published_at` + `title` present (lib.ts truth — agentic-builders/lib.ts parseVaultFile() silently returns null without these)
**Severity:** WARN at v1.49.0.2 → ERROR ratchet at v1.50.0+
**Closes:** Fire 3 class of c5a7e391 §13.2 KGAE retrospective (KGAE source was locked at v1.0 but missing slug + published_at; produced production 404)
**Status discipline:** drafts/archived/recycled SKIPPED — publish-fields only required when article is publish-ready

### check_ship_artifact_required_fields  ✅ SHIPPED v1.49.0.2

**Scope:** every vault entry with `type: ship-artifact`
**Validates:** required fields for ALL: `kind` (must be `file` or `folder`) + `target` (must be array shape per v1.3+); required for kind=file additionally: `canonical_source` + `parent` (8-hex UID; coerced to string for shape check since YAML auto-parses unquoted 8-hex as int)
**Severity:** WARN at v1.49.0.2 → ERROR ratchet at v1.50.0+
**Closes:** Fire 1 class of c5a7e391 §13.2 KGAE retrospective (KGAE wrapper was missing `kind: file` so publish.py extract_manifest_root silently dropped it)
**Shape discipline:** folder-class wrappers (e.g., category roots like 4938b65a Articles) are exempt from canonical_source + parent checks — they ARE the parent

### publish-check.py — preflight composition (user-facing)  ✅ SHIPPED v1.49.0.2

The 4 validators above run at vault-rebuild time (WARN level). For user-facing preflight on a specific article before publishing, use `.tropo/scripts/publish-check.py <article-uid>` (or `--slug <slug>`) — composes the validator logic + manifest-walker lookup into one command with actionable error output + ready-to-paste wrapper scaffolds. `--create-wrapper` flag auto-authors the wrapper (interactive confirm + source-readiness gate per c5a7e391 §13.3 P4). See §11.1.

### lib/article_readiness.py — shared field-presence rule module  ✅ SHIPPED v1.49.0.2

DRY-refactor per R1 paired-walk P1 finding on publish-check.py (skeptic-arch 2026-05-22: "extract the field-presence rules into a shared module so both consumers share a single source of truth + can't drift"). Module exports:

- `check_source_article_required_fields(uid, fm) -> CheckResult` — shared source-article rules
- `check_wrapper_required_fields(uid, fm) -> CheckResult` — shared wrapper rules
- `CheckResult` dataclass — findings + blocking + skipped flag (consumers prepend their own severity prefixes)
- `VALID_WRAPPER_KINDS` + `NON_PUBLISH_READY_STATUSES` constants

Consumed by:
- `tropo-validate.py` (vault-rebuild WARN-level batch checks)
- `publish-check.py` (user-facing preflight per-article CLI)

Both consumers add their own output formatting (validator: `[WARN]/[FAIL]` text prefixes; CLI: `_fail/_warn/_ok` ANSI+text-prefix). Rule logic stays in one place. Future consumer (e.g., `tropo publish` command per P5; auto-wrapper enhancements per P4) imports from same module.

---

## §8. Exit Codes

### publish.py runtime

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Validation or extraction failure |
| 2 | No entries found for selection_rules |
| 3 | Target module not found |
| 4 | Pipeline definition not found or invalid |

### publish-check.py preflight (v1.1 NEW)

| Code | Meaning |
|---|---|
| 0 | READY — article passes all preflight checks |
| 1 | NOT READY — article has blocking defects (output names specific fixes + where to apply them) |
| 2 | Article UID or slug not found in vault (also: malformed YAML in source frontmatter; bad UID shape) |
| 3 | No wrapper found for article (script outputs ready-to-paste wrapper scaffold with actual category UIDs) |

---

## §9. Composes With

- **[c5a7e391 v0.4 §3.6](../../vault/files/c5a7e391.md)** — universal workflow pattern + class-core/workflow distinction
- **[c5a7e391 §3.5 Cleanup Rules Schema](../../vault/files/c5a7e391.md)** — cleanup_rules field schema (six sub-fields)
- **[c5a7e391 §4.5 Asset-Handling Architecture](../../vault/files/c5a7e391.md)** — `!asset:` sentinel for binary references in vault markdown
- **[ship-artifact.capsule v1.4](ship-artifact.capsule.md)** — §Publish-Act + Check 27 (publication_state pipeline-write derives from sentinel)
- **[ship-artifact.capsule v1.4 §External-Work](ship-artifact.capsule.md)** — external-work/ staging architecture (output directory shape)
- **[Tropo Website Content Structure (4a99638d)](../../vault/files/4a99638d.md)** — web target manifest root example
- **[lib/ship_extract/](../../.tropo/scripts/lib/ship_extract/)** — shared extraction engine used by publish.py class core
- **[publish-to-web (f1b4c8d2)](../../vault/files/f1b4c8d2.md)** — operational example pipeline definition (web target)
- **[publish-to-docx (e0a3d9c7)](../../vault/files/e0a3d9c7.md)** — example pipeline definition (docx target)
- **[v1.49.0 cycle brief (143c74d5)](../../vault/files/143c74d5.md)** — codification cycle that ships this capsule

---

## §10. State

publish.pipeline.md definitions have a simple state machine:

| State | status: | Meaning |
|---|---|---|
| `draft` | `draft` | Authored; not yet operational |
| `active` | `active` | Operational; can be invoked via publish.py |
| `archived` | `archived` | No longer operational; preserved for honest historical record |

No publish-time state changes on the pipeline definition itself — state changes happen on the ship-artifact wrappers that the pipeline publishes (per ship-artifact.capsule v1.4 §Publish-Act).

---

## §11. Authoring Guide

### §11.1 Pre-publish readiness check (use FIRST when publishing an article)

Before invoking publish.py against a vault article, run the preflight check:

```bash
python3 .tropo/scripts/publish-check.py <article-uid>
# OR by slug if you don't know the UID:
python3 .tropo/scripts/publish-check.py --slug <url-slug>
```

The preflight catches at vault-rebuild-time the three substrate-coherence defect classes from the v1.49.0 KGAE retrospective ([c5a7e391 §13.2](../../vault/files/c5a7e391.md)): source article missing required fields (subtype/slug/published_at/title); wrapper missing required fields (kind/target/canonical_source/parent); target module not present.

**Output decoder:**
- **`[OK] READY`** — article passes all preflight; output names the exact publish.py command + pipeline UID resolved
- **`[FAIL] NOT READY`** — output names each specific defect + where to fix it (file + frontmatter field + example value)
- **`No wrapper found`** — output prints a ready-to-paste wrapper scaffold with the actual category UIDs filled in

Run preflight at vault-rebuild time too if you want WARN-mode coverage: `python3 .tropo/scripts/tropo-validate.py` runs `check_article_source_required_fields` + `check_ship_artifact_required_fields` + `check_publish_pipeline_md_schema` + `check_target_module_present` across the entire vault.

### §11.2 Authoring a new publish.pipeline.md definition

When authoring a NEW publish.pipeline.md (separate concern from publishing an existing article):

1. **Choose target.** What format do you need to produce? (`web` for tropo-ai.com; `docx` for colleagues; `pdf` for documents; future: `pptx`, etc.)
2. **Confirm target module exists.** Check `.tropo/scripts/publish_targets/<target>.py`. If not, the target needs to ship first (separate work).
3. **Choose selection shape.** Single file = `explicit_uids: [<uid>]`. All files in a project = `all_files_of_type` (v1.1+) or `explicit_uids`. Full manifest = `manifest_root: <uid>`.
4. **Pick template.** Each target has a default template; check the target module's docstring for additional options.
5. **Cleanup rules: usually inherit from capsule defaults.** Override only if your case is genuinely unusual (most cases don't need overrides).
6. **Author the markdown file.** Land at `vault/files/<new-uid>.md` with frontmatter following §3 schema.
7. **Smoke test with --dry-run.** `python3 .tropo/scripts/publish.py <uid> --dry-run` prints what would happen without writing.
8. **Live run.** `python3 .tropo/scripts/publish.py <uid>` executes the pipeline.

---

## §12. Provenance

Full per-version provenance (v1.0 + v1.1 authoring records) extracted to the [history companion (78c51bdf)](publish.pipeline.history.md). Current + previous version provenance: the `v1_3_amendment_note` + `v1_2_amendment_note` frontmatter fields.

---

## §13. Implementation Status

The v1.1-era per-component shipped/deferred snapshot (frozen as of v1.49.0.2) is preserved in the [history companion (78c51bdf)](publish.pipeline.history.md). Current operational truth: query the vault index for the `implements_in_code:` paths in this capsule's frontmatter; the §7 validator checks fire at every rebuild. The deferred-arc items live at [c5a7e391 §13.4 + §13.6](../../vault/files/c5a7e391.md).

---

## §14. Package Step Specification (v1.2 amendment per [2f5e8c1a v1.3](../../vault/files/2f5e8c1a.md))

The package step of the publish.pipeline class (workflow Step 2 of [c5a7e391](../../vault/files/c5a7e391.md)'s universal extract-and-publish pattern) creates the `02-outbox/` folder structure on first run and verifies/refreshes it on subsequent runs. Three concrete rules bind contract; full design narrative lives at the source brief.

### §14.1 Folder Shape (LOCKED)

```
02-outbox/<medium>/<section>/<article-slug>/
  <article-slug>-[YYYY-MM-DDTHHMMSS].md           ← source for current publish run
  <article-slug>-[YYYY-MM-DDTHHMMSS].docx         ← target output, same timestamp as source
  <article-slug>-[YYYY-MM-DDTHHMMSS].pdf          ← target output, same timestamp as source
  /03-design                                       ← section-scope design substrate per §15.2 cascade
  /versions                                        ← prior dated sets archived here as units
```

`<medium>` examples: `web`, `print`. `<section>` examples: `agentic-builders`, `news`, `<day-job-project>`. `<article-slug>` is the published slug. Folder convention governed by [numeric-folder-prefix.capsule v1.0 (61f650aa)](numeric-folder-prefix.capsule.md) + folder-scoped [02-outbox/AGENTS.md](../../02-outbox/AGENTS.md).

### §14.2 Dated-Filename Model (Decision 1)

Every file inside an article-slug folder is timestamped with the publish run's date-time:

- Source markdown: `<article-slug>-[date-time].md`
- All target outputs from that run: `<article-slug>-[date-time].docx`, `.pdf`, etc.

**A "set" is the source + all target outputs from one publish run, all sharing the same timestamp.** `/versions/` stores prior sets; each moves to `/versions/` as a unit on subsequent runs.

- **Why date everything (including binary outputs):** preserves docx/pdf history alongside markdown. Asymmetric dating loses deliverable history.
- **Filename format:** ISO 8601 compact with seconds resolution (e.g., `2026-05-23T143012`). Implementation chooses exact separator characters.

### §14.3 Check-and-Move Rule (Decision 2)

The check-and-move primitive fires **only when a replacement is incoming**:

1. publish.py begins a publish run; computes the run's timestamp
2. For each file the run will write (source + targets), check if a prior file with the same article-slug + different timestamp exists at the article-slug folder
3. If yes (replacement incoming): move the prior set as a unit to `/versions/<prior-timestamp>/`
4. If no (first run for this article OR cleanup-only run): no move; the run authors fresh

This avoids `/versions/` accumulating empty directories on non-replacement runs.

### §14.4 Divergent-Update Conflict Surfacing (Decision 3)

When publish.py begins a run, it compares mtime of:

- The vault source entry (`vault/files/<source-uid>.md`)
- The latest dated source in the article-slug folder (`<article-slug>-[latest-date].md`)

**If the dated source is newer than the vault source** (divergent update; someone edited the dated copy directly), publish.py:

- Halts before the package step proceeds
- Surfaces the divergence + asks the user: (a) discard the dated edit and republish from vault; (b) pull the dated edit back into vault first; (c) cancel
- Does NOT silently overwrite

**Exit code:** publish.py exits 5 on divergent-update halt (extends §8 exit codes; the existing 0/1/2/3/4 sequence stays intact).

### §14.5 Optional `source_authority:` Field

A pipeline definition MAY declare `source_authority:` to suppress the divergent-update check when the publish flow intentionally writes to the dated source first:

```yaml
source_authority: dated_outbox   # default is "vault" (the standard pattern)
```

Two values: `vault` (default; divergent-update check fires) or `dated_outbox` (suppress check; dated source is authoritative for this pipeline). Rarely used.

---

## §15. Design Step Specification (v1.2 amendment per [5b3e9c47 v1.1](../../vault/files/5b3e9c47.md))

The design step (workflow Step 3a of [c5a7e391](../../vault/files/c5a7e391.md)'s universal pattern) is where an agent and the user collaborate to develop visual + voice assets that compose the article into a brand-consistent, audience-ready artifact. Format step downstream is pure rendering; design step is where shaping happens.

### §15.1 Substrate Inputs at Step Open

By design-step open, the package step has placed:

- The canonical source at `<article-slug>/<slug>-[date-time].md`
- Empty `<article-slug>/03-design/` ready to receive article-specific assets
- The target outputs declared in pipeline def (web, docx, pdf, etc.)
- The target template selected per declared target

The design step does NOT need dated target outputs to exist yet — format step renders them downstream.

### §15.2 Brand-Kit Inheritance Cascade (LOCKED)

The design step inherits brand-kit substrate from higher scopes via filesystem hierarchy. Agent walks UP the design tree at step open:

```
argo-os/03-design/                                    ← global Studio brand (Claude Design export; studio root)
02-outbox/<medium>/03-design/                         ← medium-specific overrides (e.g., web/print)
02-outbox/<medium>/<section>/03-design/               ← section-specific overrides + section substrate
02-outbox/<medium>/<section>/<slug>/03-design/        ← article-specific (empty at first run; populated by design step)
```

**Brand-kit format LOCKED:** Claude Design export format (Anthropic April 2026; DTCG-aligned per W3C Design Tokens Community Group draft). Each 03-design folder constituting a brand kit contains `README.md` + `STYLE-GUIDE.md` (identity, color, type, spacing, layout, motion, voice) + `tokens.css` (CSS custom properties; `--tropo-*` namespaced) + `tokens.json` (`$schema: https://design-tokens.github.io/community-group/format/`; industry-portable) + `fonts.md` + `components.md` + SVG/raster assets. Per [03-design/AGENTS.md](../../03-design/AGENTS.md) canonical reference.

### §15.3 Agent Behavior Across Design-Step Lifecycle

**Opening pattern (agent initiative):**

1. Walk up the design tree; surface the inherited brand context to the user (current section substrate + voice anchor + applicable component spec)
2. Present a brief design opener for the article (e.g., "Section voice is X; component cues are Y; here's a first-pass treatment direction")
3. Wait for user steer before iterating

**Brainstorming pattern:** agent proposes; user redirects. No design choices land without user confirmation. Per Mike-G58 design-step is mike-in-loop binding pin (not unilateral agent authoring per Metis G58 design-step gap surfaced at case-study piece retrospective).

### §15.4 Iteration Modes

Two iteration modes:

- **Conversational** (default): each iteration is a user steer + agent revision; small bounded loops
- **Batch-revision** (explicit user opt-in): user provides a list of changes; agent applies in batch + returns for next steer

User can switch modes mid-step via verbatim direction.

### §15.5 Diff-Aware Re-Runs

On re-run (publish.pipeline activated against an article that has a prior dated set):

- Design step reads the previous dated set's `03-design/` contents
- Surfaces diff between prior assets + the current source's design needs
- Asks user: (a) re-use prior design assets; (b) update specific assets; (c) start fresh
- No silent re-design; explicit user choice each re-run

### §15.6 Close + Handoff to Format Step

Design step closes when:

- User signals design complete (verbatim direction OR explicit close gesture)
- `<article-slug>/03-design/` contains the assets the format step needs (or is intentionally empty if the article needs no per-article design substrate beyond inherited cascade)
- Voice review completed per [doc-spec.capsule v1.0 §Voice Review Definition](doc-spec.capsule.md) + [voice-review.skill (811856a5)](../skills/voice-review.skill.md) three-layer contract (tone + lore + stranger-encounter test)

State handed to format step: dated source + populated 03-design/ + applicable brand cascade + selected target template per pipeline def.

---

## §16. Section-Scope Substrate Composition (v1.2 amendment per [b7e4f192](../../vault/files/b7e4f192.md))

Some substrate composes across pieces in a section rather than living inline in each piece (e.g., author bios, section voice anchors). This section governs section-scope substrate resolution at publish-time.

### §16.1 Section-Scope Substrate Location

Section-scope substrate lives at `02-outbox/<medium>/<section>/03-design/` per the brand-kit cascade pattern (§15.2). Examples:

- `02-outbox/web/agentic-builders/03-design/bio.md` — author bio for all agentic-builders pieces
- `02-outbox/web/agentic-builders/03-design/section-voice.md` — section voice anchor (future)
- `02-outbox/web/agentic-builders/03-design/footer.md` — section footer (future)

### §16.2 Composition into Pieces (Format-Step Substitution; LOCKED)

Per Metis G59 lean ratified captain-mode by Argus A81 2026-05-24 per Mike-A81 strong-lean calibration:

- **WHERE substrate lives:** section-scope `03-design/` (cascade-parallel to brand kit; natural home)
- **WHO owns content:** the author owns their own bio content; the section owner owns placement + wrapper styling
- **HOW composed:** format-step substitution (publish.pipeline format step appends section-scope substrate to extracted content at composition-time). Source markdown stays clean; no template directives leak into source; bio composition is a publish-time concern not a source-authoring concern
- **WHEN it refreshes:** on every publish (same as cleanup_rules run on every extract). Per-piece overrides allowed (rare cases where a piece needs a custom variant; declared via `section_substrate_override:` field on the article wrapper)
- **WHAT on substrate update:** explicit republish-cycle for substrate updates (operator action; not automatic). Preserves the dated-set + sentinel-commit discipline. Operator: "I edited bio.md; republish all pieces in /agentic-builders/" runs publish.pipeline against each piece in the section.

### §16.3 Bio Template as Worked Example

The bio template lives at `02-outbox/web/agentic-builders/03-design/bio.md` (and equivalent paths for other sections that publish bios). Format:

```markdown
---
type: section-substrate
substrate_class: bio
section: agentic-builders
medium: web
owner: <author-slug>   # who owns content
section_placement_owner: metis   # who owns placement + styling
last_updated: <iso-date>
---

<bio content in plain markdown; format-step appends to pieces in the section>
```

**Authoring authority:** the bio content is owned by the author. For Mike's bio at `02-outbox/web/agentic-builders/03-design/bio.md`, Metis is the section placement-owner who authors the file; Mike's bio content goes verbatim. Section-scope authority lives where design-class authority lives (Metis-lane).

### §16.4 Per-Piece Override

A piece's wrapper entry MAY declare:

```yaml
section_substrate_override:
  bio: inline   # use inline bio from the piece's source; suppress section-scope cascade
  bio: <uid-of-alternate-bio>   # OR use a specific alternate bio entry
```

Rare. Default is section-scope cascade.

### §16.5 Substrate-Update Republish Discipline

When section-scope substrate updates (e.g., bio refresh):

1. Metis (or section owner) edits `02-outbox/<medium>/<section>/03-design/<substrate>.md`
2. Operator runs publish.pipeline against each piece in the section that needs the refresh
3. Each piece's publish produces a new dated set with the updated section-scope substrate composed in
4. Prior dated sets move to `/versions/` per §14.3 check-and-move rule

Explicit republish-cycle (not automatic) preserves substrate-honest record + sentinel-commit discipline. Bio update is a deliberate cycle event, not a silent background process.

### §16.6 v1.52 P-lane P5 Closure Note

This section codifies the bio cascade per Metis G59's Path 2 finding [b7e4f192](../../vault/files/b7e4f192.md). The actual `02-outbox/web/agentic-builders/03-design/bio.md` file authoring is Metis-lane (she co-authored Mike's polished bio in the case-study piece work 2026-05-23; she owns the section-scope authoring + the corresponding `02-outbox/web/agentic-builders/03-design/` substrate). Section-scope file authoring composes with [Case-Study Piece Activation Plan (4f8c2a91)](../../vault/files/4f8c2a91.md) (G59's primary work).

---

## §17. Activation Modes (v1.3 amendment per c8a47e91)

*Pipeline activations are API-shaped: typed input (the ignition key — pipeline UID pointing at the typed spec) plus mode parameter (how much rigor) plus target parameter (which output format) plus template parameter (which template variant). The pipeline definition declares the activation_modes block; the engine reads the chosen mode + executes per the mode's declared gate-list + halt semantics. Calling agent picks intentionally based on the situation.*

### §17.1 Three Modes (initial implementation)

**Strict mode.** All gates fire. Engine HALTS on any failure. Mike-in-loop required at design walk + visual eyeball. Use cases: Cycle 1 of an important article; substrate-class publishes (governance docs, capsule schemas, ADRs); any time the calling agent wants maximum discipline before something hits readers.

Gates: extract_cleanness + package_structure + design_walk + publish_state + visual_eyeball. Halt: all. Require Mike-in-loop: [design_walk, visual_eyeball].

**Standard mode (default if --mode omitted).** Mechanical gates engine-enforced. Qualitative gates as agent-discipline recommendations (soft-warnings on skip; not halt). Use cases: routine cycles; bug squashes; micro-edits; pipeline-discipline already proven on prior cycle; most ongoing publish work.

Gates (hard): extract_cleanness + package_structure + publish_state. Halt: hard_gates_only. Soft gates: [design_walk, visual_eyeball].

**Express mode.** Minimum gates. User explicitly opts out of ceremony. Use cases: quick conversions (e.g., "convert .md to .docx and ship fast"); high-frequency low-stakes runs; single-target ship with no review needed; PDF generation for download.

Gates: source_exists + output_writeable + sentinel_commit. Halt: all (failure on any of these is absolute-required failure). No design walk; no eyeball gate before publish.

### §17.2 Activation Parameter Surface

```bash
# Default (standard mode; default target = wrapper.target; default template = pipeline_def.template)
python3 .tropo/scripts/publish.py <pipeline-uid> --cycle-context "..."

# Explicit modes
python3 .tropo/scripts/publish.py <pipeline-uid> --mode=strict --cycle-context "..."
python3 .tropo/scripts/publish.py <pipeline-uid> --mode=express --cycle-context "..."

# Explicit target + template (multi-param activation)
python3 .tropo/scripts/publish.py <pipeline-uid> --mode=express --target=docx --template=external --cycle-context "quick docx for client"
```

Parameter validation:
- `--mode` validates against this section's activation_modes declarations. Unknown mode = error before any execution.
- `--target` validates against wrapper.target list. Multi-target via comma-separated list. Unknown target for wrapper = error.
- `--template` validates against the available template set in the brand-kit cascade (template substrate brief pending). For initial implementation: accept string + log to run-log + pass to target module via pipeline_def['template'] override.

### §17.3 Substrate-Side Declaration

Pipeline definitions (or per-target-class capsule defaults) declare activation_modes blocks. Initial implementation hardcodes the three modes per §17.1; substrate-declared modes become readable once the activation_modes block ships as capsule-class field per this section.

```yaml
activation_modes:
  strict:
    description: "All gates fire; engine halts on any failure; Mike-in-loop required at design + eyeball."
    gates: [extract_cleanness, package_structure, design_walk, publish_state, visual_eyeball]
    halt_on_failure: all
    require_mike_in_loop: [design_walk, visual_eyeball]
  standard:
    description: "Default. Mechanical gates enforced; qualitative gates as agent-discipline recommendations."
    gates: [extract_cleanness, package_structure, publish_state]
    soft_gates: [design_walk, visual_eyeball]
    halt_on_failure: hard_gates_only
  express:
    description: "Minimum gates; user explicitly opts out of ceremony for quick conversions."
    gates: [source_exists, output_writeable, sentinel_commit]
    halt_on_failure: all
default_mode: standard
```

### §17.4 Cross-Pipeline-Class Generalization

The activation_modes pattern generalizes across pipeline classes (dev / doc / test / publish). Each pipeline class can declare its own mode-set with class-appropriate gate definitions. The shape is universal:

- Pipeline definition (or class capsule) declares activation_modes block
- Each mode has: description + gates + halt_on_failure semantics + (optional) require_mike_in_loop list
- Engine reads chosen mode at activation + executes accordingly
- Default mode is whatever the pipeline class declares

publish-pipeline ships the initial implementation; cross-class generalization is future-cycle work that lands once publish-pipeline implementation proves the design.

### §17.5 What This Resolves

Rigor becomes a typed activation parameter rather than a fixed engine property — strict IS the heavy path, express IS the lightweight path, standard IS the hybrid; the discipline is structurally enforced at the mode the calling agent chose. *(Design history — the v1.49 lightweight-vs-heavy tension + the G58 skipped-step failure mode — in the [history companion (78c51bdf)](publish.pipeline.history.md).)*

---

## §18. Multi-Target Activation + Output Path Convention (v1.3 amendment per e7d4b58f)

*Wrappers declare what targets are POSSIBLE; activation picks what to FIRE. Output paths land where content lives — content-grouped at the piece level under hierarchical sub_system / sub_sub_system path.*

### §18.1 Multi-Target Wrappers

Wrapper schema `target:` accepts string OR list-of-strings. List-shape declares multi-target capability:

```yaml
target: web              # single target (current default)
target: [web]            # equivalent list-shape
target: [web, docx, pdf] # multi-target wrapper
```

At activation:
- `--target=<comma-list>` picks subset to fire (e.g., `--target=web,docx`). Validates against wrapper.target.
- `--target` omitted: fires ALL targets in wrapper.target.
- Single-target wrappers (current behavior) continue to work unchanged.

publish.py iterates over resolved target list + dispatches to each target module independently. Per-target failure does not block other targets; engine emits warning per-target + accumulates results in activation_run log.

### §18.2 Output Path Convention (publish-pipeline outputs)

**Path shape:** `02-outbox/<sub_system>/<sub_sub_system>/<slug>/<slug>-<timestamp>.<ext>`

**Wrapper declares:**

```yaml
sub_system: web                    # broad content category (web, downloads, client-deliverables, marketing, internal, etc.)
sub_sub_system: agentic-builders   # section within (agentic-builders within web; client-name within client-deliverables; etc.)
```

Multi-target activation produces all outputs in the SAME piece-folder with the SAME timestamp:

```
02-outbox/web/agentic-builders/knowledge-graphs-arent-enough/
  ├── knowledge-graphs-arent-enough-2026-05-24T153336.md     ← web target output
  ├── knowledge-graphs-arent-enough-2026-05-24T153336.docx   ← docx target output
  ├── knowledge-graphs-arent-enough-2026-05-24T153336.pdf    ← pdf target output (future)
  ├── 03-design/                                              ← per-piece assets
  └── versions/                                               ← prior dated sets archive
```

Outputs are content-grouped at the piece level; format is the file extension at the leaf. Composes with §14 dated-source packaging primitive (the .md source already lands here; .docx/.pdf/etc. land alongside with same timestamp).

### §18.3 Versions Archive (per-target)

Each target's prior dated outputs archive to `<slug>/versions/` on subsequent publish runs (§14.3 check-and-move primitive extended per-target). Multi-target wrapper publish moves all prior dated outputs (.md + .docx + .pdf) to versions/ together as a coherent prior-dated set.

### §18.4 Working-Copy / Import-Export Loop (preserved per 5a89297a)

The working-copy / import-export loop at `external-work/<target>/<pipeline-slug>/<filename>.<ext>` (per [5a89297a v0.5](../../vault/files/5a89297a.md)) is PRESERVED AS-IS. Different use case (user-binary → markdown-edit → user-binary); different lineage; different governance; preserved per locked arch-spec.

Distinguishable at runtime via `pipeline_def.use_case` field (or equivalent). If `use_case: working-copy-export`, output path uses 5a89297a convention; else publish-pipeline outputs use §18.2 convention.

### §18.5 Web Target Special Case

Web target writes BOTH:
- Source-side artifact at `02-outbox/web/<section>/<slug>/<slug>-<timestamp>.md` per §18.2 (where dated source + 03-design + versions live).
- Platform-side mirror at `app/(web)/kb-content/<source-uid>.md` (platform repo; what Vercel deploys + article-route renders).

Two locations serve different consumers: source-side is substrate-honest artifact; platform-side is reader-facing renderable. Both stay.

### §18.6 Sub-System + Sub-Sub-System Semantics

For v1 implementation, sub_system + sub_sub_system are EXPLICIT wrapper frontmatter fields. Pre-Phase-3a wrappers (authored before v1.3 amendment) can be amended in bulk to declare these fields. Future cycles can add derivation rules (e.g., infer sub_system from wrapper's member_of chain; infer sub_sub_system from parent section).

### §18.7 Composes With Existing Substrate

- §14 Package Step (dated-filename + check-and-move + versions/) — same shape, extended per-target
- §15 Design Step (per-piece 03-design/ assets) — sits inside the piece-folder under §18.2 path
- §16 Section-Scope Substrate Composition (bio cascade) — bio template at `02-outbox/<sub_system>/<sub_sub_system>/03-design/bio.md` (section-scope folder one level up from piece-scope)
- [c5a7e391 v0.5](../../vault/files/c5a7e391.md) universal extract-and-publish pattern — §18 path convention extends Step 2 packaging semantics across multi-target
- [5a89297a v0.5](../../vault/files/5a89297a.md) working-copy primitive — preserved at external-work/ per §18.4

---

*publish.pipeline.capsule v1.3 | UID `7e3a91c8` | v1.3 amendment Metis G60 2026-05-24 (activation modes §17 + multi-target §18) | full version history at the [history companion (78c51bdf)](publish.pipeline.history.md) | Companion to c5a7e391 + ship-artifact.capsule + numeric-folder-prefix.capsule + doc-spec.capsule + 5a89297a working-copy spec*
*"The class codifies what the workflow describes. Three stages observable. Targets extend. Activation modes parameterize rigor. Humans verify."*
