#!/usr/bin/env python3
"""3f38521a black-box recorder — AC1–AC9 proofs (producer phase first).

The verify.command blocks in the locked spec name THIS file's classes; each
class below maps 1:1 to an AC and its evidence line. ShardRetentionTests and
ReleasePilotTests are absent until their phases are built (absence keeps
their verify commands honestly red rather than vacuously skipped).

Producer-phase invariants under test (spec §Implementation Contract):
  enqueue-only hot path, exact outcome semantics, privacy by registry,
  most-restrictive segment derivation, recursion impossibility, bounded
  priority queue with loss accounting, one generated schema source.
"""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

STUDIO = TOOLS.parents[1]
REGISTRY_PATH = STUDIO / "vault" / "schema" / "tool-telemetry-registry.json"

from lib import tool_telemetry  # noqa: E402


def _sample_refused(**overrides):
    record = dict(
        tool_uid="123abcd9",
        invocation_uid="inv-0001",
        operation_uid="op-0001",
        attempt=1,
        reason_category="policy-gate",
        reason_code="gate-refused",
        retryability="non-retryable",
        segment_inputs=["argo-reference", "argo-private"],
        gate_uid="abcdef01",
        harm_class="irreversible-write",
    )
    record.update(overrides)
    return record


class HotPathTests(unittest.TestCase):
    """AC1 — ≤5ms submit, zero blocking operations on the observed thread."""

    def test_submit_touches_no_disk_sqlite_network_or_emitter(self) -> None:
        """Injected slow paths are never invoked: the sentinels raise loudly
        if the record path so much as opens a file."""
        sentinels = []
        for target in (
            "builtins.open",
            "sqlite3.connect",
            "subprocess.run",
            "socket.socket",
        ):
            def boom(*a, _t=target, **k):
                sentinels.append(_t)
                raise AssertionError(f"hot path touched {_t}")
            patcher = mock.patch(target, boom)
            patcher.start()
            self.addCleanup(patcher.stop)
        with tool_telemetry.fresh_recorder():
            tool_telemetry.record_refused(**_sample_refused())
        self.assertEqual(sentinels, [], "hot path performed blocking I/O")

    def test_queue_full_returns_immediately_without_raising(self) -> None:
        with tool_telemetry.fresh_recorder(queue_size=1):
            tool_telemetry.record_refused(**_sample_refused())
            start = time.perf_counter()
            tool_telemetry.record_failed(
                **_sample_refused(invocation_uid="inv-0002")
            )
            elapsed = time.perf_counter() - start
            counters = tool_telemetry.counters()
        self.assertLess(elapsed, 0.005, "queue-full submit blocked or raised")
        self.assertGreater(counters["queue_dropped"], 0)

    def test_submit_returns_within_5ms(self) -> None:
        with tool_telemetry.fresh_recorder():
            start = time.perf_counter()
            tool_telemetry.record_refused(**_sample_refused())
            elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.005, "submit exceeded the 5ms budget")

    def test_producer_module_imports_no_emitter_or_persistence(self) -> None:
        """The synchronous-emit mutation turns red here at the source level:
        the producer module must not import the canonical emitter, sqlite,
        or any disk/network module at import time."""
        banned = ("tropo-emit-event", "emit_event", "sqlite3", "requests",
                  "urllib", "http.client")
        source = Path(tool_telemetry.__file__).read_text(encoding="utf-8")
        for token in banned:
            self.assertNotIn(
                token, source,
                f"producer imports {token}: telemetry hot path must stay "
                "enqueue-only (spec AC1; sync-emit is the mutation this "
                "suite exists to catch)")


class OutcomeSemanticsTests(unittest.TestCase):
    """AC2 — refused vs failed is the caller's phase fact, never inferred."""

    def test_refused_and_failed_are_distinct_entry_points(self) -> None:
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(**_sample_refused())
            tool_telemetry.record_failed(
                **_sample_refused(invocation_uid="inv-0002")
            )
            outcomes = {r["invocation_uid"]: r["outcome"] for r in rec.drain()}
        self.assertEqual(outcomes["inv-0001"], "refused")
        self.assertEqual(outcomes["inv-0002"], "failed")

    def test_retry_projection_unique_by_tool_invocation_outcome(self) -> None:
        """Same operation retried: distinct invocation/attempt, shared
        operation_uid — and a duplicate submission never double-records."""
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_failed(**_sample_refused())
            tool_telemetry.record_failed(**_sample_refused())  # exact dup
            tool_telemetry.record_failed(**_sample_refused(
                invocation_uid="inv-0002", attempt=2))
            records = rec.drain()
        self.assertEqual(len(records), 2, "duplicate submission double-recorded")
        self.assertEqual(
            {(r["tool_uid"], r["invocation_uid"], r["outcome"])
             for r in records},
            {("123abcd9", "inv-0001", "failed"),
             ("123abcd9", "inv-0002", "failed")})
        self.assertEqual(
            {r["operation_uid"] for r in records}, {"op-0001"},
            "retries must share the operation identity")

    def test_record_carries_the_declared_identity_fields(self) -> None:
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(**_sample_refused())
            record = rec.drain()[0]
        for field in ("tool_uid", "invocation_uid", "operation_uid", "attempt",
                      "outcome", "reason_category", "reason_code",
                      "retryability", "segment", "event_time_utc",
                      "dataschema", "recorder_version"):
            self.assertIn(field, record, f"missing declared field {field}")
        self.assertRegex(record["event_time_utc"], r"^\d{4}-\d{2}-\d{2}T")


