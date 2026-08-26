#!/usr/bin/env python3
"""STUDIO-ROOT validator debt ratchet — NOT a release-surface check.

READ THIS BEFORE TRUSTING THE FILENAME. This file is called
`test_post_migration_release_clean.py` and the word "release" in that name is
wrong. It runs `tropo-validate` against the STUDIO ROOT — our own workshop
floor — and has never looked at a release extract. What ships is validated by
the release harness at stage and walked by Po at the cold walk; this suite
cannot see either.

The name is kept because it is only a name: renaming a file breaks every
historical record that cites it, and this studio's whole forward-only
discipline says you do not move a thing to make a label tidy. So the label is
corrected here, at the top, where a reader lands.

WHAT IT ACTUALLY MEASURES, and why that is still worth measuring: the studio's
own accumulated validator debt, as a RATCHET. Debt may be paid down freely; it
may not grow by accident. A commit that adds failures fails this suite.

WHY IT WAS RED FOR MONTHS. It compared against `BASELINE_FAIL_CEILING = 2`, a
constant captured at v1.74 ship that nothing ever updated, while the real count
drifted to 504. An alarm that cannot be silenced is an alarm nobody reads, and
this one had grown into a permanent red on the board — read by at least one
agent (me, 2026-08-08) as a release-blocking signal, which cost a morning until
the code said otherwise. The frozen constant is replaced by a recorded baseline
that a human updates deliberately, in a file beside this test, with the reason.

(talos-t39, 2026-08-08, at Metis G105's direction after the v1.86 cut-ready
call; the diagnosis is on gate c8416724.)
"""
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = ROOT / "vault" / "tools" / "tropo-validate.py"
BASELINE_PATH = Path(__file__).with_name("studio-validator-debt-baseline.json")

# v1.91 S1 AC4: the ONE debt predicate — this ratchet and the release-
# validation gate resolve the same question through the same function
# (lib/debt_rule.py). No private copy of the rule may live here.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.debt_rule import debt_verdict  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_debt_classes  # noqa: E402

#: Wall-clock ceiling for the validator subprocess, named so the number lives in
#: one place (velocity item 4). Bumped 120 -> 360 -> 900 chasing linear growth,
#: which is the shape a named constant does not fix on its own — so the note
#: that matters is the MEASUREMENT: the validator ran 244.9s standalone on
#: 2026-08-08 and 176.7s after the libyaml switch on 2026-08-09, and it runs
#: slower when the build invokes it concurrently with the rebuild's own
#: validator pre-step (velocity item 2, Vela's). 900s is ~5x the measured
#: standalone time; if it is ever bumped again, re-measure first and record the
#: number here rather than doubling on feel.
VALIDATOR_TIMEOUT_S = 900


def run_validate() -> tuple[int, int, str]:
    """Run tropo-validate against the STUDIO ROOT and return (passed, failed, output)."""
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=VALIDATOR_TIMEOUT_S,
    )
    output = result.stdout + result.stderr
    m = re.search(r"Summary[:\s]+(\d+) passed.*?(\d+) failed", output)
    if m:
        return int(m.group(1)), int(m.group(2)), output
    return 0, 0, output


def load_baseline() -> tuple[int, str]:
    """The recorded debt ceiling, or a refusal to guess one.

    Returns (ceiling, provenance). A missing or malformed baseline is NOT
    silently defaulted: a made-up ceiling is exactly how the v1.74 constant
    outlived its meaning.
    """
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        return int(data["failed"]), str(data.get("recorded_at", "unknown"))
    except (OSError, ValueError, KeyError, TypeError):
        return -1, "absent"


