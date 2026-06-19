"""release_validators.py — Release entry schema checks (v1.59 Lane B A1).

Per dev-spec d8c3f1b7 A1. Extends release.capsule v3.8 validator with:
  - required_at_activation field-class checks (WARN at v1.59)
  - required_at_ship field-class checks (WARN at v1.59; ERROR ratchet v1.60+)
  - cascade_pipelines_retired check: refuses ship if triggered doc/test pipelines not retired

Wired into:
  - tropo-validate.py (WARN-level audit at vault rebuild)
  - build-release.py Lane B pre-flip gate (blocks ship if checks fail)
"""
from __future__ import annotations

TARGETS_CAPSULE = "release"  # Lane V Layer 3 M.1 targeting (8e2f1a47)

import json, re
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]

# Fields required at activation (when release entry first created)
REQUIRED_AT_ACTIVATION = {
    "capabilities_touched",
    "kernel_substrate_touched",
    "foundation",
    "member_of",
}

# Fields required at ship (must be non-TBD before status:shipped flip)
REQUIRED_AT_SHIP = {
    "released_at",
    "released_by",
    "build_artifact_path",
    "validator_state_at_ship",
    "pristine_streak_at_ship",
    "ship_signal_verbatim",
    "cold_boot_walk_disposition",
}

UID_RE = re.compile(r"^[0-9a-f]{8}$")

# Per release.capsule v3.12 Rule 15: required_at_* checks exempt for pre-v1.59.0 releases.
# Fields like ship_signal_verbatim / validator_state_at_ship are unknowable for historical entries.
_GRANDFATHER_THRESHOLD = (1, 59, 0)


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse 'v1.59.0' or '1.59.0' -> (1, 59, 0). Returns (0,) on parse failure."""
    v = v.strip().lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _read_index(vault: Path) -> list[dict]:
    idx = vault / "vault" / "00-index.jsonl"
    if not idx.exists():
        return []
    rows = []
    for line in idx.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _get_scalar(fm: str, field: str) -> str | None:
    m = re.search(rf"^{re.escape(field)}:\s*(.+?)\s*$", fm, re.MULTILINE)
    if not m:
        return None
    val = m.group(1).strip().strip('"').strip("'")
    return val or None


def _get_list(fm: str, field: str) -> list[str]:
    inline = re.search(rf"^{re.escape(field)}:\s*\[([^\]]*)\]", fm, re.MULTILINE)
    if inline:
        return [v.strip().strip('"').strip("'") for v in inline.group(1).split(",") if v.strip()]
    block = re.search(rf"^{re.escape(field)}:\s*\n((?:\s*-\s+.*\n?)+)", fm, re.MULTILINE)
    if block:
        return [re.match(r"\s*-\s+(.+)", l).group(1).strip().strip('"').strip("'")
                for l in block.group(1).splitlines() if re.match(r"\s*-\s+", l)]
    return []


def check_release_required_fields(vault: Path) -> tuple[list[str], int, int]:
    """Check release entries for required_at_activation + required_at_ship fields.

    Returns (findings, entries_checked, defects).
    """
    findings: list[str] = []
    checked = 0

    for row in _read_index(vault):
        if row.get("type") != "release":
            continue
        uid = row.get("uid", "")
        if not UID_RE.match(uid):
            continue

        path = vault / "vault" / "files" / f"{uid}.md"
        if not path.exists():
            continue

        try:
            text = path.read_text(encoding="utf-8")
            m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
            if not m:
                continue
            fm = m.group(1)
        except Exception:
            continue

        checked += 1
        status = _get_scalar(fm, "status") or ""

        # Grandfather guard (release.capsule v3.12 Rule 15): skip pre-v1.59.0 entries.
        release_version = _get_scalar(fm, "release_version") or ""
        if _parse_version(release_version) < _GRANDFATHER_THRESHOLD:
            continue

        # required_at_activation checks (all non-archived release entries)
        if status not in ("archived", "superseded"):
            for field in REQUIRED_AT_ACTIVATION:
                val = _get_scalar(fm, field)
                if not val or val.upper() in ("TBD", "PENDING", ""):
                    findings.append(
                        f"  [WARN] release {uid}: required_at_activation field {field!r} "
                        f"missing or TBD (A1 release.capsule v1.59)"
                    )

        # required_at_ship checks (only status:shipped entries)
        if status == "shipped":
            for field in REQUIRED_AT_SHIP:
                val = _get_scalar(fm, field)
                if not val or val.upper() in ("TBD", "PENDING", ""):
                    findings.append(
                        f"  [WARN] release {uid}: required_at_ship field {field!r} "
                        f"missing or TBD — status:shipped with unpopulated field (A1 v1.59)"
                    )

    return findings, checked, len(findings)


def check_cascade_pipelines_retired(vault: Path, dev_spec_uid: str) -> tuple[list[str], bool]:
    """Check that triggered doc + test pipeline activations are status:retired.

    Returns (findings, all_retired).
    Called from build-release.py Lane B pre-flip gate.
    """
    findings: list[str] = []

    # Find the dev-spec entry
    spec_path = vault / "vault" / "files" / f"{dev_spec_uid}.md"
    if not spec_path.exists():
        return [f"  [WARN] dev-spec {dev_spec_uid} not found; cascade check skipped"], True

    try:
        text = spec_path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        fm = m.group(1) if m else ""
    except Exception:
        return [f"  [WARN] dev-spec {dev_spec_uid} unreadable; cascade check skipped"], True

    doc_activation_uids = _get_list(fm, "triggered_doc_activation_uids")
    test_activation_uids = _get_list(fm, "triggered_test_activation_uids")

    if not doc_activation_uids and not test_activation_uids:
        return [], True  # No triggered activations — single-pipeline cycle; skip

    all_retired = True
    for uid_list, label in [(doc_activation_uids, "doc-pipeline"),
                             (test_activation_uids, "test-pipeline")]:
        for act_uid in uid_list:
            act_path = vault / "vault" / "files" / f"{act_uid}.md"
            if not act_path.exists():
                findings.append(f"  [WARN] {label} activation {act_uid} not found")
                continue
            try:
                act_text = act_path.read_text(encoding="utf-8")
                act_m = re.match(r"^---\n(.*?)\n---", act_text, re.DOTALL)
                act_fm = act_m.group(1) if act_m else ""
                status = _get_scalar(act_fm, "status") or "unknown"
            except Exception:
                findings.append(f"  [WARN] {label} activation {act_uid} unreadable")
                continue
            if status != "retired":
                findings.append(
                    f"  [FAIL] {label} activation {act_uid} status={status!r} "
                    f"(must be retired before ship-flip — V3 build-release Lane B gate)"
                )
                all_retired = False

    return findings, all_retired
