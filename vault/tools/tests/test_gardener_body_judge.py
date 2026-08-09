#!/usr/bin/env python3
"""Isolated plants for loop policy enforcement and dry-run body-judge queue."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
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
SCRIPTS = ROOT / ".tropo" / "scripts"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


body_judge = _load(
    "gardener_body_judge_test_target",
    TOOLS / "tropo-gardener-body-judge.py",
)
rebuild = _load(
    "gardener_body_judge_test_rebuild",
    TOOLS / "tropo-rebuild-index.py",
)
from lib import index_surfaces, pruning_contract, template_leg  # noqa: E402
from lib.normalized_body_hash import (  # noqa: E402
    normalized_body_sha256,
    raw_body_sha256,
)
import loop_validators  # noqa: E402


AUTHOR_UID = "11111111"
HUMAN_UID = "22222222"
TOOL_UID = "33333333"
POLICY_UID = "44444444"
OTHER_POLICY_UID = "55555555"


def _write_markdown(
    root: Path,
    relative: str,
    frontmatter: dict,
    body: str = "# Fixture\n\nFixture body.\n",
) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n"
        + body,
        encoding="utf-8",
    )
    return path


def _frontmatter(path: Path) -> dict:
    snapshot = pruning_contract.read_markdown_snapshot(path)
    return snapshot.frontmatter


def _base_loop(
    uid: str,
    *,
    status: str = "draft",
    runner: str | None = None,
) -> dict:
    frontmatter = {
        "uid": uid,
        "type": "loop",
        "title": f"Loop {uid}",
        "description": "Isolated loop validator fixture.",
        "name": f"loop-{uid}",
        "version": "0.1.0",
        "author": AUTHOR_UID,
        "status": status,
        "state": "active",
        "goal": {
            "description": "Done condition",
            "exit_criteria": ["fixture exits cleanly"],
            "authored_by": HUMAN_UID,
        },
        "trigger": {"kind": "manual", "spec": "explicit fixture launch"},
        "policy": {"kind": "agentic-tool", "ref": TOOL_UID},
        "tools": [TOOL_UID],
        "verifier": {
            "kind": "validator",
            "independent": True,
            "lenses": 2,
            "attestation": "aspirational",
        },
        "brakes": {
            "max_iterations": 1,
            "max_budget_usd": 0.0,
            "max_wall_clock_min": 1,
        },
        "consequence": "high",
        "schema_version": 2,
        "capsule_version": "1.4",
    }
    if runner is not None:
        frontmatter["runner"] = runner
    return frontmatter


def _authority_rows() -> list[dict]:
    return [
        {
            "uid": AUTHOR_UID,
            "type": "agent",
            "status": "active",
            "state": "active",
        },
        {
            "uid": HUMAN_UID,
            "type": "principal",
            "principal_class": "human",
            "status": "active",
            "state": "active",
        },
        {
            "uid": TOOL_UID,
            "type": "tool",
            "status": "active",
            "state": "active",
        },
    ]


def _write_registered_tool(
    root: Path,
    *,
    uid: str = TOOL_UID,
    name: str = "gardener-body-judge",
) -> Path:
    path = root / "vault" / "tools" / f"tropo-{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "uid": uid,
        "name": name,
        "type": "tool",
        "status": "active",
        "state": "active",
        "writes_scope": [],
    }
    path.write_text(
        "#!/usr/bin/env python3\n"
        '"""\n'
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n"
        '"""\n',
        encoding="utf-8",
    )
    return path


def _write_index_file(root: Path, filename: str, rows: list[dict]) -> None:
    path = root / "vault" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _write_index(root: Path, rows: list[dict]) -> None:
    _write_index_file(root, "00-index.jsonl", rows)


def _clear_loop_caches() -> None:
    loop_validators._load_loops.cache_clear()
    loop_validators._load_loop_runs.cache_clear()
    loop_validators._load_tools.cache_clear()


class LoopMintScratch:
    def __init__(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="loop_mint_")
        self.root = Path(self._temp.name)
        (self.root / ".tropo").mkdir()
        (self.root / "vault" / "files").mkdir(parents=True)
        capsules = self.root / "vault" / "capsules"
        capsules.mkdir()
        shutil.copy2(
            ROOT / "vault" / "capsules" / "tropo-loop.capsule.md",
            capsules / "tropo-loop.capsule.md",
        )
        tools = self.root / "vault" / "tools"
        tools.mkdir()
        for name in (
            "tropo-mint-id.py",
            "tropo-rebuild-index.py",
            "tropo-generate-relations-header.py",
            "tropo-navblock-strip.py",
        ):
            shutil.copy2(TOOLS / name, tools / name)
        shutil.copytree(TOOLS / "lib", tools / "lib")
        (capsules / "mint-registry.json").write_bytes(
            template_leg.build_mint_registry_bytes(self.root)
        )
        _write_markdown(
            self.root,
            f"vault/files/{AUTHOR_UID}.md",
            _authority_rows()[0],
        )
        _write_markdown(
            self.root,
            f"vault/files/{HUMAN_UID}.md",
            _authority_rows()[1],
        )
        _write_markdown(
            self.root,
            f"vault/files/{TOOL_UID}.md",
            _authority_rows()[2],
        )
        self._run_rebuild("--apply", "--skip-rehydrate")

    @property
    def mint_script(self) -> Path:
        return self.root / "vault" / "tools" / "tropo-mint-id.py"

    @property
    def rebuild_script(self) -> Path:
        return self.root / "vault" / "tools" / "tropo-rebuild-index.py"

    def _run_rebuild(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                sys.executable,
                str(self.rebuild_script),
                *args,
                "--vault-path",
                str(self.root),
            ],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        return result

    def close(self) -> None:
        self._temp.cleanup()


