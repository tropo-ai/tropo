#!/usr/bin/env python3
"""
---
uid: aeb2df3d
name: lock-dev-spec
type: tool
title: "lock-dev-spec — atomic dev-spec lock + pipeline-activation registration (ADR-052)"
status: active
owner: talos
domain: "The dev-spec LOCK gesture, made runnable per ADR-052 (ee0e35ad): locking a dev-spec ATOMICALLY registers its dev-pipeline activation, so the audit chain (dev-spec<->activation<->build<->release) is intact by default. Implements the tropo-dev-spec.capsule.md Studio-Shop-Signage's forthcoming 'lock-dev-spec.skill.md' as a runnable tool. Refines/extends the coupling-fix dev-spec (8f15f08d) per ADR-052's PRIMARY design; check_dev_spec_activation_coupling in tropo-validate.py stays the always-on BACKSTOP, unmodified by this build."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-lock-dev-spec.py"
script_path: vault/tools/tropo-lock-dev-spec.py
spawnable_by:
  - all-executives
input:
  type: object
  properties:
    dev-spec-uid: {type: string, description: "8-hex UID of the dev-spec to lock"}
    locked-by: {type: string, description: "principal locking (agent slug or entity UID)"}
    pipeline-uid: {type: string, description: "dev-pipeline template UID to activate against (default: cd1fcd25, this studio's dev-pipeline)"}
    cycle-context: {type: string, description: "optional human-readable cycle/run context, forwarded to pipeline-activate.py"}
output:
  type: object
  description: "prints '<dev_spec_uid> LOCKED activation=<activation_uid>' on success (exit 0); refuses (non-zero exit, dev-spec file UNCHANGED byte-for-byte) if the activation cannot be opened or the dev-spec is not in a lockable state"
created: '2026-07-07'
created_by: talos-t25
modified: '2026-07-07'
modified_by: talos-t25
governed_by: d5e1b4a3
member_of:
  - "8dd772a0"
schema_version: 2
belt: false  # trimmed from belt by vela-v65 2026-07-10 — over the 15-entry cap; mount/publish are federation-specific, lock-dev-spec is ceremony-specific. Cataloged + functional; not in quick-ref.
extraction_scope: argo-reference
trigger_description: "Lock a dev-spec; atomically opens its correlated dev-pipeline activation in the same gesture (ADR-052)."
belt_invocation: "python3 vault/tools/tropo-lock-dev-spec.py --dev-spec-uid <uid> --locked-by <agent>"
belt_example: "python3 vault/tools/tropo-lock-dev-spec.py --dev-spec-uid 943bb220 --locked-by argus"
---
"""

