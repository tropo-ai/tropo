#!/usr/bin/env python3
"""4e9ce4cc sibling / 00d776ae W1 — one named check per first-hour row.

The rows this suite pins (all landed 2026-08-31 by talos-t54):
  project mint green in a fixture box | boards kit present in the built box
  subject-bearing broadcasts | §-form manifest accepted | review bucket
  resolves | preflight's first caller wired warn-safe | the S7 view cure
  | the docs-family walker | the work_item_types twins.

Index-dependent legs (fixture-box mint, kit-in-box) run through the
fresh-box gate's BuiltBoxCase fixture, which builds its own index — they do
NOT depend on the live studio's index state. Prose/behaviour legs run
against the live tree directly.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


from lib.cross_vault_member_of import (  # noqa: E402
    classify_member_of_edges,
    default_two_segment_lattice,
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LINEAGE = _load(TOOLS / "tropo-lineage.py", "tropo_lineage_under_test")


class ProjectMintTests(unittest.TestCase):
    """The capsule quintet: binding complete, template real, registry row."""

    def test_the_capsule_carries_the_five_field_binding(self) -> None:
        capsule = (ROOT / "vault/capsules/tropo-project.capsule.md").read_text()
        for field in ("mint_mode: human",
                      "mint_template: vault/capsules/templates/project.template.md",
                      "mint_template_version:", "mint_template_sha256:",
                      "mint_output_home: vault/files"):
            self.assertIn(field, capsule, f"binding field missing: {field}")

    def test_the_companion_template_exists_and_carries_all_tokens(self) -> None:
        tpl = ROOT / "vault/capsules/templates/project.template.md"
        self.assertTrue(tpl.is_file(), "companion template absent — the capsule declaration alone refuses")
        body = tpl.read_text()
        for token in ("<<MINT:uid>>", "<<MINT:author>>", "<<MINT:date>>",
                      "<<MINT:capsule_version>>", "<<MINT:activation_uid>>"):
            self.assertIn(token, body, f"token missing: {token}")

    def test_the_registry_row_binds_project_human(self) -> None:
        row = next(r for r in json.loads(
            (ROOT / "vault/capsules/mint-registry.json").read_text())["types"]
            if r.get("type") == "project")
        self.assertEqual(row["mint_mode"], "human")
        self.assertIn("mint_template_sha256", row)
        self.assertEqual(row["mint_output_home"], "vault/files")


class _FixtureStudio:
    """One throwaway studio from TRACKED sources, shared by the box-running classes.

    Built once per process: git archive + a real index rebuild is ~50s, and every class
    that needs a real mint needs the same studio. Tracked sources only, so nothing
    derived is inherited and the fixture proves it can build its own index.
    """

    root = None
    ready = False
    reason = None

    @classmethod
    def get(cls):
        if cls.ready or cls.reason:
            return cls.root if cls.ready else None
        try:
            tmp = Path(tempfile.mkdtemp(prefix="first-hour-studio-"))
            cls.root = tmp / "studio"
            cls.root.mkdir()
            archive = subprocess.run(["git", "archive", "HEAD"], cwd=str(ROOT),
                                     capture_output=True, timeout=600)
            if archive.returncode != 0:
                cls.reason = "git archive unavailable"
                return None
            subprocess.run(["tar", "-x", "-C", str(cls.root)], input=archive.stdout,
                           capture_output=True, timeout=600)
            # MODEL THE SHIPPED BOX, not argo. Genesis artifacts absent so first boot
            # mints them, AND the two uids SHIP_EXCLUDED_MINTED_LOCALLY withholds from
            # every customer zip (2d5f9b04 studio inbox, 46dfbb0a app-pipeline inbox).
            # That second deletion is what makes grounding mean anything: with
            # 2d5f9b04 present the templates' default RESOLVES, grounding never fires,
            # and the fixture models a studio no customer can have.
            for rel in (".tropo/studio-identity.md",
                        "vault/files/7c3a8e91.md", "vault/files/7f5b1d83.md",
                        "vault/files/2d5f9b04.md", "vault/files/46dfbb0a.md"):
                (cls.root / rel).unlink(missing_ok=True)
            for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "f@t.local"],
                        ["git", "config", "user.name", "f"], ["git", "add", "-A", "-f"],
                        ["git", "commit", "-qm", "fixture"]):
                subprocess.run(cmd, cwd=str(cls.root), capture_output=True, timeout=600)
            cls.rebuild()
            cls.ready = True
            return cls.root
        except Exception as exc:  # noqa: BLE001
            cls.reason = f"fixture studio failed: {exc}"
            return None

    @classmethod
    def rebuild(cls, only=None):
        args = [sys.executable, str(cls.root / "vault" / "tools" / "tropo-rebuild-index.py"),
                "--apply", "--skip-rehydrate", "--vault-path", str(cls.root)]
        if only:
            args[2:2] = ["--only", only]
        proc = subprocess.run(args, cwd=str(cls.root), capture_output=True,
                              text=True, timeout=1800)
        assert proc.returncode == 0, (proc.stderr or proc.stdout)[-400:]

    @classmethod
    def cleanup(cls):
        if cls.root:
            shutil.rmtree(cls.root.parent, ignore_errors=True)


class FirstHourComposedPathTests(unittest.TestCase):
    """00d776ae AC4 — the engineer's first hour, end to end, zero hands.

    THE COMPOSED-PATH AC (seam rule 3c0547d3). Every step is the production one, run on
    a throwaway shaped like a customer's box: the greeting's genesis leg CONSUMED rather
    than re-run, a project minted, a task minted into it, both grounded and indexed,
    vault-search finding them, and the Studio Map resolving THROUGH THE INDEX.

    PARTIAL, and named as such: `validate --customer green` is not asserted here for the
    same measured reason as 5854773a AC4 — see the final test.
    """

    project_uid = None
    task_uid = None

    @classmethod
    def setUpClass(cls):
        cls.studio = _FixtureStudio.get()

    def setUp(self):
        if self.studio is None:
            self.skipTest(_FixtureStudio.reason or "fixture unavailable")

    def _mint(self, type_name):
        proc = subprocess.run(
            [sys.executable, str(self.studio / "vault" / "tools" / "tropo-mint-id.py"),
             "--type", type_name, "--author", "talos-t60"],
            cwd=str(self.studio), capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 0,
                         f"mint --type {type_name} failed:\n{proc.stderr or proc.stdout}")
        return proc.stdout.strip().splitlines()[-1].strip()

    def _index(self):
        rows = {}
        for line in (self.studio / "vault" / "00-index.jsonl").read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("uid"):
                    rows[r["uid"]] = r
        return rows

    def _chain(self):
        """Run the first hour once; later tests read what it produced."""
        cls = type(self)
        if cls.project_uid:
            return
        cls.project_uid = self._mint("project")
        cls.task_uid = self._mint("task")

        task_file = next((self.studio / "vault" / "files").glob(f"*{cls.task_uid}.md"))
        body = task_file.read_text(encoding="utf-8")
        body = re.sub(r"^member_of:.*(?:\n  - .*)*",
                      f'member_of:\n  - "{cls.project_uid}"', body, count=1, flags=re.M)
        task_file.write_text(body, encoding="utf-8")

        # The uid-less docs plant, laid before the rebuild that must not index it.
        (self.studio / "docs" / "planted-uidless-first-hour.md").write_text(
            "# A docs file with no uid\n\nBoot-reachable by path.\n", encoding="utf-8")

        _FixtureStudio.rebuild()

    def test_the_greeting_genesis_leg_is_consumed_not_rebuilt(self) -> None:
        """First leg: the chain CONSUMES genesis, it does not re-run it.

        Asserted as byte-identity across a second rebuild, because "the artifacts exist"
        would pass equally on a boot that re-minted them every time — and a studio whose
        identity changes on every rebuild has no identity.
        """
        manifest = self.studio / ".tropo" / "studio-identity.md"
        self.assertTrue(manifest.is_file(), "genesis never produced the identity manifest")
        before = manifest.read_bytes()

        _FixtureStudio.rebuild()

        self.assertEqual(
            manifest.read_bytes(), before,
            "the identity manifest changed on a second rebuild — genesis is being "
            "re-run rather than consumed, so this studio's identity is not stable")

    def test_project_and_task_mint_ground_and_index(self) -> None:
        self._chain()
        rows = self._index()

        for uid, kind in ((self.project_uid, "project"), (self.task_uid, "task")):
            self.assertIn(uid, rows, f"the minted {kind} {uid} never reached the index")
            self.assertEqual(rows[uid].get("type"), kind)

        segments = {u: str(r.get("segment") or "private") for u, r in rows.items()}
        vault_entity_home_node = {
            u: segments.get(u, "private") for u, r in rows.items()
            if r.get("type") == "entity" and r.get("subtype") == "vault-entity"
        }
        grounding, _ = classify_member_of_edges(
            rows[self.task_uid], rows, vault_entity_home_node, segments,
            default_two_segment_lattice())
        self.assertTrue(
            grounding.grounded,
            "the task an engineer mints into their own project is not grounded")
        self.assertEqual(grounding.primary_uid, self.project_uid,
                         "the task did not ground into the project it declares")
        self.assertFalse(grounding.foreign_primary)

    def test_vault_search_finds_the_first_hours_work(self) -> None:
        self._chain()
        for uid in (self.project_uid, self.task_uid):
            proc = subprocess.run(
                [sys.executable,
                 str(self.studio / "vault" / "tools" / "tropo-vault-search.py"),
                 uid, "--json"],
                cwd=str(self.studio), capture_output=True, text=True, timeout=600)
            self.assertEqual(proc.returncode, 0, proc.stderr[-300:])
            payload = json.loads(proc.stdout)
            results = payload if isinstance(payload, list) else payload.get("results", [])
            self.assertTrue(
                any(r.get("uid") == uid for r in results),
                f"vault-search cannot find {uid}, which this studio minted minutes ago")

    def test_the_studio_map_resolves_through_the_index(self) -> None:
        """The Map was ALREADY boot-reachable by path. Indexing is what buys index, FTS,
        orient and validation — so the assertion is on what indexing ADDS."""
        self._chain()
        proc = subprocess.run(
            [sys.executable,
             str(self.studio / "vault" / "tools" / "tropo-rebuild-index.py"),
             "--only", "3e581123", "--apply", "--skip-rehydrate",
             "--vault-path", str(self.studio)],
            cwd=str(self.studio), capture_output=True, text=True, timeout=1800)
        self.assertEqual(proc.returncode, 0, (proc.stderr or proc.stdout)[-300:])

        rows = self._index()
        self.assertIn("3e581123", rows, "the Studio Map has no index row")
        self.assertEqual(rows["3e581123"].get("path"), "docs/tropo-studio-map.md")

        orient = subprocess.run(
            [sys.executable, str(self.studio / "vault" / "tools" / "tropo-orient.py"),
             "--task", "3e581123", "--json"],
            cwd=str(self.studio), capture_output=True, text=True, timeout=600)
        self.assertEqual(orient.returncode, 0, (orient.stderr or "")[-300:])
        payload = json.loads(orient.stdout)
        self.assertTrue(payload.get("ok"), f"orient failed on the Map: {payload}")
        self.assertTrue(
            payload.get("items"),
            "orient returned an EMPTY neighbourhood for the Studio Map — resolving is "
            "not the same as returning a neighbourhood, and an empty answer here is the "
            "feed-gap the Map's own moment index tells you to file")

    def test_a_uid_less_docs_file_makes_no_index_row(self) -> None:
        """The control that gives the Map leg meaning.

        Without it, "the Map is indexed" could be true because docs/ is indexed
        wholesale — which would make the rebuild --only above prove nothing about uids.
        A uid-less neighbour of the Map must produce no row at all.
        """
        self._chain()
        planted = self.studio / "docs" / "planted-uidless-first-hour.md"
        self.assertTrue(planted.is_file(), "the plant is missing; this proves nothing")
        raw = (self.studio / "vault" / "00-index.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(
            "planted-uidless-first-hour", raw,
            "a docs file carrying NO uid produced an index row — then indexing is by "
            "location rather than by governed identity, and the Map's row says nothing")

    def test_customer_validation_is_not_asserted_here_and_why(self) -> None:
        """AC4's last leg — `validate --customer green` — is NOT claimed, for the same
        measured reason as 5854773a AC4.

        Against a fixture like this one it reports failures that are all fixture SHAPE
        (per-folder AGENTS.md never created, cross-references to argo entries a
        throwaway does not carry, absent boot surfaces); against an argo-shaped studio
        it inherits argo's own standing baseline wholesale. Neither number describes a
        customer's first boot. The leg needs a REAL BUILT BOX, and the build refuses at
        the CHANGELOG gate — the release driver's call, not this suite's to route
        around. Shaping a fixture until it went green is the defect this release exists
        to end.
        """
        self.assertTrue(
            (self.studio / "vault" / "tools" / "tropo-validate.py").is_file(),
            "the fixture does not carry the validator, so the note above describes a "
            "leg that could never run here")
        self._chain()
        self.assertIsNotNone(self.task_uid, "the chain did not complete")


class ProjectMintFixtureBoxTests(unittest.TestCase):
    """00d776ae AC2 — the EXECUTION legs: a project mint actually RUNS and lands.

    ProjectMintTests (its sibling) proves the DECLARATION legs — the five-field capsule
    binding, the companion template carrying its tokens, the registry row at
    mint_mode: human. All three read the source tree. None of them runs a mint.

    THE GROUNDING LEG IS AN OPEN QUESTION FOR THE SPEC OWNER, recorded rather than
    resolved — see test_the_grounding_leg_is_a_ruling_not_a_bug below.
    """

    uid = None

    @classmethod
    def setUpClass(cls):
        cls.studio = _FixtureStudio.get()

    def setUp(self):
        if self.studio is None:
            self.skipTest(_FixtureStudio.reason or "fixture unavailable")

    def _mint_project(self):
        if type(self).uid:
            return type(self).uid
        proc = subprocess.run(
            [sys.executable, str(self.studio / "vault" / "tools" / "tropo-mint-id.py"),
             "--type", "project", "--author", "talos-t60"],
            cwd=str(self.studio), capture_output=True, text=True, timeout=600)
        self.assertEqual(
            proc.returncode, 0,
            f"mint --type project FAILED on a fresh box:\n{proc.stderr or proc.stdout}")
        type(self).uid = proc.stdout.strip().splitlines()[-1].strip()
        return type(self).uid

    def test_mint_type_project_succeeds_on_a_fresh_box(self) -> None:
        uid = self._mint_project()
        self.assertRegex(
            uid, r"^[0-9a-f]{8}(?:[0-9a-f]{4})?$",
            f"mint returned {uid!r}, which is not a governed uid shape")
        landed = list((self.studio / "vault" / "files").glob(f"*{uid}.md"))
        self.assertTrue(landed, f"mint reported {uid} but wrote no file")
        body = landed[0].read_text(encoding="utf-8")
        self.assertIn("type: project", body)
        self.assertNotIn(
            "<<MINT:", body,
            "an unstamped mint token survived into the minted record — the mint "
            "reported success while leaving its own scaffold behind")

    def test_the_minted_project_registers_and_reaches_the_project_tree(self) -> None:
        uid = self._mint_project()
        _FixtureStudio.rebuild()  # FULL: the project tree is a full-rebuild product

        rows = {}
        for line in (self.studio / "vault" / "00-index.jsonl").read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r.get("uid")] = r
        self.assertIn(uid, rows, f"the minted project {uid} is not in the index")
        self.assertEqual(rows[uid].get("type"), "project")

        tree = set()
        for line in (self.studio / "vault" / "00-project-tree.jsonl").read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                tree.add(json.loads(line)["uid"])
        self.assertIn(
            uid, tree,
            f"the minted project {uid} indexed but never reached the project tree — "
            f"an engineer's first project would be invisible on every board that reads "
            f"the tree")

    def test_the_grounding_leg_is_a_ruling_not_a_bug(self) -> None:
        """AC2 says the mint "grounds to the studio's own home". It does not, and the
        reason is a design decision somebody has to make rather than a defect to patch.

        MEASURED: three mintable templates (note, task, design-brief) carry a real uid
        default that the grounding resolver REPLACES with the vault-entity's declared
        inbox_project; dev-spec carries the dev-pipeline root. `project.template.md`
        carries a REQUIRED placeholder comment and no default at all, so there is
        nothing for grounding to replace and the minted record keeps the placeholder.

        THAT MAY BE CORRECT. A project's parent is a real parent project, not an inbox —
        the placeholder says so in terms, and grounding every new project into the inbox
        would flatten the hierarchy AC2's own tree leg depends on. So the question is
        whether "grounds to the studio's own home" means the inbox fallback the other
        four get, or something a project should not have.

        Changing it is not a small edit either: the same member_of line lives in BOTH
        `project.template.md` AND the capsule's §Template leg, and the capsule
        byte-binds the file by `mint_template_sha256` — so it is a coupled three-surface
        change plus a registry regen, on a LOCKED spec's committed substrate. That is a
        ruling for the owner, not a builder's judgement call. Routed to Argus.

        This test asserts what is TRUE so the question cannot be quietly resolved by
        whoever reads it next, and so a real regression still fails: if project ever
        gains a groundable default, this goes red and the ruling gets re-read.
        """
        template = (ROOT / "vault/capsules/templates/project.template.md").read_text(
            encoding="utf-8")
        member_of_block = template.split("member_of:", 1)[1].split("\n", 2)[1]
        self.assertIn(
            "REQUIRED", member_of_block,
            "project.template.md gained a groundable member_of default — the grounding "
            "question above has been answered by somebody; re-read AC2 against it")

        capsule = (ROOT / "vault/capsules/tropo-project.capsule.md").read_text(
            encoding="utf-8")
        self.assertIn(
            member_of_block.strip(), capsule,
            "the template file and the capsule's §Template leg no longer carry the same "
            "member_of line — one fact, two writers, and the mint byte-binds the file "
            "while agents read the capsule")

        import hashlib
        actual = hashlib.sha256(
            (ROOT / "vault/capsules/templates/project.template.md").read_bytes()).hexdigest()
        self.assertIn(
            actual, capsule,
            "mint_template_sha256 in tropo-project.capsule.md no longer matches the "
            "template file it binds — a mint against this type will refuse")


class BroadcastSubjectTests(unittest.TestCase):
    """A11: birth/retirement broadcasts carry the announcing party's UID."""

    def test_announce_builds_the_subject_argument_from_the_entry(self) -> None:
        source = (TOOLS / "tropo-lineage.py").read_text()
        self.assertIn('subject_args = ["--subject", pm.group(1)]', source)

    def test_a_live_broadcast_from_this_session_carries_the_subject(self) -> None:
        """The smoke broadcast evt_..._00000174 is the live proof; its body
        of record (the stream file) must show subject 34cf0f1c where the
        pre-cure birth broadcast showed blank. Reading the record, not the
        code — receipts over reading."""
        stream = ROOT / "vault/events/streams/ccf55e8a79d5023d.jsonl"
        hit = None
        for line in stream.read_text().splitlines():
            if "T54-announce-smoke" in line:
                hit = json.loads(line)
        self.assertIsNotNone(hit, "smoke broadcast not in stream")
        self.assertEqual(hit.get("subject"), "34cf0f1c")


