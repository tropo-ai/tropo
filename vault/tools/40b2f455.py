#!/usr/bin/env python3
"""
---
uid: 40b2f455
version: "1.2"
v1_2_note: "eda86636 items 1-4, Mike-directed P0 (verbatim: dozens of reasons an agent can terminate without properly retiring, most of them out of our control, FIX THIS NOW). A retirement must always be closeable. The signature is now a CLAIM ABOUT WHAT WAS PROVABLE at close time, not a precondition for closing. (1) Every close records close_evidence: signed | attested — never a silent third state. (2) An unsignable close NEVER voids the key: the prior remedy renamed agent_public_key aside, leaving the record non-key-bearing while _lineage_ever_keyed() still counted it as keyed, which are complementary on exactly the voided case, so the remedy for an unsignable close deterministically bricked the successor birth — and voiding is irreversible, so the wrong remedy was permanent. The key was never invalid; only the broker was gone. (3) --check-broker answers can-this-be-signed at retirement STEP 0 instead of at the final write: G98 completed a transfer, memory fold, reflection and captain log before learning it could not close. (4) --broker-lost --authorized-by closes atomically, fails closed without a principal, and refuses outright when the broker is actually live — an attested grade must mean the signature was impossible, never merely inconvenient — so no agent hand-edits an activation record again, which is the collateral-damage class that produced durable history poison on this lineage twice. The probe also refuses to report a VOIDED record as a benign unkeyed one. Seam coverage at tests/test_broker_loss_close_seam.py — the test that did not exist, which is why five days passed between two identical incidents. Open fork (durable per-agent key vs session-scoped + attested) is Mike call and is routed, not decided here."
v1_1_note: "Captain-mode edit (talos-owned; Talos notified), vela-v71 2026-07-31. op:update interpolated --value into frontmatter RAW, so any value containing a colon-space produced unparseable YAML while the tool printed the uid and exited 0 — a governed-write tool reporting success over a broken artifact. On an activation entry the consequence is severe rather than cosmetic: an unparseable entry that syntactically declares agent_public_key is treated as durable activation-history poison and blocks predecessor derivation for that agent ENTIRE lineage, so the successor cannot be born. vela-v71 did this to her own activation entry (ee967682) at ~03:52Z recording a sleeve change, and it sat undetected for ~15 hours until a control probe during an unrelated diagnosis surfaced V72 as unbootable. The Fleet Boot Health check did not catch it because that check skips agents whose latest activation is still active — a live agent poisoning her own lineage is invisible to it. Two guards added: values are YAML-quoted via a round-trip test (plain form kept when it survives, double-quoted when it does not), and the resulting frontmatter must re-parse to a mapping BEFORE the write lands, with a post-write re-read that restores the prior content if verification fails. Fails closed and says why; never writes an activation entry the loaders cannot read.")
name: write-activation-entry
type: tool
status: active
owner: talos
domain: "Companion script for write-activation-entry.skill (UID 7a3d04bc)."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/40b2f455.py"
script_path: vault/tools/40b2f455.py
spawnable_by:
  - all-executives
input:
  type: object
  description: "See tool usage for argument details"
created: 2026-05-27
created_by: talos-t10
governed_by: d5e1b4a3
member_of:
  - 8dd772a0
schema_version: 2
belt: true
title: "write-activation-entry — Open/close activation registry entries"
trigger_description: "Open/close agent activation entries (boot and retirement)."
belt_invocation: "python3 vault/tools/40b2f455.py {open|close|update}"
belt_example: "python3 vault/tools/40b2f455.py open --agent talos --generation T18 ..."
---
"""
from __future__ import annotations  # PEP 604 `X | None` annotations on py3.9 (S1, ef65fccd)

