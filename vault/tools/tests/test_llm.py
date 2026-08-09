"""Cut 4C locked LLM route and legacy compatibility plants."""
from __future__ import annotations

import inspect
import os
import socket
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from lib import llm, loop_metering


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


def context(task="parse-query", admission_mode="production"):
    model = llm.LOCKED_TASK_MODELS[task]
    return llm.MeteringContext(
        reservation_id="a1b2c3d4",
        policy_uid="0c938a95",
        policy_version="1.6.0",
        task=task,
        model=model,
        admission_mode=admission_mode,
        segment_classes=("private",),
        utc_day="2026-07-23",
        run_uid="abcd1234",
        gateway_url="http://127.0.0.1:8080",
        virtual_key="sk-virtual-tropo-abcd1234",
    )


class FakeSdk:
    def __init__(self):
        self.module = ModuleType("anthropic")
        self.module.AuthenticationError = type("AuthenticationError", (Exception,), {})
        self.module.RateLimitError = type("RateLimitError", (Exception,), {})
        self.create = mock.Mock()
        self.client = SimpleNamespace(messages=SimpleNamespace(create=self.create))
        self.module.Anthropic = mock.Mock(return_value=self.client)

    def response(self, model, *, content=None, usage=None):
        return SimpleNamespace(
            model=model,
            content=content
            if content is not None
            else [SimpleNamespace(type="text", text='{"ok":true}')],
            usage=usage
            if usage is not None
            else SimpleNamespace(
                input_tokens=10,
                output_tokens=2,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                service_tier="standard",
                inference_geo="global",
                output_tokens_details=SimpleNamespace(thinking_tokens=0),
                server_tool_use=SimpleNamespace(
                    web_search_requests=0,
                    web_fetch_requests=0,
                ),
            ),
            stop_reason="end_turn",
        )


