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
modified: '2026-08-24'
modified_by: talos-t50
governed_by: d5e1b4a3
member_of:
  - "8dd772a0"
schema_version: 2
belt: false  # trimmed from belt by vela-v65 2026-07-10 — over the 15-entry cap; mount/publish are federation-specific, lock-dev-spec is ceremony-specific. Cataloged + functional; not in quick-ref.
extraction_scope: ship  # v1.92 Stream 2 AC1 (1a478c48), 2026-08-24 by talos-t50: the dev-pipeline's only ignition was argo-reference — a stranger studio received a pipeline it could not start. Flipped alongside b281edeb (the lib/ closure) and confirmed clean of absolute paths / argo-private UID references (see 5187be30's fix, same build).
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

Since 308bb12e (v1.94): the same transaction stamps the dev-spec's paired
test-specs. Every uid in the dev-spec's `triggered_test_spec_uids` gets
`triggered_by_dev_cycle: <activation-uid>` written into its frontmatter, in the
same all-or-none plan as the spec flip (which stays the LAST operation). The
field has five production readers — 9e7003b1's evidence discovery (:4989),
post-test evidence gate (:5269) and closure refusal (:5052) among them — and,
until this, zero producers: every pre-lock test-spec failed those gates by
construction and the release procedure carried an interim hand
lock-then-stamp step (Metis-adopted 2026-08-31). A named pair that does not
resolve on disk, is not type:test-spec, or already carries a DIFFERENT cycle's
uid refuses the whole lock before anything is applied — the refusals name
their harms; the no-pairs dev-spec locks clean and stamps nothing.

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
    dev_spec_uid: str = "",
    pipeline_uid: str,
    pipeline_version: str,
    actor: str,
    timestamp: Optional[str] = None,
    backfilled_by: Optional[str] = None,
    subject_kind: str = "dev-spec",
    subject_uid: str = "",
    extra: Optional[dict] = None,
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
    # v1.89 2fae6312: one seed renderer for every pipeline. The subject is a
    # dev-spec for a dev cycle and a release-plan for a release; keying the seed
    # on dev_spec_uid alone made a release seed unrecognisable to the very
    # runtime its lock had just opened. dev_spec_uid stays populated for the dev
    # dialect so historical readers and existing runs are unaffected.
    resolved_subject = subject_uid or dev_spec_uid
    data = {
        "pipeline": pipeline_uid,
        "pipeline_uid": pipeline_uid,
        "pipeline_version": pipeline_version,
        "pipeline_run_uid": run_uid,
        "subject_kind": subject_kind,
        "subject_uid": resolved_subject,
        "activation_uid": activation_uid,
        "activation_root_uid": root_uid,
        "members": [root_uid],
        "authorized_by": actor,
        "bootstrap_pending": True,
    }
    if subject_kind == "dev-spec":
        data["dev_spec_uid"] = dev_spec_uid or resolved_subject
    if extra:
        data.update(extra)
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
    entry_path = _governed_path(files_dir, run_uid)
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


#: v1.95, task f01592dca86d (found by metis-g118 counting the v1.94 fan-in).
#: The release plan 301dce9d carried `dev_spec_uids: []   # fills at spec-lock`
#: and FOURTEEN specs locked against it while the list stayed empty, because
#: this tool contained no reference to the field. tropo-lock-release-plan.py
#: refuses an empty list by design, so the plan could not have locked at any
#: count of done rows; the plan owner populated all fourteen by hand.
#:
#: BLOCK-AWARE ON PURPOSE (the plan-lock's own NO-GO item 5): a naive `^key:`
#: match on a block value produced two `dev_spec_uids:` keys and YAML silently
#: kept the last.
_PLAN_LIST_KEY = "dev_spec_uids"
#: The plan statuses the lock may append to (A172 condition 3, 2026-09-06): a
#: locked or terminal plan gets the WARN, never a write — its member list is
#: either sealed under a digest or describes a release that already happened.
PLAN_APPENDABLE_STATUSES = frozenset({"design", "specify", "active"})


