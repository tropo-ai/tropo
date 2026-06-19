#!/usr/bin/env python3
"""
---
uid: d4e9a2c7
title: generate-capability-catalogs — Tool
name: generate-capability-catalogs
type: tool
status: active
owner: argus
domain: Generate three Tropo capability catalogs (tool / skill / sa-agent) from vault entries — v1.15 substrate.
spawnable_by:
- all-executives
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/d4e9a2c7.py [--apply] [--vault-path PATH]
script_path: vault/tools/d4e9a2c7.py
input:
  type: object
  properties:
    apply:
      type: boolean
      description: Without --apply, dry-run preview only
    vault-path:
      type: string
output:
  type: object
  properties:
    verdict:
      type: string
      enum:
      - pass
      - missing-trigger-descriptions
    tool_count:
      type: integer
    skill_count:
      type: integer
    sa_agent_count:
      type: integer
    missing_trigger_descriptions:
      type: integer
destructive: true
audit_required: false
writes_scope:
- .tropo/tool-catalog.md
- .tropo/skill-catalog.md
- .tropo/sa-agent-catalog.md
governance_category: lifecycle
description: 'Reads three sources and emits three agent-canonical catalogs: vault/00-index.jsonl filtered by type:tool → .tropo/tool-catalog.md; .tropo/skills/*.skill.md filtered by type:how-to → .tropo/skill-catalog.md; agents/sa/<name>/<name>.md filtered by type:session-agent → .tropo/sa-agent-catalog.md. Each filter requires extraction_scope:ship and status active. Per Mike-A52 mirror-Claude-Code lock 2026-05-09: catalog filenames preserve user-facing language (tool / skill / sa-agent) even though underlying schema types are tool / how-to / session-agent — the translation happens here. Idempotent — clean re-runs produce byte-identical output.'
domain_tags:
- catalog-generator
- agent-canonical-substrate
- mirror-claude-code
- hybrid-generation
- idempotent
- v1.15-stream-e
trigger_description: Reach for this any time the three Tropo capability catalogs need to be regenerated — typically after adding/amending vault entries with type:tool/how-to/session-agent (new capabilities, edited trigger_description, status changes that affect catalog membership). Also re-run as part of build-release.py preflight to ensure shipped Studios get fresh catalogs. Run with --apply to write; without --apply for dry-run preview that surfaces missing-trigger-description warnings without modifying files.
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
- catalog-generator
- v1.15-stream-e
- agent-canonical-substrate
subsystem_hub:
- 8dd772a0
---
"""
from __future__ import annotations

"""
generate-capability-catalogs.py — v1.15 Tropo Tool / Skill / sa.* Agent Catalog generator.

Reads three sources, emits three agent-canonical catalogs:

    Source                                                  Type filter           Catalog
    ─────────────────────────────────────────────────────── ─────────────────────  ────────────────────────────
    vault/00-index.jsonl                                    type: tool             .tropo/tool-catalog.md
    .tropo/skills/*.skill.md (frontmatter)                  type: how-to           .tropo/skill-catalog.md
    agents/sa/<name>/<name>.md (frontmatter)                type: session-agent    .tropo/sa-agent-catalog.md

Each catalog filter:
    extraction_scope: ship  (catalogs are agent-facing surfaces; non-ship don't appear)
    presence-of trigger_description (per Q2 hybrid lock; entries without are emitted as WARNINGs)

Each catalog entry:
    - Name (heading)
    - One-line domain (or purpose for skills)
    - trigger_description (verbatim hand-authored prose)
    - Implementation pointer (script_path / file path)
    - UID + governed_by capsule

Per Mike-A52 mirror-Claude-Code lock 2026-05-09: catalog filenames preserve user-facing
language (tool / skill / sa-agent) even though underlying schema types are tool / how-to /
session-agent. The translation happens here.

Idempotent: re-running against unchanged sources produces byte-identical catalogs.

Usage:
    python3 .tropo/scripts/generate-capability-catalogs.py [--apply] [--vault-path PATH]

Default mode is dry-run (preview). Use --apply to write.

v1.15 Stream E — first generation of agent-canonical catalogs.
"""


import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

GENERATED_AT = datetime.now().strftime("%Y-%m-%d")


