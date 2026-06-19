#!/usr/bin/env python3
"""
---
uid: 40b2f455
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
  - c7e4f9a2
schema_version: 2
belt: true
title: "write-activation-entry — Open/close activation registry entries"
trigger_description: "Open/close agent activation entries (boot and retirement)."
belt_invocation: "python3 vault/tools/40b2f455.py {open|close|update}"
belt_example: "python3 vault/tools/40b2f455.py open --agent talos --generation T18 ..."
---
"""

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
import os
import re
import secrets
import sys
import time
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
VAULT_FILES = VAULT_ROOT / "vault" / "files"
LOCK_DIR = VAULT_ROOT / ".tropo-studio" / "locks"
TODAY = time.strftime("%Y-%m-%d")
SCRIPT_NAME = "write-activation-entry.py"

VALID_STATUSES = {"active", "retired", "failed", "stale", "paused"}
TERMINAL_STATUSES = {"retired", "failed", "stale"}
VALID_CLASSES = {"executive", "director", "sa", "cosmo", "tropo",
                 "worker", "child-agent", "pipeline"}
# Per-class stale_threshold_hours defaults (capsule v1.0.1 §2 amendment)
STALE_THRESHOLD_DEFAULTS = {
    "sa": 2, "worker": 6, "executive": 168, "director": 168,
    "cosmo": 168, "tropo": 168, "child-agent": 4,
}
VALID_CLOSURE_REASONS = {
    "clean-retirement", "context-overflow", "parallel-boot-violation",
    "stale-sweep", "dispatch-failure", "harness-watchdog-stall",
    "[SHUTDOWN]", "paused-by-user",
}
LIFECYCLE_FIELDS = {"status", "agent", "activated_at", "activated_by",
                    "type", "name", "agent_root", "agent_class", "generation"}


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
    "_mint_uid_canonical_40b2", Path(__file__).resolve().parent / "5187be30.py"
)
_mint_mod_40b2 = _ilu_40b2.module_from_spec(_mint_spec_40b2)
_mint_spec_40b2.loader.exec_module(_mint_mod_40b2)


def load_existing_uids():
    return _mint_mod_40b2.load_existing_uids()


def mint_uid(existing):
    existing_with_session = _mint_mod_40b2.load_existing_uids() | existing
    for _ in range(64):
        candidate = secrets.token_hex(4)
        if candidate not in existing_with_session:
            existing.add(candidate)
            return candidate
    raise RuntimeError("UID collision storm")


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
    if agent_class in {"executive", "director", "cosmo", "tropo"}:
        m = re.match(r"^([A-Za-z]+)(\d+)$", gen_str)
        if m:
            return int(m.group(2))
    elif agent_class in {"sa", "worker"}:
        m = re.match(r"^.+-(\d+)$", gen_str)
        if m:
            return int(m.group(1))
    elif agent_class == "child-agent":
        m = re.search(r"\.(\d+)\.", gen_str)
        if m:
            return int(m.group(1))
    return None


def successor_generation(gen_str, agent_class):
    """Compute successor generation string from current generation. v1.52 A12b helper.

    Used by op_close to author the transfer-stub frontmatter at retirement-time.
    Executive class: 'A57' -> 'A58'; sa class: 'sa.skeptic-024' -> 'sa.skeptic-025'.
    Returns None if generation pattern cannot be parsed.
    """
    if agent_class in {"executive", "director", "cosmo", "tropo"}:
        m = re.match(r"^([A-Za-z]+)(\d+)$", gen_str)
        if m:
            prefix = m.group(1)
            num = int(m.group(2)) + 1
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

def op_open(args):
    """Write a new activation entry. Validates ADR-016 + ADR-028 substrate."""
    # Validate args
    if args.agent_class not in VALID_CLASSES:
        print(f"ERROR: agent_class {args.agent_class!r} not in {sorted(VALID_CLASSES)}",
              file=sys.stderr)
        sys.exit(1)
    # Acquire lock
    lock = acquire_lock(args.agent)
    if lock is None:
        print(f"ERROR: lock acquisition timeout for agent {args.agent!r}", file=sys.stderr)
        sys.exit(2)
    try:
        # ADR-016 substrate check
        entries = scan_activations()
        active_for_agent = [(uid, fm) for uid, fm in entries
                            if fm.get("agent") == args.agent
                            and fm.get("status") == "active"]
        if active_for_agent:
            print(f"ERROR: ADR-016 violation — agent {args.agent!r} already has "
                  f"{len(active_for_agent)} active activation entry/entries: "
                  f"{[u for u, _ in active_for_agent]}", file=sys.stderr)
            sys.exit(1)
        # ADR-028 substrate check
        same_agent = [(uid, fm) for uid, fm in entries
                      if fm.get("agent") == args.agent]
        if same_agent:
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
                print(f"ERROR: ADR-028 violation — generation chain mismatch for "
                      f"{args.agent!r}. Predecessor {pred_fm.get('generation')!r} "
                      f"({pred_uid}); your generation {args.generation!r} should be "
                      f"predecessor + 1.", file=sys.stderr)
                sys.exit(1)
        # Mint UID + write entry
        existing_uids = load_existing_uids()
        uid = mint_uid(existing_uids)
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
            f"activated_at: {TODAY}",
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
        (VAULT_FILES / f"{uid}.md").write_text("\n".join(lines))
        print(uid)  # stdout returns the UID
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
                _sys.path.insert(0, str(_sys.path))
            from lib.event_emitter import auto_emit
            auto_emit("tropo.substrate.created", "/tools/write-activation-entry", "123e12e7",
                      lifecycle="evergreen", data={"uid": uid, "agent": args.agent})
        except Exception:
            pass
        return 0
    finally:
        release_lock(lock)


