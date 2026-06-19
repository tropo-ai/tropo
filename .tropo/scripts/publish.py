#!/usr/bin/env python3
"""v1.56 compatibility forwarder — publish.py moved to vault/tools/2e642578.py.

This shim forwards to the canonical location per tool.capsule v1.6 §2.5
single-file-truth migration. Remove at v1.57 once invocation-path sweep complete.
"""
import sys, subprocess
from pathlib import Path
_VAULT_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _VAULT_ROOT / "vault" / "tools" / "2e642578.py"
sys.exit(subprocess.run([sys.executable, str(_TARGET)] + sys.argv[1:]).returncode)
