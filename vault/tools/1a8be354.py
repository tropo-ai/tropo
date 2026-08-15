#!/usr/bin/env python3
"""
---
uid: 1a8be354
title: tropo-export-public-snapshot — Local Public Snapshot Exporter
name: tropo-export-public-snapshot
type: tool
status: active
state: active
owner: orpheus
domain: Deterministic deny-by-default local export of allowlisted public release facts.
spawnable_by:
- all-executives
- user
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/1a8be354.py --out PATH [--dry-run] [--force] [--validate]
script_path: vault/tools/1a8be354.py
input:
  type: object
  required:
  - out
  properties:
    out:
      type: string
    dry-run:
      type: boolean
    force:
      type: boolean
    source-commit:
      type: string
      description: Fixture-only commit label; requires --fixture-mode
    fixture-mode:
      type: boolean
      description: Hidden test-only seam requiring sentinel, environment opt-in, and no origin
    validate:
      type: boolean
output:
  type: object
  properties:
    source_commit:
      type: string
      description: Local operator evidence only; never serialized into bundle files
    records:
      type: integer
      description: Deduplicated public facts identified only by public_fact_id
    fact_identity:
      type: string
      enum: [public_fact_id]
    bundle_sha256:
      type: string
    overrides_consumed:
      type: array
      maxItems: 0
destructive: false
audit_required: true
writes_scope:
- 02-outbox/web-v4/**
reads_scope:
- vault/events/00-events.jsonl
- vault/events/streams/**
- vault/events/release-receipts/**
- vault/agents/*.md
- vault/files/20495aaf.md
- vault/files/eb8e65c8.md
- vault/tools/1a8be354.py
- vault/tools/lib/public_snapshot.py
- vault/tools/lib/release_receipt.py
- vault/tools/lib/event_identity.py
- vault/tools/lib/tropo_roots.py
- vault/tools/tropo-publish-release.py
- vault/tools/tropo-check-publish-state.py
network_access: false
governance_category: projection
description: Local-only web-v4 Phase 0.6 exporter. Reads a clean, HEAD-bound canonical mixed event union and optional content-addressed verify-live receipts, projects release facts only from matching validated receipts, refuses all v1 overrides, emits fixed-bucket privacy receipts, and performs no network operation.
version: 1.1.0
created: 2026-07-17
created_by: orpheus-o32
modified: 2026-07-17
modified_by: orpheus-o32
schema_version: 2
capsule_version: '1.8'
extraction_scope: ship
governed_by: d5e1b4a3
member_of:
- 4d50b2de
- 4cd50219
- 1157fded
refs:
- 148dd9cc
- 739e423f
- 20495aaf
- eb8e65c8
- dccbcf65
tags:
- tool
- cli
- public-snapshot
- web-v4
- privacy
- local-only
subsystem_hub:
- 8dd772a0
---

## Intent

Build or validate the local web-v4 Public Snapshot Bundle Contract v1. Invoke
it for deny-by-default release-fact projection, not for network publication or
raw event export.

## Invocation Protocol

Run from the repository root:
``python3 vault/tools/1a8be354.py --out 02-outbox/web-v4/<bundle>``.
Add ``--dry-run`` for a zero-write preview, ``--force`` only for a safe
three-file replacement, or ``--validate`` to re-derive an existing bundle.
``--source-commit`` is fixture-only and requires the hidden fixture seam:
an exact sentinel, explicit test environment opt-in, and a Git repo without
``origin``.

## Input / Output

Inputs are the clean HEAD-bound event union, agent identity map, public policy,
and CLI flags declared above. Output is exactly ``manifest.json``,
``release-facts.json``, and ``privacy-receipt.json`` plus a local JSON stdout
summary. Private source commit evidence appears only in that operator summary.

## Governance

Writes are restricted to repository ``02-outbox/web-v4/**``. The tool performs
no network I/O, trusts no label-only event provenance, consumes no v1
overrides, treats governed content-addressed receipts as a governance-authorized,
hash-consistent publisher assertion given a trusted main checkout—not
cryptographic authentication—and refuses dirty sources, unsafe paths, symlinks,
hardlinks, or undeclared output contents. The generated privacy receipt is the
invocation audit evidence.

## Verification

Exit 0 means the in-memory contract and hashes validated. Re-run with
``--validate`` and run
``python3 -m unittest vault.tools.tests.test_public_snapshot_export`` for the
privacy, determinism, source-binding, and filesystem attack matrix.

## Failure Modes

| Exit | Meaning | Response |
|---|---|---|
| 0 | Build, dry-run, or validation succeeded | Inspect stdout and receipt |
| 2 | Contract, source-binding, argument, or filesystem refusal | Correct the named precondition; do not bypass it |
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ``--dry-run writes zero bytes`` includes repository-local bytecode caches.
sys.dont_write_bytecode = True

from lib import public_snapshot


VAULT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_BINDING_PATHS = (
    Path("vault/events/00-events.jsonl"),
    Path("vault/events/streams"),
    Path("vault/events/release-receipts"),
    Path("vault/agents"),
    Path("vault/files/20495aaf.md"),
    Path("vault/files/eb8e65c8.md"),
    Path("vault/tools/1a8be354.py"),
    Path("vault/tools/lib/public_snapshot.py"),
    Path("vault/tools/lib/release_receipt.py"),
    Path("vault/tools/lib/event_identity.py"),
    Path("vault/tools/lib/tropo_roots.py"),
    Path("vault/tools/tropo-publish-release.py"),
    Path("vault/tools/tropo-check-publish-state.py"),
)
OPTIONAL_SOURCE_BINDING_PATHS = frozenset(
    {
        Path("vault/events/streams"),
        Path("vault/events/release-receipts"),
    }
)
FIXTURE_SENTINEL_NAME = ".tropo-public-snapshot-fixture"
FIXTURE_SENTINEL_BYTES = b"tropo-public-snapshot-fixture-v1\n"
FIXTURE_ENV_NAME = "TROPO_PUBLIC_SNAPSHOT_TEST_FIXTURE"


def _run_git(*arguments: str) -> str:
    git_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    git_environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=VAULT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=git_environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise public_snapshot.SnapshotContractError(
            "local git source binding could not be established"
        ) from exc
    return result.stdout


def _require_fixture_seam() -> None:
    root = VAULT_ROOT.resolve()
    git_marker = VAULT_ROOT / ".git"
    try:
        git_metadata = git_marker.lstat()
    except OSError as exc:
        raise public_snapshot.SnapshotContractError(
            "--fixture-mode requires a real local .git directory"
        ) from exc
    if git_marker.is_symlink() or not stat.S_ISDIR(git_metadata.st_mode):
        raise public_snapshot.SnapshotContractError(
            "--fixture-mode requires a real local .git directory"
        )

    sentinel = VAULT_ROOT / FIXTURE_SENTINEL_NAME
    try:
        metadata = sentinel.lstat()
        payload = sentinel.read_bytes()
    except OSError as exc:
        raise public_snapshot.SnapshotContractError(
            "--fixture-mode requires the exact test fixture sentinel"
        ) from exc
    if (
        sentinel.is_symlink()
        or not sentinel.is_file()
        or metadata.st_nlink != 1
        or payload != FIXTURE_SENTINEL_BYTES
    ):
        raise public_snapshot.SnapshotContractError(
            "--fixture-mode sentinel is missing, linked, or invalid"
        )
    if os.environ.get(FIXTURE_ENV_NAME) != "1":
        raise public_snapshot.SnapshotContractError(
            "--fixture-mode requires explicit test environment opt-in"
        )
    try:
        marker_directory = git_marker.resolve(strict=True)
        resolved_git_directory = Path(
            _run_git("rev-parse", "--absolute-git-dir").strip()
        ).resolve(strict=True)
        resolved_git_directory.relative_to(root)
    except (OSError, ValueError) as exc:
        raise public_snapshot.SnapshotContractError(
            "--fixture-mode git directory must resolve inside the fixture root"
        ) from exc
    if resolved_git_directory != marker_directory:
        raise public_snapshot.SnapshotContractError(
            "--fixture-mode git directory does not match the fixture .git directory"
        )
    remotes = set(_run_git("remote").splitlines())
    if "origin" in remotes:
        raise public_snapshot.SnapshotContractError(
            "--fixture-mode is forbidden in a repository with origin"
        )


def _head_commit() -> str:
    return public_snapshot.validate_source_commit(
        _run_git("rev-parse", "--verify", "HEAD").strip()
    )


def _require_governed_main() -> str:
    """Require the checked-out branch itself to be synchronized governed main."""
    branch = _run_git("branch", "--show-current").strip()
    if branch != "main":
        raise public_snapshot.SnapshotContractError(
            "normal public snapshot requires the actual checked-out branch main"
        )
    head = _head_commit()
    try:
        origin_main = public_snapshot.validate_source_commit(
            _run_git(
                "rev-parse",
                "--verify",
                "refs/remotes/origin/main",
            ).strip()
        )
    except public_snapshot.SnapshotContractError as exc:
        raise public_snapshot.SnapshotContractError(
            "normal public snapshot requires a valid origin/main tracking ref"
        ) from exc
    if head != origin_main:
        raise public_snapshot.SnapshotContractError(
            "normal public snapshot requires HEAD to equal origin/main"
        )
    return head


def _require_clean_sources() -> None:
    status = _run_git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *(path.as_posix() for path in SOURCE_BINDING_PATHS),
    )
    if status:
        raise public_snapshot.SnapshotContractError(
            "public snapshot source paths must be clean relative to HEAD"
        )


def _source_file_payloads() -> list[tuple[str, bytes]]:
    records: list[tuple[str, bytes]] = []
    for relative in SOURCE_BINDING_PATHS:
        source = VAULT_ROOT / relative
        if not source.exists() and relative in OPTIONAL_SOURCE_BINDING_PATHS:
            continue
        if source.is_symlink() or not source.exists():
            raise public_snapshot.SnapshotContractError(
                "required public snapshot source is missing or symlinked"
            )
        if source.is_dir():
            for child in source.rglob("*"):
                if child.is_symlink():
                    raise public_snapshot.SnapshotContractError(
                        "public snapshot source trees cannot contain symlinks"
                    )
                if child.is_file():
                    try:
                        payload = child.read_bytes()
                    except OSError as exc:
                        raise public_snapshot.SnapshotContractError(
                            "public snapshot source changed while being read"
                        ) from exc
                    records.append(
                        (child.relative_to(VAULT_ROOT).as_posix(), payload)
                    )
                elif child.exists() and not child.is_dir():
                    raise public_snapshot.SnapshotContractError(
                        "public snapshot source contains a non-regular entry"
                    )
        elif source.is_file():
            try:
                payload = source.read_bytes()
            except OSError as exc:
                raise public_snapshot.SnapshotContractError(
                    "public snapshot source changed while being read"
                ) from exc
            records.append((relative.as_posix(), payload))
        else:
            raise public_snapshot.SnapshotContractError(
                "public snapshot source must be a regular file or directory"
            )

    return sorted(records, key=lambda item: item[0])


def _git_blob_id(payload: bytes, object_format: str) -> str:
    framed = f"blob {len(payload)}\0".encode("ascii") + payload
    if object_format == "sha1":
        return hashlib.sha1(framed).hexdigest()
    if object_format == "sha256":
        return hashlib.sha256(framed).hexdigest()
    raise public_snapshot.SnapshotContractError(
        "unsupported git object format for source binding"
    )


def _require_sources_match_head(records: list[tuple[str, bytes]]) -> None:
    tree_output = _run_git(
        "ls-tree",
        "-r",
        "--full-tree",
        "HEAD",
        "--",
        *(path.as_posix() for path in SOURCE_BINDING_PATHS),
    )
    head_blobs: dict[str, str] = {}
    for line in tree_output.splitlines():
        try:
            metadata, relative = line.split("\t", 1)
            _mode, object_type, object_id = metadata.split()
        except ValueError as exc:
            raise public_snapshot.SnapshotContractError(
                "git returned an ambiguous source tree"
            ) from exc
        if object_type != "blob" or relative in head_blobs:
            raise public_snapshot.SnapshotContractError(
                "source tree contains a non-file or duplicate git entry"
            )
        head_blobs[relative] = object_id

    working = {relative: payload for relative, payload in records}
    if len(working) != len(records) or set(working) != set(head_blobs):
        raise public_snapshot.SnapshotContractError(
            "public snapshot source file set does not exactly match HEAD"
        )
    object_format = _run_git("rev-parse", "--show-object-format").strip()
    for relative, payload in records:
        if _git_blob_id(payload, object_format) != head_blobs[relative]:
            raise public_snapshot.SnapshotContractError(
                "public snapshot source bytes do not exactly match HEAD"
            )


def _source_tree_digest(records: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for relative_text, payload in records:
        relative = relative_text.encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _capture_source_binding() -> tuple[str, str]:
    commit = _require_governed_main()
    _require_clean_sources()
    records = _source_file_payloads()
    _require_sources_match_head(records)
    digest = _source_tree_digest(records)
    _require_clean_sources()
    if _require_governed_main() != commit:
        raise public_snapshot.SnapshotContractError(
            "HEAD changed while source binding was captured"
        )
    return commit, digest


def _verify_source_binding(binding: tuple[str, str]) -> None:
    commit, digest = binding
    if _require_governed_main() != commit:
        raise public_snapshot.SnapshotContractError(
            "HEAD changed during public snapshot discovery"
        )
    _require_clean_sources()
    records = _source_file_payloads()
    _require_sources_match_head(records)
    if _source_tree_digest(records) != digest:
        raise public_snapshot.SnapshotContractError(
            "public snapshot sources changed during discovery"
        )
    _require_clean_sources()


def _resolve_source_commit(
    override: str | None, *, fixture_mode: bool
) -> str:
    if fixture_mode:
        _require_fixture_seam()
        if override is None:
            raise public_snapshot.SnapshotContractError(
                "--fixture-mode requires an explicit --source-commit"
            )
        return public_snapshot.validate_source_commit(override)
    if override is not None:
        raise public_snapshot.SnapshotContractError(
            "--source-commit is fixture-only and requires --fixture-mode"
        )
    return _require_governed_main()


def _generated_at() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _preflight_output(output: Path, *, force: bool) -> None:
    if output.is_symlink():
        raise public_snapshot.SnapshotContractError(
            "output directory cannot be a symbolic link"
        )
    if output.exists() and not output.is_dir():
        raise public_snapshot.SnapshotContractError(
            "output path exists and is not a directory"
        )
    if not output.exists():
        return
    entries = list(output.iterdir())
    if entries and not force:
        raise public_snapshot.SnapshotContractError(
            "output directory is non-empty; pass --force to replace a v1 bundle"
        )
    if force:
        for entry in entries:
            metadata = entry.lstat()
            if (
                entry.name not in public_snapshot.BUNDLE_FILENAMES
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
            ):
                raise public_snapshot.SnapshotContractError(
                    "--force only replaces unlinked regular v1 bundle files"
                )


def _check_write_directory(output: Path) -> None:
    if output.is_symlink() or not output.is_dir():
        raise public_snapshot.SnapshotContractError(
            "output changed into a non-directory or symbolic link"
        )
    for entry in output.iterdir():
        metadata = entry.lstat()
        if (
            entry.name not in public_snapshot.BUNDLE_FILENAMES
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            raise public_snapshot.SnapshotContractError(
                "output acquired an unsafe, linked, or unexpected entry"
            )


def _mkdir_without_symlinks(
    output: Path, *, source_event_paths: tuple[str, ...]
) -> None:
    missing: list[Path] = []
    cursor = output
    while not cursor.exists():
        if cursor.is_symlink():
            raise public_snapshot.SnapshotContractError(
                "output parent chain contains a symbolic link"
            )
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise public_snapshot.SnapshotContractError(
            "output parent chain does not end in a real directory"
        )
    for directory in reversed(missing):
        os.mkdir(directory, 0o755)
        public_snapshot.assert_safe_output_path(
            VAULT_ROOT, output, source_event_paths=source_event_paths
        )


def _atomic_write(
    output: Path,
    name: str,
    payload: bytes,
    *,
    source_event_paths: tuple[str, ...],
) -> None:
    # Re-evaluate lexical scope and every existing parent immediately before
    # each file replacement.  Directory-fd operations below narrow, but cannot
    # completely eliminate, local filesystem TOCTOU in this stdlib v1.
    checked = public_snapshot.assert_safe_output_path(
        VAULT_ROOT, output, source_event_paths=source_event_paths
    )
    if checked != output:
        raise public_snapshot.SnapshotContractError("output path changed")
    _check_write_directory(output)

    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(output, directory_flags)
    temporary_name = f".{name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    temporary_created = False
    try:
        path_metadata = os.stat(output, follow_symlinks=False)
        fd_metadata = os.fstat(directory_fd)
        if (path_metadata.st_dev, path_metadata.st_ino) != (
            fd_metadata.st_dev,
            fd_metadata.st_ino,
        ):
            raise public_snapshot.SnapshotContractError(
                "output directory changed during write setup"
            )
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        file_flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(
            temporary_name, file_flags, 0o600, dir_fd=directory_fd
        )
        temporary_created = True
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        try:
            target = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            target = None
        if target is not None and (
            not stat.S_ISREG(target.st_mode) or target.st_nlink != 1
        ):
            raise public_snapshot.SnapshotContractError(
                "refusing to replace a linked or non-regular bundle file"
            )
        temporary_metadata = os.stat(
            temporary_name, dir_fd=directory_fd, follow_symlinks=False
        )
        if (
            not stat.S_ISREG(temporary_metadata.st_mode)
            or temporary_metadata.st_nlink != 1
        ):
            raise public_snapshot.SnapshotContractError(
                "temporary bundle file acquired an unsafe hard link"
            )
        latest_path = os.stat(output, follow_symlinks=False)
        if (latest_path.st_dev, latest_path.st_ino) != (
            fd_metadata.st_dev,
            fd_metadata.st_ino,
        ):
            raise public_snapshot.SnapshotContractError(
                "output directory changed before atomic replacement"
            )
        os.replace(
            temporary_name,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temporary_created = False
        os.fsync(directory_fd)
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except OSError:
                pass
        os.close(directory_fd)


def _write_bundle(output: Path, bundle: public_snapshot.SnapshotBundle) -> None:
    _mkdir_without_symlinks(
        output, source_event_paths=bundle.source_event_paths
    )
    # The manifest is the completion marker and is therefore replaced last.
    for name in (
        public_snapshot.RELEASE_FACTS_NAME,
        public_snapshot.PRIVACY_RECEIPT_NAME,
        public_snapshot.MANIFEST_NAME,
    ):
        _atomic_write(
            output,
            name,
            bundle.files[name],
            source_event_paths=bundle.source_event_paths,
        )


def _summary(
    bundle: public_snapshot.SnapshotBundle,
    *,
    dry_run: bool,
    output: Path,
) -> dict:
    receipt = bundle.privacy_receipt
    return {
        "bundle_sha256": bundle.manifest["bundle_sha256"],
        "dry_run": dry_run,
        "fact_identity": "public_fact_id",
        "held_back_buckets": [row["bucket"] for row in receipt["held_back"]],
        "output": str(output),
        "overrides_consumed": [],
        "records": receipt["crossed"]["release_facts"]["count"],
        "release_facts_sha256": receipt["crossed"]["release_facts"]["sha256"],
        "source_commit": bundle.bound_source_commit,
        "validated": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or validate a local public snapshot v1 bundle."
    )
    parser.add_argument(
        "--out",
        required=True,
        metavar="PATH",
        help="Explicit local bundle directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate in memory; write zero bytes.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing directory containing only v1 bundle files.",
    )
    parser.add_argument(
        "--source-commit",
        metavar="40_HEX",
        help="Fixture-only commit label; requires --fixture-mode.",
    )
    parser.add_argument(
        "--fixture-mode",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--validate",
        "--validate-bundle",
        action="store_true",
        help="Validate and source-rederive the existing --out bundle.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_arg = Path(args.out)
    try:
        if args.validate:
            if args.dry_run or args.force:
                raise public_snapshot.SnapshotContractError(
                    "--validate cannot be combined with export-only options"
                )
            source_commit = _resolve_source_commit(
                args.source_commit, fixture_mode=args.fixture_mode
            )
            binding = None if args.fixture_mode else _capture_source_binding()
            if binding is not None and source_commit != binding[0]:
                raise public_snapshot.SnapshotContractError(
                    "normal validation must bind source_commit to current HEAD"
                )
            validation_output = public_snapshot.assert_safe_output_path(
                VAULT_ROOT,
                output_arg,
            )
            result = public_snapshot.validate_bundle_directory(
                validation_output,
                source_root=VAULT_ROOT,
                bound_source_commit=source_commit,
            )
            if binding is not None:
                _verify_source_binding(binding)
            print(
                json.dumps(
                    {
                        "fixture_mode": args.fixture_mode,
                        "output": str(validation_output),
                        "source_commit": source_commit,
                        "valid": True,
                        **result,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0

        source_commit = _resolve_source_commit(
            args.source_commit, fixture_mode=args.fixture_mode
        )
        binding = None if args.fixture_mode else _capture_source_binding()
        if binding is not None:
            if source_commit != binding[0]:
                raise public_snapshot.SnapshotContractError(
                    "normal export must bind source_commit to current HEAD"
                )
            source_commit = binding[0]
        bundle = public_snapshot.discover_public_snapshot(
            VAULT_ROOT,
            source_commit=source_commit,
            generated_at=_generated_at(),
        )
        if binding is not None:
            _verify_source_binding(binding)
        output = public_snapshot.assert_safe_output_path(
            VAULT_ROOT,
            output_arg,
            source_event_paths=bundle.source_event_paths,
        )
        _preflight_output(output, force=args.force)

        # Validate all would-be bytes before the dry-run boundary or any write.
        public_snapshot.validate_bundle_bytes(bundle.files)
        if args.dry_run:
            print(
                json.dumps(
                    _summary(bundle, dry_run=True, output=output),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0

        _write_bundle(output, bundle)
        public_snapshot.validate_bundle_directory(
            output,
            source_root=VAULT_ROOT,
            bound_source_commit=source_commit,
        )
        if binding is not None:
            _verify_source_binding(binding)
        print(
            json.dumps(
                _summary(bundle, dry_run=False, output=output),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except public_snapshot.SnapshotContractError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"REFUSED: local filesystem operation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
