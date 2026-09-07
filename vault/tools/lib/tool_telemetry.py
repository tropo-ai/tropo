"""tool_telemetry — the enqueue-only black-box recorder producer (3f38521a).

One mechanism, one caller shape: an observed tool calls ``record_refused`` /
``record_failed`` and keeps moving. The submit path validates a small typed
record against the generated registry, drops it into a bounded in-memory
priority queue, and returns — no disk, no SQLite, no network, no subprocess,
no canonical emitter, no lock, no fsync (AC1). Persistence belongs to the
drainer (``tropo-drain-tool-telemetry.py``), never to the observed thread.

Privacy is structural (AC3): the registry declares the only legal keys and
types; there is no free-text field to sanitize because no field accepts
free text. The MVP records no argument fingerprint at all — deferred with
the spec, forbidden by the schema.

Recursion is impossible, not discouraged (AC5): a ContextVar guard plus the
``TROPO_TELEMETRY_OFF`` environment flag suppress recording inside producer,
drainer, projector, schema-generator, and health-counter code paths.

Loss is accounted, never silent (AC6): overload drops the least-valuable
queued record first (refusal outranks failure), and the counters live
outside the event bus — they are read by tooling, never emitted.

The registry at ``vault/schema/tool-telemetry-registry.json`` is the single
strict source (AC8): it self-certifies via ``content_digest`` over its own
canonical form, so a hand edit cannot pass for generated truth, and every
consumer (validation here, drainer schema, query projection) derives from
the same loaded document and digest.
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime as _dt
import hashlib
import heapq
import json
import os
import re
import threading
from pathlib import Path
from typing import Iterator

from lib.governed_path import is_governed_uid_shape

_TOOLS = Path(__file__).resolve().parent.parent  # <studio>/vault/tools
_STUDIO = _TOOLS.parents[1]  # vault/tools -> vault -> studio root
REGISTRY_PATH = _STUDIO / "vault" / "schema" / "tool-telemetry-registry.json"

_DEFAULT_QUEUE_SIZE = 4096
_SHA_RE = re.compile(r"^[0-9a-f]{16,}$")
_TOKEN_RE = re.compile(r"^\S{1,64}$")
_COUNTER_CLASSES = (
    "attempted", "enqueued", "sampled_out", "queue_dropped",
    "serialization_rejected", "persistence_failed", "segment_rejected",
    "deduplicated",
)

_SUPPRESSED = contextvars.ContextVar("tool_telemetry_suppressed", default=False)


class RegistryDriftError(RuntimeError):
    """The registry's self-certification failed: hand-edited content."""


# ---------------------------------------------------------------------------
# registry (AC8)
# ---------------------------------------------------------------------------

_REGISTRY_CACHE: dict | None = None


