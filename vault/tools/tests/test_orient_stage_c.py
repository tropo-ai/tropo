#!/usr/bin/env python3
"""Contract-first Stage C plants, cut from dev-spec 2672f9d0's AC1-AC13.

WHY THIS FILE IS RED TODAY
--------------------------
``lib/orient_stage_c.py`` and ``lib/span_guard.py`` do not exist yet. That is
deliberate. 2672f9d0 §6 says it in the spec's own words: *"a suite written to
the implementation passes while the behaviour is wrong."* Every case below is
cut from an acceptance criterion, before the build. The module-scope imports
directly beneath this docstring fail loudly and exactly once; nothing here is
stubbed, mocked or weakened to manufacture green.

THE CONTRACT SURFACE THESE PLANTS PIN
-------------------------------------
``lib/span_guard.py`` (Lock 2's three clauses)::

    MAX_SPAN_SENTENCES: int          # decided: 3
    MAX_SPAN_BYTES: int              # decided: 600
    REPAIR_RETRY_BUDGET: int         # fixed at 1 by Lock 2
    SpanGuardRefusal(Exception)      # carries .reason
    REASON_NO_MATCH
    REASON_SPAN_SENTENCE_BOUND
    REASON_SPAN_BYTE_BOUND
    REASON_INCOMPLETE_BOUNDARY
    REASON_REPAIR_BUDGET_EXHAUSTED
    Locator(uid, body_sha256, char_start, char_end)
    ContextWindow(preceding, following)
    GuardedSpan(uid, span_text, context_window, locator)
    match_domain_bytes(path) -> bytes        # raw on-disk post-frontmatter bytes
    canonicalize(text) -> str                # NFC + quote/dash fold + ws collapse
    guard_span(*, uid, model_span_text, source_bytes) -> GuardedSpan
    guard_with_repair(*, uid, source_bytes, propose) -> GuardedSpan

``lib/orient_stage_c.py`` (C1/C2/C3 + the ephemeral block)::

    K_SURVIVORS: int                 # decided: 8
    PER_BODY_INPUT_BYTE_CAP: int    # ~8K per §2
    C1_TASK_CLASS: str               # decided: the parse-class route
    C2_TASK_CLASS: str               # the distill route
    C2_MAX_OUTPUT_TOKENS: int
    REPAIR_RETRY_BUDGET: int         # == span_guard.REPAIR_RETRY_BUDGET
    MODEL_CALL_FLOOR / MODEL_CALL_CEILING     # 2 / 3 per §2
    BODY_ROT_SCREENED: bool          # False — the named interim mode
    FIRST_SCALE_REHEARSAL_REQUIRED: bool
    RESPONSE_MAX_BYTES: int          # 4096
    FENCE_PROHIBITION: str           # substring of both system prompts
    C1_SYSTEM_PROMPT / C2_SYSTEM_PROMPT: str
    StageCRefusal(Exception)         # carries .reason
    REASON_MODEL_SUBSTITUTION / REASON_RESPONSE_CONTRACT / REASON_SPEND_CEILING
    REASON_SEGMENT_EGRESS / REASON_VIEWER_MISMATCH / REASON_AS_OF_MISMATCH
    REASON_SPAN_GUARD / REASON_UNREHEARSED_CORPUS_SCALE
    ParsedResponse(value, original_text, sha256)
    parse_model_json(text, *, field) -> ParsedResponse
    most_restricted_segment(classes) -> str
    StageCBlock(spans, circle, ranking, c1_brief, body_rot_screened,
                capture_log, replay_artifacts, model_calls, rehearsal_receipt)
    run_stage_c(**kwargs) -> StageCBlock

``run_stage_c`` is keyword-only. Stage B outputs (``ranking``, ``circle``,
``task_source``) are duck-typed so Stage C need not export input types; the
block's own types are Stage C's.

Wire shapes the model must emit (raw JSON, no fence — AC3)::

    C1 -> {"brief": "<one paragraph>"}
    C2 -> {"spans": [{"uid": "<8-hex>", "span_text": "<verbatim-ish>"}, ...]}

THE FOUR OPEN BUILD PARAMETERS OF §3 — DECIDED, AND WHY
-------------------------------------------------------
1. **K = 8.** Arithmetic, not taste. C2 is ONE batched Sonnet call against a
   $0.25 reservation. At §2's ~8K-token per-body cap, K=8 is $0.192 of input,
   K=10 is $0.240, and K=12 is $0.288 — over the reservation before a single
   output token. Output at 15,000 nano/token and the C1 brief carried in
   context push the real ceiling lower still. The durable property is the cost
   envelope, not the integer; K may be retuned against recall@K later, so the
   plants assert the envelope (see ``OpenBuildParameterTests``).
2. **Span upper bound: <= 3 sentences AND <= 600 bytes.** An unbounded span is
   Lock 2's paraphrase loophole by another name. Expressed in both units so the
   bound cannot fight AC8's complete-boundary requirement, and the guard must
   REJECT rather than truncate — truncating would break the boundary invariant
   it exists to protect.
3. **C1 runs on the parse class (Haiku)**, per §3's cost reasoning. The plants
   require the assignment to read from ONE named constant — and audit the
   source for hardcoded model literals — so moving C1 to Sonnet stays a
   one-line policy-conformant change rather than a re-spec.
4. **Repair-retry budget = 1**, fixed by Lock 2. A hard ceiling, not a default:
   a plant proves a second retry is refused.

SPEC/CODE NAMING MISMATCH RECORDED HERE, NOT INVENTED AWAY
----------------------------------------------------------
AC4 names ``MonthlyBeltError``. No such class exists anywhere in the tree. The
real one is ``lib.daily_spend.MonthlySpendLimitError`` (a ``DailySpendError``
subclass). These plants are written against the real name; the mismatch is
recorded in ``AC4SpendTests.test_ac4_monthly_fifty_dollar_utc_belt_is_enforced_and_reachable``.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import inspect
import json
import socket
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lib import daily_spend, llm, loop_metering, metered_model
from lib import normalized_body_hash as nbh
from lib.distiller_model_policy import (
    DAILY_CEILING_NANO_USD,
    MODEL_ROUTES,
    MONTHLY_CEILING_NANO_USD,
    POLICY_UID,
    POLICY_VERSION,
    PRICING_NANO_USD_PER_TOKEN,
    SEGMENT_CLASSES,
    DistillerModelPolicy,
    ModelRoute,
)
from lib.viewer_projection import OS_SEGMENT, Viewer

# The build under contract. Absent today: this is the one loud failure the
# whole suite is designed to produce, and it is the correct state.
from lib import orient_stage_c as osc
from lib import span_guard


# --------------------------------------------------------------------------- #
# Process-wide network guard — the sibling-suite idiom. A contract test that    #
# needs a real model is not a contract test.                                    #
# --------------------------------------------------------------------------- #
_SOCKET_PATCHERS = (
    mock.patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket.socket,
        "connect",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket.socket,
        "connect_ex",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket,
        "socket",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
)


def setUpModule():
    for patcher in _SOCKET_PATCHERS:
        patcher.start()


def tearDownModule():
    for patcher in reversed(_SOCKET_PATCHERS):
        patcher.stop()


# --------------------------------------------------------------------------- #
# Fixture vocabulary                                                            #
# --------------------------------------------------------------------------- #
RUN_UID = "aa00bb01"
RUNNER_UID = "6389dcd4"
TASK_UID = "7a5c0001"
DAY = "2026-07-31"
CLOCK = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
SNAPSHOT = "snapshot-stage-c-1"

# One paragraph, ASCII-only on purpose: the source has a straight apostrophe and
# a hyphen exactly where AC6's plant makes the model emit a curly quote and an
# em-dash.
TYPOGRAPHY_BODY = (
    "Stage C is extractive at span grain. "
    "The guard replaces the model's span text with the exact source bytes "
    "- never the reverse. "
    "Typography from the model must never reach the block.\n"
)
TYPOGRAPHY_SOURCE_SPAN = (
    "The guard replaces the model's span text with the exact source bytes "
    "- never the reverse."
)
TYPOGRAPHY_MODEL_SPAN = (
    "The guard replaces the model\u2019s span text with the exact source bytes "
    "\u2014 never the reverse."
)
SENTENCES_BODY = "Alpha one. Bravo two. Charlie three. Delta four. Echo five.\n"

# Four DISTINCT long sentences. Distinct on purpose: identical sentences would
# give a proposed span two equally valid source positions, and an ambiguous
# match is a separate contract question from the byte bound under test here.
LONG_SENTENCES = tuple(
    f"{ordinal}, the distiller reads the ranked survivors and returns the few "
    "verbatim spans the task actually needs, each one resolving to its exact "
    "governed source rather than to a paraphrase taken on faith by the reader."
    for ordinal in ("Firstly", "Secondly", "Thirdly", "Fourthly")
)
LONG_BODY = " ".join(LONG_SENTENCES) + "\n"
THREE_LONG_SENTENCES = " ".join(LONG_SENTENCES[:3])


def governed_markdown(uid: str, body: str, *, title: str = "Stage C plant") -> bytes:
    """One governed file whose post-fence bytes are exactly ``body``."""
    frontmatter = (
        f"uid: {uid}\n"
        f"title: {title}\n"
        "type: note\n"
        "status: active\n"
    )
    return f"---\n{frontmatter}---\n{body}".encode("utf-8")


@dataclass(frozen=True)
class FakeTaskSource:
    """Lock 3's C1 inputs: title + body + existing links, pre-loaded.

    Pre-loaded on purpose. AC9's ordering property is about *survivor* bodies:
    keeping the task's own text out of ``body_reader`` makes "before any body is
    read" a clean, unambiguous assertion rather than an off-by-one argument.
    """

    uid: str = TASK_UID
    title: str = "Wire Stage C's brief, select and guard"
    body: str = "Build C1/C2/C3 and the ephemeral block per the five Mike-locks."
    links: tuple[str, ...] = ("33ca5ad5", "4de4438e")


@dataclass(frozen=True)
class FakeRanking:
    """Stage B's stamped output. R2 requires viewer + as-of stamped at rank."""

    viewer: Viewer
    index_as_of: str
    uids: tuple[str, ...]
    authority: dict = field(default_factory=dict)


class RecordingCorpus:
    """A body reader that records read order and read count.

    Reads the raw on-disk post-frontmatter bytes through the guard's own match
    domain, so AC6(a)/AC7's "one read of those bytes, never the composed-index
    body copy" is exercised rather than asserted in the abstract.
    """

    def __init__(self, files: dict, events: list):
        self._files = files
        self._events = events
        self.reads: list = []

    def __call__(self, uid: str) -> bytes:
        self._events.append(("read", uid))
        self.reads.append(uid)
        return span_guard.match_domain_bytes(self._files[uid])


