"""Shared library — duplicate top-level YAML key detection + merge.

Single canonical implementation of the duplicate-top-level-YAML-key
defect class detection and merge logic for Tropo-OS substrate hygiene.

Both `fix-duplicate-yaml-keys.py` (one-shot cleanup) and
`tropo-validate.py` (`check_duplicate_yaml_keys`) import from this
module — no parallel implementations.

Detection scope: top-level YAML keys ONLY. A within-list value
duplicate (same UID twice in one block-style list under a single key)
is a different defect class — out of scope per Mike-A63 2026-05-14;
filed at vault/files/6ba0e525.md.

Implementation note: line-by-line parser, NOT PyYAML. PyYAML's
last-wins behavior masks the defect we're trying to detect.

Spec: vault/files/81555e45.md v0.4 §3.1 + §3.2.
Stream A of v1.29.0; see vault/files/d4eaf245.md for execution plan.
"""

import re
from typing import Optional

# Top-level YAML key regex: identifier characters at column 0 followed by colon.
# Matches `member_of:`, `uid:`, `tags:`, etc. Does not match `  - item` or
# `    nested: value` (indented lines), nor comments, nor list dashes.
_TOP_LEVEL_KEY_RE = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_]*):(.*)$')


def extract_frontmatter(file_text: str) -> Optional[tuple[str, str, str]]:
    """Extract YAML frontmatter from a markdown file's full text.

    Returns (opening_delim_block, frontmatter_body, rest_of_file) or None
    if no frontmatter delimiters found.

    Round-trip invariant: opening + body + after == file_text exactly.

    - opening_delim_block: `'---\\n'`
    - frontmatter_body: YAML between delimiters, NO trailing newline
      (the trailing `\\n` lives at the start of `after`).
    - rest_of_file: starts with `'\\n---\\n'` (or `'\\n---'` at EOF) so
      concatenation reproduces the original byte-for-byte.

    Worked example:
      input:  `'---\\nfoo: bar\\n---\\nbody\\n'`
      output: `('---\\n', 'foo: bar', '\\n---\\nbody\\n')`
      round-trip: `'---\\n' + 'foo: bar' + '\\n---\\nbody\\n'` ==
        `'---\\nfoo: bar\\n---\\nbody\\n'` ✓
    """
    if not file_text.startswith('---\n'):
        return None
    # Find the closing `---` on its own line
    rest = file_text[4:]  # skip opening `---\n`
    closing_idx = rest.find('\n---\n')
    if closing_idx == -1:
        # Try EOF case (file ends with `---` no trailing newline)
        if rest.endswith('\n---'):
            closing_idx = len(rest) - 4
            return ('---\n', rest[:closing_idx], rest[closing_idx:])
        return None
    body = rest[:closing_idx]
    # `after` starts at the `\n` of `\n---\n` (preserves the newline
    # before the closing delimiter so round-trip reconstruction is
    # byte-exact). Mirrors the EOF-branch slice convention above.
    after = rest[closing_idx:]
    return ('---\n', body, after)


def detect_duplicate_yaml_keys(frontmatter_text: str) -> dict[str, int]:
    """Detect duplicate top-level YAML keys in frontmatter text.

    Args:
        frontmatter_text: The YAML frontmatter string (between `---`
            delimiters; do NOT include the delimiters themselves).

    Returns:
        Dict mapping each duplicated top-level key name to its occurrence
        count (only keys with count > 1 are returned). Empty dict if no
        duplicates detected.

    Detection scope: top-level YAML keys ONLY. Within-list value
    duplicates (same UID twice in one block-style list under a single
    key) are a different defect class — out of scope per Mike-A63
    2026-05-14; filed at vault/files/6ba0e525.md.

    Implementation: line-by-line scan; counts occurrences of
    `^[a-zA-Z_][a-zA-Z0-9_]*:` at column 0 of frontmatter. Does NOT use
    PyYAML (PyYAML's last-wins semantic masks the defect we are
    detecting).
    """
    counts: dict[str, int] = {}
    for line in frontmatter_text.splitlines():
        match = _TOP_LEVEL_KEY_RE.match(line)
        if match is None:
            continue
        key = match.group(1)
        counts[key] = counts.get(key, 0) + 1
    return {k: v for k, v in counts.items() if v > 1}


