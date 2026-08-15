#!/usr/bin/env python3
"""tropo-publish-scope-gate.py — hard scope gate for the tropo-app publish split.

STATUS: RATIFIED 2026-07-19. Mike Maziarz gave the explicit GO ("I ratify the
scope gate", 2026-07-19); signed by Argus A135, Chief Architect + owner of the
publish boundary (dev-spec f47da329; declaration ed10a8be; conformance test-spec
498e88fc, G1-G8 green). A clean result from this gate — run against the pinned
source commit and grounded in the app-ship declaration — now AUTHORIZES the
tropo-app publish split. Any violation still fails closed (DO NOT PUBLISH).

WHY THIS EXISTS
---------------
argo-os is the PRIVATE studio: crew souls, strategy, the argo-private vault, the
events plane. tropo-app/ is the PUBLIC L2 application, now living inside that
private repo so one studio and one events plane cover both layers.

That inversion makes the release path a hard security boundary. Publishing runs
`git subtree split --prefix=tropo-app` and pushes the result to the public
tropo-app repo. This gate stands between the split and that push, and it
FAILS CLOSED: any doubt is a refusal, never a warning.

GROUNDED IN A GOVERNED DECLARATION (F1 — dev-spec f47da329)
-----------------------------------------------------------
The gate no longer carries hardcoded, floating denylists (the A134 ruling: a
floating denylist is convenience, and convenience is not isolation — miss one
entry and it leaks). It derives ALL of its authorization rules from the governed
app-ship declaration `.tropo/app-ship.manifest.md` (UID ed10a8be), a top-down,
un-forgeable studio-tier declaration that lives ABOVE the shipped subtree (in
`.tropo/`, never inside `tropo-app/`). If that declaration is missing or corrupt
the gate FAILS CLOSED — no declaration means no authorization, never a fallback
allow.

The five fixes this rewire lands (f47da329 F1–F5):
  F1  ground in the declaration    — scope/holes/modes/extensions/markers all
                                      derive from ed10a8be; missing/corrupt →
                                      fail closed ("no app-ship declaration").
  F2  enforce deny_holes           — refuse any split path matching a governed
                                      deny-hole glob (playbook-runs/**, vault/**,
                                      **/.tropo-studio/**, **/agent-memory.md …).
  F3  pin the commit               — split + cross-check against an explicit
                                      --source-commit, NOT a floating HEAD; the
                                      split file set must equal tropo-app/ AT the
                                      pinned commit.
  F4  refuse gitlinks              — refuse ls-tree mode 160000 (submodule /
                                      gitlink) in addition to 120000 (symlink).
  F5  scan .jsonl / .ndjson        — the content-scan extension set is the
                                      declaration's private_content_extensions,
                                      which now includes .jsonl/.ndjson (the
                                      run-log / event-row leak the old scan
                                      missed).
  F6  secret-shaped basenames      — refuse a basename matching the
      (allowlist-exempt)             declaration's secret_filename_patterns
                                      (.env, .env.*, credentials, credentials.*)
                                      UNLESS its exact basename is in
                                      secret_allowlist. This is the ONE check
                                      that yields to the allowlist (deny_holes
                                      never do), so .env.local / credentials are
                                      refused while .env.example ships. Restores
                                      the env/credential coverage the original
                                      hardcoded SECRET_PATTERNS carried.

BOUNDARY SEPARATION (do NOT merge code paths — f47da329 §Scope boundary / G7)
-----------------------------------------------------------------------------
This is the app-subtree split authorization path. It deliberately shares NO code
with the vault-record FEDERATION boundary (44badb55 / vault/tools/lib/segment.py),
which authorizes governed markdown vault entries by extraction_scope + derived
vault-node segment. The two paths authorize different classes of thing and stay
separate (A134 ruling). This file MUST NOT import lib/segment.py's federation
two-gate filter.
"""
import argparse
import fnmatch
import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