def find_vault_root(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).resolve()
        if (p / "vault").is_dir() and (p / ".tropo").is_dir():
            return p
        sys.exit(f"ERROR: --vault-path {p} does not contain vault/ + .tropo/")
    here = Path(__file__).resolve()
    for candidate in [here.parent.parent.parent, *here.parents]:
        if (candidate / "vault").is_dir() and (candidate / ".tropo").is_dir():
            return candidate
    sys.exit("ERROR: could not resolve vault root (no vault/ + .tropo/ ancestor)")


def _strip_inline_comment(val: str) -> str:
    """Strip trailing YAML inline comments (' # ...') and quotes from a scalar value."""
    if " #" in val:
        val = val.split(" #", 1)[0].rstrip()
    if val.startswith('"') and val.endswith('"'):
        val = val[1:-1]
    return val.strip()


def parse_frontmatter(text: str) -> dict | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    fm_text = text[4:end]
    out = {}
    current_key = None
    for line in fm_text.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", line)
        if m and not line.startswith(" "):
            key, val = m.group(1), m.group(2).strip()
            out[key] = _strip_inline_comment(val)
            current_key = key
        elif line.lstrip().startswith("- ") and current_key:
            existing = out.get(current_key, "")
            if not isinstance(existing, list):
                out[current_key] = []
            val = _strip_inline_comment(line.lstrip()[2:])
            out[current_key].append(val)
    return out


BELT_BUDGET_CHARS = 3072   # ~3KB; generator fails if belt exceeds this
BELT_MAX_ENTRIES = 15       # hard cap; generator fails if more than this carry belt: true


def _extract_python_frontmatter(text: str) -> dict | None:
    """Extract YAML frontmatter from a Python triple-quote docstring (\"\"\"\\n---\\n...)."""
    m = re.search(r'"""\s*\n---\n(.*?)\n---\n', text, re.DOTALL)
    if not m:
        return None
    fm_text = m.group(1)
    out: dict = {}
    current_key: str | None = None
    for line in fm_text.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        km = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", line)
        if km and not line.startswith(" "):
            key, val = km.group(1), km.group(2).strip()
            out[key] = _strip_inline_comment(val)
            current_key = key
        elif line.lstrip().startswith("- ") and current_key:
            if not isinstance(out.get(current_key), list):
                out[current_key] = []
            out[current_key].append(_strip_inline_comment(line.lstrip()[2:]))
    return out


def _belt_name(fm: dict) -> str:
    """Extract short name from title (text before em-dash), fallback to name field."""
    title = fm.get("title", "")
    if "—" in title:
        return title.split("—")[0].strip()
    if " - " in title:
        return title.split(" - ")[0].strip()
    return fm.get("name") or fm.get("uid", "?")


def _belt_invocation(fm: dict) -> str:
    """Derive canonical invocation from belt_invocation, then cli_command, then uid path."""
    if fm.get("belt_invocation"):
        return str(fm["belt_invocation"])
    if fm.get("cli_command"):
        return str(fm["cli_command"])
    uid = fm.get("uid", "")
    if uid and fm.get("_kind") == "tool":
        return f"python3 vault/tools/{uid}.py"
    path = fm.get("_path", "")
    return f"# see {path}"


def collect_belt_entries(vault_root: Path) -> list[dict]:
    """Collect entries with belt: true from vault/tools/*.py and agents/sa/**/*.md."""
    entries: list[dict] = []

    tools_dir = vault_root / "vault" / "tools"
    if tools_dir.exists():
        for src in sorted(tools_dir.glob("*.py")):
            text = src.read_text()
            fm = _extract_python_frontmatter(text)
            if not fm:
                continue
            if fm.get("belt") not in ("true", "True"):
                continue
            if fm.get("status") in ("deprecated", "superseded", "archived"):
                continue
            fm["_path"] = str(src.relative_to(vault_root))
            fm["_kind"] = "tool"
            entries.append(fm)

    sa_dir = vault_root / "agents" / "sa"
    if sa_dir.exists():
        for src in sorted(sa_dir.rglob("*.md")):
            text = src.read_text()
            fm = parse_frontmatter(text)
            if not fm:
                continue
            if fm.get("belt") not in ("true", "True"):
                continue
            if fm.get("status") in ("deprecated", "superseded", "archived"):
                continue
            fm["_path"] = str(src.relative_to(vault_root))
            fm["_kind"] = "session-agent"
            entries.append(fm)

    return entries


