#!/usr/bin/env python3
"""
update-subsystem-canonical-docs.py — dev-pipeline step v1.9.2

Auto-fires Rule 12 hub release_history derivation. Reads the release-plan's
`capabilities_touched:` and `hub_summaries:`, derives `subsystems_touched:`
via 1-hop `member_of:` graph traversal, then for each touched subsystem hub
writes:

  1. A new `release_history:` row at the top of the hub's frontmatter array
     (with `derived_from: capabilities_touched`)
  2. A `last_release_reflected:` bump on the hub's frontmatter
  3. A corresponding row in `subsystem-registry.jsonl`
  4. The derived `subsystems_touched:` set on the release entry

Frontmatter only. Body sections (`## Change Log`, `## Current State`) are
human documentation per v1.9.2 Q7 walk reframe (carry-forward 4b7a9d3f);
they are NOT this executor's scope.

Closes the manual-substitute pattern that ran across v1.8 + v1.9.0 + v1.9.1
(each cycle hand-wrote an `append-v1-X-hub-rows.py` script because this
executor didn't exist). Per build-the-executor-when-introducing-doctrine pin
(a46-reflection 2026-05-05).

Governed by:
  - WorkflowNode entry: vault/files/9d4f7e21.md
  - pipeline.capsule v2.4: .tropo/capsules/pipeline.capsule.md
  - release-plan.capsule v1.3: .tropo/capsules/release-plan.capsule.md
    (consumes hub_summaries: field)
  - release.capsule v3.4: Rule 12 (the rule this executor fires)
  - subsystem-hub.capsule v1.4: contract for release_history rows

Usage:
  python3 update-subsystem-canonical-docs.py \\
    --release-plan-uid <uid> \\
    --release-entry-uid <uid> \\
    [--build-entry-uid <uid>] \\
    [--vault-root <path>] \\
    [--dry-run]

Exit codes:
  0 = success (or dry-run clean)
  1 = validation FAIL (missing hub_summaries; non-hub UID; etc.)
  2 = vault inconsistency (UID not found; index broken)
  3 = write conflict
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import secrets
import sys
from pathlib import Path

import yaml


def _extract_stream_ids(streams_field: list) -> list[str]:
    """Pull stream id strings from a release-plan's `streams:` array.

    Each stream entry is a dict like `{id: "A", name: "...", owner: "...",
    items: 4}`. Returns the list of `id` values (e.g., ["A", "B", "C"]).
    Used by `append_registry_row` to populate `streams_touched`.
    """
    ids: list[str] = []
    for entry in streams_field:
        if isinstance(entry, dict) and "id" in entry:
            ids.append(str(entry["id"]))
        elif isinstance(entry, str):
            # Some release-plans declare streams as a flat string array.
            ids.append(entry)
    return ids


# The 7 valid subsystem hub UIDs (children of aae9a37b tropo-subsystems root).
# Source-of-truth: collections/subsystem-hubs.collection.md + capsule v1.4.
HUB_UIDS: frozenset[str] = frozenset({
    "8dd772a0",  # tropo-governance
    "dbc1cbbf",  # tropo-rendering
    "2d083137",  # tropo-work
    "99ed55fd",  # tropo-agents
    "76bab75f",  # tropo-playbooks
    "1aba710c",  # tropo-library
    "f87e33f0",  # tropo-documentation
})


class StepError(Exception):
    """Pipeline-step failure with structured exit code.

    Code conventions (mirrors module docstring):
      1 = validation FAIL
      2 = vault inconsistency
      3 = write conflict
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[exit {self.code}] {self.message}"


# ---------------------------------------------------------------------------
# Pure functions (testable without vault I/O)
# ---------------------------------------------------------------------------


