#!/usr/bin/env python3
"""Cut 4A full orient() chassis and owned-source boundary plants."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import socket
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from vault.tools.tests import test_distiller as legacy
from vault.tools.tests.test_distiller_model_policy import PolicyFixture

import lib.distiller as di
import lib.distiller_content as dc
import lib.distiller_edge as de
import lib.distiller_query as dq
import lib.task_circle as tc
import lib.llm as llm
import lib.daily_spend as daily_spend
import lib.metered_model as metered_model
from lib.distiller_model_policy import (
    POLICY_VERSION,
    claim_canary_authority,
    resolve_policy,
)


SNAPSHOT = "snapshot-orient-1"
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


class CountingLoader(dc.InMemoryContentLoader):
    def __init__(self, bodies, *, index_as_of=SNAPSHOT):
        super().__init__(bodies, index_as_of=index_as_of, max_chunk_bytes=1024)
        self.calls = []

    def load_spans(self, uid):
        self.calls.append(uid)
        return super().load_spans(uid)


class OrientChassisCase(unittest.TestCase):
    def setUp(self) -> None:
        self.roots = legacy._RootFactory()
        self.addCleanup(self.roots.cleanup)
        self.fx = legacy._OrientFixture(self.roots)
        self.fx.node("task0001", legacy.TEAM, type_="task", status="active")
        self.fx.node("caps0001", legacy.TEAM, type_="capsule", status="locked")
        self.fx.node("query001", legacy.TEAM, type_="note", status="active")
        self.fx.node("queryhop", legacy.TEAM, type_="note", status="active")
        self.fx.node("hidden01", legacy.PRIV_ALICE, type_="note", status="active")
        self.fx.rel("task0001", "caps0001", "governed_by")
        self.fx.neighbor("query001", "queryhop")
        self.viewer = legacy.bob()
        self.projection = self.fx.projection()
        self.circle_index = tc.InMemoryStructuralIndex(
            self.fx._structures, index_as_of=SNAPSHOT
        )
        self.query_index = dq.InMemoryQueryIndex(
            {
                "query001": "needle relevant",
                "hidden01": "needle hidden",
            },
            index_as_of=SNAPSHOT,
        )
        self.bodies = {
            "caps0001": "# Capsule\n\ncapsule body",
            "query001": "# Query\n\nquery body",
            "queryhop": "# Hop\n\nhop body",
        }

    def orient(self, *, intent="needle", parse_double=None, distill_double=None, loader=None):
        loader = loader or CountingLoader(self.bodies)
        result = di.orient(
            "task0001",
            self.viewer,
            16,
            intent=intent,
            index_as_of=SNAPSHOT,
            chunk_budget=3,
            projection=self.projection,
            query_index=self.query_index,
            circle_index=self.circle_index,
            rank_index=self.fx.rank_index(),
            content_loader=loader,
            parse_double=parse_double,
            distill_double=distill_double,
        )
        return result, loader


class FullAssemblyTests(OrientChassisCase):
    def test_no_double_defaults_run_full_chassis_deterministically(self):
        with mock.patch.object(
            llm,
            "call_locked",
            side_effect=AssertionError("draft/all-ask policy must call zero providers"),
        ) as provider:
            first, _ = self.orient()
            second, _ = self.orient()
        provider.assert_not_called()
        self.assertTrue(first.ok, msg=first.error)
        self.assertTrue(second.ok, msg=second.error)
        orientation = first.value
        self.assertIsInstance(orientation, de.Orientation)
        self.assertEqual(orientation.query_seeds.uids, ("query001",))
        self.assertTrue(orientation.query_seeds.fallback_used)
        self.assertEqual(orientation.bound_deterministic.viewer, self.viewer)
        self.assertEqual(
            orientation.bound_deterministic.index_as_of, SNAPSHOT
        )
        self.assertIn("query001", orientation.bound_deterministic.deterministic.uids())
        self.assertIn("queryhop", orientation.bound_deterministic.deterministic.uids())
        self.assertTrue(orientation.distillation.fallback_used)
        self.assertEqual(first.value, second.value)
        self.assertIsNone(orientation.distillation.capture_id)
        self.assertEqual(orientation.distillation.capture_status, "pending")

    def test_pre_attestation_canary_calls_leave_orient_zero_call_and_policy_unchanged(self):
        candidate = PolicyFixture()
        self.addCleanup(candidate.close)
        studio = candidate.root.resolve()
        (studio / ".tropo").mkdir()
        policy = resolve_policy(studio_root=studio)
        self.assertEqual(policy.version, POLICY_VERSION)
        self.assertFalse(policy.production_enabled)
        self.assertTrue(policy.canary_admissible)
        source_before = hashlib.sha256(policy.source_path.read_bytes()).hexdigest()
        ledger = studio / metered_model.LEDGER_RELATIVE_PATH
        day = daily_spend.utc_day()
        daily_spend.initialize_ledger(
            ledger,
            policy_uid=policy.uid,
            policy_version=policy.version,
            daily_ceiling_nano_usd=policy.daily_ceiling_nano_usd,
            day=day,
        )
        run_dir = studio / "vault/loop-runs/canary"
        run_dir.mkdir()
        created, contract = metered_model.canary_run_events(
            "ca000001",
            policy.runner_uid,
        )
        (run_dir / "run.jsonl").write_text(
            "\n".join(
                __import__("json").dumps(
                    value,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                for value in (created, contract)
            )
            + "\n"
        )
        contract_hash = metered_model.canary_contract_sha256(contract)
        claim_canary_authority(
            ledger,
            policy=policy,
            run_uid="ca000001",
            run_dir=run_dir,
            contract_sha256=contract_hash,
        )
        preparation = {
            "schema_version": 1,
            "status": "prepared",
            "policy_uid": policy.uid,
            "policy_version": policy.version,
            "runner_uid": policy.runner_uid,
            "run_uid": "ca000001",
            "contract_sha256": contract_hash,
            "request_sha256": metered_model.canary_request_hashes(),
            "admission_mode": "canary",
            "segment_classes": ["os"],
            "tasks": list(metered_model.CANARY_TASKS),
            "max_iterations": 2,
            "max_reserved_nano_usd": 260_000_000,
            "preparation_day": day,
            "execution_ledger_required": True,
        }
        (run_dir / metered_model.CANARY_PREPARATION_NAME).write_text(
            __import__("json").dumps(
                preparation,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        execution_ledger = metered_model.canary_execution_ledger_receipt(
            run_uid="ca000001",
            contract_sha256=contract_hash,
            preparation_day=day,
            execution_day=day,
            initial_ledger_sha256=hashlib.sha256(
                daily_spend._ledger_path(
                    ledger,
                    day,
                    policy.version,
                ).read_bytes()
            ).hexdigest(),
        )
        (run_dir / metered_model.CANARY_EXECUTION_LEDGER_NAME).write_text(
            __import__("json").dumps(
                execution_ledger,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        binding = metered_model.RunBinding(
            "ca000001",
            metered_model.GATEWAY_URL,
            "sk-virtual-tropo-ca000001",
            studio,
            run_dir,
        )
        ids = iter(("ca000011", "ca000012"))
        paid_calls = []

        def provider(task, _messages, **kwargs):
            paid_calls.append((task, kwargs["metering_context"].admission_mode))
            return llm.LockedLLMResponse(
                text="{}",
                model=llm.LOCKED_TASK_MODELS[task],
                usage={
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "service_tier": "standard",
                    "inference_geo": "global",
                },
            )

        def canary(task):
            return metered_model.call_canary(
                task,
                run_binding=binding,
                provider_call=provider,
                policy_resolver=lambda: policy,
                clock=lambda: datetime.now(timezone.utc),
                reservation_id_factory=lambda: next(ids),
                environment={},
            )

        with mock.patch.object(
            llm,
            "call_locked",
            side_effect=AssertionError("orient production path must call zero providers"),
        ) as production_provider:
            before, _ = self.orient()
            parse = canary("parse-query")
            distill = canary("distill")
            after, _ = self.orient()
        production_provider.assert_not_called()
        self.assertIsInstance(parse, metered_model.MeteredModelResult)
        self.assertIsInstance(distill, metered_model.MeteredModelResult)
        self.assertEqual(
            paid_calls,
            [("parse-query", "canary"), ("distill", "canary")],
        )
        self.assertTrue(before.ok, msg=before.error)
        self.assertEqual(before.value, after.value)
        self.assertEqual(
            hashlib.sha256(policy.source_path.read_bytes()).hexdigest(),
            source_before,
        )

    def test_parse_double_adds_visible_seed_provenance_and_hides_hidden_proposal(self):
        result, _ = self.orient(
            parse_double=lambda **_kwargs: dq.QueryProposal(
                ("hidden01", "query001")
            )
        )
        self.assertTrue(result.ok, msg=result.error)
        orientation = result.value
        self.assertFalse(orientation.query_seeds.fallback_used)
        self.assertEqual(orientation.query_seeds.uids, ("query001",))
        deterministic = orientation.bound_deterministic.deterministic
        self.assertEqual(
            deterministic.circle.reason("query001"),
            f"{tc.REL_QUERY_SEED}:task0001",
        )
        self.assertNotIn("hidden01", deterministic.uids())
        self.assertNotIn(
            "hidden01",
            tuple(chunk.source_uid for chunk in orientation.distillation.chunks),
        )

    def test_valid_distill_double_selects_exact_loaded_span(self):
        def select_query(*, candidates, **_kwargs):
            span = next(span for span in candidates if span.source_uid == "query001")
            return (de.SpanSelection(span.source_uid, span.span_anchor),)

        result, _ = self.orient(distill_double=select_query)
        self.assertTrue(result.ok, msg=result.error)
        self.assertFalse(result.value.distillation.fallback_used)
        self.assertEqual(
            tuple(chunk.source_uid for chunk in result.value.distillation.chunks),
            ("query001",),
        )
        self.assertEqual(
            result.value.distillation.chunks[0].text, self.bodies["query001"]
        )

    def test_invalid_distill_double_falls_back_without_partial_selection(self):
        def invalid(*, candidates, **_kwargs):
            span = candidates[0]
            return (
                de.SpanSelection(span.source_uid, span.span_anchor),
                de.SpanSelection("outside1", span.span_anchor),
            )

        result, _ = self.orient(distill_double=invalid)
        baseline, _ = self.orient()
        self.assertTrue(result.ok, msg=result.error)
        self.assertTrue(result.value.distillation.fallback_used)
        self.assertEqual(result.value.distillation, baseline.value.distillation)

    def test_empty_intent_uses_exact_no_freeform_seed_path(self):
        result, _ = self.orient(intent=" ")
        self.assertTrue(result.ok, msg=result.error)
        orientation = result.value
        self.assertEqual(orientation.query_seeds.uids, ())
        self.assertFalse(orientation.query_seeds.fallback_used)
        deterministic = orientation.bound_deterministic.deterministic
        self.assertEqual(deterministic.uids(), ("caps0001",))
        self.assertEqual(orientation.distillation.shown_circle.seeds, ())


class OrientPreReadBindingTests(OrientChassisCase):
    def test_content_binding_mismatch_refuses_before_loader_read(self):
        loader = CountingLoader(self.bodies, index_as_of="other")
        result, _ = self.orient(loader=loader)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, de.DistillErrorCode.BINDING_MISMATCH)
        self.assertEqual(loader.calls, [])

    def test_circle_binding_mismatch_refuses_before_query_or_content(self):
        calls = []

        def parse(**_kwargs):
            calls.append("parse")
            return dq.QueryProposal(("query001",))

        self.circle_index = tc.InMemoryStructuralIndex(
            self.fx._structures, index_as_of="other"
        )
        loader = CountingLoader(self.bodies)
        result, _ = self.orient(parse_double=parse, loader=loader)
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, dq.QueryErrorCode.BINDING_MISMATCH)
        self.assertEqual(calls, [])
        self.assertEqual(loader.calls, [])


class CutBoundarySourceAudit(unittest.TestCase):
    def test_owned_runtime_imports_and_calls_stay_inside_cut_4a_boundary(self):
        modules = (dq, dc, de, di)
        forbidden_import_roots = {
            "requests",
            "urllib",
            "http",
            "httpx",
            "socket",
            "openai",
            "anthropic",
            "boto3",
        }
        forbidden_call_tokens = {
            "emit_event",
            "emit",
            "capture_write",
            "meter",
            "price",
            "egress",
        }
        for module in modules:
            path = Path(module.__file__)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = set()
            calls = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        calls.add(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        calls.add(node.func.attr)
            self.assertEqual(
                imports & forbidden_import_roots,
                set(),
                msg=f"forbidden import in {path.name}",
            )
            self.assertEqual(
                calls & forbidden_call_tokens,
                set(),
                msg=f"forbidden call in {path.name}",
            )


# BEGIN 77184178 BOOT-ORIENTATION TESTS
class _GitFixture:
    """Small real repository with exact, replayable commit topology."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.run("init")
        self.run("config", "user.name", "Distiller Fixture")
        self.run("config", "user.email", "distiller@example.invalid")
        self.run("config", "commit.gpgSign", "false")
        hooks = self.root / ".fixture-hooks"
        hooks.mkdir()
        self.run("config", "core.hooksPath", str(hooks))
        self.run("branch", "-M", "main")

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def run(
        self, *args: str, check: bool = True, env=None
    ) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if check and result.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)} failed: {result.stderr or result.stdout}"
            )
        return result

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self, message: str, *, date: Optional[str] = None) -> str:
        environment = None
        if date is not None:
            import os

            environment = dict(os.environ)
            environment["GIT_AUTHOR_DATE"] = date
            environment["GIT_COMMITTER_DATE"] = date
        self.run("add", "-A")
        self.run("commit", "-m", message, env=environment)
        return self.run("rev-parse", "HEAD").stdout.strip()


def _memory_surface(commit: str, *, event_position="2026-07-26T12:34:56Z") -> str:
    event_line = (
        f"  event_position: '{event_position}'\n"
        if event_position is not None
        else ""
    )
    return (
        "---\n"
        "agent: argus\n"
        "spec_version: '3.0'\n"
        "transfer_watermark:\n"
        f"  commit: '{commit}'\n"
        f"{event_line}"
        "  curated_date: '2026-07-26'\n"
        "---\n\n"
        "# Argus memory\n\n"
        "## §Living-Transfer-from-Predecessor\n\n"
        "Exact predecessor handoff bytes.\n"
        "Second handoff line.\n\n"
        "## §History\n\n"
        "Older material.\n"
    )


AGENT_UID = "a9e00001"
ROOT_UID = "a7000001"


def _agent_source(
    agent: str,
    party_uid: str,
    *,
    identity_uid: str = AGENT_UID,
    root_uid: str = ROOT_UID,
) -> str:
    return (
        "---\n"
        f"uid: {identity_uid}\n"
        "type: agent\n"
        f"agent: {agent}\n"
        f"party_uid: {party_uid}\n"
        f"agent_root_uid: {root_uid}\n"
        "member_of:\n"
        f"  - {root_uid}\n"
        "status: active\n"
        "---\n"
        f"# {agent} identity\n"
    )


def _root_source(agent: str, root_uid: str = ROOT_UID) -> str:
    return (
        "---\n"
        f"uid: {root_uid}\n"
        "type: project\n"
        f"agent_slug: {agent}\n"
        "status: active\n"
        "---\n"
        f"# {agent} root\n"
    )


def _party_source(party_uid: str, agent: str) -> str:
    return (
        "---\n"
        f"uid: {party_uid}\n"
        "type: principal\n"
        f"display_name: {agent}\n"
        "status: active\n"
        "---\n"
        f"# {agent} principal\n"
    )


def _entry_source(
    uid: str,
    *,
    type_: str,
    segment: str,
    owner=None,
    assigned_to=None,
    member_of=None,
) -> str:
    lines = [
        "---",
        f"uid: {uid}",
        f"type: {type_}",
        "status: active",
        "modified: '2026-07-26'",
        f"segment: {segment}",
    ]
    if owner is not None:
        lines.append(f"owner: {owner}")
    if assigned_to is not None:
        lines.append(f"assigned_to: {assigned_to}")
    if member_of:
        lines.append("member_of:")
        lines.extend(f"  - {parent}" for parent in member_of)
    lines.extend(["---", f"# {uid}", ""])
    return "\n".join(lines)


def _superseded_day_granular_delta(records, watermark_day: str, as_of_day: str):
    """The replaced A140 formula, retained only as the criterion-6 control."""

    return tuple(
        record["uid"]
        for record in records
        if isinstance(record.get("modified"), str)
        and watermark_day < record["modified"] <= as_of_day
    )


def _dotted_call(call: ast.Call) -> str:
    if (
        isinstance(call.func, ast.Call)
        and isinstance(call.func.func, ast.Name)
        and call.func.func.id == "getattr"
        and len(call.func.args) >= 2
        and isinstance(call.func.args[0], ast.Name)
        and isinstance(call.func.args[1], ast.Constant)
        and isinstance(call.func.args[1].value, str)
    ):
        return f"{call.func.args[0].id}.{call.func.args[1].value}"
    parts = []
    cursor = call.func
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        parts.append(cursor.id)
    return ".".join(reversed(parts))


def _import_aliases(node: ast.AST) -> dict:
    aliases = {}
    for item in ast.walk(node):
        if isinstance(item, ast.Import):
            for imported in item.names:
                aliases[imported.asname or imported.name.split(".", 1)[0]] = imported.name
        elif isinstance(item, ast.ImportFrom) and item.module:
            for imported in item.names:
                if imported.name != "*":
                    aliases[imported.asname or imported.name] = (
                        f"{item.module}.{imported.name}"
                    )
    return aliases


_ENTROPY_MODULES = {
    "time",
    "datetime",
    "random",
    "secrets",
    "uuid",
    "os",
}


def _expression_reference(
    expression: ast.AST,
    aliases: Mapping[str, str],
    structured_values: Optional[Mapping[str, ast.AST]] = None,
):
    structured_values = structured_values or {}
    if isinstance(expression, ast.Name):
        return aliases.get(expression.id, expression.id)
    if isinstance(expression, ast.Attribute):
        owner = _expression_reference(expression.value, aliases, structured_values)
        return f"{owner}.{expression.attr}" if owner else None
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == "getattr"
        and expression.args
    ):
        owner = _expression_reference(
            expression.args[0], aliases, structured_values
        )
        if not owner:
            return None
        if (
            len(expression.args) >= 2
            and isinstance(expression.args[1], ast.Constant)
            and isinstance(expression.args[1].value, str)
        ):
            return f"{owner}.{expression.args[1].value}"
        if owner.split(".", 1)[0] in _ENTROPY_MODULES:
            return f"{owner}.*"
    if isinstance(expression, ast.Call) and not expression.args and not expression.keywords:
        if isinstance(expression.func, ast.Lambda):
            return _expression_reference(
                expression.func.body, aliases, structured_values
            )
        if isinstance(expression.func, ast.Name):
            factory = structured_values.get(f"{expression.func.id}()")
            if factory is None:
                assigned = structured_values.get(expression.func.id)
                if isinstance(assigned, ast.Lambda):
                    factory = assigned.body
            if factory is not None:
                return _expression_reference(factory, aliases, structured_values)
    if isinstance(expression, ast.Subscript):
        if (
            isinstance(expression.value, ast.Name)
            and expression.value.id in structured_values
            and isinstance(expression.slice, ast.Constant)
            and isinstance(expression.slice.value, int)
        ):
            structured = structured_values[expression.value.id]
            if isinstance(structured, (ast.Tuple, ast.List)):
                try:
                    selected = structured.elts[expression.slice.value]
                except IndexError:
                    selected = None
                if selected is not None:
                    return _expression_reference(
                        selected, aliases, structured_values
                    )
        owner = _expression_reference(
            expression.value, aliases, structured_values
        )
        if owner and owner.split(".", 1)[0] in _ENTROPY_MODULES:
            return f"{owner}.*"
    if isinstance(expression, ast.NamedExpr):
        return _expression_reference(expression.value, aliases, structured_values)
    return None


def _assignment_aliases(node: ast.AST, initial: Mapping[str, str]) -> tuple:
    """Resolve statically knowable assignment chains and destructuring."""

    aliases = dict(initial)
    structured_values = {}
    assignments = []
    for item in ast.walk(node):
        if isinstance(item, ast.Assign):
            assignments.extend((target, item.value) for target in item.targets)
        elif isinstance(item, ast.AnnAssign) and item.value is not None:
            assignments.append((item.target, item.value))
        elif isinstance(item, ast.NamedExpr):
            assignments.append((item.target, item.value))
        elif (
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item is not node
        ):
            returns = [
                child.value
                for child in item.body
                if isinstance(child, ast.Return) and child.value is not None
            ]
            if len(returns) == 1:
                structured_values[f"{item.name}()"] = returns[0]

    def bind(target, value):
        changed = False
        if isinstance(value, ast.Name) and value.id in structured_values:
            value = structured_values[value.id]
        if isinstance(target, ast.Starred):
            return bind(target.value, value)
        if isinstance(target, (ast.Tuple, ast.List)) and isinstance(
            value, (ast.Tuple, ast.List)
        ):
            starred = [
                position
                for position, child in enumerate(target.elts)
                if isinstance(child, ast.Starred)
            ]
            if len(starred) == 1 and len(value.elts) >= len(target.elts) - 1:
                position = starred[0]
                trailing = len(target.elts) - position - 1
                for child_target, child_value in zip(
                    target.elts[:position], value.elts[:position]
                ):
                    changed = bind(child_target, child_value) or changed
                middle_end = len(value.elts) - trailing if trailing else len(value.elts)
                changed = bind(
                    target.elts[position],
                    ast.List(
                        elts=value.elts[position:middle_end],
                        ctx=ast.Load(),
                    ),
                ) or changed
                if trailing:
                    for child_target, child_value in zip(
                        target.elts[-trailing:], value.elts[-trailing:]
                    ):
                        changed = bind(child_target, child_value) or changed
            elif len(target.elts) == len(value.elts):
                for child_target, child_value in zip(target.elts, value.elts):
                    changed = bind(child_target, child_value) or changed
            return changed
        if not isinstance(target, ast.Name):
            return False
        if isinstance(value, (ast.Tuple, ast.List, ast.Lambda)):
            rendered = ast.dump(value, include_attributes=False)
            previous = structured_values.get(target.id)
            if previous is None or ast.dump(
                previous, include_attributes=False
            ) != rendered:
                structured_values[target.id] = value
                return True
            return False
        reference = _expression_reference(value, aliases, structured_values)
        if reference and aliases.get(target.id) != reference:
            aliases[target.id] = reference
            return True
        return False

    for _pass in range(len(assignments) + 1):
        changed = False
        for target, value in assignments:
            changed = bind(target, value) or changed
        if not changed:
            break
    return aliases, structured_values


