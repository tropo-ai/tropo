"""What both ignitions write (0a0a6777 AC2/AC4; argus-a147 NO-GO item 4).

AC2 asks the dev lock for "one activation/root plus one pipeline-run/run-folder
containing immutable hashes of the spec, ACs, committed substrate, and full
declarations". AC4 asks the release lock for the symmetric thing. Contract §2
calls them a pair, so the snapshot authoring lives here once and both locks
instantiate it — otherwise "symmetric" is an aspiration maintained by hand.

THREE THINGS THE FIRST VERSION GOT WRONG, all caught in review:

  no activation ROOT      an activation without its root project leaves the
                          cycle with nothing to archive at close, which is the
                          Rule 12 bookend
  no declaration snapshot the whole point of §1 is that a started run executes
                          its OWN declarations. A run opened without them has
                          no snapshot to execute and falls back to whatever the
                          definition says today — the exact contract-swap §1
                          forbids, reintroduced by the ignition itself
  hardcoded version 2.0   the release root is version 1.0.0 and status draft.
                          Stamping 2.0 on a run of a 1.0.0 root makes the run's
                          own record of what it is executing false

The version is read from the root, never assumed, and a root that is not
active or approved cannot be ignited.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

#: A pipeline root may only be ignited from these. `draft` is excluded on
#: purpose: igniting a draft binds real work to a definition its author has not
#: finished, and the run's immutable snapshot then preserves that half-written
#: contract for the life of the cycle.
IGNITABLE_ROOT_STATUSES = frozenset({"active", "locked", "approved"})


class IgnitionRefusal(Exception):
    """A precondition for opening a run is false."""


@dataclass(frozen=True)
class DeclarationSnapshot:
    """The full step declarations a run is opened against, and their digest.

    The digest is over the ORDERED, fully-resolved declarations, so a run can
    later prove which contract it started under rather than asserting it.
    """

    pipeline_uid: str
    pipeline_version: str
    steps: tuple
    digest: str
    step_digests: "dict | None" = None
    bytes_pinned: bool = False
    #: The resolved declaration BYTES, so the run can execute the pinned
    #: contract after its sources are edited or deleted. Hashes prove this
    #: content is what was pinned; the content is what runs.
    declarations: "dict | None" = None

    def as_dict(self) -> dict:
        return {
            "pipeline_uid": self.pipeline_uid,
            "pipeline_version": self.pipeline_version,
            "declared_steps": list(self.steps),
            "declaration_digest": self.digest,
            "step_content_digests": self.step_digests or {},
            "bytes_pinned": self.bytes_pinned,
            "declarations": self.declarations or {},
        }


def snapshot_declarations(
    root_uid: str,
    read_entry: Callable[[str], Optional[dict]],
    resolve_steps: Callable[[str], list],
    read_bytes: Optional[Callable[[str], Optional[bytes]]] = None,
) -> DeclarationSnapshot:
    """Freeze the pipeline's declarations at ignition, refusing an unfit root.

    BLOCKER 4 (argus-a147): this used to digest the UID LIST and nothing else.
    A UID list pins which steps a run holds and says nothing about what those
    steps SAY — so every step's exit criteria, verification command, trust level
    and dependencies could be rewritten after ignition and the "immutable"
    snapshot would still verify. §1 promises a run executes the declarations it
    started under, and a list of names is not the declarations.

    `read_bytes` supplies each entry's canonical bytes. When it is absent the
    snapshot still records the UID list, but marks itself `bytes_pinned: false`
    so a reader can tell the difference between "the contents matched" and "the
    contents were never captured".
    """
    root = read_entry(root_uid)
    if root is None:
        raise IgnitionRefusal(f"pipeline root {root_uid} does not resolve")
    fm = root.get("frontmatter", root)

    status = str(fm.get("status") or "").strip().lower()
    if status not in IGNITABLE_ROOT_STATUSES:
        raise IgnitionRefusal(
            f"pipeline root {root_uid} is status {status!r}; ignition requires one "
            f"of {sorted(IGNITABLE_ROOT_STATUSES)}. Igniting a draft would bind real "
            "work to an unfinished definition, and the run's immutable snapshot "
            "would then preserve that half-written contract for the whole cycle."
        )

    version = str(fm.get("version") or "").strip()
    if not version:
        raise IgnitionRefusal(
            f"pipeline root {root_uid} declares no version. The run records which "
            "contract it executes; an unversioned root makes that record unfalsifiable."
        )

    steps = tuple(resolve_steps(root_uid))
    if not steps:
        raise IgnitionRefusal(
            f"pipeline root {root_uid} resolves to zero steps. A run opened with no "
            "declarations has no snapshot to execute and would fall back to whatever "
            "the definition says later — the contract swap 0a0a6777 §1 forbids."
        )

    # The CANONICAL CONTENT of the root and every step, not just their digests.
    #
    # argus-a147, second pass: hashes DETECT change and cannot EXECUTE anything.
    # §1 says a started run executes only its immutable declaration snapshot —
    # so if the source entries are edited the run should carry on unaffected,
    # and if they are DELETED it should still be able to run at all. A snapshot
    # of hashes satisfies neither: with the sources gone there is nothing left
    # to execute, and the pinned contract dies with the files it merely
    # fingerprinted.
    #
    # The snapshot therefore stores the resolved declaration BYTES. The digests
    # remain, because they are what proves the stored content is the content
    # that was pinned.
    step_digests: dict = {}
    declarations: dict = {}
    bytes_pinned = read_bytes is not None
    if bytes_pinned:
        for uid in (root_uid, *steps):
            raw = read_bytes(uid)
            if raw is None:
                raise IgnitionRefusal(
                    f"pipeline entry {uid} has no readable bytes to pin. A "
                    "declaration snapshot that cannot capture what a step SAYS "
                    "pins only its name, and every exit criterion, verification "
                    "command and dependency could be rewritten after ignition "
                    "while the snapshot still verified."
                )
            step_digests[uid] = hashlib.sha256(raw).hexdigest()
            declarations[uid] = raw.decode("utf-8", errors="replace")

    payload = json.dumps(
        {"pipeline": root_uid, "version": version, "steps": list(steps),
         "step_digests": step_digests},
        sort_keys=True,
    )
    return DeclarationSnapshot(
        pipeline_uid=root_uid,
        pipeline_version=version,
        steps=steps,
        digest=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        step_digests=step_digests,
        bytes_pinned=bytes_pinned,
        declarations=declarations,
    )


class SnapshotRefusal(Exception):
    """A stored snapshot cannot be trusted to be the contract that was pinned."""


def load_snapshot(path: "Path | str") -> dict:
    """Load a run's declarations FROM ITS SNAPSHOT, verifying as it goes.

    This is the loader the runtime was missing. Without it the snapshot was an
    artifact nobody read: execution went on consulting the live vault entries,
    so the pinned contract described the run without governing it.

    Every stored declaration is re-hashed and compared to the digest recorded
    beside it, and the whole payload is checked against the snapshot digest, so
    a snapshot edited after the lock is refused rather than executed. Verifying
    before returning matters more here than anywhere else: this content is about
    to become the contract, and a caller that has to remember to validate will
    eventually not.
    """
    import json as _json
    from pathlib import Path as _Path

    path = _Path(path)
    try:
        body = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SnapshotRefusal(
            f"declaration snapshot at {path} is unreadable ({exc}). A run cannot "
            "execute a contract it cannot load."
        ) from exc

    declarations = body.get("declarations") or {}
    digests = body.get("step_content_digests") or {}
    if not body.get("bytes_pinned") or not declarations:
        raise SnapshotRefusal(
            f"declaration snapshot at {path} stores no declaration content — only "
            "names and hashes. Hashes detect change; they cannot be executed, and "
            "if the source entries are gone there is nothing left to run."
        )

    for uid, digest in digests.items():
        stored = declarations.get(uid)
        if stored is None:
            raise SnapshotRefusal(
                f"snapshot at {path} records a digest for {uid} but stores no "
                "declaration for it")
        actual = hashlib.sha256(stored.encode("utf-8")).hexdigest()
        if actual != digest:
            raise SnapshotRefusal(
                f"snapshot at {path}: stored declaration for {uid} does not match "
                f"its recorded digest ({actual[:12]} vs {digest[:12]}). The "
                "snapshot has been altered since the lock, so it is no longer the "
                "contract the run started under.")

    payload = _json.dumps(
        {"pipeline": body.get("pipeline_uid"),
         "version": body.get("pipeline_version"),
         "steps": list(body.get("declared_steps") or []),
         "step_digests": digests},
        sort_keys=True,
    )
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if expected != body.get("declaration_digest"):
        raise SnapshotRefusal(
            f"snapshot at {path}: its declaration_digest does not match its own "
            "contents. Something has rewritten the snapshot since the lock.")

    return {
        "pipeline_uid": body.get("pipeline_uid"),
        "pipeline_version": body.get("pipeline_version"),
        "declared_steps": list(body.get("declared_steps") or []),
        "declarations": declarations,
        "declaration_digest": body.get("declaration_digest"),
    }


def spec_component_digests(spec_text: str) -> dict:
    """Separate hashes for the acceptance criteria and the committed substrate.

    BLOCKER 4: the input snapshot hashed the whole dev-spec file and stopped
    there. A whole-file hash proves the spec changed and cannot say WHAT
    changed, so it cannot distinguish an editorial fix in the prose from someone
    rewriting the acceptance criteria the run is being judged against. AC2 names
    "spec, ACs, committed substrate" as three things, and they are three because
    they answer three different questions at close.

    Parsed from the frontmatter blocks by name, and each digest is over the
    canonical re-serialisation so that reordering or reformatting the YAML does
    not read as a content change.
    """
    import json as _json

    try:
        import yaml as _yaml
    except ImportError:  # pragma: no cover
        return {}

    parts = spec_text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        frontmatter = _yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}
    if not isinstance(frontmatter, dict):
        return {}

    digests: dict = {}
    for field, label in (("acceptance_criteria", "acceptance_criteria"),
                         ("committed_substrate", "committed_substrate")):
        value = frontmatter.get(field)
        canonical = _json.dumps(value, sort_keys=True, default=str)
        digests[f"{label}_sha256"] = hashlib.sha256(
            canonical.encode("utf-8")).hexdigest()
        digests[f"{label}_present"] = value is not None
    return digests


def input_snapshot(paths_and_labels: list[tuple[str, Path]]) -> dict:
    """Immutable hashes of the inputs a cycle is opened against.

    AC2 names spec, ACs and committed substrate. They are hashed from the file
    on disk rather than from a parsed projection: a projection can change when
    the parser changes, and then the "immutable" hash moves without the input
    moving.
    """
    snapshot: dict = {}
    for label, path in paths_and_labels:
        if not path.is_file():
            raise IgnitionRefusal(
                f"ignition input {label} does not resolve at {path}; a run cannot "
                "record an immutable hash of something that is not there"
            )
        snapshot[f"{label}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def _yaml_scalar(value: str) -> str:
    """Render arbitrary text as a YAML scalar that survives its own content.

    Wrapping free text in single quotes and hoping is what produced an
    unparseable activation: Metis's cycle context contained an apostrophe, the
    quote closed early, and `ddc56dab` had to be repaired by hand after the
    lock had already committed it (argus-a148,
    evt_a9360f18f56fe472_00000020).

    JSON string syntax is a subset of YAML's double-quoted scalar, so
    `json.dumps` escapes quotes, colons, backslashes and newlines correctly
    and needs no separate escaping table of ours to drift out of date. It is
    the same device this Studio already uses to emit YAML values safely in
    `tropo-generate-package-operations.py`.

    The failure this prevents is nastier than a bad file. The lock transaction
    is atomic and journalled, so it lands a *valid* transaction containing an
    *invalid* record: nothing to roll back, nothing refused, and the damage is
    only visible the next time someone parses the entry.
    """
    return json.dumps(str(value))


def render_activation(
    activation_uid: str, root_uid: str, run_uid: str, pipeline_uid: str,
    subject_uid: str, subject_kind: str, actor: str, today: str,
    cycle_context: str = "",
) -> str:
    """The activation entry, authored INSIDE the lock transaction.

    WHY NOT SHELL OUT TO pipeline-activate.py (argus-a147, stage-4 blocker 1).
    The dev lock used to invoke it as a subprocess before taking the lock. Two
    consequences, both fatal to the transaction:

      it writes IMMEDIATELY and outside the journal, so a later refusal left an
      activation and a root on disk with nothing describing them — the exact
      partial identity the journal exists to prevent

      it authors its OWN `activation_root_project`, and the ignition then
      authored a second one, so a successful lock produced one activation and
      TWO roots

    A subprocess cannot participate in a transaction. So the activation is
    authored here, as one operation among the others, and either the whole
    ignition lands or none of it does.

    The field shape deliberately matches what pipeline-activate.py emits for a
    dev activation — `agent_class: pipeline`, `activation_root_project`,
    `member_of` the root — so `check_dev_spec_activation_coupling` and every
    other reader sees what it already expects. `author` records the real writer
    rather than claiming to be pipeline-activate.py, because a record that lies
    about its own provenance is worse than one that is merely different.
    """
    cycle_line = (
        f"cycle_context: {_yaml_scalar(cycle_context)}\n" if cycle_context else ""
    )
    subject_field = subject_kind.replace("-", "_") + "_uid"
    return f"""---
