"""lib/po_first_boot.py — B-7 (f01564310146): the one shared fact both Po's
first-boot trigger (.tropo/concierge/activate.md, kernel surface) and her
walk (vault/playbooks/po-first-boot-orientation-f015f6f98b9b.md) read, so "does the automatic walk
fire" has exactly one answer instead of two copies of the same prose
drifting apart -- the studio's own costliest defect family, applied here
before it has a chance to recur.

The flag is per-install, machine scope in the studio-ops taxonomy
(0be90697) -- it sits beside the existing dated `.tropo/flags/*.flag`
markers and follows their own shape: presence is the whole signal, byte
content is never read.
"""
from __future__ import annotations

from pathlib import Path

FLAG_REL = Path(".tropo") / "flags" / "po-first-boot-orientation-offered.flag"


def should_fire_automatic_walk(vault_root: Path) -> bool:
    """True until the flag exists. Gates the AUTOMATIC first-boot fire
    ONLY -- callers driving an on-demand request ("give me the tour")
    must never consult this; the walk playbook runs in full regardless."""
    return not (Path(vault_root) / FLAG_REL).is_file()


def mark_walk_offered(vault_root: Path) -> Path:
    """Write the flag (idempotent, empty-file marker). Call this whether
    the walk completed or was skipped -- the flag records that the offer
    was made, not that it was accepted."""
    flag = Path(vault_root) / FLAG_REL
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.touch(exist_ok=True)
    return flag
