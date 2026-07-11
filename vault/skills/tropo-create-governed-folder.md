---
skill: create-governed-folder
name: create-governed-folder
type: how-to
purpose: Create a new folder with proper governance — AGENTS.md, CAPSULE.md, 00-index.md
when: When creating any new subfolder in the vault, or when importing external files into a new folder
uid: b2c3d4e5
status: active
owner: argus
created: 2026-04-15
modified: 2026-05-09
modified_by: argus-a53
governed_by: a7c3f489
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: 'Reach for this whenever you create a new folder in the vault — ensures the folder ships with proper governance from creation: AGENTS.md (universal write-rules pointer; identical in every folder), CAPSULE.md (folder-specific governance contract; declares who can write, what belongs, what protocols), 00-index.md (4-column folder catalog). The Tropo three-tier governance model (TROPO-CONTROL → STUDIO → CAPSULE) requires every folder to declare its CAPSULE; this skill enforces that at folder creation rather than discovering the gap later.'
subsystem_hub:
  - 8dd772a0
---

# Create a Governed Folder

Use this whenever you create a new folder that will contain files.

## Steps

1. **Create the folder.** Make the directory at the desired path.

2. **Copy AGENTS.md.** Copy `vault/templates/AGENTS.md` into the new folder. Do not modify it — it is identical in every folder.

3. **Create CAPSULE.md.** Use `vault/templates/CAPSULE.md` as a starting point. Fill in the frontmatter:
 ```yaml
 ---
 spec_version: 2
 tier: capsule
 folder_type: <workspace|governed|registry|content|archive|sprint|package|system-agent>
 owner: <your-agent-name or the human owner>
 write_access: [<who can write here>]
 read_access: all
 purpose: "<one line — what is this folder for?>"
 uid: <generate with openssl rand -hex 4>
 ---
 ```
 Write a 1-3 sentence body describing the folder's purpose. Only add `## Operating Logic` or `## Override Declarations` sections if this folder has rules that differ from `STUDIO.md` defaults.

4. **Create 00-index.md.** Add a standard index with the four-column format:
 ```markdown
 # <Folder Name> — Index

 | Path | Type | Status | Description |
 |------|------|--------|-------------|
 | AGENTS.md | governance | — | Tropo-OS folder entry point |
 | CAPSULE.md | governance | active | Folder governance and operating logic |
 ```

5. **Create `.tropo-capsule/`.** Create a `.tropo-capsule/` subfolder inside the new folder. This is the folder's operational plumbing — hidden infrastructure for memory, local indexes, and grooming agent output. If the folder will have agents that accumulate memory, also create `.tropo-capsule/memory/` with an empty `MEMORY.md` index.

6. **Register CAPSULE.md.** Use the `register-file` skill to add the CAPSULE.md to `.tropo-studio/registries/agent-registry.yaml`. (AGENTS.md does not get a registry entry — it has no UID by design.)

7. **Log to ops.** Append to `channels/ops.md`:
 ```
 [YYYY-MM-DD HH:MM] <your-agent-id> — Created governed folder <path>. CAPSULE.md UID: <uid>.
 ```

## Success

The folder contains AGENTS.md (thin template), CAPSULE.md (with UID and frontmatter), and 00-index.md. CAPSULE.md is projected into `vault/00-index.jsonl` automatically on the next `python3 vault/tools/tropo-rebuild-vault.py --apply`. The creation is logged in `channels/ops.md`.
