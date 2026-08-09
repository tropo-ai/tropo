#!/usr/bin/env python3
"""Regression coverage for the studio test-suite runner."""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = ROOT / "vault" / "tools" / "tropo-run-suites.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("tropo_run_suites", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


class TestSuiteRunnerTimeoutAccounting(unittest.TestCase):
    def test_timeout_preserves_completed_verbose_test_count(self):
        partial_stderr = (
            "test_first (__main__.Example.test_first) ... ok\n"
            "test_second (__main__.Example.test_second) ... skipped 'environment'\n"
            "test_third (__main__.Example.test_third) ... "
        )
        timeout = subprocess.TimeoutExpired(
            cmd=["python3", "example.py"],
            timeout=180,
        )
        process = Mock(pid=4321)
        process.wait.side_effect = timeout

        with (
            patch.object(
                runner.subprocess,
                "Popen",
                return_value=process,
            ) as popen,
            patch.object(
                runner,
                "_terminate_process_group",
            ) as terminate,
            patch.object(
                runner,
                "_read_capture",
                side_effect=["", partial_stderr],
            ),
            patch.object(runner.time, "monotonic", side_effect=[10.0, 190.2]),
        ):
            result = runner.run_one(Path("example.py"), 180)

        terminate.assert_called_once_with(process)
        self.assertEqual(
            popen.call_args.kwargs["start_new_session"],
            runner.os.name == "posix",
        )
        self.assertIsNot(
            popen.call_args.kwargs["stdout"],
            runner.subprocess.PIPE,
        )
        self.assertIsNot(
            popen.call_args.kwargs["stderr"],
            runner.subprocess.PIPE,
        )
        process.wait.assert_called_once_with(timeout=180)
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertEqual(result["tests"], 2)
        self.assertEqual(result["seconds"], 180.2)
        self.assertEqual(result["detail"], "exceeded 180s")

    def test_final_unittest_summary_remains_authoritative(self):
        output = (
            "test_first (__main__.Example.test_first) ... ok\n"
            "test_second (__main__.Example.test_second) ... ok\n"
            "Ran 3 tests in 0.001s\n"
        )
        self.assertEqual(runner._tests_executed(output), 3)

    @unittest.skipUnless(runner.os.name == "posix", "process groups are POSIX-only")
    def test_timeout_cleanup_terminates_the_suite_process_group(self):
        process = Mock(pid=4321)
        process.wait.return_value = -runner.signal.SIGTERM

        with patch.object(runner.os, "killpg") as killpg:
            runner._terminate_process_group(process)

        killpg.assert_called_once_with(4321, runner.signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=5)

    @unittest.skipUnless(runner.os.name == "posix", "process groups are POSIX-only")
    def test_completed_suite_is_not_blocked_by_pipe_inheriting_descendant(self):
        with tempfile.TemporaryDirectory() as temporary:
            suite = Path(temporary) / "test_pipe_inheritor.py"
            suite.write_text(
                "\n".join(
                    (
                        "import subprocess",
                        "import sys",
                        "subprocess.Popen([",
                        "    sys.executable, '-c',",
                        "    'import signal; signal.pause()',",
                        "])",
                        "print('test_done (__main__.Example.test_done) ... ok',",
                        "      file=sys.stderr, flush=True)",
                        "print('Ran 1 test in 0.001s', file=sys.stderr, flush=True)",
                    )
                ),
                encoding="utf-8",
            )

            result = runner.run_one(suite, timeout=5)

        self.assertEqual(result["status"], "green")
        self.assertEqual(result["tests"], 1)
        self.assertLess(result["seconds"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
