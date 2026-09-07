#!/usr/bin/env python3
"""Executable regression for Ceremony 2's documented identity contract.

The test parses the shipped playbook, executes its mint/render blocks against
temporary roots, then invokes the production mount CLI with a temporary
compose.lock. It performs no provider calls and never writes to the live Studio.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
PLAYBOOK_PATH = ROOT / "vault" / "playbooks" / "f01558f0ee26.md"
MOUNT_PATH = ROOT / "vault" / "tools" / "tropo-mount.py"


def _step_block(playbook: str, step: int) -> str:
    marker = f"## Step {step} —"
    section = playbook.split(marker, 1)[1]
    if "\n## Step " in section:
        section = section.split("\n## Step ", 1)[0]
    match = re.search(r"```(?:sh)?\n(.*?)\n```", section, re.DOTALL)
    if match is None:
        raise AssertionError(f"Step {step} has no executable command block")
    return match.group(1)


def _set_shell_assignment(block: str, name: str, value: str) -> str:
    rendered, count = re.subn(
        rf"^{re.escape(name)}=.*$",
        f"{name}={shlex.quote(value)}",
        block,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise AssertionError(f"Step 3 does not assign {name}")
    return rendered


def _run_shell(block: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", block],
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
    )


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if match is None:
        raise AssertionError(f"{path} has no YAML frontmatter")
    value = yaml.safe_load(match.group(1))
    if not isinstance(value, dict):
        raise AssertionError(f"{path} frontmatter is not a mapping")
    return value


class TestMountPlaybookCeremony2(unittest.TestCase):
    def test_documented_commands_mint_distinct_ids_and_mount_by_vault_uid(self) -> None:
        playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
        step1 = _step_block(playbook, 1)
        step2 = _step_block(playbook, 2)
        step3 = _step_block(playbook, 3)

        # These assertions identify the production commands being walked; the
        # fixture execution below is the behavioral proof.
        self.assertRegex(step3, r"tropo-mint-id\.py\"?\s+--kind file")
        self.assertRegex(step3, r"tropo-mint-id\.py\"?\s+--kind vault")

        with tempfile.TemporaryDirectory(prefix="ceremony2-playbook-") as tmp:
            fixture = Path(tmp)
            team_root = fixture / "team-vault"
            composing_root = fixture / "composing-studio"
            (composing_root / ".tropo-studio").mkdir(parents=True)
            compose_lock = composing_root / ".tropo-studio" / "compose.lock"

            env = os.environ.copy()
            env.update(
                {
                    "GIT_AUTHOR_NAME": "Ceremony Fixture",
                    "GIT_AUTHOR_EMAIL": "fixture@test.local",
                    "GIT_COMMITTER_NAME": "Ceremony Fixture",
                    "GIT_COMMITTER_EMAIL": "fixture@test.local",
                }
            )

            create = step1.replace(
                "<team-vault-root>", shlex.quote(str(team_root))
            )
            result = _run_shell(create, fixture, env)
            self.assertEqual(result.returncode, 0, result.stderr)

            genesis = (
                step2.replace(
                    "<absolute path to your team-vault-root>",
                    shlex.quote(str(team_root.resolve())),
                )
                .replace("<studio>", shlex.quote(str(ROOT)))
                .replace("<you>", "cold-engineer")
            )
            result = _run_shell(genesis, team_root, env)
            self.assertEqual(result.returncode, 0, result.stderr)

            render = step3
            values = {
                "STUDIO_ROOT": str(ROOT),
                "TEAM_VAULT_NAME": "Fixture Team Vault",
                "OWNER": "fixture-owner",
                "AUDIENCE": "bbbb2222",
                "REMOTE": "https://example.com/fixture-team.git",
                "CURATOR": "fixture-curator",
                "REGISTERED_TYPES": "task,project,note",
                "CAPABILITIES": "fixture-tool",
            }
            for name, value in values.items():
                render = _set_shell_assignment(render, name, value)
            result = _run_shell(render, team_root, env)
            self.assertEqual(result.returncode, 0, result.stderr)

            identity = _frontmatter(team_root / ".tropo" / "studio-identity.md")
            manifest = _frontmatter(team_root / ".tropo" / "vault-manifest.md")
            manifest_uid = manifest["uid"]
            vault_uid = manifest["vault_uid"]

            self.assertRegex(manifest_uid, r"^[0-9a-f]{12}$")
            self.assertTrue(manifest_uid.startswith(identity["mint_prefix"]))
            self.assertRegex(vault_uid, r"^[a-z0-9]{4,6}$")
            self.assertNotEqual(manifest_uid, vault_uid)
            self.assertEqual(
                manifest["contract"]["capabilities"],
                [f"{vault_uid}:fixture-tool"],
            )

            mount = subprocess.run(
                [
                    "python3",
                    str(MOUNT_PATH),
                    "--mount-path",
                    str(team_root),
                    "--consent",
                    "--compose-lock",
                    str(compose_lock),
                    "--mounted-by",
                    "cold-engineer",
                ],
                cwd=str(ROOT),
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(mount.returncode, 0, mount.stdout + mount.stderr)

            lock = json.loads(compose_lock.read_text(encoding="utf-8"))
            self.assertEqual(list(lock["vaults"]), [vault_uid])
            self.assertNotIn(manifest_uid, lock["vaults"])
            record = lock["vaults"][vault_uid]
            self.assertEqual(record["vault_uid"], vault_uid)
            self.assertEqual(
                record["contract"]["capabilities"],
                [f"{vault_uid}:fixture-tool"],
            )
            self.assertTrue(record["consent"]["consented"])


if __name__ == "__main__":
    unittest.main()
