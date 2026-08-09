#!/usr/bin/env python3
"""
---
uid: 2a83b8be
name: verify-authority
type: tool
status: active
owner: argus
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-verify-authority.py"
script_path: vault/tools/tropo-verify-authority.py
created: 2026-07-26
created_by: argus-a142
governed_by: d5e1b4a3
member_of:
  - 8dd772a0
schema_version: 2
title: "verify-authority — Verify activation-bound provenance and anchor reachability"
trigger_description: "Verify commit provenance, derive allowed signers, audit identity collapse, or probe an authority anchor."
---
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from lib.authority_chain import (  # noqa: E402
    AuthorityChainError,
    AuthorityErrorCode,
    collect_commit_signatures,
    detect_key_author_collapse,
    derive_canonical_allowed_signers,
    discover_harness_signer,
    load_canonical_activation_entries,
    probe_anchor_with_positive_control,
    probe_harness_anchor,
    resolve_commit_chain,
    sign_commit,
)


ROOT = Path(__file__).resolve().parents[2]
def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def command_verify(args) -> int:
    result = resolve_commit_chain(
        Path(args.repo).resolve(),
        args.commit,
        require_authority=args.require_authority,
    )
    if args.json:
        _print_json(result.to_dict())
    else:
        print(f"commit: {result.commit}")
        print(f"provenance: {result.provenance}")
        print(f"signature-key: {result.key_fingerprint}")
        print(f"author: {result.author_identity}")
        if result.activation_uid:
            print(
                "activation: "
                f"{result.activation_uid} ({result.agent} {result.generation})"
            )
            print(f"activated-by: {result.activated_by}")
        print(f"authority: {'yes' if result.authority else 'no'}")
        if result.key_custody:
            print(f"key-custody: {result.key_custody}")
        for finding in result.findings:
            print(f"finding: {finding.code.value} — {finding.message}")
    return 0


def command_allowed_signers(args) -> int:
    # Stdout only.  This command intentionally has no --output option: derived
    # signer material must never become a hand-maintained Studio artifact.
    sys.stdout.write(
        derive_canonical_allowed_signers(Path(args.repo).resolve())
    )
    return 0


def command_probe_anchor(args) -> int:
    program = args.signing_program or shutil.which("ssh-keygen")
    if not program:
        raise AuthorityChainError(
            AuthorityErrorCode.ANCHOR_PROBE_FAILED,
            "no signing program is available",
        )
    result = probe_anchor_with_positive_control(
        Path(args.repo).resolve(),
        args.candidate_key,
        signing_program=program,
        signing_key=args.signing_key,
    )
    _print_json(result.to_dict())
    # Stage 1 never treats either a reachable or merely unreachable candidate
    # as authority-bearing. Both outcomes are fail-closed.
    return 1


def command_probe_harness(args) -> int:
    result = probe_harness_anchor(Path(args.repo).resolve())
    _print_json(result.to_dict())
    # This positive control MUST be reachable and therefore MUST be refused.
    return 1


def command_sign(args) -> int:
    repo = Path(args.repo).resolve()
    if not getattr(args, "paths", None):
        raise AuthorityChainError(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "sign requires one or more explicit --path arguments",
        )
    records = load_canonical_activation_entries(repo)
    matches = [record for record in records if record.uid == args.activation_uid]
    if len(matches) != 1:
        raise AuthorityChainError(
            AuthorityErrorCode.ACTIVATION_KEY_UNBOUND,
            "activation UID does not resolve exactly once",
            details={"activation_uid": args.activation_uid, "matches": len(matches)},
        )
    signed = sign_commit(
        repo,
        matches[0],
        args.message,
        allow_empty=args.allow_empty,
        stage_paths=args.paths,
    )
    _print_json(
        {
            "ok": True,
            "commit": signed.commit,
            "activation_uid": signed.activation_uid,
            "signature": signed.signature.to_dict(),
        }
    )
    return 0


def command_audit(args) -> int:
    repo = Path(args.repo).resolve()
    if args.commits:
        commits = args.commits
    else:
        command = ["git", "rev-list"]
        if args.max_count is not None:
            command.append(f"--max-count={args.max_count}")
        command.append(args.revision)
        result = subprocess.run(
            command,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise AuthorityChainError(
                AuthorityErrorCode.GIT_COMMAND_FAILED,
                "git rev-list failed",
                details={"stderr": (result.stderr or result.stdout).strip()},
            )
        commits = [line for line in result.stdout.splitlines() if line]
    signatures = collect_commit_signatures(repo, commits)
    findings: list[dict] = []
    try:
        detect_key_author_collapse(signatures)
    except AuthorityChainError as error:
        if error.code != AuthorityErrorCode.ONE_KEY_MANY_AUTHORS:
            raise
        findings.append(
            {
                "code": error.code.value,
                "message": error.message,
                "details": error.details,
            }
        )
    identity_collapse = bool(findings)
    _print_json(
        {
            "ok": not identity_collapse,
            "commits_scanned": len(commits),
            "signed_commits": len(signatures),
            "skipped_signatures": [
                skipped.to_dict() for skipped in signatures.skipped
            ],
            "identity_collapse": identity_collapse,
            "findings": findings,
        }
    )
    return 1 if identity_collapse else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify activation-bound commit provenance and authority-anchor reachability"
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="Resolve a commit provenance chain")
    verify.add_argument("--repo", default=str(ROOT))
    verify.add_argument("--commit", default="HEAD")
    verify.add_argument("--require-authority", action="store_true")
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=command_verify)

    signers = sub.add_parser(
        "allowed-signers",
        help="Render active activation signers to stdout (never writes an artifact)",
    )
    signers.add_argument("--repo", default=str(ROOT))
    signers.set_defaults(func=command_allowed_signers)

    probe = sub.add_parser(
        "probe-anchor",
        help="Attempt a fabricated-author signature against a candidate anchor",
    )
    probe.add_argument("--candidate-key", required=True)
    probe.add_argument("--repo", default=str(ROOT))
    probe.add_argument("--signing-program", default="")
    probe.add_argument(
        "--signing-key",
        default="",
        help=(
            "Private-key path or agent-resolvable public key passed to git; "
            "defaults to the candidate public key"
        ),
    )
    probe.set_defaults(func=command_probe_anchor)

    harness = sub.add_parser(
        "probe-harness",
        help="Run the mandatory known-positive reachability plant",
    )
    harness.add_argument("--repo", default=str(ROOT))
    harness.set_defaults(func=command_probe_harness)

    sign = sub.add_parser(
        "sign",
        help="Create an activation-signed commit with per-command config only",
    )
    sign.add_argument("--repo", default=str(ROOT))
    sign.add_argument("--activation-uid", required=True)
    sign.add_argument("--message", required=True)
    sign.add_argument(
        "--path",
        dest="paths",
        action="append",
        required=True,
        help="Exact repository-relative path to include; repeat for multiple paths",
    )
    sign.add_argument("--allow-empty", action="store_true")
    sign.set_defaults(func=command_sign)

    audit = sub.add_parser(
        "audit-identities",
        help="Detect one signing key under multiple commit authors",
    )
    audit.add_argument("--repo", default=str(ROOT))
    audit.add_argument("--revision", default="HEAD")
    audit.add_argument(
        "--max-count",
        type=_positive_int,
        default=None,
        help="Optional explicit history bound; default scans all commits reachable from revision",
    )
    audit.add_argument("commits", nargs="*")
    audit.set_defaults(func=command_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "signing_key", None) == "":
        args.signing_key = None
    try:
        return args.func(args)
    except AuthorityChainError as error:
        _print_json(error.to_dict())
        return 2


if __name__ == "__main__":
    sys.exit(main())