"""tropo-lock-dev-spec.py — the dev-spec LOCK gesture, made runnable (ADR-052).

Authored 2026-07-07 by Talos T25 per Argus's work-order (event 00005883, Item
2) — "build the coupling RUNNABLE-LOCK per 8f15f08d as REFINED BY ADR-052
(ee0e35ad, Mike-accepted) — make the dev-spec LOCK gesture atomically register
its pipeline activation."

ADR-052's decision, verbatim: "Locking a dev-spec ATOMICALLY registers its
pipeline activation. The lock gesture is made runnable... on lock it (a)
flips status: locked and (b) opens the correlated type: activation carrying
the dev-spec's dev_spec_uid — as ONE INDIVISIBLE ACT." This script is that
runnable gesture. It does not replace check_dev_spec_activation_coupling
(8f15f08d) in tropo-validate.py — that check remains the always-on BACKSTOP
that catches any escape around this gesture (hand-edited status: locked,
legacy drift, etc.). This script makes the COMPLIANT path the EASY path, so
there is nothing to be tempted away from.

Atomicity model (single-process, no true distributed transaction available):
  1. Resolve whether a pipeline activation is ALREADY correlated to this
     dev-spec (any status — mirrors check_dev_spec_activation_coupling's own
     "existence is the gate, not activeness" semantics). If one already
     exists (e.g. a prior retroactive feed-the-pipeline cure), reuse it —
     do NOT open a redundant second activation.
  2. If none exists, invoke the real pipeline-activate.py (e337f1dd.py) as a
     subprocess — the SAME tool + invocation shape used for every other
     dev-pipeline activation in this studio (retroactive or live) — to open
     one, BEFORE touching the dev-spec file at all.
  3. Only if step 1 or step 2 produces a real, on-disk, correlated activation
     does this script flip the dev-spec's own status -> locked (+ locked_by
     + locked_at + a new dev_spec_activation_uid backreference). If the
     activation-open fails for any reason, this script aborts WITHOUT
     touching the dev-spec file — so the dev-spec can never end up
     status:locked without a real, verified-present activation. That is the
     "indivisible act" ADR-052 requires, made structural rather than merely
     ordered-in-a-runbook.

The dev-spec frontmatter edit is a SURGICAL line-level patch (regex-targeted),
not a full YAML re-serialization — this avoids reformatting a live,
hand-authored dev-spec's existing quote/flow-style conventions, matching the
discipline this session's other tools use when touching pre-existing files
(vs. freshly-authoring new ones, which pipeline-activate.py does with a full
template).

Usage:
    python3 vault/tools/tropo-lock-dev-spec.py \\
        --dev-spec-uid <8-hex> \\
        --locked-by <agent-slug-or-entity-uid> \\
        [--pipeline-uid <8-hex>]   # default: cd1fcd25 (dev-pipeline)
        [--cycle-context <str>]    # forwarded to pipeline-activate.py

Exit codes:
    0   Success — dev-spec locked, activation correlated (new or reused)
    1   Refused — dev-spec not lockable, already locked, or activation-open
        failed (dev-spec file is UNCHANGED in every refusal case)
    2   Internal invariant failure (activation reported success but no
        correlated record is found on disk — should not happen; investigate
        e337f1dd.py before retrying)
    3   Argument / environment error
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
PIPELINE_ACTIVATE_SCRIPT = Path(__file__).resolve().parent / "e337f1dd.py"
DEFAULT_PIPELINE_UID = "cd1fcd25"  # dev-pipeline
LOCKABLE_STATUSES = {"draft"}


def render_lock_run_created(
    *,
    run_uid: str,
    activation_uid: str,
    root_uid: str,
    dev_spec_uid: str,
    pipeline_uid: str,
    pipeline_version: str,
    actor: str,
    timestamp: Optional[str] = None,
    backfilled_by: Optional[str] = None,
) -> str:
    """Render the single journal seed authored atomically by the lock.

    The lock creates the run identity and folder, so it owns the first event.
    ``bootstrap_pending`` tells pipeline-runtime this is a lock seed, not a
    completed bootstrap: runtime adopts this exact event once, then appends the
    immutable activation contract and step declarations without duplicating
    ``run_created``.
    """
    ts = timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    span_id = hashlib.sha256(
        f"{activation_uid}:{run_uid}:run_created".encode("utf-8")
    ).hexdigest()[:16]
    data = {
        "pipeline": pipeline_uid,
        "pipeline_uid": pipeline_uid,
        "pipeline_version": pipeline_version,
        "pipeline_run_uid": run_uid,
        "dev_spec_uid": dev_spec_uid,
        "activation_uid": activation_uid,
        "activation_root_uid": root_uid,
        "members": [root_uid],
        "authorized_by": actor,
        "bootstrap_pending": True,
    }
    if backfilled_by:
        data["backfilled_by"] = backfilled_by
    event = {
        "event": "run_created",
        "ts": ts,
        "actor": actor,
        "actor_label_resolved": None,
        "step": None,
        "stage": None,
        "data": data,
        "schema_version": 2,
        "trace_id": activation_uid,
        "span_id": span_id,
        "parent_span_id": None,
    }
    return json.dumps(event, ensure_ascii=False) + "\n"


def split_frontmatter(text: str) -> Optional[str]:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    return text[4:end]


def parse_frontmatter(text: str) -> dict:
    fm_text = split_frontmatter(text)
    if fm_text is None:
        return {}
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def backfill_missing_run_journal(
    run_uid: str,
    *,
    files_dir: Path = VAULT_FILES,
    vault_root: Path = VAULT_ROOT,
    backfilled_by: str,
) -> Path:
    """Create only the missing lock seed for one already-declared run.

    This is intentionally refusal-heavy: it never overwrites a journal, never
    guesses a folder, and only repairs a pipeline-run whose lock declaration
    snapshot is present. The caller supplies an explicit UID, keeping a bounded
    principal-approved backfill bounded.
    """
    entry_path = files_dir / f"{run_uid}.md"
    if not entry_path.is_file():
        raise ValueError(f"pipeline-run {run_uid} does not resolve")
    fm = parse_frontmatter(entry_path.read_text(encoding="utf-8"))
    if fm.get("type") != "pipeline-run":
        raise ValueError(f"{run_uid} is not type:pipeline-run")
    run_folder = str(fm.get("run_folder") or "")
    if not run_folder:
        raise ValueError(f"pipeline-run {run_uid} declares no run_folder")
    folder = (vault_root / run_folder).resolve()
    try:
        folder.relative_to(vault_root.resolve())
    except ValueError as exc:
        raise ValueError(f"pipeline-run {run_uid} run_folder escapes the Studio") from exc
    if not (folder / "declaration-snapshot.json").is_file():
        raise ValueError(
            f"pipeline-run {run_uid} has no declaration-snapshot.json; "
            "this is not the bounded lock-writer gap"
        )
    journal = folder / "run.jsonl"
    if journal.exists():
        raise FileExistsError(f"pipeline-run {run_uid} already has run.jsonl")
    journal.write_text(
        render_lock_run_created(
            run_uid=run_uid,
            activation_uid=str(fm.get("activation") or ""),
            root_uid=str(fm.get("activation_root_uid") or ""),
            dev_spec_uid=str(fm.get("dev_spec_uid") or ""),
            pipeline_uid=str(fm.get("pipeline") or ""),
            pipeline_version=str(fm.get("pipeline_version") or ""),
            actor=str(fm.get("created_by") or fm.get("owner") or "unknown"),
            backfilled_by=backfilled_by,
        ),
        encoding="utf-8",
    )
    return journal


def find_correlated_activation(dev_spec_uid: str, files_dir: Path = VAULT_FILES) -> Optional[dict]:
    """Mirrors check_dev_spec_activation_coupling's own correlation semantics
    (tropo-validate.py): ANY type:activation entry anywhere in vault/files/
    whose dev_spec_uid matches, of ANY status, counts — existence is the
    gate, not activeness (2ffdd9d6/35c12763 precedent)."""
    if not files_dir.is_dir():
        return None
    for f in sorted(files_dir.glob("*.md")):
        try:
            text = f.read_text(errors="replace")
        except Exception:
            continue
        fm = parse_frontmatter(text)
        if fm.get("type") == "activation" and str(fm.get("dev_spec_uid") or "") == dev_spec_uid:
            fm.setdefault("uid", f.stem)
            return fm
    return None


def flip_dev_spec_to_locked(raw_text: str, locked_by: str, today: str, activation_uid: str) -> str:
    """Surgical frontmatter patch: flip status -> locked, add locked_by /
    locked_at / dev_spec_activation_uid, refresh modified / modified_by.
    Touches no other line — does not round-trip the file through a full YAML
    dump, which would risk reformatting a hand-authored file's existing
    quote/flow-style conventions."""
    if not raw_text.startswith("---\n"):
        raise ValueError("dev-spec file has no opening frontmatter fence")
    end = raw_text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("dev-spec file frontmatter is not closed")
    fm_block = raw_text[4:end]
    rest = raw_text[end + 5:]

    lines = fm_block.split("\n")
    out_lines = []
    status_replaced = False
    modified_replaced = False
    modified_by_replaced = False
    for line in lines:
        if re.match(r"^status:\s*", line):
            out_lines.append("status: locked")
            status_replaced = True
        elif re.match(r"^modified:\s*", line):
            out_lines.append(f"modified: '{today}'")
            modified_replaced = True
        elif re.match(r"^modified_by:\s*", line):
            out_lines.append("modified_by: tropo-lock-dev-spec.py")
            modified_by_replaced = True
        else:
            out_lines.append(line)

    if not status_replaced:
        raise ValueError("dev-spec frontmatter has no status: field to flip")
    if not modified_replaced:
        out_lines.append(f"modified: '{today}'")
    if not modified_by_replaced:
        out_lines.append("modified_by: tropo-lock-dev-spec.py")

    final_lines = []
    for line in out_lines:
        final_lines.append(line)
        if line == "status: locked":
            final_lines.append(f"locked_by: {locked_by}")
            final_lines.append(f"locked_at: '{today}'")
            final_lines.append(f"dev_spec_activation_uid: '{activation_uid}'")

    new_fm_block = "\n".join(final_lines)
    return f"---\n{new_fm_block}\n---\n{rest}"


def open_activation(pipeline_uid: str, locked_by: str, cycle_context: str,
                     dev_spec_uid: str, vault_root: Path = VAULT_ROOT,
                     activate_script: Path = PIPELINE_ACTIVATE_SCRIPT):
    """Invoke the real pipeline-activate.py as a subprocess — the same tool +
    invocation shape used for every dev-pipeline activation in this studio
    (retroactive or live). Returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        [
            sys.executable, str(activate_script),
            "--pipeline-uid", pipeline_uid,
            "--activated-by", locked_by,
            "--cycle-context", cycle_context,
            "--dev-spec-uid", dev_spec_uid,
        ],
        capture_output=True, text=True, cwd=str(vault_root),
    )
    return result.returncode, result.stdout, result.stderr