def emit_belt_card(entries: list[dict]) -> str:
    """Render the toolbelt reference card (~3KB budget; vault-search always last)."""
    vault_search_uid = "943149d4"
    core = [e for e in entries if e.get("uid") != vault_search_uid]
    tail = [e for e in entries if e.get("uid") == vault_search_uid]
    ordered = core + tail

    lines = [
        "---",
        "uid: toolbelt",
        "name: toolbelt",
        "type: catalog",
        "kind: belt",
        f"generated_at: {GENERATED_AT}",
        "generated_by: generate-capability-catalogs.py",
        "extraction_scope: ship",
        "---",
        "",
        "# Tropo Toolbelt",
        "",
        f"*{len(entries)} core tools. Derived from `belt: true` frontmatter — do not hand-edit.*",
        "",
        "---",
        "",
    ]
    for e in ordered:
        name = _belt_name(e)
        invocation = _belt_invocation(e)
        example = e.get("belt_example") or invocation
        trigger = e.get("trigger_description") or e.get("domain") or e.get("description", "")
        if trigger:
            first_sent = trigger.split(". ")[0].rstrip(".")
            if len(first_sent) > 160:
                first_sent = first_sent[:157] + "..."
            trigger = first_sent + "."
        lines.append(f"### {name}")
        if trigger:
            lines.append(trigger)
            lines.append("")
        lines.append("```")
        lines.append(invocation)
        lines.append("```")
        if example != invocation:
            lines.append(f"*Example:* `{example}`")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Anything not here? → `python3 vault/tools/943149d4.py <query>`*")
    lines.append("")
    lines.append(f"*Tropo Toolbelt | {GENERATED_AT} | v1.15 substrate*")
    return "\n".join(lines) + "\n"


def collect_tools(vault_root: Path) -> list[dict]:
    index = vault_root / "vault" / "00-index.jsonl"
    if not index.exists():
        return []
    out = []
    for line in index.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("type") != "tool":
            continue
        if rec.get("extraction_scope") != "ship":
            continue
        if rec.get("status") in ("deprecated", "superseded"):
            continue
        # Re-read the source file to recover trigger_description + invocation fields not in index
        uid = rec["uid"]
        src = vault_root / "vault" / "files" / f"{uid}.md"
        if src.exists():
            fm = parse_frontmatter(src.read_text())
            if fm:
                rec["trigger_description"] = fm.get("trigger_description")
                rec["domain"] = fm.get("domain")
                rec["transport"] = fm.get("transport")
                rec["cli_command"] = fm.get("cli_command")
                rec["script_path"] = fm.get("script_path")
        out.append(rec)
    return sorted(out, key=lambda r: r.get("title", r.get("uid")))


def collect_typed_files(vault_root: Path, dir_path: Path, type_value: str) -> list[dict]:
    if not dir_path.exists():
        return []
    out = []
    for src in sorted(dir_path.rglob("*.md")):
        text = src.read_text()
        fm = parse_frontmatter(text)
        if not fm:
            continue
        if fm.get("type") != type_value:
            continue
        if fm.get("extraction_scope") != "ship":
            continue
        if fm.get("status") in ("deprecated", "superseded", "archived"):
            continue
        fm["_path"] = str(src.relative_to(vault_root))
        out.append(fm)
    return sorted(out, key=lambda r: r.get("name", r.get("uid", "")))


