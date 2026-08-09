#!/usr/bin/env python3
"""Focused isolated plants for the Gardener Pruning writer/projection slice."""
from __future__ import annotations

import contextlib
import copy
import fcntl
import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


writer = _load("gardener_verdict_test_target", TOOLS / "tropo-gardener-verdict.py")
rebuild = _load("gardener_verdict_test_rebuild", TOOLS / "tropo-rebuild-index.py")
tool_validators = _load(
    "gardener_verdict_tool_validators",
    ROOT / ".tropo" / "scripts" / "lib" / "tool_validators.py",
)
from lib import index_surfaces  # noqa: E402
from lib.normalized_body_hash import (  # noqa: E402
    normalized_body_sha256,
    raw_body_sha256,
)


TARGET_UID = "11111111"
POLICY_UID = "22222222"
STUDIO_UID = "5747d1a0"
JUDGE_PROMPT_SHA256 = "b" * 64
HUMAN_UID = "33333333"
AGENT_UID = "44444444"
OTHER_POLICY_UID = "55555555"
FIXED_NOW = datetime(2026, 7, 17, 10, 0, 0, tzinfo=timezone.utc)
DEFAULT_BODY = (
    b"# Fixture\n\n"
    b"This body is superseded by the canonical replacement.\n\n"
    b"Second evidence sentence.\n"
)
FIRST_EVIDENCE = "This body is superseded by the canonical replacement."
SECOND_EVIDENCE = "Second evidence sentence."


