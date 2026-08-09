"""Cut 4D fixed Distiller canary plants; all provider behavior is doubled."""
from __future__ import annotations

import hashlib
import io
import importlib.util
import inspect
import json
import shutil
import socket
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import daily_spend, llm, metered_model  # noqa: E402
from lib import distiller_model_policy as policy  # noqa: E402
from lib.loop_metering import price_locked_usage_nano_usd  # noqa: E402


ATTEMPT1_HASHES = {
    "vault/loop-runs/.model-spend/2026-07-24.json": (
        "25ce6361b950b9243db45e8c4fb7f4d9ad78dbac2270bf38a7f3794ccb32d2d2"
    ),
    "vault/loop-runs/.model-spend/2026-07-24.lock": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    (
        "vault/loop-runs/.model-spend/"
        "distiller-canary-0c938a95-1.1.0-claim.json"
    ): "086069800b8262cde674b32740d308ba4fe14033639444db1fd8cb4b69eb0b58",
    (
        "vault/loop-runs/.model-spend/"
        "distiller-canary-0c938a95-1.1.0-claim.lock"
    ): "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    (
        "vault/loop-runs/distiller-canary-20260724/"
        "distiller-metered-canary-gateway-receipts.json"
    ): "0279a5c01c5928fcfa0ebf4e006bd8aeca9d2b0a10a6b0880aedc881d81ceca4",
    (
        "vault/loop-runs/distiller-canary-20260724/"
        "distiller-metered-canary-preparation.json"
    ): "b905a8a09beb541c541b1fb3ae8ef8f9c717e00979014dfeb5aa3c65a7287b40",
    (
        "vault/loop-runs/distiller-canary-20260724/"
        "distiller-metered-canary-readiness.json"
    ): "a693fb85c4e0a7e73ebd144daa0be0fc4b644495c51986b252f2c72f5997725a",
    (
        "vault/loop-runs/distiller-canary-20260724/"
        "distiller-metered-canary-scorecard.json"
    ): "a60ac4a34c6339571cd1a32a3c30d0a2a0f779b3073c0ac4fdcab4f1111b84bf",
    "vault/loop-runs/distiller-canary-20260724/gateway_spend.json": (
        "6248495b9a1f0157aa434a26165735306e7c481c672adc53c2b05ba8f726a5c6"
    ),
    "vault/loop-runs/distiller-canary-20260724/run.jsonl": (
        "5f9ea33b4e1dde237b82a8c5d485e361bde3baefe90b360e13bd98508f5ce39f"
    ),
}
ATTEMPT2_HASHES = {
    "vault/loop-runs/.model-spend/2026-07-24@1.2.0.json": (
        "0ae0e035f6af7c2a074860955a7c04b8273088eadb564d9adedc4640acfa7639"
    ),
    "vault/loop-runs/.model-spend/2026-07-24.lock": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    (
        "vault/loop-runs/.model-spend/"
        "distiller-canary-0c938a95-1.2.0-claim.json"
    ): "96d2c5951585386611bf27210ec06b015e3f4108fc5eccbfb40bb6df9f91cacf",
    (
        "vault/loop-runs/.model-spend/"
        "distiller-canary-0c938a95-1.2.0-claim.lock"
    ): "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    (
        "vault/loop-runs/distiller-canary-attempt2-20260724/"
        "distiller-metered-canary-gateway-receipts.json"
    ): "dfe61703249497992ba3e0ca6dbe547b6c3fb16dc586a5e2150256c12914a28f",
    (
        "vault/loop-runs/distiller-canary-attempt2-20260724/"
        "distiller-metered-canary-preparation.json"
    ): "45583704505bfb1b8f990104979bb3d83c1c44b6a397da73b110feb38d8e3176",
    (
        "vault/loop-runs/distiller-canary-attempt2-20260724/"
        "distiller-metered-canary-readiness.json"
    ): "a38e3fdd21e4677e8f039d806f0d59b22818b3ea220977e6ef94cefcf9a6b0e8",
    (
        "vault/loop-runs/distiller-canary-attempt2-20260724/"
        "distiller-metered-canary-scorecard.json"
    ): "888a9242f03866323c85f3eb1ef8579795b110d67b97cb702eb91ae722fa12fd",
    (
        "vault/loop-runs/distiller-canary-attempt2-20260724/gateway_spend.json"
    ): "30ea0bc2545f4636b620654738f8d46011e5a60fd71bfb8e5b77d7126c5eb06c",
    "vault/loop-runs/distiller-canary-attempt2-20260724/run.jsonl": (
        "35db0314f447f4c05508952e3271d9c97759abf63bc65f30b8a5119f835142d0"
    ),
}
ATTEMPT3_HASHES = {
    "vault/loop-runs/.model-spend/2026-07-24@1.3.0.json": (
        "015900b164b6dfd328a8d3410c31e2e2841ff9a451ccc018c7044023117a1d8e"
    ),
    "vault/loop-runs/.model-spend/2026-07-24.lock": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    (
        "vault/loop-runs/.model-spend/"
        "distiller-canary-0c938a95-1.3.0-claim.json"
    ): "e7c92ddeb300b83ee242b757b074ff2edc948058da32e88e787e54291023cd21",
    (
        "vault/loop-runs/.model-spend/"
        "distiller-canary-0c938a95-1.3.0-claim.lock"
    ): "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    (
        "vault/loop-runs/distiller-canary-attempt3-20260724/"
        "distiller-metered-canary-gateway-receipts.json"
    ): "1a84477db2de54c5d69e4bd93cad6b349c6d9af0892e8f72b6eabb70eadb1299",
    (
        "vault/loop-runs/distiller-canary-attempt3-20260724/"
        "distiller-metered-canary-preparation.json"
    ): "0ae5018b5f6784049fe62e9984728b86e683fdbeb177226cb20f41492455c840",
    (
        "vault/loop-runs/distiller-canary-attempt3-20260724/"
        "distiller-metered-canary-readiness.json"
    ): "bede639ddb5a2d3e61e2e8ab9ddc7e1957da3682a1dbea6bc30255dd0c21b191",
    (
        "vault/loop-runs/distiller-canary-attempt3-20260724/"
        "distiller-metered-canary-scorecard.json"
    ): "041140500ceb0eb34261d13643e8f3c2589e9e43d3772b2b5dfbac6fde29f70b",
    (
        "vault/loop-runs/distiller-canary-attempt3-20260724/gateway_spend.json"
    ): "996cb8eca90b6f85b35d69f223b20f195814796a16c2439f0e4d5483cfd5c8e3",
    "vault/loop-runs/distiller-canary-attempt3-20260724/run.jsonl": (
        "e92e1868ea6f8ee75d65fbe72fd89561094c6cc0c8f07230124b918e6837b908"
    ),
}
ATTEMPT4_HASHES = {
    "vault/loop-runs/.model-spend/2026-07-24@1.4.0.json": (
        "50fbf461f674c8b1eebad8491c40cd1b6d249bb81ca4a1b9ef8f81db3ce08b8c"
    ),
    "vault/loop-runs/.model-spend/2026-07-24.lock": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    (
        "vault/loop-runs/.model-spend/"
        "distiller-canary-0c938a95-1.4.0-claim.json"
    ): "bd59879ff381b46cd332ee441d6a3437b698712d42cbbcfc70d222d6554363d4",
    (
        "vault/loop-runs/.model-spend/"
        "distiller-canary-0c938a95-1.4.0-claim.lock"
    ): "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    (
        "vault/loop-runs/distiller-canary-attempt4-20260724/"
        "distiller-metered-canary-gateway-receipts.json"
    ): "6d378fc61bfe13652f39617e982863cef36dedb4f81d96241bf3e4c56d994235",
    (
        "vault/loop-runs/distiller-canary-attempt4-20260724/"
        "distiller-metered-canary-preparation.json"
    ): "170b04879a3cb1896c655463e378a211bde3bb3a875125ad8a2bc815c0db93cc",
    (
        "vault/loop-runs/distiller-canary-attempt4-20260724/"
        "distiller-metered-canary-readiness.json"
    ): "8c89a2759ca648b691bda7aacc52c0192adc49a2025500dfee5a6a13fc69da42",
    (
        "vault/loop-runs/distiller-canary-attempt4-20260724/"
        "distiller-metered-canary-scorecard.json"
    ): "b506e2f804a107e047b5b1508614edb08c02b762c56f54e1cef365900bbf5b7c",
    (
        "vault/loop-runs/distiller-canary-attempt4-20260724/gateway_spend.json"
    ): "6aa40222d985dce81873be1949fbe771f7473929bd7a72d4d02fba0286decb24",
    "vault/loop-runs/distiller-canary-attempt4-20260724/run.jsonl": (
        "bc54a60b1485211d5d93d6c5a062fd6e43da840b6c95bf9f6271fa7eedd12af9"
    ),
}
ATTEMPT6_HASHES = {
    "vault/loop-runs/.model-spend/distiller-canary-0c938a95-1.7.0-claim.json": (
        "631263cbc59f813387627e800e7435b7ea6d5f657da6ec7171f16a6fdece81ca"
    ),
    "vault/loop-runs/.model-spend/distiller-canary-0c938a95-1.7.0-claim.lock": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    "vault/loop-runs/.model-spend/2026-07-25@1.7.0.json": (
        "9dfaeaf9c6a2a73ba60525b7f63e113af2c661d805ca8243a10564054c2dea00"
    ),
    "vault/loop-runs/.model-spend/2026-07-25.lock": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    "vault/loop-runs/distiller-canary-attempt6-20260725/run.jsonl": (
        "140bf05442058362136cc628b708e356f5bdad65c6031694ac4a1d554f679aee"
    ),
    (
        "vault/loop-runs/distiller-canary-attempt6-20260725/"
        "distiller-metered-canary-preparation.json"
    ): "3e99ed069be89bb0cef946bc91571baf76cc6eba763fdbaee0bc7bdbb9e1cd0e",
    (
        "vault/loop-runs/distiller-canary-attempt6-20260725/"
        "distiller-metered-canary-readiness.json"
    ): "57e01e03cf1d07827e793128d98626b1191160c95d3ab7789beb0f5f4342c072",
    (
        "vault/loop-runs/distiller-canary-attempt6-20260725/"
        "distiller-metered-canary-execution-ledger.json"
    ): "8b482b901f15debca578ed11e1a1cdda5789da0da883dbe4dff5d0beccc9dd84",
    (
        "vault/loop-runs/distiller-canary-attempt6-20260725/"
        "distiller-metered-canary-gateway-receipts.json"
    ): "6bef28dae221556c00119668cb65fe8656c9938c85ec9665e20f6d962f2aef10",
    (
        "vault/loop-runs/distiller-canary-attempt6-20260725/"
        ".distiller-metered-canary-gateway-receipts.json.lock"
    ): "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    (
        "vault/loop-runs/distiller-canary-attempt6-20260725/gateway_spend.json"
    ): "96d86d452513551d3f5bdaad821f9c551bedefc71b020f001778845f2e984135",
    (
        "vault/loop-runs/distiller-canary-attempt6-20260725/"
        "distiller-metered-canary-scorecard.json"
    ): "7db939c1e4a1158e802b2aae0102758ed66161daee2c9ad348ee4d616aed1d93",
}
PRIOR_HASHES = {
    **ATTEMPT1_HASHES,
    **ATTEMPT2_HASHES,
    **ATTEMPT3_HASHES,
    **ATTEMPT4_HASHES,
    **ATTEMPT6_HASHES,
}


