---
uid: 'f01592dca86d'
type: task
title: "The spec lock appends its uid to the release plan's dev_spec_uids — the 'fills at spec-lock' mechanism that was never built"
status: new
state: active
owner: metis
assigned_to: talos
reviewer: argus
priority: high
member_of:
  - 2d5f9b04
created: '2026-09-03'
created_by: "metis-g118"
schema_version: 2
governed_by: 8dd772a0
extraction_scope: ship
relationships:
  - rel: references
    to: 301dce9d
  - rel: references
    to: aeb2df3d
tags: [release-pipeline, plan-lock, spec-lock, declared-but-not-wired, v1.95-candidate]
---

# The spec lock appends its uid to the release plan's `dev_spec_uids`

<!-- nav-block:start -->
**📍 Vault Path:** [2d5f9b04](2d5f9b04.md) → **The spec lock appends its uid to the release plan's dev_s...**
<!-- nav-block:end -->

**Found 2026-09-03 by metis-g118 while counting the v1.94 fan-in.** The release plan `301dce9d` carried
`dev_spec_uids: []   # fills at spec-lock, per stream, per the v1.92 pattern`. Fourteen specs were locked
against it between 08-29 and 09-02 and the list stayed empty, because `tropo-lock-dev-spec.py` (`aeb2df3d`,
owner talos) contains **no reference to the field**. `tropo-lock-release-plan.py` refuses an empty list by
design ("a valid digest for a release that attests to nothing"), so v1.94 could not have locked at any count
of done rows. Every "thirteen" on the board and in three letters came from letters; the plan's own field
never said anything. The plan owner populated the fourteen by hand on 2026-09-03 and wrote the reason on the
plan (§The fan-in list). This task builds the mechanism so the next plan does not depend on a hand.

**Builder:** Talos T61 (tool owner). **Reviewer:** Argus A168. **Verifier at close:** the release driver, non-author.

## Contract

**AC1 — the lock appends.** When `tropo-lock-dev-spec.py` locks a dev-spec that names a release plan (the
spec's plan binding — `member_of`, `refs`, or the lock's `--release-plan-uid`, whichever the tool already
resolves; say which), it appends the spec uid to that plan's `dev_spec_uids`, **block-aware** (the plan-lock's
own NO-GO item 5: a naive `^key:` match on a block value produced two `dev_spec_uids:` keys and YAML silently
kept the last). Verify: fixture plan with `dev_spec_uids: []`, lock a spec, assert exactly one key and one
entry; RED when the append is removed.

**AC2 — idempotent and order-preserving.** Locking the same spec twice leaves one entry; a second spec appends
after the first. Verify with two locks and a re-lock.

**AC3 — the inline-empty shape is handled.** `dev_spec_uids: []   # comment` (inline empty with a trailing
comment) is the shape v1.94 actually had; the append must replace it with a block list and keep the comment or
drop it deliberately. Verify on that literal line.

**AC4 — the plan lock can see its members.** After AC1 on a fixture, `tropo-lock-release-plan.py`'s
`gather_row` runs for the appended uid and its "lists no dev_spec_uids" refusal no longer fires; the refusal that
fires instead is the row-level one for an unclosed spec. Verify by calling the module.

**AC5 — drift check.** A validator check (or the plan-lock precondition) reports any locked dev-spec bound to a
plan that is absent from that plan's `dev_spec_uids`, as WARN (warn-safe, `deb77758`). Verify: plant the
mismatch, assert the line; remove the check, assert RED.

**AC6 — disclosed.** One sentence in the release-pipeline capsule or `RELEASING.md`: the spec lock maintains
the plan's member list; the plan owner no longer does it by hand.

## Notes

- v1.92's plan (`088e21aa`, cancelled) and v1.93's (`2e15ef76`, locked) may show how the list was maintained
  then — by hand, most likely. Read before assuming a "v1.92 pattern" existed as code.
- Not v1.94 scope; the hand-populated list carries v1.94.

## Reviewer read, AC1–AC3 (Argus A172, 2026-09-06 02:45Z, `b016db11a`)

**ACCEPT AC1–AC3.** Read the diff and probed the world, not only the fixtures: `resolve_plan_for_spec` on the three v1.95 specs (`f015de6b3a18`, `f015997f8d8e`, `af6c53df`) returns `vault/files/f015ba71c711.md` for each with no ambiguity; `append_uid_to_plan_list` on the REAL plan text is idempotent for a present uid (`changed=False`), appends a new one with exactly one `dev_spec_uids:` key, and the resulting frontmatter still parses. Suite `test_spec_lock_appends_plan_members` Ran 14 OK. The binding choice (spec `target_release` against plan `release_version`, refuse on zero-or-many live plans) is the right one and is stated in the docstring, as the task asked. Two refusals are correct by design: two keys in a plan, and an inline non-empty list. **Open: AC4 (plan lock sees its members), AC5 (drift WARN), AC6 (one disclosing sentence).** Verifier at close: the release driver, non-author, per the task header.

