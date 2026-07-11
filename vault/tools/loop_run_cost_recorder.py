#!/usr/bin/env python3
"""
loop_run_cost_recorder.py — S11 loop-cost recording hook (Talos, v1.80, dev-spec be1979b6 S11).

Stamps a maintenance-registry loop entry's `last_run` + `last_run_cost` fields
in the SAME gesture, per boot-fast-path v0.5 §5.1.7 (the stamp rule) and
loop.capsule v1.3 (1248583d)'s `last_run_cost` schema:

    last_run_cost: { tokens, wall_min, usd_est, recorded_by, recorded_at }

Null-honest by construction — this script reads only what two real sources
expose and NEVER fabricates a number:

  usd_est  — read from <run_dir>/gateway_spend.json, written by the mitmproxy
             metering addon (loop_metering_gateway.py) from Anthropic's real
             per-response `usage`. The gateway persists a running dollar total
             ONLY (`{"spent_usd": <float>}`) — it does NOT persist token counts
             anywhere on disk, so `tokens` stays null at this build (there is
             no ground-truth source for it yet; do not guess from $ and a
             price table — that would be a fabricated figure, not a measured
             one). Absent/missing/corrupt gateway_spend.json -> usd_est: null.

  wall_min — computed from <run_dir>'s folder ctime to now, when --run-dir is
             given and the folder exists (the same ground-truth the wall-clock
             brake watchdog reads per loop.capsule §3). No run_dir -> null.

  tokens   — always null today (no ground-truth source exposed by the gateway
             or the harness at this build). Wiring a token source is future
             work, not something to fake here.

`--boot-inline` loops (e.g. Update Discovery) never dispatch a sa.* runner —
there is no gesture to meter. All three numeric fields stamp null; only
recorded_by/recorded_at are set, so the record is honest about *why* it's
empty (no dispatch cost was incurred) rather than silently absent.

Typing cure: `last_run` is written as a native YAML date-or-null (via
yaml.safe_dump), never the Python str "null" — closes the string-null class
loop.capsule v1.3 calls out explicitly.

Usage:
  # A dispatched sa.* runner just completed:
  python3 vault/tools/loop_run_cost_recorder.py stamp <loop-uid> \\
      --recorded-by <agent-gen> [--run-dir vault/loop-runs/<run>]

  # A boot-inline loop step (e.g. 5.1.6 update discovery) just ran in-process:
  python3 vault/tools/loop_run_cost_recorder.py stamp <loop-uid> \\
      --recorded-by <agent-gen> --boot-inline

  # Trace only (no write) — prints what WOULD be stamped:
  python3 vault/tools/loop_run_cost_recorder.py stamp <loop-uid> \\
      --recorded-by <agent-gen> --run-dir <path> --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


class RecorderError(Exception):
    pass


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_loop_entry(uid: str) -> dict:
    path = VAULT_FILES / f"{uid}.md"
    if not path.is_file():
        raise RecorderError(f"loop uid {uid!r} does not resolve to {path}")
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise RecorderError(f"{path} has no parseable frontmatter block")
    fm = yaml.safe_load(m.group(1)) or {}
    if not isinstance(fm, dict):
        raise RecorderError(f"{path} frontmatter did not parse to a dict")
    return {"frontmatter": fm, "body": m.group(2), "path": path}


def write_loop_entry(path: Path, frontmatter: dict, body: str) -> None:
    fm_yaml = yaml.safe_dump(
        frontmatter, default_flow_style=False, sort_keys=False,
        allow_unicode=True, width=200,
    )
    path.write_text(f"---\n{fm_yaml}---\n{body}")


def read_gateway_spend(run_dir: Path | None) -> float | None:
    """Ground-truth $ spend for this run, per loop_metering_gateway.py's persisted
    gateway_spend.json (`{"spent_usd": <float>}`). Null-honest: no run_dir, no
    file, or an unreadable/malformed file -> None. Never estimate from anything
    else — that is precisely the fabrication this hook exists to prevent.
    """
    if run_dir is None:
        return None
    spend_file = run_dir / "gateway_spend.json"
    if not spend_file.is_file():
        return None
    try:
        data = json.loads(spend_file.read_text())
        spent = data.get("spent_usd")
        return float(spent) if spent is not None else None
    except Exception:
        return None


def compute_wall_min(run_dir: Path | None) -> float | None:
    """Wall-clock minutes from the run folder's ctime to now — the same
    ground-truth source the brakes wall-clock watchdog reads (loop.capsule §3).
    No run_dir / folder missing -> None (never guess at elapsed time).
    """
    if run_dir is None or not run_dir.is_dir():
        return None
    try:
        started = run_dir.stat().st_ctime
        elapsed_sec = datetime.now().timestamp() - started
        if elapsed_sec < 0:
            return None
        return round(elapsed_sec / 60.0, 2)
    except Exception:
        return None


def action_stamp(loop_uid: str, recorded_by: str, run_dir: str | None,
                  boot_inline: bool, dry_run: bool) -> dict:
    entry = read_loop_entry(loop_uid)
    fm = entry["frontmatter"]

    if not fm.get("cadence"):
        raise RecorderError(
            f"loop {loop_uid!r} has no `cadence:` declared — it is not "
            f"registry-dispatched; the S11 stamp rule only applies to loops "
            f"the boot-fast-path §5.1.7 dispatch step actually fires."
        )

    run_dir_path = Path(run_dir) if run_dir else None

    if boot_inline or fm.get("runner") == "boot-inline":
        # No sa.* runner was spawned — no dispatch cost was incurred. Null-honest:
        # all three numeric members stay null; recorded_by/recorded_at still stamp
        # so the record states WHY it's empty rather than looking merely missing.
        tokens = wall_min = usd_est = None
    else:
        tokens = None  # no ground-truth token source exposed today (see module docstring)
        usd_est = read_gateway_spend(run_dir_path)
        wall_min = compute_wall_min(run_dir_path)

    last_run_cost = {
        "tokens": tokens,
        "wall_min": wall_min,
        "usd_est": usd_est,
        "recorded_by": recorded_by,
        "recorded_at": _now_iso(),
    }

    # Typing cure (loop.capsule v1.3): last_run is a native YAML date-or-null —
    # never the Python/YAML string "null". yaml.safe_dump renders a real
    # `datetime.date`/`None` as `2026-07-04` / `null` (bare), not `"null"`.
    last_run_value = datetime.strptime(_today(), "%Y-%m-%d").date()

    if dry_run:
        return {
            "loop_uid": loop_uid,
            "would_stamp": {"last_run": last_run_value.isoformat(), "last_run_cost": last_run_cost},
            "written": False,
        }

    fm["last_run"] = last_run_value
    fm["last_run_cost"] = last_run_cost
    fm["modified"] = _today()
    fm["modified_by"] = recorded_by
    write_loop_entry(entry["path"], fm, entry["body"])

    return {
        "loop_uid": loop_uid,
        "stamped": {"last_run": last_run_value.isoformat(), "last_run_cost": last_run_cost},
        "written": True,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="S11 loop-cost recording hook (1248583d / be1979b6 S11)")
    sub = p.add_subparsers(dest="action", required=True)
    st = sub.add_parser("stamp", help="stamp last_run + last_run_cost on a maintenance-registry loop entry")
    st.add_argument("loop_uid")
    st.add_argument("--recorded-by", required=True, help="the DISPATCHING agent's generation label, e.g. talos-t24")
    st.add_argument("--run-dir", default=None, help="loop-run folder (reads gateway_spend.json + folder ctime); omit for boot-inline")
    st.add_argument("--boot-inline", action="store_true", help="no sa.* runner was dispatched — stamp null-honest cost")
    st.add_argument("--dry-run", action="store_true", help="print intended stamp without writing")
    st.add_argument("--json", action="store_true", help="emit JSON to stdout")
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.action == "stamp":
            result = action_stamp(args.loop_uid, args.recorded_by, args.run_dir,
                                   args.boot_inline, args.dry_run)
        else:
            print(f"unknown action {args.action!r}", file=sys.stderr)
            return 2
    except RecorderError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("written"):
            print(f"stamped:{result['loop_uid']} last_run={result['stamped']['last_run']} "
                  f"last_run_cost={result['stamped']['last_run_cost']}")
        else:
            print(f"[dry-run] would stamp {result['loop_uid']}: {result['would_stamp']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
