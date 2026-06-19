#!/usr/bin/env python3
"""
---
uid: f5e2d1c7
title: validate-capability-membership — Tool
name: validate-capability-membership
type: tool
status: active
owner: argus
domain: Validate the typed capability ↔ subsystem membership graph; enforces Checks 19-23 + Rule 11/12 + structural-consistency.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/f5e2d1c7.py [--soft] [--vault-path PATH]
script_path: vault/tools/f5e2d1c7.py
input:
  type: object
  properties:
    soft:
      type: boolean
      description: Override v1.10 STRICT default to SOFT (WARN only)
    vault-path:
      type: string
output:
  type: object
  properties:
    verdict:
      type: string
      enum:
      - pass
      - errors
      - warnings-only
    errors:
      type: integer
    warnings:
      type: integer
destructive: false
audit_required: false
writes_scope: []
governance_category: query
description: 'Validates the typed capability ↔ subsystem membership graph introduced in v1.8. Every governed primitive (capsule definition, action, skill, playbook, sa.* agent, KB article, library doc) MUST declare its owning subsystem via member_of: including exactly one of the 7 subsystem hub UIDs. Plus release-plan.capsule v1.3 Checks 19-23 (capabilities_touched + hub_summaries) + Rule 11 (release ↔ registry) + Rule 12 (subsystems_touched derivation) + structural-consistency check. v1.10 Pure Enforcement: STRICT mode default; build refuses on any ERROR.'
domain_tags:
- validator
- capability-membership
- subsystem-graph
- hub-membership
- build-pipeline-pre-flight
- v1.10-strict
trigger_description: 'Reach for this when verifying typed-graph integrity — every capability has exactly one subsystem hub in member_of:, every release plan declares capabilities_touched + hub_summaries, every release entry''s subsystems_touched derives correctly. Run before any architectural call that touches member_of: arrays, before any release-plan or release entry lock, and as part of build-release.py Step 0 pre-flight gate. Pairs with validate-canonical-l0.py (L0 structural-shape) + validate-release-manifest.py (ship-artifact graph) as the structural-validator quartet. Default mode v1.10+ is STRICT (build refuses on ERROR); --soft flag returns to v1.8-v1.9 WARN-only.'
created: 2026-05-09
created_by: argus-a53
modified: 2026-05-09
modified_by: argus-a53
governed_by: d5e1b4a3
capsule_version: '2.5'
schema_version: 2
extraction_scope: ship
member_of:
- c7e4f9a2
tags:
- tool
- cli
- validator
- capability-membership
- v1.10-strict
- build-pipeline-pre-flight
- v1.15-stream-b
subsystem_hub:
- 8dd772a0
---
"""
from __future__ import annotations

"""
validate-capability-membership.py — v1.10 Pure Enforcement

Validates the typed capability ↔ subsystem membership graph introduced in v1.8
(Capability Subsystem Membership cycle; per release.capsule v3.4 Rule 12 +
release-plan.capsule v1.3 Checks 19/20/21/22/23 + subsystem-hub.capsule v1.4).

v1.10 Pure Enforcement (Argus A50 + Mike pair-design 2026-05-07; brief 44b2623e):
  - Mode default flips from SOFT (v1.8-v1.9) to STRICT (v1.10+).
  - Checks 20-23 + Rule 11 + Rule 12 + structural-consistency check ERROR
    in STRICT mode (build refuses if any fail).
  - GRANDFATHER pre-v1.9.2 releases per Q8 lock 2026-05-07: structural-
    consistency check returns INFO ("grandfathered") on a676a5f2 / 14e5f79c
    / 1b4bb15a / f604209d. v1.9.2 onward enforces strictly.
  - Substrate-membership-backfill gap (Operating Principles + KB articles +
    scripts lacking direct hub member_of) routed to v1.11 Substrate Repair.

Per [v1.8 brief fd2d9e77](../../vault/files/fd2d9e77.md) + Mike-A46 mid-cycle elevation 2026-05-05:
  - Every governed primitive (capsule definition, action, skill, playbook,
    sa.* agent, KB article, library doc) MUST declare its owning subsystem
    via `member_of:` including exactly one of the 7 subsystem hub UIDs
    (6 v1.7-anchored hubs + tropo-documentation `f87e33f0` added v1.8).
  - release-plan.capsule v1.3 declares `capabilities_touched: [UIDs]` +
    `hub_summaries: {hub_uid: text}` (NEW v1.9.2; Check 21/22/23 target).
  - release.capsule v3.4 declares derived `subsystems_touched: [UIDs]`
    (auto-populated via 1-hop graph traversal from capabilities_touched
    by `.tropo/scripts/dev-pipeline/update-subsystem-canonical-docs.py`
    NEW v1.9.2 dev-pipeline step `9d4f7e21`).

Exit codes:
  0 — clean (zero ERRORs in current mode)
  1 — at least one ERROR

Usage:
  python3 .tropo/scripts/validate-capability-membership.py [--soft] [--json]

  Default mode is STRICT (v1.10+ semantics). Pass --soft for v1.8-v1.9
  semantics (Checks 1-19 only at WARNING; structural-consistency suppressed).
  Build pipelines invoke without flags; v1.X+ cycles can opt into --soft for
  specific scoped checks.

Notes:
  - Reads vault/00-index.jsonl + governed primitive frontmatter +
    `subsystem-registry.jsonl` at `.tropo-studio/registries/` (Rule 11 cross-check; moved from vault root at v1.50.0 per registry primitive establishment).
  - Cross-references release-plan + release entries for capabilities_touched
    consistency + derived subsystems_touched (Rule 12 + structural-consistency).
  - Documentation-class capabilities placeholder-tagged at member_of: [1aba710c]
    (Tropo Library hub) per v1.8 brief D4 PUNT — these emit INFO not WARNING
    until v1.9 Documentation thesis decides their final home (now landed at
    v1.9.0 — placeholder no longer needed; INFO-level retained for honest record).
"""


import json
import re
import sys
import subprocess
from pathlib import Path
from typing import NamedTuple

try:
    import yaml  # PyYAML — robust frontmatter parsing for v1.10
except ImportError:
    yaml = None


# Vault root = directory containing .tropo/scripts/ (this file's grandparent)
VAULT_ROOT = Path(__file__).resolve().parent.parent.parent

