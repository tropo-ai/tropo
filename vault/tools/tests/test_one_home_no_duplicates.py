#!/usr/bin/env python3
"""AC1 — One Home: no governed file exists in two homes.

Post-migration, the same UID must not appear in both vault/ content directories
and .tropo/ content directories. The ONLY legitimate .tropo/ content is the
bootstrap-floor pointer set (boot-config, boot-digest, orientation, SELF-HEALING,
toolbelt, boot-fast-path, skill-catalog, tool-catalog, sa-agent-catalog, the
concierge and persona subdirs).

Exit 0 = PASS (one home), Exit 1 = FAIL (two-home violations found).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VAULT = ROOT / "vault"
TROPO = ROOT / ".tropo"

FRONTMATTER_UID = re.compile(r"^uid:\s*([0-9a-f]{8})\s*$", re.MULTILINE)

# Bootstrap-floor .tropo/ files that legitimately exist outside vault/.
# These are static pointers, not substantive governed content.
BOOTSTRAP_FLOOR = frozenset({
    "boot-config.md", "boot-digest.md", "boot-fast-path.md", "orientation.md",
    "SELF-HEALING.md", "CAPSULE.md", "TROPO-CONTROL.md", "00-index.md",
    "AGENTS.md", "HUMAN-NAVIGATION.md", "toolbelt.md", "version.md",
    "tool-catalog.md", "skill-catalog.md", "sa-agent-catalog.md",
    "scheduled-agents.md",
})


def uids_in_dir(directory: Path, glob: str = "**/*.md") -> dict[str, Path]:
    uid_map = {}
    if not directory.exists():
        return uid_map
    for f in directory.glob(glob):
        if f.name in BOOTSTRAP_FLOOR:
            continue
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        m = FRONTMATTER_UID.search(text[:2000])
        if m:
            uid_map[m.group(1)] = f
    return uid_map


def main() -> int:
    vault_uids: dict[str, Path] = {}
    for subdir in ["files", "skills", "actions", "tools", "playbooks", "capsules", "templates"]:
        vault_uids.update(uids_in_dir(VAULT / subdir))

    # .tropo/ content dirs (not scripts/ which are shims, not skills/actions that should be gone)
    tropo_content_uids: dict[str, Path] = {}
    for subdir in ["skills", "actions", "capsules", "templates", "playbooks"]:
        tropo_content_uids.update(uids_in_dir(TROPO / subdir))
    # Also scan .tropo/ root .md files (excluding bootstrap floor)
    for f in TROPO.glob("*.md"):
        if f.name not in BOOTSTRAP_FLOOR:
            try:
                text = f.read_text(errors="ignore")
                m = FRONTMATTER_UID.search(text[:2000])
                if m:
                    tropo_content_uids[m.group(1)] = f
            except Exception:
                pass

    violations = []
    for uid, tropo_path in tropo_content_uids.items():
        if uid in vault_uids:
            violations.append((uid, tropo_path, vault_uids[uid]))

    if violations:
        print(f"FAIL — {len(violations)} two-home violation(s):")
        for uid, tp, vp in violations[:20]:
            print(f"  {uid}: .tropo/={tp.relative_to(ROOT)}  vault/={vp.relative_to(ROOT)}")
        if len(violations) > 20:
            print(f"  ... and {len(violations) - 20} more")
        return 1

    print(f"PASS — zero two-home duplicates (vault/ UIDs: {len(vault_uids)}, .tropo/ content UIDs: {len(tropo_content_uids)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
