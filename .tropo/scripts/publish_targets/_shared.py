"""
publish_targets/_shared.py — Shared helpers for publish.pipeline target modules.

Extracted from web.py dated-source packaging primitive (Talos T10, 2026-05-24)
so both web and docx targets can reuse versioning logic without duplication.
"""

from __future__ import annotations

import glob as _glob
import os
import shutil


def ensure_dated_slot(folder: str, slug: str, timestamp: str, ext: str) -> str:
    """Create outbox slot for a dated artifact, archiving any prior same-run files.

    Creates <folder>/versions/ if needed. Moves any existing <slug>-*.<ext> files
    to <folder>/versions/ (prior publish runs). Returns the path for the new file:
    <folder>/<slug>-<timestamp>.<ext>.

    Used by both web target (dated .md source) and docx target (dated .docx output)
    to maintain a clean outbox with one current file + versioned archive.
    """
    if not os.path.isdir(folder):
        return os.path.join(folder, f'{slug}-{timestamp}.{ext}')

    versions_dir = os.path.join(folder, 'versions')
    os.makedirs(versions_dir, exist_ok=True)

    new_name = f'{slug}-{timestamp}.{ext}'
    for prior in _glob.glob(os.path.join(folder, f'{slug}-*.{ext}')):
        if os.path.isfile(prior) and os.path.basename(prior) != new_name:
            shutil.move(prior, os.path.join(versions_dir, os.path.basename(prior)))

    return os.path.join(folder, new_name)