def derive_subsystems_with_audit(
    capabilities: list[str],
    member_of_map: dict[str, list[str]],
    hub_uids: frozenset[str] = HUB_UIDS,
) -> tuple[list[str], list[str]]:
    """1-hop graph traversal with audit trail.

    For each capability UID, look up member_of, filter to hub UIDs. Returns:
        (sorted_subsystems_touched, non_hub_capabilities)

    The second tuple element is the audit trail Stream B2 round 2 fold added:
    capabilities whose `member_of:` array contains zero subsystem hub UIDs are
    silently filtered from the subsystems set (per soft-WARN Check 20 at
    v1.9.x; promoted to ERROR at v1.10). Surfacing them in the audit trail
    closes the v1.9.2 class signature ("rule in prose, not in mechanism").

    Raises StepError(2) if any capability UID is missing from member_of_map.
    """
    subsystems: set[str] = set()
    non_hub_caps: list[str] = []
    for cap_uid in capabilities:
        if cap_uid not in member_of_map:
            raise StepError(2, f"capability UID {cap_uid} not found in vault index")
        cap_hub_parents = [p for p in member_of_map[cap_uid] if p in hub_uids]
        if not cap_hub_parents:
            non_hub_caps.append(cap_uid)
        else:
            for p in cap_hub_parents:
                subsystems.add(p)
    return sorted(subsystems), non_hub_caps


def derive_subsystems_touched(
    capabilities: list[str],
    member_of_map: dict[str, list[str]],
    hub_uids: frozenset[str] = HUB_UIDS,
) -> list[str]:
    """Backward-compatible wrapper around derive_subsystems_with_audit.

    Returns only the sorted subsystems_touched list. Used by external callers
    (test-runner.py) that don't need the audit trail.
    """
    subsystems, _ = derive_subsystems_with_audit(capabilities, member_of_map, hub_uids)
    return subsystems


def validate_hub_summaries(
    subsystems: list[str],
    hub_summaries: dict[str, str],
) -> list[str]:
    """Returns list of hub UIDs missing from hub_summaries (empty list = valid).

    Per release-plan.capsule v1.3 Check 21: every derived subsystem hub MUST
    have a hub_summaries entry. Honor-system at v1.9.2-v1.9.x; ERROR at v1.10.

    Caller decides whether to FAIL or continue on missing entries.
    """
    return [h for h in subsystems if h not in hub_summaries]


def validate_summary_lengths(
    hub_summaries: dict[str, str],
    min_chars: int = 50,
    max_chars: int = 1500,
) -> list[tuple[str, str]]:
    """Returns list of (hub_uid, reason) for summaries failing length bounds.

    Per release-plan.capsule v1.3 Check 22: each summary text >= 50 chars
    (no placeholder rows like "v1.X.Y ship: TBD") AND <= 1500 chars (caps
    hub frontmatter readability).
    """
    failures: list[tuple[str, str]] = []
    for hub_uid, text in hub_summaries.items():
        n = len(text or "")
        if n < min_chars:
            failures.append((hub_uid, f"summary too short ({n} chars; minimum {min_chars})"))
        elif n > max_chars:
            failures.append((hub_uid, f"summary too long ({n} chars; maximum {max_chars})"))
    return failures


def allocate_registry_uid() -> str:
    """8-hex random UID for a subsystem-registry.jsonl row."""
    return secrets.token_hex(4)


def build_release_history_row(
    release_uid: str,
    release_version: str,
    summary: str,
    registry_uid: str,
) -> str:
    """Render a release_history row as YAML text (no leading dash; the
    surgical editor handles indentation + list-item structure).

    Layout matches the manual scripts (append-v1-X-hub-rows.py) for
    visual consistency in hub frontmatter diffs.
    """
    # JSON-escape the summary for safe single-line YAML embedding.
    # YAML's single-quoted scalar is the safest for arbitrary text containing
    # double-quotes, colons, etc.; we escape any embedded single-quotes by
    # doubling them per YAML 1.2 §7.4.1.
    escaped_summary = summary.replace("'", "''")
    return (
        f"  - release_uid: {release_uid}\n"
        f"    release_version: \"{release_version}\"\n"
        f"    summary: '{escaped_summary}'\n"
        f"    registry_uid: {registry_uid}\n"
        f"    derived_from: capabilities_touched\n"
    )


# ---------------------------------------------------------------------------
# Vault I/O (depends on filesystem)
# ---------------------------------------------------------------------------


_UID_PATH_CACHE: dict[str, Path] = {}


