---
uid: 4a2f6dbd
title: "Reconcile Imports"
type: playbook
version: "1.2"
status: active
locked_by: argus-a62
locked_at: 2026-05-14
v1_1_locked_by: argus-a61
v1_1_locked_at: 2026-05-13
modified: 2026-05-14
modified_by: argus-a62
created: 2026-05-13
created_by: argus-a60
author:
  name: "Argus"
  role: "Chief Architect"
domain: "substrate-reconciliation"
tags: [reconcile-imports, sa-reconciler, import-primitive, v1.25.0-stream-c, v1.26.0-stream-c-amendment, v1.28.0-stream-c-amendment]
v1_2_amendment_note: "v1.28.0 Stream C amendment per arch-spec [5a89297a v0.5](../files/5a89297a.md) §3.8 v0.5 — additive (semver minor). Three changes. (1) `template-binary-drift` event ACTIVATED — was reserved-deferred at v1.1; now live at §Step 4 + §Step 6 (judgment-class 0.50; surface_to_user with three resolution paths: accept-and-export / re-register / abort per arch-spec §3.7 precondition 3). (2) NEW `folder-mirror-orphan-state` event per arch-spec §3.8 v0.5 (closes sa.skeptic-008 P1-1 + sa.cold-boot-007 B2): emitted when reconciler encounters partial state from interrupted create-sidecar co-write (orphan .tmp mirror file OR on-disk marker without matching vault mirror); judgment-class 0.55; resolution path is reconciler-deterministic retro-fill using marker UID. (3) Folder-mirror UID-duplication sanctioned exception per arch-spec §3.8 v0.5 (closes sa.skeptic-008 P0-2): the existing v1.0 duplicate-UID-at-different-paths rule now treats `mirror_of: <same-uid>` self-reference + matching folder_marker_path as a sanctioned dual-residence pattern (skip duplicate-UID detection); composes with §3.10 check 8 NEW validator. Existing v1.0 + v1.1 behavior unchanged; v1.28.0 sa.reconciler runs detect template-binary-drift and folder-mirror-orphan-state in addition to the prior delta types."
v1_1_amendment_note: "v1.26.0 Stream C amendment per arch-spec [5a89297a v0.3](../files/5a89297a.md) §3.8 — additive (semver minor per the playbook's stated versioning rule: 'New patterns added to Step 5 catalog — semver minor'). §Step 2 extended with a SEPARATE working-copy + template enumeration walk (clean abstraction layer per arch-spec §3.8 layering fix — closes sa.skeptic-006 P1-5). §Step 4 extended with new delta type `working-copy-source-drift` (judgment-class; honors hash_function semantics per §3.8 closing sa.skeptic-006 P1-4). §Step 6 categorization table extended with row for the new event. Existing v1.0 behavior unchanged; v1.25.0 sa.reconciler runs continue to operate cleanly. v1.28.0 will add `template-binary-drift` event in the same shape."
trigger: [commissioned-by-sa-reconciler]
readers: [agent]
scope: single-reconciliation-pass
estimated_duration: "5-30 seconds (full-studio scope at typical knowledge-worker scale)"
spec: "vault/files/2b49ba79.md"   # Import Primitive Architecture Specification v1.0 LOCKED
requires:
  roles:
    - sa-reconciler-instance
calls:
  - "import-walker.py"
  - "scan-import-state.py"
schema_version: 2
extraction_scope: ship
governed_by: e6d373bc   # playbook.capsule
aligned_with:
  - "2b49ba79"   # Import Primitive Architecture Specification v1.0 LOCKED
  - "eedd7034"   # external-artifact.capsule v1.0
  - "013b7b6e"   # reconcile-report.capsule v1.0
member_of:
  - "d36c63c8"   # v1.25.0 Stream C — Reconciler Subsystem
  - "76bab75f"   # tropo-playbooks
---

# Reconcile Imports

*The playbook that sa.reconciler runs end-to-end on every reconciliation pass. Codifies the structural intelligence: enumerate substrate → detect deltas → recognize patterns → categorize events → apply routine changes → defer judgment-class to executive → produce structured report.*

*Locked v1.0 in v1.25.0 Stream C per locked arch-spec [vault/files/2b49ba79.md](../files/2b49ba79.md) §A.4 + §C.5. **v1.1 amendment in v1.26.0 Stream C per [arch-spec 5a89297a v0.3](../files/5a89297a.md) §3.8** — extends Enumeration / Delta Detection / Categorization for the working-copy primitive.*

