#!/usr/bin/env python3
"""Focused isolated plants for the shared core-v1.7 pruning validator."""
from __future__ import annotations

import copy
import gc
import importlib.util
import math
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


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


writer = _load("pruning_validator_writer", TOOLS / "tropo-gardener-verdict.py")
full_validator = _load("pruning_validator_full", TOOLS / "tropo-validate.py")
check_one = _load("pruning_validator_check_one", TOOLS / "tropo-check-one.py")

from lib import index_surfaces, pruning_contract  # noqa: E402
from lib.normalized_body_hash import (  # noqa: E402
    normalized_body_sha256,
    raw_body_sha256,
)
from vault.tools.tests.test_gardener_verdict import (  # noqa: E402
    AGENT_UID,
    FIRST_EVIDENCE,
    HUMAN_UID,
    IsolatedVault,
    POLICY_UID,
    TARGET_UID,
)


class SharedPruningContractTests(unittest.TestCase):
    def _fixture(self, *, stamped: bool = True) -> IsolatedVault:
        fixture = IsolatedVault()
        self.addCleanup(fixture.close)
        if stamped:
            fixture.stamp()
        return fixture

    @staticmethod
    def _records(fixture: IsolatedVault) -> list[dict]:
        return index_surfaces.load_index_records(
            fixture.root,
            include_archive=False,
        )

    def _result(
        self,
        fixture: IsolatedVault,
        *,
        records: list[dict] | None = None,
    ):
        return pruning_contract.check_pruning_path(
            fixture.target,
            fixture.root,
            records if records is not None else self._records(fixture),
            expected_uid=TARGET_UID,
        )

    def _pure(
        self,
        fixture: IsolatedVault,
        block: object,
        *,
        body: bytes | None = None,
        t1: str | None = None,
        t2: str | None = None,
        records: list[dict] | None = None,
    ):
        snapshot = pruning_contract.read_markdown_snapshot(fixture.target)
        return pruning_contract.evaluate_pruning_contract(
            uid=TARGET_UID,
            path=f"vault/files/{TARGET_UID}.md",
            block=block,
            body=snapshot.body if body is None else body,
            current_t1=t1 or raw_body_sha256(fixture.target),
            current_t2=t2 or normalized_body_sha256(fixture.target),
            current_records=records if records is not None else self._records(fixture),
        )

    @staticmethod
    def _replace_block(fixture: IsolatedVault, block: dict) -> None:
        snapshot = pruning_contract.read_markdown_snapshot(fixture.target)
        frontmatter = copy.deepcopy(snapshot.frontmatter)
        frontmatter["pruning"] = block
        rendered = yaml.safe_dump(
            frontmatter,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        fixture.target.write_bytes(
            b"---\n"
            + rendered.encode("utf-8")
            + b"---\n"
            + snapshot.body
        )

    @staticmethod
    def _tree_bytes(root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_writer_full_validator_and_check_one_share_one_contract_source(self):
        shared_path = Path(pruning_contract.__file__).resolve()
        self.assertEqual(
            Path(full_validator.pruning_contract.__file__).resolve(),
            shared_path,
        )
        self.assertEqual(
            Path(check_one.pruning_contract.__file__).resolve(),
            shared_path,
        )
        self.assertIs(
            writer._validate_pruning_block,
            pruning_contract.validate_pruning_block,
        )
        self.assertIs(
            writer._validate_confidence,
            pruning_contract.validate_confidence,
        )

    def test_absent_block_is_silent_pass(self):
        fixture = self._fixture(stamped=False)
        result = self._result(fixture)
        self.assertEqual(result.severity, "PASS")
        self.assertFalse(result.has_pruning)
        self.assertEqual(result.findings, ())

        findings, checked, defects = full_validator.check_pruning_contract(
            fixture.root
        )
        self.assertEqual((findings, checked, defects), ([], 0, 0))
        targeted = check_one.run_pruning_check(TARGET_UID, fixture.root)
        self.assertIsNotNone(targeted)
        self.assertFalse(targeted.has_pruning)
        self.assertEqual(targeted.formatted_findings(), [])

        fixture.target.write_bytes(
            fixture.target.read_bytes()
            + b"\npruning:\n  this-is-body-prose: true\n"
        )
        body_prose = self._result(fixture)
        self.assertEqual(body_prose.severity, "PASS")
        self.assertFalse(body_prose.has_pruning)

    def test_quoted_spaced_and_malformed_pruning_keys_are_semantically_detected(self):
        for rendered_key in (b'"pruning" :', b"pruning :"):
            with self.subTest(rendered_key=rendered_key):
                fixture = self._fixture()
                fixture.target.write_bytes(
                    fixture.target.read_bytes().replace(
                        b"\npruning:\n",
                        b"\n" + rendered_key + b"\n",
                        1,
                    )
                )
                direct = self._result(fixture)
                full_findings, checked, defects = (
                    full_validator.check_pruning_contract(fixture.root)
                )
                targeted = check_one.run_pruning_check(TARGET_UID, fixture.root)
                self.assertEqual(direct.severity, "PASS")
                self.assertEqual((full_findings, checked, defects), ([], 1, 0))
                self.assertEqual(targeted.severity, "PASS")

        malformed = self._fixture()
        malformed.target.write_bytes(
            malformed.target.read_bytes()
            .replace(b"\npruning:\n", b'\n"pruning" :\n', 1)
            .replace(b"  evidence_locator:\n", b"  evidence_locator: [\n", 1)
        )
        direct = self._result(malformed)
        full_findings, checked, defects = full_validator.check_pruning_contract(
            malformed.root
        )
        targeted = check_one.run_pruning_check(TARGET_UID, malformed.root)
        self.assertEqual(direct.severity, "FAIL")
        self.assertEqual(direct.findings[0].code, "PRUNING_SOURCE_SHAPE")
        self.assertEqual(full_findings, targeted.formatted_findings())
        self.assertEqual((checked, defects), (1, 1))

    def test_arbitrary_yaml_values_and_unicode_fail_totally_in_both_adapters(self):
        plants = ("huge-confidence", "list-verdict", "mixed-keys", "lone-surrogate")
        for plant in plants:
            with self.subTest(plant=plant):
                fixture = IsolatedVault()
                try:
                    fixture.stamp()
                    block = copy.deepcopy(fixture.pruning())
                    if plant == "huge-confidence":
                        block["confidence"] = 10 ** 400
                        self._replace_block(fixture, block)
                    elif plant == "list-verdict":
                        block["verdict"] = ["superseded"]
                        self._replace_block(fixture, block)
                    elif plant == "mixed-keys":
                        block[7] = "non-string key"
                        self._replace_block(fixture, block)
                    else:
                        fixture.target.write_bytes(
                            fixture.target.read_bytes().replace(
                                (
                                    b"evidence_span: "
                                    + FIRST_EVIDENCE.encode("utf-8")
                                ),
                                b'evidence_span: "\\uD800"',
                                1,
                            )
                        )

                    direct = self._result(fixture)
                    full_findings, checked, defects = (
                        full_validator.check_pruning_contract(fixture.root)
                    )
                    targeted = check_one.run_pruning_check(
                        TARGET_UID,
                        fixture.root,
                    )
                    self.assertEqual(direct.severity, "FAIL")
                    self.assertEqual(full_findings, targeted.formatted_findings())
                    self.assertEqual((checked, defects), (1, 1))
                    self.assertTrue(
                        all(line.startswith("[FAIL]") for line in full_findings)
                    )
                    if plant == "lone-surrogate":
                        cli = subprocess.run(
                            [
                                sys.executable,
                                str(TOOLS / "tropo-check-one.py"),
                                TARGET_UID,
                                "--vault-path",
                                str(fixture.root),
                            ],
                            capture_output=True,
                            text=True,
                            cwd=ROOT,
                        )
                        self.assertEqual(cli.returncode, 1, cli.stderr)
                        self.assertIn("valid strict UTF-8", cli.stdout)
                finally:
                    fixture.close()

    def test_fully_current_block_passes(self):
        fixture = self._fixture()
        result = self._result(fixture)
        self.assertEqual(result.severity, "PASS")
        self.assertEqual(result.declared_verdict, "superseded")
        self.assertEqual(result.effective_verdict, "superseded")
        self.assertTrue(result.t1_current)
        self.assertTrue(result.t2_current)
        self.assertTrue(result.policy_current)

        findings, checked, defects = full_validator.check_pruning_contract(
            fixture.root
        )
        self.assertEqual((findings, checked, defects), ([], 1, 0))

    def test_full_scan_covers_exactly_the_four_declared_markdown_homes(self):
        for home in (
            "vault/files",
            "vault/agents",
            "agents",
            "vault/capsules",
        ):
            with self.subTest(home=home):
                fixture = IsolatedVault(home=home)
                try:
                    fixture.stamp()
                    findings, checked, defects = (
                        full_validator.check_pruning_contract(fixture.root)
                    )
                    self.assertEqual((findings, checked, defects), ([], 1, 0))
                finally:
                    fixture.close()

    def test_full_scan_ignores_playbooks_python_and_json(self):
        fixture = self._fixture(stamped=False)
        markdown = (
            b"---\nuid: abcdef01\ntype: document\npruning:\n"
            b"  malformed: true\n---\nBody.\n"
        )
        playbook = fixture.root / "vault" / "playbooks" / "abcdef01.md"
        playbook.parent.mkdir(parents=True, exist_ok=True)
        playbook.write_bytes(markdown)
        tools = fixture.root / "vault" / "tools"
        tools.mkdir(parents=True, exist_ok=True)
        tools.joinpath("abcdef02.py").write_text(
            '"""\n---\nuid: abcdef02\ntype: tool\n'
            'pruning:\n  malformed: true\n---\n"""\n',
            encoding="utf-8",
        )
        tools.joinpath("abcdef03.json").write_text(
            '{"tropo_metadata":{"uid":"abcdef03","type":"tool",'
            '"pruning":{"malformed":true}}}',
            encoding="utf-8",
        )

        findings, checked, defects = full_validator.check_pruning_contract(
            fixture.root
        )
        self.assertEqual((findings, checked, defects), ([], 0, 0))
        ignored = pruning_contract.check_pruning_path(
            playbook,
            fixture.root,
            self._records(fixture),
            expected_uid="abcdef01",
        )
        self.assertFalse(ignored.applicable)

    def test_targeted_index_check_ignores_non_pruning_tool_home(self):
        fixture = self._fixture(stamped=False)
        tool = fixture.root / "vault" / "tools" / "abcdef02.py"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text(
            '"""\n---\nuid: abcdef02\ntype: tool\n---\n"""\n',
            encoding="utf-8",
        )
        row = {
            "uid": "abcdef02",
            "type": "tool",
            "path": "vault/tools/abcdef02.py",
        }

        result = pruning_contract._indexed_row_check(
            "abcdef02",
            row,
            fixture.root,
            [*self._records(fixture), row],
        )

        self.assertFalse(result.applicable)
        self.assertFalse(result.has_pruning)
        self.assertEqual(result.formatted_findings(), [])

    def test_dotdot_symlink_and_escape_aliases_fail_once_with_adapter_parity(self):
        dotdot = self._fixture()
        dotdot.rewrite_target_index_path(
            f"vault/files/../files/{TARGET_UID}.md"
        )
        full_findings, checked, defects = full_validator.check_pruning_contract(
            dotdot.root
        )
        targeted = check_one.run_pruning_check(TARGET_UID, dotdot.root)
        self.assertEqual(full_findings, targeted.formatted_findings())
        self.assertEqual((checked, defects), (1, 1))
        self.assertIn("'..'", full_findings[0])

        linked = self._fixture()
        alias = linked.root / "vault" / "agents"
        alias.symlink_to(
            linked.root / "vault" / "files",
            target_is_directory=True,
        )
        linked.rewrite_target_index_path(f"vault/agents/{TARGET_UID}.md")
        full_findings, checked, defects = full_validator.check_pruning_contract(
            linked.root
        )
        targeted = check_one.run_pruning_check(TARGET_UID, linked.root)
        self.assertEqual(full_findings, targeted.formatted_findings())
        self.assertEqual((checked, defects), (1, 1))
        self.assertIn("symlink component", full_findings[0])

        escaped = self._fixture()
        escaped.rewrite_target_index_path(str(escaped.target))
        full_findings, checked, defects = full_validator.check_pruning_contract(
            escaped.root
        )
        targeted = check_one.run_pruning_check(TARGET_UID, escaped.root)
        self.assertEqual(full_findings, targeted.formatted_findings())
        self.assertEqual((checked, defects), (1, 1))
        self.assertIn("Studio-relative", full_findings[0])

    def test_full_scan_ignores_unindexed_symlink_alias_and_prefers_canonical_path(self):
        fixture = self._fixture()
        alias = fixture.root / "vault" / "agents"
        alias.symlink_to(
            fixture.root / "vault" / "files",
            target_is_directory=True,
        )

        full_findings, checked, defects = full_validator.check_pruning_contract(
            fixture.root
        )
        targeted = check_one.run_pruning_check(TARGET_UID, fixture.root)

        self.assertEqual((full_findings, checked, defects), ([], 1, 0))
        self.assertEqual(targeted.severity, "PASS")
        self.assertEqual(
            targeted.path,
            f"vault/files/{TARGET_UID}.md",
        )

    def test_check_pruning_path_fails_closed_when_root_reached_via_symlink(self):
        # Argus A141's repro (0e64549a): a vault checked out or reached through
        # a symlinked ancestor (e.g. a symlinked TMPDIR) made check_pruning_path
        # resolve `vault_root` but not `path`, so `path.relative_to(vault_root)`
        # raised ValueError even for a path genuinely inside the vault. The old
        # except-branch fallback kept the raw unresolved path, which never
        # matches `is_declared_pruning_home`, so the function returned an early
        # not-applicable result — severity PASS, zero findings — for real,
        # in-scope pruning-governed files. Reproduce the symlink divergence
        # directly (not via $TMPDIR, so this is deterministic on any machine)
        # and prove a genuinely malformed block still fails, and a genuinely
        # valid block still evaluates for real, when reached via the alias.
        # .resolve() on the REAL side only. IsolatedVault resolves its own root
        # (needed so rebuild_index's destination allowlist matches), so an
        # unresolved real_base makes the relative_to() below raise. The ALIAS is
        # deliberately left unresolved — that divergence is the thing under
        # test, and the two assertions below still pin it.
        # (metis-g103 2026-08-06)
        real_base = Path(tempfile.mkdtemp(prefix="pruning-symlink-real-")).resolve()
        self.addCleanup(shutil.rmtree, real_base, ignore_errors=True)
        alias_base = real_base.parent / f"{real_base.name}-alias"
        alias_base.symlink_to(real_base, target_is_directory=True)
        self.addCleanup(alias_base.unlink)

        original_tempdir = tempfile.tempdir
        tempfile.tempdir = str(real_base)
        try:
            malformed = IsolatedVault()
        finally:
            tempfile.tempdir = original_tempdir
        self.addCleanup(malformed.close)
        malformed.stamp()
        malformed.target.write_bytes(
            malformed.target.read_bytes()
            .replace(b"\npruning:\n", b'\n"pruning" :\n', 1)
            .replace(b"  evidence_locator:\n", b"  evidence_locator: [\n", 1)
        )
        aliased_root = alias_base / malformed.root.relative_to(real_base)
        aliased_target = aliased_root / malformed.target.relative_to(malformed.root)

        # Sanity: the alias really is a distinct, unresolved path to the same
        # file — otherwise this test would not exercise the divergence at all.
        self.assertNotEqual(aliased_root, aliased_root.resolve())
        self.assertEqual(aliased_root.resolve(), malformed.root.resolve())

        via_alias = pruning_contract.check_pruning_path(
            aliased_target,
            aliased_root,
            self._records(malformed),
            expected_uid=TARGET_UID,
        )
        direct = self._result(malformed)
        self.assertEqual(direct.severity, "FAIL")
        self.assertEqual(via_alias.severity, "FAIL")
        self.assertTrue(via_alias.applicable)
        self.assertEqual(via_alias.findings[0].code, direct.findings[0].code)

        original_tempdir = tempfile.tempdir
        tempfile.tempdir = str(real_base)
        try:
            valid = IsolatedVault()
        finally:
            tempfile.tempdir = original_tempdir
        self.addCleanup(valid.close)
        valid.stamp()
        valid_aliased_root = alias_base / valid.root.relative_to(real_base)
        valid_aliased_target = (
            valid_aliased_root / valid.target.relative_to(valid.root)
        )
        via_alias_valid = pruning_contract.check_pruning_path(
            valid_aliased_target,
            valid_aliased_root,
            self._records(valid),
            expected_uid=TARGET_UID,
        )
        self.assertTrue(via_alias_valid.applicable)
        self.assertTrue(via_alias_valid.has_pruning)
        self.assertEqual(via_alias_valid.severity, "PASS")
        self.assertEqual(via_alias_valid.declared_verdict, "superseded")
        self.assertEqual(via_alias_valid.effective_verdict, "superseded")

    def test_archived_target_uses_union_but_current_policy_authority(self):
        fixture = self._fixture()
        fixture.target.write_bytes(
            fixture.target.read_bytes().replace(
                b"state: active",
                b"state: archived",
                1,
            )
        )
        self.assertEqual(fixture.freshen(TARGET_UID), 0)

        current = index_surfaces.load_index_records(
            fixture.root,
            include_archive=False,
        )
        union = index_surfaces.load_index_records(
            fixture.root,
            include_archive=True,
        )
        self.assertFalse(any(row.get("uid") == TARGET_UID for row in current))
        self.assertTrue(any(row.get("uid") == TARGET_UID for row in union))
        self.assertTrue(any(row.get("uid") == POLICY_UID for row in current))

        full_findings, checked, defects = full_validator.check_pruning_contract(
            fixture.root
        )
        targeted = check_one.run_pruning_check(TARGET_UID, fixture.root)
        self.assertEqual((full_findings, checked, defects), ([], 1, 0))
        self.assertEqual(targeted.severity, "PASS")
        self.assertTrue(targeted.policy_current)

    def test_archived_human_does_not_authorize_override(self):
        fixture = self._fixture()
        fixture.override(confirm=lambda _prompt: True)
        fixture.human.write_bytes(
            fixture.human.read_bytes().replace(
                b"state: active",
                b"state: archived",
                1,
            )
        )
        self.assertEqual(fixture.freshen(HUMAN_UID), 0)

        full_findings, checked, defects = full_validator.check_pruning_contract(
            fixture.root
        )
        targeted = check_one.run_pruning_check(TARGET_UID, fixture.root)
        self.assertEqual(full_findings, targeted.formatted_findings())
        self.assertEqual((checked, defects), (1, 1))
        self.assertIn("PRUNING_OVERRIDE_AUTHORITY", full_findings[0])

    def test_missing_indexed_source_fails_full_targeted_and_cli(self):
        fixture = self._fixture()
        fixture.target.unlink()

        full_findings, checked, defects = full_validator.check_pruning_contract(
            fixture.root
        )
        targeted = check_one.run_pruning_check(TARGET_UID, fixture.root)
        self.assertEqual(full_findings, targeted.formatted_findings())
        self.assertEqual((checked, defects), (1, 1))
        self.assertIn("indexed source is missing", full_findings[0])
        self.assertIn("tropo-rebuild-index.py", full_findings[0])

        cli = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "tropo-check-one.py"),
                TARGET_UID,
                "--vault-path",
                str(fixture.root),
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(cli.returncode, 1, cli.stderr)
        self.assertIn("PRUNING_INDEX", cli.stdout)
        self.assertIn("→ FAIL", cli.stdout)

    def test_missing_or_corrupt_current_index_has_consistent_repair_failure(self):
        for state in ("missing", "corrupt"):
            with self.subTest(state=state):
                fixture = IsolatedVault()
                try:
                    fixture.stamp()
                    current = fixture.root / "vault" / "00-index.jsonl"
                    if state == "missing":
                        current.unlink()
                    else:
                        current.write_text("{not-json}\n", encoding="utf-8")

                    full_findings, checked, defects = (
                        full_validator.check_pruning_contract(fixture.root)
                    )
                    targeted = check_one.run_pruning_check(
                        TARGET_UID,
                        fixture.root,
                    )
                    self.assertEqual(
                        full_findings,
                        targeted.formatted_findings(),
                    )
                    self.assertEqual((checked, defects), (1, 1))
                    self.assertIn("current index validation failed", full_findings[0])
                    self.assertIn(
                        "python3 vault/tools/tropo-rebuild-index.py",
                        full_findings[0],
                    )

                    cli = subprocess.run(
                        [
                            sys.executable,
                            str(TOOLS / "tropo-check-one.py"),
                            TARGET_UID,
                            "--vault-path",
                            str(fixture.root),
                        ],
                        capture_output=True,
                        text=True,
                        cwd=ROOT,
                    )
                    self.assertEqual(cli.returncode, 1, cli.stderr)
                    self.assertIn("PRUNING_INDEX", cli.stdout)
                finally:
                    fixture.close()

    def test_missing_source_and_broken_current_index_emit_one_global_failure(self):
        for state in ("missing", "corrupt"):
            with self.subTest(state=state):
                fixture = IsolatedVault()
                try:
                    fixture.stamp()
                    fixture.target.unlink()
                    current = fixture.root / "vault" / "00-index.jsonl"
                    if state == "missing":
                        current.unlink()
                    else:
                        current.write_text("{broken-json}\n", encoding="utf-8")

                    full_findings, checked, defects = (
                        full_validator.check_pruning_contract(fixture.root)
                    )
                    targeted = check_one.run_pruning_check(
                        TARGET_UID,
                        fixture.root,
                    )
                    self.assertEqual(
                        full_findings,
                        targeted.formatted_findings(),
                    )
                    self.assertEqual((checked, defects), (1, 1))
                    self.assertEqual(len(full_findings), 1)
                    self.assertIn("[FAIL] <global> vault/00-index.jsonl", full_findings[0])
                    self.assertIn("PRUNING_INDEX", full_findings[0])
                    self.assertIn("tropo-rebuild-index.py", full_findings[0])
                finally:
                    fixture.close()

    def test_closed_shape_type_range_hash_time_and_confidence_failures(self):
        fixture = self._fixture()
        valid = fixture.pruning()
        plants: list[tuple[str, dict]] = []

        def plant(name: str, mutate):
            block = copy.deepcopy(valid)
            mutate(block)
            plants.append((name, block))

        plant("missing", lambda b: b.pop("verdict"))
        plant("unknown", lambda b: b.__setitem__("unknown", True))
        plant("verdict", lambda b: b.__setitem__("verdict", "done"))
        plant("evidence-type", lambda b: b.__setitem__("evidence_span", 7))
        plant("locator-shape", lambda b: b["evidence_locator"].__setitem__("extra", 1))
        plant("range-bool", lambda b: b["evidence_locator"].__setitem__("start_byte", True))
        plant("range-negative", lambda b: b["evidence_locator"].__setitem__("start_byte", -1))
        plant(
            "range-order",
            lambda b: b["evidence_locator"].__setitem__(
                "end_byte", b["evidence_locator"]["start_byte"]
            ),
        )
        plant("t1-hash", lambda b: b["evidence_locator"].__setitem__("body_sha256", "ABC"))
        plant("policy-uid", lambda b: b.__setitem__("judge_policy_uid", "bad"))
        plant("version-empty", lambda b: b.__setitem__("judge_version", ""))
        plant("time-naive", lambda b: b.__setitem__("judged_at", "2026-07-17"))
        plant("time-invalid", lambda b: b.__setitem__("judged_at", "not-a-time"))
        plant("confidence-bool", lambda b: b.__setitem__("confidence", True))
        plant("confidence-nan", lambda b: b.__setitem__("confidence", math.nan))
        plant("confidence-range", lambda b: b.__setitem__("confidence", 1.1))
        plant("t2-hash", lambda b: b.__setitem__("normalized_body_hash_judged", "ABC"))

        with_override = copy.deepcopy(valid)
        with_override["override"] = {
            "action": "keep",
            "by": HUMAN_UID,
            "at": "2026-07-17T10:00:00Z",
            "reason": "Keep.",
        }
        for name, mutation in (
            ("override-extra", lambda b: b["override"].__setitem__("extra", True)),
            ("override-action", lambda b: b["override"].__setitem__("action", "drop")),
            ("override-by", lambda b: b["override"].__setitem__("by", "bad")),
            ("override-time", lambda b: b["override"].__setitem__("at", "2026-07-17")),
            ("override-reason", lambda b: b["override"].__setitem__("reason", "")),
        ):
            block = copy.deepcopy(with_override)
            mutation(block)
            plants.append((name, block))

        for name, block in plants:
            with self.subTest(name=name):
                result = self._pure(fixture, block)
                self.assertEqual(result.severity, "FAIL")
                self.assertEqual(result.findings[0].code, "PRUNING_SHAPE")

    def test_evidence_failures_cover_empty_bounds_mismatch_nav_and_invalid_utf8(self):
        fixture = self._fixture()
        valid = fixture.pruning()

        for name, mutation in (
            ("missing", lambda b: b.pop("evidence_span")),
            ("empty", lambda b: b.__setitem__("evidence_span", "")),
            (
                "out-of-range",
                lambda b: b["evidence_locator"].__setitem__(
                    "end_byte", len(fixture.body_bytes()) + 1
                ),
            ),
            ("mismatch", lambda b: b.__setitem__("evidence_span", "Different evidence.")),
        ):
            block = copy.deepcopy(valid)
            mutation(block)
            with self.subTest(name=name):
                result = self._pure(fixture, block)
                self.assertEqual(result.severity, "FAIL")

        nav_body = (
            b"<!-- nav-block:start -->\nGenerated evidence.\n"
            b"<!-- nav-block:end -->\n"
        )
        nav_start = nav_body.index(b"Generated evidence.")
        nav_block = copy.deepcopy(valid)
        nav_block["evidence_span"] = "Generated evidence."
        nav_block["evidence_locator"] = {
            "body_sha256": "1" * 64,
            "start_byte": nav_start,
            "end_byte": nav_start + len(b"Generated evidence."),
        }
        nav_block["normalized_body_hash_judged"] = "2" * 64
        nav_result = self._pure(
            fixture,
            nav_block,
            body=nav_body,
            t1="1" * 64,
            t2="2" * 64,
        )
        self.assertEqual(nav_result.severity, "FAIL")
        self.assertIn("nav-block", nav_result.findings[-1].message)

        invalid_body = b"Prefix\n\xff\n"
        invalid_block = copy.deepcopy(valid)
        invalid_block["evidence_span"] = "\ufffd"
        invalid_block["evidence_locator"] = {
            "body_sha256": "3" * 64,
            "start_byte": 7,
            "end_byte": 8,
        }
        invalid_block["normalized_body_hash_judged"] = "4" * 64
        invalid_result = self._pure(
            fixture,
            invalid_block,
            body=invalid_body,
            t1="3" * 64,
            t2="4" * 64,
        )
        self.assertEqual(invalid_result.severity, "FAIL")
        self.assertIn("invalid UTF-8", invalid_result.findings[-1].message)

    def test_stale_t2_warns_and_excludes_verdict(self):
        fixture = self._fixture()
        block = copy.deepcopy(fixture.pruning())
        result = self._pure(fixture, block, t2="f" * 64)
        self.assertEqual(result.severity, "WARN")
        self.assertIn("PRUNING_T2_STALE", [f.code for f in result.findings])
        self.assertIsNone(result.effective_verdict)

    def test_missing_stale_and_ambiguous_policy_warn(self):
        fixture = self._fixture()
        valid = fixture.pruning()
        base_records = self._records(fixture)
        without_policy = [
            row for row in base_records if row.get("uid") != POLICY_UID
        ]
        stale_policy = copy.deepcopy(base_records)
        for row in stale_policy:
            if row.get("uid") == POLICY_UID:
                row["version"] = "2.0.0"
        ambiguous = copy.deepcopy(base_records)
        second = next(
            copy.deepcopy(row)
            for row in base_records
            if row.get("uid") == POLICY_UID
        )
        second["uid"] = "abcdef12"
        ambiguous.append(second)

        for name, records in (
            ("missing", without_policy),
            ("stale", stale_policy),
            ("ambiguous", ambiguous),
        ):
            with self.subTest(name=name):
                result = self._pure(fixture, valid, records=records)
                self.assertEqual(result.severity, "WARN")
                self.assertIn(
                    "PRUNING_POLICY_STALE",
                    [finding.code for finding in result.findings],
                )
                self.assertIsNone(result.effective_verdict)

    def test_stale_t1_unique_evidence_warns_with_restamp_cure(self):
        fixture = self._fixture()
        snapshot = pruning_contract.read_markdown_snapshot(fixture.target)
        changed_body = snapshot.body.replace(
            FIRST_EVIDENCE.encode() + b"\n",
            FIRST_EVIDENCE.encode() + b"   \n",
            1,
        )
        fixture.target.write_bytes(
            snapshot.raw[:-len(snapshot.body)] + changed_body
        )
        result = self._result(fixture)
        self.assertEqual(result.severity, "WARN")
        self.assertTrue(result.t2_current)
        self.assertFalse(result.t1_current)
        self.assertEqual(result.effective_verdict, "superseded")
        finding = next(
            finding
            for finding in result.findings
            if finding.code == "PRUNING_T1_STALE"
        )
        self.assertIn("re-stamp", finding.cure)

    def test_stale_t1_zero_or_multiple_evidence_fails(self):
        fixture = self._fixture()
        block = copy.deepcopy(fixture.pruning())
        old_t2 = block["normalized_body_hash_judged"]
        for name, body in (
            ("zero", b"No matching evidence.\n"),
            (
                "multiple",
                (
                    FIRST_EVIDENCE.encode()
                    + b"\n"
                    + FIRST_EVIDENCE.encode()
                    + b"\n"
                ),
            ),
        ):
            with self.subTest(name=name):
                result = self._pure(
                    fixture,
                    block,
                    body=body,
                    t1="0" * 64,
                    t2=old_t2,
                )
                self.assertEqual(result.severity, "FAIL")
                finding = next(
                    finding
                    for finding in result.findings
                    if finding.code == "PRUNING_STALE_EVIDENCE"
                )
                expected_count = 0 if name == "zero" else 2
                self.assertIn(f"resolves {expected_count} times", finding.message)

    def test_invalid_human_authority_fails(self):
        fixture = self._fixture()
        block = copy.deepcopy(fixture.pruning())
        block["override"] = {
            "action": "keep",
            "by": AGENT_UID,
            "at": "2026-07-17T10:00:00Z",
            "reason": "Not a human.",
        }
        result = self._pure(fixture, block)
        self.assertEqual(result.severity, "FAIL")
        self.assertIn(
            "PRUNING_OVERRIDE_AUTHORITY",
            [finding.code for finding in result.findings],
        )
        self.assertIsNone(result.effective_verdict)

    def test_current_authorized_keep_override_is_effective_keep(self):
        fixture = self._fixture()
        fixture.override(confirm=lambda _prompt: True)
        result = self._result(fixture)
        self.assertEqual(result.severity, "PASS")
        self.assertTrue(result.override_current)
        self.assertEqual(result.declared_verdict, "superseded")
        self.assertEqual(result.effective_verdict, "keep")

        historical = self._pure(
            fixture,
            copy.deepcopy(fixture.pruning()),
            t2="f" * 64,
        )
        self.assertEqual(historical.severity, "WARN")
        self.assertFalse(historical.override_current)
        self.assertIsNone(historical.effective_verdict)

    def test_full_and_targeted_adapters_have_identical_warning_substance(self):
        fixture = self._fixture()
        snapshot = pruning_contract.read_markdown_snapshot(fixture.target)
        changed_body = snapshot.body.replace(
            FIRST_EVIDENCE.encode() + b"\n",
            FIRST_EVIDENCE.encode() + b"   \n",
            1,
        )
        fixture.target.write_bytes(
            snapshot.raw[:-len(snapshot.body)] + changed_body
        )
        shared = self._result(fixture)
        expected = shared.formatted_findings()
        full_findings, checked, defects = full_validator.check_pruning_contract(
            fixture.root
        )
        targeted = check_one.run_pruning_check(TARGET_UID, fixture.root)
        targeted_defects, summary = check_one.run_checks(
            TARGET_UID,
            "document",
            fixture.root,
            quiet=True,
        )

        self.assertEqual(full_findings, expected)
        self.assertEqual(targeted.formatted_findings(), expected)
        self.assertEqual((checked, defects), (1, 0))
        self.assertEqual(targeted_defects, 0)
        self.assertIn("PASS", summary)
        self.assertTrue(all(line.startswith("[WARN]") for line in expected))
        cli = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "tropo-check-one.py"),
                TARGET_UID,
                "--vault-path",
                str(fixture.root),
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn("PRUNING_T1_STALE", cli.stdout)
        self.assertIn("→ PASS", cli.stdout)

    def test_full_and_targeted_adapters_have_identical_failure_tally(self):
        fixture = self._fixture()
        block = copy.deepcopy(fixture.pruning())
        block["evidence_span"] = "Mismatched evidence."
        self._replace_block(fixture, block)

        shared = self._result(fixture)
        expected = shared.formatted_findings()
        full_findings, checked, defects = full_validator.check_pruning_contract(
            fixture.root
        )
        targeted = check_one.run_pruning_check(TARGET_UID, fixture.root)
        targeted_defects, summary = check_one.run_checks(
            TARGET_UID,
            "document",
            fixture.root,
            quiet=True,
        )

        self.assertEqual(shared.severity, "FAIL")
        self.assertEqual(full_findings, expected)
        self.assertEqual(targeted.formatted_findings(), expected)
        self.assertEqual((checked, defects), (1, 1))
        self.assertEqual(targeted_defects, 1)
        self.assertIn("FAIL", summary)
        self.assertTrue(all(line.startswith("[FAIL]") for line in expected))
        cli = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "tropo-check-one.py"),
                TARGET_UID,
                "--vault-path",
                str(fixture.root),
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(cli.returncode, 1, cli.stderr)
        self.assertIn("PRUNING_EVIDENCE", cli.stdout)
        self.assertIn("→ FAIL", cli.stdout)

    def test_validation_calls_do_not_mutate_any_fixture_file(self):
        fixture = self._fixture()
        gc.collect()
        connection = sqlite3.connect(fixture.root / "vault" / "00-index.sqlite")
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            connection.close()
        gc.collect()
        before = self._tree_bytes(fixture.root)

        shared = self._result(fixture)
        full = full_validator.check_pruning_contract(fixture.root)
        targeted = check_one.run_pruning_check(TARGET_UID, fixture.root)

        self.assertEqual(shared.severity, "PASS")
        self.assertEqual(full, ([], 1, 0))
        self.assertEqual(targeted.severity, "PASS")
        self.assertEqual(self._tree_bytes(fixture.root), before)