def find_vault_entry(uid: str, vault_root: Path) -> Path:
    """Resolve a UID to its file path across the Studio.

    Fast path: `vault/files/<uid>.md`. Fallback: scan known kernel directories
    where governed primitives live (capsule definitions, boot config files,
    boot extensions, playbooks, root files, KB articles, .tropo-studio entries).

    Cross-folder lookup is required because `capabilities_touched:` may
    reference any governed primitive (capsule at `.tropo/capsules/`, Tier 1
    boot config at `.tropo/boot-config.md`, Tier 3 extension at
    `agents/<name>/agent-boot.extension.md`, etc.) — not just vault/files/.
    The cold-boot 142 Q3 P3 cross-folder UID-resolution gap (carry-forward
    3d7c387f §4.3 deferred to v1.10) surfaced empirically when this executor
    was first fired against v1.9.2's own substrate at Stream C4 — the cycle's
    own dogfood gate caught the defect. Fixed forward per cycle doctrine:
    extend the resolver, do NOT substitute manually.

    Cache: scan results are memoized in `_UID_PATH_CACHE` to avoid re-reading
    files across multiple calls within one executor run. The cache is module-
    scoped, lifetime-limited to one run (each CLI invocation gets a fresh
    process).

    Raises StepError(2) if the UID is not found in any known location.
    """
    if uid in _UID_PATH_CACHE:
        return _UID_PATH_CACHE[uid]

    # Fast path: vault/files/<uid>.md
    candidate = vault_root / "vault" / "files" / f"{uid}.md"
    if candidate.exists():
        _UID_PATH_CACHE[uid] = candidate
        return candidate

    # Fallback: scan known kernel directories. Order matches frequency in
    # capabilities_touched arrays observed across v1.6 → v1.9.1 release entries.
    scan_dirs: list[tuple[Path, str]] = [
        (vault_root / ".tropo" / "capsules", "*.capsule.md"),
        (vault_root / ".tropo" / "playbooks", "*.playbook.md"),
        (vault_root / ".tropo-studio", "*.md"),
        (vault_root / ".tropo-studio" / "memory", "*.md"),
        (vault_root / ".tropo", "*.md"),
        (vault_root / "agents", "agent-boot.extension.md"),
    ]

    for scan_dir, glob_pattern in scan_dirs:
        if not scan_dir.exists():
            continue
        for candidate_file in scan_dir.glob(f"**/{glob_pattern}"):
            if not candidate_file.is_file():
                continue
            try:
                fm, _, _ = parse_frontmatter(candidate_file)
            except StepError:
                continue  # malformed frontmatter; skip
            if fm.get("uid") == uid:
                _UID_PATH_CACHE[uid] = candidate_file
                return candidate_file

    # Last-resort: glob across the entire studio for any .md with matching
    # frontmatter UID. Slow but correct. Caps cost via the cache above.
    for candidate_file in vault_root.glob("**/*.md"):
        if not candidate_file.is_file():
            continue
        # Skip noise dirs (frozen historical snapshots, archive, etc.)
        rel = candidate_file.relative_to(vault_root)
        if any(part in {"archive", "recycle", "releases"} for part in rel.parts):
            continue
        try:
            fm, _, _ = parse_frontmatter(candidate_file)
        except StepError:
            continue
        if fm.get("uid") == uid:
            _UID_PATH_CACHE[uid] = candidate_file
            return candidate_file

    raise StepError(2, f"UID {uid} not found in vault/files/ or known kernel directories under {vault_root}")


def parse_frontmatter(file_path: Path) -> tuple[dict, str, str]:
    """Returns (frontmatter_dict, frontmatter_raw_text, body)."""
    text = file_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise StepError(2, f"no frontmatter in {file_path}")
    end_marker = text.find("\n---\n", 4)
    if end_marker == -1:
        # File may end with --- without trailing newline; try alternate.
        end_marker = text.find("\n---", 4)
        if end_marker == -1 or text[end_marker + 4 :].strip():
            raise StepError(2, f"malformed frontmatter in {file_path}")
    fm_raw = text[4:end_marker]
    body = text[end_marker + 5 :] if text[end_marker:].startswith("\n---\n") else text[end_marker + 4 :]
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as e:
        raise StepError(2, f"invalid YAML frontmatter in {file_path}: {e}")
    return fm, fm_raw, body