class FakeProvider:
    """A scripted provider bound to the metered edge's call signature.

    ``metered_model._call`` invokes ``provider_call(task, messages, max_tokens=,
    system=, metering_context=)``; anything Stage C routes through the metered
    edge lands here, so the plants see exactly what the wire would.
    """

    def __init__(self, events: list, *, responses=None, model_override=None,
                 usage_override=None, ledger_root=None):
        self._events = events
        self._responses = dict(responses or {})
        self._model_override = model_override
        self._usage_override = usage_override
        self._ledger_root = ledger_root
        self.calls: list = []
        self.ledger_at_call: list = []

    def script(self, task: str, payloads) -> "FakeProvider":
        self._responses[task] = list(payloads)
        return self

    def __call__(self, task, messages, **kwargs):
        self._events.append(("model", task))
        self.calls.append(
            {
                "task": task,
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens"),
                "system": kwargs.get("system"),
                "metering_context": kwargs.get("metering_context"),
            }
        )
        if self._ledger_root is not None:
            self.ledger_at_call.append(_ledger_reservations(self._ledger_root))
        queue = self._responses.get(task)
        if not queue:
            raise AssertionError(f"provider has no scripted response for {task!r}")
        payload = queue.pop(0) if len(queue) > 1 else queue[0]
        override = self._model_override
        if isinstance(override, dict):
            override = override.get(task)
        return llm.LockedLLMResponse(
            text=payload if isinstance(payload, str) else json.dumps(payload),
            model=override or llm.LOCKED_TASK_MODELS[task],
            usage=self._usage_override or locked_usage(),
        )


def locked_usage(**overrides) -> dict:
    usage = {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "service_tier": "standard",
        "inference_geo": "not_available",
    }
    usage.update(overrides)
    return usage


def _ledger_reservations(ledger_root: Path) -> dict:
    ledger = daily_spend.read_ledger(
        ledger_root,
        day=DAY,
        policy_uid=POLICY_UID,
        policy_version=POLICY_VERSION,
        daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
    )
    return {
        reservation_id: record["status"]
        for reservation_id, record in ledger["reservations"].items()
    }


