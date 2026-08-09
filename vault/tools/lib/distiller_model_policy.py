"""Strict resolver for the one canonical Distiller metered-model policy."""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

import yaml

from lib import daily_spend, llm, loop_metering


POLICY_UID = "0c938a95"
POLICY_VERSION = "1.9.0"
POLICY_RUNNER = "distiller-model-edge"
POLICY_RELATIVE_PATH = Path("vault/files/0c938a95.md")
POLICY_INDEX_RELATIVE_PATH = Path("vault/00-index.jsonl")
OS_GEO_EVENT_RELATIVE_PATH = Path(
    "vault/events/streams/6147bbbaaf258b3c.jsonl"
)
OS_GEO_SOURCE_EVENT = "evt_6147bbbaaf258b3c_00000017"
OS_GEO_RULED_BY = "7b921d17"
OS_GEO_RULING_SCOPE = "os-only-any-bounded-response-geo"
OS_GEO_RULING_MESSAGE = (
    "MIKE RULED (2026-07-24, in-session with me, walked with numbered options "
    "incl. your allowlist lean): OPTION 3 - ANY response geo is acceptable for "
    "OS-SEGMENT inference; tighten per-segment later when team/private enter. "
    "Binding details as walked: (1) OS-segment acceptance does NOT fail on "
    "reported inference_geo - any value accepted AND RECORDED; (2) request-side "
    "controls stay as-built (Sonnet still REQUESTS global - asking costs nothing; "
    "parse stays tier-only); (3) team/private remain blocked from model egress "
    "entirely (unchanged, ask); (4) arbitrary-geo acceptance is OS-ONLY - not a "
    "precedent for other segments, revisit with real teeth at team/private "
    "onboarding. RECOMMENDATION riding along: bind observed geo into gateway "
    "receipts + scorecard going forward - closes the evidence gap you flagged "
    "(rejected value not preserved) and gives the future per-segment ruling real "
    "routing data to stand on. Ready to execute attempt 5 on your handoff per the "
    "established pattern. - Metis G93"
)
RUNNER_WATCHDOG_UID = "1edbee15"
SPEND_APPROVER_UID = "7b921d17"
SPEND_APPROVAL = "I approve the spend limits. Go for it."
CANARY_APPROVER_UID = "7b921d17"
CANARY_APPROVED_AT = "2026-07-25"
CANARY_APPROVAL_SCOPE = (
    "single-os-only-canary-attempt-7-exact-json-fence-"
    "max-reserved-0.26-no-production"
)
CANARY_APPROVAL = "I approve"
CANARY_ATTEMPT = 7
PRIOR_1_RUN_UID = "4412b12b"
PRIOR_1_CONTRACT_SHA256 = (
    "ecee6ff5807dc327c9a66085c76341dd20a39933a7f55454c02a3337eba82c46"
)
PRIOR_1_POLICY_VERSION = "1.1.0"
PRIOR_1_RESERVATION_ID = "eb129fcf"
PRIOR_1_RETAINED_NANO_USD = 5_269_000
PRIOR_1_SCORECARD_SHA256 = (
    "a60ac4a34c6339571cd1a32a3c30d0a2a0f779b3073c0ac4fdcab4f1111b84bf"
)
PRIOR_1_LEDGER_DAY = "2026-07-24"
PRIOR_1_LEDGER_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/2026-07-24.json"
)
PRIOR_1_CLAIM_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/"
    "distiller-canary-0c938a95-1.1.0-claim.json"
)
PRIOR_1_RUN_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-20260724/run.jsonl"
)
PRIOR_1_RUN_DIR_RELATIVE_PATH = PRIOR_1_RUN_RELATIVE_PATH.parent
PRIOR_1_SCORECARD_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-20260724/"
    "distiller-metered-canary-scorecard.json"
)
PRIOR_2_RUN_UID = "78f771c0"
PRIOR_2_CONTRACT_SHA256 = (
    "3dac5d15ff94b3821fa29123254c3f7339b0327a19c5a525e8301c806cc9115c"
)
PRIOR_2_POLICY_VERSION = "1.2.0"
PRIOR_2_RESERVATION_ID = "41b9a003"
PRIOR_2_RETAINED_NANO_USD = 5_281_000
PRIOR_2_SCORECARD_SHA256 = (
    "888a9242f03866323c85f3eb1ef8579795b110d67b97cb702eb91ae722fa12fd"
)
PRIOR_2_LEDGER_DAY = "2026-07-24"
PRIOR_2_LEDGER_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/2026-07-24@1.2.0.json"
)
PRIOR_2_CLAIM_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/"
    "distiller-canary-0c938a95-1.2.0-claim.json"
)
PRIOR_2_RUN_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-attempt2-20260724/run.jsonl"
)
PRIOR_2_RUN_DIR_RELATIVE_PATH = PRIOR_2_RUN_RELATIVE_PATH.parent
PRIOR_2_SCORECARD_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-attempt2-20260724/"
    "distiller-metered-canary-scorecard.json"
)
PRIOR_3_RUN_UID = "114ab671"
PRIOR_3_CONTRACT_SHA256 = (
    "64e1ee0360700705586e0ffdf92f370c4960cbe8cb78d1819d1026be8ec82d58"
)
PRIOR_3_POLICY_VERSION = "1.3.0"
PRIOR_3_RESERVATION_ID = "e24e507a"
PRIOR_3_RETAINED_NANO_USD = 5_337_000
PRIOR_3_SCORECARD_SHA256 = (
    "041140500ceb0eb34261d13643e8f3c2589e9e43d3772b2b5dfbac6fde29f70b"
)
PRIOR_3_LEDGER_DAY = "2026-07-24"
PRIOR_3_LEDGER_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/2026-07-24@1.3.0.json"
)
PRIOR_3_CLAIM_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/"
    "distiller-canary-0c938a95-1.3.0-claim.json"
)
PRIOR_3_RUN_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-attempt3-20260724/run.jsonl"
)
PRIOR_3_RUN_DIR_RELATIVE_PATH = PRIOR_3_RUN_RELATIVE_PATH.parent
PRIOR_3_SCORECARD_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-attempt3-20260724/"
    "distiller-metered-canary-scorecard.json"
)
PRIOR_4_RUN_UID = "31ec76ae"
PRIOR_4_CONTRACT_SHA256 = (
    "243dce295fc85454f3057cc46e1dac672f4b061f0fc3428fa9e85021690c7566"
)
PRIOR_4_POLICY_VERSION = "1.4.0"
PRIOR_4_RESERVATION_ID = "f6cd5bb6"
PRIOR_4_RETAINED_NANO_USD = 5_312_000
PRIOR_4_SCORECARD_SHA256 = (
    "b506e2f804a107e047b5b1508614edb08c02b762c56f54e1cef365900bbf5b7c"
)
PRIOR_4_LEDGER_DAY = "2026-07-24"
PRIOR_4_LEDGER_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/2026-07-24@1.4.0.json"
)
PRIOR_4_CLAIM_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/"
    "distiller-canary-0c938a95-1.4.0-claim.json"
)
PRIOR_4_RUN_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-attempt4-20260724/run.jsonl"
)
PRIOR_4_RUN_DIR_RELATIVE_PATH = PRIOR_4_RUN_RELATIVE_PATH.parent
PRIOR_4_SCORECARD_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-attempt4-20260724/"
    "distiller-metered-canary-scorecard.json"
)
PRIOR_5_POLICY_VERSION = "1.5.0"
PRIOR_5_RUN_UID = "a3a7ed57"
PRIOR_5_CONTRACT_SHA256 = (
    "2cb7e885841591816743d1dbda0308ebc08a01d80adfd1e683c1706260d8aeb0"
)
PRIOR_5_LEDGER_DAY = "2026-07-24"
PRIOR_5_LEDGER_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/2026-07-24@1.5.0.json"
)
PRIOR_5_CLAIM_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/"
    "distiller-canary-0c938a95-1.5.0-claim.json"
)
PRIOR_5_RUN_DIR_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-attempt5-v15-orphan-20260724"
)
PRIOR_5_RUN_RELATIVE_PATH = PRIOR_5_RUN_DIR_RELATIVE_PATH / "run.jsonl"
PRIOR_5_PROVENANCE_RELATIVE_PATH = (
    PRIOR_5_RUN_DIR_RELATIVE_PATH / "orphan-evidence-provenance.json"
)
PRIOR_6_POLICY_VERSION = "1.6.0"
PRIOR_6_RUN_UID = "13f98a4e"
PRIOR_6_CONTRACT_SHA256 = (
    "cd51ab1e56c925c56ed618bea09e0b904f7089f6eef20d4b35ade9e62cf3515f"
)
PRIOR_6_LEDGER_DAY = "2026-07-24"
PRIOR_6_LEDGER_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/2026-07-24@1.6.0.json"
)
PRIOR_6_CLAIM_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/"
    "distiller-canary-0c938a95-1.6.0-claim.json"
)
PRIOR_6_CLAIM_LOCK_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/"
    "distiller-canary-0c938a95-1.6.0-claim.lock"
)
PRIOR_6_RUN_DIR_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-attempt5-20260724"
)
PRIOR_6_RUN_RELATIVE_PATH = PRIOR_6_RUN_DIR_RELATIVE_PATH / "run.jsonl"
PRIOR_EXECUTION_POLICY_VERSION = "1.7.0"
PRIOR_EXECUTION_RUN_UID = "a02843bc"
PRIOR_EXECUTION_RESERVATION_ID = "9448c1b0"
PRIOR_EXECUTION_RESERVED_NANO_USD = 5_312_000
PRIOR_EXECUTION_ACTUAL_NANO_USD = 218_000
PRIOR_EXECUTION_CONTRACT_SHA256 = (
    "04cba6ec0f4236ccf9607860b34211cef0e71b7d287f8c474f3656513bae323e"
)
PRIOR_EXECUTION_SCORECARD_SHA256 = (
    "7db939c1e4a1158e802b2aae0102758ed66161daee2c9ad348ee4d616aed1d93"
)
PRIOR_EXECUTION_LEDGER_RECEIPT_SHA256 = (
    "8b482b901f15debca578ed11e1a1cdda5789da0da883dbe4dff5d0beccc9dd84"
)
PRIOR_EXECUTION_RESPONSE_SHA256 = (
    "6c5e90f0ebd5cb5b601e8c17228e9153a2626b20460fbed2dca3c55af3d42c32"
)
PRIOR_EXECUTION_RESPONSE_TEXT = '```json\n{"uids":["0c938a95"]}\n```'
PRIOR_EXECUTION_SERVICE_TIER = "standard"
PRIOR_EXECUTION_INFERENCE_GEO = "not_available"
PRIOR_EXECUTION_PREPARATION_DAY = "2026-07-25"
PRIOR_EXECUTION_DAY = "2026-07-25"
PRIOR_EXECUTION_RUN_DIR_RELATIVE_PATH = Path(
    "vault/loop-runs/distiller-canary-attempt6-20260725"
)
PRIOR_EXECUTION_RUN_RELATIVE_PATH = (
    PRIOR_EXECUTION_RUN_DIR_RELATIVE_PATH / "run.jsonl"
)
PRIOR_EXECUTION_CLAIM_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/"
    "distiller-canary-0c938a95-1.7.0-claim.json"
)
PRIOR_EXECUTION_CLAIM_LOCK_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/"
    "distiller-canary-0c938a95-1.7.0-claim.lock"
)
PRIOR_EXECUTION_LEDGER_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/2026-07-25@1.7.0.json"
)
PRIOR_EXECUTION_DAY_LOCK_RELATIVE_PATH = Path(
    "vault/loop-runs/.model-spend/2026-07-25.lock"
)
# Compatibility aliases for tests/tools that historically named attempt 1 "prior".
PRIOR_RUN_UID = PRIOR_1_RUN_UID
PRIOR_CONTRACT_SHA256 = PRIOR_1_CONTRACT_SHA256
PRIOR_POLICY_VERSION = PRIOR_1_POLICY_VERSION
PRIOR_RESERVATION_ID = PRIOR_1_RESERVATION_ID
PRIOR_RETAINED_NANO_USD = PRIOR_1_RETAINED_NANO_USD
PRIOR_SCORECARD_SHA256 = PRIOR_1_SCORECARD_SHA256
PRIOR_LEDGER_DAY = PRIOR_1_LEDGER_DAY
PRIOR_LEDGER_RELATIVE_PATH = PRIOR_1_LEDGER_RELATIVE_PATH
PRIOR_CLAIM_RELATIVE_PATH = PRIOR_1_CLAIM_RELATIVE_PATH
PRIOR_RUN_RELATIVE_PATH = PRIOR_1_RUN_RELATIVE_PATH
PRIOR_SCORECARD_RELATIVE_PATH = PRIOR_1_SCORECARD_RELATIVE_PATH
PRIOR_ATTEMPT_RUN_UIDS = (
    PRIOR_1_RUN_UID,
    PRIOR_2_RUN_UID,
    PRIOR_3_RUN_UID,
    PRIOR_4_RUN_UID,
)
PRIOR_PREPARATION_RUN_UIDS = (PRIOR_5_RUN_UID, PRIOR_6_RUN_UID)
PRIOR_EXECUTION_RUN_UIDS = (PRIOR_EXECUTION_RUN_UID,)
PRIOR_RUN_UIDS = (
    PRIOR_ATTEMPT_RUN_UIDS
    + PRIOR_PREPARATION_RUN_UIDS
    + PRIOR_EXECUTION_RUN_UIDS
)
PRIOR_RETAINED_TOTAL_NANO_USD = (
    PRIOR_1_RETAINED_NANO_USD
    + PRIOR_2_RETAINED_NANO_USD
    + PRIOR_3_RETAINED_NANO_USD
    + PRIOR_4_RETAINED_NANO_USD
)
CANARY_SEGMENT = "os"
CANARY_MAX_CALLS = 2
CANARY_MAX_RESERVED_NANO_USD = 260_000_000
CANARY_CLAIM_NAME = "distiller-canary-0c938a95-1.8.0-claim.json"
CANARY_CLAIM_LOCK_NAME = "distiller-canary-0c938a95-1.8.0-claim.lock"
PRICING_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
DAILY_CEILING_NANO_USD = 5_000_000_000
MONTHLY_CEILING_NANO_USD = 50_000_000_000
SEGMENT_CLASSES = ("os", "private", "team")
MODEL_ROUTES = {
    "parse-query": ("claude-haiku-4-5-20251001", 10_000_000),
    "distill": ("claude-sonnet-4-6", 250_000_000),
}
PRICING_NANO_USD_PER_TOKEN = {
    "claude-haiku-4-5-20251001": {
        "input_tokens": 1_000,
        "output_tokens": 5_000,
        "cache_creation_5m_input_tokens": 1_250,
        "cache_creation_1h_input_tokens": 2_000,
        "cache_read_input_tokens": 100,
    },
    "claude-sonnet-4-6": {
        "input_tokens": 3_000,
        "output_tokens": 15_000,
        "cache_creation_5m_input_tokens": 3_750,
        "cache_creation_1h_input_tokens": 6_000,
        "cache_read_input_tokens": 300,
    },
}
_UID_RE = re.compile(r"^[0-9a-f]{8}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_FIELDS = frozenset(
    {
        "uid",
        "type",
        "title",
        "description",
        "name",
        "version",
        "author",
        "owner",
        "status",
        "state",
        "created",
        "created_by",
        "modified",
        "modified_by",
        "schema_version",
        "capsule_version",
        "extraction_scope",
        "governed_by",
        "subsystem_hub",
        "realizes_dev_spec",
        "runner",
        "execution_mode",
        "consent_mode",
        "model_routes",
        "daily_spend",
        "monthly_spend",
        "pricing_usd_per_mtok",
        "pricing_source",
        "pricing_verified_at",
        "request_controls",
        "response_usage_controls",
        "os_geo_ruling",
        "segment_egress",
        "egress_approved",
        "egress_approved_by",
        "canary_egress",
        "spend_limits_locked_by",
        "spend_limits_locked_at",
        "spend_limits_approval_scope",
        "spend_limits_approval_verbatim",
        "goal",
        "trigger",
        "policy",
        "tools",
        "verifier",
        "brakes",
        "consequence",
        "metered_canary",
    }
)


