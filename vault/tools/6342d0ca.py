#!/usr/bin/env python3
"""
---
uid: 6342d0ca
name: derive-subsystem-registry
type: tool
status: active
owner: talos
domain: "derive-subsystem-registry.py — Going-forward subsystem-registry.jsonl deriver."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/6342d0ca.py"
script_path: vault/tools/6342d0ca.py
spawnable_by:
  - all-executives
input:
  type: object
  description: "See tool usage for argument details"
created: 2026-05-27
created_by: talos-t10
governed_by: d5e1b4a3
member_of:
  - c7e4f9a2
schema_version: 2
---
"""
from __future__ import annotations

"""
derive-subsystem-registry.py — Going-forward subsystem-registry.jsonl deriver.

Called by rebuild-vault.py on every comprehensive vault rebuild. Reads every
shipped Tropo-OS release entry (status:shipped or status:done) + derives
subsystem rows via 1-hop member_of: traversal over capabilities_touched:
(or release-plan's capabilities_touched: when shipped_release_plan: is declared).

Authors v1.50.0 by Argus A79 per registry primitive establishment cycle. Replaces
the one-time backfill script at agents/argus/.tropo-capsule/workspace/ — that
script's job ends when its initial population lands; this script's job is the
going-forward derivation that keeps the registry in sync by construction.

OUTPUT:
    .tropo-studio/registries/subsystem-registry.jsonl
    (overwritten each rebuild; substrate-honest regeneration from current state)

USAGE:
    python3 .tropo/scripts/derive-subsystem-registry.py [--vault-root <path>]
    Returns: 0 on success; 1 on derivation error; 2 on filesystem/IO error.

INVARIANTS (per registry.capsule v1.0 + release.capsule v3.4):
    - One row per (release, subsystem) tuple
    - subsystem_uid is one of 7 canonical hubs (per release.capsule v3.4 Rule 12)
    - Row shape per registry.capsule v1.0 §2 (8 fields)
    - Sorted by shipped_at + version + subsystem_name for stable diff
    - Idempotent (re-running produces same output unless substrate changed)

REGISTRY WRAPPER ENTRY:
    vault/files/880a9e5a.md (type:registry; declares this script as producer)
"""


import json
import secrets
import sys
from pathlib import Path

_CANONICAL_HUBS_FALLBACK = {
    "8dd772a0": "tropo-governance",
    "dbc1cbbf": "tropo-rendering",
    "2d083137": "tropo-work",
    "99ed55fd": "tropo-agents",
    "76bab75f": "tropo-playbooks",
    "1aba710c": "tropo-library",
    "f87e33f0": "tropo-documentation",
}

_VAULT_ROOT_DEFAULT = Path(__file__).resolve().parents[2]


