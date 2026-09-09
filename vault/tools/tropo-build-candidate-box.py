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
    # ARM THE SHIP-VERDICT RESOLVER, as the release build does first thing in
    # main() (init_ship_verdicts, :4280). Unarmed, copy_file ships everything:
    # no ROOT MANIFEST row or ship-artifact DENY applied to any candidate ever
    # built here, so a walker could be handed content the release box denies
    # (measured 2026-09-06 by argus-a172: four DENY'd kernel history companions
    # still in the candidate). The census the gate prints is the loud half.
    builder.init_ship_verdicts(studio, builder.INDEX_PATH)
    return builder


def box_declared_version(box: Path) -> str:
    """The version the BOX itself declares, from its own .tropo/version.md.

    A candidate never bumps, so this is the tracked value at the source commit.
    Reading it from the box rather than accepting a flag is deliberate: it is the
    only value that cannot disagree with what a stranger opening the box reads.
    """
    version_file = box / ".tropo" / "version.md"
    if not version_file.is_file():
        # LOUD. Three generated artifacts stamp this string, and a box with no
        # declared version would stamp them "unknown" and look like a real
        # release with a broken version — worse than refusing to build one.
        raise SystemExit(
            f"REFUSED: {version_file} is absent, so the box declares no version and "
            "MANIFEST.md / tropo-image-manifest.json cannot be stamped truthfully."
        )
    return version_file.read_text(encoding="utf-8").strip().lstrip("v")


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
    # The real build's wholesale playbook channel (step_3d), so a candidate box
    # carries what a release box carries -- the AC7 doc-currency exit instrument
    # (scripts/doc-currency-candidate-gate.py) reads this box as the build's
    # stand-in. Before this line the candidate shipped only the manifest-channel
    # playbooks (25 of 28 at HEAD 2026-09-05) and under-counted the gate by the
    # three superseded files the release build still copied (argus-a172).
    builder.step_3d_copy_vault_playbooks(str(box))
    # The release build's other wholesale channels (the ship-manifest suite's
    # "every emitter a real build runs" list): vault/tools/ recursively by the A92
    # ruling fdef56ea (the scripting layer is atomic; per-tool tagging re-opens
    # the omission bug), vault/updates/, vault/schema/. Without 3b this candidate
    # carried 83 of 114 tools and the doc-currency exit instrument reported the
    # join ceremony's four group tools "absent" when every release box has
    # shipped them (argus-a172, 2026-09-06, second under-count found).
    builder.step_3b_copy_vault_tools(str(box))
    builder.step_3e_copy_vault_updates(str(box))
    builder.step_3j_copy_vault_schema(str(box))
    builder.step_4_copy_ship_entries(
        str(box), builder.load_ship_entries(builder.INDEX_PATH)
    )
    # The tree-resident files the manifest channel does not carry: CHANGELOG.md,
    # package.json, the four folder-level AGENTS.md contracts, and the
    # mission-brief boot slot. Until 2026-09-08 these lived inline in the release
    # build's main() and no other caller could reach them, so every candidate box
    # ever built was missing all seven — and three of the twelve box gates refused
    # on that gap rather than on the product (task f0158df832b1, the keystone;
    # measured on a HEAD box the same morning: build-mission-brief-slot,
    # build-box-self-test and build-release-harness all RED, none a product
    # defect). They are now named steps in tropo-build-release.py and these are
    # calls to the SAME functions, in the release build's own order — one
    # producer, so the two boxes cannot drift on this content again. Copying the
    # seven filenames into this file instead would have recreated the
    # two-producers-of-one-fact defect that has cost this studio most of the last
    # six releases. [talos-t65]
    builder.step_5c_copy_changelog(str(box))
    builder.step_5d_copy_folder_mirror_files(str(box))
    try:
        builder.step_7_create_vault_skeleton(str(box))
    except SystemExit as exc:
        print(f"  · skeleton step declined: {exc}")
    # AFTER the skeleton, exactly as the release build orders it: step_7 rmtree's
    # and recreates .tropo-studio/, so a slot seeded before it is clobbered.
    builder.step_7_1_seed_mission_brief_slot(str(box))
    # Step 7.2 — the score-formula doctrine, same post-skeleton rule. Added
    # 2026-09-08 by talos-t66: the candidate lane is where beat 4 is scored, so a
    # candidate box missing this file is precisely the case that has been failing.
    builder.step_7_2_seed_score_formula_doctrine(str(box))
    # The address is DERIVED — from the publish environment, else from tracked
    # publication evidence. A candidate box that invented a URL would have
    # someone walk a lie, and a candidate that merely REPORTED the gap and
    # exited 0 sent Metis a box whose update leg could not be walked (AC8
    # verdict 62a22664, Argus ruling 3). So an unresolved address is now fatal
    # here: a walkable candidate cannot be missing a required leg.
    # The release build's Step 3f: the two per-studio boot derivations
    # (.tropo/boot-digest.md, .tropo/boot-fast-path.md) leave the box and their
    # index rows are pruned. This tool never ran it, so every candidate carried
    # both files and the doc-currency exit instrument read 0 where the release
    # build read 2 (v1.95 candidate #1, 2026-09-06 -- the canonical playbook's
    # line 58 links both). Third channel the candidate under-represented; the
    # instrument must predict the build (argus-a172, driver evt _00000159).
    # Placed where the release build places it: AFTER every copy channel (the
    # derivations are governed entries and arrive through step_4's ship entries,
    # so a 3f before step_4 removed nothing -- measured on the first rebuild).
    builder.step_3f_remove_per_studio_boot_derivations(str(box))
    builder.step_3g_write_update_source(str(box))
    # Step 9b (the box's own index, --no-genesis) then 9b2 (the Studio Map rendered
    # inside the box, AC8's build-step half): the release build runs both before
    # sanitize; without them a candidate has no boards/po/studio-map.html and AC8's
    # zip-listing check can never pass on it (argus-a172, 2026-09-06, rehearsing
    # the box-dependent rows on a HEAD candidate). 9b's index is purged by 10.2
    # below exactly as in a release box.
    builder.step_9b_regenerate_tropo_nav(str(box))
    builder.step_9b2_render_studio_map(str(box))
    # The three artifacts the release build GENERATES rather than copies:
    # vault/vendor-refs-manifest.json (9c, before sanitize), MANIFEST.md (9,
    # after the purge so it cannot list files the freeze removed) and
    # tropo-image-manifest.json (9d, last, because it is the only record a
    # recipient can integrity-check the box against). Bucket two of task
    # f0158df832b1: generate them, or make the gates that read them skip with a
    # named reason. GENERATE, for the reason this tool's own contract already
    # states -- "a candidate that represents the FINAL box must end where the
    # official build ends." Measured 2026-09-08: without MANIFEST.md the box
    # fails its own shipped harness 11/12 and `build-release-harness` refuses,
    # while the SHIPPED v1.95.0 box passes that same gate -- a difference that
    # is the builder's, not the product's, which is precisely what the twelve
    # gates must stop reporting before they can be wired into the nightly.
    #
    # THE VERSION IS THE BOX'S OWN. A candidate does not bump, so the box carries
    # the tracked .tropo/version.md, and all three artifacts are stamped from it:
    # the version.md, the MANIFEST header and the image manifest then agree with
    # each other. Inventing a candidate-only string here would put one fact in
    # three places with two of them disagreeing -- the defect family this whole
    # task exists to close. Candidate identity is the source commit, and it lives
    # where a walker looks for it: CANDIDATE-BOX-MANIFEST.json, next to
    # not_a_release: true. [talos-t65]
    version = box_declared_version(box)
    builder.step_9c_generate_vendor_ref_manifest(str(box), version)

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
    # After the purge, exactly as the release build orders it: the manifest must
    # not list files the freeze removed, and must be stamped AFTER sanitize
    # rewrote its subjects (a hash taken before the rewrite makes every untouched
    # shipped file read USER_MODIFIED_SHIPPED on a customer's disk).
    builder.step_9_generate_manifest(str(box), version)
    # Last thing written, as in the release build: it is the only record a
    # recipient can integrity-check the box against, and it excludes itself.
    builder.step_9d_emit_image_manifest(str(box), version)
    return {
        "manifest_root": root_uid,
        "entries": len(entries),
        "update_source": "written",
        "box_version": version,
    }


