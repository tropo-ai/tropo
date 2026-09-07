"""adopt_declared_hubs — the plan's hub_summaries is a source for subsystems_touched (argus-a169, 2026-09-04).

Known-positive: the v1.94 shape — fourteen dev-spec capabilities with no hub parent, hub_summaries naming
one real hub — must yield that hub, not []. Negative control: with the adoption removed the same inputs
yield [], which is the defect the v1.94 run measured (release entry f015fd0f0dee, subsystems_touched: []).
"""
import importlib.util, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".tropo/scripts/dev-pipeline/update-subsystem-canonical-docs.py"
spec = importlib.util.spec_from_file_location("usc", SCRIPT)
usc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usc)


class DeclaredHubsAreASource(unittest.TestCase):
    def setUp(self):
        self.caps = [f"f015{i:08x}" for i in range(14)]
        self.member_of = {c: ["cd1fcd25"] for c in self.caps}  # dev-pipeline root, not a hub

    def test_v194_shape_yields_the_declared_hub(self):
        derived, non_hub = usc.derive_subsystems_with_audit(self.caps, self.member_of, usc.HUB_UIDS)
        self.assertEqual(derived, [])
        self.assertEqual(len(non_hub), 14)
        union, adopted = usc.adopt_declared_hubs(derived, {"8dd772a0": "the governance hub"}, usc.HUB_UIDS)
        self.assertEqual(union, ["8dd772a0"])
        self.assertEqual(adopted, ["8dd772a0"])

    def test_non_hub_declaration_is_not_adopted(self):
        union, adopted = usc.adopt_declared_hubs([], {"deadbeef": "not a hub"}, usc.HUB_UIDS)
        self.assertEqual((union, adopted), ([], []))

    def test_derived_and_declared_union_without_double_count(self):
        union, adopted = usc.adopt_declared_hubs(["2d083137"], {"2d083137": "work", "8dd772a0": "gov"}, usc.HUB_UIDS)
        self.assertEqual(union, ["2d083137", "8dd772a0"])
        self.assertEqual(adopted, ["8dd772a0"])

    def test_negative_control_without_adoption_the_defect_returns(self):
        derived, _ = usc.derive_subsystems_with_audit(self.caps, self.member_of, usc.HUB_UIDS)
        # The mechanism under test is adoption; remove it and the v1.94 defect is back.
        self.assertEqual(derived, [], "derivation alone must still be blind to the declaration")


if __name__ == "__main__":
    unittest.main()
