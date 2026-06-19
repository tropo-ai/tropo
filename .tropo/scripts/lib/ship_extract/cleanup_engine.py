"""cleanup_engine — Applies cleanup_rules to extracted file content.

v1.43.0 Stream C extraction from build-release.py. Authored 2026-05-18 by argus-a72.
v1.51.0 schema-implementation gap closed 2026-05-24 by talos-t9 per Metis G59 P0 diagnosis:
  added strip_nav_blocks, strip_relations_table, strip_italic_provenance_lines,
  broken_link_policy: strip, and fixed double-paren orphan-UID bug in Pattern 2.

Per ship-artifact.capsule v1.3 (substrate UID eeb59ddf), entries may declare
`cleanup_rules:` specifying transformations to apply during extraction:

- `strip_argo_markers` — remove `<!-- argo-only -->...<!-- /argo-only -->` blocks from body
- `strip_nav_blocks` — remove `<!-- nav-block:start -->...<!-- nav-block:end -->` blocks
- `strip_relations_table` — remove **Relations** heading + GFM table that follows
- `strip_italic_provenance_lines` — remove italic-only lines containing UID/LOCKED/Authored-by/agent-id patterns
- `strip_trailing_sections` — remove substrate-maintenance sections at body tail (e.g. `## Changelog`,
  `## Schema Migrations`, `## Amendment History`, `## Revision History`) that document the file's own
  version history. Internal content already captured in frontmatter `amend_history`. Accepts `true`
  (uses defaults: Changelog / Schema Migrations / Amendment History / Revision History / Version History)
  or a list of section heading names to override the default set. Strips from the matching `## <name>`
  heading (and any immediately-preceding horizontal rule) through end-of-file. Surfaced by metis-g61
  2026-05-25 from Studio Manifesto live-render bleed; Mike-G61 directive `fix properly as we go`.
- `broken_link_policy` — how to handle cross-references that don't resolve in the output target
  - `preserve` — keep the link text as-is (default; matches release-target behavior)
  - `inline_text` — replace `[text](broken-uid.md)` with just `text`
  - `mark_broken` — wrap broken links with explanatory marker
  - `strip` — drop both link text and ref entirely
- `uid_rewrite_template` — pattern for transforming UID-based vault references to target-appropriate paths
  - Release target default: no rewrite (UIDs stay as `vault/files/<uid>.md`)
  - Web target default: `/kb/<uid>` per v1.42 walk-decision B

This module exposes:

- `apply_cleanup_rules(content, entry, target='release')` — apply all declared cleanup_rules to a file's content
- `apply_uid_rewrite_template(content, template, target_uids=None)` — perform UID rewriting per template

These functions are PURE (return transformed content; do not write to disk).
The calling orchestration script reads source file → applies cleanup_engine →
writes result via output_writer.

v1.42 substrate state: full cleanup pattern enforcement for web target depends on
`cleanup_rules:` field being populated on every web-target ship-artifact entry;
v1.43 ships the engine + default behaviors; per-entry cleanup_rules authoring is
ongoing as web-target entries are minted.
"""

import re


# Default uid_rewrite_template values per target (per v1.42 capsule v1.3 walk-decision B)
DEFAULT_UID_REWRITE_TEMPLATES = {
    'release': None,  # No rewrite — UIDs stay as vault/files/<uid>.md
    'web': '/kb/<uid>',  # Web target default — discriminator-level routing defers to v1.43+
}


# Default section-heading names stripped when strip_trailing_sections: true (no list override).
# Substrate-maintenance section classes — version history captured in frontmatter amend_history
# is already canonical; body-side duplication bleeds to public render. Authored 2026-05-25 by
# metis-g61 per Mike-G61 directive `fix properly as we go; no hot fixes`.
DEFAULT_TRAILING_SECTIONS_TO_STRIP = [
    'Changelog',
    'Schema Migrations',
    'Amendment History',
    'Revision History',
    'Version History',
]


