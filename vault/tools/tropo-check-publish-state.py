#!/usr/bin/env python3
"""
---
uid: 7b3c1f90
name: check-publish-state
type: tool
status: active
owner: argus
domain: "Release publish-state reconciliation — internal version vs the LIVE GitHub remote."
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-check-publish-state.py"
belt: false
title: "check-publish-state — is internal version in sync with what's PUBLISHED on GitHub?"
trigger_description: "Run before any release/publish action, or as a health check, to see whether the internal version has drifted ahead of what is actually tagged on the public GitHub remote. Hits the LIVE remote via git ls-remote — never a local clone, unless --remote/--clone overrides it (test seam)."
schema_version: 2
version: '2.1'
v2_1_amendment_note: "Verify-live now resolves the exact remote tag target (peeling annotated tags) and requires remote_tag_sha == remote_main_sha == staged_sha when --sha is supplied. Machine JSON reports observations rather than self-asserted proof flags. The publisher pins this tool to tropo-ai/tropo; standalone remote overrides remain test seams."
---

WHY THIS EXISTS (Argus A129, 2026-07-11, Mike-caught): I read a LOCAL clone once,
saw a stale tag, and burned two days catching up a release that was already
published. The rule 'verify the LIVE state, not a local clone or a memory' was a
memory pin — discipline, which failed. This is the structural version: a check
that reads the internal version and queries the ACTUAL GitHub remote (git
ls-remote, no local clone by default) and reports drift. Wire it into the release
flow / a boot health line so 'is it already published?' is answered by the
substrate, not by an agent eyeballing a stale copy.

Exit 0 = in sync (or --expect verification passed). Exit 1 = drift / --expect
verification failed. Exit 2 = could not determine (network/remote error, or
version.md missing/unparseable) — fail-LOUD, never silently 'assume in sync'.
"""
from __future__ import annotations  # PEP 604 `X | None` annotations on py3.9
import argparse
import json as _json
import subprocess
import sys
import re
from pathlib import Path

REMOTE = "https://github.com/tropo-ai/tropo.git"   # the public OS repo; live remote by default
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _semver_key(v):
    v = v.lstrip("v")
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in (parts + ["0", "0", "0"])[:3])


def internal_version(root: Path, version_path: Path = None) -> str:
    """Parse .tropo/version.md. Handles both shapes in the wild:
    - bare (this studio's own convention): the whole file is just 'v1.84.1' / '1.84.1'.
    - frontmatter (a BUILT release's shipped version.md, per step_8_write_version):
      '---\\nversion: "1.84.1"\\n...\\n---\\n...'.
    Returns 'UNKNOWN' if the file is absent, empty, or neither shape parses —
    callers must treat UNKNOWN as a hard stop (exit 2), never as a version to compare.
    """
    vf = version_path or (root / ".tropo" / "version.md")
    if not vf.is_file():
        return "UNKNOWN"
    try:
        text = vf.read_text(encoding="utf-8").strip()
    except OSError:
        return "UNKNOWN"
    if not text:
        return "UNKNOWN"
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end == -1:
            return "UNKNOWN"
        fm_text = text[3:end]
        m = re.search(r'^version:\s*["\']?(\d+\.\d+\.\d+)', fm_text, re.MULTILINE)
        return m.group(1) if m else "UNKNOWN"
    m = re.match(r'^v?(\d+\.\d+\.\d+)', text)
    return m.group(1) if m else "UNKNOWN"