class LockedCallTests(unittest.TestCase):
    def setUp(self):
        self.sdk = FakeSdk()

    def invoke(self, task="parse-query"):
        model = llm.LOCKED_TASK_MODELS[task]
        self.sdk.create.return_value = self.sdk.response(model)
        with mock.patch.dict("sys.modules", {"anthropic": self.sdk.module}):
            return llm.call_locked(
                task,
                [{"role": "user", "content": "{}"}],
                max_tokens=32,
                system="closed",
                metering_context=context(task),
            )

    def test_exact_task_routes_and_usage_return(self):
        for task, model in llm.LOCKED_TASK_MODELS.items():
            with self.subTest(task=task):
                self.sdk.create.reset_mock()
                result = self.invoke(task)
                self.assertIsInstance(result, llm.LockedLLMResponse)
                self.assertEqual(result.model, model)
                self.assertEqual(result.usage["input_tokens"], 10)
                kwargs = self.sdk.create.call_args.kwargs
                self.assertEqual(kwargs["model"], model)
                self.assertEqual(kwargs["max_tokens"], 32)
                self.assertEqual(kwargs["system"], "closed")
                self.assertEqual(
                    {
                        key: kwargs[key]
                        for key in llm.LOCKED_TASK_REQUEST_CONTROLS[task]
                    },
                    dict(llm.LOCKED_TASK_REQUEST_CONTROLS[task]),
                )
                self.assertEqual(
                    set(kwargs),
                    {
                        "model",
                        "max_tokens",
                        "messages",
                        "system",
                        "extra_headers",
                        *llm.LOCKED_TASK_REQUEST_CONTROLS[task],
                    },
                )
                if task == "parse-query":
                    self.assertNotIn("inference_geo", kwargs)
                else:
                    self.assertEqual(kwargs["inference_geo"], "global")
                self.assertEqual(
                    kwargs["extra_headers"]["x-tropo-reservation-id"],
                    "a1b2c3d4",
                )
                self.assertEqual(
                    kwargs["extra_headers"]["x-tropo-admission-mode"],
                    "production",
                )
                self.assertEqual(
                    self.sdk.module.Anthropic.call_args.kwargs,
                    {
                        "api_key": "sk-virtual-tropo-abcd1234",
                        "base_url": "http://127.0.0.1:8080",
                        "max_retries": 0,
                        "timeout": 60.0,
                    },
                )

    def test_sdk_usage_validation_is_task_and_model_aware(self):
        haiku = llm.LOCKED_TASK_MODELS["parse-query"]
        sonnet = llm.LOCKED_TASK_MODELS["distill"]
        base = {
            "input_tokens": 1,
            "output_tokens": 1,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "service_tier": "standard",
        }
        for task, model in (("parse-query", haiku), ("distill", sonnet)):
            for geo in ("global", "us", "EU West / 東京?! #1", " "):
                with self.subTest(task=task, geo=geo):
                    self.sdk.create.return_value = self.sdk.response(
                        model,
                        usage={**base, "inference_geo": geo},
                    )
                    with mock.patch.dict(
                        "sys.modules",
                        {"anthropic": self.sdk.module},
                    ):
                        result = llm.call_locked(
                            task,
                            [{"role": "user", "content": "{}"}],
                            max_tokens=1,
                            metering_context=context(task),
                        )
                    self.assertEqual(result.usage["inference_geo"], geo)

    def test_locked_surface_has_no_model_override(self):
        self.assertNotIn("model", inspect.signature(llm.call_locked).parameters)
        with self.assertRaises(TypeError):
            llm.call_locked(
                "parse-query",
                [{"role": "user", "content": "{}"}],
                max_tokens=1,
                metering_context=context(),
                model="claude-opus-4-8",
            )
        for control in ("service_tier", "inference_geo"):
            with self.subTest(control=control):
                with self.assertRaises(TypeError):
                    llm.call_locked(
                        "parse-query",
                        [{"role": "user", "content": "{}"}],
                        max_tokens=1,
                        metering_context=context(),
                        **{control: "caller-override"},
                    )

    def test_unknown_task_refuses_before_sdk_construction(self):
        with mock.patch.dict("sys.modules", {"anthropic": self.sdk.module}):
            with self.assertRaisesRegex(RuntimeError, "unknown locked task"):
                llm.call_locked(
                    "alias",
                    [{"role": "user", "content": "{}"}],
                    max_tokens=1,
                    metering_context=context(),
                )
        self.sdk.module.Anthropic.assert_not_called()

    def test_context_task_model_mismatch_refuses_before_sdk(self):
        with self.assertRaisesRegex(RuntimeError, "context route mismatch"):
            llm.call_locked(
                "distill",
                [{"role": "user", "content": "{}"}],
                max_tokens=1,
                metering_context=context("parse-query"),
            )
        self.sdk.module.Anthropic.assert_not_called()

    def test_admission_mode_is_immutable_and_header_bound(self):
        canary = context(admission_mode="canary")
        self.assertEqual(canary.admission_mode, "canary")
        self.assertEqual(
            canary.gateway_headers()["x-tropo-admission-mode"],
            "canary",
        )
        for invalid in ("", "preview", "CANARY", None, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    context(admission_mode=invalid)

    def test_short_haiku_alias_response_is_an_explicit_negative(self):
        self.sdk.create.return_value = self.sdk.response("claude-haiku-4-5")
        with mock.patch.dict("sys.modules", {"anthropic": self.sdk.module}):
            with self.assertRaisesRegex(RuntimeError, "model does not match"):
                llm.call_locked(
                    "parse-query",
                    [{"role": "user", "content": "{}"}],
                    max_tokens=1,
                    metering_context=context(),
                )
        self.assertEqual(
            self.sdk.create.call_args.kwargs["model"],
            "claude-haiku-4-5-20251001",
        )

    def test_response_model_content_and_usage_are_closed(self):
        invalid = (
            self.sdk.response("claude-sonnet-4-6"),
            self.sdk.response("claude-haiku-4-5"),
            self.sdk.response("claude-haiku-4-5-20251001", content=[]),
            self.sdk.response(
                "claude-haiku-4-5-20251001",
                content=[
                    SimpleNamespace(type="text", text="a"),
                    SimpleNamespace(type="text", text="b"),
                ],
            ),
            self.sdk.response(
                "claude-haiku-4-5-20251001",
                content=[SimpleNamespace(type="tool_use", text=None)],
            ),
            self.sdk.response(
                "claude-haiku-4-5-20251001",
                usage={
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "unknown": 0,
                },
            ),
        )
        for response in invalid:
            with self.subTest(response=response):
                self.sdk.create.return_value = response
                with mock.patch.dict("sys.modules", {"anthropic": self.sdk.module}):
                    with self.assertRaises(RuntimeError):
                        llm.call_locked(
                            "parse-query",
                            [{"role": "user", "content": "{}"}],
                            max_tokens=1,
                            metering_context=context(),
                        )


    def test_serialized_and_validated_wire_body_use_closed_task_controls(self):
        bodies = {}
        for task in llm.LOCKED_TASK_MODELS:
            with self.subTest(task=task):
                rendered = llm.serialize_locked_request(
                    task,
                    [{"role": "user", "content": "{}"}],
                    max_tokens=32,
                    system="closed",
                )
                body = __import__("json").loads(rendered)
                bodies[task] = body
                self.assertEqual(
                    {
                        key: body[key]
                        for key in llm.LOCKED_TASK_REQUEST_CONTROLS[task]
                    },
                    dict(llm.LOCKED_TASK_REQUEST_CONTROLS[task]),
                )
                self.assertEqual(
                    set(body),
                    {
                        "model",
                        "max_tokens",
                        "messages",
                        "system",
                        *llm.LOCKED_TASK_REQUEST_CONTROLS[task],
                    },
                )
                self.assertEqual(
                    llm.validate_locked_request_body(task, body),
                    rendered,
                )
        self.assertNotIn("inference_geo", bodies["parse-query"])
        self.assertEqual(bodies["distill"]["inference_geo"], "global")

    def test_task_specific_wire_control_drift_refuses(self):
        parse = __import__("json").loads(
            llm.serialize_locked_request(
                "parse-query",
                [{"role": "user", "content": "{}"}],
                max_tokens=32,
            )
        )
        distill = __import__("json").loads(
            llm.serialize_locked_request(
                "distill",
                [{"role": "user", "content": "{}"}],
                max_tokens=32,
            )
        )
        cases = (
            ("parse-query", parse, lambda value: value.pop("service_tier")),
            (
                "parse-query",
                parse,
                lambda value: value.__setitem__("service_tier", "priority"),
            ),
            (
                "parse-query",
                parse,
                lambda value: value.__setitem__("inference_geo", "global"),
            ),
            ("distill", distill, lambda value: value.pop("service_tier")),
            (
                "distill",
                distill,
                lambda value: value.__setitem__("service_tier", "priority"),
            ),
            ("distill", distill, lambda value: value.pop("inference_geo")),
            (
                "distill",
                distill,
                lambda value: value.__setitem__("inference_geo", "us"),
            ),
            (
                "distill",
                distill,
                lambda value: value.__setitem__("override", True),
            ),
        )
        for task, body, mutation in cases:
            candidate = dict(body)
            mutation(candidate)
            with self.subTest(task=task, candidate=candidate):
                with self.assertRaises(ValueError):
                    llm.validate_locked_request_body(task, candidate)

    def test_task_control_table_is_deeply_immutable(self):
        with self.assertRaises(TypeError):
            llm.LOCKED_TASK_REQUEST_CONTROLS["parse-query"] = {}
        with self.assertRaises(TypeError):
            llm.LOCKED_TASK_REQUEST_CONTROLS["parse-query"][
                "inference_geo"
            ] = "global"

    def test_locked_sdk_rejects_live_usage_pricing_metadata_drift(self):
        base = {
            "input_tokens": 1,
            "output_tokens": 1,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "service_tier": "standard",
            "inference_geo": "global",
        }
        invalid = []
        for field, value in (
            ("service_tier", "priority"),
            ("service_tier", "batch"),
            ("inference_geo", ""),
            (
                "inference_geo",
                "x" * (loop_metering.INFERENCE_GEO_MAX_LENGTH + 1),
            ),
            ("inference_geo", 7),
        ):
            candidate = dict(base)
            candidate[field] = value
            invalid.append(candidate)
        for missing in ("service_tier", "inference_geo"):
            candidate = dict(base)
            candidate.pop(missing)
            invalid.append(candidate)
        invalid.extend(
            (
                {**base, "output_tokens_details": {"thinking_tokens": 1}},
                {
                    **base,
                    "server_tool_use": {
                        "web_search_requests": 1,
                        "web_fetch_requests": 0,
                    },
                },
                {**base, "unknown": 0},
            )
        )
        for usage in invalid:
            with self.subTest(usage=usage):
                self.sdk.create.return_value = self.sdk.response(
                    llm.LOCKED_TASK_MODELS["parse-query"],
                    usage=usage,
                )
                with mock.patch.dict("sys.modules", {"anthropic": self.sdk.module}):
                    with self.assertRaisesRegex(RuntimeError, "usage is malformed"):
                        llm.call_locked(
                            "parse-query",
                            [{"role": "user", "content": "{}"}],
                            max_tokens=1,
                            metering_context=context(),
                        )


class LegacyCompatibilityTests(unittest.TestCase):
    def test_legacy_model_override_and_text_return_remain(self):
        sdk = FakeSdk()
        sdk.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="legacy")],
            stop_reason="end_turn",
        )
        with mock.patch.dict("sys.modules", {"anthropic": sdk.module}):
            with mock.patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "fixture"},
                clear=True,
            ):
                self.assertEqual(
                    llm.call(
                        "triage",
                        [{"role": "user", "content": "x"}],
                        model="legacy-model",
                        max_tokens=7,
                    ),
                    "legacy",
                )
        self.assertEqual(sdk.create.call_args.kwargs["model"], "legacy-model")


if __name__ == "__main__":
    unittest.main()
