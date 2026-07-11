"""lib/segment.py — un-forgeable segment derivation (dev-spec 44badb55, ADR-051
Ruling 3 — "the biggest red-team fix").

SHARED module imported by tropo-publish.py (the publish-side two-gate filter),
tropo-validate.py's check_publish_boundary (client-side re-validation), and
tropo-mount.py's pull-side enforcement — one derivation, three consumers, so
none of them can silently disagree on what "segment" means for a record.

THE RULING THIS IMPLEMENTS (Argus A128, 44badb55 §3 / Ruling 3):
  segment is DERIVED from the record's enclosing vault-node manifest UID
  (signed I1, dd16c90c/5d3ab142), durable + authored (stamped at a vault's
  own genesis), NEVER a hand-editable per-record frontmatter field and NEVER
  computed from runtime reachability (whether a vault happens to be mounted
  in somebody's compose.lock right now varies machine-to-machine — that was
  the determinism hole). A hand-edited `segment:` value on a record never
  governs; a mismatch between the derived value and a stray frontmatter
  claim is the CALLER's job to treat as an ERROR (this module only derives —
  it does not itself decide what a mismatch means for a given gate).

TWO CASES, exactly one applies to any given vault_root:
  1. vault_root carries its OWN `.tropo/vault-manifest.md` (a standalone or
     mounted vault-node, per 943bb220/5d3ab142 §2) -> segment == that
     manifest's own `uid` — a per-VAULT-ROOT constant, read fresh from the
     manifest file every call, never cached across vault_roots. This is
     what a real team vault (44badb55's publish target) resolves to.
  2. vault_root has no manifest of its own (this studio's own bundled vault
     — the only case that exists in production today; REAL-STUDIO GENESIS
     is deferred per 32067bea) -> fall back UNCHANGED to the existing
     os/private discriminator already live in lib.gardener
     (discriminate_segment + safety_net_segment + backfill_extraction_scope_
     by_path, all IMPORTED here, never duplicated) — zero behavior change
     for the local vault's own index build.

This module does not replace lib.gardener's os/private logic; it composes
with it. gardener.py itself is unamended by this dev-spec (not in 44badb55's
committed_substrate) — it keeps working exactly as it does today, because
case 2 above delegates straight through to gardener's existing functions.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

import yaml

from lib.gardener import (
    discriminate_segment,
    safety_net_segment,
    resolve_effective_scope,
)

# ---------------------------------------------------------------------------
# The public allowlist (Ruling 2): a versioned CODE-CONSTANT, never config —
# config is edit-without-review; a frozenset literal here means widening the
# public surface is itself a reviewable code change. Frozen at v1.84 per the
# spec's DETERMINISM acceptance criterion (AC11): this ruleset does not
# silently grow across a rebuild.
# ---------------------------------------------------------------------------
PUBLIC_EXTRACTION_SCOPES = frozenset({"ship", "external"})

# Shared between tropo-publish.py (writes this branch) and tropo-validate.py's
# check_publish_boundary (re-reads it) — one name, so a future rename can't
# leave the validator checking a branch the publisher stopped writing to.
TEAM_BRANCH_DEFAULT = "team-main"

VAULT_MANIFEST_REL = Path(".tropo") / "vault-manifest.md"
_FRONTMATTER_RE = re.compile(r'^---\n(.*?\n)---\n', re.DOTALL)
_UID_RE = re.compile(r'^[0-9a-f]{8}$')

# Unicode category prefixes stripped before compare: Cf (format — zero-width
# space, joiners, bidi controls) and Cc (control chars). Identical pipeline to
# tropo-mount.py's _normalize_capability_name (Argus A128's exact recommended
# order, event 00005962) — reused verbatim here rather than re-derived, so
# scope-normalization and capability-name-normalization cannot drift apart on
# "how much" to normalize. Both defend the same bypass class: a value that
# survives a naive string compare only because of case, whitespace, or a
# Unicode homoglyph that NFKC-normalizes to the reserved/allowlisted form.
_STRIPPED_UNICODE_CATEGORIES = ("Cf", "Cc")


def normalize_extraction_scope(value: Optional[str]) -> str:
    """NFKC -> strip Cf/Cc -> strip() -> casefold(). Returns '' for
    None/empty/whitespace-only, which never matches the allowlist — the
    fail-closed default-deny behavior falls out of this for free rather
    than needing a separate "is it set" branch at every call site."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = "".join(
        ch for ch in normalized
        if unicodedata.category(ch) not in _STRIPPED_UNICODE_CATEGORIES
    )
    return normalized.strip().casefold()