def _load_tropo_roots():
    """Load the production-owned roots module outside either ``lib`` package."""
    roots_path = Path(__file__).resolve().with_name("lib") / "tropo_roots.py"
    spec = importlib.util.spec_from_file_location("_tropo_tools_roots", roots_path)
    if spec is None or spec.loader is None:
        raise ImportError("tropo_roots helper could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tropo_roots = _load_tropo_roots()

# ---------------------------------------------------------------------------
# The declaration lives here — ABOVE the shipped subtree, in the private
# studio-governance layer, so it cannot be forged from inside tropo-app/.
# ---------------------------------------------------------------------------
MANIFEST_REL = Path(".tropo") / "app-ship.manifest.md"
MANIFEST_UID = "ed10a8be"

# Exit codes (all non-zero = DO NOT PUBLISH):
EXIT_CLEAN = 0        # no violation found (RATIFIED 2026-07-19 — authorizes publish)
EXIT_VIOLATION = 2    # one or more violations — fail closed
EXIT_NO_DECLARATION = 3  # missing/corrupt manifest, or a required pin absent (F1/F3)

# git tree modes, for human-readable refusal reasons (F4). The refused SET comes
# from the declaration (refused_git_modes); these labels are only presentation.
_MODE_LABEL = {
    "120000": "SYMLINK (may resolve outside the subtree)",
    "160000": "GITLINK/SUBMODULE (ancestry + leak surface)",
}

# REVIEW tier — ADVISORY ONLY, never fails the gate, so it is NOT an
# authorization rule (F1 governs what REFUSES; this only informs a reviewer).
# The app legitimately resolves vault content, so it names the vault node and
# the event types it reads; flagging those as leaks was a historical false
# positive (lib/studio-events.ts, lib/kb.ts). Reported for human eyes only.
CONTENT_REVIEW = (
    "argo-private",
    "§Soul",
    "agent-memory.md",
)


class ScopeGateFailClosed(Exception):
    """A fail-closed refusal raised BEFORE any per-path scan can run — a missing
    or corrupt declaration, or a required pin that was not supplied. Distinct
    from per-path violations so the caller can emit the right exit code."""


# ===========================================================================
# F1 — the governed declaration
# ===========================================================================

@dataclass(frozen=True)
class Manifest:
    """The parsed, compiled app-ship declaration. Every field the gate enforces
    comes from here — there is no hardcoded authorization fallback."""
    prefix: str
    deny_holes: tuple[tuple[str, re.Pattern], ...]   # (glob, compiled) — F2
    refused_modes: frozenset[str]                    # F4
    secret_allowlist: frozenset[str]                 # declared shippable exceptions
    secret_filename_patterns: tuple[str, ...]        # F6 (allowlist-exempt)
    content_extensions: tuple[str, ...]              # F5
    content_markers_hard: tuple[str, ...]            # hard-refusal markers
    pinned_commit_required: bool                     # F3

    def deny_hole_hit(self, path: str) -> Optional[str]:
        """Return the matched deny-hole glob for `path`, or None. (F2) Deny-holes
        are UNCONDITIONAL — never yield to the allowlist."""
        for glob, pattern in self.deny_holes:
            if pattern.match(path):
                return glob
        return None

    def is_allowlisted(self, path: str) -> bool:
        """A file whose basename is a declared shippable exception
        (secret_allowlist, e.g. .env.example). Exempt from the content scan
        and, unlike deny-holes, from the F6 secret-filename check."""
        return path.rsplit("/", 1)[-1] in self.secret_allowlist

    def secret_filename_hit(self, path: str) -> Optional[str]:
        """F6: return the matched secret-filename glob for `path`'s BASENAME, or
        None. ALLOWLIST-EXEMPT — a basename whose exact string is in
        secret_allowlist is never a hit (this is the key difference from the
        unconditional deny-holes). Matched case-sensitively against the basename
        only, so `.env.local`/`credentials` are refused while `.env.example`
        ships and a legit `credentials-helper.ts` is untouched."""
        base = path.rsplit("/", 1)[-1]
        if base in self.secret_allowlist:
            return None
        for pat in self.secret_filename_patterns:
            if fnmatch.fnmatchcase(base, pat):
                return pat
        return None

    def scanned_extension(self, path: str) -> bool:
        """True when `path`'s extension is in the declaration's content-scan set
        (F5 — includes .jsonl/.ndjson)."""
        return any(path.endswith(ext) for ext in self.content_extensions)

    def mode_refused(self, mode: str) -> bool:
        return mode in self.refused_modes


def _split_frontmatter(text: str) -> Optional[str]:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    return text[4:end]


def _glob_to_regex(glob: str) -> re.Pattern:
    """Translate a gitignore-style glob into an anchored regex.

      **/   → zero or more leading path segments  (matches in any directory)
      /**   → everything below                    (trailing)
      **    → any run of characters incl. '/'
      *     → any run within a single segment      (never crosses '/')
      ?     → one non-'/' character

    So `agents/**` is ANCHORED at the split root (it matches `agents/x`, NOT
    `app/api/agents/x` — the historical false-positive that flagged eight
    legitimate Next.js routes), while `**/.tropo-studio/**` matches at any depth.
    """
    out: list[str] = ["^"]
    i, n = 0, len(glob)
    while i < n:
        c = glob[i]
        if c == "*":
            if i + 1 < n and glob[i + 1] == "*":
                i += 2
                if i < n and glob[i] == "/":
                    out.append("(?:.*/)?")  # '**/' — zero or more segments
                    i += 1
                else:
                    out.append(".*")         # '**' — any run incl. '/'
            else:
                out.append("[^/]*")           # '*' — within one segment
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    out.append("$")
    return re.compile("".join(out))


def load_manifest(root: Path) -> Manifest:
    """Load + compile the app-ship declaration (F1). FAIL CLOSED on anything
    that is not a well-formed, default-deny app-ship manifest — a missing file,
    unparseable frontmatter, the wrong kind, a non-deny default, or a missing
    required field. NEVER returns a hardcoded fallback allow.
    """
    manifest_path = root / MANIFEST_REL
    if not manifest_path.is_file():
        raise ScopeGateFailClosed(
            f"no app-ship declaration: {MANIFEST_REL} is missing — the gate "
            f"refuses to authorize any split without its governing declaration "
            f"({MANIFEST_UID}). No declaration means no authorization."
        )
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScopeGateFailClosed(
            f"no app-ship declaration: cannot read {MANIFEST_REL}: {exc}"
        ) from exc

    fm_text = _split_frontmatter(text)
    if fm_text is None:
        raise ScopeGateFailClosed(
            f"no app-ship declaration: {MANIFEST_REL} has no parseable "
            f"frontmatter (corrupt manifest → fail closed)."
        )
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        raise ScopeGateFailClosed(
            f"no app-ship declaration: {MANIFEST_REL} frontmatter is not valid "
            f"YAML (corrupt manifest → fail closed): {exc}"
        ) from exc
    if not isinstance(fm, dict):
        raise ScopeGateFailClosed(
            f"no app-ship declaration: {MANIFEST_REL} frontmatter is not a "
            f"mapping (corrupt manifest → fail closed)."
        )

    if fm.get("kind") != "app-ship-manifest":
        raise ScopeGateFailClosed(
            f"no app-ship declaration: {MANIFEST_REL} kind is "
            f"{fm.get('kind')!r}, not 'app-ship-manifest' (fail closed)."
        )
    if str(fm.get("default", "")).lower() != "deny":
        raise ScopeGateFailClosed(
            f"no app-ship declaration: {MANIFEST_REL} is not default-deny "
            f"(default={fm.get('default')!r}) — a non-deny declaration cannot "
            f"authorize a split (fail closed)."
        )

    prefix = fm.get("app_ship_prefix")
    if not isinstance(prefix, str) or not prefix.strip():
        raise ScopeGateFailClosed(
            f"no app-ship declaration: {MANIFEST_REL} missing app_ship_prefix."
        )
    prefix = prefix.strip().rstrip("/")

    deny_globs = fm.get("deny_holes") or []
    if not isinstance(deny_globs, list):
        raise ScopeGateFailClosed(
            f"no app-ship declaration: deny_holes must be a list."
        )
    deny_holes = tuple((str(g), _glob_to_regex(str(g))) for g in deny_globs)

    refused_modes = fm.get("refused_git_modes") or []
    if not isinstance(refused_modes, list):
        raise ScopeGateFailClosed(
            f"no app-ship declaration: refused_git_modes must be a list."
        )
    # YAML may parse bare 120000 as int; normalize every mode to a string.
    refused = frozenset(str(m).strip() for m in refused_modes)

    allowlist = fm.get("secret_allowlist") or []
    secret_allowlist = frozenset(str(a) for a in allowlist) if isinstance(allowlist, list) else frozenset()

    # F6 — secret-shaped basename patterns (env/credential), allowlist-exempt.
    # Required + list-typed; an absent or malformed field is fail-closed,
    # consistent with F1 (no silent gap in secret-file coverage).
    if "secret_filename_patterns" not in fm:
        raise ScopeGateFailClosed(
            f"no app-ship declaration: {MANIFEST_REL} is missing "
            f"secret_filename_patterns (F6 — required; an absent field is "
            f"fail-closed, consistent with F1)."
        )
    sfp = fm.get("secret_filename_patterns")
    if not isinstance(sfp, list):
        raise ScopeGateFailClosed(
            f"no app-ship declaration: secret_filename_patterns must be a list "
            f"(F6, fail closed)."
        )
    secret_filename_patterns = tuple(str(x) for x in sfp)

    extensions = fm.get("private_content_extensions") or []
    if not isinstance(extensions, list) or not extensions:
        raise ScopeGateFailClosed(
            f"no app-ship declaration: private_content_extensions must be a "
            f"non-empty list (F5 content scan cannot run without it)."
        )
    content_extensions = tuple(str(e) for e in extensions)

    markers = fm.get("private_content_markers_hard") or []
    if not isinstance(markers, list):
        raise ScopeGateFailClosed(
            f"no app-ship declaration: private_content_markers_hard must be a list."
        )
    content_markers_hard = tuple(str(m) for m in markers)

    pinned_commit_required = bool(fm.get("pinned_commit_required", False))

    return Manifest(
        prefix=prefix,
        deny_holes=deny_holes,
        refused_modes=refused,
        secret_allowlist=secret_allowlist,
        secret_filename_patterns=secret_filename_patterns,
        content_extensions=content_extensions,
        content_markers_hard=content_markers_hard,
        pinned_commit_required=pinned_commit_required,
    )


# ===========================================================================
# git plumbing
# ===========================================================================

def run(args: list[str], cwd: Path) -> str:
    out = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(
            f"FAIL: command errored: {' '.join(args)}\n{out.stderr.strip()}"
        )
    return out.stdout


@dataclass
class TreeEntry:
    mode: str
    path: str


def enumerate_tree(root: Path, ref: str) -> list[TreeEntry]:
    """Every (mode, path) in a tree ref, recursively."""
    entries: list[TreeEntry] = []
    for line in run(["git", "ls-tree", "-r", ref], root).splitlines():
        if not line.strip():
            continue
        meta, _, path = line.partition("\t")
        mode = meta.split()[0]
        entries.append(TreeEntry(mode=mode, path=path))
    return entries


def prefix_pathset_at_commit(root: Path, commit: str, prefix: str) -> set[str]:
    """The prefix-relative file set of `prefix/` AT a specific commit (F3 — the
    PINNED commit, never a floating HEAD)."""
    listing = run(
        ["git", "ls-tree", "-r", "--name-only", commit, f"{prefix}/"], root
    )
    head = f"{prefix}/"
    return {p[len(head):] for p in listing.splitlines() if p.startswith(head)}


# ===========================================================================
# The scan — all rules derive from the Manifest (F1)
# ===========================================================================

@dataclass
class GateResult:
    exit_code: int
    violations: list[str] = field(default_factory=list)
    review: list[str] = field(default_factory=list)
    split_ref: Optional[str] = None
    file_count: int = 0
    source_commit: Optional[str] = None
    banner: bool = False


def scan_split(
    root: Path,
    manifest: Manifest,
    split_ref: str,
    source_commit: str,
) -> GateResult:
    """Run F2/F4/F5 over the split tree + F3 cross-check against the pinned
    commit. Pure w.r.t. the manifest — every refusal traces to a declared rule.
    """
    entries = enumerate_tree(root, split_ref)
    paths = [e.path for e in entries]
    violations: list[str] = []
    review: list[str] = []

    # F4 — refused git modes (symlinks 120000, gitlinks 160000, …).
    for e in entries:
        if manifest.mode_refused(e.mode):
            label = _MODE_LABEL.get(e.mode, f"mode {e.mode}")
            violations.append(f"REFUSED GIT MODE {e.mode} — {label} in split: {e.path}")

    # F2 — governed deny-holes (unconditional; never yield to the allowlist).
    for p in paths:
        glob = manifest.deny_hole_hit(p)
        if glob is not None:
            violations.append(f"DENY-HOLE '{glob}' matched in split: {p}")

    # F6 — secret-shaped basenames (env/credential), ALLOWLIST-EXEMPT: refused
    # unless the exact basename is a declared shippable exception. So
    # .env.local / .env.production / credentials are refused while
    # .env.example / .env.sample / .env.template ship.
    for p in paths:
        pat = manifest.secret_filename_hit(p)
        if pat is not None:
            violations.append(
                f"SECRET-SHAPED FILENAME '{pat}' in split (not in secret_allowlist): {p}"
            )

    # F3 — cross-check the split file set against the PINNED source commit
    # (never a floating HEAD). The split of `prefix/` at `source_commit` must
    # equal that commit's `prefix/` file set exactly.
    pinned_set = prefix_pathset_at_commit(root, source_commit, manifest.prefix)
    split_set = set(paths)
    injected = split_set - pinned_set
    for p in sorted(injected)[:20]:
        violations.append(
            f"INJECTED PATH (in split, not under {manifest.prefix}/ at pinned "
            f"commit {source_commit[:12]}): {p}"
        )
    dropped = pinned_set - split_set
    for p in sorted(dropped)[:20]:
        violations.append(
            f"SPLIT/PIN MISMATCH (under {manifest.prefix}/ at pinned commit "
            f"{source_commit[:12]} but absent from split): {p}"
        )

    # F5 — content scan over declared extensions (now incl. .jsonl/.ndjson).
    for p in paths:
        if not manifest.scanned_extension(p):
            continue
        if manifest.is_allowlisted(p):
            continue  # declared shippable exception (e.g. .env.example)
        try:
            blob = run(["git", "show", f"{split_ref}:{p}"], root)
        except SystemExit:
            continue
        for marker in manifest.content_markers_hard:
            if marker in blob:
                violations.append(f"PRIVATE CREW DATA '{marker}' in split file: {p}")
                break
        else:
            for marker in CONTENT_REVIEW:
                if marker in blob:
                    review.append(f"{p} (mentions '{marker}')")
                    break

    exit_code = EXIT_VIOLATION if violations else EXIT_CLEAN
    return GateResult(
        exit_code=exit_code,
        violations=violations,
        review=review,
        split_ref=split_ref,
        file_count=len(paths),
        source_commit=source_commit,
        banner=(exit_code == EXIT_CLEAN),
    )


def run_gate(root: Path, source_commit: Optional[str]) -> GateResult:
    """Full gate: load the declaration (F1), resolve the pinned commit (F3),
    split from it, and scan. Fail-closed refusals surface as GateResult with a
    non-zero exit_code — never an exception past this boundary."""
    try:
        manifest = load_manifest(root)
    except ScopeGateFailClosed as exc:
        return GateResult(exit_code=EXIT_NO_DECLARATION, violations=[str(exc)])

    # F3 — a floating HEAD is never authorized when the declaration requires a pin.
    if manifest.pinned_commit_required and not source_commit:
        return GateResult(
            exit_code=EXIT_NO_DECLARATION,
            violations=[
                "pinned source commit required by the declaration "
                "(pinned_commit_required: true) but none supplied — pass "
                "--source-commit <sha>. A floating HEAD is not the pinned "
                "changeset commit (F3, fail closed)."
            ],
        )

    ref = source_commit or "HEAD"
    # Resolve to a concrete sha so the split + the cross-check pin to the SAME
    # commit even if the ref is symbolic.
    resolved = run(["git", "rev-parse", ref], root).strip()

    split_ref = run(
        ["git", "subtree", "split", f"--prefix={manifest.prefix}", resolved], root
    ).strip()
    if not split_ref:
        return GateResult(
            exit_code=EXIT_VIOLATION,
            violations=[f"subtree split of {manifest.prefix}/ at {resolved[:12]} produced no ref"],
        )

    return scan_split(root, manifest, split_ref, resolved)


# ===========================================================================
# CLI
# ===========================================================================

def _print_report(root: Path, result: GateResult) -> None:
    if result.split_ref:
        print(f"[scope-gate] split ref: {result.split_ref}")
        print(f"[scope-gate] split contains {result.file_count} files "
              f"(pinned commit {(result.source_commit or '')[:12]})")

    if result.review:
        print(f"\n[scope-gate] REVIEW ({len(result.review)}) — legitimate identifier "
              f"mentions, not failures:")
        for r in result.review[:15]:
            print(f"  · {r}")
        if len(result.review) > 15:
            print(f"  … and {len(result.review) - 15} more")

    print()
    if result.exit_code == EXIT_NO_DECLARATION:
        print("[scope-gate] ✗ FAIL-CLOSED — no usable app-ship declaration.")
        for v in result.violations:
            print(f"  - {v}")
        return
    if result.violations:
        print(f"[scope-gate] ✗ REFUSED — {len(result.violations)} violation(s). DO NOT PUBLISH.")
        for v in result.violations[:50]:
            print(f"  - {v}")
        if len(result.violations) > 50:
            print(f"  … and {len(result.violations) - 50} more")
        return

    print(f"[scope-gate] ✓ no violation found in the split (grounded in {MANIFEST_UID}).")
    _print_ratified_banner()


def _print_ratified_banner() -> None:
    """The RATIFIED banner — Mike gave the explicit GO 2026-07-19; signed by
    Argus A135 against declaration ed10a8be + dev-spec f47da329 (conformance
    498e88fc, G1-G8 green). A clean result AUTHORIZES the tropo-app publish
    split. Fail-closed on any violation is unchanged."""
    print("[scope-gate] ─────────────────────────────────────────────────────────")
    print("[scope-gate] RATIFIED 2026-07-19 (Mike GO; signed Argus A135). A clean")
    print("[scope-gate] result against the pinned commit + app-ship declaration")
    print("[scope-gate] AUTHORIZES the tropo-app publish split. Any violation still")
    print("[scope-gate] fails closed.")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hard, declaration-grounded scope gate for the tropo-app publish split."
    )
    parser.add_argument(
        "--source-commit",
        help="The PINNED source commit (sha or ref) to split + cross-check "
             "against (F3). Required when the declaration sets "
             "pinned_commit_required.",
    )
    parser.add_argument(
        "--root",
        help="Repo root to operate on (defaults to the argo-os studio root "
             "containing this tool). The declaration is read from "
             "<root>/.tropo/app-ship.manifest.md.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve() if args.root else tropo_roots.STUDIO_ROOT

    print(f"[scope-gate] grounding in declaration {MANIFEST_REL} ({MANIFEST_UID})…")
    result = run_gate(root, args.source_commit)
    _print_report(root, result)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
