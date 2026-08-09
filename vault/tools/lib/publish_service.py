"""lib/publish_service.py — the L1v3 write-path publish-job SERVICE (LOCAL half).

Dev-spec 3c13977e §Write Contract + §Write Library; cycle brief cc437616 §7
(job lifecycle + the meaning of "landed") and §9 (the minimum write library +
the closed error enum). Test-spec c56b9cc0 assertions A1 (landing agreement),
A4 (job store durability) and A5 (closed error enum).

WHAT THIS IS
  The write side of the L1v3 contract, sitting ON TOP of the R1 publish-journal
  STORE (lib/publish_journal.py) I already shipped. The store persists typed
  transitions; THIS module is the service that DRIVES the SOURCE/DESTINATION
  state machine through legal transitions, refuses illegal ones, and stamps
  `blocked` records with a closed-enum error. The API layer reads job state
  back through the draftStatus overlay (lib/draft_status.py) — a `vault:rebuild`
  cannot erase it because the journal is outside the derived index (R1).

THE LOCAL / D5 BOUNDARY (304badf7 — a design-brief, NOT a built dependency)
  Buildable + testable NOW — the LOCAL lifecycle (§Write Library "local ones"):
    - plan_changeset      — resolve the vault-scoped ref-closure, write the
                            immutable changeset envelope, open the job at
                            `planned`.
    - validate_changeset  — the deterministic planning + policy + privacy gate;
                            `planned → validated`, or `blocked` with a closed
                            LOCAL error (STALE_PLAN / OVERLAPPING_CHANGESET /
                            GROUP_RESOLUTION_UNAVAILABLE / POLICY_REFUSED /
                            PRIVACY_REFUSED).
    - request_assent / record_assent — the local assent prefix
                            (`validated → awaiting-assent → ready`).
    - get_publish_job     — the `jobStatus(jobId)` read shape.
    - the SOURCE/DESTINATION state machine + closed error enum + the R2
      no-optimistic-landed guard (there is NO local path to `landed`: only
      reconcile_destination reaches it, and that is D5-gated — so a clean local
      run can never optimistically show `published`).

  REQUIRES D5 (flagged, never faked) — the REMOTE half:
    - publish_changeset   — authenticated remote push + remote CAS (one-winner
                            cross-Studio contention) + signed integration
                            attestation (`ready → pushed → remote-integrated`).
    - reconcile_destination — destination compose-lock mount resolution, fetch
                            of the integrated commit, LOCAL freshen/rebuild +
                            integrity check, and a durable target reconciliation
                            receipt linked to the source attestation
                            (`pending → reconciling → receipt-emitted →
                            landed-local`; source `awaiting-receipt → landed`).
  These two raise D5FederationRequired rather than build on unbuilt infra
  (cc437616 §9: `tropo-publish.py` is transport substrate, "not itself the
  recursive folder-backed planner, merge engine, job service, or landed
  reconciler"). The local precondition is still checked first so the refusal is
  precise, and the state machine that D5 will drive is fully wired here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence

from lib import publish_journal as pj
from lib import ref_closure as rc
from lib import l1v3_read_surface as rs
from lib import draft_status as ds
from lib import github_transport as ght
from lib import receipt_ref as rref
from lib.group_registry import GroupResolver

# The immutable changeset envelope (cc437616 §8, private-local evidence tier 1)
# lives alongside the journal but is a DISTINCT artifact: the journal records
# transitions; the envelope records the plan (selection, closure, bindings) the
# transitions act on. Both are outside the derived index (R1).
CHANGESET_DIR_REL = Path(".tropo") / "publish-journal" / "changesets"

# States a brand-new job may be OPENED in (no predecessor). Everything else must
# transition from an existing record.
ENTRY_STATES = frozenset({"planned", "pending"})

# States a `blocked` job may be resumed INTO (a typed resumable_from must name
# one of these — never a terminal state, never `blocked` itself).
RESUMABLE_TARGETS = pj.ALL_STATES - pj.TERMINAL_STATES - {pj.BLOCKED}

# ---------------------------------------------------------------------------
# The legal transition table — the closed SOURCE + DESTINATION machines
# (cc437616 §7 / dev-spec §Write Contract). This is a CODE CONSTANT for the same
# reason publish_journal.SOURCE_STATES is: widening what may follow what is a
# reviewable code change, never config.
#
# R2 IS BAKED IN HERE: `landed` (source) is reachable ONLY from
# `awaiting-receipt`. `remote-integrated → landed` is deliberately ABSENT, so an
# optimistic "a remote merge means it landed" jump is an IllegalTransition — the
# hostile A1 plant. `landed-local` (destination) is reachable ONLY from
# `receipt-emitted`, i.e. after a real local reconcile.
# ---------------------------------------------------------------------------
BLOCKED = pj.BLOCKED

LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    # SOURCE
    "planned": frozenset({"validated", BLOCKED}),
    "validated": frozenset({"awaiting-assent", BLOCKED}),
    "awaiting-assent": frozenset({"ready", BLOCKED}),
    "ready": frozenset({"pushed", BLOCKED}),
    "pushed": frozenset({"remote-integrated", BLOCKED}),
    "remote-integrated": frozenset({"awaiting-receipt", BLOCKED}),
    "awaiting-receipt": frozenset({"landed", BLOCKED}),
    "landed": frozenset({"landed-then-superseded"}),
    "landed-then-superseded": frozenset(),
    # DESTINATION
    "pending": frozenset({"reconciling", "superseded-before-reconcile", BLOCKED}),
    "reconciling": frozenset({"receipt-emitted", "superseded-before-reconcile", BLOCKED}),
    "receipt-emitted": frozenset({"landed-local", BLOCKED}),
    "landed-local": frozenset(),
    "superseded-before-reconcile": frozenset(),
}

# The LOCAL slice of the closed error enum — the reasons validate_changeset can
# determine WITHOUT the remote (the rest are D5-reachable only). Every one is a
# member of publish_journal.CLOSED_ERROR_ENUM (A5).
LOCAL_ERROR_CODES = frozenset({
    "STALE_PLAN",
    "OVERLAPPING_CHANGESET",
    "GROUP_RESOLUTION_UNAVAILABLE",
    "POLICY_REFUSED",
    "PRIVACY_REFUSED",
})

# The error codes only the REMOTE half (D5) can reach — documented so the
# boundary is explicit, never silently swallowed.
D5_ONLY_ERROR_CODES = frozenset({
    "CONFLICT", "REMOTE_CHECK_FAILED", "REMOTE_CAS_FAILED", "RECONCILE_FAILED",
    "RECEIPT_REF_FAILED", "RECEIPT_INVALID", "SUPERSEDED_BEFORE_RECONCILE",
})


class PublishServiceError(Exception):
    """Base class for write-path service refusals (typed, never silent)."""


class IllegalTransition(PublishServiceError):
    """A transition the closed SOURCE/DESTINATION machine does not permit —
    including the optimistic `remote-integrated → landed` jump R2 forbids."""


class ChangesetNotFound(PublishServiceError):
    """No immutable envelope exists for the requested changeset_uid."""


class D5FederationRequired(PublishServiceError):
    """A REMOTE op that needs D5 (304badf7) federation infrastructure which is
    NOT built. Raised instead of building on missing infra (directive: FLAG,
    do not fake). Carries the exact capability the op is waiting on."""

    def __init__(self, op: str, needs: Sequence[str]):
        self.op = op
        self.needs = tuple(needs)
        needs_text = "; ".join(needs)
        super().__init__(
            f"{op} requires D5 (304badf7) federation infrastructure that is not "
            f"built — needs: {needs_text}. The local precondition passed; the "
            f"remote transition is out of scope until D5 lands (flagged, not faked)."
        )


# ---------------------------------------------------------------------------
# State-machine validation (the guard the store append does NOT do — the store
# checks the closed enum; THIS checks the closed graph of legal transitions)
# ---------------------------------------------------------------------------

def is_legal_transition(frm: Optional[str], to: str) -> bool:
    """True iff `frm → to` is a permitted transition. `frm is None` means opening
    a new job (only ENTRY_STATES). From `blocked`, the only legal move is a
    RESUME to a non-terminal, non-blocked state (the concrete target is read from
    the blocked record's typed `resumable_from` by resume_job)."""
    if frm is None:
        return to in ENTRY_STATES
    if frm == BLOCKED:
        return to in RESUMABLE_TARGETS
    return to in LEGAL_TRANSITIONS.get(frm, frozenset())


def assert_transition(frm: Optional[str], to: str) -> None:
    if not is_legal_transition(frm, to):
        if frm == "remote-integrated" and to == "landed":
            raise IllegalTransition(
                "optimistic 'remote-integrated → landed' is forbidden: `landed` "
                "binds to LOCAL reconcile (R2 / cc437616 §7 / 44badb55 R10); a "
                "remote merge alone is only `remote-integrated`. Reach `landed` "
                "via reconcile_destination, never a direct jump."
            )
        raise IllegalTransition(f"illegal job transition {frm!r} → {to!r}")


# ---------------------------------------------------------------------------
# The immutable changeset envelope (cc437616 §8 tier-1 private-local evidence)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChangesetPlan:
    """The result of plan_changeset. Contains the changeset_uid the contract
    names PLUS the job_uid the store keys on (equivalent-to per §Write Library
    'names may vary')."""
    changeset_uid: str
    job_uid: str
    vault_uid: str
    destination: str
    target_audience: str
    base: Optional[str]
    included_nodes: tuple = ()
    cut_edges: tuple = ()
    stranded_nodes: tuple = ()
    external_dependency_pins: tuple = ()
    bindings: dict = field(default_factory=dict)


def _mint_uid() -> str:
    return uuid.uuid4().hex[:8]


def _changeset_path(vault_root: Path, changeset_uid: str) -> Path:
    return vault_root / CHANGESET_DIR_REL / f"{changeset_uid}.json"


def _write_envelope_atomic(path: Path, envelope: dict) -> None:
    """Write the envelope durably: temp file in the same dir, fsync, atomic
    os.replace, then fsync the directory so the rename itself survives a crash.
    The envelope is immutable — plan_changeset is the ONLY writer (cc437616 §8:
    'No later event mutates the original envelope')."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    blob = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    dfd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def read_envelope(vault_root: Path, changeset_uid: str) -> dict:
    path = _changeset_path(vault_root, changeset_uid)
    if not path.is_file():
        raise ChangesetNotFound(f"no changeset envelope for {changeset_uid!r}")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Internal: current state of a job, and the guarded advance
# ---------------------------------------------------------------------------

def _current_state(records: list[dict], job_uid: str, destination: Optional[str], path_set) -> Optional[str]:
    latest = pj._latest_for_job(records, job_uid, destination, pj.path_set_hash(path_set))
    return latest["state"] if latest else None


def _advance(
    vault_root: Path,
    vault_uid: str,
    *,
    job_uid: str,
    changeset_uid: str,
    destination: Optional[str],
    path_set,
    to_state: str,
    actor: str,
    asof: str,
    error: Optional[str] = None,
    reason: Optional[str] = None,
    resumable_from: Optional[str] = None,
) -> dict:
    """Guarded transition: check the closed transition graph, THEN append to the
    store (which independently re-checks the closed enum + is idempotent). The
    two guards are deliberately layered — the store owns the closed VALUE space,
    the service owns the closed GRAPH of moves.

    Idempotent resume (R1): re-applying the EXACT transition already on the tip
    (same state + error + resumable_from) is a no-op that returns the existing
    record — it must NOT be rejected as an illegal `frm == to` move. This is what
    lets a process that died after the store append but before returning resume
    from evidence without duplicating a row."""
    records = pj.read_records(vault_root, vault_uid)
    latest = pj._latest_for_job(records, job_uid, destination, pj.path_set_hash(path_set))
    frm = latest["state"] if latest else None
    if (latest is not None
            and latest["state"] == to_state
            and latest.get("error") == error
            and latest.get("resumable_from") == resumable_from):
        return latest
    assert_transition(frm, to_state)
    return pj.append_transition(
        vault_root, vault_uid,
        job_uid=job_uid, changeset_uid=changeset_uid, destination=destination,
        path_set=path_set, state=to_state, actor=actor, asof=asof,
        error=error, reason=reason, resumable_from=resumable_from,
    )


# ---------------------------------------------------------------------------
# §Write Library — the LOCAL operations (buildable + testable NOW)
# ---------------------------------------------------------------------------

def plan_changeset(
    vault_root: Path,
    vault_uid: str,
    *,
    selection: Iterable[str],
    destination: str,
    target_audience: str,
    graph: Mapping[str, rc.GraphNode],
    exclusions: Iterable[str] = (),
    base: Optional[str] = None,
    bindings: Optional[Mapping] = None,
    actor: str,
    asof: str,
    snapshot_revision: Optional[str] = None,
) -> ChangesetPlan:
    """Open a publish job: resolve the vault-scoped, exclusion-aware ref-closure,
    write the immutable changeset envelope, and record the opening `planned`
    transition. Refuses (raises, opens NO job) a closure the query rejects —
    empty selection, unknown uid, or a cross-vault selection (A6 / cc437616 §3).

    Accepts an AGENT-STAGED (non-interactive) selection — the agent-first
    workflow stages big-N closures for a human to one-click assent
    (c27c741b §7 Q4); nothing here assumes an interactive caller.
    """
    closure = rc.compute_ref_closure(
        graph, selection, exclusions=exclusions, snapshot_revision=snapshot_revision
    )
    if closure.refused:
        raise PublishServiceError(
            f"cannot plan changeset: ref-closure refused — {closure.reason}"
        )

    changeset_uid = _mint_uid()
    job_uid = _mint_uid()
    included = tuple(closure.included_nodes)
    bindings = dict(bindings or {})

    envelope = {
        "schema_id": "tropo.changeset-envelope/v1",
        "changeset_uid": changeset_uid,
        "job_uid": job_uid,
        "vault_uid": vault_uid,
        "destination": destination,
        "target_audience": target_audience,
        "base": base,
        "selection": list(dict.fromkeys(selection)),
        "exclusions": list(closure.exclusions),
        "included_nodes": list(included),
        "cut_edges": [list(e) for e in closure.cut_edges],
        "stranded_nodes": list(closure.stranded_nodes),
        "external_dependency_pins": list(closure.external_dependency_pins),
        "snapshot_revision": closure.snapshot_revision,
        "bindings": bindings,
        "planned_by": actor,
        "planned_at": asof,
    }
    _write_envelope_atomic(_changeset_path(vault_root, changeset_uid), envelope)

    _advance(
        vault_root, vault_uid,
        job_uid=job_uid, changeset_uid=changeset_uid, destination=destination,
        path_set=included, to_state="planned", actor=actor, asof=asof,
        reason="changeset planned",
    )

    return ChangesetPlan(
        changeset_uid=changeset_uid,
        job_uid=job_uid,
        vault_uid=vault_uid,
        destination=destination,
        target_audience=target_audience,
        base=base,
        included_nodes=included,
        cut_edges=tuple(tuple(e) for e in closure.cut_edges),
        stranded_nodes=tuple(closure.stranded_nodes),
        external_dependency_pins=tuple(
            tuple(sorted(p.items())) for p in closure.external_dependency_pins
        ),
        bindings=bindings,
    )


def validate_changeset(
    vault_root: Path,
    vault_uid: str,
    changeset_uid: str,
    *,
    actor: str,
    asof: str,
    current_bindings: Optional[Mapping] = None,
    files: Iterable[Mapping] = (),
    resolver: Optional[GroupResolver] = None,
    policy_hook: Optional[Callable[[dict], Optional[str]]] = None,
) -> dict:
    """The deterministic planning + policy + privacy gate (cc437616 §4/§8).
    `planned → validated` on a clean pass, else `planned → blocked` with a closed
    LOCAL error code + a typed resumable_from. Every blocked outcome carries a
    code from LOCAL_ERROR_CODES ⊂ publish_journal.CLOSED_ERROR_ENUM (A5).

    Gate order is deterministic (a plant triggers exactly one):
      1. STALE_PLAN                — a bound revision changed since plan.
      2. OVERLAPPING_CHANGESET     — another in-flight job for this vault.
      3. GROUP_RESOLUTION_UNAVAILABLE — the target audience won't resolve.
      4. POLICY_REFUSED            — the publish policy refuses (blank audience
                                     or an injected policy_hook veto).
      5. PRIVACY_REFUSED           — a private file sits in a shared tree
                                     (scope-vs-location; the next push leaks it).
    """
    envelope = read_envelope(vault_root, changeset_uid)
    job_uid = envelope["job_uid"]
    destination = envelope["destination"]
    path_set = envelope["included_nodes"]
    target_audience = envelope.get("target_audience")

    error: Optional[str] = None
    reason: Optional[str] = None

    # 1. STALE_PLAN — any recorded plan binding whose current value differs.
    if current_bindings is not None:
        planned = envelope.get("bindings") or {}
        changed = [
            k for k, v in planned.items()
            if current_bindings.get(k) != v
        ]
        if changed:
            error, reason = "STALE_PLAN", (
                f"plan bindings changed since plan: {sorted(changed)}"
            )

    # 2. OVERLAPPING_CHANGESET — a second in-flight source job for this vault.
    if error is None:
        records = pj.read_records(vault_root, vault_uid)
        if _other_in_flight_job(records, job_uid):
            error, reason = "OVERLAPPING_CHANGESET", (
                "another publish job for this vault is in flight; one Studio "
                "serializes its own integration attempts (cc437616 §7)"
            )

    # 3. GROUP_RESOLUTION_UNAVAILABLE — the audience group won't resolve.
    if error is None and resolver is not None:
        res = resolver.resolve_members(target_audience)
        if not res.ok:
            error, reason = "GROUP_RESOLUTION_UNAVAILABLE", (
                f"target audience {target_audience!r} did not resolve against "
                f"the B4 group registry"
            )

    # 4. POLICY_REFUSED — deterministic publish-policy gate.
    if error is None:
        if not target_audience:
            error, reason = "POLICY_REFUSED", (
                "publish policy requires an explicit target audience"
            )
        elif policy_hook is not None:
            veto = policy_hook(envelope)
            if veto:
                error, reason = "POLICY_REFUSED", veto

    # 5. PRIVACY_REFUSED — privacy-before-push scope-vs-location lint.
    if error is None and files:
        findings = rs.scope_vs_location_lint(files)
        if findings:
            error, reason = "PRIVACY_REFUSED", (
                f"{len(findings)} private file(s) in a shared clone tree would "
                f"leak on push: {[f['path'] for f in findings]}"
            )

    if error is not None:
        _advance(
            vault_root, vault_uid,
            job_uid=job_uid, changeset_uid=changeset_uid, destination=destination,
            path_set=path_set, to_state=BLOCKED, actor=actor, asof=asof,
            error=error, reason=reason, resumable_from="planned",
        )
    else:
        _advance(
            vault_root, vault_uid,
            job_uid=job_uid, changeset_uid=changeset_uid, destination=destination,
            path_set=path_set, to_state="validated", actor=actor, asof=asof,
            reason="passed the planning/policy/privacy gate",
        )
    return get_publish_job(vault_root, vault_uid, job_uid)


def _other_in_flight_job(records: list[dict], this_job_uid: str) -> bool:
    """True iff a DIFFERENT job in this vault currently sits in a non-terminal,
    non-blocked SOURCE state (an in-flight publish)."""
    in_flight_states = pj.SOURCE_STATES - pj.TERMINAL_STATES
    latest_by_job: dict[str, dict] = {}
    for rec in records:
        j = rec["job_uid"]
        if j not in latest_by_job or rec["seq"] > latest_by_job[j]["seq"]:
            latest_by_job[j] = rec
    for j, rec in latest_by_job.items():
        if j == this_job_uid:
            continue
        if rec["state"] in in_flight_states:
            return True
    return False


def request_assent(
    vault_root: Path, vault_uid: str, changeset_uid: str, *, actor: str, asof: str,
) -> dict:
    """`validated → awaiting-assent`: the job now awaits the policy-authorized
    principal's assent. LOCAL (no remote)."""
    env = read_envelope(vault_root, changeset_uid)
    _advance(
        vault_root, vault_uid,
        job_uid=env["job_uid"], changeset_uid=changeset_uid,
        destination=env["destination"], path_set=env["included_nodes"],
        to_state="awaiting-assent", actor=actor, asof=asof,
        reason="awaiting policy-authorized assent",
    )
    return get_publish_job(vault_root, vault_uid, env["job_uid"])


def record_assent(
    vault_root: Path, vault_uid: str, changeset_uid: str, *, assented_by: str, asof: str,
) -> dict:
    """`awaiting-assent → ready`: the principal assented; ready to publish. This
    is the last LOCAL transition — the next step (`ready → pushed`) is the D5
    remote push. LOCAL (no remote)."""
    env = read_envelope(vault_root, changeset_uid)
    _advance(
        vault_root, vault_uid,
        job_uid=env["job_uid"], changeset_uid=changeset_uid,
        destination=env["destination"], path_set=env["included_nodes"],
        to_state="ready", actor=assented_by, asof=asof,
        reason=f"assented by {assented_by}",
    )
    return get_publish_job(vault_root, vault_uid, env["job_uid"])


def resume_job(
    vault_root: Path, vault_uid: str, job_uid: str, *, actor: str, asof: str,
) -> dict:
    """Resume a `blocked` job to its typed `resumable_from` state (R1 recovery).
    Reads the recorded resumable_from off the current blocked record — the
    caller does not choose the target — and refuses if the job is not blocked or
    the target is not a live (non-terminal) state."""
    status = get_publish_job(vault_root, vault_uid, job_uid)
    if status["state"] != BLOCKED:
        raise IllegalTransition(
            f"resume_job only applies to a blocked job; {job_uid!r} is {status['state']!r}"
        )
    target = status.get("resumable_from")
    if target not in RESUMABLE_TARGETS:
        raise IllegalTransition(
            f"blocked job {job_uid!r} has no live resumable_from (got {target!r})"
        )
    env = read_envelope(vault_root, status["changeset_uid"])
    _advance(
        vault_root, vault_uid,
        job_uid=job_uid, changeset_uid=status["changeset_uid"],
        destination=env["destination"], path_set=env["included_nodes"],
        to_state=target, actor=actor, asof=asof,
        reason=f"resumed from blocked → {target}",
    )
    return get_publish_job(vault_root, vault_uid, job_uid)


def get_publish_job(vault_root: Path, vault_uid: str, job_uid: str) -> dict:
    """`jobStatus(jobId) → { state, error?, resumable_from?, asOf }` (dev-spec
    §Write Contract). Returns the CURRENT (latest-by-seq) record for the job.
    An unknown job is a hard failure — the read never invents a state."""
    records = pj.read_records(vault_root, vault_uid)
    job_records = [r for r in records if r["job_uid"] == job_uid]
    if not job_records:
        raise PublishServiceError(f"no such publish job {job_uid!r} in vault {vault_uid}")
    latest = max(job_records, key=lambda r: r["seq"])
    return {
        "jobId": job_uid,
        "changeset_uid": latest["changeset_uid"],
        "destination": latest["destination"],
        "state": latest["state"],
        "error": latest.get("error"),
        "resumable_from": latest.get("resumable_from"),
        "reason": latest.get("reason"),
        "asOf": latest["asOf"],
    }


def overlay_for_changeset(
    vault_root: Path, vault_uid: str, extraction_scope: Optional[str], changeset_uid: str,
) -> dict:
    """The draftStatus two-source merge for a changeset's row: (index base scope)
    ⊔ (live job state from the store). Demonstrates the overlay reading LIVE
    service-produced job state (dev-spec §Read Contract item 3 / A2). The
    `publishing`/`blocked` values it returns live in NO frontmatter."""
    env = read_envelope(vault_root, changeset_uid)
    records = pj.read_records(vault_root, vault_uid)
    return ds.resolve_row(
        extraction_scope, records,
        destination=env["destination"], path_set=env["included_nodes"],
    )


# ===========================================================================
# §Write Library — the D5 REMOTE half (dev-spec 396d88a4, GitHub.com transport)
#
# The two ops that previously raised D5FederationRequired are COMPLETE here: the
# atomic promotion transaction (publish_changeset) and the local-reconcile +
# receipt landing (reconcile_destination), driven over the github_transport CAS
# primitive + the receipt_ref stream. They still FLAG — raise D5FederationRequired
# — when no PromotionContext / ReconcileContext is provided, because RUNNING them
# against github.com needs the provisioned least-privilege GitHub App credential
# + the disposable protected repo (an environment prerequisite). Given a context
# (the proof fixture wires it to local bare remotes, real git), they run the full
# transaction end to end. Mechanism built; credential prerequisite flagged.
# ===========================================================================


class PromotionFault(RuntimeError):
    """A SIMULATED crash injected at a promotion step (fault-injection harness,
    P1). Retrying publish_changeset must resume from journal + progress evidence
    to a SINGLE clean outcome."""


@dataclass
class PromotionContext:
    """Everything the atomic promotion needs, injected so the SAME code proves
    against local bare remotes and runs against github.com. `team_scope` is the
    destination segment's extraction_scope; `expected_tip` is the team canonical
    tip the plan was pinned to (None = first integration)."""
    private_repo: Path
    team_clone: Path
    transport: "ght.GitHubTransport"
    team_scope: str = "team"
    expected_tip: Optional[str] = None

    def remap(self, priv_uid: str) -> str:
        """Deterministic private→team uid remap (Phase B studio-prefixed minting,
        modelled as a stable hash of team_scope + priv_uid). Deterministic is what
        makes the transaction retry-safe: a re-run computes the SAME team_uid, so
        a crash-then-retry never duplicates the promoted node."""
        return hashlib.sha1(f"{self.team_scope}:{priv_uid}".encode("utf-8")).hexdigest()[:8]


@dataclass
class ReconcileContext:
    """Everything the destination reconcile needs. `destination_clone` is the
    receiving Studio's clone (resolved from a registered mount, never a caller
    path); `receipts` is the append-only receipt-ref client; the writer key is
    the least-privilege append credential."""
    destination_clone: Path
    team_remote: str
    receipts: "rref.ReceiptRefClient"
    writer_instance_uid: str
    writer_key: str
    canonical_ref: str = "refs/heads/main"
    source_attestation_hash: str = ""


def _progress_path(vault_root: Path, changeset_uid: str) -> Path:
    return vault_root / CHANGESET_DIR_REL / f"{changeset_uid}.promotion.json"


def _read_progress(vault_root: Path, changeset_uid: str) -> dict:
    p = _progress_path(vault_root, changeset_uid)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def _write_progress(vault_root: Path, changeset_uid: str, progress: dict) -> None:
    _write_envelope_atomic(_progress_path(vault_root, changeset_uid), progress)


def _maybe_fault(fault_after: Optional[str], step: str) -> None:
    if fault_after == step:
        raise PromotionFault(f"simulated crash after promotion step {step!r}")


def _split_frontmatter(text: str) -> tuple[Optional[list[str]], str]:
    """(frontmatter_lines, body) via EXACT-line fences — the SAME rule the
    governance validator uses, so the two never disagree."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return lines[1:i], "\n".join(lines[i + 1:])
    return None, text


def _remap_tokens(text: str, remap: Mapping[str, str]) -> str:
    for priv, team in remap.items():
        text = re.sub(rf"\b{re.escape(priv)}\b", team, text)
    return text


def _transform_promoted(private_text: str, team_uid: str, team_scope: str, remap: Mapping[str, str]) -> str:
    """Produce the team-side artifact from the private one: uid → team_uid,
    extraction_scope → team_scope, and every ref to another promoted uid remapped
    team-internal (so a team artifact refs only team uids — D1 boundary law)."""
    fm, body = _split_frontmatter(private_text)
    if fm is None:
        raise PublishServiceError("cannot promote a file without well-formed frontmatter")
    out = []
    for line in fm:
        if re.match(r"^uid:", line):
            out.append(f"uid: {team_uid}")
        elif re.match(r"^extraction_scope:", line):
            out.append(f"extraction_scope: {team_scope}")
        else:
            out.append(_remap_tokens(line, remap))
    body = _remap_tokens(body, remap)
    return "---\n" + "\n".join(out) + "\n---\n" + body


def _git_commit_all(repo: Path, message: str) -> Optional[str]:
    """Stage + commit everything; return the new HEAD sha, or None if there was
    nothing to commit (idempotent — a re-run with no changes is a no-op)."""
    ght.run_git(["add", "-A"], cwd=repo)
    status = ght.run_git(["status", "--porcelain"], cwd=repo).stdout.strip()
    if not status:
        return None
    ght.run_git(["commit", "-q", "-m", message], cwd=repo)
    return ght.run_git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()


def _write_promoted_to_team(promotion: PromotionContext, remap: Mapping[str, str]) -> str:
    """write-to-team + uid-remap: materialise each promoted artifact into the team
    clone and commit → the candidate SHA. Idempotent: if the files already match
    HEAD (a retry), reuse HEAD rather than minting a second commit."""
    team_files = promotion.team_clone / "files"
    team_files.mkdir(parents=True, exist_ok=True)
    for priv_uid, team_uid in remap.items():
        priv_path = promotion.private_repo / "files" / f"{priv_uid}.md"
        team_text = _transform_promoted(priv_path.read_text(encoding="utf-8"),
                                        team_uid, promotion.team_scope, remap)
        (team_files / f"{team_uid}.md").write_text(team_text, encoding="utf-8")
    new_head = _git_commit_all(promotion.team_clone, f"promote {sorted(remap.values())} to team")
    if new_head is not None:
        return new_head
    return ght.run_git(["rev-parse", "HEAD"], cwd=promotion.team_clone).stdout.strip()


def _fixup_private(promotion: PromotionContext, remap: Mapping[str, str]) -> None:
    """private-side ref-fixup + original redirect: rewrite every private artifact
    that referenced a promoted uid to the new team uid, and replace the promoted
    file itself with a redirect stub — so a promoted file's private refs leave
    ZERO orphaned refs (P1). Idempotent."""
    files_dir = promotion.private_repo / "files"
    promoted = set(remap)
    for md in sorted(files_dir.glob("*.md")):
        stem = md.stem
        if stem in promoted:
            team_uid = remap[stem]
            md.write_text(_redirect_stub(stem, team_uid), encoding="utf-8")
        else:
            original = md.read_text(encoding="utf-8")
            rewritten = _remap_tokens(original, remap)
            if rewritten != original:
                md.write_text(rewritten, encoding="utf-8")
    _git_commit_all(promotion.private_repo, f"fixup private refs after promoting {sorted(remap.values())}")


def _redirect_stub(priv_uid: str, team_uid: str) -> str:
    return (
        "---\n"
        f"uid: {priv_uid}\n"
        "type: redirect\n"
        "title: \"Promoted to team segment\"\n"
        "owner: tropo-federation\n"
        f"redirect_to: {team_uid}\n"
        "extraction_scope: argo-private\n"
        "promoted: true\n"
        "---\n"
        f"This record was promoted to the team segment as `{team_uid}`.\n"
    )


def publish_changeset(
    vault_root: Path, vault_uid: str, changeset_uid: str, *, actor: str, asof: str,
    promotion: Optional[PromotionContext] = None, fault_after: Optional[str] = None,
) -> str:
    """`publish_changeset(changeset_uid) → job_uid` — the atomic private→team
    promotion transaction (dev-spec 396d88a4 / cc437616 §5).

    write-to-team + push + uid-remap + private-side ref-fixup + original redirect
    as ONE retry-safe transaction: each durable effect is journaled (state) +
    progress-logged (candidate/integrated sha, remap, step markers), so a crash
    at ANY step resumes to a SINGLE clean outcome — no half-promoted or
    duplicated node, no orphaned refs. Remote integration is protected-ref
    non-force fast-forward CAS to the exact candidate against the pinned tip
    (one winner; losers → REMOTE_CAS_FAILED/STALE_PLAN).

    With no PromotionContext, the mechanism is built but cannot RUN — it FLAGS
    (D5FederationRequired) because github.com integration needs the provisioned
    least-privilege GitHub App credential + protected repo (prerequisite).
    """
    env = read_envelope(vault_root, changeset_uid)
    job_uid = env["job_uid"]
    dest = env["destination"]
    path_set = env["included_nodes"]
    status = get_publish_job(vault_root, vault_uid, job_uid)
    cur = status["state"]

    if cur in ("awaiting-receipt", "landed", "landed-then-superseded"):
        return job_uid  # already integrated — idempotent resume
    if cur == BLOCKED:
        if status.get("resumable_from") == "ready":
            _advance(vault_root, vault_uid, job_uid=job_uid, changeset_uid=changeset_uid,
                     destination=dest, path_set=path_set, to_state="ready",
                     actor=actor, asof=asof, reason="resume publish after a remote refusal")
            cur = "ready"
        else:
            raise IllegalTransition(
                f"blocked job {job_uid!r} is not resumable to `ready` (resumable_from="
                f"{status.get('resumable_from')!r})"
            )
    if cur not in ("ready", "pushed", "remote-integrated"):
        raise IllegalTransition(
            f"publish_changeset cannot start from {cur!r}; expected ready/pushed/remote-integrated"
        )

    if promotion is None:
        raise D5FederationRequired(
            "publish_changeset",
            needs=[
                "a configured PromotionContext (team clone + github_transport for authenticated push + protected-ref CAS)",
                "the provisioned LEAST-PRIVILEGE GitHub App/installation credential that may advance the protected canonical ref",
                "the disposable protected repo + branch-protection + required Action (github.com-only proof) — see federation/github-gate",
            ],
        )

    def _adv(state, **kw):
        return _advance(vault_root, vault_uid, job_uid=job_uid, changeset_uid=changeset_uid,
                        destination=dest, path_set=path_set, to_state=state,
                        actor=actor, asof=asof, **kw)

    progress = _read_progress(vault_root, changeset_uid)
    if "remap" not in progress:
        progress["remap"] = {p: promotion.remap(p) for p in path_set}
    remap = progress["remap"]
    if not progress.get("candidate_sha"):
        progress["candidate_sha"] = _write_promoted_to_team(promotion, remap)
        progress["expected_tip"] = promotion.expected_tip
        _write_progress(vault_root, changeset_uid, progress)
    _maybe_fault(fault_after, "write-to-team")
    candidate = progress["candidate_sha"]

    if cur == "ready":
        _adv("pushed", reason=f"candidate {candidate[:12]} staged for team {dest}")
        cur = "pushed"
        _maybe_fault(fault_after, "pushed")

    if cur == "pushed":
        try:
            result = promotion.transport.cas_advance(
                promotion.team_clone, expected_tip=progress.get("expected_tip"),
                candidate_sha=candidate,
            )
        except ght.RemoteIntegrationError as exc:
            _adv(BLOCKED, error=exc.code, reason=str(exc), resumable_from="ready")
            return job_uid
        progress["integrated_sha"] = result["integrated_sha"]
        _write_progress(vault_root, changeset_uid, progress)
        _adv("remote-integrated", reason=f"CAS-integrated {candidate[:12]} on {dest} canonical")
        cur = "remote-integrated"
        _maybe_fault(fault_after, "cas")

    if cur == "remote-integrated":
        if not progress.get("fixup_done"):
            _fixup_private(promotion, remap)
            progress["fixup_done"] = True
            _write_progress(vault_root, changeset_uid, progress)
        _maybe_fault(fault_after, "fixup")
        _adv("awaiting-receipt", reason="integrated; awaiting destination reconcile receipt")

    return job_uid


def _reconcile_local(reconcile: ReconcileContext, integrated_sha: str) -> str:
    """LOCAL fetch + freshen/rebuild + integrity check (R2, never optimistic).
    Fetch the canonical ref into the destination clone, fast-forward the working
    tree to it, and assert the integrated commit is the EXACT tip. Returns the
    result-tree hash; raises ValueError (→ RECONCILE_FAILED) on any mismatch."""
    clone = reconcile.destination_clone
    ght.run_git(["fetch", "--quiet", reconcile.team_remote, reconcile.canonical_ref], cwd=clone)
    fetched = ght.run_git(["rev-parse", "FETCH_HEAD"], cwd=clone).stdout.strip()
    if not integrated_sha or fetched != integrated_sha:
        raise ValueError(
            f"destination fetched {fetched[:12]} but the source integrated "
            f"{str(integrated_sha)[:12]} — integrity check failed"
        )
    ght.run_git(["merge", "--ff-only", "--quiet", "FETCH_HEAD"], cwd=clone, check=False)
    tree = ght.run_git(["rev-parse", f"{integrated_sha}^{{tree}}"], cwd=clone).stdout.strip()
    return tree


def reconcile_destination(
    vault_root: Path, vault_uid: str, job_uid: str,
    destination_studio_uid: str, replica_uid: str, *, actor: str, asof: str,
    reconcile: Optional[ReconcileContext] = None,
    superseded: bool = False, fault_after: Optional[str] = None,
) -> str:
    """`reconcile_destination(job_uid, destination_studio_uid, replica_uid)` — the
    ONLY path to `landed` (dev-spec 396d88a4 / cc437616 §7). Drives the
    DESTINATION machine (pending → reconciling → receipt-emitted → landed-local)
    on a receiver-scoped row AND the source per-destination `awaiting-receipt →
    landed`, but ONLY after a real local fetch + freshen + integrity check + a
    durable receipt appended to refs/tropo/receipts/<writer>. The optimistic
    `remote-integrated → landed` jump stays an IllegalTransition (R2).

    With no ReconcileContext, the mechanism is built but FLAGS — running against
    the live receipts repo needs the provisioned writer credential + mount. This
    is the FIRST gate: without the context/credential nothing can run, so a
    caller lacking it gets a clean D5 flag rather than a partial side effect.
    """
    if reconcile is None:
        raise D5FederationRequired(
            "reconcile_destination",
            needs=[
                "a configured ReconcileContext (destination clone resolved from the registered compose-lock mount)",
                "the append credential for refs/tropo/receipts/<writer> on the live tropo-ai/tropo-receipts repo",
                "the source attestation hash to link the reconciliation receipt to (local freshen/rebuild + integrity check)",
            ],
        )

    records = pj.read_records(vault_root, vault_uid)
    dest_rows = [r for r in records if r["job_uid"] == job_uid and r["destination"] == destination_studio_uid]
    if not dest_rows:
        raise PublishServiceError(
            f"no source row for job {job_uid!r} at destination {destination_studio_uid!r}"
        )
    latest = max(dest_rows, key=lambda r: r["seq"])
    changeset_uid = latest["changeset_uid"]
    env = read_envelope(vault_root, changeset_uid)
    path_set = env["included_nodes"]
    src_state = latest["state"]

    if src_state in ("landed", "landed-then-superseded"):
        return job_uid  # idempotent
    if src_state == "remote-integrated":
        _advance(vault_root, vault_uid, job_uid=job_uid, changeset_uid=changeset_uid,
                 destination=destination_studio_uid, path_set=path_set,
                 to_state="awaiting-receipt", actor=actor, asof=asof,
                 reason="source acknowledges integration; awaiting receipt")
        src_state = "awaiting-receipt"
    if src_state != "awaiting-receipt":
        raise IllegalTransition(
            f"reconcile requires the source at `awaiting-receipt`; it is {src_state!r}"
        )

    recv = f"recv:{destination_studio_uid}:{replica_uid}"

    def _recv(state, **kw):
        return _advance(vault_root, vault_uid, job_uid=job_uid, changeset_uid=changeset_uid,
                        destination=recv, path_set=path_set, to_state=state,
                        actor=actor, asof=asof, **kw)

    def _src(state, **kw):
        return _advance(vault_root, vault_uid, job_uid=job_uid, changeset_uid=changeset_uid,
                        destination=destination_studio_uid, path_set=path_set, to_state=state,
                        actor=actor, asof=asof, **kw)

    _recv("pending", reason=f"destination {destination_studio_uid} notified of integration")

    # SUPERSEDE (P5): the promoted uid changed before this destination projected
    # the integrated state → terminal NOT-landed; the source row stays un-landed.
    if superseded:
        _recv("superseded-before-reconcile",
              reason="promoted uid superseded before destination projected the integrated state")
        return job_uid

    _recv("reconciling", reason="local fetch + freshen + integrity check")
    _maybe_fault(fault_after, "reconciling")

    integrated_sha = _read_progress(vault_root, changeset_uid).get("integrated_sha")
    try:
        result_tree = _reconcile_local(reconcile, integrated_sha)
    except (ValueError, ght.GitError) as exc:
        _recv(BLOCKED, error="RECONCILE_FAILED", reason=str(exc), resumable_from="reconciling")
        _src(BLOCKED, error="RECONCILE_FAILED", reason=str(exc), resumable_from="awaiting-receipt")
        return job_uid

    payload = {
        "payload_type": rref.RECONCILIATION_TYPE,
        "vault_uid": vault_uid,
        "changeset_uid": changeset_uid,
        "destination": destination_studio_uid,
        "replica": replica_uid,
        "integrated_commit": integrated_sha,
        "result_tree_hash": result_tree,
        "source_attestation_hash": reconcile.source_attestation_hash,
        "writer": reconcile.writer_instance_uid,
        "asOf": asof,
    }
    try:
        rec = reconcile.receipts.append_receipt(
            reconcile.writer_instance_uid, payload, presented_key=reconcile.writer_key,
        )
    except rref.ReceiptError as exc:
        _recv(BLOCKED, error=exc.code, reason=str(exc), resumable_from="reconciling")
        _src(BLOCKED, error=exc.code, reason=str(exc), resumable_from="awaiting-receipt")
        return job_uid

    _recv("receipt-emitted", reason=f"receipt {rec['receipt_id'][:12]} appended to {rec['ref']}")
    _maybe_fault(fault_after, "receipt")
    _recv("landed-local", reason="destination reconcile complete")
    _src("landed", reason=f"reconciled + durable receipt {rec['receipt_id'][:12]} (R2)")
    return job_uid


def mark_landed_then_superseded(
    vault_root: Path, vault_uid: str, job_uid: str, destination_studio_uid: str,
    *, actor: str, asof: str,
) -> dict:
    """Record that an already-landed destination advanced past the integrated
    result (a later descendant) — `landed → landed-then-superseded`, distinct
    from `superseded-before-reconcile` (which never landed). Never compares the
    later tree to the old result (cc437616 §7)."""
    records = pj.read_records(vault_root, vault_uid)
    rows = [r for r in records if r["job_uid"] == job_uid and r["destination"] == destination_studio_uid]
    if not rows:
        raise PublishServiceError(f"no row for job {job_uid!r} at {destination_studio_uid!r}")
    changeset_uid = max(rows, key=lambda r: r["seq"])["changeset_uid"]
    env = read_envelope(vault_root, changeset_uid)
    _advance(vault_root, vault_uid, job_uid=job_uid, changeset_uid=changeset_uid,
             destination=destination_studio_uid, path_set=env["included_nodes"],
             to_state="landed-then-superseded", actor=actor, asof=asof,
             reason="landed destination advanced past the integrated result")
    return get_publish_job(vault_root, vault_uid, job_uid)


__all__ = [
    "CHANGESET_DIR_REL", "ENTRY_STATES", "RESUMABLE_TARGETS",
    "LEGAL_TRANSITIONS", "LOCAL_ERROR_CODES", "D5_ONLY_ERROR_CODES",
    "PublishServiceError", "IllegalTransition", "ChangesetNotFound",
    "D5FederationRequired", "PromotionFault",
    "is_legal_transition", "assert_transition",
    "ChangesetPlan", "PromotionContext", "ReconcileContext", "read_envelope",
    "plan_changeset", "validate_changeset", "request_assent", "record_assent",
    "resume_job", "get_publish_job", "overlay_for_changeset",
    "publish_changeset", "reconcile_destination", "mark_landed_then_superseded",
]
