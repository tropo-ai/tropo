#!/usr/bin/env python3
"""Cut 4A binding refusal, fallback provenance, and constrained-double plants."""
from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path

from vault.tools.tests import test_distiller as legacy

import lib.distiller as di
import lib.distiller_content as dc
import lib.distiller_edge as de
import lib.distiller_query as dq
import lib.distiller_ranker as dr
import lib.task_circle as tc
import lib.viewer_projection as vp
import lib.metered_model as mm
from lib.distiller_model_policy import (
    DAILY_CEILING_NANO_USD,
    DistillerModelPolicy,
    MODEL_ROUTES,
    ModelRoute,
)


SNAPSHOT = "snapshot-edge-1"


def active_policy():
    return DistillerModelPolicy(
        uid="0c938a95",
        version="1.0.0",
        status="active",
        state="active",
        runner_name="distiller-model-edge",
        runner_uid="6389dcd4",
        routes={
            task: ModelRoute(task, model, ceiling)
            for task, (model, ceiling) in MODEL_ROUTES.items()
        },
        daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
        segment_egress={"os": "auto", "team": "auto", "private": "auto"},
        consent_mode="auto",
        egress_approved=True,
        production_enabled=True,
        disabled_reasons=(),
        source_path=Path("vault/files/0c938a95.md"),
        index_path=Path("vault/00-index.jsonl"),
    )


def model_result(text):
    return mm.MeteredModelResult(
        text=text,
        model="claude-sonnet-4-6",
        usage={"input_tokens": 1, "output_tokens": 1},
        receipt=mm.ModelReceipt(
            "a1b2c3d4",
            "2026-07-23",
            "0c938a95",
            "1.0.0",
            "abcd1234",
            "distill",
            "claude-sonnet-4-6",
            ("team",),
            1,
            1,
        ),
    )


class CountingLoader(dc.InMemoryContentLoader):
    def __init__(self, bodies, *, index_as_of=SNAPSHOT, max_chunk_bytes=8192):
        super().__init__(
            bodies,
            index_as_of=index_as_of,
            max_chunk_bytes=max_chunk_bytes,
        )
        self.calls = []

    def load_spans(self, source_uid):
        self.calls.append(source_uid)
        return super().load_spans(source_uid)


class EdgeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.roots = legacy._RootFactory()
        self.addCleanup(self.roots.cleanup)
        self.fx = legacy._OrientFixture(self.roots)
        self.fx.node("task0001", legacy.TEAM, type_="task", status="active")
        self.fx.node("note0001", legacy.TEAM, type_="note", status="active")
        self.fx.node("caps0001", legacy.TEAM, type_="capsule", status="locked")
        self.fx.node("memo0001", legacy.TEAM, type_="memory", status="draft")
        self.fx.rel("task0001", "note0001", "refs")
        self.fx.rel("task0001", "caps0001", "governed_by")
        self.fx.rel("task0001", "memo0001", "refs")
        self.viewer = legacy.bob()
        self.circle_index = tc.InMemoryStructuralIndex(
            self.fx._structures, index_as_of=SNAPSHOT
        )
        result = di.orient_deterministic(
            "task0001",
            self.viewer,
            16,
            projection=self.fx.projection(),
            circle_index=self.circle_index,
            rank_index=self.fx.rank_index(),
        )
        self.assertTrue(result.ok, msg=result.error)
        self.deterministic = result.value
        self.assertEqual(
            self.deterministic.uids(), ("caps0001", "note0001", "memo0001")
        )
        self.bound = de.BoundOrientation(
            self.deterministic, self.viewer, SNAPSHOT
        )
        self.seeds = dq.PrevalidatedQuerySeeds(
            self.viewer, SNAPSHOT, ("note0001",), False
        )
        self.bodies = {
            "caps0001": "# Capsule\n\ncapsule truth",
            "note0001": "# Note\n\nnote truth",
            "memo0001": "# Memory\n\nmemory truth",
        }

    def run_distill(self, loader, *, double=None, budget=3, viewer=None, as_of=SNAPSHOT):
        return de.distill(
            self.bound,
            viewer or self.viewer,
            as_of,
            budget,
            intent="find truth",
            query_seeds=self.seeds,
            content_loader=loader,
            distill_double=double,
        )