def build_member_of_map(capabilities: list[str], vault_root: Path) -> dict[str, list[str]]:
    """For each capability UID, read its file's `member_of:` array."""
    result: dict[str, list[str]] = {}
    for cap_uid in capabilities:
        cap_path = find_vault_entry(cap_uid, vault_root)
        fm, _, _ = parse_frontmatter(cap_path)
        member_of = fm.get("member_of") or []
        if not isinstance(member_of, list):
            raise StepError(2, f"capability {cap_uid} has non-list member_of: {member_of!r}")
        result[cap_uid] = [str(u) for u in member_of]
    return result


def prepend_release_history_row(
    hub_path: Path,
    row_text: str,
    release_uid: str | None = None,
) -> bool:
    """Surgical edit: insert a release_history row at the top of the array.

    Returns True if row was prepended, False if skipped via idempotency guard.

    **Idempotency guard (Stream B2 round 2 fold):** if `release_uid` is
    provided AND a row referencing this release_uid already exists anywhere in
    the file, skip the prepend (return False). This prevents partial-state
    re-fires from producing duplicate rows: if the executor failed mid-loop on
    a prior fire and is being re-fired, hubs that already got their row are
    skipped; only the missing hubs get written.

    Preserves all existing rows + comments + ordering. Pattern matches
    `append-v1-9-1-hub-rows.py` for consistency with the three manual cycles'
    approach.
    """
    text = hub_path.read_text(encoding="utf-8")

    if release_uid is not None:
        # Idempotency check: does any existing row in this file reference the
        # given release_uid? If yes, the row was already written on a prior
        # (possibly partial) fire — skip without modification.
        if re.search(rf"release_uid:\s*{re.escape(release_uid)}\b", text):
            return False

    pattern = re.compile(r"^(release_history:\s*\n)", re.MULTILINE)
    if not pattern.search(text):
        raise StepError(
            2, f"hub {hub_path.name} has no release_history field — cannot prepend row"
        )
    new_text = pattern.sub(r"\1" + row_text, text, count=1)
    hub_path.write_text(new_text, encoding="utf-8")
    return True


def bump_last_release_reflected(hub_path: Path, version: str) -> None:
    """Surgical edit: replace last_release_reflected scalar value."""
    text = hub_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r'^(last_release_reflected:\s*)(?:"[^"]*"|\'[^\']*\'|null|~)\s*$',
        re.MULTILINE,
    )
    if not pattern.search(text):
        raise StepError(
            2, f"hub {hub_path.name} has no last_release_reflected field"
        )
    new_text = pattern.sub(rf'\1"{version}"', text, count=1)
    hub_path.write_text(new_text, encoding="utf-8")


def append_registry_row(row: dict, registry_path: Path, dedup: bool = True) -> bool:
    """Append a JSONL row to subsystem-registry.jsonl.

    Returns True if appended, False if skipped via dedup.

    **Dedup guard (Stream B2 round 2 fold):** if `dedup` is True (default) AND
    a row with the same `(release_uid, subsystem_uid)` pair already exists in
    the registry file, skip the append. Same shape as the hub-side
    idempotency guard: prevents partial-state re-fires from producing orphan
    registry rows. The `uid:` (registry_uid) field is non-deterministic per
    `secrets.token_hex` — so re-firing without dedup would orphan the prior
    partial fire's registry rows; with dedup, the prior row is preserved.
    """
    if dedup and registry_path.exists():
        target_release = row.get("release_uid")
        target_subsystem = row.get("subsystem_uid")
        if target_release and target_subsystem:
            existing_text = registry_path.read_text(encoding="utf-8")
            for line in existing_text.splitlines():
                if not line.strip():
                    continue
                try:
                    existing = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    existing.get("release_uid") == target_release
                    and existing.get("subsystem_uid") == target_subsystem
                ):
                    return False

    line_text = json.dumps(row, sort_keys=True, separators=(", ", ": "))
    with registry_path.open("a", encoding="utf-8") as f:
        f.write(line_text + "\n")
    return True


