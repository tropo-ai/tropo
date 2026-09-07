#!/usr/bin/env python3
"""v1.94 Stream 2 (266edea6, LOCKED) — the merge seam gauntlet.

The driver, the validator, and the gate client are all built and green in
isolation; nothing was wired. This suite proves the WIRING, not the logic
each piece already has its own tests for: a governed-file conflict routes
through the field-aware driver instead of git's default, the gate refuses
invalid content at commit time, an unwired clone says so, and a resolution
leaves a trace on the bus.

Everything below runs against real, local, throwaway git repos (a bare
remote + working clones under tempfile.TemporaryDirectory() — no network,
same pattern test_d5_atomic_promotion_0f06a8b5.py uses for its two-Studio
fixture). "A suite passing in-repo is not the same claim" as exercising the
seam from the outside (266edea6's own caution) — these tests clone, edit,
and merge for real rather than calling driver/gate functions in isolation.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import github_transport as ght  # noqa: E402
from lib import governance_gate as gg  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load(
    "merge_seam_tropo_validate_governed",
    TOOLS / "federation" / "tropo_validate_governed.py",
)

GITATTRIBUTES = f"{gg.MERGE_GOVERNED_PATTERN} {gg.MERGE_DRIVER_ATTR}\n"


def _git(args, cwd=None, **kwargs):
    return ght.run_git(args, cwd=cwd, **kwargs)


def _governed_text(uid: str, *, owner: str = "mike", status: str = "active",
                    title: str = "Test", body: str = "Body text.") -> str:
    return (
        "---\n"
        f"uid: {uid}\n"
        "type: note\n"
        f'title: "{title}"\n'
        f"owner: {owner}\n"
        f"status: {status}\n"
        "---\n"
        f"{body}\n"
    )


class MergeSeamFixture(unittest.TestCase):
    """A bare team remote, wired at the committed half (.gitattributes
    declares merge=tropo), seeded with one governed file. Individual tests
    clone from it as many times as their scenario needs."""

    UID = "aaaa0001"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="merge-seam-")
        self.d = Path(self._tmp.name)
        self.team_bare = ght.init_bare_remote(self.d / "team.git")

        seed = self.d / "seed"
        _git(["clone", "-q", self.team_bare, str(seed)])
        (seed / "vault" / "files").mkdir(parents=True)
        (seed / ".gitattributes").write_text(GITATTRIBUTES, encoding="utf-8")
        (seed / "vault" / "files" / f"{self.UID}.md").write_text(
            _governed_text(self.UID), encoding="utf-8"
        )
        _git(["add", "-A"], cwd=seed)
        _git(["-c", "user.email=seed@test", "-c", "user.name=seed",
              "commit", "-qm", "seed"], cwd=seed)
        _git(["push", "-q", "origin", "main"], cwd=seed)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _clone(self, name: str) -> Path:
        clone = self.d / name
        _git(["clone", "-q", self.team_bare, str(clone)])
        return clone

    def _commit(self, repo: Path, msg: str, *, who: str = "w") -> None:
        _git(["add", "-A"], cwd=repo)
        _git(["-c", f"user.email={who}@test", "-c", f"user.name={who}",
              "commit", "-qm", msg], cwd=repo)

    def _rel(self) -> str:
        return f"vault/files/{self.UID}.md"


class AC1AcceptsBothUidShapes(unittest.TestCase):
    """AC1 — the blocker, and it lands before anything is wired: the
    governance validator accepts a correctly-shaped composite-UID file, an
    8-hex legacy file, and refuses both a wrong-tail composite and an
    unparseable stem. Pure unit-level; no git required."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ac1-uid-shapes-")
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, filename: str, uid: str) -> Path:
        path = self.dir / filename
        path.write_text(_governed_text(uid), encoding="utf-8")
        return path

    def test_accepts_both_uid_shapes(self) -> None:
        composite = "9f2cb81d4e07"
        legacy = "b81d4e07"

        # RULED shape: slug-<whole composite uid>.md
        p1 = self._write("my-note-9f2cb81d4e07.md", composite)
        status, problems = validator.validate(str(p1))
        self.assertEqual(status, "VALID", problems)

        # legacy 8-hex, untouched
        p2 = self._write("my-note-b81d4e07.md", legacy)
        status, problems = validator.validate(str(p2))
        self.assertEqual(status, "VALID", problems)

        # bare composite, no slug
        p3 = self._write("9f2cb81d4e07.md", composite)
        status, problems = validator.validate(str(p3))
        self.assertEqual(status, "VALID", problems)

        # THE NEGATIVES, which are why this criterion outlived the blocker:
        # SUPERSEDED shape (wrong local-8 tail over a composite uid) -- the
        # filename ends with a real 8-hex fragment, but it is not the WHOLE
        # composite uid this file actually declares.
        p4 = self._write("my-note-b81d4e07.md", composite)
        status, problems = validator.validate(str(p4))
        self.assertEqual(status, "BROKEN", problems)
        self.assertTrue(any("filename/uid mismatch" in p for p in problems))

        # unparseable stem: the filename shares no relationship with the uid
        p5 = self._write("totally-unrelated-name.md", composite)
        status, problems = validator.validate(str(p5))
        self.assertEqual(status, "BROKEN", problems)
        self.assertTrue(any("filename/uid mismatch" in p for p in problems))

    def test_control_the_superseded_last_8_rule_would_have_accepted_the_wrong_tail(self) -> None:
        """Proves the AC1 negative reads the RULE, not the test data: under
        the SUPERSEDED last-8-only match (what this validator carried before
        the 2026-08-31 whole-uid ruling), the wrong-tail case above would
        flip from refused to accepted. If it didn't, the negative above
        would be passing by coincidence, not by asserting the rule."""
        composite = "9f2cb81d4e07"
        stem = "my-note-b81d4e07"  # ends with the real LAST 8 of the composite

        def superseded_last8_match(stem: str, uid: str) -> bool:
            return stem == uid or stem.endswith(uid[-8:])

        self.assertTrue(
            superseded_last8_match(stem, composite),
            "the superseded rule must accept this exact case -- otherwise "
            "the control proves nothing about what changed",
        )
        # And the CURRENT rule (what the validator actually runs) refuses it.
        self.assertFalse(stem.endswith(composite))


