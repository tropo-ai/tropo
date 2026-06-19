# Release Test-Harness — Playbook

*Prototype, Argus A115 2026-06-17. Design-brief [f13cc214]. Lock-ready for the v1.72 cycle, which migrates this to the canonical `vault/playbooks/<uid>.md` shape (with a thin pointer here, per the v1.69 playbook-unification pattern) and wires it into Build-Release Phase 3.*

## Intent
You are verifying a Tropo release. Read this, execute it end-to-end, and write `test-report.md`. The human reads one report instead of orchestrating a walk. This is the v2.0 "stranger walk" gate, made repeatable.

## Two modes — declare which you are
- **Regression mode (default):** you are Po or another crew agent. Fast, repeatable. Answers *"does this release still work?"* Run it every release.
- **Stranger mode:** you are a genuinely cold agent with NO studio context. Answers *"can a stranger navigate this?"* — the honest v2.0 gate. Use periodically (or the human does it).
- **Record which mode in the report.** A green regression run is NOT a passed stranger walk; don't let one masquerade as the other.

## Layer 1 — Mechanical regression (deterministic; run the script)
From the release root, run:

```
python3 .tropo/scripts/test-harness-check.py
```

It checks the structural + integrity invariants (required files present · index parses · version stamped · capsules ship · manifest present · no private content leaked), prints PASS/FAIL per check, and writes the mechanical section of `test-report.md`. Exit 0 = all pass. **Any FAIL here is a release defect — stop and report it; do not proceed to ship.**

*(v1.1 hardening, queued: golden-output snapshots — diff actual-vs-expected per release so "regression" is a real diff.)*

## Layer 2 — Guided walk (your judgment)
Then walk the release as the onboarding flow intends, recording PASS / WARN / FAIL + a note for each. (This is the cold-boot-test, [cb007e57], unified here.)

**Orientation:** read `.tropo/orientation.md` — can you name the capsule types and the constraint (markdown + filesystem + LLM)?
**Navigation:** find + read the index (`vault/00-index.jsonl`); read one random vault entry — can you identify its type, owner, status? Read one capsule from `.tropo/capsules/`.
**Onboarding:** find the onboarding/boot path (`START-TROPO.md` → `CLAUDE.md`/concierge); can you follow the first 3 steps without error?
**Task:** create a scratch task via the documented action; clean it up after.
**Governance:** read `AGENTS.md` — can you state what you're allowed to do and not, from the governing files alone?

## Write the report
Append your Layer-2 results to `test-report.md` (Layer 1 already wrote its section). End with:
- **Mode:** regression | stranger
- **Mechanical:** N/6 (from Layer 1)
- **Walk:** the per-check PASS/WARN/FAIL list
- **Verdict:** PASS (all green) · WARN (walks degraded but functional) · FAIL (any mechanical FAIL or a blocking walk FAIL)

The human reads the verdict + the failures. Done.

---
*Composes with: cold-boot-test [cb007e57] · cold-boot-action-test · the Build-Release playbook [9d58acc8] Phase 3. The mechanical script ships in the release, so a stranger's download can self-verify itself.*
