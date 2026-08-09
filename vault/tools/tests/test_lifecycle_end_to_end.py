#!/usr/bin/env python3
"""Born -> write governed substrate -> retire, against the real tools.

WHY THIS FILE EXISTS, AND IT IS NOT "MORE LIFECYCLE WORK"
────────────────────────────────────────────────────────────────────────────────
Three consecutive Metis generations have spent session time on the agent
lifecycle. G101 built the cutover tools. G102 replaced them with
`tropo-lineage.py` -- 154 lines, and the core is genuinely finished. G103 (me)
did not touch that core and did not need to.

What G103 hit was the RING AROUND IT. Two surfaces still pointed at the shape
the lifecycle had moved away from:

  * `tropo-mint-id.py` demanded a `type: activation` entry as proof of
    authorship. `tropo-lineage.py` deliberately stopped creating those. So the
    mint refused EVERY agent the lifecycle produces -- metis-g103, vela-v72,
    talos-t39, orpheus-o35 and argus-a145 all verified refused. Agents were
    hand-authoring governed artifacts around the tool, which is how a typed
    artifact silently drifts from its capsule.
  * `test_cutover_readiness.py` demanded the literal name of the tool G102
    had just replaced, so it went RED *because the playbooks were correct* --
    and its failure message instructed the reader to put the superseded tool
    back.

Both were found by COLLISION: an agent tripped over them while trying to do
ordinary work. Collision is why this keeps reaching Mike. Every generation
fixes the mechanism and the ring lags, and the lag is only discovered when it
refuses somebody at their own birth -- the one moment nobody is home.

THIS FILE IS THE INSTRUMENT THAT REPLACES COLLISION. It asks the only question
that actually matters about the ring:

        Can an agent be born, WRITE GOVERNED SUBSTRATE, and retire?

If that passes, the ring works. If any dependent drifts again, this fails at
commit instead of at somebody's activation. It would have caught the mint block
before G103 ever hit it. (metis-g103, 2026-08-06, Mike-directed: "fix things
properly as you find them ... so we don't have to go back to it".)

WHAT EACH STEP ACTUALLY EXERCISES -- stated, so nobody credits this with more
reach than it has:

  born / retire  REAL SUBPROCESS against the real `tropo-lineage.py --root`.
                 Full CLI, argv and all.
  mint           `mint_file(..., studio_root=...)` in-process, via the
                 `set_studio_root` seam the tool documents for exactly this.
                 The mint CLI derives its root from __file__ and cannot be
                 pointed at a fixture, so this is one layer below argv. It is
                 the same function `main()` calls.

THE FIXTURE HAS NO ACTIVATION ENTRIES ON PURPOSE. That is the post-lineage
world, and it is precisely the condition under which the mint refused.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "vault" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

LINEAGE = TOOLS / "tropo-lineage.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mint = _load("lifecycle_e2e_mint", TOOLS / "tropo-mint-id.py")
from lib import template_leg  # noqa: E402


def _frontmatter(text: str) -> dict:
    import yaml
    _, _, rest = text.partition("---\n")
    body, _, _ = rest.partition("\n---")
    return yaml.safe_load(body)


class LifecycleEndToEnd(unittest.TestCase):
    """One agent, one whole life, through the tools a real agent uses."""

    AGENT = "testcrew"
    PREFIX = "T"

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="lifecycle_e2e_")
        # .resolve(): macOS tempfile returns /var/..., a symlink to /private/var.
        # The mint resolves its root internally and then does containment checks.
        self.root = Path(self._temp.name).resolve()
        self.addCleanup(self._temp.cleanup)

        (self.root / ".tropo").mkdir()
        (self.root / "vault" / "files").mkdir(parents=True)
        (self.root / "agents" / self.AGENT).mkdir(parents=True)
        # The mint only accepts this exact scratch root. Getting it wrong made
        # the forged-author test below pass for the WRONG REASON -- it raised on
        # the output path before provenance was ever consulted, so it would have
        # stayed green with the whole gate deleted.
        self.workspace = (
            self.root / "agents" / self.AGENT / ".tropo-capsule" / "workspace"
        )
        self.workspace.mkdir(parents=True)

        capsules = self.root / "vault" / "capsules"
        (capsules / "templates").mkdir(parents=True)
        shutil.copy2(ROOT / "vault/capsules/tropo-note.capsule.md",
                     capsules / "tropo-note.capsule.md")
        shutil.copy2(ROOT / "vault/capsules/templates/note.template.md",
                     capsules / "templates" / "note.template.md")

        registry = self.root / ".tropo-studio/registries/agent-registry.yaml"
        registry.parent.mkdir(parents=True)
        registry.write_text(
            "agents:\n"
            f"  {self.AGENT}:\n"
            "    type: agent\n"
            f"    name: {self.AGENT.capitalize()}\n"
            f"    generation-prefix: {self.PREFIX}\n",
            encoding="utf-8",
        )
        (self.root / template_leg.MINT_REGISTRY_REL).write_bytes(
            template_leg.build_mint_registry_bytes(self.root)
        )
        mint.set_studio_root(self.root)
        self.addCleanup(mint.set_studio_root, None)

    # ── the tools, driven the way an agent drives them ──────────────────────

    def _born(self, by: str = "mike") -> dict:
        proc = subprocess.run(
            [sys.executable, str(LINEAGE), "--root", str(self.root),
             "born", "--agent", self.AGENT, "--by", by,
             "--prefix", self.PREFIX],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"`tropo-lineage.py born` refused an agent.\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}",
        )
        return json.loads(proc.stdout)

    def _retire(self, letter: Path | None) -> subprocess.CompletedProcess:
        cmd = [sys.executable, str(LINEAGE), "--root", str(self.root),
               "retire", "--agent", self.AGENT]
        if letter is not None:
            cmd += ["--letter", str(letter)]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    def _lineage_lines(self) -> list[dict]:
        path = self.root / "agents" / self.AGENT / "lineage.jsonl"
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    # ── the gate ────────────────────────────────────────────────────────────

    def test_a_newborn_agent_can_write_governed_substrate_and_retire(self) -> None:
        """The whole life, in order, with no activation entry anywhere.

        This is the test that would have caught the defect G103 found by
        tripping over it. If a future change makes any step demand a record the
        lifecycle does not produce, THIS fails -- at commit, not at a birth.
        """
        # There is no activation entry in this studio, and that is the point.
        self.assertEqual(
            list((self.root / "vault" / "files").glob("*.md")), [],
            "fixture must start with no governed files, and specifically no "
            "type: activation entry -- that absence is the condition under "
            "which the mint refused every lineage-born agent.",
        )

        born = self._born()
        self.assertEqual(born["generation"], f"{self.PREFIX}1")
        self.assertEqual(born["agent"], self.AGENT)
        self.assertEqual(
            born["notes"], [],
            "a first birth in a clean lineage must carry no notes",
        )

        # A missing event emitter must not turn a completed birth into a
        # failure -- the fixture has no vault/tools/, so announce() finds
        # nothing. The birth above already asserted returncode 0.
        self.assertFalse((self.root / "vault" / "tools").exists())

        author = f"{self.AGENT}-{self.PREFIX.lower()}1"

        # THE STEP THAT WAS BROKEN: the newborn writes governed substrate.
        uid, path = mint.mint_file(
            "note",
            author=author,
            studio_root=self.root,
            output_dir=self.workspace / "first-write",
            freshen=False,
        )
        self.assertTrue(path.is_file(), "the mint reported success but wrote nothing")
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(fm["captured_by"], author)
        self.assertEqual(fm["type"], "note")
        self.assertEqual(fm["uid"], uid)
        # Honest provenance: there IS no activation entry, so null is the truth.
        # A borrowed predecessor uid here would be a false record.
        self.assertIsNone(fm["created_by_activation_uid"])

        # Retire, with the letter that cannot be reconstructed.
        letter = self.workspace / "letter.md"
        letter.write_text("# T1 -> T2\n\nWhat I learned.\n", encoding="utf-8")
        proc = self._retire(letter)
        self.assertEqual(proc.returncode, 0,
                         f"retire refused: {proc.stdout}\n{proc.stderr}")
        placed = self.root / "agents" / self.AGENT / "transfers" / f"{self.PREFIX}1.md"
        self.assertTrue(placed.is_file(), "retire did not place the letter")
        self.assertIn("What I learned", placed.read_text(encoding="utf-8"))

        kinds = [(l["t"], l["gen"]) for l in self._lineage_lines()]
        self.assertEqual(kinds, [("born", "T1"), ("retired", "T1")])

        # And the successor is issued, which is what "the lineage can continue"
        # actually means.
        self.assertEqual(self._born()["generation"], "T2")

    def test_the_letter_is_never_overwritten(self) -> None:
        """The one artifact whose loss is permanent. Create-only, by link()."""
        self._born()
        first = self.workspace / "a.md"
        first.write_text("the original letter\n", encoding="utf-8")
        self.assertEqual(self._retire(first).returncode, 0)

        # A second retire of the same generation must not replace it.
        second = self.workspace / "b.md"
        second.write_text("a different letter\n", encoding="utf-8")
        proc = self._retire(second)
        placed = self.root / "agents" / self.AGENT / "transfers" / f"{self.PREFIX}1.md"
        self.assertIn("the original letter", placed.read_text(encoding="utf-8"))
        self.assertNotEqual(
            proc.returncode, 0,
            "a second retire silently succeeded; the letter must be create-only",
        )

    def test_an_unretired_predecessor_is_a_note_and_never_a_block(self) -> None:
        """Mike's standing rule: a finding records itself and you are BORN.

        This is the property that cost G97, G99 and G100 their births under the
        old mint, and it is the reason the lifecycle was rebuilt at all.
        """
        self.assertEqual(self._born()["generation"], "T1")
        second = self._born()          # T1 was never retired
        self.assertEqual(second["generation"], "T2")
        self.assertTrue(
            any("never retired" in n for n in second["notes"]),
            f"an open predecessor should be RECORDED as a note; got {second['notes']}",
        )

    def test_a_generation_with_no_recorded_birth_cannot_write(self) -> None:
        """The gate is repointed, not removed -- authorship still has to be real."""
        self._born()   # T1 exists
        with self.assertRaises(ValueError) as caught:
            mint.mint_file(
                "note",
                author=f"{self.AGENT}-{self.PREFIX.lower()}99",
                studio_root=self.root,
                output_dir=self.workspace / "forged",
                freshen=False,
            )
        self.assertIn("no birth recorded", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