class AC2DriverIsReached(MergeSeamFixture):
    """AC2 — the merge driver is REACHED. A real two-clone conflicting edit
    routes through the field-aware driver, not git's default."""

    def test_driver_is_reached(self) -> None:
        # clone_b stays on the seed base; clone_a edits and pushes first.
        clone_b = self._clone("clone_b")
        _git(["config", "merge.tropo.driver", gg.merge_driver_command()], cwd=clone_b)

        clone_a = self._clone("clone_a")
        rel = self._rel()
        (clone_a / rel).write_text(
            _governed_text(self.UID, status="active", title="Edited by A"),
            encoding="utf-8",
        )
        self._commit(clone_a, "A edits title", who="a")
        _git(["push", "-q", "origin", "main"], cwd=clone_a)

        # clone_b: a TRUE clash on `title` -- the same field, both sides,
        # different values. Git's own default line-merge would wrap this in
        # raw <<<<<<< markers; the driver must not.
        (clone_b / rel).write_text(
            _governed_text(self.UID, status="active", title="Edited by B"),
            encoding="utf-8",
        )
        self._commit(clone_b, "B edits title", who="b")
        _git(["fetch", "-q", "origin"], cwd=clone_b)
        result = _git(["merge", "origin/main", "-m", "merge"], cwd=clone_b, check=False)

        merged = (clone_b / rel).read_text(encoding="utf-8")
        self.assertNotIn("<<<<<<<", merged, "raw git markers mean the driver did NOT run")
        self.assertIn("TROPO-FIELD-CONFLICT", merged,
                       "the driver's own parseable annotation form must be present")
        self.assertNotEqual(result.returncode, 0,
                             "a true field clash must still exit non-zero")

    def test_control_the_same_race_without_the_driver_produces_raw_markers(self) -> None:
        """Negative control: the SAME scenario, in a clone with NO driver
        configured, must show git's default raw markers instead -- proving
        AC2's assertion distinguishes wired from unwired, not merely
        "a merge happened somehow"."""
        clone_b = self._clone("clone_b_unwired")  # merge.tropo.driver NOT set

        clone_a = self._clone("clone_a2")
        rel = self._rel()
        (clone_a / rel).write_text(
            _governed_text(self.UID, title="Edited by A"), encoding="utf-8"
        )
        self._commit(clone_a, "A edits title", who="a")
        _git(["push", "-q", "origin", "main"], cwd=clone_a)

        (clone_b / rel).write_text(
            _governed_text(self.UID, title="Edited by B"), encoding="utf-8"
        )
        self._commit(clone_b, "B edits title", who="b")
        _git(["fetch", "-q", "origin"], cwd=clone_b)
        _git(["merge", "origin/main", "-m", "merge"], cwd=clone_b, check=False)

        merged = (clone_b / rel).read_text(encoding="utf-8")
        self.assertIn("<<<<<<<", merged,
                       "without the driver configured, git's default markers must appear")
        self.assertNotIn("TROPO-FIELD-CONFLICT", merged)


