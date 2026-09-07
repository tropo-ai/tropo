#!/usr/bin/env python3
"""---
uid: 6a41f0c9
type: tool
name: tropo-lock-release-plan
title: tropo-lock-release-plan.py — the release ignition
status: active
owner: talos
extraction_scope: ship
schema_version: 2
modified: '2026-08-16'
modified_by: talos-t44
scope_ruling_note: 'extraction_scope declared 2026-08-16 per A150 ruling: the release orchestrator, preflight and lock-release-plan are product surfaces and ship. This tool had carried no frontmatter at all, which is why it sat outside the ship census while its siblings disagreed with each other.'
---

tropo-lock-release-plan.py — the release ignition (0a0a6777 AC4/AC5, §2-§4).

The symmetric twin of `tropo-lock-dev-spec.py`. Where the dev lock is the only
way a dev cycle starts, this is the only way a release cycle starts, and the two
share one transaction mechanism (`lib/lock_transaction.py`) rather than two that
drift apart.

Locking a release-plan is ONE indivisible act that:

  1. gathers a fan-in row for every ordered member, binding the seven AC5 values
  2. refuses any member that is not `done`, or that another release-plan still
     holds a reservation on
  3. writes the fan-in manifest and records its digest on the plan
  4. opens exactly one release activation and one immutable release run
  5. flips the plan to `status: locked` with all five contract fields

WHY THE ROWS ARE GATHERED AND NEVER FABRICATED
----------------------------------------------
Every binding is read from substrate that already exists, and a member whose
binding is absent is REFUSED rather than defaulted. A row is the release's claim
that this exact work, in this exact verified state, is shipping; a default value
would make the claim while destroying its content. In particular
`tested_final_commit` comes from the stage-3 close, so a dev-spec that never
closed against one unchanged tested tree cannot be fanned in at all — which is
the intended consequence, not a gap.

Exit codes:
    0   Locked
    1   Refused (plan not lockable, member gate failed, binding missing) —
        nothing was written
    2   Applied partially and could not fully unwind; the journal names what is
        stranded
    3   Argument / environment error
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util as _ilu
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
PIPELINE_RUNS = VAULT_ROOT / "vault" / "pipeline-runs"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import fan_in, ignition, lock_transaction as lt  # noqa: E402
from lib import release_saga

# The seed renderer lives in the dev-spec lock tool and is now pipeline-neutral.
# Loaded by path because the filename is hyphenated; imported rather than
# reimplemented, so both locks emit one envelope.
_lock_dev_spec = _ilu.module_from_spec(
    _ilu.spec_from_file_location(
        "_release_lock_seed_renderer",
        Path(__file__).resolve().with_name("tropo-lock-dev-spec.py"),
    )
)
_lock_dev_spec.__spec__.loader.exec_module(_lock_dev_spec)

try:
    from lib import fast_yaml as _yaml_mod

    def _yaml_load(text: str):
        return _yaml_mod.safe_load(text)
except Exception:  # pragma: no cover - fallback for a stripped environment
    import yaml

    def _yaml_load(text: str):
        return yaml.safe_load(text)

RELEASE_PIPELINE_UID = "634913c2"
# ONE declared set, shared with the preflight's lock-plan-record gate
# (f015ef8ff398 step 2, talos-t63 2026-09-06): the lock's pre-lock states and
# the preflight's "is a plan state" used to be two hand lists that disagreed,
# and the disagreement refused Mike's v1.95 ignition. The set lives in
# lib/release_capsule_contract beside the capsule's enum; this name is kept so
# every reader in this file and its tests stays valid.
from lib.release_capsule_contract import LOCKABLE_STATUSES  # noqa: E402
UID_RE = re.compile(r"^[0-9a-f]{8}(?:[0-9a-f]{4})?$")  # accepts-both (3d430852)


class LockRefused(Exception):
    pass


def _resolve_path(uid: str, files_dir: Path) -> Optional[Path]:
    """The file a governed uid lives in: `<uid>.md`, or the slug-named
    `<slug>-<uid>.md` canonical since the 2026-08-31 filename ruling.

    Every fan-in binding resolved `files_dir / f"{uid}.md"` and nothing else,
    so the first slug-named test-spec cited as acceptance_evidence was refused
    as "does not resolve" while check-one resolved it fine. Third reader of
    the same convention change (after tropo-recycle.py and tropo-close-dev.py).
    The name proposes; the frontmatter decides — a slug match is confirmed by
    the file's own `uid:` before it is trusted. (metis-g117, 2026-09-03)
    """
    bare = files_dir / f"{uid}.md"
    if bare.is_file():
        return bare
    for cand in sorted(files_dir.glob(f"*-{uid}.md")):
        try:
            head = cand.read_text(encoding="utf-8", errors="replace")[:65536]
        except OSError:
            continue
        if re.search(rf"^uid:\s*['\"]?{re.escape(uid)}['\"]?\s*$", head, flags=re.MULTILINE):
            return cand
    return None


def read_entry(uid: str, files_dir: Path = VAULT_FILES) -> Optional[dict]:
    path = _resolve_path(uid, files_dir)
    if path is None or not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = _yaml_load(parts[1]) or {}
    except Exception:
        return None
    if not isinstance(fm, dict):
        return None
    return {"uid": uid, "frontmatter": fm, "raw": raw, "path": path}


def all_release_plans(files_dir: Path = VAULT_FILES) -> list[dict]:
    """Every release-plan's frontmatter, for the reservation scan.

    Read from the files rather than the index on purpose: the index is
    per-machine derived state (gitignored), and a gate that can be wrong because
    a rebuild has not run is not a gate.
    """
    plans = []
    for path in sorted(files_dir.glob("*.md")):
        entry = read_entry(path.stem, files_dir)
        if entry and entry["frontmatter"].get("type") == "release-plan":
            plans.append(entry["frontmatter"])
    return plans


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_pipeline_run(activation_uid: str, files_dir: Path) -> Optional[dict]:
    for path in sorted(files_dir.glob("*.md")):
        entry = read_entry(path.stem, files_dir)
        if not entry:
            continue
        fm = entry["frontmatter"]
        if fm.get("type") == "pipeline-run" and fm.get("activation") == activation_uid:
            return fm
    return None


def _acceptance_evidence_digest(uids: list, files_dir: Path) -> str:
    """Hash the CONTENT the evidence UIDs resolve to, not the list of names.

    Hashing the UID list would bind the release to a set of pointers whose
    targets can change afterwards — the citation would keep resolving while the
    thing cited had moved. Hashing content makes the binding mean what it says.
    """
    digest = hashlib.sha256()
    for uid in sorted(str(u) for u in uids):
        path = _resolve_path(uid, files_dir)
        if path is None or not path.is_file():
            raise LockRefused(
                f"acceptance_evidence names {uid}, which does not resolve. A "
                "release cannot bind to evidence that is not there."
            )
        digest.update(uid.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


DEV_CLOSE_EVENT = "dev_closed"


#: A receipt must declare itself as one, so a bare `{"event": "dev_closed"}`
#: line — the shape the first version accepted — is no longer sufficient.
CANONICAL_RECEIPT_KIND = "canonical-dev-close"

#: The links a canonical receipt binds. A consumer that checks one of these is
#: checking nothing: the point is that they must all agree with each other AND
#: with the substrate they name.
RECEIPT_IDENTITY_FIELDS = ("dev_spec_uid", "activation_uid", "pipeline_run_uid",
                           "activation_root_uid")


def read_canonical_close_receipt(
    dev_spec_uid: str, activation_uid: str, run_uid: str, files_dir: Path,
) -> dict:
    """Exactly one canonical receipt whose every link resolves and agrees.

    BLOCKER 3 (argus-a147). The first version scanned the run folder for any
    line containing `dev_closed` and took its `tested_sha`. Everything about
    that was forgeable:

      any *.jsonl under any matching folder counted, so a hand-written line was
      a valid receipt

      the trace was never checked, so a receipt from a DIFFERENT run satisfied
      this one

      nothing bound the spec, activation, run or root together, so the SHA could
      belong to a cycle unrelated to the member being fanned in

      acceptance evidence was any UID that resolved — a note saying "looks fine"
      passed, and so did evidence pointing at a failing report

    A release's whole claim is that this exact work, in this exact verified
    state, is shipping. That claim cannot rest on a field; it has to rest on a
    chain where each link names the next and every one of them checks out.
    """
    """The one tested SHA the dev close actually recorded, or a refusal.

    Reads the run's own event log rather than any frontmatter field, because the
    close event is the artifact the close produced and frontmatter is a
    projection anyone can write. Requires exactly one dev_closed event binding
    exactly one 40-hex SHA:

      none      the cycle never closed against a tested tree, so there is
                nothing for this row to bind
      several   the run closed more than once against different trees, so no
                single tree is THE tested one

    Fail-closed, harm named (deb77758): a release citing provenance that was
    never established is a false success that outlives the cycle — once
    published, the citation cannot be withdrawn from what consumed it.
    """
    run_folder = _run_folder_for(run_uid, files_dir)
    if run_folder is None or not run_folder.is_dir():
        raise LockRefused(
            f"dev-spec {dev_spec_uid}: no run folder resolves for run {run_uid}, so "
            "its close receipt cannot be read. A release binds to the close that "
            "happened, not to a frontmatter field that may have been hand-written."
        )

    expected = {
        "dev_spec_uid": dev_spec_uid,
        "activation_uid": activation_uid,
        "pipeline_run_uid": run_uid,
    }

    receipts: list = []
    rejected: list = []
    for events_path in sorted(run_folder.glob("*.jsonl")):
        for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or DEV_CLOSE_EVENT not in line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") != DEV_CLOSE_EVENT:
                continue
            data = event.get("data") or {}

            if data.get("receipt_kind") != CANONICAL_RECEIPT_KIND:
                rejected.append("a dev_closed line that does not declare itself a "
                                f"{CANONICAL_RECEIPT_KIND} receipt")
                continue

            # The trace must be THIS run's. A receipt copied from another cycle
            # otherwise satisfies this one.
            if event.get("trace_id") not in (activation_uid, None):
                rejected.append(f"a receipt traced to {event.get('trace_id')!r}, "
                                f"not to activation {activation_uid}")
                continue

            mismatched = [f"{key}={data.get(key)!r} (expected {value})"
                          for key, value in expected.items()
                          if str(data.get(key) or "") != str(value)]
            if mismatched:
                rejected.append("a receipt whose identity disagrees: "
                                + "; ".join(mismatched))
                continue

            root_uid = data.get("activation_root_uid")
            if not root_uid or not (files_dir / f"{root_uid}.md").is_file():
                rejected.append(f"a receipt naming root {root_uid!r}, which does "
                                "not resolve")
                continue

            sha = data.get("tested_commit_sha") or data.get("tested_sha")
            if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)):
                rejected.append(f"a receipt whose tested SHA {sha!r} is not 40 hex")
                continue

            if data.get("verdict") not in (None, "complete"):
                rejected.append(f"a receipt with verdict {data.get('verdict')!r}, "
                                "which is not a passing close")
                continue

            receipts.append(data)

    if not receipts:
        detail = ("; ".join(sorted(set(rejected))[:3]) if rejected
                  else "none present at all")
        raise LockRefused(
            f"dev-spec {dev_spec_uid}: run {run_uid} carries no CANONICAL "
            f"{DEV_CLOSE_EVENT} receipt ({detail}). Stage-3 close writes one that "
            "binds dev-spec, activation, run, root, journal and tested tree "
            "together; a release cannot bind to provenance that was never "
            "established, and a bare close line is a shape anyone can type."
        )

    distinct = {r.get("tested_commit_sha") or r.get("tested_sha") for r in receipts}
    if len(receipts) > 1 and len(distinct) > 1:
        raise LockRefused(
            f"dev-spec {dev_spec_uid}: run {run_uid} carries {len(receipts)} "
            f"canonical receipts binding {len(distinct)} different trees "
            f"({', '.join(sorted(distinct))}). No single tree is the tested one."
        )
    if len(receipts) > 1:
        raise LockRefused(
            f"dev-spec {dev_spec_uid}: run {run_uid} carries {len(receipts)} "
            "canonical close receipts. A cycle closes ONCE; duplicates mean the "
            "close ran more than once and which one governs is undecidable."
        )
    return receipts[0]


def _run_folder_for(run_uid: str, files_dir: Path) -> Optional[Path]:
    entry = read_entry(run_uid, files_dir)
    if entry is None:
        return None
    declared = entry["frontmatter"].get("run_folder")
    if declared:
        candidate = files_dir.parents[1] / str(declared)
        if candidate.is_dir():
            return candidate
    runs = files_dir.parent / "pipeline-runs"
    if not runs.is_dir():
        return None
    for folder in sorted(runs.glob(f"*{run_uid}*")):
        if folder.is_dir():
            return folder
    return None


#: Entry types that can attest that acceptance criteria PASSED. An arbitrary
#: note cannot: it has no verdict field, so "the ACs passed" and "someone wrote
#: something down" become the same statement.
EVIDENCE_TYPES = frozenset({"completion-report", "test-spec", "release",
                            "vela-test-plan", "verification-report"})

#: Values in a verdict/status field that mean the thing actually passed.
PASSING_VERDICTS = frozenset({"pass", "passed", "complete", "done", "shipped",
                              "green", "accepted"})


def _assert_typed_passing_evidence(dev_spec_uid: str, receipt_uid: str,
                                   evidence: list, files_dir: Path) -> None:
    """Acceptance evidence must be typed AND passing (argus-a147 blocker 3).

    The first version required only that each UID resolved. A note saying
    "looks fine" satisfied it, and so did a completion report whose verdict was
    FAIL — the check proved a file existed, not that anything passed.

    Fail-closed, harm named (deb77758): this is the false-completion class. A
    release that fans in a failed cycle ships work that never passed while its
    own manifest attests that it did, and that attestation cannot be withdrawn
    from whatever consumed it.
    """
    typed_passing = []
    problems = []
    for uid in [str(u) for u in evidence]:
        path = _resolve_path(uid, files_dir)
        if path is None or not path.is_file():
            raise LockRefused(
                f"dev-spec {dev_spec_uid}: acceptance_evidence names {uid}, which "
                "does not resolve. A release cannot bind to evidence that is not "
                "there."
            )
        fm = (read_entry(uid, files_dir) or {}).get("frontmatter", {})
        entry_type = str(fm.get("type") or "")
        if entry_type not in EVIDENCE_TYPES:
            problems.append(f"{uid} is type {entry_type!r}, which carries no verdict")
            continue
        verdict = str(fm.get("verdict") or fm.get("status") or "").strip().lower()
        if verdict not in PASSING_VERDICTS:
            problems.append(f"{uid} is {entry_type} at verdict/status {verdict!r}, "
                            "which is not a pass")
            continue
        typed_passing.append(uid)

    if not typed_passing:
        raise LockRefused(
            f"dev-spec {dev_spec_uid}: no acceptance evidence both TYPED and "
            f"PASSING ({'; '.join(problems) or 'none supplied'}). Requiring only "
            "that a UID resolves proves a file exists, not that anything passed — "
            "a note saying 'looks fine' and a report whose verdict is FAIL both "
            f"satisfied that. Accepted types: {sorted(EVIDENCE_TYPES)}."
        )


def gather_row(dev_spec_uid: str, files_dir: Path = VAULT_FILES) -> dict:
    """Build one fan-in row from substrate, refusing on any absent binding."""
    entry = read_entry(dev_spec_uid, files_dir)
    if entry is None:
        raise LockRefused(f"dev-spec {dev_spec_uid} does not resolve")
    fm = entry["frontmatter"]
    if fm.get("type") != "dev-spec":
        raise LockRefused(
            f"{dev_spec_uid} is type {fm.get('type')!r}, not a dev-spec"
        )

    activation_uid = fm.get("dev_spec_activation_uid")
    if not activation_uid:
        raise LockRefused(
            f"dev-spec {dev_spec_uid} carries no dev_spec_activation_uid, so the "
            "row cannot name which cycle produced it"
        )

    run = _find_pipeline_run(str(activation_uid), files_dir)
    if run is None:
        raise LockRefused(
            f"no pipeline-run resolves for activation {activation_uid} "
            f"(dev-spec {dev_spec_uid}); the row cannot name which run ran it"
        )

    # NO-GO item 3: consume the immutable dev-close RECEIPT, not whichever
    # frontmatter field happens to be populated.
    #
    # The first version searched spec, then activation, then run, for any of
    # final_commit / tested_final_commit / tested_sha and took the first hit.
    # That is syntactic: `final_commit` is a generic field any gesture may
    # stamp, the fallback chain means the row cannot say WHICH artifact it
    # believed, and a spec hand-edited with a plausible SHA satisfied it. A
    # release's provenance has to come from the close that actually happened.
    receipt = read_canonical_close_receipt(
        dev_spec_uid, str(activation_uid), str(run.get("uid")), files_dir)
    tested = receipt.get("tested_commit_sha") or receipt.get("tested_sha")

    receipt_uid = fm.get("completion_report_uid") or fm.get("completion_receipt_uid")
    if not receipt_uid:
        raise LockRefused(
            f"dev-spec {dev_spec_uid} names no completion report; the row cannot "
            "bind a completion receipt hash"
        )
    receipt_path = _resolve_path(str(receipt_uid), files_dir)
    if receipt_path is None or not receipt_path.is_file():
        raise LockRefused(
            f"completion report {receipt_uid} for dev-spec {dev_spec_uid} does not resolve"
        )

    evidence = fm.get("acceptance_evidence") or []
    if not evidence:
        raise LockRefused(
            f"dev-spec {dev_spec_uid} has empty acceptance_evidence. The completion "
            "receipt says the run ENDED; acceptance evidence says the ACs PASSED. "
            "Without the second, a run that finished-but-failed fans in looking "
            "identical to one that passed."
        )
    _assert_typed_passing_evidence(dev_spec_uid, receipt_uid, evidence, files_dir)

    return {
        "dev_spec_uid": dev_spec_uid,
        "dev_spec_sha256": _sha256_file(entry["path"]),
        "activation_uid": str(activation_uid),
        "pipeline_run_uid": str(run.get("uid")),
        "tested_final_commit": tested,
        "completion_receipt_sha256": _sha256_file(receipt_path),
        "acceptance_evidence_sha256": _acceptance_evidence_digest(evidence, files_dir),
    }


def _patch_plan_frontmatter(raw: str, fields: dict) -> str:
    """Surgical line-level frontmatter edit, matching the dev lock's discipline.

    A full YAML re-serialization would reformat a live hand-authored plan's
    quoting and ordering, producing a diff where almost nothing changed.
    """
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise LockRefused("release-plan has no parseable frontmatter block")
    body_lines = parts[1].strip("\n").split("\n")

    managed = set(fields) | {"status", "locked_by", "locked_at"}

    # BLOCK-AWARE removal. The first version matched `^key:\s`, which never
    # matches a key whose value is a block (`dev_spec_uids:` has nothing after
    # the colon), and would have left the indented items behind even if it had.
    # Result: a second `dev_spec_uids:` was appended and the plan carried two
    # values for one key — legal-looking text that YAML resolves by silently
    # taking the last. argus-a147 NO-GO item 5.
    out: list[str] = []
    skipping = False
    for line in body_lines:
        key_match = re.match(r"^([A-Za-z0-9_]+):", line)
        if key_match:
            skipping = key_match.group(1) in managed
            if skipping:
                continue
        elif skipping and (line.startswith((" ", "\t")) or not line.strip()):
            continue  # a continuation line of the block being dropped
        else:
            skipping = False
        out.append(line)

    # FIELD-DRIVEN, not a hardcoded roster. The first version emitted a fixed
    # five keys and a literal `status: locked`, so `release_entry_uid` and
    # `saga_id` were passed in by the caller and silently dropped on the floor —
    # the plan never carried the release identity the spec's bidirectional
    # table requires, and nothing failed, because the caller had no way to
    # notice its own arguments being ignored. The literal status also made this
    # function unusable for any transition other than locking: abandonment
    # would have re-locked the plan it was ending.
    if "status" in fields:
        out.append(f"status: {fields['status']}")
    for key, value in fields.items():
        if key == "status":
            continue
        if value is None:
            continue
        if isinstance(value, list):
            out.append(f"{key}:")
            out.extend(f"  - {v}" for v in value)
        else:
            out.append(f"{key}: '{value}'")

    rendered = "\n".join(out)
    _refuse_duplicate_keys(rendered)
    return "---\n" + rendered + "\n---" + parts[2]


def _refuse_duplicate_keys(frontmatter_text: str) -> None:
    """A duplicate top-level key is refused rather than silently last-wins.

    Fail-closed, harm named (deb77758): YAML resolves duplicates by taking the
    last, so a plan can display one member list and be READ as another. A
    release whose fan-in digest was computed over a different list than the one
    a reader sees is a false-success that survives inspection.
    """
    seen: dict[str, int] = {}
    for line in frontmatter_text.split("\n"):
        match = re.match(r"^([A-Za-z0-9_]+):", line)
        if match:
            seen[match.group(1)] = seen.get(match.group(1), 0) + 1
    duplicates = sorted(k for k, n in seen.items() if n > 1)
    if duplicates:
        raise LockRefused(
            f"the patched frontmatter carries duplicate key(s): {', '.join(duplicates)}. "
            "YAML resolves duplicates by taking the last, so the plan would display "
            "one value and be read as another."
        )


def _require_lock_time_field(fm: dict, field: str, plan_uid: str):
    """A lock-time release field must be real, or the lock refuses.

    dev-spec 2fae6312. The release entry is authored at plan lock, so every
    field it carries is derived from the plan rather than from a shipped
    artifact. A missing one is refused here instead of being filled with a
    placeholder: a `TBD`, an empty list, or a null in a costume satisfies the
    schema and tells the next reader something false with the capsule's
    authority behind it.
    """
    value = fm.get(field)
    if value is None or value == "" or value == [] or value == {}:
        raise LockRefused(
            "release-plan {} declares no {}. The lock authors a release entry "
            "from these fields, and a placeholder there would be a fabricated "
            "fact carrying the release capsule's authority.".format(plan_uid, field)
        )
    if isinstance(value, str) and value.strip().upper() in ("TBD", "N/A", "NONE"):
        raise LockRefused(
            "release-plan {} sets {} to {!r}, which is a placeholder wearing a "
            "value's clothes.".format(plan_uid, field, value)
        )
    return value


def _render_release_entry(
    release_uid: str, plan_uid: str, plan_fm: dict, actor: str, saga_id: str,
    activation_uid: str, run_uid: str, root_uid: str,
) -> str:
    """The pre-ship release entry, derived entirely from the locked plan.

    Born at lock so the release has one identity from the beginning. Ship-only
    fields are absent rather than invented; the release capsule's v1.89
    amendment says exactly which those are.
    """
    today = time.strftime("%Y-%m-%d")
    version = _require_lock_time_field(plan_fm, "release_version", plan_uid)
    capabilities = _require_lock_time_field(plan_fm, "capabilities_touched", plan_uid)
    kernel = _require_lock_time_field(plan_fm, "kernel_substrate_touched", plan_uid)
    foundation = _require_lock_time_field(plan_fm, "foundation", plan_uid)
    ratchets = _require_lock_time_field(plan_fm, "ratchet_targets", plan_uid)
    hubs = _require_lock_time_field(plan_fm, "hub_summaries", plan_uid)
    title = str(plan_fm.get("release_title") or "Tropo-OS v{}".format(version))
    description = str(
        plan_fm.get("release_description")
        or "Release {} governed by release-plan {}.".format(version, plan_uid)
    )
    members = [plan_uid] + [
        str(u) for u in (plan_fm.get("release_program_projects") or [])
    ]
    return (
        "---\n"
        "uid: {uid}\n"
        "type: release\n"
        "title: {title}\n"
        "description: {description}\n"
        "status: pre-ship\n"
        "state: active\n"
        "owner: {actor}\n"
        "release_version: {version}\n"
        "shipped_release_plan: {plan}\n"
        "release_activation_uid: {activation}\n"
        "release_pipeline_run_uid: {run}\n"
        "activation_root_uid: {root}\n"
        "saga_id: {saga}\n"
        "capabilities_touched: {capabilities}\n"
        "kernel_substrate_touched: {kernel}\n"
        "foundation: {foundation}\n"
        "ratchet_targets: {ratchets}\n"
        "hub_summaries: {hubs}\n"
        "member_of: {members}\n"
        "created: {today}\n"
        "modified: {today}\n"
        "created_by: {actor}\n"
        "schema_version: 2\n"
        "governed_by: 8dd772a0\n"
        "---\n"
        "\n"
        "# {title_plain}\n"
        "\n"
        "Pre-ship release identity, authored by the lock of release-plan "
        "{plan}. Ship-only fields are absent until the facts exist: this entry "
        "records what the release IS, not what it will have done.\n"
    ).format(
        uid=json.dumps(release_uid), title=json.dumps(title),
        description=json.dumps(description), actor=actor,
        version=json.dumps(str(version)), plan=json.dumps(plan_uid),
        activation=json.dumps(activation_uid), run=json.dumps(run_uid),
        root=json.dumps(root_uid), saga=json.dumps(saga_id),
        capabilities=json.dumps(capabilities), kernel=json.dumps(kernel),
        foundation=json.dumps(foundation), ratchets=json.dumps(ratchets),
        hubs=json.dumps(hubs), members=json.dumps(members),
        today=json.dumps(today), title_plain=title,
    )


def _refuse_on_unmet_preconditions(release_plan_uid, fm, files_dir) -> None:
    """Run the lock-static boundary before locking. AC3 of 61f3153a.

    Fail-closed, harm named (deb77758): a release-plan locked over unmet
    governance preconditions opens a run, reserves its members and writes an
    immutable fan-in manifest — a transaction whose digest attests to a set that
    was never eligible, and which cannot be withdrawn from the receipts that
    later cite it.

    THIS TOOL REFERENCED THE PREFLIGHT ZERO TIMES. Seven gates were registered
    at `lock-static` — the boundary named for this gesture — and the only
    production caller of `run_phase` anywhere was the publish tool, for a
    different boundary. The preconditions existed and the gesture they govern
    never asked.

    WARN-SAFE ON ITS OWN FAILURE. A gate that cannot reach an answer must not
    refuse the lock: an unreadable input is "I cannot see", never "you are
    wrong". Operational failures surface and the lock proceeds, which is the
    deb77758 default and the reason this catches GateInputError separately from
    a REFUSED verdict.
    """
    studio_root = Path(files_dir).resolve().parent.parent
    try:
        from lib import release_gate_inputs as gate_inputs
        from lib.release_gates import VERDICT_REFUSED

        preflight = _load_preflight(studio_root)
        context = gate_inputs.build_context(
            studio_root, release_plan_uid,
            version_string=str(fm.get("release_version") or ""),
        )
        outcomes = preflight.build_registry().run_phase("lock-static", context)
    except Exception as exc:  # noqa: BLE001 — operational, never a verdict
        print(
            f"  [WARN] lock-static preconditions could not be evaluated "
            f"({type(exc).__name__}: {exc}); proceeding per warn-safe. The lock "
            f"is not gated on a check that could not run.",
            file=sys.stderr,
        )
        return

    refused = [o for o in outcomes if o.verdict == VERDICT_REFUSED]
    if not refused:
        return
    # EVERY unmet precondition, not the first. An operator who fixes the named
    # one only to meet the next is being drip-fed a truth this already had —
    # which is the whole reason the retrospective asked for one report.
    detail = "\n  ".join(f"{o.gate_id}: {o.detail}" for o in refused)
    raise LockRefused(
        f"release-plan {release_plan_uid} has {len(refused)} unmet governance "
        f"precondition(s):\n  {detail}"
    )


def _load_preflight(studio_root: Path):
    import importlib.util

    path = Path(studio_root) / "vault" / "tools" / "tropo-release-preflight.py"
    spec = importlib.util.spec_from_file_location("tropo_release_preflight_ac3", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_release_lock(
    release_plan_uid: str,
    locked_by: str,
    files_dir: Path = VAULT_FILES,
    runs_dir: Path = PIPELINE_RUNS,
) -> list:
    """--check (f015ef8ff398, Mike's word at the fifth v1.95 refusal): EVERY unmet
    precondition at once, nothing written, no uid consumed.

    The pure phase refuses at the first unmet precondition by design (AC4: zero
    partial state). That is right for the lock and wrong for the operator, who
    was handed five refusals in sequence on 2026-09-06 -- each correct, none
    knowable before the run. This runs the same preconditions as independent
    probes, records each refusal instead of raising it, and finishes with the
    full pure phase under a stub mint so anything the probes do not cover is
    still named. Returns the list of problems; empty means the lock would pass.
    """
    problems: list = []
    entry = read_entry(release_plan_uid, files_dir)
    if entry is None:
        return [f"release-plan {release_plan_uid} does not resolve"]
    fm = entry["frontmatter"]
    if fm.get("type") != "release-plan":
        return [f"{release_plan_uid} is type {fm.get('type')!r}, not a release-plan"]
    status = str(fm.get("status") or "").strip().lower()
    if status == "locked":
        problems.append(f"release-plan {release_plan_uid} is already locked")
    elif status not in LOCKABLE_STATUSES:
        problems.append(f"release-plan {release_plan_uid} is status {status!r}; lockable from "
                        f"{sorted(LOCKABLE_STATUSES)} (cure: set status to one of them)")
    ordered = [str(u) for u in (fm.get("dev_spec_uids") or [])]
    if not ordered:
        problems.append(f"release-plan {release_plan_uid} lists no dev_spec_uids "
                        "(cure: lock each member dev-spec; the lock appends it)")
    try:
        _refuse_on_unmet_preconditions(release_plan_uid, fm, files_dir)
    except LockRefused as exc:
        problems.append(str(exc))
    # The lock-time fields the release entry is born from (2fae6312): each one
    # named on its own, not the first missing one.
    for field in ("release_version", "capabilities_touched", "kernel_substrate_touched",
                  "foundation", "ratchet_targets", "hub_summaries"):
        try:
            _require_lock_time_field(fm, field, release_plan_uid)
        except LockRefused as exc:
            problems.append(str(exc))
    for uid in ordered:
        spec = read_entry(uid, files_dir)
        if spec is None:
            problems.append(f"member dev-spec {uid} does not resolve")
            continue
        sfm = spec["frontmatter"]
        evidence = sfm.get("acceptance_evidence") or []
        if not evidence:
            problems.append(f"dev-spec {uid} has empty acceptance_evidence")
            continue
        try:
            _assert_typed_passing_evidence(uid, str(sfm.get("completion_report_uid") or ""),
                                           evidence, files_dir)
        except LockRefused as exc:
            problems.append(str(exc))
    # Everything the probes above do not cover (release-entry fields such as
    # foundation, the declaration snapshot, receipt binding) still refuses one
    # at a time inside the pure phase; run it once under a stub mint so the
    # first of those is named too, without consuming a uid or writing a byte.
    import itertools as _it
    _counter = _it.count(1)

    def _stub_mint(*_a, **_k):
        return f"f015chk{next(_counter):05x}"

    try:
        plan_release_lock(release_plan_uid, locked_by, files_dir, runs_dir, mint=_stub_mint)
    except LockRefused as exc:
        msg = str(exc)
        if not any(msg.split("\n")[0] in p or p.split("\n")[0] in msg for p in problems):
            problems.append(msg)
    except Exception as exc:  # noqa: BLE001 -- operational, still named
        problems.append(f"pure phase could not complete: {type(exc).__name__}: {exc}")
    return problems


def plan_release_lock(
    release_plan_uid: str,
    locked_by: str,
    files_dir: Path = VAULT_FILES,
    runs_dir: Path = PIPELINE_RUNS,
    mint: Optional[callable] = None,
) -> lt.LockPlan:
    """The PURE phase: everything decided, nothing written.

    Every refusal AC4 names as "leaves zero partial state" is raised from here.
    """
    entry = read_entry(release_plan_uid, files_dir)
    if entry is None:
        raise LockRefused(f"release-plan {release_plan_uid} does not resolve")
    fm = entry["frontmatter"]
    if fm.get("type") != "release-plan":
        raise LockRefused(f"{release_plan_uid} is type {fm.get('type')!r}, not a release-plan")

    status = str(fm.get("status") or "").strip().lower()
    if status == "locked":
        raise LockRefused(
            f"release-plan {release_plan_uid} is already locked. Re-locking is not "
            "a retry: the lock opened a run and reserved members, and doing it "
            "again would open a second contract for one release."
        )
    if status not in LOCKABLE_STATUSES:
        raise LockRefused(
            f"release-plan {release_plan_uid} is status {status!r}; lockable from "
            f"{sorted(LOCKABLE_STATUSES)}"
        )

    ordered = [str(u) for u in (fm.get("dev_spec_uids") or [])]
    if not ordered:
        raise LockRefused(
            f"release-plan {release_plan_uid} lists no dev_spec_uids. Ordered "
            "members are the plan's content; locking an empty plan would produce "
            "a valid digest for a release that attests to nothing."
        )

    _refuse_on_unmet_preconditions(release_plan_uid, fm, files_dir)

    plans = all_release_plans(files_dir)
    members = []
    for uid in ordered:
        spec = read_entry(uid, files_dir)
        if spec is None:
            raise LockRefused(f"member dev-spec {uid} does not resolve")
        members.append({"dev_spec": dict(spec["frontmatter"], uid=uid),
                        "row": gather_row(uid, files_dir)})

    rows = fan_in.build_rows(members, plans, release_plan_uid)

    # NO-GO item 4: read the root's real version and refuse an unfit root. The
    # first version hardcoded pipeline_version '2.0' while 634913c2 is 1.0.0 and
    # draft, so every run recorded a contract it was not executing.
    def _entry_bytes(uid):
        path = files_dir / f"{uid}.md"
        return path.read_bytes() if path.is_file() else None

    snapshot = ignition.snapshot_declarations(
        RELEASE_PIPELINE_UID,
        lambda uid: read_entry(uid, files_dir),
        lambda uid: _resolve_step_uids(uid, files_dir),
        read_bytes=_entry_bytes,
    )

    minter = mint or _mint_uid
    root_uid = minter(files_dir)
    activation_uid = minter(files_dir, exclude={root_uid})
    run_uid = minter(files_dir, exclude={root_uid, activation_uid})
    release_uid = minter(files_dir, exclude={root_uid, activation_uid, run_uid})
    # Derived, never minted: replay computes the same saga identity from the
    # same run, so one release can never open a second saga over itself.
    saga_id = release_saga.saga_id_for(run_uid)
    run_name = f"release-pipeline-{run_uid}-{time.strftime('%Y-%m-%d')}"
    run_folder = runs_dir / run_name
    manifest_rel = f"vault/pipeline-runs/{run_name}/fan-in-manifest.json"

    plan = lt.LockPlan(kind="release-plan-lock", subject_uid=release_plan_uid,
                       actor=locked_by)
    plan.notes = {
        "release_pipeline": RELEASE_PIPELINE_UID,
        "member_count": len(rows),
        "fan_in_digest": fan_in.manifest_digest(rows),
    }

    plan.notes["declaration_digest"] = snapshot.digest
    plan.notes["pipeline_version"] = snapshot.pipeline_version

    plan.create(run_folder / "fan-in-manifest.json",
                fan_in.render_manifest(rows, release_plan_uid))
    plan.create(run_folder / "declaration-snapshot.json",
                json.dumps(snapshot.as_dict(), indent=2, sort_keys=True) + "\n")
    plan.create(files_dir / f"{root_uid}.md",
                ignition.render_activation_root(
                    root_uid, activation_uid, release_plan_uid, "release-plan",
                    locked_by, time.strftime("%Y-%m-%d"), RELEASE_PIPELINE_UID),
                governed=True)
    # S3 AC7 (176a8995): the activation carries the minted release_entry_uid
    # in the SAME transaction as the plan, run, entry and run_created row —
    # fire's _release_entry_uid_for reads it off the activation and v1.90's
    # lock never wrote it (a6ebf96e was patched by hand after the confirm).
    activation_text = ignition.render_activation(
        activation_uid, root_uid, run_uid, RELEASE_PIPELINE_UID,
        release_plan_uid, "release-plan", locked_by, time.strftime("%Y-%m-%d"),
        release_entry_uid=release_uid,
    )
    plan.create(files_dir / f"{activation_uid}.md", activation_text, governed=True)
    plan.create(files_dir / f"{run_uid}.md",
                _render_run(run_uid, activation_uid, release_plan_uid, locked_by,
                            run_name, snapshot, release_uid, saga_id, root_uid),
                governed=True)
    # dev-spec 2fae6312: the release identity and its journal are born here, in
    # the SAME transaction as the activation, root and run. Any of them landing
    # without the others is the partial state AC5 refuses.
    plan.create(files_dir / f"{release_uid}.md",
                _render_release_entry(release_uid, release_plan_uid, fm, locked_by,
                                      saga_id, activation_uid, run_uid, root_uid),
                governed=True)
    plan.create(run_folder / "run.jsonl",
                _lock_dev_spec.render_lock_run_created(
                    run_uid=run_uid,
                    activation_uid=activation_uid,
                    root_uid=root_uid,
                    pipeline_uid=RELEASE_PIPELINE_UID,
                    pipeline_version=snapshot.pipeline_version,
                    actor=locked_by,
                    subject_kind="release-plan",
                    subject_uid=release_plan_uid,
                    extra={"saga_id": saga_id, "release_entry_uid": release_uid},
                ))
    plan.notes["release_entry_uid"] = release_uid
    plan.notes["saga_id"] = saga_id
    # v1.91 S2 AC1/AC5 (3fb41c99): carried for scope_locked's bus emission in
    # lock_release_plan(), after apply_plan() durably commits this transaction.
    plan.notes["activation_uid"] = activation_uid
    plan.notes["activation_root_uid"] = root_uid
    plan.notes["release_pipeline_run_uid"] = run_uid

    plan.patch(
        entry["path"], entry["raw"],
        _patch_plan_frontmatter(entry["raw"], {
            "status": "locked",
            "locked_by": locked_by,
            "locked_at": time.strftime("%Y-%m-%d"),
            "dev_spec_uids": ordered,
            "fan_in_manifest_ref": manifest_rel,
            "fan_in_digest": fan_in.manifest_digest(rows),
            "release_activation_uid": activation_uid,
            # The spec's bidirectional identity table requires all four on the
            # plan. root and entry were being dropped by the patcher.
            "activation_root_uid": root_uid,
            "release_pipeline_run_uid": run_uid,
            "release_entry_uid": release_uid,
            "saga_id": saga_id,
        }),
    )
    return plan


#: Terminal state each locked record reaches when a release is abandoned.
#: Declared as a table rather than inline writes so the test can assert the
#: post-state from the same source the transaction applies, and so a record
#: added to the lock cannot be silently forgotten here.
ABANDON_TERMINAL_STATES = {
    "plan": {"status": "cancelled"},
    "activation": {"status": "retired"},
    "run": {"status": "cancelled"},
    "root": {"status": "cancelled", "state": "archived"},
    "release_entry": {"status": "pre-ship", "state": "archived"},
}


def _abandon_receipt(plan_uid: str, reason: str, principal: str, at: str) -> str:
    """One receipt, shared by every record the transaction touches.

    Content-addressed over the abandonment's own facts so the same abandonment
    computes the same receipt on replay, and two different abandonments of one
    plan cannot collide.
    """
    payload = json.dumps(
        {"plan": plan_uid, "reason": reason, "principal": principal, "at": at},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _shipped_evidence(release_entry: Optional[dict]) -> Optional[str]:
    """Why this release may no longer be abandoned, or None.

    Abandonment is a pre-ship act. Once anything is public the honest move is
    forward-only compensation, never retracting the record of a thing that
    happened — so this refuses rather than archiving a shipped release.
    """
    if release_entry is None:
        return None
    fm = release_entry["frontmatter"]
    status = str(fm.get("status") or "").strip().lower()
    if status and status != "pre-ship":
        return f"release entry is status {status!r}, not 'pre-ship'"
    for field in ("publication_receipt_sha256", "released_at", "public_asset_url"):
        if fm.get(field):
            return f"release entry carries {field}, so it has shipped"
    return None


def plan_release_abandon(
    release_plan_uid: str,
    abandoned_by: str,
    reason: str,
    files_dir: Path = VAULT_FILES,
) -> lt.LockPlan:
    """The PURE phase of abandonment: one transaction, or none.

    A lock opens five correlated records and a reservation on every member.
    Abandoning it has to close all of them together — a run left `active`
    beside a `cancelled` plan is a release that is neither running nor over,
    and the next lock attempt reads that as contention.

    Reservations are released by the plan's own status: `cancelled` is in
    fan_in.RESERVATION_RELEASING_STATUSES, so the members are freed by the same
    write that ends the plan rather than by a second pass that could fail
    separately.
    """
    entry = read_entry(release_plan_uid, files_dir)
    if entry is None:
        raise LockRefused(f"release-plan {release_plan_uid} does not resolve")
    fm = entry["frontmatter"]
    if fm.get("type") != "release-plan":
        raise LockRefused(
            f"{release_plan_uid} is type {fm.get('type')!r}, not a release-plan"
        )
    if not str(reason or "").strip():
        raise LockRefused(
            "abandonment requires a reason. The record outlives everyone who "
            "remembers why, and an unexplained cancellation is indistinguishable "
            "from a mistake."
        )

    status = str(fm.get("status") or "").strip().lower()
    release_uid = str(fm.get("release_entry_uid") or "").strip()
    activation_uid = str(fm.get("release_activation_uid") or "").strip()
    run_uid = str(fm.get("release_pipeline_run_uid") or "").strip()
    release_entry = read_entry(release_uid, files_dir) if release_uid else None

    shipped = _shipped_evidence(release_entry)
    if shipped:
        raise LockRefused(
            f"release-plan {release_plan_uid} cannot be abandoned: {shipped}. "
            "After shipment the cure is forward-only compensation, never "
            "retracting a record of something that already happened in public."
        )

    if status not in {"locked", "cancelled"}:
        raise LockRefused(
            f"release-plan {release_plan_uid} is status {status!r}; only a locked "
            "plan has a transaction to abandon (and an already-cancelled one "
            "replays as a no-op)"
        )

    at = time.strftime("%Y-%m-%d")
    # An exact retry reuses the recorded receipt rather than minting a second
    # one from today's date, so replay is byte-identical and not merely similar.
    receipt = str(fm.get("abandon_receipt") or "").strip() or _abandon_receipt(
        release_plan_uid, reason, abandoned_by, at
    )
    recorded_reason = str(fm.get("abandon_reason") or "").strip() or reason
    recorded_at = str(fm.get("abandoned_at") or "").strip() or at
    recorded_by = str(fm.get("abandoned_by") or "").strip() or abandoned_by

    plan = lt.LockPlan(kind="release-plan-abandon", subject_uid=release_plan_uid,
                       actor=abandoned_by)
    plan.notes = {
        "abandon_receipt": receipt,
        "abandon_reason": recorded_reason,
        "release_entry_uid": release_uid,
        "release_activation_uid": activation_uid,
        "release_pipeline_run_uid": run_uid,
    }

    shared = {
        "abandoned_by": recorded_by,
        "abandoned_at": recorded_at,
        "abandon_reason": recorded_reason,
        "abandon_receipt": receipt,
    }

    def _terminate(uid: str, role: str, extra: Optional[dict] = None) -> None:
        """Patch one correlated record to its terminal state, if it is not there."""
        if not uid:
            return
        record = read_entry(uid, files_dir)
        if record is None:
            return
        target = dict(ABANDON_TERMINAL_STATES[role], **shared, **(extra or {}))
        patched = _patch_plan_frontmatter(record["raw"], target)
        # Byte equality is the whole idempotency guard, deliberately the only
        # one. An earlier version also pre-checked whether each field already
        # held its target value, which read like a safeguard and was dead: an
        # already-terminal record patches to identical bytes, so this line
        # caught it anyway. Two guards where one decides means a mutation to
        # either survives, and the suite cannot tell you which one is load-
        # bearing.
        if patched != record["raw"]:
            plan.patch(record["path"], record["raw"], patched)

    root_uid = ""
    if activation_uid:
        activation = read_entry(activation_uid, files_dir)
        if activation is not None:
            root_uid = str(
                activation["frontmatter"].get("activation_root_uid")
                or activation["frontmatter"].get("activation_root_project")
                or ""
            ).strip()

    _terminate(release_plan_uid, "plan")
    _terminate(activation_uid, "activation")
    _terminate(run_uid, "run")
    _terminate(root_uid, "root", {"final_commit": receipt})
    _terminate(release_uid, "release_entry")
    return plan


def abandon_release_plan(release_plan_uid: str, abandoned_by: str, reason: str,
                         files_dir: Path = VAULT_FILES) -> dict:
    """Plan and apply one abandonment. Returns the applied summary."""
    with lt.exclusive_workspace_lock(timeout_s=30.0):
        plan = plan_release_abandon(release_plan_uid, abandoned_by, reason, files_dir)
        if not plan.operations:
            # Every record is already terminal. An exact retry writes nothing —
            # not "writes the same bytes again", which would still touch mtimes
            # and journal a second transaction over a finished one.
            return {"applied": False, "no_op": True, **plan.notes}
        journal = lt.apply_plan(plan)
        return {"applied": True, "no_op": False, "journal": str(journal), **plan.notes}


_MINT_TOOL_MODULE = None


def _mint_tool():
    """Load tropo-mint-id.py lazily (its filename is not importable) for the
    studio-identity manifest read composite minting requires."""
    global _MINT_TOOL_MODULE
    if _MINT_TOOL_MODULE is None:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "mint_id_module_for_release_lock", Path(__file__).resolve().parent / "tropo-mint-id.py")
        _MINT_TOOL_MODULE = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_MINT_TOOL_MODULE)
    return _MINT_TOOL_MODULE


def _mint_uid(files_dir: Path, exclude: Optional[set] = None) -> str:
    """Route through the AUTHORITY mint shape (3d430852): composite when the
    generation constant says 12, reading the studio-identity manifest
    (refuse-if-absent); the legacy flat 8-hex before that. Same cure as the
    dev-spec lock's twin — this uuid4 literal was the flip census's second
    missed site (found by test_release_plan_lock_end_to_end at the flip)."""
    import sys as _sys
    import uuid
    _here = Path(__file__).resolve().parent
    if str(_here) not in _sys.path:
        _sys.path.insert(0, str(_here))
    from lib import governed_path as _gp
    taken = {p.stem for p in files_dir.glob("*.md")} | (exclude or set())
    if _gp.MINT_HEX_LEN == 12:
        _mintmod = _mint_tool()
        identity = _mintmod.read_studio_identity(root=files_dir.parent.parent)
        prefix = str(identity["mint_prefix"])
        if not _gp.is_composite_mint_prefix(prefix):
            raise _mintmod.StudioIdentityError(
                f"studio-identity manifest mint_prefix {prefix!r} is not the "
                "4-hex composite shape — the release lock cannot mint "
                "composite identities against it; re-issue per 3d430852")
        while True:
            candidate = _gp.composite_uid(prefix)
            if candidate not in taken and UID_RE.match(candidate):
                return candidate
    while True:
        candidate = uuid.uuid4().hex[:8]
        if candidate not in taken and UID_RE.match(candidate):
            return candidate


def _resolve_step_uids(root_uid: str, files_dir: Path) -> list:
    """The release graph's step UIDs, in declaration order.

    Walks the root's children rather than the index: the run's snapshot must
    describe the definition on disk at ignition, and the index is per-machine
    derived state that may not have been rebuilt.
    """
    seen: list = []
    stack = [root_uid]
    visited = set()
    while stack:
        uid = stack.pop(0)
        if uid in visited:
            continue
        visited.add(uid)
        entry = read_entry(uid, files_dir)
        if entry is None:
            continue
        fm = entry["frontmatter"]
        children = [str(c) for c in (fm.get("children") or [])
                    if UID_RE.match(str(c))]
        if uid != root_uid and not children:
            seen.append(uid)
        stack.extend(children)
    return seen


def _render_run(uid: str, activation_uid: str, plan_uid: str, actor: str,
                run_name: str, snapshot, release_uid: str = '', saga_id: str = '',
                root_uid: str = '') -> str:
    today = time.strftime("%Y-%m-%d")
    return f"""---
uid: {json.dumps(str(uid))}
type: pipeline-run
title: "Release run {run_name}"
description: "The single immutable release run opened by the lock of release-plan {plan_uid}."
status: active
state: active
owner: {actor}
pipeline: {RELEASE_PIPELINE_UID}
pipeline_version: '{snapshot.pipeline_version}'
declaration_digest: '{snapshot.digest}'
activation: '{activation_uid}'
activation_root_uid: '{root_uid}'
substrate_authored_by: '{activation_uid}'
release_plan_uid: '{plan_uid}'
release_entry_uid: '{release_uid}'
saga_id: '{saga_id}'
run_folder: 'vault/pipeline-runs/{run_name}'
created: '{today}'
modified: '{today}'
created_by: {actor}
schema_version: 2
governed_by: 8dd772a0
---

# {run_name}

Immutable release run. Its declaration snapshot is fixed at open; the engine
reports definition drift and never heals it (0a0a6777 §1).
"""


#: This tool's own registered uid (its frontmatter `uid:`), so scope_locked's
#: emitter names itself the way every non-agent emitter in this studio does.
TOOL_UID = "6a41f0c9"


def _emit_scope_locked(release_plan_uid: str, notes: dict, files_dir: Path) -> None:
    """v1.91 S2 AC1/AC5 (3fb41c99). Argus A155's ruling: scope_locked is the
    fact that AUTHORIZED the run to exist, not an event OF the run -- Mike
    locking a release's scope is principal authority, and principal
    authority goes on the studio event bus (2fae6312's design intent), not
    into the run's own pre-bootstrap journal seed. Appending it there is
    exactly what collided with 9e7003b1.py's bootstrap-adoption gate; that
    gate's invariant (a fresh lock-seeded run carries exactly one adoptable
    event) is untouched.

    Called only after apply_plan() durably commits -- never announce a lock
    that did not land. Best-effort: a broken emitter costs the crew a
    notification, never the lock itself (same swallow-everything stance as
    tropo-lineage.py's own crew announce()). `release_plan_uid` comes from
    the caller's own parameter, not `notes` -- the lock never stashes the
    subject uid it was already given.

    `files_dir` derives the studio root the SAME way `plan_release_lock`'s
    own governed-file writes already do, rather than resolving from this
    module's own `__file__` -- test_release_plan_lock_end_to_end.py loads
    this module directly from its real production path (a legitimate,
    different isolation strategy than temp_studio.py's file-copying: it
    redirects every write via `files_dir`/`runs_dir` parameters and keeps
    the module itself pointed at production). A `__file__`-relative
    resolution ignores that redirection and writes through the REAL
    vault/tools/tropo-emit-event.py against the REAL event bus -- found
    live: 40 stray rows of this event landed in production
    vault/events/streams/ during this fix's own test runs before this
    parameter existed. Cleaned up; not repeatable now.
    """
    data = {
        "saga_id": notes.get("saga_id", ""),
        "release_plan_uid": release_plan_uid,
        "activation_uid": notes.get("activation_uid", ""),
        "activation_root_uid": notes.get("activation_root_uid", ""),
        "pipeline_run_uid": notes.get("release_pipeline_run_uid", ""),
        "release_entry_uid": notes.get("release_entry_uid", ""),
    }
    studio_root = files_dir.resolve().parents[1]
    tool = studio_root / "vault" / "tools" / "tropo-emit-event.py"  # emit-event
    if not tool.is_file():
        return
    try:
        subprocess.run(
            [sys.executable, str(tool), "--type", "tropo.release.scope_locked",
             "--source", "/tools/tropo-lock-release-plan", "--source-uid", TOOL_UID,
             "--lifecycle", "evergreen", "--data", json.dumps(data)],
            capture_output=True, text=True, timeout=30, cwd=str(studio_root))
    except Exception:
        pass


def lock_release_plan(release_plan_uid: str, locked_by: str,
                      files_dir: Path = VAULT_FILES,
                      runs_dir: Path = PIPELINE_RUNS) -> tuple[int, str]:
    # The lock spans GATHER through COMMIT, not just the write. The reservation
    # scan inside plan_release_lock decides no rival holds a member; if another
    # ignition can start between that decision and this commit, both decide on
    # stale reads and both claim the same member.
    #
    # It was outside the tool until 2026-08-10 — the tests wrapped it, so they
    # passed while the real CLI path would have refused with "without the
    # workspace lock held". A fixture that supplies what production lacks proves
    # the opposite of what it looks like it proves.
    try:
        with lt.exclusive_workspace_lock():
            # RECOVERY FIRST, inside the same span (argus-a147 NO-GO item 2).
            # A crashed prior attempt may have left half-written substrate that
            # the reservation scan would then read as real. Recovering after the
            # scan, or outside the lock, means planning against a world that is
            # still being repaired. recover_incomplete() had no caller at all
            # until now, so the recovery machinery existed and never ran.
            for report in lt.recover_incomplete():
                print(f"[RECOVERY] {report['journal']}: {report['outcome']} "
                      f"(recovered={len(report['recovered'])}, "
                      f"diverged={len(report['diverged'])})", file=sys.stderr)
                if report["outcome"] == "needs-operator":
                    return 2, (
                        f"REFUSED: an earlier transaction at {report['journal']} "
                        "cannot be recovered automatically — files match neither "
                        "its pre- nor post-state, so something has touched them "
                        "since. Resolve it before locking; proceeding would plan "
                        "against substrate that is still half-written.")

            plan = plan_release_lock(release_plan_uid, locked_by, files_dir, runs_dir)

            if lt.already_applied("release-plan-lock", release_plan_uid, plan):
                return 0, (f"{release_plan_uid} already locked by this exact plan "
                           "(idempotent retry)")
            journal = lt.apply_plan(plan)
            _emit_scope_locked(release_plan_uid, plan.notes, files_dir)
    except (LockRefused, fan_in.FanInRefusal, ignition.IgnitionRefusal) as exc:
        return 1, f"REFUSED: {exc}"
    except lt.LockRefusal as exc:
        return 1, f"REFUSED: {exc}"
    except lt.LockApplyFailure as exc:
        return 2, f"PARTIAL: {exc}"

    return 0, (f"{release_plan_uid} LOCKED members={plan.notes['member_count']} "
               f"fan_in_digest={plan.notes['fan_in_digest'][:12]} journal={journal.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release-plan-uid", required=True)
    parser.add_argument("--check", action="store_true",
                        help="report EVERY unmet lock precondition at once; writes nothing, mints nothing")
    parser.add_argument("--locked-by")
    # Abandonment is a flag on the same tool rather than a separate script: it
    # is the inverse of this transaction and has to know exactly what the lock
    # created. A second tool would drift the moment the lock adds a record.
    parser.add_argument(
        "--abandon", action="store_true",
        help="abandon a locked release plan: cancel the plan, terminate the "
             "activation/run/root/entry, release member reservations",
    )
    parser.add_argument("--abandoned-by")
    parser.add_argument("--reason", help="why this release is being abandoned")
    args = parser.parse_args()

    if not UID_RE.match(args.release_plan_uid):
        print(f"ERROR: --release-plan-uid must be 8-hex; got {args.release_plan_uid!r}",
              file=sys.stderr)
        return 3

    if args.check:
        problems = check_release_lock(args.release_plan_uid, args.locked_by or "check")
        if not problems:
            print(f"CHECK PASS: release-plan {args.release_plan_uid} meets every lock precondition; nothing written")
            return 0
        print(f"CHECK: release-plan {args.release_plan_uid} has {len(problems)} unmet precondition(s); nothing written:")
        for n, p in enumerate(problems, 1):
            print(f"  {n}. {p}")
        return 1
    if args.abandon:
        principal = args.abandoned_by or args.locked_by
        if not principal:
            print("ERROR: --abandon requires --abandoned-by", file=sys.stderr)
            return 3
        if not (args.reason or "").strip():
            print("ERROR: --abandon requires --reason", file=sys.stderr)
            return 3
        try:
            result = abandon_release_plan(
                args.release_plan_uid, principal, args.reason
            )
        except (LockRefused, lt.LockRefusal) as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        except lt.LockApplyFailure as exc:
            print(f"PARTIAL: {exc}", file=sys.stderr)
            return 2
        if result.get("no_op"):
            print(f"{args.release_plan_uid} already abandoned "
                  f"(receipt={result['abandon_receipt'][:12]}); exact retry wrote nothing")
        else:
            print(f"{args.release_plan_uid} ABANDONED "
                  f"receipt={result['abandon_receipt'][:12]} reason={result['abandon_reason']!r}")
        return 0

    if not args.locked_by:
        print("ERROR: --locked-by is required to lock", file=sys.stderr)
        return 3

    code, message = lock_release_plan(args.release_plan_uid, args.locked_by)
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
