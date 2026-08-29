#!/usr/bin/env python3
"""The minimal cold runner.

Stream 1 of v1.92 (dev-spec 5b608d28), AC6. The order is a mechanism, not a
label: this walks a release profile's declared slots in order, one step at
a time, reads the AC5 profile's own executor bindings to know what comes
next, executes deterministic steps, and halts at the first judgment step
naming its executor class and a runnable command — the profile's consumer,
so the seam does not ship with zero of them.

SAFETY BOUNDARY, BY CONSTRUCTION, NOT BY A GUARD. A walk halts permanently
at the FIRST judgment step it reaches and never resumes past it within one
call. The only step in the publish-the-artifact slot of the shipped v1.92
profile — the one irreversible outward act — has an `entry` shaped to be
dynamically invoked, but it sits behind two judgment steps earlier in the
walk order and is therefore unreachable from a cold walk today. Execution
is additionally opt-in (`execute=False` by default; the CLI requires
`--execute`), so the default invocation of this tool, on any profile,
performs no side effect at all. If a future profile ever placed a
dynamically-invocable entry before the first judgment step, this boundary
would need re-examining explicitly — noting it here so it is a decision,
not a surprise.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib.release_profile import (  # noqa: E402
    ReleaseProfile,
    iter_release_profile_uids,
    load_profile,
)
from lib import release_bindings  # noqa: E402

__all__ = [
    "RunAction", "RunOutcome", "RunContext", "walk", "first_action",
    "resolve_context", "step_status", "TERMINAL_STEP_STATES",
]

#: A step in one of these states has already happened. Read from the run's own
#: `run.state.json`, which the pipeline runtime maintains — NOT re-derived from
#: the journal here. This runner having its own opinion of what is done would be
#: a second source for one fact, which is the defect class that cost this Studio
#: v1.92's whole release week.
TERMINAL_STEP_STATES = frozenset({"verified", "completed", "skipped"})


@dataclass(frozen=True)
class RunAction:
    """One step the runner reports, in the order it walked.

    `command` is the runnable thing a human or agent must do: the
    binding's own `entry` for a deterministic step, or a constructed
    instruction naming the executor class for a judgment step. `invoked`
    is True only when this step was a deterministic step that the runner
    ACTUALLY called (requires `execute=True` and an `entry` shaped as
    `<path>:<callable>`) — a report of intent is never conflated with a
    report of action.
    """

    step_uid: str
    slot: str
    deterministic: bool
    executor: Optional[str]
    description: str
    command: str
    invoked: bool = False
    #: True when the run's own state already recorded this step terminal, so
    #: the runner skipped it. This is what makes a re-run resumable instead of
    #: destructive.
    already_done: bool = False
    #: Set when an executed step raised. A step that failed is never reported
    #: as invoked-and-fine; the walk stops here.
    error: Optional[str] = None


@dataclass(frozen=True)
class RunOutcome:
    """The result of one cold walk.

    `status` is "complete" when every step in the profile was deterministic
    and the walk finished without stopping, or "halted" when a judgment
    step was reached. A halt is a terminal verdict, not a failure: the
    runner is not authorized to act past a decision only a named executor
    may make.
    """

    status: str
    actions: List[RunAction]
    halted_at: Optional[RunAction] = None
    #: Set when status == "failed": the step whose execution raised.
    failed_at: Optional[RunAction] = None


class RunStateUnreadable(RuntimeError):
    """The run's own record of what is done could not be read. Never downgraded
    to "nothing is done" — that inverts resume into re-run at the exact moment
    the file is damaged."""


@dataclass(frozen=True)
class RunContext:
    """What a real release step needs to be CALLED, not merely named.

    Every entry in the shipped profile takes arguments — an activation uid, a
    run folder, a candidate path — and the runner used to invoke each one as a
    bare `fn()`. That is why `--execute` had never executed a single step since
    it was declared in v1.92 Stream 1: the first call raised TypeError before
    anything could happen. One context, resolved once from the run's own files,
    adapted per step below.
    """

    vault_root: Path
    release_plan_uid: str
    run_dir: Path
    activation_uid: str
    version: Optional[str] = None
    candidate: Optional[Path] = None
    release_entry_uid: Optional[str] = None
    #: who is performing this walk, stamped onto records the steps write.
    #: NOT defaulted to this tool's own filename: that is a product
    #: literal, and test_release_profile_seam_v192 refuses one here —
    #: "the machine does not know what it is shipping". It caught this
    #: exact line. Supplied by --actor; the neutral default is honest
    #: about being unattributed rather than guessing an agent.
    actor: str = "unattributed-runner"


def _load_tool(name: str, base_dir: Path):
    """Import a hyphenated sibling tool by filename. They are scripts, not
    modules, so a plain import cannot reach them."""
    path = base_dir / name
    if not path.is_file():
        return None
    module_name = "release_run_tool_%s" % name.replace("-", "_").replace(".", "_")
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def step_status(run_dir: Path) -> Dict[str, str]:
    """Per-step state as the pipeline runtime recorded it.

    `run.state.json` is the declared home of this fact. Reading it is what makes
    a re-run resumable rather than destructive: a step already `verified` is not
    run again, and the runner never forms its own view of what is done.
    """
    state_path = run_dir / "run.state.json"
    if not state_path.is_file():
        return {}
    try:
        body = json.loads(state_path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        # D-7: `{}` meant two irreconcilable things — "this run has done
        # nothing" and "I could not read what this run has done". Under
        # --execute the second silently became the first and the runner re-ran
        # the release from the fan-in validator through the build. A
        # half-written state file is what an interrupted pipeline run leaves
        # behind, so this is the one moment the promise mattered and the one
        # moment it inverted.
        raise RunStateUnreadable(
            "%s could not be read (%s). Refusing to walk: an unreadable state "
            "file is not an empty one, and treating it as empty re-runs steps "
            "that may already have happened." % (state_path, exc))
    raw = body.get("step_status") or {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def run_is_walkable(run_dir: Path, runs_root: Optional[Path] = None) -> Optional[str]:
    """Why this run must not be walked, or None.

    D-9 (adversarial review): on the abandoned run the fire precondition was
    ALREADY SATISFIED — its journal carries an orchestrator_invoked row from
    before it was abandoned — while every step read as never done. So an
    abandoned run walked as a live one with the gate on the outward act
    pre-satisfied.

    READ THE FIELD IN THE RIGHT DIRECTION. My first version refused any run
    carrying `supersedes_activation`, and that field means this run supersedes
    ANOTHER — it marks the SURVIVOR. It refused `cd68bea8`, the run that
    actually shipped, and let the abandoned `42261546` walk. The
    abandoned run carries no marker of its own at all: it is identified only by
    a later run naming ITS activation. Caught by running it against both real
    runs instead of trusting a field name.
    """
    state_path = run_dir / "run.state.json"
    if not state_path.is_file():
        return None
    try:
        body = json.loads(state_path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return None  # D-7 handles unreadable state; not this check's job
    status = str(body.get("run_status") or "").lower()
    if status and status not in ("active", "running", "open"):
        return "this run is %r, not active" % status

    activation = str(body.get("activation_uid") or "")
    if not activation:
        # 4.2 (closing review): the ONE real abandoned run on disk carries
        # `{"run_nonce": "..."}` and nothing else — no run_status, no
        # activation. It was abandoned precisely BECAUSE it could never
        # bootstrap, so it never acquired the fields either detection path
        # looked for, while its journal still carries an orchestrator_invoked
        # row that leaves the fire gate open. Both paths missed the only run
        # that exhibits the problem.
        #
        # A run that never bootstrapped has no steps, no authorization key and
        # no release folder. There is nothing to walk.
        return ("this run has no activation in its state — it never "
                "bootstrapped, so it has no steps to walk")
    root = runs_root if runs_root is not None else run_dir.parent
    if not root.is_dir():
        return None
    for other in sorted(root.glob("release-pipeline-*")):
        if other.resolve() == run_dir.resolve():
            continue
        other_state = other / "run.state.json"
        if not other_state.is_file():
            continue
        try:
            other_body = json.loads(other_state.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            continue
        if str(other_body.get("supersedes_activation") or "") == activation:
            return ("this run's activation %s was superseded by %s (%s)"
                    % (activation, other.name,
                       str(other_body.get("supersession_reason") or "superseded")[:80]))
    return None


def plan_is_walkable(vault_root: Path, release_plan_uid: str) -> Optional[str]:
    """Why this release PLAN must not be driven, or None.

    The plan owns its own lifecycle and says so in its frontmatter: the
    abandoned v1.92 plan carries `status: cancelled` with an `abandon_reason`
    naming Mike's authorization. The run it opened carries none of that — a run
    abandoned before bootstrap never acquires the fields a reader would check.
    So ask the plan, which is where the fact is declared.
    """
    path = Path(vault_root) / "vault" / "files" / ("%s.md" % release_plan_uid)
    if not path.is_file():
        return None
    # F1 (fourth verification): this read only the first 60 lines, an arbitrary
    # cap I chose without measuring real frontmatter. The cancelled plan this
    # function's own docstring names declares `status:` at line 64, and another
    # at line 127 — so the guard was DEAD on 2 of the 11 cancelled plans on
    # disk, including the one it was written for. Its test stayed green because
    # the fixture was a four-line file: structurally incapable of reaching the
    # boundary it was meant to prove.
    #
    # Parse the whole frontmatter block instead of guessing how long it is.
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    block = text[3:end] if end != -1 else text[3:]
    for line in block.splitlines():
        if line.startswith("status:"):
            status = line.split(":", 1)[1].strip().strip("'\"").lower()
            if status in ("cancelled", "canceled", "abandoned", "superseded"):
                return "release plan %s is %r" % (release_plan_uid, status)
            return None
    return None


def resolve_context(
    vault_root: Path, release_plan_uid: str, version: Optional[str] = None,
    candidate: Optional[Path] = None, base_dir: Optional[Path] = None,
    actor: Optional[str] = None,
) -> RunContext:
    """Resolve the run folder and identity from the plan uid alone.

    The operator has a release PLAN uid in hand; everything else is looked up
    from files inside the run, never from the index — the index is per-machine
    derived state and a release must not depend on whether a rebuild has run.
    """
    base_dir = base_dir if base_dir is not None else TOOLS_DIR
    orchestrator = _load_tool(
        release_bindings.OPERATOR_TOOLING["orchestrator_module"], base_dir)
    if orchestrator is None or not hasattr(orchestrator, "resolve_run_dir"):
        raise RuntimeError("cannot load the orchestrator module's resolve_run_dir")
    run_dir = Path(orchestrator.resolve_run_dir(Path(vault_root), release_plan_uid))
    activation_uid = ""
    auth = run_dir / "release-authorization.json"
    if auth.is_file():
        try:
            activation_uid = str(
                (json.loads(auth.read_text(encoding="utf-8")) or {}).get("activation_uid") or "")
        except (OSError, ValueError):
            activation_uid = ""
    if not activation_uid:
        state = run_dir / "run.state.json"
        if state.is_file():
            try:
                activation_uid = str(
                    (json.loads(state.read_text(encoding="utf-8")) or {}).get("activation_uid") or "")
            except (OSError, ValueError):
                activation_uid = ""
    # The plan DECLARES the version it is cutting. Making the operator retype it
    # is a mechanical command landing on their keyboard for a fact the substrate
    # already holds — and counting exactly those is this release's deliverable.
    # An explicit --version still wins; this only fills the blank.
    if not version:
        plan_path = Path(vault_root) / "vault" / "files" / ("%s.md" % release_plan_uid)
        if plan_path.is_file():
            text = plan_path.read_text(encoding="utf-8", errors="replace")
            end = text.find("\n---", 3) if text.startswith("---") else -1
            block = text[3:end] if end != -1 else ""
            for line in block.splitlines():
                if line.startswith("release_version:"):
                    version = line.split(":", 1)[1].strip().strip("'\"") or None
                    break
    # Same reasoning as release_version directly above: the plan DECLARES the
    # release entry this build writes its history onto. Reading it here is one
    # fewer fact the operator has to hold, and the release-history step cannot
    # run without it.
    release_entry_uid = _plan_field(vault_root, release_plan_uid, "release_entry_uid")
    return RunContext(
        vault_root=Path(vault_root), release_plan_uid=release_plan_uid,
        run_dir=run_dir, activation_uid=activation_uid,
        version=version, candidate=candidate,
        release_entry_uid=release_entry_uid,
        **({"actor": actor} if actor else {}),
    )


def _plan_field(vault_root: Path, release_plan_uid: str, field: str) -> Optional[str]:
    """Read one scalar from the release plan's frontmatter.

    From the PLAN FILE, never the index: a release must not depend on whether a
    rebuild has run on this machine (resolve_context's own rule, applied to one
    more field instead of open-coded a second time).
    """
    plan_path = Path(vault_root) / "vault" / "files" / ("%s.md" % release_plan_uid)
    if not plan_path.is_file():
        return None
    text = plan_path.read_text(encoding="utf-8", errors="replace")
    end = text.find("\n---", 3) if text.startswith("---") else -1
    block = text[3:end] if end != -1 else ""
    prefix = "%s:" % field
    for line in block.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip().strip("'\"") or None
    return None


# An adapter returns a FAILURE REASON, or None when the step genuinely passed.
#
# D-2 (independent adversarial review, 2026-08-26): the walk used to treat "the
# callable returned" as "the step succeeded". Only a raised exception could fail
# a step — and the real steps do not raise. `compare_current` returns
# {"verdict": "fail"}; the harness receipt returns EXIT_REFUSED; the freeze
# returns a refusal string. All three reported RAN and the walk continued.
# Worse, one function held two contradictory notions of failure: the
# bare-command path used subprocess check=True and DID fail, while the callable
# path used by five of the six real steps had no definition of failure at all.
def _adapt_capture_baseline(fn, ctx: RunContext) -> Optional[str]:
    return _verdict_failure(fn(ctx.activation_uid), "capture_baseline")


def _adapt_compare_current(fn, ctx: RunContext) -> Optional[str]:
    return _verdict_failure(fn(ctx.activation_uid), "compare_current")


def _adapt_harness_receipt(fn, ctx: RunContext) -> Optional[str]:
    return _exit_code_failure(fn(["--activation-uid", ctx.activation_uid]))


def _verdict_failure(result: Any, what: str) -> Optional[str]:
    """A gate that returns a verdict dict has failed when the verdict is not a
    pass. Reading `verdict` is reading the declared field, not guessing."""
    if isinstance(result, dict):
        verdict = str(result.get("verdict") or "")
        if verdict and verdict not in ("pass", "ok", "clean", "green"):
            return "%s returned verdict %r" % (what, verdict)
    return _exit_code_failure(result)


def _exit_code_failure(result: Any) -> Optional[str]:
    """CLI mains return exit codes. Nonzero is a refusal, not a return."""
    if isinstance(result, bool):
        return None
    if isinstance(result, int) and result != 0:
        return "step returned exit code %d" % result
    if isinstance(result, tuple) and len(result) == 2 and result[1]:
        # decide()-shaped (payload, refusal)
        return "step refused: %s" % (result[1],)
    return None


def _adapt_build_release(fn, ctx: RunContext):
    """The build step's `main()` takes no argv parameter and parses sys.argv
    itself, so the invocation is supplied the only way it accepts one.
    --target, not --bump: the runner is cutting a NAMED version, never guessing
    the next one."""
    if not ctx.version:
        raise ValueError("step 8654900a needs --version (the release being cut)")
    saved = sys.argv
    try:
        # --activation-uid is REQUIRED, not optional. stage6_package_authority
        # refuses a package it cannot attribute — "Deliberately no fallback.
        # There is no 'if we cannot resolve a run, carry on' branch ... a gate a
        # caller can decline is not a gate." Sending only --target left it None
        # and a runner-driven walk could not get through the build step at all.
        #
        # Found by talos-t52's independent rewrite. An adversarial pass had
        # already raised it; I mis-triaged that finding as being about the
        # discarded return value, fixed that half, and left this one. And the
        # flag is absent from the tool's --help because it is parsed by hand
        # from sys.argv, so checking --help nearly made me dismiss a correct
        # report — the help output is not the interface.
        sys.argv = [release_bindings.OPERATOR_TOOLING["build_argv0"],
                    "--target", ctx.version,
                    "--activation-uid", ctx.activation_uid]
        return _exit_code_failure(fn())
    finally:
        sys.argv = saved


def _adapt_freeze_candidate(fn, ctx: RunContext) -> Optional[str]:
    """Supply the freeze step's RUNTIME arguments.

    The declaration names the callable that RECORDS the freeze; this supplies
    the two values a static declaration cannot know, because they do not exist
    until a release is running. That division is the point: an adapter must
    never be where a wrong callable hides, and a declaration must never pretend
    to know a run folder.
    """
    if ctx.candidate is None:
        raise ValueError("the freeze step needs --candidate (the built .zip)")
    return _exit_code_failure(fn([
        "--run-dir", str(ctx.run_dir),
        "--candidate", str(ctx.candidate),
        "--emit",
    ]))


#: step_uid -> how to CALL that step's entry. Keyed by step so the knowledge
#: lives in one readable place; a step with no adapter falls back to a bare
#: `fn()`, which keeps fixture profiles working unchanged.
ADAPTERS: Dict[str, Callable[[Any, RunContext], Any]] = {
    "f9365ede": _adapt_capture_baseline,
    "4262d5fa": _adapt_compare_current,
    "a0f2bea8": _adapt_harness_receipt,
    "8654900a": _adapt_build_release,
    "7de2c49f": _adapt_freeze_candidate,
}


def _args_release_history(ctx: RunContext) -> List[str]:
    """Supply the release-history step's RUNTIME arguments.

    `--release-entry-uid` is REQUIRED by the script and is a per-release fact,
    so the profile's static declaration cannot carry it and must not pretend to
    (the freeze adapter's rule, same reason). Without it the step exits 2 on
    argparse before doing anything.
    """
    if not ctx.release_entry_uid:
        raise ValueError(
            "step 2e9b1db7 needs release_entry_uid, which release plan %s does "
            "not declare" % ctx.release_plan_uid)
    # --registry-path and --executor-agent are NOT optional in practice:
    # the script defaults the registry to a studio-root path that has never
    # been authoritative, and defaults the row's created_by to
    # "unknown-agent". Both defaults write successfully and wrongly, which is
    # this walk's whole failure family. The path comes from the bindings
    # module because the runner may not name a product literal.
    return ["--release-entry-uid", ctx.release_entry_uid,
            "--release-plan-uid", ctx.release_plan_uid,
            "--registry-path",
            str(ctx.vault_root
                / release_bindings.OPERATOR_TOOLING["subsystem_registry_path"]),
            "--executor-agent", ctx.actor]


#: step_uid -> extra argv appended to a BARE-COMMAND entry. The sibling of
#: ADAPTERS for steps declared as a shell command rather than a callable.
#: Both tables exist because both declaration shapes ship in the real profile;
#: neither may silently invoke a step with arguments it does not take.
COMMAND_ARGS: Dict[str, Callable[[RunContext], List[str]]] = {
    "2e9b1db7": _args_release_history,
}


def _record_step(drive, context, step_uid: str) -> Optional[str]:
    """Tell the runtime the step completed, and return a failure reason if it
    could not be recorded.

    A step that RAN but was never recorded is worse than a step that failed:
    nothing downstream becomes eligible, resume has nothing to read, and the
    walk reports success. One helper so the two invocation paths cannot drift
    apart again — which is exactly how the bare-command path came to be missing
    this entirely.
    """
    if context is None:  # a cold walk has no run to drive
        return None
    recorded = drive(context, "step-complete", step_uid,
                     ["--artifact-links", str(context.run_dir)])
    if recorded:
        return "step ran but could not be recorded: %s" % recorded
    return None

def _requires_orchestrator_invoked(ctx: RunContext) -> Optional[str]:
    """The publish step may not be reached until the principal has run the
    orchestrator, because the release scorecard cannot be valid without it.

    WHY THIS IS A GATE AND NOT SOMETHING THE RUNNER DOES ITSELF. The obvious
    "fix" is for this runner to write the orchestrator-invoked event on its own
    during the walk. That would be forgery. That event records, in its
    own author's words, "the moment Mike runs the bare orchestrator" — it is
    stamped `actor: "mike"` and it is counted as a PRINCIPAL INPUT on the
    release scorecard, the instrument that measures how many gestures a release
    costs the human. A machine writing it would inflate the count of human
    gestures with a gesture no human made, in the one number built to keep us
    honest about that. So the runner refuses to pass, and says what to run.

    This is the defect that cost v1.92 its completion, turned into a gate: the
    correct order was written down (LOCK -> BOOTSTRAP -> STEPS -> BUILD ->
    STAGE -> PREFLIGHT -> ORCHESTRATOR -> FIRE) and nothing enforced it, so the
    orchestrator step was skipped, `orchestrator_started_at` stayed null, the
    scorecard was invalid, and the saga could not close. Prose became a gate
    that reads world state.
    """
    # D-9: this used to scan only run_dir/run.jsonl while the scorecard's own
    # reader scans the journal AND the canonical event bus, joined on
    # data.pipeline_run_uid — and that reader's docstring explains why the
    # second store is not optional: "scope_locked has NEVER appeared in a
    # release run journal — not once. It is emitted to the canonical event bus
    # by the lock tool." A gate bound to one store, for a vocabulary that
    # demonstrably writes to both, would refuse forever on any run whose
    # orchestrator event landed on the bus.
    #
    # So it asks the declared reader instead of being a third one.
    orchestrator = _load_tool(
        release_bindings.OPERATOR_TOOLING["orchestrator_module"], TOOLS_DIR)
    if orchestrator is None or not hasattr(orchestrator, "_journal_timestamps"):
        return ("cannot load the release orchestrator to check whether the "
                "orchestrator step has run")
    try:
        identity = orchestrator._identity(ctx.run_dir) or {}
        stamps = orchestrator._journal_timestamps(ctx.run_dir, identity, ctx.vault_root)
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        # SystemExit is NOT an Exception, and _identity raises it by design on a
        # run whose journal names no saga. I fixed exactly this in the execution
        # path (D-5) two hours before writing it again here, which is the whole
        # argument for the guard below rather than for being careful.
        #
        # Fail closed. A gate that crashes on a malformed run is worse than one
        # that refuses: the traceback stops the walk with no cure named, and a
        # caller that caught it would read the crash as "no opinion".
        return ("could not read this run's moments (%s: %s) — refusing rather "
                "than assuming the orchestrator ran"
                % (type(exc).__name__, exc))
    if stamps.get("orchestrator_started_at"):
        return None
    return (
        "the orchestrator has not been run for this release, so the release "
        "scorecard cannot be valid and the saga cannot complete.\n"
        "           Run this, then run this command again:\n"
        "               %s" % (release_bindings.OPERATOR_TOOLING[
            "orchestrator_command"] % ctx.release_plan_uid,)
    )


#: step_uid -> a check that must pass before the walk may reach that step.
#: These read world state, never a claim that something happened.
PRECONDITIONS: Dict[str, Callable[[RunContext], Optional[str]]] = {
    "3dd817cb": _requires_orchestrator_invoked,
}


#: What an operator runs for a step the runner will not invoke itself. Flags
#: verified against the tool's own --help, per AC4.
NOT_INVOKED_COMMANDS: Dict[str, str] = {
    "3dd817cb": release_bindings.OPERATOR_TOOLING["publish_command"],
}


#: The one irreversible outward act. Never invoked by this runner, at any flag.
#: It has its own authorization gate and its own TTY confirmation, and routing a
#: fire through a walk would put a second, weaker door on the same room.
NEVER_INVOKED = frozenset({"3dd817cb"})

#: D-6: keying the boundary to a literal uid means a profile that renumbers the
#: publish step, or adds a second one, walks straight past it. The SLOT is the
#: declared structure; the uid is one instance of it. Both are checked, so the
#: guard survives a step being renamed.
PUBLISH_SLOTS = frozenset({"publish-the-artifact"})


def _is_outward_act(step_uid: str, slot: str) -> bool:
    return step_uid in NEVER_INVOKED or slot in PUBLISH_SLOTS


def _resolve_callable(entry: str, base_dir: Path):
    """Resolve a `<path>:<callable>` entry to a live Python callable, or
    None when the entry is not shaped that way or does not resolve — a
    bare command string (most of today's real tool bindings) is reported,
    never guessed at as something to import."""
    if entry.count(":") != 1:
        return None
    script_part, _, callable_name = entry.partition(":")
    script_path = Path(script_part)
    if not script_path.is_absolute():
        script_path = base_dir / script_path
    if not script_path.is_file():
        return None
    module_name = "release_run_dynamic_%s" % abs(hash(str(script_path)))
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    # Registering before exec_module avoids the dataclasses/py3.9 load-by-
    # path AttributeError Argus A156 flagged when he declared the binding
    # contract — the same hazard applies to any module loaded this way.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, callable_name, None)


#: The enforced path for recording that a human gate was satisfied. The
#: standalone `human-signoff` CLI was retired at v1.66; `resume` is the one
#: path that carries the independence checks. Flags verified against the
#: tool's own --help, which is what AC4 exists to keep true.
SIGNOFF_COMMAND = release_bindings.OPERATOR_TOOLING["signoff_command"]


def _drive_runtime(ctx: RunContext, subcommand: str, step_uid: str,
                   extra: Optional[List[str]] = None) -> Optional[str]:
    """Tell the pipeline runtime what this walk just did.

    THE DEFECT THIS CLOSES, found by the first real release this runner ever
    drove: the runner executed a step and never told the runtime. The step
    stayed `declared`, `current_step` stayed None, and only the first step was
    ever eligible — so the doc leg refused with "not eligible in this run" and
    the walk could not pass step one on a real release.

    Worse, the resume this runner is built around reads step state from the
    run's own record, and NOTHING WROTE IT. Every resume test passed because
    the fixtures wrote that state by hand. Only a real release could surface
    this, because only a real release has a runtime holding an opinion.

    A walker that does not advance the run is not a driver. This is the walk's
    half of the contract.
    """
    runtime = TOOLS_DIR / "9e7003b1.py"
    if not runtime.is_file() or not ctx.activation_uid:
        return "cannot reach the pipeline runtime to record %s" % subcommand
    cmd = [sys.executable, str(runtime), "--activation-uid", ctx.activation_uid,
           subcommand, step_uid] + list(extra or [])
    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=str(ctx.vault_root))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return "%s %s refused: %s" % (subcommand, step_uid,
                                      detail[-1] if detail else "no detail")
    return None


#: How the walk records itself with the pipeline runtime. Production always
#: uses the real driver; tests may substitute one, and two tests assert that
#: THIS default is the real one and that the walk actually calls it — a
#: tolerant no-op driver is how the original defect hid for a whole cycle.
RUNTIME_DRIVER = _drive_runtime


def _judgment_command(
    executor: Optional[str], entry: str, context: Optional[RunContext] = None
) -> str:
    """What the operator must actually DO and then RUN at a judgment step.

    This used to return "read and perform playbook <uid> as executor class
    'vela'" — a description, not a command. An operator who has done the work
    is then stuck: nothing tells them how to record it, so the walk halts at
    the same step forever. That is the shape this Studio keeps shipping, and
    A155 named it inside Argus's own boot contract: a step that names a tool
    without its exact invocation is the defect.

    With a context the second line is runnable verbatim except for the
    principal's name.
    """
    doing = "perform %s as executor class %r" % (entry, executor)
    if context is None:
        return doing
    if not context.activation_uid:
        # D-8: this used to return the bare description — verbatim the shape
        # this function's own docstring calls the defect — with no warning on
        # the halt line. Measured across the twelve release runs on disk, two
        # are in that state. Say so, rather than quietly becoming the thing
        # AC4 was written to remove.
        return ("%s\n           then record it — but this run names no "
                "activation, so the signoff command cannot be built. Find it in "
                "the run's release-authorization.json or run.state.json, then:\n"
                "               %s" % (doing, SIGNOFF_COMMAND % "<activation-uid>"))
    return "%s\n           then record it and re-run this command:\n               %s" % (
        doing, SIGNOFF_COMMAND % context.activation_uid,
    )


def walk(
    profile: ReleaseProfile,
    base_dir: Optional[Path] = None,
    execute: bool = False,
    context: Optional[RunContext] = None,
    drive=None,
) -> RunOutcome:
    """Walk a profile's steps in declared order, resuming past what is done.

    Without a `context` this behaves exactly as it always has: a cold report
    that halts at the first judgment step and, under `execute`, calls resolvable
    entries with no arguments (which is all a fixture profile needs).

    With a `context` it becomes the resumable runner the one-command release
    needs:

    * a step the run's own `run.state.json` records terminal is SKIPPED, so
      re-running is safe and picks up where the last call stopped — including
      past judgment steps a human has since satisfied;
    * a deterministic step is invoked through its adapter, with the arguments
      it actually takes;
    * a bare-command entry is run as a subprocess from the Studio root, rather
      than being reported and silently not done;
    * a step that raises stops the walk as "failed" — never reported as fine;
    * a pending judgment step halts the walk and names what a human must do.

    The publish step is never invoked here (see NEVER_INVOKED): it owns its own
    authorization and TTY confirmation, and a walk must not become a second,
    weaker door to the same room.
    """
    base_dir = base_dir if base_dir is not None else TOOLS_DIR
    drive = drive if drive is not None else RUNTIME_DRIVER
    statuses = step_status(context.run_dir) if context is not None else {}
    actions: List[RunAction] = []

    for slot_spec in profile.slots:
        for binding in slot_spec.steps:
            done = statuses.get(binding.step_uid, "") in TERMINAL_STEP_STATES
            if done:
                actions.append(RunAction(
                    step_uid=binding.step_uid, slot=slot_spec.slot,
                    deterministic=binding.deterministic, executor=binding.executor,
                    description=binding.description,
                    command=binding.entry if binding.deterministic
                    else _judgment_command(binding.executor, binding.entry, context),
                    invoked=False, already_done=True,
                ))
                continue

            precondition = PRECONDITIONS.get(binding.step_uid)
            if precondition is not None and context is not None:
                unmet = precondition(context)
                if unmet:
                    action = RunAction(
                        step_uid=binding.step_uid, slot=slot_spec.slot,
                        deterministic=binding.deterministic,
                        executor=binding.executor, description=binding.description,
                        command=unmet, invoked=False,
                    )
                    actions.append(action)
                    return RunOutcome(status="halted", actions=actions,
                                      halted_at=action)

            if binding.deterministic:
                invoked = False
                error: Optional[str] = None
                if execute and not _is_outward_act(binding.step_uid, slot_spec.slot):
                    if context is not None:
                        opened = drive(context, "step-start", binding.step_uid)
                        if opened:
                            error = opened
                    try:
                        if error:
                            raise RuntimeError(error)
                        fn = _resolve_callable(binding.entry, base_dir)
                        if fn is not None:
                            adapter = ADAPTERS.get(binding.step_uid)
                            if adapter is not None and context is not None:
                                failure = adapter(fn, context)
                            else:
                                failure = _exit_code_failure(fn())
                            if failure:
                                error = failure
                            else:
                                invoked = True
                                recorded = _record_step(
                                    drive, context, binding.step_uid)
                                if recorded:
                                    error = recorded
                                    invoked = False
                        elif context is not None and binding.entry.strip():
                            # A bare command string. Reporting it and doing
                            # nothing is how a step silently never runs.
                            #
                            # TWO defects lived here until argus-a160 drove the
                            # first walk that ever REACHED one of these steps
                            # (2e9b1db7 was unreachable behind the profile's
                            # step-order defect, so this branch had never run
                            # against a real release):
                            #
                            #  1. No arguments. Identical to the defect A159
                            #     fixed on the callable path above — fixed
                            #     there, left here, because only the callable
                            #     path had ever executed. COMMAND_ARGS is this
                            #     path's ADAPTERS.
                            #  2. NO RUNTIME RECORDING — the worse one, because
                            #     it fails SILENTLY. The callable path records
                            #     step-complete; this one set invoked=True and
                            #     returned. A bare-command step would run,
                            #     report success, and leave the runtime never
                            #     marking it complete — so nothing downstream
                            #     becomes eligible and resume has nothing to
                            #     read. That is verbatim the class A159 named
                            #     as one of the two defects only a real release
                            #     found; it was fixed on one path of two.
                            command = binding.entry
                            extra = COMMAND_ARGS.get(binding.step_uid)
                            if extra is not None:
                                command = " ".join(
                                    [command]
                                    + [shlex.quote(a) for a in extra(context)])
                            subprocess.run(
                                command, shell=True, check=True,
                                cwd=str(context.vault_root),
                            )
                            invoked = True
                            recorded = _record_step(
                                drive, context, binding.step_uid)
                            if recorded:
                                error = recorded
                                invoked = False
                    except SystemExit as exc:
                        # D-5: `except Exception` does not catch SystemExit, and
                        # an adapted CLI main() exits that way — so a refusing
                        # build tore the whole walk down instead of failing its
                        # step. A zero exit is that tool's success.
                        code = exc.code if exc.code is not None else 0
                        if code not in (0, None):
                            error = "step exited with code %r" % (code,)
                        else:
                            invoked = True
                    except Exception as exc:  # noqa: BLE001 — surfaced, never swallowed
                        error = "%s: %s" % (type(exc).__name__, exc)
                action = RunAction(
                    step_uid=binding.step_uid, slot=slot_spec.slot,
                    deterministic=True, executor=binding.executor,
                    description=binding.description, command=binding.entry,
                    invoked=invoked, error=error,
                )
                actions.append(action)
                if error is not None:
                    return RunOutcome(status="failed", actions=actions, failed_at=action)
                if execute and not invoked and context is not None:
                    # F3 (independent verification, 2026-08-26): a pending step
                    # the runner did not invoke must NOT fall through to
                    # "complete". With the publish step pending, an executing
                    # walk previously printed "[complete] every step in this
                    # profile is deterministic" and returned 0 — a green report
                    # over a step that never happened, which is the exact shape
                    # that let v1.92 ship without its scorecard. Reproduced at
                    # the LAST step of the walk, in the tool built to prevent it.
                    halt = RunAction(
                        step_uid=binding.step_uid, slot=slot_spec.slot,
                        deterministic=True, executor=binding.executor,
                        description=binding.description,
                        command=NOT_INVOKED_COMMANDS.get(
                            binding.step_uid,
                            "this step was not invoked by the runner; run its "
                            "entry yourself: %s" % binding.entry),
                        invoked=False,
                    )
                    actions[-1] = halt
                    return RunOutcome(status="halted", actions=actions, halted_at=halt)
            else:
                action = RunAction(
                    step_uid=binding.step_uid, slot=slot_spec.slot,
                    deterministic=False, executor=binding.executor,
                    description=binding.description,
                    command=_judgment_command(binding.executor, binding.entry, context),
                    invoked=False,
                )
                actions.append(action)
                return RunOutcome(status="halted", actions=actions, halted_at=action)

    # THE COMPLETION VERDICT. `complete` used to mean "the for-loop ended",
    # which is not a fact about the release: with the publish step pending and
    # everything else terminal, a walk printed "complete" and exited 0 for a
    # release whose one irreversible outward act had never happened. Both
    # independent verifiers reproduced it, and the first repair closed only the
    # --execute path, leaving the default dry run still reporting complete.
    #
    # A release is complete when every step is RECORDED terminal. Anything else
    # is `incomplete`, and the operator is told which steps are outstanding.
    # 4.1 (closing review): this was guarded by `if context is not None`, so a
    # context-free walk could still report "complete" over a publish step that
    # was never invoked. Not reachable with the shipped profile, but the claim
    # this makes — "complete is a fact about the release, not about the loop
    # ending" — held only on one path, and a claim that holds on one path is the
    # shape of every defect in this cycle.
    # WITHOUT a context there is no release to be complete ABOUT: no plan, no
    # run, no recorded state. "complete" there means the profile walked to its
    # end, which is what this function's cold-report contract has always said
    # and what the printed line says ("every step in this profile is
    # deterministic"). The closing review flagged the asymmetry and judged it a
    # sharp edge rather than a false report; changing it broke a documented
    # cold-walk contract to chase a claim the cold path never makes.
    if context is not None:
        outstanding = [a for a in actions if not a.already_done]
        if outstanding:
            return RunOutcome(status="incomplete", actions=actions)
    return RunOutcome(status="complete", actions=actions)


def first_action(profile: ReleaseProfile) -> Optional[RunAction]:
    """The very first action a cold walk reports, from a clean state with
    nothing else run and nothing executed. The runner's cold-start
    property (AC6): computing it has no side effect at all."""
    outcome = walk(profile, execute=False)
    return outcome.actions[0] if outcome.actions else None


def _print_outcome(outcome: RunOutcome) -> None:
    tail = {outcome.halted_at, outcome.failed_at}
    for action in outcome.actions:
        if action in tail:
            continue
        kind = "tool" if action.deterministic else "playbook"
        if action.already_done:
            mark = "already done"
        elif action.invoked:
            mark = "RAN"
        else:
            mark = "reported (not invoked)"
        print(f"  [{mark}] {action.step_uid} ({action.slot}, {kind}) — {action.description}")

    if outcome.status == "failed" and outcome.failed_at is not None:
        bad = outcome.failed_at
        print(f"  [FAILED] {bad.step_uid} ({bad.slot}) — {bad.description}")
        print(f"           {bad.error}")
        print(f"           command: {bad.command}")
        return

    if outcome.status == "halted" and outcome.halted_at is not None:
        halt = outcome.halted_at
        print(
            f"  [HALTED] {halt.step_uid} ({halt.slot}) — executor={halt.executor!r}: "
            f"{halt.description}"
        )
        print(f"           command: {halt.command}")
        print()
        print("  NEXT: that step needs a human or a named agent. Do it, then run "
              "this exact command again — completed steps are skipped.")
        return

    if outcome.status == "incomplete":
        outstanding = [a for a in outcome.actions if not a.already_done]
        print("  [INCOMPLETE] %d step(s) are not recorded done — this release "
              "has NOT shipped:" % len(outstanding))
        for a in outstanding:
            print("               %s (%s) — %s" % (a.step_uid, a.slot, a.description))
        print()
        print("  Re-run with --execute to perform the ones the runner can do.")
        return
    if all(a.already_done for a in outcome.actions) and outcome.actions:
        print("  [complete] every step in this release is already done. "
              "Nothing to do.")
    else:
        print("  [complete] every step in this profile is deterministic.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "profile_uid", nargs="?", default=None,
        help="the uid of a type: release-profile vault entry. Omit to auto-discover "
        "the one release-profile entry under vault/files/ — a stranger should not "
        "need to already know a uid to run this cold.",
    )
    parser.add_argument(
        "--vault-path", default=".", help="Studio root (default: current directory)"
    )
    parser.add_argument(
        "--release-plan-uid", default=None,
        help="the release PLAN uid. Supplying it resolves the run folder and "
        "activation from the run's own files, skips steps already recorded "
        "done, and invokes each step with the arguments it actually takes. "
        "Without it this stays a cold, context-free report.",
    )
    parser.add_argument(
        "--version", default=None,
        help="the version being cut (e.g. X.Y.Z) — required only by the build step",
    )
    parser.add_argument(
        "--candidate", default=None,
        help="path to the built .zip — required only by the freeze step",
    )
    parser.add_argument(
        "--actor", default=None,
        help="who is performing this walk (e.g. argus-a160); stamped onto "
             "records the steps write",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually invoke resolvable deterministic steps. Off by default: a cold "
        "walk with no flag reports intent and invokes nothing.",
    )
    args = parser.parse_args(argv)
    vault_root = Path(args.vault_path)

    if args.profile_uid is None:
        candidates = iter_release_profile_uids(vault_root)
        if len(candidates) != 1:
            print(
                f"ERROR: expected exactly one type: release-profile entry to "
                f"auto-discover under {vault_root / 'vault' / 'files'}, found "
                f"{len(candidates)}: {candidates}. Pass profile_uid explicitly.",
                file=sys.stderr,
            )
            return 2
        profile_uid = candidates[0]
    else:
        profile_uid = args.profile_uid

    try:
        # AC5's leaf validation existed only in the test. Production called
        # load_profile with no declared_leaves, so every leaf-validation path
        # the test exercises was dead here: an independent adversarial pass
        # deleted a real leaf from the governing pipeline and AC5+AC6 stayed
        # fully green while AC2 went 11-failed. The profile kept binding a step
        # that was no longer a leaf, and the seam never noticed.
        profile = load_profile(
            vault_root, profile_uid,
            declared_leaves=release_bindings.declared_leaves(vault_root),
        )
    except Exception as exc:  # operational-misuse class, never a release verdict
        print(f"ERROR: cannot load release profile {profile_uid}: {exc}", file=sys.stderr)
        return 2

    context = None
    if args.release_plan_uid:
        try:
            context = resolve_context(
                vault_root, args.release_plan_uid, version=args.version,
                candidate=Path(args.candidate) if args.candidate else None,
                actor=args.actor,
            )
        except Exception as exc:  # operational misuse, never a release verdict
            print(f"ERROR: cannot resolve release plan {args.release_plan_uid}: {exc}",
                  file=sys.stderr)
            return 2

    if context is not None:
        blocked = plan_is_walkable(vault_root, args.release_plan_uid) or \
            run_is_walkable(context.run_dir)
        if blocked:
            print("ERROR: refusing to walk %s — %s. A superseded or closed run "
                  "still carries its old moments, so walking it can find the "
                  "fire gate already satisfied while every step reads as never "
                  "done." % (context.run_dir.name, blocked), file=sys.stderr)
            return 2

    outcome = walk(profile, execute=args.execute, context=context)
    print(f"=== {profile.product} ({profile.uid}) — {outcome.status} ===")
    if context is not None:
        print(f"    plan {context.release_plan_uid} · run {context.run_dir.name} · "
              f"activation {context.activation_uid or '<unresolved>'}")
        if not args.execute:
            print("    (dry run — pass --execute to actually invoke pending steps)")
    _print_outcome(outcome)
    return 1 if outcome.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
