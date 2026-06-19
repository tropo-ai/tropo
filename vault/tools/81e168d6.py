#!/usr/bin/env python3
"""
---
uid: 81e168d6
name: render-boards
type: tool
status: active
owner: vela
domain: "render-boards.py — render board.md files from board-definition + substrate."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/81e168d6.py"
script_path: vault/tools/81e168d6.py
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

"""render-boards.py — render board.md files from board-definition + substrate.

Authored 2026-05-16 by Argus A67 per v1.35.0 design spec d2f8c194 Q26α.

Composes with rebuild-vault.py (invoked as a new step in the rebuild pipeline).
Reads `type: board-definition` entries + `type: project` entries with
`status_board:` bindings (or kernel default project-board for projects without
explicit binding); evaluates each board's sections against the substrate;
renders board.md to disk at `00-tropo-nav/00-tropo-active/<project-slug>/board.md`.

v1.35.0 minimal implementation:
    - Supports Hello Tropo's bound project-board (kernel default at UID c72f1a85)
    - Renders 4 sections: Open Tasks; Sub-Projects/Workstreams; Documents/Decisions; Task Status Summary
    - Walks `member_of:` transitively (subtree recursion semantics per board-definition.capsule)
    - Writes to canonical 00-tropo-nav/00-tropo-active/<slug>/board.md

v1.35.5 enrichment defers: full prose-query parser; full render-enum coverage
(tree; list-with-links; grouped tables); multi-project board rollups;
board-snapshot.capsule frozen-in-time views.

Usage:
    python3 .tropo/scripts/render-boards.py [--apply]
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
INDEX_PATH = VAULT_ROOT / "vault" / "00-index.jsonl"
NAV_ACTIVE = VAULT_ROOT / "00-tropo-nav" / "00-tropo-active"
KERNEL_PROJECT_BOARD_UID = "c72f1a85"


def load_index() -> dict:
    """Load 00-index.jsonl into a UID-keyed dict. Each entry has type/title/state/status/member_of/etc."""
    if not INDEX_PATH.exists():
        return {}
    index = {}
    for line in INDEX_PATH.read_text().splitlines():
        try:
            entry = json.loads(line)
            uid = entry.get("uid")
            if uid:
                index[uid] = entry
        except json.JSONDecodeError:
            continue
    return index


def parse_frontmatter(path: Path) -> dict:
    if not path.exists():
        return {}
    content = path.read_text()
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---\n", 4)
    if end < 0:
        return {}
    try:
        result = yaml.safe_load(content[4:end])
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError:
        return {}


def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def subtree_members(root_uid: str, index: dict) -> list:
    """Walk member_of: subtree transitively. Returns all UIDs that have root_uid in their member_of (direct or transitive)."""
    found = set()
    frontier = {root_uid}
    while frontier:
        new_frontier = set()
        for uid, entry in index.items():
            if uid in found or uid in frontier:
                continue
            members = entry.get("member_of") or []
            if any(m in frontier for m in members):
                found.add(uid)
                new_frontier.add(uid)
        frontier = new_frontier
    return list(found)


def render_table(title: str, rows: list, columns: list, null_result: str) -> str:
    """Render a markdown table."""
    out = [f"## {title}", ""]
    if not rows:
        out.append(f"*{null_result}*")
        out.append("")
        return "\n".join(out)
    out.append("| " + " | ".join(columns) + " |")
    out.append("|" + "|".join("---" for _ in columns) + "|")
    for row in rows:
        cells = []
        for col in columns:
            val = row.get(col, "")
            if val is None:
                val = ""
            cells.append(str(val).replace("|", "\\|").replace("\n", " "))
        out.append("| " + " | ".join(cells) + " |")
    out.append("")
    return "\n".join(out)


def render_list_with_links(title: str, items: list, null_result: str) -> str:
    out = [f"## {title}", ""]
    if not items:
        out.append(f"*{null_result}*")
        out.append("")
        return "\n".join(out)
    for item in items:
        uid = item.get("uid", "")
        t = item.get("title", uid)
        out.append(f"- [{t}](../../../vault/files/{uid}.md)")
    out.append("")
    return "\n".join(out)