def _load_target():
    spec = importlib.util.spec_from_file_location(
        "distiller_metered_canary_test_target",
        TOOLS / "tropo-distiller-metered-canary.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


canary = _load_target()
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


class CanaryFixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="distiller_canary_")
        self.root = Path(self.temp.name).resolve()
        (self.root / ".tropo").mkdir()
        (self.root / "vault/files").mkdir(parents=True)
        (self.root / "vault/tools").mkdir(parents=True)
        self.source = self.root / policy.POLICY_RELATIVE_PATH
        self.copy_pre_attestation_policy()
        shutil.copy2(
            ROOT / "vault/tools/6389dcd4.py",
            self.root / "vault/tools/6389dcd4.py",
        )
        ruling_event = self.root / policy.OS_GEO_EVENT_RELATIVE_PATH
        ruling_event.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / policy.OS_GEO_EVENT_RELATIVE_PATH, ruling_event)
        evidence_paths = {
            relative
            for evidence in policy.PRIOR_ATTEMPT_EVIDENCE
            for relative, _sha256 in evidence.evidence_hashes
        }
        evidence_paths.update(
            relative
            for evidence in policy.PRIOR_PREPARATION_EVIDENCE
            for _name, relative, _sha256 in evidence.evidence_hashes
        )
        evidence_paths.update(
            relative
            for evidence in policy.PRIOR_EXECUTION_EVIDENCE
            for _name, relative, _sha256 in evidence.evidence_hashes
        )
        for relative in evidence_paths:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        self.policy_row = {
            "uid": policy.POLICY_UID,
            "type": "loop",
            "version": policy.POLICY_VERSION,
            "state": "active",
            "status": "draft",
            "runner": policy.POLICY_RUNNER,
            "path": policy.POLICY_RELATIVE_PATH.as_posix(),
        }
        self.runner_row = {
            "uid": "6389dcd4",
            "type": "tool",
            "name": policy.POLICY_RUNNER,
            "status": "active",
            "state": "active",
            "transport": "library",
            "implementation_kind": "library",
            "path": "vault/tools/6389dcd4.py",
        }
        self.write_index()
        self.run_dir = self.root / "vault/loop-runs/canary"
        self.calls = []
        self.gateway_nano = 0
        self.response_texts = {
            task: metered_model.canary_expected_response(task)[0]
            for task in metered_model.CANARY_TASKS
        }
        self.reservation_ids = iter(
            ("ca000011", "ca000012", "ca000013", "ca000014")
        )

    def close(self):
        self.temp.cleanup()

    def copy_pre_attestation_policy(self):
        shutil.copy2(ROOT / policy.POLICY_RELATIVE_PATH, self.source)
        text = self.source.read_text(encoding="utf-8")
        _open, raw, body = text.split("---", 2)
        value = yaml.safe_load(raw)
        # Canary-path plants intentionally model the candidate before the live
        # root policy recorded its passed attempt-7 attestation AND before
        # Mike's separate D1-D4 production ruling (v1.9.0) — pin the
        # pre-ruling governance fields explicitly so this fixture never
        # silently drifts with whatever the live root's current production
        # state happens to be.
        value.pop("metered_canary", None)
        value["status"] = "draft"
        value["consent_mode"] = "ask"
        value["segment_egress"] = {"os": "ask", "team": "ask", "private": "ask"}
        value["egress_approved"] = False
        value["egress_approved_by"] = None
        self.source.write_text(
            "---\n"
            + yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
            + "---"
            + body,
            encoding="utf-8",
        )

    def write_index(self):
        path = self.root / "vault/00-index.jsonl"
        path.write_text(
            "".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                for row in (self.policy_row, self.runner_row)
            )
        )

    def resolve(self):
        return policy.resolve_policy(studio_root=self.root)

    def policy_hash(self):
        return hashlib.sha256(
            (self.root / policy.POLICY_RELATIVE_PATH).read_bytes()
        ).hexdigest()

    def provider(self, task, messages, **kwargs):
        context = kwargs["metering_context"]
        self.calls.append(
            {
                "task": task,
                "messages": messages,
                "max_tokens": kwargs["max_tokens"],
                "system": kwargs["system"],
                "context": context,
            }
        )
        usage = {
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "service_tier": "standard",
            "inference_geo": "EU West / 東京?! #1" if task == "parse-query" else "us",
            "output_tokens_details": {"thinking_tokens": 0},
            "server_tool_use": {
                "web_search_requests": 0,
                "web_fetch_requests": 0,
            },
        }
        actual_nano = price_locked_usage_nano_usd(
            llm.LOCKED_TASK_MODELS[task],
            usage,
            task=task,
        )
        self.gateway_nano += actual_nano
        (self.run_dir / "gateway_spend.json").write_text(
            json.dumps({"spent_usd": self.gateway_nano / 1_000_000_000})
            + "\n"
        )
        text = self.response_texts[task]
        receipt_path = self.run_dir / canary.GATEWAY_RECEIPTS_NAME
        surface = json.loads(receipt_path.read_text())
        surface["receipts"].append(
            {
                "reservation_id": context.reservation_id,
                "task": task,
                "model": llm.LOCKED_TASK_MODELS[task],
                "actual_nano_usd": actual_nano,
                "response_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "response_text": text,
                "service_tier": usage["service_tier"],
                "inference_geo": usage["inference_geo"],
            }
        )
        receipt_path.write_text(
            json.dumps(
                surface,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return llm.LockedLLMResponse(
            text=text,
            model=llm.LOCKED_TASK_MODELS[task],
            usage=usage,
        )

    def seed_run(self, *, budget=0.26, run_uid="ca000001"):
        self.run_dir.mkdir(parents=True)
        created, contract = canary._run_events(run_uid)
        contract["brakes"]["max_budget_usd"] = budget
        (self.run_dir / "run.jsonl").write_text(
            json.dumps(created, sort_keys=True, separators=(",", ":"))
            + "\n"
            + json.dumps(contract, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        (self.run_dir / "gateway_spend.json").write_text('{"spent_usd":0.0}\n')

    def mark_ready(self):
        preparation = json.loads(
            (self.run_dir / canary.PREPARATION_NAME).read_text()
        )
        readiness = metered_model.canary_readiness_receipt(
            run_uid=preparation["run_uid"],
            runner_uid="6389dcd4",
            contract_sha256=preparation["contract_sha256"],
        )
        (self.run_dir / canary.READINESS_NAME).write_text(
            json.dumps(readiness, sort_keys=True, separators=(",", ":")) + "\n"
        )
        receipts = metered_model.empty_canary_gateway_receipts(
            run_uid=preparation["run_uid"],
            contract_sha256=preparation["contract_sha256"],
        )
        (self.run_dir / canary.GATEWAY_RECEIPTS_NAME).write_text(
            json.dumps(receipts, sort_keys=True, separators=(",", ":")) + "\n"
        )

    def mutate_policy(self, function):
        source = self.root / policy.POLICY_RELATIVE_PATH
        text = source.read_text()
        _open, raw, body = text.split("---", 2)
        value = yaml.safe_load(raw)
        function(value)
        source.write_text(
            "---\n"
            + yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
            + "---"
            + body
        )

    def invoke(self, provider=None, **kwargs):
        resolver = lambda: policy.resolve_policy(studio_root=self.root)
        selected_provider = provider or self.provider
        run_name = kwargs.get("run_name", "canary")
        target_run = self.root / f"vault/loop-runs/{run_name}"

        def token_hex(_bytes):
            if not (target_run / "run.jsonl").exists():
                return "ca000001" if run_name == "canary" else "ca000002"
            return next(self.reservation_ids)

        with mock.patch.object(canary, "STUDIO_ROOT", self.root):
            with mock.patch.object(
                metered_model,
                "resolve_policy",
                side_effect=resolver,
            ):
                with mock.patch.object(
                    llm,
                    "call_locked",
                    side_effect=selected_provider,
                ):
                    with mock.patch.object(
                        canary.secrets,
                        "token_hex",
                        side_effect=token_hex,
                    ):
                        return canary.run_canary(
                            Path(
                                "vault/loop-runs/"
                                + kwargs.get("run_name", "canary")
                            ),
                            sdk_check=kwargs.get("sdk_check", lambda: None),
                            gateway_check=kwargs.get(
                                "gateway_check",
                                lambda: None,
                            ),
                            monotonic=kwargs.get("monotonic"),
                            environment=kwargs.get("environment", {}),
                            clock=kwargs.get("clock"),
                        )

    def run(self, provider=None, **kwargs):
        prepared = self.invoke(provider, **kwargs)
        if prepared["status"] == "prepared":
            self.mark_ready()
            return self.invoke(provider, **kwargs)
        return prepared


class DistillerMeteredCanaryTests(unittest.TestCase):
    def setUp(self):
        self.fx = CanaryFixture()
        self.addCleanup(self.fx.close)

    def test_all_prior_execution_evidence_trees_are_byte_identical(self):
        actual = {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in PRIOR_HASHES
        }
        self.assertEqual(len(ATTEMPT1_HASHES), 10)
        self.assertEqual(len(ATTEMPT2_HASHES), 10)
        self.assertEqual(len(ATTEMPT3_HASHES), 10)
        self.assertEqual(len(ATTEMPT4_HASHES), 10)
        self.assertEqual(len(ATTEMPT6_HASHES), 12)
        self.assertEqual(len(PRIOR_HASHES), 49)
        self.assertEqual(actual, PRIOR_HASHES)

    def test_raw_and_exact_fenced_responses_normalize_identically_for_both_tasks(self):
        for task in canary.CANARY_TASKS:
            with self.subTest(task=task):
                raw, expected = metered_model.canary_expected_response(task)
                fenced = f"```json\n{raw}\n```"
                raw_body = canary.normalize_response_text(raw, f"{task} response")
                fenced_body = canary.normalize_response_text(
                    fenced,
                    f"{task} response",
                )
                self.assertEqual(raw_body, raw)
                self.assertEqual(fenced_body, raw)
                self.assertEqual(
                    canary._strict_object(raw_body, f"{task} response"),
                    expected,
                )
                self.assertEqual(
                    canary._strict_object(fenced_body, f"{task} response"),
                    expected,
                )
                self.assertIsNone(canary._parse_response(task, raw))
                self.assertIsNone(canary._parse_response(task, fenced))

    def test_response_normalizer_refuses_every_ambiguous_or_heuristic_shape(self):
        raw = '{"uids":["0c938a95"]}'
        refused = {
            "empty": "",
            "raw-leading-space": f" {raw}",
            "raw-trailing-space": f"{raw} ",
            "fence-leading-space": f" ```json\n{raw}\n```",
            "fence-trailing-space": f"```json\n{raw}\n``` ",
            "fence-trailing-newline": f"```json\n{raw}\n```\n",
            "uppercase-tag": f"```JSON\n{raw}\n```",
            "javascript-tag": f"```javascript\n{raw}\n```",
            "bare-fence": f"```\n{raw}\n```",
            "opening-crlf": f"```json\r\n{raw}\n```",
            "closing-crlf": f"```json\n{raw}\r\n```",
            "missing-opening-newline": f"```json{raw}\n```",
            "missing-closing-newline": f"```json\n{raw}```",
            "missing-closing-fence": f"```json\n{raw}",
            "empty-body": "```json\n\n```",
            "body-leading-space": f"```json\n {raw}\n```",
            "body-trailing-space": f"```json\n{raw} \n```",
            "nested-fence": f'```json\n{{"value":"```"}}\n```',
            "multiple-fences": f"```json\n{raw}\n```\n```json\n{raw}\n```",
            "raw-fence": f'{{"value":"```json"}}',
            "prose-before": f"result: {raw}",
            "prose-after": f"{raw}\ndone",
            "array": '["0c938a95"]',
            "string-scalar": '"0c938a95"',
            "number-scalar": "7",
            "null-scalar": "null",
        }
        for label, text in refused.items():
            with self.subTest(label=label):
                with self.assertRaises(canary.DistillerCanaryError):
                    canary.normalize_response_text(text, "response")
        with self.assertRaises(canary.DistillerCanaryError):
            canary.normalize_response_text(None, "response")

    def test_response_normalizer_enforces_exact_4096_utf8_byte_boundary(self):
        raw_at_limit = "{" + ("é" * 2047) + "}"
        self.assertEqual(len(raw_at_limit.encode("utf-8")), 4096)
        self.assertEqual(
            canary.normalize_response_text(raw_at_limit, "response"),
            raw_at_limit,
        )
        with self.assertRaisesRegex(canary.DistillerCanaryError, "4096"):
            canary.normalize_response_text(raw_at_limit[:-1] + "a}", "response")

        body_at_limit = "{" + ("x" * 4082) + "}"
        fenced_at_limit = f"```json\n{body_at_limit}\n```"
        self.assertEqual(len(fenced_at_limit.encode("utf-8")), 4096)
        self.assertEqual(
            canary.normalize_response_text(fenced_at_limit, "response"),
            body_at_limit,
        )
        with self.assertRaisesRegex(canary.DistillerCanaryError, "4096"):
            canary.normalize_response_text(
                f"```json\n{{{'x' * 4083}}}\n```",
                "response",
            )

    def test_strict_semantic_parser_still_refuses_invalid_fenced_objects(self):
        invalid = {
            "malformed": "```json\n{not-json}\n```",
            "duplicate": (
                '```json\n{"uids":["0c938a95"],"uids":["0c938a95"]}\n```'
            ),
            "nonfinite": '```json\n{"uids":[NaN]}\n```',
            "unknown": (
                '```json\n{"uids":["0c938a95"],"unexpected":true}\n```'
            ),
            "wrong-member": '```json\n{"uids":["deadbeef"]}\n```',
        }
        for label, text in invalid.items():
            with self.subTest(label=label):
                with self.assertRaises(canary.DistillerCanaryError):
                    canary._parse_response("parse-query", text)

    def _seed_current_ledger_collision(self, kind, *, fx=None, day=None):
        selected = fx or self.fx
        ledger_root = selected.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        day = day or daily_spend.utc_day()
        ledger_path = daily_spend._ledger_path(
            ledger_root,
            day,
            policy.POLICY_VERSION,
        )
        if kind in {"empty", "foreign-reservation"}:
            daily_spend.initialize_ledger(
                ledger_root,
                policy_uid=policy.POLICY_UID,
                policy_version=policy.POLICY_VERSION,
                daily_ceiling_nano_usd=policy.DAILY_CEILING_NANO_USD,
                day=day,
            )
            if kind == "foreign-reservation":
                daily_spend.reserve(
                    ledger_root,
                    day=day,
                    policy_uid=policy.POLICY_UID,
                    policy_version=policy.POLICY_VERSION,
                    daily_ceiling_nano_usd=policy.DAILY_CEILING_NANO_USD,
                    reservation_id="f4000001",
                    run_uid="f4000002",
                    task="parse-query",
                    model="claude-haiku-4-5-20251001",
                    segment_classes=("os",),
                    worst_case_nano_usd=1_000_000,
                )
        elif kind == "malformed":
            ledger_path.write_bytes(b'{"malformed":true}\n')
        elif kind == "symlink":
            target = selected.root / "foreign-v18-ledger.json"
            target.write_bytes(b'{"foreign":true}\n')
            ledger_path.symlink_to(target)
        else:  # pragma: no cover - test helper guard
            raise AssertionError(f"unknown collision fixture {kind}")
        return ledger_root, ledger_path

    def _assert_fresh_preparation_does_not_inspect_or_mutate_ledger(self, kind):
        ledger_root, ledger_path = self._seed_current_ledger_collision(kind)
        day_lock = ledger_root / f"{daily_spend.utc_day()}.lock"
        ledger_identity = (
            ("symlink", str(ledger_path.readlink()))
            if ledger_path.is_symlink()
            else ("file", hashlib.sha256(ledger_path.read_bytes()).hexdigest())
        )
        lock_preexisting = day_lock.exists() or day_lock.is_symlink()
        lock_hash = (
            hashlib.sha256(day_lock.read_bytes()).hexdigest()
            if day_lock.is_file()
            else None
        )
        with mock.patch.object(
            canary.daily_spend,
            "initialize_ledger",
            wraps=canary.daily_spend.initialize_ledger,
        ) as initialize:
            result = self.fx.invoke()
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(self.fx.calls, [])
        initialize.assert_not_called()
        self.assertTrue(
            (ledger_root / policy.CANARY_CLAIM_NAME).is_file()
        )
        self.assertTrue((self.fx.run_dir / "run.jsonl").is_file())
        self.assertTrue((self.fx.run_dir / canary.PREPARATION_NAME).is_file())
        self.assertFalse((self.fx.run_dir / canary.EXECUTION_LEDGER_NAME).exists())
        self.assertFalse((self.fx.run_dir / canary.SCORECARD_NAME).exists())
        actual_identity = (
            ("symlink", str(ledger_path.readlink()))
            if ledger_path.is_symlink()
            else ("file", hashlib.sha256(ledger_path.read_bytes()).hexdigest())
        )
        self.assertEqual(actual_identity, ledger_identity)
        self.assertEqual(day_lock.exists() or day_lock.is_symlink(), lock_preexisting)
        if lock_hash is not None:
            self.assertEqual(
                hashlib.sha256(day_lock.read_bytes()).hexdigest(),
                lock_hash,
            )

    def test_fresh_preparation_is_ledgerless_with_preexisting_empty_v18_ledger(self):
        self._assert_fresh_preparation_does_not_inspect_or_mutate_ledger("empty")

    def test_fresh_preparation_is_ledgerless_with_foreign_v18_reservation(self):
        self._assert_fresh_preparation_does_not_inspect_or_mutate_ledger(
            "foreign-reservation"
        )

    def test_fresh_preparation_is_ledgerless_with_malformed_v18_ledger(self):
        self.fx.run_dir.mkdir(parents=True)
        self._assert_fresh_preparation_does_not_inspect_or_mutate_ledger("malformed")

    def test_fresh_preparation_is_ledgerless_with_symlinked_v18_ledger(self):
        self._assert_fresh_preparation_does_not_inspect_or_mutate_ledger("symlink")

    def test_fresh_preparation_preserves_both_inert_prior_ledgers_and_claims(self):
        tracked = {
            relative
            for evidence in policy.PRIOR_PREPARATION_EVIDENCE
            for _name, relative, _sha256 in evidence.evidence_hashes
        }
        before = {
            relative: hashlib.sha256((self.fx.root / relative).read_bytes()).hexdigest()
            for relative in tracked
        }
        with mock.patch.object(
            canary.daily_spend,
            "initialize_ledger",
            wraps=canary.daily_spend.initialize_ledger,
        ) as initialize:
            result = self.fx.invoke()
        self.assertEqual(result["status"], "prepared")
        initialize.assert_not_called()
        self.assertEqual(
            {
                relative: hashlib.sha256(
                    (self.fx.root / relative).read_bytes()
                ).hexdigest()
                for relative in tracked
            },
            before,
        )

    def test_execution_refuses_unbound_current_day_ledger_collision_matrix(self):
        for kind in ("empty", "foreign-reservation", "malformed", "symlink"):
            with self.subTest(kind=kind):
                fx = CanaryFixture()
                self.addCleanup(fx.close)
                prepared = fx.invoke()
                self.assertEqual(prepared["status"], "prepared")
                fx.mark_ready()
                _ledger_root, ledger_path = self._seed_current_ledger_collision(
                    kind,
                    fx=fx,
                )
                identity = (
                    ("symlink", str(ledger_path.readlink()))
                    if ledger_path.is_symlink()
                    else ("file", hashlib.sha256(ledger_path.read_bytes()).hexdigest())
                )
                with mock.patch.object(
                    canary.daily_spend,
                    "initialize_ledger",
                    wraps=canary.daily_spend.initialize_ledger,
                ) as initialize:
                    result = fx.invoke()
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["phase"], "execution-ledger")
                initialize.assert_not_called()
                self.assertEqual(fx.calls, [])
                self.assertFalse(
                    (fx.run_dir / canary.EXECUTION_LEDGER_NAME).exists()
                )
                actual = (
                    ("symlink", str(ledger_path.readlink()))
                    if ledger_path.is_symlink()
                    else ("file", hashlib.sha256(ledger_path.read_bytes()).hexdigest())
                )
                self.assertEqual(actual, identity)

    def test_execution_receipt_and_ledger_mutation_matrix_refuses_without_calls(self):
        mutations = (
            "missing-ledger",
            "malformed-receipt",
            "symlinked-receipt",
            "receipt-hash",
            "receipt-day",
            "receipt-path",
            "foreign-reservation",
            "poisoned-ledger",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                fx = CanaryFixture()
                self.addCleanup(fx.close)
                prepared = fx.invoke()
                self.assertEqual(prepared["status"], "prepared")
                fx.mark_ready()
                ledger_root, ledger_path, receipt_path, _receipt = (
                    self._seed_exact_execution_ledger(fx)
                )
                if mutation == "missing-ledger":
                    ledger_path.unlink()
                elif mutation == "malformed-receipt":
                    receipt_path.write_bytes(b'{"malformed":true}\n')
                elif mutation == "symlinked-receipt":
                    target = fx.root / "foreign-execution-receipt.json"
                    target.write_bytes(receipt_path.read_bytes())
                    receipt_path.unlink()
                    receipt_path.symlink_to(target)
                elif mutation in {"receipt-hash", "receipt-day", "receipt-path"}:
                    receipt = json.loads(receipt_path.read_text())
                    if mutation == "receipt-hash":
                        receipt["initial_ledger_sha256"] = "f" * 64
                    elif mutation == "receipt-day":
                        receipt["execution_day"] = "2026-07-23"
                    else:
                        receipt["ledger_relative_path"] = (
                            "vault/loop-runs/.model-spend/foreign.json"
                        )
                    receipt_path.write_text(
                        json.dumps(receipt, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )
                elif mutation == "foreign-reservation":
                    daily_spend.reserve(
                        ledger_root,
                        day=daily_spend.utc_day(),
                        policy_uid=policy.POLICY_UID,
                        policy_version=policy.POLICY_VERSION,
                        daily_ceiling_nano_usd=policy.DAILY_CEILING_NANO_USD,
                        reservation_id="f4000011",
                        run_uid="f4000012",
                        task="parse-query",
                        model="claude-haiku-4-5-20251001",
                        segment_classes=("os",),
                        worst_case_nano_usd=1_000_000,
                    )
                else:
                    ledger = json.loads(ledger_path.read_text())
                    ledger["poisoned"] = True
                    ledger["poison_reason"] = "injected valid poison state"
                    ledger["checksum"] = daily_spend._checksum(ledger)
                    ledger_path.write_text(
                        json.dumps(ledger, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )
                with mock.patch.object(
                    canary.daily_spend,
                    "initialize_ledger",
                    wraps=canary.daily_spend.initialize_ledger,
                ) as initialize:
                    result = fx.invoke()
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["phase"], "execution-ledger")
                self.assertEqual(fx.calls, [])
                initialize.assert_not_called()
                self.assertFalse((fx.run_dir / canary.SCORECARD_NAME).exists())

    def _snapshot_tree(self, root):
        result = {}
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if path.is_symlink():
                result[relative] = ("symlink", str(path.readlink()))
            elif path.is_dir():
                result[relative] = ("directory",)
            else:
                result[relative] = (
                    "file",
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
        return result

    def _seed_exact_execution_ledger(self, fx, *, day=None):
        selected_day = day or daily_spend.utc_day()
        ledger_root = fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        ledger_path = daily_spend._ledger_path(
            ledger_root,
            selected_day,
            policy.POLICY_VERSION,
        )
        daily_spend.initialize_ledger(
            ledger_root,
            policy_uid=policy.POLICY_UID,
            policy_version=policy.POLICY_VERSION,
            daily_ceiling_nano_usd=policy.DAILY_CEILING_NANO_USD,
            day=selected_day,
        )
        preparation = json.loads(
            (fx.run_dir / canary.PREPARATION_NAME).read_text()
        )
        receipt = metered_model.canary_execution_ledger_receipt(
            run_uid=preparation["run_uid"],
            contract_sha256=preparation["contract_sha256"],
            preparation_day=preparation["preparation_day"],
            execution_day=selected_day,
            initial_ledger_sha256=hashlib.sha256(
                ledger_path.read_bytes()
            ).hexdigest(),
        )
        receipt_path = fx.run_dir / canary.EXECUTION_LEDGER_NAME
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
        )
        return ledger_root, ledger_path, receipt_path, receipt

    def _assert_prepared_claim_refusal(self, fx, mutation):
        prepared = fx.invoke()
        self.assertEqual(prepared["status"], "prepared")
        fx.mark_ready()
        ledger_root = fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        claim_path = ledger_root / policy.CANARY_CLAIM_NAME
        claim_lock = ledger_root / policy.CANARY_CLAIM_LOCK_NAME
        raw = claim_path.read_bytes()
        if mutation == "missing":
            claim_path.unlink()
        elif mutation == "symlink":
            target = fx.root / "foreign-prepared-claim.json"
            target.write_bytes(raw)
            claim_path.unlink()
            claim_path.symlink_to(target)
        elif mutation == "directory":
            claim_path.unlink()
            claim_path.mkdir()
        elif mutation == "malformed":
            claim_path.write_bytes(b"not-json\n")
        elif mutation == "partial":
            claim_path.write_bytes(raw[: len(raw) // 2])
        else:
            field, replacement = mutation
            value = json.loads(raw)
            value[field] = replacement
            claim_path.write_text(
                json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
            )
        self.assertFalse(claim_lock.exists())
        self.assertFalse(claim_lock.is_symlink())
        before = self._snapshot_tree(fx.root)
        with ExitStack() as stack:
            claim = stack.enter_context(
                mock.patch.object(
                    canary,
                    "claim_canary_authority",
                    wraps=canary.claim_canary_authority,
                )
            )
            exact = stack.enter_context(
                mock.patch.object(
                    canary,
                    "verify_exact_canary_claim",
                    wraps=canary.verify_exact_canary_claim,
                )
            )
            locked = stack.enter_context(
                mock.patch.object(
                    canary,
                    "locked_canary_claim",
                    wraps=canary.locked_canary_claim,
                )
            )
            write_new = stack.enter_context(
                mock.patch.object(
                    canary,
                    "_write_new",
                    wraps=canary._write_new,
                )
            )
            write_scorecard = stack.enter_context(
                mock.patch.object(
                    canary,
                    "_write_scorecard",
                    wraps=canary._write_scorecard,
                )
            )
            result = fx.invoke()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(fx.calls, [])
        claim.assert_not_called()
        exact.assert_called_once()
        locked.assert_not_called()
        write_new.assert_not_called()
        write_scorecard.assert_not_called()
        self.assertFalse(claim_lock.exists())
        self.assertFalse(claim_lock.is_symlink())
        self.assertEqual(self._snapshot_tree(fx.root), before)

    def test_prepared_claim_deletion_refuses_without_recreation_or_writes(self):
        self._assert_prepared_claim_refusal(self.fx, "missing")

    def test_prepared_claim_symlink_refuses_without_lock_or_writes(self):
        self._assert_prepared_claim_refusal(self.fx, "symlink")

    def test_prepared_claim_nonregular_refuses_without_lock_or_writes(self):
        self._assert_prepared_claim_refusal(self.fx, "directory")

    def test_prepared_claim_malformed_refuses_without_lock_or_writes(self):
        self._assert_prepared_claim_refusal(self.fx, "malformed")

    def test_prepared_claim_partial_refuses_without_lock_or_writes(self):
        self._assert_prepared_claim_refusal(self.fx, "partial")

    def test_prepared_claim_binding_mismatch_refuses_without_lock_or_writes(self):
        mismatches = (
            ("policy_uid", "deadbeef"),
            ("policy_version", "9.9.9"),
            ("run_dir", str(self.fx.root / "vault/loop-runs/other")),
            ("run_uid", "deadbeef"),
            ("contract_sha256", "f" * 64),
            ("approval_scope", "wrong-scope"),
        )
        for index, mismatch in enumerate(mismatches):
            with self.subTest(field=mismatch[0]):
                fx = self.fx if index == 0 else CanaryFixture()
                if fx is not self.fx:
                    self.addCleanup(fx.close)
                self._assert_prepared_claim_refusal(fx, mismatch)

    def test_attempt1_run_uid_preseed_refuses_before_any_attempt7_write(self):
        self.fx.seed_run(run_uid=policy.PRIOR_RUN_UID)
        root_hashes_before = {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in PRIOR_HASHES
        }
        before = {
            path.relative_to(self.fx.root): path.read_bytes()
            for path in self.fx.root.rglob("*")
            if path.is_file()
        }
        with mock.patch.object(
            canary.daily_spend,
            "initialize_ledger",
            wraps=canary.daily_spend.initialize_ledger,
        ) as initialize:
            with mock.patch.object(
                canary,
                "claim_canary_authority",
                wraps=canary.claim_canary_authority,
            ) as claim:
                with mock.patch.object(
                    canary,
                    "_write_new",
                    wraps=canary._write_new,
                ) as write_new:
                    with mock.patch.object(
                        canary,
                        "_write_scorecard",
                        wraps=canary._write_scorecard,
                    ) as write_scorecard:
                        result = self.fx.invoke()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("fresh run_uid", result["error"])
        initialize.assert_not_called()
        claim.assert_not_called()
        write_new.assert_not_called()
        write_scorecard.assert_not_called()
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        current_ledger = daily_spend._ledger_path(
            ledger_root,
            daily_spend.utc_day(),
            policy.POLICY_VERSION,
        )
        current_day_lock = ledger_root / f"{daily_spend.utc_day()}.lock"
        self.assertFalse(current_ledger.exists())
        self.assertFalse((ledger_root / policy.CANARY_CLAIM_NAME).exists())
        self.assertFalse((ledger_root / policy.CANARY_CLAIM_LOCK_NAME).exists())
        self.assertFalse((self.fx.run_dir / canary.PREPARATION_NAME).exists())
        self.assertFalse((self.fx.run_dir / canary.SCORECARD_NAME).exists())
        after = {
            path.relative_to(self.fx.root): path.read_bytes()
            for path in self.fx.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)
        root_hashes_after = {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in PRIOR_HASHES
        }
        self.assertEqual(root_hashes_before, PRIOR_HASHES)
        self.assertEqual(root_hashes_after, root_hashes_before)

    def test_all_other_prior_run_uids_refuse_before_any_attempt7_write(self):
        for run_uid in policy.PRIOR_RUN_UIDS[1:]:
            with self.subTest(run_uid=run_uid):
                fx = CanaryFixture()
                self.addCleanup(fx.close)
                fx.seed_run(run_uid=run_uid)
                before = {
                    path.relative_to(fx.root): path.read_bytes()
                    for path in fx.root.rglob("*")
                    if path.is_file()
                }
                with mock.patch.object(
                    canary.daily_spend,
                    "initialize_ledger",
                    wraps=canary.daily_spend.initialize_ledger,
                ) as initialize:
                    with mock.patch.object(
                        canary,
                        "claim_canary_authority",
                        wraps=canary.claim_canary_authority,
                    ) as claim:
                        with mock.patch.object(
                            canary,
                            "_write_new",
                            wraps=canary._write_new,
                        ) as write_new:
                            result = fx.invoke()
                self.assertEqual(result["status"], "blocked")
                self.assertIn("fresh run_uid", result["error"])
                initialize.assert_not_called()
                claim.assert_not_called()
                write_new.assert_not_called()
                after = {
                    path.relative_to(fx.root): path.read_bytes()
                    for path in fx.root.rglob("*")
                    if path.is_file()
                }
                self.assertEqual(after, before)

    def test_each_prior_claim_collision_has_zero_attempt7_side_effects(self):
        for evidence in (
            *policy.PRIOR_ATTEMPT_EVIDENCE,
            *policy.PRIOR_PREPARATION_EVIDENCE,
            *policy.PRIOR_EXECUTION_EVIDENCE,
        ):
            with self.subTest(version=evidence.policy_version):
                fx = CanaryFixture()
                self.addCleanup(fx.close)
                ledger_root = fx.root / evidence.ledger_path.parent
                current_claim = ledger_root / policy.CANARY_CLAIM_NAME
                shutil.copy2(fx.root / evidence.claim_path, current_claim)

                def snapshot():
                    return {
                        path.relative_to(fx.root): (
                            "directory" if path.is_dir() else path.read_bytes()
                        )
                        for path in fx.root.rglob("*")
                    }

                before = snapshot()
                with mock.patch.object(
                    canary,
                    "_materialize_run",
                    wraps=canary._materialize_run,
                ) as materialize:
                    with mock.patch.object(
                        canary,
                        "_initialize_or_verify_execution_ledger",
                        wraps=canary._initialize_or_verify_execution_ledger,
                    ) as initialize:
                        with mock.patch.object(
                            canary,
                            "_write_new",
                            wraps=canary._write_new,
                        ) as write_new:
                            result = fx.invoke()
                self.assertEqual(result["status"], "blocked")
                self.assertIn("different run", result["error"])
                materialize.assert_not_called()
                initialize.assert_not_called()
                write_new.assert_not_called()
                self.assertEqual(snapshot(), before)
                self.assertFalse(
                    (ledger_root / policy.CANARY_CLAIM_LOCK_NAME).exists()
                )
                self.assertFalse(fx.run_dir.exists())
                self.assertFalse(
                    daily_spend._ledger_path(
                        ledger_root,
                        daily_spend.utc_day(),
                        policy.POLICY_VERSION,
                    ).exists()
                )

    def test_fresh_preparation_consumes_claim_before_run_ledger_and_receipt(self):
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        current_ledger = daily_spend._ledger_path(
            ledger_root,
            daily_spend.utc_day(),
            policy.POLICY_VERSION,
        )
        current_day_lock = ledger_root / f"{daily_spend.utc_day()}.lock"
        day_lock_before = (
            current_day_lock.read_bytes() if current_day_lock.is_file() else None
        )
        events = []
        original_create_claim = policy._create_claim
        original_materialize = canary._materialize_run
        original_write_new = canary._write_new

        def create_claim(path, value):
            entries_before = set(ledger_root.iterdir())
            self.assertFalse(self.fx.run_dir.exists())
            self.assertFalse(current_ledger.exists())
            self.assertEqual(
                current_day_lock.read_bytes()
                if current_day_lock.is_file()
                else None,
                day_lock_before,
            )
            self.assertFalse(
                (ledger_root / policy.CANARY_CLAIM_LOCK_NAME).exists()
            )
            result = original_create_claim(path, value)
            self.assertTrue(path.is_file())
            self.assertEqual(
                set(ledger_root.iterdir()) - entries_before,
                {path},
            )
            self.assertFalse(
                (ledger_root / policy.CANARY_CLAIM_LOCK_NAME).exists()
            )
            self.assertFalse(self.fx.run_dir.exists())
            self.assertFalse(current_ledger.exists())
            self.assertEqual(
                current_day_lock.read_bytes()
                if current_day_lock.is_file()
                else None,
                day_lock_before,
            )
            self.assertFalse(
                any(
                    item.name.startswith(f".{path.name}.")
                    for item in ledger_root.iterdir()
                )
            )
            events.append("claim")
            return result

        def materialize(*args, **kwargs):
            self.assertTrue((ledger_root / policy.CANARY_CLAIM_NAME).is_file())
            self.assertFalse(current_ledger.exists())
            events.append("materialize")
            return original_materialize(*args, **kwargs)

        def write_new(path, raw):
            events.append(f"write:{path.name}")
            return original_write_new(path, raw)

        with mock.patch.object(policy, "_create_claim", side_effect=create_claim):
            with mock.patch.object(
                canary,
                "_materialize_run",
                side_effect=materialize,
            ):
                with mock.patch.object(
                    canary.daily_spend,
                    "initialize_ledger",
                    wraps=canary.daily_spend.initialize_ledger,
                ) as initialize:
                    with mock.patch.object(
                        canary,
                        "_write_new",
                        side_effect=write_new,
                    ):
                        result = self.fx.invoke()
        self.assertEqual(result["status"], "prepared")
        initialize.assert_not_called()
        self.assertEqual(
            events,
            [
                "claim",
                "materialize",
                "write:run.jsonl",
                "write:gateway_spend.json",
                f"write:{canary.PREPARATION_NAME}",
            ],
        )
        claim_lock = ledger_root / policy.CANARY_CLAIM_LOCK_NAME
        self.assertFalse(claim_lock.exists())
        self.assertEqual(
            current_day_lock.read_bytes()
            if current_day_lock.is_file()
            else None,
            day_lock_before,
        )
        self.assertFalse(current_ledger.exists())
        self.fx.mark_ready()
        completed = self.fx.invoke()
        self.assertEqual(completed["status"], "pass")
        self.assertTrue(claim_lock.is_file())
        self.assertTrue(current_ledger.is_file())

    def test_fresh_materialization_calls_claim_authority_exactly_once(self):
        with mock.patch.object(
            canary,
            "claim_canary_authority",
            wraps=canary.claim_canary_authority,
        ) as claim:
            with mock.patch.object(
                canary,
                "verify_exact_canary_claim",
                wraps=canary.verify_exact_canary_claim,
            ) as exact:
                prepared = self.fx.invoke()
        self.assertEqual(prepared["status"], "prepared")
        claim.assert_called_once()
        exact.assert_not_called()

    def test_prepared_continuation_initializes_exact_v18_ledger_only_at_execution(self):
        prepared = self.fx.invoke()
        self.assertEqual(prepared["status"], "prepared")
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        ledger_path = daily_spend._ledger_path(
            ledger_root,
            daily_spend.utc_day(),
            policy.POLICY_VERSION,
        )
        stable_paths = (
            ledger_root / policy.CANARY_CLAIM_NAME,
            self.fx.run_dir / "run.jsonl",
            self.fx.run_dir / canary.PREPARATION_NAME,
        )
        stable_hashes = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in stable_paths
        }
        self.assertFalse(ledger_path.exists())
        self.assertFalse(ledger_path.is_symlink())
        self.assertFalse(
            (self.fx.run_dir / canary.EXECUTION_LEDGER_NAME).exists()
        )
        self.fx.mark_ready()
        claim_lock = ledger_root / policy.CANARY_CLAIM_LOCK_NAME
        original_exact = canary.verify_exact_canary_claim
        original_locked = canary.locked_canary_claim
        verification_order = []

        def exact(*args, **kwargs):
            self.assertFalse(claim_lock.exists())
            verification_order.append("read-only")
            return original_exact(*args, **kwargs)

        def locked(*args, **kwargs):
            @contextmanager
            def wrapper():
                self.assertEqual(verification_order, ["read-only"])
                self.assertFalse(claim_lock.exists())
                verification_order.append("locked")
                with original_locked(*args, **kwargs) as claim:
                    yield claim

            return wrapper()

        with ExitStack() as stack:
            claim = stack.enter_context(
                mock.patch.object(
                    canary,
                    "claim_canary_authority",
                    wraps=canary.claim_canary_authority,
                )
            )
            exact_verifier = stack.enter_context(
                mock.patch.object(
                    canary,
                    "verify_exact_canary_claim",
                    side_effect=exact,
                )
            )
            locked_verifier = stack.enter_context(
                mock.patch.object(
                    canary,
                    "locked_canary_claim",
                    side_effect=locked,
                )
            )
            initialize = stack.enter_context(
                mock.patch.object(
                    canary.daily_spend,
                    "initialize_ledger",
                    wraps=canary.daily_spend.initialize_ledger,
                )
            )
            completed = self.fx.invoke()
        self.assertEqual(completed["status"], "pass")
        self.assertEqual(
            [call["task"] for call in self.fx.calls],
            ["parse-query", "distill"],
        )
        claim.assert_not_called()
        exact_verifier.assert_called_once()
        locked_verifier.assert_called_once()
        self.assertEqual(verification_order, ["read-only", "locked"])
        initialize.assert_called_once()
        self.assertTrue(ledger_path.is_file())
        self.assertTrue(
            (self.fx.run_dir / canary.EXECUTION_LEDGER_NAME).is_file()
        )
        self.assertEqual(
            {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in stable_paths
            },
            stable_hashes,
        )

    def test_prepared_continuation_refuses_foreign_run_in_v18_ledger(self):
        prepared = self.fx.invoke()
        self.assertEqual(prepared["status"], "prepared")
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        day = daily_spend.utc_day()
        ledger_path = daily_spend._ledger_path(
            ledger_root,
            day,
            policy.POLICY_VERSION,
        )
        daily_spend.initialize_ledger(
            ledger_root,
            policy_uid=policy.POLICY_UID,
            policy_version=policy.POLICY_VERSION,
            daily_ceiling_nano_usd=policy.DAILY_CEILING_NANO_USD,
            day=day,
        )
        daily_spend.reserve(
            ledger_root,
            day=day,
            policy_uid=policy.POLICY_UID,
            policy_version=policy.POLICY_VERSION,
            daily_ceiling_nano_usd=policy.DAILY_CEILING_NANO_USD,
            reservation_id="f4000003",
            run_uid="f4000004",
            task="parse-query",
            model="claude-haiku-4-5-20251001",
            segment_classes=("os",),
            worst_case_nano_usd=1_000_000,
        )
        ledger_hash = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
        self.fx.mark_ready()
        result = self.fx.invoke()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("foreign run", result["error"])
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(
            hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
            ledger_hash,
        )
        self.assertFalse((self.fx.run_dir / canary.SCORECARD_NAME).exists())
        self.assertFalse(
            (self.fx.run_dir / canary.EXECUTION_LEDGER_NAME).exists()
        )

    def test_cross_day_prepare_and_execute_creates_only_execution_day_ledger(self):
        execution_time = datetime.now(timezone.utc)
        preparation_time = execution_time - timedelta(days=1)
        preparation_day = daily_spend.utc_day(preparation_time)
        execution_day = daily_spend.utc_day(execution_time)
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        preparation_ledger = daily_spend._ledger_path(
            ledger_root,
            preparation_day,
            policy.POLICY_VERSION,
        )
        execution_ledger = daily_spend._ledger_path(
            ledger_root,
            execution_day,
            policy.POLICY_VERSION,
        )

        prepared = self.fx.invoke(clock=lambda: preparation_time)
        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(prepared["preparation_day"], preparation_day)
        self.assertFalse(preparation_ledger.exists())
        self.assertFalse(execution_ledger.exists())
        self.fx.mark_ready()
        completed = self.fx.invoke(clock=lambda: execution_time)

        self.assertEqual(completed["status"], "pass")
        self.assertEqual(completed["preparation_day"], preparation_day)
        self.assertEqual(completed["execution_day"], execution_day)
        self.assertFalse(preparation_ledger.exists())
        self.assertFalse(preparation_ledger.is_symlink())
        self.assertTrue(execution_ledger.is_file())
        self.assertEqual(
            completed["execution_ledger"]["ledger_relative_path"],
            execution_ledger.relative_to(self.fx.root).as_posix(),
        )

    def test_day_rollover_after_execution_ledger_init_consumes_authority(self):
        preparation_time = datetime(2026, 7, 24, 23, 59, tzinfo=timezone.utc)
        execution_time = datetime(2026, 7, 25, 23, 59, tzinfo=timezone.utc)
        rolled_time = datetime(2026, 7, 26, 0, 0, tzinfo=timezone.utc)
        prepared = self.fx.invoke(clock=lambda: preparation_time)
        self.assertEqual(prepared["status"], "prepared")
        self.fx.mark_ready()
        execution_clock = iter((execution_time, execution_time, rolled_time))

        failed = self.fx.invoke(clock=lambda: next(execution_clock))

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["phase"], "calls")
        self.assertEqual(failed["preparation_day"], "2026-07-24")
        self.assertEqual(failed["execution_day"], "2026-07-25")
        self.assertIn("UTC day rolled over", failed["error"])
        self.assertEqual(self.fx.calls, [])
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        execution_ledger = daily_spend._ledger_path(
            ledger_root,
            "2026-07-25",
            policy.POLICY_VERSION,
        )
        self.assertTrue(execution_ledger.is_file())
        self.assertTrue(
            (self.fx.run_dir / canary.EXECUTION_LEDGER_NAME).is_file()
        )
        self.assertEqual(
            daily_spend.read_ledger(
                ledger_root,
                day="2026-07-25",
                policy_uid=policy.POLICY_UID,
                policy_version=policy.POLICY_VERSION,
                daily_ceiling_nano_usd=policy.DAILY_CEILING_NANO_USD,
            )["reservations"],
            {},
        )
        self.assertFalse(
            daily_spend._ledger_path(
                ledger_root,
                "2026-07-26",
                policy.POLICY_VERSION,
            ).exists()
        )
        retry = self.fx.invoke(clock=lambda: rolled_time)
        self.assertEqual(retry["status"], "blocked")
        self.assertIn("already has a scorecard", retry["error"])
        self.assertEqual(self.fx.calls, [])

    def test_execution_ledger_creation_race_consumes_authority_without_call(self):
        prepared = self.fx.invoke()
        self.assertEqual(prepared["status"], "prepared")
        self.fx.mark_ready()
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        day = daily_spend.utc_day()
        ledger_path = daily_spend._ledger_path(
            ledger_root,
            day,
            policy.POLICY_VERSION,
        )
        claim_path = ledger_root / policy.CANARY_CLAIM_NAME
        claim_lock = ledger_root / policy.CANARY_CLAIM_LOCK_NAME
        original_write_new_locked = daily_spend._write_new_locked
        race_hash = {}
        raced = False

        def race_at_atomic_ledger_create(path, ledger):
            nonlocal raced
            if raced:
                return original_write_new_locked(path, ledger)
            raced = True
            self.assertTrue(claim_path.is_file())
            self.assertTrue(claim_lock.is_file())
            original_write_new_locked(path, dict(ledger))
            race_hash["ledger"] = hashlib.sha256(
                ledger_path.read_bytes()
            ).hexdigest()
            return original_write_new_locked(path, ledger)

        with mock.patch.object(
            daily_spend,
            "_write_new_locked",
            side_effect=race_at_atomic_ledger_create,
        ):
            first = self.fx.invoke()
        self.assertEqual(first["status"], "blocked")
        self.assertEqual(first["phase"], "execution-ledger")
        self.assertIn("daily ledger creation failed", first["error"])
        self.assertEqual(self.fx.calls, [])
        self.assertTrue(claim_path.is_file())
        claim_hash = hashlib.sha256(claim_path.read_bytes()).hexdigest()
        self.assertEqual(
            hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
            race_hash["ledger"],
        )
        self.assertTrue((self.fx.run_dir / "run.jsonl").is_file())
        self.assertTrue((self.fx.run_dir / "gateway_spend.json").is_file())
        self.assertTrue((self.fx.run_dir / canary.PREPARATION_NAME).is_file())
        self.assertFalse(
            (self.fx.run_dir / canary.EXECUTION_LEDGER_NAME).exists()
        )
        self.assertFalse((self.fx.run_dir / canary.SCORECARD_NAME).exists())
        self.assertTrue(claim_lock.is_file())

        second = self.fx.invoke()
        self.assertEqual(second["status"], "blocked")
        self.assertEqual(second["phase"], "execution-ledger")
        self.assertIn("no exact execution-ledger receipt", second["error"])
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(
            hashlib.sha256(claim_path.read_bytes()).hexdigest(),
            claim_hash,
        )
        self.assertEqual(
            hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
            race_hash["ledger"],
        )

    def test_failure_after_fresh_claim_consumes_authority_without_retry(self):
        with mock.patch.object(
            canary,
            "_materialize_run",
            side_effect=OSError("injected materialization failure"),
        ) as materialize:
            first = self.fx.invoke()
        self.assertEqual(first["status"], "blocked")
        self.assertIn("injected materialization failure", first["error"])
        self.assertEqual(materialize.call_count, 1)
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        self.assertTrue((ledger_root / policy.CANARY_CLAIM_NAME).is_file())
        self.assertFalse(
            (ledger_root / policy.CANARY_CLAIM_LOCK_NAME).exists()
        )
        self.assertFalse(self.fx.run_dir.exists())

        with mock.patch.object(
            canary,
            "_materialize_run",
            wraps=canary._materialize_run,
        ) as retry_materialize:
            second = self.fx.invoke()
        self.assertEqual(second["status"], "blocked")
        self.assertIn("automatic retry is forbidden", second["error"])
        retry_materialize.assert_not_called()
        self.assertFalse(
            (ledger_root / policy.CANARY_CLAIM_LOCK_NAME).exists()
        )

    def test_partial_claim_write_consumes_authority_and_retry_fails_closed(self):
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        claim_path = ledger_root / policy.CANARY_CLAIM_NAME
        claim_lock = ledger_root / policy.CANARY_CLAIM_LOCK_NAME
        current_ledger = daily_spend._ledger_path(
            ledger_root,
            daily_spend.utc_day(),
            policy.POLICY_VERSION,
        )
        original_write = policy.os.write
        injected = False

        def partial_write(descriptor, value):
            nonlocal injected
            if not injected:
                injected = True
                raw = bytes(value)
                original_write(descriptor, raw[: max(1, len(raw) // 4)])
                raise OSError("injected partial claim write")
            return original_write(descriptor, value)

        with mock.patch.object(policy.os, "write", side_effect=partial_write):
            first = self.fx.invoke()
        self.assertEqual(first["status"], "blocked")
        self.assertIn("injected partial claim write", first["error"])
        self.assertTrue(claim_path.is_file())
        with self.assertRaises(policy.PolicyError):
            policy._read_claim(claim_path)
        self.assertFalse(claim_lock.exists())
        self.assertFalse(current_ledger.exists())
        self.assertFalse(self.fx.run_dir.exists())
        self.assertFalse(
            any(
                item.name.startswith(f".{claim_path.name}.")
                for item in ledger_root.iterdir()
            )
        )

        def snapshot():
            return {
                path.relative_to(self.fx.root): (
                    "directory" if path.is_dir() else path.read_bytes()
                )
                for path in self.fx.root.rglob("*")
            }

        after_failure = snapshot()
        second = self.fx.invoke()
        self.assertEqual(second["status"], "blocked")
        self.assertIn("global canary claim is malformed", second["error"])
        self.assertEqual(snapshot(), after_failure)
        self.assertFalse(claim_lock.exists())
        self.assertFalse(current_ledger.exists())
        self.assertFalse(self.fx.run_dir.exists())

    def test_attempt1_contract_hash_mutations_block_canary_before_side_effects(self):
        for label in ("claim", "run-contract", "scorecard"):
            with self.subTest(label=label):
                fx = CanaryFixture()
                self.addCleanup(fx.close)
                if label == "claim":
                    path = fx.root / policy.PRIOR_CLAIM_RELATIVE_PATH
                    value = json.loads(path.read_text())
                    value["contract_sha256"] = "f" * 64
                elif label == "run-contract":
                    path = fx.root / policy.PRIOR_RUN_RELATIVE_PATH
                    events = [
                        json.loads(line)
                        for line in path.read_text().splitlines()
                    ]
                    events[1]["brakes"]["max_iterations"] = 3
                    path.write_text(
                        "".join(
                            json.dumps(
                                event,
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                            + "\n"
                            for event in events
                        )
                    )
                    value = None
                else:
                    path = fx.root / policy.PRIOR_SCORECARD_RELATIVE_PATH
                    value = json.loads(path.read_text())
                    value["run"]["contract_sha256"] = "f" * 64
                if value is not None:
                    path.write_text(
                        json.dumps(value, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )
                before = {
                    item.relative_to(fx.root): item.read_bytes()
                    for item in fx.root.rglob("*")
                    if item.is_file()
                }
                with mock.patch.object(
                    canary,
                    "_ensure_run",
                    wraps=canary._ensure_run,
                ) as ensure_run:
                    with mock.patch.object(
                        canary.daily_spend,
                        "initialize_ledger",
                        wraps=canary.daily_spend.initialize_ledger,
                    ) as initialize:
                        with mock.patch.object(
                            canary,
                            "claim_canary_authority",
                            wraps=canary.claim_canary_authority,
                        ) as claim:
                            result = fx.invoke()
                self.assertEqual(result["status"], "blocked")
                self.assertIn("attempt-1", result["error"])
                self.assertEqual(fx.calls, [])
                ensure_run.assert_not_called()
                initialize.assert_not_called()
                claim.assert_not_called()
                after = {
                    item.relative_to(fx.root): item.read_bytes()
                    for item in fx.root.rglob("*")
                    if item.is_file()
                }
                self.assertEqual(after, before)
                self.assertFalse(fx.run_dir.exists())

    def test_attempt2_through_4_mutations_block_canary_before_side_effects(self):
        for evidence in policy.PRIOR_ATTEMPT_EVIDENCE[1:]:
            for label, relative in (
                ("claim", evidence.claim_path),
                ("run-contract", evidence.run_path),
                (
                    "scorecard",
                    next(
                        path
                        for path, _sha256 in evidence.evidence_hashes
                        if path.name
                        == "distiller-metered-canary-scorecard.json"
                    ),
                ),
            ):
                with self.subTest(attempt=evidence.attempt, label=label):
                    fx = CanaryFixture()
                    self.addCleanup(fx.close)
                    path = fx.root / relative
                    path.write_bytes(path.read_bytes() + b"x")
                    before = {
                        item.relative_to(fx.root): item.read_bytes()
                        for item in fx.root.rglob("*")
                        if item.is_file()
                    }
                    with mock.patch.object(
                        canary,
                        "_ensure_run",
                        wraps=canary._ensure_run,
                    ) as ensure_run:
                        with mock.patch.object(
                            canary.daily_spend,
                            "initialize_ledger",
                            wraps=canary.daily_spend.initialize_ledger,
                        ) as initialize:
                            result = fx.invoke()
                    self.assertEqual(result["status"], "blocked")
                    self.assertIn(f"attempt-{evidence.attempt}", result["error"])
                    ensure_run.assert_not_called()
                    initialize.assert_not_called()
                    self.assertEqual(fx.calls, [])
                    after = {
                        item.relative_to(fx.root): item.read_bytes()
                        for item in fx.root.rglob("*")
                        if item.is_file()
                    }
                    self.assertEqual(after, before)

    def test_pass_runs_exact_fixed_tasks_and_writes_closed_scorecard(self):
        before = self.fx.policy_hash()
        scorecard = self.fx.run()
        self.assertEqual(scorecard["status"], "pass")
        self.assertEqual(scorecard["phase"], "score")
        self.assertEqual(
            set(scorecard),
            {
                "schema_version",
                "mode",
                "status",
                "phase",
                "policy",
                "run",
                "receipts",
                "gateway_receipts",
                "reserved_nano_usd",
                "actual_nano_usd",
                "gateway_spend_usd",
                "preparation_day",
                "execution_day",
                "execution_ledger",
                "execution_ledger_receipt_sha256",
                "error",
            },
        )
        self.assertEqual(scorecard["policy"]["version"], policy.POLICY_VERSION)
        self.assertFalse(scorecard["policy"]["production_enabled"])
        self.assertTrue(scorecard["policy"]["canary_admissible"])
        self.assertEqual(scorecard["run"]["uid"], "ca000001")
        self.assertEqual(
            scorecard["run"]["request_sha256"],
            metered_model.canary_request_hashes(),
        )
        self.assertEqual(
            scorecard["run"]["request_sha256"],
            {
                "parse-query": (
                    "0e1f56e65d48d38eb7f8e2d844407752306426613a8cd5ea4289c1a583ff5454"
                ),
                "distill": (
                    "1a6765fd1317aeab230546e6d642e724871b939efdcad716b4a028f01aa06b2c"
                ),
            },
        )
        for task in metered_model.CANARY_TASKS:
            projection = metered_model.canary_request_projection(task)
            self.assertEqual(projection["service_tier"], "standard_only")
            if task == "parse-query":
                self.assertNotIn("inference_geo", projection)
            else:
                self.assertEqual(projection["inference_geo"], "global")
        self.assertEqual(len(scorecard["run"]["contract_sha256"]), 64)
        self.assertEqual(scorecard["preparation_day"], daily_spend.utc_day())
        self.assertEqual(scorecard["execution_day"], daily_spend.utc_day())
        self.assertEqual(
            set(scorecard["execution_ledger"]),
            {
                "schema_version",
                "status",
                "policy_uid",
                "policy_version",
                "run_uid",
                "contract_sha256",
                "preparation_day",
                "execution_day",
                "ledger_relative_path",
                "initial_ledger_sha256",
            },
        )
        execution_receipt_path = (
            self.fx.run_dir / canary.EXECUTION_LEDGER_NAME
        )
        self.assertEqual(
            hashlib.sha256(execution_receipt_path.read_bytes()).hexdigest(),
            scorecard["execution_ledger_receipt_sha256"],
        )
        self.assertEqual(
            metered_model.verify_canary_execution_ledger(
                run_dir=self.fx.run_dir,
                ledger_root=(
                    self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
                ),
                policy=self.fx.resolve(),
                run_uid=scorecard["run"]["uid"],
                contract_sha256=scorecard["run"]["contract_sha256"],
            ),
            scorecard["execution_ledger"],
        )
        self.assertEqual(
            [receipt["task"] for receipt in scorecard["receipts"]],
            ["parse-query", "distill"],
        )
        self.assertTrue(
            all(
                set(receipt)
                == {
                    "task",
                    "status",
                    "reservation_id",
                    "reserved_nano_usd",
                    "actual_nano_usd",
                    "reservation_status",
                    "worst_case_retained",
                    "response_sha256",
                    "response_text",
                    "response_service_tier",
                    "response_inference_geo",
                    "error",
                }
                for receipt in scorecard["receipts"]
            )
        )
        self.assertTrue(
            all(
                set(receipt)
                == {
                    "reservation_id",
                    "task",
                    "model",
                    "actual_nano_usd",
                    "response_sha256",
                    "response_text",
                    "service_tier",
                    "inference_geo",
                }
                for receipt in scorecard["gateway_receipts"]
            )
        )
        self.assertTrue(
            all(receipt["status"] == "pass" for receipt in scorecard["receipts"])
        )
        self.assertTrue(
            all(
                len(receipt["response_sha256"]) == 64
                for receipt in scorecard["receipts"]
            )
        )
        self.assertEqual(
            [
                (
                    receipt["response_service_tier"],
                    receipt["response_inference_geo"],
                )
                for receipt in scorecard["receipts"]
            ],
            [("standard", "EU West / 東京?! #1"), ("standard", "us")],
        )
        self.assertEqual(
            [
                (receipt["service_tier"], receipt["inference_geo"])
                for receipt in scorecard["gateway_receipts"]
            ],
            [("standard", "EU West / 東京?! #1"), ("standard", "us")],
        )
        self.assertLessEqual(
            scorecard["reserved_nano_usd"],
            policy.CANARY_MAX_RESERVED_NANO_USD,
        )
        self.assertEqual(
            scorecard["actual_nano_usd"],
            sum(
                receipt["actual_nano_usd"]
                for receipt in scorecard["gateway_receipts"]
            ),
        )
        self.assertEqual(
            [receipt["response_text"] for receipt in scorecard["receipts"]],
            [
                '{"uids":["0c938a95"]}',
                (
                    '{"selections":[{"source_uid":"0c938a95",'
                    '"span_anchor":"frontmatter:uid=0c938a95",'
                    '"reorder_note":null}]}'
                ),
            ],
        )
        self.assertEqual(
            [call["task"] for call in self.fx.calls],
            ["parse-query", "distill"],
        )
        parse_prompt = json.loads(self.fx.calls[0]["messages"][0]["content"])
        self.assertEqual(
            parse_prompt,
            {
                "intent": (
                    "Select the authoritative Distiller metered-model policy "
                    "from this closed OS candidate set."
                ),
                "candidates": [
                    {
                        "uid": "0c938a95",
                        "title": (
                            "Distiller Cut 4G — Metered Model Runtime Policy"
                        ),
                        "context": (
                            "Authoritative OS loop policy for the two Distiller "
                            "model edges; production remains closed and "
                            "attempt-4 authority is separate."
                        ),
                    }
                ],
            },
        )
        self.assertNotIn(
            "private",
            self.fx.calls[0]["messages"][0]["content"].lower(),
        )
        self.assertNotIn(
            "team",
            self.fx.calls[0]["messages"][0]["content"].lower(),
        )
        distill_prompt = json.loads(
            self.fx.calls[1]["messages"][0]["content"]
        )
        self.assertEqual(
            distill_prompt["candidates"][0]["text"],
            (
                "Distiller policy 0c938a95 keeps production closed and "
                "authorizes only model-capability-shaped OS canary attempt 4."
            ),
        )
        self.assertEqual(
            [call["context"].admission_mode for call in self.fx.calls],
            ["canary", "canary"],
        )
        self.assertEqual(
            [call["context"].segment_classes for call in self.fx.calls],
            [("os",), ("os",)],
        )
        self.assertEqual(self.fx.policy_hash(), before)
        frontmatter = policy._read_frontmatter(
            self.fx.root / policy.POLICY_RELATIVE_PATH
        )
        self.assertNotIn("metered_canary", frontmatter)
        written = json.loads(
            (self.fx.run_dir / canary.SCORECARD_NAME).read_text()
        )
        self.assertEqual(written, scorecard)

    def test_exact_fenced_pass_preserves_original_text_and_sha_everywhere(self):
        fenced = {
            task: f"```json\n{metered_model.canary_expected_response(task)[0]}\n```"
            for task in canary.CANARY_TASKS
        }
        self.fx.response_texts.update(fenced)

        scorecard = self.fx.run()

        self.assertEqual(scorecard["status"], "pass")
        self.assertEqual(
            [receipt["response_text"] for receipt in scorecard["receipts"]],
            [fenced[task] for task in canary.CANARY_TASKS],
        )
        self.assertEqual(
            [
                receipt["response_text"]
                for receipt in scorecard["gateway_receipts"]
            ],
            [fenced[task] for task in canary.CANARY_TASKS],
        )
        for call_receipt, gateway_receipt in zip(
            scorecard["receipts"],
            scorecard["gateway_receipts"],
        ):
            expected_sha = hashlib.sha256(
                call_receipt["response_text"].encode("utf-8")
            ).hexdigest()
            self.assertEqual(call_receipt["response_sha256"], expected_sha)
            self.assertEqual(gateway_receipt["response_sha256"], expected_sha)
            self.assertEqual(
                gateway_receipt["response_text"],
                call_receipt["response_text"],
            )
        self.assertEqual(self.fx.response_texts, fenced)

    def test_fenced_semantic_failure_reconciles_cost_before_score_failure(self):
        text = '```json\n{"uids":[]}\n```'
        self.fx.response_texts["parse-query"] = text

        scorecard = self.fx.run()

        self.assertEqual(scorecard["status"], "failed")
        self.assertEqual(scorecard["phase"], "calls")
        self.assertIn("sole fixed expected selection", scorecard["error"])
        self.assertEqual(len(scorecard["receipts"]), 1)
        receipt = scorecard["receipts"][0]
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["reservation_status"], "reconciled")
        self.assertFalse(receipt["worst_case_retained"])
        self.assertGreater(receipt["actual_nano_usd"], 0)
        self.assertEqual(receipt["response_text"], text)
        self.assertEqual(
            receipt["response_sha256"],
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(scorecard["actual_nano_usd"], receipt["actual_nano_usd"])
        self.assertEqual(
            scorecard["gateway_receipts"],
            [
                {
                    "reservation_id": receipt["reservation_id"],
                    "task": "parse-query",
                    "model": "claude-haiku-4-5-20251001",
                    "actual_nano_usd": receipt["actual_nano_usd"],
                    "response_sha256": receipt["response_sha256"],
                    "response_text": text,
                    "service_tier": "standard",
                    "inference_geo": "EU West / 東京?! #1",
                }
            ],
        )

    def test_schema_valid_but_wrong_parse_selection_fails_with_bounded_receipts(self):
        wrong_responses = (
            '{"uids":[]}',
            '{"uids": ["0c938a95"]}',
            '{"uids":["deadbeef"]}',
            '{"uids":["0c938a95","deadbeef"]}',
            '{"uids":["deadbeef","0c938a95"]}',
            '{"uids":["0c938a95","0c938a95"]}',
        )
        for raw in wrong_responses:
            with self.subTest(raw=raw):
                fixture = CanaryFixture()
                self.addCleanup(fixture.close)

                def provider(task, messages, **kwargs):
                    result = fixture.provider(task, messages, **kwargs)
                    if task != "parse-query":
                        return result
                    return llm.LockedLLMResponse(
                        text=raw,
                        model=result.model,
                        usage=result.usage,
                    )

                scorecard = fixture.run(provider)
                self.assertEqual(scorecard["status"], "failed")
                self.assertEqual(
                    [call["task"] for call in fixture.calls],
                    ["parse-query"],
                )
                self.assertEqual(
                    [receipt["task"] for receipt in scorecard["receipts"]],
                    ["parse-query"],
                )
                parse = scorecard["receipts"][0]
                self.assertEqual(parse["status"], "failed")
                self.assertIn("sole fixed expected selection", parse["error"])
                self.assertEqual(parse["reservation_status"], "reconciled")
                self.assertEqual(
                    parse["response_sha256"],
                    hashlib.sha256(raw.encode()).hexdigest(),
                )
                self.assertLessEqual(
                    scorecard["reserved_nano_usd"],
                    policy.CANARY_MAX_RESERVED_NANO_USD,
                )
                self.assertEqual(len(scorecard["gateway_receipts"]), 1)

    def test_provider_failure_retains_reservation_and_writes_failed_scorecard(self):
        before = self.fx.policy_hash()

        def provider(task, messages, **kwargs):
            if task == "parse-query":
                self.fx.calls.append(
                    {
                        "task": task,
                        "messages": messages,
                        "max_tokens": kwargs["max_tokens"],
                        "system": kwargs["system"],
                        "context": kwargs["metering_context"],
                    }
                )
                raise RuntimeError("doubled provider outcome unknown")
            return self.fx.provider(task, messages, **kwargs)

        scorecard = self.fx.run(provider)
        self.assertEqual(scorecard["status"], "failed")
        self.assertEqual(
            [receipt["task"] for receipt in scorecard["receipts"]],
            ["parse-query"],
        )
        parse = scorecard["receipts"][0]
        self.assertEqual(parse["status"], "failed")
        self.assertTrue(parse["worst_case_retained"])
        self.assertEqual(parse["reservation_status"], "reserved")
        self.assertIn("PROVIDER_FAILED", parse["error"])
        self.assertGreater(scorecard["reserved_nano_usd"], 0)
        self.assertEqual(self.fx.policy_hash(), before)
        self.assertTrue(
            (self.fx.run_dir / canary.SCORECARD_NAME).is_file()
        )

    def test_short_haiku_alias_is_rejected_in_canary_scorecard(self):
        def alias_provider(task, messages, **kwargs):
            self.fx.calls.append(
                {
                    "task": task,
                    "messages": messages,
                    "max_tokens": kwargs["max_tokens"],
                    "system": kwargs["system"],
                    "context": kwargs["metering_context"],
                }
            )
            return llm.LockedLLMResponse(
                text='{"uids":["0c938a95"]}',
                model="claude-haiku-4-5",
                usage={
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            )

        scorecard = self.fx.run(alias_provider)
        self.assertEqual(scorecard["status"], "failed")
        self.assertEqual([call["task"] for call in self.fx.calls], ["parse-query"])
        receipt = scorecard["receipts"][0]
        self.assertIn("MODEL_SUBSTITUTION", receipt["error"])
        self.assertTrue(receipt["worst_case_retained"])
        self.assertEqual(receipt["reservation_status"], "reserved")

    def test_prepare_wait_and_infrastructure_refusals_make_zero_reservations(self):
        prepared = self.fx.invoke()
        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(self.fx.calls, [])
        self.assertFalse((self.fx.run_dir / canary.SCORECARD_NAME).exists())
        self.assertTrue((self.fx.run_dir / canary.PREPARATION_NAME).is_file())

        waiting = self.fx.invoke()
        self.assertEqual(waiting["status"], "waiting")
        self.assertIn("readiness", waiting["error"])
        self.assertEqual(self.fx.calls, [])

        self.fx.mark_ready()
        failures = (
            ("sdk", {"sdk_check": mock.Mock(side_effect=RuntimeError("sdk missing"))}),
            (
                "port",
                {
                    "gateway_check": mock.Mock(
                        side_effect=RuntimeError("port closed")
                    )
                },
            ),
            ("real-key", {"environment": {"REAL_ANTHROPIC_API_KEY": "forbidden"}}),
        )
        for label, kwargs in failures:
            with self.subTest(label=label):
                result = self.fx.invoke(**kwargs)
                self.assertEqual(result["status"], "waiting")
                self.assertEqual(self.fx.calls, [])
                self.assertFalse(
                    (self.fx.run_dir / canary.SCORECARD_NAME).exists()
                )

    def test_execution_orders_full_preflight_before_ledger_reserve_and_provider(self):
        prepared = self.fx.invoke()
        self.assertEqual(prepared["status"], "prepared")
        self.fx.mark_ready()
        events = []
        original_read = canary._read_canonical_file
        original_exact = canary.verify_exact_canary_claim
        original_gateway_receipts = canary._gateway_receipts
        original_records = canary.metered_model.canary_ledger_records
        original_initialize = canary.daily_spend.initialize_ledger
        original_reserve = canary.daily_spend.reserve

        def read(path, field):
            if path.name == canary.PREPARATION_NAME:
                events.append("preparation")
            elif path.name == canary.READINESS_NAME:
                events.append("readiness")
            return original_read(path, field)

        def exact(*args, **kwargs):
            events.append("claim")
            return original_exact(*args, **kwargs)

        def gateway_receipts(*args, **kwargs):
            if "empty-gateway-receipts" not in events:
                events.append("empty-gateway-receipts")
            return original_gateway_receipts(*args, **kwargs)

        def records(*args, **kwargs):
            if "zero-reservations" not in events:
                events.append("zero-reservations")
            return original_records(*args, **kwargs)

        def initialize(*args, **kwargs):
            events.append("initialize")
            return original_initialize(*args, **kwargs)

        def reserve(*args, **kwargs):
            events.append("reserve")
            return original_reserve(*args, **kwargs)

        def sdk_check():
            events.append("sdk")

        def gateway_check():
            events.append("port")

        def provider(task, messages, **kwargs):
            events.append("provider")
            return self.fx.provider(task, messages, **kwargs)

        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(canary, "_read_canonical_file", side_effect=read)
            )
            stack.enter_context(
                mock.patch.object(
                    canary,
                    "verify_exact_canary_claim",
                    side_effect=exact,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    canary,
                    "_gateway_receipts",
                    side_effect=gateway_receipts,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    canary.metered_model,
                    "canary_ledger_records",
                    side_effect=records,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    canary.daily_spend,
                    "initialize_ledger",
                    side_effect=initialize,
                )
            )
            stack.enter_context(
                mock.patch.object(
                    canary.daily_spend,
                    "reserve",
                    side_effect=reserve,
                )
            )
            completed = self.fx.invoke(
                provider=provider,
                sdk_check=sdk_check,
                gateway_check=gateway_check,
            )
        self.assertEqual(completed["status"], "pass")
        first_provider = events.index("provider")
        ordered = [
            "claim",
            "preparation",
            "readiness",
            "sdk",
            "port",
            "empty-gateway-receipts",
            "zero-reservations",
            "initialize",
            "reserve",
        ]
        self.assertEqual(
            [events.index(item) for item in ordered],
            sorted(events.index(item) for item in ordered),
        )
        self.assertLess(events.index("reserve"), first_provider)

    def test_prior_readiness_identity_cannot_execute_attempt7(self):
        prepared = self.fx.invoke()
        self.assertEqual(prepared["status"], "prepared")
        self.fx.mark_ready()
        readiness_path = self.fx.run_dir / canary.READINESS_NAME
        readiness = json.loads(readiness_path.read_text())
        readiness["policy_version"] = "1.1.0"
        readiness_path.write_text(
            json.dumps(readiness, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        ledger_path = daily_spend._ledger_path(
            ledger_root,
            daily_spend.utc_day(),
            policy.POLICY_VERSION,
        )
        self.assertFalse(ledger_path.exists())
        self.assertFalse(ledger_path.is_symlink())
        waiting = self.fx.invoke()
        self.assertEqual(waiting["status"], "waiting")
        self.assertIn("readiness receipt drifted", waiting["error"])
        self.assertEqual(self.fx.calls, [])
        self.assertFalse(ledger_path.exists())
        self.assertFalse(ledger_path.is_symlink())
        self.assertFalse(
            (self.fx.run_dir / canary.EXECUTION_LEDGER_NAME).exists()
        )
        self.assertFalse((self.fx.run_dir / canary.SCORECARD_NAME).exists())

    def test_same_prepared_run_continues_but_second_run_cannot_adopt_ledger(self):
        prior_paths = {
            evidence.claim_path
            for evidence in policy.PRIOR_ATTEMPT_EVIDENCE
        } | {
            evidence.ledger_path
            for evidence in policy.PRIOR_ATTEMPT_EVIDENCE
        }
        prior_before = {
            relative: (self.fx.root / relative).read_bytes()
            for relative in prior_paths
        }
        prepared = self.fx.invoke()
        self.assertEqual(prepared["status"], "prepared")
        claim_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        current_claim = claim_root / policy.CANARY_CLAIM_NAME
        self.assertTrue(current_claim.is_file())
        self.assertEqual(
            json.loads(current_claim.read_text())["policy_version"],
            policy.POLICY_VERSION,
        )
        current_ledger = daily_spend._ledger_path(
            claim_root,
            daily_spend.utc_day(),
            policy.POLICY_VERSION,
        )
        self.assertFalse(current_ledger.exists())
        self.assertFalse(current_ledger.is_symlink())
        self.assertEqual(
            {
                evidence.ledger_path.name
                for evidence in (
                    *policy.PRIOR_ATTEMPT_EVIDENCE,
                    *policy.PRIOR_PREPARATION_EVIDENCE,
                )
            },
            {
                "2026-07-24.json",
                "2026-07-24@1.2.0.json",
                "2026-07-24@1.3.0.json",
                "2026-07-24@1.4.0.json",
                "2026-07-24@1.5.0.json",
                "2026-07-24@1.6.0.json",
            },
        )
        self.assertEqual(
            sum(
                daily_spend.effective_committed_nano_usd(
                    daily_spend.read_ledger(
                        claim_root,
                        day=evidence.ledger_day,
                        policy_uid=policy.POLICY_UID,
                        policy_version=evidence.policy_version,
                        daily_ceiling_nano_usd=policy.DAILY_CEILING_NANO_USD,
                    )
                )
                for evidence in policy.PRIOR_ATTEMPT_EVIDENCE
            ),
            policy.PRIOR_RETAINED_TOTAL_NANO_USD,
        )
        self.assertEqual(
            {
                relative: (self.fx.root / relative).read_bytes()
                for relative in prior_paths
            },
            prior_before,
        )
        second = self.fx.invoke(run_name="other")
        self.assertEqual(second["status"], "blocked")
        self.assertIn("different run", second["error"])
        self.assertEqual(self.fx.calls, [])
        self.assertFalse(current_ledger.exists())
        self.assertFalse(current_ledger.is_symlink())
        self.assertEqual(
            {
                relative: (self.fx.root / relative).read_bytes()
                for relative in prior_paths
            },
            prior_before,
        )

        self.fx.mark_ready()
        continued = self.fx.invoke()
        self.assertEqual(continued["status"], "pass")
        self.assertTrue(current_ledger.is_file())

    def test_distill_note_must_be_null_and_deadline_stops_without_retry(self):
        def wrong_distill(task, messages, **kwargs):
            result = self.fx.provider(task, messages, **kwargs)
            if task == "distill":
                return llm.LockedLLMResponse(
                    text=(
                        '{"selections":[{"source_uid":"0c938a95",'
                        '"span_anchor":"frontmatter:uid=0c938a95",'
                        '"reorder_note":""}]}'
                    ),
                    model=result.model,
                    usage=result.usage,
                )
            return result

        failed = self.fx.run(wrong_distill)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual([call["task"] for call in self.fx.calls], list(canary.CANARY_TASKS))
        self.assertIn("sole fixed expected selection", failed["receipts"][1]["error"])

        deadline = CanaryFixture()
        self.addCleanup(deadline.close)
        values = iter((0.0, 0.0, 301.0, 301.0))
        timed = deadline.run(monotonic=lambda: next(values))
        self.assertEqual(timed["status"], "failed")
        self.assertEqual([call["task"] for call in deadline.calls], ["parse-query"])
        self.assertIn("deadline", timed["receipts"][0]["error"])

    def test_replay_over_budget_contract_and_passed_attestation_refuse_zero_calls(self):
        passed = self.fx.run()
        self.assertEqual(passed["status"], "pass")
        calls = len(self.fx.calls)
        replay = self.fx.run()
        self.assertEqual(replay["status"], "blocked")
        self.assertIn("already has a scorecard", replay["error"])
        self.assertEqual(len(self.fx.calls), calls)

        over = CanaryFixture()
        self.addCleanup(over.close)
        over.seed_run(budget=0.27)
        result = over.run()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("exact canary contract", result["error"])
        self.assertEqual(over.calls, [])

        attested = CanaryFixture()
        self.addCleanup(attested.close)
        attested.seed_run()

        def add_attestation(value):
            value["metered_canary"] = {
                "passed": True,
                "policy_uid": policy.POLICY_UID,
                "policy_version": policy.POLICY_VERSION,
                "runner_uid": "6389dcd4",
                "canary_run_uid": "ca000000",
                "scorecard_sha256": "a" * 64,
                "verified_by": "7ddf4814",
                "verified_at": "2026-07-24",
                "reserved_nano_usd": 100_000_000,
                "actual_nano_usd": 1_000_000,
            }

        attested.mutate_policy(add_attestation)
        result = attested.run()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("already recorded", result["error"])
        self.assertEqual(attested.calls, [])

    def test_real_root_cli_blocks_attested_policy_without_new_artifacts(self):
        loop_root = ROOT / "vault/loop-runs"
        run_relative = Path(
            "vault/loop-runs/distiller-canary-post-attestation-test"
        )
        run_dir = ROOT / run_relative
        self.assertFalse(run_dir.exists() or run_dir.is_symlink())

        def snapshot():
            result = {}
            for path in loop_root.rglob("*"):
                relative = path.relative_to(loop_root).as_posix()
                if path.is_symlink():
                    result[relative] = ("symlink", str(path.readlink()))
                elif path.is_file():
                    result[relative] = (
                        "file",
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
                elif path.is_dir():
                    result[relative] = ("directory", None)
            return result

        before = snapshot()
        with mock.patch.object(
            sys,
            "stdout",
            new_callable=io.StringIO,
        ) as output:
            exit_code = canary.main(["--run-dir", run_relative.as_posix()])
        result = json.loads(output.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["phase"], "preflight")
        self.assertIn("passed metered canary is already recorded", result["error"])
        self.assertFalse(run_dir.exists() or run_dir.is_symlink())
        self.assertEqual(snapshot(), before)

    def test_cli_and_registered_delegate_expose_no_authority_overrides(self):
        parser = canary.build_parser()
        self.assertEqual(
            {action.dest for action in parser._actions},
            {"help", "run_dir"},
        )
        self.assertEqual(
            parser.parse_args(
                ["--run-dir", "vault/loop-runs/canary"]
            ).run_dir,
            "vault/loop-runs/canary",
        )
        forbidden = (
            "--model",
            "--task-count",
            "--segment",
            "--policy",
            "--fixture",
            "--ledger",
            "--admission-mode",
        )
        for option in forbidden:
            with self.subTest(option=option):
                with self.assertRaises(SystemExit):
                    parser.parse_args(
                        [
                            "--run-dir",
                            "vault/loop-runs/canary",
                            option,
                            "escape",
                        ]
                    )

        spec = importlib.util.spec_from_file_location(
            "distiller_runner_signature_target",
            ROOT / "vault/tools/6389dcd4.py",
        )
        assert spec and spec.loader
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        signature = inspect.signature(runner.call_canary)
        self.assertEqual(
            tuple(signature.parameters),
            ("task", "run_binding"),
        )
        for forbidden_parameter in (
            "messages",
            "system",
            "max_tokens",
            "segment_classes",
            "admission_mode",
            "provider_call",
        ):
            self.assertNotIn(forbidden_parameter, signature.parameters)

        with mock.patch.object(
            canary,
            "run_canary",
            return_value={"status": "prepared"},
        ):
            self.assertEqual(
                canary.main(
                    ["--run-dir", "vault/loop-runs/canary"]
                ),
                3,
            )


if __name__ == "__main__":
    unittest.main()