def _check_retirement_invariants(fm: dict, args) -> list[str]:
    """v1.48.0 Carryalong 3 — symmetric structural enforcement for executive-class retirement.

    Per Cosmo C4 brief [360a5a55] 2026-05-16 — activation-side enforces ADR-016/028 server-side
    at op_open; retirement-side relied on agent self-discipline. This function mirrors the
    activation-side discipline for executive-class retirement-target closures via three
    invariants (R-1 retirement run folder + Group 0 milestone; R-2 status card transited
    through RETIRING; R-3 reflection authored).

    Returns list of failure messages (empty list = all invariants pass; non-empty = HALT).

    Invariants only fire when target_status == 'retired' AND agent_class == 'executive'.
    sa.*, director, worker, child-agent, pipeline classes are exempt by design (their
    retirement substrate is shaped differently; this discipline is executive-scoped).
    """
    failures: list[str] = []
    agent_slug = fm.get("agent", "unknown")
    generation = fm.get("generation", "unknown")
    gen_slug = generation.lower() if generation else "unknown"

    # Invariant R-1: retirement run folder exists with Group 0 milestone
    run_folder = args.retirement_run_folder
    if not run_folder:
        # Best-effort default path resolution
        run_folder = f"playbook-runs/agent-retire-{agent_slug}-{gen_slug}-{TODAY}/"
    rf_path = VAULT_ROOT / run_folder
    rf_jsonl = rf_path / "run.jsonl"
    if not rf_path.is_dir():
        failures.append(
            f"R-1 HALT: retirement run folder {run_folder!r} does not exist. "
            f"Per agent-retire.playbook v2.8 §Group 0 — retirement run folder is required "
            f"BEFORE close-mode call. Remediation: create {run_folder!r} + fire Group 0 "
            f"§Step 0.1 (status card → RETIRING) + §Step 0.2 (Signal Secured milestone). "
            f"Then retry close. Pass --retirement-run-folder <path> to override default."
        )
    elif not rf_jsonl.is_file():
        failures.append(
            f"R-1 HALT: retirement run folder {run_folder!r} exists but run.jsonl missing. "
            f"Remediation: write Group 0 milestone event to {rf_jsonl!r} per playbook §Step 0.2."
        )
    else:
        try:
            jsonl_text = rf_jsonl.read_text()
            if not re.search(
                r'"milestone_fired"[^\n]*"Signal Secured"[^\n]*"Group 0"', jsonl_text
            ):
                failures.append(
                    f"R-1 HALT: retirement run.jsonl at {rf_jsonl!r} does not contain "
                    f"Group 0 Signal Secured milestone. Per agent-retire.playbook §Step 0.2 — "
                    f"the milestone event is the structural signal that the HARD GATE "
                    f"(status card RETIRING flip) fired. Remediation: append the milestone "
                    f"event to run.jsonl + retry close."
                )
        except (OSError, UnicodeDecodeError) as e:
            failures.append(f"R-1 HALT: cannot read {rf_jsonl!r}: {e}")

    # Invariant R-2: status card transited through RETIRING
    # Two acceptance paths: (a) explicit --retiring-flip-recorded-at timestamp; (b) the
    # Signal Secured milestone implies the RETIRING flip per playbook ordering. Since
    # R-1 already verified the milestone, R-2 is satisfied transitively unless caller
    # wants to assert explicit timestamp for audit purposes.
    if args.retiring_flip_recorded_at:
        # Verify the timestamp is sane: between activation_at and now
        activated_at = fm.get("activated_at", "")
        if activated_at and args.retiring_flip_recorded_at < activated_at:
            failures.append(
                f"R-2 HALT: --retiring-flip-recorded-at {args.retiring_flip_recorded_at!r} "
                f"is before activation_at {activated_at!r}. Timestamp must fall between "
                f"activation and now."
            )
    # Else R-2 satisfied transitively via R-1's milestone check.

    # Invariant R-3: reflection authored at canonical path with File Manifest section
    reflection_path = args.reflection_path
    if not reflection_path:
        # Best-effort default path resolution
        reflection_path = f"agents/{agent_slug}/reflections/{gen_slug}-reflection.md"
    rp_path = VAULT_ROOT / reflection_path
    if not rp_path.is_file():
        failures.append(
            f"R-3 HALT: reflection file {reflection_path!r} does not exist. Per "
            f"agent-retire.playbook v2.8 §Group 2 — executive-class reflection is the "
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
                    f"R-3 HALT: reflection at {reflection_path!r} exists but is missing "
                    f"`## File Manifest` section. Per agent-retire.playbook §Step 2.2 — "
                    f"the File Manifest section is required for executive-class reflections "
                    f"(non-git audit trail; provenance record). Remediation: add the section "
                    f"listing this session's created / modified / deleted files."
                )
        except (OSError, UnicodeDecodeError) as e:
            failures.append(f"R-3 HALT: cannot read {reflection_path!r}: {e}")

    return failures


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
    if (args.target_status == "retired"
            and agent_class == "executive"
            and not args.skip_retirement_invariants):
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
                    new_fm_lines.append(f"closure_reason: {yaml_quote(args.closure_reason)}")
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
            new_fm_lines.append(f"closure_reason: {yaml_quote(args.closure_reason)}")
        if args.transfer_uid and not transfer_uid_set:
            new_fm_lines.append(f"transfer_uid: {args.transfer_uid}")
        new_content = "---\n" + "\n".join(new_fm_lines) + "\n---" + body
        path.write_text(new_content)

        # v1.52 A12b structural fix — auto-create transfer-stub if --transfer-uid set + stub absent.
        # Composes with v1.48 Carryalong 3 retirement-invariants pattern. Closes the recurring
        # defect class (Metis G55→G56 + G56→G57 + G57→G58 all required Vela captain-mode
        # surgical stub authoring at ship time because no auto-creation existed at retirement time).
        if args.transfer_uid:
            closing_actor = (args.actor if hasattr(args, 'actor') and args.actor
                            else fm.get("agent", "unknown") + "-" + fm.get("generation", "unknown").lower())
            stub_created = auto_create_transfer_stub(fm, args.transfer_uid, closing_actor)
            if stub_created:
                print(f"AUTO-STUB-CREATED: vault/files/{args.transfer_uid}.md", file=sys.stderr)

        print(args.activation_uid)
        # V4 — v1.59 Lane D: auto-fire render-crew-brief on activation open
        try:
            _crew_script = Path(__file__).resolve().parents[2] / "vault" / "tools" / "6510afc7.py"
            if _crew_script.exists():
                import subprocess as _sp2
                _sp2.run([sys.executable, str(_crew_script)], capture_output=True, timeout=15)
        except Exception:
            pass
        # C.2 — Stream C auto-emission: tropo.substrate.modified on close (v1.58)
        try:
            import importlib.util as _ilu, sys as _sys
            _vr = Path(__file__).resolve().parents[2]
            _sp = _vr / ".tropo" / "scripts"
            if str(_sp) not in _sys.path:
                _sys.path.insert(0, str(_sp))
            from lib.event_emitter import auto_emit
            auto_emit("tropo.substrate.modified", "/tools/write-activation-entry", "123e12e7",
                      lifecycle="evergreen",
                      data={"uid": args.activation_uid, "status": args.target_status})
        except Exception:
            pass
        return 0
    finally:
        release_lock(lock)


def op_update(args):
    """Update a non-lifecycle field on an existing activation entry."""
    if args.field in LIFECYCLE_FIELDS:
        print(f"ERROR: {args.field!r} is lifecycle-load-bearing; not updatable "
              f"via op:update (use op:close for status changes)", file=sys.stderr)
        sys.exit(1)
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
        new_fm_lines = []
        field_set = False
        for line in raw_fm.splitlines():
            if line.startswith(f"{args.field}:"):
                new_fm_lines.append(f"{args.field}: {args.value}")
                field_set = True
            elif line.startswith("modified:"):
                new_fm_lines.append(f"modified: {TODAY}")
            else:
                new_fm_lines.append(line)
        if not field_set:
            new_fm_lines.append(f"{args.field}: {args.value}")
        new_content = "---\n" + "\n".join(new_fm_lines) + "\n---" + body
        path.write_text(new_content)
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