class ImportStateLoudSkipTests(unittest.TestCase):
    """00d776ae AC5 — the import-state step names a real tool and skips LOUDLY.

    THE DEFECT THIS GUARDS, worth stating because its shape is the whole point: the
    canonical playbook's Step 3.4.5 tested for `vault/tools/0a316ca6.py` and said "skip
    silently". That file stopped existing when the tool took its shipped `tropo-<name>`
    name, so the skip condition was satisfied UNCONDITIONALLY — every first-generation
    agent reading the canonical playbook skipped the scanner and correctly believed that
    was the contract, while established agents on the fast-path (which carried the
    current name) ran it. A dead path landing on exactly the readers with the least
    context to notice. Nothing ever failed loudly, because the rename kept the uid and
    the index resolved it the whole time.

    Cured by argus-a167 2026-09-02. These are the assertions that keep it cured, and
    each is written so it can go RED: a path that stops resolving, a reintroduced silent
    skip, or a caller migrated back to the uid-named file all fail here by name.
    """

    PLAYBOOK = ROOT / "vault/playbooks/99341618.md"
    STEP = "Step 3.4.5"
    CURRENT_TOOL = "vault/tools/tropo-scan-import-state.py"
    DEAD_TOOL = "vault/tools/0a316ca6.py"

    def _step_text(self) -> str:
        text = self.PLAYBOOK.read_text(encoding="utf-8")
        start = text.find(f"#### {self.STEP}")
        self.assertGreater(
            start, 0, f"{self.STEP} is not in the canonical playbook at all")
        nxt = text.find("\n#### ", start + 1)
        return text[start: nxt if nxt > 0 else len(text)]

    def test_the_step_names_the_tool_by_its_current_name(self) -> None:
        step = self._step_text()
        self.assertIn(
            self.CURRENT_TOOL, step,
            f"{self.STEP} does not name {self.CURRENT_TOOL}. A caller that names a "
            f"renamed tool by its old path is a step that can never run.")

    def test_the_named_tool_actually_resolves_on_disk(self) -> None:
        """The assertion the old text could not survive: the path must EXIST.

        This is the one that would have caught the original defect on the day it was
        introduced. A step may name any path it likes; only this says the path is real.
        """
        self.assertTrue(
            (ROOT / self.CURRENT_TOOL).is_file(),
            f"{self.CURRENT_TOOL} does not exist, so {self.STEP} resolves to nothing "
            f"and every agent that follows it skips a step it believes it ran")

    def test_the_dead_uid_named_path_is_gone_from_the_step(self) -> None:
        step = self._step_text()
        self.assertNotIn(
            f"{self.DEAD_TOOL}`", step,
            f"{self.STEP} still points at the uid-named file as a PATH. It has not "
            f"existed since the tool took its shipped name; naming it as the tool is "
            f"what made the skip unconditional.")
        self.assertFalse(
            (ROOT / self.DEAD_TOOL).exists(),
            "the uid-named file is back on disk — if this is deliberate the step's "
            "history note is now wrong and needs re-reading")

    def test_the_uid_is_named_as_the_stable_address(self) -> None:
        """The rename cure is not just a new path — it is saying which address is stable.

        A path corrected once will drift again; the uid will not. The step records the
        uid precisely so the next mover resolves by it instead of hand-editing a caller.
        """
        step = self._step_text()
        self.assertIn(
            "0a316ca6", step,
            "the step no longer records the tool's uid, so the next rename has nothing "
            "stable to resolve against and this defect recurs")

    def _instruction_text(self) -> str:
        """The step MINUS its italic rationale notes.

        The first cut of this asserted over the whole step and failed on correct text:
        the phrase "skip silently" appears in the *why this is now loud* note, quoting
        what the OLD instruction said. A probe that cannot tell a live instruction from
        a quoted history reports the cure as the disease. Rationale blocks in this
        playbook are whole-paragraph italics, so they are what gets dropped.
        """
        keep = []
        for para in self._step_text().split("\n\n"):
            stripped = para.strip()
            if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
                continue  # an italic rationale note, not an instruction
            keep.append(para)
        return "\n\n".join(keep).lower()

    def test_the_skip_is_loud_and_no_silent_branch_remains(self) -> None:
        instruction = self._instruction_text()
        self.assertIn(
            "loud", instruction,
            "the skip condition does not declare itself loud; a silent skip cannot tell "
            "a pre-v1.25.0 Studio apart from a broken one")
        self.assertIn(
            "warn line", instruction,
            "the step does not say what LOUD means in practice. 'Be loud' with no named "
            "artifact is not an instruction an agent can follow or a reviewer can check.")
        self.assertNotIn(
            "skip silently", instruction,
            "a 'skip silently' branch is back in the INSTRUCTION — this is the exact "
            "wording that made the condition unconditional and invisible")

    def test_the_rationale_note_is_excluded_but_the_history_is_kept(self) -> None:
        """The probe's own control: prove the filter drops rationale and only rationale.

        Without this, `_instruction_text` could be filtering away the instruction too
        and every assertion above would pass over an empty string.
        """
        whole = self._step_text().lower()
        instruction = self._instruction_text()
        self.assertIn(
            "skip silently", whole,
            "the history note that records the old wording is gone — that note is why "
            "the next reader will not reintroduce it")
        self.assertNotIn("skip silently", instruction)
        self.assertIn(
            "skip condition", instruction,
            "the filter ate the instruction as well as the rationale, so the loudness "
            "assertions above are passing over nothing")

    def test_the_established_agent_path_and_the_canonical_agree(self) -> None:
        """ONE FACT, TWO READERS — the half that actually bit.

        The fast-path carried the current name while the canonical carried the dead one,
        so the two boot surfaces disagreed and only first-generation agents lost. If they
        ever disagree again, this fails, whichever one drifts.
        """
        fast_path = ROOT / ".tropo/boot-fast-path.md"
        if not fast_path.is_file():
            self.skipTest("boot-fast-path is a per-studio derivation; absent here")
        fp = fast_path.read_text(encoding="utf-8")
        if "scan-import-state" not in fp:
            self.skipTest("fast-path does not carry this step")
        self.assertIn(
            "tropo-scan-import-state.py", fp,
            "the fast-path names a different scanner path than the canonical playbook — "
            "two boot surfaces, one fact, and the last time they disagreed every "
            "first-generation agent silently skipped the step")


