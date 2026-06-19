#!/usr/bin/env python3
"""test_meta_validator_v1_58.py — Lane V Layer 3 regression tests (M.1 per spec 8e2f1a47 §9).

Tests:
  §9.1 — v1.55 empirical lifecycle case (canonical positive test)
  §9.2 — Parser edge cases
  §9.3 — AST parser edge cases
  §9.4 — Negative tests (no false-fails)
"""
from __future__ import annotations
import sys, tempfile
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(VAULT_ROOT / ".tropo" / "scripts"))
from lib.meta_validators import (
    parse_capsule_schema, parse_validator_implementation, compare,
    SchemaDecls, ImplDecls,
)


def write_temp(dir_path: Path, filename: str, content: str) -> Path:
    p = dir_path / filename
    p.write_text(content, encoding="utf-8")
    return p


def test_9_1_v1_55_lifecycle_canonical() -> bool:
    """§9.1 — The v1.55 empirical case: lifecycle enum drift is caught."""
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)

        # Synthetic capsule with correct lifecycle declaration
        capsule = write_temp(tdir, "events.capsule.md", """---
uid: test
---
## 2. Schema
| Field | Required | Description |
|---|---|---|
| `lifecycle` | yes | Enum: `evergreen` (preserve) OR `ephemeral` (excluded) |
""")

        # Synthetic validator with the WRONG values (the v1.55 bug)
        validator = write_temp(tdir, "event_validators.py", """
TARGETS_CAPSULE = "events"
VALID_LIFECYCLE = {"open", "active", "closed"}  # WRONG — the v1.55 bug
""")

        schema = parse_capsule_schema(capsule)
        impl = parse_validator_implementation(validator)
        findings = compare(schema, impl)

        enum_findings = [f for f in findings if f.drift_class == "enum-value-drift"]
        lifecycle_findings = [f for f in enum_findings if f.field_name == "lifecycle"]

        ok = (
            len(lifecycle_findings) == 1
            and lifecycle_findings[0].drift_added == {"open", "active", "closed"}
            and lifecycle_findings[0].drift_removed == {"evergreen", "ephemeral"}
        )
        print(f"  [{'PASS' if ok else 'FAIL'}] §9.1 v1.55 lifecycle empirical case detected")
        return ok


def test_9_1_v1_55_lifecycle_aligned() -> bool:
    """§9.1 — Aligned lifecycle (no finding expected)."""
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        capsule = write_temp(tdir, "events.capsule.md", """---
uid: test
---
## 2. Schema
| Field | Required | Description |
|---|---|---|
| `lifecycle` | yes | Enum: `evergreen` (preserve) OR `ephemeral` (excluded) |
""")
        validator = write_temp(tdir, "event_validators.py", """
TARGETS_CAPSULE = "events"
VALID_LIFECYCLE = {"evergreen", "ephemeral"}  # CORRECT — aligned with canon
""")
        schema = parse_capsule_schema(capsule)
        impl = parse_validator_implementation(validator)
        findings = compare(schema, impl)
        drift_findings = [f for f in findings if f.drift_class == "enum-value-drift"]
        ok = len(drift_findings) == 0
        print(f"  [{'PASS' if ok else 'FAIL'}] §9.1 aligned lifecycle → zero findings")
        return ok


def test_9_2_no_validator_for_capsule() -> bool:
    """§9.2 — Capsule without matching validator → skip silently (no false fail)."""
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        capsule = write_temp(tdir, "unknown.capsule.md", """---
uid: test
---
| `foo` | yes | Enum: `a` OR `b` |
""")
        # No matching validator module
        schema = parse_capsule_schema(capsule)
        impl = ImplDecls(module_name="nonexistent_validators", targets_capsule="")
        findings = compare(schema, impl)
        # Should emit impl-not-detected but no false drift fail
        drift_fails = [f for f in findings if f.drift_class == "enum-value-drift" and f.drift_added or f.drift_removed]
        ok = len(drift_fails) == 0
        print(f"  [{'PASS' if ok else 'FAIL'}] §9.2 capsule without validator → no false-fail")
        return ok


def test_9_3_ast_computed_set() -> bool:
    """§9.3 — Validator with computed set → parse-ambiguous (not evaluated)."""
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        validator = write_temp(tdir, "test_validators.py", """
TARGETS_CAPSULE = "test"
# Computed set — Layer 3 should not evaluate
VALID_STATUS = {x for x in ["a", "b", "c"]}
""")
        impl = parse_validator_implementation(validator)
        # Should NOT have valid_sets["VALID_STATUS"] (can't eval comprehension)
        has_ambiguous = len(impl.parse_ambiguous) > 0 or "VALID_STATUS" not in impl.valid_sets
        print(f"  [{'PASS' if has_ambiguous else 'FAIL'}] §9.3 computed set → parse-ambiguous or skipped")
        return has_ambiguous


def test_9_4_perfectly_aligned() -> bool:
    """§9.4 — Perfectly aligned capsule + validator → zero findings."""
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        capsule = write_temp(tdir, "events.capsule.md", """---
uid: test
---
## 2. Schema
| Field | Required | |
|---|---|---|
| `lifecycle` | yes | Enum: `evergreen` OR `ephemeral` |
## 3. Event Type Registry
### tropo.message.sent
### tropo.message.acked
""")
        validator = write_temp(tdir, "event_validators.py", """
TARGETS_CAPSULE = "events"
VALID_LIFECYCLE = {"evergreen", "ephemeral"}
REGISTERED_TYPES = {"tropo.message.sent", "tropo.message.acked"}
""")
        schema = parse_capsule_schema(capsule)
        impl = parse_validator_implementation(validator)
        findings = compare(schema, impl)
        drift_findings = [f for f in findings if f.drift_class in ("enum-value-drift", "registered-type-drift")]
        ok = len(drift_findings) == 0
        print(f"  [{'PASS' if ok else 'FAIL'}] §9.4 perfectly aligned → zero drift findings")
        return ok


def test_real_substrate_events_capsule() -> bool:
    """§9.1 extended — Run Layer 3 against real events.capsule + event_validators.py."""
    capsule_path = VAULT_ROOT / ".tropo" / "capsules" / "events.capsule.md"
    validator_path = VAULT_ROOT / ".tropo" / "scripts" / "lib" / "event_validators.py"
    if not capsule_path.exists() or not validator_path.exists():
        print("  [SKIP] real substrate test — files not found")
        return True
    schema = parse_capsule_schema(capsule_path)
    impl = parse_validator_implementation(validator_path)
    findings = compare(schema, impl)
    drift_findings = [f for f in findings if f.drift_class in ("enum-value-drift", "registered-type-drift")]
    ok = len(drift_findings) == 0
    if not ok:
        for f in drift_findings:
            print(f"    {f.as_line()}")
    print(f"  [{'PASS' if ok else 'WARN'}] §9.1 real events.capsule ↔ event_validators aligned ({len(drift_findings)} drift findings)")
    return ok  # WARN not hard fail — schema parsing may surface parse-ambiguous items


def main() -> int:
    print("=== Lane V Layer 3 Regression Tests (v1.58 M.1 — spec 8e2f1a47 §9) ===")
    results = [
        test_9_1_v1_55_lifecycle_canonical(),
        test_9_1_v1_55_lifecycle_aligned(),
        test_9_2_no_validator_for_capsule(),
        test_9_3_ast_computed_set(),
        test_9_4_perfectly_aligned(),
        test_real_substrate_events_capsule(),
    ]
    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