def emit_tool_catalog(tools: list[dict]) -> str:
    lines = [
        "---",
        "uid: tool-catalog",
        "name: tool-catalog",
        "type: catalog",
        "kind: tool",
        f"generated_at: {GENERATED_AT}",
        "generated_by: generate-capability-catalogs.py (v1.15)",
        "source: vault/00-index.jsonl filtered by type:tool + extraction_scope:ship",
        "governed_by: d5e1b4a3   # tool.capsule v1.4",
        "extraction_scope: ship",
        "---",
        "",
        "# Tropo Tool Catalog",
        "",
        f"*Auto-generated {GENERATED_AT} from vault entries with `type: tool` + `extraction_scope: ship`. Hand-authored content lives in each entry's `trigger_description:` field. Do not edit this file directly — re-run the generator instead.*",
        "",
        "## How to invoke",
        "",
        "Tools are **typed callables**. The Invocation block under each entry is the executable command. Default working directory is the Studio root (the directory containing `vault/` + `.tropo/`). Exit code 0 = pass; non-zero = drift or failure (each entry's Failure Modes section in the underlying vault entry — linked by UID — documents the specific exit-code contract).",
        "",
        f"**{len(tools)} tools** registered in this Studio.",
        "",
        "---",
        "",
    ]
    for t in tools:
        name = t.get("title") or t.get("name") or t["uid"]
        lines.append(f"## {name}")
        lines.append("")
        if t.get("domain"):
            lines.append(f"**Domain.** {_strip_inline_comment(t['domain'])}")
            lines.append("")
        td = t.get("trigger_description")
        if td:
            lines.append(f"**When to reach for it.** {td}")
            lines.append("")
        else:
            lines.append("⚠️ **WARNING — `trigger_description:` missing from vault entry.** Catalog cannot show when-to-invoke prose without this field.")
            lines.append("")
        if t.get("cli_command"):
            lines.append("**Invocation.**")
            lines.append("```")
            lines.append(t["cli_command"])
            lines.append("```")
            lines.append("")
        if t.get("script_path"):
            lines.append(f"**Implementation.** [{t['script_path']}]({'../' + t['script_path']})")
            lines.append("")
        lines.append(f"**UID.** [`{t['uid']}`](../vault/files/{t['uid']}.md) | governed by [`tool.capsule v1.4`](capsules/tool.capsule.md)")
        lines.append("")
        lines.append("---")
        lines.append("")
    lines.append(f"*Tropo Tool Catalog | Generated {GENERATED_AT} | v1.15 substrate*")
    return "\n".join(lines) + "\n"


def emit_skill_catalog(skills: list[dict]) -> str:
    lines = [
        "---",
        "uid: skill-catalog",
        "name: skill-catalog",
        "type: catalog",
        "kind: skill",
        f"generated_at: {GENERATED_AT}",
        "generated_by: generate-capability-catalogs.py (v1.15)",
        "source: .tropo/skills/*.skill.md filtered by type:how-to + extraction_scope:ship",
        "governed_by: a7c3f489   # how-to.capsule v1.3",
        "extraction_scope: ship",
        "---",
        "",
        "# Tropo Skill Catalog",
        "",
        f"*Auto-generated {GENERATED_AT} from `.tropo/skills/*.skill.md` files with `type: how-to` + `extraction_scope: ship`. Skills ARE how-tos in Tropo (codification, not invention — the canonical capsule type is `how-to`; user-facing surface uses 'skill' per Mike-A52 mirror-Claude-Code lock 2026-05-09). Hand-authored content lives in each skill file's `trigger_description:` field. Do not edit this file directly — re-run the generator instead.*",
        "",
        "## How to invoke",
        "",
        "Skills are **inline behavior bundles** — there is no CLI to run. To execute a skill: open the implementation file linked in each entry below, read its Steps section, follow the procedure in your own context. The catalog tells you WHEN to reach for a skill; the implementation file tells you HOW to perform it.",
        "",
        f"**{len(skills)} skills** registered in this Studio.",
        "",
        "---",
        "",
    ]
    for s in skills:
        name = s.get("name") or s.get("skill") or s.get("skill_id") or s.get("title") or s["uid"]
        lines.append(f"## {name}")
        lines.append("")
        if s.get("purpose"):
            lines.append(f"**Domain.** {s['purpose']}")
            lines.append("")
        # v1.15 fold (sa.cold-boot 144 P1): drop the legacy `when` field rendering.
        # `trigger_description:` is the canonical agent-facing prose; rendering both
        # invited "which do I follow?" confusion in cold-boot evaluation.
        td = s.get("trigger_description")
        if td:
            lines.append(f"**When to reach for it.** {td}")
            lines.append("")
        else:
            lines.append("⚠️ **WARNING — `trigger_description:` missing.** Skill registration is incomplete.")
            lines.append("")
        if s.get("_path"):
            lines.append(f"**Implementation.** [{s['_path']}]({'../' + s['_path']})")
            lines.append("")
        lines.append(f"**UID.** `{s['uid']}` | governed by [`how-to.capsule v1.3`](capsules/how-to.capsule.md)")
        lines.append("")
        lines.append("---")
        lines.append("")
    lines.append(f"*Tropo Skill Catalog | Generated {GENERATED_AT} | v1.15 substrate*")
    return "\n".join(lines) + "\n"