def apply_cleanup_rules(content, entry, target='release', target_uids=None):
    """Apply all declared cleanup_rules to a file's content.

    v1.43 ships the engine + default cleanup behaviors. Per-entry `cleanup_rules:`
    overrides default behavior when declared.

    Args:
        content: Source file content (string).
        entry: Hydrated ship-artifact entry dict (may have 'cleanup_rules' field).
        target: Target key ('release' | 'web' | etc.) — selects target-appropriate defaults.
        target_uids: Optional set of UIDs that exist in the output target's manifest.
                     Used by broken_link_policy to detect cross-references that don't resolve.

    Returns:
        Cleaned-up content string ready to write to output.
    """
    rules = entry.get('cleanup_rules', {}) or {}
    if isinstance(rules, str):
        # Backward-compat: pre-v1.3 entries may have cleanup_rules as a simple string flag
        rules = {'strip_argo_markers': True} if rules == 'strip_argo_markers' else {}

    # Rule: strip_argo_markers — remove <!-- argo-only -->...<!-- /argo-only --> blocks
    if rules.get('strip_argo_markers', False):
        content = re.sub(
            r'<!--\s*argo-only\s*-->.*?<!--\s*/argo-only\s*-->',
            '',
            content,
            flags=re.DOTALL,
        )

    # Rule: strip_nav_blocks — remove <!-- nav-block:start -->...<!-- nav-block:end --> blocks
    if rules.get('strip_nav_blocks', False):
        content = re.sub(
            r'\n*<!--\s*nav-block:start\s*-->.*?<!--\s*nav-block:end\s*-->\n*',
            '\n',
            content,
            flags=re.DOTALL,
        )

    # Rule: strip_relations_table — remove **Relations** heading + GFM table that follows
    if rules.get('strip_relations_table', False):
        content = re.sub(
            r'\n*\*\*Relations\*\*\s*\n+\|\s*Relation\s*\|\s*Target\s*\|\s*\n\|[^\n]+\|\s*\n(?:\|[^\n]+\|\s*\n)*\n*',
            '\n',
            content,
            flags=re.MULTILINE,
        )

    # Rule: strip_italic_provenance_lines — remove italic-only lines with UID/LOCKED/Authored-by/agent-id patterns
    if rules.get('strip_italic_provenance_lines', False):
        content = re.sub(
            r'^\*[^*\n]*(?:UID\s*`[a-f0-9]{8}`|LOCKED|Authored.*by|metis-g\d+|argus-a\d+|vela-v\d+|talos-t\d+|cosmo-c\d+|orpheus-o\d+).*?\*\s*$\n?',
            '',
            content,
            flags=re.MULTILINE,
        )

    # Rule: strip_trailing_sections — remove substrate-maintenance sections at body tail
    # (e.g. "## Changelog", "## Schema Migrations") whose content duplicates frontmatter
    # amend_history. Match `true` (use defaults) or a list override.
    # Strips from the matching ## heading + optional immediately-preceding horizontal rule
    # through end-of-file.
    strip_trailing = rules.get('strip_trailing_sections', False)
    if strip_trailing:
        section_names = (
            strip_trailing if isinstance(strip_trailing, list) else DEFAULT_TRAILING_SECTIONS_TO_STRIP
        )
        alt = '|'.join(re.escape(name) for name in section_names)
        content = re.sub(
            rf'\n*(?:^---\s*\n+)?^## (?:{alt})\s*$.*\Z',
            '\n',
            content,
            flags=re.MULTILINE | re.DOTALL,
        )

    # Rule: uid_rewrite_template — transform UID-based vault references
    template = rules.get('uid_rewrite_template')
    if template is None:
        template = DEFAULT_UID_REWRITE_TEMPLATES.get(target)
    if template is not None:
        content = apply_uid_rewrite_template(content, template, target_uids=target_uids)

    # Rule: broken_link_policy — handle cross-references that don't resolve
    policy = rules.get('broken_link_policy', 'preserve')
    if policy != 'preserve' and target_uids is not None:
        content = _apply_broken_link_policy(content, policy, target_uids)

    return content


def apply_uid_rewrite_template(content, template, target_uids=None):
    """Transform UID-based vault references per the rewrite template.

    Patterns matched:
    - `vault/files/<uid>.md` → template-substituted form
    - `(<uid>.md)` in markdown links — when uid is 8-hex
    - Bare UID strings in inline contexts where the link target is a vault entry

    Args:
        content: Source content (string).
        template: Rewrite template string with `<uid>` placeholder (e.g., '/kb/<uid>').
                  If None, no rewrite is performed.
        target_uids: Optional set of UIDs that exist in the output target's manifest.
                     If provided, only references to UIDs IN this set are rewritten;
                     references to UIDs not in the target are left as-is (broken_link_policy
                     handles those separately).

    Returns:
        Content with UID references rewritten per the template.
    """
    if template is None:
        return content

    def _rewrite_uid(match):
        uid = match.group(1)
        if target_uids is not None and uid not in target_uids:
            return match.group(0)  # Leave as-is; not in target manifest
        return template.replace('<uid>', uid)

    # Pattern 1: vault/files/<uid>.md links
    content = re.sub(r'vault/files/([a-f0-9]{8})\.md', _rewrite_uid, content)
    # Pattern 2: Bare (<uid>.md) markdown link targets
    # Fix: only add wrapping parens on the rewrite path; leave-as-is path returns full match
    # (prior bug: lambda unconditionally added parens, double-wrapping preserved UIDs)
    def _rewrite_paren_match(match):
        uid = match.group(1)
        if target_uids is not None and uid not in target_uids:
            return match.group(0)  # Leave as-is; full match already includes parens
        return '(' + template.replace('<uid>', uid) + ')'
    content = re.sub(r'\(([a-f0-9]{8})\.md\)', _rewrite_paren_match, content)

    return content


def _apply_broken_link_policy(content, policy, target_uids):
    """Internal: apply broken_link_policy to references that don't resolve in target.

    Args:
        content: Source content.
        policy: 'inline_text' | 'mark_broken' | 'strip'.
        target_uids: Set of UIDs present in the output target's manifest.

    Returns:
        Content with broken links handled per policy.
    """
    def _handle_link(match):
        text = match.group(1)
        uid = match.group(2)
        if uid in target_uids:
            return match.group(0)  # Link resolves; keep
        if policy == 'inline_text':
            return text  # Replace [text](broken-uid.md) with just text
        if policy == 'mark_broken':
            return f'{text} *(broken link: {uid})*'
        if policy == 'strip':
            return ''  # Drop both link text and ref entirely
        return match.group(0)

    return re.sub(r'\[([^\]]+)\]\(([a-f0-9]{8})\.md\)', _handle_link, content)