class PolicyError(RuntimeError):
    """The canonical policy cannot safely authorize a model attempt."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise PolicyError(f"duplicate YAML key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class PriorAttemptEvidence:
    attempt: int
    policy_version: str
    run_uid: str
    reservation_id: str
    retained_nano_usd: int
    contract_sha256: str
    scorecard_sha256: str
    ledger_day: str
    ledger_path: Path
    claim_path: Path
    run_path: Path
    expected_model: str
    approval_scope: str
    gateway_spend: tuple[tuple[str, object], ...]
    scorecard_error: str
    receipt_error: str
    evidence_hashes: tuple[tuple[Path, str], ...]

    def policy_record(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "policy_version": self.policy_version,
            "run_uid": self.run_uid,
            "reservation_id": self.reservation_id,
            "retained_nano_usd": self.retained_nano_usd,
            "contract_sha256": self.contract_sha256,
            "scorecard_sha256": self.scorecard_sha256,
        }


PRIOR_ATTEMPT_EVIDENCE = (
    PriorAttemptEvidence(
        attempt=1,
        policy_version=PRIOR_1_POLICY_VERSION,
        run_uid=PRIOR_1_RUN_UID,
        reservation_id=PRIOR_1_RESERVATION_ID,
        retained_nano_usd=PRIOR_1_RETAINED_NANO_USD,
        contract_sha256=PRIOR_1_CONTRACT_SHA256,
        scorecard_sha256=PRIOR_1_SCORECARD_SHA256,
        ledger_day=PRIOR_1_LEDGER_DAY,
        ledger_path=PRIOR_1_LEDGER_RELATIVE_PATH,
        claim_path=PRIOR_1_CLAIM_RELATIVE_PATH,
        run_path=PRIOR_1_RUN_RELATIVE_PATH,
        expected_model="claude-haiku-4-5",
        approval_scope="single-os-only-canary-max-reserved-0.26-no-production",
        gateway_spend=(
            ("metering_error", "response model does not match requested model"),
        ),
        scorecard_error="gateway_spend.json must contain only spent_usd",
        receipt_error=(
            "PROVIDER_FAILED: Anthropic gateway error: "
            "Provider usage could not be safely metered."
        ),
        evidence_hashes=(
            (
                PRIOR_1_LEDGER_RELATIVE_PATH,
                "25ce6361b950b9243db45e8c4fb7f4d9ad78dbac2270bf38a7f3794ccb32d2d2",
            ),
            (
                Path("vault/loop-runs/.model-spend/2026-07-24.lock"),
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                PRIOR_1_CLAIM_RELATIVE_PATH,
                "086069800b8262cde674b32740d308ba4fe14033639444db1fd8cb4b69eb0b58",
            ),
            (
                Path(
                    "vault/loop-runs/.model-spend/"
                    "distiller-canary-0c938a95-1.1.0-claim.lock"
                ),
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                PRIOR_1_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-gateway-receipts.json",
                "0279a5c01c5928fcfa0ebf4e006bd8aeca9d2b0a10a6b0880aedc881d81ceca4",
            ),
            (
                PRIOR_1_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-preparation.json",
                "b905a8a09beb541c541b1fb3ae8ef8f9c717e00979014dfeb5aa3c65a7287b40",
            ),
            (
                PRIOR_1_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-readiness.json",
                "a693fb85c4e0a7e73ebd144daa0be0fc4b644495c51986b252f2c72f5997725a",
            ),
            (
                PRIOR_1_SCORECARD_RELATIVE_PATH,
                PRIOR_1_SCORECARD_SHA256,
            ),
            (
                PRIOR_1_RUN_DIR_RELATIVE_PATH / "gateway_spend.json",
                "6248495b9a1f0157aa434a26165735306e7c481c672adc53c2b05ba8f726a5c6",
            ),
            (
                PRIOR_1_RUN_RELATIVE_PATH,
                "5f9ea33b4e1dde237b82a8c5d485e361bde3baefe90b360e13bd98508f5ce39f",
            ),
        ),
    ),
    PriorAttemptEvidence(
        attempt=2,
        policy_version=PRIOR_2_POLICY_VERSION,
        run_uid=PRIOR_2_RUN_UID,
        reservation_id=PRIOR_2_RESERVATION_ID,
        retained_nano_usd=PRIOR_2_RETAINED_NANO_USD,
        contract_sha256=PRIOR_2_CONTRACT_SHA256,
        scorecard_sha256=PRIOR_2_SCORECARD_SHA256,
        ledger_day=PRIOR_2_LEDGER_DAY,
        ledger_path=PRIOR_2_LEDGER_RELATIVE_PATH,
        claim_path=PRIOR_2_CLAIM_RELATIVE_PATH,
        run_path=PRIOR_2_RUN_RELATIVE_PATH,
        expected_model="claude-haiku-4-5-20251001",
        approval_scope=(
            "single-os-only-canary-attempt-2-max-reserved-0.26-no-production"
        ),
        gateway_spend=(
            (
                "metering_error",
                "usage has unknown fields: ['inference_geo', 'service_tier']",
            ),
        ),
        scorecard_error="gateway_spend.json must contain only spent_usd",
        receipt_error=(
            "PROVIDER_FAILED: Anthropic gateway error: "
            "Provider usage could not be safely metered."
        ),
        evidence_hashes=(
            (
                PRIOR_2_LEDGER_RELATIVE_PATH,
                "0ae0e035f6af7c2a074860955a7c04b8273088eadb564d9adedc4640acfa7639",
            ),
            (
                Path("vault/loop-runs/.model-spend/2026-07-24.lock"),
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                PRIOR_2_CLAIM_RELATIVE_PATH,
                "96d2c5951585386611bf27210ec06b015e3f4108fc5eccbfb40bb6df9f91cacf",
            ),
            (
                Path(
                    "vault/loop-runs/.model-spend/"
                    "distiller-canary-0c938a95-1.2.0-claim.lock"
                ),
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                PRIOR_2_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-gateway-receipts.json",
                "dfe61703249497992ba3e0ca6dbe547b6c3fb16dc586a5e2150256c12914a28f",
            ),
            (
                PRIOR_2_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-preparation.json",
                "45583704505bfb1b8f990104979bb3d83c1c44b6a397da73b110feb38d8e3176",
            ),
            (
                PRIOR_2_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-readiness.json",
                "a38e3fdd21e4677e8f039d806f0d59b22818b3ea220977e6ef94cefcf9a6b0e8",
            ),
            (
                PRIOR_2_SCORECARD_RELATIVE_PATH,
                PRIOR_2_SCORECARD_SHA256,
            ),
            (
                PRIOR_2_RUN_DIR_RELATIVE_PATH / "gateway_spend.json",
                "30ea0bc2545f4636b620654738f8d46011e5a60fd71bfb8e5b77d7126c5eb06c",
            ),
            (
                PRIOR_2_RUN_RELATIVE_PATH,
                "35db0314f447f4c05508952e3271d9c97759abf63bc65f30b8a5119f835142d0",
            ),
        ),
    ),
    PriorAttemptEvidence(
        attempt=3,
        policy_version=PRIOR_3_POLICY_VERSION,
        run_uid=PRIOR_3_RUN_UID,
        reservation_id=PRIOR_3_RESERVATION_ID,
        retained_nano_usd=PRIOR_3_RETAINED_NANO_USD,
        contract_sha256=PRIOR_3_CONTRACT_SHA256,
        scorecard_sha256=PRIOR_3_SCORECARD_SHA256,
        ledger_day=PRIOR_3_LEDGER_DAY,
        ledger_path=PRIOR_3_LEDGER_RELATIVE_PATH,
        claim_path=PRIOR_3_CLAIM_RELATIVE_PATH,
        run_path=PRIOR_3_RUN_RELATIVE_PATH,
        expected_model="claude-haiku-4-5-20251001",
        approval_scope=(
            "single-os-only-canary-attempt-3-standard-global-"
            "max-reserved-0.26-no-production"
        ),
        gateway_spend=(("spent_usd", 0.0),),
        scorecard_error=(
            "PROVIDER_FAILED: Anthropic gateway error: Error code: 400 - "
            "{'type': 'error', 'error': {'type': 'invalid_request_error', "
            "'message': \"'claude-haiku-4-5-20251001' does not support "
            "inference_geo.\"}, "
            "'request_id': 'req_011CdMJE2UeTiFMzJYgzewEK'}"
        ),
        receipt_error=(
            "PROVIDER_FAILED: Anthropic gateway error: Error code: 400 - "
            "{'type': 'error', 'error': {'type': 'invalid_request_error', "
            "'message': \"'claude-haiku-4-5-20251001' does not support "
            "inference_geo.\"}, "
            "'request_id': 'req_011CdMJE2UeTiFMzJYgzewEK'}"
        ),
        evidence_hashes=(
            (
                PRIOR_3_LEDGER_RELATIVE_PATH,
                "015900b164b6dfd328a8d3410c31e2e2841ff9a451ccc018c7044023117a1d8e",
            ),
            (
                Path("vault/loop-runs/.model-spend/2026-07-24.lock"),
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                PRIOR_3_CLAIM_RELATIVE_PATH,
                "e7c92ddeb300b83ee242b757b074ff2edc948058da32e88e787e54291023cd21",
            ),
            (
                Path(
                    "vault/loop-runs/.model-spend/"
                    "distiller-canary-0c938a95-1.3.0-claim.lock"
                ),
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                PRIOR_3_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-gateway-receipts.json",
                "1a84477db2de54c5d69e4bd93cad6b349c6d9af0892e8f72b6eabb70eadb1299",
            ),
            (
                PRIOR_3_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-preparation.json",
                "0ae5018b5f6784049fe62e9984728b86e683fdbeb177226cb20f41492455c840",
            ),
            (
                PRIOR_3_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-readiness.json",
                "bede639ddb5a2d3e61e2e8ab9ddc7e1957da3682a1dbea6bc30255dd0c21b191",
            ),
            (
                PRIOR_3_SCORECARD_RELATIVE_PATH,
                PRIOR_3_SCORECARD_SHA256,
            ),
            (
                PRIOR_3_RUN_DIR_RELATIVE_PATH / "gateway_spend.json",
                "996cb8eca90b6f85b35d69f223b20f195814796a16c2439f0e4d5483cfd5c8e3",
            ),
            (
                PRIOR_3_RUN_RELATIVE_PATH,
                "e92e1868ea6f8ee75d65fbe72fd89561094c6cc0c8f07230124b918e6837b908",
            ),
        ),
    ),
    PriorAttemptEvidence(
        attempt=4,
        policy_version=PRIOR_4_POLICY_VERSION,
        run_uid=PRIOR_4_RUN_UID,
        reservation_id=PRIOR_4_RESERVATION_ID,
        retained_nano_usd=PRIOR_4_RETAINED_NANO_USD,
        contract_sha256=PRIOR_4_CONTRACT_SHA256,
        scorecard_sha256=PRIOR_4_SCORECARD_SHA256,
        ledger_day=PRIOR_4_LEDGER_DAY,
        ledger_path=PRIOR_4_LEDGER_RELATIVE_PATH,
        claim_path=PRIOR_4_CLAIM_RELATIVE_PATH,
        run_path=PRIOR_4_RUN_RELATIVE_PATH,
        expected_model="claude-haiku-4-5-20251001",
        approval_scope=(
            "single-os-only-canary-attempt-4-model-capabilities-"
            "max-reserved-0.26-no-production"
        ),
        gateway_spend=(
            (
                "metering_error",
                "usage.inference_geo must equal 'global'",
            ),
        ),
        scorecard_error="gateway_spend.json must contain only spent_usd",
        receipt_error=(
            "PROVIDER_FAILED: Anthropic gateway error: "
            "Provider usage could not be safely metered."
        ),
        evidence_hashes=(
            (
                PRIOR_4_LEDGER_RELATIVE_PATH,
                "50fbf461f674c8b1eebad8491c40cd1b6d249bb81ca4a1b9ef8f81db3ce08b8c",
            ),
            (
                Path("vault/loop-runs/.model-spend/2026-07-24.lock"),
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                PRIOR_4_CLAIM_RELATIVE_PATH,
                "bd59879ff381b46cd332ee441d6a3437b698712d42cbbcfc70d222d6554363d4",
            ),
            (
                Path(
                    "vault/loop-runs/.model-spend/"
                    "distiller-canary-0c938a95-1.4.0-claim.lock"
                ),
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                PRIOR_4_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-gateway-receipts.json",
                "6d378fc61bfe13652f39617e982863cef36dedb4f81d96241bf3e4c56d994235",
            ),
            (
                PRIOR_4_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-preparation.json",
                "170b04879a3cb1896c655463e378a211bde3bb3a875125ad8a2bc815c0db93cc",
            ),
            (
                PRIOR_4_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-readiness.json",
                "8c89a2759ca648b691bda7aacc52c0192adc49a2025500dfee5a6a13fc69da42",
            ),
            (
                PRIOR_4_SCORECARD_RELATIVE_PATH,
                PRIOR_4_SCORECARD_SHA256,
            ),
            (
                PRIOR_4_RUN_DIR_RELATIVE_PATH / "gateway_spend.json",
                "6aa40222d985dce81873be1949fbe771f7473929bd7a72d4d02fba0286decb24",
            ),
            (
                PRIOR_4_RUN_RELATIVE_PATH,
                "bc54a60b1485211d5d93d6c5a062fd6e43da840b6c95bf9f6271fa7eedd12af9",
            ),
        ),
    ),
)


@dataclass(frozen=True)
class PriorPreparationEvidence:
    kind: str
    status: str
    policy_version: str
    run_uid: str
    contract_sha256: str
    preparation_day: str
    ledger_path: Path
    claim_path: Path
    run_path: Path
    claim_run_dir_name: str
    approval_scope: str
    absent_artifacts: tuple[str, ...]
    evidence_hashes: tuple[tuple[str, Path, str], ...]
    provenance_path: Path | None = None

    def policy_record(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "status": self.status,
            "policy_version": self.policy_version,
            "run_uid": self.run_uid,
            "contract_sha256": self.contract_sha256,
            "preparation_day": self.preparation_day,
            "zero_reservations": True,
            "zero_provider_calls": True,
            "zero_spend": True,
            "absent_artifacts": list(self.absent_artifacts),
            "evidence_sha256": {
                name: expected_sha
                for name, _relative_path, expected_sha in self.evidence_hashes
            },
        }


PRIOR_PREPARATION_EVIDENCE = (
    PriorPreparationEvidence(
        kind="revoked-inert-preparation",
        status="orphaned-inert-preparation",
        policy_version=PRIOR_5_POLICY_VERSION,
        run_uid=PRIOR_5_RUN_UID,
        contract_sha256=PRIOR_5_CONTRACT_SHA256,
        preparation_day=PRIOR_5_LEDGER_DAY,
        ledger_path=PRIOR_5_LEDGER_RELATIVE_PATH,
        claim_path=PRIOR_5_CLAIM_RELATIVE_PATH,
        run_path=PRIOR_5_RUN_RELATIVE_PATH,
        claim_run_dir_name="distiller-canary-attempt5-20260724",
        approval_scope=(
            "single-os-only-canary-attempt-5-haiku-global-us-sonnet-global-"
            "max-reserved-0.26-no-production"
        ),
        absent_artifacts=(
            "distiller-metered-canary-readiness.json",
            "distiller-metered-canary-gateway-receipts.json",
            "distiller-metered-canary-scorecard.json",
            (
                "vault/loop-runs/.model-spend/"
                "distiller-canary-0c938a95-1.5.0-claim.lock"
            ),
        ),
        evidence_hashes=(
            (
                "claim",
                PRIOR_5_CLAIM_RELATIVE_PATH,
                "3419834714e9a53e3e6bbd13ee034e10e6a9798c7f9c513f97bfb916074fa955",
            ),
            (
                "ledger",
                PRIOR_5_LEDGER_RELATIVE_PATH,
                "39060ecf9f6e8f94138d69d97da920c7f7fd0c78c8bd77feb9bf6e3a55434c03",
            ),
            (
                "run",
                PRIOR_5_RUN_RELATIVE_PATH,
                "e185eec29a0c9cb1277815a44db52c08bf29f907132658aa5d869a990b17ef0c",
            ),
            (
                "preparation",
                PRIOR_5_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-preparation.json",
                "231e35482b1238929bd3c9bf4b0f15bae1bd8912b45738066596416bf32602dd",
            ),
            (
                "gateway_spend",
                PRIOR_5_RUN_DIR_RELATIVE_PATH / "gateway_spend.json",
                "996cb8eca90b6f85b35d69f223b20f195814796a16c2439f0e4d5483cfd5c8e3",
            ),
            (
                "provenance",
                PRIOR_5_PROVENANCE_RELATIVE_PATH,
                "a1b420b0c95006e7b105808687cdb88bd6f781381d0dee20b32ccf0bf0000aa9",
            ),
        ),
        provenance_path=PRIOR_5_PROVENANCE_RELATIVE_PATH,
    ),
    PriorPreparationEvidence(
        kind="stranded-inert-preparation",
        status="stranded-inert-preparation",
        policy_version=PRIOR_6_POLICY_VERSION,
        run_uid=PRIOR_6_RUN_UID,
        contract_sha256=PRIOR_6_CONTRACT_SHA256,
        preparation_day=PRIOR_6_LEDGER_DAY,
        ledger_path=PRIOR_6_LEDGER_RELATIVE_PATH,
        claim_path=PRIOR_6_CLAIM_RELATIVE_PATH,
        run_path=PRIOR_6_RUN_RELATIVE_PATH,
        claim_run_dir_name=PRIOR_6_RUN_DIR_RELATIVE_PATH.name,
        approval_scope=(
            "single-os-only-canary-attempt-5-any-bounded-geo-recorded-"
            "max-reserved-0.26-no-production"
        ),
        absent_artifacts=("distiller-metered-canary-scorecard.json",),
        evidence_hashes=(
            (
                "claim",
                PRIOR_6_CLAIM_RELATIVE_PATH,
                "a859b071c3daefc8b8614bb2c98b9a32940f68405ce22a8e1345eaa7be4ac015",
            ),
            (
                "claim_lock",
                PRIOR_6_CLAIM_LOCK_RELATIVE_PATH,
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                "ledger",
                PRIOR_6_LEDGER_RELATIVE_PATH,
                "75d4b372ab631989ab9d7220d7de486e68bb809c970dd79e8ff2c9cbbeb93c0d",
            ),
            (
                "run",
                PRIOR_6_RUN_RELATIVE_PATH,
                "45c91f2c238ecd5a456ff86b6572e64e6e1f4a5ce7f7e0e298662932a1adc4ef",
            ),
            (
                "preparation",
                PRIOR_6_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-preparation.json",
                "66c3f3d0f9faab19c3ae81877e9c90f6c5e48849f6c89c059ae1266ed0c5e581",
            ),
            (
                "readiness",
                PRIOR_6_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-readiness.json",
                "6e5912164832ced78005501e69d184b7d648e08bbe876cee6fbbbcfb07698e4b",
            ),
            (
                "gateway_receipts",
                PRIOR_6_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-gateway-receipts.json",
                "b425ceebf28e3d3bbe1ce772b39d0745867df7e05a98f8776ab6d8aa1bc1cc1a",
            ),
            (
                "gateway_spend",
                PRIOR_6_RUN_DIR_RELATIVE_PATH / "gateway_spend.json",
                "996cb8eca90b6f85b35d69f223b20f195814796a16c2439f0e4d5483cfd5c8e3",
            ),
        ),
    ),
)


@dataclass(frozen=True)
class PriorExecutionEvidence:
    attempt: int
    status: str
    policy_version: str
    run_uid: str
    reservation_id: str
    reserved_nano_usd: int
    actual_nano_usd: int
    contract_sha256: str
    scorecard_sha256: str
    execution_ledger_receipt_sha256: str
    response_sha256: str
    response_text: str
    service_tier: str
    inference_geo: str
    preparation_day: str
    execution_day: str
    semantic_error: str
    run_path: Path
    claim_path: Path
    ledger_path: Path
    evidence_hashes: tuple[tuple[str, Path, str], ...]

    def policy_record(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "status": self.status,
            "policy_version": self.policy_version,
            "run_uid": self.run_uid,
            "reservation_id": self.reservation_id,
            "reserved_nano_usd": self.reserved_nano_usd,
            "actual_nano_usd": self.actual_nano_usd,
            "contract_sha256": self.contract_sha256,
            "scorecard_sha256": self.scorecard_sha256,
            "execution_ledger_receipt_sha256": (
                self.execution_ledger_receipt_sha256
            ),
            "response_sha256": self.response_sha256,
            "response_text": self.response_text,
            "service_tier": self.service_tier,
            "inference_geo": self.inference_geo,
            "preparation_day": self.preparation_day,
            "execution_day": self.execution_day,
            "semantic_error": self.semantic_error,
            "evidence_sha256": {
                name: expected_sha
                for name, _relative_path, expected_sha in self.evidence_hashes
            },
        }


PRIOR_EXECUTION_EVIDENCE = (
    PriorExecutionEvidence(
        attempt=6,
        status="reconciled-semantic-failure",
        policy_version=PRIOR_EXECUTION_POLICY_VERSION,
        run_uid=PRIOR_EXECUTION_RUN_UID,
        reservation_id=PRIOR_EXECUTION_RESERVATION_ID,
        reserved_nano_usd=PRIOR_EXECUTION_RESERVED_NANO_USD,
        actual_nano_usd=PRIOR_EXECUTION_ACTUAL_NANO_USD,
        contract_sha256=PRIOR_EXECUTION_CONTRACT_SHA256,
        scorecard_sha256=PRIOR_EXECUTION_SCORECARD_SHA256,
        execution_ledger_receipt_sha256=(
            PRIOR_EXECUTION_LEDGER_RECEIPT_SHA256
        ),
        response_sha256=PRIOR_EXECUTION_RESPONSE_SHA256,
        response_text=PRIOR_EXECUTION_RESPONSE_TEXT,
        service_tier=PRIOR_EXECUTION_SERVICE_TIER,
        inference_geo=PRIOR_EXECUTION_INFERENCE_GEO,
        preparation_day=PRIOR_EXECUTION_PREPARATION_DAY,
        execution_day=PRIOR_EXECUTION_DAY,
        semantic_error=(
            "parse-query response is malformed: "
            "Expecting value: line 1 column 1 (char 0)"
        ),
        run_path=PRIOR_EXECUTION_RUN_RELATIVE_PATH,
        claim_path=PRIOR_EXECUTION_CLAIM_RELATIVE_PATH,
        ledger_path=PRIOR_EXECUTION_LEDGER_RELATIVE_PATH,
        evidence_hashes=(
            (
                "claim",
                PRIOR_EXECUTION_CLAIM_RELATIVE_PATH,
                "631263cbc59f813387627e800e7435b7ea6d5f657da6ec7171f16a6fdece81ca",
            ),
            (
                "claim_lock",
                PRIOR_EXECUTION_CLAIM_LOCK_RELATIVE_PATH,
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                "ledger",
                PRIOR_EXECUTION_LEDGER_RELATIVE_PATH,
                "9dfaeaf9c6a2a73ba60525b7f63e113af2c661d805ca8243a10564054c2dea00",
            ),
            (
                "day_lock",
                PRIOR_EXECUTION_DAY_LOCK_RELATIVE_PATH,
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                "run",
                PRIOR_EXECUTION_RUN_RELATIVE_PATH,
                "140bf05442058362136cc628b708e356f5bdad65c6031694ac4a1d554f679aee",
            ),
            (
                "preparation",
                PRIOR_EXECUTION_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-preparation.json",
                "3e99ed069be89bb0cef946bc91571baf76cc6eba763fdbaee0bc7bdbb9e1cd0e",
            ),
            (
                "readiness",
                PRIOR_EXECUTION_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-readiness.json",
                "57e01e03cf1d07827e793128d98626b1191160c95d3ab7789beb0f5f4342c072",
            ),
            (
                "execution_ledger",
                PRIOR_EXECUTION_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-execution-ledger.json",
                PRIOR_EXECUTION_LEDGER_RECEIPT_SHA256,
            ),
            (
                "gateway_receipts",
                PRIOR_EXECUTION_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-gateway-receipts.json",
                "6bef28dae221556c00119668cb65fe8656c9938c85ec9665e20f6d962f2aef10",
            ),
            (
                "gateway_receipts_lock",
                PRIOR_EXECUTION_RUN_DIR_RELATIVE_PATH
                / ".distiller-metered-canary-gateway-receipts.json.lock",
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ),
            (
                "gateway_spend",
                PRIOR_EXECUTION_RUN_DIR_RELATIVE_PATH / "gateway_spend.json",
                "96d86d452513551d3f5bdaad821f9c551bedefc71b020f001778845f2e984135",
            ),
            (
                "scorecard",
                PRIOR_EXECUTION_RUN_DIR_RELATIVE_PATH
                / "distiller-metered-canary-scorecard.json",
                PRIOR_EXECUTION_SCORECARD_SHA256,
            ),
        ),
    ),
)


@dataclass(frozen=True)
class ModelRoute:
    task: str
    model: str
    per_call_ceiling_nano_usd: int


@dataclass(frozen=True)
class DistillerModelPolicy:
    uid: str
    version: str
    status: str
    state: str
    runner_name: str
    runner_uid: str
    routes: dict[str, ModelRoute]
    daily_ceiling_nano_usd: int
    segment_egress: dict[str, str]
    consent_mode: str
    egress_approved: bool
    production_enabled: bool
    disabled_reasons: tuple[str, ...]
    source_path: Path
    index_path: Path
    canary_admissible: bool = False
    canary_disabled_reasons: tuple[str, ...] = ()
    monthly_ceiling_nano_usd: int | None = None

    def route(self, task: str) -> ModelRoute:
        try:
            return self.routes[task]
        except KeyError as exc:
            raise PolicyError(f"unknown Distiller model task: {task!r}") from exc

    @property
    def response_usage_controls(self) -> dict[str, dict[str, object]]:
        return {
            task: {
                "service_tier": controls["service_tier"],
                "inference_geo_policy": controls["inference_geo_policy"],
            }
            for task, controls in loop_metering.LOCKED_RESPONSE_USAGE_CONTROLS.items()
        }


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise PolicyError(f"non-finite JSON constant {value!r}")


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PolicyError(f"canary claim is not canonical JSON: {exc}") from exc


def _strict_json_bytes(raw: bytes, field: str) -> dict:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except PolicyError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PolicyError(f"{field} is malformed: {exc}") from exc
    if type(value) is not dict:
        raise PolicyError(f"{field} must be a JSON object")
    return value


def _closed_object(value: Any, expected: set[str], field: str) -> dict:
    if type(value) is not dict:
        raise PolicyError(f"{field} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise PolicyError(f"{field} keys must be strings")
    if set(value) != expected:
        raise PolicyError(
            f"{field} fields must equal {sorted(expected)}; got {sorted(value)}"
        )
    return value


def _exact_int(value: Any, expected: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise PolicyError(f"{field} must equal integer {expected}")


def _nano_amount(value: Any, field: str, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > maximum
    ):
        raise PolicyError(
            f"{field} must be exact nonnegative nano-USD at or below {maximum}"
        )
    return value


def _usd_to_nano(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise PolicyError(f"{field} must be an exact finite USD number")
    try:
        decimal = Decimal(str(value))
        nano = decimal * Decimal(1_000_000_000)
    except (InvalidOperation, ValueError) as exc:
        raise PolicyError(f"{field} must be an exact finite USD number") from exc
    if not decimal.is_finite() or decimal < 0 or nano != nano.to_integral_value():
        raise PolicyError(f"{field} must convert exactly to nonnegative nano-USD")
    return int(nano)


def _path_has_symlink(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _read_frontmatter(path: Path) -> dict:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise PolicyError(f"canonical policy source is unreadable: {exc}") from exc
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise PolicyError("canonical policy source has no YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise PolicyError("canonical policy frontmatter is unterminated") from exc
    try:
        value = yaml.load("\n".join(lines[1:end]), Loader=_UniqueLoader)
    except PolicyError:
        raise
    except yaml.YAMLError as exc:
        raise PolicyError(f"canonical policy YAML is invalid: {exc}") from exc
    if type(value) is not dict:
        raise PolicyError("canonical policy frontmatter must be an object")
    unknown = sorted(set(value) - _TOP_LEVEL_FIELDS)
    if unknown:
        raise PolicyError(f"canonical policy has unknown fields: {unknown}")
    return value


def _read_current_index(path: Path) -> list[dict]:
    if path.is_symlink() or not path.is_file():
        raise PolicyError("current index is missing or symlinked")
    rows = []
    try:
        for line_number, raw in enumerate(path.read_bytes().splitlines(), 1):
            if not raw.strip():
                continue
            value = json.loads(
                raw.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
            if type(value) is not dict:
                raise PolicyError(f"current index line {line_number} is not an object")
            rows.append(value)
    except PolicyError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PolicyError(f"current index is malformed: {exc}") from exc
    return rows


def _read_runner_frontmatter(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise PolicyError("registered runner source is missing or symlinked")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PolicyError(f"registered runner source is unreadable: {exc}") from exc
    marker = '"""---\n'
    start = text.find(marker)
    if start != 0:
        raise PolicyError("registered runner has no leading metadata block")
    end = text.find("\n---", start + len(marker))
    if end < 0:
        raise PolicyError("registered runner metadata is unterminated")
    try:
        value = yaml.load(
            text[start + len(marker) : end],
            Loader=_UniqueLoader,
        )
    except PolicyError:
        raise
    except yaml.YAMLError as exc:
        raise PolicyError(f"registered runner metadata is invalid: {exc}") from exc
    if type(value) is not dict:
        raise PolicyError("registered runner metadata must be an object")
    return value


