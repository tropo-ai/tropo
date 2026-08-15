#!/usr/bin/env python3
"""
---
uid: 40b6cfd6
title: build-candidate-box — Tool
name: build-candidate-box
type: tool
status: active
owner: talos
domain: "Reproducible NON-RELEASE candidate box for an independent cold walk: same production package functions as the release builder, bound to an exact source commit, with a recorded package SHA. Never publishes, locks, or produces a release."
spawnable_by:
  - all-executives
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-build-candidate-box.py --out <dir> [--commit <sha>]"
script_path: vault/tools/tropo-build-candidate-box.py
destructive: false
audit_required: false
writes_scope:
  - "<explicit --out directory only>"
governance_category: query
description: "Builds a candidate box for cold-walk verification (gate 2a7ab1cf / AC8). Materializes tracked sources at an exact commit into an isolated tree, freshens that tree's own index, then runs the SAME production package functions the release builder uses. Emits CANDIDATE-BOX-MANIFEST.json with the source commit, per-file digests, a package SHA, and the Fresh-Box contract checks. Refuses to write into releases/ and creates no release receipt, version bump, or publish state."
domain_tags:
  - release
  - cold-walk
  - candidate-box
  - verification
trigger_description: "Reach for this when someone who did not build the code needs to walk a real box — a cold walk, a gate verification, or reproducing a customer-path defect. It is NOT the release builder: it cannot publish and produces no receipt. For an actual release, drive pipeline-runtime.py, which mints the activation key build-release requires."
created: 2026-08-13
created_by: talos-t41
modified: 2026-08-13
modified_by: talos-t41
governed_by: d5e1b4a3
member_of:
  - 8dd772a0
schema_version: 2
extraction_scope: argo-private
refs:
  - e52826c5
  - 2a7ab1cf
tags:
  - tool
  - cli
  - cold-walk
subsystem_hub:
  - 8dd772a0
---
"""

from __future__ import annotations

