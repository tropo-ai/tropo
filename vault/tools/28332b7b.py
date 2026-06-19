#!/usr/bin/env python3
"""
---
uid: 28332b7b
name: agent-unify-migrate
type: tool
title: "agent-unify-migrate — v1.69 per-agent atomic migration to vault/agents/<uid>.md"
description: "Per-agent atomic migration script for the v1.69 Agent Unification cycle (0c61a52b). Dry-run-gated; each agent is a 6-step transaction. P0.7 phase-gate asserts P0.1-P0.6 live before any tombstone. Pre-apply gate refuses if target agent is RETIRING or has an open activation entry mid-close."
status: active
state: active
owner: talos
domain: "v1.69 migration — agent unification (S1)"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/28332b7b.py --agent <slug> [--dry-run] [--apply]"
script_path: vault/tools/28332b7b.py
spawnable_by:
  - talos
created: 2026-06-11
created_by: talos-t14
modified: 2026-06-11
modified_by: talos-t15
version: "1.0"
governed_by: 8dd772a0
member_of:
  - "b7649a1c"   # v1.69 root
refs:
  - "0c61a52b"   # v1.69 dev-spec
  - "2f8b4e3d"   # agent.capsule v2.0
schema_version: 2
extraction_scope: argo-reference
tags: [tool, migration, v1.69, agent-unification, per-agent-atomic, dry-run-gated, p0.7-phase-gate]
---
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
TODAY = date.today().isoformat()


# ── P0.7 phase-gate assertions ─────────────────────────────────────────────────
# Asserts P0.1-P0.6 are live before any tombstone can be written.

P0_CHECKS = {
    "P0.1 dual-shape boot resolution": lambda: _check_p01(),
    "P0.2 retire-playbook cutover": lambda: _check_p02(),
    "P0.4 roster-iteration (no hardcoded UIDs)": lambda: _check_p04(),
    "P0.5 transfer-stub v1.1 surface": lambda: _check_p05(),
    "P0.6 vault/agents/ walker in rebuild-index": lambda: _check_p06(),
}


def _check_p01() -> tuple[bool, str]:
    """P0.1: agent-activation.playbook declares dual-shape priority logic."""
    playbook = VAULT_ROOT / '.tropo' / 'playbooks' / 'agent-activation.playbook.md'
    if not playbook.exists():
        return False, "agent-activation.playbook.md not found"
    text = playbook.read_text(encoding='utf-8', errors='replace')
    if 'agent_uid' not in text or 'dual-shape' not in text.lower():
        return False, "dual-shape boot resolution not detected in activation playbook"
    return True, "activation playbook declares dual-shape resolution"


def _check_p02() -> tuple[bool, str]:
    """P0.2: agent-retire.playbook references unified entry."""
    playbook = VAULT_ROOT / '.tropo' / 'playbooks' / 'agent-retire.playbook.md'
    if not playbook.exists():
        return False, "agent-retire.playbook.md not found"
    text = playbook.read_text(encoding='utf-8', errors='replace')
    if 'unified' not in text.lower() and 'agent_uid' not in text:
        return False, "retire playbook does not reference unified entry shape"
    return True, "retire playbook references unified entry"


def _check_p04() -> tuple[bool, str]:
    """P0.4: no hardcoded tombstone-set UIDs in sa.* DEFINITION files (not activation logs)."""
    HARDCODED_UIDS = {'82c06372', 'c407f4c0', '9c2e99ef', 'd97d96a6'}
    sa_dir = VAULT_ROOT / 'agents' / 'sa'
    if not sa_dir.is_dir():
        return True, "no agents/sa/ directory (skip)"
    hits = []
    # Only scan sa.* definition files (sa.<slug>/sa.<slug>.md), not activation-log records
    for sa_subdir in sa_dir.iterdir():
        if not sa_subdir.is_dir():
            continue
        def_file = sa_subdir / f"{sa_subdir.name}.md"
        if not def_file.exists():
            continue
        text = def_file.read_text(encoding='utf-8', errors='replace')
        for uid in HARDCODED_UIDS:
            if uid in text:
                hits.append(f"{def_file.relative_to(VAULT_ROOT)}:{uid}")
    # Also check vault/session-agents/ mirrors
    vs_dir = VAULT_ROOT / 'vault' / 'session-agents'
    if vs_dir.is_dir():
        for f in vs_dir.glob('*.md'):
            text = f.read_text(encoding='utf-8', errors='replace')
            for uid in HARDCODED_UIDS:
                if uid in text:
                    hits.append(f"{f.relative_to(VAULT_ROOT)}:{uid}")
    if hits:
        return False, f"hardcoded UIDs in sa.* definitions: {hits[:3]}"
    return True, "zero hardcoded tombstone-set UIDs in sa.* definitions"


def _check_p05() -> tuple[bool, str]:
    """P0.5: auto_create_transfer_stub points at agent-memory.md, not living-transfer.md."""
    tool = VAULT_ROOT / 'vault' / 'tools' / '40b2f455.py'
    if not tool.exists():
        return False, "write-activation-entry.py not found"
    text = tool.read_text(encoding='utf-8', errors='replace')
    if 'living-transfer.md' in text and 'agent-memory.md' not in text:
        return False, "stub template still references v2 living-transfer.md path"
    if 'agent-memory.md' not in text:
        return False, "stub template does not reference agent-memory.md"
    return True, "transfer-stub template uses v1.1 agent-memory.md surface"


def _check_p06() -> tuple[bool, str]:
    """P0.6: f4b8a6e2.py includes vault/agents/ and vault/playbooks/ walkers."""
    rebuild_idx = VAULT_ROOT / 'vault' / 'tools' / 'f4b8a6e2.py'
    if not rebuild_idx.exists():
        return False, "f4b8a6e2.py not found"
    text = rebuild_idx.read_text(encoding='utf-8', errors='replace')
    has_agents = 'collect_vault_agents_records' in text
    has_playbooks = 'collect_vault_playbooks_records' in text
    if not has_agents or not has_playbooks:
        missing = []
        if not has_agents: missing.append('vault/agents/')
        if not has_playbooks: missing.append('vault/playbooks/')
        return False, f"walkers missing: {missing}"
    return True, "vault/agents/ and vault/playbooks/ walkers present"


def run_phase_gate(run_folder=None) -> bool:  # Path | None; avoid | on Python < 3.10
    """Run all P0 checks. Returns True if all pass. Writes milestone if run_folder given."""
    print("=== P0.7 Phase Gate ===")
    all_pass = True
    results = {}
    for name, check_fn in P0_CHECKS.items():
        passed, detail = check_fn()
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {detail}")
        results[name] = {"passed": passed, "detail": detail}
        if not passed:
            all_pass = False

    if all_pass:
        print("\nP0.7 GATE: ALL CHECKS PASS — migration may proceed\n")
        if run_folder:
            run_folder.mkdir(parents=True, exist_ok=True)
            milestone = {
                "event": "milestone_fired",
                "milestone": "P0-Phase-Gate-Live",
                "group": "Phase-0",
                "timestamp": TODAY,
                "checks": results,
            }
            (run_folder / "run.jsonl").write_text(
                json.dumps(milestone) + "\n", encoding="utf-8"
            )
            print(f"Milestone written to {run_folder}/run.jsonl")
    else:
        print("\nP0.7 GATE: FAILED — do not proceed with migration until all P0 checks pass\n")
    return all_pass


# ── Pre-apply gate ─────────────────────────────────────────────────────────────

def pre_apply_gate(agent_slug: str) -> tuple[bool, str]:
    """Refuse migration only while the target agent's retirement is IN FLIGHT.

    v1.69 gate refinement (Argus A109 2026-06-11; corrects the locked spec's P0.3
    wording to its stated intent — "catches retirements that started before the
    lock appeared"): an ACTIVE agent always has an open activation entry, so
    open-entry-alone must not refuse (as built it blocked every fleet migration;
    caught at the Cosmo canary dry-run). The in-flight signal is status RETIRING —
    written by agent-retire.playbook Step 0.1 (the first hard gate) and cleared at
    close; an interrupted retirement stays RETIRING, so the same check covers it.
    """
    import re

    def _status_is_retiring(text: str) -> bool:
        m = re.search(r'^status:\s*["\']?([A-Za-z-]+)', text, re.MULTILINE)
        return bool(m and m.group(1).upper() == 'RETIRING')

    # Resolve the live status surface, dual-shape (P0.1 precedence):
    # unified entry (agent_uid) -> legacy vault card (status_card_uid) ->
    # legacy agents/<slug>/<slug>-status.md.
    candidates = []
    pointer = VAULT_ROOT / f'agents/{agent_slug}/{agent_slug}-activation.md'
    if pointer.exists():
        ptext = pointer.read_text(encoding='utf-8', errors='replace')
        m = re.search(r'^agent_uid:\s*["\']?([0-9a-f]{8})', ptext, re.MULTILINE)
        if m:
            candidates.append(VAULT_ROOT / f'vault/agents/{m.group(1)}.md')
        m = re.search(r'^status_card_uid:\s*["\']?([0-9a-f]{8})', ptext, re.MULTILINE)
        if m:
            candidates.append(VAULT_ROOT / f'vault/files/{m.group(1)}.md')
    candidates.append(VAULT_ROOT / f'agents/{agent_slug}/{agent_slug}-status.md')

    for sc in candidates:
        if sc.exists():
            if _status_is_retiring(sc.read_text(encoding='utf-8', errors='replace')):
                return False, (
                    f"{agent_slug} is RETIRING — retirement in flight; "
                    f"wait for it to complete"
                )
            break  # first existing surface is authoritative

    return True, "pre-apply gate clear"


# ── Main ───────────────────────────────────────────────────────────────────────

V169_RUN = VAULT_ROOT / "agents/dev-pipeline/activations/b7649a1c"
LOCK_FILE = VAULT_ROOT / ".tropo-studio/locks/migration-in-progress.lock"


# ── Utility ────────────────────────────────────────────────────────────────────

def _extract_frontmatter_raw(content: str) -> str:
    parts = content.split('---', 2)
    return parts[1] if len(parts) >= 3 else ''


def _extract_body(content: str) -> str:
    parts = content.split('---', 2)
    return parts[2].strip() if len(parts) >= 3 else content.strip()


def _parse_frontmatter(content: str) -> dict:
    try:
        import yaml
        return yaml.safe_load(_extract_frontmatter_raw(content)) or {}
    except Exception:
        return {}


def _fm_modify(content: str, changes: dict, additions: dict = None) -> str:
    """Modify frontmatter fields by string manipulation — preserves original formatting.

    changes: {key: value} — replace existing key's value
    additions: {key: value} — add key at end of frontmatter if not already present
    """
    import re
    parts = content.split('---', 2)
    if len(parts) < 3:
        return content
    fm_raw, body = parts[1], parts[2]

    for key, value in (changes or {}).items():
        pattern = re.compile(r'^(' + re.escape(key) + r'\s*:).*$', re.MULTILINE)
        if isinstance(value, str) and any(c in value for c in ':#{}[]|>&!"\'') or (
            isinstance(value, str) and value.startswith(' ')
        ):
            replacement = f'{key}: "{value}"'
        else:
            replacement = f'{key}: {value}'
        fm_raw, n = pattern.subn(replacement, fm_raw)
        if n == 0:
            # Key absent — treat as addition
            if additions is None:
                additions = {}
            additions.setdefault(key, value)

    for key, value in (additions or {}).items():
        import re as _re
        if not _re.search(r'^' + _re.escape(key) + r'\s*:', fm_raw, _re.MULTILINE):
            line = f'{key}: {value}\n'
            fm_raw = fm_raw.rstrip('\n') + '\n' + line

    return f'---{fm_raw}---{body}'


def _bounded_status_notes(body: str, current_gen: str) -> str:
    """Extract current + predecessor generation sections from a status card body.
    Drops sections for generations older than predecessor (current-1).
    """
    import re
    m = re.match(r'^([A-Za-z]+)(\d+)$', current_gen)
    if not m:
        return body
    prefix, curr_num = m.group(1), int(m.group(2))
    pred_num = curr_num - 1

    lines = body.split('\n')
    result, skip = [], False
    for line in lines:
        if re.match(r'^## ', line):
            gen_m = re.search(r'\b' + re.escape(prefix) + r'(\d+)\b', line, re.IGNORECASE)
            skip = bool(gen_m and int(gen_m.group(1)) < pred_num)
        if not skip:
            result.append(line)
    return '\n'.join(result).rstrip()


# ── Identity resolution ────────────────────────────────────────────────────────

# Registry `class:` vocab → agent.capsule v2.0 Required Frontmatter enum.
# Registry uses crew/personal/director/worker/concierge; capsule uses
# executive/director/worker/concierge. `crew` and `personal` both map to
# `executive` (ADR-039: crew-class agents carry executive-level standing).
_REGISTRY_TO_CAPSULE_CLASS = {
    'executive': 'executive',
    'crew': 'executive',
    'personal': 'executive',
    'director': 'director',
    'worker': 'worker',
    'concierge': 'concierge',
}


def _resolve_capsule_class(registry_class: str) -> str:
    """Translate registry class vocab to agent.capsule v2.0 enum value."""
    if not registry_class:
        return 'executive'
    return _REGISTRY_TO_CAPSULE_CLASS.get(registry_class.lower(), registry_class)


def _normalize_status(raw_status) -> str:
    """Normalize a status card's status field to the agent.capsule v2.0 enum.

    Status cards (especially Vela/Orpheus) use multi-line narrative status values
    like 'V61 ACTIVE 2026-06-09 — ...'. Extract the enum word.
    """
    if not raw_status:
        return 'DORMANT'
    s = str(raw_status).strip()
    # Already a clean enum value
    if s.upper() in ('ACTIVE', 'DORMANT', 'RETIRED'):
        return s.upper()
    # Narrative: look for the first enum keyword
    import re
    m = re.search(r'\b(ACTIVE|DORMANT|RETIRED|active|dormant|retired)\b', s)
    if m:
        return m.group(1).upper()
    # Fallback sub-mappings for non-enum vocabulary
    sub_map = {
        'retiring': 'ACTIVE',  # mid-retirement, still counts as was-active
        'draft': 'DORMANT',
        'on-hold': 'DORMANT',
        'shell-active': 'DORMANT',
        'not-commissioned': 'DORMANT',
        'superseded': 'RETIRED',
    }
    return sub_map.get(s.lower(), 'DORMANT')


def _find_activation_ptr(agent_slug: str) -> Path:
    """Locate the activation thin-pointer, trying standard + legacy filenames."""
    base = VAULT_ROOT / f'agents/{agent_slug}'
    for name in (f'{agent_slug}-activation.md', f'{agent_slug}-activate.md', 'activate.md'):
        p = base / name
        if p.exists():
            return p
    # directors may live under agents/directors/<slug>/
    for name in (f'{agent_slug}-activation.md', f'{agent_slug}-activate.md', 'activate.md'):
        p = VAULT_ROOT / 'agents' / 'directors' / agent_slug / name
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Activation thin-pointer not found for '{agent_slug}' "
        f"(tried agents/{agent_slug}/[<slug>-activation|<slug>-activate|activate].md "
        f"and agents/directors/{agent_slug}/[...].md)"
    )


def _resolve_identity(agent_slug: str) -> dict:
    """Read activation thin-pointer + source files; return all fields needed to build the entry."""
    ptr_path = _find_activation_ptr(agent_slug)
    ptr_fm = _parse_frontmatter(ptr_path.read_text('utf-8'))

    charter_uid = ptr_fm.get('charter_uid') or ptr_fm.get('charter')
    soul_uid = ptr_fm.get('soul_uid') or ptr_fm.get('soul')
    status_card_uid = ptr_fm.get('status_card_uid') or ptr_fm.get('status_card')
    tier3_uid = ptr_fm.get('boot_extension_uid') or ptr_fm.get('tier3_uid') or ptr_fm.get('boot_extension')
    agent_root_uid = ptr_fm.get('agent_root_uid')

    sc_path = VAULT_ROOT / f'vault/files/{status_card_uid}.md' if status_card_uid else None
    if sc_path and sc_path.exists():
        sc_text = sc_path.read_text('utf-8')
    else:
        # Fallback: user-owned status file at agents/<slug>/<slug>-status.md
        sc_fallback = VAULT_ROOT / f'agents/{agent_slug}/{agent_slug}-status.md'
        sc_text = sc_fallback.read_text('utf-8') if sc_fallback.exists() else ''
    sc_fm = _parse_frontmatter(sc_text) if sc_text else {}
    t3_path = VAULT_ROOT / f'vault/files/{tier3_uid}.md' if tier3_uid else None
    t3_text = t3_path.read_text('utf-8') if (t3_path and t3_path.exists()) else ''
    t3_fm = _parse_frontmatter(t3_text) if t3_text else {}

    party_uid = sc_fm.get('tropo_agent_id') or sc_fm.get('party_uid')

    # Fall back to activation pointer's own frontmatter for fields absent from status card
    ptr_role = ptr_fm.get('role', '')
    ptr_class = ptr_fm.get('agent_class', '')

    return {
        'charter_uid': charter_uid,
        'soul_uid': soul_uid,
        'status_card_uid': status_card_uid,
        'tier3_uid': tier3_uid,
        'agent_root_uid': agent_root_uid,
        'party_uid': party_uid,
        'generation': sc_fm.get('generation', ''),
        'role': sc_fm.get('role', '') or ptr_role,
        'agent_class': _resolve_capsule_class(
            sc_fm.get('class') or sc_fm.get('agent_class') or ptr_class
        ),
        'status': _normalize_status(sc_fm.get('status')),
        'last_session': sc_fm.get('last_session', ''),
        'model': sc_fm.get('model', ''),
        'current_activation_uid': sc_fm.get('activation_entry') or sc_fm.get('current_activation_uid') or '',
        'continuous_listen': t3_fm.get('continuous_listen', ''),
        'extraction_scope': sc_fm.get('extraction_scope') or t3_fm.get('extraction_scope') or ptr_fm.get('extraction_scope') or '',
        'activation_file_path': str(ptr_path.relative_to(VAULT_ROOT)),
    }


# ── Unified entry assembly ─────────────────────────────────────────────────────

def _build_unified_entry(agent_slug: str, identity: dict, minted_uid: str) -> str:
    """Assemble the full vault/agents/<uid>.md content.

    §Soul is verbatim — never summarized or trimmed (agent.capsule rule 3).
    §Status-Notes is bounded to current + predecessor generation (capsule rule 4).
    """
    import yaml

    def _read_body(uid):
        if not uid:
            return None
        p = VAULT_ROOT / f'vault/files/{uid}.md'
        return _extract_body(p.read_text('utf-8')) if p.exists() else None

    charter_body = _read_body(identity['charter_uid']) or '*(charter not yet authored)*'
    soul_body = _read_body(identity['soul_uid'])
    tier3_body = _read_body(identity['tier3_uid'])
    status_body = _read_body(identity['status_card_uid']) or ''

    status_notes = _bounded_status_notes(status_body, identity['generation'])

    fm: dict = {
        'uid': minted_uid,
        'type': 'agent',
        'title': f'{agent_slug.capitalize()} — {identity["role"]}',
        'agent': agent_slug,
        'role': identity['role'],
        'agent_class': identity['agent_class'],
        'status': identity['status'],
        'generation': identity['generation'],
        'party_uid': identity['party_uid'],
        'agent_root_uid': identity['agent_root_uid'],
        'activation_file': identity['activation_file_path'],
        'state': 'active',
        'governed_by': '2f8b4e3d',
        'member_of': [identity['agent_root_uid']],
        'schema_version': 2,
        'created': TODAY,
        'created_by': 'talos-t15',
        'migration_note': (
            f'v1.69 S1 migration — absorbed {identity["status_card_uid"]} '
            f'(status) · {identity["charter_uid"]} (charter) · '
            f'{identity["soul_uid"]} (soul) · {identity["tier3_uid"]} '
            f'(tier3). dev-spec 0c61a52b.'
        ),
    }
    if identity['model']:
        fm['model'] = identity['model']
        fm['platform'] = 'claude-code'
    if identity['last_session']:
        fm['last_session'] = identity['last_session']
    if identity['current_activation_uid']:
        fm['current_activation_uid'] = identity['current_activation_uid']
    if identity['continuous_listen']:
        fm['continuous_listen'] = identity['continuous_listen']
    if identity['extraction_scope']:
        fm['extraction_scope'] = identity['extraction_scope']

    fm_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Assemble body sections — soul and tier3 are optional
    display = agent_slug.replace('-', ' ').replace('.', ' ').title()
    parts = [
        f"---\n{fm_yaml.rstrip()}\n---\n\n",
        f"# {display} — Unified Agent Entry\n\n",
        f"*One agent, one entry per agent.capsule v2.0 (2f8b4e3d). "
        f"v1.69 migration dev-spec 0c61a52b.*\n\n---\n\n",
        f"## §Charter\n\n{charter_body}\n\n---\n\n",
    ]
    if soul_body:
        parts.append(f"## §Soul\n\n{soul_body}\n\n---\n\n")
    elif tier3_body:
        # Soul is inline in the Tier 3 body (e.g., Talos — no separate soul file).
        parts.append(
            f"## §Soul\n\n"
            f"*Soul is authored inline in §Boot-Extension (§Group 2 Step 2.0 of the Tier 3). "
            f"There is no separate soul file for this agent — see §Boot-Extension below.*\n\n---\n\n"
        )
    if tier3_body:
        parts.append(f"## §Boot-Extension\n\n{tier3_body}\n\n---\n\n")
    parts += [
        f"## §Status-Notes\n\n",
        f"*Bounded to current + predecessor generation. "
        f"Older notes live in activation entries.*\n\n",
        f"{status_notes}\n\n---\n\n",
        f"*{display} — Unified Agent Entry | UID `{minted_uid}` | "
        f"Migrated {TODAY} by talos-t15 | v1.69 dev-spec 0c61a52b*\n",
    ]
    return ''.join(parts)


# ── Dry-run diff output ────────────────────────────────────────────────────────

def _run_dry_run(agent_slug: str, unified_uid: str, overrides: dict = None) -> int:
    identity = _resolve_identity(agent_slug)
    if overrides:
        identity.update(overrides)
    tombstone_set = [
        (uid, label)
        for uid, label in [
            (identity['status_card_uid'], 'status card'),
            (identity['charter_uid'], 'charter'),
            (identity['soul_uid'], 'soul'),
            (identity['tier3_uid'], 'tier3 boot extension'),
        ]
        if uid  # skip None entries (agents with incomplete substrate)
    ]
    party_uid = identity['party_uid']

    sep = '=' * 72
    print(f"\n[DRY-RUN] Migration diff — {agent_slug} → vault/agents/{unified_uid}.md\n{sep}")

    # Step 1 — full unified entry content
    print(f"\n{'─'*72}")
    print(f"[DIFF-1] CREATE vault/agents/{unified_uid}.md  (new file)")
    print(f"{'─'*72}")
    print(_build_unified_entry(agent_slug, identity, unified_uid))

    # Step 2 — thin-pointer diff
    ptr_path = identity['activation_file_path']
    print(f"\n{'─'*72}")
    print(f"[DIFF-2] MODIFY {ptr_path}")
    print(f"{'─'*72}")
    print(f"+agent_uid: {unified_uid}   (added to frontmatter; all other fields unchanged)")

    # Step 3 — principal entry diff
    principal_path = VAULT_ROOT / f'vault/files/{party_uid}.md'
    print(f"\n{'─'*72}")
    print(f"[DIFF-3] MODIFY vault/files/{party_uid}.md  (type:principal)")
    print(f"{'─'*72}")
    if principal_path.exists():
        p_fm = _parse_frontmatter(principal_path.read_text('utf-8'))
        current_sc = p_fm.get('status_card_uid', '(not set)')
        print(f"-status_card_uid: {current_sc}")
        print(f"+status_card_uid: {unified_uid}")
    else:
        print(f"  WARNING: principal entry vault/files/{party_uid}.md not found")

    # Step 4 — tombstone diffs
    for uid, label in tombstone_set:
        t_path = VAULT_ROOT / f'vault/files/{uid}.md'
        print(f"\n{'─'*72}")
        print(f"[DIFF-4] TOMBSTONE vault/files/{uid}.md  ({label})")
        print(f"{'─'*72}")
        if t_path.exists():
            t_fm = _parse_frontmatter(t_path.read_text('utf-8'))
            cur_status = t_fm.get('status', '(not set)')
            print(f"-status: {cur_status}")
            print(f"+status: superseded")
            print(f"+superseded_by: {unified_uid}")
            print(f"+superseded_at: {TODAY}")
            print(f"+superseded_by_agent: talos-t15")
            print(f"  (body: preserved verbatim — not recycled)")
        else:
            print(f"  WARNING: vault/files/{uid}.md not found")

    # Steps 5-6 — commands
    print(f"\n{'─'*72}")
    print(f"[DIFF-5] Rebuild index slice")
    print(f"{'─'*72}")
    print(f"  python3 vault/tools/e8d4c1b9.py --only {unified_uid}")

    print(f"\n{'─'*72}")
    print(f"[DIFF-6] Re-render crew brief")
    print(f"{'─'*72}")
    print(f"  python3 .tropo/scripts/render-crew-brief.py")

    print(f"\n{sep}")
    print(f"UNIFIED UID: {unified_uid}")
    print(f"Tombstone set: {' · '.join(uid for uid, _ in tombstone_set)}")
    print(f"Re-run with --apply after [GO-4] from Argus.")
    return 0


# ── Apply — 6-step transaction ─────────────────────────────────────────────────

def _log_event(event: dict) -> None:
    V169_RUN.mkdir(parents=True, exist_ok=True)
    with open(V169_RUN / 'run.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(event) + '\n')


def _run_apply(agent_slug: str, unified_uid: str, overrides: dict = None) -> int:
    import subprocess

    identity = _resolve_identity(agent_slug)
    if overrides:
        identity.update(overrides)
    tombstone_set = [
        (uid, label)
        for uid, label in [
            (identity['status_card_uid'], 'status card'),
            (identity['charter_uid'], 'charter'),
            (identity['soul_uid'], 'soul'),
            (identity['tier3_uid'], 'tier3 boot extension'),
        ]
        if uid  # skip None entries (agents with incomplete substrate)
    ]
    party_uid = identity['party_uid']

    # Write lock file
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(
        f"agent: {agent_slug}\nunified_uid: {unified_uid}\nstarted: {TODAY}\n",
        encoding='utf-8'
    )
    _log_event({"event": "migration_started", "agent": agent_slug, "unified_uid": unified_uid, "timestamp": TODAY})

    try:
        # Step 1 — create unified entry
        unified_content = _build_unified_entry(agent_slug, identity, unified_uid)
        agents_dir = VAULT_ROOT / 'vault' / 'agents'
        agents_dir.mkdir(parents=True, exist_ok=True)
        unified_path = agents_dir / f'{unified_uid}.md'
        unified_path.write_text(unified_content, encoding='utf-8')
        if not unified_path.exists():
            raise RuntimeError(f"Step 1 failed — unified entry not found after write: {unified_path}")
        print(f"[1/6] Created vault/agents/{unified_uid}.md")
        _log_event({"event": "step_complete", "step": 1, "path": f"vault/agents/{unified_uid}.md", "timestamp": TODAY})

        # Step 2 — re-point thin-pointer
        ptr_path = VAULT_ROOT / identity['activation_file_path']
        new_ptr = _fm_modify(ptr_path.read_text('utf-8'), {}, {'agent_uid': unified_uid})
        ptr_path.write_text(new_ptr, encoding='utf-8')
        print(f"[2/6] Re-pointed {identity['activation_file_path']} → agent_uid: {unified_uid}")
        _log_event({"event": "step_complete", "step": 2, "path": identity['activation_file_path'], "timestamp": TODAY})

        # Step 3 — update principal entry status_card_uid
        principal_path = VAULT_ROOT / f'vault/files/{party_uid}.md'
        if principal_path.exists():
            new_principal = _fm_modify(principal_path.read_text('utf-8'), {}, {'status_card_uid': unified_uid})
            principal_path.write_text(new_principal, encoding='utf-8')
            print(f"[3/6] Updated principal vault/files/{party_uid}.md → status_card_uid: {unified_uid}")
        else:
            print(f"[3/6] WARNING: principal vault/files/{party_uid}.md not found — skipped")
        _log_event({"event": "step_complete", "step": 3, "principal": party_uid, "timestamp": TODAY})

        # Step 4 — tombstone old identity files (LAST content step)
        for uid, label in tombstone_set:
            uid_path = VAULT_ROOT / f'vault/files/{uid}.md'
            if uid_path.exists():
                tombstoned = _fm_modify(
                    uid_path.read_text('utf-8'),
                    {'status': 'superseded'},
                    {'superseded_by': unified_uid, 'superseded_at': TODAY, 'superseded_by_agent': 'talos-t15'},
                )
                uid_path.write_text(tombstoned, encoding='utf-8')
                print(f"[4/6] Tombstoned vault/files/{uid}.md ({label})")
            else:
                print(f"[4/6] WARNING: vault/files/{uid}.md not found ({label})")
        _log_event({"event": "step_complete", "step": 4, "tombstone_set": [uid for uid, _ in tombstone_set], "timestamp": TODAY})

        # Step 5 — rebuild index slice
        result = subprocess.run(
            ['python3', str(VAULT_ROOT / 'vault/tools/e8d4c1b9.py'), '--only', unified_uid],
            capture_output=True, text=True, cwd=str(VAULT_ROOT),
            stdin=subprocess.DEVNULL, timeout=120,
        )
        tail = (result.stdout + result.stderr)[-600:] if (result.stdout + result.stderr) else ''
        print(f"[5/6] Rebuild index slice: exit {result.returncode}")
        if tail:
            print(tail)
        _log_event({"event": "step_complete", "step": 5, "exit_code": result.returncode, "timestamp": TODAY})

        # Step 6 — re-render crew brief
        render = VAULT_ROOT / '.tropo/scripts/render-crew-brief.py'
        if render.exists():
            result = subprocess.run(
                ['python3', str(render)],
                capture_output=True, text=True, cwd=str(VAULT_ROOT),
                stdin=subprocess.DEVNULL, timeout=60,
            )
            print(f"[6/6] Re-rendered crew brief: exit {result.returncode}")
            _log_event({"event": "step_complete", "step": 6, "exit_code": result.returncode, "timestamp": TODAY})
        else:
            print(f"[6/6] render-crew-brief.py not found — skipping crew brief re-render")
            _log_event({"event": "step_complete", "step": 6, "skipped": True, "reason": "script not found", "timestamp": TODAY})

        _log_event({"event": "migration_complete", "agent": agent_slug, "unified_uid": unified_uid, "timestamp": TODAY})
        print(f"\n[APPLY] Migration complete: {agent_slug} → vault/agents/{unified_uid}.md")
        return 0

    except Exception as exc:
        _log_event({"event": "migration_failed", "agent": agent_slug, "error": str(exc), "timestamp": TODAY})
        print(f"\nERROR: Migration failed at step: {exc}")
        return 1

    finally:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="v1.69 per-agent atomic migration to vault/agents/<uid>.md"
    )
    parser.add_argument("--agent", required=True, help="Agent slug to migrate (e.g., cosmo, vela)")
    parser.add_argument("--unified-uid", default=None,
                        help="Pre-minted UID for the unified entry. "
                             "If omitted, minted fresh via vault/tools/5187be30.py.")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Print full diff without writing (default)")
    parser.add_argument("--apply", action="store_true",
                        help="Execute the 6-step transaction (requires phase-gate PASS + Argus GO)")
    parser.add_argument("--status", default=None,
                        help="Override status in unified entry (ACTIVE/DORMANT/RETIRED)")
    parser.add_argument("--class", dest="agent_class", default=None,
                        help="Override agent_class in unified entry (executive/director/worker/concierge)")
    args = parser.parse_args()

    dry_run = not args.apply

    # P0.7 phase gate (always runs first)
    run_folder = V169_RUN
    gate_passed = run_phase_gate(run_folder if not dry_run else None)
    if not gate_passed:
        print("ERROR: Phase gate failed. Run 'python3 vault/tools/d2b9c8e6.py' to diagnose.")
        return 1

    # Pre-apply gate
    ok, reason = pre_apply_gate(args.agent)
    if not ok:
        print(f"ERROR: Pre-apply gate: {reason}")
        return 1

    # Resolve or mint unified UID
    unified_uid = args.unified_uid
    if not unified_uid:
        import subprocess
        result = subprocess.run(
            ['python3', str(VAULT_ROOT / 'vault/tools/5187be30.py'),
             '--reason', f'{args.agent} unified agent entry v1.69'],
            capture_output=True, text=True, cwd=str(VAULT_ROOT), stdin=subprocess.DEVNULL,
        )
        unified_uid = result.stdout.strip()
        if not unified_uid:
            print(f"ERROR: Failed to mint UID via mint-uid tool: {result.stderr}")
            return 1
        print(f"Minted unified entry UID: {unified_uid}")

    overrides = {}
    if args.status:
        overrides['status'] = args.status
    if args.agent_class:
        overrides['agent_class'] = args.agent_class

    if dry_run:
        return _run_dry_run(args.agent, unified_uid, overrides)

    return _run_apply(args.agent, unified_uid, overrides)


if __name__ == "__main__":
    sys.exit(main())
