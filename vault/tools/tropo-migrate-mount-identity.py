#!/usr/bin/env python3
"""
---
uid: 9288d8b9
title: migrate-mount-identity — Tool
name: migrate-mount-identity
type: tool
status: active
owner: talos
domain: "Idempotent Mount Identity repair (7b1e0ae5 §3.4): backfill governed mount projects under external-context, reparent mounted mirrors off Tropo Work, dispose handmade stand-in L0s."
spawnable_by:
  - all-executives
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-migrate-mount-identity.py [--apply] [--studio PATH]"
script_path: vault/tools/tropo-migrate-mount-identity.py
input:
  type: object
  description: "Dry-run by default; --apply writes frontmatter + indexes changed UIDs."
created: 2026-08-12
created_by: talos-t41
modified: 2026-08-12
modified_by: talos-t41
governed_by: 34e4cb0b
member_of:
  - 8dd772a0
schema_version: 2
extraction_scope: ship
refs:
  - 7b1e0ae5
tags:
  - tool
  - cli
  - mount-identity
  - migration
---
"""

from __future__ import annotations

"""Mount Identity migration — 7b1e0ae5 §3.4.

Repairs every customer studio that mounted folders before governed mount
projects existed:

1. Backfill ``vault/files/<mount_uid>.md`` as ``type: project`` under
   ``external-context`` (``48f8c52c``).
2. Re-parent mounted mirrors off Tropo Work (``2d083137``) — both
   ``member_of`` and legacy ``subsystem_hub`` edges.
3. Named disposition for this studio's handmade stand-in L0 ``ae4168fc``
   (maz-notes): superseded by mount identity ``1e6a0b5d``.

Dry-run by default. Idempotent: a second ``--apply`` is a no-op.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load_folder_module():
    import importlib.util

    path = TOOLS / "tropo-folder.py"
    spec = importlib.util.spec_from_file_location("tropo_folder_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses reads sys.modules[cls.__module__] while the class body runs.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


folder = _load_folder_module()

EXTERNAL_CONTEXT_L0_UID = folder.EXTERNAL_CONTEXT_L0_UID  # 48f8c52c
TROPO_WORK_L0_UID = "2d083137"
# Handmade stand-in L0 for mindbridge-notes before mount identity existed.
HANDMADE_STANDIN_UID = "ae4168fc"
HANDMADE_STANDIN_SUPERSEDED_BY = "1e6a0b5d"
SPEC_UID = "7b1e0ae5"
ACTOR = "talos-t41"
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
UID_RE = re.compile(r"^[0-9a-f]{8}$")


@dataclass
class Change:
    uid: str
    action: str
    detail: str


@dataclass
class Metrics:
    unresolvable_mount_refs: int = 0
    improper_mount_identity_refs: int = 0


@dataclass
class Plan:
    changes: list[Change] = field(default_factory=list)
    before: Metrics = field(default_factory=Metrics)
    after: Metrics = field(default_factory=Metrics)
    staged: dict[Path, bytes] = field(default_factory=dict)


def resolve_studio(explicit: Optional[str]) -> Path:
    if explicit:
        root = Path(explicit).resolve()
        if not (root / ".tropo").is_dir():
            raise SystemExit(f"not a studio root (missing .tropo/): {root}")
        return root
    here = Path(__file__).resolve()
    for candidate in [here.parents[2], *here.parents]:
        if (candidate / ".tropo").is_dir() and (candidate / "vault").is_dir():
            return candidate
    raise SystemExit("could not locate studio root")


def _parse_frontmatter(text: str) -> tuple[Optional[dict], Optional[str], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, None, text
    try:
        import yaml

        data = yaml.safe_load(match.group(1)) or {}
    except Exception:
        return None, None, text
    if not isinstance(data, dict):
        return None, None, text
    body = text[match.end() :]
    return data, match.group(1), body


def _dump_frontmatter(data: dict) -> str:
    import yaml

    # Keep list/flow style readable and stable for 8-hex UIDs.
    class _Dumper(yaml.SafeDumper):
        pass

    def _str_representer(dumper, value):
        if UID_RE.match(value) or "\n" in value or value == "":
            return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="'")
        if any(ch in value for ch in ":#{}[],&*?|>!%@`"):
            return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="'")
        return dumper.represent_scalar("tag:yaml.org,2002:str", value)

    _Dumper.add_representer(str, _str_representer)
    dumped = yaml.dump(
        data,
        Dumper=_Dumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    return dumped


def _as_uid_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value] if UID_RE.match(value) else []
    out: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and UID_RE.match(item):
                out.append(item)
            elif isinstance(item, dict):
                # ignore
                pass
    return out


def _load_mount_registry(root: Path) -> dict[str, dict]:
    path = root / ".tropo-studio" / "folder-mounts.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    mounts = data.get("mounts") or {}
    return {str(uid): dict(rec or {}) for uid, rec in mounts.items()}


def _identity_path(root: Path, uid: str) -> Path:
    return root / "vault" / "files" / f"{uid}.md"


def is_proper_mount_identity(fm: dict) -> bool:
    if fm.get("type") != "project":
        return False
    return EXTERNAL_CONTEXT_L0_UID in _as_uid_list(fm.get("member_of"))


def measure_metrics(root: Path) -> Metrics:
    files_dir = root / "vault" / "files"
    identities: dict[str, dict] = {}
    refs: list[tuple[str, str]] = []
    for path in sorted(files_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        fm, _, _ = _parse_frontmatter(text)
        if not fm:
            continue
        uid = str(fm.get("uid") or path.stem)
        if path.stem in ("98cdd398", "1e6a0b5d") or fm.get("mount_kind") == "folder":
            identities[path.stem] = fm
        mount_uid = fm.get("mount_uid")
        if isinstance(mount_uid, str) and UID_RE.match(mount_uid):
            refs.append((path.stem, mount_uid))

    # Also treat any mount_uid target file as candidate identity.
    for _stem, mount_uid in refs:
        if mount_uid not in identities:
            ip = _identity_path(root, mount_uid)
            if ip.is_file():
                fm, _, _ = _parse_frontmatter(ip.read_text(encoding="utf-8", errors="replace"))
                if fm:
                    identities[mount_uid] = fm

    metrics = Metrics()
    for _stem, mount_uid in refs:
        ip = _identity_path(root, mount_uid)
        if not ip.is_file():
            metrics.unresolvable_mount_refs += 1
            metrics.improper_mount_identity_refs += 1
            continue
        fm = identities.get(mount_uid)
        if fm is None:
            fm, _, _ = _parse_frontmatter(ip.read_text(encoding="utf-8", errors="replace"))
            identities[mount_uid] = fm or {}
        if not is_proper_mount_identity(identities[mount_uid]):
            metrics.improper_mount_identity_refs += 1
    return metrics


def _rewrite(path: Path, fm: dict, body: str) -> bytes:
    return f"---\n{_dump_frontmatter(fm)}---\n{body}".encode("utf-8")


def _retarget_existing_identity(path: Path, fm: dict, body: str, name: str) -> bytes:
    """Preserve body; force project-under-external-context shape."""
    fm = dict(fm)
    fm["type"] = "project"
    fm.pop("document_type", None)
    fm["member_of"] = [EXTERNAL_CONTEXT_L0_UID]
    fm.setdefault("mount_kind", "folder")
    if name and not fm.get("mount_name"):
        fm["mount_name"] = name
    fm.setdefault("mount_record", ".tropo-studio/folder-mounts.json")
    tags = list(fm.get("tags") or [])
    for tag in ("folder-mount", "mount-identity", "external-context"):
        if tag not in tags:
            tags.append(tag)
    fm["tags"] = tags
    refs = _as_uid_list(fm.get("refs"))
    if SPEC_UID not in refs:
        refs.append(SPEC_UID)
    fm["refs"] = refs
    fm["modified_by"] = ACTOR
    return _rewrite(path, fm, body)


def _dispose_handmade_standin(path: Path, fm: dict, body: str) -> bytes:
    fm = dict(fm)
    superseded_by = fm.get("mount_uid")
    if not isinstance(superseded_by, str) or not UID_RE.match(superseded_by):
        superseded_by = HANDMADE_STANDIN_SUPERSEDED_BY
    fm["status"] = "archived"
    fm["state"] = "archived"
    fm["member_of"] = [superseded_by]
    hubs = [h for h in _as_uid_list(fm.get("subsystem_hub")) if h != TROPO_WORK_L0_UID]
    if hubs:
        fm["subsystem_hub"] = hubs
    else:
        fm.pop("subsystem_hub", None)
    fm["disposition"] = "superseded-by-mount-identity"
    fm["superseded_by"] = superseded_by
    fm["modified_by"] = ACTOR
    note = (
        "\n\n## Disposition (7b1e0ae5 §3.4)\n\n"
        f"*Superseded by governed mount identity "
        f"[{superseded_by}]({superseded_by}.md) "
        f"under [external-context]({EXTERNAL_CONTEXT_L0_UID}.md). "
        "This handmade stand-in L0 is retained as an archived historical record; "
        "children were re-parented to the mount.*\n"
    )
    if "Disposition (7b1e0ae5 §3.4)" not in body:
        body = body.rstrip() + note
    return _rewrite(path, fm, body)


def _reparent_mount_row(fm: dict) -> tuple[dict, list[str]]:
    """Return updated frontmatter + list of mutation labels (empty if no-op)."""
    fm = dict(fm)
    actions: list[str] = []
    mount_uid = fm.get("mount_uid")
    if not isinstance(mount_uid, str) or not UID_RE.match(mount_uid):
        return fm, actions

    members = _as_uid_list(fm.get("member_of"))
    hubs = _as_uid_list(fm.get("subsystem_hub"))
    changed = False

    if TROPO_WORK_L0_UID in members:
        members = [mount_uid if m == TROPO_WORK_L0_UID else m for m in members]
        # Dedup while preserving order
        seen: set[str] = set()
        members = [m for m in members if not (m in seen or seen.add(m))]
        actions.append(f"member_of: {TROPO_WORK_L0_UID}→{mount_uid}")
        changed = True

    if HANDMADE_STANDIN_UID in members:
        members = [
            mount_uid if m == HANDMADE_STANDIN_UID else m for m in members
        ]
        seen = set()
        members = [m for m in members if not (m in seen or seen.add(m))]
        actions.append(f"member_of: {HANDMADE_STANDIN_UID}→{mount_uid}")
        changed = True

    # Strays: folder mirrors with empty member_of but Tropo Work via subsystem_hub
    # (or no parent at all).
    if not members and (
        TROPO_WORK_L0_UID in hubs
        or fm.get("type") == "project"
        or fm.get("governance") == "tier-1-sidecar"
    ):
        members = [mount_uid]
        actions.append(f"member_of: []→[{mount_uid}]")
        changed = True

    if TROPO_WORK_L0_UID in hubs:
        hubs = [h for h in hubs if h != TROPO_WORK_L0_UID]
        actions.append(f"subsystem_hub: drop {TROPO_WORK_L0_UID}")
        changed = True

    if not changed:
        return fm, []

    fm["member_of"] = members
    if hubs:
        fm["subsystem_hub"] = hubs
    else:
        fm.pop("subsystem_hub", None)
    fm["modified_by"] = ACTOR
    return fm, actions


def build_plan(root: Path) -> Plan:
    plan = Plan()
    plan.before = measure_metrics(root)
    mounts = _load_mount_registry(root)
    files_dir = root / "vault" / "files"

    # --- 1. Mount identities ---
    for mount_uid, rec in sorted(mounts.items()):
        name = str(rec.get("name") or mount_uid)
        path = _identity_path(root, mount_uid)
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            fm, _, body = _parse_frontmatter(text)
            if fm and is_proper_mount_identity(fm):
                continue
            if fm is None:
                plan.changes.append(
                    Change(mount_uid, "identity-rewrite", "unparseable; recreate")
                )
                raw = folder._render_mount_identity_bytes(
                    mount_uid, name, ACTOR, mounted_at=folder._now()
                )
                plan.staged[path] = raw
            else:
                plan.changes.append(
                    Change(
                        mount_uid,
                        "identity-retarget",
                        f"type={fm.get('type')} member_of={fm.get('member_of')}",
                    )
                )
                plan.staged[path] = _retarget_existing_identity(path, fm, body, name)
        else:
            plan.changes.append(
                Change(mount_uid, "identity-create", f"name={name}")
            )
            plan.staged[path] = folder._render_mount_identity_bytes(
                mount_uid, name, ACTOR, mounted_at=folder._now()
            )

    # --- 2. Reparent mounted rows ---
    for path in sorted(files_dir.glob("*.md")):
        if path in plan.staged:
            # Identity already staged; still allow reparent pass on other files only.
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        fm, _, body = _parse_frontmatter(text)
        if not fm:
            continue
        uid = path.stem
        if uid == HANDMADE_STANDIN_UID:
            continue  # handled in disposition
        mount_uid = fm.get("mount_uid")
        if not isinstance(mount_uid, str) or not UID_RE.match(mount_uid):
            continue
        if uid == mount_uid:
            continue  # the identity row itself
        new_fm, actions = _reparent_mount_row(fm)
        if not actions:
            continue
        plan.changes.append(Change(uid, "reparent", "; ".join(actions)))
        plan.staged[path] = _rewrite(path, new_fm, body)

    # --- 3. Handmade stand-in disposition ---
    standin = _identity_path(root, HANDMADE_STANDIN_UID)
    if standin.is_file() and standin not in plan.staged:
        text = standin.read_text(encoding="utf-8", errors="replace")
        fm, _, body = _parse_frontmatter(text)
        if fm is not None:
            superseded_by = fm.get("mount_uid")
            if not isinstance(superseded_by, str) or not UID_RE.match(superseded_by):
                superseded_by = HANDMADE_STANDIN_SUPERSEDED_BY
            already = (
                fm.get("disposition") == "superseded-by-mount-identity"
                and fm.get("state") == "archived"
                and superseded_by in _as_uid_list(fm.get("member_of"))
                and TROPO_WORK_L0_UID not in _as_uid_list(fm.get("subsystem_hub"))
            )
            if not already:
                plan.changes.append(
                    Change(
                        HANDMADE_STANDIN_UID,
                        "dispose-standin",
                        f"superseded-by={HANDMADE_STANDIN_SUPERSEDED_BY}",
                    )
                )
                plan.staged[standin] = _dispose_handmade_standin(standin, fm, body)

    return plan


def apply_plan(root: Path, plan: Plan) -> None:
    if not plan.staged:
        return
    # Write + index through the same canonical freshen path mount uses.
    folder._freshen_projection_index(root, plan.staged)


def finalize_metrics(root: Path, plan: Plan) -> None:
    plan.after = measure_metrics(root)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Idempotent Mount Identity migration (7b1e0ae5 §3.4)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default is dry-run).",
    )
    parser.add_argument("--studio", default=None, help="Studio root (default: auto).")
    args = parser.parse_args(argv)

    root = resolve_studio(args.studio)
    plan = build_plan(root)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Mount Identity migration ({SPEC_UID} §3.4) — {mode} ===")
    print(f"Studio: {root}")
    print(
        f"Before: unresolvable={plan.before.unresolvable_mount_refs} "
        f"improper_identity={plan.before.improper_mount_identity_refs}"
    )
    print(f"Planned changes: {len(plan.changes)}")
    for change in plan.changes[:40]:
        print(f"  - {change.uid}: {change.action} — {change.detail}")
    if len(plan.changes) > 40:
        print(f"  … {len(plan.changes) - 40} more")

    if args.apply:
        apply_plan(root, plan)
        # Re-measure after writes (and after identity files exist on disk).
        finalize_metrics(root, plan)
        print(
            f"After:  unresolvable={plan.after.unresolvable_mount_refs} "
            f"improper_identity={plan.after.improper_mount_identity_refs}"
        )
        if plan.after.unresolvable_mount_refs != 0:
            print("ERROR: unresolvable mount_uid refs remain", file=sys.stderr)
            return 1
        if plan.after.improper_mount_identity_refs != 0:
            print("ERROR: improper mount identities remain", file=sys.stderr)
            return 1
        # Idempotence probe on the post-apply tree.
        second = build_plan(root)
        print(f"Second-plan changes: {len(second.changes)} (expect 0)")
        if second.changes:
            print("ERROR: migration is not idempotent", file=sys.stderr)
            for change in second.changes[:20]:
                print(f"  - {change.uid}: {change.action} — {change.detail}", file=sys.stderr)
            return 1
        print("Result: CLEAN")
        return 0

    # Dry-run: project after-metrics from staged identity overlays.
    projected = Metrics()
    identity_overlay: dict[str, dict] = {}
    for path, raw in plan.staged.items():
        if path.parent.name == "files" and UID_RE.match(path.stem):
            fm, _, _ = _parse_frontmatter(raw.decode("utf-8"))
            if fm:
                identity_overlay[path.stem] = fm
    for path in (root / "vault" / "files").glob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        fm, _, _ = _parse_frontmatter(text)
        if not fm:
            continue
        mount_uid = fm.get("mount_uid")
        if not isinstance(mount_uid, str) or not UID_RE.match(mount_uid):
            continue
        if mount_uid in identity_overlay:
            fm_id = identity_overlay[mount_uid]
        else:
            ip = _identity_path(root, mount_uid)
            if not ip.is_file():
                projected.unresolvable_mount_refs += 1
                projected.improper_mount_identity_refs += 1
                continue
            fm_id, _, _ = _parse_frontmatter(
                ip.read_text(encoding="utf-8", errors="replace")
            )
            fm_id = fm_id or {}
        if not is_proper_mount_identity(fm_id):
            projected.improper_mount_identity_refs += 1
    print(
        f"Projected after: unresolvable={projected.unresolvable_mount_refs} "
        f"improper_identity={projected.improper_mount_identity_refs}"
    )
    print("Dry-run only — re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
