#!/usr/bin/env python3
"""
---
uid: 6510afc7
name: render-crew-brief
type: tool
status: active
owner: talos
domain: "render-crew-brief.py — Auto-render the crew tables in 00-crew-brief.md."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/6510afc7.py"
script_path: vault/tools/6510afc7.py
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

"""
render-crew-brief.py — Auto-render the crew tables in 00-crew-brief.md.

Authored captain-mode by vela-v46 2026-05-16 per Mike-V46 directive
"fix the root cause of the crew brief always being wrong." Same shape as
.tropo/scripts/render-boards.py (auto-render derivable content from
canonical substrate) and the Navigation block render pattern
(HUMAN-NAVIGATION.md OS-tier primitive — substrate is for agents; rendered
surface is for humans).

Root cause this fixes: the "Operating crew" + "Dormant/retired" tables in
00-crew-brief.md duplicate per-agent status card fields (generation,
status, last_session, role) that already live canonically at
vault/files/<status_card_uid>.md. Hand-edited duplication can't keep up
when generations roll over multiple times per session (3 rolls in 90 min
on 2026-05-16: A66→A67→pending-A68, T4→T5→pending-T6). Auto-derive the
tables from the canonical source; leave human-authored sections alone.

Discovery: walks vault/files/ for type:project entries with the
'agent-root-project' tag (these are the canonical per-agent root projects
established v1.21.0). For each crew agent, resolves agents/<slug>/<slug>-
activation.md (BY DESIGN per agent-activation.playbook v2.11) → reads
status_card_uid: frontmatter → loads the current status card.

Renders between sentinel markers:
  <!-- crew-table:start -->
  ...
  <!-- crew-table:end -->

Idempotent: replaces content between sentinels on every run. Leaves all
content outside the sentinels untouched (human-authored sections stay
human-authored). Updates last_updated: frontmatter to today's date.

Filter: only renders agent_class == 'executive' or == 'tropo'. Director
and sa.* classes are crew-roster substrate but not surfaced in the
operational crew tables (matches existing crew-brief shape).

Wired into rebuild-vault.py Step 4 (canonical render pass) so it runs at
every vault rebuild. Can also be invoked standalone via:
  python3 .tropo/scripts/render-crew-brief.py