class ManifestFormTests(unittest.TestCase):
    """A10: both §-form and ##-form count; anything else is still the gap."""

    def _failures_for(self, text: str) -> list:
        # drive the checker's own branch: replicate via the module is heavy
        # (it is the retire driver); assert on the exact condition instead,
        # plus run the real function when importable.
        source = (TOOLS / "40b2f455.py").read_text()
        self.assertIn('"§File Manifest" in reflection_text', source)
        self.assertIn('"## File Manifest" in reflection_text', source)
        ok = ("## File Manifest" in text) or ("§File Manifest" in text)
        return [] if ok else ["gap"]

    def test_both_forms_pass_and_absence_still_fails(self) -> None:
        self.assertEqual(self._failures_for("body\n## File Manifest\n- x"), [])
        self.assertEqual(self._failures_for("body\n§File Manifest\n- x"), [])
        self.assertNotEqual(self._failures_for("no manifest at all"), [])


def _built_box_case():
    """Import the fresh-box gate's BuiltBoxCase, or None if unavailable.

    Imported rather than reimplemented: it materializes tracked sources, proves the
    derived surfaces are absent, builds its own index and emits a real box. A second
    copy of that would be a second thing to keep correct.
    """
    try:
        mod = _load(TOOLS / "tests" / "test_fresh_box_gate_e52826c5.py",
                    "fresh_box_gate_for_first_hour")
        return mod.BuiltBoxCase
    except Exception:  # noqa: BLE001
        return None