# Fallback hub list (7 original hubs) used when vault is unreachable at init
_SUBSYSTEM_HUBS_FALLBACK = {
    "8dd772a0": "tropo-governance",
    "dbc1cbbf": "tropo-rendering",
    "2d083137": "tropo-work",
    "99ed55fd": "tropo-agents",
    "76bab75f": "tropo-playbooks",
    "1aba710c": "tropo-library",
    "f87e33f0": "tropo-documentation",
}


def _discover_subsystem_hubs(vault_root: Path) -> dict[str, str]:
    """Discover subsystem hubs dynamically by scanning vault/files/ for subsystem_name: field."""
    hubs: dict[str, str] = {}
    files_dir = vault_root / "vault" / "files"
    if not files_dir.exists():
        return {}
    for f in files_dir.glob("*.md"):
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        if "subsystem_name:" not in text:
            continue
        if not text.startswith("---"):
            continue
        lines = text.split("\n")
        end_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_idx = i
                break
        if end_idx is None:
            continue
        uid = None
        name = None
        state = None
        status = None
        for line in lines[1:end_idx]:
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


# Dynamic subsystem hub set — active hubs only (excludes state/status:archived); 10 active hubs as of v1.15
SUBSYSTEM_HUBS = _discover_subsystem_hubs(VAULT_ROOT) or _SUBSYSTEM_HUBS_FALLBACK

# tropo-subsystems root (the parent of the 6 hubs)
SUBSYSTEMS_ROOT = "aae9a37b"

# Documentation-class capabilities default to tropo-library placeholder per v1.8 D4
DOCUMENTATION_PLACEHOLDER_HUB = "1aba710c"

# v1.50.0 cycle 2026-05-22 — grandfather threshold extended from (1,9,2) → (1,40,0)
# per Mike-A79 substrate-honesty walk authorization 2026-05-22.
#
# RATIONALE: v1.10-v1.39 shipped during the 10-cycle subsystem-registry bypass
# pattern. The registry file was specified across capsules (release.capsule v3.3
# Rule 11; v3.4 Rule 12; subsystem-hub.capsule v1.5 bidirectional pair) but never
# built as governed substrate. Authors bypassed via TROPO_SKIP_ENFORCEMENT_GATE=1
# because the validator couldn't enforce against a missing file. capabilities_touched
# was systemically under-populated (empty arrays OR prose strings OR maximalist
# 184-UID dumps that don't satisfy 1-hop derivation).
#
# Reconstructing strict-compliance-shaped historical capabilities_touched for
# v1.10-v1.39 is archaeology, not enforcement — judgment-call work that risks
# fabrication. The substrate-honest move is acknowledging the historical pattern
# at this threshold + enforcing strict going forward.
#
# v1.40+ enforces strict because:
#   - Mike-V50 Path B directive 2026-05-22 ("v1.49 ships clean or v1.49 doesn't ship")
#     broke the bypass pattern at policy level
#   - Argus A79 v1.50.0 registry primitive establishment 2026-05-22 broke it at
#     substrate level (registry.capsule + Registries hub + 5 wrapper entries +
#     subsystem-registry.jsonl populated + rebuild-vault.py derivation path)
#   - Future releases inherit the structural fix by construction
#
# Threshold extension authority: Mike-A79 verbatim 2026-05-22 — "I agree. I am
# fine with that. we get it right moving forward, that's most important."
#
# DO NOT EXTEND FURTHER without explicit Mike approval + v1.X cycle scope.
# Extending grandfathering becomes the new bypass-pattern; the discipline is
# pinning the line at v1.40 with explicit historical rationale.
#
# Prior threshold: v1.9.2 (v1.10 Q8 lock 2026-05-07 per argus-a49).
GRANDFATHER_VERSION_THRESHOLD = (1, 40, 0)

# Explicit UID set for grandfathered releases that lack a parseable release_version
# (e.g., example/sample releases like Meetly/Gleam/Helm/Solace at 1.0.0; older
# Tropo-OS releases without strict semver). Members are also covered by version
# comparison; this set is the explicit fallback.
GRANDFATHERED_RELEASES_EXPLICIT = frozenset({
    "a676a5f2",  # v1.7 release entry
    "14e5f79c",  # v1.8 release entry
    "1b4bb15a",  # v1.9.0 release entry
    "f604209d",  # v1.9.1 release entry
    # v1.50.0 additions — unversioned releases shipped during bypass-pattern era;
    # surfaced by validator R11 sweep; substrate-honest grandfathering per Mike-A79
    # walk 2026-05-22 (same rationale as version-threshold extension above).
    "1d8a2904",  # unversioned; shipped pre-v1.40
    "6823f75d",  # unversioned; shipped pre-v1.40
    "c7d1f0a4",  # unversioned; shipped pre-v1.40
    "db32a917",  # unversioned; shipped pre-v1.40
    "bcdf390c",  # unversioned; 11 prose-caps; v1.51+ research candidate
    "f7c4e3a8",  # unversioned; 10 prose-caps; v1.51+ research candidate
    # v1.65 additions — ancient v1.1.0 releases using `version:` field (not
    # `release_version:`); done→shipped migration exposed the version-field mismatch
    # (Vela V59 flag 2026-06-07). 8e27e00e is a self-declared duplicate of 8a70af21.
    "8a70af21",  # Tropo-OS v1.1.0; version: "1.1.0" (not release_version:)
    "8e27e00e",  # Tropo-OS v1.1.0 duplicate — recycle pending
})


def _parse_semver(version_str: str | None) -> tuple[int, int, int] | None:
    """Parse '1.9.2' or '1.9' or '1.10.0' → (1,9,2)/(1,9,0)/(1,10,0). None on failure."""
    if not version_str:
        return None
    parts = str(version_str).strip().lstrip("v").split(".")
    try:
        major = int(parts[0]) if len(parts) >= 1 else 0
        minor = int(parts[1]) if len(parts) >= 2 else 0
        patch = int(parts[2]) if len(parts) >= 3 else 0
        return (major, minor, patch)
    except (ValueError, IndexError):
        return None


