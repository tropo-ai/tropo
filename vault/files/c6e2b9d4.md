#!/usr/bin/env python3
"""
---
uid: c6e2b9d4
title: rebuild-project-index — Tool
name: rebuild-project-index
type: tool
status: active
owner: argus
domain: Rebuild a project's 00-index.md from folder contents — 4-column table from frontmatter.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/c6e2b9d4.py --slug <project-slug> [--dry-run]
script_path: vault/tools/c6e2b9d4.py
input:
  type: object
  required:
  - slug
  properties:
    slug:
      type: string
      description: Project slug under projects/
    dry-run:
      type: boolean
destructive: false
audit_required: false
writes_scope:
- projects/<slug>/00-index.md
governance_category: update
description: 'Rebuilds projects/<slug>/00-index.md from the actual folder contents — 4-column table (Path | Type | Status | Description) derived from each file''s YAML frontmatter or marked ''folder'' for subdirectories. Reader-triggered: when an agent encounters a stale or missing 00-index.md during a session, run this. Idempotent — re-running on unchanged folder produces identical output. Format follows .tropo/schema/index-standard.md.'
domain_tags:
- project-index
- folder-rebuild
- reader-triggered
- idempotent
trigger_description: Reach for this when you encounter a projects/<slug>/00-index.md that is missing, stale, or out of sync with the folder contents — typically while navigating to a project, registering a new file in it, or inspecting its status. Idempotent and safe to re-run; produces identical output on unchanged folders. Future v1.5+ may add watcher-triggered automation; today it is reader-triggered (the agent that notices the drift fixes it).
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
- project-index
- rendering
- v1.15-stream-b
subsystem_hub:
- dbc1cbbf
---
"""
from __future__ import annotations