def append_uid_to_plan_list(plan_text: str, uid: str) -> tuple:
    """Append `uid` to the plan's dev_spec_uids. Returns (text, changed).

    Handles the three shapes a plan actually carries:
      * `dev_spec_uids: []` inline-empty, with or without a trailing comment
        (the shape v1.94 had) -> becomes a block list, comment preserved;
      * `dev_spec_uids:` followed by `  - <uid>` entries -> appended after the
        last entry, order preserved;
      * `dev_spec_uids:` bare with no entries -> becomes the first entry.

    Idempotent: a uid already present returns the text unchanged. Never writes a
    second key.
    """
    lines = plan_text.splitlines(keepends=True)
    key_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^%s\s*:" % re.escape(_PLAN_LIST_KEY), line):
            if key_idx is not None:
                raise ValueError(
                    "plan carries two %s keys — refusing to guess which is live"
                    % _PLAN_LIST_KEY)
            key_idx = i
    if key_idx is None:
        return plan_text, False

    head, _, rest = lines[key_idx].partition(":")
    value, hashmark, comment = rest.partition("#")
    inline = value.strip()

    # Walk the block entries that follow.
    # Entries carry TRAILING COMMENTS in the real plan
    # (`  - f015de6b3a18   # Spine A, identity and arrival`). My first pattern
    # required the line to end at the uid, matched none of them, and so both
    # appended a DUPLICATE of a uid already present and inserted the new one
    # FIRST instead of last. The synthetic fixture was self-consistent and the
    # world was not; the round-trip against the live plan is what said so.
    # `-\s+`, not `-\s*`: a YAML list entry has whitespace after the dash, and
    # the frontmatter closer `---` has none. With `\s*` the closer matched as an
    # entry named "--", so a plan whose member list was the LAST key had its new
    # uid inserted after `---`, into the body, while YAML read the list as null
    # and the plan lock still refused "lists no dev_spec_uids". Every fixture
    # had a key after the list; the AC4 fixture did not (T63, f01592dca86d).
    entry_re = re.compile(r"^\s*-\s+['\"]?([A-Za-z0-9_.-]+)['\"]?\s*(?:#.*)?$")
    last = key_idx
    existing = []
    for j in range(key_idx + 1, len(lines)):
        if lines[j].rstrip("\r\n") == "---":
            break  # the frontmatter closer, never an entry
        m = entry_re.match(lines[j])
        if m:
            existing.append(m.group(1))
            last = j
            continue
        if lines[j].strip() == "" or lines[j].lstrip().startswith("#"):
            continue
        break

    if inline and inline not in ("[]", "[ ]"):
        # an inline NON-empty list: out of scope, and guessing would corrupt it
        raise ValueError("plan carries an inline %s list; append not supported"
                         % _PLAN_LIST_KEY)
    if uid in existing:
        return plan_text, False

    entry = "  - %s\n" % uid
    if inline in ("[]", "[ ]"):
        # Replace the inline empty with a bare key, KEEPING the comment: it is
        # the plan owner's note about the field and dropping it silently would
        # lose the only place the convention was written down.
        tail = ("   #" + comment.rstrip("\n")) if hashmark else ""
        lines[key_idx] = "%s:%s\n" % (head, tail)
    lines.insert(last + 1, entry)
    return "".join(lines), True


def scan_release_plans(files_dir: Path) -> list:
    """Every release-plan under files_dir as (path, frontmatter), one pass.

    The resolver below takes this list so a caller checking MANY specs (the
    validator's drift check, f01592dca86d AC5) scans the vault once instead of
    once per spec — 100 specs against 6,000 files was a five-minute check.
    """
    plans = []
    for path in sorted(files_dir.glob("*.md")):
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        if fm.get("type") == "release-plan":
            plans.append((path, fm))
    return plans


def resolve_plan_for_spec(spec_fm: dict, files_dir: Path, plans=None) -> tuple:
    """(plan_path, why) for the release plan this spec belongs to.

    THE BINDING, said explicitly because the task asked which one is used: a
    dev-spec carries no pointer to its plan. `member_of` on both is the
    dev-pipeline template, not the plan. What actually binds them is the spec's
    `target_release` against the plan's `release_version`.

    Exactly one live candidate is required. Zero -> nothing to append to, which
    is normal for a spec locked outside a release cycle. More than one -> this
    refuses rather than guessing which plan a spec belongs to.
    """
    target = str(spec_fm.get("target_release") or "").strip()
    if not target:
        return None, "spec declares no target_release"
    terminal = {"done", "closed", "cancelled", "archived", "superseded"}
    hits = []
    if plans is None:
        plans = scan_release_plans(files_dir)
    for path, fm in plans:
        if str(fm.get("release_version") or "").strip() != target:
            continue
        if str(fm.get("status") or "").strip().lower() in terminal:
            continue
        hits.append(path)
    if not hits:
        return None, "no live release-plan declares release_version %r" % target
    if len(hits) > 1:
        return None, ("%d live release-plans declare release_version %r: %s — "
                      "refusing to guess" % (len(hits), target,
                                             ", ".join(q.name for q in hits)))
    return hits[0], ""


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