---

## Intent

Keep the import primitive's substrate (sidecars, source files, vault projections) self-consistent as users edit, move, rename, copy, delete, and add content. The playbook executes structurally — every step has clear inputs, outputs, and decision logic — so the system's behavior is auditable and improvable.

The playbook is **the intelligence**. sa.reconciler is the process that runs it. The audit log is the durable state. New failure modes extend the playbook (pattern catalog additions, confidence threshold tuning); the system gets smarter over time.

---

## Rules

**Per-spawn ephemeral execution.** This playbook is invoked once per sa.reconciler dispatch. The agent runs steps 1–10 sequentially, then terminates with `[SHUTDOWN]`.

**Exclusive substrate lock.** Step 7 (Application) acquires `.tropo-studio/reconciler/.lock` before any write. If lock is held, exits cleanly with a STATUS bulletin to `channels/ops.md`. Stale lock (mtime > 1 hour) is overridden with a WARN bulletin.

**Categorize before applying.** Every event has a confidence value `[0.0, 1.0]` and a category (`routine` | `pattern-matched` | `judgment` | `blocking`). Apply boundary uses strict inequalities:

- `routine`: confidence `>= 0.95` → auto-apply silently
- `pattern-matched`: confidence in `[0.80, 0.95)` → auto-apply; surface in report's §Pattern-matched
- `judgment`: confidence in `[0.50, 0.80)` → defer to executive; surface in report's §Judgment
- `blocking`: confidence in `[0.0, 0.50)` → defer to user; surface in report's §Blocking

**Hash function fallback chain.** Per arch-spec §C.5 Rule 6 — try stable-identifier first (Office docProps/core.xml dc:identifier; PDF /ID); fall back to content-aware hash (XML payload + SHA-256); fall back to plain SHA-256. Record `hash_function:` per file.

**Audit log every event.** Every event (applied or deferred) writes a row to `.tropo-studio/reconciler/journal.jsonl` per the row schema in arch-spec §C.8. Reversibility classification per arch-spec §C.8 reversibility table.

**Conservative posture on ambiguity.** When in doubt, mark as judgment or blocking; never silently consolidate UIDs; never silently destroy substrate. The `surface_to_user` action is the safe default.

---

## Resources

### Required Reads

| Resource | Purpose |
|---|---|
| Activation record commissioning prompt | Scope, trigger_path, executive context |
| `.tropoignore` at Studio root | Exclusion rules for the scan |
| Recent `journal.jsonl` rows (last 30 days; tail-read) | Last-known state for delta detection |
| Pattern catalog (in this playbook §Step 5) | Pattern recognition rules |

### Tools Invoked

| Tool | Step | Purpose |
|---|---|---|
| `import-walker.py scan` | 2 | Enumeration; UID-to-state map |
| `import-walker.py apply` | 7 | Per-event application (writes) |
| Internal hash routines | 3 | Hash function per §C.5 Rule 6 |
| JSONL append | 8 | Audit log writes |

### Produces

| Output | Step |
|---|---|
| Structured `reconcile-report` instance | 9 |
| Append-only journal entries | 8 |
| Substrate changes (sidecar/projection writes) | 7 |
| `[SHUTDOWN]` on activation record | 10 |

---

## Steps

### Step 1 — Scope Resolution

**Executor:** sa.reconciler (agent decision; no tool call)

Read the commissioning record's `[RESPONSE]` block for:
- `scope:` — `full-studio` | `folder:<path>` | `operation:<uid>`
- `trigger_path:` — `anomaly` | `scheduled` | `user-invoked`
- `executive:` — the persona that commissioned this run

If `scope` is `operation:<uid>`, resolve the operation to its concrete folder/file targets (e.g., a user-invoked "promote folder X" operation has `<path>` embedded).

Output: bounded scope for Step 2 enumeration.

---

### Step 2 — Enumeration

**Executor:** sa.reconciler invokes `import-walker.py scan --scope <...>` + (v1.1) reads working-copy + template vault entries directly

**v1.0 binary-layer walks** (unchanged):
Walk all `.tropo-studio/*.tropo.md` sidecars in scope (recursive). Walk all source files in governed folders in scope (recursive; respecting `.tropoignore`). Walk all `vault/files/<uid>.md` (Tier 1) + `vault/files/<uid>/metadata.md` (Tier 2) projections with `type: external-artifact` in scope.

