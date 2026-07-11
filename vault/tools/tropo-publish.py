#!/usr/bin/env python3
"""
---
uid: 6f9a3c72
name: tropo-publish
type: tool
title: "tropo-publish — orphan-commit public-only publisher (Git Beat 2 federation transport)"
status: active
owner: talos
domain: "The public-only ORPHAN-COMMIT publisher for a mounted team vault (a separate repo, its own remote — never the studio's private repo). Enumerates the team vault's filesystem, applies the two-gate allowlist (extraction_scope public + segment==this-vault-UID), builds a fresh commit from exactly the passing files with no private ancestry, and pushes only that one branch ref. Implements dev-spec 44badb55 (ADR-051, Argus A128 lane)."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-publish.py"
script_path: vault/tools/tropo-publish.py
spawnable_by:
  - all-executives
input:
  type: object
  description: "See --help for full argument details"
created: '2026-07-08'
created_by: talos-t27
governed_by: 8dd772a0
member_of:
  - cd1fcd25
schema_version: 2
extraction_scope: argo-reference
belt: false  # trimmed from belt by vela-v65 2026-07-10 — over the 15-entry cap; mount/publish are federation-specific, lock-dev-spec is ceremony-specific. Cataloged + functional; not in quick-ref.
belt_invocation: "python3 vault/tools/tropo-publish.py --team-vault-root <path> --remote <remote> [--apply]"
belt_example: "python3 vault/tools/tropo-publish.py --team-vault-root ../team-vault --remote origin --apply"
---
"""

