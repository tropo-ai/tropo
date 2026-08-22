"""v1.89 lifecycle pairing gate — AC1 declaration contract.

Dev-spec 271d28d7, activation 7a47c089.  Every case here drives the production
loader against real capsule bytes written to an isolated tree; none asserts on
the source text of the implementation.  The mutation cases exist because a
declaration parser that cannot be made to refuse is not a parser.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(STUDIO_ROOT / "vault" / "tools"))

from lib import lifecycle_machine as lm  # noqa: E402
from lib import lifecycle_pairing as lp  # noqa: E402

REQUIRED_TYPES = ("arch-spec", "design-brief", "dev-spec", "project", "task", "test-spec")

# The matrix locked in 271d28d7 §Capsule declaration.  Written out longhand so a
# silent edit to a production capsule has to disagree with something.
LOCKED_MATRIX = {
    "project": {"terminal": {"done", "cancelled"}, "source": "machine", "archived": {"done", "cancelled"}},
    "task": {"terminal": {"closed"}, "source": "machine", "archived": {"closed"}},
    "dev-spec": {"terminal": {"done"}, "source": "fallback", "archived": "any"},
    "design-brief": {"terminal": {"done"}, "source": "fallback", "archived": "any"},
    "test-spec": {"terminal": {"done"}, "source": "fallback", "archived": "any"},
    "arch-spec": {"terminal": {"locked", "done"}, "source": "fallback", "archived": "any"},
}

_MACHINE_CAPSULE = """---
uid: aaaa1111
name: widget
type: capsule-definition
version: '1.0'
status: active
{pairing}enforced_enums:
  status:
    - open
    - closed
  state:
    - active
    - archived
meta_status_rollup:
  in-progress:
    - open
  done:
    - closed
lifecycle_machine:
  field: status
  optional: false
  states:
    - {{value: open, label: Open, terminal: false}}
    - {{value: closed, label: Closed, terminal: true}}
  moves:
    - {{move_id: close, from: open, to: closed, label: Close, direction: forward,
       confirm: false, resolution: null, gate: null, warning: null,
       principal_only: false, legacy_default: false}}
---

# widget
"""

_PLAIN_CAPSULE = """---
uid: bbbb2222
name: gadget
type: capsule-definition
version: '1.0'
status: active
{pairing}enforced_enums:
  status:
    canonical:
      - draft
      - done
    aliases:
      finished: done
  state:
    - active
    - archived
---

# gadget
"""


def _pairing_block(body: str) -> str:
    return "lifecycle_pairing:\n" + body if body else ""


class _CapsuleTree:
    """An isolated studio holding exactly the capsules a case needs."""

    def __init__(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="t44-pairing-")
        self.root = Path(self._tmp)
        (self.root / "vault" / "capsules").mkdir(parents=True)

    def write(self, type_name: str, template: str, pairing_body: str) -> Path:
        path = self.root / "vault" / "capsules" / "tropo-{}.capsule.md".format(type_name)
        path.write_text(template.format(pairing=_pairing_block(pairing_body)), encoding="utf-8")
        return path

    def cleanup(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)


class PairingDeclarationTests(unittest.TestCase):
    """AC1 — the declaration contract, proven against the production loader."""

    def setUp(self) -> None:
        self.tree = _CapsuleTree()
        self.addCleanup(self.tree.cleanup)

    # -- the six production declarations -----------------------------------

    def test_all_six_production_declarations_load(self) -> None:
        pairings = lp.load_lifecycle_pairings(STUDIO_ROOT)
        for type_name in REQUIRED_TYPES:
            self.assertIn(type_name, pairings, "{} declares no lifecycle_pairing".format(type_name))

    def test_production_declarations_match_the_locked_matrix(self) -> None:
        pairings = lp.load_lifecycle_pairings(STUDIO_ROOT)
        for type_name, expected in LOCKED_MATRIX.items():
            pairing = pairings[type_name]
            self.assertEqual(set(pairing.terminal_statuses), expected["terminal"], type_name)
            self.assertEqual(pairing.terminal_source, expected["source"], type_name)
            if expected["archived"] == "any":
                self.assertTrue(pairing.archived_allows_any, type_name)
            else:
                self.assertFalse(pairing.archived_allows_any, type_name)
                self.assertEqual(
                    set(pairing.archived_allowed_statuses), expected["archived"], type_name
                )

    def test_q1_removed_status_archived_from_test_spec_and_arch_spec(self) -> None:
        for type_name in ("test-spec", "arch-spec"):
            capsule = STUDIO_ROOT / "vault" / "capsules" / "tropo-{}.capsule.md".format(type_name)
            canonical, _ = lm.canonical_enum_for_field(capsule, "status")
            self.assertNotIn(
                "archived",
                canonical,
                "{} still declares archived as an intrinsic status".format(type_name),
            )

    def test_undeclared_type_is_absent_rather_than_defaulted(self) -> None:
        self.tree.write("widget", _MACHINE_CAPSULE, "")
        pairings = lp.load_lifecycle_pairings(self.tree.root)
        self.assertEqual(pairings, {})

    # -- terminality has exactly one authority ------------------------------

    def test_machine_supplies_terminality_and_forbids_a_fallback(self) -> None:
        path = self.tree.write("widget", _MACHINE_CAPSULE, "  archived_state_allowed_statuses: [closed]\n")
        pairing = lp.parse_capsule_lifecycle_pairing(path)
        self.assertEqual(pairing.terminal_source, "machine")
        self.assertEqual(set(pairing.terminal_statuses), {"closed"})

        path = self.tree.write(
            "widget",
            _MACHINE_CAPSULE,
            "  terminal_statuses: [closed]\n  archived_state_allowed_statuses: [closed]\n",
        )
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("forbidden when lifecycle_machine exists", str(caught.exception))

    def test_machineless_capsule_requires_a_fallback(self) -> None:
        path = self.tree.write("gadget", _PLAIN_CAPSULE, "  archived_state_allowed_statuses: any\n")
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("required when the capsule declares no lifecycle_machine", str(caught.exception))

    # -- values resolve through the capsule's own enum ----------------------

    def test_alias_resolves_to_canon_and_collides_with_it(self) -> None:
        path = self.tree.write(
            "gadget", _PLAIN_CAPSULE, "  terminal_statuses: [finished]\n  archived_state_allowed_statuses: any\n"
        )
        pairing = lp.parse_capsule_lifecycle_pairing(path)
        self.assertEqual(set(pairing.terminal_statuses), {"done"})
        self.assertEqual(pairing.raw_terminal_statuses, ("finished",))

        path = self.tree.write(
            "gadget",
            _PLAIN_CAPSULE,
            "  terminal_statuses: [done, finished]\n  archived_state_allowed_statuses: any\n",
        )
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("duplicate", str(caught.exception))

    def test_unknown_status_in_a_declaration_is_refused(self) -> None:
        path = self.tree.write(
            "gadget",
            _PLAIN_CAPSULE,
            "  terminal_statuses: [shipped]\n  archived_state_allowed_statuses: any\n",
        )
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("not a canonical status or alias", str(caught.exception))

    # -- the closed shape ---------------------------------------------------

    def test_unknown_key_is_refused(self) -> None:
        path = self.tree.write(
            "gadget",
            _PLAIN_CAPSULE,
            "  terminal_statuses: [done]\n  archived_state_allowed_statuses: any\n  archived_state_forbidden: [draft]\n",
        )
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("closed block", str(caught.exception))

    def test_missing_archived_declaration_is_refused(self) -> None:
        path = self.tree.write("gadget", _PLAIN_CAPSULE, "  terminal_statuses: [done]\n")
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("is required", str(caught.exception))

    def test_empty_list_is_refused(self) -> None:
        path = self.tree.write(
            "gadget", _PLAIN_CAPSULE, "  terminal_statuses: []\n  archived_state_allowed_statuses: any\n"
        )
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("non-empty list", str(caught.exception))

    def test_non_string_member_is_refused(self) -> None:
        path = self.tree.write(
            "gadget", _PLAIN_CAPSULE, "  terminal_statuses: [7]\n  archived_state_allowed_statuses: any\n"
        )
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("non-empty string", str(caught.exception))

    def test_wildcard_is_scalar_only_and_never_a_terminal(self) -> None:
        path = self.tree.write(
            "gadget",
            _PLAIN_CAPSULE,
            "  terminal_statuses: [done]\n  archived_state_allowed_statuses: [any]\n",
        )
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("legal only as the scalar", str(caught.exception))

        path = self.tree.write(
            "gadget",
            _PLAIN_CAPSULE,
            "  terminal_statuses: any\n  archived_state_allowed_statuses: any\n",
        )
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("must be a list", str(caught.exception))

    def test_unrecognized_scalar_archived_value_is_refused(self) -> None:
        path = self.tree.write(
            "gadget",
            _PLAIN_CAPSULE,
            "  terminal_statuses: [done]\n  archived_state_allowed_statuses: all\n",
        )
        with self.assertRaises(lp.LifecyclePairingError) as caught:
            lp.parse_capsule_lifecycle_pairing(path)
        self.assertIn("scalar form must be", str(caught.exception))

    def test_duplicate_declaration_keys_are_refused(self) -> None:
        path = self.tree.write(
            "gadget",
            _PLAIN_CAPSULE,
            "  terminal_statuses: [done]\n  terminal_statuses: [draft]\n  archived_state_allowed_statuses: any\n",
        )
        with self.assertRaises(lp.LifecyclePairingError):
            lp.parse_capsule_lifecycle_pairing(path)

    # -- the shared resolver ------------------------------------------------

    def test_one_resolver_maps_capsule_filename_to_governed_type(self) -> None:
        self.assertEqual(
            lm.capsule_type_from_filename(Path("vault/capsules/tropo-project.capsule.md")),
            "project",
        )
        # The bug this resolver exists to kill: keying `tropo-project` while
        # source entries carry `type: project` checked zero entries silently.
        self.assertNotEqual(
            lm.capsule_type_from_filename(Path("vault/capsules/tropo-project.capsule.md")),
            "tropo-project",
        )

    def test_loaded_type_names_match_source_type_values(self) -> None:
        pairings = lp.load_lifecycle_pairings(STUDIO_ROOT)
        for type_name in REQUIRED_TYPES:
            self.assertEqual(pairings[type_name].type_name, type_name)
            self.assertFalse(pairings[type_name].type_name.startswith("tropo-"))

    # -- the contract digest ------------------------------------------------

    def test_contract_digest_is_stable_and_moves_with_the_contract(self) -> None:
        path = self.tree.write(
            "gadget", _PLAIN_CAPSULE, "  terminal_statuses: [done]\n  archived_state_allowed_statuses: any\n"
        )
        first = lp.parse_capsule_lifecycle_pairing(path).contract_sha256
        self.assertEqual(first, lp.parse_capsule_lifecycle_pairing(path).contract_sha256)

        path = self.tree.write(
            "gadget", _PLAIN_CAPSULE, "  terminal_statuses: [done]\n  archived_state_allowed_statuses: [done]\n"
        )
        self.assertNotEqual(first, lp.parse_capsule_lifecycle_pairing(path).contract_sha256)

    # -- orthogonality, at the declaration layer ----------------------------

    def test_terminal_status_with_state_active_is_never_a_violation(self) -> None:
        pairing = lp.load_lifecycle_pairings(STUDIO_ROOT)["task"]
        self.assertIsNone(
            lp.evaluate_record(
                pairing, uid="aaaa0001", path="vault/files/aaaa0001.md",
                raw_status="closed", state="active",
            )
        )

    def test_declared_archived_pair_is_permitted_and_undeclared_one_is_not(self) -> None:
        pairing = lp.load_lifecycle_pairings(STUDIO_ROOT)["task"]
        self.assertIsNone(
            lp.evaluate_record(
                pairing, uid="aaaa0002", path="vault/files/aaaa0002.md",
                raw_status="closed", state="archived",
            )
        )
        violation = lp.evaluate_record(
            pairing, uid="aaaa0003", path="vault/files/aaaa0003.md",
            raw_status="active", state="archived",
        )
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, lp.RULE_ARCHIVED_NOT_ALLOWED)
        self.assertEqual(violation.canonical_status, "active")

    def test_unknown_source_status_reports_null_canonical_rather_than_passing(self) -> None:
        # A150's ruling: the row is recorded with canonical_status null so the
        # census stays complete and strict-zero fails; it never passes, and it
        # never downgrades enum enforcement.
        pairing = lp.load_lifecycle_pairings(STUDIO_ROOT)["task"]
        violation = lp.evaluate_record(
            pairing, uid="aaaa0004", path="vault/files/aaaa0004.md",
            raw_status="archived", state="archived",
        )
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, lp.RULE_UNKNOWN_STATUS)
        self.assertIsNone(violation.canonical_status)
        self.assertEqual(violation.raw_status, "archived")
        self.assertIsNone(violation.as_row()["canonical_status"])


_PAIRED_CAPSULE = """---
uid: eeee4444
name: {type_name}
type: capsule-definition
version: '1.0'
status: active
lifecycle_pairing:
  terminal_statuses: [done]
  archived_state_allowed_statuses: [done]