**Reviewer correction (Argus A172, 2026-09-06 06:45Z):** my ACCEPT of AC1 above was on the functions and a world probe of them; T63 found that `append_uid_to_plan_list` / `resolve_plan_for_spec` have no caller in `lock_dev_spec` — the lock does not append yet. Ruled (a): wire unconditionally, warn-safe (zero-or-many live plans → one WARN, lock proceeds; one plan → append through the governed write, in the lock's own commit; pre-lock plan states only; no opt-out flag). AC1 stays open until the call site lands; the known-negative is "remove the call, the one-plan arm goes red." I verified a declared primitive without finding its caller — the family, in my own review.

## Builder landing, AC1 call site + AC4–AC6 (Talos T63, 2026-09-06, on Mike's word "build all three now")

**AC1 is now actually wired** (A172's correction: the functions were accepted, the call site never existed). `lock_dev_spec` resolves the plan after the spec flip is planned, inside the same transaction: one live plan → `plan.patch` on the plan file in the same journaled apply as the spec, activation and run; zero or many live plans → one `[WARN]` quoting the resolver's reason, lock exit 0, plan untouched; a locked/terminal plan → the WARN, never a write (`PLAN_APPENDABLE_STATUSES`). No opt-out flag, per the ruling. The lock's own message now carries `plan=<uid|none>`. The tool itself never commits; the commit is the operator's, as before.

**AC4 found a real AC1 defect.** Calling the plan lock (not reading the text back) showed the append still refused "lists no dev_spec_uids": the entry pattern `-\s*` matched the frontmatter closer `---` as an entry named `--`, so a plan whose member list was its LAST key had the uid inserted into the body. Every prior fixture had a key after the list. Cured (`-\s+`, and the walk stops at the closer); test `test_the_member_list_as_the_last_frontmatter_key_stays_inside_the_frontmatter` is red on the old code.

**AC5** is `check_dev_spec_plan_membership_drift` in `tropo-validate.py`, registered in `main`, WARN-only. It loads the lock tool's own `resolve_plan_for_spec` rather than re-deriving the binding (one reader of one fact) and emits a WARN if that loader cannot run, so the skip is visible. The first live run took over five minutes (144 specs × 5,421 files, one scan per spec); cured with `scan_release_plans` once-per-check. Live studio today: 144 checked, 0 drift, 14 s.

**AC6** is one sentence at the top of `RELEASING.md` §The flow.

**Verify (all run 2026-09-06, non-piped exit codes):**
- `python3 -m unittest vault.tools.tests.test_spec_lock_call_site_appends_plan` — 5/5 (arms: one plan appended; re-lock no double; no live plan WARN + exit 0 + untouched; two plans WARN names both; locked plan WARN not write). **Mutation-proven:** with `plan.patch(plan_path, …)` replaced by `pass`, arm 1 fails on "the plan was not written — the call site is missing"; restored, green.
- `python3 -m unittest vault.tools.tests.test_spec_lock_appends_plan_members` — 15/15 (was 14; +the last-key shape).
- `python3 -m unittest vault.tools.tests.test_release_plan_lock_end_to_end` — includes `test_the_spec_locks_append_lets_the_plan_lock_see_its_members` (AC4); was RED before the entry-pattern cure.
- `python3 -m unittest vault.tools.tests.test_dev_spec_plan_membership_drift` — 9/9, including the registered-in-main guard.
- `test_lock_stamps_paired_test_specs_v194` still green alongside (124 across the four neighbouring suites).

**Verifier at close:** the release driver, non-author. Reviewer: Argus A172, non-author on the push.

**Reviewer read, AC1 (wired) + AC4–AC6 (Argus A172, 2026-09-06 08:00Z, `ad4be7967`): ACCEPT.** The call site exists in `lock_dev_spec` (`resolve_plan_for_spec` :1078, `append_uid_to_plan_list` :1095, same transaction, warn-safe on zero-or-many plans as ruled). Non-author runs: `test_spec_lock_call_site_appends_plan` Ran 5 OK (a real lock on a fixture, the arm that was missing), `test_spec_lock_appends_plan_members` 15 OK, `test_dev_spec_plan_membership_drift` 9 OK (AC5), `test_release_plan_lock_end_to_end` 92 OK (AC4), RELEASING.md carries the disclosing sentence (AC6). The AC1 defect AC4 exposed (a frontmatter closer matched as a block continuation) is cured in the same commit with its own arm. Verifier at close stays the release driver.
