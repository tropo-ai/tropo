"""Governed-skip obligation resolver for the pipeline engine (d9ca03fd / d7db77d8).

One activation-scoped replay index + one obligation resolver. Every consumer —
eligibility, step verification, B3-extension, terminal reporting, all-steps
verification, and the no-trigger cascade — must go through resolve_obligation.
Do not grow a second satisfaction rule beside this module.
"""
from __future__ import annotations

import re
from typing import Any

# Disposition vocabulary locked by d7db77d8.
SATISFIED = "satisfied"
SATISFIED_BY_SKIP = "satisfied_by_skip"
WAIVED_BY_SKIP = "waived_by_skip"
UNSATISFIED = "unsatisfied"
UNAUTHORIZED_SKIP = "unauthorized_skip"

_HANDLE_RE = re.compile(
    r"^(?P<handle>triggered_(?:doc|test)_(?:spec|activation)"
    r"|dev_spec\.triggered_(?:doc|test)_(?:spec|activation)_uids"
    r"|dev_spec)"
)

# Artifact-shaped criteria: the producer's work creates or populates something.
# When that producer is auth-skipped, the criterion is waived (not claimed present).
_ARTIFACT_MARKERS = (
    " exists",
    " populated",
    " contains ",
    ".stage ==",
    ".status ==",
    ".acceptance_evidence",
)


def extract_handle(criterion: str) -> str | None:
    """Leading substrate handle a criterion consults, if any."""
    s = (criterion or "").strip()
    if not s or s.startswith("human:") or s.startswith("aggregate:"):
        return None
    # Prefer the longest explicit path forms first.
    for prefix in (
        "dev_spec.triggered_test_spec_uids",
        "dev_spec.triggered_doc_spec_uids",
        "dev_spec.triggered_test_activation_uids",
        "dev_spec.triggered_doc_activation_uids",
        "triggered_test_activation",
        "triggered_doc_activation",
        "triggered_test_spec",
        "triggered_doc_spec",
    ):
        if s.startswith(prefix):
            return prefix
    m = _HANDLE_RE.match(s)
    return m.group("handle") if m else None


def is_artifact_criterion(criterion: str) -> bool:
    s = (criterion or "").strip()
    return any(marker in s for marker in _ARTIFACT_MARKERS)


def _paired_handles(handle: str) -> tuple[str, ...]:
    """Array / activation forms owned with a creation-shaped primary handle."""
    if handle == "triggered_test_spec":
        return (
            "dev_spec.triggered_test_spec_uids",
            "triggered_test_activation",
            "dev_spec.triggered_test_activation_uids",
        )
    if handle == "triggered_doc_spec":
        return (
            "dev_spec.triggered_doc_spec_uids",
            "triggered_doc_activation",
            "dev_spec.triggered_doc_activation_uids",
        )
    if handle == "triggered_test_activation":
        return ("dev_spec.triggered_test_activation_uids",)
    if handle == "triggered_doc_activation":
        return ("dev_spec.triggered_doc_activation_uids",)
    return ()


def build_producer_ownership(
    decls: dict[str, dict],
) -> tuple[dict[str, str], set[str]]:
    """Map handle → producer step from creation-shaped exit criteria.

    Explicit field-level ownership (d7db77d8). A step that authors
    `triggered_test_spec.uid exists` owns that handle. Legacy adapter only —
    no hardcoded step UIDs.

    Ambiguous claims (two distinct producers for the same handle) fail closed:
    the handle is omitted from the ownership map and listed in the ambiguous set.
    First-writer-wins is refused — silent reassignment is the defect class.
    """
    claims: dict[str, set[str]] = {}
    # Ownership is creation-shaped only. "populated" is a consumer check that a
    # field was filled — it must not claim producer ownership (that false claim
    # is exactly how a terminal step and its trigger step look "ambiguous").
    creation_markers = (" exists", " contains ")

    def _claim(handle: str, step_id: str) -> None:
        claims.setdefault(handle, set()).add(step_id)

    for step_id, decl in decls.items():
        for criterion in decl.get("exit_criteria") or []:
            if not any(m in criterion for m in creation_markers):
                continue
            handle = extract_handle(criterion)
            if not handle:
                continue
            _claim(handle, step_id)
            for paired in _paired_handles(handle):
                _claim(paired, step_id)

    ownership: dict[str, str] = {}
    ambiguous: set[str] = set()
    for handle, producers in claims.items():
        if len(producers) == 1:
            ownership[handle] = next(iter(producers))
        else:
            ambiguous.add(handle)
    return ownership, ambiguous


