#!/usr/bin/env python3
"""---
uid: c778f748
name: migrate-sidecar-to-singlefile
type: tool
status: active
owner: talos
domain: "Migrate one sidecar tool entry (vault/files/<uid>.md + .tropo/scripts/<name>.py) to single-file-truth at vault/tools/<uid>.py per tool.capsule v1.6 §2.5. Idempotent."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/c778f748.py --sidecar-uid <uid>"
spawnable_by:
  - talos
  - argus
input:
  type: object
  required: [sidecar_uid]
  properties:
    sidecar_uid:
      type: string
      description: "8-hex UID of the sidecar vault/files/<uid>.md entry to migrate"
    dry_run:
      type: boolean
      description: "Preview migration without writing files (default: false)"
output:
  type: object
  properties:
    migrated_path: {type: string, description: "New path: vault/tools/<uid>.py"}
    recycled_sidecar: {type: string, description: "Recycled sidecar path"}
    status: {type: string, enum: [ok, skipped, error]}
write_scope:
  - vault/tools/
  - vault/99-recycle/
destructive: false
audit_required: false
governance_category: lifecycle
description: "v1.56 Lane M migration helper. Reads the sidecar vault/files/<uid>.md frontmatter, moves .tropo/scripts/<name>.py to vault/tools/<uid>.py with frontmatter embedded in leading docstring, then recycles the sidecar via tropo-recycle.py. Idempotent: if vault/tools/<uid>.py already exists, skips. R6 chicken-egg mitigation: tropo-recycle.py is called at its .tropo/scripts/ location until it migrates itself last."
created: 2026-05-27
created_by: talos-t10
governed_by: d5e1b4a3
member_of:
  - c7e4f9a2
schema_version: 2
---

Migration helper for v1.56 Lane M: sidecar → single-file-truth.

Usage:
  python3 vault/tools/c778f748.py --sidecar-uid <8-hex-uid>
  python3 vault/tools/c778f748.py --sidecar-uid <8-hex-uid> --dry-run

The sidecar entry at vault/files/<uid>.md must have a script_path: .tropo/scripts/<name>.py.
The script is moved to vault/tools/<uid>.py with the sidecar frontmatter embedded.
The sidecar vault/files/<uid>.md is then recycled via tropo-recycle.py.

Idempotent: if vault/tools/<uid>.py already exists, the migration is skipped.
"""

from __future__ import annotations
import argparse, re, shutil, subprocess, sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = VAULT_ROOT / "vault" / "tools"
FILES_DIR = VAULT_ROOT / "vault" / "files"
RECYCLE_SCRIPT = VAULT_ROOT / "vault" / "tools" / "2573f6dd.py"  # tropo-recycle (v1.56 migrated)

UID_RE = re.compile(r"^[0-9a-f]{8}$")


def read_file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def get_scalar_fm(fm: str, field: str) -> str | None:
    m = re.search(rf"^{re.escape(field)}:\s*(.+?)\s*$", fm, re.MULTILINE)
    if not m:
        return None
    val = m.group(1).strip().strip('"').strip("'")
    if "#" in val:
        val = val.split("#")[0].strip()
    return val or None


def split_sidecar_frontmatter(text: str) -> str | None:
    """Extract raw YAML frontmatter from a vault/files/<uid>.md sidecar."""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    return m.group(1) if m else None


def build_docstring_frontmatter(fm_yaml: str, uid: str, new_script_path: str) -> str:
    """Build the embedded frontmatter docstring for vault/tools/<uid>.py.

    Updates script_path and cli_command to point at the new vault/tools/ location.
    Adds implementation_kind: python-script if absent.
    """
    lines = fm_yaml.splitlines()
    out_lines: list[str] = []
    has_impl_kind = any(l.strip().startswith("implementation_kind:") for l in lines)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("script_path:"):
            out_lines.append(f"script_path: {new_script_path}")
        elif stripped.startswith("cli_command:"):
            # Update cli_command to use vault/tools/ path
            existing = get_scalar_fm(fm_yaml, "cli_command") or ""
            old_scripts_pattern = r'\.tropo/scripts/[^\s"\']+'
            new_cmd = re.sub(old_scripts_pattern, new_script_path, existing)
            if not new_cmd or new_cmd == existing:
                # Fallback: replace just the script path segment
                new_cmd = existing.replace(".tropo/scripts/", "vault/tools/", 1)
            out_lines.append(f'cli_command: "python3 {new_script_path}"'
                             if not new_cmd.strip() else f"cli_command: {new_cmd}")
        else:
            out_lines.append(line)

    if not has_impl_kind:
        # Insert implementation_kind after transport: line
        result_lines: list[str] = []
        for line in out_lines:
            result_lines.append(line)
            if line.strip().startswith("transport:"):
                result_lines.append("implementation_kind: python-script")
        out_lines = result_lines

    return "\n".join(out_lines)


