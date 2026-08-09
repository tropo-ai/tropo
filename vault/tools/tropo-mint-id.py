#!/usr/bin/env python3
"""
---
uid: 5187be30
name: mint-id
type: tool
title: "mint-id — canonical collision-checked identifiers and typed governed births"
status: active
owner: argus
domain: "Identifier minting plus registry-bound human artifact birth through the canonical multi-surface transaction"
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-mint-id.py"
script_path: vault/tools/tropo-mint-id.py
spawnable_by:
  - all-executives
input:
  type: object
  properties:
    count: {type: integer, description: "how many identifiers to mint (default 1)"}
    reason: {type: string, description: "advisory note for the caller's own log (not persisted here)"}
    kind: {type: string, description: "identifier kind — file|agent (flat 8-hex, live) or studio (genesis manifest writer, live per 32067bea) or vault (short registered code, live per 943bb220) or event (declared in the ADR-050 contract, not yet built — raises NotImplementedError)"}
    segment: {type: string, description: "write segment (32067bea) — private (default, bare 8-hex) or team (studio-prefixed, reads the studio-identity manifest; fails loud if missing/corrupt)"}
    type_name: {type: string, description: "human-mintable governed type; every system-only binding refuses through the generic CLI"}
    list_types: {type: boolean, description: "list schema-v2 mint_mode=human bindings only"}
    author: {type: string, description: "writer label; registered agent-generation labels require activation provenance"}
    activation_uid: {type: string, description: "activation provenance UID; defaults from TROPO_ACTIVATION_UID"}
output:
  type: object
  description: "one collision-checked identifier per line on stdout; --type also atomically creates the governed artifact and reports its path on stderr"
created: 2026-06-02
created_by: argus-a93
modified: '2026-08-03'
modified_by: argus-a144
version: "2.3"
v2_0_amendment_note: "Talos T25 2026-07-06, dev-spec 796d9330 (ADR-050 cb0f8e46 step 1). Renamed mint-uid -> mint-id (belt mint-uid->mint-id) — the tool now mints identifiers generally, not only file UIDs. Added --kind {file,agent,vault,studio,event} per ADR-050 Decision 3: file/agent are the live flat-8-hex shape (identical collision domain — Decision 2's identifier != identity split means 'agent' here is a handle shape, not the governed agent entity); vault/studio/event are declared in the contract but stub NotImplementedError until their consumers exist (ADR-050 Decision 4c/4d). Added extra_existing= to mint() so the 3 partial-duplicator callers (40b2f455/9e7003b1/e337f1dd) can merge their in-session accumulated set into the collision check without reimplementing the mint loop. UID 5187be30 unchanged — the stable address; no caller link breaks."
v2_1_amendment_note: "Talos T25 2026-07-06, dev-spec 32067bea (Studio-Identity Primitive — Federation Phase A). --kind studio is now real: the idempotent genesis writer for a self-sovereign studio-identity manifest at .tropo/studio-identity.md (studio_id + short mint_prefix, minted once, never regenerated). Added --segment {private,team} (default private): a team-segment file/agent mint reads the manifest and produces <mint_prefix>-<8hex>; private stays bare 8-hex (unchanged default behavior). A missing/corrupt manifest on a team-segment mint raises StudioIdentityError — fails loud, never falls back to a silent bare or fabricated identity (AC5). 'studio' moved file/agent -> _IMPLEMENTED_KINDS; vault/event remain declared-not-built per ADR-050 Decision 4d."
v2_2_amendment_note: "Talos T25 2026-07-07, dev-spec 943bb220 (vault.capsule forge, ADR-051 Fork 1 / ADR-050 Decision 4c). --kind vault is now real: mints a fresh, collision-checked SHORT REGISTERED CODE (4-6 lowercase alnum) per ADR-050 Decision 3 ('vault/studio = short registered code' — explicitly NOT the flat-8-hex file/agent shape). Shares its shape-generation helper (_generate_short_code) with the studio mint_prefix generator (judgment call, named in 943bb220's build report: same SHAPE contract reused, no shared STATE — a vault code and a studio's own mint_prefix are minted independently and a fresh vault code is also checked against this studio's own mint_prefix, if one exists, so a composed <studio_prefix>-<vault_code> identifier can never self-collide). Unlike 'studio' (idempotent genesis writer, exactly one per studio), 'vault' mints like file/agent: any count >= 1, no manifest file written here — Fork 2 (the per-vault-root manifest governed-write-gate) is a named downstream dependency, not owned by this build. 'vault' moved file/agent/studio -> _IMPLEMENTED_KINDS; 'event' remains declared-not-built per ADR-050 Decision 4d (a different, monotonic collision model)."
governed_by: d5e1b4a3
member_of:
  - "8dd772a0"
schema_version: 2
belt: true
extraction_scope: ship
trigger_description: "Mint a bare collision-checked identifier, list human typed bindings, or atomically birth a registry-bound human artifact."
belt_invocation: "python3 vault/tools/tropo-mint-id.py"
belt_example: "python3 vault/tools/tropo-mint-id.py --count 5 --kind file"
---
"""