def is_grandfathered_release(uid: str, fm: dict) -> bool:
    """True if this release entry is pre-v1.9.2 (grandfather threshold).

    Checks release_version: first (canonical), then version: fallback (legacy
    pre-v1.7 releases used version: before release_version: was established).
    """
    if uid in GRANDFATHERED_RELEASES_EXPLICIT:
        return True
    parsed = _parse_semver(fm.get("release_version"))
    if parsed is not None and parsed < GRANDFATHER_VERSION_THRESHOLD:
        return True
    # Fallback: some ancient entries use version: instead of release_version:
    parsed = _parse_semver(fm.get("version"))
    if parsed is not None and parsed < GRANDFATHER_VERSION_THRESHOLD:
        return True
    return False


def is_grandfathered_release_plan(fm: dict) -> bool:
    """True if this release plan targets a pre-grandfather-threshold release.

    v1.50.0 amendment (Argus A79 2026-05-22 per Mike-A79 substrate-honesty walk):
    fall back to release_version then title-parsing when target_release isn't declared
    (legacy release-plans pre-date that field convention). Threshold itself extended
    to (1,40,0) per GRANDFATHER_VERSION_THRESHOLD docstring.
    """
    # Primary: target_release field (post-v1.9.x convention)
    parsed = _parse_semver(fm.get("target_release"))
    if parsed is not None and parsed < GRANDFATHER_VERSION_THRESHOLD:
        return True
    # Fallback 1: release_version field (legacy release-plan shape)
    parsed = _parse_semver(fm.get("release_version"))
    if parsed is not None and parsed < GRANDFATHER_VERSION_THRESHOLD:
        return True
    # Fallback 2: parse from title "Tropo-OS vX.Y.Z — ..."
    title = str(fm.get("title") or "")
    if "Tropo-OS v" in title:
        try:
            version_part = title.split("Tropo-OS v", 1)[1].split(" ", 1)[0].split("—")[0].strip()
            parsed = _parse_semver(version_part)
            if parsed is not None and parsed < GRANDFATHER_VERSION_THRESHOLD:
                return True
        except (IndexError, ValueError):
            pass
    # Plans authored under capsule v1.2 are all pre-v1.9.2 (v1.3 came at v1.9.2)
    if str(fm.get("capsule_version") or "") == "1.2":
        return True
    return False

# release-plan.capsule v1.3 Check 22: hub_summaries entries within length bounds
HUB_SUMMARY_MIN_CHARS = 50
HUB_SUMMARY_MAX_CHARS = 1500

# v1.11 Check 24: L1 canonical entry must reference all active subsystem hub UIDs
# per Mike-A50 L1/L2/L3 documentation hierarchy 2026-05-08. Drift prevention through
# UID-referenced one-way flow (L1 → L2 → L3): if L1 stops referencing a hub, the
# hierarchy breaks for that subsystem. STRICT mode ERROR; build refuses.
L1_CANONICAL_ENTRY_UID = "eca73d77"


class Finding(NamedTuple):
    severity: str  # "ERROR" / "WARNING" / "INFO"
    check: str
    target: str  # file path or UID
    message: str


