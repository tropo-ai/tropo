#!/usr/bin/env python3
"""
---
uid: 5187be30
name: mint-uid
type: tool
title: "mint-uid — the canonical collision-checked UID minter"
status: active
owner: argus
domain: "UID minting — the one collision-checked source of governed 8-hex UIDs"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/5187be30.py"
script_path: vault/tools/5187be30.py
spawnable_by:
  - all-executives
input:
  type: object
  properties:
    count: {type: integer, description: "how many UIDs to mint (default 1)"}
    reason: {type: string, description: "advisory note for the caller's own log (not persisted here)"}
output:
  type: object
  description: "one collision-checked 8-hex UID per line on stdout"
created: 2026-06-02
created_by: argus-a93
modified: 2026-06-02
modified_by: argus-a93
version: "1.0"
governed_by: d5e1b4a3
member_of:
  - "c7e4f9a2"
schema_version: 2
belt: true
extraction_scope: ship
trigger_description: "Get a fresh collision-checked 8-hex UID before authoring."
belt_invocation: "python3 vault/tools/5187be30.py"
belt_example: "python3 vault/tools/5187be30.py --count 5"
---
"""


# mint-uid — the canonical, collision-checked UID minter.
#
# WHY THIS EXISTS (Argus A93 2026-06-02, per Mike-A93 directive): minting a UID was a
# DISCIPLINARY surface — every agent rolled its own `secrets.token_hex(4)` one-liner, and
# most did NOT collision-check. A survey found the pattern duplicated across ~9 tools
# (e337f1dd, 9e7003b1, 40b2f455, 4beff0d6, 1056eec5, 6342d0ca, b3f9d7e2, bf886f30,
# ce9dbcc2). This is the Disciplinary->Structural law (2bc33c0f) applied: one gesture,
# correct by construction (always collision-checked against everywhere UIDs live).
#
# ONE-CHOKEPOINT FOLLOW-UP (Talos lane, tracked): the ~9 duplicating callers should be
# refactored to `from <this> import mint` so there is exactly one minting code path. Until
# then this is the SANCTIONED minter; a future `check_uid_collision` validator at rebuild
# makes the chokepoint enforced (catches any UID collision that slips in by another path).
#
# FEDERATION EXTENSION POINT (Federation Foundation 7cac6473 / brainstorm a1230aff): a
# federated, multi-Studio mint must be PREFIX-AWARE (Studio-Prefixed UIDs) so two laptops
# minting offline cannot collide. That `--prefix <studio>` logic lands HERE when federation
# is sequenced. Today, single-Studio: plain collision-checked 8-hex.

from __future__ import annotations
import argparse
import re
import secrets
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
INDEX = VAULT_ROOT / "vault" / "00-index.jsonl"

_HEX8 = re.compile(r"^[0-9a-f]{8}$")
_INDEX_UID = re.compile(r'"uid"\s*:\s*"([0-9a-f]{8})"')


def load_existing_uids() -> set[str]:
    """Every 8-hex UID currently in use — the index + the governed-file filenames.

    These are the two places a governed UID lives; the registries derive from the index.
    """
    uids: set[str] = set()
    if INDEX.exists():
        for line in INDEX.read_text(encoding="utf-8").splitlines():
            m = _INDEX_UID.search(line)
            if m:
                uids.add(m.group(1))
    if VAULT_FILES.is_dir():
        for f in VAULT_FILES.glob("*.md"):
            if _HEX8.match(f.stem):
                uids.add(f.stem)
    return uids


def mint(count: int = 1) -> list[str]:
    """Return `count` fresh 8-hex UIDs, each guaranteed not to collide with any in use."""
    if count < 1:
        raise ValueError("count must be >= 1")
    existing = load_existing_uids()
    out: list[str] = []
    for _ in range(count):
        for _attempt in range(64):
            candidate = secrets.token_hex(4)
            if candidate not in existing:
                existing.add(candidate)
                out.append(candidate)
                break
        else:
            raise RuntimeError("UID collision storm — could not mint a free 8-hex in 64 tries")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Mint collision-checked governed 8-hex UID(s).")
    p.add_argument("--count", type=int, default=1, help="how many UIDs to mint (default 1)")
    p.add_argument("--reason", default="", help="advisory; for the caller's own log (not persisted)")
    args = p.parse_args()
    try:
        for u in mint(args.count):
            print(u)
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