def plan_dev_snapshot_transaction(
    dev_spec_uid: str, locked_by: str, activation_uid: Optional[str] = None,
    files_dir: Path = VAULT_FILES, runs_dir: Optional[Path] = None,
    mint: Optional[object] = None, cycle_context: str = "",
):
    """AC2's snapshot transaction, on the shared mechanism (0a0a6777 §2).

    Contract §2 calls the two locks a symmetric pair. Until now only the release
    side had the transaction, so "symmetric" was an aspiration; this instantiates
    the SAME primitive for dev, which is what makes it real rather than a phrase
    in a spec.

    What AC2 asks for, in one indivisible act: one activation root, one
    pipeline-run and run folder, and immutable hashes of the spec, its ACs, and
    its committed substrate. Specify only confirms this snapshot afterwards; it
    does not author or repin it.
    """
    import json as _json
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lib import ignition as _ig, lock_transaction as _lt

    runs = runs_dir or (files_dir.parent / "pipeline-runs")
    spec_path = files_dir / f"{dev_spec_uid}.md"

    def _read(uid):
        path = files_dir / f"{uid}.md"
        if not path.is_file():
            return None
        return {"frontmatter": parse_frontmatter(path.read_text(encoding="utf-8"))}

    def _entry_bytes(uid):
        path = files_dir / f"{uid}.md"
        return path.read_bytes() if path.is_file() else None

    snapshot = _ig.snapshot_declarations(
        DEFAULT_PIPELINE_UID, _read,
        lambda uid: _resolve_step_uids(uid, files_dir),
        read_bytes=_entry_bytes)

    # Hashed from the file, not from a parse: a projection moves when the parser
    # changes, and then an "immutable" hash moves without the input moving.
    inputs = _ig.input_snapshot([("dev_spec", spec_path)])
    # AC2 names spec, ACs and committed substrate as three inputs. A whole-file
    # hash proves the spec moved and cannot say whether it was a typo or the
    # acceptance criteria being rewritten under the run.
    inputs.update(_ig.spec_component_digests(spec_path.read_text(encoding="utf-8")))

    minter = mint or (lambda exclude=frozenset(): _mint_uid(files_dir, exclude))

    # A pre-existing correlated activation is REUSED, never duplicated (ADR-052
    # "existence is the gate") — AND SO IS ITS ROOT.
    #
    # argus-a147 residual 1: the first version reused the activation and then
    # minted a fresh root anyway, so the reuse path produced a second root just
    # as the subprocess path had. Reusing half an identity is not reuse; it
    # leaves two roots claiming one cycle, and Rule 12 has two things to archive
    # where there should be one.
    reused_activation = activation_uid is not None
    existing = None
    if not reused_activation:
        existing = find_correlated_activation(dev_spec_uid, files_dir=files_dir)
        if existing is not None:
            activation_uid = existing.get("uid")
            reused_activation = True

    root_uid = None
    if reused_activation:
        if existing is None:
            existing = _read_entry_frontmatter(activation_uid, files_dir)
        root_uid = _resolve_existing_root(activation_uid, existing, files_dir)

    if root_uid is None:
        root_uid = minter()
    run_uid = minter({root_uid})
    if not reused_activation:
        activation_uid = minter({root_uid, run_uid})
    run_name = f"dev-pipeline-{run_uid}-{time.strftime('%Y-%m-%d')}"
    today = time.strftime("%Y-%m-%d")

    plan = _lt.LockPlan(kind="dev-spec-lock", subject_uid=dev_spec_uid, actor=locked_by)
    plan.notes = {
        "activation_uid": activation_uid,
        "activation_reused": reused_activation,
        "activation_root_uid": root_uid,
        "run_uid": run_uid,
        "declaration_digest": snapshot.digest,
        "pipeline_version": snapshot.pipeline_version,
        **inputs,
    }

    if not reused_activation:
        # The root is authored only alongside a NEW activation. A reused
        # activation already has one, resolved above.
        plan.create(files_dir / f"{root_uid}.md",
                    _ig.render_activation_root(root_uid, activation_uid, dev_spec_uid,
                                               "dev-spec", locked_by, today,
                                               DEFAULT_PIPELINE_UID),
                    governed=True)
        plan.create(files_dir / f"{activation_uid}.md",
                    _ig.render_activation(
                        activation_uid, root_uid, run_uid, DEFAULT_PIPELINE_UID,
                        dev_spec_uid, "dev-spec", locked_by, today, cycle_context),
                    governed=True)

    plan.create(runs / run_name / "declaration-snapshot.json",
                _json.dumps(dict(snapshot.as_dict(), **inputs),
                            indent=2, sort_keys=True) + "\n")
    plan.create(
        runs / run_name / "run.jsonl",
        render_lock_run_created(
            run_uid=run_uid,
            activation_uid=activation_uid,
            root_uid=root_uid,
            dev_spec_uid=dev_spec_uid,
            pipeline_uid=DEFAULT_PIPELINE_UID,
            pipeline_version=snapshot.pipeline_version,
            actor=locked_by,
        ),
    )
    plan.create(files_dir / f"{run_uid}.md", "---\n" + "\n".join([
        f"uid: {run_uid}", "type: pipeline-run",
        f'title: "Dev run {run_name}"',
        f'description: "Immutable dev run opened by the lock of dev-spec {dev_spec_uid}."',
        "status: active", "state: active", f"owner: {locked_by}",
        f"pipeline: {DEFAULT_PIPELINE_UID}",
        f"pipeline_version: '{snapshot.pipeline_version}'",
        f"activation: '{activation_uid}'",
        # The engine correlates runs to activations through THIS field
        # (find_pipeline_run_for). Without it the run the lock creates is
        # invisible to the runtime, which then behaves as though no run exists.
        f"substrate_authored_by: '{activation_uid}'",
        f"activation_root_uid: '{root_uid}'",
        f"dev_spec_uid: '{dev_spec_uid}'",
        f"declaration_digest: '{snapshot.digest}'",
        f"dev_spec_sha256: '{inputs['dev_spec_sha256']}'",
        f"run_folder: 'vault/pipeline-runs/{run_name}'",
        f"created: '{today}'", f"modified: '{today}'", f"created_by: {locked_by}",
        "schema_version: 2", "governed_by: 8dd772a0",
    ]) + "\n---\n\n# " + run_name + "\n", governed=True)

    return plan