def _registered_runner(rows: list[dict], root: Path, runner_ref: object) -> str:
    if not isinstance(runner_ref, str) or not _UID_RE.fullmatch(runner_ref):
        raise PolicyError("policy.ref must be one registered 8-hex tool UID")
    matches = [
        row
        for row in rows
        if row.get("type") == "tool"
        and row.get("uid") == runner_ref
        and row.get("status") == "active"
        and row.get("state", "active") == "active"
    ]
    if len(matches) != 1:
        raise PolicyError(
            f"expected one active registered {POLICY_RUNNER} tool; found {len(matches)}"
        )
    row = matches[0]
    uid = row.get("uid")
    if not isinstance(uid, str) or not _UID_RE.fullmatch(uid):
        raise PolicyError("registered runner UID must be 8 lowercase hex")
    expected_path = f"vault/tools/{uid}.py"
    if row.get("path") != expected_path:
        raise PolicyError(f"registered runner path must equal {expected_path}")
    source = root / expected_path
    if _path_has_symlink(source) or source.resolve() != (
        root.resolve() / expected_path
    ):
        raise PolicyError("registered runner source path drifted")
    metadata = _read_runner_frontmatter(source)
    expected = {
        "uid": uid,
        "name": POLICY_RUNNER,
        "type": "tool",
        "status": "active",
        "state": "active",
        "transport": "library",
        "implementation_kind": "library",
    }
    for field, value in expected.items():
        if metadata.get(field) != value or row.get(field, value) != value:
            raise PolicyError(f"registered runner {field} drifted")
    return uid


