"""Round-trip receipt for the import/export boundary (v1.81, dev-spec 92093c81).

Ports the four-layer Update Covenant honesty model from the update path to the
import/export boundary. Owner-checkable WITHOUT trusting Tropo:

  1. REPRODUCES — pre/post content hashes recompute from ground-truth artifacts
  2. CONTENT vs CHROME — user-authored bytes separated from Tropo frontmatter,
     nav-block spans, and tropo:block provenance anchors
  3. EVERY DROP DISCLOSED — extraction_stats drops listed explicitly
  4. RECEIPT-LAST — ReceiptSeal guard (same structural discipline as update covenant)

Shared by tropo-export.py and vault/tools/tests/test_work_crosses_boundary_v181.py.
"""

import hashlib
import re

from lib.tropo_update_receipt import (
    NAV_BLOCK_END,
    NAV_BLOCK_START,
    ReceiptSeal,
    PostReceiptWriteError,
    byte_hash,
    combined_manifest_hash,
)

__all__ = [
    'extraction_stats_break_conservation',
    'PostReceiptWriteError',
    'ReceiptSeal',
    'ANCHOR_RE',
    'strip_user_content',
    'user_content_hash',
    'collect_drops_from_stats',
    'verify_round_trip_receipt',
    'build_round_trip_receipt_markdown',
]

ANCHOR_RE = re.compile(r'<!--\s*tropo:block\s+idx=\d+\s+hash=[0-9a-f]{8}\s*-->\n?')
_FRONTMATTER_RE = re.compile(r'^---\s*\n.*?\n---\s*\n', re.DOTALL)
_NAV_BLOCK_RE = re.compile(
    re.escape(NAV_BLOCK_START) + r".*?" + re.escape(NAV_BLOCK_END) + r"\n*",
    re.DOTALL,
)


def strip_user_content(text):
    """Remove Tropo chrome — frontmatter, nav-block, provenance anchors."""
    text = _FRONTMATTER_RE.sub('', text, count=1)
    text = _NAV_BLOCK_RE.sub('', text)
    text = ANCHOR_RE.sub('', text)
    return text


def user_content_hash(text):
    """SHA-256 of user-authored content (chrome stripped)."""
    return hashlib.sha256(strip_user_content(text).encode('utf-8')).hexdigest()


def collect_drops_from_stats(extraction_stats):
    """Return a list of disclosed drop descriptions from extraction_stats."""
    if not extraction_stats:
        return []
    drops = []
    drop_keys = (
        'inline_drawings_dropped', 'equations_dropped', 'custom_styles_dropped',
        'unsupported_elements_dropped', 'tables_dropped', 'footnotes_dropped',
    )
    for key in drop_keys:
        val = extraction_stats.get(key)
        if val:
            drops.append(f'{key}: {val}')
    for key, val in sorted(extraction_stats.items()):
        if (key.endswith('_dropped') or key.startswith('dropped_')) and key not in drop_keys and val:
            drops.append(f'{key}: {val}')
    return drops


def build_round_trip_receipt_markdown(
    *,
    run_uid,
    projection_uid,
    working_copy_uid,
    source_path,
    export_path,
    source_pre_hash,
    export_post_hash,
    source_byte_hash,
    export_byte_hash,
    extraction_stats,
    chrome_disclosure,
    generated_at,
    result='pass',
):
    """Render a locally-auditable round-trip receipt."""
    drops = collect_drops_from_stats(extraction_stats or {})
    lines = ['---']
    lines.append(f'run_uid: "{run_uid}"')
    lines.append(f'projection_uid: "{projection_uid}"')
    lines.append(f'working_copy_uid: "{working_copy_uid}"')
    lines.append(f'source_path: "{source_path}"')
    lines.append(f'export_path: "{export_path}"')
    lines.append(f'result: "{result}"')
    lines.append(f'source_user_content_hash: "{source_pre_hash}"')
    lines.append(f'export_user_content_hash: "{export_post_hash}"')
    lines.append(f'source_byte_hash: "{source_byte_hash}"')
    lines.append(f'export_byte_hash: "{export_byte_hash}"')
    lines.append('drops_disclosed:')
    if drops:
        for d in drops:
            lines.append(f'  - "{d}"')
    else:
        lines.append('  []')
    lines.append('chrome_disclosure:')
    if chrome_disclosure:
        for item in sorted(chrome_disclosure, key=lambda x: x['path']):
            lines.append(f'  - path: "{item["path"]}"')
            lines.append(f'    byte_hash: "{item["byte_hash"]}"')
    else:
        lines.append('  []')
    lines.append(f'generated_at: "{generated_at}"')
    lines.append('---')
    lines.append('')
    lines.append(f'# Round-Trip Receipt — {run_uid}')
    lines.append('')
    content_match = source_pre_hash == export_post_hash
    if content_match:
        lines.append(
            f'User content unchanged (nav/anchor/frontmatter stripped): '
            f'`{source_pre_hash}` — byte hashes disclosed separately below.'
        )
    else:
        lines.append(
            f'**CONTENT DRIFT** — user-content hash before `{source_pre_hash}` != '
            f'after `{export_post_hash}`. Inspect disclosed drops and chrome entries.'
        )
    if drops:
        lines.append('')
        lines.append('Extraction drops disclosed this round-trip:')
        for d in drops:
            lines.append(f'- {d}')
    if chrome_disclosure:
        lines.append('')
        lines.append('Tropo chrome written (byte-hash after):')
        for item in sorted(chrome_disclosure, key=lambda x: x['path']):
            lines.append(f"- `{item['path']}` — `{item['byte_hash']}`")
    manifest = combined_manifest_hash([
        ('source_user_content', source_pre_hash),
        ('export_user_content', export_post_hash),
    ])
    lines.append('')
    lines.append(f'Combined user-content manifest: `{manifest}`')
    return '\n'.join(lines) + '\n'




def extraction_stats_break_conservation(extraction_stats):
    """True when extractor reported undisclosed body text (v1.81 B5 backstop)."""
    if not extraction_stats:
        return False
    return bool(extraction_stats.get('text_conservation_unaccounted_chars'))

def verify_round_trip_receipt(receipt_text, *, source_text, export_text, extraction_stats=None):
    """Machine-verify the four concrete receipt properties. Returns (ok, reasons)."""
    reasons = []
    pre = user_content_hash(source_text)
    post = user_content_hash(export_text)
    if pre != post:
        reasons.append(f'user_content_hash mismatch: {pre} != {post}')

    drops = collect_drops_from_stats(extraction_stats or {})
    for key in (extraction_stats or {}):
        if key.endswith('_dropped') and extraction_stats[key]:
            matched = any(key in d for d in drops)
            if not matched:
                reasons.append(f'undisclosed drop: {key}')

    unaccounted = (extraction_stats or {}).get('text_conservation_unaccounted_chars') or 0
    if unaccounted:
        reasons.append(f'text_conservation_unaccounted_chars: {unaccounted}')

    if 'source_user_content_hash:' not in receipt_text:
        reasons.append('receipt missing source_user_content_hash')
    if 'export_user_content_hash:' not in receipt_text:
        reasons.append('receipt missing export_user_content_hash')
    if pre not in receipt_text or post not in receipt_text:
        reasons.append('receipt hashes not reproducible from artifacts')

    return (len(reasons) == 0, reasons)