def _canonical_digest(payload: dict) -> str:
    body = {k: v for k, v in payload.items() if k != "content_digest"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_registry(*, force: bool = False) -> dict:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None and not force:
        return _REGISTRY_CACHE
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    claimed = payload.get("content_digest")
    if not isinstance(claimed, str) or _canonical_digest(payload) != claimed:
        raise RegistryDriftError(
            "tool-telemetry registry content_digest mismatch: the file was "
            "hand-edited away from its generated canonical form — regenerate "
            "rather than patch (spec 3f38521a AC8)"
        )
    _REGISTRY_CACHE = payload
    return payload


def registry_digest() -> str:
    return _canonical_digest(load_registry())


_registry_version = load_registry()["registry_version"]
_recorder_version = load_registry()["recorder_version"]


def _derive_segment(segment_inputs, order: list[str]):
    """Most-restrictive derivation; caller input is never authority alone —
    only known values participate, absence/ambiguity rejects (AC4)."""
    if not isinstance(segment_inputs, (list, tuple)) or not segment_inputs:
        return None
    rank = {name: i for i, name in enumerate(order)}
    known = [rank[s] for s in segment_inputs if s in rank]
    if not known:
        return None
    return order[max(known)]


def _validate_and_shape(payload: dict, outcome: str, registry: dict) -> dict | None:
    """Strict whole-record validation against the generated registry.

    Returns the shaped record, or None with the caller incrementing the
    reject counter. Strict means strict: one unknown key, one out-of-taxonomy
    value, and the entire record is refused — partial acceptance would let
    privacy violations ride along in the fields that did validate.
    """
    schema = registry["record_schema"]
    # The caller answers to the CALLER_PAYLOAD contract only (A152 verify
    # pass 1: conflating it with the shaped-record contract left a cold
    # caller unable to construct a valid payload from the registry — his
    # privacy probe never established a known-positive because of it).
    allowed = (
        set(schema["caller_payload"]["required"])
        | set(schema["caller_payload"]["optional"])
    )
    if set(payload) - allowed:
        return None
    taxonomy = registry["reason_taxonomy"]
    # AC8: a recorder generation built against a different registry version
    # than the one on disk must refuse to record — the dataschema it would
    # stamp is not a schema this studio can read.
    if _registry_version != registry["registry_version"]:
        return None
    category = payload.get("reason_category")
    code = payload.get("reason_code")
    if category not in taxonomy or code not in taxonomy[category]["codes"]:
        return None
    # is_governed_uid_shape, not the wider UID_HEX_PATTERN: tool_uid keys
    # the registry's segment_floor dict below, which is keyed by the real
    # (lowercase-minted) uid. A case-mismatched but shape-plausible uid
    # would fail that dict lookup silently (floor_name=None) and skip the
    # floor-enforcement check entirely -- the exact resolver-split class
    # is_governed_uid_shape exists to close.
    if not is_governed_uid_shape(str(payload.get("tool_uid") or "")):
        return None
    for token_field in ("invocation_uid", "operation_uid"):
        value = str(payload.get(token_field) or "")
        if not _TOKEN_RE.fullmatch(value):
            return None
        # A152 F1: token fields admit OPAQUE IDENTIFIERS, and credentials are
        # token-shaped by construction — the closed allowlist alone cannot
        # tell them apart (every credential format he tested passed). Known
        # credential prefixes are refused at the door; the claim in the
        # privacy docstring is corrected to match what is actually enforced.
        lowered = value.lower()
        if any(lowered.startswith(prefix)
               for prefix in registry.get("credential_token_prefixes", ())):
            return None
    for run_field in ("release_run_uid", "pipeline_run_uid"):
        run_value = str(payload.get(run_field) or "")
        lowered_run = run_value.lower()
        if run_value and any(
                lowered_run.startswith(prefix)
                for prefix in registry.get("credential_token_prefixes", ())):
            return None
    attempt = payload.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        return None
    retryability = payload.get("retryability", taxonomy[category]["default_retryability"])
    if retryability not in registry["retryability"]:
        return None
    segment = _derive_segment(
        payload.get("segment_inputs"), registry["segment_restrictiveness_order"])
    if segment is None:
        return None
    # A152 F2: a caller can under-declare segment_inputs, landing a record in
    # a LESS restrictive shard than the producing tool operates at. Registered
    # producers declare a segment floor in the registry; a derived segment
    # below the tool's floor refuses. (The producer cannot verify caller
    # truth — the floor is the honest bound it CAN enforce.)
    floors = registry.get("producers", {}).get("segment_floor", {})
    floor_name = floors.get(str(payload.get("tool_uid") or ""))
    if floor_name:
        order = registry["segment_restrictiveness_order"]
        if order.index(segment) < order.index(floor_name):
            return None
    record = {
        "tool_uid": payload["tool_uid"],
        "invocation_uid": payload["invocation_uid"],
        "operation_uid": payload["operation_uid"],
        "attempt": attempt,
        "outcome": outcome,
        "reason_category": category,
        "reason_code": code,
        "retryability": retryability,
        "segment": segment,
        "event_time_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds").replace("+00:00", "Z"),
        "dataschema": f"tool-telemetry/{_registry_version}",
        "recorder_version": _recorder_version,
    }
    if payload.get("gate_uid") is not None:
        if not is_governed_uid_shape(str(payload["gate_uid"])):
            return None
        record["gate_uid"] = payload["gate_uid"]
    if payload.get("harm_class") is not None:
        if payload["harm_class"] not in registry["harm_classes"]:
            return None
        record["harm_class"] = payload["harm_class"]
    if payload.get("tool_build_sha") is not None:
        if not _SHA_RE.fullmatch(str(payload["tool_build_sha"])):
            return None
        record["tool_build_sha"] = payload["tool_build_sha"]
    for run_field in ("release_run_uid", "pipeline_run_uid"):
        value = payload.get(run_field)
        if value is not None:
            if not _TOKEN_RE.fullmatch(str(value)):
                return None
            record[run_field] = value
    return record


# ---------------------------------------------------------------------------
# recorder (AC1/2/5/6)
# ---------------------------------------------------------------------------