def _evidence_bytes(root: Path, relative_path: Path, field: str) -> bytes:
    path = root / relative_path
    if _path_has_symlink(path) or path.is_symlink() or not path.is_file():
        raise PolicyError(f"{field} is missing or symlinked")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PolicyError(f"{field} is unreadable: {exc}") from exc


def _verify_os_geo_ruling_event(root: Path) -> None:
    """Verify Mike's OPTION 3 ruling first-hand from its canonical stream."""
    raw = _evidence_bytes(
        root,
        OS_GEO_EVENT_RELATIVE_PATH,
        "OS geo ruling event stream",
    )
    try:
        events = [
            json.loads(
                line.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
            for line in raw.splitlines()
            if line.strip()
        ]
    except PolicyError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PolicyError(f"OS geo ruling event stream is malformed: {exc}") from exc
    matches = [
        event
        for event in events
        if type(event) is dict
        and (
            event.get("event_uid") == OS_GEO_SOURCE_EVENT
            or event.get("id") == OS_GEO_SOURCE_EVENT
        )
    ]
    if len(matches) != 1:
        raise PolicyError(
            "OS geo ruling source_event must occur exactly once in canonical stream"
        )
    event = _closed_object(
        matches[0],
        {
            "specversion",
            "type",
            "source",
            "time",
            "source_uid",
            "lifecycle",
            "subject",
            "correlationid",
            "causationid",
            "data",
            "id",
            "event_uid",
            "writer_instance_uid",
            "stream_uid",
            "local_seq",
        },
        "OS geo ruling event",
    )
    expected_event = {
        "specversion": "1.0",
        "type": "tropo.message.sent",
        "source": "/agents/metis",
        "time": "2026-07-24T20:57:43Z",
        "source_uid": "7c017d1f",
        "lifecycle": "evergreen",
        "subject": "cdf9b3ad",
        "correlationid": "distiller-local-canary-a139-attempt4-20260724",
        "causationid": "evt_7c41ab5947a779a3_00000009",
        "id": OS_GEO_SOURCE_EVENT,
        "event_uid": OS_GEO_SOURCE_EVENT,
        "writer_instance_uid": "6147bbbaaf258b3c",
        "stream_uid": "6147bbbaaf258b3c",
        "local_seq": 17,
    }
    if any(
        type(event.get(field)) is not type(expected)
        or event.get(field) != expected
        for field, expected in expected_event.items()
    ):
        raise PolicyError("OS geo ruling event identity, source, or subject drifted")
    data = _closed_object(
        event["data"],
        {"to", "reply_required", "message"},
        "OS geo ruling event data",
    )
    expected_data = {
        "to": "argus",
        "reply_required": True,
        "message": OS_GEO_RULING_MESSAGE,
    }
    if any(
        type(data.get(field)) is not type(expected)
        or data.get(field) != expected
        for field, expected in expected_data.items()
    ):
        raise PolicyError("OS geo ruling event semantics drifted")


def _validate_os_geo_ruling(fm: dict, root: Path) -> None:
    ruling = _closed_object(
        fm.get("os_geo_ruling"),
        {"ruled_by", "source_event", "scope", "team_private", "revisit_on"},
        "os_geo_ruling",
    )
    expected = {
        "ruled_by": OS_GEO_RULED_BY,
        "source_event": OS_GEO_SOURCE_EVENT,
        "scope": OS_GEO_RULING_SCOPE,
        "team_private": "blocked",
        "revisit_on": "team-private-model-egress",
    }
    if any(
        type(ruling.get(field)) is not type(value)
        or ruling.get(field) != value
        for field, value in expected.items()
    ):
        raise PolicyError("os_geo_ruling binding drifted")
    _verify_os_geo_ruling_event(root)


def _verify_one_prior_attempt(root: Path, evidence: PriorAttemptEvidence) -> None:
    label = f"attempt-{evidence.attempt}"
    run_evidence_paths = {
        relative_path
        for relative_path, _expected_sha in evidence.evidence_hashes
        if relative_path.parent == evidence.run_path.parent
    }
    run_evidence_dir = root / evidence.run_path.parent
    try:
        actual_run_paths = {
            path.relative_to(root)
            for path in run_evidence_dir.iterdir()
        }
    except OSError as exc:
        raise PolicyError(f"{label} evidence tree is unreadable: {exc}") from exc
    if actual_run_paths != run_evidence_paths:
        raise PolicyError(f"{label} evidence tree files drifted")
    for relative_path, expected_sha in evidence.evidence_hashes:
        raw = _evidence_bytes(
            root,
            relative_path,
            f"{label} evidence {relative_path.name}",
        )
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise PolicyError(f"{label} evidence hash drifted: {relative_path}")

    try:
        ledger_raw = _evidence_bytes(
            root,
            evidence.ledger_path,
            f"{label} ledger evidence",
        )
        ledger = daily_spend._validate_ledger(
            daily_spend._strict_json(ledger_raw),
            expected_day=evidence.ledger_day,
            policy_uid=POLICY_UID,
            policy_version=evidence.policy_version,
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
        )
    except daily_spend.DailySpendError as exc:
        raise PolicyError(f"{label} ledger evidence is invalid: {exc}") from exc
    reservation = ledger["reservations"].get(evidence.reservation_id)
    if (
        ledger["poisoned"]
        or set(ledger["reservations"]) != {evidence.reservation_id}
        or type(reservation) is not dict
        or reservation.get("run_uid") != evidence.run_uid
        or reservation.get("task") != "parse-query"
        or reservation.get("model") != evidence.expected_model
        or reservation.get("worst_case_nano_usd") != evidence.retained_nano_usd
        or reservation.get("status") != "claimed"
        or reservation.get("actual_nano_usd") is not None
    ):
        raise PolicyError(f"{label} retained reservation evidence drifted")

    claim_raw = _evidence_bytes(
        root,
        evidence.claim_path,
        f"{label} global claim evidence",
    )
    claim = _strict_json_bytes(claim_raw, f"{label} global claim evidence")
    if _canonical_json_bytes(claim) + b"\n" != claim_raw:
        raise PolicyError(f"{label} global claim evidence is not canonical JSON")
    _closed_object(
        claim,
        {
            "schema_version",
            "policy_uid",
            "policy_version",
            "runner_uid",
            "run_uid",
            "run_dir",
            "contract_sha256",
            "approval_scope",
        },
        f"{label} global claim evidence",
    )
    expected_claim = {
        "schema_version": 1,
        "policy_uid": POLICY_UID,
        "policy_version": evidence.policy_version,
        "runner_uid": "6389dcd4",
        "run_uid": evidence.run_uid,
        "contract_sha256": evidence.contract_sha256,
        "approval_scope": evidence.approval_scope,
    }
    if any(
        type(claim.get(field)) is not type(expected)
        or claim.get(field) != expected
        for field, expected in expected_claim.items()
    ) or (
        not isinstance(claim.get("run_dir"), str)
        or Path(claim["run_dir"]).name != evidence.run_path.parent.name
    ):
        raise PolicyError(f"{label} global claim evidence identity drifted")

    run_raw = _evidence_bytes(root, evidence.run_path, f"{label} run evidence")
    try:
        run_events = [
            json.loads(
                line.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
            for line in run_raw.splitlines()
            if line.strip()
        ]
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PolicyError(f"{label} run evidence is malformed: {exc}") from exc
    expected_created = {
        "event": "run_created",
        "run_uid": evidence.run_uid,
        "loop": POLICY_UID,
        "loop_version": evidence.policy_version,
    }
    if len(run_events) != 2 or any(type(event) is not dict for event in run_events):
        raise PolicyError(f"{label} run evidence identity drifted")
    contract = _closed_object(
        run_events[1],
        {
            "event",
            "loop",
            "loop_version",
            "policy",
            "admission_mode",
            "segment_classes",
            "tasks",
            "request_sha256",
            "brakes",
        },
        f"{label} run contract",
    )
    request_hashes = _closed_object(
        contract["request_sha256"],
        {"parse-query", "distill"},
        f"{label} request hashes",
    )
    if (
        run_events[0] != expected_created
        or contract["event"] != "loop_contract_locked"
        or contract["loop"] != POLICY_UID
        or contract["loop_version"] != evidence.policy_version
        or contract["policy"] != {"kind": "agentic-tool", "ref": "6389dcd4"}
        or contract["admission_mode"] != "canary"
        or contract["segment_classes"] != ["os"]
        or contract["tasks"] != ["parse-query", "distill"]
        or contract["brakes"]
        != {
            "max_iterations": CANARY_MAX_CALLS,
            "max_budget_usd": 0.26,
            "max_wall_clock_min": 5,
        }
        or any(
            not isinstance(value, str) or not _SHA256_RE.fullmatch(value)
            for value in request_hashes.values()
        )
    ):
        raise PolicyError(f"{label} run evidence identity drifted")
    if b"".join(
        _canonical_json_bytes(event) + b"\n" for event in run_events
    ) != run_raw:
        raise PolicyError(f"{label} run evidence is not canonical JSONL")
    contract_sha = hashlib.sha256(
        _canonical_json_bytes(run_events[1])
    ).hexdigest()
    if (
        contract_sha != evidence.contract_sha256
        or claim["contract_sha256"] != contract_sha
    ):
        raise PolicyError(f"{label} contract SHA-256 chain drifted")

    run_dir = evidence.run_path.parent

    def read_run_json(name: str) -> dict:
        raw = _evidence_bytes(root, run_dir / name, f"{label} {name}")
        value = _strict_json_bytes(raw, f"{label} {name}")
        if _canonical_json_bytes(value) + b"\n" != raw:
            raise PolicyError(f"{label} {name} is not canonical closed JSON")
        return value

    preparation = read_run_json("distiller-metered-canary-preparation.json")
    readiness = read_run_json("distiller-metered-canary-readiness.json")
    gateway = read_run_json("distiller-metered-canary-gateway-receipts.json")
    gateway_spend = read_run_json("gateway_spend.json")
    request_hashes = contract["request_sha256"]
    shared_identity = {
        "policy_uid": POLICY_UID,
        "policy_version": evidence.policy_version,
        "run_uid": evidence.run_uid,
        "runner_uid": "6389dcd4",
        "contract_sha256": contract_sha,
    }
    if any(
        any(surface.get(field) != expected for field, expected in shared_identity.items())
        for surface in (preparation, readiness)
    ):
        raise PolicyError(f"{label} preparation/readiness identity drifted")
    if (
        preparation.get("status") != "prepared"
        or readiness.get("status") != "ready"
        or preparation.get("request_sha256") != request_hashes
        or readiness.get("request_sha256") != request_hashes
        or preparation.get("segment_classes") != ["os"]
        or preparation.get("tasks") != ["parse-query", "distill"]
        or preparation.get("max_iterations") != CANARY_MAX_CALLS
        or preparation.get("max_reserved_nano_usd")
        != CANARY_MAX_RESERVED_NANO_USD
        or readiness.get("admission_mode") != "canary"
        or readiness.get("gateway_url") != "http://127.0.0.1:8080"
        or readiness.get("gateway_spend_nano_usd") != 0
        or readiness.get("real_key_present") is not True
    ):
        raise PolicyError(f"{label} preparation/readiness values drifted")
    if gateway != {
        "schema_version": 1,
        "policy_uid": POLICY_UID,
        "policy_version": evidence.policy_version,
        "run_uid": evidence.run_uid,
        "contract_sha256": contract_sha,
        "receipts": [],
    }:
        raise PolicyError(f"{label} gateway receipt evidence drifted")
    expected_gateway_spend = dict(evidence.gateway_spend)
    _closed_object(
        gateway_spend,
        set(expected_gateway_spend),
        f"{label} gateway spend",
    )
    if any(
        type(gateway_spend.get(field)) is not type(expected)
        or gateway_spend.get(field) != expected
        for field, expected in expected_gateway_spend.items()
    ):
        raise PolicyError(f"{label} gateway failure evidence drifted")

    scorecard_raw = _evidence_bytes(
        root,
        run_dir / "distiller-metered-canary-scorecard.json",
        f"{label} scorecard evidence",
    )
    scorecard = _strict_json_bytes(scorecard_raw, f"{label} scorecard evidence")
    receipts = scorecard.get("receipts")
    receipt = receipts[0] if isinstance(receipts, list) and len(receipts) == 1 else None
    if (
        hashlib.sha256(scorecard_raw).hexdigest() != evidence.scorecard_sha256
        or type(scorecard.get("run")) is not dict
        or scorecard["run"].get("contract_sha256") != contract_sha
        or scorecard.get("status") != "failed"
        or scorecard.get("actual_nano_usd") != 0
        or scorecard.get("reserved_nano_usd") != evidence.retained_nano_usd
        or scorecard.get("gateway_spend_usd") is not None
        or scorecard.get("gateway_receipts") != []
        or scorecard.get("phase") != "calls"
        or scorecard.get("error") != evidence.scorecard_error
        or type(scorecard.get("policy")) is not dict
        or scorecard["policy"].get("uid") != POLICY_UID
        or scorecard["policy"].get("version") != evidence.policy_version
        or scorecard["run"].get("uid") != evidence.run_uid
        or type(receipt) is not dict
        or receipt.get("reservation_id") != evidence.reservation_id
        or receipt.get("task") != "parse-query"
        or receipt.get("reserved_nano_usd") != evidence.retained_nano_usd
        or receipt.get("reservation_status") != "claimed"
        or receipt.get("worst_case_retained") is not True
        or receipt.get("error") != evidence.receipt_error
        or receipt.get("status") != "failed"
        or receipt.get("actual_nano_usd") is not None
        or receipt.get("response_sha256") is not None
        or receipt.get("response_text") is not None
    ):
        raise PolicyError(f"{label} scorecard evidence values drifted")


def _verify_prior_attempt_evidence(root: Path, canary: dict) -> None:
    """Verify all four ordered prior failures from every immutable evidence byte."""
    prior_attempts = canary.get("prior_attempts")
    if not isinstance(prior_attempts, list) or len(prior_attempts) != 4:
        raise PolicyError(
            "canary_egress.prior_attempts must contain attempts 1, 2, 3, then 4"
        )
    for index, (actual, evidence) in enumerate(
        zip(prior_attempts, PRIOR_ATTEMPT_EVIDENCE),
        1,
    ):
        expected = evidence.policy_record()
        _closed_object(
            actual,
            set(expected),
            f"canary_egress.prior_attempts[{index - 1}]",
        )
        if any(
            type(actual.get(field)) is not type(value)
            or actual.get(field) != value
            for field, value in expected.items()
        ):
            raise PolicyError(
                "canary_egress.prior_attempts must be the exact ordered "
                "attempt-1/attempt-2/attempt-3/attempt-4 evidence list"
            )
        _verify_one_prior_attempt(root, evidence)
    retained_total = sum(
        evidence.retained_nano_usd for evidence in PRIOR_ATTEMPT_EVIDENCE
    )
    if retained_total != PRIOR_RETAINED_TOTAL_NANO_USD:
        raise PolicyError("prior retained spend total drifted")


def _verify_one_prior_preparation(
    root: Path,
    evidence: PriorPreparationEvidence,
) -> None:
    label = f"prior preparation {evidence.policy_version}"
    run_dir = evidence.run_path.parent
    for absent in evidence.absent_artifacts:
        relative = Path(absent)
        path = root / relative if len(relative.parts) > 1 else root / run_dir / relative
        if path.exists() or path.is_symlink():
            raise PolicyError(f"{label} absent artifact appeared: {absent}")
    expected_run_paths = {
        relative_path
        for _name, relative_path, _expected_sha in evidence.evidence_hashes
        if relative_path.parent == run_dir
    }
    try:
        actual_run_paths = {
            path.relative_to(root)
            for path in (root / run_dir).iterdir()
        }
    except OSError as exc:
        raise PolicyError(f"{label} evidence tree is unreadable: {exc}") from exc
    if actual_run_paths != expected_run_paths:
        raise PolicyError(f"{label} evidence tree files drifted")

    raw_by_name: dict[str, bytes] = {}
    for name, relative_path, expected_sha in evidence.evidence_hashes:
        raw = _evidence_bytes(root, relative_path, f"{label} {name}")
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise PolicyError(f"{label} evidence hash drifted: {relative_path}")
        raw_by_name[name] = raw

    try:
        ledger = daily_spend._validate_ledger(
            daily_spend._strict_json(raw_by_name["ledger"]),
            expected_day=evidence.preparation_day,
            policy_uid=POLICY_UID,
            policy_version=evidence.policy_version,
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
        )
    except daily_spend.DailySpendError as exc:
        raise PolicyError(f"{label} ledger evidence is invalid: {exc}") from exc
    if (
        ledger["reservations"] != {}
        or ledger["actual_total_nano_usd"] != 0
        or ledger["poisoned"]
    ):
        raise PolicyError(f"{label} ledger is not inert")

    claim = _strict_json_bytes(raw_by_name["claim"], f"{label} claim")
    if _canonical_json_bytes(claim) + b"\n" != raw_by_name["claim"]:
        raise PolicyError(f"{label} claim is not canonical JSON")
    _closed_object(
        claim,
        {
            "schema_version",
            "policy_uid",
            "policy_version",
            "runner_uid",
            "run_uid",
            "run_dir",
            "contract_sha256",
            "approval_scope",
        },
        f"{label} claim",
    )
    expected_claim = {
        "schema_version": 1,
        "policy_uid": POLICY_UID,
        "policy_version": evidence.policy_version,
        "runner_uid": "6389dcd4",
        "run_uid": evidence.run_uid,
        "contract_sha256": evidence.contract_sha256,
        "approval_scope": evidence.approval_scope,
    }
    if any(
        type(claim.get(field)) is not type(expected)
        or claim.get(field) != expected
        for field, expected in expected_claim.items()
    ) or (
        not isinstance(claim.get("run_dir"), str)
        or Path(claim["run_dir"]).name != evidence.claim_run_dir_name
    ):
        raise PolicyError(f"{label} claim identity drifted")

    try:
        events = [
            json.loads(
                line.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
            for line in raw_by_name["run"].splitlines()
            if line.strip()
        ]
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PolicyError(f"{label} run evidence is malformed: {exc}") from exc
    if (
        len(events) != 2
        or events[0]
        != {
            "event": "run_created",
            "run_uid": evidence.run_uid,
            "loop": POLICY_UID,
            "loop_version": evidence.policy_version,
        }
    ):
        raise PolicyError(f"{label} run identity drifted")
    contract = _closed_object(
        events[1],
        {
            "event",
            "loop",
            "loop_version",
            "policy",
            "admission_mode",
            "segment_classes",
            "tasks",
            "request_sha256",
            "brakes",
        },
        f"{label} contract",
    )
    request_hashes = {
        "parse-query": (
            "671107293d8ea6fedd08d7c8d4a61d169143fca2b391e0772e993453f81d2923"
        ),
        "distill": (
            "79279cdc5677aad1ec24755e18fccfb6ca42c2147526f95aafa097b6ca229584"
        ),
    }
    if contract != {
        "event": "loop_contract_locked",
        "loop": POLICY_UID,
        "loop_version": evidence.policy_version,
        "policy": {"kind": "agentic-tool", "ref": "6389dcd4"},
        "admission_mode": "canary",
        "segment_classes": ["os"],
        "tasks": ["parse-query", "distill"],
        "request_sha256": request_hashes,
        "brakes": {
            "max_iterations": CANARY_MAX_CALLS,
            "max_budget_usd": 0.26,
            "max_wall_clock_min": 5,
        },
    }:
        raise PolicyError(f"{label} run contract drifted")
    if b"".join(_canonical_json_bytes(event) + b"\n" for event in events) != (
        raw_by_name["run"]
    ):
        raise PolicyError(f"{label} run evidence is not canonical JSONL")
    contract_sha = hashlib.sha256(_canonical_json_bytes(contract)).hexdigest()
    if contract_sha != evidence.contract_sha256:
        raise PolicyError(f"{label} contract SHA-256 chain drifted")

    def surface(name: str) -> dict:
        value = _strict_json_bytes(raw_by_name[name], f"{label} {name}")
        if _canonical_json_bytes(value) + b"\n" != raw_by_name[name]:
            raise PolicyError(f"{label} {name} is not canonical JSON")
        return value

    preparation = surface("preparation")
    expected_preparation = {
        "schema_version": 1,
        "status": "prepared",
        "policy_uid": POLICY_UID,
        "policy_version": evidence.policy_version,
        "runner_uid": "6389dcd4",
        "run_uid": evidence.run_uid,
        "contract_sha256": evidence.contract_sha256,
        "request_sha256": request_hashes,
        "admission_mode": "canary",
        "segment_classes": ["os"],
        "tasks": ["parse-query", "distill"],
        "max_iterations": CANARY_MAX_CALLS,
        "max_reserved_nano_usd": CANARY_MAX_RESERVED_NANO_USD,
    }
    if preparation != expected_preparation:
        raise PolicyError(f"{label} preparation receipt drifted")
    if surface("gateway_spend") != {"spent_usd": 0.0}:
        raise PolicyError(f"{label} gateway spend is not exact zero")

    if evidence.policy_version == PRIOR_6_POLICY_VERSION:
        readiness = surface("readiness")
        if readiness != {
            "schema_version": 1,
            "status": "ready",
            "policy_uid": POLICY_UID,
            "policy_version": evidence.policy_version,
            "runner_uid": "6389dcd4",
            "run_uid": evidence.run_uid,
            "contract_sha256": evidence.contract_sha256,
            "request_sha256": request_hashes,
            "admission_mode": "canary",
            "gateway_url": "http://127.0.0.1:8080",
            "gateway_spend_nano_usd": 0,
            "real_key_present": True,
        }:
            raise PolicyError(f"{label} readiness receipt drifted")
        if surface("gateway_receipts") != {
            "schema_version": 1,
            "policy_uid": POLICY_UID,
            "policy_version": evidence.policy_version,
            "run_uid": evidence.run_uid,
            "contract_sha256": evidence.contract_sha256,
            "receipts": [],
        }:
            raise PolicyError(f"{label} gateway receipts are not exact empty state")

    if evidence.provenance_path is not None:
        provenance = surface("provenance")
        expected_source_hashes = {
            "gateway_spend.json": evidence.policy_record()["evidence_sha256"][
                "gateway_spend"
            ],
            "preparation.json": evidence.policy_record()["evidence_sha256"][
                "preparation"
            ],
            "run.jsonl": evidence.policy_record()["evidence_sha256"]["run"],
            "v1.5.0-claim.json": evidence.policy_record()["evidence_sha256"]["claim"],
            "v1.5.0-ledger.json": evidence.policy_record()["evidence_sha256"]["ledger"],
        }
        if provenance != {
            "schema_version": 1,
            "status": evidence.status,
            "policy_uid": POLICY_UID,
            "policy_version": evidence.policy_version,
            "run_uid": evidence.run_uid,
            "source_branch": "canary-evidence/distiller-orphan-v15-prepare-a3a7ed57",
            "source_commit": "9aac71ad62755668131a1bb4dc9b475438775d91",
            "original_run_relative_path": (
                "vault/loop-runs/distiller-canary-attempt5-20260724"
            ),
            "rehomed_run_relative_path": run_dir.as_posix(),
            "source_hashes": expected_source_hashes,
            "zero_reservations": True,
            "zero_provider_calls": True,
            "zero_spend": True,
            "key_material_hits": 0,
            "absent_artifacts": list(evidence.absent_artifacts),
        }:
            raise PolicyError(f"{label} provenance semantics drifted")


def _verify_prior_preparation_evidence(root: Path, canary: dict) -> None:
    prior = canary.get("prior_preparations")
    if not isinstance(prior, list) or len(prior) != len(PRIOR_PREPARATION_EVIDENCE):
        raise PolicyError(
            "canary_egress.prior_preparations must contain exact v1.5 and v1.6 "
            "inert preparations"
        )
    for index, (actual, evidence) in enumerate(
        zip(prior, PRIOR_PREPARATION_EVIDENCE)
    ):
        expected = evidence.policy_record()
        _closed_object(
            actual,
            set(expected),
            f"canary_egress.prior_preparations[{index}]",
        )
        if actual != expected:
            raise PolicyError(
                "canary_egress.prior_preparations must be the exact ordered "
                "v1.5/v1.6 evidence list"
            )
        _verify_one_prior_preparation(root, evidence)


def _verify_one_prior_execution(
    root: Path,
    evidence: PriorExecutionEvidence,
) -> None:
    label = f"prior execution attempt-{evidence.attempt}"
    run_dir = evidence.run_path.parent
    expected_run_paths = {
        relative_path
        for _name, relative_path, _expected_sha in evidence.evidence_hashes
        if relative_path.parent == run_dir
    }
    try:
        actual_run_paths = {
            path.relative_to(root)
            for path in (root / run_dir).iterdir()
        }
    except OSError as exc:
        raise PolicyError(f"{label} evidence tree is unreadable: {exc}") from exc
    if actual_run_paths != expected_run_paths:
        raise PolicyError(f"{label} evidence tree files drifted")

    raw_by_name: dict[str, bytes] = {}
    for name, relative_path, expected_sha in evidence.evidence_hashes:
        raw = _evidence_bytes(root, relative_path, f"{label} {name}")
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise PolicyError(f"{label} evidence hash drifted: {relative_path}")
        raw_by_name[name] = raw

    try:
        events = [
            json.loads(
                line.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
            for line in raw_by_name["run"].splitlines()
            if line.strip()
        ]
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PolicyError(f"{label} run evidence is malformed: {exc}") from exc
    old_request_hashes = {
        "parse-query": (
            "671107293d8ea6fedd08d7c8d4a61d169143fca2b391e0772e993453f81d2923"
        ),
        "distill": (
            "79279cdc5677aad1ec24755e18fccfb6ca42c2147526f95aafa097b6ca229584"
        ),
    }
    expected_events = [
        {
            "event": "run_created",
            "run_uid": evidence.run_uid,
            "loop": POLICY_UID,
            "loop_version": evidence.policy_version,
        },
        {
            "event": "loop_contract_locked",
            "loop": POLICY_UID,
            "loop_version": evidence.policy_version,
            "policy": {"kind": "agentic-tool", "ref": "6389dcd4"},
            "admission_mode": "canary",
            "segment_classes": ["os"],
            "tasks": ["parse-query", "distill"],
            "request_sha256": old_request_hashes,
            "brakes": {
                "max_iterations": CANARY_MAX_CALLS,
                "max_budget_usd": 0.26,
                "max_wall_clock_min": 5,
            },
        },
    ]
    if events != expected_events or b"".join(
        _canonical_json_bytes(event) + b"\n" for event in events
    ) != raw_by_name["run"]:
        raise PolicyError(f"{label} run contract drifted")
    if hashlib.sha256(_canonical_json_bytes(events[1])).hexdigest() != (
        evidence.contract_sha256
    ):
        raise PolicyError(f"{label} contract SHA-256 chain drifted")

    claim = _strict_json_bytes(raw_by_name["claim"], f"{label} claim")
    if _canonical_json_bytes(claim) + b"\n" != raw_by_name["claim"]:
        raise PolicyError(f"{label} claim is not canonical JSON")
    _closed_object(
        claim,
        {
            "schema_version",
            "policy_uid",
            "policy_version",
            "runner_uid",
            "run_uid",
            "run_dir",
            "contract_sha256",
            "approval_scope",
        },
        f"{label} claim",
    )
    if (
        claim.get("schema_version") != 1
        or claim.get("policy_uid") != POLICY_UID
        or claim.get("policy_version") != evidence.policy_version
        or claim.get("runner_uid") != "6389dcd4"
        or claim.get("run_uid") != evidence.run_uid
        or claim.get("contract_sha256") != evidence.contract_sha256
        or claim.get("approval_scope")
        != (
            "single-os-only-canary-attempt-6-claim-bound-execution-day-"
            "ledger-max-reserved-0.26-no-production"
        )
        or not isinstance(claim.get("run_dir"), str)
        or Path(claim["run_dir"]).name != run_dir.name
    ):
        raise PolicyError(f"{label} claim identity drifted")

    try:
        ledger = daily_spend._validate_ledger(
            daily_spend._strict_json(raw_by_name["ledger"]),
            expected_day=evidence.execution_day,
            policy_uid=POLICY_UID,
            policy_version=evidence.policy_version,
            daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
        )
    except daily_spend.DailySpendError as exc:
        raise PolicyError(f"{label} ledger evidence is invalid: {exc}") from exc
    reservation = ledger["reservations"].get(evidence.reservation_id)
    if (
        ledger["poisoned"]
        or ledger["actual_total_nano_usd"] != evidence.actual_nano_usd
        or set(ledger["reservations"]) != {evidence.reservation_id}
        or type(reservation) is not dict
        or reservation.get("run_uid") != evidence.run_uid
        or reservation.get("task") != "parse-query"
        or reservation.get("model") != "claude-haiku-4-5-20251001"
        or reservation.get("segment_classes") != ["os"]
        or reservation.get("worst_case_nano_usd") != evidence.reserved_nano_usd
        or reservation.get("actual_nano_usd") != evidence.actual_nano_usd
        or reservation.get("status") != "reconciled"
    ):
        raise PolicyError(f"{label} reconciled reservation evidence drifted")

    def surface(name: str) -> dict:
        value = _strict_json_bytes(raw_by_name[name], f"{label} {name}")
        if _canonical_json_bytes(value) + b"\n" != raw_by_name[name]:
            raise PolicyError(f"{label} {name} is not canonical JSON")
        return value

    preparation = surface("preparation")
    readiness = surface("readiness")
    execution_ledger = surface("execution_ledger")
    gateway_receipts = surface("gateway_receipts")
    gateway_spend = surface("gateway_spend")
    scorecard = surface("scorecard")
    shared = {
        "policy_uid": POLICY_UID,
        "policy_version": evidence.policy_version,
        "run_uid": evidence.run_uid,
        "contract_sha256": evidence.contract_sha256,
    }
    if any(
        any(value.get(field) != expected for field, expected in shared.items())
        for value in (preparation, readiness, execution_ledger, gateway_receipts)
    ):
        raise PolicyError(f"{label} identity chain drifted")
    if (
        preparation.get("status") != "prepared"
        or preparation.get("preparation_day") != evidence.preparation_day
        or preparation.get("request_sha256") != old_request_hashes
        or readiness.get("status") != "ready"
        or readiness.get("request_sha256") != old_request_hashes
        or readiness.get("gateway_spend_nano_usd") != 0
        or readiness.get("gateway_url") != "http://127.0.0.1:8080"
        or readiness.get("real_key_present") is not True
        or execution_ledger.get("status") != "initialized"
        or execution_ledger.get("preparation_day") != evidence.preparation_day
        or execution_ledger.get("execution_day") != evidence.execution_day
        or execution_ledger.get("ledger_relative_path")
        != evidence.ledger_path.as_posix()
        or gateway_spend != {"spent_usd": 0.000218}
    ):
        raise PolicyError(f"{label} lifecycle or spend evidence drifted")

    expected_gateway_receipt = {
        "reservation_id": evidence.reservation_id,
        "task": "parse-query",
        "model": "claude-haiku-4-5-20251001",
        "actual_nano_usd": evidence.actual_nano_usd,
        "response_sha256": evidence.response_sha256,
        "service_tier": evidence.service_tier,
        "inference_geo": evidence.inference_geo,
    }
    if gateway_receipts.get("receipts") != [expected_gateway_receipt]:
        raise PolicyError(f"{label} gateway receipt evidence drifted")

    receipts = scorecard.get("receipts")
    receipt = receipts[0] if isinstance(receipts, list) and len(receipts) == 1 else None
    if (
        hashlib.sha256(raw_by_name["scorecard"]).hexdigest()
        != evidence.scorecard_sha256
        or hashlib.sha256(raw_by_name["execution_ledger"]).hexdigest()
        != evidence.execution_ledger_receipt_sha256
        or hashlib.sha256(
            evidence.response_text.encode("utf-8", errors="strict")
        ).hexdigest()
        != evidence.response_sha256
        or scorecard.get("status") != "failed"
        or scorecard.get("phase") != "calls"
        or scorecard.get("error") != evidence.semantic_error
        or scorecard.get("preparation_day") != evidence.preparation_day
        or scorecard.get("execution_day") != evidence.execution_day
        or scorecard.get("reserved_nano_usd") != evidence.reserved_nano_usd
        or scorecard.get("actual_nano_usd") != evidence.actual_nano_usd
        or scorecard.get("execution_ledger_receipt_sha256")
        != evidence.execution_ledger_receipt_sha256
        or scorecard.get("gateway_receipts") != [expected_gateway_receipt]
        or type(receipt) is not dict
        or receipt.get("reservation_id") != evidence.reservation_id
        or receipt.get("reservation_status") != "reconciled"
        or receipt.get("reserved_nano_usd") != evidence.reserved_nano_usd
        or receipt.get("actual_nano_usd") != evidence.actual_nano_usd
        or receipt.get("worst_case_retained") is not False
        or receipt.get("response_text") != evidence.response_text
        or receipt.get("response_sha256") != evidence.response_sha256
        or receipt.get("response_service_tier") != evidence.service_tier
        or receipt.get("response_inference_geo") != evidence.inference_geo
        or receipt.get("error") != evidence.semantic_error
        or receipt.get("status") != "failed"
    ):
        raise PolicyError(f"{label} scorecard evidence values drifted")


def _verify_prior_execution_evidence(root: Path, canary: dict) -> None:
    prior = canary.get("prior_executions")
    if not isinstance(prior, list) or len(prior) != len(PRIOR_EXECUTION_EVIDENCE):
        raise PolicyError(
            "canary_egress.prior_executions must contain exact closed attempt-6 "
            "reconciled semantic failure"
        )
    for index, (actual, evidence) in enumerate(
        zip(prior, PRIOR_EXECUTION_EVIDENCE)
    ):
        expected = evidence.policy_record()
        _closed_object(
            actual,
            set(expected),
            f"canary_egress.prior_executions[{index}]",
        )
        if actual != expected:
            raise PolicyError(
                "canary_egress.prior_executions must be the exact ordered "
                "attempt-6 evidence list"
            )
        _verify_one_prior_execution(root, evidence)


def _validate_policy(
    fm: dict,
    row: dict,
    runner_uid: str,
    root: Path,
) -> None:
    identity = {
        "uid": POLICY_UID,
        "type": "loop",
        "version": POLICY_VERSION,
        "state": "active",
        "runner": POLICY_RUNNER,
        "execution_mode": "on-demand",
        "realizes_dev_spec": "fe4c17e9",
    }
    for field, expected in identity.items():
        if fm.get(field) != expected:
            raise PolicyError(f"policy {field} must equal {expected!r}")
    if fm.get("status") not in {"draft", "active"}:
        raise PolicyError("policy status must be draft or active")
    for field in ("uid", "type", "version", "state", "status", "runner"):
        if row.get(field) != fm.get(field):
            raise PolicyError(f"policy source/index {field} disagreement")
    if row.get("path") != POLICY_RELATIVE_PATH.as_posix():
        raise PolicyError("policy current-index path is not canonical")

    routes = _closed_object(
        fm.get("model_routes"),
        set(MODEL_ROUTES),
        "model_routes",
    )
    for task, (model, ceiling_nano) in MODEL_ROUTES.items():
        route = _closed_object(
            routes[task],
            {"model", "per_call_ceiling_usd"},
            f"model_routes.{task}",
        )
        if route["model"] != model:
            raise PolicyError(f"model_routes.{task}.model must equal {model}")
        if _usd_to_nano(
            route["per_call_ceiling_usd"],
            f"model_routes.{task}.per_call_ceiling_usd",
        ) != ceiling_nano:
            raise PolicyError(f"model_routes.{task} spend ceiling changed")

    daily = _closed_object(
        fm.get("daily_spend"),
        {"ceiling_usd", "timezone", "scope"},
        "daily_spend",
    )
    if (
        _usd_to_nano(daily["ceiling_usd"], "daily_spend.ceiling_usd")
        != DAILY_CEILING_NANO_USD
        or daily["timezone"] != "UTC"
        or daily["scope"] != "combined"
    ):
        raise PolicyError("daily_spend must retain the locked combined $5 UTC limit")

    # monthly_spend is an optional, backward-compatible addition (D2's $50/month
    # aggregate belt) — absent means no monthly gate applies; present means it
    # must equal exactly the locked $50 combined UTC-month ceiling.
    if "monthly_spend" in fm:
        monthly = _closed_object(
            fm.get("monthly_spend"),
            {"ceiling_usd", "timezone", "scope"},
            "monthly_spend",
        )
        if (
            _usd_to_nano(monthly["ceiling_usd"], "monthly_spend.ceiling_usd")
            != MONTHLY_CEILING_NANO_USD
            or monthly["timezone"] != "UTC"
            or monthly["scope"] != "combined"
        ):
            raise PolicyError(
                "monthly_spend must retain the locked combined $50 UTC-month belt"
            )

    pricing = _closed_object(
        fm.get("pricing_usd_per_mtok"),
        set(PRICING_NANO_USD_PER_TOKEN),
        "pricing_usd_per_mtok",
    )
    for model, expected_rates in PRICING_NANO_USD_PER_TOKEN.items():
        model_prices = _closed_object(
            pricing[model],
            set(expected_rates),
            f"pricing_usd_per_mtok.{model}",
        )
        for field, nano_per_token in expected_rates.items():
            nano_per_mtok = _usd_to_nano(
                model_prices[field],
                f"pricing_usd_per_mtok.{model}.{field}",
            )
            if nano_per_mtok != nano_per_token * 1_000_000:
                raise PolicyError(f"pricing_usd_per_mtok.{model}.{field} changed")
    if fm.get("pricing_source") != PRICING_SOURCE:
        raise PolicyError("pricing_source is not the official locked source")
    request_controls = _closed_object(
        fm.get("request_controls"),
        set(llm.LOCKED_TASK_REQUEST_CONTROLS),
        "request_controls",
    )
    expected_controls = {
        task: dict(controls)
        for task, controls in llm.LOCKED_TASK_REQUEST_CONTROLS.items()
    }
    for task, expected in expected_controls.items():
        actual = _closed_object(
            request_controls[task],
            set(expected),
            f"request_controls.{task}",
        )
        if any(
            type(actual.get(field)) is not type(value)
            or actual.get(field) != value
            for field, value in expected.items()
        ):
            raise PolicyError(f"request_controls.{task} capability drifted")
    response_controls = _closed_object(
        fm.get("response_usage_controls"),
        set(loop_metering.LOCKED_RESPONSE_USAGE_CONTROLS),
        "response_usage_controls",
    )
    expected_response_controls = {
        task: {
            "service_tier": controls["service_tier"],
            "inference_geo_policy": controls["inference_geo_policy"],
        }
        for task, controls in loop_metering.LOCKED_RESPONSE_USAGE_CONTROLS.items()
    }
    for task, expected in expected_response_controls.items():
        actual = _closed_object(
            response_controls[task],
            set(expected),
            f"response_usage_controls.{task}",
        )
        if any(
            type(actual.get(field)) is not type(value)
            or actual.get(field) != value
            for field, value in expected.items()
        ):
            raise PolicyError(f"response_usage_controls.{task} drifted")

    segments = _closed_object(
        fm.get("segment_egress"),
        set(SEGMENT_CLASSES),
        "segment_egress",
    )
    if any(value not in {"ask", "auto", "disabled"} for value in segments.values()):
        raise PolicyError("segment_egress values must be ask, auto, or disabled")
    if fm.get("consent_mode") not in {"ask", "auto", "disabled"}:
        raise PolicyError("consent_mode must be ask, auto, or disabled")
    if type(fm.get("egress_approved")) is not bool:
        raise PolicyError("egress_approved must be boolean")
    approved_by = fm.get("egress_approved_by")
    if approved_by is not None and (
        not isinstance(approved_by, str) or not _UID_RE.fullmatch(approved_by)
    ):
        raise PolicyError("egress_approved_by must be null or a principal UID")

    if (
        fm.get("spend_limits_locked_by") != SPEND_APPROVER_UID
        or fm.get("spend_limits_approval_scope") != "spend-limits-only"
        or fm.get("spend_limits_approval_verbatim") != SPEND_APPROVAL
    ):
        raise PolicyError("human spend-only lock is absent or changed")
    _validate_os_geo_ruling(fm, root)

    canary = _closed_object(
        fm.get("canary_egress"),
        {
            "approved",
            "approved_by",
            "approved_at",
            "approval_scope",
            "approval_verbatim",
            "attempt",
            "prior_attempts",
            "prior_preparations",
            "prior_executions",
            "segment",
            "max_calls",
            "max_reserved_usd",
        },
        "canary_egress",
    )
    expected_canary = {
        "approved": True,
        "approved_by": CANARY_APPROVER_UID,
        "approved_at": CANARY_APPROVED_AT,
        "approval_scope": CANARY_APPROVAL_SCOPE,
        "approval_verbatim": CANARY_APPROVAL,
        "attempt": CANARY_ATTEMPT,
        "segment": CANARY_SEGMENT,
    }
    for field, expected in expected_canary.items():
        if type(canary.get(field)) is not type(expected) or canary.get(field) != expected:
            raise PolicyError(f"canary_egress.{field} must equal {expected!r}")
    _exact_int(canary["max_calls"], CANARY_MAX_CALLS, "canary_egress.max_calls")
    if (
        _usd_to_nano(
            canary["max_reserved_usd"],
            "canary_egress.max_reserved_usd",
        )
        != CANARY_MAX_RESERVED_NANO_USD
    ):
        raise PolicyError("canary_egress.max_reserved_usd must equal the $0.26 lock")
    _verify_prior_attempt_evidence(root, canary)
    _verify_prior_preparation_evidence(root, canary)
    _verify_prior_execution_evidence(root, canary)

    trigger = _closed_object(fm.get("trigger"), {"kind", "spec"}, "trigger")
    if trigger.get("kind") != "manual":
        raise PolicyError("trigger.kind must be manual")
    policy = _closed_object(fm.get("policy"), {"kind", "ref"}, "policy")
    if policy != {"kind": "agentic-tool", "ref": runner_uid}:
        raise PolicyError("policy executor does not bind the registered runner UID")
    tools = fm.get("tools")
    if (
        not isinstance(tools, list)
        or len(tools) != 2
        or set(tools) != {runner_uid, RUNNER_WATCHDOG_UID}
    ):
        raise PolicyError("tools must bind only the runner and loop watchdog UIDs")
    brakes = _closed_object(
        fm.get("brakes"),
        {"max_iterations", "max_budget_usd", "max_wall_clock_min"},
        "brakes",
    )
    _exact_int(brakes["max_iterations"], 2, "brakes.max_iterations")
    _exact_int(brakes["max_wall_clock_min"], 5, "brakes.max_wall_clock_min")
    if _usd_to_nano(brakes["max_budget_usd"], "brakes.max_budget_usd") != (
        DAILY_CEILING_NANO_USD
    ):
        raise PolicyError("brakes.max_budget_usd must equal the $5 lock")
    if fm.get("consequence") != "high":
        raise PolicyError("policy consequence must remain high")


def _canary_passed(fm: dict, runner_uid: str) -> bool:
    value = fm.get("metered_canary")
    if value is None:
        return False
    canary = _closed_object(
        value,
        {
            "passed",
            "policy_uid",
            "policy_version",
            "runner_uid",
            "canary_run_uid",
            "scorecard_sha256",
            "verified_by",
            "verified_at",
            "reserved_nano_usd",
            "actual_nano_usd",
        },
        "metered_canary",
    )
    if type(canary.get("passed")) is not bool:
        raise PolicyError("metered_canary.passed must be boolean")
    expected = {
        "policy_uid": POLICY_UID,
        "policy_version": POLICY_VERSION,
        "runner_uid": runner_uid,
    }
    for field, exact in expected.items():
        if canary.get(field) != exact:
            raise PolicyError(f"metered_canary.{field} must equal {exact!r}")
    for field in ("canary_run_uid", "verified_by"):
        if (
            not isinstance(canary.get(field), str)
            or not _UID_RE.fullmatch(canary[field])
        ):
            raise PolicyError(f"metered_canary.{field} must be 8 lowercase hex")
    if (
        not isinstance(canary.get("scorecard_sha256"), str)
        or not _SHA256_RE.fullmatch(canary["scorecard_sha256"])
    ):
        raise PolicyError("metered_canary.scorecard_sha256 must be lowercase SHA-256")
    if (
        not isinstance(canary.get("verified_at"), str)
        or not _DATE_RE.fullmatch(canary["verified_at"])
    ):
        raise PolicyError("metered_canary.verified_at must be YYYY-MM-DD")
    try:
        if date.fromisoformat(canary["verified_at"]).isoformat() != canary["verified_at"]:
            raise ValueError
    except ValueError as exc:
        raise PolicyError(
            "metered_canary.verified_at must be a canonical calendar date"
        ) from exc
    reserved = _nano_amount(
        canary.get("reserved_nano_usd"),
        "metered_canary.reserved_nano_usd",
        maximum=CANARY_MAX_RESERVED_NANO_USD,
    )
    actual = _nano_amount(
        canary.get("actual_nano_usd"),
        "metered_canary.actual_nano_usd",
        maximum=CANARY_MAX_RESERVED_NANO_USD,
    )
    if actual > reserved:
        raise PolicyError("metered_canary actual spend exceeds reserved spend")
    return canary["passed"]


def _claim_binding(
    *,
    ledger_root: Path,
    policy: DistillerModelPolicy,
    run_uid: str,
    run_dir: Path | str,
    contract_sha256: str,
    require_run_dir: bool,
) -> dict:
    if policy.uid != POLICY_UID or policy.version != POLICY_VERSION:
        raise PolicyError("canary claim policy identity drifted")
    if policy.runner_uid != "6389dcd4":
        raise PolicyError("canary claim runner identity drifted")
    if not isinstance(run_uid, str) or not _UID_RE.fullmatch(run_uid):
        raise PolicyError("canary claim run_uid must be 8 lowercase hex")
    if run_uid in PRIOR_RUN_UIDS:
        raise PolicyError("attempt-7 canary claim requires a fresh run_uid")
    if (
        not isinstance(contract_sha256, str)
        or not _SHA256_RE.fullmatch(contract_sha256)
    ):
        raise PolicyError("canary claim contract_sha256 must be lowercase SHA-256")
    path = Path(run_dir)
    expected_parent = ledger_root.parent
    if (
        not path.is_absolute()
        or path.parent != expected_parent
        or path != expected_parent / path.name
        or path.name in {"", ".", "..", ledger_root.name}
        or _path_has_symlink(path)
    ):
        raise PolicyError("canary claim run_dir must be canonical and non-symlinked")
    if path.exists() or path.is_symlink():
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise PolicyError(f"canary claim run_dir is unavailable: {exc}") from exc
        if resolved != path or not path.is_dir():
            raise PolicyError(
                "canary claim run_dir must be an existing canonical directory"
            )
    elif require_run_dir:
        raise PolicyError("canary claim run_dir is unavailable")
    else:
        try:
            if expected_parent.resolve(strict=True) != expected_parent:
                raise PolicyError("canary claim run parent is not canonical")
        except OSError as exc:
            raise PolicyError(
                f"canary claim run parent is unavailable: {exc}"
            ) from exc
    return {
        "schema_version": 1,
        "policy_uid": policy.uid,
        "policy_version": policy.version,
        "runner_uid": policy.runner_uid,
        "run_uid": run_uid,
        "run_dir": str(path),
        "contract_sha256": contract_sha256,
        "approval_scope": CANARY_APPROVAL_SCOPE,
    }


def _claim_paths(ledger_root: Path | str) -> tuple[Path, Path]:
    root = Path(ledger_root)
    if not root.is_absolute() or _path_has_symlink(root):
        raise PolicyError("canary claim root must be canonical and non-symlinked")
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise PolicyError(f"canary claim root is unavailable: {exc}") from exc
    if resolved != root or not root.is_dir():
        raise PolicyError("canary claim root must be an existing canonical directory")
    return root / CANARY_CLAIM_NAME, root / CANARY_CLAIM_LOCK_NAME


@contextmanager
def _claim_lock(ledger_root: Path | str) -> Iterator[tuple[Path, Path]]:
    claim_path, lock_path = _claim_paths(ledger_root)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise PolicyError(f"canary claim lock is unavailable: {exc}") from exc
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise PolicyError("canary claim lock must be a regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield claim_path, lock_path
    finally:
        os.close(fd)


def _read_claim(path: Path) -> dict:
    if path.is_symlink():
        raise PolicyError(
            "global canary claim must be a regular non-symlinked file"
        )
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise PolicyError(f"global canary claim is unavailable: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise PolicyError("global canary claim must be a regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read()
    finally:
        os.close(fd)
    value = _strict_json_bytes(raw, "global canary claim")
    if _canonical_json_bytes(value) + b"\n" != raw:
        raise PolicyError("global canary claim is not canonical closed JSON")
    return value


def _create_claim(path: Path, value: dict) -> None:
    rendered = _canonical_json_bytes(value) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise PolicyError("global canary authority is already claimed") from exc
    try:
        remaining = memoryview(rendered)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("claim write made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.close(fd)


def claim_canary_authority(
    ledger_root: Path | str,
    *,
    policy: DistillerModelPolicy,
    run_uid: str,
    run_dir: Path | str,
    contract_sha256: str,
) -> dict:
    """Atomically consume fresh v1.8 authority, including an exact claim race."""
    claim_path, _lock_path = _claim_paths(ledger_root)
    expected = _claim_binding(
        ledger_root=claim_path.parent,
        policy=policy,
        run_uid=run_uid,
        run_dir=run_dir,
        contract_sha256=contract_sha256,
        require_run_dir=False,
    )
    # Collision checks are deliberately lock-free and write-free. A preseeded
    # mismatched/symlinked claim must not create even the claim lock.
    if claim_path.exists() or claim_path.is_symlink():
        actual = _read_claim(claim_path)
        if actual != expected:
            raise PolicyError(
                "global v1.8 canary authority is consumed by a different run"
            )
        return actual
    try:
        _create_claim(claim_path, expected)
    except PolicyError:
        # The atomic hard-link is the single-winner operation. A racing loser
        # may resume only when the winner consumed the identical authority.
        if not claim_path.exists() and not claim_path.is_symlink():
            raise
        actual = _read_claim(claim_path)
        if actual != expected:
            raise PolicyError(
                "global v1.8 canary authority is consumed by a different run"
            )
        return actual
    return expected


def verify_exact_canary_claim(
    ledger_root: Path | str,
    *,
    policy: DistillerModelPolicy,
    run_uid: str,
    run_dir: Path | str,
    contract_sha256: str,
) -> dict:
    """Read and exactly verify prepared authority without locking or writing."""
    claim_path, _lock_path = _claim_paths(ledger_root)
    expected = _claim_binding(
        ledger_root=claim_path.parent,
        policy=policy,
        run_uid=run_uid,
        run_dir=run_dir,
        contract_sha256=contract_sha256,
        require_run_dir=True,
    )
    actual = _read_claim(claim_path)
    if actual != expected:
        raise PolicyError("global canary claim does not bind this exact run")
    return dict(actual)


@contextmanager
def locked_canary_claim(
    ledger_root: Path | str,
    *,
    policy: DistillerModelPolicy,
    run_uid: str,
    run_dir: Path | str,
    contract_sha256: str,
) -> Iterator[dict]:
    """Hold the global claim lock while verifying a bound canary operation."""
    claim_path, _lock_path = _claim_paths(ledger_root)
    expected = _claim_binding(
        ledger_root=claim_path.parent,
        policy=policy,
        run_uid=run_uid,
        run_dir=run_dir,
        contract_sha256=contract_sha256,
        require_run_dir=True,
    )
    with _claim_lock(ledger_root) as (claim_path, _lock_path):
        actual = _read_claim(claim_path)
        if actual != expected:
            raise PolicyError("global canary claim does not bind this exact run")
        yield actual


def verify_canary_claim(
    ledger_root: Path | str,
    *,
    policy: DistillerModelPolicy,
    run_uid: str,
    run_dir: Path | str,
    contract_sha256: str,
) -> dict:
    """Verify the globally consumed authority without widening it."""
    with locked_canary_claim(
        ledger_root,
        policy=policy,
        run_uid=run_uid,
        run_dir=run_dir,
        contract_sha256=contract_sha256,
    ) as claim:
        return dict(claim)


def resolve_policy(*, studio_root: Path | str | None = None) -> DistillerModelPolicy:
    """Resolve the fixed UID/path authority; callers cannot override either."""
    root = (
        Path(studio_root).absolute()
        if studio_root is not None
        else Path(__file__).resolve().parents[3]
    )
    source = root / POLICY_RELATIVE_PATH
    index = root / POLICY_INDEX_RELATIVE_PATH
    if _path_has_symlink(source) or source.is_symlink() or not source.is_file():
        raise PolicyError("canonical policy source is missing or symlinked")
    if source.resolve() != (root.resolve() / POLICY_RELATIVE_PATH):
        raise PolicyError("canonical policy source path drifted")
    fm = _read_frontmatter(source)
    rows = _read_current_index(index)
    policy_rows = [row for row in rows if row.get("uid") == POLICY_UID]
    if len(policy_rows) != 1:
        raise PolicyError(
            f"expected one current policy row {POLICY_UID}; found {len(policy_rows)}"
        )
    policy_ref = (
        fm.get("policy", {}).get("ref")
        if type(fm.get("policy")) is dict
        else None
    )
    runner_uid = _registered_runner(rows, root, policy_ref)
    _validate_policy(fm, policy_rows[0], runner_uid, root)

    routes = {
        task: ModelRoute(task, model, ceiling)
        for task, (model, ceiling) in MODEL_ROUTES.items()
    }
    segments = dict(fm["segment_egress"])
    monthly_ceiling_nano_usd = (
        MONTHLY_CEILING_NANO_USD if "monthly_spend" in fm else None
    )
    canary_passed = _canary_passed(fm, runner_uid)
    reasons = []
    if fm["status"] != "active":
        reasons.append("policy is not active")
    if fm["state"] != "active":
        reasons.append("policy state is not active")
    if fm["consent_mode"] != "auto":
        reasons.append("policy consent mode is not auto")
    if fm["egress_approved"] is not True or fm["egress_approved_by"] is None:
        reasons.append("segment egress has no separate human approval")
    if not canary_passed:
        reasons.append("metered canary gate is not passed")
    canary_reasons = []
    production_closed = (
        fm["consent_mode"] == "ask"
        and fm["egress_approved"] is False
        and fm["egress_approved_by"] is None
        and segments == {"os": "ask", "team": "ask", "private": "ask"}
    )
    if not production_closed:
        canary_reasons.append("production authority is not fully closed")
    if canary_passed:
        canary_reasons.append("a passed metered canary is already recorded")
    return DistillerModelPolicy(
        uid=POLICY_UID,
        version=POLICY_VERSION,
        status=fm["status"],
        state=fm["state"],
        runner_name=POLICY_RUNNER,
        runner_uid=runner_uid,
        routes=routes,
        daily_ceiling_nano_usd=DAILY_CEILING_NANO_USD,
        monthly_ceiling_nano_usd=monthly_ceiling_nano_usd,
        segment_egress=segments,
        consent_mode=fm["consent_mode"],
        egress_approved=fm["egress_approved"],
        production_enabled=not reasons,
        disabled_reasons=tuple(reasons),
        source_path=source,
        index_path=index,
        canary_admissible=not canary_reasons,
        canary_disabled_reasons=tuple(canary_reasons),
    )


__all__ = [
    "CANARY_APPROVAL",
    "CANARY_APPROVAL_SCOPE",
    "CANARY_APPROVED_AT",
    "CANARY_APPROVER_UID",
    "CANARY_ATTEMPT",
    "CANARY_CLAIM_LOCK_NAME",
    "CANARY_CLAIM_NAME",
    "CANARY_MAX_CALLS",
    "CANARY_MAX_RESERVED_NANO_USD",
    "CANARY_SEGMENT",
    "DAILY_CEILING_NANO_USD",
    "DistillerModelPolicy",
    "MODEL_ROUTES",
    "MONTHLY_CEILING_NANO_USD",
    "ModelRoute",
    "OS_GEO_EVENT_RELATIVE_PATH",
    "OS_GEO_RULED_BY",
    "OS_GEO_RULING_MESSAGE",
    "OS_GEO_RULING_SCOPE",
    "OS_GEO_SOURCE_EVENT",
    "POLICY_RUNNER",
    "POLICY_UID",
    "POLICY_VERSION",
    "PRIOR_CLAIM_RELATIVE_PATH",
    "PRIOR_CONTRACT_SHA256",
    "PRIOR_LEDGER_DAY",
    "PRIOR_LEDGER_RELATIVE_PATH",
    "PRIOR_POLICY_VERSION",
    "PRIOR_RESERVATION_ID",
    "PRIOR_RETAINED_NANO_USD",
    "PRIOR_RUN_RELATIVE_PATH",
    "PRIOR_RUN_UID",
    "PRIOR_RUN_UIDS",
    "PRIOR_ATTEMPT_RUN_UIDS",
    "PRIOR_EXECUTION_RUN_UIDS",
    "PRIOR_PREPARATION_RUN_UIDS",
    "PRIOR_SCORECARD_RELATIVE_PATH",
    "PRIOR_SCORECARD_SHA256",
    "PRIOR_ATTEMPT_EVIDENCE",
    "PRIOR_EXECUTION_EVIDENCE",
    "PRIOR_PREPARATION_EVIDENCE",
    "PRIOR_RETAINED_TOTAL_NANO_USD",
    "PRIOR_3_CLAIM_RELATIVE_PATH",
    "PRIOR_3_CONTRACT_SHA256",
    "PRIOR_3_LEDGER_RELATIVE_PATH",
    "PRIOR_3_POLICY_VERSION",
    "PRIOR_3_RESERVATION_ID",
    "PRIOR_3_RETAINED_NANO_USD",
    "PRIOR_3_RUN_RELATIVE_PATH",
    "PRIOR_3_RUN_UID",
    "PRIOR_3_SCORECARD_RELATIVE_PATH",
    "PRIOR_3_SCORECARD_SHA256",
    "PRIOR_4_CLAIM_RELATIVE_PATH",
    "PRIOR_4_CONTRACT_SHA256",
    "PRIOR_4_LEDGER_RELATIVE_PATH",
    "PRIOR_4_POLICY_VERSION",
    "PRIOR_4_RESERVATION_ID",
    "PRIOR_4_RETAINED_NANO_USD",
    "PRIOR_4_RUN_RELATIVE_PATH",
    "PRIOR_4_RUN_UID",
    "PRIOR_4_SCORECARD_RELATIVE_PATH",
    "PRIOR_4_SCORECARD_SHA256",
    "PolicyError",
    "claim_canary_authority",
    "locked_canary_claim",
    "resolve_policy",
    "verify_exact_canary_claim",
    "verify_canary_claim",
]