class LoopPolicyValidatorTests(unittest.TestCase):
    def tearDown(self) -> None:
        _clear_loop_caches()

    def test_disabled_loop_refuses_mint_while_embedded_check_one_passes(self) -> None:
        scratch = LoopMintScratch()
        self.addCleanup(scratch.close)
        refused = subprocess.run(
            [
                sys.executable,
                str(scratch.mint_script),
                "--type",
                "loop",
                "--author",
                "talos-t33",
            ],
            cwd=scratch.root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertIn("mint_mode 'disabled'", refused.stderr)

        uid = "44440001"
        path = scratch.root / "vault" / "files" / f"{uid}.md"
        legacy_leg = template_leg.load_verifier_template(scratch.root, "loop")
        legacy_scaffold = (
            legacy_leg.scaffold
            .replace("<<MINT:uid>>", uid)
            .replace("<<MINT:date>>", "2026-08-03")
            .replace("<<MINT:author>>", "talos-t33")
            .replace("<<MINT:capsule_version>>", legacy_leg.capsule_version)
        )
        path.write_text(legacy_scaffold, encoding="utf-8")
        frontmatter = _frontmatter(path)
        frontmatter.update(_base_loop(uid))
        frontmatter["capsule_version"] = legacy_leg.capsule_version
        path.write_text(
            "---\n"
            + yaml.safe_dump(frontmatter, sort_keys=False)
            + "---\n"
            "# Consumed Loop\n\n"
            "## Purpose\nScratch purpose.\n\n"
            "## Goal & Verifier\nIndependent fixture verifier.\n\n"
            "## Brakes\nZero-dollar hard floor.\n\n"
            "## Cold-Boot Walk-Through\nManual start to deterministic stop.\n\n"
            "## Known Enforcement Gaps\nNone verified.\n\n"
            "## Changelog\nInitial fixture.\n",
            encoding="utf-8",
        )
        text = path.read_text(encoding="utf-8")
        self.assertEqual(template_leg.find_required_placeholders(text), [])
        scratch._run_rebuild("--only", uid)
        _clear_loop_caches()

        targeted = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "tropo-check-one.py"),
                uid,
                "--capsule",
                "loop",
                "--vault-path",
                str(scratch.root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            targeted.returncode,
            0,
            targeted.stdout + targeted.stderr,
        )
        self.assertIn("0 finding(s), 0 defect(s)", targeted.stdout)

    def _validator_fixture(
        self,
        frontmatter: dict,
        *,
        human_row: dict | None = None,
    ) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory(prefix="loop_validator_")
        root = Path(temp.name)
        _write_markdown(
            root,
            f"vault/files/{frontmatter['uid']}.md",
            frontmatter,
        )
        rows = _authority_rows()
        if human_row is not None:
            rows[1] = human_row
        rows.append(
            {
                "uid": frontmatter["uid"],
                "type": "loop",
                "path": f"vault/files/{frontmatter['uid']}.md",
                "status": frontmatter.get("status"),
                "state": frontmatter.get("state"),
                "runner": frontmatter.get("runner"),
            }
        )
        _write_registered_tool(root)
        _write_index(root, rows)
        _clear_loop_caches()
        return temp, root

    def test_malformed_author_human_lenses_brakes_and_cadence_fail(self) -> None:
        cases: list[tuple[str, dict, str, dict | None]] = []

        malformed_author = _base_loop("aaaa0001")
        malformed_author["author"] = "talos-t33"
        cases.append(("author", malformed_author, "author must be an 8-hex", None))

        unresolved_author = _base_loop("aaaa0008")
        unresolved_author["author"] = "99999999"
        cases.append(
            (
                "author-unresolved",
                unresolved_author,
                "must resolve exactly once",
                None,
            )
        )

        bad_human = _base_loop("aaaa0002")
        inactive_human = copy.deepcopy(_authority_rows()[1])
        inactive_human["state"] = "archived"
        cases.append(
            (
                "human",
                bad_human,
                "current active human principal",
                inactive_human,
            )
        )

        bad_lenses = _base_loop("aaaa0003")
        bad_lenses["verifier"]["lenses"] = 1
        cases.append(("lenses", bad_lenses, "lenses must be an integer >= 2", None))

        dependent_verifier = _base_loop("aaaa0009")
        dependent_verifier["verifier"]["independent"] = False
        cases.append(
            (
                "independent",
                dependent_verifier,
                "verifier.independent must be true",
                None,
            )
        )

        negative_brake = _base_loop("aaaa0004")
        negative_brake["brakes"]["max_budget_usd"] = -0.01
        cases.append(
            (
                "brakes",
                negative_brake,
                "max_budget_usd must be a finite nonnegative number",
                None,
            )
        )

        missing_floor = _base_loop("aaaa0010")
        missing_floor["brakes"] = {"max_iterations": 1}
        cases.append(
            (
                "brake-floor",
                missing_floor,
                "brakes missing hard floor",
                None,
            )
        )

        bad_maintenance = _base_loop("aaaa0005")
        bad_maintenance.update(
            {
                "cadence": "daily",
                "consent_mode": "sometimes",
                "runner": "gardener-body-judge",
            }
        )
        cases.append(
            (
                "cadence",
                bad_maintenance,
                "consent_mode 'sometimes'",
                None,
            )
        )

        for name, frontmatter, expected, human_row in cases:
            with self.subTest(name=name):
                temp, root = self._validator_fixture(
                    frontmatter,
                    human_row=human_row,
                )
                self.addCleanup(temp.cleanup)
                findings, _checked, _defects = (
                    loop_validators.run_all_loop_checks(root)
                )
                self.assertIn(expected, "\n".join(findings))

        maintenance_disabled = _base_loop("aaaa0006")
        maintenance_disabled.update(
            {
                "cadence": "daily",
                "consent_mode": "disabled",
                "runner": "sa.fixture",
            }
        )
        temp, root = self._validator_fixture(maintenance_disabled)
        self.addCleanup(temp.cleanup)
        findings, _checked, _defects = loop_validators.check_loop_consent_mode(
            root
        )
        self.assertEqual(findings, [])

        nonmaintenance = _base_loop("aaaa0007")
        nonmaintenance["consent_mode"] = "not-an-enum"
        nonmaintenance["runner"] = "not-a-runner"
        temp, root = self._validator_fixture(nonmaintenance)
        self.addCleanup(temp.cleanup)
        findings, _checked, _defects = loop_validators.check_loop_consent_mode(
            root
        )
        self.assertEqual(findings, [])

    def test_cadence_tool_runner_requires_exact_active_policy_binding(self) -> None:
        valid = _base_loop(
            "aaaa0011",
            status="active",
            runner="gardener-body-judge",
        )
        valid.update(
            {
                "cadence": "weekly",
                "consent_mode": "auto",
                "trigger": {
                    "kind": "schedule",
                    "spec": "weekly proposal-only fixture",
                },
            }
        )
        temp, root = self._validator_fixture(valid)
        self.addCleanup(temp.cleanup)
        findings, _checked, defects = loop_validators.check_loop_consent_mode(
            root
        )
        self.assertEqual((findings, defects), ([], 0))

        invalid_cases = (
            (
                "name-mismatch",
                lambda fm: fm.update({"runner": "unregistered-runner"}),
                "must equal registered tool name",
            ),
            (
                "missing-tools-binding",
                lambda fm: fm.update({"tools": []}),
                "policy.ref must be present in tools",
            ),
            (
                "wrong-policy-kind",
                lambda fm: fm.update(
                    {"policy": {"kind": "executive", "ref": TOOL_UID}}
                ),
                "requires policy.kind agentic-tool",
            ),
        )
        for name, mutate, expected in invalid_cases:
            with self.subTest(name=name):
                frontmatter = copy.deepcopy(valid)
                frontmatter["uid"] = {
                    "name-mismatch": "aaaa0012",
                    "missing-tools-binding": "aaaa0013",
                    "wrong-policy-kind": "aaaa0014",
                }[name]
                mutate(frontmatter)
                temp, root = self._validator_fixture(frontmatter)
                self.addCleanup(temp.cleanup)
                findings, _checked, defects = (
                    loop_validators.check_loop_consent_mode(root)
                )
                self.assertEqual(defects, 1)
                self.assertIn(expected, "\n".join(findings))

    def test_gardener_policy_uniqueness_zero_one_two_active(self) -> None:
        for active_count in (0, 1, 2):
            with self.subTest(active_count=active_count):
                temp = tempfile.TemporaryDirectory(prefix="policy_unique_")
                self.addCleanup(temp.cleanup)
                root = Path(temp.name)
                rows = _authority_rows()
                for index in range(2):
                    uid = f"aaaa000{index}"
                    status = "active" if index < active_count else (
                        "draft" if index == 0 else "archived"
                    )
                    state = "active" if status != "archived" else "archived"
                    loop = _base_loop(
                        uid,
                        status=status,
                        runner="gardener-body-judge",
                    )
                    loop["state"] = state
                    _write_markdown(
                        root,
                        f"vault/files/{uid}.md",
                        loop,
                    )
                    rows.append(
                        {
                            "uid": uid,
                            "type": "loop",
                            "status": status,
                            "state": state,
                            "runner": "gardener-body-judge",
                            "path": f"vault/files/{uid}.md",
                        }
                    )
                _write_index(root, rows)
                _clear_loop_caches()
                findings, checked, defects = (
                    loop_validators.check_gardener_policy_uniqueness(root)
                )
                if active_count == 0:
                    self.assertEqual(checked, 0)
                    self.assertEqual(defects, 0)
                    self.assertIn("[WARN]", findings[0])
                    all_findings, _all_checked, all_defects = (
                        loop_validators.run_all_loop_checks(root)
                    )
                    self.assertEqual(all_defects, 0)
                    self.assertTrue(
                        any(
                            "no active gardener-body-judge loop" in finding
                            for finding in all_findings
                        )
                    )
                elif active_count == 1:
                    self.assertEqual((findings, checked, defects), ([], 1, 0))
                else:
                    self.assertEqual(checked, 2)
                    self.assertEqual(defects, 1)
                    self.assertIn("[ERROR]", findings[0])
                    self.assertIn("aaaa0000", findings[0])
                    self.assertIn("aaaa0001", findings[0])

    def test_frozen_legacy_warns_while_every_other_uid_is_strict_v15(self) -> None:
        def malformed(uid: str) -> dict:
            frontmatter = _base_loop(uid)
            frontmatter.update(
                {
                    "author": "talos-t33",
                    "capsule_version": "1.0",
                    "cadence": "daily",
                    "consent_mode": "sometimes",
                    "runner": "not-a-runner",
                    "consequence": "low",
                }
            )
            frontmatter["goal"]["authored_by"] = "99999999"
            frontmatter["verifier"]["ref"] = TOOL_UID
            frontmatter["policy"]["ref"] = TOOL_UID
            frontmatter["brakes"]["max_budget_usd"] = float("nan")
            return frontmatter

        cases = (
            ("03f9a721", "WARN", 0),
            ("aaaa0099", "ERROR", 1),
        )
        for uid, severity, minimum_defects in cases:
            with self.subTest(uid=uid):
                temp, root = self._validator_fixture(malformed(uid))
                self.addCleanup(temp.cleanup)
                findings, _checked, defects = (
                    loop_validators.run_all_loop_checks(root)
                )
                uid_findings = [
                    finding for finding in findings if uid in finding
                ]
                self.assertTrue(uid_findings)
                self.assertTrue(
                    all(f"[{severity}]" in finding for finding in uid_findings),
                    "\n".join(uid_findings),
                )
                if minimum_defects == 0:
                    self.assertEqual(defects, 0)
                else:
                    self.assertGreaterEqual(defects, minimum_defects)
                self.assertTrue(
                    any("finite nonnegative number" in f for f in uid_findings)
                )
                self.assertTrue(
                    any("current active principal" in f for f in uid_findings)
                )
                self.assertTrue(
                    any("identity-distinct" in f for f in uid_findings)
                )

    def test_strict_goal_author_requires_current_principal_and_human_at_high(self) -> None:
        inactive = _base_loop("aaaa0097")
        inactive["consequence"] = "low"
        inactive_human = copy.deepcopy(_authority_rows()[1])
        inactive_human["state"] = "archived"
        temp, root = self._validator_fixture(
            inactive,
            human_row=inactive_human,
        )
        self.addCleanup(temp.cleanup)
        findings, _checked, defects = (
            loop_validators.check_loop_goal_independent(root)
        )
        self.assertGreater(defects, 0)
        self.assertIn("current active principal", "\n".join(findings))

        nonhuman = _base_loop("aaaa0098")
        active_nonhuman = copy.deepcopy(_authority_rows()[1])
        active_nonhuman["principal_class"] = "agent"
        temp, root = self._validator_fixture(
            nonhuman,
            human_row=active_nonhuman,
        )
        self.addCleanup(temp.cleanup)
        findings, _checked, defects = (
            loop_validators.check_loop_goal_independent(root)
        )
        self.assertGreater(defects, 0)
        self.assertIn("current active human principal", "\n".join(findings))