# Every shipped file that stamps its own build time. They are real shipped bytes
# and belong in the package identity; they also make that identity differ between
# two builds of the SAME commit, which would silently retire this tool's
# reproducibility claim. So both numbers are reported, each saying what it is.
#
# MEASURED, not assumed (talos-t65, 2026-09-08): two builds of commit 51803f445
# were compared file by file. Exactly these five differ, each by a timestamp
# alone; with them set aside the remaining 1,436 files are byte-identical. The
# first draft of this list named only the first two — the ones I had just added —
# and asserted reproducibility on that basis; the double build said otherwise.
# If a future emitter stamps a time, this list goes stale silently: the way to
# find out is the same double build, not a re-reading of this comment.
SELF_TIMESTAMPED_ARTIFACTS = (
    "MANIFEST.md",                               # Step 9's "Generated:" header
    "tropo-image-manifest.json",                 # Step 9d's generated_utc
    "vault/vendor-refs-manifest.json",           # Step 9c's "generated"
    ".tropo-studio/shards/index-rebuild-run.json",  # the box's own index rebuild: run_started_at
    "vault/events/00-events.jsonl",              # the rebuild's ephemeral substrate.modified event
)


def _fold(files: dict) -> str:
    return hashlib.sha256(
        "\n".join(f"{rel}\0{digest}" for rel, digest in sorted(files.items())).encode()
    ).hexdigest()