def _normalized_call(
    call: ast.Call,
    aliases: Mapping[str, str],
    structured_values: Optional[Mapping[str, ast.AST]] = None,
) -> str:
    resolved = _expression_reference(call.func, aliases, structured_values)
    dotted = resolved or _dotted_call(call)
    if not dotted:
        return ""
    head, *tail = dotted.split(".")
    replacement = aliases.get(head, head)
    return ".".join((replacement, *tail))


def _definition_nodes(tree: ast.AST):
    definitions = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    definitions[f"{node.name}.{member.name}"] = member
    return definitions


def _determinism_modules():
    import lib.distiller_ranker as ranker_module
    import lib.task_circle as circle_module
    import lib.viewer_projection as projection_module

    modules = (di, ranker_module, circle_module, projection_module)
    return {
        module.__name__: (
            module,
            ast.parse(Path(module.__file__).read_text(encoding="utf-8")),
        )
        for module in modules
    }


def _reachable_determinism_violations(module_trees) -> set[str]:
    """Import-aware transitive scan of every boot composition dependency."""

    definitions = {
        module_name: _definition_nodes(tree)
        for module_name, (_module, tree) in module_trees.items()
    }
    module_aliases = {
        module_name: _import_aliases(tree)
        for module_name, (_module, tree) in module_trees.items()
    }
    methods_by_name = {}
    for module_name, module_definitions in definitions.items():
        for qualified_name in module_definitions:
            methods_by_name.setdefault(qualified_name.rsplit(".", 1)[-1], []).append(
                (module_name, qualified_name)
            )
    pending = [
        ("lib.distiller", "orient_boot"),
        ("lib.distiller", "_compose_open_work"),
        ("lib.distiller", "_load_committed_boot_sources"),
        ("lib.distiller", "_verify_injected_boot_sources"),
        ("lib.distiller", "_FrozenBootProjection.visible_segments"),
        ("lib.distiller", "_FrozenBootProjection.filter_visible_uids"),
        ("lib.distiller", "_FrozenBootProjection.adjacency"),
        ("lib.distiller", "_FrozenBootProjection.authority"),
        ("lib.distiller", "_FrozenStructuralIndex.structure"),
        ("lib.distiller", "_FrozenStructuralIndex.__getattr__"),
        ("lib.distiller", "_FrozenRankIndex.record"),
        ("lib.distiller_ranker", "rank_circle"),
        ("lib.task_circle", "draw_circle"),
        ("lib.viewer_projection", "ViewerProjection.visible_segments"),
        ("lib.viewer_projection", "ViewerProjection.filter_visible_uids"),
        ("lib.viewer_projection", "ViewerProjection.adjacency"),
        ("lib.viewer_projection", "ViewerProjection.authority"),
    ]
    visited = set()
    violations = set()
    while pending:
        module_name, qualified_name = pending.pop()
        identity = (module_name, qualified_name)
        if identity in visited:
            continue
        visited.add(identity)
        node = definitions.get(module_name, {}).get(qualified_name)
        if node is None:
            continue
        module = module_trees[module_name][0]
        aliases = dict(module_aliases[module_name])
        aliases.update(_import_aliases(node))
        aliases, structured_values = _assignment_aliases(node, aliases)
        for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
            dotted = _normalized_call(call, aliases, structured_values)
            if (
                dotted.startswith("time.")
                or dotted.startswith("datetime.")
                or dotted.startswith("random.")
                or dotted.startswith("secrets.")
                or dotted.startswith("uuid.")
                or dotted in {"os.urandom", "os.times", "os.*"}
            ):
                violations.add(dotted)
            if isinstance(call.func, ast.Name):
                name = call.func.id
                if name in definitions[module_name]:
                    pending.append((module_name, name))
                    continue
                imported = aliases.get(name, "")
                imported_module, _, imported_name = imported.rpartition(".")
                if imported_module in definitions:
                    pending.append((imported_module, imported_name))
                    continue
                target = vars(module).get(name)
                target_module = inspect.getmodule(target)
                target_name = getattr(target, "__qualname__", "")
                if target_module is not None and target_module.__name__ in definitions:
                    pending.append((target_module.__name__, target_name))
            elif isinstance(call.func, ast.Attribute):
                attribute = call.func.attr
                imported_module, _, imported_name = dotted.rpartition(".")
                if imported_module in definitions:
                    pending.append((imported_module, imported_name))
                if isinstance(call.func.value, ast.Name):
                    owner = vars(module).get(call.func.value.id)
                    if inspect.ismodule(owner) and owner.__name__ in definitions:
                        pending.append((owner.__name__, attribute))
                pending.extend(methods_by_name.get(attribute, ()))
    return violations


def _compose_seed_guard_violations(tree: ast.AST) -> set[str]:
    """Structural guard for projection-owned immutable viewer seed approval."""

    node = _definition_nodes(tree)["_compose_open_work"]
    approval_node = _definition_nodes(tree)["ViewerApprovedUIDs.from_projection"]
    calls = [
        (call, _dotted_call(call), statement_index)
        for statement_index, statement in enumerate(node.body)
        for call in ast.walk(statement)
        if isinstance(call, ast.Call)
    ]
    violations = set()
    required = {
        "projection.visible_segments",
        "projection.authority",
        "ViewerApprovedUIDs.from_projection",
        "approved.prevalidated_query_seeds",
        "draw_circle",
        "rank_circle",
    }
    indexes = {}
    for required_call in required:
        locations = [
            statement_index
            for _call, dotted, statement_index in calls
            if dotted == required_call
        ]
        if not locations:
            violations.add(f"missing:{required_call}")
        else:
            indexes[required_call] = min(locations)
    record_indexes = [
        statement_index
        for statement_index, statement in enumerate(node.body)
        if any(
            isinstance(item, ast.Name)
            and item.id == "records"
            and isinstance(item.ctx, ast.Load)
            for item in ast.walk(statement)
        )
    ]
    if not record_indexes:
        violations.add("missing:records")
    elif all(name in indexes for name in required):
        order = (
            indexes["projection.visible_segments"],
            indexes["projection.authority"],
            min(record_indexes),
            indexes["ViewerApprovedUIDs.from_projection"],
            indexes["approved.prevalidated_query_seeds"],
            indexes["draw_circle"],
            indexes["rank_circle"],
        )
        if tuple(sorted(order)) != order or len(set(order)) != len(order):
            violations.add("order:visibility-authority-records-filter-seed-draw-rank")
    forbidden_names = {
        "all_records",
        "raw_records",
        "scan",
        "_records",
        "_items",
        "_graph",
        "_source",
    }
    for item in ast.walk(node):
        if isinstance(item, ast.Attribute) and item.attr in forbidden_names:
            violations.add(f"raw-source:{item.attr}")
        elif isinstance(item, ast.Name) and item.id in forbidden_names:
            violations.add(f"raw-source:{item.id}")
        if isinstance(item, ast.BinOp) and isinstance(item.op, (ast.BitAnd, ast.BitOr)):
            violations.add("compose:raw-set-algebra")
        elif (
            isinstance(item, ast.Call)
            and isinstance(item.func, ast.Attribute)
            and item.func.attr in {"intersection", "union", "update"}
        ):
            violations.add("compose:raw-set-algebra")
    draw_calls = [call for call, dotted, _index in calls if dotted == "draw_circle"]
    if draw_calls:
        keywords = {keyword.arg: keyword.value for keyword in draw_calls[0].keywords}
        expected_draw_bindings = {
            "projection": "projection",
            "index": "circle_index",
            "query_seeds": "query_seeds",
        }
        for keyword, expected_name in expected_draw_bindings.items():
            value = keywords.get(keyword)
            if not isinstance(value, ast.Name) or value.id != expected_name:
                violations.add(f"draw-binding:{keyword}")
    approved_assignments = [
        statement
        for statement in node.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "approved"
            for target in statement.targets
        )
    ]
    if len(approved_assignments) != 1:
        violations.add("compose:approved-overwrite")
    approval_indexes = [
        index
        for _call, dotted, index in calls
        if dotted == "ViewerApprovedUIDs.from_projection"
    ]
    if approval_indexes:
        approval_index = min(approval_indexes)
        for statement in node.body[approval_index + 1 :]:
            if any(
                isinstance(item, ast.Name)
                and item.id == "candidate_uids"
                and isinstance(item.ctx, ast.Load)
                for item in ast.walk(statement)
            ):
                violations.add("compose:post-filter-candidate-bypass")
    if not any(
        isinstance(item, ast.Attribute)
        and isinstance(item.value, ast.Name)
        and item.value.id == "approved"
        and item.attr == "uids"
        for item in ast.walk(node)
    ):
        violations.add("compose:approved-uids-unused")

    approval_calls = [
        call for call in ast.walk(approval_node) if isinstance(call, ast.Call)
    ]
    if not any(
        _dotted_call(call) == "projection.filter_visible_uids"
        for call in approval_calls
    ):
        violations.add("approval:missing-projection-filter")
    if not any(
        isinstance(call.func, ast.Attribute) and call.func.attr == "issubset"
        for call in approval_calls
    ):
        violations.add("approval:missing-candidate-subset")
    approved_values = [
        statement
        for statement in approval_node.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "approved"
            for target in statement.targets
        )
    ]
    if len(approved_values) != 1:
        violations.add("approval:approved-overwrite")
    elif not any(
        isinstance(item, ast.Name) and item.id == "filtered"
        for item in ast.walk(approved_values[0].value)
    ) or any(
        isinstance(item, ast.Name) and item.id in {"candidates", "candidate_uids"}
        for item in ast.walk(approved_values[0].value)
    ):
        violations.add("approval:approved-not-filter-derived")
    for item in ast.walk(approval_node):
        if isinstance(item, ast.BinOp) and isinstance(item.op, ast.BitOr):
            violations.add("approval:union-bypass")
        elif (
            isinstance(item, ast.Call)
            and isinstance(item.func, ast.Attribute)
            and item.func.attr in {"union", "update"}
        ):
            violations.add("approval:union-bypass")
    return violations