def parse_frontmatter(text: str) -> dict | None:
    """Extract YAML frontmatter from a markdown file. Returns dict or None.

    v1.10 update: uses PyYAML for robust handling of inline comments + nested
    dicts (hub_summaries) + multi-line list comments. Falls back to a minimal
    line-based parser if yaml unavailable (extracts only top-level scalars +
    flat lists; nested structures become None).
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    fm_text = text[4:end]

    if yaml is not None:
        try:
            parsed = yaml.safe_load(fm_text)
            if isinstance(parsed, dict):
                return parsed
        except yaml.YAMLError:
            pass  # fall through to minimal parser
        return None

    # Fallback minimal parser (yaml not installed)
    fm: dict = {}
    current_list_key = None
    for line in fm_text.split("\n"):
        if not line or line.lstrip().startswith("#"):
            continue
        if current_list_key and line.startswith("  - "):
            value = line[4:].strip()
            value = re.sub(r"\s+#.*$", "", value).strip().strip('"').strip("'")
            if not isinstance(fm.get(current_list_key), list):
                fm[current_list_key] = []
            fm[current_list_key].append(value)
            continue
        if current_list_key and not line.startswith("  ") and not line.startswith("\t"):
            current_list_key = None
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            value = re.sub(r"\s+#.*$", "", value).strip()
            if value == "" or value == "[]":
                fm[key] = [] if value == "[]" else None
                if value == "":
                    current_list_key = key
            else:
                if value.startswith("[") and value.endswith("]"):
                    inner = value[1:-1]
                    fm[key] = [
                        item.strip().strip('"').strip("'")
                        for item in inner.split(",")
                        if item.strip()
                    ]
                else:
                    fm[key] = value.strip('"').strip("'")
    return fm


def collect_governed_primitives() -> list[Path]:
    """Returns list of paths to governed primitive markdown files."""
    primitive_dirs = [
        VAULT_ROOT / ".tropo/capsules",
        VAULT_ROOT / ".tropo/actions",
        VAULT_ROOT / ".tropo/skills",
        VAULT_ROOT / ".tropo/playbooks",
        VAULT_ROOT / ".tropo/kb",
        VAULT_ROOT / ".tropo/definitions",
        VAULT_ROOT / "playbooks",
        VAULT_ROOT / "library",
    ]
    paths: list[Path] = []
    for d in primitive_dirs:
        if not d.exists():
            continue
        paths.extend(p for p in d.rglob("*.md") if "99-archive" not in str(p))
    # sa.* agent activation files
    sa_dir = VAULT_ROOT / "agents/sa"
    if sa_dir.exists():
        for sa_subdir in sa_dir.iterdir():
            if sa_subdir.is_dir() and sa_subdir.name.startswith("sa."):
                activation = sa_subdir / f"{sa_subdir.name}.md"
                if activation.exists():
                    paths.append(activation)
    return sorted(set(paths))


def is_documentation_class(path: Path) -> bool:
    """Documentation-class capabilities (KB articles, library docs) per v1.8 D4."""
    parts = set(path.parts)
    return ".tropo" in parts and "kb" in parts or "library" in parts


def validate_capability(path: Path) -> list[Finding]:
    """Validates a single governed primitive against v1.8 capability membership rules."""
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        findings.append(Finding("WARNING", "C0", str(path), f"could not read file: {e}"))
        return findings
    fm = parse_frontmatter(text)
    if fm is None:
        # No frontmatter — likely an index file / pointer; skip
        return findings
    if not fm.get("uid"):
        # No UID — not a governed primitive; skip
        return findings

    rel_path = path.relative_to(VAULT_ROOT)
    member_of = fm.get("member_of") or []
    if isinstance(member_of, str):
        member_of = [member_of]

    # Filter to subsystem hub UIDs in member_of
    hubs_in_member_of = [uid for uid in member_of if uid in SUBSYSTEM_HUBS]

    if len(hubs_in_member_of) == 0:
        severity = "INFO" if is_documentation_class(path) else "WARNING"
        check = "C1-doc-placeholder" if is_documentation_class(path) else "C1-missing-hub"
        msg = (
            "documentation-class capability missing subsystem hub in member_of: "
            f"defaulting to tropo-library placeholder ({DOCUMENTATION_PLACEHOLDER_HUB}) "
            "per v1.8 brief D4 PUNT; v1.9 Documentation thesis decides final home"
            if is_documentation_class(path)
            else "missing subsystem hub in member_of: must include exactly one of "
            f"{sorted(SUBSYSTEM_HUBS.keys())}"
        )
        findings.append(Finding(severity, check, str(rel_path), msg))
    elif len(hubs_in_member_of) > 1:
        findings.append(Finding(
            "WARNING", "C2-multiple-hubs", str(rel_path),
            f"member_of: includes multiple subsystem hub UIDs {hubs_in_member_of}; "
            "a capability belongs to ONE subsystem (D2 of v1.8 brief). "
            "Cross-cutting expressed via relationships:, not member_of:. "
            "PRIMARY function determines hub."
        ))
    return findings


def load_member_of_map() -> dict[str, list[str]]:
    """Build {capability_uid: [member_of_uids]} from governed capability surfaces.

    v1.9.2 cross-folder UID resolver pattern: scans vault/files/ + .tropo/capsules/ +
    .tropo-studio/ + vault/tools/ + agents/*/agent-boot.extension.md.
    """
    mo_map: dict[str, list[str]] = {}
    scan_dirs = [
        VAULT_ROOT / "vault" / "files",
        VAULT_ROOT / ".tropo" / "capsules",
        VAULT_ROOT / ".tropo-studio",
    ]
    boot_ext_glob = list((VAULT_ROOT / "agents").glob("*/agent-boot.extension.md"))

    md_files: list[Path] = []
    for d in scan_dirs:
        if d.exists():
            md_files.extend(d.rglob("*.md"))
    md_files.extend(boot_ext_glob)
    tool_files = list((VAULT_ROOT / "vault" / "tools").glob("*.py"))

    # v1.15.1 Stream G: Studio-root *.md files with uid: frontmatter
    # (STUDIO.md, TROPO-CAPABILITIES.md, etc.) live at the Studio root by documented
    # exception. Closes the C20 + R12 ERRORs on 8dc4d66a + 20576f78 that v1.15
    # bypassed via TROPO_SKIP_ENFORCEMENT_GATE=1.
    md_files.extend(VAULT_ROOT.glob("*.md"))

    for path in md_files + tool_files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Governed Python tools embed the same YAML block inside a docstring.
        if path.suffix == ".py":
            start = text.find("---\n")
            if start == -1:
                continue
            text = text[start:]
        fm = parse_frontmatter(text)
        if not fm:
            continue
        uid = fm.get("uid")
        if not uid:
            continue
        # v1.51.0 amendment (vela-v51 2026-05-23): merge member_of: + subsystem_hub: edges.
        # A80's v1.14 schema split same-session moved subsystem-hub edges from member_of:
        # → subsystem_hub: for 1059 migrated entries. This loader was a reader not audited
        # in the writer-change pass; R12 derive_subsystems then saw zero hub-edges on all
        # migrated capabilities + every shipped release with declared subsystems_touched
        # tripped R12. Merging both fields restores derivation. Discipline pin: when
        # changing a writer, audit ALL readers (third symmetric defect this session arc).
        mo = fm.get("member_of") or []
        sh = fm.get("subsystem_hub") or []
        combined: list[str] = []
        if isinstance(mo, list):
            combined.extend(str(x).strip() for x in mo if x)
        if isinstance(sh, list):
            combined.extend(str(x).strip() for x in sh if x)
        elif isinstance(sh, str) and sh.strip():
            combined.append(sh.strip())
        if combined:
            mo_map[uid] = combined
    return mo_map


def derive_subsystems(capabilities: list[str], mo_map: dict[str, list[str]]) -> tuple[set[str], list[str]]:
    """1-hop graph traversal — capability → member_of → filter to hub UIDs.

    Returns (derived_hub_set, non_hub_capabilities). Non-hub capabilities are
    surfaced for audit trail (per v1.9.2 Round 2 fold pattern).
    """
    derived: set[str] = set()
    non_hub: list[str] = []
    for cap_uid in capabilities:
        mo = mo_map.get(cap_uid, [])
        hub_hits = [h for h in mo if h in SUBSYSTEM_HUBS]
        if hub_hits:
            derived.update(hub_hits)
        else:
            non_hub.append(cap_uid)
    return derived, non_hub


# Rule 14 path-pattern table (v3.7) — mirrors release.capsule.md §Rule 14 Path-Pattern Table.
# Patterns evaluated in declared order; first match wins; default fallback last.
# Pattern maintenance: update this list when capsule table is amended (capsule is canonical).
_RULE14_PATTERNS: list[tuple[str, str]] = [
    (r'^\.tropo/scripts/.*\.py$',           '76bab75f'),  # tropo-playbooks
    (r'^\.tropo/playbooks/.*\.md$',          '76bab75f'),  # tropo-playbooks
    (r'^\.tropo/skills/.*\.skill\.md$',      '76bab75f'),  # tropo-playbooks
    (r'^\.tropo/capsules/.*\.capsule\.md$',  '8dd772a0'),  # tropo-governance
    (r'.*/AGENTS\.md$',                      '8dd772a0'),  # tropo-governance
    (r'^STUDIO\.md$',                        '8dd772a0'),  # tropo-governance
    (r'^RELEASE-NOTES\.md$',                 '2d083137'),  # tropo-work
    (r'^\.tropo/.*',                         '8dd772a0'),  # tropo-governance (default fallback)
]
_COMPILED_RULE14 = [(re.compile(pat), hub) for pat, hub in _RULE14_PATTERNS]