Output (v1.0 binary-layer): three lists — `sidecars[]`, `source_files[]`, `projections[]`. Each entry carries: path, UID (from frontmatter or filename), filesystem mtime, filesystem size.

**v1.1 derived-artifact-layer walk (NEW — per arch-spec §3.8 layering fix):**

Walk SEPARATELY all `vault/files/<uid>.md` entries with `type: working-copy` in scope. Walk SEPARATELY all `vault/files/<uid>.md` entries with `type: docx-template` in scope. These walks operate at the **derived-artifact layer** (working-copies are derived from projections; templates are derived from user-uploaded binaries) — distinct from the binary layer the v1.0 walks cover.

Output (v1.1 derived-artifact-layer): two additional lists — `working_copies[]` and `templates[]`. Each entry carries: path, UID, frontmatter shape per the respective capsule, `derived_from:` (for working-copies) or `template_binary_path:` (for templates).

**Why two separate walks instead of one merged walk:** the v1.0 binary-layer walks produce 7 raw delta types (move, rename, content-change, orphan-source, orphan-sidecar, duplicate-UID, new-uncompanioned-file) that operate on filesystem + binary state. The v1.1 derived-artifact-layer walks produce different delta types (working-copy-source-drift, template-binary-drift) that operate on frontmatter-recorded hash state. Mixing the abstraction layers would force §Step 4 to discriminate by delta source — cleaner to keep the layers separate at enumeration.

---

### Step 3 — Hash Computation

**Executor:** sa.reconciler invokes `import-walker.py` internal hash routines

For each source file in scope, compute hash per the fallback chain:

1. **Stable-identifier:** if extension is `.docx`/`.xlsx`/`.pptx`, open as ZIP + read `docProps/core.xml` + extract `dc:identifier`. If extension is `.pdf`, read PDF trailer + extract `/ID` array. Record `hash_function: stable-id`.
2. **Content-aware fallback:** if no stable identifier found, extract XML payload from ZIP + SHA-256 the payload. Record `hash_function: content-aware`.
3. **Plain SHA-256 fallback:** if the above fails (not an Office binary or PDF; or content extraction fails), SHA-256 the file bytes. Record `hash_function: sha256`.

Output: `source_file_hashes[]` mapping each source path to `(hash, hash_function)`.

---

### Step 4 — Delta Detection

**Executor:** sa.reconciler (agent decision based on Step 2 + Step 3 outputs)

Build a UID-to-current-state map. Compare against last-known state from recent journal entries (or from sidecar frontmatter `modified` + `source_hash` if no recent journal entries for the UID). Categorize raw deltas.

**v1.0 binary-layer raw delta types** (unchanged):

- **move** — UID's sidecar path changed; hash unchanged
- **rename** — sidecar path stable but the `<filename>` portion changed; hash unchanged (same-folder)
- **content-change** — UID's hash changed
- **orphan-source** — source file present without corresponding sidecar
- **orphan-sidecar** — sidecar present without corresponding source file
- **duplicate-UID** — same UID found at two different sidecar locations (likely `cp -r` copy)
- **new-uncompanioned-file** — source file in governed folder with no sidecar AND not matching any orphan sidecar by hash

**v1.1 derived-artifact-layer raw delta types (NEW):**

- **working-copy-source-drift** — a `type: working-copy` instance whose `derived_from: [<projection-uid>]` source projection's source binary now has a different hash than the working-copy's `last_source_hash_seen:` field. Carries: `working_copy_uid`, `projection_uid`, `source_path`, `hash_before` (the working-copy's recorded `last_source_hash_seen:`), `hash_after` (the freshly-computed current binary hash), `hash_function` (the recorded function used at extraction). **Hash-function semantics (per arch-spec §3.8 closing sa.skeptic-006 P1-4):** when the working-copy's recorded `hash_function:` is `stable-id`, detection MUST recompute using the SAME hash function chain that was used at extraction; the journal row additionally records `drift_detection_caveat: "stable-id may under-detect content drift; consider content-aware reconfirmation if user reports surprise"` for forensic clarity. When `hash_function:` is `content-aware` or `sha256`, drift detection is precise and no caveat is recorded.

- **template-binary-drift (v1.2 ACTIVATED)** — a `type: docx-template` instance whose `template_binary_path:` resolves to a binary with SHA-256 different from the entry's `template_binary_hash:`. Carries: `template_uid`, `template_binary_path`, `hash_before` (the entry's recorded `template_binary_hash:`), `hash_after` (current binary SHA-256). Detection is straightforward — template binaries hash deterministically with SHA-256; no fallback chain. Activated at v1.28.0 Stream C per arch-spec §3.8 v0.5 (was reserved-deferred at v1.1).