_BINDING_RAISE_COVERAGE = {
    ("InMemoryBootIndex.visible_records", "'boot_index.snapshot'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("SqliteBootIndex.visible_records", "'index_path'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_frontmatter_at", "f'{path}.frontmatter.start'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_frontmatter_at", "f'{path}.frontmatter.end'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_frontmatter_at", "f'{path}.frontmatter.yaml'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_frontmatter_at", "f'{path}.frontmatter.type'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_bind_records_to_git", "'boot_index.path'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_bind_records_to_git", "'boot_index.source'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_bind_records_to_git", "'boot_index.uid'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_bind_records_to_git", "f'boot_index.{field}'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_require_record_matches_source", "f'authority_index.{field}'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_resolve_agent_authority", "'identity.path'"):
        "test_binding_source_and_authority_guards_report_exact_fields",
    ("_FrozenBootProjection._viewer_result", "'frozen_projection.viewer'"):
        "test_binding_frozen_and_serve_guards_report_exact_fields",
    ("_FrozenBootProjection.adjacency", "'frozen_projection.adjacency'"):
        "test_binding_frozen_and_serve_guards_report_exact_fields",
    ("_FrozenBootProjection.authority", "'frozen_projection.authority'"):
        "test_binding_frozen_and_serve_guards_report_exact_fields",
    ("_snapshot_rows", "f'boot_snapshot.{field}.shape'"):
        "test_binding_snapshot_guards_report_exact_fields",
    ("_snapshot_rows", "f'boot_snapshot.{field}.uids'"):
        "test_binding_snapshot_guards_report_exact_fields",
    ("_load_committed_boot_sources", "'boot_snapshot.bytes'"):
        "test_binding_snapshot_guards_report_exact_fields",
    ("_load_committed_boot_sources", "'boot_snapshot.schema'"):
        "test_binding_snapshot_guards_report_exact_fields",
    ("_load_committed_boot_sources", "'boot_snapshot.viewer'"):
        "test_binding_snapshot_guards_report_exact_fields",
    ("_load_committed_boot_sources", "'boot_snapshot.visible_segments'"):
        "test_binding_snapshot_guards_report_exact_fields",
    ("_load_committed_boot_sources", "'boot_snapshot.records.segment'"):
        "test_binding_snapshot_guards_report_exact_fields",
    ("_load_committed_boot_sources", "f'boot_snapshot.{field}.membership'"):
        "test_binding_snapshot_guards_report_exact_fields",
    ("_load_committed_boot_sources", "'boot_snapshot.projection.adjacency'"):
        "test_binding_snapshot_guards_report_exact_fields",
    ("_load_committed_boot_sources", "'boot_snapshot.circle_index.children'"):
        "test_binding_snapshot_guards_report_exact_fields",
    ("_verify_injected_boot_sources", "'projection.visible_segments'"):
        "test_binding_injected_source_guards_report_exact_fields",
    ("_verify_injected_boot_sources", "'boot_index.content'"):
        "test_binding_injected_source_guards_report_exact_fields",
    ("_verify_injected_boot_sources", "'projection.filter_visible_uids'"):
        "test_binding_injected_source_guards_report_exact_fields",
    ("_verify_injected_boot_sources", "'projection.content'"):
        "test_binding_injected_source_guards_report_exact_fields",
    ("_verify_injected_boot_sources", "'circle_index.content'"):
        "test_binding_injected_source_guards_report_exact_fields",
    ("_verify_injected_boot_sources", "'rank_index.content'"):
        "test_binding_injected_source_guards_report_exact_fields",
    ("serve_boot_orientation", "'content_identity.shape'"):
        "test_binding_frozen_and_serve_guards_report_exact_fields",
    ("serve_boot_orientation", "'content_identity.digest'"):
        "test_binding_frozen_and_serve_guards_report_exact_fields",
    ("serve_boot_orientation", "'viewer'"):
        "test_binding_frozen_and_serve_guards_report_exact_fields",
    ("serve_boot_orientation", "'as_of'"):
        "test_binding_frozen_and_serve_guards_report_exact_fields",
    ("serve_boot_orientation", "'source_snapshot.consumer'"):
        "test_binding_frozen_and_serve_guards_report_exact_fields",
    ("serve_boot_orientation", "'source_snapshot.provenance'"):
        "test_binding_frozen_and_serve_guards_report_exact_fields",
    ("serve_boot_orientation", "'source_snapshot.bytes'"):
        "test_binding_frozen_and_serve_guards_report_exact_fields",
}


def _binding_error_sites(tree: ast.AST) -> tuple:
    sites = []
    stack = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def visit_FunctionDef(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def visit_AsyncFunctionDef(self, node):
            self.visit_FunctionDef(node)

        def visit_Call(self, node):
            error = node
            if (
                isinstance(error, ast.Call)
                and isinstance(error.func, ast.Name)
                and error.func.id == "BootOrientationError"
                and error.args
                and ast.unparse(error.args[0])
                == "BootOrientationErrorCode.BINDING_MISMATCH"
            ):
                field = next(
                    (
                        ast.unparse(keyword.value)
                        for keyword in error.keywords
                        if keyword.arg == "field"
                    ),
                    "MISSING",
                )
                sites.append((".".join(stack), field))
            self.generic_visit(node)

    Visitor().visit(tree)
    return tuple(sites)


def _criterion6_reachable_evidence(
    records,
    *,
    changed_uid: str,
    changed_path: str,
    changed_commit: str,
    changed_commits,
    raw_changed_paths,
    before_bytes: bytes,
    after_bytes: bytes,
    watermark_day: str,
    changed_day: str,
    as_of_day: str,
    new_delta_uids,
    formula=_superseded_day_granular_delta,
):
    """Prove DAG delta catches a stale-day change the old formula misses."""

    assert records, "criterion-6 fixture must contain records"
    changed = [
        record
        for record in records
        if record.get("uid") == changed_uid and record.get("path") == changed_path
    ]
    assert len(changed) == 1, "changed UID/path must resolve exactly once"
    assert isinstance(changed[0].get("modified"), str), "changed record needs modified"
    assert changed_commits, "reachable commit range must be nonempty"
    assert changed_commit in changed_commits, "changed commit must be in reachable range"
    assert changed_commit in raw_changed_paths.get(
        changed_path, ()
    ), "raw DAG evidence must name the changed path and commit"
    assert before_bytes != after_bytes, "changed path must have different tree bytes"
    assert watermark_day < as_of_day, "governing days must be distinct and ordered"
    assert changed_day == as_of_day, "changed commit must land on the as_of day"
    assert (
        changed[0]["modified"] == watermark_day
    ), "changed record must retain the stale watermark-day frontmatter"
    assert tuple(new_delta_uids) == (
        changed_uid,
    ), "new reachability delta must contain the expected UID"
    blind_result = formula(records, watermark_day, as_of_day)
    assert blind_result == (), "superseded formula must miss stale modified day"
    boundary_records = (
        dict(changed[0], uid="lower-bound", modified=watermark_day),
        dict(changed[0], uid="inside-window", modified="2026-07-26"),
        dict(changed[0], uid="upper-bound", modified=as_of_day),
        dict(changed[0], uid="after-window", modified="2026-07-28"),
    )
    assert formula(boundary_records, watermark_day, as_of_day) == (
        "inside-window",
        "upper-bound",
    ), "formula boundary control must enforce both sides of its date window"
    return blind_result


class BootOrientCase(unittest.TestCase):
    def write_authority(
        self,
        fixture,
        *,
        agent="argus",
        party_uid=legacy.BOB,
        identity_uid=AGENT_UID,
        root_uid=ROOT_UID,
    ) -> None:
        fixture.write(
            f"vault/agents/{identity_uid}.md",
            _agent_source(
                agent,
                party_uid,
                identity_uid=identity_uid,
                root_uid=root_uid,
            ),
        )
        fixture.write(f"vault/files/{root_uid}.md", _root_source(agent, root_uid))
        fixture.write(
            f"vault/files/{party_uid}.md", _party_source(party_uid, agent)
        )

    def write_boot_snapshot(self, fixture, fx, records, viewer) -> None:
        """Commit the exact viewer-legal graph/circle/rank bytes under test."""

        projection = fx.projection()
        visible_result = projection.visible_segments(viewer)
        self.assertTrue(visible_result.ok, msg=visible_result.error)
        visible_segments = frozenset(visible_result.value)
        legal_records = tuple(
            sorted(
                (
                    dict(record)
                    for record in records
                    if record.get("segment") in visible_segments
                ),
                key=lambda record: record["uid"],
            )
        )
        legal_uids = frozenset(record["uid"] for record in legal_records)
        circle = tc.InMemoryStructuralIndex(fx._structures)
        projection_rows = []
        circle_rows = []
        rank_rows = []
        rank_index = fx.rank_index()
        for uid in sorted(legal_uids):
            adjacency = projection.adjacency(uid, viewer)
            authority = projection.authority(uid)
            self.assertTrue(adjacency.ok, msg=adjacency.error)
            self.assertTrue(authority.ok, msg=authority.error)
            structure = dict(circle.structure(uid))
            for field in ("member_of", "refs", "governed_by"):
                structure[field] = sorted(
                    value
                    for value in structure.get(field, ())
                    if value in legal_uids
                )
            projection_rows.append(
                {
                    "uid": uid,
                    "adjacency": sorted(
                        {
                            neighbor
                            for neighbor in adjacency.value
                            if neighbor in legal_uids
                        }
                    ),
                    "authority": authority.value,
                }
            )
            circle_rows.append(
                {
                    "uid": uid,
                    "structure": structure,
                    "children": sorted(
                        {
                            child
                            for child in circle.children_of(uid)
                            if child in legal_uids
                        }
                    ),
                }
            )
            rank_rows.append({"uid": uid, "record": rank_index.record(uid)})
        document = {
            "schema": 1,
            "viewer": {
                "principal_uid": viewer.principal_uid,
                "private_segment_uid": viewer.private_segment_uid,
            },
            "visible_segments": sorted(visible_segments),
            "records": list(legal_records),
            "projection": projection_rows,
            "circle_index": circle_rows,
            "rank_index": rank_rows,
        }
        fixture.write(
            "vault/boot-orientation-snapshot.json",
            json.dumps(document, allow_nan=False, separators=(",", ":"), sort_keys=True)
            + "\n",
        )

    def setUp(self) -> None:
        self.git = _GitFixture()
        self.addCleanup(self.git.cleanup)
        for number in range(5):
            uid = f"work{number:04d}"
            self.git.write(
                f"vault/files/{uid}.md",
                _entry_source(
                    uid,
                    type_="task",
                    segment=legacy.TEAM,
                    assigned_to="argus",
                    member_of=[ROOT_UID],
                ),
            )
        self.git.write(
            "vault/files/other001.md",
            _entry_source(
                "other001",
                type_="task",
                segment=legacy.TEAM,
                owner="someone-else",
            ),
        )
        self.git.write(
            "vault/files/hidden01.md",
            _entry_source(
                "hidden01",
                type_="task",
                segment=legacy.PRIV_ALICE,
                assigned_to="argus",
                member_of=[ROOT_UID],
            ),
        )
        self.write_authority(self.git)
        self.watermark = self.git.commit("base")
        self.git.write(
            "agents/argus/.tropo-capsule/memory/agent-memory.md",
            _memory_surface(self.watermark),
        )
        self.git.commit("commit-bound living transfer")
        self.git.write(
            "vault/files/hidden01.md",
            _entry_source(
                "hidden01",
                type_="task",
                segment=legacy.PRIV_ALICE,
                assigned_to="argus",
                member_of=[ROOT_UID],
            )
            + "hidden-only change\n",
        )
        self.hidden_commit = self.git.commit("hidden-only activity")
        self.git.write(
            "vault/files/work0000.md",
            _entry_source(
                "work0000",
                type_="task",
                segment=legacy.TEAM,
                assigned_to="argus",
                member_of=[ROOT_UID],
            )
            + "viewer-legal change\n",
        )
        self.git.write(
            "vault/files/other001.md",
            _entry_source(
                "other001",
                type_="task",
                segment=legacy.TEAM,
                owner="someone-else",
            )
            + "viewer-legal change\n",
        )
        snapshot_fx, snapshot_records = self.substrate()
        self.write_boot_snapshot(
            self.git, snapshot_fx, snapshot_records, legacy.bob()
        )
        self.as_of = self.git.commit("viewer-legal changes")

    def substrate(
        self,
        *,
        primary_segment=legacy.TEAM,
        hidden_segment=legacy.PRIV_ALICE,
        agent="argus",
        item_count=1,
        party_uid=legacy.BOB,
        identity_uid=AGENT_UID,
        root_uid=ROOT_UID,
        memory_path=None,
    ):
        roots = legacy._RootFactory()
        self.addCleanup(roots.cleanup)
        fx = legacy._OrientFixture(roots)
        fx.node(identity_uid, primary_segment, type_="agent", status="active")
        fx.node(root_uid, primary_segment, type_="project", status="active")
        fx.node(party_uid, primary_segment, type_="principal", status="active")
        fx.rel(identity_uid, root_uid, "member_of")
        for number in range(item_count):
            uid = f"work{number:04d}"
            fx.node(uid, primary_segment, type_="task", status="active")
            fx.rel(uid, root_uid, "member_of")
        fx.node("other001", primary_segment, type_="task", status="active")
        fx.node("hidden01", hidden_segment, type_="task", status="active")
        fx.rel("hidden01", root_uid, "member_of")
        records = [
            {
                "uid": identity_uid,
                "type": "agent",
                "agent": agent,
                "agent_root_uid": root_uid,
                "party_uid": party_uid,
                "member_of": [root_uid],
                "path": f"vault/agents/{identity_uid}.md",
                "segment": primary_segment,
                "status": "active",
                "modified": "2026-07-26",
            },
            {
                "uid": root_uid,
                "type": "project",
                "agent_slug": agent,
                "owner": agent,
                "path": f"vault/files/{root_uid}.md",
                "segment": primary_segment,
                "status": "active",
                "modified": "2026-07-26",
            },
            {
                "uid": party_uid,
                "type": "principal",
                "path": f"vault/files/{party_uid}.md",
                "segment": primary_segment,
                "status": "active",
                "modified": "2026-07-26",
            },
            {
                "uid": "other001",
                "type": "task",
                "owner": "someone-else",
                "path": "vault/files/other001.md",
                "segment": primary_segment,
                "status": "active",
                "modified": "2026-07-26",
            },
            {
                "uid": "hidden01",
                "type": "task",
                "assigned_to": agent,
                "member_of": [root_uid],
                "path": "vault/files/hidden01.md",
                "segment": hidden_segment,
                "status": "active",
                "modified": "2026-07-26",
            },
        ]
        for number in range(item_count):
            uid = f"work{number:04d}"
            records.append(
                {
                    "uid": uid,
                    "type": "task",
                    "assigned_to": agent,
                    "member_of": [root_uid],
                    "path": f"vault/files/{uid}.md",
                    "segment": primary_segment,
                    "status": "active",
                    "modified": "2026-07-26",
                }
            )
        if memory_path is not None:
            records[0]["memory_path"] = memory_path
        return fx, records

    def run_boot(
        self,
        *,
        viewer=None,
        observe_all=False,
        memory=None,
        primary_segment=legacy.TEAM,
        hidden_segment=legacy.PRIV_ALICE,
        agent="argus",
        item_count=1,
        memory_path=None,
        party_uid=None,
        identity_uid=AGENT_UID,
        root_uid=ROOT_UID,
        git_dag=None,
        as_of=None,
        snapshots=None,
    ):
        viewer = viewer or legacy.bob()
        party_uid = party_uid or viewer.principal_uid
        if identity_uid != AGENT_UID:
            default_identity = self.git.root / f"vault/agents/{AGENT_UID}.md"
            if default_identity.exists():
                default_identity.unlink()
        for number in range(item_count):
            uid = f"work{number:04d}"
            path = self.git.root / f"vault/files/{uid}.md"
            desired = _entry_source(
                uid,
                type_="task",
                segment=primary_segment,
                assigned_to=agent,
                member_of=[root_uid],
            )
            if not path.exists() or not path.read_text(encoding="utf-8").startswith(
                desired
            ):
                self.git.write(
                    f"vault/files/{uid}.md",
                    desired,
                )
        other_path = self.git.root / "vault/files/other001.md"
        other_source = _entry_source(
            "other001",
            type_="task",
            segment=primary_segment,
            owner="someone-else",
        )
        if not other_path.exists() or not other_path.read_text(
            encoding="utf-8"
        ).startswith(other_source):
            self.git.write(
                "vault/files/other001.md",
                other_source,
            )
        hidden_path = self.git.root / "vault/files/hidden01.md"
        hidden_source = _entry_source(
            "hidden01",
            type_="task",
            segment=hidden_segment,
            assigned_to=agent,
            member_of=[root_uid],
        )
        if not hidden_path.exists() or not hidden_path.read_text(
            encoding="utf-8"
        ).startswith(hidden_source):
            self.git.write(
                "vault/files/hidden01.md",
                hidden_source,
            )
        self.write_authority(
            self.git,
            agent=agent,
            party_uid=party_uid,
            identity_uid=identity_uid,
            root_uid=root_uid,
        )
        if memory is not None:
            self.git.write(
                f"agents/{agent}/.tropo-capsule/memory/agent-memory.md",
                memory,
            )
        fx, records = self.substrate(
            primary_segment=primary_segment,
            hidden_segment=hidden_segment,
            agent=agent,
            item_count=item_count,
            party_uid=party_uid,
            identity_uid=identity_uid,
            root_uid=root_uid,
            memory_path=memory_path,
        )
        if as_of is None:
            self.write_boot_snapshot(self.git, fx, records, viewer)
        if self.git.run("status", "--porcelain").stdout.strip():
            as_of = self.git.commit("fixture authority or memory override")
        elif memory is not None:
            as_of = self.git.run("rev-parse", "HEAD").stdout.strip()
        as_of = as_of or self.as_of
        boot_index = di.InMemoryBootIndex(snapshots or {as_of: records})
        projection = fx.projection()
        projection.index_as_of = as_of
        circle_index = tc.InMemoryStructuralIndex(
            fx._structures, index_as_of=as_of
        )
        rank_index = fx.rank_index()
        rank_index.index_as_of = as_of
        result = di.orient_boot(
            agent,
            viewer,
            as_of=as_of,
            projection=projection,
            circle_index=circle_index,
            rank_index=rank_index,
            boot_index=boot_index,
            observe_all=observe_all,
            repo_root=self.git.root,
            git_dag=git_dag,
        )
        return result, boot_index, records


class AC1BootSurfaceTests(BootOrientCase):
    def test_returns_three_parts_and_observe_all_defaults_false(self):
        memory = _memory_surface(self.watermark)
        result, _index, _records = self.run_boot(memory=memory)
        self.assertTrue(result.ok, msg=result.error)
        orientation = result.value
        expected_transfer = memory[
            memory.index("## §Living-Transfer-from-Predecessor") :
            memory.index("## §History")
        ]
        self.assertEqual(orientation.living_transfer, expected_transfer)
        self.assertIsInstance(orientation.delta_since_transfer, di.BootDelta)
        self.assertIsInstance(
            orientation.ranked_open_work, di.DeterministicOrientation
        )
        self.assertFalse(orientation.observe_all)
        self.assertEqual(orientation.ranked_open_work.uids(), ("work0000",))


class AC2BootDeterminismTests(BootOrientCase):
    def test_identical_inputs_serialize_byte_identically(self):
        first, _index, _records = self.run_boot()
        second, _index, _records = self.run_boot()
        self.assertTrue(first.ok and second.ok)
        self.assertEqual(first.value.canonical(), second.value.canonical())

    def test_import_aware_transitive_graph_rejects_talos_entropy_matrix(self):
        self.assertEqual(_reachable_determinism_violations(_determinism_modules()), set())
        mutations = (
            (
                "lib.distiller",
                "orient_boot",
                "import time as talos_clock\ntalos_clock.time()",
                "time.time",
            ),
            (
                "lib.distiller",
                "_compose_open_work",
                "from time import time_ns as wall_ns\nwall_ns()",
                "time.time_ns",
            ),
            (
                "lib.distiller_ranker",
                "rank_circle",
                "import time as clock\nclock.perf_counter()",
                "time.perf_counter",
            ),
            (
                "lib.task_circle",
                "draw_circle",
                "from time import process_time as cpu_time\ncpu_time()",
                "time.process_time",
            ),
            (
                "lib.distiller",
                "_verify_injected_boot_sources",
                "from time import monotonic as tick\ntick()",
                "time.monotonic",
            ),
            (
                "lib.distiller",
                "_load_committed_boot_sources",
                "import datetime as dt\ndt.datetime.now()",
                "datetime.datetime.now",
            ),
            (
                "lib.viewer_projection",
                "ViewerProjection.visible_segments",
                "from datetime import date as day\nday.today()",
                "datetime.date.today",
            ),
            (
                "lib.distiller",
                "_FrozenBootProjection.visible_segments",
                "import random as rng\nrng.random()",
                "random.random",
            ),
            (
                "lib.distiller",
                "_boot_source_identity",
                "from secrets import token_bytes as entropy\nentropy(1)",
                "secrets.token_bytes",
            ),
            (
                "lib.distiller",
                "_FrozenRankIndex.record",
                "import os as operating_system\noperating_system.urandom(1)",
                "os.urandom",
            ),
            (
                "lib.viewer_projection",
                "ViewerProjection.authority",
                "from uuid import uuid4 as make_id\nmake_id()",
                "uuid.uuid4",
            ),
        )
        for module_name, qualified_name, source, expected in mutations:
            with self.subTest(
                module=module_name,
                function=qualified_name,
                expression=expected,
            ):
                module_trees = _determinism_modules()
                node = _definition_nodes(module_trees[module_name][1])[qualified_name]
                node.body[0:0] = ast.parse(source).body
                self.assertIn(
                    expected,
                    _reachable_determinism_violations(module_trees),
                )

    def test_executed_wall_clock_plant_fails_on_reachable_compose_path(self):
        import time

        original = di._compose_open_work

        def planted_compose(*args, **kwargs):
            time.time()
            return original(*args, **kwargs)

        with mock.patch.object(
            di, "_compose_open_work", side_effect=planted_compose
        ), mock.patch.object(
            time, "time", side_effect=AssertionError("wall clock executed")
        ):
            with self.assertRaisesRegex(AssertionError, "wall clock executed"):
                self.run_boot()

    def test_assignment_alias_dataflow_rejects_chains_destructuring_and_unknowns(self):
        mutations = (
            (
                "lib.distiller",
                "orient_boot",
                "import time\nalias_clock = time.time_ns\nalias_clock()",
                {"time.time_ns"},
            ),
            (
                "lib.distiller",
                "_compose_open_work",
                "import time\nfirst = time.perf_counter\nsecond = first\nsecond()",
                {"time.perf_counter"},
            ),
            (
                "lib.distiller_ranker",
                "rank_circle",
                "import time\none = two = time.monotonic\ntwo()",
                {"time.monotonic"},
            ),
            (
                "lib.task_circle",
                "draw_circle",
                "import time\nimport secrets\n(clock, entropy) = (time.process_time, secrets.token_bytes)\nclock()\nentropy(1)",
                {"time.process_time", "secrets.token_bytes"},
            ),
            (
                "lib.distiller",
                "_load_committed_boot_sources",
                "import time\n((nested_clock,),) = ((time.time_ns,),)\nnested_clock()",
                {"time.time_ns"},
            ),
            (
                "lib.distiller",
                "_FrozenStructuralIndex.structure",
                "import time\nimport random\npair = (time.time_ns, random.random)\nalias_pair = pair\n(clock, random_call) = alias_pair\nclock()\nrandom_call()",
                {"time.time_ns", "random.random"},
            ),
            (
                "lib.distiller",
                "_FrozenStructuralIndex.__getattr__",
                "import time\n[*clock_list] = [time.time_ns]\nclock_list[0]()",
                {"time.time_ns"},
            ),
            (
                "lib.distiller",
                "_FrozenBootProjection.adjacency",
                "import time\nclock_table = (time.process_time,)\nclock_table[0]()",
                {"time.process_time"},
            ),
            (
                "lib.distiller",
                "_FrozenBootProjection.authority",
                "import time\n(alias_clock := time.monotonic_ns)()",
                {"time.monotonic_ns"},
            ),
            (
                "lib.distiller",
                "_verify_injected_boot_sources",
                "import time\nclock_module = time\nindirect = clock_module.time\nindirect()",
                {"time.time"},
            ),
            (
                "lib.viewer_projection",
                "ViewerProjection.visible_segments",
                "import time\nmember = 'time_ns'\nunknown_clock = getattr(time, member)\nunknown_clock()",
                {"time.*"},
            ),
            (
                "lib.viewer_projection",
                "ViewerProjection.filter_visible_uids",
                "import time\nmember = 'time_ns'\ntime.__dict__[member]()",
                {"time.__dict__.*"},
            ),
            (
                "lib.distiller",
                "_boot_source_identity",
                "import time\ndef clock_receiver():\n    return time\nclock_receiver().clock_gettime(0)",
                {"time.clock_gettime"},
            ),
            (
                "lib.task_circle",
                "derive_seeds",
                "import time\nreceiver = lambda: time\nreceiver().time_ns()",
                {"time.time_ns"},
            ),
            (
                "lib.distiller",
                "_FrozenStructuralIndex.__getattr__",
                "import os\ndef process_clock_receiver():\n    return os\nprocess_clock_receiver().times()",
                {"os.times"},
            ),
            (
                "lib.distiller",
                "_FrozenBootProjection.visible_segments",
                "import random\nrandom_call = random.random\nrandom_call()",
                {"random.random"},
            ),
            (
                "lib.distiller",
                "_FrozenRankIndex.record",
                "import os\nentropy = os.urandom\nentropy(1)",
                {"os.urandom"},
            ),
            (
                "lib.viewer_projection",
                "ViewerProjection.authority",
                "import uuid\nmake_id = uuid.uuid4\nmake_id()",
                {"uuid.uuid4"},
            ),
        )
        for module_name, qualified_name, source, expected in mutations:
            with self.subTest(module=module_name, mutation=qualified_name):
                module_trees = _determinism_modules()
                node = _definition_nodes(module_trees[module_name][1])[qualified_name]
                node.body[0:0] = ast.parse(source).body
                violations = _reachable_determinism_violations(module_trees)
                self.assertTrue(expected <= violations, msg=violations)

    def test_runtime_entropy_sandbox_precedes_reload_and_executes_semantic_plants(self):
        import os
        import sys
        import textwrap

        source = textwrap.dedent(
            r"""
            import contextlib
            import datetime as datetime_module
            import json
            import os
            import random
            import secrets
            import sys
            import time
            import types
            import uuid
            from unittest import mock

            class EntropyRead(AssertionError):
                pass

            def poison(*_args, **_kwargs):
                raise EntropyRead("runtime entropy source executed")

            class PoisonDateTime(datetime_module.datetime):
                @classmethod
                def now(cls, *_args, **_kwargs):
                    poison()
                @classmethod
                def today(cls, *_args, **_kwargs):
                    poison()
                @classmethod
                def utcnow(cls, *_args, **_kwargs):
                    poison()

            class PoisonDate(datetime_module.date):
                @classmethod
                def today(cls, *_args, **_kwargs):
                    poison()

            fake_datetime = types.ModuleType("datetime")
            for name in dir(datetime_module):
                setattr(fake_datetime, name, getattr(datetime_module, name))
            fake_datetime.datetime = PoisonDateTime
            fake_datetime.date = PoisonDate

            with contextlib.ExitStack() as stack:
                for module, names in (
                    (time, (
                        "time", "time_ns", "perf_counter", "perf_counter_ns",
                        "process_time", "process_time_ns", "monotonic",
                        "monotonic_ns",
                    )),
                    (random, (
                        "random", "randint", "randrange", "choice", "choices",
                        "shuffle", "getrandbits",
                    )),
                    (secrets, (
                        "choice", "randbelow", "randbits", "token_bytes",
                        "token_hex", "token_urlsafe",
                    )),
                    (uuid, ("uuid1", "uuid4")),
                ):
                    for name in names:
                        if hasattr(module, name):
                            stack.enter_context(
                                mock.patch.object(module, name, side_effect=poison)
                            )
                stack.enter_context(mock.patch.object(os, "urandom", side_effect=poison))
                stack.enter_context(mock.patch.dict(sys.modules, {"datetime": fake_datetime}))

                # Every reachable production module is first imported only
                # after the entropy sandbox is active.
                import lib.viewer_projection as vp
                import lib.distiller_query as dq
                import lib.task_circle as tc
                import lib.distiller_ranker as dr
                import lib.distiller as di

                class Projection:
                    index_as_of = "a" * 40
                    def visible_segments(self, viewer):
                        return di.Result.success(frozenset(("team",)))
                    def authority(self, uid):
                        return di.Result.success(1)
                    def adjacency(self, uid, viewer):
                        return di.Result.success(())
                    def filter_visible_uids(self, candidates, viewer):
                        return di.Result.success(
                            tuple(uid for uid in candidates if uid != "hidden01")
                        )

                class CircleIndex:
                    index_as_of = "a" * 40
                    def structure(self, uid):
                        return {
                            "type": "task",
                            "member_of": [],
                            "refs": [],
                            "governed_by": [],
                            "decay": None,
                        }
                    def children_of(self, uid):
                        return ()

                class RankIndex:
                    index_as_of = "a" * 40
                    def record(self, uid):
                        return {
                            "uid": uid,
                            "type": "task",
                            "status": "open",
                            "state": "active",
                            "decay": None,
                        }

                viewer = vp.Viewer(
                    principal_uid="b0b00001",
                    private_segment_uid="private-bob",
                )
                records = (
                    {
                        "uid": "visible1",
                        "type": "task",
                        "status": "open",
                        "assigned_to": "argus",
                        "member_of": ["root0001"],
                    },
                    {
                        "uid": "hidden01",
                        "type": "task",
                        "status": "open",
                        "assigned_to": "argus",
                        "member_of": ["root0001"],
                    },
                )
                result = di._compose_open_work(
                    "argus",
                    viewer,
                    "a" * 40,
                    False,
                    records,
                    "root0001",
                    projection=Projection(),
                    circle_index=CircleIndex(),
                    rank_index=RankIndex(),
                )
                if not result.ok or result.value.uids() != ("visible1",):
                    raise AssertionError(result.error if not result.ok else result.value.uids())

                plants = {
                    "assignment": "import time\nclock = time.time_ns\nclock()",
                    "starred": "import time\n[*clocks] = [time.time_ns]\nclocks[0]()",
                    "indexed": "import time\nclocks = [time.perf_counter]\nclocks[0]()",
                    "walrus": "import time\n(clock := time.monotonic)()",
                    "unknown": "import time\ngetattr(time, ''.join(('time', '_ns')))()",
                    "datetime": "import datetime\ndatetime.datetime.now()",
                    "random": "import random\nrandom.random()",
                    "secrets": "import secrets\nsecrets.token_bytes(1)",
                    "urandom": "import os\nos.urandom(1)",
                    "uuid": "import uuid\nuuid.uuid4()",
                }
                executed = []
                for label, plant in plants.items():
                    try:
                        exec(compile(plant, "<entropy-" + label + ">", "exec"), {})
                    except EntropyRead:
                        executed.append(label)
                    else:
                        raise AssertionError("plant escaped sandbox: " + label)
                print(json.dumps({
                    "compose_uids": result.value.uids(),
                    "plants": executed,
                }, sort_keys=True))
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", source],
            cwd=str(Path(di.__file__).parents[2]),
            env={
                **dict(os.environ),
                "PYTHONPATH": os.pathsep.join(
                    (str(Path(di.__file__).parents[1]), str(Path(di.__file__).parents[3]))
                ),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout={completed.stdout}\nstderr={completed.stderr}",
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["compose_uids"], ["visible1"])
        self.assertEqual(
            payload["plants"],
            [
                "assignment",
                "starred",
                "indexed",
                "walrus",
                "unknown",
                "datetime",
                "random",
                "secrets",
                "urandom",
                "uuid",
            ],
        )

    def test_full_orient_boot_is_metamorphic_under_varying_entropy_receivers(self):
        import os
        import sys
        import textwrap

        baseline, _index, _records = self.run_boot(item_count=3)
        self.assertTrue(baseline.ok, msg=baseline.error)
        as_of = baseline.value.as_of
        viewer = legacy.bob()
        source = textwrap.dedent(
            r"""
            import contextlib
            import datetime as datetime_module
            import json
            import os
            import random
            import secrets
            import subprocess
            import sys
            import tempfile
            import time
            import types
            import uuid
            from unittest import mock

            variant = int(os.environ["ENTROPY_VARIANT"])
            planted = os.environ["PARITY_PLANT"] == "1"
            seconds = float(100 + variant)
            nanoseconds = 100000000000 + variant
            original_times = os.times()

            class VariantDateTime(datetime_module.datetime):
                @classmethod
                def now(cls, tz=None):
                    value = cls(2030 + variant, 1 + variant, 2 + variant, tzinfo=tz)
                    return value
                @classmethod
                def today(cls):
                    return cls(2030 + variant, 1 + variant, 2 + variant)
                @classmethod
                def utcnow(cls):
                    return cls(2030 + variant, 1 + variant, 2 + variant)

            class VariantDate(datetime_module.date):
                @classmethod
                def today(cls):
                    return cls(2030 + variant, 1 + variant, 2 + variant)

            fake_datetime = types.ModuleType("datetime")
            for name in dir(datetime_module):
                setattr(fake_datetime, name, getattr(datetime_module, name))
            fake_datetime.datetime = VariantDateTime
            fake_datetime.date = VariantDate

            def variant_randrange(start, stop=None, step=1):
                if stop is None:
                    start, stop = 0, start
                return start + ((variant * step) % max(step, stop - start))

            def variant_choices(population, *args, **kwargs):
                count = kwargs.get("k", 1)
                return [population[variant % len(population)] for _ in range(count)]

            def variant_shuffle(values, *_args, **_kwargs):
                if variant % 2:
                    values.reverse()

            def variant_token_bytes(length=None):
                length = 32 if length is None else length
                return bytes(((variant + 17) % 256,)) * length

            def variant_times():
                value = seconds
                return type(original_times)((value, value, value, value, value))

            with contextlib.ExitStack() as stack:
                seconds_names = (
                    "time", "perf_counter", "process_time", "monotonic",
                    "thread_time", "clock_gettime",
                )
                nanos_names = (
                    "time_ns", "perf_counter_ns", "process_time_ns",
                    "monotonic_ns", "thread_time_ns", "clock_gettime_ns",
                )
                for name in seconds_names:
                    if hasattr(time, name):
                        stack.enter_context(
                            mock.patch.object(time, name, return_value=seconds)
                        )
                for name in nanos_names:
                    if hasattr(time, name):
                        stack.enter_context(
                            mock.patch.object(time, name, return_value=nanoseconds)
                        )
                stack.enter_context(mock.patch.object(os, "times", side_effect=variant_times))
                stack.enter_context(
                    mock.patch.object(os, "urandom", side_effect=variant_token_bytes)
                )
                stack.enter_context(
                    mock.patch.object(random, "random", return_value=variant / 10.0)
                )
                stack.enter_context(
                    mock.patch.object(random, "randint", side_effect=lambda a, b: a + variant % (b - a + 1))
                )
                stack.enter_context(
                    mock.patch.object(random, "randrange", side_effect=variant_randrange)
                )
                stack.enter_context(
                    mock.patch.object(random, "choice", side_effect=lambda values: values[variant % len(values)])
                )
                stack.enter_context(
                    mock.patch.object(random, "choices", side_effect=variant_choices)
                )
                stack.enter_context(
                    mock.patch.object(random, "shuffle", side_effect=variant_shuffle)
                )
                stack.enter_context(
                    mock.patch.object(random, "getrandbits", return_value=variant + 1)
                )
                stack.enter_context(
                    mock.patch.object(secrets, "choice", side_effect=lambda values: values[variant % len(values)])
                )
                stack.enter_context(
                    mock.patch.object(secrets, "randbelow", side_effect=lambda upper: variant % upper)
                )
                stack.enter_context(
                    mock.patch.object(secrets, "randbits", return_value=variant + 1)
                )
                stack.enter_context(
                    mock.patch.object(secrets, "token_bytes", side_effect=variant_token_bytes)
                )
                stack.enter_context(
                    mock.patch.object(secrets, "token_hex", side_effect=lambda length=None: variant_token_bytes(length).hex())
                )
                stack.enter_context(
                    mock.patch.object(secrets, "token_urlsafe", return_value="variant-" + str(variant))
                )
                stack.enter_context(
                    mock.patch.object(uuid, "uuid1", return_value=uuid.UUID(int=variant + 1))
                )
                stack.enter_context(
                    mock.patch.object(uuid, "uuid4", return_value=uuid.UUID(int=variant + 17))
                )
                stack.enter_context(mock.patch.dict(sys.modules, {"datetime": fake_datetime}))

                # Reachable modules first execute only after every varying
                # entropy implementation, including os.times, is installed.
                import lib.viewer_projection as vp
                import lib.distiller_ranker as dr
                import lib.task_circle as tc
                import lib.distiller as di

                entropy_probe = {
                    "datetime": fake_datetime.datetime.now().isoformat(),
                    "random": random.random(),
                    "secret": secrets.token_bytes(1).hex(),
                    "urandom": os.urandom(1).hex(),
                    "uuid": str(uuid.uuid4()),
                }
                repo = os.environ["ORIENT_REPO"]
                as_of = os.environ["ORIENT_AS_OF"]
                viewer = vp.Viewer(
                    principal_uid=os.environ["ORIENT_VIEWER"],
                    private_segment_uid=os.environ["ORIENT_PRIVATE_SEGMENT"],
                )
                git_dag = di.SubprocessGitDAG(repo)
                (
                    _snapshot_bytes,
                    _visible_segments,
                    records,
                    projection,
                    circle_index,
                    rank_index,
                    _expected,
                ) = di._load_committed_boot_sources(
                    as_of=as_of,
                    viewer=viewer,
                    git_dag=git_dag,
                )

                class ClockReceiver:
                    def __call__(self):
                        return time

                receiver = ClockReceiver()
                receiver_value = receiver().time()
                if receiver_value != seconds:
                    raise AssertionError("receiver-call clock was not poisoned")

                class ProcessClockReceiver:
                    def __call__(self):
                        return os

                process_times = ProcessClockReceiver()().times()
                if process_times.user != seconds:
                    raise AssertionError("receiver-call os.times was not poisoned")

                class InjectedCircleIndex:
                    index_as_of = as_of
                    def structure(self, uid):
                        return circle_index.structure(uid)
                    def children_of(self, uid):
                        return tuple(circle_index._children.get(uid, ()))

                if planted:
                    original_rank_circle = di.rank_circle
                    def parity_rank_circle(*args, **kwargs):
                        ranked = original_rank_circle(*args, **kwargs)
                        if ranked.ok and int(receiver().time()) % 2:
                            value = ranked.value
                            ranked = di.Result.success(
                                dr.RankedCircle(
                                    task_uid=value.task_uid,
                                    weights=value.weights,
                                    tilt=value.tilt,
                                    members=tuple(reversed(value.members)),
                                )
                            )
                        return ranked
                    di.rank_circle = parity_rank_circle

                entrypoint_calls = 0
                def invoke_orient_boot():
                    global entrypoint_calls
                    entrypoint_calls += 1
                    return di.orient_boot(
                        "argus",
                        viewer,
                        as_of=as_of,
                        projection=projection,
                        circle_index=InjectedCircleIndex(),
                        rank_index=rank_index,
                        boot_index=di.InMemoryBootIndex({as_of: records}),
                        repo_root=repo,
                        git_dag=git_dag,
                    )

                result = invoke_orient_boot()
                if not result.ok:
                    raise AssertionError(result.error)
                uids = result.value.ranked_open_work.uids()
                if len(uids) < 3:
                    raise AssertionError("metamorphic fixture needs at least three ranked items")
                print(json.dumps({
                    "canonical": result.value.canonical(),
                    "entropy_probe": entropy_probe,
                    "entrypoint_calls": entrypoint_calls,
                    "process_user_time": process_times.user,
                    "receiver_value": receiver_value,
                    "uids": uids,
                }, sort_keys=True))
            """
        )

        def run_variant(variant, *, planted=False):
            environment = {
                **dict(os.environ),
                "ENTROPY_VARIANT": str(variant),
                "PARITY_PLANT": "1" if planted else "0",
                "ORIENT_REPO": str(self.git.root),
                "ORIENT_AS_OF": as_of,
                "ORIENT_VIEWER": viewer.principal_uid,
                "ORIENT_PRIVATE_SEGMENT": viewer.private_segment_uid,
                "PYTHONPATH": os.pathsep.join(
                    (
                        str(Path(di.__file__).parents[1]),
                        str(Path(di.__file__).parents[3]),
                    )
                ),
            }
            completed = subprocess.run(
                [sys.executable, "-c", source],
                cwd=str(Path(di.__file__).parents[2]),
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"variant={variant} planted={planted}\n"
                f"stdout={completed.stdout}\nstderr={completed.stderr}",
            )
            return json.loads(completed.stdout)

        outputs = tuple(run_variant(variant) for variant in range(3))
        self.assertTrue(all(output["entrypoint_calls"] == 1 for output in outputs))
        self.assertTrue(all(len(output["uids"]) >= 3 for output in outputs))
        self.assertEqual(
            tuple(output["receiver_value"] for output in outputs),
            (100.0, 101.0, 102.0),
        )
        self.assertEqual(
            tuple(output["process_user_time"] for output in outputs),
            (100.0, 101.0, 102.0),
        )
        for field in ("datetime", "random", "secret", "urandom", "uuid"):
            self.assertEqual(
                len({output["entropy_probe"][field] for output in outputs}),
                3,
            )
        canonical_bytes = tuple(
            output["canonical"].encode("utf-8") for output in outputs
        )
        self.assertEqual(len(set(canonical_bytes)), 1)
        self.assertEqual(len({tuple(output["uids"]) for output in outputs}), 1)

        planted_outputs = tuple(
            run_variant(variant, planted=True) for variant in (0, 1)
        )
        with self.assertRaises(AssertionError):
            self.assertEqual(
                len(
                    {
                        output["canonical"].encode("utf-8")
                        for output in planted_outputs
                    }
                ),
                1,
            )


class AC3ReachabilityAndWatermarkTests(BootOrientCase):
    def test_reachable_delta_uses_commit_range_and_viewer_legal_scope(self):
        result, _index, _records = self.run_boot()
        self.assertTrue(result.ok, msg=result.error)
        delta = result.value.delta_since_transfer
        self.assertIsNotNone(delta)
        self.assertEqual(tuple(item.uid for item in delta.items), ("work0000",))
        self.assertEqual(delta.commits, ())
        self.assertEqual(delta.items[0].commits, ())
        canonical = result.value.canonical()
        self.assertNotIn('"commits"', canonical)
        self.assertNotIn(self.hidden_commit, canonical)
        self.assertNotIn('"commit_count"', canonical)
        compatibility_item = di.BootDeltaItem(
            "visible01", "vault/files/visible01.md", (self.hidden_commit,)
        )
        compatibility_delta = di.BootDelta(
            (self.hidden_commit,), (compatibility_item,)
        )
        self.assertEqual(compatibility_item.commits, ())
        self.assertEqual(compatibility_delta.commits, ())

    def test_absent_malformed_and_day_only_watermarks_fail_closed_typed(self):
        cases = {
            "absent": (
                "---\nagent: argus\n---\n\n"
                "## §Living-Transfer-from-Predecessor\n\nhandoff\n",
                di.BootOrientationErrorCode.WATERMARK_ABSENT,
            ),
            "malformed": (
                _memory_surface("not-a-commit"),
                di.BootOrientationErrorCode.WATERMARK_MALFORMED,
            ),
            "day-only-commit": (
                _memory_surface("2026-07-26"),
                di.BootOrientationErrorCode.WATERMARK_DAY_ONLY,
            ),
            "day-only-event-position": (
                _memory_surface(self.watermark, event_position="2026-07-26"),
                di.BootOrientationErrorCode.WATERMARK_DAY_ONLY,
            ),
        }
        for label, (memory, code) in cases.items():
            with self.subTest(label=label):
                result, _index, _records = self.run_boot(memory=memory)
                self.assertFalse(result.ok)
                self.assertIsInstance(result.error, di.BootOrientationError)
                self.assertEqual(result.error.code, code)
                self.assertIsNone(result.value)


class AC4BootPrivacyTests(BootOrientCase):
    def test_privacy_floor_covers_transfer_delta_and_rank_under_observe_all(self):
        with mock.patch.object(
            di, "draw_circle", wraps=di.draw_circle
        ) as circle_draw, mock.patch.object(
            di, "rank_circle", wraps=di.rank_circle
        ) as circle_rank:
            result, boot_index, _records = self.run_boot(observe_all=True)
        self.assertTrue(result.ok, msg=result.error)
        orientation = result.value
        self.assertEqual(circle_draw.call_args.args[1], legacy.bob())
        self.assertEqual(circle_rank.call_args.args[2], legacy.bob())
        self.assertEqual(
            boot_index.visible_calls,
            [
                (
                    self.as_of,
                    frozenset({legacy.OS, legacy.TEAM, legacy.PRIV_BOB}),
                )
            ],
        )
        self.assertNotIn("hidden01", orientation.living_transfer)
        self.assertNotIn(
            "hidden01",
            tuple(item.uid for item in orientation.delta_since_transfer.items),
        )
        self.assertNotIn("hidden01", orientation.ranked_open_work.uids())
        self.assertNotIn("hidden01", orientation.canonical())
        self.assertIn("other001", orientation.ranked_open_work.uids())


class AC5TeamPrivateZeroModelTests(BootOrientCase):
    def test_team_and_private_segments_return_all_parts_with_zero_model_calls(self):
        cases = (
            (legacy.bob(), legacy.TEAM, legacy.PRIV_ALICE),
            (legacy.alice(), legacy.PRIV_ALICE, legacy.PRIV_BOB),
        )
        with mock.patch.object(
            llm,
            "call_locked",
            side_effect=AssertionError("orient_boot must never call a model"),
        ) as provider:
            for viewer, primary, hidden in cases:
                with self.subTest(segment=primary):
                    result, _index, _records = self.run_boot(
                        viewer=viewer,
                        primary_segment=primary,
                        hidden_segment=hidden,
                    )
                    self.assertTrue(result.ok, msg=result.error)
                    self.assertTrue(result.value.living_transfer)
                    self.assertIsInstance(
                        result.value.delta_since_transfer, di.BootDelta
                    )
                    self.assertIsInstance(
                        result.value.ranked_open_work,
                        di.DeterministicOrientation,
                    )
                    self.assertNotIn("hidden01", result.value.living_transfer)
                    self.assertNotIn(
                        "hidden01",
                        tuple(
                            item.uid
                            for item in result.value.delta_since_transfer.items
                        ),
                    )
                    self.assertNotIn(
                        "hidden01", result.value.ranked_open_work.uids()
                    )
        provider.assert_not_called()


class AC6UnreachableTransferTests(BootOrientCase):
    def divergent_replay(self):
        divergent = _GitFixture()
        self.addCleanup(divergent.cleanup)
        self.write_authority(divergent)
        divergent.write(
            "vault/files/work0000.md",
            _entry_source(
                "work0000",
                type_="task",
                segment=legacy.TEAM,
                assigned_to="argus",
                member_of=[ROOT_UID],
            ),
        )
        divergent.write(
            "vault/files/other001.md",
            _entry_source(
                "other001",
                type_="task",
                segment=legacy.TEAM,
                owner="someone-else",
            ),
        )
        divergent.write(
            "vault/files/hidden01.md",
            _entry_source(
                "hidden01",
                type_="task",
                segment=legacy.PRIV_ALICE,
                assigned_to="argus",
                member_of=[ROOT_UID],
            ),
        )
        base = divergent.commit("shared base")
        divergent.run("checkout", "-b", "transfer-line")
        divergent.write(
            "vault/files/work0000.md",
            _entry_source(
                "work0000",
                type_="task",
                segment=legacy.TEAM,
                assigned_to="argus",
                member_of=[ROOT_UID],
            )
            + "transfer-line state before handoff\n",
        )
        transfer_commit = divergent.commit("stranded transfer state")
        divergent.write(
            "agents/argus/.tropo-capsule/memory/agent-memory.md",
            _memory_surface(transfer_commit),
        )
        divergent.commit("living transfer authored on transfer line")
        divergent.run("checkout", "main")
        divergent.write(
            "agents/argus/.tropo-capsule/memory/agent-memory.md",
            _memory_surface(transfer_commit),
        )
        divergent.write(
            "vault/files/work0000.md",
            _entry_source(
                "work0000",
                type_="task",
                segment=legacy.TEAM,
                assigned_to="argus",
                member_of=[ROOT_UID],
            )
            + "main moved without transfer\n",
        )
        snapshot_fx, snapshot_records = self.substrate()
        self.write_boot_snapshot(
            divergent, snapshot_fx, snapshot_records, legacy.bob()
        )
        as_of = divergent.commit("booting line")

        old_git, old_watermark, old_as_of = self.git, self.watermark, self.as_of
        self.git, self.watermark, self.as_of = divergent, transfer_commit, as_of
        try:
            result, _index, records = self.run_boot(as_of=as_of)
        finally:
            self.git, self.watermark, self.as_of = old_git, old_watermark, old_as_of
        return result, records, transfer_commit, as_of, base, divergent.root

    def test_nonancestor_transfer_sets_explicit_named_divergence(self):
        with mock.patch.object(
            di.SubprocessGitDAG,
            "commits_between",
            side_effect=AssertionError(
                "unreachable transfer must not compute a normal delta"
            ),
        ) as delta_read:
            result, _records, transfer_commit, as_of, _base, _root = (
                self.divergent_replay()
            )
        delta_read.assert_not_called()
        self.assertTrue(result.ok, msg=result.error)
        divergence = result.value.unreachable_transfer_divergence
        self.assertIsNotNone(divergence)
        self.assertEqual(divergence.kind, "unreachable-transfer")
        self.assertEqual(divergence.transfer_commit, transfer_commit)
        self.assertEqual(divergence.as_of, as_of)
        self.assertIsNone(result.value.delta_since_transfer)

    def test_governing_plant_discriminates_stale_day_record_across_actual_days(self):
        watermark_day = "2026-07-25"
        as_of_day = "2026-07-27"
        changed_path = "vault/files/work0000.md"
        stale_source = _entry_source(
            "work0000",
            type_="task",
            segment=legacy.TEAM,
            assigned_to="argus",
            member_of=[ROOT_UID],
        ).replace("modified: '2026-07-26'", f"modified: '{watermark_day}'")
        self.git.write(changed_path, stale_source + "\nWatermark tree bytes.\n")
        for relative in ("vault/files/other001.md", "vault/files/hidden01.md"):
            source = (self.git.root / relative).read_text(encoding="utf-8")
            self.git.write(
                relative,
                source.replace(
                    "modified: '2026-07-26'",
                    f"modified: '{watermark_day}'",
                ),
            )
        watermark = self.git.commit(
            "cross-day governing watermark",
            date=f"{watermark_day}T09:00:00+00:00",
        )

        self.git.write(changed_path, stale_source + "\nChanged after watermark.\n")
        self.git.write(
            "agents/argus/.tropo-capsule/memory/agent-memory.md",
            _memory_surface(watermark),
        )
        fx, records = self.substrate()
        for record in records:
            record["modified"] = watermark_day
        self.write_boot_snapshot(self.git, fx, records, legacy.bob())
        as_of = self.git.commit(
            "cross-day stale-frontmatter change",
            date=f"{as_of_day}T17:00:00+00:00",
        )

        topology = di.SubprocessGitDAG(self.git.root)
        projection = fx.projection()
        projection.index_as_of = as_of
        circle_index = tc.InMemoryStructuralIndex(
            fx._structures, index_as_of=as_of
        )
        rank_index = fx.rank_index()
        rank_index.index_as_of = as_of
        result = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=as_of,
            projection=projection,
            circle_index=circle_index,
            rank_index=rank_index,
            boot_index=di.InMemoryBootIndex({as_of: records}),
            repo_root=self.git.root,
            git_dag=topology,
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertTrue(topology.is_ancestor(watermark, as_of))
        changed_commits = topology.commits_between(watermark, as_of)
        self.assertTrue(changed_commits)
        self.assertEqual(changed_commits[-1], as_of)
        raw_changed_paths = topology.changed_paths(changed_commits)
        self.assertTrue(raw_changed_paths)
        self.assertIn(as_of, raw_changed_paths.get(changed_path, ()))
        delta_uids = tuple(item.uid for item in result.value.delta_since_transfer.items)
        self.assertEqual(delta_uids, ("work0000",))

        def commit_day(commit):
            author_day, committer_day = topology._run(
                "show", "-s", "--format=%aI%n%cI", commit
            ).stdout.splitlines()
            author_day = author_day.split("T", 1)[0]
            committer_day = committer_day.split("T", 1)[0]
            self.assertEqual(author_day, committer_day)
            return author_day

        old_delta = _criterion6_reachable_evidence(
            records,
            changed_uid="work0000",
            changed_path=changed_path,
            changed_commit=as_of,
            changed_commits=changed_commits,
            raw_changed_paths=raw_changed_paths,
            before_bytes=topology.read_bytes(watermark, changed_path),
            after_bytes=topology.read_bytes(as_of, changed_path),
            watermark_day=commit_day(watermark),
            changed_day=commit_day(as_of),
            as_of_day=commit_day(as_of),
            new_delta_uids=delta_uids,
        )
        self.assertEqual(old_delta, ())

    def test_governing_plant_rejects_talos_class_variant_mutations(self):
        changed = {
            "uid": "work0000",
            "path": "vault/files/work0000.md",
            "modified": "2026-07-25",
        }
        valid = {
            "records": (changed,),
            "changed_uid": "work0000",
            "changed_path": "vault/files/work0000.md",
            "changed_commit": "a" * 40,
            "changed_commits": ("a" * 40,),
            "raw_changed_paths": {
                "vault/files/work0000.md": ("a" * 40,)
            },
            "before_bytes": b"before",
            "after_bytes": b"after",
            "watermark_day": "2026-07-25",
            "changed_day": "2026-07-27",
            "as_of_day": "2026-07-27",
            "new_delta_uids": ("work0000",),
        }

        def greater_equal_lower(records, watermark_day, as_of_day):
            return tuple(
                record["uid"]
                for record in records
                if isinstance(record.get("modified"), str)
                and watermark_day <= record["modified"] <= as_of_day
            )

        def upper_only(records, _watermark_day, as_of_day):
            return tuple(
                record["uid"]
                for record in records
                if isinstance(record.get("modified"), str)
                and record["modified"] <= as_of_day
            )

        def open_upper(records, watermark_day, as_of_day):
            return tuple(
                record["uid"]
                for record in records
                if isinstance(record.get("modified"), str)
                and watermark_day < record["modified"] < as_of_day
            )

        def missing_upper_bound(records, watermark_day, _as_of_day):
            return tuple(
                record["uid"]
                for record in records
                if isinstance(record.get("modified"), str)
                and watermark_day < record["modified"]
            )

        mutation_cases = (
            ("empty-input", {**valid, "records": ()}),
            ("garbage-input", {**valid, "records": ({"garbage": True},)}),
            (
                "missing-modified",
                {**valid, "records": ({key: value for key, value in changed.items() if key != "modified"},)},
            ),
            ("fixture-not-changed", {**valid, "raw_changed_paths": {}}),
            ("tree-not-changed", {**valid, "after_bytes": b"before"}),
            ("empty-new-delta", {**valid, "new_delta_uids": ()}),
            (
                "re-dated-frontmatter",
                {
                    **valid,
                    "records": ({**changed, "modified": "2026-07-27"},),
                },
            ),
            ("re-dated-commit", {**valid, "changed_day": "2026-07-26"}),
            (
                "same-actual-days",
                {
                    **valid,
                    "watermark_day": "2026-07-27",
                },
            ),
            (
                "wrong-change-commit",
                {
                    **valid,
                    "raw_changed_paths": {
                        "vault/files/work0000.md": ("b" * 40,)
                    },
                },
            ),
            ("constant-formula", {**valid, "formula": lambda *_args: ()}),
            (
                "greater-equal-lower-formula",
                {**valid, "formula": greater_equal_lower},
            ),
            ("upper-only-formula", {**valid, "formula": upper_only}),
            ("open-upper-formula", {**valid, "formula": open_upper}),
            ("missing-upper-formula", {**valid, "formula": missing_upper_bound}),
        )
        for label, arguments in mutation_cases:
            with self.subTest(mutation=label), self.assertRaises(AssertionError):
                _criterion6_reachable_evidence(**arguments)


class AC7RankPermutationPropertyTests(BootOrientCase):
    def test_ranked_output_is_a_permutation_for_generated_combinations(self):
        for agent in ("argus", "vela"):
            for viewer in (legacy.alice(), legacy.bob()):
                for count in range(5):
                    with self.subTest(
                        agent=agent,
                        viewer=viewer.principal_uid,
                        count=count,
                    ):
                        memory = _memory_surface(self.watermark).replace(
                            "agent: argus", f"agent: {agent}"
                        )
                        result, _index, _records = self.run_boot(
                            agent=agent,
                            viewer=viewer,
                            item_count=count,
                            memory=memory,
                        )
                        self.assertTrue(result.ok, msg=result.error)
                        orientation = result.value.ranked_open_work
                        self.assertEqual(
                            sorted(orientation.uids()),
                            sorted(orientation.circle.uids()),
                        )
                        self.assertEqual(
                            len(orientation.uids()),
                            len(set(orientation.circle.uids())),
                        )


class AC8SeedResolutionTests(BootOrientCase):
    def test_hidden_assigned_seed_neither_appears_nor_influences_circle_or_rank(self):
        with_hidden, _index, _records = self.run_boot()
        self.assertTrue(with_hidden.ok, msg=with_hidden.error)
        fx, all_records = self.substrate()
        del fx._records["hidden01"]
        del fx._node_root["hidden01"]
        del fx._structures["hidden01"]
        del fx._rankrecs["hidden01"]
        fx._edges = [
            edge for edge in fx._edges if "hidden01" not in edge
        ]
        records = [
            record for record in all_records if record["uid"] != "hidden01"
        ]
        projection = fx.projection()
        projection.index_as_of = self.as_of
        rank_index = fx.rank_index()
        rank_index.index_as_of = self.as_of
        without_hidden = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=self.as_of,
            projection=projection,
            circle_index=tc.InMemoryStructuralIndex(
                fx._structures, index_as_of=self.as_of
            ),
            rank_index=rank_index,
            boot_index=di.InMemoryBootIndex({self.as_of: records}),
            repo_root=self.git.root,
        )
        self.assertTrue(without_hidden.ok, msg=without_hidden.error)
        self.assertEqual(
            with_hidden.value.ranked_open_work.canonical(),
            without_hidden.value.ranked_open_work.canonical(),
        )
        self.assertNotIn("hidden01", with_hidden.value.ranked_open_work.uids())

    def test_compose_establishes_visibility_and_authority_before_record_access(self):
        fx, records = self.substrate()
        source_projection = fx.projection()
        events = []

        class OrderedRecords:
            def __iter__(inner_self):
                events.append("records")
                self.assertEqual(events[:3], ["visible_segments", "authority", "records"])
                return iter(records)

            def __len__(inner_self):
                return len(records)

        class OrderedProjection:
            index_as_of = self.as_of

            def visible_segments(inner_self, viewer):
                events.append("visible_segments")
                return source_projection.visible_segments(viewer)

            def authority(inner_self, uid):
                events.append("authority")
                return source_projection.authority(uid)

            def filter_visible_uids(inner_self, candidates, viewer):
                events.append("filter_visible_uids")
                return source_projection.filter_visible_uids(candidates, viewer)

            def adjacency(inner_self, uid, viewer):
                return source_projection.adjacency(uid, viewer)

        circle_index = tc.InMemoryStructuralIndex(
            fx._structures, index_as_of=self.as_of
        )
        rank_index = fx.rank_index()
        rank_index.index_as_of = self.as_of
        result = di._compose_open_work(
            "argus",
            legacy.bob(),
            self.as_of,
            False,
            OrderedRecords(),
            ROOT_UID,
            projection=OrderedProjection(),
            circle_index=circle_index,
            rank_index=rank_index,
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertEqual(
            events[:4],
            ["visible_segments", "authority", "records", "filter_visible_uids"],
        )

    def test_compose_guard_kills_all_talos_raw_seed_bypass_families(self):
        import copy

        baseline = ast.parse(Path(di.__file__).read_text(encoding="utf-8"))
        self.assertEqual(_compose_seed_guard_violations(baseline), set())

        def compose(tree):
            return _definition_nodes(tree)["_compose_open_work"]

        def move_records_before_floor(tree):
            node = compose(tree)
            candidate = next(
                statement
                for statement in node.body
                if isinstance(statement, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "candidate_uids"
                    for target in statement.targets
                )
            )
            node.body.remove(candidate)
            node.body.insert(0, candidate)

        def delete_authority_floor(tree):
            node = compose(tree)
            node.body = [
                statement
                for statement in node.body
                if not any(
                    isinstance(call, ast.Call)
                    and _dotted_call(call) == "projection.authority"
                    for call in ast.walk(statement)
                )
            ]

        def replace_filter_with_raw_scan(tree):
            approval = _definition_nodes(tree)["ViewerApprovedUIDs.from_projection"]
            for item in ast.walk(approval):
                if isinstance(item, ast.Attribute) and item.attr == "filter_visible_uids":
                    item.attr = "raw_records"
                    return
            self.fail("filter_visible_uids mutation target absent")

        def remove_prevalidated_query_seeds(tree):
            draw = next(
                call
                for call in ast.walk(compose(tree))
                if isinstance(call, ast.Call) and _dotted_call(call) == "draw_circle"
            )
            draw.keywords = [
                keyword for keyword in draw.keywords if keyword.arg != "query_seeds"
            ]

        def substitute_raw_projection(tree):
            draw = next(
                call
                for call in ast.walk(compose(tree))
                if isinstance(call, ast.Call) and _dotted_call(call) == "draw_circle"
            )
            next(
                keyword for keyword in draw.keywords if keyword.arg == "projection"
            ).value = ast.Name(id="raw_projection", ctx=ast.Load())

        mutations = (
            (
                "record-scan-before-floor",
                move_records_before_floor,
                "order:visibility-authority-records-filter-seed-draw-rank",
            ),
            (
                "authority-floor-deleted",
                delete_authority_floor,
                "missing:projection.authority",
            ),
            (
                "raw-record-filter-bypass",
                replace_filter_with_raw_scan,
                "approval:missing-projection-filter",
            ),
            (
                "draw-fallback-without-prevalidated-seeds",
                remove_prevalidated_query_seeds,
                "draw-binding:query_seeds",
            ),
            (
                "raw-projection-substitution",
                substitute_raw_projection,
                "draw-binding:projection",
            ),
        )
        for label, mutate, expected in mutations:
            with self.subTest(mutation=label):
                tree = copy.deepcopy(baseline)
                mutate(tree)
                self.assertIn(expected, _compose_seed_guard_violations(tree))

    def test_typed_viewer_approval_kills_post_filter_overwrite_union_and_bypass(self):
        import copy
        import dataclasses

        baseline = ast.parse(Path(di.__file__).read_text(encoding="utf-8"))
        self.assertEqual(_compose_seed_guard_violations(baseline), set())

        def approved_assignment(tree):
            return next(
                statement
                for statement in _definition_nodes(tree)[
                    "ViewerApprovedUIDs.from_projection"
                ].body
                if isinstance(statement, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "approved"
                    for target in statement.targets
                )
            )

        def overwrite_with_candidates(tree):
            approved_assignment(tree).value = ast.Name(
                id="candidates", ctx=ast.Load()
            )

        def bitwise_union(tree):
            assignment = approved_assignment(tree)
            original = assignment.value
            assignment.value = ast.BinOp(
                left=original,
                op=ast.BitOr(),
                right=ast.Name(id="candidates", ctx=ast.Load()),
            )

        def method_union(tree):
            assignment = approved_assignment(tree)
            assignment.value = ast.Call(
                func=ast.Attribute(
                    value=assignment.value,
                    attr="union",
                    ctx=ast.Load(),
                ),
                args=[ast.Name(id="candidates", ctx=ast.Load())],
                keywords=[],
            )

        def update_union(tree):
            function = _definition_nodes(tree)["ViewerApprovedUIDs.from_projection"]
            assignment = approved_assignment(tree)
            position = function.body.index(assignment)
            function.body.insert(
                position + 1,
                ast.Expr(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="approved", ctx=ast.Load()),
                            attr="update",
                            ctx=ast.Load(),
                        ),
                        args=[ast.Name(id="candidates", ctx=ast.Load())],
                        keywords=[],
                    )
                ),
            )

        for label, mutate, expected in (
            (
                "post-filter-overwrite",
                overwrite_with_candidates,
                "approval:approved-not-filter-derived",
            ),
            ("bitwise-or", bitwise_union, "approval:union-bypass"),
            ("set-union", method_union, "approval:union-bypass"),
            ("set-update", update_union, "approval:union-bypass"),
        ):
            with self.subTest(mutation=label):
                tree = copy.deepcopy(baseline)
                mutate(tree)
                violations = _compose_seed_guard_violations(tree)
                self.assertIn(expected, violations)

        fx, records = self.substrate()
        source_projection = fx.projection()

        class TripwireProjection:
            index_as_of = self.as_of

            def __init__(inner_self):
                inner_self.filter_calls = 0

            def visible_segments(inner_self, viewer):
                return source_projection.visible_segments(viewer)

            def authority(inner_self, uid):
                return source_projection.authority(uid)

            def adjacency(inner_self, uid, viewer):
                return source_projection.adjacency(uid, viewer)

            def filter_visible_uids(inner_self, candidates, viewer):
                inner_self.filter_calls += 1
                values = tuple(candidates)
                caller = inspect.currentframe().f_back.f_code.co_name
                if caller == "draw_circle" and "hidden01" in values:
                    raise AssertionError("hidden seed reached post-approval index access")
                return source_projection.filter_visible_uids(values, viewer)

        circle_index = tc.InMemoryStructuralIndex(
            fx._structures, index_as_of=self.as_of
        )
        rank_index = fx.rank_index()
        rank_index.index_as_of = self.as_of

        def compose_with(projection):
            return di._compose_open_work(
                "argus",
                legacy.bob(),
                self.as_of,
                False,
                records,
                ROOT_UID,
                projection=projection,
                circle_index=circle_index,
                rank_index=rank_index,
            )

        approval_projection = TripwireProjection()
        approval = di.ViewerApprovedUIDs.from_projection(
            tuple(record["uid"] for record in records),
            legacy.bob(),
            self.as_of,
            projection=approval_projection,
        )
        self.assertTrue(approval.ok, msg=approval.error)
        self.assertEqual(approval.value.viewer, legacy.bob())
        self.assertEqual(approval.value.index_as_of, self.as_of)
        self.assertTrue(
            set(approval.value.uids).issubset(approval.value.candidate_uids)
        )
        self.assertNotIn("hidden01", approval.value.uids)
        query_seeds = approval.value.prevalidated_query_seeds()
        self.assertEqual(query_seeds.viewer, legacy.bob())
        self.assertEqual(query_seeds.index_as_of, self.as_of)
        self.assertEqual(query_seeds.uids, approval.value.uids)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            approval.value.uids = ("hidden01",)

        class ExpandingProjection(TripwireProjection):
            def filter_visible_uids(inner_self, candidates, viewer):
                return di.Result.success(tuple(candidates) + ("outside01",))

        expanded = di.ViewerApprovedUIDs.from_projection(
            ("visible01",),
            legacy.bob(),
            self.as_of,
            projection=ExpandingProjection(),
        )
        self.assertFalse(expanded.ok)
        self.assertEqual(
            expanded.error.code,
            di.BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
        )
        self.assertEqual(expanded.error.field, "projection.filter_visible_uids")

        honest_projection = TripwireProjection()
        honest = compose_with(honest_projection)
        self.assertTrue(honest.ok, msg=honest.error)
        self.assertNotIn("hidden01", honest.value.uids())

        def forged_factory(mode):
            def factory(
                cls,
                candidate_uids,
                viewer,
                index_as_of,
                *,
                projection,
            ):
                candidates = set(candidate_uids)
                if mode == "bypass":
                    approved = set(candidates)
                else:
                    filtered = projection.filter_visible_uids(
                        tuple(sorted(candidates)), viewer
                    )
                    self.assertTrue(filtered.ok, msg=filtered.error)
                    approved = set(filtered.value)
                    if mode == "overwrite":
                        approved = set(candidates)
                    elif mode == "bitwise-or":
                        approved = approved | candidates
                    elif mode == "union":
                        approved = approved.union(candidates)
                    elif mode == "update":
                        approved.update(candidates)
                return di.Result.success(
                    cls._from_validated(
                        viewer=viewer,
                        index_as_of=index_as_of,
                        candidate_uids=tuple(sorted(candidates)),
                        uids=tuple(sorted(approved)),
                    )
                )

            return factory

        for mode in ("overwrite", "bitwise-or", "union", "update", "bypass"):
            with self.subTest(runtime_mutation=mode), mock.patch.object(
                di.ViewerApprovedUIDs,
                "from_projection",
                new=classmethod(forged_factory(mode)),
            ):
                with self.assertRaisesRegex(
                    AssertionError, "hidden seed reached post-approval"
                ):
                    compose_with(TripwireProjection())


class AC9StampedServeTests(BootOrientCase):
    def test_viewer_and_as_of_are_stamped_and_mismatches_refuse(self):
        result, _index, _records = self.run_boot()
        self.assertTrue(result.ok, msg=result.error)
        orientation = result.value
        self.assertEqual(orientation.viewer, legacy.bob())
        self.assertEqual(orientation.as_of, self.as_of)
        self.assertRegex(
            orientation.source_snapshot,
            rf"^git:{self.as_of}:sha256:[0-9a-f]{{64}}$",
        )
        self.assertRegex(orientation.content_identity, r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(
            di.serve_boot_orientation(
                orientation,
                legacy.bob(),
                self.as_of,
                source_snapshot=orientation.source_snapshot,
                repo_root=self.git.root,
            ).ok
        )
        for viewer, as_of in (
            (legacy.alice(), self.as_of),
            (legacy.bob(), self.watermark),
        ):
            refused = di.serve_boot_orientation(orientation, viewer, as_of)
            self.assertFalse(refused.ok)
            self.assertEqual(
                refused.error.code,
                di.BootOrientationErrorCode.BINDING_MISMATCH,
            )
            self.assertEqual(
                refused.error.field,
                "viewer" if viewer != legacy.bob() else "as_of",
            )


class AdversarialReviewRegressionTests(BootOrientCase):
    def test_matching_content_does_not_require_mutable_as_of_labels(self):
        fx, records = self.substrate()
        projection = fx.projection()
        projection.index_as_of = "caller-self-certified-label"
        rank_index = fx.rank_index()
        rank_index.index_as_of = "another-mutable-label"
        result = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=self.as_of,
            projection=projection,
            circle_index=tc.InMemoryStructuralIndex(
                fx._structures, index_as_of="third-mutable-label"
            ),
            rank_index=rank_index,
            boot_index=di.InMemoryBootIndex({self.as_of: records}),
            repo_root=self.git.root,
        )
        self.assertTrue(result.ok, msg=result.error)

    def test_real_argus_identity_shape_resolves_party_root_and_memory(self):
        viewer = di.Viewer("cdf9b3ad", legacy.PRIV_BOB)
        result, _index, records = self.run_boot(
            viewer=viewer,
            primary_segment=legacy.PRIV_BOB,
            hidden_segment=legacy.PRIV_ALICE,
            party_uid="cdf9b3ad",
            identity_uid="76f0219f",
            root_uid="6dff0111",
        )
        self.assertTrue(result.ok, msg=result.error)
        identity = next(record for record in records if record["uid"] == "76f0219f")
        self.assertEqual(identity["party_uid"], "cdf9b3ad")
        self.assertEqual(identity["agent_root_uid"], "6dff0111")
        self.assertTrue(result.value.living_transfer)

    def test_ascii_and_unicode_newline_duplicate_identities_refuse_identically(self):
        duplicate_source = _agent_source(
            "argus",
            legacy.BOB,
            identity_uid="d00d0001",
            root_uid=ROOT_UID,
        )
        ascii_path = "vault/agents/duplicate.md"
        self.git.write(ascii_path, duplicate_source)
        ascii_result, _index, _records = self.run_boot()
        self.assertFalse(ascii_result.ok)

        (self.git.root / ascii_path).unlink()
        unicode_path = "vault/agents/düplicate-身份\ncontinued.md"
        self.git.write(unicode_path, duplicate_source)
        unicode_result, _index, _records = self.run_boot()
        self.assertFalse(unicode_result.ok)

        self.assertEqual(
            (
                ascii_result.error.code,
                ascii_result.error.field,
                ascii_result.error.message,
            ),
            (
                unicode_result.error.code,
                unicode_result.error.field,
                unicode_result.error.message,
            ),
        )
        self.assertEqual(
            ascii_result.error.code,
            di.BootOrientationErrorCode.TRANSFER_UNAVAILABLE,
        )
        self.assertEqual(ascii_result.error.field, "agent")
        topology = di.SubprocessGitDAG(self.git.root)
        with mock.patch.object(
            topology, "_run_bytes", wraps=topology._run_bytes
        ) as tree_reader:
            listed = topology.list_paths(
                self.git.run("rev-parse", "HEAD").stdout.strip(),
                "vault/agents",
            )
        self.assertIn(unicode_path, listed)
        args = tree_reader.call_args.args
        self.assertEqual(args[:2], ("-c", "core.quotepath=off"))
        self.assertIn("-z", args)

    def test_unrelated_viewer_cannot_trigger_private_memory_read(self):
        topology = di.SubprocessGitDAG(self.git.root)
        with mock.patch.object(
            topology, "read_bytes", wraps=topology.read_bytes
        ) as memory_read:
            result, _index, _records = self.run_boot(
                viewer=legacy.alice(),
                primary_segment=legacy.TEAM,
                party_uid=legacy.BOB,
                git_dag=topology,
            )
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error.code,
            di.BootOrientationErrorCode.TRANSFER_FORBIDDEN,
        )
        self.assertNotIn(
            "agents/argus/.tropo-capsule/memory/agent-memory.md",
            tuple(call.args[1] for call in memory_read.call_args_list),
        )

    def test_identity_cannot_redirect_memory_reader_to_arbitrary_repo_file(self):
        topology = di.SubprocessGitDAG(self.git.root)
        with mock.patch.object(
            topology, "read_bytes", wraps=topology.read_bytes
        ) as memory_read:
            result, _index, _records = self.run_boot(
                memory_path="STUDIO.md",
                git_dag=topology,
            )
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error.code,
            di.BootOrientationErrorCode.TRANSFER_FORBIDDEN,
        )
        read_paths = tuple(call.args[1] for call in memory_read.call_args_list)
        self.assertNotIn(
            "agents/argus/.tropo-capsule/memory/agent-memory.md", read_paths
        )
        self.assertNotIn("STUDIO.md", read_paths)

    def test_memory_frontmatter_cannot_self_assert_another_agent(self):
        result, _index, _records = self.run_boot(
            memory=_memory_surface(self.watermark).replace(
                "agent: argus", "agent: vela"
            )
        )
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error.code,
            di.BootOrientationErrorCode.TRANSFER_FORBIDDEN,
        )

    def test_legacy_memory_loader_api_is_retained_but_cannot_bypass_git(self):
        called = []
        fx, records = self.substrate()
        projection = fx.projection()
        projection.index_as_of = self.as_of
        rank_index = fx.rank_index()
        rank_index.index_as_of = self.as_of
        result = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=self.as_of,
            projection=projection,
            circle_index=tc.InMemoryStructuralIndex(
                fx._structures, index_as_of=self.as_of
            ),
            rank_index=rank_index,
            boot_index=di.InMemoryBootIndex(records),
            repo_root=self.git.root,
            memory_loader=lambda _path: called.append("called"),
        )
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error.code,
            di.BootOrientationErrorCode.TRANSFER_FORBIDDEN,
        )
        self.assertEqual(called, [])

    def test_circle_rank_and_projection_execute_only_against_frozen_bytes(self):
        fx, records = self.substrate()
        projection_source = fx.projection()
        circle_source = tc.InMemoryStructuralIndex(
            fx._structures, index_as_of=self.as_of
        )
        rank_source = fx.rank_index()

        class OneReadProjection:
            index_as_of = self.as_of

            def __init__(inner_self):
                inner_self.calls = {}

            def once(inner_self, operation, uid, call):
                key = (operation, uid)
                inner_self.calls[key] = inner_self.calls.get(key, 0) + 1
                if inner_self.calls[key] > 1:
                    raise AssertionError(f"mutable projection reused: {key}")
                return call()

            def visible_segments(inner_self, viewer):
                return inner_self.once(
                    "visible_segments",
                    viewer.principal_uid,
                    lambda: projection_source.visible_segments(viewer),
                )

            def filter_visible_uids(inner_self, candidates, viewer):
                values = tuple(candidates)
                return inner_self.once(
                    "filter_visible_uids",
                    values,
                    lambda: projection_source.filter_visible_uids(values, viewer),
                )

            def adjacency(inner_self, uid, viewer):
                return inner_self.once(
                    "adjacency",
                    uid,
                    lambda: projection_source.adjacency(uid, viewer),
                )

            def authority(inner_self, uid):
                return inner_self.once(
                    "authority",
                    uid,
                    lambda: projection_source.authority(uid),
                )

        class OneReadCircle:
            index_as_of = self.as_of

            def __init__(inner_self):
                inner_self.calls = {}

            def once(inner_self, operation, uid, call):
                key = (operation, uid)
                inner_self.calls[key] = inner_self.calls.get(key, 0) + 1
                if inner_self.calls[key] > 1:
                    raise AssertionError(f"mutable circle index reused: {key}")
                return call()

            def structure(inner_self, uid):
                return inner_self.once(
                    "structure", uid, lambda: circle_source.structure(uid)
                )

            def children_of(inner_self, uid):
                return inner_self.once(
                    "children_of", uid, lambda: circle_source.children_of(uid)
                )

        class OneReadRank:
            index_as_of = self.as_of

            def __init__(inner_self):
                inner_self.calls = {}

            def record(inner_self, uid):
                inner_self.calls[uid] = inner_self.calls.get(uid, 0) + 1
                if inner_self.calls[uid] > 1:
                    raise AssertionError(f"mutable rank index reused: {uid}")
                return rank_source.record(uid)

        projection = OneReadProjection()
        circle_index = OneReadCircle()
        rank_index = OneReadRank()
        result = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=self.as_of,
            projection=projection,
            circle_index=circle_index,
            rank_index=rank_index,
            boot_index=di.InMemoryBootIndex({self.as_of: records}),
            repo_root=self.git.root,
        )
        self.assertTrue(result.ok, msg=result.error)
        legal_uids = {
            record["uid"]
            for record in records
            if record["segment"] in {legacy.OS, legacy.TEAM, legacy.PRIV_BOB}
        }
        self.assertEqual(set(rank_index.calls), legal_uids)
        self.assertTrue(all(count == 1 for count in rank_index.calls.values()))
        self.assertTrue(all(count == 1 for count in circle_index.calls.values()))
        self.assertTrue(all(count == 1 for count in projection.calls.values()))

    def test_binding_sibling_guards_report_distinct_fields(self):
        def invoke(fx, records):
            return di.orient_boot(
                "argus",
                legacy.bob(),
                as_of=self.as_of,
                projection=fx.projection(),
                circle_index=tc.InMemoryStructuralIndex(fx._structures),
                rank_index=fx.rank_index(),
                boot_index=di.InMemoryBootIndex({self.as_of: records}),
                repo_root=self.git.root,
            )

        cases = []
        fx, records = self.substrate()
        records[0]["unexpected"] = "caller-only"
        cases.append(("boot-index", fx, records, "boot_index.content"))

        fx, records = self.substrate()
        fx.neighbor("work0000", "other001")
        cases.append(("projection", fx, records, "projection.content"))

        fx, records = self.substrate()
        fx._structures["work0000"]["refs"].append("other001")
        cases.append(("circle", fx, records, "circle_index.content"))

        fx, records = self.substrate()
        fx._rankrecs["work0000"]["decay"] = {"stale": True}
        cases.append(("rank", fx, records, "rank_index.content"))

        for label, fx, records, expected_field in cases:
            with self.subTest(guard=label):
                result = invoke(fx, records)
                self.assertFalse(result.ok)
                self.assertEqual(
                    result.error.code,
                    di.BootOrientationErrorCode.BINDING_MISMATCH,
                )
                self.assertEqual(result.error.field, expected_field)

    def test_as_of_selects_source_snapshot_and_later_entry_cannot_be_re_served(self):
        old_as_of = self.as_of
        self.git.write(
            "vault/files/late0001.md",
            _entry_source(
                "late0001",
                type_="task",
                segment=legacy.TEAM,
                assigned_to="argus",
                member_of=[ROOT_UID],
            ),
        )
        later = self.git.commit("post-as-of entry")
        committed_fx, old_records = self.substrate()
        committed_projection = committed_fx.projection()
        committed_rank = committed_fx.rank_index()
        result = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=old_as_of,
            projection=committed_projection,
            circle_index=tc.InMemoryStructuralIndex(committed_fx._structures),
            rank_index=committed_rank,
            boot_index=di.InMemoryBootIndex({old_as_of: old_records}),
            repo_root=self.git.root,
        )
        self.assertTrue(result.ok, msg=result.error)
        self.assertNotIn("late0001", result.value.ranked_open_work.uids())
        self.assertNotIn("late0001", result.value.canonical())

        mutable_fx, _ = self.substrate()
        mutable_fx.node("late0001", legacy.TEAM, type_="task", status="active")
        mutable_fx.rel("late0001", ROOT_UID, "member_of")
        late_record = {
            "uid": "late0001",
            "type": "task",
            "assigned_to": "argus",
            "member_of": ["root0001"],
            "path": "vault/files/late0001.md",
            "segment": legacy.TEAM,
            "status": "active",
            "modified": "2026-07-26",
        }
        mutable_projection = mutable_fx.projection()
        mutable_projection.index_as_of = old_as_of
        mutable_rank = mutable_fx.rank_index()
        mutable_rank.index_as_of = old_as_of
        refused_mutable = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=old_as_of,
            projection=mutable_projection,
            circle_index=tc.InMemoryStructuralIndex(
                mutable_fx._structures, index_as_of=old_as_of
            ),
            rank_index=mutable_rank,
            boot_index=di.InMemoryBootIndex(
                {
                    old_as_of: old_records,
                    later: [*old_records, late_record],
                }
            ),
            repo_root=self.git.root,
        )
        self.assertFalse(refused_mutable.ok)
        self.assertEqual(
            refused_mutable.error.code,
            di.BootOrientationErrorCode.BINDING_MISMATCH,
        )
        self.assertEqual(refused_mutable.error.field, "projection.content")
        refused = di.serve_boot_orientation(
            result.value,
            legacy.bob(),
            later,
        )
        self.assertFalse(refused.ok)
        self.assertEqual(
            refused.error.code,
            di.BootOrientationErrorCode.BINDING_MISMATCH,
        )
        self.assertEqual(refused.error.field, "as_of")

    def test_mislabeled_index_with_post_as_of_record_fails_content_binding(self):
        old_as_of = self.as_of
        self.git.write("vault/files/late0001.md", "created after as_of\n")
        self.git.commit("post-as-of source")
        fx, records = self.substrate()
        fx.node("late0001", legacy.TEAM, type_="task", status="active")
        fx.rel("late0001", ROOT_UID, "member_of")
        records.append(
            {
                "uid": "late0001",
                "type": "task",
                "assigned_to": "argus",
                "member_of": [ROOT_UID],
                "path": "vault/files/late0001.md",
                "segment": legacy.TEAM,
                "status": "active",
            }
        )
        projection = fx.projection()
        projection.index_as_of = old_as_of
        rank_index = fx.rank_index()
        rank_index.index_as_of = old_as_of
        result = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=old_as_of,
            projection=projection,
            circle_index=tc.InMemoryStructuralIndex(
                fx._structures, index_as_of=old_as_of
            ),
            rank_index=rank_index,
            boot_index=di.InMemoryBootIndex({old_as_of: records}),
            repo_root=self.git.root,
        )
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error.code,
            di.BootOrientationErrorCode.BINDING_MISMATCH,
        )
        self.assertEqual(result.error.field, "boot_index.content")

    def test_mutable_rank_label_cannot_masquerade_as_as_of_content(self):
        first, _index, records = self.run_boot()
        self.assertTrue(first.ok, msg=first.error)

        fx, _ = self.substrate()
        fx._rankrecs["work0000"]["decay"] = {
            "stale": True,
            "confidence": 1.0,
        }
        projection = fx.projection()
        projection.index_as_of = self.as_of
        rank_index = fx.rank_index()
        rank_index.index_as_of = self.as_of
        second = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=self.as_of,
            projection=projection,
            circle_index=tc.InMemoryStructuralIndex(
                fx._structures, index_as_of=self.as_of
            ),
            rank_index=rank_index,
            boot_index=di.InMemoryBootIndex({self.as_of: records}),
            repo_root=self.git.root,
        )
        self.assertFalse(second.ok)
        self.assertEqual(
            second.error.code,
            di.BootOrientationErrorCode.BINDING_MISMATCH,
        )
        self.assertEqual(second.error.field, "rank_index.content")
        refused = di.serve_boot_orientation(
            first.value,
            legacy.bob(),
            self.as_of,
            source_snapshot=f"git:{self.as_of}:sha256:" + ("0" * 64),
        )
        self.assertFalse(refused.ok)
        self.assertEqual(
            refused.error.code,
            di.BootOrientationErrorCode.BINDING_MISMATCH,
        )
        self.assertEqual(refused.error.field, "source_snapshot.consumer")

    def test_two_mutable_projections_with_same_label_cannot_masquerade(self):
        fx, records = self.substrate()
        honest = fx.projection()
        honest.index_as_of = self.as_of
        honest_rank = fx.rank_index()
        honest_rank.index_as_of = self.as_of
        first = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=self.as_of,
            projection=honest,
            circle_index=tc.InMemoryStructuralIndex(
                fx._structures, index_as_of=self.as_of
            ),
            rank_index=honest_rank,
            boot_index=di.InMemoryBootIndex({self.as_of: records}),
            repo_root=self.git.root,
        )
        self.assertTrue(first.ok, msg=first.error)

        fx.neighbor("work0000", "other001")
        changed = fx.projection()
        changed.index_as_of = self.as_of
        changed_rank = fx.rank_index()
        changed_rank.index_as_of = self.as_of
        second = di.orient_boot(
            "argus",
            legacy.bob(),
            as_of=self.as_of,
            projection=changed,
            circle_index=tc.InMemoryStructuralIndex(
                fx._structures, index_as_of=self.as_of
            ),
            rank_index=changed_rank,
            boot_index=di.InMemoryBootIndex({self.as_of: records}),
            repo_root=self.git.root,
        )
        self.assertFalse(second.ok)
        self.assertEqual(
            second.error.code,
            di.BootOrientationErrorCode.BINDING_MISMATCH,
        )
        self.assertEqual(second.error.field, "projection.content")

    def test_re_serve_rereads_git_provenance_and_refuses_a_resealed_forgery(self):
        first, _index, _records = self.run_boot()
        self.assertTrue(first.ok, msg=first.error)
        topology = di.SubprocessGitDAG(self.git.root)
        with mock.patch.object(
            topology, "read_bytes", wraps=topology.read_bytes
        ) as source_reads:
            served = di.serve_boot_orientation(
                first.value,
                legacy.bob(),
                self.as_of,
                repo_root=self.git.root,
                git_dag=topology,
            )
        self.assertTrue(served.ok, msg=served.error)
        self.assertEqual(
            {call.args[1] for call in source_reads.call_args_list},
            {
                "vault/boot-orientation-snapshot.json",
                "agents/argus/.tropo-capsule/memory/agent-memory.md",
            },
        )

        unsigned_forgery = di.replace(
            first.value,
            source_snapshot=f"git:{self.as_of}:sha256:" + ("0" * 64),
            content_identity="",
        )
        resealed_forgery = di.replace(
            unsigned_forgery,
            content_identity=di._orientation_content_identity(unsigned_forgery),
        )
        refused = di.serve_boot_orientation(
            resealed_forgery,
            legacy.bob(),
            self.as_of,
            repo_root=self.git.root,
        )
        self.assertFalse(refused.ok)
        self.assertEqual(
            refused.error.code,
            di.BootOrientationErrorCode.BINDING_MISMATCH,
        )
        self.assertEqual(refused.error.field, "source_snapshot.bytes")

        tampered = di.replace(
            first.value,
            living_transfer=first.value.living_transfer + "tampered\n",
        )
        refused = di.serve_boot_orientation(
            tampered, legacy.bob(), self.as_of
        )
        self.assertFalse(refused.ok)
        self.assertEqual(
            refused.error.code,
            di.BootOrientationErrorCode.BINDING_MISMATCH,
        )
        self.assertEqual(refused.error.field, "content_identity.digest")

    def test_sqlite_boot_index_loads_committed_blob_not_working_tree(self):
        import sqlite3

        database = self.git.root / "boot-index.sqlite"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE entries (uid TEXT, fm_json TEXT)")
        connection.execute(
            "INSERT INTO entries VALUES (?, ?)",
            (
                "old00001",
                json.dumps({"uid": "old00001", "segment": legacy.TEAM}),
            ),
        )
        connection.commit()
        connection.close()
        old_snapshot = self.git.commit("old index snapshot")

        connection = sqlite3.connect(database)
        connection.execute(
            "INSERT INTO entries VALUES (?, ?)",
            (
                "late0001",
                json.dumps({"uid": "late0001", "segment": legacy.TEAM}),
            ),
        )
        connection.commit()
        connection.close()
        self.git.commit("later index snapshot")

        rows = di.SqliteBootIndex("boot-index.sqlite").visible_records(
            {legacy.TEAM},
            as_of=old_snapshot,
            git_dag=di.SubprocessGitDAG(self.git.root),
        )
        self.assertEqual(tuple(row["uid"] for row in rows), ("old00001",))

    def test_sqlite_fallback_reads_exact_worktree_and_commit_bytes_mode_0600(self):
        import sqlite3
        import stat

        database = self.git.root / "fallback-index.sqlite"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE entries (uid TEXT, fm_json TEXT)")
        connection.execute(
            "INSERT INTO entries VALUES (?, ?)",
            (
                "old00001",
                json.dumps({"uid": "old00001", "segment": legacy.TEAM}),
            ),
        )
        connection.commit()
        connection.close()
        old_snapshot = self.git.commit("fallback old index snapshot")

        connection = sqlite3.connect(database)
        connection.execute(
            "INSERT INTO entries VALUES (?, ?)",
            (
                "late0001",
                json.dumps({"uid": "late0001", "segment": legacy.TEAM}),
            ),
        )
        connection.commit()
        connection.close()
        self.git.commit("fallback later index snapshot")

        topology = di.SubprocessGitDAG(self.git.root)
        expected_snapshots = [
            database.read_bytes(),
            topology.read_bytes(old_snapshot, "fallback-index.sqlite"),
        ]
        temporary_paths = []
        real_connect = sqlite3.connect
        real_mkstemp = di.tempfile.mkstemp

        class NoDeserializeConnection:
            def __init__(inner_self):
                inner_self._connection = real_connect(":memory:")

            def close(inner_self):
                inner_self._connection.close()

        def tracked_mkstemp(*args, **kwargs):
            descriptor, path = real_mkstemp(*args, **kwargs)
            temporary_paths.append(Path(path))
            return descriptor, path

        def fallback_connect(database_name, *args, **kwargs):
            if database_name == ":memory:":
                return NoDeserializeConnection()
            temporary_path = temporary_paths[-1]
            self.assertTrue(kwargs.get("uri"))
            self.assertEqual(
                database_name,
                temporary_path.resolve().as_uri() + "?mode=ro&immutable=1",
            )
            self.assertEqual(
                stat.S_IMODE(temporary_path.stat().st_mode),
                0o600,
            )
            self.assertEqual(
                temporary_path.read_bytes(),
                expected_snapshots.pop(0),
            )
            return real_connect(database_name, *args, **kwargs)

        with mock.patch.object(
            di.tempfile, "mkstemp", side_effect=tracked_mkstemp
        ), mock.patch.object(sqlite3, "connect", side_effect=fallback_connect):
            working_rows = di.SqliteBootIndex(database).visible_records(
                {legacy.TEAM}
            )
            self.assertFalse(temporary_paths[-1].exists())
            commit_rows = di.SqliteBootIndex(
                "fallback-index.sqlite"
            ).visible_records(
                {legacy.TEAM},
                as_of=old_snapshot,
                git_dag=topology,
            )
            self.assertFalse(temporary_paths[-1].exists())

        self.assertEqual(
            tuple(row["uid"] for row in working_rows),
            ("late0001", "old00001"),
        )
        self.assertEqual(
            tuple(row["uid"] for row in commit_rows),
            ("old00001",),
        )
        self.assertEqual(expected_snapshots, [])
        self.assertEqual(len(temporary_paths), 2)
        self.assertTrue(all(not path.exists() for path in temporary_paths))

    def test_sqlite_fallback_unlinks_private_file_when_query_fails(self):
        import sqlite3
        import stat

        malformed = self.git.root / "malformed-index.sqlite"
        malformed.write_bytes(b"not-a-sqlite-snapshot")
        temporary_paths = []
        real_connect = sqlite3.connect
        real_mkstemp = di.tempfile.mkstemp

        class NoDeserializeConnection:
            def __init__(inner_self):
                inner_self._connection = real_connect(":memory:")

            def close(inner_self):
                inner_self._connection.close()

        def tracked_mkstemp(*args, **kwargs):
            descriptor, path = real_mkstemp(*args, **kwargs)
            temporary_paths.append(Path(path))
            return descriptor, path

        def fallback_connect(database_name, *args, **kwargs):
            if database_name == ":memory:":
                return NoDeserializeConnection()
            temporary_path = temporary_paths[-1]
            self.assertEqual(
                stat.S_IMODE(temporary_path.stat().st_mode),
                0o600,
            )
            self.assertEqual(
                temporary_path.read_bytes(),
                b"not-a-sqlite-snapshot",
            )
            return real_connect(database_name, *args, **kwargs)

        with mock.patch.object(
            di.tempfile, "mkstemp", side_effect=tracked_mkstemp
        ), mock.patch.object(sqlite3, "connect", side_effect=fallback_connect):
            with self.assertRaises(di.BootOrientationError) as raised:
                di.SqliteBootIndex(malformed).visible_records({legacy.TEAM})

        self.assertEqual(
            raised.exception.code,
            di.BootOrientationErrorCode.SUBSTRATE_UNAVAILABLE,
        )
        self.assertEqual(len(temporary_paths), 1)
        self.assertFalse(temporary_paths[0].exists())

    def test_git_changed_paths_preserves_unicode_and_embedded_newline(self):
        relative = "vault/files/résumé-路径\ncontinued.md"
        self.git.write(relative, "unicode path fixture\n")
        commit = self.git.commit("unicode changed path")
        topology = di.SubprocessGitDAG(self.git.root)

        with mock.patch.object(
            topology, "_run_bytes", wraps=topology._run_bytes
        ) as byte_reader:
            changed = topology.changed_paths((commit,))

        self.assertEqual(changed, {relative: (commit,)})
        args = byte_reader.call_args.args
        self.assertEqual(args[:2], ("-c", "core.quotepath=off"))
        self.assertIn("-z", args)

    def test_unbound_current_source_refuses_old_as_of_before_memory_read(self):
        later = self.git.run("rev-parse", "HEAD").stdout.strip()
        topology = di.SubprocessGitDAG(self.git.root)
        fx, records = self.substrate()
        projection = fx.projection()
        projection.index_as_of = later
        rank_index = fx.rank_index()
        rank_index.index_as_of = later
        with mock.patch.object(
            topology, "read_bytes", wraps=topology.read_bytes
        ) as memory_read:
            result = di.orient_boot(
                "argus",
                legacy.bob(),
                as_of=self.watermark,
                projection=projection,
                circle_index=tc.InMemoryStructuralIndex(
                    fx._structures, index_as_of=later
                ),
                rank_index=rank_index,
                boot_index=di.InMemoryBootIndex({later: records}),
                repo_root=self.git.root,
                git_dag=topology,
            )
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error.code,
            di.BootOrientationErrorCode.BINDING_MISMATCH,
        )
        self.assertEqual(result.error.field, "boot_snapshot.bytes")
        self.assertNotIn(
            "agents/argus/.tropo-capsule/memory/agent-memory.md",
            tuple(call.args[1] for call in memory_read.call_args_list),
        )


class BindingGuardCoverageTests(BootOrientCase):
    def test_all_38_binding_sites_are_mapped_and_per_guard_deletion_is_killed(self):
        import copy

        tree = ast.parse(Path(di.__file__).read_text(encoding="utf-8"))
        expected = tuple(_BINDING_RAISE_COVERAGE)
        self.assertEqual(_binding_error_sites(tree), expected)
        self.assertEqual(len(expected), 38)
        self.assertTrue(
            all(
                hasattr(self, test_name)
                for test_name in set(_BINDING_RAISE_COVERAGE.values())
            )
        )

        def binding_error_nodes(source_tree):
            nodes = []
            for node in ast.walk(source_tree):
                if not isinstance(node, ast.Call):
                    continue
                error = node
                if (
                    isinstance(error.func, ast.Name)
                    and error.func.id == "BootOrientationError"
                    and error.args
                    and ast.unparse(error.args[0])
                    == "BootOrientationErrorCode.BINDING_MISMATCH"
                ):
                    nodes.append(node)
            return sorted(nodes, key=lambda node: node.lineno)

        for index, site in enumerate(expected):
            with self.subTest(deleted_guard=site):
                mutated = copy.deepcopy(tree)
                target = binding_error_nodes(mutated)[index]
                parents = {
                    child: parent
                    for parent in ast.walk(mutated)
                    for child in ast.iter_child_nodes(parent)
                }
                statement = target
                while not isinstance(statement, ast.stmt):
                    statement = parents[statement]
                parent = parents[statement]
                replacement = ast.copy_location(ast.Pass(), statement)
                replaced = False
                for field, value in ast.iter_fields(parent):
                    if isinstance(value, list):
                        for position, child in enumerate(value):
                            if child is statement:
                                value[position] = replacement
                                replaced = True
                                break
                    elif value is statement:
                        setattr(parent, field, replacement)
                        replaced = True
                    if replaced:
                        break
                self.assertTrue(replaced)
                self.assertEqual(len(_binding_error_sites(mutated)), len(expected) - 1)
                self.assertNotIn(site, _binding_error_sites(mutated))

    def test_binding_source_and_authority_guards_report_exact_fields(self):
        class TextGit:
            def __init__(inner_self, text):
                inner_self.text = text

            def read_text(inner_self, _commit, _path):
                return inner_self.text

            def list_paths(inner_self, _commit, _prefix):
                return ("vault/agents/not-the-uid.md",)

        valid_source = "---\nuid: work0000\ntype: task\nstatus: active\n---\n"
        mismatch_identity = _agent_source(
            "argus", legacy.BOB, identity_uid=AGENT_UID, root_uid=ROOT_UID
        )
        cases = (
            (
                "in-memory-snapshot",
                "boot_index.snapshot",
                lambda: di.InMemoryBootIndex({"a" * 40: ()}).visible_records(
                    {legacy.TEAM}, as_of="b" * 40
                ),
            ),
            (
                "sqlite-path",
                "index_path",
                lambda: di.SqliteBootIndex("/absolute.sqlite").visible_records(
                    {legacy.TEAM}, as_of="a" * 40, git_dag=TextGit("")
                ),
            ),
            (
                "frontmatter-start",
                "vault/files/work0000.md.frontmatter.start",
                lambda: di._frontmatter_at(
                    TextGit("uid: work0000\n"), "a" * 40, "vault/files/work0000.md"
                ),
            ),
            (
                "frontmatter-end",
                "vault/files/work0000.md.frontmatter.end",
                lambda: di._frontmatter_at(
                    TextGit("---\nuid: work0000\n"),
                    "a" * 40,
                    "vault/files/work0000.md",
                ),
            ),
            (
                "frontmatter-yaml",
                "vault/files/work0000.md.frontmatter.yaml",
                lambda: di._frontmatter_at(
                    TextGit("---\n[broken\n---\n"),
                    "a" * 40,
                    "vault/files/work0000.md",
                ),
            ),
            (
                "frontmatter-type",
                "vault/files/work0000.md.frontmatter.type",
                lambda: di._frontmatter_at(
                    TextGit("---\n- list\n---\n"),
                    "a" * 40,
                    "vault/files/work0000.md",
                ),
            ),
            (
                "record-path",
                "boot_index.path",
                lambda: di._bind_records_to_git(
                    ({"uid": "work0000"},),
                    as_of="a" * 40,
                    git_dag=TextGit(valid_source),
                ),
            ),
            (
                "record-source",
                "boot_index.source",
                lambda: di._bind_records_to_git(
                    ({"uid": "work0000", "path": "vault/files/work0000.md"},),
                    as_of="a" * 40,
                    git_dag=TextGit("not frontmatter\n"),
                ),
            ),
            (
                "record-uid",
                "boot_index.uid",
                lambda: di._bind_records_to_git(
                    ({"uid": "other000", "path": "vault/files/work0000.md"},),
                    as_of="a" * 40,
                    git_dag=TextGit(valid_source),
                ),
            ),
            (
                "record-field",
                "boot_index.status",
                lambda: di._bind_records_to_git(
                    (
                        {
                            "uid": "work0000",
                            "path": "vault/files/work0000.md",
                            "status": "archived",
                        },
                    ),
                    as_of="a" * 40,
                    git_dag=TextGit(valid_source),
                ),
            ),
            (
                "authority-field",
                "authority_index.uid",
                lambda: di._require_record_matches_source(
                    {"uid": "other000"},
                    {"uid": "work0000"},
                    ("uid",),
                    "vault/agents/a9e00001.md",
                ),
            ),
            (
                "identity-path",
                "identity.path",
                lambda: di._resolve_agent_authority(
                    (),
                    "argus",
                    legacy.bob(),
                    as_of="a" * 40,
                    git_dag=TextGit(mismatch_identity),
                ),
            ),
        )
        for label, expected_field, operation in cases:
            with self.subTest(guard=label), self.assertRaises(
                di.BootOrientationError
            ) as raised:
                operation()
            self.assertEqual(
                raised.exception.code,
                di.BootOrientationErrorCode.BINDING_MISMATCH,
            )
            self.assertEqual(raised.exception.field, expected_field)

    def test_binding_snapshot_guards_report_exact_fields(self):
        topology = di.SubprocessGitDAG(self.git.root)
        valid_bytes = topology.read_bytes(
            self.as_of, "vault/boot-orientation-snapshot.json"
        )
        valid = json.loads(valid_bytes.decode("utf-8"))

        class SnapshotGit:
            def __init__(inner_self, payload):
                inner_self.payload = payload

            def read_bytes(inner_self, _commit, _path):
                return inner_self.payload

        def encoded(mutate):
            document = json.loads(json.dumps(valid))
            mutate(document)
            return json.dumps(document).encode("utf-8")

        def set_schema(document):
            document["schema"] = 2

        def set_viewer(document):
            document["viewer"] = {"principal_uid": "wrong"}

        def duplicate_segments(document):
            document["visible_segments"].append(document["visible_segments"][0])

        def records_shape(document):
            document["records"] = "not-a-list"

        def duplicate_record_uid(document):
            document["records"].append(dict(document["records"][0]))

        def hidden_record(document):
            document["records"][0]["segment"] = "not-visible"

        def rank_membership(document):
            document["rank_index"].pop()

        def bad_adjacency(document):
            document["projection"][0]["adjacency"] = ["not-a-record"]

        def bad_children(document):
            document["circle_index"][0]["children"] = ["not-a-record"]

        cases = (
            ("bytes", "boot_snapshot.bytes", b"{"),
            ("schema", "boot_snapshot.schema", encoded(set_schema)),
            ("viewer", "boot_snapshot.viewer", encoded(set_viewer)),
            (
                "visible-segments",
                "boot_snapshot.visible_segments",
                encoded(duplicate_segments),
            ),
            ("records-shape", "boot_snapshot.records.shape", encoded(records_shape)),
            (
                "record-uids",
                "boot_snapshot.records.uids",
                encoded(duplicate_record_uid),
            ),
            (
                "record-segment",
                "boot_snapshot.records.segment",
                encoded(hidden_record),
            ),
            (
                "rank-membership",
                "boot_snapshot.rank_index.membership",
                encoded(rank_membership),
            ),
            (
                "projection-adjacency",
                "boot_snapshot.projection.adjacency",
                encoded(bad_adjacency),
            ),
            (
                "circle-children",
                "boot_snapshot.circle_index.children",
                encoded(bad_children),
            ),
        )
        for label, expected_field, payload in cases:
            with self.subTest(guard=label), self.assertRaises(
                di.BootOrientationError
            ) as raised:
                di._load_committed_boot_sources(
                    as_of=self.as_of,
                    viewer=legacy.bob(),
                    git_dag=SnapshotGit(payload),
                )
            self.assertEqual(
                raised.exception.code,
                di.BootOrientationErrorCode.BINDING_MISMATCH,
            )
            self.assertEqual(raised.exception.field, expected_field)

    def test_binding_injected_source_guards_report_exact_fields(self):
        topology = di.SubprocessGitDAG(self.git.root)
        (
            _snapshot_bytes,
            visible_segments,
            committed_records,
            _frozen_projection,
            _frozen_circle,
            _frozen_rank,
            expected,
        ) = di._load_committed_boot_sources(
            as_of=self.as_of,
            viewer=legacy.bob(),
            git_dag=topology,
        )

        class ProjectionProxy:
            def __init__(inner_self, delegate, mode):
                inner_self.delegate = delegate
                inner_self.mode = mode

            def visible_segments(inner_self, viewer):
                if inner_self.mode == "visibility":
                    return di.Result.success(frozenset())
                return inner_self.delegate.visible_segments(viewer)

            def filter_visible_uids(inner_self, candidates, viewer):
                if inner_self.mode == "filter":
                    return di.Result.success(())
                return inner_self.delegate.filter_visible_uids(candidates, viewer)

            def adjacency(inner_self, uid, viewer):
                return inner_self.delegate.adjacency(uid, viewer)

            def authority(inner_self, uid):
                return inner_self.delegate.authority(uid)

        def invoke(mode):
            fx, records = self.substrate()
            projection = fx.projection()
            circle_index = tc.InMemoryStructuralIndex(fx._structures)
            rank_index = fx.rank_index()
            boot_records = records
            if mode == "boot-index":
                boot_records = [dict(record) for record in records]
                boot_records[0]["unexpected"] = True
            elif mode == "projection":
                fx.neighbor("work0000", "other001")
                projection = fx.projection()
            elif mode == "circle":
                fx._structures["work0000"]["refs"].append("other001")
                circle_index = tc.InMemoryStructuralIndex(fx._structures)
            elif mode == "rank":
                fx._rankrecs["work0000"]["decay"] = {"stale": True}
                rank_index = fx.rank_index()
            if mode in {"visibility", "filter"}:
                projection = ProjectionProxy(projection, mode)
            return di._verify_injected_boot_sources(
                as_of=self.as_of,
                viewer=legacy.bob(),
                visible_segments=visible_segments,
                committed_records=committed_records,
                expected=expected,
                projection=projection,
                circle_index=circle_index,
                rank_index=rank_index,
                boot_index=di.InMemoryBootIndex({self.as_of: boot_records}),
                git_dag=topology,
            )

        cases = (
            ("visibility", "projection.visible_segments"),
            ("boot-index", "boot_index.content"),
            ("filter", "projection.filter_visible_uids"),
            ("projection", "projection.content"),
            ("circle", "circle_index.content"),
            ("rank", "rank_index.content"),
        )
        for mode, expected_field in cases:
            with self.subTest(guard=mode), self.assertRaises(
                di.BootOrientationError
            ) as raised:
                invoke(mode)
            self.assertEqual(
                raised.exception.code,
                di.BootOrientationErrorCode.BINDING_MISMATCH,
            )
            self.assertEqual(raised.exception.field, expected_field)

    def test_binding_frozen_and_serve_guards_report_exact_fields(self):
        frozen = di._FrozenBootProjection(
            viewer=legacy.bob(),
            as_of=self.as_of,
            visible_segments={legacy.TEAM},
            legal_uids={"work0000"},
            adjacency={"work0000": ()},
            authority={"work0000": 0},
        )
        frozen_cases = (
            (
                "frozen-viewer",
                frozen.visible_segments(legacy.alice()),
                "frozen_projection.viewer",
            ),
            (
                "frozen-adjacency",
                frozen.adjacency("missing00", legacy.bob()),
                "frozen_projection.adjacency",
            ),
            (
                "frozen-authority",
                frozen.authority("missing00"),
                "frozen_projection.authority",
            ),
        )
        for label, result, expected_field in frozen_cases:
            with self.subTest(guard=label):
                self.assertFalse(result.ok)
                self.assertEqual(
                    result.error.code,
                    di.BootOrientationErrorCode.BINDING_MISMATCH,
                )
                self.assertEqual(result.error.field, expected_field)

        boot, _index, _records = self.run_boot()
        self.assertTrue(boot.ok, msg=boot.error)
        orientation = boot.value

        class ProvenanceFailure:
            def normalize_commit(inner_self, _revision, *, field):
                raise di.BootOrientationError(
                    di.BootOrientationErrorCode.GIT_UNAVAILABLE,
                    "planted provenance failure",
                    field=field,
                )

        class DifferentBytes:
            def normalize_commit(inner_self, revision, *, field):
                self.assertEqual(field, "as_of")
                return revision

            def read_bytes(inner_self, _commit, path):
                return f"different:{path}".encode("utf-8")

        serve_cases = (
            (
                "content-shape",
                lambda: di.serve_boot_orientation(
                    di.replace(orientation, ranked_open_work=None),
                    legacy.bob(),
                    self.as_of,
                ),
                "content_identity.shape",
            ),
            (
                "content-digest",
                lambda: di.serve_boot_orientation(
                    di.replace(orientation, content_identity="sha256:" + "0" * 64),
                    legacy.bob(),
                    self.as_of,
                ),
                "content_identity.digest",
            ),
            (
                "viewer",
                lambda: di.serve_boot_orientation(
                    orientation, legacy.alice(), self.as_of
                ),
                "viewer",
            ),
            (
                "as-of",
                lambda: di.serve_boot_orientation(
                    orientation, legacy.bob(), self.watermark
                ),
                "as_of",
            ),
            (
                "source-consumer",
                lambda: di.serve_boot_orientation(
                    orientation,
                    legacy.bob(),
                    self.as_of,
                    source_snapshot=f"git:{self.as_of}:sha256:" + "0" * 64,
                ),
                "source_snapshot.consumer",
            ),
            (
                "source-provenance",
                lambda: di.serve_boot_orientation(
                    orientation,
                    legacy.bob(),
                    self.as_of,
                    git_dag=ProvenanceFailure(),
                ),
                "source_snapshot.provenance",
            ),
            (
                "source-bytes",
                lambda: di.serve_boot_orientation(
                    orientation,
                    legacy.bob(),
                    self.as_of,
                    git_dag=DifferentBytes(),
                ),
                "source_snapshot.bytes",
            ),
        )
        for label, operation, expected_field in serve_cases:
            with self.subTest(guard=label):
                result = operation()
                self.assertFalse(result.ok)
                self.assertEqual(
                    result.error.code,
                    di.BootOrientationErrorCode.BINDING_MISMATCH,
                )
                self.assertEqual(result.error.field, expected_field)


class OrientBootRegressionFloor(unittest.TestCase):
    PRE_CYCLE_COMMIT = "f82adb0227f2209d1d475e932cc6389daf5238e8"
    PRE_CYCLE_BLOB = "8ab0af3f1a30c347915237547a20540c352dd847"
    # test_distiller.py legitimately changed after this file's pre-cycle floor:
    # 993820cb (Mike-approved relation-specificity ranker cycle, 2026-08-03)
    # recomputed the fifth feature's frozen canonical and added bounded-boost
    # tests. Keep THIS file pinned to PRE_CYCLE_COMMIT while pinning that imported
    # dependency to the reviewed commit that now owns its bytes.
    IMPORTED_FIXTURE_COMMIT = "993820cb420ddbe9bcfc1f90217c773de557b414"
    IMPORTED_FIXTURE_BLOB = "b2a4239975203a400c55654debbf3b3f8bc4c8d2"

    def _pinned_blob(
        self, relative: str, expected_blob: str, *, commit: str | None = None
    ) -> bytes:
        root = Path(__file__).resolve().parents[3]
        resolved_blob = subprocess.run(
            ["git", "rev-parse", f"{commit or self.PRE_CYCLE_COMMIT}:{relative}"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout.strip()
        self.assertEqual(resolved_blob, expected_blob)
        return subprocess.run(
            ["git", "cat-file", "blob", expected_blob],
            cwd=root,
            capture_output=True,
            timeout=20,
            check=True,
        ).stdout

    def _assert_imported_fixture_bytes(self, current: bytes) -> None:
        baseline = self._pinned_blob(
            "vault/tools/tests/test_distiller.py",
            self.IMPORTED_FIXTURE_BLOB,
            commit=self.IMPORTED_FIXTURE_COMMIT,
        )
        self.assertEqual(
            hashlib.sha256(current).digest(), hashlib.sha256(baseline).digest()
        )
        self.assertEqual(current, baseline)

    def test_entire_precycle_file_reconstructs_to_pinned_blob_bytes(self):
        root = Path(__file__).resolve().parents[3]
        relative = "vault/tools/tests/test_distiller_orient.py"
        baseline = self._pinned_blob(relative, self.PRE_CYCLE_BLOB).decode("utf-8")
        current = Path(__file__).read_text(encoding="utf-8")
        reconstructed = current
        # One carve-out per cycle that appended to this file. The floor's
        # claim is unchanged by adding another: everything OUTSIDE the
        # delimited blocks still has to be the pre-cycle bytes exactly, so a
        # cycle can add tests and cannot quietly edit the ones already here.
        # 2672f9d0 declares its imports inside its own block for the same
        # reason — nothing it adds lands in the pinned region.
        for begin, end in (
            (
                "# BEGIN 77184178 BOOT-ORIENTATION TESTS\n",
                "# END 77184178 BOOT-ORIENTATION TESTS\n",
            ),
            (
                "# BEGIN 2672f9d0 STAGE-C WIRING TESTS\n",
                "# END 2672f9d0 STAGE-C WIRING TESTS\n",
            ),
        ):
            self.assertEqual(reconstructed.count(begin), 1)
            self.assertEqual(reconstructed.count(end), 1)
            start = reconstructed.index(begin)
            stop = reconstructed.index(end, start) + len(end)
            reconstructed = reconstructed[:start] + reconstructed[stop:]
        for added_import in (
            "import inspect\n",
            "import json\n",
            "import subprocess\n",
            "import tempfile\n",
        ):
            self.assertEqual(reconstructed.count(added_import), 1)
            reconstructed = reconstructed.replace(added_import, "", 1)
        self.assertEqual(
            hashlib.sha256(reconstructed.encode("utf-8")).hexdigest(),
            hashlib.sha256(baseline.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(reconstructed, baseline)

    def test_imported_precycle_fixture_dependency_is_pinned_byte_for_byte(self):
        root = Path(__file__).resolve().parents[3]
        current = (root / "vault/tools/tests/test_distiller.py").read_bytes()
        self._assert_imported_fixture_bytes(current)

    def test_imported_fixture_mutation_probe_fails_the_regression_floor(self):
        root = Path(__file__).resolve().parents[3]
        current = (root / "vault/tools/tests/test_distiller.py").read_bytes()
        with self.assertRaises(AssertionError):
            self._assert_imported_fixture_bytes(
                current.replace(b"class _OrientFixture:", b"class _MutatedFixture:", 1)
            )


class HostileWatermarkGauntlet(BootOrientCase):
    def test_resolvable_shape_cannot_hide_unresolvable_or_unreachable_identity(self):
        nonexistent = "f" * 40
        result, _index, _records = self.run_boot(
            memory=_memory_surface(nonexistent)
        )
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error.code,
            di.BootOrientationErrorCode.WATERMARK_MALFORMED,
        )
        abbreviated = self.watermark[:12]
        result, _index, _records = self.run_boot(
            memory=_memory_surface(abbreviated)
        )
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error.code,
            di.BootOrientationErrorCode.WATERMARK_MALFORMED,
        )


# END 77184178 BOOT-ORIENTATION TESTS
# BEGIN 2672f9d0 STAGE-C WIRING TESTS
"""Stage C wired into orient() — the seam, not Stage C's own contract.

``test_orient_stage_c.py`` proves Stage C. Nothing here re-proves it. What
these plants answer is the question that suite structurally cannot: does the
crown actually CALL it, with the right inputs, in the right order, and does a
caller who did not ask for it still pay nothing?

Every plant here therefore drives the real :func:`lib.distiller.orient` over a
real offline Studio — governed files on disk, both index surfaces, the spend
ledger — with a scripted provider and no network. The Stage C fixtures are
imported from the contract suite rather than re-typed: a wiring test that
builds its own idea of what a survivor body looks like is testing its own
fixture.
"""
from vault.tools.tests import test_orient_stage_c as stage_c_plants  # noqa: E402
from lib import orient_stage_c as osc  # noqa: E402
from lib import span_guard  # noqa: E402


STAGE_C_SNAPSHOT = "snapshot-stage-c-orient"
STAGE_C_TASK_UID = stage_c_plants.TASK_UID
TYPOGRAPHY_UID = "aaaa0001"
SENTENCES_UID = "aaaa0002"
HIDDEN_UID = "dddd0001"

# The composed-index copies. DELIBERATELY not the on-disk bodies: Lock 2(a)
# forbids the composed copy as a match domain precisely because it is stripped
# and can lag disk, so if the wiring ever hands Stage C the content loader
# instead of the body reader, the locator plant below goes red rather than
# quietly agreeing with itself.
COMPOSED_COPIES = {
    TYPOGRAPHY_UID: "# Composed\n\nCOMPOSED INDEX COPY - STRIPPED AND STALE",
    SENTENCES_UID: "# Composed\n\nAlso stale, also not the disk bytes.",
}

# Alice's private note, planted on disk in EVERY Studio the harness builds --
# the exposed one and the clean one alike. Visibility is the projection's
# answer, not the filesystem's, and a leaked seed whose file happened not to
# exist would redden the AC12 R1 plant with a missing-file error rather than
# with the different block the floor actually rules out.
HIDDEN_BODY = "Alpha one. Bravo two. Charlie three. Delta four. Echo five.\n"


class RecordingBodyReader:
    """The shipped body reader, recording read order into a shared event log.

    Wraps :func:`lib.distiller.governed_body_reader` rather than standing in
    for it. AC7 and AC9 are claims about reads through the reader the crown
    actually uses; a hand-rolled stand-in that happens to agree with it would
    make both claims about the stand-in.
    """

    def __init__(self, files_root, events):
        self._read = di.governed_body_reader(files_root)
        self._events = events
        self.reads = []

    def __call__(self, uid):
        self._events.append(("read", uid))
        self.reads.append(uid)
        return self._read(uid)


class RecordingLoader(dc.InMemoryContentLoader):
    """``distill``'s content loader, recording into the SAME ordered log.

    AC9 says the brief is written before any body is read. ``distill`` reads
    bodies too — the composed-index copy rather than the on-disk bytes — so
    both kinds of read land in one log and the ordering claim needs no
    argument about which copy of a body counts.
    """

    def __init__(self, bodies, events):
        super().__init__(bodies, index_as_of=STAGE_C_SNAPSHOT, max_chunk_bytes=1024)
        self._events = events
        self.loads = []

    def load_spans(self, uid):
        self._events.append(("load_spans", uid))
        self.loads.append(uid)
        return super().load_spans(uid)


class StageCHarness:
    """One offline Studio wired end to end into ``orient()``.

    The graph, projection and both indexes come from the deterministic
    fixtures; the governed files, spend ledger, policy and run binding come
    from the Stage C contract suite's Studio. The two are joined on UID, which
    is exactly how they are joined in production: the index names an entry and
    the entry is a file on disk.

    ``parse_double`` and ``distill_double`` are supplied on every run so the
    ONLY model edge any plant here can reach is Stage C's. That makes
    "provider.calls" a direct reading of Stage C's spend rather than a mixture
    of three edges.
    """

    def __init__(self, case, *, hidden=(), unresolved=()):
        self.events: list = []
        self.studio = stage_c_plants.StudioFixture(
            {
                TYPOGRAPHY_UID: stage_c_plants.TYPOGRAPHY_BODY,
                SENTENCES_UID: stage_c_plants.SENTENCES_BODY,
                HIDDEN_UID: HIDDEN_BODY,
            }
        )
        case.addCleanup(self.studio.close)
        self.roots = legacy._RootFactory()
        case.addCleanup(self.roots.cleanup)

        self.fx = legacy._OrientFixture(self.roots)
        self.fx.node(STAGE_C_TASK_UID, legacy.TEAM, type_="task", status="active")
        self.fx.node(TYPOGRAPHY_UID, legacy.TEAM, type_="note", status="active")
        self.fx.node(SENTENCES_UID, legacy.TEAM, type_="note", status="active")
        self.fx.rel(STAGE_C_TASK_UID, TYPOGRAPHY_UID, "refs")
        self.fx.rel(STAGE_C_TASK_UID, SENTENCES_UID, "refs")
        for raw_target in unresolved:
            self.fx._node_root[raw_target] = self.roots.manifest_root(legacy.TEAM)
            self.fx.rel(STAGE_C_TASK_UID, raw_target, "refs")
        for uid in hidden:
            # Alice's private segment: planted in the same graph, invisible to
            # the viewer, and proposed as a query seed anyway (AC12 R1).
            self.fx.node(uid, legacy.PRIV_ALICE, type_="note", status="active")
            self.fx.rel(STAGE_C_TASK_UID, uid, "refs")
        self.hidden = tuple(hidden)

        self.viewer = legacy.bob()
        self.query_index = dq.InMemoryQueryIndex(
            {
                TYPOGRAPHY_UID: "needle guard",
                # Indexed too, so the FTS-fallback branch of resolve_query has
                # an invisible candidate of its own to drop.
                **{uid: "needle hidden" for uid in hidden},
            },
            index_as_of=STAGE_C_SNAPSHOT,
        )
        self.circle_index = tc.InMemoryStructuralIndex(
            self.fx._structures, index_as_of=STAGE_C_SNAPSHOT
        )
        self.loader = RecordingLoader(COMPOSED_COPIES, self.events)
        self.files_root = self.studio.root / "vault/files"
        self.body_reader = RecordingBodyReader(self.files_root, self.events)
        self.provider = stage_c_plants.FakeProvider(
            self.events, ledger_root=self.studio.ledger_root
        )
        self.script()
        self.reservation_ids = iter(f"cc0001{index:02d}" for index in range(1, 40))

    def script(self, *, brief=None, spans=None):
        """Script C1 and C2. ``spans`` may be a list of successive responses."""
        self.brief = brief or (
            "The task needs the guard clause that keeps model typography out "
            "of the emitted block, judged against the source bytes on disk."
        )
        self.provider.script(osc.C1_TASK_CLASS, [{"brief": self.brief}])
        proposals = spans if spans is not None else [
            [{"uid": TYPOGRAPHY_UID, "span_text": stage_c_plants.TYPOGRAPHY_MODEL_SPAN}]
        ]
        self.provider.script(
            osc.C2_TASK_CLASS, [{"spans": proposal} for proposal in proposals]
        )
        return self

    def request(self, **overrides):
        values = dict(
            task_source=stage_c_plants.FakeTaskSource(),
            body_reader=self.body_reader,
            provider_call=self.provider,
            clock=lambda: stage_c_plants.CLOCK,
            reservation_id_factory=lambda: next(self.reservation_ids),
            environment={},
        )
        values.update(overrides)
        return di.StageCRequest(**values)

    def orient(self, **overrides):
        values = dict(
            intent="needle",
            index_as_of=STAGE_C_SNAPSHOT,
            chunk_budget=2,
            projection=self.fx.projection(),
            query_index=self.query_index,
            circle_index=self.circle_index,
            rank_index=self.fx.rank_index(),
            content_loader=self.loader,
            # The parse-query seed proposal, invisible candidates included:
            # resolve_query resolves it through the projection before Stage C
            # is handed anything.
            parse_double=lambda **_kwargs: (TYPOGRAPHY_UID, *self.hidden),
            distill_double=lambda **_kwargs: None,
            model_run_binding=self.studio.binding(),
            model_policy_resolver=self.studio.policy,
            segment_resolver=lambda _uid: "os",
            stage_c=None,
        )
        values.update(overrides)
        return di.orient(STAGE_C_TASK_UID, self.viewer, 16, **values)

    def model_tasks(self):
        return [call["task"] for call in self.provider.calls]

    def source_bytes(self, uid):
        return span_guard.match_domain_bytes(self.studio.files[uid])


class StageCWiringCase(unittest.TestCase):
    def setUp(self):
        self.h = StageCHarness(self)

    def block(self, **overrides):
        result = self.h.orient(stage_c=self.h.request(**overrides))
        self.assertTrue(result.ok, msg=result.error)
        return result.value.stage_c


# --------------------------------------------------------------------------- #
# The spend gate. Stage C calls a metered model edge; wiring it must not make  #
# a caller who says nothing start paying.                                      #
# --------------------------------------------------------------------------- #
class StageCSpendGateTests(StageCWiringCase):
    def test_a_run_that_does_not_opt_in_reaches_no_metered_edge(self):
        """The gate, with the control that proves the probe is on the path.

        The negative half of this plant is worth exactly nothing on its own: a
        patch on a symbol the code path never reaches records zero calls for
        the wrong reason. So the same spy, in the same patch, is then shown to
        fire once when the request IS supplied. If the wiring is deleted, the
        control goes red; if the gate is deleted, the claim goes red.
        """
        with mock.patch.object(di, "run_stage_c", wraps=osc.run_stage_c) as spy:
            silent = self.h.orient()
            self.assertTrue(silent.ok, msg=silent.error)
            self.assertEqual(spy.call_count, 0, msg="Stage C ran without being asked")
            self.assertEqual(
                self.h.provider.calls,
                [],
                msg="a run that did not opt in reached the metered edge",
            )

            opted_in = self.h.orient(stage_c=self.h.request())
            self.assertTrue(opted_in.ok, msg=opted_in.error)
            self.assertEqual(
                spy.call_count,
                1,
                msg="CONTROL: the patched symbol is not the one orient() calls, "
                "so the assertion above proved nothing",
            )
        self.assertEqual(
            self.h.model_tasks(), [osc.C1_TASK_CLASS, osc.C2_TASK_CLASS]
        )

    def test_the_returned_type_says_whether_stage_c_ran(self):
        """"Did this cost money?" is answerable without reading the ledger."""
        silent = self.h.orient()
        self.assertIs(type(silent.value), de.Orientation)
        self.assertNotIsInstance(silent.value, di.SpanOrientation)
        self.assertFalse(hasattr(silent.value, "stage_c"))

        opted_in = self.h.orient(stage_c=self.h.request())
        self.assertIsInstance(opted_in.value, di.SpanOrientation)
        # Still an Orientation, so a consumer that type-checks keeps working.
        self.assertIsInstance(opted_in.value, de.Orientation)
        self.assertIsInstance(opted_in.value.stage_c, osc.StageCBlock)

    def test_the_gate_defaults_closed_on_the_signature_itself(self):
        """No flag, no environment variable, no policy state — one parameter.

        Asserted on the signature because that is where a later 'convenience'
        default would land, and a default of anything other than None is the
        crown deciding to spend on a caller's behalf.
        """
        parameters = inspect.signature(di.orient).parameters
        self.assertIn("stage_c", parameters)
        self.assertIsNone(parameters["stage_c"].default)
        self.assertIs(
            parameters["stage_c"].kind, inspect.Parameter.KEYWORD_ONLY
        )


class StageCReferenceObservationTests(unittest.TestCase):
    def test_stage_c_body_reader_never_receives_reference_observations(self):
        harness = StageCHarness(self, unresolved=("deadbeef",))
        result = harness.orient(stage_c=harness.request())
        self.assertTrue(result.ok, msg=result.error)

        deterministic = result.value.bound_deterministic.deterministic
        self.assertEqual(
            tuple(
                observation.raw_target
                for observation in deterministic.reference_observations
            ),
            ("deadbeef",),
        )
        self.assertNotIn("deadbeef", deterministic.uids())
        self.assertNotIn("deadbeef", result.value.stage_c.circle)
        self.assertNotIn("deadbeef", harness.body_reader.reads)
        self.assertNotIn("deadbeef", harness.loader.loads)


# --------------------------------------------------------------------------- #
# The extractive claim, made through orient() rather than asserted about it.   #
# --------------------------------------------------------------------------- #
class StageCExtractiveClaimTests(StageCWiringCase):
    def test_orient_returns_spans_byte_identical_to_the_governed_source(self):
        block = self.block()
        self.assertTrue(block.spans, "orient() produced no spans to check")
        body = self.h.source_bytes(TYPOGRAPHY_UID).decode("utf-8")
        for guarded in block.spans:
            with self.subTest(uid=guarded.uid):
                self.assertEqual(
                    guarded.span_text,
                    body[guarded.locator.char_start : guarded.locator.char_end],
                )
                self.assertEqual(
                    guarded.span_text.encode("utf-8"),
                    body[
                        guarded.locator.char_start : guarded.locator.char_end
                    ].encode("utf-8"),
                )
        # CONTROL: the claim is only interesting if a model actually proposed
        # something. A run where C2 never happened has no spans to be faithful.
        self.assertIn(osc.C2_TASK_CLASS, self.h.model_tasks())

    def test_the_models_typography_never_reaches_the_block(self):
        """The whole of Lock 2, observed at the crown's own return value."""
        proposed = stage_c_plants.TYPOGRAPHY_MODEL_SPAN
        # CONTROL: the fixture must actually differ from the source, or
        # "the model's text did not survive" is true of a no-op.
        self.assertNotEqual(proposed, stage_c_plants.TYPOGRAPHY_SOURCE_SPAN)
        self.assertIn("\u2019", proposed)
        self.assertIn("\u2014", proposed)

        block = self.block()
        emitted = [guarded.span_text for guarded in block.spans]
        self.assertEqual(emitted, [stage_c_plants.TYPOGRAPHY_SOURCE_SPAN])
        for text in emitted:
            self.assertNotIn("\u2019", text)
            self.assertNotIn("\u2014", text)

    def test_the_locator_indexes_the_disk_bytes_not_the_composed_index_copy(self):
        """Proves WHICH reader the crown wired in, not merely that one exists.

        The content loader in this harness carries a deliberately divergent
        copy of both bodies. If ``orient()`` ever hands Stage C the loader
        instead of the body reader, every locator hash below moves.
        """
        block = self.block()
        disk = hashlib.sha256(self.h.source_bytes(TYPOGRAPHY_UID)).hexdigest()
        composed = hashlib.sha256(
            COMPOSED_COPIES[TYPOGRAPHY_UID].encode("utf-8")
        ).hexdigest()
        self.assertNotEqual(disk, composed)
        self.assertTrue(block.spans)
        for guarded in block.spans:
            self.assertEqual(guarded.locator.body_sha256, disk)
            self.assertNotEqual(guarded.locator.body_sha256, composed)


# --------------------------------------------------------------------------- #
# Lock 3's ordering, through the composed call path.                           #
# --------------------------------------------------------------------------- #
class StageCOrderingTests(StageCWiringCase):
    def test_ac9_c1_precedes_every_body_read_on_the_orient_path(self):
        """Lock 3 is an ordering property, so it is read off an ordered log.

        The log carries three kinds of event from three different objects: the
        scripted provider's model calls, the body reader's on-disk reads, and
        the content loader's composed-copy reads. Both kinds of read are in
        there on purpose. A brief written after the corpus has been read is a
        summary of the corpus, and which COPY of the corpus was read is not a
        distinction that rescues it.
        """
        self.block()
        reads = [event for event in self.h.events if event[0] == "read"]
        loads = [event for event in self.h.events if event[0] == "load_spans"]
        models = [event for event in self.h.events if event[0] == "model"]
        # CONTROL: an ordering claim over an empty log is vacuously true, and
        # all three populations must be non-empty for it to mean anything.
        self.assertTrue(reads, "no survivor body was read; the claim is vacuous")
        self.assertTrue(loads, "distill never ran; the claim is vacuous")
        self.assertTrue(models, "no model was called; the claim is vacuous")

        self.assertEqual(self.h.events[0], ("model", osc.C1_TASK_CLASS))
        first_c1 = self.h.events.index(("model", osc.C1_TASK_CLASS))
        for index, event in enumerate(self.h.events):
            if event[0] in {"read", "load_spans"}:
                with self.subTest(event=event):
                    self.assertGreater(
                        index,
                        first_c1,
                        msg=f"{event} precedes C1; got {self.h.events}",
                    )

    def test_ac9_no_survivor_body_is_smuggled_into_the_brief_prompt(self):
        """The other half of Lock 3: C1's payload cannot contain what it must
        not have seen. Ordering alone would still permit a caller that handed
        the bodies to C1 through the task stub."""
        self.block()
        c1 = next(
            call
            for call in self.h.provider.calls
            if call["task"] == osc.C1_TASK_CLASS
        )
        payload = json.dumps(c1["messages"], sort_keys=True)
        self.assertIn(STAGE_C_TASK_UID, payload)
        for uid in (TYPOGRAPHY_UID, SENTENCES_UID):
            with self.subTest(uid=uid):
                body = self.h.source_bytes(uid).decode("utf-8").strip()
                self.assertNotIn(body, payload)
        self.assertNotIn(stage_c_plants.TYPOGRAPHY_SOURCE_SPAN, payload)

    def test_ac7_each_survivor_body_is_read_exactly_once_through_orient(self):
        self.block()
        # CONTROL: both survivors must have been read, or "exactly once" is a
        # statement about an empty set.
        self.assertEqual(set(self.h.body_reader.reads), {TYPOGRAPHY_UID, SENTENCES_UID})
        for uid in set(self.h.body_reader.reads):
            with self.subTest(uid=uid):
                self.assertEqual(self.h.body_reader.reads.count(uid), 1)

    def test_ac7_a_repair_retry_does_not_re_read_through_the_wired_reader(self):
        self.h.script(
            spans=[
                [{"uid": TYPOGRAPHY_UID, "span_text": "Nowhere in the source."}],
                [
                    {
                        "uid": TYPOGRAPHY_UID,
                        "span_text": stage_c_plants.TYPOGRAPHY_MODEL_SPAN,
                    }
                ],
            ]
        )
        block = self.block()
        # CONTROL: the repair must actually have been spent, or this is the
        # no-repair plant above wearing a different name.
        self.assertEqual(len(block.model_calls), osc.MODEL_CALL_CEILING)
        self.assertEqual(self.h.body_reader.reads.count(TYPOGRAPHY_UID), 1)


# --------------------------------------------------------------------------- #
# Composition: what Stage C was given, and what it left alone.                 #
# --------------------------------------------------------------------------- #
class StageCCompositionTests(StageCWiringCase):
    def test_stage_c_composes_with_distill_and_leaves_it_byte_equal(self):
        """The existing path is not disturbed by the new one running first."""
        without = self.h.orient()
        self.assertTrue(without.ok, msg=without.error)
        with_stage_c = self.h.orient(stage_c=self.h.request())
        self.assertTrue(with_stage_c.ok, msg=with_stage_c.error)

        self.assertEqual(with_stage_c.value.distillation, without.value.distillation)
        self.assertEqual(with_stage_c.value.query_seeds, without.value.query_seeds)
        self.assertEqual(
            with_stage_c.value.bound_deterministic, without.value.bound_deterministic
        )
        # CONTROL: the distillation must carry something, or equality between
        # two empty values would pass with the distill path removed entirely.
        self.assertTrue(without.value.distillation.chunks)

    def test_the_ranking_stage_c_verifies_carries_this_runs_stamps(self):
        """R2 is 'stamped at rank, verified at distill'. This is the stamp.

        Stage C refuses on a viewer or as-of that is not this run's, so the
        value handed to it has to carry both, and it has to carry the ranked
        order the deterministic core actually produced — not a re-derivation.
        """
        result = self.h.orient(stage_c=self.h.request())
        self.assertTrue(result.ok, msg=result.error)
        orientation = result.value
        deterministic = orientation.bound_deterministic.deterministic
        ranking = orientation.stage_c.ranking

        self.assertIsInstance(ranking, di.StageBRanking)
        self.assertEqual(ranking.viewer, self.h.viewer)
        self.assertEqual(ranking.index_as_of, STAGE_C_SNAPSHOT)
        self.assertEqual(ranking.uids, deterministic.uids())
        self.assertIs(ranking.deterministic, deterministic)
        # CONTROL: an empty ranking would satisfy the equality above trivially.
        self.assertEqual(ranking.uids, (TYPOGRAPHY_UID, SENTENCES_UID))

    def test_the_block_carries_the_circle_the_deterministic_core_drew(self):
        result = self.h.orient(stage_c=self.h.request())
        self.assertTrue(result.ok, msg=result.error)
        members = tuple(
            member.uid
            for member in result.value.bound_deterministic.deterministic.circle.members
        )
        self.assertEqual(result.value.stage_c.circle, members)
        self.assertTrue(members)


# --------------------------------------------------------------------------- #
# Refusals: what the seam does when Stage C, or its inputs, say no.            #
# --------------------------------------------------------------------------- #
class StageCRefusalTests(StageCWiringCase):
    def test_ac13_a_corpus_scale_run_without_receipts_refuses_before_spending(self):
        """AC13 is not routed around, and it refuses on the near side of spend."""
        refused = self.h.orient(
            stage_c=self.h.request(corpus_scale=True, rehearsal_receipt=None)
        )
        self.assertFalse(refused.ok)
        self.assertIsInstance(refused.error, osc.StageCRefusal)
        self.assertEqual(
            refused.error.reason, osc.REASON_UNREHEARSED_CORPUS_SCALE
        )
        self.assertEqual(
            self.h.provider.calls, [], msg="AC13 refused only after spending"
        )

        receipt = {"kind": "capped-rehearsal", "max_survivors": osc.K_SURVIVORS}
        # CONTROL: the same run with receipts must succeed, or the refusal
        # above could be coming from anything else in the harness.
        admitted = self.h.orient(
            stage_c=self.h.request(corpus_scale=True, rehearsal_receipt=receipt)
        )
        self.assertTrue(admitted.ok, msg=admitted.error)
        self.assertEqual(admitted.value.stage_c.rehearsal_receipt, receipt)

    def test_a_stage_c_refusal_propagates_typed_and_untranslated(self):
        """Stage C's named reason survives the seam intact.

        Collapsing it into a DistillError would answer "the distillation was
        unavailable" for a run whose guard could not place a single span, and
        those are different facts about different parts of the system.
        """
        unplaceable = [
            [{"uid": TYPOGRAPHY_UID, "span_text": f"Absent sentence {n} entirely."}]
            for n in range(4)
        ]
        self.h.script(spans=unplaceable)
        refused = self.h.orient(stage_c=self.h.request())
        self.assertFalse(refused.ok)
        self.assertIsInstance(refused.error, osc.StageCRefusal)
        self.assertNotIsInstance(refused.error, de.DistillError)
        self.assertEqual(refused.error.reason, osc.REASON_SPAN_GUARD)
        # CONTROL: the refusal must have come from the guard after the edge
        # was reached, not from an input gate before it.
        self.assertEqual(len(self.h.provider.calls), osc.MODEL_CALL_CEILING)

    def test_stage_c_without_a_segment_classifier_refuses_before_the_edge(self):
        """AC5's egress gate cannot decide from nothing, so nothing is spent."""
        refused = self.h.orient(
            stage_c=self.h.request(), segment_resolver=None
        )
        self.assertFalse(refused.ok)
        self.assertIsInstance(refused.error, de.DistillError)
        self.assertEqual(refused.error.code, de.DistillErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.h.provider.calls, [])

        # CONTROL: the identical run with a classifier succeeds.
        admitted = self.h.orient(stage_c=self.h.request())
        self.assertTrue(admitted.ok, msg=admitted.error)

    def test_stage_c_without_a_run_binding_refuses_before_the_edge(self):
        refused = self.h.orient(
            stage_c=self.h.request(), model_run_binding=None
        )
        self.assertFalse(refused.ok)
        self.assertIsInstance(refused.error, de.DistillError)
        self.assertEqual(refused.error.code, de.DistillErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.h.provider.calls, [])

        admitted = self.h.orient(stage_c=self.h.request())
        self.assertTrue(admitted.ok, msg=admitted.error)

    def test_a_task_stub_for_another_task_refuses_before_c1(self):
        """C1 briefs the task it was handed. Briefing one task from another's
        title and body is a wrong answer that looks exactly like a right one."""
        other = stage_c_plants.FakeTaskSource(uid="7a5c0002")
        refused = self.h.orient(stage_c=self.h.request(task_source=other))
        self.assertFalse(refused.ok)
        self.assertIsInstance(refused.error, de.DistillError)
        self.assertEqual(refused.error.code, de.DistillErrorCode.BINDING_MISMATCH)
        self.assertEqual(self.h.provider.calls, [])

        # CONTROL: the same stub bound to this task is admitted.
        admitted = self.h.orient(
            stage_c=self.h.request(
                task_source=stage_c_plants.FakeTaskSource(uid=STAGE_C_TASK_UID)
            )
        )
        self.assertTrue(admitted.ok, msg=admitted.error)

    def test_an_unreadable_survivor_body_is_typed_not_a_raised_oserror(self):
        """A ranked entry whose governed file is gone is a substrate fault, and
        ``distill`` already answers that fault with CONTENT_UNAVAILABLE. The
        crown returns a Result; it must not start raising instead."""
        path = self.h.studio.files[SENTENCES_UID]
        # CONTROL: the run is otherwise sound, so the failure below can only be
        # the missing file.
        self.assertTrue(path.exists())
        path.unlink()

        refused = self.h.orient(stage_c=self.h.request())
        self.assertFalse(refused.ok)
        self.assertIsInstance(refused.error, de.DistillError)
        self.assertEqual(
            refused.error.code, de.DistillErrorCode.CONTENT_UNAVAILABLE
        )
        self.assertIn(SENTENCES_UID, refused.error.message)


# --------------------------------------------------------------------------- #
# AC12 R1, through the crown: the seeds Stage C is given are already resolved. #
# --------------------------------------------------------------------------- #
class StageCViewerFloorTests(unittest.TestCase):
    """AC12 R1 through the crown, over BOTH routes a seed can arrive by.

    ``resolve_query`` resolves candidates through the projection in two
    separate places: once for the parse model's proposal, and once for the
    FTS fallback when no proposal is usable. They are different lines of code
    and a floor that holds on only one of them is a floor with a door in it,
    so every plant here runs both.
    """

    #: ``(name, parse_double, fallback_expected)``. The doubles decline or
    #: propose; which line of ``resolve_query`` then does the resolving is the
    #: thing being varied, and ``fallback_used`` on the returned seeds is the
    #: control that says which one actually ran.
    ROUTES = (
        ("parse-proposal", lambda hidden: (lambda **_kw: (TYPOGRAPHY_UID, *hidden)), False),
        ("fts-fallback", lambda _hidden: (lambda **_kw: None), True),
    )

    def _run(self, parse_double_for, *, hidden):
        harness = StageCHarness(self, hidden=hidden)
        result = harness.orient(
            stage_c=harness.request(),
            parse_double=parse_double_for(harness.hidden),
        )
        self.assertTrue(result.ok, msg=result.error)
        return harness, result

    def test_ac12_r1_the_block_is_identical_whether_invisible_seeds_exist(self):
        """The strongest form of "no leak": not that hidden UIDs are absent
        from the block, but that the block is the SAME VALUE either way, so no
        count, total or gap can be inferred from it.

        Through ``orient()`` this holds for a stronger reason than Stage C's
        own class-grain filter: ``resolve_query`` has already resolved the seed
        candidates through the projection at UID grain, so an invisible one
        never reaches Stage C at all. The harness classifies every UID as
        OS-segment precisely so Stage C's own filter cannot be what passes
        this — if the crown stopped resolving seeds, nothing downstream would
        catch it.
        """
        for name, parse_double_for, fallback_expected in self.ROUTES:
            with self.subTest(route=name):
                exposed, with_hidden = self._run(
                    parse_double_for, hidden=(HIDDEN_UID,)
                )
                clean, without_hidden = self._run(parse_double_for, hidden=())

                # CONTROL: the hidden node must really be in the exposed graph,
                # really be an indexed candidate, and really be invisible to
                # this viewer — or the two runs are the same run.
                self.assertIn(HIDDEN_UID, exposed.fx._structures)
                self.assertNotIn(HIDDEN_UID, clean.fx._structures)
                self.assertIn(
                    HIDDEN_UID, exposed.query_index.search_uids(("needle",))
                )
                self.assertNotIn(
                    HIDDEN_UID, clean.query_index.search_uids(("needle",))
                )
                self.assertEqual(exposed.hidden, (HIDDEN_UID,))
                # CONTROL: and the route under test must be the one that ran.
                self.assertEqual(
                    with_hidden.value.query_seeds.fallback_used,
                    fallback_expected,
                    msg=f"the {name} route was not the one resolve_query took",
                )
                self.assertEqual(
                    with_hidden.value.query_seeds.uids, (TYPOGRAPHY_UID,)
                )

                self.assertEqual(
                    with_hidden.value.stage_c, without_hidden.value.stage_c
                )
                self.assertNotIn(HIDDEN_UID, repr(with_hidden.value.stage_c))


# --------------------------------------------------------------------------- #
# The body reader itself: one definition of "body", not a second one.          #
# --------------------------------------------------------------------------- #
class GovernedBodyReaderTests(unittest.TestCase):
    def setUp(self):
        self.studio = stage_c_plants.StudioFixture(
            {TYPOGRAPHY_UID: stage_c_plants.TYPOGRAPHY_BODY}
        )
        self.addCleanup(self.studio.close)
        self.read = di.governed_body_reader(self.studio.root / "vault/files")

    def test_it_returns_the_shipped_lock_2a_match_domain_and_nothing_else(self):
        expected = span_guard.match_domain_bytes(self.studio.files[TYPOGRAPHY_UID])
        # CONTROL: an empty body would make any two readers agree.
        self.assertTrue(expected)
        self.assertEqual(self.read(TYPOGRAPHY_UID), expected)
        self.assertEqual(
            self.read(TYPOGRAPHY_UID).decode("utf-8"),
            stage_c_plants.TYPOGRAPHY_BODY,
        )

    def test_it_refuses_anything_that_is_not_a_governed_uid(self):
        """The argument crosses into a path join, so the check lives here too."""
        for candidate in ("../../etc/passwd", "AAAA0001", "aaaa000", "", None):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    self.read(candidate)


# END 2672f9d0 STAGE-C WIRING TESTS
if __name__ == "__main__":
    unittest.main()