def published_versions(remote: str):
    """Query the remote (URL or local path — git ls-remote accepts either
    transparently, the mechanism the --remote/--clone test seams rely on) for
    tags. Returns sorted list of x.y.z strings, or raises."""
    out = subprocess.run(
        ["git", "ls-remote", "--tags", remote],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git ls-remote failed: {out.stderr.strip()[:200]}")
    tags = set()
    for line in out.stdout.splitlines():
        m = re.search(r"refs/tags/v?(\d+\.\d+\.\d+)(?:\^\{\})?$", line.strip())
        if m:
            tags.add(m.group(1))
    return sorted(tags, key=_semver_key)


def remote_main_sha(remote: str) -> str | None:
    """The live remote's refs/heads/main sha, or None if the ref doesn't resolve."""
    out = subprocess.run(
        ["git", "ls-remote", remote, "refs/heads/main"],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git ls-remote failed: {out.stderr.strip()[:200]}")
    line = out.stdout.strip()
    if not line:
        return None
    parts = line.split()
    if (
        len(parts) != 2
        or parts[1] != "refs/heads/main"
        or not SHA_RE.fullmatch(parts[0])
    ):
        raise RuntimeError("git ls-remote returned an ambiguous main ref")
    return parts[0]


def remote_tag_sha(remote: str, tag: str) -> str | None:
    """Resolve a lightweight or annotated tag to its target commit SHA."""
    direct_ref = f"refs/tags/{tag}"
    peeled_ref = f"{direct_ref}^{{}}"
    out = subprocess.run(
        ["git", "ls-remote", remote, direct_ref, peeled_ref],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git ls-remote failed: {out.stderr.strip()[:200]}")
    refs: dict[str, str] = {}
    for line in out.stdout.splitlines():
        parts = line.strip().split()
        if (
            len(parts) != 2
            or parts[1] not in {direct_ref, peeled_ref}
            or not SHA_RE.fullmatch(parts[0])
            or parts[1] in refs
        ):
            raise RuntimeError("git ls-remote returned an ambiguous tag ref")
        refs[parts[1]] = parts[0]
    if peeled_ref in refs and direct_ref not in refs:
        raise RuntimeError("git ls-remote returned a peeled tag without its tag ref")
    if peeled_ref in refs:
        return refs[peeled_ref]
    return refs.get(direct_ref)


def _emit(json_mode: bool, payload: dict, human_lines: list[str]):
    if json_mode:
        print(_json.dumps(payload, indent=2))
    else:
        for line in human_lines:
            print(line)


def cmd_expect(args, remote: str) -> int:
    """--expect <version> [--sha <sha>]: the verify-live tag-target/main leg. The
    gh release-object leg composes on top of this in tropo-publish-release.py —
    this tool never shells out to gh (git-only, per its own WHY-THIS-EXISTS)."""
    expect_norm = str(args.expect).lstrip("vV")
    tag = f"v{expect_norm}"
    try:
        tag_sha = remote_tag_sha(remote, tag)
        main_sha = remote_main_sha(remote)
    except Exception as e:
        payload = {"status": "unreachable", "exit_code": 2, "error": str(e), "expect": expect_norm}
        _emit(args.json, payload, [f"✗ COULD NOT REACH THE REMOTE: {e}", "  Fail-loud: do NOT assume verified."])
        return 2
    expected_sha = args.sha
    verified = (
        tag_sha is not None
        and main_sha is not None
        and tag_sha == main_sha
        and (expected_sha is None or main_sha == expected_sha)
    )
    payload = {
        "status": "verified" if verified else "not_verified",
        "exit_code": 0 if verified else 1,
        "expect": expect_norm,
        "tag": tag,
        "expected_sha": expected_sha,
        "remote_tag_sha": tag_sha,
        "remote_main_sha": main_sha,
    }
    lines = [
        f"{tag} target commit: {tag_sha!r}",
        f"refs/heads/main commit: {main_sha!r}",
    ]
    if expected_sha:
        lines.append(f"staged commit: {expected_sha!r}")
    lines.append("✓ VERIFIED" if verified else "✗ NOT VERIFIED")
    _emit(args.json, payload, lines)
    return 0 if verified else 1


def cmd_status(args, remote: str, root: Path = None) -> int:
    root = root or Path(__file__).resolve().parents[2]   # <studio root>; test seam via param
    internal = internal_version(root)
    if internal == "UNKNOWN":
        payload = {"status": "unknown_version", "exit_code": 2, "internal_version": "UNKNOWN"}
        _emit(args.json, payload,
              ["✗ UNKNOWN — .tropo/version.md missing or unparseable.",
               "  Fail-loud: never 'drift' on a version we can't even read."])
        return 2

    try:
        pubs = published_versions(remote)
    except Exception as e:
        payload = {"status": "unreachable", "exit_code": 2, "internal_version": internal, "error": str(e)}
        _emit(args.json, payload,
              [f"internal version (.tropo/version.md): v{internal}", f"remote: {remote}",
               f"✗ COULD NOT REACH THE REMOTE: {e}",
               "  Fail-loud: do NOT assume in-sync. Resolve connectivity, then re-run."])
        return 2

    latest_pub = pubs[-1] if pubs else None
    lines = [
        f"internal version (.tropo/version.md): v{internal}",
        f"remote: {remote}",
        f"latest published tag: {'v' + latest_pub if latest_pub else '(none)'}",
        f"published tags: {', '.join('v' + p for p in pubs) if pubs else '(none)'}",
    ]

    if latest_pub is None:
        status, exit_code = "internal_ahead", 1
        lines.append("⚠ DRIFT — internal has a version but NOTHING is published.")
    else:
        ik, pk = _semver_key(internal), _semver_key(latest_pub)
        if ik == pk:
            status, exit_code = "in_sync", 0
            lines.append(f"✓ IN SYNC — v{internal} is published on GitHub. No publish action needed.")
        elif ik > pk:
            status, exit_code = "internal_ahead", 1
            lines.append(f"⚠ DRIFT — internal v{internal} is AHEAD of published v{latest_pub}. "
                         f"The current version is NOT on GitHub. Publish before acting.")
        else:
            status, exit_code = "remote_ahead_anomaly", 1
            lines.append(f"⚠ ANOMALY — published v{latest_pub} is AHEAD of internal v{internal}. Investigate.")

    payload = {
        "status": status, "exit_code": exit_code,
        "internal_version": internal, "published_versions": pubs,
        "latest_published": latest_pub,
    }
    _emit(args.json, payload, lines)
    return exit_code


def main():
    ap = argparse.ArgumentParser(description="check-publish-state — internal vs published-on-GitHub reconciliation")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--remote", default=None, help="override the live remote URL (test seam)")
    ap.add_argument("--clone", default=None, help="alias for --remote naming a local clone/bare dir "
                                                    "(git ls-remote accepts a local path transparently)")
    ap.add_argument("--expect", default=None, metavar="VERSION",
                     help="verify-live mode: resolve this tag target and require it equals remote main")
    ap.add_argument("--sha", default=None,
                    help="companion to --expect: tag target and remote main must also equal this staged sha")
    args = ap.parse_args()

    remote = args.clone or args.remote or REMOTE

    if args.expect:
        return cmd_expect(args, remote)
    return cmd_status(args, remote)


if __name__ == "__main__":
    sys.exit(main())
