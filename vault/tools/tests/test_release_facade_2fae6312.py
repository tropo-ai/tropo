#!/usr/bin/env python3
"""The one command: what it does, and what it refuses to pretend.

Dev-spec 2fae6312 step 8, operator facade. Two things are worth testing about
a facade. That it composes the real modules rather than growing a second
opinion about the release, and that its refusals are honest — a tool which
silently no-ops the outward half is worse than one that will not run.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = STUDIO_ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import release_metrics as metrics  # noqa: E402
from lib import release_saga as saga  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "tropo_release_facade_under_test", TOOLS / "tropo-release.py"
)
facade = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = facade
_spec.loader.exec_module(facade)

SAGA = "release:934436ca"
RUN = "934436ca"


class FacadeTestCase(unittest.TestCase):
    def run_dir(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="release-facade-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "run.jsonl").write_text(
            json.dumps(
                {
                    "event": "tropo.release.scope_locked",
                    "data": {"saga_id": SAGA, "pipeline_run_uid": RUN},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return tmp

    def rehearse(self, run_dir: Path) -> int:
        return facade.main(
            ["--vault", str(STUDIO_ROOT), "rehearse", "--run-dir", str(run_dir)]
        )


class RehearsalTests(FacadeTestCase):
    def test_a_rehearsal_walks_every_checkpoint_and_passes(self):
        run_dir = self.run_dir()
        self.assertEqual(self.rehearse(run_dir), facade.EXIT_OK)

        card = json.loads(
            (run_dir / "one-prompt-rehearsal-scorecard.json").read_text(encoding="utf-8")
        )
        self.assertEqual(card["mode"], metrics.REHEARSAL)
        self.assertEqual(card["verdict"], "pass")
        self.assertTrue(card["gestures"]["met"])

    def test_a_replay_performs_nothing(self):
        """Idempotency through the production saga, not around it.

        The fake world persists in its own file because the real one does. An
        in-memory fake would make every replay look like a first run, and a
        broken idempotency contract would rehearse clean.
        """
        run_dir = self.run_dir()
        self.rehearse(run_dir)
        world_before = (run_dir / "rehearsal-world.json").read_text(encoding="utf-8")

        self.assertEqual(self.rehearse(run_dir), facade.EXIT_OK)

        self.assertEqual(
            (run_dir / "rehearsal-world.json").read_text(encoding="utf-8"),
            world_before,
            "the replay changed the world it was supposed to find already made",
        )
        journal_rows = [
            json.loads(line)
            for line in (run_dir / "release-saga.jsonl").read_text().splitlines()
            if line.strip()
        ]
        outcomes = [
            r.get("outcome")
            for r in journal_rows
            if r.get("event") == saga.OBSERVED_EVENT
        ]
        self.assertEqual(
            outcomes.count(saga.OUTCOME_ALREADY_PRESENT),
            len(saga.CHECKPOINTS),
            "the replay re-acted instead of observing the facts already present",
        )

    def test_a_rehearsal_never_writes_the_real_fire_scorecard(self):
        run_dir = self.run_dir()
        self.rehearse(run_dir)
        self.assertFalse(
            (run_dir / "one-prompt-real-fire-scorecard.json").exists(),
            "a rehearsal wrote where a real fire is read from",
        )

    def test_the_rehearsal_scorecard_validates(self):
        run_dir = self.run_dir()
        self.rehearse(run_dir)
        card = json.loads(
            (run_dir / "one-prompt-rehearsal-scorecard.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            metrics.validate_scorecard(
                card,
                STUDIO_ROOT / "vault" / "schema" /
                "one-prompt-release-scorecard.schema.json",
            ),
            [],
        )


class FireRefusalTests(FacadeTestCase):
    CREDENTIALS = {
        "TROPO_GITHUB_TOKEN": "x",
        "TROPO_SUPABASE_KEY": "y",
        "TROPO_APP_DEPLOY_REMOTE": "z",
    }

    def fire(self, run_dir: Path, *extra) -> int:
        return facade.main(
            ["--vault", str(STUDIO_ROOT), "fire", "--run-dir", str(run_dir), *extra]
        )

    def test_fire_refuses_without_the_credentialed_edges(self):
        run_dir = self.run_dir()
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(self.fire(run_dir), facade.EXIT_REFUSED)

    def test_the_refusal_names_which_edge_is_missing(self):
        """'Not configured' sends an operator hunting."""
        environ = dict(self.CREDENTIALS)
        del environ["TROPO_SUPABASE_KEY"]
        missing = facade._missing_fire_requirements(environ)
        self.assertEqual(missing, ["TROPO_SUPABASE_KEY"])

    def test_each_guard_produces_its_own_refusal_code(self):
        """Three refusals share one exit status, so the CODE is the assertion.

        Without distinct codes these guards are unobservable: a mutation that
        deleted the credential check left every test green, because the
        terminal 'adapters not wired' refusal returned the same status either
        way. That mutation is why this test exists.
        """
        code, message = facade.fire_refusal(environ={}, authorized=True)
        self.assertEqual(code, facade.REFUSAL_MISSING_CREDENTIALS)
        self.assertIn("TROPO_GITHUB_TOKEN", message)

        code, _ = facade.fire_refusal(environ=dict(self.CREDENTIALS), authorized=False)
        self.assertEqual(code, facade.REFUSAL_AUTHORIZATION_REQUIRED)

        # AC5 (2cb346d6, 2026-08-21): fully credentialed AND authorized now
        # PROCEEDS. The terminal 'adapters not wired' refusal was deleted with
        # the stub it described. Asserting None here keeps this test's original
        # purpose — the guards stay observable — while pinning current truth:
        # both gates cleared means the facade routes to the wired fire.
        self.assertIsNone(
            facade.fire_refusal(environ=dict(self.CREDENTIALS), authorized=True),
            "credentialed + authorized must proceed, not refuse",
        )

    def test_credentials_are_checked_before_authorization(self):
        """On a machine with no edges, asking to authorize is a false prompt."""
        code, _ = facade.fire_refusal(environ={}, authorized=False)
        self.assertEqual(code, facade.REFUSAL_MISSING_CREDENTIALS)


class StatusTests(FacadeTestCase):
    def test_status_on_an_untouched_run_is_incomplete(self):
        run_dir = self.run_dir()
        code = facade.main(
            ["--vault", str(STUDIO_ROOT), "status", "--run-dir", str(run_dir)]
        )
        self.assertEqual(code, facade.EXIT_REFUSED)

    def test_a_missing_run_directory_is_misuse(self):
        self.assertEqual(
            facade.main(
                ["--vault", str(STUDIO_ROOT), "status", "--run-dir", "/tmp/no-such-run"]
            ),
            facade.EXIT_MISUSE,
        )


class CompositionTests(unittest.TestCase):
    """The facade composes; it does not decide."""

    def test_it_holds_no_checkpoint_list_of_its_own(self):
        source = (TOOLS / "tropo-release.py").read_text(encoding="utf-8")
        self.assertIn("saga.CHECKPOINTS", source)
        self.assertNotIn("site_prepare\"", source.replace("saga.", ""))

    def test_it_reuses_the_live_verifier_observers(self):
        source = (TOOLS / "tropo-release.py").read_text(encoding="utf-8")
        self.assertIn("tropo-verify-release-live.py", source)
        self.assertIn("build_observers", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