enforced_enums:
  status:
    - draft
    - done
  state:
    - active
    - archived
---

# {type_name}
"""

_PAIRED_ENTRY = """---
uid: {uid}
type: {type_name}
title: probe
status: {status}
state: {state}
owner: talos
created: '2026-08-16'
modified: '2026-08-16'
schema_version: 2
---

# probe
"""


class PairingJsonGateTests(unittest.TestCase):
    """AC3 — the machine surface, in the half that severity cannot move."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="t44-json-")
        self.root = Path(self._tmp)
        (self.root / "vault" / "capsules").mkdir(parents=True)
        (self.root / "vault" / "files").mkdir(parents=True)
        # resolve_vault_root() accepts a tree only if it has both vault/ and
        # .tropo/, so a fixture without it fails at argument resolution and
        # never reaches the mode under test.
        (self.root / ".tropo").mkdir()
        self.addCleanup(shutil.rmtree, self._tmp, True)

    def _capsule(self, type_name: str = "widget") -> None:
        (self.root / "vault" / "capsules" / "tropo-{}.capsule.md".format(type_name)).write_text(
            _PAIRED_CAPSULE.format(type_name=type_name), encoding="utf-8"
        )

    def _entry(self, uid: str, status: str, state: str, type_name: str = "widget") -> None:
        (self.root / "vault" / "files" / "{}.md".format(uid)).write_text(
            _PAIRED_ENTRY.format(uid=uid, type_name=type_name, status=status, state=state),
            encoding="utf-8",
        )

    def test_document_carries_the_closed_schema(self) -> None:
        self._capsule()
        report = lp.build_report(self.root)
        self.assertEqual(
            set(report),
            {"schema_version", "mode", "complete", "gate_pass", "declarations",
             "counts", "violations", "baselines", "errors"},
        )
        self.assertEqual(set(report["declarations"]),
                         {"required_types", "loaded_types", "missing_types", "coverage"})
        self.assertEqual(set(report["counts"]),
                         {"pairing_violations", "enum_violations",
                          "pairing_known_debt", "enum_known_debt",
                          "new_pairing_failures", "new_enum_failures",
                          "stale_pairing_baseline_rows", "stale_enum_baseline_rows",
                          "errors"})
        self.assertEqual(set(report["baselines"]),
                         {"pairing", "enum", "creation_commit", "census_sha256"})
        for side in ("pairing", "enum"):
            self.assertEqual(set(report["baselines"][side]),
                             {"present", "contract_sha256", "row_count", "stale_rows"},
                             side)
        self.assertEqual(report["schema_version"], lp.SCHEMA_VERSION)

    def test_document_is_json_serializable_and_stable_across_runs(self) -> None:
        self._capsule()
        self._entry("aaaa1001", "draft", "archived")
        first = json.dumps(lp.build_report(self.root), sort_keys=True)
        second = json.dumps(lp.build_report(self.root), sort_keys=True)
        self.assertEqual(first, second)

    def test_violations_are_ordered_by_path_then_uid(self) -> None:
        # Feeding the document deliberately unordered rows, because the scan
        # walks sorted(glob) and would satisfy this assertion by accident: the
        # first version of this case passed with the sort deleted.
        self._capsule()
        unordered = [
            lp.PairingViolation(uid=u, path="vault/files/{}.md".format(u),
                                type_name="widget", raw_status="draft",
                                canonical_status="draft", state="archived",
                                rule_id=lp.RULE_ARCHIVED_NOT_ALLOWED,
                                contract_sha256="0" * 64)
            for u in ("cccc0003", "aaaa0001", "bbbb0002")
        ]
        original = lp.scan_source_pairings
        lp.scan_source_pairings = lambda root, pairings=None: {
            "loaded": {"widget": original(root)["loaded"]["widget"]},
            "coverage": {"widget": {"discovered": 3, "checked": 3}},
            "violations": unordered,
            "errors": [],
        }
        try:
            rows = lp.build_report(self.root, required_types=("widget",))["violations"]
        finally:
            lp.scan_source_pairings = original
        self.assertEqual([r["uid"] for r in rows], ["aaaa0001", "bbbb0002", "cccc0003"])

    def test_unknown_status_serializes_canonical_null(self) -> None:
        self._capsule()
        self._entry("aaaa1002", "invented", "active")
        row = lp.build_report(self.root)["violations"][0]
        self.assertIsNone(row["canonical_status"])
        self.assertEqual(row["rule_id"], lp.RULE_UNKNOWN_STATUS)
        self.assertIn('"canonical_status": null', json.dumps(row))

    def test_complete_census_with_zero_violations_passes_the_gate(self) -> None:
        self._capsule()
        self._entry("aaaa1003", "done", "archived")
        self._entry("aaaa1004", "done", "active")
        report = lp.build_report(self.root, required_types=("widget",))
        self.assertEqual(report["counts"]["pairing_violations"], 0)
        self.assertTrue(report["gate_pass"])
        self.assertTrue(report["complete"])

    def test_violations_fail_the_gate_while_the_census_stays_complete(self) -> None:
        self._capsule()
        self._entry("aaaa1005", "draft", "archived")
        report = lp.build_report(self.root, required_types=("widget",))
        self.assertTrue(report["complete"], "the scan looked at everything it declared")
        self.assertFalse(report["gate_pass"], "and what it found is not clean")

    def test_a_nonempty_baseline_cannot_pass_the_gate(self) -> None:
        self._capsule()
        self._entry("aaaa1006", "done", "active")
        baseline = {"present": True,
                    "signatures": {"sig-a": {"signature": "sig-a"}},
                    "header": {"creation_commit": "abc123"}}
        report = lp.build_report(self.root, baseline=baseline, required_types=("widget",))
        self.assertEqual(report["counts"]["pairing_violations"], 0)
        self.assertFalse(report["gate_pass"], "known debt still means not-yet-clean")
        self.assertTrue(report["baselines"]["pairing"]["present"])
        self.assertEqual(report["baselines"]["pairing"]["row_count"], 1)
        self.assertEqual(report["counts"]["stale_pairing_baseline_rows"], 1,
                         "a baselined row that no longer occurs is stale")

    def test_missing_required_declaration_makes_the_census_incomplete(self) -> None:
        # No capsule at all: the six required types are unrepresented, and the
        # report must say so rather than reporting a clean empty world.
        report = lp.build_report(self.root)
        self.assertFalse(report["complete"])
        self.assertEqual(report["declarations"]["missing_types"], list(lp.REQUIRED_TYPES))
        self.assertTrue(
            all(e["code"] == lp.ERR_MISSING_DECLARATION for e in report["errors"])
        )
        self.assertFalse(report["gate_pass"])

    def test_unreadable_source_is_an_error_entry_not_a_crash(self) -> None:
        self._capsule()
        (self.root / "vault" / "files" / "bad00001.md").write_bytes(
            b"---\nuid: bad00001\ntype: widget\nstatus: [unclosed\n---\n"
        )
        report = lp.build_report(self.root)
        self.assertTrue(any(e["code"] == lp.ERR_UNREADABLE_SOURCE for e in report["errors"]))
        self.assertFalse(report["complete"])

    def test_duplicate_uid_is_reported(self) -> None:
        self._capsule()
        self._entry("dupe0001", "done", "active")
        (self.root / "vault" / "files" / "dupe0002.md").write_text(
            _PAIRED_ENTRY.format(uid="dupe0001", type_name="widget", status="done", state="active"),
            encoding="utf-8",
        )
        report = lp.build_report(self.root)
        self.assertTrue(any(e["code"] == lp.ERR_DUPLICATE_UID for e in report["errors"]))

    def test_census_counts_discovered_and_checked_per_type(self) -> None:
        self._capsule()
        for i in range(3):
            self._entry("eeee000{}".format(i), "done", "active")
        coverage = lp.build_report(self.root)["declarations"]["coverage"]
        self.assertEqual(coverage["widget"], {"discovered": 3, "checked": 3})

    def _all_required_capsules(self) -> None:
        """Declare every production-required type.

        The CLI has no required-types override and should not: the production
        set is fixed. So a fixture that declares one invented type is correctly
        reported as an incomplete census, and any case exercising the modes'
        clean path has to declare the real six.
        """
        for name in lp.REQUIRED_TYPES:
            self._capsule(name)

    def _cli(self, *flags: str, root: Path = None):
        """Run the real validator CLI, because AC3 is a command contract."""
        import subprocess

        proc = subprocess.run(
            [sys.executable, str(STUDIO_ROOT / "vault" / "tools" / "tropo-validate.py"),
             "--vault-path", str(root if root is not None else self.root), *flags],
            capture_output=True, text=True, timeout=600,
        )
        return proc

    def test_report_mode_stdout_is_one_json_document_and_nothing_else(self) -> None:
        self._all_required_capsules()
        self._entry("aaaa2001", "draft", "archived", type_name="task")
        proc = self._cli("--state-pairing-json")
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        document = json.loads(proc.stdout)  # would raise on any human chatter
        self.assertEqual(document["mode"], "report")
        self.assertEqual(document["schema_version"], lp.SCHEMA_VERSION)

    def test_report_mode_exits_zero_even_when_it_reports_violations(self) -> None:
        # Report mode answers "did the evaluation complete", not "is it clean".
        self._all_required_capsules()
        self._entry("aaaa2002", "draft", "archived", type_name="task")
        proc = self._cli("--state-pairing-json")
        self.assertEqual(proc.returncode, 0)
        self.assertGreater(json.loads(proc.stdout)["counts"]["pairing_violations"], 0)

    def test_strict_mode_exits_one_on_violations(self) -> None:
        self._all_required_capsules()
        self._entry("aaaa2003", "draft", "archived", type_name="task")
        proc = self._cli("--require-state-pairing-zero")
        self.assertEqual(proc.returncode, 1, proc.stdout[:300])
        self.assertEqual(json.loads(proc.stdout)["mode"], "require-zero")

    def test_incomplete_census_exits_two_in_both_modes(self) -> None:
        # No capsule: the required production types are undeclared, which is a
        # malformed/incomplete evaluation rather than a clean world.
        for flag in ("--state-pairing-json", "--require-state-pairing-zero"):
            proc = self._cli(flag)
            self.assertEqual(proc.returncode, 2, flag)
            self.assertFalse(json.loads(proc.stdout)["complete"], flag)

    def test_the_two_modes_are_mutually_exclusive(self) -> None:
        proc = self._cli("--state-pairing-json", "--require-state-pairing-zero")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("mutually exclusive", proc.stderr)

    def test_modes_refuse_to_combine_with_other_flags(self) -> None:
        for flag in ("--release", "--customer", "--thorough"):
            proc = self._cli("--state-pairing-json", flag)
            self.assertEqual(proc.returncode, 2, flag)
            self.assertIn("composes only with --vault-path", proc.stderr)
        proc = self._cli("--state-pairing-json", "--write-fingerprints")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--write-fingerprints", proc.stderr)

    def test_the_production_studio_reports_a_complete_census(self) -> None:
        report = lp.build_report(STUDIO_ROOT)
        self.assertEqual(report["declarations"]["missing_types"], [])
        self.assertTrue(report["complete"], report["errors"][:3])
        for name in lp.REQUIRED_TYPES:
            counts = report["declarations"]["coverage"][name]
            self.assertEqual(counts["discovered"], counts["checked"], name)