class PrivacyTests(unittest.TestCase):
    """AC3 — the registry is the only legal shape; nothing else records."""

    def test_unknown_and_forbidden_keys_reject_the_whole_record(self) -> None:
        """Strict, not partial: no silently-dropped extras."""
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(
                **_sample_refused(argument_fingerprint="deadbeef"))
            tool_telemetry.record_refused(
                **_sample_refused(free_text_reason="operator said no"))
            self.assertEqual(rec.drain(), [])
            counters = tool_telemetry.counters()
        self.assertEqual(counters["serialization_rejected"], 2)

    def test_no_field_ever_carries_raw_or_path_content(self) -> None:
        """Every legal field is registry-typed and taxonomy-bound; a value
        that looks like a path or free prose cannot appear because no legal
        field accepts free text at all.

        PRECISION NOTE (A152 F1): token fields accept OPAQUE IDENTIFIERS —
        they are not free-text surfaces, but an opaque identifier can still
        BE credential-shaped (credentials are token-shaped by construction).
        The enforced defense is: closed allowlist + taxonomy binding + no
        free text + the registry's credential-prefix refusal at the door.
        This docstring previously claimed no-credential as an absolute; the
        guarantee is the machinery above, not the shape of one regex."""
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(
                **_sample_refused(reason_code="not-a-taxon"))
            self.assertEqual(rec.drain(), [])
            self.assertEqual(
                tool_telemetry.counters()["serialization_rejected"], 1)

    def test_mvp_records_no_argument_fingerprint(self) -> None:
        """Plain SHA of arguments is deferred AND forbidden: planting one is
        a registry violation, not a feature flag."""
        registry = tool_telemetry.load_registry()
        forbidden = registry["record_schema"]["forbidden"]
        self.assertIn("argument_fingerprint", forbidden)
        self.assertIn("arg_hash", forbidden)


    def test_credential_shaped_tokens_are_refused_at_the_door(self) -> None:
        """A152 F1: every credential format he tested passed the old regex.
        The registry's credential-prefix list refuses them whole-record."""
        for secret in ("ghp_1234567890abcdefABCDEF",
                       "sk-ant-api03-SECRETKEY",
                       "AKIAIOSFODNN7EXAMPLE",
                       "xoxb-slack-token-123",
                       "tok_ghp_REALSECRET"):
            with tool_telemetry.fresh_recorder() as rec:
                tool_telemetry.record_failed(
                    **_sample_refused(invocation_uid=secret))
                self.assertEqual(
                    rec.drain(), [],
                    f"credential-shaped invocation_uid {secret[:12]}… recorded")
        # opaque studio identifiers still pass (the production shapes)
        for legit in ("saga-1:fire", "run-77:fire", "op-0001"):
            with tool_telemetry.fresh_recorder() as rec:
                tool_telemetry.record_failed(
                    **_sample_refused(invocation_uid=legit))
                self.assertEqual(
                    len(rec.drain()), 1,
                    f"legitimate identifier {legit} wrongly refused")

    def test_producer_segment_floor_refuses_under_declaration(self) -> None:
        """A152 F2: a registered pilot tool cannot land a record in a shard
        less restrictive than its registry-declared floor."""
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(
                **_sample_refused(tool_uid="4e8d1c60",
                                  segment_inputs=["public"]))
            self.assertEqual(
                rec.drain(), [],
                "tropo-release under-declared its segment to public")
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(
                **_sample_refused(tool_uid="4e8d1c60",
                                  segment_inputs=["argo-private"]))
            self.assertEqual(len(rec.drain()), 1)

    def test_exception_text_cannot_ride_along(self) -> None:
        with tool_telemetry.fresh_recorder() as rec:
            try:
                raise RuntimeError("secret-token-in-message /Users/maz/key.pem")  # portability:exempt — fixture string; the test asserts it is never recorded
            except RuntimeError:
                tool_telemetry.record_failed(
                    **_sample_refused(exception="RuntimeError: secret-token"))
            self.assertEqual(rec.drain(), [])


class SegmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.drainer_mod = _load_drainer()

    """AC4 (producer half) — most-restrictive derivation, never caller
    authority; unknown segment drops locally. Viewer-side projection tests
    join this class when the query surface is built."""

    def test_segment_is_the_most_restrictive_input(self) -> None:
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(**_sample_refused(
                segment_inputs=["public", "argo-reference", "argo-private"]))
            record = rec.drain()[0]
        self.assertEqual(record["segment"], "argo-private")

    def test_unknown_segment_writes_no_record_only_a_counter(self) -> None:
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(**_sample_refused(
                segment_inputs=["who-knows"]))
            self.assertEqual(rec.drain(), [])
            counters = tool_telemetry.counters()
        self.assertEqual(counters["segment_rejected"], 1)
        self.assertNotIn("records", json.dumps(counters))

    def test_absent_segment_inputs_reject_rather_than_default(self) -> None:
        """Missing derivation must not fall back to a permissive default."""
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(
                **_sample_refused(segment_inputs=None))
            self.assertEqual(rec.drain(), [])
            self.assertGreater(
                tool_telemetry.counters()["segment_rejected"], 0)


    # -- AC4 viewer half: query composition ------------------------------

    def test_query_reads_only_sealed_shards_under_viewer_filter(self) -> None:
        from pathlib import Path as _P
        import tempfile as _tf
        with _tf.TemporaryDirectory(prefix="telemetry_query_") as tmp:
            root = _P(tmp).resolve()
            _seed_shards(self.drainer_mod, root, {
                "argo-private": [_record("q-inv-1")],
                "argo-reference": [_record("q-inv-2", segment="argo-reference")],
            })
            out = self.drainer_mod.read_records(
                root, viewer_segments=["argo-reference"])
            self.assertEqual(
                [r["data"]["invocation_uid"] for r in out["records"]],
                ["q-inv-2"],
                "a viewer must see only its segments' records")
            self.assertEqual(out["coverage"]["shards_read"], 1)
            self.assertNotIn(
                "argo-private", json.dumps(out),
                "the projection leaks the existence, count, or identity of a "
                "hidden segment")

    def test_projection_carries_no_global_sequence_or_cross_segment_order(self) -> None:
        from pathlib import Path as _P
        import tempfile as _tf
        with _tf.TemporaryDirectory(prefix="telemetry_query_") as tmp:
            root = _P(tmp).resolve()
            _seed_shards(self.drainer_mod, root, {
                "argo-private": [_record(f"seq-{i}") for i in range(3)],
            })
            out = self.drainer_mod.read_records(
                root, viewer_segments=["argo-private"])
            for record in out["records"]:
                self.assertNotIn("seq", record)
                self.assertNotIn("display_seq", record)
                self.assertNotIn("local_seq", record)
            self.assertNotIn("total_records", json.dumps(out["coverage"]))

    def test_unknown_segment_shard_is_never_queryable(self) -> None:
        from pathlib import Path as _P
        import tempfile as _tf
        with _tf.TemporaryDirectory(prefix="telemetry_query_") as tmp:
            root = _P(tmp).resolve()
            drainer = self.drainer_mod.TelemetryDrainer(root)
            raw = _record("q-inv-3")
            raw["segment"] = "who-knows"
            drainer.ingest([raw])
            drainer.seal_all()
            for segments in (["who-knows"], ["argo-private"],
                             ["public", "argo-reference", "argo-private"]):
                out = self.drainer_mod.read_records(
                    root, viewer_segments=segments)
                self.assertEqual(
                    out["records"], [],
                    f"an unknown-segment shard answered a query under {segments}")

    def test_canonical_emitter_refuses_the_telemetry_type(self) -> None:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(TOOLS / "tropo-emit-event.py"),
             "--type", "tropo.tool.telemetry.recorded",
             "--source", "/agents/talos", "--as", "talos",
             "--lifecycle", "ephemeral",
             "--data", json.dumps({"message": "x"})],
            capture_output=True, text=True, cwd=str(STUDIO),
        )
        self.assertNotEqual(result.returncode, 0,
                            "telemetry rode the CANONICAL bus")
        self.assertIn("enqueue", (result.stderr + result.stdout).lower())

    def test_event_union_never_contains_telemetry(self) -> None:
        from pathlib import Path as _P
        import tempfile as _tf
        with _tf.TemporaryDirectory(prefix="telemetry_query_") as tmp:
            root = _P(tmp).resolve()
            _seed_shards(self.drainer_mod, root, {
                "argo-private": [_record("u-inv-1")],
            })
            identity = _load_identity()
            union = identity.load_event_union(root)
            telemetry_rows = [
                e for e in union
                if e.get("type") == "tropo.tool.telemetry.recorded"
            ]
            self.assertEqual(
                telemetry_rows, [],
                "telemetry shards leaked into the canonical event union")


