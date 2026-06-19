#!/usr/bin/env python3
"""Discoverable-name shim — query-events lives at vault/tools/1545ac97.py.

The canonical "check events" operation (Tier 2 boot doc) tells agents to run
`query-events --party <uid>`. But the tool is UID-named after the v1.61
tools-in-vault migration, so `find -iname "*query-event*"` returns nothing and
agents hand-roll JSONL parsers instead of the one-second lookup. This shim
restores name-discoverability: it is findable by name and runnable directly:

    python3 .tropo/scripts/query-events.py --party <uid>
    python3 .tropo/scripts/query-events.py --type tropo.broadcast.crew --limit 8

It forwards every argument to the canonical tool. SUPERSEDED when the full
tool-discovery layer (name->UID dispatcher + MCP exposure) lands pre-v2.0 per
the Argus A89 brief; until then this is the L1 band-aid. Authored Argus A89
2026-05-31 (Phe-class friction; Mike-A89 'shim now and keep moving').
"""
import sys, subprocess
from pathlib import Path
_VAULT_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _VAULT_ROOT / "vault" / "tools" / "1545ac97.py"
sys.exit(subprocess.run([sys.executable, str(_TARGET)] + sys.argv[1:]).returncode)