def _load_validator():
    """Import the validator script by path (its filename is not importable)."""
    import importlib.util

    path = STUDIO_ROOT / "vault" / "tools" / "tropo-validate.py"
    spec = importlib.util.spec_from_file_location("t44_tropo_validate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ENUM_CAPSULE = """---
uid: cccc3333
name: widget
type: capsule-definition
version: '1.0'
status: active
enforced_enums:
  status:
    - open
    - closed
---

# widget
"""

_ENTRY = """---
uid: {uid}
type: widget
title: probe
status: {status}
state: active
owner: talos
created: '2026-08-16'
modified: '2026-08-16'
schema_version: 2
---

# probe
"""


class PairingRatchetTests(unittest.TestCase):
    """AC2 — the enum check may never pass vacuously again."""

    def setUp(self) -> None:
        self.tv = _load_validator()
        self._tmp = tempfile.mkdtemp(prefix="t44-coverage-")
        self.root = Path(self._tmp)
        (self.root / "vault" / "capsules").mkdir(parents=True)
        (self.root / "vault" / "files").mkdir(parents=True)
        (self.root / "vault" / "capsules" / "tropo-widget.capsule.md").write_text(
            _ENUM_CAPSULE, encoding="utf-8"
        )
        for i, status in enumerate(("open", "closed", "wildly-invented"), start=1):
            (self.root / "vault" / "files" / f"dddd000{i}.md").write_text(
                _ENTRY.format(uid=f"dddd000{i}", status=status), encoding="utf-8"
            )
        self.addCleanup(shutil.rmtree, self._tmp, True)

    def test_resolver_maps_capsule_filename_to_the_type_entries_declare(self) -> None:
        resolved = self.tv._capsule_type_from_filename(
            Path("vault/capsules/tropo-widget.capsule.md")
        )
        self.assertEqual(resolved, "widget")

    def test_compliance_examines_a_nonzero_corpus(self) -> None:
        _, checked, errors, _ = self.tv.check_enforced_enum_compliance(self.root)
        self.assertEqual(checked, 3, "the three planted entries must be examined")
        self.assertEqual(errors, 1, "only the invented status is drift")

    def test_unknown_status_still_errors_and_is_never_downgraded(self) -> None:
        # A150's separation: pairing may account for a row as known debt, but
        # enum enforcement keeps calling an unknown status an ERROR.
        findings, _, errors, _ = self.tv.check_enforced_enum_compliance(self.root)
        self.assertEqual(errors, 1)
        self.assertTrue(
            any("wildly-invented" in f and "[ERROR]" in f for f in findings),
            findings,
        )

    def test_coverage_gate_passes_when_the_corpus_is_examined(self) -> None:
        findings, types, defects = self.tv.check_enforced_enum_coverage(self.root)
        self.assertEqual(types, 1)
        self.assertEqual(defects, 0, findings)

    def test_coverage_gate_fires_on_the_vacuous_pass(self) -> None:
        # The causal plant: reintroduce the exact resolver bug and the gate must
        # refuse, because '0 entries checked' and 'everything is fine' printed
        # the same PASS for months.
        original = self.tv._capsule_type_from_filename
        self.tv._capsule_type_from_filename = lambda p: p.name.split(".capsule.md")[0]
        try:
            _, checked, _, _ = self.tv.check_enforced_enum_compliance(self.root)
            self.assertEqual(checked, 0, "the plant must reproduce the silent skip")
            findings, _, defects = self.tv.check_enforced_enum_coverage(self.root)
            self.assertEqual(defects, 1, "the gate must catch a vacuous pass")
            self.assertTrue(any("vacuously" in f for f in findings), findings)
        finally:
            self.tv._capsule_type_from_filename = original

        _, checked, _, _ = self.tv.check_enforced_enum_compliance(self.root)
        self.assertEqual(checked, 3, "control: the gate is green once repaired")

    def test_empty_studio_is_legal_rather_than_a_coverage_defect(self) -> None:
        empty = Path(tempfile.mkdtemp(prefix="t44-empty-"))
        self.addCleanup(shutil.rmtree, empty, True)
        (empty / "vault" / "capsules").mkdir(parents=True)
        (empty / "vault" / "files").mkdir(parents=True)
        (empty / "vault" / "capsules" / "tropo-widget.capsule.md").write_text(
            _ENUM_CAPSULE, encoding="utf-8"
        )
        findings, types, defects = self.tv.check_enforced_enum_coverage(empty)
        self.assertEqual(types, 1)
        self.assertEqual(defects, 0, "zero discovered with zero checked is a fresh Studio")


class GardenerDivergenceTests(unittest.TestCase):
    """AC5 — the Gardener reads the same law, and never gains closure authority."""

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(STUDIO_ROOT / "vault" / "tools"))
        from lib import gardener as gardener_module

        cls.g = gardener_module
        cls.pairings = lp.load_lifecycle_pairings(STUDIO_ROOT)

    def _provenance(self, **over):
        base = {
            "judge_policy_uid": "341823aa",
            "judge_version": "2.1.0",
            "normalized_body_sha256": "a" * 64,
        }
        base.update(over)
        return base

    # -- the contradiction signal now reads capsule law ---------------------

    def test_terminal_and_visible_is_no_longer_a_contradiction(self) -> None:
        # The locked Closure Page says a done record may remain the current
        # reference. The old global logic called that stale.
        for type_name, pairing in self.pairings.items():
            for status in sorted(pairing.terminal_statuses):
                self.assertIsNone(
                    self.g.signal_lifecycle_contradiction(
                        {"type": type_name, "status": status, "state": "active"},
                        self.pairings,
                    ),
                    "{} {} + active".format(type_name, status),
                )

    def test_an_illegal_declared_pair_is_a_contradiction(self) -> None:
        signal = self.g.signal_lifecycle_contradiction(
            {"type": "project", "status": "evergreen", "state": "archived"},
            self.pairings,
        )
        self.assertEqual(signal, "status:evergreen on state:archived")

    def test_an_undeclared_type_is_unchecked_not_defaulted(self) -> None:
        self.assertIsNone(
            self.g.signal_lifecycle_contradiction(
                {"type": "note", "status": "open", "state": "archived"}, self.pairings
            )
        )

    def test_without_the_law_the_signal_declines_rather_than_guesses(self) -> None:
        self.assertIsNone(
            self.g.signal_lifecycle_contradiction(
                {"type": "project", "status": "evergreen", "state": "archived"}, {}
            )
        )

    # -- the derived candidate ---------------------------------------------

    def test_open_status_with_a_current_terminal_verdict_yields_a_candidate(self) -> None:
        candidate = self.g.derive_closure_review_candidate(
            {"type": "task", "status": "active"}, self.pairings["task"],
            "finished", **self._provenance()
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["source"], self.g.CLOSURE_REVIEW_SOURCE)
        self.assertEqual(candidate["verdict"], "finished")
        self.assertEqual(candidate["status"], "active")
        self.assertEqual(candidate["judge_policy_uid"], "341823aa")
        self.assertEqual(candidate["normalized_body_sha256"], "a" * 64)

    def test_terminal_records_get_no_candidate(self) -> None:
        self.assertIsNone(
            self.g.derive_closure_review_candidate(
                {"type": "task", "status": "closed"}, self.pairings["task"],
                "finished", **self._provenance()
            )
        )

    def test_a_stale_or_absent_verdict_gets_no_candidate(self) -> None:
        for verdict in (None, "", "current", "unknown-verdict"):
            self.assertIsNone(
                self.g.derive_closure_review_candidate(
                    {"type": "task", "status": "active"}, self.pairings["task"],
                    verdict, **self._provenance()
                ),
                repr(verdict),
            )

    def test_a_current_human_keep_override_suppresses_the_candidate(self) -> None:
        self.assertIsNone(
            self.g.derive_closure_review_candidate(
                {"type": "task", "status": "active"}, self.pairings["task"],
                "finished", **self._provenance(), override_current=True
            )
        )

    def test_provenance_is_required_for_a_contestable_claim(self) -> None:
        for missing in ("judge_policy_uid", "judge_version", "normalized_body_sha256"):
            self.assertIsNone(
                self.g.derive_closure_review_candidate(
                    {"type": "task", "status": "active"}, self.pairings["task"],
                    "finished", **self._provenance(**{missing: None})
                ),
                missing,
            )

    def test_every_pass_clears_stale_candidates_before_recompute(self) -> None:
        records = [
            {"uid": "aaaa0001", self.g.CLOSURE_REVIEW_KEY: {"verdict": "finished"}},
            {"uid": "aaaa0002"},
            {"uid": "aaaa0003", self.g.CLOSURE_REVIEW_KEY: {"verdict": "abandoned"}},
        ]
        self.assertEqual(self.g.clear_closure_review_candidates(records), 2)
        for record in records:
            self.assertNotIn(self.g.CLOSURE_REVIEW_KEY, record)

    def test_source_declared_candidate_is_spoofing(self) -> None:
        self.assertTrue(
            self.g.source_declared_closure_candidate(
                {"uid": "aaaa0004", self.g.CLOSURE_REVIEW_KEY: {"verdict": "finished"}}
            )
        )
        self.assertFalse(self.g.source_declared_closure_candidate({"uid": "aaaa0004"}))

    def test_the_candidate_is_review_evidence_and_never_authority(self) -> None:
        # The record carries no field a transition API could read as permission:
        # no approval, no authorization, no closer identity, no target status.
        candidate = self.g.derive_closure_review_candidate(
            {"type": "task", "status": "active"}, self.pairings["task"],
            "finished", **self._provenance()
        )
        forbidden = {"approved", "approved_by", "authorized", "authorization",
                     "closed_by", "close", "new_status", "transition", "signed_by"}
        self.assertEqual(set(candidate) & forbidden, set(), candidate)
        self.assertIn("reason", candidate)

    def test_deriving_a_candidate_does_not_mutate_the_source_record(self) -> None:
        record = {"type": "task", "status": "active", "uid": "aaaa0005"}
        before = json.dumps(record, sort_keys=True)
        self.g.derive_closure_review_candidate(
            record, self.pairings["task"], "finished", **self._provenance()
        )
        self.assertEqual(json.dumps(record, sort_keys=True), before)


class PairingSemanticsTests(unittest.TestCase):
    """AC4 — orthogonality: the archived direction is constrained, nothing else."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pairings = lp.load_lifecycle_pairings(STUDIO_ROOT)

    def _verdict(self, type_name: str, status: str, state: str):
        return lp.evaluate_record(
            self.pairings[type_name],
            uid="aaaa9000", path="vault/files/aaaa9000.md",
            raw_status=status, state=state,
        )

    def test_terminal_status_with_state_active_is_legal_for_every_type(self) -> None:
        # A done record that is still the current reference is not a
        # contradiction. Treating it as one is the folklore this replaces.
        for type_name, pairing in self.pairings.items():
            for status in sorted(pairing.terminal_statuses):
                self.assertIsNone(
                    self._verdict(type_name, status, "active"),
                    "{}: {} + active must be legal".format(type_name, status),
                )

    def test_project_evergreen_and_active_cannot_be_archived(self) -> None:
        for status in ("evergreen", "active"):
            violation = self._verdict("project", status, "archived")
            self.assertIsNotNone(violation, status)
            self.assertEqual(violation.rule_id, lp.RULE_ARCHIVED_NOT_ALLOWED)
            self.assertEqual(violation.canonical_status, status)

    def test_project_done_and_cancelled_may_be_archived(self) -> None:
        for status in ("done", "cancelled"):
            self.assertIsNone(self._verdict("project", status, "archived"), status)

    def test_task_open_states_cannot_be_archived_but_closed_can(self) -> None:
        for status in ("new", "accepted", "active"):
            violation = self._verdict("task", status, "archived")
            self.assertIsNotNone(violation, status)
            self.assertEqual(violation.rule_id, lp.RULE_ARCHIVED_NOT_ALLOWED)
        self.assertIsNone(self._verdict("task", "closed", "archived"))

    def test_spec_types_permit_visibility_retirement_at_any_status(self) -> None:
        # Mike's Q1 ruling: archival is a visibility move, so a stale draft
        # retires as a draft rather than being marked done.
        for type_name in ("dev-spec", "design-brief", "test-spec", "arch-spec"):
            pairing = self.pairings[type_name]
            self.assertTrue(pairing.archived_allows_any, type_name)
            for status in pairing.canonical_statuses:
                self.assertIsNone(
                    self._verdict(type_name, status, "archived"),
                    "{}: {} + archived must be visibility retirement".format(
                        type_name, status),
                )

    def test_test_spec_and_arch_spec_no_longer_accept_status_archived(self) -> None:
        for type_name in ("test-spec", "arch-spec"):
            self.assertNotIn("archived", self.pairings[type_name].canonical_statuses)
            violation = self._verdict(type_name, "archived", "active")
            self.assertIsNotNone(violation, type_name)
            self.assertEqual(violation.rule_id, lp.RULE_UNKNOWN_STATUS)
            self.assertIsNone(violation.canonical_status)

    def test_design_brief_alias_resolves_before_the_pairing_verdict(self) -> None:
        # 'closed' is a declared alias for 'done'; the verdict must judge the
        # canonical value, not the surface string.
        pairing = self.pairings["design-brief"]
        self.assertEqual(pairing.canonicalize("closed"), "done")
        self.assertIsNone(self._verdict("design-brief", "closed", "archived"))

    def test_removing_a_declaration_changes_the_verdict(self) -> None:
        # The mutation the spec names: without the declaration there is no law
        # to apply, so the type falls out of the checked set entirely.
        tmp = Path(tempfile.mkdtemp(prefix="t44-ac4-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "vault" / "capsules").mkdir(parents=True)
        source = STUDIO_ROOT / "vault" / "capsules" / "tropo-task.capsule.md"
        text = source.read_text(encoding="utf-8")
        stripped = text.replace(
            "lifecycle_pairing:\n  archived_state_allowed_statuses: [closed]\n", "", 1
        )
        self.assertNotEqual(text, stripped, "the plant must actually remove the block")
        (tmp / "vault" / "capsules" / "tropo-task.capsule.md").write_text(
            stripped, encoding="utf-8"
        )
        self.assertEqual(lp.load_lifecycle_pairings(tmp), {})

    def test_one_global_terminal_set_would_be_wrong_for_these_types(self) -> None:
        # Substituting a single shared terminal set is the folklore the spec
        # forbids: no one set is correct across the six.
        observed = {name: frozenset(p.terminal_statuses)
                    for name, p in self.pairings.items()}
        self.assertGreater(len(set(observed.values())), 1,
                           "types genuinely disagree about terminality")
        for candidate in set(observed.values()):
            mismatched = [n for n, t in observed.items() if t != candidate]
            self.assertTrue(mismatched,
                            "no single terminal set fits every type: {}".format(observed))


class StrictZeroFixtureTests(unittest.TestCase):
    """AC3 — strict-zero's refusal matrix, each case proving its exact exit code."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="t44-strict-")
        self.root = Path(self._tmp)
        (self.root / "vault" / "capsules").mkdir(parents=True)
        (self.root / "vault" / "files").mkdir(parents=True)
        (self.root / ".tropo").mkdir()
        self.addCleanup(shutil.rmtree, self._tmp, True)

    def _declare_all(self, pairing_body: str = None) -> None:
        for name in lp.REQUIRED_TYPES:
            text = _PAIRED_CAPSULE.format(type_name=name)
            if pairing_body is not None:
                text = text.replace(
                    "lifecycle_pairing:\n"
                    "  terminal_statuses: [done]\n"
                    "  archived_state_allowed_statuses: [done]\n",
                    pairing_body,
                    1,
                )
            (self.root / "vault" / "capsules" / "tropo-{}.capsule.md".format(name)).write_text(
                text, encoding="utf-8"
            )

    def _entry(self, uid: str, status: str, state: str, type_name: str = "task") -> None:
        (self.root / "vault" / "files" / "{}.md".format(uid)).write_text(
            _PAIRED_ENTRY.format(uid=uid, type_name=type_name, status=status, state=state),
            encoding="utf-8",
        )

    def _cli(self, *flags: str):
        import subprocess

        return subprocess.run(
            [sys.executable, str(STUDIO_ROOT / "vault" / "tools" / "tropo-validate.py"),
             "--vault-path", str(self.root), *flags],
            capture_output=True, text=True, timeout=600,
        )

    def test_an_isolated_clean_fixture_passes_strict_zero_end_to_end(self) -> None:
        self._declare_all()
        self._entry("bbbb0001", "done", "archived")
        self._entry("bbbb0002", "draft", "active")
        proc = self._cli("--require-state-pairing-zero")
        self.assertEqual(proc.returncode, 0, proc.stdout[:400] + proc.stderr[:400])
        document = json.loads(proc.stdout)
        self.assertTrue(document["gate_pass"])
        self.assertTrue(document["complete"])
        self.assertEqual(document["counts"]["pairing_violations"], 0)

    def test_a_violation_exits_one(self) -> None:
        self._declare_all()
        self._entry("bbbb0003", "draft", "archived")
        proc = self._cli("--require-state-pairing-zero")
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(json.loads(proc.stdout)["gate_pass"])

    def test_a_missing_declaration_exits_two(self) -> None:
        # Only five of the six required types declared: an incomplete census is
        # not a clean world, and must not be reported as one.
        self._declare_all()
        (self.root / "vault" / "capsules" / "tropo-task.capsule.md").unlink()
        proc = self._cli("--require-state-pairing-zero")
        self.assertEqual(proc.returncode, 2)
        document = json.loads(proc.stdout)
        self.assertIn("task", document["declarations"]["missing_types"])
        self.assertFalse(document["complete"])

    def test_a_malformed_declaration_exits_two(self) -> None:
        self._declare_all(
            pairing_body="lifecycle_pairing:\n  terminal_statuses: [done]\n"
                         "  archived_state_allowed_statuses: [done]\n  bogus_key: 1\n"
        )
        proc = self._cli("--require-state-pairing-zero")
        self.assertEqual(proc.returncode, 2, proc.stdout[:300])
        self.assertFalse(json.loads(proc.stdout)["complete"])

    def test_unreadable_yaml_exits_two(self) -> None:
        self._declare_all()
        (self.root / "vault" / "files" / "bbbb0004.md").write_text(
            "---\nuid: bbbb0004\ntype: task\nstatus: [unterminated\n---\n", encoding="utf-8"
        )
        proc = self._cli("--require-state-pairing-zero")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(
            any(e["code"] == lp.ERR_UNREADABLE_SOURCE
                for e in json.loads(proc.stdout)["errors"])
        )

    def test_a_duplicate_uid_exits_two(self) -> None:
        self._declare_all()
        self._entry("bbbb0005", "done", "active")
        (self.root / "vault" / "files" / "bbbb0006.md").write_text(
            _PAIRED_ENTRY.format(uid="bbbb0005", type_name="task", status="done", state="active"),
            encoding="utf-8",
        )
        proc = self._cli("--require-state-pairing-zero")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(
            any(e["code"] == lp.ERR_DUPLICATE_UID
                for e in json.loads(proc.stdout)["errors"])
        )

    def test_report_mode_never_exits_one_where_strict_does(self) -> None:
        # The modes differ only in verdict, never in what they observed: same
        # census, same violations, different exit contract.
        self._declare_all()
        self._entry("bbbb0007", "draft", "archived")
        report = self._cli("--state-pairing-json")
        strict = self._cli("--require-state-pairing-zero")
        self.assertEqual((report.returncode, strict.returncode), (0, 1))
        a, b = json.loads(report.stdout), json.loads(strict.stdout)
        self.assertEqual(a["violations"], b["violations"])
        self.assertEqual(a["declarations"]["coverage"], b["declarations"]["coverage"])
        self.assertEqual((a["mode"], b["mode"]), ("report", "require-zero"))


class StableAcIdPairingTests(unittest.TestCase):
    """AC8 — v1.8 criteria pair by stable AC ID; integers stay legacy-only."""

    @classmethod
    def setUpClass(cls) -> None:
        scripts = STUDIO_ROOT / ".tropo" / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from lib import dev_spec_validators, test_spec_validators

        cls.dsv = dev_spec_validators
        cls.tsv = test_spec_validators

    def test_the_capsule_template_emits_a_stable_id_not_an_integer(self) -> None:
        capsule = (STUDIO_ROOT / "vault" / "capsules" / "tropo-test-spec.capsule.md").read_text()
        # Anchored at line start: the frontmatter quotes the heading name while
        # explaining template_enforced_from, and an unanchored search lands
        # there instead — the same class of mistake this whole AC is about.
        heading = re.search(r"^## §Template", capsule, re.MULTILINE)
        self.assertIsNotNone(heading, "the capsule must carry a §Template leg")
        # Bounded by the scaffold's own fence: running to end-of-file swept in
        # changelog rows that merely NAME the field, which is not the scaffold.
        fenced = re.search(r"^~~~\w*\n(.*?)^~~~", capsule[heading.start():],
                           re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(fenced, "the §Template leg must carry a fenced scaffold")
        template = fenced.group(1)
        pointer_lines = [
            line for line in template.splitlines()
            if "verifies_acceptance_criterion" in line
        ]
        self.assertTrue(pointer_lines, "the template must scaffold the pointer")
        for line in pointer_lines:
            self.assertNotRegex(
                line, r"verifies_acceptance_criterion:\s*\d+\s*$",
                "the scaffold teaches the pointer shape; an integer teaches the legacy one",
            )
            self.assertIn("AC1", line)

    def test_a_stable_id_matches_the_declared_pattern(self) -> None:
        for good in ("AC1", "AC2", "AC10"):
            self.assertRegex(good, self.dsv.AC_ID_RE)
        for bad in ("AC0", "ac1", "AC", "1", "AC1a", ""):
            self.assertNotRegex(bad, self.dsv.AC_ID_RE, bad)

    def test_the_locked_spec_declares_stable_ids_and_is_v18(self) -> None:
        import yaml

        text = (STUDIO_ROOT / "vault" / "files" / "271d28d7.md").read_text()
        frontmatter = yaml.safe_load(re.match(r"\A---\n(.*?)\n---", text, re.DOTALL).group(1))
        self.assertTrue(self.dsv.is_v18_dev_spec(frontmatter))
        ids = [c.get("id") for c in frontmatter["acceptance_criteria"]]
        self.assertEqual(ids, ["AC{}".format(n) for n in range(1, len(ids) + 1)])
        for ac_id in ids:
            self.assertRegex(ac_id, self.dsv.AC_ID_RE)

    def test_the_frozen_legacy_cohort_is_closed_and_untouched(self) -> None:
        # The amendment changes the scaffold, never an instance. Every live
        # test-spec still pairing by integer must be paired to a pre-v1.8
        # dev-spec, or the cohort is not frozen and this is a migration.
        import yaml

        def frontmatter(uid):
            path = STUDIO_ROOT / "vault" / "files" / "{}.md".format(uid)
            if not path.is_file():
                return None
            match = re.match(r"\A---\n(.*?)\n---", path.read_text(errors="replace"), re.DOTALL)
            if not match:
                return None
            try:
                return yaml.safe_load(match.group(1))
            except Exception:
                return None

        offenders = []
        for path in (STUDIO_ROOT / "vault" / "files").glob("*.md"):
            data = frontmatter(path.stem)
            if not isinstance(data, dict) or data.get("type") != "test-spec":
                continue
            integers = [
                behavior.get("verifies_acceptance_criterion")
                for behavior in (data.get("behaviors_covered") or [])
                if isinstance(behavior, dict)
                and isinstance(behavior.get("verifies_acceptance_criterion"), int)
            ]
            if not integers:
                continue
            dev_uid = (data.get("verifies_dev_spec") or data.get("triggered_by_dev_cycle")
                       or data.get("dev_spec_uid"))
            dev = frontmatter(dev_uid) if dev_uid else None
            if dev and self.dsv.is_v18_dev_spec(dev):
                offenders.append(path.stem)
        self.assertEqual(offenders, [], "these pair by integer against a v1.8 dev-spec")


class SourceImmutabilityTests(unittest.TestCase):
    """AC7 — nothing in this package writes to governed source, and one verdict serves both doors."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="t44-immutable-")
        self.root = Path(self._tmp)
        (self.root / "vault" / "capsules").mkdir(parents=True)
        (self.root / "vault" / "files").mkdir(parents=True)
        (self.root / ".tropo").mkdir()
        for name in lp.REQUIRED_TYPES:
            (self.root / "vault" / "capsules" / "tropo-{}.capsule.md".format(name)).write_text(
                _PAIRED_CAPSULE.format(type_name=name), encoding="utf-8"
            )
        self._entry("f00d0001", "draft", "archived")
        self._entry("f00d0002", "done", "active")
        self.addCleanup(shutil.rmtree, self._tmp, True)

    def _entry(self, uid: str, status: str, state: str, type_name: str = "task") -> None:
        (self.root / "vault" / "files" / "{}.md".format(uid)).write_text(
            _PAIRED_ENTRY.format(uid=uid, type_name=type_name, status=status, state=state),
            encoding="utf-8",
        )

    def _snapshot(self) -> dict:
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((self.root / "vault").rglob("*.md"))
        }

    def _cli(self, *flags: str):
        import subprocess

        return subprocess.run(
            [sys.executable, str(STUDIO_ROOT / "vault" / "tools" / "tropo-validate.py"),
             "--vault-path", str(self.root), *flags],
            capture_output=True, text=True, timeout=600,
        )

    def test_the_scan_does_not_touch_source(self) -> None:
        before = self._snapshot()
        lp.scan_source_pairings(self.root)
        lp.build_report(self.root)
        self.assertEqual(self._snapshot(), before)

    def test_report_and_strict_modes_do_not_touch_source(self) -> None:
        before = self._snapshot()
        self._cli("--state-pairing-json")
        self._cli("--require-state-pairing-zero")
        self.assertEqual(self._snapshot(), before)

    def test_baseline_capture_and_comparison_do_not_touch_source(self) -> None:
        before = self._snapshot()
        lp.write_pairing_baseline(self.root)
        lp.build_report(self.root)
        lp.write_pairing_baseline(self.root)
        self.assertEqual(self._snapshot(), before, "a baseline writes its own file only")

    def test_a_gardener_pass_does_not_touch_source(self) -> None:
        sys.path.insert(0, str(STUDIO_ROOT / "vault" / "tools"))
        from lib import gardener

        before = self._snapshot()
        records = [
            {"uid": "f00d0001", "type": "task", "status": "draft", "state": "archived",
             "path": "vault/files/f00d0001.md"},
            {"uid": "f00d0002", "type": "task", "status": "done", "state": "active",
             "path": "vault/files/f00d0002.md"},
        ]
        gardener.apply_gardener_pass(self.root, records, False)
        self.assertEqual(self._snapshot(), before)

    def test_source_declared_closure_candidate_is_rejected(self) -> None:
        self.assertTrue(
            lp.CLOSURE_REVIEW_KEY_PRESENT({"uid": "x", lp.CLOSURE_REVIEW_KEY: {}})
        )
        self.assertFalse(lp.CLOSURE_REVIEW_KEY_PRESENT({"uid": "x"}))

    def test_one_engine_serves_the_targeted_and_full_verdicts(self) -> None:
        # A stale or absent index row must not change the answer: both doors
        # read the source through the same evaluator.
        pairing = lp.load_lifecycle_pairings(self.root)["task"]
        source_verdict = lp.evaluate_record(
            pairing, uid="f00d0001", path="vault/files/f00d0001.md",
            raw_status="draft", state="archived",
        )
        report = lp.build_report(self.root)
        reported = [row for row in report["violations"] if row["uid"] == "f00d0001"]
        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0]["rule_id"], source_verdict.rule_id)
        self.assertEqual(reported[0]["canonical_status"], source_verdict.canonical_status)

    def test_the_verdict_is_identical_with_no_index_present_at_all(self) -> None:
        # There is no index in this fixture; the scan still reaches a verdict,
        # because it reads vault/files directly rather than trusting a row.
        self.assertFalse((self.root / "vault" / "00-index.jsonl").exists())
        report = lp.build_report(self.root)
        self.assertEqual(report["counts"]["pairing_violations"], 1)
        self.assertTrue(report["complete"])