def digest_tree(box: Path) -> tuple:
    """Per-file digests, the package SHA, and the commit-reproducible SHA.

    `package` covers every shipped byte — Argus's ruling (evt 113) that a package
    SHA excluding a shipped file is not an identity for that package. `content`
    drops the five artifacts that stamp their own build time, so two builds of one
    commit can be compared for real. Neither replaces the other: `package`
    identifies THIS box, `content` answers "is this the same box as that one".

    `content` is NOT a reproducibility guarantee — it is the question asked
    honestly. Equal content SHAs across two builds of one commit mean the 1,436
    other files matched; unequal means something outside the named five moved,
    and that is the finding.
    """
    files = {}
    for path in sorted(box.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(box).as_posix()
        if rel == MANIFEST_NAME:
            continue
        files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    content = _fold({k: v for k, v in files.items()
                     if k not in SELF_TIMESTAMPED_ARTIFACTS})
    return files, _fold(files), content


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
    # .resolve(): the verdict resolver compares Studio-relative paths, and on macOS
    # tempfile hands back /var/... while the loaded builder sees /private/var/...
    # through the symlink -- every kernel file then reads as "outside the root"
    # and the armed build refuses (argus-a172, 2026-09-06).
    workspace = (out / "_source" if args.keep_source else Path(tempfile.mkdtemp(prefix="candidate-src-"))).resolve()
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
    files, package_sha, content_sha = digest_tree(box)
    checks = contract_checks(box, workspace)

    manifest = {
        "schema_id": "tropo.candidate-box/v1",
        "not_a_release": True,
        "built_by": f"{TOOL_UID} tropo-build-candidate-box.py",
        "source_commit": commit,
        # The version the box declares, stamped into MANIFEST.md and
        # tropo-image-manifest.json. It is the tracked value at source_commit, NOT
        # a release: a candidate does not bump, and `not_a_release` above plus
        # `source_commit` are this box's identity.
        "box_declared_version": stats["box_version"],
        "manifest_root": stats["manifest_root"],
        "ship_artifact_entries": stats["entries"],
        "update_source": stats["update_source"],
        "file_count": len(files),
        "package_sha256": package_sha,
        # Same bytes minus the five artifacts that stamp their own build time
        # (SELF_TIMESTAMPED_ARTIFACTS, listed here so a reader of this manifest
        # alone knows what the number covers). Compare THIS across two builds to
        # ask whether one commit produced one box.
        "content_sha256": content_sha,
        "content_sha256_excludes": list(SELF_TIMESTAMPED_ARTIFACTS),
        "contract_checks": checks,
        "files": files,
    }
    (box.parent / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print()
    print(f"  box:          {box}")
    print(f"  files:        {len(files)}")
    print(f"  package_sha:  {package_sha}  (every shipped byte)")
    print(f"  content_sha:  {content_sha}  (minus {len(SELF_TIMESTAMPED_ARTIFACTS)} self-timestamped artifacts)")
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
