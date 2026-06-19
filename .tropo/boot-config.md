---
uid: b7e3a291
tier: 1
type: os-config-pointer
status: published
version: "2.0"
supersedes_version: "1.2"
owner: tropo
created: 2026-04-15
modified: 2026-06-04
modified_by: argus-a97
v2_0_1_hygiene_note: "Argus A97 2026-06-04 — v1.61 channel-retirement tail fix (no contract change). The degraded-mode fallback block instructed agents to post to retired channels/alerts.md (substrate-resolution failure) + channels/ops.md (ADR-016 HALT); both retired at v1.61 per Rule 13. Replaced with the canonical event-log pattern (emit tropo.broadcast.crew severity:flash / category:ops), matching the activation playbook v2.12 + canonical Tier 1 substrate 8f6ea459. Low-traffic fallback block missed by the v1.61 sweep; surfaced at A97 boot diagnostic, fixed per Mike-A97 self-healing directive. Boot semantics unchanged; only the coordination mechanism corrected to reality."
governed_by: 78c2126d
canonical_substrate_uid: "8f6ea459"   # Canonical Tier 1 substrate at vault/files/<uid>.md (per v1.20.0 Q5 lock: two-file pattern; kernel pointer + canonical vault substrate)
member_of:
  - "8dd772a0"   # tropo-governance
---

# Tropo-OS — Boot Configuration (Tier 1 Kernel Pointer)

*Bootstrap-floor kernel pointer. The canonical Tier 1 substrate lives at [`vault/files/8f6ea459.md`](../vault/files/8f6ea459.md). This pointer carries an inline degraded-mode fallback content block (universal hard gates + universal required outcomes) so an agent can boot in fallback mode if the canonical substrate is unreachable.*

---

## Boot Resolution

**Primary path:** Read the canonical Tier 1 substrate at [`vault/files/8f6ea459.md`](../vault/files/8f6ea459.md). The canonical substrate carries the full content body (path resolution, tier reachability rules, phase structure, universal hard gates, universal required outcomes, self-healing primitive). All subsequent boot steps resolve against the canonical substrate.

**Degraded-mode fallback path:** If the canonical substrate UID `8f6ea459` does not resolve (vault index corrupted, UID absent, file missing), boot in **fallback mode** using the inline content block below. Emit a `tropo.broadcast.crew` event with `severity: flash` naming the resolution failure (the event log is the canonical coordination surface post-v1.61; `channels/alerts.md` retired per Rule 13). Await human resolution before continuing past activation Group 0.

---

## Degraded-Mode Fallback Content (inline; sufficient to boot)

### Phase Structure

Every agent activation executes these Groups in order. Milestone gates are structural — a Group cannot begin until its dependency milestone fires.

**Established-agent routing (v1.70 S3.5.3):** if you are generation 2+ WITH a §Boot-Extension, the activation playbook is read via the established-agent fast-path [`.tropo/boot-fast-path.md`](boot-fast-path.md) (`a993f079`) instead of reading the full canonical playbook. This routes established agents to the ~28-30K boot path. Else (generation 1, OR gen 2+ with no §Boot-Extension): read the full canonical playbook. The two populations exhaustively partition; the safe default is stated, not inferred.

```
Group 0 — Boot Configuration → milestone: Boot Config Chain Complete
Group 1 — Identity Verification → milestone: Identity Gates Clear (HARD GATES)
Group 2 — Context Loading → milestone: Context Loaded
Group 3 — Operational Grounding → milestone: Operationally Grounded
Group 4 — Self-Diagnostic → milestone: Diagnostic Complete
Group 5 — Startup Signal → milestone: Agent Active
```

### Universal Hard Gates

These two conditions HALT activation. They are not advisory.

**ADR-016 — Parallel Generation:** If the predecessor's status shows ACTIVE (not RETIRING or RETIRED), HALT. Emit a `tropo.broadcast.crew` event with `category: ops` naming the violation (`channels/ops.md` retired per Rule 13; the event log is canonical). Wait for human direction. Two active generations of the same agent is a governance violation.

**ADR-028 — Generation Mismatch:** If the generation number in the log does not equal last row + 1, HALT. Flag to human. Generation identity mismatch requires human resolution.

### Universal Required Outcomes

Every activation must achieve these before delivering the startup signal:

- Predecessor confirmed RETIRING or RETIRED
- Generation log row opened; predecessor's row closed
- Vault root resolved
- **Self-Healing Primitive read and internalized; confirmation surfaces in startup signal** *(per [`.tropo/SELF-HEALING.md`](SELF-HEALING.md))*
- Operating principles read
- Mission brief read
- Memory loaded (agent-level and vault-level, or gap noted)
- Crew brief read
- Status card updated with ACTIVE status and current generation
- Startup signal delivered

### Self-Healing Primitive Binding

**Every Tropo agent — in every Studio, every role, every session — operates under the [Self-Healing Primitive at `.tropo/SELF-HEALING.md`](SELF-HEALING.md).** Read at Group 2 of activation; confirmation surfaces in startup signal at Group 5; soft-gated by principal's eyes on the signal.

The primitive declares the universal binding: *if you see something, fix it.* Trivial defects: fix in place. Substantive defects: file as tracked work-items in the relevant project's `01-inbox/`. Don't carry forward. Don't defer.

This is OS-tier; cannot be overridden by Tier 2 (Studio) or Tier 3 (agent) configuration.

---

## Path Resolution Discipline

**Vault root is resolved in Group 0, Step 0.0 of the activation playbook — BEFORE any tier reads.** The activation file's own location is the primary anchor: for an activation file at `<some-path>/agents/<name>/<name>-activation.md`, vault root is `<some-path>/`. Fallback: the directory containing `STUDIO.md`. All paths declared in this Tier 1 file, in Tier 2, and in Tier 3 are relative to vault root.

**Tier file locations (post-v1.20.0 two-file pattern):**

- Tier 1 kernel pointer: `<vault-root>/.tropo/boot-config.md` (this file)
- Tier 1 canonical substrate: `<vault-root>/vault/files/8f6ea459.md`
- Tier 2 kernel pointer: `<vault-root>/.tropo-studio/agent-boot.extension.md`
- Tier 2 canonical substrate: `<vault-root>/vault/files/cf8c3be9.md`
- Tier 3: per-agent at `<vault-root>/vault/files/<agent-boot-extension-uid>.md` (resolved via status card; one entry per agent)

## What This File Does NOT Declare

- Studio-specific channel lists (Tier 2 declares)
- Soul loading (Tier 3 declares)
- Agent-specific reads (Tier 3 declares)
- Vault-specific operating principles (Tier 2 declares)

The canonical substrate at [`vault/files/8f6ea459.md`](../vault/files/8f6ea459.md) carries the full content; this kernel pointer + inline degraded-mode fallback is the bootstrap floor that lets a Studio resolve to canonical even if the canonical substrate is temporarily unreachable.

---

*Tropo-OS Boot Configuration Kernel Pointer | Tier 1 | v2.0 (post-v1.20.0 two-file pattern)*
*Canonical substrate: [vault/files/8f6ea459.md](../vault/files/8f6ea459.md)*
*Migration provenance: bumped from v1.2 (single-file kernel content) to v2.0 (kernel pointer + canonical vault substrate) at v1.20.0 per Q5 lock — Convergence Phase 2.*