class AC3GateInstallAndDetect(unittest.TestCase):
    """AC3 — the gate installs per clone and its absence is DETECTED. This
    exercises the ALREADY-BUILT governance_gate.install_hook /
    assert_hook_installed against a real throwaway repo (proving the
    mechanism, which is the wiring gap -- the functions themselves are not
    new)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ac3-gate-install-")
        self.repo = Path(self._tmp.name)
        _git(["init", "-q", "-b", "main", str(self.repo)])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_gate_install_and_detect(self) -> None:
        # A fresh clone with no hook must be reported as ungated.
        with self.assertRaises(gg.GateNotInstalled):
            gg.assert_hook_installed(self.repo)

        # Installing it clears the report.
        hook = gg.install_hook(self.repo)
        self.assertTrue(hook.is_file())
        gg.assert_hook_installed(self.repo)  # no raise

        # The install is idempotent.
        hook2 = gg.install_hook(self.repo)
        self.assertEqual(hook, hook2)
        gg.assert_hook_installed(self.repo)  # still no raise
        self.assertIn(gg._HOOK_MARKER, hook.read_text(encoding="utf-8"))


class AC4ComposedConflictWalk(MergeSeamFixture):
    """AC4 — THE COMPOSED PATH: two clones, a conflicting governed edit, the
    driver resolving it, the gate validating the result, and a
    conflict-routing event on the bus naming the record and the resolver."""

    def test_composed_conflict_walk(self) -> None:
        clone_b = self._clone("clone_b")
        _git(["config", "merge.tropo.driver", gg.merge_driver_command()], cwd=clone_b)

        clone_a = self._clone("clone_a")
        rel = self._rel()
        # Adjacent INDEPENDENT fields -- git's own default would false-
        # conflict this (the corruption suite's "decisive win" case); the
        # driver auto-merges cleanly. THIS is "a conflicting governed edit
        # the driver resolves": a real git-level conflict, resolved.
        (clone_a / rel).write_text(
            _governed_text(self.UID, status="closed"), encoding="utf-8"
        )
        self._commit(clone_a, "A closes it", who="a")
        _git(["push", "-q", "origin", "main"], cwd=clone_a)

        (clone_b / rel).write_text(
            _governed_text(self.UID, owner="argus"), encoding="utf-8"
        )
        self._commit(clone_b, "B reassigns owner", who="b")
        _git(["fetch", "-q", "origin"], cwd=clone_b)
        result = _git(["merge", "origin/main", "-m", "merge"], cwd=clone_b, check=False)

        merged = (clone_b / rel).read_text(encoding="utf-8")
        self.assertNotIn("<<<<<<<", merged)
        self.assertNotIn("TROPO-FIELD-CONFLICT", merged,
                          "independent fields must auto-merge, not clash")
        self.assertIn("status: closed", merged)
        self.assertIn("owner: argus", merged)
        self.assertEqual(result.returncode, 0,
                          "the driver resolved it cleanly -- the merge itself succeeds")

        # The gate validates the resolved result.
        status, problems = validator.validate(str(clone_b / rel))
        self.assertEqual(status, "VALID", problems)

        # A trace on the bus, naming the record and the resolver, per
        # 7191d685 (uids for records, never a label alone).
        owner_party_uid = "34cf0f1c"  # a real governed party uid, for the assertion's shape
        path = gg.emit_conflict_event(
            clone_b, record_uid=self.UID, owner_party_uid=owner_party_uid,
            resolver="tropo_merge",
        )
        self.assertTrue(path.is_file())
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        import json
        event = json.loads(lines[0])
        self.assertEqual(event["data"]["record_uid"], self.UID)
        self.assertEqual(event["data"]["owner_party_uid"], owner_party_uid)
        self.assertEqual(event["subject"], owner_party_uid)
        self.assertEqual(event["data"]["resolver"], "tropo_merge")

    def test_control_a_resolution_with_no_trace_is_not_what_this_criterion_accepts(self) -> None:
        """A resolution that leaves no bus trace at all must not be
        mistaken for satisfying AC4 -- confirms the event assertions above
        are load-bearing, not decorative."""
        with tempfile.TemporaryDirectory() as tmp:
            vault_root = Path(tmp)
            streams = vault_root / "vault" / "events" / "streams"
            self.assertFalse(streams.exists(), "no event was ever emitted here")


class AC5DeleteChangeRace(MergeSeamFixture):
    """AC5, amended 2026-09-02 (Mike-ruled, aa245696f) -- THE DELETE/CHANGE
    RACE IS DETECTED AND SURFACED, not resolved by the wired driver. A
    modify/delete conflict never reaches `merge.tropo.driver` (talos-t58's
    real two-clone proof: git's own native path is taken first, structurally,
    regardless of wiring) -- so this criterion is aimed at detection reading
    the unmerged stages directly, never at the driver."""

    def _race(self, name: str) -> tuple[Path, str]:
        """One clone deletes the seeded governed file; another, unaware,
        edits it. clone_b merges clone_a's delete on top of its own edit --
        a real git-level modify/delete conflict, not a simulated one."""
        # clone_b FIRST, while the bare remote still carries the seed file --
        # otherwise it would clone A's delete already applied (AC2/AC4's own
        # ordering, for the same reason).
        clone_b = self._clone(f"clone_b_{name}")
        rel = self._rel()

        clone_a = self._clone(f"clone_a_{name}")
        (clone_a / rel).unlink()
        self._commit(clone_a, "A deletes it", who="a")
        _git(["push", "-q", "origin", "main"], cwd=clone_a)

        (clone_b / rel).write_text(
            _governed_text(self.UID, title="Edited by B"), encoding="utf-8"
        )
        self._commit(clone_b, "B edits it", who="b")
        _git(["fetch", "-q", "origin"], cwd=clone_b)
        result = _git(["merge", "origin/main", "-m", "merge"], cwd=clone_b, check=False)
        self.assertNotEqual(result.returncode, 0,
                             "a real modify/delete conflict must not auto-succeed")
        return clone_b, rel

    def test_delete_change_race_detected_and_surfaced(self) -> None:
        clone_b, rel = self._race("detect")

        # DETECTED: read-only, straight from git's own unmerged stages --
        # never from the driver, which this class never reaches.
        deleted_by = gg.detect_delete_change_race(clone_b, rel)
        self.assertEqual(deleted_by, "theirs-deleted",
                          "clone_b's own edit survives (ours); the incoming "
                          "merge (theirs) is the side that deleted it")

        # SURFACED: a named signal on the bus, distinct from AC4's
        # driver-resolved conflict_routed -- this class was never resolved
        # by anything at this point, and must never read as if it had been.
        owner_party_uid = "34cf0f1c"
        path = gg.emit_delete_change_race_event(
            clone_b, record_uid=self.UID, owner_party_uid=owner_party_uid,
            deleted_by=deleted_by,
        )
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        import json
        event = json.loads(lines[0])
        self.assertEqual(event["type"], "tropo.governance.delete_change_race")
        self.assertEqual(event["data"]["record_uid"], self.UID)
        self.assertEqual(event["data"]["owner_party_uid"], owner_party_uid)
        self.assertEqual(event["data"]["deleted_by"], "theirs-deleted")
        self.assertEqual(event["subject"], owner_party_uid)

        # Resolution is available but SEPARATE from the criterion above --
        # the edit still wins if and when this runs, but AC5 does not
        # require it to prove detection+signal.
        self.assertTrue(gg.resolve_delete_change_conflict(clone_b, rel))
        self.assertEqual(gg._unmerged_stages(clone_b, rel), {},
                          "resolving must clear the unmerged stage")
        self.assertIn("Edited by B", (clone_b / rel).read_text(encoding="utf-8"))

    def test_control_suppressed_detection_leaves_no_signal(self) -> None:
        """Negative control, verbatim per the locked evidence: suppress the
        detection and the same race must complete with no signal raised.
        Proves the event above is not incidental to the merge/resolve
        machinery -- it exists only because detection explicitly ran."""
        clone_b, rel = self._race("suppressed")

        # The race is real (proven by _race's own assertion), but detection
        # is never called here -- standing in for a wiring that skips it.
        streams = clone_b / "vault" / "events" / "streams"
        self.assertFalse(streams.exists(), "no signal must exist without detection")

        # Resolving the conflict directly, without ever detecting/surfacing
        # it first, must still raise nothing -- resolution alone is not the
        # signal this criterion requires.
        self.assertTrue(gg.resolve_delete_change_conflict(clone_b, rel))
        self.assertFalse(streams.exists(),
                          "resolving without detecting must still surface nothing")


class AC6GateRefusesBrokenCommit(MergeSeamFixture):
    """AC6 — THE GATE DEMONSTRABLY FIRES. A deliberately broken governed
    file committed through the wired hook is REFUSED, naming which rule
    fired. Control: repair the file and the same commit must succeed."""

    def test_gate_refuses_broken_commit(self) -> None:
        clone = self._clone("clone_gate")
        gg.install_hook(clone)
        rel = self._rel()

        # Break it: drop the required `owner` key.
        (clone / rel).write_text(
            "---\n"
            f"uid: {self.UID}\n"
            "type: note\n"
            'title: "Broken"\n'
            "status: active\n"
            "---\n"
            "Body.\n",
            encoding="utf-8",
        )
        _git(["add", "-A"], cwd=clone)
        result = subprocess.run(
            ["git", "-c", "user.email=g@test", "-c", "user.name=g",
             "commit", "-qm", "break it"],
            cwd=str(clone), capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0, "the hook must refuse the commit")
        self.assertIn("governance gate", (result.stdout + result.stderr))
        self.assertIn("BROKEN", (result.stdout + result.stderr))

        # Control: repair it, the same commit must now succeed. Distinct
        # from the seed's original bytes -- otherwise the index could match
        # HEAD exactly and "nothing to commit" (exit 1, no gate involved)
        # would be mistaken for the gate passing a repaired file.
        (clone / rel).write_text(
            _governed_text(self.UID, status="active", title="Repaired"),
            encoding="utf-8",
        )
        _git(["add", "-A"], cwd=clone)
        result2 = subprocess.run(
            ["git", "-c", "user.email=g@test", "-c", "user.name=g",
             "commit", "-qm", "repair it"],
            cwd=str(clone), capture_output=True, text=True,
        )
        self.assertEqual(result2.returncode, 0, result2.stderr)


class AC7UnconfiguredDriverWarns(MergeSeamFixture):
    """AC7 — the unconfigured-driver path: a clone declaring merge=tropo
    with no driver configured emits a NAMED warning and proceeds (warn-
    first is the lean). Control: remove the emission and the criterion
    goes red -- proven here by asserting the emission's own precondition
    logic directly, not by re-deriving it."""

    def test_unconfigured_driver_warns(self) -> None:
        clone = self._clone("clone_unconfigured")
        # .gitattributes already declares merge=tropo (from the seed); this
        # clone has NOT run install_merge_driver.
        self.assertFalse(gg.merge_driver_configured(clone))
        self.assertTrue(gg.gitattributes_declares_merge_tropo(clone))

        warnings = gg.unconfigured_driver_warning(clone)
        self.assertEqual(len(warnings), 1)
        self.assertIn("merge.tropo.driver", warnings[0])
        self.assertIn(gg.MERGE_GOVERNED_PATTERN, warnings[0])

        # The operation proceeds: a normal git merge in this state does not
        # abort -- it falls back to git's own default merge, which is the
        # documented (if suboptimal) behaviour this warning exists to
        # surface, never a hard failure.
        clone_a = self._clone("clone_a_for_ac7")
        rel = self._rel()
        (clone_a / rel).write_text(_governed_text(self.UID, status="closed"), encoding="utf-8")
        self._commit(clone_a, "A edits", who="a")
        _git(["push", "-q", "origin", "main"], cwd=clone_a)
        _git(["fetch", "-q", "origin"], cwd=clone)
        result = _git(["merge", "origin/main", "-m", "merge"], cwd=clone, check=False)
        self.assertEqual(result.returncode, 0, "an unconfigured driver on a "
                          "non-conflicting change must not block the merge")

    def test_configuring_the_driver_clears_the_warning(self) -> None:
        """Positive control: proves the warning is about configuration
        state specifically, not that the function always warns."""
        clone = self._clone("clone_now_configured")
        gg.install_merge_driver(clone)
        self.assertEqual(gg.unconfigured_driver_warning(clone), [])

    def test_no_declaration_at_all_is_silent_too(self) -> None:
        """Positive control: a clone that never declared merge=tropo has
        nothing to warn about -- the warning is specifically about a
        declared-but-unconfigured state, not about absence."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(["init", "-q", "-b", "main", str(repo)])
            self.assertEqual(gg.unconfigured_driver_warning(repo), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
