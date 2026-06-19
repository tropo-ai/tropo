#!/usr/bin/env python3
"""Discoverable-name shim — mint-uid lives at vault/tools/5187be30.py.

Agents reference `mint-uid` by logical name; the canonical tool is UID-named after the
tools-in-vault convention, so this shim restores name-discoverability + runnability:

    python3 .tropo/scripts/mint-uid.py [--count N] [--reason "..."]

Forwards every argument to the canonical tool. Superseded by the full tool-discovery
layer (name->UID dispatcher) when that lands. Authored Argus A93 2026-06-02.
"""
import sys
import subprocess
from pathlib import Path

_VAULT_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _VAULT_ROOT / "vault" / "tools" / "5187be30.py"
sys.exit(subprocess.run([sys.executable, str(_TARGET)] + sys.argv[1:]).returncode)