class QueueScratch:
    def __init__(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="body_judge_queue_")
        self.root = Path(self._temp.name)
        self.rows = _authority_rows()
        self.archive_rows: list[dict] = []
        _write_registered_tool(self.root)
        self.policy = self.add_source(
            POLICY_UID,
            f"vault/files/{POLICY_UID}.md",
            self.policy_frontmatter(),
            "os",
            body="# Body-Judge Policy\n\nPolicy body evidence.\n",
        )
        self.stamp_current(self.policy)

    def close(self) -> None:
        self._temp.cleanup()

    @staticmethod
    def policy_frontmatter(uid: str = POLICY_UID) -> dict:
        frontmatter = _base_loop(
            uid,
            status="active",
            runner="gardener-body-judge",
        )
        frontmatter.update(
            {
                "version": "2.1.0",
                "cadence": "weekly",
                "consent_mode": "auto",
                "trigger": {
                    "kind": "schedule",
                    "spec": "weekly proposal-only fixture",
                },
                "judge_model": "cursor-subagent",
                "judge_kind": "cursor-cloud-subagent",
                "provider_api_calls": "forbidden",
                "brakes": {
                    "max_iterations": 1,
                    # v2.0.0: unpriced sub-agent judge makes no provider
                    # call, so the metered ceiling is an enforceable zero.
                    "max_budget_usd": 0.0,
                    "max_wall_clock_min": 180,
                },
            }
        )
        return frontmatter

    def add_source(
        self,
        uid: str,
        relative: str,
        frontmatter: dict | None,
        segment: str,
        *,
        body: str = "# Body\n\nBody evidence sentence.\n",
        archived_index: bool = False,
    ) -> Path:
        fm = frontmatter or {
            "uid": uid,
            "type": "document",
            "title": f"Document {uid}",
            "description": "Body-judge queue fixture.",
            "status": "active",
            "state": "active",
            "schema_version": 2,
        }
        path = _write_markdown(self.root, relative, fm, body)
        row = copy.deepcopy(fm)
        row["path"] = relative
        row["segment"] = segment
        (self.archive_rows if archived_index else self.rows).append(row)
        return path

    def stamp_current(
        self,
        path: Path,
        *,
        policy_uid: str = POLICY_UID,
        version: str = "2.1.0",
        override: bool = False,
    ) -> None:
        snapshot = pruning_contract.read_markdown_snapshot(path)
        evidence = "Policy body evidence." if path == self.policy else (
            "Body evidence sentence."
        )
        encoded = evidence.encode("utf-8")
        start = snapshot.body.index(encoded)
        block = {
            "verdict": "superseded",
            "evidence_span": evidence,
            "evidence_locator": {
                "body_sha256": raw_body_sha256(path),
                "start_byte": start,
                "end_byte": start + len(encoded),
            },
            "judge_policy_uid": policy_uid,
            "judge_version": version,
            # Federation provenance travels ON the stamp (core capsule v1.8).
            "judge_prompt_sha256": "b" * 64,
            "origin_studio": "f1a7b3c2",
            "judged_at": "2026-07-17T16:00:00+00:00",
            "confidence": 0.99,
            "normalized_body_hash_judged": normalized_body_sha256(path),
        }
        if override:
            block["override"] = {
                "action": "keep",
                "by": HUMAN_UID,
                "at": "2026-07-17T16:01:00+00:00",
                "reason": "Human fixture keeps the current body.",
            }
        frontmatter = snapshot.frontmatter
        frontmatter["pruning"] = block
        path.write_bytes(
            (
                "---\n"
                + yaml.safe_dump(frontmatter, sort_keys=False)
                + "---\n"
            ).encode("utf-8")
            + snapshot.body
        )

    def finalize(self) -> None:
        _write_index(self.root, self.rows)
        _write_index_file(
            self.root,
            "00-archive-index.jsonl",
            self.archive_rows,
        )
        _clear_loop_caches()


