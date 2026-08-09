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
    existing = find_correlated_activation(dev_spec_uid, files_dir=files_dir)
    opened_new = False
    if existing is not None:
        activation_uid = existing.get("uid")
    else:
        ctx = cycle_context or f"lock-dev-spec.py atomic lock-time activation for {dev_spec_uid}"
        returncode, stdout, stderr = open_activation(
            pipeline_uid, locked_by, ctx, dev_spec_uid,
            vault_root=vault_root, activate_script=activate_script,
        )
        if returncode != 0:
            return 1, (f"ERROR: pipeline-activate.py refused to open an activation for dev-spec "
                        f"{dev_spec_uid!r} (exit={returncode}). ABORTING THE LOCK — the dev-spec's "
                        f"status is UNCHANGED (atomic: no activation means no lock).\n"
                        f"--- pipeline-activate.py stderr ---\n{stderr}")
        opened_new = True
        # Re-scan is authoritative: confirms the activation is really on disk
        # and correlated, rather than trusting stdout parsing alone.
        fresh = find_correlated_activation(dev_spec_uid, files_dir=files_dir)
        if fresh is None:
            return 2, (f"FATAL: pipeline-activate.py exited 0 but no correlated activation is "
                        f"found on disk for {dev_spec_uid!r} — ABORTING THE LOCK (atomicity guard "
                        f"tripped; investigate e337f1dd.py before retrying). stdout was: {stdout!r}")
        activation_uid = fresh.get("uid")

    # Only reached with a real, on-disk, correlated activation in hand.
    today = time.strftime("%Y-%m-%d")
    new_text = flip_dev_spec_to_locked(raw, locked_by, today, activation_uid)
    dev_spec_path.write_text(new_text, encoding="utf-8")

    tag = "new" if opened_new else "pre-existing, reused"
    return 0, f"{dev_spec_uid} LOCKED activation={activation_uid} ({tag})"


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
