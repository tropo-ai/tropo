#!/usr/bin/env python3
"""The retired-render stripping primitives, in one neutral home.

WHY THIS FILE EXISTS. Two callers need to agree, byte for byte, about which
parts of a governed body are RENDERER-OWNED chrome and which are the owner's
words:

  * `tropo-generate-relations-header.py` strips them when it rewrites a body;
  * `lib/tropo_update_receipt.canonicalize_for_content_hash()` must ignore
    exactly the same spans when it computes the covenant content hash.

They disagreed. Since the 2026-07-23 File Anatomy v2 retool the renderer has
stripped un-sentineled Relations/Members tables, and the canonicalizer stripped
only the sentinel nav-block span. Measured in the live customer studio: 78
files carry legacy Relations renders, so a CLEAN update apply would have
produced 78 content_hash mismatches, quarantined the run, and read the customer
a covenant-violation banner for a defect that was entirely ours.

The fix is not a second regex in the receipt module. It is one definition with
two importers, so the two answers cannot drift again. The renderer re-exports
everything below for the nine existing call sites, which keep importing from
where they always did.

Extracted from `tropo-generate-relations-header.py` WITHOUT changing matching
behaviour — the code below is that file's code, moved. (Dev-spec task
d220d43b D1; Argus A145 concurrence, evt 9429.)
"""

from __future__ import annotations

import re
from typing import Optional, Tuple


_NAV_BLOCK_RE = re.compile(
    r"^<!-- nav-block:start -->\n.*?^<!-- nav-block:end -->\n*",
    re.DOTALL | re.MULTILINE,
)


def strip_nav_block(text: str) -> str:
    """Remove the sentinel-wrapped Navigation block region(s), if present.

    Byte-safe outside the sentinels; idempotent (a no-op on text with no block, and
    re-running on already-stripped text changes nothing). Line-anchored (see the
    self-heal note above `_NAV_BLOCK_RE`'s definition) — will not false-match a
    sentinel string quoted mid-line in prose. This is the CANONICAL single source of
    truth for the strip — the same `_NAV_BLOCK_RE` this renderer already uses to
    detect/replace its own block. Dev-spec 6ec30708 (Option A, I5 dd16c90c) reuses this
    exact function
    from two external callers so every stripper agrees byte-for-byte:
      - the git clean filter (vault/tools/tropo-navblock-strip.py `--clean`), which
        strips at the git boundary before content enters the object store;
      - the Option-B migration pass (deferred to Phase F), a direct body rewrite.
    Neither caller reinvents the regex — both import this function.
    """
    return _NAV_BLOCK_RE.sub("", text)


def find_navigation_block(body: str) -> Optional[Tuple[int, int]]:
    """Detect existing sentinel-wrapped Navigation block. Returns (start, end)
    or None. Sentinels make this trivially idempotent."""
    m = _NAV_BLOCK_RE.search(body)
    if m:
        return m.start(), m.end()
    return None


def find_relations_block(body: str) -> Optional[Tuple[int, int]]:
    """Detect a legacy Relations/Members navigation render. Returns (start, end) or None.

    RETIRED SURFACE (File Anatomy v2, 4506b6d4): these renders are no longer
    emitted; this finder remains so (a) this tool's sweep can strip them from
    bodies, and (b) tropo-rebuild-index.py can keep dropping them from
    mention-derivation in archived bodies that predate the sweep.

    Handles two legacy formats + the final table format:
    - Table: `**Relations**` heading + blank line + markdown table
    - Legacy 2: `> **Relations**` blockquote with row-per-item `> · Label: ...` lines
    - Legacy 1: `> **Relations**` blockquote with middle-dot inline separators
    - Standalone: `**Members**` table with no preceding Relations block

    After finding the Relations anchor, also consumes any trailing `**Members**`
    blocks (including stacked duplicates) so the whole unit resolves as one span
    (Argus A58 / v1.22.0.3 stacked-Members fix).
    """
    start = None
    end = None

    # Table format: **Relations** heading + table
    table_pattern = re.compile(
        r"^\*\*Relations\*\*[^\n]*\n+\| Relation \| Target \|\n\|[-:|\s]+\|\n(?:\|[^\n]*\|\n)+",
        re.MULTILINE,
    )
    m = table_pattern.search(body)
    if m:
        start, end = m.start(), m.end()
    else:
        # Legacy blockquote format
        bq_pattern = re.compile(r"^> \*\*Relations\*\*[^\n]*\n(?:^>[^\n]*\n)*", re.MULTILINE)
        m = bq_pattern.search(body)
        if m:
            start, end = m.start(), m.end()

    if start is None:
        # No Relations block — check for standalone Members block (files with
        # children but no outbound navigation fields)
        members_only = re.compile(
            r"^\*\*Members\*\*[^\n]*\n+\| Type \| Children \|\n\|[-:|\s]+\|\n(?:\|[^\n]*\|\n)*",
            re.MULTILINE,
        )
        m = members_only.search(body)
        if m:
            start, end = m.start(), m.end()
        else:
            return None

    # Consume any trailing Members blocks (handles normal append + stacked duplicates)
    members_pattern = re.compile(
        r"^\*\*Members\*\*[^\n]*\n+\| Type \| Children \|\n\|[-:|\s]+\|\n(?:\|[^\n]*\|\n)*",
        re.MULTILINE,
    )
    while True:
        remaining = body[end:]
        blank_match = re.match(r"^\n+", remaining)
        offset = blank_match.end() if blank_match else 0
        mm = members_pattern.match(remaining[offset:])
        if mm:
            end = end + offset + mm.end()
        else:
            break

    return start, end


_STALE_MEMBERS_RE = re.compile(
    r"\n*\*\*Members\*\*[^\n]*\n+\| Type \| Children \|\n\|[-:|\s]+\|\n(?:\|[^\n]*\|\n)*",
    re.MULTILINE,
)


def _strip_stale_members(text: str) -> str:
    """Remove any stray **Members** tables from a text segment."""
    return _STALE_MEMBERS_RE.sub("", text)


def strip_legacy_renders(body: str) -> str:
    """Strip every retired derived render from a body: sentinel nav-block(s),
    Relations/Members unit(s), stray Members tables. Idempotent; byte-safe
    outside the recognized spans. The File Anatomy v2 sweep primitive."""
    # Sentinel-wrapped nav-block(s) — global, line-anchored.
    body = strip_nav_block(body)
    # Relations/Members units — loop; a body may carry several from old runs.
    for _ in range(10):  # bounded loop, defensive against pathological bodies
        found = find_relations_block(body)
        if found is None:
            break
        start, end = found
        body = body[:start] + body[end:]
    # Stray Members tables not adjacent to a Relations block.
    body = _strip_stale_members(body)
    # Collapse blank-line runs left behind by removals.
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body