# mint-id — the canonical, collision-checked identifier minter (ADR-050 chokepoint).
#
# WHY THIS EXISTS (Argus A93 2026-06-02, per Mike-A93 directive): minting a UID was a
# DISCIPLINARY surface — every agent rolled its own `secrets.token_hex(4)` one-liner, and
# most did NOT collision-check. A survey found the pattern duplicated across ~9 tools
# (e337f1dd, 9e7003b1, 40b2f455, 4beff0d6, 1056eec5, 6342d0ca, b3f9d7e2, bf886f30,
# ce9dbcc2). This is the Disciplinary->Structural law (2bc33c0f) applied: one gesture,
# correct by construction (always collision-checked against everywhere UIDs live).
#
# CHOKEPOINT CLOSED (Talos T25, 2026-07-06, dev-spec 796d9330 / ADR-050 cb0f8e46): the 6
# real bypasses (tropo-import-walker, tropo-export, 6342d0ca, tropo-register-kernel,
# tropo-register-template, 4beff0d6) now route through mint() via a dynamic
# spec_from_file_location import (module names can't start with a digit / contain
# hyphens). The 3 partial-duplicators (40b2f455, 9e7003b1, e337f1dd) delegate their
# mint_uid(existing) helper to mint(1, extra_existing=existing)[0] instead of
# reimplementing the collision loop. `check_mint_id_chokepoint` (tropo-validate.py)
# enforces no NEW raw token_hex(4) bypass survives (WARN, ERROR-ratchet after first
# clean pass), proven by an adversarial plant in test_capability_chain_smoke.py.
#
# IDENTIFIER != IDENTITY (ADR-050 Decision 2): this service mints opaque, typed HANDLES.
# It does not assemble the governed entity behind a handle (an agent's charter/soul/
# memory/lineage; a vault's governance) — that stays with the owning governed process
# (activation playbooks, capsules, state machines). `--kind agent` returns the same
# flat-8-hex shape as `--kind file`; it exists so callers can express INTENT and so the
# vault/studio/event kinds have a coherent home when their consumers exist.
#
# FEDERATION EXTENSION POINT (Federation Foundation 7cac6473 / brainstorm a1230aff): a
# federated, multi-Studio mint must be PREFIX-AWARE (Studio-Prefixed UIDs) so two laptops
# minting offline cannot collide. The `--prefix <studio>` SEAM IS IMPLEMENTED (S8, v1.80):
# output is `<prefix>-<8hex>` per the decided `[studio]-[random]` shape (d89b5da3).
#
# STUDIO-IDENTITY PRIMITIVE BUILT (Talos T25, 2026-07-06, dev-spec 32067bea / Federation
# Phase A): `--kind studio` is the idempotent GENESIS gesture — mints a self-sovereign
# studio_id + short mint_prefix locally (no HQ call) and writes the manifest at
# `.tropo/studio-identity.md`. Re-running it never regenerates; it reads + returns the
# existing identity. This is the PRIMITIVE that now feeds the `--prefix` seam for real:
# `--segment team` reads the manifest and mints `<mint_prefix>-<8hex>`; `--segment private`
# (the default) stays bare 8-hex, unchanged from today's behavior. A missing/corrupt
# manifest on a team-segment mint raises `StudioIdentityError` — FAILS LOUD, never falls
# back to a silent bare or fabricated identity (that would defeat the collision-safety the
# prefix exists to guarantee). Cross-Studio N-member collision checking at team-JOIN time
# (Federation Phase B) and the `teams/<uid>/` segment-storage mount (Phase C) are explicitly
# OUT of scope here — this primitive only answers "what is MY studio's identity."

# VAULT.CAPSULE FORGE BUILT (Talos T25, 2026-07-07, dev-spec 943bb220 / ADR-051 Fork 1): --kind
# vault is the identifier side of the forge (the capsule/schema side lives in
# vault/capsules/tropo-vault.capsule.md). Per ADR-050 Decision 3 ("vault/studio = short
# registered code," a DIFFERENT collision domain from file/agent's flat 8-hex) a vault mint
# returns a fresh 4-6 lowercase-alnum code, not an 8-hex UID — do not assume the flat shape.
# Unlike `studio` (an idempotent, exactly-once genesis writer), `vault` mints like file/agent:
# every call returns `count` FRESH codes; nothing is written to disk here (a vault's own
# per-vault-root manifest write is Fork 2, a named downstream dependency, not this build's
# job — 943bb220 §"Where instances live"). The shape-generator is shared with the studio
# mint_prefix generator (a deliberate, named judgment call: same SHAPE contract, no shared
# STATE) and a fresh vault code is also checked against THIS studio's own mint_prefix (when
# a studio-identity manifest exists) so a composed `<studio_prefix>-<vault_code>` federated
# identifier can never self-collide.

from __future__ import annotations
import argparse
import contextlib
import datetime as _dt
import importlib.util
import io
import json
import os
import re
import secrets
import sqlite3
import stat
import sys
import tempfile
import time
from pathlib import Path

import yaml

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
INDEX = VAULT_ROOT / "vault" / "00-index.jsonl"
ARCHIVE_INDEX = VAULT_ROOT / "vault" / "00-archive-index.jsonl"
STUDIO_IDENTITY_REL = Path(".tropo") / "studio-identity.md"

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from lib import template_leg  # noqa: E402 -- must follow the sys.path insert above

_HEX8 = re.compile(r"^[0-9a-f]{8}$")
_INDEX_UID = re.compile(r'"uid"\s*:\s*"([0-9a-f]{8})"')
_MINT_PREFIX_SHAPE = re.compile(r"^[a-z0-9]{4,6}$")

# ADR-050 Decision 3 — the typed-kind contract. file/agent share the flat-8-hex shape
# (identifier != identity: "agent" here is a handle shape, not the governed entity).
# `studio` (dev-spec 32067bea) and `vault` (dev-spec 943bb220) are now implemented — both
# are "short registered code" shape (4-6 lowercase alnum), a DIFFERENT collision domain
# from file/agent's flat 8-hex (ADR-050 Decision 3). `event` is still DECLARED (so the
# contract is stable + callers can name intent early) but stubs NotImplementedError until
# its consumer exists (ADR-050 Decision 4d) — it is a monotonic max+1 sequence, a different
# collision model again, and must not be built speculatively.
VALID_KINDS = ("file", "agent", "vault", "studio", "event")
_IMPLEMENTED_KINDS = frozenset({"file", "agent", "studio", "vault"})

