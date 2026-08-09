#!/usr/bin/env python3
"""
---
uid: d78cc16a
title: preflight — Tool
name: preflight
type: tool
status: active
owner: metis
domain: "Can this machine run the studio at all? Verifies the interpreter floor and every dependency declared in requirements.txt, using ONLY the standard library, and prints the exact remediation instead of an ImportError stack. Degrades to a known minimum on a studio forked before requirements.txt existed."
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-preflight.py [--json] [--quiet]"
script_path: vault/tools/tropo-preflight.py
belt: true
belt_invocation: "python3 vault/tools/tropo-preflight.py"
belt_example: "python3 vault/tools/tropo-preflight.py --json"
trigger_description: "First command on any new machine, and the first thing to run when a tool dies on an import."
author: metis-g97
created: '2026-07-30'
created_by: metis-g97
schema_version: 2
governed_by: d5e1b4a3
member_of:
- 8dd772a0
---

tropo-preflight — can this machine run the studio at all?

WHY THIS EXISTS (metis-g97, 2026-07-30)
---------------------------------------
`requirements.txt` DECLARES the studio's Python dependencies (argus-a136,
2026-07-21, closing a root cause the v1.85.0-b4a genesis exposed). Nothing
VERIFIED them. That is the automatic-half/manual-half shape: the declaration is
machine-readable and the checking was left to an agent noticing an ImportError
stack mid-ceremony.

Two machines paid for it in one day:
  * Mike's new Mac — metis-g97's boot died on `yaml`, then on `cryptography`,
    one crash at a time, with no instruction attached to either.
  * The MindBridge work studio — forked from the v1.84.1 base (2026-07-10),
    which predates requirements.txt by eleven days. Val cannot read a
    declaration that studio never received, and the B4a update package does not
    ship it into the target.

So this tool has one hard constraint: **it must run when NOTHING is installed.**
Standard library only. No yaml. If it ever grows a third-party import it has
defeated its own purpose.

USAGE
    python3 vault/tools/tropo-preflight.py            # human-readable
    python3 vault/tools/tropo-preflight.py --json     # machine-readable
    python3 vault/tools/tropo-preflight.py --quiet    # exit code only

EXIT CODES
    0  ready
    1  a required dependency or the interpreter floor is unmet
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

# The interpreter floor the toolchain is written against. Declared in
# requirements.txt's header; restated here because preflight must work on a
# studio whose requirements.txt is missing entirely (the MindBridge case).
PYTHON_FLOOR = (3, 9)

# PyPI distribution name -> the module you actually import. These differ often
# enough that guessing is wrong: PyYAML imports as `yaml`.
IMPORT_NAME = {
    "pyyaml": "yaml",
    "cryptography": "cryptography",
    "anthropic": "anthropic",
    "pdfplumber": "pdfplumber",
    "mitmproxy": "mitmproxy",
    "markdown": "markdown",
}

# Fallback used ONLY when requirements.txt is absent — i.e. a studio forked
# before the declaration existed. Keeping this in sync is a maintenance cost we
# accept, because the alternative is telling a stranded studio nothing at all.
FALLBACK_REQUIRED = ["PyYAML", "cryptography"]


def studio_root() -> Path:
    """The studio root: this file lives at <root>/vault/tools/."""
    return Path(__file__).resolve().parents[2]


def parse_requirements(path: Path) -> tuple[list[str], bool]:
    """Return (required distribution names, file_found).

    Deliberately simple text parsing: a commented-out line is an OPTIONAL
    dependency by this file's own convention and must not be treated as
    required. Anything after a `#` on a live line is a trailing comment.
    """
    if not path.is_file():
        return (list(FALLBACK_REQUIRED), False)

    required: list[str] = []
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name = re.split(r"[<>=!~\[]", line, 1)[0].strip()
        if name:
            required.append(name)
    if not required:
        return (list(FALLBACK_REQUIRED), True)
    return (required, True)


def module_for(dist: str) -> str:
    return IMPORT_NAME.get(dist.lower(), dist.lower().replace("-", "_"))


def check_module(mod: str) -> tuple[bool, str]:
    """Importable? Return (ok, detail). Never raises."""
    try:
        spec = importlib.util.find_spec(mod)
    except (ImportError, ValueError, ModuleNotFoundError, AttributeError):
        return (False, "not importable")
    if spec is None:
        return (False, "not installed")
    origin = spec.origin or "namespace"
    return (True, origin)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True, description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--quiet", action="store_true", help="exit code only")
    args = ap.parse_args()

    root = studio_root()
    req_path = root / "requirements.txt"
    required, found = parse_requirements(req_path)

    py_ok = sys.version_info[:2] >= PYTHON_FLOOR
    py_actual = ".".join(str(p) for p in sys.version_info[:3])

    results = []
    missing = []
    for dist in required:
        mod = module_for(dist)
        ok, detail = check_module(mod)
        results.append({"dist": dist, "module": mod, "ok": ok, "detail": detail})
        if not ok:
            missing.append(dist)

    ready = py_ok and not missing

    if args.json:
        print(json.dumps({
            "ready": ready,
            "studio_root": str(root),
            "python": {"actual": py_actual, "floor": ".".join(map(str, PYTHON_FLOOR)), "ok": py_ok},
            "requirements_txt_found": found,
            "required": results,
            "missing": missing,
        }, indent=2))
        return 0 if ready else 1

    if args.quiet:
        return 0 if ready else 1

    print("Tropo preflight — can this machine run the studio?")
    print(f"  studio root : {root}")
    print(f"  python      : {py_actual}  ({'ok' if py_ok else 'BELOW FLOOR ' + '.'.join(map(str, PYTHON_FLOOR))})")
    if not found:
        print(f"  requirements: NOT FOUND at {req_path}")
        print("                This studio predates the dependency declaration")
        print("                (added 2026-07-21). Checking the known minimum instead.")
    else:
        print(f"  requirements: {req_path}")
    print()

    for r in results:
        mark = "ok  " if r["ok"] else "MISSING"
        print(f"  [{mark}] {r['dist']}  (import {r['module']})")

    print()
    if ready:
        print("READY — the governed toolchain can run.")
        return 0

    print("NOT READY. Fix, in order:")
    step = 1
    if not py_ok:
        print(f"  {step}. Python {'.'.join(map(str, PYTHON_FLOOR))}+ is required; this is {py_actual}.")
        print("     On macOS, the stock interpreter comes with the command line tools:")
        print("         xcode-select --install")
        step += 1
    if missing:
        print(f"  {step}. Install the missing packages (no sudo, no virtualenv needed):")
        if found:
            print(f"         python3 -m pip install --user -r {req_path}")
        else:
            print(f"         python3 -m pip install --user {' '.join(missing)}")
        print()
        print("     NOTE: if you are following a B4a update package, its own")
        print("     requirements.txt declares cryptography ONLY. The studio also")
        print("     needs PyYAML — 53 modules import it. Install both.")
        step += 1
    print()
    print("  Then re-run: python3 vault/tools/tropo-preflight.py")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