def render_hello_tropo_board(project_uid: str, project_fm: dict, index: dict) -> str:
    """Render the project board for a given project per kernel project-board definition.

    v1.35.0 minimal: 4 sections derived from board-definition c72f1a85 schema +
    walked against the project's member_of subtree.
    """
    title = project_fm.get("title", "Project")
    description = project_fm.get("description", "")
    members = subtree_members(project_uid, index)

    # Categorize members
    open_tasks = []
    sub_projects = []
    documents = []
    task_status_all = []

    for uid in members:
        entry = index.get(uid, {})
        etype = entry.get("type", "")
        state = entry.get("state", "")
        status = entry.get("status", "")
        title_str = entry.get("title") or entry.get("name") or uid
        if etype == "task":
            task_status_all.append({
                "title": title_str,
                "owner": entry.get("owner", ""),
                "status": status,
                "state": state,
                "uid": uid,
            })
            if state == "active" and status not in ("done", "cancelled", "closed"):
                open_tasks.append({
                    "title": title_str,
                    "owner": entry.get("owner", ""),
                    "status": status,
                    "modified": entry.get("modified", ""),
                    "uid": uid,
                })
        elif etype in ("project", "project-plan"):
            sub_projects.append({"uid": uid, "title": title_str, "type": etype})
        elif etype in ("decision", "design-brief", "note", "document"):
            documents.append({
                "title": title_str,
                "owner": entry.get("owner", ""),
                "modified": entry.get("modified", ""),
                "uid": uid,
            })

    # Build summary stats
    total_tasks = len(task_status_all)
    done_count = sum(1 for t in task_status_all if t["status"] in ("done", "closed"))
    open_count = sum(1 for t in task_status_all if t["state"] == "active" and t["status"] not in ("done", "cancelled", "closed"))

    out = [
        f"# {title} — Project Board",
        "",
        f"*{description}*",
        "",
        f"**Project:** [{project_uid}](../../../vault/files/{project_uid}.md)",
        f"**Status board:** kernel default [`project-board`](../../../vault/files/{KERNEL_PROJECT_BOARD_UID}.md)",
        "",
        "## State at a glance",
        "",
        f"- **Total tasks:** {total_tasks}",
        f"- **Completed:** {done_count}",
        f"- **Open / in-flight:** {open_count}",
        f"- **Sub-projects + workstreams:** {len(sub_projects)}",
        f"- **Documents + decisions:** {len(documents)}",
        "",
        render_table("Open Tasks", open_tasks, ["title", "owner", "status", "modified"], "— No open tasks. All work at terminal state. —"),
        render_list_with_links("Sub-Projects + Workstreams", sub_projects, "— No sub-projects. —"),
        render_table("Documents + Decisions", documents, ["title", "owner", "modified"], "— No documents. —"),
        render_table("Task Status Summary", task_status_all, ["title", "owner", "status", "state"], "— No tasks. —"),
        "",
        "---",
        "",
        f"*Rendered by `.tropo/scripts/render-boards.py` (v1.35.0 minimal). Regenerates on every `npm run vault:rebuild` from substrate state.*",
    ]
    return "\n".join(out)


def render_all_boards(apply: bool) -> list:
    """Find all projects with status_board: (or kernel-default-inheritance); render each.

    v1.35.0 minimal: only renders projects with explicit status_board: c72f1a85
    or projects under tropo-examples / well-known parents. Argo's own dev-pipeline /
    publish-pipeline / web-pipeline projects don't auto-render at v1.35.0 (would
    add noise; not in scope).
    """
    index = load_index()
    rendered = []
    for uid, entry in index.items():
        if entry.get("type") != "project":
            continue
        if entry.get("status_board") != KERNEL_PROJECT_BOARD_UID:
            continue  # v1.35.0 only renders explicit-binding projects
        project_fm = parse_frontmatter(VAULT_FILES / f"{uid}.md")
        if not project_fm:
            continue
        title = project_fm.get("title", uid)
        slug = slugify(title.split("—")[0].strip() if "—" in title else title)
        target_dir = NAV_ACTIVE / slug
        target_path = target_dir / "board.md"
        board_content = render_hello_tropo_board(uid, project_fm, index)
        if apply:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path.write_text(board_content)
        rendered.append({"project_uid": uid, "target": str(target_path.relative_to(VAULT_ROOT)), "lines": len(board_content.splitlines())})
    return rendered


def main():
    parser = argparse.ArgumentParser(description="Render project boards from board-definition + substrate.")
    parser.add_argument("--apply", action="store_true", help="Write rendered boards to disk (default: dry-run preview)")
    args = parser.parse_args()

    rendered = render_all_boards(args.apply)
    if args.apply:
        print(f"Rendered {len(rendered)} board(s):")
    else:
        print(f"DRY-RUN — would render {len(rendered)} board(s):")
    for r in rendered:
        print(f"  - {r['target']} ({r['lines']} lines) from project {r['project_uid']}")
    if not rendered:
        print("  (no projects with status_board: c72f1a85 binding found at v1.35.0 minimal scope)")
    sys.exit(0)


if __name__ == "__main__":
    main()