def load_class_baseline() -> tuple[dict, list, dict, bool]:
    """Per-class debt, the legacy exemption list, and the CURATED GATE LIST.

    Returns (classes, non_gating, gating, present). `present` is False when the
    baseline predates the per-class record, in which case the total-only ratchet
    below still runs unchanged — this addition may not turn into a reason the
    gate stops working on a studio that has not re-recorded yet.

    GATING IS AN OPT-IN LIST THAT NAMES ITS HARM, per Mike's standing ruling
    (`.tropo-studio/memory/entries/deb77758.md`, 2026-08-09): "A new refusal must
    name, in one sentence, the irreversible harm it prevents. If it cannot, it is
    a WARNING: visible, stated in the record, and the work proceeds."

    THIS REVERSES THE PRIOR DEFAULT, DELIBERATELY, AND HERE IS WHY THE PRIOR
    ARGUMENT DOES NOT HOLD. What stood here said an opt-in gate list would let
    new checks "arrive ungated by default and nobody would notice." That defends
    against losing DETECTION — but detection is never lost: every class is still
    classified, still printed, and any untriaged class that grows is now named
    explicitly under "reporting-only (never triaged)". Nothing hides. What the
    old default actually bought was ENFORCEMENT-BY-ACCIDENT: eighteen classes
    became release blockers without one of them ever being asked to name a harm,
    and the measured result was 1 finding in 148 that warranted stopping a ship,
    zero of the eighteen classes examining a byte that reaches a customer, and a
    663-byte overage in a private memory file halting a release whose total debt
    had gone DOWN six.

    The shape is the one this studio already uses for build refusals: every stop
    site declares priced/warn/misuse, and undispositioned sites are reported
    rather than silently defaulted. Same discipline, applied to validator classes.

    Curated by argus-a158 on Mike's explicit authorization, 2026-08-25. The plan
    Mike approved (v1.86 retrospective, velocity item 3) specified "gates on a
    curated class list"; the inversion to an exemptions allow-list happened during
    implementation with no decision record. This restores what was approved.
    """
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, [], {}, False
    classes = data.get("classes")
    if not isinstance(classes, dict):
        return {}, [], {}, False
    non_gating = data.get("non_gating_classes")
    if not isinstance(non_gating, list):
        non_gating = []
    gating = data.get("gating_classes")
    if not isinstance(gating, dict):
        gating = {}
    return (
        {str(k): int(v) for k, v in classes.items()},
        [str(x) for x in non_gating],
        {str(k): str(v) for k, v in gating.items()},
        True,
    )


def report_itemized_delta(output: str, baseline_classes: dict, non_gating: list,
                          gating: dict) -> int:
    """Print what moved, per class, and the actual lines for anything that grew.

    Returns the number of GATING findings added. This is the half of item 3 that
    replaces an hour of archaeology: the gate already parsed the output, so it
    can say which class grew and show the lines, instead of telling a human at
    midnight to go and read 2,000 lines of validator output for themselves.

    A class gates ONLY if it is named in `gating_classes` with the harm it
    prevents. Everything else reports. When `gating_classes` is absent the legacy
    behaviour is preserved exactly, so a studio that has not re-recorded keeps
    the gate it had.
    """
    current = studio_debt_classes.classify(output)
    moved = studio_debt_classes.delta(baseline_classes, current)
    if not moved:
        print("Per-class delta: no class moved.")
        return 0

    curated = bool(gating)
    excused = set(non_gating)

    def _gates(name: str) -> bool:
        if curated:
            return name in gating
        return name not in excused

    grew_gating: list[str] = []
    untriaged_growth: list[str] = []
    print("\nPer-class delta (against the recorded per-class baseline):")
    for name, (was, now) in moved.items():
        grew = now > was
        gates = _gates(name)
        mark = " " if not grew else ("!" if gates else "~")
        note = ""
        if grew and gates:
            note = "  [GATING — %s]" % gating.get(name, "recorded decision")
        elif grew and curated:
            note = "  [reporting-only — not on the gate list, never triaged]"
        elif grew and name in excused:
            note = "  [non-gating by recorded decision]"
        elif now == 0 and was > 0:
            # A class that vanishes is not automatically good news.
            note = "  [class produced NO findings — verify the check still runs]"
        print(f"  {mark} {name}: {was} -> {now}{note}")
        if grew and gates:
            grew_gating.append(name)
        elif grew and curated:
            untriaged_growth.append(name)

    if untriaged_growth:
        # The whole objection to an opt-in gate list was that new checks would
        # "arrive ungated and nobody would notice." This is the answer: they are
        # named, every run, in the one place a human is already reading.
        print("\nReporting-only classes that grew (visible, not fatal — triage if "
              "one of these names a harm worth stopping a ship for):")
        for name in untriaged_growth:
            print(f"    ~ {name}")

    if grew_gating:
        print("\nThe findings that grew, verbatim:")
        for name, lines in studio_debt_classes.findings_for(output, grew_gating).items():
            print(f"\n  --- {name} ---")
            for line in lines[:20]:
                print(f"    {line}")
            if len(lines) > 20:
                print(f"    ... and {len(lines) - 20} more in this class")
    return sum(
        current.get(name, 0) - baseline_classes.get(name, 0) for name in grew_gating
    )


