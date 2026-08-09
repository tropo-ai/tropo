---
uid: toolbelt
name: toolbelt
type: catalog
kind: belt
generated_at: 2026-08-08
generated_by: generate-capability-catalogs.py
extraction_scope: ship
---

# Tropo Toolbelt

*18 core tools. Derived from `belt: true` frontmatter — do not hand-edit.*

---

### loop-activate
Activation gate for governed loops (v1.71 S1).

```
python3 vault/tools/2e5c81d3.py
```

### write-activation-entry
Open/close agent activation entries (boot and retirement).

```
python3 vault/tools/40b2f455.py {open|close|update}
```
*Example:* `python3 vault/tools/40b2f455.py open --agent talos --generation T18 ...`

### archive()
Flip entry state active↔archived with provenance and event.

```
python3 vault/tools/tropo-archive.py <uid> --reason <reason>
```
*Example:* `python3 vault/tools/tropo-archive.py 8f6ea459 --reason \"superseded\"`

### check-events
Drain your event log (directed + broadcasts; cannot miss a reply_required).

```
python3 vault/tools/tropo-check-events.py --as <name>
```
*Example:* `python3 vault/tools/tropo-check-events.py --as talos`

### tropo-disposition
Dispose of stale backlog items safely: archives referenced items, recycles unreferenced ones, surfaces judgment cases for review.

```
python3 vault/tools/tropo-disposition.py --owner <owner>
```
*Example:* `python3 vault/tools/tropo-disposition.py --owner argus --apply`

### emit-event
Emit a CloudEvent (message/broadcast/completion).

```
python3 vault/tools/tropo-emit-event.py --as <name> ...
```
*Example:* `python3 vault/tools/tropo-emit-event.py --type tropo.message.sent --as talos --lifecycle ephemeral --subject <party_uid> --data '{\"body\": \"...\"}'`

### generate-mint-registry
Regenerate the typed mint registry after capsule or companion-template changes.

```
python3 vault/tools/tropo-generate-mint-registry.py
```
*Example:* `python3 vault/tools/tropo-generate-mint-registry.py --check`

### mint-id
Mint a bare collision-checked identifier, list human typed bindings, or atomically birth a registry-bound human artifact.

```
python3 vault/tools/tropo-mint-id.py
```
*Example:* `python3 vault/tools/tropo-mint-id.py --count 5 --kind file`

### preflight
First command on any new machine, and the first thing to run when a tool dies on an import.

```
python3 vault/tools/tropo-preflight.py
```
*Example:* `python3 vault/tools/tropo-preflight.py --json`

### query-events
Query historical event log with advanced filtering.

```
python3 vault/tools/tropo-query-events.py
```
*Example:* `python3 vault/tools/tropo-query-events.py --type tropo.broadcast.crew`

### rebuild-vault
Comprehensive substrate refresh (index + nav + boards + brief).

```
python3 vault/tools/tropo-rebuild-vault.py
```
*Example:* `python3 vault/tools/tropo-rebuild-vault.py --only 3031ffa3`

### tropo-recycle
Soft-delete governed entries (mv to recycle/).

```
python3 vault/tools/tropo-recycle.py <uid>
```
*Example:* `python3 vault/tools/tropo-recycle.py 8f6ea459 --reason \"superseded\"`

### scan-import-state.py
Boot-time shallow scanner for orphan/anomaly detection.

```
python3 vault/tools/tropo-scan-import-state.py --output-dir <dir>
```
*Example:* `python3 vault/tools/tropo-scan-import-state.py --output-dir agents/talos/...`

### smoke
Run after any retirement, after any commit that touches vault/tools/, and any time the studio feels wrong but the validator says it is fine.

```
python3 vault/tools/tropo-smoke.py
```
*Example:* `python3 vault/tools/tropo-smoke.py --only index --json`

### tropo-test
Single-gesture green/yellow/red substrate health verdict.

```
python3 vault/tools/tropo-test.py
```
*Example:* `python3 vault/tools/tropo-test.py --quick`

### tropo-validate
Comprehensive read-only audit of vault structural health.

```
python3 vault/tools/tropo-validate.py
```
*Example:* `python3 vault/tools/tropo-validate.py --vault-path .`

### sa.board-agent
Per-agent backlog board rendering at activation Group 4.

```
'# (sa.board-agent is dispatched, not called directly)'
```
*Example:* `'# see agents/sa/sa.board-agent/sa.board-agent.md'`

### vault-search
The lookup verb.

```
python3 vault/tools/tropo-vault-search.py \"<query>\"
```
*Example:* `python3 vault/tools/tropo-vault-search.py \"argus soul\"`

---

*Anything not here? → `python3 vault/tools/tropo-vault-search.py <query>`*

*Tropo Toolbelt | 2026-08-08 | v1.15 substrate*
