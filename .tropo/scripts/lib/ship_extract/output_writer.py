"""output_writer — Writes extracted ship-artifact entries to output target.

v1.43.0 Stream C extraction from build-release.py. Authored 2026-05-18 by argus-a72.

This module isolates the side-effectful disk-write operations used during build
extraction. All other ship_extract sub-modules are pure-or-mostly-pure; this one
owns the filesystem.

Exposes:

- `sha256_file(filepath)` — compute SHA-256 hash of a file (used for manifest integrity)
- `copy_file(src, dst, dry_run=False)` — copy a file with parent-directory creation
- `write_content(content, dst, dry_run=False)` — write transformed content (post cleanup_engine) to output

Target-specific output orchestration:

- Release target (build-release.py): writes to `<RELEASES_DIR>/v<X.Y.Z>/{builds,testing}/tropo-os-v<X.Y.Z>/`
- Web target (build-web-content.py; v1.43 Stream D): writes to `<website-content-repo>/working-copy/`

This module does NOT decide the destination — the caller passes the dst path. The orchestrator
script computes the appropriate destination per target convention.
"""

import hashlib
import os
import shutil


def sha256_file(filepath):
    """Compute SHA-256 hash of a file.

    Used for build manifest integrity verification + byte-identical-output checks
    during behavior-preservation testing.

    Args:
        filepath: Absolute path to the file.

    Returns:
        Hex string SHA-256 hash.
    """
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _assert_within_build_root(dst, build_root):
    """Path-traversal guard — assert dst is within build_root before write.

    P1-b absorption (sa.skeptic-108 R3 production-failure lens 2026-05-18):
    supply-chain hardening. Templates render `canonical_source` + `output_path` from
    substrate authored by Mike-approved agents → trust-boundary today, but as substrate
    expands (web-target, future targets) this is a hardening gap.

    Args:
        dst: Absolute destination path.
        build_root: Absolute build root (the directory all writes must stay within).

    Raises:
        ValueError: dst escapes build_root via `..` traversal or symlink shenanigans.
    """
    if build_root is None:
        # Backward-compat: callers pre-Stream-C-R3 don't pass build_root; opt-out.
        # New callers (build-release.py + build-web-content.py post-R3 absorption) pass it.
        return
    real_dst = os.path.realpath(dst)
    real_root = os.path.realpath(build_root)
    if os.path.commonpath([real_dst, real_root]) != real_root:
        raise ValueError(
            f'path-traversal guard: dst {dst!r} (real: {real_dst!r}) escapes '
            f'build_root {build_root!r} (real: {real_root!r}). '
            f'Check entry output_path for `..` traversal.'
        )


def copy_file(src, dst, dry_run=False, build_root=None):
    """Copy a file, creating parent directories as needed.

    Uses shutil.copy2 to preserve mtime + permissions (matters for some downstream
    audit checks).

    Args:
        src: Absolute source path.
        dst: Absolute destination path.
        dry_run: If True, no actual copy occurs (used by --dry-run flag).
        build_root: Optional absolute path; if provided, asserts dst is within it
                    (P1-b path-traversal guard from sa.skeptic-108 R3 absorption).
    """
    if dry_run:
        return
    _assert_within_build_root(dst, build_root)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def write_content(content, dst, dry_run=False, build_root=None):
    """Write transformed content to output path.

    Used for entries that go through cleanup_engine (content is transformed before write,
    so we can't use shutil.copy2). Creates parent directories as needed.

    Args:
        content: Transformed file content (string).
        dst: Absolute destination path.
        dry_run: If True, no actual write occurs.
        build_root: Optional absolute path; if provided, asserts dst is within it
                    (P1-b path-traversal guard from sa.skeptic-108 R3 absorption).
    """
    if dry_run:
        return
    _assert_within_build_root(dst, build_root)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(content)