"""Rebuild `projects/<slug>/00-index.md` from folder contents.

Per [v1.4 Stream 2 §D2.3 (d9f3b8c1)](argo-os/ledger/files/d9f3b8c1.md). Resolves
Mike's Q1 from [post-ship findings (21183d40)](argo-os/ledger/files/21183d40.md)
row 18: a routine for an agent (or scheduled run) to rebuild a project's
00-index.md from the actual folder contents, without re-reading every file
each session.

Format follows [.tropo/schema/index-standard.md](argo-os/.tropo/schema/index-standard.md):
4-column markdown table with Path | Type | Status | Description, derived
from each file's YAML frontmatter (or marked `folder` for subdirectories).

**Reader-triggered invocation (v1.4 minimal viable):** when an agent encounters
a `projects/<slug>/` folder during a session — typically to navigate, register
a new file, or inspect status — and the folder's `00-index.md` is missing or
stale, the agent runs this script with `--slug <slug>` to refresh. Future v1.5+
may add watcher-triggered automation.

**Idempotent.** Re-running on an unchanged folder produces identical output.
The `Last updated:` line includes the running agent's identifier when given.

Usage:
    # Rebuild a single project's index:
    python3 .tropo/scripts/rebuild-project-index.py --slug agentic-builders-launch

    # Rebuild ALL projects' indexes (backfill pass):
    python3 .tropo/scripts/rebuild-project-index.py --all

    # Dry-run (preview without writing):
    python3 .tropo/scripts/rebuild-project-index.py --slug <slug> --dry-run

    # Specify vault root + agent identifier:
    python3 .tropo/scripts/rebuild-project-index.py --all --vault-path /path/to/vault --by vela-v36

Authored: Vela V36, 2026-04-28.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
FIELD_RE = re.compile(r"^([a-zA-Z_][\w-]*):\s*(.*)$", re.MULTILINE)

# Filename-based type inference for files whose frontmatter lacks an explicit `type:`.
# Fall through in order — most-specific suffix first.
FILENAME_TYPE_INFERENCE: list[tuple[str, str]] = [
    (".board.md", "board-snapshot"),
    (".collection.md", "collection-ref"),
    (".skill.md", "skill"),
    (".playbook.md", "playbook"),
    (".capsule.md", "capsule"),
    (".extension.md", "extension"),
    (".directive.md", "directive"),
    ("AGENTS.md", "agents-md"),
    ("CAPSULE.md", "capsule"),
    ("CLAUDE.md", "claude-md"),
    ("README.md", "readme"),
]


def infer_type_from_filename(name: str) -> str:
    for suffix, type_ in FILENAME_TYPE_INFERENCE:
        if name.endswith(suffix):
            return type_
    return "file"


def resolve_vault_root(arg: str | None) -> Path:
    if arg:
        p = Path(arg).resolve()
    else:
        # Script-relative: <vault>/.tropo/scripts/rebuild-project-index.py
        p = Path(__file__).resolve().parent.parent.parent
    if not (p / "projects").is_dir():
        raise SystemExit(f"No projects/ directory found at {p}")
    return p


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Return a flat dict of top-level frontmatter fields. Empty if no frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        fm_match = FIELD_RE.match(line)
        if fm_match:
            key, val = fm_match.group(1), fm_match.group(2).strip()
            # First-occurrence wins; nested values handled raw
            if key not in fm:
                # Strip surrounding quotes for cleaner display
                fm[key] = val.strip("\"'")
    return fm


def describe_entry(name: str, path: Path) -> tuple[str, str, str, str]:
    """Return (path_str, type, status, description) for one entry in a project folder."""
    if path.is_dir():
        # Skip dot-folders + archive (archive content typically isn't surfaced)
        path_str = f"{name}/"
        return (path_str, "folder", "—", _folder_description(path))

    # File
    if path.suffix == ".md" or name in {"AGENTS.md", "CAPSULE.md", "CLAUDE.md", "README.md"}:
        fm = parse_frontmatter(path)
        # Type: explicit frontmatter > filename inference > "file"
        type_ = fm.get("type", "").lower() or infer_type_from_filename(name)
        status = fm.get("status", fm.get("stage", "—"))
        # Description: title > description > body H1 > "—"
        desc = fm.get("title") or fm.get("description") or _extract_first_heading(path)
        if len(desc) > 80:
            desc = desc[:77] + "..."
        return (f"`{name}`", type_, status, desc or "—")

    # Non-markdown file (yaml, json, py, etc.)
    return (f"`{name}`", "file", "—", "")


def _extract_first_heading(path: Path) -> str:
    """Return the body's first H1 (or H2) heading, sans the # prefix.
    Fallback used when frontmatter has no title/description — gives readable
    descriptions for AGENTS.md / CAPSULE.md / README.md / similar files
    that govern navigation but skip the title field."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    # Skip frontmatter if present
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end >= 0:
            text = text[end + 4:]
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line.startswith("## "):
            return line[3:].strip()
    return ""


def _folder_description(path: Path) -> str:
    """Best-effort one-liner for a subfolder. Reads the folder's own 00-index.md
    title line if present, else the AGENTS.md frontmatter title, else returns empty."""
    sub_index = path / "00-index.md"
    if sub_index.is_file():
        for line in sub_index.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("*") and line.endswith("*") and len(line) > 4:
                return line.strip("* ")[:80]
            if line.startswith("# "):
                continue
    sub_agents = path / "AGENTS.md"
    if sub_agents.is_file():
        fm = parse_frontmatter(sub_agents)
        if "title" in fm:
            return fm["title"][:80]
    return ""


def render_index(project_slug: str, project_path: Path, by: str) -> str:
    """Render the 4-column 00-index.md content per the index-standard."""
    today = date.today().isoformat()

    # Sort entries: numerical-prefix order first (00-, 01-, ...), then alphabetical
    entries = sorted(
        [p for p in project_path.iterdir() if p.name not in {"00-index.md", ".DS_Store"}
         and not p.name.startswith(".")],
        key=lambda p: (p.name, p.is_file()),
    )

    rows: list[str] = []
    for p in entries:
        path_str, type_, status, desc = describe_entry(p.name, p)
        rows.append(f"| {path_str} | {type_} | {status} | {desc} |")

    # Find a good folder description from the project's own metadata if available
    project_desc = "Project folder."
    for candidate in [project_path / "AGENTS.md", project_path / "project.board.md"]:
        if candidate.is_file():
            fm = parse_frontmatter(candidate)
            project_desc = fm.get("title", fm.get("description", project_desc))[:120]
            break

    table = "\n".join(rows) if rows else "*(empty)*"

    return f"""# {project_slug} — Index

*{project_desc}*

---

## Files

| Path | Type | Status | Description |
|---|---|---|---|
{table}

---

*Last updated: {today} by {by} via `.tropo/scripts/rebuild-project-index.py`*
"""


