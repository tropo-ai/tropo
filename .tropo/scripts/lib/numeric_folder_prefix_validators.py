"""numeric-folder-prefix.capsule v1.0 validator extensions for tropo-validate.py.

Authored by Argus A81 2026-05-24 captain-mode under v1.52 cycle P-lane P3 per:
- numeric-folder-prefix.capsule v1.0 §6 Validation Checks (UID 61f650aa)
- Path 2 finding 7e4c2b81 (Metis G58 + Mike-G58 walk 2026-05-23 source doctrine)
- Mike-A81 strong-lean calibration (stm-a81-003) 2026-05-24

WHAT THIS DOES:

Four validator extensions ship at WARN severity at v1.0; ERROR ratchet at v1.1 per
ratchet_schedule (after evidence of clean operational use across >= 2 cycles + >=
1 fresh Studio install).

1. check_numeric_folder_prefix_reserved_range
   Scans every numeric-prefixed folder under <studio-root>/ matching pattern ^\\d{2}-.
   If prefix is in [00-09], folder name must match a row in capsule §3 (active
   tropo-system reservations). Studio-claimed 00-09 folders not in §3 are violations.

2. check_studio_specific_folder_has_agents_md
   Scans every numeric-prefixed folder under <studio-root>/ matching pattern ^[1-9]\\d-
   (i.e., 10+). Asserts AGENTS.md exists at folder root (governance contract requirement).

3. check_99_terminal_convention
   Scans every folder matching pattern ^99-. Asserts folder name matches a capsule §4
   row (99-archive folder-local OR 99-recycle studio-root).

4. check_no_vault_subfolders_numeric_prefix
   Scans every subfolder under vault/ (excluding vault/files/). Asserts no
   numeric-prefixed folders. Flat-vault discipline binding per Mike pin.

Lib module matches the existing lib/dev_spec_validators.py + lib/v14_subsystem_hub_validators.py
DRY pattern. Rule logic in lib/; tropo-validate.py imports + invokes.
"""

from __future__ import annotations
import re
from pathlib import Path

# Active reservations from capsule §3 — must stay in sync with capsule v1.0.
RESERVED_00_09 = {
    "00-": "index/navigation (any scope)",
    "00-tropo-nav": "navigation render tree (canonical)",
    "01-inbox": "lifecycle: incoming work (per-project)",
    "02-outbox": "lifecycle: outgoing publications (studio-root)",
    "03-design": "design substrate (multi-scope)",
}

# Reserved-future range 04-09 — Studios cannot claim.
RESERVED_FUTURE_04_09 = {f"0{n}-" for n in range(4, 10)}

# Active 99- conventions from capsule §4.
ACTIVE_99_PATTERNS = {
    "99-archive": "folder-local archive (any scope)",
    "99-recycle": "studio-root soft-delete bin (one per Studio)",
}

_NUMERIC_PREFIX = re.compile(r"^(\d{2})-(.*)$")
_TEN_PLUS_PREFIX = re.compile(r"^[1-9]\d-")


def _list_subdirs(parent: Path) -> list[Path]:
    """Return immediate subdirectories of parent (no recursion)."""
    if not parent.exists() or not parent.is_dir():
        return []
    return [p for p in parent.iterdir() if p.is_dir()]


def check_numeric_folder_prefix_reserved_range(studio_root: Path) -> list[str]:
    """Check 1: studio-claimed 00-09 folders must match capsule §3 reservations."""
    findings = []
    for sub in _list_subdirs(studio_root):
        name = sub.name
        m = _NUMERIC_PREFIX.match(name)
        if not m:
            continue
        prefix_2 = m.group(1)
        if prefix_2 not in {f"{n:02d}" for n in range(0, 10)}:
            continue  # 10+ handled by Check 2
        # 00-09 range — must match a known reservation
        # Check exact match in RESERVED_00_09 first, then prefix-only match for 00- pattern
        matched = False
        for reserved_name in RESERVED_00_09:
            if name == reserved_name:
                matched = True
                break
            # Handle 00-* generic family (00-index, 00-project-tree, 00-tropo-nav, etc.)
            if reserved_name == "00-" and name.startswith("00-"):
                matched = True
                break
        if not matched:
            # Check if it's in the reserved-future range
            if f"{prefix_2}-" in RESERVED_FUTURE_04_09:
                findings.append(
                    f"{sub} — folder name claims tropo-system reserved-future prefix '{prefix_2}-' "
                    f"(range 04-09 reserved for future tropo-system conventions; studios cannot claim). "
                    f"Mike-walked amendment to numeric-folder-prefix.capsule v1.0 §3 required."
                )
            else:
                findings.append(
                    f"{sub} — folder name uses tropo-system reserved prefix '{prefix_2}-' "
                    f"but '{name}' not in capsule §3 active reservations. "
                    f"Either match a reservation OR re-prefix to 10+ studio-specific range."
                )
    return findings