def derive_kernel_path_hubs(kernel_paths: list[str]) -> set[str]:
    """Rule 14a: map kernel_substrate_touched paths to hub UIDs via path-pattern table."""
    hubs: set[str] = set()
    for path_str in kernel_paths:
        if not isinstance(path_str, str):
            continue
        for pattern, hub_uid in _COMPILED_RULE14:
            if pattern.search(path_str):
                hubs.add(hub_uid)
                break  # first match wins
    return hubs


def derive_pipeline_type_hubs(capabilities: list[str]) -> set[str]:
    """Rule 14b: for type:pipeline capability entries, read their subsystem_hub: field."""
    hubs: set[str] = set()
    vault_files_dir = VAULT_ROOT / "vault" / "files"
    for cap_uid in capabilities:
        if not (isinstance(cap_uid, str) and len(cap_uid) == 8):
            continue
        cap_path = vault_files_dir / f"{cap_uid}.md"
        if not cap_path.exists():
            continue
        try:
            text = cap_path.read_text(encoding='utf-8', errors='replace')
            fm = parse_frontmatter(text)
        except Exception:
            continue
        if not fm or fm.get('type') != 'pipeline':
            continue
        hub = fm.get('subsystem_hub')
        if hub and hub in SUBSYSTEM_HUBS:
            hubs.add(hub)
    return hubs


def derive_subsystems_extended(
    capabilities: list[str],
    kernel_paths: list[str],
    mo_map: dict[str, list[str]],
) -> tuple[set[str], list[str]]:
    """Rule 12 + Rule 14 (v3.7) extended derivation for releases >= v1.54.0.

    Union of:
    - Rule 12: capabilities_touched -> member_of -> hub (unchanged)
    - Rule 14a: kernel_substrate_touched paths -> path-pattern table -> hub
    - Rule 14b: type:pipeline capability entries -> subsystem_hub: field

    Returns (derived_hub_set, non_hub_capabilities).
    """
    rule12_hubs, non_hub = derive_subsystems(capabilities, mo_map)
    rule14a_hubs = derive_kernel_path_hubs(kernel_paths)
    rule14b_hubs = derive_pipeline_type_hubs(capabilities)
    return rule12_hubs | rule14a_hubs | rule14b_hubs, non_hub


def load_subsystem_registry() -> dict[str, set[str]]:
    """Load subsystem-registry.jsonl → {release_uid: {subsystem_uid, ...}}."""
    by_release: dict[str, set[str]] = {}
    registry_path = VAULT_ROOT / ".tropo-studio" / "registries" / "subsystem-registry.jsonl"
    if not registry_path.exists():
        return by_release
    try:
        with registry_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rel = row.get("release_uid")
                sub = row.get("subsystem_uid")
                if rel and sub:
                    by_release.setdefault(rel, set()).add(sub)
    except OSError:
        return by_release
    return by_release


def validate_release_plan(uid: str, fm: dict, mo_map: dict[str, list[str]], strict: bool) -> list[Finding]:
    """Validates a release-plan instance.

    v1.10 promotes Checks 19-23 to ERROR in strict mode:
      - Check 19: capabilities_touched non-empty at specify onward
      - Check 20: every UID in capabilities_touched resolves to a capability
        whose member_of contains a hub UID
      - Check 21: every derived subsystem hub has a hub_summaries entry
      - Check 22: hub_summaries entries within length bounds (50-1500 chars)
      - Check 23: substantive-amendment honor-system (INFO; never escalates)
    """
    findings: list[Finding] = []
    capsule_version_raw = fm.get("capsule_version")
    capsule_version = str(capsule_version_raw) if capsule_version_raw is not None else None
    # Pre-v1.2 release-plans grandfathered (no capabilities_touched contract)
    if capsule_version not in ("1.2", "1.3"):
        return findings

    # v1.10 Q8 lock: pre-v1.9.2 release plans grandfathered (Checks 19-23 skipped)
    if is_grandfathered_release_plan(fm):
        findings.append(Finding(
            "INFO", "GRANDFATHERED-pre-v1.9.2-plan", uid,
            f"release-plan v{capsule_version} targets pre-v1.9.2 release; "
            "Checks 19-23 skipped per Q8 lock 2026-05-07."
        ))
        return findings

    stage = fm.get("stage")
    capabilities_touched = fm.get("capabilities_touched") or []
    if isinstance(capabilities_touched, str):
        capabilities_touched = [capabilities_touched]

    severity_19_20 = "ERROR" if strict else "WARNING"

    # Check 19: non-empty at specify onward
    if stage in ("specify", "build", "done") and not capabilities_touched:
        findings.append(Finding(
            severity_19_20, "C19-empty-capabilities-touched", uid,
            f"release-plan v{capsule_version} at stage:{stage} has empty capabilities_touched; "
            "Check 19 violation (non-empty required at specify onward)"
        ))

    if not capabilities_touched:
        return findings

    # Check 20: every UID in capabilities_touched resolves to a capability with valid hub member_of
    derived, non_hub = derive_subsystems(capabilities_touched, mo_map)
    if non_hub:
        findings.append(Finding(
            severity_19_20, "C20-non-hub-capabilities", uid,
            f"release-plan v{capsule_version} capabilities_touched contains "
            f"{len(non_hub)} UID(s) without direct hub member_of (audit trail): "
            f"{non_hub[:5]}{'...' if len(non_hub) > 5 else ''}"
        ))

    # Checks 21/22 only apply to v1.3+ (hub_summaries field introduced v1.9.2)
    if capsule_version == "1.3" and stage in ("specify", "build", "done"):
        hub_summaries = fm.get("hub_summaries") or {}
        if isinstance(hub_summaries, dict):
            hs_keys = {str(k) for k in hub_summaries}
        else:
            hs_keys = set()
            findings.append(Finding(
                severity_19_20, "C21-hub-summaries-shape", uid,
                "release-plan v1.3 hub_summaries must be a dict {hub_uid: text}"
            ))
        # Check 21: every derived subsystem hub has a hub_summaries entry
        missing = [h for h in derived if h not in hs_keys]
        if missing:
            findings.append(Finding(
                severity_19_20, "C21-missing-hub-summaries", uid,
                f"release-plan v1.3 hub_summaries missing entries for derived subsystems: "
                f"{sorted(missing)} (Check 21 — honor-system at v1.9.x; ERROR at v1.10+)"
            ))
        # Check 22: length bounds
        if isinstance(hub_summaries, dict):
            for hub_uid, summary in hub_summaries.items():
                summary_str = str(summary or "")
                length = len(summary_str)
                if length < HUB_SUMMARY_MIN_CHARS:
                    findings.append(Finding(
                        severity_19_20, "C22-hub-summary-too-short", uid,
                        f"hub_summaries[{hub_uid}] length {length} < {HUB_SUMMARY_MIN_CHARS} "
                        "(Check 22 length bounds)"
                    ))
                elif length > HUB_SUMMARY_MAX_CHARS:
                    findings.append(Finding(
                        severity_19_20, "C22-hub-summary-too-long", uid,
                        f"hub_summaries[{hub_uid}] length {length} > {HUB_SUMMARY_MAX_CHARS} "
                        "(Check 22 length bounds)"
                    ))
        # Check 23: substantive-amendment discipline (honor-system; INFO forever per Mike-A49 Q5
        # over-engineering catch — soft principle prose, no mechanical rule, no validator escalation)
        findings.append(Finding(
            "INFO", "C23-substantive-amendment", uid,
            "Check 23 substantive-amendment honor-system: capabilities_touched should reflect "
            "substantively-amended primitives, not metadata-touched. Honor-system; not validator-enforced "
            "(per Mike-A49 Q5 over-engineering catch 2026-05-06)."
        ))

    return findings