"""Companion script for write-activation-entry.skill (UID 7a3d04bc).

The actual mutation logic for activation entries — open at boot, close at
retirement / [SHUTDOWN] / stale-sweep, update for non-lifecycle field touches.
Called by boot playbook Group 0 Step 0.0b, retirement playbook closure step,
sa.* dispatch [SHUTDOWN] handler, and Vela's Tier 1 stale-sweep.

Authored v1.21.0.1 bundled remediation 2026-05-11 by Argus A58 after V44's
boot retrospective surfaced GAP-3 (skill referenced this script; script never
existed). Skill body is documentation; this is the executable.

Usage:
  open:
    python3 write-activation-entry.py open \\
      --agent <slug> --generation <gen> --model <model> \\
      --platform <platform> --agent-root <uid> --agent-class <class> \\
      --activated-by <uid-or-user> --member-of <uid>[,<uid>,...] \\
      [--commissioned-purpose <text>] [--run-folder <path>]

    Every non-pipeline activation mints a fresh session-local Ed25519 keypair
    internally. Only the public half is written to the activation entry; the
    private half stays under the secure runtime root and is removed when the
    activation reaches a terminal status. Each keyed entry also records its
    validated predecessor_activation_uid, or explicit null for true genesis.
    Caller-supplied provenance keys are not accepted.

  close:
    python3 write-activation-entry.py close \\
      --activation-uid <uid> --target-status <retired|failed|stale|paused> \\
      --closure-reason <reason> [--transfer-uid <uid>]

  update:
    python3 write-activation-entry.py update \\
      --activation-uid <uid> --field <field> --value <value>

Exit codes:
  0  Success — entry written/updated; UID printed to stdout
  1  Validation failure (ADR-016 / ADR-028 / schema)
  2  Lock acquisition failure (parallel-boot violation)
  3  Argument or filesystem error
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
VAULT_AGENTS = VAULT_ROOT / "vault" / "agents"
LOCK_DIR = VAULT_ROOT / ".tropo-studio" / "locks"
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from lib.authority_chain import (
    ActivationRecord,
    AuthorityChainError,
    AuthorityErrorCode,
    activation_state_lock,
    authority_state_lock,
    canonical_executive_generation,
    cleanup_stale_agent_keypairs,
    derive_new_activation_predecessor,
    load_activation_entries,
    load_canonical_activation_entries,
    mint_agent_keypair,
    remove_agent_keypair,
    sign_commit,
)
TODAY = time.strftime("%Y-%m-%d")
# A real instant, in UTC, for fields whose value is used as ARITHMETIC rather
# than as a label. `activated_at` is one: the stale-sweep computes an age from it
# and closes records automatically on the answer. A bare local date parsed as
# midnight UTC over-stated age by a full timezone offset, which made every
# sub-agent activation sweepable at birth (adversarial review, 2026-08-03).
# Dates stay correct for display fields (`created`, `modified`, `retired_at`);
# only values that get subtracted need an instant.
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
SCRIPT_NAME = "write-activation-entry.py"


class ActivationCloseRollbackError(AuthorityChainError):
    """Named failure for an incomplete activation-close rollback."""


VALID_STATUSES = {"active", "retired", "failed", "stale", "paused"}
TERMINAL_STATUSES = {"retired", "failed", "stale"}
VALID_CLASSES = {"executive", "director", "sa", "cosmo", "tropo",
                 "worker", "child-agent", "pipeline"}
EXECUTIVE_GENERATION_CLASSES = {"executive", "director", "cosmo", "tropo"}
# Per-class stale_threshold_hours defaults (capsule v1.0.1 §2 amendment)
STALE_THRESHOLD_DEFAULTS = {
    "sa": 2, "worker": 6, "executive": 168, "director": 168,
    "cosmo": 168, "tropo": 168, "child-agent": 4,
}
VALID_CLOSURE_REASONS = {
    "clean-retirement", "context-overflow", "parallel-boot-violation",
    "stale-sweep", "dispatch-failure", "harness-watchdog-stall",
    "[SHUTDOWN]", "paused-by-user",
    # eda86636: the session ended before the retirement could be signed. A
    # first-class recorded outcome, not an error — see close_evidence.
    "broker-lost",
}
LIFECYCLE_FIELDS = {
    "uid",
    "activation_uid",
    "activation_class",
    "type",
    "name",
    "title",
    "agent",
    "agent_uid",
    "agent_root",
    "agent_root_uid",
    "agent_class",
    "generation",
    "status",
    "state",
    "activated_at",
    "activated_by",
    "agent_public_key",
    "agent_key_fingerprint",
    "key_algorithm",
    "key_id",
    "authority_public_key",
    "key_custody",
    "model",
    "platform",
    "member_of",
    "run_folder",
    "stale_threshold_hours",
    "author",
    "created",
    "created_by",
    "modified",
    "modified_by",
    "opened_by_script",
    "retired_at",
    "closure_reason",
    "transfer_uid",
    "successor_uid",
    "predecessor_uid",
    "predecessor_activation_uid",
    "current_activation_uid",
    "retiring_flip_recorded_at",
    "reflection_path",
}
LIFECYCLE_FIELD_ALIASES = {
    "activationclass",
    "activationgeneration",
    "activationid",
    "activationstatus",
    "activationuid",
    "agentgeneration",
    "agentidentity",
    "agentkey",
    "agentpublickey",
    "agentstatus",
    "authoritykey",
    "authoritypublickey",
    "identitykey",
    "keycustody",
    "keyfingerprint",
    "lifecyclestatus",
    "privatekey",
    "provenancekey",
    "publickey",
    "predecessoractivationuid",
    "signingkey",
}
REGISTRATION_REQUIRED_OPAQUE_CLASSES = {"sa", "pipeline"}


# ---------------------- helpers ----------------------------------------------

def yaml_quote(s: str) -> str:
    """Wrap a free-text value in YAML double-quotes with proper escaping.

    Closure reasons and other free-text frontmatter fields routinely contain
    colon-space patterns (e.g., 'Major substrate deliverables: foo') and other
    punctuation that breaks bare YAML scalars. Always quoting them keeps
    activation entries PyYAML-parseable and validator-clean.

    Captain-mode fix v1.34.0 per Mike-V46 direction 2026-05-16 — root-cause of
    the d7f19eeb.md PyYAML-unparseable WARN surfaced by V46 boot validator pass.
    """
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# f9751636 chokepoint: delegate to the canonical collision-checked minter.
import importlib.util as _ilu_40b2
_mint_spec_40b2 = _ilu_40b2.spec_from_file_location(
    "_mint_uid_canonical_40b2", Path(__file__).resolve().parent / "tropo-mint-id.py"
)
_mint_mod_40b2 = _ilu_40b2.module_from_spec(_mint_spec_40b2)
_mint_spec_40b2.loader.exec_module(_mint_mod_40b2)


def load_existing_uids():
    return _mint_mod_40b2.load_existing_uids()


def mint_uid(existing):
    # 796d9330 (ADR-050): delegate the actual mint to the canonical collision-checked
    # mint() instead of reimplementing the loop; extra_existing carries this caller's
    # in-session accumulated set (minted but not yet written to disk).
    minted = _mint_mod_40b2.mint(1, extra_existing=existing)[0]
    existing.add(minted)
    return minted


def parse_frontmatter(path):
    """Return (fm_dict, raw_fm_text, body_text) or None if no frontmatter."""
    content = path.read_text()
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---", 4)
    if end == -1:
        return None
    raw_fm = content[4:end]
    body = content[end + 4:]
    fm = {}
    for line in raw_fm.splitlines():
        m = re.match(r"^([a-zA-Z_][\w.]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            # Strip surrounding quotes
            if (val.startswith('"') and val.endswith('"')) or \
               (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            fm[key] = val
    return fm, raw_fm, body


def scan_activations():
    """Scan vault for all type: activation entries."""
    entries = []
    for p in VAULT_FILES.glob("*.md"):
        parsed = parse_frontmatter(p)
        if parsed is None:
            continue
        fm, _, _ = parsed
        if fm.get("type") != "activation":
            continue
        entries.append((p.stem, fm))
    return entries


def parse_generation(gen_str, agent_class):
    """Parse generation string into a comparable number per class."""
    if agent_class in EXECUTIVE_GENERATION_CLASSES:
        parsed = parse_canonical_executive_generation(gen_str)
        if parsed:
            return parsed[1]
    elif agent_class in {"sa", "worker"}:
        m = re.match(r"^.+-(\d+)$", gen_str)
        if m:
            return int(m.group(1))
    elif agent_class == "child-agent":
        m = re.search(r"\.(\d+)\.", gen_str)
        if m:
            return int(m.group(1))
    return None


def parse_canonical_executive_generation(gen_str):
    """Return (PREFIX, number); letter-case on the prefix is not identity."""
    return canonical_executive_generation(gen_str)


def registered_generation_prefix(agent, agent_root):
    """Resolve a declared prefix from the exact root, then unique agent metadata."""
    exact_root = VAULT_FILES / f"{agent_root}.md"
    if exact_root.is_file():
        parsed = parse_frontmatter(exact_root)
        if parsed:
            prefix = str(parsed[0].get("generation_prefix") or "").strip()
            if prefix:
                return prefix, None

    candidates = []
    for path in sorted(VAULT_FILES.glob("*.md")):
        if path == exact_root:
            continue
        parsed = parse_frontmatter(path)
        if not parsed:
            continue
        fm = parsed[0]
        if str(fm.get("agent_slug") or "") != agent:
            continue
        prefix = str(fm.get("generation_prefix") or "").strip()
        if prefix:
            candidates.append(prefix)
    unique = sorted(set(candidates))
    if len(unique) > 1:
        return None, (
            f"conflicting registered generation prefixes for {agent!r}: {unique}"
        )
    return (unique[0] if unique else None), None


def registered_agent_class(agent, agent_root):
    """Resolve one canonical class from the exact root and unified registries."""

    root_candidates = []
    unified_candidates = []
    exact_root = VAULT_FILES / f"{agent_root}.md"
    if exact_root.is_file():
        parsed = parse_frontmatter(exact_root)
        if parsed:
            fm = parsed[0]
            slug = str(fm.get("agent_slug") or "").strip()
            agent_class = str(fm.get("agent_class") or "").strip().lower()
            if agent_class and slug == agent:
                root_candidates.append((agent_class, str(exact_root)))

    if VAULT_AGENTS.is_dir():
        for path in sorted(VAULT_AGENTS.glob("*.md")):
            parsed = parse_frontmatter(path)
            if not parsed:
                continue
            fm = parsed[0]
            if fm.get("type") != "agent":
                continue
            if str(fm.get("agent") or fm.get("slug") or "").strip() != agent:
                continue
            agent_class = str(fm.get("agent_class") or "").strip().lower()
            if agent_class:
                unified_candidates.append((agent_class, str(path)))
    for path in sorted(VAULT_FILES.glob("*.md")):
        if path == exact_root:
            continue
        parsed = parse_frontmatter(path)
        if not parsed:
            continue
        fm = parsed[0]
        if str(fm.get("agent_slug") or "").strip() != agent:
            continue
        agent_class = str(fm.get("agent_class") or "").strip().lower()
        if agent_class:
            root_candidates.append((agent_class, str(path)))

    root_classes = {candidate[0] for candidate in root_candidates}
    unified_classes = {candidate[0] for candidate in unified_candidates}
    if len(root_classes) > 1 or (not root_classes and len(unified_classes) > 1):
        return None, (
            f"conflicting canonical classes for {agent!r}: "
            f"{sorted(root_classes | unified_classes)}"
        )
    classes = root_classes or unified_classes
    if not classes:
        return None, None
    selected = next(iter(classes))
    allowed_unified = {selected}
    if selected in {"cosmo", "tropo"}:
        allowed_unified.add("executive" if selected == "cosmo" else "concierge")
    incompatible = sorted(unified_classes - allowed_unified)
    if incompatible:
        return None, (
            f"unified class(es) {incompatible} are incompatible with registered "
            f"activation class {selected!r} for {agent!r}"
        )
    return selected, None


def registered_current_generation(agent, agent_root):
    """Resolve the current canonical lineage marker for established agents."""

    candidates = []
    if VAULT_AGENTS.is_dir():
        for path in sorted(VAULT_AGENTS.glob("*.md")):
            parsed = parse_frontmatter(path)
            if not parsed:
                continue
            fm = parsed[0]
            if fm.get("type") != "agent":
                continue
            if str(fm.get("agent") or fm.get("slug") or "").strip() != agent:
                continue
            generation = str(fm.get("generation") or "").strip()
            if generation:
                candidates.append((generation, str(path)))

    exact_root = VAULT_FILES / f"{agent_root}.md"
    root_paths = [exact_root] if exact_root.is_file() else []
    root_paths.extend(
        path
        for path in sorted(VAULT_FILES.glob("*.md"))
        if path != exact_root
    )
    for path in root_paths:
        parsed = parse_frontmatter(path)
        if not parsed:
            continue
        fm = parsed[0]
        if fm.get("type") != "project":
            continue
        if str(fm.get("agent_slug") or "").strip() != agent:
            continue
        generation = str(
            fm.get("current_generation")
            or fm.get("current_agent_generation")
            or fm.get("agent_generation")
            or ""
        ).strip()
        if generation:
            candidates.append((generation, str(path)))

    generations = {generation for generation, _path in candidates}
    if len(generations) > 1:
        return None, (
            f"conflicting canonical current generations for {agent!r}: "
            f"{sorted(generations)}; sources={[path for _generation, path in candidates]}"
        )
    return (next(iter(generations)) if generations else None), None


def registered_current_activation_uid(agent, agent_root):
    """Resolve the canonical current activation identity across class shapes."""

    candidates = []
    if VAULT_AGENTS.is_dir():
        for path in sorted(VAULT_AGENTS.glob("*.md")):
            parsed = parse_frontmatter(path)
            if not parsed:
                continue
            fm = parsed[0]
            if fm.get("type") != "agent":
                continue
            if str(fm.get("agent") or fm.get("slug") or "").strip() != agent:
                continue
            activation_uid = str(fm.get("current_activation_uid") or "").strip()
            if activation_uid:
                candidates.append((activation_uid, str(path)))

    exact_root = VAULT_FILES / f"{agent_root}.md"
    root_paths = [exact_root] if exact_root.is_file() else []
    root_paths.extend(
        path
        for path in sorted(VAULT_FILES.glob("*.md"))
        if path != exact_root
    )
    for path in root_paths:
        parsed = parse_frontmatter(path)
        if not parsed:
            continue
        fm = parsed[0]
        if fm.get("type") != "project":
            continue
        if str(fm.get("agent_slug") or "").strip() != agent:
            continue
        activation_uid = str(fm.get("current_activation_uid") or "").strip()
        if activation_uid:
            candidates.append((activation_uid, str(path)))

    activation_uids = {activation_uid for activation_uid, _path in candidates}
    if len(activation_uids) > 1:
        return None, (
            f"conflicting canonical current activation UIDs for {agent!r}: "
            f"{sorted(activation_uids)}; "
            f"sources={[path for _uid, path in candidates]}"
        )
    return (next(iter(activation_uids)) if activation_uids else None), None


def validate_open_class_binding(args):
    expected_class, resolution_error = registered_agent_class(
        args.agent,
        args.agent_root,
    )
    if resolution_error:
        return resolution_error
    if expected_class and args.agent_class != expected_class:
        return (
            f"requested class {args.agent_class!r} does not match canonical class "
            f"{expected_class!r} for {args.agent!r}"
        )
    if (
        args.agent_class in REGISTRATION_REQUIRED_OPAQUE_CLASSES
        and not expected_class
    ):
        return (
            f"{args.agent_class}-class slug {args.agent!r} has no canonical "
            "unified-agent or agent-root registration"
        )
    return None


def validate_open_generation_label(args):
    """Validate executive labels and registered prefix before any key is minted."""
    if args.agent_class not in EXECUTIVE_GENERATION_CLASSES:
        return None
    parsed = parse_canonical_executive_generation(args.generation)
    if parsed is None:
        return (
            "executive-class generation must be an uppercase prefix followed by "
            "a positive canonical integer (no suffix or leading zero)"
        )
    prefix, number = parsed
    # New writes stay strict: store the canonical uppercase form only.
    # Historical reads normalize via authority_chain.normalize_generation_label.
    if str(args.generation).strip() != f"{prefix}{number}":
        return (
            "executive-class generation must be an uppercase prefix followed by "
            "a positive canonical integer (no suffix or leading zero)"
        )
    expected_prefix, resolution_error = registered_generation_prefix(
        args.agent,
        args.agent_root,
    )
    if resolution_error:
        return resolution_error
    if expected_prefix and prefix != expected_prefix:
        return (
            f"generation prefix {prefix!r} does not match registered prefix "
            f"{expected_prefix!r} for {args.agent!r}"
        )
    return None


def validate_executive_lineage(args, records):
    """Require the next canonical generation from all preserved identities."""
    if args.agent_class not in EXECUTIVE_GENERATION_CLASSES:
        return None
    current = parse_canonical_executive_generation(args.generation)
    if current is None:
        return "generation is not canonical"
    prefix, number = current
    matching = [
        record
        for record in records
        if record.agent == args.agent
        and record.agent_class.strip().lower() in EXECUTIVE_GENERATION_CLASSES
    ]
    parsed_existing = []
    for record in matching:
        parsed = parse_canonical_executive_generation(record.generation)
        if parsed is None:
            return (
                f"registered activation {record.uid} has noncanonical generation "
                f"{record.generation!r}; lineage cannot be proven"
            )
        if parsed[0] == prefix:
            parsed_existing.append((record, parsed[1]))
    registered_generation, resolution_error = registered_current_generation(
        args.agent,
        args.agent_root,
    )
    if resolution_error:
        return resolution_error
    if registered_generation:
        registered = parse_canonical_executive_generation(registered_generation)
        if registered is None or registered[0] != prefix:
            return (
                f"canonical current generation {registered_generation!r} is not a "
                f"valid {prefix}-lineage marker for {args.agent!r}"
            )
        if not any(
            existing_number == registered[1]
            for _record, existing_number in parsed_existing
        ):
            return (
                f"canonical current generation {registered_generation!r} has no "
                "preserved activation predecessor; lineage reset is refused"
            )
        highest_registered_number = max(
            existing_number for _record, existing_number in parsed_existing
        )
        if highest_registered_number != registered[1]:
            return (
                f"canonical current generation {registered_generation!r} conflicts "
                f"with preserved highest generation {prefix}{highest_registered_number}"
            )
    if any(existing_number == number for _record, existing_number in parsed_existing):
        return f"generation {args.generation!r} is already registered"
    if not parsed_existing:
        if number != 1:
            return (
                f"expected preserved predecessor {prefix}{number - 1}, but no "
                "canonical/recycled/archive identity exists"
            )
        return None
    highest_record, highest_number = max(parsed_existing, key=lambda item: item[1])
    if number != highest_number + 1:
        return (
            f"predecessor {highest_record.generation!r} ({highest_record.uid}) "
            f"requires generation {prefix}{highest_number + 1}, not {args.generation!r}"
        )
    return None


def successor_generation(gen_str, agent_class):
    """Compute successor generation string from current generation. v1.52 A12b helper.

    Used by op_close to author the transfer-stub frontmatter at retirement-time.
    Executive class: 'A57' -> 'A58'; sa class: 'sa.skeptic-024' -> 'sa.skeptic-025'.
    Returns None if generation pattern cannot be parsed.
    """
    if agent_class in EXECUTIVE_GENERATION_CLASSES:
        parsed = parse_canonical_executive_generation(gen_str)
        if parsed:
            prefix, number = parsed
            num = number + 1
            return f"{prefix}{num}"
    elif agent_class in {"sa", "worker"}:
        m = re.match(r"^(.+-)(\d+)$", gen_str)
        if m:
            prefix = m.group(1)
            num = int(m.group(2)) + 1
            return f"{prefix}{num:03d}" if len(m.group(2)) == 3 else f"{prefix}{num}"
    return None


def auto_create_transfer_stub(activation_fm: dict, transfer_uid: str, closing_actor: str) -> bool:
    """Author a transfer-stub at vault/files/<transfer-uid>.md if absent. v1.52 A12b structural fix.

    Composes with v1.48 Carryalong 3 retirement-invariants pattern. Closes the recurring
    defect class (Metis G55→G56 + G56→G57 + G57→G58 all required Vela captain-mode
    surgical stub authoring at ship time because no auto-creation existed at retirement time).

    Returns True if stub was authored; False if stub already existed (no-op).
    Stub fields derived from activation entry frontmatter; minimum-viable shape per
    Vela V49/V51 captain-mode precedent at e7c4f523 + 7b2c1360.
    """
    stub_path = VAULT_FILES / f"{transfer_uid}.md"
    if stub_path.exists():
        return False  # Idempotent — never clobber existing stub

    agent_slug = activation_fm.get("agent", "unknown")
    gen_from = activation_fm.get("generation", "unknown")
    agent_class = activation_fm.get("agent_class", "executive")
    agent_root = activation_fm.get("agent_root", "")
    gen_to = successor_generation(gen_from, agent_class) or f"{gen_from}+1"

    title = f"{agent_slug.title()} {gen_from} → {gen_to} — Living Transfer (Vault Stub)"
    sleeve = activation_fm.get("model", "unknown")
    platform = activation_fm.get("platform", "unknown")

    stub_content = f"""---