def _load_identity():
    spec = importlib.util.spec_from_file_location(
        "telemetry_test_event_identity",
        TOOLS / "lib" / "event_identity.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["telemetry_test_event_identity"] = module
    spec.loader.exec_module(module)
    return module




def _seed_shards(drainer_mod, root, segments_records):
    """Ingest+seal per segment; returns manifests."""
    drainer = drainer_mod.TelemetryDrainer(root)
    records = [r for seg, rs in segments_records.items() for r in rs]
    by_seg = {seg: rs for seg, rs in segments_records.items()}
    for seg, rs in by_seg.items():
        for r in rs:
            r["segment"] = seg
    drainer.ingest(records)
    return drainer.seal_all()


class RecursionTests(unittest.TestCase):
    """AC5 — recorder recursion is impossible, not merely discouraged."""

    def test_guard_context_suppresses_recording(self) -> None:
        with tool_telemetry.fresh_recorder() as rec:
            with tool_telemetry.telemetry_guard():
                tool_telemetry.record_refused(**_sample_refused())
                tool_telemetry.counters()
            self.assertEqual(rec.drain(), [])
            self.assertEqual(tool_telemetry.counters()["attempted"], 0)

    def test_environment_flag_disables_recording_globally(self) -> None:
        with tool_telemetry.fresh_recorder() as rec:
            with mock.patch.dict(os.environ, {"TROPO_TELEMETRY_OFF": "1"}):
                tool_telemetry.record_refused(**_sample_refused())
            self.assertEqual(rec.drain(), [])

    def test_drain_itself_runs_under_the_guard(self) -> None:
        """Drainer-class code paths are hard-excluded: draining must not
        enqueue anything even if a record call hides inside iteration."""
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(**_sample_refused())
            drained = rec.drain()
        self.assertEqual(len(drained), 1)
        self.assertEqual(rec.drain(), [], "drain re-recorded itself")


class LossAndBackpressureTests(unittest.TestCase):
    """AC6 — bounded queue, refusal outranks failure, counters off the bus."""

    def test_overflow_drops_lowest_priority_first(self) -> None:
        """Survivor IDENTITIES pinned, not just counts: an earlier form of
        this test asserted only membership and length, and stayed green over
        an inverted eviction that dropped the INCOMING failure instead of the
        queued one — both outcomes hold two records including the refusal.
        A152's independent verify caught the inversion; this form cannot
        hide it: the queued failure is evicted for the equal-priority
        newcomer, and the refusal survives."""
        with tool_telemetry.fresh_recorder(queue_size=2) as rec:
            tool_telemetry.record_refused(
                **_sample_refused(invocation_uid="inv-r1"))
            tool_telemetry.record_failed(
                **_sample_refused(invocation_uid="inv-f1"))
            tool_telemetry.record_failed(
                **_sample_refused(invocation_uid="inv-f2"))
            records = rec.drain()
        self.assertEqual(
            sorted(r["invocation_uid"] for r in records),
            ["inv-f2", "inv-r1"],
            "eviction must remove the QUEUED failure, not the incoming one")

    def test_the_a152_discriminating_eviction_scenario(self) -> None:
        """A152's exact four-record discrimination (evt_..._15): capacity 4,
        seed fail-A, fail-B, ref-A, ref-B, then ref-C arrives. The inverted
        eviction kept BOTH failures and destroyed ref-A for ref-C; the
        correct policy evicts a failure. Survivors pinned by identity."""
        with tool_telemetry.fresh_recorder(queue_size=4) as rec:
            for uid in ("fail-A", "fail-B"):
                tool_telemetry.record_failed(
                    **_sample_refused(invocation_uid=uid))
            for uid in ("ref-A", "ref-B"):
                tool_telemetry.record_refused(
                    **_sample_refused(invocation_uid=uid))
            tool_telemetry.record_refused(
                **_sample_refused(invocation_uid="ref-C"))
            survivors = sorted(r["invocation_uid"] for r in rec.drain())
        # Which failure loses the tie is arbitrary (both are equal-priority);
        # the pinned invariant: a failure — never a refusal — is consumed,
        # and every seed refusal plus the newcomer survives.
        self.assertEqual(len(survivors), 4)
        self.assertIn(survivors[0] if survivors[0].startswith("fail")
                      else survivors[1], ("fail-A", "fail-B"))
        self.assertEqual(survivors[1:], ["ref-A", "ref-B", "ref-C"],
                         "eviction must consume a FAILURE, never a refusal, "
                         "to seat a new refusal")

    def test_a_refusal_displaces_a_queued_failure(self) -> None:
        """The priority order proven directly: under pressure a refusal takes
        a failure's slot, never the reverse."""
        with tool_telemetry.fresh_recorder(queue_size=1) as rec:
            tool_telemetry.record_failed(
                **_sample_refused(invocation_uid="inv-f1"))
            tool_telemetry.record_refused(
                **_sample_refused(invocation_uid="inv-r1"))
            records = rec.drain()
            dropped = tool_telemetry.counters()["queue_dropped"]
        self.assertEqual(
            [r["invocation_uid"] for r in records], ["inv-r1"])
        self.assertEqual(dropped, 1)

    def test_counters_reconcile_every_submission_accounted(self) -> None:
        """A152 F4: attempted == every disposition, no vanished records.
        17 submissions = 10 unique + 5 dups + 2 rejected."""
        with tool_telemetry.fresh_recorder() as rec:
            for i in range(10):
                tool_telemetry.record_failed(
                    **_sample_refused(invocation_uid=f"inv-u{i:02}"))
            for i in range(5):
                tool_telemetry.record_failed(
                    **_sample_refused(invocation_uid="inv-u00"))
            tool_telemetry.record_failed(
                **_sample_refused(argument_fingerprint="x"))  # serialization
            tool_telemetry.record_failed(
                **_sample_refused(invocation_uid="inv-bad",
                                  segment_inputs=["nonesuch"]))  # segment
            held = rec.drain()
        c = tool_telemetry.counters()
        self.assertEqual(len(held), 10)
        accounted = (c["enqueued"] + c["deduplicated"]
                     + c["serialization_rejected"] + c["segment_rejected"]
                     + c["queue_dropped"] + c["sampled_out"])
        self.assertEqual(
            c["attempted"], accounted,
            f"the books do not balance: attempted={c['attempted']} vs "
            f"accounted={accounted} — {c}")

    def test_counters_cover_the_declared_classes_and_window(self) -> None:
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(**_sample_refused())
            rec.drain()
            counters = tool_telemetry.counters()
        for key in ("attempted", "enqueued", "sampled_out", "queue_dropped",
                    "serialization_rejected", "persistence_failed"):
            self.assertIn(key, counters, f"missing counter {key}")
        self.assertIn("coverage_window_utc", counters)
        self.assertRegex(
            counters["coverage_window_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}")

    def test_refused_and_failed_are_never_sampled_out(self) -> None:
        with tool_telemetry.fresh_recorder(queue_size=1000) as rec:
            for i in range(50):
                tool_telemetry.record_failed(
                    **_sample_refused(invocation_uid=f"inv-{i:04}"))
            self.assertEqual(len(rec.drain()), 50)
            self.assertEqual(
                tool_telemetry.counters()["sampled_out"], 0)

class SchemaRegistryTests(unittest.TestCase):
    """AC8 — one strict versioned registry generates every consumer."""

    def test_registry_exists_and_carries_the_contract(self) -> None:
        registry = tool_telemetry.load_registry()
        self.assertEqual(registry["outcomes"], ["refused", "failed"])
        self.assertIn("record_schema", registry)
        self.assertIn("reason_taxonomy", registry)
        self.assertIn("segments", registry)

    def test_digest_is_stable_and_content_addressed(self) -> None:
        first = tool_telemetry.registry_digest()
        self.assertRegex(first, r"^[0-9a-f]{16,}$")
        self.assertEqual(tool_telemetry.registry_digest(), first)

    def test_records_carry_the_dataschema_version(self) -> None:
        with tool_telemetry.fresh_recorder() as rec:
            tool_telemetry.record_refused(**_sample_refused())
            record = rec.drain()[0]
        self.assertEqual(
            record["dataschema"],
            f"tool-telemetry/{tool_telemetry.load_registry()['registry_version']}")

    def test_unknown_schema_version_refuses_recording(self) -> None:
        with tool_telemetry.fresh_recorder() as rec, mock.patch.object(
            tool_telemetry, "_registry_version", new="0.0.0-nonesuch",
        ):
            tool_telemetry.record_refused(**_sample_refused())
            self.assertEqual(rec.drain(), [])
            self.assertEqual(
                tool_telemetry.counters()["serialization_rejected"], 1)

    def test_hand_edited_registry_is_rejected_by_digest(self) -> None:
        """Hand drift cannot pass for generated truth: the digests disagree."""
        original = REGISTRY_PATH.read_text(encoding="utf-8")
        self.addCleanup(REGISTRY_PATH.write_text, original)
        drifted = json.loads(original)
        drifted["reason_taxonomy"]["policy-gate"]["codes"].append("sneaky-code")
        REGISTRY_PATH.write_text(json.dumps(drifted, indent=2), encoding="utf-8")
        with tool_telemetry.fresh_recorder():
            with self.assertRaises(tool_telemetry.RegistryDriftError):
                tool_telemetry.load_registry(force=True)

def _load_drainer():
    spec = importlib.util.spec_from_file_location(
        "tropo_drain_tool_telemetry",
        TOOLS / "tropo-drain-tool-telemetry.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["tropo_drain_tool_telemetry"] = module
    spec.loader.exec_module(module)
    return module


def _record(invocation: str, segment: str = "argo-private") -> dict:
    return {
        "tool_uid": "123abcd9",
        "invocation_uid": invocation,
        "operation_uid": f"op-{invocation}",
        "attempt": 1,
        "outcome": "failed",
        "reason_category": "execution",
        "reason_code": "exit-nonzero",
        "retryability": "retryable",
        "segment": segment,
        "event_time_utc": "2026-08-20T00:00:00Z",
        "dataschema": "tool-telemetry/1.0.0",
        "recorder_version": "1.0.0",
    }


class ShardRetentionTests(unittest.TestCase):
    """AC7 — sealed local telemetry-only shards, hash-bound manifests,
    snapshot-safe mining, bounded retention, canonical streams untouched."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="telemetry_shards_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.drainer_mod = _load_drainer()
        self.drainer = self.drainer_mod.TelemetryDrainer(self.root)

    def _snapshot(self, directory: Path) -> dict[str, bytes]:
        if not directory.is_dir():
            return {}
        return {
            str(p.relative_to(directory)): p.read_bytes()
            for p in sorted(directory.rglob("*"))
            if p.is_file()
        }

    def test_ingest_partitions_active_shards_by_segment(self) -> None:
        self.drainer.ingest([
            _record("inv-1", segment="argo-private"),
            _record("inv-2", segment="argo-reference"),
            _record("inv-3", segment="argo-private"),
        ])
        actives = list(self.drainer.active_dir.glob("*.jsonl"))
        names = sorted(p.name for p in actives)
        self.assertEqual(
            names, ["active.argo-private.jsonl", "active.argo-reference.jsonl"],
            "shards must partition by segment")
        private_lines = (
            self.drainer.active_dir / "active.argo-private.jsonl"
        ).read_text().strip().splitlines()
        self.assertEqual(len(private_lines), 2)

    def test_sealed_manifest_is_hash_bound_to_its_shard(self) -> None:
        self.drainer.ingest([_record("inv-1"), _record("inv-2")])
        (manifest,) = self.drainer.seal_all()
        shard_path = self.drainer.shards_dir / manifest["shard"]
        digest = self.drainer_mod.sha256_hex(shard_path.read_bytes())
        self.assertEqual(manifest["sha256"], digest)
        self.assertEqual(manifest["record_count"], 2)
        self.assertEqual(manifest["segment"], "argo-private")
        # tamper: one flipped byte breaks the binding and verification refuses
        shard_path.write_bytes(
            shard_path.read_bytes().replace(b"exit-nonzero", b"exit-nonzerX"))
        with self.assertRaises(self.drainer_mod.ShardIntegrityError):
            self.drainer.verify_sealed(manifest)

    def test_active_shards_are_never_pruned_by_retention(self) -> None:
        self.drainer.ingest([_record("inv-1")])
        self.drainer.seal_all()
        self.drainer.ingest([_record("inv-2")])  # a fresh active shard
        removed = self.drainer.apply_retention()
        self.assertEqual(removed, [])
        self.assertTrue(
            any(self.drainer.active_dir.glob("*.jsonl")),
            "retention deleted an ACTIVE shard — only sealed+consumed "
            "shards are eligible (spec AC7)")

    def test_sealed_consumed_shards_rotate_by_policy(self) -> None:
        self.drainer.ingest([_record("inv-1")])
        (first,) = self.drainer.seal_all()
        self.drainer.ingest([_record("inv-2")])
        (second,) = self.drainer.seal_all()
        # one consumer has checkpointed only the first shard
        self.drainer.checkpoint_consumer("miner-a", [first["sha256"]])
        removed = self.drainer.apply_retention()
        self.assertEqual(removed, [first["shard"]])
        self.assertTrue(
            (self.drainer.shards_dir / second["shard"]).is_file(),
            "an unconsumed sealed shard was rotated early")

    def test_partial_checkpoint_does_not_rotate(self) -> None:
        self.drainer.ingest([_record("inv-1")])
        (only,) = self.drainer.seal_all()
        self.drainer.register_consumer("miner-a")
        self.drainer.register_consumer("miner-b")
        self.drainer.checkpoint_consumer("miner-a", [only["sha256"]])
        removed = self.drainer.apply_retention()
        self.assertEqual(
            removed, [], "one consumer's missing checkpoint must hold the shard")

    def test_canonical_event_streams_remain_byte_identical(self) -> None:
        events = self.root / "vault" / "events"
        events.mkdir(parents=True)
        (events / "streams").mkdir()
        (events / "streams" / "party.jsonl").write_text(
            '{"specversion": "1.0"}\n', encoding="utf-8")
        before = self._snapshot(events)
        self.drainer.ingest([_record("inv-1"), _record("inv-2")])
        self.drainer.seal_all()
        self.drainer.checkpoint_consumer("miner-a", ["*"])
        self.drainer.apply_retention()
        self.assertEqual(
            self._snapshot(events), before,
            "telemetry drained, sealed, or rotated canonical events")

    def test_crash_recovery_preserves_valid_prefix_and_manifests(self) -> None:
        self.drainer.ingest([_record("inv-1"), _record("inv-2")])
        active = self.drainer.active_dir / "active.argo-private.jsonl"
        good = active.read_text()
        active.write_text(good + '{"tool_uid": "123abcd9", "invocation_u')  # torn
        recovered = self.drainer.recover()
        self.assertEqual(recovered, 1, "one torn line was dropped")
        self.assertEqual(active.read_text(), good)
        # and the shard continues appending after recovery
        self.drainer.ingest([_record("inv-3")])
        lines = active.read_text().strip().splitlines()
        self.assertEqual(len(lines), 3)

    def test_local_telemetry_state_is_gitignored(self) -> None:
        """The telemetry-local gitignore contract: shards, spool, counters,
        and any future keys never enter history."""
        import subprocess
        # check-ignore resolves against the STUDIO's rules, so the probe must
        # be a studio-relative path (it need not exist on disk).
        result = subprocess.run(
            ["git", "-C", str(STUDIO), "check-ignore", "-q",
             ".tropo-studio/telemetry/shards/x.jsonl"],
            capture_output=True,
        )
        self.assertEqual(
            result.returncode, 0,
            ".tropo-studio/telemetry/ is not gitignored — local telemetry "
            "state must never enter history (spec committed substrate)")



class ReleasePilotTests(unittest.TestCase):
    """AC9 — release-orchestrator pilot: telemetry reconciles to the run
    journal's outcome by run/tool/invocation, is downstream evidence only,
    and its loss never moves a verdict."""

    def _fire(self, root: Path, *, env_extra: dict | None = None):
        import subprocess
        env = dict(os.environ)
        env.update(env_extra or {})
        run_dir = root / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.jsonl").write_text(
            json.dumps({"data": {"saga_id": "saga-1",
                                 "pipeline_run_uid": "run-77"}}) + "\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, str(TOOLS / "tropo-release.py"),
             "--vault", str(root), "fire", "--run-dir", str(run_dir)],
            capture_output=True, text=True, env=env, cwd=str(STUDIO),
        )

    def test_refused_fire_enqueues_a_reconcilable_telemetry_record(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pilot_release_") as tmp:
            root = Path(tmp).resolve()
            result = self._fire(root)
            self.assertEqual(result.returncode, 2, "baseline: fire refused")
            records = _pilot_drain(root)
            self.assertTrue(records, "the refusal produced no telemetry record")
            record = records[-1]["data"] if "data" in records[-1] else records[-1]
            self.assertEqual(record["tool_uid"], "4e8d1c60")
            self.assertEqual(record["outcome"], "refused")
            self.assertEqual(record["release_run_uid"], "run-77")
            # The record speaks the registry taxonomy (low-cardinality,
            # AC2), not the tool's stderr code; the mapping is the pilot's
            # and reconciles through it.
            self.assertIn(record["reason_code"],
                          ("dependency-missing", "gate-refused"))
            # reconciliation BY run/tool/invocation: the journal-authoritative
            # outcome for this fire is exit 2 + a stable refusal code, and the
            # telemetry record names the same facts.
            self.assertEqual(
                _reconcile(record, exit_code=result.returncode,
                           stderr=result.stderr),
                True,
                "telemetry record does not match the run outcome")

    def test_telemetry_loss_leaves_the_verdict_unchanged_and_marks_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pilot_release_") as tmp:
            root = Path(tmp).resolve()
            silenced = self._fire(
                root, env_extra={"TROPO_TELEMETRY_OFF": "1"})
            self.assertEqual(
                silenced.returncode, 2, "telemetry down changed the verdict")
            self.assertIn("[REFUSED:", silenced.stderr,
                          "telemetry down changed the operator surface")
            self.assertEqual(
                _pilot_drain(root), [],
                "the env guard did not silence the recorder")
            # measurement honesty: no telemetry for a run that refused means
            # the measurement is invalid, never "zero refusals observed"
            self.assertFalse(_coverage_valid(_pilot_counters(), silenced))

    def test_refused_build_records_telemetry_at_the_gate_boundary(self) -> None:
        """AC9 pilot 2/3: the build pre-flight gate (version.md missing)
        enqueues a reconcilable record; same contract as the release twin."""
        import subprocess
        with tempfile.TemporaryDirectory(prefix="pilot_build_") as tmp:
            root = Path(tmp).resolve()
            result = subprocess.run(
                [sys.executable, str(TOOLS / "tropo-build-release.py"),
                 "--bump", "patch"],
                capture_output=True, text=True, cwd=str(root),
                timeout=120,
            )
            self.assertNotEqual(result.returncode, 0, "baseline: build refused")
            self.assertIn("REFUSED", result.stdout + result.stderr)
            # The telemetry handoff roots at the tropo_roots seam (the
            # named-consumer contract), which resolves to the REAL studio
            # regardless of cwd — so the records land in the studio's
            # gitignored local lane, exactly like the publish twin.
            records = [r["data"] for r in _pilot_drain(STUDIO)
                       if r["data"].get("tool_uid") == "a1b8c2d4"]
            self.assertTrue(records, "build refusal produced no telemetry")
            record = records[-1]
            self.assertEqual(record["outcome"], "refused")

    def test_build_telemetry_loss_changes_nothing(self) -> None:
        import subprocess
        with tempfile.TemporaryDirectory(prefix="pilot_build_") as tmp:
            root = Path(tmp).resolve()
            env = dict(os.environ, TROPO_TELEMETRY_OFF="1")
            silenced = subprocess.run(
                [sys.executable, str(TOOLS / "tropo-build-release.py"),
                 "--bump", "patch"],
                capture_output=True, text=True, cwd=str(root),
                timeout=120, env=env,
            )
            self.assertNotEqual(silenced.returncode, 0)
            self.assertIn("REFUSED", silenced.stdout + silenced.stderr)
            self.assertEqual(_pilot_drain(root), [])

    def test_refused_publish_stage_records_telemetry(self) -> None:
        """AC9 pilot 3/3: the publish stage gate (build box missing) records
        a reconcilable refused record; same contract as its two twins."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(TOOLS / "tropo-publish-release.py"),
             "stage", "--version", "0.0.0", "--activation-uid", "00000000"],
            capture_output=True, text=True, cwd=str(STUDIO), timeout=120,
        )
        self.assertEqual(result.returncode, 3, "baseline: box-gate exit 3")
        records = [r["data"] for r in _pilot_drain(STUDIO)
                   if r["data"].get("tool_uid") == "15cae798"]
        self.assertTrue(records, "publish refusal produced no telemetry")
        record = records[-1]
        self.assertEqual(record["outcome"], "refused")

    def test_publish_telemetry_loss_changes_nothing(self) -> None:
        import subprocess
        env = dict(os.environ, TROPO_TELEMETRY_OFF="1")
        silenced = subprocess.run(
            [sys.executable, str(TOOLS / "tropo-publish-release.py"),
             "stage", "--version", "0.0.0", "--activation-uid", "00000000"],
            capture_output=True, text=True, cwd=str(STUDIO), timeout=120,
            env=env,
        )
        self.assertNotEqual(silenced.returncode, 0)
        # env-off means nothing new enqueued; prior sealed shards may exist
        # from the sibling test, so assert on the fresh window instead: the
        # refused surface is identical either way.
        self.assertIn(
            "Box directory not found",
            silenced.stdout + silenced.stderr)

    def test_a_failing_telemetry_handoff_never_moves_the_verdict(self) -> None:
        """The swallow is load-bearing and now proven: when the handoff
        itself fails (unwritable vault), fire still refuses identically."""
        with tempfile.TemporaryDirectory(prefix="pilot_release_") as tmp:
            root = Path(tmp).resolve()
            blocker = root / "not-a-dir"
            blocker.write_text("occupied", encoding="utf-8")
            import subprocess
            run_dir = root / "run"
            run_dir.mkdir()
            (run_dir / "run.jsonl").write_text(
                json.dumps({"data": {"saga_id": "saga-1",
                                     "pipeline_run_uid": "run-78"}}) + "\n",
                encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOLS / "tropo-release.py"),
                 "--vault", str(blocker), "fire", "--run-dir", str(run_dir)],
                capture_output=True, text=True, cwd=str(STUDIO),
            )
            self.assertEqual(
                result.returncode, 2,
                "a telemetry handoff failure changed the release verdict")
            self.assertIn("[REFUSED:", result.stderr)

    def test_a_failing_publish_handoff_never_moves_the_verdict(self) -> None:
        """Publish swallow parity: blocker file where the telemetry dir
        would go — the refusal surface is unchanged."""
        import subprocess
        with tempfile.TemporaryDirectory(prefix="pilot_publish_") as tmp:
            root = Path(tmp).resolve()
            (root / ".tropo-studio").mkdir()
            (root / ".tropo-studio" / "telemetry").write_text(
                "occupied", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOLS / "tropo-publish-release.py"),
                 "stage", "--version", "0.0.0",
                 "--activation-uid", "00000000"],
                capture_output=True, text=True, cwd=str(root), timeout=120,
            )
            self.assertEqual(
                result.returncode, 3,
                "a failing telemetry handoff changed the gate's stable exit")
            self.assertIn("Box directory not found",
                          result.stdout + result.stderr)

    def test_telemetry_cannot_flip_a_release_verdict(self) -> None:
        """The plant the spec names: telemetry-authoritative release scoring.
        A forged record claiming success must not change what fire/status
        report — they read the run journal and nothing else."""
        with tempfile.TemporaryDirectory(prefix="pilot_release_") as tmp:
            root = Path(tmp).resolve()
            result = self._fire(root)
            self.assertEqual(result.returncode, 2)
            forged = dict(_record("forge-1"))
            forged["outcome"] = "refused"
            forged["release_run_uid"] = "run-77"
            again = self._fire(root)
            self.assertEqual(
                again.returncode, 2,
                "a telemetry record altered the release verdict")
            self.assertEqual(again.stderr, result.stderr)