class IsolatedVault:
    def __init__(self, home: str = "vault/files", body: bytes = DEFAULT_BODY):
        self._tmp = tempfile.TemporaryDirectory()
        # .resolve(): macOS tempfile returns /var/folders/..., a symlink to
        # /private/var/folders/.... rebuild_index() resolves its own root and
        # then checks transaction destinations against an allowlist, so an
        # unresolved fixture root fails setup before any assertion runs.
        # This fixture is imported by test_pruning_contract too, so the one line
        # clears both suites. (metis-g103 2026-08-06 — fourth and fifth instance
        # of this defect today; the tool was never wrong in any of them.)
        self.root = Path(self._tmp.name).resolve()
        (self.root / ".tropo").mkdir()
        # origin_studio is resolved from STUDIO.md by the writer (never caller-
        # supplied), so an isolated vault needs its own studio identity.
        (self.root / "STUDIO.md").write_text(
            "---\n"
            f"uid: {STUDIO_UID}\n"
            "tier: vault\n"
            "vault_name: Isolated Fixture Studio\n"
            "---\n"
            "# Isolated Fixture Studio\n",
            encoding="utf-8",
        )
        self.body = body
        paths = {
            "vault/files": self.root / "vault" / "files" / f"{TARGET_UID}.md",
            "vault/agents": self.root / "vault" / "agents" / f"{TARGET_UID}.md",
            "agents": self.root / "agents" / "talos" / "roadmap.md",
            "vault/capsules": (
                self.root
                / "vault"
                / "capsules"
                / "tropo-fixture.capsule.md"
            ),
        }
        self.target = paths[home]
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self._write_target()

        files = self.root / "vault" / "files"
        files.mkdir(parents=True, exist_ok=True)
        self.policy = files / f"{POLICY_UID}.md"
        self.human = files / f"{HUMAN_UID}.md"
        self.agent = files / f"{AGENT_UID}.md"
        self.other_policy = files / f"{OTHER_POLICY_UID}.md"
        self._write_policy(self.policy, POLICY_UID, "active", "active", "1.0.0")
        self._write_principal(self.human, HUMAN_UID, "human")
        self._write_principal(self.agent, AGENT_UID, "agent-executive")
        self._write_policy(
            self.other_policy,
            OTHER_POLICY_UID,
            "archived",
            "archived",
            "9.0.0",
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = rebuild.rebuild_index(self.root, True)
        if rc != 0:
            raise AssertionError(f"isolated index setup failed with exit {rc}")

    def close(self):
        self._tmp.cleanup()

    def _write_target(self):
        self.target.write_bytes(
            (
                f"---\n"
                f"uid: {TARGET_UID}\n"
                "type: document\n"
                "title: Writer fixture\n"
                "description: Isolated Gardener writer plant.\n"
                "status: active\n"
                "state: active\n"
                "owner: test\n"
                "created: '2026-07-17'\n"
                "modified: '2026-07-17'\n"
                "modified_by: fixture\n"
                "schema_version: 2\n"
                "---\n"
            ).encode("utf-8")
            + self.body
        )

    @staticmethod
    def _write_policy(path: Path, uid: str, status: str, state: str, version: str):
        path.write_text(
            "---\n"
            f"uid: {uid}\n"
            "type: loop\n"
            f"title: Policy {uid}\n"
            "description: Isolated body judge policy.\n"
            f"status: {status}\n"
            f"state: {state}\n"
            "owner: test\n"
            "author: test\n"
            f"version: '{version}'\n"
            "runner: gardener-body-judge\n"
            f"judge_prompt_sha256: {JUDGE_PROMPT_SHA256}\n"
            "created: '2026-07-17'\n"
            "modified: '2026-07-17'\n"
            "schema_version: 2\n"
            "---\n"
            "# Policy\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_principal(path: Path, uid: str, principal_class: str):
        path.write_text(
            "---\n"
            f"uid: {uid}\n"
            "type: principal\n"
            f"title: Principal {uid}\n"
            "description: Isolated principal.\n"
            "status: active\n"
            "state: active\n"
            "owner: test\n"
            f"principal_class: {principal_class}\n"
            "created: '2026-07-17'\n"
            "modified: '2026-07-17'\n"
            "schema_version: 2\n"
            "---\n"
            "# Principal\n",
            encoding="utf-8",
        )

    def body_bytes(self) -> bytes:
        return writer._read_snapshot(self.target).body

    def request(
        self,
        evidence: str = FIRST_EVIDENCE,
        *,
        verdict: str = "superseded",
        policy_uid: str = POLICY_UID,
        version: str = "1.0.0",
        confidence: float = 0.91,
    ):
        body = self.body_bytes()
        encoded = evidence.encode("utf-8")
        start = body.index(encoded)
        return writer.StampRequest(
            uid=TARGET_UID,
            verdict=verdict,
            evidence_span=evidence,
            start_byte=start,
            end_byte=start + len(encoded),
            expected_body_sha256=raw_body_sha256(self.target),
            expected_normalized_body_sha256=normalized_body_sha256(self.target),
            judge_policy_uid=policy_uid,
            judge_version=version,
            confidence=confidence,
            actor="gardener-body-judge-test",
        )

    def stamp(self, request=None, **kwargs):
        request = request or self.request()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return writer.stamp_verdict(
                request,
                vault_root=self.root,
                now=lambda: FIXED_NOW,
                **kwargs,
            )

    def override(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return writer.add_keep_override(
                TARGET_UID,
                by=kwargs.pop("by", HUMAN_UID),
                reason=kwargs.pop("reason", "Human review says keep this body."),
                vault_root=self.root,
                now=lambda: FIXED_NOW,
                **kwargs,
            )

    def freshen(self, uid: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return rebuild.freshen_one(uid, self.root)

    def set_policy_version(self, version: str):
        text = self.policy.read_text(encoding="utf-8")
        text = text.replace("version: '1.0.0'", f"version: '{version}'")
        self.policy.write_text(text, encoding="utf-8")
        if self.freshen(POLICY_UID) != 0:
            raise AssertionError("policy version freshen failed")

    def switch_policy(self):
        first = self.policy.read_text(encoding="utf-8")
        first = first.replace("status: active", "status: archived", 1)
        first = first.replace("state: active", "state: archived", 1)
        self.policy.write_text(first, encoding="utf-8")
        second = self.other_policy.read_text(encoding="utf-8")
        second = second.replace("status: archived", "status: active", 1)
        second = second.replace("state: archived", "state: active", 1)
        self.other_policy.write_text(second, encoding="utf-8")
        # A policy switch intentionally changes two canonical sources. The
        # global incremental-authority contract therefore requires one full
        # apply; sequential --only calls would certify stale peer state.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = rebuild.rebuild_index(self.root, True)
        if rc != 0:
            raise AssertionError("policy switch full-apply cure failed")

    def pruning(self) -> dict | None:
        return writer._read_snapshot(self.target).frontmatter.get("pruning")

    def projected(self) -> tuple[dict, dict]:
        rows = [
            row
            for row in index_surfaces.load_index_records(
                self.root,
                include_archive=True,
            )
            if row.get("uid") == TARGET_UID
        ]
        if len(rows) != 1:
            raise AssertionError(f"expected one target row, got {len(rows)}")
        with sqlite3.connect(self.root / "vault" / "00-index.sqlite") as conn:
            sqlite_row = conn.execute(
                "SELECT fm_json FROM entries WHERE uid=?",
                (TARGET_UID,),
            ).fetchone()
        if not sqlite_row:
            raise AssertionError("missing target SQLite row")
        return rows[0], json.loads(sqlite_row[0])

    def rewrite_target_index_path(self, relative_path: str):
        changed = False
        for name in (
            index_surfaces.CURRENT_INDEX_NAME,
            index_surfaces.ARCHIVE_INDEX_NAME,
        ):
            path = self.root / "vault" / name
            rows = list(index_surfaces.iter_jsonl(path))
            for row in rows:
                if row.get("uid") == TARGET_UID:
                    row["path"] = relative_path
                    changed = True
            index_surfaces.write_jsonl_atomic(path, rows)
        if not changed:
            raise AssertionError("target index row not found")


class GardenerVerdictWriterTests(unittest.TestCase):
    def test_valid_stamp_is_body_safe_and_query_visible(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        before_body = fixture.body_bytes()
        before_t1 = raw_body_sha256(fixture.target)
        before_t2 = normalized_body_sha256(fixture.target)

        result = fixture.stamp()

        self.assertEqual(result.operation, "stamp")
        self.assertTrue(result.source_changed)
        self.assertEqual(fixture.body_bytes(), before_body)
        self.assertEqual(raw_body_sha256(fixture.target), before_t1)
        self.assertEqual(normalized_body_sha256(fixture.target), before_t2)
        pruning = fixture.pruning()
        self.assertEqual(pruning["judge_policy_uid"], POLICY_UID)
        addressed = before_body[
            pruning["evidence_locator"]["start_byte"]:
            pruning["evidence_locator"]["end_byte"]
        ]
        self.assertEqual(addressed.decode("utf-8"), pruning["evidence_span"])
        jsonl, sqlite_record = fixture.projected()
        self.assertEqual(jsonl["pruning"], pruning)
        self.assertEqual(sqlite_record["pruning"], pruning)

    def test_evidence_refusals_leave_source_unchanged(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        base = fixture.request()
        before = fixture.target.read_bytes()
        variants = [
            replace(base, evidence_span=None),
            replace(base, evidence_span=""),
            replace(base, start_byte=-1),
            replace(base, end_byte=len(fixture.body_bytes()) + 1),
            replace(base, evidence_span="different"),
        ]
        for request in variants:
            with self.subTest(request=request):
                with self.assertRaisesRegex(
                    writer.GardenerVerdictError,
                    "core pruning contract v1.7",
                ):
                    fixture.stamp(request)
                self.assertEqual(fixture.target.read_bytes(), before)

    def test_nav_and_invalid_utf8_evidence_refuse(self):
        nav_body = (
            b"Alpha\n"
            b"<!-- nav-block:start -->\n"
            b"Generated evidence.\n"
            b"<!-- nav-block:end -->\n"
            b"Omega\n"
        )
        nav_fixture = IsolatedVault(body=nav_body)
        self.addCleanup(nav_fixture.close)
        nav_request = nav_fixture.request(evidence="Generated evidence.")
        with self.assertRaisesRegex(writer.GardenerVerdictError, "nav-block"):
            nav_fixture.stamp(nav_request)

        invalid_fixture = IsolatedVault(body=b"Valid evidence.\nBroken: \xff\n")
        self.addCleanup(invalid_fixture.close)
        body = invalid_fixture.body_bytes()
        invalid_index = body.index(b"\xff")
        request = invalid_fixture.request(evidence="Valid evidence.")
        invalid_request = replace(
            request,
            evidence_span="\ufffd",
            start_byte=invalid_index,
            end_byte=invalid_index + 1,
        )
        with self.assertRaisesRegex(writer.GardenerVerdictError, "invalid UTF-8"):
            invalid_fixture.stamp(invalid_request)

    def test_malformed_existing_and_closed_shape_constraints_refuse(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        fixture.stamp()
        text = fixture.target.read_text(encoding="utf-8")
        fixture.target.write_text(
            text.replace("  verdict:", "  unknown_key: forbidden\n  verdict:", 1),
            encoding="utf-8",
        )
        before = fixture.target.read_bytes()
        with self.assertRaisesRegex(writer.GardenerVerdictError, "unknown"):
            fixture.stamp(fixture.request())
        self.assertEqual(fixture.target.read_bytes(), before)

        block = copy.deepcopy(fixture.pruning())
        block.pop("unknown_key")
        plants = []
        bad = copy.deepcopy(block)
        bad["confidence"] = True
        plants.append(bad)
        bad = copy.deepcopy(block)
        bad["confidence"] = float("nan")
        plants.append(bad)
        bad = copy.deepcopy(block)
        bad["judged_at"] = "2026-07-17"
        plants.append(bad)
        bad = copy.deepcopy(block)
        bad["normalized_body_hash_judged"] = "ABC"
        plants.append(bad)
        bad = copy.deepcopy(block)
        bad["evidence_locator"]["start_byte"] = True
        plants.append(bad)
        for bad_block in plants:
            with self.subTest(bad_block=bad_block):
                with self.assertRaises(writer.GardenerVerdictError):
                    writer._validate_pruning_block(bad_block)

    def test_hash_confidence_and_policy_constraints_fail_closed(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        base = fixture.request()
        variants = [
            replace(base, expected_body_sha256="ABC"),
            replace(base, expected_body_sha256="0" * 64),
            replace(base, expected_normalized_body_sha256="f" * 64),
            replace(base, confidence=True),
            replace(base, confidence=-0.1),
            replace(base, confidence=1.1),
            replace(base, confidence=float("inf")),
            replace(base, judge_policy_uid="99999999"),
            replace(base, judge_version="9.9.9"),
        ]
        for request in variants:
            with self.subTest(request=request):
                with self.assertRaises(writer.GardenerVerdictError):
                    fixture.stamp(request)
        text = fixture.policy.read_text(encoding="utf-8")
        text = text.replace("status: active", "status: archived", 1)
        text = text.replace("state: active", "state: archived", 1)
        fixture.policy.write_text(text, encoding="utf-8")
        self.assertEqual(fixture.freshen(POLICY_UID), 0)
        with self.assertRaisesRegex(writer.GardenerVerdictError, "fails closed"):
            fixture.stamp(base)

    def test_exact_retry_is_source_noop_and_repairs_projection(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        request = fixture.request()
        fixture.stamp(request)
        source = fixture.target.read_bytes()
        pruning = fixture.pruning()

        current_path = fixture.root / "vault" / index_surfaces.CURRENT_INDEX_NAME
        rows = list(index_surfaces.iter_jsonl(current_path))
        for row in rows:
            if row.get("uid") == TARGET_UID:
                row.pop("pruning", None)
        index_surfaces.write_jsonl_atomic(current_path, rows)
        with sqlite3.connect(fixture.root / "vault" / "00-index.sqlite") as conn:
            row = conn.execute(
                "SELECT fm_json FROM entries WHERE uid=?",
                (TARGET_UID,),
            ).fetchone()
            record = json.loads(row[0])
            record.pop("pruning", None)
            conn.execute(
                "UPDATE entries SET fm_json=? WHERE uid=?",
                (json.dumps(record), TARGET_UID),
            )
            conn.commit()

        result = fixture.stamp(request)

        self.assertEqual(result.operation, "exact-retry")
        self.assertFalse(result.source_changed)
        self.assertEqual(fixture.target.read_bytes(), source)
        jsonl, sqlite_record = fixture.projected()
        self.assertEqual(jsonl["pruning"], pruning)
        self.assertEqual(sqlite_record["pruning"], pruning)

    def test_nonidentical_same_t2_policy_and_version_always_refuses(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        base = fixture.request()
        fixture.stamp(base)
        second = fixture.request(evidence=SECOND_EVIDENCE)
        variants = [
            replace(base, verdict="abandoned"),
            replace(base, confidence=0.75),
            second,
        ]
        before = fixture.target.read_bytes()
        for request in variants:
            with self.subTest(request=request):
                with self.assertRaisesRegex(
                    writer.GardenerVerdictError,
                    "non-identical payload",
                ):
                    fixture.stamp(request)
                self.assertEqual(fixture.target.read_bytes(), before)

    def test_authorized_version_upgrade_accepts_identical_revalidated_evidence(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        fixture.stamp()
        fixture.set_policy_version("2.0.0")

        revalidated = fixture.request(version="2.0.0")
        result = fixture.stamp(revalidated)
        self.assertEqual(result.operation, "judge-version-replacement")
        self.assertEqual(fixture.pruning()["judge_version"], "2.0.0")
        self.assertEqual(fixture.pruning()["evidence_span"], FIRST_EVIDENCE)

    def test_different_policy_uid_refuses_pending_migration(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        fixture.stamp()
        fixture.switch_policy()
        request = fixture.request(
            evidence=SECOND_EVIDENCE,
            policy_uid=OTHER_POLICY_UID,
            version="9.0.0",
        )
        with self.assertRaisesRegex(writer.GardenerVerdictError, "migration"):
            fixture.stamp(request)

    def test_human_override_gates_and_current_override_suppression(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        fixture.stamp()
        source = fixture.target.read_bytes()

        with self.assertRaisesRegex(writer.GardenerVerdictError, "principal_class:human"):
            fixture.override(by=AGENT_UID, confirm=lambda _prompt: True)
        self.assertEqual(fixture.target.read_bytes(), source)

        seen_prompts = []
        with self.assertRaisesRegex(writer.GardenerVerdictError, "defaulted to NO"):
            fixture.override(confirm=lambda prompt: seen_prompts.append(prompt) or False)
        self.assertIn(TARGET_UID, seen_prompts[0])
        self.assertIn(normalized_body_sha256(fixture.target), seen_prompts[0])
        self.assertIn("superseded", seen_prompts[0])
        self.assertEqual(fixture.target.read_bytes(), source)

        with mock.patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(writer.GardenerVerdictError, "defaulted to NO"):
                fixture.override()

        result = fixture.override(confirm=lambda _prompt: True)
        self.assertEqual(result.operation, "human-keep-override")
        override = fixture.pruning()["override"]
        self.assertEqual(
            override,
            {
                "action": "keep",
                "by": HUMAN_UID,
                "at": "2026-07-17T10:00:00Z",
                "reason": "Human review says keep this body.",
            },
        )
        source_with_override = fixture.target.read_bytes()
        retry = fixture.stamp(fixture.request())
        self.assertEqual(retry.operation, "exact-retry")
        self.assertFalse(retry.source_changed)
        self.assertEqual(fixture.target.read_bytes(), source_with_override)
        self.assertEqual(fixture.pruning()["override"], override)

        fixture.set_policy_version("2.0.0")
        request = fixture.request(evidence=SECOND_EVIDENCE, version="2.0.0")
        with self.assertRaisesRegex(writer.GardenerVerdictError, "keep override"):
            fixture.stamp(request)
        self.assertEqual(fixture.pruning()["override"], override)

    def test_new_t2_replacement_does_not_inherit_override(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        fixture.stamp()
        fixture.override(confirm=lambda _prompt: True)
        raw = fixture.target.read_bytes()
        fixture.target.write_bytes(
            raw.replace(
                b"This body is superseded by the canonical replacement.",
                b"This body is abandoned after a real content revision.",
            )
        )
        new_evidence = "This body is abandoned after a real content revision."
        request = fixture.request(evidence=new_evidence, verdict="abandoned")

        result = fixture.stamp(request)

        self.assertEqual(result.operation, "new-body-replacement")
        self.assertNotIn("override", fixture.pruning())
        self.assertEqual(fixture.pruning()["evidence_span"], new_evidence)

    def test_compare_and_swap_and_atomic_failure_preserve_the_right_source(self):
        cas_fixture = IsolatedVault()
        self.addCleanup(cas_fixture.close)

        def concurrent_edit(path: Path):
            path.write_bytes(
                path.read_bytes().replace(
                    b"owner: test\n",
                    b"owner: test\nexternal_change: true\n",
                    1,
                )
            )

        with self.assertRaisesRegex(writer.GardenerVerdictError, "compare-and-swap"):
            cas_fixture.stamp(
                before_compare_and_swap=concurrent_edit,
            )
        self.assertIn(b"external_change: true", cas_fixture.target.read_bytes())
        self.assertIsNone(cas_fixture.pruning())

        atomic_fixture = IsolatedVault()
        self.addCleanup(atomic_fixture.close)
        before = atomic_fixture.target.read_bytes()

        def fail_atomic(_path: Path, _data: bytes):
            raise OSError("injected pre-replace failure")

        with self.assertRaisesRegex(writer.GardenerVerdictError, "atomic source write"):
            atomic_fixture.stamp(atomic_write=fail_atomic)
        self.assertEqual(atomic_fixture.target.read_bytes(), before)
        self.assertIsNone(atomic_fixture.pruning())

    def test_stamp_and_override_reresolve_index_identity_after_lock(self):
        for operation in ("stamp", "override"):
            with self.subTest(operation=operation):
                fixture = IsolatedVault()
                try:
                    if operation == "override":
                        fixture.stamp()
                    source_before = fixture.target.read_bytes()
                    alternate = fixture.root / "vault" / "files" / "aaaaaaaa.md"
                    alternate.write_bytes(
                        source_before.replace(
                            b"uid: 11111111",
                            b"uid: aaaaaaaa",
                            1,
                        )
                    )

                    lock_path = (
                        fixture.root
                        / ".tropo-studio"
                        / "locks"
                        / f"gardener-verdict-{TARGET_UID}.lock"
                    )
                    lock_path.parent.mkdir(parents=True, exist_ok=True)
                    entered_lock_boundary = threading.Event()
                    outcome = []
                    original_lock = writer._uid_lock

                    @contextlib.contextmanager
                    def observed_lock(*args, **kwargs):
                        entered_lock_boundary.set()
                        with original_lock(*args, **kwargs):
                            yield

                    def invoke():
                        try:
                            if operation == "stamp":
                                writer.stamp_verdict(
                                    fixture.request(),
                                    vault_root=fixture.root,
                                    now=lambda: FIXED_NOW,
                                )
                            else:
                                writer.add_keep_override(
                                    TARGET_UID,
                                    by=HUMAN_UID,
                                    reason="Race plant.",
                                    vault_root=fixture.root,
                                    confirm=lambda _prompt: True,
                                    now=lambda: FIXED_NOW,
                                )
                        except Exception as exc:  # captured for thread assertion
                            outcome.append(exc)
                        else:
                            outcome.append(None)

                    with lock_path.open("a+", encoding="utf-8") as blocker:
                        fcntl.flock(blocker.fileno(), fcntl.LOCK_EX)
                        with mock.patch.object(writer, "_uid_lock", observed_lock):
                            worker = threading.Thread(target=invoke)
                            worker.start()
                            self.assertTrue(entered_lock_boundary.wait(timeout=2))
                            fixture.rewrite_target_index_path(
                                "vault/files/aaaaaaaa.md"
                            )
                            fcntl.flock(blocker.fileno(), fcntl.LOCK_UN)
                            worker.join(timeout=5)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(len(outcome), 1)
                    self.assertIsInstance(outcome[0], writer.GardenerVerdictError)
                    self.assertIn("UID/path/frontmatter disagreement", str(outcome[0]))
                    self.assertEqual(fixture.target.read_bytes(), source_before)
                finally:
                    fixture.close()

    def test_override_refuses_uid_change_between_preresolution_and_locked_read(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        fixture.stamp()
        source_before_race = fixture.target.read_bytes()
        lock_path = (
            fixture.root
            / ".tropo-studio"
            / "locks"
            / f"gardener-verdict-{TARGET_UID}.lock"
        )
        pre_resolved = threading.Event()
        outcome = []
        original_resolve = writer._resolve_target
        resolve_calls = 0
        resolve_calls_lock = threading.Lock()

        def observed_resolve(*args, **kwargs):
            nonlocal resolve_calls
            result = original_resolve(*args, **kwargs)
            with resolve_calls_lock:
                resolve_calls += 1
                if resolve_calls == 1:
                    pre_resolved.set()
            return result

        def invoke_override():
            try:
                writer.add_keep_override(
                    TARGET_UID,
                    by=HUMAN_UID,
                    reason="Exact post-resolution UID race plant.",
                    vault_root=fixture.root,
                    confirm=lambda _prompt: True,
                    now=lambda: FIXED_NOW,
                )
            except Exception as exc:  # captured for thread assertion
                outcome.append(exc)
            else:
                outcome.append(None)

        with lock_path.open("a+", encoding="utf-8") as blocker:
            fcntl.flock(blocker.fileno(), fcntl.LOCK_EX)
            with mock.patch.object(writer, "_resolve_target", observed_resolve):
                worker = threading.Thread(target=invoke_override)
                worker.start()
                resolved_before_lock = pre_resolved.wait(timeout=2)
                if resolved_before_lock:
                    fixture.target.write_bytes(
                        source_before_race.replace(
                            b"uid: 11111111",
                            b"uid: aaaaaaaa",
                            1,
                        )
                    )
                fcntl.flock(blocker.fileno(), fcntl.LOCK_UN)
                worker.join(timeout=5)

        self.assertTrue(resolved_before_lock)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(outcome), 1)
        self.assertIsInstance(outcome[0], writer.GardenerVerdictError)
        self.assertIn("UID/path/frontmatter disagreement", str(outcome[0]))
        raced = writer._read_snapshot(fixture.target)
        self.assertEqual(
            writer._source_scalar(raced.frontmatter_text, "uid"),
            "aaaaaaaa",
        )
        self.assertNotIn("override", raced.frontmatter["pruning"])

    def test_incremental_uid_override_mismatch_refuses(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        fixture.target.write_bytes(
            fixture.target.read_bytes().replace(
                b"uid: 11111111",
                b"uid: aaaaaaaa",
                1,
            )
        )
        self.assertIsNone(
            rebuild.process_file(fixture.target, uid_override=TARGET_UID)
        )
        self.assertEqual(fixture.freshen(TARGET_UID), 1)
        rows = index_surfaces.load_index_records(
            fixture.root,
            include_archive=True,
        )
        target = [row for row in rows if row.get("uid") == TARGET_UID]
        self.assertEqual(len(target), 1)
        self.assertNotIn("pruning", target[0])

        tools = fixture.root / "vault" / "tools"
        tools.mkdir(parents=True, exist_ok=True)
        tools.joinpath("abcdef01.py").write_text(
            '"""\n---\n'
            'uid: abcdef02\n'
            'name: mismatched-tool\n'
            'type: tool\n'
            'status: active\n'
            'state: active\n'
            'owner: test\n'
            "created: '2026-07-17'\n"
            "modified: '2026-07-17'\n"
            'schema_version: 2\n'
            '---\n"""\n',
            encoding="utf-8",
        )
        self.assertEqual(fixture.freshen("abcdef01"), 1)

    def test_index_paths_reject_dotdot_and_parent_symlinks(self):
        dotdot = IsolatedVault()
        self.addCleanup(dotdot.close)
        dotdot.rewrite_target_index_path(
            f"vault/files/../files/{TARGET_UID}.md"
        )
        with self.assertRaisesRegex(writer.GardenerVerdictError, r"'\.\.'"):
            dotdot.stamp()

        linked = IsolatedVault()
        self.addCleanup(linked.close)
        alias = linked.root / "vault" / "agents"
        alias.symlink_to(linked.root / "vault" / "files", target_is_directory=True)
        linked.rewrite_target_index_path(f"vault/agents/{TARGET_UID}.md")
        with self.assertRaisesRegex(writer.GardenerVerdictError, "symlink component"):
            linked.stamp()

    def test_writer_refuses_markdown_outside_four_declared_homes(self):
        for relative in (
            f"vault/playbooks/{TARGET_UID}.md",
            f"vault/skills/{TARGET_UID}.md",
            f"notes/{TARGET_UID}.md",
        ):
            with self.subTest(relative=relative):
                fixture = IsolatedVault()
                try:
                    outside = fixture.root / relative
                    outside.parent.mkdir(parents=True, exist_ok=True)
                    outside.write_bytes(fixture.target.read_bytes())
                    fixture.rewrite_target_index_path(relative)
                    before = outside.read_bytes()
                    with self.assertRaisesRegex(
                        writer.GardenerVerdictError,
                        "outside the four declared pruning Markdown homes",
                    ):
                        fixture.stamp()
                    self.assertEqual(outside.read_bytes(), before)
                    self.assertIsNone(
                        writer._read_snapshot(outside).frontmatter.get("pruning")
                    )
                finally:
                    fixture.close()

    def test_non_markdown_pruning_never_projects(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        tools = fixture.root / "vault" / "tools"
        tools.mkdir(parents=True, exist_ok=True)
        python_uid = "a1a1a1a1"
        json_uid = "b2b2b2b2"
        (tools / f"{python_uid}.py").write_text(
            '"""\n'
            '---\n'
            f'uid: {python_uid}\n'
            'name: python-negative\n'
            'type: tool\n'
            'title: Python negative\n'
            'status: active\n'
            'state: active\n'
            'owner: test\n'
            "created: '2026-07-17'\n"
            "modified: '2026-07-17'\n"
            'schema_version: 2\n'
            'pruning:\n'
            '  verdict: finished\n'
            '---\n'
            '"""\n',
            encoding="utf-8",
        )
        (tools / f"{json_uid}.json").write_text(
            json.dumps(
                {
                    "tropo_metadata": {
                        "uid": json_uid,
                        "name": "json-negative",
                        "type": "tool",
                        "title": "JSON negative",
                        "status": "active",
                        "state": "active",
                        "owner": "test",
                        "created": "2026-07-17",
                        "modified": "2026-07-17",
                        "schema_version": 2,
                        "pruning": {"verdict": "finished"},
                    }
                }
            ),
            encoding="utf-8",
        )

        # Both new tool sources are present before projection, so this is a
        # global two-source delta and must use the full-apply cure.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(rebuild.rebuild_index(fixture.root, True), 0)
        records = {
            row["uid"]: row
            for row in index_surfaces.load_index_records(
                fixture.root,
                include_archive=True,
            )
        }
        with sqlite3.connect(fixture.root / "vault" / "00-index.sqlite") as conn:
            sqlite_rows = {
                uid: json.loads(fm_json)
                for uid, fm_json in conn.execute(
                    "SELECT uid, fm_json FROM entries WHERE uid IN (?, ?)",
                    (python_uid, json_uid),
                )
            }
        for uid in (python_uid, json_uid):
            self.assertNotIn("pruning", records[uid])
            self.assertNotIn("pruning", sqlite_rows[uid])

    def test_friendly_path_tool_contract_validates_from_frontmatter_uid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tools = root / "vault" / "tools"
            tools.mkdir(parents=True)
            source = TOOLS / "tropo-gardener-verdict.py"
            friendly = tools / "tropo-gardener-verdict.py"
            friendly.write_bytes(source.read_bytes())

            findings, checked, defects = tool_validators.run_all_tool_checks(root)

            self.assertEqual(checked, 1)
            self.assertEqual(defects, 0, "\n".join(findings))
            self.assertEqual(findings, [])
            fm_text, body = tool_validators._parse_frontmatter_from_tool_file(
                friendly
            )
            metadata = writer.yaml.safe_load(fm_text)
            self.assertEqual(metadata["uid"], "7bf6187d")
            self.assertEqual(metadata["input"]["type"], "object")
            self.assertEqual(len(metadata["input"]["allOf"]), 2)
            for expected_scope in (
                ".tropo-studio/dirty-counter.json",
                ".tropo-studio/locks/index-write.lock",
            ):
                self.assertIn(expected_scope, metadata["writes_scope"])
            for heading in (
                "## Intent",
                "## Invocation Protocol",
                "## Input / Output",
                "## Governance",
                "## Verification",
                "## Failure Modes",
            ):
                self.assertIn(heading, body)
            shipped_text = friendly.read_text(encoding="utf-8")
            for private_uid in (
                "5d3ab142",
                "a286c210",
                "132fb547",
                "ee814120",
            ):
                self.assertNotIn(private_uid, shipped_text)
            self.assertIn("tropo-core.capsule.md", shipped_text)

    def test_freshen_failure_is_nonzero_equivalent_and_never_false_success(self):
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        with self.assertRaisesRegex(writer.GardenerVerdictError, "index freshen failed"):
            fixture.stamp(freshen=lambda _uid, _root: 7)
        self.assertIsNotNone(fixture.pruning())
        jsonl, sqlite_record = fixture.projected()
        self.assertNotIn("pruning", jsonl)
        self.assertNotIn("pruning", sqlite_record)

    def test_all_eligible_governed_markdown_homes_freshen(self):
        for home in (
            "vault/files",
            "vault/agents",
            "agents",
            "vault/capsules",
        ):
            with self.subTest(home=home):
                fixture = IsolatedVault(home=home)
                try:
                    result = fixture.stamp()
                    self.assertEqual(result.operation, "stamp")
                    jsonl, sqlite_record = fixture.projected()
                    self.assertEqual(jsonl["pruning"], fixture.pruning())
                    self.assertEqual(sqlite_record["pruning"], fixture.pruning())
                finally:
                    fixture.close()

    def test_cli_exposes_no_noninteractive_override_bypass(self):
        parser = writer.build_parser()
        help_text = parser.format_help()
        self.assertNotIn("--yes", help_text)
        self.assertNotIn("--force", help_text)
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                parser.parse_args(
                    [
                        "override",
                        TARGET_UID,
                        "--action",
                        "keep",
                        "--by",
                        HUMAN_UID,
                        "--reason",
                        "keep",
                        "--yes",
                    ]
                )


if __name__ == "__main__":
    unittest.main()