def _strip_inline_comment(line_value: str) -> str:
    """Strip an inline YAML `# end-of-line comment` from a list item value.

    Per YAML semantics: outside a quoted string, `#` preceded by whitespace
    starts a comment that runs to end of line. Inside a quoted string, `#`
    is part of the value.

    Examples (input → output):
      `"f87e33f0"   # tropo-documentation`     → `"f87e33f0"`
      `abc123 # short comment`                  → `abc123`
      `"value#hash"`                            → `"value#hash"` (unchanged; `#` inside quotes)
      `"f87e33f0"`                              → `"f87e33f0"` (no comment)
      `unquoted-value`                          → `unquoted-value` (no comment)

    v1.0.4 fix per Round-4-pre corruption finding 2026-05-15: prior parser
    stored the whole post-`- ` content (including inline comments) as the
    item value, which on re-emission produced corrupted YAML
    (`""f87e33f0"   # comment"`). This helper restores proper YAML semantics.
    """
    s = line_value.strip()
    if not s:
        return s
    # If the value starts with a quote, find the matching closing quote
    # and treat everything after as comment-or-whitespace.
    if s[0] in ('"', "'"):
        quote = s[0]
        # Find closing quote (no escape handling needed — UIDs don't contain
        # quotes; this is bounded by the substrate-class we're operating on).
        close_idx = s.find(quote, 1)
        if close_idx == -1:
            # Malformed — return as-is; merge logic upstream may catch it
            return s
        return s[: close_idx + 1].rstrip()
    # Unquoted value: scan for ` #` (whitespace + hash) which starts a comment.
    # Standalone `#` at column 0 of the value is also a comment marker.
    for i, ch in enumerate(s):
        if ch == '#' and (i == 0 or s[i - 1] in (' ', '\t')):
            return s[:i].rstrip()
    return s


def _parse_inline_list(value_text: str) -> Optional[list[str]]:
    """Parse a YAML inline list (e.g., `[a, b, "c"]`) into a list of strings.

    Returns None if value_text is not a valid inline list (caller falls
    back to scalar handling).
    """
    s = value_text.strip()
    if not (s.startswith('[') and s.endswith(']')):
        return None
    inner = s[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    # Simple comma split — values are UIDs / short strings; nested commas
    # are not expected in this defect class.
    for raw in inner.split(','):
        item = raw.strip()
        # Strip surrounding quotes if present
        if (item.startswith('"') and item.endswith('"')) or \
           (item.startswith("'") and item.endswith("'")):
            item = item[1:-1]
        if item:
            items.append(item)
    return items


def _collect_block_list_items(
    lines: list[str], start_idx: int
) -> tuple[list[str], int, bool]:
    """Collect block-style list items immediately following lines[start_idx].

    Returns (items, next_idx, has_comments).
    - next_idx points to the first line that is NOT a continuation of
      this block list.
    - has_comments is True if the block contained ANY indented `#` comment
      lines (caller uses this to fail-loud rather than silently drop
      annotations on merge).

    Continuation rules (v1.0.1):
    - Indented `- ` line → list item (collected).
    - Indented `#` comment line → has_comments=True; line itself is NOT
      collected as an item; caller decides whether to refuse-merge for
      the file.
    - Blank line → continuation IF the next non-blank line is also an
      indented `- ` item (allows human-formatted lists with grouping
      blanks); otherwise terminates the block.
    - Anything else → terminates the block.
    """
    items: list[str] = []
    has_comments = False
    i = start_idx
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        # Block-list continuation: indented `-` line
        if line.startswith(' ') and stripped.startswith('- '):
            # v1.0.4: strip inline `# end-of-line comments` BEFORE quote-strip,
            # per proper YAML semantics. Prior parser stored the whole
            # post-`- ` content (including comments) which on re-emission
            # produced corrupted YAML.
            raw = _strip_inline_comment(stripped[2:])
            item = raw.strip()
            if (item.startswith('"') and item.endswith('"')) or \
               (item.startswith("'") and item.endswith("'")):
                item = item[1:-1]
            items.append(item)
            i += 1
            continue
        # Block-list comment continuation: indented `#` comment line.
        # Mark has_comments and skip; caller fails loud per spec §3.1
        # step 5 "preserve all other lines verbatim".
        if line.startswith(' ') and stripped.startswith('#'):
            has_comments = True
            i += 1
            continue
        # Blank line: peek ahead. If next non-blank is indented `- `,
        # treat blank(s) as continuation (human formatting with grouping
        # blanks). Otherwise terminate the block.
        if line.strip() == '':
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines) and lines[j].startswith(' ') and \
               lines[j].lstrip().startswith('- '):
                # Skip past the blank(s); resume collection at j
                i = j
                continue
            # Blank followed by non-list content → terminate
            break
        # Anything else terminates the block
        break
    return items, i, has_comments