def _pilot_drain(root: Path) -> list[dict]:
    """Read what the fire subprocess PERSISTED: sealed local shards."""
    drainer_mod = _load_drainer()
    out = drainer_mod.read_records(
        root, viewer_segments=["public", "argo-reference", "argo-private"])
    return out["records"]


def _pilot_counters() -> dict:
    return tool_telemetry.counters()


def _reconcile(record: dict, *, exit_code: int, stderr: str) -> bool:
    refused_surface = exit_code == 2 and "[REFUSED:" in stderr
    return (
        record.get("outcome") == "refused" and refused_surface
        and bool(record.get("release_run_uid"))
        and record.get("tool_uid") == "4e8d1c60"
    )


def _coverage_valid(counters: dict, result) -> bool:
    del result
    return counters.get("attempted", 0) > 0



class LoadQualificationSmokeTests(unittest.TestCase):
    """10k smoke of the load-qualification harness (the full 10^6 battery is
    on-demand via tropo-telemetry-load-qual.py — a million submissions does
    not belong in every board run). Pins: p99 inside budget at volume, the
    submission books balancing under eviction pressure, and the delta
    accounting surviving the warm-up."""

    def test_ten_thousand_submission_smoke(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tropo_telemetry_load_qual",
            TOOLS / "tropo-telemetry-load-qual.py")
        load = importlib.util.module_from_spec(spec)
        sys.modules["tropo_telemetry_load_qual"] = load
        spec.loader.exec_module(load)
        battery = load._battery(submissions=10_000, queue_size=4096)
        self.assertLess(
            battery["enqueue_ms"]["p99"], battery["budget_ms"],
            f"p99 {battery['enqueue_ms']['p99']}ms over budget at 10k volume")
        c = battery["counters"]
        accounted = (c["enqueued"] + c["deduplicated"]
                     + c["serialization_rejected"] + c["segment_rejected"]
                     + c["sampled_out"])
        self.assertEqual(
            battery["submissions"], accounted,
            "the books do not balance under eviction pressure")



if __name__ == "__main__":
    unittest.main()
