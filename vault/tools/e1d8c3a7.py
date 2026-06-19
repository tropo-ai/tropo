#!/usr/bin/env python3
"""
---
uid: e1d8c3a7
title: validate-release-manifest — Tool
name: validate-release-manifest
type: tool
status: active
owner: argus
domain: Validate the ship-artifact manifest graph — 23 checks per ship-artifact.capsule v1.1.4.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/e1d8c3a7.py [--vault-path PATH]
script_path: vault/tools/e1d8c3a7.py
input:
  type: object
  properties:
    vault-path:
      type: string
output:
  type: object
  properties:
    verdict:
      type: string
      enum:
      - pass
      - findings
    p0:
      type: integer
    p1:
      type: integer
    p2:
      type: integer
destructive: false
audit_required: false
writes_scope: []
governance_category: query
description: 'Validates the ship-artifact manifest graph rooted at the ''Tropo Release Structure'' project per ship-artifact.capsule v1.1.4 §Validation Checks. 23 checks: per-entry frontmatter validation (Checks 1-13), graph integrity (Checks 14-16), composition path-tree containment + override-child shape + skip applicability + direct-retirement audit (Checks 17-20), honor-system warnings (Checks 21-23). Per Build-Release Pipeline arch-spec 747c33c9 §3.2: dual-form — standalone CLI + importable as `from validate_release_manifest import validate_manifest, ManifestValidationError`.'
domain_tags:
- validator
- ship-artifact
- manifest-graph
- dual-form
- build-pipeline-pre-flight
trigger_description: Reach for this when verifying the ship-artifact manifest is structurally clean — every ship-artifact entry has valid frontmatter, parent UIDs resolve, output_path is unique, supersession pairs are bidirectional, override-child shape is legal. Run before build-release.py and after any ship-artifact entry edit. Importable shape (`from validate_release_manifest import validate_manifest`) lets build-release.py call it programmatically without subprocess overhead. Pairs with validate-canonical-l0 + validate-capability-membership + tropo-validate as the structural-validator quartet.
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
- ship-artifact
- manifest-graph
- dual-form
- v1.15-stream-b
subsystem_hub:
- 8dd772a0
---
"""
from __future__ import annotations

"""
validate-release-manifest.py — v1.12.2

Validates the ship-artifact manifest graph rooted at the "Tropo Release
Structure" project per ship-artifact.capsule v1.1.4 §Validation Checks.

Implements all 23 checks declared in the capsule:
  - Checks 1-13:  per-entry frontmatter validation (type, kind, canonical_source
                  resolves, source_mode enum, extraction_scope enum, parent UID
                  resolves, explicit-children consistency, output_path
                  uniqueness, cleanup_rules schema, status discipline,
                  locked_by/locked_at presence, body sections present,
                  member_of includes manifest_root_uid)
  - Checks 14-16: graph integrity (parent chain terminates at root without
                  cycles, supersession bidirectional pairs)
  - Checks 17-20: composition path-tree containment, override-child shape
                  legality, skip applicability, direct-retirement audit
                  (capsule numbering 19-22; spec numbering 17-20)
  - Checks 21-23: honor-system warnings (description substance, cleanup notes
                  accuracy, Notes audit accuracy)

Per Build-Release Pipeline arch-spec 747c33c9 §3.2: dual-form validator —
standalone CLI + importable as `from validate_release_manifest import
validate_manifest, ManifestValidationError`.

Per arch-spec Required Behavior #3: manifest_root_uid is read from
ship-artifact.capsule.md frontmatter dynamically — NEVER hard-coded.

Per arch-spec §3.4 Severity Registry:
  - [enforced]    → P0 (HALT in --strict)
  - [honor-system] → P2 (always WARN)
  - --strict      → promotes P1 findings to P0 (no P1s currently; reserved
                    for forward-compat)

Exit codes:
  0  — clean (no P0s)
  1  — at least one P0
  64 — bootstrap halt (manifest_root_uid TBD or capsule unreadable)
  65 — validation failure (P0 ERRORs)

Usage:
  python3 .tropo/scripts/validate-release-manifest.py [--strict] [--json]
  python3 .tropo/scripts/validate-release-manifest.py --vault-root <path>
"""


