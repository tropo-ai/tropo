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
import datetime as _dt
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
from lib.governed_path import UID_HEX_PATTERN  # noqa: E402
from lib.release_gates import PHASES, PREFLIGHT_EVIDENCE_FILENAME  # noqa: E402

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
        # refusal: misuse — the named release-plan does not resolve
        raise SystemExit(f"[MISUSE] release-plan {release_plan_uid} does not resolve")
    text = plan_path.read_text(encoding="utf-8", errors="replace")
    # accepts-both (UID_SHAPES): an unanchored 8-only capture truncated a
    # composite 12-hex release_pipeline_run_uid and resolved the wrong file.
    run_uid = _re.search(
        r"^release_pipeline_run_uid:\s*'?(%s)'?" % UID_HEX_PATTERN, text, _re.M
    )
    if not run_uid:
        # refusal: misuse — the release-plan names no pipeline run to resume from
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
    # refusal: misuse — no run folder exists on disk for that run
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
    # refusal: misuse — the run journal names no saga_id or pipeline_run_uid
    raise SystemExit(
        "[MISUSE] this run journal names no saga_id/pipeline_run_uid. Lock the "
        "release plan first — that is gesture one, and it is what creates the "
        "identity this command resumes from."
    )


def _run_is_bootstrapped(run_dir: Path) -> bool:
    """3d8d4351 §2: the run carries an activation in run.state.json.

    The SAME fact run_is_walkable reads (tropo-release-run.py), read here so
    the stamp can never land on a run that never bootstrapped — the wedge
    whose first movers were two pre-bootstrap leg_attested rows. One home
    per fact: this reads the state file's activation_uid exactly as the
    walker's own 4.2 note describes it.
    """
    state_path = run_dir / "run.state.json"
    if not state_path.is_file():
        return False
    try:
        body = json.loads(state_path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return False
    return bool(str(body.get("activation_uid") or ""))



def _chokepoint_mint_uid() -> str:
    """3d430852: route raw-mint uids through the collision-checked chokepoint.

    This uid lands in a GOVERNED record (run journal / release event), so it
    follows the ADR-050 ruling — not the run-record deferral class.
    """
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        "_mint_uid_chokepoint",
        Path(__file__).resolve().parent / "tropo-mint-id.py")
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod.mint(1, kind="file", studio_root=Path(__file__).resolve().parents[2])[0]

