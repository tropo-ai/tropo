#!/usr/bin/env python3
"""Phase 1 typed-mint registry, companion, and transactional-birth plants."""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
SCRIPT_LIB = ROOT / ".tropo" / "scripts" / "lib"
if str(SCRIPT_LIB) not in sys.path:
    sys.path.insert(0, str(SCRIPT_LIB))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mint = _load("typed_mint_phase1_runtime", TOOLS / "tropo-mint-id.py")
generator = _load(
    "typed_mint_phase1_generator",
    TOOLS / "tropo-generate-mint-registry.py",
)
check_one = _load("typed_mint_phase1_check_one", TOOLS / "tropo-check-one.py")
dev_spec_validators = _load(
    "typed_mint_phase1_dev_spec_validators",
    ROOT / ".tropo" / "scripts" / "lib" / "dev_spec_validators.py",
)
spec_lock_validators = _load(
    "typed_mint_phase1_spec_lock_validators",
    ROOT / ".tropo" / "scripts" / "lib" / "spec_lock_validators.py",
)
from lib import template_leg  # noqa: E402


PILOTS = ("note", "task", "dev-spec", "design-brief")
BOUND_TYPES = PILOTS
FIXED_UIDS = {
    "note": "11111111",
    "task": "22222222",
    "dev-spec": "33333333",
    "design-brief": "44444444",
}
PILOT_REQUIRED_FRONTMATTER = {
    "note": {
        "uid", "type", "captured_by", "created_by_activation_uid", "created",
        "modified", "state", "member_of", "schema_version",
        "capsule_version", "governed_by",
    },
    "task": {
        "uid", "type", "title", "status", "requested_by", "requested_of",
        "member_of", "state", "created", "created_by",
        "created_by_activation_uid", "modified", "modified_by",
        "schema_version", "capsule_version", "governed_by",
    },
    "dev-spec": {
        "uid", "type", "title", "description", "status", "state", "owner",
        "author", "created", "created_by", "created_by_activation_uid",
        "modified", "modified_by", "schema_version", "capsule_version",
        "governed_by", "member_of", "committed_substrate",
        "acceptance_criteria",
    },
    "design-brief": {
        "uid", "type", "title", "description", "status", "state", "author",
        "owner", "member_of", "created", "created_by",
        "created_by_activation_uid", "modified", "modified_by",
        "schema_version", "capsule_version", "governed_by",
    },
}
PILOT_REQUIRED_SECTIONS = {
    "note": set(),
    "task": {"Intent", "What to Do", "Verification"},
    "dev-spec": {
        "Intent",
        "Current State and Gap",
        "Desired Capability",
        "Scope Boundaries",
        "Implementation Contract",
        "Acceptance and Verification",
        "Handoff",
    },
    "design-brief": {"The problem", "Proposed direction", "Open questions"},
}


class FixedDate(dt.date):
    @classmethod
    def today(cls) -> "FixedDate":
        return cls(2026, 8, 3)


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    end = text.find("\n---", 4)
    assert end != -1
    value = yaml.safe_load(text[4:end])
    assert isinstance(value, dict)
    return value


class MintFixture:
    def __init__(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="typed_mint_phase1_")
        # .resolve() because on macOS tempfile hands back /var/folders/..., which
        # is a symlink to /private/var/folders/.... mint_file() resolves the root
        # internally and then asks whether the output dir is relative_to() it, so
        # an unresolved fixture root made every containment check raise "scratch
        # output must stay inside the Studio root" -- 3 failures + 5 errors in
        # this file on every Mac, and green on Linux CI. The tool was never
        # wrong; the fixture described a machine nobody runs on.
        # (metis-g103 2026-08-06, found while adding lineage-provenance cover.)
        self.root = Path(self._temp.name).resolve()
        (self.root / ".tropo").mkdir()
        (self.root / "vault" / "files").mkdir(parents=True)
        self.workspace = (
            self.root
            / "agents"
            / "test-agent"
            / ".tropo-capsule"
            / "workspace"
        )
        self.workspace.mkdir(parents=True)
        capsules = self.root / "vault" / "capsules"
        templates = capsules / "templates"
        templates.mkdir(parents=True)
        for type_name in (*BOUND_TYPES, "test-spec"):
            shutil.copy2(
                ROOT / "vault" / "capsules" / f"tropo-{type_name}.capsule.md",
                capsules / f"tropo-{type_name}.capsule.md",
            )
            if type_name in BOUND_TYPES:
                shutil.copy2(
                    ROOT / "vault" / "capsules" / "templates" / f"{type_name}.template.md",
                    templates / f"{type_name}.template.md",
                )
        self.refresh_registry()

    def add_system_only_binding(self) -> None:
        capsule = self.root / "vault/capsules/tropo-system-record.capsule.md"
        template = self.root / "vault/capsules/templates/system-record.template.md"
        template.write_text(
            "---\n"
            "uid: '<<MINT:uid>>'\n"
            "type: system-record\n"
            "title: <<SYSTEM:title>>\n"
            "status: active\n"
            "owner: <<MINT:author>>\n"
            "created: '<<MINT:date>>'\n"
            "modified: '<<MINT:date>>'\n"
            "created_by_activation_uid: <<MINT:activation_uid>>\n"
            "capsule_version: '<<MINT:capsule_version>>'\n"
            "---\n",
            encoding="utf-8",
        )
        capsule.write_text(
            "---\n"
            "uid: aaaaaaaa\n"
            "name: system-record\n"
            "type: capsule-definition\n"
            "extends: core\n"
            "version: '1.0'\n"
            "mint_mode: system-only\n"
            "mint_template: vault/capsules/templates/system-record.template.md\n"
            "mint_template_version: '1.0'\n"
            f"mint_template_sha256: {hashlib.sha256(template.read_bytes()).hexdigest()}\n"
            "mint_output_home: vault/files\n"
            "---\n",
            encoding="utf-8",
        )
        self.refresh_registry()

    def refresh_registry(self) -> None:
        path = self.root / template_leg.MINT_REGISTRY_REL
        path.write_bytes(template_leg.build_mint_registry_bytes(self.root))

    def close(self) -> None:
        self._temp.cleanup()


