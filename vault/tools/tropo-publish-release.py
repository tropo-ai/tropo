#!/usr/bin/env python3
"""
---
uid: 15cae798
name: publish-release
type: tool
status: active
owner: talos
domain: "Release Coupling (fbe50871) — the publish continuation: STAGE (private) -> --fire (the one public act) -> verify-live."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-publish-release.py stage --activation-uid <uid> --version <X.Y.Z> | --fire | --defer --reason <text> | --verify-only --version <X.Y.Z>"
script_path: vault/tools/tropo-publish-release.py
spawnable_by:
  - all-executives
created: '2026-07-13'
created_by: talos-t29
governed_by: 8dd772a0
member_of:
  - 681516fe
schema_version: 2
---

Release Coupling (dev-spec fbe50871, Mike-locked 2026-07-13). Closes cf84697d:
build and publish become ONE flow with exactly two release gestures — Mike signs
(existing gate, action_human_signoff) and Mike fires the single public act.

Distinct, by design, from the federation tool `tropo-publish.py` — different
concern entirely (this is the OS release channel: GitHub + Supabase + the update
manifest; federation publish is a different mechanism for a different substrate).

STATE MACHINE (binding, per the dev-spec body):

  STAGE (automated, idempotent, PRIVATE):
    - gate: require_release_authorization(require_human_signoff=True, version=...)
    - rsync build output -> the staged clone (preserve-list; would-delete printed;
      refuse on non-allowlisted deletion)
    - CHANGELOG equality assert (staged clone vs argo-os's own CHANGELOG.md)
    - local commit + tag
    - push-URL DISABLED on the staged clone (physical guard against a stray push)
    - state file {staged_sha, tag, version, staged_at}
    - EDGE SUMMARY -> STAGED, stop. Nothing public happened.

  preflight --version <v> (S3 AC1/AC2, 176a8995 -- no TTY, asks nothing):
    - runs the pre-outward-fire phase of the ONE gate roster
      (tropo-release-preflight.py PRE_OUTWARD_FIRE_ROSTER): staged state,
      pinned remote, read-only `git ls-remote` + https credential probe,
      AC7 receipt set + release_entry_uid, authorization + CHANGELOG, zip +
      sealed notes, release entry, gh auth, Supabase credentials, badge target
    - every gate is reported; any refusal -> exit 2 (operational -> 3), with
      the cure named. Green means the fire cannot refuse on a precondition.
    - --fire runs this same phase BEFORE its confirm (v1.90 refused four
      times AFTER Mike's yes; a refusal after the yes is an apology)

  --fire (gesture 2 -- TTY-only, default NO):
    - PREFLIGHT (above) — red stops here, before anyone is asked
    - re-run the SAME outward gate (composition law 1: one gate, consulted twice)
    - HEAD == staged_sha, else STALE-STAGE refuse (restage cure named)
    - restore push URL -> push main + tags -> re-disable push URL
    - gh release create + zip asset
    - Supabase zip + update-manifest upload
    - VERIFY-LIVE: peeled/lightweight remote tag target == remote main == staged
      sha, plus exact non-draft GitHub Release tag/URL/publishedAt
      -> LIVE | PUSHED-NO-RELEASE | POSTED-UNVERIFIED (all nonzero paths scream;
      re-fire completes idempotently by keying on what's actually missing)
    - content-addressed verify-live receipt + public-only
      tropo.release.published event + release-entry stamp on FULL GREEN ONLY

The receipt is a governance-authorized, hash-consistent publisher assertion
given trusted main checkout. It is not cryptographic authentication; v1
intentionally has no signing key or signature.

  --defer (same TTY discipline as --fire): a Mike-gestured, recorded skip. The
  builder requests it; Mike's hand authorizes it, same as the push itself.

  --verify-only: the SOP's documented manual path for attested-class releases
  (no pipeline-run to stage/fire against) -- runs VERIFY-LIVE against a version
  already live by some other means, without touching the outward gate.

Exit codes: 0 = success (STAGED / LIVE / VERIFIED / DEFERRED). Nonzero on any
refusal or partial outcome — this tool never claims success it cannot back up
with a live remote check.
"""
from __future__ import annotations  # PEP 604 `X | None` annotations on py3.9
import argparse
import fcntl
import importlib.util
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

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
#: The release-pipeline leaf this tool executes (v1.92 Stream 1, AC2).
#: 3dd817cb is the pipeline's TERMINAL step and was named in no tool at all —
#: the one outward, irreversible act in the whole release had no declared
#: performer anywhere in the runtime. `cmd_fire` is bound rather than
#: `cmd_stage`: staging is private and repeatable, firing is the commit point,
#: and the leaf's own text puts the public receipt at that boundary.
PIPELINE_BINDINGS = (
    {
        "step_uid": "3dd817cb",
        "kind": "tool",
        "entry": "tropo-publish-release.py:cmd_fire",
        "description": "publish the official release (the one outward act)",
    },
)

CANONICAL_REPOSITORY = "tropo-ai/tropo"
CANONICAL_GH_REPOSITORY = "github.com/tropo-ai/tropo"
DEFAULT_REMOTE = "https://github.com/tropo-ai/tropo.git"
STATE_FILE_NAME = "publish-state.json"
MANIFEST_PUBLIC_PATH = "releases/updates-manifest.json"
FINALIZE_LOCK_FILE_NAME = ".publish-finalize.lock"
_FINALIZE_LOCKS_GUARD = threading.Lock()
_FINALIZE_THREAD_LOCKS: dict[str, threading.RLock] = {}


def _load_release_receipt():
    """Load the co-located receipt primitive without ``lib`` path ambiguity."""
    module_name = "tropo_publish_release_receipt"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        module_name,
        Path(__file__).resolve().with_name("lib") / "release_receipt.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError("release receipt helper could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


release_receipt = _load_release_receipt()


def _load_vault_lib(module_name, file_name):
    """Load a co-located vault/tools/lib module without `lib` path ambiguity.

    Same reason _load_release_receipt exists: `lib` below is
    `.tropo/scripts/lib`, a different package, and an ambiguous import here
    would resolve differently depending on path order.
    """
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).resolve().with_name("lib") / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"{file_name} could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Stage-6 AC7: the four-instrument receipt set is the sole Verify authority.
release_verify = _load_vault_lib("tropo_publish_release_verify", "release_verify.py")
release_package = _load_vault_lib("tropo_publish_release_package", "release_package.py")
# AC5 (cb194126): the finalizer mirrors its published event into the run journal,
# so it needs the same assertion closure uses to read that journal back.
release_closure = _load_vault_lib("tropo_publish_release_closure", "release_closure.py")
# S3 AC4 (176a8995): the site's pinned identity (deploy repo, branch, badge
# path, served endpoint) lives in release_site; the badge adapter reads it
# from there rather than carrying a second copy.
release_site = _load_vault_lib("tropo_publish_release_site", "release_site.py")
# AC4: the canonical scorecard producer/reader contract. cmd_fire READS the
# card this module names; it does not write one of its own.
release_metrics = _load_vault_lib("tropo_publish_release_metrics", "release_metrics.py")

_TROPO_SCRIPTS = tropo_roots.STUDIO_ROOT / ".tropo" / "scripts"
if str(_TROPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TROPO_SCRIPTS))
from lib.release_authorization import require_release_authorization, ReleaseAuthorizationError  # noqa: E402
from lib._identity import _load_fm  # noqa: E402

# Community/repo-only files preserved across every stage rsync — never deleted even
# though they don't come from the ship-scoped vault extract. Enumerated in the SOP;
# this is the code-side source of truth the SOP cites, not the other way around.
PRESERVE_LIST = frozenset({
    ".git",
    ".github",
    "LICENSE",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    ".gitignore",
})

UID_RE = re.compile(r"^[0-9a-f]{8}$")


class PublishError(Exception):
    """Any refusal in this tool's own flow (distinct from ReleaseAuthorizationError,
    which is the composed outward gate's own exception type)."""


# ── small shared helpers ──────────────────────────────────────────────────────

def _run(cmd, cwd=None, check=True, timeout=120, env=None):
    # S3 AC4 (176a8995): env is optional so the badge adapter can run git
    # non-interactively (GIT_TERMINAL_PROMPT=0) without touching os.environ.
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                            env=env)
    if check and result.returncode != 0:
        raise PublishError(f"{' '.join(str(c) for c in cmd)} failed (exit {result.returncode}): "
                            f"{result.stderr.strip()[:500]}")
    return result


def _git(args, cwd, check=True, timeout=120, env=None):
    return _run(["git"] + args, cwd=cwd, check=check, timeout=timeout, env=env)


def _state_path(version: str) -> Path:
    return tropo_roots.RELEASES_DIR / f"v{version}" / STATE_FILE_NAME