# Types whose capsule carries a §Template leg but which the GENERIC door must not
# open. `activation` is the record of an identity being issued: the writer has to
# own the generation counter, the lineage read and the findings, none of which a
# type-agnostic mint can do. Two writers for one lifecycle fact is rule 7's
# divergence at its most expensive (40b13b5b) -- the shape pipelines already have,
# where e337f1dd.py hand-writes activation frontmatter as an f-string. The leg
# still exists so the record shape has one authored home; only this door is shut.
_SYSTEM_ONLY_TYPES = {
    "activation": "python3 vault/tools/tropo-activate.py --agent <slug> --authorized-by <principal>",
}
_MANIFEST_SCHEMA_VERSION = 1
_REQUIRED_MANIFEST_FIELDS = (
    "studio_id", "mint_prefix", "created", "minted_by", "hq_registered", "schema_version",
)
# d89b5da3 §"Open option": tropo- is a reserved namespace for canonical OS substrate;
# a locally-minted studio must never accidentally claim it.
_RESERVED_MINT_PREFIXES = frozenset({"tropo"})

# Tests override this (see set_studio_root) so fixtures never touch the real studio's
# manifest. Mirrors the lib.tropo_git_history.set_repo_root pattern used elsewhere.
_STUDIO_ROOT_OVERRIDE: Path | None = None


def set_studio_root(path: Path | None) -> None:
    """Test seam: point studio-identity reads/writes at an isolated fixture root."""
    global _STUDIO_ROOT_OVERRIDE
    _STUDIO_ROOT_OVERRIDE = Path(path) if path is not None else None


def _effective_studio_root() -> Path:
    return _STUDIO_ROOT_OVERRIDE if _STUDIO_ROOT_OVERRIDE is not None else VAULT_ROOT


class StudioIdentityError(RuntimeError):
    """A team-segment mint could not find a valid studio-identity manifest.

    Dev-spec 32067bea AC5 (non-negotiable): fail LOUD on missing/corrupt — never fall
    back to a silent bare or fabricated identity for a team-segment write, which would
    defeat the collision-safety the studio prefix exists to guarantee.
    """


def _studio_identity_path(root: Path | None = None) -> Path:
    return (root if root is not None else _effective_studio_root()) / STUDIO_IDENTITY_REL