def validate_release_entry(uid: str, fm: dict, mo_map: dict[str, list[str]],
                            registry: dict[str, set[str]], strict: bool) -> list[Finding]:
    """Validates a release entry against Rule 11 + Rule 12 + structural-consistency.

    v1.10 hard-gates (effective at B6 atomic-triangle ship):
      - Rule 11: every release at status:done has matching subsystem-registry rows
      - Rule 12: release.subsystems_touched matches derived(release-plan.capabilities_touched)
      - Structural-consistency: explicit assertion of Rule 12 invariant

    GRANDFATHER pre-v1.9.2: releases in GRANDFATHERED_RELEASES return INFO
    (structural-consistency skipped) per Q8 lock 2026-05-07.
    """
    findings: list[Finding] = []
    # v1.27.0 Stream A amendment: gate fires on both legacy "done" and post-v1.21.0 "shipped" conventions.
    # Pre-v1.27.0 the gate only fired on status:done; the post-v1.21.0 brief-based release pattern uses
    # status:shipped which silently bypassed enforcement. v1.27.0 closes this hole per Mike-A59 directive
    # 2026-05-12 ("dev-pipelines should be explicit, not lazy"). Stream E historical sweep backfilled
    # v1.16.0 → v1.24.0 entries before this gate ratched, so the cycle ships without surfacing legacy errors.
    if fm.get("status") not in ("done", "shipped"):
        return findings  # only check shipped releases

    severity = "ERROR" if strict else "WARNING"

    # Rules 11/12 govern Tropo-OS semver releases. Other release families
    # (for example kb-marketing-v14.1) share type:release but do not participate
    # in the OS subsystem registry.
    release_version = fm.get("release_version")
    if _parse_semver(release_version) is None:
        findings.append(Finding(
            "INFO", "NON-OS-release-family", uid,
            f"release_version={release_version!r} is not Tropo-OS semver; "
            "Rule 11 + Rule 12 subsystem checks skipped."
        ))
        return findings

    # A superseded archived duplicate is historical evidence, not the canonical
    # shipped release. The canonical successor remains subject to the hard gate.
    if fm.get("state") == "archived" and fm.get("superseded_by"):
        findings.append(Finding(
            "INFO", "SUPERSEDED-release-record", uid,
            f"archived release is superseded by {fm.get('superseded_by')}; "
            "Rule 11 + Rule 12 subsystem checks apply to the canonical successor."
        ))
        return findings

    # Grandfather pre-v1.9.2 (by version comparison OR explicit UID set)
    if is_grandfathered_release(uid, fm):
        version = release_version or "?"
        findings.append(Finding(
            "INFO", "GRANDFATHERED-pre-v1.9.2", uid,
            f"release entry release_version={version} pre-dates v1.9.2 mechanical derivation; "
            "Rule 11 + Rule 12 + structural-consistency check skipped per v1.10 Q8 lock 2026-05-07. "
            "Substrate-membership-backfill gap routed to v1.11 Substrate Repair."
        ))
        return findings

    subsystems_touched = fm.get("subsystems_touched") or []
    if isinstance(subsystems_touched, str):
        subsystems_touched = [subsystems_touched]
    declared_subs = {str(s) for s in subsystems_touched if s}

    # Rule 11: subsystem-registry consistency
    # Vela V61 finding: YAML parses unquoted decimal UIDs as integers; normalize to str
    # so registry.get(int) doesn't miss a string-keyed entry (str key is the canonical form).
    registry_subs = registry.get(str(uid), set())
    if not registry_subs:
        findings.append(Finding(
            severity, "R11-missing-registry-rows", uid,
            f"release status:done has no rows in subsystem-registry.jsonl for release_uid={uid} "
            "(Rule 11 violation — every shipped release must have matching registry rows)"
        ))
    else:
        # Cross-check declared vs registry
        only_declared = declared_subs - registry_subs
        only_registry = registry_subs - declared_subs
        if only_declared or only_registry:
            findings.append(Finding(
                severity, "R11-registry-mismatch", uid,
                f"release subsystems_touched != registry rows. "
                f"In subsystems_touched only: {sorted(only_declared)}. "
                f"In registry only: {sorted(only_registry)}. "
                "(Rule 11 hard-gate at B6)"
            ))

    # Rule 12 + structural-consistency: derive from release-plan.capabilities_touched
    shipped_release_plan_uid = fm.get("shipped_release_plan")
    if not shipped_release_plan_uid:
        # Try to find by reverse pointer
        for f in (VAULT_ROOT / "vault/files").glob("*.md"):
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rp_fm = parse_frontmatter(text)
            if rp_fm and rp_fm.get("type") == "release-plan" and rp_fm.get("shipped_release") == uid:
                shipped_release_plan_uid = rp_fm.get("uid")
                break

    if not shipped_release_plan_uid:
        # v1.27.0 Stream A amendment: brief-based releases (input_brief_uid: without release-plan) carry
        # capabilities_touched + hub_summaries on the release entry itself. Derive structural-consistency
        # from the release entry's own fields when no plan exists.
        release_caps = fm.get("capabilities_touched") or []
        release_hub_summaries = fm.get("hub_summaries") or {}

        # v1.27.0 Stream E grace period: releases backfilled by historical sweep carry sweep_history_*
        # frontmatter; downgrade severity to INFO so the cycle ships without surfacing 7+ historical errors.
        # ERROR ratchet planned for v1.28.0+ once substrate has settled + new releases author cleanly.
        is_sweep_backfilled = bool(fm.get("sweep_history_backfilled_at"))
        brief_severity = "INFO" if is_sweep_backfilled else severity

        if not release_caps and not release_hub_summaries:
            findings.append(Finding(
                brief_severity, "R12-brief-based-release-missing-fields", uid,
                "release entry is brief-based (input_brief_uid: pattern; no shipped_release_plan) but has no "
                "capabilities_touched + no hub_summaries on the release entry itself. Either declare both fields "
                "on the release entry (v1.27.0+ brief-based pattern) or author a release-plan and link via "
                "shipped_release_plan: (legacy pattern). (Rule 12 hard-gate at B6; INFO if Stream-E-backfilled)"
            ))
            return findings
        # Derive subsystems from release entry's own capabilities_touched
        if isinstance(release_caps, list) and release_caps:
            # capabilities_touched on brief-based releases may be UID strings OR descriptive strings;
            # filter to UID-shaped entries for derivation
            uid_caps = [c for c in release_caps if isinstance(c, str) and len(c) == 8 and all(ch in "0123456789abcdef" for ch in c)]
            # v1.27.0.1 Stream F remediation per sa.skeptic-005 P0-2: surface when capabilities_touched
            # is non-empty but no entries are UID-shaped (prose-only declarations bypass structural
            # consistency derive silently). Closes the same honor-system surface v1.27.0 exists to fix.
            if not uid_caps:
                findings.append(Finding(
                    brief_severity, "R12-brief-capabilities-no-uid-shape", uid,
                    f"release.capabilities_touched is non-empty ({len(release_caps)} entries) but none are UID-shaped "
                    "(8 lowercase hex chars). Cannot derive structural-consistency from prose-only capabilities. "
                    "Author capabilities as UIDs of touched primitives (per v1.27.0+ brief-based pattern), not "
                    "as descriptive strings. (Rule 12 brief-based — v1.27.0.1 enforcement; INFO if Stream-E-backfilled)"
                ))
            if uid_caps:
                derived, _ = derive_subsystems(uid_caps, mo_map)
                if derived != declared_subs:
                    only_derived = derived - declared_subs
                    only_declared_post = declared_subs - derived
                    findings.append(Finding(
                        brief_severity, "R12-brief-structural-consistency", uid,
                        f"release.subsystems_touched != derived(release.capabilities_touched). "
                        f"Only in derived: {sorted(only_derived)}. "
                        f"Only in declared: {sorted(only_declared_post)}. "
                        f"(Rule 12 brief-based hard-gate at B6 — v1.27.0 enforcement; INFO if Stream-E-backfilled)"
                    ))
        # Check 21 brief-based: hub_summaries should cover declared subsystems
        if isinstance(release_hub_summaries, dict):
            missing_summaries = [h for h in declared_subs if h not in release_hub_summaries]
            if missing_summaries and strict:
                findings.append(Finding(
                    "INFO", "C21-brief-hub-summaries-missing", uid,
                    f"release entry declares subsystems_touched but hub_summaries missing entries for: "
                    f"{sorted(missing_summaries)} (Check 21 honor-system at v1.27.0; ERROR ratchet planned)"
                ))
        return findings

    # Load release plan
    rp_path = VAULT_ROOT / "vault/files" / f"{shipped_release_plan_uid}.md"
    if not rp_path.exists():
        findings.append(Finding(
            severity, "R12-release-plan-not-found", uid,
            f"shipped_release_plan {shipped_release_plan_uid} file not found at {rp_path}. "
            "(Rule 12 hard-gate at B6)"
        ))
        return findings
    try:
        rp_text = rp_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        findings.append(Finding(
            severity, "R12-release-plan-unreadable", uid,
            f"shipped_release_plan {shipped_release_plan_uid} unreadable: {e}"
        ))
        return findings
    rp_fm = parse_frontmatter(rp_text)
    if not rp_fm:
        findings.append(Finding(
            severity, "R12-release-plan-no-frontmatter", uid,
            f"shipped_release_plan {shipped_release_plan_uid} has no frontmatter"
        ))
        return findings

    capabilities_touched = rp_fm.get("capabilities_touched") or []
    if isinstance(capabilities_touched, str):
        capabilities_touched = [capabilities_touched]

    # v1.56 Lane X.2: release.capsule v3.8 retires Rule 14 path-pattern table.
    # Grandfathering: releases < v1.56.0 keep Rule 14 extended derivation (v3.7 contract);
    # releases >= v1.56.0 use Rule 12 1-hop traversal only (v3.8 contract).
    # Tools now carry member_of: graph citizenship; path-pattern table is redundant.
    release_version_parsed = _parse_semver(fm.get("release_version"))
    use_rule14 = release_version_parsed is not None and release_version_parsed < (1, 56, 0) \
        and release_version_parsed >= (1, 54, 0)
    if use_rule14:
        kernel_paths = fm.get("kernel_substrate_touched") or []
        if isinstance(kernel_paths, str):
            kernel_paths = [kernel_paths]
        derived, _ = derive_subsystems_extended(capabilities_touched, kernel_paths, mo_map)
    else:
        derived, _ = derive_subsystems(capabilities_touched, mo_map)
    if derived != declared_subs:
        only_derived = derived - declared_subs
        only_declared_post = declared_subs - derived
        # v1.27.0 Stream A grace period: same backfill grace as brief-based above.
        is_sweep_backfilled = bool(fm.get("sweep_history_backfilled_at"))
        sc_severity = "INFO" if is_sweep_backfilled else severity
        findings.append(Finding(
            sc_severity, "R12-structural-consistency", uid,
            f"release.subsystems_touched != derived(release-plan.capabilities_touched). "
            f"Only in derived: {sorted(only_derived)}. "
            f"Only in declared: {sorted(only_declared_post)}. "
            f"(Rule 12 + structural-consistency hard-gate at B6 — v1.10 enforcement; INFO if Stream-E-backfilled)"
        ))

    return findings