def emit_sa_agent_catalog(sas: list[dict]) -> str:
    lines = [
        "---",
        "uid: sa-agent-catalog",
        "name: sa-agent-catalog",
        "type: catalog",
        "kind: sa-agent",
        f"generated_at: {GENERATED_AT}",
        "generated_by: generate-capability-catalogs.py (v1.15)",
        "source: agents/sa/*/<name>.md filtered by type:session-agent + extraction_scope:ship",
        "governed_by: b4e2a718   # session-agent.capsule v1.4",
        "extraction_scope: ship",
        "---",
        "",
        "# Tropo sa.* Agent Catalog",
        "",
        f"*Auto-generated {GENERATED_AT} from `agents/sa/<name>/<name>.md` activation files with `type: session-agent` + `extraction_scope: ship`. Sa.\\* agents are SEMI-AUTONOMOUS (own context + judgment + [QUERY] mid-execution capacity) — a category boundary, not a flavor variation. Plus dual-purpose: real fleet-ops work AND living-example pattern library for users authoring their own. The user-facing 'sa-agent' filename mirrors Claude Code's tool-catalog pattern; underlying schema type is `session-agent`. Hand-authored content lives in each activation file's `trigger_description:` field.*",
        "",
        "## How to commission",
        "",
        "Sa.\\* agents are dispatched, not invoked directly. To commission one: read [`agents/sa/.tropo-studio/CAPSULE.md`](../agents/sa/.tropo-studio/CAPSULE.md) for the canonical 6-step protocol — or the hot-path extraction at [`agents/sa/commission-quickref.md`](../agents/sa/commission-quickref.md) for repeat commissionings within a session. The protocol summary: (1) determine next record number under `agents/sa/<name>/activation-log/`; (2) determine your spawner ID; (3) create the record file with header + `[PENDING]` items; (4) spawn the agent via Task; (5) respond to its `[QUERY]` with `[RESPONSE]`; (6) add work and terminate with `[SHUTDOWN]`.",
        "",
        "## Archetypes",
        "",
        "- **`one-shot`** — spawn once per task; the agent self-terminates after writing `[DONE]` (or after `[SHUTDOWN]` in live-channel mode).",
        "- **`persistent`** — boot once at the start of a session and stay alive; the spawning agent queries it repeatedly throughout the session before sending `[SHUTDOWN]` at retirement.",
        "- **`on-demand`** — spawn when triggered, may run multiple times in a session; lighter-weight than persistent but reusable.",
        "",
        "## Spawnable-by values",
        "",
        "- **`all-executives`** — any executive agent (Argus, Vela, Metis, Orpheus, etc.) may dispatch.",
        "- **`[<agent>, fleet-ops]`** — restricted to the named agents plus the fleet-ops dispatcher (a scheduled-dispatch surface that runs sa.\\* agents on cadence per the fleet-ops registry).",
        "- **`[<agent>]`** — restricted to the named agent only (typically because the sa.\\* serves that agent's workflow specifically, e.g. `sa.metis-nav` is Metis-only).",
        "",
        f"**{len(sas)} session agents** registered in this Studio.",
        "",
        "---",
        "",
    ]
    for s in sas:
        name = s.get("name") or s["uid"]
        lines.append(f"## {name}")
        lines.append("")
        if s.get("domain"):
            lines.append(f"**Domain.** {s['domain']}")
            lines.append("")
        if s.get("archetype"):
            lines.append(f"**Archetype.** `{s['archetype']}`")
            lines.append("")
        if s.get("spawnable_by"):
            spawn = s["spawnable_by"]
            if isinstance(spawn, list):
                spawn = ", ".join(spawn)
            lines.append(f"**Spawnable by.** {spawn}")
            lines.append("")
        td = s.get("trigger_description")
        if td:
            lines.append(f"**When to reach for it.** {td}")
            lines.append("")
        else:
            lines.append("⚠️ **WARNING — `trigger_description:` missing.** Sa.* registration is incomplete.")
            lines.append("")
        if s.get("_path"):
            lines.append(f"**Activation file.** [{s['_path']}]({'../' + s['_path']})")
            lines.append("")
        lines.append(f"**UID.** `{s['uid']}` | governed by [`session-agent.capsule v1.4`](capsules/session-agent.capsule.md)")
        lines.append("")
        lines.append("---")
        lines.append("")
    lines.append(f"*Tropo sa.\\* Agent Catalog | Generated {GENERATED_AT} | v1.15 substrate*")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="Write catalogs (default: dry-run preview)")
    parser.add_argument("--vault-path", help="Explicit vault root")
    args = parser.parse_args()

    vault_root = find_vault_root(args.vault_path)
    print("=" * 70)
    print(f"generate-capability-catalogs.py — v1.15 Stream E")
    print(f"Mode: {'APPLY (writes will happen)' if args.apply else 'DRY-RUN (preview only)'}")
    print(f"Vault root: {vault_root}")
    print("=" * 70)

    tools = collect_tools(vault_root)
    skills = collect_typed_files(vault_root, vault_root / "vault" / "skills", "how-to")
    sas = collect_typed_files(vault_root, vault_root / "agents" / "sa", "session-agent")

    belt_entries = collect_belt_entries(vault_root)

    print(f"\nTools (type:tool, extraction_scope:ship, status:active): {len(tools)}")
    print(f"Skills (type:how-to, extraction_scope:ship, status:active): {len(skills)}")
    print(f"Sa.* agents (type:session-agent, extraction_scope:ship, status:active): {len(sas)}")
    print(f"Belt entries (belt: true): {len(belt_entries)}")

    if len(belt_entries) > BELT_MAX_ENTRIES:
        print(f"\nERROR: {len(belt_entries)} entries carry belt: true — cap is {BELT_MAX_ENTRIES}.", file=sys.stderr)
        print("Remove belt: true from the lowest-priority entries and re-run.", file=sys.stderr)
        return 1

    missing_td = []
    for collection, label in [(tools, "tool"), (skills, "skill"), (sas, "sa-agent")]:
        for r in collection:
            if not r.get("trigger_description"):
                missing_td.append(f"  {label}: {r.get('name', r.get('uid'))}")

    if missing_td:
        print(f"\n⚠️ {len(missing_td)} entries missing trigger_description (will emit WARNING in catalog):")
        for m in missing_td[:10]:
            print(m)
        if len(missing_td) > 10:
            print(f"  ... and {len(missing_td) - 10} more")

    tool_catalog = emit_tool_catalog(tools)
    skill_catalog = emit_skill_catalog(skills)
    sa_catalog = emit_sa_agent_catalog(sas)
    belt_card = emit_belt_card(belt_entries)

    belt_size = len(belt_card)
    if belt_size > BELT_BUDGET_CHARS:
        print(f"\nERROR: belt card is {belt_size} chars — budget is {BELT_BUDGET_CHARS}.", file=sys.stderr)
        print("Trim trigger descriptions or remove lower-priority entries.", file=sys.stderr)
        return 1

    catalogs_dir = vault_root / ".tropo"
    targets = [
        (catalogs_dir / "tool-catalog.md", tool_catalog),
        (catalogs_dir / "skill-catalog.md", skill_catalog),
        (catalogs_dir / "sa-agent-catalog.md", sa_catalog),
        (catalogs_dir / "toolbelt.md", belt_card),
    ]

    print(f"\nCatalogs to emit:")
    for path, content in targets:
        print(f"  {path.relative_to(vault_root)} ({len(content.splitlines())} lines, {len(content)} bytes)")

    if args.apply:
        for path, content in targets:
            path.write_text(content)
            print(f"  ✓ wrote {path.relative_to(vault_root)}")
        print("\n✓ APPLY complete. Three catalogs emitted.")
    else:
        print("\nDRY-RUN — no files written. Re-run with --apply to write.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