"""Candidate box for an independent cold walk (gate 2a7ab1cf AC8).

The builder cannot certify their own box, so someone else has to walk one — and
what they walk has to be reproducible, bound to a known commit, and built by the
SAME functions that build a real release. Otherwise the walk verifies an
artifact no customer will ever receive.

WHY THIS IS NOT `tropo-build-release.py`. That tool refuses without a Pipeline
Activation Key, minted at the produce-release-folder gate by the pipeline
runtime, and producing one means driving a release cycle. A cold walk is not a
release: nothing is published, no receipt is written, no version is bumped, and
the release plan stays untouched. So this entry point is FENCED — it invokes the
package functions and nothing downstream of them.

What it does not do, by construction:
  * never writes into ``releases/``;
  * never mints a receipt, bumps ``.tropo/version.md``, or sets publish state;
  * never mutates the source Studio's index or any other derived surface;
  * never claims a verdict. It reports contract checks; a human walks the box.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL_UID = "40b6cfd6"
ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "vault" / "tools"
MANIFEST_NAME = "CANDIDATE-BOX-MANIFEST.json"


def run(args: list, cwd: Path, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(a) for a in args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def source_commit(explicit: str | None) -> str:
    if explicit:
        return explicit
    proc = run(["git", "rev-parse", "HEAD"], ROOT)
    if proc.returncode != 0:
        raise SystemExit("cannot resolve HEAD; pass --commit explicitly")
    return proc.stdout.strip()


def materialize(commit: str, into: Path) -> None:
    """Tracked sources at an exact commit — no derived state, no local dirt."""
    archive = subprocess.run(
        ["git", "archive", commit], cwd=str(ROOT), capture_output=True, timeout=600
    )
    if archive.returncode != 0:
        raise SystemExit(
            f"git archive {commit} failed: {archive.stderr.decode()[:300]}"
        )
    extract = subprocess.run(
        ["tar", "-x", "-C", str(into)], input=archive.stdout, capture_output=True
    )
    if extract.returncode != 0:
        raise SystemExit(f"tar extract failed: {extract.stderr.decode()[:300]}")


def freshen_index(studio: Path) -> None:
    """The candidate's OWN index, derived from its own sources.

    Index surfaces are gitignored, so a tracked-source tree has none. Building
    the package against the operator's live index is what made the first
    Fresh-Box fixture pass on one machine and fail on another.
    """
    proc = run(
        [
            sys.executable,
            studio / "vault" / "tools" / "tropo-rebuild-index.py",
            "--apply",
            "--skip-rehydrate",
            "--vault-path",
            studio,
        ],
        studio,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "candidate index rebuild failed:\n" + (proc.stderr or proc.stdout)[-800:]
        )


def load_builder(studio: Path):
    """The production package functions, rooted at the candidate source tree."""
    spec = importlib.util.spec_from_file_location(
        "tropo_build_release_candidate", studio / "vault" / "tools" / "tropo-build-release.py"
    )
    builder = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = builder
    spec.loader.exec_module(builder)
    builder.tropo_roots.STUDIO_ROOT = studio
    builder.tropo_roots.VAULT_DIR = studio / "vault"
    builder.INDEX_PATH = str(studio / "vault" / "00-index.jsonl")
    builder.SHIP_ARTIFACT_CAPSULE_PATH = str(
        studio / "vault" / "capsules" / "tropo-ship-artifact.capsule.md"
    )
    builder.DRY_RUN = False
    return builder


def emit_box(builder, box: Path) -> dict:
    """The same emitters, in the same order, as a real build."""
    root_uid = builder.read_manifest_root_uid(builder.SHIP_ARTIFACT_CAPSULE_PATH)
    entries = builder.load_manifest_entries(builder.INDEX_PATH, root_uid)
    builder.build_from_manifest(str(box), entries)
    # The kernel copy, which the official build runs and this tool did not. It
    # carries `.tropo/` including the concierge and its outcome playbooks —
    # the "make your first agent in 5 minutes" path START-TROPO advertises.
    # Without it a candidate box was missing content the real package ships, so
    # every walk of one under-represented the artifact and could report a
    # missing-file finding that exists only in the candidate. A walk is only
    # worth the paper it prints if the thing walked is the thing shipped.
    builder.step_3_copy_kernel(str(box))
    builder.step_4_copy_ship_entries(
        str(box), builder.load_ship_entries(builder.INDEX_PATH)
    )
    try:
        builder.step_7_create_vault_skeleton(str(box))
    except SystemExit as exc:
        print(f"  · skeleton step declined: {exc}")
    # The address is DERIVED — from the publish environment, else from tracked
    # publication evidence. A candidate box that invented a URL would have
    # someone walk a lie, and a candidate that merely REPORTED the gap and
    # exited 0 sent Metis a box whose update leg could not be walked (AC8
    # verdict 62a22664, Argus ruling 3). So an unresolved address is now fatal
    # here: a walkable candidate cannot be missing a required leg.
    builder.step_3g_write_update_source(str(box))

    # A candidate that represents the FINAL box must end where the official
    # build ends. Stopping earlier shipped an intermediate shape: an unsanitized
    # box still carrying Argo identity, and an index nobody had sealed — so the
    # recipient's first documented rebuild refused with "no trusted
    # index-surface metadata" and the cure the message named did not work
    # (Argus ruling, evt 107). The digest is taken after these, so the SHA names
    # the artifact a walker actually receives.
    builder.step_10_sanitize_argo_identity(str(box))
    # PURGE BEFORE SEAL. The seal records which evidence copies exist, so
    # sealing first and deleting the database afterwards left a ratchet that
    # expects a file the package does not carry — the recipient's first rebuild
    # then refused with "shrink-floor evidence is incomplete". Removing it first
    # makes `sqlite_state: missing` the truth the seal records.
    # No seal: sealing writes evidence ABOUT surfaces this package does not
    # ship, and evidence for absent files is the self-contradiction evt 114
    # rules out. The recipient's first rebuild seals its own generation.
    builder.step_10_2_purge_run_local_artifacts(str(box))
    return {"manifest_root": root_uid, "entries": len(entries), "update_source": "written"}


def digest_tree(box: Path) -> tuple:
    """Per-file digests plus one package SHA over the sorted (path, digest) list."""
    files = {}
    for path in sorted(box.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(box).as_posix()
        if rel == MANIFEST_NAME:
            continue
        files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    package = hashlib.sha256(
        "\n".join(f"{rel}\0{digest}" for rel, digest in sorted(files.items())).encode()
    ).hexdigest()
    return files, package


def verify_portable_surfaces(box: Path) -> dict:
    """The portable truth the package ships, and the machine-local state it does not.

    Ruled by Argus (evt 113): a package SHA that excludes a shipped file is not
    an identity for that package, so the database does not ship at all. What
    ships is the sealed current/archive JSONL pair plus index-surfaces.meta.json
    — text, byte-identical on any machine — and the seal already declares
    `sqlite_state: missing`, so shipping no database is what the metadata says.
    """
    vault = box / "vault"
    current, archive = vault / "00-index.jsonl", vault / "00-archive-index.jsonl"
    machine_local = sorted(
        str(p.relative_to(box)) for p in box.rglob("*")
        if p.is_file() and (p.name.endswith((".sqlite", "-shm", "-wal", ".tmp-shm",
                                             ".tmp-wal", ".pyc", ".pyo"))
                            or p.name == "index-write.lock")
    )
    def rows(path: Path) -> int:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                   if line.strip()) if path.is_file() else 0

    return {
        "sealed_pair_present": current.is_file() and archive.is_file(),
        "current_rows": rows(current),
        "archive_rows": rows(archive),
        "seal_present": (box / ".tropo-studio" / "locks"
                         / "index-surfaces.meta.json").is_file(),
        "machine_local_files": machine_local,
    }


def contract_checks(box: Path, studio: Path) -> dict:
    """The Fresh-Box contract, restated against the emitted box.

    Same properties the accepted fixture asserts, so the walked box and the
    tested box are demonstrably the same shape. This reports; it does not judge.
    """
    templates_expected = sorted(
        p.name for p in (studio / "vault" / "templates").glob("tropo-*.template.md")
    )
    templates_present = sorted(
        p.name for p in (box / "vault" / "templates").glob("tropo-*.template.md")
    )
    orientation = box / "AGENT-ORIENTATION.md"
    smoke = box / "vault" / "tools" / "tropo-smoke.py"
    trust_leaks = [
        p.relative_to(box).as_posix()
        for p in box.rglob("*")
        if p.is_file() and "trust/" in p.relative_to(box).as_posix()
    ]
    return {
        "AC1_templates_expected": len(templates_expected),
        "AC1_templates_present": len(templates_present),
        "AC1_missing": [t for t in templates_expected if t not in templates_present],
        "AC5_trust_state_files": trust_leaks,
        "AC6_smoke_present": smoke.is_file(),
        "AC7_orientation_present": orientation.is_file(),
        "AC7_orientation_bytes": orientation.stat().st_size if orientation.is_file() else 0,
        "portable_surfaces": verify_portable_surfaces(box),
    }


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a NON-RELEASE candidate box for an independent cold walk. "
            "Never publishes, locks, or produces a release."
        )
    )
    parser.add_argument("--out", required=True, help="output directory (must not exist)")
    parser.add_argument("--commit", default=None, help="source commit (default: HEAD)")
    parser.add_argument("--keep-source", action="store_true",
                        help="retain the extracted source tree beside the box")
    args = parser.parse_args(argv)

    out = Path(args.out).resolve()
    if "releases" in out.parts:
        raise SystemExit(
            f"REFUSED: {out} is inside releases/. A candidate box is not a release; "
            "point --out somewhere else."
        )
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"REFUSED: {out} exists and is not empty")

    commit = source_commit(args.commit)
    out.mkdir(parents=True, exist_ok=True)
    workspace = out / "_source" if args.keep_source else Path(tempfile.mkdtemp(prefix="candidate-src-"))
    workspace.mkdir(parents=True, exist_ok=True)
    box = out / "box"
    box.mkdir()

    print("=" * 72)
    print(f"Candidate box (NOT a release) — source commit {commit[:12]}")
    print("=" * 72)
    print("[1/4] materializing tracked sources at the exact commit…")
    materialize(commit, workspace)
    print("[2/4] building the candidate's own index from those sources…")
    freshen_index(workspace)
    print("[3/4] emitting through production package functions…")
    stats = emit_box(load_builder(workspace), box)
    print("[4/4] digesting and checking the Fresh-Box contract…")
    files, package_sha = digest_tree(box)
    checks = contract_checks(box, workspace)

    manifest = {
        "schema_id": "tropo.candidate-box/v1",
        "not_a_release": True,
        "built_by": f"{TOOL_UID} tropo-build-candidate-box.py",
        "source_commit": commit,
        "manifest_root": stats["manifest_root"],
        "ship_artifact_entries": stats["entries"],
        "update_source": stats["update_source"],
        "file_count": len(files),
        "package_sha256": package_sha,
        "contract_checks": checks,
        "files": files,
    }
    (box.parent / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print()
    print(f"  box:          {box}")
    print(f"  files:        {len(files)}")
    print(f"  package_sha:  {package_sha}")
    print(f"  manifest:     {box.parent / MANIFEST_NAME}")
    print(f"  update-source: {stats['update_source']}")
    print()
    print("  contract checks (reported, not judged):")
    for key, value in checks.items():
        print(f"    {key}: {value}")
    print()
    print("  This box is NOT a release: no receipt, no version bump, no publish")
    print("  state, and nothing written outside --out. A human walks it; this")
    print("  tool does not record a verdict.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
