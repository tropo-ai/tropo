---
uid: 3ca544f2
title: 'Migrate: Backfill status field on content files'
migration_id: migrate-file-status
version: '1.0'
status: published
state: active
reactivated_at: '2026-07-02'
reactivated_by: talos-t23
reactivation_note: 'Re-validated against the One-Home boundary per Gate 2 (dev-spec fc4874f4) committed_substrate item 6 — "re-validation against the new boundary, not a rewrite of the migration logic" per the spec''s own framing. Scope glob updated to resolve under vault/ (agents/*/workspace/** stays outside vault/ per vault/AGENTS.md "What Does NOT Belong Here" — workspace scratch is not vault content, so it legitimately does not resolve under vault/; everything else re-pointed). Report paths re-homed system/updates/ -> vault/updates/. This migration remains conceptually live (status: fields are actively used vault-wide, unlike the dead 00-index.md convention migrate-index-format.playbook.md targets — see edf0da23 for that finding).'
archived_at: '2026-06-11'
archived_by: argus-a109
archive_reason: 'v1.69 S2 disposition: migrations/ playbooks are historical record, not live fleet (per the S2 disposition list; un-indexed kernel files so archived by direct frontmatter edit — the archive tool resolves by index). Superseded by the reactivation above.'
author:
  name: Tropo
  role: Framework
domain: system-maintenance
tags:
  - migration
  - v0.2.3
  - content-conventions
  - one-home
  - gate-2
created: '2026-04-05'
last_updated: '2026-07-02'
estimated_duration: 10-120 seconds (depends on vault size)
readers:
  - agent
spec_ref: design/update-spec-v1.1-amendment.md §14.3
scope: vault/files/**/*.md, vault/playbooks/**/*.md, agents/*/workspace/**/*.md
modes:
  - dry-run
  - commit
subsystem_hub:
  - 76bab75f
---

# Migration: Backfill `status: active` on Content Files

*v0.2.3 migration. Walks user-content scopes and adds `status: active` to frontmatter on any content file missing the field. Conservative default. Defensive on unexpected structure. Idempotent.*

*This playbook is invoked twice by the v0.2.3 pipeline: once by the concierge in `dry-run` mode during Review, and once by the apply-update playbook in `commit` mode during Step 3b after user approval of the dry-run diff.*

## Intent

The `status:` field on content files was introduced in v0.2.2 as part of the Content File Conventions schema (`.tropo/schema/content-file-conventions.md`). Files created after v0.2.2 have it. Files that predate v0.2.2 do not. This migration backfills the field with `status: active` — the conservative default — on every content file that lacks it.

Why `active` as the default:
- A file that exists in a user's workspace without a status field is, in the vast majority of cases, being actively used (or was last used as active content). `active` is the safe assumption.
- The alternative defaults (`draft` would imply pre-lock and may be wrong; `archived` would imply frozen and may be wrong) are both more likely to mislead future readers and downstream tooling.
- `active` is reversible — users (or agents) can correct individual files to `draft`, `superseded`, or `archived` after the migration, and the migration will not overwrite the correction on re-run (idempotency).

This migration implements the v0.2.3 scope item "file status backfill" from BOARD.md and is the first migration to exercise the v1.1 migration class end-to-end. It is deliberately narrow: one field, one conservative default, one reversible write per file.

## Suggestions

- Read the scope glob carefully before running. If the glob matches zero files (e.g., the vault has no agent workspaces yet), the migration is a valid no-op — log it cleanly and return a PASS with `files_walked: 0, files_changed: 0`.
- Treat every "file I can't parse" as a defensive skip, not a halt. Malformed frontmatter, missing frontmatter entirely, weird YAML, encoding issues — all log-and-skip with the reason. The pipeline continues. Halting-on-unexpected is the wrong default for migrations per v1.1 §14.3.
- The difference between dry-run and commit is writes, nothing else. Both modes walk the full scope, parse every file, compute the diff, and write a §14.3.2-format report. Dry-run stops before writing the backfill. Commit writes the backfill and then writes the report.
- Idempotency is achieved at the per-file level: if a file already has `status:` set to any value (including `active`), skip it with reason "already-has-status". The migration does not modify existing values. Running the migration twice produces the same result as running it once.
- The out-of-scope file type exclusion list (`schema`, `template`, `charter`, `agent`, `system`) must match the vault steward's Function 7 scope list. If the steward changes, update this playbook. If this playbook changes, update the steward. They are two sides of the same convention enforcement.

## Rules

**Scope rules (v1.1 §14.3):**

