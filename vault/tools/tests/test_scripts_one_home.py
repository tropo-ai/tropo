#!/usr/bin/env python3
"""AC3 — Scripts one home: all scripts at vault/tools/<uid>.py; no .tropo/scripts/ duplicate.

Post-migration, .tropo/scripts/ must not contain any .py file that is also a canonical
vault/tools/ tool. Legitimate .tropo/scripts/ residents after migration:
  - Compatibility shim files (thin forwarders, no uid: in their frontmatter/body)
  - Library modules: _yaml_dup_lib.py, docx_styles_bundle.py, publish_types.py
  - publish_targets/ directory
  - lib/ directory
  - Test fixtures (test_*.py — regression tests, not tools)

Any .py file whose UID (8-hex basename) also appears in vault/tools/ is a duplicate.

Exit 0 = PASS, Exit 1 = FAIL.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VAULT_TOOLS = ROOT / "vault" / "tools"
TROPO_SCRIPTS = ROOT / ".tropo" / "scripts"

UID_PATTERN = re.compile(r"^[0-9a-f]{8}$")

# Known non-tool residents that legitimately live in .tropo/scripts/ post-migration
LEGITIMATE_RESIDENTS = frozenset({
    "_yaml_dup_lib.py", "docx_styles_bundle.py", "publish_types.py",
    "emit-event.py",  # thin shim
    "_MIGRATION.md",
    "test-harness-check.py",  # self-contained release regression test (no vault imports by design)
    "tropo.py",  # tool-discovery dispatcher; reads frontmatter dynamically
})


def vault_tool_uids() -> set[str]:
    uids = set()
    if not VAULT_TOOLS.exists():
        return uids
    for f in VAULT_TOOLS.glob("*.py"):
        if UID_PATTERN.match(f.stem):
            uids.add(f.stem)
    return uids


def tropo_script_duplicates(vault_uids: set[str]) -> list[str]:
    duplicates = []
    if not TROPO_SCRIPTS.exists():
        return duplicates
    for f in TROPO_SCRIPTS.glob("*.py"):
        if f.name in LEGITIMATE_RESIDENTS:
            continue
        if f.name.startswith("test_"):
            continue
        if UID_PATTERN.match(f.stem) and f.stem in vault_uids:
            duplicates.append(str(f.relative_to(ROOT)))
        elif not UID_PATTERN.match(f.stem):
            # Named shim files — check if they forward to a vault/tools/ tool
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            # Pre-migration shim: forwards to vault/tools/<uid>.py that still exists
            uid_refs = re.findall(r"vault/tools/([0-9a-f]{8})\.py", text)
            if uid_refs and any(u in vault_uids for u in uid_refs):
                continue  # legitimate shim (pre-migration UID-named target)
            # Post-migration shim: forwards to vault/tools/tropo-*.py
            tropo_refs = re.findall(r"vault/tools/tropo-[\w.-]+\.py", text)
            if tropo_refs:
                continue  # legitimate shim (post-migration tropo-named target)
            # Named script with no vault/tools/ forwarder — flag for review
            duplicates.append(f"[review] {f.relative_to(ROOT)}")
    return duplicates


def main() -> int:
    vault_uids = vault_tool_uids()
    dups = tropo_script_duplicates(vault_uids)

    if dups:
        print(f"FAIL — {len(dups)} .tropo/scripts/ duplicate(s) of vault/tools/ remain:")
        for d in dups[:20]:
            print(f"  {d}")
        return 1

    print(f"PASS — no .tropo/scripts/ duplicates of vault/tools/ (vault/tools/ UIDs: {len(vault_uids)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
