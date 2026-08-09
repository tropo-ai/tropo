#!/usr/bin/env python3
"""
---
uid: bbf5afe8
name: generate-mint-registry
type: tool
title: "generate-mint-registry — derive typed mint bindings from capsules"
status: active
owner: argus
domain: "Typed mint registry generation"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-generate-mint-registry.py"
script_path: vault/tools/tropo-generate-mint-registry.py
spawnable_by:
  - all-executives
input:
  type: object
  properties:
    check: {type: boolean, description: "refuse when the generated registry differs from disk"}
output:
  type: object
  description: "deterministic disposable registry at vault/capsules/mint-registry.json"
created: 2026-08-03
created_by: argus-a144
modified: 2026-08-03
modified_by: argus-a144
version: "1.0"
governed_by: d5e1b4a3
member_of:
  - "8dd772a0"
schema_version: 2
belt: true
extraction_scope: ship
trigger_description: "Regenerate the typed mint registry after capsule or companion-template changes."
belt_invocation: "python3 vault/tools/tropo-generate-mint-registry.py"
belt_example: "python3 vault/tools/tropo-generate-mint-registry.py --check"
---
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib import template_leg  # noqa: E402


VAULT_ROOT = Path(__file__).resolve().parents[2]
class MintRegistryGenerationError(ValueError):
    pass


def build_registry_bytes(vault_root: Path) -> bytes:
    """Return byte-stable schema-v2 content from the shared registry builder."""
    try:
        return template_leg.build_mint_registry_bytes(vault_root)
    except template_leg.TemplateLegError as exc:
        raise MintRegistryGenerationError(str(exc)) from exc


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        tmp_path.unlink(missing_ok=True)


def generate_registry(
    vault_root: Path,
    output_path: Path | None = None,
    *,
    check: bool = False,
) -> Path:
    raw = build_registry_bytes(vault_root)
    path = output_path or (vault_root / template_leg.MINT_REGISTRY_REL)
    if check:
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise MintRegistryGenerationError(
                f"mint registry check failed: {path} is missing or unreadable"
            ) from exc
        if current != raw:
            raise MintRegistryGenerationError(
                f"mint registry check failed: {path} is stale; regenerate it"
            )
        return path
    _atomic_write(path, raw)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive the disposable typed mint registry from capsule bindings."
    )
    parser.add_argument("--check", action="store_true", help="refuse if the registry is stale")
    parser.add_argument(
        "--vault-path",
        type=Path,
        default=VAULT_ROOT,
        help="Studio root (default: root containing this tool)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="test-only alternate output path",
    )
    args = parser.parse_args()
    try:
        path = generate_registry(args.vault_path.resolve(), args.output, check=args.check)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
