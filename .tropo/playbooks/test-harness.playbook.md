# Release Test-Harness — Conductor Playbook

*Prototype Argus A115 2026-06-17 (design-brief [f13cc214]); amended to the **conductor** shape Argus A117 2026-06-19 per dev-spec [554624e5] (v1.74 Stranger-Walk Gate). Canonicalization to `vault/playbooks/<uid>.md` rides the v1.74 cycle.*

## Intent
You are verifying a Tropo release. Read this, execute it end-to-end, write `test-report.md` + the verdict, render the board. The human reads one report + glances one board instead of orchestrating a walk. This is the v2.0 "stranger walk" gate, made repeatable.

## Who runs this — the conductor vs. the strangers
- **Po (or a crew agent) is the CONDUCTOR** — runs Layer 1, *dispatches* the Layer-2 strangers, aggregates, reports to Mike, renders the board. The conductor has full studio context. That is correct for orchestration and **wrong for the walk itself.**
- **The Layer-2 strangers are fresh, NO-CONTEXT sub-agents** the conductor dispatches. Po must never *be* a stranger — Po knows where everything is and would pass a walk a real newcomer fails.
- **Record the conductor + each stranger's mode in the report.** A green regression run is NOT a passed stranger walk; don't let one masquerade as the other.

## Mike's election (per dev-spec 554624e5 D3)
The release flow ALWAYS ASKS Mike "run the cold-boot stranger-walk? [default YES]" at the cut. Default-run; Mike may override to skip; the choice is recorded in the release entry (`cold_walk: ran|skipped-by-mike@<version>` + `last_cold_walk_release`). This playbook's Layer 2 runs when L2 was elected. **No auto-classifier — the human decides at the gate.**

## Layer 1 — Mechanical regression (deterministic; run the script)
From the release root, run:

```
python3 .tropo/scripts/test-harness-check.py
```

Structural + integrity invariants (required files present · index parses · version stamped · capsules ship · manifest present · no private content leaked); prints PASS/FAIL per check, writes the mechanical section of `test-report.md`. Exit 0 = all pass. **Any FAIL here is a release defect — stop and report it; do not proceed.** L1 is universal (pure Python, no agent) — the downloader can always run it.

## Layer 2 — Cold stranger-walk (the honest gate; CAPABILITY-level, agent-driven)
Runs only when Mike elected it. This is NOT a recognition test ("can I *find* X") — it is a **capability test** ("can a newcomer actually *do* the things Tropo promises"). The cold agent operates inside its own isolated extract and **MAY create / modify / run** — writes are expected; the copy is discarded after. Declining a write *because* "it performs writes" is a mis-calibration, not a finding.