"""
import os
import re
import sys
import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
VAULT_ROOT = SCRIPT_DIR.parent.parent
CREW_BRIEF_PATH = VAULT_ROOT / "00-crew-brief.md"
VAULT_FILES_DIR = VAULT_ROOT / "vault" / "files"

FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
SENTINEL_START = "<!-- crew-table:start -->"
SENTINEL_END = "<!-- crew-table:end -->"


def parse_frontmatter(path: Path) -> dict:
    """Lightweight frontmatter parser — line-based scalar extraction.

    Avoids PyYAML dependency to keep this script stdlib-only. We only need
    scalar fields (status, generation, last_session, agent, role, etc.) —
    no nested dicts or lists from these particular files.
    """
    try:
        text = path.read_text(errors='replace')
    except Exception:
        return {}
    m = FM_RE.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        sm = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+?)\s*(?:#.*)?$', line)
        if not sm:
            continue
        key, value = sm.group(1), sm.group(2).strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        fm[key] = value
    return fm


def discover_crew() -> list[dict]:
    """Walk vault/files/ for agent_root projects; resolve each to current status card."""
    crew = []
    for f in VAULT_FILES_DIR.glob('*.md'):
        try:
            text = f.read_text(errors='replace')[:3000]
        except Exception:
            continue
        if 'type: project' not in text:
            continue
        if 'agent-root-project' not in text.lower():
            continue
        fm = parse_frontmatter(f)
        slug = fm.get('agent_slug')
        agent_class = fm.get('agent_class')
        if not slug or agent_class not in ('executive', 'tropo'):
            continue  # skip directors + sa.* (not shown in operational tables)
        role = fm.get('role', '')
        # Resolve activation file → status_card_uid (canonical post-v1.21.0)
        candidates = [
            VAULT_ROOT / 'agents' / slug / f'{slug}-activation.md',
            VAULT_ROOT / 'agents' / slug / 'activate.md',
        ]
        status_card_uid = None
        agent_uid = None
        for c in candidates:
            if c.is_file():
                act_fm = parse_frontmatter(c)
                # v1.69 dual-shape (P0.1 precedence; Argus A109 2026-06-11,
                # caught at the Cosmo canary apply — the renderer followed the
                # legacy status_card_uid to a TOMBSTONE and showed the migrated
                # agent as 'superseded'): a thin-pointer declaring agent_uid:
                # means ALL identity reads go to vault/agents/<agent_uid>.md.
                agent_uid = act_fm.get('agent_uid')
                status_card_uid = act_fm.get('status_card_uid')
                if agent_uid or status_card_uid:
                    break
        # Resolve status surface: unified entry FIRST (agent_uid), then legacy
        # vault card (status_card_uid), then pre-v1.21.0 agents/<slug> path.
        # Skip silently if none resolves — surfaces as missing in the table.
        status_card_path = None
        if agent_uid:
            p = VAULT_ROOT / 'vault' / 'agents' / f'{agent_uid}.md'
            if p.is_file():
                status_card_path = p
                status_card_uid = agent_uid  # rendered link targets the unified entry
        if status_card_path is None and status_card_uid:
            p = VAULT_FILES_DIR / f'{status_card_uid}.md'
            if p.is_file():
                status_card_path = p
        if status_card_path is None:
            legacy = VAULT_ROOT / 'agents' / slug / f'{slug}-status.md'
            if legacy.is_file():
                status_card_path = legacy
                # Synthesize a UID-equivalent for the rendered link (legacy
                # status cards don't have vault UIDs; link to the file path).
                if not status_card_uid:
                    status_card_uid = f'agents/{slug}/{slug}-status.md'
        if status_card_path is None:
            continue  # no resolvable status card; skip silently
        sc_fm = parse_frontmatter(status_card_path)
        crew.append({
            'slug': slug,
            'class': agent_class,
            'role': role,
            'generation': sc_fm.get('generation', '?'),
            'status': sc_fm.get('status', '?'),
            'last_session': sc_fm.get('last_session', '?'),
            'status_card_uid': status_card_uid,
        })
    return crew


def classify(status: str) -> str:
    """Bucket status string into ACTIVE / RETIRED / INACTIVE / OTHER."""
    s = status.upper()
    if s.startswith('ACTIVE'):
        return 'ACTIVE'
    if 'RETIRING' in s:
        return 'RETIRING'
    if 'RETIRED' in s:
        return 'RETIRED'
    if 'INACTIVE' in s or 'DORMANT' in s:
        return 'INACTIVE'
    return 'OTHER'


def render_row(agent: dict) -> str:
    """One markdown table row for an agent."""
    name = agent['slug'].capitalize() if not agent['slug'].startswith('d.') else agent['slug']
    gen = f"**{agent['generation']}**"
    last = agent['last_session']
    status = agent['status']
    sc_uid = agent['status_card_uid']
    # Legacy status card paths (Tropo + similar) are stored as relative paths;
    # vault/files/<uid>.md cases get the canonical link shape; v1.69 unified
    # entries (vault/agents/<uid>.md exists) link there instead.
    if sc_uid.startswith('agents/'):
        sc_link = f"[status](../../{sc_uid})" if False else f"[status]({sc_uid})"
    elif (VAULT_ROOT / 'vault' / 'agents' / f'{sc_uid}.md').is_file():
        sc_link = f"[{sc_uid}](vault/agents/{sc_uid}.md)"
    else:
        sc_link = f"[{sc_uid}](vault/files/{sc_uid}.md)"
    return f"| {name} | {gen} | {last} | {status} (status card: {sc_link}) |"


def render_tables(crew: list[dict]) -> str:
    """Render the two crew tables (Operating + Dormant) as one markdown block."""
    today = datetime.date.today().isoformat()
    # Sort: ACTIVE by last_session desc; RETIRED/INACTIVE by last_session desc
    active = sorted(
        [a for a in crew if classify(a['status']) in ('ACTIVE', 'RETIRING')],
        key=lambda a: a['last_session'], reverse=True
    )
    dormant = sorted(
        [a for a in crew if classify(a['status']) in ('RETIRED', 'INACTIVE', 'OTHER')],
        key=lambda a: a['last_session'], reverse=True
    )
    out = []
    out.append("**Operating crew (active executors right now):**")
    out.append("")
    out.append("| Agent | Generation | Last Session | Status |")
    out.append("|---|---|---|---|")
    # Mike is the founder — special-cased; not derivable from agent_root projects
    out.append(f"| Mike | Founder | {today} | ACTIVE |")
    for a in active:
        out.append(render_row(a))
    out.append("")
    out.append("**Dormant / on-hold / retired:**")
    out.append("")
    out.append("| Agent | Generation | Last Session | Status |")
    out.append("|---|---|---|---|")
    for a in dormant:
        out.append(render_row(a))
    out.append("")
    out.append(f"*Tables auto-rendered from per-agent status cards by `.tropo/scripts/render-crew-brief.py` on {today}. Status cards are the canonical source of truth; the body sections above and below this block remain human-authored.*")
    return "\n".join(out)


def replace_between_sentinels(text: str, start: str, end: str, replacement: str) -> tuple[str, bool]:
    """Replace content between sentinel markers. Returns (new_text, was_found)."""
    pattern = re.compile(re.escape(start) + r'\n.*?\n' + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        return text, False
    new_text = pattern.sub(f"{start}\n{replacement}\n{end}", text)
    return new_text, True


def update_last_updated(text: str) -> str:
    """Update the last_updated: frontmatter field to today's date."""
    today = datetime.date.today().isoformat()
    new_value = f'"{today} (auto-rendered by render-crew-brief.py)"'
    pattern = re.compile(r'^last_updated:\s*.*$', re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(f"last_updated: {new_value}", text, count=1)
    return text


def main() -> int:
    if not CREW_BRIEF_PATH.is_file():
        print(f"ERROR: crew brief not found at {CREW_BRIEF_PATH}", file=sys.stderr)
        return 1
    crew = discover_crew()
    if not crew:
        print("WARN: no crew agents discovered — render skipped", file=sys.stderr)
        return 0
    tables = render_tables(crew)
    text = CREW_BRIEF_PATH.read_text()
    new_text, found = replace_between_sentinels(text, SENTINEL_START, SENTINEL_END, tables)
    if not found:
        print(f"ERROR: sentinel markers '{SENTINEL_START}' / '{SENTINEL_END}' not found in {CREW_BRIEF_PATH}", file=sys.stderr)
        print(f"       Add the markers around the auto-rendered crew tables section to enable rendering.", file=sys.stderr)
        return 2
    new_text = update_last_updated(new_text)
    if new_text == text:
        print(f"Crew brief already current ({len(crew)} agents discovered; no changes)")
        return 0
    CREW_BRIEF_PATH.write_text(new_text)
    print(f"Crew brief rendered: {len(crew)} agents discovered "
          f"({sum(1 for a in crew if classify(a['status']) in ('ACTIVE','RETIRING'))} active, "
          f"{sum(1 for a in crew if classify(a['status']) in ('RETIRED','INACTIVE','OTHER'))} dormant)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