class FederationProvenanceFieldTests(unittest.TestCase):
    """origin_studio + judge_prompt_sha256 must travel ON the stamp.

    A verdict crossing a federation mount boundary has to be evaluable without
    resolving back into the origin studio, because the origin's policy file may
    not be readable from the receiving side. Metis G93 flagged this on
    2026-07-25 as the last cheap moment — before the first sweep's 250
    proposals become stamps and a retrofit means rewriting governed bodies.
    """

    GOOD = {
        "verdict": "finished",
        "evidence_span": "This work is complete.",
        "evidence_locator": {
            "body_sha256": "a" * 64,
            "start_byte": 0,
            "end_byte": 22,
        },
        "judge_policy_uid": "341823aa",
        "judge_version": "2.0.0",
        "judge_prompt_sha256": "b" * 64,
        "origin_studio": "f1a7b3c2",
        "judged_at": "2026-07-25T00:00:00Z",
        "confidence": 0.9,
        "normalized_body_hash_judged": "c" * 64,
    }

    def test_complete_block_with_provenance_is_accepted(self):
        pruning_contract.validate_pruning_block(dict(self.GOOD))

    def test_both_provenance_fields_are_required(self):
        for field in ("origin_studio", "judge_prompt_sha256"):
            with self.subTest(missing=field):
                block = dict(self.GOOD)
                block.pop(field)
                with self.assertRaises(pruning_contract.PruningContractError):
                    pruning_contract.validate_pruning_block(block)

    def test_origin_studio_must_be_eight_lowercase_hex(self):
        for bad in ("NOTHEX", "F1A7B3C2", "f1a7b3c", "f1a7b3c22", "", None, 12345678):
            with self.subTest(value=bad):
                block = dict(self.GOOD)
                block["origin_studio"] = bad
                with self.assertRaises(pruning_contract.PruningContractError):
                    pruning_contract.validate_pruning_block(block)

    def test_prompt_sha_may_be_null_for_a_judge_with_no_prompt(self):
        # A model-only judge has no prompt to hash. Absent is honest; a
        # fabricated hash would not be. The key stays required so readers can
        # rely on it existing.
        block = dict(self.GOOD)
        block["judge_prompt_sha256"] = None
        pruning_contract.validate_pruning_block(block)

    def test_malformed_prompt_sha_refuses(self):
        for bad in ("b" * 63, "B" * 64, "zz", 5):
            with self.subTest(value=bad):
                block = dict(self.GOOD)
                block["judge_prompt_sha256"] = bad
                with self.assertRaises(pruning_contract.PruningContractError):
                    pruning_contract.validate_pruning_block(block)


