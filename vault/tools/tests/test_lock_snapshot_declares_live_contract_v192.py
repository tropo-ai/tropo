"""AC2 (v1.92 Stream 2, 1a478c48): the dev lock's declaration snapshot
declares the LIVE, startable contract -- no element the runtime refuses.

G111's 2026-08-23 measurement ("01-studio-inbox item 4"): a lock-opened dev
run's snapshot declared steps the runtime refused -- bootstrap on "already has
events", step-start on "not in activation contract". Talos T50's re-run
(2026-08-24, against the post-repair tree) found the premise had moved: the
runtime accepted every declared step on a real production-door lock, cleanly,
first try. Metis G112, spec owner, ruled on the finding (ac_premise_correction
recorded on run 8098be20): G111's measurement was PRE-repair (argus-a156's
2.0.1 dev-graph fix, 2026-08-24); the declared four v2 steps are now TRUE and
startable, so AC2 narrows from "reshape the declaration" to "prove it, and fix
the one reader that still can't read it".

WHAT THIS FILE PROVES, real tools, real production door, no hand-built
snapshot:

  1. `DevSpecLockDeclaresTheRealPipelineCleanly` -- locks a fixture dev-spec
     against the REAL dev-pipeline tree (cd1fcd25 + its 3 stages + 4 leaf
     steps, copied byte-for-byte from vault/files/), then drives the real
     runtime through bootstrap -> step-start on the first declared step
     (exactly G111's repro shape). Zero refusals is the assertion; a refusal
     raises and fails the test loudly. Scoped to entry rather than a full
     four-step walk for a reason named on the test itself: `0c6518ef`'s own
     verification_command needs the real `tests/` tree, which an isolated
     TempStudio deliberately doesn't carry. The full walk was run for real,
     unfixtured, against the actual worktree during this build -- see that
     test's docstring for the transcript pointer.

     Isolation follows the two-tool split this codebase already uses for a
     lock+runtime pair (test_release_plan_lock_end_to_end.py): the LOCK tool
     is loaded ONCE at module scope and driven by monkey-patching
     `lib.lock_transaction`'s globals per test (its own containment check
     reads a module-level VAULT_ROOT, not a parameter -- a fresh
     `TempStudio.load()` copy per test method silently reuses the FIRST
     copy's cached `sys.modules["lib.lock_transaction"]` instead of
     re-executing, and every lock after the first refuses "resolves outside
     the studio" against a deleted tmpdir. Found live authoring this file).
     The RUNTIME tool (9e7003b1.py) has no such global and is loaded fresh
     per test via `temp_studio.TempStudio.load()`, matching the existing
     precedent exactly.

  2. `BothNamedReadersAcceptTheConformedSnapshot` -- the two readers AC2
     names, against Metis G112's OWN real snapshot (declaration_digest
     875b845a61eb..., run dev-pipeline-8098be20-2026-08-24 -- the actual
     v1.92 Stream 2 spec's own lock, per her instruction to use it as the
     fixture since it is "now a TRUE specimen, not a broken one").
     `9e7003b1.py`'s side is proven by class (1) already driving bootstrap
     over this same shape; `lib/release_events.py`'s `AuthorizationContext.
     observe` / `_snapshot_step_uids` is proven directly against the real
     file.

     THIS SECOND READER IS EXPECTED TO FAIL until Argus's lane lands: an
     empirical check (`_snapshot_step_uids` recognises keys `uid` /
     `step_uid` / `node_uid` and list-keys `children` / `steps` / `nodes` --
     the real snapshot's field is `declared_steps`, which matches none of
     them) proves it currently reads an empty set off every real snapshot,
     dev or release. Reported to Argus A156 2026-08-24 (release_events.py is
     Stream 1 substrate; not edited here per the spec's own coordination
     boundary). These two tests are the mutation guard AC2 asks for on that
     axis: "breaking either reader on the new shape turns this RED" -- right
     now it already is red, honestly, for the reason named above, and will
     go green the instant his fix lands with no change needed here.

Fully qualified selector, pytest is absent here:
    python3 -m unittest vault.tools.tests.test_lock_snapshot_declares_live_contract_v192
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TOOLS = TESTS_DIR.parent
REAL_ROOT = TOOLS.parents[1]
REAL_FILES = REAL_ROOT / "vault" / "files"
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TOOLS))

import temp_studio  # noqa: E402
from lib import lock_transaction as lt  # noqa: E402
from lib import release_events as _release_events  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "ac2_lock_dev_spec", TOOLS / "tropo-lock-dev-spec.py")
dl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dl)

#: The dev-pipeline root; every entry it names as a child, transitively, is
#: pulled in at setUp time -- read from disk each run rather than hand-copied,
#: so a future definition change is picked up automatically instead of
#: silently testing a stale shadow of the real tree.
DEV_PIPELINE_ROOT = "cd1fcd25"

REAL_SNAPSHOT_PATH = (
    REAL_ROOT / "vault" / "pipeline-runs" / "dev-pipeline-8098be20-2026-08-24"
    / "declaration-snapshot.json"
)

# 3d430852 suite migration 6 of 7 (T55): mint-output assertions follow the
# AUTHORITY mint constant — Stage A mints 8-hex (the lock message regex passes
# today unchanged); when Stage B flips MINT_HEX_LEN to 12 this follows the
# flip instead of breaking. Never a second mint-shape definition.
from lib.governed_path import MINT_HEX_LEN as _MINT_LEN  # noqa: E402

LOCK_MESSAGE_RE = re.compile(r"\bactivation=([0-9a-f]{%d})\b" % _MINT_LEN)


def _dev_pipeline_tree_uids() -> list:
    """Every UID in the real dev-pipeline tree, root first, breadth-first."""
    seen: list = []
    stack = [DEV_PIPELINE_ROOT]
    visited = set()
    while stack:
        uid = stack.pop(0)
        if uid in visited:
            continue
        visited.add(uid)
        path = REAL_FILES / f"{uid}.md"
        if not path.is_file():
            continue
        seen.append(uid)
        text = path.read_text(encoding="utf-8")
        fm_text = text.split("\n---", 1)[0]
        m = re.search(r"children:\s*\n((?:\s*-\s*\S+\n?)+)", fm_text)
        if m:
            for line in m.group(1).splitlines():
                mm = re.match(r"\s*-\s*([0-9a-f]{8})", line)
                if mm:
                    stack.append(mm.group(1))
    return seen


class DevSpecLockDeclaresTheRealPipelineCleanly(unittest.TestCase):
    """Lock -> bootstrap -> step-start every leaf, on the REAL definition."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ac2-lock-live-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.studio = temp_studio.TempStudio(self.tmp).build()

        self._orig_lt = (lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT)
        lt.LOCK_JOURNAL_DIR = self.tmp / "journal"
        lt.WORKSPACE_LOCK_PATH = self.tmp / "journal" / "ignition.lock"
        lt.VAULT_ROOT = self.tmp
        self.addCleanup(self._restore_lt)

        # The real dev-pipeline tree, byte-for-byte -- not a synthetic proxy.
        # This is the whole point: prove the declaration the ACTUAL shipped
        # definition produces is startable, not a fixture that happens to be.
        for uid in _dev_pipeline_tree_uids():
            shutil.copy2(REAL_FILES / f"{uid}.md", self.studio.files / f"{uid}.md")

        self.studio.write_entry("ab000001", [
            "type: dev-spec",
            "title: AC2 live-contract fixture",
            "status: draft",
            "acceptance_criteria:",
            "  - id: AC1",
            "    behavior: the declaration the real definition produces is startable",
            "    verify:",
            "      method: automated",
            "      command: python3 -m unittest "
            "vault.tools.tests.test_lock_snapshot_declares_live_contract_v192",
        ])

        # Stage B (3d430852): the lock's composite mints read the
        # studio-identity manifest — the fixture studio needs its genesis.
        _mg = self.studio.load("tropo-mint-id.py", "ac2_genesis_seed")
        _mg.mint_studio_identity(root=self.studio.root, minted_by='fixture-genesis')

        self.rt = self.studio.load("9e7003b1.py", "ac2_runtime")
        self.studio.assert_tools_are_rooted_here(self.rt)

    def _restore_lt(self) -> None:
        lt.LOCK_JOURNAL_DIR, lt.WORKSPACE_LOCK_PATH, lt.VAULT_ROOT = self._orig_lt

    def _lock_and_bootstrap(self):
        production_before = temp_studio.production_fingerprint()
        code, message = dl.lock_dev_spec(
            "ab000001", "talos-t50-test", files_dir=self.studio.files)
        self.assertEqual(code, 0, message)

        m = LOCK_MESSAGE_RE.search(message)
        self.assertIsNotNone(m, f"could not find activation UID in: {message!r}")
        activation_uid = m.group(1)

        run = self.rt.find_pipeline_run_for(activation_uid)
        self.assertIsNotNone(run, "lock did not leave a resolvable pipeline-run")

        contract = self.tmp / "contract-input.json"
        contract.write_text(json.dumps({
            "skips_authorized_upfront": [],
            "additional_steps_added": [],
            "trust_overrides": {},
            "human_instructions": "",
        }))
        returned_run_uid = self.rt.action_bootstrap(activation_uid, str(contract), False)
        self.assertIsInstance(returned_run_uid, str)

        production_after = temp_studio.production_fingerprint()
        self.assertEqual(
            temp_studio.diff_fingerprints(production_before, production_after),
            {},
            "AC2 live-contract lock/bootstrap touched production",
        )
        return activation_uid, run

    def test_bootstrap_and_the_first_declared_step_start_with_zero_refusals(self) -> None:
        """Proves the exact failure class G111 measured is gone: bootstrap on
        a lock-opened run, then step-start on the first declared step, refuse
        on nothing (her repro: "already has events" / "not in activation
        contract").

        Scoped to entry (bootstrap + the first step-start) rather than a full
        walk through all four: `0c6518ef`'s own verification_command is
        `python3 -m pytest -q vault/tools/tests/test_ac2_dev_lock_snapshot_transaction.py`
        -- a whole-repo-relative suite invocation that genuinely cannot run
        inside an isolated TempStudio (it has no `tests/` tree, deliberately
        -- TempStudio copies only the tool scripts a lock/bootstrap gesture
        reaches, per its own module docstring). That is an environment-
        fidelity gap in the TEST, not a defect in the runtime's contract
        logic, and conflating "does 0c6518ef's own check pass in a sandbox
        that can't run it" with "does the runtime refuse the declaration
        shape" would test the wrong thing. The full four-step walk (start ->
        complete, in order, every step accepted) was run for real against
        the actual worktree checkout during this build (not fixture, not
        isolated) with zero refusals; that transcript is attached as AC2
        evidence on the spec's run rather than re-created here as a fragile
        semi-real hybrid.
        """
        activation_uid, run = self._lock_and_bootstrap()
        folder = self.rt.run_folder_for(run["frontmatter"])
        snapshot = json.loads((folder / "declaration-snapshot.json").read_text())
        declared = snapshot.get("declared_steps") or []
        self.assertTrue(declared, "declaration snapshot declares zero steps")

        # A refusal raises (ValidationError / ContractError); the test fails
        # loudly rather than a printed warning surviving unnoticed.
        self.rt.action_step_start(activation_uid, declared[0], "talos-t50-test")

    def test_the_declared_steps_are_the_real_definitions_four_v2_leaves(self) -> None:
        """Control: prove the snapshot names the ACTUAL current leaves.

        Without this, a bug that silently declared zero or the wrong steps
        could still pass the "no refusals" test above by declaring nothing at
        all -- ignition.py already refuses on empty declarations (a separate,
        existing gate), but this asserts the CONTENT, not just non-emptiness.
        """
        _activation_uid, run = self._lock_and_bootstrap()
        folder = self.rt.run_folder_for(run["frontmatter"])
        snapshot = json.loads((folder / "declaration-snapshot.json").read_text())
        self.assertEqual(
            sorted(snapshot.get("declared_steps") or []),
            sorted(["0c6518ef", "fa3a49c8", "9d4f7e21", "0b6b244c"]),
        )