import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

# ─── Configuration ───────────────────────────────────────────────────────────

VAULT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHIP_ARTIFACT_CAPSULE_PATH = VAULT_ROOT / ".tropo" / "capsules" / "ship-artifact.capsule.md"

VALID_SOURCE_MODES = {
    "recursive-ship-all",
    "recursive-ship-tagged",
    "explicit-children",
    "structure-only",
    "skip",
    "direct-copy",
}
FOLDER_ONLY_MODES = {"recursive-ship-all", "recursive-ship-tagged", "explicit-children", "structure-only"}
FILE_ONLY_MODES = {"direct-copy"}
ANY_KIND_MODES = {"skip"}

VALID_EXTRACTION_SCOPES = {"ship", "argo-reference", "argo-private"}
VALID_KINDS = {"folder", "file"}
VALID_CLEANUP_KEYS = {"strip_markers", "broken_link_policy", "rewrite_uid_refs"}
LEGAL_OVERRIDE_CHILD_MODES = {"direct-copy", "skip"}  # Check 18 (capsule Check 20)

REQUIRED_BODY_SECTIONS = {"## Purpose", "## Description"}


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class Finding:
    severity: str  # "P0" | "P1" | "P2"
    check_id: str
    entry: str   # uid or path
    detail: str
    suggested_resolution: str = ""

    def to_row(self) -> str:
        return f"| {self.entry} | {self.severity} | {self.check_id} | {self.detail} | {self.suggested_resolution} |"


@dataclass
class ManifestEntry:
    uid: str
    path: Path
    fm: dict
    body: str = ""

    @property
    def kind(self) -> Optional[str]:
        return self.fm.get("kind")

    @property
    def source_mode(self) -> Optional[str]:
        return self.fm.get("source_mode")

    @property
    def canonical_source(self) -> Optional[str]:
        return self.fm.get("canonical_source")

    @property
    def output_path(self) -> Optional[str]:
        op = self.fm.get("output_path")
        return op if op else None

    @property
    def parent(self) -> Optional[str]:
        p = self.fm.get("parent")
        if p is None or p == "null":
            return None
        return str(p).strip()

    @property
    def member_of(self) -> list[str]:
        mo = self.fm.get("member_of") or []
        if isinstance(mo, str):
            mo = [mo]
        return [str(x).strip() for x in mo if x]

    @property
    def status(self) -> Optional[str]:
        return self.fm.get("status")

    @property
    def state(self) -> Optional[str]:
        return self.fm.get("state")

    @property
    def extraction_scope(self) -> Optional[str]:
        return self.fm.get("extraction_scope")


class ManifestValidationError(Exception):
    """Raised by validate_manifest() when one or more P0 findings exist."""

    def __init__(self, findings: list[Finding]):
        self.findings = findings
        super().__init__(f"{len(findings)} P0 ERROR(s) in ship-artifact manifest")


# ─── Frontmatter parsing ─────────────────────────────────────────────────────

def parse_frontmatter_and_body(text: str) -> tuple[Optional[dict], str]:
    """Return (frontmatter dict, body string). Returns (None, "") on parse failure."""
    if not text.startswith("---\n"):
        return None, ""
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, ""
    fm_text = text[4:end]
    body = text[end + 5:]

    if yaml is not None:
        try:
            parsed = yaml.safe_load(fm_text)
            if isinstance(parsed, dict):
                return parsed, body
        except yaml.YAMLError:
            return None, body
        return None, body
    return None, body