def _discover_canonical_hubs(vault_root: Path) -> dict[str, str]:
    """Discover subsystem hubs dynamically by scanning vault/files/ for subsystem_name: field."""
    hubs: dict[str, str] = {}
    files_dir = vault_root / "vault" / "files"
    if not files_dir.exists():
        return {}
    for f in files_dir.glob("*.md"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "subsystem_name:" not in text:
            continue
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---\n", 4)
        if end == -1:
            continue
        uid = None
        name = None
        state = None
        status = None
        for line in text[4:end].split("\n"):
            if line.startswith("uid:"):
                uid = line.split(":", 1)[1].strip().strip("\"'")
            elif line.startswith("subsystem_name:"):
                name = line.split(":", 1)[1].strip().strip("\"'")
            elif line.startswith("state:"):
                state = line.split(":", 1)[1].strip().strip("\"'")
            elif line.startswith("status:"):
                status = line.split(":", 1)[1].strip().strip("\"'")
        if uid and name and state != "archived" and status != "archived":
            hubs[uid] = name
    return hubs


# Canonical subsystem hubs — active only (excludes state/status:archived); 10 active hubs as of v1.15
CANONICAL_HUBS = _discover_canonical_hubs(_VAULT_ROOT_DEFAULT) or _CANONICAL_HUBS_FALLBACK


def resolve_vault_root(args: list[str]) -> Path:
    """Resolve vault root. Explicit --vault-root wins; else script-location-derived."""
    if "--vault-root" in args:
        idx = args.index("--vault-root")
        if idx + 1 < len(args):
            return Path(args[idx + 1]).resolve()
    # Script lives at .tropo/scripts/derive-subsystem-registry.py → 2 up = vault root
    return Path(__file__).resolve().parents[2]


def parse_frontmatter(file_path: Path) -> dict:
    """Minimal YAML frontmatter parser. Top-level scalars + list values + nested maps."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    fm_text = text[4:end]

    fm: dict = {}
    current_key = None

    for raw_line in fm_text.split("\n"):
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        if not raw_line.startswith(" ") and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                current_key = key
                fm[key] = []
            else:
                current_key = None
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                fm[key] = value
        elif (raw_line.startswith("  ") or raw_line.startswith("- ")) and current_key:
            # v1.51.0 amendment (vela-v51 2026-05-23): accept zero-indent block-lists in addition
            # to 2-space indent. PyYAML default for yaml.dump produces zero-indent list items
            # ("member_of:\n- uid1\n- uid2"); 2-space form is human-edited convention. Same bug
            # class A80 fixed in migration script for v1.14 schema split same day — audit
            # discipline: zero-indent block-list trap exists in any regex-based YAML parser.
            stripped = raw_line.strip()
            if stripped.startswith("- "):
                item = stripped[2:].strip()
                if " #" in item:
                    item = item.split(" #")[0].strip()
                if item.startswith('"') and item.endswith('"'):
                    item = item[1:-1]
                elif item.startswith("'") and item.endswith("'"):
                    item = item[1:-1]
                if isinstance(fm.get(current_key), list):
                    fm[current_key].append(item)
            elif ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip().strip('"').strip("'")
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                if isinstance(fm.get(current_key), list) and not fm[current_key]:
                    fm[current_key] = {}
                if isinstance(fm.get(current_key), dict):
                    fm[current_key][key] = value
    return fm


_UID_PATH_CACHE: dict[str, Path] = {}


def resolve_uid_to_file(uid: str, vault_root: Path) -> Path | None:
    """Resolve UID to file. Fast-path vault/files/, fallback kernel dirs."""
    if uid in _UID_PATH_CACHE:
        return _UID_PATH_CACHE[uid]

    fast = vault_root / "vault" / "files" / f"{uid}.md"
    if fast.exists():
        _UID_PATH_CACHE[uid] = fast
        return fast

    kernel_dirs = [
        (vault_root / ".tropo" / "capsules", "*.capsule.md"),
        (vault_root / ".tropo" / "playbooks", "*.playbook.md"),
        (vault_root / ".tropo-studio", "*.md"),
        (vault_root / ".tropo", "*.md"),
        (vault_root / "agents", "agent-boot.extension.md"),
    ]
    for scan_dir, glob_pattern in kernel_dirs:
        if not scan_dir.exists():
            continue
        for candidate in scan_dir.glob(f"**/{glob_pattern}"):
            if not candidate.is_file():
                continue
            fm = parse_frontmatter(candidate)
            if fm.get("uid") == uid:
                _UID_PATH_CACHE[uid] = candidate
                return candidate
    return None


def derive_subsystems_from_capabilities(capabilities: list[str], vault_root: Path) -> set[str]:
    """For each capability UID, read member_of: + subsystem_hub: → return set of canonical-hub UIDs.

    v1.51.0 amendment (vela-v51 2026-05-23): added `subsystem_hub:` field reading per A80's
    v1.14 schema split same session. The schema split moved subsystem-hub edges from
    `member_of:` → `subsystem_hub:` for 1059 migrated entries; this deriver was a reader
    that wasn't audited in the writer-change pass. Symptom: post-v1.14 derivation produced
    only 10 rows across 5 releases (was 72 rows across 29 releases before); v1.46.0 release
    entry 82e44710 hit R11 + R12 enforcement gate at v1.51 build because its capability
    member-of edges no longer resolved. Discipline: when changing a writer, audit ALL readers.
    """
    hubs: set[str] = set()
    for cap_uid in capabilities:
        if not (len(cap_uid) == 8 and all(c in "0123456789abcdef" for c in cap_uid.lower())):
            continue
        cap_file = resolve_uid_to_file(cap_uid, vault_root)
        if cap_file is None:
            continue
        cap_fm = parse_frontmatter(cap_file)
        # Read member_of: (canonical-content + project parentage edges)
        member_of = cap_fm.get("member_of", [])
        if isinstance(member_of, list):
            for parent_uid in member_of:
                if parent_uid in CANONICAL_HUBS:
                    hubs.add(parent_uid)
        # Read subsystem_hub: (v1.14 schema split — subsystem-hub edges live here post-2026-05-23)
        subsystem_hub = cap_fm.get("subsystem_hub", [])
        if isinstance(subsystem_hub, list):
            for parent_uid in subsystem_hub:
                if parent_uid in CANONICAL_HUBS:
                    hubs.add(parent_uid)
        elif isinstance(subsystem_hub, str):
            # Defensive: single-string form (capsule v2.5 allows list OR scalar)
            if subsystem_hub in CANONICAL_HUBS:
                hubs.add(subsystem_hub)
    return hubs


def scan_shipped_releases(vault_root: Path) -> list[dict]:
    """Find every type:release + status:(shipped|done) + title startswith 'Tropo-OS v' entry.

    Includes legacy status:done releases per v1.27.0 validator pattern.
    Resolves derivation source: release-plan's capabilities_touched/hub_summaries
    when shipped_release_plan declared; else release entry's own.
    """
    releases = []
    vault_files = vault_root / "vault" / "files"
    if not vault_files.exists():
        return releases

    for f in sorted(vault_files.glob("*.md")):
        fm = parse_frontmatter(f)
        if fm.get("type") != "release":
            continue
        if fm.get("status") not in ("shipped", "done"):
            continue
        title = fm.get("title", "")
        if not title.startswith("Tropo-OS v"):
            continue

        capabilities = fm.get("capabilities_touched", []) if isinstance(fm.get("capabilities_touched"), list) else []
        hub_summaries = fm.get("hub_summaries", {}) if isinstance(fm.get("hub_summaries"), dict) else {}

        # Prefer release-plan derivation when declared
        plan_uid = fm.get("shipped_release_plan", "")
        if plan_uid and (len(plan_uid) == 8 and all(c in "0123456789abcdef" for c in plan_uid.lower())):
            plan_file = resolve_uid_to_file(plan_uid, vault_root)
            if plan_file:
                plan_fm = parse_frontmatter(plan_file)
                plan_caps = plan_fm.get("capabilities_touched", []) if isinstance(plan_fm.get("capabilities_touched"), list) else []
                plan_hubs = plan_fm.get("hub_summaries", {}) if isinstance(plan_fm.get("hub_summaries"), dict) else {}
                if plan_caps or plan_hubs:
                    capabilities = plan_caps or capabilities
                    hub_summaries = plan_hubs or hub_summaries

        # subsystems_touched: directly-declared hub UIDs on release entry (fallback when
        # capabilities_touched contains prose names or L0 projects that don't resolve to
        # canonical-hub edges). v1.51.0 amendment (vela-v51 2026-05-23): pre-existing
        # registry-derivation gap for releases v1.43-v1.47 surfaced at v1.51 build pre-flight
        # — capabilities were prose-named (e.g., 'pipeline.capsule', '.tropo/scripts/foo.py')
        # which can't resolve via UID lookup. Release entry's subsystems_touched: is the
        # canonical-record-of-record declaration; use it as fallback when derivation produces
        # zero hubs but declaration has them.
        declared_subsystems = fm.get("subsystems_touched", []) if isinstance(fm.get("subsystems_touched"), list) else []

        releases.append({
            "file": f,
            "uid": fm.get("uid", ""),
            "version": fm.get("release_version", "") or fm.get("ships_in_v", ""),
            "shipped_at": fm.get("shipped_at") or fm.get("created", ""),
            "capabilities_touched": capabilities,
            "hub_summaries": hub_summaries,
            "declared_subsystems": declared_subsystems,
            "title": title,
        })
    return releases


def build_registry_rows(releases: list[dict], vault_root: Path) -> list[dict]:
    """Derive subsystem rows for each release. Returns sorted list of row dicts."""
    rows = []
    for rel in releases:
        if not rel["uid"]:
            continue
        version = rel["version"].lstrip("v").strip()
        if not version:
            continue
        touched_hubs = derive_subsystems_from_capabilities(rel["capabilities_touched"], vault_root)
        derived_from = "capabilities_touched"
        # Fallback: if derivation produced zero hubs but release entry declared subsystems_touched,
        # use the declaration (v1.51.0 amendment per vela-v51 2026-05-23). Closes the gap where
        # capabilities are prose-named/L0-projects that don't resolve to canonical-hub edges.
        if not touched_hubs and rel.get("declared_subsystems"):
            for hub_uid in rel["declared_subsystems"]:
                if hub_uid in CANONICAL_HUBS:
                    touched_hubs.add(hub_uid)
            if touched_hubs:
                derived_from = "release-entry-subsystems_touched-fallback"
        for hub_uid in sorted(touched_hubs):
            summary = rel["hub_summaries"].get(hub_uid) if rel["hub_summaries"] else None
            row = {
                "registry_uid": secrets.token_hex(4),
                "release_uid": rel["uid"],
                "release_version": version,
                "subsystem_uid": hub_uid,
                "subsystem_name": CANONICAL_HUBS[hub_uid],
                "summary": summary,
                "derived_from": derived_from,
                "shipped_at": rel["shipped_at"][:10] if rel["shipped_at"] else "",
            }
            rows.append(row)
    rows.sort(key=lambda r: (r["shipped_at"], r["release_version"], r["subsystem_name"]))
    return rows


def main() -> int:
    args = sys.argv[1:]
    vault_root = resolve_vault_root(args)
    registry_path = vault_root / ".tropo-studio" / "registries" / "subsystem-registry.jsonl"

    quiet = "--quiet" in args
    if not quiet:
        print(f"derive-subsystem-registry.py — v1.0 (v1.50.0 cycle; Argus A79)")
        print(f"Vault root: {vault_root}")
        print(f"Target:     {registry_path}")

    releases = scan_shipped_releases(vault_root)
    if not releases:
        print("derive-subsystem-registry: ERROR — no shipped releases found", file=sys.stderr)
        return 1

    rows = build_registry_rows(releases, vault_root)

    try:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        with registry_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"derive-subsystem-registry: ERROR — write failed: {e}", file=sys.stderr)
        return 2

    if not quiet:
        print(f"  Scanned {len(releases)} shipped releases.")
        print(f"  Wrote {len(rows)} rows across {len(set(r['release_uid'] for r in rows))} releases.")
        print(f"  ✓ subsystem-registry.jsonl regenerated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