def main() -> int:
    if not VALIDATOR.exists():
        print(f"FAIL — validator not found at {VALIDATOR.relative_to(ROOT)}")
        return 1

    ceiling, recorded_at = load_baseline()
    if ceiling < 0:
        print(f"FAIL — no recorded baseline at {BASELINE_PATH.name}.")
        print("       This suite refuses to invent a ceiling. Run tropo-validate,")
        print("       record the count with a reason, and commit the baseline.")
        return 1

    print("Scope: the STUDIO ROOT, not a release surface.")
    print("Running tropo-validate (this may take ~2-3 min)...")
    try:
        passed, failed, output = run_validate()
    except subprocess.TimeoutExpired:
        print(f"FAIL — tropo-validate timed out after {VALIDATOR_TIMEOUT_S}s")
        return 1

    print(f"Result: {passed} passed, {failed} failed "
          f"(recorded studio debt: {ceiling}, from {recorded_at})")

    baseline_classes, non_gating, gating, have_classes = load_class_baseline()
    # Assigned before the branch: the verdict below reads it unconditionally, and
    # the `not have_classes` path used to reach that read with the name unbound —
    # a NameError on exactly the studio this branch exists to keep working.
    gating_growth = 0

    if not have_classes:
        # A baseline recorded before per-class tracking existed. Say so and fall
        # through to the total-only ratchet: an upgrade to the reporting must not
        # become a new way for the gate to refuse.
        print(f"INFO — {BASELINE_PATH.name} has no `classes` record, so this run "
              "reports the total only.")
        print("       Add one with `--record` to get the itemized delta.")
    else:
        gating_growth = report_itemized_delta(output, baseline_classes, non_gating,
                                              gating)
        if gating_growth > 0:
            _v = debt_verdict(failed, ceiling, gating_growth)
            print(f"\nFAIL — {_v.reason}.")
            print("       The classes and the lines are printed above; no archaeology")
            print("       needed. Every class that gates is named in `gating_classes`")
            print(f"       in {BASELINE_PATH.name}, together with the irreversible harm")
            print("       it prevents. If the growth above does not match that harm,")
            print("       the gate is wrong and the entry should come off the list —")
            print("       that question comes before 'can we turn it off'.")
            return 1
        if gating:
            print(f"\n({len(gating)} class(es) gate, each naming its harm; every other "
                  "class reports and never stops a build — per deb77758.)")
        elif non_gating:
            print(f"\n({len(non_gating)} class(es) excused from gating by recorded "
                  "decision; growth in them is reported above, never fatal.)")

    # v1.91 S1 AC4: the ONE predicate decides; this site prints its verdict.
    verdict = debt_verdict(current_failed=failed, ceiling=ceiling,
                           gating_growth=gating_growth)
    print(f"{'PASS' if verdict.ok else 'FAIL'} — {verdict.reason}.")
    return 0 if verdict.ok else 1


def record_baseline() -> int:
    """Re-record the baseline, totals AND per-class, from one live run.

    Deliberately a flag on this file rather than a separate tool: the numbers
    must come from the same parse the gate uses, or the recorded baseline and
    the thing measured against it can disagree about what a class even is.
    """
    print("Recording a fresh studio debt baseline from a live validator run...")
    passed, failed, output = run_validate()
    classes = studio_debt_classes.classify(output)
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data["passed"] = passed
    data["failed"] = failed
    data["classes"] = dict(sorted(classes.items()))
    data.setdefault("non_gating_classes", [])
    data["recorded_at"] = _dt.date.today().isoformat()
    BASELINE_PATH.write_text(
        json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Recorded {failed} failed across {len(classes)} class(es) "
          f"into {BASELINE_PATH.name}.")
    print("Set `recorded_by` and `reason` by hand — a baseline with no reason is "
          "the ceiling that rises quietly.")
    return 0


if __name__ == "__main__":
    if "--record" in sys.argv:
        sys.exit(record_baseline())
    sys.exit(main())
