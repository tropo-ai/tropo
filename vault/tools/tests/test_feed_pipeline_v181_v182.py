#!/usr/bin/env python3
"""test_feed_pipeline_v181_v182.py — proves item 3 of Argus's session queue
(00005829): the retroactive feed-the-pipeline cure for v1.81 "Work Crosses
the Boundary" (92093c81) and v1.82 "Gardener" (8e551957), per Mike's ruling
in vault/files/8e8a0962.md ("feed the pipeline, not attested-cut").

Proves, against the REAL vault substrate (not a fixture — this item is
about whether the real cure landed):
  1. Both retroactive dev-pipeline activations exist, are well-formed, and
     carry dev_spec_uid correlating to the correct dev-spec.
  2. Both type:build entries exist, are schema-valid against build.capsule
     (type / status / build_version / derived_from / member_of /
     locked_by+locked_at / the 4 required body sections in order), and
     honestly transcribe the real evidence (build_signed_at, argus_verify_uid)
     rather than fabricating it.
  3. A fresh run of tropo-validate.py's check_dev_spec_activation_coupling
     (8f15f08d) no longer flags 92093c81 or 8e551957 as off-pipeline — the
     precise condition Vela's release-cut and Argus's coupling gate both
     depend on.
  4. The two disclosed capsule-vs-practice gaps (build_path; derived_from
     targeting a dev-spec) are present as explicit, documented notes rather
     than silently fabricated values.
"""
from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
FILES_DIR = ROOT / "vault" / "files"
VALIDATE_PATH = ROOT / "vault" / "tools" / "tropo-validate.py"

_spec = importlib.util.spec_from_file_location("tropo_validate_under_test_feed_pipeline", str(VALIDATE_PATH))
tropo_validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tropo_validate)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _load(uid: str) -> tuple[dict, str]:
    path = FILES_DIR / f"{uid}.md"
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    assert m, f"{uid}.md has no parseable frontmatter"
    fm = yaml.safe_load(m.group(1))
    body = m.group(2)
    return fm, body