uid: {_yaml_scalar(activation_uid)}
type: activation
title: "Activation — {subject_kind} {subject_uid}"
description: "Opened atomically by the lock gesture as one indivisible act with the root, the run and the spec flip (0a0a6777 AC2/AC4)."
status: active
state: active
owner: {_yaml_scalar(actor)}
agent_class: pipeline
# action_bootstrap gates on THIS field; without it the runtime refuses
# the activation the lock just opened.
activation_class: pipeline
agent_root: {_yaml_scalar(pipeline_uid)}
pipeline: {_yaml_scalar(pipeline_uid)}
pipeline_uid: {_yaml_scalar(pipeline_uid)}
pipeline_run_uid: '{run_uid}'
activation_root_project: '{root_uid}'
{subject_field}: '{subject_uid}'
activated_by: {_yaml_scalar(actor)}
activated_at: '{today}'
member_of:
  - {_yaml_scalar(root_uid)}
{cycle_line}author: lock-gesture
created: '{today}'
modified: '{today}'
created_by: {_yaml_scalar(actor)}
schema_version: 2
governed_by: 8dd772a0
tags: [activation, pipeline-class]
---

# Activation — {subject_kind} {subject_uid}

Authored inside the lock transaction, not by a subprocess ahead of it. The
activation, its root, its run and the subject's own status flip are one plan:
either all of them land or none of them do.
"""


def render_activation_root(
    root_uid: str, activation_uid: str, subject_uid: str, subject_kind: str,
    actor: str, today: str, pipeline_uid: str,
) -> str:
    """The activation ROOT project — the thing Rule 12 archives at close.

    Without it a cycle has an activation and nothing to archive, so the closing
    bookend has no subject and `final_commit` has nowhere to land.
    """
    return f"""---
uid: {_yaml_scalar(root_uid)}
type: project
title: "Activation Root — {subject_kind} {subject_uid}"
description: "Activation root authored atomically at ignition (0a0a6777 AC2/AC4). Rule 12 archives this at terminal close and stamps final_commit here."
status: active
state: active
owner: {_yaml_scalar(actor)}
activated_by_pipeline: {_yaml_scalar(pipeline_uid)}
activation_uid: '{activation_uid}'
{subject_kind.replace('-', '_')}_uid: '{subject_uid}'
created: '{today}'
modified: '{today}'
created_by: {_yaml_scalar(actor)}
schema_version: 2
governed_by: 8dd772a0
---

# Activation Root — {subject_kind} {subject_uid}

Authored at step 0 by the lock gesture, per pipeline capsule Rule 10. Closed and
stamped with `final_commit` at terminal verification, per Rule 12.
"""