def is_public_scope(value: Optional[str]) -> bool:
    """Gate 3 (44badb55 §5): normalized extraction_scope in the public
    allowlist. Unmarked/None/empty/private/argo-reference/unrecognized/
    normalization-variant all return False — default-deny, not a denylist."""
    return normalize_extraction_scope(value) in PUBLIC_EXTRACTION_SCOPES


def _split_frontmatter(text: str) -> Optional[str]:
    m = _FRONTMATTER_RE.match(text)
    return m.group(1) if m else None


def read_vault_manifest_uid(vault_root: Path) -> Optional[str]:
    """Read <vault_root>/.tropo/vault-manifest.md's own `uid` (or
    `vault_uid`) — the durable, authored identity of the vault-node that
    governs everything physically under vault_root. Returns None if no
    manifest exists at this root, if it fails to parse, or if the uid field
    is missing/malformed — all of which mean "this is not a standalone
    vault-node," never an error to raise here (the caller's fallback to case
    2 handles it)."""
    manifest_path = vault_root / VAULT_MANIFEST_REL
    if not manifest_path.is_file():
        return None
    try:
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fm_text = _split_frontmatter(text)
    if fm_text is None:
        return None
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    uid = fm.get("uid") or fm.get("vault_uid")
    if not uid or not _UID_RE.match(str(uid)):
        return None
    return str(uid)


def derive_segment(
    rec: dict,
    vault_root: Path,
    ship_manifest_uids: Optional[set[str]] = None,
) -> str:
    """THE single source of truth for segment (Ruling 3). NEVER reads a
    per-record `segment:` frontmatter field — callers that need to detect a
    forged/stale frontmatter claim compare THIS return value against the
    record's own field and treat a mismatch as their own ERROR condition;
    this function only derives the true value.

    `rec` needs only `uid`, `extraction_scope` (optional), and `path`
    (relative to vault_root) — the same shape lib.gardener's functions
    already expect, so this composes with the existing index-build records
    with no reshaping.
    """
    manifest_uid = read_vault_manifest_uid(vault_root)
    if manifest_uid:
        return manifest_uid

    scope, _was_backfilled = resolve_effective_scope(rec)
    seg = discriminate_segment(rec, scope or None, ship_manifest_uids or set())
    if not scope and seg != "os":
        seg = safety_net_segment(rec.get("path", ""))
    return seg


# ---------------------------------------------------------------------------
# Publish-boundary git-hygiene checks (44badb55 §5 gate 5 / Ruling 5, 6, 10).
#
# SHARED between tropo-publish.py (pre-push self-check, the "A" side) and
# tropo-validate.py's check_publish_boundary (independent post-push/post-pull
# re-check, the "B don't-trust-A's-receipt" side, Ruling 10). One correct
# implementation, not two that could silently disagree — same reasoning as
# lib.shard_index.staleness_findings being shared by writer and validator.
# "Independent verification" (Ruling 10) means B re-derives the actual git
# state itself rather than trusting A's receipt as an assertion; it does not
# require a SEPARATE algorithm to do that re-derivation correctly.
# ---------------------------------------------------------------------------

import subprocess  # noqa: E402


def check_no_submodules(repo_root: Path) -> Optional[str]:
    gitmodules = repo_root / ".gitmodules"
    if gitmodules.is_file():
        return f".gitmodules present at {gitmodules} — submodules are refused (gitlink objects are an ancestry/leak surface)"
    return None


