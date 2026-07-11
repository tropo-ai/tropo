"""The covenant receipt — dual-hash + disclosure (Gate 2, dev-spec fc4874f4,
LOCK-AMENDMENT 3, 2026-07-02, Mike verbatim "i think i am okay with the nav
block. as soon as we start importing work into the studio, it becomes
'governed'"). Findings record: 5d4bbbf2.

THE RULING THIS CODE ENCODES: the covenant protects user CONTENT, not byte-
identity. The studio's own governance chrome (the nav-block renderer,
`tropo-generate-relations-header.py`) legitimately writes into governed user
file bodies — that write is not a covenant violation. What WAS a violation
(the Po-walk F6 finding) is a receipt that claimed zero churn by BYTE hash
while chrome writes had already landed on disk, undetected. This module
makes the receipt honest instead of forbidding the chrome:

  1. RECEIPT-LAST (`ReceiptSeal`) — a structural guard, not a playbook
     instruction. Every write the apply engine performs (discrete ops,
     migrations, AND post-apply housekeeping/index-rebuild) must be recorded
     via `ReceiptSeal.record_write()` before the receipt is computed.
     Calling `.seal()` freezes the guard; any further `record_write()` call
     raises `PostReceiptWriteError` instead of silently succeeding. This is
     the fix for F6: if housekeeping is ever re-sequenced to run AFTER the
     receipt again (the exact regression this exists to prevent), the guard
     — not a human re-reading the playbook — catches it, at the moment the
     illegal write is attempted, not at the next walk.

  2. DUAL-HASH RECEIPT (`content_hash`, `build_receipt_markdown`) — per user
     file, the receipt reports (a) a CONTENT hash with nav-block spans
     canonicalized out (`content_hash` strips exactly the sentinel span
     `tropo-generate-relations-header.py` inserts — this is the actual
     covenant proof, "your words didn't change") and (b) an honest
     DISCLOSURE list of exactly which files the nav renderer chromed this
     run, each with its real post-apply BYTE hash (fully auditable, never
     hidden). A clean run reads "your content: 5/5 unchanged; navigation
     added to 4 files" — honest and green, never a false zero-churn claim.

Both the apply engine (conceptually — see vault/playbooks/71f186cf.md "The
Covenant Receipt") and THE FLOOR TEST
(vault/tools/tests/test_clean_update_floor.py) use this module — same
discipline as the namespace predicate (tropo_update_namespace.py): one
implementation, so "what the playbook says" and "what actually gets tested"
cannot drift apart.
"""

import hashlib
import re

# Must mirror the sentinel pair `tropo-generate-relations-header.py`'s
# `_NAV_BLOCK_RE` inserts/detects (`build_navigation_block` / `find_navigation_block`).
# Duplicated here (rather than importing the hyphenated tool module) because this
# is a stable markup contract, not shared logic — `check_nav_sentinel_matches_generator()`
# in the floor test cross-checks the two stay in sync against the real generator file,
# so drift is machine-caught rather than assumed away.
NAV_BLOCK_START = "<!-- nav-block:start -->"
NAV_BLOCK_END = "<!-- nav-block:end -->"
_NAV_BLOCK_RE = re.compile(
    re.escape(NAV_BLOCK_START) + r".*?" + re.escape(NAV_BLOCK_END) + r"\n*",
    re.DOTALL,
)


class PostReceiptWriteError(RuntimeError):
    """Raised by ReceiptSeal.record_write() once the guard has been sealed.

    This is the structural half of RECEIPT-LAST: the receipt is supposed to be
    the terminal act of an apply run. If anything — housekeeping, a stray
    rebuild, a forgotten cleanup step — tries to write after the receipt was
    computed and sealed, this exception fires instead of the write silently
    landing behind the receipt's back (the exact F6 defect class)."""


def canonicalize_for_content_hash(text):
    """Strip nav-block spans so the CONTENT hash reflects the owner's words,
    not the studio's navigation chrome. This is the covenant proof half of
    the dual-hash receipt — it must return the same string whether or not
    the nav renderer has run against this file, PROVIDED the renderer only
    ever touches its own sentinel-wrapped span (true for
    `tropo-generate-relations-header.py`'s insert_or_update_block, which is
    idempotent-by-sentinel by design)."""
    return _NAV_BLOCK_RE.sub("", text)


def content_hash(text):
    """SHA-256 of the chrome-canonicalized text — the per-file covenant proof."""
    return hashlib.sha256(canonicalize_for_content_hash(text).encode("utf-8")).hexdigest()