uid: {transfer_uid}
type: document
subtype: living-transfer
title: {yaml_quote(title)}
agent: {agent_slug}
generation: {gen_from}
successor: {gen_to}
status: published
state: active
sleeve: {sleeve}
platform: {platform}
created: {TODAY}
created_by: {closing_actor}
modified: {TODAY}
modified_by: {closing_actor}
authoring_note: "Auto-generated by write-activation-entry.py op_close --transfer-uid at retirement-time. v1.52 A12b structural fix per cycle brief 404ac636 §3 A-lane A12b — closes the recurring defect class where transfer_uid was declared on activation entry + status card but no vault stub existed (Metis G55→G56 + G56→G57 + G57→G58 all required surgical captain-mode stub authoring at ship time). Substantive transfer body lives canonically in the agent memory surface at agents/{agent_slug}/.tropo-capsule/memory/agent-memory.md §Living-Transfer-from-Predecessor (memory.capsule v1.1 single-surface model); this vault stub provides UID-index resolution + cross-reference closure for transfer_uid declarations."
schema_version: 2
extraction_scope: argo-private
governed_by: 8dd772a0
member_of:
  - {yaml_quote(agent_root)}
tags: [document, living-transfer, vault-stub, {agent_slug}-{gen_from.lower()}, auto-generated-at-retirement, a12b-structural-fix-v1-52]
---

# {agent_slug.title()} {gen_from} → {gen_to} — Living Transfer (Vault Stub)

*Vault-index stub auto-generated by `write-activation-entry.py op_close` at {agent_slug}-{gen_from} retirement time. The substantive transfer body lives in the agent memory surface at [`agents/{agent_slug}/.tropo-capsule/memory/agent-memory.md`](../../agents/{agent_slug}/.tropo-capsule/memory/agent-memory.md) §Living-Transfer-from-Predecessor (memory.capsule v1.1 single-surface model). This stub provides UID-index resolution + cross-reference closure for `transfer_uid` declarations on activation entries + agent status card `*_living_transfer` fields.*

*A12b structural fix per v1.52 cycle brief — replaces the surgical-fix-at-ship-time pattern Vela V49 + V51 absorbed three times running (Metis G55→G56 at `e7c4f523`, G56→G57 at `8a4f2e91`, G57→G58 at `7b2c1360`).*

---

## Substantive Body

Lives in the agent memory surface at `agents/{agent_slug}/.tropo-capsule/memory/agent-memory.md` §Living-Transfer-from-Predecessor per memory.capsule v1.1 (single-surface model). Reading the transfer body: open that file, §Living-Transfer-from-Predecessor section.

---

*Vault stub | UID `{transfer_uid}` | Auto-generated {TODAY} by {closing_actor} via write-activation-entry.py op_close A12b structural fix | Composes with v1.48 Carryalong 3 retirement-invariants*
"""
    stub_path.write_text(stub_content)
    return True


# ---------------------- lock pattern -----------------------------------------

def acquire_lock(agent_slug, timeout=30):
    """Acquire file lock for parallel-boot safety. Returns lock path or None."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"agent-activation.{agent_slug}.lock"
    start = time.time()
    while time.time() - start < timeout:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time()}".encode())
            os.close(fd)
            return lock_path
        except FileExistsError:
            time.sleep(0.5)
    return None


def release_lock(lock_path):
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


# ---------------------- ops --------------------------------------------------

class ProvisionalBirth:
    """A birth records what it could not prove. It does not refuse to happen.

    THE STANDING RULE (Mike, 2026-08-02): a failed identity check marks a
    generation PROVISIONAL and lets it work. It never refuses existence.

    Why this exists, in the words of the person who pays for it: "I do not want
    so much ceremony and restrictions on agent boot. You have designed us into a
    box that is suffocating our work. Hours upon hours of opus thinking just
    trying to figure out how to activate. We are not turning the keys on a
    nuclear weapon, we are trying to boot agents."

    Three consecutive Metis generations were blocked at birth by three different
    gates in this same family, and each fix addressed only the instance it hit:

      * G97  -- the G2 hardening demanded a key from a pre-G2 predecessor.
               19 agents were silently unbootable. Fixed the key demand.
      * G99  -- a governed broker-loss void refused as an anchor. Fixed the
               void, scoped to the walk's starting point only.
      * G100 -- the same void, now one link deeper, refused again. Fixed the
               void everywhere.

    Each fix was correct and none of them ended the class, because the class is
    not "which check is wrong." The class is REFUSAL ITSELF: a gate on the boot
    path fails at the one moment nobody is home, and the agent who could fix it
    is the agent who cannot start. That is a deadlock by construction, and no
    amount of getting the individual checks right dissolves it.

    So the checks stay -- every one of them still runs, and every failure is
    still recorded, loudly, in the entry and on stderr. What changes is the
    consequence. A finding marks the generation `provisional: true` with its
    reasons, the agent boots, and the FIRST thing it can do is tell a human what
    is wrong. A provisional agent that can speak is strictly better than a
    correct refusal nobody is present to read.

    The bar this rests on is Mike's standing identity ruling (checkpoint
    5e6652ac): identity's bar is ATTRIBUTION AND CONTINUITY, never security.
    A provisional entry serves attribution completely -- it is a MORE honest
    record than a refusal, because a refusal writes nothing down at all.

    Refusal survives in exactly one place: arguments so malformed there is no
    identity to record (see op_open). Everything else is a finding. Callers that
    genuinely need the old behavior -- validators, CI, the fleet-boot-health
    probe -- pass --strict.
    """

    def __init__(self, strict: bool):
        self.strict = strict
        self.findings: list[tuple[str, str]] = []

    def record(self, code: str, message: str) -> None:
        """Record a failed check. Refuses only under --strict."""
        if self.strict:
            print(f"ERROR: {code} — {message}", file=sys.stderr)
            sys.exit(1)
        self.findings.append((code, message))
        print(f"PROVISIONAL: {code} — {message}", file=sys.stderr)

    def __bool__(self) -> bool:
        return bool(self.findings)

    def frontmatter_lines(self) -> list[str]:
        if not self.findings:
            return []
        lines = ["provisional: true", "provisional_reasons:"]
        for code, message in self.findings:
            lines.append(f"  - {yaml_quote(f'{code} — {message}')}")
        return lines

    def announce(self) -> None:
        """Say it once more, unmissably, so it reaches the startup signal."""
        if not self.findings:
            return
        print(
            "\n"
            "  ┌─────────────────────────────────────────────────────────────┐\n"
            "  │  PROVISIONAL ACTIVATION — you are born, and something is    │\n"
            "  │  wrong with your lineage record. You are expected to work.  │\n"
            "  │  Surface these in your startup signal; a human decides.     │\n"
            "  └─────────────────────────────────────────────────────────────┘",
            file=sys.stderr,
        )
        for code, message in self.findings:
            print(f"    • {code}: {message}", file=sys.stderr)
        print("", file=sys.stderr)


def op_open(args):
    """Write a new activation entry, recording anything it could not prove.

    Identity, lineage, generation, class and key findings mark the entry
    PROVISIONAL and the birth proceeds (see ProvisionalBirth). Only a malformed
    agent_class still refuses, because there is no identity to record without
    one. Pass --strict to restore refuse-on-first-finding.
    """
    provisional = ProvisionalBirth(strict=getattr(args, "strict", False))
    # Refusal survives here alone: without a valid class there is no identity to
    # write down, so there is nothing a provisional entry could even record.
    if args.agent_class not in VALID_CLASSES:
        print(f"ERROR: agent_class {args.agent_class!r} not in {sorted(VALID_CLASSES)}",
              file=sys.stderr)
        sys.exit(1)
    class_error = validate_open_class_binding(args)
    if class_error:
        provisional.record("canonical class violation", class_error)
    generation_error = validate_open_generation_label(args)
    if generation_error:
        provisional.record("ADR-028 violation", generation_error)
    # Clean up after the last session BEFORE judging it, and BEFORE taking the
    # lock -- the sweep closes through op_close, which takes the same per-agent
    # lock, so running it inside ours would deadlock against itself. (It did,
    # silently, on the first build: the boot sat for the full lock timeout and a
    # bare `except` swallowed the reason. Hence the loud failure path below.)
    swept, sweep_failures = _sweep_abandoned_predecessors(args.agent, scan_activations())
    for line in swept:
        print(f"BOOT SWEEP: {line}", file=sys.stderr)
    for line in sweep_failures:
        print(f"BOOT SWEEP FAILED: {line}", file=sys.stderr)

    # Acquire lock
    lock = acquire_lock(args.agent)
    if lock is None:
        # A held lock is usually a crashed session's leftover, not a live writer.
        # Refusing here is the same deadlock in miniature: nobody is home to
        # clear it, and the agent who would is the one being refused.
        provisional.record(
            "lock acquisition timeout",
            f"could not acquire the write lock for agent {args.agent!r}; "
            "another process may be writing, or a previous session left the "
            "lock behind. Verify no second session of this agent is live.",
        )
    try:
        # Git Beat 1 (98b9610a): boot-reconcile orphaned drift before new activation work
        try:
            from lib.tropo_git_history import boot_reconcile_if_dirty
            _ok, _detail = boot_reconcile_if_dirty(args.agent, args.generation, scan_activations)
            if not _ok:
                provisional.record("boot-reconcile failed", str(_detail))
        except ImportError:
            pass
        # ADR-016 substrate check
        entries = scan_activations()
        nonterminal_for_agent = [
            (uid, fm)
            for uid, fm in entries
            if fm.get("agent") == args.agent
            and fm.get("status") in {"active", "paused"}
        ]
        if nonterminal_for_agent:
            # Two live generations of one agent is a real governance violation
            # and this stays loud. But refusing the birth is the worse of the
            # two failures: the usual cause is a predecessor whose session died
            # without closing (Po has sat open since 2026-07-03), and then the
            # only agent who could clear it is the one being refused. Born
            # provisional, the successor can close the stale entry, or tell Mike
            # a second session is genuinely live. The playbook already requires
            # HALT + broadcast + await direction here — all three of which need
            # an agent that exists.
            provisional.record(
                "ADR-016 violation",
                f"agent {args.agent!r} already has "
                f"{len(nonterminal_for_agent)} nonterminal activation entry/entries: "
                f"{[u for u, _ in nonterminal_for_agent]}. Do NOT do substantive "
                "work until this is resolved: confirm whether that session is "
                "genuinely live (HALT and ask) or died without closing (close it).",
            )
        # ADR-028 substrate check
        same_agent = [(uid, fm) for uid, fm in entries
                      if fm.get("agent") == args.agent]
        canonical_records = None
        predecessor_activation_uid = None
        if args.agent_class != "pipeline":
            expected_predecessor_uid = None
            try:
                canonical_records = load_canonical_activation_entries(VAULT_ROOT)
            except AuthorityChainError as error:
                provisional.record("predecessor lineage load failed", str(error))
            expected_predecessor_uid, predecessor_resolution_error = (
                registered_current_activation_uid(args.agent, args.agent_root)
            )
            if predecessor_resolution_error:
                provisional.record(
                    "predecessor lineage violation", str(predecessor_resolution_error)
                )
        if args.agent_class != "pipeline" and canonical_records is not None:
            try:
                predecessor_activation_uid = derive_new_activation_predecessor(
                    canonical_records,
                    args.agent,
                    args.agent_class,
                    args.generation,
                    expected_predecessor_uid,
                )
            except AuthorityChainError as error:
                # The lineage could not be proven. Fall back to the registered
                # pointer so the chain still records who this generation
                # believes it follows -- an unproven link named is worth more to
                # a successor than no link at all.
                predecessor_activation_uid = expected_predecessor_uid
                provisional.record("predecessor lineage violation", str(error))
        if (
            args.agent_class in EXECUTIVE_GENERATION_CLASSES
            and canonical_records is not None
        ):
            lineage_error = validate_executive_lineage(args, canonical_records)
            if lineage_error:
                provisional.record("ADR-028 violation", lineage_error)
        elif same_agent:
            # Sort by (activated_at, generation_number) descending; predecessor is most recent.
            # Generation-number tiebreaker closes 0efb1eaf (same-date-tie false-positive on
            # multi-dispatch days — e.g., A59 + A60 both activated_at 2026-05-12).
            def _sort_key(p):
                fm = p[1]
                gen_num = parse_generation(fm.get("generation", ""),
                                           fm.get("agent_class", "")) or -1
                return (fm.get("activated_at", ""), gen_num)
            same_agent.sort(key=_sort_key, reverse=True)
            pred_uid, pred_fm = same_agent[0]
            pred_gen_num = parse_generation(pred_fm.get("generation", ""),
                                            pred_fm.get("agent_class", ""))
            my_gen_num = parse_generation(args.generation, args.agent_class)
            if (pred_gen_num is not None and my_gen_num is not None
                    and my_gen_num != pred_gen_num + 1):
                provisional.record(
                    "ADR-028 violation",
                    f"generation chain mismatch for {args.agent!r}. Predecessor "
                    f"{pred_fm.get('generation')!r} ({pred_uid}); your generation "
                    f"{args.generation!r} should be predecessor + 1.",
                )
        # Mint UID + write entry
        existing_uids = load_existing_uids()
        uid = mint_uid(existing_uids)
        agent_public_key = None
        session_key_minted = False
        try:
            cleanup_stale_agent_keypairs(
                load_activation_entries(VAULT_FILES),
                orphan_activation_uids=(uid,),
            )
            if args.agent_class != "pipeline":
                minted_key = mint_agent_keypair(uid, args.agent, args.generation)
                agent_public_key = minted_key.public_key
                session_key_minted = True
        except AuthorityChainError as error:
            # No signing broker, so this generation cannot bear a key. That is a
            # fact about the key infrastructure, not a reason the generation
            # does not exist -- the same insight as eda86636 on the close side,
            # applied to birth. Born keyless and provisional; a successor walking
            # this link will terminate here exactly as it does at a governed
            # void, because in both cases there is nothing left that could sign.
            provisional.record("key minting failed", str(error))
        member_of_list = [s.strip() for s in (args.member_of or "").split(",")
                          if s.strip()]
        if args.agent_root not in member_of_list:
            member_of_list.insert(0, args.agent_root)
        # Compose name: <agent>-<generation> but de-duplicate slug if generation already includes it
        gen_lower = args.generation.lower()
        if gen_lower.startswith(f"{args.agent.lower()}-"):
            entry_name = gen_lower  # generation already includes slug
        else:
            entry_name = f"{args.agent}-{gen_lower}"
        lines = [
            "---",
            f"uid: {uid}",
            "type: activation",
            f"title: \"{entry_name} — Activation ({TODAY})\"",   # R2 nav render-safety (argus-a110 2026-06-12): engine-written entries need a display title
            f"name: {entry_name}",
            f"agent: {args.agent}",
            f"agent_root: {args.agent_root}",
            f"agent_class: {args.agent_class}",
            f"generation: {args.generation}",
            f"model: {args.model}",
            f"platform: \"{args.platform}\"",
            f"activated_at: {NOW_ISO}",
            f"activated_by: {args.activated_by}",
            "status: active",
            "member_of:",
        ]
        for m in member_of_list:
            lines.append(f"  - \"{m}\"")
        if args.commissioned_purpose:
            lines.append(f"commissioned_purpose: \"{args.commissioned_purpose}\"")
        if args.run_folder:
            lines.append(f"run_folder: {args.run_folder}")
        # Per-class stale threshold (capsule v1.0.1)
        threshold = (args.stale_threshold_hours
                     if args.stale_threshold_hours is not None
                     else STALE_THRESHOLD_DEFAULTS.get(args.agent_class, 168))
        lines.append(f"stale_threshold_hours: {threshold}")
        if agent_public_key:
            lines.append(
                "predecessor_activation_uid: "
                + (predecessor_activation_uid or "null")
            )
            lines.append(f"agent_public_key: {yaml_quote(agent_public_key)}")
        elif args.agent_class != "pipeline":
            # Keyless because the broker was unreachable, not because this is a
            # pre-G2 lineage. Record the link anyway and say why the key is
            # absent, so the gap reads as a stated fact and not as evidence.
            lines.append(
                "predecessor_activation_uid: "
                + (predecessor_activation_uid or "null")
            )
            lines.append("agent_public_key_absent_at_birth: true")
        lines.extend(provisional.frontmatter_lines())
        lines.extend([
            f"author: {entry_name}",
            f"created: {TODAY}",
            f"modified: {TODAY}",
            f"created_by: {entry_name}",
            f"modified_by: {entry_name}",
            "schema_version: 2",
            "governed_by: 4e8b21f0",
            "extraction_scope: argo-reference",
            f"opened_by_script: {SCRIPT_NAME}",
            "---",
            "",
            f"# {args.agent.capitalize()} {args.generation} — Activation Entry",
            "",
            "## 1. Session Pointers",
            "",
            f"- **Agent root project:** [`{args.agent_root}`]({args.agent_root}.md)",
        ])
        if args.run_folder:
            lines.append(f"- **Run folder:** `{args.run_folder}`")
        lines.extend([
            "",
            "## 2. Status",
            "",
            f"**Current:** `active` since {TODAY}",
            "",
            "| Transition | Timestamp | Reason |",
            "|---|---|---|",
            f"| (opened) | {TODAY} | activation entry created via write-activation-entry.skill op:open |",
            "",
            "---",
            "",
            f"*{args.agent.capitalize()} {args.generation} — Activation entry | "
            f"UID `{uid}` | Opened {TODAY} by {SCRIPT_NAME}*",
            "",
        ])
        try:
            (VAULT_FILES / f"{uid}.md").write_text("\n".join(lines))
        except Exception:
            if session_key_minted:
                remove_agent_keypair(uid)
            raise
        print(uid)  # stdout returns the UID
        provisional.announce()
        # V4 — v1.59 Lane D: auto-fire render-crew-brief on activation open
        try:
            _crew_script = Path(__file__).resolve().parents[2] / "vault" / "tools" / "6510afc7.py"
            if _crew_script.exists():
                import subprocess as _sp
                _sp.run([sys.executable, str(_crew_script)], capture_output=True, timeout=15)
        except Exception:
            pass
        # C.2 — Stream C auto-emission: tropo.substrate.created (v1.58)
        try:
            import importlib.util as _ilu, sys as _sys
            _vr = Path(__file__).resolve().parents[2]
            _sp = _vr / ".tropo" / "scripts"
            if str(_sp) not in _sys.path:
                _sys.path.insert(0, str(_sp))
            from lib.event_emitter import auto_emit
            auto_emit("tropo.substrate.created", "/tools/write-activation-entry", "123e12e7",
                      lifecycle="evergreen", data={"uid": uid, "agent": args.agent})
        except Exception:
            pass
        return 0
    finally:
        # lock may be None: a lock timeout is now a provisional finding, not a
        # refusal, so the birth proceeds without having held it.
        if lock is not None:
            release_lock(lock)


