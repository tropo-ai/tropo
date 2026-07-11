---
uid: toolbelt
name: toolbelt
type: catalog
kind: belt
generated_at: 2026-07-11
generated_by: generate-capability-catalogs.py
extraction_scope: ship
---

# Tropo Toolbelt

*14 core tools. Derived from `belt: true` frontmatter — do not hand-edit.*

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

### mint-id
Get a fresh collision-checked identifier before authoring (file/agent UID or studio genesis today; vault/event declared, not yet built).

```
python3 vault/tools/tropo-mint-id.py
```
*Example:* `python3 vault/tools/tropo-mint-id.py --count 5 --kind file`

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

### vault-search
The lookup verb.

```
python3 vault/tools/tropo-vault-search.py \"<query>\"
```
*Example:* `python3 vault/tools/tropo-vault-search.py \"argus soul\"`

---

*Anything not here? → `python3 vault/tools/tropo-vault-search.py <query>`*

*Tropo Toolbelt | 2026-07-11 | v1.15 substrate*