class BindingRefusalTests(EdgeCase):
    def test_each_mismatch_refuses_before_first_loader_call(self):
        cases = (
            (
                vp.Viewer("other001", self.viewer.private_segment_uid),
                SNAPSHOT,
                SNAPSHOT,
            ),
            (
                vp.Viewer(self.viewer.principal_uid, "otherseg"),
                SNAPSHOT,
                SNAPSHOT,
            ),
            (self.viewer, "other-snapshot", SNAPSHOT),
            (self.viewer, SNAPSHOT, "loader-other"),
        )
        for viewer, requested, loader_snapshot in cases:
            with self.subTest(viewer=viewer, requested=requested, loader=loader_snapshot):
                loader = CountingLoader(
                    self.bodies, index_as_of=loader_snapshot
                )
                result = self.run_distill(
                    loader, viewer=viewer, as_of=requested
                )
                self.assertFalse(result.ok)
                self.assertEqual(
                    result.error.code, de.DistillErrorCode.BINDING_MISMATCH
                )
                self.assertEqual(loader.calls, [])

    def test_query_seed_binding_mismatch_also_precedes_read(self):
        loader = CountingLoader(self.bodies)
        forged = dq.PrevalidatedQuerySeeds(
            vp.Viewer(self.viewer.principal_uid, "wrong-private"),
            SNAPSHOT,
            ("note0001",),
            False,
        )
        result = de.distill(
            self.bound,
            self.viewer,
            SNAPSHOT,
            3,
            intent="intent",
            query_seeds=forged,
            content_loader=loader,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, de.DistillErrorCode.BINDING_MISMATCH)
        self.assertEqual(loader.calls, [])


class DeterministicFallbackTests(EdgeCase):
    def test_fallback_is_rank_then_span_order_with_total_provenance(self):
        loader = CountingLoader(self.bodies)
        result = self.run_distill(loader)
        self.assertTrue(result.ok, msg=result.error)
        distilled = result.value
        self.assertEqual(
            tuple(chunk.source_uid for chunk in distilled.chunks),
            self.deterministic.uids(),
        )
        for chunk in distilled.chunks:
            self.assertIs(chunk.why, self.deterministic.item(chunk.source_uid))
            self.assertEqual(chunk.freshness, de.FRESHNESS_UNKNOWN)
            expected = loader._bodies[chunk.source_uid]
            self.assertEqual(chunk.text, expected)
        self.assertTrue(distilled.fallback_used)
        self.assertEqual(distilled.shown_circle.seeds, self.seeds.uids)
        self.assertEqual(
            distilled.shown_circle.members, self.deterministic.circle.members
        )
        self.assertEqual(distilled.viewer, self.viewer)
        self.assertEqual(distilled.index_as_of, SNAPSHOT)
        self.assertIsNone(distilled.capture_id)
        self.assertEqual(distilled.capture_status, "pending")

    def test_fallback_preserves_each_sources_span_order_and_global_budget(self):
        loader = CountingLoader(
            {
                **self.bodies,
                "caps0001": "one one one\n\ntwo two two\n\nthree three three",
            },
            max_chunk_bytes=14,
        )
        result = self.run_distill(loader, budget=3)
        self.assertTrue(result.ok, msg=result.error)
        chunks = result.value.chunks
        self.assertEqual(len(chunks), 3)
        self.assertEqual({chunk.source_uid for chunk in chunks}, {"caps0001"})
        self.assertEqual(
            "".join(chunk.text for chunk in chunks), loader._bodies["caps0001"]
        )
        ranges = [
            (chunk.span_anchor.paragraph_start, chunk.span_anchor.paragraph_end)
            for chunk in chunks
        ]
        self.assertEqual(ranges, sorted(ranges))