def check_single_worktree(repo_root: Path) -> Optional[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "worktree", "list"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return None  # cannot verify; not a hard refusal (older git lacks `worktree list` in some builds)
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    if len(lines) > 1:
        return f"{len(lines)} worktrees detected for {repo_root} — refused (multi-worktree is an unaudited state-sharing surface)"
    return None


def check_reflog_disabled(remote: str) -> tuple[bool, str]:
    """Best-effort, disclosed-limitation check (Ruling 11: platform remotes
    we don't control are a named ceiling, not a hidden hole). If `remote`
    resolves to a local filesystem path (the test-harness / a self-hosted
    bare repo), read its config directly. If it is a URL (http(s)/ssh — a
    real GitHub/GitLab-class remote), this cannot be verified client-side;
    that limitation is surfaced rather than silently assumed clean."""
    if "://" in remote or (":" in remote and "@" in remote):
        return True, (
            f"remote {remote!r} is not a local path — reflog-disabled cannot be verified "
            f"client-side (named platform limit, Ruling 11); proceeding without this "
            f"specific assertion"
        )
    remote_path = Path(remote).resolve()
    if not remote_path.exists():
        return True, f"remote path {remote_path} does not exist yet — reflog check skipped for a not-yet-existing bare repo"
    config_result = subprocess.run(
        ["git", "-C", str(remote_path), "config", "--get", "core.logallrefupdates"],
        capture_output=True, text=True, timeout=10,
    )
    value = config_result.stdout.strip().lower()
    if value == "true":
        return False, (
            f"remote {remote_path} has core.logallrefupdates=true (reflog ENABLED) — refused "
            f"(Ruling 5/AC8: a force-reset-away private-adjacent state must not be recoverable "
            f"via reflog on the far end)"
        )
    return True, f"remote {remote_path} reflog disabled (core.logallrefupdates={value or 'false/unset'})"


def verify_clean_ancestry(repo_root: Path, commit: str) -> tuple[bool, str]:
    """Walks the full history reachable from `commit` and confirms: (a)
    every commit has AT MOST ONE parent (no merge commit ever entered this
    history — a merge is exactly how unrelated/private history could sneak
    in), and (b) the oldest reachable commit has ZERO parents (a true
    orphan root, never grafted onto anything pre-existing). Returns
    (holds, detail)."""
    log_result = subprocess.run(
        ["git", "-C", str(repo_root), "log", "--format=%H %P", commit],
        capture_output=True, text=True, timeout=30,
    )
    if log_result.returncode != 0:
        return False, f"git log failed: {log_result.stderr.strip()}"

    lines = [ln for ln in log_result.stdout.splitlines() if ln.strip()]
    if not lines:
        return False, "git log returned no history for the given commit"

    root_count = 0
    for line in lines:
        parts = line.split()
        commit_hash = parts[0]
        parents = parts[1:]
        if len(parents) > 1:
            return False, f"commit {commit_hash} is a MERGE ({len(parents)} parents) — ancestry is not linear/orphan-safe"
        if len(parents) == 0:
            root_count += 1

    if root_count != 1:
        return False, f"expected exactly one orphan root in history, found {root_count}"

    objects_result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-list", "--objects", commit],
        capture_output=True, text=True, timeout=30,
    )
    if objects_result.returncode != 0:
        return False, f"git rev-list --objects failed: {objects_result.stderr.strip()}"

    return True, (
        f"{len(lines)} commit(s) reachable, linear, single orphan root; "
        f"{len(objects_result.stdout.splitlines())} object(s) reachable"
    )