def check_studio_specific_folder_has_agents_md(studio_root: Path) -> list[str]:
    """Check 2: 10+ studio-specific folders must have AGENTS.md governance contract."""
    findings = []
    for sub in _list_subdirs(studio_root):
        if not _TEN_PLUS_PREFIX.match(sub.name):
            continue
        agents_md = sub / "AGENTS.md"
        if not agents_md.exists():
            findings.append(
                f"{sub} — 10+ studio-specific folder missing AGENTS.md governance contract. "
                f"Per numeric-folder-prefix.capsule v1.0 §5, studio-specific 10+ folders require "
                f"AGENTS.md at folder root + canonical_contract: 61f650aa reference."
            )
    return findings


def check_99_terminal_convention(studio_root: Path) -> list[str]:
    """Check 3: 99- folders must match capsule §4 patterns."""
    findings = []
    # Scan studio-root + one level deep (folder-local 99-archive can appear in any subdir)
    candidates = list(_list_subdirs(studio_root))
    for top in list(candidates):
        candidates.extend(_list_subdirs(top))
    for sub in candidates:
        name = sub.name
        if not name.startswith("99-"):
            continue
        if name not in ACTIVE_99_PATTERNS:
            findings.append(
                f"{sub} — 99- folder '{name}' not in capsule §4 active conventions "
                f"({sorted(ACTIVE_99_PATTERNS.keys())}). Either rename to a known convention "
                f"OR Mike-walked amendment to capsule §4 required."
            )
    return findings


def check_no_vault_subfolders_numeric_prefix(studio_root: Path) -> list[str]:
    """Check 4: no numeric-prefixed folders directly under vault/ (flat-vault doctrine)."""
    findings = []
    vault_dir = studio_root / "vault"
    if not vault_dir.exists():
        return findings
    for sub in _list_subdirs(vault_dir):
        if sub.name == "files":
            continue  # vault/files/ is the canonical exception
        if _NUMERIC_PREFIX.match(sub.name):
            findings.append(
                f"{sub} — numeric-prefixed folder directly under vault/ violates "
                f"flat-vault doctrine (Mike pin feedback_flat_vault_doctrine + capsule §5). "
                f"Numeric-prefix folders sit at studio-root or sub-project root, not under vault/."
            )
    return findings


def run_all_numeric_folder_prefix_checks(vault_dir: str) -> tuple[list[str], int, int]:
    """Run all 4 checks; return (findings, total_folders_scanned, defects_count).

    vault_dir is the vault/ subdirectory path; studio-root is the parent.
    """
    studio_root = Path(vault_dir).parent
    all_findings: list[str] = []
    all_findings.extend(check_numeric_folder_prefix_reserved_range(studio_root))
    all_findings.extend(check_studio_specific_folder_has_agents_md(studio_root))
    all_findings.extend(check_99_terminal_convention(studio_root))
    all_findings.extend(check_no_vault_subfolders_numeric_prefix(studio_root))
    # Total folders scanned = numeric-prefixed folders under studio-root + vault/ subdirs
    total = sum(1 for sub in _list_subdirs(studio_root) if _NUMERIC_PREFIX.match(sub.name))
    return all_findings, total, len(all_findings)


# WIRE_UP_REFERENCE for tropo-validate.py:
#
#     # --- v1.52 P-lane P3: numeric-folder-prefix.capsule v1.0 §6 Validation Checks ---
#     print('\\n--- numeric-folder-prefix.capsule v1.0 §Validation Checks (v1.52 P-lane P3; 4 checks; WARN at v1.0 / ERROR ratchet v1.1) ---')
#     try:
#         from lib.numeric_folder_prefix_validators import run_all_numeric_folder_prefix_checks
#         nfp_findings, nfp_total, nfp_defects = run_all_numeric_folder_prefix_checks(vault)
#         if not nfp_findings:
#             print(f'[PASS] {nfp_total} numeric-prefix folders verified clean — 4-check family green')
#             total_passes += 1
#         else:
#             print(f'[WARN] {nfp_total} numeric-prefix folders checked; {nfp_defects} findings (WARN at v1.0)')
#             for line in nfp_findings[:10]:
#                 print(f'  {line}')
#                 total_warnings += 1
#             if len(nfp_findings) > 10:
#                 print(f'  ... and {len(nfp_findings) - 10} more')
#                 total_warnings += (len(nfp_findings) - 10)
#     except ImportError as e:
#         print(f'[WARN] numeric-folder-prefix validator lib not importable: {e}')
#         total_warnings += 1
