#!/usr/bin/env python3
"""No module may re-derive the governed-uid shape locally.

THE CLASS. `lib/governed_path.py` declares the shape once -- `UID_SHAPES`, with
`is_governed_uid_shape()` for predicates and `UID_HEX_PATTERN` for regex sites.
Its own docstring has said the rule since Stage A: *"Local hex-length literals
die here."* Declared, and until now unenforced.

WHAT THE UNENFORCED VERSION COST, in one day, each found separately and each
AFTER it had already blocked something:

  tropo-mount.py       no team vault could mount
  tropo-archive.py     every record minted after the flip: unarchivable
  tropo-restore.py     every record minted after the flip: unrestorable
  tropo-lineage.py     resolve_entry() returned None for ANY composite-uid agent,
                       so the lineage tool could not find that agent's own
                       identity entry -- and Cal and Darin are minted exactly
                       that way at genesis
  .tropo/scripts/lib/spec_substrate_refs.py   would have refused the next lock's
                       own activation uid

Metis G115 put the problem correctly: patch the list and the next one is found
the same way; build the authority and the class dies. This is the enforcement.

THE RULE. A non-test module under vault/tools/ that carries a uid-shaped hex
literal must EITHER import the authority, OR be named in GRANDFATHERED below with
a reason. A new module doing neither fails this test.

THE BASELINE IS HONEST. GRANDFATHERED is not a list of sites audited and found
correct; it is a list of sites NOT YET AUDITED, frozen so the bleeding stops
while the audit is owed. Per ADR-044, enforcement ratchets with named
grandfathers. Removing a name is the audit; adding one requires a reason.

Argus A165, 2026-09-01.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "vault" / "tools"))

from lib.governed_path import UID_SHAPES, UID_HEX_PATTERN, is_governed_uid_shape  # noqa: E402

TOOLS = ROOT / "vault" / "tools"

#: A hex-length literal in a regex AT A UID WIDTH -- the widths governed_path
#: declares (4 = the composite mint prefix, 8 = legacy, 12 = composite).
#: The first version matched ANY width (\{\d+\}) and so flagged a sha256
#: pattern ([0-9a-f]{64}) in tropo-render-studio-map.py as a uid literal: the
#: detector was broader than the rule its own docstring states ("uid-shaped").
#: A content hash is not a uid shape and has no home in governed_path to be
#: routed to; narrowing the detector fixes the instrument rather than
#: grandfathering a correct regex under a false reason. (argus-a168, 2026-09-03,
#: on talos-t61's routing; the {64} negative control below pins it.)
SHAPE_LITERAL = re.compile(r"\[0-9a-f(?:A-F)?\]\{(?:4|8|12)\}", re.IGNORECASE)

#: NOT AUDITED -- 68 modules, frozen 2026-09-01, keyed by path to their hit lines.
#:
#: READ THIS BEFORE TRUSTING THE GREEN. This list is NOT "sites checked and found
#: correct." It is "sites carrying a local shape literal that NOBODY HAS CLASSIFIED
#: YET." Metis G115 measured the same population and put the discriminator exactly:
#: most of these are legitimately 8 (uuid4 run uids, sha256 truncations, event ids,
#: step uids) and the question for each is whether THE VALUE COMES FROM THE MINT.
#: A static test cannot infer that; a person reading the site can.
#:
#: So this is a ratchet, not a clean bill of health (ADR-044: enforcement advances
#: with NAMED grandfathers). What it buys today: nothing NEW can start deriving the
#: shape locally without failing this test. What it still owes: the audit. Each of
#: the four cured on 2026-09-01 -- mount, archive, restore, lineage -- was found
#: one at a time, by accident, AFTER it had already blocked something. That is the
#: cost of an unaudited list, and it is why removing names from it is real work
#: rather than bookkeeping.
#:
#: Removing a name IS the audit. Adding one requires a reason in the commit.
GRANDFATHERED = {
    '11f3ebd4.py': [440],
    '28332b7b.py': [199, 202],
    '2e642578.py': [121],
    '4beff0d6.py': [197, 554, 612],
    '9e7003b1.py': [123, 527, 1156, 1535, 1557, 1559, 1561, 1586, 2301, 3672, 3874, 4691, 4693, 4914, 5241],
    'c778f748.py': [68],
    'e337f1dd.py': [699, 707, 756, 774],
    'lib/audience_context.py': [83, 85],
    'lib/authority_chain.py': [577, 1132, 1963, 2577, 2794, 2940],
    'lib/daily_spend.py': [20, 30],
    'lib/distiller.py': [123, 2442],
    'lib/distiller_capture.py': [20],
    'lib/distiller_edge.py': [24],
    'lib/distiller_model_policy.py': [308, 311],
    'lib/distiller_query.py': [25],
    'lib/event_identity.py': [49, 50, 51, 52, 354, 358],
    'lib/fan_in.py': [108, 109, 110],
    'lib/folder_sidecar.py': [54, 57],
    'lib/gardener_precision_fixtures.py': [42, 43, 44],
    'lib/group_authority.py': [218, 219, 220],
    'lib/group_contract.py': [43, 45],
    'lib/llm.py': [63],
    'lib/metered_model.py': [44, 251, 289, 294],
    'lib/mounted_projection_trust.py': [21],
    'lib/orient_stage_c.py': [287],
    'lib/pruning_contract.py': [51, 52],
    'lib/public_receipt_projection.py': [68, 136, 244],
    'lib/public_snapshot.py': [125, 126, 127, 128],
    'lib/release_closure.py': [56],
    'lib/release_events.py': [515],
    'lib/release_legs.py': [74, 79],
    'lib/release_package.py': [52],
    'lib/release_receipt.py': [86, 87, 379, 509, 706],
    'lib/release_site.py': [88],
    'lib/release_verify.py': [80, 81],
    'lib/template_leg.py': [459],
    'lib/tropo_round_trip_receipt.py': [40],
    'tropo-activate.py': [169, 174],
    'tropo-build-release.py': [1601, 1863, 3765],
    'tropo-check-events.py': [204, 206, 234],
    'tropo-check-one.py': [501],
    'tropo-check-publish-state.py': [58],
    # accepts-both extraction regex over prose in the L1 entry (AC8 render half,
    # metis/orpheus 2026-09-05) -- not a gate; audit owed to route it through
    # UID_HEX_PATTERN. Named 2026-09-05 by argus-a171 while auditing three others out.
    'tropo-render-studio-map.py': [888],
    'tropo-compact-continue.py': [572],
    'tropo-distiller-metered-canary.py': [160],
    'tropo-distiller-model-edge.py': [57],
    'tropo-emit-event.py': [169, 181, 205, 231, 349, 353, 538, 601],
    'tropo-export.py': [558],
    'tropo-folder.py': [556, 579, 583, 1126, 1425, 1466, 1550, 1554, 1602, 1617, 2063, 2202, 2213, 2492],
    'tropo-gardener-body-judge.py': [48, 116, 121],
    'tropo-gardener-verdict.py': [30, 48, 51, 54, 71],
    'tropo-generate-relations-header.py': [172],
    'tropo-import-walker.py': [403, 695],
    'tropo-lock-dev-spec.py': [674, 737],
    'tropo-lock-release-plan.py': [96, 281],
    'tropo-migrate-mount-identity.py': [92],
    'tropo-mint-id.py': [146, 151, 152, 881],
    'tropo-rebuild-vault.py': [162, 262],
    'tropo-recycle.py': [69, 292, 309],
    'tropo-release-validation-gate.py': [26, 147, 226],
    'tropo-release.py': [98],
    'tropo-smoke.py': [365],
    'tropo-validate-package-links.py': [76],
    'tropo-validate.py': [284, 1493, 2335, 4806, 4807, 5730, 8067, 9433, 9434, 12146, 12575, 12735, 12857, 13003, 13004, 13005, 14217],
}


#: AUDITED AND LEGITIMATELY LOCAL. A site here HAS been read and its value does
#: NOT come from the mint, so an 8-only literal is correct and routing it through
#: the governed-uid authority would be wrong.
#:
#: This dict exists because the first version of this gate had only two states --
#: routed, or unaudited-grandfathered -- and so DOING the audit had nowhere to
#: land. Metis G115's framing is that removing a name IS the audit; that is only
#: true if a correct-as-is finding can be recorded. Otherwise the only way to
#: clear a name is to make a wrong change.
AUDITED_LOCAL = {
    'loop_metering_gateway.py':
        "RUN_UID_RE gates a loop-run uid minted as uuid4()[:8] by 2e5c81d3.py:96 "
        "-- not a governed mint. 8 is correct and composite would be wrong. "
        "Audited 2026-09-01 by argus-a165 while curing the launcher's missing "
        "run_uid key; both ends read, both shapes confirmed.",
}

def _modules():
    for p in sorted(TOOLS.rglob("*.py")):
        if "tests" in p.parts:
            continue
        yield p


class TheUidShapeHasExactlyOneHome(unittest.TestCase):

    def test_no_unroutined_module_carries_a_shape_literal(self) -> None:
        offenders = []
        for p in _modules():
            text = p.read_text(errors="ignore")
            hits = [
                (i + 1, line.strip())
                for i, line in enumerate(text.split("\n"))
                if SHAPE_LITERAL.search(line) and not line.strip().startswith("#")
            ]
            if not hits:
                continue
            routed = ("is_governed_uid_shape" in text) or ("UID_HEX_PATTERN" in text)
            rel = str(p.relative_to(TOOLS))
            if routed or rel in GRANDFATHERED or rel in AUDITED_LOCAL:
                continue
            offenders.append(f"{p.relative_to(ROOT)} lines {[h[0] for h in hits][:5]}")
        self.assertEqual(
            offenders,
            [],
            "these modules derive the governed-uid shape locally instead of importing "
            "the authority. Either route them through lib.governed_path, or add them to "
            "GRANDFATHERED with a reason stating what is UNKNOWN about them:\n  "
            + "\n  ".join(offenders),
        )

    def test_grandfathered_names_still_exist(self) -> None:
        """A grandfather for a file that no longer exists is debt pretending to be
        coverage -- it makes the list look longer than the problem."""
        for name in GRANDFATHERED:
            self.assertTrue(
                (TOOLS / name).is_file(),
                f"{name} is grandfathered but does not exist; remove the entry.",
            )

    def test_the_authority_agrees_with_its_own_derived_pattern(self) -> None:
        """The predicate and the regex pattern are two faces of UID_SHAPES. If they
        ever disagree, a regex site and a predicate site would classify the same
        uid differently -- the defect this whole file exists to end."""
        rx = re.compile(r"^(?:%s)$" % UID_HEX_PATTERN)
        for n in range(1, 25):
            sample = "a" * n
            self.assertEqual(
                bool(rx.fullmatch(sample)),
                is_governed_uid_shape(sample),
                f"predicate and pattern disagree at length {n}",
            )


    def test_a_name_is_not_both_audited_and_unaudited(self) -> None:
        """Overlap would let an audited-correct finding hide inside the debt pile,
        which is the opposite of what the audit is for."""
        both = sorted(set(GRANDFATHERED) & set(AUDITED_LOCAL))
        self.assertEqual(both, [], "these are in both lists: %r" % (both,))

    def test_every_audited_entry_states_a_reason(self) -> None:
        """An audit with no reason is a deletion wearing an audit's name."""
        for name, reason in AUDITED_LOCAL.items():
            self.assertGreater(
                len(reason), 60,
                "%s is marked audited with no substantive reason" % name)

    def test_the_control_would_notice(self) -> None:
        """Proof the scan can fail: a synthetic unrouted module must be caught. If
        the detector cannot see a planted literal, every green run above is
        meaningless."""
        # A sha256 pattern is NOT a uid shape: the detector must stay quiet on
        # it, or every content-hash regex in the corpus reads as a second home.
        self.assertIsNone(
            SHAPE_LITERAL.search("FP = re.compile(r'<!-- sha256:([0-9a-f]{64}) -->')"),
            "a 64-hex content hash is not a uid-shaped literal",
        )
        planted = "x = re.compile(r'^[0-9a-f]{8}$')"
        self.assertTrue(
            SHAPE_LITERAL.search(planted),
            "the detector does not match a plain shape literal, so it proves nothing",
        )
        self.assertFalse(
            SHAPE_LITERAL.search("x = some_call(uid)"),
            "the detector matches a line with no shape literal, so it would cry wolf",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
