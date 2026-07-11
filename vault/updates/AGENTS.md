# vault/updates/ — Update Apply State Machine (Governance Contract)

*The customer-side (this-Studio-side) update apply pipeline. Re-homed here from the dissolved `system/updates/` at the v1.78 Gate-2 clean-self-update cycle (dev-spec `fc4874f4`), per One Home (ADR-045). This is NOT the framework distribution staging area — that is the top-level `updates/` folder (owner: Metis; see `updates/.tropo-studio/CAPSULE.md`). This folder is where THIS vault's own applied/pending/failed update history lives.*

## Invariant

**Governed by the apply-update playbook, not hand-edited.** Every write to `pending/`, `applied/`, `failed/`, or `update-history.jsonl` happens through [`vault/playbooks/71f186cf.md`](../playbooks/71f186cf.md) (Apply a Tropo-OS Update, v2.0) or the concierge's Review-phase dry-run orchestration (`.tropo/concierge/activate.md` §Section 5). Do not hand-place or hand-delete update folders.

## What belongs here

- `pending/<update_id>/` — an update package dropped in by the user, awaiting review/apply. Contains the update package (`manifest.yaml`, `UPDATE.playbook.md`, `TEST.playbook.md`, `files/`) plus, once Review starts, `dry-run-reports/<migration_id>.md` per migration.
- `applied/<update_id>/` — a successfully applied update, moved here with its verification report and all migration reports. Never delete. Never re-run from here.
- `failed/<update_id>/` — an update that halted (validation, compatibility, operation, or migration failure), moved here with a partial-apply or divergence report. Never delete; the report is the audit trail.
- `update-history.jsonl` — one JSON line per applied-or-failed update (append-only). Rows: `{"update_id","target_version","min_compatible","result","date","reason"}`. This is the history index — **NOT** a `00-index.md` (that per-folder convention was retired 2026-06-21; superseded studio-wide by the graph vault). Query with `grep`/`jq`, same idiom as `vault/00-index.jsonl`.
- `receipts/<update_id>-receipt.md` — the per-apply covenant verification receipt (ADR-049 layer 3): pre/post hash manifest of user substrate + the list of `tropo-*` components replaced. Written by the apply engine on every apply (success or failure up to the point reached), read by Po to present to the owner in plain language.

## What does NOT belong here

- Framework update *packages being built* for distribution — those live in the top-level `updates/` staging folder (Metis-owned), never here.
- Anything outside the pending/applied/failed/history/receipts shape above.

## Namespace rule this folder's contents obey (ADR-045)

Every file this folder receives via an apply is either a `tropo-*` OS component (replaced) or arrives as part of the update package payload itself (never a `<slug>-<uid>` user file — user files are never routed through here).

---
*vault/updates/AGENTS.md | Owner: Talos | Re-homed from system/updates/ at v1.78 Gate-2 (dev-spec fc4874f4) | 2026-07-02*
