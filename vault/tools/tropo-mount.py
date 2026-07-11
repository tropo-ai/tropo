#!/usr/bin/env python3
"""
---
uid: 8a4c1f6e
name: mount
type: tool
title: "tropo-mount — vault mount-gate + compose-lockfile (ADR-051 Fork 2)"
status: active
owner: talos
domain: "tropo-mount.py — the mount-gate CLI: validates a candidate vault's per-vault-root manifest + contract, pins the mount to a resolved commit in .tropo-studio/compose.lock, records executable-consent as a governed write, enforces <vault>:skill name-qualification, and enforces one-clone-per-vault-UID. Implements dev-spec 409ef1cc (ADR-051 Fork 2, Argus A127 lane)."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-mount.py"
script_path: vault/tools/tropo-mount.py
spawnable_by:
  - all-executives
input:
  type: object
  description: "See --help for full argument details"
created: '2026-07-08'
created_by: talos-t26
modified: '2026-07-08'
modified_by: talos-t26
governed_by: 8dd772a0
member_of:
  - cd1fcd25
schema_version: 2
extraction_scope: argo-reference
belt: false  # trimmed from belt by vela-v65 2026-07-10 — over the 15-entry cap; mount/publish are federation-specific, lock-dev-spec is ceremony-specific. Cataloged + functional; not in quick-ref.
belt_invocation: "python3 vault/tools/tropo-mount.py --mount-path <path> [--consent] [--force-remount]"
belt_example: "python3 vault/tools/tropo-mount.py --mount-path ../other-studio --consent"
---
"""

