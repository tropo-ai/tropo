#!/usr/bin/env python3
"""
---
uid: 5c1ff4bb
name: tropo-run-suites
type: tool
title: "tropo-run-suites — run the studio's test suites, because nothing did"
status: active
owner: metis
domain: "Executes the Python test suites under vault/tools/tests/ and reports which are green, which are red, and which could not run. The studio had 115 of them and no runner."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-run-suites.py"
script_path: vault/tools/tropo-run-suites.py
spawnable_by:
  - all-executives
output:
  type: object
  description: "human table on stdout; --json for a machine record; exit 1 if any suite is red"
created: '2026-08-04'
created_by: metis-g100
modified: '2026-08-04'
modified_by: metis-g100
version: "1.0"
schema_version: 2
extraction_scope: ship
---
"""

# WHY THIS EXISTS.
#
# On 2026-08-03 this studio had 115 test files under vault/tools/tests/, no CI,
# no git hooks, and no runner. `npm test` runs the VALIDATOR, which checks
# substrate shape and never executes a single one of those suites. So every one
# of them ran only when an agent happened to remember.
#
# The cost was not theoretical. tropo-activate.py shipped 18/18 green and was
# broken hours later by another agent's commit changing a required argument.
# Its suite went to fourteen failures and NOTHING TOLD ANYONE. It was found by
# accident, while rehearsing an unrelated retirement, roughly an hour before a
# live agent would have hit it.
#
# That is the same defect the fleet-health check had: an instrument that is
# correct and reports where nobody is looking. This studio spent a full session
# diagnosing that pattern and then built four more instruments with it.
#
# WHAT THIS DELIBERATELY DOES NOT DO: it does not maintain a baseline of
# "expected failures". A baseline is how a suite becomes green while broken —
# the exact failure mode of the twenty-five tests that were green for months
# while pinning a contract the principal had ruled out. Environmental skips are
# declared HERE, in the open, with a stated reason, and they are reported as
# SKIP rather than folded into a pass count.

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = STUDIO_ROOT / "vault" / "tools" / "tests"
# test_index_lifecycle takes 181.8s of real work and passes all 75 tests. At a
# 180s ceiling it reported TIMEOUT — a red board entry decided by 1.8 seconds
# and by whatever else the machine was doing. A budget a passing suite loses to
# by 1% is measuring load, not correctness.
DEFAULT_TIMEOUT = 300

# Suites that cannot pass on an ordinary developer machine, each with the reason
# stated. Named here rather than silently tolerated, so the list is auditable and
# a suite cannot quietly join it. If a reason stops being true, delete the line.
ENVIRONMENTAL_SKIPS = {
    "test_authority_chain.py":
        "needs a Cursor Cloud machine for the harness-plant fixtures and a live "
        "ssh-agent; documented baseline is 1 failure / 6 errors on a Mac. "
        "Retiring with ADR-066 — delete this entry when the chain goes.",
}

_VERBOSE_RESULT = re.compile(
    r"^.+ \(.+\) \.\.\. "
    r"(?:ok|FAIL|ERROR|expected failure|unexpected success|skipped .+)$"
)


def discover(pattern: str | None) -> list[Path]:
    found = sorted(p for p in TESTS_DIR.glob("test_*.py") if p.is_file())
    if pattern:
        found = [p for p in found if pattern in p.name]
    return found


def _tests_executed(output: str) -> int:
    """Read a final unittest count, or completed verbose rows before a timeout."""
    for line in output.splitlines():
        if line.startswith("Ran ") and " test" in line:
            try:
                return int(line.split()[1])
            except (ValueError, IndexError):
                pass
    return sum(bool(_VERBOSE_RESULT.match(line)) for line in output.splitlines())