def stamp_pair_with_activation(raw_text: str, activation_uid: str) -> str:
    """Surgical frontmatter patch for a paired test-spec (308bb12e): write
    `triggered_by_dev_cycle: <activation-uid>` — the exact scalar the runtime's
    evidence-discovery and post-test gates string-match (9e7003b1 :4989/:5269;
    the closure refusal at :5052 names this field as the cure verbatim). Same
    discipline as flip_dev_spec_to_locked: line-level replace-or-append, never
    a YAML round-trip that could reformat a hand-authored pair."""
    if not raw_text.startswith("---\n"):
        raise ValueError("paired test-spec has no opening frontmatter fence")
    end = raw_text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("paired test-spec frontmatter is not closed")
    fm_block = raw_text[4:end]
    rest = raw_text[end + 5:]

    out_lines = []
    replaced = False
    for line in fm_block.split("\n"):
        if re.match(r"^triggered_by_dev_cycle:\s*", line):
            out_lines.append(f"triggered_by_dev_cycle: {activation_uid}")
            replaced = True
        else:
            out_lines.append(line)
    if not replaced:
        out_lines.append(f"triggered_by_dev_cycle: {activation_uid}")

    new_fm_block = "\n".join(out_lines)
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



def refuse_on_own_findings(dev_spec_uid: str, inputs: dict) -> None:
    """S4 AC8 (29506520) — refuse on a precondition this gesture itself recorded.

    Extracted from inline so the contract is RUNNABLE. AC8's locked verify command
    names test_lock_refuses_on_own_findings_v191.py, and an inline guard inside a
    transaction that mints UIDs and opens activations cannot be exercised by a test
    without standing up that whole world. A refusal nobody can run is the exact
    defect this spec is about (argus-a154, 2026-08-23).

    Raises SystemExit when acceptance_criteria_present is False. Warns and returns
    when committed_substrate_present is False. The asymmetry is named to its harm
    per deb77758: a lock with no criteria the machine can find is a close nobody can
    judge; a spec is locked BEFORE it is built, so an empty substrate at lock time is
    usually the honest state and refusing it would be a gate wider than its harm.
    """
    if inputs.get("acceptance_criteria_present") is False:
        raise SystemExit(
            f"REFUSED: {dev_spec_uid} declares no `acceptance_criteria:` in its "
            f"frontmatter, and this gesture was about to record that fact and lock "
            f"anyway.\n"
            f"  A lock with no criteria the machine can find is a close nobody can "
            f"judge.\n"
            f"  If the criteria are written in the BODY, move them to frontmatter — "
            f"that is where every reader looks.\n"
            f"  (S4 AC8, 29506520. This refusal names one harm and covers only it; "
            f"an absent committed_substrate warns and proceeds.)")
    if inputs.get("committed_substrate_present") is False:
        print(f"[WARN] {dev_spec_uid} declares no `committed_substrate:` at lock time. "
              f"Locking proceeds — a spec is locked before it is built, so this is often "
              f"the honest state. The snapshot records it either way.", file=sys.stderr)



def _is_governed_uid_shape(uid: str) -> bool:
    """The shape authority, imported rather than re-derived. Same self-sufficient
    path insert as _governed_path below, for the same reason."""
    import sys as _s
    _here = str(Path(__file__).resolve().parent)
    if _here not in _s.path:
        _s.path.insert(0, _here)
    from lib.governed_path import is_governed_uid_shape as _igus
    return _igus(uid)