"""tropo-publish.py — the orphan-commit publisher (dev-spec 44badb55).

Authored 2026-07-08 by Talos T27 per Argus A128's red-team-hardened dev-spec
44badb55 (ADR-051, the v1.84 federation DoD). Ratified rulings this build
does NOT re-litigate (44badb55 "Rulings — build against these"):

  - Transport = git-remote (Mike-decided). No Supabase.
  - Allowlist + default-deny, NORMALIZED: public frozenset code-constant
    ({ship, external}) — lib.segment.PUBLIC_EXTRACTION_SCOPES, compared via
    lib.segment.normalize_extraction_scope (NFKC+Cf/Cc-strip+casefold,
    identical pipeline to tropo-mount.py's _normalize_capability_name).
  - Segment is DERIVED + un-forgeable + positive + target-relative
    (lib.segment.derive_segment) — never a hand-edited frontmatter field.
  - Deterministic tool-call, never agent judgment — this script reads
    durable fields mechanically; no LLM judges publicness.
  - Public-only ACCUMULATING history, private-ancestry-free: the FIRST
    publish is an orphan root; each SUBSEQUENT publish's parent is the
    prior team-branch tip (itself public-only) — never a merge/rebase/
    cherry-pick from the private repo.
  - Both ends enforce — this is the publish (A) side; tropo-mount.py's
    pull-side amendment is the (B) side. Client-side only; server hooks
    untrusted.
  - Fail-closed / default-refuse: unmarked, ambiguous, unresolved-path, or
    unprovable does not cross.
  - Honest receipt, no metadata leak: held-back is receipted (uid/scope/
    segment only, never title/body); never silently dropped.
  - Forward-only revocation (named limit, not a bug): the covenant holds at
    PUSH TIME; a file downgraded public->private after it crossed is
    already out. This tool does not attempt retroactive redaction.

WHAT THIS SCRIPT DOES, in order, on every `--apply` invocation (dry-run
without --apply performs every step through the receipt, then stops before
the git-object writes and the push):

  1. Enumerates the FILESYSTEM of <team-vault-root>/vault/files/*.md — NOT
     git's tracked-file list (a private file hiding as untracked/gitignored
     must still be caught and refused, never silently skipped-as-if-clean).
  2. For each candidate, in this exact order: lstat (refuse symlinks —
     lstat does not follow them, unlike stat); refuse hardlinks
     (st_nlink > 1); realpath (refuse anything resolving outside the
     team-vault root) — ALL of this BEFORE reading any frontmatter, so a
     malicious/mistaken path never gets far enough to leak scope metadata
     via a stack trace or partial read.
  3. Reads frontmatter; applies the two-gate filter (lib.segment.is_public_
     scope(extraction_scope) AND lib.segment.derive_segment(rec, team_vault_
     root) == this team-vault's own manifest uid).
  4. Builds a tree from EXACTLY the passing files using an ISOLATED
     temporary git index (GIT_INDEX_FILE) — never `git add` of the real
     working tree/index, which could sweep in an untracked private file
     that happens to sit in the same directory. Blobs are written via
     `git hash-object -w` into the team-vault-root's OWN object store
     (never the private repo's — they are different repositories with
     different object stores by construction; there is no path here for a
     private-repo object hash to ever enter this store).
  5. Commits that tree via `git commit-tree`: parent = the prior team-branch
     tip (read from the LOCAL team-vault-root's own ref, which only ever
     advances via a prior successful publish) or NONE for the very first
     publish (a true orphan root). Committer identity is a FIXED, generic
     federation identity; the message is a FIXED template — neither
     carries a private UID, a private path, or this studio's identity.
  6. Pushes ONLY that single branch ref to `--remote` — never `--all`,
     never `--tags`, never `--follow-tags`, never `refs/notes/*`.
  7. Emits a receipt: the crossed set (uid, path, normalized scope, derived
     segment, content sha256), the held-back COUNT + minimal provenance
     (uid/scope/segment only — no title/body), an ancestry proof (the
     pushed commit's hash + parent + a `git rev-list --objects` walk
     confirming every reachable commit has at most one parent and the
     oldest has none — i.e. no merge ever occurred and the root is a true
     orphan), and environment assertions (reflog-disabled where checkable,
     no submodules, single worktree).

The privacy boundary is this filter + the orphan/accumulating-only
construction — NOT .gitignore (792919dd fork 3; .gitignore is a hygiene
backstop, never the enforcement mechanism).

Usage:
    python3 vault/tools/tropo-publish.py \\
        --team-vault-root <path-to-the-team-vault-repo-root> \\
        --remote <git-remote-url-or-local-path> \\
        [--branch team-main]        # default team branch name
        [--apply]                  # required to actually write objects + push; default is dry-run preview
        [--receipt-out <path>]      # write the receipt JSON here (default: print to stdout)
        [--committer-name ...] [--committer-email ...]  # override the fixed federation identity (testing only)

Exit codes:
    0   Success (dry-run preview, or --apply completed and pushed)
    1   Refused — no manifest at team-vault-root, remote reflog enabled,
        dirty prerequisite state, or a push-time git failure
    2   Argument / environment error
"""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
STUDIO_ROOT = SCRIPT_DIR.resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))  # so `from lib.segment import ...` resolves regardless of CWD

from lib.segment import (  # noqa: E402
    TEAM_BRANCH_DEFAULT,
    is_public_scope,
    normalize_extraction_scope,
    read_vault_manifest_uid,
    derive_segment,
    check_no_submodules,
    check_single_worktree,
    check_reflog_disabled,
    verify_clean_ancestry,
    find_boundary_violations_in_committed_tree,
)

FRONTMATTER_RE = re.compile(r'^---\n(.*?\n)---\n', re.DOTALL)

# Fixed, generic federation identity — deliberately carries NOTHING
# studio-specific (no Mike, no studio_id, no mint_prefix). A leak vector
# closure finding (44badb55 §2.4): commit author + message are metadata
# that travels with public history forever, so they must be as anonymous
# as the content-boundary itself.
FEDERATION_COMMITTER_NAME = "Tropo Federation Publisher"
FEDERATION_COMMITTER_EMAIL = "federation-publish@tropo.invalid"
# BOUNCE finding #7 "DETERMINISM" (Argus A128, 2026-07-09): the template
# previously embedded a free-running wall-clock timestamp, so two
# publishes of byte-identical content produced different commit messages
# for no content-driven reason. The count is content-derived (crossed set
# size); nothing else varies.
COMMIT_MESSAGE_TEMPLATE = "tropo-publish: {count} file(s)\n"