def read_studio_identity(root: Path | None = None) -> dict:
    """Read + structurally validate the studio-identity manifest.

    Raises StudioIdentityError (never returns a partial/fabricated dict) when the
    manifest is missing, unreadable, not valid YAML frontmatter, missing a required
    field, or carries a malformed studio_id/mint_prefix shape.
    """
    path = _studio_identity_path(root)
    if not path.exists():
        raise StudioIdentityError(
            f"studio-identity manifest not found at {path} — a team-segment mint requires "
            f"a genesis identity first; run `tropo-mint-id --kind studio`."
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise StudioIdentityError(f"studio-identity manifest at {path} could not be read: {e}") from e
    if not text.startswith("---"):
        raise StudioIdentityError(
            f"studio-identity manifest at {path} is corrupt: missing YAML frontmatter delimiter"
        )
    rest = text[3:]
    end_idx = rest.find("\n---")
    if end_idx == -1:
        raise StudioIdentityError(
            f"studio-identity manifest at {path} is corrupt: unterminated frontmatter block"
        )
    raw_fm = rest[:end_idx]
    try:
        data = yaml.safe_load(raw_fm)
    except yaml.YAMLError as e:
        raise StudioIdentityError(f"studio-identity manifest at {path} is corrupt: invalid YAML ({e})") from e
    if not isinstance(data, dict):
        raise StudioIdentityError(f"studio-identity manifest at {path} is corrupt: frontmatter is not a mapping")
    missing = [f for f in _REQUIRED_MANIFEST_FIELDS if f not in data]
    if missing:
        raise StudioIdentityError(
            f"studio-identity manifest at {path} is corrupt: missing field(s) {missing}"
        )
    if not _HEX8.match(str(data["studio_id"])):
        raise StudioIdentityError(
            f"studio-identity manifest at {path} is corrupt: studio_id {data['studio_id']!r} is not 8-hex"
        )
    if not _MINT_PREFIX_SHAPE.match(str(data["mint_prefix"])):
        raise StudioIdentityError(
            f"studio-identity manifest at {path} is corrupt: mint_prefix {data['mint_prefix']!r} "
            f"is not 4-6 lowercase alphanumeric chars (d89b5da3 bound)"
        )
    return data


def _generate_mint_prefix() -> str:
    """A short (4-6 char), lowercase-alnum studio prefix. d89b5da3: "short, stable" —
    bounded so it doesn't blow up human-navigation/parse cost the way a full 8-hex would.
    Collision-checked only against the reserved namespace (`tropo-`): a studio mints its
    own prefix exactly once at genesis, so there is no local peer set to check against;
    cross-Studio uniqueness is Federation Phase B (team-join N-member check), out of
    scope here per the dev-spec.

    Delegates to `_generate_short_code` (943bb220) — same shape contract `vault` now
    also uses; kept as its own named function since callers (this module's tests
    included) reference `_generate_mint_prefix` by name.
    """
    return _generate_short_code(set())


def _generate_short_code(existing: set[str]) -> str:
    """A short (4-6 char), lowercase-alnum registered code — the shape ADR-050 Decision 3
    names for BOTH `studio` and `vault` kinds ("vault/studio = short registered code"),
    distinct from file/agent's flat 8-hex. Shared shape-generation helper: `studio`'s
    mint_prefix and `vault`'s code are minted independently (no shared state) but must
    never collide with EACH OTHER or the reserved `tropo-` namespace, since a federated
    identifier may compose both (e.g. `<studio_prefix>-<vault_code>-<8hex>`).

    `existing` is the caller-supplied exclusion set (e.g. this studio's own mint_prefix,
    plus any extra_existing codes already minted this session) — this helper has no
    disk-scan of its own; callers assemble `existing` per their own collision domain.
    """
    for _attempt in range(64):
        candidate = secrets.token_hex(3)[:5]
        if candidate not in _RESERVED_MINT_PREFIXES and candidate not in existing:
            return candidate
    raise RuntimeError("short-code collision storm — could not generate in 64 tries")


def mint_studio_identity(root: Path | None = None, minted_by: str = "tropo-mint-id") -> dict:
    """The genesis gesture (dev-spec 32067bea): self-sovereign, mints locally, no HQ call.

    Idempotent — if a manifest already exists it is read + returned UNCHANGED (the
    mint_prefix is stable once set and never silently regenerated). Only the first call
    on a fresh studio actually mints; every subsequent call is a no-op read.
    """
    path = _studio_identity_path(root)
    if path.exists():
        return read_studio_identity(root)
    studio_id = secrets.token_hex(4)
    mint_prefix = _generate_mint_prefix()
    data = {
        "studio_id": studio_id,
        "mint_prefix": mint_prefix,
        "created": _dt.date.today().isoformat(),
        "minted_by": minted_by,
        "hq_registered": False,
        "schema_version": _MANIFEST_SCHEMA_VERSION,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    body = (
        "\n# Studio Identity\n\n"
        "Self-sovereign studio-identity manifest — mints locally at genesis, no HQ call\n"
        "(dev-spec [32067bea], Federation Phase A; composes [ADR-050](../../vault/files/cb0f8e46.md)).\n"
        "`mint_prefix` is stable once set and never silently regenerated; a team-segment\n"
        "mint reads it to produce `<mint_prefix>-<8hex>`. Private-segment mints stay bare.\n"
        "`hq_registered: false` — HQ Studio Registration ([7cac6473]) is an optional later\n"
        "overlay on top of this primitive, never a prerequisite.\n"
    )
    path.write_text(f"---\n{fm_text}---\n{body}", encoding="utf-8")
    return data


def load_existing_uids() -> set[str]:
    """Every 8-hex UID currently in use — the index + the governed-file filenames.

    These are the two places a governed UID lives; the registries derive from the index.
    """
    uids: set[str] = set()
    # ADR-047 Layer 1: archived/superseded UIDs remain permanently in use.
    # Mint collision checks therefore opt into both disposable surfaces.
    for index_path in (INDEX, ARCHIVE_INDEX):
        if not index_path.exists():
            continue
        for line in index_path.read_text(encoding="utf-8").splitlines():
            m = _INDEX_UID.search(line)
            if m:
                uids.add(m.group(1))
    if VAULT_FILES.is_dir():
        for f in VAULT_FILES.glob("*.md"):
            if _HEX8.match(f.stem):
                uids.add(f.stem)
    return uids


def mint(count: int = 1, prefix: str = "", kind: str = "file",
          extra_existing: set[str] | None = None, segment: str = "private",
          studio_root: Path | None = None, minted_by: str = "tropo-mint-id") -> list[str]:
    """Return `count` fresh identifiers, each guaranteed not to collide with any in use.

    S8 (v1.80): optional `prefix` seam. When prefix is non-empty the returned token is
    ``{prefix}-{8hex}`` — a namespaced identifier for federation / vault-identity use. The
    8-hex portion still collides-checks against the in-use set (prefix is not part of
    the index scan, so the check is conservative and always safe). Grain-neutral by
    design: the seam does not care whether the prefix names a studio or a vault.

    v2.0 (796d9330 / ADR-050): `kind` types the identifier per Decision 3. `file`/`agent`
    mint the same flat-8-hex shape (identifier != identity — "agent" is a handle, not the
    governed entity). `vault`/`event` are declared in the contract but raise
    NotImplementedError — built when their consumers exist (Decision 4c/4d), never
    speculatively.

    v2.1 (32067bea, Federation Phase A): `kind="studio"` is the idempotent GENESIS
    writer — mints (or, on re-run, simply reads) the self-sovereign studio-identity
    manifest and returns `[studio_id]`. It ignores `segment`/`extra_existing` (there is
    exactly one studio identity) and rejects an explicit `prefix` (the mint_prefix is
    generated at genesis, not caller-supplied).

    v2.2 (943bb220, vault.capsule forge): `kind="vault"` mints `count` FRESH short
    registered codes (4-6 lowercase alnum — ADR-050 Decision 3's "vault/studio" shape,
    NOT the flat-8-hex file/agent shape). Unlike `studio`, this is not a once-per-studio
    genesis writer: every call mints anew (no manifest file is read or written here —
    the per-vault-root manifest write is Fork 2, a named downstream dependency). Each
    code is checked against `extra_existing` AND, if this studio already has a
    studio-identity manifest, against that studio's own `mint_prefix` (so a composed
    `<studio_prefix>-<vault_code>` federated identifier can never self-collide).
    Rejects an explicit `prefix` (a vault code is generated fresh, not caller-supplied)
    and ignores `segment` (vault codes have their own collision domain, not
    private/team-segment file/agent namespacing).

    `segment` is now segment-aware for `file`/`agent` mints: `"team"` reads the
    studio-identity manifest and mints `<mint_prefix>-<8hex>` (fails LOUD via
    StudioIdentityError if the manifest is missing/corrupt — AC5 of 32067bea); the
    default `"private"` stays bare 8-hex, identical to pre-32067bea behavior. An
    explicit `prefix` and `segment="team"` together is rejected — the manifest is the
    only source of a team-segment prefix, not a caller-supplied override.

    `extra_existing`: an optional caller-supplied set of already-minted-but-not-yet-
    written-to-disk UIDs to also treat as taken (for the 3 partial-duplicator callers'
    session-accumulated sets — 40b2f455/9e7003b1/e337f1dd) — merged with the disk scan,
    never replacing it.

    `studio_root`: test seam — overrides where the studio-identity manifest is read
    from/written to for this call only (production callers never pass this; it defaults
    to the real studio root / the `set_studio_root` override).
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown kind {kind!r}; must be one of {VALID_KINDS}")
    if kind not in _IMPLEMENTED_KINDS:
        raise NotImplementedError(
            f"kind={kind!r} is declared in the ADR-050 contract but not yet built — "
            f"built when its consumer exists (ADR-050 cb0f8e46 Decision 4c/4d), never speculatively."
        )
    if kind == "studio":
        if count != 1:
            raise ValueError("kind='studio' mints exactly one identity per call (count must be 1)")
        if prefix:
            raise ValueError(
                "kind='studio' does not accept an explicit prefix — mint_prefix is generated "
                "at genesis and stable thereafter; pass nothing and re-run to read it back."
            )
        identity = mint_studio_identity(root=studio_root, minted_by=minted_by)
        return [identity["studio_id"]]
    if kind == "vault":
        if prefix:
            raise ValueError(
                "kind='vault' does not accept an explicit prefix — the vault code is "
                "generated fresh each mint, like kind='studio''s mint_prefix."
            )
        if count < 1:
            raise ValueError("count must be >= 1")
        existing_codes: set[str] = set(extra_existing) if extra_existing else set()
        try:
            existing_codes.add(read_studio_identity(root=studio_root)["mint_prefix"])
        except StudioIdentityError:
            pass  # no studio-identity manifest yet — nothing to disjoint-check against
        out_codes: list[str] = []
        for _ in range(count):
            code = _generate_short_code(existing_codes)
            existing_codes.add(code)
            out_codes.append(code)
        return out_codes
    if segment not in ("private", "team"):
        raise ValueError(f"unknown segment {segment!r}; must be 'private' or 'team'")
    effective_prefix = prefix
    if segment == "team":
        if prefix:
            raise ValueError(
                "segment='team' derives its prefix from the studio-identity manifest — "
                "do not also pass an explicit prefix."
            )
        identity = read_studio_identity(root=studio_root)  # fails LOUD on missing/corrupt (AC5)
        effective_prefix = identity["mint_prefix"]
    if count < 1:
        raise ValueError("count must be >= 1")
    existing = load_existing_uids()
    if extra_existing:
        existing = existing | set(extra_existing)
    out: list[str] = []
    for _ in range(count):
        for _attempt in range(64):
            candidate = secrets.token_hex(4)
            if candidate not in existing:
                existing.add(candidate)
                out.append(f"{effective_prefix}-{candidate}" if effective_prefix else candidate)
                break
        else:
            raise RuntimeError("UID collision storm — could not mint a free 8-hex in 64 tries")
    return out


def _derived_uid_present(root: Path, uid: str) -> bool:
    for path in (
        root / "vault" / "00-index.jsonl",
        root / "vault" / "00-archive-index.jsonl",
    ):
        if not path.is_file():
            continue
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                row = json.loads(raw)
                if isinstance(row, dict) and row.get("uid") == uid:
                    return True
        except (OSError, UnicodeError, json.JSONDecodeError):
            return True
    sqlite_path = root / "vault" / "00-index.sqlite"
    if sqlite_path.is_file():
        try:
            with sqlite3.connect(str(sqlite_path)) as conn:
                if conn.execute(
                    "SELECT 1 FROM entries WHERE uid = ? LIMIT 1", (uid,)
                ).fetchone():
                    return True
        except sqlite3.Error:
            return True
    return False


def _rollback_minted_birth(
    freshener,
    root: Path,
    uid: str,
    out_path: Path,
) -> str | None:
    """Remove a committed source and its derived rows after failed verification."""
    try:
        out_path.unlink(missing_ok=True)
    except OSError as exc:
        return f"could not remove minted source {out_path}: {exc}"
    if not _derived_uid_present(root, uid):
        return None
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = freshener.remove_many((uid,), root)
    except Exception as exc:
        return f"derived-row rollback could not complete: {exc}"
    if code != 0:
        diagnostic = (stderr.getvalue() or stdout.getvalue()).strip()
        return f"derived-row rollback exited {code}" + (
            f": {diagnostic}" if diagnostic else ""
        )
    if _derived_uid_present(root, uid):
        return f"derived-row rollback returned success but UID {uid} is still indexed"
    return None


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        tmp_path.unlink(missing_ok=True)


def _verify_minted_index_row(
    root: Path,
    uid: str,
    out_path: Path,
    type_name: str,
) -> None:
    """Require the minted identity on both current index surfaces.

    A zero freshen exit is necessary but not sufficient: the birth gesture may
    report success only when the exact UID/path/type identity is visible in the
    current JSONL projection and SQLite row.
    """
    try:
        expected_path = out_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"minted path {out_path} escapes studio root {root}") from exc

    current_path = root / "vault" / "00-index.jsonl"
    if not current_path.is_file():
        raise RuntimeError(f"current JSONL index is missing at {current_path}")
    jsonl_matches: list[dict] = []
    try:
        for line_number, raw in enumerate(
            current_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"current JSONL index has invalid JSON on line {line_number}"
                ) from exc
            if isinstance(row, dict) and row.get("uid") == uid:
                jsonl_matches.append(row)
    except OSError as exc:
        raise RuntimeError(f"current JSONL index cannot be read: {exc}") from exc

    if len(jsonl_matches) != 1:
        raise RuntimeError(
            f"current JSONL index has {len(jsonl_matches)} rows for minted UID {uid}; "
            "expected exactly one"
        )
    expected_identity = {
        "uid": uid,
        "path": expected_path,
        "type": type_name,
    }
    jsonl_identity = {
        field: jsonl_matches[0].get(field) for field in expected_identity
    }
    if jsonl_identity != expected_identity:
        raise RuntimeError(
            f"current JSONL identity {jsonl_identity!r} does not match "
            f"{expected_identity!r}"
        )

    sqlite_path = root / "vault" / "00-index.sqlite"
    if not sqlite_path.is_file():
        raise RuntimeError(f"SQLite index is missing at {sqlite_path}")
    try:
        with sqlite3.connect(str(sqlite_path)) as conn:
            sqlite_row = conn.execute(
                "SELECT fm_json FROM entries WHERE uid = ?",
                (uid,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise RuntimeError(f"SQLite index lookup failed: {exc}") from exc
    if sqlite_row is None:
        raise RuntimeError(f"SQLite index has no row for minted UID {uid}")
    try:
        sqlite_record = json.loads(sqlite_row[0])
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"SQLite fm_json for minted UID {uid} is invalid") from exc
    sqlite_identity = {
        field: sqlite_record.get(field) for field in expected_identity
    }
    if sqlite_identity != expected_identity:
        raise RuntimeError(
            f"SQLite identity {sqlite_identity!r} does not match "
            f"{expected_identity!r}"
        )


def _registered_agent_generation(
    root: Path, author: str
) -> tuple[str, str] | None:
    """Resolve a registered agent-generation author to (agent slug, generation)."""
    registry_rel = Path(".tropo-studio/registries/agent-registry.yaml")
    registry = root / registry_rel
    if not registry.exists() and not registry.is_symlink():
        return None
    try:
        registry = template_leg._strict_regular_file(
            root, registry_rel, "agent registry"
        )
        value = yaml.safe_load(registry.read_text(encoding="utf-8"))
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        template_leg.TemplateLegError,
    ) as exc:
        raise RuntimeError(f"agent registry cannot be read for mint provenance: {exc}") from exc
    agents = value.get("agents") if isinstance(value, dict) else None
    if not isinstance(agents, dict):
        raise RuntimeError("agent registry has no agents mapping for mint provenance")
    lowered = author.casefold()
    for row in agents.values():
        if not isinstance(row, dict) or row.get("type") != "agent":
            continue
        name = str(row.get("name") or "").strip()
        prefix = str(
            row.get("generation-prefix") or row.get("generation_prefix") or ""
        ).strip()
        if not name or not prefix:
            continue
        slug = re.sub(r"[^a-z0-9.]+", "-", name.casefold()).strip("-")
        match = re.fullmatch(
            rf"{re.escape(slug)}-{re.escape(prefix.casefold())}(\d+)",
            lowered,
        )
        if match:
            return slug, f"{prefix}{match.group(1)}"
    return None


def _indexed_activation_row(root: Path, activation_uid: str) -> dict:
    """Resolve one activation from exactly one current/archive index row."""
    matches: list[dict] = []
    for rel in (
        Path("vault/00-index.jsonl"),
        Path("vault/00-archive-index.jsonl"),
    ):
        path = root / rel
        if not path.exists() and not path.is_symlink():
            continue
        try:
            path = template_leg._strict_regular_file(root, rel, "vault index")
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError, template_leg.TemplateLegError) as exc:
            raise ValueError(
                f"cannot verify activation provenance against {rel}: {exc}"
            ) from exc
        for line_number, raw in enumerate(lines, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"cannot verify activation provenance: {rel} line "
                    f"{line_number} is invalid JSON"
                ) from exc
            if isinstance(row, dict) and row.get("uid") == activation_uid:
                matches.append(row)
    if len(matches) != 1:
        raise ValueError(
            f"activation provenance {activation_uid} must resolve to exactly one "
            f"current/archive index row; found {len(matches)}"
        )
    return matches[0]


def _lineage_records_birth(root: Path, agent: str, generation: str) -> bool:
    """True when ``agents/<agent>/lineage.jsonl`` records a birth for this generation.

    THE GATE'S QUESTION IS "IS THIS A REAL GENERATION OF A REAL AGENT", AND THE
    LINEAGE FILE IS NOW THE ONLY THING THAT ANSWERS IT.

    Until 2026-08-06 the only accepted proof was a ``type: activation`` entry.
    ``tropo-lineage.py`` then became the lifecycle and deliberately stopped
    creating those entries -- it touches no index, no mint, no card and no
    registry, because every birth this studio ever refused was refused by one
    of them. The proof this gate demanded became a record nothing produces, so
    the gate refused *every agent the lifecycle makes*: metis-g103, vela-v72,
    talos-t39 and orpheus-o35 all verified refused, and the predecessor's card
    is not a workaround because the generations do not match. Agents were
    hand-authoring governed artifacts around the tool, which is how a typed
    artifact drifts from its capsule (metis-g103, finding ea38581b -- itself
    hand-authored around this very refusal).

    Lineage cannot go stale against the lifecycle the way an activation entry
    did: the lifecycle is the only writer of this file. A malformed line
    elsewhere is skipped rather than fatal -- unlike ``tropo-lineage.py born``
    we are only asking whether a birth is recorded, never inventing a number
    from a file we cannot read, so a damaged unrelated line must not block a
    generation whose own birth line is perfectly readable.
    """
    rel = Path("agents") / agent / "lineage.jsonl"
    try:
        path = template_leg._strict_regular_file(root, rel, "agent lineage")
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, template_leg.TemplateLegError):
        return False
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(row, dict)
            and row.get("t") == "born"
            and str(row.get("gen") or "") == generation
        ):
            return True
    return False


def _resolve_activation_provenance(
    root: Path, author: str, activation_uid: str | None
) -> str | None:
    registered = _registered_agent_generation(root, author)
    if registered is None:
        return None
    agent, generation = registered
    if not activation_uid:
        # Lineage is the current proof. An explicit --activation-uid is still
        # honoured below, unchanged, so the 516 frozen activation entries and
        # any legacy caller keep working exactly as before.
        if _lineage_records_birth(root, agent, generation):
            return None
        raise ValueError(
            f"author {author!r} is a registered agent-generation label with no "
            f"birth recorded in agents/{agent}/lineage.jsonl; be born with "
            "`tropo-lineage.py born`, or provide --activation-uid or "
            "TROPO_ACTIVATION_UID for a pre-lineage generation"
        )
    if not _HEX8.fullmatch(activation_uid):
        raise ValueError("activation provenance UID must be exactly 8 lowercase hex")
    index_row = _indexed_activation_row(root, activation_uid)
    rel = Path("vault/files") / f"{activation_uid}.md"
    path = template_leg._strict_regular_file(
        root, rel, "activation provenance"
    )
    try:
        fm = template_leg._frontmatter_mapping(
            path.read_text(encoding="utf-8"), path
        )
    except (OSError, UnicodeError, template_leg.TemplateLegError) as exc:
        raise ValueError(f"activation provenance {activation_uid} is unreadable: {exc}") from exc
    expected = {
        "uid": activation_uid,
        "type": "activation",
        "agent": agent,
        "generation": generation,
    }
    source_actual = {field: str(fm.get(field) or "") for field in expected}
    indexed_actual = {
        field: str(index_row.get(field) or "") for field in expected
    }
    if source_actual != expected or indexed_actual != expected:
        raise ValueError(
            f"activation provenance {activation_uid} does not match author "
            f"{author!r}: expected {expected!r}, source {source_actual!r}, "
            f"index {indexed_actual!r}"
        )
    expected_path = rel.as_posix()
    if index_row.get("path") != expected_path:
        raise ValueError(
            f"activation provenance {activation_uid} is not indexed at its "
            f"canonical source {expected_path}"
        )
    source_status = str(fm.get("status") or "")
    index_status = str(index_row.get("status") or "")
    if source_status not in {"active", "retired"} or index_status != source_status:
        raise ValueError(
            f"activation provenance {activation_uid} must be active or retired "
            f"with matching source/index status; source={source_status!r}, "
            f"index={index_status!r}"
        )
    return activation_uid


def _validate_stamped_instance(
    text: str, *, uid: str, type_name: str, capsule_version: str
) -> None:
    try:
        fm = template_leg._frontmatter_mapping(text, Path(f"{uid}.md"))
    except template_leg.TemplateLegError as exc:
        raise ValueError(f"stamped instance is not valid YAML: {exc}") from exc
    expected = {
        "uid": uid,
        "type": type_name,
        "capsule_version": capsule_version,
    }
    actual = {field: fm.get(field) for field in expected}
    if actual != expected:
        raise ValueError(
            f"stamped instance identity mismatch: expected {expected!r}, "
            f"found {actual!r}"
        )
    stray = template_leg.find_stray_mint_tokens(text)
    if stray:
        raise ValueError(f"stamped instance retains mint token(s): {stray}")


def _scratch_output_dir(root: Path, requested: Path) -> Path:
    """Resolve a direct-write destination under an agent's approved workspace."""
    root = root.resolve(strict=True)
    candidate = requested if requested.is_absolute() else root / requested
    try:
        logical_rel = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("scratch output must stay inside the Studio root") from exc
    if ".." in logical_rel.parts:
        raise ValueError("scratch output path may not contain '..'")
    cursor = root
    for part in logical_rel.parts:
        cursor = cursor / part
        try:
            mode = cursor.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ValueError(f"scratch output path contains symlink {cursor}")
    resolved = candidate.resolve(strict=False)
    try:
        rel = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("scratch output must stay inside the Studio root") from exc
    parts = rel.parts
    if (
        len(parts) < 4
        or parts[0] != "agents"
        or not parts[1]
        or parts[2:4] != (".tropo-capsule", "workspace")
    ):
        raise ValueError(
            "output_dir must be inside the explicit approved Studio scratch root "
            "agents/<agent>/.tropo-capsule/workspace"
        )
    return resolved


def _load_rebuild_index(root: Path):
    rel = Path("vault/tools/tropo-rebuild-index.py")
    try:
        script = template_leg._strict_regular_file(
            root, rel, "canonical multi-surface freshener"
        )
    except template_leg.TemplateLegError as exc:
        raise RuntimeError(
            f"canonical multi-surface freshener is missing or unsafe at "
            f"{root / rel}: {exc}"
        ) from exc
    module_name = f"_typed_mint_rebuild_{abs(hash(str(script.resolve())))}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical freshener from {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def mint_file(
    type_name: str,
    *,
    author: str,
    activation_uid: str | None = None,
    output_dir: Path | None = None,
    studio_root: Path | None = None,
    freshen: bool = True,
) -> tuple[str, Path]:
    """Governed-cp birth from a registry-selected visible companion template.

    Resolve and byte-check the generated registry, select a human companion,
    validate provenance + exact tokens + stamped YAML, then stage canonical
    source bytes through freshen_many's existing multi-surface transaction.
    Embedded capsule §Template sections are never a mint fallback.

    `output_dir` is an explicit scratch-only override and therefore skips index
    freshening; it may not name the canonical One-Home directory.
    ``freshen=False`` is rejected unless this explicit scratch override is
    present. Without it, the selected capsule's ``mint_output_home`` binding
    wins. Every canonical route is freshened in-gesture.

    Raises template_leg.TemplateLegError (registry/type/binding refusal),
    lets mint()'s own exceptions propagate (collision storm, bad kind, etc),
    and raises RuntimeError only after rolling canonical source + derived rows
    back when freshening or exact index-row verification fails.
    """
    if type_name in _SYSTEM_ONLY_TYPES:
        raise ValueError(
            f"type {type_name!r} is system-only and is not mintable through the "
            f"generic door -- it is written by its own lifecycle tool alone: "
            f"{_SYSTEM_ONLY_TYPES[type_name]}"
        )
    if not freshen and output_dir is None:
        raise ValueError(
            "freshen=False is legal only with an explicit scratch output_dir; "
            "canonical governed birth must freshen and verify its exact index row"
        )

    logical_root = Path(studio_root if studio_root is not None else VAULT_ROOT)
    try:
        root_mode = logical_root.lstat().st_mode
    except OSError as exc:
        raise ValueError(f"Studio root cannot be inspected: {exc}") from exc
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise ValueError("Studio root must be a real directory, not a symlink")
    root = logical_root.resolve(strict=True)
    leg = template_leg.load_mint_template(root, type_name)
    if leg.output_home is None:
        raise template_leg.TemplateLegError(
            f"mint binding for {type_name!r} has no output home"
        )
    canonical_target_dir = template_leg._strict_directory(
        root, leg.output_home, "mint_output_home"
    )
    resolved_output_dir: Path | None = None
    if output_dir is not None:
        resolved_output_dir = _scratch_output_dir(root, Path(output_dir))

    provenance_uid = _resolve_activation_provenance(
        root, author, activation_uid
    )
    uid = mint(1, kind="file", studio_root=studio_root)[0]
    today = _dt.date.today().isoformat()
    instance_text = template_leg.stamp(
        leg,
        uid=uid,
        date=today,
        author=author,
        activation_uid=provenance_uid,
    )
    _validate_stamped_instance(
        instance_text,
        uid=uid,
        type_name=type_name,
        capsule_version=leg.capsule_version,
    )

    if output_dir is not None:
        assert resolved_output_dir is not None
        target_dir = resolved_output_dir
    else:
        target_dir = canonical_target_dir
    out_path = target_dir / f"{uid}.md"
    if output_dir is not None:
        if out_path.exists() or out_path.is_symlink():
            raise RuntimeError(
                f"mint collision: {out_path} already exists; refusing overwrite"
            )
        _atomic_write_text(out_path, instance_text)
    else:
        if not freshen:
            raise AssertionError("canonical no-freshen guard should have refused")
        freshener = _load_rebuild_index(root)
        diagnostic = ""
        for attempt in range(4):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = freshener.freshen_many(
                    (uid,),
                    root,
                    source_replacements={out_path: instance_text.encode("utf-8")},
                    require_absent_sources=(out_path,),
                )
            diagnostic = (stderr.getvalue() or stdout.getvalue()).strip()
            transient_contention = (
                "changed outside the owned projections" in diagnostic
                or "source inventory incomplete" in diagnostic
            )
            if code == 0 or not transient_contention or attempt == 3:
                break
            time.sleep(0.05 * (attempt + 1))
        if code != 0:
            raise RuntimeError(
                "mint transaction refused; canonical source and all derived "
                f"surfaces remain unchanged"
                + (f": {diagnostic}" if diagnostic else "")
            )
        try:
            _verify_minted_index_row(root, uid, out_path, type_name)
        except Exception as exc:
            rollback_error = _rollback_minted_birth(
                freshener, root, uid, out_path
            )
            if rollback_error:
                raise RuntimeError(
                    "mint transaction returned success but exact-row verification "
                    f"failed ({exc}); rollback is incomplete: {rollback_error}"
                ) from exc
            raise RuntimeError(
                "mint transaction returned success but exact-row verification "
                f"failed and the governed birth was rolled back: {exc}"
            ) from exc
    return uid, out_path


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Mint bare collision-checked identifiers or complete human-mintable "
            "governed artifacts from schema-v2 companion bindings."
        ),
        epilog=(
            "examples:\n"
            "  tropo-mint-id --kind file\n"
            "  tropo-mint-id --list-types\n"
            "  tropo-mint-id --type note --author mike\n"
            "  tropo-mint-id --type task --author argus-a144 "
            "--activation-uid <8hex>\n"
            "mint_mode=system-only bindings are reserved for explicit "
            "lifecycle-writer library APIs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--count", type=int, default=1, help="how many identifiers to mint (default 1)")
    p.add_argument("--reason", default="", help="advisory; for the caller's own log (not persisted)")
    p.add_argument("--prefix", default="", help="optional namespace prefix (S8 seam); output is <prefix>-<8hex>")
    p.add_argument("--kind", default="file", choices=VALID_KINDS,
                   help="identifier kind (ADR-050 Decision 3); file/agent/studio/vault live, event declared-not-built")
    p.add_argument("--segment", default="private", choices=("private", "team"),
                   help="write segment (32067bea): team reads the studio-identity manifest and "
                        "prefixes; private (default) stays bare 8-hex")
    p.add_argument("--minted-by", default="tropo-mint-id",
                   help="advisory provenance tag written into the studio-identity manifest "
                        "for --kind studio (ignored otherwise)")
    p.add_argument("--type", default="", metavar="TYPE",
                   help="Governed Autonomy S2 (bba40cd7): mint a FULL governed file of this "
                        "type from its registry-selected visible companion, stamp it, write it, "
                        "and freshen its index row instead of a bare identifier. Requires --author.")
    p.add_argument("--list-types", action="store_true",
                   help="list mint_mode=human types from a verified current registry")
    p.add_argument("--author", default="",
                   help="author label (required with --type); registered agent-generation "
                        "labels also require activation provenance")
    p.add_argument("--activation-uid", default="",
                   help="artifact provenance activation UID; defaults to "
                        "TROPO_ACTIVATION_UID for registered agent-generation authors")
    p.add_argument("--output-dir", default="", metavar="DIR",
                   help="scratch-only direct write under "
                        "agents/<agent>/.tropo-capsule/workspace; canonical homes, "
                        "outside paths, and symlinks refuse")
    p.add_argument("--no-freshen", action="store_true",
                   help="scratch-only: skip index freshening when --output-dir is also supplied; "
                        "canonical --type birth always freshens and verifies or fails")
    args = p.parse_args()

    if args.list_types:
        if args.type:
            print("ERROR: --list-types cannot be combined with --type", file=sys.stderr)
            return 1
        try:
            for type_name in template_leg.list_mintable_types(VAULT_ROOT):
                print(type_name)
            return 0
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    if args.type:
        if args.kind != "file":
            print("ERROR: --type is only meaningful with --kind file (the default)", file=sys.stderr)
            return 1
        if not args.author:
            print("ERROR: --type requires --author <minting agent-generation slug>", file=sys.stderr)
            return 1
        if args.no_freshen and not args.output_dir:
            print(
                "ERROR: canonical --type birth cannot use --no-freshen; "
                "--no-freshen is legal only with an explicit scratch --output-dir",
                file=sys.stderr,
            )
            return 1
        try:
            uid, out_path = mint_file(
                args.type, author=args.author,
                activation_uid=(
                    args.activation_uid
                    or os.environ.get("TROPO_ACTIVATION_UID")
                    or None
                ),
                output_dir=Path(args.output_dir) if args.output_dir else None,
                freshen=not args.no_freshen,
            )
            print(uid)
            print(f"path: {out_path}", file=sys.stderr)
            return 0
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    try:
        for u in mint(args.count, prefix=args.prefix, kind=args.kind,
                       segment=args.segment, minted_by=args.minted_by):
            print(u)
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