class BodyJudgeQueueTests(unittest.TestCase):
    def tearDown(self) -> None:
        _clear_loop_caches()

    def test_queue_classifies_four_homes_segments_and_is_deterministic(self) -> None:
        fixture = QueueScratch()
        self.addCleanup(fixture.close)

        absent = fixture.add_source(
            "aaaa1001",
            "vault/files/aaaa1001.md",
            None,
            "private",
        )
        current = fixture.add_source(
            "aaaa1002",
            "vault/agents/aaaa1002.md",
            None,
            "os",
        )
        fixture.stamp_current(current)
        t2_stale = fixture.add_source(
            "aaaa1003",
            "agents/talos/queue-fixture.md",
            None,
            "team:alpha",
        )
        fixture.stamp_current(t2_stale)
        t2_stale.write_text(
            t2_stale.read_text(encoding="utf-8") + "\nReal body edit.\n",
            encoding="utf-8",
        )
        policy_stale = fixture.add_source(
            "aaaa1004",
            "vault/capsules/tropo-queue-fixture.capsule.md",
            None,
            "os",
        )
        fixture.stamp_current(
            policy_stale,
            policy_uid=OTHER_POLICY_UID,
            version="0.9.0",
        )
        keep = fixture.add_source(
            "aaaa1005",
            "vault/files/aaaa1005.md",
            None,
            "private",
        )
        fixture.stamp_current(keep, override=True)
        archived = fixture.add_source(
            "aaaa1006",
            "vault/files/aaaa1006.md",
            None,
            "private",
            archived_index=True,
        )
        fixture.archive_rows.append(
            {
                "uid": "aaaa1007",
                "type": "document",
                "path": "vault/files/aaaa1007.md",
                "segment": "private",
            }
        )
        malformed = fixture.root / "vault" / "files" / "aaaa1008.md"
        malformed.write_text(
            "---\n"
            "uid: aaaa1008\n"
            "title: malformed: source\n"
            "---\n"
            "# Malformed fixture\n",
            encoding="utf-8",
        )
        fixture.archive_rows.append(
            {
                "uid": "aaaa1008",
                "type": "document",
                "path": "vault/files/aaaa1008.md",
                "segment": "private",
            }
        )
        symlink = fixture.root / "vault" / "files" / "aaaa1009.md"
        symlink.symlink_to("aaaa1001.md")
        fixture.archive_rows.append(
            {
                "uid": "aaaa1009",
                "type": "document",
                "path": "vault/files/aaaa1009.md",
                "segment": "private",
            }
        )
        fixture.archive_rows.append(
            {
                **fixture.policy_frontmatter(OTHER_POLICY_UID),
                "path": "recycle/loops/55555555.md",
                "segment": "private",
            }
        )
        unindexed = _write_markdown(
            fixture.root,
            "vault/files/aaaa1999.md",
            {
                "uid": "aaaa1999",
                "type": "document",
                "status": "active",
                "state": "active",
            },
        )
        readme = _write_markdown(
            fixture.root,
            "agents/talos/README.md",
            {
                "uid": "aaaa1998",
                "type": "document",
                "status": "active",
                "state": "active",
            },
        )
        fixture.finalize()

        before = {
            path.relative_to(fixture.root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in fixture.root.rglob("*")
            if path.is_file()
        }
        first = body_judge.build_dry_run_queue(fixture.root)
        second = body_judge.build_dry_run_queue(fixture.root)
        cli = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "tropo-gardener-body-judge.py"),
                "--dry-run",
                "--vault-path",
                str(fixture.root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        after = {
            path.relative_to(fixture.root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in fixture.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertEqual(first, second)
        self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)
        self.assertEqual(json.loads(cli.stdout), first)
        self.assertEqual(cli.stderr, "")
        self.assertEqual(first["policy_uid"], POLICY_UID)
        self.assertEqual(first["policy_version"], "2.1.0")
        self.assertEqual(first["scanned_count"], 10)
        self.assertEqual(first["queue_count"], 4)
        self.assertEqual(first["current_count"], 3)
        self.assertEqual(first["blocked_count"], 3)
        self.assertEqual(
            first["scanned_count"],
            first["queue_count"]
            + first["current_count"]
            + first["blocked_count"],
        )
        reasons = {
            row["uid"]: row["reason"] for row in first["candidates"]
        }
        self.assertEqual(
            reasons,
            {
                "aaaa1001": "missing-pruning",
                "aaaa1003": "t2-stale",
                "aaaa1004": "policy-stale",
                "aaaa1006": "missing-pruning",
            },
        )
        self.assertNotIn("aaaa1002", reasons)
        self.assertNotIn("aaaa1005", reasons)
        self.assertNotIn("aaaa1999", reasons)
        self.assertNotIn("aaaa1998", reasons)
        self.assertNotIn(OTHER_POLICY_UID, reasons)
        self.assertEqual(
            first["blocked"],
            [
                {
                    "uid": "aaaa1007",
                    "path": "vault/files/aaaa1007.md",
                    "segment": "private",
                    "reason": "source-missing",
                },
                {
                    "uid": "aaaa1008",
                    "path": "vault/files/aaaa1008.md",
                    "segment": "private",
                    "reason": "source-frontmatter-invalid",
                },
                {
                    "uid": "aaaa1009",
                    "path": "vault/files/aaaa1009.md",
                    "segment": "private",
                    "reason": "source-symlink",
                },
            ],
        )
        self.assertEqual(
            first["blocked_counts"],
            {
                "by_reason": {
                    "source-frontmatter-invalid": 1,
                    "source-missing": 1,
                    "source-symlink": 1,
                },
                "by_segment": {"private": 3},
            },
        )
        self.assertEqual(
            first["per_segment_counts"],
            {
                "os": {
                    "scanned_count": 3,
                    "queue_count": 1,
                    "current_count": 2,
                    "blocked_count": 0,
                },
                "private": {
                    "scanned_count": 6,
                    "queue_count": 2,
                    "current_count": 1,
                    "blocked_count": 3,
                },
                "team:alpha": {
                    "scanned_count": 1,
                    "queue_count": 1,
                    "current_count": 0,
                    "blocked_count": 0,
                },
            },
        )
        self.assertEqual(
            [row["uid"] for row in first["candidates"]],
            ["aaaa1004", "aaaa1001", "aaaa1006", "aaaa1003"],
        )
        self.assertTrue(absent.is_file())
        self.assertTrue(archived.is_file())
        self.assertTrue(unindexed.is_file())
        self.assertTrue(readme.is_file())

    def test_live_v21_policy_reaches_queue_computation_read_only(self) -> None:
        watched = (
            ROOT / "vault" / "files" / "341823aa.md",
            ROOT / "vault" / "00-index.jsonl",
            ROOT / "vault" / "00-archive-index.jsonl",
            ROOT / "vault" / "events" / "00-events.jsonl",
        )
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in watched
        }

        queue = body_judge.build_dry_run_queue(ROOT)

        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in watched
        }
        policy = _frontmatter(watched[0])
        self.assertEqual(before, after)
        self.assertEqual(queue["policy_uid"], "341823aa")
        self.assertEqual(queue["policy_version"], "2.1.0")
        self.assertEqual(policy["cadence"], "weekly")
        self.assertEqual(policy["consent_mode"], "auto")
        self.assertEqual(policy["trigger"]["kind"], "schedule")
        self.assertEqual(policy["judge_model"], "cursor-subagent")
        self.assertEqual(policy["judge_kind"], "cursor-cloud-subagent")
        self.assertEqual(policy["provider_api_calls"], "forbidden")
        self.assertEqual(
            policy["brakes"],
            {
                "max_iterations": 1,
                "max_budget_usd": 0.0,
                "max_wall_clock_min": 180,
            },
        )

    def test_current_production_union_is_fully_accounted_read_only(self) -> None:
        watched = (
            ROOT / "vault" / "00-index.jsonl",
            ROOT / "vault" / "00-archive-index.jsonl",
            ROOT / "vault" / "events" / "00-events.jsonl",
            ROOT / ".tropo-studio" / "dirty-counter.json",
        )
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in watched
        }
        _current, candidate_union = (
            pruning_contract.load_target_index_union_strict(ROOT)
        )
        expected_scanned = len(
            body_judge._eligible_candidate_rows(candidate_union)
        )
        accounting = body_judge.account_current_union(ROOT)
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in watched
        }

        self.assertEqual(before, after)
        self.assertEqual(accounting["scanned_count"], expected_scanned)
        self.assertEqual(
            accounting["blocked_count"],
            len(accounting["blocked"]),
        )
        self.assertEqual(
            accounting["blocked_count"],
            sum(accounting["blocked_counts"]["by_reason"].values()),
        )
        self.assertEqual(
            accounting["scanned_count"],
            accounting["queue_count"]
            + accounting["current_count"]
            + accounting["blocked_count"],
        )
        self.assertEqual(
            accounting["scanned_count"],
            sum(
                segment["scanned_count"]
                for segment in accounting["per_segment_counts"].values()
            ),
        )

    def test_missing_ambiguous_and_invalid_policy_refuse(self) -> None:
        fixture = QueueScratch()
        self.addCleanup(fixture.close)
        fixture.finalize()

        no_policy_rows = [
            row for row in fixture.rows if row.get("uid") != POLICY_UID
        ]
        _write_index(fixture.root, no_policy_rows)
        _clear_loop_caches()
        with self.assertRaisesRegex(
            body_judge.BodyJudgeQueueError,
            "found 0",
        ):
            body_judge.build_dry_run_queue(fixture.root)

        duplicate = QueueScratch()
        self.addCleanup(duplicate.close)
        duplicate.rows.append(
            {
                **duplicate.policy_frontmatter(OTHER_POLICY_UID),
                "path": f"vault/files/{OTHER_POLICY_UID}.md",
                "segment": "private",
            }
        )
        duplicate.finalize()
        with self.assertRaisesRegex(
            body_judge.BodyJudgeQueueError,
            "found 2",
        ):
            body_judge.build_dry_run_queue(duplicate.root)

        invalid_cases = (
            (
                "consent",
                lambda fm: fm.update({"consent_mode": "ask"}),
                None,
                "consent_mode must be auto",
            ),
            (
                "trigger",
                lambda fm: fm.update(
                    {"trigger": {"kind": "manual", "spec": "manual fixture"}}
                ),
                None,
                "trigger.kind must be schedule",
            ),
            (
                "judge-model",
                lambda fm: fm.update({"judge_model": "claude-opus-4-8"}),
                None,
                "judge_model must be cursor-subagent",
            ),
            (
                "judge-kind",
                lambda fm: fm.update({"judge_kind": "provider-api"}),
                None,
                "judge_kind must be cursor-cloud-subagent",
            ),
            (
                "provider",
                lambda fm: fm.update({"provider_api_calls": "allowed"}),
                None,
                "provider_api_calls must be forbidden",
            ),
            (
                "brakes",
                lambda fm: fm["brakes"].update({"max_budget_usd": 80.0}),
                None,
                "max_budget_usd must equal locked value 0.0",
            ),
            (
                "version",
                lambda fm: fm.update({"version": "not-semver"}),
                {"version": "not-semver"},
                "version must be a semantic version",
            ),
            (
                "runner",
                lambda fm: fm.update({"runner": "other-runner"}),
                {"runner": "other-runner"},
                "found 0",
            ),
        )
        for name, mutate, row_update, expected in invalid_cases:
            with self.subTest(name=name):
                invalid = QueueScratch()
                self.addCleanup(invalid.close)
                snapshot = pruning_contract.read_markdown_snapshot(invalid.policy)
                invalid_frontmatter = snapshot.frontmatter
                mutate(invalid_frontmatter)
                invalid.policy.write_bytes(
                    (
                        "---\n"
                        + yaml.safe_dump(invalid_frontmatter, sort_keys=False)
                        + "---\n"
                    ).encode("utf-8")
                    + snapshot.body
                )
                if row_update:
                    policy_row = next(
                        row
                        for row in invalid.rows
                        if row.get("uid") == POLICY_UID
                    )
                    policy_row.update(row_update)
                invalid.finalize()
                with self.assertRaisesRegex(
                    body_judge.BodyJudgeQueueError,
                    expected,
                ):
                    body_judge.build_dry_run_queue(invalid.root)

    def test_cli_is_explicit_dry_run_only(self) -> None:
        assert body_judge.__doc__ is not None
        metadata_text = body_judge.__doc__.split("---", 2)[1]
        metadata = yaml.safe_load(metadata_text)
        self.assertEqual(metadata["uid"], "76ebc743")
        self.assertEqual(metadata["governance_category"], "query")
        self.assertEqual(
            metadata["writes_scope"],
            [
                "vault/loop-runs/*/gardener-synthetic-canary-scorecard.json",
                "vault/loop-runs/*/gateway_spend.json",
            ],
        )
        self.assertFalse(metadata["destructive"])
        self.assertTrue(metadata["audit_required"])
        self.assertEqual(len(metadata["input"]["oneOf"]), 2)
        self.assertEqual(len(metadata["output"]["oneOf"]), 2)
        self.assertTrue(
            all(
                not variant["additionalProperties"]
                for variant in metadata["output"]["oneOf"]
            )
        )
        dry_schema = metadata["output"]["oneOf"][0]
        self.assertEqual(
            dry_schema["properties"]["policy_version"]["pattern"],
            "^[0-9]+[.][0-9]+(?:[.][0-9]+)?$",
        )
        self.assertEqual(
            dry_schema["properties"]["blocked_counts"]["required"],
            ["by_reason", "by_segment"],
        )
        self.assertEqual(
            dry_schema["properties"]["candidates"]["items"]["properties"][
                "reason"
            ]["enum"],
            [
                "missing-pruning",
                "t2-stale",
                "policy-stale",
                "invalid-pruning",
            ],
        )
        self.assertEqual(
            dry_schema["properties"]["blocked"]["items"]["properties"][
                "reason"
            ]["enum"],
            [
                "source-missing",
                "source-symlink",
                "source-frontmatter-invalid",
                "source-uid-mismatch",
                "source-path-invalid",
                "source-segment-invalid",
                "source-evaluation-failed",
            ],
        )
        self.assertIn("## Failure Modes", body_judge.__doc__)

        parser_dests = {action.dest for action in body_judge.build_parser()._actions}
        self.assertEqual(
            parser_dests,
            {
                "help",
                "dry_run",
                "synthetic_canary",
                "vault_path",
                "run_dir",
            },
        )

        refused = subprocess.run(
            [sys.executable, str(TOOLS / "tropo-gardener-body-judge.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(refused.returncode, 2)
        self.assertIn("--dry-run or --synthetic-canary is required", refused.stderr)

        for flag in ("--live", "--execute", "--stamp"):
            with self.subTest(flag=flag):
                bypass = subprocess.run(
                    [
                        sys.executable,
                        str(TOOLS / "tropo-gardener-body-judge.py"),
                        flag,
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(bypass.returncode, 2)
                self.assertIn("unrecognized arguments", bypass.stderr)

    def test_friendly_tool_registration_freshens_exact_row_in_scratch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="body_judge_tool_") as tmp:
            # macOS exposes /var/folders through /private/var/folders; use the
            # canonical path on both sides of rebuild/freshen comparisons.
            root = Path(tmp).resolve()
            (root / ".tropo").mkdir()
            (root / "vault" / "files").mkdir(parents=True)
            tools = root / "vault" / "tools"
            tools.mkdir()
            self.assertEqual(rebuild.rebuild_index(root, True), 0)
            source = TOOLS / "tropo-gardener-body-judge.py"
            target = tools / source.name
            shutil.copy2(source, target)

            self.assertEqual(rebuild.freshen_one("76ebc743", root), 0)
            records = index_surfaces.load_index_records(
                root,
                include_archive=True,
            )
            matches = [
                row for row in records if row.get("uid") == "76ebc743"
            ]
            self.assertEqual(len(matches), 1)
            self.assertEqual(
                matches[0]["path"],
                "vault/tools/tropo-gardener-body-judge.py",
            )
            self.assertEqual(matches[0]["governance_category"], "query")
            pruning_result = pruning_contract.check_pruning_uid(
                "76ebc743",
                root,
            )
            self.assertIsNotNone(pruning_result)
            self.assertFalse(pruning_result.applicable)
            self.assertEqual(pruning_result.findings, ())
            with sqlite3.connect(root / "vault" / "00-index.sqlite") as conn:
                row = conn.execute(
                    "SELECT fm_json FROM entries WHERE uid=?",
                    ("76ebc743",),
                ).fetchone()
            self.assertIsNotNone(row)
            sqlite_record = json.loads(row[0])
            self.assertEqual(sqlite_record["uid"], "76ebc743")
            self.assertEqual(sqlite_record["path"], matches[0]["path"])


if __name__ == "__main__":
    unittest.main()