- **You MUST walk ONLY the paths matching the declared scope glob.** The declared scope covers user/studio content under One Home: `vault/files/`, `vault/playbooks/`, plus agent workspaces (which legitimately live outside `vault/` per `vault/AGENTS.md` "What Does NOT Belong Here" — workspace scratch is not vault content). Never walk outside this scope. Never walk `.tropo/` — it is the OS bootstrap floor (Namespace Predicate category (b), REPLACE-only via discrete update operations, never a migration target). Never walk `vault/tropo-*` — OS components (Namespace Predicate category (a)). Never walk `archive/` — archived files are frozen by design.
- **You MUST skip files whose `type:` field is in the out-of-scope list:** `schema`, `template`, `charter`, `agent`, `system`. These are governed files, not content files, and they follow kernel conventions rather than content conventions.
- **You MUST NOT write to files outside the scope glob under any circumstances.** Every write is audited in the migration report with the absolute file path. If the file's path does not match the declared scope, the write is a governance boundary violation and the migration MUST halt with classification `governance`.

**Idempotency rules:**

- **A file that already has a `status:` field (any value) MUST be recorded as a skip with reason "already-has-status".** Do NOT modify the existing value, even if the value is a canonical value like `active`.
- **A file with no frontmatter at all MUST be recorded as a skip with reason "no-frontmatter".** Do NOT create frontmatter. Files without frontmatter are governed by their own rules (they are usually binary-ish or non-structural content) and this migration does not apply to them.
- **A file with frontmatter but no `type:` field MUST be recorded as a skip with reason "no-type-field".** The `type:` field is required for this migration to determine whether the file is in scope. Without it, the file is ambiguous and the safe default is to skip.
- **A file whose `type:` is in the out-of-scope list MUST be recorded as a skip with reason "out-of-scope-type: <type>".** These are explicitly excluded by the scope rules above.

**Defensive skip rules (v1.1 §14.3, required):**

- **Malformed YAML frontmatter** (parse error) — log-and-skip with reason "malformed-frontmatter: <parse error>". Do NOT halt.
- **File unreadable** (permission denied, not found mid-walk, etc.) — log-and-skip with reason "unreadable: <error>". Do NOT halt.
- **Encoding issue** (non-UTF-8 content) — log-and-skip with reason "encoding-error: <error>". Do NOT halt.
- **Frontmatter present but not a YAML mapping** (e.g., list, scalar) — log-and-skip with reason "non-mapping-frontmatter". Do NOT halt.
- **You MUST NOT halt on any content-shape issue.** Halting is reserved for: filesystem errors affecting the scope walk itself (not individual files), governance boundary violations, unrepresentable state.

**Mode rules:**

- **In `dry-run` mode**, walk the full scope, parse every file, classify each file (would-change / would-skip / error), but DO NOT write backfills. Write the dry-run report at the path the concierge expects (see Resources below). Return the result.
- **In `commit` mode**, walk the full scope, parse every file, classify each file, AND write the backfill on every file classified as "would-change". After writing each backfill, verify the file's frontmatter now has `status: active`. Write the commit report at the path the apply-update playbook expects (see Resources below). Return the result.
- **The classification logic MUST be identical between modes.** A file classified as "would-change" in dry-run MUST be classified as "will-change" / "changed" in commit, assuming no divergence. If the two classifications differ on the same file between dry-run and commit, the apply-update playbook's divergence check (Step 3b.2) will halt the migration. Do not introduce mode-dependent classification logic.

**Write rules (commit mode only):**

- **The write MUST be surgical.** Read the file, parse the YAML frontmatter, add ONLY the `status: active` field to the frontmatter mapping, serialize the frontmatter back, and write the file. Do NOT modify any other frontmatter field. Do NOT modify the content body. Do NOT reformat the YAML.
- **Field ordering:** append the `status:` field after the last existing field in the frontmatter. Do not reorder existing fields. Agents (and humans) have visual memory of where fields live in frontmatter; preserve it.
- **Post-write verification:** after writing, re-read the file's frontmatter and confirm `status: active` is present. If the verification read fails (field missing, value different), record the file as an error with reason "write-verification-failed" and continue. Do NOT retry the write.

**Report rules (both modes, required per v1.1 §14.3.2):**

- **Write the report using the §14.3.2 format exactly.** Required frontmatter: `migration_id`, `scope`, `run_mode`, `run_date`, `files_walked`, `files_changed`, `files_would_change` (dry-run only), `files_skipped`, `files_errors`, `result`. Required body sections: Summary, Files Changed (or Would Change), Files Skipped, Errors, Classification (on failure only).
- **Dry-run report location:** `vault/updates/pending/<update_id>/dry-run-reports/migrate-file-status.md`. The concierge reads from this path at Step 3 Review. The apply-update playbook reads from this path at Step 1c validation and Step 3b.1 divergence check.
- **Commit report location:** `vault/updates/pending/<update_id>/migrate-file-status-commit-report.md` (flat, top-level inside the update folder). The apply-update playbook reads this at Step 3b.4 for result classification. After the update promotes to `applied/`, the report travels with it.
- **The Summary section must be plain-language, readable by a non-technical user.** Example: "Walked 147 files across 3 agent workspaces. 47 would gain a `status: active` backfill. 100 already have a status field and will be skipped. 0 errors."

## Resources

### Knowledge Base

