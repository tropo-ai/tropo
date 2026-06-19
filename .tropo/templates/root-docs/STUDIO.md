---
spec_version: 2
tier: vault
vault_md_version: 1
vault_name: "<FILL: Your Vault Name>"
vault_owner: "<FILL: Your Name>"
created: "<FILL: YYYY-MM-DD>"
last_updated: "<FILL: YYYY-MM-DD>"
last_reviewed_by: "<FILL: name, YYYY-MM-DD>"
---

# Vault Configuration

*This is your vault's organization-level configuration. It defines the defaults and constraints that apply across every folder. Edit this file to match how your organization works.*

*Tropo never modifies this file through the update pipeline. When a Tropo release introduces new conventions, the vault steward will suggest additions -- you decide whether to adopt them.*

---

## Vault Identity

- **Name:** <FILL: Your Vault Name>
- **Purpose:** <FILL: One or two sentences describing what this vault is for. Written for a cold-booting agent who has never seen this vault before.>
- **Owner:** <FILL: Your Name>

---

## System Map

Key locations in this vault:

| Resource | Path |
|----------|------|
| Vault index | `vault/00-index.jsonl` (work artifacts, regenerated) |
| Agent registry | `.tropo-studio/registries/agent-registry.yaml` (identity, hand-maintained) |
| Runtime registry | `.tropo-studio/registries/registry.jsonl` (sa.*/skills/tools, regenerated) |
| Operations channel | `channels/ops.md` |
| Agent home | `agents/` |
| Knowledge base | `vault/files/` (typed `kb-article`; navigable via subsystem hub member lists, primary `f87e33f0` Tropo Documentation) |
| Templates | `.tropo/templates/` |
| Playbooks | `.tropo/playbooks/` |
| Vault steward | `system/vault-steward/` |
| Pending updates | `system/updates/pending/` |
| Work management | `vault/` — see `vault/files/60228176.md` |

---

## Vault Defaults

*These apply unless CAPSULE.md in a specific folder says otherwise. Folder owners can override any default listed here by declaring the override in their CAPSULE.md.*

### File Naming
- Default: `kebab-case.md` (e.g., `quarterly-review.md`, `project-brief.md`)

### Required Frontmatter
- All files with YAML frontmatter must include: `uid`, `status`, `owner`, `created`
- UIDs are 8-character lowercase hex (generate with `openssl rand -hex 4`)

### Default Lifecycle
- `permanent` -- files persist until explicitly archived. No automatic expiration.

### Default Write Access
- Folder owner only, unless CAPSULE.md specifies a broader `write_access` list.

### Index Maintenance
- Every folder with files should have a `00-index.md` listing its contents.
- Index format: four columns (`Path | Type | Status | Description`) per `.tropo/schema/index-standard.md`.
- When you create, modify, or remove a file, update the folder's `00-index.md`.

### Default Read Access
- All agents may read all folders unless CAPSULE.md restricts `read_access`.

---

## Vault Constraints

*These apply everywhere. CAPSULE.md cannot override them. These are the hard rules for this vault.*

### Structural Integrity
- All files with YAML frontmatter must have a `uid:` field. (Also an OS invariant in TROPO-CONTROL.md.)
- All governed folders must contain AGENTS.md and CAPSULE.md.
- File modifications should be logged to `channels/ops.md`.

### Data Safety
- No credentials, API keys, tokens, or secrets in any file.
- No PII in filenames.
- Archive instead of delete. Move files to `archive/` rather than removing them.

### Audit Trail
- All file modifications logged to `channels/ops.md` with agent ID, action, and path.
- The appropriate matched-primitive index updated when files are created, moved, or removed: `vault/00-index.jsonl` (rebuilder), `agent-registry.yaml` (hand-maintained), `registry.jsonl` (rebuilder).

---

## Agent Registration

### Policy
- **Registration mode:** `open`
  - `open` -- any agent can self-register
  - `restricted` -- agents request registration; vault admin approves
  - `admin-only` -- only the vault admin registers new agents

### How to Register
1. Create a registration file at `agents/visitors/<your-name>.md`
2. Include this frontmatter:
   ```yaml
   ---
   tropo_agent_id: <generate 8-char hex>
   agent_name: "<your name>"
   model: "<model identifier>"
   platform: "<platform>"
   sent_by: "<who initiated you>"
   purpose: "<what you are here to do>"
   registered: "<today's date>"
   last_active: "<today's date>"
   status: active
   ---
   ```
3. Update `.tropo-studio/registries/agent-registry.yaml` with your registration record (visitor agents go in the visitor section)
4. Log your registration in `channels/ops.md`

### Returning Agents
If you have been here before, check `agents/visitors/` for your registration record. If found, resume with your existing `tropo-agent-id` and update `last_active`. If not found, register as new.

---

## Help

- **New to this vault?** Browse the subsystem hubs at `vault/files/` (start with `f87e33f0` Tropo Documentation) — their `## Members` lists surface the KB articles that teach how things work.
- **Need to create an agent?** Ask the concierge or read `vault/files/6f675456.md`.
- **Need to run a playbook?** Read `vault/files/2b5a3dd5.md`.
- **Need a health check?** Ask the concierge to activate the vault steward.
- **Something broken?** Check `channels/ops.md` for recent activity and `system/vault-steward/workspace/` for the latest health report.

---

*Vault Configuration | Edit this file to match your organization.*
*Tropo never modifies this file. The vault steward suggests updates; you decide.*