class ConstrainedDoubleTests(EdgeCase):
    def candidates(self):
        return tuple(
            dc.chunk_body(uid, self.bodies[uid])
            for uid in self.deterministic.uids()
        )

    def test_valid_exact_selection_and_explained_reorder_succeed(self):
        by_uid = {
            uid: dc.chunk_body(uid, self.bodies[uid])[0]
            for uid in self.deterministic.uids()
        }

        def select_one(**_kwargs):
            span = by_uid["note0001"]
            return (de.SpanSelection(span.source_uid, span.span_anchor),)

        selected = self.run_distill(
            CountingLoader(self.bodies), double=select_one
        ).value
        self.assertFalse(selected.fallback_used)
        self.assertEqual(
            tuple(chunk.source_uid for chunk in selected.chunks), ("note0001",)
        )

        def explained_reorder(**_kwargs):
            lower = by_uid["note0001"]
            higher = by_uid["caps0001"]
            return (
                de.SpanSelection(
                    lower.source_uid, lower.span_anchor, "task-specific emphasis"
                ),
                de.SpanSelection(higher.source_uid, higher.span_anchor),
            )

        reordered = self.run_distill(
            CountingLoader(self.bodies), double=explained_reorder
        ).value
        self.assertFalse(reordered.fallback_used)
        self.assertEqual(
            tuple(chunk.source_uid for chunk in reordered.chunks),
            ("note0001", "caps0001"),
        )
        self.assertEqual(
            reordered.chunks[0].reorder_note, "task-specific emphasis"
        )

    def test_every_invalid_double_discards_all_output_and_matches_fallback(self):
        by_uid = {
            uid: dc.chunk_body(uid, self.bodies[uid])[0]
            for uid in self.deterministic.uids()
        }
        real = by_uid["caps0001"]
        unknown_anchor = dc.SpanAnchor((), 99, 99)

        def raises(**_kwargs):
            raise RuntimeError("boom")

        invalid = (
            lambda **_kwargs: "malformed",
            lambda **_kwargs: (),
            lambda **_kwargs: (
                de.SpanSelection("nonmember", real.span_anchor),
            ),
            lambda **_kwargs: (
                de.SpanSelection("caps0001", unknown_anchor),
            ),
            lambda **_kwargs: (
                de.SpanSelection(real.source_uid, real.span_anchor),
                de.SpanSelection(real.source_uid, real.span_anchor),
            ),
            lambda **_kwargs: (
                de.SpanSelection(
                    "note0001", by_uid["note0001"].span_anchor
                ),
                de.SpanSelection(
                    "caps0001", by_uid["caps0001"].span_anchor
                ),
            ),
            raises,
        )
        baseline = self.run_distill(CountingLoader(self.bodies)).value
        for double in invalid:
            with self.subTest(double=double):
                result = self.run_distill(
                    CountingLoader(self.bodies), double=double
                )
                self.assertTrue(result.ok, msg=result.error)
                self.assertEqual(result.value, baseline)

    def test_over_budget_double_falls_back(self):
        spans = {
            uid: dc.chunk_body(uid, body)[0] for uid, body in self.bodies.items()
        }

        def too_many(**_kwargs):
            return tuple(
                de.SpanSelection(uid, spans[uid].span_anchor)
                for uid in self.deterministic.uids()
            )

        result = self.run_distill(
            CountingLoader(self.bodies), double=too_many, budget=2
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertTrue(result.value.fallback_used)
        self.assertEqual(len(result.value.chunks), 2)


class DistillModelAdapterTests(unittest.TestCase):
    def setUp(self):
        self.span = dc.ContentSpan(
            "a0000001",
            dc.SpanAnchor((), 1, 1, True),
            "exact source truth",
        )

    def adapter(self, output):
        return de.DistillModelAdapter(
            run_binding=object(),
            segment_resolver=lambda uid: "team" if uid == "a0000001" else None,
            call_model=lambda *_args, **_kwargs: output,
            policy_resolver=active_policy,
        )

    def test_closed_selection_resolves_back_to_actual_anchor(self):
        output = model_result(
            json.dumps(
                {
                    "selections": [
                        {
                            "source_uid": self.span.source_uid,
                            "span_anchor": self.span.span_anchor.canonical(),
                            "reorder_note": None,
                        }
                    ]
                }
            )
        )
        selected = self.adapter(output)(
            intent="truth",
            candidates=(self.span,),
            chunk_budget=1,
        )
        self.assertEqual(
            selected,
            (de.SpanSelection(self.span.source_uid, self.span.span_anchor),),
        )
        self.assertIs(selected[0].span_anchor, self.span.span_anchor)

    def test_denial_malformed_nonmember_duplicate_and_extra_discard_whole(self):
        valid = {
            "source_uid": self.span.source_uid,
            "span_anchor": self.span.span_anchor.canonical(),
            "reorder_note": None,
        }
        outputs = (
            mm.ModelRefusal("CONSENT_DENIED", "ask"),
            model_result("{"),
            model_result(json.dumps({"selections": [{**valid, "extra": 1}]})),
            model_result(
                json.dumps(
                    {
                        "selections": [
                            {**valid, "source_uid": "b0000001"},
                        ]
                    }
                )
            ),
            model_result(json.dumps({"selections": [valid, valid]})),
        )
        for output in outputs:
            with self.subTest(output=output):
                with self.assertRaises(Exception):
                    self.adapter(output)(
                        intent="truth",
                        candidates=(self.span,),
                        chunk_budget=2,
                    )


class FrozenOutputTests(EdgeCase):
    def test_binding_and_output_dataclasses_are_frozen(self):
        distilled = self.run_distill(CountingLoader(self.bodies)).value
        for value, field, replacement in (
            (self.bound, "index_as_of", "other"),
            (distilled, "fallback_used", False),
            (distilled.chunks[0], "freshness", "fresh"),
        ):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(value, field, replacement)


if __name__ == "__main__":
    unittest.main()
