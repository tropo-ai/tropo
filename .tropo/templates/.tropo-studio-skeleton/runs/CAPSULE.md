---
spec_version: 2
tier: capsule
folder_type: governed
owner: vault-admin
write_access: all-agents
read_access: all
purpose: "Playbook run records — activation records, retirement records, fleet-ops run artifacts. Per-run state the boot + retirement playbooks write to."
uid: 5ef081c4
---

# `.tropo-studio/runs/` — Playbook Run Records

## Purpose

Every playbook run that produces persistent state for audit or verification writes here. Activation runs, retirement runs, fleet-ops runs — each gets a folder or file that records what happened.

## What belongs here

- **Activation run folders** — subfolders per activation with `run.jsonl` milestone logs. The agent-activation playbook creates these at Group 0 Step 0.0.
- **Retirement run folders** — parallel pattern for the retirement playbook.
- **Fleet-ops run records** — per-dispatch logs when the ops fleet runs scheduled work.
- **Other playbook artifacts** where the playbook needs permanent trace of execution.

## What does NOT belong here

- **Agent memory** — that's in `memory/` (vault) or `agents/<name>/.tropo-capsule/memory/` (per-agent).
- **Channel posts** — those are in `channels/`.
- **Task state** — that's in your work management system.
- **Temporary scratch** — use a workspace.

## Naming convention

Activation runs: `agent-activation-<name>-<generation>-<date>/` (e.g., `agent-activation-vela-v32-2026-05-01/`)
Retirement runs: `agent-retire-<name>-<generation>-<date>/`
Fleet-ops runs: `fleet-ops-<date>-<hhmm>/`

## Retention

Run records are permanent. They're the audit trail for every boot and retirement on the vault. Do not delete them.

Archive if volume becomes a problem: move older runs (e.g., >90 days) to `runs/archive/` but keep accessible.
