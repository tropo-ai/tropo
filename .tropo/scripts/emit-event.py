#!/usr/bin/env python3
"""Discoverable-name shim — emit-event lives at vault/tools/ca90f098.py.

Companion to query-events.py. The boot docs reference `emit-event` by logical
name; the tool is UID-named (ca90f098.py) after the v1.61 tools-in-vault
migration, so agents can't find it by name. This shim restores
name-discoverability and runnability:

    python3 .tropo/scripts/emit-event.py --type tropo.message.sent \\
        --source //argus-a89 --source-uid <uid> --lifecycle ephemeral --data '{...}'

Forwards every argument to the canonical tool. SUPERSEDED by the full
tool-discovery layer (name->UID dispatcher + MCP exposure) pre-v2.0 per the
Argus A89 brief. L1 band-aid; authored Argus A89 2026-05-31 (Mike-A89 'shim now').
"""
import sys, subprocess
from pathlib import Path
_VAULT_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _VAULT_ROOT / "vault" / "tools" / "ca90f098.py"
sys.exit(subprocess.run([sys.executable, str(_TARGET)] + sys.argv[1:]).returncode)