def _governed_path(files_dir: Path, uid: str) -> Path:
    """Bare name first, then the slug-anchored resolver.

    THE SAME SEAM THE PAIRED-TEST-SPEC PATH ALREADY HANDLES ~370 lines below, and
    it was handled there and not here: the dev-spec's OWN path was built bare, so
    once readable filenames flipped on, a slug-named dev-spec could not be locked
    at all. Its refusal read "does not resolve", which sounds like a missing spec
    rather than a naming seam, and B-7's own dev-spec was in exactly that state.

    Bare-first keeps the legacy corpus on the fast path and costs a scan only when
    the bare name misses. (argus-a165, 2026-09-01.)
    """
    bare = files_dir / f"{uid}.md"
    if bare.is_file():
        return bare
    # Insert our own tools dir rather than depending on a caller having done it.
    # This module inserts sys.path lazily INSIDE several functions, so a helper
    # that assumed the path was already set would resolve correctly only when
    # called after one of them -- a correctness that depends on call ORDER.
    import sys as _s
    _here = str(Path(__file__).resolve().parent)
    if _here not in _s.path:
        _s.path.insert(0, _here)
    try:
        from lib.governed_path import resolve_governed_path as _rgp
    except ImportError as exc:  # the authority is unreachable: SAY SO, never skip
        raise RuntimeError(
            "cannot resolve a slug-named governed file: lib.governed_path is "
            "unimportable (%s). Refusing to fall back to the bare name, because "
            "that returns 'does not resolve' for a file that is present and "
            "reads as a missing spec." % exc
        ) from exc
    resolved = _rgp(uid, files_dir.parent.parent)
    return Path(resolved) if resolved is not None else bare


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
    spec_path = _governed_path(files_dir, dev_spec_uid)

    def _read(uid):
        path = _governed_path(files_dir, uid)
        if not path.is_file():
            return None
        return {"frontmatter": parse_frontmatter(path.read_text(encoding="utf-8"))}

    def _entry_bytes(uid):
        path = _governed_path(files_dir, uid)
        return path.read_bytes() if path.is_file() else None

    snapshot = _ig.snapshot_declarations(
        DEFAULT_PIPELINE_UID, _read,
        lambda uid: _resolve_step_uids(uid, files_dir),
        read_bytes=_entry_bytes)

    # The whole-file pin is GONE (f01519144119 step 2, talos-t63 2026-09-06,
    # Mike's word). `input_snapshot([("dev_spec", spec_path)])` hashed the file
    # BEFORE this same gesture rewrote it (status flip, activation stamp), so
    # `dev_spec_sha256` never matched the locked file of any run and nothing
    # read it. The two component digests below carry the meaning the pin could
    # not: WHAT moved, and the close compares them (tropo-close-dev.py).
    # The refusal the dropped call carried, kept explicitly: a run cannot record
    # digests of a spec that is not there (S4 AC8 shape -- a gesture that finds
    # a missing precondition refuses on it).
    if not spec_path.is_file():
        raise _ig.IgnitionRefusal(
            f"ignition input dev_spec does not resolve at {spec_path}; a run cannot "
            "record the digests of something that is not there")
    inputs = {}
    inputs.update(_ig.spec_component_digests(spec_path.read_text(encoding="utf-8")))

    # S4 AC8 (29506520), argus-a154 2026-08-23 — A GESTURE THAT RECORDS A MISSING
    # PRECONDITION MUST REFUSE ON IT.
    #
    # This gesture pinned acceptance_criteria_present=false into the declaration
    # snapshot of all three v1.91 specs and locked them anyway. It was never blind:
    # it looked, wrote down that the criteria were absent, and proceeded. Root cause
    # measured the same day — the four specs carried 6-7 acceptance criteria in the
    # BODY and zero in frontmatter, while this gesture reads frontmatter. The
    # convention moved and the gesture did not.
    #
    # THE ASYMMETRY IS DELIBERATE, per deb77758 (a refusal earns its existence by
    # naming its irreversible harm, or it is a warning that proceeds and records):
    #   acceptance_criteria absent -> REFUSE. A lock with no criteria the machine can
    #       find is a close nobody can judge; the run's own verdict becomes unfalsifiable.
    #   committed_substrate absent -> WARN. A dev-spec is locked BEFORE it is built, so
    #       an empty substrate at lock time is often the honest state, not a defect.
    #       Refusing it would be a gate wider than its harm — the exact class this
    #       whole cycle exists to remove.
    refuse_on_own_findings(dev_spec_uid, inputs)

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
        # the two digests the close compares; the whole-file pin they replace
        # never matched the locked file (f01519144119)
        f"acceptance_criteria_sha256: '{inputs.get('acceptance_criteria_sha256', '')}'",
        f"committed_substrate_sha256: '{inputs.get('committed_substrate_sha256', '')}'",
        f"run_folder: 'vault/pipeline-runs/{run_name}'",
        f"created: '{today}'", f"modified: '{today}'", f"created_by: {locked_by}",
        "schema_version: 2", "governed_by: 8dd772a0",
    ]) + "\n---\n\n# " + run_name + "\n", governed=True)

    return plan