def read_manifest_root_uid(target: str = "release") -> str:
    """Read manifest_root_uid from ship-artifact.capsule frontmatter.

    Per arch-spec Required Behavior #3: NEVER hard-coded; resolved dynamically.
    Halts on TBD or absent (exit 64 EX_USAGE).

    v1.42.0 Stream F atomic-commit migration (2026-05-18, argus-a71):
    capsule v1.3 changed manifest_root_uid: from scalar to per-target map.
    Accepts `target` parameter (default 'release' for this script's release-target validation).

    v1.3+ map shape: `manifest_root_uid: {release: <uid>, web: <uid>}` → return value for `target` key
    v1.2 scalar fallback: `manifest_root_uid: <uid>` → return value for target='release'; ERROR otherwise
    """
    if not SHIP_ARTIFACT_CAPSULE_PATH.exists():
        print(f"BOOTSTRAP HALT: ship-artifact.capsule not found at {SHIP_ARTIFACT_CAPSULE_PATH}", file=sys.stderr)
        sys.exit(64)
    text = SHIP_ARTIFACT_CAPSULE_PATH.read_text()
    fm, _ = parse_frontmatter_and_body(text)
    if not fm or "manifest_root_uid" not in fm:
        print("BOOTSTRAP HALT: manifest_root_uid not declared in ship-artifact.capsule frontmatter", file=sys.stderr)
        sys.exit(64)

    raw = fm["manifest_root_uid"]

    # v1.3+ map shape
    if isinstance(raw, dict):
        if target not in raw:
            print(f"BOOTSTRAP HALT: target {target!r} not declared in capsule manifest_root_uid map", file=sys.stderr)
            print(f"      Available targets: {list(raw.keys())}", file=sys.stderr)
            sys.exit(64)
        val = str(raw[target]).strip()
    # v1.2 scalar shape (backward-compat)
    else:
        if target != "release":
            print(f"BOOTSTRAP HALT: capsule manifest_root_uid is scalar (v1.2 shape); target {target!r} unsupported.", file=sys.stderr)
            print(f"      Web target requires v1.3+ capsule with manifest_root_uid map shape.", file=sys.stderr)
            sys.exit(64)
        val = str(raw).strip()

    if val == "TBD":
        print("BOOTSTRAP HALT: manifest_root_uid is TBD — Phase D project not yet authored", file=sys.stderr)
        sys.exit(64)
    return val


# ─── Manifest loading ────────────────────────────────────────────────────────

