"""Release-gate commands stay activation-bound and production-resolving.

The release graph snapshots verification commands into an immutable run. A
command that points at a fixture, omits the activation, or names an undeclared
runner cannot be repaired after ignition.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
FILES = ROOT / "vault" / "files"
PRODUCTION_TOOL = "vault/tools/tropo-release-validation-gate.py"


class ReleaseVerificationCommands(unittest.TestCase):

    def test_two_point_commands_name_the_production_tool_and_activation(self) -> None:
        for uid, mode in (("f9365ede", "capture"), ("4262d5fa", "compare")):
            with self.subTest(uid=uid):
                frontmatter = yaml.safe_load(
                    (FILES / f"{uid}.md").read_text().split("---", 2)[1]
                )
                command = frontmatter.get("verification_command")
                self.assertIsInstance(command, str)
                self.assertIn(PRODUCTION_TOOL, command)
                self.assertIn(f" {mode} ", command)
                self.assertIn("--activation-uid {activation}", command)


if __name__ == "__main__":
    unittest.main()
