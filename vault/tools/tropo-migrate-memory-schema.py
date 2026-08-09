#!/usr/bin/env python3
"""
---
uid: 2f3a38e3
name: migrate-memory-schema
type: tool
status: active
owner: argus
domain: "Engine Phase-1 governed forward-migration for memory entry scope/context/subtype reconciliation."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-migrate-memory-schema.py [--apply] [--vault-path PATH]"
script_path: vault/tools/tropo-migrate-memory-schema.py
spawnable_by:
  - all-executives
input:
  type: object
  description: "Dry-run by default; --apply performs byte-preserving-body frontmatter migration."
created: 2026-07-15
created_by: argus-a132
governed_by: d5e1b4a3
member_of:
  - f025bcd3
schema_version: 2
trigger_description: "Use only for the Engine Phase-1 memory.capsule v1.5 reconciliation: scope aliases, missing/long context, and legacy subtype mappings. Dry-run first."
extraction_scope: ship
title: "migrate-memory-schema — Engine Phase-1 forward migration"
---
"""

from __future__ import annotations

"""Forward-migrate memory entry frontmatter without rewriting memory bodies.

The append-only episodic logs are explicitly OUT of scope: old dialects remain
historical facts.  This migrates only discrete ``entries/*.md`` files.
"""

import argparse
import json
import os
import re
import textwrap
from collections import Counter
from pathlib import Path

import yaml


