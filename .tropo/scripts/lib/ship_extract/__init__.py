"""ship_extract — Shared ship-artifact extraction engine for Tropo-OS.

Authored 2026-05-18 by argus-a72 per v1.43.0 Stream C (lib/ship_extract/ engine refactor).
Inherits from v1.42 brief Decision E sharpening (substrate UID fdda7ceb).

Five sub-modules under one engine:

- `manifest_walker` — reads capsule + walks ship-artifact graph + filters by target
- `source_mode_dispatch` — applies source mode behavior to entries (6 modes)
- `cleanup_engine` — applies cleanup_rules to file content (marker stripping, UID rewriting)
- `validator` — runs validation checks target-aware (v1.42 capsule v1.3 amendment)
- `output_writer` — writes extracted entries to output target

Consumed by:
- `.tropo/scripts/build-release.py` — release-target orchestration (target='release')
- `.tropo/scripts/build-web-content.py` — web-target orchestration (target='web'; v1.43 Stream D)
- Future-target orchestration scripts can be added per v1.42 capsule v1.3 target enum extensibility

Engine design principles:

1. **Pure functions where feasible** — each sub-module exposes pure-ish functions that take inputs
   and return outputs; side effects (filesystem writes) are isolated to output_writer.
2. **Target-aware throughout** — every function that varies by target accepts a `target` parameter
   (default 'release' for backward compat with pre-v1.43 build-release.py invocation).
3. **Byte-identical behavior preserved at extraction** — Stream C extracts existing logic;
   it does NOT change build-release.py's release-target output. Verification: byte-diff comparison
   against pre-Stream-C release builds.

Python: 3.10+ pinned per v1.42 brief Decision E lock (matches existing scripts).

Imports (recommended pattern):

    from lib.ship_extract.manifest_walker import read_manifest_root_uid, load_manifest_entries
    from lib.ship_extract.source_mode_dispatch import resolve_source_path, should_exclude_kernel
    from lib.ship_extract.cleanup_engine import apply_cleanup_rules, apply_uid_rewrite_template
    from lib.ship_extract.validator import validate_manifest_basic
    from lib.ship_extract.output_writer import sha256_file, copy_file
"""

__version__ = "1.0.0"
__cycle_landed__ = "v1.43.0"
__brief__ = "c47b9d82"
__cycle_root__ = "e8a3f491"

# Re-exports for convenience — callers can `from lib.ship_extract import X` for common operations
from .manifest_walker import read_manifest_root_uid, load_manifest_entries
from .source_mode_dispatch import resolve_source_path, should_exclude_kernel
from .cleanup_engine import apply_cleanup_rules, apply_uid_rewrite_template
from .validator import validate_manifest_basic
from .output_writer import sha256_file, copy_file

__all__ = [
    'read_manifest_root_uid',
    'load_manifest_entries',
    'resolve_source_path',
    'should_exclude_kernel',
    'apply_cleanup_rules',
    'apply_uid_rewrite_template',
    'validate_manifest_basic',
    'sha256_file',
    'copy_file',
]
