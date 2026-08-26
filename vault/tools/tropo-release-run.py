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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib.release_profile import (  # noqa: E402
    ReleaseProfile,
    iter_release_profile_uids,
    load_profile,
)
from lib import release_bindings  # noqa: E402

__all__ = ["RunAction", "RunOutcome", "walk", "first_action"]


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


def _judgment_command(executor: Optional[str], entry: str) -> str:
    """The runnable instruction for a judgment step: no universal CLI runs
    a governed playbook in this Studio, so the actionable command IS the
    instruction to a named executor class."""
    return "read and perform playbook %s as executor class %r" % (entry, executor)


def walk(
    profile: ReleaseProfile,
    base_dir: Optional[Path] = None,
    execute: bool = False,
) -> RunOutcome:
    """Walk a profile's steps in declared order (build, then verify, then
    publish; declared order within a slot), stopping at the first judgment
    step it reaches.

    `execute=False` (the default) never calls anything — every deterministic
    step is reported with `invoked=False`. `execute=True` additionally
    resolves each deterministic step's `entry` via `_resolve_callable` and
    calls it when resolvable; a bare command-string entry that does not
    resolve is still reported, just not invoked — reporting is never
    silently downgraded to nothing happening.
    """
    base_dir = base_dir if base_dir is not None else TOOLS_DIR
    actions: List[RunAction] = []
    for slot_spec in profile.slots:
        for binding in slot_spec.steps:
            if binding.deterministic:
                invoked = False
                if execute:
                    fn = _resolve_callable(binding.entry, base_dir)
                    if fn is not None:
                        fn()
                        invoked = True
                action = RunAction(
                    step_uid=binding.step_uid,
                    slot=slot_spec.slot,
                    deterministic=True,
                    executor=binding.executor,
                    description=binding.description,
                    command=binding.entry,
                    invoked=invoked,
                )
                actions.append(action)
            else:
                action = RunAction(
                    step_uid=binding.step_uid,
                    slot=slot_spec.slot,
                    deterministic=False,
                    executor=binding.executor,
                    description=binding.description,
                    command=_judgment_command(binding.executor, binding.entry),
                    invoked=False,
                )
                actions.append(action)
                return RunOutcome(status="halted", actions=actions, halted_at=action)
    return RunOutcome(status="complete", actions=actions)


def first_action(profile: ReleaseProfile) -> Optional[RunAction]:
    """The very first action a cold walk reports, from a clean state with
    nothing else run and nothing executed. The runner's cold-start
    property (AC6): computing it has no side effect at all."""
    outcome = walk(profile, execute=False)
    return outcome.actions[0] if outcome.actions else None


def _print_outcome(outcome: RunOutcome) -> None:
    for action in outcome.actions[:-1] if outcome.status == "halted" else outcome.actions:
        kind = "tool" if action.deterministic else "playbook"
        ran = "ran" if action.invoked else "reported (not invoked)"
        print(
            f"  [{ran}] {action.step_uid} ({action.slot}, {kind}) — {action.description}"
        )
    if outcome.status == "halted" and outcome.halted_at is not None:
        halt = outcome.halted_at
        print(
            f"  [HALTED] {halt.step_uid} ({halt.slot}) — executor={halt.executor!r}: "
            f"{halt.description}"
        )
        print(f"           command: {halt.command}")
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

    outcome = walk(profile, execute=args.execute)
    print(f"=== {profile.product} ({profile.uid}) — {outcome.status} ===")
    _print_outcome(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
