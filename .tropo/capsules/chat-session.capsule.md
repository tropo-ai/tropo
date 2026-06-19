---
subsystem_hub:
  - "2d083137"
uid: 88c21798
name: "chat-session"
type: capsule-definition
extends: core
version: 1.0
tier: os
author: argus-a95
created: 2026-06-03
modified: 2026-06-03
created_by: argus-a95
status: draft
enforced_enums:
  status: [new, active, closed]
meta_status_rollup:
  to-do: [new]
  in-progress: [active]
  done: [closed]
schema_version: 2
governed_by: 222873b9
aligned_with:
  - 63dbc524   # ADR-043 (Studio Consolidation Phase 2) — D1 mandates this type
  - 624b1976   # Studio Consolidation brief (Metis G66)
  - 7c47429a   # note.capsule — the governance-WEIGHT model (lightweight, capture-not-request)
---

# chat-session — Capsule Definition v1.0 (DRAFT)

*Authored Argus A95 2026-06-03 per [ADR-043 (63dbc524)](../../vault/files/63dbc524.md) D1. `status: draft` — the shape Metis (product) and Argus (architecture) aligned on; ships when Studio Consolidation Phase 2 builds, then locks. Models its GOVERNANCE WEIGHT on [note.capsule (7c47429a)](note.capsule.md) (lightweight, capture-not-request) but carries its own first-class structure.*

---

## 1. Intent

A chat-session is the **revisitable research-writing thread** — the conversation (intent → research → generate) that produces artifacts. Per ADR-043 D1: chats persist (revisit is a live product capability), but the **artifact is the primary governed deliverable**; the chat-session is its **provenance thread**. Governance is deliberately light: persist the session, do not heavy-govern every keystroke. It is a first-class primitive (not a note flavor) because it has structure note lacks — it belongs to a project and it produces artifacts.

**What this is NOT:** the crew event log (that is agent-to-agent coordination, a different modality). Chat-sessions are user-research conversations, vault-native, member_of a project.

## 2. Required Frontmatter (in addition to core)

| Field | Type | Constraint |
|-------|------|-----------|
| `member_of` | array of UIDs | The project (and/or hub) this research thread belongs to. A chat-session is always scoped to at least one project. |

**Required core fields (inherited from `core.capsule`):** `uid`, `type` (= `"chat-session"`), `title`, `created`, `modified`, `state` (= `active` at open). See [core.capsule (ee814120)](core.capsule.md).

## 3. Optional Frontmatter

| Field | Type | Purpose |
|-------|------|---------|
| `produced_artifacts` | array of UIDs | **The load-bearing relation.** Refs to the artifact entries this session generated. Encodes D1 "artifact is primary; chat-session is its provenance thread." Empty until the session produces an artifact. |
| `status` | enum | `new` / `active` / `closed` (the abstract 4-state; modeled on note v3.2). Optional — set when the thread's lifecycle matters; a thread is `active` while open, `closed` when the research is done. Absent = no lifecycle tracked. Structured field, never a tag (status-is-the-arbiter doctrine). |
| `tags` | array of strings | Freeform discovery axis. Describe, never decide (status is the arbiter). |
| `context` | string | One-line "what this research thread is after." ≤ 120 chars. |
| `refs` | array of UIDs | Related vault entries (source project entries read, prior sessions resumed, etc.). |
| `model` | string | The model/sleeve that ran the session (provenance). Optional. |

Additional fields are legal per core rules; this capsule does not police extras.

## 4. Body — the conversation (lightweight)

The body holds the conversation turns (or a curated summary + a pointer to the full transcript/trace). **No required structure** — free-form, like note. The discipline (D1): persist the session as a revisitable thread; do not govern every keystroke. When a session grows large, a summary-in-body + the full turns in a companion/trace store is acceptable (the artifact + the session record are the governed things, not every token).

## 5. State Machine

**Canonical status enum:** `status:` ∈ {new, active, closed}

```
(open) → active → closed
```
`status` is OPTIONAL (a session that never needs lifecycle leaves it absent). `state` (core) tracks visibility (`active` / `archived`). A closed research thread stays in the vault (revisitable); archival follows the standard state-change convention (no relocation).

## 6. The artifact relation (the primary-deliverable rule)

The **artifact** is the primary governed deliverable of research-writing; the chat-session is its **provenance** — `produced_artifacts:` links session → artifact(s). The artifact entry's own type is settled by the artifact-storage decision in the Phase-2 build (the existing document / external-artifact type, or a research-artifact type); this capsule refs artifacts by UID and does not redefine them. *(Composes-with dependency, not a blocker.)*

## 7. Governance Rules (in addition to core)

1. **Lightweight by mandate (D1).** No required body structure; persist the thread, not every keystroke.
2. **Capture, not request.** No request-lifecycle fields (`requested_by`/`approver`/`verifier`) — a chat-session is a research thread, not a delegated work request (same posture as note). If a session's output matures into requested work, that lives on the artifact or a task, not here.
3. **Structured status, never tags** (status-is-the-arbiter, Metis G66 / Mike doctrine).
4. **member_of is mandatory** — a session always belongs to a project (no orphan research threads).

## 8. Validation Checks (run at check-in)

1. `type` = `"chat-session"`; core fields present.
2. `member_of` present + resolves to at least one project entry (Rule 4).
3. If `produced_artifacts` present, every UID resolves to a vault entry.
4. If `status` present, value ∈ {`new`, `active`, `closed`}.
5. No request-lifecycle fields present (Rule 2 — WARN if found; promote to a task instead).

## 9. Composition

- **[ADR-043 (63dbc524)](../../vault/files/63dbc524.md)** D1 — the decision that mandates this type; D2 (direct vault reads) means surfaces read these entries via the index directly; D4 (write-through) means a new session is index-discoverable immediately.
- **[note.capsule (7c47429a)](note.capsule.md)** — governance-weight model (lightweight, capture-not-request, optional status).
- **[project.capsule (...)](project.capsule.md)** — `member_of` target; the project owns its research threads.
- **The artifact type** — `produced_artifacts` target; the primary deliverable (§6).
- **status-is-the-arbiter doctrine** (Metis G66 / Mike) — structured status + member_of, never tags-as-state.

---

*chat-session capsule | UID `88c21798` | v1.0 DRAFT | Argus A95 2026-06-03 | per ADR-043 D1 | "the revisitable research thread; the artifact is the deliverable, the session is its provenance — governed light."*
