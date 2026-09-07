#!/usr/bin/env python3
"""
---
uid: f0157919c42f
name: tropo-genesis-companions
type: tool
title: "tropo-genesis-companions — Mint founding companions from shipped content"
status: active
owner: talos
domain: "Offline, per-Studio genesis for Cal and Darin."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-genesis-companions.py --studio . (--po | --accept cal|darin|cal,darin)"
script_path: vault/tools/tropo-genesis-companions.py
spawnable_by:
  - all-executives
created: 2026-08-31
created_by: talos-t56
modified: 2026-09-06
modified_by: argus-a172
governed_by: d5e1b4a3
member_of:
  - 99ed55fd
schema_version: 2
extraction_scope: ship
trigger_description: "Materialize Cal and Darin locally from identity-free shipped templates."
belt: true
---
"""

from __future__ import annotations

"""Ship companion content; mint companion identity where the Studio lives.

The templates are vendor content. Every identity-bearing artifact this module
writes is absent from the image and therefore structurally unreachable by the
image applier. Genesis is the one bounded interim path allowed to create a
local Studio prefix while issuance is unavailable.
"""

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


COMPANIONS: tuple[dict[str, str], ...] = (
    {
        "slug": "cal",
        "display_name": "Cal",
        "role": "Architect and Builder",
        "generation_prefix": "C",
    },
    {
        "slug": "darin",
        "display_name": "Darin",
        "role": "Strategist and COO",
        "generation_prefix": "D",
    },
)
#: Po ships as a companion class, not crew (Argus A165's ruling, his last
#: act before retiring: evt_b51c083be28ac6fe_00000344, 2026-09-01T12:00:42Z).
#: Deliberately NOT a member of COMPANIONS: a
#: Studio that already commissioned a real Po must never have her identity or
#: charter body touched by this module — no section-preserving applier exists
#: to merge template content into a real, mixed charter. This spec is used
#: only to mint her locally, exactly like Cal and Darin, when a cold box has
#: no Po at all (see genesis()).
PO_SPEC: dict[str, str] = {
    "slug": "po",
    "display_name": "Po",
    "role": "Studio Concierge",
    "generation_prefix": "P",
}
#: v1.95 Spine A AC5 D3: the crew-block relationship each present party carries.
CREW_RELATIONSHIPS: dict[str, str] = {
    "cal": "architecture-and-build",
    "darin": "strategy-and-operations",
    "po": "studio-concierge",
}
CREW_START = "<!-- tropo-companion-crew:start -->"
CREW_END = "<!-- tropo-companion-crew:end -->"
TOKEN_RE = re.compile(r"\{\{([a-z_]+)\}\}")


class CompanionGenesisError(RuntimeError):
    """Genesis cannot complete without guessing identity or overwriting memory."""