def _read_entry_frontmatter(uid: str, files_dir: Path) -> Optional[dict]:
    path = files_dir / f"{uid}.md"
    if not path.is_file():
        return None
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def _resolve_existing_root(activation_uid: str, activation_fm: Optional[dict],
                           files_dir: Path) -> str:
    """The root a reused activation ALREADY has, or a refusal naming why not.

    Three ways this can fail, and they are different problems (argus-a147
    residual 1):

      missing    the activation names no root, or names one that does not
                 resolve — its identity is incomplete and minting a fresh root
                 would paper over that rather than fix it
      ambiguous  the activation names one root while another project claims the
                 same activation; two records disagree about one identity
      multiple   several projects claim this activation

    Fail-closed, harm named (deb77758): a cycle with two roots has two things to
    archive at close and two places to stamp final_commit, so its completion
    record is unreconstructable afterwards — the identity class deb77758 lists.
    """
    from lib import ignition as _ig

    named = (activation_fm or {}).get("activation_root_project")
    claimants = []
    for path in sorted(files_dir.glob("*.md")):
        fm = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if fm.get("type") == "project" and fm.get("activation_uid") == activation_uid:
            claimants.append(path.stem)

    if named and not (files_dir / f"{named}.md").is_file():
        raise _ig.IgnitionRefusal(
            f"activation {activation_uid} names root {named}, which does not "
            "resolve. Minting a replacement would leave the activation pointing "
            "at nothing while a new root claimed the cycle."
        )
    if len(claimants) > 1:
        raise _ig.IgnitionRefusal(
            f"activation {activation_uid} is claimed by {len(claimants)} roots "
            f"({', '.join(claimants)}). One cycle cannot have two roots to "
            "archive at close."
        )
    if named and claimants and named not in claimants:
        raise _ig.IgnitionRefusal(
            f"activation {activation_uid} names root {named} but root "
            f"{claimants[0]} claims the activation. Two records disagree about "
            "one identity; resolve it before locking."
        )
    resolved = named or (claimants[0] if claimants else None)
    if not resolved:
        raise _ig.IgnitionRefusal(
            f"activation {activation_uid} exists but names no activation root. "
            "Its identity is incomplete, and minting a fresh root here would "
            "hide that rather than repair it."
        )
    return str(resolved)


