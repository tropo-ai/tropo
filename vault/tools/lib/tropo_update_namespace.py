"""The namespace predicate — the load-bearing rule of Gate 2 (dev-spec fc4874f4).

Replaces the old path-by-path SHA-drift heuristic in the apply-update playbook
(vault/playbooks/71f186cf.md v1.1 Step 3c) with a deterministic rule keyed on
filename namespace + the studio's own shipped manifest (ADR-045 ca6e5824;
LOCK-AMENDMENT 2, finding 4496553c). This module is the single source of truth
both the apply engine and the clean-update floor test import — duplicating the
rule in two places is exactly the kind of drift One Home exists to prevent.

Four categories:

  (a) vault/tropo-*        — OS component, shipped standard library  -> REPLACE
  (b) .tropo/ bootstrap floor (boot config, OS P0 primitives, schema,
      generated catalogs, concierge, orientation)                    -> REPLACE
  (c) vault/<slug>-<uid>.md or bare <uid>.md (user/studio content)    -> PRESERVE
      (default for anything not positively identified as OS substrate)
  (d) MANIFEST-LISTED (LOCK-AMENDMENT 2, 2026-07-02) — any path listed in the
      studio's own shipped MANIFEST.md is OS substrate. Content-blind and
      deterministic exactly like (a)/(b): the manifest already ships in every
      box with a per-file SHA-256, constructed at build time. Listed AND the
      on-disk hash matches the manifest -> REPLACE. Listed but the on-disk
      hash does NOT match -> USER_MODIFIED_SHIPPED: the file is OS substrate
      the owner has locally edited; NEVER silently overwritten — surfaced as
      an explicit overwrite-confirm line in the dry-run diff instead.

Category (d) exists because (a)/(b)/(c) alone cannot classify the update
mechanism's own files: canonical UID-named playbooks/tools (e.g.
vault/playbooks/71f186cf.md), .tropo-studio/ registries, and root docs (where
the ADR-049 covenant text lands) are neither `tropo-*`-named nor under
`.tropo/` — under the three-category rule alone they default to PRESERVE,
which means an update could never deliver its own machinery to an existing
studio. Found 2026-07-02 by running the real v1.77->v1.78 machinery delta
through the real predicate while staging the Po walk (board item 4496553c) —
the floor test's idealized fixture (tropo-*-only seed) could not see this
gap; the fixture was hardened to seed the real shipped layout in response.

(c) remains the safe default: a path earns REPLACE by matching (a), (b), or
being positively listed in the manifest for (d). Nothing is preserved-by-guess
and nothing is replaced-by-guess.
"""

import re

_UID_RE = re.compile(r'^[0-9a-f]{8}(-[0-9a-f]{8})?$')  # bare <uid>.md, defensive on doubled uid
_SLUG_UID_RE = re.compile(r'^[a-z0-9-]+-[0-9a-f]{8}$')  # <slug>-<uid>.md

# Matches a MANIFEST.md table row: | path | size | `hexhash` | or `hexhash...` |
# The REAL shipped format (confirmed against tropo-releases/v1.77.0/builds/tropo-os-v1.77.0/MANIFEST.md,
# 957 rows) truncates to 12 hex chars with a literal trailing ellipsis inside the backticks —
# e.g. `93a3feeab56b...` — NOT a bare full-length hex string. tropo-build-release.py's
# step_9_generate_manifest was fixed at Gate 2 to emit the full 64-hex hash going forward, but
# every box already shipped (v1.77.0 and earlier) carries the truncated form forever — the parser
# MUST accept both permanently, not just "until the fix rolls out" (finding from Argus A123's
# re-verify against a real v1.77.0 extract, LOCK-AMENDMENT 2 F1). Defensive: the manifest is a
# generated markdown table (957 rows in v1.77) — a malformed row is logged-and-skipped, never a
# parse crash. Escaped-pipe paths (`\|`) are unescaped defensively; none occur in the real v1.77
# manifest today but a path could legitimately contain one.
_MANIFEST_ROW_RE = re.compile(
    r'^\|\s*(?P<path>[^|]+?)\s*\|\s*(?P<size>[0-9,]+)\s*\|\s*'
    r'`(?P<hash>[0-9a-f]{6,64})(?P<ellipsis>\.\.\.)?`\s*\|\s*$'
)

REPLACE = 'replace'
PRESERVE = 'preserve'
USER_MODIFIED_SHIPPED = 'user_modified_shipped'