class _Recorder:
    """Bounded priority buffer. Entries heap as (-keep_priority, seq, record)
    so the ROOT is the most valuable record; overflow evicts the LEAST
    valuable by scanning the bounded heap — never a blocking wait."""

    __slots__ = ("_heap", "_seen", "_lock", "_counters", "_seq", "_capacity")

    def __init__(self, queue_size: int = _DEFAULT_QUEUE_SIZE) -> None:
        self._heap: list[tuple[int, int, dict]] = []
        self._seen: set[tuple[str, str, str]] = set()
        self._lock = threading.Lock()
        self._counters = {name: 0 for name in _COUNTER_CLASSES}
        self._seq = 0
        self._capacity = queue_size

    def _bump(self, name: str) -> None:
        self._counters[name] += 1

    def submit(self, outcome: str, payload: dict) -> None:
        if _SUPPRESSED.get() or os.environ.get("TROPO_TELEMETRY_OFF") == "1":
            return
        self._bump("attempted")
        registry = load_registry()
        keep = registry["keep_priority"][outcome]
        segment_inputs = payload.get("segment_inputs")
        if _derive_segment(
                segment_inputs, registry["segment_restrictiveness_order"]) is None:
            self._bump("segment_rejected")
            return
        record = _validate_and_shape(payload, outcome, registry)
        if record is None:
            self._bump("serialization_rejected")
            return
        identity = (record["tool_uid"], record["invocation_uid"], record["outcome"])
        with self._lock:
            if identity in self._seen:
                # Projection uniqueness (AC2). Counted (A152 F4): an operator
                # reading the counter surface must be able to reconcile
                # attempted against every disposition without reading source —
                # uncounted dedup read as five vanished records.
                self._bump("deduplicated")
                return
            if len(self._heap) >= self._capacity:
                self._evict_for(keep, record)
            else:
                self._enqueue(keep, record)
                self._seen.add(identity)
                self._bump("enqueued")

    def _enqueue(self, keep: int, record: dict) -> None:
        self._seq += 1
        heapq.heappush(self._heap, (-keep, self._seq, record))

    def _evict_for(self, incoming_keep: int, record: dict) -> None:
        """Overload policy (AC6): drop the least valuable first. Entries heap
        as (-keep, seq, record), so the least valuable is the MINIMUM keep —
        found here as max by -keep, i.e. max by the stored first field. If
        the incoming record is itself the least valuable thing considered, it
        is the drop — a weaker record never displaces a stronger one. (The
        selection below was briefly INVERTED — max by keep, evicting the most
        valuable — and the suite stayed green over it because the eviction
        test counted survivors without pinning identities; A152's verify
        caught it. The strengthened test now pins the survivor set.)"""
        worst = max(
            range(len(self._heap)),
            key=lambda i: self._heap[i][0],
        )
        worst_keep = -self._heap[worst][0]
        if worst_keep <= incoming_keep:
            evicted = self._heap.pop(worst)
            evicted_identity = (
                evicted[2]["tool_uid"],
                evicted[2]["invocation_uid"],
                evicted[2]["outcome"],
            )
            self._seen.discard(evicted_identity)
            self._bump("queue_dropped")
            self._enqueue(incoming_keep, record)
            self._seen.add(
                (record["tool_uid"], record["invocation_uid"], record["outcome"]))
            self._bump("enqueued")
        else:
            self._bump("queue_dropped")

    def drain(self) -> list[dict]:
        """Hand the buffered records to the drainer. Runs under the guard:
        nothing that happens in here may record (AC5)."""
        token = _SUPPRESSED.set(True)
        try:
            with self._lock:
                records = [entry[2] for entry in sorted(self._heap)]
                self._heap.clear()
                self._seen.clear()
            return records
        finally:
            _SUPPRESSED.reset(token)

    def counters(self) -> dict:
        token = _SUPPRESSED.set(True)
        try:
            snapshot = dict(self._counters)
            snapshot["coverage_window_utc"] = (
                _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H") + "Z"
            )
            return snapshot
        finally:
            _SUPPRESSED.reset(token)


_singleton = _Recorder()


@contextlib.contextmanager
def fresh_recorder(queue_size: int = _DEFAULT_QUEUE_SIZE) -> Iterator[_Recorder]:
    """Swap in a clean bounded recorder (tests, drainer staging)."""
    global _singleton
    previous = _singleton
    _singleton = _Recorder(queue_size=queue_size)
    try:
        yield _singleton
    finally:
        _singleton = previous


@contextlib.contextmanager
def telemetry_guard() -> Iterator[None]:
    """Suppress recording on this context (AC5). Producer, drainer,
    projector, schema-generator, and health-counter code run inside it."""
    token = _SUPPRESSED.set(True)
    try:
        yield
    finally:
        _SUPPRESSED.reset(token)



def sample_payload() -> dict:
    """A known-good caller payload (the A152 verify fixture).

    The exact dict that lands enqueued when passed to record_refused /
    record_failed — derived FROM the registry's caller_payload contract so
    it cannot drift from it. A cold caller copies this shape; the privacy
    mutation arm re-sends it with a secret field attached and must see the
    WHOLE record refused.
    """
    return {
        "tool_uid": "123abcd9",
        "invocation_uid": "inv-0001",
        "operation_uid": "op-0001",
        "attempt": 1,
        "reason_category": "policy-gate",
        "reason_code": "gate-refused",
        "retryability": "non-retryable",
        "segment_inputs": ["argo-private"],
        "gate_uid": "abcdef01",
        "harm_class": "irreversible-write",
    }


def record_refused(**payload) -> None:
    """Execution never began. Returns within the hot-path budget."""
    _singleton.submit("refused", payload)


def record_failed(**payload) -> None:
    """Execution began and did not complete. Returns within the budget."""
    _singleton.submit("failed", payload)


def counters() -> dict:
    """Recorder health, read by tooling — never emitted through the bus."""
    return _singleton.counters()


def drain() -> list[dict]:
    """Drain the process singleton (the drainer's entry point)."""
    return _singleton.drain()