def build_activation_replay_index(
    events: list[dict],
    decls: dict[str, dict],
    activation_uid: str,
) -> dict[str, Any]:
    """One activation-scoped replay index (d7db77d8 lines 74–76).

    Derives: latest declarations/receipts, ordered request→authorization→skip
    chains, current-trace completion artifacts, and terminal findings.
    Rejects pass→fail receipt ordering and cross-trace evidence by construction
    (only events whose trace_id matches the activation are indexed).
    """
    ownership, ambiguous_producers = build_producer_ownership(decls)

    skip_requests: dict[str, dict] = {}
    skip_auths: dict[str, dict] = {}
    skip_applied: dict[str, dict] = {}
    latest_receipts: dict[str, dict] = {}
    terminal_findings: list[dict] = []
    completion_artifacts: list[dict] = []

    # Per-step last non-fail receipt verdict for pass→fail refusal.
    last_pass_receipt: dict[str, dict] = {}

    for ev in events:
        et = ev.get("event")
        data = ev.get("data") or {}
        trace = ev.get("trace_id")
        # Cross-trace evidence is not indexed — fail closed at resolve time.
        if trace is not None and activation_uid and trace != activation_uid:
            continue

        step = ev.get("step") or data.get("step_id")

        if et == "skip_request" and step:
            skip_requests[step] = {
                "event": ev,
                "span_id": ev.get("span_id"),
                "requested_by": data.get("requested_by"),
                "reason": data.get("reason"),
            }
        elif et == "skip_authorization" and step:
            skip_auths[step] = {
                "event": ev,
                "span_id": ev.get("span_id"),
                "parent_span_id": ev.get("parent_span_id"),
                "authorized_by": data.get("authorized_by"),
                "conditions": data.get("conditions"),
            }
        elif et == "step_skipped" and step:
            skip_applied[step] = {
                "event": ev,
                "span_id": ev.get("span_id"),
                "auth_span": data.get("skip_authorization_span_id"),
            }
        elif et == "verification_receipt" and step:
            verdict = data.get("verdict")
            prev = latest_receipts.get(step)
            if (
                prev
                and prev.get("verdict") == "pass"
                and verdict in ("fail", "error")
            ):
                # Record the illegal ordering; resolve_obligation refuses it.
                data = dict(data)
                data["_pass_to_fail"] = True
                data["_prior_pass_span"] = prev.get("span_id")
            latest_receipts[step] = {
                "event": ev,
                "span_id": ev.get("span_id"),
                "verdict": verdict,
                "per_criterion": data.get("per_criterion") or [],
                "pass_to_fail": bool(data.get("_pass_to_fail")),
            }
            if verdict == "pass":
                last_pass_receipt[step] = latest_receipts[step]
        elif et == "verifier_findings":
            terminal_findings.append(ev)
        elif et in ("step_completed", "dev_closed", "workflow_complete"):
            completion_artifacts.append(ev)

    chains: dict[str, dict] = {}
    for step_id in set(skip_requests) | set(skip_auths) | set(skip_applied):
        req = skip_requests.get(step_id)
        auth = skip_auths.get(step_id)
        applied = skip_applied.get(step_id)
        ordered_ok = True
        if auth and req:
            # Authorization must parent the request span.
            if auth.get("parent_span_id") and req.get("span_id"):
                ordered_ok = auth["parent_span_id"] == req["span_id"]
        elif auth and not req:
            ordered_ok = False
        chains[step_id] = {
            "request": req,
            "authorization": auth,
            "skipped": applied,
            "ordered": ordered_ok,
            "authorized": bool(auth) and ordered_ok,
        }

    return {
        "activation_uid": activation_uid,
        "decls": decls,
        "producer_ownership": ownership,
        "ambiguous_producers": frozenset(ambiguous_producers),
        "skip_chains": chains,
        "latest_receipts": latest_receipts,
        "terminal_findings": terminal_findings,
        "completion_artifacts": completion_artifacts,
        "step_status_hint": {
            # Convenience for callers that also hold derive_state output.
        },
    }