def _basename_no_ext(path):
    name = path.rsplit('/', 1)[-1]
    if '.' in name:
        name = name.rsplit('.', 1)[0]
    return name


def parse_manifest_md(text):
    """Parse a MANIFEST.md's `| Path | Size | SHA-256 |` table into
    {rel_path: sha256_hex_or_truncated_prefix}. Skips the header/divider rows
    and any row that doesn't match the expected shape — a malformed row is
    never fatal, per the same log-and-skip discipline the migration playbooks
    use. Accepts BOTH the full 64-hex format (Gate-2-and-later builds) and the
    truncated `<12hex>...` format every pre-Gate-2 box ships forever (see
    _MANIFEST_ROW_RE docstring) — the returned hash string is whatever length
    the manifest actually carries; classify()'s hash comparison handles both.

    Returns (index, skipped_row_count) — skipped_row_count is unmatched/
    malformed rows only, NOT a count of truncated-but-valid rows."""
    index = {}
    skipped = 0
    for line in text.splitlines():
        stripped = line.strip()
        if re.fullmatch(r'\|[-:\s|]+\|', stripped):
            continue  # markdown table divider row (|------|-----:|--------|) — not a defect
        m = _MANIFEST_ROW_RE.match(line)
        if not m:
            if stripped.startswith('|') and '|' in stripped[1:]:
                skipped += 1  # looked like a table row but didn't parse — log-and-skip
            continue
        path = m.group('path').strip().replace('\\|', '|')  # defensive: unescape literal pipes
        if path in ('Path',):  # header row guard, defensive
            continue
        index[path] = m.group('hash').strip()  # length as-shipped: 12 (truncated) or 64 (full)
    return index, skipped


def is_os_component(rel_path):
    """Structural-only check: True if `rel_path` is a REPLACE-class OS
    component under categories (a) or (b) alone (no manifest consulted).
    Use `classify()` for the full four-category predicate, which is what the
    real apply engine and the floor test use — this function stays narrow
    for callers that only need the filename-namespace half of the rule
    (e.g. authoring-time sanity checks that don't have a manifest handy)."""
    rel_path = rel_path.lstrip('/')

    if rel_path.startswith('vault/'):
        basename = rel_path.rsplit('/', 1)[-1]
        return basename.startswith('tropo-')

    if rel_path.startswith('.tropo/'):
        return True

    return False


def _hashes_match(manifest_hash, current_hash):
    """Full-vs-full: exact match. Either side shorter than 64 hex (the legacy
    truncated format every pre-Gate-2 box ships forever — see
    _MANIFEST_ROW_RE): prefix-match on the shorter length. This is F2 from
    Argus A123's re-verify against a real v1.77.0 extract — a v1.77 box's
    MANIFEST.md will NEVER carry full hashes; treating a 12-hex truncated
    entry as "can't verify, fall through to something else" would silently
    disable category (d) on every box shipped before the Gate-2 fix landed."""
    shorter = min(len(manifest_hash), len(current_hash))
    return manifest_hash[:shorter] == current_hash[:shorter]


def classify(rel_path, manifest_index=None, current_hash=None):
    """The full four-category predicate. Returns REPLACE, PRESERVE, or
    USER_MODIFIED_SHIPPED.

    manifest_index: optional {rel_path: sha256_hex_or_truncated_prefix} dict,
      typically from parse_manifest_md() against the studio's own shipped
      MANIFEST.md. Required to activate category (d); without it, only
      (a)/(b)/(c) apply and manifest-listed-but-not-namespace-matching paths
      fall through to PRESERVE (the pre-LOCK-AMENDMENT-2 behavior).
    current_hash: optional; the actual on-disk sha256 of rel_path right now
      (full 64-hex — compute with hashlib, never pre-truncate the argument).
      Only consulted for category (d) mismatch detection. If omitted, a
      manifest-listed path is trusted as REPLACE (caller is asserting no
      drift check is needed — e.g. a fresh install with nothing to compare).
    """
    rel_path = rel_path.lstrip('/')

    if is_os_component(rel_path):  # categories (a)/(b)
        return REPLACE

    if manifest_index is not None and rel_path in manifest_index:  # category (d)
        manifest_hash = manifest_index[rel_path]
        if current_hash is None or _hashes_match(manifest_hash, current_hash):
            return REPLACE
        return USER_MODIFIED_SHIPPED

    return PRESERVE  # category (c) / unlisted — the safe default