def validate_l1_canonical_entry_hub_coverage(strict: bool) -> list[Finding]:
    """Check 24 (v1.11): L1 canonical entry must reference all active subsystem hubs.

    Drift prevention through UID-referenced one-way flow (L1 → L2 → L3):
    if L1 stops mentioning a hub UID, the hierarchy breaks for that subsystem.
    Mike-A50 L1/L2/L3 documentation hierarchy 2026-05-08.

    Returns INFO if L1 entry doesn't exist (e.g., pre-v1.11 vaults — grandfather);
    returns ERROR (STRICT) or WARNING (SOFT) for any missing hub UID reference.
    """
    findings: list[Finding] = []
    l1_path = VAULT_ROOT / "vault" / "files" / f"{L1_CANONICAL_ENTRY_UID}.md"
    if not l1_path.exists():
        findings.append(Finding(
            "INFO", "C24-L1-not-yet-shipped", L1_CANONICAL_ENTRY_UID,
            f"L1 canonical entry {L1_CANONICAL_ENTRY_UID} not present at {l1_path.relative_to(VAULT_ROOT) if l1_path.is_relative_to(VAULT_ROOT) else l1_path} — "
            "pre-v1.11 vault or v1.11 not yet applied. Hub-coverage check skipped."
        ))
        return findings
    try:
        text = l1_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        findings.append(Finding(
            "ERROR" if strict else "WARNING", "C24-L1-unreadable", L1_CANONICAL_ENTRY_UID,
            f"L1 canonical entry unreadable: {e}"
        ))
        return findings

    # Strip frontmatter; check body for hub UID references
    body_start = text.find("\n---\n", 4)
    body = text[body_start + 5:] if body_start != -1 else text

    # C24 iterates CANONICAL hubs only — peer-level subsystems, not capability-overview
    # hubs nested under another subsystem (e.g. import-primitive is under tropo-governance).
    # Criterion: exclude any hub whose member_of contains another hub UID.
    hub_set = set(SUBSYSTEM_HUBS)
    canonical_hubs: dict[str, str] = {}
    files_dir = VAULT_ROOT / "vault" / "files"
    for hub_uid, hub_name in SUBSYSTEM_HUBS.items():
        hub_file = files_dir / f"{hub_uid}.md"
        try:
            hub_text = hub_file.read_text(errors="replace")
        except OSError:
            canonical_hubs[hub_uid] = hub_name
            continue
        hub_fm = parse_frontmatter(hub_text) or {}
        mo = hub_fm.get("member_of") or []
        if not isinstance(mo, list):
            mo = [mo] if mo else []
        nested = any(m in hub_set and m != hub_uid for m in mo if isinstance(m, str))
        if not nested:
            canonical_hubs[hub_uid] = hub_name

    severity = "ERROR" if strict else "WARNING"
    for hub_uid, hub_name in canonical_hubs.items():
        if hub_uid not in body:
            findings.append(Finding(
                severity, "C24-L1-missing-hub", L1_CANONICAL_ENTRY_UID,
                f"L1 canonical entry body does not reference hub {hub_uid} ({hub_name}). "
                "Mike-A50 L1/L2/L3 hierarchy requires L1 to reference all active subsystem hubs by UID; "
                "drift prevention through one-way reference flow."
            ))
    return findings


