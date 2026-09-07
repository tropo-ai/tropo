"""308bb12e — the lock stamps its paired test-specs in the same transaction.

`triggered_by_dev_cycle` had FIVE production readers (9e7003b1's evidence
discovery :4989, post-test evidence gate :5269, closure refusal :5052 among
them) and ZERO producers — the capsule said the engine writes it, nothing did,
so every pre-lock test-spec failed those gates by construction and the release
procedure carried an interim hand lock-then-stamp step (Metis-adopted
2026-08-31). This suite proves the cure: the lock gesture itself writes
`triggered_by_dev_cycle: <activation-uid>` into every uid named in the
dev-spec's `triggered_test_spec_uids`, all-or-none with the lock.

The reader proof is against the REAL reader, not a mirror of its predicate:
the copied runtime's own `discover_acceptance_evidence` must find the stamped
pair — the same function whose empty result is the closure refusal at :5052.

Isolation per temp_studio: every test runs in a fresh interpreter inside a
temp Studio with its own copy of the tools, and tearDown asserts the
production Studio is byte-identical (argus-a147's never-wrote-there, not
cleaned-up-after).

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_lock_stamps_paired_test_specs_v194
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import temp_studio  # noqa: E402

SPEC_UID = "10c51001"
PAIR_UID = "10c51002"
OTHER_PAIR_UID = "10c51003"


class TheLockStampsItsPairs(unittest.TestCase):
    """Every test here runs the real gesture and asserts production did not move."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="lock-stamp-pairs-")).resolve()
        self.studio = temp_studio.TempStudio(self.tmp / "studio").build()
        self.before = temp_studio.production_fingerprint()
        self._seed()

    def tearDown(self) -> None:
        after = temp_studio.production_fingerprint()
        changes = temp_studio.diff_fingerprints(self.before, after)
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertEqual(
            changes, {},
            "the production Studio changed while an ISOLATED test ran: "
            f"{changes}")

    def _seed(self) -> None:
        self.studio.write_entry("cd1fcd25", [
            "type: pipeline", "title: dev-pipeline", "status: active",
            "version: 2.0.0", "children:", "  - 0c6518ef", "  - fa3a49c8"])
        for uid, title in (("0c6518ef", "specify"), ("fa3a49c8", "build")):
            self.studio.write_entry(uid, ["type: pipeline", "subtype: workflow-node",
                                          f"title: {title}", "status: active"])

    def _write_dev_spec(self, extra: list) -> None:
        self.studio.write_entry(SPEC_UID, [
            "type: dev-spec", "title: the spec", "status: draft",
            "acceptance_criteria:",
            "  - id: AC1",
            "    behavior: the lock stamps its paired test-specs or refuses",
            "    verify:",
            "      method: automated",
            "      command: python3 -m unittest vault.tools/tests/test_lock_stamps_paired_test_specs_v194.py",
            *extra])

    def _write_pair(self, uid: str, extra: list | None = None) -> None:
        self.studio.write_entry(uid, [
            "type: test-spec", f"title: pair {uid}", "status: done",
            *(extra or [])])

    def _run_in_studio(self, body: str) -> subprocess.CompletedProcess:
        """Execute in a FRESH interpreter rooted in the temp Studio — the same
        discipline as test_ac2_isolation_and_production_identity: in-process
        imports would reuse any cached production `lib` package."""
        script = self.studio.root / "run_gesture.py"
        script.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(self.studio.tools)!r})\n"
            "import importlib.util\n"
            "from pathlib import Path\n"
            f"spec = importlib.util.spec_from_file_location('lockdev', {str(self.studio.tools / 'tropo-lock-dev-spec.py')!r})\n"
            "lockdev = importlib.util.module_from_spec(spec); spec.loader.exec_module(lockdev)\n"
            f"STUDIO = Path({str(self.studio.root)!r})\n"
            "assert Path(lockdev.VAULT_ROOT).resolve() == STUDIO\n"
            # Stage B: composite mints read the studio-identity manifest —
            # the fixture studio needs its genesis before locking.
            "import importlib.util as _ilu\n"
            "_mspec = _ilu.spec_from_file_location('mint_seed', STUDIO / 'vault' / 'tools' / 'tropo-mint-id.py')\n"
            "_mint = _ilu.module_from_spec(_mspec); _mspec.loader.exec_module(_mint)\n"
            "_mint.mint_studio_identity(root=STUDIO, minted_by='fixture-genesis')\n"
            + body,
            encoding="utf-8")
        return subprocess.run([sys.executable, str(script)],
                              capture_output=True, text=True, timeout=120)

    def _lock_body(self, spec_uid: str = SPEC_UID) -> str:
        return (
            "code, message = lockdev.lock_dev_spec("
            f"{spec_uid!r}, 'talos-t55')\n"
            "print(f'EXIT={code}')\n"
            "print(message)\n")

    # ------------------------------------------------------------- the stamp

    def test_lock_stamps_every_named_pair_with_the_activation_uid(self) -> None:
        """The cure itself: pairs bound in the same all-or-none plan."""
        self._write_dev_spec([
            "triggered_test_spec_uids:",
            f"  - '{PAIR_UID}'",
            f"  - '{OTHER_PAIR_UID}'"])
        self._write_pair(PAIR_UID)
        self._write_pair(OTHER_PAIR_UID)
        result = self._run_in_studio(self._lock_body())
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2000:]}")
        self.assertIn("pairs=2", result.stdout)

        spec_text = (self.studio.files / f"{SPEC_UID}.md").read_text()
        self.assertIn("status: locked", spec_text)
        self.assertIn("dev_spec_activation_uid: '", spec_text)
        activation_uid = next(
            line.split(":")[1].strip().strip("'") for line in spec_text.splitlines()
            if line.startswith("dev_spec_activation_uid:"))
        self.assertRegex(activation_uid, r"^[0-9a-f]+$")

        for uid in (PAIR_UID, OTHER_PAIR_UID):
            pair_text = (self.studio.files / f"{uid}.md").read_text()
            self.assertIn(
                f"triggered_by_dev_cycle: {activation_uid}", pair_text,
                f"pair {uid} was not stamped with the activation uid")

    def test_a_slug_named_pair_stamps_through_the_resolver(self) -> None:
        """Metis's W7-gate finding: post-D7 readable-named pairs are
        <slug>-<uid>.md, and the bare construction refused them as 'does not
        resolve' — the only thing standing between the merge seam and a lock.
        The stamp must land through the slug-anchored resolver."""
        self._write_dev_spec([
            "triggered_test_spec_uids:",
            f"  - '{PAIR_UID}'"])
        # The pair exists ONLY under its readable name — no bare twin.
        self.studio.write_entry(PAIR_UID, [
            "type: test-spec", "title: the readable pair", "status: done"])
        pair_file = self.studio.files / f"readable-pair-{PAIR_UID}.md"
        (self.studio.files / f"{PAIR_UID}.md").rename(pair_file)

        result = self._run_in_studio(self._lock_body())
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2000:]}")
        self.assertIn("pairs=1", result.stdout)
        self.assertIn("triggered_by_dev_cycle:",
                      pair_file.read_text(),
                      "the slug-named pair was not stamped")

    def test_the_real_reader_discovers_the_stamped_pair(self) -> None:
        """Zero-defect on the reader side, against the reader itself.

        discover_acceptance_evidence is the function whose empty result is the
        CLOSURE REFUSED error at 9e7003b1 :5052 — the gate every pre-lock
        test-spec failed by construction. It must find the stamped pair through
        its own string-match, not through a predicate mirrored here.
        """
        self._write_dev_spec([
            "triggered_test_spec_uids:",
            f"  - '{PAIR_UID}'"])
        self._write_pair(PAIR_UID)
        result = self._run_in_studio(self._lock_body() +
            "rt_spec = importlib.util.spec_from_file_location('runtime', "
            f"{str(self.studio.tools / '9e7003b1.py')!r})\n"
            "runtime = importlib.util.module_from_spec(rt_spec)\n"
            "rt_spec.loader.exec_module(runtime)\n"
            "assert Path(runtime.VAULT_ROOT).resolve() == STUDIO\n"
            "spec_path = STUDIO / 'vault' / 'files' / '" + SPEC_UID + ".md'\n"
            "activation_uid = [l.split(':', 1)[1].strip().strip(chr(39))\n"
            "                  for l in spec_path.read_text().splitlines()\n"
            "                  if l.startswith('dev_spec_activation_uid:')][0]\n"
            "evidence = runtime.discover_acceptance_evidence("
            "'" + SPEC_UID + "', activation_uid)\n"
            "assert '" + PAIR_UID + "' in evidence, 'reader missed the pair: %s' % (evidence,)\n"
            "print('READER-FOUND')\n")
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2000:]}")
        self.assertIn("READER-FOUND", result.stdout)

    # --------------------------------------------------------- no-pair cases

    def test_a_dev_spec_with_no_pairs_locks_clean_and_stamps_nothing(self) -> None:
        self._write_dev_spec([])
        result = self._run_in_studio(self._lock_body())
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2000:]}")
        self.assertIn("pairs=0", result.stdout)
        self.assertIn("status: locked",
                      (self.studio.files / f"{SPEC_UID}.md").read_text())
        stamped = [p.name for p in self.studio.files.glob("*.md")
                   if "triggered_by_dev_cycle:" in p.read_text()]
        self.assertEqual(stamped, [], "a no-pair lock wrote a stamp somewhere")

    # ------------------------------------------------------------ refusals

    def _assert_refused_untouched(self, result: subprocess.CompletedProcess,
                                  needle: str, guarded_uids: list[str]) -> None:
        self.assertIn("EXIT=1", result.stdout,
                      f"expected refusal, got: {result.stdout}\n{result.stderr[-1500:]}")
        self.assertIn(needle, result.stdout)
        self.assertIn("status: draft",
                      (self.studio.files / f"{SPEC_UID}.md").read_text(),
                      "the spec flipped despite the refusal")
        for uid in guarded_uids:
            path = self.studio.files / f"{uid}.md"
            if path.exists():
                self.assertNotIn("triggered_by_dev_cycle:",
                                 path.read_text(),
                                 f"{uid} was stamped despite the refusal")
        activations = [p for p in self.studio.files.glob("*.md")
                       if "type: activation" in p.read_text()]
        self.assertEqual(activations, [],
                         "a refused lock still left an activation behind — "
                         "all-or-none is broken")
        self.assertEqual(list(self.studio.runs.glob("dev-pipeline-*")), [],
                         "a refused lock still left a run folder behind")

    def test_a_named_pair_that_does_not_resolve_refuses_the_whole_lock(self) -> None:
        self._write_dev_spec([
            "triggered_test_spec_uids:",
            "  - '10c59999'"])
        result = self._run_in_studio(self._lock_body())
        self._assert_refused_untouched(result, "does not resolve", [SPEC_UID])

    def test_a_named_entry_that_is_not_a_test_spec_refuses(self) -> None:
        self._write_dev_spec([
            "triggered_test_spec_uids:",
            f"  - '{PAIR_UID}'"])
        self.studio.write_entry(PAIR_UID, [
            "type: kb-article", "title: not a pair", "status: published"])
        result = self._run_in_studio(self._lock_body())
        self._assert_refused_untouched(result, "not test-spec", [SPEC_UID, PAIR_UID])

    def test_a_pair_bound_to_another_cycle_refuses_rather_than_overwrites(self) -> None:
        self._write_dev_spec([
            "triggered_test_spec_uids:",
            f"  - '{PAIR_UID}'"])
        self._write_pair(PAIR_UID, ["triggered_by_dev_cycle: aaaaaaaa"])
        before = (self.studio.files / f"{PAIR_UID}.md").read_text()
        result = self._run_in_studio(self._lock_body())
        # The pair is intentionally pre-stamped here; its untouched-ness is
        # proven by the byte comparison below, not by absence of the field.
        self._assert_refused_untouched(result, "already carries", [SPEC_UID])
        self.assertIn("aaaaaaaa", result.stdout)
        self.assertEqual((self.studio.files / f"{PAIR_UID}.md").read_text(), before,
                         "the conflicting stamp was rewritten despite the refusal")

    def test_a_pair_already_bound_to_this_cycle_is_left_untouched(self) -> None:
        """The reuse path: a retroactive cure correlated the activation and
        hand-stamped the pair — re-binding it is duplication, not repair."""
        self.studio.write_entry("ac700099", [
            "type: activation", "title: pre-existing", "status: active",
            f"dev_spec_uid: '{SPEC_UID}'", "activation_root_project: 'a0070099'"])
        self.studio.write_entry("a0070099", [
            "type: project", "title: pre-existing root", "status: active",
            "activation_uid: 'ac700099'"])
        self._write_dev_spec([
            "triggered_test_spec_uids:",
            f"  - '{PAIR_UID}'"])
        self._write_pair(PAIR_UID, ["triggered_by_dev_cycle: ac700099"])
        before = (self.studio.files / f"{PAIR_UID}.md").read_text()
        result = self._run_in_studio(self._lock_body())
        self.assertEqual(result.returncode, 0,
                         f"stdout={result.stdout}\nstderr={result.stderr[-2000:]}")
        self.assertIn("pairs=1", result.stdout)
        self.assertIn("pre-existing, reused", result.stdout)
        self.assertEqual((self.studio.files / f"{PAIR_UID}.md").read_text(), before,
                         "an already-bound pair was rewritten")


if __name__ == "__main__":
    unittest.main()
