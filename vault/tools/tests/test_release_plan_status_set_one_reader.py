#!/usr/bin/env python3
"""f015ef8ff398 step 2 (Talos's half) — the plan-status sets have ONE declared home.

The preflight's `lock-plan-record` gate carried `("locked", "active", "design")`
by hand and the lock tool carried `{"design", "specify"}` by hand. The first
lacked `specify`, the plan's correct post-walk state, and refused Mike's v1.95
ignition on it. Now both read `lib/release_capsule_contract`, whose enum is the
capsule's own Check 2 line. This suite goes red if:

  - the contract's PLAN_STATUSES and the capsule's Check 2 enum disagree
    (either side grows a value the other lacks);
  - the lock tool's LOCKABLE_STATUSES is not the contract's object;
  - LOCKABLE_STATUSES is not a subset of PLAN_STATUSES;
  - the preflight's gate accepts a status outside PLAN_STATUSES, or refuses
    `specify` (the v1.95 refusal, re-planted).

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_release_plan_status_set_one_reader
"""
from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))

from lib import release_capsule_contract as contract  # noqa: E402


def _load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, TOOLS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CAPSULE = ROOT / "vault" / "capsules" / "tropo-release-plan.capsule.md"


def _capsule_check2_enum() -> frozenset:
    text = CAPSULE.read_text(encoding="utf-8")
    m = re.search(r"^\d+\.\s+`status:`\s+∈\s+\{([^}]*)\}", text, flags=re.MULTILINE)
    assert m, "the capsule's Check 2 status enum line was not found"
    return frozenset(v.strip().strip("`") for v in m.group(1).split(","))


class OneDeclaredSet(unittest.TestCase):

    def test_the_contract_enum_is_the_capsules_check_2_verbatim(self) -> None:
        self.assertEqual(contract.PLAN_STATUSES, _capsule_check2_enum(),
                         "PLAN_STATUSES and the capsule's Check 2 disagree")

    def test_specify_is_a_plan_state(self) -> None:
        """The v1.95 refusal: the plan was at `specify`, its correct post-walk state."""
        self.assertIn("specify", contract.PLAN_STATUSES)
        self.assertIn("specify", contract.LOCKABLE_STATUSES)

    def test_lockable_is_a_subset_of_the_plan_states(self) -> None:
        self.assertTrue(contract.LOCKABLE_STATUSES <= contract.PLAN_STATUSES,
                        sorted(contract.LOCKABLE_STATUSES - contract.PLAN_STATUSES))
        self.assertNotIn("locked", contract.LOCKABLE_STATUSES, "a locked plan is not re-lockable")

    def test_the_lock_tool_reads_the_contracts_object_not_a_copy(self) -> None:
        lock = _load("tropo-lock-release-plan.py", "lock_release_plan_for_status_set")
        self.assertIs(lock.LOCKABLE_STATUSES, contract.LOCKABLE_STATUSES,
                      "the lock tool carries its own LOCKABLE_STATUSES again")

    def test_the_preflight_gate_reads_the_contract_set(self) -> None:
        """Accepts every plan state, refuses anything outside it."""
        pre = _load("tropo-release-preflight.py", "release_preflight_for_status_set")
        for status in sorted(contract.PLAN_STATUSES):
            with self.subTest(status=status):
                out = pre._lock_plan_record({"release_plan": {"uid": "b1a00001", "status": status}})
                self.assertNotIn("not a plan state", out.detail or "",
                                 f"{status!r} is in the capsule enum but the gate refuses it")
        out = pre._lock_plan_record({"release_plan": {"uid": "b1a00001", "status": "draft"}})
        self.assertIn("not a plan state", out.detail or "")
        self.assertEqual(out.verdict, pre.VERDICT_REFUSED)

    def test_no_hand_list_of_plan_states_survives_in_either_reader(self) -> None:
        """A second literal set is how the two readers grew apart."""
        for name in ("tropo-lock-release-plan.py", "tropo-release-preflight.py"):
            source = (TOOLS / name).read_text(encoding="utf-8")
            self.assertNotRegex(source, r'\("locked",\s*"active",\s*"design"\)', name)
            self.assertNotRegex(source, r'LOCKABLE_STATUSES\s*=\s*\{', name)


if __name__ == "__main__":
    unittest.main()