class PairingDebtBaselineTests(unittest.TestCase):
    """The pairing baseline: separate from enum debt, shrink-only, never amnesty."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="t44-pairbase-")
        self.root = Path(self._tmp)
        (self.root / "vault" / "capsules").mkdir(parents=True)
        (self.root / "vault" / "files").mkdir(parents=True)
        (self.root / ".tropo").mkdir()
        for name in lp.REQUIRED_TYPES:
            (self.root / "vault" / "capsules" / "tropo-{}.capsule.md".format(name)).write_text(
                _PAIRED_CAPSULE.format(type_name=name), encoding="utf-8"
            )
        self.addCleanup(shutil.rmtree, self._tmp, True)

    def _entry(self, uid: str, status: str, state: str, type_name: str = "task") -> None:
        (self.root / "vault" / "files" / "{}.md".format(uid)).write_text(
            _PAIRED_ENTRY.format(uid=uid, type_name=type_name, status=status, state=state),
            encoding="utf-8",
        )

    def test_absent_baseline_calls_every_violation_new(self) -> None:
        self._entry("eeee0001", "draft", "archived")
        report = lp.build_report(self.root)
        self.assertEqual(report["counts"]["new_pairing_failures"], 1)
        self.assertEqual(report["counts"]["pairing_known_debt"], 0)
        self.assertFalse(report["baselines"]["pairing"]["present"])

    def test_captured_rows_become_known_debt(self) -> None:
        self._entry("eeee0002", "draft", "archived")
        messages, code = lp.write_pairing_baseline(self.root)
        self.assertEqual(code, 0, messages)
        report = lp.build_report(self.root)
        self.assertEqual(report["counts"]["pairing_known_debt"], 1)
        self.assertEqual(report["counts"]["new_pairing_failures"], 0)
        self.assertEqual(report["violations"][0]["baseline_disposition"], "known")

    def test_a_new_violation_after_capture_is_new(self) -> None:
        self._entry("eeee0003", "draft", "archived")
        lp.write_pairing_baseline(self.root)
        self._entry("eeee0004", "draft", "archived")
        report = lp.build_report(self.root)
        self.assertEqual(report["counts"]["new_pairing_failures"], 1)
        self.assertEqual(report["counts"]["pairing_known_debt"], 1)

    def test_the_writer_refuses_to_grow(self) -> None:
        self._entry("eeee0005", "draft", "archived")
        lp.write_pairing_baseline(self.root)
        self._entry("eeee0006", "draft", "archived")
        messages, code = lp.write_pairing_baseline(self.root)
        self.assertEqual(code, 1, messages)
        self.assertTrue(any("refusing to grow" in m for m in messages))

    def test_a_fixed_row_shows_as_stale_until_the_baseline_shrinks(self) -> None:
        self._entry("eeee0007", "draft", "archived")
        lp.write_pairing_baseline(self.root)
        (self.root / "vault" / "files" / "eeee0007.md").unlink()
        report = lp.build_report(self.root)
        self.assertEqual(report["counts"]["stale_pairing_baseline_rows"], 1)
        messages, code = lp.write_pairing_baseline(self.root)
        self.assertEqual(code, 0, messages)
        self.assertEqual(
            lp.build_report(self.root)["counts"]["stale_pairing_baseline_rows"], 0
        )

    def test_the_two_baselines_are_counted_separately(self) -> None:
        self._entry("eeee0008", "draft", "archived")
        lp.write_pairing_baseline(self.root)
        report = lp.build_report(
            self.root,
            enum_summary={"present": True, "row_count": 7, "violations": 3,
                          "known_debt": 3, "new_failures": 0,
                          "contract_sha256": "f" * 64, "stale_rows": []},
        )
        counts = report["counts"]
        self.assertEqual(counts["pairing_known_debt"], 1)
        self.assertEqual(counts["enum_known_debt"], 3)
        self.assertEqual(report["baselines"]["pairing"]["row_count"], 1)
        self.assertEqual(report["baselines"]["enum"]["row_count"], 7)
        self.assertNotEqual(
            report["baselines"]["pairing"]["contract_sha256"],
            report["baselines"]["enum"]["contract_sha256"],
        )

    def test_known_debt_on_either_side_still_fails_the_gate(self) -> None:
        # Both baselines empty is part of gate_pass: known debt means the
        # cleanup is unfinished however clean today's scan looks.
        self._entry("eeee0009", "done", "archived")  # legal pair, no violation
        report = lp.build_report(
            self.root,
            enum_summary={"present": True, "row_count": 1, "violations": 0,
                          "known_debt": 0, "new_failures": 0,
                          "contract_sha256": "", "stale_rows": []},
        )
        self.assertEqual(report["counts"]["pairing_violations"], 0)
        self.assertFalse(report["gate_pass"], "a non-empty enum baseline blocks the gate")

    def test_capture_refuses_on_an_incomplete_census(self) -> None:
        (self.root / "vault" / "files" / "bad00002.md").write_text(
            "---\nuid: bad00002\ntype: task\nstatus: [unterminated\n---\n", encoding="utf-8"
        )
        messages, code = lp.write_pairing_baseline(self.root)
        self.assertEqual(code, 2, messages)
        self.assertFalse((self.root / lp.PAIRING_BASELINE_RELATIVE_PATH).exists())


class EnumDebtBaselineTests(unittest.TestCase):
    """The bounded amendment: known debt warns, anything new still errors."""

    def setUp(self) -> None:
        self.tv = _load_validator()
        self._tmp = tempfile.mkdtemp(prefix="t44-debt-")
        self.root = Path(self._tmp)
        (self.root / "vault" / "capsules").mkdir(parents=True)
        (self.root / "vault" / "files").mkdir(parents=True)
        (self.root / ".tropo").mkdir()
        (self.root / "vault" / "capsules" / "tropo-widget.capsule.md").write_text(
            _ENUM_CAPSULE, encoding="utf-8"
        )
        self.addCleanup(shutil.rmtree, self._tmp, True)

    def _entry(self, uid: str, status: str) -> None:
        (self.root / "vault" / "files" / f"{uid}.md").write_text(
            _ENTRY.format(uid=uid, status=status), encoding="utf-8"
        )

    def _capture(self) -> None:
        messages, code = self.tv.write_enum_debt_baseline(self.root)
        self.assertEqual(code, 0, messages)

    def test_absent_baseline_excuses_nothing(self) -> None:
        self._entry("dddd1001", "invented")
        _, _, errors, _ = self.tv.check_enforced_enum_compliance(self.root)
        self.assertEqual(errors, 1, "no baseline means no amnesty")

    def test_captured_signature_warns_instead_of_erroring(self) -> None:
        self._entry("dddd1002", "invented")
        self._capture()
        findings, _, errors, warns = self.tv.check_enforced_enum_compliance(self.root)
        self.assertEqual(errors, 0)
        self.assertEqual(warns, 1)
        self.assertTrue(any("known enum debt" in f for f in findings), findings)

    def test_a_new_signature_still_errors_after_capture(self) -> None:
        self._entry("dddd1003", "invented")
        self._capture()
        self._entry("dddd1004", "freshly-wrong")
        findings, _, errors, _ = self.tv.check_enforced_enum_compliance(self.root)
        self.assertEqual(errors, 1)
        self.assertTrue(any("freshly-wrong" in f and "[ERROR]" in f for f in findings))

    def test_the_same_bad_value_on_a_new_file_is_still_known_debt(self) -> None:
        # The signature is the drift, not the file: the sweep fixes values, and
        # a per-uid key would error on every rename during the cleanup.
        self._entry("dddd1005", "invented")
        self._capture()
        self._entry("dddd1006", "invented")
        _, _, errors, warns = self.tv.check_enforced_enum_compliance(self.root)
        self.assertEqual(errors, 0)
        self.assertEqual(warns, 2)

    def test_writer_refuses_to_grow_the_baseline(self) -> None:
        self._entry("dddd1007", "invented")
        self._capture()
        self._entry("dddd1008", "a-second-invention")
        messages, code = self.tv.write_enum_debt_baseline(self.root)
        self.assertEqual(code, 1, messages)
        self.assertTrue(any("refusing to grow" in m for m in messages), messages)

    def test_writer_accepts_a_shrink(self) -> None:
        self._entry("dddd1009", "invented")
        self._entry("dddd1010", "also-invented")
        self._capture()
        (self.root / "vault" / "files" / "dddd1010.md").unlink()
        messages, code = self.tv.write_enum_debt_baseline(self.root)
        self.assertEqual(code, 0, messages)
        remaining = self.tv.load_enum_debt_baseline(self.root)
        self.assertEqual(len(remaining["signatures"]), 1)

    def test_widening_the_enum_retires_the_row_rather_than_absolving_it(self) -> None:
        # The property worth having: the signature carries the enum's contract
        # hash, so widening the vocabulary invalidates the baseline row instead
        # of silently making the violation disappear as if someone decided it.
        self._entry("dddd1011", "invented")
        self._capture()
        before = set(self.tv.load_enum_debt_baseline(self.root)["signatures"])

        capsule = self.root / "vault" / "capsules" / "tropo-widget.capsule.md"
        capsule.write_text(
            _ENUM_CAPSULE.replace("    - closed\n", "    - closed\n    - invented\n"),
            encoding="utf-8",
        )
        _, _, errors, warns = self.tv.check_enforced_enum_compliance(self.root)
        self.assertEqual((errors, warns), (0, 0), "the value is canonical now")

        messages, code = self.tv.write_enum_debt_baseline(self.root)
        self.assertEqual(code, 0, messages)
        after = set(self.tv.load_enum_debt_baseline(self.root)["signatures"])
        self.assertEqual(after, set(), "the widened contract retires the stale row")
        self.assertNotEqual(before, after)

    def test_a_malformed_baseline_refuses_rather_than_silently_excusing(self) -> None:
        (self.root / ".tropo" / "enum-debt-baseline.json").write_text(
            "{not json", encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            self.tv.load_enum_debt_baseline(self.root)

    def test_coverage_gate_is_unaffected_by_the_baseline(self) -> None:
        self._entry("dddd1012", "invented")
        self._capture()
        _, _, defects = self.tv.check_enforced_enum_coverage(self.root)
        self.assertEqual(defects, 0, "severity never touches whether the check looked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