def _boundary_violations_at_one_commit(
    repo_root: Path, team_vault_uid: str, commit: str,
) -> list[str]:
    """The single-commit tree-walk (what the whole-history walker below
    calls once per ancestor). Walks the COMMITTED tree at `commit` (via
    `git ls-tree` + `git show` — NEVER the working tree, closing the TOCTOU
    between whatever a filter saw and what is actually in the object
    store).

    Segment resolution mirrors lib.shard_index.derive_mounted_shard_
    records's own fix for the SAME interlocking findings (#1 fail-open +
    #4 tautology + #10 "key off compose.lock"): if repo_root has a
    resolvable manifest (the publish-side case — checking the ORIGINAL
    team-vault-root's own history, which stays on a manifest-bearing
    branch throughout), derive_segment provides an independent
    cross-check against team_vault_uid. If repo_root has no manifest (a
    pull-side mount of just the published branch), team_vault_uid —
    supplied by the caller from compose.lock, established once at
    original mount-gate time — is trusted directly; the scope gate below
    still runs unconditionally either way, so nothing not provably public
    can pass regardless of which branch resolved the segment.
    """
    manifest_present = read_vault_manifest_uid(repo_root) is not None
    violations: list[str] = []
    ls_tree_full = subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", "-r", commit],
        capture_output=True, text=True, timeout=30,
    )
    if ls_tree_full.returncode != 0:
        return [f"git ls-tree failed at commit {commit[:12]}: {ls_tree_full.stderr.strip()}"]

    md_paths: list[str] = []
    for line in ls_tree_full.stdout.splitlines():
        if line.startswith("160000 "):
            violations.append(
                f"gitlink (mode 160000) object present at commit {commit[:12]} ({line.strip()}) — refused"
            )
            continue
        if line.startswith("120000 "):
            violations.append(
                f"symlink (mode 120000) tree entry present at commit {commit[:12]} ({line.strip()}) — refused"
            )
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        rel_path = parts[1].strip()
        if rel_path.startswith("vault/files/") and rel_path.endswith(".md"):
            md_paths.append(rel_path)

    fm_re = re.compile(r'^---\n(.*?\n)---\n', re.DOTALL)
    for rel_path in md_paths:
        show_result = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{commit}:{rel_path}"],
            capture_output=True, text=True, timeout=10,
        )
        if show_result.returncode != 0:
            continue
        if show_result.stdout.lstrip().startswith("version https://git-lfs"):
            violations.append(f"{rel_path!r} at commit {commit[:12]} is an LFS pointer file — refused")
            continue
        m = fm_re.match(show_result.stdout)
        if not m:
            # SECURITY-REVIEW FIX (Argus A128 HEAVY-verify BOUNCE finding
            # #11, 2026-07-09): a vault/files/*.md blob with NO parseable
            # frontmatter was previously treated as clean (silently
            # skipped) — that is fail-OPEN for a malformed governed-path
            # blob. A file living at this path with no readable
            # frontmatter cannot prove it cleared the boundary; default-DENY.
            violations.append(
                f"{rel_path!r} at commit {commit[:12]} has NO parseable frontmatter — "
                f"a governed-path blob must prove its extraction_scope/segment to cross; "
                f"refused (default-deny, not silently treated as clean)"
            )
            continue
        try:
            fm = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            violations.append(f"{rel_path!r} at commit {commit[:12]} has UNPARSEABLE YAML frontmatter — refused")
            continue
        if not isinstance(fm, dict):
            violations.append(f"{rel_path!r} at commit {commit[:12]} frontmatter did not parse to a mapping — refused")
            continue
        raw_scope = fm.get("extraction_scope")
        rec = {"uid": fm.get("uid"), "extraction_scope": raw_scope, "path": rel_path}
        segment = derive_segment(rec, repo_root) if manifest_present else team_vault_uid

        # AC3 (BOUNCE finding #4's concrete, actionable half): a record's OWN
        # frontmatter `segment:` field, if present, is cross-checked against
        # team_vault_uid — a disagreement is exactly the tamper signature
        # (content authored/claimed for one vault, physically committed
        # under another) and is a violation regardless of what derive_segment
        # independently resolves. NOTE (disclosed, not fabricated): this
        # closes the SPECIFIC gap Argus named ("derive_segment never reads a
        # per-record segment field, so forged provenance is silently
        # accepted") but does not by itself make segment cryptographically
        # un-forgeable — an attacker who also forges a matching `segment:`
        # value defeats this specific check. True mint-time provenance
        # (a ledger or UID-embedded mint-prefix, independent of anything the
        # record's own frontmatter claims) is a separate, larger build this
        # dev-spec's committed_substrate does not cover; flagged back to
        # Argus as a named follow-up, not silently declared solved.
        claimed_segment = fm.get("segment")
        if claimed_segment is not None and str(claimed_segment) != str(team_vault_uid):
            violations.append(
                f"{rel_path!r} at commit {commit[:12]} carries frontmatter segment={claimed_segment!r} "
                f"which DISAGREES with team-vault-uid={team_vault_uid!r} — refused (AC3 mismatch)"
            )
            continue

        if not is_public_scope(raw_scope) or segment != team_vault_uid:
            violations.append(
                f"committed file {rel_path!r} at commit {commit[:12]} FAILS the two-gate boundary "
                f"(scope={raw_scope!r}, derived_segment={segment!r} vs team-vault-uid={team_vault_uid!r})"
            )
    return violations