class TypedMintPhase1Tests(unittest.TestCase):
    def test_dev_spec_validator_uses_status_done_and_v18_required_fields(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        path = fixture.root / "vault/files/33333333.md"
        path.write_text(
            "---\n"
            "uid: '33333333'\n"
            "type: dev-spec\n"
            "title: Example\n"
            "description: Example build contract\n"
            "status: done\n"
            "state: active\n"
            "capsule_version: '1.8'\n"
            "committed_substrate:\n"
            "  - target: example-target\n"
            "    change_class: NEW\n"
            "    description: Example target\n"
            "acceptance_criteria:\n"
            "  - id: AC1\n"
            "    behavior: Example behavior works\n"
            "    verify:\n"
            "      method: automated\n"
            "      command: python3 -m unittest example\n"
            "      evidence: Test exits zero\n"
            "---\n",
            encoding="utf-8",
        )
        required_findings, checked, _defects = (
            dev_spec_validators.check_dev_spec_required_fields(fixture.root)
        )
        self.assertEqual(checked, 1)
        self.assertEqual(required_findings, [])
        acceptance_findings, checked, _defects = (
            dev_spec_validators.check_dev_spec_acceptance_criteria_present(
                fixture.root
            )
        )
        self.assertEqual(checked, 1)
        self.assertEqual(acceptance_findings, [])

        close_findings, checked, _defects = (
            dev_spec_validators.check_dev_spec_close_invariants(fixture.root)
        )
        self.assertEqual(checked, 1)
        self.assertTrue(
            any(
                "status:done + state:active requires closed_at" in finding
                for finding in close_findings
            ),
            close_findings,
        )

        child_uid = "44444444"
        child = fixture.root / f"vault/files/{child_uid}.md"
        child.write_text(
            "---\n"
            f"uid: '{child_uid}'\n"
            "type: doc-spec\n"
            "status: locked\n"
            "state: active\n"
            "---\n",
            encoding="utf-8",
        )
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "acceptance_criteria:\n",
                f"triggered_doc_spec_uids:\n  - '{child_uid}'\n"
                "closed_at: '2026-08-03'\n"
                "acceptance_criteria:\n",
            ),
            encoding="utf-8",
        )
        dev_spec_validators._load_dev_specs.cache_clear()
        dev_spec_validators._load_uid_status_map.cache_clear()
        close_findings, _checked, _defects = (
            dev_spec_validators.check_dev_spec_close_invariants(fixture.root)
        )
        self.assertTrue(
            any(
                child_uid in finding and "not done" in finding
                for finding in close_findings
            ),
            close_findings,
        )

    def test_dev_spec_validation_and_lock_are_dual_legacy_v18(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        path = fixture.root / "vault/files/33333333.md"
        v18 = {
            "uid": "33333333",
            "type": "dev-spec",
            "description": "Version-aware contract",
            "status": "locked",
            "state": "active",
            "capsule_version": "1.8",
            "committed_substrate": [
                {
                    "target": "version-aware-target",
                    "change_class": "NEW",
                    "description": "Version-aware target",
                }
            ],
            "acceptance_criteria": [
                {
                    "id": "AC1",
                    "behavior": "The v1.8 behavior is observable.",
                    "verify": {
                        "method": "peer-review",
                        "command": "N/A — reviewer inspects the generated contract",
                        "evidence": "Review records the observed result.",
                    },
                }
            ],
        }

        def write(frontmatter: dict) -> None:
            path.write_text(
                "---\n"
                + yaml.safe_dump(frontmatter, sort_keys=False)
                + "---\n",
                encoding="utf-8",
            )
            dev_spec_validators._load_dev_specs.cache_clear()

        write(v18)
        self.assertEqual(
            dev_spec_validators.check_dev_spec_required_fields(fixture.root)[0],
            [],
        )
        self.assertEqual(
            dev_spec_validators.check_dev_spec_acceptance_criteria_present(
                fixture.root
            )[0],
            [],
        )
        self.assertEqual(
            spec_lock_validators.check_dev_spec_locked_required_fields_strict(
                fixture.root
            )[0],
            [],
        )

        malformed = json.loads(json.dumps(v18))
        malformed["acceptance_criteria"].append(
            {
                "id": "AC1",
                "behavior": "",
                "verify": {
                    "method": "other",
                    "command": "N/A",
                    "evidence": "",
                },
            }
        )
        write(malformed)
        general = dev_spec_validators.check_dev_spec_acceptance_criteria_present(
            fixture.root
        )[0]
        locked = (
            spec_lock_validators.check_dev_spec_locked_required_fields_strict(
                fixture.root
            )[0]
        )
        for expected in (
            "duplicated",
            "behavior must be a non-empty string",
            "verify.method",
            "N/A only with a reason",
            "verify.evidence",
        ):
            self.assertTrue(any(expected in finding for finding in general), general)
            self.assertTrue(any(expected in finding for finding in locked), locked)

        legacy = {
            key: value
            for key, value in v18.items()
            if key != "capsule_version"
        }
        legacy["target_release"] = "1.7.0"
        legacy["target_stream"] = None
        legacy["acceptance_criteria"] = ["Legacy behavior remains accepted."]
        write(legacy)
        self.assertEqual(
            dev_spec_validators.check_dev_spec_required_fields(fixture.root)[0],
            [],
        )
        self.assertEqual(
            dev_spec_validators.check_dev_spec_acceptance_criteria_present(
                fixture.root
            )[0],
            [],
        )
        self.assertEqual(
            spec_lock_validators.check_dev_spec_locked_required_fields_strict(
                fixture.root
            )[0],
            [],
        )

        del legacy["target_release"]
        write(legacy)
        self.assertTrue(
            any(
                "target_release" in finding
                for finding in dev_spec_validators.check_dev_spec_required_fields(
                    fixture.root
                )[0]
            )
        )
        self.assertTrue(
            any(
                "target_release" in finding
                for finding in spec_lock_validators.check_dev_spec_locked_required_fields_strict(
                    fixture.root
                )[0]
            )
        )

    def test_pilot_companions_expose_the_complete_capsule_birth_shape(self) -> None:
        for type_name in PILOTS:
            with self.subTest(type_name=type_name):
                leg = template_leg.load_mint_template(ROOT, type_name)
                stamped = template_leg.stamp(
                    leg,
                    uid=FIXED_UIDS[type_name],
                    date="2026-08-03",
                    author="human",
                    activation_uid=None,
                )
                frontmatter = _frontmatter(stamped)
                self.assertTrue(
                    PILOT_REQUIRED_FRONTMATTER[type_name].issubset(frontmatter),
                    PILOT_REQUIRED_FRONTMATTER[type_name] - set(frontmatter),
                )
                self.assertEqual(
                    set(leg.required_sections()),
                    PILOT_REQUIRED_SECTIONS[type_name],
                )
                required = template_leg.REQUIRED_PLACEHOLDER_RE.findall(stamped)
                if type_name == "note":
                    self.assertEqual(required, [])
                    self.assertIn("<!-- OPTIONAL:", stamped)
                else:
                    self.assertGreater(len(required), 0)
                if type_name == "dev-spec":
                    self.assertNotIn("target_release", frontmatter)
                    self.assertNotIn("target_stream", frontmatter)
                    self.assertEqual(
                        set(frontmatter["acceptance_criteria"][0]),
                        {"id", "behavior", "verify"},
                    )

    def test_registry_generation_is_deterministic_sorted_and_duplicate_free(self) -> None:
        first = generator.build_registry_bytes(ROOT)
        second = generator.build_registry_bytes(ROOT)
        self.assertEqual(first, second)
        registry = json.loads(first)
        type_names = [row["type"] for row in registry["types"]]
        self.assertEqual(type_names, sorted(type_names))
        self.assertEqual(len(type_names), len(set(type_names)))
        self.assertEqual(
            [
                row["type"]
                for row in registry["types"]
                if row["mint_mode"] == "human"
            ],
            ["design-brief", "dev-spec", "note", "task"],
        )
        modes = {row["type"]: row["mint_mode"] for row in registry["types"]}
        self.assertEqual(modes["activation"], "disabled")
        self.assertEqual(modes["test-spec"], "disabled")
        self.assertEqual(registry["schema_version"], 2)
        self.assertEqual(registry["generated_by"], "argus-a144")
        self.assertEqual((ROOT / template_leg.MINT_REGISTRY_REL).read_bytes(), first)

    def test_duplicate_registry_type_is_refused(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        path = fixture.root / template_leg.MINT_REGISTRY_REL
        registry = json.loads(path.read_text(encoding="utf-8"))
        registry["types"].append(dict(registry["types"][0]))
        path.write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaisesRegex(template_leg.TemplateLegError, "duplicate type"):
            template_leg.load_mint_registry(fixture.root)

    def test_list_types_exposes_only_bound_companions(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TOOLS / "tropo-mint-id.py"), "--list-types"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["design-brief", "dev-spec", "note", "task"],
        )

    def test_each_pilot_mints_the_exact_companion_with_only_universal_tokens(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        author = "argus-a-phase1"
        output_dir = fixture.workspace / "pilot-mints"

        for type_name in PILOTS:
            with self.subTest(type_name=type_name):
                uid = FIXED_UIDS[type_name]
                template_path = (
                    fixture.root
                    / "vault"
                    / "capsules"
                    / "templates"
                    / f"{type_name}.template.md"
                )
                raw_template = template_path.read_text(encoding="utf-8")
                self.assertEqual(
                    set(template_leg.MINT_TOKEN_RE.findall(raw_template)),
                    {
                        "uid",
                        "date",
                        "author",
                        "capsule_version",
                        "activation_uid",
                    },
                )
                leg = template_leg.load_mint_template(fixture.root, type_name)
                expected = template_leg.stamp(
                    leg,
                    uid=uid,
                    date="2026-08-03",
                    author=author,
                    activation_uid=None,
                )
                with mock.patch.object(mint, "mint", return_value=[uid]), mock.patch.object(
                    mint._dt, "date", FixedDate
                ):
                    minted_uid, path = mint.mint_file(
                        type_name,
                        author=author,
                        studio_root=fixture.root,
                        output_dir=output_dir,
                        freshen=False,
                    )
                self.assertEqual(minted_uid, uid)
                self.assertEqual(path, output_dir / f"{uid}.md")
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text, expected)
                self.assertEqual(template_leg.find_stray_mint_tokens(text), [])

                fm = _frontmatter(text)
                self.assertEqual(fm["uid"], uid)
                self.assertEqual(fm["type"], type_name)
                self.assertEqual(fm["capsule_version"], leg.capsule_version)

    def test_missing_registry_unknown_and_non_mintable_types_refuse_before_write(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        scratch = fixture.workspace / "refusals"
        (fixture.root / template_leg.MINT_REGISTRY_REL).unlink()
        with self.assertRaisesRegex(template_leg.TemplateLegError, "registry is missing"):
            mint.mint_file(
                "note",
                author="argus",
                studio_root=fixture.root,
                output_dir=scratch,
                freshen=False,
            )
        self.assertFalse(scratch.exists())

        fixture.refresh_registry()
        with self.assertRaisesRegex(template_leg.TemplateLegError, "unknown type"):
            mint.mint_file(
                "not-a-type",
                author="argus",
                studio_root=fixture.root,
                output_dir=scratch,
                freshen=False,
            )
        with self.assertRaisesRegex(template_leg.TemplateLegError, "mint_mode 'disabled'"):
            mint.mint_file(
                "test-spec",
                author="argus",
                studio_root=fixture.root,
                output_dir=scratch,
                freshen=False,
            )
        self.assertFalse(scratch.exists())

    def test_stale_registry_refuses_listing_and_minting(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        note_capsule = fixture.root / "vault" / "capsules" / "tropo-note.capsule.md"
        note_capsule.write_text(
            note_capsule.read_text(encoding="utf-8") + "\n<!-- drift -->\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(template_leg.TemplateLegError, "registry.*stale"):
            template_leg.list_mintable_types(fixture.root)
        with self.assertRaisesRegex(template_leg.TemplateLegError, "registry.*stale"):
            template_leg.load_mint_template(fixture.root, "note")

        fixture.close()
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        task_template = (
            fixture.root / "vault" / "capsules" / "templates" / "task.template.md"
        )
        task_template.write_text(
            task_template.read_text(encoding="utf-8") + "\n<!-- drift -->\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(template_leg.TemplateLegError, "companion hash drift"):
            template_leg.load_mint_template(fixture.root, "task")

    def test_missing_companion_never_falls_back_to_embedded_template(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        (
            fixture.root / "vault" / "capsules" / "templates" / "task.template.md"
        ).unlink()
        with self.assertRaisesRegex(template_leg.TemplateLegError, "is missing"):
            template_leg.load_mint_template(fixture.root, "task")

    def test_canonical_transaction_refusal_leaves_source_absent(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        uid = "44444444"
        refused = mock.Mock()
        refused.freshen_many.return_value = 1
        with mock.patch.object(mint, "mint", return_value=[uid]), mock.patch.object(
            mint, "_load_rebuild_index", return_value=refused
        ):
            with self.assertRaisesRegex(RuntimeError, "all derived surfaces remain unchanged"):
                mint.mint_file(
                    "note",
                    author="human-test",
                    studio_root=fixture.root,
                )
        self.assertFalse((fixture.root / "vault" / "files" / f"{uid}.md").exists())
        self.assertFalse(mint._derived_uid_present(fixture.root, uid))
        staged = refused.freshen_many.call_args.kwargs["source_replacements"]
        self.assertEqual(staged.keys(), {fixture.root / "vault" / "files" / f"{uid}.md"})

    def test_create_only_collision_refuses_inside_freshen_lock(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        uid = "44444445"
        path = fixture.root / "vault/files" / f"{uid}.md"
        original = b"existing governed source\n"
        path.write_bytes(original)
        freshener = mint._load_rebuild_index(ROOT)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = freshener.freshen_many(
                (uid,),
                fixture.root,
                source_replacements={path: b"replacement must not land\n"},
                require_absent_sources=(path,),
            )
        self.assertEqual(code, 1)
        self.assertIn("mint collision inside index lock", stderr.getvalue())
        self.assertEqual(path.read_bytes(), original)

    def test_exact_token_set_rejects_unknown_and_missing_tokens(self) -> None:
        for replacement, expected in (
            (
                ("<<MINT:activation_uid>>", "<<MINT:surprise>>"),
                "unknown.*missing",
            ),
            (("<<MINT:activation_uid>>", "null"), "missing"),
        ):
            with self.subTest(expected=expected):
                fixture = MintFixture()
                self.addCleanup(fixture.close)
                template = (
                    fixture.root
                    / "vault/capsules/templates/note.template.md"
                )
                template.write_text(
                    template.read_text(encoding="utf-8").replace(*replacement),
                    encoding="utf-8",
                )
                capsule = (
                    fixture.root / "vault/capsules/tropo-note.capsule.md"
                )
                text = capsule.read_text(encoding="utf-8")
                text = re.sub(
                    r"mint_template_sha256: [0-9a-f]{64}",
                    f"mint_template_sha256: {hashlib.sha256(template.read_bytes()).hexdigest()}",
                    text,
                    count=1,
                )
                capsule.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(
                    template_leg.TemplateLegError, expected
                ):
                    template_leg.build_mint_registry_bytes(fixture.root)

    def test_malformed_mint_token_forms_are_refused(self) -> None:
        for malformed in (
            "<<MINT:UID>>",
            "<<MINT:uid-extra>>",
            "<<MINT:>>",
            "<<MINT:uid>",
        ):
            with self.subTest(malformed=malformed):
                fixture = MintFixture()
                self.addCleanup(fixture.close)
                template = (
                    fixture.root
                    / "vault/capsules/templates/note.template.md"
                )
                template.write_text(
                    template.read_text(encoding="utf-8").replace(
                        "<<MINT:uid>>", malformed, 1
                    ),
                    encoding="utf-8",
                )
                capsule = (
                    fixture.root / "vault/capsules/tropo-note.capsule.md"
                )
                text = capsule.read_text(encoding="utf-8")
                text = re.sub(
                    r"mint_template_sha256: [0-9a-f]{64}",
                    f"mint_template_sha256: {hashlib.sha256(template.read_bytes()).hexdigest()}",
                    text,
                    count=1,
                )
                capsule.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(
                    template_leg.TemplateLegError, "malformed mint token"
                ):
                    template_leg.build_mint_registry_bytes(fixture.root)

    def test_yaml_safe_author_and_null_human_provenance(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        author = 'human: [unsafe] # "quoted"'
        with mock.patch.object(mint, "mint", return_value=["55555555"]):
            _uid, path = mint.mint_file(
                "note",
                author=author,
                studio_root=fixture.root,
                output_dir=fixture.workspace / "yaml-safe",
                freshen=False,
            )
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        self.assertIn(author, fm.values())
        self.assertIn(None, fm.values())
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            mint._validate_stamped_instance(
                "---\n"
                "uid: 12345678\n"
                "type: note\n"
                "capsule_version: '3.5'\n"
                "---\n",
                uid="12345678",
                type_name="note",
                capsule_version="3.5",
            )

    def test_registered_agent_requires_matching_activation_provenance(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        registry = fixture.root / ".tropo-studio/registries/agent-registry.yaml"
        registry.parent.mkdir(parents=True)
        registry.write_text(
            "agents:\n"
            "  badge:\n"
            "    type: agent\n"
            "    name: Argus\n"
            "    generation-prefix: A\n",
            encoding="utf-8",
        )
        # UID-shaped scalars containing `e` must stay strings, never YAML
        # scientific notation.
        activation_uid = "114e8351"
        activation = fixture.root / "vault/files" / f"{activation_uid}.md"
        activation.write_text(
            "---\n"
            f"uid: {activation_uid}\n"
            "type: activation\n"
            "agent: argus\n"
            "generation: A144\n"
            "status: retired\n"
            "---\n",
            encoding="utf-8",
        )
        indexed = {
            "uid": activation_uid,
            "type": "activation",
            "agent": "argus",
            "generation": "A144",
            "status": "retired",
            "path": f"vault/files/{activation_uid}.md",
        }
        (fixture.root / "vault/00-index.jsonl").write_text(
            json.dumps(indexed) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "provide --activation-uid"):
            mint.mint_file(
                "note",
                author="argus-a144",
                studio_root=fixture.root,
                output_dir=fixture.workspace / "provenance",
                freshen=False,
            )
        with mock.patch.object(mint, "mint", return_value=["66666666"]):
            _uid, path = mint.mint_file(
                "note",
                author="argus-a144",
                activation_uid=activation_uid,
                studio_root=fixture.root,
                output_dir=fixture.workspace / "provenance",
                freshen=False,
            )
        self.assertEqual(
            _frontmatter(path.read_text(encoding="utf-8"))[
                "created_by_activation_uid"
            ],
            activation_uid,
        )
        with self.assertRaisesRegex(ValueError, "does not match author"):
            mint.mint_file(
                "note",
                author="argus-a145",
                activation_uid=activation_uid,
                studio_root=fixture.root,
                output_dir=fixture.workspace / "provenance",
                freshen=False,
            )
        source = activation.read_text(encoding="utf-8")
        activation.write_text(
            source.replace(f"uid: {activation_uid}", "uid: ffffffff", 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "does not match author"):
            mint.mint_file(
                "note",
                author="argus-a144",
                activation_uid=activation_uid,
                studio_root=fixture.root,
                output_dir=fixture.workspace / "provenance",
                freshen=False,
            )

    def test_lineage_birth_is_activation_provenance(self) -> None:
        """An agent born through tropo-lineage.py can mint under its own name.

        The lifecycle stopped creating `type: activation` entries, so demanding
        one refused every agent it produced (metis-g103, ea38581b). Lineage is
        the proof now. Asserted three ways so this cannot pass by accident:
        a recorded birth mints, an unrecorded generation still refuses, and the
        stamped provenance is honestly null rather than a borrowed uid.
        """
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        registry = fixture.root / ".tropo-studio/registries/agent-registry.yaml"
        registry.parent.mkdir(parents=True)
        registry.write_text(
            "agents:\n"
            "  badge:\n"
            "    type: agent\n"
            "    name: Metis\n"
            "    generation-prefix: G\n",
            encoding="utf-8",
        )
        lineage = fixture.root / "agents/metis/lineage.jsonl"
        lineage.parent.mkdir(parents=True)
        lineage.write_text(
            json.dumps({"t": "born", "gen": "G102", "at": "2026-08-05T00:00:00Z"})
            + "\n"
            + json.dumps({"t": "retired", "gen": "G102", "at": "2026-08-06T00:00:00Z"})
            + "\n"
            + "{ this line is not JSON and must not be fatal\n"
            + json.dumps({"t": "born", "gen": "G103", "at": "2026-08-06T13:44:49Z"})
            + "\n",
            encoding="utf-8",
        )

        with mock.patch.object(mint, "mint", return_value=["55555555"]):
            _uid, path = mint.mint_file(
                "note",
                author="metis-g103",
                studio_root=fixture.root,
                output_dir=fixture.workspace / "lineage-provenance",
                freshen=False,
            )
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(fm["captured_by"], "metis-g103")
        # Null, not a borrowed predecessor uid: there is genuinely no
        # activation entry, and inventing one would be a false record.
        self.assertIsNone(fm["created_by_activation_uid"])

        # A generation with no recorded birth is still refused -- the gate is
        # repointed, not removed.
        with self.assertRaisesRegex(ValueError, "no birth recorded"):
            mint.mint_file(
                "note",
                author="metis-g999",
                studio_root=fixture.root,
                output_dir=fixture.workspace / "lineage-provenance",
                freshen=False,
            )

        # No lineage file at all is refused too -- absence of the file must not
        # read as permission.
        lineage.unlink()
        with self.assertRaisesRegex(ValueError, "no birth recorded"):
            mint._resolve_activation_provenance(fixture.root, "metis-g103", None)

    def test_system_only_mode_has_explicit_api_and_generic_refusal(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        fixture.add_system_only_binding()
        with self.assertRaisesRegex(template_leg.TemplateLegError, "system-only"):
            template_leg.load_mint_template(fixture.root, "system-record")
        leg = template_leg.load_system_mint_template(
            fixture.root, "system-record"
        )
        text = template_leg.stamp_system_template(
            leg,
            uid="77777777",
            date="2026-08-03",
            author="lifecycle-writer",
            context={"title": "Lifecycle-owned record"},
        )
        fm = _frontmatter(text)
        self.assertEqual(fm["uid"], "77777777")
        self.assertEqual(fm["type"], "system-record")
        self.assertEqual(fm["title"], "Lifecycle-owned record")
        self.assertIsNone(fm["created_by_activation_uid"])
        with self.assertRaisesRegex(template_leg.TemplateLegError, "system-only"):
            mint.mint_file(
                "system-record",
                author="human",
                studio_root=fixture.root,
                output_dir=fixture.workspace / "system-refusal",
                freshen=False,
            )

    def test_root_escape_and_symlink_outputs_are_refused(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        with self.assertRaisesRegex(ValueError, "explicit approved Studio scratch"):
            mint.mint_file(
                "note",
                author="human",
                studio_root=fixture.root,
                output_dir=fixture.root / "scratch-by-name-is-not-approved",
                freshen=False,
            )
        with self.assertRaisesRegex(ValueError, "explicit approved Studio scratch"):
            mint.mint_file(
                "note",
                author="human",
                studio_root=fixture.root,
                output_dir=fixture.root / "vault/files",
                freshen=False,
            )
        with tempfile.TemporaryDirectory(prefix="typed-mint-outside-") as tmp:
            outside = Path(tmp)
            with self.assertRaisesRegex(ValueError, "inside the Studio root"):
                mint.mint_file(
                    "note",
                    author="human",
                    studio_root=fixture.root,
                    output_dir=outside / "scratch",
                    freshen=False,
                )
            link = fixture.workspace / "outside-link"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "inside the Studio root|symlink"):
                mint.mint_file(
                    "note",
                    author="human",
                    studio_root=fixture.root,
                    output_dir=link,
                    freshen=False,
                )
        real_scratch = fixture.workspace / "real"
        real_scratch.mkdir()
        internal_link = fixture.workspace / "internal-link"
        internal_link.symlink_to(real_scratch, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            mint.mint_file(
                "note",
                author="human",
                studio_root=fixture.root,
                output_dir=internal_link,
                freshen=False,
            )
        fixture_tools = fixture.root / "vault/tools"
        fixture_tools.mkdir()
        (fixture_tools / "tropo-rebuild-index.py").symlink_to(
            TOOLS / "tropo-rebuild-index.py"
        )
        with mock.patch.object(mint, "mint", return_value=["99999998"]):
            with self.assertRaisesRegex(RuntimeError, "unsafe.*symlink"):
                mint.mint_file(
                    "note",
                    author="human",
                    studio_root=fixture.root,
                )

    def test_symlinked_capsule_and_template_are_refused(self) -> None:
        for kind in ("capsule", "template"):
            with self.subTest(kind=kind):
                fixture = MintFixture()
                self.addCleanup(fixture.close)
                if kind == "capsule":
                    path = fixture.root / "vault/capsules/tropo-note.capsule.md"
                else:
                    path = fixture.root / "vault/capsules/templates/note.template.md"
                raw = path.read_bytes()
                outside = fixture.root / f"scratch-{kind}.md"
                outside.write_bytes(raw)
                path.unlink()
                path.symlink_to(outside)
                with self.assertRaisesRegex(
                    template_leg.TemplateLegError, "symlink"
                ):
                    template_leg.build_mint_registry_bytes(fixture.root)

    def test_disabled_legacy_verifier_refuses_symlinked_capsule(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        capsule = fixture.root / "vault/capsules/tropo-test-spec.capsule.md"
        outside = fixture.root / "scratch-test-spec.capsule.md"
        outside.write_bytes(capsule.read_bytes())
        capsule.unlink()
        capsule.symlink_to(outside)
        with self.assertRaisesRegex(template_leg.TemplateLegError, "symlink"):
            template_leg.load_verifier_template(fixture.root, "test-spec")
        findings = check_one.run_generic_mint_checks(
            "99999999", "test-spec", fixture.root
        )
        self.assertTrue(
            any(
                "TEMPLATE-BINDING" in finding and "symlink" in finding
                for finding in findings
            ),
            findings,
        )

    def test_companion_is_check_one_source_and_missing_sections_fail(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        leg = template_leg.load_mint_template(fixture.root, "task")
        verifier_leg = template_leg.load_verifier_template(
            fixture.root, "task"
        )
        self.assertEqual(verifier_leg.scaffold, leg.scaffold)
        stamped = template_leg.stamp(
            leg,
            uid="88888888",
            date="2026-08-03",
            author="human",
            activation_uid=None,
        )
        consumed = re.sub(
            r"<!--\s*REQUIRED:.*?-->",
            "filled",
            stamped,
        )
        required_sections = leg.required_sections()
        self.assertGreater(len(required_sections), 0)
        for section in required_sections:
            with self.subTest(section=section):
                planted = re.sub(
                    rf"^## {re.escape(section)}.*?(?=^## |\Z)",
                    "",
                    consumed,
                    flags=re.MULTILINE | re.DOTALL,
                )
                path = fixture.root / "vault/files/88888888.md"
                path.write_text(planted, encoding="utf-8")
                findings = check_one.run_generic_mint_checks(
                    "88888888", "task", fixture.root
                )
                self.assertTrue(
                    any(
                        "MISSING-SECTION" in finding and section in finding
                        for finding in findings
                    ),
                    findings,
                )

        path = fixture.root / "vault/files/88888888.md"
        wrong_version = re.sub(
            r"^capsule_version:\s*.*$",
            "capsule_version: '0.0'",
            consumed,
            count=1,
            flags=re.MULTILINE,
        )
        path.write_text(wrong_version, encoding="utf-8")
        findings = check_one.run_generic_mint_checks(
            "88888888", "task", fixture.root
        )
        self.assertTrue(
            any("CAPSULE-VERSION" in finding for finding in findings),
            findings,
        )

        path.write_text("---\nuid: [\n---\n", encoding="utf-8")
        findings = check_one.run_generic_mint_checks(
            "88888888", "task", fixture.root
        )
        self.assertTrue(
            any("STAMPED-YAML" in finding for finding in findings),
            findings,
        )

    def test_dev_spec_generic_verifier_catches_every_heading_and_marker(self) -> None:
        fixture = MintFixture()
        self.addCleanup(fixture.close)
        uid = "89898989"
        leg = template_leg.load_mint_template(fixture.root, "dev-spec")
        stamped = template_leg.stamp(
            leg,
            uid=uid,
            date="2026-08-03",
            author="human",
            activation_uid=None,
        )
        path = fixture.root / "vault/files" / f"{uid}.md"
        path.write_text(stamped, encoding="utf-8")

        markers = template_leg.find_required_placeholders(stamped)
        findings = check_one.run_generic_mint_checks(
            uid, "dev-spec", fixture.root
        )
        incomplete = [
            finding for finding in findings if "INCOMPLETE" in finding
        ]
        self.assertEqual(len(incomplete), len(markers), findings)
        for marker in markers:
            self.assertTrue(
                any(marker in finding for finding in incomplete),
                (marker, findings),
            )

        consumed = re.sub(
            r"<!--\s*REQUIRED:.*?-->",
            "filled",
            stamped,
        )
        self.assertEqual(
            set(leg.required_sections()),
            PILOT_REQUIRED_SECTIONS["dev-spec"],
        )
        for section in leg.required_sections():
            with self.subTest(required_section=section):
                planted, replacements = re.subn(
                    rf"^## {re.escape(section)}.*?(?=^## |\Z)",
                    "",
                    consumed,
                    count=1,
                    flags=re.MULTILINE | re.DOTALL,
                )
                self.assertEqual(replacements, 1)
                path.write_text(planted, encoding="utf-8")
                findings = check_one.run_generic_mint_checks(
                    uid, "dev-spec", fixture.root
                )
                self.assertTrue(
                    any(
                        "MISSING-SECTION" in finding
                        and section in finding
                        for finding in findings
                    ),
                    findings,
                )

        without_optional = consumed
        for section in leg.optional_sections():
            without_optional, replacements = re.subn(
                rf"^## {re.escape(section)}.*?(?=^## |\Z)",
                "",
                without_optional,
                count=1,
                flags=re.MULTILINE | re.DOTALL,
            )
            self.assertEqual(replacements, 1)
        path.write_text(without_optional, encoding="utf-8")
        findings = check_one.run_generic_mint_checks(
            uid, "dev-spec", fixture.root
        )
        self.assertFalse(
            any("MISSING-SECTION" in finding for finding in findings),
            findings,
        )

        legacy = (
            "---\n"
            f"uid: '{uid}'\n"
            "type: dev-spec\n"
            "created: '2026-08-04'\n"
            "capsule_version: '1.7'\n"
            "---\n\n"
            "# Legacy free-form dev-spec\n\n"
            "The pre-v1.8 body remains governed by its historical contract.\n"
        )
        path.write_text(legacy, encoding="utf-8")
        findings = check_one.run_generic_mint_checks(
            uid, "dev-spec", fixture.root
        )
        self.assertFalse(
            any(
                code in finding
                for finding in findings
                for code in ("MISSING-SECTION", "CAPSULE-VERSION")
            ),
            findings,
        )


class TemplateBearingScanScopeTests(unittest.TestCase):
    """The scanner must not read a capsule's own contract as an unfilled instance.

    `find_required_placeholders` and `find_stray_mint_tokens` scanned whole
    instance text with no exclusions, so every `capsule-definition` — which MUST
    show the scaffold it governs, tokens intact, or it cannot declare a contract
    at all — reported as incompletely minted. That was 228 of the shipped v1.86
    box's 235 health-check failures and 238 identical findings studio-side across
    the same 14 UIDs (metis-g105, punch list 51dc85ef item 1, 2026-08-08).

    The exclusion is by REGION and not by type. A type-wide skip would be shorter
    and would make these checks unable to fail for the one class of file they are
    most often wrong about, so the teeth test below is the point of this class.
    """

    CAPSULE = (
        "---\n"
        "uid: 'aa11bb22'\n"
        "type: capsule-definition\n"
        "---\n\n"
        "# Some Capsule\n\n"
        "Prose that legitimately discusses minting.\n\n"
        "## §Examples\n\n"
        "~~~markdown\n"
        "uid: <<MINT:uid>>\n"
        "created: <<MINT:date>>\n"
        "~~~\n\n"
        "## §Template (companion scaffold)\n\n"
        "~~~markdown\n"
        "---\n"
        "uid: <<MINT:uid>>\n"
        "author: <<MINT:author>>\n"
        "---\n\n"
        "<!-- REQUIRED: write the capture here -->\n"
        "~~~\n\n"
        "## §Changelog\n\n"
        "Nothing token-shaped down here.\n"
    )

    def test_a_capsules_template_leg_and_fences_are_not_unfilled_instances(self):
        self.assertEqual(
            template_leg.find_stray_mint_tokens(self.CAPSULE, "capsule-definition"),
            [],
        )
        self.assertEqual(
            template_leg.find_required_placeholders(self.CAPSULE, "capsule-definition"),
            [],
        )

    def test_the_same_text_without_the_type_still_reports_everything(self):
        """The control. Without this, the test above could pass on empty input.

        Same bytes, no entry type: every token must still be found, which proves
        the fixture actually contains the tokens the exclusion is suppressing.
        """
        self.assertEqual(
            len(template_leg.find_stray_mint_tokens(self.CAPSULE)), 4
        )
        self.assertEqual(
            len(template_leg.find_required_placeholders(self.CAPSULE)), 1
        )

    def test_a_real_stray_token_in_capsule_prose_still_reds(self):
        """The teeth. Metis's stated mutation for punch-list item 1.

        A token in ordinary prose — outside the template leg, outside every
        fence — is a genuine unfilled instance even in a capsule-definition, and
        the exclusion must not reach it.
        """
        leaked = self.CAPSULE.replace(
            "Prose that legitimately discusses minting.",
            "Prose that leaked <<MINT:uid>> into the body.",
        )
        self.assertEqual(
            template_leg.find_stray_mint_tokens(leaked, "capsule-definition"),
            ["<<MINT:uid>>"],
        )

        placeholder_leaked = self.CAPSULE.replace(
            "Nothing token-shaped down here.",
            "<!-- REQUIRED: someone never filled this in -->",
        )
        self.assertEqual(
            template_leg.find_required_placeholders(
                placeholder_leaked, "capsule-definition"
            ),
            ["someone never filled this in"],
        )

    def test_no_other_type_gains_the_exemption(self):
        """A note with tokens in a fence is still an unfilled instance."""
        note = self.CAPSULE.replace("type: capsule-definition", "type: note")
        self.assertEqual(len(template_leg.find_stray_mint_tokens(note, "note")), 4)
        self.assertEqual(len(template_leg.find_required_placeholders(note, "note")), 1)

    def test_an_unclosed_fence_grants_no_exemption(self):
        """A fence that never closes is malformed, not a licence.

        Otherwise one stray line of backticks in a capsule would silence the
        scanner for the whole remainder of the file.
        """
        unclosed = (
            "---\nuid: 'aa11bb22'\ntype: capsule-definition\n---\n\n"
            "# Some Capsule\n\n"
            "~~~markdown\n"
            "uid: <<MINT:uid>>\n"
        )
        self.assertEqual(
            template_leg.find_stray_mint_tokens(unclosed, "capsule-definition"),
            ["<<MINT:uid>>"],
        )

    def test_a_heading_inside_the_scaffold_does_not_end_the_template_section(self):
        """The ordering regression, and it is worth its own test.

        A scaffold is markdown inside a fence, so it contains headings — most
        real ones open with `# <!-- REQUIRED: title -->`. Searching for the end
        of the §Template section BEFORE blanking fences finds that heading and
        closes the section on its first line, leaving the entire scaffold in
        scope while looking like it worked.

        Measured on the live vault while building this: fences-second dropped
        169 of 238 findings and left 69 across 13 capsules; fences-first dropped
        all 238. Nothing in the output said which one you had — the fix simply
        under-delivered, which is why this is pinned by a test rather than by a
        comment.
        """
        capsule = (
            "---\nuid: 'cc33dd44'\ntype: capsule-definition\n---\n\n"
            "# Loop Capsule\n\n"
            "## §Template (companion scaffold)\n\n"
            "~~~markdown\n"
            "---\nuid: <<MINT:uid>>\n---\n\n"
            "# <!-- REQUIRED: title (mirror frontmatter) -->\n\n"
            "## §Purpose\n\n"
            "<!-- REQUIRED: what this loop does -->\n"
            "~~~\n\n"
            "| 0.1 | <<MINT:date>> | Initial proposal. | <<MINT:author>> |\n"
        )
        self.assertEqual(
            template_leg.find_stray_mint_tokens(capsule, "capsule-definition"), []
        )
        self.assertEqual(
            template_leg.find_required_placeholders(capsule, "capsule-definition"), []
        )
        # Control: the tokens really are in the fixture.
        self.assertEqual(len(template_leg.find_stray_mint_tokens(capsule)), 3)
        self.assertEqual(len(template_leg.find_required_placeholders(capsule)), 2)

    def test_blanking_preserves_offsets_so_findings_still_describe_the_file(self):
        scannable = template_leg.scannable_instance_text(
            self.CAPSULE, "capsule-definition"
        )
        self.assertEqual(len(scannable), len(self.CAPSULE))
        self.assertEqual(scannable.count("\n"), self.CAPSULE.count("\n"))


if __name__ == "__main__":
    unittest.main()
