"""channel_render_validators.py — check_channel_render_safety for rendered_from_events channels.

Per v1.57 Stream B dev-spec (5b2e8c41) §B.5.
Wired into tropo-validate.py main() by Talos T10 v1.57 Lane B.5.

Checks (WARN at v1.57; ERROR ratchet v1.58+):
  1. Channel files with rendered_from_events:true can be re-rendered deterministically
     (same event log → byte-identical output vs on-disk content).
  2. Channel files with rendered_from_events:true have parties: field present.
  3. Channel files with rendered_from_events:true have no manual edits (drift detection
     via byte comparison of re-rendered output vs on-disk).
"""



from __future__ import annotations

TARGETS_CAPSULE = "channels"  # Lane V Layer 3 M.1 targeting (8e2f1a47)
import json, re, subprocess, sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
CHANNELS_DIR = VAULT_ROOT / "channels"
RENDERER = VAULT_ROOT / "vault" / "tools" / "71b0a4d8.py"


def _read_frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^(\w[\w_-]*):\s*(.+)", line)
        if kv:
            fm[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")
    # Parse parties: list
    parties_block = re.search(r"^parties:\s*\n((?:\s+-\s+\S+\n?)+)", m.group(1), re.MULTILINE)
    if parties_block:
        fm["parties"] = [
            re.match(r"\s+-\s+(\S+)", l).group(1)
            for l in parties_block.group(1).splitlines()
            if re.match(r"\s+-\s+\S+", l)
        ]
    return fm


def run_channel_render_safety_checks(vault: Path) -> tuple[list[str], int, int]:
    """Check all channels/. files with rendered_from_events:true for safety + drift.

    Returns (findings, channels_checked, defects).
    """
    channels_dir = vault / "channels"
    renderer = vault / "vault" / "tools" / "71b0a4d8.py"

    if not channels_dir.is_dir():
        return [], 0, 0

    findings: list[str] = []
    checked = 0

    for path in sorted(channels_dir.glob("*.md")):
        if path.name.startswith("_") or path.stem == "CAPSULE":
            continue
        fm = _read_frontmatter(path)
        rendered_flag = str(fm.get("rendered_from_events", "")).lower()
        if rendered_flag != "true":
            continue

        checked += 1
        label = f"channels/{path.name}"

        # Check 1: parties: field present
        parties = fm.get("parties")
        if not parties or (isinstance(parties, list) and len(parties) == 0):
            findings.append(
                f"  [WARN] {label}: rendered_from_events:true but no parties: field (Check 1)"
            )
            continue  # Can't render without parties

        party_uids = parties if isinstance(parties, list) else [parties]

        # Check 2: renderer executable
        if not renderer.exists():
            findings.append(
                f"  [WARN] {label}: render-events-as-views.py not found at {renderer} (Check 2)"
            )
            continue

        # Check 3: re-render and compare (drift detection)
        try:
            cmd = [sys.executable, str(renderer), "--channel", str(path), "--dry-run"]
            for uid in party_uids:
                cmd += ["--party-uid", uid]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                    cwd=str(vault))
            if result.returncode != 0:
                findings.append(
                    f"  [WARN] {label}: renderer exited {result.returncode}: "
                    f"{result.stderr.strip()[:120]} (Check 3)"
                )
                continue

            rendered_output = result.stdout
            on_disk = path.read_text(encoding="utf-8")

            if rendered_output.strip() != on_disk.strip():
                findings.append(
                    f"  [WARN] {label}: rendered_from_events:true but on-disk content "
                    f"differs from canonical renderer output — manual edit or stale render "
                    f"(Check 3 drift detection)"
                )

        except subprocess.TimeoutExpired:
            findings.append(f"  [WARN] {label}: renderer timed out (30s) (Check 3)")
        except Exception as e:
            findings.append(f"  [WARN] {label}: renderer check failed: {e} (Check 3)")

    return findings, checked, len(findings)