def find_boundary_violations_in_committed_tree(
    repo_root: Path, team_vault_uid: str, tip: str,
) -> list[str]:
    """Walks EVERY commit reachable from `tip` — not just `tip` itself —
    and returns the union of _boundary_violations_at_one_commit's findings
    across all of them. Empty list = clean.

    SECURITY-REVIEW FIX (Argus A128 HEAVY-verify BOUNCE finding #2
    "ancestry poisoning", 2026-07-09): the prior version checked ONLY the
    tip's tree. verify_clean_ancestry (below) proves the commit GRAPH SHAPE
    is clean (linear, single orphan root) but says nothing about whether
    each ancestor's CONTENT ever held a private file — a private blob
    committed at any point in history stays reachable (and gets
    transferred by any clone/fetch) even if a LATER commit's tip looks
    clean, exactly the classic "deleted in a later commit, still in
    history forever" problem. Walking every reachable commit's tree is
    what actually closes it, both on the publish side (before pushing a
    newly-built commit whose PARENT's history was never itself
    re-verified) and the pull/audit side (B re-checking A's claims).

    SHARED by tropo-validate.py's check_publish_boundary (post-hoc validator
    re-check), tropo-mount.py's pull-side enforcement ("B does not trust
    A"), and tropo-publish.py's own pre-push self-check — one tree-walk
    implementation, not several that could silently drift on what "clean"
    means.
    """
    rev_list_result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-list", tip],
        capture_output=True, text=True, timeout=30,
    )
    if rev_list_result.returncode != 0:
        return [f"git rev-list failed at tip {tip[:12]}: {rev_list_result.stderr.strip()}"]
    commits = [c for c in rev_list_result.stdout.splitlines() if c.strip()]
    if not commits:
        return [f"git rev-list returned no history for tip {tip[:12]}"]

    violations: list[str] = []
    for commit in commits:
        violations.extend(_boundary_violations_at_one_commit(repo_root, team_vault_uid, commit))
    return violations


def check_no_shallow_clone(repo_root: Path) -> Optional[str]:
    """Pull-side enforcement (44badb55 §4): B refuses a shallow clone — a
    manipulated shallow boundary (a `--depth` clone that silently omits
    history) can smuggle private ancestry past a check that only looks at
    what history happens to be present locally. Returns a refusal reason,
    or None if the repo is a full clone (or shallowness cannot be
    determined, which is treated as "not shallow" — git itself reports
    false for a non-shallow repo, and a missing/unreadable .git/shallow is
    the same as false)."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--is-shallow-repository"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return None
    if result.stdout.strip().lower() == "true":
        return (
            f"{repo_root} is a SHALLOW clone (git rev-parse --is-shallow-repository=true) — "
            f"refused (44badb55 §4: a shallow boundary can smuggle private ancestry past a "
            f"history check that never sees what was truncated)"
        )
    return None


def check_gitdir_distinct(repo_a: Path, repo_b: Path) -> Optional[str]:
    """Refuses if two repo roots resolve to the SAME .git directory (e.g. a
    team-vault mount_path that is actually the studio's own repo, or a
    worktree of it) — the physical-separation invariant (44badb55 §1:
    "private segment = studio's own repo; team segment = a separate
    mounted repo with its own remote") must hold on disk, not just in
    manifest metadata."""
    git_a = (repo_a / ".git").resolve() if (repo_a / ".git").exists() else None
    git_b = (repo_b / ".git").resolve() if (repo_b / ".git").exists() else None
    if git_a is not None and git_a == git_b:
        return f"{repo_a} and {repo_b} share the SAME .git directory ({git_a}) — refused (physical-separation invariant, §1)"
    return None