def resolve_obligation(
    *,
    kind: str,
    replay: dict[str, Any],
    step_status: dict[str, str],
    consumer_step: str | None = None,
    producer_step: str | None = None,
    criterion: str | None = None,
    raw_verdict: str | None = None,
) -> dict[str, Any]:
    """Resolve one obligation through the single disposition vocabulary.

    kind:
      - "dependency" — consumer depends_on producer_step
      - "criterion"  — consumer exit criterion, optionally after evaluate_criterion
      - "step"       — whether a step itself is terminal (verified / auth-skip)
    """
    chains = replay.get("skip_chains") or {}
    ownership = replay.get("producer_ownership") or {}

    def _record(disposition: str, producer: str | None = None, auth_span: str | None = None,
                rationale: str = "") -> dict[str, Any]:
        return {
            "disposition": disposition,
            "consumer_step": consumer_step,
            "producer_step": producer,
            "criterion": criterion,
            "authorization_span_id": auth_span,
            "rationale": rationale,
        }

    if kind == "step":
        sid = producer_step or consumer_step
        status = step_status.get(sid or "", "declared")
        chain = chains.get(sid or "")
        if status == "verified":
            receipt = (replay.get("latest_receipts") or {}).get(sid or "")
            if receipt and receipt.get("pass_to_fail"):
                return _record(UNSATISFIED, sid, rationale="pass→fail receipt ordering refused")
            return _record(SATISFIED, sid, rationale="verification_receipt pass")
        if status == "skipped":
            if chain and chain.get("authorized"):
                auth_span = (chain.get("authorization") or {}).get("span_id")
                return _record(SATISFIED_BY_SKIP, sid, auth_span,
                               rationale="authorized skip satisfies step terminality")
            return _record(UNAUTHORIZED_SKIP, sid,
                           rationale="step skipped without ordered authorization")
        return _record(UNSATISFIED, sid, rationale=f"step status={status!r}")

    if kind == "dependency":
        if not producer_step:
            return _record(UNSATISFIED, rationale="dependency missing producer_step")
        status = step_status.get(producer_step)
        chain = chains.get(producer_step)
        if status == "verified":
            return _record(SATISFIED, producer_step, rationale="producer verified")
        if status == "skipped":
            if chain and chain.get("authorized"):
                auth_span = (chain.get("authorization") or {}).get("span_id")
                return _record(SATISFIED_BY_SKIP, producer_step, auth_span,
                               rationale="authorized producer skip satisfies dependency readiness")
            return _record(UNAUTHORIZED_SKIP, producer_step,
                           rationale="producer skipped without authorization")
        # vc:false completed is handled by caller via decl; treat as unsatisfied here.
        return _record(UNSATISFIED, producer_step, rationale=f"producer status={status!r}")

    if kind == "criterion":
        handle = extract_handle(criterion or "")
        ambiguous = replay.get("ambiguous_producers") or frozenset()
        if handle and handle in ambiguous and not producer_step:
            return _record(
                UNSATISFIED,
                rationale=(
                    f"ambiguous producer ownership for handle {handle!r} — "
                    "multiple distinct steps claim it; refuse (d7db77d8 fail-closed)"
                ),
            )
        producer = producer_step or (ownership.get(handle) if handle else None)
        chain = chains.get(producer) if producer else None

        # Ordinary satisfaction from substrate evaluation.
        if raw_verdict == "pass":
            return _record(SATISFIED, producer, rationale="criterion passed on substrate")

        # Producer auth-skipped: waive artifact criteria; never claim present.
        if producer and chain and chain.get("authorized") and step_status.get(producer) == "skipped":
            auth_span = (chain.get("authorization") or {}).get("span_id")
            if is_artifact_criterion(criterion or "") or raw_verdict in ("fail", "error", None):
                return _record(
                    WAIVED_BY_SKIP, producer, auth_span,
                    rationale=(
                        f"producer {producer} authorized-skipped; "
                        f"artifact/state criterion waived (not claimed present)"
                    ),
                )
            return _record(SATISFIED_BY_SKIP, producer, auth_span,
                           rationale="structural criterion carried by authorized skip")

        if producer and step_status.get(producer) == "skipped":
            return _record(UNAUTHORIZED_SKIP, producer,
                           rationale="producer skipped without authorization")

        if raw_verdict == "fail":
            return _record(UNSATISFIED, producer, rationale="criterion failed on substrate")
        if raw_verdict == "error":
            return _record(UNSATISFIED, producer,
                           rationale="criterion error (unresolved handle or DSL)")
        return _record(UNSATISFIED, producer, rationale="criterion unresolved")

    return _record(UNSATISFIED, rationale=f"unknown obligation kind {kind!r}")


def criterion_result_from_obligation(obligation: dict[str, Any]) -> dict[str, Any]:
    """Map an obligation into a verification_receipt per_criterion row."""
    disposition = obligation["disposition"]
    if disposition in (SATISFIED, SATISFIED_BY_SKIP, WAIVED_BY_SKIP):
        verdict = "pass"
    elif disposition == UNAUTHORIZED_SKIP:
        verdict = "error"
    else:
        verdict = "fail"
    return {
        "criterion": obligation.get("criterion"),
        "verdict": verdict,
        "disposition": disposition,
        "producer_step": obligation.get("producer_step"),
        "consumer_step": obligation.get("consumer_step"),
        "authorization_span_id": obligation.get("authorization_span_id"),
        "rationale": obligation.get("rationale"),
        "substrate_state_at_check": None,
    }


def require_ordered_skip_chain(replay: dict[str, Any], step_uid: str) -> str:
    """Return the authorization span_id, or raise ValueError describing the gap.

    Used by action_apply_skip so step_skipped cannot land without a prior
    skip_request and an ordered authorization (d7db77d8).
    """
    chain = (replay.get("skip_chains") or {}).get(step_uid)
    if not chain:
        raise ValueError(f"no skip chain for step {step_uid!r}")
    if not chain.get("request"):
        raise ValueError(f"no prior skip_request for step {step_uid!r}")
    if not chain.get("authorization"):
        raise ValueError(f"no prior skip_authorization for step {step_uid!r}")
    if not chain.get("ordered"):
        raise ValueError(
            f"skip authorization for {step_uid!r} is not ordered on the request span"
        )
    auth_by = (chain["authorization"].get("authorized_by") or "").strip()
    if not auth_by:
        raise ValueError(f"skip_authorization for {step_uid!r} missing authorized_by")
    return chain["authorization"]["span_id"]