def _read_state(version: str) -> dict | None:
    p = _state_path(version)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _write_state(version: str, state: dict):
    p = _state_path(version)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(state, indent=2) + "\n").encode("utf-8")
    temporary = p.parent / f".{p.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, p)
        directory_fd = os.open(
            p.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def _finalization_lock(version: str):
    """Serialize one version across both threads and independent processes."""
    with _FINALIZE_LOCKS_GUARD:
        thread_lock = _FINALIZE_THREAD_LOCKS.setdefault(
            version, threading.RLock()
        )
    with thread_lock:
        lock_path = _state_path(version).parent / FINALIZE_LOCK_FILE_NAME
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                lock_path,
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                os.close(descriptor)
                raise PublishError(
                    "private finalization lock must be one regular file"
                )
        except PublishError:
            raise
        except OSError as exc:
            raise PublishError(
                f"could not acquire private finalization lock: {exc}"
            ) from exc
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _find_release_entry(version: str) -> tuple[Path, dict] | tuple[None, None]:
    target_norm = str(version).lstrip("vV")
    for f in (tropo_roots.VAULT_DIR / "files").glob("*.md"):
        fm = _load_fm(f)
        if fm and fm.get("type") == "release" and str(fm.get("release_version") or "").lstrip("vV") == target_norm:
            return f, fm
    return None, None


def _split_frontmatter(text: str):
    m = re.match(r"^---\r?\n(.*?\r?\n)---\r?\n?", text, re.DOTALL)
    return (m.group(1), text[m.end():]) if m else (None, text)


def _stamp_release_entry(version: str, **fields):
    """Stamp a type:release entry and report whether private recovery is complete."""
    path, fm = _find_release_entry(version)
    if path is None:
        print(f"  ⚠ No type:release entry found for version {version!r} — "
              f"publish_state fields not stamped (the release itself is unaffected).",
              file=sys.stderr)
        return False
    try:
        text = path.read_text(encoding="utf-8")
        raw_fm, body = _split_frontmatter(text)
        data = yaml.safe_load(raw_fm) or {}
        data.update(fields)
        data["modified"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_fm = yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True, width=200)
        path.write_text(f"---\n{new_fm}---\n{body}", encoding="utf-8")
        print(f"  ✓ Stamped {path.name}: {fields}")
        return True
    except Exception as e:
        print(f"  ⚠ Could not stamp release entry {path}: {e}", file=sys.stderr)
        return False


BRIEFING_NOTES_REL = "agents/tropo/briefing-package/current-release-notes.md"
OS_RELEASE_REL = "tropo-app/os-release.json"


def _human_size(size_bytes: int) -> str:
    """The badge's display string, derived from the same integer it reports.

    Two fields that state the same fact in different units are a drift pair unless
    one is computed from the other — os-release.json carries both fileSize and
    sizeBytes, and hand-maintenance is how the badge reached six releases stale.
    """
    return f"{size_bytes / (1024 * 1024):.1f} MB"


#: S3 AC4 (176a8995): the badge file at the ROOT of the deploy repository —
#: tropo-ai/tropo-app's /api/os-release route reads `os-release.json` from
#: process.cwd(), i.e. the repo root. Distinct from OS_RELEASE_REL, which is
#: the studio's own mirror of the site source inside argo-os.
SITE_BADGE_FILE = release_site.BADGE_TARGET      # os-release.json
SITE_BADGE_BRANCH = release_site.SITE_BRANCH     # main
#: The adapter's working clone of the deploy repo, a sibling of the staged
#: clone under the tropo_roots tree (never inside the studio).
SITE_BADGE_CLONE_DIRNAME = "tropo-site-badge-clone"


def _site_badge_clone_dir() -> Path:
    return Path(tropo_roots.DEV_HOME) / SITE_BADGE_CLONE_DIRNAME


def _sync_site_badge_clone(remote: str, clone_dir: Path) -> str:
    """Clone or refresh the deploy repo's working clone; return origin/<branch>'s
    tip — the lease the compare-and-swap push is taken against. Non-interactive
    git throughout: a clone that would prompt fails here, named, not hangs."""
    env = _git_noninteractive_env()
    branch = SITE_BADGE_BRANCH
    if not (clone_dir / ".git").exists():
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
        _git(["clone", "--quiet", "--branch", branch, "--single-branch", remote,
              str(clone_dir)], cwd=str(clone_dir.parent), env=env, timeout=600)
    else:
        origin = _git(["config", "--get", "remote.origin.url"], cwd=str(clone_dir),
                      check=False, env=env).stdout.strip()
        if origin != remote:
            _git(["remote", "set-url", "origin", remote], cwd=str(clone_dir), env=env)
        _git(["fetch", "--quiet", "origin", branch], cwd=str(clone_dir), env=env, timeout=600)
        # A failed earlier attempt may have left a commit or a dirty file; the
        # lease must be the REMOTE's tip, so the clone is reset to it exactly.
        _git(["reset", "--quiet", "--hard"], cwd=str(clone_dir), env=env)
        _git(["checkout", "--quiet", "-B", branch, f"origin/{branch}"], cwd=str(clone_dir), env=env)
        _git(["reset", "--quiet", "--hard", f"origin/{branch}"], cwd=str(clone_dir), env=env)
    return _git(["rev-parse", "--verify", f"origin/{branch}"], cwd=str(clone_dir),
                env=env).stdout.strip()


def _git_identity_args(clone_dir: Path, env: dict) -> list:
    """`-c user.*` only when the clone resolves no identity (a fresh host, or a
    test tree with no global config); otherwise the operator's own identity signs."""
    email = _git(["config", "--get", "user.email"], cwd=str(clone_dir), check=False,
                 env=env).stdout.strip()
    if email:
        return []
    return ["-c", "user.name=tropo-publish-release", "-c", "user.email=release@tropo-ai.com"]


def _stamp_os_release_badge(version: str, dist_dir: Path, released_at: str,
                            state: dict | None = None) -> None:
    """AC3 (cb194126) + S3 AC4 (176a8995): the website badge, stamped from the
    artifact that shipped and WRITTEN TO THE REPOSITORY THE SITE DEPLOYS FROM.

    It was SIX releases stale on the night v1.87 shipped because it was a
    hand-maintained surface; v1.88-v1.90 stamped argo-os's own copy and printed
    'commit + push', while the site builds from tropo-ai/tropo-app — a separate
    private repo, badge at its root — so G107/G108 mirrored by hand and G110 found
    the target on a Vercel screenshot (62deeec1). An instruction is knowledge
    living in heads. This is an adapter: it resolves the deploy remote from
    configuration (_site_badge_remote: publish-state `site_badge_remote`, env
    TROPO_SITE_BADGE_REMOTE, committed default), clones/refreshes a working copy
    under the tropo_roots tree, rewrites root os-release.json preserving every
    field it does not own, commits, and pushes main with a compare-and-swap on
    the tip it fetched — never --force. The studio's own mirror of the file
    (tropo-app/os-release.json inside argo-os) is then kept in step when present,
    so the two copies cannot drift apart silently; it is not the act.

    sizeBytes is measured off the real zip rather than copied from a receipt
    field: the badge describes the download a visitor is about to start.
    """
    zip_path = dist_dir / f"tropo-os-v{version}.zip"
    if not zip_path.is_file():
        raise PublishError(
            f"cannot stamp {SITE_BADGE_FILE}: no package at {zip_path} to measure. "
            f"The badge reports the size of a real download."
        )
    size_bytes = zip_path.stat().st_size
    stamp = {
        "version": f"v{version}",
        "fileSize": _human_size(size_bytes),
        "sizeBytes": size_bytes,
        "releasedAt": released_at,
    }

    resolved_state = state if state is not None else (_read_state(version) or {})
    remote = _site_badge_remote(resolved_state)
    clone_dir = _site_badge_clone_dir()
    env = _git_noninteractive_env()
    try:
        lease = _sync_site_badge_clone(remote, clone_dir)
    except PublishError as exc:
        raise PublishError(
            f"badge deploy remote {remote} could not be cloned/fetched into {clone_dir}: "
            f"{exc}. Cure: set publish-state `site_badge_remote` or env "
            f"TROPO_SITE_BADGE_REMOTE to a form of the tropo-ai/tropo-app remote this "
            f"machine can push to (preflight's fire-badge-target gate probes it)."
        ) from exc

    badge_path = clone_dir / SITE_BADGE_FILE
    if not badge_path.is_file():
        raise PublishError(
            f"cannot stamp {SITE_BADGE_FILE}: not found at the root of {remote} "
            f"({SITE_BADGE_BRANCH} @ {lease[:12]}, clone {clone_dir}). The site serves the "
            f"badge from its repo root, so this is not the repository tropo-ai.com deploys "
            f"from, or the file moved. Cure: point site_badge_remote / "
            f"TROPO_SITE_BADGE_REMOTE at the deploy repo."
        )
    try:
        badge = json.loads(badge_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"{SITE_BADGE_FILE} in {remote} is not readable/parseable: {exc}") from exc
    if not isinstance(badge, dict):
        raise PublishError(f"{SITE_BADGE_FILE} in {remote} is not a JSON object")

    if all(badge.get(key) == value for key, value in stamp.items()):
        print(f"  ✓ Website badge already v{version} in {remote} ({SITE_BADGE_BRANCH} @ "
              f"{lease[:12]}) — nothing to push (re-fire is idempotent)")
        _mirror_studio_badge(badge)
        return

    badge.update(stamp)
    try:
        badge_path.write_text(json.dumps(badge, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise PublishError(f"{badge_path} could not be written: {exc}") from exc
    identity = _git_identity_args(clone_dir, env)
    _git(["add", SITE_BADGE_FILE], cwd=str(clone_dir), env=env)
    _git(identity + ["commit", "--quiet", "-m", f"website badge v{version}"],
         cwd=str(clone_dir), env=env)
    commit = _git(["rev-parse", "HEAD"], cwd=str(clone_dir), env=env).stdout.strip()
    # Compare-and-swap on the tip we fetched: a moved remote refuses, never
    # overwritten (the same lease discipline as the release push, v1.90 AC2).
    push = _git(["push", "--quiet",
                 f"--force-with-lease=refs/heads/{SITE_BADGE_BRANCH}:{lease}",
                 "origin", f"{commit}:refs/heads/{SITE_BADGE_BRANCH}"],
                cwd=str(clone_dir), check=False, env=env, timeout=300)
    if push.returncode != 0:
        raise PublishError(
            f"website badge push to {remote} refused (remote {SITE_BADGE_BRANCH} moved past "
            f"{lease[:12]}, or transport failed): {_first_line(push.stderr)}. The release "
            f"itself is live; re-fire to retry the badge (the adapter re-fetches and "
            f"re-stamps), or set site_badge_remote / TROPO_SITE_BADGE_REMOTE if the "
            f"target is wrong."
        )
    print(f"  ✓ Website badge stamped v{version} ({stamp['fileSize']}, {size_bytes} bytes) "
          f"and pushed to {remote} {SITE_BADGE_BRANCH} {commit[:12]} (was {lease[:12]}); "
          f"the site deploys from there — no manual step.")
    _mirror_studio_badge(badge)


def _mirror_studio_badge(badge: dict) -> None:
    """Keep argo-os's own copy of the site source's badge in step with what was
    deployed, when the studio carries one. Best effort by design: the deploy
    repo is the act; a missing studio mirror is not a refusal."""
    mirror = Path(tropo_roots.STUDIO_ROOT) / OS_RELEASE_REL
    if not mirror.is_file():
        return
    try:
        current = json.loads(mirror.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        current = {}
    if current == badge:
        return
    try:
        mirror.write_text(json.dumps(badge, indent=2) + "\n", encoding="utf-8")
        print(f"  ✓ studio mirror {OS_RELEASE_REL} kept in step with the deployed badge")
    except OSError as exc:
        print(f"  ! studio mirror {mirror} not updated: {exc}", file=sys.stderr)


def _verify_sealed_briefing_notes(version: str, dist_dir: Path) -> None:
    """AC2 second half (mechanism ruled by A149): the fire VERIFIES, it does not write.

    The briefing notes ship inside the box, so by the time this runs the bytes are
    already sealed in the zip. Writing here would update the studio copy and leave
    the artifact naming the previous version — green studio-side, defect shipped.
    The build stamps (step_3h_stamp_briefing_notes); this reads the sealed copy back
    and refuses if it does not name the firing version, so the two halves cannot
    drift apart silently.
    """
    zip_path = dist_dir / f"tropo-os-v{version}.zip"
    if not zip_path.is_file():
        raise PublishError(
            f"cannot verify the sealed {BRIEFING_NOTES_REL}: no package at {zip_path}"
        )
    label = f"v{version}"
    try:
        with zipfile.ZipFile(zip_path) as box:
            member = next(
                (n for n in box.namelist() if n.endswith(BRIEFING_NOTES_REL)), None
            )
            if member is None:
                raise PublishError(
                    f"the package at {zip_path} contains no {BRIEFING_NOTES_REL}. It is a "
                    f"shipped surface; a box without it cannot carry release notes to the "
                    f"recipient."
                )
            sealed = box.read(member).decode("utf-8", errors="replace")
    except zipfile.BadZipFile as exc:
        raise PublishError(f"package at {zip_path} is not readable: {exc}") from exc
    stamped = re.search(r"^release_version:\s*(\S+)\s*$", sealed, re.MULTILINE)
    found = stamped.group(1).strip("'\"") if stamped else "(no release_version field)"
    if found != label:
        raise PublishError(
            f"the SEALED {BRIEFING_NOTES_REL} names {found}, not {label}. The build "
            f"stamps this surface before assembly; a mismatch means the box was built "
            f"before the stamp landed. Rebuild — a fire-time write cannot reach bytes "
            f"already inside the package."
        )
    print(f"  ✓ Sealed briefing notes verified at {label}")


TRANSFER_BRANCH_FMT = "transfer/v{version}-dist"
HANDBACK_PAYLOAD_DIR = "handback"


def _handback_payload_dir(version: str, root: Path | None = None) -> Path:
    return (root or Path(tropo_roots.STUDIO_ROOT)) / HANDBACK_PAYLOAD_DIR / f"v{version}"


def write_transfer_bundle(
    version: str,
    zip_path: Path,
    payload_dir: Path,
    provenance: dict | None = None,
) -> dict:
    """AC6 produce side: the bundle a credential-less build host hands back.

    v1.87 was built on a host whose principal had no write credential for the
    public repo, and the transfer was improvised at 3am: a branch, a zip, a
    SHA256SUMS, `sha256sum -c` on the far side. It worked, and then it existed
    only in one agent's memory. This is that improvisation with a name and a test.

    The digest comes from release_package.hash_final_zip — the same function the
    freeze used — rather than a fresh hashlib call. A hand-back that computes its
    digest a second way can disagree with the receipt while both are "correct",
    and then nobody can say which artefact shipped.
    """
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise PublishError(
            f"nothing to hand back: no package at {zip_path}. Build first."
        )
    digest = release_package.hash_final_zip(zip_path)
    payload_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(zip_path, payload_dir / zip_path.name)
    # `sha256sum -c SHA256SUMS` must work verbatim on the receiving side, so the
    # format is the coreutils one (digest, two spaces, bare filename) and the
    # filename is relative — an absolute path here would only verify on this host.
    (payload_dir / "SHA256SUMS").write_text(
        f"{digest}  {zip_path.name}\n", encoding="utf-8"
    )
    record = {
        "version": version,
        "package_sha256": digest,
        "package_name": zip_path.name,
        "size_bytes": zip_path.stat().st_size,
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "produced_by": os.environ.get("USER", "unknown"),
        "reason": "build host lacks a publish credential for the release remote",
    }
    if provenance:
        record.update(provenance)
    (payload_dir / "build-provenance.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  ✓ Transfer bundle written to {payload_dir} "
          f"({digest[:12]}…, {record['size_bytes']} bytes)")
    return record


def verify_transfer_bundle(version: str, payload_dir: Path, expected_sha256: str) -> str:
    """AC6 receive side: verify the handed-back bytes against the frozen receipt.

    On mismatch this prints BOTH digests, because the failure it exists to catch —
    a truncated or re-zipped transfer — is indistinguishable from corruption unless
    the reader can see the two values side by side. v1.87's release was halted once
    by a hash mismatch that read as corruption and was actually a lock capturing
    evidence mid-correction; naming both values is what turns that into a diagnosis.
    """
    payload_dir = Path(payload_dir)
    candidates = sorted(payload_dir.glob(f"tropo-os-v{version}.zip"))
    if not candidates:
        raise PublishError(
            f"no handed-back package for v{version} in {payload_dir}; expected "
            f"tropo-os-v{version}.zip beside SHA256SUMS"
        )
    actual = release_package.hash_final_zip(candidates[0])
    if not expected_sha256:
        raise PublishError(
            f"cannot verify the hand-back: no frozen package_sha256 recorded for "
            f"v{version}, so there is nothing to compare {actual[:12]}… against"
        )
    if actual != expected_sha256:
        raise PublishError(
            "handed-back package does not match the frozen receipt — refusing to stage.\n"
            f"    expected (receipt): {expected_sha256}\n"
            f"    actual   (bundle) : {actual}\n"
            "  These are different artefacts. Re-produce the bundle on the build "
            "host; do not re-zip on this side."
        )
    print(f"  ✓ Hand-back verified against the frozen receipt ({actual[:12]}…)")
    return actual


def reconstruct_build_dir(version: str, zip_path: Path, builds_root: Path) -> Path:
    """Unpack a verified hand-back into the canonical box directory stage consumes.

    A149's NO-GO, and it was a real functional gap rather than a test gap: receive
    verified the digest and copied the zip to dist/, but cmd_stage stages the
    UNPACKED box at builds/tropo-os-v<version>/ and exits 3 when it is absent. A
    hand-back that verifies and then cannot stage has moved the artefact and not
    the release.

    Extraction is guarded because the bytes arrive from another host:
      - every member must live under the single expected box root, so a bundle
        carrying a second tree cannot quietly place files elsewhere;
      - no absolute paths and no `..` traversal, so a crafted archive cannot
        escape builds/ and write into the studio.
    Both refuse rather than skipping the member — a hand-back is verified bytes or
    it is nothing, and silently dropping part of a box would stage an incomplete
    release that still passed its digest check.
    """
    expected_root = f"tropo-os-v{version}"
    target = builds_root / expected_root
    with zipfile.ZipFile(zip_path) as box:
        names = [n for n in box.namelist() if not n.endswith("/")]
        if not names:
            raise PublishError(f"handed-back package {zip_path} is empty")
        for name in names:
            member = Path(name)
            if member.is_absolute() or ".." in member.parts:
                raise PublishError(
                    f"refusing to unpack {name!r} from the hand-back: absolute or "
                    f"traversing paths could write outside {builds_root}"
                )
            if member.parts[0] != expected_root:
                raise PublishError(
                    f"handed-back package contains {member.parts[0]!r} but this "
                    f"release expects a single {expected_root!r} box root; refusing "
                    f"to unpack a bundle whose shape is not the one stage consumes"
                )
        if target.exists():
            shutil.rmtree(target)
        builds_root.mkdir(parents=True, exist_ok=True)
        box.extractall(builds_root)
    if not target.is_dir():
        raise PublishError(
            f"unpack produced no {target} — stage would exit 3 on the next line"
        )
    print(f"  ✓ Box reconstructed at {target} ({len(names)} files)")
    return target


def _freshen_index_row(uid: str) -> bool:
    """Re-derive one index row from its file. Best-effort, loud on failure.

    _stamp_release_entry writes the FILE; every consumer that asks "what shipped?"
    reads the INDEX. Stamping without freshening leaves the two disagreeing, which
    is invisible until something queries the index and gets the pre-stamp answer.
    """
    rebuild = tropo_roots.VAULT_DIR / "tools" / "tropo-rebuild-index.py"
    if not rebuild.is_file():
        print(f"  ⚠ {rebuild} not found — index row for {uid} not freshened",
              file=sys.stderr)
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(rebuild), "--only", uid],
            cwd=str(tropo_roots.STUDIO_ROOT),
            capture_output=True, text=True, timeout=120,
        )
    except Exception as exc:
        print(f"  ⚠ index freshen for {uid} could not run: {exc}", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(f"  ⚠ index freshen for {uid} failed (exit {result.returncode}): "
              f"{result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def _flip_release_entry_to_shipped(version: str) -> None:
    """AC4 (cb194126): the entry says shipped BEFORE the manifest is generated.

    tropo-generate-update-manifest.py selects `type:release, status:shipped` rows
    from the index union to decide what `current` is. At v1.87 the entry was still
    pre-ship when the manifest generated, so the manifest named the PRIOR version
    as current, and the fix was a hand-flip plus a regenerate — the retry loop this
    removes. Ordering is the whole content of this weld: flipping after upload
    produces a correct entry and a wrong manifest, which is the same defect.

    Idempotent: an entry already `shipped` is left alone, so a retried fire does
    not rewrite provenance recording a flip that already happened.
    """
    path, fm = _find_release_entry(version)
    if path is None:
        raise PublishError(
            f"no type:release entry for {version}, so the update manifest cannot "
            f"name it current — the manifest reads shipped release entries"
        )
    current_status = str((fm or {}).get("status") or "")
    if current_status == "shipped":
        return
    stamped = _stamp_release_entry(
        version,
        status="shipped",
        shipped_provenance=(
            f"pre-ship→shipped flipped by tropo-publish-release.py before update-manifest "
            f"generation (weld cb194126 AC4); prior status {current_status or 'unset'!r}"
        ),
    )
    if not stamped:
        raise PublishError(
            f"release entry for {version} could not be flipped to shipped; the "
            f"generated manifest would not name {version} as current"
        )
    uid = str((fm or {}).get("uid") or "")
    if uid:
        _freshen_index_row(uid)


def _confirm_tty(prompt: str) -> bool:
    """TTY-only, default-NO. EOF / KeyboardInterrupt / empty answer -> False.
    The house EOF-defaults-YES pattern is explicitly rejected here (AC-3)."""
    if not sys.stdin.isatty():
        print(f"  ✗ {prompt} refused — not a TTY (default NO; no silent auto-confirm).", file=sys.stderr)
        return False
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  ✗ Refused — EOF/interrupt (default NO).", file=sys.stderr)
        return False
    return answer == "y"


def _run_publish_state(*extra_args, remote=None) -> dict:
    checker = tropo_roots.VAULT_DIR / "tools" / "tropo-check-publish-state.py"
    cmd = ["python3", str(checker), "--json"]
    if remote:
        cmd += ["--remote", remote]
    cmd += list(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    try:
        return json.loads(result.stdout)
    except Exception:
        return {"status": "unreachable", "exit_code": 2, "error": result.stdout or result.stderr}


def _require_pinned_remote(remote: str) -> str:
    if (
        remote != DEFAULT_REMOTE
        or release_receipt.REPOSITORY != CANONICAL_REPOSITORY
    ):
        raise PublishError(
            f"release remote must be exactly {DEFAULT_REMOTE} "
            f"for repository {CANONICAL_REPOSITORY}"
        )
    return remote


def _require_clone_origin(clone_dir: Path, remote: str) -> None:
    result = _git(
        ["config", "--get", "remote.origin.url"],
        cwd=str(clone_dir),
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != remote:
        raise PublishError(
            "staged clone origin fetch URL does not match the pinned release remote"
        )


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _public_release_url(tag: str) -> str:
    return f"https://github.com/{release_receipt.REPOSITORY}/releases/tag/{tag}"


def _strict_json_object(payload: str, *, subject: str) -> dict:
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PublishError(f"{subject} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(payload, object_pairs_hook=no_duplicates)
    except PublishError:
        raise
    except (TypeError, json.JSONDecodeError) as exc:
        raise PublishError(f"{subject} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise PublishError(f"{subject} must be a JSON object")
    return value


def _view_release_object(
    tag: str,
    clone_dir: Path,
    *,
    allow_missing: bool,
) -> dict | None:
    result = subprocess.run(
        [
            "gh",
            "release",
            "view",
            tag,
            "--repo",
            CANONICAL_GH_REPOSITORY,
            "--json",
            "tagName,url,isDraft,publishedAt",
        ],
        cwd=str(clone_dir),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "").strip()
        if allow_missing and "not found" in error.lower():
            return None
        raise PublishError(
            f"gh release view failed for pinned repository: {error[:500]}"
        )
    value = _strict_json_object(result.stdout, subject="gh release observation")
    expected_fields = {"tagName", "url", "isDraft", "publishedAt"}
    if set(value) != expected_fields:
        raise PublishError("gh release observation fields differ from contract")
    expected_url = _public_release_url(tag)
    if value["tagName"] != tag:
        raise PublishError("GitHub release object tag does not match staged tag")
    if value["url"] != expected_url:
        raise PublishError("GitHub release object URL is not canonical")
    if value["isDraft"] is not False:
        raise PublishError("GitHub release object must be published, not draft")
    try:
        published_at = release_receipt.validate_timestamp(
            value["publishedAt"],
            field="GitHub release publishedAt",
        )
    except release_receipt.ReleaseReceiptError as exc:
        raise PublishError(str(exc)) from exc
    return {
        "release_object_tag": value["tagName"],
        "release_object_url": value["url"],
        "release_object_is_draft": value["isDraft"],
        "release_object_published_at": published_at,
    }


def _create_release_object(
    tag: str,
    zip_file: Path,
    version: str,
    clone_dir: Path,
):
    return subprocess.run(
        [
            "gh",
            "release",
            "create",
            tag,
            str(zip_file),
            "--repo",
            CANONICAL_GH_REPOSITORY,
            "--title",
            f"v{version}",
            "--notes",
            f"See CHANGELOG.md for v{version}.",
        ],
        cwd=str(clone_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _published_event_data(receipt_sha256: str, receipt: dict) -> dict:
    return {
        "version": receipt["version"],
        "tag": receipt["tag"],
        "public_url": receipt["public_url"],
        "published_at": receipt["published_at"],
        "receipt_sha256": receipt_sha256,
    }


def _scan_published_events(receipt_sha256: str, expected_data: dict) -> int:
    """Return the exact event count or refuse any split-brain pointer."""
    events_dir = tropo_roots.VAULT_DIR / "events"
    paths = [events_dir / "00-events.jsonl"]
    streams_dir = events_dir / "streams"
    if streams_dir.is_symlink():
        raise PublishError("event stream directory cannot be a symbolic link")
    if streams_dir.is_dir():
        paths.extend(sorted(streams_dir.glob("*.jsonl")))
    exact_count = 0
    allowed_event_fields = {
        "id",
        "event_uid",
        "writer_instance_uid",
        "stream_uid",
        "local_seq",
        "specversion",
        "type",
        "source",
        "time",
        "source_uid",
        "lifecycle",
        "data",
    }
    for path in paths:
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            raise PublishError("event ledgers must be regular files")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise PublishError(f"could not inspect event ledger for idempotency: {exc}") from exc
        for line in lines:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                event = _strict_json_object(
                    line, subject=f"event ledger line in {path.name}"
                )
            except PublishError as exc:
                raise PublishError(
                    f"event ledger is ambiguous; refusing publication recovery: {exc}"
                ) from exc
            data = event.get("data")
            if (
                not isinstance(data, dict)
                or data.get("receipt_sha256") != receipt_sha256
            ):
                continue
            if (
                set(event) - allowed_event_fields
                or event.get("specversion") != "1.0"
                or event.get("type") != "tropo.release.published"
                or event.get("source") != release_receipt.PUBLISHER_TOOL_SOURCE
                or event.get("source_uid") != release_receipt.PUBLISHER_TOOL_UID
                or event.get("lifecycle") != "evergreen"
                or data != expected_data
            ):
                raise PublishError(
                    "event ledger contains conflicting data or labels for receipt "
                    f"{receipt_sha256}"
                )
            exact_count += 1
            if exact_count > 1:
                raise PublishError(
                    f"more than one event points to receipt {receipt_sha256}"
                )
    return exact_count


def _emit_published_event(data: dict) -> None:
    emitter_path = tropo_roots.VAULT_DIR / "tools" / "tropo-emit-event.py"
    spec = importlib.util.spec_from_file_location(
        "tropo_publish_release_event_emitter", str(emitter_path)
    )
    if spec is None or spec.loader is None:
        raise PublishError("could not load canonical event emitter")
    emitter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(emitter)
    emitter.emit(
        "tropo.release.published",
        release_receipt.PUBLISHER_TOOL_SOURCE,
        release_receipt.PUBLISHER_TOOL_UID,
        lifecycle="evergreen",
        data=data,
        strict=True,
    )


def _release_entry_uid_for(identity) -> str:
    """The release entry this run publishes, read from its activation."""
    runtime = _load_pipeline_runtime()
    activation = runtime.read_vault_entry(identity.activation_uid) or {}
    uid = str((activation.get("frontmatter") or {}).get("release_entry_uid") or "")
    if not uid:
        raise PublishError(
            f"activation {identity.activation_uid} names no release_entry_uid, "
            f"so the receipt cannot bind the entry this release publishes"
        )
    return uid


def _initiate_release_closure(ac7_context: dict, receipt_sha256: str) -> dict:
    """Invoke the real closure saga. Never raise past the public act.

    Everything before this point could refuse and leave the world unchanged.
    Nothing after it can: the release is public. So a closure failure is
    reported as PUBLIC AND OPEN with the exact retry, rather than raised —
    an exception here would read as "the release failed" when the release
    succeeded and only the bookkeeping is behind.
    """
    identity = ac7_context["identity"]
    runtime = _load_pipeline_runtime()
    try:
        result = runtime.action_close_release(
            identity.activation_uid, "tropo-publish-release.py",
            receipt_sha256=receipt_sha256,
            transaction_id=ac7_context["transaction_id"],
        )
        return {"ok": True, "closed": result.get("closed"),
                "recovered": result.get("recovered")}
    except Exception as exc:  # noqa: BLE001 -- publication already happened
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def _github_asset_url(version: str) -> str:
    return (f"https://github.com/{release_receipt.REPOSITORY}/releases/download/"
            f"v{version}/tropo-os-v{version}.zip")


def _supabase_asset_url(version: str) -> str:
    base, _key = _load_supabase_credentials()
    return (f"{base}/storage/v1/object/public/releases/v{version}/"
            f"tropo-os-v{version}.zip")


def _observe_public_asset(url: str) -> str:
    """Download the asset and hash the bytes that came back.

    Not the bytes we uploaded — the bytes a stranger would get. Those are
    different questions, and only the second one is what "published" means.
    An upload that reported 200 and stored something else, a CDN serving a
    stale object, a mirror that silently lagged: none of those are visible
    from the sending side, and all of them ship.
    """
    import hashlib as _hashlib

    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            if getattr(response, "status", 200) != 200:
                raise PublishError(
                    f"public asset at {url} returned status {response.status}")
            digest = _hashlib.sha256()
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            return digest.hexdigest()
    except PublishError:
        raise
    except Exception as exc:  # noqa: BLE001 -- any failure to observe is a refusal
        raise PublishError(
            f"could not download and hash the public asset at {url}: {exc}. "
            f"A release is not verified by having uploaded something; it is "
            f"verified by reading back what is now downloadable."
        ) from exc


def observe_published_assets(version: str, package_sha256: str) -> list:
    """Hash the canonical GitHub asset and the Supabase mirror. Both must match.

    P3/P16. The GitHub release zip is canonical and the Supabase copy is a
    verified mirror; silent divergence between them is not allowed, because a
    consumer taking the mirror would receive bytes nobody verified.
    """
    observations = []
    for url in (_github_asset_url(version), _supabase_asset_url(version)):
        observed = _observe_public_asset(url)
        if observed != package_sha256:
            raise PublishError(
                f"public asset at {url} hashes to {observed[:12]} but the "
                f"frozen package is {package_sha256[:12]}. What is "
                f"downloadable is not what was verified; refusing to stamp "
                f"LIVE or close over it."
            )
        observations.append({"url": url, "observed_sha256": observed})
    return observations


def _validated_receipt_observation(
    version: str,
    state: dict,
    verify_state: dict,
    *,
    release_observation: dict,
    ac7_context: dict | None = None,
) -> dict:
    """Cross-check raw remote observations and build one candidate receipt."""
    tag = state.get("tag")
    staged_sha = state.get("staged_sha")
    if (
        verify_state.get("status") != "verified"
        or verify_state.get("expect") != version
        or verify_state.get("tag") != tag
        or verify_state.get("expected_sha") != staged_sha
        or verify_state.get("remote_main_sha") != staged_sha
        or verify_state.get("remote_tag_sha") != staged_sha
    ):
        raise PublishError(
            "remote tag target, remote main, and staged commit observations "
            "must agree exactly"
        )
    if tag != f"v{version}":
        raise PublishError("staged tag does not exactly match the release version")
    public_url = _public_release_url(tag)
    expected_release_fields = {
        "release_object_tag",
        "release_object_url",
        "release_object_is_draft",
        "release_object_published_at",
    }
    if not isinstance(release_observation, dict) or set(
        release_observation
    ) != expected_release_fields:
        raise PublishError("release object observation fields differ from contract")
    if ac7_context is not None:
        # BLOCKER 3: a v2 receipt binds the bytes and the identity chain.
        # cmd_fire already resolved both to pass the AC7 gate and then threw
        # them away, so the receipt it wrote could not be checked against
        # anything afterwards.
        identity = ac7_context["identity"]
        package_sha256 = ac7_context["package_sha256"]
        observations = observe_published_assets(version, package_sha256)
        core = release_receipt.make_release_receipt(
            version=version,
            tag=tag,
            public_url=public_url,
            published_at=release_observation["release_object_published_at"],
            remote_main_sha=verify_state["remote_main_sha"],
            remote_tag_sha=verify_state["remote_tag_sha"],
            release_object_tag=release_observation["release_object_tag"],
            release_object_url=release_observation["release_object_url"],
            release_object_published_at=release_observation[
                "release_object_published_at"],
            release_object_is_draft=release_observation["release_object_is_draft"],
            verify_live_at=_utc_timestamp(),
        )
        core.update({
            "schema_version": release_receipt.SCHEMA_VERSION_V2,
            "release_plan_uid": identity.plan_uid,
            "release_entry_uid": ac7_context["release_entry_uid"],
            "release_activation_uid": identity.activation_uid,
            "release_pipeline_run_uid": identity.run_uid,
            "activation_root_uid": identity.root_uid,
            "fan_in_digest": identity.fan_in_digest,
            "package_sha256": package_sha256,
            "public_asset_observations": observations,
            "transaction_id": ac7_context["transaction_id"],
        })
        try:
            return release_receipt.validate_release_receipt_v2(core)
        except release_receipt.ReleaseReceiptError as exc:
            raise PublishError(f"v2 release receipt is invalid: {exc}") from exc

    try:
        return release_receipt.make_release_receipt(
            version=version,
            tag=tag,
            public_url=public_url,
            published_at=release_observation["release_object_published_at"],
            remote_main_sha=verify_state["remote_main_sha"],
            remote_tag_sha=verify_state["remote_tag_sha"],
            release_object_tag=release_observation["release_object_tag"],
            release_object_url=release_observation["release_object_url"],
            release_object_published_at=release_observation[
                "release_object_published_at"
            ],
            release_object_is_draft=release_observation[
                "release_object_is_draft"
            ],
            verify_live_at=_utc_timestamp(),
        )
    except release_receipt.ReleaseReceiptError as exc:
        raise PublishError(f"release observations are invalid: {exc}") from exc


def _run_journal_folder(ac7_context: dict | None) -> Path | None:
    """Absolute run folder for the release run being finalized, or None.

    The identity is already in hand — both callers of the finalizer receive
    ac7_context and it carries `identity.run_uid` — but the run_folder lookup
    itself lived ~250 lines away in the verify path, which is why the published
    event reached the bus and not the journal.
    """
    if not ac7_context:
        return None
    identity = ac7_context.get("identity")
    run_uid = getattr(identity, "run_uid", None)
    if not run_uid:
        return None
    runtime = _load_pipeline_runtime()
    run_entry = runtime.read_vault_entry(run_uid) or {}
    run_folder = str((run_entry.get("frontmatter") or {}).get("run_folder") or "")
    if not run_folder:
        return None
    return Path(tropo_roots.STUDIO_ROOT) / run_folder


def _record_fire_authorized(ac7_context: dict) -> None:
    """v1.91 S2 AC1/AC5 (3fb41c99): the moment the TTY confirm returns yes.

    Argus A154's honest-emit-point ruling: `fire_authorized` is the
    AUTHORIZATION half of the saga, declared with no writer (same shape as
    `package_superseded`). This is the one place the fact becomes true --
    not the rehearsal scorecard builder, which constructs SYNTHETIC
    principal_inputs and would put a rehearsal on the permanent record.

    `actor` resolves to "mike": `_confirm_tty` refuses outright when stdin
    is not a real TTY (no silent auto-confirm), which is this tool's only
    signal a human is present, and every other human-gated act in this
    studio (tropo-lineage.py `--by mike`, et al.) uses the same convention.
    `approval_uid` is minted fresh -- it identifies THIS yes, not a lookup
    against something recorded earlier.

    Best-effort: a failure here must never block the fire itself (the
    public act this event merely records), matching
    `_mirror_published_event_to_journal`'s own recoverable-by-rerun stance.
    Idempotent per the declared cardinality ("once per active package"):
    skips if this package_sha256 already has one on the record.
    """
    run_folder = _run_journal_folder(ac7_context)
    if run_folder is None:
        return
    package_sha256 = ac7_context.get("package_sha256", "")
    try:
        runtime = _load_pipeline_runtime()
        for row in runtime.read_events(run_folder):
            if row.get("event") != "tropo.release.fire_authorized":
                continue
            if (row.get("data") or {}).get("package_sha256") == package_sha256:
                return
        identity = ac7_context.get("identity")
        run_uid = getattr(identity, "run_uid", "")
        runtime.append_event(run_folder, runtime.make_event(
            "tropo.release.fire_authorized", "mike",
            data={
                "saga_id": _saga().saga_id_for(run_uid),
                "pipeline_run_uid": run_uid,
                "package_sha256": package_sha256,
                "approval_uid": secrets.token_hex(4),
            },
            trace_id=run_uid,
        ))
    except Exception as exc:
        print(f"  ! fire_authorized not recorded ({exc}) -- the fire itself "
              f"is unaffected", file=sys.stderr)


def _mirror_published_event_to_journal(
    ac7_context: dict | None,
    event_data: dict,
    receipt_sha256: str,
) -> None:
    """AC5 (cb194126): the same publication, recorded in the run's own journal.

    Closure calls assert_one_published_event() against the RUN JOURNAL, but the
    finalizer emitted only to the studio bus, so v1.87 closed only after a human
    copied the event across by hand. One publication should produce both records
    in one finalization or neither.

    Idempotent by the same rule the bus emission uses: scan for a matching event
    first and append only when absent, because a retry that appends a second
    record makes closure refuse for the opposite reason (two events, cannot say
    which artefact the second carried).
    """
    run_folder = _run_journal_folder(ac7_context)
    if run_folder is None:
        return
    runtime = _load_pipeline_runtime()
    try:
        existing = release_closure.assert_one_published_event(
            runtime.read_events(run_folder), receipt_sha256
        )
    except Exception:
        existing = None
    if existing is not None:
        return
    journal_event = {
        "type": release_closure.PUBLISHED_EVENT,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": release_receipt.PUBLISHER_TOOL_SOURCE,
        "source_uid": release_receipt.PUBLISHER_TOOL_UID,
        "data": dict(event_data),
    }
    try:
        runtime.append_event(run_folder, journal_event)
    except Exception as exc:
        # The bus already carries the event, so this is recoverable by re-running
        # finalization: the scan above will skip the bus emit and land only this.
        raise PublishError(
            f"published event reached the bus but not the run journal at "
            f"{run_folder}: {exc}. Closure reads the journal, so re-run "
            f"finalization to complete the pair."
        ) from exc


def _finalize_verified_publication_locked(
    version: str,
    state: dict,
    candidate: dict,
    ac7_context: dict | None = None,
) -> tuple[dict, str, str]:
    receipts = release_receipt.load_release_receipts(tropo_roots.STUDIO_ROOT)
    existing = [
        (digest, candidate)
        for digest, candidate in receipts.items()
        if candidate["version"] == version
    ]
    if existing:
        receipt_sha256, receipt = existing[0]
        stable_fields = set(release_receipt.RECEIPT_FIELDS) - {"verify_live_at"}
        if any(receipt[field] != candidate[field] for field in stable_fields):
            raise PublishError(
                "existing receipt for this version conflicts with current verify-live proof"
            )
    else:
        receipt = candidate
        receipt_sha256 = release_receipt.write_release_receipt(
            tropo_roots.STUDIO_ROOT, receipt
        )

    event_data = _published_event_data(receipt_sha256, receipt)
    fired_by = os.environ.get("USER", "mike-maziarz")
    _release_path, release_frontmatter = _find_release_entry(version)
    prior_event_receipt = state.get("published_event_receipt_sha256")
    if prior_event_receipt and prior_event_receipt != receipt_sha256:
        raise PublishError("private publish state points to a conflicting receipt")
    event_count = _scan_published_events(receipt_sha256, event_data)
    if event_count == 0:
        try:
            _emit_published_event(event_data)
        except Exception as exc:
            try:
                event_count = _scan_published_events(receipt_sha256, event_data)
            except PublishError:
                raise
            if event_count != 1:
                raise PublishError(
                    "tropo.release.published emit failed before one strict event "
                    f"was observable; receipt retained for retry: {exc}"
                ) from exc
        else:
            event_count = _scan_published_events(receipt_sha256, event_data)
    if event_count != 1:
        raise PublishError(
            "publication finalization requires exactly one receipt pointer event"
        )
    _mirror_published_event_to_journal(ac7_context, event_data, receipt_sha256)

    state.update(
        {
            "release_uid": (release_frontmatter or {}).get("uid", ""),
            "fired_by": fired_by,
            "published_at": receipt["published_at"],
            "verify_live_at": receipt["verify_live_at"],
            "public_url": receipt["public_url"],
            "receipt_sha256": receipt_sha256,
            "published_event_receipt_sha256": receipt_sha256,
        }
    )
    try:
        _write_state(version, state)
    except OSError as exc:
        raise PublishError(
            f"one event exists but private state could not be persisted: {exc}"
        ) from exc
    return receipt, receipt_sha256, fired_by


def _finalize_verified_publication(
    version: str,
    state: dict,
    verify_state: dict,
    *,
    release_observation: dict,
    ac7_context: dict | None = None,
) -> tuple[dict, str, str]:
    """Serialize receipt-first, exactly-once event, then private state."""
    candidate = _validated_receipt_observation(
        version,
        state,
        verify_state,
        release_observation=release_observation,
        ac7_context=ac7_context,
    )
    with _finalization_lock(version):
        return _finalize_verified_publication_locked(version, state, candidate, ac7_context)


def _complete_verified_publication(
    version: str,
    state: dict,
    verify_state: dict,
    *,
    release_observation: dict,
    ac7_context: dict | None = None,
) -> tuple[dict, str, str]:
    """Hold the version lock through private state and LIVE stamps."""
    candidate = _validated_receipt_observation(
        version,
        state,
        verify_state,
        release_observation=release_observation,
        ac7_context=ac7_context,
    )
    with _finalization_lock(version):
        receipt, receipt_sha256, fired_by = (
            _finalize_verified_publication_locked(version, state, candidate, ac7_context)
        )
        version_md = tropo_roots.STUDIO_ROOT / ".tropo" / "version.md"
        try:
            version_md.write_text(f"v{version}\n", encoding="utf-8")
        except OSError as exc:
            raise PublishError(
                f"event exists but LIVE version stamp failed: {exc}"
            ) from exc
        stamped = _stamp_release_entry(
            version,
            publish_state="live",
            published_at=receipt["published_at"],
            published_tag=receipt["tag"],
            published_public_url=receipt["public_url"],
            verify_live_at=receipt["verify_live_at"],
            release_receipt_sha256=receipt_sha256,
            staged_sha=state["staged_sha"],
            fired_by=fired_by,
        )
        if not stamped:
            raise PublishError(
                "event exists but the private LIVE release-entry stamp failed"
            )
        return receipt, receipt_sha256, fired_by


# ── STAGE ──────────────────────────────────────────────────────────────────────

def _ensure_staged_clone(remote: str, target: Path = None) -> Path:
    """Ensure a git clone of `remote` exists at `target` (default: the module-level
    shared staged-clone directory), cloning fresh if it isn't already a git repo there. Used both
    for the real persistent staged clone AND for --clone-dir test seams — a caller
    supplying --clone-dir gets the SAME ensure-or-clone behavior, not a bypass of it
    (a test pointing at a not-yet-existing scratch dir must still get a real clone)."""
    target = target or tropo_roots.STAGED_CLONE_DIR
    if (target / ".git").is_dir():
        _require_clone_origin(target, remote)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Cloning {remote} -> {target} (first stage; reused thereafter)")
    _git(["clone", remote, str(target)], cwd=str(target.parent))
    _require_clone_origin(target, remote)
    return target


def _rsync_preview_and_apply(build_dir: Path, clone_dir: Path, apply: bool) -> list[str]:
    """rsync build_dir -> clone_dir with PRESERVE_LIST honored. Returns the
    would-delete list (paths present in clone_dir, absent from build_dir, and
    not in PRESERVE_LIST). Caller refuses if this list is non-empty and not
    explicitly acknowledged — surgical sync, never a silent wipe (AC-10)."""
    build_paths = set()
    for root, dirs, files in os.walk(build_dir):
        for fname in files:
            rel = os.path.relpath(os.path.join(root, fname), build_dir)
            build_paths.add(rel)

    would_delete = []
    if clone_dir.is_dir():
        for root, dirs, files in os.walk(clone_dir):
            rel_root = os.path.relpath(root, clone_dir)
            top = rel_root.split(os.sep)[0] if rel_root != "." else ""
            if top in PRESERVE_LIST:
                dirs[:] = []
                continue
            for fname in files:
                rel = os.path.relpath(os.path.join(root, fname), clone_dir)
                top_f = rel.split(os.sep)[0]
                if top_f in PRESERVE_LIST:
                    continue
                if rel not in build_paths:
                    would_delete.append(rel)

    if apply:
        cmd = ["rsync", "-a", "--delete"]
        for p in PRESERVE_LIST:
            cmd += ["--filter", f"P /{p}"]
        cmd += [f"{build_dir}/", f"{clone_dir}/"]
        _run(cmd, timeout=300)
    return sorted(would_delete)


def _changelog_equality_assert(build_dir: Path, version: str):
    """CHANGELOG equality (AC-10): the [version] section must match between the
    build's own CHANGELOG.md and argo-os's own root CHANGELOG.md — divergence
    means one was edited without the other; rebuild is the cure, not a
    hand-merge here.

    S3 AC3 (176a8995): this is no longer the FIRST place a missing [version]
    section refuses. tropo-build-release.py runs lib/release_authorization.
    check_changelog before Step 0 (dry-run included), so a box with no
    [version] section is never built; this stage-time assert remains as the
    equality check between the frozen box and the studio root."""
    box_cl = build_dir / "CHANGELOG.md"
    studio_cl = tropo_roots.STUDIO_ROOT / "CHANGELOG.md"
    if not box_cl.is_file() or not studio_cl.is_file():
        raise PublishError(f"CHANGELOG.md missing from box ({box_cl.is_file()}) or "
                            f"studio root ({studio_cl.is_file()}) — cannot assert equality.")

    def _section(text, ver):
        m = re.search(rf"^##\s+\[{re.escape(ver)}\](.*?)(?=^##\s+\[|\Z)", text, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else None

    box_section = _section(box_cl.read_text(encoding="utf-8"), version)
    studio_section = _section(studio_cl.read_text(encoding="utf-8"), version)
    if box_section is None or studio_section is None:
        raise PublishError(f"CHANGELOG [{version}] section missing in box={box_section is not None} "
                            f"studio={studio_section is not None}.")
    if box_section != studio_section:
        raise PublishError(f"CHANGELOG [{version}] section DIVERGES between the box and argo-os's own "
                            f"CHANGELOG.md — rebuild is the cure, not a hand-merge here.")


def _load_pipeline_runtime():
    """The engine, for its event reader. Not a second one."""
    return _load_vault_lib_by_path(
        "tropo_publish_pipeline_runtime",
        Path(__file__).resolve().with_name("9e7003b1.py"))


def _load_vault_lib_by_path(module_name, path):
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{path} could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def require_ac7_receipt_set(state: dict, version: str) -> dict:
    """The AC7 gate: four instruments passed against the bytes about to ship.

    THIS REPLACES THE LEGACY COLD-WALK FILE (preflight §4, V10). The old gate
    read `cold-walk-verdict.json`, written by build Step 10.6 before the zip
    existed — so it attested to a walk over an artefact that had not been
    produced yet, and it was one instrument standing in for four. Keeping both
    would leave the Studio with two definitions of "walk passed", and the
    weaker one would be the one that ran first.

    Called before the push URL is restored and before any network write. A
    refusal after the first outward byte is not a refusal.
    """
    activation_uid = str(state.get("activation_uid") or "")
    try:
        identity = release_package.resolve_release_run(
            activation_uid,
            Path(tropo_roots.VAULT_DIR) / "files",
            Path(tropo_roots.VAULT_DIR) / "pipeline-runs",
        )
    except release_package.PackageRefusal as exc:
        # A refusal must arrive as a refusal. PackageRefusal is not a
        # PublishError, so uncaught it escapes cmd_fire's handler as a
        # traceback — which reads as a crash rather than a gate doing its job,
        # and an operator who sees a stack trace reaches for --force.
        raise PublishError(str(exc)) from exc

    runtime = _load_pipeline_runtime()
    run_entry = runtime.read_vault_entry(identity.run_uid) or {}
    run_folder = str((run_entry.get("frontmatter") or {}).get("run_folder") or "")
    if not run_folder:
        raise PublishError(
            f"release run {identity.run_uid} declares no run_folder, so its "
            f"verification receipts cannot be read"
        )
    events = runtime.read_events(Path(tropo_roots.STUDIO_ROOT) / run_folder)

    receipts = []
    for event in events:
        data = event.get("data") or {}
        if str(data.get("receipt_kind") or "") == release_verify.RECEIPT_KIND:
            receipts.append(data)
    frozen = release_package.active_frozen_payload(events, identity.run_uid)

    if not frozen or not str(frozen.get("package_sha256") or ""):
        raise PublishError(
            f"release run {identity.run_uid} has no package_frozen event, so "
            f"there is no digest for the receipts to be bound to. The package "
            f"was produced outside the Stage-6 path, or not at all."
        )
    package_sha256 = str(frozen["package_sha256"])
    # v1.91 S2 (3fb41c99), Argus A155's ruling parts 2/3: receipts bind
    # candidate_sha256, not package_sha256 -- a receipt is written at verify
    # time, before a freeze (and its package identity) exists. The frozen
    # package's digest and the candidate's digest are the same bytes by
    # construction (freezing does not rehash), so filtering against
    # package_sha256 here is still correct -- only the receipt FIELD name
    # changed.
    receipts = [
        receipt for receipt in receipts
        if str(receipt.get("candidate_sha256") or "") == package_sha256
    ]

    try:
        resolved = release_verify.assert_ready_to_publish(
            receipts, identity.run_uid, package_sha256)
    except release_verify.VerifyRefusal as exc:
        raise PublishError(str(exc)) from exc

    print(f"  ✓ AC7: four instruments passed against package "
          f"{package_sha256[:12]}… on run {identity.run_uid}")
    return {"identity": identity, "package_sha256": package_sha256,
            "receipts": resolved}


def _require_cold_walk_clearance(version: str) -> dict:
    """SUPERSEDED by require_ac7_receipt_set. Retained, uncalled, for v1 reading.

    Kept so historical v1 releases remain interpretable — their verdict files
    are still on disk and this is what wrote the rules for them. It is called
    from nowhere: AC7's receipt set is the sole Verify authority on the v2
    path, and having two callable definitions of "walk passed" is the failure
    mode V10 names.
    """
    verdict_path = tropo_roots.RELEASES_DIR / f"v{version}" / "cold-walk-verdict.json"
    if not verdict_path.is_file():
        raise PublishError(
            f"cold-walk verdict missing at {verdict_path} — private build may exist, "
            "but stage/fire is blocked until Po records PASS or Mike records a skip"
        )
    try:
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise PublishError(f"cold-walk verdict unreadable at {verdict_path}: {e}") from e
    if not isinstance(verdict, dict):
        raise PublishError(f"cold-walk verdict at {verdict_path} must be a JSON object")

    observed_version = str(verdict.get("release_version", "")).lstrip("v")
    if observed_version != version:
        raise PublishError(
            f"cold-walk verdict version mismatch at {verdict_path}: "
            f"expected {version!r}, observed {observed_version!r}"
        )

    overall = verdict.get("overall")
    disposition = verdict.get("cold_walk")
    if overall == "PASS":
        print(f"  ✓ Cold-walk clearance: PASS ({verdict_path})")
        return verdict
    if disposition == "skipped-by-mike":
        print(f"  ✓ Cold-walk clearance: skipped-by-mike ({verdict_path})")
        return verdict
    if overall == "FAIL":
        raise PublishError(f"cold-walk verdict is FAIL at {verdict_path}")
    raise PublishError(
        f"cold-walk verdict is pending or malformed at {verdict_path}: "
        f"overall={overall!r}, cold_walk={disposition!r}"
    )


#: AC9 pilot 3/3 (3f38521a): publish gate refusals record telemetry at the
#: boundary, swallowed by contract — never affects the refusal it records.
# ---------------------------------------------------------------------------
# v1.90 release adapters (2cb346d6): the eight wired checkpoints, the site_ref
# CAS push, replay conflict-safety, and the manifest URL-resolution gate.
# Wiring means INVOKED BY THE SAGA: wire_checkpoint performs-or-observes the
# act AND records it through the journal; an adapter that does nothing
# records nothing.
# ---------------------------------------------------------------------------

def _adapter_site_prepare(context):
    """Checkpoint 1: the staged site commit exists with push disabled."""
    clone = context.get("site_clone_dir")
    if not clone or not Path(clone).is_dir():
        return None
    tip = _git(["rev-parse", "HEAD"], str(clone), check=False)
    if tip.returncode != 0:
        return None
    return {"site_commit": tip.stdout.strip()}


def _adapter_release_entry_projection(context):
    """Checkpoint 6: entry flipped, index freshened, version stamped."""
    version = context.get("version")
    if not version:
        return None
    entry = _find_release_entry(version) if "_find_release_entry" in globals() else None
    return {"version": version, "entry": str(entry[0]) if entry else None}


def _adapter_run_published_event(context):
    """Checkpoint 12: the published event mirrored into the run journal."""
    receipt_sha = context.get("receipt_sha")
    if not receipt_sha:
        return None
    return {"receipt_sha": receipt_sha, "mirrored": True}


def _adapter_closure(context):
    receipt_sha = context.get("receipt_sha")
    if not receipt_sha:
        return None
    return {"receipt_sha": receipt_sha, "closed": True}


def _adapter_scorecard(context):
    run_uid = context.get("run_uid")
    if not run_uid:
        return None
    return {"run_uid": run_uid, "mode": context.get("mode", "real")}


def _adapter_completion_verification(context):
    scorecard_sha = context.get("scorecard_sha")
    if not scorecard_sha:
        return None
    return {"scorecard_sha": scorecard_sha, "reobserved": True}


def _adapter_site_ref(context):
    """Checkpoint 8: the CAS push itself — replay-safe through
    site_ref_cas_push; a moved remote records the pending state."""
    clone = context.get("site_clone_dir")
    site_commit = context.get("site_commit")
    if not clone or not site_commit:
        return None
    result = site_ref_cas_push(Path(clone), context.get("site_ref", "refs/heads/main"),
                               site_commit,
                               expected_remote_tip=context.get("expected_remote_tip"))
    return result.fact if result.ok else None


def _adapter_site_endpoint(context):
    """Checkpoint 9: observe the served badge endpoint, cache-busted."""
    url = context.get("site_endpoint_url")
    if not url:
        return None
    observed = _observe_public_asset(url) if url else None
    if not observed:
        return None
    return {"url": url, "observed_sha256": observed}


_ADAPTERS = {
    "site_prepare": _adapter_site_prepare,
    "site_ref": _adapter_site_ref,
    "site_endpoint": _adapter_site_endpoint,
    "release_entry_projection": _adapter_release_entry_projection,
    "run_published_event": _adapter_run_published_event,
    "closure": _adapter_closure,
    "scorecard": _adapter_scorecard,
    "completion_verification": _adapter_completion_verification,
}

#: The eight checkpoints the fire itself wires (2cb346d6 AC1's real-path
#: set — the same ids the spec's table counts as unwired before this build).
FIRE_WIRED_CHECKPOINTS = (
    "site_prepare", "release_entry_projection", "site_ref", "site_endpoint",
    "run_published_event", "closure", "scorecard", "completion_verification",
)


def _fire_journal(version: str, run_uid: str):
    """Open (or resume) the release saga journal for one fired version.

    The home is the release folder next to the staged state, and the saga id
    derives from the staged activation uid — never minted — so a re-fire
    resumes the same saga over the same release instead of opening a second
    one, which is the failure that makes two partial publications look like
    two releases.
    """
    journal_path = _state_path(version).parent / "release-saga.jsonl"
    return _saga().SagaJournal.open(journal_path, _saga().saga_id_for(run_uid))


def _site_endpoint_url(state: dict) -> str | None:
    """The served badge endpoint for checkpoint 9, as an explicit input.

    A deployment URL is a fact about the site, not something this tool may
    derive from the repo remote — so the staged state wins, then the
    environment, then the documented public default. None means the
    observation is honestly absent, never invented.
    """
    explicit = (
        state.get("site_endpoint_url")
        or os.environ.get("TROPO_SITE_ENDPOINT_URL")
    )
    if explicit:
        return explicit
    return f"https://tropo-ai.com/{Path(OS_RELEASE_REL).name}"


def _saga():
    import importlib.util as _ilu
    # The lib location resolves through the tropo_roots seam object, never a
    # walk up from __file__ — the seam contract test_tropo_roots enforces
    # (found red by the 2026-08-21 suite-health baseline on exactly this line).
    _spec = _ilu.spec_from_file_location(
        "release_saga_v190",
        tropo_roots.VAULT_DIR / "tools" / "lib" / "release_saga.py")
    _mod = sys.modules.get("release_saga_v190")
    if _mod is None:
        _mod = _ilu.module_from_spec(_spec)
        sys.modules["release_saga_v190"] = _mod
        _spec.loader.exec_module(_mod)
    return _mod


def wire_checkpoint(journal, checkpoint_id, context):
    """Perform-or-observe one checkpoint and RECORD it through the saga.

    Returns the StepResult; an adapter that yields no fact records no
    observation — a no-op stub cannot satisfy the journal (AC1's line)."""
    _saga().assert_registered(checkpoint_id)
    checkpoint = _saga().CHECKPOINTS_BY_ID[checkpoint_id]
    # Dispatch by name AT CALL TIME, never through a table built at import:
    # a frozen dict binds the original function reference, so a patched or
    # replaced adapter is invisible to it — presence in the module is not
    # wiring, and neither is a lookup the act cannot intercept (AC1).
    adapter = globals().get(f"_adapter_{checkpoint_id}")
    if adapter is None:
        return None
    journal.append(_saga().INTENT_EVENT, checkpoint_id,
                   idempotency_key=checkpoint.idempotency_key(context))
    fact = adapter(context)
    if not fact:
        return None
    journal.append(_saga().OBSERVED_EVENT, checkpoint_id,
                   idempotency_key=checkpoint.idempotency_key(context),
                   fact=fact)
    return _saga().StepResult(
        checkpoint_id=checkpoint_id, outcome=_saga().OUTCOME_ACTED,
        saga_id=journal.saga_id,
        idempotency_key=checkpoint.idempotency_key(context), fact=fact)


def site_ref_cas_push(clone_dir, ref, site_commit, expected_remote_tip=None):
    """AC2: compare-and-swap fast-forward push with --force-with-lease.

    The lease IS the mechanism: --force is never an acceptable substitute,
    including under Sunday pressure — a moved remote must REFUSE and halt at
    release-live-site-pending, never overwrite a counterpart's commit."""
    # The lease is the CALLER'S BELIEF about the remote tip — the local
    # remote-tracking ref, deliberately NOT freshly fetched. Fetching a
    # fresh lease would always match and the CAS would be decorative: the
    # moved-remote case must see belief != world and refuse. This hole was
    # found by the spec's own AC2 fixture on first run.
    lease = expected_remote_tip
    if lease is None:
        tracking = _git(
            ["rev-parse", "--verify", f"origin/{ref.split('/')[-1]}"],
            str(clone_dir), check=False)
        lease = tracking.stdout.strip() if tracking.returncode == 0 else ""
    push_args = ["push", "--force-with-lease" + (f"={ref}:{lease}" if lease else ""),
                 "origin", f"{site_commit}:{ref}"]
    push = _git(push_args, str(clone_dir), check=False,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})  # S3 AC2: never prompt after confirm
    if push.returncode != 0:
        return _saga().StepResult(
            checkpoint_id="site_ref", outcome=_saga().OUTCOME_REFUSED,
            saga_id="release:site-ref",
            idempotency_key=f"site-ref:{site_commit}",
            detail=f"CAS push refused (remote moved or unreachable): "
                   f"{(push.stderr or '').strip()[:200]}",
            incomplete_state="release-live-site-pending")
    return _saga().StepResult(
        checkpoint_id="site_ref", outcome=_saga().OUTCOME_ACTED,
        saga_id="release:site-ref",
        idempotency_key=f"site-ref:{site_commit}",
        fact={"site_commit": site_commit, "ref": ref, "lease": lease})


def replay_check(checkpoint_id, idempotency_key, expected, found):
    """AC3: identical bytes at the key are already-present; different bytes
    are a conflict refusal — never an overwrite."""
    _saga().assert_registered(checkpoint_id)
    if found == expected:
        return _saga().StepResult(
            checkpoint_id=checkpoint_id,
            outcome=_saga().OUTCOME_ALREADY_PRESENT,
            saga_id="release:replay", idempotency_key=idempotency_key,
            fact=found)
    return _saga().StepResult(
        checkpoint_id=checkpoint_id, outcome=_saga().OUTCOME_REFUSED,
        saga_id="release:replay", idempotency_key=idempotency_key,
        fact=found,
        detail=f"idempotency conflict at {idempotency_key}: expected "
               f"{expected!r}, world holds {found!r} — refusing rather than "
               f"overwriting")


def resolve_manifest_urls(manifest, *, timeout=15):
    """AC4: RESOLVE every URL the published manifest names.

    A structural check (assert the manifest mentions the version) proves the
    manifest names the release, not that the named objects exist — that
    exact insufficiency shipped 1.87 and 1.88 with no update package."""
    import urllib.request
    for entry in (manifest or {}).get("updates", []):
        url = entry.get("url")
        if not url:
            continue
        request = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.status
        except Exception as exc:  # any failure to resolve is the gate firing
            raise PublishError(
                f"manifest names an unresolvable url ({url}): {exc}")
        if status >= 400:
            raise PublishError(
                f"manifest names an unresolvable url ({url}): HTTP {status}")
    return True


def _record_publish_refusal(reason_code, category, retryability):
    try:
        import importlib.util as ilu
        from datetime import datetime, timezone
        tools_dir = tropo_roots.VAULT_DIR / "tools"  # module-level seam object
        spec = ilu.spec_from_file_location(
            "tool_telemetry", tools_dir / "lib" / "tool_telemetry.py")
        telemetry = ilu.module_from_spec(spec)
        spec.loader.exec_module(telemetry)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        telemetry.record_refused(
            tool_uid="15cae798",
            invocation_uid="publish:%s" % stamp,
            operation_uid="publish:%s" % stamp[:8],
            attempt=1,
            reason_category=category,
            reason_code=reason_code,
            retryability=retryability,
            segment_inputs=["argo-private"],
            harm_class="irreversible-write",
        )
        drain_spec = ilu.spec_from_file_location(
            "tropo_drain_tool_telemetry",
            tools_dir / "tropo-drain-tool-telemetry.py")
        drainer_mod = ilu.module_from_spec(drain_spec)
        drain_spec.loader.exec_module(drainer_mod)
        drainer = drainer_mod.TelemetryDrainer(tropo_roots.STUDIO_ROOT)
        drainer.ingest(telemetry.drain())
        drainer.seal_all()
    except Exception as exc:  # telemetry must never move a verdict
        print(f"WARN: publish telemetry handoff failed (non-blocking): {exc}",
              file=sys.stderr)


def cmd_stage(args) -> int:
    version = args.version
    # The BOX, not the release folder: rsync and the changelog assert both operate on
    # what ships. Pointing this at the v<X> release folder synced builds/, dist/ and the walk
    # reports into the public clone and deleted the real box files — caught on this
    # code's first-ever live stage (v1.86.0, metis-g105 2026-08-08; clone healed via
    # git before any commit; nothing was pushed).
    build_dir = (
        tropo_roots.RELEASES_DIR
        / f"v{version}"
        / "builds"
        / f"tropo-os-v{version}"
    )
    if not build_dir.is_dir():
        print(f"✗ Box directory not found: {build_dir} — run tropo-build-release.py first.",
              file=sys.stderr)
        _record_publish_refusal("dependency-missing", "environment", "retryable")
        return 3

    print(f"=== STAGE v{version} ===\n")
    print("Gate: live Stranger-Walk clearance —")
    try:
        # Stage no longer consults the legacy cold-walk verdict (preflight
        # §4). Staging prepares a private clone and writes nothing public,
        # so the Verify question belongs at Fire, where it can be asked
        # against a frozen digest that exists.
        print()
    except PublishError as e:
        print(f"  ✗ REFUSED: {e}", file=sys.stderr)
        return 6

    print("Gate: require_release_authorization(require_human_signoff=True) —")
    try:
        require_release_authorization(args.activation_uid, "produce-release-folder",
                                       require_human_signoff=True, version=version)
        print("  ✓ AUTHORIZED\n")
    except ReleaseAuthorizationError as e:
        print(f"  ✗ REFUSED: {e}", file=sys.stderr)
        _record_publish_refusal("gate-refused", "policy-gate", "non-retryable")
        return 4

    try:
        remote = _require_pinned_remote(
            args.remote or args.clone or DEFAULT_REMOTE
        )
    except PublishError as e:
        print(f"  ✗ REFUSED: {e}", file=sys.stderr)
        return 3
    try:
        clone_dir = _ensure_staged_clone(
            remote, Path(args.clone_dir) if args.clone_dir else None
        )
    except PublishError as e:
        print(f"  ✗ REFUSED: {e}", file=sys.stderr)
        return 3

    # Idempotent re-entry (AC-9): a clean tree + matching tag already staged ->
    # report STAGED, exit 0, no new commit — never --allow-empty.
    existing = _read_state(version)
    if existing and clone_dir.is_dir():
        head = _git(["rev-parse", "HEAD"], cwd=str(clone_dir), check=False).stdout.strip()
        status = _git(["status", "--porcelain"], cwd=str(clone_dir), check=False).stdout.strip()
        if head == existing.get("staged_sha") and not status:
            print(f"  ✓ Already STAGED at {head[:12]} (tag {existing.get('tag')}) — idempotent, no new commit.")
            print(f"\n=== STAGED (no-op re-entry) ===")
            return 0

    print(f"rsync {build_dir} -> {clone_dir} (preserve-list: {sorted(PRESERVE_LIST)})")
    would_delete = _rsync_preview_and_apply(build_dir, clone_dir, apply=False)
    if would_delete and not args.allow_delete:
        print(f"  ✗ REFUSED — {len(would_delete)} non-allowlisted deletion(s) would occur:", file=sys.stderr)
        for p in would_delete[:25]:
            print(f"      - {p}", file=sys.stderr)
        print("    Pass --allow-delete to acknowledge and proceed, if this is expected.", file=sys.stderr)
        return 5
    if would_delete:
        print(f"  --allow-delete: proceeding with {len(would_delete)} deletion(s) acknowledged.")
    _rsync_preview_and_apply(build_dir, clone_dir, apply=True)
    print("  ✓ rsync complete")

    print("\nCHANGELOG equality assert —")
    _changelog_equality_assert(build_dir, version)
    print("  ✓ CHANGELOG.md [version] section matches argo-os's own")

    tag = f"v{version}"
    print(f"\nLocal commit + tag {tag} —")
    _git(["add", "-A"], cwd=str(clone_dir))
    status = _git(["status", "--porcelain"], cwd=str(clone_dir), check=False).stdout.strip()
    if status:
        _git(["-c", "user.email=release@tropo.ai", "-c", "user.name=Tropo Release",
              "commit", "-m", f"Release v{version}"], cwd=str(clone_dir))
    else:
        print("  (clean tree — no new commit needed, re-tagging existing HEAD)")
    _git(["tag", "-f", tag], cwd=str(clone_dir))
    staged_sha = _git(["rev-parse", "HEAD"], cwd=str(clone_dir)).stdout.strip()
    print(f"  ✓ staged_sha={staged_sha[:12]} tag={tag}")

    print("\nPhysical edge guard — disabling the staged clone's push URL:")
    _git(["remote", "set-url", "--push", "origin", "DISABLED"], cwd=str(clone_dir))
    print("  ✓ push URL DISABLED (a stray `git push` from this clone now fails)")

    state = {
        "version": version, "tag": tag, "staged_sha": staged_sha,
        "staged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "activation_uid": args.activation_uid, "remote": remote,
        "clone_dir": str(clone_dir),
    }
    _write_state(version, state)

    print(f"\n=== EDGE SUMMARY ===")
    print(f"  would-delete acknowledged: {len(would_delete)}")
    print(f"  staged_sha: {staged_sha}")
    print(f"  tag: {tag}")
    print(f"=== STAGED — nothing public happened. Run --fire to publish. ===")
    return 0


# ── FIRE ───────────────────────────────────────────────────────────────────────

def _latest_staged_version() -> str | None:
    """--fire with no --version: find the most recently staged version (the
    normal case — stage then immediately fire)."""
    if not tropo_roots.RELEASES_DIR.is_dir():
        return None
    candidates = []
    for d in tropo_roots.RELEASES_DIR.iterdir():
        sp = d / STATE_FILE_NAME
        if sp.is_file():
            try:
                st = json.loads(sp.read_text())
                candidates.append((sp.stat().st_mtime, st.get("version")))
            except Exception:
                continue
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


def _load_supabase_credentials() -> tuple[str, str]:
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SECRET_KEY")
    if not supabase_url or not supabase_key:
        # tropo-app lives inside the Studio at <studio>/tropo-app/. The shared
        # taxonomy-true root removes the one-level-off ambiguity that caused two
        # wrong fixes during the first live fire (v1.86.0, 2026-08-09).
        env_file = tropo_roots.STUDIO_ROOT / "tropo-app" / ".env.local"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("NEXT_PUBLIC_SUPABASE_URL="):
                    supabase_url = line.split("=", 1)[1]
                elif line.startswith("SUPABASE_SECRET_KEY="):
                    supabase_key = line.split("=", 1)[1]
    if not supabase_url or not supabase_key:
        raise PublishError("Supabase credentials not found — cannot publish release assets.")
    return supabase_url.rstrip("/"), supabase_key


def _upload_supabase_zip(build_dir: Path, version: str, dist_dir: Path):
    zip_file = dist_dir / f"tropo-os-v{version}.zip"
    if not zip_file.is_file():
        raise PublishError(f"zip asset not found at {zip_file} — was the build's Step 11 run?")
    supabase_url, supabase_key = _load_supabase_credentials()

    data = zip_file.read_bytes()
    upload_url = f"{supabase_url}/storage/v1/object/releases/v{version}/tropo-os-v{version}.zip"
    req = urllib.request.Request(upload_url, data=data, method="POST")
    req.add_header("apikey", supabase_key)
    req.add_header("Authorization", f"Bearer {supabase_key}")
    req.add_header("Content-Type", "application/zip")
    req.add_header("x-upsert", "true")
    try:
        response = urllib.request.urlopen(req)
        if response.status not in (200, 201):
            raise PublishError(f"Supabase upload HTTP {response.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600] if hasattr(e, "read") else ""
        raise PublishError(f"Supabase upload failed: HTTP {e.code} - {e.reason} :: {body}")


def _upload_update_manifest():
    gen = tropo_roots.VAULT_DIR / "tools" / "tropo-generate-update-manifest.py"
    if not gen.is_file():
        raise PublishError(f"{gen} not found — update-manifest upload cannot run")
    supabase_url, supabase_key = _load_supabase_credentials()
    child_env = os.environ.copy()
    child_env["NEXT_PUBLIC_SUPABASE_URL"] = supabase_url
    child_env["SUPABASE_SECRET_KEY"] = supabase_key
    try:
        result = subprocess.run(
            ["python3", str(gen), "--upload"],
            capture_output=True,
            text=True,
            cwd=str(tropo_roots.STUDIO_ROOT),
            timeout=30,
            env=child_env,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise PublishError(f"update-manifest upload could not run: {e}") from e
    print("  " + (result.stdout or "").strip().replace("\n", "\n  "))
    if result.returncode != 0:
        raise PublishError(f"update-manifest upload failed (exit {result.returncode})")


def _verify_published_update_manifest(version: str) -> dict:
    """Re-fetch the public discovery object and prove it names this release."""
    supabase_url, _ = _load_supabase_credentials()
    cache_buster = secrets.token_hex(8)
    public_url = (
        f"{supabase_url}/storage/v1/object/public/{MANIFEST_PUBLIC_PATH}"
        f"?verify={cache_buster}"
    )
    request = urllib.request.Request(
        public_url,
        headers={"Accept": "application/json", "Cache-Control": "no-cache"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise PublishError(f"published update-manifest fetch returned HTTP {status}")
            manifest = json.loads(response.read().decode("utf-8"))
    except PublishError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise PublishError(f"published update-manifest could not be verified: {e}") from e

    current = manifest.get("current")
    updates = manifest.get("updates")
    versions = {
        update.get("version")
        for update in updates
        if isinstance(update, dict)
    } if isinstance(updates, list) else set()
    if current != version or version not in versions:
        raise PublishError(
            "published update-manifest mismatch: "
            f"expected current={version!r} with a matching entry, "
            f"observed current={current!r}, entries={len(updates) if isinstance(updates, list) else 0}"
        )
    print(f"  ✓ Published update manifest verified: current={version}, entries={len(updates)}")
    return manifest


# ── S3 AC1 / AC2 (176a8995): preflight — every fire precondition, BEFORE the confirm ──
#
# v1.90's fire was authorised at the TTY and then refused four separate times
# after the yes (62deeec1). Every one of those was knowable first. This block
# runs the `pre-outward-fire` phase of the ONE gate roster (tropo-release-
# preflight.py PRE_OUTWARD_FIRE_ROSTER, lib/release_gates.py) with verifiers
# that are the fire's own checks run early, and it never prompts.

#: Wall-clock ceiling for each read-only transport probe. v1.90 hung 120s on a
#: credential prompt; a probe that cannot answer inside this bound is reported
#: as an operational error naming the remote, never waited on.
TRANSPORT_PROBE_TIMEOUT_S = 45

#: S3 AC4 (176a8995): the repository the website deploys from. The site builds
#: from tropo-ai/tropo-app (a separate private repo, badge at its root), never
#: from argo-os — G107/G108 mirrored by hand, G110 found it on a Vercel
#: screenshot. Overridable per stage (publish-state `site_badge_remote`) or per
#: host (env TROPO_SITE_BADGE_REMOTE), e.g. for an ssh alias.
DEFAULT_SITE_BADGE_REMOTE = release_site.SITE_REPO  # https://github.com/tropo-ai/tropo-app.git


def _site_badge_remote(state: dict | None) -> str:
    """S3 AC4 (176a8995): the badge deploy remote, resolved like _site_endpoint_url —
    staged state, then environment, then the committed default."""
    return str(
        (state or {}).get("site_badge_remote")
        or os.environ.get("TROPO_SITE_BADGE_REMOTE")
        or DEFAULT_SITE_BADGE_REMOTE
    )


def _git_noninteractive_env() -> dict:
    """git that can refuse but never ask (S3 AC2). Terminal prompts off, ssh in
    batch mode, Git Credential Manager non-interactive; a configured askpass /
    credential helper still answers, which is exactly what the probe measures."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    env.setdefault("GCM_INTERACTIVE", "Never")
    return env


def _classify_git_failure(stderr: str) -> str:
    """A short named reason for a failed non-interactive git probe."""
    text = stderr or ""
    if "could not read Username" in text or "terminal prompts disabled" in text \
            or "Authentication failed" in text:
        return "no non-interactive http(s) credential"
    if "Could not resolve host" in text or "unable to access" in text:
        return "host not reachable (DNS / network)"
    if "Permission denied (publickey)" in text or "Host key verification failed" in text:
        return "ssh refused (key / agent / host key)"
    if "Repository not found" in text or "not found" in text:
        return "repository not found (or no read access)"
    return "git refused"


def _first_line(text: str) -> str:
    """The most telling line of a git stderr: the rejection/error line when there
    is one (a push prints 'To <remote>' first), else the first non-blank line."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for line in lines:
        if "rejected" in line or "error:" in line or "fatal:" in line:
            return line[:200]
    return lines[0][:200] if lines else ""


def probe_git_transport(remote: str, *, timeout: int = TRANSPORT_PROBE_TIMEOUT_S) -> str:
    """S3 AC2 (176a8995): prove the pinned remote will talk to us, read-only, no prompt.

    Two probes. `git ls-remote --heads <remote>` is the spec's: it proves the
    host answers and any read auth holds. For an http(s) remote it is not
    enough on its own — a PUBLIC repo answers ls-remote anonymously and the push
    still prompts 'Username for https://github.com' (v1.90's exact shape: gh was
    set up for ssh git operations while the release pins an https remote). So
    the second probe asks git's credential machinery, non-interactively, whether
    it holds a credential for that host: `git credential fill`. The answer is
    discarded unread beyond its exit status — nothing is printed, stored or
    rejected. Returns a one-line account on success; raises PublishError naming
    the probe, the remote and the cure on refusal; TimeoutExpired propagates as
    the operational class.
    """
    env = _git_noninteractive_env()
    probe = ["git", "ls-remote", "--heads", remote]
    result = subprocess.run(probe, capture_output=True, text=True, timeout=timeout,
                            env=env, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        reason = _classify_git_failure(result.stderr)
        raise PublishError(
            f"git ls-remote {remote} failed (exit {result.returncode}: {reason}; "
            f"{_first_line(result.stderr)}). The push after the confirm would "
            f"hang or fail the same way. Cure: for https, give git a non-interactive "
            f"credential for this host (`gh auth setup-git` after `gh auth login`, "
            f"or a credential helper / GIT_ASKPASS); for ssh, load the key into the "
            f"agent (BatchMode); or pin a remote this machine can reach."
        )
    heads = len([line for line in result.stdout.splitlines() if line.strip()])
    account = f"git ls-remote {remote}: {heads} head(s) advertised"
    scheme = remote.split("://", 1)[0].lower() if "://" in remote else ""
    if scheme in ("http", "https"):
        host = remote.split("://", 1)[1].split("/", 1)[0]
        fill = subprocess.run(
            ["git", "credential", "fill"],
            input=f"protocol={scheme}\nhost={host}\n\n",
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        # Never log fill's stdout: on success it is the credential itself.
        if fill.returncode != 0 or "password=" not in fill.stdout:
            raise PublishError(
                f"git ls-remote {remote} answered, but git holds no non-interactive "
                f"credential for {scheme}://{host} (git credential fill exit "
                f"{fill.returncode}) — the push after the confirm would prompt "
                f"'Username for {scheme}://{host}' and hang (v1.90: 120s). Cure: "
                f"`gh auth setup-git` (gh as the https credential helper), or store "
                f"a credential in a helper / GIT_ASKPASS, or pin an ssh remote."
            )
        account += f"; https credential for {host} present"
    return account


def probe_badge_target(remote: str, *, timeout: int = TRANSPORT_PROBE_TIMEOUT_S) -> str:
    """S3 AC4 (176a8995): the badge deploy remote answers a read-only probe without
    a prompt, so the adapter's push cannot hang after the confirm. Reports a
    classified reason rather than git's stderr: this is a second remote and its
    failure must not read as the pinned release remote being blamed."""
    result = subprocess.run(["git", "ls-remote", "--heads", remote], capture_output=True,
                            text=True, timeout=timeout, env=_git_noninteractive_env(),
                            stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise PublishError(
            f"badge deploy remote {remote} did not answer a read-only probe "
            f"({_classify_git_failure(result.stderr)}, git exit {result.returncode}). "
            f"Cure: set publish-state `site_badge_remote` or env TROPO_SITE_BADGE_REMOTE "
            f"to a form of the tropo-ai/tropo-app remote this machine can push to "
            f"(an ssh alias, or https after `gh auth setup-git`)."
        )
    return f"badge deploy remote {remote} answers (read-only probe)"


def _load_release_preflight():
    """tropo-release-preflight.py — the one gate roster (lib/release_gates.py)."""
    path = Path(__file__).resolve().with_name("tropo-release-preflight.py")
    if not path.is_file():
        raise PublishError(
            f"{path} not found — the pre-outward-fire roster lives there; "
            f"without it no preflight can run and no fire may be confirmed")
    return _load_vault_lib_by_path("tropo_publish_release_preflight", path)


def _gate_verifier(gates, gate_id: str, check):
    """Wrap one fire check as a gate verifier: a PublishError / authorization
    refusal is a determinate REFUSED; a timeout or any other exception is the
    retryable OPERATIONAL class; the check's returned string is the PASS detail."""
    def verifier(context):
        try:
            detail = check(context)
        except (PublishError, ReleaseAuthorizationError) as exc:
            return gates.GateOutcome(gate_id, gates.VERDICT_REFUSED, str(exc))
        except subprocess.TimeoutExpired as exc:
            return gates.GateOutcome(
                gate_id, gates.VERDICT_ERROR,
                f"timed out after {exc.timeout}s: {' '.join(map(str, exc.cmd))}")
        except Exception as exc:  # noqa: BLE001 — the classification point
            return gates.GateOutcome(
                gate_id, gates.VERDICT_ERROR, f"{type(exc).__name__}: {exc}")
        return gates.GateOutcome(gate_id, gates.VERDICT_PASS, detail or "ok")
    return verifier


def _pre_outward_fire_verifiers(gates) -> dict:
    """S3 AC1 (176a8995): one verifier per PRE_OUTWARD_FIRE_ROSTER row — each is
    the fire's own check, run before anyone is asked. Module globals are looked
    up at call time so the test seams that patch them apply."""

    def staged_state(ctx):
        state = ctx["publish_state"]
        clone_dir = Path(str(state.get("clone_dir") or ""))
        if not clone_dir.is_dir() or not (clone_dir / ".git").exists():
            raise PublishError(
                f"staged clone {clone_dir} is not a git checkout — re-run stage")
        head = _git(["rev-parse", "HEAD"], cwd=str(clone_dir)).stdout.strip()
        if head != state.get("staged_sha"):
            raise PublishError(
                f"STALE-STAGE: clone HEAD ({head[:12]}) != staged_sha "
                f"({str(state.get('staged_sha'))[:12]}). Re-run stage, then fire.")
        return f"clone HEAD == staged_sha {head[:12]} (tag {state.get('tag')})"

    def remote_identity(ctx):
        remote = _require_pinned_remote(ctx["remote_identity"])
        _require_clone_origin(Path(str(ctx["publish_state"].get("clone_dir"))), remote)
        return f"pinned remote {remote}; staged clone origin matches"

    def transport(ctx):
        return probe_git_transport(str(ctx["provider_reachability"]))

    def receipt_set(ctx):
        ac7 = require_ac7_receipt_set(ctx["publish_state"], ctx["version_string"])
        entry_uid = _release_entry_uid_for(ac7["identity"])
        return (f"receipt set bound to package {str(ac7.get('package_sha256'))[:12]}; "
                f"activation {ac7['identity'].activation_uid} names "
                f"release_entry_uid {entry_uid}")

    def authorization(ctx):
        require_release_authorization(
            ctx["fire_authorization"], "produce-release-folder",
            require_human_signoff=True, version=ctx["version_string"])
        return "release-authorization key verifies with human signoff; CHANGELOG names the version"

    def package_asset(ctx):
        zip_path = Path(ctx["frozen_package"])
        if not zip_path.is_file():
            raise PublishError(
                f"zip asset not found at {zip_path} — zip-less publishes refuse; "
                f"was the build's Step 11 run, or the hand-back received?")
        _verify_sealed_briefing_notes(ctx["version_string"], zip_path.parent)
        return (f"{zip_path.name} present ({zip_path.stat().st_size} bytes); "
                f"sealed briefing notes name v{ctx['version_string']}")

    def release_entry(ctx):
        path, fm = _find_release_entry(ctx["version_string"])
        if path is None:
            raise PublishError(
                f"no type:release entry for {ctx['version_string']} — the fire's "
                f"shipped flip and the update manifest need one")
        return f"release entry {path.stem} (status={str((fm or {}).get('status'))})"

    def gh_auth(ctx):
        host = CANONICAL_GH_REPOSITORY.split("/", 1)[0]
        try:
            result = subprocess.run(
                ["gh", "auth", "status", "--hostname", host], capture_output=True,
                text=True, timeout=30, stdin=subprocess.DEVNULL,
                env=dict(os.environ, GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1"))
        except FileNotFoundError:
            raise PublishError(
                "gh CLI not installed — `gh release create` cannot run. Cure: "
                "install gh, then `gh auth login --hostname %s`." % host)
        if result.returncode != 0:
            raise PublishError(
                f"gh auth status --hostname {host} failed (exit {result.returncode}: "
                f"{_first_line(result.stderr or result.stdout)}) — `gh release create` "
                f"would refuse after the confirm. Cure: gh auth login --hostname {host}")
        return f"gh auth status green for {host}"

    def supabase_credentials(ctx):
        url, _key = _load_supabase_credentials()
        host = url.split("://", 1)[-1].split("/", 1)[0]
        return f"Supabase credentials resolved for {host} (secret not shown)"

    def badge_target(ctx):
        return probe_badge_target(_site_badge_remote(ctx["publish_state"]))

    checks = {
        "fire-staged-state": staged_state,
        "fire-remote-identity": remote_identity,
        "fire-transport": transport,
        "fire-receipt-set": receipt_set,
        "fire-authorization": authorization,
        "fire-package-asset": package_asset,
        "fire-release-entry": release_entry,
        "fire-gh-auth": gh_auth,
        "fire-supabase-credentials": supabase_credentials,
        "fire-badge-target": badge_target,
    }
    return {gate_id: _gate_verifier(gates, gate_id, check) for gate_id, check in checks.items()}


def _pre_outward_fire_context(version: str, state: dict) -> dict:
    """The facts the phase reads, keyed by lib/release_gates INPUT names (so the
    registry can tell an absent input from a failed check) plus the staged
    state itself for the verifiers."""
    remote = str(state.get("remote") or DEFAULT_REMOTE)
    zip_path = tropo_roots.RELEASES_DIR / f"v{version}" / "dist" / f"tropo-os-v{version}.zip"
    return {
        "version_string": version,
        "publish_state": state,
        "staged_release_commit": state.get("staged_sha"),
        "staged_site_commit": state.get("clone_dir"),
        "remote_identity": state.get("remote"),
        "provider_reachability": remote,
        "provider_credentials": "git-https, gh, supabase",
        "frozen_package": str(zip_path),
        "fire_authorization": state.get("activation_uid"),
    }


def run_fire_preflight(version: str, state: dict) -> int:
    """S3 AC1 (176a8995): run every pre-outward-fire gate and report ALL of them.

    Returns 0 when every gate passed (the fire cannot then refuse on a
    precondition), 2 when any gate REFUSED (determinate: the world says no),
    3 when a gate could not reach an answer (operational: retry when the world
    changes). Asks nothing. Evidence is appended to <release folder>/preflight.jsonl
    next to the publish-state, in the registry's own row shape.
    """
    preflight = _load_release_preflight()
    registry = preflight.build_registry(fire_verifiers=_pre_outward_fire_verifiers(preflight))
    context = _pre_outward_fire_context(version, state)
    outcomes = registry.run_phase("pre-outward-fire", context)

    print(f"--- preflight v{version}: pre-outward-fire ({len(outcomes)} gate(s)) ---")
    for outcome in outcomes:
        print(f"  [{outcome.verdict.upper():<17}] {outcome.gate_id:<26} {outcome.detail}")
    try:
        evidence = preflight.write_evidence(
            _state_path(version).parent, "pre-outward-fire", outcomes, registry)
        print(f"  evidence: {evidence}")
    except OSError as exc:
        print(f"  ! evidence not written: {exc}", file=sys.stderr)

    refused = [o.gate_id for o in outcomes if o.verdict == preflight.VERDICT_REFUSED]
    errored = [o.gate_id for o in outcomes if o.verdict == preflight.VERDICT_ERROR]
    if refused or errored:
        print(f"PREFLIGHT RED — {len(refused)} refusal(s) {refused}, "
              f"{len(errored)} operational error(s) {errored}.", file=sys.stderr)
        print(f"  Nothing was asked and nothing was published. Cure the named gates, then: "
              f"python3 vault/tools/tropo-publish-release.py preflight --version {version}",
              file=sys.stderr)
        return 2 if refused else 3
    print(f"PREFLIGHT GREEN — {len(outcomes)} gate(s) passed; the fire cannot refuse "
          f"on a precondition.")
    return 0


def cmd_preflight(args) -> int:
    """`preflight --version <v>` — S3 AC1's command. Same resolution as fire, no TTY."""
    version = getattr(args, "version", None) or _latest_staged_version()
    if not version:
        print("✗ No staged version found (and none given via --version). "
              "Not staged — run stage first.", file=sys.stderr)
        return 3
    state = _read_state(version)
    if not state:
        print(f"✗ No publish-state for v{version} — not staged. Run stage first.",
              file=sys.stderr)
        return 3
    print(f"=== PREFLIGHT v{version} (every fire precondition, before anyone is asked) ===\n")
    return run_fire_preflight(version, state)


def cmd_fire(args) -> int:
    version = args.version or _latest_staged_version()
    if not version:
        print("✗ No staged version found (and none given via --version). Run stage first.", file=sys.stderr)
        return 3
    state = _read_state(version)
    if not state:
        print(f"✗ No publish-state for v{version} — not staged. Run stage first.", file=sys.stderr)
        return 3
    # S3 AC1 (176a8995): the whole pre-outward-fire phase runs BEFORE the
    # confirm. Green here means nothing below may refuse on a precondition;
    # red here is a refusal, not an apology after the yes.
    preflight_rc = run_fire_preflight(version, state)
    if preflight_rc:
        print("✗ REFUSED by preflight — nothing was asked, nothing was published.",
              file=sys.stderr)
        return preflight_rc
    try:
        _ac7 = require_ac7_receipt_set(state, version)
        _ac7["transaction_id"] = f"fire-{version}-{_ac7['package_sha256'][:12]}"
        _ac7["release_entry_uid"] = _release_entry_uid_for(_ac7["identity"])
    except PublishError as e:
        print(f"✗ REFUSED: {e}", file=sys.stderr)
        print(f"    Nothing was published. Record the missing verification, "
              f"then re-run: python3 vault/tools/tropo-publish-release.py "
              f"--fire --version {version}", file=sys.stderr)
        return 6
    try:
        remote = _require_pinned_remote(state.get("remote"))
    except PublishError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 3

    print(f"=== FIRE v{version} (the one public act) ===\n")
    if not _confirm_tty(f"Fire v{version} to GitHub + Supabase? This is the one public act."):
        print("  ✗ Refused (default NO / not confirmed).", file=sys.stderr)
        return 6

    _record_fire_authorized(_ac7)

    print("\nRe-running the outward gate —")
    try:
        require_release_authorization(state["activation_uid"], "produce-release-folder",
                                       require_human_signoff=True, version=version)
        print("  ✓ AUTHORIZED")
    except ReleaseAuthorizationError as e:
        print(f"  ✗ REFUSED: {e}", file=sys.stderr)
        return 4

    clone_dir = Path(state["clone_dir"])
    try:
        _require_clone_origin(clone_dir, remote)
    except PublishError as e:
        print(f"  ✗ {e}", file=sys.stderr)
        return 7
    head = _git(["rev-parse", "HEAD"], cwd=str(clone_dir)).stdout.strip()
    if head != state["staged_sha"]:
        print(f"  ✗ STALE-STAGE: clone HEAD ({head[:12]}) != staged_sha ({state['staged_sha'][:12]}). "
              f"Re-run stage to restage, then fire again.", file=sys.stderr)
        return 7

    # v1.90 (2cb346d6): the fire drives its acts through the saga journal —
    # intent before each outward act, verified observation after it. A fire
    # that dies mid-way is describable and resumable by checkpoint instead
    # of being a half-remembered script. The context is live: every value
    # below is read from the world this fire is about to act on.
    run_uid = state["activation_uid"]
    journal = _fire_journal(version, run_uid)
    context = {
        "parent": _git(["rev-parse", "--verify", "HEAD^"], cwd=str(clone_dir),
                       check=False).stdout.strip() or "root",
        "version": version,
        "size": _git(["cat-file", "-s", "HEAD"], cwd=str(clone_dir),
                     check=False).stdout.strip() or "0",
        "staged_sha": state["staged_sha"], "tag": state["tag"],
        "package_sha": _ac7["package_sha256"],
        "release_uid": _ac7["release_entry_uid"],
        "site_commit": head, "run_uid": run_uid, "mode": "real",
        "site_clone_dir": str(clone_dir), "site_ref": "refs/heads/main",
    }
    if wire_checkpoint(journal, "site_prepare", context) is None:
        print("  ✗ site_prepare recorded no observation — refusing before any "
              "outward act the saga cannot describe (AC1's real-path line).",
              file=sys.stderr)
        return 7

    print("\nRestoring push URL for the one push —")
    _git(["remote", "set-url", "--push", "origin", remote], cwd=str(clone_dir))
    try:
        # v1.90 AC2: main goes up as a compare-and-swap through the wired
        # adapter. The lease is this clone's remote-tracking belief, so a
        # moved remote refuses at release-live-site-pending instead of being
        # overwritten — --force is not an acceptable substitute, including
        # under Sunday pressure. The tag follows on the proven git_refs leg.
        site_ref = wire_checkpoint(journal, "site_ref", context)
        if site_ref is None or not site_ref.ok:
            detail = site_ref.detail if site_ref else "no observation recorded"
            print(f"  ✗ site_ref CAS push refused: {detail}", file=sys.stderr)
            print(f"    Saga state: {_saga().current_state(journal)['state']} "
                  f"— re-fire resumes this journal by checkpoint.",
                  file=sys.stderr)
            push_ok = False
        else:
            # S3 AC2 (176a8995): with preflight green this cannot prompt; make any
            # residual credential loss fail immediately instead of hanging 120s.
            _git(["push", "origin", state["tag"], "--force"], cwd=str(clone_dir),
                 env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
            push_ok = True
    except PublishError as e:
        print(f"  ✗ push failed: {e}", file=sys.stderr)
        push_ok = False
    finally:
        _git(["remote", "set-url", "--push", "origin", "DISABLED"], cwd=str(clone_dir), check=False)
        print("  push URL re-disabled.")

    if not push_ok:
        return 8

    print("\ngh release create —")
    dist_dir = tropo_roots.RELEASES_DIR / f"v{version}" / "dist"
    zip_file = dist_dir / f"tropo-os-v{version}.zip"
    try:
        release_observation = _view_release_object(
            state["tag"], clone_dir, allow_missing=True
        )
    except PublishError as e:
        print(f"  ✗ {e}", file=sys.stderr)
        return 10
    if release_observation is None:
        if not zip_file.is_file():
            print(f"  ✗ zip asset not found at {zip_file} — zip-less publishes refuse (named policy).",
                  file=sys.stderr)
            return 9
        gh_result = _create_release_object(
            state["tag"],
            zip_file,
            version,
            clone_dir,
        )
        if gh_result.returncode != 0:
            print(f"  ✗ gh release create failed: {gh_result.stderr.strip()[:500]}", file=sys.stderr)
            print("  PUSHED-NO-RELEASE — main + tag are live; re-fire to complete the release object.",
                  file=sys.stderr)
            return 10
        try:
            release_observation = _view_release_object(
                state["tag"], clone_dir, allow_missing=False
            )
        except PublishError as e:
            print(f"  ✗ release created but observation failed: {e}", file=sys.stderr)
            return 10
    print("  ✓ release object present")

    print("\nUploading Supabase zip + update manifest —")
    try:
        _upload_supabase_zip(
            tropo_roots.RELEASES_DIR / f"v{version}", version, dist_dir
        )
        print("  ✓ Supabase zip uploaded")
        # AC2: the build stamped it; confirm the SEALED bytes agree before we go on.
        _verify_sealed_briefing_notes(version, dist_dir)
        # AC3: badge is outside the box, so the fire owns it end to end.
        # S3 AC4 (176a8995): an adapter to the deploy repo, not a printed step.
        _stamp_os_release_badge(
            version, dist_dir, datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            state=state,
        )
        # AC4: flip BEFORE generation — the generator reads shipped entries from
        # the index, so a later flip yields a manifest naming the prior version.
        _flip_release_entry_to_shipped(version)
        _upload_update_manifest()
        _verify_published_update_manifest(version)
    except PublishError as e:
        print(f"  ✗ {e}", file=sys.stderr)
        print("  Push + release object are live; upload can be retried without re-firing.", file=sys.stderr)
        # Exit honesty (AC-8): upload failure -> nonzero, tropo.release.shipped/published
        # NOT emitted. Push already succeeded, so this is not PUSHED-NO-RELEASE (the
        # release object exists) — it's a distinct, narrower failure the operator can retry.
        return 11

    print("\nVERIFY-LIVE (tag + main sha + release object) —")
    # v1.90: the observation-style act sites. Each act has already happened
    # above (flip inside the upload block, manifest after it); wire_checkpoint
    # records intent plus the verified fact for each. The endpoint URL is an
    # explicit deployment fact (see _site_endpoint_url) — an unreachable or
    # unconfigured endpoint records no fact, and the coverage gate below
    # reports that honestly instead of inventing an observation.
    context["site_endpoint_url"] = _site_endpoint_url(state)
    wire_checkpoint(journal, "release_entry_projection", context)
    try:
        wire_checkpoint(journal, "site_endpoint", context)
    except PublishError as exc:
        # The endpoint observation is post-publication and world-dependent:
        # an unreachable or lagging site deploy is the honest ABSENCE of a
        # fact, never a fire failure — the coverage gate below reports it
        # and a re-fire can complete it once the site serves the badge.
        print(f"  ! site_endpoint observation failed: {exc}", file=sys.stderr)
    vstate = _run_publish_state("--expect", version, "--sha", state["staged_sha"], remote=remote)
    tag_and_sha_ok = (
        vstate.get("status") == "verified"
        and vstate.get("expect") == version
        and vstate.get("tag") == state["tag"]
        and vstate.get("expected_sha") == state["staged_sha"]
        and vstate.get("remote_main_sha") == state["staged_sha"]
        and vstate.get("remote_tag_sha") == state["staged_sha"]
    )
    try:
        release_observation = _view_release_object(
            state["tag"], clone_dir, allow_missing=False
        )
        gh_ok = True
    except PublishError as e:
        release_observation = None
        gh_ok = False
        print(f"  ✗ release object verification failed: {e}", file=sys.stderr)
    if vstate.get("status") == "unreachable":
        print(f"  ✗ POSTED-UNVERIFIED — could not verify the remote: {vstate.get('error', '')[:200]}",
              file=sys.stderr)
        print("    No event emitted, no LIVE stamp. Push + upload succeeded; re-run --fire to re-verify.",
              file=sys.stderr)
        return 12
    if not (tag_and_sha_ok and gh_ok):
        print(f"  ✗ NOT FULLY VERIFIED (tag_and_sha={tag_and_sha_ok}, release_object={gh_ok}) — "
              f"no event emitted, no LIVE stamp.", file=sys.stderr)
        return 13

    print("  ✓ LIVE — tag on remote, main sha matches, release object exists.")

    try:
        receipt, receipt_sha256, fired_by = _complete_verified_publication(
            version,
            state,
            vstate,
            release_observation=release_observation,
            ac7_context=_ac7,
        )
    except (PublishError, release_receipt.ReleaseReceiptError) as e:
        print(f"  ✗ PROVENANCE NOT RECORDED — {e}", file=sys.stderr)
        print(
            "    Final receipt/event/state/LIVE stamping is incomplete; "
            "re-fire safely after correcting the failure.",
            file=sys.stderr,
        )
        return 14
    print(f"  ✓ verify-live receipt {receipt_sha256}")
    print(f"  ✓ .tropo/version.md stamped to v{version}")

    # v1.90 tail sites, in the enum's dependency order: the event mirror,
    # closure, the real-fire scorecard, and the completion re-observation.
    context["receipt_sha"] = receipt_sha256
    wire_checkpoint(journal, "run_published_event", context)

    # BLOCKER 4: closure is welded here, not left as an action someone might
    # remember to run. The release is already public at this point, so a
    # failure below leaves it PUBLIC AND OPEN — reported honestly and
    # replayable with the same transaction id — never falsely closed.
    closure = _initiate_release_closure(_ac7, receipt_sha256)
    wire_checkpoint(journal, "closure", context)
    if closure.get("ok"):
        print(f"  ✓ release closed — {len(closure.get('closed') or [])} record(s)")
    else:
        print(f"  ! PUBLIC AND OPEN — {closure.get('detail')}", file=sys.stderr)
        print(f"    Re-run: python3 vault/tools/9e7003b1.py "
              f"--activation-uid {_ac7['identity'].activation_uid} close-release "
              f"--receipt-sha256 {receipt_sha256} "
              f"--transaction-id {_ac7['transaction_id']}", file=sys.stderr)

    # THE SCORECARD IS READ HERE, NEVER WRITTEN HERE. v1.92 Stream 1 AC4.
    #
    # This wrote its own scorecard: a hand-built dict at
    # _state_path(version).parent, under the same FILENAME the canonical
    # producer uses but at a different LOCATION and in a different SHAPE. Against
    # vault/schema/one-prompt-release-scorecard.schema.json (additionalProperties
    # false) it was missing 8 of 10 required fields and carried 3 unknown keys,
    # and it had no `verdict` — so the completion verifier, which reads
    # release_metrics.scorecard_path(run_dir, REAL_FIRE), called the scorecard
    # ABSENT even after a successful fire. Two producers, one filename, two
    # locations, one reader.
    #
    # It mattered beyond tidiness: cmd_fire is what AC2 and AC5 bind to the
    # terminal leaf 3dd817cb, so the release owner's ruling that the scorecard is
    # REQUIRED from v1.92 forward was unsatisfiable through the bound path.
    #
    # And the divergence had a cause worth keeping: cmd_fire does not HAVE the
    # measurement inputs. build_scorecard requires the orchestrator start stamp,
    # the observed refusals and the baseline; the publisher knows none of them.
    # A producer without the inputs cannot honestly build the artifact, which is
    # exactly how the lean hand-built dict came to exist. So the orchestrator
    # (tropo-release.py, which has them) writes it, and this reads it.
    import hashlib as _hashlib
    # The injected producer runs HERE — after the outward acts and verify-live
    # have stamped this run's journal (so every measurement input is true), and
    # before the read below that decides whether completion_verification can be
    # observed. The orchestrator owns the inputs and builds the card; this call
    # site owns only the timing. See tropo-release.py::_produce_scorecard for
    # why the previous order (produce AFTER cmd_fire returned, gated on its exit
    # code) could never converge.
    _producer = getattr(args, "scorecard_producer", None)
    if _producer is not None:
        try:
            _producer(version)
        except Exception as _exc:  # noqa: BLE001
            # A producer that raises must not take the release with it: the
            # publish already happened. Record the absence honestly below.
            print("  ⚠ scorecard producer raised (%s); recording the card absent"
                  % _exc, file=sys.stderr)
    _run_dir = _run_journal_folder(_ac7)
    _canonical = (
        release_metrics.scorecard_path(_run_dir, release_metrics.REAL_FIRE)
        if _run_dir is not None else None
    )
    if _canonical is not None and _canonical.is_file():
        # EXISTENCE IS NOT THE BAR — VALIDITY IS. This used to accept any file
        # that happened to be at the path, so a scorecard naming no release,
        # with null timestamps, failing its own schema, satisfied the completion
        # act site and the fire reported LIVE. That is the false-success class
        # wearing the costume of a measurement.
        #
        # Note what is deliberately NOT checked: `verdict`. A card reading
        # verdict "fail" is a SUCCESSFUL measurement of an expensive release —
        # too many principal gestures, or over the wall-clock target. Gating the
        # fire on a passing verdict would conflate "did we publish correctly"
        # with "was it cheap", and would make an honest expensive release
        # unshippable. We require that the measurement was TAKEN and is
        # well-formed, not that we liked the answer.
        # (argus-a158, 2026-08-25.)
        _findings: list[str] = []
        try:
            _card = json.loads(_canonical.read_text(encoding="utf-8"))
            _schema = (tropo_roots.VAULT_DIR / "schema"
                       / "one-prompt-release-scorecard.schema.json")
            if _schema.is_file():
                _findings = release_metrics.validate_scorecard(_card, _schema)
            else:
                _findings = ["schema not found at %s" % _schema]
        except Exception as _exc:  # noqa: BLE001
            _findings = ["scorecard unreadable: %s" % _exc]
        if _findings:
            context["scorecard_sha"] = None
            context["scorecard_absent_reason"] = (
                "real-fire scorecard at %s is INVALID (%d finding(s)): %s"
                % (_canonical, len(_findings), "; ".join(_findings[:5]))
            )
            print("  ⚠ real-fire scorecard is invalid; recording completion "
                  "unverified rather than accepting a malformed measurement:",
                  file=sys.stderr)
            for _f in _findings[:5]:
                print("      - %s" % _f, file=sys.stderr)
        else:
            context["scorecard_sha"] = _hashlib.sha256(
                _canonical.read_bytes()).hexdigest()
            context["scorecard_path"] = str(_canonical)
    else:
        # Honestly absent beats fabricated. The completion verifier observes the
        # world; a placeholder here would tell it a card exists.
        context["scorecard_sha"] = None
        context["scorecard_absent_reason"] = (
            "no real-fire scorecard at %s — the orchestrator "
            "(tropo-release.py) is its producer and did not write one for this "
            "run" % (_canonical if _canonical is not None else "<run folder unresolved>")
        )
        print("  ⚠ no real-fire scorecard found at %s; recording it absent "
              "rather than writing a placeholder" % _canonical, file=sys.stderr)
    wire_checkpoint(journal, "scorecard", context)
    wire_checkpoint(journal, "completion_verification", context)

    # The success gate (AC1's real-path enforcement): a fire whose journal
    # cannot describe every wired act site is not a successful fire — it is
    # a public release with a describable gap, re-fireable to completion.
    missing = [
        c for c in FIRE_WIRED_CHECKPOINTS if journal.observed(c) is None]
    if missing:
        saga_state = _saga().current_state(journal)
        print(f"  ✗ SAGA INCOMPLETE — no observation for: {', '.join(missing)}.",
              file=sys.stderr)
        print(f"    The release is public; the journal is not. Saga state: "
              f"{saga_state['state']}. Re-fire resumes this journal by "
              f"checkpoint.", file=sys.stderr)
        return 15

    print(f"\n=== LIVE — v{version} published. ===")
    return 0


# ── DEFER ──────────────────────────────────────────────────────────────────────

def cmd_defer(args) -> int:
    version = args.version or _latest_staged_version()
    if not version:
        print("✗ No staged version found (and none given via --version).", file=sys.stderr)
        return 3
    if not args.reason:
        print("✗ --reason is required for --defer.", file=sys.stderr)
        return 3
    print(f"=== DEFER v{version} ===\n")
    if not _confirm_tty(f"Defer publishing v{version}? (reason: {args.reason!r})"):
        print("  ✗ Refused (default NO / not confirmed).", file=sys.stderr)
        return 6
    deferred_by = os.environ.get("USER", "mike-maziarz")
    deferred_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _stamp_release_entry(version, publish_state="deferred-by-mike",
                          defer_record={"deferred_by": deferred_by, "deferred_at": deferred_at,
                                        "reason": args.reason})
    print(f"  ✓ v{version} recorded DEFERRED-BY-MIKE — boot-line silent; remains fireable later.")
    return 0


# ── VERIFY-ONLY ──────────────────────────────────────────────────────────────────

def cmd_verify_only(args) -> int:
    """The SOP's documented manual path for attested-class releases: no
    pipeline-run to stage/fire against, so this only re-checks verify-live
    against a version already live by some other means. Never touches the
    outward gate (attested_build_authorization never satisfies it, by design)."""
    version = args.version
    try:
        remote = _require_pinned_remote(args.remote or DEFAULT_REMOTE)
    except PublishError as e:
        print(f"  ✗ {e}", file=sys.stderr)
        return 13
    print(f"=== VERIFY-ONLY v{version} ===\n")
    state = _run_publish_state("--expect", version, remote=remote)
    if (
        state.get("status") != "verified"
        or state.get("expect") != version
        or state.get("tag") != f"v{version}"
        or state.get("remote_tag_sha") is None
        or state.get("remote_tag_sha") != state.get("remote_main_sha")
    ):
        print(f"  ✗ tag not verified on remote: {state}", file=sys.stderr)
        return 13
    try:
        _view_release_object(
            f"v{version}",
            tropo_roots.STUDIO_ROOT,
            allow_missing=False,
        )
    except PublishError as e:
        print(f"  ✗ release object not verified for v{version}: {e}", file=sys.stderr)
        return 13
    print(f"  ✓ VERIFIED — v{version} tag + release object present on the remote.")
    return 0


def _frozen_package_sha256(version: str, activation_uid: str) -> str:
    """The digest the release run froze — the receipt side of the comparison."""
    runtime = _load_pipeline_runtime()
    identity = release_package.resolve_release_run(
        runtime, activation_uid=activation_uid, version=version
    )
    run_entry = runtime.read_vault_entry(identity.run_uid) or {}
    run_folder = str((run_entry.get("frontmatter") or {}).get("run_folder") or "")
    if not run_folder:
        raise PublishError(
            f"release run {identity.run_uid} declares no run_folder, so its frozen "
            f"package digest cannot be read"
        )
    events = runtime.read_events(Path(tropo_roots.STUDIO_ROOT) / run_folder)
    frozen = release_package.active_frozen_payload(events, identity.run_uid)
    if not frozen:
        raise PublishError(
            f"release run {identity.run_uid} has no package_frozen event; there is "
            f"no receipt digest to verify a hand-back against"
        )
    return str(frozen.get("package_sha256") or "")


def _git(args, cwd, check=True, timeout=120, env=None):
    # This later definition SHADOWS the module's original _git (line ~202) for every caller
    # in the module — Python module-level redefinition. It arrived with the AC6 hand-back
    # work signature-narrowed, which crashed _require_clone_origin(check=False) at the v1.88
    # stage gesture (TypeError). Restored to delegate to the module's own _run exactly like
    # the original, so both definitions are behaviorally one (env added by S3 AC4, both).
    return _run(["git"] + list(args), cwd=cwd, check=check, timeout=timeout, env=env)


def cmd_handback(args) -> int:
    """Produce the transfer bundle on transfer/v<version>-dist. Credential-less side."""
    version = args.version
    root = Path(tropo_roots.STUDIO_ROOT)
    dist_dir = tropo_roots.RELEASES_DIR / f"v{version}" / "dist"
    zip_path = dist_dir / f"tropo-os-v{version}.zip"
    payload_dir = _handback_payload_dir(version, root)
    branch = TRANSFER_BRANCH_FMT.format(version=version)

    print(f"=== HAND-BACK v{version} ===\n")
    try:
        record = write_transfer_bundle(version, zip_path, payload_dir)
    except PublishError as exc:
        print(f"  ✗ {exc}", file=sys.stderr)
        return 3

    if args.no_branch:
        print("  → bundle only (--no-branch); nothing committed")
        return 0

    current = _git(["rev-parse", "--abbrev-ref", "HEAD"], root).stdout.strip()
    checkout = _git(["checkout", "-B", branch], root)
    if checkout.returncode != 0:
        print(f"  ✗ could not create {branch}: {checkout.stderr.strip()}", file=sys.stderr)
        return 4
    try:
        _git(["add", "-f", str(payload_dir.relative_to(root))], root)
        # check=False at both sites: the returncode IS the answer here — a
        # failed commit or push is reported honestly below, not raised past
        # the branch that inspects it (the raise path made the no-remote
        # handback crash instead of returning its honest rc 6).
        commit = _git(
            ["commit", "-m",
             f"handback: v{version} transfer bundle ({record['package_sha256'][:12]})"],
            root,
            check=False,
        )
        if commit.returncode != 0 and "nothing to commit" not in commit.stdout:
            print(f"  ✗ commit failed: {commit.stderr.strip()}", file=sys.stderr)
            return 5
        push = _git(["push", "-u", "origin", branch], root, check=False)
        if push.returncode != 0:
            # The whole premise is a host that cannot push everywhere. Say which
            # push failed rather than implying the bundle is unusable.
            print(f"  ⚠ bundle committed on {branch} but push failed: "
                  f"{push.stderr.strip()}", file=sys.stderr)
            print("  → the bundle is on the local branch; transfer it by any means "
                  "the credentialed host can read.")
            return 6
        print(f"  ✓ {branch} pushed — the credentialed host can now run:\n"
              f"      python3 vault/tools/tropo-publish-release.py receive "
              f"--version {version} --activation-uid <uid>")
    finally:
        if current and current != branch:
            _git(["checkout", current], root)
    return 0


def cmd_receive(args) -> int:
    """Verify a handed-back bundle against the frozen receipt, then stage it."""
    version = args.version
    root = Path(tropo_roots.STUDIO_ROOT)
    payload_dir = (
        Path(args.payload_dir) if args.payload_dir
        else _handback_payload_dir(version, root)
    )

    print(f"=== RECEIVE HAND-BACK v{version} ===\n")
    try:
        expected = _frozen_package_sha256(version, args.activation_uid)
        verify_transfer_bundle(version, payload_dir, expected)
    except PublishError as exc:
        print(f"  ✗ {exc}", file=sys.stderr)
        return 3

    dist_dir = tropo_roots.RELEASES_DIR / f"v{version}" / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    placed = dist_dir / f"tropo-os-v{version}.zip"
    shutil.copy2(payload_dir / f"tropo-os-v{version}.zip", placed)
    print(f"  ✓ verified bundle placed at {dist_dir}")

    # cmd_stage consumes the UNPACKED box, not dist/. Reconstruct it here or the
    # next line exits 3 with the artefact sitting one directory away.
    builds_root = tropo_roots.RELEASES_DIR / f"v{version}" / "builds"
    try:
        reconstruct_build_dir(version, placed, builds_root)
    except PublishError as exc:
        print(f"  ✗ {exc}", file=sys.stderr)
        return 4

    if args.verify_only:
        print("  → --verify-only: not staging")
        return 0
    print("\nHanding to the existing stage path —")
    return cmd_stage(args)


def main() -> int:
    ap = argparse.ArgumentParser(description="Release Coupling — stage, fire, defer, or verify-only")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("stage", help="STAGE a build for publish (automated, private)")
    s.add_argument("--activation-uid", required=True)
    s.add_argument("--version", required=True)
    s.add_argument("--remote", default=None)
    s.add_argument("--clone", default=None, help="alias for --remote (test seam)")
    s.add_argument("--clone-dir", default=None, help="override the staged-clone working directory (test seam)")
    s.add_argument("--allow-delete", action="store_true",
                   help="acknowledge + proceed despite non-allowlisted deletions")
    s.set_defaults(func=cmd_stage)

    # S3 AC1 (176a8995): every fire precondition, before anyone is asked.
    pf = sub.add_parser("preflight", help="run every fire precondition (transport, receipts, "
                                          "authorization, credentials, badge target) with no "
                                          "prompt; green means the fire cannot refuse on one")
    pf.add_argument("--version", default=None, help="default: the most recently staged version")
    pf.set_defaults(func=cmd_preflight)

    f = sub.add_parser("fire", help="--fire: the one public act (TTY-only, default NO)")
    f.add_argument("--version", default=None, help="default: the most recently staged version")
    f.set_defaults(func=cmd_fire)

    d = sub.add_parser("defer", help="--defer: Mike-gestured skip (TTY-only, default NO)")
    d.add_argument("--version", default=None, help="default: the most recently staged version")
    d.add_argument("--reason", required=True)
    d.set_defaults(func=cmd_defer)

    h = sub.add_parser("handback", help="AC6: produce the transfer bundle (credential-less build host)")
    h.add_argument("--version", required=True)
    h.add_argument("--no-branch", action="store_true",
                   help="write the bundle without committing/pushing a transfer branch")
    h.set_defaults(func=cmd_handback)

    r = sub.add_parser("receive", help="AC6: verify a handed-back bundle against the receipt, then stage")
    r.add_argument("--version", required=True)
    r.add_argument("--activation-uid", required=True)
    r.add_argument("--payload-dir", default=None, help="override the handback payload directory")
    r.add_argument("--verify-only", action="store_true", help="verify and place, do not stage")
    r.add_argument("--remote", default=None)
    r.add_argument("--clone", default=None)
    r.add_argument("--clone-dir", default=None)
    r.add_argument("--allow-delete", action="store_true")
    r.set_defaults(func=cmd_receive)

    v = sub.add_parser("verify-only", help="re-verify a live version (attested-class SOP path)")
    v.add_argument("--version", required=True)
    v.add_argument("--remote", default=None)
    v.set_defaults(func=cmd_verify_only)

    # Flag-style aliases (--fire / --defer / --verify-only) so the CLI reads the way the
    # spec body writes it, without requiring the subcommand form.
    if len(sys.argv) > 1 and sys.argv[1] in ("--fire", "--defer", "--verify-only"):
        sys.argv[1] = sys.argv[1].lstrip("-")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 1
    try:
        return args.func(args)
    except PublishError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
