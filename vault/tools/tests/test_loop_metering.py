"""Cut 4C exact Haiku/Sonnet pricing and Opus regression plants."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from lib import loop_metering as meter


def usage(**overrides):
    value = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    value.update(overrides)
    return value


def locked_usage(**overrides):
    value = usage(
        service_tier="standard",
        inference_geo="global",
    )
    value.update(overrides)
    return value


class ExactPriceTests(unittest.TestCase):
    def test_haiku_pricing_identity_is_fixed_snapshot_not_short_alias(self):
        self.assertEqual(
            meter.HAIKU_45_MODEL,
            "claude-haiku-4-5-20251001",
        )
        with self.assertRaises(meter.MeteringContractError):
            meter.pricing_for("claude-haiku-4-5")

    def test_one_million_standard_tokens_match_official_prices(self):
        vectors = (
            (meter.HAIKU_45_MODEL, "input_tokens", 1_000_000_000),
            (meter.HAIKU_45_MODEL, "output_tokens", 5_000_000_000),
            (meter.SONNET_46_MODEL, "input_tokens", 3_000_000_000),
            (meter.SONNET_46_MODEL, "output_tokens", 15_000_000_000),
        )
        for model, field, expected in vectors:
            with self.subTest(model=model, field=field):
                self.assertEqual(
                    meter.price_usage_nano_usd(
                        model,
                        usage(**{field: 1_000_000}),
                    ),
                    expected,
                )

    def test_cache_write_and_hit_prices_are_exact(self):
        vectors = (
            (meter.HAIKU_45_MODEL, 1_250_000_000, 2_000_000_000, 100_000_000),
            (meter.SONNET_46_MODEL, 3_750_000_000, 6_000_000_000, 300_000_000),
        )
        for model, five, hour, hit in vectors:
            with self.subTest(model=model):
                self.assertEqual(
                    meter.price_usage_nano_usd(
                        model,
                        usage(
                            cache_creation_input_tokens=1_000_000,
                            cache_creation={
                                "ephemeral_5m_input_tokens": 1_000_000,
                                "ephemeral_1h_input_tokens": 0,
                            },
                        ),
                    ),
                    five,
                )
                self.assertEqual(
                    meter.price_usage_nano_usd(
                        model,
                        usage(
                            cache_creation_input_tokens=1_000_000,
                            cache_creation={
                                "ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 1_000_000,
                            },
                        ),
                    ),
                    hour,
                )
                self.assertEqual(
                    meter.price_usage_nano_usd(
                        model,
                        usage(cache_read_input_tokens=1_000_000),
                    ),
                    hit,
                )

    def test_mixed_vector_is_integer_exact(self):
        self.assertEqual(
            meter.price_usage_nano_usd(
                meter.HAIKU_45_MODEL,
                usage(
                    input_tokens=3,
                    output_tokens=5,
                    cache_read_input_tokens=7,
                    cache_creation_input_tokens=24,
                    cache_creation={
                        "ephemeral_5m_input_tokens": 11,
                        "ephemeral_1h_input_tokens": 13,
                    },
                ),
            ),
            3 * 1_000 + 5 * 5_000 + 7 * 100 + 11 * 1_250 + 13 * 2_000,
        )

    def test_malformed_usage_matrix_refuses(self):
        invalid = (
            {},
            {"input_tokens": 1},
            usage(input_tokens=True),
            usage(output_tokens=-1),
            usage(input_tokens=1.5),
            usage(extra=1),
            usage(
                cache_creation_input_tokens=2,
                cache_creation={"ephemeral_5m_input_tokens": 1},
            ),
            usage(
                cache_creation_input_tokens=1,
                cache_creation={"ephemeral_5m_input_tokens": 1, "extra": 0},
            ),
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(meter.MeteringContractError):
                    meter.price_usage_nano_usd(meter.HAIKU_45_MODEL, value)


class LockedUsageTests(unittest.TestCase):
    def test_live_haiku_global_usage_prices_after_metadata_validation(self):
        value = locked_usage(
            input_tokens=3,
            output_tokens=2,
            cache_read_input_tokens=4,
            output_tokens_details={"thinking_tokens": 0},
            server_tool_use={
                "web_search_requests": 0,
                "web_fetch_requests": 0,
            },
        )
        self.assertEqual(
            meter.parse_locked_usage(value, task="parse-query"),
            {
                "input_tokens": 3,
                "output_tokens": 2,
                "cache_read_input_tokens": 4,
                "cache_creation_5m_input_tokens": 0,
                "cache_creation_1h_input_tokens": 0,
            },
        )
        self.assertEqual(
            meter.price_locked_usage_nano_usd(
                meter.HAIKU_45_MODEL,
                value,
                task="parse-query",
            ),
            3 * 1_000 + 2 * 5_000 + 4 * 100,
        )

    def test_optional_live_usage_objects_may_be_absent(self):
        self.assertEqual(
            meter.price_locked_usage_nano_usd(
                meter.HAIKU_45_MODEL,
                locked_usage(input_tokens=1, output_tokens=1),
            ),
            6_000,
        )

    def test_both_tasks_accept_and_preserve_any_bounded_geo_string(self):
        accepted = (
            "global",
            "us",
            "EU West / 東京?! #1",
            " ",
            "A" * meter.INFERENCE_GEO_MAX_LENGTH,
        )
        for task, model in (
            ("parse-query", meter.HAIKU_45_MODEL),
            ("distill", meter.SONNET_46_MODEL),
        ):
            for geo in accepted:
                with self.subTest(task=task, geo=geo):
                    self.assertIs(meter.validate_inference_geo(geo), geo)
                    self.assertEqual(
                        meter.parse_locked_usage(
                            locked_usage(inference_geo=geo),
                            task=task,
                            model=model,
                        )["input_tokens"],
                        0,
                    )

    def test_both_tasks_refuse_missing_empty_overlong_or_nonstring_geo(self):
        invalid = (
            "",
            "a" * (meter.INFERENCE_GEO_MAX_LENGTH + 1),
            None,
            1,
            True,
            [],
            {},
        )
        for task, model in (
            ("parse-query", meter.HAIKU_45_MODEL),
            ("distill", meter.SONNET_46_MODEL),
        ):
            for geo in invalid:
                with self.subTest(task=task, geo=geo):
                    with self.assertRaises(meter.MeteringContractError):
                        meter.parse_locked_usage(
                            locked_usage(inference_geo=geo),
                            task=task,
                            model=model,
                        )
            missing = locked_usage()
            missing.pop("inference_geo")
            with self.subTest(task=task, geo="missing"):
                with self.assertRaises(meter.MeteringContractError):
                    meter.parse_locked_usage(missing, task=task, model=model)

    def test_geo_aware_locked_prices_are_exact_across_all_five_categories(self):
        vector = locked_usage(
            input_tokens=3,
            output_tokens=5,
            cache_read_input_tokens=7,
            cache_creation_input_tokens=24,
            cache_creation={
                "ephemeral_5m_input_tokens": 11,
                "ephemeral_1h_input_tokens": 13,
            },
        )
        haiku_standard = (
            3 * 1_000 + 5 * 5_000 + 7 * 100 + 11 * 1_250 + 13 * 2_000
        )
        sonnet_standard = (
            3 * 3_000 + 5 * 15_000 + 7 * 300 + 11 * 3_750 + 13 * 6_000
        )
        sonnet_us = (
            3 * 3_300 + 5 * 16_500 + 7 * 330 + 11 * 4_125 + 13 * 6_600
        )
        for geo in ("global", "us", "EU West / 東京?! #1", " "):
            with self.subTest(model="haiku", geo=geo):
                value = {**vector, "inference_geo": geo}
                self.assertEqual(
                    meter.price_locked_usage_nano_usd(
                        meter.HAIKU_45_MODEL,
                        value,
                        task="parse-query",
                    ),
                    haiku_standard,
                )
        for geo in ("global", "eu-west_1", "US", " us", "us ", "東京 / ?!"):
            with self.subTest(model="sonnet", geo=geo):
                value = {**vector, "inference_geo": geo}
                self.assertEqual(
                    meter.price_locked_usage_nano_usd(
                        meter.SONNET_46_MODEL,
                        value,
                        task="distill",
                    ),
                    sonnet_standard,
                )
        self.assertEqual(sonnet_us, sonnet_standard * 11 // 10)
        self.assertEqual(
            meter.price_locked_usage_nano_usd(
                meter.SONNET_46_MODEL,
                {**vector, "inference_geo": "us"},
                task="distill",
            ),
            sonnet_us,
        )
        self.assertTrue(
            all(
                type(rate) is int
                for rate in meter.SONNET_US_PRICING_NANO_USD_PER_TOKEN.values()
            )
        )

    def test_locked_usage_identity_is_required_and_closed(self):
        with self.assertRaises(meter.MeteringContractError):
            meter.parse_locked_usage(locked_usage())
        for task, model in (
            ("parse-query", meter.SONNET_46_MODEL),
            ("distill", meter.HAIKU_45_MODEL),
            ("alias", meter.HAIKU_45_MODEL),
        ):
            with self.subTest(task=task, model=model):
                with self.assertRaises(meter.MeteringContractError):
                    meter.parse_locked_usage(
                        locked_usage(),
                        task=task,
                        model=model,
                    )

    def test_locked_response_control_table_is_exact_and_immutable(self):
        self.assertEqual(
            {
                task: {
                    "service_tier": controls["service_tier"],
                    "inference_geo_policy": controls["inference_geo_policy"],
                }
                for task, controls in meter.LOCKED_RESPONSE_USAGE_CONTROLS.items()
            },
            {
                "parse-query": {
                    "service_tier": "standard",
                    "inference_geo_policy": "bounded-any-recorded",
                },
                "distill": {
                    "service_tier": "standard",
                    "inference_geo_policy": "bounded-any-recorded",
                },
            },
        )
        with self.assertRaises(TypeError):
            meter.LOCKED_RESPONSE_USAGE_CONTROLS["parse-query"] = {}
        with self.assertRaises(TypeError):
            meter.LOCKED_RESPONSE_USAGE_CONTROLS["parse-query"][
                "service_tier"
            ] = "priority"

    def test_locked_usage_tier_and_closed_schema_matrix_refuses(self):
        invalid = (
            locked_usage(service_tier="priority"),
            locked_usage(service_tier="batch"),
            {key: value for key, value in locked_usage().items() if key != "service_tier"},
            locked_usage(output_tokens_details={"thinking_tokens": 1}),
            locked_usage(output_tokens_details={"thinking_tokens": False}),
            locked_usage(output_tokens_details={"thinking_tokens": 0, "extra": 0}),
            locked_usage(output_tokens_details={}),
            locked_usage(output_tokens_details=[]),
            locked_usage(
                server_tool_use={
                    "web_search_requests": 1,
                    "web_fetch_requests": 0,
                }
            ),
            locked_usage(
                server_tool_use={
                    "web_search_requests": 0,
                    "web_fetch_requests": 1,
                }
            ),
            locked_usage(server_tool_use={"web_search_requests": 0}),
            locked_usage(
                server_tool_use={
                    "web_search_requests": 0,
                    "web_fetch_requests": 0,
                    "extra": 0,
                }
            ),
            locked_usage(server_tool_use=None),
            locked_usage(extra=0),
            locked_usage(input_tokens=True),
            locked_usage(output_tokens=-1),
            locked_usage(cache_read_input_tokens=0.5),
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(meter.MeteringContractError):
                    meter.price_locked_usage_nano_usd(
                        meter.HAIKU_45_MODEL,
                        value,
                        task="parse-query",
                    )
        for task, model in (
            ("parse-query", meter.HAIKU_45_MODEL),
            ("distill", meter.SONNET_46_MODEL),
        ):
            for tier in ("priority", "batch", "", None):
                with self.subTest(task=task, tier=tier):
                    with self.assertRaises(meter.MeteringContractError):
                        meter.parse_locked_usage(
                            locked_usage(service_tier=tier),
                            task=task,
                            model=model,
                        )

    def test_generic_parser_is_not_widened_to_price_tier_or_geo_metadata(self):
        with self.assertRaises(meter.MeteringContractError):
            meter.price_usage_nano_usd(
                meter.HAIKU_45_MODEL,
                locked_usage(),
            )


class WorstCaseTests(unittest.TestCase):
    def test_cache_modes_select_exact_input_rate(self):
        request_bytes = 10
        max_tokens = 2
        input_bound = request_bytes + meter.REQUEST_OVERHEAD_BYTES
        expected_rates = {"none": 1_000, "5m": 1_250, "1h": 2_000, "read": 100}
        for mode, input_rate in expected_rates.items():
            with self.subTest(mode=mode):
                self.assertEqual(
                    meter.worst_case_request_cost_nano_usd(
                        meter.HAIKU_45_MODEL,
                        request_bytes=request_bytes,
                        max_tokens=max_tokens,
                        cache_mode=mode,
                    ),
                    input_bound * input_rate + max_tokens * 5_000,
                )

    def test_sonnet_preflight_uses_exact_us_adjusted_rates(self):
        request_bytes = 10
        max_tokens = 2
        input_bound = request_bytes + meter.REQUEST_OVERHEAD_BYTES
        expected_rates = {
            "none": 3_300,
            "5m": 4_125,
            "1h": 6_600,
            "read": 330,
        }
        for mode, input_rate in expected_rates.items():
            with self.subTest(mode=mode):
                self.assertEqual(
                    meter.worst_case_request_cost_nano_usd(
                        meter.SONNET_46_MODEL,
                        request_bytes=request_bytes,
                        max_tokens=max_tokens,
                        cache_mode=mode,
                    ),
                    input_bound * input_rate + max_tokens * 16_500,
                )

    def test_invalid_request_domains_refuse(self):
        for field, value in (
            ("request_bytes", True),
            ("request_bytes", -1),
            ("max_tokens", 0),
            ("max_tokens", 1.5),
        ):
            kwargs = {"request_bytes": 1, "max_tokens": 1, field: value}
            with self.subTest(field=field, value=value):
                with self.assertRaises(meter.MeteringContractError):
                    meter.worst_case_request_cost_nano_usd(
                        meter.SONNET_46_MODEL,
                        cache_mode="none",
                        **kwargs,
                    )
        with self.assertRaises(meter.MeteringContractError):
            meter.worst_case_request_cost_nano_usd(
                meter.HAIKU_45_MODEL,
                request_bytes=1,
                max_tokens=1,
                cache_mode="alias",
            )


class OpusRegressionTests(unittest.TestCase):
    def test_opus_usage_and_legacy_float_result_are_unchanged(self):
        vector = usage(
            input_tokens=100,
            output_tokens=20,
            cache_read_input_tokens=10,
            cache_creation_input_tokens=10,
            cache_creation={
                "ephemeral_5m_input_tokens": 4,
                "ephemeral_1h_input_tokens": 6,
            },
        )
        expected_nano = 100 * 5_000 + 20 * 25_000 + 10 * 500 + 4 * 6_250 + 6 * 10_000
        self.assertEqual(
            meter.price_usage_nano_usd(meter.OPUS_48_MODEL, vector),
            expected_nano,
        )
        self.assertEqual(
            meter.price_usage(meter.OPUS_48_MODEL, vector),
            expected_nano / 1_000_000_000,
        )

    def test_legacy_worst_case_still_uses_highest_input_rate(self):
        expected = (
            (1 + meter.REQUEST_OVERHEAD_BYTES) * 10_000 + 2 * 25_000
        ) / 1_000_000_000
        self.assertEqual(
            meter.worst_case_request_cost(
                meter.OPUS_48_MODEL,
                request_bytes=1,
                max_tokens=2,
            ),
            expected,
        )


if __name__ == "__main__":
    unittest.main()