- **folder-mirror-orphan-state (v1.2 NEW per arch-spec §3.8 v0.5 — closes sa.skeptic-008 P1-1 + sa.cold-boot-007 B2)** — emitted when the reconciler detects partial state from an interrupted `create-sidecar` co-write. Two sub-states: `orphan_tmp_mirror` (a `vault/files/<uid>.md.tmp` file exists with no matching `<uid>.md` finalized — process died after .tmp write but before atomic-rename); `marker_without_mirror` (an on-disk `.tropo-folder.md` marker exists with no matching `vault/files/<marker-uid>.md` mirror — pre-v0.4 import OR mid-write process-death recovery). Carries: `folder_path`, `observed_state` (one of the two sub-states), `marker_uid` (when known). Resolution path: reconciler re-runs the mirror co-write deterministically using the marker's existing UID (retro-fill semantics per arch-spec §3.5.5 Amendment 1 v0.5); if marker is also absent, surfaces as judgment for user resolution.

**Folder-mirror UID-duplication is a SANCTIONED exception (v1.2 per arch-spec §3.8 v0.5 — closes sa.skeptic-008 P0-2):** the existing v1.0 `duplicate-UID` raw delta rule treats same-UID-at-two-paths as a copy event requiring resolution. The v0.4 folder-marker mirror pattern (per arch-spec §3.5.5 Amendment 1) deliberately writes the SAME UID at two paths (on-disk `.tropo-folder.md` + vault `vault/files/<uid>.md`) — this is a sanctioned dual-residence pattern, NOT a duplicate. Detection rule:

> When both files carry the SAME UID **AND** one declares `mirror_of: <same-uid>` (self-reference) **AND** declares `folder_marker_path:` pointing at the other, the reconciler treats the pair as a single governed entity (skip `duplicate-UID` event emission for this UID-pair).

Any other same-UID-at-two-paths state remains a `duplicate-UID` event per the v1.0 rule. The §3.10 check 8 NEW validator (v1.28.0 Stream D) binds the integrity contract: `mirror_of:` self-reference resolves; `folder_marker_path:` resolves; UIDs match; both files carry consistent `title:` + `source_folder_name:` + `original_path:`.

Output: `raw_deltas[]` with each delta typed + carrying before/after state. Binary-layer + derived-artifact-layer deltas pass through to §Step 5 together; pattern recognition is per-delta-type regardless of layer.

---

### Step 5 — Pattern Recognition

**Executor:** sa.reconciler (agent interpretive work)

Compress raw deltas into fewer-but-richer events by matching the pattern catalog:

**Initial Pattern Catalog (v1.0; extensible):**

| Pattern | Detection Rule | Compressed Event |
|---|---|---|
| **folder-relocation** | ≥5 raw deltas of type `move` with consistent path prefix change + identical hashes for each | One event: "folder X moved to Y; N files; UIDs preserved" |
| **cp-r-duplicate** | ≥5 `duplicate-UID` deltas where all duplicates share a common path prefix not present at source | One event: "folder X duplicated to Y; mint new UIDs in destination" |
| **batch-edit-session** | ≥3 `content-change` deltas within same folder + same 5-minute window | One event: "batch edit session in folder X; N files content-changed" |
| **sidecar-folder-cleanup** | ≥3 `orphan-sidecar` deltas in same folder + no corresponding orphan-sources | One event: "user removed .tropo-studio/ in folder X; recover via journal history" |
| **share-drop-batch-import** | ≥3 `new-uncompanioned-file` deltas in same folder + same file type | One event: "batch of N <type> files added to folder X; sidecar via auto-index" |
| **rename-same-folder** | One `orphan-sidecar` + one `new-uncompanioned-file` in same folder with matching hash | One event: "file renamed within folder; sidecar updated" |

Unmatched raw deltas pass through as their own events.