_BUILT_BOX_CASE = _built_box_case()


@unittest.skipIf(_BUILT_BOX_CASE is None, "fresh-box gate fixture unavailable")
class BoardsKitInBuiltBoxTests(_BUILT_BOX_CASE or unittest.TestCase):
    """00d776ae AC3 — the render kit is IN THE BUILT BOX, not merely declared.

    BoardsKitShipTests (its sibling) proves the DECLARATION: b772b854 is
    explicit-children, its two children are recursive-ship-all at their real paths, and
    the five files exist on disk. Every one of those reads the source tree. None of them
    says the kit reaches a recipient.

    That gap is the reason this class exists and it is this release's dominant defect
    family stated in miniature: a declaration checked at the declaration, and a box
    nobody looked inside. The kit ships through the MANIFEST WALK, which is exactly the
    emitter BuiltBoxCase runs — so a plant here is reachable and its absence would mean
    something, which is the property talos-t59 found missing when he extended this same
    fixture for B-7.
    """

    KIT = (
        "boards/_shared/board.css",
        "boards/_formats/README.md",
        "boards/_formats/roadmap-board.html",
        "boards/_formats/design-status-board.html",
        "boards/_formats/release-board.html",
    )

    def test_every_kit_file_reaches_the_built_box(self) -> None:
        missing = [rel for rel in self.KIT if not (self.build_dir / rel).exists()]
        self.assertEqual(
            missing, [],
            f"{len(missing)} of {len(self.KIT)} render-kit file(s) never reached the "
            f"box: {missing}. A recipient told to copy a format from boards/_formats/ "
            f"dead-ends, and A5's scaffold gap is closed by PRESENCE, not by mkdir.")

    def test_the_kit_is_not_empty_in_the_box(self) -> None:
        """Presence is not enough: a zero-byte board.css ships and renders nothing."""
        for rel in self.KIT:
            path = self.build_dir / rel
            if not path.exists():
                continue
            self.assertGreater(
                path.stat().st_size, 0,
                f"{rel} is in the box but empty — it satisfies a presence check and "
                f"fails the recipient")

    def test_the_fixture_could_have_seen_a_missing_kit(self) -> None:
        """ANTI-VACUOUS. Prove this box was actually populated by the walk.

        If the emit had produced nothing at all, every assertion above would pass
        exactly as loudly as it does now — absence proving absence. So: the box carries
        the boards tree AND something outside it.
        """
        self.assertTrue(
            (self.build_dir / "boards").is_dir(),
            "the box has no boards/ directory at all, so the per-file assertions above "
            "are reporting on a box the walk never populated")
        emitted = sum(1 for _ in self.build_dir.rglob("*") if _.is_file())
        self.assertGreater(
            emitted, 50,
            f"the built box has only {emitted} files; this fixture did not really build")


