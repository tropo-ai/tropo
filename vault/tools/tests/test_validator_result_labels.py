from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TOOLS = Path(__file__).resolve().parent.parent
VALIDATOR_PATH = TOOLS / "tropo-validate.py"
SPEC = importlib.util.spec_from_file_location("validator_result_labels", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def framed_index_hash(current: bytes, archive: bytes) -> str:
    combined = hashlib.sha256(b"tropo.validator.index-surfaces.v1\0")
    for name, content in (
        ("00-index.jsonl", current),
        ("00-archive-index.jsonl", archive),
    ):
        encoded_name = name.encode("utf-8")
        combined.update(len(encoded_name).to_bytes(4, "big"))
        combined.update(encoded_name)
        combined.update(len(content).to_bytes(8, "big"))
        combined.update(hashlib.sha256(content).digest())
    return combined.hexdigest()


class ValidatorResultLabelsTest(unittest.TestCase):
    def test_scope_records_default_customer_release_and_thorough(self):
        self.assertEqual(
            validator.validator_invocation_scope(),
            {
                "default": True,
                "customer": False,
                "release": False,
                "thorough": False,
            },
        )
        self.assertEqual(
            validator.validator_invocation_scope(customer=True),
            {
                "default": False,
                "customer": True,
                "release": False,
                "thorough": False,
            },
        )
        self.assertEqual(
            validator.validator_invocation_scope(release=True),
            {
                "default": False,
                "customer": False,
                "release": True,
                "thorough": False,
            },
        )
        self.assertEqual(
            validator.validator_invocation_scope(thorough=True),
            {
                "default": True,
                "customer": False,
                "release": False,
                "thorough": True,
            },
        )

    def test_provenance_hashes_exact_index_bytes_and_validator_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            vault.mkdir()
            current = b'{"uid":"current"}\n'
            archive = b'{"uid":"archive"}\n'
            (vault / "00-index.jsonl").write_bytes(current)
            (vault / "00-archive-index.jsonl").write_bytes(archive)
            scope = validator.validator_invocation_scope(release=True, thorough=True)

            no_git = validator.subprocess.CompletedProcess(
                args=["git"], returncode=128, stdout="", stderr="not a repository"
            )
            with mock.patch.object(validator.subprocess, "run", return_value=no_git):
                provenance = validator.collect_validator_provenance(root, scope)

        self.assertEqual(
            set(provenance),
            {
                "schema_version",
                "commit",
                "index_hash",
                "validator_version",
                "scope",
            },
        )
        self.assertEqual(provenance["schema_version"], 1)
        self.assertIsNone(provenance["commit"])
        self.assertEqual(
            provenance["index_hash"],
            framed_index_hash(current, archive),
        )
        self.assertEqual(
            provenance["validator_version"],
            hashlib.sha256(VALIDATOR_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(provenance["scope"], scope)

    def test_index_hash_frames_partition_boundaries(self):
        current_a, archive_a = b"a", b"bc"
        current_b, archive_b = b"ab", b"c"
        self.assertEqual(current_a + archive_a, current_b + archive_b)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hashes = []
            for folder, current, archive in (
                ("a", current_a, archive_a),
                ("b", current_b, archive_b),
            ):
                candidate = root / folder
                vault = candidate / "vault"
                vault.mkdir(parents=True)
                (vault / "00-index.jsonl").write_bytes(current)
                (vault / "00-archive-index.jsonl").write_bytes(archive)
                hashes.append(validator._validator_index_hash(candidate))

        self.assertNotEqual(hashes[0], hashes[1])
        self.assertEqual(hashes[0], framed_index_hash(current_a, archive_a))
        self.assertEqual(hashes[1], framed_index_hash(current_b, archive_b))

    def test_missing_git_or_index_is_null_honest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            vault.mkdir()
            (vault / "00-index.jsonl").write_bytes(b"current only\n")

            no_git = validator.subprocess.CompletedProcess(
                args=["git"], returncode=128, stdout="", stderr="not a repository"
            )
            with mock.patch.object(validator.subprocess, "run", return_value=no_git):
                provenance = validator.collect_validator_provenance(
                    root,
                    validator.validator_invocation_scope(customer=True),
                    validator_path=root / "missing-validator.py",
                )

        self.assertIsNone(provenance["commit"])
        self.assertIsNone(provenance["index_hash"])
        self.assertIsNone(provenance["validator_version"])

    def test_git_head_ignores_redirected_git_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actual = root / "actual"
            redirected = root / "redirected"
            clean_env = {
                key: value
                for key, value in validator.os.environ.items()
                if not key.startswith("GIT_")
            }

            for repo, message in (
                (actual, "actual head"),
                (redirected, "redirected head"),
            ):
                validator.subprocess.run(
                    ["git", "init", "-q", str(repo)],
                    check=True,
                    capture_output=True,
                    env=clean_env,
                )
                validator.subprocess.run(
                    [
                        "git",
                        "-C",
                        str(repo),
                        "-c",
                        "user.name=Validator Test",
                        "-c",
                        "user.email=validator@example.invalid",
                        "commit",
                        "--allow-empty",
                        "-q",
                        "-m",
                        message,
                    ],
                    check=True,
                    capture_output=True,
                    env=clean_env,
                )

            actual_head = validator.subprocess.run(
                ["git", "-C", str(actual), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            ).stdout.strip()
            redirected_head = validator.subprocess.run(
                ["git", "-C", str(redirected), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            ).stdout.strip()
            self.assertNotEqual(actual_head, redirected_head)

            captured_env = {}
            real_run = validator.subprocess.run

            def recording_run(*args, **kwargs):
                captured_env.update(kwargs["env"])
                return real_run(*args, **kwargs)

            redirected_env = {
                "GIT_DIR": str(redirected / ".git"),
                "GIT_WORK_TREE": str(redirected),
                "GIT_INDEX_FILE": str(redirected / ".git" / "index"),
            }
            with (
                mock.patch.dict(validator.os.environ, redirected_env, clear=False),
                mock.patch.object(
                    validator.subprocess,
                    "run",
                    side_effect=recording_run,
                ),
            ):
                provenance = validator.collect_validator_provenance(
                    actual,
                    validator.validator_invocation_scope(),
                )

        self.assertEqual(provenance["commit"], actual_head)
        self.assertEqual(captured_env.get("GIT_OPTIONAL_LOCKS"), "0")
        self.assertFalse(
            any(
                key.startswith("GIT_") and key != "GIT_OPTIONAL_LOCKS"
                for key in captured_env
            ),
            captured_env,
        )

    def test_payload_preserves_six_counts_and_adds_only_provenance(self):
        from lib import event_emitter

        provenance = {
            "schema_version": 1,
            "commit": "abc123",
            "index_hash": "index",
            "validator_version": "validator",
            "scope": validator.validator_invocation_scope(),
        }
        with mock.patch.object(event_emitter, "auto_emit") as auto_emit:
            status = validator.emit_validator_run_completed(
                passed=1,
                failed=2,
                warnings=3,
                normalizable=4,
                meta_status_coverage_gaps=5,
                meta_status_unresolved=6,
                provenance=provenance,
                exit_code=1,
            )

        self.assertEqual(status, 1)
        args, kwargs = auto_emit.call_args
        self.assertEqual(
            args,
            (
                "tropo.validator.run.completed",
                "/tools/tropo-validate",
                "d2b9c8e6",
            ),
        )
        self.assertEqual(kwargs["lifecycle"], "ephemeral")
        payload = kwargs["data"]
        self.assertEqual(
            set(payload),
            {
                "passed",
                "failed",
                "warnings",
                "normalizable",
                "meta_status_coverage_gaps",
                "meta_status_unresolved",
                "provenance",
            },
        )
        self.assertEqual(
            {key: payload[key] for key in payload if key != "provenance"},
            {
                "passed": 1,
                "failed": 2,
                "warnings": 3,
                "normalizable": 4,
                "meta_status_coverage_gaps": 5,
                "meta_status_unresolved": 6,
            },
        )
        self.assertEqual(payload["provenance"], provenance)
        self.assertNotIn("writer_instance_uid", payload)
        self.assertNotIn("writer_instance_uid", payload["provenance"])

    def test_provenance_failure_is_nonblocking_null_and_exit_neutral(self):
        scope = validator.validator_invocation_scope(thorough=True)
        stderr = io.StringIO()
        with (
            mock.patch.object(
                validator,
                "collect_validator_provenance",
                side_effect=RuntimeError("collection broke"),
            ),
            contextlib.redirect_stderr(stderr),
        ):
            provenance = validator.collect_validator_provenance_nonblocking(
                Path("/unused"),
                scope,
            )

        self.assertIn("provenance collection failed", stderr.getvalue())
        self.assertEqual(
            provenance,
            {
                "schema_version": 1,
                "commit": None,
                "index_hash": None,
                "validator_version": None,
                "scope": scope,
            },
        )

        from lib import event_emitter

        with mock.patch.object(event_emitter, "auto_emit"):
            status = validator.emit_validator_run_completed(
                passed=0,
                failed=9,
                warnings=0,
                normalizable=0,
                meta_status_coverage_gaps=0,
                meta_status_unresolved=0,
                provenance=provenance,
                exit_code=1,
            )
        self.assertEqual(status, 1)

    def test_event_failure_warns_and_preserves_each_exit_status(self):
        from lib import event_emitter

        provenance = validator._empty_validator_provenance(
            validator.validator_invocation_scope()
        )
        for expected_status in (0, 1):
            with self.subTest(exit_code=expected_status):
                stderr = io.StringIO()
                with (
                    mock.patch.object(
                        event_emitter,
                        "auto_emit",
                        side_effect=RuntimeError("emit broke"),
                    ),
                    contextlib.redirect_stderr(stderr),
                ):
                    status = validator.emit_validator_run_completed(
                        passed=1,
                        failed=expected_status,
                        warnings=0,
                        normalizable=0,
                        meta_status_coverage_gaps=0,
                        meta_status_unresolved=0,
                        provenance=provenance,
                        exit_code=expected_status,
                    )
                self.assertEqual(status, expected_status)
                self.assertIn("event emission failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
