"""lib/draft_status.py — the draftStatus TWO-SOURCE MERGE resolver.

Dev-spec 3c13977e §Read Contract item 3 (§6.2 P0); cycle brief cc437616 §9;
test-spec c56b9cc0 assertion A2. This is the P0 correction the whole L1v3
contract exists to carry: draftStatus is NOT one derivation off a single field.

  draftStatus = (index extraction_scope base) ⊔ (live publish-job store overlay)

`draft`/`published` derive from the frontmatter `extraction_scope` via the
rebuildable derived index (the public/private authority is segment.py's frozen
allowlist — imported here so the two surfaces cannot disagree). `publishing`/
`blocked` are TRANSIENT job states that live in NO frontmatter and NO index
column — they come from the durable publish-journal (lib/publish_journal.py),
which a `vault:rebuild` cannot erase (A2 regression). The merge happens HERE, at
the read/API layer; `publishing`/`blocked` are NEVER written to frontmatter.

The exact matrix (dev-spec §Read Contract):

  | index base | live job state                                             | draftStatus     |
  |------------|------------------------------------------------------------|-----------------|
  | private    | none                                                       | draft           |
  | public     | none                                                       | published       |
  | any        | planned | validated | awaiting-assent                        | awaiting_assent |
  | any        | ready                                                      | ready           |
  | any        | pushed | remote-integrated | awaiting-receipt | reconciling  | publishing      |
  | any        | superseded-before-reconcile | (current) blocked            | blocked         |
  | any        | landed | landed-local | landed-then-superseded              | published       |

Only the CURRENT non-superseded job for (vault_uid, destination, uid/path set)
overlays the base; a later landed job supersedes an older blocked one (history
stays queryable, cannot permanently dominate the row) — enforced by
publish_journal.current_row_record (latest transition by append-only seq).
"""
from __future__ import annotations

from typing import Optional

from lib.segment import is_public_scope
from lib import publish_journal as pj

# The draftStatus vocabulary the cockpit renders (c27c741b §2).
DRAFT = "draft"
PUBLISHED = "published"
AWAITING_ASSENT = "awaiting_assent"
READY = "ready"
PUBLISHING = "publishing"
BLOCKED = "blocked"

# Every closed job state maps to exactly one draftStatus overlay value. This is
# the machine form of the matrix above; an unmapped state is a hard failure
# (the state space is closed — publish_journal.ALL_STATES).
_OVERLAY: dict[str, str] = {
    # awaiting-assent lane
    "planned": AWAITING_ASSENT,
    "validated": AWAITING_ASSENT,
    "awaiting-assent": AWAITING_ASSENT,
    "ready": READY,
    # in-flight → publishing
    "pushed": PUBLISHING,
    "remote-integrated": PUBLISHING,
    "awaiting-receipt": PUBLISHING,
    "pending": PUBLISHING,
    "reconciling": PUBLISHING,
    "receipt-emitted": PUBLISHING,
    # blocked lane (superseded-before-reconcile is terminal NOT-landed)
    "superseded-before-reconcile": BLOCKED,
    pj.BLOCKED: BLOCKED,
    # terminal positive → published (it landed / is shared)
    "landed": PUBLISHED,
    "landed-local": PUBLISHED,
    "landed-then-superseded": PUBLISHED,
}


def base_draft_status(extraction_scope: Optional[str]) -> str:
    """The index-side base before any overlay: public scope → published, else
    draft (fail-closed: absent/private/argo-reference/unknown → draft). Uses the
    same public allowlist as segment.py so draft-vs-published never drifts from
    the publish boundary."""
    return PUBLISHED if is_public_scope(extraction_scope) else DRAFT


def resolve_draft_status(extraction_scope: Optional[str], job_state: Optional[str]) -> str:
    """The pure two-source merge for one row. `job_state` is the CURRENT
    non-superseded overlay state (or None). Raises on a job_state outside the
    closed set — the merge never invents a value for an unknown state."""
    if job_state is None:
        return base_draft_status(extraction_scope)
    if job_state not in _OVERLAY:
        raise pj.PublishJournalValidationError(
            f"job_state {job_state!r} is outside the closed state set — the "
            f"draftStatus merge refuses to map an unknown state (A5/§9)"
        )
    return _OVERLAY[job_state]


def resolve_row(
    extraction_scope: Optional[str],
    records: list[dict],
    *,
    destination: Optional[str],
    path_set,
) -> dict:
    """Resolve one row's draftStatus against the durable journal and return the
    read-contract shape. Every read result carries `jobId` (where a job
    applies) and `asOf` (dev-spec §Read Contract: "Every read result carries
    jobId and asOf")."""
    current = pj.current_row_record(records, destination, path_set)
    if current is None:
        return {
            "draftStatus": base_draft_status(extraction_scope),
            "jobId": None,
            "asOf": None,
        }
    return {
        "draftStatus": resolve_draft_status(extraction_scope, current["state"]),
        "jobId": current["job_uid"],
        "asOf": current["asOf"],
        "error": current.get("error"),
    }


__all__ = [
    "DRAFT", "PUBLISHED", "AWAITING_ASSENT", "READY", "PUBLISHING", "BLOCKED",
    "base_draft_status", "resolve_draft_status", "resolve_row",
]
