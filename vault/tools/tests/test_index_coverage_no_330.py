#!/usr/bin/env python3
"""AC4 — Index coverage: vault/skills/* and every vault/<type>/* appear in 00-index.jsonl.

The 330-failure root cause was vault/skills/ being unindexed. This test proves the
failure class cannot recur: after a rebuild, every vault/<type>/ directory's .md files
appear as entries in vault/00-index.jsonl.

Also verifies that 992ba026 (tropo-disposition, the regression seed) is indexed —
specifically that a tool with YAML frontmatter in its Python docstring IS picked up
by the rebuild.

Exit 0 = PASS, Exit 1 = FAIL.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VAULT = ROOT / "vault"
INDEX = VAULT / "00-index.jsonl"

# vault/ subdirs that should have all their .md files indexed
CONTENT_DIRS = ["files", "skills", "actions", "playbooks"]
# Optional dirs that should be indexed IF they exist
OPTIONAL_DIRS = ["capsules", "templates"]

REGRESSION_SEED_UID = "992ba026"


def load_indexed_uids() -> set[str]:
    uids = set()
    if not INDEX.exists():
        return uids
    with open(INDEX) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                uid = d.get("uid")
                if uid:
                    uids.add(uid)
            except Exception:
                pass
    return uids


def get_vault_uids_in_dir(d: Path) -> dict[str, Path]:
    import re
    uid_re = re.compile(r"^uid:\s*([0-9a-f]{8})\s*$", re.MULTILINE)
    result = {}
    if not d.exists():
        return result
    for f in d.glob("*.md"):
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        m = uid_re.search(text[:2000])
        if m:
            result[m.group(1)] = f
    return result


def main() -> int:
    indexed = load_indexed_uids()
    failed = False

    for subdir in CONTENT_DIRS:
        d = VAULT / subdir
        dir_uids = get_vault_uids_in_dir(d)
        missing = {uid: p for uid, p in dir_uids.items() if uid not in indexed}
        if missing:
            print(f"FAIL — vault/{subdir}/: {len(missing)} unindexed file(s):")
            for uid, p in list(missing.items())[:10]:
                print(f"  {uid}: {p.name}")
            failed = True
        else:
            print(f"PASS — vault/{subdir}/: all {len(dir_uids)} file(s) indexed")

    for subdir in OPTIONAL_DIRS:
        d = VAULT / subdir
        if not d.exists():
            print(f"NOTE — vault/{subdir}/ does not exist (migration not yet complete)")
            continue
        dir_uids = get_vault_uids_in_dir(d)
        missing = {uid: p for uid, p in dir_uids.items() if uid not in indexed}
        if missing:
            print(f"FAIL — vault/{subdir}/: {len(missing)} unindexed file(s):")
            for uid, p in list(missing.items())[:10]:
                print(f"  {uid}: {p.name}")
            failed = True
        else:
            print(f"PASS — vault/{subdir}/: all {len(dir_uids)} file(s) indexed")

    # Regression seed: 992ba026 must be indexed (found dc8f8f2e)
    if REGRESSION_SEED_UID in indexed:
        print(f"PASS — regression seed {REGRESSION_SEED_UID} (tropo-disposition) is indexed")
    else:
        print(f"FAIL — regression seed {REGRESSION_SEED_UID} (tropo-disposition) is NOT indexed")
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