**Step B1 — Extract the SHIPPED zip into isolation.** Extract `dist/tropo-os-v<X.Y.Z>.zip` into a pristine temp dir (no studio siblings, no network) — the genuine "stranger downloaded it" surface, NOT the build-adjacent `testing/` mirror. *(Talos's clean-room tool, dev-spec 554624e5 §1, materializes this.)*

**Step B2 — Dispatch the cold strangers** (compose the persona machinery of [release-cold-boot-walk 6f3d2a18]: per-stranger filesystem-isolated clones; each sub-agent reads ONLY inside its clone — genuine cold context). Count per dev-spec D1: routine = 1 generalist; milestone (e.g. v2.0) = 3 personas (engineer / operator / enterprise).

Each stranger runs these checks, recording PASS / WARN / FAIL + a note + the **subsystem** each exercises (Captain's Briefing Req 2 — accumulate subsystem coverage; add a per-feature check each release):

| # | Check (capability, not recognition) | Subsystem | PASS bar |
|---|---|---|---|
| 1 | **Boot & orient** — boot via `START-TROPO.md`; the concierge greeting actually fires; name the capsule types + the L1 constraint (markdown + filesystem + LLM). | concierge | greeting fires + oriented |
| 2 | **Configure the studio** — run the concierge's STUDIO.md Bootstrap (§1.5) with test inputs; placeholders fill. | onboarding | no `<FILL>` remains *after* bootstrap |
| 3 | **Create the first agent** — via the concierge, create an agent → registered + indexed → **ask it a question → in-character answer**. | agents | agent exists, indexed, answers |
| 4 | **Tropo Work end-to-end** — create a project + a task (test inputs) → mark the task done → the lifecycle shows in the index; then clean up. | work | the work round-trips |
| 5 | **The engine runs** — run `npm test` / the validator + a rebuild *inside the extract*. | runtime/index | 0 FAILED |
| 6 | **Coordination round-trips** — emit an event + drain it (`query-events` / `check-events`). | events | the event is seen |
| 7 | **Governance is legible** — read `AGENTS.md`; state what you may / may not do from the governing files alone. | governance | rules statable from files alone |

**Calibration (binding — the v1.73 dry-run lesson):** intended template-state (`<FILL>` starters in STUDIO.md + the root CAPSULE.md) is the SHIPPED design, filled by the user (STUDIO.md at first boot via the concierge §1.5; the root CAPSULE.md on registration). It is **NOT a defect — do not WARN on it.** Instead EXERCISE it (check #2 fills it and verifies). A WARN is for genuine degradation a real newcomer would hit; a FAIL is a capability a newcomer genuinely cannot complete — never for the template doing its job, never for declining a write you were empowered to make.

## Step C — Aggregate + write the verdict (the EXACT shape the ship-gate reads)
The conductor aggregates a human report into `test-report.md` AND writes the **verdict JSON** that build-release Step 10.6 reads. The schema + path below are settled with Talos (swgate1) — write them EXACTLY; the gate keys on `overall`.

**Path (the gate reads this exact location):** `<RELEASES_DIR>/v<X.Y.Z>/cold-walk-verdict.json`

```json
{
  "schema_version": "1",
  "release_version": "X.Y.Z",
  "walk_date": "<date>",
  "conductor": "po",
  "l1_result": "PASS",
  "l2_personas": [
    {"persona": "engineer", "verdict": "PASS",
     "checks": [
       {"name": "boot-orient",   "subsystem": "concierge",     "status": "PASS", "note": "..."},
       {"name": "configure",     "subsystem": "onboarding",    "status": "PASS", "note": "placeholders filled"},
       {"name": "create-agent",  "subsystem": "agents",        "status": "PASS", "note": "agent answered in-character"},
       {"name": "tropo-work",    "subsystem": "work",          "status": "PASS", "note": "task round-tripped"},
       {"name": "engine",        "subsystem": "runtime/index", "status": "PASS", "note": "0 FAILED"},
       {"name": "coordination",  "subsystem": "events",        "status": "PASS", "note": "event seen"},
       {"name": "governance",    "subsystem": "governance",    "status": "PASS", "note": "rules statable"}
     ]}
  ],
  "overall": "PASS"
}
```

**`overall` is the only field the gate requires** (PASS | FAIL). **Rollup rule:** `overall: FAIL` iff L1 FAILs OR any L2 capability check #1–#6 FAILs (a newcomer genuinely cannot complete it). Otherwise `overall: PASS` — record any WARNs as per-check notes (the gate hard-blocks only on FAIL). **Template-state never drives FAIL or WARN** (per the §Layer-2 calibration). `overall: FAIL` → Step 10.6 `sys.exit(5)`, ship blocked. Missing verdict (or no `overall`) when L2 was elected → upload soft-blocked until the conductor writes it. The conductor may add `scores`, `report_paths`, etc. — the gate ignores extra fields, but **always emit `overall`** (the v1.73 dry-run wrote `verdict` instead and would have soft-blocked a real cut).

## Step D — Report to Mike (plain English)
Tell Mike the company picture, not UIDs: did a stranger boot it cold, what worked, what degraded, the one-line verdict + ship/hold. Failures first.

## Step E — Render the board
Render to the **working studio's** `boards/po/release-test-v<X.Y.Z>.html` (where Mike looks — NOT the throwaway extract, where the v1.73 dry-run left it). Self-contained HTML (OP-12 renderer; existing `boards/` convention): L1 N/6 · **the 7 L2 capability checks with their subsystem + PASS/WARN/FAIL + note** · per-stranger verdicts · overall verdict · the cold/skip provenance. Rich enough to read the studio's health at a glance — subsystem coverage visible, not just a single pass/fail line.

---
*Composes with: clean-room extract + ship-gate (dev-spec [554624e5], Talos) · persona machinery [6f3d2a18] · mechanical script [test-harness-check.py] · Pipeline Activation Key [2ffdd9d6] (same human-in-loop cut). The whole harness ships INSIDE the release, so a downloader self-verifies with the identical tool we gated on (L1 universal; L2 needs an agent — i.e. Claude Code, our audience).*