def _resolve_step_uids(root_uid: str, files_dir: Path) -> list:
    """Leaf step UIDs under a pipeline root, read from disk.

    From disk rather than the index: the run's snapshot must describe the
    definition as it stands at ignition, and the index is per-machine derived
    state that may not have been rebuilt.
    """
    seen: list = []
    stack = [root_uid]
    visited = set()
    while stack:
        uid = stack.pop(0)
        if uid in visited:
            continue
        visited.add(uid)
        path = files_dir / f"{uid}.md"
        if not path.is_file():
            continue
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        children = [str(c) for c in (fm.get("children") or [])
                    if re.fullmatch(r"[0-9a-f]{8}", str(c))]
        if uid != root_uid and not children:
            seen.append(uid)
        stack.extend(children)
    return seen


def _mint_uid(files_dir: Path, exclude=frozenset()) -> str:
    import uuid

    taken = {p.stem for p in files_dir.glob("*.md")} | set(exclude)
    while True:
        candidate = uuid.uuid4().hex[:8]
        if candidate not in taken:
            return candidate


def lock_dev_spec(dev_spec_uid: str, locked_by: str, pipeline_uid: str = DEFAULT_PIPELINE_UID,
                   cycle_context: str = "", files_dir: Path = VAULT_FILES,
                   vault_root: Path = VAULT_ROOT,
                   activate_script: Path = PIPELINE_ACTIVATE_SCRIPT) -> tuple[int, str]:
    """Core atomic gesture, factored out of main() so tests can call it
    directly against an isolated fixture vault. Returns (exit_code, message)."""
    dev_spec_uid = dev_spec_uid.strip()
    if not re.fullmatch(r"[0-9a-f]{8}", dev_spec_uid):
        return 3, f"ERROR: --dev-spec-uid must be 8-hex; got: {dev_spec_uid!r}"

    dev_spec_path = files_dir / f"{dev_spec_uid}.md"
    if not dev_spec_path.is_file():
        return 1, f"ERROR: dev-spec {dev_spec_uid!r} does not resolve at {dev_spec_path}"

    raw = dev_spec_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(raw)
    if fm.get("type") != "dev-spec":
        return 1, f"ERROR: {dev_spec_uid!r} is not type:dev-spec (got type:{fm.get('type')!r})"

    current_status = fm.get("status")
    if current_status == "locked":
        return 1, (f"ERROR: dev-spec {dev_spec_uid!r} is already status:locked — refusing to "
                    f"re-lock (this gesture locks once; supersession is a separate governed act)")
    if current_status not in LOCKABLE_STATUSES:
        return 1, (f"ERROR: dev-spec {dev_spec_uid!r} is status:{current_status!r}, not in a "
                    f"lockable state ({sorted(LOCKABLE_STATUSES)}) — refusing to lock")

    # --- The atomic gesture (ADR-052: "as one indivisible act") ---
    #
    # REFACTORED 2026-08-10 for argus-a147 stage-4 blocker 1. This used to shell
    # out to pipeline-activate.py BEFORE taking the lock, then build a snapshot
    # transaction afterwards. Two defects fell out of that split, and both are
    # the kind that only appear on the paths nobody tests:
    #
    #   the subprocess wrote immediately and outside the journal, so a refusal
    #   after it succeeded left an activation and a root on disk with nothing
    #   describing them
    #
    #   pipeline-activate authors its own `activation_root_project` and the
    #   ignition authored another, so a SUCCESSFUL lock produced one activation
    #   and TWO roots
    #
    # A subprocess cannot join a transaction. Everything the gesture writes —
    # activation, root, run, run folder, and the spec flip — is now one plan,
    # built and applied inside one lock span.
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lib import ignition as _ig, lock_transaction as _lt

    today = time.strftime("%Y-%m-%d")

    # The plan is built INSIDE the span, not before it. It was outside until the
    # lock token was added, and the token caught it immediately: a plan carries
    # the acquisition its reads were taken under, and one built beforehand
    # carries none. That is not a technicality — the plan reads the pipeline
    # definition and the dev-spec, and doing so outside the lock means planning
    # against a world another ignition can still be changing.
    try:
        with _lt.exclusive_workspace_lock():
            # Recovery inside the span and before anything else, symmetric with
            # the release ignition: a crashed prior attempt must be resolved
            # before this one plans against what it left behind.
            for report in _lt.recover_incomplete():
                print(f"[RECOVERY] {report['journal']}: {report['outcome']}",
                      file=sys.stderr)
                if report["outcome"] == "needs-operator":
                    return 2, (
                        f"REFUSED: an earlier transaction at {report['journal']} "
                        "cannot be recovered automatically. Resolve it before "
                        "locking.")

            plan = plan_dev_snapshot_transaction(
                dev_spec_uid, locked_by, files_dir=files_dir,
                cycle_context=cycle_context)
            # The spec flip is the LAST operation in the plan and part of it, so
            # a failure anywhere leaves the spec exactly as found.
            plan.patch(
                dev_spec_path, raw,
                flip_dev_spec_to_locked(raw, locked_by, today,
                                        plan.notes["activation_uid"]))

            if _lt.already_applied("dev-spec-lock", dev_spec_uid, plan):
                return 0, f"{dev_spec_uid} already locked by this exact plan (idempotent retry)"
            _lt.apply_plan(plan)
    except _ig.IgnitionRefusal as exc:
        return 1, (f"ERROR: cannot open the dev snapshot transaction for "
                   f"{dev_spec_uid!r}: {exc}. ABORTING THE LOCK — the dev-spec is "
                   "UNCHANGED. A lock that flips status without writing the run's "
                   "immutable snapshot leaves a cycle executing a contract it never "
                   "recorded.")
    except _lt.LockRefusal as exc:
        return 1, f"REFUSED: {exc}"
    except _lt.LockApplyFailure as exc:
        return 2, f"PARTIAL: {exc}"

    tag = "pre-existing, reused" if plan.notes["activation_reused"] else "new"
    return 0, (f"{dev_spec_uid} LOCKED activation={plan.notes['activation_uid']} "
               f"({tag}) root={plan.notes['activation_root_uid']} "
               f"run={plan.notes['run_uid']} "
               f"declarations={plan.notes['declaration_digest'][:12]} "
               f"version={plan.notes['pipeline_version']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Atomic dev-spec lock + pipeline-activation registration (ADR-052 ee0e35ad)."
    )
    parser.add_argument("--dev-spec-uid", required=True, help="8-hex UID of the dev-spec to lock")
    parser.add_argument("--locked-by", required=True, help="Principal locking (agent slug or entity UID)")
    parser.add_argument("--pipeline-uid", default=DEFAULT_PIPELINE_UID,
                         help=f"dev-pipeline template UID to activate against (default: {DEFAULT_PIPELINE_UID})")
    parser.add_argument("--cycle-context", default="", help="Optional human-readable cycle/run context")
    args = parser.parse_args()

    exit_code, message = lock_dev_spec(
        args.dev_spec_uid, args.locked_by,
        pipeline_uid=args.pipeline_uid, cycle_context=args.cycle_context,
    )
    stream = sys.stdout if exit_code == 0 else sys.stderr
    print(message, file=stream)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
