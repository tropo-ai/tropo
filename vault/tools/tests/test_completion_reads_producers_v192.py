"""AC4 (5b608d28, v1.92 Stream 1): the completion verifier reads what producers
actually write, observed against the LIVE v1.91 run rather than a fixture.

THE MEASURED MOTIVATION. `verify_completion()` had never been able to return
complete for ANY release in this Studio's history (`814210f0`). Every one of its
five bound facts read a key or a path nothing writes: `publication_receipt`
looked in the run folder while the receipt is content-addressed by its own sha;
`closed_records` wanted `closed_uids` while the closure names five records under
five other keys; `scorecard` wanted an artifact nothing in the release path
writes. This is the leg whose whole purpose is to break the circularity of a
release verifying itself, and it had never observed one.

WHY THIS FILE EXISTS AS A SEPARATE ARTIFACT. It is AC4's committed test target
and it did not exist until 2026-08-25 — no git history at any commit on any
branch. AC4's implementation was built; the artifact proving it was not, and
`python3 -m pytest -q <missing file>` prints "no tests ran" and exits 0, so in a
batch of six acceptance runs it reads as benign. That is the false-success shape
appearing inside the acceptance run for the criterion about false success.
(Found by argus-a157 pre-landing, after the criterion had been reported built.)

THE SCORECARD IS AN OPEN GOVERNANCE QUESTION, AND THIS TEST DOES NOT PREJUDGE
IT. Measured against the live run, four of five facts are SEEN and `scorecard`
is genuinely ABSENT: v1.91 was never fired through `REAL_FIRE`, which A156 wired
after that release shipped. AC4's behavior text says the question is answered by
an explicit recorded decision — give the fact a producer, or remove it from
REQUIRED_FACTS with the reason on the record — and that its evidence must be
worded so EITHER answer can pass. So `ScorecardDecisionIsRecorded` below accepts
both, and fails only when neither has happened. The decision belongs to the
intent-holder, not to this file.

Verify command (locked in the spec):
    python3 -m pytest -q vault/tools/tests/test_completion_reads_producers_v192.py

Run mutation controls with `python3 -B` (see `42800b75`).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
LIB = TOOLS / "lib"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# Imported EXACTLY as the verifier imports it — `lib.release_completion`, with
# only vault/tools on the path. Importing it bare as `release_completion` (by
# also putting vault/tools/lib on sys.path) loads the same FILE as a SECOND
# module object, and then `isinstance(obs, FactObservation)` is false between
# the two copies: the verifier's observers return its FactObservation and this
# module compares against a different class of the same name. The first version
# of this file did that and produced the perfect error message —
# "observer for 'publication_receipt' returned 'FactObservation', not a
# FactObservation". One file, two identities, is the defect this whole stream
# is about; it is worth not committing it inside the test that checks for it.
from lib import release_completion as rc  # noqa: E402

#: The real release this criterion is measured against. Not a fixture: the
#: verifier's failure mode was reading shapes no producer emits, and a fixture
#: authored in the reader's shape is exactly how that survived undetected.
LIVE_RUN = STUDIO_ROOT / "vault" / "pipeline-runs" / "release-pipeline-7ee91e0b-2026-08-23"
BUS_DIR = STUDIO_ROOT / "vault" / "events" / "streams"

VERIFIER_PATH = TOOLS / "tropo-verify-release-live.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "tropo_verify_release_live_ac4", VERIFIER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bus_rows():
    """Every bus stream, as the verifier's own reader would take them."""
    rows = []
    for path in sorted(BUS_DIR.glob("*.jsonl")):
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


class TheSubjectIsReal(unittest.TestCase):
    """If the live run is not there, everything below is a fixture test wearing
    a live test's name — which is the defect this criterion exists to close."""

    def test_the_live_v191_run_folder_exists(self) -> None:
        self.assertTrue(
            LIVE_RUN.is_dir(),
            f"the v1.91 release run is not at {LIVE_RUN}; this criterion is "
            f"measured against a real release, never a fixture",
        )

    def test_the_run_journal_is_readable(self) -> None:
        self.assertTrue((LIVE_RUN / "run.jsonl").is_file())

    def test_the_bus_carries_rows(self) -> None:
        self.assertGreater(len(_bus_rows()), 0, "no bus rows found to observe")