MIGRATION_UID = "dd9d4fe6"
MIGRATED_AT = "2026-07-15"
MIGRATED_BY = "argus-a132"
VALID_SUBTYPES = {"semantic", "episodic", "procedural", "reference", "feedback"}
SUBTYPE_MAP = {
    "architectural": "semantic",
    "intergenerational": "episodic",
    "relationship": "semantic",
}
LEGACY_UID_MAP = {
    "agents/argus/.tropo-capsule/memory/entries/release_step_author_vela_test_plan.md":
        "d6dcd993",
}
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def discover_entries(root: Path) -> list[Path]:
    paths = list(root.glob("agents/*/.tropo-capsule/memory/entries/*.md"))
    paths.extend(root.glob(".tropo-studio/memory/entries/*.md"))
    for path in root.glob("vault/files/*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        match = FRONTMATTER_RE.match(text)
        if not match:
            continue
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            continue
        if frontmatter.get("type") == "memory":
            paths.append(path)
    return sorted(set(paths))


def split_entry(path: Path) -> tuple[str, dict, str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("missing or malformed YAML frontmatter")
    frontmatter = yaml.safe_load(match.group(1)) or {}
    if not isinstance(frontmatter, dict):
        raise ValueError("frontmatter is not a mapping")
    return match.group(1), frontmatter, text[match.end():]


def infer_scope(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    if relative.parts[0] == "agents":
        return "agent"
    if relative.parts[0] == ".tropo-studio":
        return "studio"
    return "doctrine"


def compact_context(value: str) -> str:
    collapsed = " ".join(str(value).split())
    return textwrap.shorten(collapsed, width=120, placeholder="…")


def derive_context(frontmatter: dict, body: str) -> str:
    description = frontmatter.get("description")
    if description:
        return compact_context(str(description))
    for raw in body.splitlines():
        candidate = raw.strip()
        if not candidate or candidate in {"---", "***"}:
            continue
        candidate = re.sub(r"^#+\s*", "", candidate)
        candidate = re.sub(r"[*_`]+", "", candidate)
        candidate = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", candidate)
        if candidate:
            return compact_context(candidate)
    return "Migrated historical memory entry; original body preserved verbatim."


def plan_updates(root: Path, path: Path, frontmatter: dict, body: str) -> dict:
    updates: dict = {}
    relative = path.relative_to(root).as_posix()

    if not frontmatter.get("uid"):
        uid = LEGACY_UID_MAP.get(relative)
        if not uid:
            raise ValueError("missing uid and no collision-checked migration mapping")
        updates["uid"] = uid

    original_type = str(frontmatter.get("type") or "")
    if original_type and original_type != "memory":
        updates["migrated_from_type"] = original_type
        updates["type"] = "memory"

    canonical_scope = infer_scope(root, path)
    original_scope = str(frontmatter.get("scope") or "")
    if original_scope != canonical_scope:
        if original_scope:
            updates["migrated_from_scope"] = original_scope
        updates["scope"] = canonical_scope

    original_subtype = str(frontmatter.get("subtype") or "")
    canonical_subtype = SUBTYPE_MAP.get(original_subtype, original_subtype)
    if not canonical_subtype:
        canonical_subtype = "feedback" if original_type == "feedback" else "semantic"
    if canonical_subtype not in VALID_SUBTYPES:
        raise ValueError(f"no adjudicated subtype mapping for {original_subtype!r}")
    if canonical_subtype != original_subtype:
        if original_subtype:
            updates["migrated_from_subtype"] = original_subtype
        updates["subtype"] = canonical_subtype

    original_context = frontmatter.get("context")
    if not original_context:
        updates["context"] = derive_context(frontmatter, body)
    elif len(str(original_context)) > 120:
        updates["migration_original_context"] = str(original_context)
        updates["context"] = compact_context(str(original_context))

    if updates:
        updates["schema_migration"] = MIGRATION_UID
        updates["schema_migrated_at"] = MIGRATED_AT
        updates["schema_migrated_by"] = MIGRATED_BY
    return updates


def yaml_value(value) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return yaml.safe_dump(value, default_flow_style=True, sort_keys=False).strip()


def apply_updates(raw_frontmatter: str, updates: dict) -> str:
    lines = raw_frontmatter.splitlines()
    for key, value in updates.items():
        replacement = f"{key}: {yaml_value(value)}"
        pattern = re.compile(rf"^{re.escape(key)}\s*:")
        for index, line in enumerate(lines):
            if pattern.match(line):
                lines[index] = replacement
                break
        else:
            lines.append(replacement)
    return "\n".join(lines)


def migrate(root: Path, *, apply: bool) -> dict:
    entries = discover_entries(root)
    changed: list[dict] = []
    errors: list[dict] = []
    field_counts: Counter = Counter()

    for path in entries:
        relative = path.relative_to(root).as_posix()
        try:
            raw_frontmatter, frontmatter, body = split_entry(path)
            updates = plan_updates(root, path, frontmatter, body)
            if not updates:
                continue
            changed.append({"path": relative, "fields": sorted(updates)})
            field_counts.update(updates.keys())
            if apply:
                migrated_frontmatter = apply_updates(raw_frontmatter, updates)
                output = f"---\n{migrated_frontmatter}\n---\n{body}"
                # Law 2 preservation plant: migration may change frontmatter,
                # never the body bytes.
                output_match = FRONTMATTER_RE.match(output)
                if output_match is None or output[output_match.end():] != body:
                    raise RuntimeError("body preservation invariant failed")
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_text(output, encoding="utf-8")
                os.replace(temporary, path)
        except Exception as exc:
            errors.append({"path": relative, "error": str(exc)})

    return {
        "mode": "apply" if apply else "dry-run",
        "entries_scanned": len(entries),
        "entries_changed": len(changed),
        "field_updates": dict(sorted(field_counts.items())),
        "changed": changed,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Forward-migrate Engine Phase-1 memory entry schema (dry-run default)."
    )
    parser.add_argument("--apply", action="store_true", help="Write planned frontmatter migrations")
    parser.add_argument(
        "--vault-path",
        default=str(Path(__file__).resolve().parents[2]),
        help="Studio root to migrate (supports scratch-copy proof)",
    )
    args = parser.parse_args()

    root = Path(args.vault_path).resolve()
    if not (root / "vault").is_dir():
        print(json.dumps({"error": f"{root} is not a Studio root"}, indent=2))
        return 2
    report = migrate(root, apply=args.apply)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
