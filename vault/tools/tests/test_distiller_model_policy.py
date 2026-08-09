"""Cut 4C strict policy source/index/runner authority plants."""
from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from lib import daily_spend
from lib import distiller_model_policy as policy


ROOT = Path(__file__).resolve().parents[3]
RUNNER_UID = "6389dcd4"
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


class PolicyFixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "vault/files").mkdir(parents=True)
        (self.root / "vault/tools").mkdir(parents=True)
        self.source = self.root / policy.POLICY_RELATIVE_PATH
        self.runner = self.root / f"vault/tools/{RUNNER_UID}.py"
        self.copy_pre_attestation_policy()
        shutil.copy2(ROOT / f"vault/tools/{RUNNER_UID}.py", self.runner)
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
            "uid": RUNNER_UID,
            "type": "tool",
            "name": policy.POLICY_RUNNER,
            "status": "active",
            "state": "active",
            "transport": "library",
            "implementation_kind": "library",
            "path": f"vault/tools/{RUNNER_UID}.py",
        }
        self.write_index()

    def close(self):
        self.temp.cleanup()

    def copy_pre_attestation_policy(self):
        shutil.copy2(ROOT / policy.POLICY_RELATIVE_PATH, self.source)
        value, body = self.frontmatter()
        # Canary-path plants need the deliberate candidate state that existed
        # before the live root policy recorded its passed attempt-7 attestation
        # AND before Mike's separate D1-D4 production ruling (v1.9.0) — pin the
        # pre-ruling governance fields explicitly so this fixture's "candidate"
        # semantics never silently drift with whatever the live root's current
        # production/consent state happens to be.
        value.pop("metered_canary", None)
        value["status"] = "draft"
        value["consent_mode"] = "ask"
        value["segment_egress"] = {"os": "ask", "team": "ask", "private": "ask"}
        value["egress_approved"] = False
        value["egress_approved_by"] = None
        self.write_frontmatter(value, body)

    def write_index(self, rows=None):
        selected = rows if rows is not None else [self.policy_row, self.runner_row]
        path = self.root / policy.POLICY_INDEX_RELATIVE_PATH
        path.write_text(
            "".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                for row in selected
            ),
            encoding="utf-8",
        )

    def frontmatter(self):
        text = self.source.read_text(encoding="utf-8")
        _open, raw, body = text.split("---", 2)
        return yaml.safe_load(raw), body

    def write_frontmatter(self, value, body=None):
        if body is None:
            _value, body = self.frontmatter()
        rendered = yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
        self.source.write_text(f"---\n{rendered}---{body}", encoding="utf-8")

    def mutate(self, function):
        value, body = self.frontmatter()
        function(value)
        self.write_frontmatter(value, body)


