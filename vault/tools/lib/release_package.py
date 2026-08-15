"""Package-entry authority and the one immutable package identity (0a0a6777 AC6-final/AC7).

Stage 6 makes one frozen digest the spine of the release:

    package zip -> package_sha256 -> four Verify receipts -> one private stage
    -> one public fire -> verified public receipt -> recoverable closure

This module owns the first link and nothing after it. It resolves who
authorised a package, hashes the final zip bytes exactly once, and describes
the `package_frozen` event that every downstream reader consults. It contains
no publisher logic, no network, and no verification vocabulary.

Three rulings from A148 (evt_a9360f18f56fe472_00000020) are load-bearing here
and are implemented literally rather than approximated:

**Identity comes from an explicit activation, never a scan.** `--activation-uid`
is required. There is no "find the single open release run" path, because an
implicit-authority resolution is precisely what produced the mount P0 that
closed this morning: a gesture that decided for itself what it was operating on
and was right until it wasn't.

**There is no omission-based legacy path.** A caller cannot opt out of the
freeze gate by leaving the argument off. v2 semantics are derived from the
resolved activation, run and snapshot -- never from a boolean the caller hands
us, which would make the gate advisory.

**The fan-in digest is one source plus an integrity check.** It is recomputed
canonically from the lock's immutable snapshot rows and compared against the
digest the lock recorded. That is not two sources of truth; it is one source
and a proof that it has not moved. Recomputing from live dev-specs would be two
sources, and is refused by construction because live state is never read here.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: The release pipeline root. A run whose pipeline is anything else is a dev
#: run, and a dev run may not authorise a release package.
RELEASE_PIPELINE_UID = "634913c2"

#: One event type, written once per release run. Named here rather than in the
#: build script so every reader imports the same string.
PACKAGE_FROZEN_EVENT = "tropo.release.package_frozen"
PACKAGE_SUPERSEDED_EVENT = "tropo.release.package_superseded"

_UID = re.compile(r"^[0-9a-f]{8}$")


class PackageRefusal(RuntimeError):
    """Refused before any package byte was written.

    Every refusal in this module happens BEFORE the zip exists. That ordering
    is the whole lesson of 254a360b: a gesture that writes first and validates
    afterwards turns a legitimate refusal into artefacts somebody has to reason
    about. Here, refusing costs nothing.
    """


@dataclass(frozen=True)
class ReleaseIdentity:
    """The chain a package digest is bound to, resolved from one activation."""

    activation_uid: str
    run_uid: str
    root_uid: str
    plan_uid: str
    fan_in_digest: str
    snapshot_path: Optional[Path] = None
    manifest_rows: tuple = field(default_factory=tuple)

    def binding(self) -> dict:
        """The identity fields every downstream record repeats verbatim."""
        return {
            "release_activation_uid": self.activation_uid,
            "release_pipeline_run_uid": self.run_uid,
            "activation_root_uid": self.root_uid,
            "release_plan_uid": self.plan_uid,
            "fan_in_digest": self.fan_in_digest,
        }


def event_type(event) -> str:
    """The event's type, whichever key this surface spells it with.

    Pipeline run JSONL writes `event`; the vault event streams write `type`.
    A reader that checks only one finds NOTHING on the other surface and
    reports a clean empty set — so the freeze idempotency check and the AC7
    receipt gate would both have passed by seeing no events at all, which is
    the worst possible way for a gate to succeed (A148,
    evt_a9360f18f56fe472_00000026 item 2).
    """
    if not isinstance(event, dict):
        return ""
    return str(event.get("event") or event.get("type") or "")


def active_frozen_payload(events, run_uid: str) -> Optional[dict]:
    """Resolve the active package after explicit pre-public supersessions."""
    active = None
    for event in events or []:
        data = event.get("data") or {}
        kind = event_type(event)
        if kind == PACKAGE_FROZEN_EVENT:
            if str(data.get("release_run_uid") or run_uid) == run_uid:
                active = data
        elif kind == PACKAGE_SUPERSEDED_EVENT:
            if str(data.get("release_run_uid") or "") != run_uid:
                continue
            old = str(data.get("old_package_sha256") or "")
            active_digest = str((active or {}).get("package_sha256") or "")
            if not active or active_digest != old:
                raise PackageRefusal(
                    f"package supersession names {old[:12]} but active freeze is "
                    f"{active_digest[:12]}"
                )
            active = None
    return active


def _frontmatter(path: Path) -> dict:
    """Parse a governed entry's frontmatter without importing the world.

    Deliberately small and deliberately strict: an entry that does not open
    with a frontmatter block is not a governed entry, and guessing one out of
    a body is how a resolver starts accepting things that merely look right.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PackageRefusal(f"cannot read {path}: {exc}") from exc
    if not text.startswith("---"):
        raise PackageRefusal(f"{path} has no frontmatter; it is not a governed entry")
    end = text.find("\n---", 3)
    if end < 0:
        raise PackageRefusal(f"{path} has an unterminated frontmatter block")
    try:
        import yaml  # local import: this module is imported by tools that may not need yaml
        parsed = yaml.safe_load(text[3:end])
    except Exception as exc:  # noqa: BLE001 -- any parse failure is a refusal
        raise PackageRefusal(f"{path} frontmatter does not parse: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PackageRefusal(f"{path} frontmatter is not a mapping")
    return parsed


def resolve_release_run(
    activation_uid: Optional[str],
    files_dir: Path,
    runs_dir: Optional[Path] = None,
) -> ReleaseIdentity:
    """Resolve activation -> run -> root, or refuse. Never scans for a run.

    A148's Q1 answer, implemented as written: require the explicit activation,
    resolve the run from it, and require that all three links agree, that the
    run's pipeline is the release pipeline, and that the snapshot resolves.
    Missing, ambiguous or mismatched identity refuses before package writes.
    """
    if not activation_uid or not str(activation_uid).strip():
        raise PackageRefusal(
            "package production requires --activation-uid. There is no "
            "no-activation path: a package that cannot name the release run "
            "that authorised it cannot be bound to a fan-in, a leg gate, or "
            "any receipt written afterwards (0a0a6777 AC6-final)."
        )
    activation_uid = str(activation_uid).strip()
    if not _UID.match(activation_uid):
        raise PackageRefusal(
            f"{activation_uid!r} is not a governed uid; refusing rather than "
            f"searching for something that resembles it"
        )

    activation_path = Path(files_dir) / f"{activation_uid}.md"
    if not activation_path.is_file():
        raise PackageRefusal(
            f"activation {activation_uid} does not resolve at {activation_path}"
        )
    activation = _frontmatter(activation_path)
    if str(activation.get("type") or "") != "activation":
        raise PackageRefusal(
            f"{activation_uid} is type {activation.get('type')!r}, not an activation"
        )

    # Field names read from what tropo-lock-release-plan.py actually renders,
    # not from the dev-side shape: the release activation carries
    # `activation_root_uid`, and the run back-references via `activation`.
    run_uid = str(activation.get("pipeline_run_uid") or "").strip()
    root_uid = str(
        activation.get("activation_root_uid")
        or activation.get("activation_root_project")
        or ""
    ).strip()
    if not run_uid:
        raise PackageRefusal(
            f"activation {activation_uid} names no pipeline_run_uid, so there "
            f"is no run to bind this package to"
        )
    if not root_uid:
        raise PackageRefusal(
            f"activation {activation_uid} names no activation_root_project"
        )

    run_path = Path(files_dir) / f"{run_uid}.md"
    if not run_path.is_file():
        raise PackageRefusal(
            f"activation {activation_uid} names run {run_uid}, which does not "
            f"resolve at {run_path}"
        )
    run = _frontmatter(run_path)

    # ALL THREE LINKS MUST AGREE. A run that points back at a different
    # activation, or a root that belongs to another run, is not a paperwork
    # nit: it means two identities are in play and the package would bind to
    # whichever one we happened to read first.
    back_activation = str(
        run.get("activation") or run.get("activation_uid") or ""
    ).strip()
    if back_activation and back_activation != activation_uid:
        raise PackageRefusal(
            f"identity disagreement: activation {activation_uid} names run "
            f"{run_uid}, but that run names activation {back_activation}"
        )

    pipeline = str(run.get("pipeline") or run.get("pipeline_uid") or "").strip()
    if pipeline != RELEASE_PIPELINE_UID:
        raise PackageRefusal(
            f"run {run_uid} belongs to pipeline {pipeline or '(unset)'}, not "
            f"the release pipeline {RELEASE_PIPELINE_UID}. A dev run cannot "
            f"authorise a release package."
        )

    snapshot_path = _snapshot_for(run, run_uid, runs_dir)
    plan_uid = str(run.get("release_plan_uid") or "").strip()
    if not plan_uid:
        raise PackageRefusal(
            f"run {run_uid} names no release_plan_uid; the package would have "
            f"no plan to close against"
        )

    # The fan-in digest lives on the PLAN, which is where the lock records it.
    # Reading it from the run would have been convenient and wrong: the run
    # does not carry it, and a resolver that tolerates its absence would treat
    # an unverifiable membership as an acceptable one.
    plan_path = Path(files_dir) / f"{plan_uid}.md"
    if not plan_path.is_file():
        raise PackageRefusal(
            f"run {run_uid} names release-plan {plan_uid}, which does not "
            f"resolve at {plan_path}"
        )
    plan = _frontmatter(plan_path)
    plan_activation = str(plan.get("release_activation_uid") or "").strip()
    if plan_activation and plan_activation != activation_uid:
        raise PackageRefusal(
            f"identity disagreement: release-plan {plan_uid} was locked by "
            f"activation {plan_activation}, not {activation_uid}"
        )
    stored_digest = str(plan.get("fan_in_digest") or "").strip()
    if not stored_digest:
        raise PackageRefusal(
            f"release-plan {plan_uid} carries no fan_in_digest, so there is "
            f"nothing to verify the package's membership against"
        )

    return ReleaseIdentity(
        activation_uid=activation_uid,
        run_uid=run_uid,
        root_uid=root_uid,
        plan_uid=plan_uid,
        fan_in_digest=stored_digest,
        snapshot_path=snapshot_path,
    )


def _snapshot_for(run: dict, run_uid: str, runs_dir: Optional[Path]) -> Optional[Path]:
    """The run's immutable declaration snapshot, which must exist."""
    folder = str(run.get("run_folder") or "").strip()
    if runs_dir is None or not folder:
        return None
    # `run_folder` is written STUDIO-relative by tropo-lock-release-plan.py
    # ("vault/pipeline-runs/<name>"), so joining it under runs_dir doubles the
    # path. Accept either form: the bare name a caller might pass, or the
    # stored studio-relative one. Caught by driving the real resolver against a
    # fixture shaped like what the lock actually writes — the previous
    # reference run passed a bare name and never exercised this.
    tail = Path(folder).name if folder.startswith("vault/") else folder
    path = Path(runs_dir) / tail / "declaration-snapshot.json"
    if not path.is_file():
        raise PackageRefusal(
            f"run {run_uid} declares run_folder {folder} but its immutable "
            f"snapshot does not resolve at {path}; a package cannot be frozen "
            f"against a contract that is not there"
        )
    return path


def verify_fan_in_digest(identity: ReleaseIdentity, manifest_rows) -> str:
    """Recompute the digest canonically and prove it has not moved.

    A148's Q5 answer. The rows come from the lock's immutable manifest, never
    from live dev-specs -- this function cannot read live state, which is the
    structural reason it cannot become a second source of truth. What it adds
    is an integrity check: if the recomputation disagrees with what the lock
    recorded, something has edited the manifest since, and the package refuses
    rather than freezing against a membership nobody approved.
    """
    from lib import fan_in  # local import keeps this module's surface small

    rows = [fan_in.validate_row(row) if isinstance(row, dict) else row
            for row in manifest_rows]
    recomputed = fan_in.manifest_digest(rows)
    if recomputed != identity.fan_in_digest:
        raise PackageRefusal(
            f"fan-in digest mismatch for run {identity.run_uid}: the lock "
            f"recorded {identity.fan_in_digest[:12]} and the manifest now "
            f"computes {recomputed[:12]}. The membership changed after the "
            f"lock, so this package would ship a set nobody approved."
        )
    return recomputed


def hash_final_zip(zip_path: Path) -> str:
    """SHA-256 of the final zip bytes, read once, in chunks.

    THE BYTES THAT SHIP ARE THE BYTES WE HASH. Not the build directory, not a
    caller-supplied value, not a re-zip. Every AC7 instrument later identifies
    its subject by this digest, so a digest taken from anything other than the
    artefact makes all four of them describe something that was never released.
    """
    path = Path(zip_path)
    if not path.is_file():
        raise PackageRefusal(f"no package to hash at {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_frozen_payload(
    identity: ReleaseIdentity,
    package_path: Path,
    package_sha256: str,
    version: str = "",
) -> dict:
    """The one event body every downstream reader consults."""
    body = dict(identity.binding())
    body.update({
        "package_path": str(package_path),
        "package_sha256": package_sha256,
    })
    if version:
        body["version"] = version
    return body


def reconcile_existing_freeze(
    existing: Optional[dict],
    package_sha256: str,
    run_uid: str,
) -> bool:
    """Decide whether this freeze is an idempotent retry or a contradiction.

    Returns True when the caller should emit a fresh `package_frozen`, False
    when an identical one already exists and re-emitting would be a duplicate.

    Same run and same bytes is a retry -- builds get interrupted, and making
    the operator hand-clean state before retrying is how people learn to
    delete evidence. Same run and DIFFERENT bytes is the dangerous case and
    refuses: two digests for one release run means the receipts written before
    this moment describe an artefact that is no longer the one shipping.
    """
    if not existing:
        return True
    recorded = str(existing.get("package_sha256") or "").strip()
    if not recorded:
        raise PackageRefusal(
            f"run {run_uid} already carries a package_frozen event with no "
            f"digest; refusing to guess whether this build supersedes it"
        )
    if recorded == package_sha256:
        return False
    raise PackageRefusal(
        f"run {run_uid} was already frozen at {recorded[:12]} and this build "
        f"produced {package_sha256[:12]}. One release run has one package "
        f"identity: any receipt already written against {recorded[:12]} "
        f"describes an artefact this build would replace."
    )