def set_subsystems_touched(release_path: Path, subsystems: list[str]) -> None:
    """Replace or insert subsystems_touched: array in the release entry frontmatter.

    Three cases:
      (a) field already present as a list literal `[...]` (with optional
          trailing inline comment `# ...`) → replace value, drop comment
      (b) field already present as a YAML block list (multi-line) → replace block
      (c) field absent → insert before the closing `---` of the frontmatter

    Round 4 fold (v1.9.2 Stream C4 dogfood gate caught a defect): the inline
    pattern previously required `\\s*$` immediately after `]`, which failed on
    `subsystems_touched: []   # populated by ...` (trailing comment). The
    executor fell through to case (c) and *inserted a duplicate field* below
    the original. Fixed by allowing optional `\\s+#.*` after the bracket.
    """
    text = release_path.read_text(encoding="utf-8")
    yaml_value = "[]" if not subsystems else "\n" + "\n".join(f"  - {uid}" for uid in subsystems)

    # Case (a): inline list `subsystems_touched: [a, b, c]` or `subsystems_touched: []`
    # — with optional trailing inline YAML comment (`# populated by ...`).
    # Round 4 fold: previously required `\s*$` immediately after `]` which
    # failed on inline-comment-with-trailing-text; now accepts optional
    # whitespace + `#` comment through end of line.
    inline_pattern = re.compile(
        r"^(subsystems_touched:\s*)\[[^\]]*\][ \t]*(?:#.*)?$", re.MULTILINE
    )
    if inline_pattern.search(text):
        new_text = inline_pattern.sub(rf"\1{yaml_value}", text, count=1)
        release_path.write_text(new_text, encoding="utf-8")
        return

    # Case (b): block list (`subsystems_touched:\n  - foo\n  - bar`)
    block_pattern = re.compile(
        r"^(subsystems_touched:)\s*\n((?:[ \t]+- .+\n)+)", re.MULTILINE
    )
    if block_pattern.search(text):
        new_text = block_pattern.sub(rf"\1{yaml_value}\n", text, count=1)
        release_path.write_text(new_text, encoding="utf-8")
        return

    # Case (c): field absent — insert before frontmatter close
    if text.startswith("---\n"):
        end_marker = text.find("\n---\n", 4)
        if end_marker == -1:
            raise StepError(2, f"malformed frontmatter in {release_path}")
        insertion = f"subsystems_touched: {yaml_value}\n"
        new_text = text[:end_marker] + "\n" + insertion + text[end_marker + 1 :]
        release_path.write_text(new_text, encoding="utf-8")
        return

    raise StepError(2, f"could not locate frontmatter boundary in {release_path}")