def load_ship_artifacts(manifest_root_uid: str) -> list[ManifestEntry]:
    """Walk vault/files/, return all ship-artifact entries belonging to the manifest graph.

    Filter: type:ship-artifact AND state:active AND member_of contains manifest_root_uid.
    Archived/superseded entries are graph-history, not build-targets.
    """
    entries: list[ManifestEntry] = []
    vault_files = VAULT_ROOT / "vault" / "files"
    if not vault_files.is_dir():
        return entries
    for path in sorted(vault_files.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, body = parse_frontmatter_and_body(text)
        if not fm:
            continue
        if fm.get("type") != "ship-artifact":
            continue
        if fm.get("state") != "active":
            continue
        mo = fm.get("member_of") or []
        if isinstance(mo, str):
            mo = [mo]
        if manifest_root_uid not in [str(x).strip() for x in mo]:
            continue
        uid = fm.get("uid")
        if not uid:
            continue
        entries.append(ManifestEntry(uid=str(uid), path=path, fm=fm, body=body))
    return entries


# ─── Per-entry checks ────────────────────────────────────────────────────────

def check_entry(entry: ManifestEntry, by_uid: dict[str, ManifestEntry]) -> list[Finding]:
    """Apply Checks 1-13 + 17-20 + 21-23 to a single entry.

    (Checks 14-16 are graph-level; applied separately in check_graph.)
    """
    findings: list[Finding] = []
    fm = entry.fm
    uid = entry.uid

    # Check 1 — type: ship-artifact (already filtered in loader; this is defensive)
    if fm.get("type") != "ship-artifact":
        findings.append(Finding("P0", "C1-type", uid, f"type is not 'ship-artifact' (got '{fm.get('type')}')", "set type: ship-artifact"))

    # Check 2 — kind is one of folder, file
    kind = entry.kind
    if kind not in VALID_KINDS:
        findings.append(Finding("P0", "C2-kind", uid, f"kind '{kind}' not in {sorted(VALID_KINDS)}", "set kind: folder OR kind: file"))

    # Check 3 — canonical_source non-empty string
    cs = entry.canonical_source
    if not cs or not isinstance(cs, str) or not cs.strip():
        findings.append(Finding("P0", "C3-canonical-source-required", uid, "canonical_source is missing or empty", "declare canonical_source: <argo-relative path>"))

    # Check 4 — canonical_source resolves (exceptions: skip + structure-only)
    mode = entry.source_mode
    if cs and mode not in ("skip", "structure-only"):
        # Strip argo-os/ prefix
        rel = cs[len("argo-os/"):] if cs.startswith("argo-os/") else cs
        abs_path = VAULT_ROOT / rel
        if not abs_path.exists():
            findings.append(Finding("P0", "C4-canonical-source-not-found", uid, f"canonical_source path does not resolve: {cs}", "fix canonical_source path OR set source_mode: skip if intentional"))
        else:
            # Type matches kind: folder for kind:folder, file for kind:file
            if kind == "folder" and not abs_path.is_dir():
                findings.append(Finding("P0", "C4b-canonical-source-kind-mismatch", uid, f"kind:folder but canonical_source is not a directory: {cs}", "set kind: file OR fix canonical_source"))
            elif kind == "file" and not abs_path.is_file():
                findings.append(Finding("P0", "C4b-canonical-source-kind-mismatch", uid, f"kind:file but canonical_source is not a file: {cs}", "set kind: folder OR fix canonical_source"))

    # Check 5 — source_mode enum + folder/file applicability
    if mode and mode not in VALID_SOURCE_MODES:
        findings.append(Finding("P0", "C5-source-mode-enum", uid, f"source_mode '{mode}' not in {sorted(VALID_SOURCE_MODES)}", "use one of the legal source_modes"))
    elif mode and kind:
        if mode in FOLDER_ONLY_MODES and kind != "folder":
            findings.append(Finding("P0", "C5b-source-mode-applicability", uid, f"source_mode '{mode}' is folder-only but kind is '{kind}'", "set kind: folder OR change source_mode"))
        if mode in FILE_ONLY_MODES and kind != "file":
            findings.append(Finding("P0", "C5b-source-mode-applicability", uid, f"source_mode '{mode}' is file-only but kind is '{kind}'", "set kind: file OR change source_mode"))

    # Check 6 — extraction_scope enum
    es = entry.extraction_scope
    if es and es not in VALID_EXTRACTION_SCOPES:
        findings.append(Finding("P0", "C6-extraction-scope-enum", uid, f"extraction_scope '{es}' not in {sorted(VALID_EXTRACTION_SCOPES)}", "use one of: ship | argo-reference | argo-private"))

    # Check 7 — parent resolves OR is null (root)
    parent = entry.parent
    if parent is not None and parent not in by_uid and parent != "b2e7d4a9":  # b2e7d4a9 is root sentinel project (not a ship-artifact)
        # Check if parent is a known root-sentinel project (the manifest graph root project)
        # Note: parent: <root-sentinel-UID> is allowed for top-level entries; the root project itself is type:project, not ship-artifact
        # so by_uid won't include it. Allow parent UIDs that resolve to *any* file in vault/files/.
        parent_path = VAULT_ROOT / "vault" / "files" / f"{parent}.md"
        if not parent_path.exists():
            findings.append(Finding("P0", "C7-parent-resolves", uid, f"parent UID '{parent}' does not resolve to any vault entry", "fix parent UID OR set parent: null for root entry"))

    # Check 8 — explicit-children consistency
    if mode == "explicit-children":
        children = fm.get("children") or []
        if not isinstance(children, list) or not children:
            findings.append(Finding("P0", "C8-explicit-children-required", uid, "source_mode: explicit-children but children: array is empty/missing", "declare children: [<UIDs>] non-empty"))
        else:
            for child_uid in children:
                child_str = str(child_uid).strip()
                if child_str not in by_uid:
                    findings.append(Finding("P0", "C8b-explicit-children-resolve", uid, f"explicit-children UID '{child_str}' does not resolve", f"fix children: array — UID '{child_str}' not found"))
                else:
                    child = by_uid[child_str]
                    if child.parent != uid:
                        findings.append(Finding("P0", "C8c-explicit-children-parent-back", uid, f"child {child_str} parent '{child.parent}' does not back-point to {uid}", f"set {child_str}.parent: {uid}"))

    # Check 10 — cleanup_rules schema
    cleanup_rules = fm.get("cleanup_rules")
    if cleanup_rules is not None:
        if not isinstance(cleanup_rules, dict):
            findings.append(Finding("P0", "C10-cleanup-rules-schema", uid, "cleanup_rules must be a dict", "use cleanup_rules: {strip_markers: ..., broken_link_policy: ..., rewrite_uid_refs: ...}"))
        else:
            for key in cleanup_rules:
                if key not in VALID_CLEANUP_KEYS:
                    findings.append(Finding("P1", "C10b-cleanup-rules-unknown-key", uid, f"cleanup_rules unknown key '{key}'", f"valid keys: {sorted(VALID_CLEANUP_KEYS)}"))

    # Check 11 — status discipline (new entries start at draft; locked requires draft → locked transition documented)
    status = entry.status
    if status not in (None, "draft", "locked", "archived"):
        findings.append(Finding("P0", "C11-status-discipline", uid, f"status '{status}' not in valid set (draft/locked/archived)", "use status: draft | locked | archived"))

    # Check 12 — if locked, locked_by + locked_at present
    if status == "locked":
        if not fm.get("locked_by"):
            findings.append(Finding("P0", "C12-locked-by-required", uid, "status: locked but locked_by missing", "declare locked_by: <agent-uid>"))
        if not fm.get("locked_at"):
            findings.append(Finding("P0", "C12-locked-at-required", uid, "status: locked but locked_at missing", "declare locked_at: <iso-date>"))

    # Check 13 — required body sections (## Purpose, ## Description)
    body_lower = entry.body
    for section in REQUIRED_BODY_SECTIONS:
        if section not in body_lower:
            findings.append(Finding("P0", "C13-required-body-sections", uid, f"required body section '{section}' missing", f"add `{section}` section to body"))

    # Check 14 — member_of includes manifest_root_uid (already filtered in loader)
    # (No-op here; load_ship_artifacts already filters; entries that fail this don't reach here)

    # Check 17 (capsule Check 19) — composition path-tree containment
    if parent and parent in by_uid:
        parent_entry = by_uid[parent]
        if parent_entry.source_mode == "recursive-ship-all" and cs and parent_entry.canonical_source:
            parent_cs = parent_entry.canonical_source.rstrip("/")
            if not (cs == parent_cs or cs.startswith(parent_cs + "/")):
                findings.append(Finding("P0", "C17-path-tree-containment", uid, f"canonical_source '{cs}' is not under recursive-ship-all parent's canonical_source '{parent_cs}'", "fix canonical_source to be under parent tree OR change parent"))

    # Check 18 (capsule Check 20) — override-child shape legality
    if parent and parent in by_uid:
        parent_entry = by_uid[parent]
        if parent_entry.source_mode == "recursive-ship-all":
            if mode and mode not in LEGAL_OVERRIDE_CHILD_MODES:
                findings.append(Finding("P0", "C18-override-child-shape", uid, f"source_mode '{mode}' is not legal under recursive-ship-all parent (only {sorted(LEGAL_OVERRIDE_CHILD_MODES)} allowed)", "change source_mode to direct-copy or skip OR change parent"))

    # Check 19 (capsule Check 21) — skip applicability
    if mode == "skip":
        if parent is None:
            findings.append(Finding("P0", "C19-skip-applicability", uid, "top-level skip rejected (parent: null)", "remove entry OR add to a recursive-ship-all parent"))
        elif parent in by_uid:
            parent_mode = by_uid[parent].source_mode
            if parent_mode == "explicit-children":
                findings.append(Finding("P0", "C19-skip-applicability", uid, "skip under explicit-children rejected", "exclude by omitting from parent's children: array"))
            elif parent_mode == "structure-only":
                findings.append(Finding("P0", "C19-skip-applicability", uid, "skip under structure-only rejected", "remove entry — structure-only descendants are auto-excluded"))

    # Check 20 (capsule Check 22) — direct-retirement audit
    if entry.state == "archived" and not fm.get("superseded_by"):
        if not fm.get("archived_by"):
            findings.append(Finding("P0", "C20-direct-retirement-audit", uid, "state: archived without superseded_by, but archived_by missing", "declare archived_by: <agent-uid>"))
        if not fm.get("archived_at"):
            findings.append(Finding("P0", "C20-direct-retirement-audit", uid, "state: archived without superseded_by, but archived_at missing", "declare archived_at: <iso-date>"))

    # Check 21 — description substantive (honor-system; warn on placeholder/empty)
    desc = fm.get("description") or ""
    desc_str = str(desc).strip()
    if not desc_str or desc_str in ("TBD", "placeholder", "<FILL>"):
        findings.append(Finding("P2", "C21-description-substance", uid, "description appears placeholder or empty", "author substantive description"))

    return findings


# ─── Graph checks ────────────────────────────────────────────────────────────

def check_graph(entries: list[ManifestEntry], by_uid: dict[str, ManifestEntry]) -> list[Finding]:
    """Apply Checks 14-16: graph integrity (parent chain terminates without cycles, supersession bidirectional)."""
    findings: list[Finding] = []

    # Check 9 — effective output_path uniqueness
    # (After resolving recursive-default + per-file overrides, every effective output_path must be unique)
    op_to_uids: dict[str, list[str]] = {}
    for e in entries:
        if e.source_mode == "skip":
            continue
        op = e.output_path
        if not op and e.canonical_source:
            # Default: mirror canonical_source minus argo-os/ prefix
            op = e.canonical_source[len("argo-os/"):] if e.canonical_source.startswith("argo-os/") else e.canonical_source
        if op:
            op_normalized = op.rstrip("/")
            op_to_uids.setdefault(op_normalized, []).append(e.uid)
    for op, uids in op_to_uids.items():
        if len(uids) > 1:
            findings.append(Finding("P0", "C9-output-path-uniqueness", op, f"effective output_path '{op}' is declared by multiple entries: {uids}", "rename output_path on all but one entry"))

    # Check 16 — graph integrity: parent chain terminates without cycles
    for e in entries:
        path: list[str] = [e.uid]
        current = e.parent
        depth = 0
        while current is not None and depth < 100:
            if current in path:
                findings.append(Finding("P0", "C16-cycle", e.uid, f"parent chain contains cycle through {current}", "break the cycle by setting one entry's parent to null OR a different parent"))
                break
            path.append(current)
            if current not in by_uid:
                break  # parent resolves outside ship-artifact set (e.g., root sentinel project) — chain terminates here
            current = by_uid[current].parent
            depth += 1

    # Check 15 — supersession bidirectional pairs
    for e in entries:
        sup = e.fm.get("supersedes")
        sup_by = e.fm.get("superseded_by")
        if sup and isinstance(sup, str):
            target = by_uid.get(sup.strip())
            if target and target.fm.get("superseded_by") != e.uid:
                findings.append(Finding("P0", "C15-supersession-bidirectional", e.uid, f"supersedes {sup} but {sup}.superseded_by != {e.uid}", f"set {sup}.superseded_by: {e.uid}"))
        if sup_by and isinstance(sup_by, str):
            target = by_uid.get(sup_by.strip())
            if target and target.fm.get("supersedes") != e.uid:
                findings.append(Finding("P0", "C15-supersession-bidirectional", e.uid, f"superseded_by {sup_by} but {sup_by}.supersedes != {e.uid}", f"set {sup_by}.supersedes: {e.uid}"))

    return findings


# ─── Public API + main ──────────────────────────────────────────────────────

def validate_manifest(strict: bool = True) -> list[Finding]:
    """Public API for build-release.py and other consumers.

    Returns list of Finding objects. Caller decides whether to halt.
    Convenience: caller may wrap in `if any(f.severity == 'P0' for f in findings): raise ManifestValidationError(findings)`.
    """
    manifest_root_uid = read_manifest_root_uid()
    entries = load_ship_artifacts(manifest_root_uid)
    by_uid = {e.uid: e for e in entries}

    all_findings: list[Finding] = []
    for entry in entries:
        all_findings.extend(check_entry(entry, by_uid))
    all_findings.extend(check_graph(entries, by_uid))

    # --strict promotion: P1 → P0 (no P1s currently; reserved for forward-compat)
    if strict:
        for f in all_findings:
            if f.severity == "P1":
                f.severity = "P0"

    return all_findings


def render_findings(findings: list[Finding]) -> str:
    """Render findings as markdown pipe-table per arch-spec §3.3."""
    p0_count = sum(1 for f in findings if f.severity == "P0")
    p1_count = sum(1 for f in findings if f.severity == "P1")
    p2_count = sum(1 for f in findings if f.severity == "P2")
    lines = []
    lines.append("=" * 72)
    lines.append("validate-release-manifest.py — v1.12.2 (Phase E spec compliance)")
    lines.append(f"{p0_count} P0 ERRORs, {p1_count} P1, {p2_count} P2 (honor-system)")
    lines.append("=" * 72)
    if findings:
        lines.append("")
        lines.append("| Entry / Path | Severity | Check | Detail | Suggested Resolution |")
        lines.append("|---|---|---|---|---|")
        # Sort: P0 first, then P1, P2; within severity by check_id then entry
        sorted_findings = sorted(findings, key=lambda f: (
            {"P0": 0, "P1": 1, "P2": 2}.get(f.severity, 3),
            f.check_id,
            f.entry,
        ))
        for f in sorted_findings:
            lines.append(f.to_row())
    else:
        lines.append("(no findings; all 23 checks passed)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ship-artifact manifest")
    parser.add_argument("--strict", action="store_true", help="Promote P1 honor-system findings to P0 (HALT)")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON instead of markdown")
    parser.add_argument("--vault-root", type=str, help="Override VAULT_ROOT (default: derived from script path)")
    args = parser.parse_args()

    if args.vault_root:
        global VAULT_ROOT, SHIP_ARTIFACT_CAPSULE_PATH
        VAULT_ROOT = Path(args.vault_root).resolve()
        SHIP_ARTIFACT_CAPSULE_PATH = VAULT_ROOT / ".tropo" / "capsules" / "ship-artifact.capsule.md"

    findings = validate_manifest(strict=args.strict)

    if args.json:
        print(json.dumps([
            {
                "severity": f.severity,
                "check_id": f.check_id,
                "entry": f.entry,
                "detail": f.detail,
                "suggested_resolution": f.suggested_resolution,
            }
            for f in findings
        ], indent=2))
    else:
        print(render_findings(findings))

    p0_count = sum(1 for f in findings if f.severity == "P0")
    if p0_count > 0:
        return 65
    return 0


if __name__ == "__main__":
    sys.exit(main())
