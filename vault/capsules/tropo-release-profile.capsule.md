---
uid: 654f3a90
name: release-profile
type: capsule-definition
extends: core
version: '1.0'
tier: os
author: argus
created: 2026-08-24
created_by: argus-a156
modified: '2026-08-26'
modified_by: vela-v74
status: locked
locked_by: mike
locked_at: '2026-08-26'
authored_under: 5b608d28
authored_note: 'Drafted 2026-08-24 by argus-a156 under Mike-locked dev-spec 5b608d28 (v1.92 Stream 1)
  AC5. Drafted at the request of talos-t51, who was assigned AC5''s build and correctly REFUSED to
  author this file: a capsule is a type definition, which is governance substrate and the architect''s
  lane regardless of which spec''s committed_substrate names it. Status stayed DRAFT until Mike locked
  it 2026-08-26, in the v1.92 release session (vela-v74) after the independent release-harness dispatch
  found its one instance (6bf18510) absent from the shipped box for the same reason — Mike locks new
  types, not Argus and not Talos.'
schema_version: 2
capsule_version: '1.0'
enforced_enums:
  status:
    - draft
    - active
    - locked
    - archived
    - retired
  slot:
    - build-the-artifact
    - verify-the-artifact
    - publish-the-artifact
  kind:
    - tool
    - playbook
meta_status_rollup:
  to-do:
    - draft
  in-progress:
    - active
  done:
    - locked
    - archived
    - retired
---

# release-profile — Capsule Definition v1.0

## 1. Intent

**The release machine must not know what product it is shipping.**

Today it does, everywhere, and the cost is measurable: this Studio runs four
forked pipelines — dev, web, app and kb — because shipping a different product
meant declaring a new domain, and a new domain means a new root pipeline, and a
new root pipeline means rebuilding the whole machine. Whoever rebuilt it wrote
five steps, not twelve. So `web-pipeline` deploys tropo-ai.com with **no freeze,
no independent verifier, and no receipt**, while `release-pipeline` has all
three. The rigour was not dropped out of carelessness; the structure required
someone to retype it and nobody did.

A **release profile** is the product-specific half, extracted. The machine
declares generic slots with gate contracts; the profile declares what actually
runs in them. **Fork the profile, not the machine** — so governance (locked-plan
ignition, preflight, deterministic build, independent verify, publish gating,
receipts) comes free with the machine rather than being re-earned per product.

**v1.92 ships exactly ONE profile.** The seam is the deliverable; populating it
is not. A second profile is built when a second product needs the machine, and
not before.

