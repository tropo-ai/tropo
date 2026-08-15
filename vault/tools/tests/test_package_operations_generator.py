#!/usr/bin/env python3
"""Package operations, computed from ground truth — and the three refusals.

talos-t40, 2026-08-09, velocity item 8 of the v1.86 retrospective.

Each refusal replays a mistake this studio actually made and paid for, so the
tests are named after the failure rather than after the branch:

  - v1.86.0's manifest shipped the narrative and NO operations, caught by the
    customer's Po at her Step-1a halt rather than by any gate of ours.
  - v1.85.0 broke a real customer as a hand-curated delta cut from the WRONG
    BASE, which makes existing paths read as `add`.
  - 24 of this studio's runtime flags reached a customer because the packaging
    path omitted nothing and questioned nothing.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

TOOLS = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "tropo_generate_package_operations",
    TOOLS / "tropo-generate-package-operations.py",
)
assert _spec and _spec.loader
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def _tree(root: Path, paths) -> Path:
    for rel in paths:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    return root


class AddVersusReplaceIsComputedNotJudged(unittest.TestCase):
    def test_presence_in_the_prior_surface_decides_the_verb(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _tree(root / "pkg" / "files", [
                ".tropo/TROPO-CONTROL.md",
                ".tropo/WAKE-DISCIPLINE.md",
                "vault/tools/tropo-validate.py",
            ])
            baseline = _tree(root / "base", [
                ".tropo/TROPO-CONTROL.md",
                "vault/tools/tropo-validate.py",
            ])
            ops, excluded = gen.plan_operations(
                payload, baseline, allow_partial_baseline=True
            )
            verbs = {op["path"]: op["type"] for op in ops}
            self.assertEqual(verbs[".tropo/TROPO-CONTROL.md"], "replace")
            self.assertEqual(verbs["vault/tools/tropo-validate.py"], "replace")
            self.assertEqual(verbs[".tropo/WAKE-DISCIPLINE.md"], "add")
            self.assertEqual(excluded, [])

    def test_every_operation_carries_a_source_the_apply_can_find(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _tree(root / "pkg" / "files", ["vault/tools/x.py"])
            baseline = _tree(root / "base", ["vault/tools/x.py"])
            ops, _ = gen.plan_operations(payload, baseline, allow_partial_baseline=True)
            self.assertEqual(ops[0]["source"], "files/vault/tools/x.py")
            self.assertIn("SHARPEN THIS REASON", ops[0]["reason"])


class TheThreeRefusals(unittest.TestCase):
    def test_an_empty_plan_is_refused_because_that_was_the_v1_86_defect(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _tree(root / "pkg" / "files", [".tropo/flags/only-state.flag"])
            baseline = _tree(root / "base", [".tropo/TROPO-CONTROL.md"])
            with self.assertRaises(gen.PackagingRefusal) as caught:
                gen.plan_operations(payload, baseline, allow_partial_baseline=True)
            self.assertIn("EMPTY", str(caught.exception))
            self.assertIn("v1.86.0 defect", str(caught.exception))

    def test_a_missing_baseline_is_refused_rather_than_assumed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _tree(root / "pkg" / "files", ["vault/tools/x.py"])
            with self.assertRaises(gen.PackagingRefusal) as caught:
                gen.plan_operations(payload, root / "nope")
            self.assertIn("v1.85.0", str(caught.exception))

    def test_a_delta_shaped_baseline_is_refused_as_the_wrong_base(self) -> None:
        """The trap I walked into while building this.

        I baselined the real v1.86 package against the v1.85.1 DELTA package and
        got "496 add + 26 replace" with no complaint — every existing customer
        path planned as new. That is the v1.85.0 failure, reproduced by me, in
        the tool written to prevent it.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _tree(root / "pkg" / "files",
                            [f"vault/files/{i:04d}.md" for i in range(40)])
            baseline = _tree(root / "base", ["vault/files/0000.md"])
            with self.assertRaises(gen.PackagingRefusal) as caught:
                gen.plan_operations(payload, baseline)
            self.assertIn("DELTA package", str(caught.exception))

            # And the escape hatch works, because sometimes it really is right.
            ops, _ = gen.plan_operations(payload, baseline, allow_partial_baseline=True)
            self.assertEqual(len(ops), 40)


class StateIsExcludedOutLoud(unittest.TestCase):
    def test_state_is_dropped_from_operations_and_reported_with_a_reason(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _tree(root / "pkg" / "files", [
                ".tropo/TROPO-CONTROL.md",
                ".tropo/flags/attendant-mode-offered.flag",
                "vault/updates/updates-manifest.json",
            ])
            baseline = _tree(root / "base", [".tropo/TROPO-CONTROL.md"])
            ops, excluded = gen.plan_operations(
                payload, baseline, allow_partial_baseline=True
            )
            self.assertEqual([op["path"] for op in ops], [".tropo/TROPO-CONTROL.md"])
            dropped = {path for path, _reason in excluded}
            self.assertEqual(dropped, {
                ".tropo/flags/attendant-mode-offered.flag",
                "vault/updates/updates-manifest.json",
            })
            for _path, reason in excluded:
                self.assertGreater(len(reason), 30, "silent omission is the defect")

    def test_it_shares_one_rule_with_the_box_build(self) -> None:
        """Not a second opinion about what state is.

        A file that is state in the box builder and OS in the packager would be
        the worst of both: excluded from one path, shipped by the other, and
        nobody able to say which is right.
        """
        source = (TOOLS / "tropo-generate-package-operations.py").read_text()
        self.assertIn("package_state_exclusions", source)
        self.assertTrue(gen.psx.is_studio_state(".tropo/flags/x.flag"))


class TheRenderedBlockIsValidManifestYaml(unittest.TestCase):
    def test_it_round_trips_through_a_yaml_parser(self) -> None:
        import yaml

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = _tree(root / "pkg" / "files", [
                'vault/files/quote"and — dash.md',
                "vault/tools/plain.py",
            ])
            baseline = _tree(root / "base", ["vault/tools/plain.py"])
            ops, _ = gen.plan_operations(payload, baseline, allow_partial_baseline=True)
            parsed = yaml.safe_load(gen.render_yaml(ops))
            self.assertEqual(len(parsed["operations"]), 2)
            self.assertEqual(
                {op["type"] for op in parsed["operations"]}, {"add", "replace"}
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
