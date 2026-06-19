---
uid: toolbelt
name: toolbelt
type: catalog
kind: belt
generated_at: 2026-06-19
generated_by: generate-capability-catalogs.py
extraction_scope: ship
---

# Tropo Toolbelt

*14 core tools. Derived from `belt: true` frontmatter — do not hand-edit.*

---

### scan-import-state.py
Boot-time shallow scanner for orphan/anomaly detection.

```
python3 vault/tools/0a316ca6.py --output-dir <dir>
```
*Example:* `python3 vault/tools/0a316ca6.py --output-dir agents/talos/...`

### query-events
Query historical event log with advanced filtering.

```
python3 vault/tools/1545ac97.py
```
*Example:* `python3 vault/tools/1545ac97.py --type tropo.broadcast.crew`

### check-events
Drain your event log (directed + broadcasts; cannot miss a reply_required).

```
python3 vault/tools/2471edc0.py --as <name>
```
*Example:* `python3 vault/tools/2471edc0.py --as talos`

### tropo-recycle
Soft-delete governed entries (mv to recycle/).

```
python3 vault/tools/2573f6dd.py <uid>
```
*Example:* `python3 vault/tools/2573f6dd.py 8f6ea459 --reason \"superseded\"`

### loop-activate
Activation gate for governed loops (v1.71 S1).

```
python3 vault/tools/2e5c81d3.py
```

### tropo-test
Single-gesture green/yellow/red substrate health verdict.

```
python3 vault/tools/3086287a.py
```
*Example:* `python3 vault/tools/3086287a.py --quick`

### write-activation-entry
Open/close agent activation entries (boot and retirement).

```
python3 vault/tools/40b2f455.py {open|close|update}
```
*Example:* `python3 vault/tools/40b2f455.py open --agent talos --generation T18 ...`

### mint-uid
Get a fresh collision-checked 8-hex UID before authoring.

```
python3 vault/tools/5187be30.py
```
*Example:* `python3 vault/tools/5187be30.py --count 5`

### archive()
Flip entry state active↔archived with provenance and event.

```
python3 vault/tools/6cc9dcdb.py <uid> --reason <reason>
```
*Example:* `python3 vault/tools/6cc9dcdb.py 8f6ea459 --reason \"superseded\"`

### emit-event
Emit a CloudEvent (message/broadcast/completion).

```
python3 vault/tools/ca90f098.py --as <name> ...
```
*Example:* `python3 vault/tools/ca90f098.py --type tropo.message.sent --as talos --lifecycle ephemeral --subject <party_uid> --data '{\"body\": \"...\"}'`

### tropo-validate
Comprehensive read-only audit of vault structural health.

```
python3 vault/tools/d2b9c8e6.py
```
*Example:* `python3 vault/tools/d2b9c8e6.py --vault-path .`

### rebuild-vault
Comprehensive substrate refresh (index + nav + boards + brief).

```
python3 vault/tools/e8d4c1b9.py
```
*Example:* `python3 vault/tools/e8d4c1b9.py --only 3031ffa3`

### sa.board-agent
Per-agent backlog board rendering at activation Group 4.

```
# (sa.board-agent is dispatched, not called directly)
```
*Example:* `# see agents/sa/sa.board-agent/sa.board-agent.md`

### vault-search
The lookup verb.

```
python3 vault/tools/943149d4.py \"<query>\"
```
*Example:* `python3 vault/tools/943149d4.py \"argus soul\"`

---

*Anything not here? → `python3 vault/tools/943149d4.py <query>`*

*Tropo Toolbelt | 2026-06-19 | v1.15 substrate*