def merge_duplicate_yaml_keys(
    frontmatter_text: str,
) -> tuple[str, dict[str, int], list[str]]:
    """Merge duplicate top-level YAML keys into single canonical entries.

    For each key with > 1 occurrence in the frontmatter, merge values
    into one canonical block-style list entry per the v0.4 spec §3.1
    merge semantics:
      1. Merge in DOCUMENT ORDER. First occurrence wins position;
         subsequent occurrences appended.
      2. Deduplicate values exactly (string-equal) — repeated UIDs
         collapse to one entry preserving first position.
      3. Inline list (`key: [a, b]`) + block-style list (`key:\\n  - c`)
         → merged block-style list (`key:\\n  - "a"\\n  - "b"\\n  - "c"`).
      4. Scalar-conflict case (duplicate top-level key with conflicting
         scalar values, e.g., two `title:` lines with different strings)
         → caller handles via the returned errors list; this function
         does NOT mutate scalar-conflict files.

    Args:
        frontmatter_text: YAML frontmatter (between `---` delimiters).

    Returns:
        Tuple of (merged_frontmatter, dropped_per_key, errors).
        - merged_frontmatter: Reconstructed frontmatter with duplicates
          merged. If errors list is non-empty (scalar conflict), the
          returned text equals the input text (no mutation).
        - dropped_per_key: Dict of key name → count of duplicate
          occurrences dropped (e.g., {"member_of": 1} means 2 occurrences
          collapsed to 1; one was dropped).
        - errors: List of human-readable error strings for scalar
          conflicts that the operator must resolve manually.
    """
    duplicates = detect_duplicate_yaml_keys(frontmatter_text)
    if not duplicates:
        return frontmatter_text, {}, []

    lines = frontmatter_text.split('\n')
    # First pass: classify each duplicate-key as list-mergeable or scalar-conflict.
    # Collect all values per key. If any value is a non-empty scalar (not list),
    # and there are multiple non-empty scalars that differ, it's a scalar conflict.
    key_values: dict[str, list[list[str]]] = {k: [] for k in duplicates}
    key_first_idx: dict[str, int] = {}
    key_occurrence_idxs: dict[str, list[int]] = {k: [] for k in duplicates}
    key_block_end_idx: dict[str, list[int]] = {k: [] for k in duplicates}
    key_scalar_values: dict[str, list[str]] = {k: [] for k in duplicates}
    key_has_comments: dict[str, bool] = {k: False for k in duplicates}

    i = 0
    while i < len(lines):
        line = lines[i]
        match = _TOP_LEVEL_KEY_RE.match(line)
        if match is None:
            i += 1
            continue
        key = match.group(1)
        value_part = match.group(2).strip()
        if key in duplicates:
            if key not in key_first_idx:
                key_first_idx[key] = i
            key_occurrence_idxs[key].append(i)
            # Determine value shape
            if value_part == '':
                # Block-style list expected on following lines
                items, next_idx, has_comments = _collect_block_list_items(lines, i + 1)
                key_values[key].append(items)
                key_block_end_idx[key].append(next_idx - 1)
                if has_comments:
                    key_has_comments[key] = True
                i = next_idx
                continue
            inline = _parse_inline_list(value_part)
            if inline is not None:
                # Inline list
                key_values[key].append(inline)
                key_block_end_idx[key].append(i)
                i += 1
                continue
            # Scalar value (not a list)
            key_scalar_values[key].append(value_part)
            key_values[key].append([])
            key_block_end_idx[key].append(i)
            i += 1
            continue
        i += 1

    # Detect refuse-merge cases:
    # 1. Scalar conflicts (different scalar values for same key)
    # 2. In-list comments (would silently drop annotations on merge — refuse per
    #    spec §3.1 step 5 "preserve all other lines verbatim")
    errors: list[str] = []
    for key, scalars in key_scalar_values.items():
        if len({s for s in scalars if s}) > 1:
            errors.append(
                f"scalar-conflict: key '{key}' has conflicting scalar values "
                f"({sorted(set(scalars))}); manual resolution required"
            )
    for key, has_comments in key_has_comments.items():
        if has_comments:
            errors.append(
                f"in-list-comments: key '{key}' has comment lines inside its "
                f"block-style list; merge would silently drop them; manual "
                f"resolution required (consolidate the duplicate key by hand "
                f"or move comments above the key)"
            )
    if errors:
        return frontmatter_text, {}, errors

    # No scalar conflicts — perform list merge for each duplicate key.
    # Build the merged block-style list value for each key.
    merged_blocks: dict[str, list[str]] = {}
    dropped_per_key: dict[str, int] = {}
    for key, value_lists in key_values.items():
        all_items: list[str] = []
        for items in value_lists:
            all_items.extend(items)
        # Dedupe preserving first position
        seen: set[str] = set()
        deduped: list[str] = []
        for item in all_items:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        merged_blocks[key] = deduped
        dropped_per_key[key] = len(all_items) - len(deduped)

    # Reconstruct frontmatter:
    #   - For each duplicate key, replace the FIRST occurrence's lines
    #     (from key_first_idx[key] through key_block_end_idx[key][0])
    #     with the merged block-style entry.
    #   - For subsequent occurrences, drop the lines (from occurrence_idx
    #     through that occurrence's block_end_idx).
    # Walk line by line; emit either:
    #   - the merged block at the first occurrence
    #   - nothing for subsequent occurrences
    #   - the original line otherwise

    # Build a map: line_index → (action, key)
    #   action='merged' at first occurrence start; 'skip-start' at subsequent
    #   occurrence starts; 'skip-cont' for lines inside any occurrence's range.
    skip_ranges: list[tuple[int, int, str, bool]] = []
    # tuple: (start_idx, end_idx_inclusive, key, is_first)
    for key in duplicates:
        for j, occ_idx in enumerate(key_occurrence_idxs[key]):
            end_idx = key_block_end_idx[key][j]
            skip_ranges.append((occ_idx, end_idx, key, j == 0))

    # Sort by start_idx
    skip_ranges.sort(key=lambda x: x[0])

    # Reconstruction loop (cursor invariant): for each skip-range
    # [start..end] in document order, emit all lines BEFORE start that
    # haven't been emitted yet, then EITHER emit the merged block (at the
    # first occurrence of this key) OR skip silently (subsequent
    # occurrences). Cursor advances past `end` so the lines inside the
    # range are dropped from output. Final loop emits remaining tail.
    out_lines: list[str] = []
    cursor = 0
    for start, end, key, is_first in skip_ranges:
        # Emit any lines before this range that haven't been emitted
        while cursor < start:
            out_lines.append(lines[cursor])
            cursor += 1
        if is_first:
            # Emit the merged block-style entry for this key
            out_lines.append(f'{key}:')
            for item in merged_blocks[key]:
                out_lines.append(f'  - "{item}"')
        # Skip the range (cursor advances past it, no lines emitted)
        cursor = end + 1
    # Emit remaining lines
    while cursor < len(lines):
        out_lines.append(lines[cursor])
        cursor += 1

    merged_text = '\n'.join(out_lines)
    # Filter dropped_per_key to only return entries with count > 0
    dropped_per_key = {k: v for k, v in dropped_per_key.items() if v > 0}
    return merged_text, dropped_per_key, []