def main(strict: bool = True, json_output: bool = False) -> int:
    all_findings: list[Finding] = []

    # Build member_of map for derivation (v1.9.2 cross-folder resolver pattern)
    mo_map = load_member_of_map()
    # Load subsystem-registry for Rule 11 cross-check
    registry = load_subsystem_registry()

    # v1.11 Check 24: L1 canonical entry hub coverage
    all_findings.extend(validate_l1_canonical_entry_hub_coverage(strict))

    # Validate every governed primitive (Checks 1-4: hub membership)
    for path in collect_governed_primitives():
        all_findings.extend(validate_capability(path))

    # Validate every release-plan instance (Checks 19-23) +
    # every release entry (Rule 11 + Rule 12 + structural-consistency)
    ledger_dir = VAULT_ROOT / "vault/files"
    if ledger_dir.exists():
        for path in ledger_dir.glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            fm = parse_frontmatter(text)
            if not fm:
                continue
            ftype = fm.get("type")
            if ftype == "release-plan":
                all_findings.extend(validate_release_plan(
                    fm.get("uid", path.stem), fm, mo_map, strict
                ))
            elif ftype == "release":
                all_findings.extend(validate_release_entry(
                    fm.get("uid", path.stem), fm, mo_map, registry, strict
                ))

    # Tally
    errors = [f for f in all_findings if f.severity == "ERROR"]
    warnings = [f for f in all_findings if f.severity == "WARNING"]
    infos = [f for f in all_findings if f.severity == "INFO"]

    if json_output:
        print(json.dumps({
            "errors": len(errors),
            "warnings": len(warnings),
            "infos": len(infos),
            "mode": "STRICT" if strict else "SOFT",
            "findings": [
                {"severity": f.severity, "check": f.check, "target": f.target, "message": f.message}
                for f in all_findings
            ]
        }, indent=2))
    else:
        for f in all_findings:
            print(f"{f.severity:7} [{f.check}] {f.target}: {f.message}")
        print(f"\n{'='*60}")
        print(f"validate-capability-membership.py — v1.10 Pure Enforcement")
        print(f"{len(errors)} ERRORs, {len(warnings)} WARNINGs, {len(infos)} INFOs")
        print(f"Mode: {'STRICT (v1.10+ — Checks 19-23 + Rule 11 + Rule 12 + structural-consistency at ERROR)' if strict else 'SOFT (v1.8-v1.9 — WARNING-level)'}")
        if any(f.check == "GRANDFATHERED-pre-v1.9.2" for f in all_findings):
            grandfathered = [f.target for f in all_findings if f.check == "GRANDFATHERED-pre-v1.9.2"]
            print(f"Grandfathered (structural-consistency skipped): {grandfathered}")

    if strict and errors:
        return 1
    return 0


if __name__ == "__main__":
    # v1.10 default: STRICT. --soft opts into v1.8-v1.9 semantics for scoped checks.
    soft_mode = "--soft" in sys.argv
    # Backward-compat: --strict was the v1.8-v1.9 way to opt INTO strict; now no-op (default).
    json_mode = "--json" in sys.argv
    sys.exit(main(strict=not soft_mode, json_output=json_mode))