def census(root: Path, *, exclude: Optional[Path] = None) -> dict:
    """Content census of every regular file under ``root``.

    Paths AND bytes, so a new file, a deleted file and an edited file are all
    caught by one equality assertion.
    """
    result = {}
    for path in sorted(root.rglob("*")):
        if exclude is not None and exclude in path.parents:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        result[path.relative_to(root).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return result


class StudioFixture:
    """A whole offline Studio: governed files, both index surfaces, the events
    plane, and the spend ledger. Everything Stage C could touch exists, so
    AC11's before/after census has something real to compare."""

    def __init__(self, bodies: dict):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name).resolve()
        (self.root / ".tropo").mkdir()
        (self.root / ".tropo/version.md").write_text("v2.0.0\n", encoding="utf-8")
        (self.root / "vault/files").mkdir(parents=True)
        (self.root / "vault/events/streams").mkdir(parents=True)
        (self.root / "vault/events/receipts").mkdir(parents=True)
        self.ledger_root = self.root / metered_model.LEDGER_RELATIVE_PATH
        self.ledger_root.mkdir(parents=True)

        self.files = {}
        rows = []
        for uid, body in bodies.items():
            path = self.root / f"vault/files/{uid}.md"
            path.write_bytes(governed_markdown(uid, body))
            self.files[uid] = path
            rows.append(
                {
                    "uid": uid,
                    "type": "note",
                    "status": "active",
                    "title": "Stage C plant",
                    # A DELIBERATELY DIVERGENT composed-index body copy. Lock
                    # 2(c) forbids Stage C from reading this; AC7's plant proves
                    # the locator hash tracks disk, not this.
                    "body": "COMPOSED INDEX COPY - STRIPPED AND STALE",
                }
            )
        (self.root / "vault/00-index.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        (self.root / "vault/00-archive-index.jsonl").write_text("", encoding="utf-8")
        # The third derived surface (index_surfaces line 508). Seeded as opaque
        # bytes so AC11's census proves an EXISTING derived index is not
        # mutated, not merely that no new one appears.
        (self.root / "vault/00-index.sqlite").write_bytes(
            b"SQLite format 3\x00stage-c-plant-derived-index"
        )
        (self.root / "vault/events/00-events.jsonl").write_text(
            json.dumps({"event": "evt_stage_c_plant_0001"}) + "\n", encoding="utf-8"
        )
        (self.root / "vault/events/streams/6147bbbaaf258b3c.jsonl").write_text(
            json.dumps({"event": "evt_stage_c_plant_0002"}) + "\n", encoding="utf-8"
        )
        (self.root / "vault/events/receipts/7a5c0001.jsonl").write_text(
            json.dumps({"receipt": "rcpt_stage_c_plant_0003"}) + "\n", encoding="utf-8"
        )

        daily_spend.initialize_ledger(
            self.ledger_root,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            day=DAY,
        )

    def close(self):
        self._temp.cleanup()

    def policy(self, **overrides) -> DistillerModelPolicy:
        """The post-A140 production policy: OS auto within ceilings (D3)."""
        base = dict(
            uid=POLICY_UID,
            version=POLICY_VERSION,
            status="active",
            state="active",
            runner_name="distiller-model-edge",
            runner_uid=RUNNER_UID,
            routes={
                task: ModelRoute(task, model, ceiling)
                for task, (model, ceiling) in MODEL_ROUTES.items()
            },
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            segment_egress={"os": "auto", "team": "ask", "private": "ask"},
            consent_mode="auto",
            egress_approved=True,
            production_enabled=True,
            disabled_reasons=(),
            source_path=self.root / "vault/files/0c938a95.md",
            index_path=self.root / "vault/00-index.jsonl",
            monthly_ceiling_nano_usd=MONTHLY_CEILING_NANO_USD,
        )
        base.update(overrides)
        return DistillerModelPolicy(**base)

    def binding(self) -> metered_model.RunBinding:
        return metered_model.RunBinding(
            RUN_UID,
            metered_model.GATEWAY_URL,
            f"sk-virtual-tropo-{RUN_UID}",
            self.root,
        )


class StageCCase(unittest.TestCase):
    """Shared Stage C harness: one Studio, one viewer, one scripted edge."""

    BODIES = {
        "aaaa0001": TYPOGRAPHY_BODY,
        "aaaa0002": SENTENCES_BODY,
    }
    BRIEF = (
        "The task needs the guard clause that keeps model typography out of the "
        "emitted block, judged against the source bytes on disk."
    )

    def setUp(self) -> None:
        self.fx = StudioFixture(self.BODIES)
        self.addCleanup(self.fx.close)
        self.viewer = Viewer(principal_uid="7a105001", private_segment_uid="b1a70001")
        self.events: list = []
        self.corpus = RecordingCorpus(self.fx.files, self.events)
        self._ids = iter(f"cc0000{index:02d}" for index in range(1, 40))

    def provider(self, *, spans=None, brief=None, **kwargs) -> FakeProvider:
        provider = FakeProvider(self.events, ledger_root=self.fx.ledger_root, **kwargs)
        provider.script(osc.C1_TASK_CLASS, [{"brief": brief or self.BRIEF}])
        provider.script(
            osc.C2_TASK_CLASS,
            [
                {
                    "spans": spans
                    if spans is not None
                    else [{"uid": "aaaa0001", "span_text": TYPOGRAPHY_MODEL_SPAN}]
                }
            ],
        )
        return provider

    def ranking(self, *, viewer=None, index_as_of=SNAPSHOT, uids=("aaaa0001",)):
        return FakeRanking(
            viewer=viewer if viewer is not None else self.viewer,
            index_as_of=index_as_of,
            uids=tuple(uids),
            authority={uid: 3 for uid in uids},
        )

    def run_stage_c(self, *, provider=None, **overrides):
        provider = provider if provider is not None else self.provider()
        kwargs = dict(
            task_uid=TASK_UID,
            task_source=FakeTaskSource(),
            viewer=self.viewer,
            visible_segments=frozenset({OS_SEGMENT}),
            index_as_of=SNAPSHOT,
            ranking=self.ranking(),
            circle=("aaaa0001", "aaaa0002"),
            seed_candidates=("aaaa0001",),
            body_reader=self.corpus,
            segment_class_of=lambda _uid: "os",
            run_binding=self.fx.binding(),
            provider_call=provider,
            policy_resolver=self.fx.policy,
            clock=lambda: CLOCK,
            reservation_id_factory=lambda: next(self._ids),
            environment={},
        )
        kwargs.update(overrides)
        return osc.run_stage_c(**kwargs)


def module_source(module) -> str:
    path = inspect.getsourcefile(module)
    if path is None:  # pragma: no cover - defensive
        raise AssertionError(f"{module!r} has no source file to audit")
    return Path(path).read_text(encoding="utf-8")


def code_string_literals(module) -> set:
    """Every string literal in a module's CODE, docstrings excluded.

    Audits what the module actually does, not what it says about itself: a
    docstring may name a model, an assignment may not.
    """
    tree = ast.parse(module_source(module))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


# =========================================================================== #
# AC1 — identity: the two pinned routes, and substitution REFUSES              #
# =========================================================================== #
class AC1IdentityTests(StageCCase):
    def test_ac1_c1_and_c2_read_their_models_from_the_policy_route_table(self):
        """C1/C2 pin the dated parse snapshot and the distill model."""
        self.assertIn(osc.C1_TASK_CLASS, MODEL_ROUTES)
        self.assertIn(osc.C2_TASK_CLASS, MODEL_ROUTES)
        self.assertEqual(
            MODEL_ROUTES[osc.C1_TASK_CLASS][0], "claude-haiku-4-5-20251001"
        )
        self.assertEqual(MODEL_ROUTES[osc.C2_TASK_CLASS][0], "claude-sonnet-4-6")
        # The dated snapshot, not the short alias: 4de4438e §1 layer 1.
        self.assertNotEqual(MODEL_ROUTES[osc.C1_TASK_CLASS][0], "claude-haiku-4-5")

    def test_ac1_open_param_3_c1_assignment_is_one_named_constant_not_a_literal(self):
        """§3's open parameter 3: moving C1 to Sonnet must stay a one-line change.

        A hardcoded model literal anywhere in Stage C would make that a re-spec,
        so the code's own string literals are audited — the constant is the only
        assignment, and MODEL_ROUTES is the only place a model name is read.
        """
        for module in (osc, span_guard):
            for literal in code_string_literals(module):
                with self.subTest(module=module.__name__, literal=literal):
                    self.assertFalse(
                        literal.startswith("claude-"),
                        msg=f"{literal!r} is hardcoded in {module.__name__}; "
                        "read the model from MODEL_ROUTES[C1_TASK_CLASS] instead",
                    )

    def test_ac1_response_model_identity_is_verified_on_every_call(self):
        """The edge refuses a substituted response model and retains the spend."""
        distill_model = MODEL_ROUTES[osc.C2_TASK_CLASS][0]
        substitute = next(
            model
            for model, _ceiling in MODEL_ROUTES.values()
            if model != distill_model
        )
        substituted = metered_model.call(
            osc.C2_TASK_CLASS,
            [{"role": "user", "content": "stage c distill probe"}],
            segment_classes=("os",),
            run_binding=self.fx.binding(),
            max_tokens=1024,
            system=osc.C2_SYSTEM_PROMPT,
            provider_call=FakeProvider(
                self.events,
                responses={osc.C2_TASK_CLASS: ['{"spans":[]}']},
                model_override=substitute,
            ),
            policy_resolver=self.fx.policy,
            clock=lambda: CLOCK,
            reservation_id_factory=lambda: next(self._ids),
            environment={},
        )
        self.assertIsInstance(substituted, metered_model.ModelRefusal)
        self.assertEqual(substituted.code, "MODEL_SUBSTITUTION")
        # "REFUSES, never downgrades": no result is returned on the cheaper
        # model, and the reservation is retained rather than quietly released.
        self.assertTrue(substituted.worst_case_retained)

    def test_ac1_stage_c_surfaces_substitution_as_a_refusal_not_a_downgrade(self):
        """A substituted C2 model must abort Stage C — never yield a block.

        C1 answers on its correct route so the refusal can only come from C2's
        identity check, and stays correct if C1 is ever moved to Sonnet.
        """
        distill_model = MODEL_ROUTES[osc.C2_TASK_CLASS][0]
        substitute = next(
            model
            for model, _ceiling in MODEL_ROUTES.values()
            if model != distill_model
        )
        provider = self.provider(
            model_override={osc.C2_TASK_CLASS: substitute}
        )
        with self.assertRaises(osc.StageCRefusal) as caught:
            self.run_stage_c(provider=provider)
        self.assertEqual(caught.exception.reason, osc.REASON_MODEL_SUBSTITUTION)


# =========================================================================== #
# AC2 — tier and geo                                                           #
# =========================================================================== #
class AC2TierAndGeoTests(StageCCase):
    def test_ac2_standard_only_requested_on_both_and_global_geo_on_sonnet_only(self):
        """Haiku rejects inference_geo as a request parameter; Sonnet asks for it."""
        parse_controls = dict(llm.LOCKED_TASK_REQUEST_CONTROLS[osc.C1_TASK_CLASS])
        distill_controls = dict(llm.LOCKED_TASK_REQUEST_CONTROLS[osc.C2_TASK_CLASS])
        self.assertEqual(parse_controls, {"service_tier": "standard_only"})
        self.assertEqual(
            distill_controls,
            {"service_tier": "standard_only", "inference_geo": "global"},
        )
        self.assertNotIn("inference_geo", parse_controls)

    def test_ac2_response_tier_must_report_standard(self):
        refusal = self._call_with_usage(locked_usage(service_tier="priority"))
        self.assertIsInstance(refusal, metered_model.ModelRefusal)
        self.assertEqual(refusal.code, "RECONCILIATION_REFUSED")
        self.assertIn("service_tier", refusal.message)

    def test_ac2_geo_is_recorded_whatever_it_reports(self):
        """Mike's option-3 ruling: any OS-segment geo is accepted AND recorded."""
        for reported in ("not_available", "global", "us"):
            with self.subTest(inference_geo=reported):
                fx = StudioFixture(self.BODIES)
                self.addCleanup(fx.close)
                result = metered_model.call(
                    osc.C2_TASK_CLASS,
                    [{"role": "user", "content": "stage c distill probe"}],
                    segment_classes=("os",),
                    run_binding=fx.binding(),
                    max_tokens=1024,
                    system=osc.C2_SYSTEM_PROMPT,
                    provider_call=FakeProvider(
                        self.events,
                        responses={osc.C2_TASK_CLASS: ['{"spans":[]}']},
                        usage_override=locked_usage(inference_geo=reported),
                    ),
                    policy_resolver=fx.policy,
                    clock=lambda: CLOCK,
                    reservation_id_factory=lambda: next(self._ids),
                    environment={},
                )
                self.assertIsInstance(result, metered_model.MeteredModelResult)
                self.assertEqual(result.usage["inference_geo"], reported)

    def test_ac2_thinking_and_server_tool_usage_counts_must_be_zero(self):
        thinking = self._call_with_usage(
            locked_usage(output_tokens_details={"thinking_tokens": 7})
        )
        self.assertEqual(thinking.code, "RECONCILIATION_REFUSED")
        self.assertIn("thinking_tokens", thinking.message)

        server_tools = self._call_with_usage(
            locked_usage(
                server_tool_use={"web_search_requests": 1, "web_fetch_requests": 0}
            )
        )
        self.assertEqual(server_tools.code, "RECONCILIATION_REFUSED")
        self.assertIn("server_tool_use", server_tools.message)

    def _call_with_usage(self, usage):
        fx = StudioFixture(self.BODIES)
        self.addCleanup(fx.close)
        return metered_model.call(
            osc.C2_TASK_CLASS,
            [{"role": "user", "content": "stage c distill probe"}],
            segment_classes=("os",),
            run_binding=fx.binding(),
            max_tokens=1024,
            system=osc.C2_SYSTEM_PROMPT,
            provider_call=FakeProvider(
                self.events,
                responses={osc.C2_TASK_CLASS: ['{"spans":[]}']},
                usage_override=usage,
            ),
            policy_resolver=fx.policy,
            clock=lambda: CLOCK,
            reservation_id_factory=lambda: next(self._ids),
            environment={},
        )


# =========================================================================== #
# AC3 — output contract                                                        #
# =========================================================================== #
class AC3OutputContractTests(unittest.TestCase):
    def test_ac3_both_system_prompts_forbid_markdown_fences(self):
        self.assertIn(osc.FENCE_PROHIBITION, osc.C1_SYSTEM_PROMPT)
        self.assertIn(osc.FENCE_PROHIBITION, osc.C2_SYSTEM_PROMPT)
        self.assertIn("fence", osc.FENCE_PROHIBITION.lower())

    def test_ac3_raw_json_is_the_preferred_accepted_form(self):
        parsed = osc.parse_model_json('{"brief":"one paragraph"}', field="c1")
        self.assertIsInstance(parsed, osc.ParsedResponse)
        self.assertEqual(parsed.value, {"brief": "one paragraph"})

    def test_ac3_exactly_one_bounded_lowercase_json_wrapper_is_tolerated(self):
        parsed = osc.parse_model_json(
            '```json\n{"brief":"one paragraph"}\n```', field="c1"
        )
        self.assertEqual(parsed.value, {"brief": "one paragraph"})

    def test_ac3_original_text_plus_hash_are_preserved_beside_every_parse(self):
        for text in ('{"brief":"x"}', '```json\n{"brief":"x"}\n```'):
            with self.subTest(text=text):
                parsed = osc.parse_model_json(text, field="c1")
                # The ORIGINAL text, fence and all — not the unwrapped body.
                self.assertEqual(parsed.original_text, text)
                self.assertEqual(
                    parsed.sha256,
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                )

    def test_ac3_prose_nesting_uppercase_and_multiples_are_all_refused(self):
        rejected = {
            "prose-before": 'Here you go: {"brief":"x"}',
            "prose-after": '{"brief":"x"} hope that helps',
            "uppercase-fence": '```JSON\n{"brief":"x"}\n```',
            "nested-fence": '```json\n{"brief":"```x```"}\n```',
            "multiple-fences": '```json\n{"a":1}\n```\n```json\n{"b":2}\n```',
            "unfenced-array": '[{"brief":"x"}]',
            "empty": "",
        }
        for label, text in rejected.items():
            with self.subTest(case=label):
                with self.assertRaises(osc.StageCRefusal) as caught:
                    osc.parse_model_json(text, field="c1")
                self.assertEqual(
                    caught.exception.reason, osc.REASON_RESPONSE_CONTRACT
                )

    def test_ac3_response_is_bounded_at_4096_bytes(self):
        self.assertEqual(osc.RESPONSE_MAX_BYTES, 4096)
        filler = "y" * (osc.RESPONSE_MAX_BYTES + 1)
        with self.assertRaises(osc.StageCRefusal) as caught:
            osc.parse_model_json(json.dumps({"brief": filler}), field="c1")
        self.assertEqual(caught.exception.reason, osc.REASON_RESPONSE_CONTRACT)


# =========================================================================== #
# AC4 — spend                                                                  #
# =========================================================================== #
class AC4SpendTests(StageCCase):
    def test_ac4_per_call_ceilings_are_one_cent_parse_and_twenty_five_cent_distill(self):
        """D1's ruled values, in nano-USD, read from the policy route table."""
        self.assertEqual(MODEL_ROUTES[osc.C1_TASK_CLASS][1], 10_000_000)
        self.assertEqual(MODEL_ROUTES[osc.C2_TASK_CLASS][1], 250_000_000)

    def test_ac4_reservation_exists_before_the_provider_is_ever_invoked(self):
        """The behaviour, not the existence of new code: metered_model already
        reserves before calling, and Stage C must inherit that ordering."""
        provider = self.provider()
        block = self.run_stage_c(provider=provider)
        self.assertEqual(len(provider.ledger_at_call), len(provider.calls))
        for index, snapshot in enumerate(provider.ledger_at_call):
            with self.subTest(call=index):
                # A live reservation exists in the ledger at the instant the
                # provider is entered. Reserve-then-call, never call-then-bill.
                self.assertIn("reserved", snapshot.values())
        self.assertGreaterEqual(len(block.model_calls), osc.MODEL_CALL_FLOOR)

    def test_ac4_every_call_reconciles_to_the_exact_provider_actual(self):
        provider = self.provider()
        block = self.run_stage_c(provider=provider)
        ledger = daily_spend.read_ledger(
            self.fx.ledger_root,
            day=DAY,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
        )
        self.assertEqual(len(ledger["reservations"]), len(block.model_calls))
        for receipt in block.model_calls:
            with self.subTest(task=receipt.task):
                record = ledger["reservations"][receipt.reservation_id]
                self.assertEqual(record["status"], "reconciled")
                expected = loop_metering.price_locked_usage_nano_usd(
                    receipt.model, locked_usage(), task=receipt.task
                )
                self.assertEqual(record["actual_nano_usd"], expected)
                self.assertEqual(receipt.actual_nano_usd, expected)
                self.assertLessEqual(
                    receipt.reserved_nano_usd,
                    MODEL_ROUTES[receipt.task][1],
                )

    def test_ac4_daily_five_dollar_ceiling_is_enforced(self):
        self.assertEqual(DAILY_CEILING_NANO_USD, 5_000_000_000)
        self._commit(DAY, "aa000001", 4_999_000_000)
        with self.assertRaises(daily_spend.DailySpendLimitError):
            self._reserve(DAY, "bb000001", 31_122_300)

    def test_ac4_monthly_fifty_dollar_utc_belt_is_enforced_and_reachable(self):
        """AC4 names ``MonthlyBeltError``. NO SUCH CLASS EXISTS.

        The real, shipped, enforced class is
        ``lib.daily_spend.MonthlySpendLimitError`` (a ``DailySpendError``
        subclass raised from ``daily_spend.reserve``). This plant is written
        against the real name; the spec text is what is wrong, and the mismatch
        is recorded here rather than papered over by inventing the class the
        spec imagined. Precondition row 4 of 2672f9d0 §1 cites
        ``MonthlyBeltError`` in ``lib/daily_spend.py`` as *verified on main* —
        it is not there, so that precondition was checked against a name that
        never shipped.
        """
        self.assertEqual(MONTHLY_CEILING_NANO_USD, 50_000_000_000)
        self.assertFalse(
            hasattr(daily_spend, "MonthlyBeltError"),
            msg="if MonthlyBeltError ever lands, reconcile AC4's naming",
        )
        for index in range(10):
            day = f"2026-07-{index + 1:02d}"
            self._commit(day, f"aa0000{index:02d}", 4_999_000_000)
        self.assertEqual(
            daily_spend.monthly_committed_nano_usd(
                self.fx.ledger_root,
                "2026-07",
                policy_uid=POLICY_UID,
                daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            ),
            49_990_000_000,
        )
        # Under the $5 day ceiling, over the $50 month belt: only the monthly
        # belt can refuse this, so the belt is genuinely load-bearing.
        with self.assertRaises(daily_spend.MonthlySpendLimitError):
            self._reserve(DAY, "bb000001", 31_122_300)

    def test_ac4_stage_c_fails_closed_when_the_monthly_belt_refuses(self):
        for index in range(10):
            day = f"2026-07-{index + 1:02d}"
            self._commit(day, f"aa0000{index:02d}", 4_999_000_000)
        with self.assertRaises(osc.StageCRefusal) as caught:
            self.run_stage_c()
        self.assertEqual(caught.exception.reason, osc.REASON_SPEND_CEILING)

    def test_ac4_fail_closed_on_an_unknown_usage_field(self):
        refusal = metered_model.call(
            osc.C2_TASK_CLASS,
            [{"role": "user", "content": "stage c distill probe"}],
            segment_classes=("os",),
            run_binding=self.fx.binding(),
            max_tokens=1024,
            system=osc.C2_SYSTEM_PROMPT,
            provider_call=FakeProvider(
                self.events,
                responses={osc.C2_TASK_CLASS: ['{"spans":[]}']},
                usage_override=locked_usage(mystery_tokens=3),
            ),
            policy_resolver=self.fx.policy,
            clock=lambda: CLOCK,
            reservation_id_factory=lambda: next(self._ids),
            environment={},
        )
        self.assertIsInstance(refusal, metered_model.ModelRefusal)
        self.assertEqual(refusal.code, "RECONCILIATION_REFUSED")
        self.assertIn("unknown fields", refusal.message)

    def test_ac4_fail_closed_on_an_unpriced_tier(self):
        with self.assertRaises(loop_metering.MeteringContractError):
            loop_metering.price_locked_usage_nano_usd(
                MODEL_ROUTES[osc.C2_TASK_CLASS][0],
                locked_usage(service_tier="batch"),
                task=osc.C2_TASK_CLASS,
            )

    def _commit(self, day, reservation_id, nano):
        try:
            daily_spend.initialize_ledger(
                self.fx.ledger_root,
                policy_uid=POLICY_UID,
                policy_version=POLICY_VERSION,
                daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
                day=day,
            )
        except daily_spend.DailySpendError:
            pass
        self._reserve(day, reservation_id, nano, monthly=None)

    def _reserve(self, day, reservation_id, nano, monthly=MONTHLY_CEILING_NANO_USD):
        return daily_spend.reserve(
            self.fx.ledger_root,
            day=day,
            policy_uid=POLICY_UID,
            policy_version=POLICY_VERSION,
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
            reservation_id=reservation_id,
            run_uid=RUN_UID,
            task=osc.C2_TASK_CLASS,
            model=MODEL_ROUTES[osc.C2_TASK_CLASS][0],
            segment_classes=("os",),
            worst_case_nano_usd=nano,
            monthly_ceiling_nano_usd=monthly,
        )


# =========================================================================== #
# AC5 — consent                                                                #
# =========================================================================== #
class AC5ConsentTests(StageCCase):
    def test_ac5_os_segment_runs_automatically_within_the_ceilings(self):
        block = self.run_stage_c()
        self.assertEqual(
            {receipt.segment_classes for receipt in block.model_calls}, {("os",)}
        )

    def test_ac5_team_and_private_chunks_refuse_at_the_model_edge(self):
        for segment in ("team", "private"):
            with self.subTest(segment=segment):
                fx = StudioFixture(self.BODIES)
                self.addCleanup(fx.close)
                refusal = metered_model.call(
                    osc.C2_TASK_CLASS,
                    [{"role": "user", "content": "stage c distill probe"}],
                    segment_classes=(segment,),
                    run_binding=fx.binding(),
                    max_tokens=1024,
                    system=osc.C2_SYSTEM_PROMPT,
                    provider_call=FakeProvider(
                        self.events,
                        responses={osc.C2_TASK_CLASS: ['{"spans":[]}']},
                    ),
                    policy_resolver=fx.policy,
                    clock=lambda: CLOCK,
                    reservation_id_factory=lambda: next(self._ids),
                    environment={},
                )
                self.assertIsInstance(refusal, metered_model.ModelRefusal)
                self.assertEqual(refusal.code, "CONSENT_DENIED")

    def test_ac5_non_os_segments_stay_refused_even_when_egress_is_auto_approved(self):
        """The second, independent gate: bounded geo is hard-coded to OS."""
        fx = StudioFixture(self.BODIES)
        self.addCleanup(fx.close)
        refusal = metered_model.call(
            osc.C2_TASK_CLASS,
            [{"role": "user", "content": "stage c distill probe"}],
            segment_classes=("team",),
            run_binding=fx.binding(),
            max_tokens=1024,
            system=osc.C2_SYSTEM_PROMPT,
            provider_call=FakeProvider(
                self.events, responses={osc.C2_TASK_CLASS: ['{"spans":[]}']}
            ),
            policy_resolver=lambda: fx.policy(
                segment_egress={"os": "auto", "team": "auto", "private": "ask"}
            ),
            clock=lambda: CLOCK,
            reservation_id_factory=lambda: next(self._ids),
            environment={},
        )
        self.assertIsInstance(refusal, metered_model.ModelRefusal)
        self.assertEqual(refusal.code, "GEO_SCOPE_REFUSED")

    def test_ac5_cost_approval_never_substitutes_for_egress_approval(self):
        """Ceilings wide open, spend irrelevant — the unapproved egress refuses."""
        refusal = metered_model.call(
            osc.C2_TASK_CLASS,
            [{"role": "user", "content": "stage c distill probe"}],
            segment_classes=("os",),
            run_binding=self.fx.binding(),
            max_tokens=1024,
            system=osc.C2_SYSTEM_PROMPT,
            provider_call=FakeProvider(
                self.events, responses={osc.C2_TASK_CLASS: ['{"spans":[]}']}
            ),
            policy_resolver=lambda: self.fx.policy(egress_approved=False),
            clock=lambda: CLOCK,
            reservation_id_factory=lambda: next(self._ids),
            environment={},
        )
        self.assertIsInstance(refusal, metered_model.ModelRefusal)
        self.assertEqual(refusal.code, "CONSENT_DENIED")
        self.assertIsNone(refusal.reservation_id)

    def test_ac5_stage_c_refuses_by_name_when_a_non_os_chunk_reaches_the_edge(self):
        with self.assertRaises(osc.StageCRefusal) as caught:
            self.run_stage_c(
                segment_class_of=lambda uid: "team" if uid == "aaaa0001" else "os"
            )
        self.assertEqual(caught.exception.reason, osc.REASON_SEGMENT_EGRESS)


# =========================================================================== #
# AC6 — the span guard (Lock 2's three clauses)                                #
# =========================================================================== #
class AC6SpanGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = StudioFixture(
            {
                "aaaa0001": TYPOGRAPHY_BODY,
                "aaaa0002": SENTENCES_BODY,
            }
        )
        self.addCleanup(self.fx.close)
        self.typography = span_guard.match_domain_bytes(self.fx.files["aaaa0001"])
        self.sentences = span_guard.match_domain_bytes(self.fx.files["aaaa0002"])

    def test_ac6a_match_domain_is_the_raw_on_disk_post_frontmatter_bytes(self):
        """Clause (a): the existing shipped body_sha256 body definition.

        Bound to ``normalized_body_hash.raw_body_sha256`` (the validator's T1
        transform) rather than to a second, drifting definition of "body".
        """
        path = self.fx.files["aaaa0001"]
        self.assertEqual(self.typography, TYPOGRAPHY_BODY.encode("utf-8"))
        self.assertEqual(
            hashlib.sha256(self.typography).hexdigest(),
            nbh.raw_body_sha256(path),
        )
        self.assertNotIn(b"uid: aaaa0001", self.typography)

    def test_ac6b_the_models_typography_can_never_reach_the_block(self):
        """THE criterion: match under canonicalization, emit the source bytes."""
        guarded = span_guard.guard_span(
            uid="aaaa0001",
            model_span_text=TYPOGRAPHY_MODEL_SPAN,
            source_bytes=self.typography,
        )
        # The model sent a curly apostrophe and an em-dash; the source has
        # neither. The emitted span must be byte-identical to what is on disk.
        emitted = guarded.span_text.encode("utf-8")
        start = self.typography.index(TYPOGRAPHY_SOURCE_SPAN.encode("utf-8"))
        self.assertEqual(emitted, self.typography[start : start + len(emitted)])
        self.assertEqual(guarded.span_text, TYPOGRAPHY_SOURCE_SPAN)
        self.assertNotIn("\u2019", guarded.span_text)
        self.assertNotIn("\u2014", guarded.span_text)
        self.assertNotEqual(guarded.span_text, TYPOGRAPHY_MODEL_SPAN)

    def test_ac6b_the_locator_is_derived_source_side(self):
        guarded = span_guard.guard_span(
            uid="aaaa0001",
            model_span_text=TYPOGRAPHY_MODEL_SPAN,
            source_bytes=self.typography,
        )
        body = self.typography.decode("utf-8")
        self.assertEqual(
            body[guarded.locator.char_start : guarded.locator.char_end],
            guarded.span_text,
        )
        self.assertEqual(
            guarded.locator.body_sha256,
            hashlib.sha256(self.typography).hexdigest(),
        )

    def test_ac6b_canonicalization_folds_typography_for_matching_only(self):
        self.assertEqual(
            span_guard.canonicalize("the model\u2019s \u2014 span"),
            span_guard.canonicalize("the model's - span"),
        )
        self.assertEqual(
            span_guard.canonicalize("collapse   these\n\nspaces"),
            span_guard.canonicalize("collapse these spaces"),
        )
        # Canonicalization is a MATCHING aid, never an emission path: folding
        # must not make two genuinely different sentences equal.
        self.assertNotEqual(
            span_guard.canonicalize("Alpha one."),
            span_guard.canonicalize("Bravo two."),
        )

    def test_ac6b_no_match_after_canonicalization_is_rejected_by_name(self):
        with self.assertRaises(span_guard.SpanGuardRefusal) as caught:
            span_guard.guard_span(
                uid="aaaa0001",
                model_span_text="This sentence is nowhere in the source at all.",
                source_bytes=self.typography,
            )
        self.assertEqual(caught.exception.reason, span_guard.REASON_NO_MATCH)

    def test_ac6b_repair_retry_budget_is_a_hard_ceiling_of_one(self):
        """§3 open parameter 4, fixed at 1 by Lock 2 — a ceiling, not a default."""
        self.assertEqual(span_guard.REPAIR_RETRY_BUDGET, 1)
        self.assertEqual(osc.REPAIR_RETRY_BUDGET, span_guard.REPAIR_RETRY_BUDGET)

        proposals = []

        def propose(previous_refusal):
            proposals.append(previous_refusal)
            return "Still nowhere in the source."

        with self.assertRaises(span_guard.SpanGuardRefusal) as caught:
            span_guard.guard_with_repair(
                uid="aaaa0001",
                source_bytes=self.typography,
                propose=propose,
            )
        self.assertEqual(
            caught.exception.reason, span_guard.REASON_REPAIR_BUDGET_EXHAUSTED
        )
        # One first attempt plus exactly one repair. A second retry is refused.
        self.assertEqual(len(proposals), 1 + span_guard.REPAIR_RETRY_BUDGET)
        self.assertIsNone(proposals[0])
        self.assertIsInstance(proposals[1], span_guard.SpanGuardRefusal)
        self.assertEqual(proposals[1].reason, span_guard.REASON_NO_MATCH)

    def test_ac6b_one_repair_is_allowed_and_still_emits_source_bytes(self):
        attempts = iter(
            ["Not in the source.", TYPOGRAPHY_MODEL_SPAN]
        )
        seen = []

        def propose(previous_refusal):
            seen.append(previous_refusal)
            return next(attempts)

        guarded = span_guard.guard_with_repair(
            uid="aaaa0001",
            source_bytes=self.typography,
            propose=propose,
        )
        self.assertEqual(len(seen), 2)
        self.assertEqual(guarded.span_text, TYPOGRAPHY_SOURCE_SPAN)

    def test_ac6_guard_rejects_rather_than_truncates(self):
        """Truncation would silently break AC8's complete-boundary invariant."""
        oversized = SENTENCES_BODY.strip()
        with self.assertRaises(span_guard.SpanGuardRefusal) as caught:
            span_guard.guard_span(
                uid="aaaa0002",
                model_span_text=oversized,
                source_bytes=self.sentences,
            )
        self.assertEqual(
            caught.exception.reason, span_guard.REASON_SPAN_SENTENCE_BOUND
        )


# =========================================================================== #
# AC7 — the locator, and ONE read of those bytes                               #
# =========================================================================== #
class AC7LocatorTests(StageCCase):
    def test_ac7_every_span_carries_uid_body_sha256_and_a_char_range(self):
        block = self.run_stage_c()
        self.assertTrue(block.spans)
        body = span_guard.match_domain_bytes(self.fx.files["aaaa0001"])
        for guarded in block.spans:
            with self.subTest(uid=guarded.uid):
                locator = guarded.locator
                self.assertEqual(locator.uid, guarded.uid)
                self.assertEqual(
                    locator.body_sha256, hashlib.sha256(body).hexdigest()
                )
                self.assertIsInstance(locator.char_start, int)
                self.assertIsInstance(locator.char_end, int)
                self.assertLess(locator.char_start, locator.char_end)
                self.assertEqual(
                    body.decode("utf-8")[locator.char_start : locator.char_end],
                    guarded.span_text,
                )

    def test_ac7_the_locator_tracks_disk_never_the_composed_index_body_copy(self):
        """Lock 2(c): the composed-index copy is stripped and can lag disk."""
        index_rows = [
            json.loads(line)
            for line in (self.fx.root / "vault/00-index.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        composed = {row["uid"]: row["body"] for row in index_rows}
        self.assertNotEqual(composed["aaaa0001"], TYPOGRAPHY_BODY)

        block = self.run_stage_c()
        disk_hash = hashlib.sha256(
            span_guard.match_domain_bytes(self.fx.files["aaaa0001"])
        ).hexdigest()
        composed_hash = hashlib.sha256(
            composed["aaaa0001"].encode("utf-8")
        ).hexdigest()
        for guarded in block.spans:
            self.assertEqual(guarded.locator.body_sha256, disk_hash)
            self.assertNotEqual(guarded.locator.body_sha256, composed_hash)

    def test_ac7_c2_and_c3_operate_on_one_read_of_those_bytes(self):
        block = self.run_stage_c()
        self.assertTrue(block.spans)
        for uid in set(self.corpus.reads):
            with self.subTest(uid=uid):
                self.assertEqual(
                    self.corpus.reads.count(uid),
                    1,
                    msg=f"{uid} was read {self.corpus.reads.count(uid)} times; "
                    "C2, C3 and the resolver share ONE read",
                )

    def test_ac7_a_repair_retry_does_not_trigger_a_second_read(self):
        provider = self.provider()
        provider.script(
            osc.C2_TASK_CLASS,
            [
                {"spans": [{"uid": "aaaa0001", "span_text": "Nowhere in source."}]},
                {"spans": [{"uid": "aaaa0001", "span_text": TYPOGRAPHY_MODEL_SPAN}]},
            ],
        )
        self.run_stage_c(provider=provider)
        self.assertEqual(self.corpus.reads.count("aaaa0001"), 1)


# =========================================================================== #
# AC8 — faithfulness: complete boundaries, context windows, decided bounds     #
# =========================================================================== #
class AC8FaithfulnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = StudioFixture(
            {"aaaa0002": SENTENCES_BODY, "aaaa0003": LONG_BODY}
        )
        self.addCleanup(self.fx.close)
        self.sentences = span_guard.match_domain_bytes(self.fx.files["aaaa0002"])
        self.long = span_guard.match_domain_bytes(self.fx.files["aaaa0003"])

    def test_ac8_spans_must_start_and_end_at_source_sentence_boundaries(self):
        with self.assertRaises(span_guard.SpanGuardRefusal) as caught:
            span_guard.guard_span(
                uid="aaaa0002",
                model_span_text="ravo two. Charlie three",
                source_bytes=self.sentences,
            )
        self.assertEqual(
            caught.exception.reason, span_guard.REASON_INCOMPLETE_BOUNDARY
        )

    def test_ac8_each_span_carries_the_preceding_and_following_sentence(self):
        guarded = span_guard.guard_span(
            uid="aaaa0002",
            model_span_text="Charlie three.",
            source_bytes=self.sentences,
        )
        self.assertEqual(guarded.context_window.preceding, "Bravo two.")
        self.assertEqual(guarded.context_window.following, "Delta four.")

    def test_ac8_the_context_window_is_deterministic(self):
        first = span_guard.guard_span(
            uid="aaaa0002",
            model_span_text="Charlie three.",
            source_bytes=self.sentences,
        )
        second = span_guard.guard_span(
            uid="aaaa0002",
            model_span_text="Charlie three.",
            source_bytes=self.sentences,
        )
        self.assertEqual(first, second)

    def test_ac8_context_window_at_a_body_edge_is_empty_not_absent(self):
        opening = span_guard.guard_span(
            uid="aaaa0002",
            model_span_text="Alpha one.",
            source_bytes=self.sentences,
        )
        self.assertEqual(opening.context_window.preceding, "")
        self.assertEqual(opening.context_window.following, "Bravo two.")

        closing = span_guard.guard_span(
            uid="aaaa0002",
            model_span_text="Echo five.",
            source_bytes=self.sentences,
        )
        self.assertEqual(closing.context_window.preceding, "Delta four.")
        self.assertEqual(closing.context_window.following, "")

    def test_ac8_open_param_2_upper_bound_is_three_sentences_and_six_hundred_bytes(self):
        """The decided bound. Unbounded spans are the paraphrase loophole."""
        self.assertEqual(span_guard.MAX_SPAN_SENTENCES, 3)
        self.assertEqual(span_guard.MAX_SPAN_BYTES, 600)

    def test_ac8_a_four_sentence_span_is_refused_on_the_sentence_bound(self):
        with self.assertRaises(span_guard.SpanGuardRefusal) as caught:
            span_guard.guard_span(
                uid="aaaa0002",
                model_span_text="Bravo two. Charlie three. Delta four. Echo five.",
                source_bytes=self.sentences,
            )
        self.assertEqual(
            caught.exception.reason, span_guard.REASON_SPAN_SENTENCE_BOUND
        )

    def test_ac8_a_three_sentence_span_over_six_hundred_bytes_is_refused(self):
        """Isolates the byte bound: exactly three complete sentences, so the
        sentence bound cannot be what refuses this."""
        self.assertEqual(len(LONG_SENTENCES[:3]), span_guard.MAX_SPAN_SENTENCES)
        self.assertGreater(
            len(THREE_LONG_SENTENCES.encode("utf-8")), span_guard.MAX_SPAN_BYTES
        )
        with self.assertRaises(span_guard.SpanGuardRefusal) as caught:
            span_guard.guard_span(
                uid="aaaa0003",
                model_span_text=THREE_LONG_SENTENCES,
                source_bytes=self.long,
            )
        self.assertEqual(caught.exception.reason, span_guard.REASON_SPAN_BYTE_BOUND)

    def test_ac8_a_span_within_both_bounds_is_admitted(self):
        guarded = span_guard.guard_span(
            uid="aaaa0002",
            model_span_text="Bravo two. Charlie three. Delta four.",
            source_bytes=self.sentences,
        )
        self.assertEqual(guarded.span_text, "Bravo two. Charlie three. Delta four.")
        self.assertLessEqual(
            len(guarded.span_text.encode("utf-8")), span_guard.MAX_SPAN_BYTES
        )


# =========================================================================== #
# AC9 — brief-then-judge (Lock 3): an ORDERING property                        #
# =========================================================================== #
class AC9BriefThenJudgeTests(StageCCase):
    def test_ac9_the_brief_is_written_before_any_survivor_body_is_read(self):
        """The ordering, not the existence, of the brief."""
        provider = self.provider()
        self.run_stage_c(provider=provider)
        self.assertTrue(self.events, "no ordered events were recorded")
        self.assertEqual(self.events[0], ("model", osc.C1_TASK_CLASS))
        first_read = next(
            index for index, event in enumerate(self.events) if event[0] == "read"
        )
        first_c1 = self.events.index(("model", osc.C1_TASK_CLASS))
        self.assertLess(
            first_c1,
            first_read,
            msg=f"C1 must precede every body read; got {self.events}",
        )

    def test_ac9_c1_reads_only_the_task_title_body_and_links(self):
        provider = self.provider()
        self.run_stage_c(provider=provider)
        task = FakeTaskSource()
        c1 = next(call for call in provider.calls if call["task"] == osc.C1_TASK_CLASS)
        payload = json.dumps(c1["messages"], sort_keys=True)
        self.assertIn(task.title, payload)
        self.assertIn(task.body, payload)
        for link in task.links:
            self.assertIn(link, payload)
        # No survivor body may be smuggled into the brief prompt.
        self.assertNotIn(TYPOGRAPHY_SOURCE_SPAN, payload)

    def test_ac9_candidate_spans_are_judged_against_the_brief_not_the_task_stub(self):
        provider = self.provider()
        self.run_stage_c(provider=provider)
        c2 = next(call for call in provider.calls if call["task"] == osc.C2_TASK_CLASS)
        payload = json.dumps(
            [c2["messages"], c2["system"]], sort_keys=True, default=str
        )
        self.assertIn(self.BRIEF, payload)

    def test_ac9_the_brief_is_carried_in_the_block(self):
        block = self.run_stage_c()
        self.assertEqual(block.c1_brief, self.BRIEF)

    def test_ac9_the_brief_is_logged_as_a_first_class_replay_artifact(self):
        block = self.run_stage_c()
        kinds = {artifact.kind for artifact in block.replay_artifacts}
        self.assertIn("c1_brief", kinds)
        artifact = next(
            item for item in block.replay_artifacts if item.kind == "c1_brief"
        )
        self.assertEqual(artifact.text, self.BRIEF)
        self.assertEqual(
            artifact.sha256, hashlib.sha256(self.BRIEF.encode("utf-8")).hexdigest()
        )

    def test_ac9_call_shape_is_two_calls_floor_three_ceiling(self):
        self.assertEqual(osc.MODEL_CALL_FLOOR, 2)
        self.assertEqual(osc.MODEL_CALL_CEILING, 3)
        block = self.run_stage_c()
        self.assertEqual(len(block.model_calls), osc.MODEL_CALL_FLOOR)
        self.assertEqual(
            [receipt.task for receipt in block.model_calls],
            [osc.C1_TASK_CLASS, osc.C2_TASK_CLASS],
        )

    def test_ac9_one_repair_reaches_the_ceiling_and_never_exceeds_it(self):
        provider = self.provider()
        provider.script(
            osc.C2_TASK_CLASS,
            [
                {"spans": [{"uid": "aaaa0001", "span_text": "Nowhere in source."}]},
                {"spans": [{"uid": "aaaa0001", "span_text": TYPOGRAPHY_MODEL_SPAN}]},
            ],
        )
        block = self.run_stage_c(provider=provider)
        self.assertEqual(len(block.model_calls), osc.MODEL_CALL_CEILING)
        self.assertLessEqual(len(provider.calls), osc.MODEL_CALL_CEILING)

    def test_ac9_the_ceiling_holds_when_every_repair_also_fails(self):
        """The budget as a CEILING, not as a happy path.

        The plant above scripts a repair that succeeds, which exercises the
        budget being spent but never the budget running out. A build that spent
        the budget PER SPAN rather than per batch passes that test and fails
        this one: four unguardable spans would buy four repair calls, and C2 is
        one batched call, so the per-run ceiling of three would be gone.

        Eight further failures are scripted and left available deliberately. If
        the ceiling holds, the provider never reaches them.
        """
        unplaceable = [
            {
                "spans": [
                    {"uid": "aaaa0001", "span_text": f"Absent sentence {n} entirely."}
                    for n in range(4)
                ]
            }
        ] * 9
        provider = self.provider()
        provider.script(osc.C2_TASK_CLASS, unplaceable)
        with self.assertRaises(osc.StageCRefusal) as caught:
            self.run_stage_c(provider=provider)
        # Refuses as a guard signal — an unguardable batch is not the same
        # answer as "the corpus has nothing to say."
        self.assertEqual(caught.exception.reason, osc.REASON_SPAN_GUARD)
        self.assertLessEqual(
            len(provider.calls),
            osc.MODEL_CALL_CEILING,
            msg="repairs are budgeted per batch; per-span spending blows the "
            "per-run ceiling the moment C2 proposes more than one bad span",
        )


# =========================================================================== #
# AC10 — interim mode; Stage C NEVER derives a rot verdict                     #
# =========================================================================== #
class AC10InterimModeTests(StageCCase):
    def test_ac10_the_block_carries_body_rot_screened_false(self):
        self.assertIs(osc.BODY_ROT_SCREENED, False)
        block = self.run_stage_c()
        self.assertIs(block.body_rot_screened, False)

    def test_ac10_rot_span_intrusion_is_a_scored_replay_metric_not_a_verdict(self):
        block = self.run_stage_c()
        kinds = {artifact.kind for artifact in block.replay_artifacts}
        self.assertIn("rot_span_intrusion", kinds)
        metric = next(
            item for item in block.replay_artifacts if item.kind == "rot_span_intrusion"
        )
        # A scored metric, not a verdict: it counts, it does not adjudicate.
        self.assertFalse(hasattr(metric, "verdict"))

    def test_ac10_stage_c_never_derives_a_rot_verdict(self):
        """A structural audit — Lock 1 says the gardener owns this, not Stage C."""
        forbidden_calls = {
            "judge_body",
            "derive_rot_verdict",
            "body_rot_verdict",
            "rot_verdict",
            "stamp_decay",
        }
        forbidden_imports = {"lib.gardener", "lib.gardener_body_judge", "lib.decay_gate"}
        for module in (osc, span_guard):
            with self.subTest(module=module.__name__):
                tree = ast.parse(module_source(module))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotIn(alias.name, forbidden_imports)
                    elif isinstance(node, ast.ImportFrom):
                        self.assertNotIn(node.module or "", forbidden_imports)
                    elif isinstance(node, ast.Call):
                        target = node.func
                        name = (
                            target.attr
                            if isinstance(target, ast.Attribute)
                            else getattr(target, "id", None)
                        )
                        self.assertNotIn(name, forbidden_calls)

    def test_ac10_the_block_exposes_no_rot_verdict_field(self):
        block = self.run_stage_c()
        fields = {name for name in dir(block) if not name.startswith("_")}
        self.assertIn("body_rot_screened", fields)
        self.assertEqual(
            {name for name in fields if "rot" in name}, {"body_rot_screened"}
        )


# =========================================================================== #
# AC11 — ephemerality (I5): the criterion most likely to be violated by         #
#        accident. Before/after census of files, index and the events plane.   #
# =========================================================================== #
class AC11EphemeralityTests(StageCCase):
    def test_ac11_stage_c_leaves_no_governed_write_and_no_index_mutation(self):
        before = census(self.fx.root, exclude=self.fx.ledger_root)
        block = self.run_stage_c()
        after = census(self.fx.root, exclude=self.fx.ledger_root)

        self.assertTrue(block.spans, "the run must have actually done work")
        self.assertEqual(
            before,
            after,
            msg="Stage C mutated the Studio outside the spend ledger",
        )

    def test_ac11_each_named_plane_is_unchanged_individually(self):
        planes = {
            "governed files": self.fx.root / "vault/files",
            "events plane": self.fx.root / "vault/events",
        }
        before = {name: census(path) for name, path in planes.items()}
        # All three derived index surfaces, byte for byte.
        surfaces = ("00-index.jsonl", "00-archive-index.jsonl", "00-index.sqlite")
        index_before = {
            name: (self.fx.root / "vault" / name).read_bytes() for name in surfaces
        }

        self.run_stage_c()

        for name, path in planes.items():
            with self.subTest(plane=name):
                self.assertEqual(before[name], census(path))
        for name in surfaces:
            with self.subTest(surface=name):
                self.assertEqual(
                    index_before[name], (self.fx.root / "vault" / name).read_bytes()
                )

    def test_ac11_the_only_mutation_anywhere_is_the_spend_ledger(self):
        before = census(self.fx.root)
        self.run_stage_c()
        after = census(self.fx.root)

        changed = {
            path
            for path in set(before) | set(after)
            if before.get(path) != after.get(path)
        }
        self.assertTrue(changed, "the metered edge must have written a reservation")
        ledger_prefix = self.fx.ledger_root.relative_to(self.fx.root).as_posix()
        for path in changed:
            with self.subTest(path=path):
                self.assertTrue(
                    path.startswith(ledger_prefix + "/"),
                    msg=f"{path} was written outside the spend ledger",
                )

    def test_ac11_the_block_is_never_stamped_committed_or_synced(self):
        block = self.run_stage_c()
        for attribute in ("stamp", "commit", "sync", "persist", "write"):
            with self.subTest(attribute=attribute):
                self.assertFalse(
                    hasattr(block, attribute),
                    msg=f"an ephemeral block must not expose .{attribute}()",
                )


# =========================================================================== #
# AC12 — the viewer floor (R1-R5)                                              #
# =========================================================================== #
class AC12ViewerFloorTests(StageCCase):
    def test_ac12_r2_viewer_is_stamped_at_rank_and_verified_at_distill(self):
        other = Viewer(principal_uid="7a105002", private_segment_uid="b1a70002")
        with self.assertRaises(osc.StageCRefusal) as caught:
            self.run_stage_c(ranking=self.ranking(viewer=other))
        self.assertEqual(caught.exception.reason, osc.REASON_VIEWER_MISMATCH)

    def test_ac12_r2_as_of_is_stamped_at_rank_and_verified_at_distill(self):
        with self.assertRaises(osc.StageCRefusal) as caught:
            self.run_stage_c(ranking=self.ranking(index_as_of="snapshot-other"))
        self.assertEqual(caught.exception.reason, osc.REASON_AS_OF_MISMATCH)

    def test_ac12_r1_resolution_does_not_leak_the_existence_of_invisible_items(self):
        block = self._block_with_hidden_seeds()
        rendered = repr(block)
        for hidden in ("dddd0001", "dddd0002", "dddd0003"):
            with self.subTest(hidden=hidden):
                self.assertNotIn(hidden, rendered)

    def test_ac12_r1_resolution_does_not_leak_the_cardinality_of_invisible_items(self):
        """The strongest form: the block is IDENTICAL whether the invisible items
        exist or not, so no count, total or gap can be inferred from it."""
        with_hidden = self._block_with_hidden_seeds()
        without_hidden = self._block_with_hidden_seeds(hidden=())
        self.assertEqual(with_hidden, without_hidden)

    def test_ac12_r4_the_capture_log_inherits_the_most_restricted_segment(self):
        self.assertEqual(set(SEGMENT_CLASSES), {"os", "private", "team"})
        self.assertEqual(osc.most_restricted_segment(("os",)), "os")
        self.assertEqual(osc.most_restricted_segment(("os", "team")), "team")
        self.assertEqual(osc.most_restricted_segment(("os", "team", "private")), "private")
        self.assertEqual(osc.most_restricted_segment(("team", "private")), "private")

        # Every chunk that survives AC5 today is OS-segment, so the inherited
        # value is "os" until a team segment exists. See the report: R4's
        # inheritance rule is only exercisable as a pure function right now.
        block = self.run_stage_c()
        self.assertEqual(
            set(block.capture_log.referenced_uids),
            {guarded.uid for guarded in block.spans},
        )
        self.assertEqual(block.capture_log.segment, "os")

    def test_ac12_r5_stage_c_passes_stage_b_authority_through_untouched(self):
        """R5 is Stage A+B's law; Stage C's obligation is non-regression."""
        ranking = self.ranking()
        block = self.run_stage_c(ranking=ranking)
        self.assertEqual(block.ranking, ranking)
        self.assertEqual(block.ranking.authority, ranking.authority)

    def _block_with_hidden_seeds(self, hidden=("dddd0001", "dddd0002", "dddd0003")):
        fx = StudioFixture(
            {
                "aaaa0001": TYPOGRAPHY_BODY,
                **{uid: "Hidden body.\n" for uid in hidden},
            }
        )
        self.addCleanup(fx.close)
        events: list = []
        corpus = RecordingCorpus(fx.files, events)
        provider = FakeProvider(events, ledger_root=fx.ledger_root)
        provider.script(osc.C1_TASK_CLASS, [{"brief": self.BRIEF}])
        provider.script(
            osc.C2_TASK_CLASS,
            [{"spans": [{"uid": "aaaa0001", "span_text": TYPOGRAPHY_MODEL_SPAN}]}],
        )
        ids = iter(f"ee0000{index:02d}" for index in range(1, 40))
        return osc.run_stage_c(
            task_uid=TASK_UID,
            task_source=FakeTaskSource(),
            viewer=self.viewer,
            visible_segments=frozenset({OS_SEGMENT}),
            index_as_of=SNAPSHOT,
            ranking=FakeRanking(
                viewer=self.viewer,
                index_as_of=SNAPSHOT,
                uids=("aaaa0001",),
                authority={"aaaa0001": 3},
            ),
            circle=("aaaa0001",),
            # The unfiltered FTS-fallback seed list, invisible items included:
            # R1 requires resolution THROUGH visible_segments.
            seed_candidates=("aaaa0001", *hidden),
            body_reader=corpus,
            segment_class_of=lambda uid: "os" if uid == "aaaa0001" else "private",
            run_binding=fx.binding(),
            provider_call=provider,
            policy_resolver=fx.policy,
            clock=lambda: CLOCK,
            reservation_id_factory=lambda: next(ids),
            environment={},
        )


# =========================================================================== #
# AC13 — first-scale rule (Canary Lane doctrine)                               #
# =========================================================================== #
class AC13FirstScaleTests(StageCCase):
    def test_ac13_a_corpus_scale_run_without_a_rehearsal_receipt_refuses(self):
        self.assertIs(osc.FIRST_SCALE_REHEARSAL_REQUIRED, True)
        with self.assertRaises(osc.StageCRefusal) as caught:
            self.run_stage_c(corpus_scale=True, rehearsal_receipt=None)
        self.assertEqual(
            caught.exception.reason, osc.REASON_UNREHEARSED_CORPUS_SCALE
        )

    def test_ac13_a_capped_rehearsal_with_receipts_is_admitted_and_recorded(self):
        receipt = {
            "kind": "capped-rehearsal",
            "approved_by": "7b921d17",
            "max_survivors": osc.K_SURVIVORS,
        }
        block = self.run_stage_c(corpus_scale=True, rehearsal_receipt=receipt)
        self.assertEqual(block.rehearsal_receipt, receipt)

    def test_ac13_an_ordinary_per_task_run_needs_no_rehearsal_receipt(self):
        block = self.run_stage_c()
        self.assertIsNone(block.rehearsal_receipt)


# =========================================================================== #
# §3's open build parameters — the arithmetic that decided them                #
# =========================================================================== #
class OpenBuildParameterTests(unittest.TestCase):
    # AC2 locks the geo policy to "bounded-any-recorded": the provider may
    # report ANY geo and it is recorded rather than refused. Sonnet is priced
    # 10% higher when it reports "us" (loop_metering.SONNET_US_PRICING...), so
    # the reservation must hold across every geo the contract admits, not just
    # the one the fixtures happen to send. See the report: pricing the envelope
    # on standard rates alone is a K1-i-shaped test — green while a US-geo run
    # blows the reservation.
    ADMISSIBLE_GEOS = ("not_available", "global", "us")

    def setUp(self) -> None:
        self.sonnet = MODEL_ROUTES["distill"][0]
        self.distill_ceiling = MODEL_ROUTES["distill"][1]
        self.input_price = PRICING_NANO_USD_PER_TOKEN[self.sonnet]["input_tokens"]

    def envelope_nano_usd(self, *, inference_geo, output_tokens):
        """Price C2's worst case through the SHIPPED pricing path.

        Not a re-derivation from the policy table: the geo premium lives in
        loop_metering, so a test that multiplies the table by hand cannot see
        it. Pricing through the real entry point is the whole point.
        """
        return loop_metering.price_locked_usage_nano_usd(
            self.sonnet,
            locked_usage(
                input_tokens=osc.K_SURVIVORS * osc.PER_BODY_INPUT_BYTE_CAP,
                output_tokens=output_tokens,
                inference_geo=inference_geo,
            ),
            task=osc.C2_TASK_CLASS,
        )

    def test_open_param_1_k_and_the_cap_match_the_ruling(self):
        """2672f9d0 §3 closed the open parameter. K=6, cap 8,000 BYTES.

        The pre-ruling form of this test asserted K was inside the spec's
        declared 8-12 range, which was derived against the reconciled cost path
        — the one that gates nothing. The ruling moved K below that range
        precisely because the admission path is stricter, so the old assertion
        was pinning a number to the wrong authority.
        """
        self.assertEqual(osc.K_SURVIVORS, 6)
        self.assertEqual(osc.PER_BODY_INPUT_BYTE_CAP, 8_000)
        # The unit is the finding, not a detail: this constant read
        # PER_BODY_INPUT_TOKEN_CAP while being applied to a byte slice, and an
        # 8,000-TOKEN body is ~32 KB. Naming it in bytes is what stops the
        # 4x miss recurring, so the name is asserted, not just the value.
        self.assertFalse(hasattr(osc, "PER_BODY_INPUT_TOKEN_CAP"))

    def test_open_param_1_k_survivors_input_alone_cannot_exhaust_the_reservation(self):
        """The decision's headline arithmetic: K bodies of input, no output yet."""
        for geo in self.ADMISSIBLE_GEOS:
            with self.subTest(inference_geo=geo):
                self.assertLess(
                    self.envelope_nano_usd(inference_geo=geo, output_tokens=0),
                    self.distill_ceiling,
                    msg="K survivors' input alone exhausts the distill reservation",
                )

    def test_open_param_1_the_k_cost_envelope_fits_under_every_geo_ac2_admits(self):
        """THE durable property. K itself may be retuned against recall@K; the
        envelope may not be exceeded, because C2 is ONE batched call against ONE
        $0.25 reservation — and AC2 lets the provider pick the geo, not us."""
        for geo in self.ADMISSIBLE_GEOS:
            with self.subTest(inference_geo=geo):
                total = self.envelope_nano_usd(
                    inference_geo=geo, output_tokens=osc.C2_MAX_OUTPUT_TOKENS
                )
                self.assertLessEqual(
                    total,
                    self.distill_ceiling,
                    msg=(
                        f"K={osc.K_SURVIVORS} at {osc.PER_BODY_INPUT_BYTE_CAP} "
                        f"tokens/body plus {osc.C2_MAX_OUTPUT_TOKENS} output tokens "
                        f"costs {total} nano-USD at inference_geo={geo!r}, against a "
                        f"{self.distill_ceiling} nano-USD reservation"
                    ),
                )

    def test_open_param_1_the_us_geo_premium_is_what_makes_that_envelope_bite(self):
        """Guards the guard: if 'us' ever stops costing more, the geo sweep above
        has quietly become the standard-pricing test it was written to replace."""
        standard = self.envelope_nano_usd(
            inference_geo="global", output_tokens=osc.C2_MAX_OUTPUT_TOKENS
        )
        premium = self.envelope_nano_usd(
            inference_geo="us", output_tokens=osc.C2_MAX_OUTPUT_TOKENS
        )
        self.assertGreater(premium, standard)

    def test_open_param_1_c2_output_budget_can_still_carry_a_full_legal_response(self):
        """The other side of the window.

        The envelope sweep above can be satisfied trivially by starving C2's
        output budget until it cannot emit the 4096-byte response AC3 permits.
        A JSON span list is worst-cased at ~3 bytes/token, so the budget must
        clear RESPONSE_MAX_BYTES // 3 for a full-size legal response to fit.
        Together the two bound C2_MAX_OUTPUT_TOKENS from both directions.
        """
        self.assertGreaterEqual(
            osc.C2_MAX_OUTPUT_TOKENS,
            osc.RESPONSE_MAX_BYTES // 3,
            msg="C2 cannot emit a full-size AC3-legal response within its budget",
        )

    def test_open_param_1_k_equals_twelve_still_overruns_before_one_output_token(self):
        """The arithmetic that ruled out the top of the range, re-checked against
        live pricing. If this ever fails, Sonnet input pricing moved and K is due
        a fresh decision — not a silent widening."""
        twelve = 12 * osc.PER_BODY_INPUT_BYTE_CAP * self.input_price
        self.assertGreater(twelve, self.distill_ceiling)

    def admission_nano_usd(self, *, request_bytes, output_tokens):
        """Price C2 through the ADMISSION path, which is a different function.

        The envelope tests above price ``price_locked_usage_nano_usd`` — the
        RECONCILED cost, computed after the provider reports what it actually
        used. But ``metered_model`` does not admit a call on reconciled cost;
        it cannot, because reconciliation happens after the call it is deciding
        whether to make. It admits on ``worst_case_request_cost_nano_usd``,
        which charges one input token per UTF-8 byte of the serialized request
        plus a fixed overhead, at the US-geo rate.

        Those two functions disagree, and an envelope certified against only
        the reconciled one certifies something the edge will refuse.
        """
        return loop_metering.worst_case_request_cost_nano_usd(
            self.sonnet,
            request_bytes=request_bytes,
            max_tokens=output_tokens,
        )

    def test_open_param_1_the_admission_path_prices_bytes_not_reconciled_tokens(self):
        """The two cost models are not interchangeable, and the gap is live.

        Pins the disagreement itself rather than either number. If the two
        paths are ever unified, this goes red and the envelope tests above
        become sufficient on their own — which is the outcome worth being told
        about.
        """
        full_batch = osc.K_SURVIVORS * osc.PER_BODY_INPUT_BYTE_CAP
        reconciled = self.envelope_nano_usd(
            inference_geo="us", output_tokens=osc.C2_MAX_OUTPUT_TOKENS
        )
        admission = self.admission_nano_usd(
            request_bytes=full_batch, output_tokens=osc.C2_MAX_OUTPUT_TOKENS
        )
        self.assertLessEqual(
            reconciled,
            self.distill_ceiling,
            msg="the reconciled envelope should fit; that is what K was tuned for",
        )
        self.assertGreater(
            admission,
            reconciled,
            msg="admission should cost more than reconciliation; if it no "
            "longer does, the envelope tests above no longer need this guard",
        )

    def test_open_param_1_the_ruled_configuration_admits_with_real_headroom(self):
        """The positive form of the tripwire this replaces.

        The old test recorded a live conflict: a full batch at the then-current
        K did not fit the admission path, and it said in its own failure
        message to delete it once the spec resolved that. 2672f9d0 §3 did, so
        it is deleted rather than relaxed.

        What replaces it is the property the ruling actually bought, which is
        not "it fits" but "it fits with room". K=7 admitted by roughly 1,400
        bytes and was rejected for that reason — the request-size figure is an
        estimate, and an envelope that survives only on an exact estimate is
        not an envelope. So this asserts a MARGIN, and it is keyed to the
        admission path because the reconciled path is the one that gates
        nothing and the one the original miss was tuned against.
        """
        full_batch = osc.K_SURVIVORS * osc.PER_BODY_INPUT_BYTE_CAP
        cost = self.admission_nano_usd(
            request_bytes=full_batch, output_tokens=osc.C2_MAX_OUTPUT_TOKENS
        )
        self.assertLess(cost, self.distill_ceiling)
        headroom = (self.distill_ceiling - cost) / self.distill_ceiling
        self.assertGreater(
            headroom,
            0.10,
            msg=f"ruled configuration admits with only {headroom:.1%} headroom; "
            "the ruling bought 12% and rejected K=7 for having too little",
        )
        # And the ceiling itself is not the thing that moved. It is Mike-ruled
        # at 7a4e9df1, and routing around a ruled value to make a first run fit
        # is the precedent the ruling explicitly declined to set.
        self.assertEqual(self.distill_ceiling, 250_000_000)

    def test_open_param_4_the_repair_budget_is_shared_not_duplicated(self):
        self.assertEqual(osc.REPAIR_RETRY_BUDGET, 1)
        self.assertEqual(osc.REPAIR_RETRY_BUDGET, span_guard.REPAIR_RETRY_BUDGET)
        self.assertEqual(
            osc.MODEL_CALL_CEILING,
            osc.MODEL_CALL_FLOOR + span_guard.REPAIR_RETRY_BUDGET,
        )


# =========================================================================== #
# §5 — out of scope, named so it does not creep                                #
# =========================================================================== #
class OutOfScopeTests(unittest.TestCase):
    def test_stage_c_builds_no_paraphrase_layer_and_no_auto_invalidation(self):
        forbidden = {
            "paraphrase",
            "precis",
            "summarise_body",
            "summarize_body",
            "auto_invalidate",
            "invalidate",
        }
        for module in (osc, span_guard):
            with self.subTest(module=module.__name__):
                tree = ast.parse(module_source(module))
                names = {
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                }
                self.assertEqual(names & forbidden, set())

    def test_stage_c_opens_no_network_and_no_vector_retrieval(self):
        forbidden_imports = {"requests", "urllib", "http", "socket", "httpx", "anthropic"}
        for module in (osc, span_guard):
            with self.subTest(module=module.__name__):
                tree = ast.parse(module_source(module))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotIn(
                                alias.name.split(".")[0], forbidden_imports
                            )
                    elif isinstance(node, ast.ImportFrom) and node.level == 0:
                        self.assertNotIn(
                            (node.module or "").split(".")[0], forbidden_imports
                        )


class SpanGuardSearchEquivalenceTests(unittest.TestCase):
    """The accelerated candidate search must decide exactly what the cubic
    enumeration decided — and must actually be taken.

    Placing a span used to compare EVERY run of source sentences by
    canonicalizing it, which is cubic in the sentence count: a 477-sentence
    governed body took 267 seconds to place one span and the vault's longest
    body is 2,905 sentences, so Stage C could not be run over the real corpus
    at all. The search now measures a run's canonical length by arithmetic and
    only canonicalizes the runs that could possibly match.

    Two things have to be true and neither implies the other. Every outcome —
    the emitted bytes, the locator, the context window, the refusal reason —
    has to be identical to the enumeration's. And the fast path has to be the
    one that produced them, which is why every case here re-runs itself
    against a forced-slow guard and compares, and why
    ``test_control_the_fast_path_is_the_one_under_test`` fails loudly if the
    two paths are secretly the same code.
    """

    #: Enough sentences that the cubic enumeration is measurably different
    #: work from the linear one, while still small enough to run both over
    #: every probe in this class on every test run.
    WIDE_BODY = " ".join(
        f"Sentence {n} carries its own distinct wording so that no two runs "
        f"of sentences in this body canonicalize alike."
        for n in range(24)
    ) + "\n"

    #: A body where one proposal matches TWO runs of different lengths, which
    #: is the only situation in which the longest-first rule changes what gets
    #: emitted. A blank line ends a sentence, so "Overview" and the line under
    #: it are two sentences whose join reads exactly like the single sentence
    #: further down — and the guard must prefer the two, not be satisfied by
    #: the one.
    AMBIGUOUS_BODY = (
        "Overview\n\nof the system. Overview of the system. Tail here.\n"
    )
    AMBIGUOUS_PROBE = "Overview of the system."

    def setUp(self) -> None:
        self.calls: list[str] = []
        real = span_guard.canonicalize

        def counting(text: str) -> str:
            self.calls.append(text)
            return real(text)

        patcher = mock.patch.object(span_guard, "canonicalize", counting)
        patcher.start()
        self.addCleanup(patcher.stop)

    @contextlib.contextmanager
    def _forced_slow(self):
        """Run the guard on the unaccelerated enumeration.

        Returning ``None`` from ``_canonical_sentences`` is the module's own
        documented escape hatch for a body whose decomposition it cannot
        vouch for, so this exercises the shipped fallback rather than a
        test-only branch.
        """
        with mock.patch.object(
            span_guard, "_canonical_sentences", return_value=None
        ):
            yield

    def _guarded(self, body: str, probe: str):
        source = body.encode("utf-8")
        try:
            got = span_guard.guard_span(
                uid="aaaa0001", model_span_text=probe, source_bytes=source
            )
            return (
                "ok", got.span_text, got.locator.char_start, got.locator.char_end,
                got.context_window.preceding, got.context_window.following,
                got.locator.body_sha256,
            )
        except span_guard.SpanGuardRefusal as refusal:
            return ("refused", refusal.reason)

    def _both(self, body: str, probe: str):
        fast = self._guarded(body, probe)
        with self._forced_slow():
            slow = self._guarded(body, probe)
        return fast, slow

    def _probes(self, body: str) -> list:
        """Every case the guard distinguishes, drawn from ``body`` itself."""
        spans = span_guard._sentence_spans(body)
        probes = []
        for first in range(len(spans)):
            for length in (1, 2, 3, 4):
                if first + length > len(spans):
                    continue
                text = body[spans[first][0]:spans[first + length - 1][1]]
                probes.append(text)                              # exact run
                probes.append(" ".join(text.split()))            # re-wrapped
                probes.append(text.replace("'", "\u2019")
                                  .replace(" - ", " \u2014 "))   # retyped
                if len(text) > 10:
                    probes.append(text[3:-3])                    # mid-clause
        probes += ["absent from this body entirely.", "", "   \n\t "]
        return probes

    def test_every_outcome_matches_the_unaccelerated_enumeration(self):
        bodies = {
            "wide": self.WIDE_BODY,
            "sentences": SENTENCES_BODY,
            "typography": TYPOGRAPHY_BODY,
            "long": LONG_BODY,
            "ambiguous": self.AMBIGUOUS_BODY,
        }
        compared = 0
        seen = set()
        for name, body in bodies.items():
            for probe in self._probes(body):
                with self.subTest(body=name, probe=probe[:48]):
                    fast, slow = self._both(body, probe)
                    self.assertEqual(fast, slow)
                    compared += 1
                    seen.add(fast[0] if fast[0] == "refused" else "ok")
                    if fast[0] == "refused":
                        seen.add(fast[1])
        # CONTROL. A body whose probes all miss would compare hundreds of
        # identical NO_MATCH refusals and prove nothing about the search.
        self.assertGreater(compared, 400)
        self.assertLessEqual(
            {
                "ok",
                span_guard.REASON_NO_MATCH,
                span_guard.REASON_INCOMPLETE_BOUNDARY,
                span_guard.REASON_SPAN_SENTENCE_BOUND,
            },
            seen,
            "the corpus of probes did not reach every outcome the search can "
            "produce, so equivalence was only shown for the easy ones",
        )

    def test_the_byte_bound_still_refuses_by_name(self):
        """The bounds are checked AFTER a run is located, so a pruned search
        must still find an over-long run in order to reject it."""
        fast, slow = self._both(LONG_BODY, THREE_LONG_SENTENCES)
        self.assertEqual(fast, slow)
        self.assertEqual(fast, ("refused", span_guard.REASON_SPAN_BYTE_BOUND))

    def test_control_the_fast_path_is_the_one_under_test(self):
        """Without this, every comparison above could be one path twice.

        Counts canonicalizations. The enumeration canonicalizes once per run
        of sentences, which is quadratic in the sentence count; the search
        canonicalizes once per sentence plus a whole-body check plus the few
        runs whose arithmetic says they could match.
        """
        probe = "absent from this body entirely."
        sentences = len(span_guard._sentence_spans(self.WIDE_BODY))
        self.assertGreater(sentences, 20)

        self.calls.clear()
        self._guarded(self.WIDE_BODY, probe)
        fast = len(self.calls)

        self.calls.clear()
        with self._forced_slow():
            self._guarded(self.WIDE_BODY, probe)
        slow = len(self.calls)

        self.assertGreater(
            slow, sentences * sentences // 4,
            "the forced-slow path did not enumerate runs, so it is not the "
            "enumeration this test is comparing against",
        )
        self.assertLess(
            fast, sentences * 3,
            "the accelerated path canonicalized once per run, so the prune "
            "did not happen and the equivalence tests above are vacuous",
        )

    def test_the_decomposition_is_checked_and_not_assumed(self):
        """``_canonical_sentences`` licenses the arithmetic, so it must refuse
        to license a decomposition that does not hold."""
        body = "Alpha one. Bravo two."
        spans = span_guard._sentence_spans(body)
        self.assertEqual(
            span_guard._canonical_sentences(body, spans),
            ["Alpha one.", "Bravo two."],
        )
        # A sentence list that omits real text between two spans: the join
        # cannot reproduce the body, so no licence is issued.
        self.assertIsNone(
            span_guard._canonical_sentences(body, [spans[0], (17, 21)])
        )

    def test_without_the_licence_every_run_is_a_candidate(self):
        runs = list(span_guard._candidate_runs(None, 4, 99))
        self.assertEqual(
            runs,
            [(4, 0), (3, 0), (3, 1), (2, 0), (2, 1), (2, 2),
             (1, 0), (1, 1), (1, 2), (1, 3)],
        )

    def test_candidates_keep_the_guards_longest_first_order(self):
        """Longest-first, then earliest.

        The lengths must DIFFER for the ordering to be observable at all —
        equal-length candidates sort the same either way, which is how an
        ordering test can pass while the ordering is reversed.
        """
        # "xx yy zz" is 8 characters across three pieces; so is "aaaaaaaa"
        # alone. Both are candidates for a target of 8, and the longer run
        # must be offered first.
        pieces = ["xx", "yy", "zz", "aaaaaaaa"]
        self.assertEqual(
            list(span_guard._candidate_runs(pieces, 4, 8)), [(3, 0), (1, 3)]
        )
        self.assertEqual(
            list(span_guard._candidate_runs(pieces, 4, 2)),
            [(1, 0), (1, 1), (1, 2)],
        )
        self.assertEqual(list(span_guard._candidate_runs(pieces, 4, 7)), [])

    def test_the_longer_run_wins_when_a_proposal_matches_two(self):
        """The ordering rule, at the guard's own surface rather than the
        enumerator's: a proposal that matches both a two-sentence run and a
        one-sentence run must be placed on the two."""
        source = self.AMBIGUOUS_BODY.encode("utf-8")
        spans = span_guard._sentence_spans(self.AMBIGUOUS_BODY)
        wanted = span_guard.canonicalize(self.AMBIGUOUS_PROBE)
        matching = [
            (length, first)
            for length in range(len(spans), 0, -1)
            for first in range(len(spans) - length + 1)
            if span_guard.canonicalize(
                self.AMBIGUOUS_BODY[spans[first][0]:spans[first + length - 1][1]]
            ) == wanted
        ]
        # CONTROL: without two matches of different lengths this test is a
        # tautology, and the ambiguity is delicate enough to lose to an edit.
        self.assertEqual(matching, [(2, 0), (1, 2)], "the fixture is not ambiguous")

        guarded = span_guard.guard_span(
            uid="aaaa0001",
            model_span_text=self.AMBIGUOUS_PROBE,
            source_bytes=source,
        )
        self.assertEqual(guarded.span_text, "Overview\n\nof the system.")
        self.assertEqual(
            (guarded.locator.char_start, guarded.locator.char_end), (0, 24)
        )
        fast, slow = self._both(self.AMBIGUOUS_BODY, self.AMBIGUOUS_PROBE)
        self.assertEqual(fast, slow)


if __name__ == "__main__":
    unittest.main()
