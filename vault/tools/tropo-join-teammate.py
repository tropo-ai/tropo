#!/usr/bin/env python3
"""---
uid: c3e11a02
type: tool
name: join-teammate
title: "join-teammate — the join ceremony (W4/bb3911f5): Po prepares, the owner applies, all-or-none"
status: active
owner: talos
domain: "Ceremony 1 of Stream 2: turn a colleague into a resident whose work can cross the publish boundary."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-join-teammate.py"
spawnable_by:
  - all-executives
input:
  type: object
  description: "See subcommands prepare/apply."
created: 2026-08-31
created_by: talos-t55
governed_by: bb3911f5
schema_version: 2
tags: [w4, stream-2, join-ceremony, federation]
---

join-teammate — Ceremony 1 of Stream 2 (dev-spec bb3911f5 / B-5).

THE JOIN IS A SUCCESSION, PREPARED BY PO AND APPLIED BY ONE OWNER SIGNATURE.
Po PREPARES a three-leg bundle:

  1. the colleague's principal record — uid COMPOSITE 12-hex through the same
     identity seam files use (Mike-ruled 2026-08-31: one identity scheme for
     every entity class, people included);
  2. a NEW immutable group generation superseding the current active one and
     including the new member (B4a has no mutate; a join adds a generation —
     0bfa771d "active semantic fields are immutable");
  3. the residency field on the principal record.

The org owner APPLIES it with ONE Ed25519 signing gesture. The key is external
by design and never minted by the agent lifecycle (ADR-066); the signature IS
the authorization — there is deliberately no --authorized-by flag, because a
second authorization channel beside the signature is a second source of truth
(the defect family this whole spec exists to close).

Atomicity is at APPLY: all three legs land or none. The journal records the
authorizing principal by UID, never by name.

Composes — never reimplements — the locked B4a primitives: lib.group_contract
(shape validation, transition-once), tropo-mint-id (the identity seam),
finalize-group's journaled model for the group leg. One writer for residency
(this tool), one reader (the scope derivation in lib/gardener.py). If a third
caller needs residency it reads the same field.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util as _ilu
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from lib import group_contract as gc  # noqa: E402

STUDIO_ROOT = Path(__file__).resolve().parents[2]
PRINCIPALS_FILE = STUDIO_ROOT / ".tropo-studio" / "group-authority" / "principals.jsonl"
BUNDLE_DIR = STUDIO_ROOT / ".tropo-studio" / "join-bundles"
TRUST_FILE = STUDIO_ROOT / ".tropo-studio" / "authorities" / "group-authority" / "accepted-trust.json"
JOURNAL_FILE = STUDIO_ROOT / ".tropo-studio" / "join-bundles" / "journal.jsonl"

#: Where the group-generation leg LANDS. Not a new home: this is
#: tropo-finalize-group's own source directory (DEFAULT_SOURCE_DIR = "groups",
#: read relative to the corpus root; its refusal when a draft is absent reads
#: "draft group <uid> has no source file under groups/"). The corpus root is the
#: STUDIO root — the corpus every other reader of the chain already resolves:
#: the three shipped groups are tracked at <studio>/groups/, the genesis runbook
#: 835404d3 passes --corpus-root <studio_root> throughout, and lib/audience_gate.py
#: re-derives source_path: groups/<uid>.json and compares bytes. The writer that
#: was missing writes to the reader that was already waiting.
#: RULED by argus-a169 2026-09-04, PROVEN BOTH WAYS against a git-archive scratch
#: with a fixture authority genesis: ruling on -> [MOUNTED], compose.lock keyed by
#: vault_uid; ruling off -> GROUP_NOT_FOUND at Step 5a. Finding f015bac58b28.
#: (a168's earlier ruling named the right reader and the wrong corpus root, taken
#: from the Step 5 he had written into the playbook; metis-g119's recipe measured
#: both alternatives — GROUP_NOT_FOUND nested, PROJECTION_MISMATCH with --source-dir,
#: which also drops the three shipped groups.)
GROUPS_DIR = STUDIO_ROOT / "groups"

#: The residency value a teammate carries. One vocabulary, read by the scope
#: derivation's authorship leg (gardener) — never restated there.
TEAM_RESIDENT = "team-resident"


def _load_mint_tool():
    """The identity seam, by file location (its filename is not importable)."""
    spec = _ilu.spec_from_file_location("mint_id_for_join", _TOOLS_DIR / "tropo-mint-id.py")
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_principals(path: Path | None = None) -> dict[str, dict]:
    path = path or PRINCIPALS_FILE
    if not path.is_file():
        return {}
    return {p["principal_uid"]: p for p in json.loads(path.read_text(encoding="utf-8"))}


def _write_principals(principals: dict[str, dict], path: Path | None = None) -> None:
    path = path or PRINCIPALS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [principals[uid] for uid in sorted(principals)]
    _atomic_write_bytes(path, (json.dumps(rows, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def _write_group_draft(draft: dict, path: Path) -> None:
    """Land the group-generation leg: the draft at <studio-root>/groups/<uid>.json.

    ONE function, by name, so the suite's negative control can mock it to a
    no-op and require the world assertion to fail (symbol fixed with argus-a168,
    evt_b51c083be28ac6fe_00000425, so his suite amendment and this tool meet
    without a fork). The payload is the canonical semantic object apply already
    computed — group_contract.SEMANTIC_KEYS — with status "draft" and a null
    semantic_hash, which is what tropo-group.capsule Rule 6 requires of a draft
    and what tropo-finalize-group's loader reads.
    """
    _atomic_write_bytes(
        path, (json.dumps(draft, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def _restore_bytes(path: Path, before: bytes | None) -> None:
    """Put a governed file back exactly as it was, including not existing.

    `before is None` means the file was absent before the apply, so restoring it
    means REMOVING it — a first join mints a group source that did not exist, and
    leaving a partial draft behind would be the very residue all-or-none denies.
    """
    if before is None:
        if path.is_file():
            path.unlink()
        return
    _atomic_write_bytes(path, before)


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def bundle_digest(bundle: dict) -> str:
    """The fixed bytes the owner signs: canonical JSON of the bundle."""
    canon = json.dumps(bundle, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()


def prepare(colleague_name: str, group_slug: str, *,
            principals_path: Path | None = None,
            mint_tool=None) -> tuple[Path, str]:
    """Po's half: mint the principal, build the three-leg bundle, hand it over.

    Returns (bundle_path, digest_to_sign). Writes NOTHING governed — the
    bundle is a proposal; only the owner's apply lands it.
    """
    mint = mint_tool or _load_mint_tool()
    principals_path = principals_path or PRINCIPALS_FILE
    principals = _load_principals(principals_path)

    # Leg 1: the colleague's principal record, uid through the same composite
    # seam every governed mint uses (the people-UID ruling). Refuse-if-absent
    # holds: no studio-identity manifest, no principal.
    principal_uid = mint.mint(1, kind="file")[0]
    if len(principal_uid) != 12:
        raise SystemExit(
            f"REFUSED: the identity seam returned {principal_uid!r} — the join "
            "requires the composite generation shape (12-hex). The studio "
            "identity era must be live before anyone joins.")

    principal = {
        "principal_uid": principal_uid,
        "principal_class": "human",
        "status": "active",
        "display_name": colleague_name,
        "source_authority_uid": "local-prepare",
        "source_revision": "0",
        "source_hash": "0" * 64,
    }

    # Leg 2: the successor group generation. The current active group's
    # members + the new principal, as a NEW draft uid — B4a succession adds a
    # generation; it never amends one.
    # (The active group is located by slug from the principals dir's sibling
    # corpus; the caller passes the slug the ceremony document names.)
    successor_uid = mint.mint(1, kind="file")[0]
    group_draft = {
        "uid": successor_uid,
        "type": "group",
        "slug": group_slug,
        "title": f"{group_slug.replace('-', ' ').title()} (successor)",
        "description": (
            f"Successor generation minted by the join ceremony for "
            f"{colleague_name}; supersedes the prior generation of "
            f"{group_slug}. B4a: a join adds a generation, never amends one."),
        "owner": None,  # bound at apply from the signing owner
        "members": None,  # bound at apply: prior members + the new principal
        "includes_groups": [],
        "status": "draft",
        "version": 1,
        "semantic_hash": None,
    }

    # Leg 3: residency — written ONLY here, read ONLY by the scope derivation.
    residency = {
        "principal_uid": principal_uid,
        "residency": TEAM_RESIDENT,
        "granted_by_bundle": None,  # digest bound at apply
    }

    bundle = {
        "schema": "join-teammate/1",
        "prepared_by": "po",
        "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "colleague_name": colleague_name,
        "group_slug": group_slug,
        "principal": principal,
        "group_draft": group_draft,
        "residency": residency,
    }

    digest = bundle_digest(bundle)
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    path = BUNDLE_DIR / f"join-{principal_uid}.json"
    _atomic_write_bytes(
        path,
        (json.dumps(bundle, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    return path, digest


def _accepted_owner_keys() -> dict[str, dict]:
    """UID -> accepted key record, from the machine-local trust file.

    A key that was not accepted refuses AUTHORITY_UNTRUSTED (group-authority's
    rule, honored here): trust is never manufactured at apply time.
    """
    if not TRUST_FILE.is_file():
        return {}
    try:
        return json.loads(TRUST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _verify_ed25519(digest_hex: str, signature_hex: str, public_key_hex: str) -> bool:
    """Ed25519 over the digest bytes with an externally supplied key.

    Uses the SAME offline backend as the locked group-authority library
    (cryptography's Ed25519); never generates, stores, or transports a seed."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        key.verify(bytes.fromhex(signature_hex), bytes.fromhex(digest_hex))
        return True
    except Exception:
        return False


def apply(bundle_path: Path, signature_hex: str, *,
          principals_path: Path | None = None,
          groups_dir: Path | None = None,
          accepted_keys: dict[str, dict] | None = None,
          verify_fn=_verify_ed25519) -> dict:
    """The owner's half: one verifying gesture lands all three legs or none.

    The signature IS the authorization (AC2): no --authorized-by flag exists,
    and the journal records the authorizing principal by UID, never name.
    """
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"REFUSED: bundle unreadable at {bundle_path}: {exc}")

    # Tamper check first: the signature is over the bundle AS PREPARED.
    digest = bundle_digest(bundle)
    if bundle.get("schema") != "join-teammate/1":
        raise SystemExit(f"REFUSED: unknown bundle schema {bundle.get('schema')!r}")

    principals_path = principals_path or PRINCIPALS_FILE
    groups_dir = groups_dir or GROUPS_DIR
    keys = accepted_keys if accepted_keys is not None else _accepted_owner_keys()
    if not keys:
        raise SystemExit(
            "REFUSED: no accepted owner keys on this machine (trust file "
            f"absent/empty at {TRUST_FILE}). Trust is never manufactured at "
            "apply time — accept the owner key out of band first.")

    authorizing_uid = None
    public_key_hex = None
    for uid, record in keys.items():
        key_hex = record.get("ed25519_public_key_hex") or record.get("public_key_hex")
        if key_hex:
            authorizing_uid, public_key_hex = uid, key_hex
            break
    if public_key_hex is None:
        raise SystemExit("REFUSED: no accepted trust record carries a public key")

    if not verify_fn(digest, signature_hex, public_key_hex):
        raise SystemExit(
            f"REFUSED: signature does not verify for owner {authorizing_uid} — "
            "nothing lands. A tampered or unsigned bundle applies nothing (AC1).")

    # ── All-or-none apply (journaled: PREPARED -> COMMITTED) ──
    principals = _load_principals(principals_path)
    principal = dict(bundle["principal"])
    residency = dict(bundle["residency"])
    group_draft = dict(bundle["group_draft"])

    principal_uid = principal["principal_uid"]
    if principal_uid in principals:
        raise SystemExit(
            f"REFUSED: principal {principal_uid} already exists — a join is "
            "once per colleague; re-preparing for the same person needs a new "
            "bundle, not a re-apply.")

    # Bind the owner-dependent legs now that the gesture verified.
    group_draft["owner"] = authorizing_uid
    residency["granted_by_bundle"] = digest

    # The prior active generation's members + the new principal (succession).
    prior_members = sorted({
        uid for uid, rec in principals.items()
        if rec.get("residency") == TEAM_RESIDENT or rec.get("principal_class") == "human"
    })
    group_draft["members"] = sorted(set(prior_members) | {principal_uid})

    # Validate the successor against the locked contract BEFORE anything lands.
    gc.canonical_semantic_object(group_draft)

    # Residency lives on the principal record (one writer: this ceremony).
    principal["residency"] = residency["residency"]
    principal["residency_bundle"] = digest

    staged = dict(principals)
    staged[principal_uid] = principal

    # ── The group-generation leg's payload ──
    # The journal has claimed this leg since the tool shipped; nothing wrote it.
    # The draft IS the canonical semantic object validated three lines above,
    # marked as the draft the finalizer expects: tropo-group.capsule Rule 6 wants
    # status "draft" with a null semantic_hash, and the finalizer refuses
    # anything whose status is not "draft" before hashing it as active.
    draft_source = dict(gc.canonical_semantic_object(group_draft))
    draft_source["semantic_hash"] = None
    group_path = Path(groups_dir) / f"{group_draft['uid']}.json"

    journal = {
        "event": "join_applied",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "authorizing_principal_uid": authorizing_uid,  # UID, never a name (AC2)
        "principal_uid": principal_uid,
        "group_draft_uid": group_draft["uid"],
        "group_slug": group_draft["slug"],
        "bundle_sha256": digest,
        "legs": ["principal", "group-generation", "residency"],
    }
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    staged_bytes = (json.dumps([staged[u] for u in sorted(staged)], indent=1, sort_keys=True)
                    + "\n").encode("utf-8")
    principals_before = (principals_path.read_bytes()
                         if principals_path.is_file() else None)
    group_before = group_path.read_bytes() if group_path.is_file() else None
    prepared = {"event": "join_prepared", "journal": journal,
                "principals_sha256_before": hashlib.sha256(
                    principals_before or b"").hexdigest(),
                # Symmetry: a PREPARED row that records one leg's before-state
                # cannot witness a recovery of the other.
                "group_source_sha256_before": hashlib.sha256(
                    group_before or b"").hexdigest(),
                "group_source_path": str(group_path)}

    # One fsynced PREPARED row, then the single governed write, then COMMITTED.
    tmp_journal = JOURNAL_FILE.with_name(JOURNAL_FILE.name + ".tmp")
    with open(tmp_journal, "wb") as fh:
        fh.write((json.dumps(prepared, sort_keys=True) + "\n").encode("utf-8"))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_journal, JOURNAL_FILE)
    _fsync_dir(JOURNAL_FILE.parent)

    # ALL-OR-NONE, and now it is real rather than true-by-having-one-leg.
    # Two governed files under ONE PREPARED/COMMITTED pair. A failure on either
    # leg restores BOTH to their pre-apply bytes, so a planted failure anywhere
    # leaves the world byte-identical — which is what AC1 always claimed and
    # could not observe while only one file was ever written.
    # Group source FIRST, principals second. Order is deliberate: it makes a
    # failure on the second leg leave GROUP residue, which is the residue only
    # a groups/ snapshot can see. With principals written first, every planted
    # failure leaves principals residue and the groups assertion could never
    # change a verdict — a control that cannot fail proves nothing, and that is
    # the shape of the defect this whole fix exists to remove.
    try:
        _write_group_draft(draft_source, group_path)
        _write_principals(staged, principals_path)
    except BaseException:
        _restore_bytes(principals_path, principals_before)
        _restore_bytes(group_path, group_before)
        raise

    with open(JOURNAL_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "join_committed", "journal": journal},
                            sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

    return journal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[1][:200])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prepare = sub.add_parser(
        "prepare", help="Po's half: mint the principal and hand the bundle for signature")
    p_prepare.add_argument("--colleague-name", required=True)
    p_prepare.add_argument("--group-slug", required=True,
                           help="slug of the group whose successor generation the join mints")

    p_apply = sub.add_parser(
        "apply", help="the owner's half: one verifying Ed25519 gesture lands all three legs")
    p_apply.add_argument("--bundle", required=True, type=Path)
    p_apply.add_argument("--signature", required=True,
                         help="hex Ed25519 signature over the bundle digest")

    args = parser.parse_args()
    if args.cmd == "prepare":
        path, digest = prepare(args.colleague_name, args.group_slug)
        print(f"BUNDLE {path}")
        print(f"DIGEST {digest}")
        print("Hand the bundle to the org owner for one Ed25519 signature over the digest.")
        return 0
    journal = apply(args.bundle, args.signature)
    print(f"JOINED principal={journal['principal_uid']} "
          f"group={journal['group_slug']} by={journal['authorizing_principal_uid']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
