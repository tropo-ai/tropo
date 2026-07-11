---
skill: debug-manifest
name: debug-manifest
type: how-to
purpose: Diagnose and fix a manifest.yaml that fails validation during update apply
when: When the concierge halts on manifest validation and reports missing or malformed fields
uid: c3d4e5f6
status: active
owner: argus
created: 2026-04-15
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: Reach for this when the apply-update playbook (or similar concierge flow) halts with a manifest.yaml validation error — missing or malformed fields. The skill walks through the required-field checklist (version, update_id, update_type, target_version, min_compatible, summary), identifies what's missing or wrong, and produces a fixed manifest. Use during update package authoring or when troubleshooting a halted apply-update run.
subsystem_hub:
  - 76bab75f
---

# Debug a Manifest

Use this when the apply-update playbook halts with a manifest validation error.

## Step 1: Identify missing fields

The required fields are:

```yaml
version: 1 # Manifest spec version (integer)
update_id: "tropo-update-v0.X.X" # Package folder name
update_type: "patch|feature|release|security"
target_version: "0.X.X" # Version after this update applies
min_compatible: "0.X.X" # Oldest vault version this works with
summary: "One-line description" # What this update does
released: "YYYY-MM-DD" # Release date
author: "author-name" # Who built it
operations: [...] # List of operations
verification: # How to verify
 test_playbook: "TEST.playbook.md"
 runner: "vault-steward"
 on_failure: "halt"
```

Compare your manifest against this shape. Add any missing fields.

## Step 2: Check operations

Each operation must have:
```yaml
- type: add|replace|edit|move|delete
 path: ".tropo/some-file.md" # Target in the user's vault
 source: "files/.tropo/some-file.md" # Payload inside the package (for add/replace)
 reason: "Non-empty explanation" # Why this operation exists
```

Common errors:
- Missing `reason:` (every operation needs one)
- `source:` path that doesn't match a file in `files/` (path mismatch)
- `path:` pointing outside `.tropo/` or `system/` without an explicit `edit_user_file` flag

## Step 3: Check migrations (if present)

Each migration entry must have:
```yaml
migrations:
 - id: "migration-name"
 path: ".tropo/playbooks/migrations/migration-name.playbook.md"
 scope: "agents/**" # What the migration walks
 reason: "What this migration does"
 order: 1 # Execution order
```

The migration playbook file must exist at `files/<path>` inside the package and must conform to Playbook Spec v1.0 (six sections).

## Step 4: Re-validate

After fixing, read the manifest back and check:
- [ ] All 10 required top-level fields present
- [ ] Every operation has `type`, `path`, `reason`
- [ ] Every `source:` path has a matching file in `files/`
- [ ] `min_compatible` is <= `target_version`
- [ ] `update_type` is one of: `patch`, `feature`, `release`, `security`

## Step 5: Report

If you are the vault concierge and the user gave you a broken package:
1. Write a diagnostic file to `system/updates/pending/<update_id>/validation-failure.md` with the exact errors and what was fixed (or needs fixing by the package author).
2. Tell the user: "This is a problem with the update package, not your vault. Nothing was changed." Then either fix it if you can, or tell them to share the diagnostic with whoever provided the update.

## Success

The manifest passes validation and the apply-update playbook proceeds past Step 1.