def migrate_sidecar(uid: str, dry_run: bool) -> dict:
    if not UID_RE.match(uid):
        return {"status": "error", "message": f"invalid UID format: {uid!r}"}

    sidecar_path = FILES_DIR / f"{uid}.md"
    target_path = TOOLS_DIR / f"{uid}.py"
    new_script_rel = f"vault/tools/{uid}.py"

    if not sidecar_path.exists():
        return {"status": "error", "message": f"sidecar not found: {sidecar_path}"}

    if target_path.exists():
        print(f"  [SKIP] vault/tools/{uid}.py already exists — migration already done")
        return {"status": "skipped", "migrated_path": str(target_path)}

    sidecar_text = read_file_text(sidecar_path)
    fm_yaml = split_sidecar_frontmatter(sidecar_text)
    if fm_yaml is None:
        return {"status": "error", "message": f"no frontmatter in {sidecar_path}"}

    script_path_str = get_scalar_fm(fm_yaml, "script_path")
    if not script_path_str:
        return {"status": "error", "message": f"{uid}: no script_path in sidecar frontmatter"}

    source_script = VAULT_ROOT / script_path_str
    if not source_script.exists():
        return {"status": "error", "message": f"{uid}: script not found at {source_script}"}

    # Build embedded frontmatter
    embedded_fm = build_docstring_frontmatter(fm_yaml, uid, new_script_rel)

    # Read existing script, strip shebang for re-attachment
    original_content = read_file_text(source_script)
    lines = original_content.splitlines(keepends=True)
    shebang = ""
    rest_start = 0
    if lines and lines[0].startswith("#!"):
        shebang = lines[0]
        rest_start = 1

    # Compose new file: shebang + frontmatter docstring + original body (without shebang)
    rest_body = "".join(lines[rest_start:])
    new_content = (
        f'{shebang}'
        f'"""\n---\n{embedded_fm}\n---\n"""\n\n'
        f'{rest_body}'
    )

    print(f"  {'[DRY-RUN] ' if dry_run else ''}Migrating {script_path_str} → {new_script_rel}")

    if not dry_run:
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_content, encoding="utf-8")
        # Remove source script (it's now at vault/tools/)
        source_script.unlink()
        print(f"  Wrote {target_path}")
        print(f"  Removed {source_script}")

        # Recycle the sidecar entry
        if RECYCLE_SCRIPT.exists():
            recycle_cmd = [sys.executable, str(RECYCLE_SCRIPT), uid, "--reason",
                           f"v1.56 Lane M: migrated to vault/tools/{uid}.py (single-file-truth per tool.capsule v1.6 §2.5)"]
            result = subprocess.run(recycle_cmd, cwd=str(VAULT_ROOT), capture_output=True, text=True)
            if result.returncode == 0:
                print(f"  Recycled vault/files/{uid}.md")
            else:
                print(f"  WARN: tropo-recycle.py returned {result.returncode}: {result.stderr.strip()}")
        else:
            print(f"  WARN: tropo-recycle.py not found at {RECYCLE_SCRIPT}; sidecar not recycled")

    return {"status": "ok", "migrated_path": str(target_path)}


def main() -> int:
    p = argparse.ArgumentParser(
        description="Migrate a sidecar tool entry to single-file-truth at vault/tools/<uid>.py"
    )
    p.add_argument("--sidecar-uid", required=True, dest="sidecar_uid",
                   help="8-hex UID of the vault/files/<uid>.md sidecar to migrate")
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Preview migration without writing files")
    args = p.parse_args()

    result = migrate_sidecar(args.sidecar_uid, args.dry_run)
    print(f"  status: {result['status']}")
    if result.get("message"):
        print(f"  message: {result['message']}", file=sys.stderr)
    if result["status"] == "error":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