def _record_orchestrator_invoked(run_dir: Path, identity: Dict[str, str],
                                 invoked_via: str = "bare") -> bool:
    """v1.91 S2 AC1/AC5 (3fb41c99): the moment the orchestrator runs.

    3d8d4351 §2 — TWO cures folded into the stamp:
      * the SHARED BOOTSTRAP GUARD: this function itself refuses unless the
        run is bootstrapped (activation present in run.state.json), so BOTH
        callers (the bare path and the fire path) share the cure and the
        bare-stamp-that-became-d9025a97's-fourth-row cannot recur.
      * the MACHINE-AUTHORSHIP cure: the row's actor is the ENGINE (this
        tool's own uid), never a human name — the v1 writer forged
        "actor": "mike" and every consumer inherited the lie. The label
        slot carries the readable name; invoked_via marks the path.

    Argus A154 could not locate this event's honest emit point before he
    retired and told his successor to stop and ask rather than invent one.
    Found: this file's own docstring names it -- "Mike locks scope, runs
    this ONCE, and authorizes the fire when asked" -- and main()'s no-
    subcommand branch is exactly that "runs this once." Not
    tropo-release.py:275's rehearsal path (cmd_rehearse constructs
    SYNTHETIC principal_inputs; Argus already ruled that one out).

    Never dedup'd: cardinality is "every registered-principal input
    retained," unlike fire_authorized's "once per active package" -- each
    invocation is its own fact, retried or not.

    Written straight to run_dir/run.jsonl (this file's own convention, see
    _identity/_rows above) rather than through the pipeline runtime's
    vault-resolved run_folder -- tropo-release.py already has run_dir in
    hand and never goes through 9e7003b1.py for anything. Confirmed safe
    against the bootstrap-adoption gate (9e7003b1.py's
    _pending_lock_run_created, hard len(events)!=1 on the FRESH lock seed):
    this file never calls action_bootstrap at all, and by the time an
    operator runs the bare orchestrator the run has already progressed well
    past that one-time seed state.
    """
    if not _run_is_bootstrapped(run_dir):
        # refusal: the stamp is evidence the orchestrator ran A BOOTSTRAPPED
        # RUN; stamping an unbootstrapped one fabricates that evidence (the
        # d9025a97 class). Never an exception — a one-line refusal the caller
        # surfaces; the lineage of the run is untouched.
        print("[REFUSED] orchestrator stamp: this run has no activation in "
              "run.state.json — it never bootstrapped, so there is nothing "
              "to stamp. Lock + bootstrap first.", file=sys.stderr)
        return False

    import hashlib
    import secrets
    import uuid as _uuid
    from datetime import datetime, timezone

    span_id = hashlib.sha256(
        f"{identity['pipeline_run_uid']}:orchestrator_invoked:"
        f"{_uuid.uuid4().hex}".encode("utf-8")
    ).hexdigest()[:16]
    event = {
        "event": "tropo.release.orchestrator_invoked",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # 3d8d4351 §2/§4: MACHINE-AUTHORED. The actor is this tool's own
        # uid (the engine), the label names it for humans, and invoked_via
        # marks the path — so the v2 tally can never count this row as a
        # principal gesture, and no journal again carries a forged human
        # name on a machine row (the authorization layer refuses names too).
        "actor": "4e8d1c60",
        "actor_label_resolved": "tropo-release engine stamp",
        "step": None,
        "stage": None,
        "data": {
            "saga_id": identity["saga_id"],
            "pipeline_run_uid": identity["pipeline_run_uid"],
            "invocation_uid": _chokepoint_mint_uid(),
            "invoked_via": invoked_via,
        },
        "schema_version": 2,
        "trace_id": identity["pipeline_run_uid"],
        "span_id": span_id,
        "parent_span_id": None,
    }
    with (run_dir / "run.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return True


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
    # THE BUS COMES FROM THE VERIFIER'S OWN LOADER, never a path typed here.
    # This read `run_dir / "bus-events.jsonl"` until 2026-09-01 -- a literal that
    # occurred exactly ONCE in the entire tree, at this line, written by nothing.
    # So every release observed an empty bus, bus_published_event is a REQUIRED
    # bound fact, and `status` could return only REFUSED, for every release,
    # with no flag to override it. The verifier cured this same conflation in
    # its own main() on 2026-08-25; the facade never routed through main().
    studio_root = TOOLS.parent.parent
    bus = module.load_bus_rows(studio_root)
    # AND THE VERSION, WHICH SCOPES THE BUS CHECK. Curing the phantom path alone
    # turned "found 0" into "found 7" -- the observer expects exactly ONE
    # tropo.release.published and, unscoped, it counts every release ever
    # published. Two defects stacked: an invisible bus, and an unscoped reader of
    # it. Fixing only the first still refuses, for a different reason, and would
    # have read as a working fix. The verifier already derives this the one true
    # way; the facade calls the same function rather than a second derivation.
    version = module._release_version_for(run_dir, studio_root)
    return module.build_observers(run_dir, bus, version, studio_root)


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


#: The surfaces that actually emit refusal telemetry. Five tools do; the
#: validator, the lock and the freeze refuse WITHOUT recording. Named on every
#: scorecard so a partial count can never be read as a total.
REFUSAL_TELEMETRY_COVERAGE = (
    "tropo-release.py",
    "tropo-build-release.py",
    "tropo-publish-release.py",
    "tropo-emit-event.py",
    "tropo-check-events.py",
)


def _journal_timestamps(run_dir: Path, identity: Optional[Dict[str, str]] = None,
                        vault: Optional[Path] = None) -> Dict[str, Any]:
    """The four moments, read from the run rather than supplied by the caller.

    Absent is None, never a substitute value. The rehearsal path sets
    primary_live_at and all_targets_live_at to the SAME argument, against a
    schema that says explicitly those two differ — a real fire must not inherit
    that shortcut, so anything this cannot observe stays None and the derived
    verdict fails on the hole rather than hiding it.

    THE FOUR MOMENTS LIVE IN TWO STORES, AND THIS USED TO READ ONE. Measured
    across all ten release runs in this studio, counting TYPED events (a plain
    grep also matches crew broadcasts discussing an event in prose, which is how
    this nearly got diagnosed backwards):

        scope_locked          bus 3   run-journal 0
        orchestrator_invoked  bus 0   run-journal 1
        completion_verified   bus 0   run-journal 1
        published             bus 5   run-journal 4

    `scope_locked` has NEVER appeared in a release run journal — not once, not
    even in the fully-published runs. It is emitted to the canonical event bus by
    the lock tool. So `scope_locked_at` was structurally always None, and the
    schema types it as a non-nullable string: every real-fire scorecard was
    therefore invalid before it was ever written, for a reason that had nothing
    to do with the release being measured.

    This is the sixteenth instance of this lineage's signature defect — one fact,
    two readers, disagreeing where nobody looks. The cure is the same each time:
    read where the writer actually writes. Bus events are correlated by
    `data.pipeline_run_uid` (scope_locked carries release_plan_uid,
    pipeline_run_uid, activation_uid AND saga_id, so this is a real join, not a
    time-window guess), and the run journal still wins when both carry a moment.
    (argus-a158, 2026-08-25, Mike-directed root-cause pass.)
    """
    stamps: Dict[str, Any] = {
        "scope_locked_at": None,
        "orchestrator_started_at": None,
        "primary_live_at": None,
        "all_targets_live_at": None,
    }
    by_event = {
        "tropo.release.scope_locked": "scope_locked_at",
        "tropo.release.orchestrator_invoked": "orchestrator_started_at",
        "tropo.release.published": "primary_live_at",
        # all_targets_live_at had NO source event: three of the four moments were
        # mapped and the fourth was left to be None forever, which made
        # lock_to_all_targets_live_seconds permanently None and the verdict
        # permanently "fail" — the scorecard could not pass for a reason that had
        # nothing to do with the release it was measuring.
        #
        # completion_verified is the right source and the only one: it is written
        # by tropo-verify-release-live's composite verifier "from the one place the
        # fact becomes true", after every target has been independently proved
        # live. `published` means the PRIMARY target is live; this means all of
        # them are, which is exactly the distinction the schema draws between
        # primary_live_at and all_targets_live_at. It lands before cmd_fire reads
        # the scorecard, so it is available when the card is built.
        # (argus-a158, 2026-08-25.)
        "tropo.release.completion_verified": "all_targets_live_at",
    }
    def _absorb(row: Dict[str, Any]) -> None:
        name = str(row.get("event") or row.get("type") or "")
        key = by_event.get(name)
        if key and stamps[key] is None:
            stamps[key] = (
                row.get("ts")
                or row.get("time")
                or (row.get("data") or {}).get("published_at")
            )

    path = run_dir / "run.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                _absorb(json.loads(line))
            except ValueError:
                continue

    # Second store: the canonical event bus, joined on pipeline_run_uid. Only
    # consulted for moments the run journal did not carry, and only for THIS
    # run — a bus scan without the join would happily stamp another release's
    # lock onto this card.
    run_uid = str((identity or {}).get("pipeline_run_uid") or "")
    if run_uid and any(stamps[k] is None for k in stamps) and vault is not None:
        streams = Path(vault) / "vault" / "events" / "streams"
        if streams.is_dir():
            for stream in sorted(streams.glob("*.jsonl")):
                try:
                    text = stream.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    data = row.get("data") or {}
                    if str(data.get("pipeline_run_uid") or "") != run_uid:
                        continue
                    _absorb(row)
    return stamps


TELEMETRY_LANE = Path(".tropo-studio") / "telemetry"


def _observed_refusals(identity: Dict[str, str], vault: Path,
                       window_start: Optional[str] = None,
                       window_end: Optional[str] = None):
    """Refusal ids observed during this release's window, or None if unreadable.

    None is the honest answer when the telemetry store cannot be read. It is
    not the same as [], which asserts that no refusal happened — and asserting
    that without measuring is the defect this whole criterion exists to remove.

    WHAT THIS USED TO DO, AND WHY IT COULD NEVER WORK. It imported
    `lib/tool_telemetry.py` fresh and looked for `read_refusals_for(run_uid)`.
    Two independent reasons that returns nothing, forever:

      1. `read_refusals_for` IS NOT DEFINED ANYWHERE IN THE CORPUS. The lookup
         is a getattr with a None fallback, so the miss was silent and the
         function returned None — "not recorded" — on every release ever run.
      2. Even written, it could not have worked. tool_telemetry is by its own
         docstring an "enqueue-only" producer holding a "bounded IN-MEMORY
         priority queue — no disk, no SQLite". Importing it in the orchestrator
         creates an EMPTY queue in a different process from the build that did
         the refusing. Persistence "belongs to the drainer, never to the
         observed thread."

    So the data was never where the reader looked. It is on the durability lane
    the drainer writes: `.tropo-studio/telemetry/{shards,active}/*.jsonl`
    (117 sealed shards on this studio at the time of writing).

    CORRELATION IS TEMPORAL, AND THAT IS A DELIBERATE, STATED LIMITATION.
    Telemetry records carry `tool_uid`, `invocation_uid`, `operation_uid` and
    `outcome` — and NO `pipeline_run_uid`. The field the old signature keyed on
    does not exist in the data, so no amount of implementing that function would
    have joined these two subsystems. Rather than widen the strict, self-certifying
    telemetry registry mid-release to add a key, this bounds by the release's own
    window: refusals recorded between the first stamped moment of this run and
    the fire. Concurrent unrelated tool refusals inside that window would be
    counted; on this studio a release IS the activity, and over-counting refusals
    is the safe direction for an instrument whose purpose is to show what shipping
    costs. If that stops being true, add `pipeline_run_uid` to the registry and
    key on it — the honest fix, at a cost this release should not pay.
    (argus-a158, 2026-08-25, Mike-directed root-cause pass.)
    """
    lane = Path(vault) / TELEMETRY_LANE
    if not lane.is_dir():
        return None
    files = sorted(lane.glob("shards/*.jsonl")) + sorted(lane.glob("active/*.jsonl"))
    if not files:
        return None
    lo = _parse_ts(window_start)
    hi = _parse_ts(window_end)
    found: list[str] = []
    seen: set[str] = set()
    for path in files:
        if path.name.endswith(".manifest.json"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            data = row.get("data") or {}
            if str(data.get("outcome") or "") != "refused":
                continue
            at = _parse_ts(data.get("event_time_utc") or row.get("time"))
            if lo is not None and (at is None or at < lo):
                continue
            if hi is not None and at is not None and at > hi:
                continue
            ident = str(row.get("id") or data.get("invocation_uid") or "")
            if ident and ident not in seen:
                seen.add(ident)
                found.append(ident)
    return sorted(found)


def _parse_ts(value: Optional[str]):
    """ISO-8601 to datetime, or None. A stamp we cannot read is not a boundary."""
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = _dt.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_dt.timezone.utc)
        return parsed
    except ValueError:
        return None


#: The timestamps a scorecard is MALFORMED without — i.e. the ones the schema
#: declares non-nullable. `primary_live_at` and `all_targets_live_at` are
#: declared ["string", "null"] and are legitimately absent on a card written
#: before the outward act completes.
_REQUIRED_CARD_STAMPS = ("scope_locked_at", "orchestrator_started_at")


def _human_gesture_moments(run_dir: Path, identity: Dict[str, str]) -> Dict[str, Optional[str]]:
    """When each PRINCIPAL input actually happened, per the declared mapping.

    Reads lib/release_events.HUMAN_INPUT_EVENTS — the one place this Studio
    declares which event records which human gesture — and finds each of those
    events in this run's journal. Never infers a human moment from a machine
    one: an absent gesture stays absent rather than borrowing a nearby
    timestamp, because a scorecard that invents a gesture is worse than one
    that reports none.
    """
    try:
        from lib.release_events import HUMAN_INPUT_EVENTS  # noqa: WPS433
    except Exception:  # noqa: BLE001 — a missing lib must not take the release
        HUMAN_INPUT_EVENTS = {
            "release_scope_locked": "tropo.release.scope_locked",
            "release_orchestrator_invoked": "tropo.release.orchestrator_invoked",
            "release_fire_authorized": "tropo.release.fire_authorized",
        }
    wanted = {event: name for name, event in HUMAN_INPUT_EVENTS.items()}
    found: Dict[str, Optional[str]] = {name: None for name in HUMAN_INPUT_EVENTS}
    path = run_dir / "run.jsonl"
    if not path.is_file():
        return found
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        name = wanted.get(str(row.get("event") or row.get("type") or ""))
        if name and not found[name]:
            found[name] = row.get("ts") or row.get("time")
    return found


def _write_real_fire_scorecard(
    identity: Dict[str, str], run_dir: Path, vault: Path, version: str
) -> None:
    """Score the REAL fire. Never raises: the release already happened.

    Until this landed, REAL_FIRE existed as a constant, a filename and an
    __all__ entry with NO CALLER ANYWHERE, so no release in this Studio's
    history was ever scored. The instrument that measures what a release costs
    the principal — gestures he made, refusals by class, wall-clock from lock to
    all targets live — was wired only to the rehearsal path.
    """
    try:
        stamps = _journal_timestamps(run_dir, identity, vault)
        # D-10 (adversarial review, 2026-08-26): the third pairing used to read
        # `primary_live_at`, which is fed by tropo.release.published — a moment
        # the MACHINE produces. On the real v1.92 run the principal's
        # authorization is at 20:12:36Z and `published` is at 20:13:51Z, so the
        # instrument built to keep this Studio honest about human gestures would
        # have timestamped the human's gesture 75 seconds late, at a machine
        # moment. Worse: in any run where fire_authorized is absent but
        # published is present, it would report a gesture the principal never
        # made — the exact forgery the runner's orchestrator gate refuses to
        # commit, committed one file away.
        #
        # The mapping from human input to event is DECLARED, once, in
        # lib/release_events.HUMAN_INPUT_EVENTS. This hand-rolled its own third
        # pairing instead of reading it. Read the declaration.
        gestures = [
            {"input": name, "at": at}
            for name, at in _human_gesture_moments(run_dir, identity).items()
            if at
        ]
        scorecard = metrics.build_scorecard(
            mode=metrics.REAL_FIRE,
            saga_id=identity.get("saga_id", ""),
            pipeline_run_uid=identity.get("pipeline_run_uid", ""),
            release_version=version,
            principal_inputs=gestures,
            timestamps=stamps,
            active_machine_seconds=None,
            # The window is this run's own first stamped moment through the fire.
            # Passing it is what makes the refusal count belong to THIS release
            # rather than to all telemetry ever recorded on the studio.
            observed_refusals=_observed_refusals(
                identity, vault,
                window_start=(stamps.get("scope_locked_at")
                              or stamps.get("orchestrator_started_at")),
                window_end=(stamps.get("all_targets_live_at")
                            or stamps.get("primary_live_at")),
            ),
            baseline=metrics.load_refusal_baseline(vault),
            refusal_coverage=REFUSAL_TELEMETRY_COVERAGE,
        )
        # AC5 (05de711d): a card missing a REQUIRED stamp is not a measurement,
        # it is a malformed file at the path a reader checks. Writing it anyway
        # is how v1.92 got a scorecard that failed its own schema on
        # orchestrator_started_at and was then correctly recorded ABSENT by the
        # publisher's validity gate — two steps to reach "nothing", with a
        # misleading file on disk in between. Refuse, and name the stamp.
        #
        # NOT gated on `verdict`. A card reading verdict "fail" is a SUCCESSFUL
        # measurement of an expensive release; gating on it would conflate "did
        # we measure" with "did we like the answer".
        # D-11: the required set is READ FROM THE SCHEMA'S OWN NULLABILITY, not
        # chosen here. My first version also required `primary_live_at`, which
        # the schema explicitly permits to be null — so the guard refused to
        # write cards the schema would have accepted. Only the two non-nullable
        # stamps make a card malformed by their absence.
        missing_stamps = [k for k in _REQUIRED_CARD_STAMPS if not stamps.get(k)]
        if missing_stamps:
            print("  ! real-fire scorecard NOT written — no %s in this run's "
                  "journal. The measurement would be malformed, and an absent "
                  "card is honest where a malformed one is not."
                  % ", ".join(missing_stamps), file=sys.stderr)
            return
        target = metrics.scorecard_path(run_dir, metrics.REAL_FIRE)
        target.write_text(
            json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("real-fire scorecard: %s (verdict %s)" % (target, scorecard["verdict"]))
    except Exception as exc:  # noqa: BLE001 — measurement never breaks the release
        print("  ! real-fire scorecard not written (%s) — the fire is unaffected"
              % exc, file=sys.stderr)


def _fire_sequence_gate(run_dir: Path, vault: Path,
                        identity: Dict[str, str]) -> Optional[Tuple[int, str]]:
    """3d8d4351 §3: the macro-sequence walked as machine-checked preconditions.

    Each stage's evidence is answered by the DECLARED READER named in
    release_bindings.MACRO_SEQUENCE — never a re-parse of another subsystem's
    file. One sentence per refusal, naming the stage and the command that
    produces the evidence; no refusal ever instructs re-running an outward
    act. Exactly one production consumer: this fire path.
    """
    from lib import release_bindings

    def _stage_commands(stage: str) -> str:
        return {
            "LOCK": "tropo-lock-dev-spec.py / tropo-lock-release-plan.py — the lock IS gesture one",
            "BOOTSTRAP": "the pipeline activation (tropo-release-run.py bootstrap)",
            "STEPS": "tropo-release-run.py — walk the declared steps",
            "BUILD": "tropo-build-release.py — produce and freeze the package",
            "STAGE": "tropo-publish-release.py stage",
            "PREFLIGHT": "tropo-release-preflight.py — run every fire precondition",
            "ORCHESTRATOR": "tropo-release.py --release-plan-uid <uid> (the bare orchestrator)",
        }.get(stage, "see the release engine docs")

    for stage_spec in release_bindings.MACRO_SEQUENCE:
        stage = stage_spec["stage"]
        if stage == "LOCK":
            stamps = _journal_timestamps(run_dir, identity, vault)
            if not stamps.get("scope_locked_at"):
                return (EXIT_REFUSED,
                        "sequence gate: LOCK has no evidence (no scope_locked "
                        "timestamp in this run's journal+bus) — %s"
                        % _stage_commands("LOCK"))
        elif stage == "BOOTSTRAP":
            if not _run_is_bootstrapped(run_dir):
                return (EXIT_REFUSED,
                        "sequence gate: BOOTSTRAP has no evidence (no "
                        "activation in run.state.json) — %s"
                        % _stage_commands("BOOTSTRAP"))
        elif stage == "STEPS":
            state = json.loads(
                (run_dir / "run.state.json").read_text(encoding="utf-8") or "{}"
            ) if (run_dir / "run.state.json").is_file() else {}
            statuses = state.get("step_status") or {}
            if not statuses:
                return (EXIT_REFUSED,
                        "sequence gate: STEPS has no evidence (run.state.json "
                        "records no step statuses) — %s" % _stage_commands("STEPS"))
            failed = [k for k, v in statuses.items() if str(v) == "failed"]
            if failed:
                return (EXIT_REFUSED,
                        "sequence gate: STEPS carry failures (%s) — resolve "
                        "them before the fire; %s"
                        % (", ".join(sorted(failed)[:4]), _stage_commands("STEPS")))
        elif stage == "BUILD":
            from lib import release_package
            try:
                # _rows is THIS module's raw-journal reader (the one the
                # stamp documents); _journal returns a SagaJournal object,
                # which the reader would iterate as empty — the silent-empty
                # failure shape release_package.event_type's own docstring
                # warns about.
                rows = _rows(run_dir / "run.jsonl")
            except (Exception, SystemExit):
                rows = []
            payload = None
            try:
                payload = release_package.active_frozen_payload(
                    rows, identity.get("pipeline_run_uid", ""))
            except Exception:
                payload = None
            if not payload:
                return (EXIT_REFUSED,
                        "sequence gate: BUILD has no evidence (no active "
                        "frozen package for this run) — %s"
                        % _stage_commands("BUILD"))
        elif stage == "STAGE":
            wired = _load_wired_publisher()
            state = wired._run_publish_state("--expect", identity.get(
                "pipeline_run_uid", "")) if wired else {}
            if not state or state.get("status") not in ("staged", "verified", "live"):
                return (EXIT_REFUSED,
                        "sequence gate: STAGE has no evidence (publish state "
                        "is %r) — %s"
                        % (state.get("status") if state else None,
                           _stage_commands("STAGE")))
        elif stage == "PREFLIGHT":
            # The roster's own runner is the declared reader; its absence or a
            # missing preflight journal is the refusal.
            # The filename is IMPORTED from the writer's own module, never
            # re-typed here. This line read "preflight-journal.jsonl" until
            # 2026-08-31 — a name nothing ever wrote — so the gate refused
            # every run that had actually passed preflight.
            pf_path = run_dir / PREFLIGHT_EVIDENCE_FILENAME
            if not pf_path.is_file():
                return (EXIT_REFUSED,
                        "sequence gate: PREFLIGHT has no evidence (no "
                        "preflight journal in the run folder) — %s"
                        % _stage_commands("PREFLIGHT"))
        elif stage == "ORCHESTRATOR":
            stamps = _journal_timestamps(run_dir, identity, vault)
            if not stamps.get("orchestrator_started_at"):
                return (EXIT_REFUSED,
                        "sequence gate: ORCHESTRATOR has no evidence (no "
                        "orchestrator_invoked timestamp) — %s"
                        % _stage_commands("ORCHESTRATOR"))
        # FIRE itself is authorized here + completed by the publisher; it has
        # no occurrence-evidence precondition of its own in this walk.
    return None


def _load_wired_publisher():
    """Best-effort load of the publisher module (the STAGE reader's home)."""
    import importlib.util as _ilu
    path = Path(__file__).resolve().parent / "tropo-publish-release.py"
    spec = _ilu.spec_from_file_location("tropo_publish_release_walk", path)
    if spec is None or spec.loader is None:
        return None
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pointer_row_for_owner(identity: Dict[str, str], message: str) -> None:
    """§1: ONE pointer row on the bus for the release owner (7c017d1f).

    A notification, never a counted ledger store. Swallowed whole: a bus the
    engine cannot reach must not turn a refusal into a crash.
    """
    import subprocess as _sp
    tool = Path(__file__).resolve().parent / "tropo-emit-event.py"
    if not tool.is_file():
        return
    try:
        _sp.run(
            [sys.executable, str(tool), "--type", "tropo.message.sent",
             "--as", "talos", "--source", "/tools/tropo-release",
             "--source-uid", "4e8d1c60", "--lifecycle", "ephemeral",
             "--subject", "7c017d1f",
             "--data", json.dumps({"body": "[fire gate] %s" % message})],
            capture_output=True, timeout=15)
    except Exception:
        return


def _rehearsal_gate(run_dir: Path, fired_version: str) -> Optional[Tuple[int, str]]:
    """3d8d4351 §7: a real fire requires a PASSING rehearsal of THIS candidate.

    The gate READS the card; it never re-runs the rehearsal. The engine
    invokes rehearse with the real candidate version elsewhere (never
    rehearse's --version default): this function only refuses, naming the
    command that produces what is missing.
    """
    card_path = metrics.scorecard_path(run_dir, metrics.REHEARSAL)
    if not card_path.is_file():
        return (EXIT_REFUSED,
                "no rehearsal card at %s — run `tropo-release.py rehearse "
                "--run-dir %s --version %s` first; the fire gate reads the "
                "card, it never runs the rehearsal for you"
                % (card_path, run_dir, fired_version or "<candidate>"))
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return (EXIT_REFUSED,
                "rehearsal card unreadable (%s) — re-run the rehearsal: "
                "tropo-release.py rehearse --run-dir %s"
                % (exc, run_dir))
    if card.get("mode") != metrics.REHEARSAL or card.get("verdict") != "pass":
        return (EXIT_REFUSED,
                "rehearsal verdict is %r, not pass — a failing rehearsal "
                "gates the fire by design; fix what it found, then re-run it"
                % (card.get("verdict"),))
    if fired_version and str(card.get("release_version") or "") != fired_version:
        return (EXIT_REFUSED,
                "rehearsal card names version %r; this candidate is %r — the "
                "rehearsal must be OF this release. Re-run: tropo-release.py "
                "rehearse --run-dir %s --version %s"
                % (card.get("release_version"), fired_version, run_dir, fired_version))
    performed = card.get("checkpoints_performed")
    declared = len(saga.CHECKPOINTS)
    if performed is None or int(performed) != declared:
        return (EXIT_REFUSED,
                "rehearsal performed %r of %d declared checkpoints — the "
                "rehearsal must exercise the full checkpoint set before the "
                "fire walks it for real" % (performed, declared))
    return None


def _write_scorecard_so_far(run_dir: Path, identity: Dict[str, str],
                            vault: Path) -> Optional[Path]:
    """3d8d4351 §1: the scorecard-so-far artifact, in the run folder, BEFORE
    the handoff — so the publisher's one go/no-go renders a MEASURED state
    and never a blank ask. Honest about absences: what the journal cannot
    yet know is recorded as absent, not guessed. Returns the artifact path
    (or None when even the identity is unreadable — the caller proceeds;
    the publisher renders its honest absent-line).
    """
    try:
        rows = _journal(run_dir)
    except (Exception, SystemExit):
        # SystemExit included deliberately: _journal's MISUSE refusal for an
        # identity-less journal is an ABSENCE here, not an error to propagate —
        # the artifact records what is knowable and the publisher renders its
        # honest absent-line either way.
        rows = []
    card = {
        "schema_version": 2,
        "kind": "scorecard-so-far",
        "saga_id": identity.get("saga_id"),
        "pipeline_run_uid": identity.get("pipeline_run_uid"),
        "journal_rows_seen": len(rows),
        "written_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "pre-handoff state; the REAL_FIRE card is produced at the "
                "moment its inputs become true (the injected producer)",
    }
    path = run_dir / "scorecard-so-far.json"
    try:
        path.write_text(json.dumps(card, indent=1) + "\n", encoding="utf-8")
        return path
    except OSError:
        return None


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

    # 3d8d4351 §3 — the macro-sequence walked as machine-checked preconditions.
    sequence_refusal = _fire_sequence_gate(run_dir, Path(args.vault), identity)
    if sequence_refusal is not None:
        code, message = sequence_refusal
        print("[REFUSED:%s] %s" % (code, message), file=sys.stderr)
        _record_fire_refusal(identity, code, Path(args.vault))
        _pointer_row_for_owner(identity, message)
        return EXIT_REFUSED

    # 3d8d4351 §7 — the rehearsal gate reads the card and never re-runs it.
    _candidate_version = getattr(args, "version", None)
    rehearsal_refusal = _rehearsal_gate(run_dir, _candidate_version or "")
    if rehearsal_refusal is not None:
        code, message = rehearsal_refusal
        print("[REFUSED:%s] %s" % (code, message), file=sys.stderr)
        _record_fire_refusal(identity, code, Path(args.vault))
        return EXIT_REFUSED

    # 3d8d4351 §1 — the scorecard-so-far lands in the run folder BEFORE the
    # handoff; the publisher's go/no-go renders it (absent-line if missing).
    _write_scorecard_so_far(run_dir, identity, Path(args.vault))

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

    def _produce_scorecard(fired_version: str) -> None:
        """Score the REAL fire, at the moment the measurement becomes true.

        Stream 1 AC4: REAL_FIRE had no caller in the entire tool corpus until
        this line existed, so no release was ever measured.

        THIS IS AN INJECTED PRODUCER, NOT A POST-RETURN CALL, and the difference
        is the whole defect. This function used to run AFTER wired.cmd_fire()
        returned and only `if code == 0`. But cmd_fire returns 15 when its
        journal has no observation for completion_verification, and that
        observation is made only when the scorecard already exists — of which
        this is the sole producer. First fire: no card, unobserved, exit 15,
        producer never runs, re-fire identical, forever.

        The layering was never the problem and is unchanged: the publisher still
        does not have the measurement inputs (orchestrator start stamp, observed
        refusals, baseline) and still does not build the card. It just calls the
        producer the orchestrator handed it, at the point in its own sequence
        where every input has become true. The ORDER was the defect.

        The fired version is a PARAMETER rather than read from args: the
        publisher resolves it (`args.version or _latest_staged_version()`) and
        passes what it actually fired. Reading it here instead produced `""` on
        every real run, because the `fire` subparser never declared --version —
        a card that named no release, failing schema minLength, in a world where
        nothing validated strictly enough to say so.
        (argus-a158, 2026-08-25, Mike-directed root-cause pass.)
        """
        _write_real_fire_scorecard(
            identity, run_dir, Path(args.vault), fired_version or "",
        )

    class _FireArgs:
        version = getattr(args, "version", None)
        scorecard_producer = staticmethod(_produce_scorecard)

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
    # Declared so an operator CAN pin the version; omitted is the normal case and
    # the publisher resolves it from staged state, then hands the resolved value
    # to the scorecard producer. Before this existed, `getattr(args, "version")`
    # in cmd_fire could only ever be None on a real run.
    fire.add_argument("--version", default=None,
                      help="version to fire; default: the most recently staged")
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
        _record_orchestrator_invoked(Path(args.run_dir), _identity(Path(args.run_dir)))
        code = cmd_status(args)
        args.authorize = False
        fire = cmd_fire(args)
        return code if fire == EXIT_OK else fire
    return args.func(args)


if __name__ == "__main__":
    # refusal: misuse — not a refusal; the entrypoint propagates main's exit code
    sys.exit(main())
