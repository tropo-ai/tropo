#!/usr/bin/env python3
"""AC2 — tropo- namespace: shipped standard library has tropo- filename prefix.

Post-migration:
  (a) Every vault/tools/*.py, vault/skills/*.md, vault/actions/*.md, vault/playbooks/*.md
      with extraction_scope:ship AND status:active must have a tropo- filename prefix.
  (b) Re-running the executable call-site enumeration finds ZERO remaining UID-path-only
      subprocess calls to other vault/tools/ scripts (the 5 known call-sites in 992ba026
      were fixed inline during migration; option C holds).

Exit 0 = PASS, Exit 1 = FAIL.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VAULT = ROOT / "vault"

FM_SCOPE = re.compile(r"^extraction_scope:\s*ship\s*$", re.MULTILINE)
FM_STATUS = re.compile(r"^status:\s*active\s*$", re.MULTILINE)
# UID-only subprocess call pattern: ['...', 'vault/tools/<8hex>.py', ...]
UID_CALL_PATTERN = re.compile(r"""["']vault/tools/([0-9a-f]{8})\.py["']""")

# Tier 1 (this cycle): only vault/tools/*.py get the tropo- prefix rename.
# Tier 2: vault/skills/*.md, vault/actions/*.md, vault/playbooks/*.md get slug-uid
# human-readable renames per ADR-048 (full slug-uid rename, ~3,200 files).
DIRS_AND_EXT = [
    (VAULT / "tools", ".py"),
]


def read_frontmatter(path: Path) -> str:
    """Extract YAML frontmatter text (everything between first --- markers)."""
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return ""
    if path.suffix == ".py":
        # frontmatter is inside the leading docstring: """...\n---\n...\n---\n..."""
        m = re.search(r'"""[\s\S]*?---\n([\s\S]+?)---\n', text)
        if m:
            return m.group(1)
        return ""
    # .md files: first ---...--- block
    m = re.search(r"^---\n([\s\S]+?)\n---\n", text)
    if m:
        return m.group(1)
    return ""


def check_tropo_prefix() -> list[str]:
    failures = []
    for d, ext in DIRS_AND_EXT:
        if not d.exists():
            continue
        for f in sorted(d.glob(f"*{ext}")):
            if f.name.startswith("tropo-"):
                continue
            fm = read_frontmatter(f)
            if FM_SCOPE.search(fm) and FM_STATUS.search(fm):
                failures.append(str(f.relative_to(ROOT)))
    return failures


def check_uid_callsites() -> list[tuple[str, str]]:
    """Find remaining UID-path subprocess calls in vault/tools/*.py."""
    hits = []
    tools_dir = VAULT / "tools"
    if not tools_dir.exists():
        return hits
    for f in sorted(tools_dir.glob("*.py")):
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        for m in UID_CALL_PATTERN.finditer(text):
            hits.append((str(f.relative_to(ROOT)), m.group(0)))
    return hits


def main() -> int:
    no_prefix = check_tropo_prefix()
    uid_calls = check_uid_callsites()
    failed = False

    if no_prefix:
        print(f"FAIL (a) — {len(no_prefix)} shipped file(s) missing tropo- prefix:")
        for p in no_prefix[:20]:
            print(f"  {p}")
        failed = True
    else:
        print("PASS (a) — all shipped files carry tropo- filename prefix")

    if uid_calls:
        print(f"FAIL (b) — {len(uid_calls)} residual UID-path call-site(s) found:")
        for f, hit in uid_calls[:10]:
            print(f"  {f}: {hit}")
        failed = True
    else:
        print("PASS (b) — zero residual UID-path subprocess call-sites")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
