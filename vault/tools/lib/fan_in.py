"""Fan-in rows and the reservation gate (0a0a6777 AC5, contract §4).

AC5: "Each fan-in row binds dev-spec UID/SHA, activation UID, pipeline-run UID,
tested final commit, completion receipt hash, and acceptance evidence hash; only
status done rows unreserved by another live release are legal."

WHAT A ROW IS FOR
-----------------
A release fans in several dev-specs, and the release's whole claim is "these
exact pieces of work, verified in these exact states, are what shipped". A row
is that claim for one dev-spec, and every one of the six bindings exists because
without it the claim degrades to something weaker that still LOOKS complete:

  dev_spec_uid          which work
  dev_spec_sha256       ...in which exact text. Without it the row names a
                        moving target: the spec can be edited after the release
                        cites it and the citation still "resolves".
  activation_uid        which cycle ran it
  pipeline_run_uid      which run of that cycle
  tested_final_commit   which tree the evidence was produced against (stage 3's
                        one unchanged tested SHA, carried forward into release)
  completion_receipt_sha256   the receipt that says it finished
  acceptance_evidence_sha256  the evidence that says it finished CORRECTLY

The last two are separate on purpose. A completion receipt says the run reached
its end; acceptance evidence says the ACs passed. Folding them into one hash
would let a run that finished-but-failed present the same shape as one that
finished-and-passed.

WARN-SAFE AUDIT (deb77758, requested by argus-a147)
---------------------------------------------------
Mike's rule: a refusal must name the irreversible harm it prevents, or be a
warning that proceeds and records. Every refusal in this module was priced
against it, and they all fall in the false-success class deb77758 names as
earning fail-closed — a green result that would be believed while wrong:

  incomplete row      a row with a gap still RENDERS as a row, so an unbound
                      claim ships looking complete
  unbindable value    `tested_final_commit: HEAD` has the field and identifies
                      no tree; presence without shape is the same false success
  member not done     the release's digest would attest to work still moving
  member reserved     two live releases each produce an honest digest for a
                      world where the other does not exist
  duplicate member    counted twice by the digest
  empty plan          a valid digest over zero rows: a release attesting to
                      nothing, and there is no unlock gesture to undo it

The one I reconsidered is the empty plan. It looked like reversible bookkeeping
until I asked what reverses it: the lock opens a run and an activation root, and
the studio has no unlock. So the cure is cancel-and-recycle-three-entries, and
the artifact in the meantime is a release that claims to contain nothing. Kept.

None of these sits on a hot path. An ignition is a rare deliberate gesture, not
a per-step check, so the cost deb77758 warns about — a gate paying its price on
every pass forever — does not apply here.

THE RESERVATION GATE
--------------------
A dev-spec may be fanned into ONE live release. Without that rule the same work
can be claimed by two in-flight releases, and both of their fan-in digests are
honest about a world where the other does not exist. Reservations are read from
the release-plans themselves rather than written onto the dev-spec: the claim
belongs to the claimant, and a dev-spec that carried its own reservation flag
would need a compensating write every time a release was cancelled — a second
place for the truth to rot.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

#: The six bindings AC5 requires, in the order the spec names them.
REQUIRED_ROW_FIELDS = (
    "dev_spec_uid",
    "dev_spec_sha256",
    "activation_uid",
    "pipeline_run_uid",
    "tested_final_commit",
    "completion_receipt_sha256",
    "acceptance_evidence_sha256",
)

#: The release-plan statuses that explicitly hold NO reservation, from the
#: capsule's own enforced_enums (a3f1e7b2) plus the `locked` value 0a0a6777 §3
#: adds: {design, specify, locked, active, build, done, cancelled}.
#:
#: `design` and `specify` are pre-lock — a reservation is created BY the lock, so
#: a plan that has not locked has claimed nothing even if it already lists
#: members. `done` has consumed its reservations and `cancelled` has abandoned
#: them; both must release, or cancelling a release would strand its members
#: forever with no cure but editing history.
#:
#: My first version of this listed "in-progress" and "building", which are not in
#: the enum. I invented them, four hours after argus-a147 corrected me for
#: inventing `status: deprecated`. Enumerating the RELEASING side and treating
#: everything else as holding is also the fail-closed direction: an unrecognized
#: status keeps the reservation and refuses the new claim, because a refused
#: claim is recoverable and a double claim is not.
RESERVATION_RELEASING_STATUSES = frozenset(
    {"design", "specify", "done", "cancelled"}
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
UID_RE = re.compile(r"^[0-9a-f]{8}$")


class FanInRefusal(Exception):
    """A fan-in row or reservation precondition is false."""


@dataclass(frozen=True)
class FanInRow:
    dev_spec_uid: str
    dev_spec_sha256: str
    activation_uid: str
    pipeline_run_uid: str
    tested_final_commit: str
    completion_receipt_sha256: str
    acceptance_evidence_sha256: str

    def as_dict(self) -> dict:
        return asdict(self)


def validate_row(row: dict) -> FanInRow:
    """Every binding present and well-shaped, or refuse naming the field.

    Shape is checked, not just presence. A row carrying
    `tested_final_commit: "HEAD"` has the field and binds nothing; an
    abbreviated SHA names a prefix that can collide. The point of the row is
    that it identifies exactly one thing per column.
    """
    missing = [f for f in REQUIRED_ROW_FIELDS if not row.get(f)]
    if missing:
        raise FanInRefusal(
            f"fan-in row for {row.get('dev_spec_uid') or '<no dev-spec>'} is missing "
            f"{len(missing)} required binding(s): {', '.join(missing)}. AC5 requires "
            "all seven; a row with a gap still renders as a row and would let an "
            "unbound claim ship looking complete."
        )

    for field_name in ("dev_spec_uid", "activation_uid", "pipeline_run_uid"):
        if not UID_RE.match(str(row[field_name])):
            raise FanInRefusal(
                f"{field_name}={row[field_name]!r} is not an 8-hex UID"
            )
    if not COMMIT_RE.match(str(row["tested_final_commit"])):
        raise FanInRefusal(
            f"tested_final_commit={row['tested_final_commit']!r} is not a 40-hex "
            "commit. An abbreviation or a symbolic name does not identify one tree, "
            "which is the only thing this column is for."
        )
    for field_name in ("dev_spec_sha256", "completion_receipt_sha256",
                       "acceptance_evidence_sha256"):
        if not SHA256_RE.match(str(row[field_name])):
            raise FanInRefusal(f"{field_name}={row[field_name]!r} is not a 64-hex SHA-256")

    return FanInRow(**{f: str(row[f]) for f in REQUIRED_ROW_FIELDS})


def manifest_digest(rows: Iterable[FanInRow]) -> str:
    """The digest recorded as `fan_in_digest` on the locked release-plan.

    Computed over the rows in their PLAN ORDER, not sorted. The plan's
    `dev_spec_uids` is explicitly ordered by the contract, so two plans with the
    same members in a different order are different plans and must not share a
    digest.
    """
    payload = json.dumps([r.as_dict() for r in rows], sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_manifest(rows: Iterable[FanInRow], release_plan_uid: str) -> str:
    rows = list(rows)
    return json.dumps(
        {
            "release_plan_uid": release_plan_uid,
            "row_count": len(rows),
            "rows": [r.as_dict() for r in rows],
            "fan_in_digest": manifest_digest(rows),
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def find_conflicting_reservation(
    dev_spec_uid: str,
    release_plans: Iterable[dict],
    claiming_plan_uid: str,
) -> Optional[str]:
    """Is this dev-spec already fanned into another LIVE release-plan?

    Returns the conflicting plan's UID, or None. The claiming plan is skipped so
    that re-locking the same plan is a retry rather than a self-conflict — which
    is the difference between idempotence and deadlock.
    """
    for plan in release_plans:
        uid = str(plan.get("uid") or "")
        if not uid or uid == claiming_plan_uid:
            continue
        status = str(plan.get("status") or "").strip().lower()
        if status in RESERVATION_RELEASING_STATUSES:
            continue
        if dev_spec_uid in (plan.get("dev_spec_uids") or []):
            return uid
    return None


def assert_member_is_fannable(
    dev_spec: dict,
    release_plans: Iterable[dict],
    claiming_plan_uid: str,
) -> None:
    """AC5's gate: `done`, and unreserved by another live release.

    Both halves refuse loudly and separately, because they are different
    problems with different cures: "not finished yet" is a scheduling fact, and
    "already claimed" is a conflict between two releases that someone has to
    adjudicate.
    """
    uid = str(dev_spec.get("uid") or "<unknown>")
    status = str(dev_spec.get("status") or "").strip().lower()
    if status != "done":
        raise FanInRefusal(
            f"dev-spec {uid} is status {status!r}, not 'done'. A release fans in "
            "FINISHED work; admitting anything else would let the release's own "
            "digest attest to work that is still moving."
        )

    conflict = find_conflicting_reservation(uid, release_plans, claiming_plan_uid)
    if conflict is not None:
        raise FanInRefusal(
            f"dev-spec {uid} is already reserved by live release-plan {conflict}. "
            "One dev-spec fans into one live release: two plans claiming it would "
            "each produce an honest fan-in digest for a world where the other does "
            "not exist. Cure: cancel or supersede one plan, or drop the member."
        )


def build_rows(
    members: list[dict],
    release_plans: Iterable[dict],
    claiming_plan_uid: str,
) -> list[FanInRow]:
    """Validate every member and every row before returning any of them.

    All-or-nothing on purpose: this feeds a lock transaction whose plan phase
    must be pure, so a member that fails the gate has to stop the whole plan
    rather than silently shrink the release.
    """
    plans = list(release_plans)
    seen: set[str] = set()
    rows: list[FanInRow] = []
    for member in members:
        dev_spec = member["dev_spec"]
        uid = str(dev_spec.get("uid") or "")
        if uid in seen:
            raise FanInRefusal(
                f"dev-spec {uid} appears twice in the plan's ordered members; a "
                "duplicate member would be counted twice by the digest"
            )
        seen.add(uid)
        assert_member_is_fannable(dev_spec, plans, claiming_plan_uid)
        rows.append(validate_row(member["row"]))
    if not rows:
        raise FanInRefusal(
            "a release-plan lock with zero members has nothing to fan in; an empty "
            "manifest would still produce a valid digest, which is the shape of a "
            "release that attests to nothing"
        )
    return rows
