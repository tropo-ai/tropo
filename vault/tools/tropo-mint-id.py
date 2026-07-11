#!/usr/bin/env python3
"""
---
uid: 5187be30
name: mint-id
type: tool
title: "mint-id — the canonical collision-checked identifier minter"
status: active
owner: argus
domain: "Identifier minting — the one collision-checked chokepoint for governed identifiers (ADR-050)"
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
output:
  type: object
  description: "one collision-checked identifier per line on stdout (8-hex, or <mint_prefix>-8hex for a team-segment mint, or the studio_id for --kind studio)"
created: 2026-06-02
created_by: argus-a93
modified: '2026-07-07'
modified_by: talos-t25
version: "2.2"
v2_0_amendment_note: "Talos T25 2026-07-06, dev-spec 796d9330 (ADR-050 cb0f8e46 step 1). Renamed mint-uid -> mint-id (belt mint-uid->mint-id) — the tool now mints identifiers generally, not only file UIDs. Added --kind {file,agent,vault,studio,event} per ADR-050 Decision 3: file/agent are the live flat-8-hex shape (identical collision domain — Decision 2's identifier != identity split means 'agent' here is a handle shape, not the governed agent entity); vault/studio/event are declared in the contract but stub NotImplementedError until their consumers exist (ADR-050 Decision 4c/4d). Added extra_existing= to mint() so the 3 partial-duplicator callers (40b2f455/9e7003b1/e337f1dd) can merge their in-session accumulated set into the collision check without reimplementing the mint loop. UID 5187be30 unchanged — the stable address; no caller link breaks."
v2_1_amendment_note: "Talos T25 2026-07-06, dev-spec 32067bea (Studio-Identity Primitive — Federation Phase A). --kind studio is now real: the idempotent genesis writer for a self-sovereign studio-identity manifest at .tropo/studio-identity.md (studio_id + short mint_prefix, minted once, never regenerated). Added --segment {private,team} (default private): a team-segment file/agent mint reads the manifest and produces <mint_prefix>-<8hex>; private stays bare 8-hex (unchanged default behavior). A missing/corrupt manifest on a team-segment mint raises StudioIdentityError — fails loud, never falls back to a silent bare or fabricated identity (AC5). 'studio' moved file/agent -> _IMPLEMENTED_KINDS; vault/event remain declared-not-built per ADR-050 Decision 4d."
v2_2_amendment_note: "Talos T25 2026-07-07, dev-spec 943bb220 (vault.capsule forge, ADR-051 Fork 1 / ADR-050 Decision 4c). --kind vault is now real: mints a fresh, collision-checked SHORT REGISTERED CODE (4-6 lowercase alnum) per ADR-050 Decision 3 ('vault/studio = short registered code' — explicitly NOT the flat-8-hex file/agent shape). Shares its shape-generation helper (_generate_short_code) with the studio mint_prefix generator (judgment call, named in 943bb220's build report: same SHAPE contract reused, no shared STATE — a vault code and a studio's own mint_prefix are minted independently and a fresh vault code is also checked against this studio's own mint_prefix, if one exists, so a composed <studio_prefix>-<vault_code> identifier can never self-collide). Unlike 'studio' (idempotent genesis writer, exactly one per studio), 'vault' mints like file/agent: any count >= 1, no manifest file written here — Fork 2 (the per-vault-root manifest governed-write-gate) is a named downstream dependency, not owned by this build. 'vault' moved file/agent/studio -> _IMPLEMENTED_KINDS; 'event' remains declared-not-built per ADR-050 Decision 4d (a different, monotonic collision model)."
governed_by: d5e1b4a3
member_of:
  - "c7e4f9a2"
schema_version: 2
belt: true
extraction_scope: ship
trigger_description: "Get a fresh collision-checked identifier before authoring (file/agent UID or studio genesis today; vault/event declared, not yet built)."
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
import datetime as _dt
import re
import secrets
import sys
from pathlib import Path

import yaml

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
INDEX = VAULT_ROOT / "vault" / "00-index.jsonl"
STUDIO_IDENTITY_REL = Path(".tropo") / "studio-identity.md"

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
    if INDEX.exists():
        for line in INDEX.read_text(encoding="utf-8").splitlines():
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


def main() -> int:
    p = argparse.ArgumentParser(description="Mint collision-checked governed identifier(s) (ADR-050 chokepoint).")
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
    args = p.parse_args()
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