class StrictPolicyTests(unittest.TestCase):
    def setUp(self):
        self.fx = PolicyFixture()
        self.addCleanup(self.fx.close)

    def resolve(self):
        return policy.resolve_policy(studio_root=self.fx.root)

    def test_pre_attestation_candidate_resolves_canary_but_disables_production(self):
        contract = self.resolve()
        self.assertEqual(contract.uid, policy.POLICY_UID)
        self.assertEqual(contract.runner_uid, RUNNER_UID)
        self.assertFalse(contract.production_enabled)
        self.assertTrue(contract.canary_admissible)
        self.assertEqual(contract.canary_disabled_reasons, ())
        self.assertEqual(
            contract.disabled_reasons,
            (
                "policy is not active",
                "policy consent mode is not auto",
                "segment egress has no separate human approval",
                "metered canary gate is not passed",
            ),
        )
        self.assertEqual(
            contract.route("parse-query").per_call_ceiling_nano_usd,
            10_000_000,
        )
        self.assertEqual(
            contract.route("parse-query").model,
            "claude-haiku-4-5-20251001",
        )
        self.assertEqual(
            contract.response_usage_controls,
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

    def test_real_root_canonical_policy_resolves_production_authorized_for_os(self):
        contract = policy.resolve_policy(studio_root=ROOT)
        frontmatter = policy._read_frontmatter(ROOT / policy.POLICY_RELATIVE_PATH)
        self.assertEqual(
            frontmatter["metered_canary"],
            {
                "passed": True,
                "policy_uid": policy.POLICY_UID,
                # metered_canary is a LIVE attestation pointer, not a frozen
                # historical record like PRIOR_*_POLICY_VERSION below — it is
                # re-stamped to the current POLICY_VERSION at every bump to
                # keep asserting "the current policy state has a passed
                # canary backing it" (enforced by _canary_passed).
                "policy_version": policy.POLICY_VERSION,
                "runner_uid": RUNNER_UID,
                "canary_run_uid": "5a5f6189",
                "scorecard_sha256": (
                    "691f5464a55117f3ec2aa2a6de02fbba031d065e63de79af"
                    "4a748ce10508b1ab"
                ),
                "verified_by": "cdf9b3ad",
                "verified_at": "2026-07-25",
                "reserved_nano_usd": 25_299_000,
                "actual_nano_usd": 1_289_000,
            },
        )
        # No second v1.8 canary can ever be admitted — that stays true forever.
        self.assertFalse(contract.canary_admissible)
        self.assertEqual(
            contract.canary_disabled_reasons,
            (
                "production authority is not fully closed",
                "a passed metered canary is already recorded",
            ),
        )
        # v1.9.0 binds Mike's D1-D4 ruling (7a4e9df1): production is now
        # authorized for the OS segment only, within the locked ceilings.
        self.assertTrue(contract.production_enabled)
        self.assertEqual(contract.disabled_reasons, ())
        self.assertEqual(contract.status, "active")
        self.assertEqual(contract.consent_mode, "auto")
        self.assertTrue(contract.egress_approved)
        self.assertEqual(
            contract.segment_egress,
            {"os": "auto", "team": "ask", "private": "ask"},
        )
        # D2: the new $50/month aggregate belt is real, code-enforced ceiling.
        self.assertEqual(contract.monthly_ceiling_nano_usd, 50_000_000_000)

    def test_source_index_identity_drift_refuses(self):
        for field, value in (
            ("uid", "deadbeef"),
            ("type", "task"),
            ("version", "1.2.1"),
            ("state", "archived"),
            ("status", "active"),
            ("runner", "alias"),
        ):
            with self.subTest(field=field):
                original = dict(self.fx.policy_row)
                self.fx.policy_row[field] = value
                self.fx.write_index()
                with self.assertRaises(policy.PolicyError):
                    self.resolve()
                self.fx.policy_row = original
                self.fx.write_index()

    def test_duplicate_and_unknown_fields_refuse(self):
        text = self.fx.source.read_text(encoding="utf-8")
        self.fx.source.write_text(
            text.replace("runner: distiller-model-edge", "runner: distiller-model-edge\nrunner: alias"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(policy.PolicyError, "duplicate YAML key"):
            self.resolve()

        self.fx.copy_pre_attestation_policy()
        self.fx.mutate(lambda value: value.__setitem__("security_escape", True))
        with self.assertRaisesRegex(policy.PolicyError, "unknown fields"):
            self.resolve()

    def test_monthly_spend_is_optional_but_strict_when_present(self):
        # The fixture's copied real file already declares monthly_spend
        # (D2's $50/month belt) — resolving it should carry the locked
        # ceiling through onto the contract.
        contract = self.resolve()
        self.assertEqual(contract.monthly_ceiling_nano_usd, 50_000_000_000)

        # Removing it entirely must be backward compatible: no monthly gate,
        # not an error.
        self.fx.mutate(lambda value: value.pop("monthly_spend", None))
        contract = self.resolve()
        self.assertIsNone(contract.monthly_ceiling_nano_usd)

        # Present but wrong must refuse closed, like daily_spend.
        for mutation in (
            lambda value: value.__setitem__(
                "monthly_spend", {"ceiling_usd": 5.0, "timezone": "UTC", "scope": "combined"}
            ),
            lambda value: value.__setitem__(
                "monthly_spend", {"ceiling_usd": 50.0, "timezone": "PST", "scope": "combined"}
            ),
            lambda value: value.__setitem__(
                "monthly_spend", {"ceiling_usd": 50.0, "timezone": "UTC", "scope": "per-task"}
            ),
            lambda value: value.__setitem__(
                "monthly_spend", {"ceiling_usd": 50.0, "timezone": "UTC"}
            ),
        ):
            with self.subTest(mutation=mutation):
                self.fx.mutate(mutation)
                with self.assertRaises(policy.PolicyError):
                    self.resolve()

    def test_nested_route_and_spend_lock_mutations_refuse(self):
        mutations = (
            lambda value: value["model_routes"]["parse-query"].__setitem__("alias", "x"),
            lambda value: value["model_routes"]["distill"].__setitem__(
                "model", "claude-opus-4-8"
            ),
            lambda value: value["daily_spend"].__setitem__("ceiling_usd", 5.01),
            lambda value: value["pricing_usd_per_mtok"][
                "claude-haiku-4-5-20251001"
            ].__setitem__("input_tokens", "1.000000001"),
            lambda value: value.__setitem__("spend_limits_locked_by", "deadbeef"),
            lambda value: value.__setitem__(
                "spend_limits_approval_verbatim", "Go for it"
            ),
        )
        pristine = self.fx.source.read_bytes()
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.fx.source.write_bytes(pristine)
                self.fx.mutate(mutation)
                with self.assertRaises(policy.PolicyError):
                    self.resolve()

    def test_pre_attestation_candidate_has_exact_attempt7_canary_authority(self):
        contract = self.resolve()
        self.assertTrue(contract.canary_admissible)
        self.assertFalse(contract.production_enabled)
        value, _body = self.fx.frontmatter()
        self.assertEqual(
            value["canary_egress"],
            {
                "approved": True,
                "approved_by": policy.CANARY_APPROVER_UID,
                "approved_at": policy.CANARY_APPROVED_AT,
                "approval_scope": policy.CANARY_APPROVAL_SCOPE,
                "approval_verbatim": policy.CANARY_APPROVAL,
                "attempt": 7,
                "prior_attempts": [
                    evidence.policy_record()
                    for evidence in policy.PRIOR_ATTEMPT_EVIDENCE
                ],
                "prior_preparations": [
                    evidence.policy_record()
                    for evidence in policy.PRIOR_PREPARATION_EVIDENCE
                ],
                "prior_executions": [
                    evidence.policy_record()
                    for evidence in policy.PRIOR_EXECUTION_EVIDENCE
                ],
                "segment": "os",
                "max_calls": 2,
                "max_reserved_usd": 0.26,
            },
        )
        self.assertEqual(value["status"], "draft")
        self.assertEqual(value["consent_mode"], "ask")
        self.assertIs(value["egress_approved"], False)
        self.assertIsNone(value["egress_approved_by"])
        self.assertEqual(
            value["segment_egress"],
            {"os": "ask", "team": "ask", "private": "ask"},
        )
        self.assertNotIn("metered_canary", value)
        self.assertEqual(
            value["request_controls"],
            {
                "parse-query": {"service_tier": "standard_only"},
                "distill": {
                    "service_tier": "standard_only",
                    "inference_geo": "global",
                },
            },
        )
        self.assertEqual(
            value["response_usage_controls"],
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
        self.assertEqual(
            value["os_geo_ruling"],
            {
                "ruled_by": "7b921d17",
                "source_event": "evt_6147bbbaaf258b3c_00000017",
                "scope": "os-only-any-bounded-response-geo",
                "team_private": "blocked",
                "revisit_on": "team-private-model-egress",
            },
        )

    def test_canary_authority_mutations_refuse(self):
        mutations = (
            lambda value: value.pop("canary_egress"),
            lambda value: value["canary_egress"].__setitem__("approved", False),
            lambda value: value["canary_egress"].__setitem__(
                "approved_by", "deadbeef"
            ),
            lambda value: value["canary_egress"].__setitem__(
                "approval_verbatim", "Yes to both"
            ),
            lambda value: value["canary_egress"].__setitem__(
                "approval_scope", "os-canary"
            ),
            lambda value: value["canary_egress"].__setitem__("attempt", 2),
            lambda value: value["canary_egress"].__setitem__(
                "prior_attempts",
                list(reversed(value["canary_egress"]["prior_attempts"])),
            ),
            lambda value: value["canary_egress"].__setitem__(
                "prior_preparations",
                list(reversed(value["canary_egress"]["prior_preparations"])),
            ),
            lambda value: value["canary_egress"]["prior_preparations"][0].__setitem__(
                "preparation_day", "2026-07-25"
            ),
            lambda value: value["canary_egress"]["prior_preparations"][1].__setitem__(
                "zero_reservations", False
            ),
            lambda value: value["canary_egress"]["prior_preparations"][0][
                "evidence_sha256"
            ].__setitem__("claim", "f" * 64),
            lambda value: value["canary_egress"]["prior_preparations"][1][
                "absent_artifacts"
            ].append("invented.json"),
            lambda value: value["canary_egress"].__setitem__(
                "prior_executions", []
            ),
            lambda value: value["canary_egress"]["prior_executions"][0].__setitem__(
                "actual_nano_usd", 218_001
            ),
            lambda value: value["canary_egress"]["prior_executions"][0].__setitem__(
                "response_text", '{"uids":["0c938a95"]}'
            ),
            lambda value: value["canary_egress"]["prior_executions"][0][
                "evidence_sha256"
            ].__setitem__("scorecard", "f" * 64),
            lambda value: value["canary_egress"]["prior_executions"][0].__setitem__(
                "unexpected", True
            ),
            lambda value: value["canary_egress"].__setitem__(
                "prior_executions",
                [
                    value["canary_egress"]["prior_executions"][0],
                    value["canary_egress"]["prior_executions"][0],
                ],
            ),
            lambda value: value["canary_egress"].__setitem__(
                "prior_attempts",
                [
                    value["canary_egress"]["prior_attempts"][0],
                    value["canary_egress"]["prior_attempts"][0],
                ],
            ),
            lambda value: value["canary_egress"].__setitem__(
                "prior_attempts",
                value["canary_egress"]["prior_attempts"][:1],
            ),
            lambda value: value["canary_egress"].__setitem__(
                "prior_attempts",
                value["canary_egress"]["prior_attempts"] + [
                    value["canary_egress"]["prior_attempts"][1]
                ],
            ),
            lambda value: value["canary_egress"].__setitem__(
                "prior_attempts",
                [
                    {
                        **value["canary_egress"]["prior_attempts"][0],
                        "run_uid": "deadbeef",
                    },
                    value["canary_egress"]["prior_attempts"][1],
                ],
            ),
            lambda value: value["canary_egress"].__setitem__("segment", "team"),
            lambda value: value["canary_egress"].__setitem__("max_calls", 3),
            lambda value: value["canary_egress"].__setitem__(
                "max_reserved_usd", 0.27
            ),
            lambda value: value["canary_egress"].__setitem__("override", True),
            lambda value: value.__setitem__(
                "request_controls",
                {
                    "parse-query": {"service_tier": "priority"},
                    "distill": {
                        "service_tier": "standard_only",
                        "inference_geo": "global",
                    },
                },
            ),
            lambda value: value.__setitem__(
                "request_controls",
                {
                    "parse-query": {
                        "service_tier": "standard_only",
                        "inference_geo": "global",
                    },
                    "distill": {
                        "service_tier": "standard_only",
                        "inference_geo": "global",
                    },
                },
            ),
            lambda value: value["response_usage_controls"][
                "parse-query"
            ].__setitem__("inference_geo_policy", "allowlist"),
            lambda value: value["response_usage_controls"][
                "distill"
            ].__setitem__("inference_geo_policy", "unrecorded"),
            lambda value: value["response_usage_controls"][
                "parse-query"
            ].__setitem__("service_tier", "priority"),
            lambda value: value["response_usage_controls"][
                "parse-query"
            ].__setitem__("unknown", True),
            lambda value: value.pop("os_geo_ruling"),
            lambda value: value["os_geo_ruling"].__setitem__(
                "source_event", "evt_wrong"
            ),
            lambda value: value["os_geo_ruling"].__setitem__("scope", "all-segments"),
            lambda value: value["os_geo_ruling"].__setitem__("team_private", "ask"),
            lambda value: value["os_geo_ruling"].__setitem__("unknown", True),
        )
        pristine = self.fx.source.read_bytes()
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.fx.source.write_bytes(pristine)
                self.fx.mutate(mutation)
                with self.assertRaises(policy.PolicyError):
                    self.resolve()

    def test_os_geo_ruling_event_is_verified_first_hand(self):
        cases = (
            ("missing", None),
            ("source", lambda event: event.__setitem__("source", "/agents/other")),
            ("subject", lambda event: event.__setitem__("subject", "deadbeef")),
            (
                "semantics",
                lambda event: event["data"].__setitem__(
                    "message",
                    "OPTION 3 without the closed ruling semantics",
                ),
            ),
        )
        for label, mutation in cases:
            with self.subTest(label=label):
                fx = PolicyFixture()
                self.addCleanup(fx.close)
                path = fx.root / policy.OS_GEO_EVENT_RELATIVE_PATH
                if mutation is None:
                    path.unlink()
                else:
                    events = [
                        json.loads(line)
                        for line in path.read_text().splitlines()
                        if line.strip()
                    ]
                    target = next(
                        event
                        for event in events
                        if event.get("event_uid") == policy.OS_GEO_SOURCE_EVENT
                    )
                    mutation(target)
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
                with self.assertRaisesRegex(policy.PolicyError, "OS geo ruling"):
                    policy.resolve_policy(studio_root=fx.root)

    def test_attempt1_evidence_is_verified_first_hand(self):
        cases = (
            "ledger",
            "claim",
            "run",
            "scorecard",
        )
        for label in cases:
            with self.subTest(label=label):
                fx = PolicyFixture()
                self.addCleanup(fx.close)
                if label == "ledger":
                    path = fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH
                    value = json.loads(path.read_text())
                    value["reservations"][policy.PRIOR_RESERVATION_ID][
                        "worst_case_nano_usd"
                    ] += 1
                    value["checksum"] = daily_spend._checksum(value)
                    path.write_text(
                        json.dumps(value, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )
                elif label == "claim":
                    path = fx.root / policy.PRIOR_CLAIM_RELATIVE_PATH
                    value = json.loads(path.read_text())
                    value["run_uid"] = "deadbeef"
                    path.write_text(
                        json.dumps(value, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )
                elif label == "run":
                    path = fx.root / policy.PRIOR_RUN_RELATIVE_PATH
                    lines = [json.loads(line) for line in path.read_text().splitlines()]
                    lines[0]["run_uid"] = "deadbeef"
                    path.write_text(
                        "".join(
                            json.dumps(
                                value,
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                            + "\n"
                            for value in lines
                        )
                    )
                else:
                    path = fx.root / policy.PRIOR_SCORECARD_RELATIVE_PATH
                    path.write_bytes(path.read_bytes() + b"\n")
                with self.assertRaisesRegex(policy.PolicyError, "attempt-1"):
                    policy.resolve_policy(studio_root=fx.root)

    def test_every_tracked_prior_evidence_file_is_hash_verified(self):
        owner_by_path = {}
        for evidence in policy.PRIOR_ATTEMPT_EVIDENCE:
            for relative, _sha256 in evidence.evidence_hashes:
                owner_by_path.setdefault(relative, evidence.attempt)
        self.assertEqual(len(owner_by_path), 37)
        for relative, attempt in owner_by_path.items():
            with self.subTest(relative=relative, attempt=attempt):
                fx = PolicyFixture()
                self.addCleanup(fx.close)
                path = fx.root / relative
                path.write_bytes(path.read_bytes() + b"x")
                with self.assertRaisesRegex(
                    policy.PolicyError,
                    f"attempt-{attempt}",
                ):
                    policy.resolve_policy(studio_root=fx.root)

    def test_every_inert_preparation_file_and_absence_is_verified(self):
        for evidence in policy.PRIOR_PREPARATION_EVIDENCE:
            for _name, relative, _sha256 in evidence.evidence_hashes:
                with self.subTest(version=evidence.policy_version, relative=relative):
                    fx = PolicyFixture()
                    self.addCleanup(fx.close)
                    path = fx.root / relative
                    path.write_bytes(path.read_bytes() + b"x")
                    with self.assertRaisesRegex(
                        policy.PolicyError,
                        f"prior preparation {evidence.policy_version}",
                    ):
                        policy.resolve_policy(studio_root=fx.root)
            for absent in evidence.absent_artifacts:
                with self.subTest(version=evidence.policy_version, absent=absent):
                    fx = PolicyFixture()
                    self.addCleanup(fx.close)
                    relative = Path(absent)
                    path = (
                        fx.root / relative
                        if len(relative.parts) > 1
                        else fx.root / evidence.run_path.parent / relative
                    )
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"unexpected\n")
                    with self.assertRaisesRegex(
                        policy.PolicyError,
                        "absent artifact appeared",
                    ):
                        policy.resolve_policy(studio_root=fx.root)

    def test_attempt6_execution_files_and_reconciled_values_are_verified(self):
        evidence = policy.PRIOR_EXECUTION_EVIDENCE[0]
        self.assertEqual(
            evidence.policy_record(),
            self.fx.frontmatter()[0]["canary_egress"]["prior_executions"][0],
        )
        self.assertEqual(evidence.run_uid, "a02843bc")
        self.assertEqual(evidence.reservation_id, "9448c1b0")
        self.assertEqual(evidence.reserved_nano_usd, 5_312_000)
        self.assertEqual(evidence.actual_nano_usd, 218_000)
        self.assertEqual(evidence.response_text, '```json\n{"uids":["0c938a95"]}\n```')
        self.assertEqual(
            hashlib.sha256(evidence.response_text.encode()).hexdigest(),
            evidence.response_sha256,
        )
        self.resolve()
        for name, relative, _sha256 in evidence.evidence_hashes:
            with self.subTest(name=name, relative=relative):
                fx = PolicyFixture()
                self.addCleanup(fx.close)
                path = fx.root / relative
                path.write_bytes(path.read_bytes() + b"x")
                with self.assertRaisesRegex(
                    policy.PolicyError,
                    "prior execution attempt-6",
                ):
                    policy.resolve_policy(studio_root=fx.root)

    def test_orphan_provenance_source_commit_bytes_match_rehomed_evidence(self):
        evidence = policy.PRIOR_PREPARATION_EVIDENCE[0]
        provenance = json.loads(
            (ROOT / evidence.provenance_path).read_text(encoding="utf-8")
        )
        self.assertEqual(
            provenance["source_commit"],
            "9aac71ad62755668131a1bb4dc9b475438775d91",
        )
        original_run = provenance["original_run_relative_path"]
        source_paths = {
            "run.jsonl": f"{original_run}/run.jsonl",
            "preparation.json": (
                f"{original_run}/distiller-metered-canary-preparation.json"
            ),
            "gateway_spend.json": f"{original_run}/gateway_spend.json",
            "v1.5.0-claim.json": (
                "vault/loop-runs/.model-spend/"
                "distiller-canary-0c938a95-1.5.0-claim.json"
            ),
            "v1.5.0-ledger.json": (
                "vault/loop-runs/.model-spend/2026-07-24@1.5.0.json"
            ),
        }
        rehomed_paths = {
            "run.jsonl": evidence.run_path,
            "preparation.json": (
                evidence.run_path.parent
                / "distiller-metered-canary-preparation.json"
            ),
            "gateway_spend.json": evidence.run_path.parent / "gateway_spend.json",
            "v1.5.0-claim.json": evidence.claim_path,
            "v1.5.0-ledger.json": evidence.ledger_path,
        }
        for name, source_path in source_paths.items():
            with self.subTest(name=name):
                source = subprocess.run(
                    [
                        "git",
                        "show",
                        f"{provenance['source_commit']}:{source_path}",
                    ],
                    cwd=ROOT,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                ).stdout
                rehomed = (ROOT / rehomed_paths[name]).read_bytes()
                self.assertEqual(source, rehomed)
                self.assertEqual(
                    hashlib.sha256(source).hexdigest(),
                    provenance["source_hashes"][name],
                )

    def test_all_prior_failure_surfaces_match_their_exact_outcome_class(self):
        self.resolve()
        for evidence in policy.PRIOR_ATTEMPT_EVIDENCE:
            with self.subTest(attempt=evidence.attempt):
                run_dir = self.fx.root / evidence.run_path.parent
                gateway_spend = json.loads(
                    (run_dir / "gateway_spend.json").read_text()
                )
                scorecard = json.loads(
                    (
                        run_dir
                        / "distiller-metered-canary-scorecard.json"
                    ).read_text()
                )
                self.assertEqual(gateway_spend, dict(evidence.gateway_spend))
                self.assertEqual(scorecard["error"], evidence.scorecard_error)
                self.assertEqual(
                    scorecard["receipts"][0]["error"],
                    evidence.receipt_error,
                )
        self.assertEqual(
            set(dict(policy.PRIOR_ATTEMPT_EVIDENCE[0].gateway_spend)),
            {"metering_error"},
        )
        self.assertEqual(
            set(dict(policy.PRIOR_ATTEMPT_EVIDENCE[1].gateway_spend)),
            {"metering_error"},
        )
        self.assertEqual(
            dict(policy.PRIOR_ATTEMPT_EVIDENCE[2].gateway_spend),
            {"spent_usd": 0.0},
        )
        self.assertIn(
            "does not support inference_geo",
            policy.PRIOR_ATTEMPT_EVIDENCE[2].scorecard_error,
        )
        self.assertEqual(
            dict(policy.PRIOR_ATTEMPT_EVIDENCE[3].gateway_spend),
            {"metering_error": "usage.inference_geo must equal 'global'"},
        )
        self.assertEqual(
            policy.PRIOR_ATTEMPT_EVIDENCE[3].retained_nano_usd,
            5_312_000,
        )
        self.assertEqual(policy.PRIOR_RETAINED_TOTAL_NANO_USD, 21_199_000)

    def test_attempt1_contract_hash_chain_mutations_refuse_without_side_effects(self):
        for label in ("claim", "run-contract", "scorecard"):
            with self.subTest(label=label):
                fx = PolicyFixture()
                self.addCleanup(fx.close)
                if label == "claim":
                    path = fx.root / policy.PRIOR_CLAIM_RELATIVE_PATH
                    value = json.loads(path.read_text())
                    value["contract_sha256"] = "f" * 64
                    path.write_text(
                        json.dumps(value, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )
                elif label == "run-contract":
                    path = fx.root / policy.PRIOR_RUN_RELATIVE_PATH
                    lines = [json.loads(line) for line in path.read_text().splitlines()]
                    lines[1]["brakes"]["max_iterations"] = 3
                    path.write_text(
                        "".join(
                            json.dumps(
                                value,
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                            + "\n"
                            for value in lines
                        )
                    )
                else:
                    path = fx.root / policy.PRIOR_SCORECARD_RELATIVE_PATH
                    value = json.loads(path.read_text())
                    value["run"]["contract_sha256"] = "f" * 64
                    path.write_text(
                        json.dumps(value, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    )

                before = {
                    item.relative_to(fx.root): item.read_bytes()
                    for item in fx.root.rglob("*")
                    if item.is_file()
                }
                with self.assertRaisesRegex(policy.PolicyError, "attempt-1"):
                    policy.resolve_policy(studio_root=fx.root)
                after = {
                    item.relative_to(fx.root): item.read_bytes()
                    for item in fx.root.rglob("*")
                    if item.is_file()
                }
                self.assertEqual(after, before)
                ledger_root = fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
                self.assertFalse((ledger_root / policy.CANARY_CLAIM_NAME).exists())
                self.assertFalse((ledger_root / policy.CANARY_CLAIM_LOCK_NAME).exists())

    def test_attempt7_claim_rejects_all_prior_run_uids_before_lock_write(self):
        contract = self.resolve()
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        run_dir = (self.fx.root / policy.PRIOR_RUN_RELATIVE_PATH).parent
        before = {
            path.relative_to(self.fx.root): path.read_bytes()
            for path in self.fx.root.rglob("*")
            if path.is_file()
        }
        for run_uid in policy.PRIOR_RUN_UIDS:
            with self.subTest(run_uid=run_uid):
                with self.assertRaisesRegex(policy.PolicyError, "fresh run_uid"):
                    policy.claim_canary_authority(
                        ledger_root,
                        policy=contract,
                        run_uid=run_uid,
                        run_dir=run_dir,
                        contract_sha256=policy.PRIOR_CONTRACT_SHA256,
                    )
                self.assertFalse((ledger_root / policy.CANARY_CLAIM_NAME).exists())
                self.assertFalse(
                    (ledger_root / policy.CANARY_CLAIM_LOCK_NAME).exists()
                )
        after = {
            path.relative_to(self.fx.root): path.read_bytes()
            for path in self.fx.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_second_v18_run_cannot_reuse_consumed_claim(self):
        contract = self.resolve()
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        first = self.fx.root / "vault/loop-runs/attempt7-first"
        second = self.fx.root / "vault/loop-runs/attempt7-second"
        first.mkdir()
        second.mkdir()
        policy.claim_canary_authority(
            ledger_root,
            policy=contract,
            run_uid="ca000001",
            run_dir=first,
            contract_sha256="a" * 64,
        )
        self.assertFalse((ledger_root / policy.CANARY_CLAIM_LOCK_NAME).exists())
        claim_before = (ledger_root / policy.CANARY_CLAIM_NAME).read_bytes()
        with self.assertRaisesRegex(policy.PolicyError, "different run"):
            policy.claim_canary_authority(
                ledger_root,
                policy=contract,
                run_uid="ca000002",
                run_dir=second,
                contract_sha256="b" * 64,
            )
        self.assertEqual(
            (ledger_root / policy.CANARY_CLAIM_NAME).read_bytes(),
            claim_before,
        )

    def test_atomic_claim_race_accepts_only_exact_single_winner(self):
        contract = self.resolve()
        ledger_root = self.fx.root / policy.PRIOR_LEDGER_RELATIVE_PATH.parent
        requested = self.fx.root / "vault/loop-runs/attempt7-requested"
        winner = self.fx.root / "vault/loop-runs/attempt7-race-winner"
        claim_path = ledger_root / policy.CANARY_CLAIM_NAME
        original_create = policy._create_claim
        for exact_match in (True, False):
            with self.subTest(exact_match=exact_match):
                claim_path.unlink(missing_ok=True)
                winner_binding = policy._claim_binding(
                    ledger_root=ledger_root,
                    policy=contract,
                    run_uid="ca000001" if exact_match else "ca000002",
                    run_dir=requested if exact_match else winner,
                    contract_sha256="a" * 64 if exact_match else "b" * 64,
                    require_run_dir=False,
                )

                def racing_create(path, value):
                    original_create(path, winner_binding)
                    original_create(path, value)

                with mock.patch.object(
                    policy,
                    "_create_claim",
                    side_effect=racing_create,
                ):
                    if exact_match:
                        actual = policy.claim_canary_authority(
                            ledger_root,
                            policy=contract,
                            run_uid="ca000001",
                            run_dir=requested,
                            contract_sha256="a" * 64,
                        )
                        self.assertEqual(actual, winner_binding)
                    else:
                        with self.assertRaisesRegex(
                            policy.PolicyError,
                            "different run",
                        ):
                            policy.claim_canary_authority(
                                ledger_root,
                                policy=contract,
                                run_uid="ca000001",
                                run_dir=requested,
                                contract_sha256="a" * 64,
                            )
                actual = json.loads(claim_path.read_text())
                self.assertEqual(actual, winner_binding)
                self.assertFalse(
                    (ledger_root / policy.CANARY_CLAIM_LOCK_NAME).exists()
                )

    def test_passed_attestation_disables_second_canary_and_opens_no_production(self):
        def attest(value):
            value["metered_canary"] = {
                "passed": True,
                "policy_uid": policy.POLICY_UID,
                "policy_version": policy.POLICY_VERSION,
                "runner_uid": RUNNER_UID,
                "canary_run_uid": "c0000001",
                "scorecard_sha256": "a" * 64,
                "verified_by": "7ddf4814",
                "verified_at": "2026-07-24",
                "reserved_nano_usd": 200_000_000,
                "actual_nano_usd": 1_000_000,
            }

        self.fx.mutate(attest)
        contract = self.resolve()
        self.assertFalse(contract.canary_admissible)
        self.assertEqual(
            contract.canary_disabled_reasons,
            ("a passed metered canary is already recorded",),
        )
        self.assertFalse(contract.production_enabled)
        self.assertNotIn(
            "metered canary gate is not passed",
            contract.disabled_reasons,
        )

    def test_future_metered_canary_attestation_schema_is_closed(self):
        attestation = {
            "passed": True,
            "policy_uid": policy.POLICY_UID,
            "policy_version": policy.POLICY_VERSION,
            "runner_uid": RUNNER_UID,
            "canary_run_uid": "c0000001",
            "scorecard_sha256": "a" * 64,
            "verified_by": "7ddf4814",
            "verified_at": "2026-07-24",
            "reserved_nano_usd": 200_000_000,
            "actual_nano_usd": 1_000_000,
        }
        mutations = (
            lambda value: value.pop("scorecard_sha256"),
            lambda value: value.__setitem__("override", True),
            lambda value: value.__setitem__("canary_run_uid", "not-a-uid"),
            lambda value: value.__setitem__("scorecard_sha256", "A" * 64),
            lambda value: value.__setitem__("verified_at", "July 24"),
            lambda value: value.__setitem__("verified_at", "2026-99-99"),
            lambda value: value.__setitem__("reserved_nano_usd", 260_000_001),
            lambda value: value.__setitem__("actual_nano_usd", 250_000_000),
        )
        pristine = self.fx.source.read_bytes()
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.fx.source.write_bytes(pristine)
                candidate = dict(attestation)
                mutation(candidate)
                self.fx.mutate(
                    lambda value: value.__setitem__(
                        "metered_canary",
                        candidate,
                    )
                )
                with self.assertRaises(policy.PolicyError):
                    self.resolve()

    def test_missing_or_drifted_runner_registration_refuses(self):
        self.fx.write_index([self.fx.policy_row])
        with self.assertRaisesRegex(policy.PolicyError, "registered"):
            self.resolve()
        self.fx.runner_row["path"] = "vault/tools/other.py"
        self.fx.write_index()
        with self.assertRaisesRegex(policy.PolicyError, "runner path"):
            self.resolve()

    def test_symlinked_policy_or_runner_refuses(self):
        outside = self.fx.root / "outside.md"
        outside.write_bytes(self.fx.source.read_bytes())
        self.fx.source.unlink()
        self.fx.source.symlink_to(outside)
        with self.assertRaisesRegex(policy.PolicyError, "symlinked"):
            self.resolve()

        self.fx.source.unlink()
        self.fx.copy_pre_attestation_policy()
        runner_outside = self.fx.root / "runner.py"
        runner_outside.write_bytes(self.fx.runner.read_bytes())
        self.fx.runner.unlink()
        self.fx.runner.symlink_to(runner_outside)
        with self.assertRaises(policy.PolicyError):
            self.resolve()

    def test_global_gates_allow_segment_scoped_auto_subset(self):
        def activate(value):
            value["status"] = "active"
            value["consent_mode"] = "auto"
            value["egress_approved"] = True
            value["egress_approved_by"] = "7b921d17"
            value["segment_egress"] = {
                "os": "auto",
                "team": "ask",
                "private": "ask",
            }
            value["metered_canary"] = {
                "passed": True,
                "policy_uid": policy.POLICY_UID,
                "policy_version": policy.POLICY_VERSION,
                "runner_uid": RUNNER_UID,
                "canary_run_uid": "c0000001",
                "scorecard_sha256": "b" * 64,
                "verified_by": "7ddf4814",
                "verified_at": "2026-07-24",
                "reserved_nano_usd": 200_000_000,
                "actual_nano_usd": 1_000_000,
            }

        self.fx.mutate(activate)
        self.fx.policy_row["status"] = "active"
        self.fx.write_index()
        contract = self.resolve()
        self.assertTrue(contract.production_enabled)
        self.assertFalse(contract.canary_admissible)
        self.assertEqual(
            contract.segment_egress,
            {"os": "auto", "team": "ask", "private": "ask"},
        )


if __name__ == "__main__":
    unittest.main()