class TestFeedThePipelineV181V182(unittest.TestCase):
    """v1.81 (92093c81 / build 58c12179 / activation 413db7f5) and
    v1.82 (8e551957 / build 3bf60661 / activation 019c765a)."""

    CASES = {
        "v1.81": dict(
            dev_spec_uid="92093c81",
            build_uid="58c12179",
            activation_uid="413db7f5",
            evidence_uid="c35a7410",
            build_version="1.81.0",
        ),
        "v1.82": dict(
            dev_spec_uid="8e551957",
            build_uid="3bf60661",
            activation_uid="019c765a",
            evidence_uid="322728e7",
            build_version="1.82.0",
        ),
    }

    # ------------------------------------------------------------------
    # 1. Activation entries
    # ------------------------------------------------------------------

    def test_activation_entries_exist_and_are_well_formed(self) -> None:
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, _body = _load(case["activation_uid"])
                self.assertEqual(fm.get("type"), "activation")
                self.assertEqual(fm.get("activation_class"), "pipeline")
                self.assertEqual(fm.get("pipeline_uid"), "cd1fcd25")
                self.assertEqual(fm.get("dev_spec_uid"), case["dev_spec_uid"])
                self.assertEqual(fm.get("status"), "retired")
                self.assertTrue(fm.get("retired_at"))
                self.assertEqual(fm.get("closure_reason"), "clean-retirement")
                self.assertTrue(fm.get("retroactive") is True)
                self.assertIn("8e8a0962", fm.get("retroactive_note", ""))

    def test_activation_root_projects_exist(self) -> None:
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, _body = _load(case["activation_uid"])
                root_uid = fm.get("activation_root_project")
                self.assertTrue(root_uid, "activation entry missing activation_root_project")
                root_fm, _root_body = _load(root_uid)
                self.assertEqual(root_fm.get("type"), "project")
                self.assertEqual(root_fm.get("activation_entry"), case["activation_uid"])

    # ------------------------------------------------------------------
    # 2. type:build entries — schema per build.capsule (b3d7e5a1)
    # ------------------------------------------------------------------

    def test_build_entries_exist_and_are_schema_valid(self) -> None:
        required_frontmatter = (
            "type", "title", "description", "status", "state", "owner",
            "build_version", "derived_from", "member_of",
        )
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, _body = _load(case["build_uid"])
                for field in required_frontmatter:
                    self.assertIn(field, fm, f"{case['build_uid']}.md missing required field {field!r}")
                self.assertEqual(fm.get("type"), "build")
                self.assertEqual(fm.get("status"), "locked")
                self.assertEqual(fm.get("build_version"), case["build_version"])
                self.assertRegex(fm.get("build_version"), r"^\d+\.\d+\.\d+(-[a-z0-9.-]+)?$")
                # Rule 12: locked_by + locked_at present when status:locked.
                self.assertTrue(fm.get("locked_by"))
                self.assertTrue(fm.get("locked_at"))

    def test_build_derived_from_points_at_the_dev_spec(self) -> None:
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, _body = _load(case["build_uid"])
                derived_from = fm.get("derived_from") or []
                self.assertIn(case["dev_spec_uid"], derived_from)
                # The dev-spec must actually exist and actually be locked +
                # mike-signed-accepted — the build's provenance must resolve to
                # something real, not a dangling reference.
                ds_fm, _ds_body = _load(case["dev_spec_uid"])
                self.assertEqual(ds_fm.get("type"), "dev-spec")
                self.assertEqual(ds_fm.get("status"), "locked")
                self.assertEqual(ds_fm.get("build_status"), "mike-signed-accepted")

    def test_build_evidence_is_transcribed_not_fabricated(self) -> None:
        """Every ship-relevant claim on the build entry must trace to something
        that already existed BEFORE today (the dev-spec's own build_signed_at /
        argus_verify_uid) — not a value invented for this retroactive record."""
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, _body = _load(case["build_uid"])
                ds_fm, _ds_body = _load(case["dev_spec_uid"])
                self.assertEqual(fm.get("build_signed_by"), ds_fm.get("build_signed_by"))
                self.assertEqual(fm.get("build_signed_at"), ds_fm.get("build_signed_at"))
                self.assertEqual(fm.get("argus_verify_uid"), ds_fm.get("argus_verify_uid"))
                self.assertEqual(fm.get("argus_verify_uid"), case["evidence_uid"])
                # The cited evidence file must actually exist and actually be the
                # verification record it claims to be.
                ev_fm, _ev_body = _load(case["evidence_uid"])
                self.assertEqual(ev_fm.get("type"), "note")
                self.assertIn(case["dev_spec_uid"], ev_fm.get("refs") or [])

    def test_build_activation_uid_backreference(self) -> None:
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, _body = _load(case["build_uid"])
                self.assertEqual(fm.get("activation_entry"), case["activation_uid"])
                self.assertEqual(fm.get("dev_spec_uid"), case["dev_spec_uid"])

    def test_build_required_body_sections_present_in_order(self) -> None:
        required_sections = ["## Build Summary", "## Spec Traceability", "## Test Results", "## Known Issues"]
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                _fm, body = _load(case["build_uid"])
                positions = [body.find(section) for section in required_sections]
                self.assertTrue(all(p >= 0 for p in positions), f"{case['build_uid']}.md missing a required body section")
                self.assertEqual(positions, sorted(positions), f"{case['build_uid']}.md required sections out of order")

    def test_build_known_issues_disclose_the_capsule_gaps_honestly(self) -> None:
        """Confirms the build_path + derived_from capsule-vs-practice gaps are
        DISCLOSED plainly (per Talos's honesty discipline) rather than silently
        worked around or left undocumented."""
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, body = _load(case["build_uid"])
                self.assertIn("N/A", fm.get("build_path", ""))
                self.assertTrue(fm.get("build_path_gap_note"))
                self.assertTrue(fm.get("derived_from_gap_note"))
                self.assertIn("build_path", body)
                self.assertIn("derived_from", body)

    def test_build_composes_into_is_unset(self) -> None:
        """Rule 3: composes_into is populated AT SHIP TIME by the deploy-stage
        owner (Vela's lane here) — Talos's build entry must NOT pre-set it."""
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, _body = _load(case["build_uid"])
                self.assertNotIn("composes_into", fm)

    # ------------------------------------------------------------------
    # 3. The validator's coupling gate (8f15f08d) no longer flags either UID
    # ------------------------------------------------------------------

    def test_validator_coupling_gate_no_longer_flags_v181_or_v182(self) -> None:
        findings, _checked, _violations = tropo_validate.check_dev_spec_activation_coupling(ROOT)
        flagged = {uid for f in findings for uid in ("92093c81", "8e551957") if uid in f}
        self.assertEqual(flagged, set(), f"coupling gate still flags: {flagged}")

    def test_dev_specs_are_in_the_named_grandfather_allowlist(self) -> None:
        """UPDATED 2026-07-08 (Talos T26, register 2b12e41d / event 00005914):
        the allowlist previously named these two UIDs explicitly while they were
        the sole grandfathered exception. The 9-other-UID debt this file's own
        docstring flagged (see check_dev_spec_activation_coupling's
        VERIFY-BEFORE-DESIGNING FINDING) has since been cured by Talos T26, so
        the allowlist ratcheted to EMPTY per 8f15f08d's own design ("no second
        hand-edit... beyond removing the emptied allowlist") — these two UIDs
        no longer need grandfather cover because they carry real, correlated
        activations (proven by test_validator_coupling_gate_no_longer_flags_v181_or_v182
        above), not just an allowlist exemption. This test now documents that
        historical fact instead of asserting the now-superseded allowlist contents."""
        self.assertEqual(tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST, frozenset())
        # Both UIDs still resolve to real, correlated activations independent
        # of the (now-empty) allowlist — the grandfather cover is no longer load-bearing.
        findings, _checked, _violations = tropo_validate.check_dev_spec_activation_coupling(ROOT)
        flagged = {uid for f in findings for uid in ("92093c81", "8e551957") if uid in f}
        self.assertEqual(flagged, set())


if __name__ == "__main__":
    unittest.main()
