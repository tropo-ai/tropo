"""lib/governance_gate.py — the D3b governance-validator GATE client (D5 P6).

Dev-spec 396d88a4 (GitHub.com enforcement transport, Phase T) + cycle brief
304badf7 D3a/D3b. Test-spec 0f06a8b5 assertion P6.

WHAT THIS IS
  The client + defence-in-depth wiring for the governance-validator gate that
  keeps a BROKEN governed file off the canonical ref. On github.com the gate is
  a REQUIRED GitHub Action (unbypassable onto main) running the hardened
  validator `vault/tools/federation/tropo_validate_governed.py`; the local
  pre-commit hook is best-effort defence-in-depth. This module:
    - `validate_paths`   — run the validator over files; raise GovernanceBlocked
                           on any BROKEN file (the gate's decision, exit 1).
    - `install_hook`     — install the pre-commit hook into a repo.
    - `assert_hook_installed` — DETECT + REFUSE a missing/wrong hook (the P6
                           "absence is detected + refused, not silently skipped"
                           requirement).

  "UNBYPASSABLE ONTO MAIN, BEST-EFFORT LOCALLY" (304badf7 D3a): the LOCAL hook
  can be removed, so it is not the trust anchor — the REQUIRED Action on the
  protected repo is. Wiring that required Action + branch-protection on the
  disposable protected repo is the github.com-only proof, flagged as a
  credential/repo prerequisite; the validator LOGIC + hook mechanics are proven
  here against the real validator CLI.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable

# The hardened D3b validator (reconstructed + re-verified, 304badf7 §4).
VALIDATOR = Path(__file__).resolve().parents[1] / "federation" / "tropo_validate_governed.py"

# Governed content the gate covers (single-doc governed markdown under files/).
GOVERNED_GLOBS = ("files/*.md", "vault/files/*.md", "teams/*/files/*.md")

_HOOK_MARKER = "tropo-governance-gate"


class GovernanceError(Exception):
    """Base class for gate refusals."""


class GovernanceBlocked(GovernanceError):
    """The validator ruled at least one governed file BROKEN (gate exit 1)."""

    def __init__(self, results: list[tuple[str, str, list[str]]]):
        self.results = results
        broken = [r for r in results if r[1] != "VALID"]
        detail = "; ".join(f"{p}: {status} ({', '.join(probs)})" for p, status, probs in broken)
        super().__init__(f"governance gate BLOCKED {len(broken)} file(s): {detail}")


class GateNotInstalled(GovernanceError):
    """The pre-commit hook is missing or does not invoke the gate — refused, NOT
    silently skipped (P6)."""


def _validate_one(path: Path) -> tuple[str, list[str]]:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True, text=True,
    )
    # exit 0=VALID · 1=BROKEN · 2=NEEDS-RESOLUTION (tropo_validate_governed.py)
    status = {0: "VALID", 1: "BROKEN", 2: "NEEDS-RESOLUTION"}.get(proc.returncode, "BROKEN")
    problems = [ln.strip("- ").strip() for ln in proc.stdout.splitlines() if ln.strip().startswith("-")]
    return status, problems


def validate_paths(paths: Iterable[Path], *, raise_on_block: bool = True) -> list[tuple[str, str, list[str]]]:
    """Run the hardened validator over `paths`. Returns [(path, status,
    problems)]. With `raise_on_block` (the gate's posture), any non-VALID file
    raises GovernanceBlocked — the same decision the required Action makes."""
    results: list[tuple[str, str, list[str]]] = []
    for p in paths:
        p = Path(p)
        status, problems = _validate_one(p)
        results.append((str(p), status, problems))
    if raise_on_block and any(status != "VALID" for _, status, _ in results):
        raise GovernanceBlocked(results)
    return results


def hook_script() -> str:
    """The pre-commit hook body: validate every STAGED governed file, block the
    commit on any BROKEN file. Best-effort local defence-in-depth.

    `mapfile` deliberately avoided: it needs bash >= 4.0, and macOS ships
    bash 3.2 as `/bin/bash` (Apple froze it at the last GPLv2 release), so
    `#!/usr/bin/env bash` resolves to a `mapfile`-less shell on every default
    macOS clone unless the user has put a newer bash first in PATH. Under
    3.2 this failed with `mapfile: command not found` and NO commit was ever
    actually validated -- the hook existed, `assert_hook_installed` reported
    it present, and it silently did nothing on every commit: precisely the
    "installed but unreachable" failure class this whole spec exists to
    catch, just one layer further in than .gitattributes/git-config wiring.
    Found running AC6 against a real commit, not by reading the script.
    """
    return f"""#!/usr/bin/env bash
# {_HOOK_MARKER}: D3b governance-validator gate (defence-in-depth; the REQUIRED
# GitHub Action is the unbypassable anchor onto main).
set -euo pipefail
VALIDATOR="{VALIDATOR}"
staged=()
while IFS= read -r f; do
  staged+=("$f")
done < <(git diff --cached --name-only --diff-filter=ACM | grep -E '(^|/)files/.*\\.md$' || true)
if [ "${{#staged[@]}}" -eq 0 ]; then exit 0; fi
if ! python3 "$VALIDATOR" "${{staged[@]}}"; then
  echo "governance gate: refusing commit — a governed file is BROKEN" >&2
  exit 1
fi
"""


def hook_path(repo: Path) -> Path:
    return Path(repo) / ".git" / "hooks" / "pre-commit"


def install_hook(repo: Path) -> Path:
    """Install the pre-commit hook (defence-in-depth). Returns the hook path."""
    hp = hook_path(repo)
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(hook_script(), encoding="utf-8")
    hp.chmod(0o755)
    return hp


def assert_hook_installed(repo: Path) -> None:
    """DETECT + REFUSE a missing/wrong gate hook (P6: not silently skipped). A
    studio whose defence-in-depth hook is absent must be refused, so a missing
    hook cannot let raw markers reach the shared graph unnoticed."""
    hp = hook_path(repo)
    if not hp.is_file():
        raise GateNotInstalled(
            f"pre-commit governance gate is NOT installed at {hp} — refused "
            f"(the local defence-in-depth hook must be present, not silently skipped)"
        )
    if _HOOK_MARKER not in hp.read_text(encoding="utf-8"):
        raise GateNotInstalled(
            f"pre-commit hook at {hp} does not invoke the governance gate "
            f"(missing marker {_HOOK_MARKER!r}) — refused"
        )


# --------------------------------------------------------------------------- #
# v1.94 Stream 2 (266edea6): the merge driver goes from built-and-green to
# wired. Two independent halves, the SAME shape as the navblock filter's
# (vault/tools/tropo-navblock-strip.py --install /
# tropo-validate.py::check_navblock_git_filter_installed): `.gitattributes`
# alone never carries the actual driver COMMAND -- the local, never-committed
# `.git/config` is a second, separate install step every clone needs. Neither
# precedent is duplicated; this mirrors their shape for the merge driver.

MERGE_SCRIPT = Path(__file__).resolve().parents[1] / "federation" / "tropo_merge.py"
MERGE_DRIVER_NAME = "tropo"
MERGE_DRIVER_ATTR = f"merge={MERGE_DRIVER_NAME}"

# The governed paths the driver handles (266edea6 committed_substrate: "merge-
# attributes-wiring"). One entry, matching the identity layer's governed home.
MERGE_GOVERNED_PATTERN = "vault/files/*.md"


def merge_driver_command() -> str:
    return f"python3 {MERGE_SCRIPT} %O %A %B %P"


def install_merge_driver(repo: Path) -> None:
    """Wire the LOCAL half: `git config merge.tropo.driver`. Per-clone, never
    committed -- the same gap the navblock filter has, and for the same
    reason (git config is never a tracked file)."""
    subprocess.run(
        ["git", "config", f"merge.{MERGE_DRIVER_NAME}.driver", merge_driver_command()],
        cwd=str(repo), check=True, capture_output=True, text=True,
    )


def merge_driver_configured(repo: Path) -> bool:
    r = subprocess.run(
        ["git", "config", "--get", f"merge.{MERGE_DRIVER_NAME}.driver"],
        cwd=str(repo), capture_output=True, text=True,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


def gitattributes_declares_merge_tropo(repo: Path, pattern: str = MERGE_GOVERNED_PATTERN) -> bool:
    """Wire the COMMITTED half: does `.gitattributes` declare `<pattern>
    merge=tropo`? Mirrors check_navblock_git_filter_installed's own
    line-by-line, tokenised read (never a raw substring scan, which a
    comment mentioning both words would false-positive)."""
    ga = Path(repo) / ".gitattributes"
    if not ga.is_file():
        return False
    for line in ga.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] == pattern and MERGE_DRIVER_ATTR in parts[1:]:
            return True
    return False


def install_merge_attributes(repo: Path, pattern: str = MERGE_GOVERNED_PATTERN) -> None:
    """Wire the COMMITTED half for a fresh repo/fixture: append the
    `<pattern> merge=tropo` declaration to `.gitattributes` if not already
    present. Idempotent."""
    if gitattributes_declares_merge_tropo(repo, pattern):
        return
    ga = Path(repo) / ".gitattributes"
    line = f"{pattern} {MERGE_DRIVER_ATTR}\n"
    with ga.open("a", encoding="utf-8") as f:
        if ga.stat().st_size and not line.startswith("\n"):
            f.write("\n" if not _ends_with_newline(ga) else "")
        f.write(line)


def _ends_with_newline(path: Path) -> bool:
    data = path.read_bytes()
    return not data or data.endswith(b"\n")


def unconfigured_driver_warning(repo: Path) -> "list[str]":
    """AC7: `.gitattributes` declares merge=tropo but this clone has not
    configured the driver -- git's own behaviour in that state is a SILENT
    fall-back to its default merge (no error, no warning), which is exactly
    the failure class this whole spec exists to end. Returns a named warning
    (empty list = nothing to warn about: either not declared, or configured)."""
    if not gitattributes_declares_merge_tropo(repo):
        return []
    if merge_driver_configured(repo):
        return []
    return [
        f"merge={MERGE_DRIVER_NAME} is declared in .gitattributes for "
        f"{MERGE_GOVERNED_PATTERN}, but this clone has not configured "
        f"merge.{MERGE_DRIVER_NAME}.driver -- git will silently fall back to "
        f"its default line merge on a governed-file conflict. Run "
        f"governance_gate.install_merge_driver(repo), or "
        f"`git config merge.{MERGE_DRIVER_NAME}.driver \"{merge_driver_command()}\"`."
    ]


def _unmerged_stages(repo: Path, relative_path: str) -> dict:
    """The raw `git ls-files -u` stage map for one path: {1: base_blob,
    2: ours_blob, 3: theirs_blob}, missing keys meaning that side has no
    blob (deleted, or never existed). Empty dict when the path carries no
    unmerged stage at all (clean, or not touched by the in-progress merge).
    Shared by both detection and resolution so the two can never disagree
    about what git itself reports."""
    ls = subprocess.run(
        ["git", "ls-files", "-u", "--", relative_path],
        cwd=str(repo), capture_output=True, text=True, check=True,
    )
    stages: dict = {}
    for line in ls.stdout.splitlines():
        # "<mode> <blob> <stage>\t<path>"
        meta, _, _ = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3:
            stages[int(parts[2])] = parts[1]
    return stages


def detect_delete_change_race(repo: Path, relative_path: str) -> "str | None":
    """AC5: DETECT a modify/delete conflict without touching anything --
    read-only, the first half of "detected and surfaced." A class git's
    content-merge machinery (custom drivers included) never even sees,
    because there is no common 3-way content case to hand a driver: a
    modify/delete conflict never reaches `merge.tropo.driver` (proven by
    talos-t58, real two-clone exercise, 2026-09-02), so detection can never
    be the driver's job and must read the unmerged stages directly.

    Returns "ours-deleted" (stage 2 absent, stage 3 present -- our side
    deleted it, theirs edited it), "theirs-deleted" (the mirror), or None
    when this path is not in that specific race (clean, a true two-sided
    content conflict with both stage 2 AND 3 present, or both sides deleted
    it -- an agreed deletion is not a race)."""
    stages = _unmerged_stages(repo, relative_path)
    if not stages or 1 not in stages:
        return None
    has_ours, has_theirs = 2 in stages, 3 in stages
    if has_ours and has_theirs:
        return None  # both sides edited -- the driver's own class, not this one
    if has_ours and not has_theirs:
        return "theirs-deleted"
    if has_theirs and not has_ours:
        return "ours-deleted"
    return None  # both sides deleted -- agreement, not a race


def emit_delete_change_race_event(
    vault_root: Path,
    *,
    record_uid: str,
    owner_party_uid: str,
    deleted_by: str,
    stream_uid: str = "b6merge0001",
) -> Path:
    """AC5: the NAMED signal half of "detected and surfaced" -- a distinct
    event type from AC4's `conflict_routed` (a driver-resolved field clash),
    because this class was never resolved by the driver and must never read
    as if it had been. Same on-disk CloudEvents shape as `emit_conflict_event`
    so both land on one bus the same way; `deleted_by` names which side
    ("ours-deleted" / "theirs-deleted") per `detect_delete_change_race`."""
    import json
    import uuid  # noqa: F401 -- kept for parity with emit_conflict_event's imports
    from datetime import datetime, timezone

    streams = Path(vault_root) / "vault" / "events" / "streams"
    streams.mkdir(parents=True, exist_ok=True)
    path = streams / f"{stream_uid}.jsonl"
    existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    seq = len(existing) + 1
    event = {
        "specversion": "1.0",
        "type": "tropo.governance.delete_change_race",
        "source": "/tools/governance-gate",
        "source_uid": stream_uid,
        "time": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "lifecycle": "evergreen",
        "subject": owner_party_uid,
        "data": {
            "record_uid": record_uid,
            "owner_party_uid": owner_party_uid,
            "deleted_by": deleted_by,
        },
        "id": f"evt_{stream_uid}_{seq:08d}",
        "event_uid": f"evt_{stream_uid}_{seq:08d}",
        "writer_instance_uid": stream_uid,
        "stream_uid": stream_uid,
        "local_seq": seq,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    return path


def resolve_delete_change_conflict(repo: Path, relative_path: str) -> bool:
    """A modify/delete conflict, ALREADY DETECTED AND SURFACED by
    `detect_delete_change_race` -- this is the separate, optional next step
    of actually clearing the unmerged stage, never a substitute for the
    signal above. AC5 itself is satisfied by detection + signal alone (Mike-
    ruled 2026-09-02, aa245696f): whether to also auto-resolve is an
    operational choice this function makes available, not something the
    locked criterion asserts.

    The studio's rule, symmetric with the driver's own field-level
    philosophy (a delete never silently wins over a change -- see
    tropo_merge.py's README table, "delete required field vs change ->
    BROKEN, gate catches the dropped field"): the EDIT wins, never the
    delete. Whichever side still has the file, keep it and stage it;
    resolution is then observable the same way any other resolved conflict
    is -- the index no longer carries unmerged stages for the path.

    Returns True if a resolution was made (an edit side existed to keep, or
    both sides agreed to delete), False if the path was not in an unmerged
    delete/modify state at all.
    """
    stages = _unmerged_stages(repo, relative_path)
    if not stages or 1 not in stages:
        return False  # not an unmerged delete/modify case (or no base stage)
    surviving_stage = 3 if 3 in stages else (2 if 2 in stages else None)
    if surviving_stage is None:
        # both sides deleted it -- nothing to keep; leave the delete resolved
        # by removing it from the index, never a claim this function makes
        # silently by falling through.
        subprocess.run(["git", "rm", "-f", "--", relative_path],
                        cwd=str(repo), check=True, capture_output=True, text=True)
        return True
    full = Path(repo) / relative_path
    blob = subprocess.run(
        ["git", "cat-file", "-p", stages[surviving_stage]],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout
    full.write_text(blob, encoding="utf-8")
    subprocess.run(["git", "add", "--", relative_path],
                    cwd=str(repo), check=True, capture_output=True, text=True)
    return True


def emit_conflict_event(
    vault_root: Path,
    *,
    record_uid: str,
    owner_party_uid: str,
    resolver: str,
    stream_uid: str = "b6merge0001",
) -> Path:
    """AC4: a governed-file conflict resolution leaves a trace on the bus --
    a merge nobody can audit is the state this seam exists to end. Per
    7191d685 (names for humans, UIDs for records), the event carries the
    RECORD uid and the OWNER's party uid, never a label alone.

    Writes one CloudEvents-shaped line directly to
    `<vault_root>/vault/events/streams/<stream_uid>.jsonl` -- the same
    on-disk shape `tropo-emit-event.py` produces, at the primitive level a
    throwaway test clone can exercise without a real studio's type registry
    or SQLite projection (both of which are the real tool's job when this
    runs inside an actual studio, not a merge fixture's)."""
    import json
    import uuid
    from datetime import datetime, timezone

    streams = Path(vault_root) / "vault" / "events" / "streams"
    streams.mkdir(parents=True, exist_ok=True)
    path = streams / f"{stream_uid}.jsonl"
    existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    seq = len(existing) + 1
    event = {
        "specversion": "1.0",
        "type": "tropo.governance.conflict_routed",
        "source": "/tools/governance-gate",
        "source_uid": stream_uid,
        "time": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "lifecycle": "evergreen",
        "subject": owner_party_uid,
        "data": {
            "record_uid": record_uid,
            "owner_party_uid": owner_party_uid,
            "resolver": resolver,
        },
        "id": f"evt_{stream_uid}_{seq:08d}",
        "event_uid": f"evt_{stream_uid}_{seq:08d}",
        "writer_instance_uid": stream_uid,
        "stream_uid": stream_uid,
        "local_seq": seq,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    return path


__all__ = [
    "VALIDATOR", "GOVERNED_GLOBS",
    "GovernanceError", "GovernanceBlocked", "GateNotInstalled",
    "validate_paths", "hook_script", "hook_path", "install_hook", "assert_hook_installed",
    "MERGE_SCRIPT", "MERGE_DRIVER_NAME", "MERGE_GOVERNED_PATTERN",
    "merge_driver_command", "install_merge_driver", "merge_driver_configured",
    "gitattributes_declares_merge_tropo", "install_merge_attributes",
    "unconfigured_driver_warning", "resolve_delete_change_conflict",
    "detect_delete_change_race", "emit_delete_change_race_event",
    "emit_conflict_event",
]
