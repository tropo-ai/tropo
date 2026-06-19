"""source_mode_dispatch — Applies source mode behavior to ship-artifact entries.

v1.43.0 Stream C extraction from build-release.py. Authored 2026-05-18 by argus-a72.

Per ship-artifact.capsule v1.3 (substrate UID eeb59ddf), six source modes govern
how entries get extracted to the build output:

- `recursive-ship-all` — copy the entire canonical_source directory recursively (folder entries)
- `recursive-ship-tagged` — copy directory recursively, but filter children by tag
- `explicit-children` — copy only entries explicitly declared as children of this folder
- `structure-only` — create the directory in build output but copy no files
- `skip` — entry exists for substrate-graph integrity but does NOT extract to build
- `direct-copy` — copy single file from canonical_source to output_path

This module exposes:

- `resolve_source_path(entry, vault_root)` — resolves the actual on-disk source path for an entry
- `should_exclude_kernel(filepath, exclude_patterns)` — filters kernel files against exclusion list

Higher-level dispatch logic (which mode triggers which copy pattern) lives in the
calling orchestration script (build-release.py / build-web-content.py) for now;
v1.44+ engineering cleanup may pull the full dispatch table here.
"""

import os
import re


def resolve_source_path(entry, vault_root):
    """Resolve the actual file path for a vault entry.

    v1.15.2 Stream C semantics: Studio-root fallback. After v1.15.1 Stream G indexed
    Studio-root files (STUDIO.md, TROPO-CAPABILITIES.md, etc.) without their frontmatter
    declaring a path: field, this resolver falls back to <vault_root>/<filename>.md when
    the canonical vault/files/<uid>.md doesn't exist. Closes the v1.15.1 build warning
    on TROPO-CAPABILITIES.md (7a1ca900). Composes with the v1.15.1 Stream G thesis
    (Studio-root files are first-class governed entries).

    Args:
        entry: Hydrated ship-artifact entry dict (must have 'uid'; may have 'path').
        vault_root: Absolute path to the Studio root.

    Returns:
        Absolute path to the on-disk source file. If no candidate resolves,
        returns the canonical vault/files/<uid>.md path so the calling code's
        missing-file branch fires.
    """
    if 'path' in entry:
        return os.path.join(vault_root, entry['path'])
    canonical = os.path.join(vault_root, 'vault', 'files', f"{entry['uid']}.md")
    if os.path.exists(canonical):
        return canonical
    # Fallback: scan Studio-root for *.md whose frontmatter uid matches.
    # Cheap because Studio-root has < 20 .md files; no caching needed at this scale.
    for fname in os.listdir(vault_root):
        if not fname.endswith('.md'):
            continue
        candidate = os.path.join(vault_root, fname)
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, 'r') as f:
                head = f.read(2048)
        except (OSError, UnicodeDecodeError):
            continue
        m = re.search(r"^uid:\s*([0-9a-f]{8})", head, re.MULTILINE)
        if m and m.group(1) == entry['uid']:
            return candidate
    # Fallback exhausted; return canonical path so the missing-file branch fires
    return canonical


def should_exclude_kernel(filepath, exclude_patterns):
    """Check if a kernel file should be excluded from the build.

    Args:
        filepath: Path to the candidate kernel file.
        exclude_patterns: List of basename substrings to exclude (e.g., ['register-kernel.py']).

    Returns:
        True if any exclude pattern matches the file basename.

    Note: build-release.py maintains the canonical KERNEL_EXCLUDE_PATTERNS list as a
    defensive belt-and-suspenders check during the v1.12.1 transition; v1.12.2+
    relies on manifest-driven `source_mode: skip` exclusions as the canonical mechanism.
    """
    basename = os.path.basename(filepath)
    for pattern in exclude_patterns:
        if pattern in basename:
            return True
    return False
