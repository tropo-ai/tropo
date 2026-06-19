"""action_validators.py — Validation checks for vault/actions/ entries (v1.60 Lane A-migrate).

Per action.capsule v1.0 (or current version). Wired into tropo-validate.py main().

Checks (WARN at v1.60):
  1. Required frontmatter present (uid, type, name)
  2. type == "action"
  3. uid format is valid 8-hex
  4. Index parity: vault/actions/ disk count == indexed count
"""
from __future__ import annotations

TARGETS_CAPSULE = "action"  # Lane V Layer 3 M.1 targeting (8e2f1a47)

import json, re
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
ACTIONS_DIR = VAULT_ROOT / "vault" / "actions"
UID_RE = re.compile(r"^[0-9a-f]{8}$")


def run_all_action_checks(vault: Path) -> tuple[list[str], int, int]:
    """Run checks against vault/actions/ entries. Returns (findings, checked, defects)."""
    actions_dir = vault / "vault" / "actions"
    if not actions_dir.is_dir():
        return [], 0, 0

    findings: list[str] = []
    checked = 0

    for path in sorted(actions_dir.iterdir()):
        if path.suffix.lower() not in (".md", ".json"):
            continue
        if not UID_RE.match(path.stem):
            continue
        checked += 1
        label = f"vault/actions/{path.name}"

        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            findings.append(f"  [WARN] {label}: read error — {e}")
            continue

        # Parse frontmatter
        m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if not m:
            findings.append(f"  [WARN] {label}: no parseable frontmatter")
            continue
        fm = m.group(1)

        def _get(field: str) -> str | None:
            m2 = re.search(rf"^{re.escape(field)}:\s*(.+?)\s*$", fm, re.MULTILINE)
            return m2.group(1).strip().strip('"').strip("'") if m2 else None

        # Check 1: required fields
        uid = _get("uid")
        name = _get("name")
        typ = _get("type")
        missing = [f for f, v in [("uid", uid), ("name", name), ("type", typ)] if not v]
        if missing:
            findings.append(f"  [WARN] {label}: missing required fields {missing} (Check 1)")

        # Check 2: type == action
        if typ and typ != "action":
            findings.append(f"  [WARN] {label}: type={typ!r} not 'action' (Check 2)")

        # Check 3: uid format
        if uid and not UID_RE.match(uid):
            findings.append(f"  [WARN] {label}: uid {uid!r} not 8-hex (Check 3)")
        if uid and uid != path.stem:
            findings.append(f"  [WARN] {label}: frontmatter uid {uid!r} != filename {path.stem!r} (Check 3)")

    # Check 4: index parity
    index_path = vault / "vault" / "00-index.jsonl"
    if index_path.exists():
        try:
            indexed = sum(
                1 for l in index_path.read_text().splitlines()
                if l.strip() and json.loads(l).get("type") == "action"
            )
            disk = sum(
                1 for f in actions_dir.iterdir()
                if f.suffix.lower() in (".md", ".json") and UID_RE.match(f.stem)
            )
            if indexed != disk:
                findings.append(
                    f"  [WARN] vault/actions/ index parity: {disk} on disk vs {indexed} indexed "
                    f"— run rebuild-index --apply (Check 4)"
                )
        except Exception as e:
            findings.append(f"  [WARN] Check 4 index parity failed: {e}")

    return findings, checked, len(findings)
