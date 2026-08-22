#!/usr/bin/env python3
"""---
uid: 4e8d1c60
type: tool
name: tropo-release
title: tropo-release.py — the one release command
status: active
owner: talos
extraction_scope: ship
schema_version: 2
created: '2026-08-16'
created_by: talos-t44
built_under: '2fae6312'
---

tropo-release.py — the operator facade for the one-prompt release.

Dev-spec 2fae6312 (locked), implementation step 8. This is the command the
spec means by gesture two: Mike locks scope, runs this once, and authorizes
the fire when asked. Everything between those three inputs is the machine's
problem, and if the machine needs a fourth input the scorecard records that as
a failure rather than a footnote.

    python3 vault/tools/tropo-release.py status   --run-dir <run>
    python3 vault/tools/tropo-release.py rehearse --run-dir <run>
    python3 vault/tools/tropo-release.py fire     --run-dir <run>

WHAT THIS FILE IS AND IS NOT. It composes; it does not decide. Phase gating
lives in `lib/release_gates`, progression in `lib/release_saga`, event
authorization in `lib/release_events`, the site in `lib/release_site`,
completion in `lib/release_completion`, and measurement in
`lib/release_metrics`. A facade that re-implemented any of those would become
a second opinion about what the release is doing, and the whole package exists
because two opinions is how v1.88 went sideways.

REHEARSAL IS NOT A DRY RUN OF FIRE. `rehearse` runs the full progression
against local fakes and writes the rehearsal scorecard to its own fixed path.
It cannot touch a provider, and it is never read as a real fire — separate
paths, separate mode field, and a schema that rejects the confusion.

WHY `fire` REFUSES HERE. The outward adapters — the credentialed GitHub,
Supabase and app-deploy remotes — exist only on Mike's machine and by design
are not in tracked substrate. On any other box `fire` refuses with a named
reason rather than pretending. That refusal is the honest state for a cloud
agent, and it is tested: a tool that silently no-ops the outward half is worse
than one that will not run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_completion as completion  # noqa: E402
from lib import release_metrics as metrics  # noqa: E402
from lib import release_saga as saga  # noqa: E402
from lib.release_gates import PHASES  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_OPERATIONAL = 3
EXIT_MISUSE = 4

#: The environment that must be present before an outward act is possible.
#: Named individually so the refusal can say WHICH one is missing rather than
#: "not configured", which sends an operator hunting.
FIRE_REQUIREMENTS = (
    "TROPO_GITHUB_TOKEN",
    "TROPO_SUPABASE_KEY",
    "TROPO_APP_DEPLOY_REMOTE",
)


def resolve_run_dir(vault: Path, release_plan_uid: str) -> Path:
    """The run folder a release plan opened at lock.

    AC9's command addresses the release by PLAN uid, which is the identity an
    operator has in hand; the run folder is an implementation detail they
    should never have to look up. Resolved from the plan's own
    release_pipeline_run_uid rather than from the index, because the index is
    per-machine derived state and a release must not depend on whether a
    rebuild has run.
    """
    import re as _re

    plan_path = Path(vault) / "vault" / "files" / f"{release_plan_uid}.md"
    if not plan_path.is_file():
        raise SystemExit(f"[MISUSE] release-plan {release_plan_uid} does not resolve")
    text = plan_path.read_text(encoding="utf-8", errors="replace")
    run_uid = _re.search(r"^release_pipeline_run_uid:\s*'?([0-9a-f]{8})'?", text, _re.M)
    if not run_uid:
        raise SystemExit(
            f"[MISUSE] release-plan {release_plan_uid} names no "
            "release_pipeline_run_uid — it has not been locked, and locking is "
            "gesture one"
        )
    run_path = Path(vault) / "vault" / "files" / f"{run_uid.group(1)}.md"
    if run_path.is_file():
        folder = _re.search(
            r"^run_folder:\s*'?([^'\n]+)'?", run_path.read_text(errors="replace"), _re.M
        )
        if folder:
            candidate = Path(vault) / folder.group(1).strip()
            if candidate.is_dir():
                return candidate
    # Fall back to the naming convention the lock uses, newest first.
    runs = sorted(
        (Path(vault) / "vault" / "pipeline-runs").glob(
            f"release-pipeline-{run_uid.group(1)}-*"
        ),
        reverse=True,
    )
    if runs:
        return runs[0]
    raise SystemExit(
        f"[MISUSE] no run folder on disk for run {run_uid.group(1)}"
    )


def _journal(run_dir: Path) -> saga.SagaJournal:
    path = run_dir / "release-saga.jsonl"
    identity = _identity(run_dir)
    return saga.SagaJournal.open(path, identity["saga_id"])


def _rows(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _identity(run_dir: Path) -> Dict[str, str]:
    for row in _rows(run_dir / "run.jsonl"):
        data = row.get("data") or {}
        if data.get("saga_id") and data.get("pipeline_run_uid"):
            return {
                "saga_id": str(data["saga_id"]),
                "pipeline_run_uid": str(data["pipeline_run_uid"]),
            }
    raise SystemExit(
        "[MISUSE] this run journal names no saga_id/pipeline_run_uid. Lock the "
        "release plan first — that is gesture one, and it is what creates the "
        "identity this command resumes from."
    )


def _missing_fire_requirements(environ) -> List[str]:
    return [name for name in FIRE_REQUIREMENTS if not environ.get(name)]


def cmd_status(args) -> int:
    run_dir = Path(args.run_dir)
    identity = _identity(run_dir)
    journal = _journal(run_dir)
    state = saga.current_state(journal)

    print("--- release %s (%s) ---" % (identity["pipeline_run_uid"], identity["saga_id"]))
    print("saga state      : %s" % state.get("state"))
    print("completed       : %d of %d checkpoints"
          % (len(state.get("completed") or []), len(saga.CHECKPOINTS)))
    pending = saga.next_checkpoint(journal)
    if pending is not None:
        print("next checkpoint : %s (%s)" % (pending.checkpoint_id, pending.incomplete_state))
    else:
        print("next checkpoint : none — every checkpoint is verified")

    verdict = completion.verify_completion(
        _completion_observers(run_dir),
        saga_id=identity["saga_id"],
        pipeline_run_uid=identity["pipeline_run_uid"],
    )
    print("completion      : %s" % ("verified" if verdict.complete else verdict.partial_state))
    if not verdict.complete:
        print("                  %s" % verdict.detail)
    print("phases          : %s" % ", ".join(PHASES))
    return EXIT_OK if verdict.complete else EXIT_REFUSED


def _completion_observers(run_dir: Path):
    """Reuse the live verifier's production observers rather than re-deriving."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "tropo_verify_release_live_for_facade", TOOLS / "tropo-verify-release-live.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    bus = _rows(run_dir / "bus-events.jsonl")
    return module.build_observers(run_dir, bus)