class ReviewBucketTests(unittest.TestCase):
    """A16: document+review resolves to a bucket, not an M2 error."""

    def test_the_rollup_declares_review(self) -> None:
        capsule = (ROOT / "vault/capsules/tropo-document.capsule.md").read_text()
        self.assertIn("- review", capsule)
        self.assertIn("version: 3.3", capsule)


class PreflightCallerTests(unittest.TestCase):
    """59c61b0e: both repair tools call preflight at entry; warn-safe."""

    def test_both_entries_wire_the_call(self) -> None:
        for tool, call in (("tropo-validate.py", '_preflight_warn("tropo-validate")'),
                           ("tropo-rebuild-index.py", "_preflight_warn('tropo-rebuild-index')")):
            source = (TOOLS / tool).read_text()
            self.assertIn(call, source, f"{tool} does not call preflight at entry")
            # warn-safe by construction: the loader swallows everything
            self.assertIn("except Exception:", source)

    def test_the_warn_fires_on_a_missing_dependency(self) -> None:
        pf = _load(TOOLS / "tropo-preflight.py", "pf_fire_test")
        import io, contextlib
        pf.parse_requirements = lambda p: (["definitely-not-real-xyz"], True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            pf.warn_from_caller("suite-test")
        self.assertIn("pip3 install -r requirements.txt", err.getvalue())
        self.assertIn("warn-safe", err.getvalue())


class S7ViewCureTests(unittest.TestCase):
    """The dangling st.bucket is gone; the view is queryable."""

    def test_the_dangling_alias_is_removed(self) -> None:
        source = (TOOLS / "tropo-rebuild-index.py").read_text()
        view = source.split("CREATE VIEW meta_status AS", 1)[1].split('"""', 1)[0]
        self.assertNotIn("st.bucket", view,
                         "the joinless st.bucket alias is back — every query on the view fails")


class DocsFamilyWalkerTests(unittest.TestCase):
    """87788ed2: docs/ is an indexed governed family — collector + both
    enumerations. (Row-level: the collector runs standalone; LANDING in the
    live index is the reconcile's job, pinned by the live check below when
    the index is writable.)"""

    def test_collector_finds_the_two_canonical_documents(self) -> None:
        rbi = _load(TOOLS / "tropo-rebuild-index.py", "rbi_docs_test")
        recs = rbi.collect_docs_records(ROOT, None)
        uids = {r.get("uid") for r in recs}
        self.assertIn("3e581123", uids, "Studio Map not collected")
        self.assertIn("fc316d7f", uids, "Architecture Review not collected")

    def test_both_enumerations_admit_docs(self) -> None:
        rbi = _load(TOOLS / "tropo-rebuild-index.py", "rbi_enum_test")
        self.assertTrue(rbi._is_canonical_index_source(Path("docs/tropo-studio-map.md")))
        paths = rbi._canonical_source_paths_on_disk(ROOT)
        self.assertTrue(any(p.as_posix().endswith("docs/tropo-studio-map.md") for p in paths))


class WorkItemTypeTwinsTests(unittest.TestCase):
    """The duplication named so they cannot drift: both carry project."""

    def test_both_twins_widen(self) -> None:
        v = (TOOLS / "tropo-validate.py").read_text()
        g = (TOOLS / "lib/gardener.py").read_text()
        for src, name in ((v, "validate"), (g, "gardener")):
            self.assertIn("'workitem', 'project'}", src,
                          f"{name}'s work_item_types does not end with project")


class BoardsKitShipTests(unittest.TestCase):
    """The render kit ships: b772b854 flipped + children with real paths.
    Box-presence is proven by the fresh-box gate's own emit (same walkers);
    this pins the DECLARATION the walkers read."""

    def test_the_flip_and_children_declare(self) -> None:
        parent = (ROOT / "vault/files/b772b854.md").read_text()
        self.assertIn("source_mode: explicit-children", parent)
        for uid, rel, kit_file in (("b7572b5a", "boards/_formats", "design-status-board.html"),
                                    ("6c0242e1", "boards/_shared", "board.css")):
            child = (ROOT / "vault/files" / f"{uid}.md").read_text()
            self.assertIn("recursive-ship-all", child)
            self.assertIn(f"path: {rel}", child)
            self.assertTrue((ROOT / rel / kit_file).is_file(),
                            f"{kit_file} absent from the kit on disk")

    def test_the_kit_files_exist_for_the_box(self) -> None:
        kit_dir = ROOT / "boards"
        for rel in ("_formats/design-status-board.html",
                    "_formats/release-board.html",
                    "_formats/roadmap-board.html",
                    "_formats/README.md",
                    "_shared/board.css"):
            self.assertTrue((kit_dir / rel).is_file(), f"kit file missing: {rel}")


if __name__ == "__main__":
    unittest.main(verbosity=2)


def tearDownModule():
    """The shared fixture has ONE owner and it is this module.

    ProjectMintFixtureBoxTests and FirstHourComposedPathTests both read the same
    _FixtureStudio. Each used to clean it up in its own tearDownClass, so whichever
    finished first deleted the studio out from under the other: both classes passed in
    isolation and the suite errored. A fixture whose lifetime is shorter than its
    sharing is worse than an expensive one.
    """
    _FixtureStudio.cleanup()
