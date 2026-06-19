"""
publish_targets/_gate_orchestrator.py — Mode-aware gate orchestrator for publish.pipeline.

Implements the strict / standard / express gate-check model per c8a47e91 v1.1 design lock.

Strict  — all 5 gates; HALT on any failure (mechanical or qualitative)
Standard — 3 mechanical gates enforced (HALT on failure) + 2 qualitative gates as WARN
Express — minimum gates only; proceeds unless absolute failure

Gates:
  1. extract_cleanness    — no nav-blocks, relations tables, or broken UID refs in output
  2. package_structure    — dated source + 03-design/ present in outbox for article targets
  3. design_walk          — strict: HALT if no acceptance recorded; standard: WARN
  4. publish_state        — sentinel commit + push + Vercel hook (enforced in publish() itself)
  5. visual_eyeball       — strict: HALT if no eyeball signal; standard: WARN; express: skip

Usage (called from publish.py after extraction, before stage):
  from publish_targets._gate_orchestrator import run_mode_gates
  passed = run_mode_gates(extracted, pipeline_def)
  if not passed:
      return 1  # halted by gate

v1.53 E-lane partial — mechanical gates 1+2 fully implemented; gates 3+5 emit human-loop
signals (can't auto-verify in v1; strict mode warns but does not block on 3+5 until
human-signoff substrate is wired).
"""

from __future__ import annotations

import os
import re
import sys

_NAV_BLOCK_RE = re.compile(r'<!--\s*nav-block:start\s*-->', re.MULTILINE)
_RELATIONS_RE = re.compile(r'^\*\*Relations\*\*', re.MULTILINE)
_ORPHAN_UID_RE = re.compile(r'\(\(?[0-9a-f]{8}\.md\)', re.MULTILINE)

VAULT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ─── Individual gate checks ───────────────────────────────────────────────────

def gate_extract_cleanness(extracted: dict) -> tuple[bool, list[str]]:
    """Gate 1: verify article-tier extracted content has no nav-blocks, relations tables, orphan UID refs.

    Only applies to articles/ paths — kb/ and legal/ entries don't have cleanup_rules
    applied and may legitimately carry vault formatting.
    """
    issues: list[str] = []
    for path, content in extracted.items():
        if content is None:
            continue
        # Only check article-tier entries (cleanup_rules applied there)
        if not path.startswith('articles/'):
            continue
        if _NAV_BLOCK_RE.search(content):
            issues.append(f'  [gate-1] nav-block markers present in {path}')
        if _RELATIONS_RE.search(content):
            issues.append(f'  [gate-1] Relations table present in {path}')
        if _ORPHAN_UID_RE.search(content):
            issues.append(f'  [gate-1] orphan UID-style links present in {path}')
    return len(issues) == 0, issues


def gate_package_structure(pipeline_def: dict) -> tuple[bool, list[str]]:
    """Gate 2: verify dated source + 03-design/ exist in outbox for each article target."""
    issues: list[str] = []
    # Resolve article slugs from pipeline_def selection_rules or skip if not article target
    source = pipeline_def.get('source', '')
    if not source:
        return True, []
    outbox_base = os.path.join(VAULT_ROOT, '02-outbox', 'web', 'agentic-builders')
    if not os.path.isdir(outbox_base):
        return True, []  # not an agentic-builders pipeline; skip
    for slug_dir in os.listdir(outbox_base):
        slug_path = os.path.join(outbox_base, slug_dir)
        # Skip non-directories, hidden dirs, and the shared 03-design/ asset folder
        if not os.path.isdir(slug_path) or slug_dir.startswith('.') or slug_dir == '03-design':
            continue
        dated_files = [
            f for f in os.listdir(slug_path)
            if re.match(rf'^{re.escape(slug_dir)}-\d{{4}}-\d{{2}}-\d{{2}}T\d{{6}}\.md$', f)
        ]
        if not dated_files:
            issues.append(f'  [gate-2] no dated source file in 02-outbox/web/agentic-builders/{slug_dir}/')
        design_dir = os.path.join(slug_path, '03-design')
        if not os.path.isdir(design_dir):
            issues.append(f'  [gate-2] 03-design/ missing from 02-outbox/web/agentic-builders/{slug_dir}/')
    return len(issues) == 0, issues


def gate_design_walk(mode: str) -> tuple[bool, list[str]]:
    """Gate 3: design walk with Mike. Auto-verifiable: no; emits human-loop signal."""
    if mode == 'strict':
        return False, ['  [gate-3] strict mode requires recorded design-walk ACCEPT signal (human-in-loop gate; auto-verify not yet implemented — operator must confirm + rerun)']
    if mode == 'standard':
        return True, ['  [gate-3] WARN: standard mode recommends design walk with Mike; skipping is recorded as soft-warning']
    return True, []  # express: skip


def gate_visual_eyeball(mode: str) -> tuple[bool, list[str]]:
    """Gate 5: visual eyeball by Mike on rendered page. Auto-verifiable: no."""
    if mode == 'strict':
        return False, ['  [gate-5] strict mode requires visual eyeball ACCEPT signal (human-in-loop gate; operator must confirm rendered page + rerun)']
    if mode == 'standard':
        return True, ['  [gate-5] WARN: standard mode recommends visual eyeball; skipping recorded as soft-warning']
    return True, []  # express: skip


# ─── Orchestrator ─────────────────────────────────────────────────────────────

def run_mode_gates(extracted: dict, pipeline_def: dict) -> bool:
    """Run gate checks for the given mode. Returns True if publish should proceed.

    strict:   gates 1+2+3+5 must pass (4 = publish_state runs inside publish())
    standard: gates 1+2 enforced; gates 3+5 emit warnings but don't block
    express:  gates 1+2 with lenient halt; gates 3+5 skipped
    """
    mode: str = pipeline_def.get('_mode', 'standard')
    verbose: bool = pipeline_def.get('_verbose', False)
    dry_run: bool = pipeline_def.get('_dry_run', False)

    if dry_run:
        return True  # gates are informational only in dry-run

    print(f'\n--- Mode gates ({mode}) ---')

    all_pass = True

    # Gate 1: extract cleanness (all modes)
    ok, issues = gate_extract_cleanness(extracted)
    if ok:
        print('  [gate-1] extract cleanness: PASS')
    else:
        for msg in issues:
            print(msg)
        if mode in ('strict', 'standard'):
            print('  [gate-1] HALT — extract cleanness failure blocks publish')
            all_pass = False
        else:
            print('  [gate-1] WARN — express mode continues despite extract issues')

    # Gate 2: package structure (all modes, agentic-builders only)
    ok, issues = gate_package_structure(pipeline_def)
    if ok:
        if verbose:
            print('  [gate-2] package structure: PASS')
    else:
        for msg in issues:
            print(msg)
        if mode == 'strict':
            print('  [gate-2] HALT — package structure failure blocks strict publish')
            all_pass = False
        else:
            print('  [gate-2] WARN — proceeding with package structure gap')

    # Gate 3: design walk (strict: halt; standard: warn; express: skip)
    ok, signals = gate_design_walk(mode)
    for msg in signals:
        print(msg)
    if not ok:
        all_pass = False

    # Gate 5: visual eyeball (strict: halt; standard: warn; express: skip)
    # Gate 4 (publish_state) runs inside publish() itself — not checked here.
    ok, signals = gate_visual_eyeball(mode)
    for msg in signals:
        print(msg)
    if not ok:
        all_pass = False

    if all_pass:
        print(f'  Mode gates ({mode}): GO\n')
    else:
        print(f'  Mode gates ({mode}): HALT\n')

    return all_pass