def byte_hash(data):
    """SHA-256 of raw bytes (or a str encoded utf-8) — the honest disclosure hash.
    Unlike content_hash, this is NOT canonicalized: it is what actually sits on
    disk, so an owner can audit a disclosed file's exact byte-for-byte state."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def combined_manifest_hash(path_hash_pairs):
    """The single combined fingerprint over a sorted {path: hash} sequence —
    same construction the v2.0 receipt used for the single (byte-hash) manifest,
    now reused for the CONTENT-hash manifest. `path_hash_pairs` is an iterable
    of (path, hash) tuples; sorted internally by path for determinism."""
    concat = "\n".join(f"{p}:{h}" for p, h in sorted(path_hash_pairs))
    return hashlib.sha256(concat.encode("utf-8")).hexdigest()


class ReceiptSeal:
    """The RECEIPT-LAST structural guard.

    Every write the apply engine performs — discrete operations, migrations,
    AND post-apply housekeeping/index-rebuild — must call `record_write()`.
    Once `seal()` is called (immediately before/while writing the receipt
    file itself), any further `record_write()` raises `PostReceiptWriteError`.

    This is intentionally a dumb, small object: it does not know what a
    "write" means beyond a caller telling it one happened. The apply engine
    is responsible for calling `record_write()` at every write site — the
    guard's job is only to make it impossible for a write to happen silently
    once the receipt is sealed, not to discover writes on its own."""

    def __init__(self):
        self._sealed = False
        self._writes = []
        self._seal_receipt_path = None

    @property
    def is_sealed(self):
        return self._sealed

    @property
    def writes(self):
        return list(self._writes)

    def record_write(self, rel_path):
        if self._sealed:
            raise PostReceiptWriteError(
                f"write to {rel_path!r} attempted AFTER the covenant receipt was "
                f"sealed (receipt: {self._seal_receipt_path!r}). The receipt must "
                f"be the structurally-terminal act of an apply run — housekeeping/"
                f"index-rebuild must run BEFORE receipt computation, not after "
                f"(LOCK-AMENDMENT 3, finding 5d4bbbf2 F6)."
            )
        self._writes.append(rel_path)

    def seal(self, receipt_path):
        if self._sealed:
            raise PostReceiptWriteError(f"ReceiptSeal already sealed at {self._seal_receipt_path!r}")
        self._sealed = True
        self._seal_receipt_path = receipt_path


def build_receipt_markdown(
    update_id,
    target_version,
    result,
    content_hash_entries,
    nav_disclosure,
    tropo_components_replaced,
    generated_at,
):
    """Render the v3.0 (LOCK-AMENDMENT 3) covenant receipt.

    content_hash_entries: list of {"path", "pre_hash", "post_hash"} for every
      category-(c) user/studio file present before the apply. `pre_hash`/
      `post_hash` are content_hash() values (nav-canonicalized) — these should
      be EQUAL for every entry on a clean apply, even for files the nav
      renderer chromed (their byte hash changed; their content hash did not).

    nav_disclosure: list of {"path", "byte_hash"} — every file the nav
      renderer actually wrote to this run, with its real post-apply byte hash.
      This is the honest disclosure; it is not folded into the content-hash
      proof, and it is never hidden.

    tropo_components_replaced: list of rel paths (OS substrate REPLACE ops),
      carried forward from the v2.0 receipt shape.
    """
    unchanged = [e for e in content_hash_entries if e["pre_hash"] == e["post_hash"]]
    mismatched = [e for e in content_hash_entries if e["pre_hash"] != e["post_hash"]]
    total = len(content_hash_entries)

    pre_combined = combined_manifest_hash((e["path"], e["pre_hash"]) for e in content_hash_entries)
    post_combined = combined_manifest_hash((e["path"], e["post_hash"]) for e in content_hash_entries)

    lines = ["---"]
    lines.append(f'update_id: "{update_id}"')
    lines.append(f'target_version: "{target_version}"')
    lines.append(f'result: "{result}"')
    lines.append(f"content_unchanged_count: {len(unchanged)}")
    lines.append(f"content_total_count: {total}")
    lines.append(f'pre_apply_content_hash_manifest: "{pre_combined}"')
    lines.append(f'post_apply_content_hash_manifest: "{post_combined}"')
    lines.append("content_hash_mismatches:")
    if mismatched:
        for e in mismatched:
            lines.append(f'  - path: "{e["path"]}"')
            lines.append(f'    pre_content_hash: "{e["pre_hash"]}"')
            lines.append(f'    post_content_hash: "{e["post_hash"]}"')
    else:
        lines.append("  []")
    lines.append("nav_chrome_disclosure:")
    if nav_disclosure:
        for d in sorted(nav_disclosure, key=lambda x: x["path"]):
            lines.append(f'  - path: "{d["path"]}"')
            lines.append(f'    byte_hash: "{d["byte_hash"]}"')
    else:
        lines.append("  []")
    lines.append("tropo_components_replaced:")
    if tropo_components_replaced:
        for p in tropo_components_replaced:
            lines.append(f'  - "{p}"')
    else:
        lines.append("  []")
    lines.append(f'generated_at: "{generated_at}"')
    lines.append("---")
    lines.append("")
    lines.append(f"# Covenant Receipt — {update_id}")
    lines.append("")

    if mismatched:
        lines.append(
            f"**COVENANT VIOLATION** — {len(mismatched)} of {total} user file(s) had their "
            f"CONTENT change (nav-chrome-canonicalized), not just their navigation chrome: "
            f"{', '.join(e['path'] for e in mismatched)}. This should never happen; treat this "
            f"apply as failed regardless of what verification reported."
        )
    else:
        nav_count = len(nav_disclosure)
        lines.append(
            f"Your content: {len(unchanged)}/{total} unchanged. "
            + (f"Navigation added to {nav_count} file(s) this run (disclosed below with byte-hashes) "
               f"— your studio's chrome, not your words." if nav_count
               else "No navigation chrome was written to any of your files this run.")
        )
        lines.append("")
        lines.append(
            f"Combined content fingerprint before and after this update: `{pre_combined}` "
            f"(computed across all {total} user/studio file(s), nav-block spans excluded) — "
            f"identical before and after. Nothing you wrote was touched."
        )
        if nav_disclosure:
            lines.append("")
            lines.append("Files the studio's navigation renderer wrote to this run (full disclosure, byte-hash after):")
            for d in sorted(nav_disclosure, key=lambda x: x["path"]):
                lines.append(f"- `{d['path']}` — `{d['byte_hash']}`")

    return "\n".join(lines) + "\n"
