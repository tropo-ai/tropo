#!/usr/bin/env python3
"""Q9: verify a real harness receipt exists. Never run the harness.

    python3 vault/tools/tropo-check-harness-receipt.py --activation-uid <uid>

This is the verification_command for WorkflowNode `a0f2bea8`
(release-harness-gate). A148's ruling, evt_a9360f18f56fe472_00000027.

WHY THIS SHAPE. `sa.release-test-harness` is a session-agent (24b57c2a, owned by
Vela), not a tool with an entry point — I checked the registry before proposing
this. Mike activates it externally. So the node cannot RUN the harness, and it
must not synthesize a verdict on the harness's behalf: an engine that writes its
own evidence has verified nothing.

What it can do is check that the evidence is real, and that is the whole job.

A RUN-EVENT RECEIPT ALONE IS NOT SELF-AUTHORIZING. That is the load-bearing
half. Anything writing into the run can produce a receipt saying the harness
passed; the receipt is a claim, not proof. So `evidence_ref` must resolve to a
typed test-run record owned by the harness agent, and that record's own release
and package identity must agree with the receipt's. Without that second hop, the
gate checks that someone said the right words.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent

#: The session-agent that owns real harness evidence. Not a tool; never invoked.
HARNESS_AGENT_UID = "24b57c2a"
HARNESS_AGENT_NAME = "sa.release-test-harness"

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2


class HarnessEvidenceRefusal(Exception):
    """The harness instrument cannot be shown to have run against this package."""


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def find_harness_receipt(events, release_run_uid: str, package_sha256: str) -> dict:
    """Exactly one passing agent-executed harness receipt for these bytes."""
    release_verify = _load("q9_verify", "lib/release_verify.py")

    candidates = []
    for event in events or []:
        data = event.get("data") or {}
        if str(data.get("receipt_kind") or "") != release_verify.RECEIPT_KIND:
            continue
        if str(data.get("instrument") or "") != "release-harness":
            continue
        if str(data.get("release_run_uid") or "") != release_run_uid:
            continue
        if str(data.get("package_sha256") or "") != package_sha256:
            continue
        candidates.append(data)

    if not candidates:
        raise HarnessEvidenceRefusal(
            f"no release-harness receipt on run {release_run_uid}. The harness "
            f"is activated by Mike, not by this node — an absent receipt means "
            f"it has not run, and this gate will not run it."
        )
    if len(candidates) > 1:
        raise HarnessEvidenceRefusal(
            f"{len(candidates)} release-harness receipts on run "
            f"{release_run_uid}; exactly one is legal and two means one of "
            f"them is unaccounted for"
        )

    receipt = release_verify.validate_receipt(candidates[0])
    if receipt.release_run_uid != release_run_uid:
        raise HarnessEvidenceRefusal(
            f"the harness receipt belongs to run {receipt.release_run_uid}, "
            f"not {release_run_uid}"
        )
    if receipt.package_sha256 != package_sha256:
        raise HarnessEvidenceRefusal(
            f"the harness tested package {receipt.package_sha256[:12]} and the "
            f"package about to ship is {package_sha256[:12]}"
        )
    if receipt.execution_mode != "agent":
        raise HarnessEvidenceRefusal(
            f"the harness receipt records execution_mode "
            f"{receipt.execution_mode!r}; harness evidence is produced by an "
            f"agent, and a machine-mode receipt here means something "
            f"synthesized it"
        )
    if receipt.verdict != "pass":
        raise HarnessEvidenceRefusal(
            f"the harness reported {receipt.verdict!r}. A present receipt is "
            f"not a passing one."
        )
    return receipt.as_dict()


def resolve_evidence(receipt: dict, read_entry) -> dict:
    """The second hop: the receipt must point at a real record the agent owns.

    Without this the gate is satisfied by anything that can append to the run.
    The receipt says the harness passed; this asks the harness's own record
    whether it agrees.
    """
    ref = str(receipt.get("evidence_ref") or "").strip()
    if not ref:
        raise HarnessEvidenceRefusal("the harness receipt carries no evidence_ref")

    uid = Path(ref).stem if "/" in ref else ref
    entry = read_entry(uid)
    if entry is None:
        raise HarnessEvidenceRefusal(
            f"the harness receipt's evidence_ref {ref!r} does not resolve to a "
            f"governed record. A receipt pointing at nothing is a claim, not "
            f"evidence."
        )

    fm = entry.get("frontmatter") or {}
    owner = str(fm.get("owner") or "")
    executed_by = str(fm.get("executed_by") or fm.get("agent") or "")
    if HARNESS_AGENT_UID not in (owner, executed_by) and \
       HARNESS_AGENT_NAME not in (owner, executed_by):
        raise HarnessEvidenceRefusal(
            f"evidence {uid} is owned by {owner or executed_by or '(unset)'}, "
            f"not {HARNESS_AGENT_NAME}. Evidence the harness did not produce "
            f"cannot show the harness ran."
        )

    # A148 fix 2: `if recorded and ...` made an ABSENT field pass. A test-run
    # naming neither a release run nor a package could authorize a release —
    # the weakest possible evidence satisfied the strongest check, because
    # silence read as agreement.
    #
    # Both fields must be present AND equal. This is the same
    # absence-is-not-agreement shape as G99's index comment and my own
    # unknown-versus-empty bug: a missing value is not a matching one.
    for field, expected, label in (
        ("release_pipeline_run_uid", receipt["release_run_uid"], "release run"),
        ("package_sha256", receipt["package_sha256"], "package"),
    ):
        recorded = str(fm.get(field) or "")
        if not recorded:
            raise HarnessEvidenceRefusal(
                f"evidence {uid} names no {label}. Evidence that does not say "
                f"which {label} it covers cannot show the harness ran against "
                f"this one; absence is not agreement."
            )
        if recorded != expected:
            raise HarnessEvidenceRefusal(
                f"evidence {uid} records {label} {recorded[:12]} but the "
                f"receipt claims {str(expected)[:12]}; the two do not describe "
                f"the same run"
            )
    return {"uid": uid, "owner": owner or executed_by}


def check(activation_uid: str) -> dict:
    runtime = _load("q9_runtime", "9e7003b1.py")
    release_package = _load("q9_package", "lib/release_package.py")

    activation = runtime.read_vault_entry(activation_uid)
    if activation is None:
        raise HarnessEvidenceRefusal(f"activation {activation_uid} does not resolve")
    run_uid = str((activation.get("frontmatter") or {}).get("pipeline_run_uid") or "")
    run = runtime.read_vault_entry(run_uid) if run_uid else None
    if run is None:
        raise HarnessEvidenceRefusal(
            f"activation {activation_uid} names no resolvable pipeline run")
    run_folder = str((run.get("frontmatter") or {}).get("run_folder") or "")
    if not run_folder:
        raise HarnessEvidenceRefusal(f"run {run_uid} declares no run_folder")

    events = runtime.read_events(runtime.VAULT_ROOT / run_folder)
    frozen = release_package.active_frozen_payload(events, run_uid)
    if not frozen or not str(frozen.get("package_sha256") or ""):
        raise HarnessEvidenceRefusal(
            f"run {run_uid} has no frozen package, so there is nothing for the "
            f"harness to have tested")

    receipt = find_harness_receipt(events, run_uid, str(frozen["package_sha256"]))
    evidence = resolve_evidence(receipt, runtime.read_vault_entry)
    return {"run": run_uid, "package_sha256": receipt["package_sha256"],
            "evidence": evidence}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activation-uid", required=True)
    args = parser.parse_args(argv)
    try:
        result = check(args.activation_uid)
    except HarnessEvidenceRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        print(f"  Rerun after the harness records evidence: python3 "
              f"vault/tools/tropo-check-harness-receipt.py --activation-uid "
              f"{args.activation_uid}", file=sys.stderr)
        return EXIT_REFUSED
    except Exception as exc:  # noqa: BLE001 -- unreadable state is a refusal
        print(f"REFUSED: harness evidence could not be read: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"✓ release-harness evidence verified — run {result['run']}, package "
          f"{result['package_sha256'][:12]}…, evidence {result['evidence']['uid']} "
          f"owned by {result['evidence']['owner']}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