# ---------------------------------------------------------------------------
# CLI driver
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-fire Rule 12 hub release_history derivation (v1.9.2 dev-pipeline step)."
    )
    parser.add_argument("--release-plan-uid", required=False, default=None, help="UID of the release-plan vault entry. v1.27.0 amendment: OPTIONAL — brief-based releases (post-v1.21.0 pattern) declare capabilities_touched + hub_summaries directly on the release entry; pass --release-plan-uid only for legacy plan-based releases.")
    parser.add_argument("--release-entry-uid", required=True, help="UID of the release vault entry.")
    parser.add_argument("--build-entry-uid", default=None, help="UID of the build vault entry (informational; not currently consumed).")
    parser.add_argument(
        "--vault-root",
        default=str(Path(__file__).resolve().parent.parent.parent.parent),
        help="Path to the Studio root (containing vault/, .tropo-studio/, etc.). Defaults to four levels up from this script.",
    )
    parser.add_argument(
        "--registry-path",
        default=None,
        help="Path to subsystem-registry.jsonl. Defaults to <vault-root>/subsystem-registry.jsonl.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print would-write manifest; no vault writes.")
    parser.add_argument(
        "--require-summaries",
        action="store_true",
        default=True,
        help="FAIL if hub_summaries is missing entries for derived hubs (default: true; honor-system Check 21).",
    )
    parser.add_argument(
        "--no-require-summaries",
        action="store_false",
        dest="require_summaries",
        help="Skip hub_summaries coverage check (use for legacy fixtures only; not for production).",
    )
    parser.add_argument(
        "--executor-agent",
        default="unknown-agent",
        help="Spawner agent identifier (e.g., 'argus-a49') — written to the registry row's `created_by` field. Default: unknown-agent.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    """Main step logic. Returns exit code."""
    vault_root = Path(args.vault_root).resolve()
    registry_path = (
        Path(args.registry_path) if args.registry_path else vault_root / "subsystem-registry.jsonl"
    )

    # 1. Load release entry frontmatter
    release_path = find_vault_entry(args.release_entry_uid, vault_root)
    release_fm, _, _ = parse_frontmatter(release_path)

    # v1.27.0 Stream B amendment: brief-based fallback. When --release-plan-uid is not provided,
    # read capabilities_touched + hub_summaries directly from the release entry (post-v1.21.0 pattern).
    # When --release-plan-uid is provided, read from the plan (legacy pattern).
    if args.release_plan_uid:
        plan_path = find_vault_entry(args.release_plan_uid, vault_root)
        plan_fm, _, _ = parse_frontmatter(plan_path)
        source_label = f"release-plan {args.release_plan_uid}"
    else:
        # Brief-based path — read from release entry itself
        plan_fm = release_fm
        source_label = f"release entry {args.release_entry_uid} (brief-based; no plan)"

    capabilities = plan_fm.get("capabilities_touched") or []
    hub_summaries = plan_fm.get("hub_summaries") or {}
    if not isinstance(capabilities, list):
        raise StepError(1, f"capabilities_touched must be a list; got {type(capabilities).__name__}")
    if not isinstance(hub_summaries, dict):
        raise StepError(1, f"hub_summaries must be a map; got {type(hub_summaries).__name__}")

    release_version = (
        release_fm.get("release_version")
        or release_fm.get("version")
        or plan_fm.get("target_release")
    )
    if not release_version:
        raise StepError(1, "release entry has no release_version or version; cannot proceed")
    # Strip any leading "v" — semver field expects "1.9.2" not "v1.9.2".
    release_version = str(release_version).lstrip("v")

    # 2. Build member_of map by reading each capability's frontmatter
    member_of_map = build_member_of_map([str(c) for c in capabilities], vault_root)

    # 3. Derive subsystems_touched + audit non-hub-member capabilities
    subsystems, non_hub_caps = derive_subsystems_with_audit(
        [str(c) for c in capabilities], member_of_map, HUB_UIDS
    )

    # Surface silent-filter audit (Stream B2 round 2 fold). Capabilities whose
    # member_of has zero subsystem hubs are dropped from subsystems_touched
    # derivation. The capsule's Check 20 labels this WARNING-level at v1.9.x;
    # the executor enforces by emitting the warning to stderr + manifest.
    if non_hub_caps:
        print(
            f"WARNING: {len(non_hub_caps)} capability/capabilities have no "
            f"subsystem hub in their member_of: {non_hub_caps}. These were "
            f"silently filtered from subsystems_touched derivation. Per "
            f"release-plan.capsule v1.3 + Check 20 (WARNING at v1.9.x; ERROR "
            f"at v1.10), each capability should belong to exactly one of the "
            f"7 subsystem hubs. Verify these UIDs are correctly tagged.",
            file=sys.stderr,
        )

    # 4. Validate hub_summaries coverage (Check 21, honor-system at v1.9.2)
    if args.require_summaries:
        missing = validate_hub_summaries(subsystems, hub_summaries)
        if missing:
            raise StepError(
                1,
                f"hub_summaries missing entries for derived hubs: {missing}. "
                f"Per release-plan.capsule v1.3 Check 21, every derived subsystem hub "
                f"must have a hub_summaries entry at status:locked.",
            )

    # 5. Validate summary lengths (Check 22)
    length_failures = validate_summary_lengths(
        {h: hub_summaries[h] for h in subsystems if h in hub_summaries}
    )
    if length_failures:
        raise StepError(
            1,
            "hub_summaries entries fail length bounds (Check 22): "
            + "; ".join(f"{h}: {reason}" for h, reason in length_failures),
        )

    # 6. Allocate registry UIDs (deterministic ordering since subsystems is sorted)
    registry_uids = {h: allocate_registry_uid() for h in subsystems}

    # 7. Dry-run: print would-write manifest and exit 0
    if args.dry_run:
        manifest = {
            "event": "dry_run_complete",
            "step": "update-subsystem-canonical-docs",
            "release_plan_uid": args.release_plan_uid,
            "release_entry_uid": args.release_entry_uid,
            "release_version": release_version,
            "capabilities_touched": capabilities,
            "subsystems_touched_derived": subsystems,
            "silently_filtered_non_hub_caps": non_hub_caps,
            "registry_uids_would_allocate": registry_uids,
            "hub_summaries_validated": True,
            "writes_skipped": True,
            "writes_planned": [
                {
                    "kind": "hub_release_history_prepend",
                    "hub_uid": h,
                    "row_summary": hub_summaries[h][:80] + ("…" if len(hub_summaries[h]) > 80 else ""),
                }
                for h in subsystems
            ]
            + [
                {"kind": "hub_last_release_reflected_bump", "hub_uid": h, "to_version": release_version}
                for h in subsystems
            ]
            + [
                {"kind": "registry_row_append", "registry_uid": registry_uids[h], "subsystem_uid": h}
                for h in subsystems
            ]
            + [
                {"kind": "release_subsystems_touched_set", "release_uid": args.release_entry_uid, "subsystems": subsystems}
            ],
        }
        print(json.dumps(manifest, indent=2))
        return 0

    # 8. Apply: hub frontmatter writes (idempotent — skip hubs that already
    # have a row for this release_uid from a partial prior fire)
    hubs_written: list[str] = []
    hubs_skipped_idempotent: list[str] = []
    for hub_uid in subsystems:
        hub_path = find_vault_entry(hub_uid, vault_root)
        registry_uid = registry_uids[hub_uid]
        row_text = build_release_history_row(
            release_uid=args.release_entry_uid,
            release_version=release_version,
            summary=hub_summaries[hub_uid],
            registry_uid=registry_uid,
        )
        wrote = prepend_release_history_row(
            hub_path, row_text, release_uid=args.release_entry_uid
        )
        if wrote:
            bump_last_release_reflected(hub_path, release_version)
            hubs_written.append(hub_uid)
        else:
            hubs_skipped_idempotent.append(hub_uid)

    # 9. Apply: registry rows (deduped on (release_uid, subsystem_uid) pair)
    # Round 4 fold (v1.9.2 Stream C4 dogfood gate caught a defect): the
    # registry row schema must match v1.9.1 + earlier rows — 11 fields total:
    # uid, subsystem_uid, subsystem_name, release_uid, release_version,
    # row_type, summary, streams_touched, derived_from, created, created_by.
    # Round 1 executor wrote only 6; surfaced at first production fire.
    today_iso = datetime.date.today().isoformat()
    streams_touched = _extract_stream_ids(plan_fm.get("streams") or [])
    registry_rows_appended: list[str] = []
    registry_rows_skipped_dedup: list[str] = []
    for hub_uid in subsystems:
        # Look up the hub's `subsystem_name:` slug from its frontmatter.
        hub_path = find_vault_entry(hub_uid, vault_root)
        hub_fm, _, _ = parse_frontmatter(hub_path)
        subsystem_name = hub_fm.get("subsystem_name", hub_uid)

        registry_row = {
            "uid": registry_uids[hub_uid],
            "subsystem_uid": hub_uid,
            "subsystem_name": subsystem_name,
            "release_uid": args.release_entry_uid,
            "release_version": release_version,
            "row_type": "per-release",
            "summary": hub_summaries[hub_uid],
            "streams_touched": streams_touched,
            "derived_from": "capabilities_touched",
            "created": today_iso,
            "created_by": args.executor_agent,
        }
        appended = append_registry_row(registry_row, registry_path, dedup=True)
        if appended:
            registry_rows_appended.append(registry_uids[hub_uid])
        else:
            registry_rows_skipped_dedup.append(hub_uid)

    # 10. Apply: release entry's subsystems_touched (naturally idempotent —
    # re-running produces the same set on the same release-plan inputs)
    set_subsystems_touched(release_path, subsystems)

    # 11. Emit run.jsonl-shaped manifest with full audit trail
    manifest = {
        "event": "step_complete",
        "step": "update-subsystem-canonical-docs",
        "step_workflow_node_uid": "9d4f7e21",
        "release_plan_uid": args.release_plan_uid,
        "release_entry_uid": args.release_entry_uid,
        "release_version": release_version,
        "outputs": {
            "subsystems_touched": subsystems,
            "hubs_written": hubs_written,
            "hubs_skipped_idempotent": hubs_skipped_idempotent,
            "registry_rows_appended": registry_rows_appended,
            "registry_rows_skipped_dedup": registry_rows_skipped_dedup,
            "registry_uids_allocated": registry_uids,
            "silently_filtered_non_hub_caps": non_hub_caps,
        },
    }
    print(json.dumps(manifest, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except StepError as e:
        print(str(e), file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