"""tropo-mount.py — the vault mount-gate (ADR-051 Fork 2, dev-spec 409ef1cc).

Authored 2026-07-08 by Talos T26 per Argus A127's dev-spec 409ef1cc, itself
implementing ADR-051 (18059aef, Mike-accepted 2026-07-06) Fork 2. Ratified
rulings this build does NOT re-litigate (409ef1cc "RULED conventions"):

  - Per-vault-root manifest path: <vault-root>/.tropo/vault-manifest.md
    (kernel-tier sibling to .tropo/studio-identity.md, mirrors 32067bea).
  - Compose-lockfile: .tropo-studio/compose.lock (studio-level, JSON).
  - Consent granularity: per-vault at first mount; the lockfile captures the
    exact capability_set consented to; a contract widening that adds
    executables re-triggers consent for the delta.
  - The held line (non-negotiable): executable-consent + <vault>:skill
    name-qualification MUST exist at the first mount (bc25583d §6).

WHAT THE GATE DOES, in order, on every `--mount-path` invocation:
  1. Reads <mount-path>/.tropo/vault-manifest.md. Parses frontmatter, runs it
     through validate_vault_manifest_fields() (imported from tropo-validate.py
     — NOT re-implemented; see "Cross-file import" below) plus this script's
     own `contract` block resolution check.
  2. Resolves a pinned commit hash for the mount (git rev-parse HEAD inside
     the mount-path; see "Resolved commit hash" judgment call below). A
     mount-path that is not a git repo, or is dirty/unresolvable, is refused
     — mounts never float at HEAD unpinned.
  3. Enforces one-clone-per-vault-UID: refuses if the manifest's vault_uid
     already has a record in compose.lock, UNLESS --force-remount is given
     (the re-mount / contract-update path, itself gated by §5 below).
  4. Enforces <vault>:skill name-qualification: every capability the
     manifest's contract declares (contract.capabilities, a list of names)
     is checked against this studio's OWN reserved capability namespace
     (every `name:` field in vault/tools/*.py + vault/skills/*.md — the
     live OS/private capability catalog). An UNQUALIFIED name colliding
     with a reserved name is refused. A name already in the vault-qualified
     form `<vault_uid>:<name>` (or `<name_prefix>:<name>`) is accepted
     regardless of collision (namespacing defeats the collision by
     construction — dependency-confusion, Birsan 2021, 5d3ab142 §6).
  5. Enforces executable-consent as a governed write: if the contract
     declares ANY capabilities (contract.capabilities non-empty), a
     consent record MUST be written to compose.lock in the SAME
     invocation — via the --consent flag (a CLI flag, not an interactive
     prompt: this is a governed write, not runtime UX per bc25583d §6). No
     --consent + executables present => refused, nothing written. Consent
     is recorded on disk (compose.lock), so it survives process restart —
     it is never held in-process only.
  6. On a --force-remount of an already-present vault-UID, diffs the NEW
     contract against the RECORDED contract_hash's underlying content
     (compose.lock stores the full contract block, not just its hash, so
     the diff is real, not a black box). A NARROWING (fewer
     registered_types, or any capsule_versions entry going down) requires
     BOTH a manifest `version` bump (vs the recorded manifest_version) AND
     --consent on this invocation (re-consent for the delta, a1f7c750
     Guarded Transitions table). Missing either => refused, compose.lock
     UNCHANGED.
  7. On success, writes/updates exactly one JSON record for this vault_uid
     in .tropo-studio/compose.lock (see .tropo/schema/compose-lockfile-schema.md
     for the record shape) and prints a one-line summary.

Refusal messages always name what was refused and why (mirrors
find_open_activation()/check_dev_spec_activation_coupling()'s terse,
specific style) — never a bare non-zero exit.

Cross-file import: validate_vault_manifest_fields() is imported from
tropo-validate.py via importlib.util.spec_from_file_location, the SAME
cross-file-import pattern already used throughout vault/tools/ (e.g.
e337f1dd.py importing tropo-mint-id.py, tropo-backfill-styles.py importing
import-walker.py). Chosen over duplicating the ~90-line validator function
here: a single source of truth for manifest-schema enforcement means a
future capsule amendment to a1f7c750 only has to change tropo-validate.py.

Usage:
    python3 vault/tools/tropo-mount.py \\
        --mount-path <path-to-candidate-vault-root> \\
        [--consent]           # required if the mounted contract declares capabilities
        [--force-remount]     # required to re-mount an already-present vault-UID
        [--compose-lock <path>]  # default: .tropo-studio/compose.lock at this studio's root
        [--mounted-by <principal>]  # advisory provenance; default $USER or "unknown"

Exit codes:
    0   Success — mount admitted, compose.lock written/updated
    1   Refused — manifest invalid, unqualified shadowing name, no consent for
        executables, unpinned/unresolvable commit, duplicate vault-UID without
        --force-remount, or narrowed contract without version-bump + re-consent.
        compose.lock is UNCHANGED in every refusal case.
    2   Argument / environment error (bad --mount-path, compose.lock corrupt)
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Optional

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
STUDIO_ROOT = SCRIPT_DIR.resolve().parents[1]
DEFAULT_COMPOSE_LOCK = STUDIO_ROOT / ".tropo-studio" / "compose.lock"
VAULT_MANIFEST_REL = Path(".tropo") / "vault-manifest.md"
TODAY = time.strftime("%Y-%m-%d")
NOW = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

FRONTMATTER_RE = re.compile(r'^---\n(.*?\n)---\n', re.DOTALL)


# ---------------------------------------------------------------------------
# Cross-file import: validate_vault_manifest_fields() from tropo-validate.py
# (943bb220 / ADR-051 Fork 1). Same importlib.util pattern used studio-wide
# (see e337f1dd.py's import of tropo-mint-id.py). Guarded so this module is
# still importable (e.g. by the test file) even if tropo-validate.py's own
# module-level side effects change in the future.
# ---------------------------------------------------------------------------
_tv_spec = importlib.util.spec_from_file_location(
    "_tropo_validate_for_mount_8a4c1f6e", str(SCRIPT_DIR / "tropo-validate.py")
)
_tropo_validate = importlib.util.module_from_spec(_tv_spec)
_tv_spec.loader.exec_module(_tropo_validate)
validate_vault_manifest_fields = _tropo_validate.validate_vault_manifest_fields

# ---------------------------------------------------------------------------
# Pull-side publish-boundary enforcement (44badb55 §4 — "B does NOT trust A").
# SHARED with tropo-validate.py's check_publish_boundary (the post-hoc
# validator re-check) — same functions, so mount-time enforcement and
# audit-time re-check cannot silently disagree on what "clean" means.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(SCRIPT_DIR))
from lib.segment import (
    TEAM_BRANCH_DEFAULT,
    check_no_shallow_clone,
    check_no_submodules,
    check_single_worktree,
    verify_clean_ancestry,
    find_boundary_violations_in_committed_tree,
)


# ---------------------------------------------------------------------------
# Frontmatter helpers (mirrors tropo-lock-dev-spec.py / e337f1dd.py's own
# minimal local copies — this repo's established convention is each
# vault/tools/ script carries its own small split_frontmatter rather than
# importing one, to stay a single-file-truth CLI; see tool.capsule v1.6 §2.5).
# ---------------------------------------------------------------------------

def split_frontmatter(text: str) -> Optional[str]:
    m = FRONTMATTER_RE.match(text)
    return m.group(1) if m else None


def read_manifest(mount_path: Path) -> tuple[Optional[dict], Optional[str]]:
    """Read + parse <mount_path>/.tropo/vault-manifest.md.

    Returns (frontmatter_dict, error). error is None on success.
    """
    manifest_path = mount_path / VAULT_MANIFEST_REL
    if not manifest_path.is_file():
        return None, f"no manifest at {manifest_path} (expected <vault-root>/.tropo/vault-manifest.md)"
    try:
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return None, f"could not read {manifest_path}: {e}"
    fm_text = split_frontmatter(text)
    if fm_text is None:
        return None, f"{manifest_path} has no parseable YAML frontmatter block"
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        return None, f"{manifest_path} frontmatter is not valid YAML: {e}"
    if not isinstance(fm, dict):
        return None, f"{manifest_path} frontmatter did not parse to a mapping"
    return fm, None


# ---------------------------------------------------------------------------
# Resolved-commit-hash resolution.
#
# JUDGMENT CALL (disclosed, not hidden): the dev-spec's own grounding notes
# there is no real git-cloneable second vault in this studio to test mounting
# against. The mechanism this gate implements is real and general — it shells
# `git -C <mount-path> rev-parse HEAD` against whatever git repo lives at
# --mount-path. Against a REAL federated vault, --mount-path would be that
# vault's local clone (already fetched by whatever transport does the
# clone — out of scope for this gate, which starts AFTER a clone exists on
# disk, per 5d3ab142 §6 "Mounting = member_of edge + clone, PINNED by a
# compose-lockfile"). Against this build's own plants, --mount-path is a
# fixture tempdir that the test itself `git init`s and commits — a real git
# repo, just not a real federated one. A mount-path that is NOT a git repo,
# or whose git state cannot be resolved to a commit, is refused (AC-4:
# mounts never float unpinned).
# ---------------------------------------------------------------------------

def resolve_commit_hash(mount_path: Path) -> tuple[Optional[str], Optional[str]]:
    """Return (commit_hash, error). error is None on success.

    Refuses a DIRTY working tree (uncommitted changes, staged or unstaged,
    including untracked files that would affect a fresh checkout of the
    manifest path) in addition to a non-git mount-path. This closes a
    confirmed bypass: read_manifest() reads the WORKING TREE copy of
    .tropo/vault-manifest.md, but the pin recorded in compose.lock is the
    committed HEAD. If those two are allowed to diverge, the gate can
    evaluate consent/qualification/narrowing against a working-tree
    manifest that says one thing while pinning a commit whose COMMITTED
    manifest says another (e.g. working tree shows capabilities:[] so no
    --consent is required, but HEAD's committed manifest declares an
    executable capability that was never consented to and never appears in
    the compose.lock record it was mounted under). Refusing any dirty tree
    at the gate — not merely at the manifest path — is the conservative,
    unbypassable fix: "pin to a resolved commit" (AC-4) means the working
    tree and HEAD must already agree, full stop.
    """
    if not (mount_path / ".git").exists():
        return None, (
            f"{mount_path} is not a git repository (no .git) — a mount must pin to a "
            f"resolved commit hash; an unpinned/non-git mount-path is refused (AC-4)"
        )
    try:
        result = subprocess.run(
            ["git", "-C", str(mount_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"could not resolve HEAD at {mount_path}: {e}"
    if result.returncode != 0:
        return None, f"git rev-parse HEAD failed at {mount_path}: {result.stderr.strip()}"
    commit = result.stdout.strip()
    if not commit:
        return None, f"git rev-parse HEAD at {mount_path} returned an empty hash (no commits yet?)"

    try:
        dirty_result = subprocess.run(
            ["git", "-C", str(mount_path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"could not check working-tree cleanliness at {mount_path}: {e}"
    if dirty_result.returncode != 0:
        return None, f"git status --porcelain failed at {mount_path}: {dirty_result.stderr.strip()}"
    if dirty_result.stdout.strip():
        dirty_lines = dirty_result.stdout.strip().splitlines()
        return None, (
            f"{mount_path} has a DIRTY working tree ({len(dirty_lines)} uncommitted "
            f"change(s), e.g. {dirty_lines[0].strip()!r}) — a mount must pin to a "
            f"resolved commit whose working tree matches HEAD exactly; gating on "
            f"uncommitted content would let the manifest evaluated at mount time "
            f"diverge from the manifest actually pinned by resolved_commit (AC-4 / "
            f"AC-3 integrity). Commit or discard local changes and retry."
        )
    return commit, None


# ---------------------------------------------------------------------------
# Contract-hash / contract-diff.
#
# The compose.lock record stores the FULL contract block (not just its
# hash) precisely so re-mount narrowing-diffs are real, not black-box —
# `contract_hash` is a convenience fingerprint (sha256 of the canonical
# JSON dump) for quick equality checks; the authoritative diff walks the
# stored `contract` object itself.
# ---------------------------------------------------------------------------

def contract_hash(contract: dict) -> str:
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def contract_is_narrowed(old_contract: dict, new_contract: dict) -> list[str]:
    """Returns a list of human-readable narrowing reasons (empty = not narrowed).

    Per a1f7c750 Guarded Transitions: "contract NARROWING (drop a type /
    downgrade a capsule version) -> BREAKING: MUST bump version AND flag
    mount re-consent."
    """
    reasons: list[str] = []
    old_types = set(old_contract.get("registered_types") or [])
    new_types = set(new_contract.get("registered_types") or [])
    dropped = old_types - new_types
    if dropped:
        reasons.append(f"registered_types dropped: {sorted(dropped)}")

    old_versions = old_contract.get("capsule_versions") or {}
    new_versions = new_contract.get("capsule_versions") or {}

    def _semver_tuple(v: Any) -> tuple:
        try:
            return tuple(int(p) for p in str(v).split("."))
        except (ValueError, AttributeError):
            return (0,)

    for capsule, old_v in old_versions.items():
        new_v = new_versions.get(capsule)
        if new_v is None:
            reasons.append(f"capsule_versions[{capsule!r}] removed (was {old_v!r})")
        elif _semver_tuple(new_v) < _semver_tuple(old_v):
            reasons.append(f"capsule_versions[{capsule!r}] downgraded {old_v!r} -> {new_v!r}")

    old_caps = set(old_contract.get("capabilities") or [])
    new_caps = set(new_contract.get("capabilities") or [])
    dropped_caps = old_caps - new_caps
    if dropped_caps:
        reasons.append(f"capabilities dropped: {sorted(dropped_caps)}")

    return reasons


def contract_added_capabilities(old_contract: dict, new_contract: dict) -> list[str]:
    old_caps = set(old_contract.get("capabilities") or [])
    new_caps = set(new_contract.get("capabilities") or [])
    return sorted(new_caps - old_caps)


# ---------------------------------------------------------------------------
# Reserved capability namespace (dependency-confusion defense, AC-2).
#
# Scans THIS studio's own governed capability catalog: every `name:` field
# in vault/tools/*.py (tool.capsule single-file-truth header block) and
# vault/skills/*.md (skill frontmatter). This is the live set of OS/private
# capability names a mounted vault must never silently shadow — namespace-
# over-precedence per 5d3ab142 §6 (npm scopes / Go module paths / Dendron
# vault-qualified links, the uniform prior-art pick).
# ---------------------------------------------------------------------------

_NAME_FIELD_RE = re.compile(r'^name:\s*"?([A-Za-z0-9_.\-]+)"?\s*$', re.MULTILINE)
# Tool scripts (vault/tools/*.py) embed frontmatter inside a docstring AFTER a
# `#!/usr/bin/env python3` shebang + opening `"""`, so it is not anchored at
# text[0] the way vault/files/<uid>.md and vault/skills/<name>.md are — this
# variant of split_frontmatter SEARCHES for the first `---\n...\n---\n` block
# anywhere in the first ~4KB rather than requiring it at position 0.
_EMBEDDED_FRONTMATTER_RE = re.compile(r'---\n(.*?\n)---\n', re.DOTALL)


def find_embedded_frontmatter(text: str) -> Optional[str]:
    # 16KB window: real tool frontmatter blocks in this studio run up to
    # ~4.6KB (e.g. tropo-mint-id.py's argparse-heavy header) — a 4KB cap
    # silently truncated the closing `---\n` and made the whole scan a
    # false-negative. 16KB comfortably covers every header block found
    # while scanning vault/tools/*.py during this build.
    m = _EMBEDDED_FRONTMATTER_RE.search(text[:16384])
    return m.group(1) if m else None


# Unicode category prefixes stripped by _normalize_capability_name: Cf
# (format — zero-width space U+200B, joiners, bidi controls) and Cc
# (control chars). Stripping these BEFORE casefold/NFKC-compare closes the
# invisible-character variant of the dependency-confusion bypass (Argus
# A128 two-sided verify, event 00005962, bounce on 409ef1cc BUILT report
# 00005961) — a zero-width space inside a name would otherwise survive
# NFKC + casefold and still read as a distinct string.
_STRIPPED_UNICODE_CATEGORIES = ("Cf", "Cc")


def _normalize_capability_name(name: str) -> str:
    """ONE canonical normalization pipeline for capability-name comparison —
    reserved_capability_names() and qualification_violations() both call
    THIS function so they cannot drift apart (the exact class of bug this
    closes: two call sites independently deciding "how much" to normalize).

    Pipeline (Argus A128's exact recommended order, event 00005962):
    NFKC-normalize -> strip Unicode format/control chars (Cf/Cc; kills
    interior zero-width spaces/joiners, which .strip() alone does not
    touch since they aren't leading/trailing whitespace) -> strip()
    leading/trailing whitespace -> casefold().

    Closes: case variants (Mint-Id), leading/trailing whitespace
    ('mint-id ' / ' mint-id'), interior zero-width chars, and Unicode
    homoglyphs that NFKC-normalize to a reserved name (fullwidth
    'ｍｉｎｔ－ｉｄ' -> NFKC -> 'mint-id' exactly) — the sharpest case,
    since NFKC is itself a standard security-normalization step, not an
    edge case being special-cased away.
    """
    normalized = unicodedata.normalize("NFKC", name)
    normalized = "".join(
        ch for ch in normalized
        if unicodedata.category(ch) not in _STRIPPED_UNICODE_CATEGORIES
    )
    return normalized.strip().casefold()


def reserved_capability_names(studio_root: Path = STUDIO_ROOT) -> set[str]:
    """Returns the reserved OS/private capability namespace, fully
    NORMALIZED via _normalize_capability_name (NFKC + Cf/Cc-strip + strip +
    casefold).

    Normalizing here (rather than at every call site) means every consumer
    of this set gets the full normalization guarantee for free — the set IS
    the normalized reserved namespace, not a raw one that happens to be
    compared normalized elsewhere.
    """
    names: set[str] = set()
    tools_dir = studio_root / "vault" / "tools"
    if tools_dir.is_dir():
        for f in tools_dir.glob("*.py"):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm_text = find_embedded_frontmatter(text)
            if fm_text is None:
                continue
            m = _NAME_FIELD_RE.search(fm_text)
            if m:
                names.add(_normalize_capability_name(m.group(1)))
    skills_dir = studio_root / "vault" / "skills"
    if skills_dir.is_dir():
        for f in skills_dir.glob("*.md"):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm_text = split_frontmatter(text)
            if fm_text is None:
                continue
            m = _NAME_FIELD_RE.search(fm_text)
            if m:
                names.add(_normalize_capability_name(m.group(1)))
    return names


def qualification_violations(capabilities: list[str], vault_uid: str,
                              name_prefix: Optional[str],
                              reserved: set[str]) -> list[str]:
    """Returns refusal reasons for capability names that shadow a reserved
    name without being vault-qualified. A name is considered qualified if it
    is of the form `<vault_uid>:<name>` or `<name_prefix>:<name>`.

    Collision comparison runs BOTH sides through _normalize_capability_name
    (NFKC + Cf/Cc-strip + strip + casefold) — a bare-case exact match is not
    the actual attack surface here. The textbook dependency-confusion
    technique (Birsan 2021) relies on near-miss variants; case is the
    cheapest one, but whitespace and Unicode homoglyphs are just as real
    (a fullwidth 'ｍｉｎｔ－ｉｄ' NFKC-normalizes to 'mint-id' exactly —
    Argus A128 two-sided verify caught this gap, event 00005962, bounce on
    the case-only version of this check). `reserved` is ALREADY normalized
    (reserved_capability_names built it via the same function); incoming
    capability names are normalized here at comparison time — one function,
    both sides, so they cannot drift apart.
    """
    violations: list[str] = []
    qualified_prefixes = {vault_uid}
    if name_prefix:
        qualified_prefixes.add(name_prefix)
    qualified_prefixes_norm = {_normalize_capability_name(p) for p in qualified_prefixes}
    for cap in capabilities:
        if ":" in cap:
            prefix, _, bare = cap.partition(":")
            if _normalize_capability_name(prefix) in qualified_prefixes_norm:
                continue  # properly qualified — never shadows, by construction
            violations.append(
                f"capability {cap!r} carries an unrecognized qualification prefix "
                f"{prefix!r} (expected {sorted(qualified_prefixes)!r})"
            )
            continue
        # Unqualified name — refuse if it collides (normalized: NFKC +
        # Cf/Cc-strip + strip + casefold) with a reserved OS/private name.
        if _normalize_capability_name(cap) in reserved:
            violations.append(
                f"capability {cap!r} is UNQUALIFIED and shadows a reserved OS/private "
                f"capability name (normalized match — case/whitespace/Unicode-"
                f"homoglyph insensitive) — mount it as "
                f"{vault_uid}:{cap} (or set name_prefix) instead (dependency-confusion "
                f"defense, 5d3ab142 §6 / bc25583d §6)"
            )
    return violations


# ---------------------------------------------------------------------------
# Working-tree / HEAD manifest cross-verification.
#
# Defense in depth alongside the dirty-tree refusal in resolve_commit_hash:
# that check catches the general case (any uncommitted change anywhere in
# the mount-path). This check is narrower and more direct — it re-reads the
# manifest specifically as it exists in the git object at the resolved
# commit (`git show <commit>:<path>`) and byte-compares it against what
# read_manifest() actually evaluated (the working-tree copy). This closes
# the gap a `git status --porcelain`-only check could miss (e.g. the
# manifest path is untracked/gitignored so `git status --porcelain` reports
# nothing, yet the file the gate evaluated is not what `resolved_commit`
# would actually check out). Belt-and-suspenders: either check alone would
# have caught the confirmed repro (dirty tree with a modified TRACKED
# manifest); both together close the broader class.
# ---------------------------------------------------------------------------

def read_manifest_at_commit(mount_path: Path, commit: str) -> tuple[Optional[str], Optional[str]]:
    """Return (raw_text, error) for the manifest as committed at `commit`.

    error is a human-readable string (not an exception) on any failure,
    including "the manifest does not exist at this commit" — a valid,
    refusal-worthy outcome (e.g. the manifest was only ever added to the
    working tree, never committed).
    """
    rel = str(VAULT_MANIFEST_REL)
    try:
        result = subprocess.run(
            ["git", "-C", str(mount_path), "show", f"{commit}:{rel}"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"could not read {rel} at commit {commit[:12]}: {e}"
    if result.returncode != 0:
        return None, (
            f"{rel} does not exist at the resolved commit {commit[:12]} "
            f"(git show failed: {result.stderr.strip()}) — the manifest read at "
            f"mount time would not be reproducible from resolved_commit alone"
        )
    return result.stdout, None


def verify_manifest_matches_head(mount_path: Path, commit: str, working_tree_text: str) -> Optional[str]:
    """Returns an error string if the manifest as committed at `commit`
    differs from the manifest actually read from the working tree, else
    None. This is what makes `resolved_commit` a REAL reproducibility pin
    for what the gate evaluated — not just "some commit exists."
    """
    committed_text, err = read_manifest_at_commit(mount_path, commit)
    if err:
        return err
    if committed_text != working_tree_text:
        return (
            f"the manifest read at mount time (working tree) does not match the "
            f"manifest committed at the resolved commit {commit[:12]} — this would "
            f"pin a resolved_commit whose committed content diverges from what was "
            f"just evaluated for consent/qualification/narrowing (AC-3/AC-4 "
            f"integrity); refusing rather than writing an unreproducible record"
        )
    return None


# ---------------------------------------------------------------------------
# Compose-lockfile I/O
# ---------------------------------------------------------------------------

def load_compose_lock(path: Path) -> dict:
    if not path.is_file():
        return {"schema_version": 1, "vaults": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"[FAIL] compose-lock at {path} is corrupt / unreadable: {e}")
    if not isinstance(data, dict) or "vaults" not in data:
        raise SystemExit(f"[FAIL] compose-lock at {path} does not match the expected schema (missing 'vaults')")
    return data


def write_compose_lock(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)  # atomic on POSIX — no partial-write window


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

class MountRefused(Exception):
    """Raised with a human-readable reason; caller prints '[REFUSED] <reason>' and exits 1."""


# ---------------------------------------------------------------------------
# Pull-side publish-boundary check (44badb55 §4, dev-spec build target).
#
# "B does NOT trust A": mounting a vault that has ever published a team
# branch re-validates that branch's committed tip independently, exactly as
# tropo-validate.py's check_publish_boundary does post-hoc — this is the
# SAME enforcement running at MOUNT TIME instead of waiting for the next
# validator pass, so a boundary violation is caught before this studio ever
# composes the mounted content into its own index.
#
# Runs ONLY when the mount candidate carries a local TEAM_BRANCH_DEFAULT
# ref — a vault that has never published anything (a fresh personal/
# knowledgebase-kind vault, or a team vault before its first publish) has
# nothing to re-validate yet, so this is a no-op for that (today universal)
# case.
# ---------------------------------------------------------------------------

def pull_side_team_branch_check(mount_path: Path, vault_uid: str) -> Optional[str]:
    """Returns a refusal reason string, or None if there is nothing to check
    (no team branch present) or everything checked out clean."""
    shallow_err = check_no_shallow_clone(mount_path)
    if shallow_err:
        return shallow_err

    tip_result = subprocess.run(
        ["git", "-C", str(mount_path), "rev-parse", "--verify", f"refs/heads/{TEAM_BRANCH_DEFAULT}"],
        capture_output=True, text=True, timeout=10,
    )
    if tip_result.returncode != 0:
        return None  # no team branch yet — nothing published, nothing to re-check
    tip = tip_result.stdout.strip()

    submodule_err = check_no_submodules(mount_path)
    if submodule_err:
        return submodule_err
    worktree_err = check_single_worktree(mount_path)
    if worktree_err:
        return worktree_err

    ancestry_holds, ancestry_detail = verify_clean_ancestry(mount_path, tip)
    if not ancestry_holds:
        return f"team branch {TEAM_BRANCH_DEFAULT!r} ancestry check FAILED: {ancestry_detail}"

    tree_violations = find_boundary_violations_in_committed_tree(mount_path, vault_uid, tip)
    if tree_violations:
        return (
            f"team branch {TEAM_BRANCH_DEFAULT!r} at tip {tip[:12]} FAILS the publish boundary "
            f"re-check ({len(tree_violations)} violation(s)): " + "; ".join(tree_violations)
        )
    return None


def run_mount(mount_path: Path, consent: bool, force_remount: bool,
              compose_lock_path: Path, mounted_by: str) -> dict:
    """Runs the full gate. Returns the written record on success. Raises
    MountRefused (never a bare exception) on any refusal."""

    manifest, err = read_manifest(mount_path)
    if err:
        raise MountRefused(f"manifest invalid — {err}")

    manifest_path = mount_path / VAULT_MANIFEST_REL
    try:
        manifest_raw_text = manifest_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise MountRefused(f"manifest invalid — could not re-read {manifest_path}: {e}")

    manifest_errors = validate_vault_manifest_fields(manifest)
    if manifest_errors:
        raise MountRefused(
            "manifest failed schema validation (a1f7c750): " + "; ".join(manifest_errors)
        )

    vault_uid = manifest.get("uid") or manifest.get("vault_uid")
    if not vault_uid or not re.match(r'^[0-9a-f]{8}$', str(vault_uid)):
        raise MountRefused(
            f"manifest has no resolvable 8-hex vault UID (uid: {vault_uid!r}) — cannot "
            f"key a compose.lock record without one"
        )
    vault_uid = str(vault_uid)

    contract = manifest.get("contract")
    if not isinstance(contract, dict):
        raise MountRefused("manifest's contract block is missing or not an object — cannot resolve what this mount grants")

    manifest_version = manifest.get("version")
    if not manifest_version:
        raise MountRefused("manifest is missing version — required to detect narrowing on re-mount")

    commit_hash, err = resolve_commit_hash(mount_path)
    if err:
        raise MountRefused(err)

    # Belt-and-suspenders on top of the dirty-tree refusal above: byte-verify
    # the manifest actually evaluated (working tree) matches what
    # `resolved_commit` would check out. Closes the confirmed bypass where
    # the working tree and HEAD's committed manifest were allowed to
    # diverge — see verify_manifest_matches_head()'s docstring.
    mismatch_err = verify_manifest_matches_head(mount_path, commit_hash, manifest_raw_text)
    if mismatch_err:
        raise MountRefused(mismatch_err)

    # 44badb55 §4 — pull-side publish-boundary enforcement ("B does NOT
    # trust A"). vault_uid is resolved above (from the manifest) before this
    # point, so it is available as the positive/target-relative segment
    # comparator the boundary re-check needs.
    pull_side_err = pull_side_team_branch_check(mount_path, vault_uid)
    if pull_side_err:
        raise MountRefused(f"publish-boundary refusal (44badb55 §4): {pull_side_err}")

    lock_data = load_compose_lock(compose_lock_path)
    vaults = lock_data.setdefault("vaults", {})
    existing = vaults.get(vault_uid)

    capabilities = list(contract.get("capabilities") or [])
    name_prefix = manifest.get("prefix_policy", {}).get("mint_prefix") if isinstance(manifest.get("prefix_policy"), dict) else None

    reserved = reserved_capability_names()
    qual_violations = qualification_violations(capabilities, vault_uid, name_prefix, reserved)
    if qual_violations:
        raise MountRefused(
            "dependency-confusion refusal (AC-2): " + "; ".join(qual_violations)
        )

    if existing is not None and not force_remount:
        raise MountRefused(
            f"vault-UID {vault_uid} already has a compose.lock record (mounted "
            f"{existing.get('mounted_at', '?')}, pinned {existing.get('resolved_commit', '?')[:12]}) "
            f"— one-clone-per-vault-UID (AC-5, satisfies signed I1 dd16c90c). Use "
            f"--force-remount to explicitly re-mount/update this vault-UID's record."
        )

    consent_required = len(capabilities) > 0
    added_caps: list[str] = []
    if existing is not None and force_remount:
        old_contract = existing.get("contract") or {}
        narrow_reasons = contract_is_narrowed(old_contract, contract)
        added_caps = contract_added_capabilities(old_contract, contract)
        if narrow_reasons:
            old_version = existing.get("manifest_version")
            version_bumped = str(manifest_version) != str(old_version)
            if not version_bumped:
                raise MountRefused(
                    "contract NARROWING without a version bump (a1f7c750 Guarded Transitions): "
                    + "; ".join(narrow_reasons)
                    + f" — manifest.version is still {manifest_version!r} (was {old_version!r}); "
                      f"bump version AND pass --consent to re-consent (AC-6)"
                )
            if not consent:
                raise MountRefused(
                    "contract NARROWING with a version bump still requires --consent "
                    "(re-consent for the delta, a1f7c750 Guarded Transitions / bc25583d §6): "
                    + "; ".join(narrow_reasons)
                )
        elif added_caps and not consent:
            raise MountRefused(
                f"contract WIDENING added new capabilities {added_caps} with no recorded "
                f"consent for the delta — re-run with --consent (bc25583d §6: consent "
                f"covers the capability_set, and widening the set re-triggers it)"
            )
    elif consent_required and not consent:
        raise MountRefused(
            f"vault {vault_uid} declares executable capabilities {capabilities} but no "
            f"--consent was given — executable-consent MUST be a recorded governed write "
            f"before a mounted vault's capabilities become invocable (AC-3, bc25583d §6). "
            f"Nothing was written to compose.lock."
        )

    record: dict[str, Any] = {
        "vault_uid": vault_uid,
        "resolved_commit": commit_hash,
        "manifest_version": manifest_version,
        "contract_hash": contract_hash(contract),
        "contract": contract,
        "name_prefix": name_prefix or vault_uid,
        "mounted_at": existing.get("mounted_at") if (existing and not consent) else NOW,
        "mounted_by": mounted_by,
        # mount_path + manifest_kind: added to close a governed-write-gate
        # blind spot (confirmed finding, security review 2026-07-08) —
        # without a durable mount-path, check_vault_manifest_governed_write_gate
        # in tropo-validate.py could only re-hash compose.lock's OWN embedded
        # contract against its OWN contract_hash (catches a hand-edit of
        # compose.lock, never a hand-edit of the actual governed artifact,
        # the per-vault-root manifest file, which is what AC-1 names). This
        # is advisory/local-filesystem state (a real federated mount-path is
        # not guaranteed durable across machines), so the validator treats
        # its absence or unreachability as "cannot verify," never a silent
        # pass — see check_vault_manifest_governed_write_gate.
        "mount_path": str(mount_path),
        "manifest_kind": manifest.get("kind"),
    }

    if consent:
        record["consent"] = {
            "consented": True,
            "consented_by": mounted_by,
            "consented_at": NOW,
            "capability_set": sorted(capabilities),
        }
    elif existing is not None and existing.get("consent"):
        # Re-mount with no new consent needed (e.g. non-narrowing, no new caps) —
        # preserve the prior consent record rather than silently dropping it.
        record["consent"] = existing["consent"]
    else:
        record["consent"] = {"consented": False, "capability_set": []}

    vaults[vault_uid] = record
    write_compose_lock(compose_lock_path, lock_data)
    return record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="tropo-mount.py",
        description=(
            "Mount-gate for vault composition (ADR-051 Fork 2, dev-spec 409ef1cc). "
            "Validates a candidate vault's manifest+contract, pins the mount to a "
            "resolved commit hash in .tropo-studio/compose.lock, requires "
            "executable-consent as a governed write (not a prompt), enforces "
            "<vault>:skill name-qualification, and enforces one-clone-per-vault-UID."
        ),
        epilog=(
            "Refusal classes (exit 1, compose.lock always left UNCHANGED on refusal):\n"
            "  - manifest missing/invalid (a1f7c750 schema)\n"
            "  - mount-path is not a git repo / commit unresolvable (unpinned mount)\n"
            "  - unqualified capability name shadows a reserved OS/private name\n"
            "  - executables declared with no --consent\n"
            "  - vault-UID already mounted, no --force-remount\n"
            "  - contract narrowed without a version bump + --consent re-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mount-path", required=True, type=Path,
                         help="path to the candidate vault-root (must contain .tropo/vault-manifest.md and be a git repo)")
    parser.add_argument("--consent", action="store_true",
                         help="explicitly grant executable-consent for this mount's declared capabilities (governed write, recorded in compose.lock — not a prompt)")
    parser.add_argument("--force-remount", action="store_true",
                         help="required to re-mount / update an already-present vault-UID's compose.lock record")
    parser.add_argument("--compose-lock", type=Path, default=DEFAULT_COMPOSE_LOCK,
                         help=f"path to the compose-lockfile (default: {DEFAULT_COMPOSE_LOCK})")
    parser.add_argument("--mounted-by", default=os.environ.get("USER", "unknown"),
                         help="advisory provenance recorded on the compose.lock record")
    args = parser.parse_args()

    mount_path = args.mount_path.resolve()
    if not mount_path.is_dir():
        print(f"[FAIL] --mount-path {mount_path} does not exist or is not a directory")
        return 2

    try:
        record = run_mount(
            mount_path=mount_path,
            consent=args.consent,
            force_remount=args.force_remount,
            compose_lock_path=args.compose_lock.resolve(),
            mounted_by=args.mounted_by,
        )
    except MountRefused as e:
        print(f"[REFUSED] {e}")
        return 1

    print(
        f"[MOUNTED] vault_uid={record['vault_uid']} "
        f"resolved_commit={record['resolved_commit'][:12]} "
        f"manifest_version={record['manifest_version']} "
        f"consent={record['consent'].get('consented', False)} "
        f"-> {args.compose_lock.resolve()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