class BothNamedReadersAcceptTheConformedSnapshot(unittest.TestCase):
    """AC2's two named readers, against Metis G112's real production snapshot.

    Per her instruction (evt 2026-08-24T15:44Z): use the v1.92 Stream 2
    spec's own lock (declaration_digest 875b845a61eb..., run
    dev-pipeline-8098be20-2026-08-24) as the fixture -- it is a real,
    production-door specimen of the conformed shape, not a hand-built one.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not REAL_SNAPSHOT_PATH.is_file():
            raise unittest.SkipTest(
                f"real fixture snapshot not present at {REAL_SNAPSHOT_PATH} "
                "(this repo checkout predates the v1.92 Stream 2 lock)")
        cls.snapshot = json.loads(REAL_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        cls.run_dir = REAL_SNAPSHOT_PATH.parent

    def test_it_is_the_specimen_metis_named(self) -> None:
        self.assertTrue(
            self.snapshot.get("declaration_digest", "").startswith("875b845a61eb"),
            "REAL_SNAPSHOT_PATH no longer points at the specimen this test "
            "was written against -- repoint or re-derive the fixture path.",
        )

    def test_reader_two_release_events_snapshot_step_uids_accepts(self) -> None:
        """The Stream-1 reader AC2 names. Expected RED until Argus's fix.

        `_snapshot_step_uids` recognises `steps`/`children`/`nodes` as
        list-keys and `uid`/`step_uid`/`node_uid` as scalar keys. The real
        snapshot's field is `declared_steps`, which is none of those --
        reported to Argus A156 2026-08-24 (release_events.py is Stream 1
        substrate; not edited here). This assertion is the mutation guard AC2
        asks for: it passes the instant his fix recognises the real field,
        and it is honestly red until then rather than silently skipped.
        """
        found = _release_events._snapshot_step_uids(self.snapshot)
        self.assertEqual(
            found,
            set(self.snapshot.get("declared_steps") or []),
            "lib/release_events.py's _snapshot_step_uids() does not "
            "recognise the 'declared_steps' key -- AuthorizationContext."
            "observe() silently sees zero steps on every real run, dev or "
            "release, until this is fixed (Argus A156's lane).",
        )

    def test_authorization_context_observe_carries_the_real_step_set(self) -> None:
        """End-to-end through the actual reader AC2 names, not just its helper.

        Same expected-RED status as the test above, and for the same reason
        -- this drives AuthorizationContext.observe() itself, the entry point
        AC2's behavior text actually names, rather than only its private
        helper.
        """
        ctx = _release_events.AuthorizationContext.observe(self.run_dir)
        self.assertEqual(
            ctx.snapshot_step_uids,
            frozenset(self.snapshot.get("declared_steps") or []),
            "AuthorizationContext.observe() read zero steps off a real "
            "snapshot that declares four -- the declared_steps key mismatch "
            "in _snapshot_step_uids (Argus A156's lane).",
        )


if __name__ == "__main__":
    unittest.main()