**v1.1 derived-artifact-layer deltas pass through as their own events.** `working-copy-source-drift` is NOT subject to pattern compression — no pattern in the v1.0 catalog applies. It advances to §Step 6 as a raw event of its own type. The phrase "pass through" means: §Step 5 does NOT match the delta against the pattern catalog; the delta advances to §Step 6 with the same delta-type name.

**v1.2 derived-artifact-layer deltas pass through as their own events.** `template-binary-drift` and `folder-mirror-orphan-state` follow the same convention — neither matches a v1.0 pattern; both advance to §Step 6 as raw events of their own type.

Output: `events[]` — each event named (pattern or raw type) + carrying its compressed evidence.

---

### Step 6 — Categorization

**Executor:** sa.reconciler (agent decision)

For each event, assign:

- **Category** per the boundary inequalities (see §Rules above)
- **Confidence** based on the rules below
- **Proposed action** (one of: `create_sidecar`, `move_sidecar_path`, `update_sidecar_metadata`, `delete_sidecar`, `create_projection`, `update_projection`, `mint_new_uid`, `surface_to_user`, plus reversibility tags per arch-spec §C.8)
- **Evidence** — paths, hashes, before/after state, pattern_match value

**Confidence assignment rules:**

| Event type | Default Confidence | Notes |
|---|---|---|
| folder-relocation (pattern) | 0.92 | High confidence; structural pattern; non-overlap with cp-r |
| cp-r-duplicate (pattern) | 0.85 | Conservative; ambiguous with move-with-leftover; surface ambiguity if hashes don't all match |
| rename-same-folder (pattern) | 0.93 | Hash-stable single-file rename; well-handled |
| batch-edit-session (pattern) | 0.97 | Content-change is expected user behavior; high confidence routine |
| sidecar-folder-cleanup (pattern) | 0.40 | Blocking — user did something destructive; never silently recreate UIDs |
| share-drop-batch-import (pattern) | 0.96 | New files; auto-index is the right action; high confidence routine |
| move (raw, unmatched) | 0.96 | Hash-stable individual move |
| rename (raw, unmatched) | 0.93 | Hash-stable individual rename |
| content-change (raw, unmatched) | 0.96 | Routine; hash drift |
| orphan-source (raw, unmatched) | 0.45 | Surface to user; could be intentional re-import, fresh content, or stranded source |
| orphan-sidecar (raw, unmatched) | 0.40 | Surface to user; could be sidecar-deleted, source-deleted, or move-without-sidecar |
| duplicate-UID (raw, unmatched) | 0.55 | Judgment; likely copy operation but ambiguous; mint new UID in destination as default |
| new-uncompanioned-file (raw, unmatched) | 0.97 | Auto-index; routine |
| **working-copy-source-drift (v1.1 — derived-artifact layer)** | **0.55** | **Judgment — drift may be benign (glance-open in Word) or material (substantive edit). Reconciler can't tell. Boundaries are strict-inequality per §Rules — judgment is `[0.50, 0.80)`; 0.55 is safely in range. Never silently apply. Proposed action: `surface_to_user` with refresh/keep resolution paths. Reconcile-report §Judgment carries the event.** |
| **template-binary-drift (v1.2 ACTIVATED)** | **0.50** | **Judgment-boundary — surfaces but does NOT auto-apply. The user decides at next `tropo-export.py --template <uid>` invocation per arch-spec §3.7 precondition 3 prompt-then-proceed (three resolution paths: `accept-and-export` → record drift_accepted + update template's recorded hash; `re-register` → invoke `tropo-register-template.py --force`; `abort` → user resolves manually). Validator §3.10 check 2 stays WARN-severity (rebuild does not refuse on drift); export tool surfaces at runtime. Proposed action: `surface_to_user`. Reconcile-report §Judgment carries the event.** |
| **folder-mirror-orphan-state (v1.2 NEW)** | **0.55** | **Judgment — partial-write state from interrupted create-sidecar co-write. Reconciler-deterministic resolution: re-run mirror co-write using the marker's existing UID (retro-fill semantics per arch-spec §3.5.5 Amendment 1 v0.5). For `orphan_tmp_mirror` sub-state (orphan .tmp file): delete the .tmp + re-author from current marker. For `marker_without_mirror` sub-state: author the missing mirror via retro-fill. Proposed action: `surface_to_user` with default `auto_resolve` button (since reconciler-deterministic) — executive may apply directly OR hand to user for review.** |

**Rename-with-overwrite case (arch-spec §A.9 fault line 3):** detect when orphan-sidecar's recorded hash matches a new source's hash AND that source has an existing-but-stale sidecar at the same path. Force this to `blocking` category (confidence 0.30); surface to user with `proposed_user_question`.

Output: `events[]` augmented with category + confidence + proposed action + evidence.

---

### Step 7 — Application

**Executor:** sa.reconciler invokes `import-walker.py apply --operation <event-json>` per event

Acquire lock at `.tropo-studio/reconciler/.lock` (if not already held). Apply each `routine` + `pattern-matched` event by invoking `import-walker.py apply` with the event payload. Skip `judgment` and `blocking` events (those defer to executive).

For each applied event:
- Tool performs the substrate write (sidecar move, projection update, etc.)
- Tool returns success or error
- On error: mark event as `applied: false`, `deferred_reason: <error>`, surface to executive

Output: list of `applied_events[]` + `deferred_events[]`.

---

### Step 8 — Audit Log Write

**Executor:** sa.reconciler invokes JSONL append for each event

For every event in `applied_events[]` + `deferred_events[]`, append a row to `.tropo-studio/reconciler/journal.jsonl` per the arch-spec §C.8 row schema. Each row carries:

- `event_uid`, `timestamp`, `run_uid`, `executive`, `trigger_path`
- `action`, `reversible`, `category`, `confidence`, `target_uid`, `pattern_match`
- `hash_function`, `before`, `after`, `evidence`
- `applied`, `applied_at`, `deferred_reason`

Reversibility per the arch-spec §C.8 table: `mint_new_uid` and `surface_to_user` are non-reversible; all others are reversible.

Output: journal updated; `audit_log_range:` (first + last event_uid for this run) recorded for the report.

---

### Step 9 — Report Composition

**Executor:** sa.reconciler authors the `reconcile-report` instance

Author a new `reconcile-report` instance per the schema at [reconcile-report.capsule v1.0 (013b7b6e)](../files/013b7b6e.md). Includes:

**Frontmatter:**
- Core: uid, type, status, title, owner, created, modified
- Reconciler-specific: run_uid, executive, trigger_path, scope, started_at, completed_at, total_deltas_detected, total_events_after_pattern_match, events_by_category, events_applied, events_deferred, schema_version
- Optional: description, pattern_catalog_version (= "1.0" for v1.25.0 ship), audit_log_range

**Body (four required sections, in order):**
- `## Routine` — applied events; one-line summaries; `(none)` if empty
- `## Pattern-matched` — applied events with context; pattern_name + brief evidence; `(none)` if empty
- `## Judgment` — deferred to executive; full description + evidence + proposed action + confidence + rationale; `(none)` if empty
- `## Blocking` — deferred to user; full description + candidate interpretations + proposed_user_question + confidence; `(none)` if empty

Optional `## Run Telemetry` if useful for forensics.

Output: report file authored; path returned to commissioning executive.

---

### Step 10 — Handoff + Shutdown

**Executor:** sa.reconciler writes [SHUTDOWN] to activation record

Append the report's UID + path to the activation record's `[WORK]` block. Write `[SHUTDOWN]` line with timestamp. sa.reconciler terminates.

Executive picks up the report; triages per §A.7 + §C.5 of the arch-spec; composes user-facing response if needed.

---

## Failure Handling

| Failure | Response |
|---|---|
| Lock held by another reconciler | Exit cleanly; STATUS bulletin to channels/ops.md; defer to lock-holder |
| Stale lock (mtime > 1 hour) | Override with WARN bulletin to channels/ops.md; proceed |
| import-walker.py error during apply | Mark event as deferred; continue with remaining events; surface error in §Blocking |
| journal.jsonl write failure | HALT; surface CRITICAL to channels/alerts.md; substrate may be in inconsistent state |
| Tool unavailable / Python error | HALT; surface CRITICAL to channels/alerts.md; this pass terminates without producing a report |
| Activation record [RESPONSE] missing scope | Request clarification via additional [QUERY]; if no response in reasonable window, terminate with [SHUTDOWN] + skip-reason |

---

## Composability

This playbook composes with:

- **[sa.reconciler activation file](../../agents/sa/sa.reconciler/sa.reconciler.md)** — the agent that runs this playbook
- **[import-walker.py (bf886f30)](../files/bf886f30.md)** — the primary tool invoked at Steps 2 + 3 + 7
- **[scan-import-state.py (0a316ca6)](../files/0a316ca6.md)** — optional pre-pass tool for fast scope reduction
- **[external-artifact.capsule v1.0 (eedd7034)](../files/eedd7034.md)** — the type sa.reconciler reads + writes
- **[reconcile-report.capsule v1.0 (013b7b6e)](../files/013b7b6e.md)** — the output schema this playbook authors against
- **fleet-ops.playbook** (registry extension in v1.25.0 Stream D) — scheduled trigger source
- **agent-activation.playbook** (Group 3 amendment in v1.25.0 Stream D) — anomaly-driven trigger source
- **[Import Primitive Architecture Specification v1.0 LOCKED (2b49ba79)](../files/2b49ba79.md)** — the architectural foundation this playbook implements

---

## Versioning

Playbook version bumps when:

- New patterns added to Step 5 catalog (semver minor)
- Confidence threshold tuning (semver minor; recorded in changelog)
- Step structure changes (semver major)

Each `reconcile-report` instance records the `pattern_catalog_version` it ran against — supports forensic replay even when the playbook has since evolved.

---

## Changelog

| Version | Date | Change | Author |
|---|---|---|---|
| 1.0 | 2026-05-13 | **LOCKED.** Initial playbook authored in v1.25.0 Stream C per locked arch-spec [2b49ba79](../files/2b49ba79.md) §A.4 + §C.5. 10 steps; initial 6-pattern catalog; strict-inequality confidence boundaries; hash function fallback chain; rename-with-overwrite blocking rule; lock + stale-lock + concurrency model; structured report composition. Three-instrument verification: Argus build (this pass); sa.cold-boot + sa.skeptic via Stream G gauntlet pending. | argus-a60 |
| 1.1 | 2026-05-13 | **LOCKED.** Additive amendment per [arch-spec 5a89297a v0.3](../files/5a89297a.md) §3.8 — v1.26.0 Stream C deliverable. §Step 2 extended with derived-artifact-layer walk (separate from binary-layer; type:working-copy + type:docx-template enumeration). §Step 4 extended with `working-copy-source-drift` raw delta type (judgment-class; honors hash_function semantics; carries drift_detection_caveat for stable-id under-detection cases). §Step 5 explicitly notes the derived-artifact delta passes through without pattern compression. §Step 6 categorization table extended with row for working-copy-source-drift at 0.55 judgment-class. `template-binary-drift` event reserved for v1.28.0 (not yet active). v1.0 behavior unchanged; existing sa.reconciler runs continue to operate. | argus-a61 |
| 1.2 | 2026-05-14 | **LOCKED.** Additive amendment per [arch-spec 5a89297a v0.5](../files/5a89297a.md) §3.8 v0.5 — v1.28.0 Stream C deliverable. Three changes. (1) `template-binary-drift` event ACTIVATED — was reserved-deferred at v1.1; now live at §Step 4 + §Step 6 (judgment-class 0.50; surface_to_user with three resolution paths per arch-spec §3.7 precondition 3). (2) NEW `folder-mirror-orphan-state` event (judgment-class 0.55; closes sa.skeptic-008 P1-1 + sa.cold-boot-007 B2): emitted on partial-write state from interrupted create-sidecar co-write; resolution is reconciler-deterministic retro-fill using marker UID per arch-spec §3.5.5 Amendment 1 v0.5. (3) Folder-mirror UID-duplication SANCTIONED EXCEPTION declared at §Step 4 (closes sa.skeptic-008 P0-2): existing v1.0 duplicate-UID rule now treats `mirror_of: <self-uid>` self-reference + matching `folder_marker_path:` as a sanctioned dual-residence pattern (skip duplicate-UID detection); composes with §3.10 check 8 NEW validator (Stream D). v1.0 + v1.1 behavior unchanged; v1.28.0 sa.reconciler runs detect template-binary-drift + folder-mirror-orphan-state in addition to prior delta types. | argus-a62 |

---

*Reconcile Imports Playbook v1.1 | LOCKED 2026-05-13 by argus-a61 (v1.1 amendment) + argus-a60 (v1.0 original) | UID 4a2f6dbd | v1.25.0 + v1.26.0 Stream C deliverable.*
*"Enumerate (binary + derived-artifact layers). Detect (typed deltas). Recognize (patterns). Categorize. Apply routine. Defer judgment. Surface blocking. Audit everything."*