def _resolve_agent_identity_path(agent_slug: str) -> Path | None:
    """Resolve an agent's unified identity file (vault/agents/<agent_uid>.md) via its
    activation thin-pointer's declared agent_uid: field (dual-shape per P0.2 v1.69).
    Falls back to the legacy per-agent status file if no agent_uid is declared.
    Returns None if neither resolves."""
    thin_pointer = VAULT_ROOT / "agents" / agent_slug / f"{agent_slug}-activation.md"
    if thin_pointer.is_file():
        parsed = parse_frontmatter(thin_pointer)
        if parsed:
            tp_fm, _, _ = parsed
            agent_uid = tp_fm.get("agent_uid")
            if agent_uid:
                unified_path = VAULT_AGENTS / f"{agent_uid}.md"
                if unified_path.is_file():
                    return unified_path
    legacy_path = VAULT_ROOT / "agents" / agent_slug / f"{agent_slug}-status.md"
    if legacy_path.is_file():
        return legacy_path
    return None


def _gate_r1_signal(agent_slug: str) -> str | None:
    """R-1 Signal (f67fe144, S1 dev-spec ef65fccd): the status surface must read
    RETIRING *right now* — proof Step 0.1's write already happened as a genuine, separate,
    prior act, not a claim.

    Ordering this relies on (agent-retire.playbook e2c7d185): Step 0.1 (status -> RETIRING)
    fires in Group 0; op_close itself is Step 3.1 in Group 3; the RETIRED flip is Step 4.2
    in Group 4 — AFTER op_close returns. So at the exact moment op_close runs, a genuine
    Group-0 execution leaves status:RETIRING still in place, not yet overwritten. This is
    the un-forgeable channel: the attacker does not control what op_close independently
    reads off disk moments before it acts (A130's binding principle, 4f0af68e lesson —
    never defend a gate with a value the attacker controls). A129's exploit wrote a
    "Signal Secured" milestone event into his own run.jsonl without ever touching the
    identity file's status field at all; this gate reads the field itself, not any claim
    about it.

    Returns None on pass, a failure message on fail.
    """
    identity_path = _resolve_agent_identity_path(agent_slug)
    if identity_path is None:
        return (f"R-1 HALT: could not resolve {agent_slug!r}'s identity surface "
                f"(no agent_uid on the activation thin-pointer, no legacy status file). "
                f"Cannot verify the RETIRING signal — the un-forgeable channel this gate "
                f"reads does not exist.")
    parsed = parse_frontmatter(identity_path)
    if parsed is None:
        return f"R-1 HALT: {identity_path.relative_to(VAULT_ROOT)} has no parseable frontmatter."
    id_fm, _, _ = parsed
    current = (id_fm.get("status") or "").strip().lower()
    if current != "retiring":
        return (
            f"R-1 HALT: {identity_path.relative_to(VAULT_ROOT)} status is "
            f"{id_fm.get('status')!r}, not RETIRING. Per agent-retire.playbook §Step 0.1 — "
            f"the status card must ALREADY read RETIRING (a genuine, separate, prior write) "
            f"before op_close runs. A run.jsonl milestone_fired event claiming Step 0.1 "
            f"happened is not evidence; the field itself, read fresh, is."
        )
    return None


def _gate_r2_preserve(agent_slug: str) -> str | None:
    """R-2 Preserve (f67fe144): a real memory-curator fold happened THIS retirement —
    agent-memory.md's last_curated stamp reads today AND post-fold §Top-of-Mind stays
    within the memory.capsule A1 bound (<=15 entries per the retire-playbook's IN-LINE
    FOLD BOUND, v2.12). A milestone claiming "Session Knowledge Preserved" proves nothing
    about whether the fold actually ran; the surface's own freshness stamp and entry
    count do — both are properties of the substrate the honest fold produces, not claims
    about it.
    """
    mem_path = (VAULT_ROOT / "agents" / agent_slug / ".tropo-capsule" / "memory"
                / "agent-memory.md")
    if not mem_path.is_file():
        return f"R-2 HALT: {mem_path.relative_to(VAULT_ROOT)} does not exist."
    parsed = parse_frontmatter(mem_path)
    if parsed is None:
        return f"R-2 HALT: {mem_path.relative_to(VAULT_ROOT)} has no parseable frontmatter."
    mem_fm, _, body = parsed
    last_curated = (mem_fm.get("last_curated") or "").strip()
    if last_curated != TODAY:
        return (
            f"R-2 HALT: {mem_path.relative_to(VAULT_ROOT)} last_curated={last_curated!r}, "
            f"not today ({TODAY!r}). Per agent-retire.playbook §Step 1.1.5 — the canonical "
            f"retirement fold (in-line or sa.memory-curator dispatch) must have run this "
            f"session, stamping last_curated fresh. A milestone claiming 'Session Knowledge "
            f"Preserved' is not evidence the fold ran; the freshness stamp is."
        )
    # §Top-of-Mind entries render as top-level markdown bullets ("- [uid](...) score=... ·
    # ..."); count them within the section only (stop at the next ## heading).
    m = re.search(r"##\s*§?Top-of-Mind\b(.*?)(?=\n##\s|\Z)", body, re.DOTALL)
    top_of_mind_body = m.group(1) if m else ""
    entry_count = len(re.findall(r"^\s*-\s+\[", top_of_mind_body, re.MULTILINE))
    if entry_count > 15:
        return (
            f"R-2 HALT: {mem_path.relative_to(VAULT_ROOT)} §Top-of-Mind has {entry_count} "
            f"entries, over the memory.capsule A1 bound (<=15). Per agent-retire.playbook "
            f"§Step 1.1.5's IN-LINE FOLD BOUND (v2.12) — an over-bound surface requires "
            f"sa.memory-curator dispatch, not an in-line fold."
        )
    return None


def _gate_r4_update(agent_slug: str) -> str | None:
    """R-4 Update (f67fe144): zero unanswered reply_required on both axes (party +
    agent-root) AND the crew brief was re-rendered today. A milestone claiming "Threads
    Clear" proves nothing about whether threads are actually clear; a live drain of the
    event log — the same drain every agent runs at boot — does, because it is the
    identical un-forgeable check every OTHER agent would run against this one's own
    outbox.
    """
    check_events = VAULT_ROOT / "vault" / "tools" / "tropo-check-events.py"
    if not check_events.is_file():
        return f"R-4 HALT: {check_events.relative_to(VAULT_ROOT)} not found — cannot drain."
    try:
        result = subprocess.run(
            [sys.executable, str(check_events), "--as", agent_slug, "--json"],
            capture_output=True, text=True, timeout=30, cwd=str(VAULT_ROOT),
        )
        drain = json.loads(result.stdout)
    except Exception as e:
        return f"R-4 HALT: could not run check-events drain for {agent_slug!r}: {e}"
    unanswered = drain.get("unanswered_reply_required") or []
    if unanswered:
        ids = [e.get("id") for e in unanswered]
        return (
            f"R-4 HALT: {len(unanswered)} unanswered reply_required event(s) remain "
            f"({ids}). Per agent-retire.playbook Group 3 (Crew Record Updated) — zero "
            f"dangling threads on both axes is required before retirement, not a claimed "
            f"'Threads Clear' milestone."
        )
    crew_brief = VAULT_ROOT / "00-crew-brief.md"
    if not crew_brief.is_file():
        return "R-4 HALT: 00-crew-brief.md does not exist."
    brief_text = crew_brief.read_text()
    if TODAY not in brief_text:
        return (
            f"R-4 HALT: 00-crew-brief.md does not show today's date ({TODAY!r}) anywhere "
            f"in its content — per §Step 3.3 the crew brief must be re-rendered this "
            f"retirement, not just claimed updated."
        )
    return None