def _load_module(path: Path, stem: str):
    if not path.is_file():
        raise CompanionGenesisError(f"required shipped module is absent: {path}")
    name = f"_tropo_companion_{stem}_{abs(hash(str(path.resolve())))}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CompanionGenesisError(f"cannot load required module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _frontmatter(text: str, path: Path) -> dict[str, Any]:
    if not text.startswith("---\n"):
        raise CompanionGenesisError(f"{path} has no closed YAML frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        raise CompanionGenesisError(f"{path} has unterminated YAML frontmatter")
    try:
        value = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise CompanionGenesisError(f"{path} has invalid YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise CompanionGenesisError(f"{path} frontmatter is not a mapping")
    return value


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _write_if_absent(path: Path, data: bytes) -> bool:
    if path.exists() or path.is_symlink():
        return False
    _atomic_write(path, data)
    return True


def _render(path: Path, values: dict[str, str]) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CompanionGenesisError(f"cannot read shipped template {path}: {exc}") from exc
    missing = sorted(set(TOKEN_RE.findall(text)) - set(values))
    if missing:
        raise CompanionGenesisError(
            f"template {path} requires unresolved token(s): {', '.join(missing)}"
        )
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    leftovers = sorted(set(TOKEN_RE.findall(text)))
    if leftovers:
        raise CompanionGenesisError(
            f"template {path} retained token(s): {', '.join(leftovers)}"
        )
    # Template placeholders stay quoted so the shipped template is valid YAML.
    # Generated UID fields must be plain scalars: the lifecycle and event
    # readers intentionally parse these hot-path fields with the shared
    # governed-UID regex and do not accept decorative quotes.
    text = re.sub(
        r'^(uid|agent_uid|party_uid|agent_root_uid|owner):\s*["\']'
        r'([0-9a-f]+)["\']\s*$',
        r"\1: \2",
        text,
        flags=re.MULTILINE,
    )
    return text


def _agent_capsule_uid(root: Path, gp) -> str:
    path = root / "vault" / "capsules" / "tropo-agent.capsule.md"
    fm = _frontmatter(path.read_text(encoding="utf-8"), path)
    uid = str(fm.get("uid") or "")
    if not gp.is_governed_uid_shape(uid):
        raise CompanionGenesisError(f"agent capsule at {path} has invalid uid {uid!r}")
    return uid


def _registry(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root / ".tropo-studio" / "registries" / "agent-registry.yaml"
    if not path.is_file():
        raise CompanionGenesisError(f"agent registry is absent: {path}")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CompanionGenesisError(f"agent registry cannot be read: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("agents"), dict):
        raise CompanionGenesisError("agent registry has no top-level agents mapping")
    return path, value


def _registry_identity(root: Path, slug: str, gp) -> tuple[str, dict[str, Any]] | None:
    _, registry = _registry(root)
    for key, row in registry["agents"].items():
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "").casefold() != slug.casefold():
            continue
        party_uid = str(row.get("party_uid") or key)
        if not gp.is_governed_uid_shape(party_uid):
            raise CompanionGenesisError(
                f"registry row for {slug} has invalid party uid {party_uid!r}"
            )
        return party_uid, row
    return None


def _append_registry_rows(
    root: Path, identities: dict[str, dict[str, str]], specs=COMPANIONS
) -> bool:
    path, before = _registry(root)
    existing_names = {
        str(row.get("name") or "").casefold()
        for row in before["agents"].values()
        if isinstance(row, dict)
    }
    additions: list[str] = []
    for spec in specs:
        slug = spec["slug"]
        if slug.casefold() in existing_names:
            continue
        identity = identities[slug]
        additions.extend(
            [
                "",
                f"  '{identity['party_uid']}':",
                "    class: crew",
                "    type: agent",
                f"    name: {slug}",
                f"    display-name: {spec['display_name']}",
                f"    party_uid: '{identity['party_uid']}'",
                f"    role: \"{spec['role']}\"",
                "    status: active",
                f"    generation-prefix: {spec['generation_prefix']}",
                f"    path: agents/{slug}/{slug}-activation.md",
                f"    activation-file: agents/{slug}/{slug}-activation.md",
                f"    commissioned: {dt.date.today().isoformat()}",
                "    created_by: studio-genesis",
            ]
        )
    if not additions:
        return False
    original = path.read_text(encoding="utf-8")
    updated = original.rstrip() + "\n" + "\n".join(additions) + "\n"
    try:
        parsed = yaml.safe_load(updated)
    except yaml.YAMLError as exc:
        raise CompanionGenesisError(f"companion registry update would be invalid: {exc}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("agents"), dict):
        raise CompanionGenesisError("companion registry update lost the agents mapping")
    _atomic_write(path, updated.encode("utf-8"))
    return True


def _find_unified_entry(root: Path, slug: str) -> tuple[Path, dict[str, Any]] | None:
    home = root / "vault" / "agents"
    if not home.is_dir():
        return None
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(home.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
            fm = _frontmatter(text, path)
        except (OSError, CompanionGenesisError):
            continue
        if str(fm.get("type") or "") == "agent" and str(
            fm.get("agent") or ""
        ).casefold() == slug.casefold():
            matches.append((path, fm))
    if len(matches) > 1:
        raise CompanionGenesisError(
            f"{len(matches)} unified entries claim agent {slug}; identity is ambiguous"
        )
    return matches[0] if matches else None


def _identity_from_entry(root: Path, slug: str, gp) -> dict[str, str] | None:
    found = _find_unified_entry(root, slug)
    if found is None:
        return None
    path, fm = found
    identity = {
        "uid": str(fm.get("uid") or ""),
        "party_uid": str(fm.get("party_uid") or ""),
        "agent_root_uid": str(fm.get("agent_root_uid") or ""),
    }
    invalid = [name for name, value in identity.items() if not gp.is_governed_uid_shape(value)]
    if invalid:
        raise CompanionGenesisError(
            f"existing {slug} entry {path} has invalid identity field(s): {invalid}"
        )
    if path.stem != identity["uid"]:
        raise CompanionGenesisError(
            f"existing {slug} entry filename {path.name} does not match uid {identity['uid']}"
        )
    return identity


def _entry_created(root: Path, slug: str, fallback: str) -> str:
    found = _find_unified_entry(root, slug)
    if found is None:
        return fallback
    value = str(found[1].get("created") or "").strip()
    return value or fallback


def _po_target(root: Path, gp) -> tuple[Path, str]:
    registry_hit = _registry_identity(root, "po", gp)
    if registry_hit is None:
        raise CompanionGenesisError(
            "Po has no agent-registry row; companion cross-resolution cannot guess "
            "the concierge party identity"
        )
    party_uid, _ = registry_hit
    found = _find_unified_entry(root, "po")
    if found is not None:
        path, fm = found
        if str(fm.get("status") or "").upper() == "RETIRED":
            raise CompanionGenesisError(
                f"Po charter target {path} is retired; genesis will not write "
                "new customer crew state into a closed identity"
            )
        declared = str(fm.get("party_uid") or "")
        if declared != party_uid:
            raise CompanionGenesisError(
                f"Po registry party uid {party_uid} disagrees with {path}: {declared!r}"
            )
        return path, party_uid
    legacy = root / "agents" / "po" / "po-charter.md"
    if legacy.is_file():
        return legacy, party_uid
    raise CompanionGenesisError(
        "Po resolves in the registry but no shipped writable charter resolves at "
        "vault/agents/<uid>.md or agents/po/po-charter.md; AC10 cannot be "
        "satisfied by writing customer crew state into the update-managed kernel"
    )


def _crew_block(party_uids: list[tuple[str, str]]) -> str:
    lines = [CREW_START]
    for party_uid, relationship in party_uids:
        lines.extend(
            [
                f"- party_uid: \"{party_uid}\"",
                f"  relationship: {relationship}",
            ]
        )
    lines.append(CREW_END)
    return "\n".join(lines)


def _update_crew_section(path: Path, block: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if CREW_START in text or CREW_END in text:
        if text.count(CREW_START) != 1 or text.count(CREW_END) != 1:
            raise CompanionGenesisError(f"{path} has malformed companion crew markers")
        start = text.index(CREW_START)
        end = text.index(CREW_END, start) + len(CREW_END)
        updated = text[:start] + block + text[end:]
    else:
        heading = re.search(r"^## §Crew\s*$", text, re.MULTILINE)
        if heading:
            insert = heading.end()
            updated = text[:insert] + "\n\n" + block + text[insert:]
        else:
            updated = text.rstrip() + "\n\n## §Crew\n\n" + block + "\n"
    if updated == text:
        return False
    _atomic_write(path, updated.encode("utf-8"))
    return True


def _principal_record(
    spec: dict[str, str], identity: dict[str, str], today: str, owner: str
) -> bytes:
    text = f"""---
uid: {identity['party_uid']}
type: principal
title: "{spec['display_name']} — Companion Principal"
name: principal-{spec['slug']}
display_name: {spec['display_name']}
principal_class: agent-companion
role: "{spec['role']}"
status: active
state: active
owner: {owner}
created: {today}
created_by: studio-genesis
modified: {today}
modified_by: studio-genesis
schema_version: 2
---

# {spec['display_name']} — Companion Principal

The addressable party identity for this Studio's {spec['display_name']}.
Names are for people; this UID is the source-of-record reference.
"""
    return text.encode("utf-8")


def _agent_root_record(
    spec: dict[str, str], identity: dict[str, str], today: str, owner: str
) -> bytes:
    text = f"""---
uid: {identity['agent_root_uid']}
type: project
name: agent-root-{spec['slug']}
title: "{spec['display_name']} — Agent Root Project"
description: "Long-lived lineage root for this Studio's {spec['display_name']}."
status: active
state: active
agent_slug: {spec['slug']}
agent_class: executive
role: "{spec['role']}"
generation_prefix: {spec['generation_prefix']}
owner: {owner}
author: studio-genesis
created: {today}
created_by: studio-genesis
modified: {today}
modified_by: studio-genesis
schema_version: 2
member_of: []
---

# {spec['display_name']} — Agent Root Project

Every generation of this Studio's {spec['display_name']} belongs to this root.
"""
    return text.encode("utf-8")


def _materialize_memory(
    root: Path, template_root: Path, spec: dict[str, str]
) -> list[str]:
    slug = spec["slug"]
    display = spec["display_name"]
    home = root / "agents" / slug / ".tropo-capsule" / "memory"
    home.mkdir(parents=True, exist_ok=True)
    changed: list[str] = []
    method_source = template_root / "memory-edition" / f"{slug}-method-pins.jsonl"
    crew_source = template_root / "memory-edition" / f"{slug}-crew-memories.jsonl"
    for source, target_name in (
        (method_source, "method-pins.jsonl"),
        (crew_source, "crew-memories.jsonl"),
    ):
        if _write_if_absent(home / target_name, source.read_bytes()):
            changed.append((home / target_name).relative_to(root).as_posix())
    episodic = home / "agent-memories.jsonl"
    if _write_if_absent(episodic, b""):
        changed.append(episodic.relative_to(root).as_posix())
    active = home / "agent-memory.md"
    active_text = f"""# {display} — Active Memory

## Inherited method

Read `method-pins.jsonl`. Those rows are inherited operating knowledge and
never claims about events {display} personally lived.

## Crew memory

Read `crew-memories.jsonl`. Every non-empty row must resolve to the originating
rehearsal journal by timestamp. This partition remains empty until that
rehearsal actually occurs.

## Episodic log

Append lived observations to `agent-memories.jsonl`. Do not rewrite prior rows.

## Handoff

First generation; no predecessor handoff exists.
"""
    if _write_if_absent(active, active_text.encode("utf-8")):
        changed.append(active.relative_to(root).as_posix())
    return changed


def _ensure_lineage(root: Path, spec: dict[str, str]) -> bool:
    path = root / "agents" / spec["slug"] / "lineage.jsonl"
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("t") == "born":
                return False
    tool = root / "vault" / "tools" / "tropo-lineage.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(tool),
            "--root",
            str(root),
            "born",
            "--agent",
            spec["slug"],
            "--by",
            "studio-genesis",
            "--model",
            "companion-content",
            "--prefix",
            spec["generation_prefix"],
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise CompanionGenesisError(
            f"lineage birth failed for {spec['slug']}: {(proc.stderr or proc.stdout)[-800:]}"
        )
    return True


def _born_generation(root: Path, spec: dict[str, str]) -> str:
    path = root / "agents" / spec["slug"] / "lineage.jsonl"
    generation = f"{spec['generation_prefix']}1"
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("t") == "born" and row.get("gen"):
                generation = str(row["gen"])
    return generation


def _emit_activated(
    root: Path, spec: dict[str, str], identity: dict[str, str], founder_uid: str
) -> str:
    """The companion's birth on the bus IS the acceptance record (events
    capsule v1.14, v1.95 Spine A AC5): `tropo.agent.activated` from the
    companion's own party, subject the founder principal, through the same
    emitter every other Studio writer uses. A birth whose record did not land
    is reported, never swallowed — Po must see it and re-send by hand."""
    slug = spec["slug"]
    tool = root / "vault" / "tools" / "tropo-emit-event.py"
    payload = {
        "agent": slug,
        "generation": _born_generation(root, spec),
        "model": "companion-content",
        "party_uid": identity["party_uid"],
        "agent_uid": identity["uid"],
        "agent_root_uid": identity["agent_root_uid"],
        "founder_principal_uid": founder_uid,
        "by": "studio-genesis",
        "lineage": f"agents/{slug}/lineage.jsonl",
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(tool),
            "--type",
            "tropo.agent.activated",
            "--source",
            f"/agents/{slug}",
            "--as",
            slug,
            "--lifecycle",
            "evergreen",
            "--subject",
            founder_uid,
            "--data",
            json.dumps(payload),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise CompanionGenesisError(
            f"{spec['display_name']} was born but tropo.agent.activated did not land: "
            f"{(proc.stderr or proc.stdout)[-800:]}"
        )
    try:
        return str(json.loads(proc.stdout)["event_uid"])
    except (ValueError, KeyError, TypeError):
        return proc.stdout.strip()


def _registry_party_uids(root: Path, gp) -> dict[str, str]:
    _, value = _registry(root)
    resolved: dict[str, str] = {}
    for key, row in value["agents"].items():
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").casefold()
        party_uid = str(row.get("party_uid") or key)
        if name and gp.is_governed_uid_shape(party_uid):
            resolved[name] = party_uid
    return resolved


def _crew_values(path: Path, gp, expected_count: int = 2) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if CREW_START not in text or CREW_END not in text:
        raise CompanionGenesisError(f"{path} has no resolved companion crew block")
    body = text.split(CREW_START, 1)[1].split(CREW_END, 1)[0]
    values = re.findall(r'^\s*-\s*party_uid:\s*["\']?([^"\'\s]+)', body, re.MULTILINE)
    if len(values) != expected_count:
        raise CompanionGenesisError(f"{path} crew block has {len(values)} party references")
    invalid = [value for value in values if not gp.is_governed_uid_shape(value)]
    if invalid:
        raise CompanionGenesisError(
            f"{path} crew block carries name or invalid uid where party uid belongs: {invalid}"
        )
    return values


def validate_crew_resolution(root: Path) -> None:
    root = Path(root).resolve()
    gp = _load_module(
        root / "vault" / "tools" / "lib" / "governed_path.py", "governed_path_validate"
    )
    parties = _registry_party_uids(root, gp)
    # v1.95 Spine A AC5 D3: only accepted companions exist, so the pairing
    # expectation follows the PRESENT set — Cal alone pairs with Po only.
    present = {
        spec["slug"]: found
        for spec in COMPANIONS
        if (found := _find_unified_entry(root, spec["slug"])) is not None
    }
    required = {"po", *present}
    missing = sorted(required - set(parties))
    if missing:
        raise CompanionGenesisError(f"registry lacks party identities for: {', '.join(missing)}")
    po_path, _ = _po_target(root, gp)
    expectations = [(po_path, {parties[slug] for slug in present})]
    for slug, (path, _) in present.items():
        expectations.append(
            (path, {parties["po"], *(parties[peer] for peer in present if peer != slug)})
        )
    for path, expected in expectations:
        actual = set(_crew_values(path, gp, len(expected)))
        if actual != expected:
            raise CompanionGenesisError(
                f"{path} crew parties {sorted(actual)} do not equal {sorted(expected)}"
            )


def genesis(
    root: Path,
    *,
    accept: tuple[str, ...] = ("cal", "darin"),
    po_only: bool = False,
    write_po_crew: bool = True,
) -> dict[str, Any]:
    root = Path(root).resolve()
    template_root = root / "vault" / "templates" / "companions"
    if not template_root.is_dir():
        raise CompanionGenesisError(
            f"shipped companion template directory is absent: {template_root}"
        )
    mint = _load_module(root / "vault" / "tools" / "tropo-mint-id.py", "mint")
    gp = _load_module(root / "vault" / "tools" / "lib" / "governed_path.py", "governed_path")

    # v1.95 Spine A AC5 (f015de6b3a18): the interim identity mint that stood
    # here is REMOVED. Genesis has already run by the time a companion is
    # offered — Po runs the first-boot rebuild in her greeting (AC2) and it
    # mints the manifest — so a Studio with no manifest at this point is a
    # Studio that skipped its own genesis, and minting one here would be the
    # side-effect identity the whole spine exists to end. Refuse and name the
    # cure; never mint.
    identity_manifest = root / ".tropo" / "studio-identity.md"
    if not identity_manifest.exists():
        raise CompanionGenesisError(
            "no studio-identity manifest at %s — this Studio has not run genesis. "
            "Companions are offered after Po's first greeting, which runs "
            "`python3 vault/tools/tropo-rebuild-index.py --apply --vault-path .` "
            "and mints the identity; run that first (v1.95 Spine A AC2/AC5)."
            % identity_manifest)
    mint.read_studio_identity(root=root)
    studio_identity_created = False

    # v1.95 Spine A AC5 (Mike: "cure and cut candidate #3"). D2: `--po` mints
    # Po's own party identity alone, at step 0b, so `--as po` resolves before
    # the offer is written. D3: only the ACCEPTED companion(s) materialise.
    selected = () if po_only else tuple(
        spec for spec in COMPANIONS if spec["slug"] in set(accept)
    )
    if not po_only and not selected:
        raise CompanionGenesisError("no companion accepted; choose cal, darin, or both")
    po_registry_hit = _registry_identity(root, "po", gp)
    if po_registry_hit is not None:
        # A Studio that already commissioned Po (real, customer-authored
        # identity) — touch only her crew block, never her identity or
        # charter body (Argus A165's ruling evt_b51c083be28ac6fe_00000344).
        po_target_path, po_party_uid = _po_target(root, gp)
        if po_only:
            # Presence is the answer (same shape as `tropo-mint-id --founder`).
            return {
                "schema": "tropo.companion-genesis/v1",
                "po_already_present": True,
                "po_party_uid": po_party_uid,
                "message": f"Po already present ({po_party_uid}); nothing minted",
            }
        specs = list(selected)
    else:
        # Cold box: no Po anywhere. She ships as a placeholder companion,
        # identical in kind to Cal and Darin — minted locally, never carrying
        # any real Studio's concrete identity.
        po_target_path = None
        po_party_uid = None
        specs = [*selected, PO_SPEC]
    # D3: a born companion is OWNED by the founder principal (AC4's uid),
    # found presence-first through the mint tool's own helper. No founder
    # means §1.5 has not run; refuse before anything is written.
    founder_uid = mint._human_principal_uid(root)
    if selected and not founder_uid:
        raise CompanionGenesisError(
            "no founder principal in vault/files (type: principal, "
            "principal_class: human) — a companion is owned by the founder, so "
            "§1.5 must run first: name the Studio, then "
            "`python3 vault/tools/tropo-mint-id.py --founder \"<name>\"`, then "
            "offer (v1.95 Spine A AC4/AC5). Nothing was written."
        )
    owner = founder_uid or "studio-owner"

    existing = {
        spec["slug"]: _identity_from_entry(root, spec["slug"], gp)
        for spec in specs
    }
    reserved = {
        value
        for identity in existing.values()
        if identity is not None
        for value in identity.values()
    }
    new_slugs = [spec["slug"] for spec in specs if existing[spec["slug"]] is None]
    minted = mint.mint(
        len(new_slugs) * 3,
        kind="agent",
        studio_root=root,
        extra_existing=reserved,
        minted_by="companion-genesis",
    ) if new_slugs else []
    cursor = 0
    identities: dict[str, dict[str, str]] = {}
    for spec in specs:
        slug = spec["slug"]
        if existing[slug] is not None:
            identities[slug] = existing[slug] or {}
            continue
        identities[slug] = {
            "uid": minted[cursor],
            "party_uid": minted[cursor + 1],
            "agent_root_uid": minted[cursor + 2],
        }
        cursor += 3
    if po_party_uid is None:
        # Cold-minted this run: resolve the party uid just assigned above so
        # Cal's and Darin's own templates can reference her, same as they
        # would a pre-existing customer Po.
        po_party_uid = identities["po"]["party_uid"]
    # D3: the PRESENT companion set — this run's plus any born earlier — so
    # every crew block names exactly who exists, never a placeholder.
    peers: dict[str, str] = {}
    for spec in COMPANIONS:
        found = identities.get(spec["slug"]) or _identity_from_entry(root, spec["slug"], gp)
        if found:
            peers[spec["slug"]] = found["party_uid"]

    today = dt.date.today().isoformat()
    agent_capsule_uid = _agent_capsule_uid(root, gp)
    created_paths: list[str] = []
    pointer_updates: list[str] = []

    for spec in specs:
        slug = spec["slug"]
        identity = identities[slug]
        created = _entry_created(root, slug, today)
        values = {
            **identity,
            "created": created,
            "agent_capsule_uid": agent_capsule_uid,
            "po_party_uid": po_party_uid,
            "cal_party_uid": peers.get("cal", ""),
            "darin_party_uid": peers.get("darin", ""),
            # D3: the unified charter is the third owner site (Vela's AC5
            # record f0157550b31b: it carried no owner at all).
            "owner": owner,
        }
        principal = root / "vault" / "files" / f"{identity['party_uid']}.md"
        if _write_if_absent(principal, _principal_record(spec, identity, today, owner)):
            created_paths.append(principal.relative_to(root).as_posix())
        agent_root = root / "vault" / "files" / f"{identity['agent_root_uid']}.md"
        if _write_if_absent(agent_root, _agent_root_record(spec, identity, today, owner)):
            created_paths.append(agent_root.relative_to(root).as_posix())
        unified = root / "vault" / "agents" / f"{identity['uid']}.md"
        rendered = _render(template_root / f"{slug}.md", values)
        if _write_if_absent(unified, rendered.encode("utf-8")):
            created_paths.append(unified.relative_to(root).as_posix())

        pointer_values = {
            "slug": slug,
            "role": spec["role"],
            "role_lower": spec["role"].lower(),
            "display_name": spec["display_name"],
            "generation_prefix": spec["generation_prefix"],
            "agent_uid": identity["uid"],
            "party_uid": identity["party_uid"],
            "agent_root_uid": identity["agent_root_uid"],
            "created": created,
        }
        pointer = root / "agents" / slug / f"{slug}-activation.md"
        pointer_text = _render(template_root / "activation-pointer.md", pointer_values)
        old_pointer = pointer.read_bytes() if pointer.is_file() else None
        pointer_bytes = pointer_text.encode("utf-8")
        if old_pointer != pointer_bytes:
            _atomic_write(pointer, pointer_bytes)
            pointer_updates.append(pointer.relative_to(root).as_posix())

        created_paths.extend(_materialize_memory(root, template_root, spec))
        for directory in (
            root / "agents" / slug / "transfers",
            root / "agents" / slug / "reflections",
        ):
            directory.mkdir(parents=True, exist_ok=True)

    # Register only after the identity-bearing files exist. If a process dies
    # before this point, the next run recovers the already-minted values from
    # the unified entries and completes the missing artifact; it never mints a
    # second party behind an already-published registry row.
    registry_changed = _append_registry_rows(root, identities, specs=specs)

    # D3: crew blocks name the PRESENT set. Each companion — this run's and
    # any born earlier — pairs with the other present companion(s) and Po;
    # Po pairs with whoever exists. An unchanged block is not rewritten.
    crew_updates: list[str] = []
    for slug in peers:
        found = _find_unified_entry(root, slug)
        if found is None:
            continue
        block = _crew_block(
            [(peers[peer], CREW_RELATIONSHIPS[peer]) for peer in peers if peer != slug]
            + [(po_party_uid, CREW_RELATIONSHIPS["po"])]
        )
        if _update_crew_section(found[0], block):
            crew_updates.append(found[0].relative_to(root).as_posix())
    po_path = po_target_path or root / "vault" / "agents" / f"{identities['po']['uid']}.md"
    if write_po_crew:
        # Back-write Po's crew block into her own charter (a pre-existing real
        # Po) or her freshly rendered entry (a cold-minted one).
        po_changed = _update_crew_section(
            po_path,
            _crew_block([(uid, CREW_RELATIONSHIPS[slug]) for slug, uid in peers.items()]),
        )
    else:
        po_changed = False

    births = [spec["slug"] for spec in specs if _ensure_lineage(root, spec)]
    validate_crew_resolution(root)
    # D3: the birth on the bus IS the acceptance record — one
    # tropo.agent.activated per companion born THIS run (never Po, never twice).
    activated = {
        spec["slug"]: _emit_activated(root, spec, identities[spec["slug"]], founder_uid)
        for spec in selected
        if spec["slug"] in births
    }
    return {
        "schema": "tropo.companion-genesis/v1",
        "studio_identity_created": studio_identity_created,
        "registry_changed": registry_changed,
        "po_crew_changed": po_changed,
        "crew_updates": sorted(crew_updates),
        "created_paths": sorted(created_paths),
        "pointer_updates": sorted(pointer_updates),
        "births": births,
        "accepted": [spec["slug"] for spec in selected],
        "founder_principal_uid": founder_uid,
        "activated": activated,
        "companions": identities,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize the accepted companion(s) from shipped templates, minting "
            "every identity locally in the target Studio; --po mints Po alone."
        )
    )
    parser.add_argument(
        "--studio",
        default=str(Path(__file__).resolve().parents[2]),
        help="Studio root; defaults to the package containing this tool",
    )
    parser.add_argument(
        "--po",
        action="store_true",
        help=(
            "step 0b: mint Po's own party identity (registry row + unified entry) "
            "and nothing else, so `--as po` resolves before the offer; idempotent"
        ),
    )
    parser.add_argument(
        "--accept",
        default=None,
        metavar="cal|darin|cal,darin",
        help=(
            "§1.5c: materialise only the accepted companion(s), owned by the "
            "founder principal; required unless --po"
        ),
    )
    args = parser.parse_args(argv)
    if args.po and args.accept:
        parser.error("--po and --accept are separate gestures (step 0b, then §1.5c)")
    if not args.po and not args.accept:
        parser.error("--accept cal|darin|cal,darin is required (or --po to mint Po alone)")
    accept = tuple(
        dict.fromkeys(part.strip().casefold() for part in (args.accept or "").split(",") if part.strip())
    )
    unknown = sorted(set(accept) - {spec["slug"] for spec in COMPANIONS})
    if unknown:
        parser.error(f"unknown companion(s): {', '.join(unknown)}; choose from cal, darin")
    try:
        result = genesis(Path(args.studio), accept=accept, po_only=args.po)
    except CompanionGenesisError as exc:
        print(f"COMPANION GENESIS REFUSED: {exc}", file=sys.stderr)
        return 1
    if result.get("message"):
        print(result["message"], file=sys.stderr)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