# Public API surface for importers
__all__ = [
    'detect_duplicate_yaml_keys',
    'merge_duplicate_yaml_keys',
    'extract_frontmatter',
]


# ---------------------------------------------------------------------------
# Self-test (run via `python3 _yaml_dup_lib.py`)
# ---------------------------------------------------------------------------
#
# Added v1.0.4 per Round-4-pre corruption finding 2026-05-15. Prior gauntlet
# missed the inline-comment-on-item case because smoke tests used items
# without inline `#` comments — the actual real-vault item shape uniformly
# carries inline comments. Fixtures here mirror observed real-vault patterns.

def _self_test() -> int:
    """Run inline regression tests. Returns 0 on pass, 1 on failure."""
    fails = 0

    # Test 1 — _strip_inline_comment edge cases
    for inp, expected in [
        ('  "f87e33f0"   # tropo-documentation', '"f87e33f0"'),
        ('  abc123 # short comment', 'abc123'),
        ('  "value#hash"', '"value#hash"'),
        ('  "f87e33f0"', '"f87e33f0"'),
        ('  unquoted-value', 'unquoted-value'),
        ('  uid#nohash', 'uid#nohash'),
    ]:
        got = _strip_inline_comment(inp)
        if got != expected:
            print(f'FAIL strip-inline-comment: input={inp!r} got={got!r} expected={expected!r}')
            fails += 1

    # Test 2 — round-trip equality on standard frontmatter
    test_rt = '---\nuid: abc12345\nfoo: bar\n---\nbody\n'
    parts = extract_frontmatter(test_rt)
    if parts is None:
        print('FAIL round-trip: extract_frontmatter returned None')
        fails += 1
    else:
        opening, body, after = parts
        if opening + body + after != test_rt:
            print('FAIL round-trip: extract+concat != original')
            fails += 1

    # Test 3 — end-to-end merge against the actual corruption pattern
    test_corrupt = (
        '---\nuid: 013ca8cb\ntype: document\nmember_of: [7d9ce3d7]\n'
        'member_of:\n  - "f87e33f0"   # tropo-documentation (v1.12 backfill)\n---\nbody\n'
    )
    expected_merged_body = (
        'uid: 013ca8cb\ntype: document\nmember_of:\n'
        '  - "7d9ce3d7"\n  - "f87e33f0"'
    )
    parts = extract_frontmatter(test_corrupt)
    if parts is not None:
        _o, body, _a = parts
        merged, dropped, errors = merge_duplicate_yaml_keys(body)
        if errors:
            print(f'FAIL e2e: unexpected errors {errors}')
            fails += 1
        elif merged != expected_merged_body:
            print(f'FAIL e2e: merged={merged!r} expected={expected_merged_body!r}')
            fails += 1
        # Idempotency
        remaining = detect_duplicate_yaml_keys(merged)
        if remaining:
            print(f'FAIL e2e idempotency: re-detect on merged returned {remaining}')
            fails += 1

    # Test 4 — scalar-conflict refusal
    test_scalar = '---\ntitle: First\ntitle: Second\n---\n'
    parts = extract_frontmatter(test_scalar)
    if parts is not None:
        _o, body, _a = parts
        merged, dropped, errors = merge_duplicate_yaml_keys(body)
        if not errors:
            print(f'FAIL scalar-conflict: expected errors, got none (merged={merged!r})')
            fails += 1

    # Test 5 — in-list-comment refusal
    test_inlist_comments = (
        '---\nfoo:\n  # commentary\n  - "a"\nfoo:\n  - "b"\n---\n'
    )
    parts = extract_frontmatter(test_inlist_comments)
    if parts is not None:
        _o, body, _a = parts
        merged, dropped, errors = merge_duplicate_yaml_keys(body)
        if not any('in-list-comments' in e for e in errors):
            print(f'FAIL in-list-comments: expected refusal, got errors={errors}')
            fails += 1

    if fails == 0:
        print('PASS — all self-tests clean (v1.0.4)')
    else:
        print(f'FAIL — {fails} self-test failure(s)')
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    import sys as _sys
    _sys.exit(_self_test())
