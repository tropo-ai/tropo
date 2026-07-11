#!/usr/bin/env python3
"""test_systemic_feed_pipeline_v184.py — proves both items of Argus's work-order
(event 00005883, correlated to Talos's ACK 00005884):

ITEM 1 — the systemic feed-the-pipeline cure for this session's off-pipeline
v1.84 federation dev-specs: forge (943bb220), nav-blocks (6ec30708), chokepoint
(796d9330), studio-identity (32067bea), coupling-gate (8f15f08d). Topology:
FIVE separate per-dev-spec activations (not one shared v1.84-cycle activation)
— a structural requirement, not just a style choice: check_dev_spec_activation_
coupling correlates via a single-value `dev_spec_uid` scalar field per
activation entry (`fm.get('dev_spec_uid')`), so one shared activation could
only ever correlate to ONE of the 5 dev-specs, leaving the other 4 uncured.

ITEM 2 — the coupling runnable-lock (vault/tools/tropo-lock-dev-spec.py, per
ADR-052 ee0e35ad): locking a dev-spec THROUGH the tool atomically opens (or
reuses) its correlated pipeline activation as one indivisible act.
check_dev_spec_activation_coupling (8f15f08d) stays the BACKSTOP, unmodified —
proven here by re-running its existing gauntlets and confirming no regression.

Honest test-environment disclosure (Talos's Rule 2 — flag, don't paper over):
`pipeline-activate.py` (e337f1dd.py) hardcodes its own vault root as
`Path(__file__).resolve().parents[2]` — it CANNOT be redirected to an isolated
fixture directory via cwd or an env var; there is no such seam in that tool.
So the atomicity/idempotency/refusal LOGIC that lives in THIS session's new
tropo-lock-dev-spec.py is proven in a fully isolated tmp-dir fixture using an
injected stand-in "activate script" (a tiny throwaway script this test writes
and fully controls) — this exercises 100% of lock-dev-spec.py's own decision
logic without touching the real vault. The actual END-TO-END integration
against the REAL pipeline-activate.py is then proven exactly once, against
the real vault, using the same plant-and-cleanup adversarial-gauntlet pattern
this session's test_capability_chain_smoke.py already established for
components that are wired to the real vault by construction (its own
`check_dev_spec_activation_coupling_gate` plants+removes a real file for the
identical reason). This mirrors, not invents, an already-accepted convention.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
FILES_DIR = ROOT / "vault" / "files"
VALIDATE_PATH = ROOT / "vault" / "tools" / "tropo-validate.py"
LOCK_TOOL_PATH = ROOT / "vault" / "tools" / "tropo-lock-dev-spec.py"
ACTIVATE_PATH = ROOT / "vault" / "tools" / "e337f1dd.py"

_spec = importlib.util.spec_from_file_location("tropo_validate_under_test_v184", str(VALIDATE_PATH))
tropo_validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tropo_validate)

_lock_spec = importlib.util.spec_from_file_location("tropo_lock_dev_spec_under_test", str(LOCK_TOOL_PATH))
lock_dev_spec_mod = importlib.util.module_from_spec(_lock_spec)
_lock_spec.loader.exec_module(lock_dev_spec_mod)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)

# Guardrail: the 9 UIDs this task must NEVER touch (Argus's own triage lane).
GUARDRAILED_9 = frozenset({
    "5e12ab9c", "81e52840", "dabe7c64", "98b9610a", "0c61a52b",
    "55c33476", "c036dd4b", "2fe61817", "bc730fe4",
})


def _load(uid: str) -> tuple[dict, str]:
    path = FILES_DIR / f"{uid}.md"
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    assert m, f"{uid}.md has no parseable frontmatter"
    fm = yaml.safe_load(m.group(1))
    body = m.group(2)
    return fm, body


# ===========================================================================
# ITEM 1 — the 5 v1.84 federation dev-spec activations + type:build entries
# ===========================================================================

class TestItem1FeedThePipelineV184(unittest.TestCase):
    """5 SEPARATE activations/builds (943bb220/6ec30708/796d9330/32067bea/8f15f08d) —
    topology forced by the single-value dev_spec_uid scalar (see module docstring)."""

    CASES = {
        "forge": dict(
            dev_spec_uid="943bb220", activation_uid="7f0ab56f", root_uid="46b703a4",
            build_uid="2d7e68f7", commit="9785718", has_verify_note=True,
        ),
        "nav-blocks": dict(
            dev_spec_uid="6ec30708", activation_uid="2fb66651", root_uid="9e0f9ecf",
            build_uid="91a51b53", commit="ce5e9232", has_verify_note=False,
        ),
        "chokepoint": dict(
            dev_spec_uid="796d9330", activation_uid="12ec241f", root_uid="e8e6ac4e",
            build_uid="825dcfe6", commit="8dd955f-NOT-USED", has_verify_note=False,
        ),
        "studio-identity": dict(
            dev_spec_uid="32067bea", activation_uid="93b7309b", root_uid="b06dad66",
            build_uid="4eaca74b", commit="e751ef1", has_verify_note=True,
        ),
        "coupling-gate": dict(
            dev_spec_uid="8f15f08d", activation_uid="2322b427", root_uid="0b9a57b3",
            build_uid="7e1af202", commit="8dd955f", has_verify_note=False,
        ),
    }

    # ------------------------------------------------------------------
    # Activation entries — topology + well-formedness
    # ------------------------------------------------------------------

    def test_five_separate_activations_each_correlate_exactly_one_dev_spec(self) -> None:
        """The structural argument for the topology choice: each activation's
        dev_spec_uid is a scalar (not a list), and each of the 5 has its OWN
        activation — no sharing. If check_dev_spec_activation_coupling's
        correlation (`fm.get('dev_spec_uid')`) ever saw a list, str(list) would
        never equal any individual dev-spec uid, breaking the cure entirely."""
        seen_dev_spec_uids = set()
        seen_activation_uids = set()
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, _body = _load(case["activation_uid"])
                self.assertEqual(fm.get("type"), "activation")
                dsu = fm.get("dev_spec_uid")
                self.assertIsInstance(dsu, str, "dev_spec_uid must be a scalar string, not a list")
                self.assertEqual(dsu, case["dev_spec_uid"])
                seen_dev_spec_uids.add(dsu)
                seen_activation_uids.add(fm.get("uid"))
        self.assertEqual(len(seen_dev_spec_uids), 5, "all 5 dev-spec correlations must be distinct")
        self.assertEqual(len(seen_activation_uids), 5, "all 5 activation UIDs must be distinct (no sharing)")

    def test_activation_entries_well_formed_and_retroactive(self) -> None:
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, _body = _load(case["activation_uid"])
                self.assertEqual(fm.get("activation_class"), "pipeline")
                self.assertEqual(fm.get("pipeline_uid"), "cd1fcd25")
                self.assertEqual(fm.get("status"), "retired")
                self.assertTrue(fm.get("retired_at"))
                self.assertEqual(fm.get("closure_reason"), "clean-retirement")
                self.assertTrue(fm.get("retroactive") is True)
                self.assertIn("00005883", fm.get("retroactive_note", ""))
                self.assertEqual(fm.get("activation_root_project"), case["root_uid"])

    def test_activation_root_projects_exist_and_backreference(self) -> None:
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                root_fm, _root_body = _load(case["root_uid"])
                self.assertEqual(root_fm.get("type"), "project")
                self.assertEqual(root_fm.get("status"), "done")
                self.assertEqual(root_fm.get("activation_entry"), case["activation_uid"])
                self.assertTrue(root_fm.get("retroactive") is True)

    # ------------------------------------------------------------------
    # type:build entries — schema per build.capsule + honest transcription
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
                self.assertRegex(fm.get("build_version"), r"^\d+\.\d+\.\d+(-[a-z0-9.-]+)?$")
                self.assertTrue(fm.get("locked_by"))
                self.assertTrue(fm.get("locked_at"))
                self.assertEqual(fm.get("dev_spec_uid"), case["dev_spec_uid"])
                self.assertEqual(fm.get("activation_entry"), case["activation_uid"])
                self.assertIn(case["dev_spec_uid"], fm.get("derived_from") or [])

    def test_build_version_uniqueness_across_all_five(self) -> None:
        """build.capsule Check 5: build_version unique across all builds."""
        versions = [_load(case["build_uid"])[0].get("build_version") for case in self.CASES.values()]
        self.assertEqual(len(versions), len(set(versions)), f"build_version collision: {versions}")

    def test_build_required_body_sections_present_in_order(self) -> None:
        required_sections = ["## Build Summary", "## Spec Traceability", "## Test Results", "## Known Issues"]
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                _fm, body = _load(case["build_uid"])
                positions = [body.find(section) for section in required_sections]
                self.assertTrue(all(p >= 0 for p in positions), f"{case['build_uid']}.md missing a required body section")
                self.assertEqual(positions, sorted(positions), f"{case['build_uid']}.md required sections out of order")

    def test_build_two_with_verify_note_transcribe_verbatim(self) -> None:
        """forge (943bb220) + studio-identity (32067bea) DO carry an
        argus_verify_note on the dev-spec — assert the build entry's evidence
        fields match that source character-for-character (no fabrication)."""
        for label, case in self.CASES.items():
            if not case["has_verify_note"]:
                continue
            with self.subTest(label=label):
                build_fm, build_body = _load(case["build_uid"])
                ds_fm, _ds_body = _load(case["dev_spec_uid"])
                verify_note = ds_fm.get("argus_verify_note")
                self.assertTrue(verify_note, f"{case['dev_spec_uid']} expected to carry argus_verify_note")
                self.assertEqual(build_fm.get("build_commit"), str(ds_fm.get("build_commit")))
                self.assertEqual(build_fm.get("argus_verified_by"), ds_fm.get("build_verified_by"))
                self.assertEqual(build_fm.get("argus_verified_at"), ds_fm.get("build_verified_at"))
                # The verify note's exact text must appear verbatim in the build body.
                self.assertIn(verify_note.strip(), build_body)

    def test_build_three_without_verify_note_disclose_the_gap_honestly(self) -> None:
        """nav-blocks (6ec30708), chokepoint (796d9330), coupling-gate (8f15f08d)
        do NOT carry an argus_verify_note on the dev-spec — despite the
        work-order's premise that all 5 do. Assert this gap is DISCLOSED on the
        build entry, not silently papered over or fabricated."""
        for label, case in self.CASES.items():
            if case["has_verify_note"]:
                continue
            with self.subTest(label=label):
                ds_fm, _ds_body = _load(case["dev_spec_uid"])
                self.assertNotIn("argus_verify_note", ds_fm,
                                  f"{case['dev_spec_uid']} unexpectedly carries argus_verify_note — "
                                  f"update this test's has_verify_note mapping")
                build_fm, build_body = _load(case["build_uid"])
                self.assertNotIn("argus_verified_by", build_fm)
                self.assertIn("GAP DISCLOSED", build_fm.get("retroactive_note", ""))
                self.assertIn("argus_verify_note_gap", build_fm)
                self.assertIn("NONE", build_fm["argus_verify_note_gap"])
                self.assertIn("commit", build_body.lower())

    def test_derived_from_and_build_path_gaps_disclosed_not_fabricated(self) -> None:
        """Identical disclosed-not-fabricated discipline as the v1.81/v1.82
        precedent (58c12179/3bf60661) — build.capsule's derived_from + build_path
        contracts predate the dev-spec-centric, no-releases-folder regime."""
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                fm, body = _load(case["build_uid"])
                self.assertIn("N/A", fm.get("build_path", ""))
                self.assertTrue(fm.get("build_path_gap_note"))
                self.assertTrue(fm.get("derived_from_gap_note"))
                self.assertIn("build_path", body)
                self.assertIn("derived_from", body)

    def test_coupling_gate_dev_spec_target_release_tension_disclosed(self) -> None:
        """8f15f08d's OWN target_release is 1.85.0 (explicitly sequenced BEHIND
        v1.84), yet Argus's work-order groups it with the 4 other v1.84 dev-specs.
        This tension must be disclosed on the build entry, not silently resolved."""
        ds_fm, ds_body = _load("8f15f08d")
        self.assertEqual(ds_fm.get("target_release"), "1.85.0")
        build_fm, _build_body = _load(self.CASES["coupling-gate"]["build_uid"])
        self.assertIn("1.85.0", build_fm.get("build_version_gap_note", ""))
        self.assertIn("DISCLOSED TENSION", build_fm.get("build_version_gap_note", ""))

    # ------------------------------------------------------------------
    # The validator's coupling gate correlates all 5 (would clear at lock time)
    # ------------------------------------------------------------------

    def test_all_five_dev_specs_have_a_correlated_activation_on_the_real_vault(self) -> None:
        """Uses the SAME correlation helper the new lock tool uses (which
        mirrors check_dev_spec_activation_coupling's own semantics) — proves
        that IF any of the 5 later locks, the coupling gate will find a real,
        pre-existing activation and NOT flag it."""
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                found = lock_dev_spec_mod.find_correlated_activation(case["dev_spec_uid"], files_dir=FILES_DIR)
                self.assertIsNotNone(found, f"{case['dev_spec_uid']} has no correlated activation on the real vault")
                self.assertEqual(found.get("uid"), case["activation_uid"])

    def test_five_dev_specs_currently_still_draft_not_locked(self) -> None:
        """Confirms this was a PROACTIVE cure (closing the gap before it could
        trip the coupling check), not a reactive cure of an already-WARNing
        violation like v1.81/v1.82 — none of the 5 are status:locked yet."""
        for label, case in self.CASES.items():
            with self.subTest(label=label):
                ds_fm, _ = _load(case["dev_spec_uid"])
                self.assertEqual(ds_fm.get("status"), "draft")

    def test_guardrailed_nine_uids_untouched_still_uncorrelated(self) -> None:
        """UPDATED 2026-07-08 (Talos T26, register 2b12e41d / event 00005914):
        at authoring time (T25, event 00005883 item 1), these 9 UIDs were
        explicitly out of THIS item's scope — "Argus's own triage lane,"
        deferred pending his own investigation (8e8a0962) and disposition
        register. That triage completed and Argus issued a FOLLOW-UP work-order
        (event 00005914) explicitly directing Talos to cure exactly these 9 UIDs
        (register 2b12e41d, 8x disposition A + 1x disposition B). This test's
        original premise — "prove item 1 didn't touch them" — no longer applies
        once a later, separately-authorized item DOES touch them on purpose.
        Kept as a positive-inverse check: item 1's OWN 5 UIDs (943bb220 etc.)
        remain distinct from the 9 (no accidental overlap), and the 9 are now
        confirmed correlated per the later work-order, not silently orphaned."""
        item1_uids = {c["dev_spec_uid"] for c in self.CASES.values()}
        self.assertEqual(
            item1_uids & GUARDRAILED_9, set(),
            "item 1's 5 federation UIDs must never overlap the 9 guardrailed UIDs",
        )
        for uid in GUARDRAILED_9:
            with self.subTest(uid=uid):
                found = lock_dev_spec_mod.find_correlated_activation(uid, files_dir=FILES_DIR)
                self.assertIsNotNone(
                    found,
                    f"guardrailed UID {uid} should now be correlated — cured by the "
                    "follow-up work-order (event 00005914, register 2b12e41d) after "
                    "item 1 deliberately deferred it",
                )


# ===========================================================================
# ITEM 2 — the coupling runnable-lock (tropo-lock-dev-spec.py, ADR-052)
# ===========================================================================

class TestItem2LockGestureIsolatedFixture(unittest.TestCase):
    """Fully isolated tmp-dir fixture proving lock_dev_spec()'s OWN atomicity /
    idempotency / refusal logic — using an injected stand-in activate-script
    (pipeline-activate.py itself cannot run against a fixture dir; see module
    docstring). This is the StudioFixture-style isolated-temp-dir pattern."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="lock_dev_spec_fixture_"))
        self.files_dir = self.tmp / "vault" / "files"
        self.files_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_dev_spec(self, uid: str, status: str = "draft") -> Path:
        path = self.files_dir / f"{uid}.md"
        path.write_text(
            "---\n"
            f"uid: {uid}\n"
            "type: dev-spec\n"
            f"status: {status}\n"
            "state: active\n"
            "title: \"fixture dev-spec\"\n"
            "modified: '2026-01-01'\n"
            "modified_by: fixture-setup\n"
            "---\n\n# fixture\n",
            encoding="utf-8",
        )
        return path

    def _write_stub_activate_script(self, succeed: bool, activation_uid: str = "aaaa1111") -> Path:
        """A tiny throwaway stand-in for pipeline-activate.py. On success it
        writes a real type:activation file (correlated to --dev-spec-uid) into
        THIS fixture's vault/files/ — proving the ordering (activation-on-disk
        BEFORE the dev-spec is flipped) without needing the real, vault-root-
        hardcoded e337f1dd.py."""
        script = self.tmp / "stub_activate.py"
        script.write_text(
            "import argparse, sys\n"
            "p = argparse.ArgumentParser()\n"
            "p.add_argument('--pipeline-uid', required=True)\n"
            "p.add_argument('--activated-by', required=True)\n"
            "p.add_argument('--cycle-context', default='')\n"
            "p.add_argument('--dev-spec-uid', required=True)\n"
            "args = p.parse_args()\n"
            f"SUCCEED = {succeed!r}\n"
            f"ACT_UID = {activation_uid!r}\n"
            "if not SUCCEED:\n"
            "    print('stub: refusing on purpose', file=sys.stderr)\n"
            "    sys.exit(1)\n"
            "import pathlib\n"
            f"files_dir = pathlib.Path({str(self.files_dir)!r})\n"
            "(files_dir / (ACT_UID + '.md')).write_text(\n"
            "    '---\\n'\n"
            "    'uid: ' + ACT_UID + '\\n'\n"
            "    'type: activation\\n'\n"
            "    'status: active\\n'\n"
            "    'dev_spec_uid: ' + args.dev_spec_uid + '\\n'\n"
            "    '---\\n\\nstub activation\\n'\n"
            ")\n"
            "print(ACT_UID)\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return script

    def test_success_path_opens_activation_then_locks_atomically(self) -> None:
        self._write_dev_spec("bbbb2222", status="draft")
        stub = self._write_stub_activate_script(succeed=True, activation_uid="cccc3333")

        code, msg = lock_dev_spec_mod.lock_dev_spec(
            "bbbb2222", "talos-test", pipeline_uid="cd1fcd25", cycle_context="fixture test",
            files_dir=self.files_dir, vault_root=self.tmp, activate_script=stub,
        )
        self.assertEqual(code, 0, msg)
        self.assertIn("LOCKED", msg)
        self.assertIn("cccc3333", msg)

        # Prove it by re-reading the fixture file, not by asserting in-memory state.
        new_fm = lock_dev_spec_mod.parse_frontmatter((self.files_dir / "bbbb2222.md").read_text())
        self.assertEqual(new_fm.get("status"), "locked")
        self.assertEqual(new_fm.get("locked_by"), "talos-test")
        self.assertTrue(new_fm.get("locked_at"))
        self.assertEqual(new_fm.get("dev_spec_activation_uid"), "cccc3333")
        # The activation really exists on disk, correlated.
        act_fm = lock_dev_spec_mod.parse_frontmatter((self.files_dir / "cccc3333.md").read_text())
        self.assertEqual(act_fm.get("dev_spec_uid"), "bbbb2222")

    def test_failure_path_leaves_dev_spec_byte_for_byte_unchanged(self) -> None:
        """The atomicity guarantee: if the activation cannot be opened, the
        dev-spec is refused — NOT partially updated. Proven by comparing raw
        bytes before and after the failed attempt."""
        path = self._write_dev_spec("dddd4444", status="draft")
        before = path.read_bytes()
        stub = self._write_stub_activate_script(succeed=False)

        code, msg = lock_dev_spec_mod.lock_dev_spec(
            "dddd4444", "talos-test", files_dir=self.files_dir, vault_root=self.tmp,
            activate_script=stub,
        )
        self.assertEqual(code, 1, msg)
        self.assertIn("ABORTING THE LOCK", msg)

        after = path.read_bytes()
        self.assertEqual(before, after, "dev-spec file must be byte-for-byte unchanged on a refused lock")
        # And no activation file leaked onto disk either.
        self.assertEqual(list(self.files_dir.glob("*.md")), [path])

    def test_idempotent_reuse_when_already_correlated_no_duplicate_activation(self) -> None:
        """If a correlated activation ALREADY exists (e.g. a prior retroactive
        feed-the-pipeline cure), the tool must REUSE it, not open a duplicate."""
        self._write_dev_spec("eeee5555", status="draft")
        (self.files_dir / "ffff6666.md").write_text(
            "---\nuid: ffff6666\ntype: activation\nstatus: retired\n"
            "dev_spec_uid: eeee5555\n---\n\npre-existing activation\n",
            encoding="utf-8",
        )
        # A stub that would FAIL if actually invoked — proves it was never called.
        stub = self._write_stub_activate_script(succeed=False)

        code, msg = lock_dev_spec_mod.lock_dev_spec(
            "eeee5555", "talos-test", files_dir=self.files_dir, vault_root=self.tmp,
            activate_script=stub,
        )
        self.assertEqual(code, 0, msg)
        self.assertIn("ffff6666", msg)
        self.assertIn("reused", msg)
        # No second activation was minted.
        activations = [f for f in self.files_dir.glob("*.md") if f.stem != "eeee5555"]
        self.assertEqual([f.stem for f in activations], ["ffff6666"])

    def test_refuses_to_relock_already_locked_dev_spec(self) -> None:
        path = self._write_dev_spec("11119999", status="locked")
        before = path.read_bytes()
        stub = self._write_stub_activate_script(succeed=True)

        code, msg = lock_dev_spec_mod.lock_dev_spec(
            "11119999", "talos-test", files_dir=self.files_dir, vault_root=self.tmp,
            activate_script=stub,
        )
        self.assertEqual(code, 1, msg)
        self.assertIn("already status:locked", msg)
        self.assertEqual(path.read_bytes(), before)

    def test_refuses_non_dev_spec_type(self) -> None:
        path = self.files_dir / "22228888.md"
        path.write_text("---\nuid: 22228888\ntype: note\nstatus: draft\n---\n\nnot a dev-spec\n", encoding="utf-8")
        stub = self._write_stub_activate_script(succeed=True)
        code, msg = lock_dev_spec_mod.lock_dev_spec(
            "22228888", "talos-test", files_dir=self.files_dir, vault_root=self.tmp,
            activate_script=stub,
        )
        self.assertEqual(code, 1, msg)
        self.assertIn("not type:dev-spec", msg)


class TestItem2LockGestureRealVaultIntegration(unittest.TestCase):
    """ONE end-to-end integration proof against the REAL pipeline-activate.py +
    the REAL vault, using the plant-and-cleanup adversarial-gauntlet pattern
    test_capability_chain_smoke.py already established for exactly this class
    of component (wired to the real vault path by construction). Plants a
    throwaway TEST FIXTURE dev-spec, locks it through the real tool end-to-end,
    asserts the coupling gate does NOT flag it, then removes every artifact."""

    PLANT_UID = "10c40001"

    def setUp(self) -> None:
        self.plant_path = FILES_DIR / f"{self.PLANT_UID}.md"
        if self.plant_path.exists():
            self.fail(f"plant path {self.plant_path} already exists — refusing to overwrite")
        self.plant_path.write_text(
            "---\n"
            f"uid: {self.PLANT_UID}\n"
            "type: dev-spec\n"
            "status: draft\n"
            "state: active\n"
            "title: \"TEST FIXTURE — lock-dev-spec real-vault integration plant (deleted immediately)\"\n"
            "target_release: \"0.0.0-test\"\n"
            "target_stream: null\n"
            "committed_substrate:\n"
            "  - target: \"vault/tools/tests/test_systemic_feed_pipeline_v184.py\"\n"
            "    change_class: \"AMENDED\"\n"
            "    description: \"test fixture plant\"\n"
            "acceptance_criteria:\n"
            "  - \"test fixture only\"\n"
            "owner: talos\n"
            "author: talos\n"
            "created: '2026-07-07'\n"
            "created_by: talos-t25\n"
            "modified: '2026-07-07'\n"
            "modified_by: talos-t25\n"
            "schema_version: 2\n"
            "tags: [test-fixture]\n"
            "---\n\n# TEST FIXTURE\n\nDeleted immediately after this gauntlet runs.\n",
            encoding="utf-8",
        )
        self._minted_activation_uid = None
        self._minted_root_uid = None

    def tearDown(self) -> None:
        if self.plant_path.exists():
            self.plant_path.unlink()
        if self._minted_activation_uid:
            act_path = FILES_DIR / f"{self._minted_activation_uid}.md"
            if act_path.exists():
                # Read the root project uid before deleting, if not already known.
                fm = lock_dev_spec_mod.parse_frontmatter(act_path.read_text())
                root_uid = fm.get("activation_root_project")
                act_path.unlink()
                if root_uid:
                    root_path = FILES_DIR / f"{root_uid}.md"
                    if root_path.exists():
                        root_path.unlink()
                    manifest_dir = ROOT / "playbook-runs" / f"pipeline-activate-{self._minted_activation_uid}"
                    if manifest_dir.exists():
                        shutil.rmtree(manifest_dir, ignore_errors=True)

    def test_real_lock_gesture_opens_real_activation_and_coupling_gate_stays_clean(self) -> None:
        code, msg = lock_dev_spec_mod.lock_dev_spec(
            self.PLANT_UID, "talos-t25-test",
            pipeline_uid="cd1fcd25",
            cycle_context="test_systemic_feed_pipeline_v184.py real-vault integration plant (deleted immediately)",
        )
        self.assertEqual(code, 0, msg)
        m = re.search(r"activation=([0-9a-f]{8})", msg)
        self.assertIsNotNone(m, msg)
        self._minted_activation_uid = m.group(1)

        # Re-read the plant from disk — proves the write really landed.
        fm = lock_dev_spec_mod.parse_frontmatter(self.plant_path.read_text())
        self.assertEqual(fm.get("status"), "locked")
        self.assertEqual(fm.get("dev_spec_activation_uid"), self._minted_activation_uid)

        # The coupling gate (8f15f08d, UNMODIFIED by this build) must NOT flag
        # the freshly-locked plant — the happy path is clean.
        findings, _checked, _violations = tropo_validate.check_dev_spec_activation_coupling(ROOT)
        flagged = [f for f in findings if self.PLANT_UID in f]
        self.assertEqual(flagged, [], f"coupling gate incorrectly flagged the atomically-locked plant: {flagged}")


class TestCouplingGateBackstopNotRegressed(unittest.TestCase):
    """Re-proves 8f15f08d's own gauntlets still pass UNCHANGED — Item 2 must
    not remove or weaken check_dev_spec_activation_coupling."""

    def test_coupling_gate_still_flags_a_genuinely_off_pipeline_plant(self) -> None:
        """Same shape as test_capability_chain_smoke.py's own adversarial plant,
        run directly here for a fast, local non-regression signal."""
        plant_uid = "1ockfeed"
        plant_path = FILES_DIR / f"{plant_uid}.md"
        if plant_path.exists():
            self.fail(f"plant path {plant_path} already exists — refusing to overwrite")
        plant_path.write_text(
            "---\n"
            f"uid: {plant_uid}\n"
            "type: dev-spec\n"
            "status: locked\n"
            "title: \"TEST FIXTURE — coupling-gate non-regression plant\"\n"
            "---\n\n# fixture\n",
            encoding="utf-8",
        )
        try:
            findings, _checked, violations = tropo_validate.check_dev_spec_activation_coupling(ROOT)
            self.assertGreaterEqual(violations, 1)
            self.assertTrue(any(plant_uid in f for f in findings), findings)
        finally:
            plant_path.unlink()
        # And the finding disappears once removed.
        findings2, _c, _v = tropo_validate.check_dev_spec_activation_coupling(ROOT)
        self.assertFalse(any(plant_uid in f for f in findings2))

    def test_allowlist_and_terminal_status_constants_unmodified(self) -> None:
        """UPDATED 2026-07-08 (Talos T26, register 2b12e41d / event 00005914 Item 4):
        this test originally asserted item 1/item 2 of THIS module's own work-order
        left the allowlist untouched (a different, later item — Item 4 — was the one
        authorized to empty it). That later item has now run: the 9-UID debt named in
        check_dev_spec_activation_coupling's own docstring is cured, and the allowlist
        ratcheted from {92093c81, 8e551957} to frozenset() per 8f15f08d's design. The
        _TERMINAL_BUILD_STATUS constant is genuinely unmodified by any item — kept."""
        self.assertEqual(tropo_validate.DEV_SPEC_ACTIVATION_COUPLING_ALLOWLIST, frozenset())
        self.assertEqual(tropo_validate._TERMINAL_BUILD_STATUS, frozenset({"mike-signed-accepted"}))


if __name__ == "__main__":
    unittest.main()
