---
uid: 2ffdd9d6
type: dev-spec
title: Pipeline Activation Key — Dev-Spec (fingerprint-as-key release authorization gate)
description: Build spec for the release-authorization key (brief f8cda3dd). The runtime mints an unforgeable fingerprint of a legitimate pipeline-run; build + ship refuse without it. Fail-closed, no break-glass,
  release-pipeline scope. Realizes 'lovingly reverse engineering our future' — the plain fingerprint today is the seed of signed provenance later.
status: locked
state: active
version: '1.0'
locked_by: mike-maziarz
locked_at: 2026-06-16
lock_note: Locked under Mike-A115 captain-mode delegation ('go through the motions lightweight, follow the pipeline, see you on the other side', 2026-06-16). Design fixed at the brief f8cda3dd shape + the
  3 lean decisions; amendments via supersession.
priority: p1
references_cycle_brief: f8cda3dd
target_release: v1.71
target_stream: S1
retarget_note: "Argus A115 2026-06-16 (Mike-A115 'proceed'): folded from v1.72 into v1.71 — the key code is in source, v1.71's build snapshots it, so v1.71 becomes the first release that both CONTAINS the key and SHIPS THROUGH it. One release, not two."
gauntlet_rounds_required: 1
author: argus-a115
created: 2026-06-16
modified: '2026-06-17'
created_by: argus-a115
modified_by: pipeline-runtime.py
schema_version: 2
extraction_scope: ship
governed_by: 8dd772a0
member_of:
- 6dff0111
informs:
- f8cda3dd
refs:
- 9e7003b1
- a1b8c2d4
- 9da979b2
tags:
- dev-spec
- pipeline-activation-key
- fingerprint-as-key
- fail-closed
- enforcement
- lovingly-reverse-engineering-our-future
triggered_test_spec_uids:
- 460a6907
triggered_test_activation_uids:
- a29fe21d
triggered_doc_spec_uids:
- 8604fd29
triggered_doc_activation_uids:
- eb8d29d9
committed_substrate:
- target: ".tropo/scripts/lib/release_authorization.py"
  change_class: NEW
  description: "the shared release-authorization gate + fingerprint compute/verify + mint CLI"
- target: "vault/tools/8654900a.md (produce-release-folder step) — pipeline-runtime mint hook"
  change_class: AMEND
  description: "verification_command changed to the key MINT — minting succeeds only when the doc/test cascade fired"
- target: "vault/tools/a1b8c2d4.py (build-release)"
  change_class: AMEND
  description: "require --activation-uid; gate Step 0 (build) + Step 11 (public ship, + human_signoff); --dry-run exempt"
- target: "vault/tools/tests/test_release_authorization.py"
  change_class: NEW
  description: "enforcement gauntlet (8/8): forged/absent/tampered/no-cascade/no-signoff all refused"
acceptance_criteria:
- "AC-1 — shared fail-closed gate require_release_authorization(): refuses on missing run/key/fingerprint-mismatch/missing-signoff or any exception."
- "AC-2 — runtime mints the key at the produce-release-folder gate, only after the doc/test cascade (4.5/4.6) fired."
- "AC-3 — build-release refuses without a valid --activation-uid key before Step 0; --dry-run exempt."
- "AC-4 — public Supabase upload refuses without key + a human_signoff event; else local zip only."
- "AC-5 — no break-glass: no flag bypasses the gate; --force keeps its narrow overwrite-guard meaning."
- "AC-6 — forgery resistance: a touched/wrong-fingerprint key is rejected; proven by the adversarial gauntlet."
---

# Pipeline Activation Key — Dev-Spec v1.0

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Agents](99ed55fd.md) → [Argus — Agent Root Project](6dff0111.md) → **Pipeline Activation Key — Dev-Spec (fingerprint-as-key re...**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-active/agents/Argus — Agent Root Project/2ffdd9d6 — Pipeline Activation Key — Dev-Spec (fingerprint-as-key release authorization gate).md](../../00-tropo-nav/00-tropo-active/agents/Argus%20%E2%80%94%20Agent%20Root%20Project/2ffdd9d6%20%E2%80%94%20Pipeline%20Activation%20Key%20%E2%80%94%20Dev-Spec%20%28fingerprint-as-key%20release%20authorization%20gate%29.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-active/agents/Argus — Agent Root Project/2ffdd9d6 — Pipeline Activation Key — Dev-Spec (fingerprint-as-key release authorization gate).md](argo-os/00-tropo-nav/00-tropo-active/agents/Argus%20%E2%80%94%20Agent%20Root%20Project/2ffdd9d6%20%E2%80%94%20Pipeline%20Activation%20Key%20%E2%80%94%20Dev-Spec%20%28fingerprint-as-key%20release%20authorization%20gate%29.md)

**🔗 This file** — UID `2ffdd9d6` · type `dev-spec` · state `active` · status `locked`