class PublishRefused(Exception):
    """Raised with a human-readable reason; caller prints '[REFUSED] <reason>' and exits 1."""


# ---------------------------------------------------------------------------
# Frontmatter read (post path-safety only — see enumerate_and_filter).
# ---------------------------------------------------------------------------

def _split_frontmatter(text: str) -> Optional[str]:
    m = FRONTMATTER_RE.match(text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Path safety (§2 step 2 / AC "ADVERSARIAL PATH-ESCAPE"). Order matters: this
# runs BEFORE any frontmatter read.
# ---------------------------------------------------------------------------

def path_safety_refusal(path: Path, team_vault_root: Path) -> Optional[str]:
    """Returns a refusal reason string, or None if the path is safe to read.

    lstat (never stat) so a symlink is detected as itself, not followed —
    stat() would silently resolve through it and inspect the TARGET's
    properties instead of catching the symlink itself.
    """
    try:
        st = path.lstat()
    except OSError as e:
        return f"could not lstat {path}: {e}"

    if stat.S_ISLNK(st.st_mode):
        return f"{path} is a symlink — refused before any content is read (path-escape defense)"

    # BOUNCE finding #6 (Argus A128, 2026-07-09): a FIFO/device/socket named
    # *.md previously passed this check (only symlink-mode was excluded) —
    # only a genuine regular file may ever cross.
    if not stat.S_ISREG(st.st_mode):
        return f"{path} is not a regular file (mode {oct(st.st_mode)}) — refused"

    if st.st_nlink > 1:
        return f"{path} is a hardlink (st_nlink={st.st_nlink}) — refused (path-escape defense)"

    try:
        resolved = path.resolve(strict=True)
        resolved_root = team_vault_root.resolve(strict=True)
    except OSError as e:
        return f"could not resolve realpath for {path}: {e}"

    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return (
            f"{path} resolves to {resolved}, OUTSIDE the team-vault root "
            f"{resolved_root} — refused (path-escape defense)"
        )

    return None


def read_file_atomically(path: Path) -> bytes:
    """BOUNCE finding #3 "TOCTOU content-swap" (Argus A128, 2026-07-09):
    path_safety_refusal's lstat and a LATER plain read() are two separate
    syscalls with a window between them where the path could be swapped
    (e.g. replaced with a symlink, or a different file moved into place).
    Opening with O_NOFOLLOW makes symlink-refusal atomic with the read
    itself (the SAME fd that's fstat-checked is the one read from — no
    second lookup of the path string can occur), and the fstat re-confirms
    regular-file + single-link status against that exact fd, not a
    possibly-stale path.
    """
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise PublishRefused(f"{path} is not a regular file at read-time (mode {oct(st.st_mode)}) — refused (TOCTOU defense)")
        if st.st_nlink > 1:
            raise PublishRefused(f"{path} is a hardlink at read-time (st_nlink={st.st_nlink}) — refused (TOCTOU defense)")
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Enumeration + the two-gate filter.
# ---------------------------------------------------------------------------

def enumerate_and_filter(
    team_vault_root: Path,
    team_vault_uid: str,
) -> tuple[list[dict], list[dict]]:
    """Returns (crossed, held_back).

    crossed: list of {uid, path (relative to team_vault_root), content_bytes,
             normalized_extraction_scope, derived_segment, content_sha256}
    held_back: list of {uid, extraction_scope, segment} — NO title/type/
               description/body, per the receipt's no-metadata-leak rule.

    Enumerates the FILESYSTEM (Path.glob), never git's tracked-file list —
    an untracked/gitignored private file must still be seen and refused,
    not silently invisible to this scan.

    BOUNCE finding #3 "TOCTOU content-swap" (Argus A128, 2026-07-09): reads
    each file's bytes EXACTLY ONCE here (via read_file_atomically), via the
    same fd used to derive content_sha256 — the FILTER'S verdict and the
    bytes build_tree() later commits are now guaranteed to be the same
    bytes, because build_tree() reuses content_bytes rather than opening
    the path a second time. A prior version read the path twice (once here
    for the sha256, again inside build_tree for hash-object) with no
    guarantee the file hadn't changed in between.
    """
    files_dir = team_vault_root / "vault" / "files"
    crossed: list[dict] = []
    held_back: list[dict] = []

    if not files_dir.is_dir():
        return crossed, held_back

    for f in sorted(files_dir.glob("*.md")):
        refusal = path_safety_refusal(f, team_vault_root)
        if refusal is not None:
            # A path-escape/symlink/hardlink refusal is NOT a normal
            # held-back record (we cannot safely report even its uid/scope,
            # since we refused before reading it) — it is refused outright
            # and never contributes a row to either list. It is still
            # counted by the caller via the returned refusal reasons list
            # (see run_publish).
            continue

        content_bytes = read_file_atomically(f)
        fm_text = _split_frontmatter(content_bytes.decode("utf-8", errors="replace"))
        if fm_text is None:
            continue
        try:
            fm = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        uid = fm.get("uid")
        if not uid:
            continue

        raw_scope = fm.get("extraction_scope")
        normalized_scope = normalize_extraction_scope(raw_scope)
        rec = {"uid": uid, "extraction_scope": raw_scope, "path": f"vault/files/{f.name}"}
        segment = derive_segment(rec, team_vault_root)

        # AC3 (BOUNCE finding #4's concrete half): a record's OWN frontmatter
        # `segment:` field, if present, must AGREE with team_vault_uid — a
        # disagreement is the tamper signature, never silently resolved
        # either direction. See lib/segment.py's _boundary_violations_at_
        # one_commit for the fuller disclosure on what this does and does
        # not prove.
        claimed_segment = fm.get("segment")
        if claimed_segment is not None and str(claimed_segment) != str(team_vault_uid):
            raise PublishRefused(
                f"vault/files/{f.name} carries frontmatter segment={claimed_segment!r} which "
                f"DISAGREES with this team-vault's own uid {team_vault_uid!r} (AC3 mismatch) — "
                f"refusing the entire publish rather than silently picking a side"
            )

        scope_ok = is_public_scope(raw_scope)
        segment_ok = segment == team_vault_uid

        if scope_ok and segment_ok:
            content_sha256 = hashlib.sha256(content_bytes).hexdigest()
            crossed.append({
                "uid": uid,
                "path": f"vault/files/{f.name}",
                "content_bytes": content_bytes,
                "normalized_extraction_scope": normalized_scope,
                "derived_segment": segment,
                "content_sha256": content_sha256,
            })
        else:
            held_back.append({
                "uid": uid,
                "extraction_scope": raw_scope,
                "segment": segment,
            })

    return crossed, held_back


def collect_path_refusals(team_vault_root: Path) -> list[str]:
    """Separate pass purely to surface path-safety refusals as human-readable
    strings for the CLI/log — kept apart from enumerate_and_filter's return
    shape so that function's crossed/held_back lists never need to carry a
    third "refused" bucket with content we deliberately never read."""
    files_dir = team_vault_root / "vault" / "files"
    refusals: list[str] = []
    if not files_dir.is_dir():
        return refusals
    for f in sorted(files_dir.glob("*.md")):
        reason = path_safety_refusal(f, team_vault_root)
        if reason is not None:
            refusals.append(reason)
    return refusals


# ---------------------------------------------------------------------------
# Tree construction via an ISOLATED temporary index (never the repo's real
# index/working tree).
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path, env: Optional[dict] = None,
          input_bytes: Optional[bytes] = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, input=input_bytes, timeout=30, env=env,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        raise PublishRefused(f"git {' '.join(args)} failed: {stderr.strip()}")
    return result


def build_tree(team_vault_root: Path, crossed: list[dict]) -> str:
    """Builds a tree object containing exactly `crossed`'s files, using a
    temporary GIT_INDEX_FILE so the repo's real index/working tree is never
    touched (no `git add`, which could sweep in something untracked)."""
    fd, tmp_index_path = tempfile.mkstemp(prefix="tropo-publish-index-")
    os.close(fd)
    os.unlink(tmp_index_path)  # git treats a nonexistent index path as a fresh empty index

    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = tmp_index_path

    try:
        for item in crossed:
            # BOUNCE finding #3 (Argus A128, 2026-07-09): reuse the EXACT
            # bytes enumerate_and_filter already read (and hashed into
            # content_sha256) rather than re-opening the path here — a
            # second, separate read is exactly the TOCTOU window the
            # bounce found. `content_bytes` is required, not a fallback:
            # every real caller goes through enumerate_and_filter, which
            # always sets it; a caller that doesn't (only test fixtures
            # exercising build_tree directly) must supply it explicitly.
            blob_result = _git(
                ["hash-object", "-w", "--stdin"],
                cwd=team_vault_root,
                input_bytes=item["content_bytes"],
            )
            blob_hash = blob_result.stdout.decode("utf-8").strip()
            _git(
                ["update-index", "--add", "--cacheinfo", "100644", blob_hash, item["path"]],
                cwd=team_vault_root, env=env,
            )
        tree_result = _git(["write-tree"], cwd=team_vault_root, env=env)
        return tree_result.stdout.decode("utf-8").strip()
    finally:
        if os.path.exists(tmp_index_path):
            os.unlink(tmp_index_path)


def resolve_prior_team_tip(remote: str, branch: str) -> Optional[str]:
    """The parent for this publish: the REMOTE's actual current tip of
    `branch`, or None if the branch does not exist there yet (this IS the
    first publish — a true orphan root, per Ruling 5).

    BOUNCE finding #9 (Argus A128, 2026-07-09): a prior version read the
    LOCAL `refs/heads/<branch>` ref instead. A local ref can be ahead of
    (a previously-failed push left it dangling) or behind (another
    machine already published something this clone hasn't fetched) the
    remote's real state — basing the parent and no-op comparison on the
    remote's actual tip, via `git ls-remote`, is what makes this correct
    regardless of local ref drift. This function still never reaches into
    the studio's private repo for a parent — the entire ancestry
    guarantee — it just reads the correct SIDE of the team-vault's own
    remote instead of a possibly-stale local mirror of it."""
    result = subprocess.run(
        ["git", "ls-remote", remote, f"refs/heads/{branch}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.split()[0].strip()


def commit_tree(team_vault_root: Path, tree_hash: str, parent: Optional[str],
                 count: int, committer_name: str, committer_email: str) -> str:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = committer_name
    env["GIT_AUTHOR_EMAIL"] = committer_email
    env["GIT_COMMITTER_NAME"] = committer_name
    env["GIT_COMMITTER_EMAIL"] = committer_email
    message = COMMIT_MESSAGE_TEMPLATE.format(count=count)

    args = ["commit-tree", tree_hash, "-m", message]
    if parent:
        args.extend(["-p", parent])
    result = _git(args, cwd=team_vault_root, env=env)
    return result.stdout.decode("utf-8").strip()


# ---------------------------------------------------------------------------
# The full publish gesture.
# ---------------------------------------------------------------------------

def run_publish(
    team_vault_root: Path,
    remote: str,
    branch: str,
    apply: bool,
    committer_name: str,
    committer_email: str,
    expect_vault_uid: Optional[str] = None,
) -> dict:
    """Runs the full publish gesture. Returns the receipt dict. Raises
    PublishRefused (never a bare exception) on any refusal — nothing is
    written or pushed in that case."""

    team_vault_uid = read_vault_manifest_uid(team_vault_root)
    if not team_vault_uid:
        raise PublishRefused(
            f"no resolvable vault-manifest uid at {team_vault_root}/.tropo/vault-manifest.md — "
            f"tropo-publish.py refuses to operate without a durable, authored vault identity to "
            f"positively match segment against (Ruling 3)"
        )

    # BOUNCE finding #5 "FOREIGN-VAULT-UID-CLAIM" (Argus A128, 2026-07-09):
    # nothing previously stopped a foreign vault whose manifest simply
    # DECLARES vault_uid == the victim team's UID from publishing to the
    # victim's remote. --expect-vault-uid is an AUTHENTICATED expectation
    # supplied by the caller (a human, or the compose.lock record for this
    # remote) — independent of anything read from team_vault_root itself.
    if expect_vault_uid is not None and team_vault_uid != expect_vault_uid:
        raise PublishRefused(
            f"manifest at {team_vault_root} declares vault_uid {team_vault_uid!r}, which does NOT "
            f"match --expect-vault-uid {expect_vault_uid!r} — refusing (foreign-vault-uid-claim defense)"
        )

    if not (team_vault_root / ".git").is_dir():
        raise PublishRefused(f"{team_vault_root} is not a git repository — cannot commit/push from here")

    submodule_err = check_no_submodules(team_vault_root)
    if submodule_err:
        raise PublishRefused(submodule_err)

    worktree_err = check_single_worktree(team_vault_root)
    if worktree_err:
        raise PublishRefused(worktree_err)

    reflog_ok, reflog_detail = check_reflog_disabled(remote)
    if not reflog_ok:
        raise PublishRefused(reflog_detail)

    path_refusals = collect_path_refusals(team_vault_root)
    crossed, held_back = enumerate_and_filter(team_vault_root, team_vault_uid)

    receipt: dict[str, Any] = {
        "team_vault_uid": team_vault_uid,
        "team_vault_root": str(team_vault_root),
        "remote": remote,
        "branch": branch,
        "crossed": [
            {k: v for k, v in item.items() if k != "content_bytes"}
            for item in crossed
        ],
        "held_back_count": len(held_back),
        "held_back": held_back,
        "path_refusals": path_refusals,
        "environment_assertions": {
            "no_submodules": True,
            "single_worktree": True,
            "reflog": reflog_detail,
        },
        "applied": False,
    }

    if not crossed:
        receipt["ancestry_proof"] = None
        receipt["new_commit"] = None
        receipt["note"] = "no files cleared the two-gate filter — nothing to publish this run"
        return receipt

    if not apply:
        receipt["note"] = "dry-run — no objects written, nothing pushed (pass --apply to execute)"
        return receipt

    tree_hash = build_tree(team_vault_root, crossed)
    # BOUNCE finding #9 (Argus A128, 2026-07-09): parent + no-op comparison
    # are now based on the REMOTE's actual tip (git ls-remote), never a
    # local ref — see resolve_prior_team_tip's docstring.
    parent = resolve_prior_team_tip(remote, branch)

    # AC1 (44badb55): "identical published state => identical composed
    # result... a second no-change sync is a no-op." Compare the freshly
    # built tree against the REMOTE's CURRENT tip's own tree — if
    # identical, the crossed set is byte-for-byte the same as what's
    # already published; committing again would be a wasted,
    # indistinguishable-content commit accumulating in public history for
    # zero actual change. Skip the commit/push entirely and report it as a
    # no-op rather than silently creating one anyway.
    if parent is not None:
        parent_tree_result = _git(["rev-parse", f"{parent}^{{tree}}"], cwd=team_vault_root)
        parent_tree = parent_tree_result.stdout.decode("utf-8").strip()
        if parent_tree == tree_hash:
            receipt["ancestry_proof"] = None
            receipt["new_commit"] = None
            receipt["parent"] = parent
            receipt["note"] = (
                f"no-op — the current public tree is byte-identical to team-branch tip "
                f"{parent[:12]}; nothing to commit or push (AC1: identical state => no-op)"
            )
            return receipt

    new_commit = commit_tree(team_vault_root, tree_hash, parent, len(crossed), committer_name, committer_email)

    ancestry_holds, ancestry_detail = verify_clean_ancestry(team_vault_root, new_commit)
    if not ancestry_holds:
        raise PublishRefused(
            f"ancestry verification FAILED after construction — refusing to push a commit whose own "
            f"history does not prove clean: {ancestry_detail}"
        )

    # BOUNCE finding #3 "committed-tree re-validation NOT RUN" (Argus A128,
    # 2026-07-09): re-read the ACTUAL committed bytes (via git show, inside
    # find_boundary_violations_in_committed_tree — never the working tree)
    # and re-run the two-gate boundary over EVERY commit reachable from the
    # new commit (closing finding #2 "ancestry poisoning" on this side too
    # — a poisoned prior tip inherited via `parent` is caught here, before
    # push, not just by B after the fact). This is the SAME check the
    # validator and the pull-side mount enforcement run — one
    # implementation, checked on both sides of the wire.
    tree_violations = find_boundary_violations_in_committed_tree(team_vault_root, team_vault_uid, new_commit)
    if tree_violations:
        raise PublishRefused(
            f"committed-tree re-validation FAILED after construction — refusing to push "
            f"({len(tree_violations)} violation(s)): " + "; ".join(tree_violations)
        )

    # BOUNCE finding #9 (Argus A128, 2026-07-09): push the constructed
    # commit object DIRECTLY to the remote ref — no local `update-ref`
    # step at all, so there is nothing to roll back if the push fails and
    # no local ref that can drift ahead of what the remote actually has.
    push_result = _git(["push", remote, f"{new_commit}:refs/heads/{branch}"], cwd=team_vault_root)

    receipt["applied"] = True
    receipt["new_commit"] = new_commit
    receipt["parent"] = parent
    receipt["ancestry_proof"] = {"holds": ancestry_holds, "detail": ancestry_detail}
    receipt["push_output"] = push_result.stderr.decode("utf-8", errors="replace").strip()
    return receipt


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="tropo-publish.py",
        description=(
            "Orphan-commit public-only publisher for a mounted team vault "
            "(dev-spec 44badb55, ADR-051). Never operates on the studio's "
            "private repo."
        ),
    )
    parser.add_argument("--team-vault-root", required=True, type=Path,
                         help="path to the team vault's OWN repo root (must contain .tropo/vault-manifest.md)")
    parser.add_argument("--remote", required=True,
                         help="git remote (URL or local path) to push the team branch to")
    parser.add_argument("--branch", default=TEAM_BRANCH_DEFAULT,
                         help=f"team branch name (default: {TEAM_BRANCH_DEFAULT})")
    parser.add_argument("--apply", action="store_true",
                         help="actually write objects + push; default is a dry-run preview")
    parser.add_argument("--receipt-out", type=Path, default=None,
                         help="write the receipt JSON here (default: print to stdout)")
    parser.add_argument("--committer-name", default=FEDERATION_COMMITTER_NAME,
                         help=argparse.SUPPRESS)  # testing override only
    parser.add_argument("--committer-email", default=FEDERATION_COMMITTER_EMAIL,
                         help=argparse.SUPPRESS)  # testing override only
    parser.add_argument("--expect-vault-uid", default=None,
                         help="refuse unless --team-vault-root's own manifest uid equals this "
                              "(BOUNCE finding #5 defense: an authenticated expectation for which "
                              "vault you believe you're publishing, independent of what the "
                              "manifest itself claims — pass the compose.lock-recorded uid for "
                              "this remote when available)")
    args = parser.parse_args()

    team_vault_root = args.team_vault_root.resolve()
    if not team_vault_root.is_dir():
        print(f"[FAIL] --team-vault-root {team_vault_root} does not exist or is not a directory")
        return 2

    try:
        receipt = run_publish(
            team_vault_root=team_vault_root,
            remote=args.remote,
            branch=args.branch,
            apply=args.apply,
            committer_name=args.committer_name,
            committer_email=args.committer_email,
            expect_vault_uid=args.expect_vault_uid,
        )
    except PublishRefused as e:
        print(f"[REFUSED] {e}")
        return 1

    receipt_json = json.dumps(receipt, indent=2, sort_keys=True, default=str)
    if args.receipt_out:
        args.receipt_out.write_text(receipt_json + "\n", encoding="utf-8")
        print(f"[RECEIPT] written to {args.receipt_out}")
    else:
        print(receipt_json)

    mode = "APPLIED" if receipt.get("applied") else "DRY-RUN"
    print(
        f"[{mode}] {len(receipt['crossed'])} file(s) crossed, "
        f"{receipt['held_back_count']} held back, "
        f"{len(receipt['path_refusals'])} path-safety refusal(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