def _read_entry_frontmatter(uid: str, files_dir: Path) -> Optional[dict]:
    path = _governed_path(files_dir, uid)
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

    if named and not _governed_path(files_dir, named).is_file():
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
        path = _governed_path(files_dir, uid)
        if not path.is_file():
            continue
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        children = [str(c) for c in (fm.get("children") or [])
                    if re.fullmatch(r"[0-9a-f]{8}(?:[0-9a-f]{4})?", str(c))]  # accepts-both
        if uid != root_uid and not children:
            seen.append(uid)
        stack.extend(children)
    return seen


_MINT_TOOL_MODULE = None


def _mint_tool():
    """Load tropo-mint-id.py lazily (its filename is not importable) for the
    studio-identity manifest read composite minting requires."""
    global _MINT_TOOL_MODULE
    if _MINT_TOOL_MODULE is None:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "mint_id_module_for_lock", Path(__file__).resolve().parent / "tropo-mint-id.py")
        _MINT_TOOL_MODULE = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_MINT_TOOL_MODULE)
    return _MINT_TOOL_MODULE


def _mint_uid(files_dir: Path, exclude=frozenset()) -> str:
    """Route through the AUTHORITY mint shape (3d430852): composite when the
    generation constant says 12, reading the studio-identity manifest
    (refuse-if-absent — a studio never self-assigns a prefix); the legacy
    flat 8-hex before that. The uuid4 literal this replaced was the one mint
    site the flip census missed; the isolation suite's SUBSTRATE extractor
    caught it live on the flip's first run."""
    import sys as _sys
    import uuid
    _here = Path(__file__).resolve().parent
    if str(_here) not in _sys.path:
        _sys.path.insert(0, str(_here))
    from lib import governed_path as _gp
    taken = {p.stem for p in files_dir.glob("*.md")} | set(exclude)
    if _gp.MINT_HEX_LEN == 12:
        _mintmod = _mint_tool()
        identity = _mintmod.read_studio_identity(root=files_dir.parent.parent)
        prefix = str(identity["mint_prefix"])
        if not _gp.is_composite_mint_prefix(prefix):
            raise _mintmod.StudioIdentityError(
                f"studio-identity manifest mint_prefix {prefix!r} is not the "
                "4-hex composite shape — the lock cannot mint composite "
                "activation identities against it; re-issue per 3d430852")
        while True:
            candidate = _gp.composite_uid(prefix)
            if candidate not in taken:
                return candidate
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
    if not _is_governed_uid_shape(dev_spec_uid):  # the authority, not a local literal
        return 3, f"ERROR: --dev-spec-uid must be a governed uid (legacy 8-hex or composite 12-hex); got: {dev_spec_uid!r}"

    # THE LOCKER RESOLVES TOO. The planner beside it was cured first and this was
    # not, so main() -> lock_dev_spec() refused before the cured code was ever
    # reached: a bare-path fix that left a bare path one function over. Caught by
    # metis-g115 on the diff, reproduced against B-7's real slug-named spec.
    dev_spec_path = _governed_path(files_dir, dev_spec_uid)
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
            # 308bb12e — stamp the paired test-specs INSIDE the same plan.
            # Refusals fire before apply_plan is ever reached, so a refused
            # lock leaves the spec, the pairs, and any authored activation
            # exactly as found: nothing has been written yet.
            pair_uids = fm.get("triggered_test_spec_uids") or []
            if isinstance(pair_uids, str):
                pair_uids = [pair_uids]
            pairs_stamped = 0
            for pair_uid in pair_uids:
                pair_uid = str(pair_uid).strip()
                # Slug-anchored resolution (Metis's W7-gate finding, 2026-08-31):
                # post-D7 readable-named pairs are <slug>-<uid>.md, and a bare
                # construction here refused them as "does not resolve" — the
                # only thing standing between the merge seam and a lock. Bare
                # fast path, then the authority's resolver, honest bare
                # fallback for the not-found message.
                bare_pair = files_dir / f"{pair_uid}.md"
                pair_path = bare_pair
                if not pair_path.is_file():
                    try:
                        from lib.governed_path import resolve_governed_path as _rgp
                        _resolved = _rgp(pair_uid, files_dir.parent.parent)
                    except Exception:
                        _resolved = None
                    if _resolved is not None:
                        pair_path = Path(_resolved)
                if not pair_path.is_file():
                    return 1, (f"ERROR: paired test-spec {pair_uid!r} named by "
                               f"{dev_spec_uid!r} does not resolve — the bare name "
                               f"and the slug-anchored resolver were both searched "
                               f"under {files_dir}. "
                               "REFUSING THE LOCK — locking anyway would leave the "
                               "pair unstamped and hand the release procedure back "
                               "the hand step this gesture exists to kill.")
                pair_raw = pair_path.read_text(encoding="utf-8")
                pair_fm = parse_frontmatter(pair_raw)
                if pair_fm.get("type") != "test-spec":
                    return 1, (f"ERROR: paired entry {pair_uid!r} is "
                               f"type:{pair_fm.get('type')!r}, not test-spec. "
                               "REFUSING THE LOCK — writing dev-cycle provenance "
                               "onto a non-test entry pollutes it.")
                existing_stamp = str(pair_fm.get("triggered_by_dev_cycle") or "").strip()
                if existing_stamp and existing_stamp != plan.notes["activation_uid"]:
                    return 1, (f"ERROR: paired test-spec {pair_uid!r} already carries "
                               f"triggered_by_dev_cycle: {existing_stamp!r}, not this "
                               f"cycle's {plan.notes['activation_uid']!r}. REFUSING "
                               "THE LOCK — overwriting would destroy the pair's "
                               "binding to its actual cycle.")
                if existing_stamp == plan.notes["activation_uid"]:
                    # Reuse path: the pair is already bound to this cycle (e.g.
                    # a retroactive cure correlated the activation). Binding it
                    # twice is the duplication this gesture refuses elsewhere.
                    pairs_stamped += 1
                    continue
                plan.patch(pair_path, pair_raw,
                           stamp_pair_with_activation(
                               pair_raw, plan.notes["activation_uid"]))
                pairs_stamped += 1
            # The spec flip is the LAST operation in the plan and part of it, so
            # a failure anywhere leaves the spec exactly as found.
            plan.patch(
                dev_spec_path, raw,
                flip_dev_spec_to_locked(raw, locked_by, today,
                                        plan.notes["activation_uid"]))

            # f01592dca86d — THE CALL SITE. AC1 ("the lock appends") was
            # accepted on the functions and the world probe while nothing
            # called them; A172 ruled (a) on 2026-09-06: wire it
            # unconditionally, warn-safe, in the same transaction as the spec
            # flip and the activation mint. A resolve failure (no live plan, or
            # more than one) prints ONE WARN quoting the resolver's reason and
            # the lock proceeds with the plan untouched. No opt-out flag: that
            # is a skip list, and a skip list is how the last plan lock refused
            # an empty list. The plan write is a plan.patch like the spec's —
            # never a bare open().write — so it lands, journals and unwinds
            # with everything else in this gesture.
            plan.notes["release_plan_appended"] = None
            plan_path, why = resolve_plan_for_spec(fm, files_dir)
            if plan_path is None:
                print(f"  [WARN] release-plan append skipped for {dev_spec_uid}: {why}. "
                      "The lock proceeds; no plan's dev_spec_uids changed.",
                      file=sys.stderr)
            else:
                plan_raw = plan_path.read_text(encoding="utf-8")
                plan_fm = parse_frontmatter(plan_raw)
                plan_uid = str(plan_fm.get("uid") or plan_path.stem)
                plan_status = str(plan_fm.get("status") or "").strip().lower()
                if plan_status not in PLAN_APPENDABLE_STATUSES:
                    print(f"  [WARN] release-plan {plan_uid} is status {plan_status!r}, not a "
                          f"pre-lock state ({sorted(PLAN_APPENDABLE_STATUSES)}); "
                          f"{dev_spec_uid} was NOT appended to its dev_spec_uids. "
                          "The lock proceeds.", file=sys.stderr)
                else:
                    try:
                        plan_text, plan_changed = append_uid_to_plan_list(plan_raw, dev_spec_uid)
                    except ValueError as exc:
                        print(f"  [WARN] release-plan {plan_uid}: {exc}; {dev_spec_uid} was NOT "
                              "appended. The lock proceeds.", file=sys.stderr)
                    else:
                        if plan_changed:
                            plan.patch(plan_path, plan_raw, plan_text)
                        plan.notes["release_plan_appended"] = plan_uid

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
               f"pairs={pairs_stamped} "
               f"plan={plan.notes.get('release_plan_appended') or 'none'} "
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
