# Release Test-Report — mechanical layer (PASS)

- release_dir: `/Users/maz/git/tropo-releases/v1.86.0/builds/tropo-os-v1.86.0`
- mode: mechanical (deterministic regression; the guided stranger-walk is the playbook's other half)
- result: **11/11 checks passed**
- stats: {'index_rows': 475, 'uids': 475, 'version': 'v1.86.0', 'capsule_defs': 1}

| Check | Verdict | Detail |
|---|---|---|
| required files/dirs present | ✓ PASS | all present |
| index parses (every row valid JSON + uid/type) | ✓ PASS | 475 rows, 0 malformed |
| version stamped | ✓ PASS | version = v1.86.0 |
| capsule definitions ship | ✓ PASS | 1 capsule-definition entries in vault/files |
| MANIFEST present | ✓ PASS | MANIFEST.md |
| no private/reference-only content leaked | ✓ PASS | clean |
| .tropo/playbooks has at least one .md playbook | ✓ PASS | 18 playbooks |
| START-TROPO.md non-empty | ✓ PASS | 27 non-blank lines |
| tropo-validate.py present and non-empty | ✓ PASS | present (642209 bytes) |
| shipped Python lib import closure | ✓ PASS | 86 tools, 66 lib modules resolved |
| golden-output snapshot (not seeded — skip) | ✓ PASS | no expected-checks.json; seed with check names to activate |

---

# Layer 2 — Cold stranger-walk (PASS)

- walk_date: 2026-08-08
- conductor: **po** — full studio context; orchestration only, did **not** walk
- strangers: **1 generalist** (routine release per dev-spec 554624e5 D1)
- stranger mode: **cold, no-context sub-agent**, dispatched against a pristine extract of `dist/tropo-os-v1.86.0.zip`, fenced from `builds/` · `dist/` · `testing/`
- clone: `coldwalk/tropo-os-v1.86.0` (discarded after the walk)
- result: **PASS** — 5 PASS · 2 WARN · 0 FAIL

> A green L1 regression run is not a passed stranger walk. These are recorded separately and the conductor never walked its own release.

## The seven capability checks

| # | Check | Subsystem | Verdict | Note |
|---|---|---|---|---|
| 1 | boot-orient | concierge | ✓ PASS | Boot chain resolved with no dead links; greeting fired with live status (3 system agents, 0 user agents, 475 index entries); capsule types + the markdown/filesystem/LLM constraint stated correctly |
| 2 | configure | onboarding | ✓ PASS | STUDIO.md Bootstrap filled all 5 frontmatter + 3 body placeholders; no `<FILL` remains after bootstrap |
| 3 | create-agent | agents | ⚠ WARN | Bar met — agent created, registered, indexed, answered in character. Path degraded: `vault/templates/` does not ship, and the skill's shared-uid rule is contradicted by the rebuilder |
| 4 | tropo-work | work | ✓ PASS | Project + task created, landed active, closed, index reflected closure without hand-editing; cleaned up via governed soft-delete |
| 5 | engine | runtime/index | ⚠ WARN | `tropo-test.py` 103 passed / **0 FAILED**; rebuild completed all 5 stages. WARN: the rebuild's validator pre-step omits `--customer`, so a pristine install is told its substrate is broken |
| 6 | coordination | events | ✓ PASS | 3 crew events emitted and drained with correct fields; clean empty result on the fresh vault |
| 7 | governance | governance | ✓ PASS | Permission model, file hierarchy, override order and authority model all statable from the governing files alone |

**Subsystem coverage this release:** concierge · onboarding · agents · work · runtime/index · events · governance (7/7)

## Conductor-verified findings

Both WARNs were reproduced independently by the conductor rather than taken on the stranger's word.

1. **`vault/templates/` does not ship.** Absent from the extract, absent from the build tree, **0 entries in the zip**, 0 template-typed index rows, 1 stray `.template.md` studio-wide. This is an extraction-scope omission, not a broken pointer. It breaks the `create-executive-agent` template steps, the concierge's §1.5b mission-brief offer, `vault/templates/AGENTS.md` + `CAPSULE.md`, and the task capsule's `mint_template`.
2. **False "broken substrate" alarm on a pristine install.** `tropo-validate.py` default → `100 passed, 284 failed`; the same validator with `--customer` → `103 passed, 0 failed`. `tropo-rebuild-vault.py` invokes the pre-step without `--customer` and exits non-zero. The substrate is clean; the alarm is a mode bug in the wrapper.

## Recommended follow-ups (none ship-blocking)

1. Ship `vault/templates/`.
2. Resolve the shared-uid contradiction — `create-executive-agent` Validation Check 4 vs the rebuilder's cross-document UID collision abort. The shipped `agents/example/` already uses distinct UIDs, so the skill is the stale side.
3. Pass `--customer` from the rebuild's validator pre-step.
4. Add `--lifecycle` + `--source-uid` to every kernel-quoted `tropo-emit-event.py` invocation.
5. Refresh stale pointers in `TROPO-CONTROL.md` / `STUDIO.md` (`channels/ops.md`, `system/updates/pending/`, the 1.49.0 version stamp).
6. `agents/example/` activation references `example-briefing.md`, which does not exist.

---

## Verdict

| Layer | Result |
|---|---|
| L1 mechanical | **PASS** (11/11) |
| L2 cold stranger (generalist) | **PASS** (5 PASS · 2 WARN · 0 FAIL) |
| **Overall** | **PASS — clear to ship** |

Rollup per the harness rule: `overall: FAIL` only if L1 fails or a capability check #1–#6 fails. Neither happened. WARNs are recorded as notes and do not block.

Verdict JSON: `cold-walk-verdict.json` · persona report: `coldwalk/reports/generalist-report.json` · board: `boards/po/release-test-v1.86.0.html`