def cmd_rehearse(args) -> int:
    """Drive every checkpoint against local fakes and score the run.

    The point is not to prove the providers work — nothing here can. It is to
    prove the PROGRESSION works: that the machine walks from lock to complete
    without a human between, because that is the claim the scorecard makes.
    """
    run_dir = Path(args.run_dir)
    identity = _identity(run_dir)
    journal = _journal(run_dir)

    context = {
        "parent": "rehearsal-parent", "version": args.version, "size": "1",
        "staged_sha": "0" * 40, "tag": "v" + args.version.lstrip("v"),
        "package_sha": "rehearsal-package", "release_uid": "00000000",
        "site_commit": "1" * 40, "run_uid": identity["pipeline_run_uid"],
        "receipt_sha": "rehearsal-receipt", "mode": metrics.REHEARSAL,
        "scorecard_sha": "rehearsal-scorecard",
    }

    # The fake world PERSISTS, in its own file, because the real one does. An
    # in-memory fake that forgets between invocations makes every replay look
    # like a first run, which would let a broken idempotency contract rehearse
    # clean. It is deliberately not the saga journal: the machine must observe
    # a world, not its own record of what it believes about the world.
    world_path = run_dir / "rehearsal-world.json"
    world: Dict[str, Any] = {}
    if world_path.is_file():
        try:
            world = json.loads(world_path.read_text(encoding="utf-8"))
        except ValueError:
            world = {}

    performed: List[str] = []
    for checkpoint in saga.CHECKPOINTS:

        def observe(_c=checkpoint):
            fact = world.get(_c.checkpoint_id)
            return saga.Observation(present=fact is not None, fact=fact or {})

        def act(_c=checkpoint):
            world[_c.checkpoint_id] = {"rehearsal": True, "checkpoint": _c.checkpoint_id}
            world_path.write_text(
                json.dumps(world, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            performed.append(_c.checkpoint_id)
            return world[_c.checkpoint_id]

        result = saga.run_checkpoint(
            checkpoint.checkpoint_id, journal=journal, context=context,
            observe=observe, act=act,
        )
        if not result.ok:
            print("[REFUSED] %s — %s" % (checkpoint.checkpoint_id, result.detail))
            return EXIT_REFUSED
        print("[%s] %s" % (result.outcome, checkpoint.checkpoint_id))

    baseline = metrics.load_refusal_baseline(Path(args.vault))
    scorecard = metrics.build_scorecard(
        mode=metrics.REHEARSAL,
        saga_id=identity["saga_id"],
        pipeline_run_uid=identity["pipeline_run_uid"],
        release_version=args.version,
        principal_inputs=[
            {"input": "release_scope_locked", "at": args.scope_locked_at},
            {"input": "release_orchestrator_invoked", "at": args.started_at},
            {"input": "release_fire_authorized", "at": args.started_at},
        ],
        timestamps={
            "scope_locked_at": args.scope_locked_at,
            "orchestrator_started_at": args.started_at,
            "primary_live_at": args.started_at,
            "all_targets_live_at": args.started_at,
        },
        active_machine_seconds=args.active_seconds,
        observed_refusals=[],
        baseline=baseline,
    )
    target = metrics.scorecard_path(run_dir, metrics.REHEARSAL)
    target.write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    findings = metrics.validate_scorecard(
        scorecard, Path(args.vault) / "vault" / "schema" /
        "one-prompt-release-scorecard.schema.json"
    )
    if findings:
        print("[FAIL] rehearsal scorecard is invalid:")
        for finding in findings:
            print("  %s" % finding)
        return EXIT_OPERATIONAL

    print("rehearsal scorecard: %s (verdict %s)" % (target, scorecard["verdict"]))
    print("checkpoints performed: %d of %d" % (len(performed), len(saga.CHECKPOINTS)))
    return EXIT_OK if scorecard["verdict"] == "pass" else EXIT_REFUSED


#: Why a fire refused, as a stable code. Three refusals share one exit status,
#: so without distinct codes the guards are unobservable — removing the
#: credential check would look identical to leaving it in, and a mutation
#: proving that is what forced these codes to exist.
REFUSAL_MISSING_CREDENTIALS = "missing-credentials"
REFUSAL_AUTHORIZATION_REQUIRED = "authorization-required"


def fire_refusal(*, environ, authorized: bool):
    """The reason this fire will not proceed, as (code, message).

    Ordered deliberately: credentials first, because on a machine with no
    outward edges the authorization question is moot and asking it would
    invite an operator to authorize something that cannot happen.
    """
    missing = _missing_fire_requirements(environ)
    if missing:
        return (
            REFUSAL_MISSING_CREDENTIALS,
            "fire needs the credentialed outward edges and this machine is "
            "missing: %s. They live only on the release machine and are "
            "deliberately outside tracked substrate. Refusing is the honest "
            "state — a run that silently skipped the outward half would report "
            "a release nobody published." % ", ".join(missing),
        )
    if not authorized:
        return (
            REFUSAL_AUTHORIZATION_REQUIRED,
            "fire requires explicit authorization (--authorize). This is "
            "gesture three, and it is the one input the machine may never "
            "supply for itself.",
        )
    # AC5 (2cb346d6, 2026-08-21): the adapters ARE wired now, so this function
    # no longer carries a third refusal. None means PROCEED — the caller routes
    # to the wired implementation. The stub that stood here, and the test that
    # pinned it, were deleted in the SAME COMMIT as this routing, which is what
    # AC5 always required: a stub that outlives its truth misdirects every
    # reader, and a test asserting a fact that has stopped being true converts
    # a green suite into a false statement.
    return None




#: AC9 pilot (3f38521a): refusal codes -> telemetry taxonomy, stable mapping.
_TELEMETRY_REASON = {
    REFUSAL_MISSING_CREDENTIALS: ("environment", "dependency-missing",
                                  "non-retryable"),
    REFUSAL_AUTHORIZATION_REQUIRED: ("policy-gate", "gate-refused",
                                     "non-retryable"),
}


def _record_fire_refusal(identity: Dict[str, str], code: str, vault: Path) -> None:
    """Enqueue one telemetry record for a refused fire, then hand the queue
    to the local drainer at this safe boundary — after the verdict, off any
    observed-tool hot path. Never raises: telemetry is downstream evidence
    and cannot affect the refusal it records (3f38521a AC9)."""
    try:
        import importlib.util as ilu
        from lib import tropo_roots as _roots
        tools_dir = _roots.VAULT_DIR / "tools"
        spec = ilu.spec_from_file_location(
            "tool_telemetry", tools_dir / "lib" / "tool_telemetry.py")
        telemetry = ilu.module_from_spec(spec)
        spec.loader.exec_module(telemetry)
        category, reason, retryability = _TELEMETRY_REASON.get(
            code, ("policy-gate", "gate-refused", "non-retryable"))
        telemetry.record_refused(
            tool_uid="4e8d1c60",
            invocation_uid="%s:fire" % identity["saga_id"],
            operation_uid="%s:fire" % identity["pipeline_run_uid"],
            attempt=1,
            reason_category=category,
            reason_code=reason,
            retryability=retryability,
            segment_inputs=["argo-private"],
            gate_uid="4e8d1c60",
            harm_class="irreversible-write",
            release_run_uid=identity["pipeline_run_uid"],
        )
        drain_spec = ilu.spec_from_file_location(
            "tropo_drain_tool_telemetry",
            tools_dir / "tropo-drain-tool-telemetry.py")
        drainer_mod = ilu.module_from_spec(drain_spec)
        drain_spec.loader.exec_module(drainer_mod)
        drainer = drainer_mod.TelemetryDrainer(vault)
        drainer.ingest(telemetry.drain())
        drainer.seal_all()
    except Exception as exc:  # telemetry must never move a verdict
        print("WARN: fire telemetry handoff failed (non-blocking): %s" % exc,
              file=sys.stderr)


def cmd_fire(args) -> int:
    """Perform the outward release, or refuse for a named reason.

    Until 2026-08-21 this ALWAYS refused: the outward provider adapters were
    stubbed and `fire_refusal` had no success path, so a fully credentialed,
    --authorize'd run still returned the terminal stub refusal. AC5 of 2cb346d6
    required that stub to die in the same commit as the last adapter; the
    adapters landed and the stub did not, so this entry point still refused by
    construction while the real wiring sat one module away. Routed here.

    The history above deliberately does NOT spell the retired refusal code.
    AC5's verify is a grep for it across vault/tools/, and a grep cannot tell a
    live stub from prose about one — narrating the token here would force every
    future verifier to reason about whether the hit is real. History belongs in
    the commit message and the verification report, where it costs no gate its
    precision.
    """
    import os

    run_dir = Path(args.run_dir)
    identity = _identity(run_dir)

    refusal = fire_refusal(environ=os.environ, authorized=bool(args.authorize))
    if refusal is not None:
        code, message = refusal
        print("[REFUSED:%s] %s" % (code, message), file=sys.stderr)
        _record_fire_refusal(identity, code, Path(args.vault))
        return EXIT_REFUSED

    # Both facade gates cleared: the credentialed outward edges are present and
    # the operator supplied --authorize (gesture three, the one input the
    # machine may never supply for itself). Route to the wired implementation.
    #
    # Its own TTY confirmation stands DELIBERATELY and is not bypassed here.
    # Two gates on the one irreversible public act is correct, and a non-TTY
    # run refuses rather than silently auto-confirming.
    import importlib.util

    wired_path = Path(__file__).resolve().parent / "tropo-publish-release.py"
    spec = importlib.util.spec_from_file_location("tropo_publish_release", wired_path)
    wired = importlib.util.module_from_spec(spec)
    sys.modules["tropo_publish_release"] = wired
    spec.loader.exec_module(wired)

    class _FireArgs:
        version = getattr(args, "version", None)

    return wired.cmd_fire(_FireArgs())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The one release command.")
    parser.add_argument("--vault", default=".", help="vault root")
    # Gesture two, as the locked spec writes it: the operator names the release
    # PLAN and nothing else. With no subcommand this runs the orchestrator,
    # which proceeds to the outward edge and stops there to ask — so a bare
    # invocation can never publish by itself.
    parser.add_argument("--release-plan-uid")
    sub = parser.add_subparsers(dest="command", required=False)

    status = sub.add_parser("status", help="what is true about this release right now")
    status.add_argument("--run-dir", required=True)
    status.set_defaults(func=cmd_status)

    rehearse = sub.add_parser("rehearse", help="full progression against local fakes")
    rehearse.add_argument("--run-dir", required=True)
    rehearse.add_argument("--version", default="v1.89.0")
    rehearse.add_argument("--scope-locked-at", default="2026-08-16T20:00:00Z")
    rehearse.add_argument("--started-at", default="2026-08-16T20:05:00Z")
    rehearse.add_argument("--active-seconds", type=float, default=1.0)
    rehearse.set_defaults(func=cmd_rehearse)

    fire = sub.add_parser("fire", help="perform the outward release")
    fire.add_argument("--run-dir", required=True)
    fire.add_argument("--authorize", action="store_true")
    fire.set_defaults(func=cmd_fire)

    args = parser.parse_args(argv)

    if getattr(args, "release_plan_uid", None) and not getattr(args, "run_dir", None):
        args.run_dir = str(resolve_run_dir(Path(args.vault), args.release_plan_uid))

    if not getattr(args, "run_dir", None):
        parser.error("one of --release-plan-uid or a subcommand's --run-dir is required")
    if not Path(args.run_dir).is_dir():
        print("[MISUSE] no such run directory: %s" % args.run_dir, file=sys.stderr)
        return EXIT_MISUSE

    if getattr(args, "func", None) is None:
        # No subcommand: the orchestrator run. It reports state, then stops at
        # the outward edge for the one authorization the machine may not give
        # itself.
        code = cmd_status(args)
        args.authorize = False
        fire = cmd_fire(args)
        return code if fire == EXIT_OK else fire
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