SCRIPT_FOOTER_MARKER = "via `.tropo/scripts/rebuild-project-index.py`"


def is_script_generated(content: str) -> bool:
    """Detect whether existing 00-index.md content was generated by THIS script
    (vs. hand-authored by a human). Script-generated files end with a tagline
    that includes SCRIPT_FOOTER_MARKER. Hand-authored files lack it.

    This guard prevents silent overwrites of human-authored content when the
    script regenerates an index. Per [Gate 4 BATCH 023 sa.skeptic P0-5
    finding](agents/sa/sa.skeptic/activation-log/023-vela-v36-record.md),
    silently overwriting hand-authored §Archive sections, ordering rationale,
    or footnotes is a data-loss risk that requires --force to override.

    Added 2026-04-28 by vela-v36 per Gate 4 P0-5 remediation."""
    return SCRIPT_FOOTER_MARKER in content


def write_index(project_path: Path, content: str, dry_run: bool, force: bool = False) -> tuple[str, str]:
    target = project_path / "00-index.md"
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    if existing == content:
        return "noop", "unchanged"

    # Hand-authored content protection (P0-5 remediation):
    # If existing 00-index.md is non-empty AND was NOT generated by this script,
    # treat it as hand-authored content and refuse to overwrite without --force.
    # An empty/missing file is safe to create. A script-generated file (carrying
    # the SCRIPT_FOOTER_MARKER) is safe to regenerate.
    if existing.strip() and not is_script_generated(existing) and not force:
        return "skipped-handauth", (
            "existing 00-index.md is hand-authored (no script footer marker); "
            "would silently overwrite. Pass --force to override."
        )

    if dry_run:
        line_count = len(content.splitlines())
        return "would-write", f"{line_count} lines (dry-run)"
    target.write_text(content, encoding="utf-8")
    line_count = len(content.splitlines())
    return ("created" if not existing else "updated"), f"{line_count} lines"


def find_projects(vault_root: Path) -> list[Path]:
    projects_dir = vault_root / "projects"
    return sorted(
        p for p in projects_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".") and not p.name.startswith("99-")
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Rebuild projects/<slug>/00-index.md")
    p.add_argument("--vault-path", help="Vault root (default: script-relative)")
    p.add_argument("--slug", help="Single project slug to rebuild")
    p.add_argument("--all", action="store_true", help="Rebuild all projects")
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    p.add_argument("--force", action="store_true",
                   help="Overwrite hand-authored 00-index.md (default: skip with warning). "
                        "Use only when you intend to replace human-authored content with "
                        "script output. Files generated by prior runs of this script are "
                        "always safe to regenerate (detected via SCRIPT_FOOTER_MARKER tagline).")
    p.add_argument("--by", default="agent", help="Identifier of who is running (e.g. vela-v36)")
    args = p.parse_args()

    if not args.slug and not args.all:
        raise SystemExit("Specify --slug <name> or --all")

    vault_root = resolve_vault_root(args.vault_path)
    print(f"Vault root: {vault_root}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'APPLY'}")

    if args.slug:
        targets = [vault_root / "projects" / args.slug]
        if not targets[0].is_dir():
            raise SystemExit(f"Project not found: {targets[0]}")
    else:
        targets = find_projects(vault_root)

    print(f"Targets: {len(targets)} project(s)")
    print()

    counts: dict[str, int] = {}
    for project_path in targets:
        slug = project_path.name
        content = render_index(slug, project_path, args.by)
        status, detail = write_index(project_path, content, args.dry_run, force=args.force)
        counts[status] = counts.get(status, 0) + 1
        emoji = {"created": "✓", "updated": "~", "noop": "·",
                 "would-write": "?", "skipped-handauth": "⚠"}.get(status, "?")
        print(f"  {emoji} {slug:50s} {status:16s} {detail}")

    print()
    parts = [f"{k}: {v}" for k, v in sorted(counts.items())]
    print(f"  TOTAL: {len(targets)}    " + " | ".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