def _terminate_process_group(
    process: subprocess.Popen[str],
) -> None:
    """Stop a timed-out suite and every fixture process it spawned."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait()


def _cleanup_completed_process_group(process: subprocess.Popen[str]) -> None:
    """Do not let a completed suite leave pipe-holding descendants behind."""
    if os.name != "posix":
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _read_capture(stream) -> str:
    stream.flush()
    stream.seek(0)
    return stream.read()


def _suite_env() -> dict:
    """Put the studio root and vault/tools on PYTHONPATH for every suite.

    Suites are invoked as scripts, which puts the SCRIPT's directory on
    sys.path and never the cwd. A suite importing `vault.tools.tests.X` or
    `lib.X` therefore dies at import with ModuleNotFoundError and exits
    non-zero before a single assertion runs — which this runner reports as
    RED with zero tests, indistinguishable from a suite that ran and failed.
    Seven suites were red for that reason alone, and two of them were hiding
    real failures behind it.
    """
    env = os.environ.copy()
    roots = [str(STUDIO_ROOT), str(STUDIO_ROOT / "vault" / "tools")]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(roots + ([existing] if existing else []))
    return env


def run_one(path: Path, timeout: int) -> dict:
    started = time.monotonic()
    with (
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout_capture,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr_capture,
    ):
        try:
            proc = subprocess.Popen(
                [sys.executable, str(path)],
                stdout=stdout_capture,
                stderr=stderr_capture,
                text=True,
                cwd=str(STUDIO_ROOT),
                env=_suite_env(),
                start_new_session=os.name == "posix",
            )
            proc.wait(timeout=timeout)
            _cleanup_completed_process_group(proc)
            out = _read_capture(stdout_capture) + _read_capture(stderr_capture)
            ran = _tests_executed(out)
            return {
                "suite": path.name,
                "status": "green" if proc.returncode == 0 else "RED",
                "tests": ran,
                "seconds": round(time.monotonic() - started, 1),
                "detail": "" if proc.returncode == 0 else _first_failure(out),
            }
        except subprocess.TimeoutExpired:
            _terminate_process_group(proc)
            out = _read_capture(stdout_capture) + _read_capture(stderr_capture)
            return {
                "suite": path.name,
                "status": "TIMEOUT",
                "tests": _tests_executed(out),
                "seconds": round(time.monotonic() - started, 1),
                "detail": f"exceeded {timeout}s",
            }
        except Exception as exc:  # never let one suite stop the sweep
            return {"suite": path.name, "status": "ERROR", "tests": 0,
                    "seconds": round(time.monotonic() - started, 1),
                    "detail": f"{type(exc).__name__}: {exc}"}


def _first_failure(out: str) -> str:
    """The first FAIL/ERROR line — enough to know WHAT broke without the dump."""
    for line in out.splitlines():
        if line.startswith(("FAIL:", "ERROR:")):
            return line.strip()[:120]
    for line in out.splitlines():
        if line.startswith("FAILED"):
            return line.strip()[:120]
    return "non-zero exit, no unittest summary found"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the studio's test suites. Nothing else does.")
    ap.add_argument("--filter", help="substring match on suite filename")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--json", action="store_true", help="machine-readable record")
    ap.add_argument("--include-environmental", action="store_true",
                    help="also run the suites that need a specific machine")
    args = ap.parse_args()

    suites = discover(args.filter)
    if not suites:
        print("no suites matched", file=sys.stderr)
        return 2

    results, skipped = [], []
    for path in suites:
        if path.name in ENVIRONMENTAL_SKIPS and not args.include_environmental:
            skipped.append({"suite": path.name,
                            "reason": ENVIRONMENTAL_SKIPS[path.name]})
            continue
        results.append(run_one(path, args.timeout))

    green = [r for r in results if r["status"] == "green"]
    bad = [r for r in results if r["status"] != "green"]
    total_tests = sum(r["tests"] for r in results)

    if args.json:
        print(json.dumps({"green": len(green), "red": len(bad),
                          "skipped": len(skipped), "tests": total_tests,
                          "results": results, "environmental_skips": skipped}))
        return 1 if bad else 0

    for r in sorted(results, key=lambda r: (r["status"] == "green", r["suite"])):
        mark = "  ok  " if r["status"] == "green" else f" {r['status']} "
        print(f"{mark} {r['suite']:<56} {r['tests']:>4} tests  {r['seconds']:>6}s")
        if r["detail"]:
            print(f"        {r['detail']}")
    for s in skipped:
        print(f" SKIP  {s['suite']:<56} — {s['reason'][:70]}")

    print()
    print(f"{len(green)} green · {len(bad)} RED · {len(skipped)} skipped "
          f"· {total_tests} tests executed")
    if bad:
        print("\nRED suites, in the order they were found:")
        for r in bad:
            print(f"  {r['suite']}: {r['detail']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
