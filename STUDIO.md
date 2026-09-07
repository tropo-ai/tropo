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
| Vault index | `vault/00-index.jsonl` (work artifacts and runtime callables, regenerated) |
| Agent registry | `.tropo-studio/registries/agent-registry.yaml` (identity, hand-maintained) |
| Runtime catalogs | `.tropo/tool-catalog.md`, `.tropo/skill-catalog.md`, `.tropo/sa-agent-catalog.md` (generated from the index) |
| Event log (coordination + audit trail) | `vault/events/` — emit with `vault/tools/tropo-emit-event.py`, read with `vault/tools/tropo-query-events.py` |
| Event projections for human reading | `channels/` — a new Studio ships none; add them as you need them (see `channels/CAPSULE.md`) |
| Agent home | `agents/` |
| Knowledge base | `vault/files/` (typed `kb-article`; navigable via subsystem hub member lists, primary `f87e33f0` Tropo Documentation) |
| Templates | `vault/templates/` |
| Playbooks | `.tropo/playbooks/` |
| Vault steward | `vault/tropo-vault-steward/` |
| Pending updates | `vault/updates/pending/` (applied: `vault/updates/applied/`, receipts: `vault/updates/receipts/`) |
| Work management | `vault/` — see `vault/files/2d4f8c91.md` |

---

## Vault Defaults

*These apply unless CAPSULE.md in a specific folder says otherwise. Folder owners can override any default listed here by declaring the override in their CAPSULE.md.*

### File Naming
- Default: `kebab-case.md` (e.g., `quarterly-review.md`, `project-brief.md`)

### Required Frontmatter
- All files with YAML frontmatter must include: `uid`, `status`, `owner`, `created`
- UIDs are 8-character lowercase hex, minted through the governed tool:
  `python3 vault/tools/tropo-mint-id.py --kind file`. The tool records every mint, so two
  files can never be given the same identifier; a raw random generator cannot promise that.

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
- File modifications should be recorded as events via `vault/tools/tropo-emit-event.py`.

### Data Safety
- No credentials, API keys, tokens, or secrets in any file.
- No PII in filenames.
- Archive instead of delete. Move files to `archive/` rather than removing them. A fresh Studio ships no `archive/` folder — create it the first time you archive something.

### Audit Trail
- All file modifications recorded to the event log via `vault/tools/tropo-emit-event.py`, carrying the acting agent, the action, and the path. Read them back with `vault/tools/tropo-query-events.py`.
- The appropriate matched-primitive index updated when files are created, moved, or removed: `vault/00-index.jsonl` (rebuilder), `agent-registry.yaml` (hand-maintained).

---

## Agent Registration

### Policy
- **Registration mode:** `open`
  - `open` -- any agent can self-register
  - `restricted` -- agents request registration; vault admin approves
  - `admin-only` -- only the vault admin registers new agents

### How to Register
1. Create a registration file at `agents/visitors/<your-name>.md`. A fresh Studio ships no `agents/visitors/` folder — create it as part of this step.
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
4. Announce yourself to the crew:
   ```
   python3 vault/tools/tropo-emit-event.py --type tropo.broadcast.crew \
     --source /agents/<your-name> --as <your-name> --lifecycle evergreen \
     --data '{"from": "<your-name>", "headline": "joined this Studio", "category": "ops"}'
   ```
   There is deliberately no `agent.registered` event type — registration IS the registry row you
   just wrote, and the event is the crew-visible announcement of it. `--as` is required for an
   agent source; a bare name is refused because the tool cannot resolve who is speaking.

### Returning Agents
If you have been here before, check `agents/visitors/` for your registration record. If the folder does not exist, no agent has registered here yet. If found, resume with your existing `tropo-agent-id` and update `last_active`. If not found, register as new.

---

## Help

- **New to this vault?** Browse the subsystem hubs at `vault/files/` (start with `f87e33f0` Tropo Documentation) — their `## Members` lists surface the KB articles that teach how things work.
- **Need to create an agent?** Ask the concierge or read `vault/files/6f675456.md`.
- **Need to run a playbook?** Read `vault/files/2b5a3dd5.md`.
- **Need a health check?** Ask the concierge to activate the vault steward.
- **Something broken?** Run `python3 vault/tools/tropo-validate.py --customer` for a structural check (always pass `--customer`; the flagless form adds vendor-development checks that do not apply to your Studio). For recent activity, read the event log with `python3 vault/tools/tropo-query-events.py`. A fresh Studio ships no health report: `vault/tropo-vault-steward/` contains only its capsule until the Vault Steward first runs, which is when it creates its `logs/` and `workspace/` folders there.

---

*Vault Configuration | Edit this file to match your organization.*
*Tropo never modifies this file. The vault steward suggests updates; you decide.*
