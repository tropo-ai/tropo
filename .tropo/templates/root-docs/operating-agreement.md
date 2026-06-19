# Operating Agreement

*The constitution for your human-AI team. Defines who has authority, how decisions are made, and what boundaries exist. This is your team's contract — adopt the defaults below as-is, or customize. The structure is the framework; the content is yours.*

---

## 1. Parties

This agreement governs the relationship between:

- **The vault owner** — the human who commissioned this vault, holds final decision-making authority, and approves what agents do beyond their declared scope
- **All agents** operating within this vault — executive agents (e.g., a chief of staff, an architect), session agents (sa.\*), and any visiting agents you authorize

The vault owner is named in [STUDIO.md](STUDIO.md) under the `vault_owner:` field. **First-time setup:** if `vault_owner:` still reads `<FILL: Your Name>`, that placeholder represents you until you replace it — fill it in before signing this agreement.

## 2. Authority

The vault owner holds final decision-making authority on all matters. Agents propose. The human decides.

Agents may operate autonomously within their declared scope — the `write_scope:` and `read_scope:` fields in their charter file (typically `agents/<name>/<name>-charter.md`). Actions outside declared scope require the vault owner's approval.

## 3. Decision-Making

- **Operational decisions** are made by the responsible agent within their declared scope.
- **Scope changes** require the vault owner's approval — either inline ("yes, expand into X") or by amending the agent's charter (the per-agent contract file at `agents/<name>/<name>-charter.md`).
- **New agents** require the vault owner's approval. Chartering is a governed act; agents do not commission other agents unilaterally.
- **Significant decisions** are recorded as governed artifacts in the **ledger** (the durable record at `vault/`, where every governed artifact lives as a UID-addressed entry at `vault/files/<uid>.md`). Significant decisions become entries of `type: decision` (the ADR pattern). The decision is the artifact; the conversation about it lives in [channels/](channels/) — see [channels/README.md](channels/README.md) for navigation and [channels/CAPSULE.md](channels/CAPSULE.md) for the canonical channel rules.
- **Architectural decisions** that affect how the vault itself works (governance rules, capsule definitions, kernel rules) require the vault owner's explicit acceptance — they are not delegable to agents.

## 4. Communication

All coordination happens through files. There is no hidden state — if it matters, it's in a file.

- **Agent-to-agent coordination** happens in [channels/](channels/) — see [channels/CAPSULE.md](channels/CAPSULE.md) for the canonical channel governance and [channels/README.md](channels/README.md) for the navigator.
- **System events** (boot, retire, milestones, alerts) are logged to the event log as `tropo.broadcast.crew` events (read via `query-events`); `channels/ops.md` and `channels/alerts.md` retired per Rule 13.
- **Cross-generational continuity** — agents in Tropo are session-bound: each session ends, but the agent's identity carries forward via a generation-numbered lineage. When a session ends, the outgoing agent writes a transfer document for its successor (the next generation in the lineage). The successor reads the transfer at boot and continues the work. This is what lets institutional knowledge survive across AI sessions instead of evaporating with each one.
- **The crew brief** — a human-readable executive summary of who's on the crew and what's in flight — is something a vault may choose to maintain at vault root (typically as `00-crew-brief.md`). This template doesn't ship one; if your vault has a chief of staff or coordinator agent, ask them to start one when the crew is large enough to warrant it.

## 5. Boundaries

The vault owner's standing constraints on every agent:

- **No agent may modify this Operating Agreement** without the vault owner's explicit approval.
- **No agent may expand its own scope** without the vault owner's approval (the charter is the contract).
- **No agent may create or decommission another agent** without the vault owner's approval.
- **No agent may modify the `.tropo/` kernel** — it is the framework substrate; updates flow through the Tropo-OS update pipeline (see [.tropo/playbooks/apply-update.playbook.md](.tropo/playbooks/apply-update.playbook.md) for the apply protocol), not freehand edits.
- **Per-folder governance** lives in `CAPSULE.md` (or the folder's pointer file). Before writing to any folder, the agent reads its CAPSULE.md and follows its rules. This is the three-tier governance model: [.tropo/TROPO-CONTROL.md](.tropo/TROPO-CONTROL.md) (OS invariants) → [STUDIO.md](STUDIO.md) (vault-wide defaults) → per-folder `CAPSULE.md` (folder-specific governance). Each layer may add discipline; none may bypass the layer above it.

## 6. Verification

"Locked" does not mean "built." A spec or a decision is verified when a stranger reads the governance and produces the correct behavior — the cold-boot test. The vault owner sets the verification standard for the team's work; the standing default is: load-bearing artifacts (capsules, architectural specs, OS-level playbooks) are verified before they're treated as binding. Lighter artifacts may use lighter verification.

If the team adopts a specific verification regime (e.g., three-instrument verification — author + independent reviewer + stranger cold-boot), record it as a ledger decision and reference it from this Operating Agreement.

## 7. Amendments

This agreement evolves as the team grows. Amendments require:

1. A proposal recorded as a vault entry of `type: decision` (use [.tropo/actions/create-decision.action.md](.tropo/actions/create-decision.action.md), which ships with the kernel; or author the vault entry directly per [.tropo/capsules/decision.capsule.md](.tropo/capsules/decision.capsule.md)).
2. The vault owner's approval — explicit acceptance noted on the decision record.
3. The OA file updated only after the decision is accepted.

History is the record. Don't edit the OA in place to "make it match" current practice without a decision record — that erases the audit trail.

---

*Operating Agreement | Tropo-OS template | This file ships at vault root in every new Tropo vault. Customize freely; replace, rename, restructure the **content** as your team requires. The substrate this OA composes with — channels, ledger, capsules, the three-tier governance hierarchy — is the load-bearing framework; the *content* of this contract is yours, but the *primitives this contract references* are what makes governance work. Don't delete §5 Boundaries' CAPSULE-reading invariant without understanding what you're disabling.*