class OriginStudioResolutionTests(unittest.TestCase):
    """origin_studio is derived from the studio, never handed in by a caller.

    A provenance field a caller can supply is a gate defended with a
    caller-controlled value: it would let a writer mint a stamp that lies about
    which studio judged the body, which is exactly what a mount boundary reads.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write_studio(self, text: str):
        (self.root / "STUDIO.md").write_text(text, encoding="utf-8")

    def test_resolves_uid_from_studio_frontmatter(self):
        self._write_studio("---\nuid: f1a7b3c2\nvault_name: Argo-OS\n---\n# Argo\n")
        self.assertEqual(
            pruning_contract.resolve_origin_studio(self.root), "f1a7b3c2"
        )

    def test_missing_studio_file_fails_closed(self):
        with self.assertRaises(pruning_contract.PruningContractError):
            pruning_contract.resolve_origin_studio(self.root)

    def test_absent_or_malformed_uid_fails_closed_rather_than_guessing(self):
        for frontmatter in (
            "---\nvault_name: Argo-OS\n---\n",          # no uid at all
            "---\nuid: NOTHEX00\n---\n",                 # not lowercase hex
            "---\nuid: f1a7b3c\n---\n",                  # too short
            "---\nuid: 12345\nuid: 67890\n---\n",        # duplicate key
            "# no frontmatter at all\n",
        ):
            with self.subTest(frontmatter=frontmatter[:28]):
                self._write_studio(frontmatter)
                with self.assertRaises(pruning_contract.PruningContractError):
                    pruning_contract.resolve_origin_studio(self.root)

    def test_real_studio_resolves(self):
        # The live studio must actually be resolvable, or no stamp can be written.
        self.assertEqual(
            pruning_contract.resolve_origin_studio(ROOT), "f1a7b3c2"
        )


if __name__ == "__main__":
    unittest.main()