- `vault/files/2b5a3dd5.md` — Playbook Spec v1.0, the six-section format
- `.tropo/schema/content-file-conventions.md` — the content file convention this migration enforces (v0.2.2)
- `.tropo/system/vault-steward.template.md` Function 7 — the steward's auto-repair behavior for the same convention (runs outside of updates)

### Files You Will Read

- Every file matching the scope glob (agent workspaces, projects, decisions, tasks, playbooks content)
- Each file's YAML frontmatter only (content body is not needed for this migration)

### Files You May Write (commit mode only)

- Files inside the scope glob, frontmatter only, `status: active` field appended
- `vault/updates/pending/<update_id>/dry-run-reports/migrate-file-status.md` (dry-run mode)
- `vault/updates/pending/<update_id>/migrate-file-status-commit-report.md` (commit mode)

### Files You MUST NOT Write

- Any file inside `.tropo/` (OS bootstrap floor — Namespace Predicate category (b))
- Any file matching `vault/tropo-*` (OS component — Namespace Predicate category (a))
- Any file inside `archive/`
- Any file outside the declared scope glob
- Any file whose `type:` is in the out-of-scope list (schema, template, charter, agent, system)
- The body of any file (frontmatter only)
- Any frontmatter field other than `status:`

## Outcomes

- [REQUIRED] Every file matching the scope glob has been walked and classified as one of: would-change / skip-already-has-status / skip-no-frontmatter / skip-no-type-field / skip-out-of-scope-type / skip-malformed-frontmatter / skip-unreadable / skip-encoding-error / skip-non-mapping-frontmatter / error-write-verification-failed.
- [REQUIRED] (commit mode) Every file classified as "would-change" has had `status: active` appended to its frontmatter. Every such write has been verified by re-reading the file.
- [REQUIRED] A §14.3.2-format report has been written at the correct path for the current mode.
- [REQUIRED] No file outside the scope glob has been modified under any circumstance.
- [REQUIRED] No file inside `.tropo/`, `vault/tropo-*`, or `archive/` has been modified under any circumstance.
- [REQUIRED] No frontmatter field other than `status:` has been modified on any file.
- [REQUIRED] No content body has been modified on any file.
- [REQUIRED] The migration's result field in the report is one of: `PASS` (zero errors, regardless of skip count), `PARTIAL` (some files changed, but a halt-worthy error occurred mid-run), `FAIL` (halt-worthy error before any change was attempted).
- [REQUIRED] On PASS: every file the dry-run said would change has been changed in commit (assuming no divergence detected by apply-update Step 3b.2).

## Verification

### Method

Self-attestation at the end of the run. The apply-update playbook's Step 3b.4 reads the report's `result:` field and classifies the commit result. The vault steward's verification (TEST.playbook.md) reviews the report as part of v1.1 §14.3.2 verification.

### Criteria

- Report exists at the correct path for the current mode
- Report frontmatter has all required §14.3.2 fields
- Report body has all required §14.3.2 sections
- `files_walked` equals the count of files matching the scope glob (minus any filesystem errors on the walk itself)
- `files_changed` + `files_skipped` + `files_errors` equals `files_walked`
- (commit mode) for every file in "Files Changed", re-reading the file shows `status: active` in frontmatter
- (commit mode) for every file NOT in "Files Changed", the file's frontmatter is unchanged from before the run
- No file outside the scope glob has been touched (cross-check against filesystem mtimes if possible)
- Result is `PASS`, `PARTIAL`, or `FAIL` — never missing, never a different value
- If result is `FAIL` or `PARTIAL`, a Classification section is present with one of: `migration-logic`, `content-shape`, `governance`

### Escalation on Failure

- **Scope glob matches zero files:** valid no-op. Write report with `files_walked: 0, files_changed: 0, result: PASS`. Plain-language summary notes that the vault has no content in the scope. Not a failure.
- **Filesystem error during scope walk itself** (not an individual file — the walk itself fails): halt with `result: FAIL`, classification `migration-logic`, error message in the report. The concierge or apply-update playbook halts the pipeline per its own halt protocol.
- **Write verification failure on an individual file** (commit mode): record the file as an error with reason "write-verification-failed". Continue the walk. The final result is `PARTIAL` if any other files changed successfully, `FAIL` if this was the only file in scope. Classification: `migration-logic`.
- **Attempted write outside scope:** THIS MUST NOT HAPPEN. If it is detected, halt immediately with `result: FAIL`, classification `governance`. This is a migration bug and requires fixing the playbook itself before the update can re-run.
- **Divergence detected by apply-update Step 3b.2** (not by this playbook — by the runtime): this playbook is not re-invoked. The apply-update playbook halts the migration phase. This playbook has no responsibility for divergence handling beyond producing consistent classification between dry-run and commit.

---

*Migration: Backfill `status: active` on Content Files | v0.2.3 | Published (G27 draft, promoted by G28)*
*"One field. One conservative default. One reversible write per file. Idempotent. Defensive. Bounded."*
