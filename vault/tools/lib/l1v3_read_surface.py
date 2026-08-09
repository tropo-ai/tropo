"""lib/l1v3_read_surface.py — the remaining read-side surfaces of the L1v3
Data Contract that are not the journal, the merge, or the ref-closure.

Dev-spec 3c13977e §Read Contract items 2 (segment, R3), 4 (/api/vaults), 6
(scope-vs-location lint), 7 (studio-health); test-spec c56b9cc0 assertions
A3, A7, A8. Each surface reads a DURABLE or DERIVED-BUT-REBUILDABLE source and
never invents state.

  - segment (R3)          — DERIVED via segment.derive_segment, never a
                            hand-editable node field. Reads expose the derived
                            value; a write that sets a disagreeing hand-authored
                            `segment` is refused/ignored, derived stays
                            authoritative.
  - /api/vaults           — memberCount from the B4 group registry (the
                            GroupResolver), NEVER GitHub (GitHub membership is
                            derived + drift-prone — 5d3ab142 §3), always paired
                            with a non-null countAsOf.
  - scope-vs-location     — ERROR-class: a private file physically inside a
                            shared clone tree (the misplaced-draft the next
                            publish would sweep up).
  - studio-health         — vault-INDEPENDENT ERROR count for the shell chrome;
                            aggregates misplaced drafts + durable blocked jobs
                            (+ injected drift inputs). Because it reads the lint
                            + the durable journal (never the rebuildable index),
                            its counts agree with the durable job record before
                            AND after a full rebuild (A8).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from lib.segment import derive_segment, normalize_extraction_scope, is_public_scope
from lib import publish_journal as pj

SEVERITY_ERROR = "ERROR"


# ---------------------------------------------------------------------------
# segment (R3) — derived, never hand-editable
# ---------------------------------------------------------------------------

def read_segment(rec: dict, vault_root: Path,
                 ship_manifest_uids: Optional[set] = None) -> str:
    """The value reads (WorkEntry.segment / GNode.segment) expose: ALWAYS the
    derivation (segment.derive_segment), NEVER the record's own `segment`
    frontmatter field. Single source of truth (R3)."""
    return derive_segment(rec, vault_root, ship_manifest_uids)


def apply_derived_segment(rec: dict, vault_root: Path,
                          ship_manifest_uids: Optional[set] = None) -> dict:
    """Write-side guard (R3): force `segment` to the DERIVED value, refusing /
    ignoring any hand-authored `segment` field. Returns a dict with the
    sanitized record plus `hand_set_rejected` (True when an incoming
    hand-authored value disagreed with the derivation and was discarded).

    The derived value is authoritative either way — this never trusts the
    node's own claim, matching segment.py's ruling that a hand-edited `segment:`
    never governs.
    """
    derived = derive_segment(rec, vault_root, ship_manifest_uids)
    claimed = rec.get("segment")
    hand_set_rejected = claimed is not None and str(claimed) != str(derived)
    sanitized = dict(rec)
    sanitized["segment"] = derived
    return {
        "record": sanitized,
        "segment": derived,
        "hand_set_rejected": hand_set_rejected,
        "rejected_value": claimed if hand_set_rejected else None,
    }


# ---------------------------------------------------------------------------
# scope-vs-location lint (item 6) — ERROR-class misplaced drafts
# ---------------------------------------------------------------------------

def scope_vs_location_lint(files: Iterable[Mapping]) -> list[dict]:
    """Return ERROR-class findings for private files physically located in a
    shared clone tree. Each `file` is a mapping with `path`, `extraction_scope`,
    and `in_shared_tree` (bool — is the file physically inside a shared clone?).

    A file is a misplaced draft when it is NOT public scope (private / draft)
    AND it sits in the shared tree — the next publish would sweep it up. Public
    files in the shared tree are correct; private files in the private tree are
    correct; only private-in-shared is the ERROR.
    """
    findings: list[dict] = []
    for f in files:
        scope = f.get("extraction_scope")
        in_shared = bool(f.get("in_shared_tree"))
        if in_shared and not is_public_scope(scope):
            findings.append({
                "kind": "misplaced-draft",
                "severity": SEVERITY_ERROR,
                "path": f.get("path"),
                "extraction_scope": normalize_extraction_scope(scope) or None,
                "detail": (
                    "private file physically located in a shared clone tree; "
                    "the next publish would sweep it up — move it before publish"
                ),
            })
    return findings


# ---------------------------------------------------------------------------
# studio-health (item 7) — vault-independent ERROR surface
# ---------------------------------------------------------------------------

# The ERROR-class condition kinds the health surface counts (dev-spec §Read
# Contract item 7). Misplaced drafts + blocked jobs are computed here from the
# lint + the durable journal; the rest are injected by their own detectors.
DRIFT_KINDS = frozenset({
    "group-drift", "acl-drift", "github-drift", "orphan-sidecar",
    "stale-plan", "remote-drift", "reconcile-failure",
})


def studio_health(
    *,
    files: Iterable[Mapping] = (),
    journal_records: Sequence[dict] = (),
    drift_findings: Iterable[Mapping] = (),
) -> dict:
    """Vault-independent studio-health surface for the shell chrome.

    Aggregates ERROR-class findings from three inputs, all of which are durable
    or physical (never the rebuildable index), so the counts are identical
    before and after a full `vault:rebuild` (A8):
      - misplaced drafts     — from the scope-vs-location lint over physical files;
      - blocked jobs         — from the durable publish-journal (carry jobId+asOf);
      - injected drift       — group/ACL/GitHub drift, orphan sidecars, stale
                               plans, remote drift, reconcile failures.
    """
    findings: list[dict] = list(scope_vs_location_lint(files))

    for rec in pj.blocked_jobs(list(journal_records)):
        findings.append({
            "kind": "blocked-job",
            "severity": SEVERITY_ERROR,
            "jobId": rec["job_uid"],
            "asOf": rec["asOf"],
            "error": rec.get("error"),
            "vault_uid": rec.get("vault_uid"),
            "destination": rec.get("destination"),
            "detail": rec.get("reason"),
        })

    for d in drift_findings:
        kind = d.get("kind")
        if kind not in DRIFT_KINDS:
            raise ValueError(
                f"studio-health drift finding kind {kind!r} is outside the "
                f"closed drift set {sorted(DRIFT_KINDS)}"
            )
        findings.append({**d, "severity": SEVERITY_ERROR})

    misplaced = [f for f in findings if f["kind"] == "misplaced-draft"]
    return {
        "errorCount": len(findings),
        "misplacedDraftCount": len(misplaced),
        "blockedJobCount": sum(1 for f in findings if f["kind"] == "blocked-job"),
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# /api/vaults (item 4) — memberCount from the B4 group registry, never GitHub
# ---------------------------------------------------------------------------

def vault_surface_row(spec: Mapping, resolver, *, count_as_of: str) -> dict:
    """One /api/vaults row: { id, name, kind, audience, segmentColor,
    memberCount, countAsOf, remoteHealth }.

    `resolver` is a lib.group_registry.GroupResolver. memberCount is the
    effective member count of the vault's audience group FROM THE REGISTRY
    (resolver.resolve_members) — never a GitHub API call — and is always paired
    with a non-null countAsOf. A registry resolution failure surfaces the typed
    GroupContractError (its code is in the contract's closed enum,
    GROUP_RESOLUTION_UNAVAILABLE) rather than a silent zero.
    """
    audience = spec.get("audience")
    result = resolver.resolve_members(audience)
    members = result.unwrap()  # raises the typed GroupContractError on failure
    if count_as_of is None:
        raise ValueError("countAsOf must be non-null (item 4: always paired)")
    return {
        "id": spec.get("id"),
        "name": spec.get("name"),
        "kind": spec.get("kind"),
        "audience": audience,
        "segmentColor": spec.get("segmentColor"),
        "memberCount": len(members),
        "countAsOf": count_as_of,
        "remoteHealth": spec.get("remoteHealth"),
    }


def vaults_surface(specs: Iterable[Mapping], resolver, *, count_as_of: str) -> list[dict]:
    return [vault_surface_row(s, resolver, count_as_of=count_as_of) for s in specs]


__all__ = [
    "SEVERITY_ERROR", "DRIFT_KINDS",
    "read_segment", "apply_derived_segment",
    "scope_vs_location_lint", "studio_health",
    "vault_surface_row", "vaults_surface",
]
