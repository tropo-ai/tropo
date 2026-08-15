"""What both ignitions must write (0a0a6777 AC2/AC4; argus-a147 NO-GO item 4).

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_ignition_snapshots
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest

import yaml
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from lib import ignition  # noqa: E402

STEPS = ["0c6518ef", "fa3a49c8", "0b6b244c"]


def _reader(status="active", version="2.0.0"):
    def read(uid):
        return {"frontmatter": {"uid": uid, "status": status, "version": version}}
    return read


class ARootMustBeFitToIgnite(unittest.TestCase):

    def test_an_active_versioned_root_ignites(self) -> None:
        """Control."""
        snap = ignition.snapshot_declarations("cd1fcd25", _reader(), lambda u: STEPS)
        self.assertEqual(snap.pipeline_version, "2.0.0")
        self.assertEqual(list(snap.steps), STEPS)
        self.assertEqual(len(snap.digest), 64)

    def test_a_draft_root_is_refused(self) -> None:
        """The live release root 634913c2 is draft at version 1.0.0, and the
        first ignition stamped 2.0 on it regardless."""
        with self.assertRaises(ignition.IgnitionRefusal) as caught:
            ignition.snapshot_declarations("634913c2", _reader(status="draft"),
                                           lambda u: STEPS)
        self.assertIn("draft", str(caught.exception))

    def test_an_unversioned_root_is_refused(self) -> None:
        with self.assertRaises(ignition.IgnitionRefusal) as caught:
            ignition.snapshot_declarations("cd1fcd25", _reader(version=""),
                                           lambda u: STEPS)
        self.assertIn("no version", str(caught.exception))

    def test_a_root_with_no_steps_is_refused(self) -> None:
        """A run with no declarations has no snapshot to execute, so it would
        fall back to whatever the definition says later — the §1 contract swap,
        reintroduced by the ignition itself."""
        with self.assertRaises(ignition.IgnitionRefusal) as caught:
            ignition.snapshot_declarations("cd1fcd25", _reader(), lambda u: [])
        self.assertIn("zero steps", str(caught.exception))

    def test_the_version_is_read_not_assumed(self) -> None:
        """NO-GO item 4 verbatim: hardcoded 2.0 against a 1.0.0 root."""
        snap = ignition.snapshot_declarations(
            "634913c2", _reader(status="active", version="1.0.0"), lambda u: STEPS)
        self.assertEqual(snap.pipeline_version, "1.0.0")

    def test_the_digest_changes_when_the_declarations_do(self) -> None:
        base = ignition.snapshot_declarations("cd1fcd25", _reader(), lambda u: STEPS)
        fewer = ignition.snapshot_declarations("cd1fcd25", _reader(), lambda u: STEPS[:2])
        reordered = ignition.snapshot_declarations(
            "cd1fcd25", _reader(), lambda u: list(reversed(STEPS)))
        self.assertNotEqual(base.digest, fewer.digest)
        self.assertNotEqual(base.digest, reordered.digest)

    def test_the_digest_is_stable_for_the_same_declarations(self) -> None:
        a = ignition.snapshot_declarations("cd1fcd25", _reader(), lambda u: STEPS)
        b = ignition.snapshot_declarations("cd1fcd25", _reader(), lambda u: STEPS)
        self.assertEqual(a.digest, b.digest)


class TheSnapshotPinsWhatStepsSAYNotJustTheirNames(unittest.TestCase):
    """Blocker 4. A UID list pins which steps a run holds and nothing about
    their content, so every exit criterion, verification command, trust level
    and dependency could be rewritten after ignition while the snapshot still
    verified."""

    def _reader(self, bodies):
        def read(uid):
            return {"frontmatter": {"uid": uid, "status": "active", "version": "2.0.0"}}
        return read

    def test_editing_a_step_changes_the_digest(self) -> None:
        bodies = {"cd1fcd25": b"root\n", "0c6518ef": b"specify v1\n",
                  "fa3a49c8": b"build\n"}
        before = ignition.snapshot_declarations(
            "cd1fcd25", self._reader(bodies), lambda u: ["0c6518ef", "fa3a49c8"],
            read_bytes=bodies.get)

        bodies["0c6518ef"] = b"specify v2 - exit criteria rewritten\n"
        after = ignition.snapshot_declarations(
            "cd1fcd25", self._reader(bodies), lambda u: ["0c6518ef", "fa3a49c8"],
            read_bytes=bodies.get)

        self.assertEqual(list(before.steps), list(after.steps),
                         "the UID list is unchanged, which is the whole point")
        self.assertNotEqual(before.digest, after.digest,
                            "a rewritten step did not move the declaration digest")

    def test_the_root_itself_is_pinned_too(self) -> None:
        bodies = {"cd1fcd25": b"root v1\n", "0c6518ef": b"specify\n"}
        before = ignition.snapshot_declarations(
            "cd1fcd25", self._reader(bodies), lambda u: ["0c6518ef"],
            read_bytes=bodies.get)
        bodies["cd1fcd25"] = b"root v2\n"
        after = ignition.snapshot_declarations(
            "cd1fcd25", self._reader(bodies), lambda u: ["0c6518ef"],
            read_bytes=bodies.get)
        self.assertNotEqual(before.digest, after.digest)

    def test_an_unreadable_step_refuses_rather_than_pinning_a_name(self) -> None:
        with self.assertRaises(ignition.IgnitionRefusal) as caught:
            ignition.snapshot_declarations(
                "cd1fcd25", self._reader({}), lambda u: ["0c6518ef"],
                read_bytes=lambda uid: None)
        self.assertIn("no readable bytes", str(caught.exception))

    def test_a_snapshot_without_bytes_says_so_rather_than_implying_it_pinned_them(self) -> None:
        """"I did not capture the contents" and "the contents matched" must be
        distinguishable to a later reader."""
        snap = ignition.snapshot_declarations(
            "cd1fcd25", self._reader({}), lambda u: ["0c6518ef"])
        self.assertFalse(snap.bytes_pinned)
        self.assertFalse(snap.as_dict()["step_content_digests"])

    def test_the_snapshot_dict_carries_the_per_step_digests(self) -> None:
        bodies = {"cd1fcd25": b"root\n", "0c6518ef": b"specify\n"}
        snap = ignition.snapshot_declarations(
            "cd1fcd25", self._reader(bodies), lambda u: ["0c6518ef"],
            read_bytes=bodies.get)
        body = snap.as_dict()
        self.assertTrue(body["bytes_pinned"])
        self.assertEqual(set(body["step_content_digests"]), {"cd1fcd25", "0c6518ef"})


class TheSnapshotIsEXECUTABLEAfterItsSourcesAreGone(unittest.TestCase):
    """argus-a147, second pass: hashes DETECT change, they cannot EXECUTE.

    §1 says a started run executes only its immutable declaration snapshot. A
    snapshot of digests satisfies neither half of that: edit the sources and
    there is nothing to run from but the edited entries, delete them and there
    is nothing to run at all. The pinned contract died with the files it merely
    fingerprinted.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="snapshot-exec-")).resolve()
        self.files = self.tmp / "vault" / "files"
        self.files.mkdir(parents=True)
        for uid, body in (("cd1fcd25", "# dev-pipeline root\nversion: 2.0.0\n"),
                          ("0c6518ef", "# specify\nexit_criteria: [a, b]\n"),
                          ("fa3a49c8", "# build\nverification_command: pytest\n")):
            (self.files / f"{uid}.md").write_text(body, encoding="utf-8")

        self.snapshot_path = self.tmp / "declaration-snapshot.json"
        snap = ignition.snapshot_declarations(
            "cd1fcd25",
            lambda uid: {"frontmatter": {"status": "active", "version": "2.0.0"}},
            lambda uid: ["0c6518ef", "fa3a49c8"],
            read_bytes=lambda uid: (self.files / f"{uid}.md").read_bytes()
            if (self.files / f"{uid}.md").is_file() else None,
        )
        self.snapshot_path.write_text(
            json.dumps(snap.as_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def test_the_run_still_executes_after_EVERY_source_node_is_deleted(self) -> None:
        """The claim in its strongest form: delete all of them.

        If the loader falls back to the vault for anything at all, this fails —
        there is no vault entry left to fall back to.
        """
        for path in list(self.files.glob("*.md")):
            path.unlink()
        self.assertEqual(list(self.files.glob("*.md")), [])

        loaded = ignition.load_snapshot(self.snapshot_path)

        self.assertEqual(loaded["declared_steps"], ["0c6518ef", "fa3a49c8"])
        self.assertIn("exit_criteria: [a, b]", loaded["declarations"]["0c6518ef"])
        self.assertIn("verification_command: pytest",
                      loaded["declarations"]["fa3a49c8"])
        self.assertIn("# dev-pipeline root", loaded["declarations"]["cd1fcd25"])

    def test_mutating_every_source_node_does_not_change_what_the_run_executes(self) -> None:
        """Insulation, not merely detection. The run carries on unaffected."""
        before = ignition.load_snapshot(self.snapshot_path)
        for uid in ("cd1fcd25", "0c6518ef", "fa3a49c8"):
            (self.files / f"{uid}.md").write_text(
                f"# {uid} REWRITTEN\nexit_criteria: [everything, now]\n",
                encoding="utf-8")

        after = ignition.load_snapshot(self.snapshot_path)

        self.assertEqual(before, after,
                         "editing the sources changed what the snapshot executes")
        self.assertNotIn("REWRITTEN", json.dumps(after["declarations"]))

    def test_a_snapshot_edited_after_the_lock_is_refused_not_executed(self) -> None:
        body = json.loads(self.snapshot_path.read_text())
        body["declarations"]["0c6518ef"] = "# specify\nexit_criteria: []\n"
        self.snapshot_path.write_text(json.dumps(body))

        with self.assertRaises(ignition.SnapshotRefusal) as caught:
            ignition.load_snapshot(self.snapshot_path)
        self.assertIn("does not match its recorded digest", str(caught.exception))

    def test_a_snapshot_whose_own_digest_was_rewritten_is_refused(self) -> None:
        """Corrupt the content AND its digest together, so they agree with each
        other and not with the snapshot digest."""
        body = json.loads(self.snapshot_path.read_text())
        forged = "# specify\nexit_criteria: []\n"
        body["declarations"]["0c6518ef"] = forged
        body["step_content_digests"]["0c6518ef"] = hashlib.sha256(
            forged.encode("utf-8")).hexdigest()
        self.snapshot_path.write_text(json.dumps(body))

        with self.assertRaises(ignition.SnapshotRefusal) as caught:
            ignition.load_snapshot(self.snapshot_path)
        self.assertIn("declaration_digest does not match", str(caught.exception))

    def test_a_hashes_only_snapshot_is_refused_as_unexecutable(self) -> None:
        """The shape that existed before this fix, planted deliberately."""
        body = json.loads(self.snapshot_path.read_text())
        body.pop("declarations")
        self.snapshot_path.write_text(json.dumps(body))

        with self.assertRaises(ignition.SnapshotRefusal) as caught:
            ignition.load_snapshot(self.snapshot_path)
        self.assertIn("cannot be executed", str(caught.exception))

    def test_the_control_an_untouched_snapshot_loads(self) -> None:
        """Without this, every refusal above passes for a loader that refuses all."""
        loaded = ignition.load_snapshot(self.snapshot_path)
        self.assertEqual(len(loaded["declarations"]), 3)


class TheSpecComponentsAreHashedSeparately(unittest.TestCase):
    """AC2 names spec, ACs and committed substrate as three things.

    A whole-file hash proves the spec changed and cannot say what changed, so it
    cannot tell an editorial fix from someone rewriting the criteria the run is
    judged against.
    """

    SPEC = ("---\nuid: 5ec00001\ntype: dev-spec\nstatus: draft\n"
            "acceptance_criteria:\n  - id: AC1\n    behavior: original\n"
            "committed_substrate:\n  - target: a.py\n    change_class: AMENDED\n"
            "---\n\n# spec\n\nprose\n")

    def test_rewriting_the_acceptance_criteria_moves_only_that_digest(self) -> None:
        before = ignition.spec_component_digests(self.SPEC)
        after = ignition.spec_component_digests(
            self.SPEC.replace("behavior: original", "behavior: REWRITTEN"))
        self.assertNotEqual(before["acceptance_criteria_sha256"],
                            after["acceptance_criteria_sha256"])
        self.assertEqual(before["committed_substrate_sha256"],
                         after["committed_substrate_sha256"],
                         "an AC edit moved the committed-substrate digest too")

    def test_editing_the_prose_moves_neither(self) -> None:
        after = ignition.spec_component_digests(
            self.SPEC.replace("prose", "different prose entirely"))
        before = ignition.spec_component_digests(self.SPEC)
        self.assertEqual(before, after,
                         "a body edit moved a frontmatter component digest")

    def test_absence_is_recorded_rather_than_hashed_as_nothing(self) -> None:
        bare = "---\nuid: 5ec00002\ntype: dev-spec\nstatus: draft\n---\n\n# spec\n"
        digests = ignition.spec_component_digests(bare)
        self.assertFalse(digests["acceptance_criteria_present"])
        self.assertFalse(digests["committed_substrate_present"])


class InputsAreHashedFromDisk(unittest.TestCase):

    def test_every_named_input_is_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec.md"
            spec.write_text("the spec\n")
            snap = ignition.input_snapshot([("dev_spec", spec)])
            self.assertEqual(
                snap["dev_spec_sha256"],
                hashlib.sha256(b"the spec\n").hexdigest())

    def test_a_missing_input_refuses_rather_than_hashing_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ignition.IgnitionRefusal) as caught:
                ignition.input_snapshot([("dev_spec", Path(tmp) / "absent.md")])
            self.assertIn("does not resolve", str(caught.exception))

    def test_the_hash_tracks_the_bytes_not_a_parse(self) -> None:
        """A projection moves when the parser changes, and then an 'immutable'
        hash moves without the input moving."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec.md"
            spec.write_text("a\n")
            first = ignition.input_snapshot([("dev_spec", spec)])["dev_spec_sha256"]
            spec.write_text("b\n")
            second = ignition.input_snapshot([("dev_spec", spec)])["dev_spec_sha256"]
            self.assertNotEqual(first, second)


class TheActivationRootExists(unittest.TestCase):
    """Without a root, Rule 12 has nothing to archive and final_commit has
    nowhere to land."""

    def test_the_root_carries_what_rule_12_closes_on(self) -> None:
        text = ignition.render_activation_root(
            "1111aaaa", "2222bbbb", "3333cccc", "dev-spec", "talos",
            "2026-08-10", "cd1fcd25")
        # Asserted against PARSED values, not rendered text. The writer now
        # quotes UIDs that look numeric — `1111aaaa` would otherwise be read
        # back as a number in some YAML dialects, which is the bug the quoting
        # prevents — and a literal `uid: 1111aaaa` match called that fix a
        # regression. What Rule 12 needs is the FIELD, at any quoting.
        fields = yaml.safe_load(text.split("---")[1])
        self.assertEqual(fields.get("type"), "project")
        self.assertEqual(str(fields.get("uid")), "1111aaaa")
        self.assertEqual(str(fields.get("activated_by_pipeline")), "cd1fcd25")
        self.assertEqual(str(fields.get("activation_uid")), "2222bbbb")
        self.assertEqual(str(fields.get("dev_spec_uid")), "3333cccc")
        self.assertEqual(fields.get("state"), "active")

    def test_the_live_release_root_is_active_after_stage9(self) -> None:
        """Stage 9 deliberately ends the draft-root era.

        Draft refusal remains mutation-backed by ``test_a_draft_root_is_refused``;
        the live corpus now proves the reviewed v1 graph is available to a
        release-plan lock rather than permanently parked behind that refusal.
        """
        root = (TOOLS.parent / "files" / "634913c2.md").read_text(encoding="utf-8")
        fields = yaml.safe_load(root.split("---")[1])
        self.assertEqual(fields.get("status"), "active")
        self.assertEqual(str(fields.get("activated_under")), "0a0a6777")
        # Pinned by parsed field rather than literal text, and to the CURRENT
        # amended version. The v1.0.1 amendment added the Assemble -> Verify ->
        # Publish cross-stage barriers so the declared sequence is executable;
        # a literal `version: 1.0.0` match read that correct fix as a
        # regression, which is a snapshot testing its own staleness.
        self.assertEqual(str(fields.get("version")), "1.0.1")


if __name__ == "__main__":
    unittest.main()