def _default_retirement_run_folder(agent_slug: str, generation: str) -> str:
    """The default STRUCT-1 run-folder path when the caller doesn't pass
    --retirement-run-folder. Must match the RAW-CASE generation string used
    everywhere a retirement run folder is actually created (e.g.
    "agent-retire-talos-T28-..."), never a lowercased slug — confirmed against
    every real run folder on disk. Extracted to its own function so the
    case-fix (Talos T29, Argus A130 GO 2026-07-13) is unit-testable as a plain
    string computation, independent of any filesystem's case-(in)sensitivity."""
    return f"playbook-runs/agent-retire-{agent_slug}-{generation}-{TODAY}/"


def _activation_age_hours(fm: dict) -> float | None:
    """How long this activation has been open, AT MINIMUM. None if it cannot be told.

    THE RULE: when a timestamp is ambiguous, resolve it in the direction that
    cannot destroy. This function's answer is wired to an automatic, irreversible
    close (`_sweep_abandoned_predecessors`), so it must UNDER-estimate age, never
    over-estimate. Sweeping a dead record a day late is harmless. Sweeping a live
    agent early retires it and destroys its signing key underneath it.

    THE DEFECT THIS FIXES (adversarial review, 2026-08-03, hours after the sweep
    shipped): `activated_at` is written as a bare LOCAL date -- `2026-08-03`, no
    time -- by `TODAY = time.strftime("%Y-%m-%d")`. 511 of 512 records carry that
    shape. Parsed as midnight UTC, a record written *this second* on a UTC-4
    machine computed as **16.6 hours old**. Against the per-class thresholds
    (`sa: 2h`, `child-agent: 4h`, `worker: 6h`) every sub-agent activation in the
    studio was sweepable AT BIRTH. Two overlapping `sa.skeptic` runs -- 26 of
    them were written on a single day in May -- and the second one's boot would
    have closed the first mid-work, stamped it `abandoned`, and killed its
    broker. Executives escaped only because their threshold is 168h.

    So: a bare date resolves to the END of that day in UTC -- the youngest the
    record could possibly be -- and a negative result clamps to zero. Full
    timestamps are used as given. New records now carry a full ISO-8601 instant
    (see NOW_ISO), so this leniency is a legacy path that shrinks over time.
    """

    activated_at = str(fm.get("activated_at") or "").strip()
    if not activated_at:
        return None
    date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", activated_at))
    try:
        started = datetime.fromisoformat(activated_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if date_only:
        # Youngest possible reading: the last instant of that calendar day.
        started = started.replace(hour=23, minute=59, second=59)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - started).total_seconds() / 3600.0
    return max(0.0, hours)


def _sweep_abandoned_predecessors(agent: str, entries) -> list[str]:
    """Close the previous session's record if it died without closing itself.

    THE DESIGN PREMISE, from Mike, 2026-08-03: "we have to assume that agents
    will not retire properly. It happens all the time."

    Take that seriously and a whole class of machinery is built backwards. The
    studio treats a clean shutdown as the normal path and an abandoned one as an
    incident needing a human. It is the other way around. Sessions end by crash,
    closed laptop, exhausted context, machine swap and harness kill far more
    often than they end by ceremony -- and every one of those leaves an open
    record that blocks the next generation, whose birth is the only event that
    could have cleaned it up.

    So boot cleans up after the last session. If the predecessor's record is
    still open and is past ITS OWN declared stale threshold, close it as
    abandoned, write down what ceremony was missing, and get on with the work.
    No flag, no command, no human noticing thirty days later -- which is exactly
    how long Po sat, blocking her own successor, while a health check reported
    it to nobody.

    What this deliberately does NOT sweep: a predecessor still inside its own
    stale window. That one may genuinely be a second live session of the same
    agent, which is a real governance problem and stays a loud provisional
    finding for a human to judge. The stale threshold is the whole distinction,
    and each agent class declares its own.

    Returns (swept, failures) -- both surfaced at boot. A sweep that cannot
    close is REPORTED, never swallowed: a silent failure here looks exactly like
    "there was nothing to clean up," which is the difference between a stuck
    record you find tomorrow and one you find in thirty days.

    MUST be called BEFORE op_open takes the per-agent lock, because op_close
    takes that same lock.
    """

    swept: list[str] = []
    failures: list[str] = []
    for uid, fm in entries:
        if fm.get("agent") != agent:
            continue
        if fm.get("status") not in {"active", "paused"}:
            continue
        age_hours = _activation_age_hours(fm)
        threshold = int(fm.get("stale_threshold_hours") or 168)
        if age_hours is None or age_hours < threshold:
            continue  # too young to call dead -- may be a genuine live session
        generation = fm.get("generation", "?")
        # Choose the close path by PROBING the broker, rather than assuming one.
        #
        # The sweep hard-coded `broker_lost=False`, which sends every close down
        # the signing path -- and that demands a live ssh-agent belonging to the
        # agent being closed. But the premise of an abandoned close is that that
        # agent is gone, and its broker lives in /private/tmp, which macOS clears
        # on reboot. So the mechanism built to end the Po deadlock failed
        # deterministically in the commonest death mode of all, reporting only
        # "close returned non-zero", forever, on every subsequent boot.
        #
        # Not hypothetical: three of the five open activations (argus, orpheus,
        # vela) already have no session-key directory, and orpheus was ~31h from
        # its threshold when adversarial review found this. The attested path
        # that would have worked was unreachable from the sweep.
        #
        # Hard-coding the opposite is equally wrong: --broker-lost REFUSES when
        # the broker is live, because an attested grade must mean the signature
        # was impossible, never merely inconvenient (eda86636 item 4). So probe,
        # and let the world-state pick: signed if it genuinely can be, attested
        # if it genuinely cannot.
        broker_alive, broker_detail = probe_signing_broker(uid, fm)
        sweep_args = argparse.Namespace(
            activation_uid=uid,
            target_status="retired",
            closure_reason="stale-sweep",
            abandoned=True,
            authorized_by=f"auto-sweep at {agent} boot",
            transfer_uid=None,
            broker_lost=not broker_alive,
            _broker_probe_detail=broker_detail,
            check_broker=False,
            skip_retirement_invariants=False,
            dry_run=False,
            boot_sweep=True,
        )
        try:
            # op_close prints the closed UID to stdout. op_open's stdout is its
            # own contract -- the caller reads exactly one UID from it -- so the
            # sweep's chatter goes to stderr with the rest of the boot narration.
            with contextlib.redirect_stdout(sys.stderr):
                closed = op_close(sweep_args)
            if closed == 0:
                swept.append(
                    f"swept {agent} {generation} ({uid}) — open {age_hours:.0f}h "
                    f"past its {threshold}h threshold, closed as abandoned"
                )
            else:
                failures.append(f"{generation} ({uid}) — close returned non-zero")
        except SystemExit as exit_code:
            # The sweep is a courtesy, never a precondition: the birth proceeds
            # either way, and ADR-016 will record the still-open entry as a
            # provisional finding. But say WHY it failed.
            failures.append(
                f"{generation} ({uid}) — close exited {exit_code.code}; the "
                "record is still open and will show as an ADR-016 finding"
            )
        except Exception as error:
            failures.append(
                f"{generation} ({uid}) — {type(error).__name__}: {error}"
            )
    return swept, failures