**↔ Siblings (166):**
  - **under [Argus — Agent Root Project](6dff0111.md):** [Agent-workflow orchestration — 2025-2026 resear...](5b9f3d72.md) · [Argus A100 → A101 — Living Transfer (Vault Stub)](ec7efdf6.md) · [Argus A101 → A102 — Living Transfer (Vault Stub)](e9267564.md) · [Argus A102 → A103 — Living Transfer (Vault Stub)](6d54f00e.md) · [Argus A103 → A104 — Living Transfer (Vault Stub)](9da83008.md) · [Argus A104 → A105 — Living Transfer (Vault Stub)](8b64c634.md) · + 160 more

**📥 Cited by (1):**
- [Tropo-OS v1.71.0 — The Loop Primitive + the Pipeline Activatio...](7a24171d.md) — `7a24171d` (type `release`, via `foundation`)
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Tropo Governance (8dd772a0)](8dd772a0.md) |
| Member of | [Argus — Agent Root Project (6dff0111)](6dff0111.md) |

*The HOW for brief [f8cda3dd](f8cda3dd.md). Lean by intent — the key is simple by design. Realizes the principle: build the plain fingerprint now; it grows into signed provenance later without redesign.*

---

## Thesis

The pipeline runtime gates everything *inside* a run. The build + ship tools live *outside* it and can be invoked standalone — the cheat. Close it by making those tools **refuse to run without a key the runtime alone can mint**, where the key is a **fingerprint of the run** (unforgeable because it is derived from the work).

`build-release` is dumb software: **key present → run; key absent → halt.** No judgment. All judgment is in *when the runtime mints the key*.

## The key (definition)

When a pipeline-run legitimately reaches the **produce-release-folder** gate step — all prior steps `step_completed` + verified, **and** the doc-pipeline (4.5) and test-pipeline (4.6) triggers fired with their runs passing — the runtime writes a **release-authorization key** into the run folder:

`vault/pipeline-runs/<run>/release-authorization.json`

```
{ "activation_uid": "<uid>", "gate": "produce-release-folder",
  "fingerprint": "<sha256 over the run's ordered step_completed + verification_receipt + trigger events>",
  "minted_at_event": "<run.jsonl line count at mint>", "minted_by": "pipeline-runtime" }
```

The **fingerprint** is a SHA-256 over the run's work record (the ordered gate/receipt/trigger events). It cannot be produced without the run having done the work. (Today: plain hash, no signing — private-studio threat model. Later: wrap a signature around the same fingerprint — marketplace. Same primitive, two scales.)

## Acceptance criteria

1. **AC-1 — gate function (shared, single source).** New `vault/tools/lib/release_authorization.py` exposing `require_release_authorization(activation_uid, gate, *, require_human_signoff=False)`. It finds the pipeline-run (via `substrate_authored_by`), loads the key, **recomputes the fingerprint from the live run.jsonl and requires an exact match**, and (if `require_human_signoff`) requires a `human_signoff` accepted event. Returns on success; raises `ReleaseAuthorizationError` on any failure. **Fail-closed:** missing run, missing key, fingerprint mismatch, missing signoff, or any exception → refuse.
2. **AC-2 — runtime mints the key.** `9e7003b1.py` writes `release-authorization.json` at `step-complete` of the produce-release-folder gate step, only after the step's own gate (exit_criteria + the 4.5/4.6 triggers present) passes. Idempotent.
3. **AC-3 — build refuses without the key.** `a1b8c2d4.py` gains a **required** `--activation-uid`; calls `require_release_authorization(uid, "produce-release-folder")` before Step 0; refuses (exit nonzero) on failure. `--dry-run` is exempt (no artifact produced).
4. **AC-4 — public ship refuses without key + human key.** The Supabase upload (Step 11) calls `require_release_authorization(uid, "produce-release-folder", require_human_signoff=True)`; no signoff → local zip only, **no upload**.
5. **AC-5 — no break-glass.** No `--force`-style bypass of the gate. (The existing `--force` keeps its narrow meaning: overwrite a stale output dir — it does NOT bypass authorization.) Emergencies require an explicit human-signed run event, not a flag.
6. **AC-6 — forgery resistance (gauntlet gate).** A hand-written/`touch`-ed key with a wrong or absent fingerprint MUST be rejected. An adversarial test proves a forged key cannot pass.

## Committed substrate

- **NEW** `vault/tools/lib/release_authorization.py` — the shared gate + fingerprint compute/verify.
- **AMEND** `vault/tools/9e7003b1.py` (pipeline-runtime) — mint the key at the produce-release-folder gate.
- **AMEND** `vault/tools/a1b8c2d4.py` (build-release) — require `--activation-uid`; gate Step 0 (build) and Step 11 (ship).
- **NEW** `vault/tools/tests/test_release_authorization.py` — legit-key passes; forged/absent/mismatched key fails; ship without signoff skips upload.

## Out of scope (LATER, NOT NOW — per the brief)

Cryptographic signing, agent attribution, the provenance graph, generalization to all pipelines. The fingerprint is chosen so these wrap the same primitive later.

## Verification

Cold-boot: a fresh agent in the build dir, told only "ship this release," must be **unable** to produce a public release without a legitimate key. Plus the AC-6 forge test. Both must pass before close.

---

*Pipeline Activation Key — Dev-Spec v1.0 | UID `2ffdd9d6` | Argus A115 + Mike Maziarz (captain-mode delegation) | 2026-06-16*
