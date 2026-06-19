"""
article_readiness.py — Shared required-fields check logic for source articles + ship-artifact wrappers.

Consumed by:
  - tropo-validate.py (vault-rebuild-time WARN-level checks across all entries)
  - publish-check.py (user-facing preflight on a specific article + wrapper)

Single source of truth for what makes an article + wrapper "publish-ready" per:
  - agentic-builders/lib.ts parseVaultFile() requirements (subtype, slug, published_at)
  - publish.py extract_manifest_root filters (kind, target, canonical_source, parent)
  - publish.pipeline.capsule v1.1 §3 + §7 schema
  - c5a7e391 §13.3 P1+P2+P6 polish spec

Authored v1.49.0.2 as DRY-extraction per R1 paired-walk P1 finding on publish-check.py
(skeptic-arch 2026-05-22: "DRY violation is real and worth refactoring — extract the
field-presence rules into .tropo/scripts/lib/article_readiness.py and have both consume").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ─── Shared constants ──────────────────────────────────────────────────────

VALID_WRAPPER_KINDS = ('file', 'folder')
"""Per ship-artifact.capsule v1.4 §schema — kind: must be one of these values."""

NON_PUBLISH_READY_STATUSES = ('draft', 'archived', 'recycled')
"""Article + wrapper statuses that exempt the entry from publish-field checks.
   Drafts are in-progress; archived are historical; recycled are soft-deleted.
   Per c5a7e391 §13.3 P1 spec discipline + v1.49.0.2 refinement after surfacing
   false-positive on 88436be8 (Substack article in draft state)."""


# ─── Result dataclass ──────────────────────────────────────────────────────

@dataclass
class CheckResult:
    """Result of a readiness check. Findings are plain strings without [WARN]/[FAIL]/[OK]
    prefixes — consumers prepend their own prefixes (publish-check.py uses _ok/_fail/_warn
    with ANSI color; tropo-validate.py uses [WARN]/[FAIL] text prefixes for log compatibility).
    """
    findings: list[str] = field(default_factory=list)
    """Each finding describes one defect. No severity prefix (consumer adds it)."""
    blocking: list[str] = field(default_factory=list)
    """List of short defect-name tokens for summary aggregation (e.g., 'slug', 'kind', 'target')."""
    skipped: bool = False
    """True if check was skipped (e.g., source is draft → publish-fields not required yet)."""


# ─── Source article checks ─────────────────────────────────────────────────

def check_source_article_required_fields(source_uid: str, source_fm: dict) -> CheckResult:
    """Verify a source article has the fields required by agentic-builders/lib.ts parseVaultFile().

    Required when entry has subtype:article AND status in (locked, active):
      - title:         (string; required for rendering)
      - slug:          (string; URL path component; lib.ts returns null without it)
      - published_at:  (YYYY-MM-DD; lib.ts returns null without it)

    Status discipline (per v1.49.0.2): drafts/archived/recycled are SKIPPED — publish-fields
    only required when article is in publish-ready state. Avoids false-positives on
    in-progress drafts.

    Args:
        source_uid: 8-hex UID (used in error messages)
        source_fm: parsed YAML frontmatter dict

    Returns:
        CheckResult with findings + blocking + skipped flag.
    """
    result = CheckResult()

    # Must be subtype:article
    if source_fm.get('subtype') != 'article':
        result.findings.append(
            f'source {source_uid} subtype:{source_fm.get("subtype")!r} not subtype:article — '
            f'web rendering requires subtype:article'
        )
        result.blocking.append('subtype:article')
        return result

    # Status check — drafts/archived/recycled skip publish-field checks
    status = source_fm.get('status')
    if status in NON_PUBLISH_READY_STATUSES:
        result.skipped = True
        return result

    # title check
    if not source_fm.get('title'):
        result.findings.append(
            f'source {source_uid} (status:{status}) missing required field `title:` — '
            f'add to frontmatter at vault/files/{source_uid}.md'
        )
        result.blocking.append('title')

    # slug check
    slug = source_fm.get('slug')
    if not slug:
        # Suggest a slug derived from title (mirrors agentic-builders/lib.ts slugify logic)
        title = source_fm.get('title', '')
        suggested = ''
        if title:
            suggested = re.sub(r'[^a-z0-9\s-]', '', str(title).lower())
            suggested = re.sub(r'\s+', '-', suggested).strip('-')[:60]
        suggested_hint = f' (suggested from title: slug: "{suggested}")' if suggested else ''
        result.findings.append(
            f'source {source_uid} (status:{status}) missing required field `slug:` — '
            f'add to frontmatter: slug: "<url-path-component>"{suggested_hint}'
        )
        result.blocking.append('slug')

    # published_at check
    if not source_fm.get('published_at'):
        result.findings.append(
            f'source {source_uid} (status:{status}) missing required field `published_at:` (YYYY-MM-DD) — '
            f'agentic-builders/lib.ts parseVaultFile returns null without it; article silently dropped from getAllArticles()'
        )
        result.blocking.append('published_at')

    return result


# ─── Ship-artifact wrapper checks ──────────────────────────────────────────

def check_wrapper_required_fields(wrapper_uid: str, wrapper_fm: dict) -> CheckResult:
    """Verify a ship-artifact wrapper has the fields required by publish.py extract_manifest_root.

    Required for ALL ship-artifacts:
      - kind:             ('file' or 'folder'; publish.py filters on entry.get('kind')=='file')
      - target:           (array per ship-artifact.capsule v1.3+; manifest_walker filters by target)

    Required for kind=file additionally:
      - canonical_source: (path to source file; e.g., argo-os/vault/files/<source-uid>.md)
      - parent:           (8-hex category UID; used by publish.py _PARENT_TO_SUBDIR for output_path)

    Folder-class wrappers (e.g., category roots like 4938b65a Articles) are EXEMPT from
    canonical_source + parent checks — they ARE the parent.

    Args:
        wrapper_uid: 8-hex UID
        wrapper_fm: parsed YAML frontmatter dict

    Returns:
        CheckResult with findings + blocking + skipped flag.
    """
    result = CheckResult()

    # Check 1: kind present + valid value (REQUIRED for ALL ship-artifacts)
    kind = wrapper_fm.get('kind')
    if not kind:
        result.findings.append(
            f'wrapper {wrapper_uid} missing required field `kind:` (must be one of {list(VALID_WRAPPER_KINDS)}) — '
            f'publish.py extract_manifest_root filters entry.get("kind")==\"file\" so wrappers without kind: silently drop'
        )
        result.blocking.append('kind')
        kind = None  # skip kind-conditional checks below
    elif kind not in VALID_WRAPPER_KINDS:
        result.findings.append(
            f'wrapper {wrapper_uid} `kind: {kind!r}` not in valid set {list(VALID_WRAPPER_KINDS)}'
        )
        result.blocking.append('kind-shape')

    # Check 2: target present + array shape (REQUIRED for ALL ship-artifacts)
    target = wrapper_fm.get('target')
    if not target:
        result.findings.append(
            f'wrapper {wrapper_uid} missing required field `target:` — must be array like `target: [web]` '
            f'(per ship-artifact.capsule v1.3+; scalar target: shape silently skips entry)'
        )
        result.blocking.append('target')
    elif not isinstance(target, list):
        result.findings.append(
            f'wrapper {wrapper_uid} `target:` must be array, got {type(target).__name__}'
        )
        result.blocking.append('target-shape')

    # Folder-class wrappers don't need canonical_source or parent (they ARE the parent)
    if kind != 'file':
        return result

    # Check 3: canonical_source (file-class only)
    if not wrapper_fm.get('canonical_source'):
        result.findings.append(
            f'wrapper {wrapper_uid} (kind:file) missing required field `canonical_source:` '
            f'(path to source file the wrapper extracts; e.g., argo-os/vault/files/<source-uid>.md)'
        )
        result.blocking.append('canonical_source')

    # Check 4: parent present + 8-hex shape (file-class only)
    # YAML parses unquoted 8-hex strings as int (e.g., `parent: 62823771`); coerce to str for shape check
    parent = wrapper_fm.get('parent')
    if not parent:
        result.findings.append(
            f'wrapper {wrapper_uid} (kind:file) missing required field `parent:` '
            f'(category UID for output_path derivation per publish.py _PARENT_TO_SUBDIR)'
        )
        result.blocking.append('parent')
    else:
        parent_str = str(parent)
        if not re.fullmatch(r'[0-9a-f]{8}', parent_str):
            result.findings.append(
                f'wrapper {wrapper_uid} (kind:file) `parent: {parent_str!r}` not 8-hex UID shape'
            )
            result.blocking.append('parent-shape')

    return result