class EveryRepairedFactIsSeenOnTheLiveRun(unittest.TestCase):
    """The four facts A156 repaired, observed against the real release."""

    REPAIRED = (
        "publication_receipt",
        "bus_published_event",
        "run_published_event",
        "closed_records",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()
        cls.observers = cls.verifier.build_observers(
            LIVE_RUN, _bus_rows(), version="1.91.0", studio_root=STUDIO_ROOT
        )
        cls.observations = {
            fact: cls.observers[fact]() for fact in rc.REQUIRED_FACTS
        }

    def test_an_observer_exists_for_every_required_fact(self) -> None:
        """A fact with no observer is counted as verified by omission."""
        for fact in rc.REQUIRED_FACTS:
            with self.subTest(fact=fact):
                self.assertIn(fact, self.observers)

    def test_the_four_repaired_facts_are_seen(self) -> None:
        for fact in self.REPAIRED:
            with self.subTest(fact=fact):
                obs = self.observations[fact]
                self.assertTrue(
                    obs.present,
                    f"{fact} is ABSENT on the live v1.91 run: {obs.detail}",
                )

    def test_each_seen_fact_carries_evidence(self) -> None:
        """Present with no evidence sha is an opinion, not an observation."""
        for fact in self.REPAIRED:
            with self.subTest(fact=fact):
                self.assertTrue(self.observations[fact].evidence_sha256)

    def test_the_co_bound_facts_agree_on_one_receipt(self) -> None:
        """Four present facts prove four things happened; they do not prove
        the four happened to the SAME release until this holds."""
        bound = {
            self.observations[f].evidence_sha256 for f in rc.CO_BOUND_FACTS
        }
        self.assertEqual(
            len(bound), 1,
            f"the co-bound facts name {len(bound)} different receipts: {bound}",
        )


class TheReceiptIsResolvedTheProducersWay(unittest.TestCase):
    """The specific repair: by the sha the PUBLISHED EVENT names, against the
    content-addressed store — never a file in the run folder, and never the
    transaction id, which carries the package sha instead."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()

    def test_there_is_exactly_one_read_path_for_the_receipt(self) -> None:
        """A second implementation is a test failure, per the criterion.

        Counted across the whole tool corpus, not just this file: the defect
        being guarded is two readers drifting apart, which cannot be seen from
        inside either one of them.
        """
        definitions = []
        for path in sorted(TOOLS.rglob("*.py")):
            for i, line in enumerate(
                path.read_text(errors="replace").splitlines(), 1
            ):
                if line.strip().startswith("def resolve_publication_receipt"):
                    definitions.append(f"{path.name}:{i}")
        self.assertEqual(
            len(definitions), 1,
            "publication_receipt must have exactly one read path; found "
            + ", ".join(definitions),
        )

    def test_the_receipt_is_verified_by_hashing_the_file_bytes(self) -> None:
        """A receipt cannot contain its own hash, so the check must hash the
        bytes rather than read a declared field."""
        source = VERIFIER_PATH.read_text(errors="replace")
        start = source.index("def resolve_publication_receipt")
        body = source[start:start + 2500]
        self.assertIn(
            "sha256", body,
            "the resolver must hash the receipt bytes, not trust a field",
        )
        self.assertNotIn(
            'get("publication_receipt_sha256")', body,
            "reading a declared self-hash is the shape this repair removed",
        )

    def test_a_receipt_resolved_by_a_wrong_sha_is_absent(self) -> None:
        """Negative control on the resolver itself."""
        ok, detail = self.verifier.resolve_publication_receipt(
            STUDIO_ROOT, "0" * 64
        )
        self.assertFalse(ok)
        self.assertTrue(detail)

    def test_an_empty_sha_is_absent_rather_than_an_error(self) -> None:
        ok, _detail = self.verifier.resolve_publication_receipt(STUDIO_ROOT, "")
        self.assertFalse(ok)


class NegativeControlsOnEachRepairedFact(unittest.TestCase):
    """Each repaired fact must still report ABSENT when its evidence is
    genuinely missing. Without these, a resolver that returns True
    unconditionally passes every assertion above."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()

    def test_an_empty_run_folder_reports_every_fact_absent(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp)
            (empty / "run.jsonl").write_text("")
            observers = self.verifier.build_observers(
                empty, [], version="1.91.0", studio_root=STUDIO_ROOT
            )
            for fact in rc.REQUIRED_FACTS:
                with self.subTest(fact=fact):
                    self.assertFalse(
                        observers[fact]().present,
                        f"{fact} reported PRESENT against an empty run folder, "
                        f"so its observer is not reading the world",
                    )

    def test_an_unobserved_bus_reads_as_absent_not_as_fine(self) -> None:
        observers = self.verifier.build_observers(
            LIVE_RUN, [], version="1.91.0", studio_root=STUDIO_ROOT
        )
        self.assertFalse(observers["bus_published_event"]().present)

    def test_another_releases_version_does_not_satisfy_this_run(self) -> None:
        observers = self.verifier.build_observers(
            LIVE_RUN, _bus_rows(), version="0.0.1-nonexistent",
            studio_root=STUDIO_ROOT,
        )
        self.assertFalse(observers["bus_published_event"]().present)


class TheVerdictIsHonestAboutWhatIsPending(unittest.TestCase):
    """`verify_completion` must name the pending edge rather than pass or crash."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()
        cls.observers = cls.verifier.build_observers(
            LIVE_RUN, _bus_rows(), version="1.91.0", studio_root=STUDIO_ROOT
        )

    def _verdict(self):
        return rc.verify_completion(
            self.observers, saga_id="7ee91e0b", pipeline_run_uid="7ee91e0b"
        )

    def test_the_verdict_reports_every_absence_not_only_the_first(self) -> None:
        verdict = self._verdict()
        absent = [o.fact for o in verdict.observations if not o.present]
        if verdict.complete:
            self.assertEqual(absent, [])
        else:
            self.assertTrue(verdict.detail)
            for fact in absent:
                self.assertIn(fact, verdict.detail)

    def test_a_pending_verdict_names_a_declared_partial_state(self) -> None:
        verdict = self._verdict()
        if not verdict.complete:
            self.assertIn(
                verdict.partial_state,
                set(rc.PARTIAL_STATE_BY_FACT.values()) | {rc.INCOHERENT_STATE},
            )

    def test_a_complete_verdict_carries_a_receipt(self) -> None:
        verdict = self._verdict()
        if verdict.complete:
            self.assertIsNotNone(verdict.receipt)
            self.assertTrue(rc.completion_receipt_sha256(verdict.receipt))

    def test_verification_refuses_without_the_run_it_verifies(self) -> None:
        with self.assertRaises(rc.ReleaseCompletionError):
            rc.verify_completion(self.observers, saga_id="", pipeline_run_uid="x")

    def test_a_missing_observer_is_refused_not_counted_as_verified(self) -> None:
        partial = {
            k: v for k, v in self.observers.items() if k != rc.REQUIRED_FACTS[0]
        }
        with self.assertRaises(rc.ReleaseCompletionError):
            rc.verify_completion(
                partial, saga_id="7ee91e0b", pipeline_run_uid="7ee91e0b"
            )


class TheOperatorPathReachesCompleteAndExitsZero(unittest.TestCase):
    """AC4's evidence says "every REQUIRED_FACT SEEN, exit 0". Neither half was
    asserted anywhere until 2026-08-25.

    The spec names a reference command. Run verbatim it produced INCOMPLETE and
    exit 1, because an omitted `--bus-events` meant "the bus is unobserved" and
    reaching exit 0 required naming one file out of 266 streams that the
    operator had to find by grepping. Meanwhile this test file supplied its own
    concatenated bus through a private helper — a shape no producer and no
    operator ever supplies. The test was green over a path nobody could walk.

    So these two assert the thing the evidence line actually claims: the verdict
    is complete, and the command an operator types exits 0.
    """

    def test_the_verdict_is_complete_on_the_live_run(self) -> None:
        verifier = _load_verifier()
        observers = verifier.build_observers(
            LIVE_RUN, _bus_rows(), version="1.91.0", studio_root=STUDIO_ROOT
        )
        verdict = rc.verify_completion(
            observers, saga_id="7ee91e0b", pipeline_run_uid="7ee91e0b"
        )
        absent = [o.fact for o in verdict.observations if not o.present]
        self.assertTrue(
            verdict.complete,
            "verify_completion must return complete for the live v1.91 run; "
            "absent facts: " + (", ".join(absent) or "none"),
        )
        self.assertIsNotNone(verdict.receipt)

    def test_the_reference_command_exits_zero_as_a_subprocess(self) -> None:
        """Driven as a command, not as a library. A test that only ever calls
        functions cannot notice that the CLI wiring is broken."""
        import subprocess

        result = subprocess.run(
            [sys.executable, str(VERIFIER_PATH),
             "--run-dir", str(LIVE_RUN), "--json"],
            capture_output=True, text=True, cwd=str(STUDIO_ROOT), timeout=180,
        )
        self.assertEqual(
            result.returncode, 0,
            f"the spec's reference command must exit 0.\n"
            f"stdout tail: {result.stdout[-400:]}\nstderr: {result.stderr[-400:]}",
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload.get("complete"))

    def test_no_bus_is_still_honestly_absent(self) -> None:
        """The property the old default was protecting must survive: choosing
        not to observe the bus reads as absent, never as fine."""
        import subprocess

        result = subprocess.run(
            [sys.executable, str(VERIFIER_PATH),
             "--run-dir", str(LIVE_RUN), "--no-bus", "--json"],
            capture_output=True, text=True, cwd=str(STUDIO_ROOT), timeout=180,
        )
        self.assertNotEqual(
            result.returncode, 0,
            "--no-bus must not reach complete; an unobserved bus is absent",
        )


class ScorecardDecisionIsRecorded(unittest.TestCase):
    """The one open governance question, and the only test here that can be
    red for a reason no code change fixes.

    AC4: "The scorecard question is answered by an explicit recorded decision —
    give it a producer, or remove it from REQUIRED_FACTS with the reason on the
    record. Evidence is worded so that EITHER answer can pass: draft v1 demanded
    'five of five SEEN', which silently foreclosed removal."

    So this accepts either resolution and fails only when neither has happened.
    It deliberately does not pick one: the decision belongs to the release's
    intent-holder.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()

    def _scorecard_observation(self):
        observers = self.verifier.build_observers(
            LIVE_RUN, _bus_rows(), version="1.91.0", studio_root=STUDIO_ROOT
        )
        return observers["scorecard"]()

    def test_the_scorecard_question_has_been_answered_one_way_or_the_other(
        self,
    ) -> None:
        if "scorecard" not in rc.REQUIRED_FACTS:
            # Answer B: removed. The reason must be on the record, in the
            # module that removed it — not in a commit message, which no
            # reader of the substrate ever sees.
            source = (LIB / "release_completion.py").read_text(errors="replace")
            self.assertIn(
                "scorecard", source.lower(),
                "scorecard was removed from REQUIRED_FACTS with no reason "
                "recorded where the tuple lives",
            )
            return

        # Answer A: kept, so it must have a producer and be observable.
        obs = self._scorecard_observation()
        self.assertTrue(
            obs.present,
            "scorecard is still a REQUIRED_FACT and is ABSENT on the live "
            "v1.91 run (%s). AC4 requires an explicit recorded decision: give "
            "it a producer, or remove it from REQUIRED_FACTS with the reason "
            "on the record. This is the intent-holder's call, and until it is "
            "made the completion verifier cannot return complete for any "
            "release — which is the defect 814210f0 documents."
            % (obs.detail or "absent"),
        )

    def test_scorecard_is_still_required_globally(self) -> None:
        """The ruling was SCOPED, and the difference is the whole point.

        A run-scoped exemption keeps v1.92 obliged to score itself. A global
        removal would retire the fact for every future release to make one past
        release green — which is why the release owner refused it by name.
        """
        self.assertIn(
            "scorecard", rc.REQUIRED_FACTS,
            "scorecard was removed globally; the ruling exempted ONE run "
            "(7ee91e0b) and required the fact from v1.92 forward",
        )

    def test_the_exemption_is_keyed_to_one_named_run(self) -> None:
        """Negative control on the exemption's SCOPE.

        THIS CONTROL WAS WRONG THE FIRST TIME AND IT MATTERS HOW. It used
        `release-pipeline-deadbeef-2026-01-01` — a uid absent from the exemption
        table entirely — so it could only ever prove that the table lookup
        works. It could not detect the actual defect, which was that the
        exemption keyed on the SAGA uid scraped from the folder name and never
        stat'd the directory: every one of these came back EXEMPT.

        The ruling was RUN-scoped. The implementation was SAGA-scoped. A
        negative control that varies the wrong dimension is a control in name
        only, and this file shipped three of them, all green.

        So the cases below now vary the dimension that actually failed: same
        saga uid, different run.
        """
        import tempfile

        # Names buy nothing now: the key is the minted activation uid read from
        # the run's own journal, so each of these carries a DIFFERENT activation
        # and must be refused regardless of what its folder is called.
        leak_shapes = (
            "release-pipeline-7ee91e0b-2026-12-31",   # a later run of the SAME saga
            "release-pipeline-7ee91e0b-2026-08-23-rerun",
            "dev-pipeline-7ee91e0b-2026-08-24",       # a different pipeline, same saga
            "totally-unrelated-7ee91e0b-thing",
            "release-pipeline-deadbeef-2026-01-01",   # the original, weak case
        )
        with tempfile.TemporaryDirectory() as tmp:
            for name in leak_shapes:
                other = Path(tmp) / name
                other.mkdir()
                # Give it the saga uid in its journal too, so the only thing
                # distinguishing it from the exempt run is its identity.
                (other / "run.jsonl").write_text(
                    '{"event":"run_created","data":{"activation_uid":"ffffffff",'
                    '"saga_id":"release:7ee91e0b"}}\n'
                )
                with self.subTest(run=name):
                    self.assertIsNone(
                        self.verifier.scorecard_exemption(other),
                        f"{name} inherited the exemption; the ruling was "
                        f"run-scoped, so a re-run or resume of the same saga "
                        f"must NOT get a permanent scorecard pass",
                    )

    def test_a_folder_named_like_the_exempt_key_is_not_exempt(self) -> None:
        """THE CONTROL THAT ACTUALLY PROTECTS THE UID KEYING.

        My first attempt to mutation-test this did not fire: I reintroduced
        name-keying as a fallback and all 30 tests still passed, because every
        leak case above uses a folder name ABSENT from the exemption table, so
        the fallback was never reached. A control that cannot reach the code it
        guards is a control in name only — the third time in one day I made that
        exact mistake, and the tell was the same each time: the mutation landed
        on the wrong test, or on none.

        This one reaches it. The folder is named EXACTLY the table key, and its
        journal carries a different activation. Any lookup that consults the
        path — as a primary or as a fallback — returns the exemption here.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            impostor = Path(tmp) / "08121161"  # the exempt key, as a folder name
            impostor.mkdir()
            (impostor / "run.jsonl").write_text(
                '{"event":"run_created","data":{"activation_uid":"ffffffff",'
                '"saga_id":"release:7ee91e0b"}}\n'
            )
            self.assertIsNone(
                self.verifier.scorecard_exemption(impostor),
                "a folder NAMED like the exempt activation must not be exempt; "
                "identity is the minted uid in the journal, never the path",
            )

    def test_the_exemption_survives_the_run_folder_being_renamed(self) -> None:
        """The other half of Mike's point. A uid does not change, so neither
        does identity: rename the real run and it is still the same run."""
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            renamed = Path(tmp) / "some-entirely-different-name"
            shutil.copytree(LIVE_RUN, renamed)
            self.assertIsNotNone(
                self.verifier.scorecard_exemption(renamed),
                "identity must follow the minted uid, not the folder name",
            )

    def test_a_named_run_that_is_not_on_disk_is_not_exempt(self) -> None:
        """A name is a claim; the directory is the evidence. This exemption
        exists because a claim was once accepted where a measurement was due."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ghost = Path(tmp) / "release-pipeline-7ee91e0b-2026-08-23"
            self.assertIsNone(self.verifier.scorecard_exemption(ghost))

    def test_an_exempt_run_never_publishes_a_scorecard_hash(self) -> None:
        """The exemption must not launder itself into a measurement field.

        `scorecard_sha256` means "the hash of the scorecard". For an exempted
        run the observation carries the hash of the GOVERNANCE DECISION ROW, and
        publishing that under this key tells the release-vs-release measurement
        a card exists. It does not.
        """
        source = VERIFIER_PATH.read_text(errors="replace")
        self.assertIn(
            'None if exempt else facts.get("scorecard", "")', source,
            "an exempted run must publish a null scorecard hash, not the hash "
            "of the decision that exempted it",
        )
        self.assertIn('"scorecard_exempt"', source)

    def test_the_exemption_fails_closed_when_its_reason_is_unreadable(
        self,
    ) -> None:
        """An exemption that cannot produce its recorded decision is an
        assertion that a fact may be skipped — the thing this verifier refuses."""
        key = "08121161"  # the run's minted activation uid, not its name
        original = self.verifier.SCORECARD_EXEMPT_RUNS[key]
        try:
            self.verifier.SCORECARD_EXEMPT_RUNS[key] = dict(
                original, journal="vault/pipeline-runs/does-not-exist/run.jsonl"
            )
            self.assertIsNone(self.verifier.scorecard_exemption(LIVE_RUN))
        finally:
            self.verifier.SCORECARD_EXEMPT_RUNS[key] = original

    def test_the_exemption_carries_the_decisions_own_evidence(self) -> None:
        """Present with a placeholder hash would be a fact asserted, not
        observed. The sha is over the decision row itself."""
        exempt = self.verifier.scorecard_exemption(LIVE_RUN)
        self.assertIsNotNone(exempt)
        self.assertEqual(len(exempt["evidence_sha256"]), 64)
        self.assertIn("scorecard_decision_recorded", exempt["detail"])

    def test_the_scorecard_reader_looks_where_the_producer_writes(self) -> None:
        """Independent of the decision above: whatever the answer, the reader
        must not be looking at a third name neither mode has ever written."""
        source = VERIFIER_PATH.read_text(errors="replace")
        self.assertNotIn(
            '"scorecard.json"', source,
            "the reader wants scorecard.json, a third name neither the "
            "rehearsal nor the real-fire mode has ever written",
        )



class TheScorecardHasExactlyOneProducer(unittest.TestCase):
    """AC4, and the reason the release owner's ruling was unsatisfiable.

    `tropo-publish-release.py:cmd_fire` wrote its own scorecard: a hand-built
    dict under the SAME FILENAME the canonical producer uses, at a DIFFERENT
    location, in a DIFFERENT shape — missing 8 of 10 schema-required fields,
    carrying 3 unknown keys, and with no `verdict`. The completion verifier
    reads `release_metrics.scorecard_path(run_dir, REAL_FIRE)`, so it called the
    scorecard ABSENT even after a successful fire.

    That is not tidiness. `cmd_fire` is what AC2 and AC5 bind to the terminal
    leaf `3dd817cb`, so "scorecard REQUIRED from v1.92 forward" could not be
    satisfied through the bound path — the same measurement gap the v1.91
    exemption exists to stop repeating.

    The divergence had a cause worth keeping visible: `cmd_fire` does not have
    the inputs. `build_scorecard` requires the orchestrator start stamp, the
    observed refusals and the baseline, and the publisher knows none of them. A
    producer without the inputs cannot honestly build the artifact — which is
    exactly how the lean hand-built dict came to exist.
    """

    PUBLISH = TOOLS / "tropo-publish-release.py"
    ORCHESTRATOR = TOOLS / "tropo-release.py"

    def test_the_publisher_does_not_write_a_scorecard(self) -> None:
        source = self.PUBLISH.read_text(errors="replace")
        self.assertNotIn(
            '"one-prompt-real-fire-scorecard.json"', source,
            "cmd_fire names the scorecard filename directly, which is how it "
            "came to write a second one at a different path",
        )
        self.assertNotIn(
            "fire_scorecard = {", source,
            "cmd_fire hand-builds a scorecard dict instead of reading the one "
            "the orchestrator produced",
        )

    def test_the_publisher_reads_the_canonical_path(self) -> None:
        source = self.PUBLISH.read_text(errors="replace")
        self.assertIn("release_metrics.scorecard_path(", source)
        self.assertIn("release_metrics.REAL_FIRE", source)

    def test_an_absent_scorecard_is_recorded_absent_not_fabricated(self) -> None:
        """Honestly absent beats a placeholder: the verifier observes the world,
        and a stand-in here would tell it a card exists."""
        source = self.PUBLISH.read_text(errors="replace")
        self.assertIn('context["scorecard_sha"] = None', source)
        self.assertIn("scorecard_absent_reason", source)

    def test_only_the_orchestrator_builds_a_scorecard(self) -> None:
        """One producer, corpus-wide. A second builder anywhere re-opens this."""
        builders = []
        for path in sorted(TOOLS.glob("*.py")):
            text = path.read_text(errors="replace")
            if "build_scorecard(" in text and "def build_scorecard" not in text:
                builders.append(path.name)
        self.assertEqual(
            builders, [self.ORCHESTRATOR.name],
            f"exactly one tool may build a scorecard; found: {builders}",
        )

if __name__ == "__main__":
    unittest.main()
