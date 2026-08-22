#!/usr/bin/env python3
"""tropo-apply-image — the v1.90 lift-and-replace update engine (ea09fc6e).

PLAN computes replace/delete/skip from declared inputs and writes nothing.
The three sets derive ONLY from: (a) the new image, (b) the installed
version's image manifest, (c) the enumerated never-touch list. The
delete-set is NEVER computed by scanning the studio — that is what makes
user content structurally unreachable rather than defended.

APPLY (built in the phases that follow) backs up everything it will touch,
then executes the list mechanically over a fixed total.

The box is the list: a file is Tropo's iff it appears in a shipped image
manifest. Customer files were never in any box, so the mechanism cannot
name them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from lib import package_state_exclusions  # noqa: E402

IMAGE_MANIFEST_NAME = "tropo-image-manifest.json"


def _image_files(image_dir: Path) -> list[str]:
    """The new image's file list: its own emitted manifest when present
    (the authoritative shipped list), else a walk of the image tree."""
    manifest_path = image_dir / IMAGE_MANIFEST_NAME
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return sorted(payload.get("files", {}))
    return sorted(
        p.relative_to(image_dir).as_posix()
        for p in image_dir.rglob("*") if p.is_file()
    )


def plan(image_dir, studio_dir, prior_manifest) -> dict:
    """Compute the three sets and the fixed total. Writes nothing.

    Mode is full when a prior image manifest resolves, legacy-source
    otherwise: in legacy-source the delete-set is empty and one named WARN
    explains why — warn-safe per deb77758, because a stale OS file left on
    disk is recoverable and halting a customer's only working update path
    over it is not."""
    image_dir = Path(image_dir)
    studio_dir = Path(studio_dir)

    replace = [rel for rel in _image_files(image_dir)
               if not package_state_exclusions.is_studio_state(rel)]

    skip = [rel for rel in _image_files(image_dir)
            if package_state_exclusions.is_studio_state(rel)]

    warnings: list[str] = []
    prior_path = Path(prior_manifest) if prior_manifest else (
        studio_dir / IMAGE_MANIFEST_NAME)
    if prior_path.is_file():
        payload = json.loads(prior_path.read_text(encoding="utf-8"))
        prior_files = set(payload.get("files", {}))
        delete = sorted(
            rel for rel in prior_files - set(replace) - set(skip)
            if not package_state_exclusions.is_studio_state(rel)
        )
        mode = "full"
    else:
        delete = []
        mode = "legacy-source"
        warnings.append(
            f"no prior image manifest at {prior_path} — deletions SKIPPED "
            f"(legacy-source mode): stale OS files may remain and are "
            f"recoverable; full mode begins with the next update")

    return {
        "mode": mode,
        "replace": replace,
        "delete": delete,
        "skip": skip,
        "total": len(replace) + len(delete),
        "warnings": warnings,
    }



class ApplyFailure(RuntimeError):
    """A mid-apply failure, naming the operation index and path. No
    rollback is attempted: the applied prefix stays, the backup stays,
    and the receipt says where it stopped (ea09fc6e AC8)."""


def apply(image_dir, studio_dir, prior_manifest=None, *, version=None):
    """Back up everything the plan touches, then execute it mechanically.

    Backup-everything PRECEDES the first write (AC4); never-touch is
    structurally absent from both sets (AC5); a failure halts with the
    operation named and no rollback (AC8); the receipt carries the backup
    pointer and the image manifest installs as the prior for the next
    update."""
    import shutil
    from datetime import datetime, timezone

    image_dir = Path(image_dir)
    studio_dir = Path(studio_dir)
    result = plan(image_dir, studio_dir, prior_manifest)

    stamp = version or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup_dir = studio_dir / "vault" / "updates" / "backups" / str(stamp)

    # AC4: capture replace-union-delete BEFORE any mutation.
    operations = (
        [("replace", rel) for rel in result["replace"]]
        + [("delete", rel) for rel in result["delete"]]
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    for _, rel in operations:
        target = studio_dir / rel
        if target.is_file():
            destination = backup_dir / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination)

    # Execute mechanically over the fixed total.
    for index, (kind, rel) in enumerate(operations):
        target = studio_dir / rel
        try:
            if kind == "replace":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((image_dir / rel).read_bytes())
            else:
                if target.is_file():
                    target.unlink()
        except OSError as exc:
            raise ApplyFailure(
                f"operation {index} of {result['total']} ({kind} {rel}) "
                f"failed: {exc} — halting; the backup at {backup_dir} is "
                f"intact and inspectable; applied prefix stays (no "
                f"rollback by design)") from exc

    # Install the image's manifest as the PRIOR manifest for the next update.
    image_manifest = image_dir / IMAGE_MANIFEST_NAME
    if image_manifest.is_file():
        shutil.copy2(image_manifest, studio_dir / IMAGE_MANIFEST_NAME)

    receipt = {
        "schema": "tropo.apply-receipt/v1",
        "mode": result["mode"],
        "version": str(stamp),
        "applied_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "total": result["total"],
        "replaced": len(result["replace"]),
        "deleted": len(result["delete"]),
        "skipped_never_touch": result["skip"],
        "warnings": result["warnings"],
        "backup_dir": str(backup_dir),
    }
    return receipt



class MigrationContractError(RuntimeError):
    """An unwired user-content rewriter is riding in the image (AC10)."""


WIRED_MIGRATIONS: frozenset[str] = frozenset()
#: The declared-and-wired set. v1.90 ships EMPTY by Mike-locked ruling:
#: migrate-file-status (3ca544f2) retires rather than wiring under
#: pre-ship pressure — that was the v1.86 failure shape. A future migration
#: is added here AND wired in the same commit, or the image refuses.


def assert_migration_contract(image_dir) -> bool:
    """Every migration playbook in the box is declared and wired, or the
    image refuses to apply. An unwired user-content rewriter riding in the
    box is its own defect (ea09fc6e AC10)."""
    image_dir = Path(image_dir)
    migrations = image_dir / ".tropo" / "playbooks" / "migrations"
    if not migrations.is_dir():
        return True
    for playbook in sorted(migrations.glob("*.playbook.md")):
        if playbook.stem not in WIRED_MIGRATIONS:
            raise MigrationContractError(
                f"migration {playbook.name} rides in the image undeclared "
                f"and unwired — an unwired user-content rewriter is the "
                f"v1.86 failure shape; declare AND wire it, or remove it")
    return True


def bootstrap(image_dir, studio_dir, prior_manifest=None):
    """AC7: the applier that executes is the one from the NEW image.

    Copies the image's own tropo-apply-image.py to a temp path and runs IT
    (subprocess) with apply semantics — a studio whose installed applier is
    the retired delta engine still receives new semantics. Returns the
    receipt the NEW applier wrote."""
    import shutil
    import subprocess
    import tempfile

    image_dir = Path(image_dir)
    studio_dir = Path(studio_dir)
    assert_migration_contract(image_dir)

    new_applier = image_dir / "vault" / "tools" / "tropo-apply-image.py"
    if not new_applier.is_file():
        raise ApplyFailure(
            "the image carries no applier — bootstrap requires "
            "vault/tools/tropo-apply-image.py in the new image")

    with tempfile.TemporaryDirectory(prefix="v190-bootstrap-") as staging:
        staged = Path(staging) / "tropo-apply-image.py"
        shutil.copy2(new_applier, staged)
        command = [
            sys.executable, str(staged), "apply",
            "--image", str(image_dir),
            "--studio", str(studio_dir),
        ]
        if prior_manifest:
            command += ["--prior-manifest", str(prior_manifest)]
        # The staged applier's __file__ lives in a bare temp dir, so its
        # own _TOOLS resolution cannot find lib/ — the image SHIPS the lib,
        # so put the image's tools dir on the subprocess path explicitly.
        import os
        environment = dict(os.environ)
        image_tools = str(image_dir / "vault" / "tools")
        existing = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = (
            image_tools + (os.pathsep + existing if existing else ""))
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=600,
            env=environment)
        if completed.returncode != 0:
            raise ApplyFailure(
                f"bootstrapped applier failed ({completed.returncode}): "
                f"{completed.stderr.strip()[:400]}")
        # The receipt is the new applier's stdout (it prints exactly the
        # one JSON document, multi-line by indent).
        return json.loads(completed.stdout)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Lift-and-replace update engine: plan (writes nothing), "
                    "then apply (mechanical, backed up, over a fixed total).")
    sub = parser.add_subparsers(dest="command", required=True)
    plan_p = sub.add_parser("plan", help="compute the operation list; write nothing")
    plan_p.add_argument("--image", required=True, dest="image_dir")
    plan_p.add_argument("--studio", required=True, dest="studio_dir")
    plan_p.add_argument("--prior-manifest", default=None, dest="prior_manifest")
    apply_p = sub.add_parser("apply", help="back up, then execute the list")
    apply_p.add_argument("--image", required=True, dest="image_dir")
    apply_p.add_argument("--studio", required=True, dest="studio_dir")
    apply_p.add_argument("--prior-manifest", default=None, dest="prior_manifest")
    boot_p = sub.add_parser(
        "bootstrap", help="run the NEW image's own applier (staged)")
    boot_p.add_argument("--image", required=True, dest="image_dir")
    boot_p.add_argument("--studio", required=True, dest="studio_dir")
    boot_p.add_argument("--prior-manifest", default=None, dest="prior_manifest")
    args = parser.parse_args(argv)

    if args.command == "plan":
        result = plan(args.image_dir, args.studio_dir, args.prior_manifest)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "apply":
        receipt = apply(args.image_dir, args.studio_dir,
                        args.prior_manifest)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.command == "bootstrap":
        receipt = bootstrap(args.image_dir, args.studio_dir,
                            args.prior_manifest)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