*Strategic tie (Mike's bar `74e9676b`): a stranger studio shipping ITS OWN work
with our pipeline unaided is only reachable if the machine is product-agnostic.
This seam is what makes that goal achievable, not an extra alongside it.*

## 2. Schema

Extends `core` (uid, type, status, state, owner).

| Field | Type | Required | Purpose |
|---|---|---|---|
| `product` | string | yes | What this profile ships. Lowercase-hyphen. Unique across active profiles. |
| `pipeline_uid` | 8-hex | yes | The root pipeline this profile drives. One profile, one pipeline. |
| `slots` | list of slot objects | yes | Exactly one entry per declared slot value (§3). |
| `supersedes_profile` | 8-hex \| null | no | Forward-pointer discipline when a profile is replaced. |

### The slot object

| Field | Type | Required | Purpose |
|---|---|---|---|
| `slot` | enum | yes | `build-the-artifact` \| `verify-the-artifact` \| `publish-the-artifact`. |
| `gate_contract` | enum | yes | The `release_gates` boundary that MUST be green before this slot completes. One of the five declared phases — **not a free string**, because a slot that names its own gate could name a gate that never runs. |
| `steps` | list of executor bindings | yes | Ordered. Each entry obeys the binding contract in `lib/release_bindings.py` — the SAME vocabulary the tools use, so a profile and a tool cannot disagree about what "deterministic" means. |

### The executor binding, in a profile

Identical in shape and rules to `lib/release_bindings.ExecutorBinding`, because
it is that type:

| Field | Required | Notes |
|---|---|---|
| `step_uid` | yes | 8-hex leaf of `pipeline_uid`. The uid is the address; a rename cannot orphan it. |
| `kind` | yes | `tool` (deterministic — the machine performs it) or `playbook` (judgment — a named executor performs it). |
| `entry` | yes | tool: `<script>:<callable>` or a command. playbook: the procedure's uid. |
| `executor` | **iff `kind: playbook`** | The executor CLASS — an agent role, or `human`. Forbidden on `kind: tool`. |
| `description` | yes | One line. The runner prints it to whoever is standing there. |

## 3. The three slots, and why exactly three

The slots are the invariant shape of shipping anything: **make it, check it,
release it.** They are deliberately few and deliberately generic — a fourth slot
would be a product concern leaking back into the machine, which is the defect
this type exists to remove.

- **`build-the-artifact`** — a commit becomes a box, deterministically. Same
  commit, same box.
- **`verify-the-artifact`** — the box is checked by something that did not build
  it. This is where the judgment steps concentrate.
- **`publish-the-artifact`** — the one outward, irreversible act.

Each slot names its `gate_contract`, which is how a profile inherits governance
rather than restating it: the machine refuses to complete a slot whose boundary
is not green, and the profile cannot choose a laxer boundary because the value
is an enum over the gate registry's own phases.

## 4. Validation Rules

1. **Exactly one slot object per declared slot value.** Three slots, no
   duplicates, none missing. A profile with two `publish-the-artifact` entries
   cannot say what publishing means.
2. **A `playbook` step MUST name an executor class.** Refused at load. *A
   procedure with no executor is an event with no emitter* — the same rule the
   retirement stream exists to enforce, and the one hard validation requirement
   AC5 names.
3. **A `tool` step MUST NOT name an executor.** A deterministic step naming a
   human is a judgment step wearing the wrong label, and it would let the runner
   walk past a decision nobody made.
4. **One executor per `step_uid`, profile-wide.** Two bindings for one step means
   the runner cannot say what comes next.
5. **Every `step_uid` resolves to a live leaf of `pipeline_uid`.** A binding
   naming an archived or invented uid resolves to nothing and reads, from the
   outside, exactly like coverage.
6. **`gate_contract` is one of the five `release_gates` phases.** Not a free
   string.
7. **`product` is unique across active profiles.** Two active profiles claiming
   one product is the forked-machine problem returning by another door.

**Deliberately NOT a rule:** that every leaf of the pipeline appears in the
profile. Partial coverage is the honest state during a build, and the completeness
demand belongs to the acceptance test, not the loader — a type that refuses to
load an incomplete profile cannot be used to report how incomplete it is.

## 5. Composes-With

- **`lib/release_bindings.py`** — the binding contract. This capsule does not
  restate it; it references it. One shape, two declarers (tools and profiles).
- **`lib/release_gates.py`** — supplies the `gate_contract` enum. A gate's phase
  is COMPUTED from its declared inputs, so a profile cannot move a gate later by
  naming a different boundary.
- **`pipeline`** (`634913c2` for `tropo-release`) — the profile drives a pipeline;
  it never replaces one. Forking a pipeline stays legal per the pipeline capsule's
  own one-root-per-domain rule. The model is **fork the profile, not the machine.**

**Not yet composed, and named so it is not discovered later:** `web-pipeline`,
`app-pipeline` and `kb-pipeline` are the products this seam eventually serves.
Migrating them is **explicitly not v1.92 work** (Mike, 2026-08-24: *"it is not
v1.92 work"*). When it happens, those root pipelines are superseded by profiles
of this type — stated here as the intended end-state so a seam that implies three
supersessions does not ambush someone two cycles from now.

## §Template

```yaml
---
uid: <8-hex>
name: <product>-release
type: release-profile
product: <lowercase-hyphen>          # REQUIRED: what this profile ships
pipeline_uid: <8-hex>                # REQUIRED: the root pipeline it drives
status: draft
state: active
owner: <agent-slug>
slots:
  - slot: build-the-artifact
    gate_contract: candidate         # a release_gates phase, never a free string
    steps:
      - step_uid: <8-hex>
        kind: tool
        entry: <script>:<callable>
        description: <one line>
  - slot: verify-the-artifact
    gate_contract: pre-freeze
    steps:
      - step_uid: <8-hex>
        kind: playbook
        entry: <playbook-uid>
        executor: <agent-role|human> # REQUIRED on playbook; refused without it
        description: <one line>
  - slot: publish-the-artifact
    gate_contract: pre-outward-fire
    steps:
      - step_uid: <8-hex>
        kind: tool
        entry: <script>:<callable>
        description: <one line>
schema_version: 2
capsule_version: '1.0'
---
```

---

*release-profile capsule v1.0 | drafted 2026-08-24 by argus-a156 under 5b608d28 AC5 |
**status: locked 2026-08-26 by Mike.***
