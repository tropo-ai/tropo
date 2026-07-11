#!/usr/bin/env python3
"""AC7 — Rename-safety smoke (option C): no uid→path resolver introduced.

Post-migration:
  (a) Every shipped tool (extraction_scope:ship, status:active) in vault/tools/ invokes
      by its tropo- name (the file is named tropo-*.py or referenced by tropo- name).
  (b) The 5 executable call-sites in 992ba026 are fixed — no UID-path subprocess call
      remains in vault/tools/992ba026*.py (the disposition tool, possibly renamed).
  (c) No uid→path resolver module or manifest-alias layer was introduced (option C held).

Exit 0 = PASS, Exit 1 = FAIL.
"""
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
VAULT_TOOLS = ROOT / "vault" / "tools"

# Pattern: subprocess call using UID-only tool path (the 5 call-sites pre-migration)
UID_CALL_PATTERN = re.compile(
    r"""(?:subprocess\.run|subprocess\.call|subprocess\.check_output)\s*\(\s*\[.*?['"](vault/tools/[0-9a-f]{8}\.py|\.tropo/scripts/[0-9a-f]{8}\.py)['"]""",
    re.DOTALL,
)

# resolver/manifest patterns that would indicate option A or B was introduced
RESOLVER_PATTERNS = [
    re.compile(r"uid_to_path|uid2path|resolve_uid.*tool|tool.*resolve_uid", re.IGNORECASE),
    re.compile(r"manifest_alias|alias_manifest|tool_manifest", re.IGNORECASE),
    re.compile(r"def.*resolve.*tool|def.*tool.*resolve", re.IGNORECASE),
]

DISPOSITION_STEM_PATTERN = re.compile(r"992ba026")


def find_disposition_tool() -> Optional[Path]:
    """Find the disposition tool (may be at 992ba026.py or tropo-disposition-992ba026.py)."""
    for f in VAULT_TOOLS.glob("*.py"):
        if DISPOSITION_STEM_PATTERN.search(f.stem):
            return f
    # Also try tropo-disposition.py (if renamed to clean tropo- name)
    candidate = VAULT_TOOLS / "tropo-disposition.py"
    if candidate.exists():
        return candidate
    return None


def check_disposition_callsites() -> list[str]:
    f = find_disposition_tool()
    if not f:
        return ["[disposition tool not found at vault/tools/992ba026*.py or tropo-disposition.py]"]
    text = f.read_text(errors="ignore")
    hits = []
    for m in UID_CALL_PATTERN.finditer(text):
        hits.append(m.group(1))
    return hits


def check_no_resolver() -> list[str]:
    hits = []
    if not VAULT_TOOLS.exists():
        return hits
    for f in VAULT_TOOLS.glob("*.py"):
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        for pat in RESOLVER_PATTERNS:
            if pat.search(text):
                hits.append(f"{f.relative_to(ROOT)}: {pat.pattern}")
                break
    return hits


def check_shipped_tropo_prefix() -> list[str]:
    FM_SCOPE = re.compile(r"^extraction_scope:\s*ship\s*$", re.MULTILINE)
    FM_STATUS = re.compile(r"^status:\s*active\s*$", re.MULTILINE)
    not_tropo = []
    if not VAULT_TOOLS.exists():
        return not_tropo
    for f in VAULT_TOOLS.glob("*.py"):
        if f.name.startswith("tropo-"):
            continue
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        fm_m = re.search(r'"""[\s\S]*?---\n([\s\S]+?)---\n', text)
        fm = fm_m.group(1) if fm_m else ""
        if FM_SCOPE.search(fm) and FM_STATUS.search(fm):
            not_tropo.append(str(f.relative_to(ROOT)))
    return not_tropo


def main() -> int:
    failed = False

    # (a) Shipped tools have tropo- prefix
    no_prefix = check_shipped_tropo_prefix()
    if no_prefix:
        print(f"FAIL (a) — {len(no_prefix)} shipped tool(s) in vault/tools/ missing tropo- prefix:")
        for p in no_prefix[:10]:
            print(f"  {p}")
        failed = True
    else:
        print("PASS (a) — all shipped vault/tools/*.py carry tropo- filename prefix")

    # (b) 992ba026 call-sites are fixed
    callsite_hits = check_disposition_callsites()
    if callsite_hits:
        print(f"FAIL (b) — {len(callsite_hits)} residual UID-path call-site(s) in disposition tool:")
        for h in callsite_hits:
            print(f"  {h}")
        failed = True
    else:
        print("PASS (b) — no residual UID-path subprocess calls in disposition tool (all 5 fixed)")

    # (c) No uid→path resolver or manifest-alias introduced
    resolver_hits = check_no_resolver()
    if resolver_hits:
        print(f"FAIL (c) — uid→path resolver or manifest-alias pattern found (option C violated):")
        for h in resolver_hits[:5]:
            print(f"  {h}")
        failed = True
    else:
        print("PASS (c) — no uid→path resolver or manifest-alias layer found (option C preserved)")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