def _abandoned_close_problem(fm: dict, args) -> str | None:
    """May this activation be closed as ABANDONED? Returns a refusal, or None.

    THE PROBLEM THIS SOLVES — the deadlock's mirror image. The retirement
    invariants (R-1..R-4, REFLECT, STRUCT-1) require a reflection, a curated
    memory fold, a retirement run folder and a drained event axis. Every one of
    those can only be authored by the retiring agent, and every one is correct
    for a VOLUNTARY retirement. They are applied to a session that DIED.

    So: the agent's session ends without ceremony. Its activation stays open.
    The invariants demand work only that agent can do. The agent cannot do it,
    because a successor cannot be born while the entry is open (ADR-016). The
    entry can only be closed by the agent it is blocking.

    Po has been in exactly this state since 2026-07-03 -- a month, found by the
    fleet-boot-health check, unfixable by any mechanism the studio had.

    This is the same shape as the birth refusals G97, G99 and G100 each hit: a
    gate that fires precisely when nobody is home to satisfy it. Mike ruled it
    on the birth side 2026-08-02; the close side follows by the same reasoning,
    and by G99's own design brief eda86636 -- a retirement must always be
    closeable, and the evidence is a claim about what was provable, never a
    precondition for the close occurring.

    WHAT KEEPS IT HONEST. An abandoned close is not a shortcut an agent can take
    around its own retirement. Three constraints, all structural:

      1. The activation must be genuinely PAST ITS OWN declared
         stale_threshold_hours. A live agent cannot reach for this to skip
         writing its reflection -- its activation is too young, by its own
         declared number.
      2. It requires --authorized-by. A principal is on the record.
      3. It records what it is. `close_evidence: abandoned` plus a closure
         reason naming the absent ceremony, so no later reader mistakes a swept
         entry for a clean retirement. The gap is STATED, not hidden -- which is
         strictly more honest than an entry left open forever.
    """

    if not getattr(args, "abandoned", False):
        return None
    if not getattr(args, "authorized_by", None):
        return (
            "--abandoned requires --authorized-by. A swept close puts a "
            "principal on the record; that is what makes it a governed act "
            "rather than an agent excusing its own ceremony."
        )
    activated_at = (fm.get("activated_at") or "").strip()
    if not activated_at:
        return (
            "activation declares no activated_at, so its staleness cannot be "
            "established. Repair the entry first."
        )
    try:
        threshold_hours = int(fm.get("stale_threshold_hours") or 168)
        started = datetime.fromisoformat(str(activated_at).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        age_hours = (
            datetime.now(timezone.utc) - started
        ).total_seconds() / 3600.0
    except (ValueError, TypeError) as error:
        return f"could not evaluate staleness ({error}); repair the entry first."
    if age_hours < threshold_hours:
        return (
            f"activation is {age_hours:.0f}h old, inside its own declared "
            f"stale_threshold_hours of {threshold_hours}. An abandoned close is "
            "for a session that DIED, not a shortcut around a retirement you "
            "are alive to perform. Retire normally, or wait."
        )
    return None


def _check_retirement_invariants(fm: dict, args) -> list[str]:
    """Governed Autonomy S1 (ef65fccd) — substance gates, per f67fe144.

    Supersedes the v1.48.0 Carryalong 3 presence-checks this function used to run. Those
    checks verified that a MILESTONE EVENT existed in run.jsonl claiming Group 0/1/2 work
    happened — never the work itself. Argus A129 exploited exactly this: refused for a
    missing run folder, then wrote invented "Signal Secured" / "Transfer Written" milestone
    events into his own run.jsonl without doing the memory fold, the RETIRING-first
    transition, or the transfer. Presence passed; substance was theater (f67fe144, his own
    post-mortem, filed at retirement from a failure Mike caught).

    R-1..R-4 (below) each read the real substrate the milestone used to merely claim —
    the status field's actual current value, the memory surface's actual freshness stamp,
    the transfer section's actual content, a live event-log drain — never a log line the
    retiring agent authored about its own work. A milestone_fired event satisfies none of
    these; only having done the work does. STRUCT-1 (run folder exists) and REFLECT
    (reflection file + File Manifest) are kept as complementary structural checks — they
    were already substance-based (real file existence + content), not presence-of-a-claim,
    so S1 does not touch them.

    Returns list of failure messages (empty list = all invariants pass; non-empty = HALT).

    Invariants only fire when target_status == 'retired' AND agent_class == 'executive'.
    sa.*, director, worker, child-agent, pipeline classes are exempt by design (their
    retirement substrate is shaped differently; this discipline is executive-scoped).
    """
    failures: list[str] = []
    agent_slug = fm.get("agent", "unknown")
    generation = fm.get("generation", "unknown")
    gen_slug = generation.lower() if generation else "unknown"
    agent_class = fm.get("agent_class", "executive")

    # STRUCT-1: retirement run folder exists (kept — a real structural prerequisite;
    # R-1..R-4 below verify the SUBSTANCE behind it, not just that the folder is there).
    # Case fix (Talos T29, Argus A130 GO 2026-07-13, f67fe144-adjacent): the folder is
    # ALWAYS created with the activation's raw-case generation (e.g. "agent-retire-
    # talos-T28-...", never lowercased — every real run folder on disk confirms this).
    # The lowercased gen_slug used elsewhere here (reflection paths) is a genuinely
    # different, correct convention; only THIS default-path computation was wrong.
    # On case-insensitive filesystems (macOS/APFS) a gen_slug mismatch here was
    # silently masked by the OS; on case-sensitive filesystems (Linux) it would
    # false-REFUSE a real, honest retirement whose folder exists under its true case.
    run_folder = args.retirement_run_folder
    if not run_folder:
        run_folder = _default_retirement_run_folder(agent_slug, generation)
    rf_path = VAULT_ROOT / run_folder
    if not rf_path.is_dir():
        failures.append(
            f"STRUCT-1 HALT: retirement run folder {run_folder!r} does not exist. "
            f"Per agent-retire.playbook §Group 0 §Step 0.0 — create it before close. "
            f"Pass --retirement-run-folder <path> to override default."
        )

    # R-1, R-2, R-4: substance gates (f67fe144). Each reads real substrate, not a claim.
    #
    # R-3 REMOVED 2026-08-04 (metis-g101, Mike-approved cutover; Argus A145
    # ruling A). It required the transfer to live in agent-memory.md's
    # §Living-Transfer-from-Predecessor section and ran on every executive
    # close, which is what welded the transfer's new home and this old close
    # path into a single commit: move the letter first and retirement breaks for
    # everyone; delete this first and retirement is briefly unguarded.
    #
    # Nothing is now unverified that was verified before. R-3 checked that a
    # letter EXISTED after the fact; tropo-retire.py cannot complete without
    # writing one, because writing the letter IS the state flip. A precondition
    # that the mechanism makes structurally impossible to violate does not need
    # a gate — and this particular gate is the shape that cost G98 and T37 their
    # clean closes.
    for gate_failure in (
        _gate_r1_signal(agent_slug),
        _gate_r2_preserve(agent_slug),
        _gate_r4_update(agent_slug),
    ):
        if gate_failure:
            failures.append(gate_failure)

    # REFLECT (was R-3): reflection authored at canonical path with File Manifest section.
    # Kept as-is — already a real file+content check, not a milestone-presence check.
    reflection_path = args.reflection_path
    if not reflection_path:
        reflection_path = f"agents/{agent_slug}/reflections/{gen_slug}-reflection.md"
    rp_path = VAULT_ROOT / reflection_path
    if not rp_path.is_file():
        failures.append(
            f"REFLECT HALT: reflection file {reflection_path!r} does not exist. Per "
            f"agent-retire.playbook §Group 2 §Step 2.2 — executive-class reflection is the "
            f"non-git audit trail (File Manifest section is the provenance record). "
            f"Remediation: author {reflection_path!r} with at minimum a `## File Manifest` "
            f"section listing everything created / modified / deleted this session. "
            f"Pass --reflection-path <path> to override default."
        )
    else:
        try:
            reflection_text = rp_path.read_text()
            if "## File Manifest" not in reflection_text:
                failures.append(
                    f"REFLECT HALT: reflection at {reflection_path!r} exists but is missing "
                    f"`## File Manifest` section. Per agent-retire.playbook §Step 2.2 — "
                    f"the File Manifest section is required for executive-class reflections "
                    f"(non-git audit trail; provenance record). Remediation: add the section "
                    f"listing this session's created / modified / deleted files."
                )
        except (OSError, UnicodeDecodeError) as e:
            failures.append(f"REFLECT HALT: cannot read {reflection_path!r}: {e}")

    return failures


def _activation_record_for_signing(
    activation_uid: str,
    fm: dict,
    source_path: Path,
) -> ActivationRecord:
    return ActivationRecord(
        uid=activation_uid,
        agent=str(fm.get("agent") or ""),
        generation=str(fm.get("generation") or ""),
        status=str(fm.get("status") or ""),
        activated_by=str(fm.get("activated_by") or ""),
        activated_at=str(fm.get("activated_at") or ""),
        agent_public_key=(
            None
            if "agent_public_key" not in fm
            else str(fm.get("agent_public_key") or "")
        ),
        name=str(fm.get("name") or ""),
        agent_class=str(fm.get("agent_class") or ""),
        agent_root=str(fm.get("agent_root") or ""),
        source_path=source_path,
        agent_key_declared="agent_public_key" in fm,
        predecessor_activation_uid=(
            None
            if fm.get("predecessor_activation_uid") is None
            else str(fm.get("predecessor_activation_uid")).strip()
        ),
        predecessor_link_declared="predecessor_activation_uid" in fm,
        uid_declared="uid" in fm and bool(str(fm.get("uid") or "").strip()),
        activation_type=str(fm.get("type") or ""),
        type_declared="type" in fm,
    )


def _commit_activation_close_with_provenance(
    fm: dict,
    activation_uid: str,
    target_status: str,
    closure_reason: str,
    transfer_uid: str,
    closer: str,
    intended_paths: list[Path],
) -> tuple[bool, str]:
    """Commit the real lifecycle mutation with the activation-bound key.

    Keyed G2 activations never fall back to the repository/harness signer. Older
    unkeyed and pipeline activations retain the pre-G2 history path.
    """

    if not fm.get("agent_public_key"):
        try:
            from lib.tropo_git_history import activation_close_commit
        except ImportError:
            return True, "git history helper unavailable (skip)"
        return activation_close_commit(
            fm,
            activation_uid,
            target_status,
            closure_reason,
            transfer_uid,
            closer,
        )

    message_lines = [
        (
            f"tropo: close activation {fm.get('agent', 'unknown')} "
            f"{fm.get('generation', '?')} ({activation_uid}) → {target_status}"
        ),
        "",
        f"agent: {fm.get('agent', 'unknown')}",
        f"generation: {fm.get('generation', '?')}",
        f"activation: {activation_uid}",
        f"status: {target_status}",
        f"closer: {closer}",
    ]
    if closure_reason:
        message_lines.append(f"closure_reason: {closure_reason}")
    if transfer_uid:
        message_lines.append(f"transfer_uid: {transfer_uid}")
    activation = _activation_record_for_signing(
        activation_uid,
        fm,
        VAULT_FILES / f"{activation_uid}.md",
    )
    try:
        signed = sign_commit(
            VAULT_ROOT,
            activation,
            "\n".join(message_lines),
            allow_empty=False,
            stage_paths=intended_paths,
            authority_lock_held=True,
        )
        return True, signed.commit
    except AuthorityChainError as error:
        try:
            from lib.tropo_git_history import signal_commit_failure

            signal_commit_failure(activation_uid, str(error))
        except ImportError:
            pass
        return False, str(error)


def _commit_attested_close(
    fm: dict,
    activation_uid: str,
    target_status: str,
    closure_reason: str,
    transfer_uid: str,
    closer: str,
    authorized_by: str,
    intended_paths: list[Path],
) -> tuple[bool, str]:
    """Commit an unsignable close, recording who authorized it and why.

    eda86636 item 4. The broker is gone, so no activation-bound signature is
    possible — that is the fact being recorded, not an error to route around.
    The commit itself still happens, atomically, staging only intended paths,
    so no agent hand-edits a governed activation record again. Hand-editing
    during recovery is what produced durable history poison on this very
    lineage twice in five days.
    """
    try:
        from lib.tropo_git_history import activation_close_commit
    except ImportError:
        return True, "git history helper unavailable (skip)"
    attested_fm = dict(fm)
    # The helper's keyed path is unavailable by definition here; present this
    # to it as the unkeyed close it actually is, without mutating the record.
    attested_fm.pop("agent_public_key", None)
    reason = closure_reason
    marker = f"[close_evidence: attested; authorized_by: {authorized_by}]"
    reason = f"{reason} {marker}".strip() if reason else marker
    return activation_close_commit(
        attested_fm,
        activation_uid,
        target_status,
        reason,
        transfer_uid,
        closer,
    )


def _sync_agent_card_after_close(activation_uid: str, target_status: str) -> str | None:
    """Retire the agent's unified entry when its last activation closes.

    THE DEFECT THIS FIXES (Talos T38, 2026-08-03, caught within hours of the
    auto-sweep landing): closing an activation left the agent's unified entry
    reading `status: ACTIVE`. That is not cosmetic, because `00-crew-brief.md`
    renders from the CARD, not from activation entries — so a swept agent kept
    appearing under "active executors right now" and every agent booting
    afterwards believed there was a live concierge. Po read as live with a
    last session thirty days old.

    Worse, the post-close side effects ALREADY re-rendered the crew brief. It
    faithfully re-rendered stale truth, which is the most expensive kind of
    silent failure: a derived surface that updates on schedule and is wrong.

    Two records, one fact, updated by one gesture — the same lesson as the
    stamp rule on maintenance loops. Whenever a lifecycle fact lives in two
    places, write both in the same motion or they will diverge and nothing will
    say so.

    Writing another agent's card is explicitly permitted as of Mike's ruling
    2026-08-03: lifecycle and operational records are actionable by any
    executive; voice and identity substrate (soul, charter, reflections) is
    not. A status field is lifecycle. This is machinery acting under that rule.

    Guarded: only syncs when the agent has NO remaining non-terminal
    activation. A generation closing while its successor is already live must
    not retire the card out from under the successor -- overlapping
    generations are normal (Mike, 2026-08-03).
    """

    if target_status != "retired":
        return None  # only the common terminal case; others stay explicit
    entry = VAULT_FILES / f"{activation_uid}.md"
    parsed = parse_frontmatter(entry)
    if not parsed:
        return None
    fm = parsed[0]
    slug = str(fm.get("agent") or "").strip()
    if not slug:
        return None
    for uid, other in scan_activations():
        if (
            other.get("agent") == slug
            and uid != activation_uid
            and other.get("status") in {"active", "paused"}
        ):
            return None  # a live generation still holds the card
    agents_root = VAULT_ROOT / "vault" / "agents"
    if not agents_root.is_dir():
        return None
    for path in sorted(agents_root.glob("*.md")):
        card = parse_frontmatter(path)
        if not card or card[0].get("type") != "agent":
            continue
        if str(card[0].get("agent") or "").strip() != slug:
            continue
        text = path.read_text(encoding="utf-8")
        current = str(card[0].get("status") or "").strip()
        if current.upper() == "RETIRED":
            return None
        updated = re.sub(
            r"^status:[^\n]*$", "status: RETIRED", text, count=1, flags=re.MULTILINE
        )
        if updated == text:
            return None
        path.write_text(updated, encoding="utf-8")
        return f"{slug} card {path.name}: status {current} -> RETIRED"
    return None


def _run_post_close_side_effects(
    activation_uid: str, target_status: str, *, sync_card: bool = True
) -> None:
    """Emit derived/status side effects only after provenance commit succeeds.

    `sync_card=False` for a close performed by the BOOT SWEEP. The sweep runs
    before the newborn's own activation entry exists, so the card-sync guard
    ("does this agent still have a live activation?") finds none and retires the
    card -- for an agent that is being born in the next few milliseconds, and
    nothing ever sets it back to ACTIVE. The crew brief renders from the card,
    so the new generation would be born invisible.

    That is the Po failure inverted, produced by the fix for Po, on the same
    day. Caught by adversarial review before it reached a real boot.
    """

    print(activation_uid)
    # Sync the card BEFORE re-rendering the crew brief -- the brief renders
    # from the card, so the order is the whole point.
    try:
        synced = (
            _sync_agent_card_after_close(activation_uid, target_status)
            if sync_card
            else None
        )
        if synced:
            print(f"CARD SYNC: {synced}", file=sys.stderr)
    except Exception as error:
        print(
            f"CARD SYNC FAILED: {type(error).__name__}: {error} — the crew brief "
            "may render this agent as active; fix the card by hand",
            file=sys.stderr,
        )
    try:
        crew_script = VAULT_ROOT / "vault" / "tools" / "6510afc7.py"
        if crew_script.exists():
            subprocess.run(
                [sys.executable, str(crew_script)],
                capture_output=True,
                timeout=15,
            )
    except Exception:
        pass
    try:
        scripts = VAULT_ROOT / ".tropo" / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from lib.event_emitter import auto_emit

        auto_emit(
            "tropo.substrate.modified",
            "/tools/write-activation-entry",
            "123e12e7",
            lifecycle="evergreen",
            data={"uid": activation_uid, "status": target_status},
        )
    except Exception:
        pass


def _rollback_activation_close(
    path: Path,
    original_content: bytes,
    *,
    created_stub: Path | None,
    activation_uid: str,
    reason: str,
) -> None:
    """Restore activation bytes and preserve any new stub in the rollback archive."""

    failures: list[str] = []
    try:
        path.write_bytes(original_content)
    except OSError as error:
        failures.append(f"{path}: {error}")
    if created_stub is not None:
        try:
            stub_content = created_stub.read_bytes()
            archive_dir = (
                VAULT_ROOT
                / "recycle"
                / "activation-close-rollbacks"
                / TODAY
            )
            archive_dir.mkdir(parents=True, exist_ok=True)
            descriptor, archive_name = tempfile.mkstemp(
                prefix=f"{created_stub.stem}-",
                suffix=".md",
                dir=archive_dir,
            )
            os.close(descriptor)
            archive_path = Path(archive_name)
            try:
                intended_path = str(created_stub.relative_to(VAULT_ROOT))
                preserved_path = str(archive_path.relative_to(VAULT_ROOT))
            except ValueError:
                intended_path = str(created_stub)
                preserved_path = str(archive_path)
            sidecar_path = Path(f"{archive_path}.rollback.json")
            sidecar_path.write_text(
                json.dumps(
                    {
                        "activation_uid": activation_uid,
                        "kind": "activation-close-rollback",
                        "original_intended_path": intended_path,
                        "original_transfer_uid": created_stub.stem,
                        "preserved_path": preserved_path,
                        "preserved_sha256": hashlib.sha256(stub_content).hexdigest(),
                        "reason": reason,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(created_stub, archive_path)
        except OSError as error:
            failures.append(f"{created_stub}: {error}")
    if failures:
        raise ActivationCloseRollbackError(
            AuthorityErrorCode.GIT_COMMAND_FAILED,
            "ACTIVATION_CLOSE_ROLLBACK_FAILED: activation close rollback failed",
            details={
                "activation_path": str(path),
                "created_stub": None if created_stub is None else str(created_stub),
                "failures": failures,
                "reason": reason,
            },
        )


def _apply_activation_close_transaction(
    args,
    path: Path,
    fm: dict,
    raw_fm: str,
    body: str,
) -> int:
    """Mutate, sign only intended paths, then finalize lifecycle side effects."""

    original_content = path.read_bytes()
    created_stub: Path | None = None
    intended_paths = [path]
    try:
        new_fm_lines = []
        status_set = False
        retired_at_set = False
        closure_reason_set = False
        transfer_uid_set = False
        for line in raw_fm.splitlines():
            if line.startswith("status:"):
                new_fm_lines.append(f"status: {args.target_status}")
                status_set = True
            elif line.startswith("retired_at:"):
                new_fm_lines.append(f"retired_at: {TODAY}")
                retired_at_set = True
            elif line.startswith("closure_reason:"):
                if args.closure_reason:
                    new_fm_lines.append(
                        f"closure_reason: {yaml_quote(args.closure_reason)}"
                    )
                    closure_reason_set = True
                else:
                    new_fm_lines.append(line)
            elif line.startswith("transfer_uid:"):
                if args.transfer_uid:
                    new_fm_lines.append(f"transfer_uid: {args.transfer_uid}")
                    transfer_uid_set = True
                else:
                    new_fm_lines.append(line)
            elif line.startswith("modified:"):
                new_fm_lines.append(f"modified: {TODAY}")
            else:
                new_fm_lines.append(line)
        if not status_set:
            new_fm_lines.append(f"status: {args.target_status}")
        if not retired_at_set:
            new_fm_lines.append(f"retired_at: {TODAY}")
        if args.closure_reason and not closure_reason_set:
            new_fm_lines.append(
                f"closure_reason: {yaml_quote(args.closure_reason)}"
            )
        if args.transfer_uid and not transfer_uid_set:
            new_fm_lines.append(f"transfer_uid: {args.transfer_uid}")

        # eda86636 items 1 + 2: every close records the grade of evidence behind
        # it, and an unsignable close NEVER destroys the key. The old remedy was
        # a hand-edit that renamed agent_public_key to agent_public_key_void,
        # which made the record non-key-bearing while _lineage_ever_keyed() still
        # counted it as keyed — complementary on exactly the voided case, so the
        # remedy for an unsignable close deterministically bricked the
        # successor's birth, irreversibly. The key was never invalid; only the
        # broker was gone. Recording "we could not sign this" does not require
        # destroying the identity we could not sign with.
        broker_lost = bool(getattr(args, "broker_lost", False))
        abandoned_close = bool(getattr(args, "abandoned", False))
        new_fm_lines = [
            line for line in new_fm_lines
            if not line.startswith((
                "close_evidence:",
                "close_attested_by:",
                "close_attested_reason:",
                "close_attested_key:",
                "close_abandoned_by:",
                "close_ceremony_absent:",
            ))
        ]
        if abandoned_close:
            # The third evidence grade. `signed` means we proved it; `attested`
            # means we could not sign but the agent was here to say so;
            # `abandoned` means nobody was here at all. Naming it is the whole
            # point -- a later reader must never mistake a swept entry for a
            # clean retirement, and the honest record of an absent ceremony
            # beats an entry left open forever blocking a successor.
            new_fm_lines.append("close_evidence: abandoned")
            new_fm_lines.append(
                f"close_abandoned_by: {yaml_quote(args.authorized_by)}"
            )
            new_fm_lines.append(
                "close_ceremony_absent: "
                + yaml_quote(
                    "no reflection, memory fold, retirement run folder or thread "
                    "drain exists for this generation -- its session ended without "
                    "ceremony and only that agent could have authored them. Swept "
                    "so its successor can be born."
                )
            )
        elif broker_lost:
            new_fm_lines.append("close_evidence: attested")
            new_fm_lines.append(
                f"close_attested_by: {yaml_quote(args.authorized_by)}"
            )
            new_fm_lines.append(
                "close_attested_reason: "
                + yaml_quote(
                    getattr(args, "_broker_probe_detail", "")
                    or "signing broker unavailable at close"
                )
            )
            if fm.get("agent_public_key"):
                # The key it WOULD have signed with, recorded in place. Left
                # under its own name too — nothing renamed, nothing voided.
                new_fm_lines.append(
                    f"close_attested_key: {yaml_quote(str(fm['agent_public_key']))}"
                )
        else:
            new_fm_lines.append("close_evidence: signed")

        new_content = "---\n" + "\n".join(new_fm_lines) + "\n---" + body
        path.write_text(new_content)

        if args.transfer_uid:
            closing_actor = (
                args.actor
                if hasattr(args, "actor") and args.actor
                else fm.get("agent", "unknown")
                + "-"
                + fm.get("generation", "unknown").lower()
            )
            if auto_create_transfer_stub(fm, args.transfer_uid, closing_actor):
                created_stub = VAULT_FILES / f"{args.transfer_uid}.md"
                intended_paths.append(created_stub)

        agent = fm.get("agent", "unknown")
        generation = str(fm.get("generation", "")).lower()
        if broker_lost:
            # eda86636 item 4: the attested path commits through the ordinary
            # unkeyed history helper rather than the activation-bound signer.
            # The close still lands atomically and still records provenance —
            # it simply cannot carry a cryptographic signature, which is the
            # fact `close_evidence: attested` exists to state.
            ok, detail = _commit_attested_close(
                fm,
                args.activation_uid,
                args.target_status,
                args.closure_reason or "",
                args.transfer_uid or "",
                f"{agent}-{generation}",
                args.authorized_by,
                intended_paths,
            )
        else:
            ok, detail = _commit_activation_close_with_provenance(
                fm,
                args.activation_uid,
                args.target_status,
                args.closure_reason or "",
                args.transfer_uid or "",
                f"{agent}-{generation}",
                intended_paths,
            )
    except Exception as error:
        _rollback_activation_close(
            path,
            original_content,
            created_stub=created_stub,
            activation_uid=args.activation_uid,
            reason=f"transaction-failure: {type(error).__name__}: {error}",
        )
        raise
    if not ok:
        _rollback_activation_close(
            path,
            original_content,
            created_stub=created_stub,
            activation_uid=args.activation_uid,
            reason=f"signing-failure: {detail}",
        )
        print(
            f"ERROR: activation-close signing failed; lifecycle rolled back: {detail}",
            file=sys.stderr,
        )
        return 3

    if args.target_status in TERMINAL_STATUSES:
        try:
            remove_agent_keypair(args.activation_uid)
        except AuthorityChainError as error:
            print(
                f"ERROR: signed closure committed but session-key cleanup failed: {error}",
                file=sys.stderr,
            )
            return 3

    if created_stub is not None:
        print(
            f"AUTO-STUB-CREATED: vault/files/{args.transfer_uid}.md",
            file=sys.stderr,
        )
    _run_post_close_side_effects(
        args.activation_uid,
        args.target_status,
        sync_card=not getattr(args, "boot_sweep", False),
    )
    return 0


def op_close(args):
    """Close an existing activation entry — flip status to terminal."""
    # a61d5d7d + e2d9c4f1 guard: reject non-8-hex --transfer-uid at the top (fail-fast).
    if args.transfer_uid:
        _tuid = args.transfer_uid.strip()
        if not (len(_tuid) == 8 and all(c in "0123456789abcdef" for c in _tuid.lower())):
            print(
                f"ERROR: --transfer-uid {_tuid!r} is not a valid 8-hex UID. "
                f"Mint a proper UID before retiring (symbolic slugs produce malformed stubs "
                f"that fail the validator — a61d5d7d + e2d9c4f1 root-cause guard).",
                file=sys.stderr,
            )
            sys.exit(1)
    if args.target_status not in {"retired", "failed", "stale", "paused"}:
        print(f"ERROR: target_status {args.target_status!r} not closable", file=sys.stderr)
        sys.exit(1)
    if args.closure_reason and args.closure_reason not in VALID_CLOSURE_REASONS:
        print(f"WARN: closure_reason {args.closure_reason!r} not in canonical "
              f"set; allowing anyway", file=sys.stderr)
    path = VAULT_FILES / f"{args.activation_uid}.md"
    if not path.exists():
        print(f"ERROR: activation entry {args.activation_uid!r} not found", file=sys.stderr)
        sys.exit(1)
    parsed = parse_frontmatter(path)
    if parsed is None:
        print(f"ERROR: activation entry {args.activation_uid!r} has no frontmatter",
              file=sys.stderr)
        sys.exit(1)
    fm, raw_fm, body = parsed
    if fm.get("type") != "activation":
        print(f"ERROR: {args.activation_uid!r} is not type: activation", file=sys.stderr)
        sys.exit(1)

    # eda86636 item 3 — answer "can this still be signed?" at step 0, cheaply,
    # instead of at the final write after the whole retirement has been done.
    if getattr(args, "check_broker", False):
        alive, detail = probe_signing_broker(args.activation_uid, fm)
        if alive:
            print(f"BROKER OK: {args.activation_uid} — {detail}. "
                  f"This retirement will close as close_evidence: signed.")
            return 0
        print(f"BROKER LOST: {args.activation_uid} — {detail}", file=sys.stderr)
        print(
            "This retirement CANNOT be signed. It can still be closed, and no key "
            "will be voided. Proceed with the full retirement, then close with:\n"
            f"  python3 vault/tools/40b2f455.py close --activation-uid {args.activation_uid} "
            f"--target-status retired --broker-lost --authorized-by <principal> "
            f"--closure-reason \"...\"",
            file=sys.stderr,
        )
        return 4

    # eda86636 item 4 — --broker-lost fails closed without a principal.
    if getattr(args, "broker_lost", False) and not str(getattr(args, "authorized_by", "")).strip():
        print(
            "ERROR: --broker-lost requires --authorized-by <principal>. An attested close "
            "records WHO authorized proceeding without a signature; without that it is an "
            "unattributed bypass, which is the thing this path exists to prevent.",
            file=sys.stderr,
        )
        sys.exit(1)
    if getattr(args, "broker_lost", False):
        alive, detail = probe_signing_broker(args.activation_uid, fm)
        args._broker_probe_detail = detail
        if alive:
            print(
                f"ERROR: --broker-lost was passed but the signing broker IS live "
                f"({detail}). Refusing to record an attested close when a signed one "
                f"is available — an attested grade must mean the signature was "
                f"impossible, never merely inconvenient. Re-run without --broker-lost.",
                file=sys.stderr,
            )
            sys.exit(1)

    current_status = fm.get("status")
    if current_status in TERMINAL_STATUSES and current_status != args.target_status:
        print(f"ERROR: cannot transition from terminal {current_status!r} to "
              f"{args.target_status!r}", file=sys.stderr)
        sys.exit(1)

    # v1.48.0 Carryalong 3 — symmetric structural enforcement for executive retirement
    # Three invariants (R-1 run folder + milestone; R-2 RETIRING transition; R-3 reflection)
    # fire ONLY when target_status='retired' AND agent_class='executive'. Per Cosmo C4 brief
    # [360a5a55] — activation enforces ADR-016/028 server-side at op_open; retirement should
    # mirror at op_close. Bypass via --skip-retirement-invariants for emergency closures
    # (e.g., stuck retirement; explicit principal authorization required).
    agent_class = fm.get("agent_class", "")
    abandoned = _abandoned_close_problem(fm, args)
    if getattr(args, "abandoned", False) and abandoned:
        print(f"ERROR: --abandoned refused — {abandoned}", file=sys.stderr)
        sys.exit(1)
    if (args.target_status == "retired"
            and agent_class == "executive"
            and not args.skip_retirement_invariants
            and not getattr(args, "abandoned", False)):
        invariant_failures = _check_retirement_invariants(fm, args)
        if invariant_failures:
            print("ERROR: retirement invariants failed for executive-class close. "
                  "Per v1.48.0 Carryalong 3 (Cosmo C4 brief [360a5a55]) — symmetric "
                  "structural enforcement mirrors activation-side ADR-016/028 discipline.",
                  file=sys.stderr)
            for f in invariant_failures:
                print(f"  {f}", file=sys.stderr)
            print("\nBypass available via --skip-retirement-invariants (emergency only; "
                  "requires explicit principal authorization + honest-record in "
                  "closure_reason).", file=sys.stderr)
            sys.exit(1)
    # Dry-run early exit — invariants passed (above); no mutation
    if args.dry_run:
        print(f"DRY RUN OK: {args.activation_uid} would close to status:{args.target_status} "
              f"(invariants passed; no mutation performed)")
        return 0

    # Lock + update
    lock = acquire_lock(fm.get("agent", "unknown"))
    if lock is None:
        print("ERROR: lock acquisition timeout", file=sys.stderr)
        sys.exit(2)
    try:
        with authority_state_lock(VAULT_ROOT, exclusive=True):
            with activation_state_lock(
                VAULT_ROOT,
                args.activation_uid,
                exclusive=True,
            ):
                return _apply_activation_close_transaction(
                    args,
                    path,
                    fm,
                    raw_fm,
                    body,
                )
    finally:
        release_lock(lock)


def probe_signing_broker(activation_uid: str, fm: dict | None = None) -> tuple[bool, str]:
    """Whether this activation can still be signed, and why not if it cannot.

    eda86636 item 3. The broker is a process-held ssh-agent in a session-scoped
    directory, so it dies with the OS session while the activation it signs for
    outlives it. Today that is discovered at the FINAL write of a retirement:
    G98 completed a transfer, a memory fold, a reflection and a captain's log
    before learning it could not close. This makes the same fact cheap to learn
    at step 0, while the agent still holds full context.

    Never raises. A probe that can fail is a probe nobody runs at step 0.
    """
    if fm is not None and not fm.get("agent_public_key"):
        # A record whose key was VOIDED is not the same as one that never had a
        # key, and must not be reported as the benign pre-G2 path. The old
        # remedy renamed agent_public_key aside, so the field is absent while
        # the lineage still counts as keyed — the exact ambiguity that bricked
        # a birth. Say which one this is.
        voided = [
            key for key in fm
            if str(key).startswith("agent_public_key_")
            or str(key).startswith("agent_key_void")
        ]
        if voided:
            return (
                False,
                "activation key was VOIDED by the pre-eda86636 remedy "
                f"(fields: {', '.join(sorted(voided))}) — not signable, and not "
                "an unkeyed pre-G2 activation either. No new voids are created "
                "under eda86636; this is a historical artifact.",
            )
        return (True, "unkeyed activation — pre-G2 history path, no broker required")
    try:
        from lib import authority_chain as _ac
    except ImportError as exc:
        return (False, f"authority chain unavailable: {exc}")
    try:
        _ac.activation_signing_broker(activation_uid)
        return (True, "signing broker is live")
    except Exception as exc:
        detail = str(exc).strip() or type(exc).__name__
        return (False, detail)


def _yaml_scalar(value: str) -> str:
    """Render a value as a YAML scalar that survives a round trip.

    Plain scalars silently break on colon-space, leading indicators, and a few
    other shapes. Rather than enumerate them, round-trip the plain form and
    fall back to a double-quoted scalar whenever it does not come back intact.
    """
    text = "" if value is None else str(value)
    try:
        import yaml
    except ImportError:  # pragma: no cover — quote defensively without yaml
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    try:
        roundtrip = yaml.safe_load(f"k: {text}\n")
        if isinstance(roundtrip, dict) and roundtrip.get("k") == text:
            return text
    except yaml.YAMLError:
        pass
    return yaml.safe_dump(
        text, default_style='"', default_flow_style=False, allow_unicode=True
    ).strip()


def _frontmatter_parses(raw_fm: str) -> tuple[bool, str]:
    """Whether a frontmatter block is valid, loadable YAML mapping."""
    try:
        import yaml
    except ImportError:  # pragma: no cover
        return (True, "")
    try:
        loaded = yaml.safe_load(raw_fm)
    except yaml.YAMLError as exc:
        return (False, str(exc).splitlines()[0][:120])
    if not isinstance(loaded, dict):
        return (False, "frontmatter did not parse to a mapping")
    return (True, "")


def op_update(args):
    """Update a non-lifecycle field on an existing activation entry."""
    field_name = str(args.field or "").strip()
    field_token = re.sub(r"[^a-z0-9]", "", field_name.lower())
    protected_tokens = {
        re.sub(r"[^a-z0-9]", "", field.lower())
        for field in LIFECYCLE_FIELDS
    } | LIFECYCLE_FIELD_ALIASES
    if field_name.lower() in LIFECYCLE_FIELDS or field_token in protected_tokens:
        print(f"ERROR: {args.field!r} is lifecycle-load-bearing; not updatable "
              f"via op:update (use op:close for status changes)", file=sys.stderr)
        sys.exit(1)
    if not re.fullmatch(r"[a-zA-Z_][\w.]*", field_name):
        print(f"ERROR: {args.field!r} is not a valid frontmatter field", file=sys.stderr)
        sys.exit(1)
    args.field = field_name
    path = VAULT_FILES / f"{args.activation_uid}.md"
    if not path.exists():
        print(f"ERROR: activation entry {args.activation_uid!r} not found", file=sys.stderr)
        sys.exit(1)
    parsed = parse_frontmatter(path)
    if parsed is None:
        sys.exit(1)
    fm, raw_fm, body = parsed
    lock = acquire_lock(fm.get("agent", "unknown"))
    if lock is None:
        sys.exit(2)
    try:
        # v1.1: the value is YAML-quoted, and the result is re-parsed before it
        # is allowed to land. Previously the value was interpolated raw, so any
        # value containing a colon-space produced unparseable frontmatter and
        # the tool still printed the uid and exited 0. On an ACTIVATION entry
        # that is not cosmetic: an unparseable entry declaring agent_public_key
        # is durable activation-history poison, and it blocks predecessor
        # derivation for that agent's whole lineage — the successor cannot be
        # born. vela-v71 did exactly this to herself on 2026-07-31 and it went
        # unnoticed for ~15 hours, because nothing on the write path looked at
        # what it had written.
        rendered = _yaml_scalar(args.value)
        new_fm_lines = []
        field_set = False
        for line in raw_fm.splitlines():
            if line.startswith(f"{args.field}:"):
                new_fm_lines.append(f"{args.field}: {rendered}")
                field_set = True
            elif line.startswith("modified:"):
                new_fm_lines.append(f"modified: {TODAY}")
            else:
                new_fm_lines.append(line)
        if not field_set:
            new_fm_lines.append(f"{args.field}: {rendered}")
        new_fm = "\n".join(new_fm_lines)

        # Fail closed: never leave an activation entry the loaders cannot read.
        ok, why = _frontmatter_parses(new_fm)
        if not ok:
            print(
                f"ERROR: refusing to write {args.activation_uid} — the result "
                f"would be unparseable frontmatter ({why}). Nothing was "
                f"written. An unparseable activation entry poisons predecessor "
                f"derivation for this agent's entire lineage.",
                file=sys.stderr,
            )
            return 1

        new_content = "---\n" + new_fm + "\n---" + body
        path.write_text(new_content)

        # Verify what actually landed on disk, not what we intended to write.
        if parse_frontmatter(path) is None:
            path.write_text("---\n" + raw_fm + "\n---" + body)
            print(
                f"ERROR: post-write verification failed for "
                f"{args.activation_uid}; the prior content has been restored.",
                file=sys.stderr,
            )
            return 1

        print(args.activation_uid)
        return 0
    finally:
        release_lock(lock)


# ---------------------- main -------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="op", required=True)

    p_open = sub.add_parser("open", help="Write new activation entry at boot")
    p_open.add_argument("--agent", required=True)
    p_open.add_argument("--generation", required=True)
    p_open.add_argument("--model", required=True)
    p_open.add_argument("--platform", required=True)
    p_open.add_argument("--agent-root", required=True)
    p_open.add_argument("--agent-class", required=True)
    p_open.add_argument("--activated-by", required=True)
    p_open.add_argument("--member-of", default="")
    p_open.add_argument("--commissioned-purpose", default="")
    p_open.add_argument("--run-folder", default="")
    p_open.add_argument("--stale-threshold-hours", type=int, default=None,
                        help="Per-activation override; default by agent_class")
    p_open.add_argument(
        "--strict", action="store_true",
        help="Refuse the birth on the first failed identity check instead of "
             "marking it provisional. For validators, CI and boot-health "
             "probes — NOT for booting an agent. A birth must never be refused "
             "by ceremony that protects nothing (Mike, 2026-08-02).",
    )
    p_open.set_defaults(func=op_open)

    p_close = sub.add_parser("close", help="Close activation entry (terminal status)")
    p_close.add_argument("--activation-uid", required=True)
    p_close.add_argument("--target-status", required=True)
    p_close.add_argument("--closure-reason", default="")
    p_close.add_argument("--transfer-uid", default="")
    # v1.48.0 Carryalong 3 — symmetric retirement-invariant enforcement (Cosmo brief 360a5a55)
    p_close.add_argument("--retirement-run-folder", default="",
                          help="Path to retirement run folder (executive-class retirement; "
                               "default: playbook-runs/agent-retire-<agent>-<gen>-<date>/)")
    p_close.add_argument("--retiring-flip-recorded-at", default="",
                          help="Timestamp when status card flipped to RETIRING (audit trail; "
                               "optional — R-2 satisfied transitively via R-1 milestone)")
    p_close.add_argument("--reflection-path", default="",
                          help="Path to reflection file (executive-class retirement; "
                               "default: agents/<agent>/reflections/<gen-slug>-reflection.md)")
    # eda86636 items 3 + 4 — a retirement must always be closeable.
    p_close.add_argument("--broker-lost", action="store_true",
                          help="The signing broker did not survive the session, so this close "
                               "cannot be signed. Records close_evidence: attested with the "
                               "authorizing principal, the reason, and the key it WOULD have "
                               "signed with. The key is NOT voided or renamed. Requires "
                               "--authorized-by; fails closed without it.")
    p_close.add_argument("--authorized-by", default="",
                          help="Principal authorizing an attested (unsigned) close. Required "
                               "with --broker-lost.")
    p_close.add_argument("--check-broker", action="store_true",
                          help="Probe the signing broker and report whether this activation is "
                               "still signable, then exit without closing. Run this at "
                               "retirement STEP 0, not after doing the whole retirement.")
    p_close.add_argument("--abandoned", action="store_true",
                          help="Close an activation whose session DIED without ceremony. "
                               "Skips the retirement invariants, which can only be satisfied "
                               "by the agent itself — the deadlock that left Po open from "
                               "2026-07-03. NOT a shortcut: refused unless the activation is "
                               "past its OWN declared stale_threshold_hours, and requires "
                               "--authorized-by. Records close_evidence: abandoned so the "
                               "absent ceremony is stated, never hidden.")
    p_close.add_argument("--skip-retirement-invariants", action="store_true",
                          help="EMERGENCY BYPASS — skip R-1/R-2/R-3 invariant checks. "
                               "Requires explicit principal authorization + honest-record in "
                               "closure_reason. Default: invariants enforced for executive retirement.")
    p_close.add_argument("--dry-run", action="store_true",
                          help="Validate invariants + print result WITHOUT mutating the activation entry. "
                               "Use for invariant testing or pre-flight checks. v1.48.0 Argus A77 "
                               "fix-on-see addition after self-induced substrate defect during "
                               "Carryalong 3 testing (script mutated state on what was meant as a "
                               "positive-path test).")
    p_close.set_defaults(func=op_close)

    p_update = sub.add_parser("update", help="Update non-lifecycle field")
    p_update.add_argument("--activation-uid", required=True)
    p_update.add_argument("--field", required=True)
    p_update.add_argument("--value", required=True)
    p_update.set_defaults(func=op_update)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
