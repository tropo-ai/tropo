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

  --fire (gesture 2 -- TTY-only, default NO):
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

def _run(cmd, cwd=None, check=True, timeout=120):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise PublishError(f"{' '.join(str(c) for c in cmd)} failed (exit {result.returncode}): "
                            f"{result.stderr.strip()[:500]}")
    return result


def _git(args, cwd, check=True, timeout=120):
    return _run(["git"] + args, cwd=cwd, check=check, timeout=timeout)


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


def _stamp_os_release_badge(version: str, dist_dir: Path, released_at: str) -> None:
    """AC3 (cb194126): the website badge, stamped from the artifact that shipped.

    Unlike the briefing notes this is genuinely fire-time — os-release.json lives
    outside the box and feeds the website, so nothing about it is sealed. It was
    SIX releases stale on the night v1.87 shipped (badge said v1.80), because it
    was a hand-maintained surface with no gate.

    sizeBytes is measured off the real zip rather than copied from a receipt
    field: the badge's job is to describe the download a visitor is about to
    start, so it should be derived from the bytes that download serves.
    """
    zip_path = dist_dir / f"tropo-os-v{version}.zip"
    if not zip_path.is_file():
        raise PublishError(
            f"cannot stamp {OS_RELEASE_REL}: no package at {zip_path} to measure. "
            f"The badge reports the size of a real download."
        )
    badge_path = Path(tropo_roots.STUDIO_ROOT) / OS_RELEASE_REL
    if not badge_path.is_file():
        raise PublishError(
            f"cannot stamp {OS_RELEASE_REL}: file not found at {badge_path}. The "
            f"website badge is a shipped-state surface and must exist to be stamped."
        )
    try:
        badge = json.loads(badge_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"{OS_RELEASE_REL} is not readable/parseable: {exc}") from exc

    size_bytes = zip_path.stat().st_size
    badge.update({
        "version": f"v{version}",
        "fileSize": _human_size(size_bytes),
        "sizeBytes": size_bytes,
        "releasedAt": released_at,
    })
    try:
        badge_path.write_text(json.dumps(badge, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise PublishError(f"{OS_RELEASE_REL} could not be written: {exc}") from exc
    print(f"  ✓ Website badge stamped v{version} ({_human_size(size_bytes)}, "
          f"{size_bytes} bytes)")
    # The site split is a separate deploy this tool does not own. Naming the exact
    # command keeps the manual step explicit instead of leaving the badge stamped
    # in the studio and stale on the website — which is the same
    # correct-here-wrong-there shape the briefing notes had.
    print(f"  → NEXT (manual): publish the site split so the website serves the new "
          f"badge:\n      cd tropo-app && npm run deploy   # serves {OS_RELEASE_REL}")


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
    hand-merge here."""
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
    receipts = [
        receipt for receipt in receipts
        if str(receipt.get("package_sha256") or "") == package_sha256
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


def cmd_fire(args) -> int:
    version = args.version or _latest_staged_version()
    if not version:
        print("✗ No staged version found (and none given via --version). Run stage first.", file=sys.stderr)
        return 3
    state = _read_state(version)
    if not state:
        print(f"✗ No publish-state for v{version} — not staged. Run stage first.", file=sys.stderr)
        return 3
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

    print("\nRestoring push URL for the one push —")
    _git(["remote", "set-url", "--push", "origin", remote], cwd=str(clone_dir))
    try:
        _git(["push", "origin", "HEAD:main"], cwd=str(clone_dir))
        _git(["push", "origin", state["tag"], "--force"], cwd=str(clone_dir))
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
        _stamp_os_release_badge(
            version, dist_dir, datetime.now(timezone.utc).strftime("%Y-%m-%d")
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

    # BLOCKER 4: closure is welded here, not left as an action someone might
    # remember to run. The release is already public at this point, so a
    # failure below leaves it PUBLIC AND OPEN — reported honestly and
    # replayable with the same transaction id — never falsely closed.
    closure = _initiate_release_closure(_ac7, receipt_sha256)
    if closure.get("ok"):
        print(f"  ✓ release closed — {len(closure.get('closed') or [])} record(s)")
    else:
        print(f"  ! PUBLIC AND OPEN — {closure.get('detail')}", file=sys.stderr)
        print(f"    Re-run: python3 vault/tools/9e7003b1.py "
              f"--activation-uid {_ac7['identity'].activation_uid} close-release "
              f"--receipt-sha256 {receipt_sha256} "
              f"--transaction-id {_ac7['transaction_id']}", file=sys.stderr)

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


def _git(args, cwd, check=True, timeout=120):
    # This later definition SHADOWS the module's original _git (line ~202) for every caller
    # in the module — Python module-level redefinition. It arrived with the AC6 hand-back
    # work signature-narrowed, which crashed _require_clone_origin(check=False) at the v1.88
    # stage gesture (TypeError). Restored to delegate to the module's own _run exactly like
    # the original, so both definitions are behaviorally one.
    return _run(["git"] + list(args), cwd=cwd, check=check, timeout=timeout)


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
        commit = _git(
            ["commit", "-m",
             f"handback: v{version} transfer bundle ({record['package_sha256'][:12]})"],
            root,
        )
        if commit.returncode != 0 and "nothing to commit" not in commit.stdout:
            print(f"  ✗ commit failed: {commit.stderr.strip()}", file=sys.stderr)
            return 5
        push = _git(["push", "-u", "origin", branch], root)
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
